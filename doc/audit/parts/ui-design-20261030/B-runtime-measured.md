# B · 运行时实测 UI（Chromium 实测，非读 CSS 推断）

> **归档副本（2026-10-30）**：原文件在审计工作区 `.ui-audit/B-runtime.md`（未入库临时件）；归档时更名，内容除本行与下列唯一修改外未改。范围：§1–§6；数字来自 measure.json。
> 原始 md5 记录见 [`../../evidence/UI_DESIGN_AUDIT_20261030/README.md`](../../evidence/UI_DESIGN_AUDIT_20261030/README.md)。

> **数据来源纪律**：本轮所有数字来自 `.ui-audit/measure.py` 在真实 Chromium（156.0.8078.4）里的
> `getComputedStyle` / `boundingBox` / CDP `CSS.getPlatformFontsForNode` 读数。
> 页面由 `loop/web/` 静态服务和 **受控 API 夹具**（复刻 `tests/browser/test_web_layout.py::populate` 字段）渲染，
> **不是真实运行数据**：夹具里的「未记录」「—」等文案只作状态/文案观察，**不作为产品缺陷**。
> 视口按 §14 写死：1280×720 / 1440×900 / 1920×1080。移动端是 §14 明确的非目标，本报告不涉及。
> 产物：`.ui-audit/measure.json`（脚本生成的全部原始数字）、`.ui-audit/shots-b/`（20 张本轮截图；原文写 17，归档时按 `ls shots-b/*.png | wc -l` 更正）。

## 0 方法与口径

| 项 | 取值 |
|---|---|
| 浏览器 | Chromium 156.0.8078.4（Playwright 自带，`PLAYWRIGHT_BROWSERS_PATH=.pw-browsers`） |
| 页面 | `loop/web/index.html` 由临时 `ThreadingHTTPServer` 提供（只读 `loop/web/**`），无真实后端 |
| API | 全部 `**/api/**` 被 `page.route` 拦截返回受控夹具；`/stream` 显式 404 让前端降级为轮询（与既有测试一致） |
| 时钟 | `page.clock.install()` 冻结定时器，避免轮询重渲染导致元素 detach（与 `test_run_sessions.py::ui` 同法） |
| 缺陷判定 | 仅以 `getComputedStyle` / `getBoundingClientRect` / 平台字体实测为准；测不到写「未实测 + 原因」 |
| 对比度 | WCAG 2.1 相对亮度公式实算，前景/背景取真实 computed 色值；向上合成半透明背景，遇渐变标记不可判定 |
| 透明度 | `opacity<1`（如 `.btn:disabled{opacity:.5}`）按「层 50% 合成到背景」计入有效前景/背景 |
| 一致性 | 脚本末行 `pageErrors: [] posts: []` 表示夹具下无 JS 异常、无写请求（本次为空） |

## 1 结论摘要

| id | 问题 | 实测证据（selector + 数值 + 视口） | 技能条款 | 严重度 | 建议方向 |
|---|---|---|---|---|---|
| B-01 | 声明的主字体 **Inter 并未本地化**（无 @font-face 文件），拉丁文本实际回退到 Liberation Sans | `getComputedStyle(body).fontFamily` = `Inter, -apple-system, …, sans-serif`；`[...document.fonts]` = `[]`；CDP 平台字体：`.page-edition` → **Liberation Sans**(20 glyph)，`#pageTitle`/`.s0-hero h2` → **Noto Sans CJK SC**，`#s0Rtl`/`#hdrAddr` → Liberation Mono；宽度探针 40px 字符串 `Inter`=643.27 == `"NoSuchFamilyXYZ"`=643.27（`siteStack`=673.67 == Liberation Sans=673.67） | B1「Use Geist/Manrope… **Never use Inter**」；§14「所有字体…本地化」 | P1 | 本地自带一个允许字体的 woff2 并删掉本机不存在的族声明；验收口径：`platformFonts` 出现该族名且 `document.fonts` 非空 |
| B-02 | 唯一主操作「派生并校验」在三档验收视口**全部不在首屏** | `#s0Prepare` y=**1098.1**（1280×720）、**1078.3**（1440×900）、**1066.5**（1920×1080），bottom=1140.1/1120.3/1108.5，`visibleRatio`=0/0/0.32；`scrollHeight`=3134/3110/3096 | A2「Primary CTA above the fold」、A4「Make the next step obvious」 | P1 | 首屏内出现主操作：压缩 `s0-hero` 与 `s0-phases` 的竖向预算，或把提交行并入页标题区；目标 y+h ≤ 视口高 |
| B-03 | 闸门视图的**材料/操作两栏整体在首屏外**（三档视口一致） | `#gateMaterial` y=**909.6**(1280×720)/**913.6**(1440×900)/**885.5**(1920×1080)，`visibleRatio`=0/0/**0.27**；`#gatePanel` 同 y，1920 下 0.42；`.diff-item` y=1292.5/1296.5/1268.3 | A2 同族（关键操作置于首屏）；§5 未规定首屏 | P1 | 压缩 `#gateHead`+阶段条高度或让两栏上移；目标两栏顶边 < 视口高 |
| B-04 | `--faint`/低饱和小字在实背景下低于 4.5:1（WCAG 1.4.3），S0 视图 28/209、monitor 33/238 | 见 §1b 完整清单：`.page-edition` **3.31**、`.diagram-label` **3.39**、`.diagram-caption` **3.27**、`.section-index` **3.89**、`.foot-note`（= `--faint #71827b` on `#fff`）**4.05**、`.stage-chev` **4.05**；最低 **1.53** | 技能无对比度条款（最接近 B1 可读性）+ WCAG 2.1 1.4.3 | P2 | 把上表前景色压到 4.5:1 以上（浅绿底上 ≈ `#5c6f58`，浅灰底上 ≈ `#5f7168`），或改用 `--text` 的低一档派生色 |
| B-05 | **8–11.5px** 小字族存在，B1 的 12px 下限被突破 | 209 个文本节点/1967 字符中：**8px×1、9px×10、10px×19、10.5px×3、11px×46、11.5px×2** ⇒ 81 元素（**38.8%**）、582 字符（**29.6%**）；样例 `.diagram-label` 8px、`#btnS0 small` 10px、`#sidebar .rail-label` 11px | B1「吸附到下面一档」+ 12px 下限 | P2 | ⚠️ 与 §14「说明文字 12px、标签与图示注释**允许更紧凑**」部分冲突：若保留紧凑档，建议把 8/9px 抬到 11px 并在 §14 写明下限；否则统一回 12px |
| B-06 | 字号共 **19 种**，多数不在 Tailwind 阶梯 | 19 档：8/9/10/10.5/11/11.5/12/12.5/**13**/14/15/16/17/19/20/21/22/**27**/**29**；落在阶梯上的只有 12/14/16/20 | B1 type scale | P2 | ⚠️ 与 §14「主要正文 13–14px」冲突：13px 作为 §14 授权例外保留，其余收敛到 {12,14,16,20,24,30}；15/17/19/21/22/27/29 无规格依据 |
| B-07 | 字号与行高**不成对**（B1 要求成套取值） | `#pageTitle` **27px/37.8px（1.4）**；`.s0-hero h2` **29px/43.5px（1.5）**；`.s0-boundary>span` **19px/22.8px（1.2）**；`.phase-index` 16px/**normal**；nav 图标 21px/**21px（1.0）**；12px 一族并存 19.2/19.8/20.4/21.6/22.8 五种行高 | B1「size + paired line height」 | P2 | 27/29 吸附到 24px/32px；12px 统一 16px 或 19.2px 一条；正文 1.65 的全局行高不要与阶梯行高混用 |
| B-08 | 焦点环在**深色侧栏与输入框**上对比不足 3:1（WCAG 1.4.11 / 2.4.11） | `#segS0`/`#btnS0`/`.action-item`/`.run-item` 环 `3px solid rgb(21,119,94)` 对 `#192e28` = **2.62:1**；`#s0Rtl`/`.input` 环 `2px solid rgb(196,226,207)` 对 `#fff` = **1.39:1**；白底按钮 **5.48:1**（合格） | B9「Focus — a visible focus ring」 | P2 | 侧栏用浅色环（如 `#8fd6bb` 一档），输入框环用 `--primary` 本色的 2px 环，统一做到 ≥3:1 |
| B-09 | `main:focus{outline:none}` 让「跳到工作区」只有功能效果、没有可见反馈 | `Tab`→`.skip-link`（环 5.48:1）→`Enter`：`activeElement`=`main#workspace`，`focusVisible=true`，但 `outlineStyle=**none**`，`scrollY` 0→**72** | B9 focus 非可选；B10 skip link | P3 | 给 `#workspace:focus-visible` 一个 inset 环或顶部高亮条；容器非控件，可接受但当前零反馈 |
| B-10 | 点击目标 **< 24×24**：Agent 卡片标题按钮 | `.agent-open`（`button.agent-name`，5 个）包围盒 **110.5×19.5 / 106.2×19.5 / 114.9×19.5 / 120.6×19.5 / 115.6×19.5**（monitor，1440×900）；monitor 视图 `<24` 共 5 个，S0/gate 为 0 | 技能无触控条款（B9 状态集）；WCAG 2.5.8 ≥24×24 | P2 | 给该按钮上下 padding 撑到 ≥24px 高（文字不变，命中区变大） |
| B-11 | 过渡动画全部是浏览器默认曲线 + 150ms | 80 个带过渡元素：`transitionTimingFunction` 全为 **`ease`**（41×三段/22×两段/17×一段）；时长 `0.15s`×71、`0.3s`×8、`0.2s`×1；另有 `animation: pulse 1.6s infinite ease`（2 处状态胶囊） | B7「Never ship a browser default curve」「color/opacity ≥200ms」 | P2 | 统一一条曲线（B7 基曲线）+ 200–300ms；`pulse` 属持续动画，考虑降为静态色点或 2s 以上低幅 |
| B-12 | 存在 1 处**背景渐变**（15px 选中指示点） | gate 勾选选项后 `.option.on > span.radio` `background-image: radial-gradient(circle, rgb(180,83,9) 0px, rgb(180,83,9) 40%, rgb(255,255,255) 42%, rgb(255,255,255) 100%)`，包围盒 **15×15**；S0 视图 0 处 | B4「Never use gradients in backgrounds」 | P3 | 改为纯色圆点（外环 + 实心内点），不用渐变 |
| B-13 | `prefers-color-scheme: dark` 下仍为浅色（**有意单主题**） | 模拟 dark：`body` 背景仍 `rgb(244,246,245)`、文字 `rgb(33,56,49)`、`html` `color-scheme: light`，与 light 完全一致 | 无（§14 未要求暗色） | P3 | 保持现状；若将来做暗色需单独过规格，不建议现在补未验证的暗色主题 |
| B-14 | 单侧边框 26 处，但**不是卡片边框** | 26 处均为 1px 分隔线：`#app>header`(bottom)、`.card-head`(bottom)、`#s0Checks>li`(bottom dashed)、`#s0PhaseFlow>li`、`.rail-foot`(top)、`footer.workspace-footer`(top)、`#s0RehearsalResult`(top dashed)；`.card` 本体 = `1px solid` **四边齐全**、`border-radius: 12px` | B4「never a border on only one side of **a card**」 | P3（记录，不判违规） | 无需改；抽公共卡片组件时把「分隔线」与「卡片边框」拆成两个 token |

## 1b 对比度失败清单（非禁用控件，比值 = WCAG 实算）

| 前景 | 背景 | 比值 | 字号/字重 | 出现位置（样例 selector） |
|---|---|---|---|---|
| `rgb(199,212,204)` | `#fff` | **1.53** | 22px/300 | `#app > header .context-divider`（"/" 装饰分隔符） |
| `rgb(172,184,177)` | `#f4f6f5` | **1.89** | 11px/400 | `.page-breadcrumb span`（"/" 分隔符） |
| `rgb(118,137,112)` | `#eaf1e7` | **3.27** | 9px/400 | `.hero-diagram .diagram-caption` |
| `#7b8b81` | `#f4f6f5` | **3.31** | 9px/400 | `.page-edition`（SIMULATION WORKBENCH） |
| `rgb(113,136,107)` | `#eaf1e7` | **3.35** | 9px/400 | `.diagram-connector span`（派生 & 核验） |
| `#71876a` | `#eaf1e7` | **3.39** | 8px/400 | `.diagram-label`（CONTROLLED DERIVATION） |
| `rgb(106,133,94)` | `#f0f4ed` | **3.68** | 16px/400 | `.phase-index`（01/02） |
| `rgb(112,131,106)` | `#f2f7f1` / `#f9fcf4` | **3.76 / 3.94** | 10px/400 | `.diagram-flow small`（只读基线 / 独立工作副本） |
| `rgb(149,125,86)` | `#fffaf0` | **3.78** | 9px/600 | `.s0-blockers .eyebrow`（BEFORE EXECUTION） |
| `rgb(105,133,99)` | `#f8faf6` | **3.89** | 12px/400 | `.section-index`（A/B/R）×7 |
| `rgb(108,127,105)` | `#f4f7f1` | **3.98** | 11px/400 | `.s0-checks li > span` ×6 |
| `#71827b`（`--faint`） | `#fff` | **4.05** | 11–12px | `.foot-note` ×2、`.stage-chev` ×19（monitor） |
| `#5c7a59` | `#eaf1e7` | **4.16** | 9px/600 | `.s0-hero .eyebrow` |
| `rgb(140,114,76)` | `#fffaf0` | **4.36** | 12px/400 | `#s0Blockers p` |
| `rgb(152,111,54)` / `rgb(152,101,101)` / `rgb(123,99,152)` | 头像底色 | **4.06 / 4.21 / 4.42** | 14px/700 | `.agent .avatar.a3/.a5/.a4`（monitor） |
| 禁用态（WCAG 1.4.3 豁免，仅记录灰度）：`rgb(97,116,108)`@op.55 | `#fff` | **2.17** | 12px/550 | `#btnNotify`（无头浏览器 Notification 被拒态，环境相关） |
| 禁用态：`#fff`@op.5 | `rgb(21,119,94)` | **2.56** | 13px/550 | `#gatePanel button.btn-primary:disabled` |
| 禁用态：`rgb(33,56,49)`@op.5 | `#fff` | **2.85** | 12px/550 | `#runHead` 取消作业键（monitor） |

## 2 逐项实测明细（与任务清单 1–10 对应）

| # | 项目 | 实测结论（数值 + 视口 1440×900，除注明外） |
|---|---|---|
| 1 | 字体族 | 声明栈首项 Inter 不可用；`document.fonts` 为空数组（**无 @font-face**），`document.fonts.check('14px Inter')` 全部返回 `true` —— 该 API 在无 @font-face 时恒真，**不能作为证据**，故以 CDP 平台字体 + 宽度探针为准（见 B-01）。实际：拉丁 = Liberation Sans，CJK = Noto Sans CJK SC，等宽 = Liberation Mono |
| 2 | 字号直方图 | 见 B-05/B-06。文本节点 209 / 字符 1967；`<12px` 占 38.8% 元素、29.6% 字符 |
| 3 | 行高配对 | 见 B-07。8px→13.2（1.65）、9px→14.85、10px→16.5/19、11px→18.15/18.7、12px→19.2/19.8/20.4/21.6/22.8、13px→21.45、14px→23.1、15px→24.75、21px→34.65/21、27px→37.8、29px→43.5/37.7 |
| 4 | 对比度 | S0 **28/209** 不达标（min **1.53**）、gate 14/173、monitor 33/238；**undecidable=0**（无渐变/半透明背景上的文本）。点名令牌：`--muted #61746c` → `#pageSub` **4.58** ✓；`--faint #71827b` → `.foot-note` **4.05** ✗；侧栏 `--rail-muted #a5b9ae` on `--rail #192e28` → **6.94** ✓（`.rail-label>span #839c8d` 4.86 ✓）；`.page-edition #7b8b81` 3.31 ✗；`.diagram-label #71876a` 3.39 ✗ |
| 5 | 焦点可见性 | S0 视图 22 步 Tab：**21/22** 有可见焦点环；gate 视图 18 步：17/18。环样式统一 `outline:3px solid rgb(21,119,94); offset:3px`（白底 5.48:1）。单选 radio 本体是 `1px auto` UA 环（元素 1×1、opacity 0），**真正的可见环在相邻 `.radio`：`2px solid rgb(21,119,94)`** → 判「有可见环」。例外：`main:focus{outline:none}`（B-09）、无焦点元素时的 BODY 空档 |
| 6 | 首屏 | `.s0-hero` 高 **252 / 265 / 275 px**（1280/1440/1920），占 720 视口 **35%**、900 的 29.4%；`#s0Prepare` 三档均不在首屏（B-02）。附加：闸门材料两栏同样在首屏外（B-03） |
| 7 | 点击目标 | 目标数 S0 26 / gate 28 / monitor 40；`<24`：0/0/**5**；`<32`：6/4/10。`<32` 明细：`.btn-sm` 93.3×30、`summary` 542.4×28.6、`.chip` 51×26.1、Agent 标题 110.5×19.5。**`.seg button` 实测 216×44**（任务简报中的 28px 已不成立）、`.rail-entry` 208×64、`.run-item` 216×66.9、`.action-item` 216×54.3 |
| 8 | 单侧边框/渐变 | 单侧边框 26 处（全为分隔线，`.card` 四边齐全）→ B-14；渐变 S0 **0** 处、gate **1** 处（`.option.on .radio`）→ B-12；`.s0-hero` `background-image: none`、`background-color: rgb(234,241,231)` |
| 9 | 动效 | 见 B-11。`prefers-reduced-motion: reduce` 下 `elementsWithMotion = **0**`（`transitionDuration` 全 0s、`animationName` 全 none；`.btn`/`.seg button`/`.rail-entry`/`.agent-clickable`/`.s0-hero`/`.card`/`.stage-bar i` 逐一复核） |
| 10 | 暗色方案 | 见 B-13（有意单主题，不做建议） |

## 2b 焦点遍历（S0 视图 22 步，键盘 Tab 真实触发）

| 停靠点 | 焦点环 | 环/底对比 |
|---|---|---|
| `#s0Rtl`（输入框） | 2px solid rgb(196,226,207) | **1.39** ✗ |
| `#s0Advanced > summary` / `.s0-access > summary` | 3px solid rgb(21,119,94) | 5.48 ✓ |
| `#s0Prepare`（主操作） | 3px solid rgb(21,119,94) offset 3px | 5.48 ✓ |
| `#s0Refresh` / `#s0SwitchRefresh` / `#s0SwitchBack` / `#s0CopiesRefresh` / `#s0Rehearsal` | 3px solid rgb(21,119,94) | 5.48 ✓ |
| `.skip-link`（首屏外 → 获焦后可见） | 3px solid rgb(21,119,94) | 5.05 ✓ |
| `#lnkLegacy` | 3px solid rgb(21,119,94) | 5.48 ✓ |
| `#btnS0` / `#btnNew` / `#segS0` / `.action-item`×2 / `.run-item`×2（深色侧栏） | 3px solid rgb(21,119,94) | **2.62** ✗ |
| `#workspace`（skip-link Enter 后） | `outline-style: none` | — ✗ |

## 3 验证为「没问题」的项（同样有数字）

| id | 项 | 证据 |
|---|---|---|
| OK-1 | 焦点环在常规白底控件上可见且充足 | 按钮/链接/summary 环 `3px solid #15775e` = **5.48:1**（21/22 停靠点），`.gate-pane` 2px 环；skip-link 环 5.05:1 且获焦后 `top:-80px → 12px` 可见 |
| OK-2 | `prefers-reduced-motion` 被真实遵守 | 模拟 reduce 后 `elementsWithMotion=0`，7 个抽样元素全部 `transition-duration:0s`、`animation-name:none` |
| OK-3 | 三档视口无水平溢出 | `scrollWidth - innerWidth = 0`：S0 高 3134/3110/3096、gate 高 1406/1586/1722，均只有纵向滚动 |
| OK-4 | 卡片边框四边齐全、无背景渐变（除 1 个 15px 指示点） | `.card` = `1px solid ×4`、radius 12px；S0 视图渐变 0 处 |
| OK-5 | 侧栏与运行条目点击目标充足 | `.seg button` 216×44、`.rail-entry` 208×64、`.run-item` 216×66.9、`.action-item` 216×54.3，均 ≥24×24 且 ≥32 高 |
| OK-6 | `.gate-pane` 双栏局部滚动生效 | `#gateMaterial` 649×560（`--gate-pane-max-h` 上限内），`#gatePanel` 461.1 高；两栏 y 相同、无横向溢出 |

## 4 未实测项与原因（不臆造）

| 项 | 原因 |
|---|---|
| `.hero-stamp` 的 65px/7px 字号与 `border-left` | `app.css:339-341` 有规则，但 `index.html`/`legacy.html` 中 **0 处** `.hero-stamp` 元素 ⇒ 死规则，运行时测不到 |
| `.linkbtn`、`.ev-chip` 尺寸 | S0/gate/monitor 三视图 `querySelectorAll` 均为 0（MISSING）；它们由事件流/节点详情动态渲染，受控夹具未产生事件（`/stream` 端点显式 404 让前端降级为轮询） |
| 受控夹具中的文案/数值结论 | 夹具值（「未记录」「—」等）不是真实运行产物，只用于渲染结构；**不作产品结论** |
| `#btnNotify`「通知 已拒绝」2.17:1 | 无头浏览器 Notification 权限默认被拒，该状态取决于运行环境而非产品数据 |
| 移动端/窄屏 | §14 明确「移动端不作为本轮设计和验收目标」，不在范围 |
| hover/active 态、loading/empty/error 三态视觉 | 本轮只覆盖静态渲染与键盘焦点；三态截图来自既有 `.ui-audit/shots/`，本次未重测 |
| 真实数据的对比度（长路径、超长错误串） | 需要真实运行数据；本轮为夹具 |
| 滚动/拖拽动效、`aspect-ratio` 变化 | 本轮未建立测量口径，不下结论 |

## 5 复跑命令

```bash
cd /home/work/chenjunming/change-impact-loop
PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers \
HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
loop/.venv/bin/python .ui-audit/measure.py
```

- 脚本只读 `loop/web/**`（起临时静态服务）并用受控夹具拦截 `**/api/**`；只写 `.ui-audit/measure.json` 与 `.ui-audit/shots-b/*.png`。
- 输出分节 M1–M10，末行 `pageErrors: [] posts: []` 表示夹具下无 JS 异常、无写请求（实测本次为空）。
- 数字核对路径：`.ui-audit/measure.json` 的 `M1_fonts` / `M2_fontSize` / `M3_lineHeight` / `M4_contrast_*` / `M4b_pairs_*` / `M5_focus_*` / `M6_fold` / `M6b_gate_fold` / `M7_targets_*` / `M7c_named_*` / `M7b_disabled_*` / `M8_borders_gradients` / `M8_gate_gradients` / `M9_motion` / `M10_scheme`。
- 既有浏览器基线（本轮未重跑，沿用任务给定记录 `12 passed in 16.34s`）：`cd loop && PLAYWRIGHT_BROWSERS_PATH=../.pw-browsers HOME=../.chrome-home TMPDIR=../.chrome-tmp .venv/bin/python -m pytest -q tests/browser/test_web_layout.py`。

## 6 原始数字（节选，完整见 measure.json）

- 元素/文本：全页 971 元素，可见文本节点 209，字符 1967（S0 视图）。
- 字号计数：8→1、9→10、10→19、10.5→3、11→46、11.5→2、12→55、12.5→8、13→30、14→10、15→9、16→2、17→1、19→1、20→1、21→6、22→1、27→1、29→3。
- 对比度：S0 `fail=28 min=1.53`、gate `fail=14 min=1.53`、monitor `fail=33 min=1.53`，`undecidable=0`。
- 首屏（S0）：`#s0Prepare` y=1098.1/1078.3/1066.5，`.s0-hero` h=252/265/275，`#s0Rtl` y=793/794.8/814.8。
- 首屏（gate）：`#gateMaterial` y=909.6/913.6/885.5（visibleRatio 0/0/0.27），`#gateHead` y=222.4/226.4/236.4。
- 动效：`{0.15s×71, 0.3s×8, 0.2s×1}`，timing 全 `ease`；`pulse 1.6s infinite`。
- 禁用态合成：`.btn:disabled{opacity:.5}` → 有效前景 `#fff`、有效背景 `rgb(138,187,174.5)` = **2.14:1**。
- 平台字体（CDP）：`latin-edition` → Liberation Sans(20)+Liberation Mono(2)；`page-title` → Noto Sans CJK SC(4)；`mono-path` → Liberation Mono(16)。
