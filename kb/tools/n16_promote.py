#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n16_promote.py —— N16 晋升新基线（人触发 + Host 原子执行；spec I8 / §7.9 / §4 N16）

流程
    0 前置检查（任一不过 ⇒ rc=3，不写任何东西）
        · G1 = signed+confirmed ∧ G2 = signed+accept ∧ G3 已决策（≠pending）
        · **身份（I20/C9）**：`--trigger-by` / `--actor-kind` 必须与 `gates.json` 里
          G3 签署记录的 `actor` / `actor_kind` **逐字一致**；缺失/不一致 ⇒ rc=3。
          工具不再硬编码 human，也不自封身份 —— 调用方（loop 的 N16 chunk）从 G3 记录取。
        · **I4 无条件**：冲突清单里任何 `blocks_release=true` 且未清零（status ∈
          {confirmed,ignored,ruled,fixed} 之外，如 open）的项 ⇒ rc=3。
          不再由 G3=milestone/defer 分流绕过（审计 A18）。
        · `kb/runs/<run_id>/case_states.json` **存在**且**无「已修订待验」**（spec I2）；
          台账判定复用 `case_state.check_ledger()`（**唯一判据实现**，不抄第二套）；
          I7 边界统一 `n6_n8_cycles >= limit` ⇒ 不得晋升（审计 C5）。
        · **真实写入开关**：默认 dry-run；只有显式 `--promote` 才落盘，
          且此时 `--actor-kind` 必须是 `human`（spec I8：人触发、Host 执行）。
        · draft manifest 过 `kb_lib.check(..., "manifest")`，且 `parent` 基线已存在（链可回放）
        · **bundle 完整性复验**：七件套每一件的 sha256/指纹与 draft manifest 声明逐一对齐
          （对不上 ⇒ rc=4，绝不把半成品固化成"真相"）
    1 写 `kb/baselines/.staging-<v>/`：**七件套**全量写完后才 rename
        · 新 manifest（parent=vₙ）           · 新 RTL 快照（tar + 逐文件 md5）
        · 新文档指纹（条目集 + 指纹）         · 新用例 md5 清单
        · 冲突清单态                          · 冻结变更结果（N2/N5/闸门/用例态 + 汇总）
        · 证据包指针（evidence/index.md + 证据件）
    2 原子晋升：`os.replace(staging, <v>)`；任一步失败 ⇒ 清理 staging、**旧基线不动**
    3 归档件 `chmod 444`（目录 555），md5/sha256 记到目录之外：`kb/baselines/INDEX.json` 追加
       （`kb_lib.check(obj,"baselines_index")`；既有键绝不重写，碰撞即 rc!=0）
    4 晋升后复验所有既有基线目录的 md5 未变（归档只增不改）

时间字段（README §3.1.1）：本脚本声明 `("created_at","promoted_at","updated_at")`；
一律经 `kb_lib.now_iso()`，`--now`/`KB_NOW` 注入。

退出码
    0 晋升成功／ 2 用法 ／ 3 前置检查未过（不写盘） ／ 4 归档或完整性失败（旧基线不动）
"""

import argparse
import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402
import case_state as CS  # noqa: E402  （I2/I7 台账判定唯一实现）

RC_OK = 0
RC_USAGE = 2
RC_PRECHECK = 3
RC_ARCHIVE = 4

#: 冲突"已清零"的状态（人裁决过 = 不再阻断发布）。其余（open 等）一律阻断。
CONFLICT_CLEARED = ("confirmed", "ignored", "ruled", "fixed")
#: 可晋升的 G3 决策（LOOP_ORCHESTRATION_SPEC §10 表 ④，与 API 晋升入口同口径）。
#: `defer` = 本轮不发版 ⇒ 不得晋升；`pending` 已在上面的"未签署"分支拒绝。
G3_PROMOTABLE = ("full_now", "subset_only", "milestone_only")

SEVEN_PIECES = ("新 manifest(parent=v_n)", "新 RTL 快照", "新文档指纹", "新用例 md5 清单",                "冲突清单态", "冻结变更结果", "证据包指针")
REQUIRED_DRAFT_KEYS = ("schema", "version", "baseline", "parent", "created_at", "created_by",
                       "package_sha256", "rtl_snapshot", "allfiles_manifest", "doc_fingerprint",
                       "cases_freeze", "conflicts_snapshot", "commit", "evidence_index")
#: 台账字面量**只从 case_state 取**（不许第二套枚举，审计 C5 / README 红线 8）
PENDING_STATE = CS.PENDING_STATE
VALID_STATES = CS.STATES
# F-N16-02（task-18）：晋升目标目录允许出现的顶层条目。仅当目标目录**不含 manifest.json**
# 且顶层条目 ⊆ 本集合时，才认定为「本工具的半截残留」并允许清理；否则拒绝且一字节不动。
ALLOWED_TARGET_ENTRIES = (
    "manifest.json", "rtl_snapshot.tar", "rtl_files.md5", "allfiles.md5",
    "doc_entries.txt", "doc_entries.jsonl", "cases.md5",
    "conflicts", "evidence", "frozen_change",
)


def fail(msg, rc):
    sys.stderr.write("[FAIL] %s\n" % msg)
    return rc


def digest_tree(root, skip_names=()):
    """{相对 root 的路径: md5}（跳过 skip_names 顶层项与 .staging-*）。"""
    out = {}
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in skip_names and not d.startswith(".staging-"))
        for fn in sorted(filenames):
            ap = os.path.join(dirpath, fn)
            if os.path.islink(ap) or not os.path.isfile(ap):
                continue
            out[os.path.relpath(ap, root).replace(os.sep, "/")] = K.md5_file(ap)
    return out


def baseline_digests(root, exclude=()):
    """既有基线目录（v0/v1/…）内所有文件的 md5，键 = `<v>/<rel>`；用于"只增不改"复验。"""
    out = {}
    if not os.path.isdir(root):
        return out
    for d in sorted(os.listdir(root)):
        if not (d.startswith("v") and d[1:].isdigit()) or d in exclude:
            continue
        for k, v in digest_tree(os.path.join(root, d)).items():
            out["%s/%s" % (d, k)] = v
    return out


def resolve(path):
    return path if os.path.isabs(path) else K.data_path(path)


def force_rmtree(p):
    """删目录（含已 chmod 444/555 的归档件）——用于清理 staging 或半截残留。"""
    if not os.path.exists(p):
        return
    for dirpath, dirnames, filenames in os.walk(p, topdown=False):
        for fn in filenames:
            try:
                os.chmod(os.path.join(dirpath, fn), 0o644)
            except OSError:
                pass
        for d in dirnames:
            try:
                os.chmod(os.path.join(dirpath, d), 0o755)
            except OSError:
                pass
        try:
            os.chmod(dirpath, 0o755)
        except OSError:
            pass
    shutil.rmtree(p, ignore_errors=True)


# ---------------------------------------------------------------- 前置检查

def precheck_gates(p):
    if not os.path.exists(p):
        return None, "闸门状态不存在：%s（先 gate.py init）" % K.relpath(p)
    st = K.read_json(p)
    want = (("G1_diff_confirm", "confirmed"), ("G2_report_accept", "accept"),
            ("G3_regression_decision", None))
    problems = []
    for gid, expect in want:
        g = (st.get("gates") or {}).get(gid)
        if not isinstance(g, dict):
            problems.append("%s 缺失" % gid)
            continue
        if g.get("status") != "signed" or g.get("decision") == "pending":
            problems.append("%s 未签署（status=%s decision=%s）"
                            % (gid, g.get("status"), g.get("decision")))
            continue
        if expect and g.get("decision") != expect:
            problems.append("%s 决策不是 %s（实际 %s）" % (gid, expect, g.get("decision")))
            continue
        if gid == "G3_regression_decision" and g.get("decision") not in G3_PROMOTABLE:
            # defer / pending 是"本轮不发版"的语义 ⇒ 不得晋升（LOOP §10 表 ④ 同口径）
            problems.append("G3 决策=%r 不是可晋升决策（只允许 %r）"
                            % (g.get("decision"), list(G3_PROMOTABLE)))
    if problems:
        return st, "闸门前置检查未过：" + "；".join(problems)
    return st, None


def precheck_identity(gates, trigger_by, actor_kind):
    """I20/C9：晋升身份必须**来自 G3 签署记录**，工具不硬编码 human、不自封身份。

    返回 (why or None, g3)。调用方传的 --trigger-by/--actor-kind 是"从 G3 记录读出来的值"，
    本函数做**逐字一致性校验**：G3 记录缺失/与传入不一致 ⇒ fail closed。
    """
    g3 = (gates.get("gates") or {}).get("G3_regression_decision")
    if not isinstance(g3, dict):
        return "G3 签署记录缺失 ⇒ 无法确定晋升身份（I20）", None
    if not g3.get("actor"):
        return "G3 签署记录缺 actor ⇒ 无法确定晋升触发者（I20 fail closed）", g3
    if g3.get("actor") != trigger_by:
        return ("--trigger-by=%r 与 G3 签署记录 actor=%r 不一致（身份必须取自 G3，C9）"
                % (trigger_by, g3.get("actor"))), g3
    if g3.get("actor_kind") != actor_kind:
        return ("--actor-kind=%r 与 G3 签署记录 actor_kind=%r 不一致（身份必须取自 G3，C9）"
                % (actor_kind, g3.get("actor_kind"))), g3
    if bool(g3.get("human_signed")) != (actor_kind == "human"):
        return ("G3 human_signed=%r 与 actor_kind=%r 不自洽（I6）"
                % (g3.get("human_signed"), actor_kind)), g3
    return None, g3


def conflicts_path_for(run_dir, explicit):
    """I4 校验对象：显式 > 本轮 bundle 的冻结快照 > 工作区现态。

    优先用 **本轮 bundle 快照**：晋升的是"这一轮冻结的冲突态"，不是工作区后来被改过的现态。
    """
    cands = []
    if explicit:
        cands.append(resolve(explicit))
    cands.append(os.path.join(run_dir, "bundle", "conflicts", "conflicts.json"))
    cands.append(K.kb_path("conflicts", "conflicts.json"))
    for p in cands:
        if os.path.isfile(p):
            return p
    return None


def precheck_conflicts(path):
    """I4 **无条件**校验（审计 A18）：blocks_release 未清零 ⇒ 不得晋升。

    不再由 loop 的 G3 选项（full_now/subset_only/milestone/defer）分流：
    里程碑/延期路径同样不得把未清零冲突固化进新基线。
    """
    if path is None:
        return None, "I4：冲突清单不存在（找不到本轮快照或工作区 conflicts/conflicts.json）⇒ 按未清零处理"
    try:
        doc = K.read_json(path)
    except ValueError as exc:
        return None, "I4：冲突清单不是合法 JSON（%s）：%s" % (exc, K.relpath(path))
    items = doc.get("conflicts")
    if not isinstance(items, list):
        return None, "I4：冲突清单缺 conflicts[] 数组：%s" % K.relpath(path)
    blocking = [c for c in items
                if isinstance(c, dict) and c.get("blocks_release")
                and c.get("status") not in CONFLICT_CLEARED]
    if blocking:
        ids = ", ".join(str(c.get("id")) for c in blocking[:12])
        return doc, ("I4：冲突未清零（%d/%d 项 blocks_release 且 status 不在 %r）⇒ 不得晋升：%s"
                     % (len(blocking), len(items), CONFLICT_CLEARED, ids))
    return doc, None


def precheck_cases(run_dir, explicit):
    """I2/I7 前置检查：**复用 case_state.check_ledger**（唯一判据实现）。"""
    p = explicit or os.path.join(run_dir, "case_states.json")
    if not os.path.exists(p):
        return None, ("用例态台账不存在：%s\n      ⇒ 先 kb/tools/case_state.py init --run <id> "
                      "并由 N6~N10 责任方写入（I2：缺台账不得晋升）" % K.relpath(p))
    try:
        st = K.read_json(p)
    except ValueError as exc:
        return None, "用例态台账不是合法 JSON（%s）：%s" % (exc, K.relpath(p))
    errs = K.validate(st, K.load_schema("case_states"))
    if errs:
        return st, "用例态台账不合 case_states.schema.json：%s" % " | ".join(errs[:6])
    problems, _info = CS.check_ledger(st, for_promotion=True)
    if problems:
        return st, "台账前置检查未过（I2/I7）：" + "；".join(problems)
    return st, None


def verify_bundle(bundle, draft):
    """复验 bundle 里七件套的指纹与 draft manifest 声明一致；返回 (ok, problems, files)."""
    problems = []
    files = {}
    rtl = draft["rtl_snapshot"]
    allf = draft["allfiles_manifest"]
    doc = draft["doc_fingerprint"]
    cases = draft["cases_freeze"]
    conf = draft["conflicts_snapshot"]

    def add(rel, must_sha):
        ap = os.path.join(bundle, rel)
        if not os.path.exists(ap):
            problems.append("七件套缺件：%s" % K.relpath(ap))
            return None
        sha = K.sha256_file(ap)
        if must_sha and sha != must_sha:
            problems.append("%s sha256 不符：manifest 声明 %s 实际 %s"
                            % (K.relpath(ap), must_sha, sha))
        files[rel] = ap
        return ap

    add("rtl_snapshot.tar", rtl.get("sha256"))
    add("rtl_files.md5", rtl.get("manifest_sha256"))
    add("allfiles.md5", allf.get("sha256"))
    add("cases.md5", cases.get("sha256"))
    add("conflicts/conflicts.json", conf.get("sha256"))
    add("doc_entries.txt", None)
    add("doc_entries.jsonl", None)

    # 条目数与文档指纹复算
    p = os.path.join(bundle, "rtl_files.md5")
    if os.path.exists(p):
        n = sum(1 for _ in open(p, "r", encoding="utf-8", errors="surrogateescape"))
        if rtl.get("entries") is not None and n != rtl["entries"]:
            problems.append("rtl_files.md5 行数 %d != rtl_snapshot.entries %s" % (n, rtl["entries"]))
    p = os.path.join(bundle, "allfiles.md5")
    if os.path.exists(p):
        n = sum(1 for _ in open(p, "r", encoding="utf-8", errors="surrogateescape"))
        if allf.get("entries") is not None and n != allf["entries"]:
            problems.append("allfiles.md5 行数 %d != allfiles_manifest.entries %s" % (n, allf["entries"]))
    p = os.path.join(bundle, "cases.md5")
    if os.path.exists(p):
        n = sum(1 for _ in open(p, "r", encoding="utf-8", errors="surrogateescape"))
        if cases.get("entries") is not None and n != cases["entries"]:
            problems.append("cases.md5 行数 %d != cases_freeze.entries %s" % (n, cases["entries"]))
    p = os.path.join(bundle, "doc_entries.txt")
    if os.path.exists(p):
        lines = []
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                lines.append(line.rstrip("\n"))
        val = K.canon_lines_sha256([x for x in lines if x != ""])
        if doc.get("value") and val != doc["value"]:
            problems.append("doc_entries.txt 规范化指纹 %s != doc_fingerprint.value %s"
                            % (val, doc["value"]))
        if doc.get("entries") is not None and len([x for x in lines if x != ""]) != doc["entries"]:
            problems.append("doc_entries.txt 行数 %d != doc_fingerprint.entries %s"
                            % (len([x for x in lines if x != ""]), doc["entries"]))
    p = os.path.join(bundle, "conflicts", "conflicts.json")
    if os.path.exists(p):
        n = len((K.read_json(p) or {}).get("conflicts", []))
        if conf.get("entries") is not None and n != conf["entries"]:
            problems.append("conflicts.json 条数 %d != conflicts_snapshot.entries %s"
                            % (n, conf["entries"]))
    return (not problems), problems, files


# ---------------------------------------------------------------- 归档

def copy_file(src, dst):
    K.ensure_dir(os.path.dirname(dst))
    shutil.copyfile(src, dst)
    return dst


def build_manifest(draft, target, parent, by, actor_kind, human_signed, run_id, final_dir,
                   run_dir, n2_path, n5_path):
    m = dict(draft)
    m["baseline"] = target
    m["parent"] = parent
    m["created_at"] = K.now_iso()
    m["created_by"] = "n16_promote.py (Host) · 人触发: %s" % by
    m["trigger"] = {"by": by, "actor_kind": actor_kind, "human_signed": human_signed,
                    "run_id": run_id, "source_gate": "G2_report_accept"}
    for key, fname in (("rtl_snapshot", "rtl_snapshot.tar"),
                       ("allfiles_manifest", "allfiles.md5"),
                       ("cases_freeze", "cases.md5"),
                       ("conflicts_snapshot", "conflicts/conflicts.json")):
        art = dict(m[key])
        art["path"] = K.relpath(os.path.join(final_dir, fname))
        m[key] = art
    doc = dict(m["doc_fingerprint"])
    doc["path"] = K.relpath(os.path.join(final_dir, "doc_entries.txt"))
    m["doc_fingerprint"] = doc
    m["evidence_index"] = K.relpath(os.path.join(final_dir, "evidence", "index.md"))
    notes = list(m.get("notes") or [])
    notes.append("N16 晋升（人触发 + Host 原子执行）：parent=%s ⇒ %s；run_id=%s；"
                 "触发者=%s(actor_kind=%s, human_signed=%s)"
                 % (parent, target, run_id, by, actor_kind, human_signed))
    notes.append("七件套：%s" % " / ".join(SEVEN_PIECES))
    notes.append("冻结变更结果：%s、%s（sha256 见 frozen_change/frozen_change.json）"
                 % (K.relpath(n2_path), K.relpath(n5_path)))
    m["notes"] = notes
    m.pop("_trigger_note", None)
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N16 晋升新基线（人触发 + Host 原子归档七件套；失败不晋升且旧基线不动）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功 / 2 用法 / 3 前置检查未过（不写盘） / 4 归档或完整性失败")
    ap.add_argument("--run", required=True, help="run_id（kb/runs/<run_id>/）")
    ap.add_argument("--draft", default=None, help="N1 草案 manifest（默认 kb/runs/<run>/n1_manifest_new.json）")
    ap.add_argument("--bundle", default=None, help="七件套 bundle 目录（默认 kb/runs/<run>/bundle）")
    ap.add_argument("--baselines-root", default=None, help="基线根目录（默认 kb/baselines；演练可指向沙箱）")
    ap.add_argument("--case-states", default=None, help="用例态台账（默认 kb/runs/<run>/case_states.json）")
    ap.add_argument("--gates", default=None, help="闸门状态文件覆盖（默认 kb/runs/<run>/gates.json）")
    ap.add_argument("--n2", default=None, help="N2 差异清单覆盖（默认 kb/runs/<run>/n2_diff.json）")
    ap.add_argument("--n5", default=None, help="N5 影响清单覆盖（默认 kb/runs/<run>/n5_impact.json）")
    ap.add_argument("--evidence-dir", default=None, help="证据目录（默认 kb/runs/<run>/evidence）")
    ap.add_argument("--trigger-by", required=True,
                    help="触发晋升的人名；**必须逐字等于 gates.json 的 G3.actor**（C9/身份取自 G3）")
    ap.add_argument("--actor-kind", required=True, choices=["human", "rehearsal", "host", "model"],
                    help="**必须逐字等于 gates.json 的 G3.actor_kind**；真实晋升只允许 human")
    ap.add_argument("--allow-nonhuman", action="store_true",
                    help="兼容旧参数：仅对 dry-run 有意义（非人类只能预演，human_signed 恒 false）")
    ap.add_argument("--promote", action="store_true",
                    help="**显式真实晋升开关**：缺省 = dry-run（只做前置检查与完整性复验，不写盘）")
    ap.add_argument("--dry-run", action="store_true",
                    help="显式 dry-run（与 --promote 互斥；缺省即 dry-run）")
    ap.add_argument("--conflicts", default=None,
                    help="I4 冲突清单覆盖（默认本轮 bundle/conflicts/conflicts.json > 工作区 conflicts/conflicts.json）")
    ap.add_argument("--now", default=None,
                    help="注入时间字段 created_at/promoted_at/updated_at（等价 KB_NOW，README §3.1.1）")
    args = ap.parse_args(argv)
    if args.now:
        K.set_now(args.now)
    if args.promote and args.dry_run:
        ap.error("--promote 与 --dry-run 互斥（默认就是 dry-run）")
    do_promote = bool(args.promote)

    run_dir = K.run_dir(args.run)
    draft_path = args.draft or os.path.join(run_dir, "n1_manifest_new.json")
    bundle = args.bundle or os.path.join(run_dir, "bundle")
    root = args.baselines_root or K.kb_path("baselines")
    root = resolve(root)
    evidence_src = args.evidence_dir or os.path.join(run_dir, "evidence")
    gates_path = args.gates or os.path.join(run_dir, "gates.json")
    n2_path = args.n2 or os.path.join(run_dir, "n2_diff.json")
    n5_path = args.n5 or os.path.join(run_dir, "n5_impact.json")
    idx_path = os.path.join(root, "INDEX.json")

    print("[kb] N16 晋升：run_id=%s 触发者=%s(actor_kind=%s) 基线根=%s"
          % (args.run, args.trigger_by, args.actor_kind, K.relpath(root)))

    # ---------- 0 前置检查
    if not args.trigger_by.strip():
        return fail("--trigger-by 不能为空（谁点的必须留痕）", RC_PRECHECK)

    gates, why = precheck_gates(gates_path)
    if why:
        return fail(why, RC_PRECHECK)
    why, g3 = precheck_identity(gates, args.trigger_by, args.actor_kind)
    if why:
        return fail(why, RC_PRECHECK)
    # 真实写入：人触发是硬前置（I8）。dry-run 允许 rehearsal 预演，但不落盘。
    if do_promote and args.actor_kind != "human":
        return fail("真实晋升必须 --actor-kind human（G3 actor_kind=%r，spec I8：人触发、Host 执行）"
                    % args.actor_kind, RC_PRECHECK)

    cases, why = precheck_cases(run_dir, args.case_states)
    if why:
        return fail(why, RC_PRECHECK)

    # I4 **无条件**（审计 A18）：不再看 G3 决策是 full_now / subset_only / milestone_only / defer
    cpath = conflicts_path_for(run_dir, args.conflicts)
    _cdoc, why = precheck_conflicts(cpath)
    if why:
        return fail(why, RC_PRECHECK)

    if not os.path.exists(draft_path):
        return fail("N1 草案 manifest 不存在：%s" % K.relpath(draft_path), RC_PRECHECK)
    draft = K.read_json(draft_path)
    missing = [k for k in REQUIRED_DRAFT_KEYS if k not in draft]
    if missing:
        return fail("草案 manifest 缺字段：%s（%s）" % (missing, K.relpath(draft_path)), RC_PRECHECK)
    errs = K.validate(draft, K.load_schema("manifest"))
    if errs:
        return fail("草案 manifest 过不了 manifest.schema.json：\n  - %s\n" % "\n  - ".join(errs),
                    RC_PRECHECK)
    parent = draft.get("parent")
    if not parent or not (parent.startswith("v") and parent[1:].isdigit()):
        return fail("草案 manifest.parent=%r 非法（必须指向已存在基线 vN）" % parent, RC_PRECHECK)
    parent_dir = os.path.join(root, parent)
    if not os.path.isfile(os.path.join(parent_dir, "manifest.json")):
        return fail("parent 基线不存在：%s（parent 链必须可回放）"
                    % K.relpath(os.path.join(parent_dir, "manifest.json")), RC_PRECHECK)
    target = "v%d" % (int(parent[1:]) + 1)
    if draft.get("baseline") not in (None, target):
        print("[WARN] 草案 baseline=%s 与按 parent 推导的 %s 不一致 ⇒ 以 %s 为准（链连续）"
              % (draft.get("baseline"), target, target))
    final_dir = os.path.join(root, target)
    staging = os.path.join(root, ".staging-%s" % target)
    if os.path.isfile(os.path.join(final_dir, "manifest.json")):
        return fail("基线 %s 已存在：%s ⇒ 归档只增不改（README 红线 4）"
                    % (target, K.relpath(final_dir)), RC_PRECHECK)

    if not os.path.isdir(bundle):
        return fail("七件套 bundle 不存在：%s（先跑 n1_snapshot.py stage）" % K.relpath(bundle),
                    RC_PRECHECK)
    ok, problems, pieces = verify_bundle(bundle, draft)
    if not ok:
        return fail("bundle 完整性复验失败（不晋升）：\n  - %s" % "\n  - ".join(problems),
                    RC_ARCHIVE)
    if not os.path.isfile(n2_path):
        return fail("冻结变更结果缺 N2 差异清单：%s（先跑 n2_diff.py）" % K.relpath(n2_path),
                    RC_PRECHECK)
    if not os.path.isfile(n5_path):
        return fail("冻结变更结果缺 N5 影响清单：%s（先跑 n5_impact.py）" % K.relpath(n5_path),
                    RC_PRECHECK)

    # F-N16-01（task-18）：**必须 exclude=(target,)** —— 与事后复验 :539 的同名口径对齐。
    # 否则"目标目录预先存在"时两侧口径不对称 ⇒ 事后必然不符 ⇒ rc=4 但晋升已发生
    # （"失败 ⇒ 不晋升"契约被违反）。
    old_digest = baseline_digests(root, exclude=(target,))
    before_old = old_digest
    human_signed = (args.actor_kind == "human")
    print("[kb] 前置检查通过：G1=confirmed G2=accept G3=%s；身份=G3(%s/%s)；"
          "用例态待验=0 且返工未到上限；I4 冲突已清零；bundle 七件套指纹对齐"
          % (gates["gates"]["G3_regression_decision"]["decision"],
             g3.get("actor"), g3.get("actor_kind")))
    print("[kb] 目标基线：%s（parent=%s）；既有基线件数=%d；模式=%s"
          % (target, parent, len(before_old), "PROMOTE(真实写入)" if do_promote else "dry-run"))

    if not do_promote:
        print("[kb] dry-run（默认；未给 --promote）：不写盘。计划写入 %s，随后 os.replace → %s，"
              "再 chmod 444 并追加 %s" % (K.relpath(staging), K.relpath(final_dir), K.relpath(idx_path)))
        return RC_OK

    # ---------- 1 写 staging
    promoted = False
    try:
        if os.path.exists(staging):
            print("[kb] 清理上次失败残留 staging：%s" % K.relpath(staging))
            force_rmtree(staging)
        K.ensure_dir(staging)
        plan = []
        for rel in ("rtl_snapshot.tar", "rtl_files.md5", "allfiles.md5", "doc_entries.txt",
                    "doc_entries.jsonl", "cases.md5"):
            plan.append((os.path.join(bundle, rel), os.path.join(staging, rel)))
        plan.append((os.path.join(bundle, "conflicts", "conflicts.json"),
                     os.path.join(staging, "conflicts", "conflicts.json")))
        for fn in sorted(os.listdir(os.path.join(bundle, "conflicts"))) \
                if os.path.isdir(os.path.join(bundle, "conflicts")) else []:
            src = os.path.join(bundle, "conflicts", fn)
            if os.path.isfile(src) and fn != "conflicts.json":
                plan.append((src, os.path.join(staging, "conflicts", fn)))

        # 六、冻结变更结果
        frozen = os.path.join(staging, "frozen_change")
        for src, name in ((n2_path, "n2_diff.json"), (n5_path, "n5_impact.json"),
                          (gates_path, "gates.json"),
                          (args.case_states or os.path.join(run_dir, "case_states.json"),
                           "case_states.json")):
            if not os.path.exists(src):
                raise RuntimeError("冻结变更结果缺件：%s" % K.relpath(src))
            plan.append((src, os.path.join(frozen, name)))
        K.ensure_dir(frozen)
        frozen_summary = {
            "schema": "kb/run/frozen_change",
            "version": 1,
            "run_id": args.run,
            "promoted_at": K.now_iso(),
            "trigger_by": args.trigger_by,
            "actor_kind": args.actor_kind,
            "human_signed": human_signed,
            "target_baseline": target,
            "parent": parent,
            "files": {name: {"md5": K.md5_file(src), "sha256": K.sha256_file(src)}
                      for src, name in ((n2_path, "n2_diff.json"), (n5_path, "n5_impact.json"),
                                        (gates_path, "gates.json"),
                                        (args.case_states
                                         or os.path.join(run_dir, "case_states.json"),
                                         "case_states.json"))},
            "gate_decisions": {g: {"decision": gates["gates"][g]["decision"],
                                   "actor_kind": gates["gates"][g]["actor_kind"],
                                   "human_signed": gates["gates"][g]["human_signed"]}
                               for g in K.GATE_IDS},
            "case_states_summary": {s: sum(1 for c in cases.get("cases", [])
                                           if c.get("state") == s) for s in VALID_STATES},
        }
        K.write_json(os.path.join(frozen, "frozen_change.json"), frozen_summary)

        # 七、证据包指针
        ev_dst = os.path.join(staging, "evidence")
        K.ensure_dir(ev_dst)
        ev_copied = []
        if os.path.isdir(evidence_src):
            for dirpath, dirnames, filenames in os.walk(evidence_src):
                dirnames[:] = sorted(dirnames)
                for fn in sorted(filenames):
                    src = os.path.join(dirpath, fn)
                    rel = os.path.relpath(src, evidence_src)
                    dst = os.path.join(ev_dst, rel)
                    K.ensure_dir(os.path.dirname(dst))
                    copy_file(src, dst)
                    ev_copied.append((rel.replace(os.sep, "/"), K.md5_file(src)))
        K.write_text(os.path.join(ev_dst, "index.md"),
                     "# 证据包指针（N16 归档）\n\n"
                     "- run_id：`%s`\n- 源证据目录：`%s`\n- 晋升目标：`%s`（parent=%s）\n"
                     "- 触发者：%s（actor_kind=%s，human_signed=%s）\n"
                     "- 冻结变更结果：`frozen_change/`（N2/N5/闸门/用例态 + 汇总）\n"
                     "- 证据件（%d 个，归档只增不改，全部 chmod 444）：\n%s\n"
                     % (args.run, K.relpath(evidence_src), target, parent, args.trigger_by,
                        args.actor_kind, human_signed, len(ev_copied),
                        "\n".join("  - `%s` md5=%s" % t for t in ev_copied) or "  - （本轮无源证据件）"))

        # 一、新 manifest
        manifest = build_manifest(draft, target, parent, args.trigger_by, args.actor_kind,
                                  human_signed, args.run, final_dir, run_dir, n2_path, n5_path)
        errs = K.validate(manifest, K.load_schema("manifest"))
        if errs:
            raise RuntimeError("新 manifest 过不了 manifest.schema.json：\n  - %s"
                               % "\n  - ".join(errs))
        K.write_json(os.path.join(staging, "manifest.json"), manifest)

        # 复制其余计划件
        for src, dst in plan:
            if not os.path.exists(src):
                raise RuntimeError("复制源缺件：%s" % K.relpath(src))
            copy_file(src, dst)

        # ---------- 完整性复核（staging 内 sha256 == 源）
        for src, dst in plan:
            if K.sha256_file(src) != K.sha256_file(dst):
                raise RuntimeError("staging 复制校验失败：%s" % K.relpath(dst))
        required = ["manifest.json", "rtl_snapshot.tar", "rtl_files.md5", "allfiles.md5",
                    "doc_entries.txt", "doc_entries.jsonl", "cases.md5",
                    "conflicts/conflicts.json", "frozen_change/frozen_change.json",
                    "frozen_change/n2_diff.json", "frozen_change/n5_impact.json",
                    "frozen_change/gates.json", "frozen_change/case_states.json",
                    "evidence/index.md"]
        for rel in required:
            ap = os.path.join(staging, rel)
            if not os.path.isfile(ap) or os.path.getsize(ap) == 0:
                raise RuntimeError("七件套不完整：缺/空 %s" % rel)
        errs = K.validate(K.read_json(os.path.join(staging, "manifest.json")),
                          K.load_schema("manifest"))
        if errs:
            raise RuntimeError("staging manifest 复校验失败：%s" % errs)

        # ---------- 2 原子晋升
        # F-N16-02（task-18）：**绝不静默删除既有内容**。只有"本工具写下的半截残留"才允许清理：
        #   判据：目标目录**不含 manifest.json**（本工具只在七件套写全后才写 manifest）
        #        且顶层条目 ⊆ 允许集合（下面 ALLOWED_TARGET_ENTRIES）。
        #   不满足 ⇒ rc!=0 且**一个字节都不动**。
        if os.path.isdir(final_dir):
            if os.path.isfile(os.path.join(final_dir, "manifest.json")):
                return fail("目标目录已存在且是**完整基线**（含 manifest.json）⇒ 拒绝晋升、"
                            "一个字节都不动：%s（归档只增不改）" % K.relpath(final_dir),
                            RC_PRECHECK)
            unexpected = sorted(set(os.listdir(final_dir)) - set(ALLOWED_TARGET_ENTRIES))
            if unexpected:
                return fail("目标目录已存在且含**非本工具产物** %r ⇒ 拒绝晋升、"
                            "一个字节都不动：%s" % (unexpected, K.relpath(final_dir)),
                            RC_PRECHECK)
            force_rmtree(final_dir)       # 只清理可识别的半截残留
        os.replace(staging, final_dir)
        promoted = True
        print("[kb] 原子晋升完成（os.replace）：%s" % K.relpath(final_dir))

        # ---------- 3 只读 + md5 记到目录之外
        for dirpath, dirnames, filenames in os.walk(final_dir):
            for fn in filenames:
                os.chmod(os.path.join(dirpath, fn), 0o444)
            os.chmod(dirpath, 0o555)
        os.chmod(final_dir, 0o555)

        files_map = {}
        for dirpath, dirnames, filenames in os.walk(final_dir):
            for fn in sorted(filenames):
                ap = os.path.join(dirpath, fn)
                rel = os.path.relpath(ap, final_dir).replace(os.sep, "/")
                files_map[rel] = {"md5": K.md5_file(ap), "sha256": K.sha256_file(ap),
                                  "bytes": os.path.getsize(ap),
                                  "mode": oct(os.stat(ap).st_mode & 0o777)}
        idx = {"schema": "kb/baselines-index", "version": 1, "updated_at": K.now_iso(),
               "note": "归档件 md5/sha256 记在基线目录之外（README 红线 4 / spec §7.7）；只追加新键",
               "baselines": {}}
        if os.path.exists(idx_path):
            old = K.read_json(idx_path)
            errs = K.validate(old, K.load_schema("baselines_index"))
            if errs:
                raise RuntimeError("既有 INDEX.json 不合 baselines_index.schema.json：%s" % errs)
            idx["baselines"] = dict(old.get("baselines") or {})
            idx["note"] = old.get("note", idx["note"])
        if target in idx["baselines"]:
            raise RuntimeError("INDEX.json 已存在键 %s ⇒ 拒绝重写既有键" % target)
        old_idx_baselines = {k: dict(v) for k, v in idx["baselines"].items()}
        idx["baselines"][target] = {
            "parent": parent, "run_id": args.run,
            "promoted_at": K.now_iso(), "created_at": manifest["created_at"],
            "trigger_by": args.trigger_by, "actor_kind": args.actor_kind,
            "human_signed": human_signed,
            "manifest_sha256": K.sha256_file(os.path.join(final_dir, "manifest.json")),
            "files": files_map, "seven_piece_set": list(SEVEN_PIECES)}
        errs = K.validate(idx, K.load_schema("baselines_index"))
        if errs:
            raise RuntimeError("INDEX.json 不合 baselines_index.schema.json：%s" % errs)
        K.write_json(idx_path, idx)

        # ---------- 4 归档只增不改复验（既有基线 md5 未变、INDEX 既有键未改写）
        after = baseline_digests(root, exclude=(target,))
        if before_old != after:
            changed = sorted(k for k in set(before_old) | set(after)
                             if before_old.get(k) != after.get(k))
            raise RuntimeError("既有基线件发生改动（违反只增不改）：%s" % changed)
        kept = {k: v for k, v in idx["baselines"].items() if k != target}
        if kept != old_idx_baselines:
            raise RuntimeError("INDEX.json 既有键被改写（违反只追加）：%s"
                               % sorted(set(kept) ^ set(old_idx_baselines)))
    except BaseException as e:
        if not promoted:
            force_rmtree(staging)
            sys.stderr.write("[FAIL] 晋升失败 ⇒ 不晋升，staging 已清理，旧基线不动：\n  %s\n" % e)
        else:
            sys.stderr.write("[FAIL] 晋升已 rename 但收尾失败（需人工核 %s）：\n  %s\n"
                             % (K.relpath(final_dir), e))
        return RC_ARCHIVE

    print("[kb] 七件套：%s" % " / ".join(SEVEN_PIECES))
    print("[kb] 归档件数=%d，全部 chmod 444；md5 记入 %s" % (len(files_map), K.relpath(idx_path)))
    print("[kb] manifest：%s sha256=%s" % (K.relpath(os.path.join(final_dir, "manifest.json")),
                                           K.sha256_file(os.path.join(final_dir, "manifest.json"))))
    print("[kb] INDEX.json 基线键：%s" % ", ".join(sorted(idx["baselines"])))
    print("[kb] 既有基线 md5 复验：%d 件全部未变（只增不改）" % len(before_old))
    print("[kb] 下一轮 N2 的 --from-baseline 应为 %s" % target)
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
