# SPEC-06 · Agent 上下文、调用记录与经验契约

> 编号：**SPEC-06**（文件名不变；编号与修订记录见 [SPEC-REV-01](SPEC-REV-01-20261022.md)）。

> 运行干预见 [AGENT_WINDOW_SPEC.md](AGENT_WINDOW_SPEC.md)。新尝试携带本会话 human_interventions，仍执行原预算、记录及 Host 校验；不覆盖旧尝试，不自动晋升经验。

> 拟议扩展：[DSH 核执行后端草案](DSH_AGENT_RUNTIME_SPEC.md)。工具补读、候选编辑与执行审计尚未实现；现行能力仍按本文及 STATUS 判读。

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
- D1 将实际 SDK 调用提取到 `host/agent_backends`；请求机制仍持有预算、校验及封存调用。
  后端选择、固定 provider 快照和兼容 backend 指纹字段见
  [SPEC-08 §4.0](DSH_AGENT_RUNTIME_SPEC.md#40-d1-首片执行契约先于实现)。旧记录不回填。
- **节点语义**分别放在 `n6_facts.py`（N6 事实构造）、`n10_semantics.py`（N10 分类/对账辅助）、
  `n11_guard.py`（N11 证据守护辅助）；`model_steps.py` 保留节点入口（N3/N6/N8/N10/N11/N12）
  与兼容导出，TriggerFlow 拓扑与消费者不变。
- `request.json` 的 `implementation_sha256` 记录**机制模块**文件指纹；模块拆分导致指纹变化时如实记录，
  不用它替代语义对照（提示词/Schema/输入字段/产物）。
- 行为不变量不因拆分改变：每次请求新 agent；预算检查在请求前且不静默截断；
  取消/重发不消费旧结果；非法输出止于消费者之前。

## H1 返工交接快照（2026-10-24，先于实现）

N6 输入新增 `rework_handoff={version, run_id, issues}`，由 Host `agent_handoff` 唯一构造。
每项包含稳定 `issue_id`、来源节点、源快照指纹、源调用引用/核验状态、原始要求和可得的 case/basis。
顺序保持 N8 must_fix 在前、N11 rework_requests 在后；相同文字的不同条目不得合并。
原 rework_reasons 由同一投影生成，保持原文本与顺序，消费者仍为 N6；新增包计入原上下文预算并随请求封存。

ID 绑定 run、节点、相关意见快照、源调用身份和条目位置；重复构造不变，跨 run/源尝试/意见改变则变化。
ID 在本片表示一次意见出现，不表示跨轮的同一个长期问题；关联新旧问题、关闭与重新打开由 H2 定义。
引用存在时须指向本 run、对应节点、标准 attempt 目录的完整 request/result，禁止越界/符号链接；
复用 agent_memory 核验完整性，再检查身份。半件、篡改、身份错位在 N6 发模型请求前失败。
旧状态缺引用时标记 unrecorded，保留原输入但不补造来源；部分引用属于错误，不降级。

意见来自 Host 当前工作流状态的投影；N11 可能由 Host 追加身份失败请求，故核验源调用完整性
不等于宣称所有意见逐字来自模型 result。源快照指纹单独记录；不得标为已解决、已验收或新建业务台账。
N8 字符串缺少结构化 case/basis 时保持 null，不猜文件定位。历史封存不回填。
本片不解决旧状态意见过时问题，不改变返工计数/边、模型输出 Schema、业务判据或经验匹配。

后续按 [分期计划](../plans/2026-10-24-agent-collaboration-memory.md) 推进问题闭环与分层记忆。

## H2a 按问题回应与复核交接（2026-10-24）

H2 分两片实施。本片由 Host 构造 `rework_assignment={version:1, run_id,
target_sha256, issues}`；issues 复用 H1 的意见出现身份，target_sha256 对本次完整 targets
做规范化 SHA-256，绑定源码指纹、修订点与上下文。它不是施加后的文件版本。
N6 每轮从原始用例重建沙箱，不能继承上一轮修复结论；历史意见是否过时留给复核判断。

N6 新增 `issue_responses`，每个输入 issue_id 恰好一条，字段为：
`issue_id, target_sha256, disposition, explanation, edit_refs[{case, edit_index}]`。
disposition 仅 `addressed|blocked|not_applicable`，表示作者声称已处理/受阻/不适用，**都不关闭问题**。
explanation 必须非空；addressed 至少引用一个本次 revisions 内的 edit（索引从 0 起），
已知 issue.case 时引用须同 case；另外两种不得引用 edit，必须解释阻塞或不适用理由。
Host 拒绝缺项、重复/未知 ID、错版本、非法枚举/类型、空说明、重复/越界/错 case 引用；
blocked/not_applicable 是可复核意见，不自动终止流程或获得豁免，仍走既有 N8/N11 与人工闸门。
旧 rework_resolution 保留展示兼容，不能替代逐项回应；无意见允许省略/空 responses，非空未知回应拒绝。
Schema 与确定性校验同步，失败在 N6_apply 消费前发生并封存 validation_failed。

N8/N11 输入增加 `author_handoff`，只接收各自来源的问题与对应作者回应、引用的候选编辑，
保留 N6 来源身份、target_sha256 与整个候选 revisions/observation_points 的 candidate_sha256。
这些是候选指纹，不声称等于当前沙箱/执行身份；复核仍以现有 sandbox/identity/evidence 为准。
Host 从当前 n6_author 指向的**封存 request/result**重建包，核对本 run/N6/attempt、完整性、
validated/validation.ok，以及当前 author.data 与封存 accepted 一致；不得用可变状态冒充封存回应。
重启按引用重建，不扫描“最新”attempt，不采信取消、错误或 validation_failed 的结果。
无引用的旧状态标记 unavailable；带新回应却无引用、半引用/坏引用显式失败。
完整旧记录缺 assignment 且无新回应时标记 legacy；有新回应则拒绝降级。
standin 标记 standin，不产出可采信回应。回应及 edit_refs 拒绝额外字段，避免偷带作者关闭声明。
有 assignment 的记录核对版本/run/targets 指纹/H1 issues 一致并复用同一回应校验，坏形状拒绝。
新增输入纳入既有预算和封存，不裁剪；不回填历史记录，不新增台账/关闭权/返工计数。

H2a 只保证回应可追溯，不表示语义修复正确，不把 N8 pass/N11 intact 自动转成逐问题关闭。

## H2b 逐问题复核与版本失效（2026-10-24）

Host `agent_review` 唯一构造 `review_assignment`，模型 N8/N11 是各自来源问题的复核决策者，
`agent_memory` 仍是封存记录唯一写者，不新增问题台账。关闭是当前复核快照的意见状态，
不代替 case_state、编译/仿真证据、Host 身份校验或人工闸门。

- assignment 绑定 reviewer、N6 封存来源、target/candidate 指纹、全部本节点业务输入的
  `review_context_sha256`，逐项列出 issue_id、原要求、case 和 acceptance。
  验收条件为：原要求已满足或有当前证据证明不适用；N8 只能依据已提供的沙箱变更范围，
  N11 依据当前身份/证据链且 Host consistent=true。作者 addressed/blocked/not_applicable 均不算验收。
  指纹排除 assignment 自身及机制追加的 human_interventions/approved_experiences；它们仍随请求完整封存。
- N8/N11 输出 `issue_reviews[{issue_id, review_context_sha256, outcome:closed|open,
  rationale, evidence_refs, rework_index}]`，每个本节点 assigned ID 恰好一条；无 assigned 项时可省略/空。
  Host 拒绝漏项、重复/未知/跨节点 ID、错版本、额外字段、非法类型和空理由。
  evidence_refs 是本次输入中的 JSON Pointer，不读模型指定的文件路径。每项至少一个真实存在的非空值，
  允许 N8 的 sandbox_cases/revision_points/applied_edits，N11 的 identity/evidence/case_states；
  closed 还必须引用 sandbox_cases（N8）或 identity/evidence（N11）。引用能解析只证明材料存在，
  是否支持结论由复核模型负责，不能宣称 Host 自动证明语义修复正确。
- open 必须以从 0 起的 rework_index 关联本次 must_fix/rework_requests 中非空、可执行的返工要求；
  N11 已知 case 须一致。多个问题可关联同一返工条目。closed 的 index 必须 null。
  有 review_assignment 的新调用必须严格校验原始完整返工列表：N8 每项为非空字符串；
  N11 每项为含非空字符串 case/what/basis 的对象。禁止丢弃非法项、重排或类型强转后再解索引。
  无 assigned 问题时也校验新增要求。新调用及封存重建统一拒绝 pass/intact 携带返工要求、
  rework/broken 无返工要求及非法结论枚举；旧无 assignment 调用保持原兼容行为。
  有 open 时只允许 N8 rework/N11 broken；N8 pass 不得夹带 must_fix。N11 Host 身份不一致不得关闭任何问题。
  非法输出在台账更新、事件放行之前拒绝。drill 没有真实返工预算，N8 rework 直接发 N8_ESCALATE，
  不发 N8_PASS 或形成无计数回环；不新增真实台账计数，standin 不产生可信关闭。
- N6 回边从当前 N6 及 N8/N11 **明确引用的封存记录**重建交接。旧问题 ID/初始来源保持，
  open 的关联返工条目存为 follow_up，不复制成新问题；没有关联的新增要求仍按 H1 新建意见身份。
  已携带的 follow_up 身份再次出现在旧节点状态时不重复新建。复核包必须与对应 N6 重建包一致，
  不能只保留正确 author_source 却替换候选/目标/问题材料。
  初始意见 ID 因此可跨轮沿用；不做语义合并，未关联的相似文字可能仍是不同问题。
- `rework_handoff.lifecycle` 记录 previous_outcome、open/reopened 状态及复核来源。
  每次新 N6 都是新候选生成边界，之前 closed 一律 reopened（即使源码目标指纹未变），原关闭记录不改。
  目标/沙箱/证据变化使复核快照指纹改变，旧结论不能提交到新快照。
  缺复核/旧格式/替身标记 unreviewed；复核指向别的 N6 封存来源标记 stale_review，旧问题继续 open。
  坏校验和、半引用、失败/取消记录、状态与 accepted 不同、assignment 与保存输入不符则显式失败，不能降级。
  重建不扫描目录最新尝试，不重复执行业务效果；输入全量计预算，超限明确拒绝，不丢弃历史问题。
  N6 替身输出不能抹掉其封存请求中已分配的问题。此时仅从核验后的请求交接/targets/assignment
  恢复本节点历史问题，保留原 ID、来源及 follow_up，标为 unreviewed/open；不携带替身回应、候选指纹或关闭权。
  有 assignment 的替身请求仍须核验 run/targets/交接一致性；无 assignment 的旧替身不虚构历史问题。

范围边界：保守的逐候选重验会增加上下文和复核成本；不做局部依赖失效或跨 run 问题合并。
旧记录不回填，不从旧 pass/intact 反推关闭。工作记忆摘要/指令生命周期/跨运行经验仍按后续 M1/M2/M3 推进。

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

## 云端实施补充（2026-10-26，新增优化尚未实现）

[REV13](SPEC-REV-13-20261026.md) 明确计划 M1 工作记忆、M2 指令生命周期、M3 经验分层的新增契约，
并与本文件既有“M1 逐次调用记录 / M2 人工确认经验”区分。现有基本能力与 H1/H2a/H2b 保留，
不能因基本记录/经验筛选已存在而把后续优化标完成；实施落点、恢复/兼容及云端测试见
[详细设计](../plans/2026-10-26-cloud-dsh-memory-design.md)。

## 执行器对齐补丁（2026-10-28，未实现）

[REV14](SPEC-REV-14-20261028.md) D2：会话内压缩保留给 DSH，但**压缩事实由 Host 从 session log 落账**
（`compaction/summary` + `time`）；事件流与投影当前没有该事实（P7 实测），不得声称"投影里有压缩行"。
覆盖责任收缩为"Host 输入包 + 提交回传"，业务结论不得依赖未提供材料（本文件 C1 的既有纪律不变）。
A4：上下文包按 REV13 §6 的 `context_manifest_ref` / source map / `input_ref` 落地，不自造第二套。
