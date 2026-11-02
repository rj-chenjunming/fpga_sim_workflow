# A · UI 视觉令牌与 CSS 审计（按 ai-design-skills Part B）

> **归档副本（2026-10-30）**：原文件在审计工作区 `.ui-audit/A-visual.md`（未入库临时件）；归档时更名，内容除本行与下列唯一修改外未改。范围：§1–§5 与附录；行号指向仓库文件。
> 原始 md5 记录见 [`../../evidence/UI_DESIGN_AUDIT_20261030/README.md`](../../evidence/UI_DESIGN_AUDIT_20261030/README.md)。

- **对象**：`loop/web/tokens.css`（17 行）、`loop/web/app.css`（1213 行）、`loop/web/legacy.css`（75 行）；`loop/web/mockup.html`（889 行）是静态历史样张，**只作对照、不计实现**。
- **视觉权威**：`doc/spec/WEB_UI_SPEC.md` §14（第 820–844 行）。**技能**：`~/.dsh/skills/ai-design-skills/SKILL.md`（Part B 见 146–353 行，Part A 见 22–143 行）。
- **方式**：只读审计；`doc/**`、`loop/**` 未改动；本轮**不修复**，只出差距。所有数字来自文末附录命令输出，未手算。
- **适用边界**：本项目是内网单机运营台，不是落地页。`B1/B2/B3/B4/B7/B9` 属可迁移的视觉规则；`Part A`、`B5`、`B11`、`B6`、`B8`、`B10` 是落地页结构/内容条款，见 §4。
- **严重度**：`P0` = 违反本项目视觉规格明文且规模性；`P1` = 违反技能硬条款 / 可观察工程缺陷；`P2` = 打磨或名义问题。

## 1 量化总览

| 维度 | 声明数 | 不同取值 | 阶外（占比） | 技能阶梯 | 主要偏离值 |
|---|---|---|---|---|---|
| 字号 | 350 | 30 | **240（68.6%）** | 12/14/16/18/20/24/30/36/48 | 11px×53、13px×39、11.5px×37、12.5px×26、10px×24 |
| 间距（padding/margin/gap） | 748 | 36 | **485（64.8%）** | 0/2/4/8/12/16/24/32/40/48/64/80/96 | 10px×118、6px×60、14px×39、9px×36、18px×33 |
| 圆角 | 107 | 13 | **62（57.9%）** | 2/4/6/8/12/16/24 | 7px×27、9px×16、10px×6、5px×4、14px×2 |
| 颜色 hex | 427 | tokens 内 25 / **tokens 外 263** | 401 次在 tokens.css 之外（93.9%） | 仅用共享令牌 | #fff×36、#f3d19e×10、#f5c6c6×9 |
| 字重 | 83 | 10 | 640/650/550/450/750 非标准档 | ≤600（semibold）或 700 | 650×12、550×6、640×3、750×1 |
| 动效 | 7 条 transition + 2 组 @keyframes | 曲线 0 处显式声明 | **0 处 base curve** | `cubic-bezier(0.22,1,0.36,1)` / 500ms | 150ms×5 组、默认 ease、`linear` 1s |

## 2 差距清单

| id | 问题 | 证据（file:line + 具体值） | 技能条款 | 严重度 | 与项目规格的关系 | 建议（方向/目标值） |
|---|---|---|---|---|---|---|
| A-01 | 配色令牌形同虚设：tokens.css 之外有 401 次 hex、263 个不同值，其中 239 个 6 位色**没有一个**等于任何 token 值 | `app.css:545` `background:#f1f6f2`；`app.css:701` `border-color:#e0e8db`；`app.css:206` `background:#2457d6`；`app.css+legacy.css` 6 位 hex 出现 335 次 / 239 distinct，与 tokens 重合 **0**；另有 8 位 alpha 30 次、3 位简写 36 次（全为 `#fff`）。102 个离 token 任一分量差 ≤10（如 `#c7d4c8` vs `--line-strong:#c7d4cc`） | B4；Quick checklist「shared tokens」 | **P0** | **冲突：§14:826 明文「共享配色令牌」** | 收敛为语义层（surface / line / 语义色各 1–2 档）；目标 tokens 外不同值 <20；`#f1f6f2/#f1f4ee/#f1f5ef/#f2f4f7` 这类近白先合并 |
| A-02 | 字号阶梯未落地：30 个不同字号，68.6% 不在 Tailwind 阶梯上 | 350 处声明 240 处阶外；桌面路径（非 @media 行）阶外 ≥12px 共 89 处：13px×39、12.5px×26、15px×6、17px×4、21px×3、29px×3、22px×2、27px×1、31px×1、34px×1、65px×1，另有 13.5/15.5/19px；例 `app.css:535` `h1{font-size:27px}`、`app.css:574` `font-size:29px`、`app.css:340` `font-size:65px` | B1 Type scale（172–192 行） | **P0** | **冲突：§14:825 明文「稳定字号阶梯」** | 吸附到 12/14/16/20/24/30/36；27→24、29→30、17/19→18、21/22→20、65→48（或作为装饰图形不入字号体系） |
| A-03 | 桌面路径上 126 处字号 <12px，最小到 6px | `<12px` 共 146 处，其中 **126 处不在 @media 行**；≤9px 共 13 处（桌面）：`app.css:341` 7px、`app.css:580` 8px、`app.css:393/421/509/537/573/585/590/591/625/782/994` 9px；10–11.5px 113 处（11px×48、11.5px×37、10px×18、10.5px×10） | B1（可用性） | P1 | 部分冲突：§14:825 允许「标签与图示注释更紧凑」，但 `app.css:309` `.foot-note{11.5px}`、`app.css:695` `.agent-role{11px}` 属**说明文字**，低于「说明文字 12px」 | 说明文字 ≥12px；7–9px 只留给纯装饰字形（`◇`、`›`）；`app.css:398` 的 6px（在 @media 内、不属验收视口）建议删除 |
| A-04 | 字体令牌首选技能禁用的 **Inter** | `tokens.css:15` `--font-sans:Inter,-apple-system,…`；`app.css:472` `body{font-family:var(--font-sans)}` 覆盖 `app.css:9` 的系统栈；全仓 `@font-face` 0 处、`url(` 0 处、HTML 外部引用 0 处 → **Inter 不会下载**，仅本机已装时生效，否则回退 `-apple-system / Segoe UI / Noto Sans SC` | B1 Fonts（154–160 行，Never use Inter） | P2 | 规格未覆盖；§14:842「无外部字体」已满足 | 从 `--font-sans` 删除 Inter，改为纯平台系统栈并在 token 注释里登记「本项目无本地字体资产」；若要保留品牌字形，只能选技能允许族（Geist/Manrope）且**本地内置** |
| A-05 | 字重越界与非标准档 | `app.css:481` `font-weight:750`（>bold 700）；640×3（`109/160/208`）、650×12、550×6、450×2 均非 CSS 标准档；700×6、300×2 | B1（162 行：Never ultra bold，cap at semibold or bold） | P2 | 规格未覆盖 | 收到 400/500/600/700 四档；750→700，640/650→600，550→600，450→400 |
| A-06 | 按钮字号/字重与 B1 Button type 差一档 | 主按钮 `app.css:544` `.btn{font-size:13px;font-weight:550}`、次按钮 `app.css:549` `.btn-sm{font-size:12px}`；B1 要求 16px semibold / 14px semibold | B1 Button type（194–197 行） | P2 | **冲突：§14:825 明文「主要表单 13–14px」** | 维持 §14（技能 Scope:16 声明 user/prompt 冲突时用户优先），在 §14 登记该条为「规格优先的显式豁免」，并把 550 提到 600 |
| A-07 | 按钮内边距不符 B2 的 8/12 | `app.css:41` `.btn{padding:0 14px}` + `app.css:544` `height:38px`（垂直内边距 0，靠固定高度）；`app.css:50` `.btn-sm{padding:0 10px}`；反例 `legacy.css:53` 是 `padding:8px 13px` | B2（219 行：主按钮 8px 垂直 / 12px 水平） | P2 | 规格未覆盖 | 垂直 8px、水平 12px（或保留 38px 高度但注明 8+22+8 的来源），`btn-sm` 用 8/12 次级档 |
| A-08 | 间距体系 64.8% 不在 B2 表 | 748 处 padding/margin/gap 声明中 485 处阶外，36 个取值；样例 `app.css:28` `padding:0 10px`、`app.css:76` `padding:10px 14px`、`app.css:74` `gap:10px`、`app.css:227` `gap:10px`、`app.css:247` `padding-left:18px`；偏离值含 1/3/5/6/7/9/10/11/13/14/15/17/18/19/20/22/25/26/28/29/30/34/36/38/46/65px 与 1 处 −5px（`app.css:340` 字距） | B2（199–219 行） | P1 | 规格未覆盖（§14 只说「稳定」，未给表） | 收敛到 4/8/12/16/24/32；10→8/12 二分，14→16，18→16，6→4/8 |
| A-09 | 圆角 57.9% 不在 B3 表，且几乎不用 `--radius` | 107 处：仅 45 处在 {2,4,6,8,12,16,24}；7px×27、9px×16、10px×6、5px×4、3px×2、11px×1、14px×2；字面值 118 处 vs `var(--radius)` **3 处**（`app.css:129/234/556`，token 为 `tokens.css:14` `--radius:12px`） | B3（221–233 行） | P1 | 规格未覆盖 | 收 6/8/12/16；`app.css:725/777` 的 14px→16；`app.css:68/69/594/719/1134` 的 9/10px→8/12；`999px`（28/163/164/1129）按 Tailwind `rounded-full` 可判合规，仅登记 |
| A-10 | 嵌套半径未按公式 | `app.css:68` `.seg{padding:3px;border-radius:9px}` 内 `app.css:69` `.seg button{border-radius:7px}`：间隙 3px <32px，公式 9−3=**6**，实为 7 | B3 Nested radius formula（225–233 行） | P2 | 规格未覆盖 | 内层改 6px；其余「外 12 内 8」（`.card` → `.diff-item` 类）已近似满足，无需动 |
| A-11 | 单侧边框当作卡片强调色（5 处声明 / 4 个组件） | `app.css:315` `.diff-item{border:1px…;border-left:3px solid var(--line-strong)}`；`app.css:804` `.nd-summary`；`app.css:834–835` `.nd-key-row`；`app.css:863/864` `.diff-pane.before/.after`；等效视觉：`app.css:712` `.option.on{box-shadow:inset 3px 0 #ba914b}`。旧界面同病：`legacy.html:85/90/154` 内联 `border-left:5px/4px`（`legacy.css:38/64` 只覆盖颜色） | B4（237 行：Never apply a border to only one side of a card） | P2 | 规格未覆盖 | 语义色改为「全边框 + 左侧 4px 语义色块（伪元素/inset 阴影）」；或直接全边框无强调边 |
| A-12 | 唯一背景渐变在单选框选中点；无背景渐变滥用 | 全仓 CSS 渐变仅 1 处：`app.css:242` `.option.on .radio{background:radial-gradient(circle,#b45309 0 40%,#fff 42% 100%)}`；对照 `mockup.html:32` 有 `linear-gradient(135deg,#2457d6,#6d28d9)` 但**未实现**；`app.css:571` 甚至显式写 `background-image:none` | B4（238 行：Never use gradients in backgrounds；B5:253 唯一例外是 hero **文字**渐变） | P2 | 规格未覆盖 | 选中点用「border + 实心 background 两层」实现，去渐变；同时在 §14 登记「本项目不使用 B5 的文字渐变例外」 |
| A-13 | 动效无 B7 基准曲线，且存在 <200ms 与 `linear` | 7 条 transition 中 **0 条**声明 timing-function（`app.css:164/168/306/403/544/551`、`legacy.css` 不含 transition）→ 浏览器默认 `ease`；时长 150ms×5 组（`168/403/544/551/…`）、200ms（`306`）、300ms（`164`）；`app.css:222` `animation:spin 1s linear infinite`；`cubic-bezier` 全仓 0 处 | B7（269–271 行） | P1 | 规格未覆盖（§14 无动效条款） | 新增 `--ease-out:cubic-bezier(0.22,1,0.36,1)` 统一引用；hover 色变 ≥200ms（现 150ms）；spinner 若保留 `linear` 需在 §14 显式登记例外（技能原文未给旋转例外） |
| A-14 | 动画 `width`（技能明令禁止） | `app.css:164` `.stage-bar i{…transition:width .3s}`，由进度值改 `style.width` | B7（273 行：Never animate top/left/width/height） | P1 | 规格未覆盖 | 改 `transform:scaleX(var(--p));transform-origin:left`，配 base curve + 500ms |
| A-15 | 全站无 `:active` 状态 | `app.css` `:active` **0 处**、`legacy.css` **0 处**、HTML 内联样式 **0 处**；对比 `:hover` 19/5、`:focus-visible` 4/3、`:disabled` 6/3 | B9（312 行：Active = scale(0.98) 或 translateY(1px)） | P1 | 规格未覆盖 | 至少 `.btn`/`.option`/`.run-item`/`.snode` 补 `:active{transform:translateY(1px)}` |
| A-16 | loading 用圆形 spinner（B9 要求骨架屏） | `app.css:221–223` `.spinner{10px;border:2px;border-radius:50%;animation:spin 1s linear infinite}`；使用点 `app.js:1282`、`app.js:1805`；骨架类 0 处（`skeleton` grep 0 命中） | B9（314 行：skeleton loaders shaped like the real layout, not circular spinners） | P2 | 规格未覆盖 | 运行中改用与真实行同形的骨架行；圆点仅保留为「状态指示」并换名 |
| A-17 | 可点元素缺 hover/焦点对 | 可点但无 hover 规则：`app.css:1129` `.ev-chip{cursor:pointer}`、`app.css:69` `.seg button`、`app.css:218` `.linkbtn`；有 hover 的对照：`app.css:237` `.option:hover`、`app.css:522` `.run-item:hover`、`app.css:153` `.stage-head:hover`。焦点环已有：`app.css:478` `:where(button,a,summary):focus-visible`、`240/679/771`、`legacy.css:69` | B9（309–318 行） | P2 | 规格未覆盖 | 三个类各补一条 hover（背景/边框位移），复用同一 token |
| A-18 | 「先骨架后覆盖」两段式定义，是令牌漂移的结构成因 | `app.css` 顶层规则 958 条 / 不同简单选择器 784 个，**183 个被 ≥2 条规则定义**；第 1–467 行 353 条（342 个选择器）与第 468–1213 行 605 条（615 个选择器）重叠 **173 个 = 50.6%**；例 `body` 7/8/472、`.btn` 41/544、`.card` 89/556、`.chip` 120/555、`.input` 111/551、`.mono` 11/473、`.avatar` 204/690、`.ev-row` 270/717 | B（148 行：每个视觉值都要经规则解析） | P1 | 规格未覆盖 | 先合并同名块（同文件内合并后再抽 token），否则任何令牌化都会立刻被后半段覆盖 |
| A-19 | 令牌外蓝色 `#2457d6` 是**死声明** | `app.css:206` `.a1{background:#2457d6}`；`app.js:1776` 生成的 className 是 `"avatar a1"` → 同特异性后置 `app.css:690` `.avatar{…background:#eaf3e8}` 覆盖它，运行时不出现该蓝；同类残留：`app.css:331` `background-size:32px 32px` 无 `background-image`（`571` 又写 `none`） | B4 / 令牌纪律 | P2 | 规格未覆盖 | 删除 `.a1` 的 background（或改为令牌色）；清理 331 的无效声明 |
| A-20 | 等宽字体用于「序号/图注」，超出 §14 允许的四类用途 | 17 处 `monospace` 引用（`font-family` 声明 15 条）；其中 `app.css:345` `.phase-index`、`app.css:377` `.s0-checks li>span`、`app.css:1184` `.s0-flow li>span` 是**序号**，`app.css:585` `.diagram-flow b` 是图注 | B1（160 行允许 mono 用于 code/data/数值） | P2 | **冲突：§14:825 明文「等宽字体仅用于路径、身份、计数与日志」** | 序号/图注改回正文字体；或把 §14 该句扩写为「路径/身份/计数/日志/序号」，二者择一，不留口径分叉 |
| A-21 | 无 `text-wrap` 断行控制 | `text-wrap` 全仓 **0 处**（`balance`/`pretty` 均无）；对应 `app.css:535` `.page-head h1`、`app.css:558` `.card-head h2` 均无 | B1 Copy rules（168 行） | P2 | 规格未覆盖 | 标题 `text-wrap:balance`、正文/说明 `pretty`（两行声明即可） |

## 3 已合规项（避免只报坏消息，均为实测反证）

| 项 | 证据 |
|---|---|
| 无斜体 | `italic`/`oblique` 全仓 0 处 |
| 无 ultra-bold 900/800 | 最重为 `app.css:481` 750，900/800 各 0 处 |
| `prefers-reduced-motion` 已覆盖 | `app.css:763`、`legacy.css:75`（均为 `animation:none!important;transition:none!important`；技能要求「换成纯 opacity」，此处为更强降级，可接受，但未保留 opacity 过渡） |
| 键盘焦点环 | `app.css:478`、`240`（单选内 input→radio）、`679`、`771`、`legacy.css:69`，共 7 处 |
| 空态 | `app.css:99/100`、`app.css:269` `.ev-list:empty:after`、`app.css:568` `.empty:before{◇}`、`app.css:425` `.aw-empty`、`app.css:825` `.nd-empty` |
| 错误态（内联、非 alert） | `app.css:78/83` `.banner.bad/.alert.bad`、`app.css:819` `.nd-failure`、`app.css:245` `.gate-error`、`app.css:1204` `.s0-switch-msg-bad`；JS 未用 `window.alert` |
| 背景基本扁平 | 全仓 CSS 渐变仅 A-12 的 1 处 |
| 无外部字体/CDN/图标库 | `@font-face` 0、`url(` 0、HTML `http(s)://` 引用 0，符合 §14:842 |

## 4 适用边界与 N/A（引用落地页条款时必须带这句）

| 技能条款 | 本项目判定 | 理由 |
|---|---|---|
| Part A1–A8（intake / 页面结构 / 布局选型 / 转化 / 文案 / 构建顺序 / SEO / 陷阱） | **N/A** | 运营台无「一个 offer、一个 CTA」的转化结构；`A5` 文案规则中「正文不许连字符、句子式大小写」属文本层，不由 CSS 判定 |
| B5 Hero（680px、标题渐变） | **N/A** | 无营销 hero；`app.css:571` 的 `.s0-hero` 是表单区头图容器，不承担 hero 语义。技能唯一的文字渐变例外在本项目**不使用** |
| B6 图标（Phosphor/Solar/Iconamoon） | **部分 N/A** | 实现是字符/Unicode 装饰（`◇`、`✓`、`▸`、`·`）与 `::before`，无图标库；技能只禁 Material Icons，本项目已满足「不用 Material」 |
| B11 Tagline reveal（强制） | **N/A** | 落地页专属的滚动逐词揭示区；运营台无此版面。若照搬会违反 §14:841「不改变交互不变量」 |
| B8 内容真实性 / B10 上线清单（404、法务链接、cookie、og:image） | **N/A（本仓库）** | 内网单机工具，无公网发布、无 cookie；`B10` 中「skip to content」与「语义 HTML」已实现（`index.html` + `app.css:476` `.skip-link`） |
| B4 Dark mode 色板（`#000/#181818/…`） | **N/A** | `tokens.css:3` `color-scheme:light`，唯一深色是侧栏 `tokens.css:12` `--rail:#192e28`（浅色主题里的深色导航，不是 dark mode）；不要按 B4 的深色表改它 |

## 5 三项最值得改（按性价比排序）

1. **A-18 → A-01 的顺序**：先在 `app.css` 内合并 183 个重复选择器（`body/.btn/.card/.chip/.input` 起手），再把颜色收进 tokens；反过来做会被第 468 行之后的覆盖段立刻冲掉。判据：tokens 外不同 hex <20，且 `grep -c 'var(--'` 在 app.css 上升。
2. **A-02/A-03 字号一次性对齐**：把 240 处阶外值吸附到 12/14/16/20/24/30/36，桌面路径 <12px 从 126 处降到 0（装饰字形除外）。这一条同时消掉 §14:825 的两处偏离。
3. **A-13/A-14 动效**：加 `--ease-out` 一处 token + 把 `.stage-bar i` 从 `width` 改 `scaleX`，再补 A-15 的 `:active`。四面小改，覆盖率提升最大。

## 6 校准说明（哪条最可能被高估）

**A-04（Inter）**：本仓无 `@font-face`、无外部请求，Inter **不会被下载**；目标机若没装 Inter，`--font-sans` 直接落到 `-apple-system/Segoe UI/Noto Sans SC`，渲染与"没有 Inter"完全一致。因此它是**名义违规 + 跨机渲染不确定**（装了 Inter 的机器会静默换字形），不是可见缺陷，按 P2 处理即可，不要当视觉返工项。次高估的是 **A-09 的 `999px`**：那是 Tailwind `rounded-full` 的等价写法，按 B3 原文可判合规。

## 附录 证据命令与输出（工作目录 `loop/web/`）

**E1 文件规模**
```
$ wc -l tokens.css app.css legacy.css mockup.html
   17 tokens.css
 1213 app.css
   75 legacy.css
  889 mockup.html
```

**E2 字号枚举（含 `font:` 简写；`SCALE={12,14,16,18,20,24,30,36,48,60,72,96,128}`；`desktop` = 该行不以 `@media` 开头）**
```
$ python3 -c "...font-size / font: 正则枚举 + 阶外统计..."
decls=350 distinct=30 off-scale=240(68.6%)
<12px=146 desktop=126 <=9px desktop=13
top off values: [(11.0,53),(13.0,39),(11.5,37),(12.5,26),(10.0,24),(9.0,14),(10.5,10),(15.0,7)]
per-file: app.css 337 处 / 233 阶外(69.1%)；legacy.css 13 处 / 7 阶外(53.8%)；tokens.css 0 处
分布(全部 30 档): 6×1 7×2 8×4 9×14 9.5×1 10×24 10.5×10 11×53 11.5×37 12×88 12.5×26 13×39 13.5×1
14×12 15×7 15.5×1 16×4 17×4 18×2 19×1 20×3 21×3 22×2 23×1 24×1 27×3 29×3 31×1 34×1 65×1
```

**E3 间距分布（`padding|margin|gap|*-top|*-bottom|*-left|*-right|row-gap|column-gap` 中的 px 值；`SPACE={0,2,4,8,12,16,24,32,40,48,64,80,96}`）**
```
decls=748 distinct=36 off=485(64.8%)
top off values: [(10.0,118),(6.0,60),(14.0,39),(9.0,36),(18.0,33),(7.0,26)]
per-file: app.css 711 处 / 461 阶外(64.8%)；legacy.css 37 处 / 24 阶外(64.9%)
```

**E4 圆角枚举（`border-radius` 中的 px 值；`RAD={2,4,6,8,12,16,24}`）**
```
decls=107 distinct=13 on=45(42.1%) off=62(57.9%)
distribution: [(3.0,2),(4.0,3),(5.0,4),(6.0,10),(7.0,27),(8.0,27),(9.0,16),(10.0,6),(11.0,1),(12.0,4),(14.0,2),(16.0,1),(999.0,4)]
$ grep -o 'border-radius:[^;}]*' app.css legacy.css | wc -l   → 118
$ grep -n 'var(--radius)' app.css legacy.css  → app.css:129 / app.css:234 / app.css:556（仅 3 处）
```

**E5 颜色普查（`#rgb|#rgba|#rrggbb|#rrggbbaa`）**
```
tokens.css: 总出现=26 (#rgb×1, #rrggbb×23, #rrggbbaa×2)
app.css:    总出现=343 (#rgb×29, #rrggbb×287, #rrggbbaa×27)
legacy.css: 总出现=58 (#rgb×7, #rrggbb×48, #rrggbbaa×3)
三文件合计 427 {6位:358, 3位:37, 8位:32}；tokens 之外 = 401（93.9%）
app+legacy 6 位 hex：出现 335 次 / distinct 239 / 与 tokens 值重合 0
app+legacy 3 位简写 36 次，全为 #fff；8 位 alpha 30 次
top 6位: [('#f3d19e',10),('#f5c6c6',9),('#7d6339',8),('#fcfdfb',7),('#f6f9f4',7),('#fffaf1',7)]
离 token 任一分量差 ≤10 的阶外色：102 个 distinct（如 #c7d4c8 vs token #c7d4cc）
```

**E6 选择器重复（大括号深度解析，注释替换为空格保行号）**
```
顶层规则=958  L1-467=353  L468+=605
distinct简单选择器=784  被>=2条规则定义=183
L1-467选择器=342  其中L468+再定义=173 (50.6%)
  .btn [41, 544]  .card [89, 556]  .chip [120, 555]  .input [111, 551]
  body [7, 8, 472]  .mono [11, 473]  .avatar [204, 690]  .option [235, 709]  .ev-row [270, 717]
```

**E7 动效**
```
$ grep -n 'transition' app.css        → 7 条：164(transition:width .3s) 168(transform .15s) 306(.2s)
                                         403(border-color/box-shadow .15s) 544(background/border-color/box-shadow .15s)
                                         551(border-color/box-shadow .15s)
$ grep -o 'cubic-bezier' app.css legacy.css | wc -l   → 0
$ grep -n 'animation|@keyframes' app.css → 222(animation:spin 1s linear infinite) 223(@keyframes spin)
                                           225(animation:pulse 1.6s infinite) 226(@keyframes pulse)
$ grep -n 'prefers-reduced-motion' app.css legacy.css → app.css:763  legacy.css:75
```

**E8 状态集**
```
$ for s in :hover :active :focus-visible :disabled; do grep -o $s …; done
:hover          app=19 legacy=5
:active         app=0  legacy=0      ← HTML 内联样式同为 0（grep -rn ':active' *.css *.html 无命中）
:focus-visible  app=4  legacy=3
:disabled       app=6  legacy=3
$ grep -n 'skeleton' app.css legacy.css index.html app.js → 0 命中
$ grep -n 'text-wrap' app.css legacy.css → 0 命中
$ grep -n 'italic|oblique' … → 0 命中
$ grep -ho 'font-weight:[0-9]*' … | sort -n | uniq -c
   2 300 | 8 400 | 2 450 | 7 500 | 6 550 | 36 600 | 3 640 | 12 650 | 6 700 | 1 750   （合计 83）
$ grep -n 'font-family|monospace' app.css → font-family 15 条；'monospace' 出现 17 次
$ grep -n '@font-face|url(' app.css tokens.css legacy.css → 无命中
$ grep -n 'https\?://' index.html legacy.html → 无命中
```

**E9 引用到的相邻文件（非审计目标，仅取值来源）**
```
app.js:49  {… avatar:"析", cls:"a1" }        app.js:1776  h("div","avatar "+(def.cls||"a6"), …)
app.js:1282 / 1805  h("span","spinner")      app.js:1284 / 2198  h("span","pulse")
legacy.html:12  font-family:"Source Han Sans SC",…,Roboto,sans-serif（被 legacy.css:2 覆盖，实际不生效）
legacy.html:85/90/154  border-left:5px/4px（旧界面单侧边框的宽度来源）
mockup.html:32  linear-gradient(135deg,#2457d6,#6d28d9)（静态样张，未实现）
```
