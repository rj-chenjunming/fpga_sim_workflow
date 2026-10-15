#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n5_impact.py —— N5 两级影响分析（Host 确定性，spec §2 N5 / §10.3；schema = kb/schema/n5_impact.schema.json）

两级（宁多勿漏）
    一级 段级粗筛：把 N2 diff 触及的 RTL 文件用 `kb/index/segment_rtl.json` 映射到**候选段**
                  （文件未映射 ⇒ 8 段全部进候选，宁可多不可漏）
    二级 offset/位域交集：diff 触及的 offset（①路 hunk 字面量换算 `<段基址>+<块内偏移>` +
                  ③路 `entry_id` 的 `offset_global`）∩ 用例实际访问的 offset
                  （`kb/index/case_access.json` 的 B1 定向 / B2 大范围站点）
    ⇒ 【必改】（offset 直接命中且位域可判定）/【待查】（只段级命中，或位域不确定）

硬口径
    * 8 个已登记段全覆盖：`0x0000/0x0100/0x0600/0x0800/0x0A00/0x0D00/0x2000/0x4000`；
      `segments_covered` 条数自检 ≥ 8（schema minItems=8）。
    * `0x8000` / `0x10000` **只打标记不建映射**：命中也只写 `marked_only_segments` +
      `index_gaps[kind=marked-only-segment]`，绝不产出【必改】/【待查】条目。
    * 位域不确定：`regEntry.bitdef_present=false` ⇒ 进【待查】（本脚本把它写进 n5_impact.md 口径说明）。
    * **索引缺失 ⇒ `index_complete=false` 且 rc!=0**：不许静默给空清单。
    * 门禁：默认强制 G1 = signed + `confirmed` 且 `human_signed=true`（验证者"跳过 G1 直接跑 N5"
      必须被拒 rc!=0）；演练链用 `--allow-rehearsal` 显式放行（human_signed 仍如实记录为 false）。
    * `generated_at` 是唯一被允许的非确定性字段（README §3.1.1，本脚本声明时间字段
      `("generated_at",)`）：一律经 `kb_lib.now_iso()`，`--now`/`KB_NOW` 注入。
      强判据 = 同一输入 + 同一 `--now` 两次逐字节相同；
      弱判据 = 不同 `--now` 两次，`K.sha256_obj_normalized(obj, ("generated_at",))` 相同。

退出码
    0 成功（index_complete=true）／ 2 用法 ／ 3 门禁未过或存在 blocking 索引缺口 ／ 4 self-check 失败
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

RC_OK = 0
RC_USAGE = 2
RC_BLOCK = 3
RC_SELFCHECK = 4

SCHEMA_NAME = "n5_impact"
SCHEMA_JSON = "kb/schema/n5_impact.schema.json"

# README §3.2：首版 8 个已登记段（全覆盖）
# 注意：schema 的段字面量 pattern 是 ^0x[0-9a-f]{4,5}$（**小写十六进制**），
# 所以 0x0A00/0x0D00 在本脚本的报告里写成 0x0a00/0x0d00（README §3.2 的 0x0A00/0x0D00 是同一段）。
REGISTERED = ("0x0000", "0x0100", "0x0600", "0x0800", "0x0a00", "0x0d00", "0x2000", "0x4000")
# README §3.2：只打标记不建映射
MARKED_ONLY = ("0x8000", "0x10000")

B1, B2, B3 = "B1", "B2", "B3"

HEXDIGITS = re.compile(r"^0x[0-9a-f_]+$", re.I)


def seg_str(v):
    return "0x%04x" % v if v <= 0xFFFF else "0x%05x" % v


def canon_seg(s):
    """段字面量规范化成 schema 要求的**小写**十六进制（0x0D00 -> 0x0d00）。"""
    v = parse_int(s)
    return None if v is None else seg_str(v)


def parse_int(s):
    if s is None:
        return None
    if isinstance(s, int):
        return s
    t = str(s).strip().lower().replace("_", "")
    if not t:
        return None
    if t.startswith("0x"):
        try:
            return int(t, 16)
        except ValueError:
            return None
    if t.startswith("0b"):
        try:
            return int(t, 2)
        except ValueError:
            return None
    try:
        return int(t, 10)
    except ValueError:
        return None


def canon_hex(s):
    """offset/地址字面量规范化成 `0x<小写十六进制>`；不可解析返回 None。"""
    v = parse_int(s)
    return None if v is None else "0x%x" % v


class InputGap(Exception):
    pass


# ---------------------------------------------------------------- 输入

def load_json_checked(path, schema_name, where, gaps, kind_for_gap):
    """读 JSON + `kb_lib.check` 校验；缺失或不合 schema ⇒ blocking 索引缺口。"""
    if not os.path.exists(path):
        gaps.append({"kind": kind_for_gap, "blocking": True,
                     "detail": "%s 不存在：%s" % (where, K.relpath(path)),
                     "action": "转人工：先生成/补齐 %s" % K.relpath(path)})
        return None
    try:
        obj = K.read_json(path)
    except ValueError as e:
        gaps.append({"kind": kind_for_gap, "blocking": True,
                     "detail": "%s 不是合法 JSON（%s）：%s" % (where, e, K.relpath(path)),
                     "action": "转人工：修 %s 后重跑 n5_impact.py" % K.relpath(path)})
        return None
    errs = K.validate(obj, K.load_schema(schema_name))
    if errs:
        gaps.append({"kind": kind_for_gap, "blocking": True,
                     "detail": "%s 不合 kb/schema/%s.schema.json：%s"
                               % (where, schema_name, " | ".join(errs[:6])),
                     "action": "转人工：把 schema 校验错误交对应生成脚本 owner（n1_case_scan/n1_doc_entries）修"})
        return None
    return obj


def gate_precondition(path, allow_rehearsal):
    """spec I1：G1 已签且 confirmed 才允许进入 N5。"""
    if not os.path.exists(path):
        return ({"gate": "G1_diff_confirm", "signed": False, "decision": "MISSING",
                 "actor_kind": "host", "human_signed": False, "enforced": True,
                 "note": "闸门状态不存在：%s ⇒ 拒绝进入 N5（先 gate.py init）" % K.relpath(path)},
                False)
    st = K.read_json(path)
    g = (st.get("gates") or {}).get("G1_diff_confirm")
    if not isinstance(g, dict):
        return ({"gate": "G1_diff_confirm", "signed": False, "decision": "MISSING",
                 "actor_kind": "host", "human_signed": False, "enforced": True,
                 "note": "gates.json 缺 G1_diff_confirm 条目 ⇒ 拒绝进入 N5"}, False)
    signed = g.get("status") == "signed" and g.get("decision") != "pending"
    decision = str(g.get("decision"))
    actor_kind = g.get("actor_kind") or "host"
    if actor_kind not in ("human", "rehearsal", "host", "model"):
        actor_kind = "host"
    human_signed = bool(g.get("human_signed"))
    # F-GATE-01（task-19，同源缺口）：`--allow-rehearsal` **只对 actor_kind=rehearsal 生效**；
    # 否则 actor_kind=model 可借该开关在**无人签署**的情况下进入 N5（I6 被绕过）。
    rehearsal_bypass = bool(allow_rehearsal) and actor_kind == "rehearsal"
    ok = signed and decision == "confirmed" and (human_signed or rehearsal_bypass)
    why = []
    if not signed:
        why.append("未签署（status=%s decision=%s）" % (g.get("status"), decision))
    if decision != "confirmed":
        why.append("决策不是 confirmed（实际 %r）" % decision)
    if not human_signed and not rehearsal_bypass:
        why.append("human_signed=false（actor_kind=%s）⇒ 只有 actor_kind=rehearsal 才能用 "
                   "--allow-rehearsal 放行演练链；model/host 一律拒绝" % actor_kind)
    pre = {"gate": "G1_diff_confirm", "signed": bool(signed), "decision": decision,
           "actor_kind": actor_kind, "human_signed": human_signed, "enforced": True,
           "note": ("G1 已确认：actor=%s actor_kind=%s human_signed=%s"
                    % (g.get("actor"), actor_kind, human_signed)) if ok
           else "禁止进入 N5：" + "；".join(why)}
    return pre, ok


# ---------------------------------------------------------------- 索引装载

def mapping_index(segment_rtl):
    """path -> [(segment, {lines, level, verified, evidence_text})]；跳过 marked-only 段。"""
    idx = {}
    segs = []
    for m in segment_rtl.get("mappings", []):
        seg = canon_seg(m.get("segment")) or str(m.get("segment"))
        if seg in MARKED_ONLY:
            continue
        segs.append(seg)
        for f in m.get("rtl_files", []) or []:
            p = str(f.get("path"))
            idx.setdefault(p, []).append((seg, {
                "lines": f.get("lines"), "level": f.get("level"),
                "verified": bool(f.get("verified")), "evidence_text": f.get("evidence_text")}))
    for p in idx:
        idx[p].sort(key=lambda t: (t[0], str(t[1].get("lines"))))
    return idx, sorted(set(segs))


def all_bases(segments):
    out = set()
    for s in segments:
        v = parse_int(s)
        if v is not None:
            out.add(v)
    out.update(parse_int(s) for s in REGISTERED)
    return sorted(v for v in out if v is not None)


def segment_of(addr, bases):
    if addr is None:
        return None
    cands = [b for b in bases if b <= addr]
    if not cands:
        return None
    return seg_str(max(cands))


def project_bitdef(rec):
    """从 doc_entry diff 的 before/after 投影 JSON 里取 bitdef_present（位域可判定性）。"""
    for key in ("after", "before"):
        s = rec.get(key)
        if not s:
            continue
        try:
            obj = json.loads(s)
        except ValueError:
            continue
        if isinstance(obj, dict) and "bitdef_present" in obj:
            return obj.get("bitdef_present")
    return None


def regmap_index(regmap):
    """(segment, offset_global) -> {entry_id, bitdef_present}；用于把 ① 路抽出的 offset 也接到
    文档位定义表上（`bitdef_present` 决定【必改】/【待查】）。regmap 缺失不阻塞（只降级为待查）。"""
    idx = {}
    for e in regmap.get("entries", []) or []:
        seg = canon_seg(e.get("segment"))
        if not seg:
            continue
        offs = [canon_hex(e.get("offset_global"))]
        eid = e.get("entry_id")
        if isinstance(eid, str) and "#" in eid:
            offs.append(canon_hex(eid.split("#", 1)[1]))
        for off in offs:
            if off:
                idx[(seg, off)] = {"entry_id": eid,
                                   "bitdef_present": bool(e.get("bitdef_present"))}
    return idx


def collect_touched(n2, map_idx, bases, gaps, notes, regmap_idx=None):
    """→ (candidates: {seg: {...}}, offsets: {seg: [entry...]}, touched_files)"""
    candidates = {}
    offsets = {}
    touched_files = []
    unmapped = []
    seen_unresolved = set()

    def add_cand(seg, reason, evidence):
        c = candidates.setdefault(seg, {"seg": seg, "reasons": [], "rtl_files": [],
                                        "segment_evidence": []})
        if reason not in c["reasons"]:
            c["reasons"].append(reason)
        if evidence and evidence not in c["segment_evidence"]:
            c["segment_evidence"].append(evidence)

    def add_off(seg, global_v, local_v, entry_id, bitdef, diff_id, kind):
        if global_v is None:
            return
        key = "0x%x" % global_v
        if entry_id is None and regmap_idx:
            hit = regmap_idx.get((seg, key))
            if hit:
                entry_id = hit["entry_id"]
                bitdef = hit["bitdef_present"]
        for o in offsets.setdefault(seg, []):
            if o["value"] == key and o["entry_id"] == entry_id:
                return
        offsets[seg].append({"value": key, "local": ("0x%x" % local_v) if local_v is not None else None,
                             "entry_id": entry_id, "bitdef_present": bitdef,
                             "diff_id": diff_id, "kind": kind})

    for rec in n2.get("diffs", []):
        kind = rec.get("kind")
        rid = str(rec.get("id"))
        if kind in ("rtl_file", "allfile"):
            touched_files.append((kind, rid))
            maps = map_idx.get(rid)
            if maps:
                for seg, info in maps:
                    ev = ("kb/index/segment_rtl.json %s ← %s:%s(verified=%s)%s"
                          % (seg, rid, info.get("lines"), info.get("verified"),
                             (" " + str(info["evidence_text"])) if info.get("evidence_text") else ""))
                    add_cand(seg, "%s diff 触及 %s（段↔RTL 映射命中）" % (kind, rid), ev)
                    if info.get("verified") is not True:
                        gaps.append({"kind": "rtl_file", "blocking": False,
                                     "detail": "%s 的段映射未经 grep 复验（verified!=true）：%s"
                                               % (rid, seg),
                                     "action": "转人工：请 case-kb 复验 %s:%s 原文" % (rid, info.get("lines"))})
                    for v in rec.get("offsets", []) or []:
                        lv = parse_int(v)
                        if lv is None:
                            continue
                        base = parse_int(seg) or 0
                        # 块内偏移 ⇒ 全局地址；同时保留“字面量本身已是全局地址”的候选（宁多勿漏）
                        add_off(seg, base + lv, lv, None, None, rid, kind)
                        if lv != base + lv:
                            add_off(seg, lv, lv, None, None, rid, kind + "+literal-as-global")
                    c = candidates[seg]
                    if rid not in c["rtl_files"]:
                        c["rtl_files"].append(rid)
                # 未抽出 offset 的说明**每条 diff 只登记一次**（此前放在每段映射循环里，
                # 同一文件映射到多段时会重复追加——lead Q1 实测的那两条重复）
                if rec.get("unresolved") and not rec.get("offsets"):
                    msg = "%s（%s）未抽出 offset：%s" % (rid, kind, rec.get("unresolved"))
                    if kind == "rtl_file":
                        if msg not in seen_unresolved:
                            seen_unresolved.add(msg)
                            gaps.append({"kind": "offset", "blocking": False, "detail": msg,
                                         "action": "转人工：按 diff_hunk/交付包定位 offset 后补 n5 输入"})
                    elif msg not in notes:
                        # ② 路只比 md5，无 hunk 是**设计如此**，offset 由 ①/③ 路提供 ⇒ 只记说明
                        notes.append(msg + "（② 路设计如此，offset 由 ①/③ 路提供）")
            elif rid.startswith("RTL/"):
                unmapped.append(rid)
        elif kind == "doc_entry":
            eid = str(rec.get("id") or rec.get("entry_id"))
            if "#" not in eid:
                gaps.append({"kind": "segment", "blocking": True,
                             "detail": "doc_entry diff 的 entry_id 不合 `0xXXXX#0xYYYY`：%r" % eid,
                             "action": "转人工：修 kb/index/regmap.json 的 entry_id 生成口径后重跑"})
                continue
            seg = canon_seg(rec.get("segment") or eid.split("#", 1)[0]) \
                or str(rec.get("segment") or eid.split("#", 1)[0])
            if seg in MARKED_ONLY:
                gaps.append({"kind": "marked-only-segment", "blocking": True,
                             "detail": "diff 触及只打标记不建映射的段 %s（entry_id=%s）：不建映射、不产出必改/待查"
                                       % (seg, eid),
                             "action": "转人工：请文档方确认该段是否登记（spec §10.3）后决定是否补登记"})
                continue
            if seg not in REGISTERED and seg not in map_idx_segments(map_idx):
                gaps.append({"kind": "segment", "blocking": True,
                             "detail": "diff 触及未登记段 %s（entry_id=%s）" % (seg, eid),
                             "action": "转人工：确认段基址（README §3.2 只有 8 个已登记段）"})
                continue
            off = rec.get("offset")
            if off in (None, "NA"):
                offs = rec.get("offsets") or []
                off = offs[0] if offs else None
            if off in (None, "NA"):
                gaps.append({"kind": "offset", "blocking": True,
                             "detail": "doc_entry %s 的 offset_global=NA ⇒ 无法定位 offset" % eid,
                             "action": "转人工：确认该条目所属段/offset 后重跑 n1_doc_entries.py"})
                continue
            gv = parse_int(off)
            add_cand(seg, "doc_entry diff 触及 %s（文档条目直接给 offset）" % eid,
                     "%s 条目 %s（offset_global=%s）" % (K.relpath("kb/index/regmap.json"), eid, off))
            add_off(seg, gv, gv, eid, project_bitdef(rec), eid, "doc_entry")
            c = candidates[seg]
            if rec.get("unresolved") and not rec.get("offsets"):
                gaps.append({"kind": "offset", "blocking": False,
                             "detail": "doc_entry %s 未抽出 offset：%s" % (eid, rec.get("unresolved")),
                             "action": "转人工：补 offset 后重跑"})

    if unmapped:
        # 宁多勿漏：未映射的 RTL 文件 ⇒ 8 段全部进候选
        for seg in REGISTERED:
            add_cand(seg, "diff 触及未映射 RTL 文件 ⇒ 段级粗筛宁多勿漏，8 段全部候选", None)
        gaps.append({"kind": "rtl_file", "blocking": False,
                     "detail": "diff 触及 %d 个 RTL 文件在 segment_rtl.json 里无映射：%s"
                               % (len(unmapped), ", ".join(sorted(set(unmapped))[:8])),
                     "action": "转人工：补 kb/index/segment_rtl.json 的段↔RTL 映射（本轮已把 8 段全部当候选）"})
    if touched_files and not candidates:
        gaps.append({"kind": "segment", "blocking": True,
                     "detail": "diff 触及文件 %d 个，但段级粗筛未命中任何已登记段（索引不可用）"
                               % len(touched_files),
                     "action": "转人工：核对 segment_rtl.json 覆盖是否完整后重跑"})
    if not touched_files:
        notes.append("N2 差异清单里没有文件级 diff（可能只有文档条目差异）⇒ 段粗筛只依赖 ③ 路 entry_id")
    return candidates, offsets, touched_files, unmapped


def map_idx_segments(map_idx):
    return sorted(set(seg for lst in map_idx.values() for seg, _ in lst))


# ---------------------------------------------------------------- task-13 标注：可达性 + 墙钟成本

DECODE_FALLBACK = ("utf-8", "gbk", "latin-1")
DEFAULT_MAX_WALL = 1800.0        # 30 min（--max-wall 可覆盖）
TASK_DEF = re.compile(r"\btask\s+(?:automatic\s+)?([A-Za-z_]\w*)\s*[;(]")
ENDTASK = re.compile(r"\bendtask\b")
ROOT_TASK_CANDIDATES = ("m_run_phase", "run_phase", "m_run")


def read_source_text(path):
    """源码文本（utf-8→gbk→latin-1 回退，与 n2_diff 同口径）；不可读返回 (None, None)。"""
    try:
        raw = open(path, "rb").read()
    except OSError:
        return None, None
    if b"\x00" in raw:
        return None, None
    for enc in DECODE_FALLBACK:
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return None, None


def parse_tasks(text):
    """→ [(name, start_line, end_line)]（1-based，endtask 行）；确定性顺序。"""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = TASK_DEF.search(line)
        if not m:
            continue
        name = m.group(1)
        if name in ("task",):      # 排除形如 "task;" 的误命中
            continue
        end = None
        for j in range(i + 1, len(lines)):
            if ENDTASK.search(lines[j]):
                end = j + 1
                break
        out.append((name, i + 1, end if end else len(lines)))
    return out


#: 宏形式的任务调用：`` `FORKJN_FOR_BLK(<N>, <TF_NAME>, …) `` / `` `FORKJN_FOR_BLK_PHASE(<N>, <TF_NAME>, <PHASE>, …) ``
#: 定义在 `TB/LIBS/CBB-LIB/macros_pkg.sv:2447` / `:2462`（**只读**）。
#: **为什么必须有这一条**：`PCIE_REG_RW` / `I2C_SLV_RW` 这类 task 在用例里是以宏**第 2 实参**的形式被调用的，
#: 普通 `name(` 正则看不见 ⇒ 调用图不完整 ⇒ 把**物理上可达**的用例判成 `unreachable`。
#: 实证（N5-M1，`REHEARSAL_REPORT.md:136`）：`tc_pcie_rw_02` 被判 unreachable，
#: 而 N9 真机全跑产出了印记 `[N6_FPGA_DATE_PCIE] OK 0x0000+0x04`（sim 141.913 µs）⇒ 判据错，不是用例不可达。
#: `\w*` 覆盖 `FORKJN_*` 的其它变体；`[^,()]*` 允许第 1 实参与缩进、含换行。
MACRO_TASK_CALL_RE = re.compile(r"`FORKJN\w*\s*\(\s*[^,()]*,\s*([A-Za-z_]\w*)")
#: `` `define `` 那一行是宏**定义**，不是调用点，必须先剔除。
MACRO_DEFINE_LINE_RE = re.compile(r"^\s*`define\b")


def macro_called_names(body_text):
    """从一段源码里取出**经宏调用的 task 名**集合（确定性）。

    先剔除 `` `define `` 定义行，再整体扫描 —— 这样跨行的宏调用也能识别。
    """
    cleaned = "\n".join(ln for ln in body_text.splitlines()
                        if not MACRO_DEFINE_LINE_RE.match(ln))
    return set(MACRO_TASK_CALL_RE.findall(cleaned))


def reachability_analysis(case_path):
    """静态调用图可达性（确定性）：以 m_run_phase 等入口 task 为根做 BFS。

    返回 dict：{ok, encoding, entry, tasks:{name:{start,end,reachable}}, reason}
    `ok=False` 时调用方应把站点标 static-only（**不许猜成 live**）。
    """
    text, enc = read_source_text(case_path)
    if text is None:
        return {"ok": False, "encoding": None, "entry": None, "tasks": {},
                "reason": "用例源不可读（缺失/二进制）：%s" % K.relpath(case_path)}
    tasks = parse_tasks(text)
    if not tasks:
        return {"ok": False, "encoding": enc, "entry": None, "tasks": {},
                "reason": "未解析到 task 定义：%s" % K.relpath(case_path)}
    lines = text.splitlines()
    bodies = {}
    for name, st, en in tasks:
        bodies.setdefault(name, []).append("\n".join(lines[st - 1:en]))
    entry = next((n for n in ROOT_TASK_CANDIDATES if n in bodies), None)
    if entry is None:
        return {"ok": False, "encoding": enc, "entry": None,
                "tasks": {n: {"start": st, "end": en, "reachable": False}
                          for n, st, en in tasks},
                "reason": "找不到入口 task（%s 都不存在）：%s"
                          % ("/".join(ROOT_TASK_CANDIDATES), K.relpath(case_path))}
    seen, stack = set(), [entry]
    call_re = {n: re.compile(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"\s*\(") for n in bodies}
    body_texts = {name: "\n".join(bl) for name, bl in bodies.items()}
    macro_calls = {name: macro_called_names(t) for name, t in body_texts.items()}

    def _calls(caller, target):
        """`caller` 是否调用 `target`：普通 `name(` **或**宏形式的第 2 实参。"""
        return bool(call_re[target].search(body_texts[caller])) or target in macro_calls[caller]

    # 链式记录：某 task 的可达路径上**是否用到过宏调用点**。
    # 只看 task 自身的调用点会漏掉"宏那一跳在上一层"的情形 ——
    # 本工程实例：m_run_phase --(宏)--> PCIE_REG_RW --(普通)--> sys_reg_test，
    # 站点在 sys_reg_test 里，宏线索在上一层；只查自身会显示 False，字段名不副实。
    via_macro_chain = {entry: False}
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for name in bodies:
            if name == cur:
                continue
            plain = bool(call_re[name].search(body_texts[cur]))
            macro = name in macro_calls[cur]
            if not (plain or macro):
                continue
            via_macro_chain[name] = (via_macro_chain.get(name, False)
                                     or via_macro_chain.get(cur, False) or macro)
            if name not in seen:
                stack.append(name)
    info = {}
    for name, st, en in tasks:
        called = any(_calls(on, name) for on in bodies if on != name)
        info.setdefault(name, {"start": st, "end": en, "reachable": name in seen,
                               "called_somewhere": bool(called),
                               "called_via_macro": bool(via_macro_chain.get(name, False))})
    return {"ok": True, "encoding": enc, "entry": entry, "tasks": info, "reason": "ok"}


def site_reachability(site, analysis):
    """站点 → (reachability, basis, called_somewhere)。三类：live / static-only / unreachable。

    `called_somewhere` 用于区分两种 unreachable：完全无调用点 vs 有调用点但不在入口可达链上
    （后者在本工程实例：`sys_reg_test` 只被同样不可达的 `PCIE_REG_RW` 调用）。
    """
    if not analysis or not analysis.get("ok"):
        return "static-only", (analysis or {}).get("reason", "无调用图分析"), None
    ln = site.get("line") or 0
    for name, t in sorted(analysis["tasks"].items()):
        if t["start"] <= ln <= t["end"]:
            if t["reachable"]:
                return "live", "站点在 task %s(:%d-%d) 内，该 task 从入口 %s 可达%s" % (
                    name, t["start"], t["end"], analysis["entry"],
                    "（经宏调用点 `` `FORKJN_FOR_BLK`` 形式的第 2 实参链）"
                    if t.get("called_via_macro") else ""), True
            return "unreachable", ("站点在 task %s(:%d-%d) 内，该 task 从入口 %s 不可达"
                                   "（called_somewhere=%s%s：%s）"
                                   % (name, t["start"], t["end"], analysis["entry"],
                                      t.get("called_somewhere"),
                                      "，含宏调用点" if t.get("called_via_macro") else "",
                                      "有调用点但调用者本身不可达" if t.get("called_somewhere")
                                      else "文件内完全无调用点")), t.get("called_somewhere")
    return "static-only", "站点不在任何 task 范围内（文件级/initial 块）：line=%s" % ln, None


SIM_END_PAT = re.compile(r"from call to \$finish")
SIM_END_FS = re.compile(r"time\s+(\d+)\s*fs")
ELAPSED_S = re.compile(r"Elapsed:\s*([0-9.]+)\s*s")


def parse_run_log_cost(path):
    """从历史运行日志解析 (sim_end_us, elapsed_s)；缺任一返回 (None, None)。"""
    text, _enc = read_source_text(path)
    if text is None:
        return None, None
    sim_end_us = None
    for line in text.splitlines():
        if SIM_END_PAT.search(line):
            m = SIM_END_FS.search(line)
            if m:
                sim_end_us = float(m.group(1)) / 1e9   # fs → µs
    m2 = ELAPSED_S.search(text)
    elapsed = float(m2.group(1)) if m2 else None
    return sim_end_us, elapsed


def cost_rate(repo_root, notes):
    """实测速率（µs 仿真/秒墙钟）：**必须**来自已归档真实运行（kb/runs/**/evidence/*_run.log）。

    多样本取中位数（确定性）；单样本样本数=1、**不外推**。返回 dict（含来源与 sha256）。
    """
    pats = []
    base = os.path.join(repo_root, "kb", "runs")
    for dp, dn, fn in os.walk(base) if os.path.isdir(base) else []:
        for f in sorted(fn):
            if f.endswith("_run.log"):
                pats.append(os.path.join(dp, f))
    pats.sort()
    samples = []
    for p in pats:
        se, el = parse_run_log_cost(p)
        if se and el and se > 0:
            samples.append({"path": K.relpath(p), "sha256": K.sha256_file(p),
                            "sim_end_us": se, "elapsed_s": el, "rate_us_per_s": se / el})
    if not samples:
        notes.append("墙钟成本：**无速率样本**（kb/runs/**/evidence/*_run.log 里没有 "
                     "同时含 `from call to $finish` 与 `Elapsed:` 的归档）⇒ sim_cost/feasible 一律 unknown（不猜）")
        return {"samples": 0, "rate_us_per_s": None, "sources": []}
    rates = sorted(s["rate_us_per_s"] for s in samples)
    n = len(rates)
    med = rates[n // 2] if n % 2 == 1 else (rates[n // 2 - 1] + rates[n // 2]) / 2.0
    notes.append("墙钟速率样本 n=%d（中位数 %.4f µs/s；**不外推**：样本来自真实归档运行，逐条 sha256 记在产物里）"
                 % (n, med))
    return {"samples": n, "rate_us_per_s": med, "sources": samples}


HIST_ROOTS = ("LOG", "SIMLIB_RUN/log", "SIMLIB")


def find_history_log(repo_root, case, seed=None):
    """历史运行日志（确定性挑选：固定根顺序 + 排序后取字典序最大者）。"""
    cands = []
    for rel in HIST_ROOTS:
        d = os.path.join(repo_root, rel)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.startswith(case + "_") and f.endswith("_run.log"):
                if seed and not f.startswith("%s_%s_run.log" % (case, seed)) and ("_%s_run.log" % seed) not in f:
                    continue
                cands.append(os.path.join(d, f))
    cands.sort()
    return cands[-1] if cands else None


def sim_cost_for(case, repo_root, rate):
    p = find_history_log(repo_root, case)
    if p is None:
        return {"unknown": True, "reason": "无历史运行日志（%s 下未命中 %s_*_run.log）"
                                           % ("/".join(HIST_ROOTS), case)}
    se, el = parse_run_log_cost(p)
    if se is None:
        return {"unknown": True, "reason": "历史日志缺 `from call to $finish` 仿真时刻：%s" % K.relpath(p),
                "source_log": K.relpath(p), "source_log_sha256": K.sha256_file(p)}
    rec = {"unknown": False, "sim_end_us": round(se, 6), "source_log": K.relpath(p),
           "source_log_sha256": K.sha256_file(p),
           "sim_end_human": ("%.3f ms" % (se / 1000.0))}
    if el:
        rec["elapsed_s"] = el
    if rate.get("rate_us_per_s"):
        wall = se / rate["rate_us_per_s"]
        rec.update({"rate_us_per_s": round(rate["rate_us_per_s"], 6),
                    "rate_samples": rate["samples"],
                    "rate_sources": rate["sources"],
                    "wall_est_s": round(wall, 2),
                    "wall_est_human": ("%.1f min" % (wall / 60.0)) if wall < 3600
                                      else ("%.2f h" % (wall / 3600.0))})
    else:
        rec["wall_est_s"] = None
    return rec


def _called_via_macro(site, analysis):
    """站点所在 task 是否经**宏调用点**被调用（N5-M1 修复的直接可见证据）。"""
    if not analysis or not analysis.get("ok"):
        return None
    ln = (site or {}).get("line") or 0
    for name, t in sorted(analysis["tasks"].items()):
        if t["start"] <= ln <= t["end"]:
            return bool(t.get("called_via_macro"))
    return None


def annotate_entries(entries, site_of, max_wall):
    """给 must_change/to_check 条目加 reachability / sim_cost / feasible；返回新增字段统计。"""
    stats = {"live": 0, "static-only": 0, "unreachable": 0, "feasible_yes": 0,
             "feasible_no": 0, "feasible_unknown": 0}
    for e in entries:
        site = site_of.get((e["case"], e.get("file"), e.get("line")), None)
        r, basis, called_somewhere = site_reachability(site, (site or {}).get("_analysis"))
        e["reachability"] = r
        e["reachability_basis"] = basis
        e["reachability_called_somewhere"] = called_somewhere
        # 该 task 是否**只**靠宏调用点才可达 —— 便于人复核"为什么这条不是 unreachable"
        e["reachability_called_via_macro"] = _called_via_macro(site, (site or {}).get("_analysis"))
        stats[r] = stats.get(r, 0) + 1
        sc = (site or {}).get("_sim_cost")
        e["sim_cost"] = sc
        if not sc or sc.get("unknown"):
            e["feasible"] = "unknown"
            e["infeasible_reason"] = "墙钟成本 unknown（%s）⇒ 不得当 yes；跑前请先补一次历史日志或人工估时" \
                                     % ((sc or {}).get("reason", "无数据"))
            stats["feasible_unknown"] += 1
        elif sc.get("wall_est_s") is not None and sc["wall_est_s"] > max_wall:
            e["feasible"] = "no"
            e["infeasible_reason"] = ("预计墙钟 %s > 阈值 %.0f s（sim_end=%s × 速率 %.4f µs/s，"
                                      "样本 n=%s，来源见 sim_cost）" % (sc.get("wall_est_human"),
                                      max_wall, sc.get("sim_end_human"), sc.get("rate_us_per_s"),
                                      sc.get("rate_samples")))
            stats["feasible_no"] += 1
        else:
            e["feasible"] = "yes"
            stats["feasible_yes"] += 1
    return stats


def split_by_budget(must, max_wall):
    """按 task-13 规则分组：unreachable 单独成组；超预算单独成组；unknown 留在必改但显式可见。"""
    unreach = [e for e in must if e.get("reachability") == "unreachable"]
    over = [e for e in must if e.get("reachability") != "unreachable" and e.get("feasible") == "no"]
    keep = [e for e in must if e.get("reachability") != "unreachable" and e.get("feasible") != "no"]
    for e in unreach:
        e["why"] = (e.get("why", "") + "；【不可达】" + e.get("reachability_basis", ""))[:1200]
    for e in over:
        e["why"] = (e.get("why", "") + "；【超预算】" + e.get("infeasible_reason", ""))[:1200]
    return keep, over, unreach


# ---------------------------------------------------------------- 用例站点

def case_sites(case_access):
    sites = []
    for i, s in enumerate(case_access.get("sites", [])):
        addr = parse_int(s.get("addr"))
        lo = hi = None
        rng = s.get("range")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = parse_int(rng[0]), parse_int(rng[1])
        sites.append({"case": s.get("case"), "file": s.get("file"), "line": s.get("line"),
                      "callee": s.get("callee"), "addr_expr": s.get("addr_expr"),
                      "bucket": s.get("bucket"), "segment": s.get("segment"),
                      "in_doc": s.get("in_doc"), "addr": addr, "lo": lo, "hi": hi,
                      "idx": i})
    sites.sort(key=lambda x: (str(x["case"]), str(x["file"]), x["line"] or 0, x["idx"]))
    return sites


def site_segment(site, bases):
    if site.get("segment"):
        return canon_seg(site["segment"]) or str(site["segment"])
    return segment_of(site.get("addr") if site.get("addr") is not None else site.get("lo"), bases)


def site_addr_str(site):
    if site.get("addr") is not None:
        return "0x%x" % site["addr"]
    if site.get("lo") is not None:
        return "0x%x..0x%x" % (site["lo"], site["hi"] if site["hi"] is not None else site["lo"])
    return "NA"


# B3「未归类」不得当漏检借口（lead hard rule）：addr_expr 文本里显式出现本次变更触及的
# offset 字面量（32'h04 / +32'h4 / 0x04 …）时，必须登记索引缺口并把该用例落进【待查】。
B3_LIST_LIMIT = 200

LIT_TOKEN = re.compile(
    r"(?<![0-9a-fA-F_])"                                   # 左边界：不吃长字面量的尾巴
    r"(?:(?:32|24|16|8|64)?'([hd])([0-9a-fA-F][0-9a-fA-F_]*)"   # 32'h04 / 'h0000_0004 / 32'd4
    r"|0x([0-9a-fA-F][0-9a-fA-F_]*))"                      # 0x04 / 0x0000_0004
    r"(?![0-9a-fA-F_])")                                   # 右边界：32'h4 不得命中 32'h4c/44/40
BARE_DEC = re.compile(r"\+\s*(\d+)(?![0-9a-fA-F_'])")    # `base + 4` 这种裸十进制偏移
#   注：`(?!')` 防把 `+ 32'h04` 里的 `32` 当成裸十进制偏移（宽度前缀不是偏移）


def literals_in(text):
    """显式地址字面量 → (strong, weak)，**边界感知 token 化 + 数值比较**。

    · strong = `0x04` / `32'h04` / `32'h0000_0004` / `'h04` / `32'd4` 这类显式进制字面量；
    · weak   = `base + 4` 这类**没有 base 可解析**的裸十进制偏移（宁多勿漏：只登记不静默丢）。
    用 token 化（左右边界 + 数值相等）而不是子串匹配，专治 lead 点名的假阳性：
    `base_addr+32'h44` / `+'h4c` / `+32'h40` 都**不会**被当成 offset 0x4。
    """
    strong, weak = set(), set()
    for m in LIT_TOKEN.finditer(text or ""):
        if m.group(1) is not None:
            digits = m.group(2).replace("_", "")
            try:
                strong.add(int(digits, 16 if m.group(1) == "h" else 10))
            except ValueError:
                continue
        else:
            digits = m.group(3).replace("_", "")
            try:
                strong.add(int(digits, 16))
            except ValueError:
                continue
    for m in BARE_DEC.finditer(text or ""):
        try:
            weak.add(int(m.group(1), 10))
        except ValueError:
            continue
    return strong, weak


def b3_naive_substring_hits(text, touched_values):
    """**仅供对照/自证**：朴素子串匹配会误命中多少（lead 点名 41 个站点的那类假阳性）。"""
    n = 0
    for v in touched_values:
        for form in ("32'h%s" % format(v, "x"), "'h%s" % format(v, "x"), "0x%s" % format(v, "x")):
            if form in (text or ""):
                n += 1
                break
    return n


def b3_compensate(sites, offsets, rtl_candidates, check, limit=B3_LIST_LIMIT, must=None):
    """B3 补偿：返回 (new_check, gaps, total, listed, matched_keys, to_check_entries, fallback)。

    `total` = **命中站点数**；`to_check_entries` = `check` 里带 `b3_compensated=true` 的
    **用例级条目数**（与 total 语义不同，site ≥ entry）。
    不变式（lead hard rule）：每个命中站点所属用例必须出现在 `must` 或 `check` 里；
    万一没有（理论上不会），本函数**兜底补一条【待查】**并计入 fallback，绝不静默放过。

    · 命中站点数 = total（**必须完整给出**，不许静默截断）；
    · 明细最多列 limit 条（超出只列前 limit 条，但 total 与提示写进 notes）；
    · 命中站点进 `index_gaps[kind=offset]`（action=转人工确认实际地址）；
    · 命中站点所属用例 **至少**【待查】（带命中的 offset，不是"整条忽略"）。
    """
    touched = {}
    for seg, lst in offsets.items():
        for o in lst:
            v = parse_int(o["value"])
            if v is not None:
                touched.setdefault(v, []).append((seg, o["value"], o["entry_id"]))
    matched = []
    for site in sites:
        if site.get("bucket") != B3:
            continue
        strong, weak = literals_in(site.get("addr_expr"))
        hits = sorted((strong | weak) & set(touched))
        if hits:
            weak_only = sorted((weak - strong) & set(touched))
            matched.append((site, hits, weak_only))
    total = len(matched)
    gaps, listed = [], 0
    for site, hits, weak_only in matched:
        if listed >= limit:
            continue
        listed += 1
        hit_txt = ",".join("0x%x" % h for h in hits)
        extra = ("" if not weak_only else
                 "（其中 %s 仅由 `+<十进制>` 裸偏移推断，无 base 可解析 ⇒ 宁可列缺口不漏）"
                 % ",".join("0x%x" % h for h in weak_only))
        gaps.append({
            "kind": "offset", "blocking": False,
            "detail": ("B3 未归类站点 %s:%s 的 addr_expr=%r 显式含变更触及 offset %s%s"
                       % (site["file"], site["line"], site["addr_expr"], hit_txt, extra)),
            "action": "转人工确认该站点的实际地址（B3 未绑定形参/变量依赖，不予猜测）"})
        for h in hits:
            for seg, val, eid in touched[h]:
                rtl_files = sorted(rtl_candidates.get(seg, {}).get("rtl_files", [])) \
                    if isinstance(rtl_candidates.get(seg), dict) else []
                seg_ev = "kb/index/segment_rtl.json：%s（B3 补偿路径）" % seg
                case_site = ("kb/index/case_access.json %s:%s B3 %s addr=%s"
                             % (site["file"], site["line"], site["callee"],
                                site_addr_str(site)))
                basis = ("段 %s → RTL %s → 用例 %s:%s（%s，B3 但 addr_expr 显式含 0x%x）"
                         % (seg, ",".join(rtl_files) or "(无 RTL 文件命中)", site["file"],
                            site["line"], site["addr_expr"], h))
                why = ("B3 未归类站点的 addr_expr 文本**显式含**本次变更触及的 offset 0x%x"
                       "（边界感知字面量匹配，非子串匹配）⇒ 按『未归类不得当漏检借口』"
                       "补偿规则，至少进【待查】并登记缺口转人工" % h)
                key = (site["case"], seg, val, eid)
                dup = None
                for e in check:
                    if (e["case"] == key[0] and e["segment"] == key[1]
                            and e.get("offset") == key[2] and e.get("entry_id") == key[3]):
                        dup = e
                        break
                if dup is not None:
                    # 同一 (用例,段,offset) 已由 B1/B2 命中 ⇒ 不重复列，但标记"B3 也命中"
                    dup["b3_compensated"] = True
                    dup["b3_evidence"] = ("B3 站点 %s:%s addr_expr=%r 也显式含 offset %s"
                                          % (site["file"], site["line"], site["addr_expr"], val))
                    continue
                check.append({
                    "case": site["case"], "file": site["file"], "line": site["line"],
                    "site_bucket": B3, "b3_compensated": True, "segment": seg,
                    "offset": val, "entry_id": eid,
                    "rtl_files": rtl_files, "basis": basis, "why": why,
                    "evidence_chain": {
                        "diff_entry": "N2 diff 触及 offset %s（B3 补偿命中）" % val,
                        "segment_evidence": seg_ev, "case_site": case_site},
                    "accessed_at": []})
    # 不变式兜底：每个命中用例至少出现在 must_change 或 to_check
    fallback = []
    if must is not None:
        present = set(e["case"] for e in must) | set(e["case"] for e in check)
        for site, hits, _weak in matched:
            if site["case"] in present:
                continue
            for h in hits:
                segs = touched.get(h) or []
                if not segs:
                    continue
                seg, val, eid = segs[0]
                check.append({
                    "case": site["case"], "file": site["file"], "line": site["line"],
                    "site_bucket": B3, "b3_compensated": True, "segment": seg,
                    "offset": val, "entry_id": eid, "rtl_files": [],
                    "basis": "段 %s → 用例 %s:%s（B3 补偿不变式兜底）"
                             % (seg, site["file"], site["line"]),
                    "why": "B3 补偿不变式兜底：命中用例未出现在必改/待查里 ⇒ 补入【待查】",
                    "evidence_chain": {
                        "diff_entry": "N2 diff 触及 offset %s（B3 补偿兜底）" % val,
                        "segment_evidence": "kb/index/segment_rtl.json：%s" % seg,
                        "case_site": "kb/index/case_access.json %s:%s B3 %s addr=%s"
                                     % (site["file"], site["line"], site["callee"],
                                        site_addr_str(site))},
                    "accessed_at": []})
                present.add(site["case"])
                fallback.append({"case": site["case"], "file": site["file"],
                                 "line": site["line"], "offset": val})
                break
        check.sort(key=lambda e: (str(e["case"]), e["segment"], e.get("offset") or "",
                                  e.get("entry_id") or ""))
    to_check_entries = sum(1 for e in check if e.get("b3_compensated"))
    matched_keys = set((m[0]["case"], m[0]["file"], m[0]["line"]) for m in matched)
    # 同一 B3 站点若已按补偿路径给出"带 offset 的待查"，就去掉它的一般 B3 待查（避免同站点两条）
    def is_generic_b3(e):
        if e.get("offset") is not None:
            return False      # 补偿条目是**带 offset** 的待查，不能删（只删"一般 B3 待查"）
        cs = (e.get("evidence_chain") or {}).get("case_site", "")
        if " B3 " not in cs:
            return False
        for case, f, ln in matched_keys:
            if cs.startswith("kb/index/case_access.json %s:%s " % (f, ln)):
                return True
        return False
    check = [e for e in check if not is_generic_b3(e)]
    check.sort(key=lambda e: (str(e["case"]), e["segment"], e.get("offset") or "",
                              e.get("entry_id") or ""))
    return check, gaps, total, listed, matched_keys, to_check_entries, fallback


def classify(sites, candidates, offsets, bases):
    must, check = [], []
    seen = set()

    def emit(bucket_list, case, seg, off, entry_id, rtl_files, basis, why, chain, accessed,
             site=None):
        key = (case, seg, off, entry_id)
        for e in bucket_list:
            if (e["case"], e["segment"], e.get("offset"), e.get("entry_id")) == key:
                for a in accessed:
                    if a not in e["accessed_at"]:
                        e["accessed_at"].append(a)
                return
        if key in seen and bucket_list is check:
            pass
        rec = {"case": case, "segment": seg, "offset": off, "entry_id": entry_id,
               "rtl_files": rtl_files, "basis": basis, "why": why,
               "evidence_chain": chain, "accessed_at": list(accessed)}
        if site is not None:
            rec["file"] = site.get("file")
            rec["line"] = site.get("line")
            rec["site_bucket"] = site.get("bucket")
        bucket_list.append(rec)

    for site in sites:
        seg = site_segment(site, bases)
        if seg is None or seg not in candidates:
            continue
        c = candidates[seg]
        rtl_files = sorted(c["rtl_files"])
        seg_ev = c["segment_evidence"][0] if c["segment_evidence"] else \
            "kb/index/segment_rtl.json：%s（本轮无 RTL 文件级命中，来自文档条目路径）" % seg
        site_ev = ("kb/index/case_access.json %s:%s %s %s addr=%s"
                   % (site["file"], site["line"], site["bucket"],
                      site["callee"], site_addr_str(site)))
        acc = {"file": site["file"], "line": site["line"], "addr": site_addr_str(site),
               "bucket": site["bucket"], "callee": site["callee"]}
        if site["bucket"] == B1 and site["addr"] is not None:
            hits = [o for o in offsets.get(seg, []) if parse_int(o["value"]) == site["addr"]]
            if hits:
                bd = [h["bitdef_present"] for h in hits]
                hit_o = sorted(hits, key=lambda h: (h["entry_id"] or "", h["value"]))[0]
                basis = ("段 %s → RTL %s → 用例 %s:%s（%s）" %
                         (seg, ",".join(rtl_files) or "(仅文档条目路径)",
                          site["file"], site["line"], site["addr_expr"]))
                chain = {"diff_entry": "N2 diff %s → offset %s" % (hit_o["diff_id"], hit_o["value"]),
                         "segment_evidence": seg_ev, "case_site": site_ev}
                if True in bd:
                    emit(must, site["case"], seg, hit_o["value"], hit_o["entry_id"], rtl_files,
                         basis, "offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改",
                         chain, [acc], site=site)
                else:
                    emit(check, site["case"], seg, hit_o["value"], hit_o["entry_id"], rtl_files,
                         basis, "offset 直接命中但位域不确定（bitdef_present=false/未知）⇒ 待查",
                         chain, [acc], site=site)
                continue
            basis = ("段 %s → RTL %s → 用例 %s:%s（%s）" %
                     (seg, ",".join(rtl_files) or "(仅文档条目路径)",
                      site["file"], site["line"], site["addr_expr"]))
            emit(check, site["case"], seg, None, None, rtl_files, basis,
                 "只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏）",
                 {"diff_entry": "N2 diff 触及段 %s 但 offset 未与本站点相交" % seg,
                  "segment_evidence": seg_ev, "case_site": site_ev}, [acc], site=site)
        elif site["bucket"] == B2:
            hits = []
            for o in offsets.get(seg, []):
                v = parse_int(o["value"])
                if v is None or site["lo"] is None or site["hi"] is None:
                    continue
                if site["lo"] <= v <= site["hi"]:
                    hits.append(o)
            note = ("B2 大范围扫描区间 [0x%x,0x%x] 包含 diff 触及 offset ⇒ 未逐点展开，位域不确定"
                    % (site["lo"], site["hi"])) if hits else \
                "只段级命中（B2 大范围扫描站点）⇒ 待查（宁多勿漏）"
            basis = ("段 %s → RTL %s → 用例 %s:%s（%s，B2 区间 [0x%x,0x%x]）" %
                     (seg, ",".join(rtl_files) or "(仅文档条目路径)", site["file"], site["line"],
                      site["addr_expr"], site["lo"], site["hi"]))
            emit(check, site["case"], seg,
                 ("0x%x" % parse_int(hits[0]["value"])) if hits else None,
                 hits[0]["entry_id"] if hits else None, rtl_files, basis, note,
                 {"diff_entry": "N2 diff %s → offset %s"
                                % (hits[0]["diff_id"], hits[0]["value"]) if hits
                                else "N2 diff 触及段 %s（B2 未展开）" % seg,
                  "segment_evidence": seg_ev, "case_site": site_ev}, [acc], site=site)
        elif site["bucket"] == B3:
            basis = ("段 %s → RTL %s → 用例 %s:%s（%s）" %
                     (seg, ",".join(rtl_files) or "(仅文档条目路径)", site["file"], site["line"],
                      site["addr_expr"]))
            # schema 的 accessed_at[].bucket 只允许 B1/B2（B3 不是"实际访问站点"，
            # 它没解析出地址），所以 B3 的证据只走 evidence_chain.case_site + why。
            emit(check, site["case"], seg, None, None, rtl_files, basis,
                 "B3 未能归类（未绑定形参/跨用例实参/变量依赖），不予猜测；段级命中 ⇒ 待查"
                 "（站点 %s:%s addr=%s）" % (site["file"], site["line"], site_addr_str(site)),
                 {"diff_entry": "N2 diff 触及段 %s（B3 站点地址不可解析）" % seg,
                  "segment_evidence": seg_ev, "case_site": site_ev}, [], site=site)
    for lst in (must, check):
        lst.sort(key=lambda e: (str(e["case"]), e["segment"], e.get("offset") or "",
                                e.get("entry_id") or ""))
    return must, check


def write_md(path, out, seg_stats, rejected=None):
    L = []
    if rejected == "gate":
        L.append("> ⚠ **门禁未过，本件不是影响清单，不得作为 N6 输入**：G1 未签或非 confirmed "
                 "（`gate_precondition.enforced=true`）。文件名 = `n5_impact.gate-rejected.md`，"
                 "**没有**产出 `n5_impact.json`（task-10 N5-1 裁定 (a)）。\n")
    elif rejected == "gap":
        L.append("> ⚠ **索引缺口阻塞，本件不是影响清单，不得作为 N6 输入**：`index_complete=false`。"
                 "文件名 = `n5_impact.gap.md`，**没有**产出 `n5_impact.json`"
                 "（task-10 N5-1 裁定 (a)）。\n")
    L.append("# N5 影响分析（两级；Host 确定性，spec §2 N5 / §10.3）\n")
    L.append("- run_id：`%s`｜generated_at：`%s`" % (out["run_id"], out["generated_at"]))
    L.append("- N2 差异清单：`%s`（sha256 `%s`）" % (K.relpath(out["_n2_path"]),
                                                   out.get("n2_diff_sha256")))
    L.append("- 门禁：G1 signed=%s decision=%s actor_kind=%s human_signed=%s enforced=%s"
             % (out["gate_precondition"]["signed"], out["gate_precondition"]["decision"],
                out["gate_precondition"]["actor_kind"], out["gate_precondition"]["human_signed"],
                out["gate_precondition"]["enforced"]))
    L.append("- 结论：【必改】%d 条、【待查】%d 条；index_complete=%s"
             % (len(out["must_change"]), len(out["to_check"]), out["index_complete"]))
    ip = out.get("index_provenance") or {}
    L.append("- 索引来源（index_provenance）："
             "case_access=`%s` sha256=`%s`；segment_rtl=`%s` sha256=`%s`；"
             "buckets=%s；权威口径：%s"
             % (ip.get("case_access", {}).get("path"),
                (ip.get("case_access", {}).get("sha256") or "")[:16],
                ip.get("segment_rtl", {}).get("path"),
                (ip.get("segment_rtl", {}).get("sha256") or "")[:16],
                ip.get("buckets"), ip.get("authority")))
    L.append("- B3 补偿（lead hard rule）：命中站点总数=%s（明细列出 %s 条）；"
             "差异清单参照=%s（存在=%s）"
             % ((ip.get("b3_compensation") or {}).get("total"),
                (ip.get("b3_compensation") or {}).get("listed"),
                ip.get("divergence_ref"), ip.get("divergence_ref_present")))
    L.append("\n## 8 段覆盖（自检 ≥8，缺段即索引缺口）\n")
    L.append("| 段 | 候选 | 触及 RTL 文件 | 触及 offset | 必改 | 待查 |")
    L.append("|---|---|---|---|---|---|")
    for s in out["segments_covered"]:
        st = seg_stats.get(s, {})
        L.append("| `%s` | %s | %s | %s | %d | %d |"
                 % (s, st.get("candidate", "-"), st.get("files") or "-",
                    st.get("offsets") or "-", st.get("must", 0), st.get("check", 0)))
    L.append("\n只打标记不建映射：%s（命中只记 index_gaps，不产出必改/待查）"
             % ", ".join("`%s`" % s for s in out["marked_only_segments"]))
    cm = out.get("cost_model") or {}
    L.append("\n## task-13 标注汇总（可达性 / 墙钟成本 / 可行性）\n")
    L.append("- 阈值 `--max-wall` = %.0f s；速率样本 n=%s，中位数 %s µs/s（**样本逐条 sha256 见 cost_model.sources；n=1 时不外推**）"
             % (out.get("max_wall_s", DEFAULT_MAX_WALL), cm.get("samples"),
                cm.get("rate_us_per_s")))
    L.append("- 分组计数：" + "；".join(
        "**%s**=%d" % (k, len(out.get(k) or [])) for k in
        ("must_change", "must_change_over_budget", "must_change_unreachable", "to_check")))
    for title, rows in (("【必改】（offset 直接命中且位域可判定）", out["must_change"]),
                        ("【必改·超预算】（仍要改，但预计本轮跑不完；**不假装会跑**）",
                         out.get("must_change_over_budget") or []),
                        ("【必改·不可达】（静态站点存在但活链不可达 ⇒ 修订无法被验证）",
                         out.get("must_change_unreachable") or []),
                        ("【待查】（只段级命中或位域不确定）", out["to_check"])):
        L.append("\n## %s —— %d 条\n" % (title, len(rows)))
        if not rows:
            L.append("_无_")
            continue
        L.append("| 用例 | 段 | offset | entry_id | 可达性 | 预计墙钟 | 可行 | 依据链（段→RTL文件→用例） | why |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            sc = r.get("sim_cost") or {}
            L.append("| `%s` | `%s` | %s | %s | %s | %s | %s | %s | %s |"
                     % (r["case"], r["segment"], r.get("offset") or "-",
                        r.get("entry_id") or "-", r.get("reachability") or "-",
                        (sc.get("wall_est_human") or "unknown"), r.get("feasible") or "-",
                        r["basis"], r["why"]))
        L.append("\n访问站点（B1/B2 原样）：")
        for r in rows:
            for a in r["accessed_at"]:
                L.append("- `%s` %s:%s [%s] addr=%s callee=%s"
                         % (r["case"], a["file"], a["line"], a["bucket"], a["addr"], a["callee"]))
    if out["index_gaps"]:
        L.append("\n## 索引缺口（index_complete=%s）\n" % out["index_complete"])
        for g in out["index_gaps"]:
            L.append("- `%s`%s：%s → **%s**" % (g["kind"], "（blocking）" if g.get("blocking") else "",
                                               g["detail"], g["action"]))
    L.append("\n## 口径说明\n")
    L.append("- 一级段级粗筛**宁多勿漏**：diff 触及的 RTL 文件经 `segment_rtl.json` 映射到候选段；"
             "文件未映射时 8 段全部进候选，绝不用『没映射就当无影响』。")
    L.append("- 二级 offset 交集：①路 hunk 抽取的字面量按**块内偏移**换算 `<段基址>+<块内偏移>`"
             "（同时保留“字面量已是全局地址”的候选）；③路 entry_id 的 `offset_global` 直接作为 offset。")
    L.append("- **位域不确定口径**：`regEntry.bitdef_present=false` ⇒ 位域不可判定 ⇒ 进【待查】；"
             "只有 offset 直接命中且 `bitdef_present=true` 才是【必改】（README §6 红线 2："
             "预期值只认文档位定义表）。")
    L.append("- B2 大范围扫描站点：只知区间不含逐点 ⇒ 命中区间也只是【待查】。"
             "B3 未能归类 ⇒ 一律【待查】，不予猜测（09 §B.0）。")
    bc = (out.get("index_provenance") or {}).get("b3_compensation") or {}
    L.append("- **B3 补偿规则（不许把『未归类』当漏检借口）**：B3 站点的 `addr_expr` 文本**显式含**"
             "本次变更触及的 offset 字面量（`32'h04` / `+32'h4` / `0x04`）时，该站点必须登记"
             "`index_gaps[kind=offset]`（转人工确认实际地址）且所属用例**至少**进【待查】；"
             "命中站点总数完整写在 `index_provenance.b3_compensation.total` 与 notes 里，"
             "明细超过 %d 条只列前 %d 条但**总数不截断**。" % (B3_LIST_LIMIT, B3_LIST_LIMIT))
    L.append("- **B3 补偿计数语义（防误读为矛盾）**：`b3_compensation.total=%s` 是**站点数**，"
             "`listed=%s` 是列出明细的站点数；而 `to_check` 里带 `b3_compensated=true` 的是"
             "**用例级条目数=%s**（同一用例多个站点会合并成一条，且若该 (用例,段,offset) 已被 "
             "B1/B2 命中则合并到那条上）。站点数 ≥ 用例条目数，两者不是同一种计数。"
             % (bc.get("total"), bc.get("listed"), bc.get("to_check_entries")))
    L.append("- **可达性判据（task-13）**：对用例源（`TESTLIB/<tc>.sv`）做**静态调用图** —— 以入口 task "
             "`m_run_phase`（缺则 `run_phase`/`m_run`）为根，沿 `task <name>(` 定义 + `name(` 调用点传播；"
             "站点所在 task 可达 ⇒ `live`；定义存在但无调用点 ⇒ `unreachable`；站点不在任何 task 内 ⇒ "
             "`static-only`；源不可读/无 task/无入口 ⇒ `static-only`（**不猜 live**）。"
             "**`unreachable` 的条目不得留在【必改】** ⇒ 单独成组 `must_change_unreachable[]`。")
    L.append("- **墙钟成本判据（task-13）**：从历史运行日志（`LOG/`、`SIMLIB_RUN/log/`、`SIMLIB/` 下 "
             "`<tc>_*_run.log`；固定根顺序 + 排序取字典序最大者）解析 `from call to $finish` 的仿真时刻；"
             "速率**必须**来自已归档真实运行（`kb/runs/**/evidence/*_run.log` 的 `Elapsed` 与仿真时刻），"
             "多样本取中位数，来源 path+sha256 全部记进 `cost_model`。"
             "`wall_est = sim_end / rate`；`> --max-wall` ⇒ `feasible=no` 并移入 `must_change_over_budget[]`"
             "（**仍在清单里**，附量化原因）。缺历史日志 ⇒ `sim_cost=unknown`/`feasible=unknown`（**不许猜 yes**）。")
    L.append("- **索引权威口径**：`kb/index/case_access.json`（T3 重推）为权威；"
             "09 笔记的数字仅为参照，N5 **不**用 09 的数字去校准（README §3.3 已改）。")
    L.append("- `0x8000`/`0x10000` 只打标记不建映射 ⇒ 命中写 `marked-only-segment` 缺口并 rc!=0，"
             "转人工，不产出必改/待查（spec §10.3）。")
    L.append("- 归一化指纹复算口径（task-18 / F-DET-01）：`normalized_sha256 = "
             "sha256(canon_json(本对象 **剔除 `normalized_sha256` 与 `time_fields`**（以及下划线开头的内部键）后，"
             "把 `generated_at` 替换为 `\"<TIMESTAMP>\"`))` —— 按 README §3.1.1 的字面公式"
             "**必须先剔除自指簿记键**才能复算。被剔除键清单："
             "`[\"normalized_sha256\",\"time_fields\",\"_*\"]`；"
             "被归一化的时间字段：`%s`。本件自报值见 `normalized_sha256` 字段。" % out.get("time_fields"))
    L.append("- `generated_at` 是唯一被允许的非确定性字段（README §3.1.1，本脚本声明时间字段 "
             "`(\"generated_at\",)`），一律经 `kb_lib.now_iso()` 与 `--now`/`KB_NOW` 注入；"
             "强判据：同一输入 + 同一 `--now` 两次逐字节相同；弱判据：不同 `--now` 两次，"
             "`K.sha256_obj_normalized(obj, (\"generated_at\",))` 相同。")
    if out.get("notes"):
        L.append("\n## 其他说明\n")
        for n in out["notes"]:
            L.append("- %s" % n)
    L.append("")
    return K.write_text(path, "\n".join(L) + "\n")


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N5 影响分析（段级粗筛 → offset/位域交集 → 必改/待查；索引缺失 rc!=0）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功 / 2 用法 / 3 门禁未过或 blocking 索引缺口 / 4 self-check 失败")
    ap.add_argument("--run", required=True, help="run_id（kb/runs/<run_id>/）")
    ap.add_argument("--n2", default=None, help="N2 差异清单（默认 kb/runs/<run_id>/n2_diff.json）")
    ap.add_argument("--gates", default=None, help="闸门状态（默认 kb/runs/<run_id>/gates.json）")
    ap.add_argument("--segment-rtl", default=None, help="默认 kb/index/segment_rtl.json")
    ap.add_argument("--case-access", default=None, help="默认 kb/index/case_access.json")
    ap.add_argument("--divergence-ref", default="kb/runs/dev-case-kb/divergence_sites.csv",
                    help="T3 重推值与 09 笔记的差异清单（写进 index_provenance.divergence_ref）")
    ap.add_argument("--regmap", default=None,
                    help="文档条目索引（默认 kb/index/regmap.json）；可选，用于把 ① 路 offset 接到"
                         "位定义表（缺省不影响 rc，只把位域判为不确定）")
    ap.add_argument("--out-dir", default=None, help="产出目录（默认 kb/runs/<run_id>）")
    ap.add_argument("--allow-rehearsal", action="store_true",
                    help="演练链：允许 human_signed=false 的 G1（默认拒绝，记录仍如实）")
    ap.add_argument("--max-wall", dest="max_wall", type=float, default=DEFAULT_MAX_WALL,
                    help="墙钟可行性阈值（秒，默认 %.0f = 30 min））；超过 ⇒ feasible=no 并进【必改·超预算】"
                         % DEFAULT_MAX_WALL)
    ap.add_argument("--overwrite", action="store_true",
                    help="允许覆盖已存在的目标产物（默认：目标已存在即 rc!=0，绝不覆盖；"
                         "归档只增不改，复跑请换 run_id 或显式加本开关）")
    ap.add_argument("--now", default=None,
                    help="注入时间字段 generated_at（ISO8601；等价环境变量 KB_NOW）；"
                         "同一输入 + 同一 --now 两次 ⇒ 输出逐字节相同（README §3.1.1）")
    args = ap.parse_args(argv)
    if args.now:
        K.set_now(args.now)   # README §3.1.1：时间字段的唯一注入入口

    rd = K.run_dir(args.run)
    n2_path = args.n2 or os.path.join(rd, "n2_diff.json")
    gates_path = args.gates or os.path.join(rd, "gates.json")
    seg_rtl_path = args.segment_rtl or K.kb_path("index", "segment_rtl.json")
    case_path = args.case_access or K.kb_path("index", "case_access.json")
    out_dir = args.out_dir or rd

    gaps, notes = [], []
    pre, gate_ok = gate_precondition(gates_path, args.allow_rehearsal)
    gen = K.now_iso()   # README §3.1.1：时间字段只经 kb_lib（--now 已于 main 开头 set_now）

    if not gate_ok:
        sys.stderr.write("[FAIL] 门禁未过：%s\n" % pre["note"])
        out = {"schema": "kb/run/n5_impact", "version": 1, "run_id": args.run,
               "generated_at": gen,
               "generator": "kb/tools/n5_impact.py (Host 确定性)",
               "gate_precondition": pre,
               "segments_covered": list(REGISTERED), "marked_only_segments": list(MARKED_ONLY),
               "must_change": [], "to_check": [], "index_gaps": [],
               "index_complete": False, "exit_code": RC_BLOCK,
               "notes": ["门禁未过 ⇒ 未执行索引运算；index_complete=false 表示『本次结论不可用』，"
                         "不是索引缺失（I1：存在未决条目不得进入修订阶段）"]}
        _write(out, out_dir, args, n2_path=n2_path, rejected="gate")
        return RC_BLOCK

    n2 = load_json_checked(n2_path, "n2_diff", "N2 差异清单", gaps, "segment")
    seg_rtl = load_json_checked(seg_rtl_path, "index", "段↔RTL 映射索引", gaps, "segment")
    case_acc = load_json_checked(case_path, "index", "用例访问站点索引", gaps, "offset")
    if n2 is None or seg_rtl is None or case_acc is None:
        # 索引缺口：绝不静默给空清单 ⇒ rc!=0
        out = {"schema": "kb/run/n5_impact", "version": 1, "run_id": args.run,
               "generated_at": gen, "generator": "kb/tools/n5_impact.py (Host 确定性)",
               "n2_diff_sha256": K.sha256_file(n2_path) if os.path.exists(n2_path) else None,
               "gate_precondition": pre, "segments_covered": list(REGISTERED),
               "marked_only_segments": list(MARKED_ONLY), "must_change": [], "to_check": [],
               "index_gaps": gaps, "index_complete": False, "exit_code": RC_BLOCK,
               "notes": ["索引缺失 ⇒ 本次不产出必改/待查清单（不许把缺口当无影响）"]}
        _write(out, out_dir, args, n2_path=n2_path, rejected="gap")
        sys.stderr.write("[FAIL] 索引缺口 ⇒ rc=%d（index_complete=false）\n" % RC_BLOCK)
        return RC_BLOCK

    map_idx, mapped_segs = mapping_index(seg_rtl)
    bases = all_bases(mapped_segs + list(REGISTERED))
    missing_reg = [s for s in REGISTERED if s not in mapped_segs]
    if missing_reg:
        gaps.append({"kind": "segment", "blocking": True,
                     "detail": "8 个已登记段在 segment_rtl.json 里缺映射：%s" % ", ".join(missing_reg),
                     "action": "转人工：请 case-kb 补齐段↔RTL 映射后重跑（首版必须 8 段全覆盖）"})
    for m in seg_rtl.get("mappings", []):
        if canon_seg(m.get("segment")) in MARKED_ONLY:
            notes.append("segment_rtl.json 里含 marked-only 段 %s ⇒ 本脚本忽略其映射（不建映射）"
                         % m.get("segment"))

    regmap_path = args.regmap or K.kb_path("index", "regmap.json")
    regmap_idx = {}
    if os.path.exists(regmap_path):
        try:
            regmap_idx = regmap_index(K.read_json(regmap_path))
            notes.append("位域可判定性来源：kb/index/regmap.json（%d 条），用于把 ① 路抽出的 "
                         "offset 接到位定义表" % len(regmap_idx))
        except ValueError:
            notes.append("kb/index/regmap.json 不是合法 JSON ⇒ ① 路 offset 的位域一律【待查】")
    else:
        notes.append("kb/index/regmap.json 缺失（非必需索引）⇒ ① 路 offset 的位域一律【待查】，"
                     "只有 ③ 路 entry 投影能判 bitdef_present")
    candidates, offsets, touched_files, unmapped = collect_touched(n2, map_idx, bases, gaps, notes,
                                                                  regmap_idx)
    sites = case_sites(case_acc)
    must, check = classify(sites, candidates, offsets, bases)
    # lead hard rule：B3 站点的 addr_expr 显式含变更触及 offset ⇒ 登记缺口 + 至少【待查】
    check, b3_gaps, b3_total, b3_listed, b3_keys, b3_entries, b3_fallback = b3_compensate(
        sites, offsets, candidates, check, limit=B3_LIST_LIMIT, must=must)
    gaps.extend(b3_gaps)
    if b3_total:
        notes.append("B3 补偿命中站点总数=%d（addr_expr 显式含变更触及 offset）；"
                     "本轮明细列出 %d 条%s；落到 to_check 的**用例级条目数=%d**"
                     "（站点数与用例条目数语义不同：同用例多站点合并）"
                     % (b3_total, b3_listed,
                        "" if b3_listed >= b3_total else
                        "（超过上限 %d，仅列前 %d 条；总数见本行，不静默截断）"
                        % (B3_LIST_LIMIT, b3_listed), b3_entries))
    if b3_fallback:
        notes.append("B3 补偿不变式兜底补入 %d 条【待查】（命中用例原本未出现在必改/待查里）：%s"
                     % (len(b3_fallback), ", ".join("%s(%s:%s)"
                                                    % (f["case"], f["file"], f["line"])
                                                    for f in b3_fallback)))

    # 段统计（含 8 段全覆盖）
    seg_stats = {}
    for s in REGISTERED:
        c = candidates.get(s)
        seg_stats[s] = {
            "candidate": "是" if c else "否",
            "files": ",".join(sorted(c["rtl_files"])) if c and c["rtl_files"] else None,
            "offsets": ",".join(sorted(o["value"] for o in offsets.get(s, []))) or None,
            "must": sum(1 for r in must if r["segment"] == s),
            "check": sum(1 for r in check if r["segment"] == s),
        }
    # B2/B1 站点统计（口径取证）
    n_b1 = sum(1 for s in sites if s["bucket"] == B1)
    n_b2 = sum(1 for s in sites if s["bucket"] == B2)
    n_b3 = sum(1 for s in sites if s["bucket"] == B3)
    notes.append("用例访问站点：B1=%d B2=%d B3=%d（B3 不猜，只在段级命中时进【待查】）"
                 % (n_b1, n_b2, n_b3))
    if n_b3:
        gaps.append({"kind": "offset", "blocking": False,
                     "detail": "存在 %d 个 B3 未能归类访问站点（含未知符号，不猜测）" % n_b3,
                     "action": "转人工：如需精确判定，请作者补绑定形参/展开变量后重扫 case_access.json"})
    if not offsets:
        gaps.append({"kind": "offset", "blocking": False,
                     "detail": "本轮未从差异里抽出任何 offset ⇒ 二级交集退化为段级（只有待查，无必改）",
                     "action": "转人工：确认 n2_diff.json 的 offsets/unresolved 是否合理"})

    # spec §10.3 / README §3.2：0x8000/0x10000 只打标记不建映射。即便本轮 diff 未触及，
    # 也在 index_gaps 里留一条**非阻塞**的 marked-only-segment 说明（缺口必须显式可见，不静默）
    for seg in MARKED_ONLY:
        if any(seg in g["detail"] for g in gaps if g.get("kind") == "marked-only-segment"):
            continue
        gaps.append({"kind": "marked-only-segment", "blocking": False,
                     "detail": ("%s 只打标记不建映射（docs/RTL 依据不足；本轮 diff 未触及该段）"
                                % seg),
                     "action": "转人工：如需覆盖该段，先补文档登记或 RTL 译码依据，再决定是否建映射"})

    # ---------------- task-13：可达性 + 墙钟成本 + 可行性标注（确定性、可复算） ----------------
    rate = cost_rate(K.ROOT, notes)
    site_of = {}
    for e in list(must) + list(check):
        site_of[(e["case"], e.get("file"), e.get("line"))] = {
            "case": e["case"], "file": e.get("file"), "line": e.get("line")}
    analyses, costs = {}, {}
    for (case, cfile, _ln) in sorted(site_of):
        if cfile and case not in costs:
            pass
        if cfile and (case, cfile) not in analyses:
            p_src = K.root_path(cfile) if not os.path.isabs(cfile) else cfile
            analyses[(case, cfile)] = reachability_analysis(p_src)
        if case not in costs:
            costs[case] = sim_cost_for(case, K.ROOT, rate)
    for _k, site in site_of.items():
        site["_analysis"] = analyses.get((site["case"], site.get("file")))
        site["_sim_cost"] = costs.get(site["case"])
    ann_must = annotate_entries(must, site_of, args.max_wall)
    ann_check = annotate_entries(check, site_of, args.max_wall)
    must, must_over, must_unreach = split_by_budget(must, args.max_wall)
    unreach_files = sorted(set("%s:%s" % (s.get("file"), s.get("line")) for s in site_of.values()
                               if (s.get("_analysis") or {}).get("ok") is False))
    if unreach_files:
        notes.append("可达性分析无法完成的用例文件 %d 个（这些站点只标 static-only，不猜 live）：%s"
                     % (len(unreach_files), ", ".join(unreach_files[:5])))
    notes.append("task-13 标注（必改）：reachability live=%d/static-only=%d/unreachable=%d，"
                 "feasible yes=%d/no=%d/unknown=%d；阈值 %.0f s；不可达 %d 组、超预算 %d 组"
                 "（分组后仍在清单里，但不假装本轮会跑）"
                 % (ann_must.get("live", 0), ann_must.get("static-only", 0),
                    ann_must.get("unreachable", 0), ann_must.get("feasible_yes", 0),
                    ann_must.get("feasible_no", 0), ann_must.get("feasible_unknown", 0),
                    args.max_wall, len(must_unreach), len(must_over)))

    index_complete = not any(g.get("blocking") for g in gaps)
    out = {"schema": "kb/run/n5_impact", "version": 1, "run_id": args.run,
           "generated_at": gen, "generator": "kb/tools/n5_impact.py (Host 确定性)",
           "n2_diff_sha256": K.sha256_file(n2_path),
           "gate_precondition": pre,
           "index_provenance": {
               "case_access": {"path": K.relpath(case_path),
                               "sha256": K.sha256_file(case_path)},
               "segment_rtl": {"path": K.relpath(seg_rtl_path),
                               "sha256": K.sha256_file(seg_rtl_path)},
               "n2_diff": {"path": K.relpath(n2_path), "sha256": K.sha256_file(n2_path)},
               "buckets": case_acc.get("buckets"),
               "authority": ("kb/index/case_access.json 的重新推导值为权威；"
                             "doc/_notes/09_iface_doc_vs_case.md 的数字（1928/66/2561/4555）"
                             "仅为参照（kb/README.md §3.3 已按 T3 重推值改）"),
               "divergence_ref": args.divergence_ref,
               "divergence_ref_present": os.path.exists(K.root_path(args.divergence_ref)),
               "b3_compensation": {"total": b3_total, "listed": b3_listed,
                                   "to_check_entries": b3_entries,
                                   "fallback_added": len(b3_fallback),
                                   "limit": B3_LIST_LIMIT}},
           "segments_covered": list(REGISTERED),
           "marked_only_segments": list(MARKED_ONLY),
           "must_change": must, "to_check": check,
           "must_change_over_budget": must_over,
           "must_change_unreachable": must_unreach,
           "max_wall_s": args.max_wall,
           "cost_model": rate,
           "annotation_stats": {"must_change": ann_must, "to_check": ann_check},
           "index_gaps": [{"kind": g["kind"], "detail": g["detail"], "action": g["action"],
                           "blocking": bool(g.get("blocking"))} for g in gaps],
           "index_complete": index_complete,
           "exit_code": RC_OK if index_complete else RC_BLOCK,
           "notes": notes,
           "touched_files": sorted(set("%s:%s" % t for t in touched_files)),
           "unmapped_rtl_files": sorted(set(unmapped)),
           "offsets_seen": offsets,
           "segment_stats": seg_stats}
    if len(out["segments_covered"]) < 8:
        sys.stderr.write("[FAIL] segments_covered < 8（脚本自检失败）\n")
        return RC_SELFCHECK
    _write(out, out_dir, args, n2_path=n2_path, seg_stats=seg_stats)
    if not index_complete:
        sys.stderr.write("[FAIL] 存在 blocking 索引缺口 ⇒ index_complete=false，rc=%d\n" % RC_BLOCK)
        return RC_BLOCK
    return RC_OK


def _write(out, out_dir, args, n2_path=None, seg_stats=None, rejected=None):
    """写 n5 产物。

    `rejected`（task-10 N5-1 裁定 (a)）：
      * None   ⇒ `n5_impact.json` / `.md`（正式影响清单）
      * "gate" ⇒ `n5_impact.gate-rejected.json` / `.md`（门禁未过，**不产生**正式清单）
      * "gap"  ⇒ `n5_impact.gap.json` / `.md`（blocking 索引缺口）
    通用纪律：**目标已存在即 rc!=0，绝不覆盖**（归档只增不改）；显式 `--overwrite` 才允许复跑。
    """
    if n2_path:
        out["_n2_path"] = n2_path
    # README §3.1.1：声明时间字段清单 + 归一化指纹（弱判据的可复算目标）
    out["time_fields"] = ["generated_at"]
    out["normalized_sha256"] = K.sha256_obj_normalized(
        {k: v for k, v in out.items() if not k.startswith("_")
         and k not in ("normalized_sha256", "time_fields")}, ("generated_at",))
    errs = K.validate({k: v for k, v in out.items() if not k.startswith("_")},
                      K.load_schema(SCHEMA_NAME))
    if errs:
        sys.stderr.write("[FAIL] 产出未过 %s：\n  - %s\n" % (SCHEMA_JSON, "\n  - ".join(errs)))
        raise SystemExit(RC_SELFCHECK)
    K.ensure_dir(out_dir)
    stem = {"gate": "n5_impact.gate-rejected", "gap": "n5_impact.gap",
            None: "n5_impact"}[rejected]
    jp = os.path.join(out_dir, stem + ".json")
    mp = os.path.join(out_dir, stem + ".md")
    if not getattr(args, "overwrite", False):
        for target in (jp, mp):
            if os.path.exists(target):
                sys.stderr.write("[FAIL] 目标已存在，拒绝覆盖（归档只增不改）：%s\n"
                                 "       ⇒ 换 run_id/--out-dir，或显式 --overwrite 复跑\n"
                                 % K.relpath(target))
                raise SystemExit(RC_BLOCK)
    K.write_json(jp, {k: v for k, v in out.items() if not k.startswith("_")})
    write_md(mp, out, seg_stats or {}, rejected=rejected)
    print("[kb] run_id=%s generated_at=%s" % (out["run_id"], out["generated_at"]))
    print("[kb] 门禁：%s" % out["gate_precondition"]["note"])
    print("[kb] 必改=%d 待查=%d index_complete=%s exit_code=%d"
          % (len(out["must_change"]), len(out["to_check"]),
             out["index_complete"], out["exit_code"]))
    for s in out["segments_covered"]:
        st = (seg_stats or {}).get(s, {})
        print("[kb]   段 %s 候选=%s 触及offset=%s 必改=%d 待查=%d"
              % (s, st.get("candidate", "?"), st.get("offsets") or "-",
                 st.get("must", 0), st.get("check", 0)))
    for g in out["index_gaps"]:
        print("[kb]   索引缺口[%s]%s：%s" % (g["kind"], " blocking" if g.get("blocking") else "",
                                            g["detail"]))
    print("[kb] 产出：%s sha256=%s" % (K.relpath(jp), K.sha256_file(jp)))
    print("[kb] 归一化指纹（弱判据，time_fields=[generated_at]）：%s"
          % out.get("normalized_sha256"))
    print("[kb]       %s sha256=%s" % (K.relpath(mp), K.sha256_file(mp)))


if __name__ == "__main__":
    raise SystemExit(main())
