# 3B 配色令牌化 · 实现者交接（handoff）

> 执行清单，不是设计文档。依据见 [absorption.md](absorption.md)，不能收敛项见 [gaps.md](gaps.md)。

## 0 开工前（必做）

```bash
cd /home/work/chenjunming/change-impact-loop && bash .ui-audit/3b/rescan.sh
```
3C 仍在写 `app.css`（本审计期间 1213→1173→1149→1218 行）。`rescan.sh` 重钉快照并重算 `map.tsv` / `map-values.tsv` / `selfcheck.out`。
**若 `snap/MD5SUMS.txt` 与本目录 `absorption.md` 记录的 md5 不同，以重跑结果为准**（值级映射不变，只有行号变）。

## 1 顺序（先令牌，后组件；不可反过来）

1. **`loop/web/tokens.css`** ← [tokens-proposed.css](tokens-proposed.css) 的 `:root{}`：40 个颜色令牌 + 原样保留
   `--shadow/--radius/--ease-out/--font-*`（共 45 个变量，保持 `color-scheme:light`）。`--shadow` 内的 `#20372b03` 在令牌文件内，允许保留。
2. **`loop/web/app.css`**：按 §5.2 组顺序替换 —— 底 → 线 → 字 → 主色 → 成功 → 警告 → 危险 → 紫 → 侧栏 → 浮层。
   逐条按 [map.tsv](map.tsv)（文件/行号/属性/现值/令牌/Δ；同一行多色分行给出）。
3. **`loop/web/legacy.css`**：同样按 `map.tsv`（59 条）。
4. **`loop/web/legacy.html`**：只有 3 条活着的内联色（L127 `.chain-arrow`、L156 `.toast-item.err`、L157 `.toast-item.ok`），
   建议换 `var(--muted)` / `var(--danger)` / `var(--ok)`（gaps §2 D4）。其余 155 条是死声明，本批不动。
5. 每步后先跑静态守卫（§4）再跑门（§5）；只改颜色值，`transparent`（20 处）/`none`/`inherit`/`auto` 保留。

## 2 完成判据

| 判据 | 期望 |
|---|---|
| 组件层字面量 | `app.css` + `legacy.css` 内 `#hex`/`rgb()`/`rgba()` = **0**（`tokens.css` 除外） |
| 令牌数 | 颜色令牌 **40**（含既有 24）；全部变量 45；`var(--x)` 未定义 = 0 |
| 色差 | 实色 309/362（85.4%）ΔRGB≤12；余 59 条按 gaps D6 决策 |
| 不受影响 | 选择器结构不变（`test_ui_css_structure.py` 仍绿）、`:active`/`text-wrap` 仍在 |

## 3 会受影响的既有测试（只读查看后列出，未运行）

| 测试 | 受影响原因 | 处置 |
|---|---|---|
| `browser/test_ui_visual_20261030.py::test_informational_text_meets_aa` | 10 个选择器实测对比度，阈值 4.5，会随令牌值移动 | 必跑；跌破则回退该令牌值或加 `--text-4`（gaps D6） |
| `…::test_run_view_informational_text_meets_aa` | 探针含 `.stage-idx`/`.agent-role`/**`.avatar.a3.a4.a5`** | 风险最高（`#7b4f4f→--danger` Δ56、`#624d80→--purple` Δ32）⇒ 跌破走 gaps D3 加 `--av-*` |
| `…::test_placeholder_text_meets_aa` | `#s0Rtl::placeholder` 前景/背景都变 | 必跑 |
| `…::test_focus_ring_contrast` | 焦点环对底 ≥3；`--primary` 未动 | 必跑确认 |
| `…::test_tokens_and_motion_contract` | 静态断言 tokens.css 无 `Inter`/`@font-face`/`url(`、有 `cubic-bezier(0.22,1,0.36,1)` 与 `--ease-out` | 提案已满足；别在 tokens.css 写 `url(` |
| `loop/tests/test_web_smoke.py` | 断言 app.css 含 `.diff-item`/`.gate-entry` | 只换色值不影响 |
| `loop/tests/browser/test_node_detail.py:1623` | 断言 app.css 不含 `entry-decisions-sample` | 不新增该类名即可 |
| `loop/tests/test_ui_typography.py` | **无颜色断言**（只查字号 11 档） | 不因 3B 重跑 |
| `loop/tests/test_ui_css_structure.py`（3C 新增） | 同一简单选择器只定义一次 | 令牌化不加规则块 ⇒ 应保持绿 |

## 4 必须新增的守卫（§5.3，建议 `loop/tests/test_ui_tokens.py`）

- `app.css`+`legacy.css` 内 `#hex|rgb(|rgba(|hsl(` 计数 = **0**，且扫描数 ≥300（防空扫）；
- 每个 `var(--x)` 在 `tokens.css` 有定义；颜色令牌数 ≤40；
- `tokens.css` 仍含 `color-scheme:light`，无 `@font-face`/`url(`；`selfcheck.py` 是同口径只读实现，可直接借断言。

## 5 门命令

```bash
cd loop && PLAYWRIGHT_BROWSERS_PATH=$PWD/../.pw-browsers HOME=$PWD/../.chrome-home \
  TMPDIR=$PWD/../.chrome-tmp .venv/bin/python -m pytest -q tests/browser
cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser -q
python3 doc/audit/check_doc_links.py
```
