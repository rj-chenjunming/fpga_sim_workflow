# F06 模型请求机制与节点语义分离 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F06（P1 保持行为重构）、
> [AGENT_CONTEXT_SPEC 实现结构](`../spec/AGENT_CONTEXT_SPEC.md`)。
> **纯重构切片**：先固定特征基线并跑绿，不适用红灯用例（§5 允许）。

| 项 | 内容 |
|---|---|
| 类型 | 保持行为重构（不改契约/提示词/Schema/拓扑/产物形状） |
| 基线提交 | `86b6216` |
| 唯一 owner | Host 请求 owner + 节点 owner（本切片同一 owner） |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [AGENT_CONTEXT_SPEC 实现结构](../spec/AGENT_CONTEXT_SPEC.md)、M1 |
| 允许修改 | `loop/workflows/chunks/`（新增 `model_request.py` / `model_common.py` / `n6_facts.py` / `n10_semantics.py` / `n11_guard.py`；`model_steps.py` 减重与兼容导出）、`doc/spec/AGENT_CONTEXT_SPEC.md`、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | 提示词、Schema、N8 分片判据、闸门、拓扑、`kb/**`、冻结证据；不改任何输入字段/产物内容 |

## 1 问题

`model_steps.py`（约 2200 行）同时承担：请求机制（contract/ask/attempt/控制包装）、Host 校验、
N6 事实构造（含 API 语义解析）、N8 沙箱分片、N10 分类/对账辅助、N11 守护辅助、N3/N12 叙述。
机制与节点语义混在一个文件：改任一节点的语义都要碰同一文件；请求机制无法独立被固定与复核；
`implementation_sha256` 也只能反映这个大文件的指纹。

## 2 目标可观察行为（重构后仍成立）

1. 每个模型请求仍是**新 agent**；预算检查在请求前；取消/重发不消费旧结果。
2. 提示词/Schema/输入字段及顺序、产物内容、业务工具参数、节点返工行为与重构前逐项相同。
3. N8 分片/闭锁语义不变；N6 事实构造字段不变；N10/N11 台账与返工效果等价。
4. `model_steps.py` 保留节点入口名与兼容导出（`build_n6_targets`、`build_sandbox_cases`、常量等），
   TriggerFlow 拓扑与所有既有消费者零改动。
5. Host 校验唯一实现（`_validate` 不复制）；机制层通过参数接收校验器。

## 3 不变量

1. 一次提交只搬一个关注点：机制 → N6 事实 → N10 辅助 → N11 辅助；每步后跑同一特征集。
2. 不改任何判定/校验/分片逻辑；如发现必须改行为，另立切片先改规格。
3. `implementation_sha256` 改为机制模块指纹属预期变化，记录在案，不用它替代语义对照。
4. 不改测试期望；测试文件零改动（除新增结构断言）。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F06-1 | 规格实现结构 + 本计划 | 文档门 |
| F06-2 | 特征基线（重构前）：机制/节点/控制/分片测试 + `test_flow.py` | 全绿（原始输出入 STATUS） |
| F06-3 | 提取 `model_common.py` + `model_request.py`（validator 注入），`model_steps` 兼容导出 | 同一特征集全绿 |
| F06-4 | 提取 `n6_facts.py`、`n10_semantics.py`、`n11_guard.py` | 同一特征集全绿 |
| F06-5 | 独立复核报告（`doc/audit/`，只读子代理） | 语义对照 + 指纹如实记录；md5 记入 STATUS |
| F06-6 | STATUS §27 | 命令与输出逐字复制；未运行项单列 |

**验证边界**：受控 provider 证明机制与调用顺序；真实模型质量、真实 provider 取消行为本机未验证。

## 5 回退

按模块回退提取提交；`model_steps.py` 的兼容导出保证消费者无需同步回退。
