"""E 复核：计划 §3.2 改过对比度、但新用例探针清单**没覆盖**的 selector 实测比值。只读。"""
from __future__ import annotations
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[2] / "loop" / "tests" / "browser"
sys.path.insert(0, str(B))
from test_run_sessions import pw, static_url, ui  # noqa
from test_web_layout import populate  # noqa

JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return {sel, missing: true};
  const parse = (s) => { const m = String(s).match(/rgba?\\(([^)]+)\\)/); if(!m) return null;
    const p = m[1].split(',').map(Number); return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}; };
  const lum = (c) => { const f=(v)=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
    return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };
  let bg=null, node=el;
  while (node && node.nodeType===1) { const c=parse(getComputedStyle(node).backgroundColor);
    if (c && c.a>=0.999) { bg=c; break; } node=node.parentElement; }
  if (!bg) bg={r:255,g:255,b:255};
  const cs=getComputedStyle(el), fg=parse(cs.color);
  const L1=lum(fg), L2=lum(bg);
  return {sel, fg: cs.color, bg:`rgb(${bg.r},${bg.g},${bg.b})`, fontSize: cs.fontSize,
          ratio: Math.round(((Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05))*100)/100};
}
"""
UNPROBED = [".s0-blockers .eyebrow", ".s0-blockers h3", ".phase-index", ".s0-checks b",
            ".s0-scope", ".s0-boundary", ".stage-idx", ".receipt-label", ".agent-role",
            ".hb-code", ".nd-hb-code", ".a3", ".a4", ".a5", ".a6", ".option.on .radio"]

def test_unprobed_selectors(ui):
    page, api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    populate(api)
    page.locator(".run-item").first.click()
    page.wait_for_timeout(200)
    print("\n--- 当前 DOM 中存在 / 缺失 ---")
    for sel in UNPROBED:
        if page.locator(sel).count() == 0:
            print(f"[未覆盖] {sel:22s} 当前视图不可见/不存在（S0+gate 视图采样不到）")
        else:
            print(f"[未覆盖] {sel:22s}", page.evaluate(JS, sel))
