# UI 批次 3C · F14 两段式 CSS 合并（行为保持）· 计划

> 来源：[`doc/agents/开工提示词_UI批次3C与3B.md`](../agents/开工提示词_UI批次3C与3B.md) §4（本轮任务）
> + [`doc/audit/AUDIT-20261021-post-ui-roadmap.md`](../audit/AUDIT-20261021-post-ui-roadmap.md#L33) F14
> + [`doc/audit/AUDIT-20261030-ui-design.md`](../audit/AUDIT-20261030-ui-design.md) D-04/D-15。
> 上游已完成：批次 1+2（STATUS §140）、批次 3A 字号阶梯（STATUS §141）。
> 本切片**不改规格**（行为保持、无契约变化）；证据与执行记录见 §7 与 `doc/STATUS.md` 新区段。

| 项 | 内容 |
|---|---|
| 类型 | 保持行为的重构（CSS 结构收敛），**零计算样式差异**是唯一硬判据 |
| 实现 owner | Lead（`loop/web/app.css` 单写者；复核阶段由只读复核员独立复跑） |
| 允许修改 | `loop/web/app.css`、新增 `loop/tests/test_ui_css_structure.py`、本计划、`doc/STATUS.md`（Lead）、`doc/evidence/UI_CSS_MERGE_20261030/`（只增）、`.ui-audit/3c/`（未入库临时区） |
| **不修改** | `loop/web/{index.html,app.js,tokens.css,legacy.*,favicon.svg}`、`loop/services/**`、`loop/host/**`、`loop/workflows/**`、`kb/**`、`mockup.html`、`doc/spec/**`（本切片不改规格）、任何已有测试的断言 |
| 回滚 | 不做 git 回滚（工作树混有前序 T3 与本轨成果）。每批前的 `app.css` 快照保存在 `.ui-audit/3c/snap-batchNN/`，回滚=按快照文件覆盖回 `loop/web/app.css`；最终 before 快照 `.ui-audit/3c/snap-before/`（md5 `103ec75124e21c6c97a717d7607fa132`） |

## 1 问题与现状（数字来自 2026-10-30 本轮实测，命令见 §9）

`loop/web/app.css` 是两段式：前段（早期组件/S0 样式）与第 468 行起的「视觉系统段」叠加，
同名选择器被多次定义；F14 要求收敛到「同一选择器单一定义」，否则任何令牌化都会被后段覆盖。

命令输出（`loop/.venv/bin/python`，用 `.ui-audit/3c/` 内的解析器，括号深度解析，非正则）：

```
app.css: 1213 行 / 1080 条解析规则 / 917 条顶层规则 / 793 个不同选择器文本 / 642 个不同简单选择器
同一 (选择器文本, @ 上下文) 被 ≥2 条规则定义：194 组，涉及 372 条规则
  其中顶层上下文 179 组 / 347 条规则；@media(max-width:760px) 14 组；@media(max-width:850px) 1 组
「同上下文、同选择器、同属性、被后置声明支配」的死声明：5 条（整条规则可删 2 条）
```

结论：F14-b（2026-10-22，STATUS §41）已清掉「同上下文内被后者完全支配」的声明；
**剩下的 194 组是「属性集不相交」的真合并**——必须搬动声明位置，靠级联语义逐条判，
不能按「同选择器出现两次」机械删。

## 2 方法与级联安全判据

### 2.1 三层证据

1. **静态级联判据（决定能不能合）**：见 §2.2，逐声明给出「搬动后无竞争者」的理由。
2. **计算样式指纹（证明真没变）**：`.ui-audit/3c/verify_style_equivalence.py`（源自冻结证据
   `doc/evidence/R_BLOCK_C_20261022/verify_style_equivalence.py`，**归档件只读，副本改 REPO 解析**）。
   覆盖：主视口 1280×720 / 1440×900 / 1920×1080 × 8 状态（s0/setup/run/gate/dirpicker/agent/
   节点详情/legacy/empty）+ 51 个断点宽度 ±1px × (s0,run) 全扫描 + 窄断点 agent + legacy 三主视口；
   每个元素取全部 longhand 计算值 + `::before`/`::after`，双哈希逐元素比对。判定 = 差异组合数 **0**。
3. **结构守卫（防回流）**：新增 `loop/tests/test_ui_css_structure.py`（软件层，不启浏览器）：
   断言「同一简单选择器在同一 @ 上下文内只定义一次」，扫描数 ≥700（防空扫），例外走白名单并注明理由。

### 2.2 合并的级联安全判据（每条搬动声明都要满足）

对同一 (选择器 S, @ 上下文 C) 的一组规则 R1…Rn（文档顺序递增），合并目标位置 = **最后一条** Rn：

- **保留哪条声明**：对属性 p，若组内存在 `!important` 声明，胜者 = 最后一条 `!important`；
  否则胜者 = 最后一条普通声明。被胜者支配的声明（同属性、重要性不高于胜者且更早）**删除**；
  同一属性不同重要性的两条同时保留（`color:red!important; color:blue` 的既有语义不变）。
- **搬动是否安全**：若胜者来自 Ri（i<n），则必须对 Ri 与 Rn 之间（文档顺序）**每一条**声明了
  同属性、同重要性的规则 R 证明「不会同时命中同一元素」或「特异性不同」。判据：
  1. `!important` 不同 → 无关（重要性永远优先于源码顺序）；
  2. 特异性不同 → 无关（高特异性恒定胜出，搬动前后都胜出；低特异性恒定失败）；
  3. 特异性相等 → 比较两者**最右复合选择器**是否可能命中同一元素：id 互斥 / 标签互斥 /
     伪元素互斥 ⇒ 不会同时命中；其余情况（都只要类、或属性选择器）**按可能命中处理**，
     此时该组不得自动合并，转为人工逐条判定，判不了就**保持现状并登记为例外**。
- **不改的东西**：不新增 `!important`；不改任何声明值；不合并 `@media` 条件；不重排
  `@media`/`@supports` 块；不删除「选择器命中 0 个元素但类名仍出现在 HTML/JS 里」的规则（动态态）。
- **死规则**：只有「选择器的最右复合选择器的**类/id 名**在 `index.html`/`app.js`/`s0.js`/
  `agent-window.js`/`node-detail.js`/`legacy.html` 中**完全不出现**」的规则才可删（如 hero 删除后的
  `.s0-hero`/`.diagram-*`/`.hero-*` 残留），且逐条列进 §7 的删除清单。

### 2.3 分批

每批 **≤15 个选择器**：`合并一批 → 主视口 8 状态指纹 → 51 断点扫描指纹 → diff=0 才进下一批`。
指纹非空：先按 §2.2 复算判据（不靠「看起来一样」），判据不成立就把该批回退到快照并登记例外。

### 2.4 证据层：为什么「静态判据」不够、证据必须 fail-closed

静态判据在类选择器之间只能得到「**可能**命中同一元素」，照字面执行会把 189/193 组都判红（`.card` vs `.gate-card`、
`.btn` vs `.btn-sm` 这类在源码上无从排除）。因此加一层**运行时 DOM 共命中证据**：

- 工具：`.ui-audit/3c/cooccur.py`（由只读分析员实现）：在 3 个主视口 × 12 个状态（s0/setup/run/gate/dirpicker/
  agent/node-detail/empty/legacy/toast/alert/gate-empty）里，对**全量 884 个选择器**（`app.css`+`legacy.css` 每条规则的
  每个逗号分量）做 `querySelectorAll`，记录「哪些选择器命中同一元素」（2626 对共命中 / 391170 对已检查）。
  匹配前剥掉交互态伪类与伪元素（`querySelectorAll(':hover')` 恒空，不剥会把交互态规则误判成「永不共命中」）。
- **fail-closed 规则**：只有当「两个选择器都在证据里被测过」且「这对从未共命中」时，才允许豁免；
  **未测到的对一律不放宽**（否则「没测」会被当成「没问题」——本轮实测踩过：证据集只覆盖首批受阻对时，
  `.input`×`.mono` 未被测，`.input` 组被错误放行，指纹当场抓到 `input.mono` 的 `font-family` 从等宽变正文族）。
- 静态判据里**简写按 longhand 展开**比较（`font`↔`font-family`、`background`↔`background-color`、`border`↔
  `border-*-color`、`gap`↔`row-gap` …），否则「`font` 简写搬到后面压掉中间 `font-weight`」这类会漏判。

### 2.5 本轮工具上发现并修正的两个缺陷（如实登记）

1. **逗号拆分不尊重括号**：`split` 第一版按 `,` 硬切，把 `:where(button,a,summary):focus-visible{…}` 拆成三条非法规则、
   被浏览器整条丢弃（实测 `a.skip-link` 的 `text-decoration` 从 `none` 变 `underline`）。已改为顶层逗号切分 + 括号平衡断言；
   该事故还暴露「只测非交互态的指纹看不见焦点环丢失」，因此验证工具补了 **focus/hover 交互态** 与
   **样式表规则序列对账**（浏览器会静默丢非法规则，条数对账能抓）。
2. **胜者判定把「前置 important」判错**：第一版「前一条 important 就保留」会让后置普通声明压不过前置 important、
   且两条普通声明时保留靠前的值（实测 `#s0AllowedRoots` 的 `font-size` 应 12px 被判成 10px）。
   已改为「`!important` 优先于源码顺序；同重要性后置胜」。两处都是**指纹先报红**、再回头改工具，不是「看起来一样」。


## 3 验收判据

| 判据 | 方式 | 目标 |
|---|---|---|
| 级联行为不变 | 指纹（3 主视口 × 8 状态 + 51 断点 × 2 状态 + agent 窄断点 + legacy） | **差异组合 0**，`transition-*`/`animation-*` 计算值也一致 |
| 结构收敛 | `test_ui_css_structure.py` + 盘点脚本 | 194 组 → **0**（白名单除外，白名单必须逐条注明理由）；顶层规则数降到「不同选择器数 + 必要 @media」量级 |
| 既有功能不退化 | 浏览器门 | **178 passed**（0 failed） |
| 软件层 | `bash spikes/run_software_checks.sh --ignore=tests/browser -q` | **≥2003 passed**（2002 + 新增 ≥1），0 failed |
| 文档 | `python3 doc/audit/check_doc_links.py` | `missing=0`，exit 0 |
| 可读性不回退 | `.ui-audit/measure.py` 复跑 | 对比度 fail 数 / 焦点环 / 点击靶 / 首屏读数与本轮基线一致（§9） |
| 诚实 | 本计划 §7 + STATUS | 保留/删除/例外逐条可查；不声称「视觉完全不变」而无指纹证据 |

## 4 写权与协作

- `loop/web/app.css` 单写者：Lead。复核员只读（不得改被测文件，报告写 `.ui-audit/3C-verify.md`）。
- 3B（配色令牌化）与批次 4 只读分析并行进行，写权互不重叠（分析产物只落 `.ui-audit/`）。
- 证据目录 `doc/evidence/UI_CSS_MERGE_20261030/` 只新增、不改旧件。

## 5 回滚

- 每批前快照：`.ui-audit/3c/snap-batchNN/app.css`；批内失败 → 覆盖回快照 + 该批登记为「例外/保持现状」。
- 整片失败 → 覆盖回 `.ui-audit/3c/snap-before/app.css`（md5 `103ec75…`，与开工时逐字节一致），
  结构守卫用例保持红灯并以 `pytest.mark.xfail`/跳过**不采用**——直接登记「本切片未完成」。

## 6 未做 / 不声称（事前登记，执行后按实际更新）

- **不令牌化**（3B 负责）：本切片只合并不改颜色字面量；`app.css` 仍是 319 处 hex。
- **不动 `legacy.css`/`legacy.html`**：F14 提到旧页内联样式被 `legacy.css` 覆盖，本切片只做 `app.css`（3C 范围）。
- **不动 `@media` 条件**、不合并断点：断点交界行为由指纹覆盖，但不改条件本身。
- **hover/active/focus/disabled 的视觉不做截图实测**：这些态的计算样式由「级联判据 + 51 断点扫描」间接覆盖，
  但**没有**逐态截图；如需要人工目检，另立项。
- **不声称视觉验收通过**：本切片只声称「计算样式指纹零差异 + 结构收敛 + 既有门全绿」。

## 7 执行记录

### 7.1 开工基线（2026-10-30，本轮实测；命令与输出见 §9）

| 门 | 命令 | 实测 |
|---|---|---|
| 浏览器全量 | `pytest -q tests/browser`（Chromium `$R/.pw-browsers`，`HOME`/`TMPDIR` 仓库内） | **178 passed in 205.88s**，exit 0 |
| 软件层 | `bash spikes/run_software_checks.sh --ignore=tests/browser -q` | **2002 passed, 3 deselected in 285.88s**，exit 0 |
| 字号守卫 | `pytest -q tests/test_ui_typography.py` | **3 passed in 0.62s** |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=3166 skipped=44727 historical=857 known_missing=16 env_missing=35 missing=0`，exit 0 |
| 运行时读数 | `.ui-audit/measure.py`（受控夹具；**不跑归档副本**，因归档副本会写冻结证据目录） | 对比度 fail：s0 `3/194`、gate `4/173`、monitor `4/238`（min 1.53 = 装饰 `/`）；焦点环可见 s0 `21/22`、gate `17/18`；`<24px` 点击靶 0；背景渐变 0；1440 闸门 `#gateMaterial y=832.3` |

### 7.2 执行记录（数字从命令输出复制）

**结构（`.ui-audit/3c/merge_plan.py stats`，同一解析器）**

| 阶段 | 行数 | 解析规则 | 顶层规则 | 不同选择器 | 重复组（选择器×上下文） |
|---|---|---|---|---|---|
| 开工（pristine，md5 `103ec75…`） | 1213 | 1160 | 969 | 792 | **193**（顶层 178 / 760 断点 14 / 850 断点 1） |
| 逗号拆分后（batch 00） | 1218 | 1160 | 969 | 792 | 193 |
| 合并收口（staging，md5 `73430cb2…`） | 1008 | 974 | 791 | 792 | **23**（全部为白名单例外） |

**为什么是 23 而不是 0**：这 23 组分成两类（见守卫 `ALLOWED` 的逐条理由）——① 两段之间夹着同特异性覆盖规则、
且运行时 DOM 共命中证据显示确有元素同时命中两者（`.btn`/`.card`/`.grid2`/`.input`/`@media760 .rail-entry` 等）；
② 同名选择器在窗口内另有别的 @ 上下文规则（`.agents`/`.run-list`/`.toast`/`.phase-card`/`.s0-phases`/`header`/
`.shell`/`.aw-*` 等）。两类都是「合并任一方向都会改变某断点/某元素组合的生效值」。

**分批（每批 ≤15、批后 24 组合指纹）**：`.ui-audit/3c/batches.log` 记录 13 批全部 `PASS`
（每批 24 个（视口,状态）组合计算样式指纹 0 差异）。**注意**：逐批「主视口 24 组合」指纹在原理上
看不见窄断点（≤1100）的行为变化——本轮就有一批（跨 @media 同选择器）靠独立复核的静态级联复算发现，
详见 §7.3。

### 7.3 独立复核发现并修复的 P0（如实登记）

独立复核员（`verifier-3c`，只读）在静态复算中发现 `classify` 的一条 **fail-open**：
同选择器跨 @ 上下文时，证据键 `pair` 退化成 1 元素集合、`pair not in co` 恒成立 ⇒ 判为「无竞争者」。
后果：pre-fix staging 有 **23 处 / 11 个选择器**的跨上下文翻转（`.agents`/`.run-list`/`.toast`/`.phase-card`/
`.s0-phases`/`.shell`/`header`/`.aw-head`/`.aw-intervene`/`.aw-log-row`/`.aw-terminal-mark`/`.aw-timeline`），
断点内生效值真的变了。修法：`sanitize(src)==sanitize(cand)` 且 `(media,at)` 不同 ⇒ **直接受阻**
（源码先后在各个上下文里就是生效关系，共命中证据对这条没有信息量）；受阻组 9 → 24，最终落盘残留 23 组。
复核员的独立枚举（不读本工具）给出 21 组、`21 ⊂ 24` 且与新受挡一一对应；其 `cross_ctx_check.py`
在 `snap-before` vs 最终产物上 PASS。

**门（本轮实测，原样输出见 `doc/evidence/UI_CSS_MERGE_20261030/`）**

| 门 | 命令 | 实测 |
|---|---|---|
| 结构守卫（先红） | `pytest -q tests/test_ui_css_structure.py`（修正解析器后对 pristine） | **193 组重复 / 非白名单 190**（`.ui-audit/3c/red-test-pristine.txt`） |
| 结构守卫（后绿） | 同上（落盘后） | **2 passed**（白名单 23 条，含陈旧条目检测） |
| 字号守卫 | `pytest -q tests/test_ui_typography.py` | 3 passed（扫描数见证据原文） |
| 计算样式指纹（3C 收口，staging 隔离） | `verify_style_equivalence.py --before-web snap-before --after-web web-stage`（全断点 196 组合） | 见 §7.4 |
| 浏览器全量 / 软件层 / 文档 | 见 STATUS 新区段 | 见 STATUS |
