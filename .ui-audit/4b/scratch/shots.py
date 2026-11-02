"""批次 4 · A 项三视口截图 + 几何/溢出读数（**在 Lead 落地 `app.css` 之后再跑**）。

不复用任何注入样式：只吃真实 `loop/web`（含 Lead 落的 `.icon`）。开头先断言 `.icon` 已生效，
避免在「样式还没落地」的状态下拍出一批误导性的截图。

用法（在 loop/ 下）：
  PLAYWRIGHT_BROWSERS_PATH=../.pw-browsers HOME=../.chrome-home TMPDIR=../.chrome-tmp \
  .venv/bin/python -m pytest -q ../.ui-audit/4b/scratch/shots.py -s
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[3] / "loop"
sys.path.insert(0, str(LOOP / "tests"))
sys.path.insert(0, str(LOOP / "tests" / "browser"))

from test_run_sessions import pw, static_url, ui  # noqa: F401,E402
from test_web_layout import populate  # noqa: F401,E402

OUT = Path(__file__).resolve().parents[1]
SHOTS = OUT / "shots"
VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]

_ICON_STYLE = """
() => {
  const el = document.querySelector('svg.icon');
  if (!el) return null;
  const cs = getComputedStyle(el);
  return {w: cs.width, h: cs.height, fill: cs.fill, stroke: cs.strokeWidth,
          hasSprite: !!document.getElementById('iconSprite')};
}
"""

_GEOM = """
() => {
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const b = el.getBoundingClientRect();
    return {w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10,
            y: Math.round(b.y * 10) / 10};
  };
  const segs = [...document.querySelectorAll('#viewSeg button')].map((el) => {
    const b = el.getBoundingClientRect();
    return {id: el.id, w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10};
  });
  return {
    segButtons: segs,
    segS0: box('#segS0'),
    railEntry: box('#btnS0'),
    navIcon: box('#segS0 .nav-icon'),
    navSvg: box('#segS0 .nav-icon svg'),
    gateMaterial: box('#gateMaterial'),
    gatePanel: box('#gatePanel'),
    gatePanes: [...document.querySelectorAll('.gate-pane')].map((el) => {
      const b = el.getBoundingClientRect();
      return {h: Math.round(b.height * 10) / 10, y: Math.round(b.y * 10) / 10,
              scrollH: el.scrollHeight, clientH: el.clientHeight};
    }),
    scrollW: document.documentElement.scrollWidth,
    clientW: document.documentElement.clientWidth,
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    emptyBeforeIcon: (() => {
      const el = document.getElementById('runEmpty');
      if (!el) return null;
      const pseudo = getComputedStyle(el.querySelector('.empty') || el, ':before');
      return {content: pseudo.content, icons: el.querySelectorAll('svg.icon').length};
    })(),
  };
}
"""


def test_capture_three_viewports(ui):
    page, api = ui
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    style = page.evaluate(_ICON_STYLE)
    print("\n[icon style]", style)
    assert style, "页面上找不到 svg.icon"
    assert style["hasSprite"], "#iconSprite 缺失"
    assert (style["w"], style["h"]) == ("16px", "16px"), f"app.css 的 .icon 未生效：{style}"
    assert style["fill"] == "none", f"app.css 的 .icon 未生效（fill）：{style}"

    # 空态机位（未选运行）：验证「只剩 1 个 58×58 插图、.empty:before 已删」
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()
    empty = page.evaluate("""() => {
      const box = document.getElementById('runEmpty');
      const inner = box ? box.querySelector('.empty') : null;
      const svg = box ? box.querySelector('svg.icon') : null;
      const b = svg ? svg.getBoundingClientRect() : null;
      const pseudo = inner ? getComputedStyle(inner, ':before') : null;
      return {icons: box ? box.querySelectorAll('svg.icon').length : -1,
              w: b ? Math.round(b.width) : 0, h: b ? Math.round(b.height) : 0,
              before: pseudo ? pseudo.content : null,
              beforeW: pseudo ? pseudo.width : null};
    }""")
    print("\n[empty state]", empty)
    page.screenshot(path=str(SHOTS / "final-empty-1440x900.png"))
    assert empty["icons"] == 1, empty
    assert (empty["w"], empty["h"]) == (58, 58), empty
    assert empty["before"] in ("none", "normal"), empty

    out: dict[str, object] = {"icon": style, "emptyState": empty, "viewports": {}}
    for width, height in VIEWPORTS:
        page.set_viewport_size({"width": width, "height": height})
        populate(api)
        page.locator("#segS0").click()
        pw.expect(page.locator("#viewS0")).to_be_visible()
        page.screenshot(path=str(SHOTS / f"s0-{width}x{height}.png"))
        geom_s0 = page.evaluate(_GEOM)

        page.locator(".run-item").first.click()
        page.locator("#segRun").click()
        pw.expect(page.locator("#viewRun")).to_be_visible()
        page.locator(".run-item").first.click()  # 再点一次：确保选中而不是被 gate 自动切走
        page.locator("#segRun").click()
        pw.expect(page.locator("#viewRun")).to_be_visible()
        page.screenshot(path=str(SHOTS / f"run-{width}x{height}.png"))
        geom_run = page.evaluate(_GEOM)

        page.locator("#segGate").click()
        pw.expect(page.locator("#viewGate")).to_be_visible()
        page.screenshot(path=str(SHOTS / f"gate-{width}x{height}.png"))
        geom_gate = page.evaluate(_GEOM)

        out["viewports"][f"{width}x{height}"] = {
            "s0": geom_s0, "run": geom_run, "gate": geom_gate}
        print(f"[gate {width}x{height}] materialY={geom_gate['gateMaterial']} "
              f"panes={geom_gate['gatePanes']}")
        print(f"\n[geom {width}x{height}] s0={geom_s0['navIcon']} rail={geom_s0['railEntry']} "
              f"overflowX={geom_s0['overflowX']} segs={[(s['id'], s['h']) for s in geom_s0['segButtons']]}")
        assert not geom_s0["overflowX"], f"{width}x{height} 页面水平溢出"
        assert all(abs(s["h"] - 44) <= 1 for s in geom_s0["segButtons"]), geom_s0["segButtons"]
        assert abs(geom_s0["railEntry"]["h"] - 64) <= 1, geom_s0["railEntry"]
        assert geom_s0["navIcon"]["w"] == 19, geom_s0["navIcon"]
        assert (geom_s0["navSvg"]["w"], geom_s0["navSvg"]["h"]) == (16, 16), geom_s0["navSvg"]

    # Agent 窗口（页内浮层：icon-panel / icon-close 的现场）
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()
    page.locator('#agents [data-agent-node="N3"]').click()
    pw.expect(page.locator("#agentWindow")).to_be_visible()
    page.wait_for_timeout(250)
    page.screenshot(path=str(SHOTS / "agent-window-1440x900.png"))
    aw_icons = page.evaluate("""() => [...document.querySelectorAll('#agentWindow svg.icon')]
      .map((el) => { const b = el.getBoundingClientRect();
                     return {href: el.querySelector('use').getAttribute('href'),
                             w: Math.round(b.width), h: Math.round(b.height)}; })""")
    print("\n[agent window icons]", aw_icons)
    out["agentWindowIcons"] = aw_icons

    # 节点详情弹层（node-detail.js 的关闭图标 + 5 处动作按钮图标）
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    page.locator(".snode").first.click()
    page.wait_for_timeout(400)
    node_open = page.evaluate("() => { const d = document.getElementById('nodeDetail'); return !!(d && d.open); }")
    print("\n[node detail open]", node_open)
    if node_open:
        page.screenshot(path=str(SHOTS / "final-node-detail-1440x900.png"))
        nd_icons = page.evaluate("""() => [...document.querySelectorAll('#nodeDetail svg.icon')]
          .map((el) => { const b = el.getBoundingClientRect();
                         return {href: el.querySelector('use').getAttribute('href'),
                                 w: Math.round(b.width), h: Math.round(b.height)}; })
          .filter((r) => r.w > 0)""")
        print("[node detail icons]", nd_icons)
        out["nodeDetailIcons"] = nd_icons

    (OUT / "measure-4b.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[done] 截图 + measure-4b.json 已写入", OUT)
