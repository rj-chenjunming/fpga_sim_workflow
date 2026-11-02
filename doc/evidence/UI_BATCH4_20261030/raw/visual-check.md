# 批次 4 · A 项视觉核对（`visual-check.md`）

> 状态：**DONE（最终基线已拍）**。本轮 `loop/web` = 3C 合并 + 批次 4（B/A/C）+ 3B 配色令牌化 **最终态**
> （Lead 在 15:19 前完成，随后浏览器单租户交给我）。截图 = `.ui-audit/4b/shots/`，读数 = [`measure-4b.json`](measure-4b.json)，
> 脚本 = [`scratch/shots.py`](scratch/shots.py)（受控 API 替身 + 真实静态页，**无任何注入样式**）。

## 1 已测（最终态 · Chromium，2026-10-30 15:19–15:2x）

| # | 项 | 判据 | 结果 |
|---|---|---|---|
| 1 | 三视口 × 三视图截图 | 1280×720 / 1440×900 / 1920×1080 × 环境准备 / 运行监控 / 闸门 | ✅ 9 张 `s0-* / run-* / gate-*.png` |
| 2 | Agent 窗口截图 | `#agentWindow` | ✅ `agent-window-1440x900.png`：「关闭 ✕」16×16 正常；另 1 个 `icon-external` 在 `hidden` 的 `#awEmbedDirect` 上（0×0，预期） |
| 3 | 节点详情弹层截图 | `#nodeDetail` | ✅ `final-node-detail-1440x900.png`：关闭图标 16×16 |
| 4 | `.icon` 渲染 | 16×16、`fill:none`、`stroke-width:1.5px` | ✅ 计算样式 = `16px/16px`、`fill:none`、`stroke-width:1.5px`、`stroke:currentColor`（颜色跟随父元素：nav 灰绿 / 主按钮白 / 状态泡语义色） |
| 5 | 空态插图 | 只剩 1 个 58×58、`.empty:before` 已删 | ✅ `icons=1`、`getBoundingClientRect()=58×58`、`.empty:before` 计算 `content="none"`；`final-empty-1440x900.png` 目检无双插图 |
| 6 | `.aw-detail` 的 `▸/▾` | 伪元素已删 | ✅ `grep` 无命中（组件层 `▸/▾` 归零见 `test_ui_icons.py`） |
| 7 | 侧栏几何（A10 输入） | `.seg button` 44±1 / `.rail-entry` 64±1 / `.nav-icon` 19×16 | ✅ 三视口 `segButtons` 全部 **44**、`rail-entry` **64**、`.nav-icon` 盒 **19×21.4**（内层 svg **16×16**；21.4 是行盒高，非按钮高） |
| 8 | 水平溢出 | `scrollWidth == clientWidth` | ✅ 三视口均 `overflowX=false` |
| 9 | 闸门两栏窗格（C 项，仅记录） | `#gateMaterial` 的 y / `.gate-pane` 窗格高 | ✅ y = **828.3 / 832.3 / 811.9**（与 Lead `measure.py` 逐位一致）；窗格高 = **420 / 600 / 780**；1440 的第二栏按内容收缩到 461.1（内容不足**不**拉伸，符合 A11「上限」口径） |
| 10 | 浏览器用例 | `test_web_layout.py` + `test_ui_visual_20261030.py` | ✅ **24 passed in 23.55s**（原始输出 [`browser-tests.txt`](browser-tests.txt)） |
| 11 | 页面 JS 错误 | `pageerror` 为空 | ✅ 替身夹具 teardown 断言通过 |

## 2 目检结论（12 张图逐张看过）

1. **图标正常渲染**：侧栏 4 个入口（立方体 / 滑杆 / 播放圈 / 闸门）、阶段展开指示、主操作 `→`、
   外链/下载、关闭 `×`、阶段与节点状态（`✓` 绿底 / `!` 等待菱形）、空态插图，全部为 1.5px 线条空心图标，
   **没有空框**（`<use>` 全部解析到 symbol 内容，`getBBox()` 非空）。
2. **没有错位**：nav 图标在原 19px 槽位居中；`.stage-chev` 展开时旋转 90°（「摄取」展开态箭头朝下）；
   `.snode` 状态泡（20px 圆）与闸门菱形泡（反向旋转 `span`）里的图标都居中；`.btn` 的 flex 布局让尾部图标与文字间距自然。
3. **颜色跟随父元素**：white（主按钮内 `→`）、灰绿（侧栏）、`--ok`（完成态 `✓`）、`--warn`（等待泡）、
   `--muted`（面板图标）各自正确；3B 令牌化后未出现硬编码色残留导致的偏色。
4. **空态**：58×58 圆角框 + 30px 插图各 1 个，无「◇ + 新图标」双插图。
5. **侧栏几何未变**：`.seg button` 44 高、`.rail-entry` 64 高与图标替换前一致（A10 的输入未动）。
6. 未发现：图标与文字重叠、行高跳动、横向滚动条、图标尺寸跳变。
7. **两处有意的视觉变化**：① `#lnkLegacy`「旧版操作台」去掉 ↗（同标签页跳转，箭头误导）；
   ② `#btnS0` 的折叠指示由 `⌄` 字形改为 1.5px 描边 chevron（内联 `rotate(90deg)` 保持朝下）。
8. **无状态节点**（N0/N1/N2 待开始）的状态泡仍是空圆 —— 与替换前一致（原先也是空文本），非回归。

## 3 未测 / 不声称

1. **未测**：Safari/Firefox（本轮只有 Chromium）；打印样式；深色主题（项目无深色主题）。
2. **未测**：≤760px 窄屏断点下的图标视觉效果（既有无障碍/视觉门都不覆盖窄屏，本批也不改窄屏契约）。
3. **不声称**：`legacy.html` 的图标已本地化 —— 12 处**未迁移**，`⚠/⛔` 仍依赖 emoji 字体（登记例外）。
4. **不声称**：`doc/evidence/**` 的冻结读数已更新（只增不改；本轮读数在 `.ui-audit/4b/measure-4b.json`）。
5. 本轮的 3B 令牌化由 Lead/另一 owner 落，我只核对「图标描边用 `currentColor` 不受影响、空态框色已映射到
   `--line-soft/--bg/--text-5`」这两条与 A 项的耦合面，未复核 3B 的全局色值清单。
