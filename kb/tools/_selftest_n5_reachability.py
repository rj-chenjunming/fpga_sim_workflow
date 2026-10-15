#!/usr/bin/env python3
"""N5 可达性自测：**宏展开**接入调用图（N5-M1 / N5-M4 修复的回归测试）。

缺陷原文（`doc/spec/evidence/loop_rehearsal/REHEARSAL_REPORT.md:136`）：
> N5 静态可达性判据**假阴性**：`tc_pcie_rw_02` 被判 `unreachable`，但 N9 实测印记真的出现
> ⇒ 根因是判据**没展开 `FORKJN_FOR_BLK` 宏**。

根因与修法：`PCIE_REG_RW` / `I2C_SLV_RW` 这类 task 在用例里是以 `` `FORKJN_FOR_BLK(<N>, <TF_NAME>, …) ``
的**第 2 实参**形式被调用的，普通 `name(` 正则看不见 ⇒ 调用图不完整。
本测试同时固定"不许放宽"的对照面：**文件内没有调用点的仍必须 unreachable**。

用法：`python3 kb/tools/_selftest_n5_reachability.py`（退出码 0 = 全过）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from n5_impact import macro_called_names, reachability_analysis  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
FIXTURE = os.path.join(ROOT, "kb", "runs", "RUN-20261015-120626", "sandbox", "TESTLIB")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


# ---- 1 宏识别单元面 ----
BODY = """
`define FORKJN_FOR_BLK(FOR_END_NUM, TF_NAME, DELAY=0)
`FORKJN_FOR_BLK(1, PCIE_REG_RW)
`FORKJN_FOR_BLK_PHASE(44, I2C_SLV_RW, PHASE_X)
`FORKJN_FOR_BLK(2,
        PCIE_REG_RW_B)
plain_task_call();
"""
got = macro_called_names(BODY)
check("1 宏第2实参识别为调用点", got == {"PCIE_REG_RW", "I2C_SLV_RW", "PCIE_REG_RW_B"}, str(sorted(got)))
check("2 `define 定义行不算调用点", "FOR_END_NUM" not in got, "")
check("3 普通调用不算宏调用", "plain_task_call" not in got, "")
check("4 FORKJN_FOR_BLK_PHASE 变体覆盖", "I2C_SLV_RW" in got, "")
check("5 跨行宏实参覆盖", "PCIE_REG_RW_B" in got, "")

# ---- 2 真实用例（归档夹具；缺失则跳过而不是假通过）----
if not os.path.isdir(FIXTURE):
    check("6 夹具存在", False, "跳过真实用例检查：%s 不存在" % FIXTURE)
else:
    a = reachability_analysis(os.path.join(FIXTURE, "tc_pcie_rw_02.sv"))
    chk = a.get("tasks", {}).get("sys_reg_test", {})
    check("6 tc_pcie_rw_02 的 sys_reg_test 变为可达（N5-M1 预期 live）",
          chk.get("reachable") is True, str(chk))
    check("7 tc_pcie_rw_02 的 PCIE_REG_RW 标记经宏可达",
          a.get("tasks", {}).get("PCIE_REG_RW", {}).get("called_via_macro") is True, "")

    b = reachability_analysis(os.path.join(FIXTURE, "tc_bmc_i2c_04_dfx.sv"))
    chk2 = b.get("tasks", {}).get("sys_reg_test", {})
    check("8 tc_bmc_i2c_04_dfx 仍为 unreachable（**不许放宽**）",
          chk2.get("reachable") is False and chk2.get("called_somewhere") is False, str(chk2))

# ---- 3 源不可读 ⇒ static-only（不猜 live）----
missing = reachability_analysis(os.path.join(ROOT, "kb", "tools", "__no_such_case__.sv"))
check("9 源不可读 ⇒ ok=False（调用方须标 static-only，不许猜 live）",
      missing.get("ok") is False and "不可读" in missing.get("reason", ""), missing.get("reason", "")[:60])

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
