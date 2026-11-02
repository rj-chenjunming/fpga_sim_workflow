"""临时渲染核对（**不是**交付测试）：在 Lead 落地 `.icon` 规则之前，用注入样式验证
41 处 `<use>` 图标在 Chromium 里是否解析、尺寸/描边是否正常，并留一张目检截图。

为什么需要：`app.css` 的 `.icon` 是硬依赖（我没有 `app.css` 写权）。本脚本注入与
`.ui-audit/4b/app-css-requests.md` §1/§2 完全一致的规则，用来把「实现不对」与
「样式还没落地」两种失败分开。正式截图在 Lead 落地后重拍。

用法（在 loop/ 下）：
  PLAYWRIGHT_BROWSERS_PATH=../.pw-browsers HOME=../.chrome-home TMPDIR=../.chrome-tmp \
  .venv/bin/python -m pytest -q ../.ui-audit/4b/scratch/verify_render.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[3] / "loop"
sys.path.insert(0, str(LOOP / "tests"))
sys.path.insert(0, str(LOOP / "tests" / "browser"))

from test_run_sessions import pw, static_url, ui  # noqa: F401,E402
from test_web_layout import populate  # noqa: F401,E402

SHOTS = Path(__file__).resolve().parents[1] / "shots"

#: 与 app-css-requests.md §1/§2 逐字一致（Lead 落地后本注入即冗余）。
INJECT = """
.icon{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:-3px;
  fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.icon-30{width:30px;height:30px;vertical-align:baseline}
.empty .icon-30{display:block;width:58px;height:58px;padding:13px;box-sizing:border-box;
  margin:0 auto 20px;border:1px solid #d6e3d8;border-radius:16px;background:#f0f6f1;color:#60846a}
.empty:before{content:none}
"""

_PROBE = """
() => {
  const icons = [...document.querySelectorAll('svg.icon')];
  const rows = icons.map((el, i) => {
    const use = el.querySelector('use');
    const box = el.getBoundingClientRect();
    let bbox = null;
    try { const b = use.getBBox(); bbox = [Math.round(b.width * 10) / 10, Math.round(b.height * 10) / 10]; }
    catch (e) { bbox = 'err'; }
    const cs = getComputedStyle(el);
    return {
      i, href: use ? use.getAttribute('href') : null,
      w: Math.round(box.width), h: Math.round(box.height),
      visible: box.width > 0 && box.height > 0,
      bbox, fill: cs.fill, stroke: cs.stroke, sw: cs.strokeWidth,
    };
  });
  return {
    total: icons.length,
    sprites: document.querySelectorAll('#iconSprite symbol').length,
    rows,
  };
}
"""


def _inject(page):
    page.add_style_tag(content=INJECT)


def _check(page, label):
    data = page.evaluate(_PROBE)
    rows = data["rows"]
    visible = [r for r in rows if r["visible"]]
    print(f"[probe:{label}] total={data['total']} symbols={data['sprites']} visible={len(visible)}")
    for r in visible:
        print("   ", r)
    assert data["sprites"] == 18, data
    assert visible, f"{label}: 没有可见图标"
    bad_size = [r for r in visible if (r["w"], r["h"]) not in ((16, 16), (19, 16), (18, 16))]
    assert not bad_size, f"{label} 尺寸异常：{bad_size}"
    bad_bbox = [r for r in visible if r["bbox"] == "err" or not r["bbox"] or min(r["bbox"]) <= 0]
    assert not bad_bbox, f"{label} <use> 未解析出内容（空框）：{bad_bbox}"
    bad_stroke = [r for r in visible if r["fill"] != "none" or r["sw"] != "1.5px"]
    assert not bad_stroke, f"{label} 描边口径异常：{bad_stroke}"
    return data


def test_icons_resolve_and_are_16px(ui):
    page, api = ui
    _inject(page)
    page.set_viewport_size({"width": 1440, "height": 900})
    populate(api)
    SHOTS.mkdir(parents=True, exist_ok=True)

    # 1) 环境准备视图（静态 + 动态图标）
    _check(page, "s0")
    page.screenshot(path=str(SHOTS / "prelim-s0-1440.png"), full_page=False)

    # 2) 运行视图的**空态**（未选运行）：内联 icon-empty 走 .icon-30 + 58×58 框
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()
    empty = page.evaluate("""() => {
      const box = document.getElementById('runEmpty');
      const svg = box ? box.querySelector('svg.icon') : null;
      const b = svg ? svg.getBoundingClientRect() : null;
      const cs = svg ? getComputedStyle(svg) : null;
      return {present: !!svg, count: box ? box.querySelectorAll('svg.icon').length : 0,
              w: b ? Math.round(b.width) : 0, h: b ? Math.round(b.height) : 0,
              pad: cs ? cs.paddingTop : null};
    }""")
    print("[probe] 空态图标:", empty)
    assert empty["present"] and empty["count"] == 1, empty
    assert (empty["w"], empty["h"]) == (58, 58), empty  # 与原 .empty:before 外框一致
    page.screenshot(path=str(SHOTS / "prelim-empty-1440.png"), full_page=False)

    # 3) 运行视图（阶段/节点状态泡/agent 卡）
    page.locator(".run-item").first.click()
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()
    _check(page, "run")
    page.screenshot(path=str(SHOTS / "prelim-run-1440.png"), full_page=False)

    # 4) 闸门视图（紧凑卡 → 逐条处置按钮）
    page.locator("#segGate").click()
    pw.expect(page.locator("#viewGate")).to_be_visible()
    _check(page, "gate")

    # 5) 节点详情 / Agent 窗口（node-detail.js 的 5 处动作按钮图标）
    page.locator("#segRun").click()
    page.locator(".snode").first.click()
    page.wait_for_timeout(300)
    dialog = page.evaluate("""() => {
      const node = document.getElementById('nodeDetail');
      const aw = document.getElementById('agentWindow');
      const scope = (node && node.open) ? node : ((aw && aw.classList.contains('open')) ? aw : null);
      if (!scope) return {scope: null, awOpen: aw ? aw.className : null, nodeOpen: node ? node.open : null};
      const icons = [...scope.querySelectorAll('svg.icon')];
      return {scope: scope.id, icons: icons.map(el => {
        const b = el.getBoundingClientRect();
        return {href: el.querySelector('use').getAttribute('href'),
                w: Math.round(b.width), h: Math.round(b.height)};
      })};
    }""")
    print("[probe] 弹层图标:", dialog)
    if dialog["scope"]:
        assert dialog["icons"], f"{dialog['scope']} 里没有图标"
        visible = [row for row in dialog["icons"] if row["w"] > 0]
        print("[probe] 弹层可见图标:", visible)
        assert visible, f"{dialog['scope']} 里没有可见图标"
        for row in visible:
            assert (row["w"], row["h"]) in ((16, 16), (19, 16)), row
        page.screenshot(path=str(SHOTS / "prelim-dialog-1440.png"), full_page=False)


_GEOM = """
() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return {w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10};
  };
  return {
    segS0: box('#segS0'), railEntry: box('#btnS0'),
    navIcon: box('#segS0 .nav-icon'), navSvg: box('#segS0 .nav-icon svg'),
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
    hOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  };
}
"""


@pytest.mark.parametrize("width,height", [(1280, 720), (1440, 900), (1920, 1080)])
def test_sidebar_geometry_unchanged(ui, width, height):
    """A10 输入：`.seg button` 44 高 / `.rail-entry` 64 高 / 无水平溢出（图标替换后不回退）。"""
    page, api = ui
    _inject(page)
    page.set_viewport_size({"width": width, "height": height})
    populate(api)
    got = page.evaluate(_GEOM)
    print(f"[geom {width}x{height}]", got)
    assert got["segS0"]["h"] == 44, got
    assert got["segS0"]["w"] == 216, got
    assert got["railEntry"]["h"] == 64, got
    assert (got["navIcon"]["w"], got["navIcon"]["h"]) == (19, 16), got
    assert (got["navSvg"]["w"], got["navSvg"]["h"]) == (16, 16), got
    assert not got["hOverflow"], got
