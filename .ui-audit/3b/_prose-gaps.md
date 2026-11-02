# 3B（配色令牌化）· 收敛不了的情况（gaps）

> 基线同 [absorption.md](absorption.md)（`app.css` md5 `00f4477c…` / 1218 行，`legacy.css` md5 `1491537…` / 81 行）。
> 本文只列**不能干净收敛**的东西，逐条给建议 + 需要人裁的点。

## 0 预算硬账：≤40 与「0 字面量 + 全 ≤12」不可同时满足

| 项 | 数 | 说明 |
|---|---|---|
| §5.2 表里的令牌 | **41** | 底5+线3+字4+主4+成3+警5+危4+紫3+栏7+浮层3；本身已超「≤40」1 个 |
| 本提案采用 | **40** | 既有 24 + 新增 16（§0.1） |
| 「全收敛」需要 | **≈46** | 40 + 补回 `--surface-3`/`--danger-line-soft`/`--purple-line`/`--rail-active`（4）+ avatar 强调色（6）− 可为 alpha 让位的 2–4 |
| 当前结果 | **40 个令牌 / 实色 Δ≤12 309/362（85.4%）/ Δ>12 59 条** | 100% 有令牌（unmapped=0），但不是 100% ≤12 |

**三选一（人裁）**：
- **A（推荐）把上限提到 46**：补 `--surface-3`、`--danger-line-soft`、`--purple-line`、`--rail-active` + `--av-*` 强调色 6 个；
  预计 Δ>12 从 59 降到 ~12（剩下的都是 alpha 不可见项与一处蓝墨）。
- **B 守住 40，接受 59 条 Δ>12**：需要人明确「这 59 条视觉差可接受」，并让实现者按 [map.tsv](map.tsv) 直接替换（Δ 列已给）。
- **C 守 40 + 缩小范围**：avatar 强调色（6 条）与 3 条内联色保留为**白名单例外**（不进令牌），其余按 map.tsv 替换；
  这样 `test_ui_tokens.py` 的「字面量 = 0」必须允许该白名单（§5.3 判据要相应放宽）。

### 0.1 本提案 40 个令牌（口径：24 既有 + 16 新增）

既有 24：`--bg --panel --surface --text --muted --faint --line --line-strong --primary --primary-hover
--primary-weak --primary-line --ok --ok-weak --warn --warn-weak --danger --danger-weak --purple --purple-weak
--rail --rail-hover --rail-text --rail-muted`
新增 16：`--surface-2 --line-soft --text-2 --text-3 --ok-line --warn-line --warn-line-soft --warn-ink
--danger-line --rail-border --rail-accent --rail-tint --rail-line --shadow-tint --shadow-pop --overlay`

## 1 ΔRGB>12 的 59 条（53 个不同值）

按成因分 7 类；**全表见 §1.8**（逐条：字面量 / 落点令牌 / Δ / α / 位置）。

| 类 | 条数 | 成因 | 建议 |
|---|---|---|---|
| **A** 阴影/遮罩 alpha | 6 | RGB 主体与令牌差 18–78，但 α≤20/255（8% 以内） | **建议接受**：α 这么小时合成差 <1%，肉眼不可见。若要求严格，加 `--shadow-glow`（绿/蓝 glow 各 1） |
| **B** avatar 强调色 / 紫边 | 9 | `.a1 #2457d6`(蓝) / `.a2 #3c7465` / `.a4 #624d80` / `.a5 #7b4f4f` 是**身份色**，§5.2 无对应族；`#e1d8ec/#dfd1ed` 紫边无 `--purple-line` | 方案 A：加 `--av-1…--av-5`（5 个）；方案 C：保留例外。**必须人裁**（见 D3） |
| **C** 琥珀强调（warn 亮阶） | 4 | `#e8b86a #c49c61 #ba914b #b9873b` 是 warn 的**亮阶**，离 `--warn-line #f3d19e` 52–61、离 `--warn #9a5e16` 41–53 | 加 `--warn-accent`（1 个，值 ≈`#c49c61`）可吃掉 4 条；否则接受 |
| **D** 中/浅绿文字（ink 档位缺口） | 10 | 存量正文字在 `#44607a…#799a8c` 一带（含 1 条蓝墨 `#44607a`），4 个冻结 ink 令牌夹不住 | 方案 A 加 `--text-4`（≈`#6d8172`）；蓝墨 `#44607a` 只能靠 `--meta-blue` 或接受 |
| **E** 浅色描边/分隔（温度差） | 10 | 同一「浅线」里有冷蓝白、绿温、暖黄三温；冻结的 `--line/--line-strong` + 新增 `--line-soft` 只能吃两温 | 接受（Δ13–16 为主）或加 `--line-warm` |
| **F** 深底浅绿 / 侧栏 | 11 | `--rail-muted`（冻结 `#a5b9ae`）与 `#839c8d…#a7c69b` 一串浅绿差 23–35；侧栏选中底色 `#304b3d` 差 14（`--rail-active` 被裁掉） | 方案 A 加 `--rail-muted-2` + `--rail-active`；否则接受 |
| **G** 其它单点 | 9 | `#148b68`（成功文字亮阶，离 `--ok` 27）、`#6b5127`（warn ink 暖阶 17）、`#54694b/#50694b/#6b836a`（legacy 绿墨 13–15） | 多为 Δ13–17，建议接受；`#148b68` 建议改 `--ok`（可见但只影响 2 处"通过"文字） |

### 1.8 全表（ΔRGB>12，按 Δ 降序）

TABLE_OVER12

## 2 内联样式：`legacy.html` 的 `<style>` 块（L8–L161）

- 该块是**旧深色主题**（`body{background:#0e1116}` 那套），共 **158 条**色值出现 / 91 个选择器。
- 与 `tokens.css` + `legacy.css` + `app.css` 比对后：**88 个选择器已被覆盖**（其中 155 条色值是**死声明**：
  被后加载的 `legacy.css` 同选择器覆盖，级联上不生效）；**只有 3 个选择器 / 3 条色值仍然生效**：

TABLE_INLINE

**建议（D4）**：
1. 首选：把 `.chain-arrow` 的 `color` 换成 `var(--muted)`（`#5a6675`→`#61746c`，Δ11，可读性不回退）；
   `.toast-item.err/.ok` 的 `border-left-color` 换成 `var(--danger)` / `var(--ok)`（亮红/亮绿 → 语义色，Δ 大但此处是 4px 状态边，观感更统一）。
   这样组件层没有活着的字面量，`legacy.html` 的 155 条死声明可**另开一批**（属清理，不属令牌化）。
2. 备选：整块删除前必须先证明 88 个选择器 100% 被覆盖（本文只给了选择器级证据；属性级还有死声明与活声明混在同一选择器里，
   例如 `.panel > h2` 的 `color:#9fd0ff` 被 `.panel>h2{color:var(--text)}` 覆盖，但 `border-color` 可能不覆盖）。
   **不建议本轮动**：删样式块的风险面比收益大，且 3C 合并期间的指纹基线不干净。
- `legacy.html` / `index.html` 的 7 处 `style="…"` 属性**全部是布局**（`margin-top` / `justify-content`），**0 个色值**，不需要处理。

## 3 JS 里动态拼的色值：0

```
grep -rnoE "#[0-9a-fA-F]{3,8}\b|rgba?\(" loop/web/*.js   →  0 命中
```
`app.js` 只切 class（`cls: "a1"…"a6"`），颜色由 CSS 决定；`agent-window.js` 只切 `className = "alert bad"`。
⇒ **不存在**「JS 里拼 hex」的问题；3B 只需改 CSS。

## 4 box-shadow 多色 / 渐变

- **渐变：0 条**（`grep -E "(linear|radial)-gradient" loop/web/app.css loop/web/legacy.css` → 无命中）。
- **多色 box-shadow：1 条**，在 `tokens.css:13` 的 `--shadow:0 2px 4px #20372b03,0 8px 24px #20372b03`。
  它在**令牌文件内**，不违反「组件层 0 字面量」；且它自己的两个色值（α=3 的深绿）与 `--shadow-tint` 同族，
  本轮**不动**（改它等于改阴影观感，超出纯令牌化）。
- 其余 `box-shadow` 都是单色，已按 A 类处理。

## 5 `mockup.html` 明确不参与

§14:825「静态历史样张不重绘」+ 审计「主动判不建议改」。`mockup.html` 的色值（**未统计，故意不统计**）
不进清单、不建令牌、不做守卫；`test_ui_tokens.py` 的扫描范围也只应覆盖 `app.css`/`legacy.css`/`tokens.css`。

## 6 待裁清单（人裁点）

| id | 待裁点 | 选项 | 影响 |
|---|---|---|---|
| D1 | 令牌预算 | A 提到 46 / B 守 40 接受 59 条 Δ>12 / C 守 40 + 白名单 | 决定实现者能拿到多少条 `Δ≤12` |
| D2 | 6 个新增令牌的中位色值（absorption §3.1） | 接受 / 换回 §5.2 原值 | 接受 ⇒ 305 条 ≤12；换回 ⇒ 282 条，Δ>12 涨到 82 |
| D3 | avatar 强调色 6 个（`.a1–.a6`） | 加 `--av-*` / 保留例外 / 粗暴映射 | 粗暴映射会把「分析=蓝」变紫、「报告=玫瑰」变红，**不建议** |
| D4 | legacy.html 仍生效的 3 条内联色 | 换 `var()` / 保留例外 / 删整块 | 见 §2；建议换 `var()`（3 行改动） |
| D5 | 4 条 α 漂移 >12（`--overlay` α163、`--rail-line` α48、toast 阴影 α38×2） | 接受 / 按族拆细令牌 | 影响遮罩深浅与 toast 阴影浓度 |
| D6 | 剩余 Δ>12（§1 A–G） | 接受 / 按 §1 建议加 1–2 个令牌 | 见 §1 表 |
| D7 | legacy 的「成功边框」是暖绿（`#c9dfc7/#c3dabc`），与 `chip.ok` 的青绿（`#bfe8d8`）不同源 | 分开（`--ok-line` + `--line-strong`）/ 合并接受 Δ17–28 | 只影响 legacy 两处徽标边框 |
| D8 | `--primary` / `--primary-hover` 吸收 0 条 | 保留（推荐，仍被 `var()` 消费）/ 删 | 删会破坏 `var()` 引用，**不可删** |
