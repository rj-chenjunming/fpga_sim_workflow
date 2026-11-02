# UI 批次 4 · 图标 sprite / GATE-1 文案中性化 / 闸门窗格上限 · 证据（2026-10-30）

> **只增不改**。本目录是 [`doc/STATUS.md`](../../STATUS.md) §143（UI 批次 4）与
> [`doc/plans/2026-10-30-ui-batch4.md`](../../plans/2026-10-30-ui-batch4.md) 的证据附录。
> 人裁（2026-10-30）：批次 4 三项「全做」，含放宽闸门 `--gate-pane-max-h`。

## 1 交付

| 项 | 结果 |
|---|---|
| A 图标 SVG sprite | `index.html` 内联 `#iconSprite`（**18 个** `<symbol viewBox="0 0 16 16">`，无 `xmlns`）+ `#iconTpl` 模板；三个 JS 各 5 行 `iconNode()`（克隆模板，不用 `createElementNS`）；**替换 41 处**（index 15 / app 14 / s0 7 / node-detail 5）；`app.css` 新增 `.icon` / `.icon-30` / `.empty .icon-30`，删 `.empty:before`、`.aw-detail summary:before`、`.aw-detail[open] summary:before`，删 3 条失效 `font-size` |
| B GATE-1 文案中性化 | 3 处（`index.html` 两处 + `s0.js` 一处，HTML/JS 逐字一致）改为中性表述；`grep -rn GATE-1 loop/web` = **0**；`kb/**`、判据、后端零改动；**GATE-1↔G1 映射仍待裁**（界面不再暗示同一身份） |
| C 闸门窗格上限 | `WEB_UI_SPEC.md` §14 先改（新增「闸门两栏上限放宽（2026-10-30 增补）」）；`app.css` `--gate-pane-max-h` = `clamp(300px, calc(100dvh - 300px), 860px)`；`test_gate_panes.py` 常量 340→300、720→860 |

## 2 门（原始输出在 `raw/`）

| 门 | 文件 | 实测 |
|---|---|---|
| B 新用例**先红 → 后绿** | `raw/red-gate-copy.txt` / `raw/green-gate-copy.txt` | `4 failed, 2 passed` → **`6 passed`** |
| A 新用例**先红 → 后绿** | `raw/red-icons.txt` / `raw/green-icons.txt` | `6 failed, 4 passed` → **`10 passed`** |
| C 常量**先红 → 后绿** | `raw/red-gate-pane.txt` / `raw/green-gate-pane.txt` | `3 failed, 5 passed` → **`8 passed`** |
| 浏览器相关用例（实现者跑） | `raw/browser-tests.txt` | `24 passed in 23.55s`（`test_web_layout.py` + `test_ui_visual_20261030.py`） |
| 静态面 | `raw/software-tests.txt` | `146 passed / 2 failed`（当时那 2 条是 3C 收口中的 `test_ui_css_structure`，现已绿） |
| 运行时读数（最终树） | `raw/measure-4b.json` | `#gateMaterial` y = **828.3 / 832.3 / 811.9**（与基线逐位一致）；窗格高 = **420 / 600 / 780**；`.icon` = 16×16、`fill:none`、`stroke-width:1.5px`、`stroke:currentColor`；空态 `icons=1`、58×58、`.empty:before` 计算 `content="none"`；三视口 `.seg button` 44、`.rail-entry` 64、无水平溢出 |
| 字号守卫 | — | 扫描数 **352**（≥300；比实现者预估的 369 低，因 3C 同时删掉大量重复 `font-size`） |
| 浏览器全量 / 软件层 / 文档 | 同 [`../UI_CSS_MERGE_20261030/raw/`](../UI_CSS_MERGE_20261030/raw/) | 见 STATUS §145 |

## 3 截图（`shots/`，Chromium 1280×720 / 1440×900 / 1920×1080，受控夹具，无注入样式）

`s0-*` / `run-*` / `gate-*` 三视图 × 三视口 9 张 + `agent-window-1440x900.png` +
`final-empty-1440x900.png`（空态：只剩 1 个 58×58 内联插图）+ `final-node-detail-1440x900.png`。
`prelim-*.png` 是「`.icon` 未落地时注入自证」的中间态留档（**不作交付**，保留以说明当时为何必须落地 `.icon`）。
目检结论（实现者，`raw/visual-check.md`）：图标全部空心线条、无空框/错位、行高无跳动、无横滚；
两处有意变化：`旧版操作台` 去 `↗`、`#btnS0` 折叠指示由 `⌄` 字形改 1.5px chevron（内联 rotate 保朝下）。

## 4 偏差与未做

**已认可的偏差**
1. `node-detail` 实为 **5 处**（设计盘点记 3 处；另 2 处是同型「动作按钮 + 尾部 →」，不补会出现同弹窗两个按钮一个 SVG 一个字形）。
2. sprite **18 个 symbol** 而非 22：`icon-back/refresh/warn/blocked` 只有 `legacy.html` 有消费者，而 legacy 本轮不迁移 ⇒ 按 YAGNI 不入 sprite；`test_ui_icons.py` 对「symbol↔use 一一对应」fail-closed，将来迁移 legacy 时成对添加。

**未做 / 不声称**
- `legacy.html` **12 处图标不迁移**（旧界面存档；`⚠/⛔` 仍依赖 emoji 字体）⇒ 4 个 legacy-only symbol 未入 sprite。
- **1280×720 闸门材料仍在首屏外**：`#gateMaterial` 的 y 由上方块高决定（实测缺口 108.3px），放宽 `--gate-pane-max-h`
  只增加窗格高度、**不移动 y**；真正解决需折叠「非当前阶段」的流程卡（结构变更），**本批不做**，进 STATUS 未做清单。
- **GATE-1 ↔ G1 身份映射仍待裁**（本批只中性化文案，不新增枚举、不映射）。
- `●` 图标未入 sprite；窄屏（≤1100）与 Firefox/非 Chromium 的图标渲染未逐项验证（只有三视口 Chromium 截图与无溢出断言）。
