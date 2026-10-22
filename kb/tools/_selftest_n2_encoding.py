#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""N2 解码口径自测（SPEC-REV-01 R3：非 UTF-8 差异可读）。

**测什么**（全部可判定，不读实现内部细节也行）
1. `DECODE_ENCODINGS` 顺序 = `("utf-8", "gb18030", "gbk", "latin-1")`（GB18030 是 GBK 超集）；
2. GB18030 编码的 RTL 文本（中文注释 + `32'h04` → `32'h0000_0004`）：
   `decode_source` / `text_diff` 返回 `encoding == "gb18030"`（= 常量里的实际 codec 名），
   hunk 非空且含改动两行，行号可从 hunk 头与 `new_lines` 抽出并与原文对得上；
3. GB18030 **独有**的 4 字节序列（GBK 解不了）也能解 ⇒ 证明"先 GB18030 再 GBK"不是摆设；
4. UTF-8 文件 ⇒ `encoding == "utf-8"`；
5. 含 NUL 的真二进制 ⇒ `decode_source` 返回 `(None, None)`、`text_diff` 返回 `None`（不放宽）；
6. `rtl_file` modified 条目必须带结构化 `encoding`（`enrich_rtl_hunks` 的接线没断）；
7. 确定性：同一输入两次调用结果完全一致（`==` 与 `json(sort_keys)` 双重比较）；
7.1 口径唯一：`n2_diff.DECODE_ENCODINGS` / `n5_impact.DECODE_FALLBACK` 都引用 `kb_lib.DECODE_ENCODINGS`（同源同序）；
8. schema 允许 `encoding`：`n2_diff.schema.json` 的 `diffEntry` 是 `additionalProperties: true`，
   且带 `encoding` 的条目真能过 `kb_lib.validate`（schema 冻结，**本测试只读不改**；
   若实际不允许则本测试失败并要求停下来报告，不得擅自改 schema）。

口径唯一：本测试**只用** `n2_diff.DECODE_ENCODINGS` / `decode_source` / `text_diff`，
不另写第二套解码实现。

用法：`python3 kb/tools/_selftest_n2_encoding.py`（退出码 0 = 全过；失败打印 FAIL n/m 并非零退出）
"""
import json
import os
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True          # kb/tools 是冻结目录：不许写 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402
import n2_diff as N  # noqa: E402

SPEC_ORDER = ("utf-8", "gb18030", "gbk", "latin-1")
REL_PATH = "RTL/SRC/imports/SRC/reg/sys_reg.v"

# 中文注释 + CRLF：与工程内 5 个自有 GBK RTL 的形态一致（sys_reg.v 实测含 CRLF）
OLD_LINES = [
    "// 系统寄存器块：日期 / 版本 / 通道使能（本文件为 GB18030 编码）",
    "module sys_reg;",
    "  // 日期寄存器：只读，复位值以文档位定义表为准",
    "  localparam [31:0] FPGA_DATE_DEFAULT = 32'h04;",
    "  // 版本寄存器",
    "  localparam [31:0] FPGA_VERSION_DEFAULT = 32'h0102_0304;",
    "endmodule",
]
NEW_LINES = list(OLD_LINES)
NEW_LINES[3] = "  localparam [31:0] FPGA_DATE_DEFAULT = 32'h0000_0004;"

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name,
                          ("(%s)" % detail) if detail else ""))


def crlf(lines):
    return "\r\n".join(lines) + "\r\n"


def make_tar(path, members):
    """把 {name: bytes} 打成 tar（tmp 目录内，不碰归档）。"""
    with tarfile.open(path, "w") as tf:
        for name, data in sorted(members.items()):
            import io
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))


def main():
    tmp = tempfile.mkdtemp(prefix="selftest-n2-encoding-")
    try:
        # ---- 1 常量顺序（SPEC-REV-01 R3）----
        check("1 DECODE_ENCODINGS 顺序 = utf-8 → gb18030 → gbk → latin-1",
              tuple(N.DECODE_ENCODINGS) == SPEC_ORDER, str(N.DECODE_ENCODINGS))
        check("2 回退链末位仍是 latin-1 兜底（GBK/GB18030 都失败才兜底）",
              N.DECODE_ENCODINGS[-1] == "latin-1", "")

        # ---- 2 GB18030 夹具（中文注释 + 地址字面量改动）----
        old_bytes = crlf(OLD_LINES).encode("gb18030")
        new_bytes = crlf(NEW_LINES).encode("gb18030")
        old_path = os.path.join(tmp, "sys_reg.v.old")
        new_path = os.path.join(tmp, "sys_reg.v.new")
        with open(old_path, "wb") as f:
            f.write(old_bytes)
        with open(new_path, "wb") as f:
            f.write(new_bytes)

        old_side = open(old_path, "rb").read()
        new_side = open(new_path, "rb").read()
        # 前提：夹具确实是 GB18030 且不是 UTF-8（否则下面测的就不是回退路径）
        utf8_fails = False
        try:
            old_side.decode("utf-8")
        except UnicodeDecodeError:
            utf8_fails = True
        check("3 夹具确为非 UTF-8（GB18030 编码，UTF-8 解码必失败）", utf8_fails, "")

        o_text, o_enc = N.decode_source(old_side)
        n_text, n_enc = N.decode_source(new_side)
        check("4 GB18030 夹具 decode_source 返回 gb18030",
              o_enc == "gb18030" and n_enc == "gb18030", "old=%r new=%r" % (o_enc, n_enc))
        check("5 解码结果与常量同名（encoding 词表唯一）",
              o_enc in N.DECODE_ENCODINGS and n_enc in N.DECODE_ENCODINGS, "")
        check("6 解码后中文注释可读（未退化成 latin-1 乱码）",
              "系统寄存器块" in (o_text or "") and "日期寄存器" in (o_text or ""), "")

        td = N.text_diff(old_side, new_side)
        check("7 text_diff 返回 dict（GB18030 不再被判二进制）", isinstance(td, dict),
              str(type(td).__name__))
        td = td or {}
        check("8 条目带结构化 encoding=gb18030", td.get("encoding") == "gb18030",
              repr(td.get("encoding")))
        check("9 hunk 非空", bool(td.get("hunk")), "len=%d" % len(td.get("hunk") or ""))
        check("10 hunk 含删除行 32'h04",
              "32'h04" in td.get("hunk", "") and
              any("32'h04" in s for s in td.get("removed_lines") or []),
              str(td.get("removed_lines")))
        check("11 hunk 含新增行 32'h0000_0004",
              "32'h0000_0004" in td.get("hunk", "") and
              any("32'h0000_0004" in s for s in td.get("added_lines") or []),
              str(td.get("added_lines")))

        # ---- 3 行号可抽：hunk 头 + new_lines，且能对回原文行 ----
        # 注意 `lineterm=""` 时 unified_diff 的 `---`/`+++` 头不带换行，头行要按 `@@` 找
        hunk_hdrs = [s for s in (td.get("hunk") or "").splitlines() if s.startswith("@@")]
        m = N.HUNK_HDR.match(hunk_hdrs[0]) if hunk_hdrs else None
        start = int(m.group(1)) if m else None
        check("12 行号可从 hunk 头 `@@ -a,b +c,d @@` 抽出（新文件侧起点）",
              start is not None and start >= 1,
              "%r -> %r" % (hunk_hdrs[0] if hunk_hdrs else "", start))
        new_lines = td.get("new_lines") or []
        expect_ln = NEW_LINES.index(NEW_LINES[3]) + 1          # 1-based：改动行在新文件的行号
        check("13 new_lines 含改动行行号且与原文对齐",
              expect_ln in new_lines and
              NEW_LINES[expect_ln - 1] == NEW_LINES[3], "expect=%d got=%s" % (expect_ln, new_lines))
        if start is not None and new_lines:
            # hunk 新文件侧覆盖行数 = ` ` 上下文行 + `+` 新增行（跳过 `---`/`+++`/`@@` 头）
            body, seen_hdr = [], False
            for s in (td.get("hunk") or "").splitlines():
                if not seen_hdr:
                    seen_hdr = s.startswith("@@")
                    continue
                body.append(s)
            new_span = sum(1 for s in body if s.startswith("+") or s.startswith(" "))
            check("14 hunk 起点 ≤ 改动行号 ≤ 起点 + 覆盖行数（hunk 确实覆盖改动行）",
                  start <= expect_ln <= start + max(new_span - 1, 0),
                  "start=%d expect=%d span=%d" % (start, expect_ln, new_span))
        else:
            check("14 hunk 起点 ≤ 改动行号 ≤ 起点 + 覆盖行数（hunk 确实覆盖改动行）",
                  False, "行号抽取失败")
        offs = N.extract_offsets((td.get("added_lines") or []) + (td.get("removed_lines") or []))
        check("15 hunk 的地址字面量可抽成 offset（32'h04 → 0x4）",
              ["0x%x" % v for v, _ in offs] == ["0x4"],
              str(["0x%x" % v for v, _ in offs]))

        # ---- 4 GB18030 独有 4 字节区（GBK 解不了）→ 证明顺序有意义 ----
        four_byte = "\U00020000".encode("gb18030")      # U+20000 在 GB18030 是 4 字节
        gbk_ok = True
        try:
            four_byte.decode("gbk")
        except UnicodeDecodeError:
            gbk_ok = False
        t4, e4 = N.decode_source(four_byte)
        check("16 GB18030 独有 4 字节序列：GBK 解不了但 decode_source 返回 gb18030",
              (not gbk_ok) and e4 == "gb18030" and t4 == "\U00020000",
              "gbk_ok=%s enc=%r" % (gbk_ok, e4))

        # ---- 5 UTF-8 ----
        u_text = crlf(OLD_LINES).encode("utf-8")
        u_text2 = crlf(NEW_LINES).encode("utf-8")
        tu = N.text_diff(u_text, u_text2) or {}
        check("17 UTF-8 文件 encoding = utf-8", tu.get("encoding") == "utf-8",
              repr(tu.get("encoding")))
        check("18 UTF-8 hunk 与 GB18030 hunk 逐字符相同（同一改动、不同编码）",
              tu.get("hunk") == td.get("hunk"), "")

        # ---- 6 含 NUL 的真二进制（不放宽）----
        bin_old = b"\x00\x01\x02SYN\x00" + old_bytes
        bin_new = b"\x00\x01\x02SYN\x00" + new_bytes
        dt, de = N.decode_source(bin_old)
        check("19 含 NUL ⇒ decode_source 返回 (None, None)", dt is None and de is None,
              "text=%r enc=%r" % (dt, de))
        tb = N.text_diff(bin_old, bin_new)
        check("20 含 NUL ⇒ text_diff 返回 None（不因放宽解码而误判文本）", tb is None, repr(tb))
        check("21 单侧二进制也返回 None（不拿半侧结果硬 diff）",
              N.text_diff(bin_old, new_side) is None, "")

        # ---- 7 rtl_file modified 条目带结构化 encoding（enrich_rtl_hunks 接线）----
        old_tar = os.path.join(tmp, "rtl_old.tar")
        new_tar = os.path.join(tmp, "rtl_new.tar")
        make_tar(old_tar, {REL_PATH: old_bytes})
        make_tar(new_tar, {REL_PATH: new_bytes})
        rec = {"kind": "rtl_file", "id": REL_PATH, "change": "modified",
               "before": "a" * 32, "after": "b" * 32, "evidence": "md5 变化",
               "lines": [], "offsets": [], "unresolved": None, "diff_hunk": None}
        notes = []
        recs = N.enrich_rtl_hunks([rec], old_tar, new_tar, notes)
        got = recs[0]
        check("22 rtl_file modified 条目带 encoding=gb18030", got.get("encoding") == "gb18030",
              repr(got.get("encoding")))
        check("23 rtl_file modified 条目 diff_hunk 非空且含改动",
              bool(got.get("diff_hunk")) and "32'h0000_0004" in got["diff_hunk"], "")
        check("24 rtl_file modified 条目抽出 offset=0x4", got.get("offsets") == ["0x4"],
              str(got.get("offsets")))
        check("25 rtl_file modified 条目 lines 非空（N3 行号来源）", bool(got.get("lines")),
              str(got.get("lines")))
        check("26 非 UTF-8 解码写进 notes（可审计，不静默）",
              any("gb18030" in s for s in notes), str(notes))

        # 二进制成员：md5 变化但 hunk 无 ⇒ unresolved 必填（不得当"无变化"）
        bin_tar_old = os.path.join(tmp, "rtl_bin_old.tar")
        bin_tar_new = os.path.join(tmp, "rtl_bin_new.tar")
        bpath = "RTL/SRC/imports/SRC/reg/blob.bin"
        make_tar(bin_tar_old, {bpath: b"\x00OLD\x00"})
        make_tar(bin_tar_new, {bpath: b"\x00NEW\x00"})
        brec = {"kind": "rtl_file", "id": bpath, "change": "modified",
                "before": "c" * 32, "after": "d" * 32, "evidence": "md5 变化",
                "lines": [], "offsets": [], "unresolved": None, "diff_hunk": None}
        N.enrich_rtl_hunks([brec], bin_tar_old, bin_tar_new, [])
        check("27 真二进制：无 hunk 且必须给 unresolved（不静默当无差异）",
              brec.get("diff_hunk") is None and bool(brec.get("unresolved"))
              and "encoding" not in brec, repr(brec.get("unresolved"))[:90])

        # ---- 8 确定性：同一输入两次完全一致 ----
        a = N.text_diff(old_side, new_side)
        b = N.text_diff(old_side, new_side)
        check("28 同一输入两次 text_diff 结果相等（==）", a == b, "")
        check("29 同一输入两次 text_diff 序列化逐字节相同（sort_keys）",
              json.dumps(a, sort_keys=True, ensure_ascii=False)
              == json.dumps(b, sort_keys=True, ensure_ascii=False), "")
        check("30 同一输入两次 decode_source 结果相等",
              N.decode_source(old_side) == N.decode_source(old_side), "")
        ra = N.enrich_rtl_hunks([dict(rec, lines=[], offsets=[], diff_hunk=None,
                                      evidence="md5 变化", unresolved=None)],
                                old_tar, new_tar, [])
        rb = N.enrich_rtl_hunks([dict(rec, lines=[], offsets=[], diff_hunk=None,
                                      evidence="md5 变化", unresolved=None)],
                                old_tar, new_tar, [])
        check("31 同一输入两次 enrich_rtl_hunks 结果序列化相同",
              json.dumps(ra, sort_keys=True, ensure_ascii=False, default=str)
              == json.dumps(rb, sort_keys=True, ensure_ascii=False, default=str), "")

        # ---- 9 schema 允许 encoding（只读；不允许就失败并要求报告）----
        schema = K.load_schema("n2_diff")
        entry = ((schema.get("definitions") or {}).get("diffEntry") or {})
        ap = entry.get("additionalProperties", True)
        allows_extra = (ap is True) or (isinstance(ap, dict) and "encoding" in
                                        (ap.get("properties") or {}))
        check("32 n2_diff.schema.json 的 diffEntry 允许额外键（additionalProperties=true）",
              allows_extra, "additionalProperties=%r" % (ap,))
        enc_prop = (entry.get("properties") or {}).get("encoding")
        check("33 若 schema 显式声明 encoding，必须是字符串类型（不得是封闭枚举）",
              enc_prop is None or (isinstance(enc_prop, dict)
                                   and "string" in (enc_prop.get("type") or [])),
              repr(enc_prop))
        obj = {
            "schema": "kb/run/n2_diff", "version": 1,
            "run_id": "RUN-20261022-000000", "generated_at": "2026-10-22T00:00:00+08:00",
            "from": {"baseline": "v0", "manifest_sha256": "0" * 64},
            "to": {"manifest_sha256": "1" * 64},
            "routes": {k: {"entries_from": 1, "entries_to": 1, "changed": 1,
                           "added": 0, "removed": 0}
                       for k in ("rtl_files", "allfiles", "doc_entries")},
            "has_change": True,
            "diffs": [{"kind": "rtl_file", "id": REL_PATH, "change": "modified",
                       "evidence": "%s:L4（逐文件 md5 变化）" % REL_PATH,
                       "encoding": "gb18030", "diff_hunk": td.get("hunk"),
                       "lines": new_lines, "offsets": ["0x4"],
                       "before": "a" * 32, "after": "b" * 32, "unresolved": None}],
        }
        errs = K.validate(obj, schema)
        check("34 带 encoding 的 diffEntry 真能过 freeze 的 n2_diff schema",
              errs == [], "; ".join(str(e) for e in errs)[:160])

        # ---- 口径唯一（SPEC-REV-01 R3）：N2 / N5 / kb_lib 必须同源，不允许第二套候选集
        import n5_impact as N5
        check("35 n2 的候选集直接引用 kb_lib（不是本地再定义一份）",
              N.DECODE_ENCODINGS is K.DECODE_ENCODINGS,
              "n2=%r kb_lib=%r" % (N.DECODE_ENCODINGS, K.DECODE_ENCODINGS))
        check("36 n5 的候选集与 n2/kb_lib 同源且顺序一致",
              N5.DECODE_FALLBACK is K.DECODE_ENCODINGS
              and tuple(N5.DECODE_FALLBACK) == SPEC_ORDER == tuple(K.DECODE_ENCODINGS),
              "n5=%r" % (N5.DECODE_FALLBACK,))
        check("37 n5 源码读取不再本地写死 gbk/latin-1（gb18030 在链上）",
              "gb18030" in N5.DECODE_FALLBACK, repr(N5.DECODE_FALLBACK))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    fails = [n for n, ok, _ in RESULTS if not ok]
    passed = len(RESULTS) - len(fails)
    if fails:
        print("\nFAIL %d/%d：%s" % (len(fails), len(RESULTS), "; ".join(fails)))
        return 1
    print("\nPASS %d/%d" % (passed, len(RESULTS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
