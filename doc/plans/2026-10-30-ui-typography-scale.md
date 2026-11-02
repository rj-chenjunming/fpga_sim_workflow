# 2026-10-30 UI 字号阶梯落地（批次 3A）执行计划

> 上游：[`doc/audit/AUDIT-20261030-ui-design.md`](../audit/AUDIT-20261030-ui-design.md) A-02/A-03/B-05/B-06/D-06；
> 批次 1+2 已完成（`doc/STATUS.md` §140）。本切片只做**字号口径**，不碰颜色令牌化与 F14 合并（批次 3B/3C）。

## 1 目标（可判定）

| 目标 | 判据 |
|---|---|
| H1 字号表入规格 | `WEB_UI_SPEC.md` §14 列出完整阶梯与例外；§10 A14 给出判定方式 |
| H2 组件层只用阶梯值 | 静态用例扫描 `loop/web/{app.css,legacy.css,index.html,legacy.html}` 的每个 `font-size`/`font` 简写 px 值，必须 ∈ 阶梯；扫描数 ≥300（防空扫） |
| H3 无视觉坍塌 | 浏览器全量（含三视口无水平溢出）+ 首屏 A12 仍成立；截图为证 |
| H4 可读性不退化 | 说明文字 ≥12px 维持（§14:825）；对比度不回退（颜色未改，字号变大不改对比度） |

## 2 契约变更（先于实现）

**§14 新增「字号阶梯（2026-10-30 增补）」**（替换原「稳定字号阶梯」的模糊表述，保留 13–14px 正文/表单口径）：

| 阶梯 | 用途 | 说明 |
|---|---|---|
| 10px / 11px | 标签与图示注释 | 仅 eyebrow、序号、图注、tag、极短标识；**不得承载唯一关键信息** |
| 12px | 说明文字 | 与 §14:825 一致（原口径不变） |
| 13px | 紧凑正文 / 表单 | 表格、密集列表、次要行 |
| 14px | 正文 / 表单 | 与 §14:825 一致（原口径不变） |
| 16px | 卡片标题 / 主按钮 / 小节标题 | 原 `15/15.5/17` 收敛到此 |
| 18px | 面板标题 | 原 `19` 收敛到此 |
| 20px | 弹窗标题 / 品牌 / 大数字 | 原 `21/22` 收敛到此 |
| 24px | 页面标题（h1） | 原 `27` 已在此 |
| 30px / 36px | 展示数字与大标题 | 原 `29/31` 收敛到 30 |

**§10 新增 A14**：字号只取 §14 阶梯（组件层 CSS/内联样式），由 `tests/test_ui_typography.py` 静态扫描判定；新增字号必须先改 §14。

## 3 映射表（旧 → 新，脚本唯一口径）

```
7,8,9,9.5 → 10     10 → 10     10.5 → 11
11 → 11            11.5 → 12   12 → 12      12.5 → 12
13 → 13            13.5 → 14   14 → 14
15,15.5,16,17 → 16 18 → 18     19 → 18
20 → 20            21,22 → 20  24 → 24
29,31 → 30         36 → 36     ≥40 → 36（仅用于展示数字）
```

覆盖范围：`loop/web/app.css`（317 处）、`loop/web/legacy.css`（13 处）、`loop/web/legacy.html` 内联样式（26 处）。
**不做**：`mockup.html`（§14 静态历史样张不重绘）、`loop/web/*.js` 中 JS 设置的字号（无，实测仅 CSS/HTML）。

## 4 切片与写权

| 切片 | 内容 | 写者 | 范围 |
|---|---|---|---|
| S0 契约 | §14 字号表、§10 A14、本计划 | Lead | `doc/spec/WEB_UI_SPEC.md`、`doc/plans/` |
| S0 用例 | 先失败静态守卫 | Lead | `loop/tests/test_ui_typography.py` |
| S1 实现 | 按 §3 映射吸附字号 | Lead | `loop/web/app.css`、`legacy.css`、`legacy.html` |
| S2 验收 | 门 + 截图 + 复核 + STATUS | Lead + 独立复核 | `doc/STATUS.md`、`doc/evidence/UI_TYPOGRAPHY_20261030/` |

## 5 验证门

1. 新用例先红后绿：`cd loop && .venv/bin/python -m pytest -q tests/test_ui_typography.py`（先红：25 个不同字号）。
2. 软件层：`bash spikes/run_software_checks.sh --ignore=tests/browser -q`。
3. 浏览器全量：`PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… .venv/bin/python -m pytest -q tests/browser`（预期 178 passed）。
4. 接口契约：A12 首屏用例（首屏高度可能 +几像素，需复跑确认）。
5. 文档：`python3 doc/audit/check_doc_links.py`（`missing=0`）。
6. 截图：三视口 + 关键弹层，人工目检字号层级（写入证据目录）。

## 6 回滚

只改 CSS/HTML 字号数值，`git revert` 单提交即可；无数据/契约副作用。

## 7 不在本切片

- 批次 3B 颜色令牌化（401 处 hex → tokens）与 3C F14 两段式合并。
- 批次 4：图标 sprite、GATE-1↔G1 映射、闸门 `--gate-pane-max-h` 常数（后两项需人裁）。
- 间距/圆角收敛（§14 无表，未定）。

---

## 8 执行记录（2026-10-30）

**状态**：H1–H4 达成。证据：[`doc/evidence/UI_TYPOGRAPHY_20261030/`](../evidence/UI_TYPOGRAPHY_20261030/README.md)。

| 目标 | 结果 |
|---|---|
| H1 字号表入规格 | §14 新增「字号阶梯（2026-10-30 增补）」11 档；§10 新增 A14 |
| H2 只用阶梯值 | `tests/test_ui_typography.py` 先红（首轮 `2 failed, 1 passed` 含用例自身缺陷；修正后 `1 failed`，16 个阶外 / 25 个不同字号）后绿（`3 passed`）；扫描 **355** 处声明（≥300 防空扫） |
| H3 无视觉坍塌 | 浏览器全量 `178 passed in 208.71s`（含三视口无水平溢出与 A12 首屏） |
| H4 可读性不退化 | 说明文字仍 ≥12px（11.5→12 是放大）；颜色未改，对比度不变 |

**实现**：按 §3 映射脚本吸附 **124 处**声明（其中 3 处落在此前 T3 未提交声明上，按 `git diff` 可归属本轮 121 处；`app.css` 25→10 个不同字号、`legacy.css` 4→3、`legacy.html` 8→5）；
`mockup.html` 未动（§14 静态历史样张）。软件层 `2002 passed, 3 deselected in 274.98s`（新增 3 条字号守卫）。

**独立复核处置**（`ui-typography-verifier`，报告 `.ui-audit/F-typography-verify.md`，结论「可合入，无 P0/P1」）：
- P2-2/2-3/2-4 守卫加固：剥离 CSS/HTML 注释、px 大小写不敏感、`font:` 简写与 `%`/`em`/`rem` 相对单位、规格解析限定 §14 bullet 并交叉校验 §10 A14（副本注入实测：大写 `11.5PX` 判红、`font:1.1em` 判红、`font-size:90%` 判红、注释内旧值不计）。
- P2-5 主区状态类文字 11→12px（`.status-pill`、`.s0-checks b`、`.s0-flow .flow-status`），§14 补一句「10/11 仅用于标签、图注、序号与密集侧栏元信息」。
- P2-6 数字口径按复核更正：脚本 124 / 可归属 121、扫描 355、先红为「16 个阶外 / 25 个不同字号」且原始日志未落档。
- P2-1：`.phase-index` 16→14 属批次 1+2 的字号变化，已在 `doc/STATUS.md` §140.2 补记。

**偏差/未做**：
- 阶梯里 `36px` 暂无消费者（保留档位，供展示数字/大标题用）。
- 间距、圆角仍未收敛（§14 无表）；颜色令牌化（3B）与 F14 合并（3C）不在本切片。
