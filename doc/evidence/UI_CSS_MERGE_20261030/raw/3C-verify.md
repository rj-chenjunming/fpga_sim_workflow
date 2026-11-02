# 3C 独立复核报告 · F14 两段式 CSS 合并（行为保持）

- 复核员：`verifier-3c`（只读；本轮**未**修改 `loop/**`、`doc/**`、`kb/**`、`.ui-audit/3c/**`，未使用任何 git 写命令）
- 复核窗口：2026-10-30 14:23 — 15:15（本机时钟）；浏览器指纹我自己开跑时间 **15:05:45**
- 本报告只写 `.ui-audit/3C-verify.md` 与 `.ui-audit/3c-verify-tmp/` 下的临时件（清单见 §⑧）
- 结论数字全部来自**本轮我自己跑的**命令输出，未抄实现者数字；凡采纳实现者数字处均标「已独立复算」或「未复核」

---

## ① 结论

**可合入（但仅在 `app-after-3c.css` 这一份产物口径下；`loop/web/app.css` 现含批次 4/4C 的正当改动，不在本结论范围）。**

| 等级 | 计数 | 说明 |
|---|---|---|
| **P0** | **0 未修**（发现 1，已修并复验） | ①「同名选择器跨 `@media` 上下文」被错误合并 ⇒ 窄断点计算样式真变。旧工具在 pre-fix staging 造成 **23 处 / 11 个选择器**的生效先后翻转；实现者修 `classify` 后受阻组 9→24，最终产物上我的检查 **PASS** |
| **P1** | 1 | 共命中证据的「零命中 ⇒ 从未共命中 ⇒ 可豁免」是 **vacuous** 逻辑：264/788（33.5%）个 `app.css` 选择器在 36 个组合里一次都没命中，涉及它们的翻转对（最终产物上 4058 个同上下文对 + 255 个跨上下文对）实际**没有**运行时证据支撑，只是「没测到」。本轮未发现由此产生的具体行为差异，但 §2.4 的 fail-closed 声称比实现更强 |
| **P2** | 6 | 计划 §1 的基线数字不可复算；计划 §2.1/§3 的「51 个断点宽度」实为 50；守卫 docstring 与实现不一致（146/「白名单当前为空」/「≈900」）；`merge_plan.py` 在证据缺失时崩而非 fail-closed（且分批脚本把崩溃当成「无可合并组」收工）；`merge-plan.json` 与最终产物不一致（`.run-list` 在 plan 里受阻、在最终产物里已合并）；文档门在「仓内 TMPDIR=`.chrome-tmp`」下会把自己单测的假仓库夹具扫成 5 条 missing（见 §6.3） |

**计算样式与结构收敛的最终判读（我自己跑 + 我自己判读，详见 §6.5）**

- 我自己的 **72 组合**（3 主视口 × (9 主状态 + 15 交互态)，含 `transition-*`/`animation-*`、`::before`/`::after`、样式表规则序列）＝ **元素级差异 0**；69 条组合差异 **100% 是 `ruleset` 项**（3 个无差异组合是 `legacy` 态，它不加载 `app.css`）。
- 实现者跑的 **196 组合**全断点产物，我解析其 JSON 独立复核：190 条差异 **100% 是 `ruleset` 项、0 条含元素级差异**。`943 → 817`（`app.css` 的 `cssRules.length`）我用**独立解析器**复算一致：`917 + 52(逗号拆分) − 178(合并删规则) = 791`，加 26 条 at-rule 块 ⇒ `943 → 817`；at-rule 块两侧均为 26 条（24 `@media` + 2 `@keyframes`），**未变**。
- 逐元素哈希抽查 6 个组合（含 760 / 851 / 1000 三个窄断点，正是旧 P0 的现形区间）：元素数与逐元素哈希**全等，不一致元素 0**。
- ⇒ **计算样式零差异 + 规则序列按预期收敛（943→817）**；这 190 条 `ruleset` 差异是 F14 的结构目标，不是行为变化。

**不是 P0 但必须写进 STATUS 的两条事实**
1. 逐批 `--no-sweep` 指纹（24 组合，最窄 1280px）**在原理上**看不见 §①P0 那类跨断点改动 —— `batches.log` 全 PASS 不构成「行为保持」证据。这一点已由 23 处翻转实证。
2. 3C 产物与 `loop/web/app.css` 不是同一个文件：3C 产物 md5 `73430cb2b6b16d74b74a0e30dc3643ad`（1008 行）；`loop/web/app.css` 复核时为 `4d4a7867c397a77f81f1ad3814cebd08`（1015 行，= 3C + 批次 4 的图标 sprite 5 条 + 4C 的 `--gate-pane-max-h`）。因此「值逐字未变 / `@media` 条件未变」只能对 `snap-before` ↔ `app-after-3c.css` 做，本报告即按此口径。

---

## ② 复核对象与快照 md5

| 对象 | 路径 | md5 / 规模 |
|---|---|---|
| 计划 | `doc/plans/2026-10-30-ui-css-merge-f14c.md` | `44cee172a29a13871429e108d8735b5a` |
| **before（pristine）** | `.ui-audit/3c/snap-before/app.css` | `103ec75124e21c6c97a717d7607fa132`，1213 行 |
| **after（3C 产物，定格）** | `.ui-audit/3c/app-after-3c.css` | `73430cb2b6b16d74b74a0e30dc3643ad`，1008 行 |
| 同一内容的 staging 目录 | `.ui-audit/3c/web-stage/app.css` | 同上 md5（复核时一致） |
| 落盘后的工作树文件（含批次 4/4C） | `loop/web/app.css` | 复核期间两次取值：`4d4a7867c397a77f81f1ad3814cebd08`（1015 行，14:51）→ `e0aace636099289edd8398e0e6d3c440`（15:20，批次 4 仍在落盘）。**两者都含 3C 之外的正当改动，不在本结论范围** |
| 新守卫 | `loop/tests/test_ui_css_structure.py` | `117921847bdc6e94ed83faf2cfffc51e` |
| 字号守卫 | `loop/tests/test_ui_typography.py` | `5f331ef3497b43d990c6d0da28cc365f` |
| 合并工具（已修版） | `.ui-audit/3c/merge_plan.py` | `8b3c6f0e8f271aae3c9c876327f7d95f` |
| 合并计划（已修版） | `.ui-audit/3c/merge-plan.json` | `88e6e4b9c00d32259a5d76b62e17668b` |
| 共命中证据 | `.ui-audit/3c/cooccur-full.json` | `141b1e3fac75098300579ffdff521826` |
| 我的独立解析/判据器 | `.ui-audit/3c-verify-tmp/indep_cascade.py` | 见 §③ |
| 我的跨上下文检查器 | `.ui-audit/3c-verify-tmp/cross_ctx_check.py` | `c539a87f2ba21a06ad1a2ad5dc92b5c1` |

**文件级「只动了 CSS」**：`web-stage/` 25 个文件中，除 `app.css` 外 **24 个与 `snap-before` 逐字节一致**（`cmp` 逐个比对，差值 0）。批次 4 的改动只出现在 `loop/web/`，未污染 3C staging。

**快照口径说明**：我另存了过程快照 `stage-142459.css`（batch 7，`239fac3443cc…`）与 `stage-FINAL-f047bf6b.css`（旧工具跑完 13 批，`f047bf6b7d99…`），用于定位 P0 的时间线；最终结论只用 `app-after-3c.css`。

---

## ③ diff 审查结果（值逐字未变 / `@media` 未变 / 无新 `!important`）

### 3.1 方法与抽样原则

不目测。我自写解析器（括号深度 + 字符串/注释感知，**不 import 被测的 `load_structure`，也不 import `merge_plan.py`**），做三件事：

1. 把 `(上下文, 简单选择器)` 作为键，把该选择器在**所有**规则里的声明按文档顺序串成一条链；
2. 在 before 的链上按「同属性、`!important` 优先、同重要性后置胜」算出唯一胜者，其余标记为被支配；
3. 断言 **after 的链 == before 的链去掉被支配者**，逐字（`prop` / `value` 原文 / `important`）比较。

抽样不是「挑几条看」，而是**全量 946 个键逐键比较**；下面只列样本便于人工目检。

### 3.2 结果（全量）

```
before: 1076 条规则 / 946 个(上下文,简单选择器)键 / 3329 条声明实例
after :  970 条规则 / 946 个键 / 3285 条声明实例
键新增 0；键消失 0；未合并键 23（其中串与 before 不等 0）；已合并键声明串不等 0
被判定支配并删除的声明实例：45
```

- **0 处值变化**：任何一条被保留的声明，`prop`、`value` 原文、`!important` 三项都与 before 完全一致；已合并的 923 个键无一例外。
- **0 处乱序**：合并把整组声明按原文档顺序搬到「最后一条规则」的位置，块内顺序未重排（链比较天然覆盖这一点：若重排，`font` 简写与 `font-size`/`font-family` 的先后会改变逐字串）。
- **45 条被删声明全部可解释**：去重后是 33 个 `(上下文, 选择器, 属性, 值, 重要性)` 元组；我独立验证**这 33 个元组 100% 属于「同上下文、同选择器、同属性、被更靠后的声明支配」**，没有一条是不该删的（`仅 after 有` 的元组数 = 0，即没有凭空出现的新值）。

### 3.3 抽样（人工可核）

| 选择器 | before | after | 判定 |
|---|---|---|---|
| `.mono` | `font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace` | `font-family:var(--font-mono)` | 前者被后段同名声明支配，删之无行为变化（§2.4 记录的 `input.mono` 事故就是这条，现由 `.input`/`.mono` 共命中 354 例挡在门外） |
| `.s0-access` | `font-size:10px` | `font-size:12px` | 10px 被后段 `font-size:12px` 支配 |
| `.nd-raw` | `margin-top:10px` | `margin-top:0` | 10px 被后段 `margin-top:0` 支配 |
| `textarea.input` | `height:42px`、`padding:0 13px` | `height:auto`、`padding:11px 13px` | 两条被后段同名声明支配；`font:inherit` 与后置 `font-size:14px` 的相对顺序保持不变 |
| `.alert.bad` | `border-color:#f5c6c6` | `border-color:#ebc4bf` | 被后段 `.banner.bad,.alert.bad` 的 `#ebc4bf` 支配（`background`/`color` 仍保留前者） |

### 3.4 新增 `!important`：无

- **不同** `(上下文, 选择器, 属性)` 且带 `!important` 的集合：before 11 个 = after 11 个，**完全相同**（差集空）。
- 实例数 5 → 11 是**计数副作用**：`@media(prefers-reduced-motion:reduce){*,*:before,*:after{…!important}}` 这一条逗号规则被拆成三条规则，3 条 `!important` 声明变成 9 条；值、属性、上下文都没变。

### 3.5 `@media` 条件：未变

- `@media`/`@supports` 条件集合 before 16 个 = after 16 个，**集合完全相同**（差集空），`prefers-reduced-motion`、`min-width:1101px and max-width:1390px` 等均原样。
- 块内规则数变化（如 `max-width:760px` 66→75）来自块内逗号规则拆分，不是条件改动、也不是块重排（两个 `@media(max-width:760px)` 块在前后都是 6 个，未合并）。

### 3.6 其它「值未变」旁证

- **不同 `(属性, 值, !important)` 组合**：before 869 / after 868（少的那 1 个是被支配的老值）；带 `!important` 的不同组合 before 4 = after 4。
- **hex 字面量**：不同 hex **值集合** before 191 = after 191（完全相同）；实例多重集 321→325 是逗号规则拆分导致的同值重复计数，不是新颜色。
- **diff 规模**：28 个 hunk、净删 374 行、净增 169 行（1213 → 1008 行），全部可由「删早期规则 + 在末条规则处合并 + 拆逗号规则」解释。

---

## ④ 独立结构复算（与守卫、与计划对账）

### 4.1 我的解析器 vs 守卫 vs 计划的数字

| 口径 | before | after | 对账 |
|---|---|---|---|
| 我的解析器：解析规则（含 `@keyframes` 内层 4 条） | 1080 | 974 | 与实现者「pristine 1080 / 合并后 974」一致 |
| 我的解析器：顶层规则 | 917 | **791** | 与实现者「合并后顶层 791」一致 |
| 拆分逗号规则后的口径（我的复算副本） | **1160 / 969** | — | 与实现者「pristine 顶层 969、解析 1160」一致（实现者用的是拆分后口径） |
| 守卫 `load_structure`：简单选择器实例 / 不同键 / 重复 | **1156 / 946 / 193** | **970 / 946 / 23** | 与 `red-test-pristine.txt` 的 193 一致；after 23 与实现者一致 |
| 我的独立解析器：(选择器文本,上下文) 重复组 | 153 组 / 307 条 | **23 组 / 47 条** | 与守卫的 193→23 同源（守卫按简单选择器计数） |
| 我的独立解析器：简单选择器重复 | **193** 个 / 403 条 | **23** 个 / 47 条 | 与守卫逐数字一致 |

**重复集合与白名单完全对齐**：after 的 23 个 `(上下文, 选择器)` 重复项与 `ALLOWED` **集合相等**（既无陈旧条目、也无遗漏条目），在 `app-after-3c.css` 与 `loop/web/app.css` 上分别跑都是这个结果。

### 4.2 23 条例外的独立归因

我把 23 条拆成我自己能复算的两类：

- **20 条 = 同名选择器跨 `@media` 上下文**（`.agents` `.toast` `.phase-card` `.s0-phases` `.grid2` `.run-item` `.agent-window` `.aw-head` `.aw-intervene` `.aw-log-row` `.aw-log-row>span` `.aw-terminal-mark` `.aw-timeline` `.shell` `header` `.rail-entry` `aside #btnNew` 及其 `@media(max-width:760px)` 版本）：我从 pristine 独立枚举出 **21** 个「同名跨上下文且值真不同」的组，与工具修复后新增的 15 个受阻组 + 旧工具已挡的 6 个**一一对应**（见 §⑤）。
- **3 条 = 共命中证据类**：`.btn`、`.card`、`.input`。我逐条核对 `cooccur-full.json`：`.btn`×`.btn-ghost`=**369**、`.btn`×`.rail-entry`=**33**、`.card`×`.gate-card`=**33**、`.input`×`.mono`=**354**（`input mono` 样本元素存在）—— 白名单理由里引用的证据都能对上。

### 4.3 `.run-list` 的「安全合并」核实（实现者点名要我核）

- pristine：顶层 2 条（L53 `overflow:auto;flex:1`、L514 `padding…`）+ `@media(max-width:760px)` 两条（块 1 `flex:none;overflow-x:auto`、块 2 `min-height:0;max-height:108px;…`）。
- 最终产物：顶层合并为 1 条（line 318）+ `@media(max-width:760px)` 合并为 1 条（line 533，`flex:none;overflow-x:auto;min-height:0;…`）。
- **顺序**：顶层合并位（318）在 media 合并位（533）**之前** ⇒ ≤760px 仍由 media 的 `flex:none` 胜出，与 pristine 一致。`cross_ctx_check.py` 对最终产物 **PASS**（0 翻转）。
- 但有一点要记：单遍 `plan`（同一 pristine 拆分输入）里 `.run-list` 是**受阻**的，分批重跑在**第 10 批**才合并 —— 因为竞争规则自己也被搬动了。工具的逐条局部判据看不到这层；结论正确是靠「最终产物级全局判据」兜住的。这是「局部判据 + 产物级判据互补」的一个实例，不是缺陷。

---

## ⑤ 工具判别性注入（在临时副本上做，未动被测文件）

### 5.1 注入清单与结果

| # | 目的 | 输入（合成 CSS） | 期望 | 实际 |
|---|---|---|---|---|
| **a2** | 复现 P0：同名选择器跨 `@media` | `.phase-card{align-items:center}` / `@media(max-width:1000px){.phase-card{align-items:start}}` / `.phase-card{padding:1px}`，用**真**证据文件 | 受阻 | **旧工具：合并** → 输出 `@media(…){…start}` 在前、`.phase-card{align-items:center;padding:1px}` 在后，**行为反转且不报受阻** |
| a3 | fail-closed 对照 | 同 a2，但把 `.phase-card` 从证据 `selector_sanitized` 里删掉 | 受阻 | 0 合并 ✔（理由「未被共命中证据覆盖 ⇒ 不能豁免」） |
| a5 | 真共命中必须挡 | `.any-a{…center}` / `.any-b{…start}` / `.any-a{padding:0}`，证据里 a×b 共命中 3 | 受阻 | 0 合并 ✔，`plan --verbose` 打印「共命中证据显示确实命中同一元素」 |
| c | 胜者判定：`!important` 优先于源码顺序 | `.e{color:red!important}` / `.e{color:blue}` / `.e{margin:0}` | 保留 `red!important`，删 `blue` | 输出 `.e{color:red!important;margin:0;}` ✔ |
| d2 | 简写按 longhand 展开 | `.g{font:14px/1.5 sans-serif}` / `.h{font-size:20px}` / `.g{padding:0}`，证据里 g×h 共命中 | 受阻（`font` 展开含 `font-size`） | 0 合并 ✔ |
| d2n | 证据「测过且不共命中」应放行 | 同 d2，但证据 g×h **不**共命中 | 合并 | 合并 ✔（`font` 搬到 `.h` 之后；这是 §2.4 的既定豁免口径） |
| j | 重要性不同不算竞争者 | `.j{color:red!important}` / `.k{color:blue}` / `.j{padding:0}`，证据 j×k **共命中** | 合并（重要性永远优先，源码先后无关） | 合并 ✔，输出 `.k{color:blue}` 在前、`.j{color:red!important;padding:0}` 在后 |
| a4 | 证据文件缺失时的 fail-closed | 任意两段 CSS + `--evidence ""` | 受阻 | **崩溃**：`TypeError: argument of type 'NoneType' is not iterable`（`classify` 用 `pair in co`，`co=None`）⇒ 见 §①P2 |

### 5.2 修复前后：同一输入的受阻组数（我独立复跑，未采信实现者数字）

输入 = `snap-before` 的拆分副本（`merge_plan.py split --apply`，1213→1218 行），证据 = 真 `cooccur-full.json`：

| 工具版本 | 可合并组 | 安全 | 受阻 | `.agents/.run-list/.toast/.phase-card` |
|---|---|---|---|---|
| 旧（我 14:26 留的副本 `.ui-audit/3c-verify-tmp/merge_plan_copy.py`） | 193 | 184 | **9** | 全部**放行** |
| 新（修复版） | 193 | 169 | **24** | 全部**受阻** |

- 我另做的独立枚举（不看 `classify`，直接扫「同 sanitize 选择器 + 窗口内 + longhand 碰撞 + 同重要性 + 值不同」）：**21 组**。
- 关系：`21 = 新增 15 + 旧工具已挡 6`，且 `新增 15 ⊆ 我的 21`、`我的 21 ⊆ 新 24` —— **一一对应，无漏挡、无凭空多挡**。
- 修复后 `blocked_detail` 24 条与我复跑结果逐条一致（`.run-list` 在单遍 plan 里受阻，见 §4.3 的批序说明）。

### 5.3 P0 的实测破坏面（pre-fix staging，旧工具产物）

用 `cross_ctx_check.py` 对比 `snap-before` ↔ 旧 staging（`f047bf6b`，13 批跑完）：**23 条 FAIL / 11 个选择器**。对照组（`snap-before` ↔ `snap-before`）= 0；batch 7 的中间快照 = 7 条 / 4 个选择器（我 14:23 据此先报了 4 个，后 11 个是批次 8–13 合并重复 `@media` 块内规则时新增的）。

| 选择器 | 属性 | before 生效 | after 生效 | 断点 |
|---|---|---|---|---|
| `.agents` | `grid-template-columns` | `1fr` | `1fr 1fr` | ≤1100 |
| `.run-list` | `flex`（grow/shrink/basis） | `none` | `1` | ≤760 |
| `.toast` | `right` / `max-width` | `16px` / `none` | `22px` / `420px` | ≤760 |
| `.phase-card` | `align-items` | `start` | `center` | 761–1000 |
| `.s0-phases` | `grid-template-columns` / `gap` / `margin-bottom` | `1fr` 等 | `1fr 1fr` 等 | ≤760 |
| `.shell` | `min-height` | `calc(100vh - 59px)` | `calc(100vh - 72px)` | ≤760 |
| `header` | `gap` | `9px` | `16px` | ≤760 |
| `.aw-head` / `.aw-intervene` / `.aw-log-row` / `.aw-log-row>span` / `.aw-terminal-mark` / `.aw-timeline` | `gap` / `border-left` / `flex` / `max-height` / `font` | — | — | ≤850 |

**最终产物上这套检查 = PASS**：

```
$ python3 .ui-audit/3c-verify-tmp/cross_ctx_check.py .ui-audit/3c/snap-before/app.css .ui-audit/3c/app-after-3c.css
before=.ui-audit/3c/snap-before/app.css
after =.ui-audit/3c/app-after-3c.css
跨 @ 上下文、同选择器、同属性、可能同时生效、值不同的对：0 处翻转
PASS: 未发现同名选择器跨 @ 上下文的发生效先后翻转
exit=0
```

**可复跑检查的用法（实现者可重跑）**：`python3 .ui-audit/3c-verify-tmp/cross_ctx_check.py <before.css> <after.css>`；退出码 0 = 无翻转、1 = 有翻转（逐条打印属性/两段值/两段生效位置）、2 = 参数错。判据不依赖共命中证据：同一简单选择器在两个可能同时生效的上下文各有同 longhand 声明且值不同时，「文档更靠后者」即生效者，互换即失败。

### 5.4 同上下文（非跨上下文）的翻转分析

按 longhand 展开、同特异性同重要性、`may_share_element` 保守判「可能共命中」：before/after 之间先后翻转 **11479 对**，其中

- 证据里**确实共命中**⇒ 真风险 **0**；
- 证据**未覆盖**该对 ⇒ **0**（即没有靠「没测到」放行的情况，说明 fail-closed 生效）；
- 证据覆盖且从未共命中 ⇒ 11479 对豁免（含 4058 对是「一侧选择器零命中」的 vacuous 豁免，见 §⑦）。

---

## ⑥ 门原始输出

### 6.1 结构守卫（我自己跑）

```
$ cd loop && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_css_structure.py
..                                                                       [100%]
2 passed in 0.65s
EXIT=0
```

说明：`2 passed` 包含 `test_simple_selectors_are_defined_once_per_context` 与 `test_whitelist_entries_still_duplicated`；后者通过 ⇒ 23 条 `ALLOWED` **全部仍在重复**（无陈旧条目），与 §4.1 的集合相等结论一致。用 `-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1` 跑，避免在 `loop/` 下留缓存。

**15:20 复跑（`loop/web/app.css` 已被批次 4 改成 `e0aace63…` 之后）**：

```
$ cd loop && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_css_structure.py tests/test_ui_typography.py
.....                                                                    [100%]
5 passed in 0.69s
EXIT=0
# 另测：当前 loop/web/app.css 的 total=970 distinct=946 dups=23，重复集合与 ALLOWED 相同=True；字号扫描数=352
```

⇒ 守卫/字号在**当前工作树**（含批次 4 最新改动）上仍绿，且结构数字与 3C 产物一致（批次 4 的图标改动未破坏结构判据）。

### 6.2 字号守卫（我自己跑）

```
$ cd loop && .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ui_typography.py
...                                                                      [100%]
3 passed in 0.61s
EXIT=0
$ # 另取 scan() 实测扫描数（断言阈值 >= 300）
字号扫描实测条数 = 352   （app.css 314 / legacy.html 25 / legacy.css 13）
出现的字号档位 = [10, 11, 12, 13, 14, 16, 18, 20, 24, 30]（全部在 §14 阶梯 [10,11,12,13,14,16,18,20,24,30,36] 内）
```

### 6.3 文档门（我自己跑）

```
$ python3 doc/audit/check_doc_links.py
checked=3289 skipped=47407 historical=857 known_missing=16 env_missing=36 missing=4
EXIT=1
[MISSING] .ui-audit/3b/handoff.md:47  loop/tests/test_ui_tokens.py
[MISSING] .ui-audit/4/gate-identity.md:6  doc/spec/S0_ENVIRONMENT_SPEC.md:11/34
[MISSING] .ui-audit/4/gate-identity.md:27  loop/workflows/chunks/gates.py:61/78
[MISSING] .ui-audit/4/gate-identity.md:52  loop/web/legacy.html:345/354/355
```

**门会随时间漂移，所以我把两次实测都记下来**（同一命令，不同时刻）：

| 时刻 | checked | missing | 构成 |
|---|---|---|---|
| 15:0x（3C 落盘后首次） | 3289 | **4** | `.ui-audit/3b/handoff.md` 1 条 + `.ui-audit/4/gate-identity.md` 3 条 |
| 15:15（写本报告期间） | 3721 | **8** | `.ui-audit/4/gate-identity.md` 3 条 + `.chrome-tmp/` 下 5 条 |

两批 missing 的归因（都不是 3C 产物的断链）：

1. **`.ui-audit/4/gate-identity.md` 3 条**：批次 4 队友的未跟踪临时件，路径写成「行号用 `/` 分隔」（形如 S0 环境规格第 11/34 行、gates.py 第 61/78 行、legacy.html 第 345/354/355 行），检查器只剥离 `:64-67` 这种单行/区间后缀，故判 missing。
2. **`.chrome-tmp/` 下 5 条**：这是**文档门自己的单测夹具**——`loop/tests/test_doc_links.py` 在 `TMPDIR` 下建了一棵「故意含断链」的假仓库（目录名 `test_repo_broken_link_makes_ex0`、`test_known_missing_is_reported0`、`test_env_missing_is_visible_bu0`、`test_resolved_and_skipped_are_0`、`test_historical_docs_are_count0`）。浏览器门的强制 env 是 `TMPDIR=<repo>/.chrome-tmp`，谁在这个 env 下跑过 `test_doc_links.py`，夹具就落在**仓内**，随后又被检查器扫到。`.chrome-tmp*/` 虽已在 `.gitignore` 第 34 行忽略，但检查器不按 gitignore 跳过（只按硬编码的 `loop/state`、`loop/.logs`、`loop/.venv`、`/tmp` 跳过）。
3. **`.ui-audit/3b/handoff.md` 那条在两次实测之间被 3B 自己改掉了**（把反引号里的路径改成纯文本），所以 4→8 不是「新增同类问题」，而是「1 条修掉 + 5 条夹具目录被扫进来」。

- **3C 产物与我的报告贡献的断链：0 条**（我写报告后重跑，`3C-verify.md` 未出现在 `[MISSING]` 列表里）。
- **结论**：文档门本轮红，成因是「并行队友临时件 + 门自己在仓内 TMPDIR 建夹具」，不是 3C 断链。要门绿：批次 4 处理自己的 `gate-identity.md`；门命令改用**仓外** TMPDIR（或让检查器跳过 `.chrome-tmp*/`）。这是**门配置问题（P2）**，建议登记到 STATUS，别当成 3C 失败。

### 6.4 计算样式指纹：我跑的部分 vs 实现者跑的部分

| 项 | 谁跑 | 我的处置 |
|---|---|---|
| **72 组合**（3 主视口 × (9 主状态 + 15 交互态)） | **我跑**（15:05:45 开跑，约 8.5 分钟） | 原始输出 `.ui-audit/3c-verify-tmp/my-nosweep-72.txt`；判读见 §6.5-A |
| **196 组合**（50 个断点宽度 × 状态 + 主视口补充） | 实现者跑，产物 `.ui-audit/3c/final-sweep-3c.txt` | 我**解析其 JSON 独立判读**（§6.5-B）并**独立复算结构账目**；但我没有自己跑这 196 个组合 |

补充说明（诚实）：本会话的命令跑在独立 PID 命名空间里（`ps -ef | wc -l` = 5），**看不到**别的 agent 的 Chromium 进程，所以「开跑前 `ps -ef | grep -c "[c]hrome"` = 0」这条约定在我这边**无法可靠执行**。我实际依赖的是：实现者明确说「浏览器现在可以用了」+ 观测到 `.ui-audit/3c/final-sweep-3c.txt` 已停止增长（15:01 完成）+ 无并发的截图/浏览器产物在写。这是本报告的一处**方法学弱点**，已如实记录。

### 6.5 指纹结果与判读

#### A. 我自己跑的 72 组合（`--no-sweep`）

```
$ PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  loop/.venv/bin/python $R/.ui-audit/3c/verify_style_equivalence.py \
  --before-web $R/.ui-audit/3c/snap-before --after-web $R/.ui-audit/3c/web-stage --no-sweep
…
DIFF: 69 个（宽度, 高度, 状态）组合不一致
EXIT=1
```

解析其 JSON（我自己写的解析，不是看汇总行）：

```
combinations = 72   diff_combinations = 69   len(diffs) = 69
kinds 分布 = {('ruleset',): 69}        含 'style' 的条目 = 0
含 'interaction-unreached' 的条目 = 0
before_rules / after_rules = 1109 / 1003（69 条全部相同）
first_rule_diff = 2（69 条全部落在同一处）
无差异的组合 = legacy @ 1280x720 / 1440x900 / 1920x1080（legacy.html 不加载 app.css）
interaction_unreached_total = 6（两侧都落不到 focus:gate:summary，已如实登记）
```

**判读**：`EXIT=1` 来自 `ruleset` 项（规则条数对账），**不是**计算样式差异。

#### B. 对实现者 196 组合产物的独立判读

```
combinations = 196  diff_combinations = 190  len(diffs) = 190
ruleset_mismatch_combinations = 190
kinds 分布 = {('ruleset',): 190}        含 'style' 的条目 = 0
含 'interaction-unreached' 的条目 = 0
before_rules = 1109 / after_rules = 1003（190 条全部相同）
first_rule_diff = 2（190 条全部）
首条差异 = '##sheet /app.css rules=943' → '##sheet /app.css rules=817'
无差异的 6 个组合 = legacy × {1280x720, 1280x1000, 1440x900, 1440x1000, 1920x1000, 1920x1080}
```

**为什么「190 条全是 ruleset ⇒ 元素级 0 差异」这个判读成立**（我核过源码，不只看汇总）：`verify_style_equivalence.py` 的比对循环里，元素指纹 `bfp != afp` 与规则序列 `b["rules"] != a["rules"]` 是**两个独立 `if`**，各自 `entry["kinds"].append(...)`，**没有短路**、没有「ruleset 不一致就跳过元素比对」。所以「190 条 kinds 只含 ruleset」意味着元素指纹在 190 个组合里都**真比过且全等**。

#### C. `943 → 817` 的结构账目（我自己数，不用浏览器）

| 量 | before | after | 说明 |
|---|---|---|---|
| `app.css` 顶层样式规则（我的括号深度解析器） | 917 | 791 | 与守卫/工具口径一致 |
| 顶层 at-rule 块 | 26（24 `@media` + 2 `@keyframes`） | **26（同一组）** | `@media` 条件未增删、未重排 |
| 浏览器 `cssRules.length` | **943 = 917+26** | **817 = 791+26** | 与指纹 JSON 的 `rules=943 / rules=817` **逐数字一致** |
| 顶层样式规则变化 | — | `917 + 52(逗号拆分新增) − 178(合并删规则) = 791` | 178 来自 `merge-log` 合计（顶层部分） |
| `@media` 内被删规则 | — | 8 条（`#hdrEnv`/`#hdrHealth`/`.run-list`/`.page-head`/`.grid2`/`.s0-grid`/`.aw-intervene`×2） | 186 = 178 + 8 |
| 展开行数合计（`tokens.css` 2 + `app.css`） | 1109 | 1003 | 与指纹 JSON 的 `before_rules/after_rules` 一致 |

⇒ 190 条 `ruleset` 差异**完全**由「合并去重 + 逗号拆分 + 删被支配规则」解释，`@media` 结构一条没动。这就是 F14 的目标，不是行为变化。

#### D. 我自己的逐元素哈希抽查（不是只看汇总）

脚本 `.ui-audit/3c-verify-tmp/element_spotcheck.py`（复用工具里冻结的 `capture_side`/`serve_dir` 保证同口径，比较与打印由我写）。抽 6 个组合，特意含 **760 / 851 / 1000** 三个窄断点（旧 P0 的现形区间）：

```
s0 @ 1280x720      元素数 948/948   哈希序列相同=True  不一致元素=0
gate @ 1280x720    元素数 1420/1420 哈希序列相同=True  不一致元素=0
run @ 760x1000     元素数 1420/1420 哈希序列相同=True  不一致元素=0
s0 @ 1000x1000     元素数 948/948   哈希序列相同=True  不一致元素=0
agent @ 851x1000   元素数 1426/1426 哈希序列相同=True  不一致元素=0
node-detail @ 1920x1080  元素数 1525/1525 哈希序列相同=True 不一致元素=0
结论：6 个组合中，逐元素哈希不一致的组合数 = 0
[ 2] header            before=a988b9c8-4d9f7ba… after=a988b9c8-4d9f7ba… 一致
[ 3] div.brand         before=a102593d-6dcb20a… after=a102593d-6dcb20a… 一致
[ 4] span.mark         before=28373b8e-f2b7c50… after=28373b8e-f2b7c50… 一致
（每组合规则序列条数：before=1109 / after=1003）
```

**我对实现者判读的结论**：**成立**。可以写进 STATUS 的原话：**计算样式零差异 + 规则序列按预期收敛（943→817，差异 100% 为 `ruleset` 项）**。唯一的保留意见是 §6.4 末尾那条「浏览器租户检查在本会话不可靠」的方法学限制，以及这套 `ruleset` 对账**本来就对结构重构必然报红**——所以它的价值是「证明条数变化可解释」，而不是「证明行为不变」；后者由元素级哈希承担（本轮 0 差异）。


---

## ⑦ 覆盖缺口与已知局限

### 7.1 共命中证据的自洽性（可核，全部对上）

| 项 | 证据值 | 我的核对 |
|---|---|---|
| 选择器键数 | 885 | = 输入清单 884 + 2 探针 − 1 非法（`::selection`），可复算 |
| 已检查对 | 391170 | = C(885,2)，**一致** |
| 共命中对 | 2626 | = `len(co_match)`，一致 |
| 状态 | 36 | 12 状态（s0/setup/run/gate/dirpicker/agent/node-detail/empty/legacy/toast/alert/gate-empty）× 3 视口 |
| 视口 | 1280×720 / 1440×900 / 1920×1080 | 全部 ≥1180px，**没有窄视口状态** |
| 零命中选择器 | 299 | 我另算 `app.css` 里 788 个简单选择器中 **264 个**在 36 组合里零命中（33.5%） |

### 7.2 缺口（按影响排序）

1. **零命中 = vacuous 豁免（P1）**：证据把「在 `selector_sanitized` 里出现过」当作「被测过」。可零命中的选择器**永远不可能**出现在 `co_match` 里，所以任何涉及它的一对都被判「从未共命中 ⇒ 可豁免」。最终产物上因此被豁免的翻转为 **4058**（同上下文） + **255**（跨上下文）。本轮没找到由此产生的真实差异（涉及的对手多是同元素互斥的结构选择器），但这条路径**不是** fail-closed。建议把 `selector_counts[s] == 0` 视为「未测」，或补动态态。
2. **交互态不在证据里**：`co_match` 的 36 个状态没有 hover/focus/active/disabled；工具靠 sanitize 剥掉伪类（`.x:hover` 与 `.x` 归一）。若窗口里存在同 sanitize 键的翻转对，`pair` 会退化成 1 元素集合，当前实现会因 `pair ⊆ measured` 且 `pair ∉ co` 而放行。本轮该情形**出现 0 次**（我专门统计了 `sanitize(x)==sanitize(y)` 的翻转对：0），但机制本身未验证。交互态指纹只在 3 个大视口采，窄断点交互态未覆盖。
3. **证据视口都在 ≥1180px**：`@media` 内规则作为「DOM 选择器」仍被测（共命中与视口无关），但**元素在窄视口是否存在/是否被 JS 换掉**没有窄视口样本。§⑤P0 那 23 处正是这条的实证代价。
4. **5 个 `app.css` 选择器未被证据覆盖**（工具会 fail-closed 挡住涉及它们的合并）：`.aw-detail[open] summary:before`、`.ev-list:empty:after`、`.option input:focus-visible + .radio`、`:where(button,a,summary):focus-visible`、`main:focus:not(:focus-visible)`。
5. **工具判据是局部的、分批序敏感**：`classify` 只看「源规则与最后一条规则之间」的竞争者，不知道竞争者自己也会被搬动；因此 `.run-list` 单遍 plan 受阻、分批第 10 批才合并（结果仍安全，见 §4.3）。`merge-plan.json` 因此不再精确描述最终决策集（P2）。
6. **`merge_plan.py` 崩溃路径**：证据文件缺失/为空时 `co=None`，`classify` 在 `pair in co` 处 `TypeError`；而分批脚本把「输出里没有『本批合并 N 个选择器』」当作 `merged=0` ⇒ 崩溃会被当成「没有可合并组，收工」。本轮证据文件始终存在，未触发。
7. **`@keyframes` 未纳入结构判据**：守卫与我的解析器按设计跳过 `@keyframes` 内层（4 条伪规则），所以「同一 keyframes 名重复定义」这类问题不在覆盖范围（本轮也没动 keyframes）。

---

## ⑧ 未验证 / 不声称 / 临时件清单

### 8.1 未跑（明确不声称）

| 项 | 原因 |
|---|---|
| 196 组合全断点指纹（自己跑） | 由实现者跑（`.ui-audit/3c/final-sweep-3c.txt`）；我只**解析其 JSON 独立判读**并独立复算结构账目，**不**声称「我跑了 196 组合」。我自己跑的是 72 组合（§6.5-A） |
| 浏览器全量门（178 passed） | 按约定由 Lead 统一跑，我没跑、不采信为我的结果 |
| 软件层全量（≥2003 passed） | 同上；我只跑了守卫与字号两项软件门 |
| hover/active/focus/disabled 截图目检 | 计划 §6 事前登记不做，我也没有做 |
| 内网/真实 ENV_ROOT 验收 | 本机无环境资产（`env_missing=36` 属环境缺件） |

### 8.2 不声称

- 不声称「视觉完全不变」：只声称**计算样式指纹（72 组合）零差异**（若未跑则连这条都不声称，见 §6.5）+ **静态级联判据零值变化**。
- 不声称 3C 之后（批次 4 / 4C）的改动无误：`loop/web/app.css` 现含它们，我的结论只对 `app-after-3c.css` 成立。
- 不声称 `merge-plan.json` 是最终决策集（见 §4.3 / §7.2-5）。
- 不声称「零命中」的 264 个选择器所涉规则的行为在各动态态下不变（§7.2-1）。

### 8.3 我本轮产生的临时件（全部在 `.ui-audit/` 下，未清理，供实现者引用）

| 文件 | 用途 |
|---|---|
| `.ui-audit/3C-verify.md` | 本报告 |
| `.ui-audit/3c-verify-tmp/indep_cascade.py` | 独立解析 + 值未变判据 + 跨选择器/跨上下文翻转判据 |
| `.ui-audit/3c-verify-tmp/cross_ctx_check.py` | P0 的可复跑检查（退出码 0/1） |
| `.ui-audit/3c-verify-tmp/final-3c-analysis.txt` | 最终产物的全量分析输出 |
| `.ui-audit/3c-verify-tmp/final-analysis.txt` | 旧 staging（f047bf6b）的分析输出 |
| `.ui-audit/3c-verify-tmp/final-3c.diff` | `snap-before` ↔ `app-after-3c.css` 的完整 diff |
| `.ui-audit/3c-verify-tmp/stage-vs-landed.diff` | staging ↔ `loop/web/app.css`，用于确认后者含批次 4/4C |
| `.ui-audit/3c-verify-tmp/merge_plan_copy.py` | 修复**前**的 `merge_plan.py` 副本（9 受阻那版，注入与对照用） |
| `.ui-audit/3c-verify-tmp/merge_plan_fixed.py` | 修复**后**的副本（24 受阻那版，注入与对照用） |
| `.ui-audit/3c-verify-tmp/old-plan-split.txt`、`.ui-audit/3c-verify-tmp/fixed-plan-split.txt` | 同一拆分输入上新旧工具的 `plan --verbose` 原始输出 |
| `.ui-audit/3c-verify-tmp/sim-fixed.css` | 用修好工具一次全量合并的模拟产物（`09f04bbc…`，1009 行；用于预告守卫剩余重复 = 24，与实际 23 差 `.run-list`） |
| `.ui-audit/3c-verify-tmp/split-before.css` | `snap-before` 的拆分副本（1218 行），供复跑对照 |
| `.ui-audit/3c-verify-tmp/inj/` | 8 组合成注入 CSS + 3 个合成证据 JSON + 产物 |
| `.ui-audit/3c-verify-tmp/stage-142459.css`、`.ui-audit/3c-verify-tmp/stage-FINAL-f047bf6b.css`、`.ui-audit/3c-verify-tmp/final-3c-73430cb2.css` | 过程快照（batch 7 / 旧流程收尾 / 最终 3C） |
| `.ui-audit/3c-verify-tmp/my-nosweep-72.txt` | **我自己跑的 72 组合** 指纹原始输出（含 JSON 汇总） |
| `.ui-audit/3c-verify-tmp/element_spotcheck.py` | 逐元素哈希抽查脚本（6 个组合，含 760/851/1000 窄断点） |

**清理状态**：未删除任何临时件（实现者要求留在 `.ui-audit/3c-verify-tmp/`）；我没有在仓库其它位置留下文件，也没有留下 git 状态变化（复核后 `git status` 与开工相比只多 `.ui-audit/` 这一未跟踪目录，那是本轮所有复核活动的临时区）。
