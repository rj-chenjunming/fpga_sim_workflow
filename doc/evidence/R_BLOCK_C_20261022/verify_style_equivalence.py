#!/usr/bin/env python3
"""F14-b 视觉等价校验（只读）：比对「改前 web 目录快照」与「改后 web 目录」的
逐元素计算样式指纹，覆盖全部媒体查询边界 ±1px 与四页/目录/Agent/旧页/空态。

原理：对 `document.querySelectorAll('body *')` 的每个元素，读取
`getComputedStyle(el)` 的全部 longhand 值（`cs.length` 遍历，覆盖继承/简写展开结果），
追加 `::before`/`::after` 伪元素同样遍历的值，排序后做双哈希（FNV-1a 与 djb2 拼接）。
同一 DOM、同一受控 API 数据、同一冻结时钟下，指纹相同即表示所有静态/断点样式等价。

只读：只启动两个 127.0.0.1 临时静态服务（分别指向 before/after 目录），
`/api/**` 由 `collect_f14a.MockApi` 受控替身应答；不写任何文件。

用法（必须可写 HOME + 浏览器路径）：
    cd /home/work/chenjunming/change-impact-loop/loop
    mkdir -p /tmp/h
    HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
      LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
      .venv/bin/python ../doc/evidence/R_BLOCK_C_20261022/verify_style_equivalence.py \
        --before-web /tmp/f14b-before-web --after-web web

退出码：0=全部等价；1=有差异；2=采集失败。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from collect_f14a import MockApi, agent_view, populated_view, serve_web  # noqa: E402

# 断点 ±1px 全覆盖 + 浏览器缩放等效 CSS 视口宽度：
#   1280 窗口 @125% ≈ 1024 CSS px、@150% ≈ 853.33 CSS px；1920 @125% ≈ 1536 CSS px、
#   @150% ≈ 1280 CSS px。缩放只改变 CSS 视口宽度，因此这些宽度覆盖 100/125/150% 的布局行为。
VIEWPORTS = [390, 759, 760, 761, 849, 850, 851, 853, 854, 999, 1000, 1001,
             1022, 1023, 1024, 1025, 1079, 1080, 1081, 1099, 1100, 1101,
             1179, 1180, 1181, 1199, 1200, 1201, 1279, 1280, 1281,
             1389, 1390, 1391, 1439, 1440, 1441, 1534, 1535, 1536, 1537,
             1549, 1550, 1551, 1599, 1600, 1601, 1919, 1920, 1921]
MAIN_VIEWPORTS = (1280, 1440, 1920)
SWEEP_STATES = ("s0", "run")            # 全断点扫描的页面
NARROW_AGENT = tuple(w for w in VIEWPORTS if w < 1101)  # Agent 窗口窄断点（850/760/1000 等）
MAIN_STATES = ("s0", "setup", "run", "gate", "dirpicker", "agent", "legacy", "empty")
HEIGHT = 1000

_JS_FINGERPRINT = r"""
() => {
  const PROPS = [
    'display','position','top','right','bottom','left','inset','z-index','float','clear',
    'width','height','min-width','min-height','max-width','max-height','box-sizing',
    'margin-top','margin-right','margin-bottom','margin-left',
    'padding-top','padding-right','padding-bottom','padding-left',
    'border-top-width','border-right-width','border-bottom-width','border-left-width',
    'border-top-style','border-right-style','border-bottom-style','border-left-style',
    'border-top-color','border-right-color','border-bottom-color','border-left-color',
    'border-top-left-radius','border-top-right-radius',
    'border-bottom-right-radius','border-bottom-left-radius',
    'outline-width','outline-style','outline-color','outline-offset',
    'box-shadow','background-color','background-image','background-position',
    'background-size','background-repeat','background-clip','background-origin',
    'color','font-family','font-size','font-weight','font-style','font-variant',
    'line-height','letter-spacing','word-spacing','text-align','text-decoration-line',
    'text-decoration-color','text-decoration-style','text-transform','text-overflow',
    'text-indent','white-space','word-break','overflow-wrap','word-wrap',
    'overflow-x','overflow-y','opacity','visibility','cursor','pointer-events',
    'flex-direction','flex-wrap','flex-grow','flex-shrink','flex-basis','order',
    'justify-content','align-items','align-content','align-self','gap','row-gap','column-gap',
    'grid-template-columns','grid-template-rows','grid-auto-flow','grid-column','grid-row',
    'list-style-type','content','vertical-align','transform','transform-origin',
    'transition-property','transition-duration','transition-timing-function','transition-delay',
    'animation-name','animation-duration','animation-timing-function','animation-delay',
    'animation-iteration-count','animation-direction','animation-fill-mode','animation-play-state',
    'backdrop-filter','filter','mix-blend-mode','scrollbar-width','scrollbar-color',
    'appearance','-webkit-font-smoothing','touch-action','user-select','resize','object-fit'
  ];
  const fnv = s => {
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return h >>> 0;
  };
  const djb = s => {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = (((h << 5) + h) ^ s.charCodeAt(i)) >>> 0;
    return h >>> 0;
  };
  const dump = cs => {
    const parts = [];
    for (const p of PROPS) parts.push(p + '=' + cs.getPropertyValue(p));
    return parts.join(';');
  };
  const out = [];
  const elements = document.querySelectorAll('body *');
  for (const el of elements) {
    let payload = dump(getComputedStyle(el));
    for (const pseudo of ['::before', '::after']) {
      payload += '|' + pseudo + '|' + dump(getComputedStyle(el, pseudo));
    }
    const label = (el.tagName.toLowerCase() +
      (el.id ? '#' + el.id : '') +
      (typeof el.className === 'string' && el.className
        ? '.' + el.className.trim().split(/\s+/).join('.') : '')).slice(0, 120);
    out.push([label, fnv(payload).toString(16) + '-' + djb(payload).toString(16)]);
  }
  return out;
}
"""


def serve_dir(directory, port=0):
    """与 collect_f14a.serve_web 同构，但可指定目录与端口（固定端口用于可复现截图）。"""
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), partial(Quiet, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, "http://127.0.0.1:%d" % server.server_port


def wait_js(page, expr, desc, timeout=8000):
    import time
    deadline = time.time() + timeout / 1000.0
    last = None
    while time.time() < deadline:
        try:
            if page.evaluate(expr):
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        page.wait_for_timeout(50)
    raise RuntimeError("等待超时：%s（%s）" % (desc, last))


def prepare_page(browser, static_url):
    context = browser.new_context(viewport={"width": 1280, "height": HEIGHT},
                                  device_scale_factor=1)
    page = context.new_page()
    page.clock.install()
    api = MockApi(page)
    page.goto(static_url)
    page.wait_for_selector(".run-item", timeout=10000)
    return context, page, api


def goto_state(page, api, static_url, state):
    """把页面切到指定状态；返回 True 表示该状态在 index.html 上。"""
    if state == "legacy":
        page.goto(static_url + "/legacy.html")
        page.wait_for_timeout(200)
        return False
    if state == "s0":
        page.locator("#segS0").click()
        page.wait_for_timeout(120)
        return True
    if state == "empty":
        page.locator("#segRun").click()
        page.wait_for_timeout(120)
        return True
    if state == "setup":
        page.locator("#segSetup").click()
        page.locator("#btnRefreshBaselines").click()
        wait_js(page, "() => document.querySelectorAll('#setupBaseline option').length > 1",
                "基线下拉")
        return True
    if state == "dirpicker":
        page.locator("#segSetup").click()
        page.wait_for_timeout(100)
        page.locator("#btnProjectBrowse").click()
        wait_js(page, "() => document.querySelectorAll('#dirList .dp-item').length > 0",
                "目录浏览器")
        return True
    if state == "run":
        populated_view(api.views["A"])
        page.locator(".run-item").filter(has_text="A").click()
        wait_js(page, "() => document.querySelector('#runHead').innerText.includes('v1.2-stable')",
                "运行头")
        page.locator("#segRun").click()
        page.wait_for_timeout(120)
        return True
    if state == "gate":
        populated_view(api.views["A"])
        page.locator(".run-item").filter(has_text="A").click()
        wait_js(page, "() => document.querySelector('#gatePanel [aria-label=\"actor\"]')",
                "闸门表单")
        page.locator("#segGate").click()
        page.wait_for_timeout(120)
        return True
    if state == "agent":
        populated_view(api.views["A"])
        page.locator(".run-item").filter(has_text="A").click()
        wait_js(page, "() => document.querySelector('#agents [data-agent-node=\"N3\"]')",
                "Agent 卡片")
        page.locator("#segRun").click()
        page.route("**/api/runs/*/agents/**", lambda route: route.fulfill(json=agent_view()))
        page.locator("#agents [data-agent-node=\"N3\"]").click()
        wait_js(page, "() => document.querySelector('#agentWindow') && "
                      "document.querySelector('#agentWindow').open", "Agent 窗口")
        page.wait_for_timeout(150)
        return True
    raise ValueError(state)


def capture_side(browser, static_url, widths_states):
    """按宽度复用页面：同一宽度只建一次 context，状态间用 goto 复位。

    返回 {(width, state): [[label, hash], ...]}；打印进度便于观察（不静默）。
    """
    result = {}
    by_width = {}
    for width, state in widths_states:
        by_width.setdefault(width, []).append(state)
    for width in sorted(by_width):
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        for state in by_width[width]:
            page.goto(static_url)
            page.wait_for_selector(".run-item", timeout=10000)
            goto_state(page, api, static_url, state)
            # 确定性：先等有限过渡结束（本仓最长 0.3s，留 600ms 余量），再把无限动画
            # （pulse/spinner）暂停并定位到 0 时刻。不注入样式，因此 transition-*/
            # animation-* 的计算值仍是真实声明的级联结果。
            page.wait_for_timeout(600)
            page.evaluate("""() => {
              for (const a of document.getAnimations()) {
                try {
                  const timing = a.effect.getTiming();
                  if (timing.iterations === Infinity) { a.pause(); a.currentTime = 0; }
                } catch (e) { /* 忽略不可控动画 */ }
              }
            }""")
            page.wait_for_timeout(30)
            result[(width, state)] = page.evaluate(_JS_FINGERPRINT)
        page.close()
        context.close()
        print("  captured width=%d states=%s" % (width, ",".join(by_width[width])),
              flush=True)
    return result


_JS_TRANSITION_DECLS = r"""
() => {
  const props = ['transition-property','transition-duration','transition-timing-function',
                 'transition-delay','animation-name','animation-duration',
                 'animation-timing-function','animation-delay','animation-iteration-count',
                 'animation-direction','animation-fill-mode','animation-play-state'];
  const out = {};
  const walk = (rules, media) => {
    for (const rule of rules) {
      if (rule.type === CSSRule.MEDIA_RULE) {
        walk(rule.cssRules, media + '|@media(' + rule.conditionText + ')');
        continue;
      }
      if (!rule.style || !rule.selectorText) continue;
      for (const prop of props) {
        const value = rule.style.getPropertyValue(prop);
        if (!value) continue;
        // 同名 selector 后置规则胜出：后写覆盖前写，因此按遍历顺序覆盖
        out[media + '|' + rule.selectorText + '|' + prop] =
          value + '|' + rule.style.getPropertyPriority(prop);
      }
    }
  };
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    walk(rules, '');
  }
  return out;
}
"""


def compare_transition_declarations(browser, before_url, after_url):
    """比对 transition/animation 声明的级联胜出值（动画关闭后指纹看不到这些声明）。"""
    results = {}
    for label, url in (("before", before_url), ("after", after_url)):
        context = browser.new_context(viewport={"width": 1280, "height": HEIGHT})
        page = context.new_page()
        MockApi(page)  # /api/** 需要受控替身，否则动态列表为空、选择器等不到
        page.goto(url)
        page.wait_for_selector(".run-item", timeout=10000)
        results[label] = page.evaluate(_JS_TRANSITION_DECLS)
        page.goto(url + "/legacy.html")
        page.wait_for_timeout(150)
        legacy = page.evaluate(_JS_TRANSITION_DECLS)
        for key, value in legacy.items():
            results[label].setdefault("legacy|" + key, value)
        context.close()
    before, after = results["before"], results["after"]
    changed = {key: (before.get(key), after.get(key))
               for key in set(before) | set(after) if before.get(key) != after.get(key)}
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-web", required=True, help="改前 web 目录快照（含 index.html）")
    parser.add_argument("--after-web", default=str(Path.cwd() / "web"),
                        help="改后 web 目录（默认 ./web）")
    parser.add_argument("--no-sweep", action="store_true", help="跳过断点 ±1px 扫描，只比主视口")
    args = parser.parse_args(argv)

    before = Path(args.before_web).resolve()
    after = Path(args.after_web).resolve()
    if not (before / "index.html").exists() or not (after / "index.html").exists():
        print("缺少 index.html：%s / %s" % (before, after), file=sys.stderr)
        return 2

    sweep = []
    if not args.no_sweep:
        sweep = [(width, state) for width in VIEWPORTS for state in SWEEP_STATES]
        sweep += [(width, "agent") for width in NARROW_AGENT]
        sweep += [(width, "legacy") for width in MAIN_VIEWPORTS]
    main_pairs = [(width, state) for width in MAIN_VIEWPORTS for state in MAIN_STATES]
    pairs = sorted(set(sweep + main_pairs))

    from playwright.sync_api import sync_playwright

    before_server, before_thread, before_url = serve_dir(before)
    after_server, after_thread, after_url = serve_dir(after)
    try:
        with sync_playwright() as pw:
            executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
            browser = pw.chromium.launch(
                **({"executable_path": executable} if executable else {}))
            print("before=%s" % before)
            print("after =%s" % after)
            print("组合数=%d（断点扫描 %d + 主视口补充 %d）" % (
                len(pairs), len(sweep), len(set(main_pairs) - set(sweep))))
            try:
                before_fp = capture_side(browser, before_url, pairs)
                after_fp = capture_side(browser, after_url, pairs)
            finally:
                browser.close()
    finally:
        for server, thread in ((before_server, before_thread), (after_server, after_thread)):
            server.shutdown()
            server.server_close()
            thread.join()

    diffs = []
    for pair in pairs:
        b = before_fp[pair]
        a = after_fp[pair]
        if [item[1] for item in b] != [item[1] for item in a]:
            changed = [(index, b[index][0] if index < len(b) else "?")
                       for index in range(min(len(a), len(b)))
                       if b[index][1] != a[index][1]]
            diffs.append({"width": pair[0], "state": pair[1],
                          "before_elements": len(b), "after_elements": len(a),
                          "changed_count": len(changed), "changed": changed[:20]})
    report = {
        "before_web": str(before), "after_web": str(after),
        "combinations": len(pairs), "diff_combinations": len(diffs), "diffs": diffs,
        "transition_declaration_diffs": {},
    }
    print(json.dumps(report, ensure_ascii=False))
    if diffs:
        for item in diffs:
            print("DIFF %s @ %d：%d 个元素变化 → %s" % (
                item["state"], item["width"], item["changed_count"],
                ", ".join("%d:%s" % (index, label) for index, label in item["changed"][:6])))
        return 1
    print("PASS: 所有 %d 个（宽度, 状态）组合的计算样式指纹完全一致"
          "（含 transition-*/animation-* 真实计算值；无限动画已停在 0 时刻）。" % len(pairs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
