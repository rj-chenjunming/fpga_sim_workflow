#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n1_doc_entries.py —— 接口文档条目抽取器（N1 文档侧锚点）

唯一数据源（只读，不修改）
    doc/reference/TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md（2006 行）
    口径与验收基准：doc/_notes/06_iface_doc_regmap.md §C

产物
    kb/index/regmap.json     （kb/schema/index.schema.json definitions.regmapFile）
    kb/index/regmap.csv      （同目录同名 .csv；--out 指向别处时 .csv 也写那里）

抽取口径（与 06 §C 逐字一致，脚本自检，不允许静默通过）
    * 汇总具名行   = 段汇总表（表头 `Offset|Name|R/W|Reset|Byte|备注`）里
                     「有地址 且 Name 非空 且 Name 不是 保留/REV」的数据行
                     （表内 `Offset：...` 分组标题行、全空行、只有 offset 无 Name 的行都不算）
    * 汇总去重 offset = 上述具名行的去重全局地址数（区间行 `0x180~0x1fc` 取起始地址）
    * 位定义表数   = 表首行形如 `| Offset：... |` 的位定义表张数
    * 位定义去重 offset = 每张位定义表贡献的 offset 数之和的去重值：
        逗号分隔的**标量**地址列表（如 `+0x20,0x24,0x28,0x2c`）逐项计数；
        含 `~` 的**区间**表达式（含 `+0x200~0x27c(ch0), +0x280~...` 多区间）整体计 1；
        `Offset：NA` 计 0（§C 合计 125 不含 2 张无地址 IO 表）
    * 硬基准（06 §C 合计）：126 / 121 / 125 / 125（不等即 rc!=0）

地址口径（06 §0.1/§0.3）
    * 汇总表（除 0x0A00/0x0D00 位定义）一律写「段内相对偏移」→ 全局地址 = 段基址 + 偏移
    * 0x0A00、0x0D00 的**位定义表**写的是 BAR0 全局地址（C46 混用）→ 直接用
    * 段基址 = 0x0000/0x0100/0x0600/0x0800/0x0A00/0x0D00/0x2000(+0x200*k)/0x4000(+0x400*m)
    * 0x8000 / 0x10000 文档未登记 ⇒ 不建条目
    * SPI Slave_a/b 是**独立 16bit 地址空间、软件不可见**，不进 BAR0 regmap 条目
      （只在抽取口径统计里计 6/6，见 06 §C 第 10 行）；3.3 IO 表 `Offset：NA` 不是寄存器

确定性（kb/README.md §3.1.1）
    * 时间字段清单 = `("generated_at",)`（**唯一**允许的非确定性来源）
    * `--now <ISO8601>`（等价环境变量 `KB_NOW`）经 `kb_lib.set_now()` / `kb_lib.now_iso()`
      注入；**未给时刻时不写 `generated_at`**，因此默认调用连跑两次逐字节相同
      （比 README §3.1.1 判据 2 更强；判据 2/3 用 `--now` 同值/异值各跑一次验证）
    * 任何地方都不自己取时钟（不用 datetime.now）
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import kb_lib  # noqa: E402  （路径/指纹/原子写/JSON-Schema 校验一律复用公共库）

# ---------------------------------------------------------------- 常量

DEFAULT_DOC = kb_lib.root_path(
    "doc", "reference", "TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md")
DEFAULT_OUT = kb_lib.kb_path("index", "regmap.json")
NOTE_06 = "doc/_notes/06_iface_doc_regmap.md"

SUMMARY_HEADER = ["Offset", "Name", "R/W", "Reset", "Byte", "备注"]
BITDEF_HEADER0 = re.compile(r"^\s*Bits\s*$")

# 段汇总表里不算「具名行」的 Name（保留/REV 是范围行）
EXCLUDE_NAMES = set(["保留", "REV", "Rev", "rev", "Reserve", "reserve", "保留范围"])

# 段定义：base=None ⇒ 无 BAR0 全局地址（只参与抽取口径统计，不建条目）
SEGMENTS = [
    {"id": "0x0000", "name": "3.1.2.2 全局寄存器", "base": 0x0000,
     "bitdef_global": False, "entries": True},
    {"id": "0x0100", "name": "3.1.2.3 DFX寄存器", "base": 0x0100,
     "bitdef_global": False, "entries": True},
    {"id": "0x2000", "name": "3.1.2.3(重号) RTC I2C Master 控制器(1~10, stride 0x200)",
     "base": 0x2000, "bitdef_global": False, "entries": True},
    {"id": "0x0a00", "name": "3.1.2.4 在线升级寄存器", "base": 0x0A00,
     "bitdef_global": True, "entries": True},
    {"id": "0x0d00", "name": "3.1.2.5 PCIE debug 寄存器", "base": 0x0D00,
     "bitdef_global": True, "entries": True},
    {"id": "0x4000", "name": "3.1.2.6 DOM RTC/Polling 控制器(0~7, stride 0x400)",
     "base": 0x4000, "bitdef_global": False, "entries": True},
    {"id": "0x0800", "name": "3.1.2.7 UART 控制器(4 路, stride 0x20)", "base": 0x0800,
     "bitdef_global": False, "entries": True},
    {"id": "0x0600", "name": "3.1.2.8 Qsfp_led 控制器", "base": 0x0600,
     "bitdef_global": False, "entries": True},
    {"id": "SPI", "name": "3.2 SPI Slave_a/b（独立 16bit 空间，软件不可见）", "base": None,
     "bitdef_global": False, "entries": False},
    {"id": "IO", "name": "3.3 IO 接口（Offset：NA，非寄存器）", "base": None,
     "bitdef_global": False, "entries": False},
]

# 标题 → 段（按顺序匹配，先长后短）
HEADING_RULES = [
    ("DOM I2C Master控制器RTC/Polling寄存器地址分配", "0x4000"),
    ("I2C Master控制器RTC寄存器地址分配", "0x2000"),
    ("全局寄存器地址分配", "0x0000"),
    ("DFX寄存器地址分配", "0x0100"),
    ("在线升级寄存器地址分配", "0x0a00"),
    ("PCIE控制器debug寄存器地址分配", "0x0d00"),
    ("UART控制器存器地址分配", "0x0800"),
    ("端口led控制器存器地址分配", "0x0600"),
    ("SPI Slave_a/SPI Slave_b接口", "SPI"),
    ("3.3 IO接口", "IO"),
]

# 06 §C 验收基准（硬性；不等即 rc!=0）
EXPECTED_TOTAL = {
    "summary_named": 126,
    "summary_unique": 121,
    "bitdef_tables": 125,
    "bitdef_unique": 125,
}
# seg_id -> (汇总具名行, 汇总去重 offset, 位定义表数, 位定义去重 offset)
EXPECTED_SEG = {
    "0x0000": (14, 14, 17, 17),
    "0x0100": (11, 11, 11, 11),
    "0x2000": (24, 24, 29, 32),
    "0x0a00": (10, 10, 10, 10),
    "0x0d00": (15, 15, 15, 15),
    "0x4000": (26, 26, 23, 26),
    "0x0800": (12, 7, 11, 7),
    "0x0600": (8, 8, 1, 1),
    "SPI": (6, 6, 6, 6),
    "IO": (0, 0, 2, 0),
}

# ---------------------------------------------------------------- 小工具

_ADDR_RE = re.compile(r"0[xX][0-9a-fA-F]+")
_SEP_RE = re.compile(r"^:?-{2,}:?$")
_OFFSET_PREFIX_RE = re.compile(r"^\s*Offset\s*[：:]\s*")
_TABLE_TITLE_RE = re.compile(r"^#*\s*表格\s*(.+?)\s*寄存器\s*(?:位定义|定义)\s*$")
_PAREN_RE = re.compile(r"[（(]\s*([A-Za-z][A-Za-z0-9_\[\]\-\. ]*?)\s*[)）]")
_ASCII_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\[\]\.]*$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
    if lines and lines[-1] == "":
        lines.pop()  # 文件末尾换行不算一行
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
    return len(cs) > 0 and all(_SEP_RE.match(c) for c in cs)


def table_blocks(lines):
    """返回 [(i0, i1)]，lines[i0:i1] 是一张连续 markdown 表。"""
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


def addr_of(text):
    """文本里第一个 0x 十六进制数（支持 0X）。"""
    m = _ADDR_RE.search(text or "")
    return int(m.group(0), 16) if m else None


def hx(value):
    return "0x%04x" % value


def plain(text):
    """去掉 markdown 强调标记，保留原文其它内容。"""
    return (text or "").replace("**", "").strip()


def bitdef_offset_tokens(cell):
    """位定义表首行 Offset 单元格 → (地址列表, 原文)。

    标量逗号列表逐项；含 `~` 的区间表达式整体算 1 项；NA ⇒ 0 项。
    """
    raw = plain(cell)
    text = _OFFSET_PREFIX_RE.sub("", cell.strip())
    text = text.replace("`", "").strip()
    if not text or text.upper() == "NA":
        return [], raw
    parts = [p.strip() for p in text.split(",") if p.strip()]
    has_range = any(("~" in p) or re.search(r"0[xX][0-9a-fA-F]+\s*[-—]", p)
                    for p in parts)
    if has_range:
        a = addr_of(parts[0])
        return ([a] if a is not None else []), raw
    out = []
    for p in parts:
        a = addr_of(p)
        if a is not None:
            out.append(a)
    return out, raw


def record_name(text):
    """从位定义表的「表格 X寄存器定义/位定义」行或最近的小节标题里取寄存器名。

    返回 (name, strength)：strength='title'（表格行/标题行，强）或 'field'（数据行 Name 列，弱）
    或 (None, None)。
    """
    m = _TABLE_TITLE_RE.match(plain(text))
    if m:
        nm = m.group(1).strip().strip("`")
        if nm:
            return nm, "title"
    return None, None


def heading_name(text):
    t = plain(text)
    t = re.sub(r"^#+\s*", "", t)
    m = _PAREN_RE.search(t)
    if m:
        return m.group(1).strip()
    # 去掉前导章节号（如 3.1.2.3.2.1）后若整体是 ASCII 标识符，则可用
    t2 = re.sub(r"^\d+(\.\d+)*\s*", "", t).strip()
    if _ASCII_NAME_RE.match(t2):
        return t2
    return None


# ---------------------------------------------------------------- 解析

def parse_doc(path):
    """把文档解析成 {seg_id: {'summary': [...], 'bitdef': [...]}} + 元信息。"""
    lines = read_lines(path)
    nlines = len(lines)

    # 标题 → 段
    heading_seg = []
    for idx, ln in enumerate(lines, 1):
        if not ln.lstrip().startswith("#"):
            continue
        for key, seg in HEADING_RULES:
            if key in ln:
                heading_seg.append((idx, seg))
                break

    def seg_at(line_no):
        cur = None
        for idx, seg in heading_seg:
            if idx < line_no:
                cur = seg
            else:
                break
        return cur

    seg_map = {}
    for seg in SEGMENTS:
        seg_map[seg["id"]] = {"summary": [], "bitdef": []}

    for (i0, i1) in table_blocks(lines):
        rows = lines[i0:i1]
        header = cells(rows[0])
        seg_id = seg_at(i0 + 1)
        if seg_id is None or seg_id not in seg_map:
            continue

        # ---- 段汇总表
        if header == SUMMARY_HEADER:
            data_rows = [k for k in range(1, len(rows)) if not is_sep(rows[k])]
            for k in data_rows:
                cs = cells(rows[k])
                if len(cs) < 1:
                    continue
                off_cell = cs[0]
                if "Offset" in off_cell:
                    continue  # 表内分组标题行（如 `...<br>Offset：0x0000`）
                a = addr_of(off_cell)
                if a is None:
                    continue
                name = cs[1] if len(cs) > 1 else ""
                if not name or name in EXCLUDE_NAMES:
                    continue
                rw = cs[2] if len(cs) > 2 else ""
                reset = cs[3] if len(cs) > 3 else ""
                byte = cs[4] if len(cs) > 4 else ""
                seg_map[seg_id]["summary"].append({
                    "offset_rel": a,
                    "line": i0 + 1 + k,
                    "name": name,
                    "rw": plain(rw),
                    "reset": plain(reset),
                    "bytes": int(byte) if byte.isdigit() else None,
                    "raw": rows[k],
                })
            continue

        # ---- 位定义表
        first_cell = cells(rows[0])[0] if cells(rows[0]) else ""
        if first_cell and _OFFSET_PREFIX_RE.match(first_cell):
            addrs, raw_off = bitdef_offset_tokens(first_cell)
            hdr_idx = None
            for k in range(1, len(rows)):
                cs = cells(rows[k])
                if cs and BITDEF_HEADER0.match(cs[0]):
                    hdr_idx = k
                    break
            data = []
            if hdr_idx is not None:
                for k in range(hdr_idx + 1, len(rows)):
                    if is_sep(rows[k]):
                        continue
                    cs = cells(rows[k])
                    if not cs or all(c == "" for c in cs):
                        continue
                    data.append({
                        "line": i0 + 1 + k,
                        "bits": cs[0],
                        "name": cs[1] if len(cs) > 1 else "",
                        "rw": plain(cs[3]) if len(cs) > 3 else "",
                        "reset": plain(cs[4]) if len(cs) > 4 else "",
                        "raw": rows[k],
                    })

            # 表名：优先最近「有名字的」标题（括号内 ASCII 名 / 纯 ASCII 标题），
            # 其次「表格 X寄存器定义」行（含中文的行视为模板残留，如
            # `表格 spi if ctl升级状态寄存器定义`，C 清单已登记此类问题）。
            hname = None
            for back in range(1, 13):
                if i0 - back < 0:
                    break
                ln = lines[i0 - back]
                if not ln.lstrip().startswith("#"):
                    continue
                nm = heading_name(ln)
                if nm:
                    hname = nm
                    break
            tname = None
            for back in range(1, 7):
                if i0 - back < 0:
                    break
                nm, _st = record_name(lines[i0 - back])
                if nm and not _CJK_RE.search(nm):
                    tname = nm
                    break
            name, strength = (None, None)
            if hname and tname and tname.startswith(hname) and tname != hname:
                name, strength = tname, "title"      # 表格名是标题名的扩展（标题漏字）
            elif hname:
                name, strength = hname, "title"
            elif tname:
                name, strength = tname, "title"
            if not name and data:
                for d in data:
                    nm = plain(d["name"])
                    if nm and nm not in EXCLUDE_NAMES and _ASCII_NAME_RE.match(nm):
                        name, strength = nm, "field"
                        break

            seg_map[seg_id]["bitdef"].append({
                "line": i0 + 1,
                "offset_raw": raw_off,
                "addrs": addrs,
                "title_name": name,
                "name_strength": strength,
                "rows": data,
            })
            continue

    return {
        "lines": lines,
        "nlines": nlines,
        "seg_map": seg_map,
    }


# ---------------------------------------------------------------- 统计

def compute_stats(parsed):
    segs = {}
    for seg in SEGMENTS:
        sid = seg["id"]
        base = seg["base"]
        sm = parsed["seg_map"][sid]
        named = []
        unique = []
        for row in sm["summary"]:
            g = (base + row["offset_rel"]) if base is not None else row["offset_rel"]
            named.append(row)
            if g not in unique:
                unique.append(g)
        bd_offsets = []
        for t in sm["bitdef"]:
            for a in t["addrs"]:
                g = a if (base is None or seg["bitdef_global"]) else base + a
                if g not in bd_offsets:
                    bd_offsets.append(g)
        segs[sid] = {
            "summary_named": len(named),
            "summary_unique": len(unique),
            "summary_unique_offsets": sorted(unique),
            "bitdef_tables": len(sm["bitdef"]),
            "bitdef_unique": len(bd_offsets),
            "bitdef_unique_offsets": sorted(bd_offsets),
        }
    totals = {
        "summary_named": sum(s["summary_named"] for s in segs.values()),
        "summary_unique": sum(s["summary_unique"] for s in segs.values()),
        "bitdef_tables": sum(s["bitdef_tables"] for s in segs.values()),
        "bitdef_unique": sum(s["bitdef_unique"] for s in segs.values()),
    }
    return segs, totals


# ---------------------------------------------------------------- 条目构建

def build_entries(parsed):
    entries = []
    for seg in SEGMENTS:
        if not seg["entries"]:
            continue
        sid = seg["id"]
        base = seg["base"]
        sm = parsed["seg_map"][sid]

        acc = {}  # global offset -> dict

        def slot(g):
            if g not in acc:
                acc[g] = {
                    "summary_rows": [], "bitdef_tables": [], "sources": [],
                }
            return acc[g]

        for row in sm["summary"]:
            g = base + row["offset_rel"]
            s = slot(g)
            s["summary_rows"].append(row)
            s["sources"].append({"kind": "summary", "line": row["line"]})

        for t in sm["bitdef"]:
            for a in t["addrs"]:
                g = a if seg["bitdef_global"] else base + a
                s = slot(g)
                if t not in s["bitdef_tables"]:
                    s["bitdef_tables"].append(t)
                s["sources"].append({"kind": "bitdef", "line": t["line"]})

        for g in sorted(acc):
            s = acc[g]
            srows = s["summary_rows"]
            bts = s["bitdef_tables"]

            # 名字：强标题名 > 汇总名 > 弱名（多 offset 共享表/字段名）
            name = None
            if len(bts) == 1 and bts[0]["name_strength"] == "title":
                name = bts[0]["title_name"]
            if name is None and srows:
                name = srows[0]["name"]
            if name is None:
                for t in bts:
                    if t["title_name"]:
                        name = t["title_name"]
                        break
            if name is None:
                name = hx(g)

            rw = ""
            for t in bts:
                for d in t["rows"]:
                    if d["rw"]:
                        rw = d["rw"]
                        break
                if rw:
                    break
            if not rw and srows:
                rw = srows[0]["rw"]
            if not rw:
                rw = "-"

            reset = ""
            for t in bts:
                for d in t["rows"]:
                    if d["reset"]:
                        reset = d["reset"]
                        break
                if reset:
                    break
            if not reset and srows:
                reset = srows[0]["reset"]
            if not reset:
                reset = "-"

            byte = None
            for row in srows:
                if row["bytes"] is not None:
                    byte = row["bytes"]
                    break

            raw = None
            if srows:
                raw = srows[0]["raw"]
            elif bts and bts[0]["rows"]:
                raw = bts[0]["rows"][0]["raw"]
            elif bts:
                raw = bts[0]["offset_raw"]

            entry = {
                "entry_id": "%s#%s" % (sid, hx(g)),
                "segment": sid,
                "offset_global": hx(g),
                "name": name,
                "rw": rw,
                "reset": reset,
                "bytes": byte,
                "bitdef_present": bool(bts),
                # 冲突↔条目 的关联写在 kb/conflicts/conflicts.json 的 linked_entries
                # （n1_conflicts.py 产出）；本脚本不反向依赖它，保持两脚本独立可复现。
                "conflict_ids": [],
                "sources": sorted(s["sources"], key=lambda x: (x["line"], x["kind"])),
            }
            if raw:
                entry["raw_line"] = plain(raw)
            entries.append(entry)

    entries.sort(key=lambda e: (e["segment"], int(e["offset_global"], 16)))
    return entries


# ---------------------------------------------------------------- 主流程

# 本脚本声明的时间字段（kb/README.md §3.1.1 弱判据用；脚本不得自取时钟）
TIME_FIELDS = ("generated_at",)
NOW_ENV = "KB_NOW"


def _has_now(args):
    return bool(args.now) or bool(os.environ.get(NOW_ENV))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="接口文档 → kb/index/regmap.json + regmap.csv（确定性）")
    ap.add_argument("--doc", default=DEFAULT_DOC, help="输入接口文档路径（默认 06 基准文档）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 regmap.json 路径（同目录写同名 .csv）")
    ap.add_argument("--now", default=None,
                    help="写入 generated_at 的时刻（ISO8601；等价环境变量 KB_NOW）。"
                         "未给时刻则不写该字段，默认调用逐字节可复现")
    ap.add_argument("--report", default=None, help="可选：把抽取口径统计写成本 JSON 文件")
    ap.add_argument("--quiet", action="store_true", help="只打印 FAIL/错误，不打印统计")
    args = ap.parse_args(argv)
    kb_lib.set_now(args.now)  # 时刻只经此入口；None ⇒ 回落 KB_NOW ⇒ 墙钟

    if not os.path.isfile(args.doc):
        sys.stderr.write("[FAIL] 输入文档不存在：%s\n" % args.doc)
        return 2

    parsed = parse_doc(args.doc)
    segs, totals = compute_stats(parsed)

    bad = []
    for key in ("summary_named", "summary_unique", "bitdef_tables", "bitdef_unique"):
        if totals[key] != EXPECTED_TOTAL[key]:
            bad.append("合计 %s = %d ≠ 基准 %d" % (key, totals[key], EXPECTED_TOTAL[key]))
    for sid, exp in EXPECTED_SEG.items():
        got = segs[sid]
        got4 = (got["summary_named"], got["summary_unique"],
                got["bitdef_tables"], got["bitdef_unique"])
        if got4 != exp:
            bad.append("段 %s (具名/去重/位定义表/位定义去重) = %s ≠ 基准 %s"
                       % (sid, got4, exp))

    entries = build_entries(parsed)

    if not args.quiet:
        print("[kb] source_doc = %s" % kb_lib.relpath(args.doc))
        print("[kb] doc_lines  = %d" % parsed["nlines"])
        print("[kb] time_fields = %s%s"
              % (",".join(TIME_FIELDS),
                 "" if _has_now(args) else "（本次未注入时刻 ⇒ 不写 generated_at）"))
        for key in ("summary_named", "summary_unique", "bitdef_tables", "bitdef_unique"):
            print("[stat] %-15s = %4d  (expected %d)" % (key, totals[key], EXPECTED_TOTAL[key]))
        for seg in SEGMENTS:
            g = segs[seg["id"]]
            print("[stat] seg %-7s 具名=%3d 去重=%3d 位定义表=%3d 位定义去重=%3d"
                  % (seg["id"], g["summary_named"], g["summary_unique"],
                     g["bitdef_tables"], g["bitdef_unique"]))
        print("[stat] entries_total = %d  (8 个 BAR0 段；SPI/IO 无 BAR0 映射，只计入上方抽取口径)"
              % len(entries))

    if bad:
        sys.stderr.write("[FAIL] 抽取口径与 06 §C 验收基准不符（%d 项）：\n" % len(bad))
        for b in bad:
            sys.stderr.write("  - %s\n" % b)
        return 1

    obj = {
        "schema": "kb/index/regmap",
        "version": 1,
        "source_doc": kb_lib.relpath(args.doc),
        "entries": entries,
    }
    if _has_now(args):
        obj["generated_at"] = kb_lib.now_iso()

    try:
        kb_lib.check(obj, "index", "regmap")
    except kb_lib.SchemaError as exc:
        sys.stderr.write("[FAIL] %s\n" % exc)
        return 3

    out = os.path.abspath(args.out)
    csv_path = os.path.splitext(out)[0] + ".csv"
    kb_lib.write_json(out, obj)
    header = ["entry_id", "segment", "offset_global", "name", "rw", "reset", "bytes",
              "bitdef_present", "summary_lines", "bitdef_lines"]
    rows = []
    for e in entries:
        sl = " ".join(str(s["line"]) for s in e["sources"] if s["kind"] == "summary")
        bl = " ".join(str(s["line"]) for s in e["sources"] if s["kind"] == "bitdef")
        rows.append([e["entry_id"], e["segment"], e["offset_global"], e["name"], e["rw"],
                     e["reset"], "" if e["bytes"] is None else e["bytes"],
                     "true" if e["bitdef_present"] else "false", sl, bl])
    kb_lib.write_csv(csv_path, header, rows)

    if args.report:
        rep = {
            "source_doc": kb_lib.relpath(args.doc),
            "doc_lines": parsed["nlines"],
            "expected_total": EXPECTED_TOTAL,
            "totals": totals,
            "segments": {
                seg["id"]: {
                    "summary_named": segs[seg["id"]]["summary_named"],
                    "summary_unique": segs[seg["id"]]["summary_unique"],
                    "bitdef_tables": segs[seg["id"]]["bitdef_tables"],
                    "bitdef_unique": segs[seg["id"]]["bitdef_unique"],
                    "summary_unique_offsets": [hx(v) for v in segs[seg["id"]]["summary_unique_offsets"]],
                    "bitdef_unique_offsets": [hx(v) for v in segs[seg["id"]]["bitdef_unique_offsets"]],
                } for seg in SEGMENTS
            },
            "entries_total": len(entries),
        }
        if _has_now(args):
            rep["generated_at"] = kb_lib.now_iso()
        kb_lib.write_json(args.report, rep)

    if not args.quiet:
        print("[kb] wrote %s" % kb_lib.relpath(out))
        print("[kb] wrote %s" % kb_lib.relpath(csv_path))
        print("[kb] sha256(%s) = %s" % (os.path.basename(out), kb_lib.sha256_file(out)))
        print("[kb] sha256(%s) = %s" % (os.path.basename(csv_path), kb_lib.sha256_file(csv_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
