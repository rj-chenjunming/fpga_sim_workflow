# 后续优化与特征重构评估

> 本轮是否修复：**否**。本轮整理现状、复核缺口和制定后续切片，没有修改运行代码或放宽现有规格。
> 评估对象：HEAD `5f6cdb2` 加工作区已有 UI 会话、Agent 记忆、S0-a、Agent 工作窗口修改；不能把 HEAD 当作包含这些能力的提交。
> 方法：规格对照、代码阅读和临时目录受控探针。同一执行者复核，不是独立终验。实测与限制见 [STATUS §11](../STATUS.md#11-后续优化与特征重构整理2026-10-21)。

## 判断与范围

建议先修复基线身份和能力展示，再建立可重复的验证基础，随后按功能边界重构。S0-b 和 Agent 持久暂停属于新增行为，不能夹在“代码整理”中上线。

本评估遵循 [AGENTS.md §2.1](../../AGENTS.md)：规格 → 计划 → 特征基线 → 缺陷红灯 → 局部提取 → 行为变更 → 验证与冻结证据。具体切片、owner、验收与回退条件见 [实施路线](../plans/2026-10-21-specdd-followups.md)。该路线中的新能力是建议目标，实施时先评审对应规格；本报告不自动替代现行契约。

优先级含义：P0 是真实运行正确性前置；P1 是下一批优化；P2 在依赖就绪后实施；P3 仅保留候选。性质分别标为 **已确证缺陷、已知能力缺口、待测风险、保持行为重构、产品增强**。源码显示潜在代价不等于已发生性能事故。

## 排序与依据

| ID / 优先级 | 性质与问题 | 定位与复核结论 | 用户收益 / 下一步 |
|---|---|---|---|
| F01 · P0 | 已确证缺陷：基线有效性及全链身份不一致 | [config_api.py:61](../../loop/services/config_api.py#L61) 只要 manifest 可解析即 `valid=True`；[api.py:177](../../loop/services/api.py#L177) 和 [main_flow.py:442](../../loop/workflows/main_flow.py#L442) 启动前没有执行完整基线校验；[host_steps.py:310](../../loop/workflows/chunks/host_steps.py#L310) real N2 固定使用 v0。受控探针确认空 manifest 被接受、非默认输入仍向 N2 工具传 v0。N0 初始化也未传入选中 manifest；[gate.py:115](../../kb/tools/gate.py#L115) 默认记录 N/A。 | 避免界面所选基线与实际差异来源不符。先统一 Host 准入，再沿 N0/N1/N2/闸门材料验证同一身份。没有在内网执行错误基线的完整闭环，不推断历史报告已受影响。 |
| F02 · P1 | 已确证缺陷：能力说明与实现漂移 | [agent_view.py:47](../../loop/services/agent_view.py#L47)、[agent_view.py:196](../../loop/services/agent_view.py#L196) 仍把 guardian 标为未实现；[model_steps.py:1732](../../loop/workflows/chunks/model_steps.py#L1732) 已实现 N11 成链/返工判断。探针复现旧提示；[test_agent_view.py:76](../../loop/tests/test_agent_view.py#L76) 还固定了旧提示。[WEB_UI_SPEC §3.3](../spec/WEB_UI_SPEC.md) 的 real 提示也沿用旧缺陷状态。 | 区分“已实现”“当前可用”“本次模式”“验证范围”。旧错误提示测试应在修正规格后有意更新，不能为了特征兼容永久保留错误。 |
| F03 · P1 | 已知验证缺口与已确证工具缺陷：云端验证混入内网依赖 | [conftest.py](../../loop/tests/conftest.py) 仍使用进程级路径和共享槽文件；[accept_v1_run.sh:33](../../loop/spikes/accept_v1_run.sh#L33) 清理共享 state 与 drill 目录。[check_doc_links.py:45](check_doc_links.py#L45) 把本仓工具/Schema 列为环境资产；探针确认本地存在的 kb_lib.py 在无环境根时被判缺失。已有完整测试限制见 STATUS。 | 建立纯软件、受控插件、真实环境分层入口；隔离测试资产；文档检查区分仓库断链和外部缺件。保留完整内网门，不把 skip 当通过。 |
| F04 · P1（分阶段） | 已知能力缺口：S0-b 与执行准出尚未闭合 | [S0 规格 §3](../spec/S0_ENVIRONMENT_SPEC.md)、[s0.py:248](../../loop/host/s0.py#L248)：ready 始终为 false；接口核对、top.sv 登记/适配、三库冒烟及新版执行入口未接入。 | 先定义软件可验证的输入/产物/驱动协议，再接内网驱动与准出消费者。S0-a 成功继续不能解锁新版执行。 |
| F05 · P1 | 保持行为重构：UI 功能与会话协调集中 | [app.js](../../loop/web/app.js) 同时承担配置、运行、阶段、闸门、目录选择和请求协调；已有 [s0.js](../../loop/web/s0.js)、[agent-window.js](../../loop/web/agent-window.js) 提供局部边界。 | 以配置、运行监控、闸门决策为切片提取视图；会话身份、草稿和提交互斥保持原行为。先做最小局部提取，不以引入框架为目标。 |
| F06 · P1 | 保持行为重构：模型语义节点、请求机制与事实构造混合 | [model_steps.py](../../loop/workflows/chunks/model_steps.py) 混合请求契约/验证、N6 上下文、各节点和业务产物；请求已提取单次 attempt，但尚未按功能解耦。 | 先提取请求执行与校验，再按 N6 用例修订、N10 分类、N11 守护分别拆；保持节点入口、输入顺序、提示词/Schema 指纹、台账写权和消费者。 |
| F07 · P2（先测量） | 待测性能风险：Agent 历史读取与控制共用服务资源 | [agent_control.py:78](../../loop/host/agent_control.py#L78) 每次读取所有尝试及控制历史；[api.py:264](../../loop/services/api.py#L264) 在 async 路由同步读取/核验文件和全事件流；[agent-window.js:176](../../loop/web/agent-window.js#L176) 周期轮询。已确认读取方式，未测得生产延迟。 | 先测历史增长时的读取量及控制响应，再考虑分页、增量游标、静态尝试按需读取。缓存只能是可丢弃投影，不能取代指纹或权威文件；活跃控制状态仍由原事件循环管理。 |
| F08 · P2 | 待测可靠性风险：记录发布与读取边界 | [agent_memory.py:113](../../loop/host/agent_memory.py#L113) 的 `_sealed` 顺序写数据和校验文件；[agent_control.py:19](../../loop/host/agent_control.py#L19) 直接复用私有函数，读取将缺件视为错误。现行实现失败关闭；尚未用进程杀断验证两文件之间的恢复体验。 | 故障注入后定义 incomplete、corrupt、committed 的区别，再提取公开的封存记录接口。保持两个业务 owner；不补写旧证据、不自动重试模型。 |
| F09 · P2 | 已知能力缺口：Agent 暂停不跨进程持久化 | [AGENT_WINDOW_SPEC](../spec/AGENT_WINDOW_SPEC.md) 明确进程级暂停和重启只读；[agent_control.py:18](../../loop/host/agent_control.py#L18) `_ACTIVE` 是进程注册表。 | 若要接近多 Agent 工作台体验，先定义 durable 请求边界与恢复握手。只恢复明确的续跑意图，新请求与旧远端计算分开标识，不能承诺远端恰好执行一次。 |
| F10 · P2 | 产品增强：上下文预算与经验可解释性 | [agent_memory.py](../../loop/host/agent_memory.py) 用序列化字节预算拒绝超限，经验需人工确认并精确匹配事实/提示词/Schema/来源。[AGENT_CONTEXT_SPEC](../spec/AGENT_CONTEXT_SPEC.md) 已禁止静默截断。 | 先展示预算组成、经验采用/拒绝原因与来源；再按 provider 能力增加 token 预检。超限分块是独立语义契约，不能悄悄摘要或放松经验匹配。 |
| F11 · P2 | 产品增强：工作窗口的观察效率 | [agent-window.js:65](../../loop/web/agent-window.js#L65) 主要展示 JSON；事件与控制记录分组、仅展示尾部；[index.html](../../loop/web/index.html) 为模态窗口。现有会话隔离是保留基线。 | 增加状态摘要、尝试输入/结果差异、指令回执关联、事件筛选/分页；再评估可固定侧栏与双窗口。时间相同的不同事件源不伪装成因果顺序，不展示隐藏推理。 |
| F12 · P3 | 新架构候选：真正并行 Agent 与任务委派 | 当前 [main_flow.py](../../loop/workflows/main_flow.py)、[主流程规格](../spec/LOOP_ORCHESTRATION_SPEC.md) 是稳定图和单环境执行槽。可进入 Agent 窗口不等于并行调度。 | 只有出现具体并行用例才立项：先处理纯只读分析的取消传播/结果汇合/唯一消费者。共享环境写入、仿真单槽及人类闸门不能因并行而弱化；当前不建议优先实施。 |

## 不应重新包装为待修缺陷的已完成事项

- UI 运行/闸门旧响应隔离、草稿身份及重复提交保护已实现，应作为重构特征基线。
- Agent 每次新请求、完整输入预算、调用留痕、经验来源筛选已实现；无需先引入向量库或长期聊天状态。
- Agent 窗口已可观察并干预请求；暂停/恢复/终止、取消超时及陈旧控制保护已有测试。待完善的是可观察性、扩展性与持久恢复。
- S0-a 已实现完整派生和基线零写；应补齐 S0-b，不能把已有能力重写一遍。
- 闸门先校验再签署、失败收敛、单槽队列唤醒已有实现。历史审计结论必须复核后才可登记为当前缺陷。

## 未决与外部边界

- 基线完整性以现行环境/业务契约及 kb 唯一解析器为准；UI 规格的“七件套”需要对照权威定义列明，不能另写一套近似判据。
- S0-b 三库驱动协议、真实 warning 评估及 TB 逐 hunk 适配需在内网验证。用户已明确无法提供内网仓库，后续交付可为协议/适配器与内网验收包，不要求外传资产。
- F07 无生产规模测量、F08 无崩溃注入证据、F09 无 durable 恢复实现；这些不能写成已复现事故或已提供能力。
- 本轮只读探针没有调用真实 LLM、kb 写工具或仿真器。四道门没有重新执行；后续实现不能以本文代替验收。
