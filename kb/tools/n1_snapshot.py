#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n1_snapshot.py —— N0 建基线 / N1 输入摄取（Host 确定性）

产出 **manifest**（spec §7.1，一行一版、含 parent 链）与其七件套里的可独立复算部分。

两个模式
    build  : 建档一个基线 → kb/baselines/<v>/ （**只增不改**：目录已存在 ⇒ rc!=0）
    stage  : N1 摄取一次新版输入 → kb/runs/<run_id>/bundle/ + n1_manifest_new.json
             （草案，parent=v<parent>，等待 N16 才成为正式基线）

manifest 的三锚 + 七件套对应关系（spec §7 / §7.9）
    ① rtl_snapshot         自研设计代码 tar（确定性打包）+ 逐文件 md5 清单
    ② allfiles_manifest    全量文件清单 md5（scope 显式记录，N2 只比 scope 交集）
    ③ doc_fingerprint      文档条目集规范化指纹（复用 kb/index/regmap.json 的 entry_id 条目）
    ④ cases_freeze         用例 md5 冻结清单
    ⑤ conflicts_snapshot   冲突清单快照（含 open 计数）
    ⑥ frozen_change        冻结变更结果（N4 产物；本脚本只转发指针，不产生）
    ⑦ evidence_index       证据包指针

用法
    python3 kb/tools/n1_snapshot.py build  --out-baseline v0
    python3 kb/tools/n1_snapshot.py stage  --parent v0 --run RUN-20261015-120000 \
            --rtl-src kb/runs/<id>/staged/RTL --doc-src kb/runs/<id>/staged/doc.md

设计纪律
    * 确定性：tar 内条目按路径排序、mtime=0、uid/gid=0、uname/gname="" ⇒ 同一输入两次 tar 逐字节相同。
    * 不许编造：交付包 sha256 在无交付包时写 "N/A(<原因>)"，并记进 notes。
    * 只复用 kb_lib 的口径函数；本脚本不自己实现任何指纹。
"""

import argparse
import io
import os
import shutil
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

DEFAULT_RTL_SRC = ["RTL/SRC/imports", "RTL/RTL_COMMON"]
DEFAULT_DOC = "doc/reference/TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md"
DEFAULT_CASE_DIR = "TESTLIB"
DEFAULT_ALLFILES_SCOPE = ["RTL", "TB", "TESTLIB", "PKG"]
SKIP_DIRS = {".git", "__pycache__", ".svn"}


# ---------------------------------------------------------------- 工具

def walk_files(root_abs, rel_root):
    """返回 [(abs, relpath-from-repo-root)]，跳过 VCS/缓存目录，按 relpath 排序。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root_abs):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            ap = os.path.join(dirpath, fn)
            if os.path.islink(ap) or not os.path.isfile(ap):
                continue
            rel = os.path.join(rel_root, os.path.relpath(ap, root_abs)).replace(os.sep, "/")
            out.append((ap, rel))
    out.sort(key=lambda x: x[1])
    return out


def write_md5_manifest(path, rows):
    """`md5sum` 兼容格式（'<md5>  <relpath>'），按 relpath 排序；原子写。"""
    body = "".join("%s  %s\n" % (md5, rel) for md5, rel in sorted(rows, key=lambda x: x[1]))
    return K.write_text(path, body)


def build_tar(tar_path, rows):
    """确定性 tar：排序 + mtime=0 + uid/gid=0 + uname/gname=''。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tf:
        for ap, rel in rows:
            ti = tarfile.TarInfo(name=rel)
            ti.size = os.path.getsize(ap)
            ti.mtime = 0
            ti.mode = 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            ti.type = tarfile.REGTYPE
            with open(ap, "rb") as f:
                tf.addfile(ti, f)
    data = buf.getvalue()
    tmp = tar_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, tar_path)
    os.chmod(tar_path, 0o444)
    return K.sha256_file(tar_path)


# ---------------------------------------------------------------- 七件套

def collect_rtl_snapshot(out_dir, rtl_srcs, notes):
    """① 自研设计代码 tar + 逐文件 md5 清单。

    rtl_srcs 里每个条目可以是：
      'RTL/SRC/imports'                    -> 直接就是仓库相对路径（默认模式）
      'kb/runs/<id>/staged/RTL/SRC/imports' -> 用 --map-prefix 映射回仓库相对路径
    """
    rows = []
    for spec in rtl_srcs:
        src, rel_root = spec if isinstance(spec, (list, tuple)) else (spec, spec)
        abs_src = K.root_path(src) if not os.path.isabs(src) else src
        if not os.path.isdir(abs_src):
            K.die("自研代码源目录不存在：%s" % abs_src)
        rows += walk_files(abs_src, rel_root)
    if not rows:
        K.die("自研代码快照为空（rtl_srcs=%r）" % (rtl_srcs,))
    md5s = [(K.md5_file(ap), rel) for ap, rel in rows]
    tar_path = os.path.join(out_dir, "rtl_snapshot.tar")
    sha = build_tar(tar_path, rows)
    mp = os.path.join(out_dir, "rtl_files.md5")
    write_md5_manifest(mp, md5s)
    notes.append("自研代码快照范围=%s（vendor IP 与 RTL/.git 不入快照）" % ",".join(
        s[1] if isinstance(s, (list, tuple)) else s for s in rtl_srcs))
    return {
        "path": K.relpath(tar_path),
        "sha256": sha,
        "manifest_sha256": K.sha256_file(mp),
        "entries": len(rows),
        "scope": sorted(set((s[1] if isinstance(s, (list, tuple)) else s) for s in rtl_srcs)),
    }


def collect_allfiles(out_dir, scope_dirs, notes):
    """② 全量文件清单 md5。scope 显式记录；N2 只比 scope 交集。"""
    rows = []
    for s in scope_dirs:
        if isinstance(s, (list, tuple)):
            src, rel_root = s
        else:
            src, rel_root = s, s
        abs_src = K.root_path(src) if not os.path.isabs(src) else src
        if os.path.isfile(abs_src):
            rows.append((abs_src, rel_root))
        elif os.path.isdir(abs_src):
            rows += walk_files(abs_src, rel_root)
        else:
            K.die("全量清单 scope 不存在：%s" % abs_src)
    md5s = [(K.md5_file(ap), rel) for ap, rel in rows]
    p = os.path.join(out_dir, "allfiles.md5")
    write_md5_manifest(p, md5s)
    notes.append("全量文件清单 scope=%s（该 scope 外的文件本轮不参与 ② 路 diff）"
                 % ",".join(s[1] if isinstance(s, (list, tuple)) else s for s in scope_dirs))
    return {"path": K.relpath(p), "sha256": K.sha256_file(p), "entries": len(rows),
            "scope": sorted(set(s[1] if isinstance(s, (list, tuple)) else s for s in scope_dirs))}


def collect_doc_fingerprint(out_dir, regmap_path, doc_src, notes):
    """③ 文档条目集规范化指纹（条目级，可定位到具体 offset/entry_id）。"""
    if not os.path.exists(regmap_path):
        K.die("文档条目索引不存在：%s\n"
              "      ⇒ 先跑 kb/tools/n1_doc_entries.py（文档锚是 manifest 必需件，"
              "        不允许用空指纹蒙混过关）" % regmap_path)
    rm = K.read_json(regmap_path)
    if not isinstance(rm.get("entries"), list) or not rm["entries"]:
        K.die("文档条目索引为空：%s" % regmap_path)
    lines = []
    for e in rm["entries"]:
        src = ",".join("%s:%s" % (s.get("kind"), s.get("line")) for s in e.get("sources", []))
        lines.append("%s|%s|%s|%s|%s|%s|%s|%s" % (
            e.get("entry_id"), e.get("name"), e.get("rw"), e.get("reset"),
            e.get("bytes"), "bitdef" if e.get("bitdef_present") else "summary-only", src,
            K.normalize_line(e.get("raw_line") or "")))
    lines.sort()
    fp = K.canon_lines_sha256(lines)
    lp = os.path.join(out_dir, "doc_entries.txt")
    K.write_text(lp, "".join(K.normalize_line(x) + "\n" for x in lines))
    jp = os.path.join(out_dir, "doc_entries.jsonl")
    K.write_jsonl(jp, sorted(rm["entries"], key=lambda e: e.get("entry_id", "")))
    if doc_src:
        notes.append("文档源=%s（sha256 %s）" % (doc_src if not os.path.isabs(doc_src)
                                              else K.relpath(doc_src),
                                              K.sha256_file(doc_src) if os.path.exists(doc_src) else "N/A"))
    return {
        "path": K.relpath(lp),
        "algo": "sha256-of-normalized-canonical-lines",
        "value": fp,
        "entries": len(lines),
        "source_doc": K.relpath(doc_src) if doc_src and os.path.exists(doc_src) else (doc_src or "N/A"),
    }


def collect_cases(out_dir, case_dir):
    """④ 用例 md5 冻结清单。"""
    abs_dir = K.root_path(case_dir) if not os.path.isabs(case_dir) else case_dir
    if not os.path.isdir(abs_dir):
        K.die("用例目录不存在：%s" % abs_dir)
    rows = []
    for fn in sorted(os.listdir(abs_dir)):
        if not fn.endswith(".sv"):
            continue
        ap = os.path.join(abs_dir, fn)
        if not os.path.isfile(ap):
            continue
        rel = "%s/%s" % (case_dir.replace(os.sep, "/").rstrip("/"), fn)
        rows.append((K.md5_file(ap), rel))
    if not rows:
        K.die("用例目录里没有 .sv：%s" % abs_dir)
    p = os.path.join(out_dir, "cases.md5")
    write_md5_manifest(p, rows)
    return {"path": K.relpath(p), "sha256": K.sha256_file(p), "entries": len(rows),
            "scope": [case_dir]}


def collect_conflicts(out_dir, conflicts_dir):
    """⑤ 冲突清单快照（含 open 计数）。"""
    abs_dir = K.data_path(conflicts_dir)
    src = os.path.join(abs_dir, "conflicts.json")
    if not os.path.exists(src):
        K.die("冲突清单不存在：%s（I4 说它是一等公民，不允许缺）" % src)
    obj = K.read_json(src)
    items = obj.get("conflicts", [])
    open_n = sum(1 for c in items if c.get("status") == "open")
    dst_dir = os.path.join(out_dir, "conflicts")
    K.ensure_dir(dst_dir)
    for fn in sorted(os.listdir(abs_dir)):
        if fn.endswith(".json"):
            shutil.copyfile(os.path.join(abs_dir, fn), os.path.join(dst_dir, fn))
    idx = os.path.join(dst_dir, "INDEX.md")
    K.write_text(idx,
                 "# 冲突清单快照（只增不改）\n\n"
                 "- 来源：`%s`\n- 矛盾条数：%d（open %d）\n"
                 "- 快照 md5：见同目录 `*.json` 与 `%s`\n"
                 % (K.relpath(src), len(items), open_n, K.relpath(idx)))
    p = os.path.join(dst_dir, "conflicts.json")
    return {"path": K.relpath(p), "sha256": K.sha256_file(p), "entries": len(items),
            "scope": ["冲突清单快照：%d 条，open %d" % (len(items), open_n)]}


# ---------------------------------------------------------------- manifest

def next_baseline():
    base = K.kb_path("baselines")
    n = 0
    if os.path.isdir(base):
        for d in os.listdir(base):
            if d.startswith("v") and d[1:].isdigit():
                n = max(n, int(d[1:]))
    return "v%d" % (n + 1)


def existing_baselines():
    base = K.kb_path("baselines")
    out = []
    if os.path.isdir(base):
        for d in sorted(os.listdir(base)):
            if d.startswith("v") and d[1:].isdigit() and \
                    os.path.isfile(os.path.join(base, d, "manifest.json")):
                out.append(d)
    return out


def evidence_index(out_dir, run_id, manifest_rel):
    p = os.path.join(out_dir, "evidence", "index.md")
    K.write_text(p,
                 "# 证据包指针\n\n"
                 "- baseline dir : `%s`\n"
                 "- manifest     : `%s`\n"
                 "- run_id       : `%s`\n"
                 "- 说明：归档只增不改；本目录内文件均已置只读（444）。\n"
                 % (K.relpath(out_dir), manifest_rel, run_id or "N/A"))
    return K.relpath(p)


def build_manifest(args, out_dir, rtl_srcs, doc_src, scope_dirs, case_dir,
                   conflicts_dir, baseline, parent, run_id, trigger):
    notes = []
    rtl = collect_rtl_snapshot(out_dir, rtl_srcs, notes)
    allf = collect_allfiles(out_dir, scope_dirs, notes)
    doc = collect_doc_fingerprint(out_dir, args.regmap, doc_src, notes)
    cases = collect_cases(out_dir, case_dir)
    conf = collect_conflicts(out_dir, conflicts_dir)

    pkg = args.package_sha256
    if not pkg:
        pkg = "N/A(本轮未收到交付包；按产品决策 2 只存 KB 自建的自研子集快照，完整包由交付方保留)"
        notes.append("交付包 sha256 缺失：%s" % pkg)

    cpath = K.root_path("RTL")
    ref, parseable = K.git_head(cpath)
    commit = {"repo": "RTL", "ref": ref or "N/A", "parseable": bool(parseable)}
    if not parseable:
        commit["ref"] = "%s (N/A：不可解析，不得当锚)" % (ref or "N/A")
    notes.append("commit 锚来自 RTL 嵌套仓 HEAD（parseable=%s）；未沿用已漂移的 BIN/commit_id.log" % parseable)

    mid = os.path.join(out_dir, "manifest.json")
    ev = evidence_index(out_dir, run_id, K.relpath(mid))
    m = {
        "schema": "kb/manifest",
        "version": 1,
        "baseline": baseline,
        "parent": parent,
        "created_at": K.now_iso(),
        "created_by": args.created_by,
        "trigger": trigger,
        "package_sha256": pkg,
        "rtl_snapshot": rtl,
        "allfiles_manifest": allf,
        "doc_fingerprint": doc,
        "cases_freeze": cases,
        "conflicts_snapshot": conf,
        "commit": commit,
        "evidence_index": ev,
        "notes": notes,
    }
    errs = K.validate(m, K.load_schema("manifest"))
    if errs:
        K.die("manifest 不符合 manifest.schema.json：\n  - %s" % "\n  - ".join(errs))
    K.write_json(mid, m)
    return m, mid


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="N0 建基线 / N1 输入摄取（Host 确定性，产出 manifest 三锚 + 七件套）",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--rtl-src", action="append", default=None,
                        help="自研代码源目录，可重复；可用 'SRC=DEST_REL' 形式映射仓库相对路径")
    parent.add_argument("--doc-src", default=None, help="文档路径（默认仓库内接口文档）")
    parent.add_argument("--regmap", default=None, help="regmap.json（默认 kb/index/regmap.json）")
    parent.add_argument("--case-dir", default=DEFAULT_CASE_DIR, help="用例目录（默认 TESTLIB）")
    parent.add_argument("--conflicts-dir", default=kb_lib.kb_path("conflicts"), help="冲突清单目录（默认工作区数据根下 conflicts/）")
    parent.add_argument("--allfiles-scope", action="append", default=None,
                        help="全量清单 scope，可重复；可用 'SRC=DEST_REL' 形式")
    parent.add_argument("--package-sha256", default=None, help="交付包 sha256（没有就留空，写 N/A+原因）")
    parent.add_argument("--run", default=None, help="run_id（写入 manifest.trigger.run_id 与证据指针）")
    parent.add_argument("--created-by", default="n1_snapshot.py (Host)")
    parent.add_argument("--now", default=None,
                        help="注入时刻 ISO8601（README §3.1.1 确定性口径；等价环境变量 KB_NOW）")

    sub = ap.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("build", parents=[parent], help="建档基线（只增不改）")
    b.add_argument("--out-baseline", required=True, help="如 v0")
    b.add_argument("--parent", default=None, help="一般 None；仅迁移/复刻时给")
    b.add_argument("--trigger-by", default=None)
    b.add_argument("--actor-kind", default="host",
                   choices=["human", "host", "rehearsal", "model"])

    s = sub.add_parser("stage", parents=[parent], help="N1 摄取新版输入（草案 manifest）")
    s.add_argument("--parent", required=True, help="上一版基线号，如 v0")
    s.add_argument("--trigger-by", default=None)
    s.add_argument("--actor-kind", default="host",
                   choices=["human", "host", "rehearsal", "model"])

    args = ap.parse_args()
    if args.now:
        K.set_now(args.now)
    if args.mode == "stage" and not args.run:
        ap.error("stage 模式必须给 --run <run_id>（父解析器里的 --run）")

    def parse_src(items, default):
        out = []
        for it in (items if items else default):
            if "=" in it and not os.path.exists(K.root_path(it)):
                a, b2 = it.split("=", 1)
                out.append((a, b2))
            else:
                out.append(it)
        return out

    rtl_srcs = parse_src(args.rtl_src, DEFAULT_RTL_SRC)
    scope_dirs = parse_src(args.allfiles_scope, DEFAULT_ALLFILES_SCOPE)
    doc_src = args.doc_src or K.root_path(DEFAULT_DOC)
    args.regmap = args.regmap or K.kb_path("index", "regmap.json")

    for spec in rtl_srcs:
        src = spec[0] if isinstance(spec, (list, tuple)) else spec
        if not os.path.isdir(K.root_path(src)):
            K.die("--rtl-src 不存在：%s" % src)

    if args.mode == "build":
        bl = args.out_baseline
        if not (bl.startswith("v") and bl[1:].isdigit()):
            K.die("--out-baseline 必须形如 v0/v1；得到 %r" % bl)
        out_dir = K.kb_path("baselines", bl)
        # 已完成的基线 = 含 manifest.json 的目录；只有半截目录（上次失败残留）允许先清理
        if os.path.isfile(os.path.join(out_dir, "manifest.json")):
            K.die("基线 %s 已存在且完整：%s\n"
                  "      ⇒ 归档只增不改（README §6 红线 4）。要新建请用 stage + n16_promote.py。"
                  % (bl, K.relpath(out_dir)))
        if os.path.isdir(out_dir):
            K.info("清理上次失败残留的目录：%s" % K.relpath(out_dir))
            shutil.rmtree(out_dir)
        K.ensure_dir(out_dir)
        trig = None
        if args.trigger_by:
            trig = {"by": args.trigger_by, "actor_kind": args.actor_kind,
                    "human_signed": args.actor_kind == "human",
                    "run_id": args.run or "N/A", "source_gate": "G2_report_accept"}
        try:
            m, mid = build_manifest(args, out_dir, rtl_srcs, doc_src, scope_dirs,
                                    args.case_dir, args.conflicts_dir, bl, args.parent,
                                    args.run, trig)
        except BaseException:
            K.info("建档失败 ⇒ 清理半截目录 %s（不留假基线）" % K.relpath(out_dir))
            shutil.rmtree(out_dir, ignore_errors=True)
            raise
        K.info("基线 %s 已建档：%s" % (bl, K.relpath(mid)))
    else:
        if args.parent not in existing_baselines():
            K.die("--parent %r 不是已存在的基线（现有：%r）" % (args.parent, existing_baselines()))
        rd = K.run_dir(args.run, create=True)
        out_dir = os.path.join(rd, "bundle")
        if os.path.exists(out_dir):
            K.die("staging bundle 已存在：%s" % K.relpath(out_dir))
        K.ensure_dir(out_dir)
        nxt = next_baseline()
        trig = None
        if args.trigger_by:
            trig = {"by": args.trigger_by, "actor_kind": args.actor_kind,
                    "human_signed": args.actor_kind == "human",
                    "run_id": args.run, "source_gate": "G2_report_accept"}
        m, mid = build_manifest(args, out_dir, rtl_srcs, doc_src, scope_dirs,
                                args.case_dir, args.conflicts_dir, nxt, args.parent,
                                args.run, trig)
        m["notes"] = list(m.get("notes", [])) + [
            "N1 摄取草案：baseline=%s 尚未晋升；必须经 G2=accept + G3 决策后由 n16_promote.py 原子晋升" % nxt]
        K.write_json(mid, m)
        draft = os.path.join(rd, "n1_manifest_new.json")
        K.write_json(draft, m)
        K.info("N1 摄取草案已生成：%s（parent=%s，候选版本 %s）"
               % (K.relpath(mid), args.parent, nxt))

    # 打印关键身份，便于把数字直接抄进证据（禁手算）
    print("")
    print("## manifest 指纹摘要（由命令输出复制）")
    print("manifest path : %s" % K.relpath(mid))
    print("manifest sha256: %s" % K.sha256_file(mid))
    for k in ("rtl_snapshot", "allfiles_manifest", "cases_freeze", "conflicts_snapshot"):
        print("%-18s: entries=%s sha256=%s" % (k, m[k]["entries"], m[k]["sha256"]))
    print("doc_fingerprint   : entries=%s value=%s" % (m["doc_fingerprint"]["entries"],
                                                       m["doc_fingerprint"]["value"]))
    print("commit            : %s parseable=%s" % (m["commit"]["ref"], m["commit"]["parseable"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
