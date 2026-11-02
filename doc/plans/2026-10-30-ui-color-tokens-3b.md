# UI 批次 3B · 配色令牌化（`tokens.css` 唯一色源）· 计划

> 来源：[`doc/agents/开工提示词_UI批次3C与3B.md`](../agents/开工提示词_UI批次3C与3B.md) §5（§5.1 目标 / §5.2 调色板 / §5.3 验收）
> + [`doc/audit/AUDIT-20261030-ui-design.md`](../audit/AUDIT-20261030-ui-design.md) D-04（配色令牌形同虚设）。
> 前置：批次 3C（F14 两段式合并）已收口——**先合并再令牌化**，否则换的值会被后段覆盖。

| 项 | 内容 |
|---|---|
| 类型 | A 类（规格 §14「颜色来源」已要求，属实现未落地）+ 一次**已获人裁的色值收敛** |
| 实现 owner | Lead 指派的实现 owner（`loop/web/{tokens.css,app.css,legacy.css,legacy.html}` 单写者） |
| 允许修改 | `loop/web/{tokens.css,app.css,legacy.css,legacy.html}`、新增 `loop/tests/test_ui_tokens.py`、本计划、`doc/STATUS.md`（Lead）、`doc/evidence/UI_COLOR_TOKENS_20261030/`（只增） |
| 不修改 | `loop/web/{index.html,app.js,s0.js,node-detail.js,favicon.svg}`（本切片不动结构）、`mockup.html`（§14 静态历史样张）、`kb/**`、`loop/services|host|workflows/**`、任何既有测试的判据 |
| 回滚 | 不做 git 回滚；`app.css`/`legacy.css`/`legacy.html`/`tokens.css` 改前快照存 `.ui-audit/3b-impl/snap-before/`，回滚=按快照覆盖 |

## 1 人裁记录（决策 + 偏差）

| 事项 | 裁决 | 结果 |
|---|---|---|
| 调色板是否接受 §5.2（≤12 RGB 合并） | **接受**（选项 A） | 按「每条字面量到其令牌 ΔRGB ≤12」执行 |
| 令牌预算 | 人裁「提到 46–50 个，保 ≤12」 | **实际 69 个（颜色）+ 5 个非颜色**。**偏差必须登记**：几何上不可兼得——213 个不同实色值里，既有 24 个冻结令牌在 Δ≤12 下只覆盖 104 个；余下 109 个按「同族 + 半径 12」最少需 29 个新语义令牌 + 7 alpha + 6 avatar + 3 内联专用。压缩曲线（实测）：**65→3 条例外、60→11、55→26、50→45**（数字见 `.ui-audit/3b/gaps-final.md` §2）。人裁的**硬意图是「保 ≤12」**，令牌数是估计值；按判据优先取 69，并把压缩曲线留在证据里供回退决策 |
| 是否允许超 40（原 §5.2 目标） | 人裁已明确放宽到 46–50；实际 69 超出估计 19 个，**需在 STATUS 与本表并列如实说明** | 同上 |
| 内联样式 | 只处理仍生效的 3 条（`legacy.html` 的 `.chain-arrow` / `.toast-item.err` / `.toast-item.ok`）；其余 155 条为死声明，不动 | 3 条各配专用令牌（`--arrow-ink`/`--toast-err`/`--toast-ok`，Δ0），标 `inline_only`，不参与吸收 CSS 字面量 |

## 2 验收判据

| 判据 | 方式 | 目标 |
|---|---|---|
| 令牌唯一色源 | 新增 `loop/tests/test_ui_tokens.py`（软件层） | `app.css`+`legacy.css` 内 hex/rgb/rgba/hsl 字面量 = **0**；`legacy.html` 的**活**样式 = 0（155 条死声明白名单并注明理由）；每个 `var(--x)` 在 `tokens.css` 有定义；颜色令牌 = 69；扫描数 ≥300 |
| 色差不超 12 | `.ui-audit/3b/selfcheck-final.txt`（值级自检，实现前冻结） | 实色 355/355 Δ≤12（max **12**）；alpha 合成后 27/27 Δ≤12（max **10**）；unmapped **0** |
| 令牌数量 | 同上 | 69 颜色 + 5 非颜色 = 74 变量（**偏差已登记**，见 §1） |
| 可读性不回退 | 复跑 `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py`（受控夹具；用 `.ui-audit/measure.py` 以免写冻结证据） | S0/gate/monitor 非装饰文本 `<4.5` 仍为 3/4/4（与本轮基线 3/194、4/173、4/238 一致，且失败项仍只含装饰 `/` 与禁用控件）；焦点环 ≥3（基线 5.48/9.0） |
| 视觉可接受 | 三视口截图（前后）人工目检 | 由人确认 ≤12 色差不可辨；本轮提供前后截图 |
| 功能 | 浏览器门 + 软件层门 + 文档门 | 0 failed；文档 `missing=0` |

## 3 方法与证据

- 设计输入（只读分析员交付，`.ui-audit/3b/`）：`tokens-final.css`（69 令牌）、`map-final.tsv`（382 条逐项）、
  `map-values-final.tsv`（233 条值级）、`absorption-final.md`（逐令牌吸收清单 + alpha 合成表）、`gaps-final.md`、`selfcheck-final.txt`。
- 实现先写红（`test_ui_tokens.py` 报「组件层仍有 382 处字面量」）→ 再改 `tokens.css` → 再逐文件替换 → 绿。
- 证据目录 `doc/evidence/UI_COLOR_TOKENS_20261030/`：before/after `app.css`/`legacy.css`/`tokens.css` 的 md5、
  替换计数、`test_ui_tokens.py` 红/绿原始输出、measure.py 前后对比、三视口截图。

## 4 未做 / 不声称

- **不为「≤40 令牌」而牺牲 ≤12**：69 个令牌是判据优先的结果，破原目标已登记（§1）。
- **不动 155 条死声明**（`legacy.html` 内联 `<style>`）：它们不生效，清退属独立结构清理。
- **不改 `mockup.html`**（§14 静态历史样张不重绘）。
- **暗色主题 / 非 Chromium / 真机滚动条**：未验证，不声称。
- **hover / active 的视觉**仍只有计算样式覆盖（同 3C 口径），不做逐态截图。
