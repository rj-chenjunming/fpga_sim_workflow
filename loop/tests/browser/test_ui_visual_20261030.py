"""UI 视觉优化（2026-10-30）验收：首屏 / 对比度 / 焦点 / 动效 / 结构。

判据来源：`doc/spec/WEB_UI_SPEC.md` §10 A12、A13 与 §14「2026-10-30 增补」；
计划：[`doc/plans/2026-10-30-ui-visual-optimization.md`](../../../doc/plans/2026-10-30-ui-visual-optimization.md)。
只消费真实静态页 + 既有受控 API 替身（`test_run_sessions.ui`），不模拟业务判据。

先按本文件判红、再实现，是本轮 SpecDD 的先失败用例（AGENTS §2.1 第 3 条）。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_run_sessions import pw, static_url, ui  # noqa: F401
from test_web_layout import populate  # noqa: F401  （受控夹具：让闸门材料有真实高度）

WEB = Path(__file__).resolve().parents[2] / "web"
VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]

#: 对比度探针：取首个不透明背景祖先，用 WCAG 相对亮度算比值。
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
  return {
    selector: sel,
    fg: cs.color,
    bg: 'rgb(' + bg.r + ',' + bg.g + ',' + bg.b + ')',
    ratio: Math.round(ratio * 100) / 100,
    fontSize: cs.fontSize,
  };
}
"""


def _ratio(page, selector):
    out = page.evaluate(_CONTRAST_JS, selector)
    assert "error" not in out, out
    return out


def _outline_ratio(page, selector):
    """焦点元素 outline 颜色对「元素首个不透明背景」的对比度。"""
    out = page.evaluate(
        """(sel) => {
      const el = document.querySelector(sel);
      if (!el) return {error: 'missing', selector: sel};
      const cs = getComputedStyle(el);
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
      let bg = null, node = el;
      while (node && node.nodeType === 1) {
        const c = parse(getComputedStyle(node).backgroundColor);
        if (c && c.a >= 0.999) { bg = c; break; }
        node = node.parentElement;
      }
      if (!bg) bg = {r: 255, g: 255, b: 255};
      const ring = parse(cs.outlineColor) || {r: 0, g: 0, b: 0};
      const L1 = lum(ring), L2 = lum(bg);
      const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
      return {selector: sel, ring: cs.outlineColor, style: cs.outlineStyle,
              width: cs.outlineWidth, bg: 'rgb(' + bg.r + ',' + bg.g + ',' + bg.b + ')',
              ratio: Math.round(ratio * 100) / 100};
    }""",
        selector,
    )
    assert "error" not in out, out
    return out


def _focus_by_tab(page, selector, max_tabs=20):
    """按真实键盘路径把焦点移到目标（`:focus-visible` 只对键盘焦点可靠）。"""
    page.evaluate("() => document.body.focus()")
    for _ in range(max_tabs):
        page.keyboard.press("Tab")
        if page.evaluate("(sel) => document.activeElement && document.activeElement.matches(sel)", selector):
            return True
    return False


def _in_first_screen(page, selector, height):
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box["y"] >= 0 and box["y"] + box["height"] <= height + 1


# ---------------------------------------------------------------- A12 首屏

@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_s0_required_field_and_primary_action_are_in_first_screen(ui, width, height):
    page, _api = ui
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("() => scrollTo(0, 0)")
    assert page.evaluate("() => scrollY") == 0, "首屏判据必须在未滚动状态下成立"
    assert _in_first_screen(page, "#s0Rtl", height), "唯一必填项不在首屏"
    assert _in_first_screen(page, "#s0Prepare", height), "主操作不在首屏"
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_gate_material_enters_first_screen_at_1440(ui):
    page, api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    populate(api)
    page.locator(".run-item").first.click()
    pw.expect(page.locator("#viewGate")).to_be_visible()
    box = page.locator("#gateMaterial").bounding_box()
    assert box is not None
    assert box["y"] < 900, f"闸门材料顶边 y={box['y']} 未进入首屏"
    # 两栏都必须在首屏起点，且页面无水平溢出
    assert page.locator("#gatePanel").bounding_box()["y"] < 900
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


# ---------------------------------------------------------------- A13 对比度

def test_informational_text_meets_aa(ui):
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    probes = [
        ".page-edition",
        ".phase-card p",
        ".phase-index",
        ".section-index",
        "#s0Checks li span",
        "#s0Blockers p",
        ".s0-blockers .eyebrow",
        ".s0-blockers h3",
        ".foot-note" if page.locator(".foot-note").count() else "#pageSub",
        ".rail-foot",
    ]
    low = []
    for sel in probes:
        if page.locator(sel).count() == 0:
            continue
        got = _ratio(page, sel)
        if got["ratio"] < 4.5:
            low.append(got)
    assert not low, low


def test_placeholder_text_meets_aa(ui):
    page, _api = ui
    got = page.evaluate(
        """() => {
      const el = document.querySelector('#s0Rtl');
      const color = getComputedStyle(el, '::placeholder').color;
      const bg = getComputedStyle(el).backgroundColor;
      const parse = (s) => { const m = String(s).match(/rgba?\\(([^)]+)\\)/); const p = m[1].split(',').map(Number);
        return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
      const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
        return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
      const fg = parse(color), b = parse(bg);
      const L1 = lum(fg), L2 = lum(b);
      return {color, bg, ratio: Math.round(((Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)) * 100) / 100};
    }"""
    )
    assert got["ratio"] >= 4.5, got


def test_run_view_informational_text_meets_aa(ui):
    """计划 §3.2 改过的 run 侧规则也要有回归探针（`.stage-idx`/`.agent-role`/头像首字母）。"""
    page, api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    populate(api)
    page.locator(".run-item").first.click()
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()
    probes = [".stage-idx", ".agent-role", ".avatar.a3", ".avatar.a4", ".avatar.a5",
              ".agent-foot", ".run-meta"]
    low = []
    for sel in probes:
        if page.locator(sel).count() == 0:
            continue
        got = _ratio(page, sel)
        if got["ratio"] < 4.5:
            low.append(got)
    assert not low, low


def test_focus_ring_contrast(ui):
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator("#s0Rtl").focus()
    ring = _outline_ratio(page, "#s0Rtl")
    assert ring["style"] != "none" and float(ring["width"].rstrip("px")) > 0, ring
    assert ring["ratio"] >= 3, ring

    assert _focus_by_tab(page, "#btnS0"), "键盘无法到达侧栏入口"
    ring = _outline_ratio(page, "#btnS0")
    assert ring["style"] != "none" and float(ring["width"].rstrip("px")) > 0, ring
    assert ring["ratio"] >= 3, ring


def test_skip_link_target_has_visible_focus(ui):
    page, _api = ui
    page.keyboard.press("Tab")
    pw.expect(page.locator(".skip-link")).to_be_focused()
    page.keyboard.press("Enter")
    state = page.evaluate(
        """() => {
      const el = document.querySelector('main');
      const cs = getComputedStyle(el);
      return {active: document.activeElement === el, style: cs.outlineStyle, width: cs.outlineWidth};
    }"""
    )
    assert state["active"], state
    assert state["style"] != "none" and float(state["width"].rstrip("px")) > 0, state


# ---------------------------------------------------------------- A13 动效与令牌契约

def test_tokens_and_motion_contract():
    tokens = (WEB / "tokens.css").read_text()
    css = (WEB / "app.css").read_text()
    assert "Inter" not in tokens, "不得声明未内置的 Inter"
    assert re.search(r"cubic-bezier\(\s*0\.22\s*,\s*1\s*,\s*0\.36\s*,\s*1\s*\)", tokens + css)
    assert "--ease-out" in tokens
    offenders = re.findall(r"transition\s*:\s*[^;{}]*\b(?:width|height)\b", css)
    assert not offenders, offenders
    longhand = re.findall(r"transition-property\s*:\s*[^;{}]*\b(?:width|height)\b", css)
    assert not longhand, longhand
    keyframes = re.findall(r"@keyframes[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", css)
    animated = [k for k in keyframes
                if re.search(r"\b(?:box-shadow|width|height|top|left|right|bottom)\s*:", k)]
    assert not animated, animated
    assert ":active" in css
    assert "text-wrap" in css
    assert "@font-face" not in tokens + css
    assert "url(" not in tokens + css


def test_stage_progress_animates_transform_not_width():
    js = (WEB / "app.js").read_text()
    assert "fill.style.width" not in js
    assert "--p" in js
    assert 'label: "进行中"' not in js
    assert 'working: "工作中"' not in js


# ---------------------------------------------------------------- 结构

def test_landing_hero_removed_nav_favicon_and_skeleton_present(ui):
    page, _api = ui
    assert page.evaluate("() => document.querySelector('.s0-hero') === null")
    assert page.evaluate("() => document.querySelectorAll('nav').length >= 1")
    assert page.evaluate("() => !!document.querySelector('link[rel=\"icon\"]')")
    html = (WEB / "index.html").read_text()
    assert "sk-line" in html
    legacy = (WEB / "legacy.html").read_text()
    assert 'class="skip-link"' in legacy
    assert "legacyMain" in legacy
