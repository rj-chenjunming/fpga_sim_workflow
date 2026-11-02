"""E 复核：对比度探针清单的背景链（区分 a=0 全透明 [跳过正确] 与 0<a<1 半透明 [跳过会算错]）。只读。"""
from __future__ import annotations
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[2] / "loop" / "tests" / "browser"
sys.path.insert(0, str(B))
from test_run_sessions import pw, static_url, ui  # noqa
from test_run_sessions import ui  # noqa
from test_web_layout import populate  # noqa

PROBES = [".page-edition", ".phase-card p", ".section-index", "#s0Checks li span",
          "#s0Blockers p", ".foot-note", "#pageSub", ".rail-foot"]

def test_bg_chain(ui):
    page, _api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    for sel in PROBES:
        if page.locator(sel).count() == 0:
            print(f"[bg] {sel:22s} count=0（原用例 continue）")
            continue
        out = page.evaluate("""(sel) => {
          const parse = (s) => { const m = String(s).match(/rgba?\\(([^)]+)\\)/); if(!m) return null;
            const p = m[1].split(',').map(Number); return {r:p[0],g:p[1],b:p[2], a: p.length>3?p[3]:1}; };
          const lum = (c) => { const f=(v)=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);};
            return 0.2126*f(c.r)+0.7152*f(c.g)+0.0722*f(c.b); };
          const el = document.querySelector(sel);
          const chain = []; let node = el; let chosen = null;
          while (node && node.nodeType === 1) {
            const c = parse(getComputedStyle(node).backgroundColor);
            chain.push({n: node.tagName, a: c ? c.a : null});
            if (c && c.a >= 0.999) { chosen = c; break; }
            node = node.parentElement;
          }
          const fg = parse(getComputedStyle(el).color);
          const L1 = lum(fg), L2 = lum(chosen);
          return {fgA: fg.a, bg: `rgb(${chosen.r},${chosen.g},${chosen.b})`,
                  ratio: Math.round(((Math.max(L1,L2)+0.05)/(Math.min(L1,L2)+0.05))*100)/100,
                  transparentSkipped: chain.slice(0,-1).filter(x=>x.a===0).length,
                  translucentSkipped: chain.slice(0,-1).filter(x=>x.a!==null && x.a>0 && x.a<0.999).length};
        }""", sel)
        bad = "★跨半透明层(会算错)" if out["translucentSkipped"] else "ok"
        print(f"[bg] {sel:22s} fgA={out['fgA']} bg={out['bg']:20s} ratio={out['ratio']:5} "
              f"跳过透明层={out['transparentSkipped']} 跳过半透明层={out['translucentSkipped']} {bad}")
