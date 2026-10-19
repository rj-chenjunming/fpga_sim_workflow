#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n10_pending.py —— N10 待裁决清单落盘（**单一写者**；spec I4 / 审计 A9）

背景
    审计 A9：N10 的 FAIL 分类 2/3 只留在 execution state，`<WORKSPACE_ROOT>/conflicts/pending.json`
    从未落盘 ⇒ I4 的"待裁决清单是一等公民"不完整。审计 A9 建议由 kb 工具写，
    不许 loop 直接 append（那会成为第二套结构/校验实现）。

本工具的唯一职责
    把 N10 对账产生的「本轮引入 / 待裁决」项追加进 `pending.json` 的 **`n10_items`**：
      * `items`（D1—D20 文档待确认）**绝不改动**；`expected_total` 语义不变（仍=文档条数 20）；
      * `n10_items` 是**加法扩展**（Lead 2026-10-19 裁决，kb/schema/conflicts.schema.json 已加
        `definitions.n10Pending`）；写后**整文件**过 `conflicts` schema；
      * 幂等键 = `(run_id, bucket_id)`；重复提交返回 rc=0 且不写盘；
      * 写前备份 `pending.json.bak-<ts>`，原子写（`kb_lib.write_json` 先 .tmp 再 os.replace）。

输入
    `--items FILE|-`（`-` = stdin）：
      * 顶层数组，或 `{"items": [...]}`；
      * 每项：`bucket_id`（必填）、`case`（必填，**折进 question** —— schema 的 n10Pending
        没有 case 字段，不能私加键）、`classification` ∈ {本轮引入, 待裁决}（必填）、
        `address_range` / `count` / `basis` / `evidence_path` 按需；
        可选 `kind` / `question` / `owner`（默认 user，必须 ∈ {doc-owner,rtl-owner,user,unassigned}）。
      输出项 id = `N10-<run_id>-<sanitized bucket_id>`（符合 schema pattern）。

退出码
    0 成功（含"无新增"幂等） / 2 用法 / 3 输入或规则拒绝（不写盘） / 4 既有 pending.json 损坏

用法
    python3 kb/tools/n10_pending.py --run RUN-20261019-180000 --items /tmp/n10.json
    echo '[{"bucket_id":"b1","case":"tc_x","classification":"本轮引入","count":3}]' \\
        | python3 kb/tools/n10_pending.py --run RUN-20261019-180000 --items -
"""

import argparse
import json
import os
import sys

sys.dont_write_bytecode = True          # kb/tools 是冻结目录：不写 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

RC_OK = 0
RC_USAGE = 2
RC_REJECT = 3
RC_BROKEN = 4

SCHEMA_NAME = "conflicts"
CLASSIFICATIONS = ("本轮引入", "待裁决")
OWNERS = ("doc-owner", "rtl-owner", "user", "unassigned")
_ID_KEEP = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")


def default_pending_path():
    return K.kb_path("conflicts", "pending.json")


def resolve(path):
    return path if os.path.isabs(path) else K.data_path(path)


def sanitize_bucket(bucket_id):
    """bucket_id -> schema id 允许的字符集（不合法字符替换为 '-'，去重连字符）。"""
    out = []
    prev_dash = False
    for ch in str(bucket_id):
        if ch in _ID_KEEP:
            out.append(ch)
            prev_dash = False
        else:
            if not prev_dash:
                out.append("-")
                prev_dash = True
    s = "".join(out).strip("-")
    return s or "bucket"


def load_doc(path):
    """读 pending.json 并过 conflicts schema；返回 (doc, why)。why 非空 = rc=4。"""
    if not os.path.exists(path):
        return None, "pending.json 不存在：%s（先跑 n1_conflicts.py 建 D1—D20；" \
                     "N10 不负责凭空造文档待确认清单）" % K.relpath(path)
    try:
        doc = K.read_json(path)
    except ValueError as exc:
        return None, "pending.json 不是合法 JSON（%s）：%s" % (exc, K.relpath(path))
    try:
        K.check(doc, SCHEMA_NAME, what="conflicts/pending.json")
    except K.SchemaError as exc:
        return None, "既有 pending.json 不合法（拒绝写，先人工修）：%s" % exc
    return doc, None


def normalize_input(raw):
    """输入 -> 规范化 item 列表；返回 (items, problems)。"""
    if isinstance(raw, dict):
        rows = raw.get("items")
        if rows is None:
            return [], ["输入对象缺 items 数组"]
    elif isinstance(raw, list):
        rows = raw
    else:
        return [], ["输入顶层必须是数组或 {\"items\": [...]}"]
    items, problems = [], []
    for i, r in enumerate(rows):
        where = "items[%d]" % i
        if not isinstance(r, dict):
            problems.append("%s 不是对象" % where)
            continue
        bucket = str(r.get("bucket_id") or "").strip()
        case = str(r.get("case") or "").strip()
        cls = str(r.get("classification") or "").strip()
        if not bucket:
            problems.append("%s 缺 bucket_id" % where)
            continue
        if not case:
            problems.append("%s 缺 case（schema 无 case 键，会折进 question；必填以便追溯）" % where)
            continue
        if cls not in CLASSIFICATIONS:
            problems.append("%s classification=%r 非法（只允许 %r）" % (where, cls, CLASSIFICATIONS))
            continue
        owner = str(r.get("owner") or "user").strip()
        if owner not in OWNERS:
            problems.append("%s owner=%r 非法（只允许 %r）" % (where, owner, OWNERS))
            continue
        count = r.get("count")
        if count is not None:
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                problems.append("%s count 必须是非负整数（实际 %r）" % (where, count))
                continue
        address_range = r.get("address_range")
        question = str(r.get("question") or "").strip() or (
            "N10 对账分类=%s；case=%s；bucket=%s；range=%s；count=%s"
            % (cls, case, bucket, address_range if address_range is not None else "N/A",
               count if count is not None else "N/A"))
        item = {
            "id": "N10-%s-%s" % (str(r.get("_run_id") or ""), sanitize_bucket(bucket)),
            "run_id": str(r.get("_run_id") or ""),
            "bucket_id": bucket,
            "kind": str(r.get("kind") or "N10-分类") ,
            "question": question,
            "classification": cls,
            "status": "open",
            "owner": owner,
        }
        if address_range is not None:
            item["address_range"] = str(address_range)
        if count is not None:
            item["count"] = count
        if r.get("basis") is not None:
            item["basis"] = str(r.get("basis"))
        if r.get("evidence_path") is not None:
            item["evidence_path"] = str(r.get("evidence_path"))
        item["created_at"] = K.now_iso()
        items.append(item)
    return items, problems


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="N10 待裁决项落盘（单一写者；只 append n10_items，D1—D20 与 expected_total 不动）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功（含无新增幂等） / 2 用法 / 3 输入或规则拒绝（不写盘） / 4 既有 pending.json 损坏")
    ap.add_argument("--run", required=True, help="run_id（形状 RUN-YYYYMMDD-HHMMSS）")
    ap.add_argument("--items", required=True, help="N10 分类项 JSON 文件；'-' 表示 stdin")
    ap.add_argument("--pending", default=None,
                    help="pending.json 覆盖（默认 <WORKSPACE_ROOT>/conflicts/pending.json；演练可指向沙箱）")
    ap.add_argument("--now", default=None, help="注入 created_at/备份时间（等价 KB_NOW，README §3.1.1）")
    args = ap.parse_args(argv)
    if args.now:
        K.set_now(args.now)

    if not (args.run.startswith("RUN-") and len(args.run) == 19
            and args.run[4:12].isdigit() and args.run[13:].isdigit() and args.run[12] == "-"):
        sys.stderr.write("[FAIL] --run 形状必须是 RUN-YYYYMMDD-HHMMSS（实际 %r）\n" % args.run)
        return RC_USAGE

    path = resolve(args.pending or default_pending_path())
    doc, why = load_doc(path)
    if why:
        sys.stderr.write("[FAIL] %s\n" % why)
        return RC_BROKEN

    if args.items == "-":
        try:
            raw = json.load(sys.stdin)
        except ValueError as exc:
            sys.stderr.write("[FAIL] stdin 不是合法 JSON：%s\n" % exc)
            return RC_REJECT
    else:
        if not os.path.isfile(args.items):
            sys.stderr.write("[FAIL] --items 文件不存在：%s\n" % args.items)
            return RC_USAGE
        try:
            with open(args.items, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except ValueError as exc:
            sys.stderr.write("[FAIL] --items 不是合法 JSON（%s）：%s\n" % (exc, args.items))
            return RC_REJECT

    rows = raw.get("items") if isinstance(raw, dict) else raw
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict):
                r["_run_id"] = args.run
    items, problems = normalize_input(raw)
    if problems:
        sys.stderr.write("[FAIL] N10 项校验失败（不写盘）：\n  - %s\n" % "\n  - ".join(problems))
        return RC_REJECT

    # 逐项按 schema 的 n10Pending 定义校验（写前拒绝，绝不写半截）
    schema_doc = K.load_schema(SCHEMA_NAME)
    n10_def = schema_doc["definitions"]["n10Pending"]
    for it in items:
        errs = K.validate(it, n10_def, "$", schema_doc)
        if errs:
            sys.stderr.write("[FAIL] 生成的 N10 项不符合 n10Pending schema（%s）：%s\n"
                             % (it.get("bucket_id"), " | ".join(errs)))
            return RC_REJECT

    existing = list(doc.get("n10_items") or [])
    seen = {(str(x.get("run_id")), str(x.get("bucket_id"))) for x in existing}
    added = []
    for it in items:
        key = (it["run_id"], it["bucket_id"])
        if key in seen:
            continue
        seen.add(key)
        added.append(it)

    if not added:
        print("[kb] 无新增（%d 项全部按 (run_id,bucket_id) 已存在）⇒ 幂等，未写盘：%s"
              % (len(items), K.relpath(path)))
        return RC_OK

    doc["n10_items"] = existing + added
    try:
        K.check(doc, SCHEMA_NAME, what="conflicts/pending.json（写前）")
    except K.SchemaError as exc:
        sys.stderr.write("[FAIL] 写前整文件校验失败（不写盘）：%s\n" % exc)
        return RC_REJECT

    # 备份（只备份、不覆盖）：时间戳经 K.now_iso 单一时间入口
    stamp = K.now_iso().replace(":", "").replace("+", "_").replace(" ", "_")
    backup = "%s.bak-%s" % (path, stamp)
    K.ensure_dir(os.path.dirname(path))
    with open(path, "rb") as src, open(backup, "wb") as dst:
        dst.write(src.read())
    try:
        os.chmod(backup, 0o444)
    except OSError:
        pass

    K.write_json(path, doc)
    try:
        K.check(K.read_json(path), SCHEMA_NAME, what="conflicts/pending.json（落盘后复验）")
    except K.SchemaError as exc:
        sys.stderr.write("[FAIL] 落盘后复验失败（需人工核）：%s\n" % exc)
        return RC_BROKEN

    print("[kb] 已追加 N10 待裁决项 %d 个 → %s" % (len(added), K.relpath(path)))
    for it in added:
        print("[kb]   %s (%s / %s)" % (it["id"], it["classification"], it["owner"]))
    print("[kb] n10_items 总数=%d；D1—D20 items=%d 与 expected_total=%r 未改；备份=%s"
          % (len(doc["n10_items"]), len(doc.get("items") or []),
             doc.get("expected_total"), K.relpath(backup)))
    print("[kb] 时间字段声明：created_at（README §3.1.1，--now/KB_NOW 注入）")
    return RC_OK


if __name__ == "__main__":
    raise SystemExit(main())
