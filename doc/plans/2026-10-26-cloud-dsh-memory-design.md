# 云端 DSH 内核与 Agent 记忆优化详细设计

日期/版本：2026-10-26 / v1。状态：**设计就绪，未实施**。规范为 [REV13](../spec/SPEC-REV-13-20261026.md)；继承 [DSH 总计划](2026-10-23-dsh-agent-runtime.md) 与 [协作/记忆计划](2026-10-24-agent-collaboration-memory.md)。本轮 owner 为本聊天设计执行者；后续代码按切片指定一个实现 owner，不声称独立验证。

## 1 云端可交付范围与入口检查

云端是本设计的开发执行端。它可完成 C1 机制开发与 WM/IL/EXP；当前实例具备模型授权及强制隔离时可继续 C2 的真实 DSH/工具验证。内网业务 E 另行验收。当前聊天运行在桌面，本轮不能执行原云端；原任务读取 403 仅为访问限制，不表示云端不能开发。

**不能据旧环境或本机推断云端现状。** 云端开始执行时产生一份当前 observed capability manifest，先执行无模型、无业务写入的探测。

| 检查 | 读取/观察 | 放行条件 / 缺失时继续工作 |
|---|---|---|
| 实例身份和配置版本 | 当前环境状态工具；若不可用则标记观察缺口 | 不复用已删除实例 ID；C1 可继续，真实准入需当前证据 |
| 代码和依赖 | clean Git HEAD、requirements、Node/DSH manifest/锁文件 | 固定本次版本；旧 npm 安装记录不能替代 |
| 网络与身份 | 当前网络策略、代理/CA、被选身份的 readiness | 不 dump env/秘密；无模型授权先完成受控测试 |
| 运行时接口 | 锁定版本的 SDK 类型/文档、无模型 initialize/shutdown | 记录字段映射；握手不计业务完成 |
| 文件/进程/网络强制隔离 | 实际容器或等价隔离的越界与后代清理探针 | 缺失时不启用带工具 DSH；不改成宿主裸 shell |
| 公共测试工程 | 软件仓内单独的合成快照及其权限标记 | 不冒充内网工程/历史夹具；支持 C1/C2 |
| 内网业务资产 | 环境注册表解析路径、已授权工程/工具 | 缺失只阻塞 E，不阻塞软件和记忆切片 |

探测产物按 observed/declared 区分，记录时间、实例/代码/运行时/协议/profile/权限策略指纹及 supported/ready/unknown 说明。观测结果不能带秘密值或原始认证错误全文。

云端代理、CA、注入身份沿用受管配置。若有 OIC manifest，只读取非秘密的身份选择元数据，按目标 alias 正常使用 SDK；不读取凭据正文、替换注入头、复用旧聊天 Token 或触发交互式登录。环境配置变更遵循该环境自己的审核流程，不由应用代码暗中修改。

原公开发行版探针见 STATUS §57。目标云端可以使用该锁定版本复现，也可显式选择另一版本；后者必须重新生成协议映射与测试证据，不能直接声称兼容。

## 2 实施切片和依赖

| 顺序 | 范围 / 实现落点 | 前置与先失败测试 | 退出证据 |
|---|---|---|---|
| P0 | 当前云端探测、版本/策略 manifest | 版本变化、旧 readiness、缺权限观察 | 当前事实明确；未知项及阻塞层级可定位 |
| P1 | WM：新 host/agent_working_memory.py；model_request 接线 | 已选来源/孤儿目录/资源变更/问题完整性 | 确定性重建、强制覆盖、预算与旧 H2b 回归 |
| P2 | IL：agent_control + 现有 API/窗口 + model_request | scope 到期、撤销竞态、原子替代、重启 | 有效集和消费者一致，旧 /control 保持行为 |
| P3 | EXP：agent_memory 经验筛选及迁移校验 | v1 特征、v2 依赖变更/通用建议/坏源/超预算 | 审计指纹与适用性分离，审批与诊断完整 |
| P4 | D2：新 agent_backends/dsh.py、dsh_protocol.py、dsh_process.py | 坏帧/重复终态/断连/模型拒绝/停止未知 | C1 机制通过；不足时保持 BackendUnavailable |
| P5 | D3：原 control/memory 与 DSH 接线 | 带工具后代存活、取消迟到结果、半写审计 | 真实停止、结果资格和工具审计可证明 |
| P6 | C2：真实 DSH + 模型 + N3 公开工程只读探针 | 越界读取、额外工具、压缩/预算边界 | 实际内核/工具证据，不是受控替身 |
| P7 | D4：N6 candidate 导入及公平对照，后续 E | 非法文件/链接/源漂移/校验后换件 | 权限通过，再按原 SPEC-08 评价业务收益 |

WM/IL/EXP 不依赖 DSH 原生接通，可以沿 Agently 现有路径先交付，避免再次因等待 DSH 而停在计划。实现顺序可按 owner 能力调整，但同一文件同一时刻只允许一个 writer，不暗示需要并行 Agent。

每片先跑既有特征，再新增红灯，最后做局部实现和受影响回归。不要在 P4 同时重写节点语义、记忆、UI 或 kb；每片可定位、可回退，状态统一写 STATUS。

## 3 模块和单一写权

| 模块 | 负责 | 明确不负责 |
|---|---|---|
| agent_working_memory | 核验选中源、映射 typed 条目、构造当前节点热输入/source map | 关闭问题、更新业务台账、语义总结、选择最新目录 |
| agent_control | 指令事件、scope 投影、代次、接受资格、停止后重发 | 业务回滚、判断自然语言矛盾、模型调用审计写盘 |
| agent_memory | 原子封存、请求审计、EXP 来源/适用性筛选 | 人工审批、自动晋升、另一套恢复调度 |
| model_request | 组合事实/WM/指令/经验、检查预算、调用原校验与发布结果 | 复制 N6/N8/N11 业务判据 |
| dsh | 后端协议编排、候选返回及脱敏 metadata | 接受业务写盘权限或决定下一节点 |
| dsh_protocol | 纯帧编解码、版本映射、关联与终态选择 | 启进程、猜文本成功或修补坏 JSON |
| dsh_process | attempt 资源创建/关闭、受管范围停止确认 | 保存业务决定、全局 DSH 会话复用 |
| 原 model_steps / N6_apply | 节点输入、原 _validate、唯一候选应用 | 重新实现协议、经验筛选或取消状态机 |

上述新模块为实施落点，当前不得提前创建只会假报成功的空壳。仍由现有 TriggerFlow 拓扑消费结果。Agently 新 API/资源抽象是否存在必须对安装版本核验；本设计不要求迁移框架或导入未经证实的新运行时 API。

## 4 DSH 运行实例和协议映射

### 4.1 资源布局

每次 attempt 使用独立执行资源，Host 保留其描述与身份：

```text
Host 管理的 run/agent_calls/NODE/attempt-NNNNNN/
  request.json + checksum           # 原记录，不回填
  result.json + checksum            # 原结果状态
  execution-request.json + checksum # 新版本非秘密执行描述
  execution-events-*.json + checksum
  artifact-manifest.json + checksum # 只保存获准产物清单/哈希
独立隔离资源内部（不等于宿主 run 目录）
  input/      只读快照
  scratch/    私有临时文件
  candidate/  N6 限定写入
  dsh-home/   私有、不与用户会话共享
  agents/     获准规则/角色的固定副本
```

审计目录不挂给 DSH；DSH 只提交证据数据，由 agent_memory 在后端返回/流事件被验证后发布。分块事件有 sequence、前块指纹和请求身份；结束清单包含连续性摘要。半件不得消费，缺口或冲突不能补猜。

N3 不挂 candidate；默认没有 shell/edit/git/仿真权限。若基础 profile 自动含这些能力，必须经固定 patch 禁用并用越权尝试验证，不能只对模型说“不要使用”。

### 4.2 协议边界

| Host 逻辑操作 | 已知 DSH 映射 / 实施要求 |
|---|---|
| probe | 读取公开 package/锁/协议/profile 指纹；initialize + 无业务调用关闭，检查当前实例 |
| start | 依据锁定协议建立独立 session，提交 session/prompt；绑定返回 messageId，不把入队当完成 |
| observe | 按锁定类型订阅 session/turn 事件，维护 request/session/turn/sequence 关联；缺序列能力则由连接边界明确诊断 |
| result | 从被确认的目标 turn 完成事件及结构化结果选取候选；若版本没有稳定结果获取接口，不启用业务 |
| cancel/close | 原版本只有进程级停止时关闭该 attempt 进程/容器；等待后代静止，未知则阻断 |

不在本设计编造 session 创建方法名、事件字段或 JSON Schema 参数名。P0 读取目标版本类型后，把原始类型/方法/字段与本表逐项映射，加入协议录制测试和指纹；这是一项具体的前置交付，而不是把猜测写进后端。

后端只向 Host 提供受类型约束的执行事件；Host observer 校验身份/顺序并调用 agent_memory 发布。observer 不是业务写盘句柄，不允许后端指定审计路径或直接 seal_record。资源/handle 记录失败时不得派发模型，须清理本轮资源；清理未知按 execution_unknown 处理。

编码器不把用户消息插进 shell 字符串。进程入口使用参数数组、绝对可执行路径和限定 cwd；未知 profile、版本或命令行失败直接返回固定诊断。stdout 协议帧和 stderr 诊断分离，所有缓冲有上限，预算超限终止并证明停止。

### 4.3 接受和清理的交接

1. control 固定当前 generation、有效指令指纹，Host 固定事实和必要上下文。
2. 探测当前 capabilities；agent_memory 先封存请求与 attempt intent，再按 execution grant 创建带该 intent 标签的资源。Host 封存实际 handle 后才能提交 prompt；中断后可按精确 owner/intent 标签识别本轮孤儿资源，不扫描或清理别的任务。
3. 启动 DSH，核验 initialize，创建独立 session；只派发一次逻辑 prompt。RPC 超时不默认重发可能已入队的请求。
4. 校验每个事件关联、工具效果及边界；接受完整候选前不改业务文件。
5. 原 Host 校验输出，control 在发布给消费者前确认 generation/有效指令/事实版本仍有效。
6. 由 agent_memory 封存结果及审计。写失败显式失败，不能先用结果再补记录。
7. 确认 DSH 和获准后代停止，固化 candidate 后才允许 Host 导入；资源关闭不删除审计。

取消时先撤销资格，即使请求之后正常返回也不能消费。不能停止的工具不得作为已暂停展示；进程未知也不能切后端重发。容器/沙箱 ID 在模型调用前已留证，服务中断后可只读确认残留执行；不恢复旧隐式上下文。

## 5 WM 构造算法与落点

输入为 RunCtx 的非秘密身份、当前节点事实、明确的上游 request/result 引用、已选 H2b 投影和当前有效指令；没有全局扫描或通用聊天历史。

算法：

1. 从当前节点输入/业务状态取得源引用集合；拒绝跨 run、路径/链接逃逸、半引用或损坏。
2. 用已有核验函数验证 request/result、身份、Host accepted 状态与资源版本。standin/legacy 显式标记，不推断可信结论。
3. 按字段注册表映射成 observed_fact / human_decision / model_proposal / open_issue / constraint；模型判断仍为 proposal。
4. 复用 H2b 的 for_author/for_reviewer 输出，不复制关闭/重开算法，不更改 issue_id。
5. 按节点消费者的稳定顺序组装必要条目，保留来源短键和失效诊断。正文已在本次 input 的条目使用直接 input_ref，不再复制大对象；禁止引用 WM 自身或外部未读取材料。相同来源/版本应产生相同序列化结果。
6. 无补读工具时把必需支持正文装入输入；有工具则声明授权引用及 required coverage。未读取不算已供给。
7. 原 AM.measure_budget/check_budget 检查全部实际发送内容；必要条目超限直接失败。
8. working_memory 与 source map 随 request 保存；恢复重新投影，不重放效果。

首次接线放在 model_request.run_attempt 的“已选来源 → 固定有效指令 → WM → 经验 → 预算 → 封存/调用”边界。具体事实源仍由节点构造，不能让请求机制自己读取不属于该节点的业务资料。

| 节点 | WM 必需类型/材料 | 现有输出/消费者保持 |
|---|---|---|
| N3 | 当前 diff/条目、基线和文档事实、有关人工约束 | 原摘要/分组/风险 → G1 |
| N6 | 所有 targets、当前依据/观测印记、未解决问题、有关建议与约束 | 原 edits/observations/issue_responses → N6_apply/复核 |
| N8 | 本次作者封存回应、实际沙箱及变更范围、review_assignment | 原 verdict/must_fix/issue_reviews → 原回边/放行 |
| N11 | Host 身份表、当前证据、已选问题及作者回应 | 原 chain/rework_requests/issue_reviews → 原消费者 |
| N10/N12 | 原证据分类事实/Host 计数/闸门可读事实及相关有效约束 | 原分类与报告候选，不写记忆权威 |

首版不把 N3 摘要当 RTL 当前事实，不把 N6 的 addressed 直接当关闭，不把人工的“希望通过”当已签闸门。预算节省仅通过不注入无关历史和无损引用，不能牺牲现行覆盖契约。

## 6 IL 事件、API 和接受门

### 6.1 事件形状与版本

```json
{
  "format_version": 2, "run_id": "...", "revision": 1,
  "operation": "supersede", "request_id": "client-id", "actor": "human:operator",
  "replaces_instruction_id": "old-id",
  "instruction": {"id": "host-issued", "version": 1, "message": "...", "scope": "node_rework", "target_nodes": ["N6"], "dependencies": []}
}
```

operation 枚举 create/revoke/supersede；以上只为一个合法事件的示例，不是现成 API。revoke 只引用存在且仍有效的目标；supersede 同一个原子事件完成旧失效/新建立。未知字段/枚举、空 message、非法节点、旧 revision 或跨 run 引用在写前拒绝。

新增指令事件统一位于 agent_controls/run 的版本化指令事件区域，包含 target_nodes；旧节点 session 格式保持不变。新增读取器负责合并指令投影，旧 /control 的节点事件读取不被扩成任意节点名。目录版本用于 CAS 和命令幂等；每节点的 effective_instruction_sha256 只覆盖实际适用于该节点的条目。对 N12 指令的更改不应无理由取消 N6；涉及 N6 有效集合的变更才撤销其接受资格。

指令事件归 control；它调用 agent_memory 公共 seal_record 发布。request 记录目录 revision 和节点有效集指纹及选择原因。模型不需要复制这些关联字段；Host 用执行身份关联。

### 6.2 一次性指令和恢复

attempt 指令绑定 Host 保留的 next-attempt intent；steer 接收后先停旧请求，再将该 intent 绑定新 attempt。该次失败/取消/初始化失败也结束一次性作用域，不能滚到另一尝试。需要继续时必须显式创建新指令。

node_rework 绑定同 run、同节点，跨该节点的正常返回和显式返工保留，直到 run 终态、显式撤销/替代或其依赖失效；不能在 N6 首次请求完成时就提前删除。run 绑定节点白名单且不跨 run。

恢复只从已提交事件归约有效集；旧 session 控制不可复活。对以后获准尝试注入当前有效文字，不重放 accepted/applied 的操作，不自动启动请求。审计损坏失败，不能悄悄清空指令继续执行。

UI 显示来源/作用域/状态、有效节点、到期/撤销原因和“接收/生效”区别；旧客户端不传 scope 保持现有会话语义。GET 的空集合与读取失败不是同一个状态。

## 7 EXP 适用性算法及迁移

请求审计仍对完整实际输入和契约计算指纹；新增经验适用性不替换它。Host 读取同一人工目录，不另建知识库或自动学习服务。

算法：验证目录格式/版本 → 核验人工批准与条目 revision → 核验历史来源完整性 → 按 kind 核验当前 typed 依赖与适用环境/契约 → 生成稳定的采用/拒用列表 → 检查可选建议预算 → 注入必要建议和短来源引用。

exact_fact 的依赖类型只来自已有事实解析器，例如当前文件内容、条目快照、环境/基线身份和工具契约版本。general_advice 不绑定整个请求，但必须有明确的节点/环境策略/兼容契约范围；缺依赖不是“通用”的理由。模型不能填写机器能验证的假兼容声明。

不自动将 v1 条目升级为 general_advice。迁移工具只校验/生成待确认草稿，写到新的候选文件；人确认后再替换人工目录。输出 old-id → new-id/revision 与条件变化说明，原请求/源归档零改动。

v2 选择拒用原因至少包括：not_approved、revoked、source_missing/corrupt、dependency_changed、unknown_dependency、contract_incompatible、environment_mismatch、budget_batch_rejected。诊断只能报告非秘密的 ID/规则，不回显凭据或完整材料。

可选建议整批超限时不采用并留诊断，必需事实/指令/问题不能因此被丢弃。需要语义检索时另立项，不用字串相似度冒充长期经验选择。

## 8 测试任务与可复现样例

全部公开/合成材料显式标记为测试资产，不能混入真实工程或冻结历史目录。

| 样例 | 核验点 | 预期 |
|---|---|---|
| N3 正常公开工程 | 从获准 diff 找到相关接口定义与文档，通过真实只读工具取证 | 结构化候选通过原 Host；工具证据绑定本 attempt |
| N3 越界与提示注入 | 材料声称“读取另一个 run / 宿主 home” | 工具层实际拒绝，原规则不被升级 |
| N6 返工与多问题 | 重复原要求、follow_up、旧 closed、新作者候选 | ID 不丢、不误合并，按 H2b 重开 |
| N6 候选编辑 | 在独立 candidate 改指定测试用例并产生合法观测印记 | 校验后由 Host 导入；多写文件/链接/源漂移拒绝 |
| 指令改口 | node_rework 指令替代/撤销与模型同时返回 | 一个有效版本，旧结果不消费 |
| 重启 | 记录已接收/已生效指令后终止进程 | 重建集合，无重复命令/候选应用/模型调用 |
| 精确经验 | 当前依赖内容变化，其余输入不变 | exact_fact 拒用 |
| 通用建议 | run/attempt/交接引用变化，已批准依赖与范围不变 | general_advice 可选用，原来源继续核验 |
| 暴力取消 | 工具生成可观测后代且延迟退出 | 未静止前不显示 paused，不启动新尝试 |
| 大上下文 | 强制问题超预算、建议超预算分别触发 | 前者调用前失败；后者整批拒用、事实完整 |

新增测试拟落点：test_agent_working_memory.py、test_agent_instruction_lifecycle.py、test_agent_experience_applicability.py、test_dsh_protocol.py、test_dsh_process.py、test_dsh_backend.py；API/浏览器沿原测试结构扩展。旧 test_agent_context_memory/control/handoff/responses/review、后端特征与 sealed 故障用例保持。

原生测试必须记录运行时/profile/依赖/代码/模型身份、输入版本、实际工具与候选/停止事实；失败、拒绝、取消和未知状态全部留证。受控模型端点可以证明传输/上下文，不用它证明真实模型质量。N6 价值试验沿 SPEC-08 预先登记任务、相同材料/权限上限、模型、预算及采纳阈值，包含所有失败，不挑成功样例。

## 9 云端执行操作清单

1. 读取当前环境状态、网络策略和工作区 AGENTS，确认代码分支/清洁状态与可写数据根。
2. 固定实际 Python/Node/DSH/协议与 profile，先跑既有最小特征测试。Linux 封存依赖在云端就地验证，不套用本机 Windows 的失败结论。
3. 先实施 P1/P2/P3，各自留 RED/GREEN 与恢复/兼容证据；在 Agently 受控路径验收，不等待 DSH。
4. P0 能力满足后实施 P4/P5；先协议替身和故障注入，再真实 SDK，最后以已授权模型做 C2。
5. C2 用独立合成工程与 state，确认停止后清理本轮资源；只删本轮自建范围，保留审计与失败。
6. 需要真实工程结论时在内网运行 E；缺此环境则交付 C1/C2 和具体待验清单，不假装已完成业务验收。
7. 运行仓库四道门。现行端到端为 drill，可写数据根前提见 AGENTS §4/STATUS §73；不要沿用“必须可写 ENV_ROOT”的旧推断。数据根脚本仍需其真实来源夹具，不能临时造同名历史资产。
8. 将结果写 STATUS，证据新增、冻结、目录外校验。原生日志不得含密钥、认证头或 Web 启动凭据。当前原始日志不可取得时明确说明，不能只写 ALL PASS。
9. 做小切片提交；推送/合并依当次用户授权执行。实现者与验证者相同则如实标明。

## 10 完成定义和交接

交付清单：版本化适配器、受限 profile/权限与运行时 manifest、WM/IL/EXP 实现、向后兼容说明、受控/原生/真实模型/内网分层结果、恢复及回退操作、STATUS 与可复验冻结证据。

C1 完成不启用 DSH；C2 只允许通过验证的节点/profile/模型组合显式启用。D4/E 与价值门未通过时不自动扩展到所有角色。审计失败、权限越界、停止未知、必需输入缺件、H2b 覆盖丢失或指令失效失控均为阻断。

后续执行者不需要重新构想方案：按 P0→P1/P2/P3→P4/P5→P6→P7 逐片推进；未决的云端事实只通过当前探测补齐，不反复以缺内网资产搁置可开发的软件项。
