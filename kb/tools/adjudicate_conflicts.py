#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate_conflicts.py —— 冲突清单的 **human-only** 裁决写入器（C10-a，2026-10-27）

背景（`doc/STATUS.md` §83.3 / C 组计划 §3）：
    `<ENV_ROOT>/kb/adjudication/C_conflicts_triage.md` 证明 `kb/schema/conflicts.schema.json`
    **已经支持**「裁决结论 + 裁决人 + 裁决主体 + 锚」的 closed 态，`I4` 只读 `blocks_release`；
    但全仓**没有任何工具**能把裁决写成 human-only，且 `n1_conflicts.py` 重跑会把 `status`/`blocks_release`
    复位（第 287/292 行硬编码 `open`/`True`）⇒ 裁决必须**外置持久化**并被抽取时合并。

本工具做两件事（一件写、一件校验）：
    1. 追加一条 human-only 裁决记录到 `<outdir>/adjudication.json`（**只增不改**，每条带
       `sha256 = sha256(canonical(record 去掉 sha256))` 可复算锚）；
    2. 把该裁决**合并**进 `<outdir>/conflicts.json`（落盘前先过 `kb_lib.check(obj,"conflicts")`），
       让 I4 立刻看到 `blocks_release` 的变化。
    `kb/tools/n1_conflicts.py` 抽取时会读同一份 `adjudication.json` 合并——重跑不丢裁决。

强制的不变式（**schema 表达不了 ⇒ 只能在这里强制**，`kb_lib.validate` 明确拒绝 `if/allOf`）：
    * 写操作必须 `--actor human:<name>`（拒绝 `model:` / `host:` / `rehearsal:` / 裸名字）；
    * `status ∈ {ruled, fixed, ignored}` ⇒ `resolution` 必填，且 `blocks_release` 强制 `false`；
    * `status = confirmed`（确认冲突真实存在）⇒ `blocks_release` 强制 `true`（不得借它清零 I4）；
    * 同一 `id` 再次裁决 = **追加**新记录（历史保留），合并时取最后一条；
    * `adjudication.json` 载入时逐条复算 `sha256`，不符即拒绝（不静默修复、不覆盖）。

用法：
    python3 kb/tools/adjudicate_conflicts.py --list
    python3 kb/tools/adjudicate_conflicts.py --actor human:chenjm --id C1 \\
        --status ruled --resolution "以位定义表 7a64_1f01 为准；汇总表 xx 为占位符，登记文档勘误"
    python3 kb/tools/adjudicate_conflicts.py --actor human:chenjm --ids C1,C2 --dry-run ...
    python3 kb/tools/adjudicate_conflicts.py --verify
    python3 kb/tools/adjudicate_conflicts.py --actor model:gpt --id C1 ...   # 必被拒

时刻：一律经 `kb_lib.now_iso()`（`--now` / `KB_NOW` 单入口），脚本内不取时钟（红线 7）。
"""

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

sys.dont_write_bytecode = True          # kb/tools 是冻结目录：不许写 __pycache__

import kb_lib  # noqa: E402

ADJ_SCHEMA = "kb/conflicts/adjudication"
ADJ_FILE = "adjudication.json"
CONFLICTS_FILE = "conflicts.json"
ID_RE = re.compile(r"^C[0-9]{1,2}$")
HUMAN_RE = re.compile(r"^human:\S")
#: 可清 `blocks_release` 的裁决状态（= 冲突已被处置）
CLEARING = ("ruled", "fixed", "ignored")


def _adj_path(outdir):
    return os.path.join(outdir, ADJ_FILE)


def _sha(record):
    """记录锚：去掉 `sha256` 后规范化 JSON 的 sha256（与 gates 锚同一做法）。"""
    body = {k: v for k, v in record.items() if k != "sha256"}
    return kb_lib.sha256_text(kb_lib.canon_json(body))


def load_adjudication(outdir):
    """读 `adjudication.json` 并逐条复算锚。不存在 ⇒ 空表（不建文件）。

    锚不符 / 形状不符 ⇒ `RuntimeError`（**不静默修复**：宁可拒绝写，也不覆盖人签过的东西）。
    """
    path = _adj_path(outdir)
    if not os.path.exists(path):
        return {"schema": ADJ_SCHEMA, "version": 1, "records": []}
    doc = kb_lib.read_json(path)
    if not isinstance(doc, dict) or doc.get("schema") != ADJ_SCHEMA:
        raise RuntimeError("%s 形状不符：schema 应为 %r" % (path, ADJ_SCHEMA))
    records = doc.get("records")
    if not isinstance(records, list):
        raise RuntimeError("%s 的 records 不是列表" % path)
    for i, rec in enumerate(records):
        if not isinstance(rec, dict) or "id" not in rec or "sha256" not in rec:
            raise RuntimeError("%s 第 %d 条形状不符（缺 id/sha256）" % (path, i))
        if _sha(rec) != rec["sha256"]:
            raise RuntimeError(
                "%s 第 %d 条（%s）锚不符：记录被外部修改或损坏（期望 %s…）"
                % (path, i, rec.get("id"), str(rec["sha256"])[:12]))
    return doc


def latest_by_id(records):
    """同 id 多条（改判）⇒ 取最后一条（追加顺序即时间顺序）。"""
    out = {}
    for rec in records:
        out[rec["id"]] = rec
    return out


def build_record(args, cid):
    """构造一条裁决记录（含锚）。不合不变式 ⇒ ValueError（写前拒绝）。"""
    status = args.status
    resolution = (args.resolution or "").strip()
    if status in CLEARING and not resolution:
        raise ValueError("status=%s ⇒ 必须给 --resolution（裁决结论不能为空）" % status)
    blocks_release = False if status in CLEARING else True
    actor = args.actor.strip()
    if status == "confirmed" and args.keep_blocks_release is False:
        # confirmed = 冲突确认存在 ⇒ 仍阻断发版；显式拒绝"用 confirmed 清零"
        pass
    rec = {
        "id": cid,
        "status": status,
        "resolution": resolution or None,
        "resolution_actor": actor,
        "resolution_kind": "human",
        "blocks_release": blocks_release,
        "adjudicated_at": kb_lib.now_iso(),
    }
    rec["sha256"] = _sha(rec)
    return rec


def apply_to_conflicts(outdir, decisions, actor):
    """把裁决合并进 `conflicts.json`（写前过 schema）。返回 (路径, 变更条数, 剩余阻断数)。"""
    path = os.path.join(outdir, CONFLICTS_FILE)
    doc = kb_lib.read_json(path)
    conflicts = doc.get("conflicts")
    if not isinstance(conflicts, list):
        raise RuntimeError("%s 的 conflicts 不是列表" % path)
    by_id = {c.get("id"): c for c in conflicts}
    unknown = sorted(set(decisions) - set(by_id))
    if unknown:
        raise ValueError("裁决引用了不存在的冲突 id：%s（本文件有 %d 条）"
                         % (unknown, len(conflicts)))
    changed = 0
    for cid, rec in sorted(decisions.items()):
        item = by_id[cid]
        before = (item.get("status"), item.get("resolution"), item.get("resolution_actor"),
                  item.get("resolution_kind"), item.get("blocks_release"))
        item["status"] = rec["status"]
        item["resolution"] = rec["resolution"]
        item["resolution_actor"] = rec["resolution_actor"]
        item["resolution_kind"] = rec["resolution_kind"]
        item["blocks_release"] = rec["blocks_release"]
        after = (item.get("status"), item.get("resolution"), item.get("resolution_actor"),
                 item.get("resolution_kind"), item.get("blocks_release"))
        if before != after:
            changed += 1
    kb_lib.check(doc, "conflicts", CONFLICTS_FILE)      # schema 兜底（改了就必须仍合法）
    kb_lib.write_json(path, doc)
    remaining = sum(1 for c in conflicts if c.get("blocks_release") is True)
    return path, changed, remaining


def cmd_list(outdir):
    doc = load_adjudication(outdir)
    latest = latest_by_id(doc["records"])
    print("[adj] file = %s（%d 条记录 / %d 个冲突）"
          % (kb_lib.relpath(_adj_path(outdir)), len(doc["records"]), len(latest)))
    for cid in sorted(latest, key=lambda x: int(x[1:])):
        rec = latest[cid]
        print("  %-4s %-9s blocks_release=%-5s %s  %s"
              % (cid, rec["status"], str(rec["blocks_release"]), rec["resolution_actor"],
                 (rec.get("resolution") or "")[:60]))
    cpath = os.path.join(outdir, CONFLICTS_FILE)
    if os.path.exists(cpath):
        conflicts = kb_lib.read_json(cpath).get("conflicts") or []
        n_open = sum(1 for c in conflicts if c.get("blocks_release") is True)
        print("[stat] conflicts=%d，仍阻断发版=%d" % (len(conflicts), n_open))
    return 0


def cmd_verify(outdir):
    doc = load_adjudication(outdir)
    latest = latest_by_id(doc["records"])
    cpath = os.path.join(outdir, CONFLICTS_FILE)
    if not os.path.exists(cpath):
        print("[FAIL] 缺 %s" % cpath)
        return 2
    conflicts = {c["id"]: c for c in (kb_lib.read_json(cpath).get("conflicts") or [])}
    bad = []
    for cid, rec in latest.items():
        item = conflicts.get(cid)
        if item is None:
            bad.append("%s 在 adjudication.json 但不在 conflicts.json" % cid)
            continue
        if item.get("resolution_kind") != "human":
            bad.append("%s conflicts.json 的 resolution_kind 不是 human" % cid)
        if item.get("status") != rec["status"]:
            bad.append("%s status 不一致：%r vs %r" % (cid, item.get("status"), rec["status"]))
        if bool(item.get("blocks_release")) != bool(rec["blocks_release"]):
            bad.append("%s blocks_release 不一致" % cid)
    n_open = sum(1 for c in conflicts.values() if c.get("blocks_release") is True)
    print("[verify] 裁决记录=%d（去重后 %d）；conflicts=%d，仍阻断=%d"
          % (len(doc["records"]), len(latest), len(conflicts), n_open))
    if bad:
        print("[FAIL] %d 项不一致：" % len(bad))
        for b in bad:
            print("  - %s" % b)
        return 1
    print("[verify] 锚与合并一致性：全部通过")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="冲突清单 human-only 裁决写入器（C10-a）")
    ap.add_argument("--outdir", default=kb_lib.kb_path("conflicts"),
                    help="conflicts/ 目录（默认数据根的 conflicts/）")
    ap.add_argument("--actor", default=None,
                    help="裁决人，必须 human:<name>（拒绝 model:/host:/rehearsal:）")
    ap.add_argument("--id", action="append", default=[], help="冲突 id（可重复）")
    ap.add_argument("--ids", default=None, help="逗号分隔的冲突 id，如 C1,C2")
    ap.add_argument("--status", default="ruled",
                    choices=["ruled", "fixed", "ignored", "confirmed"])
    ap.add_argument("--resolution", default=None, help="裁决结论（ruled/fixed/ignored 必填）")
    ap.add_argument("--keep-blocks-release", action="store_true",
                    help="仅对 confirmed 有意义；给出即显式确认仍阻断（默认即如此）")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写任何文件")
    ap.add_argument("--no-apply", action="store_true", help="只写 adjudication.json，不改 conflicts.json")
    ap.add_argument("--list", action="store_true", help="列出已有裁决与剩余阻断数")
    ap.add_argument("--verify", action="store_true", help="校验锚 + 与 conflicts.json 的一致性")
    ap.add_argument("--now", default=None,
                    help="裁决时刻（ISO8601；等价 KB_NOW）。经 kb_lib.set_now 单入口注入")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    kb_lib.set_now(args.now)

    if not os.path.isdir(args.outdir):
        sys.stderr.write("[FAIL] 目录不存在：%s\n" % args.outdir)
        return 2
    if args.list:
        try:
            return cmd_list(args.outdir)
        except RuntimeError as exc:
            sys.stderr.write("[FAIL] %s\n" % exc)
            return 3

    try:
        doc = load_adjudication(args.outdir)
    except RuntimeError as exc:
        sys.stderr.write("[FAIL] %s\n" % exc)
        return 3

    if args.verify:
        try:
            return cmd_verify(args.outdir)
        except RuntimeError as exc:
            sys.stderr.write("[FAIL] %s\n" % exc)
            return 3

    ids = list(args.id)
    if args.ids:
        ids += [x.strip() for x in args.ids.split(",") if x.strip()]
    if not ids:
        sys.stderr.write("[FAIL] 缺冲突 id：用 --id C1 或 --ids C1,C2\n")
        return 2
    bad_ids = [c for c in ids if not ID_RE.match(c)]
    if bad_ids:
        sys.stderr.write("[FAIL] 非法冲突 id：%s（应形如 C1）\n" % bad_ids)
        return 2
    actor = (args.actor or "").strip()
    if not HUMAN_RE.match(actor):
        sys.stderr.write(
            "[FAIL] --actor 必须是 human:<name>（当前 %r）。模型/宿主不得自签裁决：\n"
            "  schema 原文：status『由人裁决推进；模型只能写 open 或提出建议，不能自封 confirmed/ruled』\n"
            % actor)
        return 4

    records = []
    for cid in ids:
        try:
            records.append(build_record(args, cid))
        except ValueError as exc:
            sys.stderr.write("[FAIL] %s\n" % exc)
            return 5

    # 同一 id 追加多条（--ids C1 --id C1）= 用户错误，先拒
    if len({r["id"] for r in records}) != len(records):
        sys.stderr.write("[FAIL] 同一次调用里同一冲突 id 出现多次\n")
        return 2

    # 先校验 id 在 conflicts.json 里存在（**写前拒绝**：不留"裁决引用了不存在冲突"的脏记录）
    cpath = os.path.join(args.outdir, CONFLICTS_FILE)
    if not args.no_apply:
        if not os.path.exists(cpath):
            sys.stderr.write("[FAIL] 缺 %s（先用 --no-apply，或先跑 n1_conflicts.py）\n" % cpath)
            return 2
        known = {c.get("id") for c in (kb_lib.read_json(cpath).get("conflicts") or [])}
        unknown = sorted({r["id"] for r in records} - known)
        if unknown:
            sys.stderr.write("[FAIL] 冲突 id 不存在：%s（本文件有 %d 条）\n"
                             % (unknown, len(known)))
            return 6

    if args.dry_run:
        print("[dry-run] 将追加 %d 条裁决（不写文件）：" % len(records))
        for rec in records:
            print("  %s → status=%s blocks_release=%s actor=%s"
                  % (rec["id"], rec["status"], rec["blocks_release"], rec["resolution_actor"]))
        return 0

    doc["records"].extend(records)
    kb_lib.write_json(_adj_path(args.outdir), doc)
    if not args.quiet:
        print("[adj] 追加 %d 条裁决 → %s" % (len(records),
                                          kb_lib.relpath(_adj_path(args.outdir))))

    if not args.no_apply:
        try:
            path, changed, remaining = apply_to_conflicts(
                args.outdir, latest_by_id(records), actor)
        except (RuntimeError, ValueError) as exc:
            sys.stderr.write("[FAIL] 合并进 conflicts.json 失败：%s\n" % exc)
            return 6
        if not args.quiet:
            print("[adj] 合并进 %s：变更 %d 条；仍阻断发版 %d 条"
                  % (kb_lib.relpath(path), changed, remaining))
    return 0


if __name__ == "__main__":
    sys.exit(main())
