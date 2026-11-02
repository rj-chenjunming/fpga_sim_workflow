# F 批次 3A「UI 字号阶梯落地」独立复核（只报告）

> 复核员 `ui-typography-verifier`，2026-10-30。**未改任何被测文件**；本次唯一写入 = 本报告。
> 对象：`loop/web/{app.css,legacy.css,legacy.html}` 字号吸附、`loop/tests/test_ui_typography.py`、
> `WEB_UI_SPEC.md` §14/§10 A14、`doc/plans/2026-10-30-ui-typography-scale.md`、`doc/evidence/UI_TYPOGRAPHY_20261030/`。
> 工作树混有前序 T3 与批次 1+2 未提交件；本轮归属判据 = 计划 §3 映射 + 「font-size/font 简写 px 值变化」+ mtime
> （3A 三文件均 `10:56:10`，测试 `10:55:56`，spec `10:55:18`；T3 的 `.py` 均 01:05–02:03）。

## 0 结论

**可合入：无 P0 / 无 P1 阻断。** 映射逐条正确，守卫三类真实写法都能判红，除字号外零副作用，
四道门与浏览器门本机复跑全绿。需修项均为 P2（2 处文档数字不实 + 守卫 4 个脆弱/漏判点），建议下一轮合并处置。

## 1 映射正确性

- 3A 可复现的字号变化 **121 处**，逐条对照计划 §3：**0 条错映射**。
  `app.css` 100（11.5→12×37、12.5→12×25、10.5→11×8、9→10×8、15→16×6、21→20×3、17→16×2、8→10×2、22→20×2、
  7→10、19→18、29→30、31→30、15.5→16、9.5→10、13.5→14）；`legacy.css` 3（17→16×2、15→16）；
  `legacy.html` 18（11.5→12×13、12.5→12×2、13.5→14×2、15→16）。
- 当前 4 文件 **355 处** `font-size`/`font` 简写 px 声明；distinct = `{10,11,12,13,14,16,18,20,24,30}` 全 ∈ 11 档（用守卫自身 `scan()` 复核，offenders=[]）。
- 映射表外的 5 处字号变化**均属前序批次 1+2**，非本轮：`.page-edition` 9→11 及其媒体查询 8→11、`.agent-role` 11→12、
  `.page-head h1` 27→24、`.phase-index` 16→14。前四项有 1+2 计划 §3.2/§3.3 与 `STATUS §140.2` 明文，且 `.ui-audit/measure.json`
  （09:55，早于 3A）已记录 `.page-edition` 计算字号=11、`.phase-index`=14；第五项 `.phase-index` 的字号变化 1+2 记录里只登记了颜色（P2-1）。
- **非字号数字零误伤**：属性级全量比对（按 selector 配对）显示 `letter-spacing`、`border-radius` 零改动；
  唯一 `line-height` 变化 `.phase-card p` 1.6→1.5 与同 hunk 的 `.phase-card{padding:18px 20px→12px 16px}`、
  `.phase-index{width 36→30;height 39→30;flex 36→30}` 同属 1+2 首屏压缩。11 处 `font:` 简写只改字号数字，
  `/1.7`、`/1.8`、`/1.3` 行高与字体族逐字不变（例：`600 29px/1.3`→`600 30px/1.3`）。
- 另核对：`body{font:14px/1.55 …}` 两侧一致（13/14px 正文口径未动）；无 `%`/关键字/大写 PX 字号。

## 2 用例有效性（`loop/tests/test_ui_typography.py`）

- **判别性实测**（把 4 文件复制到 `/tmp`，用同一模块改一个值后调用同一函数；仓库零改动）：
  - `font-size:12px→11.5px` ⇒ 判红 `app.css:70 11.5px （11.5px）`
  - `font:12px var(--font-mono)→font:11.5px …` ⇒ 判红 `app.css:533 11.5px （11.5px var(--font-mono)）`
  - `legacy.html .tiny{font-size:11.5px}` ⇒ 判红 `legacy.html:19 11.5px`
  - 未改副本 ⇒ `3 passed`。**三种真实写法（普通声明 / `font:` 简写 / HTML 内联）都能抓住**。
- 覆盖面：`font-size` 声明 293+12+25 与 `font:` 简写 24+1 均计入；`index.html` 现 0 处字号但仍被扫描；
  `mockup.html` 按 §14 排除（其自身仍有 11.5/12.5/10.5/14.5 等阶外值，豁免有意义且未动）。
- 阈值 `≥300` 实测 355（余量约 18%），足以防「空扫通过」。
- **漏判（P2-2，实测）**：`font-size:11.5PX`（大写 PX）、`font:1.1em …`（简写内相对单位不受 `test_no_relative_font_sizes` 管）、
  `font-size:90%` 三种写法两测都不判红——当前仓内无此形态，属未来回归口子。
- **注释被当声明（P2-3，实测）**：正则不剥离注释，`/* 旧值 font-size:11.5px */` 会被计入；当前注释无此形态（`app.css:1197` 的 `1px` 无 `font-size:` 前缀，未误报）。
- **规格解析脆弱（P2-4，实测）**：`test_scale_matches_spec_table` 取 marker 后 **1200 字符窗口**，实测窗口已跨进 §13（T3 区段）；
  窗口内任何反引号两位数即误红（插 `` `40` `` ⇒ `[10..36,40]`），`` `12` ``→`` `12px` `` 误红，`` `30/36/100` `` 误红；
  而新增**单位数**（插 `` `9` ``）被 `\d{2}` 忽略 ⇒ **漏判**；marker 文案改名 ⇒ `ValueError`（error 而非断言）。
  建议：限定 §14 那一条 bullet、允许 1–3 位数字、并同时校验 §10 A14 列表。

## 3 契约对照（§14 ↔ §10 A14）

- §14 bullet 的 11 档、A14 的 11 个值、用例 `SCALE` 三者一致（脚本比对 `quoted == SCALE` = True）。
- 13–14px 正文/表单口径未破坏：现 13px×35、14px×13 仍在；被吸附的 11.5/12.5 只升不降（12.5→12 仍 ≥12）。
- `mockup.html` 豁免在 §14 与用例 `FILES` 中一致；`36` 档无消费者已在计划 §8 / STATUS §141.2 如实登记。
- 唯一不可机械判定项（P2-5）：§14「10/11 仅限标签与图示注释、不得承载唯一关键信息」；
  `.s0-flow li>.flow-status`（阶段回执的「待执行/✓」）为 11px 信息性文本，建议人工目检确认属标签而非唯一关键信息。

## 4 无副作用

- 3A 触碰文件 = 3 个 web 文件（10:56:10）+ 新测试（10:55:56）+ spec（10:55:18）+ 计划/证据/STATUS（文档）。
  3A 时间窗（10:40–11:00）内无其它 `loop/**`、无 `kb/**` 落笔。
- `loop/services/{api,contracts}.py`（01:35/01:50）、`loop/host/{s0,s0b}.py`（01:05/01:48）、`loop/workflows/*`（01:31–02:03）
  的未提交改动 mtime 全在 3A 之前 ⇒ 前序 T3，非本轮。
- `mockup.html` 未动：工作 md5 = `git show HEAD` md5 = `a55d2be7990cb755b3456efc60fe0882`。
- `loop/web/*.js` 无任何 `font-size`/`fontSize`/`font:`（计划「JS 无字号」属实）。
- 证据 4 张截图 md5 与证据 README §4 全部一致；目检 before/after `1440-environment`：仅小字整体放大、层级更稳，无坍塌/错位。

## 5 回归（本机真跑，原始输出）

| # | 命令（`cd loop`，环境变量按任务给定） | 原始输出 | exit |
|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q tests/test_ui_typography.py` | `3 passed in 0.61s` | 0 |
| 2 | `… tests/browser/test_web_layout.py tests/browser/test_ui_visual_20261030.py` | `24 passed in 22.97s` | 0 |
| 3 | `… tests/browser/test_s0_auto_entry.py tests/browser/test_run_sessions.py` | `38 passed in 43.34s` | 0 |
| 4 | `cd .. && python3 doc/audit/check_doc_links.py` | `checked=3133 skipped=44372 historical=857 known_missing=16 env_missing=35 missing=0` | 0 |
| 5（加跑） | `… .venv/bin/python -m pytest -q tests/browser` | `178 passed in 210.63s (0:03:30)` | 0 |
| 6（加跑） | `bash spikes/run_software_checks.sh --ignore=tests/browser -q` | `2002 passed, 3 deselected, 1 warning in 284.03s (0:04:44)` | 0 |

## 6 诚实性（计划 §8 / STATUS §141 / 证据 README 对实测）

- 一致：`3 passed`、浏览器全量 `178 passed`、软件层 `2002 passed, 3 deselected`、文档门 `missing=0`（时长不同，属机器差异）；
  `app.css 25→10`、`legacy.css 4→3`、`legacy.html 8→5`、`36` 无消费者、`mockup` 未动 —— 全部可复现。
- 不实（P2-6）：
  1) **「124 处」**：按工作树只能复现 **121 处**。明细差两格：`10.5→11` 声称 ×10 实测 ×8、`12.5→12` 声称 ×28 实测 ×27，其余逐项相符。
     差额 3 可能来自 3A 对 T3 **未提交**新增声明的吸附（git 侧不可见），但按当前工作树无法复现 124，应标注口径或来源。
  2) **「扫描 356 处」**（计划 §3/§8）：守卫实测 **355**；`legacy.html` 第 26 处是 `font-size:inherit`（无 px，不计入）。
  3) **「先红 2 failed, 1 passed（25 个阶外）」**：§5 写「25 个不同字号」正确，§8/证据写「25 个阶外」错位——按 3A 前口径
     distinct=25，其中**阶外 16**。且「2 failed」不可复现：3A 前仓内无 rem/em 字号，`no_relative` 当时应通过；
     第 2 个失败项无解释，建议把先红原始日志落档。

## 7 问题清单

| 级别 | 项 | 处置建议 |
|---|---|---|
| P0 | 无 | — |
| P1 | 无 | — |
| P2-1 | `.phase-index` 16→14 是 1+2 改动，但 1+2 计划/STATUS 只登记颜色 | 1+2 记录补登字号变化（避免被误读成本轮） |
| P2-2 | 守卫漏判：大写 `PX`、`font:` 简写内 `em/rem/%`、百分比字号 | 补一条「阶梯外单位」守卫或统一小写 + 覆盖简写 |
| P2-3 | 守卫不剥离注释，注释内 `font-size:…px` 会被当声明 | 正则前去除 `/*…*/` 与 HTML 注释 |
| P2-4 | `test_scale_matches_spec_table` 窗口化解析：跨 §13、`\d{2}`、marker 缺失抛 ValueError | 限定 §14 bullet + 1–3 位数字 + 校验 A14 |
| P2-5 | §14「10/11 不得承载唯一关键信息」无判据；`.s0-flow li>.flow-status` 11px 待目检 | 人工目检并在证据里留一句结论 |
| P2-6 | 三处数字口径：124 vs 121、356 vs 355、「25 个阶外」vs「25 个不同字号/阶外 16」；先红无原始日志 | 改文档数字或注明口径；先红日志落档 |
