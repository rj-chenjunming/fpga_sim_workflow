# SPEC-04 · Web UI 规格（v1 · 运营台）

> 编号：**SPEC-04**（文件名不变；编号与修订记录见 [SPEC-REV-01](SPEC-REV-01-20261022.md)）。

> **2026-10-21 网页视觉修订**：当前视觉契约以 §14 为准，覆盖下文 v1 的导航尺寸和样张样式。旧样张保留为历史参考。

> Agent 卡片新增工作窗口；可观察内容、真实请求边界干预与 API 见 [AGENT_WINDOW_SPEC.md](AGENT_WINDOW_SPEC.md)。关闭窗口不停止任务，刷新不重建输入表单，过期回包不得污染其他运行。

> 2026-10-21 S0 工作台增量：默认入口改为“环境准备”，新增 S0-a/S0-b 双段视图，契约见 [S0_ENVIRONMENT_SPEC.md](S0_ENVIRONMENT_SPEC.md)。以深色导航、浅色主区和青绿操作色重排；既有配置/运行/闸门保留，并标注“现有闭环”。S0 展示真实派生记录、指纹与阻断，绝不从空 TB 表或未跑编译推断就绪。表单与结果分栏，窄屏堆叠；按钮/输入具可访问名称和焦点标识。轮询不重建 S0 表单、保持既有闸门会话隔离。

> **状态**：v1 设计基线（2026-10-19）。设计样张：[`../web/mockup.html`](../../loop/web/mockup.html)（只读静态页，数据为假）。
> **上游**：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §10（UI 投影契约）、`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（N0–N16 / I1–I8 / 三闸门）、`doc/audit/AUDIT-20261019-spec-conformance.md`（已知实现缺口）。
> **定位**：把现有「15 个面板堆一页」的界面重构为「**配置 → 执行 → 监控**」两区运营台；界面仍然只是**只读投影 + 两个写动作的传输层**。
> **范围纪律**：v1 只做「基线目录选择 / 项目目录选择 / 流程执行状态 / 6 个 agent 工作状态 / 闸门操作」；细节迭代见 §12。

---

## 1 目标与非目标

### 目标（操作员三条主路径）

1. **配置一次运行**：选基线版本目录 + 选要修订的项目目录 → 校验 → 确认启动。
2. **看流程**：N0–N16 按「摄取 / 修订 / 验证 / 决策」四段展示，当前段自动展开。
3. **看 agent**：6 个模型角色各自的状态、当前动作、耗时、结论与证据入口。
4. **做决策**：到闸门时提交唯一的人工决策；被拒时看到服务端给出的 blockers。

### 非目标（v1 明确不做）

- 不做用户体系/鉴权/多用户；不暴露到网络（只绑 `127.0.0.1` + SSH 隧道）。
- 不做前端编辑用例、直接改基线/冲突清单。
- 不做 SSE/WebSocket（v1 用轮询）；不做移动端适配。
- 不做跨环境**运行时**切换（见 §4.3 的硬约束）。
- 不把界面做成第二套状态机：不判绿、不判红、不手抄闸门枚举。

---

## 2 信息架构（两区）

```
┌──────────────────────────────────────────────────────────────────┐
│ 顶栏：品牌 · 当前环境 · 服务地址 · 样张/版本标记                  │
├──────────────┬───────────────────────────────────────────────────┤
│ 左栏 286px   │ 右区（工作区，按阶段切换）                        │
│              │                                                   │
│ ＋ 新建运行  │ ① 配置视图：基线 → 项目 → 选项 → 确认条          │
│              │                                                   │
│ 运行记录     │ ② 运行视图：状态条 + 四段流程 + agent 卡           │
│ - RUN-…      │             + 右列（闸门/双口径/blockers/证据）    │
│ - RUN-…      │                                                   │
│              │ ③ 闸门视图：材料 + 选项 + actor/理由 + 提交        │
│ 底部：根/模型│                                                   │
└──────────────┴───────────────────────────────────────────────────┘
```

- **左栏**：新建入口 + 运行列表（`run_id / status / mode / updated_at / current_node`），选中高亮；底部显示 `TOOL_ROOT / WORKSPACE_ROOT / 模型`。
- **右区视图切换**：由运行状态驱动（`waiting_gate` 默认进闸门视图），也允许手动切换用于预览（样张里用 ①②③ 开关）。
- **响应式**：宽度 < 1100px 时右列（闸门/证据）下移为整行；左栏不折叠（单机单用户）。

---

## 3 配置视图

三个步骤 + 一个确认条。

### 3.1 步骤 1：选择基线版本

- 数据源：`GET /api/baselines`（实现见 §6.1），列出 `<WORKSPACE_ROOT>/baselines/*`。
- 每项展示：版本号、`manifest.created_at`、`parent`、用例数、RTL 快照大小、`valid`（manifest 可解析）。
- 交互：下拉 + 「浏览…」打开目录浏览器（见 §3.4，根 = `baselines/`）+ 「刷新」。
- 校验：必须选一个 `valid=true` 的版本；`v1` 等不存在版本置灰。
- 回填：`baseline`（字符串）写入运行创建请求。

### 3.2 步骤 2：选择要修订的项目目录

- 语义：**`ENV_ROOT`（环境仓根）**，即被守卫的 `RTL/TB/PKG/TESTLIB + uvs.setup` 所在目录。
- 交互：只读输入框 + 「浏览…」（目录浏览器，根 = 配置的浏览根，见 §6.3）+ 「校验」。
- 校验：`GET /api/env/check?path=`（§6.2）返回：
  - `ok`、`env_id`（命中注册表时）、`registered`；
  - `plugin_missing` / `workspace_missing`；
  - `counts{rtl_files, cases}`；
  - `writable{frozen, sim_workdir}`；
  - `warnings[]`（如「当前进程 ENV_ROOT 不是该目录」）。
- 通过条件：`ok=true` 且 `plugin_missing=[]`；否则确认按钮禁用并展示缺什么。

### 3.3 步骤 3：运行选项

- `mode`：`drill`（默认，冻结夹具）/ `real`（真机）。
- `scenario`：`happy` / `dead_job` / `cancel`（仅 drill 有意义）。
- 高级（默认折叠）：`now`（ISO 时间注入）。
- **real 模式提示**：读审计结论，显示「real 链路未闭合（N1/N6/N7/N9/N15），启动前请确认」；允许启动但必须显示风险标记（不静默）。

### 3.4 目录浏览器（基线与项目共用）

- 结构：`↑ 上级` + 面包屑（可点击跳转）+ 当前层目录列表 + `选择此目录`。
- 列表项：`name`、类型（目录/环境仓/基线版本）、可选的标记（`manifest.json`、`uvs.setup`、用例数）。
- 只列**目录**；文件只在「标记」里出现名字，不读内容（见 §8）。
- 基线与项目**共用组件**，差异只在数据源与根。

### 3.5 确认条

- 汇总：`基线 / 环境 / 模式`；主按钮「确认并启动」；启动中禁用并显示 spinner。
- 点击后：`POST /api/runs`（§6.4）→ 成功后切到运行视图；失败按服务端错误展示（不吞）。

---

## 4 运行视图

### 4.1 顶部状态条

- `run_id`（等宽）、状态胶囊、`mode`、`baseline`、`project`、已用时长、最后更新时间。
  - v1 后端**实际**只会给出：`running / waiting_gate / finished / failed`；`waiting_job / waiting_slot` 的细分属审计 I18 的后续修复，v1 统一显示为 `waiting_gate` 并用 tooltip 说明「可能是作业/单槽等待」。
- 动作：刷新、取消作业（仅在有活动 job 时可用）。
- 若 `status=failed`：展示 `error` 原文与 `notes`；不得只显示「失败」。

### 4.2 四段流程（折叠 + 展开当前段）

| 段 | 节点 | 展开默认 |
|---|---|---|
| 摄取 | N0 基线 · N1 摄取 · N2 diff · N3 总结 · **N4 闸门1** | 闸门 1 等待时 |
| 修订 | N5 影响 · N6 修订 · N7 编译 · N8 复核 | N5–N8 进行时 |
| 验证 | N9 全跑 · N10 对账 · N11 守护 · N12 报告 | N9–N12 进行时 |
| 决策 | **N13 闸门2** · **N14 闸门3** · N15 回归 · N16 晋升 | 闸门 2/3 等待时 |

- 段头：序号、段名、节点区间、进度条、状态（`完成 / 进行中 / 等待人工 / 失败 / 待开始 / n/m`）。
- 默认只展开「当前段」；点段头手风琴切换（同时只开一个）。
- 展开后每个节点 chip：节点号 + 名称 + owner（`Host / analyst / author / checker / guardian / reporter / 人 / TriggerFlow`）+ 状态。
- 闸门用菱形标记；`等待` 状态的闸门节点高亮为琥珀色。
- **映射是展示契约**（写在本文 §4.2），不是执行契约；节点集合变化时以 `node_history` 为准并显式显示未知节点。

### 4.2.1 节点详情面板（节点 chip 可点击）

> AI 首批入口调整见 [SPEC-09 §11](AI_WORK_PANEL_SPEC.md#11-本批实现契约2026-10-24先于代码)：AI 节点先进入工作面板，
> 再由“节点执行详情”进入本节面板；角色卡同入口。Host/闸门仍直接进入本节详情，原投影能力保留。
> 本节的全部节点详情可访问性继续有效，AI 默认入口由新契约细化；实测范围见 STATUS §55。

> 来源：[SPEC-REV-01](SPEC-REV-01-20261022.md) R4、[SPEC-REV-04](SPEC-REV-04-20261023.md) R1。数据契约见 [SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4。

- **范围 = 全部节点**：执行视图里出现的**每一个**节点 chip 都可点击——N0–N16、四段之外/内部的节点
  （`N6_apply` / `N9_submit` / `N15_select` / `N15_submit`）、`HALT`，以及将来新增的节点；
  闸门节点（N4/N13/N14）同样可点。不按白名单裁剪，不因"没有中文名/owner"就不可点。
- **数据**：`GET /api/runs/{run_id}/nodes/{node}`（§6.7）；内容来自事件流 + `node_finished.detail` + `refs`，**界面不自行拼装**。
- **状态原值**：节点 status 不只 `ok/failed`（闸门=决策值、N8/N11/N16/HALT 各不相同）；面板显示服务端原值，不得自行归成"完成/失败"。
- **可读性优先（SPEC-REV-04 R1）**：面板从上到下固定为
  ① 头部（节点/名称/owner/状态原值/执行方式）→ ②「这一步做什么」（`story.purpose` 一句话）→
  ③「结果一句话」（`summary` 原文）→ ④「关键数字」（`story.key_results` 逐项标签+值）→
  ⑤「过程」（`story.steps` 按事件顺序的人话步骤）→ ⑥「证据 / 失败」→
  ⑦「原始记录（排查用，默认收起）」。
  首屏必须能读到 ②–⑤，不必展开。

  | 区块 | 内容 |
  |---|---|
  | ① 头部 | node / 名称 / owner / 状态（服务端原值 + `story.status_note` 中文释义，如 `ok 通过`）/ 执行方式（`source` 原值 + 中文说明；夹具与 standin 必须醒目） |
  | ② 这一步做什么 | 服务端 `story.purpose`；未知节点显示"服务端未登记用途" |
  | ③ 结果一句话 | `story.headline`（短结果，服务端模板生成）；`story.headline_source` 不是 `template` 时在其后加小字附注（`summary` ⇒「（原文摘要）」、`missing` ⇒「（未下发）」，`template` 不显示）；`story.note` 非空时在其下渲染一行黄条；`detail.summary` 原文移入 ⑦「原始记录」顶部并注明"服务端 summary 原文" |
  | ④ 关键数字 | `story.key_results`（逐节点精选字段；缺失逐项"未下发"；`detail` 为空时只显示一行"还没有收尾记录"）；N6 另按 `story.observation_points` 渲染可折叠「观测点（N 条）」列表（每条：用例 / marker / addr+off / 期望值；`null` ⇒「未下发（旧 run 或替身，模型未产出观测点）」） |
  | ⑤ 过程 | `story.steps`（人话；时间由前端按 `ts` 渲染；**正文不出现 `seq`**；步骤状态 chip 同样带中文释义） |
  | ⑥ 证据 / 失败 | `refs` 存在性探测；`story.evidence_groups` 为数组时按用例分组展示（组头=用例名；组内 refs 为空 ⇒ 显示服务端 `note`，如「本轮未执行/无证据」，不留空白）；`evidence_groups=[]` ⇒ 显示 `story.evidence_groups_note`；`null` ⇒ 维持平铺 `refs`。N9 显示 `detail.example_line`（默认收起，展开见原文；`null` ⇒ 不渲染）。`story.evidence_note` 非空时置顶显示（`agent_calls` ⇒ 指 Agent 工作窗口，**不得**再显示"证据缺失"；`not_executed` ⇒ "本轮未执行（无证据）"）；`node_failed` 时显示 `error` 原文，**不得**显示"完成" |
  | ⑦ 原始记录 | **默认收起** `<details>`：原始事件切片（含 `seq` / `kind` / `status` / `ts`）、完整 `detail` JSON、`summary` 原文、`missing_fields`、身份技术字段（`known` / `authority` / `started_at` / `finished_at` / `source` 原值） |

- **状态释义（P-07）**：状态 chip 显示 `{服务端原值} {story.status_note}`；原值逐字保留、不归一
  （`ok` 不得被改写成"已完成"）。释义表由服务端 `story.status_glossary` 下发，前端不手抄第二份。
- **未到达 / 未执行 / 未下发三态必须分清（P-30/P-32/P-33）**：
  - `story.not_reached=true`（运行已终态且该节点无事件）⇒ 显示服务端 `headline`
    「本轮没有走到这个节点（运行停在 {run_status}，{中文释义}）」——原值保留、中文 gloss 附后
    （`failed→失败`/`finished→已完成`），**不得**说"还没有收尾记录，等它跑完再看"；
  - `story.not_executed=true`（drill/演示下确实没执行该动作）⇒ "—（未执行）"，不写成"未下发"；
    drill 停在更早闸门（运行已被 HALT 终止）时，归因必须是「本轮未执行（没有提交记录）」，
    **不得**写成"演示模式不提交"（那会把"没走到"误报成"演示不跑"）；
  - 其余缺字段仍显示"未下发"。
- **闸门节点（N4/N13/N14）**：②之后新增「差异清单」区（见 §4.2.2）；等待态必须用白话 + 数字列出
  硬阻断（`gate.hard_block`，如"有 3 个用例改完没验证通过 / 日志错误标记 1687 行 ≠ 0 / 72 条冲突未清零"），
  内部代号（I2/I3/I4）只能作小字附注或留在原始记录。
- **N12 报告**：`report.available=true` 时提供「查看报告全文」只读视图（契约见 §6.8）；缺失显示"本轮没有报告文件"。


- **`seq` 的定义与位置**：`seq` 是同一 run 内严格递增的**事件流水号**，只用于排序与定位（"第几条事件"），
  **不是业务状态**。正文不展示；只在 ⑦ 顶部以一句解释 + 逐条事件的形式出现。
- **drill 说明**：`source=drill_fixture` 显示为「drill 演示数据（不碰真实环境）」，并在首屏加一行
  「结果来自预置数据（夹具），不碰真实环境，也不验证环境搭建（S0）」；不得用 drill 结果暗示环境就绪。
- **步骤来源**：`story.steps` 由服务端按事件 `kind` 白名单确定性生成（[SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4）；
  界面不做语义拼装、不做状态归一、不补默认文案。

- **逐节点字段下限**：见 [SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4 的逐节点表（N0–N16 + 内部节点 + HALT）；
  缺失字段显示"未下发"并进 `missing_fields`，不得用前端默认值补齐。
- **身份来源**：节点名 / owner 以**服务端下发**为准；前端 `NODE_META` 仅作服务端未下发时的**兜底**，不得成为第二权威（AGENTS §2：两个 owner 写同一份状态 ⇒ 设计不成立）。
- **与 §12 的边界**：本条与 §12「v1 不做」里 agent 卡的「详细模式」是不同对象——前者是**节点执行详情**，后者是**模型角色的输入/输出详情**；§12 该条不覆盖本面板。
- **边界**：面板只读、不写盘、不触发重跑；不提供 run 目录外的任何路径；模型节点可从这里跳到 Agent 工作窗口（[SPEC-07](AGENT_WINDOW_SPEC.md)），Host 节点不提供工作窗口入口；闸门节点可跳闸门视图（材料同源）。
- **轮询不丢**：执行视图流程条约 1.5 s 全量重建，面板必须是**独立弹层/抽屉**（自带状态），不能做成 chip 内联展开块。
- **历史 run**：旧 run 的 detail 可能缺新字段，面板显示"未下发"并列出 `missing_fields`；**不回填**历史事件与既有 run。
- **诚实标注**：面板底部固定一句「投影，非权威；判据以服务端 blockers / gates.json 为准」。

### 4.2.2 闸门节点的二级差异清单（N4/N13/N14；P-17/P-18/P-29）

> 来源：[SPEC-REV-04](SPEC-REV-04-20261023.md) §R2（设计已定）。数据面见 [SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4.2。

- **位置**：闸门节点面板在「结果」之后新增「差异清单」区，标题行 `共 N 条修订点，已处置 M 条`
  （`N = gate.counts.revision_points`；等待态 `M` 由共享草稿算，已决策态取 `gate.counts.disposed`）。
- **每条一行（一级，紧凑）**：勾选框（处置状态）+ 一句话（`gate.entries[].title`）+ 元信息
  （文件名 · 行号/偏移 · 变更种类 · 未决徽标）+ 「查看前后对比 ↗」入口。
  `gate.entries[].attached` 是同一文件的**附证据**（md5-only，`redundant_of` 指向主条目），
  只作"另有整文件指纹 1 条（不计入）"显示，**不清单行、不计入 N 条**；附证据的 `note`
  （如"整文件指纹，不计入修订点"）必须在条目展开/浮窗的附证据区可见（不得只显示条数）。
- **前后对比用浮窗，不在行内展开（P-18）**：宽 ≥ 80% 视口、可滚动、代码自动换行；左右两栏
  before/after（全宽），`diff_hunk` 按 `@@ -a,b +c,d @@` 解析成两栏并标行号；`doc_entry` 先列变化字段
  （before→after）；无 hunk 必须显示**原因**（旧版正文缺失 / 非 UTF-8 / 二进制）与可替代证据
  （行号、md5），不得留空；元信息含 `offset` / `encoding` / `evidence` / 夹具徽标。
- **逐条处置**：每条可选 `confirmed`（已确认）/ `ignored`（忽略，理由必填）/ `disputed`（有疑义，理由必填）；
  取值一律用服务端 `gate.decision_options`（不手抄枚举）。整门决策由逐条处置推导
  （有 `disputed` ⇒ `disputed`；否则有 `ignored` ⇒ `ignored`；否则 `confirmed`），
  推导复用 `GateSession.deriveEntryDecision`；**最终以服务端 `normalize_entry_decisions` 判定为准**。
- **提交入口唯一**：面板**不新增写动作**，勾选与理由只写进共享 `gate-session` 草稿
  （`run_id + gate + cycle` 身份，刷新保留、不落盘）；底部只给「已处置 M / N」+「去闸门视图确认并提交 →」，
  真正提交仍走 §4.4 的闸门视图现有表单（`entry_decisions` 覆盖全部 `entry_id`）。
- **已决策态只读**：显示当时的逐条处置（`gate.entries[].disposition`，来自 `decisions/<gate>.json`）、
  整门决策（含人工理由原文与签署时间）；无落账 ⇒ 明说"逐条处置未留存"，**不从 `gates.json` 猜**。
- **浮窗嵌套**：节点面板本身是 `<dialog>`，浮窗用 dialog 栈或页内 overlay；Esc 只关上层、焦点回触发按钮；
  窄屏浮窗改全屏。勾选框与「查看前后对比」是两个独立命中区。
- **N13/N14 的"待确认项"（2026-10-23 裁决 #2：只读清单，不新增逐条处置）**：闸门区在 G2/G3 渲染
  `gate.items` 只读清单（标题「待确认项（只读，N 条）」），每条一行：`kind` 徽标 + 一句话 + 补充说明；
  **没有勾选框、没有 disposition、不参与提交**（逐条处置语义仍只属于 G1/I1）。
  - G2（N13）：`kind=blocker`（当前阻断项，白话）+ `kind=open_item`（N12 报告未闭环项）；
  - G3（N14）：`kind=blocker` + `kind=conflict`（未清冲突摘要，如 "72/126 条"）+ `kind=case`（回归选集用例；
    `N15_select` 在 G3 之后才跑，已决策且选集已落地时才列）。
  - `gate.state` 四态：`waiting`（等待人）/ `decided`（已决策）/ `read_only`（非 G1、只有只读清单，
    无可处置项 ⇒ 不显示"去闸门视图确认并提交"）/ `no_material`（连清单都没有，明说"服务端未下发待确认项"）。
  - 清单来源全部是服务端既有材料（`blockers` / `N12.open_items` / `N15_select.cases` / 冲突快照），
    缺材料就少列、**不编**。

### 4.3 Agent 工作状态（6 张简洁角色卡）

| 角色卡 | 节点 | 负责 |
|---|---|---|
| `simenv-analyst` | N3 | 差异语义总结 |
| `simenv-author` | N6 | 用例修订/补充 |
| `simenv-checker` | N8、N10 | 静态复核 / 结果对账 |
| `simenv-guardian` | N11 | 证据守护（成链判断） |
| `simenv-reporter` | N12 | 评估报告 |
| Host（非角色卡，固定一行） | N0/N1/N2/N5/N7/N9/N15/N16 | 确定性步骤 / 长任务看护 |

卡片字段（v1）：

| 字段 | 来源 | 说明 |
|---|---|---|
| `status` | 事件派生：`idle / working / waiting / done / failed` | `working` = 最近事件是 `node_started`；`waiting` = 该节点对应闸门 pending 或长任务停放；`done` = `node_finished ok`；`failed` = `node_failed` 或 `finished failed` |
| `last_action` | 最近一条事件 `kind + status` | 如 `node_started`、`node_finished(validation_failed)` |
| `elapsed` | `node_started` 到 `node_finished`（或现在） | 只显示粗粒度 `mm:ss` |
| `summary` | 该节点产物存在时读取（N3 `n3_digest.md`、N6 `N6_author_note.md`、N8 `check_C.md`、N10 `reconcile.md`、N12 `n12_report.md`） | 仅一行；读不到就显示「产物未生成」 |
| `mode` | `node_finished` 的 detail（`<node>_request` 事件里 `model`） | `live` / `standin`；读不到显示 `—` |
| `evidence` | run 目录内产物相对路径 | 点击先 `GET …/evidence/exists` 探测，再打开/提示缺失 |

- **诚实标注**：卡片底部统一标注「投影，非权威；判据以服务端 blockers / gates.json 为准」。
- **能力事实（F02）**：每张卡由**服务端**下发 `capabilities`，四个维度相互独立、不得互相推断：

  | 维度 | 取值 | 含义 |
  |---|---|---|
  | `implemented` | `true` / `false` | 该角色的业务能力是否已有实现（当前 5 个角色均为 `true`，含 N11 成链判断/返工） |
  | `dependencies_ready` | `true` / `false` / `null` | 当前环境依赖（provider、UVS、夹具）是否齐备；`null` = **未知**，不得猜 |
  | `execution` | `not_started` / `standin` / `real` / `unknown` | 本次运行该节点实际执行方式；`standin` 不等于真模型完成 |
  | `verification_scope` | 字符串 / `null` | 本次证据覆盖的验证范围；`null` = 未知 |

  UI 只消费这些字段，**不得**从 `idle`、颜色或历史审计结论推断能力；未知一律显示「未知」。
  `idle` 只表示「本次尚未开始」，不表示「未实现」。

  **工作窗口一致消费（F02-c）**：Agent 工作窗口对选中节点展示**同一服务端** `capabilities`
  （`GET /api/runs/{run_id}/agents/{node}` 响应字段，由 `agent_view` 的同一实现投影），
  格式化与角色卡共用唯一实现（前端 `run-view-state` 之外的 `capabilities` 格式化模块，不各写一套）。
  未知维度（`null`）显示「未知」；`idle`/`standin` 不得显示成「真实」或「已完成」。
  旧页面（`legacy.html`）不含角色卡，不新增能力结论，也不得出现过期能力文案。

### 4.4 右列

1. **闸门卡**（仅 `pending_interrupt.type=gate_decision` 时）：标题（闸门名/轮次）、材料摘要、`gate_options`（服务端下发）、actor 输入（默认 `human:`）、理由、提交按钮（提交中禁用、防双击）。被拒时展示 `detail.blockers` 原文。
   **G1 的 N2 差异清单必须逐条可见**（2026-10-20 补）：渲染 `pending_interrupt.payload.difference_items.entries`
   的 `entry_id / kind / change / segment / offset / lines / unresolved / evidence`，未决条目高亮并在
   顶部列出 chip；闸门视图完整展开，运行视图右列闸门卡提供同名可折叠块。材料仍全部来自服务端，
   前端不判定、不排序、不隐藏。
   **G1 材料必须可判（2026-10-22 增补，[SPEC-REV-01](SPEC-REV-01-20261022.md) R2）**：每条差异必须展示
   `before` / `after` **双栏对照**；`diff_hunk` 非空时按行渲染并标行号；`doc_entry` 先列**变化字段**
   （before→after），其余字段折叠为"未变（N 项）"；`rtl_file` 无文本 hunk 时必须显示**原因**
   （编码 / 二进制 / 夹具）与可替代的行号证据。非 UTF-8 源文件必须显示 `encoding`（如 `gbk`）与
   "解码后对比"标注。drill / 夹具条目必须带 `drill_fixture` 徽标。材料另需给出 `n3_digest.md`
   与 Host 留痕（如夹具的 `mock_change_applied.json`）入口（存在性探测）。
   **逐条处置界面输入通道（2026-10-23 增补，取代 v1 的"走 API"兜底）**：当
   `pending_interrupt.payload.entry_decisions_required === true` 时，闸门视图必须为**每个唯一
   `entry_id`** 渲染一组处置控件（选项一律取服务端下发的 `decision_options`，前端不得手抄枚举）
   与理由输入（`ignored` / `disputed` 必填）；提交 payload 必须带 `entry_decisions` 覆盖**全部**
   条目。整门决策由逐条处置**推导**：存在 `disputed` ⇒ `disputed`；否则存在 `ignored` ⇒ `ignored`；
   否则 `confirmed`。推导值与手选值不一致时必须就地提示，最终以服务端拒绝为准。
   材料不足以生成控件时，仍须显式提示"该门需走 API"并给出可复制样例，**不得让人盲签**。
   **与节点面板共用草稿（2026-10-23 增补）**：闸门节点面板的二级差异清单（§4.2.2）与本卡使用**同一份**
   `gate-session` 草稿（同一 `run_id + gate + cycle` 身份）；面板只写草稿、不发 POST，
   提交入口仍只有本卡的提交按钮——避免两套提交与两套判据。
   **G2 报告全文一次点击（2026-10-23 裁决 #8）**：材料区的「查看报告全文」直接打开**公共报告浮窗**
   （`window.ReportViewer`，与 N12 面板同一实现、同一白名单端点 §6.8），不再先跳 N12 面板再点一次。
   G2/G3 的"待确认项"是只读清单（§4.2.2），不进入本卡的逐条处置控件。
2. **双口径计数**：口径一 / 口径二**并列同权**，原值显示，不换算；附「两者都归零才可判绿」说明。
3. **阻断项**：按 `severity` 分区（hard / info），code + 一句话说明；不做前端过滤。
4. **证据概况 / 长任务**：job 状态、log_tail（折叠、等宽、只读）；证据入口先探测存在性。
5. **事件流**：折叠；只显示白名单 `kind`；`seq` 递增；不把 raw parser 路径暴露给前端（只显示 `refs`）。

### 4.5 环境来源（S0）徽标

> 来源：[SPEC-REV-01](SPEC-REV-01-20261022.md) R5。S0 能力与验收见 [SPEC-05](S0_ENVIRONMENT_SPEC.md) §6。

- 运行视图顶部必须显示该 run 的**环境来源**：`S0 记录 <id>`（输入目录来自 S0 派生副本）或
  `未经 S0 派生`（现有闭环）。
- 数据来自 run 文档的 `s0_record_id`（可空）；为空时显示"未经 S0 派生"，**不得**显示为"环境就绪"。
- drill 运行必须同时显示 `mode=drill`，来源徽标显示"未经 S0 派生（drill 不覆盖 S0）"。
- 边界：徽标只是只读投影，不证明 S0-b 或环境可用。

---

## 5 闸门视图

- 触发：`pending_interrupt` 存在，或用户手动进入。
- 内容：闸门材料（差异清单/冲突快照/报告+用例态/评估结论，按闸门不同）、权威枚举、当前轮次、未决计数。
- 操作：选择决策 → 填 actor（必须 `human` 前缀）→ 理由（`ignored/rework/disputed` 必填）→ 提交。
- **G1 逐条处置（2026-10-23 增补）**：`entry_decisions_required=true` 时先逐条选择
  （每个唯一 `entry_id` 一组控件），再提交；整门决策由逐条处置推导（§4.4），界面不得用一句
  attestation 代替逐条核对。
- 提交路径：`POST /api/runs/{run_id}/gates/{gate_id}/decision`；成功后回到运行视图并刷新。
- 被拒（403）：显示服务端 `detail.error` + `blockers`，**不消耗中断**的说明如实展示。
- 执行停放说明：顶部固定一句「执行处于 interrupt，可安全重启；闸门态权威在 `gates.json`」。
- **材料可判性（[SPEC-REV-01](SPEC-REV-01-20261022.md) R2）**：闸门视图与右列闸门卡使用**同一份**服务端材料；
  G1 逐条展示 before/after、diff_hunk、encoding、未决原因与 `drill_fixture` 徽标；材料不足以判断时
  必须显式提示（"材料不足以判断：缺 X"），不提供"直接确认"的诱导。
- **入口**：材料区提供 N3 摘要与 Host 留痕入口（存在性探测）；未生成时显示"未生成"而不是空白。

---

## 6 API 契约（新增 / 扩展）

> 所有新增端点只读、只返回投影，不改变业务权威。错误一律 `4xx + detail.error`，不返回空数组冒充成功。

### 6.1 `GET /api/baselines`

```json
{
  "baselines": [
    {"id": "v0", "created_at": "2026-10-15T12:05:00+0800", "parent": null,
     "cases": 162, "rtl_snapshot_bytes": 2570240, "valid": true,
     "missing": [], "errors": []}
  ],
  "workspace_root": ".../kb"
}
```

- 来源：`<WORKSPACE_ROOT>/baselines/*/manifest.json`；`valid` 的**唯一判据**见编排规格 §3.1（manifest schema +
  身份一致 + 七件套指纹 + parent 链），实现只有 `loop/host/baseline.py` 一处；本端点复用同一函数。
- 坏件不抛 500：`valid=false` 并在 `missing`（缺失件）/`errors`（schema·身份·指纹·链）给出原因。
- 只列**基线号形状**（`^v[0-9]+$`）的条目；符号链接基线**列入但 `valid=false`**，不静默跳过；
  `.staging-*` 等非基线目录不列。

### 6.2 `GET /api/env/check?path=<abs>`

```json
{
  "path": "/…/SimEnv_TCS9620…",
  "ok": true,
  "registered": true,
  "env_id": "simenv-tcs9620-64ch",
  "plugin_missing": [],
  "workspace_missing": [],
  "counts": {"rtl_files": 1210, "cases": 162},
  "writable": {"frozen": false, "sim_workdir": true},
  "warnings": [],
  "matches_current_process": true
}
```

- `matches_current_process=false` ⇒ 前端显示「需以该环境重启服务」，确认按钮禁用（见 §4.3 硬约束）。
- 路径必须存在且为目录；否则 `400`。
- 只读探测：不创建目录、不写文件。

### 6.3 `GET /api/fs/dirs?path=<abs>`

```json
{
  "path": "/home/work/chenjunming",
  "parent": "/home/work",
  "roots": ["/home/work/chenjunming"],
  "entries": [
    {"name": "FPGA_SIM", "is_env": false, "markers": []},
    {"name": "SimEnv_TCS9620…", "is_env": true, "markers": ["uvs.setup", "RTL/", "TESTLIB/"]}
  ]
}
```

- 允许根（allowlist）：`environments.json` 中每个环境的 `path`、其父目录与祖父目录；`<WORKSPACE_ROOT>/baselines`；可选 `SETTINGS.yaml` 的 `loop.ui.browse_roots`（显式配置时覆盖默认）。
- 越界（`realpath` 不在允许根下）⇒ `403`；符号链接解析后校验。
- 只返回目录名与**文件名标记**（`uvs.setup`、`manifest.json`），不读文件内容。

### 6.4 `POST /api/runs` 扩展

请求新增 `project`（绝对路径，缺省 = 当前 `ENV_ROOT`）：

```json
{"baseline": "v0", "project": "/…/SimEnv_TCS9620…", "mode": "drill", "scenario": "happy", "now": null}
```

- 校验：`project` 必须等于**当前进程解析的 `ENV_ROOT`**；否则 `400`（理由：三根在进程启动时解析，跨环境需重启；不得静默切换）。
- `mode=real` 时 `baseline` 必须存在且 `valid`（判据见编排规格 §3.1），准入发生在**建运行目录/写事件/申请单槽之前**，
  否则 `400` 且零副作用；`mode=drill` 不读基线资产、不做准入，但不得据此声称基线已验证。
- 基线无效时 `detail` 必须结构化：`{error, baseline, missing[], errors[]}`（`missing` = 缺失件，
  `errors` = schema/身份/指纹/parent 链违规）。**UI 必须展示 `missing` 与 `errors`**（不得只显示 `error` 字符串），
  列表项的 `missing`/`errors` 也在配置视图展示（§6.1）。
- 返回沿用 `{run_id, mode, scenario, created_at}`，并新增 `project`。

### 6.5 `GET /api/runs/{run_id}` 扩展

新增字段：

```json
{
  "project": "/…/SimEnv_TCS9620…",
  "agents": [
    {"role": "analyst", "name": "simenv-analyst", "nodes": ["N3"],
     "status": "done", "last_action": "node_finished(ok)", "elapsed_s": 12,
     "summary": "3 组 / 27 条差异摘要", "mode": "live",
     "evidence": ["n3_digest.md"], "note": null}
  ],
  "stage_map": [{"key": "ingest", "name": "摄取", "nodes": ["N0","N1","N2","N3","N4"]}]
}
```

- `agents` 是**投影**（自报事件派生），响应里带 `"authority": "projection"`。
- `stage_map` 由服务端下发，前端不手抄节点分组（避免两侧漂移）。

### 6.6 不变量

- 现有端点与字段**只增不改**；旧前端（`legacy.html`）仍可用。
- `gate_options`、`blockers`、`counts` 仍由服务端计算与下发；前端不参与判定。
- 所有新端点不写任何文件；`POST /api/runs` 是唯一建运行入口，闸门决策是唯一业务写动作。

---

### 6.7 `GET /api/runs/{run_id}/nodes/{node}`（节点详情，只读）

> 供 §4.2.1 节点详情面板使用；数据契约见 [SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4。

```json
{
  "run_id": "RUN-…", "node": "N1", "known": true, "name": "输入摄取", "owner": "Host",
  "status": "ok", "started_at": 1792650932.891, "finished_at": 1792650932.892,
  "source": "drill_fixture",
  "summary": "N1：v0→v1，manifest 已产出",
  "detail": {"artifact": "…/n1_manifest_new.json", "parent": "v0", "source": "drill_fixture"},
  "refs": ["…/n1_manifest_new.json"],
  "refs_omitted": 0,
  "events": [{"seq": 4, "kind": "node_started", "status": "running", "ts": 1792650932.891,
               "refs": [], "refs_omitted": 0}],
  "missing_fields": ["manifest_entries"],
  "authority": "projection",
  "run_status": "finished", "run_terminal": true, "node_started_present": true,
  "report": null,
  "gate": null,
  "story": {
    "purpose": "给当前代码和文档拍一张快照：多少文件、什么指纹、哪些用例，作为对比起点。",
    "headline": "快照完成：3374 个文件，冻结 162 个用例。",
    "headline_source": "template",
    "note": null,
    "not_reached": false,
    "not_executed": false,
    "evidence_note": null,
    "status_note": "通过",
    "status_glossary": {"ok": "通过", "fail": "未通过", "live": "真实模型调用"},
    "gate": null,
    "observation_points": null,
    "evidence_groups": null,
    "evidence_groups_note": null,
    "steps": [
      {"seq": 4, "at": 1792650932.891, "kind": "node_started", "status": "running", "text": "开始执行"},
      {"seq": 5, "at": 1792650932.892, "kind": "node_finished", "status": "ok", "text": "结束，状态 ok"}
    ],
    "key_results": [
      {"field": "manifest.allfiles_entries", "label": "快照文件数", "value": 3374, "text": "3374", "missing": false},
      {"field": "manifest.cases_frozen", "label": "冻结用例数", "value": 162, "text": "162", "missing": false}
    ]
  }
}
```

- **`story` 是展示投影（SPEC-REV-04 R1）**：`purpose` 来自服务端节点目录；`headline` 由服务端按节点模板
  从已有 `detail` 字段确定性生成（`summary` 原文移入面板「原始记录」）；`note` 是首屏黄条；`steps` 由该节点
  事件按 `kind` 白名单确定性生成（缺字段写"未下发/原因未下发"，不推断）；`key_results` 按 §4.2.1 逐节点清单
  取值（缺失项 `missing=true`、`text="未下发"`）。**界面直接渲染，不自行拼装**；`story` 不含业务判定，
  不改变 `summary` / `detail` / `events` 的原始语义。
- **`story` 第三轮新增字段（2026-10-23，只增不改）**：
  - `observation_points`（仅 N6）：`detail.observation_points` 的确定性透传，
    `[{case, marker, addr, offset, expected_value}]`；`null` = 未下发（旧 run / drill / standin）；
    `[]` = 下发了但 0 条（不冒充未下发）。
  - `evidence_groups` / `evidence_groups_note`（N7/N9）：证据按用例分组，
    `[{case, refs, note}]`；组内 `refs` 为空 ⇒ `note` 说明（如"本轮未执行/无证据"）；
    用例名不可知或没有一条 ref 可归属 ⇒ `[]` + `evidence_groups_note` 说明原因；
    其余节点为 `null`（前端维持平铺 `refs`）。分组只用服务端已下发的用例名，**不推断、不补名字**。
  - `headline_source` 必须有授权消费者：`summary`/`missing` ⇒ 结果标题后小字附注（见 §4.2.1）。
- **新增只读字段**：`run_status` / `run_terminal`（P-30 未到达态）、`node_started_present`（P-33）、
  `report`（仅 N12，P-28）、`gate`（仅 N4/N13/N14，P-17/P-18，形状见 [SPEC-02](LOOP_ORCHESTRATION_SPEC.md) §10.4.2：
  G1 用 `entries` 逐条处置；G2/G3 用 `items` 只读清单，`gate.state` 含 `read_only`）。
  只增不改；历史 run 为新字段缺失时按"未下发/不适用"显示，**不回填**。
- 未知 node：返回 200 + `{"known": false, …}` 空投影（`story.purpose=null`、`key_results=[]`），**不**用 404 冒充"节点不存在"。
- 只读：不写盘；`refs` 只给 run 目录内路径；**不返回文件内容**（唯一例外 = §6.8 的报告只读端点）。`refs` 取自事件流顶层
  （`node_history` 不含 `refs`），由本端点合并展示；目录外引用（如作业日志）只以
  `refs_omitted` 计数呈现，**不给路径**。
- 同一引用边界也适用于 `events[].refs`：逐条事件复用顶层 `refs` 的目录判据，
  每条事件以 `refs_omitted` 记录被省略的引用条数；事件顺序和其他字段不变，原始事件不改写。
- 字段缺失必须列进 `missing_fields`；前端显示"未下发"，不猜、不补默认值；历史 run 不回填。
- 端点实现前，前端可先从 `GET /api/runs/{run_id}` 的 `node_history` + `/events` 拼同一投影，但契约字段一致。

### 6.8 `GET /api/runs/{run_id}/report`（报告全文，只读；P-28）

> 用途：G2 验收报告时，人必须能读到**本 run 的**报告正文（此前材料只给路径+存在性）。

```json
{"run_id": "RUN-…", "file": "n12_report.md", "path": "…/RUN-…/n12_report.md",
 "bytes": 12345, "truncated": false, "content": "# 本轮评估报告\n…", "authority": "projection"}
```

- **白名单写死**：只允许 `n12_report.md`；`?path=` 只接受该值，其余一律 403（**不开放任意路径**）。
- **不越出 run 目录**：解析后必须落在该 run 的目录内（符号链接逃逸一律 403）。
- **大小上限**：512 KiB；超出即截断并标 `truncated=true`（不报 500、不落盘缓存）。
- 缺失 ⇒ 404；未知 run ⇒ 404；只读、不写盘、不改 run 状态。
- 节点详情里的 `report` 块只给 `{file, available, bytes}`，**不给正文**（正文只在本端点）。

### 6.9 `GET /api/runs/{run_id}/stream`（SSE 运行投影流；2026-10-24，SPEC-REV-07 U2-a）

> 用途：把"运行详情感知"从轮询节拍改为服务端推送。**只是传输层**：推送内容 = 既有
> `GET /api/runs/{run_id}` 同源投影（`RunManager.run_view` 唯一产出），本端点不构造第二份判据、
> 不新增事件 kind（SPEC-02 白名单不变）、不写任何文件。

- `media_type=text/event-stream`；帧格式 `event: run_view` + `data: <JSON>`，**仅投影变化时推送**。
  变更检测用「排除 `updated_at` 等易变字段后的规范化 JSON 签名」；签名不变不推（`updated_at`
  每次投影刷新都会变，不得用它当变化信号）。约每 15 s 发一行 `: ping` 注释帧保活。
- 投影里的 `job.log_tail` 随 `run_view` 一并在变化时更新（长作业日志尾巴的推送即此实现）；
  独立的逐行日志流不在本节范围。
- 未知 `run_id` ⇒ 404（建立连接前）；流建立后 run 消失 ⇒ `event: gone` 后正常结束，不断开重连。
- 客户端断开 ⇒ 服务端生成器立即结束（无泄漏）；单连接单用户，不做广播/多路复用。
- 心跳节拍与签名口径的实现唯一在 `loop/services/run_stream.py`；路由层（api.py）只做 404 准入与
  StreamingResponse 包装。旧历史/旧前端不受影响：本端点纯新增，`GET /api/runs/{run_id}` 原样保留。

### 6.10 `GET /api/runs/{run_id}/agents/{node}/stream`（SSE Agent 窗口流；2026-10-24，SPEC-REV-07 U2-b）

> 用途：Agent 工作窗口的读取从 1.5 s 轮询改为推送。传输/心跳/变更检测**复用 §6.9 全部口径**
> （`loop/services/run_stream.py` 同一实现，事件名为 `agent_view`）；本节只登记差异。

- 推送内容 = `GET /api/runs/{run_id}/agents/{node}` 的**同一装配**（read_view + 节点事件 +
  capabilities + context_budget；装配函数唯一，两条路由共用，口径同源——红线 8）。
- `?attempt=` 语义与 GET 相同；`attempt` 变化由客户端**重建流**（新 URL），不在流内切换。
- 建立连接前按 GET 同口径预验证一次（未知 run/node ⇒ 404；坏记录/坏尝试 ⇒ 422）；
  流建立后记录损坏 ⇒ 生成器异常结束、连接断开，客户端回退轮询，由 GET 的 422 暴露真实错误。
- 控制 POST（SPEC-07）零改动：窗口的控制命令仍走 `/control`，不经流上行。

## 7 状态、刷新与错误

| 场景 | 行为 |
|---|---|
| 轮询 | 运行视图 1.5 s/次；`document.hidden` 时降为 10 s；切回立即刷新 |
| 加载 | 骨架/「加载中」，禁止把空数组显示成「无数据」 |
| 断连 | 顶部红色横幅 + 最后成功时间；恢复后自动消失 |
| 空态 | 无运行 → 左栏空态引导「新建运行」；无证据 → 显式「证据缺失（E-2）」 |
| 失败 | `status=failed` 显示 `error` + `notes`；`node_failed` 在流程条标红 |
| 提交中 | 按钮禁用 + spinner；重复点击不产生第二次请求（前端幂等键同 `resume_request_id` 语义） |

### 7.1 运行切换与闸门会话（2026-10-21 增补）

本节细化 §7 的异步交互边界，不新增业务决策。执行权威、闸门选项和拒绝原因仍来自服务端。

- **选择隔离**：点击运行记录立即显示所选运行的加载态并移除上一运行的操作表单；仅当前选择的最新详情请求可更新页面。快速 A→B→A、轮询与点击交错时，旧响应（包括错误）不得覆盖当前详情、导航或提示。
- **草稿身份**：草稿与表单以 `run_id + interrupt.id + gate + cycle` 联合标识。相同身份轮询保留选项、actor、理由、输入焦点；运行或中断身份改变时清空草稿，禁止继承旧选择。
- **双视图一致**：执行视图和闸门视图共享同一身份的草稿；切换视图后显示相同选项、actor、理由，不因同步重建输入节点。
- **提交隔离**：POST 固定发往点击提交时的运行与闸门；同一身份提交期间禁止再次发出 POST，切走再返回也保持提交中。切换运行后，旧提交的成功或失败不得清空新草稿、切换新页面或显示旧错误。
- **拒绝可恢复**：当前会话收到服务端拒绝时，保留输入并展示其 error、blockers、note，解除提交中状态。没有服务端确认不得显示“已通过”。
- **过期选项**：只允许提交当前服务端选项中存在的值；刷新撤回的选项不得继续发出 POST。是否授权仍由服务端判定。
- **实现归属（F05）**：会话协调 owner 只有 `app.js`（持有草稿/提交台账/选择代次）；
  草稿身份、撤回选项清空、提交互斥这些**判定**的唯一实现在纯函数模块 `gate-session.js`，
  app.js 只消费。模块不读全局、不写 DOM、不发请求。

验收以真实浏览器点击、输入、延迟响应与拒绝响应为准；检查源码字符串不能替代交互验收。

### 7.2 首次加载、首次失败与刷新失败（2026-10-21 F13）

运行详情是**请求展示状态**，不是新增工作流业务状态。服务端不下发新字段；以下五种情况由
「当前选择是否有最近一次成功数据（`viewData`）」「当前请求代次的错误（`viewError`）」和
「是否有在途请求」共同判定，唯一实现为前端纯函数模块 run-view-state.js（`loop/web/`，app.js 只消费）：

| 可观察情况 | 判定 | 顶栏状态 | 提示 |
|---|---|---|---|
| 加载中 | 无成功数据、无错误、有在途请求 | 「加载中…」 | 不显示错误横幅，不声称已有数据 |
| 尚未读取（idle） | 无成功数据、无错误、无在途请求 | 「尚未读取」 | 不显示错误横幅；仅在页面尚未发起读取时的过渡态，不得伪装成加载中 |
| 尚无数据且读取失败（首次失败） | 无成功数据、有错误 | 「读取失败」 | 「读取运行视图失败：<error>（尚无成功读取的数据）」+「重新读取」入口 |
| 已加载 | 有成功数据、无错误 | 服务端 `status` | 无错误横幅 |
| 已有数据但刷新失败（陈旧） | 有成功数据、有错误 | 服务端 `status`（数据保留） | 「…（数据已过期；上次成功 HH:MM:SS）」+「重新读取」入口；不得再显示「加载中」 |
| 恢复 | 新请求成功 | 服务端 `status` | 错误横幅消失；上次成功时间更新 |

约束：

1. **数据归属**：`viewData` 与「上次成功时间」属于**当前选择**；切换运行（或 A→B→A）立即清空，
   新选择不得复用上一运行的成功数据或成功时间。仅有当前代次（runId + selectionEpoch + detailRequest）的
   回包可更新数据、错误与成功时间；旧回包（成功或失败）一律丢弃。
2. **不重建表单**：重新读取只更新数据与提示，不重建闸门表单、不丢草稿、不移动焦点（沿用 §7.1 草稿身份）。
3. **可重试**：首次失败与陈旧失败都必须提供可达的「重新读取」入口；恢复后入口消失。
4. **不得伪装**：没有成功数据时不得出现「最近一次成功的数据」「上次成功」措辞；有成功数据时不得让失败看起来像加载中。
5. **启动请求超时 ≠ 未创建（2026-10-23 增补）**：`POST /api/runs` 在 `real` 模式下同步执行
   N0–N3（真实模型，可能数分钟），客户端超时只表示**客户端先断开**。超时后界面必须按
   `GET /api/runs` 核对是否已有新建 run：有则直接接入并提示「已在服务端启动（客户端超时，已自动接入）」，
   无（或核对窗口内始终没有）才显示启动失败；**不得**把已创建的 run 报成失败、也不得重复提交同一个启动。

### 7.3 传输与降级：SSE 优先、轮询兜底（2026-10-24，SPEC-REV-07 U2-a）

§7 表中「轮询」行为不变，但当前选择的运行详情**优先走 §6.9 的 SSE 流**：

| 流状态 | 行为 |
|---|---|
| 实时（open） | 详情更新由推送驱动；主轮询循环**跳过**运行详情请求（运行列表/健康检查照常轮询） |
| 连接中（connecting） | 首次打开的过渡态；主轮询照常拉详情（宁可多拉一拍，不出现空窗） |
| 轮询回退（fallback） | 流断开（含服务重启、`gone`）；**立即回到 §7 既有轮询行为，与现状逐字一致**；之后按固定间隔重试建流 |
| —（无选择/不支持） | 不建流；轮询即唯一通道。浏览器不支持 `EventSource` ⇒ 直接轮询，不报错 |

Agent 工作窗口（§6.10）同口径：连接中/回退 ⇒ 窗口保持既有 1.5 s 轮询；实时（open）⇒ 停轮询、
仅推送更新渲染（同一代次/身份守卫）；窗口关闭或切换节点/尝试 ⇒ 停流停轮询并按新身份重建。

约束：**不双通道并发写**——`open` 态只有推送会更新 `viewData`，回退态只有轮询会；两路更新都遵守
§7.1 的选择隔离与 §7.2 的代次判定（旧推送不得覆盖新选择）。流状态在运行视图以小徽标外显
（实时/轮询回退），**不作为业务状态**：判定、草稿、提交均不读它。U1 的等待提醒仍以运行列表轮询
为数据源，不受本节影响。


---

## 8 安全与边界

1. **只绑 `127.0.0.1`**：远程通过 SSH 隧道（见 `loop/remote/README.md`）；界面无鉴权。
2. **目录浏览 allowlist**：见 §6.3；拒绝 `..`、符号链接逃逸、非目录。
3. **不读文件内容**：`/api/fs/dirs` 只返回名字与标记；证据读取仍走既有 `evidence` 端点。
4. **XSS**：所有服务端字符串用 `textContent` 渲染；禁止把 `error`/`notes` 直接拼进 `innerHTML`。
5. **无外链**：不引 CDN/字体/图标库；颜色/图标用内联 CSS。
6. **不泄露密钥**：沿用 `/api/health` 的脱敏字段。

---

## 9 前端工程

| 项 | 决定 |
|---|---|
| 文件 | `loop/web/` 下拆为 `index.html` + `app.js` + `app.css`（P3 新增；零外部依赖，无构建步骤）；旧界面保留为 `legacy.html` 一个迭代 |
| 渲染 | 单向：`state → render(view)`；无框架；每 1.5 s 拉一次 `run_view` 全量重绘小面板 |
| 组件 | `Sidebar` / `SetupView` / `RunView` / `GateView` / `StageAccordion` / `AgentCard` / `DirPicker` / `Toast` / `Banner` |
| 设计基线 | `loop/web/mockup.html`（样式与布局参考，可逐步替换为真实组件） |
| 可访问性 | 键盘可达（按钮/输入原生元素）、颜色不作为唯一状态信号（配文字） |

---

## 10 验收判据（可判定）

| # | 判据 | 判定方式 |
|---|---|---|
| A1 | `/api/baselines` 返回 v0，字段与目录一致 | 单测 + `curl` 对比 manifest |
| A2 | `/api/env/check` 对不存在/非目录 fail closed；对当前 ENV_ROOT `ok=true` | 单测 |
| A3 | `/api/fs/dirs` 越界返回 403；允许根内只返回目录 | 单测（含符号链接用例） |
| A4 | `POST /api/runs` 带 `project` 创建成功；`run_view.project` 回显；跨环境 `400` | 单测 |
| A5 | `run_view.agents` 在 drill 全链路下 6 角色状态随事件变化（含 failed 分支） | 单测 + 终验相 |
| A6 | 闸门提交仍走服务端权威；被拒时返回 blockers 且不消耗中断 | 沿用现有测试 + 界面手测 |
| A7 | `/legacy.html` 仍可访问且旧接口未破坏 | 冒烟测试 |
| A8 | 页面无外部链接；关键元素 id 存在；`GET /` 200 | 冒烟测试（HTML 解析） |
| A9 | 每张 agent 卡带 `capabilities` 四维（未知为 `null`）；idle 不显示「未实现」；`standin`/`real` 如实区分 | 单测（`test_agent_view.py`）+ 浏览器用例（需 Chromium） |

---

## 11 实施拆分（供后续 plan）

1. **P1 后端只读 API**：`/api/baselines`、`/api/env/check`、`/api/fs/dirs` + allowlist + 单测。
2. **P2 投影扩展**：`run_view.project` / `agents` / `stage_map` + 单测；`POST /api/runs` 收 `project`。v1 不细化 `waiting_job/waiting_slot`（审计 I18 另修）。
3. **P3 前端骨架**：文件拆分、左栏、三视图切换、轮询/横幅/空态；`legacy.html` 保留。
4. **P4 配置视图**：基线列表、目录浏览器（基线与项目）、校验与确认条。
5. **P5 运行/闸门视图**：四段折叠、agent 卡、右列、闸门表单。
6. **P6 验收与文档**：A1–A8、更新 `loop/README.md` 与 `doc/OVERVIEW.md` 截图/说明。

> 每步遵循 TDD（先失败用例再实现）；不修改业务语义；发现契约缺口只登记。

---

## 12 后续迭代（v1 不做）

- SSE/WebSocket 实时推送、日志流内嵌。
- 跨环境运行时切换（需先把 `ENV_ROOT` 从进程常量改为 per-run 注入；见审计 A19 同族）。
- 证据内嵌预览（PDF/日志高亮）、报告 diff。
- 多用户/鉴权/审计日志、移动端。
- agent 卡的「详细模式」（输入摘要、校验问题、重试次数、输出全文）。
- N11 证据守护 / N6 沙箱 / real 链路的实现（属代码缺陷修复轮，见审计 §6）。


---

## 13 实现状态与差异登记（2026-10-19）

**已实现**：`loop/web/index.html` + `app.js` + `app.css`（两区运营台）、`legacy.html`（旧界面存档）、
三个只读端点（`/api/baselines`、`/api/env/check`、`/api/fs/dirs`）、`POST /api/runs` 的 `project`、
`run_view.agents/stage_map/project`；冒烟与契约测试见 `loop/tests/test_web_smoke.py`、
`test_config_api.py`、`test_agent_view.py`、`test_api_ui_contract.py`。

**与规格的差异（v1 接受，登记而非隐藏）**：

1. **证据「打开」只做存在性探测**：后端没有内容读取端点，点击证据 = `GET …/evidence/exists` + toast（缺失显示 E-2 原文）。
2. **内部节点显式列出**：`node_history` 里 `N3_request`/`N6_model`/`HALT` 等内部节点不隐藏，列在四段下方的「未纳入四段展示的节点」区；是否在后端投影层吸收属后续迭代。
3. **agent 摘要**取产物第一行正文（最长 120 字符），不做换行裁剪与富文本。
4. **状态细分**仍统一为 `waiting_gate`（审计 I18），tooltip 说明可能是作业/单槽等待。
5. **`app.js` 约 2.4k 行**（单文件、无构建）；后续可在不引入构建步骤的前提下按视图拆分模块。
6. **N11 能力展示（F02）**：N11 已有成链判断/返工实现；卡片按 §4.3 的 `capabilities` 四维如实展示，
   不得再显示「未实现」，也不得把 `standin` 或未开始的运行说成已完成证据守护。
7. **G1 差异清单逐条渲染（2026-10-20 补）**：闸门材料消费 `difference_items`（含未决标记、evidence、行号/offset），
   消除"界面看不到条目却要求逐条确认"的缺口；回归见 `test_web_smoke.py::test_gate_material_script_renders_n2_diff_entries`
   与 `test_api_ui_contract.py::test_gate_material_projection_has_diff_entries`。

## 14 全站网页视觉系统（2026-10-21）

用户选择“专业清爽”，并澄清仅需现有浏览器网页，不开发桌面客户端或手机端专项适配。本轮覆盖环境准备、运行配置、运行监控、人工闸门、Agent 工作窗口、目录浏览器和旧界面；静态历史样张不重绘。UI 实现者是视觉与展示元数据的唯一 owner；业务状态、准出、闸门授权仍由既有 Host/API 负责。

- **框架**：固定深墨色工作侧栏，顶部轻量服务状态栏，雾白工作区与青绿主操作色。四个页面入口集中在侧栏，选中页有文字、背景和标记。主区保留清晰页标题、用途描述和视图编号。提供跳到主内容的键盘入口。
- **层次**：页标题、卡片标题、正文、辅助说明使用稳定字号阶梯；主要正文 13–14px、主要表单 13–14px、说明文字 12px，标签与图示注释允许更紧凑。等宽字体仅用于路径、身份、计数与日志。状态保留文字，成功、阻断、失败使用统一语义色。
- **组件**：共享配色令牌、按钮、焦点环、卡片、分隔、输入、选择项、空态、通知；S0 的流程卡与检查回执、运行阶段与 Agent 卡、人工闸门的材料/操作两栏、Agent 窗口及旧界面采用同一系统。现有未实现提示和阻断保持可见。
- **桌面布局**：验收宽度 1280/1440/1920，主区不产生页面水平溢出；宽屏使用有效分栏，1280 下侧栏和关键表单仍可用，长路径/错误换行，日志局部滚动。移动端不作为本轮设计和验收目标，原有窄屏兼容保留。
- **交互不变量**：不改变请求形状、轮询、运行选择、草稿身份或后端判据；切页不提交写操作，轮询保留输入和焦点；主操作禁用/提交中/被拒状态继续生效。目录选择与 Agent 打开/关闭支持键盘。
- **资产**：所有字体、装饰和图标本地化，无 CDN、外部字体或运行时依赖；旧界面提供返回主工作台入口。

验收先运行现有浏览器特征基线，再验证三种桌面宽度下各页、目录选择器和 Agent 窗口的可用性、溢出及关键操作，并保存桌面截图做视觉检查。静态资源 HTTP 冒烟一并执行。仅视觉改动不替代完整业务四道门；未运行项在 STATUS 明示。
