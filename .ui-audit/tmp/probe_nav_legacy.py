"""E 复核：<nav> 包裹对 .seg 几何的影响 + legacy skip-link/焦点环是否真的可用。只读。"""
from __future__ import annotations
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[2] / "loop" / "tests" / "browser"
sys.path.insert(0, str(B))
from test_run_sessions import pw, static_url, ui  # noqa

def test_nav_wrapper_geometry(ui):
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    before = page.evaluate("""() => {
      const seg = document.querySelector('#viewSeg'), nav = seg.parentElement;
      const r = seg.getBoundingClientRect(), rn = nav.getBoundingClientRect();
      return {tag: nav.tagName, segW: Math.round(r.width), navW: Math.round(rn.width),
              segDisplay: getComputedStyle(seg).display, navDisplay: getComputedStyle(nav).display,
              asideW: Math.round(document.querySelector('aside').getBoundingClientRect().width)};
    }""")
    print("\n[nav] 有 <nav> 包裹:", before)
    after = page.evaluate("""() => {
      const seg = document.querySelector('#viewSeg'), nav = seg.parentElement;
      const parent = nav.parentElement;
      parent.replaceChild(seg, nav);            // 仅内存里解除包裹，模拟改动前结构
      const r = seg.getBoundingClientRect(), rp = parent.getBoundingClientRect();
      return {segW: Math.round(r.width), parentW: Math.round(rp.width),
              segDisplay: getComputedStyle(seg).display, asideW: Math.round(parent.getBoundingClientRect().width)};
    }""")
    print("[nav] 解除包裹（改动前等价）:", after)
    print("[nav] ⇒ seg 宽度变化 %d → %d px" % (before["segW"], after["segW"]))
    # 视图编号/页标题/用途描述（§14 框架条）在三视口是否仍在
    for w, h in [(1280, 720), (1440, 900), (1920, 1080)]:
        page.goto(page.url)
        page.set_viewport_size({"width": w, "height": h})
        page.wait_for_timeout(60)
        got = page.evaluate("""() => {
          const h1 = document.querySelector('#pageTitle'), sub = document.querySelector('#pageSub'),
                ed = document.querySelector('.page-edition'), idx = document.querySelector('#pageIndex');
          const vis = (e) => e ? getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().height > 0 : false;
          return {h1: h1 && h1.textContent.trim(), h1Visible: vis(h1),
                  sub: sub && sub.textContent.trim(), subVisible: vis(sub),
                  editionVisible: vis(ed), viewIndex: idx && idx.textContent.trim()};
        }""")
        print(f"[§14 框架] {w}x{h}:", got)

def test_legacy_skip_link_and_focus(ui, static_url):
    page, _api = ui
    page.goto(static_url + "/legacy.html")
    page.wait_for_timeout(300)
    print("\n[legacy] url =", page.url)
    first = page.evaluate("""() => {const a=document.activeElement; return a && (a.className||a.tagName);}""")
    page.keyboard.press("Tab")
    f1 = page.evaluate("""() => {const a=document.activeElement; return {cls: a.className, text: a.textContent.trim(),
       outline: getComputedStyle(a).outlineStyle + ' ' + getComputedStyle(a).outlineWidth,
       top: Math.round(a.getBoundingClientRect().top)};}""")
    print("[legacy] 加载后焦点 =", first, "| 首个 Tab =", f1)
    page.keyboard.press("Enter")
    page.wait_for_timeout(120)
    st = page.evaluate("""() => {
      const m = document.querySelector('#legacyMain'), a = document.activeElement;
      const cs = getComputedStyle(m);
      return {activeIsMain: a === m, active: a && (a.id || a.tagName),
              tabindex: m.getAttribute('tabindex'),
              outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth,
              outlineColor: cs.outlineColor, scrollY: Math.round(scrollY)};
    }""")
    print("[legacy] Enter 后:", st)
