# 3B（配色令牌化）· 吸收表

> **基线（钉住的快照，`.ui-audit/3b/snap/`）**：`loop/web/app.css` md5 `00f4477cc800aea432ccc3df9e2d1f53` / 1218 行；
> `loop/web/legacy.css` md5 `149153746ed1fa738b56aebea7db1e40` / 81 行；`loop/web/tokens.css` md5 `3d23134177964d8e2b2749a241f55a43` / 18 行。
>
> **这条必须读**：3C（F14 合并）正在写 `loop/web/app.css`，本轮审计期间它被重写了 4 次（1213 → 1173 → 1149 → 1218 行，md5 连变）。
> 行号会继续漂移，**值是稳定的**：字面量→令牌是**值级映射**（`map-values.tsv`，234 个不同值），不依赖行号；
> 行号级替换清单 `map.tsv` 与基线 md5 绑定。实现前请先跑 `bash .ui-audit/3b/rescan.sh` 重钉快照。
> **复核实测（14:0x，对当时的工作树）**：live `app.css`（md5 `b31ca8f0…`）与本快照的**不同值集合完全相同**
> （389 条出现 / 234 个不同值，差集为 0）——3C 只挪/合并声明，没改色值。⇒ `map-values.tsv` 现在就能用，只有行号要重跑。
>
> 本表只覆盖 `app.css` + `legacy.css`（§5.1 的两个组件文件）；`legacy.html` 内联样式、`mockup.html` 见 [gaps.md](gaps.md)。

## 1 口径（先说清楚，避免复核歧义）

| 约定 | 取值 |
|---|---|
| ΔRGB | `max(|Δr|,|Δg|,|Δb|)`，逐通道最大绝对差，0–255 sRGB；**不是**加权色差、不是 HSL 差、不乘系数 |
| 合并容差 | **12**（人裁「同一语义族内允许 ≤12 RGB 的合并色差」） |
| 跨族合并 | **禁止**。成功 / 警告 / 危险 / 紫 各自独立；守卫在 `build_mapping.py` 的 `COMPAT`：warn 字面量不可能落到 ok/primary/danger 令牌 |
| 既有 24 个颜色令牌 | 值**一律不动**（§5.2「现状」）。所以 `--text`/`--muted`/`--faint`/`--line`/`--line-strong`/`--rail-*` 的部分吸收会 >12，单列在 [gaps.md](gaps.md) |
| 新增 16 个令牌 | 值取所吸收存量族的中位色；与 §5.2 建议值的偏差逐条列在 §3 |
| alpha 面（8 位 hex / rgba） | ΔRGB 不作判据（alpha 才是观感主因），改看 **α 漂移**（§4） |
| 归一化 | `#abc` → `#aabbcc`；`#aabbccdd` 拆成 `rgb + alpha`；`rgb()/rgba()` 转 0–255 |

## 2 每个令牌吸收了什么（§5.2 组顺序）

| 组 | 令牌 | §5.2 建议值 | 采用值（本提案） | 与建议值 ΔRGB | 吸收的字面量（归一化，次数） | 吸收条数 | 组内最大 ΔRGB |
|---|---|---|---|---|---|---|---|
| 底（浅表面） | `--panel` | #fff | #ffffff | 0 | #fff×39 #fefefe×1 | 40 | 1 |
| 底（浅表面） | `--surface` | #f8faf9 | #f8faf9 | 0 | #f8fafc×2 #f9fbf7×2 #f8faf6×1 #fafcf8×1 #f9fbf6×1 #f7faf7×1 #fafcfa×1 | 9 | 3 |
| 底（浅表面） | `--surface-2` | #fcfdfb | #fcfdfb | 0 | #fcfdfb×9 #fbfdf9×5 #fffdf8×3 #fcfdfc×3 #fffafa×2 #fbfcfe×2 #fafbfd×1 #fffdf7×1 | 26 | 4 |
| 底（浅表面） | `--bg` | #f4f6f5 | #f4f6f5 | 0 | #f6f9f4×8 #f5f8f1×5 #f8faf5×4 #f6f9f3×2 #f2f4f7×1 #f0f3f7×1 #f3faf5×1 #f1f6f2×1 #f3f6f3×1 #f4f7f1×1 #f7faf5×1 #f8eeee×1 #f6faf3×1 #f7f8f6×1 #f4f8f0×1 #f7faf3×1 | 31 | 8 |
| 线（分隔/边框） | `--line` | #e1e8e4 | #e1e8e4 | 0 | #e1ede7×1 #e5ece9×1 #e6edea×1 #e2eadb×1 #e1d8ec×1 #dde5df×1 #dfd1ed×1 | 7 | 23 |
| 线（分隔/边框） | `--line-strong` | #c7d4cc | #c7d4cc | 0 | #c7d4c8×3 #c4dfcc×2 #cae2c4×1 #d0ddcc×1 #c4d1c7×1 #cfdccb×1 #d3dfcc×1 #c9d4c3×1 #c8dfbc×1 | 12 | 16 |
| 线（分隔/边框） | `--line-soft` | #eef1f5 | #d9ecde | 23 | #d9ecde×2 #d7e6e1×1 #dae6df×1 #d6e3d8×1 #dce7da×1 #e1eadb×1 #dae5d2×1 #d9e7d6×1 #e0e9db×1 #e0e8db×1 #d9e8d4×1 #e0ecda×1 #dae3d5×1 #d7e8d5×1 #dce8d7×1 | 16 | 12 |
| 字（正文/说明） | `--text` | #213831 | #213831 | 0 | #20382b×2 #243a2b×2 #183d2e×1 | 5 | 9 |
| 字（正文/说明） | `--text-2` | #3d5545 | #2f4a37 | 14 | #34533c×2 #234b34×1 #304b3d×1 #284c35×1 #36533d×1 #2f4a37×1 #304b35×1 | 8 | 12 |
| 字（正文/说明） | `--text-3` | — | #536e58 | — | #55684f×3 #456761×2 #4d6b4e×2 #5c7a59×2 #456a58×1 #496353×1 #536e58×1 #58715f×1 #5d7756×1 #62834c×1 #3c7465×1 #456e48×1 #5e7854×1 #54694b×1 #5c7055×1 #5a6e52×1 #57764c×1 #50694b×1 | 23 | 23 |
| 字（正文/说明） | `--muted` | #61746c | #61746c | 0 | #617673×1 #799a8c×1 #718c7e×1 #728d7b×1 #60846a×1 #6b836a×1 | 6 | 38 |
| 字（正文/说明） | `--faint` | #5f6f67 | #5f6f67 | 0 | #44607a×2 #52716c×1 | 3 | 27 |
| 主色（青绿） | `--primary` | 现状 | #15775e | — | （无吸收） | 0 | 0 |
| 主色（青绿） | `--primary-hover` | 现状 | #0e604b | — | （无吸收） | 0 | 0 |
| 主色（青绿） | `--primary-weak` | 现状 | #eaf5ef | — | #eceff4×1 #edf2f1×1 #edf2ee×1 #eaf0e9×1 #e9f3ee×1 #eef2ef×1 #e8eeea×1 | 7 | 7 |
| 主色（青绿） | `--primary-line` | 现状 | #b8daca | — | #b7d2bf×1 #c1dcbd×1 | 2 | 13 |
| 成功 | `--ok` | #24734d | #24734d | 0 | #148b68×2 | 2 | 27 |
| 成功 | `--ok-weak` | #edf7ef | #edf7ef | 0 | #edf3e8×3 #eef8f1×2 #e9f8f0×1 #f0f6f1×1 #f0f4ed×1 #f2f7ef×1 #f0f4ef×1 #eaf3e8×1 #eef7ee×1 #f2f6ee×1 #f1f5ef×1 #f1f4ee×1 #edf4e8×1 #edf5e7×1 | 17 | 8 |
| 成功 | `--ok-line` | #bfe8d8 | #cbe9d8 | 12 | #bfe8d8×4 #cae9db×3 #cbe9d8×1 #d1e5da×1 #d4e8c8×1 #d4e0cc×1 #c9dfc7×1 #c3dabc×1 | 13 | 28 |
| 警告 | `--warn` | #9a5e16 | #9a5e16 | 0 | #ba914b×1 #b9873b×1 | 2 | 53 |
| 警告 | `--warn-weak` | #fff6e8 | #fff6e8 | 0 | #fffaf1×7 #fbf7ef×2 #fdf0ef×2 #fff8ec×1 #fffaf0×1 #fbf2e6×1 #fff8eb×1 | 15 | 9 |
| 警告 | `--warn-line` | #f3d19e | #f3d19e | 0 | #f3d19e×10 #e8b86a×1 #c49c61×1 | 12 | 61 |
| 警告 | `--warn-line-soft` | #ead7b7 | #ecdcbe | 7 | #ead7b7×6 #e2d3b6×5 #ebdfc6×2 #efe1c3×1 #e9dfc9×1 #eddfc5×1 #eedecc×1 #e8d8b7×1 #ecdcbe×1 #efe0bf×1 #e7d5b4×1 #e6d5b4×1 | 22 | 14 |
| 警告 | `--warn-ink` | #7a6234 | #7a6234 | 0 | #7d6339×8 #7a6234×4 #6b5127×2 #7a5a26×1 | 15 | 17 |
| 危险 | `--danger` | #b34140 | #b34140 | 0 | #7b4f4f×1 | 1 | 56 |
| 危险 | `--danger-weak` | #fff0ef | #fff0ef | 0 | #ecdada×1 | 1 | 22 |
| 危险 | `--danger-line` | #f5c6c6 | #eac8c3 | 11 | #f5c6c6×9 #ebc4bf×3 #e7c4bf×1 #d9b3ae×1 #f1cfcf×1 #f2c9c9×1 #e7bdb8×1 #eac8c3×1 #e2bbb5×1 #dcb1ab×1 #e4c1bb×1 #f8dcd7×1 #e6c0b9×1 | 23 | 24 |
| 紫（次要标签） | `--purple` | #7357a0 | #7357a0 | 0 | #2457d6×1 #624d80×1 | 2 | 79 |
| 紫（次要标签） | `--purple-weak` | #f3eef9 | #f3eef9 | 0 | #eef1f5×2 #eef3f9×2 #eef2f6×1 #f0ecf6×1 | 6 | 5 |
| 侧栏（深墨） | `--rail` | 现状 | #192e28 | — | #142d32×1 #20362a×1 | 2 | 10 |
| 侧栏（深墨） | `--rail-hover` | 现状 | #243d34 | — | #284536×1 #213d2d×1 #25462e×1 | 3 | 9 |
| 侧栏（深墨） | `--rail-border` | #3a5a4a | #3a5a4a | 0 | #3d5545×3 #29484b×1 #38614c×1 #425449×1 #3a5a4a×1 #3e5546×1 | 8 | 18 |
| 侧栏（深墨） | `--rail-text` | 现状 | #e1eae4 | — | #dde8dc×1 #e8f0e4×1 #e2ebe1×1 #eaf3e4×1 | 4 | 9 |
| 侧栏（深墨） | `--rail-muted` | 现状 | #a5b9ae | — | #93a49a×2 #839c8d×1 #91ab9a×1 #91ad9b×1 #acb8b1×1 #aebfb2×1 #a3be97×1 #a7c69b×1 #a0c18b×1 | 10 | 35 |
| 侧栏（深墨） | `--rail-accent` | #b9d5aa | #bacdb3 | 9 | #b9d5aa×2 #b2c5b9×1 #c5ddb9×1 #bacdb3×1 #b4c9ab×1 #a9cfb7×1 #bbceba×1 #bcccb2×1 | 9 | 17 |
| 浮层 / 阴影 / 白色叠加 | `--overlay` | #12251ab3 | #12251ab3 | 0 | #12251ab3(α179)×4 #102515a3(α163)×1 | 5 | 5 |
| 浮层 / 阴影 / 白色叠加 | `--rail-tint` | — | #ffffff08 | — | #ffffff0a(α10)×1 #ffffff06(α6)×1 #ffffff08(α8)×1 | 3 | 0 |
| 浮层 / 阴影 / 白色叠加 | `--rail-line` | — | #ffffff17 | — | #ffffff20(α32)×2 #ffffff17(α23)×1 #ffffff30(α48)×1 #ffffff12(α18)×1 | 5 | 0 |
| 浮层 / 阴影 / 白色叠加 | `--shadow-tint` | — | #20372b0a | — | rgba(16,24,40,.08)(α20)×1 #087e7912(α18)×1 #21383104(α4)×1 #0000000a(α10)×1 #0f4c2810(α16)×1 #20372b08(α8)×1 #20372b0a(α10)×1 #20372b0f(α15)×1 | 8 | 78 |
| 浮层 / 阴影 / 白色叠加 | `--shadow-pop` | — | #10291a38 | — | #173b2426(α38)×2 #10291a38(α56)×2 #10291a40(α64)×1 #152c2133(α51)×1 | 6 | 18 |

合计：吸收字面量出现 389 次（234 个不同值）；组内最大 ΔRGB 见上表。

读表要点：
- `吸收条数` 是**出现次数**（同一字面量出现多次算多条），括号里的 `(αN)` 是 8 位 hex 的 alpha。
- `组内最大 ΔRGB` > 12 的令牌 = 该族里有存量值落在容差外，逐条在 [gaps.md](gaps.md) 的 A–G 分类表。
- 有 2 个令牌吸收 0 条：`--primary`、`--primary-hover`。它们仍被组件层以 `var()` 消费，值不动，保留。

## 3 与 §5.2 建议值的偏差、以及裁剪

### 3.1 新增令牌的值偏差（6 个；其余 10 个与 §5.2 完全一致）

| 令牌 | §5.2 建议 | 采用 | ΔRGB | 为什么动 |
|---|---|---|---|---|
| `--line-soft` | `#eef1f5` | `#d9ecde` | 23 | 存量「浅分隔线」是**绿温**（`#d9ecde/#dae5d2/#e0e8db/#e1eadb` ×15），不是 §5.2 猜的冷蓝白；取绿温中位色后 15/15 条进容差（用建议值只有 1 条） |
| `--text-2` | `#3d5545` | `#2f4a37` | 14 | 存量「次正文」聚在更暗一档（`#304b3d/#2f4a37/#304b35` …）；取中位色后 7/7 进容差 |
| `--ok-line` | `#bfe8d8` | `#cbe9d8` | 12 | 成功边框两种温度并存：青绿（`#bfe8d8/#cae9db`）与黄绿（`#c9dfc7/#c3dabc`）；取中位色兼顾，仍 5/8 |
| `--warn-line-soft` | `#ead7b7` | `#ecdcbe` | 7 | 存量都在 `#e9dfc9…#efe1c3`，比建议值更黄一档；11/12 进容差 |
| `--danger-line` | `#f5c6c6` | `#eac8c3` | 11 | 存量 `#ebc4bf/#eac8c3/#e7bdb8/#e2bbb5` 更灰（去饱和），取中位色 9/13 |
| `--rail-accent` | `#b9d5aa` | `#bacdb3` | 9 | 存量含 `#a0c18b…#c5ddb9` 一整个宽簇，中位色更居中（6/8） |

> 这 6 个偏差都在 §5.2 自己的方法内（「值为现有使用族的中位色」），不是换调色板；
> 但**是否接受这 6 个值**需要人裁：若坚持 §5.2 原值，`ΔRGB<=12` 的实色出现会从 305 掉到约 262（约 −43 条）。

### 3.2 没有采用的 6 个 §5.2 令牌（≤40 预算）

| 未采用 | §5.2 建议 | 折叠去向 | 代价 |
|---|---|---|---|
| `--surface-3` | `#f6f9f4` | 并入 `--surface-2`（两值 Δ7，合并后 26 条全在 ≤12） | 少一档「浅色块」语义；视觉 0 变化 |
| `--danger-line-soft` | `#ebc4bf` | 并入 `--danger-line`（两值 Δ10） | 弱/强危险描边共用一阶 |
| `--mono-bg` | `#20382b` | 并入 `--rail`（Δ10） | 日志块底 = 侧栏底色（本来就同族） |
| `--mono-text` | `#dde8dc` | 并入 `--rail-text`（Δ8） | 日志正文 = 深底正文 |
| `--purple-line` | `#e1d8ec` | **无去处**，落到 `--line`（Δ16–23） | 2 条紫边会被判 >12（gaps B） |
| `--rail-active` | `#304b3d` | **无去处**，落到 `--rail-hover`（Δ14） | 侧栏选中底色浅一档（gaps F） |

### 3.3 新增的 5 个「§5.2 之外」令牌（必须加，否则组件层不可能 0 字面量）

| 令牌 | 值 | 吸收 | 理由 |
|---|---|---|---|
| `--rail-tint` | `#ffffff08` | 白色遮罩 a6/a8/a10（3 条） | 深色侧栏上的白色叠加**必须带 alpha**，映射到任何不透明令牌都会把浅色叠加变实色 |
| `--rail-line` | `#ffffff17` | 白色描边 a18/a23/a32（4 条） | 同上，分隔线 |
| `--shadow-tint` | `#20372b0a` | 卡片阴影 a4–a15 + 一次彩色 glow（8 条） | 阴影色带 1.5%–6% alpha，用不透明令牌会把阴影变成实色边框 |
| `--shadow-pop` | `#10291a38` | 弹层阴影 a38–a64（4 条） | 窗口/浮层阴影 |
| `--overlay` | `#12251ab3` | `::backdrop` / `.modal` 遮罩（5 条） | §5.2 已有此令牌，此处确认其吸收范围 |

> `--text-3`（`#536e58`）也是 §5.2 之外的**第 6 个**新增：§5.2 的「字」只有 4 档（text/text-2/muted/faint），
> 但存量正文字族在 `#456a58…#62834c` 有一整档（23 条）任何现档位都 >12。加它是把 `Δ>12` 从 ~33 条压到 10 条的关键。

### 3.4 预算诚实账

- §5.2 表本身我数出来是 **41** 个令牌（底 5 + 线 3 + 字 4 + 主 4 + 成 3 + 警 5 + 危 4 + 紫 3 + 栏 7 + 浮层 3），**已超「≤40」1 个**。
- 本提案 = 40 = 既有 24 + 新增 16（§5.2 的 11 个 + §5.2 外 5 个，其中 `--text-3` 换掉 `--rail-active` 的位置，见 §3.2/§3.3）。
- 要「全收敛（0 条 >12）」需要 ~46 个令牌（把 §3.2 的 6 个补回来 + avatar 强调色 6 个）。三选一在 [gaps.md](gaps.md) §0。

## 4 alpha 面（8 位 hex / rgba：27 条出现）

| 令牌 | 值 | α 吸收范围 | 条数 | α 漂移 >12 的条目 |
|---|---|---|---|---|
| `--overlay` | `#12251ab3`（α179） | 163–179 | 5 | `#102515a3`（α163→179，+16，legacy `.modal`） |
| `--rail-tint` | `#ffffff08`（α8） | 6–10 | 3 | 无（≤2） |
| `--rail-line` | `#ffffff17`（α23） | 12–32 | 5 | `#ffffff30`（α48→23，−25，`.rail-entry:hover` 描边） |
| `--shadow-tint` | `#20372b0a`（α10） | 4–20 | 8 | 无（≤10）；其中 4 条的 RGB 主体与令牌差 21–78，但 α≤20/255 ⇒ 合成差 <1%，列 gaps A |
| `--shadow-pop` | `#10291a38`（α56） | 38–64 | 6 | `#173b2426`（α38→56，+18，`.toast`/`.toast-item` 阴影） |

α 漂移 ≤12 的 23 条视为可接受（≤4.7% 不透明度差）；4 条 >12 的列在 [gaps.md](gaps.md) §1（A 类），需人裁。

## 5 自检（可重跑，输出原样粘贴）

```bash
cd /home/work/chenjunming/change-impact-loop && UI3B_SNAP=1 python3 .ui-audit/3b/selfcheck.py
```

```
PASS  map.tsv 与 CSS 逐条一致：CSS 内 389 条色值出现 == map.tsv 389 行
PASS  unmapped=0（每条形如 file/line/property/literal 都有令牌）
PASS  map.tsv 用到的 38 个令牌全部在 tokens-proposed.css 有定义
PASS  颜色令牌数 = 40（上限 40，含既有 24）
PASS  全部变量 = 45（40 颜色 + --shadow/--radius/--ease-out/--font-*）
PASS  保持 color-scheme:light
PASS  无外部引用（0 个 url()/@import）

--- 覆盖（ΔRGB = max(|Δr|,|Δg|,|Δb|)，0-255 sRGB）---
色值出现总数 = 389；不同值（rgb+alpha）= 234
实色（非 alpha）出现 = 362，ΔRGB<=12 = 309（85.4%）
ΔRGB>12 出现 = 59 / 不同值 = 53
alpha 类出现 = 27（其 ΔRGB 不作判据，见 absorption.md 的 α 列）

--- 写权 ---
本次审计只写 .ui-audit/3b/；loop/web/**、loop/tests/**、doc/**、kb/** 未改动（见 handoff.md 的 git status 片段）

result: unmapped=0, all checks passed
```

自检覆盖：① CSS 内每一条色值出现 ↔ `map.tsv` 一行（双向相等，不只是计数相等）；② `unmapped=0`；
③ `map.tsv` 用到的每个令牌在 `tokens-proposed.css` 有定义；④ 颜色令牌数 = 40；⑤ `color-scheme:light`、
无 `url()`/`@import`；⑥ 覆盖统计。
