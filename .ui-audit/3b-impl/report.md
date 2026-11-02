# UI 批次 3B · 配色令牌化（`tokens.css` 唯一色源）· 实现报告

> 实现 owner：`token-owner`（本文件作者）｜计划：[`doc/plans/2026-10-30-ui-color-tokens-3b.md`](../../doc/plans/2026-10-30-ui-color-tokens-3b.md)
> 人裁：**接受 69 个颜色令牌、每条颜色到令牌的 ΔRGB ≤12（实色与 alpha 合成后都 ≤12）**。
> 设计输入（只读、实现前冻结）：`.ui-audit/3b/{tokens-final.css,map-final.tsv,map-values-final.tsv,absorption-final.md,gaps-final.md,selfcheck-final.txt}`。
> 本目录（`.ui-audit/3b-impl/**`）是**实现方证据**：快照、脚本、红/绿原始输出、复核输出。只增不改。

## 0 结论摘要

| 判据 | 目标 | 实测 | 结论 |
|---|---|---|---|
| 组件层 `app.css` 颜色字面量 | 0 | **0**（实现前 323） | ✅ |
| 组件层 `legacy.css` 颜色字面量 | 0 | **0**（实现前 59） | ✅ |
| `legacy.html` **活**规则颜色字面量 | 0 | **0**（3 条活值 → `var()`；155 条死声明按人裁不动） | ✅ |
| 颜色令牌数 | 69（±0） | **69**（+5 非颜色 = 74 变量） | ✅ |
| `var(--x)` 未定义 | 0 | **0**（另有 2 个非令牌运行时/局部变量，§7 说明） | ✅ |
| map 382 条落空（unmapped） | 0 | **0**（382/382 逐条应用，逐文件计数与 map 完全一致） | ✅ |
| 实际替换条数 | map 382 | **382** = app.css 323 + legacy.css 59（+ legacy.html 3） | ✅ |
| 5 个静态用例 | 全绿 | **30 passed**（tokens 9 + css_structure 2 + typography 3 + icons 10 + gate_copy 6） | ✅ |
| 浏览器对比度 / 焦点环 / 截图 / measure.py | —— | **未跑、不声称**（Lead 独占浏览器） | ⏳ |

## 1 写权边界

**只写了**：`loop/web/{tokens.css,app.css,legacy.css,legacy.html}`、新增 `loop/tests/test_ui_tokens.py`、`.ui-audit/3b-impl/**`。

**没有写**（逐条自证）：`doc/**`、`kb/**`、`loop/services|host|workflows/**`、任何既有测试、
`loop/web/{index.html,app.js,s0.js,node-detail.js}`、`.ui-audit/3b/**`（分析员交付）。
未执行任何 git 写命令（只用过 `git status --porcelain` 读状态）。

**回滚**：实现前四文件快照在 `snap-before/`（md5 见 §2），回滚 = 按快照覆盖回 `loop/web/`。

## 2 四文件 md5（前后）

| 文件 | 实现前（= 冻结基线） | 实现后 | 行数 |
|---|---|---|---|
| `loop/web/tokens.css` | `3d23134177964d8e2b2749a241f55a43` | `2eee8a67befa10308c56aadb1f71ef2f` | 18 → 92 |
| `loop/web/app.css` | `4d4a7867c397a77f81f1ad3814cebd08`（= map 锚点） | `e0aace636099289edd8398e0e6d3c440` | 1015 → 1015 |
| `loop/web/legacy.css` | `149153746ed1fa738b56aebea7db1e40`（= map 锚点） | `91f647c090ba78631417a1e857539711` | 81 → 81 |
| `loop/web/legacy.html` | `6efe19041973dd727f80bcb0b365ee08` | `c0270e2001de8675597dd25bada46168` | 1794 → 1794 |

实现前 md5 与 `map-final.tsv` / `gaps-final.md` 声明的锚点**逐位一致** ⇒ 映射针对的就是这份工作树，
不存在行号漂移前提。`app.css`/`legacy.css`/`legacy.html` 行数不变 ⇒ 没有 reflow、没有增删声明。

## 3 TDD：先红后绿

| 阶段 | 证据文件 | 关键输出 |
|---|---|---|
| 红（写守卫、未实现） | `red-tokens.txt` | `组件层仍有 382 处颜色字面量` / `活规则仍有颜色字面量，共 3 处` / `颜色令牌 24 个，人裁是 69 个` / **3 failed, 6 passed** |
| 绿（实现后） | `green-tokens.txt` | **9 passed** |

红测只有这 3 条判据是红的（另外 6 条在实现前就成立：死声明存在、style 属性无色值、反空扫、非颜色令牌集合、
本地无色变量、`--ease-out`/`color-scheme` 契约），说明守卫不是「一律红」也不是「一律绿」。

## 4 逐文件替换结果

| 文件 | 替换条数 | 其他行改动 | 字面量 前→后 | `var()` 用量 前→后 |
|---|---|---|---|---|
| `app.css` | **323** | 0 | 323 → **0** | 484 → 807（+323，正好等于替换数） |
| `legacy.css` | **59** | 0 | 59 → **0** | 80 → 139（+59） |
| `legacy.html` | **3**（活值） | 0 | 158 → 155（余 155 条死声明，按人裁不动） | 0 → 3 |
| **合计** | **385** | 0 | —— | —— |

- `app.css`/`legacy.css` 用脚本按**值级映射**原位替换（`apply_tokens.py`）：先 dry-run 逐条打印
  382 行计划（`dryrun-applegacy.txt`），再 `--apply`（`apply-applegacy.txt`），应用后自检「剩余字面量=0」。
- `legacy.html` 只做 3 处定点 `edit`，`diff` 恰好 3 行（`.chain-arrow`→`var(--arrow-ink)`、
  `.toast-item.err`→`var(--toast-err)`、`.toast-item.ok`→`var(--toast-ok)`，三者 ΔRGB 全 = 0）。
- 只改颜色字面量：选择器、声明顺序、其它值、格式、注释一律未动（见 §5 的骨架恒等证明）。

## 5 独立复核（不复用替换算法）

`verify_surgical.py` → `verify-surgical.txt`，用**冻结的 `map-final.tsv`（file/line/property/literal/token）**
做 oracle，三道检查全 PASS：

1. **骨架恒等**：把「before 的颜色字面量」与「after 的 `var(--…)`」都抹成同一标记后，`app.css`/`legacy.css`
   的**声明文本逐字相等** ⇒ 属性名、单位、顺序、其它值一字未动，改动只发生在色值位置。
2. **逐位置对齐**：两侧标记数相等且位置一一对应；每个原字面量位置必须换成**映射指定的**令牌
   （不是「随便一个令牌」）；**既有 `var()` 必须原样留在原位**（未被顺手换掉）。
   结果：`按位置逐条核对：app.css 323 条、legacy.css 59 条，合计 382`。
3. **map 逐行命中**：382 行按冻结的 `file/line/property` 逐行核对——该行 before 确有该字面量、
   after 对应属性的声明值里确有 `var(--token)`，次数与 map 行数一致。`map-final 行数：382`。

**ΔRGB 重算**（不信任 map 的 delta 列）：从 `tokens.css` 取令牌值、从 `map-final.tsv` 取字面量，
对 **355 条实色行**按 Chebyshev 距离重算 ΔRGB：**与 map 的 delta 列 382 行里实色 355 行逐条相等**，
`实色 max ΔRGB = 12`，无一条 >12。alpha 27 条按冻结证据（`selfcheck-final.txt`：合成后 27/27 ≤12，max 10）执行，
替换脚本另断言「所应用行的 map delta ≤12」，否则中止不写盘。

## 6 令牌层结果

- `tokens.css` = **`.ui-audit/3b/tokens-final.css` 原文**（`diff` 为空，md5 相同），
  保留 `color-scheme:light`；`--shadow/--radius/--ease-out/--font-*` 5 个非颜色令牌原样。
- **颜色令牌 69**（判据：值本身**整体**是一个色值；`--shadow` 的值含 alpha 色值但整体是阴影表达式 ⇒ 不计入颜色令牌）。
  `69 + 5 = 74` 个变量，与 `selfcheck-final.txt` 的「颜色 69 / 全部 74」一致。
- **69 个颜色令牌全部被组件层引用**（无死令牌），组件层 `var()` 引用总数 **949**：
  `--line` 135 / `--muted` 103 / `--bg` 54 / `--rail-muted` … 完整每令牌计数见 `stats.txt`。
- `--arrow-ink` / `--toast-err` / `--toast-ok` 各被 `legacy.html` 引用 1 次（`inline_only`，不进 CSS 吸收）。
- **`var(--x)` 未定义 = 0**（守卫 `test_tokens_css_defines_every_used_variable`）。

## 7 偏离 / 需要 Lead 知道的事

| # | 事项 | 处理 | 需要谁做什么 |
|---|---|---|---|
| 1 | **2 个非令牌自定义属性**：`--p`（`app.js` 运行时 `setProperty("--p", ratio)`，以 `var(--p,0)` 消费）、`--gate-pane-max-h`（`app.css` L443 的**组件局部**声明 `clamp(300px, calc(100dvh - 300px), 860px)`，`tests/browser/test_gate_panes.py` 直接读它） | **未搬进 `tokens.css`**：它们不是颜色，3B 范围外；`--gate-pane-max-h` 若搬成全局 `:root` 令牌会改变语义且超出本批写权 | 若 Lead 认为「每个 var 都必须在 tokens.css」要严格执行，需单开一批（改 `app.css` 局部声明 + 可能影响 gate_panes 用例），本批**不声称**满足该字面口径 |
| 2 | `gaps-final.md` §3 的括号值笔误：写 `--text-5（#839c8d）`，而 `tokens-final.css`/`map-final.tsv` 的 `--text-5` = `#698872` | 按 **tokens-final + 值级 map** 执行；重算 `#60846a→#698872` 的 Δ = **9**（与 map 的 Δ9 一致），判据未破 | 分析员/Lead 可修正 `gaps-final.md`（只读文件，我方未改） |
| 3 | `gaps-final.md` §1 写「7 处 `style="…"`」，实测 **9 处**（`index.html` 3 + `legacy.html` 6），**全部 0 色值** | 不影响判据（都是布局），未改动任何 `style` 属性 | 可顺手修文档；`index.html` 不在本批写权内 |
| 4 | 冻结的 `.ui-audit/3b/selfcheck_final.py` 是**实现前**锚定物（比对 map 与当时的 CSS 逐条一致） | 实现后重跑：**1 项 FAIL**（`map-final.tsv 与 CSS 逐条一致（0 条色值 / 382 行）`——因为 CSS 里已经没有字面量了，属**预期**），其余 11 项仍 PASS（69 令牌/74 变量/Δ≤12 355/355/alpha 27/27/内联 3 条）。**未修改 `.ui-audit/3b/**` 任何文件** | Lead 不要把它当实现后的验收门；实现后的门是 `test_ui_tokens.py` + §5 复核 |
| 5 | 跑上述 selfcheck 时它 `import scan_colors`，Python 刷新了 `.ui-audit/3b/__pycache__/scan_colors.cpython-311.pyc`（**仅字节码缓存**，分析员交付的 `.py/.tsv/.md` 内容零改动） | 如实披露；后续未再运行该脚本 | 无需处理（`git status` 里 `.ui-audit/3b/` 整体是未跟踪目录） |

**没有其它偏离**：382 条全部按 map 执行，无一需要人工改判，**不存在「必须偏离 map 的条目」**。

## 8 守卫设计与变异性自检

`loop/tests/test_ui_tokens.py`（9 个用例，软件层、不启浏览器）：

| 用例 | 守的东西 |
|---|---|
| `test_component_css_has_no_color_literals` | `app.css`+`legacy.css` 声明位置色值字面量 = 0 |
| `test_component_layer_actually_consumes_tokens` | 反空扫：`var()` 用量 ≥300（实测 949） |
| `test_legacy_inline_live_rules_have_no_color_literals` | `legacy.html` `<style>` 的**活规则** = 0（判活口径见下） |
| `test_legacy_inline_style_attributes_have_no_color_literals` | 6 个 `style="…"` 属性 = 0 |
| `test_dead_inline_declarations_stay_untouched_by_design` | 155 条死声明**按设计保留**（显式单列，将来清退只改这一个用例） |
| `test_tokens_css_defines_every_used_variable` | 每个 `var(--x)` 可解析；组件层**本地声明里不许有颜色变量**（防第二色源） |
| `test_runtime_variable_allowlist_is_still_real` | `--p` 白名单必须在 `app.js` 真有 `setProperty` 写入点（防白名单腐化） |
| `test_color_token_count_is_the_adjudicated_69` | 颜色令牌 = 69 ±0；非颜色令牌 = 原 5 个 |
| `test_tokens_css_stays_light_local_and_on_the_motion_contract` | `color-scheme:light`、无 `@font-face`/`url(`/外链/`Inter`、`--ease-out` 仍是 `cubic-bezier(0.22,1,0.36,1)`（护住既有浏览器用例 `test_tokens_and_motion_contract`） |

**扫描口径的两个关键点**（否则会假红/假绿）：
1. **只扫声明位置**：`#banners{…}`、`aside #btnNew{…}` 这类 **ID 选择器**不是色值。做法是把选择器前导
   等长涂空（保留换行 ⇒ 行号不变）后再匹配。实测涂空后得 `app.css` 323 / `legacy.css` 59，
   与 `map-final.tsv` 的 323+59 **完全一致** ⇒ 证明这就是分析员的口径。
2. **"活规则"判据** = 该选择器单元**没有被后加载的 tokens/legacy/app 重新声明**（与 `.ui-audit/3b/_gen-inline.md`
   的「158 条色值 / 88 个被覆盖选择器 / 3 个未覆盖」一致；选择器按顶层逗号拆单元、`a > b` 与 `a>b` 归一）。
   实测活单元里**带色的恰好 3 个**：`.chain-arrow` / `.toast-item.err` / `.toast-item.ok` —— 与分析员证据**逐条吻合**。
   （本守卫统计的规则总数 127 条 / 选择器单元 137 个，与分析员口径的「91 个选择器」计数方式不同，
   但**结论集合（3 条活带色规则）完全相同**，判据落在结论上。）

**变异性自检**（`guard_mutation.py` → `guard-mutation.txt`，全 PASS）：回填 `#fff`/`rgba()`/`hsl()` 各能被抓到；
`#banners`/注释里的旧值/`transparent`/`inherit` **不误报**；一行两个色值能分别抓到；
选择器归一正确；3 条内联活规则仍在活集合里且其声明无字面量。

## 9 静态用例原始输出

`static-5-suites.txt`（命令与输出原样）：

```
cd loop && .venv/bin/python -m pytest tests/test_ui_tokens.py tests/test_ui_css_structure.py \
  tests/test_ui_typography.py tests/test_ui_icons.py tests/test_ui_gate_copy.py -q
..............................                                           [100%]
30 passed in 0.84s
```

另跑了受本批直接影响的软件层冒烟（不在任务要求的 5 个里，但会读 `/app.css`）：
`tests/test_web_smoke.py` → **6 passed, 1 warning**。

`test_ui_css_structure.py` 绿 ⇒ 选择器结构与 F14 收敛未被破坏（替换未触碰选择器）；
`test_ui_typography.py` 绿 ⇒ 字号阶梯不受影响（颜色与字号正交）。

## 10 未做 / 不声称

- **浏览器验证全部未跑**（按写权：Lead 独占浏览器）。未跑：`tests/browser/test_ui_visual_20261030.py`
  的对比度探针与焦点环、`measure.py` 前后测量、三视口截图。**不声称可读性/视觉无回退**。
- 未改任何令牌值以迁就浏览器用例；若对比度探针回退，属**令牌值层面**问题，需 Lead 回头一起处理
  （本批只做「字面量 → 令牌」的机械替换，ΔRGB 已按人裁 ≤12 执行）。
- 未处理 `mockup.html`（§14 静态历史样张，不参与）、`favicon.svg`（非 CSS 组件层）。
- 未清退 `legacy.html` 的 155 条死声明（人裁：属结构清理批次）。
- 未做暗色主题 / 非 Chromium / 真机滚动条验证。

## 11 需要 Lead 跑的浏览器验证（建议清单 + 关注点）

```bash
cd loop && PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home \
  TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser
```

| 优先 | 用例 | 为什么可能受影响 |
|---|---|---|
| 1 | `test_ui_visual_20261030.py` 的 A13 **对比度探针**（S0/gate/monitor 三区） | 令牌值与原字面量有 ΔRGB≤12 的差；判据是 `<4.5` 的非装饰文本数量不增加 |
| 2 | `test_ui_visual_20261030.py::test_focus_ring_contrast` | `outline`/`outline-color` 有 2 条换成令牌（`--primary` 等），焦点环对背景的比值需 ≥3 |
| 3 | `test_ui_visual_20261030.py::test_tokens_and_motion_contract` | 纯静态，但正是本批的契约面（`--ease-out`、无 `@font-face`/`url(`）；守卫已镜像它，仍建议实跑 |
| 4 | `test_gate_panes.py`（读 `--gate-pane-max-h`） | 该 token 仍留在 `app.css` 局部声明（未搬），应不受影响；确认无意外 |
| 5 | `test_node_detail.py`（含读 `app.css` 的静态断言） | 只是 `read_text` 找选择器字符串，替换未动选择器；确认无意外 |
| 6 | 三视口截图前后对比 + `measure.py`（用 `.ui-audit/measure.py`，不写冻结证据） | 人裁要求「≤12 色差不可辨」的人工目检 |

**回退路径**：若浏览器门红在色差上，`snap-before/` 四文件可直接覆盖回滚（不需要 git）。

## 12 本目录文件清单

| 文件 | 说明 |
|---|---|
| `snap-before/{tokens,app,legacy}.css`、`legacy.html` | 实现前快照（md5 见 §2），回滚用 |
| `red-tokens.txt` / `green-tokens.txt` | TDD 红/绿**原始输出**（含 md5 与时间戳） |
| `dryrun-applegacy.txt` | 替换脚本 dry-run：382 条逐条计划（`文件:行 字面量 -> 令牌 ΔRGB`） |
| `apply-applegacy.txt` | `--apply` 原始输出 + 应用后自检「剩余字面量=0」 |
| `verify-surgical.txt` | 独立复核（骨架恒等 / 逐位置对齐 / map 逐行命中）原始输出 |
| `stats.txt` | 前后字面量、`var()` 用量、令牌 74 个逐条引用次数 |
| `static-5-suites.txt` | 5 个静态用例 + web 冒烟**原始输出** |
| `guard-mutation.txt` | 守卫变异性自检（会红、不误报）原始输出 |
| `apply_tokens.py` / `verify_surgical.py` / `stats.py` / `guard_mutation.py` / `probe*.py` | 可重跑的脚本（`probe*` 是开工前确定扫描口径的探针） |
