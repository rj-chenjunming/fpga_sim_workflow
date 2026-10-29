# RUN-20261024-002609 变更影响评估报告草稿（N12）

- 模型模式：`live`；provider：`origin-deepseek-v4-1-flash`
- claimed_verdict：`not_passed`

## 本轮改了什么

本轮 run_id = `RUN-20261024-002609`，`must_change_count = 5`。case_states 记录 `state_counts.已修订待验 = 5`、`pending_verified = 5`、`rework_cycles.limit = 3`、`n6_n8_cycles = 0`；各用例 `compile_rc = 0`、`static_check = pass`、`updated_by = loop:N10`、`updated_at = 2026-10-24T22:07:52+0800`，状态均为 `已修订待验`；note 均为 `N10：卡点D 判据未通过 ⇒ 保持待验，不得称跑通`。

| case | file | md5_before | md5_after | state |
|---|---|---|---|---|
| tc_cpu_i2c_03 | TESTLIB/tc_cpu_i2c_03.sv | 74ea6e5d6ead2408753a727ab2055f40 | 6f14e6beb030fd3d069bd3a7657d9005 | 已修订待验 |
| tc_pcie_rw_02 | TESTLIB/tc_pcie_rw_02.sv | eab350bb81d14bb9987bd6691a26df54 | 4c31f76cdc452d0ac771f2d89f72cb23 | 已修订待验 |
| tc_pcie_rw_smoke | TESTLIB/tc_pcie_rw_smoke.sv | 75f95660d375ac2abd0595efa04b2c63 | 1d1f3ba9dc1067d41867e0d8b1b53913 | 已修订待验 |
| tc_rtc_05 | TESTLIB/tc_rtc_05.sv | d0649ceebadf6ce32c768ee1230c314f | 80b13e5f9e79a82b7f083afb9eeea886 | 已修订待验 |
| tc_rtc_10 | TESTLIB/tc_rtc_10.sv | 6f4fa3d7b82f3dc2bae69de92dd89060 | 49bcfe2ce26d3ebfb97424fa7082036e | 已修订待验 |

上述修订不代表判据通过；各用例 note 明确要求保持待验，不得称跑通。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/case_states.json`

## 两套口径（并列陈述）

两套口径分别取、分别存，不得互相替代（doc/AGENTS.md 红线 3 / spec I3）。

**全局逐用例求和**

- 口径一（`*E` 文本行数，逐用例求和）：value = 1716，zero = false。
- 口径二（UVM Report Summary，逐用例求和）：UVM_ERROR = 0，UVM_FATAL = 0，UVM_WARNING = 0，UVM_INFO = 59060，zero = true。

| case | 口径一 value | 口径一 zero | 口径二 UVM_INFO | 口径二 UVM_ERROR | 口径二 UVM_FATAL | 口径二 UVM_WARNING | 口径二 zero | both_zero |
|---|---:|---|---:|---:|---:|---:|---|---|
| tc_cpu_i2c_03 | 29 | false | 29 | 0 | 0 | 0 | true | false |
| tc_pcie_rw_02 | 1687 | false | 34934 | 0 | 0 | 0 | true | false |
| tc_pcie_rw_smoke | 0 | true | 60 | 0 | 0 | 0 | true | true |
| tc_rtc_05 | 0 | true | 82 | 0 | 0 | 0 | true | true |
| tc_rtc_10 | 0 | true | 23955 | 0 | 0 | 0 | true | true |

**口径二为 0 不足以判绿**：即使口径二的 UVM_ERROR、UVM_FATAL、UVM_WARNING 均为 0，只要口径一非 0 或期望观测点印记不一致，就不得判跑通。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-003330_tc_cpu_i2c_03_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-141810_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143644_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143755_tc_rtc_05_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-144201_tc_rtc_10_1_run.log`

## 观测印记

顶层 `imprints = {}`。逐用例印记如下。

- tc_cpu_i2c_03：`imprints = {}`，无预期观测点印记；verdict.reasons 包含 `无预期观测点印记（I3：预期观测点必须留下通过印记）`。
- 其余印记的 expected 均为：address = `0x0d00+0x04`，entry_name = `pcie_test`，marker_entry = `0x0d00#0x0d04`，resolved_by = `run-snapshot`，source = `/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/bundle/doc_entries.jsonl`，value = `0x00000000`。

| marker | case | observed address | observed id_count | observed imprint_count | observed value | observed sim_time | observed ref | observed text |
|---|---|---|---:|---:|---|---:|---|---|
| N6_pcie_test_tc_pcie_rw_02 | tc_pcie_rw_02 | 0x0d00+0x04 | 1 | 1 | 0x78560000 | 3974.113 us | tc_pcie_rw_02.sv:243 | OK 0x0d00+0x04 pcie_test = 0x78560000 |
| N6_pcie_test_tc_pcie_rw_smoke | tc_pcie_rw_smoke | 0x0d00+0x04 | 1 | 1 | 0x78560000 | 165.177 us | tc_pcie_rw_smoke.sv:118 | OK 0x0d00+0x04 pcie_test = 0x78560000 |
| N6_pcie_test_tc_rtc_05 | tc_rtc_05 | 0x0d00+0x04 | 1 | 1 | 0x78560000 | 258.601 us | tc_rtc_05.sv:120 | OK 0x0d00+0x04 pcie_test = 0x78560000 |
| N6_pcie_test_tc_rtc_10 | tc_rtc_10 | 0x0d00+0x04 | 1 | 1 | 0x78560000 | 283.641 us | tc_rtc_10.sv:126 | OK 0x0d00+0x04 pcie_test = 0x78560000 |

上述四个印记的 checks 均为 `address_matches_expected: true`、`count_matches_id_count: true`、`id_count_present: true`、`imprint_present: true`、`value_matches_expected: false`；因此 `consistent = false`，`failed_count = 1`，`verified_count = 4`，失败项均为 `['value_matches_expected']`。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-003330_tc_cpu_i2c_03_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-141810_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143644_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143755_tc_rtc_05_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-144201_tc_rtc_10_1_run.log`

## 受影响用例态

case_states 显示：`state_counts.已修订待验 = 5`，`pending_verified = 5`，`present = true`，`rework_cycles.limit = 3`，`n6_n8_cycles = 0`；各用例均为 `state = 已修订待验`、`compile_rc = 0`、`static_check = pass`。

聚合 verdict：`passed = false`；criterion = `聚合判据 = 各用例 I3 判据的合取（含印记三向一致）`。

逐例 verdict.reasons：

- tc_cpu_i2c_03：判据未通过（口径一 = 29 ≠ 0；无预期观测点印记（I3：预期观测点必须留下通过印记））
- tc_pcie_rw_02：判据未通过（口径一 = 1687 ≠ 0；印记 N6_pcie_test_tc_pcie_rw_02 三向不一致：['value_matches_expected']）
- tc_pcie_rw_smoke：判据未通过（印记 N6_pcie_test_tc_pcie_rw_smoke 三向不一致：['value_matches_expected']）
- tc_rtc_05：判据未通过（印记 N6_pcie_test_tc_rtc_05 三向不一致：['value_matches_expected']）
- tc_rtc_10：判据未通过（印记 N6_pcie_test_tc_rtc_10 三向不一致：['value_matches_expected']）

所有受影响用例保持待验，不得据口径二为 0 或静态检查 pass 宣称跑通。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/case_states.json`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-003330_tc_cpu_i2c_03_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-141810_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143644_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143755_tc_rtc_05_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-144201_tc_rtc_10_1_run.log`

## 未闭环项与冲突

冲突与未闭环事实：`conflicts.total = 72`，`conflicts.blocks_release = 72`，`chain = intact`。tc_cpu_i2c_03 的口径一 = 29 ≠ 0 且无预期观测点印记；tc_pcie_rw_02 的口径一 = 1687 ≠ 0 且印记 value_matches_expected 失败；tc_pcie_rw_smoke、tc_rtc_05、tc_rtc_10 的口径一均为 0、口径二 UVM_ERROR/UVM_FATAL/UVM_WARNING 均为 0，但其印记 value_matches_expected 均失败，故均不得判跑通。

口径二为 0 不足以判绿：口径一非 0 或印记不一致时不得判跑通。本报告仅陈述评估事实，不替人做发版决策。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/case_states.json`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-003330_tc_cpu_i2c_03_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-141810_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143644_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-143755_tc_rtc_05_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/runs/RUN-20261024-002609/evidence/20261024-144201_tc_rtc_10_1_run.log`

## 未闭环项

- tc_cpu_i2c_03：判据未通过；口径一 = 29 ≠ 0；无预期观测点印记（I3：预期观测点必须留下通过印记）。
- tc_pcie_rw_02：判据未通过；口径一 = 1687 ≠ 0；印记 N6_pcie_test_tc_pcie_rw_02 三向不一致：['value_matches_expected']。
- tc_pcie_rw_smoke：判据未通过；印记 N6_pcie_test_tc_pcie_rw_smoke 三向不一致：['value_matches_expected']；口径二 UVM_ERROR = 0、UVM_FATAL = 0、UVM_WARNING = 0，但口径二为 0 不足以判绿。
- tc_rtc_05：判据未通过；印记 N6_pcie_test_tc_rtc_05 三向不一致：['value_matches_expected']；口径二 UVM_ERROR = 0、UVM_FATAL = 0、UVM_WARNING = 0，但口径二为 0 不足以判绿。
- tc_rtc_10：判据未通过；印记 N6_pcie_test_tc_rtc_10 三向不一致：['value_matches_expected']；口径二 UVM_ERROR = 0、UVM_FATAL = 0、UVM_WARNING = 0，但口径二为 0 不足以判绿。
- 印记 expected value = 0x00000000，observed value = 0x78560000；各印记 failed_count = 1、verified_count = 4。
- conflicts.total = 72；conflicts.blocks_release = 72；chain = intact。
- rework_cycles.limit = 3；n6_n8_cycles = 0；pending_verified = 5；state_counts.已修订待验 = 5。
- 口径二为 0 不足以判绿：口径一非 0 或印记不一致时不得判跑通。
- 本报告不替人做发版决策。
