# Agent 上下文、调用记录与经验契约

> 运行干预见 [AGENT_WINDOW_SPEC.md](AGENT_WINDOW_SPEC.md)。新尝试携带本会话 human_interventions，仍执行原预算、记录及 Host 校验；不覆盖旧尝试，不自动晋升经验。

本契约由用户授权的本轮优化建立。上游为 [编排规格](LOOP_ORCHESTRATION_SPEC.md)、[业务规格](CHANGE_IMPACT_LOOP_SPEC.md)，执行纪律为 [AGENTS.md](../../AGENTS.md) §2。
本轮不变更执行拓扑、审批身份或业务权威，不引入自动学习与向量数据库。

## Owner 与范围

| 数据 | 唯一 owner | 消费者 |
|---|---|---|
| 模型输入与覆盖信息 | Host 上下文构造器 | N3/N6/N8/N10/N11/N12 请求 |
| 本轮工作状态 | TriggerFlow 节点 | 后继节点与显式返工边 |
| 调用记录 | Host / `loop/host/agent_memory.py` | 开发者核验 CLI、输出的记录引用、经验来源核验 |
| 已确认经验目录 | 人工维护的工作区 adjudication 文件 | Host 精确筛选后作为有来源建议提供给模型 |
| 闸门/用例态/基线 | 既有 kb 工具 | 现有消费者，记忆层不得回写 |

## C1 输入覆盖与预算

- N3 保留输入差异顺序，提供全部差异及完整 before/after；禁止固定条数或字段字符截断。
- N6 同一用例有多个修订点时，`targets[].excerpts` 按输入顺序提供每一处片段；保留 `excerpt` 为首个片段的兼容字段，不能只提供首处代码而要求模型修订远处目标。
- N6 提供已解析调用定义的完整签名/函数体及 complete 标记，不按固定函数数量或行数截断；定义未闭合时 real 输入构造失败。扫描缓存只在本次目标构造中共享，跨轮重新读取，包含曾经未找到的定义。找不到定义仍显式为空，模型按原规则不得猜测参数语义。
- N8 小文件保留全文。大文件基于**源代码与沙箱的实际差异**提供所有变更前后片段及行号；缺源文件或变更无法定位时不得猜测复核范围。全文和片段均带文件指纹、模式、覆盖数；不能用“覆盖了变更”冒充全文复核。
- 所有模型请求以完整序列化 input/info/instruct/schema 的 UTF-8 大小检查预算。默认上限 `120000` bytes；超过上限在模型调用前显式失败，记录预算/失败，不裁剪、丢用例或静默抽样。这是应用输入预算，不承诺等于提供方 token 上限。
- 输入缺失/校验错误继续走既有失败收敛路径；drill 替身保留明确标注，不能被记录为 live 成功。

## M1 逐次调用记录

- 路径为本 run 的 `agent_calls/<node>/attempt-<sequence>/`。序号通过独占创建目录分配，重启后继续分配；不依赖会被重置的返工计数，不覆盖历史尝试。
- `request.json` 保存 run/node/cycle、完整已发送输入、已渲染 info/instruct、输出 schema、模型与插件标识、实现文件指纹、规范化 offered 校验材料和作用域指纹。
- `result.json` 保存 provider 原始结构化返回与 Host 校验结果、状态 `validated/validation_failed/standin/error/interrupted`。这是模型调用阶段的结果，不能被当作整节点或整轮已经通过。
- request 在调用前落盘；result 在返回/失败时落盘。两者分别附 SHA-256，文件只读且只写一次。调用前写失败不得发请求；结果写失败不得继续消费输出。中断/写盘故障可能留下只有 request 的尝试，CLI 必须报告 incomplete，不能冒充完成。
- 仅记录明确的 model/plugin 标识和业务输入，不序列化 provider 配置对象、请求认证信息或进程环境。没有保存模型内部推理的要求。
- 重新打开记录可校验完整性并读取当时输入和结果；核验命令不重发模型请求、不重放写操作、不默认打印源码内容。输出中的 request/result 引用用于追踪；下游不得据其绕过业务校验。
- SHA-256 用于核验文件是否与所记录的指纹一致，不构成不可抵赖签名；拥有本机写权者能同时修改文件与指纹。跨用户可信审批需要后续鉴权契约。

## M2 人工确认经验

- 可选文件为 `<WORKSPACE_ROOT>/adjudication/agent_experiences.json`，顶层 `{version: 1, items: [...]}`。Host 只读；缺文件视为未配置，不影响普通执行。
- 每项要求 `id`、`status: approved`、`approved_by: human:<非空名称>`、`scope`、`source{path,sha256}`、`advice`。审批字段是单机流程元数据，不是强鉴权证明。
- `scope` 与当前记录请求的作用域逐值一致：环境标识、基线、事实 SHA-256、提示词 SHA-256、Schema SHA-256。事实指纹排除 run_id/cycle/rework_reasons，保留目标内容/文件指纹及其他事实；基线来自当前 run 的 view.json，缺失时不使用历史经验。
- source 必须是工作区 runs 下已有文件的相对路径，解析符号链接后仍在范围内，且 SHA-256 相同。路径逃逸、损坏、未确认、重复 ID、作用域不符的条目均拒用并留下诊断；整个目录格式无效时全部拒用。
- 只将筛选通过项的 id、advice、来源路径与指纹放入 `approved_experiences`。提示词明确它们是参考，当前事实和 Host 权威优先；不从历史输出推导审批或通过状态。
- 经验最多读取十项且 advice 每项最多四千字符；超量整体拒用而非截断，全部拒用原因写入本次记录与 warning。写回/自动晋升/经验管理 UI 不在本轮范围。

## 可判定验收

| 条款 | 验收 |
|---|---|
| C1 | 超过原差异条数、长 before/after、文件尾部修改与删除均进入模型输入；预算超限不发请求；原小输入保持语义 |
| M1 | 多次调用与重启不覆盖；记录能校验输入/输出；篡改和未完成记录能判错；失败、替身、取消和校验拒绝不记为 validated；写盘失败不被吞掉 |
| M2 | 相同作用域和源指纹的人工确认建议进入请求；错误版本、变化源文件、路径逃逸和缺审批均拒用；记录筛选诊断；模型结果不写经验目录 |

## 未决与验证边界

内网环境和历史夹具不可提供给云端。云端以独立测试目录、受控模型响应验收这些机制；真实模型质量、实际上下文窗口及完整真机闭环仍须内网测试。
多模型独立复核、用户鉴权和记忆管理 UI 属后续独立契约；不能用本轮机制声称它们已实现。
API 定义仍按受支持的 task/function 文本结构提取，不是完整 SystemVerilog 语义解析器；宏和条件编译的语义仍需已有仿真与人工验证。

## 使用与迁移

现有运行目录无需迁移；新调用自动分配新尝试，旧输出不被覆盖。没有经验目录时按普通节点执行。

```bash
cd loop
# 使用本轮独立测试，不需要内网仿真数据
LOOP_LLM_MODE=standin .venv/bin/python -m pytest tests/test_agent_context_memory.py -q
# 替换为真实 attempt 目录；只输出状态、身份和作用域摘要
.venv/bin/python -m host.agent_memory --verify /absolute/workspace/runs/RUN-ID/agent_calls/N6/attempt-000001
```

人工从已核验请求的 scope 复制完整作用域，填写已有来源的相对路径与 SHA-256，并在工作区 adjudication 下维护目录，例如：

```json
{
  "version": 1,
  "items": [{
    "id": "mask-lesson",
    "status": "approved",
    "approved_by": "human:reviewer",
    "scope": {
      "env_id": "<copy-from-request>",
      "baseline": "<copy-from-request>",
      "facts_sha256": "<copy-from-request>",
      "prompt_sha256": "<copy-from-request>",
      "schema_sha256": "<copy-from-request>"
    },
    "source": {"path": "runs/<historical-run>/agent_calls/N6/attempt-000001/result.json", "sha256": "<source-sha256>"},
    "advice": "结合当前 RTL 核对掩码，历史结论不能作为本轮通过凭据。"
  }]
}
```

这是保守的精确匹配；事实中的路径等值发生变化也会拒用，不做语义相似检索。不要将占位符模板当成已确认经验，也不要修改旧请求的 scope 来强行命中。
