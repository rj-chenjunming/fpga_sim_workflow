# E 交付独立复核：UI 视觉优化（批次 1+2）

| 项 | 内容 |
|---|---|
| 复核者 | `ui-delivery-verifier`（独立只读；未改 `loop/**`、`doc/**`、测试、证据 JSON，未 git add/commit） |
| 对象 | 计划 [`2026-10-30-ui-visual-optimization.md`](../../doc/plans/2026-10-30-ui-visual-optimization.md) §8；[`WEB_UI_SPEC.md`](../../doc/spec/WEB_UI_SPEC.md) §10 A12/A13 + §14「2026-10-30 增补」；[`证据目录`](../../doc/evidence/UI_VISUAL_OPTIMIZATION_20261030/README.md) |
| 环境 | Chromium（`$PWD/.pw-browsers`）+ `loop/.venv/bin/python`，2026-10-30 10:17–10:35 |
| 判别性手段 | 全部在 `.ui-audit/tmp/` 内用**副本改探针 / 浏览器内存注入**完成；原测试与实现零改动 |

## 1 结论

**需修（P1 × 1，仅文档门；代码与测试可合入）。无 P0，无代码阻断项。**

1. **P1（阻断验收）** `doc/STATUS.md` **没有本轮新区段**：文件末段仍是 §139（T3 RTL 一键入口，mtime 02:14，`+91` 行全是 T3），而证据 README 第 3 行写「本目录是 `doc/STATUS.md` §140 与 … 的证据附录」——**§140 不存在**（悬空引用）。计划 §5 门 6「数字写入 `doc/STATUS.md` 新区段」与 AGENTS §4「界面有改动必须单独跑浏览器门并记入 STATUS」均未执行；本轮数字目前只活在计划 §8 与证据 README。
2. 我独立复跑与 Lead 自测**一致**：新用例 11 passed、浏览器全量 177 passed、文档 missing=0、软件层经正规入口 12 passed（§5 原始输出）。
3. 其余为 P2：判据覆盖面/脆弱度、两处口径不实（「三页 favicon」、§14「说明文字≥12px」）、§9 遗漏登记（§6/§7）。

## 2 diff 范围核对（工作树**实测 26 项**已跟踪改动；任务/审计文档记 23，差额为前序 T3 后期改动，按 mtime + 内容分离）

**本轮（2026-10-30 09:39–10:16）**：`loop/web/app.css`(09:53)、`app.js`(09:43)、`index.html`(10:03)、`tokens.css`(09:44)、`legacy.html`(10:03)、`legacy.css`(09:43)、**新增** `loop/web/favicon.svg`(10:03) = **7 个 UI 文件**；文档 `doc/spec/WEB_UI_SPEC.md`(09:39) + `doc/plans/2026-10-30-ui-visual-optimization.md`（新增）+ `doc/evidence/UI_VISUAL_OPTIMIZATION_20261030/`（新增）；另新增 `loop/tests/browser/test_ui_visual_20261030.py`。

**前序（非本轮，全部 ≤02:14，行内带 `T3` 注释）**：`loop/host/s0.py` `s0b.py`、`loop/services/api.py` `contracts.py`、`loop/workflows/*`、`loop/web/s0.js`(01:16)、`loop/tests/browser/test_run_sessions.py`(01:15)、`test_web_layout.py`(00:57)、`doc/spec/S0_ENVIRONMENT_SPEC.md` 等 **19 项**（26 − 本轮 7 项）。
- `index.html` / `app.css` / `app.js` / `WEB_UI_SPEC.md` 是**同文件混合**：T3 hunk（`s0-entry`/阶段回执卡、高级区、`from-rtl`、§13 增补）+ 本轮 hunk（hero 删除、nav、favicon、骨架、`--p`、状态词、A12/A13、§14 增补）。逐 hunk 已核对，未把前序算成本轮。
- ✅ `loop/services/**`、`kb/**`、`loop/host/**` **本轮零改动**；`app.js` 本轮只有 3 处：`fill.style.setProperty("--p")`、阶段词、Agent 词——**未改请求形状/轮询/闸门判据**（T3 的 prefill 属前序）。
- ❌ `doc/STATUS.md` 未被本轮改动（见 §1 P1）。

## 3 用例有效性（`test_ui_visual_20261030.py`，我实跑 `11 passed in 11.70s`）

| 用例 | 与规格一致 | 判别性（能判红？） | 缺陷/风险 |
|---|---|---|---|
| `test_s0_required_field_and_primary_action_are_in_first_screen`×3 视口 | A12 原文一致 | **能**：1280×720 实测「未滚动 ⇒ False，`scrollIntoView` 后 ⇒ True」 | P2：**不断言 `scrollY==0`**（实测自然加载 0，本轮成立）；只判垂直、不判 x；`bounding_box()` 为 `None` 时 `assert` 会显式红（不会假绿） |
| `test_gate_material_enters_first_screen_at_1440` | A12 原文一致 | 能（回退留白即红） | P2：判据本身极弱——实测 `#gateMaterial y=831.4 h=560 可见比例 0.12`，只有卡片头入屏，决策区仍未达；余量 68.6px 依赖字体度量 |
| `test_informational_text_meets_aa` | 部分 | 能（探针可算） | **P2 三缺**：①只取 7 个 selector，计划 §3.2 改过 12 条对比度规则，`.s0-blockers .eyebrow/.h3`、`.receipt-label`、`.phase-index`、`.stage-idx`、`.a3–.a6`、`.hb-code` **无探针**（我补测全部 5.35–6.23，当前无缺陷、纯保护缺口）；②每 selector 只测 `querySelector` 首个元素；③不看 fg `opacity` |
| `test_placeholder_text_meets_aa` | A13 | 能 | 只比元素自身 `backgroundColor`，同半透明盲区 |
| `test_focus_ring_contrast` | A13 | 能（实测 ring 5.48 / 9.0） | P2 脆弱：实测 `document.body.focus()` **无效**（body 不可聚焦，实为从 `#s0Rtl` 继续），到 `#btnS0` 需 **13 次 Tab**（上限 20，从文档起点只需 3 次）；两次实跑均绿、无偶发红，但中间插 8 个可聚焦元素即破 |
| `test_skip_link_target_has_visible_focus` | A13 | 能（实测 `activeElement===main`，`outline 2px solid`） | 无（仅覆盖 index，legacy 无对应用例，见 §7） |
| `test_tokens_and_motion_contract` | §14 动效/字体 | 能（副本回退 Inter / 加 `transition:width` ⇒ 均判红） | P2：`":active" in css` 与 `"--p" in js` 是**存在性**断言（写在注释里也通过）；正则只抓 `transition:` 简写，`transition-property:width` 长写法可绕过（实测 `offenders=[]`） |
| `test_stage_progress_animates_transform_not_width` | §14 动效 | 能（改回 `label:"进行中"` ⇒ 判红） | 同为存在性断言 |
| `test_landing_hero_removed_nav_favicon_and_skeleton_present` | §14 结构 | 能（结构回退即红） | P2：`"sk-line" in html` 不校验处数（实际 9 个 `.sk-line` / 4 容器 = 符合 G7） |

**对比度探针背景算法（Q2）**：算法只接受 `a>=0.999` 的祖先，**跳过**半透明层而不做合成；浏览器内存注入实验（`background:rgba(0,0,0,.65)` 浅色祖先 + 低对比文字）实测探针 `bg=rgb(255,255,255) ratio=4.29`，真实合成后仅 `1.63` ⇒ **会高估**，换上更暗 fg 即可假绿。但本轮 8 个探针目标实测背景链**半透明层数全为 0**（只跳过 `a=0` 全透明层，跳过正确），故当前不误判。
**`--p`（Q4）**：实测 `--p=0 → 渲染 0px / 0.33 → 99px / 0.5 → 150px / 1 → 300px`（`transform-origin:left`，几何正确）；`app.js` 有 `Math.min(1,Math.max(0,…))` 钳位，`total=0` 时 0 宽与原 `width:0%` 等价。唯一副作用：`scaleX` 会横向压扁 5px 条的右端圆角（视觉噪音，非缺陷）。
**hero 删除（Q5）**：三视口实测 `#pageTitle`「环境准备」/`#pageSub` 用途描述/`.page-edition` + `#pageIndex="S0"` **均可见**，§14「页标题、用途描述、视图编号」未失效；`hero/diagram` 残留引用 0（仅 1 行注释）。`<nav>` 包裹实测对 `#viewSeg` 几何无影响（216px→216px）。
**legacy（Q6）**：独立静态页实测——首个 Tab 落 `.skip-link`（top:12 可见），Enter 后 `activeElement=#legacyMain`、`outline 2px solid rgb(21,119,94)`、第 2 个 Tab 继到既有 `SUMMARY` ⇒ 既有键盘路径未坏，`legacy.css` 有同名 `main:focus-visible` 规则（`tokens.css` 已链接，`--primary` 有值）。

## 4 契约 A12/A13 对照

- **A12** ✅ 三视口 `#s0Rtl`(`y=488.3`) / `#s0Prepare`(`y=565.1`) 完整入屏、`scrollY=0`、`horizontalOverflow=0`；1440 闸门 `y=831.4<900`。（复现值与 `measure-after.json` 逐位相同，证据可复跑。）
- **A13** ✅ 信息文本：`measure-after.json` `failCount=3/194`，我核对其 3 条为 2 个装饰 `/`（1.53/1.89）+ disabled `#btnNotify`（2.17，WCAG 1.4.3 不适用）⇒ 声称成立；焦点环 5.48/9.0 ✅；skip 落点 ✅；基准曲线/无 `transition:width`/`:active` 6 选择器 ✅（`--ease-out` 覆盖全部 transition）。**但**判据覆盖只到采样（§3），且新增 §14 条「只动 transform/opacity、spinner 为唯一例外」被既有 `.pulse`（`animation:pulse` 动 `box-shadow`，`app.js:1284/2200`）证伪——该例外未登记（P2）。
- §14 增补：hero ✅、动效曲线 ✅、字体（`--font-sans` 无 Inter/`@font-face`/`url(` 全 0）✅、骨架 ✅（4 容 9 行）、color-source 已登记 ✅。**「说明文字不小于 12px」未达成且无判据**：`.rail-foot` 实测 10px（侧栏脚注）；`.foot-note` 声明 11.5px 但被 :556 覆盖为 12px（两段式死声明，属 D-15 债）。本轮只改了 `.agent-role` 11→12px（P2）。

## 5 回归原始输出（我本人执行，原样粘贴）

```
$ .venv/bin/python -m pytest -q tests/browser/test_ui_visual_20261030.py tests/browser/test_web_layout.py
23 passed in 23.04s
$ .venv/bin/python -m pytest -q tests/browser/test_s0_auto_entry.py tests/browser/test_run_sessions.py
38 passed in 42.79s
$ .venv/bin/python -m pytest -q tests/browser          # 额外自证全量
177 passed in 185.99s (0:03:05)
$ .venv/bin/python -m pytest -q tests/test_web_smoke.py tests/test_api.py     # 任务给的原始命令
5 failed, 7 passed, 1 warning in 3.12s
  E OSError: [Errno 30] Read-only file system: '<ENV_ROOT>/kb/runs/RUN-20261030-1019xx'   # ×5
$ bash spikes/run_software_checks.sh tests/test_web_smoke.py tests/test_api.py -q   # 同两文件走正规入口（可写影子数据根）
12 passed, 1 warning in 11.33s
$ python3 doc/audit/check_doc_links.py ; echo EXIT=$?
checked=3087 skipped=44001 historical=857 known_missing=16 env_missing=35 missing=0
EXIT=0
```
说明：原始命令的 5 failed 全是 `ENV_ROOT/kb/runs` 只读 `OSError`（AGENTS §4 登记的环境缺件，非代码缺陷），同两文件经 `run_software_checks.sh` 12 passed 可证。文档计数 `checked` 比 Lead 的 3079 多 8（两次运行之间文档增长），`missing=0` 一致。Lead 的全量软件层 1999 passed **我没有重跑**（任务未要求、成本 4.5 min），本报告不为其背书。

## 6 诚实性与遗留清单核对

| 声称 | 核对 |
|---|---|
| 新用例 11 passed | ✅ 我实跑 `11 passed in 11.70s` |
| 浏览器全量 177 passed | ✅ 我实跑 `177 passed in 185.99s` |
| 文档 `missing=0` | ✅ 我实跑（`checked=3087`） |
| 软件层 1999 passed | 未复核（不背书）；所列两条命令我复跑一致 |
| 「先红 11 failed」 | ❌ 不可复核（需回退工作树，本任务禁止）；已用 §3 副本回退/滚动/注入实验替代证明判红能力 |
| **G7「三页有 favicon」** | ❌ **不实**：`loop/web/*.html` 共 3 页（index/legacy/mockup），只有 **2 页**有 `rel="icon"`；`mockup.html` 未改（mtime 10-19，属「静态样张不重绘」可接受，但记录写成「三页」） |
| G5「颜色/边框过渡 ≥200ms」 | ✅ 实测非 `--ease-out` 的 transition 仅 `reduced-motion` 的 `none` |
| G2 闸门首屏 | 诚实（记录写了 `visibleRatio 0.12`），但 A12 判据过弱（见 §3） |
| 计划 §9「仍未做」 | **不完整**：漏登 ①`doc/STATUS.md` 新区段（见 §1）②D-19 其余口径项（状态词表、状态判据三份、产品名不一致、`↗` 一符三义、两处 `window.confirm`、`.chip` 一符多义）③§14「说明文字≥12px」未达成 ④`.pulse` 的 box-shadow 动画例外未登记 |

## 7 问题清单

**P0**：无。
**P1**：
1. `doc/STATUS.md` 缺本轮新区段；证据 README 引用不存在的 `§140`（悬空、唯一数字源缺失、浏览器门未记入 STATUS）。→ 补 STATUS 区段并改正证据 README 引用。
2. （建议）A13 声明其判据就是本用例，但探针只覆盖 7/12 条改过规则 ⇒ 那 5 条若回退不会红；建议按计划 §3.2 表补探针或加"全节点扫描"式断言。
**P2**：
3. 首屏用例不断言 `scrollY==0`（判据随视口滚动而变，实测当前 0）；建议加一行。
4. 对比度探针跳过半透明层而非合成（实测高估 4.29 vs 真实 1.63），当前背景链未触发但属结构隐患。
5. 焦点环用例的 Tab 路径脆弱（13/20），`document.body.focus()` 无效。
6. 动效/结构断言多为"存在性"（`":active"`、`"--p"`、`"sk-line"`、`<nav>`），`transition-property` 长写法可绕过。
7. 「三页 favicon」记录不实（实为 2 页）。
8. §14「说明文字不小于 12px」无判据；`.rail-foot` 实测仍 10px（`.foot-note` 有效值为 12px，11.5px 是死声明）。
9. `.pulse` 动 `box-shadow`，与新增「只动 transform/opacity（spinner 唯一例外）」冲突且未登记。
10. 计划 §9 漏登 §6 表内四项（尤其 STATUS 与 D-19 余项）。
11. （前序 T3，非本轮，但与本轮同文件）`WEB_UI_SPEC.md` 出现**两个 `## 13`**（802 行旧、854 行新）且新 §13 排在 §14 之后；本轮改同一文件未顺手登记。
