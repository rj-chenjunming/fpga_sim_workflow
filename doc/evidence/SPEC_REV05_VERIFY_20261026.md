# SPEC-REV-05 实现与验证（R1 失败报告收口 / R2 真实轮冻结为 drill 夹具）· 2026-10-26

> **这份证据证明什么**：
> ① R1（方案 D）在真实服务进程上生效——失败报告 `accept` 无理由被 403、有理由 200；
> ② R2 的 drill 夹具能**逐项复现**真实轮的 5 个用例与两套口径（合计 1716，逐例 29/1687/0/0/0）；
> ③ 一轮 drill 能走完 N0→N16 并停在合法终点（N16 `refused`）。
> **不证明**：判据通过、环境就绪、S0-b 已接入。
>
> 记录方式：命令输出与 run 文档直接引用；数字不经手算。

---

## 1 R1：失败报告的 accept 通道（方案 D）

drill run `RUN-20261026-135835`（报告 `claimed_verdict=not_passed`）在 G2 上：

| 动作 | 请求 | 结果 |
|---|---|---|
| 无理由 accept | `{"decision":"accept","actor":"human:lead-verify-20261026"}` | **403**，错误原文：`D：本轮报告结论为 not_passed（未通过）⇒ 接受失败报告必须给出理由（reason）。…接受报告不等于判据通过，N16 仍受 I3/I4 阻断。` |
| 有理由 accept | 同上 + `"reason":"…接受未通过报告…"` | **200**，`ok=true`，`warnings=["报告结论 not_passed：accept 作为失败收口（已给理由）；0 个用例仍待验，不得称跑通"]` |

判定链未放松：G2 仍保留 `I3_KOUTOU1_NONZERO`、`I4_CONFLICTS_UNCLEARED` 两条 blocker；
accept 后 N16 仍 `refused`（见 §3）。

---

## 2 R2：真实轮冻结为 drill 夹具（逐项复现）

| 项 | 真实轮 `RUN-20261024-002609` | drill 回放 `RUN-20261026-135835` |
|---|---|---|
| 用例数 | 5 | **5** |
| `tc_cpu_i2c_03` 口径一 | 29 | **29** |
| `tc_pcie_rw_02` 口径一 | 1687 | **1687** |
| `tc_pcie_rw_smoke` / `tc_rtc_05` / `tc_rtc_10` | 0 / 0 / 0 | **0 / 0 / 0** |
| 口径一合计 | 1716 | **1716** |
| 口径二 UVM_ERROR/FATAL | 0 / 0 | **0 / 0** |
| N9 status | `fail` | **`fail`** |
| N12 结论 | `not_passed` | **`not_passed`** |
| 耗时 | 21.56 h（真实仿真） | **秒级**（只回放，不重跑） |

夹具目录：`workspaces/s0-ws-20261023/fixtures/drill-real-20261024/`（14 MB，35 个文件，
`md5.txt` 逐文件清单，`drill_cases.json` 声明 5 例与日志映射）。
冻结内容：`n1_manifest_new.json`、`n2_diff.json/.md`、`n3_digest.md`、`n5_impact.json/.md`、
`n10_pending.json`、`n10_reconcile.md`、`n12_report.md`、`sandbox/TESTLIB/*.sv`、
`evidence/`（5 份 run.log + 15 份三库日志）。**不含** `case_states.json`/`gates.json`（身份与闸门必须从空开始）。

选择方式：`LOOP_DRILL_FIXTURE=fixtures/drill-real-20261024`（缺省仍是 legacy
`runs/RUN-20261015-120626`，`accept_v1_run.sh` 不受影响）；缺件时**启动期显式失败**，不静默回退。

---

## 3 drill 全流程终点（N0→N16）

| 节点 | status | 摘要 |
|---|---|---|
| N9 | `fail` | 5 例回放，口径一 1716，UVM_ERROR/FATAL 0/0 |
| N10 | `fail` | `verdict_passed=False` |
| N11 | `intact` | 身份链完整（回放无身份头，如实标注） |
| N12 | `standin` | `claimed_verdict=not_passed`（standin 模式） |
| N13（G2） | `accept` | `human_signed=true`，有理由 |
| N14（G3） | `milestone_only` | 先试 `full_now` 被 **403 I4**（72 条 `blocks_release`）拒绝，改选 `milestone_only` |
| N15/N15_select | `ok` | 按 milestone 选 5 个回归用例；drill 显式 no-op |
| N16 | **`refused`** | dry-run `rc=3`，actor=`human:lead-verify-20261026` |

run 最终 `status=finished`（合法终点）。

---

## 4 一并暴露的运维风险（必须记住）

**改工作流代码后重启服务，会让停在闸门的 run 恢复失败。**

| run | 重启前 | 重启后 |
|---|---|---|
| `RUN-20261024-002609`（真实轮，停在 G2） | `waiting_gate` | **`failed`**：`恢复失败：async_load 异常 ValueError: Can not load TriggerFlow execution snapshot. … flow definition fingerprint mismatch.` |
| `RUN-20261023-213737`（drill，停在 G1） | `waiting_gate` | **`failed`**（同因） |

- 五个用例的**数据与证据未丢**：`n9_run_summary.tsv`、`case_states.json`、`n12_report.md`、
  5 份 run.log 全在；快照也留在 `state/recovery/<run_id>.json`（未被删除）。
- 根因：TriggerFlow 快照带"工作流定义指纹"，代码变了就拒载（fail-closed 设计，不是数据损坏）。
- 结论：**要改 `loop/workflows/**` 或 `loop/services/**` 前，先把停着的 run 处理完/接受完**；
  或按本文的 R2 夹具路线用 drill 复现，不要在真实轮停在闸门时改代码重启。
- 本次的真实轮因此无法再在 UI 上点 accept；其结论已由 drill 回放（§2）完整复现。

---

## 5 可复核路径

| 产物 | 路径 |
|---|---|
| drill run 文档 | `workspaces/s0-ws-20261023/runs/RUN-20261026-135835/` |
| drill 夹具 | `workspaces/s0-ws-20261023/fixtures/drill-real-20261024/`（含 `md5.txt`、`drill_cases.json`） |
| 真实轮证据（保留） | `workspaces/s0-ws-20261023/runs/RUN-20261024-002609/`（run 文档现为 failed，数据件齐） |
| 契约 | [SPEC-REV-05](../spec/SPEC-REV-05-20261026.md)、[SPEC-01 §1 I2 增补](../spec/CHANGE_IMPACT_LOOP_SPEC.md) |
