# `doc/` —— 文档索引

> **一句话**：本目录放**契约、角色、证据、历史与审计**五类文档；**代码与运行数据都不在这里**。
>
> **数据根不在本仓**：`kb/index|conflicts|baselines|runs`、`adjudication/` 等属于 **`WORKSPACE_ROOT`**，
> 本机当前 = `ENV_ROOT/kb`（`ENV_ROOT` 由 [`environments.json`](../environments.json) 决定），
> 本仓 `kb/` 只有 `tools/`、`schema/`、`README.md`。解析规则见
> [`spec/ENV_PLUGIN_SPEC.md`](spec/ENV_PLUGIN_SPEC.md) §1。
>
> **数字唯一来源**：[`STATUS.md`](STATUS.md)（Lead 维护）。本目录其它文档**不各自抄一份数字**，
> 历史文档里的数字按上下文标注为历史值。
>
> **适用版本**：本索引描述**当前**仓库结构与入口；带日期/提交号的章节是历史采样，
> 现行能力与实测以 STATUS 最新章节为准。

---

## 1 目录导航

| 目录/文件 | 是什么 | 入口 / 主要文件 |
|---|---|---|
| [`OVERVIEW.md`](OVERVIEW.md) | **项目总览 + 三张流程图**（架构边界 / 主流程 / 长任务生命周期） | 先读这个 |
| [`UI_RUNBOOK.md`](UI_RUNBOOK.md) | **人工跑通手册**：起服务、配置一次运行、三道闸门怎么点、终点判读与排障（操作类，非契约） | 要亲手跑一遍时看 |
| [`spec/`](spec/) | 三份契约：业务篇 / 编排篇 / 环境插件篇 | 见 §2 |
| [`agents/`](agents/) | 6 个角色定义 + 2 份开工提示词 | [`agents/README.md`](agents/README.md) |
| [`evidence/`](evidence/) | 验收报告与演练证据（**内容冻结、只增不改**） | [`evidence/README.md`](evidence/README.md) |
| [`history/`](history/) | 拆仓前的历史快照（**不是现状**） | [`history/README.md`](history/README.md) |
| `audit/` | 审计与独立验证报告（**只登记/只报告，不改被测实现**）：2026-10-19 总报告 + 附录、后续复核与逐切片验证 | [`audit/README.md`](audit/README.md)、[`audit/AUDIT-20261019-spec-conformance.md`](audit/AUDIT-20261019-spec-conformance.md)、`audit/parts/*.md`（附录）、`audit/*-verify-*.md` |
| [`STATUS.md`](STATUS.md) | 唯一数字源：HEAD、单测/断言数、四道门状态、外部数据根 | 由 Lead 维护 |
| [`plans/`](plans/) | 按 SpecDD 拆分的实施计划与验收条件 | [优化与重构执行手册](plans/OPTIMIZATION_PLAYBOOK.md) |

> 逐级入口：[`../README.md`](../README.md)（项目导航）→ [`../AGENTS.md`](../AGENTS.md)（流程 / 写权 / 红线）
> → 本文件 → 各子目录 README。

后续工作统一入口：[下一轮 SpecDD 计划](plans/2026-10-22-next-iteration-specdd.md) → [内网验证手册](plans/2026-10-22-intranet-validation.md)（可复制命令、预期结果、失败处理、证据交接）。先收口 R1–R5，再做 F14/F05；本次成册不代表修复已实施。原 [优化与重构执行手册](plans/OPTIMIZATION_PLAYBOOK.md) 保留 F 编号与任务来源，历史实施进度见 STATUS §14 起，最新复核/离线交付见 §35–§36。此前 [优化评估](audit/AUDIT-20261021-specdd-followups.md) 与 [原路线](plans/2026-10-21-specdd-followups.md) 保留为来源。

网页视觉升级：[视觉契约](spec/WEB_UI_SPEC.md#14-全站网页视觉系统2026-10-21) → [实施计划](plans/2026-10-21-desktop-redesign.md) → [预览与验证证据](evidence/WEB_REDESIGN_20261021.md)。范围为浏览器中的现有工作台；状态与本轮实测见 STATUS §12。

内网浏览器验证：[Rocky 离线包与运行命令](../loop/offline/README.md) → [交付计划](plans/2026-10-22-browser-offline.md)；实际结果与主机系统库限制见 STATUS §36。

## 2 `spec/` 契约

> **编号**：每份 SPEC 有稳定编号 `SPEC-0X`（文件名不变）。当前修订记录：[`SPEC-REV-01`](spec/SPEC-REV-01-20261022.md)（2026-10-22，待验收）。
> 修订记录只增不改；新增 [SPEC-REV-02](spec/SPEC-REV-02-20261023.md) 为 DSH 核接入设计草案，未实现、未验收，不替代现行能力说明。

| 编号 | 文件 | 管什么 |
|---|---|---|
| SPEC-01 | [`spec/CHANGE_IMPACT_LOOP_SPEC.md`](spec/CHANGE_IMPACT_LOOP_SPEC.md) | 业务与不变量 I1–I8、16 节点 N0–N16、三道人工闸门（Gate1/2/3）、闸门材料充分性（§7.1） |
| SPEC-02 | [`spec/LOOP_ORCHESTRATION_SPEC.md`](spec/LOOP_ORCHESTRATION_SPEC.md) | 编排层机制契约：owner 账本、生命周期、长任务停等、单槽准入、重启恢复、进度/UI 投影、节点执行详情投影（§10.4） |
| SPEC-03 | [`spec/ENV_PLUGIN_SPEC.md`](spec/ENV_PLUGIN_SPEC.md) | 三根（`TOOL_ROOT`/`ENV_ROOT`/`WORKSPACE_ROOT`）解析、环境插件契约、拆仓分步与「数据不搬」决定 |
| SPEC-04 | [`spec/WEB_UI_SPEC.md`](spec/WEB_UI_SPEC.md) | v1 运营台：两区信息架构、配置/运行/闸门三视图、节点详情面板（§4.2.1）、闸门材料可判性、环境来源徽标（§4.5）、新增 API 契约与验收判据 |
| SPEC-05 | [S0 环境准备](spec/S0_ENVIRONMENT_SPEC.md) | 修订稿 S0 双段、基线零写、派生校验、TB 授权及三库准出边界；S0 与 drill/N0–N16 的关系与两级验收（§6/§7） |
| SPEC-06 | [`spec/AGENT_CONTEXT_SPEC.md`](spec/AGENT_CONTEXT_SPEC.md) | Agent 上下文覆盖、逐次调用留痕、人工确认经验及版本/来源失效规则 |
| SPEC-07 | [Agent 工作窗口](spec/AGENT_WINDOW_SPEC.md) | 逐节点观察、人工补充指令、请求暂停/恢复/终止、控制审计与身份隔离（仅模型节点；Host 节点用 SPEC-04 §4.2.1） |
| SPEC-08（草案） | [DSH Agent 执行后端](spec/DSH_AGENT_RUNTIME_SPEC.md) | 环境 DSH 核接入、工具与候选目录权限、会话/控制/审计及验收；未实现 |
| SPEC-09（草案） | [AI 工作面板体验设计](spec/AI_WORK_PANEL_SPEC.md) | 统一 AI 入口、成果阅读、状态化操作、历史与刷新、可访问性及分阶段验收；未实现 |

DSH 接入阅读入口：[设计草案](spec/DSH_AGENT_RUNTIME_SPEC.md) → [实施切片](plans/2026-10-23-dsh-agent-runtime.md)。先探测内网真实能力，再接 N3 只读分析与 N6 候选编辑。

AI 界面优化入口：[设计与布局示意](spec/AI_WORK_PANEL_SPEC.md) → [实施切片](plans/2026-10-23-ai-work-panel.md)；
修订范围见 [SPEC-REV-03](spec/SPEC-REV-03-20261023.md)。第一版复用现有接口，第二版按依赖增加对比、预览与 DSH 动态。

## 3 阅读顺序（新接手）

1. [`../README.md`](../README.md) §2「三个根」+ [`../AGENTS.md`](../AGENTS.md)（组织与纪律）。
2. `spec/` 三篇按 业务 → 编排 → 环境插件 的顺序读。
3. 找角色/写权：[`agents/README.md`](agents/README.md)。
4. 现状数字：[`STATUS.md`](STATUS.md)；历史背景：[`history/README.md`](history/README.md)。
5. 已知偏差：[`audit/`](audit/)（总报告 + 附录；**审计发现不等于已修复**）。

## 4 文档纪律

- 新增文档先归类：spec / agents / evidence / history / audit，**不在根目录堆日期文件**（`AGENTS.md` §6）。
- `evidence/` 与 `history/` **只增不改**；移动文件必须留下 MIGRATION 或「已过期」横幅（`AGENTS.md` 红线 12）。
- 引用冻结件必须带 md5；判「未改动」按**内容 md5**，不按 mtime。
- 本仓 `doc/` ≠ 环境仓 `doc/`：`doc/AGENTS.md`、`doc/skills/`、`doc/_notes/`、`doc/tools/`、
  `doc/spec/evidence/` 等仍在 **`ENV_ROOT`**；本目录文档里出现这些路径时，均**相对 `ENV_ROOT`**，不是本仓。
  （唯一例外是本文与各 README 里显式写成 `doc/...` 的本仓页面。）
