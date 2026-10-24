# UI 交互与等待期体验：实施计划与设计详案（未排期部分）

日期：2026-10-24。依据：[SPEC-REV-07](../spec/SPEC-REV-07-20261024.md)。
状态：**提案配套计划；顺序 1–4 与顺序 5（U2-b，先修订 SPEC-04 §6.10）、顺序 9（U5）已于 2026-10-24 实施**（断言 25/25、8/8+9/9、12/12；pytest/browser/内网终验未运行，实测见 [STATUS §59](../STATUS.md)–[§61](../STATUS.md)）；顺序 6（U2-c 独立日志流）后置——`job.log_tail` 已随 run_view 推送；顺序 7（U3，须与 F05-b/c 合并）、顺序 8（U4）、顺序 10（U6）未评审、未实施、未排期，**设计详案见本文 §A–§D**。本轮不变更写权、拓扑、闸门/记忆契约与环境资产。

| 顺序 | 切片 | 落点 / owner | 前置 | 验证门 |
|---|---|---|---|---|
| 1 | U1-a 通知 + 标题闪烁 | `loop/web/`（app.js 轮询消费处）；实现 owner | 无契约变更 | browser 特征测试：状态跃迁触发通知、权限拒绝降级可见；现有轮询/渲染断言不变 |
| 2 | U1-b 「在等我」行动条 | `loop/web/`（新侧栏区或独立模块，双导出供 node 单测） | 无 | 与 `list_runs`/`run_view` 同源断言；点击直达对应面板；空态显式「无待办」；不新增 API |
| 3 | U1-c 操作者预填 | `loop/web/`（localStorage） | 无 | 已填值不被覆盖；预填不改变提交校验（空操作者仍被拒，权威仍 `human_signed`） |
| 4 | U2-a run 投影 SSE | `loop/services/api.py` + web | 先修订 SPEC-04 §6/§7 | 受控 generator 断言推送与轮询**逐字节同源**；断线回退轮询；无 run 空转；重连一次全量对齐 |
| 5 | U2-b Agent 窗口收编 | `loop/web/agent-window.js` | U2-a | 现有 agent 窗口 browser 测试全绿；控制 POST 协议（SPEC-07）零改动 |
| 6 | U2-c 作业日志尾巴 | `loop/services/api.py` + web | U2-a | 尾行追加不重发全文；作业终态后流收敛；不新增权威日志文件 |
| 7 | U3 渲染分段签名 | `loop/web/`（与 F05-b/c 同片，不另立编号） | F05-b/c 立项 | 行为保持：browser 套件全绿；焦点/草稿保活断言不变；DOM 变更量阈值实施前登记 |
| 8 | U4 G1 引导流 | `loop/web/`（闸门视图） | 无 | 四态判定仍在服务端；`gate_entries_view` 契约不变；N13/N14 不动（STATUS §50 裁决） |
| 9 | U5 事件流过滤 | `loop/web/` | 无 | 纯客户端；清除过滤即还原全量，事件不丢失 |
| 10 | U6 后置项收口 | 各自既有编号 | F14 / SPEC-09 后置 / legacy 清退 | 按各自既有验收条件执行，本计划不重复 |

环境限制：云端会话无内网 `ENV_ROOT`/归档夹具；browser 测试使用受控 API 替身，**真实通知投递与 SSE 长连接行为须内网终验**，不得以受控替身通过冒充。
本计划不安装依赖、不触发 live 模型、不动冻结 kb 目录、不改闸门/记忆/控制契约。
每片完成后按 AGENTS.md §4 记录四道门；实测数字只登记 STATUS 对应新节，禁止预写。

回退：任一片行为回归即整体回退该提交；SSE 断线回退路径保证「最坏情况 = 现状轮询」，不存在需要数据迁移的不可逆变更。

---

## 设计详案：未实施切片（§A–§D，2026-10-24 补全）

> 本节为 U3/U4/U6/U2-c 的**先于代码的设计**；实施仍须按 SpecDD 补各自红灯与切片计划，
> 本节不预写任何验收数字。行号锚点为 2026-10-24 `main` 快照，实施前复核。

### §A U3 + F05-b/c：app.js 分段拆分与按节签名渲染

**现状锚点**（app.js 单 IIFE 约 3660 行）：常量区（约 :20-88）/state（:93-131+）/工具+api
（:136-249）/格式化（:254-338）/数据层+轮询（:389-550）/视图切换+侧栏+配置（:555-988）/
运行视图渲染（约 :993-1990）/闸门视图（约 :1990-3070）/目录浏览器+装配（约 :3070-3560）。
四个含输入面板各自手写保活：run 视图 token 三元组（`fetchRunView`）、node-detail 与
agent-window 各一套 epoch+request、s0 选择计数；表单草稿靠 `GateSession.reconcile` +
`ensureGateForm/updateGateForm` 的 `data-gate-key` 守卫。U2-a 后 `renderLive` 又新增流推送触发，
全量重画的渲染量进一步放大。

**目标结构**（拆分次序，每步一个提交、行为保持）：

1. `web/app-format.js`——parseTs/relTime/fmtDuration/bytesText/pad/errText（双导出；消 app.js 与
   node-detail/report-viewer 的三份 parseTs、三份 errText、三份 pad）。
2. `web/request-guard.js`——epoch+request 双守卫的**唯一实现**（双导出；app.js / node-detail /
   agent-window / s0 四处改消费；node 单测先锁四处现状语义再替换）。
3. `web/dir-picker.js`——目录浏览器（`state.picker` 自包含；app.js 注入 api 与回调）。
4. `web/gate-diff.js`——闸门 diff 渲染（约 660 行；纯渲染，逐条处置经 GateDraftBridge）。
5. `web/agent-cards.js`——agent 角色卡渲染（约 280 行）。
6. **按节签名**：`renderLive` 改为节级调度——`sig = canonical(节数据)`，节 = header /
   sidebar+行动条 / run{stages, agents, counts, blockers, job, events} / gate{material, panel,
   entries} / banners；签名不变跳过该节渲染。输入保活由节签名天然保证：含输入的节其签名
   **不含输入值**（只含身份与数据），输入 DOM 不再因数据重画被替换。
7. app.js 收敛为 state + 装配 + 数据层 + 提交动作（目标 < 1200 行）。

**边界**：不改服务端契约；不动 `gate-session.js`/`run-view-state.js` 等既有纯模块的判定口径；
DOM id 与结构不变（browser 特征测试的选择器不变）。

**验证门**：每步后 `pytest tests/browser -q` 全绿 + node 单测全绿；第 6 步前先以 Playwright
测量「无变化轮询拍」的 DOM mutation 计数现状并登记阈值，实施后断言不升。

**回退**：拆分不迁数据、不改 DOM 结构，任一步回归 revert 该提交即零成本。

### §B U4：G1 引导流（线式 checklist，纯前端）

**现状**：闸门视图已有逐条处置控件（`renderEntryDecisionControls`）与未处置计数
（`GateDraftBridge.counts()`，`validateEntryDecisions` 判定唯一实现）；节点详情二级清单写共享
草稿。痛点：diff 材料与处置控件分栏，需人工来回核对；进度只有计数、没有动线。

**设计**（判定全部留在服务端，前端只做引导呈现）：

- 处置进度条：已处置/总数 + 每条 chip（未处置空心 / 已处置实心 / 存疑高亮）。
- 「下一条未处置」按钮：滚动并高亮下一条 diff 条目、聚焦其处置控件。
- 全部处置且 `counts().complete === true` ⇒ 提交按钮从 disabled 转 primary 高亮
  （数据已有，**不新算判据**）。
- 键盘 J/K 在未处置条目间跳转（沿用侧栏方向键模式）。
- N13/N14 **不加**处置控件（STATUS §50 裁决维持只读待确认项）。

**验证门**：browser 特征测试——处置 n-1 条时提交仍禁用、全部处置后可用、跳转落点正确；
`POST decision` 的 `entry_decisions` 载荷契约断言不变。

### §C U6：既有后置项收口（每项独立小片，按既有编号）

1. **AI 面板停靠/全屏**（SPEC-09 后置）：dialog 加「停靠/浮窗」切换，停靠 = 右侧内嵌滚动区；
   纯 CSS + 类切换，无数据变更。
2. **跨关闭草稿**：sessionStorage 键 `loop.draft.<run_id>.<node>.<session_id>`；关窗暂存、
   同身份重开恢复、提交成功或身份变化清除；草稿是**会话工作记忆**非权威，不落 run 目录。
3. **N10/N11/N12 专用成果渲染**：按 `agent-results.js` 的 N3/N6/N8 结构化模式各加一个渲染器
   （N10 分桶分类表 / N11 四方同值表 / N12 数字对账表）；数据全部来自现有 read_view 投影。
4. **attempt 输出 diff**：需在 `/agents/{node}` 投影增加相邻 attempt 的结果摘要字段——
   **小契约增补，实施前按 SpecDD 先修订 SPEC-07 的 API 行**；客户端复用输入 diff 呈现模式。
5. **F14 V6 人工矩阵**：125%/150% 缩放、hover/focus 动态态人工判读（自动截图与计算样式工具
   已就绪），按 F14 既有验收执行并留证。
6. **legacy 清退**：删 `legacy.html`/`legacy.css`（约 -1878 行；`test_web_smoke` 的 legacy 断言
   同步移除）；`mockup.html` 移出 StaticFiles 可达范围或加显著访问说明。

### §D U2-c：独立逐行日志流（后置，需使用证据）

现状 `job.log_tail`（12 行）已随 §6.9 的 run_view 推送（§6.9 注明的口径）。仅当长作业盯屏的
真实使用需求被登记后（采纳门：先有使用证据）再立项：`event: job_log` 增量帧（日志文件
offset + 行）、投影字段与游标语义，先修订 §6.9 再实现；在此之前不得以「可能有用」立项。
