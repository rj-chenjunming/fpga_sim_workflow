#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n2_diff.py —— N2 差异对比（Host 确定性，spec §2 N2 / §7；schema = kb/schema/n2_diff.schema.json）

**不上模型、不许随机**。同一输入连跑两次产出逐字节相同：无本机随机量、无字典序不稳，
所有列表排序确定，序列化走 `kb_lib.write_json`（`sort_keys` 口径）。

三路 diff（每条都带可复算的 `evidence` —— 下游 N3 的行号只能来自这里）
    ① `rtl_file`  自研设计代码快照逐文件 md5（`rtl_files.md5`，用 manifest.rtl_snapshot.manifest_sha256
                  复验）；**modified 的文件再解包两版 `rtl_snapshot.tar` 做文本 diff**，
                  抽取 `32'hXXXX_XXXX` / `0xXXXX` 这类地址字面量 ⇒ offsets（定位到 offset）
    ② `allfile`   全量文件清单 md5（parse `allfiles.md5`）；**只比两版 scope 交集**，
                  scope 只在单侧有的范围显式记入 `scope_notes`（不得静默当无差异）
    ③ `doc_entry` 文档条目集（regmap `entry_id` = `0xXXXX#0xYYYY` 条目级对比）⇒ 直接定位到
                  具体 offset（`entry_id` 无需从文本抽）

口径说明（写进 n2_diff.md）
    * offset 来源两条：①路 hunk 新增/删除行里的地址字面量 + ③路 `entry_id` 直接取
      （段基址+块内偏移：hunk 里的字面量按块内偏移理解，N5 会用 `segment_rtl.json` 把
      文件映射到段后换算全局地址）；抽不出 ⇒ 该条 `unresolved` 说明，**不丢条目**。
    * 条目集路径推导（task-9 N2-1）：**主口径 = `dirname(manifest.doc_fingerprint.path)/doc_entries.jsonl`**
      （`n1_snapshot.py` 的 `collect_doc_fingerprint` 一次写 `doc_entries.txt` 与 `doc_entries.jsonl` 到同目录）；
      回退链 `→ <manifest>/bundle/doc_entries.jsonl → <manifest>/doc_entries.jsonl → kb/index/regmap.json`，
      **用回退必写进 notes**（回退会掩盖"该版没落盘"）。
    * 非 UTF-8 源码（task-9 N2-3）：hunk 解码按 `utf-8 → gbk → latin-1` 回退（工程内 5 个自有 RTL 是 GBK，
      先例见 `doc/tools/extract_sys_reg.py` docstring）；实际编码写进该条 diff 的 `encoding` 与 `evidence`。
      只有含 NUL 字节的真二进制才保留 `unresolved`。
    * 缺口产物（task-9 N2-2，裁定 (a)）：存在 blocking 缺口时**不产生** `n2_diff.json`，
      缺口报告写 `n2_diff.gap.json` + `n2_diff.gap.md`（首行标「不完整，不得作为 N3 输入」）。
    * 通用纪律（task-10）：**目标产物已存在即 rc!=0，绝不覆盖**；复跑请换 run_id/--out-dir，
      或显式 `--overwrite`。
    * 时间字段（README §3.1.1）：本脚本声明的时间字段清单 = `("generated_at",)`；
      一律走 `kb_lib.now_iso()`，并在 main() 里 `if args.now: K.set_now(args.now)` 注入
      （等价环境变量 `KB_NOW`）。**时间字段是唯一被允许的非确定性**：
      强判据 = 同一输入 + 同一 `--now` 连跑两次逐字节相同；
      弱判据 = 同一输入 + 不同 `--now` 两次，`K.sha256_obj_normalized(obj,("generated_at",))` 相同。

退出码
    0 成功（含 `has_change=false` 的「无变化」）  2 用法  3 输入/契约缺口  4 self-check 失败
"""

import argparse
import difflib
import json
import os
import re
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

RC_OK = 0
RC_USAGE = 2
RC_GAP = 3
RC_SELFCHECK = 4

SCHEMA_NAME = "n2_diff"
SCHEMA_JSON = "kb/schema/n2_diff.schema.json"
HUNK_LIMIT = 4000          # 单文件 hunk 入库上限（超出截断并在 notes 记明）
OFFSET_MAX = 0x1FFFF       # 段基址最大 0x10000，offset 取 5 位十六进制以内

ADDR_32H = re.compile(r"32'h([0-9a-fA-F][0-9a-fA-F_]*)")
ADDR_0X = re.compile(r"\b0x([0-9a-fA-F][0-9a-fA-F_]*)\b")
HUNK_HDR = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

ENTRY_FIELDS = ("segment", "offset_global", "name", "rw", "reset", "bytes", "bitdef_present")


class InputGap(Exception):
    """输入/契约缺口 ⇒ rc=3（不许静默给空清单）。"""


# ---------------------------------------------------------------- 输入

def load_manifest(path):
    if not os.path.exists(path):
        raise InputGap("manifest 不存在：%s" % K.relpath(path))
    m = K.read_json(path)
    for k in ("baseline", "rtl_snapshot", "allfiles_manifest", "doc_fingerprint"):
        if k not in m:
            raise InputGap("manifest 缺字段 %r：%s" % (k, K.relpath(path)))
    return m


def now_source(args):
    if args.now:
        return "--now"
    if os.environ.get("KB_NOW"):
        return "KB_NOW"
    return "wallclock(kb_lib.now_iso)"


def parse_md5_listing(path):
    """解析 `md5sum` 清单 → {relpath: (md5, lineno)}；损坏即 InputGap。"""
    if not os.path.exists(path):
        raise InputGap("逐文件 md5 清单不存在：%s" % K.relpath(path))
    rows = {}
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        for ln, raw in enumerate(f, 1):
            s = raw.rstrip("\n")
            if not s.strip():
                continue
            parts = s.split("  ", 1)
            if len(parts) != 2:
                parts = s.split(None, 1)
            if len(parts) != 2:
                raise InputGap("逐文件 md5 清单格式不合法（%s:L%d）：%r"
                               % (K.relpath(path), ln, s))
            digest, rel = parts[0].strip(), parts[1].strip()
            if len(digest) != 32 or any(c not in "0123456789abcdef" for c in digest):
                raise InputGap("md5 不合法（%s:L%d）：%r" % (K.relpath(path), ln, digest))
            if not rel:
                raise InputGap("清单缺路径（%s:L%d）" % (K.relpath(path), ln))
            rows[rel] = (digest, ln)
    if not rows:
        raise InputGap("逐文件 md5 清单为空：%s" % K.relpath(path))
    return rows


def resolve_rtl_md5(manifest, explicit):
    """① 路：显式 > `rtl_snapshot.path` 同目录的 `rtl_files.md5`（与 n1_snapshot.py 一致）。"""
    if explicit:
        return explicit
    tar_rel = manifest["rtl_snapshot"]["path"]
    return os.path.join(os.path.dirname(K.root_path(tar_rel)), "rtl_files.md5")


def resolve_allfiles(manifest, explicit):
    if explicit:
        return explicit
    return K.root_path(manifest["allfiles_manifest"]["path"])


def resolve_tar(manifest, explicit):
    if explicit:
        return explicit
    return K.root_path(manifest["rtl_snapshot"]["path"])


ENTRY_FALLBACK_TAG = "回退"


def entry_candidates(manifest, manifest_path, side, explicit):
    """③ 路条目集候选（按优先级）→ [(path, label)]。

    主口径 = `dirname(manifest.doc_fingerprint.path)/doc_entries.jsonl`（task-9 N2-1 定稿）；
    之后依次回退 `<manifest>/bundle/doc_entries.jsonl`、`<manifest>/doc_entries.jsonl`、
    `kb/index/regmap.json`（末级兜底会掩盖"该版没落盘"，故使用时必须记 notes）。
    """
    md = os.path.dirname(os.path.abspath(manifest_path))
    out = []
    if explicit:
        out.append((explicit, "显式 --%s-entries" % side))
    dfp = ((manifest.get("doc_fingerprint") or {}).get("path") or "")
    if dfp:
        out.append((os.path.join(os.path.dirname(K.root_path(dfp)), "doc_entries.jsonl"),
                    "manifest.doc_fingerprint.path 同目录（主口径）"))
    out.append((os.path.join(md, "bundle", "doc_entries.jsonl"),
                "%s %s/bundle/doc_entries.jsonl" % (ENTRY_FALLBACK_TAG, side)))
    out.append((os.path.join(md, "doc_entries.jsonl"),
                "%s %s 同目录/doc_entries.jsonl" % (ENTRY_FALLBACK_TAG, side)))
    out.append((K.kb_path("index", "regmap.json"),
                "%s kb/index/regmap.json（末级）" % ENTRY_FALLBACK_TAG))
    return out


def resolve_entries(manifest, manifest_path, side, explicit, notes):
    cands = entry_candidates(manifest, manifest_path, side, explicit)
    for path, label in cands:
        if os.path.exists(path):
            if not explicit and ENTRY_FALLBACK_TAG in label:
                notes.append("③ 路 %s 版条目集走了**回退**（%s ⇒ %s）：回退会掩盖『该版未落盘』，"
                             "请核对 %s 的 doc_fingerprint.path 同目录产物"
                             % (side, label, K.relpath(path), side))
            return path, label
    raise InputGap("文档条目集一个候选都不存在（%s 版）：%s\n"
                   "      ⇒ 先跑 n1_doc_entries.py 生成 kb/index/regmap.json，"
                   "再由 n1_snapshot.py 落 <bundle>/doc_entries.jsonl"
                   % (side, "; ".join(K.relpath(p) for p, _ in cands)))


def load_entries(path, where):
    if not os.path.exists(path):
        raise InputGap("文档条目集不存在（%s）：%s\n"
                       "      ⇒ 先跑 n1_doc_entries.py 生成 kb/index/regmap.json，"
                       "再由 n1_snapshot.py 落 doc_entries.jsonl" % (where, K.relpath(path)))
    if path.endswith(".jsonl"):
        rows = K.read_jsonl(path)
    else:
        obj = K.read_json(path)
        if isinstance(obj, dict):
            rows = obj.get("entries")
            if rows is None:
                raise InputGap("条目集 JSON 缺 entries：%s" % K.relpath(path))
        elif isinstance(obj, list):
            rows = obj
        else:
            raise InputGap("条目集 JSON 形态不支持：%s" % K.relpath(path))
    out = {}
    for i, e in enumerate(rows):
        if not isinstance(e, dict) or not e.get("entry_id"):
            raise InputGap("条目缺 entry_id（%s entries[%d]）" % (K.relpath(path), i))
        out[str(e["entry_id"])] = e
    if not out:
        raise InputGap("条目集为空：%s" % K.relpath(path))
    return out


def canon_seg(s):
    """段字面量规范化成小写十六进制（schema 的段 pattern 只允许 [0-9a-f]）。"""
    if s is None:
        return None
    t = str(s).strip().lower().replace("_", "")
    if not t.startswith("0x"):
        return str(s)
    try:
        v = int(t, 16)
    except ValueError:
        return str(s)
    return "0x%04x" % v if v <= 0xFFFF else "0x%05x" % v


def canon_hex(s):
    """offset/addr 字面量规范化成 0x<小写十六进制>；不可解析则原样。"""
    if s is None:
        return None
    t = str(s).strip().lower().replace("_", "")
    try:
        v = int(t, 16) if t.startswith("0x") else int(t, 10)
    except ValueError:
        return str(s)
    return "0x%x" % v


def entry_projection(e):
    return {k: e.get(k) for k in ENTRY_FIELDS}


def entry_sources(e):
    out = []
    for s in e.get("sources", []) or []:
        if isinstance(s, dict) and s.get("line") is not None:
            out.append((str(s.get("kind")), int(s["line"])))
    out.sort(key=lambda x: (str(x[0]), x[1]))
    return out


def scope_prefixes(manifest):
    art = manifest.get("allfiles_manifest") or {}
    out = []
    for s in (art.get("scope") or []):
        s = str(s).replace(os.sep, "/").strip().rstrip("/")
        if s:
            out.append(s)
    return sorted(set(out))


def in_scope(rel, prefixes):
    if not prefixes:
        return True
    return any(rel == p or rel.startswith(p + "/") for p in prefixes)


# ---------------------------------------------------------------- tar / 文本 diff

def read_tar_members(tar_path):
    """{member_name: bytes}；tar 缺失 ⇒ InputGap。"""
    if not os.path.exists(tar_path):
        raise InputGap("RTL 快照 tar 不存在：%s" % K.relpath(tar_path))
    out = {}
    with tarfile.open(tar_path, "r") as tf:
        for ti in tf.getmembers():
            if not ti.isfile():
                continue
            f = tf.extractfile(ti)
            out[ti.name] = f.read() if f is not None else b""
    return out


DECODE_ENCODINGS = ("utf-8", "gbk", "latin-1")   # task-9 N2-3：工程内 5 个自有 RTL 是 GBK


def decode_source(b):
    """按 utf-8 → gbk → latin-1 回退解码；含 NUL 字节视为真二进制 ⇒ (None, None)。"""
    if b"\x00" in b:
        return None, None
    for enc in DECODE_ENCODINGS:
        try:
            return b.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return None, None


def text_diff(old_bytes, new_bytes, limit=HUNK_LIMIT):
    """确定性文本 hunk：返回 dict（含实际使用的 encoding）或 None（含 NUL 的真二进制）。"""
    o, enc_o = decode_source(old_bytes)
    n, enc_n = decode_source(new_bytes)
    if o is None or n is None:
        return None
    enc = enc_o if enc_o == enc_n else ("%s/%s" % (enc_o, enc_n))
    ud = list(difflib.unified_diff(o.splitlines(), n.splitlines(),
                                   lineterm="", n=3))
    if not ud:
        return {"hunk": "", "added_lines": [], "removed_lines": [], "new_lines": [],
                "encoding": enc}
    added, removed, new_lines = [], [], []
    cur = None
    for ln in ud:
        if ln.startswith("---") or ln.startswith("+++"):
            continue
        m = HUNK_HDR.match(ln)
        if m:
            cur = int(m.group(1))
            continue
        if cur is None:
            continue
        if ln.startswith("+"):
            added.append(ln[1:])
            new_lines.append(cur)
            cur += 1
        elif ln.startswith("-"):
            removed.append(ln[1:])
        elif ln.startswith(" "):
            cur += 1
    hunk = "\n".join(ud)
    return {"hunk": hunk[:limit], "added_lines": added, "removed_lines": removed,
            "new_lines": sorted(set(new_lines)), "encoding": enc}


def extract_offsets(lines):
    """从 hunk 的新增/删除行里抽地址字面量 → [(value_int, raw)]（去重、升序）。"""
    found = {}
    for text in lines:
        for pat in (ADDR_32H, ADDR_0X):
            for m in pat.finditer(text):
                raw = m.group(0)
                digits = m.group(1).replace("_", "")
                try:
                    v = int(digits, 16)
                except ValueError:
                    continue
                if v > OFFSET_MAX:
                    continue
                found.setdefault(v, raw)
    return sorted(found.items())


# ---------------------------------------------------------------- diff 记录

def diff_md5_rows(old, new, kind, old_label, new_label, scope_prefixes_=None):
    recs = []
    for rel in sorted(set(old) | set(new)):
        if scope_prefixes_ is not None and not in_scope(rel, scope_prefixes_):
            continue
        rec = {"kind": kind, "id": rel, "change": None, "before": None, "after": None,
               "evidence": "", "lines": [], "offsets": [], "unresolved": None,
               "diff_hunk": None}
        o, n = old.get(rel), new.get(rel)
        if o and not n:
            rec["change"] = "removed"
            rec["before"] = o[0]
            rec["evidence"] = "%s:L%d（仅旧版有；旧版正文不在 KB，无 hunk）" % (old_label, o[1])
            rec["unresolved"] = "文件已被删除：行号/offset 需人工或 N3 从交付包定位"
        elif n and not o:
            rec["change"] = "added"
            rec["after"] = n[0]
            rec["evidence"] = "%s:L%d（仅新版有；无旧版正文，无 hunk）" % (new_label, n[1])
            rec["unresolved"] = "新增文件：行号/offset 需人工或 N3 从新包定位"
        elif o[0] != n[0]:
            rec["change"] = "modified"
            rec["before"], rec["after"] = o[0], n[0]
            rec["evidence"] = "%s:L%d -> %s:L%d（逐文件 md5 变化）" % (old_label, o[1], new_label, n[1])
            if kind == "allfile":
                rec["unresolved"] = ("② 路只比逐文件 md5 清单，无文本 hunk（旧版正文不在 KB）"
                                     "⇒ offset 由 ①/③ 路提供；本条已按『modified』计入差异")
        else:
            continue
        recs.append(rec)
    return recs


def enrich_rtl_hunks(recs, old_tar, new_tar, notes):
    """① 路 modified 文件：解包两版 tar 做文本 diff，填 lines/offsets/diff_hunk。"""
    need = [r for r in recs if r["kind"] == "rtl_file" and r["change"] == "modified"]
    if not need:
        return recs
    old_members = read_tar_members(old_tar)
    new_members = read_tar_members(new_tar)
    for r in need:
        rel = r["id"]
        if rel not in old_members or rel not in new_members:
            r["unresolved"] = ("tar 内未找到该文件（old=%s new=%s）⇒ 无 hunk"
                               % (rel in old_members, rel in new_members))
            notes.append("① 路 %s：两版 tar 内未同时找到该成员，改用 md5 结论" % rel)
            continue
        td = text_diff(old_members[rel], new_members[rel])
        if td is None:
            r["unresolved"] = ("含 NUL 字节的真二进制（非文本源码）⇒ 无数值 hunk，offset 需人工；"
                               "文本源码已穷尽 utf-8→gbk→latin-1 回退")
            continue
        r["encoding"] = td.get("encoding")
        r["diff_hunk"] = td["hunk"] or None
        if td.get("encoding") not in (None, "utf-8"):
            r["evidence"] += ("；hunk 解码编码=%s（非 UTF-8；工程内 GBK RTL 先例见 "
                              "doc/tools/extract_sys_reg.py）" % td["encoding"])
            notes.append("① 路 %s：GBK/非 UTF-8 源码，按 %s 回退解码成功（仍能抽 offset）"
                         % (rel, td["encoding"]))
        r["lines"] = td["new_lines"]
        offs = extract_offsets(td["added_lines"] + td["removed_lines"])
        r["offsets"] = ["0x%x" % v for v, _ in offs]
        r["_offset_raw"] = {"0x%x" % v: raw for v, raw in offs}
        if not offs:
            r["unresolved"] = ("hunk 里未抽到地址字面量（32'hXXXX / 0xXXXX）⇒ "
                               "offset 交由 ③ 路或人工补")
        if td["hunk"] and len(td["hunk"]) >= HUNK_LIMIT:
            notes.append("① 路 %s 的 hunk 超过 %d 字符已截断（N3/人工可回看 tar）"
                         % (rel, HUNK_LIMIT))
    return recs


def diff_entries(old, new, old_label, new_label):
    recs = []
    for eid in sorted(set(old) | set(new)):
        o, n = old.get(eid), new.get(eid)
        src = n if n is not None else o
        src_lines = entry_sources(src)
        src_seg = canon_seg(src.get("segment")) or src.get("segment")
        loc = "entry_id=%s segment=%s offset_global=%s" % (
            eid, src_seg, src.get("offset_global"))
        rec = {"kind": "doc_entry", "id": eid, "change": None, "before": None, "after": None,
               "evidence": "", "lines": [], "offsets": [], "unresolved": None,
               "diff_hunk": None, "entry_id": eid,
               "segment": src_seg, "offset": canon_hex(src.get("offset_global"))
               if src.get("offset_global") not in (None, "NA") else None}
        off = src.get("offset_global")
        if off and off != "NA":
            rec["offsets"] = [canon_hex(off)]
        else:
            rec["unresolved"] = "该条目 offset_global=NA（段未登记/文档无 offset）⇒ 转人工，不建映射"
        if o is not None and n is None:
            rec["change"] = "removed"
            rec["before"] = K.canon_json(entry_projection(o)).rstrip("\n")
            rec["evidence"] = ("%s[%s] sources=%s（仅旧版有）"
                               % (old_label, loc, ",".join("%s:%d" % t for t in src_lines)))
        elif n is not None and o is None:
            rec["change"] = "added"
            rec["after"] = K.canon_json(entry_projection(n)).rstrip("\n")
            rec["evidence"] = ("%s[%s] sources=%s（仅新版有）"
                               % (new_label, loc, ",".join("%s:%d" % t for t in src_lines)))
        else:
            po = K.canon_json(entry_projection(o))
            pn = K.canon_json(entry_projection(n))
            if po == pn:
                continue
            rec["change"] = "modified"
            rec["before"], rec["after"] = po.rstrip("\n"), pn.rstrip("\n")
            fields = ["%s:%s->%s" % (f, o.get(f), n.get(f))
                      for f in ENTRY_FIELDS if o.get(f) != n.get(f)]
            rec["evidence"] = ("%s[%s] sources=%s 字段变更[%s]"
                               % (new_label, loc, ",".join("%s:%d" % t for t in src_lines),
                                  "; ".join(fields)))
        if src_lines:
            rec["lines"] = [src_lines[0][1]]
        recs.append(rec)
    return recs


# ---------------------------------------------------------------- 报告

def route_stat(recs, kind, entries_from, entries_to, extra=None):
    st = {"entries_from": entries_from, "entries_to": entries_to,
          "changed": sum(1 for r in recs if r["kind"] == kind and r["change"] == "modified"),
          "added": sum(1 for r in recs if r["kind"] == kind and r["change"] == "added"),
          "removed": sum(1 for r in recs if r["kind"] == kind and r["change"] == "removed")}
    if extra:
        st.update(extra)
    return st


def write_md(path, out, meta, gap=False):
    L = []
    if gap:
        L.append("> ⚠ **不完整，不得作为 N3 输入**：本轮存在 blocking 输入缺口（见文末「输入缺口」）"
                 "⇒ 本文件是 `n2_diff.gap.md`，**没有**产出 `n2_diff.json`。\n")
    L.append("# N2 差异对比（Host 确定性，spec §2 N2 / schema `n2_diff`）\n")
    L.append("- run_id：`%s`｜generated_at：`%s`" % (out["run_id"], out["generated_at"]))
    L.append("- from：`%s`（`%s`）" % (out["from"]["baseline"], out["from"]["manifest_path"]))
    L.append("- to  ：`%s`（`%s`）" % (out["to"].get("baseline"), out["to"]["manifest_path"]))
    L.append("- 结论：**%s**" % ("无变化" if not out["has_change"] else "有变化"))
    if out.get("no_change_statement"):
        L.append("- 无变化声明：%s" % out["no_change_statement"])
    L.append("\n## 三路统计\n")
    L.append("| 路 | entries_from | entries_to | modified | added | removed |")
    L.append("|---|---|---|---|---|---|")
    for k, name in (("rtl_files", "① rtl_file"), ("allfiles", "② allfile"),
                    ("doc_entries", "③ doc_entry")):
        st = out["routes"][k]
        L.append("| %s | %d | %d | %d | %d | %d |"
                 % (name, st["entries_from"], st["entries_to"], st["changed"],
                    st["added"], st["removed"]))
    a = out["routes"]["allfiles"]
    if a.get("scope") is not None:
        L.append("\n② 路 scope：`%s`｜交集 `%s`｜只在旧版 `%s`｜只在新版 `%s`"
                 % (a.get("scope"), a.get("scope_intersection"),
                    a.get("only_in_from"), a.get("only_in_to")))
    L.append("\n## 差异条目（每条带 evidence，下游 N3 的行号唯一来源）\n")
    L.append("| kind | id | change | before | after | evidence | lines | offsets |")
    L.append("|---|---|---|---|---|---|---|---|")
    for d in out["diffs"]:
        b, af = (d.get("before") or "-"), (d.get("after") or "-")
        if d["kind"] == "doc_entry":
            b, af = "`%s`" % _short(b), "`%s`" % _short(af)
        L.append("| %s | `%s` | %s | %s | %s | %s | %s | %s |"
                 % (d["kind"], d["id"], d["change"], b, af, d["evidence"],
                    d.get("lines") or "-", d.get("offsets") or "-"))
    unres = [d for d in out["diffs"] if d.get("unresolved")]
    if unres:
        L.append("\n## 无法定位的条目（不丢条目，给 unresolved 说明）\n")
        for d in unres:
            L.append("- `%s`（%s）：%s" % (d["id"], d["kind"], d["unresolved"]))
    if out.get("offsets"):
        L.append("\n## 抽出的 offset（供 N5 段粗筛后与用例访问求交）\n")
        L.append("| offset | kind | 来源 | entry_id |")
        L.append("|---|---|---|---|")
        for o in out["offsets"]:
            L.append("| `%s` | %s | `%s` | %s |" % (o["value"], o["kind"], o["source"],
                                                    o.get("entry_id") or "-"))
    L.append("\n## 口径说明\n")
    L.append("- offset 两条来源：①路 hunk 新增/删除行里的地址字面量（`32'hXXXX_XXXX`、`0xXXXX`，"
             "按**块内偏移**理解，N5 用 `segment_rtl.json` 映射到段后换算 `<段基址>+<块内偏移>`）；"
             "③路 `entry_id` 的 `offset_global`**直接**作为 offset（无需从文本抽）。")
    L.append("- 归一化指纹复算口径（task-18 / F-DET-01）：`checks.normalized_sha256 = "
             "sha256(canon_json(本对象 **剔除 `checks`** 后，把 `generated_at` 替换为 `\"<TIMESTAMP>\"`))` —— "
             "按 README §3.1.1 的字面公式**必须先剔除自指簿记键**才能复算。"
             "被剔除键清单：`[\"checks\"]`（其中含本字段自身）；被归一化的时间字段：`[\"generated_at\"]`。"
             "本件自报值见 `checks.normalized_sha256`。")
    L.append("- `generated_at` 是**唯一**被允许的非确定性字段（README §3.1.1，本脚本声明时间字段 "
             "`(\"generated_at\",)`）；一律经 `kb_lib.now_iso()`，`--now`/`KB_NOW` 注入。"
             "强判据：同一输入 + 同一 `--now` 两次逐字节相同；弱判据：不同 `--now` 两次，"
             "`K.sha256_obj_normalized(obj, (\"generated_at\",))` 相同。")
    L.append("- ②路只比两版 `allfiles_manifest.scope` 交集；scope 只在单侧有的范围内文件**不可比**，"
             "记入 `scope_notes`，不静默当无差异。")
    if out.get("scope_notes"):
        L.append("\n## scope / 其他说明\n")
        for n in out["scope_notes"]:
            L.append("- %s" % n)
    if out.get("index_gaps"):
        L.append("\n## 输入缺口（转人工）\n")
        for g in out["index_gaps"]:
            L.append("- `%s`%s：%s" % (g["kind"], "（blocking）" if g.get("blocking") else "",
                                       g["detail"]))
        if out.get("blocking_gap"):
            L.append("\n**本轮 blocking 缺口导致不产出 `n2_diff.json`（task-9 N2-2 裁定 (a)）。**")
    if out.get("stale_n2_diff"):
        L.append("\n> 注意：目录里仍存在上一次的 `n2_diff.json`（sha256 `%s`），它对应**不同输入**，"
                 "本轮未覆盖也未删除，**不得作为本轮 N3 输入**。"
                 % out["stale_n2_diff"]["sha256"])
    de = out["routes"]["doc_entries"]
    L.append("\n③ 路条目集解析：旧版 = `%s`（%s）；新版 = `%s`（%s）；用了回退=%s"
             % (de.get("entries_from_path"), de.get("entries_from_resolved_by"),
                de.get("entries_to_path"), de.get("entries_to_resolved_by"),
                de.get("used_fallback")))
    encs = sorted(set(d.get("encoding") for d in out["diffs"] if d.get("encoding")))
    if encs:
        L.append("① 路 hunk 解码编码：%s（非 UTF-8 走 gbk/latin-1 回退；task-9 N2-3）"
                 % ", ".join(str(e) for e in encs))
    L.append("")
    return K.write_text(path, "\n".join(L) + "\n")


def refuse_if_exists(targets, overwrite):
    """通用纪律（task-10 追加到 n2）：目标已存在即 rc!=0，绝不覆盖（归档只增不改）。"""
    if overwrite:
        return
    for t in targets:
        if os.path.exists(t):
            sys.stderr.write("[FAIL] 目标已存在，拒绝覆盖（归档只增不改）：%s\n"
                             "       ⇒ 换 run_id/--out-dir，或显式 --overwrite 复跑\n"
                             % K.relpath(t))
            raise SystemExit(RC_GAP)


def _short(s, n=90):
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N2 差异对比（三路确定性：RTL 逐文件 md5 + hunk offset 抽取 / 全量清单 md5 / 文档条目集）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功（含无变化） / 2 用法 / 3 输入或契约缺口 / 4 self-check 失败")
    ap.add_argument("--from-manifest", default=None, help="旧版 manifest.json")
    ap.add_argument("--from-baseline", default=None,
                    help="旧版基线号（如 v0）⇒ kb/baselines/<v>/manifest.json")
    ap.add_argument("--to-manifest", required=True,
                    help="新版 manifest（N1 草案：kb/runs/<run_id>/n1_manifest_new.json）")
    ap.add_argument("--run", default=None, help="run_id（默认从 --to-manifest 目录推导）")
    ap.add_argument("--out-dir", default=None, help="产出目录（默认 kb/runs/<run_id>）")
    ap.add_argument("--overwrite", action="store_true",
                    help="允许覆盖已存在的目标产物（默认：目标已存在即 rc!=0，绝不覆盖；"
                         "归档只增不改，复跑请换 run_id/--out-dir 或显式加本开关）")
    ap.add_argument("--now", default=None,
                    help="注入时间字段 generated_at（ISO8601；等价环境变量 KB_NOW）；"
                         "同一输入 + 同一 --now 两次 ⇒ 输出逐字节相同（README §3.1.1）")
    ap.add_argument("--from-rtl-md5", default=None)
    ap.add_argument("--to-rtl-md5", default=None)
    ap.add_argument("--from-allfiles", default=None)
    ap.add_argument("--to-allfiles", default=None)
    ap.add_argument("--from-entries", default=None)
    ap.add_argument("--to-entries", default=None)
    ap.add_argument("--from-rtl-tar", default=None, help="① 路旧版 tar（默认 manifest 里的 path）")
    ap.add_argument("--to-rtl-tar", default=None)
    args = ap.parse_args(argv)
    if args.now:
        K.set_now(args.now)   # README §3.1.1：时间字段的唯一注入入口

    if not args.from_manifest and not args.from_baseline:
        ap.error("必须给 --from-manifest 或 --from-baseline")
    if args.from_baseline and not (args.from_baseline.startswith("v")
                                   and args.from_baseline[1:].isdigit()):
        ap.error("--from-baseline 必须形如 v0/v1")
    from_manifest = args.from_manifest or K.kb_path("baselines", args.from_baseline, "manifest.json")

    run_id = args.run
    out_dir = args.out_dir
    if not out_dir:
        tm_dir = os.path.dirname(os.path.abspath(args.to_manifest))
        if tm_dir.startswith(K.run_dir("") + os.sep):
            run_id = run_id or os.path.basename(tm_dir)
            out_dir = tm_dir
        elif run_id:
            out_dir = K.run_dir(run_id)
        else:
            ap.error("无法推导产出目录：给 --out-dir 或 --run（或让 --to-manifest 位于 "
                     "kb/runs/<run_id>/ 下）")
    if not run_id:
        run_id = "RUN-19700101-000000"
        sys.stderr.write("[WARN] 未给 --run 且无法从路径推导 ⇒ run_id 写占位 %s\n" % run_id)
    if not re.match(r"^RUN-[0-9]{8}-[0-9]{6}$", run_id):
        sys.stderr.write("[WARN] run_id=%r 不符合 schema 的 ^RUN-YYYYMMDD-HHMMSS$；"
                         "schema 校验会失败\n" % run_id)

    gaps, notes, recs = [], [], []
    inputs = {}
    try:
        fm = load_manifest(from_manifest)
        tm = load_manifest(args.to_manifest)
    except InputGap as e:
        sys.stderr.write("[FAIL] %s\n" % e)
        return RC_GAP
    inputs["from_manifest"] = {"path": K.relpath(from_manifest),
                               "sha256": K.sha256_file(from_manifest)}
    inputs["to_manifest"] = {"path": K.relpath(args.to_manifest),
                             "sha256": K.sha256_file(args.to_manifest)}

    # ---- ① RTL 逐文件 md5（+ hunk offset）
    rtl_ok = True
    f_rtl_n = t_rtl_n = 0
    try:
        f_rtl_path = resolve_rtl_md5(fm, args.from_rtl_md5)
        t_rtl_path = resolve_rtl_md5(tm, args.to_rtl_md5)
        f_rtl = parse_md5_listing(f_rtl_path)
        t_rtl = parse_md5_listing(t_rtl_path)
        f_rtl_n, t_rtl_n = len(f_rtl), len(t_rtl)
        for tag, man, p in (("from", fm, f_rtl_path), ("to", tm, t_rtl_path)):
            exp = man["rtl_snapshot"].get("manifest_sha256")
            got = K.sha256_file(p)
            if exp and exp != got:
                raise InputGap("① 路清单指纹与 manifest 不符（%s）：%s manifest_sha256=%s 实际=%s"
                               % (tag, K.relpath(p), exp, got))
        r_rtl = diff_md5_rows(f_rtl, t_rtl, "rtl_file", K.relpath(f_rtl_path),
                              K.relpath(t_rtl_path))
        r_rtl = enrich_rtl_hunks(r_rtl, resolve_tar(fm, args.from_rtl_tar),
                                 resolve_tar(tm, args.to_rtl_tar), notes)
        recs += r_rtl
        inputs["rtl_files_md5_from"] = {"path": K.relpath(f_rtl_path),
                                        "sha256": K.sha256_file(f_rtl_path), "entries": len(f_rtl)}
        inputs["rtl_files_md5_to"] = {"path": K.relpath(t_rtl_path),
                                      "sha256": K.sha256_file(t_rtl_path), "entries": len(t_rtl)}
        inputs["rtl_snapshot_sha256_from"] = {"path": fm["rtl_snapshot"]["path"],
                                             "sha256": fm["rtl_snapshot"]["sha256"]}
        inputs["rtl_snapshot_sha256_to"] = {"path": tm["rtl_snapshot"]["path"],
                                           "sha256": tm["rtl_snapshot"]["sha256"]}
    except InputGap as e:
        rtl_ok = False
        gaps.append({"kind": "rtl_file", "blocking": True, "detail": str(e),
                     "action": "补/修 ①路逐文件清单或 tar 后重跑 n2_diff.py"})

    # ---- ② 全量清单（scope 交集）
    allf_ok = True
    f_all_n = t_all_n = 0
    sc_from = sc_to = scope = None
    try:
        f_all = parse_md5_listing(resolve_allfiles(fm, args.from_allfiles))
        t_all = parse_md5_listing(resolve_allfiles(tm, args.to_allfiles))
        f_all_n, t_all_n = len(f_all), len(t_all)
        for tag, man, p in (("from", fm, resolve_allfiles(fm, args.from_allfiles)),
                            ("to", tm, resolve_allfiles(tm, args.to_allfiles))):
            exp = man["allfiles_manifest"].get("sha256")
            got = K.sha256_file(p)
            if exp and exp != got:
                raise InputGap("② 路清单 sha256 与 manifest 不符（%s）：%s manifest=%s 实际=%s"
                               % (tag, K.relpath(p), exp, got))
        sc_from, sc_to = scope_prefixes(fm), scope_prefixes(tm)
        scope = sorted(set(sc_from) & set(sc_to))
        only_from = sorted(set(sc_from) - set(sc_to))
        only_to = sorted(set(sc_to) - set(sc_from))
        if not scope:
            scope = sorted(set(sc_from) | set(sc_to))
            notes.append("② 路两版 scope 无交集（from=%r to=%r）⇒ 退化为并集 %r 比较，宁多勿漏"
                         % (sc_from, sc_to, scope))
        if only_from or only_to:
            notes.append("② 路 scope 只在旧版有=%r、只在新版有=%r ⇒ 这些范围内文件"
                         "**不可比**（不得当无差异），已记入 scope_notes" % (only_from, only_to))
        recs += diff_md5_rows(f_all, t_all, "allfile",
                              K.relpath(resolve_allfiles(fm, args.from_allfiles)),
                              K.relpath(resolve_allfiles(tm, args.to_allfiles)),
                              scope_prefixes_=scope)
        inputs["allfiles_md5_from"] = {"path": K.relpath(resolve_allfiles(fm, args.from_allfiles)),
                                       "sha256": K.sha256_file(resolve_allfiles(fm, args.from_allfiles)),
                                       "entries": len(f_all), "scope": sc_from}
        inputs["allfiles_md5_to"] = {"path": K.relpath(resolve_allfiles(tm, args.to_allfiles)),
                                     "sha256": K.sha256_file(resolve_allfiles(tm, args.to_allfiles)),
                                     "entries": len(t_all), "scope": sc_to}
        inputs["allfiles_scope_intersection"] = scope
    except InputGap as e:
        allf_ok = False
        gaps.append({"kind": "rtl_file", "blocking": True, "detail": str(e),
                     "action": "补/修 ②路全量清单后重跑 n2_diff.py"})

    # ---- ③ 文档条目集
    doc_ok = True
    f_ent_n = t_ent_n = 0
    f_ent_path = t_ent_path = None
    f_label = t_label = None
    inputs_entries_from = inputs_entries_to = None
    try:
        f_ent_path, f_label = resolve_entries(fm, from_manifest, "from",
                                              args.from_entries, notes)
        t_ent_path, t_label = resolve_entries(tm, args.to_manifest, "to",
                                              args.to_entries, notes)
        # 两侧解析到同一文件且文档指纹不同 ⇒ 新版条目集根本没落盘（回退/兜底掩盖），fail-closed
        if os.path.abspath(f_ent_path) == os.path.abspath(t_ent_path):
            same_manifest = os.path.abspath(from_manifest) == os.path.abspath(args.to_manifest)
            same_fp = (fm.get("doc_fingerprint", {}).get("value")
                       == tm.get("doc_fingerprint", {}).get("value"))
            if not (same_manifest or same_fp):
                raise InputGap(
                    "③ 路两版条目集解析到同一文件（%s），但两版 doc_fingerprint.value 不同："
                    "旧=%s 新=%s ⇒ 新版条目集未落盘（回退/兜底掩盖），无法做条目级 diff"
                    % (K.relpath(f_ent_path), fm.get("doc_fingerprint", {}).get("value"),
                       tm.get("doc_fingerprint", {}).get("value")))
        f_ent = load_entries(f_ent_path, "旧版")
        t_ent = load_entries(t_ent_path, "新版")
        f_ent_n, t_ent_n = len(f_ent), len(t_ent)
        inputs_entries_from = {"path": K.relpath(f_ent_path), "sha256": K.sha256_file(f_ent_path),
                               "entries": len(f_ent), "resolved_by": f_label}
        inputs_entries_to = {"path": K.relpath(t_ent_path), "sha256": K.sha256_file(t_ent_path),
                             "entries": len(t_ent), "resolved_by": t_label}
        inputs["doc_entries_from"] = inputs_entries_from
        inputs["doc_entries_to"] = inputs_entries_to
        inputs["doc_fingerprint_from"] = {"path": fm["doc_fingerprint"]["path"],
                                         "sha256": fm["doc_fingerprint"]["value"],
                                         "entries": fm["doc_fingerprint"].get("entries")}
        inputs["doc_fingerprint_to"] = {"path": tm["doc_fingerprint"]["path"],
                                       "sha256": tm["doc_fingerprint"]["value"],
                                       "entries": tm["doc_fingerprint"].get("entries")}
        recs += diff_entries(f_ent, t_ent, K.relpath(f_ent_path), K.relpath(t_ent_path))
    except InputGap as e:
        doc_ok = False
        gaps.append({"kind": "offset", "blocking": True, "detail": str(e),
                     "action": "生成/修 kb/index/regmap.json 与 doc_entries.jsonl 后重跑"})

    # ---- 组装产出
    recs.sort(key=lambda r: (r["kind"], r["id"], r["change"]))
    offsets = []
    for r in recs:
        raw_map = r.pop("_offset_raw", {}) if isinstance(r.get("_offset_raw"), dict) else {}
        for v in r.get("offsets", []):
            offsets.append({"value": v, "raw": raw_map.get(v, v), "kind": r["kind"],
                            "source": r["id"] if r["kind"] != "doc_entry" else
                            str(r.get("entry_id")),
                            "entry_id": r.get("entry_id"),
                            "lines": list(r.get("lines") or [])})
    offsets.sort(key=lambda o: (o["kind"], o["source"], o["value"]))
    unresolved_offsets = [{"kind": r["kind"], "id": r["id"], "reason": r["unresolved"]}
                          for r in recs if r.get("unresolved")]
    # 去掉内部辅助键（schema additionalProperties=true，但 rtl_files.md5 复验用得上故保留）
    gen = K.now_iso()
    out = {
        "schema": "kb/run/n2_diff",
        "version": 1,
        "run_id": run_id,
        "generated_at": gen,
        "generator": "kb/tools/n2_diff.py (Host 确定性)",
        "from": {"baseline": fm.get("baseline", "N/A"),
                 "manifest_path": K.relpath(from_manifest),
                 "manifest_sha256": K.sha256_file(from_manifest)},
        "to": {"baseline": tm.get("baseline"),
               "manifest_path": K.relpath(args.to_manifest),
               "manifest_sha256": K.sha256_file(args.to_manifest)},
        # 输入身份（含 ③ 路解析方式 resolved_by / 是否用回退），供审计与 N3 引用
        "inputs": inputs,
        "routes": {
            "rtl_files": route_stat(recs, "rtl_file", f_rtl_n, t_rtl_n, {
                "md5_listing_from": K.relpath(resolve_rtl_md5(fm, args.from_rtl_md5)),
                "md5_listing_to": K.relpath(resolve_rtl_md5(tm, args.to_rtl_md5)),
                "manifest_sha256_from": fm["rtl_snapshot"].get("manifest_sha256"),
                "manifest_sha256_to": tm["rtl_snapshot"].get("manifest_sha256"),
                "tar_sha256_from": fm["rtl_snapshot"].get("sha256"),
                "tar_sha256_to": tm["rtl_snapshot"].get("sha256"),
                "ok": rtl_ok}),
            "allfiles": route_stat(recs, "allfile", f_all_n, t_all_n, {
                "md5_listing_from": K.relpath(resolve_allfiles(fm, args.from_allfiles)),
                "md5_listing_to": K.relpath(resolve_allfiles(tm, args.to_allfiles)),
                "md5_listing_sha256_from": K.sha256_file(resolve_allfiles(fm, args.from_allfiles)),
                "md5_listing_sha256_to": K.sha256_file(resolve_allfiles(tm, args.to_allfiles)),
                "scope": sc_from if sc_from is not None else [],
                "scope_from": sc_from or [],
                "scope_to": sc_to or [],
                "scope_intersection": scope or [],
                "only_in_from": sorted(set((sc_from or [])) - set((sc_to or []))),
                "only_in_to": sorted(set((sc_to or [])) - set((sc_from or []))),
                "ok": allf_ok}),
            "doc_entries": route_stat(recs, "doc_entry", f_ent_n, t_ent_n, {
                "entries_from_path": K.relpath(f_ent_path) if f_ent_path else None,
                "entries_to_path": K.relpath(t_ent_path) if t_ent_path else None,
                "entries_from_resolved_by": f_label,
                "entries_to_resolved_by": t_label,
                "entries_derivation": ("主口径 dirname(manifest.doc_fingerprint.path)/"
                                       "doc_entries.jsonl；回退链 <manifest>/bundle → "
                                       "<manifest> 同目录 → kb/index/regmap.json"),
                "used_fallback": bool((f_label or "").find(ENTRY_FALLBACK_TAG) >= 0
                                      or (t_label or "").find(ENTRY_FALLBACK_TAG) >= 0),
                "fingerprint_from": fm["doc_fingerprint"].get("value"),
                "fingerprint_to": tm["doc_fingerprint"].get("value"),
                "fingerprint_entries_from": fm["doc_fingerprint"].get("entries"),
                "fingerprint_entries_to": tm["doc_fingerprint"].get("entries"),
                "ok": doc_ok}),
        },
        "has_change": bool(recs),
        "no_change_statement": None,
        "scope_notes": [],
        "diffs": recs,
        "offsets": offsets,
        "unresolved_offsets": unresolved_offsets,
        "index_gaps": gaps,
        "checks": {"schema": SCHEMA_JSON, "self_check_ok": False,
                   "deterministic": True,
                   "time_fields": ["generated_at"],
                   "generated_at_source": now_source(args),
                   "weak_criterion": "kb_lib.sha256_obj_normalized(obj, ('generated_at',))"},
        "notes": notes,
    }
    if not out["has_change"]:
        out["no_change_statement"] = (
            "无变化：三路 diff（① 自研代码逐文件 md5 ② 全量清单 md5（scope 交集 %s）"
            "③ 文档条目集 entry_id 级）逐条比对后无任何差异；rc=0，N2 到此结束"
            "（spec §4 N2：无差异 ⇒ 直接结束并报告「无变化」）。"
            % (",".join(scope or []) or "N/A"))
    out["scope_notes"] = notes
    # task-9 N2-2（裁定 (a)）：blocking 缺口 ⇒ **不产生** n2_diff.json，缺口报告写 n2_diff.gap.json
    out["blocking_gap"] = bool(gaps)
    out["blocking_gap_reasons"] = [g["detail"] for g in gaps]
    if gaps:
        notes.append("存在 blocking 输入缺口 ⇒ 差异清单**不完整**，rc=%d（不得当空清单使用）"
                     "；本轮**不产生** n2_diff.json，缺口报告 = n2_diff.gap.json/.md" % RC_GAP)
        out["scope_notes"] = notes

    errs = K.validate(out, K.load_schema(SCHEMA_NAME))
    if errs:
        sys.stderr.write("[FAIL] 产出未过 %s：\n  - %s\n" % (SCHEMA_JSON, "\n  - ".join(errs)))
        return RC_SELFCHECK
    out["checks"]["self_check_ok"] = True
    out["checks"]["normalized_sha256"] = K.sha256_obj_normalized(
        {k: v for k, v in out.items() if k != "checks"}, ("generated_at",))
    K.ensure_dir(out_dir)

    if gaps:
        jp = os.path.join(out_dir, "n2_diff.gap.json")
        mp = os.path.join(out_dir, "n2_diff.gap.md")
        refuse_if_exists((jp, mp), args.overwrite)
        stale = os.path.join(out_dir, "n2_diff.json")
        if os.path.exists(stale):
            out["stale_n2_diff"] = {"path": K.relpath(stale),
                                    "sha256": K.sha256_file(stale),
                                    "warning": "目录里仍存在上一次的 n2_diff.json（对应不同输入），"
                                               "本轮**未**覆盖也**未**删除它；不得当本轮输入用"}
            K.write_json(jp, out)   # 带上 stale 信息后重写
        else:
            out["stale_n2_diff"] = None
            K.write_json(jp, out)
        write_md(mp, out, {}, gap=True)
        print("[kb] run_id=%s generated_at=%s（源=%s）"
              % (run_id, gen, out["checks"]["generated_at_source"]))
        print("[kb] 结论：**不完整**（blocking 输入缺口 %d 条）⇒ 未产出 n2_diff.json" % len(gaps))
        print("[kb] 缺口报告：%s sha256=%s" % (K.relpath(jp), K.sha256_file(jp)))
        print("[kb]           %s sha256=%s" % (K.relpath(mp), K.sha256_file(mp)))
        if out["stale_n2_diff"]:
            sys.stderr.write("[WARN] 目录里存在上一次的 n2_diff.json（sha256=%s）；本轮未覆盖/未删除，"
                             "**不得作为本轮 N3 输入**\n" % out["stale_n2_diff"]["sha256"])
        for g in gaps:
            print("[kb] 输入缺口（%s）：%s" % (g["kind"], g["detail"]))
        sys.stderr.write("[FAIL] 存在 blocking 输入缺口 ⇒ rc=%d；已写 n2_diff.gap.json/.md，"
                         "未写 n2_diff.json\n" % RC_GAP)
        return RC_GAP

    jp = os.path.join(out_dir, "n2_diff.json")
    mp = os.path.join(out_dir, "n2_diff.md")
    refuse_if_exists((jp, mp), args.overwrite)
    K.write_json(jp, out)
    write_md(mp, out, {})

    print("[kb] run_id=%s generated_at=%s（源=%s）"
          % (run_id, gen, out["checks"]["generated_at_source"]))
    print("[kb] kb_lib.now_iso()（注入后，即产物里的时刻）=%s" % K.now_iso())
    print("[kb] 结论：%s" % ("无变化" if not out["has_change"] else "有变化"))
    print("[kb] 差异条目：%d（rtl_file=%d allfile=%d doc_entry=%d）；抽出 offset=%d；"
          "unresolved=%d"
          % (len(recs), out["routes"]["rtl_files"]["changed"] + out["routes"]["rtl_files"]["added"]
             + out["routes"]["rtl_files"]["removed"],
             out["routes"]["allfiles"]["changed"] + out["routes"]["allfiles"]["added"]
             + out["routes"]["allfiles"]["removed"],
             out["routes"]["doc_entries"]["changed"] + out["routes"]["doc_entries"]["added"]
             + out["routes"]["doc_entries"]["removed"],
             len(offsets), len(unresolved_offsets)))
    print("[kb] 产出：%s sha256=%s" % (K.relpath(jp), K.sha256_file(jp)))
    print("[kb] 归一化指纹（弱判据，time_fields=[generated_at]）：%s"
          % out["checks"]["normalized_sha256"])
    print("[kb]       %s sha256=%s" % (K.relpath(mp), K.sha256_file(mp)))
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
