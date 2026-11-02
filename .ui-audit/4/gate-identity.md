# 批次 4 · B 项设计：`GATE-1` ↔ `G1` 身份（**文案中性化**，不动枚举/不动判据）

> 只读设计分析，供人裁后实现。**未改任何文件**（`kb/tools/**` 冻结目录全程只读）。
> 依据：`doc/audit/AUDIT-20261030-ui-design.md` D-18；`doc/audit/parts/ui-design-20261030/C-content-semantics.md` C3；
> `D-independent-verify.md`（C3 更正为"有名未映射，不是不存在"）；`doc/plans/OPTIMIZATION_PLAYBOOK.md:159`；
> `kb/tools/kb_lib.py:549-560`；`doc/spec/S0_ENVIRONMENT_SPEC.md:11/34`；`AGENTS.md` §5 红线 4。

## 0 结论先行

- 人裁已定：**全做**。本项按"**只中性化界面文案**"落地（批次 4 三项里唯一不需要改规格的一项）。
- **不改 `kb/tools/kb_lib.py`、不改 `GATE_DECISIONS`、不改闸门判据、不改后端**；`GATE-1≢G1` 的映射问题**保持未决**，界面只是不再宣称自己知道答案。
- 落地改动 = **3 行文案**（`loop/web/index.html:87`、`index.html:136`、`loop/web/s0.js:77`）+ 1 条新增静态守卫。
- **既有测试零改动**：`grep -rn 'GATE-1' loop/tests/ --include=*.py | wc -l` = **0**。

---

## 1 全仓盘点

### 1.1 权威侧（只读，不要动）

| 位置 | 内容 | 性质 |
|---|---|---|
| `kb/tools/kb_lib.py:549` | `GATE_IDS = ("G1_diff_confirm", "G2_report_accept", "G3_regression_decision")` | **枚举权威**（红线 4） |
| `kb/tools/kb_lib.py:550-554` | `GATE_KIND = {G1_diff_confirm: "diff_confirm", G2_report_accept: "report_accept", G3_regression_decision: "regression_decision"}` | 同上 |
| `kb/tools/kb_lib.py:556-560` | `GATE_DECISIONS = {G1_diff_confirm: ["confirmed","ignored","disputed","pending"], G2_report_accept: ["accept","rework","pending"], G3_regression_decision: ["full_now","subset_only","milestone_only","defer","pending"]}` | 同上（本次设计**逐字确认**：**没有 `GATE-1`，也没有任何第四道门**） |
| `loop/services/node_registry.py:13-17` | `GATE_ID_BY_NODE = {"N4": "G1_diff_confirm", "N13": "G2_report_accept", "N14": "G3_regression_decision"}` | 节点↔闸门唯一登记（后端），同样没有 `GATE-1` |
| `loop/workflows/chunks/gates.py:61/78` | `GATE_NODE` / `GATE_LABEL_CN = {"G1_diff_confirm": "闸门1（差异确认）", …}` | 展示元数据 |
| `doc/spec/S0_ENVIRONMENT_SPEC.md:11` | 「S0 两段及 **GATE-1** 均满足后才可执行用例。**S0 不新增闸门**，也不改变既有 N0–N16 的三个闸门。」 | 规格原文：**GATE-1 有名 + 明说不新增闸门** → 它是"复核步骤"的名字，不是第四道枚举门 |
| `doc/spec/S0_ENVIRONMENT_SPEC.md:34` | 「登记表…**GATE-1 负责复核**；否决后逐 hunk 回滚并重跑冒烟。」 | 同上（职责描述） |
| `doc/plans/OPTIMIZATION_PLAYBOOK.md:159` | 「明确 **GATE-1 与现有 G1 的对应关系，不能默认为同一身份**」 | 这正是"映射未决"的出处 |
| `loop/host/s0.py`、`loop/host/s0b.py` | `grep -c gate` → `0` / `0`（S0 后端**没有任何 gate 字段**；`ready_for_execution` 由六项检查决定） | 说明"GATE-1"在服务端**无对应数据**，界面无法 join |

### 1.2 界面侧（本项唯一写范围）

`grep -rn "GATE-1" loop/web` → **3 处**（逐字校验过行号）：

| # | file:line | 现状文本（节选） | 上下文 |
|---|---|---|---|
| 1 | `loop/web/index.html:87` | `准出与切换由服务端判定；准备完成后仍需 <b>GATE-1</b>` | `#s0SubmitHint`，主操作行左提示（**静态首屏兜底文本**） |
| 2 | `loop/web/index.html:136` | `完成 S0 两段及 <b>GATE-1</b> 后才能进入新版执行。` | `#s0Blockers` 的第二段（**服务端无记录时的兜底**；`s0.js:125-127` 有记录时会 `replaceChildren()` 用服务端 blockers 覆盖） |
| 3 | `loop/web/s0.js:77` | `$("s0SubmitHint").textContent = value ? "完整工程复制可能需要较长时间，请保留本页" : "准出与切换由服务端判定；准备完成后仍需 GATE-1";` | busy 态切换时**覆盖**第 1 处的文本；与 1 必须逐字一致 |

> `legacy.html` 里 `grep GATE-1` = 0（旧页面只用 `gate_id` 原文，正好符合"不手抄名"）。

### 1.3 `G1` 在界面里的真实呈现（对照用，不改）

| 位置 | 内容 |
|---|---|
| `loop/web/app.js:57-61` | `GATE_TITLES = {G1_diff_confirm: {label:"闸门 1 · 差异确认", node:"N4"}, G2…, G3…}` —— **只作未知时的展示兜底**，节点优先取服务端 `payload.gate_node` |
| `loop/web/index.html:365`（闸门视图）/ `app.js:1424-1443` | 闸门身份一律来自服务端：`pending.gate`、`gate_options`、`gates_authority.gates` |
| `loop/web/node-detail.js:628-633` | `gateIsG1(gate)` → `String(gate.gate) === "G1_diff_confirm"`（展示形态选择，非判据） |
| `loop/web/legacy.html:345/354/355` | 旧页面对 N4/N13/N14 的说明文字（`【闸门1】差异确认 G1_diff_confirm` …） |
| 测试 | `loop/tests/test_pane_scroll.py:35/42…` 用 `G1_diff_confirm` 作为身份样例；无任何 `GATE-1` |

**因此界面现状是**：闸门**决策**相关的地方全部用服务端下发的 `G1_diff_confirm`（正确）；**只有 S0 准备页的 3 处文案**自己造了一个权威里不存在的 `GATE-1`（红线 4 邻域）。

### 1.4 文档/证据侧（**不要改**）

| 类别 | 文件（`GATE-1` 命中数） | 处置 |
|---|---|---|
| 冻结证据 | `doc/evidence/UI_DESIGN_AUDIT_20261030/measure.json`(4)、`doc/evidence/UI_VISUAL_OPTIMIZATION_20261030/measure-after.json`(3)、`doc/evidence/R_BLOCK_C_20261022/raw/summary.json`(3) | **只增不改**（AGENTS §3）。它们是历史快照，改动后与当时界面文案不同是**正确**的，不要回填 |
| 审计/计划/STATUS/交接 | `doc/audit/AUDIT-20261030-ui-design.md`(3)、`doc/audit/parts/…/{C-content-semantics,D-independent-verify}.md`(4+4)、`doc/plans/{OPTIMIZATION_PLAYBOOK,2026-10-30-ui-visual-optimization,2026-10-30-ui-typography-scale,2026-10-21-specdd-followups}.md`(1+3+1+1)、`doc/STATUS.md`(1)、`doc/agents/开工提示词_UI批次3C与3B.md`(3) | 由 Lead 在 STATUS 新区段记录"已中性化"，其余不动 |
| 人工手册 | `workspaces/manual-20261023/ui-inventory.md`(2) | 运行产物侧手册，**不在本轨写权**；登记为待同步（不是代码缺陷） |
| `loop/.logs/**` 备份 | 多份历史 HTML 快照 | 归档，不动 |

> 合计（排除 `.logs/`、`.ui-audit/`）：**38 处**，其中 `.json` 冻结证据 10 处、可写文档 25 处、界面 3 处。

---

## 2 文案中性化方案（逐条给落点）

原则：**界面不再出现任何闸门 id**；用 S0 规格既有词汇（「S0 两段」「S0-b」「接口复核」「准出」）描述"还要做什么"；
**不新增名字、不加"(身份待定)"这类括号**（那是把未决项甩给操作员，运营台不该这样说话）。
语气沿用现有运营台：短句、陈述、以服务端为准。

### 2.1 `loop/web/index.html:87`（`#s0SubmitHint` 静态兜底）

- 现状：`准出与切换由服务端判定；准备完成后仍需 GATE-1`
- 建议：`准出与切换由服务端判定；准备完成后仍需 S0-b 接口复核`
- 为什么：`S0-b` 是 `S0_ENVIRONMENT_SPEC.md:11` 明文定义的段名（"S0-b：消费外部接口差异 → 核对/适配副本 `TB/top.sv` 并逐 hunk 登记 → …"），**不是闸门 id**，与 `GATE_DECISIONS` 无冲突；「准出与切换由服务端判定」原句保留 → 不暗示界面有判定权。

### 2.2 `loop/web/index.html:136`（`#s0Blockers` 兜底段落）

- 现状：`完成 S0 两段及 GATE-1 后才能进入新版执行。`
- 建议：`完成 S0 两段（含 S0-b 接口复核与准出判定）后才能进入新版执行。`
- 为什么：把"第三件事"还原成 S0-b 内部的复核与准出，而不是另立一道门；`S0_ENVIRONMENT_SPEC.md:11` 的"两段 + 复核"语义不变；同段第一句「派生成功后端口差异与三库冒烟由本页承接；无记录时以服务端结论为准。」已经把判据归给服务端。

### 2.3 `loop/web/s0.js:77`（busy 态覆盖文本，必须与 2.1 逐字一致）

- 现状：`… : "准出与切换由服务端判定；准备完成后仍需 GATE-1";`
- 建议：`… : "准出与切换由服务端判定；准备完成后仍需 S0-b 接口复核";`
- **强制要求**：`index.html:87` 与 `s0.js:77` 两处字符串**逐字相同**（否则首屏兜底与 busy 恢复后文案不一致，正是这类双写的老坑）。建议新增守卫断言二者相等（见 §3）。

### 2.4 为什么中性化后**不会**与后端 `gate` 字段产生歧义

1. **服务端从不产生 `GATE-1`**：`kb_lib.GATE_IDS`/`GATE_DECISIONS` 只有 G1/G2/G3；`host/s0.py`、`host/s0b.py` 里 gate 字段数 = 0（实测 `grep -c gate` = `1`/`2`，均为 `encoding="utf-8"` 等无关命中）。
2. **界面不引入新标识符**：改后 S0 文案里没有任何"门"的代号（只有段名 `S0-b` 与动作「接口复核/准出判定」）。凡出现闸门代号的地方（闸门视图、右列闸门卡、节点面板）**一律来自服务端** `pending.gate` / `gate_options` / `gates_authority.gates`，既有判据「gate 只认 payload.gate」（`app.js:1427` 注释口径）不变。
3. **不会出现"同一个词两个意思"**：`G1` 在界面上仍只由服务端下发时出现；`S0-b` 从来不是闸门，不存在与 `gate` 取值域的交集（`GATE_DECISIONS` 的键是 `G1_diff_confirm`/`G2_report_accept`/`G3_regression_decision`）。
4. **反向风险也消除了**：现状"界面说 GATE-1" 会让读者以为存在第四道门 → 与 `S0_ENVIRONMENT_SPEC.md:11`「S0 不新增闸门」直接冲突；中性化后不再冲突。

### 2.5 若人裁日后定为「GATE-1 ≡ G1」

那属于**规格变更**：要改 `S0_ENVIRONMENT_SPEC.md:11/34` 的措辞（把 GATE-1 写成 G1 的复核步骤），并且**只能在得到人裁后**再让界面文案引用 `G1`；**不要现在预先写成 G1**——那就是 `OPTIMIZATION_PLAYBOOK.md:159` 明令禁止的"默认为同一身份"。
若定为「新增第四道门」：**不可在 UI 轨做** —— 需人裁 + 改 `kb/tools/kb_lib.py` 的 `GATE_IDS`/`GATE_KIND`/`GATE_DECISIONS`（冻结目录单独变更并留证）+ 改 `services/node_registry.py` + 改编排 §闸门 + 改 `gates.py` 的分支事件，**不属于本批次**。

---

## 3 需要同步的测试断言

### 3.1 既有断言：**零改动**

| 检查 | 结果 |
|---|---|
| `grep -rn 'GATE-1' loop/tests/ --include=*.py \| wc -l` | **0** |
| `loop/tests/browser/test_run_sessions.py:165`（`#s0Blockers` 含「三库未执行」） | 断言的是**服务端 blockers** 路径（`s0.js:125-127` 覆盖后），与兜底文案无关 → 不受影响 |
| `loop/tests/browser/test_s0_auto_entry.py:192`（`#s0Blockers` 含「端口差异待处置」） | 同上，服务端 blockers → 不受影响 |
| 其它 `s0SubmitHint` 断言 | `grep -rn s0SubmitHint loop/tests` = **0** → 无断言 |

### 3.2 建议新增守卫（软件层，先红后绿，红日志落档）

`loop/tests/test_ui_gate_copy.py`：
1. `loop/web/**` 全量（`*.html,*.js`）里 `"GATE-1"` 出现次数 = **0**（带白名单：`.logs/` 不在 `loop/web` 下，无需豁免）；
2. `index.html` 里 `#s0SubmitHint` 的文本与 `s0.js:77` 的 `else` 分支字符串**逐字相同**（防双写漂移）；
3. 反向护栏（防以后"顺手自建闸门名"）：`loop/web/**` 里出现的闸门 id 字面量只能是 `G1_diff_confirm`/`G2_report_accept`/`G3_regression_decision`，且必须同时出现在 `loop/services/node_registry.py` 的 `GATE_ID_BY_NODE` 值域里（**不读 `kb/`、不把枚举抄进测试**：从 `services` 侧导入，符合红线 4「权威 = GATE_DECISIONS，前端不许手抄」的检查方向）。

> 注意：第 3 条若实现成"从 `kb.tools.kb_lib` 导入 `GATE_DECISIONS`"也可以（冻结目录可用**只读**），但 `tests/` 现有约定是从 `services` 侧取投影；两种都行，取一种、别两套。

---

## 4 风险与判定边界

| 风险 | 说明 | 处置 |
|---|---|---|
| 把"中性化"当成"映射已定" | 中性化只解决"界面别宣称"，**不解决身份未决** | STATUS 新段必须写「GATE-1↔G1 映射**仍待裁**；本批次只做了文案中性化」 |
| 顺手改 `doc/spec/S0_ENVIRONMENT_SPEC.md` | 会变成契约变更（写权在 Lead） | 本项**不改规格**；若人裁要写映射，另开切片 |
| 改冻结证据 `doc/evidence/**/*.json` | 只增不改 | 不动；文档门只查链接存在性，不查字面一致 |
| legacy 页面 | `legacy.html` 无 `GATE-1`，无需改 | 不动 |
| 文案口味 | "S0-b 接口复核"是否够清楚 | 备选：`仍需执行前检查（S0-b）`；两者都不含闸门代号，二选一人裁定 |

## 5 未做 / 不声称

1. **`GATE-1` 与 `G1` 是否同一身份：未决**，本设计不回答，也不暗示。
2. 不改 `kb/tools/**`、不改 `GATE_DECISIONS`、不改闸门判据、不改后端、不改 `doc/spec/**`。
3. `workspaces/manual-20261023/ui-inventory.md` 的 2 处 `GATE-1` **未同步**（不在本轨写权）。
4. 本项**不需要跑浏览器门**（纯文案），但按 AGENTS §4「界面有改动必须跑浏览器门」仍应跑一次并记入 STATUS。
