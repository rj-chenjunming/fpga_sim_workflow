#!/usr/bin/env python3
"""3C 共命中证据（只读）：在受控夹具的多个 UI 状态下，为每个选择器求
`document.querySelectorAll(sel)` 的命中集合，输出「同一元素被两个选择器命中」的
**运行时 DOM 共命中**证据。

用途（证据边界，别过度声称）：
  · 它回答的是「选择器 A 与 B 在**这些受控状态**下是否真的落到同一个元素上」；
    共命中 ⇒ 两者的声明可能在同一元素上竞争（搬动/合并时会互相影响）；
  · 不共命中 ⇒ 在**已覆盖状态**下找不到同一个元素，不等于「全状态全断点永不互相影响」；
  · 它不是静态级联判据的替代，只是判据里的「可能命中」这一步的运行时下界证据。

关键设计（不这么做证据会假绿）：
  1. **先去交互态再匹配**：无真实指针时 `querySelectorAll(':hover')` 恒为 0，会把
     「只在 hover/focus 下才生效的竞争规则」误判成「永不共命中」。因此先 sanitize：
     剥掉交互态伪类 `:hover/:focus/:focus-visible/:focus-within/:active` 与伪元素
     `::before/::after/::selection/:before/:after/...`（querySelectorAll 匹配不到伪元素；
     伪元素之间的互斥由静态判据处理）。**保留**结构性/静态伪类（`:disabled`、`:checked`、
     `:first-child`、`:empty`、`:not(...)`、`:nth-*` 等，它们能静态命中）。
     剥掉的动作与结果逐条记在输出的 `selector_sanitized` / `sanitize_notes` 里，可复核。
  2. **稳定 key**：元素用 WeakMap 自增 id + 结构化路径（tag#id:nth-of-type>...），
     同一状态快照内同一个元素只会有一个 key。
  3. **空扫自检**：每个状态必须满足「元素总数 > 100」且「`.btn` / `header` / `.rail-entry`
     里至少 2 个命中数 > 0」，否则该状态采集判为不可信（exit 1），不许拿空扫当「不共命中」。
  4. **blocked_pairs 逐对回填**：输入文件里的每一对竞争选择器都在输出里给出
     `co_match` 是否出现（出现则给 count + 样例 class 列表），并给 pairs_checked /
     co_match_pairs 计数，便于复核「哪些对被证伪/证实」。

输入（lead 生成）：`--selectors` JSON：{"selectors": [...], "blocked_pairs": [[a, b], ...]}
输出：`--out` JSON（默认同目录 cooccur.json）。

用法：
    R=/home/work/chenjunming/change-impact-loop
    cd $R/loop
    PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
      .venv/bin/python $R/.ui-audit/3c/cooccur.py \
        --web $R/.ui-audit/3c/snap-harness-same \
        --selectors $R/.ui-audit/3c/cooccur-selectors.json \
        --out $R/.ui-audit/3c/cooccur.json
    # 两次稳定性对比（同一 web 目录跑两次后）：
    #   .venv/bin/python .ui-audit/3c/cooccur.py --check-stable cooccur-a.json

退出码：0=采集成功且空扫自检通过；1=空扫自检失败/稳定性对比不一致/断言失败；2=输入或启动失败。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from collect_f14a import MockApi  # noqa: E402
from verify_style_equivalence import (  # noqa: E402
    MAIN_VIEWPORTS, goto_state, serve_dir, settle, wait_js,
)

# 与交付 1（verify_style_equivalence.py）相同的状态集 + 额外尽量覆盖的态。
BASE_STATES = ("s0", "setup", "run", "gate", "dirpicker", "agent", "node-detail",
               "empty", "legacy")
EXTRA_STATES = ("toast", "alert", "gate-empty")   # 真实交互/错误态，见 apply_state
ALL_STATES = BASE_STATES + EXTRA_STATES

# 空扫自检：每状态至少 2 个必须命中的选择器 > 0，且元素总数 > 100。
SCAN_PROBES = (".btn", "header", ".rail-entry")
SCAN_MIN_PROBE_HITS = 2
SCAN_MIN_ELEMENTS = 100

# 工具附加的元素探针：输入选择器文件是「CSS 规则选择器」清单，不含裸元素选择器，
# 但「button 规则与 .btn 规则是否落到同一个元素」正是最典型的互相影响证据，
# 因此固定附加这两个探针（输出里用 probe_selectors 标出来，不混进输入清单）。
PROBE_SELECTORS = ("button", "#btnS0")

# --selfcheck 用的固定断言对（2026-10-30 在本仓受控夹具上实测确认）：
#   5 个必然共命中（含 1 个跨 sanitize 的对：.btn-ghost:hover 剥成 .btn-ghost 后与静态版共命中）
CO_MATCH_EXPECT = ((".btn", "button"), (".rail-entry", "#btnS0"), (".btn", ".btn-sm"),
                   (".btn-ghost", ".btn-ghost:hover"), (".btn", ".btn:disabled"))
#   3 个必然不共命中（不同元素，且两者都在输入选择器清单里 ⇒ 不是「没测量」的假阴性）
NO_CO_MATCH_EXPECT = ((".dp-list", ".rail-entry"), (".run-item", ".agent-open"),
                      (".aw-layout", ".aw-intervene"))

INTERACTIVE_PSEUDOS = ("focus-visible", "focus-within", "hover", "focus", "active")
PSEUDO_ELEMENTS = ("before", "after", "selection", "marker", "placeholder",
                   "first-line", "first-letter", "backdrop", "file-selector-button",
                   "cue", "part", "slotted")

_JS_COLLECT = r"""
(selectors) => {
  const KEYS = new WeakMap();
  let next = 0;
  const pathOf = (el) => {
    const parts = [];
    let cur = el, depth = 0;
    while (cur && cur.nodeType === 1 && depth < 5) {
      let s = cur.tagName.toLowerCase();
      if (cur.id) s += '#' + cur.id;
      const p = cur.parentElement;
      if (p) {
        const same = Array.from(p.children).filter(c => c.tagName === cur.tagName);
        if (same.length > 1) s += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')';
      }
      parts.unshift(s);
      cur = p;
      depth++;
    }
    return parts.join('>');
  };
  const out = {selectors: {}, errors: {}, element_total: 0};
  out.element_total = document.querySelectorAll('body *').length;
  for (const sel of selectors) {
    let list;
    try {
      list = document.querySelectorAll(sel);
    } catch (e) {
      out.errors[sel] = String(e && e.name ? e.name : e);
      out.selectors[sel] = [];
      continue;
    }
    const rows = [];
    for (const el of list) {
      let id = KEYS.get(el);
      if (id === undefined) { id = 'e' + (++next); KEYS.set(el, id); }
      rows.push({
        key: id,
        path: pathOf(el),
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').trim(),
        id_attr: el.id || '',
      });
    }
    out.selectors[sel] = rows;
  }
  return out;
}
"""


# --------------------------------------------------------------------------- #
# 选择器 sanitize（去交互态 / 去伪元素）
# --------------------------------------------------------------------------- #
def sanitize_selector(selector):
    """剥掉交互态伪类与伪元素；返回 (sanitized, notes)。剥不干净就如实报告。"""
    text = selector
    notes = []
    for pe in sorted(PSEUDO_ELEMENTS, key=len, reverse=True):
        pattern = re.compile(r"::?" + re.escape(pe) + r"\b")
        if pattern.search(text):
            notes.append("pseudo-element :%s 已剥" % pe)
            text = pattern.sub("", text)
    for pc in sorted(INTERACTIVE_PSEUDOS, key=len, reverse=True):
        # 允许写成 :hover 或 :hover(...)（虽然后者少见），一并剥
        pattern = re.compile(r":" + re.escape(pc) + r"\b(\([^()]*\))?")
        if pattern.search(text):
            notes.append("交互态 :%s 已剥（querySelectorAll 恒不命中）" % pc)
            text = pattern.sub("", text)
    text = re.sub(r"\(\s*\)", "", text)           # :not()/:where() 剥空壳
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"(\s*[>+~]\s*)+$", "", text).strip()   # 尾部残留组合符
    if not text:
        notes.append("剥完后为空（原有选择器只表达交互态/伪元素）")
    return text, notes


def describe(el):
    """样例可读描述：优先 class 列表，其次 tag#id。"""
    if el.get("cls"):
        return el["cls"]
    return "%s%s" % (el.get("tag", "?"), ("#" + el["id_attr"]) if el.get("id_attr") else "")


# --------------------------------------------------------------------------- #
# 状态驱动：与交付 1 同一受控夹具，另外补 toast / role=alert / dialog 打开态
# --------------------------------------------------------------------------- #
def apply_state(page, api, static_url, state):
    """切到 state。基础/交互态复用 verify 的 goto_state；额外态在此实现。"""
    if state in BASE_STATES:
        goto_state(page, api, static_url, state)
        return {}
    if state == "toast":                      # 真实 toast 可见态（基线 setup 的刷新基线）
        goto_state(page, api, static_url, "setup")
        wait_js(page, "() => !!document.querySelector('#toast.show')", "toast 可见")
        return {"toast_text": page.evaluate(
            "() => { const t = document.querySelector('#toast');"
            " return t ? t.innerText.trim() : null; }")}
    if state == "alert":                      # role=alert 错误态：#s0Error 里出现 .alert.bad
        goto_state(page, api, static_url, "s0")
        # POST 提交失败（受控替身回 500）→ s0.js error() → #s0Error[role=alert] 渲染 .alert.bad
        page.route("**/api/s0/from-rtl", lambda route: route.fulfill(
            status=500, json={"detail": {"error": "受控替身：派生失败（cooccur 夹具）"}}))
        page.fill("#s0Rtl", "/fixture/RTL")
        page.click("#s0Prepare")
        wait_js(page, "() => { const e = document.querySelector('#s0Error .alert');"
                      " return !!e && e.innerText.trim().length > 0; }", "S0 错误态")
        return {"alert_text": page.evaluate(
            "() => { const e = document.querySelector('#s0Error .alert');"
            " return e ? e.innerText.trim() : null; }")}
    if state == "gate-empty":                 # 闸门视图未选运行 → .alert.info 提示
        goto_state(page, api, static_url, "s0")
        page.locator("#segGate").click()
        wait_js(page, "() => { const a = document.querySelector('#gateAlerts .alert');"
                      " return !!a && a.innerText.trim().length > 0; }", "闸门空态提示")
        return {"alert_text": page.evaluate(
            "() => { const a = document.querySelector('#gateAlerts .alert');"
            " return a ? a.innerText.trim() : null; }")}
    raise ValueError(state)


def collect_side(browser, static_url, states, selectors_by_state):
    """返回 (records, order)：records[state] = {selectors: {...}, element_total: n}。"""
    records = {}
    by_viewport = defaultdict(list)
    for width, height, state in states:
        by_viewport[(width, height)].append(state)
    for (width, height) in sorted(by_viewport):
        context = browser.new_context(viewport={"width": width, "height": height},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        for state in by_viewport[(width, height)]:
            page.goto(static_url)
            page.wait_for_selector(".run-item", timeout=10000)
            extra = apply_state(page, api, static_url, state)
            settle(page)
            data = page.evaluate(_JS_COLLECT, selectors_by_state[state])
            data["extra"] = extra
            key = "%dx%d/%s" % (width, height, state)
            records[key] = data
            print("  collected %-24s elements=%-5d selectors=%d hits=%d" % (
                key, data["element_total"], len(selectors_by_state[state]),
                sum(len(v) for v in data["selectors"].values())), flush=True)
        page.close()
        context.close()
    return records


def build_report(records, order, selectors, sanitized, notes, invalid, blocked_pairs):
    """汇总 co_match（只保留 count>0 的对）与各口径命中数。"""
    co_count = defaultdict(int)
    co_sample = {}
    selector_counts = {sel: 0 for sel in selectors}
    counts_by_state = {}
    state_totals = {}
    zero_by_state = {}
    invalid_hits = defaultdict(int)

    for state in order:
        data = records[state]
        state_totals[state] = data["element_total"]
        counts_by_state[state] = {sel: len(data["selectors"].get(sel) or [])
                                  for sel in selectors}
        zero_by_state[state] = [sel for sel in selectors
                                if not data["selectors"].get(sel)]
        for sel in selectors:
            selector_counts[sel] += len(data["selectors"].get(sel) or [])
        for sel, err in data.get("errors", {}).items():
            invalid_hits[sel] += 1
        # 反查：元素 key → 命中它的选择器集合
        per_element = defaultdict(set)
        element_desc = {}
        for orig in selectors:
            for row in data["selectors"].get(orig) or []:
                per_element[row["key"]].add(orig)
                element_desc.setdefault(row["key"], (row, state))
        for key, origs in per_element.items():
            if len(origs) < 2:
                continue
            ordered = sorted(origs)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    pair = (ordered[i], ordered[j])
                    co_count[pair] += 1
                    if pair not in co_sample:
                        row, st = element_desc[key]
                        co_sample[pair] = {"state": st, "path": row["path"],
                                           "class": describe(row)}

    co_match = []
    for (a, b), count in sorted(co_count.items()):
        sample = co_sample[(a, b)]
        co_match.append({"a": a, "b": b, "count": count,
                         "sample": sample["class"],
                         "sample_state": sample["state"],
                         "sample_path": sample["path"],
                         "a_sanitized": sanitized[a], "b_sanitized": sanitized[b]})
    co_pairs = {(item["a"], item["b"]) for item in co_match}

    blocked = []
    measured_set = set(selectors)
    unmeasured = 0
    for a, b in blocked_pairs:
        if a not in measured_set or b not in measured_set:
            # 不能把「没测量」记成「不共命中」：这两种情况的证据力完全不同。
            unmeasured += 1
            blocked.append({"a": a, "b": b, "co_match": False, "count": 0,
                            "measured": False,
                            "note": "至少一方不在被测选择器集合里 ⇒ 未测量，不能当作「不共命中」"})
            continue
        key = (a, b) if (a, b) in co_pairs else ((b, a) if (b, a) in co_pairs else None)
        hit = co_count.get(key, 0) if key else 0
        entry = {"a": a, "b": b, "co_match": bool(hit), "count": hit, "measured": True}
        if key:
            entry.update({"sample": co_sample[key]["class"],
                          "sample_state": co_sample[key]["state"],
                          "sample_path": co_sample[key]["path"]})
        blocked.append(entry)

    zero_hit = [sel for sel in selectors if selector_counts[sel] == 0]
    probe_report = {}
    states_untrusted = []
    for state in order:
        counted = {sel: counts_by_state[state][sel] for sel in SCAN_PROBES
                   if sel in selectors}
        hits = sum(1 for value in counted.values() if value > 0)
        ok = (state_totals[state] > SCAN_MIN_ELEMENTS and hits >= SCAN_MIN_PROBE_HITS)
        probe_report[state] = {"element_total": state_totals[state],
                               "probe_hits": counted,
                               "probes_hit": hits, "trusted": ok}
        if not ok:
            states_untrusted.append(state)

    return {
        "states": order,
        "state_element_totals": state_totals,
        "state_extras": {state: (records[state].get("extra") or {}) for state in order},
        "selector_counts": selector_counts,
        "selector_counts_by_state": counts_by_state,
        "zero_hit_selectors": zero_hit,
        "zero_hit_by_state": zero_by_state,
        "selector_sanitized": sanitized,
        "sanitize_notes": notes,
        "invalid_selectors": invalid,
        "invalid_selector_errors": dict(invalid_hits),
        "co_match": co_match,
        "co_match_pair_count": len(co_match),
        "pairs_checked": len(selectors) * (len(selectors) - 1) // 2,
        "blocked_pairs": blocked,
        "blocked_pairs_checked": len(blocked_pairs),
        "blocked_pairs_co_match": sum(1 for item in blocked if item["co_match"]),
        "blocked_pairs_unmeasured": unmeasured,
        "empty_scan_selfcheck": {
            "probes": list(SCAN_PROBES), "min_probe_hits": SCAN_MIN_PROBE_HITS,
            "min_elements": SCAN_MIN_ELEMENTS, "per_state": probe_report,
            "untrusted_states": states_untrusted,
        },
        "notes": {
            "selector_total": len(selectors),
            "state_total": len(order),
            "co_match_semantics": "count = 命中同一元素（同一状态）的 (状态, 元素) 次数；"
                                  "只输出 count>0 的对；不共命中≠全态永不互相影响",
            "sanitize_semantics": "交互态伪类与伪元素在匹配前被剥掉（querySelectorAll 对它们"
                                  "恒/必然不命中），因此命中集合是「该规则目标元素」的上界近似",
        },
    }


def check_stable(path_a, path_b):
    """两次运行稳定性：co_match 集合 + 每选择器命中数必须一致。返回 (ok, detail)。"""
    a = json.loads(Path(path_a).read_text(encoding="utf-8"))
    b = json.loads(Path(path_b).read_text(encoding="utf-8"))
    set_a = {(item["a"], item["b"]) for item in a["co_match"]}
    set_b = {(item["a"], item["b"]) for item in b["co_match"]}
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    counts_diff = {sel: (a["selector_counts"].get(sel), b["selector_counts"].get(sel))
                   for sel in set(a["selector_counts"]) | set(b["selector_counts"])
                   if a["selector_counts"].get(sel) != b["selector_counts"].get(sel)}
    ok = not only_a and not only_b and not counts_diff
    detail = {"co_match_only_in_a": only_a[:10], "co_match_only_in_b": only_b[:10],
              "co_match_count_a": len(set_a), "co_match_count_b": len(set_b),
              "selector_count_diffs": dict(list(counts_diff.items())[:10]),
              "selector_count_diff_total": len(counts_diff)}
    return ok, detail


def run_selfcheck(report):
    """判别性自检：3 个必然共命中 + 3 个必然不共命中，且空扫自检必须 trusted。"""
    pairs = {(item["a"], item["b"]) for item in report["co_match"]}
    lines = []
    ok = True
    for a, b in CO_MATCH_EXPECT:
        hit = (a, b) in pairs or (b, a) in pairs
        entry = next((item for item in report["co_match"]
                      if {item["a"], item["b"]} == {a, b}), None)
        lines.append("%s 必然共命中 %-28s %-18s count=%s sample=%r" % (
            "PASS" if hit else "FAIL", a, b,
            entry["count"] if entry else 0, entry["sample"] if entry else None))
        ok = ok and hit
    for a, b in NO_CO_MATCH_EXPECT:
        hit = (a, b) in pairs or (b, a) in pairs
        lines.append("%s 必然不共命中 %-26s %-18s（出现在 co_match=%s）" % (
            "FAIL" if hit else "PASS", a, b, hit))
        ok = ok and not hit
    untrusted = report["empty_scan_selfcheck"]["untrusted_states"]
    lines.append("%s 空扫自检：%d 个状态中 %d 个不可信 %s" % (
        "PASS" if not untrusted else "FAIL", len(report["states"]),
        len(untrusted), untrusted))
    ok = ok and not untrusted
    lines.append("PASS 共命中对 %d 个 / 已检查对 %d 个；选择器 %d 个，其中 0 命中 %d 个" % (
        report["co_match_pair_count"], report["pairs_checked"],
        report["notes"]["selector_total"], len(report["zero_hit_selectors"])))
    return ok, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", default=None,
                        help="被测 web 目录（含 index.html）；--check-stable 模式不需要")
    parser.add_argument("--selectors", default=str(HERE / "cooccur-selectors.json"),
                        help="选择器输入 JSON（默认同目录 cooccur-selectors.json）")
    parser.add_argument("--out", default=str(HERE / "cooccur.json"), help="输出 JSON")
    parser.add_argument("--selfcheck", action="store_true",
                        help="跑 3 必共命中 + 3 必不共命中断言（并打印空扫自检）")
    parser.add_argument("--check-stable", metavar="OTHER_JSON", default=None,
                        help="与另一次运行的 JSON 比较 co_match 集合与命中数，退出码=是否一致")
    args = parser.parse_args(argv)

    if args.check_stable:
        ok, detail = check_stable(args.out, args.check_stable)
        print(json.dumps(detail, ensure_ascii=False))
        print(("PASS" if ok else "DIFF") + ": co_match 集合与逐选择器命中数%s" %
              ("完全一致" if ok else "不一致"))
        return 0 if ok else 1

    if not args.web:
        print("采集模式必须给 --web", file=sys.stderr)
        return 2
    web = Path(args.web).resolve()
    if not (web / "index.html").exists():
        print("缺少 index.html：%s" % web, file=sys.stderr)
        return 2
    input_path = Path(args.selectors).resolve()
    if not input_path.exists():
        print("缺少选择器输入：%s（先用 --selectors 指定）" % input_path, file=sys.stderr)
        return 2
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    selectors = []
    for sel in raw.get("selectors") or []:
        if isinstance(sel, str) and sel.strip() and sel not in selectors:
            selectors.append(sel.strip())
    blocked_raw = [tuple(pair) for pair in (raw.get("blocked_pairs") or [])
                   if isinstance(pair, (list, tuple)) and len(pair) == 2]
    blocked_pairs = []
    for pair in blocked_raw:
        if pair not in blocked_pairs:
            blocked_pairs.append(pair)
    if not selectors:
        print("选择器文件里没有可用选择器：%s" % input_path, file=sys.stderr)
        return 2

    probe_selectors = [sel for sel in PROBE_SELECTORS if sel not in selectors]
    measured = selectors + probe_selectors

    sanitized = {}
    notes = {}
    for sel in measured:
        text, note = sanitize_selector(sel)
        sanitized[sel] = text
        notes[sel] = note
    # 每个状态实际执行的选择器集合 = 去重后的 sanitized 文本（不含空串）。
    match_selectors = sorted({sanitized[sel] for sel in measured
                              if sanitized[sel]})
    invalid = [sel for sel in measured if not sanitized[sel]]
    by_state_selectors = {state: match_selectors for state in ALL_STATES}

    from playwright.sync_api import sync_playwright

    server, thread, url = serve_dir(web)
    states = [(width, height, state) for (width, height) in MAIN_VIEWPORTS
              for state in ALL_STATES]
    try:
        with sync_playwright() as pw:
            executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
            browser = pw.chromium.launch(
                **({"executable_path": executable} if executable else {}))
            print("web=%s" % web)
            print("状态数=%d（%d 视口 × %d 状态）；选择器 %d 个（匹配用 %d 个）" % (
                len(states), len(MAIN_VIEWPORTS), len(ALL_STATES),
                len(selectors), len(match_selectors)))
            try:
                records = collect_side(browser, url, states, by_state_selectors)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    order = ["%dx%d/%s" % (width, height, state) for (width, height) in MAIN_VIEWPORTS
             for state in ALL_STATES]
    # 把「匹配用文本」的命中映射回「原始选择器」
    original_of = defaultdict(list)
    for sel in measured:
        if sanitized[sel]:
            original_of[sanitized[sel]].append(sel)
    rekeyed = {}
    for state, data in records.items():
        mapped = {"selectors": {}, "errors": {}, "element_total": data["element_total"],
                  "extra": data.get("extra") or {}}
        for match_sel, error in (data.get("errors") or {}).items():
            for orig in original_of.get(match_sel, []):
                mapped["errors"][orig] = error
        for match_sel, rows in data["selectors"].items():
            for orig in original_of.get(match_sel, []):
                mapped["selectors"][orig] = rows
        # 原始选择器里剥成空串的：显式记为 0 命中（不静默消失）
        for orig in invalid:
            mapped["selectors"][orig] = []
        rekeyed[state] = mapped

    report = build_report(rekeyed, order, measured, sanitized, notes, invalid,
                          blocked_pairs)
    report["probe_selectors"] = list(probe_selectors)
    report["note_probe_selectors"] = ("工具附加的元素探针（不在输入文件里）：button / #btnS0；"
                                      "它们参与 co_match，只为把「元素选择器 vs 类选择器」"
                                      "这类竞争纳入证据，不计入输入清单口径")
    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = {
        "web": str(web), "selectors": str(input_path), "out": str(out),
        "states": len(order), "selector_total": len(measured),
        "input_selector_total": len(selectors), "probe_selectors": list(probe_selectors),
        "invalid_selectors": len(invalid),
        "zero_hit_selectors": len(report["zero_hit_selectors"]),
        "co_match_pair_count": report["co_match_pair_count"],
        "pairs_checked": report["pairs_checked"],
        "blocked_pairs_checked": report["blocked_pairs_checked"],
        "blocked_pairs_co_match": report["blocked_pairs_co_match"],
        "untrusted_states": report["empty_scan_selfcheck"]["untrusted_states"],
    }
    print(json.dumps(summary, ensure_ascii=False))

    ok = True
    if args.selfcheck:
        ok, lines = run_selfcheck(report)
        for line in lines:
            print(line)
    untrusted = report["empty_scan_selfcheck"]["untrusted_states"]
    if untrusted:
        print("FAIL: 空扫自检不可信状态 %s（这些状态不能当「不共命中」证据）" % untrusted)
        return 1
    print(("PASS" if ok else "DIFF") + ": 共命中证据采集完成")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
