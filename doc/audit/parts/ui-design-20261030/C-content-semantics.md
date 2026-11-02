# C：UI 文案 / 语义 HTML / 图标 / 状态与上线项审计

> **归档副本（2026-10-30）**：原文件在审计工作区 `.ui-audit/C-content.md`（未入库临时件）；归档时更名，内容除本行与下列唯一修改外未改。范围：§0–§12 + N/A 清单。
> 原始 md5 记录见 [`../../evidence/UI_DESIGN_AUDIT_20261030/README.md`](../../evidence/UI_DESIGN_AUDIT_20261030/README.md)。

> 审计对象：`loop/web/{index,legacy,mockup}.html`、`loop/web/app.js`（渲染模板与静态文案）、`agent-window.js`、`node-detail.js`、`s4-view.js`、`legacy.css`。**全部只读，本轮不修改任何被测文件。**
>
> 判据：`ai-design-skills/SKILL.md`（A/B 部分）、`doc/spec/WEB_UI_SPEC.md` §10 验收判据 + §14 视觉系统 + §13 S0 条目、`AGENTS.md` 红线 4。
>
> 证据来源：① 逐行通读 + `file:line` 原文引用；② `.ui-audit/measure.json` M5/M6（受控夹具渲染的 `getBoundingClientRect` 实测，非真实运行）；③ `.ui-audit/shots/*.png` 仅作定性比对。**未运行的项不推断。**
>
> 严重度定义：P0 = 违反验收判据或主路径不可达；P1 = 明确缺陷、改动小收益大；P2 = 打磨项。

## 0 结论摘要

| 级别 | 条数 | 明细 |
|---|---|---|
| P0 | **0** | 未发现违反 §10 A1–A11 的文案/语义项 |
| P1 | **3** | C1 图标系统缺失、C2 S0 落地页式 hero 错位、C3 `GATE-1` 未定身份当既定事实 |
| P2 | **16** | C4–C19（术语/状态词/键位可达/语义标签/上线项/owner 纪律） |

**先给正向结论（避免下文看起来像全面否定）**：`lang`/`<title>` 三页齐备；零外部依赖（`http(s)://` 在 `loop/web/**` 中 0 处命中，满足 §14「无 CDN、外部字体或运行时依赖」与 §10 A8）；3 个原生 `<dialog>` 全部 `showModal()` + `aria-labelledby`；四段折叠头是带 `aria-expanded` 的 `<button>`（`app.js:1629-1631`）且 `▸` 由 CSS 旋转（`app.css:169`）；tablist 实现了 roving tabindex + 方向键 + Home/End（`app.js:3747-3763`），**符合 ARIA APG，不是缺陷**。

---

## 1 图标（技能 B6）

技能只允许 Phosphor / Solar / Iconamoon，禁用 Material Icons/Symbols。本项目**两者都不是**：`loop/web/` 下无任何图标资产（`ls` 无 `*.svg/*.ico`、无 icon font、`grep url(` 仅 `background-image:none`），全部图标由 Unicode 字符承担。

| id | 问题 | 证据（file:line，原文） | 条款 | 级别 | 与项目规格冲突 | 建议 |
|---|---|---|---|---|---|---|
| C1 | **「图标系统缺失」成立**：15 组、约 20 个 Unicode 码位充当图标，且无语义层、无统一描边/尺寸，跨平台字形由系统字体决定（本轮实测拉丁文本落 `Liberation Sans`、CJK 落 `Noto Sans CJK SC`，见 `measure.stdout.txt` M1 的 `platformFonts`） | 见下表 glyph 清单 | B6 | **P1** | **是**：§14「所有字体、装饰和图标本地化，无 CDN、外部字体或运行时依赖」⇒ 引入 Phosphor/Solar 必须本地打包（约 3–7 个 SVG 或一份子集字体），不能走 CDN | 自绘 16×16 inline SVG sprite（对齐 §14 零外链最省），或本地打包 Phosphor 子集；两者都不违反 §14 |

**Glyph 清单（file:line）**

| 码位 | 用途 | 出现处 | 语义歧义 |
|---|---|---|---|
| `▧` U+25A7 | 导航「环境准备」 | `index.html:38`；`index.html:76`（图为 BASELINE） | 同一字符两义 |
| `⊞` U+229E | 导航「运行配置」 | `index.html:39`；`index.html:76`（图为 WORKSPACE） | 同一字符两义 |
| `◴` U+25F4 | 导航「运行监控」 | `index.html:40` | 时钟字形与 `◴` 无既有约定 |
| `◇` U+25C7 | 导航「人工闸门」；**空态插图** | `index.html:41`；`app.css:568` `.empty:before{content:"◇"}` | 导航项与空态共用 |
| `⌄` U+2304 | 侧栏入口尾部箭头 | `index.html:33` | **下拉箭头却没有下拉面板**：点击只做 `showView("s0")`（`app.js:3738`），无展开态 |
| `＋` U+FF0B | 新建运行 | `index.html:34`、`299`；`app.js:728`、`1238` | 全角加号，与 `+` 不同码位 |
| `✓` | 已完成 | `app.css:338`（hero 标签）、`app.js:1497`、`1632`、`legacy.html:575` | 兼作「卖点勾选」与「状态已完成」 |
| `!` / `…` / `✕` | 等待 / 进行 / 失败 | `app.js:1498-1500` | 纯文本字符当状态图标 |
| `▸` / `▾` | 折叠指示 | `app.css:434-435`；`app.js:1644`（`▸`+CSS 旋转）；`app.js:3606` | 三处两种实现 |
| `×` | 关闭 | `index.html:416`、`547`、`618`、`634` | 有 `aria-label` 兜底，可接受 |
| `→` | 流程箭头 | `index.html:101`、`104`、`150`、`310`；`app.js:3110` | — |
| `↗` | 外链 / 下载 / 弹层**三义** | `index.html:21`（同标签页跳转）、`139`（下载）、`506`（新窗口，唯一正确用法）、`app.js:1779`（打开弹层）、`node-detail.js:790`、`1575`、`1740` | 见 C14 |
| `↑` | 上级目录 | `index.html:395` | — |
| `F` / `>_` | 工作空间图标 / 终端标记 | `index.html:33`、`413` | 裸拉丁字母当图标；`>_` 为装饰（已 `aria-hidden`） |
| `⚠` / `⛔` | 警告（旧界面） | `legacy.html:764`、`986`、`1301` | 彩色 emoji，缺 emoji 字体即豆腐块 |

---

## 2 落地页条款的唯一例外：S0 首屏 hero 错位

**判定：属错位，且代价可量化。** `#viewS0` 把落地页式首屏（英文眉题 + 营销式大标题 + 装饰流程图 + 卖点标签）放在运营台第一个可交互区域，而运营台首屏应当是「页标题 + 一句用途 + 第一项任务」。

| id | 问题 | 证据 | 条款 | 级别 | 冲突 | 建议 |
|---|---|---|---|---|---|---|
| C2 | 落地页 hero 抢占运营台首屏：hero 高度 250–275px（`app.css:571` `min-height:250px`；1440 实测 265、1920 实测 275），标题 1440 下 **29px/43.5px**（`app.css:574`；实测 `measure.stdout.txt` M3「29px/43.5px ratio=1.5」），装饰流程图 `index.html:76` 自带 `CONTROLLED DERIVATION`/`BASELINE`/`WORKSPACE` 三行装饰性英文 | `index.html:70-77`；`app.css:571`、`574` | A2、B8（hero 只属落地页） | **P1** | 否（§14 只要求「主区保留清晰页标题、用途描述和视图编号」，未要求 hero） | 改为紧凑任务页头（约 64px：眉题+一句用途+主操作），删装饰图 |

**折叠线实测（受控夹具，`measure.json` M6，`getBoundingClientRect`）**

| 视口 | `.page-head` | `.s0-hero` | `.s0-phases` | 唯一必填项 `#s0Rtl` | **主操作 `#s0Prepare`** | 是否首屏可见 |
|---|---|---|---|---|---|---|
| 1280×720 | y=100 h=96.4 | y=222.4 **h=252** | y=496 h=122 | y=793 | **y=1098.1** | 否（低于折叠线 378px） |
| 1440×900 | y=104 h=96.4 | y=226.4 **h=265** | y=513.4 h=106.8 | y=794.8 | **y=1078.3** | 否（低于折叠线 178px） |
| 1920×1080 | y=110 h=96.4 | y=236.4 **h=275** | y=533.4 h=106.8 | y=814.8 | **y=1066.5** | 仅 32% 可见（`visibleRatio=0.32`） |

> 结论：三个验收视口下，「派生并校验」这颗主操作**均在折叠线之外**（1280×720 尤其严重）。若该 hero 换成 64px 紧凑页头，1440×900 下 `#s0Prepare` 约前移至 **≈877px**，进入首屏。

**文案重复（这是 hero 多余的直接证据）**：页头副标题 `index.html:61`「从只读基线派生工作副本，**让每一次验证**都有据可查」与 hero 标题 `index.html:72`「**让每一次验证**，<br>都有可靠的起点。」相隔 11 行、同屏可见，共用同一句式和同一对概念（派生 / 工作副本）；同一叙事的第 3、4 次重复见 `index.html:73`（hero 副文）与 `index.html:80-81`（S0-a/S0-b 阶段卡）。B8「sentence case / 无空话」在中文语境下落到事实层就是：**同一屏四次说同一件事**。

---

## 3 文案规则：连字符与中英混排的**适用范围**（技能 B1/A5/B8）

中文无大小写，故 B8「sentence case」对中文标题/按钮**不适用**（判据应改为：中英混排的英文片段是否遵循同一大小写约定）。连字符在中文语境主要出现在三类地方，必须分开判：

| 类型 | 出现处与原文 | 判定 |
|---|---|---|
| ① 领域标识符（应保留） | `index.html:90`「新版 RTL 文件夹」；`index.html:101`「TB、TESTLIB、PKG」；`index.html:113`「S0 演练」 | **不算缺陷**，属权威命名 |
| ② 身份未定的腕造名 | `index.html:104`「准备完成后仍需 **GATE-1**」、`142`「完成 S0 两段及 **GATE-1** 后才能进入新版执行」、`s0.js:77`（同一句） | **P1 → C3** |
| ③ 内部代号/字段名直接暴露给操作员 | `index.html:109`「S0-**rehearsal**」；`index.html:98`「TOOL_ROOT/workspaces/原环境名-**derived**-时间戳」；`index.html:94`「（**origin_env_root**）」；`index.html:158`「预填 **s0_record_id** 与推荐基线」；`index.html:111`「自动完成一次 **copy** → 整体替换 RTL → 核验」；`120`「**copy→replace→核验**链路」；`app.js:49-53`「**simenv-analyst** / simenv-author / …」；`app.js:2733`「**ignored / disputed** 必须写理由」；`app.js:2758`、`3206` 同族 | **P2 → C4**，建议保留字段名但降级为悬停提示，正文用中文 |

| id | 问题 | 证据 | 条款 | 级别 | 冲突 | 建议 |
|---|---|---|---|---|---|---|
| C3 | 界面把「GATE-1」当作既定闸门下达，但该身份在权威里不存在：`kb_lib.GATE_DECISIONS` 只有 `G1_diff_confirm`/`G2_report_accept`/`G3_regression_decision`（`kb/tools/kb_lib.py:556-560`），而 `doc/plans/OPTIMIZATION_PLAYBOOK.md:159` 明确要求「**明确 GATE-1 与现有 G1 的对应关系，不能默认为同一身份**」 | `index.html:104`、`142`、`s0.js:77`；对照 `kb_lib.py:556-560`、`OPTIMIZATION_PLAYBOOK.md:159` | 红线 4 邻域 | **P1** | **是**（红线 4：闸门枚举权威 = `GATE_DECISIONS`） | 在身份未定前改为中性表述（如「完成 S0 两段与环境复核后」），或在文案后标注「(身份待定)」；不要在 `app.js`/`s0.js` 里自建闸门名 |
| C4 | 内部代号、字段名、英文枚举直接进正文 | 见上表 ③ 全列 | B1「no hyphens in copy」、B8「write the copy」 | P2 | 否（§14 要求等宽字体仅用于路径/身份/计数，隐含它们可以出现，但不构成正文用词） | 正文中文化；技术标识移到 `title` 或等宽小字 |

---

## 4 语义 HTML 与键盘（B10）

| id | 问题 | 证据 | 条款 | 级别 | 冲突 | 建议 |
|---|---|---|---|---|---|---|
| C5 | **全站 0 个 `<nav>`**（`grep -c "<nav"` 三页均为 0），四个页面入口放在 `<aside id="sidebar">` 内并以 `role="tablist"` 承担导航；`<article>` 亦为 0 | `grep -c '<nav'` → `index.html:0`、`legacy.html:0`、`mockup.html:0`；`index.html:30` `<aside id="sidebar">`、`37-42` `<div class="seg" role="tablist">` | B10「Semantic HTML: `<nav>`…」 | P2 | 否（§2 只要求「左栏」） | 把 `.seg` 外层包 `<nav aria-label="主导航">`；tablist 语义可保留在当前页内切换场景 |
| C6 | skip link 目标无视觉确认：`main tabindex="-1"` + `main:focus{outline:none}` 组合，跳转后焦点落在 `main` 但**没有任何视觉指示** | `index.html:56` `<main id="workspace" tabindex="-1">`；`app.css:478` 全局 `:where(button,a,summary):focus-visible` 焦点环；`app.css:479` `main:focus{outline:none}` | B9「Focus — a visible focus ring」、B10 skip link | P2 | 否 | 改为 `main:focus-visible{outline:2px solid var(--primary);outline-offset:-2px}`；skip link 本身合格（实测 `measure.stdout.txt` M5 第 17 步 `withOutline=3px`，可聚焦可见） |
| C7 | `legacy.html` 无 skip link、无 `<nav>`；该页仍被 §10 A7 验收（「`/legacy.html` 仍可访问」） | `legacy.html:168`（`<h1>` 起，之前无 skip link）；`legacy.html:169` 有返回入口 | B10 skip link | P2 | 否 | 旧界面只保留一个迭代，建议沿用 index 的 `skip-link` 一行即可 |
| C8 | 页内浮窗 `#ndDiffOverlay` 声明 `role="dialog" aria-modal="true"` 但**不捕获焦点**：`openOverlay()` 只把焦点送到关闭按钮，无 Tab 环，也不 `aria-hidden` 背景 | `index.html:610`；`node-detail.js:230-241`（`openOverlay` 全文），`node-detail.js:2024-2027` | B10 语义、B9 focus | P2 | 否 | 要么补 Tab 环，要么去掉 `aria-modal="true"` 只留 `role="dialog"`（不夸大语义） |

**语义合格项（勿动）**：3 个原生 `<dialog>` + `showModal()`（`agent-window.js:641`、`node-detail.js:311`、`report-viewer.js:98`）；标题层级无跳跃（`index.html` h1×1→h2→h3→h4，`legacy.html` 无 h3 跳级）；`role="tablist"/tab/tabpanel` 配套（`index.html:37-42`+`188/295/365`），`aria-selected` 与 `.on` 同步更新于同一循环（`app.js:610-616`），并带 roving tabindex（`app.js:614`）与方向键（`app.js:3747-3763`）；唯一表格用真 `<table>`+`<th scope="col">`（`index.html:474-482`）；状态条用 `<dl>`（`index.html:436-447`）。

---

## 5 状态（B9）与关键词一致性

| id | 问题 | 证据 | 条款 | 级别 | 冲突 | 建议 |
|---|---|---|---|---|---|---|
| C9 | **`:active` 态全站缺失**：`app.css` 中 `:hover` 19 处、`:active` **0 处** | `grep -c ":active" app.css` → `0` | B9「Active — scale(0.98) 或 translateY(1px)」 | P2 | 否 | 给 `.btn/.run-item/.snode/.seg button` 加 `:active{transform:translateY(1px)}` |
| C10 | 加载态**只有文字、无骨架屏**（技能明确要求「skeleton loaders shaped like the real layout, not circular spinners」）；现有 `spinner` 只用于运行中状态，用法合理 | `index.html:107`「加载中…」、`173`、`180`、`210`「加载中」；`app.css:221-223` `.spinner`；`app.js:1282`、`1805` 仅状态处使用 | B9 Loading | P2 | 否 | 4 个首屏卡片各给 2–3 行灰块骨架即可，其余保留文字 |
| C11 | **同一概念三套状态词**：运行=「执行中」，阶段聚合=「进行中」，Agent=「工作中」 | `app.js:75` `running: "执行中"`；`app.js:1521` `"进行中"`；`app.js:1766` `working: "工作中"` | B8「system messages calm and specific」 | P2 | 否 | 冻结一份词表：运行/阶段/Agent 统一用「执行中」 |
| C12 | 状态判据在**同一文件内重复三份**（词表 + 类名 + 圆点色），新增状态需改三处，漏改即不一致 | `app.js:74-81` `STATUS_LABEL`、`375-381` `statusKind`、`383-389` `dotClass` | 红线 8「口径唯一」的精神（前端展示层） | P2 | 否 | 合并为一张 `{label, cls, dot}` 表 |
| C13 | 组件语义混载：同一 `chip` 同时表示「实现状态」「本次运行状态」「校验结论」 | `index.html:81` `<span class="chip ok">已接入</span>`（实现状态）；`index.html:135-136` 静态「已接入」；`index.html:129`「尚未准出」（校验）；`index.html:80`「待准备」 | B9 状态 | P2 | 否（真伪属实现审计；此处只判组件语义混载） | 把「实现状态」降为页脚一行说明，chip 只留给运行/校验态 |

---

## 6 占位与死链（B9/B10）

| 检查项 | 结果 | 证据 |
|---|---|---|
| `href="#"` | 1 处，**不是死链** | `index.html:506` `#awEmbedDirect`；`agent-window.js:241-257` 无可用地址时置 `href="#"` **且 `link.hidden=true`**，`agent-window.js:706-709` 点击 `preventDefault()` |
| 无 `href` 的 `<a>` | 1 处，**不是死链** | `index.html:139` `#s0Report` 初始无 href，`s0.js:129-131` 在显示前必定写入 `href` |
| `href=""` / `javascript:void` | **0 处** | `grep` 无命中 |
| 外部 URL | **0 处** | `loop/web/**` 内无 `http(s)://`（满足 §10 A8） |
| 返回入口 | **齐备** | `index.html:21` → `legacy.html`；`legacy.html:169` → `index.html` |
| 「当前页」指示 | **合格** | `.on` + `aria-selected`（`app.js:611-613`），§14「选中页有文字、背景和标记」 |
| `window.alert()` | **0 处** | 错误一律 inline（`#banners`/`role="alert"`），符合 B9 |

| id | 问题 | 证据 | 条款 | 级别 | 建议 |
|---|---|---|---|---|---|
| C14 | `↗` 一符三义（同标签页跳转 / 下载 / 新窗口），其中 3 处与「新窗口」约定相反 | `index.html:21`（`href="legacy.html"` 同标签页）、`139`（下载）、`506`（`target="_blank"`，唯一正确）；`app.js:1779`（`agent-name agent-open` 打开弹层）；`node-detail.js:790`、`1575`、`1740` | P2 | 只在新窗口/外部链接上用 `↗`；下载用 `↓`，打开弹层不加符号 |
| C15 | 两处阻塞式 `window.confirm()` 与本仓既有的页内二次确认模式不一致（后者已有 `#awStopConfirm` 先例且文案更完整） | `app.js:1337`（取消作业）、`s0.js:562`（删除副本）vs `index.html:524-528` + `agent-window.js:696-701` | P2 | 统一走页内确认；`s0.js` 的删除确认文案本身合格（已含「不可恢复 / 原始环境不受影响」） |

---

## 7 上线必需项（B10）逐项判定

> 本项目定位：**单机内网运营台**，只绑 `127.0.0.1`（`WEB_UI_SPEC.md:29`「不暴露到网络（只绑 `127.0.0.1` + SSH 隧道）」），无对外发布、无用户体系、无 SEO 需求。公网发布项按此判「不适用」，不判缺陷。

| 项 | 状态 | 判定与理由 |
|---|---|---|
| `<title>` | **有** | `index.html:6`「FPGA Flow · 仿真工作台」；`legacy.html:6`「闭环变更影响 · 闸门操作台」；`mockup.html:6`。**适用且满足**。但三页产品名不一致 → C16 |
| `lang` | **有** | 三页均 `<html lang="zh-CN">`（各第 2 行）。**适用且满足** |
| 语义 HTML | **部分** | `<main>/<aside>/<section>` 有，`<nav>` 0 → C5 |
| skip link | **有**（主界面） | `index.html:11`「跳到工作区」→ `#workspace`；可 Tab 聚焦、`focus` 时 `top:12px` 可见（`app.css:476-477`，实测 M5 第 17 步）。`legacy.html` 无 → C7 |
| 每页有回路 | **有** | 见 §6。`mockup.html` 无任何链接（`grep -c "href="` → 0）→ C18 |
| favicon | **无** | 三页均无 `<link rel="icon">`，`loop/web/` 无 `*.svg/*.ico`。**适用，应补**：本地一句 `<link rel="icon" href="data:image/svg+xml,…">` 不违反 §14 零外链 → C17 |
| alt text | **不适用** | 全站 `<img>` **0 处**（`grep -rn "<img"` 无命中），无内容图像；CSS 亦无 `url()` 背景图。装饰 glyph 已 `aria-hidden="true"`，图标按钮均有 `aria-label`（`index.html:416`、`547`、`618`、`634`） |
| 客户端表单校验 | **部分适用且满足** | 无 email 字段（无注册/联系表单）⇒ 邮箱格式校验不适用；必填项用原生 `required`（`index.html:91`）+ 提交前校验（`app.js:3272`（缺项提示由 `validateEntryDecisions` 驱动））+ 缺项就地提示（`app.js:3272`） |
| 自定义 404 | **不适用** | 无公网发布，无 SEO/品牌要求；`StaticFiles(html=True)` 对未命中路径返回 JSON 404（`loop/services/api.py:1381`），诚实、非假页面。运维误输 URL 场景可接受 |
| `<title>`/meta description/`og:image`/社交标签 | **不适用（og/description）** | 无抓取方、无分享场景，A7 整节不适用（见 §8）。`<title>` 已具备 |
| 隐私政策 / 条款链接 | **不适用** | 无用户体系、无注册、无数据外发（`WEB_UI_SPEC.md:29`）；`document.cookie` 0 处。仅 `localStorage` 存上次操作者字符串（`operator.js:4`）、`sessionStorage` 存预填（`s0.js:457`），均不出本机 |
| Cookie 同意 | **不适用** | 无 cookie、无第三方脚本、无埋点（`grep document.cookie` 0 处），不触发任何同意义务 |

| id | 问题 | 证据 | 条款 | 级别 | 建议 |
|---|---|---|---|---|---|
| C16 | 三页产品名不统一：主界面「FPGA Flow · 仿真工作台」、旧界面「闭环变更影响 · 闸门操作台」、样张「闭环变更影响 · 样张 v1」，而旧界面返回链接写「返回 **FPGA Flow** 工作台」 | `index.html:6`、`legacy.html:6`、`mockup.html:6`、`legacy.html:169` | B8 一致性 | P2 | 统一为「FPGA Flow · 仿真工作台」，旧页加「（旧版）」后缀 |
| C17 | 无 favicon | 三页均无；目录无图标资产 | B10「A branded favicon」 | P2 | inline data-URI SVG（保持零外链） |
| C18 | `mockup.html` 被 `StaticFiles` 对外提供（`GET /mockup.html` 可访问）但**无任何返回入口**，且用 `<div onclick>` 冒充按钮 | `loop/services/api.py:1379-1381`；`mockup.html:294`、`298-310`、`331-333` | B10 每页有回路、B9 键盘可达 | P2 | 二选一：移出 `WEB_DIR`（改为 `doc/` 存档），或补一行返回链接（§14 已声明「静态历史样张不重绘」，故不建议改其内部结构） |

---

## 8 owner 纪律：前端是否手抄服务端文案/枚举

**只报告可观察事实，不改判 owner。**

| 事实 | 证据 | 说明 |
|---|---|---|
| 状态词表在前端硬编码 6 个键 | `app.js:74-81` | 服务端新增状态时降级为原值显示（`app.js:372` `STATUS_LABEL[s] \|\| String(s)`），**不吞异常**，属可接受的展示层翻译 |
| 闸门"逐条处置"标签表在前端硬编码（含 `accept`/`rework`） | `node-detail.js:36-39` `DISPOSITION_LABELS` / `GATE_LABELS` | 是中文译名表，不是判据；但**值集合与 `kb_lib.GATE_DECISIONS` 重复**（`kb_lib.py:556-560`） |
| 闸门枚举兜底默认值写死 | `gate-session.js:104` `Array.isArray(allowed) ? allowed : ["confirmed", "ignored", "disputed"]` | 只有服务端未下发 `allowed` 时才用，是「无权威输入」的兜底；风险是服务端改枚举后前端仍按旧集合校验 |
| 决策判定口径前端也有实现 | `gate-session.js:84-96` | 注释自陈「口径与服务端 `gates.normalize_entry_decisions` 一致」——两份同判据实现，属红线 8 的关注面 |
| **反例（做对了）** | `app.js:398`「事件白名单以服务端为准：静态表只是首屏兜底，收到 health 后覆盖」；`app.js:1256`「空值不得说成"环境就绪"」；`node-detail.js:188`「状态原值逐字保留；中文释义只追加，不替换」 | 这三处是"投影不造判据"的正确示范，可作为 C3 之外的正面样板 |

---

## 9 装饰性英文眉题：B8「sentence case」的适用性

中文标题无大小写问题，但英文装饰层有：**14 处全大写英文**（`index.html:16` WORKSPACE、`36` WORKBENCH、`44` ATTENTION、`46` HISTORY、`64` SIMULATION WORKBENCH、`71` SIMULATION / ENVIRONMENT、`76` CONTROLLED DERIVATION / BASELINE / WORKSPACE、`142` BEFORE EXECUTION、`414` AGENT WORKSPACE、`541` NODE DETAIL、`614` BEFORE / AFTER、`630` REPORT），以及 2 处混合形（`index.html:80`「S0-a / 派生准备」、`81`「S0-b / 执行前检查」）。

| id | 问题 | 条款 | 级别 | 建议 |
|---|---|---|---|---|
| C19 | 若按 B8「sentence case for headings」判，14 处全大写均为违规；但它们承担的是「编号/分区标牌」而非标题，且中英双标是本仓既有做法（§14 未禁止） | B8 | P2 | **不必全改**：保留分区编号类（S0-a、S0-b、REPORT），把纯装饰的 3 处（`76` 的 CONTROLLED DERIVATION/BASELINE/WORKSPACE）随 C2 一起删除即可 |

---

## 10 N/A 条款清单（落地页专属，逐条给理由）

| 条款 | 判定 | 理由 |
|---|---|---|
| A1 Intake（offer / ICP / 转化定义 / 反对意见） | **N/A** | 运营台无「转化」概念：入口即已登录的单机操作员，不存在获客漏斗；§1 定义的三条主路径取代了 offer 定义 |
| A2 页面结构（hero / benefits / how it works / proof / FAQ / 最终 CTA） | **N/A** | 落地页叙事骨架。运营台结构由 §3–§5 规定（配置/运行/闸门三视图）。**唯一需要单独裁定的是 S0 首屏**——已按 C2 单列，判为错位 |
| A3 布局选择（A 经典 hero / B 长文 / C 最小转化 / D 对比页） | **N/A** | 四种布局都服务单一转化意图；运营台是持久工作区，布局由 §2 信息架构（两区）固定 |
| A4 转化规则（above the fold CTAs / message match / risk reversal） | **N/A** | 无广告来源、无风险逆转（无付费）、无"竞争 CTA"问题——每个视图只有一个主操作 |
| A5 文案（headline 公式 / CTA 动词 / benefit bullets） | **部分 N/A** | 「{Outcome} without {Pain}」「The {category} for {audience}」等**获客句式不适用**；但「CTA = 动词 + 得到什么」对按钮仍适用，实测合格：「派生并校验」「确认并启动」「提交闸门决策」「刷新执行结果」均为动词短语，无「Learn more / Submit」。**不同意的只有 S0 hero 标题的 slogan 化**（C2） |
| A6 构建顺序（hero→benefits→…） | **N/A** | 生成顺序条款，非成品判据 |
| A7 SEO / AEO（index 或 noindex、meta、FAQ schema、内链） | **N/A** | 不对外发布、无搜索引擎抓取方（`127.0.0.1` + SSH 隧道，`WEB_UI_SPEC.md:29`）；无 FAQ 内容可 schema 化 |
| A8 落地页陷阱（多 CTA、空话价值主张…) | **N/A（部分借用）** | 「Vague value prop」这一条对运营台同样成立，已体现为 C2/C19；其余（proof 埋底、移动端断行）不适用 |
| B5 hero 标题渐变（#FFF→#9B9B9B 等） | **N/A** | 唯一允许用渐变的地方是「hero 标题文字」，而运营台不该有 hero（C2）；且本仓 §14 规定背景为平色。实测 `measure.json` M8：`.s0-hero` `backgroundImage:"none"`，无渐变违规 |
| B11 tagline reveal 区（每页必备的大字标语滚动逐词点亮） | **N/A** | 该区是落地页的"第二个说服时刻"；运营台把同一句标语做成 250px hero 已经是负担（C2），再加一个滚动标语区只会进一步推迟主操作 |
| B10 公网发布项（og:image、社交标签、meta description、cookie consent、隐私政策、自定义 404） | **N/A** | 单机内网运营台、无对外发布、无用户体系、无 cookie/第三方脚本。详见 §7 逐项理由。**不因此判缺陷** |
| B2/B3/B4/B7（间距 / 圆角 / 边框与背景 / 动效曲线） | **不在本条范围** | 属视觉与动效条款，由并行审计负责；此处仅登记 `measure.json` M8/M9 的既有结论（单边边框 26 处、全 `ease` 默认曲线的元素 80 处）供交叉引用 |

---

## 11 不该改的一条（明确反对的改动）

**`index.html:506` 的 `href="#"` —— 不是死链，不要"修"。**

原文：`<a class="btn btn-sm" id="awEmbedDirect" href="#" target="_blank" rel="noopener" hidden>打开真实用例（实例窗口）↗</a>`

按 B9「No dead links. A button pointing at `#` is either linked or visually disabled」逐字对读，这里两条都满足：`agent-window.js:241-257` 在服务端未给可用地址时**同时**执行 `link.setAttribute("href","#")` + `link.hidden = true`（视觉上不存在），`agent-window.js:706-709` 再对 `href === "#"` 的点击 `preventDefault()`，且 `title` 写明「服务端未提供可用实例地址」。把它改成 `href=""`、改成 `disabled` 按钮、或删掉这个 `<a>` 都会破坏 `setEntry()` 的既有两态模型；这是一次纯粹的外观式"修死链"，收益为零、回归面非零。

**同族「已合格、勿动」清单**（审计中曾疑似问题、验证后确认合格）：`#s0Report` 无初始 `href`（`s0.js:129-131` 必先写 href 再显示）；四段折叠头用 `<button aria-expanded>` + CSS 旋转 `▸`（`app.js:1629-1631`、`app.css:169`）；tablist 的 roving tabindex（`app.js:614` 是有配套方向键的，符合 APG）；零外部依赖（`loop/web/**` 无 `http(s)://`）；无 `<img>` 故 alt 条款不适用。

---

## 12 最小改动集（按性价比排序）

1. **C2**：删除 `index.html:70-77` 的 `.s0-hero`，换成一句用途 + 主操作；同步删 `app.css:571-592` 的 hero 样式（约 22 行）。→ 1440 下主操作进首屏。
2. **C3**：把 3 处 `GATE-1` 改为不含未定身份的表述（`index.html:104`、`142`、`s0.js:77`）。
3. **C1**：新增一份本地自绘 SVG sprite（16 个 16×16 符号，落点由实现时定）+ `<use>` 替换 glyph；保留 `aria-hidden`，不引入 CDN。
4. **C6**：`app.css:479` 一行改 `:focus-visible` + 可见 outline。
5. **C11/C12**：合并三套状态词与三份判据为一张表。
6. 其余 P2 按表逐条处理，**不改** `mockup.html` 内部（§14 已声明样张不重绘）。

---

**审计边界声明**：本轮只读代码与受控夹具测量；未启动真实服务、未运行 Playwright、未验证真实运行时的动态文案（如 SSE 断线提示的实际取值）。所有 `y=`/高度数字来自 `.ui-audit/measure.json` M6，不来自截图目测。本轮**未修复任何文件**，只新增本报告。
