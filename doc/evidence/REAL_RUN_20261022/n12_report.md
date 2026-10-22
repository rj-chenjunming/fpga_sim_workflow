# RUN-20261022-181700 评估报告草稿（N12）

- 模型模式：`live`；provider：`origin-deepseek-v4-1-flash`
- claimed_verdict：`not_passed`

## 本轮改了什么

受影响用例（`state_counts.已修订待验`: 3）：

- `tc_pcie_rw_02`：`TESTLIB/tc_pcie_rw_02.sv`，`md5_before` 为 `eab350bb81d14bb9987bd6691a26df54`，`md5_after` 为 `9139589046f1ceea8af59e9249f66f0b`；`compile_rc`: 0，`static_check`: pass，`state`: 已修订待验。
- `tc_pcie_rw_smoke`：`TESTLIB/tc_pcie_rw_smoke.sv`，`md5_before` 为 `75f95660d375ac2abd0595efa04b2c63`，`md5_after` 为 `18822965d0c39184a3b029c9de8b82fe`；`compile_rc`: 0，`static_check`: pass，`state`: 已修订待验。
- `tc_rtc_05`：`TESTLIB/tc_rtc_05.sv`，`md5_before` 为 `d0649ceebadf6ce32c768ee1230c314f`，`md5_after` 为 `5a5c9f73e1f8efc253f4ed976c67bd78`；`compile_rc`: 0，`static_check`: pass，`state`: 已修订待验。

以上用例 `updated_by` 为 `loop:N10`；`note` 均为“N10：卡点D 判据未通过 ⇒ 保持待验，不得称跑通”。本报告仅形成评估草稿，不替人做发版决策。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/case_states.json`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/sandbox/TESTLIB/tc_pcie_rw_02.sv`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/sandbox/TESTLIB/tc_pcie_rw_smoke.sv`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/sandbox/TESTLIB/tc_rtc_05.sv`

## 两套口径（并列陈述）

两套口径分别取、分别存，不得互相替代（doc/AGENTS.md 红线 3 / spec I3）。

**口径一（`*E` 文本行数，逐用例求和）**：`value`: 1687，`zero`: false。`refs` 覆盖 line 357、line 360、line 363、line 366、line 374、line 35152、line 35153、line 35154。

**口径二（UVM Report Summary，逐用例求和）**：`value`: {UVM_ERROR: 0, UVM_FATAL: 0, UVM_INFO: 35066, UVM_WARNING: 0}，`zero`: true。

逐用例并列：

- `tc_pcie_rw_02`：口径一 `value`: 1687，`zero`: false；口径二 UVM_ERROR: 0、UVM_FATAL: 0、UVM_INFO: 34930、UVM_WARNING: 0，`zero`: true；`both_zero`: false。
- `tc_pcie_rw_smoke`：口径一 `value`: 0，`zero`: true；口径二 UVM_ERROR: 0、UVM_FATAL: 0、UVM_INFO: 57、UVM_WARNING: 0，`zero`: true；`both_zero`: true。
- `tc_rtc_05`：口径一 `value`: 0，`zero`: true；口径二 UVM_ERROR: 0、UVM_FATAL: 0、UVM_INFO: 79、UVM_WARNING: 0，`zero`: true；`both_zero`: true。

**口径二为 0 不足以判绿**：口径一非 0 或印记不一致时，不得判跑通。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-193218_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195119_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195230_tc_rtc_05_1_run.log`

## 观测印记

`imprints`: {}；逐用例 `tc_pcie_rw_02`、`tc_pcie_rw_smoke`、`tc_rtc_05` 的 `imprints` 均为 {}。各用例均无预期观测点印记，触发 I3：预期观测点必须留下通过印记。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-193218_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195119_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195230_tc_rtc_05_1_run.log`

## 受影响用例态与判定事实

`case_states.pending_verified`: 3；`state_counts.已修订待验`: 3；`rework_cycles.limit`: 3；`rework_cycles.n6_n8_cycles`: 0。

| case | state | static_check | compile_rc | verdict.passed | reasons |
|---|---|---|---|---|---|
| `tc_pcie_rw_02` | 已修订待验 | pass | 0 | false | 口径一 = 1687 ≠ 0；无预期观测点印记（I3：预期观测点必须留下通过印记） |
| `tc_pcie_rw_smoke` | 已修订待验 | pass | 0 | false | 无预期观测点印记（I3：预期观测点必须留下通过印记） |
| `tc_rtc_05` | 已修订待验 | pass | 0 | false | 无预期观测点印记（I3：预期观测点必须留下通过印记） |

聚合判据 = 各用例 I3 判据的合取（含印记三向一致）；`verdict.passed`: false。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/case_states.json`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-193218_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195119_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195230_tc_rtc_05_1_run.log`

## 未闭环项与冲突

- `conflicts.total`: 72；`conflicts.blocks_release`: 72。
- `pending_verified`: 3；`state_counts.已修订待验`: 3。
- `imprints`: {}；各用例均无预期观测点印记。
- `tc_pcie_rw_02`：口径一 = 1687 ≠ 0，且无预期观测点印记；不得称跑通。
- `tc_pcie_rw_smoke`：口径二为 0，但无预期观测点印记；口径二为 0 不足以判绿。
- `tc_rtc_05`：口径二为 0，但无预期观测点印记；口径二为 0 不足以判绿。
- `rework_cycles.n6_n8_cycles`: 0，`rework_cycles.limit`: 3。

本报告仅陈述当前事实与 blockers，不替人做发版决策；不以历史 approved_experiences 替代当前 Host 校验。

引用：`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/case_states.json`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-193218_tc_pcie_rw_02_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195119_tc_pcie_rw_smoke_1_run.log`、`/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/RUN-20261022-181700/evidence/20261022-195230_tc_rtc_05_1_run.log`

## 未闭环项

- conflicts.total: 72；conflicts.blocks_release: 72。
- pending_verified: 3；state_counts.已修订待验: 3。
- imprints: {}；各用例均无预期观测点印记（I3：预期观测点必须留下通过印记）。
- tc_pcie_rw_02：口径一 = 1687 ≠ 0，且无预期观测点印记；不得称跑通。
- tc_pcie_rw_smoke：口径二为 0，但无预期观测点印记；口径二为 0 不足以判绿。
- tc_rtc_05：口径二为 0，但无预期观测点印记；口径二为 0 不足以判绿。
- rework_cycles.n6_n8_cycles: 0，rework_cycles.limit: 3。
