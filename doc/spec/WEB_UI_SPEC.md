# Web UI 规格（v1 · 运营台）

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

### 4.4 右列

1. **闸门卡**（仅 `pending_interrupt.type=gate_decision` 时）：标题（闸门名/轮次）、材料摘要、`gate_options`（服务端下发）、actor 输入（默认 `human:`）、理由、提交按钮（提交中禁用、防双击）。被拒时展示 `detail.blockers` 原文。
   **G1 的 N2 差异清单必须逐条可见**（2026-10-20 补）：渲染 `pending_interrupt.payload.difference_items.entries`
   的 `entry_id / kind / change / segment / offset / lines / unresolved / evidence`，未决条目高亮并在
   顶部列出 chip；闸门视图完整展开，运行视图右列闸门卡提供同名可折叠块。材料仍全部来自服务端，
   前端不判定、不排序、不隐藏。
2. **双口径计数**：口径一 / 口径二**并列同权**，原值显示，不换算；附「两者都归零才可判绿」说明。
3. **阻断项**：按 `severity` 分区（hard / info），code + 一句话说明；不做前端过滤。
4. **证据概况 / 长任务**：job 状态、log_tail（折叠、等宽、只读）；证据入口先探测存在性。
5. **事件流**：折叠；只显示白名单 `kind`；`seq` 递增；不把 raw parser 路径暴露给前端（只显示 `refs`）。

---

## 5 闸门视图

- 触发：`pending_interrupt` 存在，或用户手动进入。
- 内容：闸门材料（差异清单/冲突快照/报告+用例态/评估结论，按闸门不同）、权威枚举、当前轮次、未决计数。
- 操作：选择决策 → 填 actor（必须 `human` 前缀）→ 理由（`ignored/rework/disputed` 必填）→ 提交。
- 提交路径：`POST /api/runs/{run_id}/gates/{gate_id}/decision`；成功后回到运行视图并刷新。
- 被拒（403）：显示服务端 `detail.error` + `blockers`，**不消耗中断**的说明如实展示。
- 执行停放说明：顶部固定一句「执行处于 interrupt，可安全重启；闸门态权威在 `gates.json`」。

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

验收以真实浏览器点击、输入、延迟响应与拒绝响应为准；检查源码字符串不能替代交互验收。

### 7.2 首次加载、首次失败与刷新失败（2026-10-21 F13）

运行详情是**请求展示状态**，不是新增工作流业务状态。服务端不下发新字段；以下五种情况由
「当前选择是否有最近一次成功数据（`viewData`）」「当前请求代次的错误（`viewError`）」和
「是否有在途请求」共同判定，唯一实现为前端纯函数模块 run-view-state.js（`loop/web/`，app.js 只消费）：

| 可观察情况 | 判定 | 顶栏状态 | 提示 |
|---|---|---|---|
| 加载中 | 无成功数据、无错误、有在途请求 | 「加载中…」 | 不显示错误横幅，不声称已有数据 |
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
