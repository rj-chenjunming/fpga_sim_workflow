"""E 复核：对新用例判据做「判别性」只读实验（复制探针，不改原测试）。

运行（repo 根）：
  PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
  loop/.venv/bin/python -m pytest -q .ui-audit/tmp/test_probe_discrimination.py -s
"""
from __future__ import annotations

import sys
from pathlib import Path

BROWSER = Path(__file__).resolve().parents[2] / "loop" / "tests" / "browser"
sys.path.insert(0, str(BROWSER))

import pytest  # noqa: E402

from test_run_sessions import pw, static_url, ui  # noqa: E402,F401
from test_web_layout import populate  # noqa: E402,F401


# ---- 原用例判据（逐字复制，仅用于对照） ----
def _in_first_screen(page, selector, height):
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box["y"] >= 0 and box["y"] + box["height"] <= height + 1


_CONTRAST_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return {error: 'missing', selector: sel};
  const parse = (s) => {
    const m = String(s).match(/rgba?\\(([^)]+)\\)/);
    if (!m) return null;
    const p = m[1].split(',').map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  let bg = null;
  let node = el;
  while (node && node.nodeType === 1) {
    const c = parse(getComputedStyle(node).backgroundColor);
    if (c && c.a >= 0.999) { bg = c; break; }
    node = node.parentElement;
  }
  if (!bg) bg = parse(getComputedStyle(document.body).backgroundColor) || {r: 255, g: 255, b: 255};
  const cs = getComputedStyle(el);
  const fg = parse(cs.color);
  const L1 = lum(fg), L2 = lum(bg);
  const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
  return {selector: sel, fg: cs.color, bg: 'rgb(' + bg.r + ',' + bg.g + ',' + bg.b + ')',
          ratio: Math.round(ratio * 100) / 100, fontSize: cs.fontSize};
}
"""


def test_A_scroll_position_drives_fold_criterion(ui):
    """Q1：bounding_box() 是**视口坐标**。把页面滚到 1280×720 下原判据「首屏外」的位置，
    同一判据立刻变成通过 ⇒ 判据本身不含 scrollY==0 前提，若页面被任何东西滚动过就会假绿。"""
    page, _api = ui
    page.set_viewport_size({"width": 1280, "height": 720})
    page.wait_for_timeout(120)
    natural = page.evaluate("() => ({y: scrollY, h: innerHeight})")
    raw = page.evaluate("""() => {
      const b = document.querySelector('#s0Prepare').getBoundingClientRect();
      return {y: b.y, bottom: b.bottom, scrollY: scrollY, docY: b.y + scrollY};
    }""")
    print("\n[A] 自然加载 scrollY =", natural["y"], " #s0Prepare 视口 y =", raw["y"],
          "文档 y =", raw["docY"])

    # 用 1024×600 制造「必须滚动才可见」，再滚到目标可见：判据通过。
    page.set_viewport_size({"width": 1280, "height": 420})
    page.wait_for_timeout(120)
    before = _in_first_screen(page, "#s0Prepare", 420)
    page.evaluate("() => document.querySelector('#s0Prepare').scrollIntoView({block:'center'})")
    page.wait_for_timeout(80)
    after = _in_first_screen(page, "#s0Prepare", 420)
    print("[A] 1280x420 未滚动判据 =", before, "| scrollIntoView 后同一判据 =", after,
          "scrollY =", page.evaluate("() => scrollY"))
    page.set_viewport_size({"width": 1280, "height": 720})
    page.wait_for_timeout(80)
    assert after is True, "滚动后判据仍应通过（证明判据跟随视口而非文档）"
    # 真实门（scrollY==0）在原用例里没有被断言
    print("[A] 原用例未断言 scrollY==0；自然加载 scrollY =", natural["y"])


def test_B_contrast_probe_ignores_translucent_layers(ui):
    """Q2：探针只接受 alpha>=0.999 的背景，半透明层被**跳过**（不是合成）。
    在浅色祖先上放一层深色半透明底 + 低对比文字，探针给出「合祖先」的高比值 ⇒ 假绿。"""
    page, _api = ui
    page.evaluate("""() => {
      const host = document.createElement('div');
      host.id = 'probeHost';
      host.style.cssText = 'background:#ffffff;padding:8px';
      const inner = document.createElement('div');
      inner.id = 'probeInner';
      inner.style.cssText = 'background:rgba(0,0,0,0.65);color:#7a7a7a;font-size:13px;padding:6px';
      inner.textContent = '低对比文字';
      host.appendChild(inner);
      document.querySelector('main').appendChild(host);
    }""")
    out = page.evaluate(_CONTRAST_JS, "#probeInner")
    # 眼睛看到的底色 = 0.65 黑 + 0.35 白 ≈ rgb(89,89,89)；文字 #7a7a7a ⇒ 真实比值 ≈ 1.35
    true_ratio = page.evaluate("""() => {
      const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
      const lum = (r, g, b) => 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
      const L1 = lum(0x7a, 0x7a, 0x7a);
      const L2 = lum(0.35 * 255, 0.35 * 255, 0.35 * 255);
      return Math.round(((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)) * 100) / 100;
    }""")
    print("\n[B] 探针 bg =", out["bg"], "探针 ratio =", out["ratio"], "| 真实合成后 ratio =", true_ratio)
    assert out["ratio"] > 4.5 and true_ratio < 2.0, (out, true_ratio)
    print("[B] ⇒ 探针把半透明层当不存在（跳过而非合成）；本次 S0 探针清单实测背景层级全为不透明，暂未触发")


def test_C_focus_ring_tab_path_is_fragile(ui):
    """Q3：焦点环用例依赖「20 次 Tab 内到达 #btnS0」。实测真实 Tab 序号与是否依赖初始焦点。"""
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(120)
    # 原用例：先 .focus() #s0Rtl，再 document.body.focus()（body 不可聚焦 ⇒ 实测是否生效）
    page.locator("#s0Rtl").focus()
    before = page.evaluate("() => document.activeElement.id")
    page.evaluate("() => document.body.focus()")
    after = page.evaluate("() => document.activeElement.id")
    print("\n[C] #s0Rtl.focus() 后 activeElement =", before, "| body.focus() 后 =", after)
    seq = []
    hit = None
    for i in range(40):
        page.keyboard.press("Tab")
        cur = page.evaluate("""() => {const a = document.activeElement;
          return (a.id || a.className || a.tagName).toString().slice(0, 28);}""")
        seq.append(cur)
        if cur == "btnS0":
            hit = i + 1
            break
    print("[C] 从 #s0Rtl 焦点出发的 Tab 序列（前 40）:", seq)
    print("[C] 到达 #btnS0 需 Tab 次数 =", hit, "（原用例上限 20）")
    # 反向：从文档起点开始
    page.reload()
    page.wait_for_timeout(200)
    seq2 = []
    hit2 = None
    for i in range(40):
        page.keyboard.press("Tab")
        cur = page.evaluate("""() => {const a = document.activeElement;
          return (a.id || a.className || a.tagName).toString().slice(0, 28);}""")
        seq2.append(cur)
        if cur == "btnS0":
            hit2 = i + 1
            break
    print("[C] 从文档起点出发 Tab 序列（前 40）:", seq2)
    print("[C] 从起点到达 #btnS0 需 Tab 次数 =", hit2)
    assert hit is not None


def test_D_scale_progress_transform(ui):
    """Q4：--p（scaleX）在 0% / 33% / 100% 的渲染几何；对照旧 width 写法的等价性。"""
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    out = page.evaluate("""() => {
      const bar = document.createElement('div'); bar.className = 'stage-bar';
      bar.style.width = '300px';
      const rows = [];
      for (const p of [0, 0.33, 0.5, 1]) {
        const i = document.createElement('i');
        i.style.setProperty('--p', String(p));
        bar.innerHTML = ''; bar.appendChild(i); document.body.appendChild(bar);
        const cs = getComputedStyle(i), r = i.getBoundingClientRect();
        rows.push({p, declaredWidth: cs.width, transform: cs.transform,
                   renderedW: Math.round(r.width * 10) / 10});
        bar.removeChild(i);
      }
      bar.remove();
      return rows;
    }""")
    for r in out:
        print("\n[D]", r)
    # 0 宽度 ⇒ 不可见；1.0 ⇒ 满宽；0.33 ⇒ 1/3 宽
    assert out[0]["renderedW"] == 0
    assert abs(out[-1]["renderedW"] - 300) < 1
    assert abs(out[1]["renderedW"] - 99) < 2
    print("[D] 0% 渲染 0 宽、100% 满宽、部分按比例 —— 几何正确（但 scaleX 会横向压扁右端圆角）")

    # app.js 写入源：确认只写 --p，不再写 width，且 ratio 有 clamp
    import inspect
    from pathlib import Path as P
    js = (P(__file__).resolve().parents[2] / "loop" / "web" / "app.js").read_text()
    assert "fill.style.width" not in js
    assert 'fill.style.setProperty("--p"' in js
    print("[D] app.js: fill.style.setProperty(\"--p\", ratio) 命中；无 fill.style.width")
