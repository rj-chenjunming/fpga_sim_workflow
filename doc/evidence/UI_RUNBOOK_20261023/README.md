# UI_RUNBOOK_20261023 · 人工跑通手册的界面截图与验证记录

> **这是什么**：为 [`doc/UI_RUNBOOK.md`](../UI_RUNBOOK.md)（2026-10-23 版）配套的**真实浏览器**
> 截图与运行记录。**不是验收报告**，也**不是**人工签署证据。
> **纪律**：本目录内容冻结、只增不改；截图来自一次性演示 run，不得当作业务结论。

---

## 1 采集条件

| 项 | 值 |
|---|---|
| 日期 | 2026-10-23 10:55–11:07 +0800 |
| 实例 | `127.0.0.1:18097`（隔离实例，未使用 8099/18099） |
| 进程 | `LOOP_LLM_MODE=standin`、`LOOP_PORT=18097` |
| 数据根 `WORKSPACE_ROOT` | `workspaces/manual-20261023/ws`（`v0` 有效 + drill 夹具 `RUN-20261015-120626`） |
| 状态根 `LOOP_STATE_ROOT` | `workspaces/manual-20261023/state3` |
| 构建 | 当前工作树（S0 工作台、节点详情"人话优先"、Agent 工作窗口、S0 来源徽标）；`/openapi.json` **18** 条路由 |
| 浏览器 | Playwright + 系统 `Google Chrome`（headless），视口 1600×1000 |
| 截图方式 | 页面用视口截图（不用 full_page，避免 sticky 头重复）；节点详情/Agent 窗口用元素截图 |
| 演示 run | `RUN-20261023-110500`（drill / happy，最终 `finished`） |

### 1.1 这轮实际发生了什么

1. S0 演练：`status = prepared`，四项 checks 通过（copy / rtl / non_rtl / baseline），
   04/05 未完成。
2. G1 `confirmed`（理由：已逐条核对 2 条差异，其中 1 条未决）→ G2 `accept`。
3. G3 先提交 `full_now`，被 I4 拒绝（HTTP 403，闸门仍 pending），再提交 `milestone_only`。
4. N15_select（5 例）→ N15（`simulated=true`）→ N16 `refused`（rc=3，dry-run=true）。
5. `gates.json` 三条记录均为 `actor=human:manual-verify`、`actor_kind=human`、
   `human_signed=true`。**这是占位 actor，不是真人签署**；仅用于把界面走到终点。

### 1.2 不能从本目录得出的结论

- 不能说「人工签署已完成」：actor 是脚本占位（`human:manual-verify`）。
- 不能说「real 真机链路已验收」：本轮是 drill + standin；real 的 N16/G2 问题见
  [`STATUS.md`](../STATUS.md) §43。
- 不能说「S0 已准出」：S0-b 未接入，`ready_for_execution=false`。
- 不能拿截图里的路径/run_id 当长期数据：`workspaces/` 不入库，演示 run 可清理。

---

## 2 截图索引

| 文件 | 对应手册位置 | 内容 |
|---|---|---|
| [`screens/01-s0.png`](screens/01-s0.png) | §2、§3 | 工作台默认「环境准备」页：四视图、S0-a/S0-b、六项检查、S0 演练卡 |
| [`screens/02-s0-rehearsal.png`](screens/02-s0-rehearsal.png) | §3.3 | S0 演练回执：四项已验证、04/05 未完成、免责声明 |
| [`screens/03-setup.png`](screens/03-setup.png) | §4.1–4.3 | 运行配置：基线 `v0` 有效、项目目录与校验 chips、模式/场景 |
| [`screens/04-setup-confirm.png`](screens/04-setup-confirm.png) | §4.4 | 确认条：基线/环境/模式汇总、`校验通过，可启动` |
| [`screens/05-gate1.png`](screens/05-gate1.png) | §6.1 | 人工闸门视图：run 头、四段流程、G1 材料/操作两栏 |
| [`screens/06-g1-diff.png`](screens/06-g1-diff.png) | §6.1 | G1 差异材料：before/after 双栏、无 hunk 原因、未决、Host 留痕入口 |
| [`screens/08-node-detail.png`](screens/08-node-detail.png) | §5.3 | N1 节点详情：这一步做什么/结果/关键数字/过程/证据/原始记录（收起） |
| [`screens/08-node-detail-N4.png`](screens/08-node-detail-N4.png) | §5.3、§6.1 | N4 闸门节点：`waiting`、用途、过程（等待人工决策） |
| [`screens/10-g2.png`](screens/10-g2.png) | §6.2 | G2 报告验收：双口径 1687 / UVM 汇总、阻断项、两个选项 |
| [`screens/11-g3.png`](screens/11-g3.png) | §6.3 | G3 回归决策：冲突 72/72/72、四个选项 |
| [`screens/12-g3-rejected.png`](screens/12-g3-rejected.png) | §6.3 | G3 `full_now` 被 I4 拒绝：红框原文、闸门仍待决策 |
| [`screens/13-finished.png`](screens/13-finished.png) | §7.2 | 终点：`已结束`、四段完成、N13/N14/N15/N16 |
| [`screens/13b-finished-blockers.png`](screens/13b-finished-blockers.png) | §7.2 | 终点的双口径与阻断项（1687、I3/I4） |
| [`screens/14-agent-window.png`](screens/14-agent-window.png) | §5.4 | Agent 工作窗口：只读观察 + 请求边界干预（历史只读） |
| [`screens/15-node-detail-N16.png`](screens/15-node-detail-N16.png) | §7.3 | N16 节点详情：`refused`、退出码 3、dry-run=是 |

初始截图另见 `workspaces/manual-20261023/shots/`（草稿区，不入库）。

---

## 3 文件 md5（内容校验用）

```
81f3784781f14345ef175a839622f386  screens/01-s0.png
746b82603d3297536b4972ecb8a65df1  screens/02-s0-rehearsal.png
a18bd42ef0eb837db8343b5cda7652f8  screens/03-setup.png
3097cf52ad7c21e466e6f40acd4e15b5  screens/04-setup-confirm.png
297983a34162015691d26af823fb978b  screens/05-gate1.png
a4eef72d502534ba08760027d25c7df1  screens/06-g1-diff.png
6a75916f26f38461f7fff9ce844e3458  screens/08-node-detail-N4.png
456d6791384c89eb9283f85057294d2e  screens/08-node-detail.png
b6d34f736974c1502b927649bd45bec6  screens/10-g2.png
0740bf2fa21ed858057365c70f5d92c3  screens/11-g3.png
d454d9c5ca6a4b1cb8c109227000f548  screens/12-g3-rejected.png
556d1e40c5daf0b30a77de0ad68db23d  screens/13b-finished-blockers.png
98234031da8d9d4ad736e1d09b988dbe  screens/13-finished.png
5a7e2e46fdd8e71fa9f7c3284f2361dc  screens/14-agent-window.png
3deabde2e86e5e120706095016f9dc2d  screens/15-node-detail-N16.png
```

---

## 4 复跑（可选）

截图脚本是**一次性**的，不在本目录。需要复跑时按 [`doc/UI_RUNBOOK.md`](../UI_RUNBOOK.md) §8
在**隔离实例**上走一遍即可；注意：

- 不要用 `8099` 上的共享 workspace 做演示（会覆盖别人的 `view.json`）；
- 不要把 `actor` 写成真实同事的名字；占位演练请在理由里写明"演练占位"；
- 不要求截图时，可以直接用界面走流程，不需要本目录任何文件。
