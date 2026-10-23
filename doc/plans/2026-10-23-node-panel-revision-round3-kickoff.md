# 节点面板补充修订（第三轮）· 开工交接提示词（2026-10-23 晚）

> **这是什么**：第二轮 9 项裁决落地后的**遗漏审计 + 第三轮开工包**。新窗口把 §1 的代码块整段粘进去即可开工。
> **背景**：P-01～P-35 已修订，9 项用户裁决已落地；四道门在第二轮工作树上全绿。本文件只列**还没闭环**的项。
> **不是什么**：不改变任何已定契约；行为以 [`SPEC-REV-04`](../spec/SPEC-REV-04-20261023.md)、
> [`SPEC-02 §10.4`](../spec/LOOP_ORCHESTRATION_SPEC.md)、[`SPEC-04`](../spec/WEB_UI_SPEC.md) 为准。

---

## 0 粘贴前必须知道的现状（2026-10-23 21:30 校订）

**① 工作树状态**

- **未提交**（用户裁决 #9：等另一条线先落，不混提）。有**两条线**的未提交改动：
  - 本轮（节点面板）：`loop/services/{node_story,node_view,contracts,api}.py`、`loop/workflows/chunks/*.py`、
    `loop/prompts/*`、`loop/web/{node-detail,report-viewer,index.html,app.css,app.js}`、`loop/tests/**`、`doc/**`；
  - 另一条线：`doc/UI_RUNBOOK.md`、`doc/evidence/UI_RUNBOOK_20261023/`、`loop/services/agent_view.py`、
    `loop/web/gate-session.js`、`loop/tests/{test_agent_view,test_gate_session,test_web_smoke}.py`、
    `doc/spec/S0_ENVIRONMENT_SPEC.md` 等。
  **一律先 `git diff <文件>` 看清再动手；只叠加不回退；`FS_STALE_VERSION` ⇒ re-read 后重做。**
- 未跟踪的新文件：`loop/services/node_story.py`、`loop/tests/test_node_story.py`、`loop/web/report-viewer.js`、
  `doc/spec/SPEC-REV-04-20261023.md`、`doc/plans/2026-10-23-node-panel-*.md`、`doc/evidence/NODE_PANEL_*.md`。
- `.tmp/` 是本会话临时目录（日志/看守），可直接删；删前确认没有看守在写（见 ④）。

**② 门禁基线（第二轮工作树，2026-10-23 20:4x 实测；新窗口记录新数字）**

| 门 | 命令 | 当前基线 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **656 passed, 3 deselected**（收集 659；~171s） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **75 passed**（~124s；4 文件） |
| kb 自测 | `LOOP_WORKSPACE=<可写影子数据根> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` / `_selftest_n5_reachability.py` | **PASS=10/0**、**PASS=9/0** |
| 端到端 | 隔离工具副本 + `LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=…/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS 117/117**（50/27/18/8/8/6） |
| 文档 | `python3 doc/audit/check_doc_links.py` | `missing=0`（`known_missing=10` 是历史登记项） |

- **直接 `pytest` 会写只读数据根**（`OSError: Errno 30`）⇒ 软件层必须走 `spikes/run_software_checks.sh`
  （自建可写影子数据根）；kb 自测需 `LOOP_WORKSPACE` 指向可写影子 + 真实基线/夹具软链。
- **DSH 沙箱的 `/tmp` 是每次 bash 调用私有的** ⇒ 跨调用落盘写仓内路径（如 `.tmp/`），别写 `/tmp`。
- `spikes/run_software_checks.sh` 自带 `-q`：再传 `-q` 会变 `-qq` **吞掉 "N passed" 汇总行**（待修，见 R3-13）。

**③ 真实 run 与 `:18098` 服务**

- 真实 run `RUN-20261023-171744`（mode=real）已于 **21:24:53 `failed`**：作业 `JOB-63f79d482690`
  被**外部取消**（`phase=cancelled`, elapsed 12918.7s），事件 `#35 cancel_requested → #36 cancelled →
  #37 lifecycle failed`。按契约"取消不得当成功"判失败。详见 `doc/evidence/NODE_PANEL_REVISION_20261023.md` §9。
- **`:18098` 仍是旧代码**（进程内 `story` 未加载）。旧 uvicorn 在**独立 PID 命名空间**，Agent 沙箱
  `/proc` 只看得到自己 ⇒ **Agent 无法按 PID 停止/重启它**。重启必须由人：
  ```bash
  cd /home/work/chenjunming/change-impact-loop/loop
  LOOP_ENV_ROOT=/home/work/chenjunming/change-impact-loop/workspaces/s0-work-20261023 \
  LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023 \
  LOOP_PORT=18098 ./run.sh
  ```
  开工第一件事：`GET :18098/api/runs/RUN-20261023-171744/nodes/N1` 看 `story.headline` 是否已出现
  （出现 = 已用新代码重启；否则仍是旧代码，**不要** pkill，先做代码/单测，等用户重启）。
- 该 run 停在 N9 失败 ⇒ **不能**用它验证 G2/G3（N13/N14 未到达）与 P-26/P-27/P-28/P-31/P-32/P-34/P-35 的真机表现；
  这些要等下一轮 real run 走到 N16。

**④ 并发红线（比原提示词更严）**

1. 不重启 `:18098`、不 `pkill uvicorn`（需用户手动停/起；旧作业已终态，但仍须人操作）；
2. 不改 `kb/tools/**`（冻结）；不改环境仓 `RTL/TB/PKG/TESTLIB`；不写 `workspaces/s0-ws-20261023/**`、
   `workspaces/s0-work-20261023/{SIMLIB_RUN,uvs.setup}`；不动 `doc/evidence/UI_RUNBOOK_20261023/**`；
3. 浏览器/端到端门会抢 CPU：只跑相关文件，全量门留到最后统一跑（若还有真实仿真在跑，先问用户）；
4. 子任务写权互斥：见 §1 第 3 节的分片；同一文件同一时刻只一个 owner。

---

## 1 开工提示词（复制整段）

```text
你是 change-impact-loop 仓本轮「节点面板补充修订（第三轮）」的实现 owner。
仓库根：/home/work/chenjunming/change-impact-loop（下文路径相对仓库根）。
目标：把第二轮遗漏/新发现的 18 个补充项闭环；不重做已完成项、不改已定裁决、不放宽断言。
本轮最关键的 P0 是让"N6 观测点印记"真正能被 host/evidence 解析（否则真实轮 I3 永远过不了）。

============================================================
0. 开工前先做这四件事
============================================================
1) git status --short && git diff --stat
   - 工作树有**两条线**的未提交改动（见 doc/plans/2026-10-23-node-panel-revision-round3-kickoff.md §0）：
     只叠加、不回退；FS_STALE_VERSION ⇒ re-read 后重做。
2) 确认服务状态：GET http://127.0.0.1:18098/api/runs 与
   GET http://127.0.0.1:18098/api/runs/RUN-20261023-171744/nodes/N1
   - 若 N1 的 story.headline 已出现 ⇒ 用户已重启，新面板可做真机复核；
   - 若仍无 ⇒ 仍是旧代码，**不要 pkill/重启**（进程在独立 PID 命名空间，Agent 停不了），先做代码+单测。
3) 读这些文件（按顺序）：
   AGENTS.md
   doc/plans/2026-10-23-node-panel-unified-revision-plan.md   ← 第一/二轮接口契约 + §8 九项裁决（已定，勿重问）
   doc/spec/SPEC-REV-04-20261023.md 的 §C.2（P 项状态）与 §R1/§R2
   doc/spec/LOOP_ORCHESTRATION_SPEC.md §10.4（10.4.1–10.4.5）
   doc/spec/WEB_UI_SPEC.md §4.2.1/§4.2.2/§4.4/§6.7/§6.8
   doc/STATUS.md §49/§50/§51（门禁数字与未关闭项）
   doc/evidence/NODE_PANEL_REVISION_20261023.md（全部实测证据）
   loop/host/evidence.py（**只读**：印记解析/期望解析/_verdict 是权威，本轮不改它）
   现状实现：loop/services/{node_story,node_view,contracts,api}.py、
             loop/workflows/chunks/{gates,host_steps,long_jobs,model_steps,model_common}.py、
             loop/prompts/{loop_nodes.yaml,node_schemas.py}、
             loop/web/{node-detail,report-viewer,index.html,app.css,app.js}、loop/tests/**
4) 基线先跑一遍软件层（约 3 分钟）确认 656 passed / 3 deselected，再动手：
   bash loop/spikes/run_software_checks.sh --ignore=tests/browser

============================================================
1. 硬约束（违反即打回）
============================================================
- 只读投影：面板不做判定、不读盘、不打开文件正文（唯一例外 = 既有 `GET /api/runs/{id}/report`）。
- 缺失一律"未下发"；不补默认值、不从 stdout 解析数字；status/decision 原值必须保留。
- 文案改动不改事件与 detail；新增 detail 字段只对新 run 生效；旧 run 不回填。
- 不改 `kb/tools/**`、不改 `host/evidence.py`（期望解析是权威）、不写环境仓/workspaces/s0-*。
- 不新增业务写动作：提交入口仍只有闸门视图现有表单；节点面板只写共享 gate-session 草稿。
- 每个补充项至少一条**可判定断言**（单测或浏览器 DOM 断言），不靠"看着顺眼"。
- 不放宽既有断言、不删既有用例来"变绿"；失败必须显式（fail-closed），不得静默。
- 文案大白话；代号（I2/I3/I4、verdict_passed、intact、no-op、rc=3）只能作小字附注或留原始记录。

============================================================
2. 已定裁决（第二轮 9 项，**不要再问**）
============================================================
1) P-25 观测点由**作者模型**产出（observation_points + 真打印印记），Host fail-closed 校验；
2) N13/N14 只做**只读待确认项清单**（gate.items），不做逐条处置/勾选；
3) P-02 偏移条目保持条数；4) P-05 模型子事件不并入；5) P-09 关键数字保持逐节点精选；
6) P-01 双写+real 隐藏+N0 新 run 改称"预置数据（夹具）初始化"；
7) 重启等作业结束后由**人**执行；8) G2 报告**一次点击**直接弹浮窗（ReportViewer）；
9) **暂不 git 提交**（等另一条线先落）。

============================================================
3. 补充修订清单（按分片；P0 必须做，P1 应做，P2 文档/验收）
============================================================
【P0-A｜N6 观测点必须能被 host/evidence 解析（本轮最关键）】
R3-01 现状是真 bug：提示词示例写成 `uvm_info("N6", $sformatf("[%s] OK …", "N6_FPGA_DATE", …))`
  ⇒ 日志里 UVM report **ID** 是 `N6`，而 host/evidence.py 的 `_auto_markers()` 只认含 `N6_` 的 **ID**
  ⇒ N10 报"无预期观测点印记"，真实轮 I3 仍失败。即使 ID 对了，marker 尾名不能解析到文档条目时
  `_verdict` 也会判"期望不可解析"。
  要做：
  ① loop/prompts/loop_nodes.yaml::n6_author 改成：
     `uvm_info("<marker>", $sformatf("OK <addr>+<off> <name> = 0x%08h", actual), UVM_LOW)`
     其中 `<marker>` = `N6_<文档条目名>`（如 `N6_fpga_date`；条目名取自 input 的 doc_bitedf/索引，
     norm 后长度≥4），**marker 必须是 UVM_INFO 的 ID，不是消息前缀**；actual 必须是实读值。
  ② loop/workflows/chunks/model_steps.py 的 N6 `_validate`：除"每用例≥1条/marker唯一/marker 在
     同用例 edits[].new 里"外，新增**可解析校验**：`host.evidence.resolve_expected_imprint(marker,
     run_dir=ctx.run_dir)` 必须返回非空 address+value，否则 problem（点名 marker 与原因）⇒ fail-closed。
     （`_validate` 若当前是纯函数，把 ctx.run_dir 作为参数传入，不改 host/evidence.py。）
  ③ 断言（至少 4 条，放 loop/tests/ 下对应文件）：
     a. 提示词文本必须是 `uvm_info("<marker>"` 形态（不得出现 `uvm_info("N6",` + 方括号消息前缀）；
     b. 合法 marker（能解析到文档条目）+ 合法 edits ⇒ 校验通过；
     c. 不可解析 marker（如 `N6_CHECK_1`）⇒ fail-closed 且原因点名；
     d. **端到端单测**：构造一条真实格式日志行
        `UVM_INFO top_env.sv(154) @ 0.000 us [N6_fpga_date] OK 0x0000+0x04 fpga_date = 0x20260708`
        + 对应的 UVM Report Summary by-id 段 `[N6_fpga_date] 1`
        ⇒ `host.evidence.evidence_view()` 的该印记 `consistent=True` 且 `verdict.passed=True`
        （这条直接证明"新 run 能过 I3"）。
  ④ 只影响新 run：旧 run/夹具不回填；drill/standin 下 `observation_points=null`。

R3-02 重启后真机复核（若用户已重启才做；未重启就跳过并记录原因）
  - 用 `RUN-20261023-171744` 复核：N1–N9 的 story.headline/关键数字/状态释义；N9 未收尾；
    N10–N16"本轮没有走到这个节点（运行停在 failed）"；N4"逐条处置未留存"；N2 黄条与 offset 定位。
  - 截图 + 命令输出写进 doc/evidence/（只增；建议新文件 `NODE_PANEL_ROUND3_20261024.md`）。
  - 注：该 run 是 cancelled/failed，G2/G3 真机仍需下一轮 real run（只登记，不伪造）。

R3-03 N6 面板显示观测点（P-25 第二半）
  - story 增"观测点 N 条"关键数字或可折叠列表（每条：用例 / marker / addr+off / 期望值）；
    `observation_points=null` ⇒ "未下发（旧 run/替身，模型未产出观测点）"。
  - 前端渲染 + 两态断言（有/无）。不放行任何未校验的推断。

R3-04 P-15 已决策态"当时的硬阻断"留存
  - chunks/gates.py::_resumed 的 `decisions/<gate>.json` record 增 `hard_block` 快照
    （`[{code,title,message}]`，取自提交前材料 `precheck`/material；无则 `[]`）。
  - contracts.gate_entries_view 已决策态从 ledger 读 `hard_block` 给面板（只读）；旧 run 无 ledger ⇒
    显示"当时的阻断项未留存（该 run 早于落账）"，不猜。
  - 断言：新 drill run 的 G1 ledger 含 hard_block；面板已决策态显示；无 ledger 的旧 run 显示未留存。

【P0-B｜服务/真机验收（依赖用户重启，做不了就登记）】
R3-05 重启前置与复核记录（同 R3-02；若未重启，在 STATUS/evidence 写"未执行+原因"，不得声称已验）。

【P1-A｜展示补齐（小改动，可并行）】
R3-06 N9/N7 证据按用例分组（P-22③/P-24⑥）：服务端给 `evidence_groups=[{case, refs[]}]`（或 story 字段），
  前端证据区按用例分组渲染；无 refs 的用例显示"本轮未执行/无证据"而不是空白。断言：N9 3 用例 ⇒ 3 组；
  N7 无 refs ⇒ 分组为空 + 原因文案。
R3-07 P-24"可展开看一行示例"：N9 面板显示 detail 里已有的 `example_line`（默认收起，展开见原文）；
  `null` ⇒ 不显示。断言：展开后含该行原文。
R3-08 `not_reached` headline 用中文状态 gloss（failed→失败 / finished→已完成，原值括号保留）；
  断言两种状态文案且不含"等它跑完"。
R3-09 drill 下 submit/编译节点细节补齐：`n9_submit` drill detail 增 `cases`；`n7` drill 的 `cases`
  形态与 story 兼容（`case_count`）；断言 drill 全链 N9_submit 显示"覆盖 1 个用例"而非"未下发"。
R3-10 提前终止下 N15_submit 归因准确：现在 drill 停在更早闸门时也写"演示模式不提交"，归因错。
  改为中性文案"本轮未执行（没有提交记录）"或由 S3 传更早 halt 事实；断言 halt 早停 run 的文案
  不含"演示模式"。

【P1-B｜一致性与清理】
R3-11 新 detail 字段与 `REQUIRED_FIELDS`：把"新 run 才有的字段"（digest_summary/to_check_case_count/
  case_edits/observation_points/identity_table/cases_table/open_items/evidence_groups…）登记为
  §10.4.5 的**可选下限**（不要塞进 REQUIRED_FIELDS，否则旧 run 全报 missing）；断言：新 drill 全链这些
  字段存在（null 也算下发），旧 run 不因缺它们失败。
R3-12 前端未消费契约字段清理（AGENTS 红线 4：字段必须有授权消费者）：`story.headline_source`、
  `gate.entries[].attached[].note` —— 要么消费（attached 展开显示 note），要么从契约移除；补断言。
R3-13 `app.js::renderEntryDecisionHint` 已成死路径（entries 存在时永不生效）：删掉函数与调用，
  或接回"材料不足"真实路径；改完跑 test_web_smoke + test_gate_session。
R3-14 `spikes/run_software_checks.sh` 自带 `-q` + 调用方再传 ⇒ `-qq` 吞掉汇总行：修脚本（去自带 -q
  或检测已含），断言 `bash loop/spikes/run_software_checks.sh tests/test_node_story.py` 输出含 "passed"。
R3-15 `GATE_NODES` 集合（node_story）与 `GATE_ID_BY_NODE`（node_view）是同一事实的两份：合并为单一
  来源（建议下沉到叶子模块 `services/node_registry.py`，node_story/node_view 都引用），删第二份。

【P2｜文档与验收】
R3-16 `doc/UI_RUNBOOK.md` 已过期（line ~524 仍写"v1 未提供逐条处置输入控件"）：先确认该文件是否仍被
  另一条线占用；若已落，更新节点面板/G1 逐条处置/报告全文/G2 材料入口/未到达态描述 + 截图。
R3-17 收尾：SPEC-REV-04 §C.2 对应状态（P-15/P-22/P-24/P-25 的补充项）、`STATUS §52` 追加
  （改了什么/四道门数字/未关闭项，只追加不回填）、evidence 新文件只增。
R3-18 真实轮验收（只登记，不阻塞）：等下一轮 real run 跑到 N16，补 P-13/P-14/P-20/P-21/P-24/P-26/
  P-27/P-28/P-29/P-31/P-32/P-34/P-35 的真机观测；写到 evidence 与 STATUS。

============================================================
4. 明确不要做的事
============================================================
- 不重做已完成的 P 项；不推翻九项裁决（尤其不要给 G2/G3 加勾选处置、不要把模型子事件并入父节点）。
- 不改 `host/evidence.py` 的解析/判据（本轮只让输出可被它解析）。
- 不重启/不 pkill 18098（进程在独立 PID 命名空间，Agent 停不了；需用户手动）。
- 不加新业务写动作；不在节点面板发 POST；不改闸门权威枚举。
- 不 git commit / checkout / stash；不回退另一条线未提交改动。
- 不为了"变绿"放宽/删除断言；缺环境就记录"未执行"，不许把跳过当通过。

============================================================
5. 完成定义（四道门 + 收尾；数字必须复制命令输出）
============================================================
软件层：bash loop/spikes/run_software_checks.sh --ignore=tests/browser
  （基线 656 passed / 3 deselected；本批会新增用例，记录新数字）
浏览器：cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
  .venv/bin/python -m pytest -q tests/browser        （基线 75 passed）
kb 自测：LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py（PASS=10/0）
        LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py（PASS=9/0）
端到端：隔离工具副本（rsync 排除 workspaces/.git/虚拟环境/日志/state/.agently）+ 副本环境：
  LOOP_ENV_ROOT=<repo>/workspaces/real-env-copy LOOP_WORKSPACE=<repo>/workspaces/real-env-copy/kb \
  LOOP_PORT=18199 bash spikes/accept_v1_run.sh        （基线 ALL PASS 117/117；跑完删副本与测试 run）
文档：python3 doc/audit/check_doc_links.py            （missing=0）
N6 印记端到端单测（R3-01④）必须绿——这是本轮"能过 I3"的唯一证据。

收尾：
- SPEC-REV-04 §C.2 对应行状态改「已修（日期）」，未做的保留「未定/待拍板」并写原因；
- doc/STATUS.md 追加 §52（只追加）：改了什么/四道门实测数字/仍未关闭项；
- 新增 doc/evidence/NODE_PANEL_ROUND3_<日期>.md（只增）；引用本轮裁决与证据；
- 不声称"已合规"；未拍板项与"未执行的真机项"必须在 STATUS 与 evidence 保持可见。

============================================================
6. 汇报格式（结束时）
============================================================
1) 改动文件清单（按分片 P0/P1/P2）
2) R3-01～R3-18 逐条状态：已实现 / 依赖用户重启而未执行（写原因）/ 按设计不做
3) R3-01 的 4 条断言（尤其端到端印记单测）实测输出，证明"I3 可过"
4) 四道门：命令 + 实测数字（复制输出）
5) 仍未关闭项：真机验收缺口、旧 run 不回填、UI_RUNBOOK owner、git 提交等
6) 顺手发现但**没有夹带修的缺陷**（只登记）
```

---

## 2 优先级与切片建议（给 Lead 排期用）

| 片 | 内容 | 依赖 | 建议 owner |
|---|---|---|---|
| S1 | R3-01（N6 印记 ID + 可解析校验 + 端到端断言） | 无 | Host 数据面 owner（prompts + model_steps + 测试） |
| S2 | R3-04（闸门 hard_block 落账） | 无 | Host 数据面 owner |
| S3 | R3-03/R3-06/R3-07/R3-08/R3-09/R3-10（story + 前端展示） | S2 的 ledger 字段（R3-04） | story 投影 + 前端两个 owner |
| S4 | R3-11/R3-12/R3-13/R3-14/R3-15（一致性与清理） | 无 | 实现 owner（谁改谁修） |
| S5 | R3-02/R3-05（重启后真机复核）、R3-16/R3-17/R3-18（文档/验收） | 用户重启 | Lead |

**写权互斥建议**：`node_story.py` 与 `node-detail.js`/`index.html`/`app.css` 只能各有一个 owner；
`workflows/chunks/**` + `prompts/**` 一个 owner；`services/{contracts,node_view,api}` 一个 owner（Lead）。

## 3 判据速查（写代码前先看）

- **印记链路**：用例 `uvm_info("<ID>", "OK <addr>+<off> <name> = 0x<value>", UVM_LOW)`
  → 日志行 `UVM_INFO file(line) @ <time> [<ID>] OK …` → `host/evidence.find_imprints()`（ID 必须含 `N6_`）
  → `parse_report_ids()`（by-id 段 `[<ID>] N`）→ `resolve_expected_imprint(ID)`（ID 归一化后含文档条目名）
  → `_verdict`（印记存在 ∧ by-id 计数一致 ∧ 地址/值与文档期望一致）。
  任一环不满足 ⇒ 不得判跑通；**这是 I3 的唯一口径，不要在别处新写判据**。
- **状态原值**：`status` / `decision` 原值必须保留；中文只是展示名（`story.status_note` / glossary）。
- **缺失语义**：`未下发`（服务端没给）/`未执行`（drill 或没走到）/`未到达`（运行终态且无事件）三者不可互换。

## 4 与第一轮开工包的关系

- 本文件**取代** [`2026-10-23-node-panel-revision-kickoff.md`](2026-10-23-node-panel-revision-kickoff.md) 作为下一窗口入口
  （那份是 P-01～P-35 的集中修订包，已完成；保留为历史）。
- 接口契约仍以 [`2026-10-23-node-panel-unified-revision-plan.md`](2026-10-23-node-panel-unified-revision-plan.md)
  §1–§8 为准；本文件 §1 第 3 节只追加新项，不改已有字段语义。
