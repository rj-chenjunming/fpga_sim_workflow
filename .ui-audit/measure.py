#!/usr/bin/env python3
"""B-runtime：在真实 Chromium 里实测 loop/web/index.html 的运行时视觉事实。

只读 loop/web/**（静态服务），只写 .ui-audit/ 下（measure.json + shots-b/*.png）。
API 全部走受控夹具（与 loop/tests/browser/test_web_layout.py::populate 同源），
**不是真实运行数据**；受控夹具只用于渲染出稳定的页面结构以测量样式事实。

复跑（在 repo 根）：
  PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers \
  HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
  loop/.venv/bin/python .ui-audit/measure.py

输出：
  .ui-audit/measure.json        全部原始数字
  .ui-audit/shots-b/*.png       本轮新增截图
stdout：可直接抄进报告的分节摘要。
"""
from __future__ import annotations

import json
import math
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "loop" / "web"
OUT = Path(__file__).resolve().parent
SHOTS = OUT / "shots-b"
GATE = "G1_diff_confirm"
VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]

# ---------------------------------------------------------------- 受控夹具
def view(rid):
    return {
        "run_id": rid, "status": "waiting_gate", "mode": "drill",
        "baseline": rid + "-baseline", "node_history": [],
        "pending_interrupt": {"id": GATE + ":0", "type": "gate_decision",
                              "payload": {"gate": GATE, "cycle": 0}},
        "gate_options": {GATE: [{"value": "confirmed", "label": "服务端确认"},
                                {"value": "ignored", "label": "服务端忽略", "requires_reason": True}]},
    }


def populate(api):
    """与 test_web_layout.py::populate 相同的受控夹具（非真实运行）。"""
    v = api["views"]["A"]
    v.update(project='/simulation/projects/TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES',
             current_node='N4', baseline='v1.2-stable',
             node_history=[{'node': 'N' + str(n), 'status': 'done'} for n in range(4)],
             counts={'koutou1': {'value': 3, 'zero': False, 'label': '口径一 · 未收敛项'},
                     'koutou2': {'value': 1, 'zero': False, 'label': '口径二 · 用例状态'}},
             blockers=[{'severity': 'blocker', 'code': 'REVIEW_PENDING',
                        'message': '接口差异仍有未决条目，请先核对证据。'}],
             agents=[{'role': role, 'nodes': nodes,
                      'capabilities': {'implemented': True, 'dependencies_ready': None,
                                       'execution': 'not_started', 'verification_scope': None},
                      'status': 'done' if role == 'analyst' else 'idle',
                      'last_action': 'node_finished(ok)' if role == 'analyst' else '等待上游步骤',
                      'summary': '已生成接口变更摘要，等待人工复核。' if role == 'analyst' else None,
                      'mode': 'standin', 'elapsed_s': 12 if role == 'analyst' else None}
                     for role, nodes in [('analyst', ['N3']), ('author', ['N6']),
                                         ('checker', ['N8', 'N10']), ('guardian', ['N11']),
                                         ('reporter', ['N12'])]])
    v['pending_interrupt']['payload'].update(difference_items={
        'present': True, 'entries': [
            {'entry_id': 'D-001', 'kind': 'interface', 'change': 'modified',
             'segment': 'dma_controller.sv', 'lines': [128, 129],
             'unresolved': '新增端口位宽需要人工核对',
             'evidence': 'input [15:0] transfer_length → input [31:0] transfer_length'},
            {'entry_id': 'D-002', 'kind': 'register', 'change': 'added',
             'evidence': '新增状态寄存器，需补充边界激励。'}]}, unresolved_entries=['D-001'])


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *_a):
        pass


# ---------------------------------------------------------------- JS 辅助
HELPERS = r"""
window.__h = (() => {
  const parseColor = (s) => {
    if (!s) return null;
    if (s === 'transparent') return {r: 0, g: 0, b: 0, a: 0};
    const m = s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(x => parseFloat(x.trim()));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const cssSel = (el) => {
    if (!el || el.nodeType !== 1) return '';
    const parts = [];
    let cur = el, depth = 0;
    while (cur && cur.nodeType === 1 && depth < 4) {
      if (cur.id) { parts.unshift('#' + cur.id); break; }
      let s = cur.tagName.toLowerCase();
      const cls = (cur.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
      if (cls.length) s += '.' + cls.join('.');
      if (cur.parentElement) {
        const same = [...cur.parentElement.children].filter(c => c.tagName === cur.tagName);
        if (same.length > 1) s += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
      }
      parts.unshift(s);
      cur = cur.parentElement; depth++;
    }
    return parts.join(' > ');
  };
  const directText = (el) => {
    let t = '';
    for (const n of el.childNodes) if (n.nodeType === 3) t += n.nodeValue;
    return t.replace(/\s+/g, ' ').trim();
  };
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.02) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0.5 && r.height > 0.5;
  };
  const lum = (c) => {
    const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const contrast = (a, b) => {
    const la = lum(a), lb = lum(b);
    const hi = Math.max(la, lb), lo = Math.min(la, lb);
    return (hi + 0.05) / (lo + 0.05);
  };
  // 从元素向上合成背景；遇到 gradient/图片 → undecidable
  const effBg = (el) => {
    const layers = []; let gradient = false, image = false, cur = el, undecidable = false;
    const seen = [];
    while (cur && cur.nodeType === 1) {
      const cs = getComputedStyle(cur);
      const bi = cs.backgroundImage;
      if (bi && bi !== 'none') {
        if (/gradient\(/i.test(bi)) { gradient = true; undecidable = true; }
        else { image = true; undecidable = true; }
      }
      const c = parseColor(cs.backgroundColor);
      if (c && c.a > 0) { layers.push(c); seen.push(cssSel(cur)); if (c.a >= 0.999) break; }
      cur = cur.parentElement;
    }
    let base;
    if (layers.length && layers[layers.length - 1].a >= 0.999) {
      base = layers[layers.length - 1];
    } else {
      base = {r: 255, g: 255, b: 255, a: 1};  // 文档默认底色
      if (layers.length) undecidable = true;
    }
    let out = {r: base.r, g: base.g, b: base.b};
    for (let i = layers.length - 2; i >= 0; i--) {
      const l = layers[i];
      out = {r: l.r * l.a + out.r * (1 - l.a), g: l.g * l.a + out.g * (1 - l.a),
             b: l.b * l.a + out.b * (1 - l.a)};
    }
    return {bg: {r: Math.round(out.r), g: Math.round(out.g), b: Math.round(out.b)},
            layers: seen, gradient, image, undecidable};
  };
  const effOpacity = (el) => {
    let o = 1, cur = el;
    while (cur && cur.nodeType === 1) {
      o *= parseFloat(getComputedStyle(cur).opacity);
      if (o < 0.001) break;
      cur = cur.parentElement;
    }
    return o;
  };
  const applyOpacity = (fg, bg, op) => op >= 0.999 ? fg :
      {r: fg.r * op + bg.r * (1 - op), g: fg.g * op + bg.g * (1 - op), b: fg.b * op + bg.b * (1 - op)};
  const all = () => [...document.querySelectorAll('*')];
  const textEls = () => all().filter(el => visible(el) && directText(el).length > 0);
  const rgbStr = (c) => 'rgb(' + c.r + ', ' + c.g + ', ' + c.b + ')';
  const isLarge = (px, w) => px >= 24 || (px >= 18.66 && w >= 700);
  return {parseColor, cssSel, directText, visible, lum, contrast, effBg, effOpacity, applyOpacity,
          all, textEls, rgbStr, isLarge};
})();
"""


# ---------------------------------------------------------------- 各测量节
def measure_fonts(page, cdp):
    """1. 实际字体族：computed fontFamily + 平台真实字体（CDP）+ 宽度探针。"""
    page.evaluate(HELPERS)
    computed = page.evaluate("() => getComputedStyle(document.body).fontFamily")
    html = page.evaluate("""() => ({
        bodyFont: getComputedStyle(document.body).fontFamily,
        monoFont: getComputedStyle(document.querySelector('.mono') || document.body).fontFamily,
        fontsCheck: {
          Inter: document.fonts.check('14px Inter'),
          NotoSansSC: document.fonts.check('14px "Noto Sans SC"'),
          DejaVu: document.fonts.check('14px "DejaVu Sans"'),
          NotoCJKSC: document.fonts.check('14px "Noto Sans CJK SC"')
        },
        faces: [...document.fonts].map(f => ({family: f.family, status: f.status, src: f.src || null}))
    })""")

    # 宽度探针：同一字符串在「字体栈首项」与「明确不存在的族」下宽度是否相同
    probe = page.evaluate("""() => {
        const sample = 'MAILBOX 0189 simulation workbench';
        const mk = (ff) => {
            const s = document.createElement('span');
            s.textContent = sample;
            s.style.cssText = 'position:absolute;left:-9999px;top:0;white-space:nowrap;font-size:40px;font-family:' + ff;
            document.body.appendChild(s);
            const w = s.getBoundingClientRect().width;
            s.remove();
            return Math.round(w * 100) / 100;
        };
        return {
          'Inter': mk('Inter'),
          'NoSuchFamilyXYZ': mk('"NoSuchFamilyXYZ"'),
          'DejaVu Sans': mk('"DejaVu Sans"'),
          'Liberation Sans': mk('"Liberation Sans"'),
          'Noto Sans SC': mk('"Noto Sans SC"'),
          'Noto Sans CJK SC': mk('"Noto Sans CJK SC"'),
          'siteStack': mk(getComputedStyle(document.body).fontFamily),
          'monoStack': mk('"SFMono-Regular", Consolas, "Liberation Mono", monospace')
        };
    }""")

    # CDP：真正参与渲染的平台字体（含字形计数）
    platform = {}
    try:
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        root = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
        for label, expr in [("body", "body"),
                            ("cjk-h2", "#viewS0 .s0-hero h2"),
                            ("page-title", "#pageTitle"),
                            ("latin-edition", ".page-edition"),
                            ("latin-brand", ".brand"),
                            ("latin-addr", "#hdrAddr"),
                            ("mono-path", "#s0Rtl")]:
            try:
                nid = cdp.send("DOM.querySelector", {"nodeId": root, "selector": expr})["nodeId"]
                if not nid:
                    platform[label] = {"error": "selector not found"}
                    continue
                info = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": nid})
                platform[label] = [{"family": f.get("familyName"),
                                    "glyphs": f.get("glyphCount"),
                                    "isCustom": f.get("isCustomFont")} for f in info.get("fonts", [])]
            except Exception as exc:  # noqa: BLE001
                platform[label] = {"error": str(exc)[:160]}
    except Exception as exc:  # noqa: BLE001
        platform = {"error": str(exc)[:200]}

    return {"computed": computed, "html": html, "widthProbe": probe, "platformFonts": platform}


def measure_fontsize(page):
    """2. 字号直方图（可见文本元素；元素数与字符数双口径）。"""
    return page.evaluate("""() => {
        const H = window.__h;
        const els = H.textEls();
        const hist = {};
        let charsTotal = 0, smallChars = 0, smallEls = 0;
        for (const el of els) {
            const cs = getComputedStyle(el);
            const px = Math.round(parseFloat(cs.fontSize) * 100) / 100;
            const txt = H.directText(el);
            const n = txt.length;
            charsTotal += n;
            const k = String(px);
            hist[k] = hist[k] || {count: 0, chars: 0, samples: [], selectors: []};
            hist[k].count += 1; hist[k].chars += n;
            if (px < 12) { smallEls += 1; smallChars += n; }
            if (hist[k].samples.length < 4) {
                hist[k].samples.push(txt.slice(0, 26));
                hist[k].selectors.push(H.cssSel(el));
            }
        }
        return {totalElements: H.all().length, textElements: els.length,
                charsTotal, smallElements: smallEls, smallChars,
                smallElPct: els.length ? smallEls / els.length : 0,
                smallCharPct: charsTotal ? smallChars / charsTotal : 0,
                histogram: hist};
    }""")


def measure_lineheight(page):
    """3. 字号 × 行高配对（行高按 computed 像素；normal 单列）。"""
    return page.evaluate("""() => {
        const H = window.__h;
        const pairs = {};
        for (const el of H.textEls()) {
            const cs = getComputedStyle(el);
            const fs = Math.round(parseFloat(cs.fontSize) * 100) / 100;
            let lh = cs.lineHeight, lhPx = null, ratio = null;
            if (lh === 'normal') { lh = 'normal'; }
            else { lhPx = Math.round(parseFloat(lh) * 100) / 100; ratio = Math.round((lhPx / fs) * 100) / 100; }
            const k = fs + 'px/' + (lhPx === null ? 'normal' : lhPx + 'px');
            pairs[k] = pairs[k] || {fontSize: fs, lineHeight: lhPx, ratio, count: 0, samples: [], selectors: []};
            pairs[k].count += 1;
            if (pairs[k].selectors.length < 3) {
                pairs[k].selectors.push(H.cssSel(el));
                pairs[k].samples.push(H.directText(el).slice(0, 22));
            }
        }
        return pairs;
    }""")


def measure_contrast(page, scope):
    """4. 对比度：WCAG 相对亮度实算；背景向上合成，渐变/图片标不可判定。"""
    return page.evaluate("""(scope) => {
        const H = window.__h;
        const rows = [];
        for (const el of H.textEls()) {
            const cs = getComputedStyle(el);
            const fs = Math.round(parseFloat(cs.fontSize) * 100) / 100;
            const fw = parseFloat(cs.fontWeight) || 400;
            const fg = H.parseColor(cs.color);
            if (!fg) continue;
            const bgInfo = H.effBg(el);
            const op = H.effOpacity(el);
            const fgEff = H.applyOpacity(fg, bgInfo.bg, op);
            const ratio = H.contrast(fgEff, bgInfo.bg);
            const large = H.isLarge(fs, fw);
            const need = large ? 3.0 : 4.5;
            rows.push({selector: H.cssSel(el), text: H.directText(el).slice(0, 30),
                       fontSize: fs, fontWeight: fw,
                       fg: H.rgbStr(fg), fgAlpha: Math.round(fg.a * 100) / 100,
                       bg: H.rgbStr(bgInfo.bg), bgLayers: bgInfo.layers,
                       gradient: bgInfo.gradient, undecidable: bgInfo.undecidable,
                       ratio: Math.round(ratio * 100) / 100, large,
                       opacity: Math.round(op * 100) / 100,
                       required: need, pass: !bgInfo.undecidable && ratio >= need});
        }
        // 去重分组
        const groups = {};
        for (const r of rows) {
            const k = [r.fg, r.fgAlpha, r.bg, r.fontSize, r.fontWeight, r.opacity].join('|');
            groups[k] = groups[k] || {fg: r.fg, fgAlpha: r.fgAlpha, bg: r.bg, fontSize: r.fontSize,
                                      fontWeight: r.fontWeight, large: r.large, ratio: r.ratio,
                                      opacity: r.opacity,
                                      required: r.required, undecidable: r.undecidable,
                                      count: 0, selectors: [], samples: [], gradient: r.gradient,
                                      bgLayers: r.bgLayers};
            const g = groups[k];
            g.count += 1;
            if (g.selectors.length < 4) { g.selectors.push(r.selector); g.samples.push(r.text); }
        }
        const gl = Object.values(groups).sort((a, b) => a.ratio - b.ratio);
        const textRows = rows.filter(r => !r.undecidable);
        return {scope, textNodes: rows.length,
                undecidable: rows.filter(r => r.undecidable).length,
                failCount: textRows.filter(r => !r.pass).length,
                min: textRows.length ? Math.min(...textRows.map(r => r.ratio)) : null,
                groups: gl,
                failing: textRows.filter(r => !r.pass).sort((a, b) => a.ratio - b.ratio)
                                  .slice(0, 40)};
    }""", scope)


def measure_pairs(page, scope, items):
    """指定 selector 的 前景/背景/对比度（任务点名要覆盖的令牌对）。"""
    return page.evaluate("""({scope, items}) => {
        const H = window.__h;
        const out = [];
        for (const [label, selector] of items) {
            const el = document.querySelector(selector);
            if (!el) { out.push({scope, label, selector, missing: true}); continue; }
            const cs = getComputedStyle(el);
            const fg = H.parseColor(cs.color);
            const bgInfo = H.effBg(el);
            const fs = Math.round(parseFloat(cs.fontSize) * 100) / 100;
            const fw = parseFloat(cs.fontWeight) || 400;
            const op = H.effOpacity(el);
            const ratio = fg ? H.contrast(H.applyOpacity(fg, bgInfo.bg, op), bgInfo.bg) : null;
            const large = H.isLarge(fs, fw);
            out.push({scope, label, selector, text: H.directText(el).slice(0, 28),
                      fontSize: fs, fontWeight: fw,
                      fg: fg ? H.rgbStr(fg) : null, bg: H.rgbStr(bgInfo.bg),
                      opacity: Math.round(op * 100) / 100,
                      bgLayers: bgInfo.layers, gradient: bgInfo.gradient,
                      undecidable: bgInfo.undecidable,
                      ratio: ratio === null ? null : Math.round(ratio * 100) / 100,
                      required: large ? 3.0 : 4.5,
                      pass: ratio !== null && !bgInfo.undecidable && ratio >= (large ? 3.0 : 4.5)});
        }
        return out;
    }""", {"scope": scope, "items": items})


S0_PAIRS = [
    ("page-edition #7b8b81", ".page-edition"),
    ("diagram-label #71876a", ".diagram-label"),
    ("rail-kicker(--rail-muted)", ".rail-kicker"),
    ("rail-label(--rail-muted)", ".rail-label"),
    ("rail-label>span #839c8d", ".rail-label > span"),
    ("rail-entry small(--rail-muted)", ".rail-entry small"),
    ("run-item meta(--rail-muted)", ".run-item .meta"),
    ("rail-foot(--rail-muted)", ".rail-foot"),
    ("pageSub(--muted)", "#pageSub"),
    ("hero p #59705b", ".s0-hero p"),
    ("hero eyebrow #5c7a59", ".s0-hero .eyebrow"),
    ("hero-tags span", ".hero-tags span"),
    ("s0SubmitHint(--muted)", "#s0SubmitHint"),
    ("card-head sub", ".card-head .sub"),
    ("readiness(--muted?)", "#s0Readiness"),
    ("s0-label span", ".s0-label span"),
    ("disabled s0Prepare", "#s0Prepare"),
    ("btn-primary", "#btnNew"),
    ("skip-link", ".skip-link"),
    ("s0-boundary", ".s0-boundary"),
    ("receipt-empty", ".receipt-empty"),
]
GATE_PAIRS = [
    ("option span(--muted)", ".option span"),
    ("option b", ".option b"),
    ("diff-meta(--muted)", ".diff-meta"),
    ("diff-unresolved(--warn)", ".diff-unresolved"),
    ("gate-blockers(--danger)", ".gate-blockers"),
    ("gate-pane", "#gateMaterial"),
    ("disabled btn", "#gatePanel .btn:disabled, #gatePanel button[disabled]"),
    ("linkbtn", ".linkbtn"),
]
MONITOR_PAIRS = [
    ("agent-note(--warn)", ".agent-note"),
    ("agent-action(--primary)", ".agent-action"),
    ("run-item meta(--rail-muted)", ".run-item .meta"),
    ("chip", ".chip"),
    ("muted tiny", ".muted.tiny"),
]

NAMED = ['.seg button', '#viewSeg button', '.rail-entry', '#btnNew', '.action-item', '.run-item',
         '.rail-foot', '.rail-label', '.btn', '.btn-sm', '.chip', '.linkbtn', '.ev-chip',
         '.agent-open', '#s0Prepare', '.s0-hero', '.s0-hero h2', '.page-edition', '.diagram-label',
         'summary', '.gate-pane', '.option', '.input', '.agent', '.stage-head', '.snode',
         '.diff-item', '.foot-note', '.page-breadcrumb', '.receipt-path', '.s0-checks li > span',
         '.card', '.card-head', '.rail-top']


def measure_named(page, scope):
    """点名控件的运行时盒子/字号（不存在记 missing，绝不臆造）。"""
    return page.evaluate("""({scope, names}) => {
        const H = window.__h;
        const out = [];
        for (const name of names) {
            const nodes = [...document.querySelectorAll(name)].filter(n => H.visible(n));
            if (!nodes.length) { out.push({scope, name, count: 0, visibleCount: 0, missing: true}); continue; }
            const el = nodes[0];
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            out.push({scope, name, count: document.querySelectorAll(name).length,
                      visibleCount: nodes.length,
                      box: {w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10},
                      fontSize: Math.round(parseFloat(cs.fontSize) * 100) / 100,
                      fontWeight: parseFloat(cs.fontWeight) || 400,
                      lineHeight: cs.lineHeight, color: cs.color,
                      bg: cs.backgroundColor, sample: H.cssSel(el),
                      borders: [cs.borderTopWidth + ' ' + cs.borderTopStyle,
                                cs.borderRightWidth + ' ' + cs.borderRightStyle,
                                cs.borderBottomWidth + ' ' + cs.borderBottomStyle,
                                cs.borderLeftWidth + ' ' + cs.borderLeftStyle].join(' | '),
                      radius: cs.borderRadius,
                      label: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 26)});
        }
        return out;
    }""", {"scope": scope, "names": NAMED})


def measure_targets(page):
    """7. 点击目标尺寸（button/a/summary/[role=button]/label.option）。"""
    return page.evaluate("""() => {
        const H = window.__h;
        const sel = 'button, a[href], summary, input:not([type="hidden"]), [role="button"], .option, .agent-clickable';
        const rows = [];
        for (const el of [...document.querySelectorAll(sel)]) {
            if (!H.visible(el)) continue;
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            rows.push({selector: H.cssSel(el), tag: el.tagName.toLowerCase(),
                       label: (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().slice(0, 34),
                       w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
                       fontSize: Math.round(parseFloat(cs.fontSize) * 100) / 100});
        }
        const lt24 = rows.filter(x => x.w < 24 || x.h < 24);
        const lt32 = rows.filter(x => x.w < 32 || x.h < 32);
        return {count: rows.length, lt24, lt32,
                byHeight: rows.map(x => x.h).sort((a, b) => a - b)};
    }""")


def measure_borders_gradients(page):
    """8. 单侧边框 & 背景渐变。"""
    return page.evaluate("""() => {
        const H = window.__h;
        const oneSided = [], grads = [];
        let hero = null;
        for (const el of H.all()) {
            const cs = getComputedStyle(el);
            if (!H.visible(el)) continue;
            const sides = {
                top: parseFloat(cs.borderTopWidth) || 0, right: parseFloat(cs.borderRightWidth) || 0,
                bottom: parseFloat(cs.borderBottomWidth) || 0, left: parseFloat(cs.borderLeftWidth) || 0
            };
            const styles = {
                top: cs.borderTopStyle, right: cs.borderRightStyle,
                bottom: cs.borderBottomStyle, left: cs.borderLeftStyle
            };
            const nz = Object.entries(sides).filter(([k, v]) => v > 0 && styles[k] !== 'none');
            if (nz.length === 1) oneSided.push({selector: H.cssSel(el), side: nz[0][0], width: nz[0][1],
                                                style: styles[nz[0][0]],
                                                color: cs['border' + nz[0][0][0].toUpperCase() + nz[0][0].slice(1) + 'Color']});
            const bi = cs.backgroundImage;
            if (bi && bi !== 'none' && /gradient\\(/i.test(bi)) {
                grads.push({selector: H.cssSel(el), image: bi, size: cs.backgroundSize, repeat: cs.backgroundRepeat});
            }
        }
        const heroEl = document.querySelector('.s0-hero');
        if (heroEl) {
            const cs = getComputedStyle(heroEl);
            hero = {selector: H.cssSel(heroEl), backgroundImage: cs.backgroundImage,
                    backgroundSize: cs.backgroundSize, backgroundColor: cs.backgroundColor,
                    backgroundRepeat: cs.backgroundRepeat};
        }
        return {oneSidedCount: oneSided.length, oneSided, gradients: grads, hero};
    }""")


def measure_motion(page):
    """9. 动效：timing-function / duration 直方图 + prefers-reduced-motion 实测。"""
    light = page.evaluate("""() => {
        const H = window.__h;
        const tf = {}, dur = {}, offenders = [];
        for (const el of H.all()) {
            const cs = getComputedStyle(el);
            const props = cs.transitionProperty;
            if (!props || props === 'all' && cs.transitionDuration === '0s') {}
            const d = cs.transitionDuration, t = cs.transitionTimingFunction;
            if (d && d !== '0s') {
                dur[d] = (dur[d] || 0) + 1;
                tf[t] = (tf[t] || 0) + 1;
                if (offenders.length < 60) offenders.push({selector: H.cssSel(el), duration: d, timing: t, props});
            }
        }
        const anims = [];
        for (const el of H.all()) {
            const cs = getComputedStyle(el);
            if (cs.animationName && cs.animationName !== 'none') {
                anims.push({selector: H.cssSel(el), name: cs.animationName,
                            duration: cs.animationDuration, timing: cs.animationTimingFunction,
                            iterations: cs.animationIterationCount});
            }
        }
        return {durationHistogram: dur, timingHistogram: tf, offenders, animations: anims};
    }""")
    page.emulate_media(reduced_motion="reduce")
    reduced = page.evaluate("""() => {
        const H = window.__h;
        const sample = ['.btn', '.seg button', '.rail-entry', '.agent-clickable', '.s0-hero', '.card',
                        '.stage-bar i', '.tooltip', '.icon-spin', '.badge'];
        const out = [];
        for (const s of sample) {
            const el = document.querySelector(s);
            if (!el) { out.push({selector: s, missing: true}); continue; }
            const cs = getComputedStyle(el);
            out.push({selector: s, transitionDuration: cs.transitionDuration,
                      transitionProperty: cs.transitionProperty,
                      animationName: cs.animationName, animationDuration: cs.animationDuration});
        }
        let nonzero = 0;
        for (const el of H.all()) {
            const cs = getComputedStyle(el);
            if (cs.transitionDuration !== '0s' && cs.transitionDuration !== '') nonzero++;
            if (cs.animationName !== 'none') nonzero++;
        }
        return {samples: out, elementsWithMotion: nonzero,
                mediaMatches: matchMedia('(prefers-reduced-motion: reduce)').matches};
    }""")
    page.screenshot(path=str(SHOTS / "1440-reduced-motion.png"))
    page.emulate_media(reduced_motion="no-preference")
    return {"light": light, "reduced": reduced}


def measure_scheme(page):
    """10. prefers-color-scheme: dark 下是否仍为浅色。"""
    light = page.evaluate("""() => ({
        bodyBg: getComputedStyle(document.body).backgroundColor,
        bodyColor: getComputedStyle(document.body).color,
        htmlColorScheme: getComputedStyle(document.documentElement).colorScheme,
        panelBg: getComputedStyle(document.querySelector('.card') || document.body).backgroundColor,
        rootVars: {
          bg: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(),
          text: getComputedStyle(document.documentElement).getPropertyValue('--text').trim()
        }
    })""")
    page.emulate_media(color_scheme="dark")
    dark = page.evaluate("""() => ({
        mediaMatches: matchMedia('(prefers-color-scheme: dark)').matches,
        bodyBg: getComputedStyle(document.body).backgroundColor,
        bodyColor: getComputedStyle(document.body).color,
        htmlColorScheme: getComputedStyle(document.documentElement).colorScheme,
        panelBg: getComputedStyle(document.querySelector('.card') || document.body).backgroundColor,
        rootVars: {
          bg: getComputedStyle(document.documentElement).getPropertyValue('--bg').trim(),
          text: getComputedStyle(document.documentElement).getPropertyValue('--text').trim()
        }
    })""")
    page.screenshot(path=str(SHOTS / "1440-dark-scheme.png"))
    page.emulate_media(color_scheme="light")
    return {"light": light, "dark": dark}


def measure_fold(page, width, height):
    """6. 首屏：主操作/hero 的 boundingBox 与视口关系。"""
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("scrollTo(0,0)")
    page.wait_for_timeout(60)
    data = page.evaluate("""() => {
        const H = window.__h;
        const box = (s) => {
            const el = document.querySelector(s);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            return {selector: s, x: Math.round(r.x * 10) / 10, y: Math.round(r.y * 10) / 10,
                    w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10,
                    bottom: Math.round(r.bottom * 10) / 10};
        };
        const targets = ['header', '#workspace', '.page-head', '.s0-hero', '.s0-phases',
                         '#s0Rtl', '#s0Advanced', '#s0Prepare', '#s0Readiness',
                         '.s0-evidence', '.s0-rehearsal'];
        const boxes = targets.map(box).filter(Boolean);
        const vh = innerHeight, vw = innerWidth;
        return {vw, vh, boxes,
                fold: boxes.map(b => ({selector: b.selector, fullyInFirstScreen: b.y >= 0 && b.bottom <= vh,
                                       topInFirstScreen: b.y < vh,
                                       visibleRatio: Math.max(0, Math.min(b.bottom, vh) - Math.max(b.y, 0)) / b.h})),
                scrollHeight: document.documentElement.scrollHeight,
                horizontalOverflow: document.documentElement.scrollWidth - vw};
    }""")
    page.screenshot(path=str(SHOTS / f"{width}x{height}-s0-first-screen.png"))
    return data


def measure_gate_fold(page, width, height):
    """6b. 闸门视图首屏：闸门材料/操作两栏是否在首屏内（附加观测）。"""
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate("scrollTo(0,0)")
    page.wait_for_timeout(80)
    data = page.evaluate("""() => {
        const box = (s) => {
            const el = [...document.querySelectorAll(s)].find(n => n.getClientRects().length);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            if (r.width < 1 || r.height < 1) return null;
            return {selector: s, y: Math.round(r.y * 10) / 10, h: Math.round(r.height * 10) / 10,
                    bottom: Math.round(r.bottom * 10) / 10};
        };
        const targets = ['header', '#gateHead', '.stage-head', '#gateMaterial', '#gatePanel',
                         '#gateCardBody', '.gate-options', '#gateMaterial .diff-item', 'footer'];
        const boxes = targets.map(box).filter(Boolean);
        const vh = innerHeight;
        return {vw: innerWidth, vh, boxes,
                fold: boxes.map(b => ({selector: b.selector, fullyInFirstScreen: b.y >= 0 && b.bottom <= vh,
                                       visibleRatio: Math.round((Math.max(0, Math.min(b.bottom, vh) - Math.max(b.y, 0)) / b.h) * 100) / 100})),
                scrollHeight: document.documentElement.scrollHeight,
                horizontalOverflow: document.documentElement.scrollWidth - innerWidth};
    }""")
    page.screenshot(path=str(SHOTS / f"{width}x{height}-gate-first-screen.png"))
    return data


def focus_snapshot(page):
    return page.evaluate("""() => {
        const H = window.__h;
        const el = document.activeElement;
        if (!el || el === document.body) return {selector: 'BODY', tag: 'body'};
        const cs = getComputedStyle(el);
        // 视觉焦点环可能挂在外层/相邻元素上（.option input:focus-visible + .radio）
        const probe = (node) => {
            if (!node) return null;
            const c = getComputedStyle(node);
            return {selector: H.cssSel(node), outlineWidth: c.outlineWidth, outlineStyle: c.outlineStyle,
                    outlineColor: c.outlineColor, boxShadow: c.boxShadow.slice(0, 60),
                    opacity: c.opacity};
        };
        const ringC = H.parseColor(cs.outlineColor);
        // outline-offset>0 时焦点环画在父级背景上，对比度应对父级底色算
        const offsetPx = parseFloat(cs.outlineOffset) || 0;
        const ringHost = (offsetPx > 0 && el.parentElement) ? el.parentElement : el;
        const bgInfo = H.effBg(ringHost);
        const ringOpacity = (offsetPx > 0 ? 1 : H.effOpacity(el)) * (ringC ? ringC.a : 1);
        const ringRatio = (ringC && cs.outlineStyle !== 'none' && cs.outlineWidth !== '0px')
            ? Math.round(H.contrast(H.applyOpacity(ringC, bgInfo.bg, ringOpacity), bgInfo.bg) * 100) / 100
            : null;
        return {selector: H.cssSel(el), tag: el.tagName.toLowerCase(),
                id: el.id || null, text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 30),
                focusVisible: el.matches(':focus-visible'),
                ringColor: cs.outlineColor, ringWidth: cs.outlineWidth, ringStyle: cs.outlineStyle,
                ringOffset: cs.outlineOffset, ringBg: H.rgbStr(bgInfo.bg), ringContrast: ringRatio,
                outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle,
                outlineColor: cs.outlineColor, outlineOffset: cs.outlineOffset,
                opacity: cs.opacity,
                boxShadow: cs.boxShadow.slice(0, 80),
                sibling: probe(el.nextElementSibling),
                rect: (() => { const r = el.getBoundingClientRect();
                               return {x: Math.round(r.x), y: Math.round(r.y),
                                       w: Math.round(r.width), h: Math.round(r.height)}; })()};
    }""")


def measure_focus(page, tag, count=20):
    """5. 焦点可见性：真键盘 Tab 走一遍 + skip link → main:focus{outline:none}。"""
    page.evaluate("scrollTo(0,0)")
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("body").click(position={"x": 400, "y": 300})
    steps = []
    for i in range(count):
        page.keyboard.press("Tab")
        page.wait_for_timeout(15)
        snap = focus_snapshot(page)
        snap["step"] = i + 1
        steps.append(snap)
        if i in (0, 2, 6):
            page.screenshot(path=str(SHOTS / f"1440-focus-{tag}-tab-{i + 1}.png"))

    page.evaluate("scrollTo(0,0)")
    page.locator(".skip-link").focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(120)
    skip = {"afterEnter": focus_snapshot(page),
            "scrollY": page.evaluate("Math.round(scrollY)"),
            "mainOutline": page.evaluate(
                """() => { const m = document.querySelector('#workspace'); const cs = getComputedStyle(m);
                           return {outlineWidth: cs.outlineWidth, outlineStyle: cs.outlineStyle,
                                   outlineColor: cs.outlineColor, focusVisible: m.matches(':focus-visible'),
                                   tabindex: m.getAttribute('tabindex')}; }""")}
    page.screenshot(path=str(SHOTS / f"1440-focus-skip-{tag}.png"))
    return {"tag": tag, "tabSequence": steps, "skipLink": skip}


def summarize_focus(focus):
    seq = focus["tabSequence"]
    withRing = [s for s in seq if s.get("outlineStyle") not in (None, "none") and s.get("outlineWidth") not in (None, "0px")]
    return {"tag": focus["tag"], "steps": len(seq),
            "withVisibleOutline": len(withRing),
            "withoutVisibleOutline": len(seq) - len(withRing),
            "skipLink": focus["skipLink"],
            "sequence": [{"step": s["step"], "selector": s.get("selector"), "tag": s.get("tag"),
                          "focusVisible": s.get("focusVisible"), "opacity": s.get("opacity"),
                          "outline": f'{s.get("outlineWidth")} {s.get("outlineStyle")} {s.get("outlineColor")}',
                          "ringContrast": s.get("ringContrast"), "ringBg": s.get("ringBg"),
                          "sibling": s.get("sibling"), "rect": s.get("rect")} for s in seq]}


def measure_disabled(page):
    """禁用态文本对比度（.btn:disabled{opacity:.5} 的真实合成色）。"""
    return page.evaluate("""() => {
        const H = window.__h;
        const out = [];
        for (const el of [...document.querySelectorAll(':disabled, [aria-disabled="true"], .disabled')]) {
            if (!H.visible(el)) continue;
            const cs = getComputedStyle(el);
            const fg = H.parseColor(cs.color);
            const bgInfo = H.effBg(el);
            const op = H.effOpacity(el);
            const ownBg = H.parseColor(cs.backgroundColor);
            const base = (ownBg && ownBg.a >= 0.999) ? ownBg : bgInfo.bg;
            const eFg = H.applyOpacity(fg, base, op);
            const eBg = H.applyOpacity(base, bgInfo.bg, op);
            const ratio = H.contrast(eFg, eBg);
            const r = el.getBoundingClientRect();
            out.push({selector: H.cssSel(el), text: (el.innerText || el.value || '').replace(/\\s+/g, ' ').trim().slice(0, 30),
                      fg: H.rgbStr(eFg), bg: H.rgbStr(eBg),
                      declaredFg: H.rgbStr(fg), declaredBg: H.rgbStr(base),
                      opacity: Math.round(op * 100) / 100,
                      fontSize: Math.round(parseFloat(cs.fontSize) * 100) / 100,
                      ratio: Math.round(ratio * 100) / 100,
                      w: Math.round(r.width), h: Math.round(r.height)});
        }
        // 合成探针：即使当前视图没有禁用按钮，也读真实 .btn:disabled 规则
        const host = document.querySelector('.card-body') || document.body;
        const probeBtn = document.createElement('button');
        probeBtn.className = 'btn btn-primary';
        probeBtn.textContent = 'PROBE';
        probeBtn.disabled = true;
        probeBtn.style.cssText = 'position:absolute;left:-9999px;top:0';
        host.appendChild(probeBtn);
        const pcs = getComputedStyle(probeBtn);
        const pfg = H.parseColor(pcs.color), pbg = H.parseColor(pcs.backgroundColor);
        const panelEl = document.querySelector('.card') || document.body;
        const pBgEff = H.parseColor(getComputedStyle(panelEl).backgroundColor) || {r:255,g:255,b:255,a:1};
        const pop = H.effOpacity(probeBtn);
        const eFgP = H.applyOpacity(pfg, pBgEff, pop);
        const eBgP = H.applyOpacity(pbg, pBgEff, pop);
        const probe = {selector: 'probe .btn.btn-primary:disabled', declaredFg: H.rgbStr(pfg),
                       declaredBg: H.rgbStr(pbg), panelBg: H.rgbStr(pBgEff),
                       opacity: Math.round(pop * 100) / 100,
                       effectiveFg: H.rgbStr(eFgP), effectiveBg: H.rgbStr(eBgP),
                       ratio: Math.round(H.contrast(eFgP, eBgP) * 100) / 100,
                       fontSize: pcs.fontSize};
        probeBtn.remove();
        return {visibleDisabled: out, probe};
    }""")


# ---------------------------------------------------------------- 主流程
def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(WEB)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    result = {"meta": {"url": base, "web_root": str(WEB),
                       "viewportList": VIEWPORTS,
                       "fixture": "controlled API fixture (test_web_layout.populate) — NOT a real run",
                       "chromium": None}}
    try:
        with sync_playwright() as p:
            exe = os.environ.get("LOOP_BROWSER_EXECUTABLE")
            browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
            result["meta"]["chromium"] = browser.version
            page = browser.new_page()
            page.set_default_timeout(8000)
            page.clock.install()
            api = {"views": {rid: view(rid) for rid in ("A", "B")}, "hold": None,
                   "pending": [], "posts": [], "nodes": {}}
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def route(route):
                path = urlsplit(route.request.url).path
                if route.request.method == "POST":
                    api["posts"].append((path, route.request.post_data_json))
                    api["pending"].append(route)
                    return
                if path.endswith("/stream"):
                    route.fulfill(status=404, json={"detail": {"error": "stream not stubbed"}})
                    return
                if path == "/api/health":
                    body = {"ok": True, "env_root": "/fixture", "plugin_missing": [], "workspace_missing": []}
                elif path == "/api/baselines":
                    body = {"baselines": []}
                elif path == "/api/s0":
                    body = {"baseline": "/fixture", "records": [],
                            "allowed_roots": ["/fixture"],
                            "capabilities": {"prepare": True, "rehearsal": True,
                                             "tb_adapt": False, "smoke": False}}
                elif path == "/api/runs":
                    body = {"runs": [{"run_id": rid, "status": "waiting_gate", "mode": "drill"}
                                     for rid in api["views"]]}
                elif path.startswith("/api/runs/") and "/nodes/" in path:
                    rest = path.split("/api/runs/", 1)[1]
                    rid, node = rest.split("/nodes/", 1)
                    body = api["nodes"].get((rid, node), {"run_id": rid, "node": node, "known": False,
                                                          "authority": "projection", "events": []})
                elif path.endswith("/evidence/exists"):
                    body = {"path": "/fixture/evidence", "exists": True, "bytes": 12}
                elif path.startswith("/api/runs/") and "/agents/" in path:
                    rid, node = path.split("/api/runs/", 1)[1].split("/agents/", 1)
                    body = {"run_id": rid, "node": node, "live": None, "selected_attempt": None,
                            "attempts": [], "request": None, "result": None, "events": [], "controls": []}
                elif path.startswith("/api/runs/"):
                    body = api["views"][path.rsplit("/", 1)[1]]
                else:
                    body = {"ok": False}
                route.fulfill(json=body)

            page.route("**/api/**", route)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto(base)
            page.locator(".run-item").first.wait_for()
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(150)
            page.screenshot(path=str(SHOTS / "1440-s0-default.png"))
            cdp = page.context.new_cdp_session(page)

            result["M1_fonts"] = measure_fonts(page, cdp)
            result["M2_fontSize"] = measure_fontsize(page)
            result["M3_lineHeight"] = measure_lineheight(page)
            result["M4_contrast_s0"] = measure_contrast(page, "s0")
            result["M4b_pairs_s0"] = measure_pairs(page, "s0", S0_PAIRS)
            result["M7_targets_s0"] = measure_targets(page)
            result["M7c_named_s0"] = measure_named(page, "s0")
            result["M8_borders_gradients"] = measure_borders_gradients(page)
            result["M7b_disabled_s0"] = measure_disabled(page)
            result["M5_focus_s0"] = summarize_focus(measure_focus(page, "s0", 22))

            # 运行视图 / 闸门视图（点击受控夹具的 run A）
            populate(api)
            page.locator(".run-item").first.click()
            page.wait_for_timeout(150)
            page.screenshot(path=str(SHOTS / "1440-gate-view.png"))
            result["M4_contrast_gate"] = measure_contrast(page, "gate")
            result["M4b_pairs_gate"] = measure_pairs(page, "gate", GATE_PAIRS)
            result["M7_targets_gate"] = measure_targets(page)
            result["M7c_named_gate"] = measure_named(page, "gate")
            result["M7b_disabled_gate"] = measure_disabled(page)
            # 选中一个闸门选项 → 触发 `.option.on .radio` 的 radial-gradient 规则
            page.evaluate("document.querySelector('.option input').click()")
            page.wait_for_timeout(100)
            result["M8_gate_gradients"] = page.evaluate("""() => {
                const H = window.__h;
                const out = [];
                for (const el of H.all()) {
                    const cs = getComputedStyle(el);
                    const bi = cs.backgroundImage;
                    if (bi && bi !== 'none' && /gradient\\(/i.test(bi)) {
                        const r = el.getBoundingClientRect();
                        out.push({selector: H.cssSel(el), image: bi,
                                  box: {w: Math.round(r.width), h: Math.round(r.height)},
                                  size: cs.backgroundSize, repeat: cs.backgroundRepeat});
                    }
                }
                return out;
            }""")
            page.screenshot(path=str(SHOTS / "1440-gate-option-checked.png"))
            result["M5_focus_gate"] = summarize_focus(measure_focus(page, "gate", 18))
            result["M6b_gate_fold"] = [measure_gate_fold(page, w, h) for (w, h) in VIEWPORTS]
            page.set_viewport_size({"width": 1440, "height": 900})
            page.wait_for_timeout(80)

            page.locator("#segRun").click()
            page.wait_for_timeout(150)
            page.screenshot(path=str(SHOTS / "1440-monitor-view.png"))
            result["M4_contrast_monitor"] = measure_contrast(page, "monitor")
            result["M4b_pairs_monitor"] = measure_pairs(page, "monitor", MONITOR_PAIRS)
            result["M7_targets_monitor"] = measure_targets(page)
            result["M7c_named_monitor"] = measure_named(page, "monitor")

            # 回到 S0 做首屏与动效、配色方案
            page.locator("#segS0").click()
            page.wait_for_timeout(120)
            result["M6_fold"] = [measure_fold(page, w, h) for (w, h) in VIEWPORTS]
            page.set_viewport_size({"width": 1440, "height": 900})
            result["M9_motion"] = measure_motion(page)
            result["M10_scheme"] = measure_scheme(page)
            page.screenshot(path=str(SHOTS / "1440-dark-scheme.png"))

            result["pageErrors"] = errors
            result["posts"] = [p[0] for p in api["posts"]]
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    (OUT / "measure.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(result)
    return result


def print_summary(r):
    print("=" * 78)
    print("M1 字体")
    print("  body font-family:", r["M1_fonts"]["computed"])
    print("  platformFonts:", json.dumps(r["M1_fonts"]["platformFonts"], ensure_ascii=False))
    print("  widthProbe:", json.dumps(r["M1_fonts"]["widthProbe"], ensure_ascii=False))
    print("  faces:", r["M1_fonts"]["html"].get("faces"))

    m2 = r["M2_fontSize"]
    print("=" * 78)
    print(f"M2 字号  textElements={m2['textElements']} chars={m2['charsTotal']} "
          f"<12px: els={m2['smallElements']} ({m2['smallElPct']*100:.1f}%) "
          f"chars={m2['smallChars']} ({m2['smallCharPct']*100:.1f}%)")
    for k in sorted(m2["histogram"], key=lambda x: float(x)):
        v = m2["histogram"][k]
        print(f"  {k:>6}px  count={v['count']:>3} chars={v['chars']:>5}  e.g. {v['selectors'][:2]}")

    print("=" * 78)
    print("M3 字号/行高配对")
    for k in sorted(r["M3_lineHeight"], key=lambda x: (float(x.split('/')[0].replace('px', '')), x)):
        v = r["M3_lineHeight"][k]
        print(f"  {k:<16} ratio={v['ratio']} count={v['count']:>3} e.g. {v['selectors'][:2]}")

    for key in ("M4_contrast_s0", "M4_contrast_gate", "M4_contrast_monitor"):
        c = r[key]
        print("=" * 78)
        print(f"{key}  scope={c['scope']} textNodes={c['textNodes']} undecidable={c['undecidable']} "
              f"fail={c['failCount']} minRatio={c['min']}")
        for g in c["groups"][:18]:
            flag = "FAIL" if g["ratio"] < g["required"] else "ok  "
            print(f"  {flag} {g['ratio']:>5} (need {g['required']}) {g['fg']:<22} on {g['bg']:<18} "
                  f"{g['fontSize']}px/{g['fontWeight']} n={g['count']:<3} {g['selectors'][:2]}")

    for key in ("M4b_pairs_s0", "M4b_pairs_gate", "M4b_pairs_monitor"):
        if key not in r:
            continue
        print("=" * 78)
        print(f"{key}  点名令牌对")
        for it in r[key]:
            if it.get("missing"):
                print(f"  MISSING {it['label']:<32} {it['selector']}")
                continue
            flag = "ok  " if it["pass"] else ("UNDET" if it["undecidable"] else "FAIL")
            print(f"  {flag} {str(it['ratio']):>6} (need {it['required']}) {it['fg']:<20} on {it['bg']:<18} "
                  f"{it['fontSize']:>5}px/{it['fontWeight']:<4} {it['label']:<30} {it['selector']}")

    for key in ("M7_targets_s0", "M7_targets_gate", "M7_targets_monitor"):
        t = r[key]
        print("=" * 78)
        print(f"{key}  targets={t['count']} <24={len(t['lt24'])} <32={len(t['lt32'])}")
        for x in t["lt24"][:14]:
            print(f"  <24 {x['w']}x{x['h']}  {x['selector']}  {x['label'][:26]!r}")
        seen = set()
        for x in t["lt32"]:
            k = (x["w"], x["h"])
            if k in seen:
                continue
            seen.add(k)
            print(f"  <32 {x['w']}x{x['h']}  {x['selector']}  {x['label'][:26]!r}")

    print("=" * 78)
    b = r["M8_borders_gradients"]
    real = [x for x in b["oneSided"] if x["style"] != "none"]
    print(f"M8 single-sided borders(raw={b['oneSidedCount']}) real(style!=none)={len(real)} "
          f"style-none(未描边)={b['oneSidedCount'] - len(real)}  gradients(S0)={len(b['gradients'])}")
    for g in b["gradients"]:
        print("  grad:", g["selector"], "|", g["image"][:100])
    for s in real:
        print("  onesided:", s)
    print("  hero:", json.dumps(b["hero"], ensure_ascii=False))
    print("  gate gradients:", json.dumps(r.get("M8_gate_gradients", []), ensure_ascii=False))

    for key in ("M7c_named_s0", "M7c_named_gate", "M7c_named_monitor"):
        if key not in r:
            continue
        print("=" * 78)
        print(key)
        for it in r[key]:
            if it.get("missing"):
                print(f"  MISSING {it['name']:<24}")
            else:
                print(f"  {it['name']:<24} {it['box']['w']}x{it['box']['h']:<8} fs={it['fontSize']:<6} "
                      f"fw={it['fontWeight']:<4} n={it['visibleCount']:<2} r={it['radius']:<6} "
                      f"border[l,t,r,b]={it['borders']}  {it['label']!r}")

    print("=" * 78)
    for key in ("M5_focus_s0", "M5_focus_gate"):
        f = r[key]
        print(f"{key} steps={f['steps']} withOutline={f['withVisibleOutline']} noOutline={f['withoutVisibleOutline']}")
        for s in f["sequence"]:
            sib = s.get("sibling")
            sibtxt = "" if not sib else f"  sibling[{sib['selector'][:28]}] outline={sib['outlineWidth']} {sib['outlineStyle']} {sib['outlineColor']}"
            print(f"  {s['step']:>2}. {str(s['selector'])[:40]:<40} fv={s['focusVisible']} "
                  f"ring={s.get('ringContrast')} outline={s['outline']}{sibtxt}")
        sl = f["skipLink"]
        print("  skipLink.afterEnter:", json.dumps(sl["afterEnter"], ensure_ascii=False)[:260])
        print("  skipLink.mainOutline:", json.dumps(sl["mainOutline"], ensure_ascii=False),
              " scrollY=", sl["scrollY"])

    for key in ("M7b_disabled_s0", "M7b_disabled_gate"):
        d = r.get(key)
        if not d:
            continue
        print("=" * 78)
        print(f"{key} visibleDisabled={len(d['visibleDisabled'])}  probe={json.dumps(d['probe'], ensure_ascii=False)}")
        for it in d["visibleDisabled"][:8]:
            print(f"  {it['ratio']:>6} {it['fg']} on {it['bg']} opacity={it['opacity']} {it['fontSize']}px {it['selector'][:50]}")

    if "M6b_gate_fold" in r:
        for d in r["M6b_gate_fold"]:
            print("=" * 78)
            print(f"M6b gate fold {d['vw']}x{d['vh']} scrollHeight={d['scrollHeight']} hOverflow={d['horizontalOverflow']}")
            for fo in d["fold"]:
                print(f"  {fo['selector']:<26} inFirstScreen={fo['fullyInFirstScreen']!s:<5} visibleRatio={fo['visibleRatio']:.2f}")
            for bx in d["boxes"]:
                print(f"    box {bx['selector']:<26} y={bx['y']:>7} h={bx['h']:>7} bottom={bx['bottom']:>7}")

    print("=" * 78)
    for d in r["M6_fold"]:
        print(f"M6 fold {d['vw']}x{d['vh']} scrollHeight={d['scrollHeight']} hOverflow={d['horizontalOverflow']}")
        for fo in d["fold"]:
            print(f"  {fo['selector']:<16} inFirstScreen={fo['fullyInFirstScreen']!s:<5} "
                  f"topIn={fo['topInFirstScreen']!s:<5} visibleRatio={fo['visibleRatio']:.2f}")
        for bx in d["boxes"]:
            print(f"    box {bx['selector']:<16} y={bx['y']:>7} h={bx['h']:>7} bottom={bx['bottom']:>7}")

    print("=" * 78)
    mm = r["M9_motion"]
    print("M9 duration histogram:", mm["light"]["durationHistogram"])
    print("   timing histogram:", mm["light"]["timingHistogram"])
    print("   animations:", mm["light"]["animations"])
    print("   reduced-motion: elementsWithMotion=", mm["reduced"]["elementsWithMotion"],
          "mediaMatches=", mm["reduced"]["mediaMatches"])
    for s in mm["reduced"]["samples"]:
        print("    ", s)

    print("=" * 78)
    sc = r["M10_scheme"]
    print("M10 light:", json.dumps(sc["light"], ensure_ascii=False))
    print("    dark :", json.dumps(sc["dark"], ensure_ascii=False))
    print("=" * 78)
    print("pageErrors:", r["pageErrors"], "posts:", r["posts"])
    print("JSON ->", OUT / "measure.json")


if __name__ == "__main__":
    main()
