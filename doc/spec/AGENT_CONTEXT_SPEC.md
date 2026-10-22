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
- N8 覆盖分配（F16）：每个沙箱用例文件都必须出现在输入里，且**覆盖本轮 edits 触及的行**。
  - 单文件超过 6000 字符（既有规则）⇒ 必须用「源代码与沙箱的实际差异」变更片段；片段上下文取变更点前后各 6 行（`N8_REGION_CONTEXT_LINES`，行号以 after 坐标）；缺源文件或变更无法定位时不得猜测复核范围，显式失败。
  - 其余文件默认全文；当全部全文的序列化大小超过 N8 分片预算（`N8_SANDBOX_BUDGET_BYTES`，默认 60000 bytes，约占默认总预算一半，留出 contract/台账余量；按 `AM.encoded` 紧凑序列化计，与预算检查同一实现）时，按**文件名的确定性顺序**把放不下的文件也降级为变更片段。
  - **按真实序列化成本选择表示（R4，2026-10-22）**：每件每种表示的成本是该件条目**实际紧凑序列化**的字节数
    （`AM.encoded`，含 `coverage`/`changed_regions`/键名与标点），**不得**用近似字节数或「片段一定更小」的假定。
    可行成本取 `min(全文成本, 片段成本)`；强制片段的大文件只有片段成本。选择按**文件名的确定性顺序**，
    先预留后续件的可行成本，再决定当前件是否用全文；只有**全部候选件的最小可行成本之和**超过分片预算时
    才显式拒绝。相同输入必须得到相同字节与相同覆盖汇总；`coverage.complete` 与
    `coverage_summary.full_files/region_files` 必须与实际发送内容一致，不得虚报。
  - 降级**不得丢文件、不得只发部分行而不标注**；每件必须带 `coverage{mode: full_file|changed_regions, complete, scope, regions}`，请求另带 `coverage_summary{used_bytes, budget_bytes, full_files, region_files}`。
  - 片段模式下模型只对已提供区域负责；不能用“覆盖了变更”冒充全文复核。
  - `coverage.complete` 语义：`true` 仅表示**该件的全部变更区域都已提供**（`full_file` 表示全文；
    `changed_regions` 表示所有变更组均已包含，只是省略了无关上下文）。它不是「已做全文复核」的证明；
    存在未提供的变更组时不得置 `true`。
  - 沙箱中没有任何 `*.sv` 用例，或 `applied_cases` 非空却找不到对应文件 ⇒ **显式失败**，
    不得以「复核 0 件」通过。
- 所有模型请求以完整序列化 input/info/instruct/schema 的 UTF-8 大小检查预算。默认上限 `120000` bytes；超过上限在模型调用前显式失败，记录预算/失败，不裁剪、丢用例或静默抽样。这是应用输入预算，不承诺等于提供方 token 上限。
- **预算计量的唯一 owner 是 Host（R5，2026-10-22）**：准入检查与对外展示使用**同一次测量**——
  `AM` 的紧凑序列化总量，构成包含外层键名与标点。API 下发该总量、各计费字段字节与**显式序列化开销**，
  且满足 `分项之和 + 开销 == 总量`；窗口只消费这些数字，不得另写求和/占比判据（红线 8）。
  `offered`/`scope` 等**未发送**给模型的材料若要展示，必须单列为「记录存储大小」，不计入预算；
  上限未知时显示未知，不给假比例；token 仍为 `unknown`。
- 输入缺失/校验错误继续走既有失败收敛路径；drill 替身保留明确标注，不能被记录为 live 成功。

## 实现结构（F06，2026-10-21）

- **请求机制**（`_request_contract` / `_ask` / 单次 attempt / `run_model_node` 的控制包装）唯一放在
  `workflows/chunks/model_request.py`；Host 校验 `_validate` 仍是**唯一实现**，由机制层以参数注入，
  机制层不得复制节点判据。
- **节点语义**分别放在 `n6_facts.py`（N6 事实构造）、`n10_semantics.py`（N10 分类/对账辅助）、
  `n11_guard.py`（N11 证据守护辅助）；`model_steps.py` 保留节点入口（N3/N6/N8/N10/N11/N12）
  与兼容导出，TriggerFlow 拓扑与消费者不变。
- `request.json` 的 `implementation_sha256` 记录**机制模块**文件指纹；模块拆分导致指纹变化时如实记录，
  不用它替代语义对照（提示词/Schema/输入字段/产物）。
- 行为不变量不因拆分改变：每次请求新 agent；预算检查在请求前且不静默截断；
  取消/重发不消费旧结果；非法输出止于消费者之前。

## M1 逐次调用记录

- 路径为本 run 的 `agent_calls/<node>/attempt-<sequence>/`。序号通过独占创建目录分配，重启后继续分配；不依赖会被重置的返工计数，不覆盖历史尝试。
- `request.json` 保存 run/node/cycle、完整已发送输入、已渲染 info/instruct、输出 schema、模型与插件标识、实现文件指纹、规范化 offered 校验材料和作用域指纹。
- `result.json` 保存 provider 原始结构化返回与 Host 校验结果、状态 `validated/validation_failed/standin/error/interrupted`。这是模型调用阶段的结果，不能被当作整节点或整轮已经通过。
- request 在调用前落盘；result 在返回/失败时落盘。两者分别附 SHA-256，文件只读且只写一次。调用前写失败不得发请求；结果写失败不得继续消费输出。中断/写盘故障可能留下只有 request 的尝试，CLI 必须报告 incomplete，不能冒充完成。
- 仅记录明确的 model/plugin 标识和业务输入，不序列化 provider 配置对象、请求认证信息或进程环境。没有保存模型内部推理的要求。
- 重新打开记录可校验完整性并读取当时输入和结果；核验命令不重发模型请求、不重放写操作、不默认打印源码内容。输出中的 request/result 引用用于追踪；下游不得据其绕过业务校验。
- SHA-256 用于核验文件是否与所记录的指纹一致，不构成不可抵赖签名；拥有本机写权者能同时修改文件与指纹。跨用户可信审批需要后续鉴权契约。

## 封存与恢复（F08）

- 一次调用尝试的记录由 `request.json` + `.sha256`（以及完成时的 `result.json` + `.sha256`）构成；
  写作者唯一为 Host `agent_memory`，读者不得修改或回填。
- 公开诊断 `record_state(path)` 只读返回：`absent`（无文件）/ `incomplete`（数据在、校验缺，或 result 缺）/
  `corrupt`（校验不匹配或 JSON 不可解析）/ `committed`（内容与校验一致）。
- 消费规则：`incomplete` 的尝试**不得**被当作有效请求/结果消费；读取视图把该尝试标为 `incomplete`，
  其它 `committed` 尝试照常可读。`corrupt`（校验不匹配/JSON 坏）与路径越界、符号链接、身份不匹配一样
  **显式失败**（安全信号，不得静默降级成普通状态）。
- 进程终止（含 `SIGKILL`）留下的半写记录由上述状态诊断；恢复只读诊断**不自动重发**模型请求，
  新尝试按序号继续分配、不覆盖已发布记录。
- **原子发布（R1，2026-10-22）**：数据与校验和都不得在最终文件名上边写边暴露。发布流程固定为：
  ① 在**同一目录**写私有临时件（名字不以 `request.json`/`result.json`/`.sha256` 结尾，不参与读取扫描）；
  ② `fsync` 临时件内容；③ 以**不可覆盖**的原子操作（同文件系统 `os.link`/等价语义）发布到最终名，
  再删除临时件；④ 同步目录项。发布顺序固定为 **数据 → 校验和**。任一时刻被终止，最终名下只可能
  「不存在」或「完整」，**不会出现空的或半截的 `.sha256`**。
  - `seal_record` 仍是唯一发布点；竞争写同一编号只有一个成功，失败者不得覆盖已发布的件。
  - 进程终止保证；断电/掉电下的持久性不在本契约声称范围（需另测）。
  - 半件（`incomplete`）只报告状态、不消费；已有 `committed` 尝试照常可读；真正的 `corrupt`
    （内容与校验不符/JSON 坏，无法由进程终止解释）仍显式失败，不得靠「一律当 incomplete」掩盖篡改。
- 公开封存接口 `seal_record(path, value)`；跨模块不得直接调用私有 `_sealed`。

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
| C1 | 超过原差异条数、长 before/after、文件尾部修改与删除均进入模型输入；预算超限不发请求；原小输入保持语义；N8 超分片预算时按确定性顺序降级且每件带 `coverage`（无静默抽样/丢文件） |
| M1 | 多次调用与重启不覆盖；记录能校验输入/输出；篡改和未完成记录能判错；失败、替身、取消和校验拒绝不记为 validated；写盘失败不被吞掉 |
| M2 | 相同作用域和源指纹的人工确认建议进入请求；错误版本、变化源文件、路径逃逸和缺审批均拒用；记录筛选诊断；模型结果不写经验目录 |

## 未决与验证边界

内网环境和历史夹具不可提供给云端。云端以独立测试目录、受控模型响应验收这些机制；真实模型质量、实际上下文窗口及完整真机闭环仍须内网测试。
多模型独立复核、用户鉴权和记忆管理 UI 属后续独立契约；不能用本轮机制声称它们已实现。
API 定义仍按受支持的 task/function 文本结构提取，不是完整 SystemVerilog 语义解析器；宏和条件编译的语义仍需已有仿真与人工验证。

**未决（R6，2026-10-22）**：N8 的复核对象当前取 `sandbox/TESTLIB/*.sv` 扫描结果，并按 `applied_cases`
校验**缺件**；沙箱中**多于** `applied_cases` 的 `.sv`（例如上一轮残留）不会被排除，且会被标
`coverage.complete=true`。确定性探针已在纯函数层证明该机制；但**当前拓扑不可产生该输入**（N5 只执行一次、
`n6_author` 每轮强制覆盖全部目标、`n6_apply` 每轮重写同一目标集，跨轮使用新 `run_dir`），
故本轮**不作为可复现缺陷立项**，也不改行为。若将来出现第二个沙箱写入者、回边改为可缩水目标集，
或同 `run_id` 复用目录，则必须改契约：沙箱对象以 `applied_cases` 为白名单、多余件显式失败、
残留件不得标 `complete=true`，并补对应红灯。登记见 [STATUS §40](../STATUS.md#40-r-门阶段-b-缺陷收口r1-r6-2026-10-22)。

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
