# 2026-10-30 UI 视觉优化（批次 1+2）执行计划

> 上游：[`doc/audit/AUDIT-20261030-ui-design.md`](../audit/AUDIT-20261030-ui-design.md)（P1=4 / P2=16）。
> 本计划只覆盖审计建议里的**批次 1（可读性）与批次 2（首屏）**：两者都是「A 类：改实现即可，不动业务契约」。
> 批次 3（字号表/令牌化/F14 合并）与批次 4（GATE-1 身份、闸门常数、图标 sprite）**不在本轮**，见 §7。

## 1 目标（可判定）

| 目标 | 判据 | 对应审计项 |
|---|---|---|
| G1 主路径首屏可达 | 1280×720 / 1440×900 / 1920×1080 下，`#s0Rtl` 与 `#s0Prepare` 的包围盒完整落在首屏内 | D-01 |
| G2 闸门决策首屏可达 | 1440×900 下，`#gateMaterial` 顶边进入首屏（`< 900`） | D-13（只压上方留白，不动 `--gate-pane-max-h`） |
| G3 信息文本 AA | S0 视图中信息性文本对比度 ≥ 4.5:1（装饰符除外） | D-02 |
| G4 焦点环 AA | `#s0Rtl` 焦点环对底 ≥ 3:1；侧栏焦点环对 `--rail` ≥ 3:1；skip-link 落点 `main` 可见焦点 | D-03 / D-12 |
| G5 动效契约 | `--ease-out = cubic-bezier(0.22,1,0.36,1)` 被引用；无 `transition: width`；颜色/边框过渡 ≥ 200ms；`:active` 存在 | D-08 / D-09 |
| G6 字体不声明不可用族 | `--font-sans` 不含 Inter；`loop/web/**` 仍零 `@font-face`/`url(`/外链 | D-05 |
| G7 结构 | 有 `<nav>`；`legacy.html` 有 skip-link；`index`/`legacy` 有 favicon（`mockup.html` 是 §14 明确的静态历史样张，不重绘）；S0 无落地页 hero；加载占位改骨架 | D-16 部分 / D-17 / D-20 / D-10 |
| G8 口径一致 | 运行/阶段/Agent 三处运行态统一为「执行中」 | D-19（状态词部分） |

## 2 契约变更（先于实现，2026-10-30）

`doc/spec/WEB_UI_SPEC.md` 增补两处（本计划即其评审记录）：

1. **§10 新增 A12 / A13**：首屏判据（S0 必填项+主操作、闸门两栏在 1440×900 进首屏）与可读性判据（信息文本 ≥4.5:1、焦点环 ≥3:1）。
   A12/A13 都是**既有 §14 意图的可判定化**，不放宽任何既有判据。
2. **§14 增补「2026-10-30 视觉与首屏修订」**：运营台不设营销 hero（S0 首屏为页标题+一句用途+首个任务）；
   动效统一基准曲线且只动 transform/opacity（`spinner` 的 `linear` 作为不确定态指示登记为唯一例外）；
   颜色只来自 `tokens.css` 的令牌（新规则，先登记，收敛在批次 3 执行）；加载占位用骨架。
   同一条里明确「§14 既有 13–14px 正文口径不变」。

## 3 设计契约（实现方共同遵守）

### 3.1 令牌（`loop/web/tokens.css`）

| 令牌 | 旧 | 新 | 依据 |
|---|---|---|---|
| `--font-sans` | `Inter,-apple-system,…` | `-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","Microsoft YaHei",sans-serif` | 全仓无字体资产，Inter 不下载；§14:842 |
| `--faint` | `#71827b`（4.05 白 / 3.73 雾白） | `#5f6f67`（5.31 / 4.89 / hero 4.61） | AA 4.5 |
| `--muted` | `#61746c` | 保持不变（4.97 / 4.58，已合格） | 最小改动 |
| 新 `--ease-out` | — | `cubic-bezier(0.22, 1, 0.36, 1)` | B7 基准曲线 |

### 3.2 局部色（`app.css`，全部达到 ≥4.5:1）

| selector | 旧 | 新 |
|---|---|---|
| `.page-edition` | `#7b8b81` 9px（3.31） | `var(--muted)`，11px（4.58） |
| `.section-index` | `#698563` on `#f8faf6`（3.89） | `#4d6b4e`（5.95 / 5.48） |
| `.s0-checks li>span` | `#6c7f69`（3.98） | `#55684f`（5.58） |
| `.s0-blockers p / .s0-blockers .eyebrow / .s0-blockers h3` | `#8c724c` / `#957d56` / `#88662e`（3.78–4.36） | `#7a6234`（5.57） |
| `.receipt-label` | `#53786b`（4.92/4.53） | `#456761`（6.24/5.75） |
| `.phase-index` | `#6a855e`（3.68） | `#4d6b4e` |
| `.input::placeholder` | `#7b8980`（≈3.5） | `var(--faint)` |
| `.agent-role` | 11px | 12px（§14:825 说明文字 12px） |
| `.hb-code` / `.nd-hb-code` | `#9a8259`（3.54） | `#7a6234` |
| 侧栏焦点环 | `--primary`（2.62 on rail） | `#b9d5aa`（9.0 on rail） |
| `#s0Rtl` 焦点环 | `#c4e2cf`（1.39） | `var(--primary)`（5.48） |
| `.option.on .radio` | `radial-gradient(...)` | 去掉渐变：`background:var(--warn)` + 内圈 `#fff` 用 `box-shadow:inset 0 0 0 3px #fff` |

> 允许实现方在「≥4.5 / ≥3」与「仍使用令牌或更暗的同色系」范围内微调取值；**不允许**放宽阈值。

### 3.3 DOM / 行为

1. **删 S0 营销 hero**：删 `index.html` 的 `#viewS0 > .s0-hero`（含 `.hero-diagram`、`hero-tags`、眉题），删 `app.css` 的 `.s0-hero/.hero-*/.diagram-*` 规则；`#pageSub` 保留为唯一一句用途说明。
2. **S0 首屏压缩**：`.page-head` 去掉 `min-height:96px`、`h1 27→24px`、`margin-bottom 26→18px`；`.s0-phases` 卡片内边距收紧（≤14px）、阶段卡高度目标 ≤76px；`.s0-form-actions` 从表单底部移到 `#s0Rtl` 之后、「高级（可改）」之前（`#s0Error` 紧随其后），保证提交行在 1280×720 首屏内。
3. **闸门视图压上方留白**：`#gateHead` 内边距收紧、`.stages` 在闸门视图的卡片头与行高收紧（`#stagesGate` 的 `.stage-head` min-height 56→44、padding 13→10），**不动** `--gate-pane-max-h` 与两栏结构。
4. **加载占位**：`#s0History`、`#s0Switch`、`#s0Copies`、`#healthBody` 的「加载中…」文本改为 2–3 行骨架块（`.sk-line`），`app.css` 新增 `.sk-line`（真实行高形状 + 微弱的静态色，不做无限动画）；加载完成后由既有 JS 覆盖 innerHTML，行为不变。
5. **`<nav>`**：`#viewSeg` 外层包 `<nav class="rail-nav" aria-label="主导航">`（tablist 语义保留在内部）。
6. **favicon**：`index.html` 与 `legacy.html` 的 `<head>` 加 `<link rel="icon" type="image/svg+xml" href="favicon.svg">`，资产为本仓 `loop/web/favicon.svg`（不破零外链）；`mockup.html` 不重绘。
7. **legacy skip-link**：`legacy.html` 顶部加 `<a class="skip-link" href="#legacyMain">跳到主内容</a>`，`<main>` 加 `id="legacyMain" tabindex="-1"`，样式加在 `legacy.css`。
8. **动效**：`--ease-out` 统一；颜色/边框/阴影 200ms；`.stage-bar i` 改 `transform:scaleX(var(--p,0))`（`transform-origin:left`，500ms），`app.js` 改设 `--p` 不再设 `width`；`.stage-chev` transform 200ms；覆盖 `prefers-reduced-motion` 既有规则。
9. **`:active`**：`.btn`、`.run-item`、`.snode`、`.seg button`、`.agent-clickable`、`.option` 统一 `transform:translateY(1px)`。
10. **`main:focus-visible`**：`main:focus:not(:focus-visible){outline:none}` + `main:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}`。
11. **状态词**：`app.js` 阶段聚合「进行中」→「执行中」、Agent `working`「工作中」→「执行中」；`s0.js` 的「切换进行中」是 S0 切换过程文案，不改。
12. **mono 用途**：`.diagram-flow b` 随 hero 删除；序号保留（§14 视为计数）。
13. **text-wrap**：标题 `balance`、正文段落 `pretty`。
14. **点击靶**：`.agent-open` 最小高度 24px。

## 4 切片与写权（互斥）

| 切片 | 内容 | 唯一写者 | 写范围 |
|---|---|---|---|
| S0 契约 | §10 A12/A13、§14 增补、本计划 | Lead | `doc/spec/WEB_UI_SPEC.md`、`doc/plans/` |
| S0 用例 | 先失败用例 | Lead | `loop/tests/browser/test_ui_visual_20261030.py` |
| S1 样式 | 令牌 + `app.css`（对比度/焦点/动效/:active/骨架/首屏压缩/闸门压缩/text-wrap/点击靶） | `ui-css` | `loop/web/tokens.css`、`loop/web/app.css` |
| S2 结构 | `index.html`（删 hero、搬提交行、nav、favicon、骨架占位）、`app.js`（scaleX、状态词）、`legacy.html`（skip-link）、`legacy.css`（skip-link 样式） | `ui-markup` | `loop/web/index.html`、`loop/web/app.js`、`loop/web/legacy.html`、`loop/web/legacy.css` |
| S3 验收 | 跑门、复核、STATUS | Lead + `ui-verifier`（只读复核） | `doc/STATUS.md`、本计划勾选 |

## 5 验证门（DoD）

1. 新用例先红后绿：`loop/tests/browser/test_ui_visual_20261030.py`（首屏/对比度/焦点/动效契约/结构/口径）。
2. 浏览器全量：`PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… loop/.venv/bin/python -m pytest -q loop/tests/browser`（基线见 `doc/STATUS.md:6644`，改动后应 ≥166 且 0 failed）。
3. 静态复测：用 `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py` 重跑，确认 S0/gate/monitor 的**非装饰信息文本**失败数为 0、焦点环 ≥3、三视口首屏判据成立。
4. 软件层：`loop/spikes/run_software_checks.sh`（只读数据根下的统一入口）。
5. 文档：`python3 doc/audit/check_doc_links.py`（`missing=0`）。
6. 记录：数字写入 `doc/STATUS.md` 新区段；本计划勾选完成项。

## 6 回滚

每个切片独立成提交；S1/S2 视觉改动全部集中在 `loop/web/**`，回滚方式为 `git revert` 该切片。
无数据/契约副作用：不写数据根、不改 API、不改闸门判据。

## 7 不在本轮（批次 3/4）

| 项 | 原因 | 前置 |
|---|---|---|
| 字号阶梯表 + 350 处字号吸附 | 需 §14 先补表（否则不可判定，A-02 已被复核降 P2） | 人确认阶梯取值 |
| 令牌化（401 处 hex → tokens） | 必须先按 F14 合并两段式（956 规则/183 重复），否则会被覆盖段冲掉 | 批次 3 专项计划 |
| GATE-1 ↔ G1 身份映射 | 契约未定（`OPTIMIZATION_PLAYBOOK.md:159` 要求不能默认同一身份） | 人裁 |
| 闸门 `--gate-pane-max-h` 常数 | §14:831-836 写死，改动=改规格承诺（`doc/STATUS.md:6411` 已登记需人裁） | 人裁 |
| 图标 SVG sprite | 独立资产改动，可与批次 3 并行 | 设计确认符号表 |

---

## 8 执行记录（2026-10-30）

**状态**：S0 契约、S0 用例、S1 样式、S2 结构、S3 验收均已完成；批次 1+2 的 G1–G8 全部达成。
证据与前后截图：[`doc/evidence/UI_VISUAL_OPTIMIZATION_20261030/`](../evidence/UI_VISUAL_OPTIMIZATION_20261030/README.md)。

| 目标 | 结果（可复核） |
|---|---|
| G1 主路径首屏 | `#s0Rtl` / `#s0Prepare` 在 1280×720 / 1440×900 / 1920×1080 三档 `visibleRatio = 1` |
| G2 闸门首屏 | 1440×900 `#gateMaterial` 顶边进入首屏（`visibleRatio 0.12`）；**1280×720 仍在首屏外**（见 §9） |
| G3 信息文本 AA | S0 fail 3/194，剩余全为装饰 `/` 与 disabled 控件；gate 4/173、monitor 4/238 同 |
| G4 焦点环 AA | `#s0Rtl` 1.39→5.48；侧栏 2.62→9.0；skip→`main` 2px solid `--primary` |
| G5 动效契约 | 全部 `cubic-bezier(0.22,1,0.36,1)`；`transition:width` 清零；`:active` 6 选择器；`.stage-bar i` 改 `scaleX(var(--p))` |
| G6 字体 | `--font-sans` 无 Inter；`@font-face`/`url(`/外链仍为 0 |
| G7 结构 | 有 `<nav>`；`index`/`legacy` 两页有 favicon（本地 `loop/web/favicon.svg`；`mockup.html` 按 §14 不重绘）；legacy 有 skip-link；S0 无 hero；4 处加载占位改骨架（9 行 `.sk-line`） |
| G8 口径 | 阶段「进行中」、Agent「工作中」→ 统一「执行中」 |

**门（原始输出）**：

| 门 | 命令 | 实际输出 |
|---|---|---|
| 新用例（先红） | `pytest -q tests/browser/test_ui_visual_20261030.py` | 首轮 `10 failed, 1 passed`（闸门用例补夹具后 `11 failed`） |
| 新用例（后绿） | 同上（复核后由 11 条增至 12 条） | `12 passed in 11.38s` |
| 浏览器全量 | `pytest -q tests/browser`（含 `LOOP_VISUAL_ARTIFACTS`） | `178 passed in 193.14s`（0 failed） |
| 软件层 | `bash spikes/run_software_checks.sh --ignore=tests/browser -q` | `1999 passed, 3 deselected in 257.93s`，exit 0 |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=3114 skipped=44286 historical=857 known_missing=16 env_missing=35 missing=0`，exit 0 |
| 运行时复测 | `measure.py`（受控夹具） | 见上表与证据目录 §2 |

**实现中发现并关闭的两个缺陷（本轮内）**：
1. favicon 初版用 SVG data URI，`xmlns='http://www.w3.org/2000/svg'` 触发 A8「页面不得引用外部资源」两条单测红
   （`test_web_smoke.py`、`test_api.py`）→ 改为本地 `loop/web/favicon.svg` + 相对 href，两测转绿、`GET /favicon.svg` 200。
2. `.stage-idx` 12px 文本实测 4.47（差 0.03）→ 改 `#55684f`（5.42）；
   monitor 头像首字母 4.06–4.42 → `.a3/.a4/.a5/.a6` 压暗到 5.71–6.23。
3. `.pulse` 原动画改 `box-shadow`，与 §14「只动 transform/opacity」冲突 → 改伪元素
   `transform:scale()/opacity`（`app.css:225-228`），规则与实现一致，无需登记例外。
4. 独立复核（`ui-delivery-verifier`）指出 A13 的判据覆盖只到 7/12 条改过规则 → 验收用例补
   `.phase-index`、`.s0-blockers .eyebrow/h3`、`.rail-foot` 探针与 run 视图
   `.stage-idx`/`.agent-role`/头像探针；并补 `scrollY==0`、`transition-property` 长写法、
   `@keyframes` 只许 transform/opacity 的守卫。用例由 11 条增至 12 条。

## 9 仍未做（不得声称完成）

| 项 | 现状 | 归属 |
|---|---|---|
| 闸门视图 1280×720 首屏 | `#gateMaterial` 仍在首屏外（只压留白不够，需折叠非当前阶段或改 `--gate-pane-max-h`） | 人裁 + 批次 4 |
| 字号阶梯/间距/圆角收敛 | 30/36/13 档未吸附（§14 无表，先立表才可判定） | 批次 3（先改规格） |
| 令牌化 | 组件层仍有硬编码 hex（只在 §14 登记了「不得新增」，存量未替换） | 批次 3（先 F14 合并） |
| 图标 sprite | 仍是 Unicode 字形（`▧ ⊞ ◴ ◇` 等） | 批次 4 |
| GATE-1 ↔ G1 映射 | 未定 | 人裁 |
| 非 Chromium / 真机滚动条 | 未验 | 环境限制（同 `doc/STATUS.md:6411`） |
| D-19 其余口径项 | 只统一了运行态词；状态判据三份（`app.js:74-81/375-381/383-389`）、三页产品名不一致、`↗` 一符三义、两处 `window.confirm`、`.chip` 一符多义未改 | 批次 3 |
| §14「说明文字不小于 12px」 | 只改了 `.agent-role`（11→12px）；`.rail-foot`、`.s0-access`、`.s0-checks b` 等仍是 10–11px（部分属「标签/图示注释」例外，需逐条判定） | 批次 3 |
| `WEB_UI_SPEC.md` 两个 `## 13`（802 旧 / 854 新） | **前序 T3 遗留**（非本轮）：新 §13 排在 §14 之后且编号重复；本轮只增补 A12/A13/§14，未重排章节 | 文档治理（需单独变更） |
