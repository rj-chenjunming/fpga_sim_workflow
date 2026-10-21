# F16 N8 上下文预算分片 · 切片计划

> P0 缺陷修复（[执行手册 §2 F16](OPTIMIZATION_PLAYBOOK.md)、[STATUS §17](../STATUS.md)）。由 Lead 实现；
> 实现后另派独立验证者复核（不再自证）。

| 项 | 内容 |
|---|---|
| 类型 | 缺陷修复（规格-实现-预算三者冲突） |
| 基线提交 | `c9b8644` |
| 唯一 owner | Host 上下文构造器（预算与覆盖）＋ N8 节点 owner（提示词）；同一 owner 本切片 |
| 规格位置 | [上下文规格 C1](../spec/AGENT_CONTEXT_SPEC.md)、[编排规格 §3 N8 行](../spec/LOOP_ORCHESTRATION_SPEC.md) |
| 允许修改 | `loop/workflows/chunks/model_steps.py`、`loop/prompts/loop_nodes.yaml`、`loop/tests/test_n8_context_budget.py`（新增）、两份规格、本计划、`doc/STATUS.md`、`doc/plans/OPTIMIZATION_PLAYBOOK.md`（F16 状态） |
| 不修改 | `kb/**`、闸门、拓扑、冻结证据；不改 120000 总预算 |

## 1 问题（已实测）

`_sandbox_code()` 对每个 ≤6000 字符的沙箱用例文件整篇下发；drill 夹具轮共约 30 个文件 ⇒
`sandbox_cases` 单项 **120063 bytes**，加 `revision_points` 6453 与 contract 2728 = **130546 > 120000**，
`check_budget` 显式失败 ⇒ drill 全链在 G1 后必挂（STATUS §17 复现）。

规格 C1 同时要求「小文件保留全文」与「超预算显式失败」，在真实输入规模下**不可同时满足** ⇒ 契约缺陷。

## 2 目标可观察行为

- 每个沙箱用例文件都出现在 `sandbox_cases` 中（不丢文件）。
- 单文件 > 6000 字符（既有规则）⇒ `changed_regions` 片段，缺源/无法定位显式失败。
- 总大小超 `N8_SANDBOX_BUDGET_BYTES`（默认 60000）时，按文件名的确定性顺序把放不下的**小文件**也降级为
  `changed_regions` 片段；每件带 `coverage{mode, complete, scope, regions}`；请求带 `coverage_summary{used_bytes, budget_bytes, full_files, region_files}`。
- 无法给出片段（缺源文件/无法定位变更）且放不下全文 ⇒ 显式失败（`RuntimeError`），不静默丢。
- 夹具轮 N8 请求整体 ≤ 120000，drill 能越过 G1 继续。

## 3 不变量

1. **不静默抽样**：降级必须逐件标注并汇总；不可只发部分行而无 coverage。
2. **确定性**：同一输入两次构造的 files/顺序/降级集合一致（按文件名排序）。
3. **不删文件、不改总预算**：120000 不变；降级只改表示形式。
4. **fail closed**：片段不可得即失败，不猜。

## 4 实测（数字从命令输出复制）

| 验证 | 原始输出 | 说明 |
|---|---|---|
| 修改前红灯（新用例） | `5 failed in 0.60s` | `build_sandbox_cases` 不存在 |
| 修改后新用例 | `5 passed in 0.56s` | 预算内全文/超预算降级/确定性/缺源闭锁/小输入保持 |
| N8 相关既有用例 | `51 passed in 1.29s` | `test_agent_context_memory` + 新用例；大文件片段规则保持 |
| 软件层单用例（原阻断） | `1 passed` | G1 后不再 budget failed |
| 软件层 `test_flow.py` | `18 passed in 26.54s` | 修复前同一入口 `11 failed` |
| 默认根全套 | `46 failed, 280 passed, 3 skipped in 11.13s` | 46 项仍为 `ENV_ROOT` 只读同因；通过数 275→280 = 新增 5 项 |

**实现要点**：单文件 >6000 字符仍强制片段（防单文件过大）；其余文件默认全文，超
`N8_SANDBOX_BUDGET_BYTES`（60000）时按文件名顺序降级；`changed_regions` 不再重复下发 after 文本
（after 只在 `excerpt`），并按**实际序列化大小**计费；片段不可得即 fail closed。

## 5 回退

还原 `build_sandbox_cases` 为全量全文 + 移除 `coverage_summary` 即回到原行为；历史请求记录不回填。
