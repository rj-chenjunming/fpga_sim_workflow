# UI 批次 3C · F14 两段式 CSS 合并 · 证据（2026-10-30）

> **只增不改**。本目录是 [`doc/STATUS.md`](../../STATUS.md) §142（UI 批次 3C）与
> [`doc/plans/2026-10-30-ui-css-merge-f14c.md`](../../plans/2026-10-30-ui-css-merge-f14c.md) 的证据附录。
> **结论口径**：本切片只声称「**元素级计算样式零差异 + 结构按预期收敛**」；
> **不**声称「视觉完全不变」（hover/active 只由计算样式与断点扫描间接覆盖，见 §5）。

## 1 改前 / 改后

| 项 | 改前（pristine） | 改后（3C 产物） |
|---|---|---|
| 文件 | `raw/app-before-3c.css` | `raw/app-after-3c.css` |
| md5 | `103ec75124e21c6c97a717d7607fa132` | `73430cb2b6b16d74b74a0e30dc3643ad` |
| 行数 | 1213 | 1008 |
| 顶层样式规则 | 917 | 791 |
| 解析规则（含 @media 内） | 1160 | 974 |
| 规则实例（浏览器 `cssRules`，含 at-rule 块 26 条） | 943 | 817 |
| 不同选择器文本 | 792 | 792（未改选择器语义） |
| **同（选择器, @上下文）被 ≥2 条规则定义** | **193**（顶层 178 / @760 14 / @850 1） | **23**（全部为白名单例外，见 §3） |
| 组件层颜色字面量 | 389 处 / 234 值 | 同 3C 前（3B 才做令牌化） |

> 改后 `loop/web/app.css` 在此之后又叠加了**批次 4** 的 6 处改动与**3B** 的配色令牌化
> （当前 md5 `d75422b5…`）。本目录的 `app-after-3c.css` 是 **3C 的定格产物**，
> 3C 的「值逐字未变 / @media 条件未变 / 零计算样式差异」都以它为口径。

## 2 门（原始输出在本目录 `raw/`）

| 门 | 文件 | 实测 |
|---|---|---|
| 结构守卫**先红**（修正解析器后对 pristine） | `raw/red-test-pristine.txt` | 简单选择器实例 1156 / 重复组 **193**（非白名单 190） |
| 结构守卫**先红**（首轮、解析器未修，仅历史留档） | `raw/red-test-01.txt` | 178（少算：`@media(...)` 无空格写法整块被漏扫，见计划 §2.5） |
| 结构守卫**后绿** | STATUS §142 | `2 passed`（白名单 23 条 + 陈旧条目检测） |
| 逐批指纹（13 批 × 24 组合） | `raw/batches.log` | 每批 `PASS`（计算样式指纹 0 差异） |
| **全断点指纹 196 组合**（主视口真实高度 + 50 断点宽度 ×2 状态 + agent 窄断点 + legacy + 10 focus + 5 hover + node-detail） | `raw/final-sweep-3c.txt` | `combinations=196`、`diff_combinations=190`，**190 条差异 100% 是 `ruleset` 项（规则 943→817），元素级 0 条** |
| 浏览器全量（最终树） | `raw/browser-gate.txt` | `178 passed in 199.18s`，exit 0（另有实现中途一次 `178 passed in 173.21s`，同一结论） |
| 软件层门（最终树） | `raw/software-gate.txt` | `2029 passed, 3 deselected in 280.71s`，exit 0 |
| 文档门（最终树） | `raw/doc-gate.txt` | `missing=0`，exit 0（`checked=3189`） |
| 受阻明细 | `raw/merge-plan.json` | `safe=169 / blocked=24`（最终落盘残留 23 组） |

**为什么 196 组合里有 190 条差异**：`verify_style_equivalence.py` 同时比「逐元素计算样式指纹」与
「样式表规则序列」两条独立判据。规则序列**本来就该变**（逗号拆分 +52、合并删 178、死规则删除），
所以它必然红；本轮独立复核逐条确认 190 条差异的 `kinds` 全为 `ruleset`、**没有一条含元素级差异**
（工具里两条判据是两个独立分支、无短路）。元素级抽查见 `.ui-audit/3C-verify.md` §5。

## 3 23 条「保留两段」例外

逐条理由写在 `loop/tests/test_ui_css_structure.py` 的 `ALLOWED`，分两类：
① 两段之间夹着**同特异性覆盖规则**、且运行时 DOM 共命中证据显示确有元素同时命中两者
（`.btn`/`.card`/`.grid2`/`.input`/`@760 .rail-entry`）；② 同名选择器在窗口内另有**别的 @ 上下文**规则
（`.agents`/`.run-item`/`.toast`/`.phase-card`/`.s0-phases`/`header`/`.shell`/`aside #btnNew`/`.aw-*` 等）。
判据与证据：`.ui-audit/3c/merge-plan.json`（受阻明细）+ `.ui-audit/3c/cooccur-full.json`
（36 个（视口,状态）组合 × 884 选择器、2626 对共命中）。

## 4 复跑

```bash
R=/home/work/chenjunming/change-impact-loop
cd $R/loop && PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/test_ui_css_structure.py      # 2 passed
# 全断点指纹（3C 定格口径；web-stage 是 pristine web 副本 + 3C 产物 app.css）
PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  .venv/bin/python $R/.ui-audit/3c/verify_style_equivalence.py \
  --before-web $R/.ui-audit/3c/snap-before --after-web $R/.ui-audit/3c/web-stage
```

## 5 未做 / 不声称 / 已知局限

- **不声称「视觉完全不变」**：hover/active 只有计算样式与断点扫描覆盖，无逐态截图；
  `.active`、触摸、`prefers-reduced-motion` 未纳入指纹。
- **证据层的已知弱点**（独立复核 P1）：共命中证据对「36 组合里零命中」的选择器是**真空真**
  （788 个 app.css 选择器里 264 个零命中；最终产物上靠这条放行的对数 4058+255）。
  本轮用「196 组合元素级指纹 + 独立复核的 `cross_ctx_check.py` + 跨上下文硬受阻」三重兜底，
  但**不能**说「未测选择器一定安全」。这条写进 STATUS §142 的未做/局限。
- **23 条例外未合并**：属「合并任一方向都改某断点生效值」的真冲突，不是遗漏。
- 工具修正历史（不掩盖）：首轮 `split` 不尊重括号、胜者判定把前置 `important` 判错、
  证据豁免短路、同选择器跨上下文 fail-open——四处都由「指纹/独立复核」先报红，修正过程见计划 §2.5/§7.3。
