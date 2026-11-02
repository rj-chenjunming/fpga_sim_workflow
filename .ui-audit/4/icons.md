# 批次 4 · A 项设计：图标 SVG sprite（inline `<symbol>`，零外链、零字体依赖）

> 只读设计分析，供人裁后实现。**未改任何被测文件**；本文所有行号/数字都来自本轮命令输出。
> 落点：`loop/web/{index.html,app.js,s0.js,node-detail.js,app.css}`（写权：UI 轨实现 owner）。
> 依据：`doc/audit/AUDIT-20261030-ui-design.md` D-16；`doc/spec/WEB_UI_SPEC.md` §14「资产」「层次」「动效」、
> §10 A10/A13/A14；`doc/agents/开工提示词_UI批次3C与3B.md` §6/§10。

## 0 快照与并发提醒（读本文必须先读这段）

| 文件 | md5（本分析读取时） | mtime |
|---|---|---|
| `loop/web/index.html` | `5694d59ef6c89e0cd1e15effcf8aec38` | 10-30 10:03 |
| `loop/web/app.js` | `e685977e97881752701f7d159f25012b` | 10-30 09:43 |
| `loop/web/s0.js` | `a362c56bad3f13a2ded59edd6d4688fc` | 10-30 01:16 |
| `loop/web/node-detail.js` | —（未改，见 §1 表尾） | 10-26 19:32 |
| `loop/web/app.css` | 读取时 `ef5b389335f48696a7e7b962dd3e3cc4`；**交稿时已变 `7d9e3aceb7c65f8f91d53516aee7565e`** | 10-30 **13:48 → 13:53**（3C 合并仍在进行） |

**坑**：`app.css` 在我读取期间正被 3C（F14 合并）反复改写（10:03 → 13:48 → 13:53；行数 1213 → 1195，`git diff --stat` 显示 `app.css -1171`；
我交稿时 `.stage-chev`/`.dp-icon` 已各下移 1 行）。**本文行号只能当定位线索，一律以选择器 grep 为准。**
本文 `app.css` 行号是上述 md5 的快照；实现时**一律按选择器 grep 定位，不要信行号**。
同理 `.aw-detail` 相关规则若已被 3C 当死声明删除，A 项的 §3.6 自动消解。

证据原始输出：`.ui-audit/4/icon-inventory.txt`（逐处校验，`校验失败=0`）、`.ui-audit/4/icon-scan-other-modules.txt`。

---

## 1 全量盘点：承担图标作用的 Unicode 字符

扫描面：`loop/web/*.{html,js,css}`（`mockup.html` 是 §14 明示的静态历史样张，不参与）。
脚本按「图标角色」逐处人工判定后**用脚本回校验行号确实含该字符**，结果 `行数=54 校验失败=0`：

| 指标 | 数值 |
|---|---|
| 参与图标的码位种类 | **23**（含 ASCII `!`；另有 ASCII 字母 `F` 作品牌字标，不算图标） |
| 图标角色出现总处数 | **54** |
| 分布 | `index.html` 15 · `app.js` 14 · `s0.js` 7 · `legacy.html` 12 · `node-detail.js` 3 · `app.css` 3 |

### 1.1 逐字符（file:line → 当前语义）

| 字符 | 码位 | 次数 | 出现位置 | 当前语义 |
|---|---|---|---|---|
| `✓` | U+2713 | 8 | `app.js:1497`（节点已完成）、`app.js:1632`（阶段序号完成态）、`s0.js:117/211/582`（检查项通过） | 完成 / 通过 |
| `→` | U+2192 | 7（图标角色） | `index.html:87`（主操作后缀）、`s0.js:76/265/295/466`、`app.js:3112` | 主操作「继续/前往」 |
| `↗` | U+2197 | 7 | `index.html:22`（旧版操作台）、`index.html:133`（下载报告）、`index.html:500`（`target=_blank` 真实用例）、`app.js:1781`、`node-detail.js:790/1575/1740` | **三种语义混用**（见 §1.2） |
| `×` | U+00D7 | 4 | `index.html:410/541/612/628` | 关闭浮层 |
| `✕` | U+2715 | 4 | `app.js:1500`；`legacy.html:1175/1604/1610` | 失败 / 拒绝 |
| `▸` | U+25B8 | 3 | `app.js:1646`（阶段展开）、`app.js:3608`（目录行）、`app.css:406`（`.aw-detail` 死规则） | 展开指示 / 行首标记 |
| `◇` | U+25C7 | 2 | `index.html:43`（导航 人工闸门）、`app.css:542`（空态插图） | **一符两义** |
| `↑` | U+2191 | 2 | `index.html:389`（上级目录）、`legacy.html:1408`（`↑ parent`） | 向上 / 父级 |
| `•` | U+2022 | 2 | `app.js:1756/1778` | agent 头像占位 |
| `⛔` | U+26D4 | 2 | `legacy.html:988/1303` | 阻断 / 不可判定（**依赖 emoji 字体**） |
| `⌄` | U+2304 | 1 | `index.html:34` | 折叠指示 |
| `▧` | U+25A7 | 1 | `index.html:40` | 导航 环境准备 |
| `⊞` | U+229E | 1 | `index.html:41` | 导航 运行配置 |
| `◴` | U+25F4 | 1 | `index.html:42` | 导航 运行监控 |
| `●` | U+25CF | 1 | `app.js:806` | `document.title` 待办计数前缀（**不可 SVG 化**） |
| `!` | U+0021 | 1 | `app.js:1498` | 节点等待（待人工） |
| `…` | U+2026 | 1（图标角色） | `app.js:1499` | 节点进行中（与 57 处文案省略号**同符不同义**） |
| `▣` | U+25A3 | 1 | `app.js:3569` | 基线条目有效 |
| `▢` | U+25A2 | 1 | `app.js:3569` | 基线条目无效 / 缺件 |
| `←` | U+2190 | 1 | `legacy.html:171` | 返回工作台 |
| `⟳` | U+27F3 | 1 | `legacy.html:564` | 重新查证 |
| `⚠` | U+26A0 | 1 | `legacy.html:766` | 警告（**依赖 emoji 字体**） |
| `▾` | U+25BE | 1 | `app.css:407` | `.aw-detail` 展开（死规则） |
| `F` | U+0046 | 1 | `index.html:34` `.workspace-icon` | 品牌字标（保留为文字） |

### 1.2 一符多义（本次要消灭的核心问题）

| 字符 | 语义 A | 语义 B | 语义 C | 结论 |
|---|---|---|---|---|
| `◇` | 导航「人工闸门」`index.html:43` | 空态插图 `app.css:542`（58×58 框内 30px） | — | 拆成 `icon-gate` / `icon-empty` |
| `▸` | 阶段展开指示 `app.js:1646`（旋转 90° 表示开合） | 目录行首标记 `app.js:3608` | 折叠三角 `app.css:406` | 前两者同义（展开）；目录行实为装饰 → 见 §3.6 |
| `↗` | 外链/新窗口：`index.html:500`（`target=_blank`）、`index.html:133`（下载） | 页内浮层：`app.js:1781`、`node-detail.js:790/1575/1740`（打开 dialog/浮窗） | 同标签页跳转：`index.html:22`（`a href="legacy.html"`，**没有新窗口**） | 拆成 `icon-external` / `icon-panel`；`index.html:22` 去掉箭头只留文字 |
| `×` vs `✕` | 关闭 `index.html:410/541/612/628` | 失败/拒绝 `app.js:1500` 等 | — | 两个不同字形表达两个语义，统一为 `icon-close` / `icon-fail` |
| `…` | 进行中状态 `app.js:1499` | 文案省略号（57 处，如「加载中…」） | — | 状态用 `icon-running`；省略号留在文本里 |
| `→` | 主操作「继续/前往」`index.html:87` 等 7 处 | 文案里的流程中继（`copy → replace`、`派生 → 端口确认 → …` 等，属内容） | — | 只有**可点击动作**换 `icon-next`；正文里的箭头保留字面（它是句子的一部分，换成 SVG 会伤选择/复制与读屏） |
| `⇧`-类 `↑` | 上级目录按钮 `index.html:389` | 父级链文本 `↑ parent` `legacy.html:1408` | — | 前者 `icon-up`；后者是带词文本，保留 |

### 1.3 明确**不**参与 sprite 的字符（避免误伤）

`§ · … “ ” ≤ ≥ ∩ ⇒ ≠ ① ② ③ — –` 等：文案标点/数学符号，不是图标。
`●`（`app.js:806`）：写入 `document.title`，浏览器标签标题只接受文本 → 见 §6 例外登记。

---

## 2 符号表（一符一义，16×16 线性图标，`currentColor`）

规范：`viewBox="0 0 16 16"`、纯线条、`fill:none` + `stroke:currentColor` + `stroke-width:1.5` +
`stroke-linecap:round` + `stroke-linejoin:round`（只在 `.icon` 规则里写一次，符号内不再重复声明）。
下列 path 是**草图**：实现时可微调几何，但**不得改语义、不得一符多义**。

| # | symbol id | 语义 | 取代 | path 草图（可直接内联） |
|---|---|---|---|---|
| 1 | `icon-s0` | 环境准备 / 派生工作副本 | `▧` `index.html:40` | `<path d="M8 1.9 13.8 5 8 8.1 2.2 5z"/><path d="M2.2 5v6L8 14.1l5.8-3.1V5"/><path d="M8 8.1v6"/>` |
| 2 | `icon-setup` | 运行配置 / 参数 | `⊞` `index.html:41` | `<path d="M2.5 5.5h11M2.5 10.5h11"/><circle cx="6" cy="5.5" r="1.7"/><circle cx="10.5" cy="10.5" r="1.7"/>` |
| 3 | `icon-run` | 运行监控 / 运行中 | `◴` `index.html:42` | `<circle cx="8" cy="8" r="5.7"/><path d="M6.7 5.6 10.6 8l-3.9 2.4z"/>` |
| 4 | `icon-gate` | 人工闸门 / 决策关卡 | `◇` `index.html:43` | `<path d="M2.5 4.8h11"/><path d="M5 4.8v8.2M11 4.8v8.2"/><path d="M2.5 13h11"/>` |
| 5 | `icon-chevron` | 展开/收起（`rotate` 表达开合） | `⌄` `index.html:34`、`▸` `app.js:1646` | `<path d="M6.2 3.8 10.4 8l-4.2 4.2"/>` |
| 6 | `icon-next` | 主操作：继续/前往 | `→` 7 处 | `<path d="M2.8 8h9.4"/><path d="M8.6 4.4 12.2 8l-3.6 3.6"/>` |
| 7 | `icon-external` | 外部动作：新窗口 / 下载 | `↗` `index.html:133/500` | `<path d="M6.6 3.4H3.4v9.2h9.2V9.4"/><path d="M9.2 3.4h3.4v3.4"/><path d="M12.6 3.4 7.6 8.4"/>` |
| 8 | `icon-panel` | 打开页内浮层（Agent 窗口/前后对比） | `↗` `app.js:1781`、`node-detail.js:790/1575/1740` | `<rect x="2.4" y="3.4" width="11.2" height="9.2" rx="1.6"/><path d="M2.4 6.3h11.2"/>` |
| 9 | `icon-close` | 关闭浮层 | `×` 4 处 | `<path d="M4.4 4.4 11.6 11.6M11.6 4.4 4.4 11.6"/>` |
| 10 | `icon-check` | 完成 / 通过 | `✓` `app.js:1497/1632`、`s0.js:117/211/582` | `<path d="M3.2 8.4 6.4 11.6 12.8 5.2"/>` |
| 11 | `icon-fail` | 失败 / 拒绝 | `✕` `app.js:1500` | `<circle cx="8" cy="8" r="5.7"/><path d="M5.9 5.9 10.1 10.1M10.1 5.9 5.9 10.1"/>` |
| 12 | `icon-wait` | 等待（待人工） | `!` `app.js:1498` | `<circle cx="8" cy="8" r="5.7"/><path d="M8 4.6v4.2"/><path d="M8 11.2v.3"/>` |
| 13 | `icon-running` | 进行中 | `…` `app.js:1499` | `<circle cx="3.2" cy="8" r="1.1"/><circle cx="8" cy="8" r="1.1"/><circle cx="12.8" cy="8" r="1.1"/>`（这三个圆用 `class="icon-fill"`） |
| 14 | `icon-up` | 上级目录 | `↑` `index.html:389` | `<path d="M8 13V3.2"/><path d="M4.4 6.8 8 3.2l3.6 3.6"/>` |
| 15 | `icon-back` | 返回（回主工作台） | `←` `legacy.html:171` | `<path d="M13 8H3.2"/><path d="M6.8 4.4 3.2 8l3.6 3.6"/>` |
| 16 | `icon-refresh` | 重新查证 | `⟳` `legacy.html:564` | `<path d="M12.6 8a4.6 4.6 0 1 1-1.35-3.25"/><path d="M11.25 2.6v2.6h-2.6"/>` |
| 17 | `icon-warn` | 警告（口径不足/待核） | `⚠` `legacy.html:766` | `<path d="M8 2.6 14.2 13H1.8z"/><path d="M8 6.4v3.2"/><path d="M8 11.5v.3"/>` |
| 18 | `icon-blocked` | 阻断 / 不可判定 | `⛔` `legacy.html:988/1303` | `<circle cx="8" cy="8" r="5.7"/><path d="M4.5 11.5 11.5 4.5"/>` |
| 19 | `icon-valid` | 有效 / 已就绪 | `▣` `app.js:3569` | `<rect x="3" y="3" width="10" height="10" rx="1.6"/><path d="M5.5 8.2 7.3 10l3.2-3.6"/>` |
| 20 | `icon-invalid` | 无效 / 缺件 | `▢` `app.js:3569` | `<rect x="3" y="3" width="10" height="10" rx="1.6"/><path d="M5.6 10.4 10.4 5.6"/>` |
| 21 | `icon-agent` | agent 角色占位 | `•` `app.js:1756/1778` | `<circle cx="8" cy="5.9" r="2.5"/><path d="M3.6 13.2a4.4 4.4 0 0 1 8.8 0"/>` |
| 22 | `icon-empty` | 空态插图（58×58 框内 30px） | `◇` `app.css:542` | `<path d="M2.4 9.2h3l1 1.8h3.2l1-1.8h3"/><path d="M2.4 9.2 4.6 3.6A1.6 1.6 0 0 1 6.1 2.6h3.8a1.6 1.6 0 0 1 1.5 1L13.6 9.2V12a1.6 1.6 0 0 1-1.6 1.6H4a1.6 1.6 0 0 1-1.6-1.6z"/>` |

> 22 个符号 vs 23 个码位：差的那一个正是 `●`（`document.title` 前缀，不可 SVG 化，§6 例外）。
> `!` 与 `…` 之所以要 sprite，是因为它们在 11px 圆形状态泡 `.snode .sb` 里承担状态含义，字形回退风险与 `✓/✕` 相同。

---

## 3 落地方式

### 3.1 sprite 放在哪

- **放在 `index.html`** 的 `<body>` 首个子节点，一个隐藏根，内部 22 个 `<symbol>`：
  ```html
  <!-- §14「资产」：图标本地内联，零外链零字体。注意：**不写 xmlns**（见 §5 坑 1）。 -->
  <svg id="iconSprite" class="icon-sprite" aria-hidden="true" focusable="false">
    <symbol id="icon-s0" viewBox="0 0 16 16"> … </symbol>
    …
    <symbol id="icon-empty" viewBox="0 0 16 16"> … </symbol>
  </svg>
  ```
- 引用点：`<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-s0"></use></svg>`
  （HTML5 内联 SVG 不需要 `xmlns`，`<use href>` 不需要 `xlink:href`；Chromium 156 实测口径见 `measure.json.meta.chromium`）。
- 动态图标的模板（`app.js` 用、避免在 JS 里拼 namespace 字符串）：
  ```html
  <template id="iconTpl"><svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-s0"></use></svg></template>
  ```

### 3.2 `app.css` 需要的规则（新增块，建议放在 `.hidden` 工具类附近）

```css
/* ---------- 图标（WEB_UI_SPEC §14「资产」：本地内联 sprite，零外链、零字体依赖） ---------- */
.icon-sprite{position:absolute;width:0;height:0;overflow:hidden}
.icon{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:-3px;
  fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.icon-fill{fill:currentColor;stroke:none}      /* icon-running 的三个圆点 */
.icon-30{width:30px;height:30px;vertical-align:baseline}  /* 空态插图 */
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
  clip-path:inset(50%);white-space:nowrap;border:0}
```
> 只用 `px` 尺寸、**不加任何 `font-size`**（否则要进 §14 字号阶梯），不写 `url()`（§5 坑 2）。

### 3.3 既有规则要改的（`app.css`，按选择器定位）

| 现有规则（快照行号） | 改法 | 理由 |
|---|---|---|
| `.nav-icon{width:19px;font-size:20px;line-height:1;text-align:center;color:#91ad9b}`（490） | `.nav-icon{width:19px;display:inline-grid;place-items:center;color:#91ad9b}` | 图标不再靠字号撑尺寸；保留 19px 槽位使 `.seg button` 的 **44px 高**（`measure.json M7c_named_s0`：`{'w':216,'h':44}`）与 `.rail-entry` **64px** 不变（A10 可达性断言依赖这些盒） |
| `@media(max-width:760px){….nav-icon{font-size:16px;width:16px}…}` | 删 `font-size:16px`，保留 `width:16px` | 同上 |
| `.stage-chev{…;font-size:11px;…}`（158） | `.stage-chev{color:var(--faint);transition:transform .2s var(--ease-out);display:inline-flex}`；`.stage.open .stage-chev{transform:rotate(90deg)}` **不动** | 旋转仍是 `transform`，符合 §14 动效（只动 transform/opacity） |
| `.dp-icon{width:18px;text-align:center;color:var(--warn);flex:0 0 auto}`（284） | `.dp-icon{width:18px;display:inline-flex;justify-content:center;color:var(--warn);flex:0 0 auto}` | — |
| `.empty:before{content:"◇";…;font-size:30px}`（542） | 删该 `:before`；改 `.empty .icon-empty{display:block;margin:0 auto 20px;padding:14px;box-sizing:content-box;border:1px solid #d6e3d8;border-radius:16px;background:#f0f6f1;color:#60846a}` | 58×58 圆角框的视觉效果保留（14px padding + 30px 图标 = 58px 内容盒） |
| `.aw-detail summary:before{content:'▸'}` / `[open]:before{content:'▾'}`（406/407） | **直接删除**（不是迁移）：`grep -rn aw-detail loop/web/` 只命中 `app.css`，无 HTML/JS 消费者 → 死规则 | 少两个码位，且符合 3C「删死声明」的方向；若 3C 已删则跳过 |

### 3.4 `app.js` / `s0.js` / `node-detail.js` 的动态图标

新增（`app.js` 顶部工具区，紧邻 `function h(...)`）：

```js
/* 图标：唯一来源是 index.html 的 #iconSprite；本文件只克隆 #iconTpl，
   不拼 "http://www.w3.org/2000/svg" 这类 namespace 字符串
   （tests/test_web_smoke.py:38 断言 app.js 里不得出现 "http://"）。 */
var ICON_TPL = null;
function iconNode(name) {
  if (!ICON_TPL) {
    var t = document.getElementById("iconTpl");
    ICON_TPL = t && t.content ? t.content.firstElementChild : null;
  }
  if (!ICON_TPL) return document.createTextNode("");
  var svg = ICON_TPL.cloneNode(true);
  var use = svg.querySelector("use");
  if (use) use.setAttribute("href", "#icon-" + name);
  return svg;
}
```
> `s0.js` / `node-detail.js` 各自的 IIFE 里没有 `h()`，按同一形态各放一份 5 行 `iconNode`（或把该函数挂到 `window` 由三者共用 —— **但那样多一个全局**；本设计倾向各文件内联小函数，与现有 `el()/h()` 各自隔离的风格一致）。
> 若实现者更愿意用 `document.createElementNS`：**禁止** —— 会把 `"http://…"` 字符串写进 JS，直接红 `test_web_smoke.py:38`。

逐处改法：

| 位置 | 现状 | 改法 |
|---|---|---|
| `index.html:40-43` | `<span class="nav-icon" aria-hidden="true">▧</span>` | `<svg class="icon nav-icon" aria-hidden="true" focusable="false"><use href="#icon-s0"/></svg>`（其余三个同理：`icon-setup`/`icon-run`/`icon-gate`）；按钮内文字与 `<small>` 保留 → 读屏仍有「环境准备 S0」 |
| `index.html:34` | `<span aria-hidden="true">⌄</span>` | `<svg class="icon" aria-hidden="true" focusable="false"><use href="#icon-chevron"/></svg>` |
| `index.html:87` | 主按钮内 `<span aria-hidden="true">→</span>` | `<svg class="icon" aria-hidden="true" …><use href="#icon-next"/></svg>`；`s0.js:76` 同步改为「文字 + iconNode("next")」（现为 `textContent = "派生并校验 →"`，**必须改成换 `replaceChildren(文本节点, 图标)`**，不能再用 `textContent`） |
| `index.html:133/500` | 文本尾部 `↗` | 尾部追加 `icon-external`；`index.html:22`（旧版操作台）**去掉 ↗ 只留文字**（同标签页跳转，↗ 误导） |
| `index.html:389` | `↑ 上级` | `icon-up` + 文字「上级」 |
| `index.html:410/541/612/628` | `关闭 ×` | 文字「关闭」+ `icon-close`（`aria-label` 已存在，保持不变） |
| `app.js:1497-1500` `nodeIcon()` | 返回字符 `"✓"/"!"/"…"/"✕"` | 返回 `iconNode("check"|"wait"|"running"|"fail")`；调用点 `app.js:1671` `bubble.appendChild(h("span", null, nodeIcon(st)))` → `bubble.appendChild(nodeIcon(st))` |
| `app.js:1632` | `h("div","stage-idx", agg.cls==="done" ? "✓" : String(idx+1))` | done 时：`var box=h("div","stage-idx"); box.appendChild(iconNode("check")); box.appendChild(h("span","sr-only","已完成"));`（`✓` 替代数字 = 状态变化，必须有文本替代）；否则仍写序号 |
| `app.js:1646` | `h("span","stage-chev","▸")` | `h("span","stage-chev")` 内 append `iconNode("chevron")` |
| `app.js:3569` | `▣/▢` | `iconNode("valid"/"invalid")`；同行已有 `chip ok`「manifest 有效」/`chip bad`「缺 …」文字，**图标 aria-hidden 即可**，不重复造文本 |
| `app.js:3608` | 目录行 `▸` | 装饰性行首：直接 `iconNode("chevron")`（`aria-hidden`）；或干脆删掉（目录行已有 `<b>` 名称） |
| `app.js:1781` / `node-detail.js:790/1575/1740` | `name + " ↗"` | 文字 + `icon-panel`（页内浮层，**不是**新窗口；这正是一符多义要修的误读） |
| `app.js:1756/1778` | `"•"` / `def.avatar or "•"` | `iconNode("agent")`；`agentCard` 里 `head.appendChild(h("div","avatar "+(cls), def.avatar || "•"))` → 无 avatar 时 append 图标节点 |
| `s0.js:117/211/582` | `"✓" : String(index+1)` | 通过时 `iconNode("check")` + `.sr-only`「已验证」；否则序号 |
| `s0.js:265/295/466` | `"继续冒烟 →"` / `"去新建运行 →"` | 文字 + `iconNode("next")`（`replaceChildren`） |
| `app.js:3112` | `"去人工闸门视图逐条处置 →"` | 同上 |

### 3.5 a11y 口径

1. **每个图标 `<svg aria-hidden="true" focusable="false">`**，语义只由相邻可见文字或 `aria-label` 承担（nav 按钮、关闭按钮、Agent 打开按钮均已有文字/aria-label）。
2. **图标不承载唯一信息**：`✓/✕/!` 这类状态图标补 `.sr-only` 文本（「已完成」「失败」「等待人工」）；`▣/▢` 已有 chip 文本，不重复。
3. **不给图标加 `tabindex`**，不把它们做成按钮；点击目标仍是外层 `button`/`a`。
4. 焦点环、hover 色沿用父元素（图标用 `currentColor`，`.snode .sb{color:var(--faint)}` 等既有色即生效）。
5. 目标尺寸：图标 16px 在 `.btn-sm`(30px)、`.seg button`(44px)、`.dp-item` 内均 ≥ 24px 命中区（A13/D-11 既有结论不回退）。

### 3.6 `legacy.html` 是否共用同一 sprite？

**建议：本批次不迁移 `legacy.html`（12 处 + `.accent` 深色主题），作为登记例外；sprite 只进 `index.html`。**

理由（按重要性）：
1. `legacy.html` 是**存档界面**（§13：保留一个迭代），其图标全在**内联脚本字符串**里（`legacy.html:564/577/766/988/1152/1175/1303/1599/1604/1610`），迁移要动存档页的渲染代码，风险与收益不成比例；
2. 无构建步骤（§13 第 5 条），**共用 sprite 只能复制粘贴**——两页各 22 个 `<symbol>`，一旦漂移就是第二套口径（红线 8 的邻域）；而 `legacy.css`/内联 `<style>` 是深色主题，颜色仍要靠 `currentColor`，共用价值低于维护成本；
3. **`<use href="icons.svg#id">` 跨文档引用不要用**：同源外部引用在部分浏览器对 `currentColor`/样式继承支持不一致，且会新增一个静态资源与一次 HTTP 请求；§14「资产」要求"零运行时依赖"，内联是唯一稳妥形态。

如果人裁要求一次性覆盖 legacy：做法是**逐页各自内联同一份 sprite**（复制 §3.1 的 22 个 symbol + §3.2 的 `.icon` 规则写进 legacy 的内联 `<style>`），并在计划里登记"两份拷贝必须逐字节一致"。注意 `⚠/⛔` 在 legacy 依赖 emoji 字体（D-16 原文），迁移后这一条风险才真正消除。

### 3.7 为什么不给 CSS 伪元素用 sprite

`.empty:before`、`.aw-detail summary:before` 都是伪元素，**无法放 `<use>`**。可选项只有：
`url()` 背景 / `mask-image`（**被 `test_ui_visual_20261030.py:261` `assert "url(" not in tokens + css` 卡的**）、或字体图标（违反零字体依赖）。
所以：**能改结构的地方改结构（`.empty` 由 `app.js:1234` 生成，加一个子节点即可），不能改的删掉死规则**。

---

## 4 会被影响的既有测试断言（**不改测试**，只列）

先给出耦合面实测（`grep -rnF` 在 `loop/tests/` 统计，本次运行）：

| 断言处 | 现断言 | 影响 | 建议改法 |
|---|---|---|---|
| `loop/tests/test_web_smoke.py:31` | `assert "http://" not in html and "https://" not in html` | **最高风险**：内联 `<svg xmlns="http://www.w3.org/2000/svg">` 会直接红 | sprite 根**不写 `xmlns`**（HTML5 不需要）；`<symbol>`/`<use>` 同理 |
| `loop/tests/test_web_smoke.py:38` | `assert "http://" not in js and "https://" not in js` | 同上，`app.js` 里不得出现 namespace URI | 用 `#iconTpl` 克隆（§3.4），禁用 `createElementNS` |
| `loop/tests/test_api.py:59` | `assert "http://" not in html and "https://" not in html`（`GET /`） | 同 `test_web_smoke.py:31` | 同上 |
| `loop/tests/browser/test_ui_visual_20261030.py:261` | `assert "url(" not in tokens + css` / `assert "@font-face" not in …` | 图标**不能**用 `url()`/字体 | 内联 sprite + `currentColor` |
| `loop/tests/browser/test_ui_visual_20261030.py:200` | 探针 `.avatar.a3/.a4/.a5` 对比度 ≥4.5 | 已知角色头像仍是汉字（`app.js:49-53`），**不受影响**；`•` 只在服务端下发未知角色时出现 | 无需改；若把 `.avatar` 全改图标，需同步探针 |
| `loop/tests/test_ui_typography.py`（`SCALE`/`assert len(found) >= 300`） | 字号必须落在 11 档、扫描数 ≥300 | 删 `.nav-icon`/`.stage-chev`/`.empty:before`/`.stage-idx` 的 `font-size` 会使扫描数下降（当前基线 355，本轮预计 −4～−6，仍 ≥300 **但须在实现后复核实际数**）；新增 `.icon` **不得**带 `font-size` | 无 | 
| `loop/tests/browser/test_web_layout.py:161-166`、`test_sidebar_entries_are_reachable_at_acceptance_viewports`（A10） | `#segS0` 可聚焦；侧栏条目 `scrollIntoView` 后完整在视口内 | 图标若改变 `.seg button`(44px)/`.rail-entry`(64px) 盒高，**会移动侧栏几何** | 按 §3.3 保留 `width:19px` 槽位与按钮高度；实现后跑浏览器门 |
| `loop/tests/test_pane_scroll.py:110` | `html.count('class="card-body gate-pane"') == 2` | 与本项无关，但**提醒**：改 `index.html` 时不要动这两处 class 顺序 | 无 |
| `loop/tests/browser/test_ui_visual_20261030.py:274-283` | `.s0-hero` 不存在、`nav` ≥1、`link[rel=icon]`、`sk-line`/`skip-link` | sprite 根是 `<svg>` 不是 `<nav>`，不冲突 | 无 |

**结论：图标字符本身在 `tests/` 里零断言**（逐个 `grep -rnF` 结果：`▧/⊞/◴/◇/✓/✕/▸/▾/▣/▢/●/⚠/⛔/⟳/↗/↑/←/⌄` 均 **0** 命中；`×` 的 6 处命中全是 `1280×720` 这类"宽×高"文案）。所以本项**不需要改任何既有测试**，风险全在 §4 表格上半部分的"零外链/零字体/字号/几何"四条边。

### 4.1 建议新增的守卫（TDD：先红后绿，红日志落档）

1. 软件层 `loop/tests/test_ui_icons.py`（不启浏览器）：
   - `index.html` 含 `id="iconSprite"`；`xmlns` 不出现（与 `test_web_smoke.py:31` 同口径但更明确）；
   - 每个 `href="#icon-X"`（含 JS 里 `iconNode("x")` 字面量）都能在 sprite 找到 `id="icon-X"`；
   - 每个 `<symbol>` 都有 `viewBox="0 0 16 16"`；id 唯一；数量 ≥ 20；且**每个 symbol 至少被引用一次**（防死符号）；
   - `index.html`/`app.js`/`s0.js`/`node-detail.js` 里 §1 的 23 个码位**归零**（`legacy.html` 白名单 + `app.js:806` 的 `●` 白名单，白名单要写理由）；
   - `app.css` 有 `.icon{…width:16px;height:16px…}`、且全文件 `url(`/`@font-face` 仍为 0（后者与既有断言重复，作为本项自证）。
2. 浏览器层（加进 `test_ui_visual_20261030.py`）：四个 `.nav-icon` 的 `getBoundingClientRect()` 为 16×16（±0.5）；`.seg button` 高仍 44（±1）；`document.querySelectorAll('svg.icon').length >= 8`。

---

## 5 坑（每条都会红一条既有断言或踩一次已经踩过的坑）

1. **`xmlns="http://www.w3.org/2000/svg"` 会红三条用例**（`test_web_smoke.py:31`、`:38`、`test_api.py:59`）。仓库里现成的 `favicon.svg` 顶部就有这个属性（它是独立文件，不受影响）——**不要整段复制进 HTML**。HTML5 内联 SVG 省略 `xmlns` 合法。
2. **CSS 侧不许 `url(`**（`test_ui_visual_20261030.py:261`）→ 伪元素图标只能删或改结构，不能做 mask/背景图。
3. **`app.js` 不许出现 namespace 字符串**（同 1）→ `document.createElementNS("http://www.w3.org/2000/svg", …)` 是**禁用写法**，用 `<template>` 克隆。
4. **几何回归**：`.seg button` 44px / `.rail-entry` 64px（`measure.json M7c_named_s0`）是 A10 侧栏可达性与 A12 首屏的输入；换图标时改 `.nav-icon` 的槽宽或行高 = 移动整条侧栏。改完必跑浏览器门。
5. **`textContent = "… →"` 的写法有 6 处**（`s0.js:76/265/295/466`、`app.js:3112`，以及 `index.html` 静态文本），改图标必须换 `replaceChildren`，否则图标会被 `textContent` 清掉或被当成文本节点插入。
6. **字体依赖未真正消除前不要声称"图标已本地化"**：`⚠/⛔` 仍在内联脚本里且只在 legacy；`●` 仍写进 `document.title`。这些必须进 STATUS「未做/例外」清单。
7. **`app.css` 正在被 3C 合并**：`.aw-detail` 死规则可能已被删、`.nav-icon`/`.stage-chev`/`.dp-icon`/`.empty:before` 的行号会漂移。落地前先 `git diff loop/web/app.css | head` 确认 3C 已收口，避免两边同时改同一块。
8. **`✓` 在 8 处有三种上下文**（节点状态/阶段序号/检查项/legacy 提交结果）：只把前三类（index 侧）换 sprite 时，不要顺手改 legacy 的 3 处，否则存档页行为未验证。
9. **状态泡 `.snode .sb` 有 `font-size:11px;font-weight:700`**（`app.css` `.snode .sb`）：换成 SVG 后这两条变成无效声明（可保留，不阻塞；但 3C 若按死声明删除是合理的）。
10. **`test_ui_typography.py` 的扫描数门槛是 ≥300**：删 4–6 条 `font-size` 仍安全，但若实现者顺手把更多字号声明改成 rem/em 会直接红。

---

## 6 未做 / 不声称（本设计明确不覆盖）

1. **`legacy.html` 12 处图标不迁移**（§3.6），`⚠/⛔` 的 emoji 字体依赖**仍在**——D-16 只被部分解决。
2. **`●`（`app.js:806`）不 sprite 化**：`document.title` 只接受文本；建议保留并登记为唯一"文本图标"例外，或后续改成纯 `(3)` 计数（已由 `wait-center.badgeTitle` 提供）。
3. **`index.html:22`「旧版操作台 ↗」**：建议只删箭头不给图标；若人裁要求保留指向性，用 `icon-back` 也不对（不是返回），**不要**复用 `icon-external`（同标签页跳转）。
4. 本文的 path 是**草图**，未在浏览器里渲染验证（本任务不跑浏览器）；落地后须截图目检并跑浏览器门。
5. 未改任何测试、未动 `loop/web/**`、未 commit。
