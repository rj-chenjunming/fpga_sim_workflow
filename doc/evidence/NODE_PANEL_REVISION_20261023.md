# 节点面板统一修订（SPEC-REV-02 P-01～P-35）· 实测证据（2026-10-23）

> **这是什么**：本轮「节点执行详情面板可读性集中修订」的实现与门禁证据。修订清单的唯一权威是
> [`SPEC-REV-02` §C](../spec/SPEC-REV-02-20261023.md)；实现接口契约见
> [`doc/plans/2026-10-23-node-panel-unified-revision-plan.md`](../plans/2026-10-23-node-panel-unified-revision-plan.md)。
> **不是什么**：不是新契约、不改变任何判据；本文只记录"改了什么 + 命令实测输出"。
> **状态**：P-01～P-35 已按清单修订；仍未关闭项见 §7（`doc/STATUS.md` §47 同一份，数字不各抄一套）。

---

## 1 范围与边界

- **只读投影**：面板仍不做判定、不读盘（唯一例外 = P-28 的报告只读端点，白名单 `n12_report.json` 之外的
  任意路径一律 403）、不打开其它文件正文；状态/decision 原值保留，中文只是展示名。
- **不改事件与 detail 原始语义**：文案只落在 `story` / 展示字段；新增 detail 字段只对**新 run** 生效，
  旧 run 不回填（缺失一律"未下发"）。
- **未新增业务写动作**：提交入口仍只有闸门视图现有表单；节点面板只写共享 `gate-session` 草稿（会话级、不落盘）。
- **未动冻结区**：`kb/tools/**`、环境仓 `RTL/TB/PKG/TESTLIB`、`workspaces/s0-ws-20261023/**`、
  `workspaces/s0-work-20261023/{SIMLIB_RUN,uvs.setup}` 零写入；`doc/UI_RUNBOOK.md` 与
  `doc/evidence/UI_RUNBOOK_20261023/**` 未动（另一条线）。
- **真实作业避让**：全程未重启 `:18098`、未 `pkill uvicorn`、未改 `kb/tools/run_guarded.sh`；
  门禁期间真实 run `RUN-20261023-171744` 一直在跑（`waiting_job` / `JOB-63f79d482690`，见 §5）。

---

## 2 实现切片与文件

| 切片 | 内容 | 文件 |
|---|---|---|
| S1 story 投影 | `headline` / `headline_source` / `note` / `not_reached` / `not_executed` / `evidence_note` / `status_note` / `status_glossary` / `gate` 透传；逐节点模板与关键数字；N2 内容维度；闸门三态 | `loop/services/node_story.py`（新增）、`loop/tests/test_node_story.py`（新增） |
| S2 宿主数据面 | N3/N5/N6/N6_apply/N8/N9/N10/N11/N12/N15*/N16/HALT 新 detail 字段；闸门逐条处置落账 `run_dir/decisions/<gate>.json`；`node_started` 补齐；`n16_result.json`；P-14 提示词 | `loop/workflows/chunks/{gates,host_steps,long_jobs,model_steps,model_common,n10_semantics}.py`、`loop/prompts/{loop_nodes.yaml,node_schemas.py}`、`loop/tests/test_flow.py` |
| S3 服务端投影 | `run_status` / `run_terminal` / `node_started_present` / `gate` 块（二级清单、`redundant_of`、P-29 数字）/ `report` 块；`GET /api/runs/{id}/report` | `loop/services/{node_view,contracts,api}.py`、`loop/tests/test_node_detail_projection.py` |
| S4 前端 | 结果区 headline + 黄条、状态 chip 释义、未到达/未执行/证据入口、闸门二级清单 + 前后对比浮窗 + 逐条处置草稿、N12 报告全文浮窗、G2 材料报告入口、`window.GateDraftBridge` | `loop/web/{node-detail.js,index.html,app.css,app.js}`、`loop/tests/browser/test_node_detail.py` |
| S5 文档 | SPEC-04 §4.2.1/§4.2.2/§4.4/§6.7/§6.8、SPEC-02 §10.4.1–§10.4.5、SPEC-REV-02 §C.2 状态 | `doc/**` |

**单一判据（AGENTS 红线 8）**：同一文件的"多路证据归并"只有一份实现
（`node_story.group_diff_entries`），闸门清单的 `contracts._group_diff_entries` **委托**它；
`gate.nodes ↔ 闸门 id` 的映射只在 `node_view.GATE_ID_BY_NODE` 一处。

---

## 3 P 项 → 落点（要点；逐条状态见 SPEC-REV-02 §C.2）

| P 项 | 落点（实现事实） |
|---|---|
| P-07 | 状态 chip = 服务端原值 + `story.status_note`；`status_glossary` 由服务端下发（16 词条含 `failed`），前端不手抄 |
| P-09 | 新增 `story.headline`；N1「结果」只留"快照文件数 + 冻结用例数"，`summary`/sha256/指纹/commit 移入「原始记录」 |
| P-10/P-11/P-12 | N2 结果以"内容有没有改"为主语；同 id（allfile+rtl_file）归并成 1 组、不算 2 条；黄条一句「N 条需要你确认，到 G1 逐条处置」（N = 有未决证据的唯一 entry_id 数） |
| P-13/P-14 | N3 detail 增 `digest_summary`/`digest_confirmations`/`groups_count`/`offered_segments_empty`；节点 summary 改用模型 summary；n3_digest 提示词改为有条件分组 + 先说改了什么；只对新 run 生效 |
| P-15/P-16 | 决策/选项中文（原值保留）、显示人工理由原文与签署时间、「等待人签署 X 小时 Y 分」；摘要/headline 去 `human_signed`/`G1_CONFIRMED` 等内部词 |
| P-17/P-18 | N4 面板二级差异清单（勾选 + 一句话 + 元信息 + 浮窗前后对比）；md5-only 只作附证据、不计修订点；`redundant_of` + 共享草稿；提交仍只有闸门视图表单；已决策态只读（`decisions/<gate>.json` 回填） |
| P-19 | 首屏只留「必改 / 待查（用例数）」；索引缺口/索引完整/gate1_rc 进原始记录；`to_check_case_count` 由 Host 提供（旧 run 未下发） |
| P-20/P-21 | N6 逐用例修改清单（`case_edits`，与 N6_apply 同一投影函数）；`applied`→已写入；证据指向 Agent 工作窗口（不误报缺失） |
| P-22/P-23 | N7 编译白话 + 用例名、去重复项；N8 复核项数/必须修改/返工轮次（含上限）、`pass`→通过（pass） |
| P-24/P-25/P-26 | N9 双口径白话 + 判据句 + 口径一来源用例 + 身份一致；N10 逐用例表 + 失败分类摘要；P-25 只做面板侧印记解释（系统侧未拍板） |
| P-27/P-28 | N11 证据链/身份一致/未闭环白话；新增报告只读端点（白名单 + 512 KiB 上限 + 越界 403）+ N12/G2 入口 |
| P-29/P-30 | 等待态"等待你处理…现在不能接受"+ 硬阻断白话 + 关键数字（硬阻断/待验用例/未清冲突）；未到达态"本轮没有走到这个节点（运行停在 X）" |
| P-31/P-32/P-33 | N15_select 用例名 + 是否真跑；N15 drill「演示模式：不真跑回归」+ `—（未执行）`；submit 节点补 `node_started` + 作业日志 refs |
| P-34/P-35 | N16 拒绝原因 stderr 首行 + dry-run 说明 + 每次尝试落 `n16_result.json` 并进 refs；HALT 补 `reason` 白话 + "这是合法终点，不是失败" |

---

## 4 门禁实测（命令输出复制，2026-10-23）

| 门 | 命令 | 实测 |
|---|---|---|
| 软件层（本轮最终代码） | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **646 passed, 3 deselected, 1 warning in 152.54s**（`EXIT=0`；收集 **649**，3 项 `env_layer` 按脚本默认排除并在输出列出） |
| 软件层（改动前基线，同命令） | 同上 | **551 passed, 3 deselected, 1 warning in 111.96s**（收集 554） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **69 passed in 111.16s**（4 个文件；改动前基线 56） |
| kb 自测 | `LOOP_WORKSPACE=<可写影子数据根> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **PASS=10 FAIL=0** |
| kb 自测 | `LOOP_WORKSPACE=<可写影子数据根> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **PASS=9 FAIL=0** |
| 端到端（隔离副本） | 工具副本 `.tmp/e2e`（rsync 排除 workspaces、.git、虚拟环境、日志、state、.agently 六类）+ `LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS，117/117**（phase 1/2/3/4/4b/5 = 50/27/18/8/8/6，六相 `rc=0`，`EXIT=0`） |
| 文档 | `python3 doc/audit/check_doc_links.py` | 见 `doc/STATUS.md` §47（同一命令与同一份数字） |

### 4.1 环境注意事项（实测）

1. **DSH 沙箱的 `/tmp` 是每次调用私有的**：跨调用落盘请写仓内路径（本轮日志写在仓内临时目录，收尾已删除）。把日志写 `/tmp` 再另一次调用读，会读不到。
2. **直接 `pytest` 会写只读数据根**（`WORKSPACE_ROOT = ENV_ROOT/kb`）：端点用例在 `prepare_run_dir` 处
   `OSError: [Errno 30] Read-only file system`。软件层入口必须用 `spikes/run_software_checks.sh`
   （自建可写影子数据根 + 隔离 state）；kb 自测同理需要可写 `LOOP_WORKSPACE`。
   本次直接 pytest 的同类失败计数 = `grep -c "^FAILED"` 与 `grep -c "Read-only file system"` 相等，
   属**环境**而非代码回归（未在门禁表里计入通过）。
3. **浏览器门的一次伪失败**：浏览器门首次与软件层并行（`nice -n 19`）跑时，
   `tests/browser/test_run_sessions.py::test_withdrawn_option_cannot_be_submitted`（基于 `page.clock` 的时序用例）
   失败 1 条；单独重跑与全量重跑（无并行、正常优先级）均通过（`69 passed`）。判定为 CPU 竞争下的
   时序抖动，不是代码回归；证据保留在本文，不掩盖。
4. **端到端副本陷阱**（延续上轮记录）：副本必须删掉 `loop/.agently` 与 `loop/state`，
   否则 RecordStore identity 报错、N0–N4 全 fail（本轮副本用 rsync 排除 + 清理，117/117 直接通过）。
5. **服务未重启**：`:18098` 上的进程仍是旧代码，`story` 需重启才生效（本轮按约束不重启）。

---

## 5 真实作业避让证据

| 时刻 | 真实 run 状态（`GET :18098/api/runs`） |
|---|---|
| 18:53（开工） | `RUN-20261023-171744` · `waiting_job` · `current_node=N9_submit` |
| 19:20（软件层门禁中） | 同上（`waiting_job`） |
| 19:28（e2e 门禁后） | 同上（`waiting_job`，作业 `JOB-63f79d482690` 仍 `running`） |

全程未对该进程/端口做任何写操作；e2e 使用隔离副本 + `:18199`，收尾已删除副本与 3 个 `.loop_drill` 测试 run。

---

## 6 面板实测样例（真实 run 数据，只读投影离线计算）

用 `RUN-20261023-171744` 的真实事件流 + detail 跑 `build_node_detail`（不写盘、不改 run）：

- **N1**：`快照完成：4492 个文件，冻结 162 个用例。`
- **N2**：`内容有变化：4 个文件改了（TCS9620_MAC_TOP.v、dom_engine_top.v、pcie_register.v…）；4 处有行级证据，4 条需要你确认；其中 pcie_register.v 第 171–172 行、偏移 0x0d04。`
  + 黄条「4 条需要你确认，到 G1 逐条处置」；关键数字 `改了文件数 / 有行级证据的改动 / 需要你确认 / 自检通过`
  （md5、路由计数不再进关键数字）。
- **N4（已决策）**：`人已确认差异清单（confirmed 已确认），签署人 human:chen，理由：4 个文件均为本次测试改动。`
  + 证据区「签署记录在 gates.json（等待人签署 …；签署时间 …）」；逐条处置清单 4 条修订点（7 条未决路证据归并为 4 组），
  因该 run 早于落账 ⇒ 明说「逐条处置未留存」，不猜。
- **N6**：`本轮修订目标 5 个用例；逐用例修改未下发（旧 run 的 detail 没有逐用例清单）；输出校验通过。`（旧 run 诚实降级）
- **N7**：`5 个用例都编译通过（失败 0）。`
- **N8**：`复核通过：检查项数未下发，没有必须修改的地方（第 1 次复核，返工上限 未下发）。`（旧 run 降级）
- **N9_submit**：`已提交全跑作业 JOB-63f79d482690，覆盖 5 个用例；流程转入等待作业完成。`

---

## 7 未关闭项（与 `doc/STATUS.md` §47 同一份）

1. **P-25 系统侧（印记谁产生）未拍板**：面板只能解释"缺印记 = 无法证明预期检查点真的跑过"，真实轮仍过不了 I3；
   未擅自改 N6 提示词/schema。
2. **N13/N14「待确认项」数据源未定**：面板保留同一骨架（显示 hard_block / 材料数字），不接假条目。
3. **P-02（N2 偏移值是否展开）、P-05（模型子事件是否并入父节点）、P-09 是否推广到"所有节点只留 2 个关键数"**：
   按用户此前指示不做，保持可见。
4. **`:18098` 服务需重启**才会出现新 `story`（进程内生成；本轮按约束未重启）。
5. **旧 run 不回填**：N3 摘要/N5 待查/N6 逐用例/闸门逐条处置只在**新 run** 有；旧 run 面板如实写"未下发/未留存"。
6. **浏览器门一次伪失败**记录在 §4.1-3（不是代码回归），不放宽断言、不抹掉。
7. **`run_software_checks.sh` 会重复传 `-q`**（脚本自带 `-q` + 调用方再传 ⇒ `-qq` 吞掉 "N passed" 汇总行）：
   既有脚本行为，本轮只登记不修（不在本批写权内）。
8. **未声称"已合规"**：上表与 `STATUS §47` 的未关闭项保持可见。

---

## 8 二轮：9 项用户裁决落地（2026-10-23）

> 裁决原文与逐项解释见 [`doc/plans/2026-10-23-node-panel-unified-revision-plan.md` §8](../plans/2026-10-23-node-panel-unified-revision-plan.md)；
> 状态数字唯一源仍为 `doc/STATUS.md` §48（本文只记事实与命令输出）。

### 8.1 落地内容

| # | 裁决 | 落地 |
|---|---|---|
| 1 | P-25 **作者模型产出观测点** | `N6Output.observation_points`（`{case, marker, address, offset, expected_value}`，marker `^N6_[A-Za-z0-9_]+$`）；提示词要求每个改动用例真打一行 `[N6_<检查点>] OK <addr>+<off> <name> = 0x…`（实读值，且该行进 `edits[].new`）；Host `_validate` fail-closed（每用例至少一条 / marker 唯一 / 必须出现在同用例 edits 里）；N6 detail 投影 `observation_points`；standin/drill 显式 `null` |
| 2 | N13/N14 **只读待确认项** | `gate.items`（`{id,kind,title,detail,severity}`，kind ∈ blocker/open_item/conflict/case）+ `gate.state` 增 `read_only`；G2 = 阻断项 + N12 报告未闭环项；G3 = 阻断项 + 未清冲突摘要 + 回归选集用例；**无勾选/无 disposition/不参与提交**；G2/G3 不再继承 G1 差异条目（避免两套材料混显） |
| 3/4/5 | P-02 / P-05 / P-09 | 按裁决保持现状（不改代码） |
| 6 | P-01 | N0 **新 run** summary =「预置数据（夹具）初始化」；drill 双写、real 隐藏 S0 说明行 |
| 7 | 重启时机 | 未重启；后台看守记录真实作业终态（见 §8.4） |
| 8 | G2 报告**一次点击** | 新增 `loop/web/report-viewer.js`（`window.ReportViewer`），`#ndReportOverlay` 改独立 body 级 `<dialog>`；N12 面板与 G2 材料共用；G2 一次点击直接弹全文 |
| 9 | 提交 | 未 commit（工作树含另一条线未提交改动） |

### 8.2 测试与验收驱动器修正（均不放宽断言）

1. `tests/test_agent_context_memory.py`：N6 fail-closed 后 fake provider 输出必须合法 ⇒ 只把 4 条
   characterization 用例的夹具换成合法输出（`revisions` 覆盖 targets + 同用例 marker 进 edits + 一致
   `observation_points`），原断言（rework_reasons/excerpts/NEW_RULE 等）逐字保留。
2. `spikes/accept_v1.py` A51：`job_submitted` 后、执行真正 pause 前可能读到 `pending_interrupt=None`
   ⇒ 先等当前中断出现（≤15s）再校验"快照里该中断可恢复"；判据不变。修正前本轮跑出
   `phase 1 PASS=49 FAIL=1`，修正后 `117/117`。

### 8.3 门禁实测（命令输出复制）

| 门 | 实测 |
|---|---|
| 软件层 | **656 passed, 3 deselected, 1 warning in 171.01s**（`EXIT=0`；收集 659） |
| 浏览器 | **75 passed in 124.37s**（`EXIT=0`；节点面板用例 26→33） |
| kb 自测 | gate_schema **PASS=10 FAIL=0**；n5_reachability **PASS=9 FAIL=0** |
| 端到端（隔离副本） | **ALL PASS 117/117**（50/27/18/8/8/6，六相 `rc=0`，`EXIT=0`） |
| 文档 | `missing=0`（`python3 doc/audit/check_doc_links.py`） |

### 8.4 真实作业避让

后台看守每 60s 记录 `RUN-20261023-171744`：收尾时仍 `waiting_job`（`JOB-63f79d482690` / `running`）。
未重启 `:18098`、未 `pkill uvicorn`；e2e 隔离副本 + `:18199`，收尾已删除副本与 3 个 `.loop_drill` 测试 run。
**重启需由人执行**（进程在独立 PID 命名空间，Agent 无法按 PID 操作）；命令与前置条件见 `STATUS §48.5`。

### 8.5 二轮遗留

- `observation_points` 只进 detail，未在面板首屏展示（是否显示"观测点 N 条"待后续需求）。
- P-25 的真实轮效果未验证（drill/standin 无 live 输出）；N6 fail-closed 是**预期代价**，首次 real 轮需观察模型稳定性。
- N13/N14 仍无"逐条处置"语义（裁决 #2 明确只做只读清单）。

---

## 9 真实作业终态记录（2026-10-23 21:25 观测，重启前置条件）

> 目的：记录"重启 `:18098` 之前真实 run 已到终态"这一事实（裁决 #7 的前置条件）。
> 数据全部来自 `GET :18098/api/runs/RUN-20261023-171744`（只读）与后台看守日志。

| 项 | 值 |
|---|---|
| run | `RUN-20261023-171744`（mode=real，baseline=v0，created 17:17:44） |
| 终态 | `status=failed`（updated 21:24:53） |
| 失败原因（服务端原文） | `投递失败：RuntimeError: 作业 JOB-63f79d482690 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续。` |
| 作业 | `JOB-63f79d482690` · `phase=cancelled` · `rc=None` · `elapsed_s=12918.7`（约 3 小时 35 分） · started 17:49:34 |
| 事件尾部 | `#35 N9 warning cancel_requested` → `#36 N9 warning cancelled` → `#37 lifecycle warning failed` |
| node_history 尾部 | `… N8 ok / N8_model ok / N8_request ok / N9 running / N9_submit ok`（N9 无收尾事件；N10/N11/N12 未到达） |
| 计数快照 | 口径一=25（非 0）；口径二 value={} |

**观测结论**：作业是被**外部取消**（`cancel_requested` 事件；非本 Agent 发起，本 Agent 全程未对
`:18098` 做任何写操作），并按既定契约**判失败**（"取消不得当成功"），符合 §43/§48 的失败语义。
看守日志（每分钟一条）见会话临时目录 `job_watch.log`（收尾随 `.tmp` 删除），首条 20:10:05、
末条 21:25:09 = `failed cancelled`。

**重启前置条件已满足**：run 已不在 `waiting_job/running`。但 `:18098` 的 uvicorn 进程在**独立 PID 命名空间**，
本 Agent 的沙箱只能看到自己的进程（`/proc` 仅 bwrap/bash 自身），**无法按 PID 停止**该进程 ⇒
物理重启需由人执行（命令见 `STATUS §48.5`）。重启后可用本 run 复核：N1–N9 新 `story`、
N9"未收尾/运行停在 failed"、N10–N16 的"本轮没有走到这个节点"、N4 的"逐条处置未留存"。
