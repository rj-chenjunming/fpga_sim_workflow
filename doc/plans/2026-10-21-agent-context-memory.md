# Agent 可靠性与记忆优化计划

契约：[AGENT_CONTEXT_SPEC](../spec/AGENT_CONTEXT_SPEC.md)。用户已明确要求按 SpecDD 优化，并将流程要求沉淀进仓库指令。

## 实施顺序

1. Lead 明确 C1/M1/M2 与写权，更新根 AGENTS.md；使用既有文件名，避免再建立一份 AGENT.md 造成流程分叉。
2. 固定小输入、独立请求、返工意见和既有拒绝的特征基线，先运行原实现。
3. 上下文与记忆新行为先编写失败用例。按 Host 模块提取输入预算、记录与筛选能力，再接入模型请求；保持 schema、业务 validator、闸门和沙箱写者。
4. 先消除 N3/N8 静默截断；再记录每次调用；最后接入人工确认、作用域精确匹配的经验。每项验收基于可观察请求/产物，不以源码字符串代替行为。
5. 运行新增测试和可用回归；UI 上轮改动与冻结证据保留。四道门与内网限制分别记录，不伪造全绿。

| Owner | 落点 | 验证门 |
|---|---|---|
| Lead | AGENTS.md、规格、计划、状态 | 规则一致与路径检查 |
| Host 实现 owner | `loop/host/agent_memory.py`、上下文构造 | 边界/写盘/来源/版本/覆盖测试 |
| 编排实现 owner | `loop/workflows/chunks/model_steps.py` | 请求输入、原输出契约及失败路径回归 |
| 验证阶段 | `loop/tests/test_agent_context_memory.py` | 先绿特征、先红回归、改后通过 |

本轮由同一执行者顺序承担实现与验证，不声称独立复核；不修改 kb 冻结工具、内网资产或历史归档。

## 命令

```bash
cd loop
LOOP_LLM_MODE=standin .venv/bin/python -m pytest tests/test_agent_context_memory.py -q
# 按 STATUS 的当前可用回归集合执行；完整门仍按 AGENTS.md §4 在内网测试副本顺序执行
```

经验配置通过人工在工作区 adjudication 下维护；运行记录核验由 `python -m host.agent_memory --verify <attempt-dir>` 提供，仅读取与校验，不重发模型请求。
