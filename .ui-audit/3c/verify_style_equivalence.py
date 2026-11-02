#!/usr/bin/env python3
"""3C 视觉等价校验（只读）：比对「改前 web 目录快照」与「改后 web 目录」的
逐元素计算样式指纹，覆盖全部媒体查询边界 ±1px 与四页/目录/Agent/节点详情/旧页/空态。

原理：对 `document.querySelectorAll('body *')` 的每个元素，读取
`getComputedStyle(el)` 的全部 longhand 值（`cs.length` 遍历，覆盖继承/简写展开结果），
追加 `::before`/`::after` 伪元素同样遍历的值，排序后做双哈希（FNV-1a 与 djb2 拼接）。
同一 DOM、同一受控 API 数据、同一冻结时钟下，指纹相同即表示所有静态/断点样式等价。

只读：只启动两个 127.0.0.1 临时静态服务（分别指向 before/after 目录），
`/api/**` 由 `collect_f14a.MockApi` 受控替身应答；不写任何文件。

本副本（.ui-audit/3c/）相对冻结证据 doc/evidence/R_BLOCK_C_20261022/ 的改动逐条：
  1. REPO/import：`collect_f14a.py` 一并复制到本目录，其 REPO 由 `HERE.parents[2]`
     改为 `HERE.parents[1]`（见该文件第 47-53 行注释）；本文件 import 仍按同目录解析，
     `HERE` 解析逻辑本身未改。
  2. 主视口用真实高度：1280×720 / 1440×900 / 1920×1080（冻结版统一 height=1000；
     `--gate-pane-max-h` 用 `100dvh`，视口高度决定闸门两栏，必须真实）。断点扫描仍用 height=1000。
  3. 新增状态 `node-detail`：运行视图点开 `#viewRun [data-node-chip="N1"]` → `#nodeDetail` 浮层；
     `/api/runs/*/nodes/*` 由 page.route 补最小受控应答（同形于只读参考
     loop/tests/browser/test_node_detail.py::node_detail）。
  4. 新增交互态（2026-10-30 实测事故驱动）：CSS 合并曾把
     `:where(button,a,summary):focus-visible{...}` 拆坏、浏览器整条丢弃、焦点环消失，而
     只测非焦点态的旧指纹仍报 0 差异。因此新增：
       · focus 状态：在 s0 与 gate 上用键盘 Tab 逐次移动焦点到 button/a/summary/input/.rail-entry，
         每落一次抓一遍指纹（覆盖 :focus / :focus-visible / input:focus 等交互声明）；
       · hover 状态：page.hover() 到 .btn/.rail-entry/.run-item/.agent-open/.crumb-seg 各一次并抓指纹；
       · 样式表规则数对账：每个状态递归展开 document.styleSheets（含 @media/@supports/keyframes），
         输出逐条 selectorText + 声明数，断言 before/after 的**总条数与逐条序列完全一致**——
         浏览器静默丢弃非法选择器时，这条能抓到「整条规则消失」。
     抓不到的焦点/悬停目标不静默跳过：记为 reached=False（两侧不一致直接判 DIFF）。
  其余（无限动画停 0 时刻、`::before`/`::after` 采集、双哈希、判据）一律未放宽。

用法（必须可写 HOME + 浏览器路径；HOME/TMPDIR 指向仓库内可写目录）：
    R=/home/work/chenjunming/change-impact-loop
    cd $R/loop
    PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
      .venv/bin/python $R/.ui-audit/3c/verify_style_equivalence.py \
        --before-web $R/.ui-audit/3c/snap-harness-before \
        --after-web  $R/.ui-audit/3c/snap-harness-after [--no-sweep]

输出：一行 JSON 摘要（stdout）+ 有差异时逐条 `DIFF <state> @ <width>`，末行 `PASS` 或 `DIFF`。
退出码：0=全部等价；1=有差异；2=采集失败（目录缺 index.html 等）。
覆盖组合：主视口 3 × 9 状态（含 node-detail）+ 断点扫描 51 宽度 × (s0,run) + 窄断点 agent + 三主视口 legacy。
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
# 3C 改动 2：主视口用真实高度（冻结版统一 HEIGHT=1000，看不到 100dvh 的真实效果）。
MAIN_VIEWPORTS = ((1280, 720), (1440, 900), (1920, 1080))
SWEEP_STATES = ("s0", "run")            # 全断点扫描的页面
NARROW_AGENT = tuple(w for w in VIEWPORTS if w < 1101)  # Agent 窗口窄断点（850/760/1000 等）
# 3C 改动 3：新增 node-detail（运行视图里的 #nodeDetail 浮层）。
MAIN_STATES = ("s0", "setup", "run", "gate", "dirpicker", "agent", "node-detail",
               "legacy", "empty")
# 3C 改动 4：交互态（focus/hover）。这些不是「页面视图」，而是「视图 + 指针/键盘态」，
# 用 `<kind>:<基线状态>:<目标>` 作为状态 id，与基础状态共用同一采集/比对管线。
FOCUS_STATES = ("s0", "gate")
FOCUS_TARGETS = ("button", "a", "summary", "input", ".rail-entry")
HOVER_TARGETS = (("s0", ".btn"), ("s0", ".rail-entry"), ("s0", ".run-item"),
                 ("run", ".agent-open"), ("dirpicker", ".crumb-seg"))
MAX_TABS = 40                           # Tab 上限，防死循环；真到上限记为 reached=False（不静默跳过）
SWEEP_HEIGHT = 1000                     # 断点扫描仍用固定高度，保持与冻结版可比
HEIGHT = SWEEP_HEIGHT                   # 兼容旧引用（prepare_page 已改用真实主视口高度）

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

# 3C 改动 4b：样式表规则序列（逐条 selectorText + 声明数）。浏览器会静默丢弃非法选择器，
# 只比计算样式看不到「规则整条消失」；这条序列把「规则集合本身」纳入判据。
_JS_RULES = r"""
() => {
  const out = [];
  const walk = (rules, prefix) => {
    for (const rule of rules) {
      const type = rule.type;
      if (type === 4 || type === 12) {            // MEDIA_RULE / SUPPORTS_RULE
        const cond = rule.conditionText || (rule.media && rule.media.mediaText) || '';
        out.push(prefix + '@' + (type === 4 ? 'media' : 'supports') + '(' + cond + ')');
        walk(rule.cssRules, prefix + '[' + cond + ']');
        continue;
      }
      if (type === 7) {                            // KEYFRAMES_RULE
        out.push(prefix + '@keyframes ' + (rule.name || '?'));
        for (const frame of rule.cssRules) {
          out.push(prefix + '  ' + frame.keyText + ' {' + (frame.style ? frame.style.length : 0) + '}');
        }
        continue;
      }
      if (rule.selectorText !== undefined) {
        out.push(prefix + rule.selectorText + ' {' + (rule.style ? rule.style.length : 0) + '}');
      }
    }
  };
  for (const sheet of document.styleSheets) {
    let rules;
    try {
      rules = sheet.cssRules;
    } catch (e) {
      out.push('!!blocked ' + (sheet.href || 'inline') + ' ' + (e && e.name));
      continue;
    }
    out.push('##sheet ' + (sheet.href ? sheet.href.replace(/^https?:\/\/[^/]+/, '') : 'inline')
             + ' rules=' + rules.length);
    walk(rules, '');
  }
  return out;
}
"""


def js_rules(page):
    """返回 [规则序列, ...]（含 sheet 头行），用于规则集合对账。"""
    return page.evaluate(_JS_RULES)


def reset_focus(page):
    """把焦点复位到 body，保证 Tab 起点确定（否则上一次交互残留会改变 Tab 次数）。"""
    page.evaluate("() => { const a = document.activeElement;"
                  " if (a && a.blur) a.blur(); if (document.body) document.body.focus(); }")
    page.wait_for_timeout(20)


_JS_TARGET_PRESENT = r"""
(sel) => {
  let list;
  try { list = document.querySelectorAll(sel); } catch (e) { return false; }
  for (const el of list) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0.5 && r.height > 0.5) return true;
  }
  return false;
}
"""


def focus_by_tab(page, selector):
    """键盘 Tab 逐次移动焦点，直到 `document.activeElement.matches(selector)`。

    返回 (reached, tabs, active_label)；reached=False 表示没有可见目标或 MAX_TABS 内
    没落到目标（调用方必须如实记录，不得静默跳过）。
    先做「目标是否可见存在」预判：目标不存在时**一次 Tab 都不按**——
    否则 120 次 Tab 会跨越页面的异步重渲染窗口，焦点落点变得不可复现（实测 2026-10-30
    在 gate 视图的 summary 上出现过两侧指纹不一致，属工具噪声，不是样式差异）。
    """
    if not page.evaluate(_JS_TARGET_PRESENT, selector):
        return False, 0, "not-present(%s)" % selector
    reset_focus(page)
    for step in range(1, MAX_TABS + 1):
        page.keyboard.press("Tab")
        page.wait_for_timeout(10)
        state = page.evaluate(
            """(sel) => {
              const el = document.activeElement;
              if (!el || el === document.body) return {match: false, label: 'body'};
              let matched = false;
              try { matched = el.matches(sel); } catch (e) { matched = false; }
              const cls = (el.getAttribute('class') || '').trim().split(/\s+/).slice(0, 2).join('.');
              return {match: matched,
                      label: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
                             + (cls ? '.' + cls : '')};
            }""", selector)
        if state["match"]:
            return True, step, state["label"]
    return False, MAX_TABS, "unreached(%s)" % selector


def hover_target(page, selector):
    """hover 一个选择器的首个可见元素；返回 (reached, note)。"""
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            return False, "no-match"
        locator.scroll_into_view_if_needed(timeout=3000)
        locator.hover(timeout=3000)
        page.wait_for_timeout(30)
        return True, "hovered"
    except Exception as exc:  # noqa: BLE001 - 记录原因，不静默跳过
        return False, "hover-failed:%s" % type(exc).__name__


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
    # 3C 改动 2：主视口默认用 1280×720 真实高度。
    context = browser.new_context(viewport={"width": 1280, "height": 720},
                                  device_scale_factor=1)
    page = context.new_page()
    page.clock.install()
    api = MockApi(page)
    page.goto(static_url)
    page.wait_for_selector(".run-item", timeout=10000)
    return context, page, api


def node_detail_payload(run="A", node="N1"):
    """`GET /api/runs/{run}/nodes/{node}` 的最小受控应答（同形于只读参考
    loop/tests/browser/test_node_detail.py::node_detail；此处只保留渲染路径所需字段，
    时间戳固定为常量，确保两次采集完全一致）。"""
    return {
        "run_id": run, "node": node, "known": True, "kind": "host",
        "name": "摄取", "owner": "Host", "status": "ok",
        "started_at": 1792650932.891, "finished_at": 1792650933.5,
        "source": "drill_fixture",
        "summary": "N1：v0→v1，manifest 已产出",
        "detail": {"artifact": "/kb/runs/A/n1_manifest_new.json", "parent": "v0",
                   "allfiles_count": 3374, "cases_frozen": 162},
        "refs": ["/kb/runs/A/n1_manifest_new.json"],
        "events": [
            {"seq": 4, "kind": "node_started", "node": node, "status": "running",
             "ts": 1792650932.891},
            {"seq": 5, "kind": "node_finished", "node": node, "status": "ok",
             "ts": 1792650933.5, "detail": {"source": "drill_fixture"},
             "refs": ["/kb/runs/A/n1_manifest_new.json"]},
        ],
        "missing_fields": ["manifest_entries"],
        "authority": "projection",
        "run_status": "waiting_gate", "run_terminal": False,
        "node_started_present": True, "gate": None, "report": None,
        "story": {
            "purpose": "给当前代码和文档拍一张快照：多少文件、什么指纹、哪些用例，作为对比起点。",
            "headline": "快照完成：3374 个文件，冻结 162 个用例。",
            "headline_source": "template", "note": None,
            "not_reached": False, "not_executed": False, "evidence_note": None,
            "status_note": None,
            "status_glossary": {
                "ok": "通过", "fail": "未通过", "live": "真实模型调用",
                "standin": "替身（非模型结论）", "intact": "完整", "broken": "不完整",
                "confirmed": "已确认", "ignored": "忽略", "waiting": "等待中",
                "failed": "未通过", "not_reached": "未到达",
            },
            "steps": [
                {"seq": 4, "at": 1792650932.891, "kind": "node_started",
                 "status": "running", "text": "开始执行"},
                {"seq": 5, "at": 1792650933.5, "kind": "node_finished",
                 "status": "ok", "text": "结束，状态 ok"},
            ],
            "key_results": [
                {"field": "artifact", "label": "清单文件",
                 "value": "/kb/runs/A/n1_manifest_new.json",
                 "text": "n1_manifest_new.json", "missing": False},
                {"field": "parent", "label": "父基线", "value": "v0",
                 "text": "v0", "missing": False},
            ],
        },
    }


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
    if state == "node-detail":
        # 3C 改动 3：host 节点 N1（不在 AGENT_DEFS 里）点击后直接打开 #nodeDetail 浮层。
        # N1 属于「摄取」段，而 current_node=N4 也在该段 ⇒ 该段默认展开、chip 可见。
        populated_view(api.views["A"])
        page.locator(".run-item").filter(has_text="A").click()
        wait_js(page, "() => document.querySelector('#gatePanel [aria-label=\"actor\"]')",
                "闸门表单")
        page.locator("#segRun").click()
        page.route("**/api/runs/*/nodes/*",
                   lambda route: route.fulfill(json=node_detail_payload("A", "N1")))
        page.locator('#viewRun [data-node-chip="N1"]').click()
        wait_js(page, "() => { const d = document.querySelector('#nodeDetail');"
                      " return !!d && d.open; }", "节点详情浮层")
        # 等数据渲染完（状态 chip 从「加载中」变为服务端 status），否则两次采集可能
        # 分别落在「加载中」/「已渲染」两帧上。
        wait_js(page, "() => { const s = document.querySelector('#ndStatus');"
                      " return !!s && s.innerText.trim() !== '加载中'; }", "节点详情数据")
        page.wait_for_timeout(150)
        return True
    raise ValueError(state)


def settle(page):
    """确定性：先等有限过渡结束（本仓最长 0.3s，留 600ms 余量），再把无限动画
    （pulse/spinner）暂停并定位到 0 时刻。不注入样式，因此 transition-*/
    animation-* 的计算值仍是真实声明的级联结果。"""
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


def apply_state(page, api, static_url, state):
    """把页面切到 state 描述的目标态；返回 dict(extra) 记录交互态是否真正落到目标。

    基础状态直接驱动 index.html/legacy.html；交互态用 `<kind>:<基线状态>:<目标>`：
      · focus:...  → 先切基线状态，键盘 Tab 到目标，再抓指纹
      · hover:...  → 先切基线状态，指针悬停到目标，再抓指纹
    """
    if ":" not in state:
        goto_state(page, api, static_url, state)
        return {}
    kind, base, target = state.split(":", 2)
    goto_state(page, api, static_url, base)
    if kind == "focus":
        reached, tabs, label = focus_by_tab(page, target)
        return {"kind": kind, "base": base, "target": target, "reached": reached,
                "tabs": tabs, "active": label}
    if kind == "hover":
        reached, note = hover_target(page, target)
        return {"kind": kind, "base": base, "target": target, "reached": reached,
                "note": note}
    raise ValueError(state)


def capture_side(browser, static_url, width_heights_states):
    """按 (宽度, 高度) 复用页面：同一视口只建一次 context，状态间用 goto 复位。

    返回 {(width, height, state): {"fp": [[label, hash], ...], "rules": [str, ...],
    "interaction": {...}}}；打印进度便于观察（不静默）。
    """
    result = {}
    by_viewport = {}
    for width, height, state in width_heights_states:
        by_viewport.setdefault((width, height), []).append(state)
    for (width, height) in sorted(by_viewport):
        context = browser.new_context(viewport={"width": width, "height": height},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        for state in by_viewport[(width, height)]:
            page.goto(static_url)
            page.wait_for_selector(".run-item", timeout=10000)
            interaction = apply_state(page, api, static_url, state)
            settle(page)
            result[(width, height, state)] = {
                "fp": page.evaluate(_JS_FINGERPRINT),
                "rules": js_rules(page),
                "interaction": interaction,
            }
        page.close()
        context.close()
        print("  captured %dx%d states=%s" % (width, height,
                                              ",".join(by_viewport[(width, height)])),
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
        sweep = [(width, SWEEP_HEIGHT, state) for width in VIEWPORTS for state in SWEEP_STATES]
        sweep += [(width, SWEEP_HEIGHT, "agent") for width in NARROW_AGENT]
        sweep += [(width, SWEEP_HEIGHT, "legacy") for width in VIEWPORTS if width in
                  {w for w, _h in MAIN_VIEWPORTS}]
    interaction_states = ["focus:%s:%s" % (base, target)
                          for base in FOCUS_STATES for target in FOCUS_TARGETS]
    interaction_states += ["hover:%s:%s" % (base, target)
                           for base, target in HOVER_TARGETS]
    main_pairs = [(width, height, state) for (width, height) in MAIN_VIEWPORTS
                  for state in list(MAIN_STATES) + interaction_states]
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
                before_cap = capture_side(browser, before_url, pairs)
                after_cap = capture_side(browser, after_url, pairs)
            finally:
                browser.close()
    finally:
        for server, thread in ((before_server, before_thread), (after_server, after_thread)):
            server.shutdown()
            server.server_close()
            thread.join()

    diffs = []
    rules_mismatch = 0
    interaction_unreached = []
    for pair in pairs:
        b = before_cap[pair]
        a = after_cap[pair]
        bfp = [item[1] for item in b["fp"]]
        afp = [item[1] for item in a["fp"]]
        entry = {"width": pair[0], "height": pair[1], "state": pair[2], "kinds": []}
        if bfp != afp:
            changed = [(index, b["fp"][index][0] if index < len(b["fp"]) else "?")
                       for index in range(min(len(afp), len(bfp)))
                       if bfp[index] != afp[index]]
            entry.update({"before_elements": len(bfp), "after_elements": len(afp),
                          "changed_count": len(changed), "changed": changed[:20]})
            entry["kinds"].append("style")
        if b["rules"] != a["rules"]:
            rules_mismatch += 1
            first = next((index for index in range(min(len(b["rules"]), len(a["rules"])))
                          if b["rules"][index] != a["rules"][index]), None)
            entry.update({
                "before_rules": len(b["rules"]), "after_rules": len(a["rules"]),
                "first_rule_diff": first,
                "rule_before": b["rules"][first] if first is not None
                and first < len(b["rules"]) else None,
                "rule_after": a["rules"][first] if first is not None
                and first < len(a["rules"]) else None,
            })
            entry["kinds"].append("ruleset")
        for side, cap in (("before", b), ("after", a)):
            info = cap.get("interaction") or {}
            if info and not info.get("reached"):
                # 交互目标没落到：两侧都落不到 = 该状态无判别力（如实登记）；
                # 只有一侧落不到 = 交互可达性变了，判 DIFF。
                other = a if side == "before" else b
                other_info = other.get("interaction") or {}
                if other_info.get("reached"):
                    entry.setdefault("unreached", []).append(
                        {"side": side, "info": info})
                    entry["kinds"].append("interaction-unreached")
                else:
                    interaction_unreached.append(
                        {"width": pair[0], "height": pair[1], "state": pair[2],
                         "info": info})
        if entry["kinds"]:
            diffs.append(entry)
    report = {
        "before_web": str(before), "after_web": str(after),
        "combinations": len(pairs), "diff_combinations": len(diffs), "diffs": diffs,
        "states": list(MAIN_STATES), "interaction_states": interaction_states,
        "main_viewports": [list(v) for v in MAIN_VIEWPORTS],
        "sweep_widths": len(VIEWPORTS), "sweep_height": SWEEP_HEIGHT,
        "ruleset_mismatch_combinations": rules_mismatch,
        "ruleset_compared_combinations": len(pairs),
        "interaction_unreached_both_sides": interaction_unreached[:40],
        "interaction_unreached_total": len(interaction_unreached),
        # 冻结版遗留字段：未启用（transition-*/animation-* 的计算值本身已在指纹 PROPS 内
        # 逐元素比对，故此处恒为空，不代表「单独对账过」）。
        "transition_declaration_diffs": {},
    }
    print(json.dumps(report, ensure_ascii=False))
    if diffs:
        for item in diffs:
            detail = []
            if "style" in item["kinds"]:
                detail.append("%d 个元素计算样式变化 → %s" % (
                    item.get("changed_count", 0),
                    ", ".join("%d:%s" % (index, label)
                              for index, label in item.get("changed", [])[:6])))
            if "ruleset" in item["kinds"]:
                detail.append("规则序列不一致（before %s 条 / after %s 条；首个差异 #%s："
                              "before=%r after=%r）" % (
                                  item.get("before_rules"), item.get("after_rules"),
                                  item.get("first_rule_diff"), item.get("rule_before"),
                                  item.get("rule_after")))
            if "interaction-unreached" in item["kinds"]:
                detail.append("交互态可达性变化：%s" % item.get("unreached"))
            print("DIFF %s @ %dx%d：%s" % (
                item["state"], item["width"], item["height"], "；".join(detail)))
        print("DIFF: %d 个（宽度, 高度, 状态）组合不一致" % len(diffs))
        return 1
    print("PASS: 所有 %d 个（宽度, 高度, 状态）组合一致 —— 计算样式指纹（含 transition-*/"
          "animation-* 真实值，无限动画停在 0 时刻、::before/::after）、样式表规则序列"
          "（%d 组合对账：总条数与逐条 selectorText+声明数）与交互态可达性。"
          % (len(pairs), len(pairs)))
    if interaction_unreached:
        print("注意：%d 个交互态两侧都没落到目标（无判别力，已列入 JSON 的 "
              "interaction_unreached_both_sides）" % len(interaction_unreached))
    return 0


if __name__ == "__main__":
    sys.exit(main())
