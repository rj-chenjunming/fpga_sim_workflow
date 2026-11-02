# UI 批次 3B · 配色令牌化 · 证据（2026-10-30）

> **只增不改**。本目录是 [`doc/STATUS.md`](../../STATUS.md) §144（UI 批次 3B）与
> [`doc/plans/2026-10-30-ui-color-tokens-3b.md`](../../plans/2026-10-30-ui-color-tokens-3b.md) 的证据附录。
> 口径：组件层颜色字面量 = 0；每条字面量到其令牌 **ΔRGB ≤12**（alpha 按合成到实际底色后判）；`tokens.css` 唯一色源。

## 1 前后

| 文件 | 改前 md5 / 行数 | 改后 md5 / 行数 |
|---|---|---|
| `loop/web/tokens.css` | `3d23134177964d8e2b2749a241f55a43` / 18 | **`2eee8a67befa10308c56aadb1f71ef2f`** / 92 |
| `loop/web/app.css` | `4d4a7867c397a77f81f1ad3814cebd08` / 1015 | 实现后 `e0aace636099289edd8398e0e6d3c440`；**对比度修正后 `d75422b5ecdc15fd26d9114d34369b5c`** / 1015 |
| `loop/web/legacy.css` | `149153746ed1fa738b56aebea7db1e40` / 81 | **`91f647c090ba78631417a1e857539711`** / 81 |
| `loop/web/legacy.html` | `6efe1904…` / 1794 | **`c0270e2001de8675597dd25bada46168`** / 1794 |

- 替换条数：`app.css` **323** + `legacy.css` **59** + `legacy.html` **3**（活值）= **385**；行数无 reflow。
- 组件层颜色字面量：**382 → 0**（`app.css` 323、`legacy.css` 59；`legacy.html` 仅活规则，155 条死声明按裁决不动）。
- 令牌：**69 个颜色令牌** + 5 个非颜色 = **74 个变量**；69 个颜色令牌全部被引用、无死令牌；`var(--x)` 未定义 = 0。
- 色差（值级自检 `selfcheck-final.txt`）：实色 **355/355 Δ≤12（max 12）**；alpha **27/27 合成后 Δ≤12（max 10）**；`unmapped=0`（382/382 逐条落位）。

## 2 门

| 门 | 文件 | 实测 |
|---|---|---|
| 新守卫**先红** | `raw/red-tokens.txt` | `3 failed / 6 passed`（报「组件层仍有 382 处颜色字面量」「活规则 3 处」「令牌 24≠69」） |
| 新守卫**后绿** | `raw/green-tokens.txt` | `9 passed` |
| 静态 5 套件 | `raw/static-5-suites.txt` | `30 passed`（tokens 9 / 结构 2 / 字号 3 / 图标 10 / gate_copy 6） |
| 替换忠实性（不复用替换算法，用冻结 map 做 oracle） | `raw/verify-surgical.txt` | 抹平色值载体后声明文本逐字相等；382/382 逐位置对齐；map 按 file/line/property 逐行命中 |
| 守卫变异性 | `raw/guard-mutation.txt` | 回填 hex/rgba/hsl 会红；`#banners` 这类 ID 选择器、注释旧值、`transparent` 不误报 |
| **A13 可读性不回退** | `raw/measure-baseline.json` / `raw/measure-final.json` / `raw/measure-final.stdout.txt` | 对比度 fail：s0 **3/194 → 3/187**、gate **4/173 → 4/162**、monitor **4/238 → 4/227**（失败项仍只有装饰 `/` ×2 与禁用控件）；焦点环 s0 21/22、gate 17/18；`<24px` 点击靶 0；渐变 0 |
| 浏览器全量 / 软件层 / 文档 | 同 [`../UI_CSS_MERGE_20261030/raw/`](../UI_CSS_MERGE_20261030/raw/) | 见 STATUS §145 |

## 3 必须登记的两处偏差

1. **令牌数 69 > 人裁「46–50」**。几何下界不是估算：213 个不同实色值里既有 24 个冻结令牌在 Δ≤12 下只覆盖 104 个；
   余下 109 个按「同族 + 半径 12」最少要 29 个新语义令牌 + 7 alpha + 6 avatar + 3 内联专用。
   压缩曲线（实测，`gaps-final.md` §2）：**65→3 条例外(max 73)、60→11、55→26、50→45** ⇒「保 ≤12」与「≤50」不可兼得，
   按人裁的**硬意图「保 ≤12」**优先取 69。
2. **`.avatar` / `.a2` 背景改映射**：冻结 map 把 `#eaf3e8`→`--rail-text`（Δ9）、`#e9f3ee`→`--rail-text`（Δ10），
   两项都 ≤12 合规，但**实测把 `.avatar.a2` 的前景对比从 4.64 压到 4.41 < A13 的 4.5**（`measure.py` 报红）。
   已改为同族绿底 `--primary-weak`（`#eaf5ef`，Δ 分别 7 / 2，仍 ≤12），对比恢复到 **≈4.85**；
   改后复测 s0/gate/monitor 失败数回到基线（见 §2）。这是「Δ≤12 不足以保证对比度」的实证。

## 4 未做 / 不声称

- **2 个非令牌自定义属性**：`--p`（`app.js` 运行时 `setProperty`，占位进度）、`--gate-pane-max-h`
  （组件局部声明，`test_gate_panes.py` 直接读）——未搬进 `tokens.css`；守卫对它们走白名单并校验真实写入点，
  **不声称**「每个 var 都定义在 tokens.css」这条字面口径。
- **155 条 `legacy.html` 死声明**未清退（按裁决不动），其内仍有旧色值。
- **未做逐态/逐视口人目检截图对比**于本目录（前后截图由批次 4 的 `UI_BATCH4_20261030` 与 measure 读数覆盖）；
  **未**在非 Chromium、真机滚动条、暗色主题下验证。
- 冻结的 `.ui-audit/3b/selfcheck_final.py` 是**实现前**锚定物，实现后重跑会 1 项预期 FAIL（map↔CSS 行锚），
  **不是**验收门；门是 `loop/tests/test_ui_tokens.py`。
