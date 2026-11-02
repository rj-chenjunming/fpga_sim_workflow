# 开工提示词 · UI 批次 3C（F14 合并）→ 3B（配色令牌化）（2026-10-30 交接）

> 用途：**在新窗口第一条消息直接整段粘贴 §0**（或说「按 `doc/agents/开工提示词_UI批次3C与3B.md` 开工」）。
> 交接时点：`HEAD = 46b4d7c`，**工作树未提交**（26 个已跟踪文件改动 + 25 个未跟踪件）；
> 其中「UI 批次 1+2 / 3A」与「前序 T3（RTL 一键入口）」**混在同一树里，都未提交**。未推送。
> 本文自包含：读完 §1 必读 + 本文，即可开工，不需要历史聊天。

---

## 0 给新窗口的第一条消息（可直接粘贴）

```text
接手 /home/work/chenjunming/change-impact-loop（change-impact-loop 软件仓）。
按 doc/agents/开工提示词_UI批次3C与3B.md 开工：先读 §1 必读，再按 §3 顺序做
3C（F14 两段式 CSS 合并，行为保持）→ 3B（配色令牌化，需先拿调色板裁决）→ 批次 4（只在人裁后）。
开工前先 `git log --oneline -3`、`git status --short`、`ls -l --time-style=+%m-%d\ %H:%M loop/web` 核对现场，
并按 §7 跑五个门确认基线（浏览器 178 passed / 软件层 2002 passed / 字号守卫 3 passed / 文档 missing=0 / 运行时读数）。
**工作树混着前序 T3 未提交件与本轮 UI 改动：不得 `git checkout/restore/stash` 整文件、不得 revert 别人的改动。**
3C 只做行为保持的重构，必须用「计算样式指纹」证明前后零差异；3B 先出调色板提案交人确认，未确认不动色值。
不 commit、不 push，除非人明确要求。
```

---

## 1 必读（按顺序，别跳）

| # | 文件 | 读它是为了 |
|---|---|---|
| 1 | [`AGENTS.md`](../../AGENTS.md) | 流程权威：SpecDD、四道门、写权、红线 |
| 2 | [`doc/STATUS.md`](../STATUS.md) **§140**（批次 1+2）、**§141**（批次 3A） | 唯一数字源：已完成范围、门数字、独立复核处置、未做项 |
| 3 | [`doc/spec/WEB_UI_SPEC.md`](../spec/WEB_UI_SPEC.md) §10 **A10–A14**、§13、§14（含「2026-10-30 增补」：首屏/可读性/动效/字体/骨架/颜色来源/字号阶梯） | 现行视觉契约与判据 |
| 4 | [`doc/plans/2026-10-30-ui-visual-optimization.md`](../plans/2026-10-30-ui-visual-optimization.md) §3/§8/§9 | 批次 1+2 的设计契约、执行记录、明确未做项 |
| 5 | [`doc/plans/2026-10-30-ui-typography-scale.md`](../plans/2026-10-30-ui-typography-scale.md) §3/§8 | 批次 3A 的映射口径与执行记录 |
| 6 | [`doc/audit/AUDIT-20261030-ui-design.md`](../audit/AUDIT-20261030-ui-design.md) | 上游审计：D-01～D-20、P1/P2 定级、争议裁决 |
| 7 | 独立复核 E/F（临时工作区，未入库）：`.ui-audit/E-delivery-verify.md`、`.ui-audit/F-typography-verify.md` | 复核发现的口子与处置，避免重犯 |
| 8 | 代码：`loop/web/{app.css,tokens.css,index.html,app.js,legacy.css,legacy.html,favicon.svg}`、`loop/tests/browser/test_ui_visual_20261030.py`、`loop/tests/test_ui_typography.py` | 落点与既有守卫 |

> `doc/evidence/**`、`doc/history/**`、`doc/audit/**` 只增不改；`mockup.html` 是 §14 明示的静态历史样张，**不重绘**。

## 2 现状快照（交接时）

### 2.1 已完成（UI 视觉轨）

| 批次 | 内容 | 关键数字（详见 STATUS） |
|---|---|---|
| 审计 | 按 ai-design-skills 审视 `loop/web/**` | P0=0 / P1=4 / P2=16；报告 `doc/audit/AUDIT-20261030-ui-design.md` + parts/ 四份分报告 |
| 1 可读性 | 对比度、焦点环、`:active`、动效曲线、字体、骨架、favicon、状态词 | S0 对比度 fail 28/209→3/194（仅装饰/禁用）；焦点环 1.39→5.48、2.62→9.0 |
| 2 首屏 | 删营销 hero、页头收紧、提交行上移、闸门压留白 | 三视口 `#s0Rtl`/`#s0Prepare` `visibleRatio=1`；1440 闸门 `#gateMaterial y=831.4` |
| 3A 字号 | §14 11 档阶梯 + §10 A14；组件层吸附 | `app.css` 25→10 个不同字号；脚本吸附 124 处（可归属本轮 121）；守卫 355 处声明 |

### 2.2 未完成（本窗口目标）

| 项 | 状态 | 说明 |
|---|---|---|
| **3C F14 合并** | ❌ 未做 | `app.css` **917 条顶层规则 / 770 个不同选择器（776 个简单选择器）**；**146 个选择器被 ≥2 条规则定义**（涉及 293 条规则）；L1–467 的 337 个选择器中有 **167 个（49.6%）** 被第 468 行起的「视觉系统段」重定义。已登记于 `doc/audit/AUDIT-20261021-post-ui-roadmap.md:33` 的 F14 |
| **3B 令牌化** | ❌ 未做 | `app.css`+`legacy.css` 仍有 **380 次 hex / 234 个不同值** + 1 处 `rgba()`，与 `tokens.css` 的 24 个令牌几乎零重合；§14 已登记「组件层不得新增硬编码 hex」 |
| 批次 4 | ❌ 待人裁 | 图标 SVG sprite（可独立做）、GATE-1↔G1 映射、闸门 `--gate-pane-max-h` 常数 |

### 2.3 工作树（**关键坑**）

`HEAD 46b4d7c`，未提交。**动任何文件前先分清归属**：

- **本 UI 轨（可继续改）**：`loop/web/{app.css,app.js,index.html,tokens.css,legacy.html,legacy.css}`（其中 `app.js`/`index.html` 是**混合文件**：同时含前序 T3 的 `s0Prefill`/`s0-entry` hunks，**不得**当成死代码删）、
  新增 `loop/web/favicon.svg`、`loop/tests/browser/test_ui_visual_20261030.py`、`loop/tests/test_ui_typography.py`、
  `doc/spec/WEB_UI_SPEC.md`、`doc/STATUS.md`、`doc/README.md`、`doc/plans/2026-10-30-ui-*.md`、
  `doc/evidence/UI_*_20261030/`、`doc/audit/AUDIT-20261030-ui-design.md` + `doc/audit/parts/ui-design-20261030/`。
- **前序 T3（RTL 一键入口，非本轨，**只读**）**：`loop/host/{s0,s0b}.py`、`loop/services/{api,contracts}.py`、
  `loop/workflows/**`、`loop/web/s0.js`、`loop/tests/browser/{test_run_sessions,test_web_layout}.py`、
  `doc/spec/{S0_ENVIRONMENT,LOOP_ORCHESTRATION,ENV_PLUGIN}_SPEC.md`、`doc/evidence/RTL_FOLDER_ENTRY_20261030*`、
  一批 `loop/tests/test_s0*` / `loop/host/derive.py` 等未跟踪件。**mtime 均 ≤ 02:14**；UI 轨改动集中在 09:39–11:30。
- 判断方法：`ls -l --time-style=+%m-%d\ %H:%M loop/web` + `git diff <file>` 内容是否含 `T3`/`s0_entry`/`prefill` 注释。
- **禁止**：`git checkout -- .`、`git restore`、`git stash`、`git clean`——会清掉 T3 与本轨未提交成果。

### 2.4 门基线（交接时实测，重跑以自己输出为准）

```bash
cd loop
R=/home/work/chenjunming/change-impact-loop
PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser            # 178 passed in 208.71s
.venv/bin/python -m pytest -q tests/test_ui_typography.py  # 3 passed
bash spikes/run_software_checks.sh --ignore=tests/browser -q  # 2002 passed, 3 deselected
cd .. && python3 doc/audit/check_doc_links.py              # missing=0, exit 0
```

## 3 本轮范围与顺序

1. **3C（先做）**：`app.css` 两段式合并为「单一选择器单一定义」，**行为保持**（计算样式零差异）。
2. **3B（后做）**：先把 §2.2 的颜色存量收敛到 `tokens.css`；**实现前必须拿到调色板裁决**（§5.2 给了提案）。
3. **批次 4**：只在人裁后做；图标 sprite 可独立，但先问。

每个切片独立收口（写好 §9 的 DoD 再进下一个）。**不得**顺手改业务逻辑、请求形状、轮询、闸门判据；
**不得**改 `loop/services/**`、`loop/host/**`、`loop/workflows/**`、`kb/**`、`mockup.html`。

## 4 3C：F14 合并（行为保持）

### 4.1 目标与做法

- 目标：`app.css` 里同一选择器只在**一个**顶层规则块里定义（`@media`/`@supports` 内的同名规则允许单独存在，按上下文计）；
  第 468 行起的「视觉系统段」与前段合并，保留**最终生效值**；删掉被完全覆盖的死声明与已无消费者的规则（如 hero 删除后的残留）。
- **不允许**用「同选择器出现两次就删」的机械办法（F14 原文警告）：必须逐条判断级联语义。
- 推荐流程（每批 ≤15 个选择器）：
  1. 先写 `.ui-audit/fingerprint.py`（或沿用 `.ui-audit/measure.py` 的起服务/夹具方式）：
     在 1280×720 / 1440×900 / 1920×1080 三档、四个视图（s0/setup/run/gate）+ Agent 窗口 + 节点详情浮层，
     对所有元素抓「结构路径 + 关键计算样式」（`font-size/font-family/color/background-color/border*/padding/margin/
     width/height/display/position/gap/line-height/letter-spacing/border-radius/box-shadow/transform/opacity/z-index/flex*/grid*`），
     排序后写 JSON。
  2. 合并一批 → 重跑指纹 → `diff` 必须为空；非空则**回滚这一批**并单独分析（不要靠「看起来一样」）。
  3. 合并完成后跑浏览器门 + 软件门 + 文档门。
- 结构守卫：在 `loop/tests/` 下新增一个静态用例（建议文件名 `test_ui_css_structure.py`，软件层，不启浏览器）：
  用括号深度解析 `app.css`，断言「同一简单选择器在同一 @ 上下文内只定义一次」；扫描数 ≥ 700（防空扫）。
  若确实需要例外，写进用例的白名单并注明理由。

### 4.2 验收

| 判据 | 方式 |
|---|---|
| 级联行为不变 | 指纹 diff = **0**（三视口 × 四视图 + 两个弹层） |
| 结构收敛 | 顶层规则数从 **917** 降到「不同选择器数 770 + 必要 @media」量级；重复定义数 **146 → 0**（白名单除外） |
| 既有功能不退化 | 浏览器 `178 passed`；软件层 `2002 + 新增 ≥ +1 passed` |
| 诚实 | 计划中写明「哪些规则按级联语义保留/删除、哪些属死声明」；不能声称「视觉完全不变」而不给指纹证据 |

**3C 不改规格**（行为保持，无契约变化）；计划里记录方法与证据即可。

## 5 3B：配色令牌化（需先裁决调色板）

### 5.1 目标

`app.css` + `legacy.css` 中**不再出现颜色字面量**（`#hex`、`rgb()/rgba()` 内联色），全部走 `var(--token)`；
`tokens.css` 成为唯一色源。`mockup.html` 不参与；`legacy.html` 内联样式一并处理（若保留，必须在计划里登记例外与数量）。

### 5.2 调色板提案（**先交人确认，再动色值**）

在既有 24 个令牌基础上补语义层（目标 ≤40 个；值为现有使用族的中位色，**允许 ≤12 RGB 的合并**）：

| 组 | 令牌 | 建议值 | 覆盖的存量族（示例） |
|---|---|---|---|
| 底 | `--panel` `--surface` `--surface-2` `--surface-3` `--bg` | `#fff` / `#f8faf9` / `#fcfdfb` / `#f6f9f4` / `#f4f6f5` | 卡片、卡头、浅色块、页面底 |
| 线 | `--line` `--line-strong` `--line-soft` | `#e1e8e4` / `#c7d4cc` / `#eef1f5` | 卡片边、输入边、分隔线 |
| 字 | `--text` `--text-2` `--muted` `--faint` | `#213831` / `#3d5545` / `#61746c` / `#5f6f67` | 正文/次正文/说明/脚注 |
| 主色 | `--primary` `--primary-hover` `--primary-weak` `--primary-line` | 现状 + `--primary-line` | 按钮、链接、选中底 |
| 成功 | `--ok` `--ok-weak` `--ok-line` | `#24734d` / `#edf7ef` / `#bfe8d8` | 通过态 |
| 警告 | `--warn` `--warn-weak` `--warn-line` `--warn-line-soft` `--warn-ink` | `#9a5e16` / `#fff6e8` / `#f3d19e` / `#ead7b7` / `#7a6234` | 等待态、阻断说明 |
| 危险 | `--danger` `--danger-weak` `--danger-line` `--danger-line-soft` | `#b34140` / `#fff0ef` / `#f5c6c6` / `#ebc4bf` | 失败态 |
| 紫 | `--purple` `--purple-weak` `--purple-line` | `#7357a0` / `#f3eef9` / `#e1d8ec` | guardian/次要标签 |
| 侧栏 | `--rail` `--rail-hover` `--rail-active` `--rail-border` `--rail-text` `--rail-muted` `--rail-accent` | 现状 + `#304b3d` / `#3a5a4a` / `#b9d5aa` | 深色导航 |
| 浮层/日志 | `--overlay` `--mono-bg` `--mono-text` | `#12251ab3` / `#20382b` / `#dde8dc` | 弹层遮罩、日志块 |

映射规则：同一语义族内取最近令牌（ΔRGB ≤12）；跨语义不合并（成功/警告/危险即使接近也分开）；
每个令牌在计划里列出「吸收的存量值清单」，便于复核。
**裁决点**：接受这版调色板（会有 ≤12 的细微色差）／要求零色差（则只能「同值建令牌」，几乎没有收敛收益）／调整分组。
未拿到答复前，3B 只可写计划与指纹基线，不可改色值。

### 5.3 验收

| 判据 | 方式 |
|---|---|
| 令牌唯一色源 | 静态守卫（`loop/tests/` 下新增，建议文件名 `test_ui_tokens.py`）：组件 CSS 内 hex/rgb 字面量 = 0；每个 `var(--x)` 在 `tokens.css` 有定义；扫描数 ≥ 300 |
| 令牌数量 | ≤40（含既有 24） |
| 可读性不回退 | 重跑 `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py`：S0/gate/monitor 非装饰文本 <4.5 仍为 0；焦点环 ≥3 |
| 视觉可接受 | 三视口 + 四视图 + 两弹层前后截图对照；人目检 ≤12 色差 |
| 功能 | 浏览器 178+ / 软件层 2002+ / 文档门 missing=0 |

## 6 批次 4（只列，不默认开工）

| 项 | 需要什么 | 建议选项 |
|---|---|---|
| GATE-1 ↔ G1 身份 | 人裁：同一身份 / 新枚举（需改 `kb_lib.GATE_DECISIONS`，冻结目录单独变更）/ 文案中性化 | 先中性化文案，避免界面下达未定身份 |
| 闸门 `--gate-pane-max-h` | 人裁：保持 §14 写死常数 / 放宽 / 折叠非当前阶段（改结构） | 1280×720 闸门首屏目前仍在折叠线下 |
| 图标 SVG sprite | 设计确认符号表后可做 | 一符一义：`▧ ⊞ ◴ ◇` 当前多义 |

## 7 环境与命令

```bash
cd /home/work/chenjunming/change-impact-loop
R=$PWD

# 浏览器门（改 loop/web/** 或 services/contracts.py 界面字段时必跑）
cd loop && PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser

# 软件层门（唯一入口；直接 pytest 会因 ENV_ROOT 只读出现 5 个 OSError，属环境缺件不是缺陷）
bash spikes/run_software_checks.sh --ignore=tests/browser -q

# 文档门
cd .. && python3 doc/audit/check_doc_links.py

# 运行时读数（受控夹具；会写同目录 measure.json/shots）
PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  loop/.venv/bin/python doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py
```

**环境事实**：Chromium 在 `$R/.pw-browsers`；`HOME/TMPDIR` 必须指仓库内可写目录；`/tmp` 跨 bash 调用不共享
（临时件写在仓库内 `.ui-audit/` 下）；数据根 `ENV_ROOT/kb` 只读；`.ui-audit/` 是未入库临时区。

## 8 纪律（每条都踩过坑）

1. **SpecDD**：先规格/计划 → 先失败用例 → 实现 → 门 → 证据 → STATUS。行为保持类重构不需要改规格，但计划要写清。
2. **TDD**：新增守卫测试必须先跑红并**保存原始输出**（上一轮 3A 的先红日志没落档，被复核记了 P2；这次务必留档）。
3. **写权**：`loop/web/**` 同一时刻一个实现 owner；`doc/spec/**`、`doc/STATUS.md` 只有 Lead；
   证据/历史只增不改；`kb/tools/**` 冻结。
4. **数字**：一律从命令输出复制，注明命令；不手算、不抄本文数字作为本轮结果。
5. **独立复核**：每个切片收口前派只读复核员（写 `.ui-audit/<X>-verify.md`），复核结论写进 STATUS。
6. **不 commit / 不 push**，除非人明确要求；不 `git checkout/restore/stash/clean`（见 §2.3）。
7. **诚实**：未实测/未做的写进 STATUS「未做/不声称」；装饰符/禁用控件的对比度豁免要说明理由。

## 9 每个切片的 DoD

- [ ] 计划文档（`doc/plans/`）含判据、写权、门、回滚、未做项
- [ ] 先失败用例（红）原始输出落档 → 实现 → 绿
- [ ] 浏览器门 0 failed（当前基线 178）
- [ ] 软件层门 0 failed（当前基线 2002 passed / 3 deselected，新增用例后只增）
- [ ] 文档门 `missing=0`
- [ ] 证据目录 `doc/evidence/<SLICE>_20261030/`：前后截图 + md5 + 门原始输出
- [ ] `doc/STATUS.md` 新区段（下一段号从 **§142** 起）+ 计划执行记录
- [ ] 独立复核报告 + 处置结论
- [ ] 未做/不声称清单

## 10 已知坑 / 限制（不要重新踩）

- 直接 `pytest` 会因只读 `ENV_ROOT/kb` 出现 5 个 `OSError`（环境缺件）；软件门只认 `run_software_checks.sh`。
- `mockup.html` 有阶外字号与渐变（§14 静态历史样张，**不重绘、不计入守卫**）。
- `WEB_UI_SPEC.md` 有**两个 `## 13`**（802 旧 / 854 新）——前序 T3 遗留，非本轨；不要顺手重排（会动锚点）。
- 1280×720 闸门材料仍在首屏外（只压留白到 1440 达标）；`--gate-pane-max-h` 不动是 §14 承诺。
- `§14:825` 说明文字 12px 未全覆盖：`.rail-foot`、`.s0-access` 等仍 10–11px（部分属「密集侧栏/图注」例外）。
- 字号阶梯 36px 暂无消费者；`test_ui_typography.py` 的规格解析只取 §14 bullet（改动规格文案时注意别破坏 marker）。
- `favicon.svg` 是本地资产；页面禁止出现 `http(s)://`（`test_web_smoke.py` / `test_api.py` 卡这条）。
- `measure.py` 归档副本第 31 行改过 REPO 解析，差异见 `doc/evidence/UI_DESIGN_AUDIT_20261030/README.md` §3。
- 状态词已统一：主区状态类文字 12px；侧栏密集元信息保留 10/11px。

## 11 交接时未决

| # | 事项 | 需要谁 | 默认动作 |
|---|---|---|---|
| 1 | 3B 调色板是否接受（§5.2） | 人 | 未答只做计划 + 指纹基线，不改色值 |
| 2 | GATE-1 ↔ G1 映射 | 人 | 不实现；界面文案不在本轨改 |
| 3 | 闸门 `--gate-pane-max-h` 是否放宽 | 人 | 保持 §14 常数 |
| 4 | 图标 sprite 是否现在做 | 人 | 可做但排在 3C 之后 |
| 5 | 本轨成果是否提交/如何切分提交 | 人 | 不 commit；建议按 1+2 / 3A / 3C / 3B 分提交 |
