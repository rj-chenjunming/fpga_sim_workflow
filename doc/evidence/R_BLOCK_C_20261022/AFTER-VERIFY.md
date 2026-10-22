# F14-b 改后验证与差异说明（slice A / A2 / B / B2 / C / D，2026-10-22）

本文件记录 F14-b 前三个组件切片的**等价性证据与差异解释**。改前基线是 F14-a 的
`HEAD=746ec8d`（证据提交 `9ebb986`，`loop/web` 未变）；验证在含 R5 的同一棵树上完成。
同一执行者实施与验证：**这不是独立视觉评审，也不声称四道门全绿**。

## 1 提交与变更规模

| 切片 | 提交 | 内容 | 删除 | 新增 `!important` |
|---|---|---|---|---|
| A 布局/框架 | `837d2aa` | header/brand/mark/shell/aside/rail-*/viewSeg/run-*/main/page-head/footer/grid2/run-grid 的 Base 层被覆盖声明 | 51 条声明 + 11 条整规则 | 否 |
| A2 断点/reduce | `25714b3` | 删除重复的 `prefers-reduced-motion:reduce` 块 | 1 个媒体块（含 2 条 `!important` 声明） | 否（净减 2） |
| B 通用控件 | `c06ca97` | `.btn*`/`.input*`/`.chip*`/`.card*`/`.empty*`/`.banner*`/`.alert*`/`.toast`/`.dirpicker`/`.dp-*`/`.step-card*`/`.confirm-bar` 等 | 56 条声明 + 8 条整规则 | 否 |
| B2 回退令牌化 | `1edd451` | 回退 3 条 `#fff -> var(--panel)`（原因见 §5） | — | 否 |
| C S0 | `f2d39fe` | `.s0-*`/`.phase-*`/`.hero-*`/`.diagram-*`/`.eyebrow`/`.section-index`/`.form-*`/`#s0Report` 的 Base 层被覆盖声明 | 88 条声明 + 12 条整规则 | 否 |
| D 运行/闸门 | `b4df6e6` | `.run-head`/`.status-pill`/`.stage*`/`.snode*`/`.agents`/`.agent*`/`.avatar*`/`.count*`/`.blocker`/`.sev`/`.option`/`.kv`/`.diff-item`/`.gate-*`/`.ev*`/`.refs`/`.log-pre`/`.spinner`/`.pulse` 的 Base 层被覆盖声明 | 81 条声明 + 8 条整规则 | 否 |

截止 D 的 `loop/web/app.css`：57526 → **51308 字节**；规则 795 → **755**；媒体查询块 14 → **13**
（只删了重复的 reduce 块，两份 `max-width:760px` 保留）；`!important` **声明数 6 → 4，行数 3 → 2**。
`legacy.css`、`tokens.css` 本阶段未改。

## 2 验证方法（每个切片都执行）

1. **全 longhand 计算样式指纹**（`verify_style_equivalence.py`，只读）：
   改前 = `git archive <基线> loop/web` 快照，改后 = 工作树；对 `body *` 每个元素取约 150 个
   longhand 属性 + `::before/::after`，逐元素哈希后比对。**无限动画暂停在 0 时刻、有限过渡沉降 600 ms**
   后取值（不注入样式，故 `transition-*`/`animation-*` 取到的是真实级联值）。
   组合 = 断点 ±1px 全扫 × {s0, run} + Agent 窗口窄断点 × agent + 主视口 8 状态
   （s0/setup/run/gate/dirpicker/agent/legacy/empty）+ legacy 主视口。
2. **`tests/browser` 41 条**（真实 Chromium，受控 API 替身，无 skip）。
3. **冻结截图对**（`capture_pair.py`，只读）：同一端口 38123、假时钟暂停在固定时刻、
   `animation/transition:none`；改前/改后各 42 张（14 状态 × 1280/1440/1920），逐张 MD5 比对。

## 3 各切片验证结果

| 切片 | 指纹组合数 | 差异组合 | 浏览器用例 | 截图对 |
|---|---|---|---|---|
| A | 113 | **0** | `41 passed in 57.34s` | 未在此切片单独截（改后统一截） |
| A2 | 139 | **0** | `41 passed in 55.21s` | 同上 |
| B | 139 | **0** | `41 passed in 55.02s` | 同上 |
| C | 139 | **0** | `41 passed in 54.07s` | **42/42 MD5 完全相同** |
| D | 139 | **0** | `41 passed in 62.71s` | **42/42 MD5 完全相同** |
| A+A2+B+B2+C+D 累计 vs F14-a 基线 | **139** | **0** | `41 passed in 62.71s`（累计） | **42/42** |

原始日志：`raw/f14b-sliceA-verify.log`、`raw/f14b-sliceA-pytest.log`、`raw/f14b-sliceA2-verify.log`、
`raw/f14b-sliceA2-pytest.log`、`raw/f14b-sliceB-verify.log`、`raw/f14b-sliceB-pytest.log`、
`raw/f14b-final-verify.log`、`raw/f14b-final-pytest.log`、`raw/f14b-sliceC-verify.log`、`raw/f14b-sliceC-pytest.log`、`raw/f14b-sliceC-screens.txt`、`raw/f14b-sliceD-verify.log`、`raw/f14b-sliceD-pytest.log`、`raw/f14b-sliceD-screens.txt`。

**缩放与键盘**：浏览器缩放只改变 CSS 视口宽度，因此断点扫描里加入了缩放等效宽度
**853/854（1280 窗口 @150%）、1024/1025（1280 @125%）、1535/1536/1537（1920 @125%）**；
这些宽度下与改前逐元素计算样式零差异。未在 Chrome UI 里真实设置 125%/150% 缩放（等价宽度法，
理由如上）。键盘可达性由 `tests/browser` 的方向键/Home/End/跳过链接/焦点保持用例覆盖；
本阶段未改 `loop/web/*.js`、未改 DOM id 与结构，焦点顺序清单（F14-a `style-inventory.md` §6）不变。

## 4 截图对差异说明

改后截图：[screens-after/](screens-after/)；与改前冻结截图 [screens-before-frozen/](screens-before-frozen/)
逐张 MD5 比较（完整 42 行见 `raw/f14b-screens-compare.txt`）：

```text
identical=42 total=42 diff=0
```

即 **42 张逐字节相同，无差异需要解释**。对照基线为 `9ebb986`（=F14-a 采集时的 `loop/web`）。

为什么不用 F14-a 的普通截图做逐字节比对：`screens-before/` 是常规管线截图，含无限动画
（`.pulse`/`.spinner`）的任意相位与动态端口/时间文本，**同一份 CSS 两次采集也不会逐字节相同**，
不能作为等价判据；冻结管线（固定端口、暂停假时钟、关闭动画/过渡）才是可判读口径。作为管线
确定性的对照，`raw/f14b-screens-selfrepeat.txt` 记录「同一份 CSS 连续采集两次」也是 42/42 相同。

## 5 被否决/回退的改动（如实登记）

1. **合并两份 `@media(max-width:760px)`：否决**。把前一块内容并入后一块后，在 **760px 处 111 个元素**
   的计算样式发生变化（前块规则跨过了 850 块与后置无条件规则的层叠次序，不只是同名重复）。
   证据：`raw/f14b-sliceA2-merge760-attempt.log`。因此两份 760 块**保留**，本阶段不合并。
2. **颜色令牌化：回退**。曾把 3 条整值相等的 `#fff` 改为 `var(--panel)`（header、.dirpicker、
   .input:focus）。计算样式零差异，但冻结截图对里 `1920-gate-rejected.png` 出现 **14 个像素、RGB ±1**
   的差异（`raw/f14b-tokenization-diff.txt` 记录了当时的 41/42 结果）；另有 1 张
   `1280-stale-error.png` 差异已定位为「上次成功 20:00:05 vs :06」的假时钟未暂停问题（已修复）。
   按 Lead「纯等价」口径，B2 回退这 3 条令牌化；回退后 42/42 逐字节相同。
   **结论**：在「截图逐字节相同」口径下，`var(--panel)` 与 `#fff` 并非渲染完全等价（差异低于视觉阈值，
   但不再声称纯等价）；颜色令牌化留待有独立视觉评审的轮次再做。

## 6 与 spec / F14 计划的对应

- WEB_UI_SPEC §14「桌面布局（1280/1440/1920 主区不产生页面水平溢出）」：F14-a 已实测三视口零溢出；
  本阶段计算样式等价 ⇒ 布局与溢出结论不变。
- F14 计划 §3.2「每类组件一个基础声明 + 明确状态/断点修饰」：本阶段先删除**可证明被完全覆盖**的
  Base 层声明（107 条独立声明 + 19 条整规则 + 1 个重复 reduce 块），把两层样式收敛为
  「修订层决定视觉、Base 层只留未被覆盖的声明」。
- F14 计划 §3.3「合并同范围媒体查询时检查交界宽度」：已检查并**否决** 760 合并（§5.1）。
- 未新增 `!important`；唯一的 `!important` 变化是删除重复 reduce 块带来的 **-2 条声明**。

## 7 本阶段未完成（下一轮直接接续）

C、D 已完成（`f2d39fe`、`b4df6e6`）。下一轮接续：

| 切片 | 写入面 | 预计删除 | 验证方法（同本文件 §2） |
|---|---|---|---|
| E Agent+旧页 | `loop/web/app.css`（`.agent-window`/`.aw-*`）+ `loop/web/legacy.css`（0 条冗余声明，仅等值检查） | 60 条声明 + 4 条整规则（dry-run） | 同上（含 850/760 窄断点 Agent 窗口） |
| F05-b/c（本窗口不启动） | `loop/web/app.js`、`run-view-state.js` 等渲染模块、`index.html` 加载顺序、`loop/tests/browser` | — | 先固定浏览器特征集，再机械提取；GET/POST 目的地与次数、草稿身份/焦点、互斥、409 保留不变 |

剩余可证冗余声明合计 **68 条**（agent；初始 410，A/A2/B/C/D 已删 342）。
`legacy.html` 内联深色主题不在可改范围（只登记）；`tokens.css` 未改（无同角色可等值替换后的稳定目标，
新增语义令牌需独立视觉评审）。

## 8 诚实边界

1. 本阶段只做**保持行为**的机械收敛，不改善任何视觉缺陷（例如 `.btn-primary` 历史蓝色 hover 已由修订层
   覆盖为 `var(--primary-hover)`，本阶段只是删除被覆盖的旧声明）。
2. 验证是「计算样式 + 冻结截图」级别，不是人眼视觉评审；同一执行者不能自证视觉验收通过。
3. 未运行：完整四道门、kb 自测、端到端、真实 provider/内网链路、真实 Chrome UI 缩放 125%/150%。
4. 冻结截图只覆盖受控 API 替身数据；真实服务端数据形状不在本阶段范围。
