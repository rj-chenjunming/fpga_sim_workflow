# AUDIT-20261030-UI 设计审视（按 ai-design-skills）

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-30（Asia/Shanghai） |
| 审计对象 | 运营台界面 `loop/web/**`（`index.html` 662 行、`app.css` 1213 行、`tokens.css` 17 行、`legacy.css` 75 行、`app.js` 3946 行及其余前端模块）；静态历史样张 `loop/web/mockup.html` 只作对照 |
| 判据 | 技能 `~/.dsh/skills/ai-design-skills/SKILL.md`（md5 `b36d1be28c24fcc890b1926a7afed220`；位于用户级 skills 目录，**不在本仓**）+ 本仓视觉权威 [`doc/spec/WEB_UI_SPEC.md`](../spec/WEB_UI_SPEC.md) §10/§13/§14 + 仓库纪律 [`AGENTS.md`](../../AGENTS.md) §2/§3/红线 4/8 |
| 组织方式 | Lead 汇总；3 名独立审计员（CSS 令牌 / 运行时实测 / 文案语义）+ 1 名独立复核员（只报告不改） |
| 本轮是否修复 | **否**。只审计与登记，未改 `loop/**`、`doc/spec/**`、`doc/STATUS.md`、`doc/plans/**` |
| 本次写入 | 本文件 + 四份分报告（[`doc/audit/parts/ui-design-20261030/`](parts/ui-design-20261030/)）+ [`doc/evidence/UI_DESIGN_AUDIT_20261030/`](../evidence/UI_DESIGN_AUDIT_20261030/README.md)；原始截图/脚本的临时件仍在未入库的 `.ui-audit/` |
| 工作树 | 审计开始/结束时 `git status` 的**已跟踪文件改动均为 23 项**（前序 T3 等未提交件，**非本轮产生**）；本轮只新增上述 3 个未跟踪路径，未 `git add` / `git commit` |
| 结论计数 | **P0 = 0 / P1 = 4 / P2 = 16**，另有 9 项主动判「不建议改」、10 项「已做对」 |

---

## 1 结论：有值得优化的空间，但不是「重做视觉」

现有视觉基线是**合格且诚实**的：零外部依赖、深色侧栏 + 雾白主区、四视图结构、空/加载/错误三态齐备、
侧栏 sticky 自滚动、`prefers-reduced-motion` 真降级、原生 `<dialog>` + roving tabindex（§5 列了 10 条带证据的「做对了」）。
缺口不在「好不好看」，集中在三处，且三处的修复成本递增：

| 类别 | 结论 | 条数 |
|---|---|---|
| **A. 主路径摩擦** | 「环境准备」页在三个验收视口下，**唯一必填项与提交行都在折叠线之外**；「人工闸门」页的**材料/操作两栏整体在首屏之外** | 1（P1）+ 1（P2） |
| **B. 可读性硬指标** | 信息性小字对比度 3.27–4.36:1、唯一必填输入框焦点环 1.39:1 —— 不是审美偏好，是 WCAG AA 不达标 | 2（P1） |
| **C. 体系债** | tokens.css 之外有 **401 次硬编码颜色（93.9%）、与 25 个令牌值零重合**；`app.css` 是「先骨架后覆盖」两段式（50.6% 的选择器被后文重写）；字号 30 档、圆角 13 档、间距 36 档；`cubic-bezier` 0 处、`:active` 0 处 | 1（P1）+ 15（P2） |

**一句话回答**：值得优化；**最大收益不是换配色或换字体，而是把「首屏该看到什么」和「说明文字读不读得清」修掉
（不动业务契约），然后把令牌与字号口径先写进 §14 再收敛——否则下一轮 UI 改动只会在两段式 CSS 上继续漂移。**

> **口径更正（必须先看）**：CSS 审计员初判 P0=2（字号阶外 68.6%、令牌外 401 色）。独立复核逐字对读
> `WEB_UI_SPEC.md:825` 后推翻：§14 写的是「稳定字号阶梯 + 主正文 13–14px + 说明文字 12px」，
> **并未采用 Tailwind 阶梯**，13px 恰是规格授权值；故「68.6% 阶外」只是与**技能**口径不符（P2），
> 不是与项目规格冲突。令牌 401 色则确与 §14:826「共享配色令牌」冲突，但无用户可观察伤害 → P1。
> 三条对读差异与理由见 [`D-independent-verify.md`](parts/ui-design-20261030/D-independent-verify.md) §1/§3。

---

## 2 方法与边界

### 2.1 技能是「落地页设计系统」，必须先裁剪

技能明确定位是落地页（`SKILL.md:8-11`「one offer → one audience → one primary action」），本项目是**单机内网运营台**。
逐条裁剪如下，**N/A 的条款不得计入缺陷**：

| 技能条款 | 本项目适用性 | 判定依据 |
|---|---|---|
| Part A1–A8（intake / 页面结构 / 版式选型 / 转化 / 构建顺序 / SEO） | **N/A** | 运营台无「一个 offer、一个主 CTA」转化结构；无公网流量 |
| A5 文案（具体数字、收益优先） | 部分 | 只适用「说清事实、别堆空话」，不适用「benefit-first 推销」 |
| B1 字体/字号阶梯/字重 | **部分** | 字号阶梯与项目 §14:825 口径不同；字体族规则（禁 Inter）可迁移，但要本地化 |
| B2 间距表、B3 圆角表 | 部分 | 无项目规格依据，最多作「收敛方向」，不作硬缺陷 |
| B4 边框/背景 | 部分 | 「卡片不单侧加边框」原文限 `a card`；实测 26 处单侧边全是 1px 分隔线（15 dashed / 11 solid），无卡片单侧粗边 → 不判违规 |
| B5 Hero（680px、标题渐变） | **N/A** | 运营台无营销 hero；技能唯一允许的文字渐变本项目不使用 |
| B6 图标库 | 部分 | 「禁 Material」已满足；「只允许 Phosphor/Solar/Iconamoon」需本地打包才不破 §14:842 |
| B7 动效 | 可迁移 | 基准曲线、禁动画 width、reduced-motion 三条都可直接判 |
| B8 内容真实感 | 部分 | 中文本无大小写，sentence case 只在英文片段适用；禁用营销词可迁移 |
| B9 状态集 | 可迁移 | 但 skeleton 只适用「首次布局加载」，不适用轮询型运行状态徽标 |
| B10 上线清单 | 部分 | og/privacy/cookie/404 属公网发布 → **不适用**；skip link、语义标签、焦点可见仍适用 |
| B11 Tagline reveal | **N/A** | 落地页专属版面；照搬会违反 §14:841「不改交互不变量」 |

### 2.2 证据三类，缺一不用

1. **静态枚举**（可复跑命令）：字号/间距/圆角/hex/选择器重复/`:active`/`cubic-bezier` 的计数。
2. **Chromium 实测**：`measure.py` 在 1280×720 / 1440×900 / 1920×1080 三档视口取计算样式与包围盒。
   **数据来自受控 API 夹具，不是真实运行**；夹具文案（「未记录」「ignored」）不作缺陷结论。
3. **逐行对读**：`file:line` 原文对读（含规格、`kb_lib.GATE_DECISIONS`、既有审计 F14 登记）。

所有数字来自命令输出；本报告中由实测值做减法得到的预测（如「去掉 hero 后约 813px」）**均标注为推算**。

---

## 3 P1（4 条）：下一轮优先修，且大多不需要改契约

### D-01 首屏：运营台主路径被「落地页式 hero + 96px 页头 + 阶段卡」挤到折叠线下（合并 B-02 + C2）

**实测**（`measure.json` `M6_fold`，受控夹具，`getBoundingClientRect`）：

| 视口 | 页头 `.page-head` | `.s0-hero` | 阶段卡 | 唯一必填 `#s0Rtl` | 主操作 `#s0Prepare` | 首屏可见 |
|---|---|---|---|---|---|---|
| 1280×720 | y=100 h=96.4 | y=222.4 **h=252** | y=496.4 h=122 | **y=793** | **y=1098.1** | 否（差 378px） |
| 1440×900 | y=104 h=96.4 | y=226.4 **h=265** | y=513.4 h=106.8 | y=794.8 | **y=1078.3** | 否（差 178px） |
| 1920×1080 | y=110 h=96.4 | y=236.4 **h=275** | y=533.4 h=106.8 | y=814.8 | 1066.5 | 仅 32% 可见 |

**同类**：人工闸门页 `#gateMaterial`/`#gatePanel` y=909.6 / 913.6 / 885.5，`visibleRatio` 在 1280/1440 为 **0**
——操作员被叫到闸门页做决策，首屏只有四段流程卡（P2 的 D-13，因修复触到 §14 写死的 `--gate-pane-max-h`）。

**为什么算缺陷**：`WEB_UI_SPEC.md:824` 只要求「主区保留清晰页标题、用途描述和视图编号」，**没有 hero 条款**；
`§14:827` 的验收视口是 1280/1440/1920，主路径首屏看不到主操作是可直接观察的任务摩擦。
技能侧对应：A2「above the fold 必须含主操作」、B8「真文案而非营销腔」——这是**把落地页 hero 搬进运营台**的错位。

**证据强度**：高。三档视口的 `#s0Rtl`/`#s0Prepare` y 值与 `measure.json` 逐位一致；截图
[`01-s0-1280x720-first-screen.png`](../evidence/UI_DESIGN_AUDIT_20261030/screens/01-s0-1280x720-first-screen.png)、
[`02-s0-1440x900-first-screen.png`](../evidence/UI_DESIGN_AUDIT_20261030/screens/02-s0-1440x900-first-screen.png) 目视一致。
文案层同屏四次说同一件事（`index.html:61` 副标题、`:72` hero 标题、`:73` hero 副文、`:80-81` 阶段卡）。

**修复方向**：hero 改紧凑任务页头（约 64px：眉题 + 一句用途 + 主操作），阶段卡并成一行；
**推算**：1440×900 下删 hero 后 `#s0Prepare` ≈ 813px（1078.3 − 265，属算术推算非实测），可进首屏；
1280×720 还需同时压缩页头与阶段卡才能进首屏。→ **A 类（不改契约）**。

### D-02 信息性文本对比度不足 4.5:1（B-04）

实测 S0 视图 **28/209** 个文本节点 <4.5:1（gate 14/173、monitor 33/238）。剔除装饰符后仍不合格的是**信息文本**：

| selector | 前景/背景 | 对比度 | 字号 | 用途 |
|---|---|---|---|---|
| `.diagram-caption` | `#768970` on `#eaf1e7` | **3.27** | 9px | 「原始资产保留 · 准备过程可追溯」 |
| `.page-edition` | `#7b8b81` on `#f4f6f5` | **3.31** | 9px | 「SIMULATION WORKBENCH」 |
| `.diagram-label` | `#71876a` on `#eaf1e7` | **3.39** | 8px | 「CONTROLLED DERIVATION」 |
| `.section-index` | `#698563` on `#f8faf6` | **3.89** | 12px | 卡片分区字母 A/B/C… |
| `.foot-note`（`--faint #71827b`） | on `#fff` / `#f4f6f5` | **4.05 / 3.73** | 12px | 脚注说明 |
| `#s0Blockers p` | `#8c724c` on `#fffaf0` | **4.36** | 12px | 执行前阻断说明 |

最低值 1.53:1 是页头装饰分隔符 `/`（`#c7d4cc` on `#fff`），按装饰处理不计。
`--muted #61746c` 实测 4.97（白）/4.58（雾白）**合格**，侧栏 `--rail-muted` 6.94 **合格**。

**为什么算缺陷**：`§14:825` 明文「说明文字 12px」并把「稳定字号阶梯」写进契约，说明文字的可读性是规格意图；
WCAG AA 1.4.3 对 <18.66px 文本要求 4.5:1。这不是风格偏好 → **A 类（改色值即可，不动契约）**。

### D-03 焦点环对比不足（B-08）

| 位置 | 环 | 底 | 对比度 |
|---|---|---|---|
| `#s0Rtl`（唯一必填输入框） | 2px `#c4e2cf` | `#fff` | **1.39** |
| 侧栏 `#btnS0` / `#segS0` / `.run-item` | 3px `--primary #15775e` | `--rail #192e28` | **2.62** |
| 合格对照（白底按钮） | 3px `#15775e` | `#fff` | 5.48 |

22 个 Tab 停靠点中 21 个可辨（这是优点，见 §5），但**唯一必填项**的环最弱。WCAG 1.4.11 要求非文本对比 ≥3:1。
→ **A 类**：输入框焦点环改 `--primary`；侧栏环改浅色（如 `#b9d5aa`，与 `#192e28` 对比 ≥3）。

### D-04 配色令牌形同虚设（A-01，§14:826 明确违反）

| 事实 | 数值 | 复核方式 |
|---|---|---|
| `tokens.css` 定义的色值 | 25 个 | 解析 `--*: #hex` |
| `app.css` + `legacy.css` 的 hex 出现次数 | **401**（其中 93.9% 在 tokens.css 之外） | 正则计数 |
| 6 位 hex | 335 次 / **239 个不同值** | 同上 |
| 6 位 hex 与任何 token 值重合 | **0** | 集合交集 |
| `var(--radius)` 使用 | 3 处 / 字面圆角 118 处 | grep |

`§14:826` 要求「组件：**共享配色令牌**…采用同一系统」。现状是令牌没被消费，而是 239 个手写近似值
（如 `#c7d4c8` vs `--line-strong:#c7d4cc`、`#f1f6f2/#f1f4ee/#f1f5ef` 三近白并存）。
**根因**：`app.css` 两段式——第 468 行起的「视觉系统」段重写了前半段；956 条顶层规则 / 784 个选择器 /
**183 个被 ≥2 条规则定义**，前 342 个选择器有 **173 个（50.6%）** 被后段覆盖。这属**已登记项**：
`AUDIT-20261021-post-ui-roadmap.md:33` 的 F14 已定性「维护成本、非渲染事故」，并明确「不能按同一选择器出现两次就自动删除」。

**为什么是 P1 而不是 P0**：违反规格明文，但无用户可观察伤害（颜色彼此接近，视觉上还不难看）。
**为什么值得优先**：不先合并两段式，任何「换令牌」都会被后半段覆盖 → 顺序必须是 **F14 合并 → 令牌化**。
→ **A 类**（规格已要求，属实现未落地）。

---

## 4 P2（16 条）：打磨与体系一致性

| id | 问题 | 关键证据 | 建议方向 | 分类 |
|---|---|---|---|---|
| D-05 | `--font-sans` 首选 Inter，但全仓无 `@font-face`/`url(`；实测拉丁回退 **Liberation Sans**（Arial 度量）、CJK **Noto Sans CJK SC**、等宽 Liberation Mono；宽度探针 Inter == 不存在族（643.27） | `tokens.css:15`；`measure.json M1_fonts` | 删掉 Inter 声明，保留平台栈并注释「无本地字体资产」；技能禁用 Inter/Arial 属技能口径，不违反 §14:842 | A |
| D-06 | 字号 30 档；桌面路径 126 处 <12px；`.agent-role` 11px、`.foot-note` 11.5px（后者被 `:562` 覆盖为 12px，属死声明）落在 §14:825「说明文字 12px」之下 | `app.css:695/309/562`；`measure.json M2` | 先立字号表（B 类），再把说明文字提到 12px；标签/图示 8–11px 由 §14 明文允许，不改 | B→A |
| D-07 | 等宽字体用于图注 `.diagram-flow b`（`BASELINE`/`WORKSPACE`），超出 §14:825「路径/身份/计数/日志」 | `app.css:585` | 图注改正文族；序号属「计数」可保留 | A |
| D-08 | 6 条 transition 全部无显式曲线（浏览器默认 `ease`），0 处 `cubic-bezier(0.22,1,0.36,1)`；80 个元素 150ms；`.stage-bar i` 动画 `width`（技能明令只动 transform/opacity） | `app.css:164/168/306/403/544/551`；`app.js:1638-1640` | 加 `--ease-out` 令牌统一引用；进度条改 `transform:scaleX()`；hover ≥200ms | A |
| D-09 | `:active` 全站 0 处（`.btn`/`.run-item`/`.snode`/`.seg button` 均无按下反馈） | `grep -c ':active'` = 0 | 补 `:active{transform:translateY(1px)}` | A |
| D-10 | 加载态只有纯文字、无骨架（正文级 6 处 + chip 3 处）；`spinner` 只用于运行中状态（用法正确，**不**应改） | `index.html:107/173/180/210/280`（另有 `202/415/546` 的 chip） | 首屏 4 个卡片各给 2–3 行灰块骨架 | A |
| D-11 | `.agent-open` 点击靶高 **19.5px**（5 个实例）< 24px | `measure.json M7_targets_monitor` | 加内边距到 ≥24px | A |
| D-12 | `main:focus{outline:none}`：skip-link 跳转后焦点落在 `main` 但**零视觉反馈**（skip-link 本身可用，环 5.05:1） | `index.html:56`；`app.css:479` | 改 `main:focus-visible` 给 2px 内嵌环 | A |
| D-13 | 闸门材料/操作两栏 y≈910，1280/1440 首屏外；缩小上方留白可直接做，动 `--gate-pane-max-h` 则是改 §14:831-836 的承诺（`doc/STATUS.md:6411` §135 P2-5 已登记「改常数=改规格承诺，需人裁」） | `measure.json M6b_gate_fold` | 先压缩 `#gateHead` 与阶段卡高度；常数改动走人裁 | A/B |
| D-14 | 唯一背景渐变在单选选中点（15×15 `radial-gradient`） | `app.css:242` | 改「边框 + 实心背景」两层，去渐变 | A |
| D-15 | 两段式 CSS（见 D-04 根因）；= 已登记 F14 | `app.css` 956 规则 / 183 重复 | 按组件合并有效声明，逐组件 + 截图对照，禁止按次数删规则 | B |
| D-16 | 图标系统缺失：约 20 个 Unicode 码位承担图标，且**多义**（`▧` 既是导航「环境准备」又是「基线」图；`◇` 既是「人工闸门」又是空态插图）；`⚠/⛔` 在 legacy 依赖 emoji 字体 | `index.html:38-41/76`；`app.css:568`；`legacy.html:764` | 自绘 16×16 inline SVG sprite（不破 §14:842 零外链），一符一义 | A |
| D-17 | 三个页面均无 `<nav>`（导航在 `<aside>` 内以 tablist 承担）；`legacy.html` 无 skip-link | `grep -c '<nav'` = 0 | `.seg` 外层包 `<nav aria-label="主导航">`；legacy 补一行 skip-link | A |
| D-18 | 界面三处以「GATE-1」下达闸门，但该身份**有名未映射**：`S0_ENVIRONMENT_SPEC.md:11/34` 命名，`kb_lib.GATE_DECISIONS`（`kb/tools/kb_lib.py:556-560`）只有 G1/G2/G3，`OPTIMIZATION_PLAYBOOK.md:159` 要求「不能默认为同一身份」 | `index.html:104/142`、`s0.js:77` | 先由人裁 GATE-1↔G1 映射，再统一文案；不要在前端自建闸门名 | B |
| D-19 | 文案/口径一致性打包：运行/阶段/Agent 三套状态词（`执行中`/`进行中`/`工作中`，`app.js:75/1521/1766`）；状态判据三份（`:74-81/375-381/383-389`）；三页产品名不一；`↗` 一符三义；两处 `window.confirm`；`.chip` 同时表示实现状态/运行状态/校验结论 | 见 [`C-content-semantics.md`](parts/ui-design-20261030/C-content-semantics.md) §5/§6 | 冻结一份状态词表与一份 chip 语义，其余降级为说明文字 | A |
| D-20 | 三页无 favicon（浏览器默认图标） | `index.html` `<head>` 仅 title+2 CSS | inline `data:` URI 图标，不破零外链 | A |

---

## 5 主动判「不建议改」（避免过度设计、避免为改而改）

| 项 | 为什么不做 |
|---|---|
| 单侧边框（A-11 原判） | 技能原文限 `a card`；实测 26 处单侧边全是 1px 分隔线，`.card` 四边齐全 → 违规不成立 |
| 圆角 `999px`（A-09 原判） | Tailwind `rounded-full` 等价写法，合规 |
| 按钮 8/12 padding、16px semibold（A-06/A-07） | 与 §14:825「主要表单 13–14px」的紧凑密度冲突；38px 固定高度已产生等效视觉；落地页按钮口径不迁移 |
| 间距/圆角全量吸附（A-08/A-09/A-10） | §14 无间距表；748 处 padding/margin 全量重排无用户收益、回归面大 |
| 全站 skeleton（A-16 原判） | `spinner` 是运行状态播报而非布局加载；只有 D-10 的正文级「加载中」适用骨架 |
| 暗色主题（B-13） | §14 无暗色要求；`tokens.css:3` 是有意单主题（深色只用于侧栏导航）。不做未验证主题 |
| 全大写英文眉题（C19） | 中英双标是本仓既有做法（编号/分区标牌，非标题）；§14 未禁止 |
| `mockup.html` 内部 | §14 明文「静态历史样张不重绘」 |
| `legacy.html` 内联字体栈含 Roboto | 被 `legacy.css:2` 的 `var(--font-sans)` 覆盖，无实际效果 |

---

## 6 做对了什么（防止报告变成单向否定）

1. **侧栏 sticky 自滚动**：`app.css:497` `position:sticky;top:72px;height:calc(100vh-72px);overflow:hidden auto`，逐字对应 §14:828-834，并有回归用例 `test_web_layout.py::test_sidebar_entries_are_reachable_at_acceptance_viewports`。
2. **闸门两栏局部滚动 + `scrollbar-gutter:stable`**：`app.css:670/674-677`，落在 §14:835-840 的写死常数上。
3. **`prefers-reduced-motion` 真降级**：`app.css:763`、`legacy.css:75`；实测 reduce 下 `elementsWithMotion=0`。
4. **skip-link 可用**：`index.html:11` + `app.css:476-477`；实测获焦后 `top:-80px → 12px`，环 5.05:1。
5. **焦点环系统**：`app.css:478` 3px `--primary` + offset 3px；21/22 停靠点可见（白底 5.48:1）。
6. **三个视口零水平溢出**：`scrollWidth - innerWidth = 0`（1280/1440/1920）。
7. **零外部依赖**：`@font-face` 0、`url(` 0、`loop/web/**` 内 `http(s)://` 0 —— 同时满足 §14:842 与 §10 A8（「页面无外部链接」）。
8. **三态齐备且错误内联**：empty/loading/error 截图三张；5 处 `role="alert"`、`window.alert()` 0 处。
9. **原生 `<dialog>` + roving tabindex**：3 个 dialog 全部 `showModal()` + `aria-labelledby`；tablist 方向键 + Home/End（`app.js:3750-3762`）。
10. **语义基础**：真 `<table>` + `<th scope>`、状态条 `<dl>`、h1→h4 无跳级、`lang="zh-CN"` 三页齐备、零 `<img>`（alt 条款不适用）。

---

## 7 建议的优化批次（若采纳，下一轮先落 `doc/plans/`）

| 批次 | 内容 | 分类 | 涉及文件 | 验证门 |
|---|---|---|---|---|
| **1 可读性**（收益/成本比最高） | D-02 对比度、D-03 焦点环、D-12 main 焦点、D-09 `:active`、D-08 动效、D-05 删 Inter、D-10 骨架、D-20 favicon、D-19 状态词表 | A | `tokens.css`、`app.css`、`app.js`、`index.html` | 浏览器全量（基线 `166 passed`，见 `doc/STATUS.md:6644`）+ 三档截图对照 + 新增 3 条断言（`--faint` 对比、`#s0Rtl` 环对比、`#s0Prepare` 首屏可见） |
| **2 首屏** | D-01：hero → 紧凑页头；阶段卡并一行；提交行上移；顺带删重复叙事；D-13 只做「压缩上方留白」 | A | `index.html`、`app.css` | 1280/1440/1920 首屏断言（`#s0Rtl` 与 `#s0Prepare` 的 `fullyInFirstScreen`）+ 全量浏览器门 |
| **3 体系收敛** | 先改 §14：①补字号表与 12px 说明文字下限；②明确「组件层不得硬编码 hex，色值只来自 tokens.css」；再按 F14 合并两段式；再 token 化（目标：tokens 外不同色值 <20） | B → A | `doc/spec/WEB_UI_SPEC.md`（Lead）、`app.css` | 先跑特征测试（受控夹具截图 + 既有浏览器用例），合并后才动色值；每片单独提交 |
| **4 需人裁 / 可并行** | D-18 GATE-1↔G1 映射（改规格或中性化文案）；D-13 闸门常数（`doc/STATUS.md:6411` §135 P2-5 已登记需人裁）；D-16 图标 sprite（可独立于上三批）；若要长期守首屏/对比度，§10 增 A12+ 判据 | B / A | `doc/spec/**`、`loop/web/**` | 人裁记录 + 对应浏览器用例 |

> **「只做一件事」建议**：批次 2（首屏）。它不动任何业务契约、不碰请求形状，直接消除「每次开工都要先滚一屏」的摩擦；
> **「只做两件事」**：+批次 1 的 D-02/D-03（可读性硬指标，属 WCAG AA）。

---

## 8 未实测 / 不确定（不得当作已证）

- `measure.json` 来自**受控夹具**：真实长路径、超长错误串、真实运行文案下的对比度未测。
- 未在真实服务进程上复测（本轮未启动 `loop/services/api.py`，未写数据根）。
- 未在非 Chromium 浏览器验证字体回退、焦点环、`scrollbar-gutter` 渲染。
- hover / active / loading 的**视觉**未截图实测，只读了计算样式与 CSS 声明。
- `.ev-chip`/`.linkbtn`/`.hero-stamp` 在当前三视图中 0 个元素渲染，`app.css:340/341` 的 65px/7px 属死规则，只能静态判定。
- 移动端/窄屏按 §14:827 与 §10 是明确非目标，未验、不建议验。
- 「去掉 hero 后 `#s0Prepare` ≈ 813px」是**算术推算**（1078.3 − 265），非实测，需批次 2 落地后实测确认。

---

## 9 证据与复跑

| 证据 | 位置 | md5 |
|---|---|---|
| 归档证据目录 | [`doc/evidence/UI_DESIGN_AUDIT_20261030/`](../evidence/UI_DESIGN_AUDIT_20261030/README.md) | — |
| 测量脚本（归档副本，第 31 行 repo 解析已改，差异见其 README §3） | `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py` | `b2ebd148c4338915a2eea597752e5bea` |
| 原始测量数字 | `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.json` | `09979b74dcd6735a3b53e29e1f5e2898` |
| 复跑一致性 | `.../repro-diff.txt`（与归档 JSON 仅 6 处差异，全是 ephemeral 端口，exit=0） | — |
| CSS 静态审计分报告 | [`A-visual-tokens.md`](parts/ui-design-20261030/A-visual-tokens.md)（归档副本；原 `.ui-audit/A-visual.md` md5 `6b0e74e37337803e6ac51196aecc4f36`） | `319fc0e418e838609a24ac19aace8248` |
| 运行时实测分报告 | [`B-runtime-measured.md`](parts/ui-design-20261030/B-runtime-measured.md)（原 md5 `97eb69b3770286b3f5bde6e2e0b3a947`） | `b20efdb69916addd8e4ba1d2d2b751bc` |
| 文案语义分报告 | [`C-content-semantics.md`](parts/ui-design-20261030/C-content-semantics.md)（原 md5 `1a400788d6a1e6c690712ca5eb753f07`；归档时改了 1 处「计划新建路径」表述） | `a2ee45322d412e8345e8407d06d68c70` |
| 独立复核报告 | [`D-independent-verify.md`](parts/ui-design-20261030/D-independent-verify.md)（原 md5 `0a36b232e37e16c51c1ed4bae239335d`） | `ce4b9e5ebe747a37e383eccc0c5d2df9` |

复跑测量（repo 根，约 2 分钟，只写 `.ui-audit/` 或证据目录）：

```bash
PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
  loop/.venv/bin/python doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py
```

本轮跑过的既有门（**与 UI 改动无关，只证明审计期间基线未被破坏**）：

| 命令 | 实际输出 |
|---|---|
| `cd loop && PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… LOOP_VISUAL_ARTIFACTS=… .venv/bin/python -m pytest -q tests/browser/test_web_layout.py` | `12 passed in 16.34s`（受控夹具，非真实服务） |
| `python3 doc/audit/check_doc_links.py` | `checked=3059 skipped=43762 historical=857 known_missing=16 env_missing=35 missing=0`（exit 0；本轮新增文档零断链） |

**本轮未跑**：软件单测四道门、kb 自测、端到端、真实服务浏览器门——本审计不改 `loop/**` 实现，无需这些门；
**不声称四道门全绿**，也不声称界面在真实运行数据下已复测。

---

## 附录 A 三份分报告与复核的口径差异

| 项 | 分报告原判 | 复核后 | 理由 |
|---|---|---|---|
| 字号 30 档 / 68.6% 阶外（A-02） | **P0**「与 §14 冲突」 | **P2** | §14:825 未采用 Tailwind 阶梯，13px 是授权值；技能口径≠项目口径 |
| 令牌外 401 色（A-01） | **P0**「与 §14 冲突」 | **P1** | 规格违反成立（§14:826），但无用户伤害 |
| 对比度（B-04） | P2 | **P1（升）** | 信息文本 3.27–4.36 属可读性缺陷，不是装饰 |
| 焦点环（B-08） | P2 | **P1（升）** | 唯一必填项 1.39:1，键盘用户几乎不可见 |
| `:active`（A-15） | P1 | P2 | 纯状态打磨，不阻塞操作 |
| 重复选择器（A-18） | P1「新发现」 | P2（**已在册 F14**） | 前序审计已定性维护成本 |
| 单侧边框（A-11） | P2「违规」 | **C 类不改** | 技能原文限 `a card`；实测全是分隔线 |
| `spinner` 应换骨架（A-16） | P2 | **不成立** | spinner 是运行状态播报；骨架只适用正文级「加载中」 |
| `GATE-1`「身份不存在」（C3） | P1 | **P2 / 改规格类** | `S0_ENVIRONMENT_SPEC.md:11/34` 有名，缺的是映射（`PLAYBOOK:159`） |
| 证据缺陷 | — | 已改正 | C 引用了不存在的 `measure.stdout.txt`；截图实为 24/20 张（非 25/17）；A 的 65px/7px 是死规则 |
