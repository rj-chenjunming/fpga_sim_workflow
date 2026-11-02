# 冻结目录变更留证：新增分流闸门 `G1_no_impact`（2026-10-30）

> 依据 AGENTS.md §3：`kb/tools/**`、`kb/schema/**` 是**冻结目录**，「改语义需单独变更并留证」。
> 本次变更**只追加**一个闸门与两个决策值，不改既有三道主线闸门的 id / 枚举 / 语义。
> 业务契约：[CHANGE_IMPACT_LOOP_SPEC §12](../../spec/CHANGE_IMPACT_LOOP_SPEC.md)；
> 机制契约：[LOOP_ORCHESTRATION_SPEC §14](../../spec/LOOP_ORCHESTRATION_SPEC.md)；
> 计划：[2026-10-30-zero-must-change-gate.md](../../plans/2026-10-30-zero-must-change-gate.md)。
> 证据冻结：本目录只增不改；md5 账本在目录外 `doc/evidence/KB_GATE_NO_IMPACT_20261030.md5`。

## 1 改了什么（逐项）

| 文件 | 变更 | 为什么不可省 |
|---|---|---|
| `kb/tools/kb_lib.py` | 新增 `GATE_IDS_V1`（原三项，供读旧记录）；`GATE_IDS` **末尾追加** `"G1_no_impact"`；`GATE_KIND` 加 `diff_confirm`；`GATE_DECISIONS` 加 `["no_impact_end","full_regression","pending"]`；`gate_init` 写 `version: 2`；新增 `GATE_BRANCH_ONLY` + `gate_applicable()`；`gate_summary` 按 version 决定必需门集合、按适用性算 `all_signed` | 决策枚举权威只此一处（AGENTS §5 红线 4）；不新增则分支决策在 `gate_set` 被拒 |
| `kb/schema/gate_state.schema.json` | `title/description` 登记新门；`version` 允许 `1/2`；`gates.properties` 加新门（`required` 仍只含三项主线门）；`gate_id` 枚举加新门 | 新 `gates.json` 必须能过 `kb_lib.check`；旧 v1 文件必须仍合法 |
| `kb/tools/gate.py` | 文档头登记新门；`DEFAULT_EXPECT` 加 `None`（已决策即可）；`load_state` 按 `version` 决定必需门集合（v1 旧记录可读、v2 缺门判破损 rc=4）；`cmd_show` 按记录里实际存在的门展示（读历史 v1 不再 KeyError） | 向后兼容：历史 `gates.json` 仍可审计回放 |

**没有改的**：`GATE_IDS` 前三项顺序与内容、`GATE_DECISIONS` 既有三门的值、
`n16_promote.py` 的晋升前置（它只显式检查三道主线门；`no_impact_end` 分支无 G3 ⇒ 自然不会晋升）、
`run_guarded.sh`、任何既有 schema 约束语义。

## 2 实测（数字从命令输出复制）

- **gate CLI**（`gate-cli.log`，在一次性 `LOOP_WORKSPACE` 上跑，不碰真实 kb/runs）：
  `init` 写出 `version=2` + 4 门；`sign G1_no_impact --decision no_impact_end --actor-kind human` 成功；
  `require-signed --gate G1_no_impact --expect no_impact_end` ⇒ `[kb] 闸门已满足`；
  非法决策 `close_now` ⇒ `rc=2`（argparse 报合法值 `no_impact_end, full_regression, pending`）；
  非 human 署名 ⇒ `rc=3`（"模型/脚本不得替人盖章（I6）"）；
  **旧 v1 记录**（3 门）`show` ⇒ `rc=0`（`all_signed=True human_signed_all=True`）；
  **v2 记录缺新门** ⇒ `rc=4`（`gates.json 缺闸门 G1_no_impact（状态不完整；version=2）`）。
- **kb 自测 + 环境层**（`kb-selftests.log`）：`_selftest_gate_schema.py: PASS=10 FAIL=0`、
  `_selftest_n5_reachability.py: PASS=9 FAIL=0`、`_selftest_adjudicate_conflicts.py: PASS=28 FAIL=0`；
  环境层 `3 passed, 24 deselected in 9.78s`；原 `ENV_ROOT` 零写入（`find -newer` 命中 0）；`rc=0`。
- **分支/端到端分支**（软件层全量 `2054 passed`、浏览器 `183 passed`、端到端 `=> ALL PASS`）：见 [`../NO_IMPACT_GATE_20261030/README.md`](../NO_IMPACT_GATE_20261030/README.md)
  （`loop/tests/test_no_impact_gate.py`：kb 形状、投影、守卫、N5 出口事件、全量目标集、drill 两分支）。

## 3 本目录文件

| 文件 | 说明 |
|---|---|
| `kb-frozen-change.diff` | 三个冻结文件的完整 diff（`git diff` 原样，未提交） |
| `gate-cli.log` | 枚举/`schema` 形状、`init/sign/require-signed/show`、非法决策、非 human、v1 兼容与 v2 缺门实测 |
| `kb-selftests.log` | `spikes/run_env_layer_checks.sh --with-kb-selftests` 输出（含原 `ENV_ROOT` 零写入自证） |
