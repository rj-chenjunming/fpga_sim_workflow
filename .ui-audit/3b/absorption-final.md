# 3B 配色令牌化 · 吸收表（收口版 A · 行号已重钉）

> **基线（钉住的快照 `.ui-audit/3b/snap/`，= 当前工作树）**：
> `loop/web/app.css` md5 **`4d4a7867c397a77f81f1ad3814cebd08`** / **1015 行**；
> `loop/web/legacy.css` md5 `149153746ed1fa738b56aebea7db1e40` / 81 行；
> `loop/web/tokens.css` md5 `3d23134177964d8e2b2749a241f55a43` / 18 行。
> 3C（F14）已收口，批次 4 的 `.icon-30` 三条字面量已纳入本表；`map-final.tsv` 的行号就是这 1015 行文件的行号。

## 1 判据（裁决 A）

| 约定 | 取值 |
|---|---|
| ΔRGB | `max(|Δr|,|Δg|,|Δb|)`，0–255 sRGB 逐通道最大绝对差 |
| 实色 | ΔRGB **≤ 12**：**355/355 条全达标**（max = 12） |
| alpha 色 | 按**合成后颜色**判（合成到真实底色）：**27/27 条全达标**（max = 10） |
| 语义族 | 成功 / 警告 / 危险 / 紫 / 主色 / 头像身份色 各自独立；neutral（底/线/字/侧栏）内部共享 |
| 头像身份色 | `.a1–.a6` 一色一令牌（`--av-1…--av-6`），值 = 字面量本身 |
| 既有 24 个令牌 | 值**未动**；新增令牌的值为覆盖该簇的球心（字面量或两字面量中点） |
| 内联 | `legacy.html` 3 条活色各有令牌（`--arrow-ink` / `--toast-err` / `--toast-ok`），Δ 全 0 |
| 底色假设 | 白色叠加按 `--rail #192e28`；阴影/遮罩按页面底 `--bg #f4f6f5` |

## 2 每个令牌吸收了什么

| 组 | 令牌 | 值 | 吸收的字面量（归一化，次数） | 吸收条数 | 组内 max Δ |
|---|---|---|---|---|---|
| 底/线/字/侧栏 | `--arrow-ink` | #5a6675 | （内联专用；CSS 内 0 条） | 0 | 0 |
| 底/线/字/侧栏 | `--bg` | #f4f6f5 | #f6f9f4×8 #f5f8f1×5 #f8faf5×4 #eef1f5×2 #f6f9f3×2 #eef8f1×2 #eef3f9×2 #f2f4f7×1 #eceff4×1 #eef2f6×1 #edf2f1×1 #f3faf5×1 #f1f6f2×1 #edf2ee×1 #f3f6f3×1 #f0f4ed×1 #f2f7ef×1 #f4f7f1×1 #f7faf5×1 #f0f4ef×1 #f0ecf6×1 #f8eeee×1 #eef2ef×1 #f0f3f7×1 #eef7ee×1 #f2f6ee×1 #f6faf3×1 #f7f8f6×1 #f0f6f1×1 #f1f5ef×1 #f1f4ee×1 #f4f8f0×1 #f7faf3×1 | 51 | 10 |
| 底/线/字/侧栏 | `--faint` | #5f6f67 | （无吸收） | 0 | 0 |
| 底/线/字/侧栏 | `--line` | #e1e8e4 | #edf3e8×3 #d9ecde×2 #dae6df×1 #d7e6e1×1 #dce7da×1 #e1eadb×1 #e5ece9×1 #e6edea×1 #e2eadb×1 #eaf0e9×1 #dde5df×1 #e0e9db×1 #e0e8db×1 #dde8dc×1 #e0ecda×1 #e8eeea×1 #e2ebe1×1 #edf4e8×1 | 21 | 12 |
| 底/线/字/侧栏 | `--line-soft` | #d5e4d0 | #cbe9d8×1 #cae2c4×1 #d0ddcc×1 #dae5d2×1 #d9e7d6×1 #d1e5da×1 #d9e8d4×1 #cfdccb×1 #d6e3d8×1 #d4e0cc×1 #dae3d5×1 #d3dfcc×1 #d7e8d5×1 #dce8d7×1 | 14 | 12 |
| 底/线/字/侧栏 | `--line-strong` | #c7d4cc | #c7d4c8×3 #c4dfcc×2 #c4d1c7×1 #c9d4c3×1 | 7 | 11 |
| 底/线/字/侧栏 | `--muted` | #61746c | #617673×1 | 1 | 7 |
| 底/线/字/侧栏 | `--neutral-12` | #335541 | #3d5545×3 #34533c×2 #38614c×1 #36533d×1 #3a5a4a×1 #3e5546×1 | 9 | 12 |
| 底/线/字/侧栏 | `--neutral-13` | #284a40 | #29484b×1 #234b34×1 #304b3d×1 #284c35×1 #2f4a37×1 #304b35×1 | 6 | 12 |
| 底/线/字/侧栏 | `--neutral-4` | #a3be97 | #a3be97×1 #a7c69b×1 #a0c18b×1 | 3 | 12 |
| 底/线/字/侧栏 | `--panel` | #ffffff | #fff×39 #fcfdfb×9 #fcfdfc×3 #fffafa×2 #fbfcfe×1 #fefefe×1 | 55 | 5 |
| 底/线/字/侧栏 | `--rail` | #192e28 | #142d32×1 | 1 | 10 |
| 底/线/字/侧栏 | `--rail-accent` | #bed4b7 | #b7d2bf×1 #c1dcbd×1 #bbceba×1 | 3 | 8 |
| 底/线/字/侧栏 | `--rail-active` | #4e7052 | #4d6b4e×2 #456a58×1 #456e48×1 #54694b×1 #57764c×1 #50694b×1 | 7 | 10 |
| 底/线/字/侧栏 | `--rail-border` | #526f62 | #52716c×1 #58715f×1 | 2 | 10 |
| 底/线/字/侧栏 | `--rail-deep` | #495f48 | #496353×1 #425449×1 | 2 | 11 |
| 底/线/字/侧栏 | `--rail-hover` | #243d34 | #284536×1 #25462e×1 | 2 | 9 |
| 底/线/字/侧栏 | `--rail-muted` | #a5b9ae | #acb8b1×1 #aebfb2×1 | 2 | 9 |
| 底/线/字/侧栏 | `--rail-muted-2` | #b5cdb5 | #b9d5aa×2 #b2c5b9×1 #bacdb3×1 #b4c9ab×1 #a9cfb7×1 #bcccb2×1 | 7 | 12 |
| 底/线/字/侧栏 | `--rail-text` | #e1eae4 | #e1ede7×1 #eaf3e8×1 #e9f3ee×1 #e8f0e4×1 #eaf3e4×1 #edf5e7×1 | 6 | 12 |
| 底/线/字/侧栏 | `--surface` | #f8faf9 | #fbfdf9×5 #f9fbf7×2 #fafbfd×1 #fffdf7×1 #f8fafc×1 #f8faf6×1 #fafcf8×1 #f9fbf6×1 #f7faf7×1 #fafcfa×1 | 15 | 7 |
| 底/线/字/侧栏 | `--text` | #213831 | #20382b×2 #243a2b×2 #183d2e×1 #213d2d×1 #20362a×1 | 7 | 9 |
| 底/线/字/侧栏 | `--text-2` | #5d7756 | #5c7a59×2 #5d7756×1 #62834c×1 #5e7854×1 #5c7055×1 #5a6e52×1 | 7 | 12 |
| 底/线/字/侧栏 | `--text-3` | #517057 | #456761×2 #536e58×1 | 3 | 12 |
| 底/线/字/侧栏 | `--text-4` | #8aa393 | #93a49a×2 #839c8d×1 #91ab9a×1 #91ad9b×1 | 5 | 10 |
| 底/线/字/侧栏 | `--text-5` | #698872 | #718c7e×1 #728d7b×1 #60846a×1 #6b836a×1 | 4 | 12 |
| 主色 | `--primary` | #15775e | （无吸收） | 0 | 0 |
| 主色 | `--primary-hover` | #0e604b | （无吸收） | 0 | 0 |
| 主色 | `--primary-line` | #b8daca | （无吸收） | 0 | 0 |
| 主色 | `--primary-weak` | #eaf5ef | （无吸收） | 0 | 0 |
| 成功 | `--ok` | #24734d | （无吸收） | 0 | 0 |
| 成功 | `--ok-ink` | #148b68 | #148b68×2 | 2 | 0 |
| 成功 | `--ok-line` | #c9e4d1 | #bfe8d8×4 #cae9db×3 | 7 | 10 |
| 成功 | `--ok-line-2` | #c9dfc7 | #c9dfc7×1 #c3dabc×1 | 2 | 11 |
| 成功 | `--ok-weak` | #edf7ef | #e9f8f0×1 | 1 | 4 |
| 成功 | `--toast-ok` | #52c41a | （内联专用；CSS 内 0 条） | 0 | 0 |
| 警告 | `--warn` | #9a5e16 | （无吸收） | 0 | 0 |
| 警告 | `--warn-7` | #b98c43 | #ba914b×1 #b9873b×1 | 2 | 8 |
| 警告 | `--warn-8` | #745a30 | #7d6339×8 #7a6234×4 #6b5127×2 | 14 | 9 |
| 警告 | `--warn-accent` | #ecd3a9 | #f3d19e×8 | 8 | 11 |
| 警告 | `--warn-ink` | #c49c61 | #c49c61×1 | 1 | 0 |
| 警告 | `--warn-line` | #e6d9be | #ead7b7×6 #e2d3b6×5 #ebdfc6×2 #efe1c3×1 #eddfc5×1 #e9dfc9×1 #e8d8b7×1 #ecdcbe×1 #efe0bf×1 #e7d5b4×1 #e6d5b4×1 | 21 | 11 |
| 警告 | `--warn-line-3` | #c8dfbc | #c5ddb9×1 #d4e8c8×1 #c8dfbc×1 | 3 | 12 |
| 警告 | `--warn-line-4` | #e8b86a | #e8b86a×1 | 1 | 0 |
| 警告 | `--warn-tint` | #fffdf8 | #fffaf1×7 #fffdf8×3 #fffaf0×1 | 11 | 8 |
| 警告 | `--warn-weak` | #fff6e8 | #fbf7ef×2 #fdf0ef×2 #fff8ec×1 #fbf2e6×1 #fff8eb×1 | 7 | 7 |
| 危险 | `--danger` | #b34140 | （无吸收） | 0 | 0 |
| 危险 | `--danger-ink-soft` | #dab2ac | #d9b3ae×1 #e2bbb5×1 #dcb1ab×1 | 3 | 9 |
| 危险 | `--danger-line` | #f5d2d0 | #eedecc×1 #ecdada×1 #f1cfcf×1 #f8dcd7×1 | 4 | 12 |
| 危险 | `--danger-line-soft` | #ebc7c4 | #f5c6c6×7 #ebc4bf×3 #e7c4bf×1 #f2c9c9×1 #e7bdb8×1 #eac8c3×1 #e4c1bb×1 #e6c0b9×1 | 16 | 12 |
| 危险 | `--danger-weak` | #fff0ef | （无吸收） | 0 | 0 |
| 危险 | `--toast-err` | #ff4d4f | （内联专用；CSS 内 0 条） | 0 | 0 |
| 紫 | `--purple` | #7357a0 | （无吸收） | 0 | 0 |
| 紫 | `--purple-line` | #e0d4ec | #e1d8ec×1 #dfd1ed×1 | 2 | 4 |
| 紫 | `--purple-weak` | #f3eef9 | （无吸收） | 0 | 0 |
| 元信息蓝 | `--meta-blue` | #44607a | #44607a×2 | 2 | 0 |
| 头像 | `--av-1` | #2457d6 | #2457d6×1 | 1 | 0 |
| 头像 | `--av-2` | #3c7465 | #3c7465×1 | 1 | 0 |
| 头像 | `--av-3` | #7a5a26 | #7a5a26×1 | 1 | 0 |
| 头像 | `--av-4` | #624d80 | #624d80×1 | 1 | 0 |
| 头像 | `--av-5` | #7b4f4f | #7b4f4f×1 | 1 | 0 |
| 头像 | `--av-6` | #55684f | #55684f×3 | 3 | 0 |
| 浮层/阴影 | `--overlay` | #12251aab | #12251ab3(α179)×4 #102515a3(α163)×1 | 5 | 7 |
| 浮层/阴影 | `--rail-line` | #ffffff17 | #ffffff20(α32)×2 #ffffff17(α23)×1 #ffffff12(α18)×1 | 4 | 8 |
| 浮层/阴影 | `--rail-line-strong` | #ffffff30 | #ffffff30(α48)×1 | 1 | 0 |
| 浮层/阴影 | `--rail-tint` | #ffffff08 | #ffffff0a(α10)×1 #ffffff06(α6)×1 #ffffff08(α8)×1 | 3 | 2 |
| 浮层/阴影 | `--shadow-pop` | #10291a38 | #10291a38(α56)×2 #10291a40(α64)×1 #152c2133(α51)×1 | 4 | 7 |
| 浮层/阴影 | `--shadow-raise` | #173b2426 | #173b2426(α38)×2 | 2 | 0 |
| 浮层/阴影 | `--shadow-tint` | #20372b0a | rgba(16,24,40,.08)(α20)×1 #087e7912(α18)×1 #21383104(α4)×1 #0000000a(α10)×1 #0f4c2810(α16)×1 #20372b08(α8)×1 #20372b0a(α10)×1 #20372b0f(α15)×1 | 8 | 10 |

## 3 令牌计数自检

| 项 | 数 |
|---|---|
| 颜色令牌合计 | **69** = 既有 24 + 新增语义 29 + alpha 7 + 头像 6 + 内联专用 3 |
| 其中纯 CSS 侧 | 66（内联专用 3 个不在 `app.css`/`legacy.css` 里吸收任何条） |
| 非颜色令牌（原样） | 5（`--shadow`/`--radius`/`--ease-out`/`--font-sans`/`--font-mono`） |
| `tokens-final.css` 变量总数 | 74 |
| 吸收的色值出现 | **382** 条 / **233** 个不同值（rgb+alpha） |
| 实色 Δ≤12 | 355 / 355（100%，max 12） |
| alpha 合成后 Δ≤12 | 27 / 27（100%，max 10） |
| 内联 3 条 | 3 / 3（Δ 0） |

> **为什么不是 46–50**：233 个不同值里，24 个冻结既有令牌在 Δ≤12 下只覆盖一部分；余下按「同族 + 半径 12」
> 最少需 29 个新令牌，再加 7 alpha + 6 头像 + 3 内联。压缩曲线（实测，见 gaps-final §2）：
> 65 令牌 → 3 条例外、60 → 11 条、55 → 26 条、50 → 45 条。**69 是「全部 ≤12」的实测解**。

> **本轮相对上一版的差异（3C 收口 + 批次 4）**：色值出现 389 → **382**（删掉的 3 条 `.empty:before` /
> `.aw-detail summary:before` / `.aw-detail[open] summary:before` 带走 10 条，批次 4 的 `.icon-30` 新增 3 条）；
> CSS 侧令牌 67 → **66**（`#60846a` 那簇并入 `--text-5`，少一个球）；另按裁决为 3 条内联色加了 3 个令牌 → 总 **69**。
> 批次 4 的 3 条新字面量：`#d6e3d8 → --line-soft`（Δ8）、`#f0f6f1 → --bg`（Δ4）、`#60846a → --text-5`（Δ9）。

> **吸收 0 条但仍保留的令牌**：`--primary` `--primary-hover` `--primary-weak` `--primary-line` `--ok` `--warn`
> `--danger` `--danger-weak` `--purple` `--purple-weak` `--faint`（既有 24 的一部分，组件层仍 `var()` 消费，删了破坏引用）；
> 以及内联专用的 `--arrow-ink` `--toast-err` `--toast-ok`（只服务 `legacy.html` 的 3 条活内联，不在两个 CSS 文件里出现）。

## 4 alpha 表（合成后颜色对比，不豁免）

| 字面量 | α | 令牌 | 令牌 α | 合成底 | 合成后（原值 → 令牌） | Δ | 位置 |
|---|---|---|---|---|---|---|---|
| `rgba(16,24,40,.08)` | 20 | `--shadow-tint` | 10 | bg(#f4f6f5) | (226,229,229) → (236,239,237) | 10 | app.css:39 box-shadow |
| `#087e7912` | 18 | `--shadow-tint` | 10 | bg(#f4f6f5) | (227,238,236) → (236,239,237) | 9 | app.css:226 box-shadow |
| `#ffffff0a` | 10 | `--rail-tint` | 8 | rail(#192e28) | (34,54,48) → (32,53,47) | 2 | app.css:236 border-bottom |
| `#21383104` | 4 | `--shadow-tint` | 10 | bg(#f4f6f5) | (241,243,242) → (236,239,237) | 5 | app.css:276 box-shadow |
| `#ffffff20` | 32 | `--rail-line` | 23 | rail(#192e28) | (54,72,67) → (46,65,59) | 8 | app.css:279 box-shadow |
| `#ffffff06` | 6 | `--rail-tint` | 8 | rail(#192e28) | (30,51,45) → (32,53,47) | 2 | app.css:296 background |
| `#ffffff17` | 23 | `--rail-line` | 23 | rail(#192e28) | (46,65,59) → (46,65,59) | 0 | app.css:296 border-color |
| `#ffffff30` | 48 | `--rail-line-strong` | 48 | rail(#192e28) | (68,85,80) → (68,85,80) | 0 | app.css:297 border-color |
| `#0000000a` | 10 | `--shadow-tint` | 10 | bg(#f4f6f5) | (234,236,235) → (236,239,237) | 3 | app.css:301 box-shadow |
| `#ffffff08` | 8 | `--rail-tint` | 8 | rail(#192e28) | (32,53,47) → (32,53,47) | 0 | app.css:322 background |
| `#ffffff20` | 32 | `--rail-line` | 23 | rail(#192e28) | (54,72,67) → (46,65,59) | 8 | app.css:322 border-color |
| `#ffffff12` | 18 | `--rail-line` | 23 | rail(#192e28) | (41,61,55) → (46,65,59) | 5 | app.css:325 border-top-color |
| `#0f4c2810` | 16 | `--shadow-tint` | 10 | bg(#f4f6f5) | (230,235,232) → (236,239,237) | 6 | app.css:342 box-shadow |
| `#20372b08` | 8 | `--shadow-tint` | 10 | bg(#f4f6f5) | (237,240,239) → (236,239,237) | 2 | app.css:453 box-shadow |
| `#20372b0a` | 10 | `--shadow-tint` | 10 | bg(#f4f6f5) | (236,239,237) → (236,239,237) | 0 | app.css:487 box-shadow |
| `#173b2426` | 38 | `--shadow-raise` | 38 | bg(#f4f6f5) | (211,218,214) → (211,218,214) | 0 | app.css:490 box-shadow |
| `#10291a38` | 56 | `--shadow-pop` | 56 | bg(#f4f6f5) | (194,201,197) → (194,201,197) | 0 | app.css:493 box-shadow |
| `#12251ab3` | 179 | `--overlay` | 171 | bg(#f4f6f5) | (85,99,91) → (92,106,98) | 7 | app.css:494 background |
| `#20372b0f` | 15 | `--shadow-tint` | 10 | bg(#f4f6f5) | (232,235,233) → (236,239,237) | 4 | app.css:538 box-shadow |
| `#10291a38` | 56 | `--shadow-pop` | 56 | bg(#f4f6f5) | (194,201,197) → (194,201,197) | 0 | app.css:546 box-shadow |
| `#12251ab3` | 179 | `--overlay` | 171 | bg(#f4f6f5) | (85,99,91) → (92,106,98) | 7 | app.css:547 background |
| `#12251ab3` | 179 | `--overlay` | 171 | bg(#f4f6f5) | (85,99,91) → (92,106,98) | 7 | app.css:755 background |
| `#10291a40` | 64 | `--shadow-pop` | 56 | bg(#f4f6f5) | (187,195,190) → (194,201,197) | 7 | app.css:757 box-shadow |
| `#12251ab3` | 179 | `--overlay` | 171 | bg(#f4f6f5) | (85,99,91) → (92,106,98) | 7 | app.css:824 background |
| `#173b2426` | 38 | `--shadow-raise` | 38 | bg(#f4f6f5) | (211,218,214) → (211,218,214) | 0 | legacy.css:64 box-shadow |
| `#102515a3` | 163 | `--overlay` | 171 | bg(#f4f6f5) | (98,112,102) → (92,106,98) | 6 | legacy.css:65 background |
| `#152c2133` | 51 | `--shadow-pop` | 56 | bg(#f4f6f5) | (199,206,203) → (194,201,197) | 6 | legacy.css:66 box-shadow |

## 5 自检输出（`UI3B_SNAP=1 python3 .ui-audit/3b/selfcheck_final.py`）

```
PASS  map-final.tsv 与 CSS 逐条一致（382 条色值 / 382 行）
PASS  unmapped=0
PASS  final-design 的 69 个令牌 == tokens-final.css 的 69 个颜色令牌
PASS  颜色令牌数 = 69
PASS  全部变量 = 74（= 颜色 69 + --shadow/--radius/--ease-out/--font-*）
PASS  保持 color-scheme:light、零外部引用
PASS  实色 ΔRGB<=12：355 / 355 条（max=12）
PASS  alpha 合成后 Δ<=12：27 / 27 条（max=10）
PASS  legacy.html 3 条活内联色全部映射且 ΔRGB<=12（--arrow-ink/--toast-err/--toast-ok）
      内联活规则行号: [127, 156, 157]
      令牌构成: {'neutral': 26, 'primary': 4, 'ok': 6, 'warn': 10, 'danger': 6, 'purple': 3, 'blue': 1, 'alpha': 7, 'av': 6}
      基线 md5: app.css 4d4a7867 / legacy.css 14915374（与当时工作树一致：True）

unmapped=0
max ΔRGB(实色)=12
alpha 合成后 max Δ=10
tokens=69（颜色；+5 非颜色 = 74 个变量）
result: all checks passed
```
