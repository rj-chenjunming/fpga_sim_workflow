# 计划 · 闸门视图「材料 / 操作」双栏独立滚动（人反馈：方便对照处理）

> 日期：2026-10-29。状态：**SpecDD ②产物**（规格已先落，见 §1；实现与验证见 §3/§4）。
> 入口：人反馈（截图：运行 `RUN-DEMO-58F` 的闸门视图底部两卡）——「闸门材料 / 闸门操作 这两块
> 做成可以分别上下滚动的东西，方便对照处理」。
> 契约：[WEB_UI_SPEC](../spec/WEB_UI_SPEC.md) §5「材料/操作双栏独立滚动」+ §10 **A11** + §14「闸门双栏局部滚动」。
> 归属：纯展示层（`loop/web/**`），不触碰业务权威、闸门判据、请求形状。

## 1 规格先行（本轮已完成）

| 项 | 内容 |
|---|---|
| 可观察行为 | 两栏各自纵向滚动；滚一栏另一栏与页面都不动；卡片头固定；内容不足一屏时不出现滚动条 |
| 不变量 | ① 布局仍是既有 `.grid2.run-grid` 两列，不新增列/分页；② 材料与选项仍全部来自服务端，前端不判定；③ 提交入口仍只有 `#gatePanel` 的提交按钮；④ 页面无水平溢出（§14 桌面布局） |
| 身份与生命周期 | 滚动身份 = `run_id + gate + cycle`；同一身份跨 1.5 s 全量重绘**保持** `scrollTop`，身份变化回顶 |
| 唯一 owner | 判定唯一实现在 `web/pane-scroll.js`（纯函数）；`app.js` 只装配状态与包装重绘；CSS 只在 `app.css` 一处 |
| 键盘 | 溢出时 `tabindex="0"` + `role="region"` + `aria-label`；不溢出不产生 Tab 停靠点 |

## 2 为什么必须做「重绘保持」（不是可选项）

`app.js` 每 `POLL_MS=1500` 一次 `renderLive()` → `renderGate()` → `renderGateMaterial()`
会 `clearEl()` 后整体重建材料栏（`renderGatePanel()` 靠 `data-gate-key` 早返回，但仍会被包装层重设
`scrollTop`）。**只加 CSS 而不做保持**时用户每 1.5 s 被滚回顶部，等于功能不成立。
故本计划的验收不只看「`overflow-y:auto` + 高度上限」，必须含「跨一次真实轮询后 `scrollTop` 不变」。

## 3 切片（单 writer：Lead）

| # | 切片 | 落点 | 验收 |
|---|---|---|---|
| T1 | 纯函数 + 先失败用例 | `web/pane-scroll.js`、`tests/test_pane_scroll.py`（node 驱动，照 `test_gate_session.py` 形态） | 身份相同 ⇒ 返回保存的 top；身份不同/空 ⇒ 0；负数/NaN 归 0；不改入参；**结构守卫**：`app.js` 只转调（`scrollHeight >` 零出现、脚本顺序 `pane-scroll.js` 先于 `app.js`） |
| T2 | 浏览器先失败用例 | `tests/browser/test_gate_panes.py`（复用 `test_run_sessions.py` 的 `ui` 受控替身） | 见 §4 判据 B1–B7；实现前必红 |
| T3 | 结构 + 样式 | `web/index.html`（两栏加 `gate-pane` / `role` / `aria-label`）、`web/app.css`（`--gate-pane-max-h` + 单列断点回退） | 双栏下 `overflow-y:auto`、`max-height` 为视口推导值；1100px 下一栏 `overflow:visible` |
| T4 | 重绘包装 | `web/app.js`：`renderPanePreservingScroll(hostId, pending, paint)` 包装 `renderGateMaterial` / `renderGatePanel`（`paint*` 为原实现），并同步 `tabindex` | 轮询后 `scrollTop` 保持；切运行/切轮次回顶；溢出才有 `tabindex` |

**写权**：`loop/web/**` + 本计划 + `tests/**` 本轮唯一 writer = Lead；`doc/spec/**` 由 Lead 改（已改）。
**不与在飞切片交叉**：工作树里 S8j（`agent-window.js` / `index.html` 的 `awEmbed` 段 / `app.css` 末尾）是
**别人未提交的在飞改动**，本计划只做**新增**行，不改它的 hunk；不提交、不 revert 他人改动。

## 4 浏览器判据（B1–B7，全部可判定；与 `tests/browser/test_gate_panes.py` 同名同号）

| # | 判据 | 判定方式 |
|---|---|---|
| B1 | 1280×720 / 1440×900 / 1920×1080 双栏下两栏 `overflow-y`/`overflow-x` 为 `auto`、`overscroll-behavior-y: contain`、`scrollbar-gutter: stable`；`--gate-pane-max-h` token 存在且解析值 = `min(max(300, vh-340), 720)`，两栏同值，`clientHeight ≤ 上限` | `getComputedStyle` |
| B2 | 长材料 + 长操作（G1 逐条处置 12 条）下两栏都真的溢出（`scrollHeight > clientHeight + 1`） | DOM 度量 |
| B3 | 滚材料栏到 200 ⇒ 操作栏 `scrollTop` 仍 0，`pageYOffset` 不变；再滚操作栏到 120 ⇒ 材料栏仍 200 | 用户手段（`mouse.wheel` / `evaluate scrollTop`） |
| B4 | 滚到 200 后等 **2 次真实轮询**（`page.clock` 快进 3.2 s，或等待 API 被再次请求）⇒ 材料栏 `scrollTop` 仍 200 | 轮询计数 + 度量 |
| B5 | 身份 = `run + gate + cycle`：同身份轮询**保持**位置；轮次 0→1（内容不变）**回顶**；轮次再变回 0 也回顶；切运行同样回顶。**主判据用切轮次**（切运行会经"加载中"重绘把位置归零，独立复核 M4 变异证明只看切运行抓不住身份接线） | 轮询重绘 + 度量 |
| B6 | 溢出时两栏 `tabindex=0`、`role=region`、`aria-label` 与标题同文；聚焦材料栏按 `PageDown` ⇒ `scrollTop` 增大；材料为空态（不溢出）时 `tabindex` 不存在 | 键盘事件 + 属性 |
| B7 | 1000px 宽（单列断点以下）⇒ 两栏 `max-height: none` / `overflow-y: visible` / 无 `tabindex`，内容不被裁掉；三种验收视口下 `document.documentElement.scrollWidth <= innerWidth` | 切换视口重度量 |

**不做**：不改 `legacy.html`；不改 `mockup.html` 静态样张；不给两栏加分页/搜索/锚点；不做移动端专项；
不改轮询频率与请求形状；不改 §4.4 右列紧凑闸门卡（人反馈的是闸门视图两栏）。

## 5 验证门（本切片）

1. 受影响：`tests/test_pane_scroll.py`、`tests/browser/test_gate_panes.py`、
   `tests/browser/test_web_layout.py`、`tests/browser/test_node_detail.py`、`tests/browser/test_run_sessions.py`
   （后三者含闸门视图断言，防回归）。
2. 四道门按 `AGENTS.md` §4：单测（可写数据根）、kb 自测 + env layer、端到端、文档门；
   界面改动 ⇒ **必跑浏览器门**并把数字记入 `doc/STATUS.md`（唯一数字源）。
3. 证据：三种视口的截图（`LOOP_VISUAL_ARTIFACTS`）只作视觉检查，不作通过判据。
