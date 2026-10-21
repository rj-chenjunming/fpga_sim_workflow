# 网页重设计后的优化与重构复核

> **本轮是否修复：否。** 本轮只读检查当前实现、补充可复现观察并整理执行手册。没有实施下面的业务修复或重构。
> 复核基线：`d7cf7c6084e884b0f554893c11f812b04c64f6bc`。同一执行者实施复核，不是独立终验。范围是软件仓及受控临时目录，没有访问内网仿真资产。
> 后续统一入口：[优化与重构执行手册](../plans/OPTIMIZATION_PLAYBOOK.md)。实测见 [STATUS §13](../STATUS.md#13-下一阶段优化与重构成册2026-10-21)。

## 与既有路线的关系

[上一轮审计](AUDIT-20261021-specdd-followups.md) 和 [原实施路线](../plans/2026-10-21-specdd-followups.md) 的 F01–F12 保持编号；本次补充 F13–F15，并把操作顺序、提交切片、验收和回退合并进执行手册。旧审计与冻结证据不回填。

网页重设计已在本次基线内：四视图导航、统一视觉令牌、旧界面样式、键盘入口及浏览器布局检查已经交付。下一阶段保留用户选择的“专业清爽”网页方向；不重新立项全站重设计，不开发桌面客户端或手机端专项适配。

## 重新确认的优先项

| ID | 当前定位 | 本次结论 | 性质 |
|---|---|---|---|
| F01 | [config_api.list_baselines](../../loop/services/config_api.py#L61)、[RunManager.start](../../loop/workflows/main_flow.py#L442)、[N0](../../loop/workflows/chunks/host_steps.py#L127)、[N2](../../loop/workflows/chunks/host_steps.py#L292) | 临时目录仅有空对象 manifest 仍被列为有效；数组 manifest 导致 AttributeError；截获 real N2 参数，选择 v-next 仍传 v0。创建入口在建立运行前缺完整基线准入，N0 所选 manifest 传递仍需闭合。 | 已复现局部缺陷；尚未在内网复现整链影响 |
| F02 | [agent_view.build_agents](../../loop/services/agent_view.py#L196)、[model_steps.n11_review](../../loop/workflows/chunks/model_steps.py#L1732)、[app.js](../../loop/web/app.js) 的 deriveNote | 无事件时 guardian 仍显示“未实现（审计 A10）”；N11 已有成链/返工实现。前后端均有旧提示，不能只改其中一处。 | 已复现提示漂移；真实 provider/完整真机验证范围仍需单独说明 |
| F03 | [测试夹具](../../loop/tests/conftest.py)、[端到端驱动](../../loop/spikes/accept_v1_run.sh)、[文档解析器](check_doc_links.py#L91) | 测试仍引用共享软件 state；验收脚本清理整个 state 和工作区 drill 记录。无内网根时，本仓存在的 kb 工具被扫描器误判为缺失。 | 已确认验证隔离不足及路径解析误判；本轮没有执行清理脚本 |
| F04 | [S0 实现](../../loop/host/s0.py)、[S0 契约](../spec/S0_ENVIRONMENT_SPEC.md) | 准出恒为 false，接口核对、逐 hunk 适配、真实三库与执行消费者尚未接入。 | 明确的能力缺口，当前阻断符合契约 |
| F07/F08/F09 | [read_view](../../loop/host/agent_control.py#L78)、[async 路由](../../loop/services/api.py#L264)、[_sealed](../../loop/host/agent_memory.py#L113) | 历史全量读取、同步文件 I/O、数据/校验顺序写入、进程内活跃注册表仍在。 | 性能和杀进程故障是待测风险；暂停不跨进程是已知边界 |

源码定位绑定本次基线；后续按函数符号定位，不能把旧行号当成永久接口。

## 本次新增条目

### F13 · P1 · 首次读取失败的反馈不准确

受控浏览器首次选择 A，详情返回 503，界面同时显示“加载中…”和“读取失败”，并声称“当前显示最近一次成功的数据”，即使该运行从未读取成功。页面无 JavaScript 异常、没有写请求；这是用户可观察的状态表达问题。

定位：[renderRunHead](../../loop/web/app.js#L938)、[renderRunAlerts](../../loop/web/app.js#L1014)。现有 [异常布局测试](../../loop/tests/browser/test_web_layout.py) 验证错误可见且无溢出，没有断言首次错误与刷新错误的语义差异。新验收应区分加载中、首次失败、已有数据但刷新失败、恢复成功，且继续拒绝旧运行回包污染当前选择。不能靠颜色或取消错误显示解决。

### F14 · P1 · 全站样式需要收敛到单一组件定义

[app.css](../../loop/web/app.css) 保留早期组件/S0 样式，并由后面的网页视觉系统覆盖。header、aside、main、按钮、卡片、S0 hero 等存在多处声明，早期断点与后续断点交叠；[legacy.html](../../loop/web/legacy.html) 的内联样式也由 [legacy.css](../../loop/web/legacy.css) 继续覆盖。

这是已确认的维护成本，不代表已发生渲染事故。应在固定新视觉特征后按组件合并有效声明和断点，迁移到共享令牌，移除经真实状态覆盖确认无用的规则。不能按“同一选择器出现两次”就自动删除，也不能把 hover、focus、disabled、dialog、动态节点及旧界面样式误判为死代码。最终基准是网页行为、有效样式与人工审阅的截图。

### F15 · P1/P2 · 规格现状、验证入口与交付记录需要一处可查

复核基线中的 [根 README](../../README.md) 仍称“单文件前端”，本轮添加导航时已改为“网页工作台”；[Web 规格](../spec/WEB_UI_SPEC.md) 中还混有 v1 的角色计数、能力和旧状态说明，留待 F15-a 系统整理。新版视觉章节覆盖了布局，却没有消除全部机制说明漂移。当前目录未发现 `.github`；只能确认没有该路径，不能推断组织没有外部 CI。

先建立“当前契约 / 已实现 / 当前环境可用 / 已验证 / 待实现”的对应表，把过时章节指向当前章节，保持冻结证据只读；再在 F03 隔离完成后固化软件检查入口和可选 CI。CI 接入目标需实施时确认；不得声称已部署自动门禁，也不能把未经隔离的全套测试直接接入共享环境。

## 后续决策

先完成 F01 的基线身份和准入，再处理 F02/F13 的真实反馈，并建立 F03 的验证隔离。随后执行 F14 样式收敛、F05 前端功能拆分和 F06 模型边界拆分。F04 先交付协议，再以实际内网证据开放准出；F07/F08 先测量或注入故障，F09 在记录恢复语义明确后立项。F10/F11 是后续可解释性与观察效率增强，F12 继续暂缓。

本轮探针及边界见新增冻结证据，MD5 统一记录在 STATUS §13。复现脚本：[post-ui-roadmap-probe.py](parts/post-ui-roadmap-probe.py)。该脚本记录现有结果，退出成功不等于这些缺陷已修复。
