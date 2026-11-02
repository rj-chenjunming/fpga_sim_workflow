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

TABLE_ABSORPTION

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
> `--danger` `--danger-weak` `--purple` `--purple-weak`（既有 24 的一部分，组件层仍 `var()` 消费，删了破坏引用）；
> 以及内联专用的 `--arrow-ink` `--toast-err` `--toast-ok`（只服务 `legacy.html` 的 3 条活内联，不在两个 CSS 文件里出现）。

## 4 alpha 表（合成后颜色对比，不豁免）

TABLE_ALPHA

## 5 自检输出（`UI3B_SNAP=1 python3 .ui-audit/3b/selfcheck_final.py`）

CHECK_OUTPUT
