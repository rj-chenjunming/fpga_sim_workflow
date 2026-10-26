# 节点面板可读性修订 · 开工交接提示词（2026-10-23）

> **这是什么**：用户按节点逐个走查完节点详情面板后的**集中修订开工包**。走查记录与全部待修订项
> 在 [`SPEC-REV-04`](../spec/SPEC-REV-04-20261023.md) §C（P-01～P-35）；本文件是给下一个窗口/实现 owner
> 的**可直接粘贴的开工提示词**与执行约束。
> **不是什么**：不是新契约；契约以 SPEC-REV-04 / SPEC-04 / SPEC-02 为准。本文件不改变任何判据。
> **状态**：走查完成（2026-10-23），**P-01～P-35 尚未实现**（第一版"人话面板"已在工作树，未提交）。
> **校订（2026-10-23 18:45，Lead）**：按当时仓库与运行态更新了并发改动清单、门禁基线数字、
> STATUS 节号与"禁止操作"清单，见 [§0.5](#05-粘贴前必须知道的现状2026-10-23-1845-校订)。

---

## 0 给 Lead / 用户的用法

1. 打开新窗口，把下面代码块**整段**粘进去（改好第一行的仓库路径即可）；
2. 新窗口的 owner 先 `git status` 确认工作树，再按切片实现；
3. 完成后按 §5 收尾：SPEC-REV-04 §C.2 状态、STATUS 新节、证据追加、四道门数字。

> 走查完成状态见 [SPEC-REV-04 §C.1](../spec/SPEC-REV-04-20261023.md)；第一版面板的实现范围与门禁数字见
> [NODE_PANEL_READABILITY_20261023](../evidence/NODE_PANEL_READABILITY_20261023.md) 与 [STATUS §48](../STATUS.md)。

---

## 0.5 粘贴前必须知道的现状（2026-10-23 18:45 校订）

**① 并发会话的未提交改动（另一条线，全部未提交，禁止回退）**

| 文件 | 内容 |
|---|---|
| `loop/web/app.js` | G1 逐条处置控件、`pendingInfo` 区分 gate/job 中断、启动超时后自动接入已创建的 run |
| `loop/web/gate-session.js` | 草稿新增 `entryDecisions`；纯函数 `deriveEntryDecision` / `validateEntryDecisions` |
| `loop/web/app.css` | `.gate-entry*` 样式 |
| `loop/services/agent_view.py` | job 中断不再把模型角色误标 `waiting`（阶段"等待人工"/chip `!` 的根因） |
| `loop/tests/test_gate_session.py`、`test_web_smoke.py`、`test_agent_view.py` | 上述行为的回归断言 |
| `doc/spec/WEB_UI_SPEC.md` | §4.4 逐条处置控件、§5 G1 逐条、§7.2 启动超时语义 |
| `doc/spec/S0_ENVIRONMENT_SPEC.md` | §8 登记 S0-b 未接入缺口（D1–D5） |

**② 门禁基线数字已变**（提示词 §5 里的是旧数）：

- 软件层 `--ignore=tests/browser`：**554 collected**（不再是 546）；上次全量实测 551 passed +
  1 failed（`test_test_layers.py::test_unknown_marker_fails_collection_with_strict_markers`，
  本机 `/tmp/facts` 权限问题，属环境）+ 56 errors（Playwright 默认浏览器未安装，属环境）。
- 浏览器层：**56 collected**，必须带 `HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome`
  （`/usr/bin/google-chrome` 存在；`~/.cache/ms-playwright` 里没有 chrome-headless-shell）。
- 端口：**不要用 18098**（真实 run 正在跑），隔离端口用 18199。

**③ STATUS 节号**：§48 已被"节点面板第一版"占用，**§54 由 Lead 预订**（S0-a 真实派生 + 真实 run 实测 +
两处缺口登记）。新会话请写 **§49**；写入前 re-read，只追加。

**④ 现在绝对不能做的事**（比提示词原文更严）：

1. **不得重启 18098、不得 `pkill -f "uvicorn services.api:app"`**：该进程下有正在执行的真实 N9 作业
   （`JOB-63f79d482690`，5 个用例，已跑 1 小时量级）。需要重启让 `story` 生效时，等 Lead 确认作业结束。
2. **不得修改 `kb/tools/run_guarded.sh`**：它正被运行中的 bash **逐行读取执行**，改它会让当前作业崩。
3. 不得写 `workspaces/s0-ws-20261023/**`（run/sandbox/evidence/job 日志）与
   `workspaces/s0-work-20261023/{SIMLIB_RUN,uvs.setup}`（仿真正在用）。
4. 浏览器/端到端测试会抢 CPU、拖慢真实仿真：**先做代码 + standin 单测**，浏览器与 e2e 留到作业结束。

**⑤ 与切片 2 的整合接口（P-17/P-18 必须复用，不许另写一套）**

- 共享草稿字段：`state.gateDraft.entryDecisions = {entry_id: {decision, reason}}`；
- 覆盖与推导只调用 `window.GateSession.validateEntryDecisions(entryDecisions, ids, allowed)` 与
  `deriveEntryDecision(values)`；`ids` = 服务端 `difference_items.entries` 去重后的 `entry_id`；
- 「冗余条目自动填充」= 提交前把主条目的 `decision/reason` 复制到 `redundant_of` 指向的 `entry_id`，
  仍覆盖全部 id；提交入口仍是闸门视图现有表单（不新增写动作）。

**⑥ P-18 数据源更正（实测）**：`gates.json` **没有** `entry_decisions`，事件流 jsonl 里也没有；
逐条处置目前只存在于提交响应与流程分支载荷。要做"已决策 run 的逐条处置重建"，必须先由 Host 侧
**补落账**（软件层新增 run 内只读产物，例如 `decisions/G1.json`），否则界面只能显示"整门决策 +
逐条处置未留存"，不得从 `gates.json` 猜。

> **已过期（2026-10-26）**：上述"补落账"已由 P-15/P-17/P-18 实施完毕 —— Host 把逐条处置写
> `run_dir/decisions/<gate>.json`（append-only）并随 `gate_decided.detail.entries` 下发，
> 已决策态面板从落账读；**事件流里现在有** `entries`。`gates.json` 按设计仍不存逐条处置
> （口径见 [业务规格 §7](../spec/CHANGE_IMPACT_LOOP_SPEC.md) 与
> [编排规格 §10.4.2](../spec/LOOP_ORCHESTRATION_SPEC.md)）。仅"早于落账"的旧 run 显示"未留存"。

---

## 1 开工提示词（复制整段）

```text
你是 change-impact-loop 仓本轮修订的实现 owner（Lead 已把节点面板逐节点走查完，现在一块实现）。
仓库根：/home/work/chenjunming/change-impact-loop（下文路径相对仓库根）。
本轮目标：把节点执行详情面板从"能看"做到"一眼看懂"，按已登记的 P-01～P-35 一次性修订；
不做新业务功能，不改闸门权威，不改已冻结证据。

============================================================
0. 开工前先做这三件事
============================================================
1) git status --short && git diff --stat
   本批面板改造的未提交改动：`loop/services/node_story.py`（新增）、`loop/services/node_view.py`、
   `loop/web/node-detail.js`、`index.html`、`app.css`、两份测试、SPEC-REV-04、STATUS §48、
   evidence/NODE_PANEL_READABILITY_20261023.md——这是**已完成的第一版"人话面板"**，不要回退。
   **注意有并发会话**：写作时已观察到 `loop/web/app.js` / `gate-session.js` / `loop/services/agent_view.py`
   等文件也被另一会话改动（完整清单见本文件 §0.5 ①）。一律先 `git diff <文件>` 看清再动手，不要回退别人的改动；
   冲突时在最新内容上叠加（FS_STALE_VERSION 就 re-read 后重做）。
2) 读这些文件（按顺序）：
   AGENTS.md
   doc/spec/SPEC-REV-04-20261023.md   ← **本轮唯一权威清单**：§R1 逐节点文案、§R2 闸门复核 UI（设计已定）、
                                          §C.1 走查进度、§C.2 P-01～P-35、§C.3 固定动作
   doc/spec/WEB_UI_SPEC.md §4.2.1/§6.7、doc/spec/LOOP_ORCHESTRATION_SPEC.md §10.4
   loop/services/node_story.py、loop/services/node_view.py、loop/web/node-detail.js
   loop/tests/test_node_story.py、loop/tests/browser/test_node_detail.py
   doc/evidence/NODE_PANEL_READABILITY_20261023.md
3) 工作区有另一个会话在写 `doc/UI_RUNBOOK.md` 和 `doc/evidence/UI_RUNBOOK_20261023/`：
   **不要动这两个**；改 `doc/STATUS.md` 前先 re-read（可能被别人追加过），冲突时只追加、不回退别人内容。
   文件写入若报 FS_STALE_VERSION：重新 read → 在最新内容上重做 → 再写。

============================================================
1. 硬约束（违反即打回）
============================================================
- 只读投影：面板不做判定、不读盘、不打开文件正文（除 P-28 明确新增的报告只读视图）。
- 缺失一律"未下发"；不得补默认值、不得从 stdout 解析数字（缺字段就让 Host 补字段）。
- 服务端 status / 决策枚举**原值必须保留**；中文只是展示名，不得替换权威值。
- 文案改动不改事件与 detail；历史 run 不回填。新增 detail 字段只对新 run 生效；
  但"展示层"（story / 前端文案）可以基于已有字段对旧 run 生效。
- `kb/tools/**` 是冻结目录：P-18 c 方案（改 N2 产物）**不要做**；本批已选 b 方案（见 §R2.2）。
- 环境仓 RTL/TB/PKG/TESTLIB 一律不写。
- **不得重启 18098 / `pkill uvicorn`；不得改 `kb/tools/run_guarded.sh`（正被执行中）；不得写
  `workspaces/s0-ws-20261023/**` 与 `workspaces/s0-work-20261023/{SIMLIB_RUN,uvs.setup}`**（理由见 §0.5 ④）。
- 不新增业务写动作；唯一提交入口仍是闸门视图现有表单（R2 已定）。
- 文案大白话，**禁止只写 I2/I3/I4、verdict_passed、intact、no-op、rc=3 这类代号/内部词**；
  代号只能作小字附注或留在「原始记录」。用户明确说过"别人看不懂"。
- 每个 P 项至少补一条可判定断言（单测或浏览器 DOM 断言），不靠"看着顺眼"。

============================================================
2. 已定的关键设计（照做，不要再问）
============================================================
A. 面板结构（已实现，保持）：一句话用途 → 结果 → 关键数字 → 过程 → 证据/失败 → 原始记录（默认收起，seq 只在这里）。
B. P-09：新增 `story.headline`（短结果，服务端按节点从已有 detail 字段生成；缺失写"未下发"），
   「结果」显示 headline，`summary` 原文移入原始记录。先做 N1；其它节点按各自 P 项。
C. P-10/P-12：N2「结果」按内容说——"内容有变化：1 个文件改了（pcie_register.v），第 171–172 行，偏移 0x0d04"；
   md5 只作证据，注明"改一个字节也会整体变，不代表改动大小"；黄块**只写一句**「1 条需要你确认，到 G1 逐条处置」。
D. P-11：同一文件的多路证据合并展示；计数分"改了 N 个文件 / M 处"与"证据 K 条"。
E. P-18/R2（闸门复核 UI）：列表紧凑 + 勾选 + 「查看前后对比」**浮窗**（宽≥80% 视口、代码自动换行）；
   md5-only 条目不作为一个修订点/不计入 N 条；服务端材料投影给 `redundant_of` 只读标记，
   界面提交时按主条目处置**自动填充**冗余条目（仍覆盖全部 entry_id，服务端校验规则不变）。
   勾完统一提交；提交入口**复用闸门视图现有表单**（共享 gate-session 草稿），节点面板不另设提交。
F. P-28：新增「查看报告全文」只读视图——仅本 run 的 `n12_report.md`（白名单、只读、大小上限、
   不开放任意路径）；入口在 N12 面板和 G2 材料；补访问测试（越权路径一律拒绝）。
G. 通用状态词：
   - `live`=已完成（真实模型调用）；`standin`=已完成（替身，非模型结论）；原值留原始记录；
   - 未收尾（运行还在跑）= "还没有收尾记录"；运行已终态且节点无事件 = **"本轮没有走到这个节点（运行停在 X）"**（P-30）；
   - 未执行（drill 不跑/没提交）="—（未执行）"，不要写"未下发"；
   - 无证据文件且确实没执行 = 说明原因，不要报"证据缺失"。

============================================================
3. 修订清单（按切片做，切片内一次改完再跑测试）
============================================================
【切片 1｜投影 + 前端文案：N0–N12 的"人话"】
P-01 drill 措辞：已实现（来源显示「drill 演示数据（不碰真实环境）」+ 说明行 + N0「拷入预置文件」）。
     本轮补齐：后端 N0 summary 里的"夹具"是否改称呼 → 先不动（记录为暂定），保持双写。
P-02 N2 偏移条目：保持"1 个"（未拍板，不要展开成 0x0d04）。
P-03 N9：结果里写清失败原因（口径一 1687≠0），不再加"原因见 N10"。
P-04 内部节点措辞：N6_apply/N9_submit/N15_submit 按 P-04/P-21/P-33 的白话。
P-05 模型子事件（N3_model/N3_request）：**不并入**父节点，保持现状。
P-06 未收尾两行提示：保留。
P-07 状态 chip：英文原值 + 中文释义（如「ok 通过」「fail 未通过」「live 真实模型」「intact 完整」「confirmed 已确认」）；
     原值必须在，不得归一。
P-08 用途文案：以 SPEC-REV-04 §R1 为准 + §C.2 各 P 项修正。
P-09 N1：结果只留"总文件数 + 用例数"；其余（sha256/指纹/commit/parent）收进原始记录。
P-13 N3：详情显示模型摘要正文 + "需人工确认 N 条"；Host 的节点 summary 改用模型 `summary`
     （组数降级为关键数字）；"0 组"解释为"没有段信息、无法分组（不是没分析）"。
P-14 N3 提示词（loop/prompts/loop_nodes.yaml 的 n3_digest + node_schemas.py 的 N3Output）：
     ①分组改为有条件（offered_segments 为空就不分组，按文件/改动说清楚）；②summary 明确"先说改了什么再说影响"；
     ③risky_points 每条"一句风险 + 依据"；④input 补 id/offsets；⑤detail 增 `digest_summary`/`digest_confirmations` 投影字段。
     **注意**：提示词改动只影响新 run；旧 run 用现有 summary，不回填。
P-15 闸门节点：决策/选项中文（confirmed 已确认/ignored 忽略/disputed 有疑义；accept 接受/rework 返工；
     full_now 全量回归/subset_only 子集回归/milestone_only 仅里程碑/defer 暂缓）；
     显示人工理由原文（gate_decided.reason）与签署时间；闸门"用时"改"等待人签署 X"。
P-16 闸门摘要去内部词（G1_diff_confirm/human_signed/G1_CONFIRMED 不进摘要）。
P-20 N6：状态「已完成（真实模型调用）」；结果补"改了哪 3 个用例"；关键数字补逐用例修改摘要
     （服务端从模型输出投影：用例名 + 改了哪一处/旧→新）；证据指向 Agent 调用记录，不误报缺失。
P-21 N6_apply：结果白话（"3 个用例各改 1 处，已写入沙箱…指纹已记录"）；逐用例清单与 N6 同源；applied→已写入。
P-23 N8：结果"复核通过：检查 9 项，没有必须修改的地方（第 1 次复核，返工上限 3）"；
     关键数字"检查项 9 / 必须修改 0 / 返工轮次 0（上限 3）"；`pass`→通过（pass）；9 项明细只在 Agent 工作窗口。
P-24 N9：口径一显示"日志错误标记行数（*E/*F/*e/ERROR:）"1687；口径二"UVM 报告 UVM_ERROR/UVM_FATAL"0/0；
     判据"两套口径都要为 0 才算通过；本次口径一 1687≠0 ⇒ 判失败"；补"证据身份一致 是"；
     步骤最后一步"作业结束：口径一 1687（非 0）⇒ 判失败"；1687 行来自 tc_pcie_rw_02，可展开看一行示例；证据按用例分组。
P-26 N10：结果"整轮未通过：tc_pcie_rw_02 1687 行读值不匹配（归为既有缺陷，不属于本轮改动），
     3 个用例都缺观测点印记；待裁决 0"；逐用例表（用例/日志错误标记/UVM 报告/印记/判定/原因）；
     分类摘要"1687 行 → 24 个地址区间，既有缺陷 24、本轮引入 0、待裁决 0"可展开；verdict_passed→整轮未通过。
P-27 N11：结果"证据链完整：3 个用例身份四处一致（run_id/用例名/审的 md5/跑的 md5），返工请求 0"；
     关键数字 + 未闭环项 3（印记缺失、冻结件未核验、用例仍待验，可展开）；intact→完整（intact）；证据指 Agent 调用记录。

【切片 2｜闸门复核 UI（大件，按 §R2 实现）】
P-17/P-18：见 §R2.1–R2.4（设计已定）。实现顺序建议：
  1) 服务端：材料投影补 `redundant_of`（只读）；已决策/历史 run 的清单+逐条处置从 `n2_diff.json + gates.json` 重建（只读投影）。
     **实测更正**：`gates.json` 与事件流都没有 `entry_decisions`（§0.5 ⑥），重建前须先补 Host 落账，
     否则只能显示"整门决策 + 逐条处置未留存"。
     > **已过期（2026-10-26）**：Host 落账已由 P-15/P-17/P-18 实现 —— 逐条处置写
     > `run_dir/decisions/<gate>.json`（append-only）并随 `gate_decided.detail.entries` 下发，
     > 已决策态面板从落账读；`gates.json` 按设计**不**存逐条处置（口径见
     > [业务规格 §7](../spec/CHANGE_IMPACT_LOOP_SPEC.md) 订正 + [编排规格 §10.4.2](../spec/LOOP_ORCHESTRATION_SPEC.md)）。
     > 仅"早于落账"的旧 run（如 `RUN-20261015-120626` 夹具）仍显示"未留存"，那是有意的降级形态。
     覆盖/推导必须复用 `GateSession.validateEntryDecisions` / `deriveEntryDecision`（§0.5 ⑤）。
  2) 前端：列表（勾选 + 一句话 + 元信息 + 「查看前后对比」）；浮窗（两栏 before/after、行号、无 hunk 原因）；
     勾选/忽略/有疑义写入共享 gate-session 草稿；底部"已处置 M/N + 去闸门视图确认并提交 →"。
  3) 提交：只走闸门视图现有表单；界面按 `redundant_of` 自动填充冗余条目，覆盖全部 entry_id。
  4) 测试：等待态可勾选、未处置禁用提交；忽略/有疑义必填理由；已决策只读；浮窗嵌套 Esc 焦点。
  注意：节点面板本身是 <dialog>，浮窗用 dialog 栈/页内 overlay；勾选框与展开是两个独立命中区。
  N13/N14 的"待确认项"来源未定 → 先只做 N4，N13/N14 留骨架不接数据。

【切片 3｜运行态与尾部节点】
P-19 N5：首屏不显示索引缺口；结果"必改 3 个用例：…；另有 6 个待查（可能受影响，需人工确认）"；
     关键数字"必改 3 / 待查 6"；缺数据：Host 在 N5 detail 补 `to_check_count`（当前只在 stdout）。
P-29 N13：等待态显示"等待你处理：本轮停在闸门 2，现在不能接受"，硬阻断**白话正文 + 数字**：
     "有 3 个用例改完没验证通过" / "日志错误标记 1687 行≠0" / "72 条文档/RTL 冲突未清零"；
     关键数字：待决策/硬阻断 3/待验用例 3/未清冲突 72；选项中文。node 投影需补 hard_block/blockers 只读字段。
P-30 N14 + 通用未到达态：node detail 补 `run_status`；运行终态且节点无事件 ⇒ "本轮没有走到这个节点（运行停在 X）"。
     已决策态：决策中文（milestone_only=仅里程碑：按受影响子集跑回归后晋升，不要求冲突清零）、
     理由/签署时间、摘要去内部词。
P-31 N15_select：结果"本轮 G3=仅里程碑：按受影响子集选出 5 个回归用例（列出名字）；real 会真跑，drill 不真跑"；
     无独立文件时说明"选择结果在事件里"；未到达按 P-30。
P-32 N15：结果"演示模式：不真跑回归。本轮回归集 = 5 个受影响用例"；关键数字"是否真跑 否（drill）/是（real）"；
     通过数 `—（未执行）`；证据说"本轮未执行回归（无证据）"；real 轮显示作业号/进度/通过数/失败用例。
P-33 N9_submit/N15_submit：Host 补 `node_started`（只影响新 run），或面板标"提交动作（无开始/结束区间）"；
     结果"已提交作业 JOB-xxx，覆盖 N 个用例；流程转入等待"；证据取 job_submitted.refs；drill 不执行要说清。
P-34 N16：结果"晋升被拒：缺少用例状态台账（I2）。本次是试运行（dry-run），没有真正落盘"；
     原因取 stderr 首行原文+白话；关键数字"晋升结果 拒绝/是否真写 否/触发人"；refused→晋升被拒；
     证据 `promote_result.json`（Host 补 refs；每次尝试都应落结果件）。
P-35 HALT：Host 补 `reason` 字段（§10.4 要求）；面板显示"本轮已终止：闸门未放行（G3=暂缓）。这是合法终点，不是失败"；
     各闸门决策中文；过程"流程终止：G3=暂缓（defer）"；证据说"终止记录在事件里"，不报缺失。
P-25 印记（面板侧）：N9/N10 用白话解释"印记"（用例自己打印的 `[N6_xxx] OK ...`，证明预期检查点真的跑过并通过），
     并指出缺哪个 marker。**系统侧（谁来产生印记：N6 提示词/schema 增加观测点输出 vs 基线用例自带）尚未拍板，
     不要擅自改提示词/schema；先做面板解释，把该问题留在 §C.2 状态里。**

============================================================
4. 明确未拍板 / 不要做的事
============================================================
- P-02 N2 偏移值展开：不做（保持条数）。
- P-05 模型子事件合并：不做。
- P-09 是否推广到"所有节点只留 2 个关键数"：未确认 → 只按各节点 P 项落地，不要全局删字段。
- P-18 c 方案（改 N2 产物）：不做（冻结目录）。
- P-25 系统侧印记责任：不做，等 Lead 拍板。
- N13/N14 的待确认项数据源：未定，先留骨架。
- 不要给面板新增任何写动作；不要在前端复制闸门提交逻辑。

============================================================
5. 完成定义（四道门，数字必须复制命令输出）
============================================================
软件层：
  bash loop/spikes/run_software_checks.sh --ignore=tests/browser --junitxml=/tmp/sw.xml
  （**当前基线 554 collected**（2026-10-23 18:45 实测；不再是 546）；本批会新增用例，记录新数字；
   3 项 env_layer 按脚本默认排除。注：本机 `test_test_layers.py::test_unknown_marker...` 因 `/tmp/facts`
   权限失败，属环境，记录为 env 失败而不是代码回归）
浏览器（系统 Chrome + 可写 HOME）：
  cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
    .venv/bin/python -m pytest -q tests/browser
  （**当前基线 56 collected**；必须带 `LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome`，否则默认
   Playwright 浏览器缺失会全 error（§0.5 ②））
端到端（隔离副本，避免污染共享 state）：
  1) 复制工具树（排除 workspaces/.git/loop/.venv/loop/.logs/loop/state/loop/.agently）
  2) 删除副本里的 loop/.agently 与 loop/state（否则 RecordStore identity 报错）
  3) ln -s 原 loop/.venv 副本的 loop/.venv
  4) LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb \
     LOOP_PORT=18199 bash spikes/accept_v1_run.sh
  （当前基线 ALL PASS 117/117；跑完清理副本与测试 run）
文档门：
  python3 doc/audit/check_doc_links.py   （missing=0，rc=0）

收尾：
- 把 SPEC-REV-04 §C.2 对应行状态改为「已修（2026-10-23）」，未做的保留「未定/待拍板」；
- doc/STATUS.md 追加新一节（**§49**；§54 已被 Lead 预订，见 §0.5 ③）：改了什么/四道门实测数字/仍未关闭项，**只追加不回填**；
- 追加/更新 doc/evidence/ 证据（只增不改），引用 SPEC-REV-04 与本次改动；
- 不要声称"已合规"；未拍板项必须在 STATUS 与 §C 保持可见。

============================================================
6. 汇报格式（结束时）
============================================================
1) 改动文件清单（按切片）
2) P-01～P-35 逐条状态：已实现 / 按设计保留 / 未做（原因）
3) 四道门：命令 + 实测数字（复制输出）
4) 仍未关闭项：P-25 系统侧、N13/N14 数据源、P-02/P-05、服务重启要求（story 在进程内，需重启）
5) 顺手发现的缺陷：只登记，不夹带修复
```
