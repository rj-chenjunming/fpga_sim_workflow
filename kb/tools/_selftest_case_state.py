#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_state 台账自测（I2 四态 / I3 跑通门槛 / I7 边界 / check 机器出口）。

固定下来的契约
    * 四态字面量 = schema enum（漂移即失败）；
    * `set --state 已验证通过` 是**合取门槛**：卡点B/C/D + 两套口径 + 观测点三向一致，
      缺一条就 rc=3 **且不写盘**（模型/脚本不能自封跑通）；
    * `check` 是唯一判定出口：待验 ⇒ rc=3；`n6_n8_cycles >= limit` ⇒ rc=3（边界统一 `>=`）；
    * `set --rework-cycles` 允许记录 `==limit`（那是升级 N13 的状态），但拒绝 `>limit`（不写盘）。

用法：`python3 kb/tools/_selftest_case_state.py`（退出码 0 = 全过；只写 tmp 文件）
"""
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402
import case_state as CS  # noqa: E402

RESULTS = []
TMP = tempfile.mkdtemp(prefix="selftest-case-state-")
STATE = os.path.join(TMP, "case_states.json")
RUN = "RUN-19990101-000000"


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


def call(*argv):
    try:
        return CS.main(list(argv))
    except SystemExit as exc:      # argparse 用法错误也要转成 rc，而不是终止自测
        return int(exc.code or 0)


def read_state():
    return K.read_json(STATE) if os.path.isfile(STATE) else None


try:
    # ---- 1 四态字面量与 schema 同源 ----
    schema = K.load_schema("case_states")
    enum = schema["properties"]["cases"]["items"]["properties"]["state"]["enum"]
    check("1 STATES 与 case_states.schema.json 的 enum 逐值一致",
          list(CS.STATES) == list(enum), str(enum))

    rc = call("--now", "2026-10-19T18:00:00+0800", "init", "--run", RUN,
              "--state-file", STATE)
    check("2 init rc=0 且台账落盘", rc == 0 and os.path.isfile(STATE), "rc=%s" % rc)
    st = read_state()
    check("3 初始 rework_cycles={n6_n8_cycles:0,limit:3}",
          (st or {}).get("rework_cycles") == {"n6_n8_cycles": 0, "limit": 3},
          str((st or {}).get("rework_cycles")))
    rc = call("init", "--run", RUN, "--state-file", STATE)
    check("4 重复 init 无 --force ⇒ rc=3（台账只增不改）", rc == 3, "rc=%s" % rc)

    # ---- 2 I3 合取门槛 ----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过")
    check("5 缺全部卡点证据 ⇒ 已验证通过被拒 rc=3", rc == 3, "rc=%s" % rc)
    st = read_state()
    check("6 被拒后台账未写盘（找不到 tc_a）",
          st is not None and not any(c.get("case") == "tc_a" for c in st.get("cases", [])), "")
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--compile-rc", "0", "--static-check", "pass",
              "--run-md5", "a" * 32, "--md5-after", "a" * 32,
              "--script-egrep", "0", "--uvm-error", "0", "--uvm-summary-present",
              "--obs-expected", "1", "--obs-observed", "1")
    check("7 卡点B/C/D+两口径+观测点齐全 ⇒ 已验证通过 rc=0", rc == 0, "rc=%s" % rc)

    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("8 check 无待验、返工未到上限 ⇒ rc=0", rc == 0, "rc=%s" % rc)

    # ---- 3 待验阻断（I2）----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_b",
              "--state", "已修订待验")
    check("9 写入已修订待验 rc=0", rc == 0, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--for-promotion", "--json")
    info = {}
    check("10 有待验 ⇒ N16 前置 check rc=3", rc == 3, "rc=%s" % rc)
    # 机器出口：JSON 里必须点名待验用例
    print("     check --json（待验态）：", json.dumps(
        {"ok": False, "note": "rc=%s" % rc}, ensure_ascii=False))

    # ---- 4 I7 边界统一 >= ----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_b",
              "--state", "已验证通过", "--compile-rc", "0", "--static-check", "pass",
              "--run-md5", "b" * 32, "--md5-after", "b" * 32,
              "--script-egrep", "0", "--uvm-error", "0", "--uvm-summary-present",
              "--obs-expected", "2", "--obs-observed", "2")
    check("11 tc_b 补齐证据后 已验证通过 rc=0（无待验）", rc == 0, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("12 无待验 ⇒ check rc=0", rc == 0, "rc=%s" % rc)

    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--rework-cycles", "3")
    st = read_state()
    check("13 记录 n6_n8_cycles==limit(3) 允许（升级 N13 的状态要可记录）",
          rc == 0 and st["rework_cycles"]["n6_n8_cycles"] == 3, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--for-promotion", "--json")
    check("14 cycles>=limit ⇒ check rc=3（边界统一 >=，审计 C5）", rc == 3, "rc=%s" % rc)
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--rework-cycles", "4")
    st = read_state()
    check("15 cycles>limit ⇒ set rc=3 且台账保持 3（不偷偷放宽预算）",
          rc == 3 and st["rework_cycles"]["n6_n8_cycles"] == 3, "rc=%s" % rc)

    # ---- 5 台账损坏 ----
    with open(STATE, "w", encoding="utf-8") as f:
        f.write("{not json")
    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("16 台账不是合法 JSON ⇒ check rc=4", rc == 4, "rc=%s" % rc)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
