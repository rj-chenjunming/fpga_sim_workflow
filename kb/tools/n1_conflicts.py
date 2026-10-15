#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n1_conflicts.py —— 06 号笔记 → conflicts / access_restrictions / pending（一等公民清单）

唯一数据源（只读）
    doc/_notes/06_iface_doc_regmap.md  §A.1（访问路径限制 20 条）
                                       §B  （文档内部矛盾 C1—C72）
                                       §D  （待确认 D1—D20）
    行号复验基准：doc/reference/TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md（2006 行）

产物与自检（06 §C：72 / 20 / 20；实际条数 != expected_total ⇒ rc!=0，绝不静默通过）
    kb/conflicts/conflicts.json            expected_total = 72，编号 C1—C72 连续无缺号
    kb/conflicts/access_restrictions.json  expected_total = 20（§A.1 主表 18 + 附加 2）
    kb/conflicts/pending.json              expected_total = 20（D1—D20，每条必须带去向 owner）

解析口径
    * §B/§A.1/§D 三张表都是结构化 markdown 表，逐行解析（id/类型/位置/内容/建议判定）
    * `segment`：按所在 `### B.x` 小节给默认段，跨段/元信息类覆盖为 'ALL'
      （B.8 同时含 LED/SPI/IO 三类，逐条显式指派）
    * `evidence` 一定带 06 笔记行号 + 文档位置行号；脚本复验所有 `L<n>` 均落在
      文档 1..2006 行内（越界 ⇒ rc!=0）
    * `status` 一律 'open'：模型不得自封 confirmed/ruled（spec §1 I4 由人推进）
    * `blocks_release` 一律 True：冲突未清零不发版（spec I4）
    * `linked_entries`：人工核对补全的 冲突 ↔ regmap entry_id 关联（格式与段一致性自检）

确定性（kb/README.md §3.1.1）
    * 时间字段清单 = `("generated_at",)`（**唯一**允许的非确定性来源）
    * `--now <ISO8601>`（等价环境变量 `KB_NOW`）经 `kb_lib.set_now()` / `kb_lib.now_iso()`
      注入；**未给时刻时不写 `generated_at`**，因此默认调用连跑两次逐字节相同
    * 脚本内不取时钟（不用 datetime.now）
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import kb_lib  # noqa: E402  （指纹/原子写/JSON-Schema 校验一律复用公共库）

# ---------------------------------------------------------------- 常量

NOTE_DEFAULT = kb_lib.root_path("doc", "_notes", "06_iface_doc_regmap.md")
DOC_DEFAULT = kb_lib.root_path(
    "doc", "reference", "TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md")
OUTDIR_DEFAULT = kb_lib.kb_path("conflicts")

EXPECTED_CONFLICTS = 72
EXPECTED_RESTRICTIONS = 20
EXPECTED_PENDING = 20

BAR0_BASES = set(["0x0000", "0x0100", "0x0600", "0x0800",
                  "0x0a00", "0x0d00", "0x2000", "0x4000"])

# `### B.x` 小节 → 默认段
SUBSECTION_SEG = {
    "B.0": "ALL",
    "B.1": "0x0000",
    "B.2": "0x0100",
    "B.3": "0x2000",
    "B.4": "0x0a00",
    "B.5": "0x0d00",
    "B.6": "0x4000",
    "B.7": "0x0800",
    "B.8": "ALL",     # LED/SPI/IO 三类混编，逐条覆盖见下
    "B.9": "ALL",
}
# 覆盖：跨段 / 元信息 / B.8 混编
SEG_OVERRIDE = {
    "C20": "ALL", "C63": "ALL", "C33": "0x2000", "C34": "0x2000",
    "C39": "ALL", "C41": "ALL",
    "C30": "ALL", "C31": "0x0600", "C32": "0x0600",
    "C48": "SPI", "C49": "SPI", "C51": "SPI", "C50": "ALL",
    "C52": "IO", "C53": "IO",
}

# §A.1 主表 18 条 + 附加 2 条：scope（schema 枚举）与 channels（schema 枚举）
# 通道一律按 06 §A.1「受限通道（文档原文）」逐条映射，原文保留在 raw 字段。
RESTRICT_SCOPE = {
    1: "register", 2: "register", 3: "register", 4: "register", 5: "register",
    6: "register", 7: "register", 8: "register", 9: "register", 10: "register",
    11: "segment", 12: "segment", 13: "block", 14: "block", 15: "register",
    16: "segment", 17: "register", 18: "register", 19: "implicit", 20: "implicit",
}
RESTRICT_CHANNELS = {
    1: ["BMC-I2C"],                                        # 只能由 bmc I2C 接口访问
    2: ["CPU-I2C"],                                        # 只能由 cpu I2C 接口访问
    3: ["CPU"], 4: ["CPU"], 5: ["CPU"], 6: ["CPU"],        # 只能由 CPU 接口访问
    7: ["BMC"],                                            # 只能由 BMC 接口访问
    8: ["CPU"], 9: ["CPU"], 10: ["CPU"],
    11: ["CPU-PCIE", "CPU-I2C"],                           # (CPU PCIE/CPU I2C 接口访问)
    12: ["CPU-PCIE", "CPU-I2C"],
    13: ["CPU"],                                           # (CPU 接口访问)
    14: ["CPU"], 15: ["BMC"],                              # 15 = "BMC可读，sonic"
    16: ["NONE"],                                          # 软件不可见
    17: ["CPLD"], 18: ["CPLD"],                            # cplda / cpldb 访问
    19: ["BMC"], 20: ["BMC"],                              # Sonic 未定义（D10），仅 BMC 可映射
}
RESTRICT_ID = {}
for _n in range(1, 19):
    RESTRICT_ID[_n] = "R%d" % _n
RESTRICT_ID[19] = "A1"
RESTRICT_ID[20] = "A2"

# §D 每条待确认的「去向」owner（schema 枚举 doc-owner/rtl-owner/user/unassigned）
# 规则：文档文字/表格内部错误、缺失、口径未声明 → doc-owner；
#       需 RTL/实测才能定的位域与偏移布局 → rtl-owner；
#       需用户决策或外部资源（Visio 原图） → user。禁止无去向，故 unassigned 一律不用。
PENDING_OWNER = {
    "D1": "doc-owner", "D2": "doc-owner", "D3": "doc-owner", "D4": "doc-owner",
    "D5": "doc-owner", "D6": "doc-owner",
    "D7": "rtl-owner",
    "D8": "doc-owner", "D9": "doc-owner", "D10": "doc-owner", "D11": "doc-owner",
    "D12": "doc-owner", "D13": "doc-owner",
    "D14": "rtl-owner", "D15": "rtl-owner", "D16": "rtl-owner",
    "D17": "doc-owner", "D18": "doc-owner", "D19": "doc-owner",
    "D20": "user",
}

# 冲突 ↔ regmap entry_id（人工核对补全；只在能指名到寄存器时列，段级/元信息类留空）
LINKED_ENTRIES = {
    "C1": ["0x0000#0x0000"],
    "C2": ["0x0000#0x0004"],
    "C3": ["0x0000#0x0010"],
    "C4": ["0x0000#0x0090"],
    "C5": ["0x0000#0x00f0"],
    "C6": ["0x0000#0x0020", "0x0000#0x008c", "0x0000#0x00f0"],
    "C7": ["0x0000#0x00c0"],
    "C8": ["0x0000#0x00b8", "0x0000#0x00bc"],
    "C9": ["0x0000#0x0080", "0x0000#0x0084", "0x2000#0x2078"],
    "C11": ["0x0100#0x0180"],
    "C12": ["0x0100#0x0134"],
    "C13": ["0x0100#0x0114", "0x0100#0x0118"],
    "C65": ["0x0100#0x0100"],
    "C14": ["0x2000#0x2054", "0x2000#0x2058", "0x2000#0x205c", "0x2000#0x2064",
            "0x2000#0x2068", "0x2000#0x206c", "0x2000#0x2070", "0x2000#0x2074"],
    "C15": ["0x2000#0x2000", "0x2000#0x2004", "0x2000#0x2008", "0x2000#0x2030"],
    "C16": ["0x2000#0x2050"],
    "C17": ["0x2000#0x2070"],
    "C18": ["0x2000#0x2054", "0x2000#0x2058", "0x2000#0x205c", "0x2000#0x2064",
            "0x2000#0x2068", "0x2000#0x206c", "0x2000#0x2070", "0x2000#0x2074"],
    "C19": ["0x2000#0x205c", "0x2000#0x2064"],
    "C22": ["0x2000#0x2078", "0x2000#0x207c"],
    "C63": ["0x2000#0x2100", "0x4000#0x4100"],
    "C43": ["0x0a00#0x0b80"],
    "C44": ["0x0a00#0x0b8c"],
    "C45": ["0x0a00#0x0b88", "0x0a00#0x0b8c", "0x0a00#0x0b98"],
    "C62": ["0x0a00#0x0b84"],
    "C47": ["0x0d00#0x0d00"],
    "C66": ["0x0d00#0x0d70", "0x0d00#0x0d74", "0x0d00#0x0d78", "0x0d00#0x0d7c",
            "0x0d00#0x0d80", "0x0d00#0x0d84", "0x0d00#0x0d88", "0x0d00#0x0d8c"],
    "C38": ["0x4000#0x4060"],
    "C39": ["0x2000#0x2018", "0x4000#0x4018"],
    "C40": ["0x4000#0x407c"],
    "C59": ["0x0000#0x0080"],
    "C60": ["0x0000#0x0014", "0x0000#0x009c"],
    "C61": ["0x0000#0x00bc", "0x0000#0x00c0"],
    "C24": ["0x0800#0x0800"],
    "C25": ["0x0800#0x0814"],
    "C26": ["0x0800#0x0810"],
    "C28": ["0x0800#0x0800", "0x0800#0x0808"],
    "C69": ["0x0800#0x0814"],
    "C70": ["0x0800#0x0814"],
    "C31": ["0x0600#0x0600", "0x0600#0x0604", "0x0600#0x0608", "0x0600#0x060c",
            "0x0600#0x0610", "0x0600#0x0614", "0x0600#0x0618", "0x0600#0x061c"],
}
# 允许跨段关联的冲突（其余冲突的 linked_entries 段必须与 segment 一致，否则 rc!=0）
CROSS_SEG_ALLOWED = set(["C9", "C39", "C63"])

ENTRY_ID_RE = re.compile(r"^0x[0-9a-f]{4}#0x[0-9a-f]{1,5}$")
LINE_REF_RE = re.compile(r"L(\d+)")

# ---------------------------------------------------------------- markdown 表解析

_ADDR_ALL_RE = re.compile(r"0[xX][0-9a-fA-F]+")


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def cells(row):
    s = row.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def is_sep(row):
    cs = cells(row)
    return len(cs) > 0 and all(re.match(r"^:?-{2,}:?$", c) for c in cs)


def plain(text):
    return (text or "").replace("**", "").replace("`", "").strip()


def table_blocks(lines):
    out = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().startswith("|"):
            j = i
            while j < n and lines[j].strip().startswith("|"):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def section_of(lines, line_no):
    """最近的 `### B.x ...` 小节号（1-based 行号之前）。"""
    cur = None
    for idx in range(0, line_no - 1):
        m = re.match(r"^###\s+(B\.\d+)", lines[idx])
        if m:
            cur = m.group(1)
    return cur


def addrs_in(text, first_only=False):
    if first_only:
        m = _ADDR_ALL_RE.search(text or "")
        return ["0x%04x" % int(m.group(0), 16)] if m else []
    out = []
    for m in _ADDR_ALL_RE.finditer(text or ""):
        v = "0x%04x" % int(m.group(0), 16)
        if v not in out:
            out.append(v)
    return out


# ---------------------------------------------------------------- 三张清单

def parse_conflicts(lines, doc_nlines):
    items = []
    for (i0, i1) in table_blocks(lines):
        rows = lines[i0:i1]
        hdr = cells(rows[0])
        if hdr[:2] != ["编号", "类型"]:
            continue
        sub = section_of(lines, i0 + 1)
        for k in range(1, len(rows)):
            if is_sep(rows[k]):
                continue
            cs = cells(rows[k])
            if len(cs) < 5:
                continue
            cid = plain(cs[0])
            if not re.match(r"^C\d+$", cid):
                continue
            doc_line = plain(cs[2])
            summary = plain(cs[3])
            advice = plain(cs[4])
            segment = SEG_OVERRIDE.get(cid, SUBSECTION_SEG.get(sub, "ALL"))

            # 行号复验：doc_line 与冲突正文里所有 L<n> 必须落在文档 1..doc_nlines
            bad = []
            for n in LINE_REF_RE.findall(doc_line) + LINE_REF_RE.findall(summary):
                if not (1 <= int(n) <= doc_nlines):
                    bad.append(n)
            if bad:
                raise ValueError("冲突 %s 的行号越界：%s（文档共 %d 行）"
                                 % (cid, bad, doc_nlines))

            note_line = i0 + 1 + k
            items.append({
                "id": cid,
                "segment": segment,
                "category": plain(cs[1]),
                "doc_line": doc_line,
                "summary": summary,
                "evidence": ("06_iface_doc_regmap.md:L%d（§%s 行）; 文档位置 %s; "
                             "06 建议判定原文：%s" % (note_line, sub, doc_line, advice)),
                "status": "open",
                "resolution": None,
                "resolution_actor": None,
                "resolution_kind": None,
                "linked_entries": list(LINKED_ENTRIES.get(cid, [])),
                "blocks_release": True,
            })
    return items


def parse_restrictions(lines):
    out = []
    for (i0, i1) in table_blocks(lines):
        rows = lines[i0:i1]
        hdr = cells(rows[0])
        if hdr[:2] != ["#", "段/块"]:
            continue
        is_main = ("受限通道" in (hdr[4] if len(hdr) > 4 else ""))
        is_extra = ("通道语义" in (hdr[4] if len(hdr) > 4 else ""))
        if not (is_main or is_extra):
            continue
        for k in range(1, len(rows)):
            if is_sep(rows[k]):
                continue
            cs = cells(rows[k])
            if len(cs) < 6:
                continue
            num = plain(cs[0])
            if not num.isdigit():
                continue
            n = int(num)
            if n not in RESTRICT_SCOPE:
                continue
            scope = RESTRICT_SCOPE[n]
            off = plain(cs[2])
            seg_cell = plain(cs[1])
            if scope == "implicit":
                address = "NA"
            else:
                tail = off.split("/")[-1].strip()
                if re.search(r"[~—]|-", tail):
                    a = addrs_in(tail, first_only=True)
                else:
                    a = addrs_in(tail)
                if not a:
                    a = addrs_in(seg_cell, first_only=True)
                address = ",".join(a) if a else "NA"
            raw = plain(cs[4])
            doc_line = plain(cs[5])
            if is_main:
                note = plain(cs[6]) if len(cs) > 6 else ""
            else:
                note = ("隐含通道语义（非寄存器级）；Sonic 通道定义缺失（06 §D D10）")
            out.append({
                "id": RESTRICT_ID[n],
                "scope": scope,
                "address": address,
                "channels": list(RESTRICT_CHANNELS[n]),
                "doc_line": doc_line,
                "raw": raw,
                "note": note,
            })
    return out


def parse_pending(lines):
    out = []
    for (i0, i1) in table_blocks(lines):
        rows = lines[i0:i1]
        hdr = cells(rows[0])
        if len(hdr) < 4 or hdr[0] != "#" or hdr[1] != "类型" or hdr[3] != "待确认内容":
            continue
        for k in range(1, len(rows)):
            if is_sep(rows[k]):
                continue
            cs = cells(rows[k])
            if len(cs) < 4:
                continue
            did = plain(cs[0])
            if not re.match(r"^D\d+$", did):
                continue
            out.append({
                "id": did,
                "kind": plain(cs[1]),
                "doc_line": plain(cs[2]),
                "question": plain(cs[3]),
                "status": "open",
                "owner": PENDING_OWNER.get(did, "unassigned"),
                "impact": ("06 §D：文档未给出该信息；仿真用例不得自行假定（需先取得去向方答复）。"),
            })
    return out


# ---------------------------------------------------------------- 自检

def check_continuity(items, prefix, expected, what):
    bad = []
    if len(items) != expected:
        bad.append("%s 实际 %d 条 != expected_total %d" % (what, len(items), expected))
    ids = [it["id"] for it in items]
    if len(set(ids)) != len(ids):
        bad.append("%s 编号有重复" % what)
    want = ["%s%d" % (prefix, i) for i in range(1, expected + 1)]
    if ids != want:
        miss = [w for w in want if w not in ids]
        extra = [x for x in ids if x not in want]
        bad.append("%s 编号不连续：缺 %s，多 %s" % (what, miss, extra))
    return bad


def check_linked(conflicts):
    bad = []
    for c in conflicts:
        for eid in c["linked_entries"]:
            if not ENTRY_ID_RE.match(eid):
                bad.append("%s linked_entries 格式非法：%r" % (c["id"], eid))
                continue
            seg = eid.split("#")[0]
            if seg not in BAR0_BASES:
                bad.append("%s linked_entries 段不在 8 个 BAR0 段内：%r" % (c["id"], eid))
            if (c["segment"] in BAR0_BASES and c["id"] not in CROSS_SEG_ALLOWED
                    and seg != c["segment"]):
                bad.append("%s linked_entries %s 与 segment %s 不一致"
                           % (c["id"], eid, c["segment"]))
    return bad


# ---------------------------------------------------------------- 主流程

TIME_FIELDS = ("generated_at",)
NOW_ENV = "KB_NOW"


def _has_now(args):
    return bool(args.now) or bool(os.environ.get(NOW_ENV))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="06 号笔记 → kb/conflicts/{conflicts,access_restrictions,pending}.json")
    ap.add_argument("--note", default=NOTE_DEFAULT, help="输入 06 号笔记路径")
    ap.add_argument("--doc", default=DOC_DEFAULT, help="接口文档路径（复验 L<n> 行号上界）")
    ap.add_argument("--outdir", default=OUTDIR_DEFAULT, help="输出目录（默认 kb/conflicts/）")
    ap.add_argument("--now", default=None,
                    help="写入 generated_at 的时刻（ISO8601；等价环境变量 KB_NOW）。"
                         "未给时刻则不写该字段，默认调用逐字节可复现")
    ap.add_argument("--quiet", action="store_true", help="只打印 FAIL/错误")
    args = ap.parse_args(argv)
    kb_lib.set_now(args.now)  # 时刻只经此入口；None ⇒ 回落 KB_NOW ⇒ 墙钟

    for p in (args.note, args.doc):
        if not os.path.isfile(p):
            sys.stderr.write("[FAIL] 输入文件不存在：%s\n" % p)
            return 2

    nlines = read_lines(args.note)
    doc_lines = read_lines(args.doc)
    doc_nlines = len(doc_lines)

    try:
        conflicts = parse_conflicts(nlines, doc_nlines)
    except ValueError as exc:
        sys.stderr.write("[FAIL] %s\n" % exc)
        return 1
    restrictions = parse_restrictions(nlines)
    pending = parse_pending(nlines)
    restrictions.sort(key=lambda r: (0 if r["id"].startswith("R") else 1,
                                     int(r["id"].lstrip("RA"))))
    pending.sort(key=lambda d: int(d["id"][1:]))

    bad = []
    conflicts.sort(key=lambda c: int(c["id"][1:]))
    restrictions_main = [r for r in restrictions if r["id"].startswith("R")]
    restrictions_extra = [r for r in restrictions if r["id"].startswith("A")]
    bad += check_continuity(conflicts, "C", EXPECTED_CONFLICTS, "conflicts")
    bad += check_continuity(restrictions_main, "R", 18, "access_restrictions 主表")
    bad += check_continuity(restrictions_extra, "A", 2, "access_restrictions 附加")
    if len(restrictions) != EXPECTED_RESTRICTIONS:
        bad.append("access_restrictions 实际 %d 条 != expected_total %d"
                   % (len(restrictions), EXPECTED_RESTRICTIONS))
    bad += check_continuity(pending, "D", EXPECTED_PENDING, "pending")
    bad += check_linked(conflicts)
    for it in pending:
        if not it["owner"]:
            bad.append("pending %s owner 为空（spec §5 禁止无去向）" % it["id"])
        for text in (it["doc_line"], it["question"]):
            for n in LINE_REF_RE.findall(text):
                if not (1 <= int(n) <= doc_nlines):
                    bad.append("pending %s 行号越界：L%s" % (it["id"], n))
    for it in restrictions:
        if not it["channels"]:
            bad.append("restriction %s channels 为空" % it["id"])
        for n in LINE_REF_RE.findall(it["doc_line"]):
            if not (1 <= int(n) <= doc_nlines):
                bad.append("restriction %s 行号越界：L%s" % (it["id"], n))

    note_rel = kb_lib.relpath(args.note)
    conflicts_obj = {
        "schema": "kb/conflicts/conflicts",
        "version": 1,
        "source_note": note_rel,
        "expected_total": EXPECTED_CONFLICTS,
        "conflicts": conflicts,
    }
    rest_obj = {
        "schema": "kb/conflicts/access_restrictions",
        "version": 1,
        "source_note": note_rel,
        "expected_total": EXPECTED_RESTRICTIONS,
        "restrictions": restrictions,
    }
    pend_obj = {
        "schema": "kb/conflicts/pending",
        "version": 1,
        "source_note": note_rel,
        "expected_total": EXPECTED_PENDING,
        "items": pending,
    }
    if _has_now(args):
        for o in (conflicts_obj, rest_obj, pend_obj):
            o["generated_at"] = kb_lib.now_iso()

    if not args.quiet:
        print("[kb] source_note = %s" % note_rel)
        print("[kb] doc_lines   = %d（L<n> 行号复验上界）" % doc_nlines)
        print("[kb] time_fields = %s%s"
              % (",".join(TIME_FIELDS),
                 "" if _has_now(args) else "（本次未注入时刻 ⇒ 不写 generated_at）"))
        print("[stat] conflicts           = %3d  (expected_total %d)"
              % (len(conflicts), EXPECTED_CONFLICTS))
        print("[stat] access_restrictions = %3d  (expected_total %d：主表 18 + 附加 2)"
              % (len(restrictions), EXPECTED_RESTRICTIONS))
        print("[stat] pending             = %3d  (expected_total %d)"
              % (len(pending), EXPECTED_PENDING))
        segcount = {}
        for c in conflicts:
            segcount[c["segment"]] = segcount.get(c["segment"], 0) + 1
        print("[stat] conflicts by segment = %s"
              % ", ".join("%s:%d" % kv for kv in sorted(segcount.items())))
        owners = {}
        for it in pending:
            owners[it["owner"]] = owners.get(it["owner"], 0) + 1
        print("[stat] pending by owner     = %s"
              % ", ".join("%s:%d" % kv for kv in sorted(owners.items())))
        print("[stat] linked_entries 非空冲突 = %d"
              % sum(1 for c in conflicts if c["linked_entries"]))

    if bad:
        sys.stderr.write("[FAIL] 清单自检未通过（%d 项）：\n" % len(bad))
        for b in bad:
            sys.stderr.write("  - %s\n" % b)
        return 1

    for label, obj in (("conflicts", conflicts_obj),
                       ("access_restrictions", rest_obj),
                       ("pending", pend_obj)):
        try:
            kb_lib.check(obj, "conflicts", label)
        except kb_lib.SchemaError as exc:
            sys.stderr.write("[FAIL] %s\n" % exc)
            return 3

    paths = []
    for name, obj in (("conflicts.json", conflicts_obj),
                      ("access_restrictions.json", rest_obj),
                      ("pending.json", pend_obj)):
        p = os.path.join(args.outdir, name)
        kb_lib.write_json(p, obj)
        paths.append(p)
    if not args.quiet:
        for p in paths:
            print("[kb] wrote %s" % kb_lib.relpath(p))
            print("[kb] sha256(%s) = %s" % (os.path.basename(p), kb_lib.sha256_file(p)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
