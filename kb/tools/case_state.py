#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_state.py —— 用例态台账（spec I2 / I3；schema = kb/schema/case_states.schema.json）

I2：每个受影响用例态 ∈ **固定中文四态** `未改 / 已修订待验 / 已验证通过 / 已退回`；
    **存在「待验」不得称跑通**。文件 = `kb/runs/<run_id>/case_states.json`。
I3：`跑通` 的可执行化 —— `set --state 已验证通过` 必须**同时**满足：
    `compile_rc==0` ∧ `static_check=="pass"` ∧ `two_counts.script_egrep==0` ∧
    `two_counts.uvm_error==0` ∧ `two_counts.uvm_summary_present==true` ∧
    `run_md5` 非空 ∧ `observation_marks.consistent==true`（expected==observed）；
    且若同时给了 `--md5-after`，必须 `run_md5 == md5_after`（运行对象身份 join，spec §7.6）。
    任一条不满足 ⇒ **rc!=0 且不写盘**（模型/脚本不能自封「已验证通过」）。

子命令
    init  --run <run_id> [--writer NAME] [--force]
    set   --run <run_id> --case <tc> --state <四态之一> [卡点B/C/D 证据字段…] [--now ISO]
    show  --run <run_id> [--case <tc>] [--json]

卡点字段（按需）
    --compile-rc N           卡点B 的 rc（只编译）
    --static-check pass|reject|pending
    --run-md5 M              实际被全跑的对象 md5（四方同值）
    --script-egrep N         口径一：egrep -c '(\*E|\*F|\*e|ERROR:)'
    --uvm-error N            口径二：UVM Report Summary 的 UVM_ERROR 计数
    --uvm-summary-present    口径二确实有 UVM Report Summary 段
    --obs-expected N --obs-observed N   预期观测点印记三向一致
    --evidence PATH, --note TEXT, --updated-by NAME

时间字段（README §3.1.1）：本脚本声明 `("updated_at",)`（条目级 `updated_at` 同口径）；
一律经 `kb_lib.now_iso()`，`--now`/`KB_NOW` 注入。

退出码：0 成功 / 2 用法 / 3 规则不满足（拒绝且不写盘） / 4 状态文件损坏
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

RC_OK = 0
RC_REJECT = 3
RC_BROKEN = 4

SCHEMA_NAME = "case_states"
STATES = ("未改", "已修订待验", "已验证通过", "已退回")
PASS_STATE = "已验证通过"


def state_path(run_id, override=None):
    """用例态台账路径：`--state-file` 覆盖 > kb/runs/<run_id>/case_states.json。

    `--state-file` 供演练/自测把台账留在自己的写权目录内。
    """
    return override or os.path.join(K.run_dir(run_id), "case_states.json")


def empty_state(run_id, writer):
    return {"schema": "kb/run/case_states", "version": 1, "run_id": run_id,
            "updated_at": K.now_iso(), "writer": writer or "case_state.py",
            "cases": [], "rework_cycles": {"n6_n8_cycles": 0, "limit": 3}}


def load_state(path, run_id):
    if not os.path.exists(path):
        return None
    try:
        st = K.read_json(path)
    except ValueError as e:
        sys.stderr.write("[FAIL] 用例态台账不是合法 JSON（%s）：%s\n" % (e, K.relpath(path)))
        raise SystemExit(RC_BROKEN)
    if st.get("run_id") != run_id:
        sys.stderr.write("[FAIL] case_states.json 的 run_id=%r 与 --run=%r 不一致（身份错位）\n"
                         % (st.get("run_id"), run_id))
        raise SystemExit(RC_BROKEN)
    return st


def find_case(st, case):
    for c in st.get("cases", []):
        if c.get("case") == case:
            return c
    return None


def cmd_init(args):
    p = state_path(args.run, args.state_file)
    if os.path.exists(p) and not args.force:
        sys.stderr.write("[FAIL] 用例态台账已存在：%s\n"
                         "      ⇒ 台账只增不改；要清空重来请显式 --force\n" % K.relpath(p))
        return RC_REJECT
    st = empty_state(args.run, args.writer)
    errs = K.validate(st, K.load_schema(SCHEMA_NAME))
    if errs:
        sys.stderr.write("[FAIL] 初始台账不合 schema：%s\n" % " | ".join(errs))
        return RC_BROKEN
    K.write_json(p, st)
    print("[kb] 已建立用例态台账：%s（run_id=%s，四态字面量固定）"
          % (K.relpath(p), args.run))
    print("[kb] 时间字段声明：updated_at（README §3.1.1，--now/KB_NOW 注入）")
    return RC_OK


def cmd_set(args):
    p = state_path(args.run, args.state_file)
    st = load_state(p, args.run)
    if st is None:
        sys.stderr.write("[FAIL] 用例态台账不存在：%s ⇒ 先 case_state.py init --run %s\n"
                         % (K.relpath(p), args.run))
        return RC_REJECT
    if args.state not in STATES:
        sys.stderr.write("[FAIL] --state 必须是 %s（spec I2 固定字面量）\n" % "/".join(STATES))
        return RC_REJECT

    case = args.case
    entry = find_case(st, case) or {"case": case, "state": args.state}
    entry["state"] = args.state
    if args.file:
        entry["file"] = args.file
    if args.md5_before is not None:
        entry["md5_before"] = args.md5_before
    if args.md5_after is not None:
        entry["md5_after"] = args.md5_after
    if args.sandbox_path is not None:
        entry["sandbox_path"] = args.sandbox_path
    if args.compile_rc is not None:
        entry["compile_rc"] = args.compile_rc
    if args.static_check is not None:
        entry["static_check"] = args.static_check
    if args.run_md5 is not None:
        entry["run_md5"] = args.run_md5
    if args.script_egrep is not None or args.uvm_error is not None \
            or args.uvm_summary_present is not None:
        tc = entry.get("two_counts") or {}
        if args.script_egrep is not None:
            tc["script_egrep"] = args.script_egrep
        if args.uvm_error is not None:
            tc["uvm_error"] = args.uvm_error
        if args.uvm_summary_present is not None:
            tc["uvm_summary_present"] = args.uvm_summary_present
        entry["two_counts"] = tc
    if args.obs_expected is not None or args.obs_observed is not None:
        om = entry.get("observation_marks") or {}
        if args.obs_expected is not None:
            om["expected"] = args.obs_expected
        if args.obs_observed is not None:
            om["observed"] = args.obs_observed
        if om.get("expected") is not None and om.get("observed") is not None:
            om["consistent"] = om["expected"] == om["observed"]
        entry["observation_marks"] = om
    if args.evidence is not None:
        entry["evidence"] = args.evidence
    if args.note is not None:
        entry["note"] = args.note
    entry["updated_by"] = args.updated_by or "case_state.py"
    entry["updated_at"] = K.now_iso()

    if args.rework_cycles is not None:
        # task-20 / I7：与 n16_promote.precheck_cases 同口径（负值拒 / >limit 拒 / ==limit 允许）
        lim = args.rework_limit
        if lim is None:
            lim = (st.get("rework_cycles") or {}).get("limit", 3)
        if args.rework_cycles < 0:
            sys.stderr.write("[FAIL] --rework-cycles 不能为负（%s）=> 台账**未写盘**\n" % args.rework_cycles)
            return RC_REJECT
        if args.rework_cycles > lim:
            sys.stderr.write("[FAIL] --rework-cycles %s > limit %s（I7）=> 返工超上限，必须升级 N13 人工裁决（spec §8）=> 台账**未写盘**\n" % (args.rework_cycles, lim))
            return RC_REJECT
        st.setdefault("rework_cycles", {})["n6_n8_cycles"] = args.rework_cycles
        if args.rework_limit is not None:
            st["rework_cycles"]["limit"] = args.rework_limit

    # ---- I3 可执行化：'已验证通过' 的合取门槛
    if args.state == PASS_STATE:
        bad = []
        if entry.get("compile_rc") != 0:
            bad.append("卡点B compile_rc 必须 == 0（实际 %r）" % entry.get("compile_rc"))
        if entry.get("static_check") != "pass":
            bad.append("卡点C static_check 必须 == 'pass'（实际 %r）" % entry.get("static_check"))
        tc = entry.get("two_counts") or {}
        if tc.get("script_egrep") is None:
            bad.append("口径一 script_egrep 缺失")
        elif tc.get("script_egrep") != 0:
            bad.append("口径一 script_egrep 必须 == 0（实际 %r）" % tc.get("script_egrep"))
        if tc.get("uvm_error") is None:
            bad.append("口径二 uvm_error 缺失")
        elif tc.get("uvm_error") != 0:
            bad.append("口径二 uvm_error 必须 == 0（实际 %r）" % tc.get("uvm_error"))
        if tc.get("uvm_summary_present") is not True:
            bad.append("必须显式 --uvm-summary-present（口径二确有 UVM Report Summary）")
        rb = entry.get("run_md5")
        if not rb:
            bad.append("run_md5 必须非空（运行对象身份 join，spec §7.6）")
        if entry.get("md5_after") and rb and entry["md5_after"] != rb:
            bad.append("run_md5(%s) != md5_after(%s) ⇒ 审的 md5 与跑的 md5 不一致"
                       % (rb, entry["md5_after"]))
        om = entry.get("observation_marks") or {}
        if om.get("expected") is None or om.get("observed") is None:
            bad.append("必须同时给 --obs-expected 与 --obs-observed（观测点三向一致）")
        elif om.get("consistent") is not True:
            bad.append("observation_marks.consistent 必须 true（expected=%r observed=%r）"
                       % (om.get("expected"), om.get("observed")))
        if bad:
            sys.stderr.write("[FAIL] --state %s 被拒（I3 跑通门槛是合取，缺一不可）：\n  - %s\n"
                             "      台账**未写盘**，用例态保持原值。\n"
                             % (PASS_STATE, "\n  - ".join(bad)))
            return RC_REJECT

    if find_case(st, case) is None:
        st.setdefault("cases", []).append(entry)
    st["cases"].sort(key=lambda c: str(c.get("case")))
    st["updated_at"] = K.now_iso()
    st["writer"] = args.updated_by or "case_state.py"

    errs = K.validate(st, K.load_schema(SCHEMA_NAME))
    if errs:
        sys.stderr.write("[FAIL] 写盘前 schema 校验失败（不写）：\n  - %s\n" % "\n  - ".join(errs))
        return RC_BROKEN
    K.write_json(p, st)
    print("[kb] %s：%s -> %s" % (case, K.relpath(p), entry["state"]))
    print("[kb]   compile_rc=%s static_check=%s two_counts=%s"
          % (entry.get("compile_rc"), entry.get("static_check"), entry.get("two_counts")))
    print("[kb] 时间字段声明：updated_at（README §3.1.1）")
    return RC_OK


def cmd_show(args):
    p = state_path(args.run, args.state_file)
    st = load_state(p, args.run)
    if st is None:
        sys.stderr.write("[FAIL] 用例态台账不存在：%s\n" % K.relpath(p))
        return RC_REJECT
    cases = st.get("cases", [])
    if args.case:
        cases = [c for c in cases if c.get("case") == args.case]
    print("[kb] %s（run_id=%s writer=%s updated_at=%s）"
          % (K.relpath(p), st.get("run_id"), st.get("writer"), st.get("updated_at")))
    counts = {}
    for c in cases:
        counts[c.get("state")] = counts.get(c.get("state"), 0) + 1
        print("[kb]   %-34s %-8s compile_rc=%s static_check=%s run_md5=%s"
              % (c.get("case"), c.get("state"), c.get("compile_rc"),
                 c.get("static_check"), c.get("run_md5")))
    for s in STATES:
        print("[kb]   态「%s」= %d" % (s, counts.get(s, 0)))
    pend = counts.get("已修订待验", 0)
    print("[kb] 待验数=%d ⇒ %s" % (pend, "不得称跑通/不得晋升（I2）" if pend else "无待验"))
    if args.json:
        sys.stdout.write(K.canon_json(st))
    return RC_OK if pend == 0 else RC_OK   # show 不因待验失败；N16 才拒绝


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="用例态台账（I2 四态 + I3 跑通门槛可执行化；N16 晋升前置检查读本文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 成功 / 2 用法 / 3 规则不满足（不写盘） / 4 状态文件损坏")
    ap.add_argument("--now", default=None,
                    help="注入时间字段 updated_at（ISO8601；等价环境变量 KB_NOW）")
    ap.add_argument("--state-file", default=None,
                    help="台账文件路径覆盖（默认 kb/runs/<run_id>/case_states.json）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--now", dest="now_sub", default=None,
                        help="注入时间字段 updated_at（ISO8601；等价环境变量 KB_NOW）")
    common.add_argument("--state-file", dest="state_file_sub", default=None,
                        help="台账文件路径覆盖（默认 kb/runs/<run_id>/case_states.json）")

    i = sub.add_parser("init", parents=[common], help="建立空台账（已存在则拒绝，--force 才重建）")
    i.add_argument("--run", required=True)
    i.add_argument("--writer", default=None)
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)

    s = sub.add_parser("set", parents=[common],
                       help="写一个用例的态与卡点证据（--state 已验证通过 走 I3 合取门槛）")
    s.add_argument("--run", required=True)
    s.add_argument("--case", required=True)
    s.add_argument("--state", required=True, choices=list(STATES))
    s.add_argument("--file", default=None, help="用例文件（如 kb/runs/<run>/sandbox/tc_x.sv）")
    s.add_argument("--md5-before", default=None, help="冻结前的用例 md5")
    s.add_argument("--md5-after", default=None, help="修订后的用例 md5")
    s.add_argument("--sandbox-path", default=None)
    s.add_argument("--compile-rc", type=int, default=None, help="卡点B rc")
    s.add_argument("--static-check", default=None, choices=["pass", "reject", "pending"])
    s.add_argument("--run-md5", default=None, help="实际全跑的对象 md5")
    s.add_argument("--script-egrep", type=int, default=None, help="口径一计数")
    s.add_argument("--uvm-error", type=int, default=None, help="口径二 UVM_ERROR 计数")
    s.add_argument("--uvm-summary-present", action="store_true", default=None,
                   help="口径二确有 UVM Report Summary")
    s.add_argument("--obs-expected", type=int, default=None)
    s.add_argument("--obs-observed", type=int, default=None)
    s.add_argument("--evidence", default=None, help="证据路径（+ md5，可解析）")
    s.add_argument("--note", default=None)
    s.add_argument("--updated-by", default=None)
    s.add_argument("--rework-cycles", type=int, default=None, help="N6↔N8 循环次数（I7）")
    s.add_argument("--rework-limit", type=int, default=None,
                    help="I7 返工上限（默认取台账 rework_cycles.limit，缺省 3；不新增漂移常量）")
    s.set_defaults(func=cmd_set)

    sh = sub.add_parser("show", parents=[common], help="显示台账与各态计数")
    sh.add_argument("--run", required=True)
    sh.add_argument("--case", default=None)
    sh.add_argument("--json", action="store_true")
    sh.set_defaults(func=cmd_show)

    args = ap.parse_args(argv)
    now = args.now or getattr(args, "now_sub", None)
    if now:
        K.set_now(now)   # README §3.1.1：时间字段的唯一注入入口
    if getattr(args, "state_file_sub", None) and not args.state_file:
        args.state_file = args.state_file_sub
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
