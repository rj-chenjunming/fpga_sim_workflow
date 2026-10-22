# 项目状态（唯一数字源）

> **本文件是数字的唯一权威**。其它文档引用这里，不各自抄一份。
> **本次采样**：2026-10-19T18:02+0800（修复轮终验，四道门全绿）；采样命令与输出见各节（数字一律复制，不手算）。
> **最新补充采样**：2026-10-21 云环境优化、S0 与 Agent 工作窗口，见 §7–§10；后续优化整理见 §11；全站网页视觉升级见 §12；下一阶段执行手册与当前复核见 §13。
> **2026-10-21/22 后续批次**：F01/F02/F03-a/F16/F16-b/F02-b 见 §14–§21；本批 F13/F03-b/F03-c/F16-c/F02-c/F15-a/F06/F05/F14/F07/F08/F10/F11 见 §22–§32，阻塞清单见 §33，独立验证汇总见 §34。旧采样保留为历史；本轮没有四道门全绿。
> **2026-10-22 拉取后复核**：被测 `a19107c`，受影响集合与浏览器、确定性边界探针及新增待修项见 §35；不覆盖上一执行端的历史采样。
> **2026-10-22 浏览器离线交付**：Rocky 8.10 / x86_64 的 Git 资源、离线安装、浏览器回归及系统库边界见 §36。
> **2026-10-22 下一轮规划**：SpecDD 优化/重构任务与内网逐步验证手册见 §37；本轮仅成册，R1–R5 和后续功能没有在本轮实施。
> **不声称合规**：审计发现但未修复的阻断项在 §5 保持可见。

---

## 1 版本与运行环境

| 项 | 值 | 来源 |
|---|---|---|
| 本仓 HEAD（采样时） | `b4a2443`（修复前基线，tag `pre-fix-20261019`）；修复提交见 `git log --oneline -3` | `git rev-parse --short HEAD` |
| 提交数（采样时） | 14（含基线提交） | `git rev-list --count HEAD` |
| Python | 3.11.7 | `loop/.venv/bin/python -V` |
| Agently | 4.1.4.8 | `pip show agently` |
| 环境仓（ENV_ROOT） | `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` | `environments.json` |
| 数据根（WORKSPACE_ROOT） | `ENV_ROOT/kb`（1.1G） | `du -sh`；决定见 `doc/spec/ENV_PLUGIN_SPEC.md` §7 |

## 2 质量门（修复后终验，2026-10-19）

| 门 | 命令 | 结果 | 说明 |
|---|---|---|---|
| 单测收集 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest --collect-only -q` | **200 tests collected** | 含修复回归（real 链路 / 生命周期 / kb 工具 / 晋升 API） |
| 单测执行 | `cd loop && flock /tmp/cic_loop_pytest.lock env LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | **200 passed, 0 failed**（72.21s） | 基线红 `test_view_projects_authority_not_just_events` 已修（身份复用 + 事件流残留） |
| kb 自测 · gate schema | `loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **10/10** | 需可写数据根 |
| kb 自测 · n5 可达性 | `loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **9/9** | 只读 |
| kb 自测 · n1 快照（F-01） | `loop/.venv/bin/python kb/tools/_selftest_n1_snapshot.py` | **7/7** | 新增；build/stage 不再 NameError |
| kb 自测 · case_state | `loop/.venv/bin/python kb/tools/_selftest_case_state.py` | **16/16** | 新增；含 check/I7 边界 |
| kb 自测 · n10 待裁决 | `loop/.venv/bin/python kb/tools/_selftest_n10_pending.py` | **13/13** | 新增；D1–D20 零改动 |
| 端到端终验 | `cd loop && LOOP_PORT=8098 bash spikes/accept_v1_run.sh` | **rc=0；117/117 断言**（相计数 50/27/18/8/8/6） | 4 代服务进程、3 次真重启；输出在 `loop/.logs/accept/`（本地、不入库） |
| 文档链接扫描 | `python3 doc/audit/check_doc_links.py` | **checked=777 / missing=0**（skipped=9424, historical=834） | 三根解析 + 行号后缀剥离 |

> **real 模式说明**：2026-10-20 已在**真实环境副本**（SCN_RTL_0D04）用 real 模式 + live LLM + 真实编译
> 跑通 **N0→N8**（N2/N5 与预登记答案一致；N7 5/5 编译 rc=0；N8 live pass）；N9 真实全跑按范围在提交后取消。
> 第二轮更长的 real 回归（N9 全跑 ≈50 min/用例）仍未执行；收紧 N6 输入（`api_semantics` + `rtl_effect`）后
> N6 五条修订已与预登记答案键一致（run8）。证据见 [`doc/evidence/REAL_RUN_SCN_RTL_0D04_20261020.md`](evidence/REAL_RUN_SCN_RTL_0D04_20261020.md)。

### 终验历史记录（不是本次实测）

`doc/evidence/ACCEPTANCE_V1.md`：**117/117** 断言（同一脚本、同一断言集）。本轮修复后复跑仍 117/117。

## 3 已知环境限制

1. **端到端必须独占 `loop/state`**：`accept_v1_run.sh` 与并发 pytest 共用 `loop/state/slot.lock` / 作业记录；
   并发会让 phase4 的「单槽被本作业持有」被其它测试伪造的锁污染。门禁顺序：先 pytest，再端到端。
2. **`tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run`** 仍假设
   `WORKSPACE_ROOT` 位于 `ENV_ROOT` 之内；工作区指向外部目录时该断言不成立（布局耦合，非本轮范围）。
3. **real 模式无 live provider 时**：N3/N10/N12 按 fail closed 处理（不再读夹具冒充）；真机端到端需配置模型提供方。
4. `n15_run` 在 drill 下是显式 no-op（不假装回归）；真实回归须 real 模式 + 单槽串行作业。

## 4 数据与归档

| 项 | 状态 |
|---|---|
| `ENV_ROOT/kb/{index,conflicts,baselines,runs,adjudication}` | 存在；`RUN-20261015-120626` 为冻结见证（只读） |
| `loop/state/` | 可删的运行时状态 |
| `doc/evidence/` | 验收报告 + 演练证据（内容冻结，只增不改） |

## 5 审计结论与修复状态（2026-10-19）

- 报告：`doc/audit/AUDIT-20261019-spec-conformance.md`；附录：`doc/audit/parts/`。
- 三路审计原始发现：规格↔实现 **49** 条、Agently 运行时 **44** 条、文档结构 **77** 条（含本轮已执行项）。
- **阻断级**（去重后 22 条）**已全部修复**：real 链路 N1/N6/N7/N9/N15 断裂；N8 模型失败默认 `pass`；
  单槽队列无唤醒；闸门「先签后恢复」失败楔死；槽按进程而非作业判活；N6 不产出沙箱导致 N9 测未修订用例；
  **外加实测 F-01（`n1_snapshot.py` 裸名 `kb_lib` NameError）与 F-02（`n2_diff.py` 主口径按 ENV_ROOT 解析）**。
- 同一轮还修了：I8 人触发真实晋升入口（`POST /api/runs/{id}/promote` + `services/promote.py`）、
  I18 waiting_gate/job/slot 区分、B2 写动作登记（spec §10.0 四个写动作）、证据聚合取最新轮/身份四方同值、
  N10 待裁决单一写者（[n10_pending.py](../kb/tools/n10_pending.py) + schema 加法扩展 `n10_items`）。
- 验收证据：`doc/evidence/FIX_ACCEPTANCE_20261019.md`（四道门命令与输出逐字复制）。
- **仍未修复（非阻断）**：审计报告 §4「重要/次要」中与本轮范围无关的条目仍保持可见；
  真机 real 全跑、72 条冲突清零、I3 双口径裁决仍需人工/环境执行。



## 5.1 本次整理做了什么（2026-10-19）

| 类别 | 变更 |
|---|---|
| 结构归位 | `CHECKPOINT-*` → `doc/history/`；`doc/agents/_demo/`（32 件）→ `doc/evidence/demo/`；`loop/ACCEPTANCE_V1.md` → `doc/evidence/`；34 个 rename 内容逐字节一致 |
| 新增入口 | 根 `README.md`、根 `AGENTS.md`（流程/写权/红线/DoD）、`doc/README.md`、`doc/agents/README.md`、`doc/evidence/README.md`、`doc/history/README.md`、`doc/STATUS.md`（本文件） |
| 迁移记录 | `doc/evidence/demo/MIGRATION.md`（old→new + md5 未变声明）；`CHECKPOINT` 顶部「已过期」横幅 |
| 规格纠偏 | 三份 spec 的状态/完成度/数字/三根路径；`kb/README.md` 按三根重写；`workspaces/README.md` 修 `yaml→json`；`loop/README.md` 统一 117/70/9 |
| 审计落档 | `doc/audit/`（总报告 + 3 份附录 + `check_doc_links.py`） |
| 清理 | `.gitignore` 删两条本仓不存在的规则、`snap.json` 移出版本控制、清 `kb/tools/__pycache__` |
| **UI v1** | 两区运营台：`index.html`+`app.js`+`app.css`；旧界面 `legacy.html`；新增 `/api/baselines`、`/api/env/check`、`/api/fs/dirs`、`run_view.agents/stage_map/project`（见 `doc/spec/WEB_UI_SPEC.md`） |

## 6 待人工拍板（沿用，未变）

| # | 事项 | 材料 |
|---|---|---|
| 1 | I3 双口径分歧（口径一 1687 ≠ 0） | `ENV_ROOT/kb/adjudication/I3_dual_count_dispute.md` |
| 2 | 72 条冲突清零 | `ENV_ROOT/kb/adjudication/C_conflicts_triage.md` |
| 3 | 是否授权改 `TB/`（仅 I3 选项 b 需要） | 环境 `doc/AGENTS.md` 红线 1 |
| 4 | 真机全跑时间窗 | 单用例 ≈19 min，修订后可达 22.8 h |

## 7 云环境优化轮（2026-10-21）

基线提交 `5f6cdb2`；Python `3.12.14`；Agently `4.1.4.8`。整体评估与排序见
[`工作流优化评估`](audit/AUDIT-20261021-workflow-priorities.md)，实施范围见
[`UI 会话可靠性计划`](plans/2026-10-21-ui-session-reliability.md)，原始摘要与命令见
[`本轮证据`](evidence/UI_SESSION_20261021.md)（MD5 `8cace0dd60779e87ee59162f1a209c74`）。这些结果不替代原主机的真机验收。

| 验证阶段 | 实测输出（逐字复制） | 解释 |
|---|---|---|
| 修改前 UI 特征基线 | `3 passed, 10 deselected in 5.66s` | 原交互特征先绿，再改实现 |
| 修改前新增会话回归 | `8 failed, 2 passed, 3 deselected in 54.02s` | 先复现缺陷，失败后才改实现 |
| 提交中切回同门补充回归（修复前） | `1 failed, 13 deselected in 7.25s` | 补充边界先红，再补跨选择的提交锁 |
| 最终 UI 浏览器回归 | `14 passed in 20.81s` | Chromium 加载真实页面；API 受控；不是真机闭环 |
| 后端相关验证 | `56 passed, 4 skipped, 1 warning in 6.33s` | 准入/作业、投影、配置、证据、kb 工具集成及静态页面；跳过项仍需夹具 |
| 修改前全套后端基线 | `61 failed, 132 passed, 6 skipped, 1 warning, 3 errors in 17.10s` | 环境仓及历史夹具未挂载；错误摘要见本轮证据；不声称全套通过 |
| gate schema 自测 | `汇总：PASS=9 FAIL=1` | 独立临时数据根，历史归档缺失项失败 |
| n5 可达性自测 | `汇总：PASS=6 FAIL=1` | 真实用例夹具缺失；相关检查未执行 |
| 文档全库路径扫描（初次） | `checked=804 skipped=10028 historical=834 missing=350` | 环境资产缺失、历史路径及扫描器三根解析误报尚存；不声称零断链 |
| 本轮文档增量检查 | `Additional unresolved inline paths versus HEAD: 0`；`New document Markdown links resolve.` | 使用相同解析规则与 HEAD 比对；本轮未新增缺失路径 |
| 服务启动与静态访问 | `/`、`/app.js`、`/legacy.html` 均返回 `200` | 健康接口同时明确缺插件面与数据面；进程已停止 |

本轮只改 UI 会话与验证文档；没有改执行拓扑、签署、仿真资产或已冻结历史证据。
端到端终验未运行：缺少环境插件、历史 drill 夹具和有效基线。先接入真实数据，再依次跑单测、kb 自测、端到端、文档门。

环境草稿已保存 install_script、start_skill，尚未发布；保存不补齐当前缺失的外部环境或证明新任务恢复。

用户后续确认环境仓位于内网、无法提供给云端。因此本轮交付范围收敛为云端可验证的 UI 会话优化与整体评估；完整质量门由内网侧执行，不再要求外传环境或历史数据。内网复验步骤见本轮计划；冻结证据不回填。

## 8 Agent 上下文与记忆优化（2026-10-21）

用户要求按 SpecDD 优化并沉淀进仓库指令，已更新根 AGENTS.md 的流程、特征测试、写权和记忆纪律。
规格见 [AGENT_CONTEXT_SPEC](spec/AGENT_CONTEXT_SPEC.md)，计划见 [本轮计划](plans/2026-10-21-agent-context-memory.md)，问题与落点见 [本轮复核](audit/AUDIT-20261021-agent-context-memory.md)，命令与输出见 [本轮证据](evidence/AGENT_CONTEXT_MEMORY_20261021.md)（MD5 `ee9d296a736ac2b354104a078caa34df`）。

| 验证 | 原始摘要 | 结论 |
|---|---|---|
| 原实现特征基线 | `4 passed, 22 deselected in 0.73s` | 新 agent、小输入与返工输入等行为先固定 |
| 保持行为的请求契约提取 | `4 passed, 22 deselected in 0.68s` | 先完成局部提取，再改行为 |
| 新功能修改前红灯 | `22 failed, 4 deselected in 1.00s` | 截断、缺记录与经验规则先复现 |
| 缺失/错误差异输入红灯 | `4 failed, 28 deselected in 0.62s` | 再补齐源错误边界 |
| 同用例远处修订点红灯 | `1 failed, 37 deselected in 0.60s` | 先复现只提供首处片段 |
| 认证异常留痕红灯 | `1 failed, 42 deselected in 0.60s` | 先复现配置异常可能带入认证值 |
| API 全文与缓存红灯 | `3 failed, 43 deselected in 0.65s` | 定义尾部与陈旧缓存先复现 |
| 最终独立上下文/记忆测试 | `46 passed in 1.04s` | 受控 provider、独立数据目录；包含新进程分配尝试与核验 CLI |
| 扩展回归 | `2 failed, 139 passed, 4 skipped, 1 warning in 8.07s` | 残留失败依赖真实历史夹具；未新增回归失败 |
| 修改前快照的同组既有测试 | `2 failed, 93 passed, 4 skipped, 1 warning in 8.63s` | 相同失败：drill sandbox 原夹具、N3 原夹具文档不存在 |
| 上轮 UI 浏览器回归 | `14 passed in 21.32s` | 真实页面、受控 API；没有真机仿真 |
| 文档全库扫描 | `checked=810 skipped=10117 historical=834 missing=350` | 沿用环境缺件与原扫描器路径解析问题，不声称零断链 |
| 文档增量与新链接 | `Additional unresolved inline paths versus HEAD: 0`；`New document Markdown links resolve.` | 本轮没有增加未解析路径 |

扩展回归通过环境变量将仅作为 subprocess cwd 的执行目录设为独立临时目录；目录没有内网资产，不是完整模拟环境。完整四道门仍未全绿：kb 历史归档自测和真机/端到端缺件限制沿用 §7，未重复声称执行；本轮文档增量另行核验。

调用记录写本 run 的 agent_calls；经验目录仅人工写，默认不存在即不启用。没有修改拓扑、闸门、kb 工具语义或冻结资产；没有新增认证能力或宣称模型语义已经可靠。

## 9 修订稿 S0 与工作台 UI（2026-10-21）

仅采纳附件 S0，未迁移 S1–S4 或改变既有三个闸门。契约见 [S0 环境准备](spec/S0_ENVIRONMENT_SPEC.md)，计划见 [S0 工作台](plans/2026-10-21-s0-workbench.md)，原始验证见 [本轮证据](evidence/S0_WORKBENCH_20261021.md)（MD5 `770498cb9ab4e8c1bc75f5ecbff3da66`），最终权限边界验证见 [只读基线补充](evidence/S0_READONLY_20261021.md)（MD5 `b4f28552a804e9055422e15b4a672a09`）。由同一实现者分阶段验证。

S0-a 已实现完整派生、RTL 整体替换、非 RTL 比对、基线前后指纹、准备报告与独立 context；重新核验展示漂移而不回填历史。UI 默认进入环境准备，展示两段进度、路径表单、证据、阻断与准备记录，保留现有配置/运行/闸门会话。

**未完成能力保持阻断**：S0-b 外部接口核对、top.sv 自动适配和逐 hunk 登记、真实三库驱动、新版执行入口均未接入，`ready_for_execution` 始终 false。S0-a 完成不能当作 S0 整体准出；现有闭环不代表附件新版 S3。

| 验证 | 原始输出 | 解释 |
|---|---|---|
| 改动前特征基线 | `25 passed, 1 warning in 21.12s` | 既有 UI 会话、静态页面和配置 API |
| 新 UI 红灯 | `1 failed, 14 deselected in 7.33s` | viewS0 尚不存在；实现前先红 |
| 报告失败/丢失边界红灯 | `2 failed, 24 deselected, 1 warning in 0.78s` | 修正报告落盘失败不能留下 prepared 状态 |
| 相关单测与浏览器（权限补充前） | `56 passed, 1 warning in 28.92s` | S0、配置 API、静态资源、真实 Chromium 页面及既有闸门竞态 |
| 只读基线边界红灯 | `1 failed, 26 deselected, 1 warning in 0.74s` | 普通用户不能删除继承只读权限的副本旧 RTL；先复现再仅调整新副本权限 |
| 最终相关单测与浏览器 | `57 passed, 1 warning in 28.81s` | 含原基线权限/内容不变、副本可完成 RTL 整体替换 |
| 扩展回归（报告补充边界前） | `2 failed, 163 passed, 4 skipped, 1 warning in 8.60s` | 相同历史夹具缺失失败，无新增既有回归失败；补充后重跑受影响集合 |
| 实际 API + 临时文件系统浏览器验收 | `S0 browser + real API + controlled filesystem passed`；`pageerrors: []` | 派生、旧 RTL 删除、基线见证、漂移失败、窄屏无溢出；非真实仿真 |
| kb gate schema | `汇总：PASS=9 FAIL=1` | 历史归档缺失，不能算全绿 |
| kb n5 reachability | `汇总：PASS=6 FAIL=1` | 真实用例夹具缺失 |
| 全库文档扫描 | `checked=818 skipped=10140 historical=834 missing=353` | 在最终状态/证据入档前采样；新增未解析引用为未挂载 TB/top.sv 的范围说明，其他仍为原缺件/解析问题 |
| 变更 Markdown 链接 | `Changed Markdown links: all targets exist.` | 仓库文档链接可达；外部环境 inline 路径不等于真实存在 |
| 语法与补丁 | `node --check`（app.js、s0.js）、`git diff --check` 通过 | 桌面与手机截图另做视觉检查 |
| 原端到端验收 | 未运行 | 缺 UVS 插件、有效基线及历史演练夹具；受控 S0 验证不替代真机/完整验收 |

没有要求用户外传内网环境。真实三库编译、TB 逐 hunk 适配/否决回滚与新版执行联动保留为内网接入验收条件；不能宣称四道门全绿或完整 S0 已就绪。

## 10 Agent 工作窗口与运行干预（2026-10-21）

契约见 [工作窗口规格](spec/AGENT_WINDOW_SPEC.md)，计划见 [实施计划](plans/2026-10-21-agent-window.md)，命令和原始输出见 [验证证据](evidence/AGENT_WINDOW_20261021.md)（MD5 `6a4821e192b800040348eaa0a70f0de4`）。同一实现者分阶段验证。

运行监控点击角色卡片/名字可进入窗口，按 run/node/session/attempt 隔离，查看输入、提示词快照、事件、结果与 Host 校验；checker 的 N8/N10 分开选择。运行中可补充指令并重发、暂停、恢复或终止模型请求。新指令进入新尝试，旧响应作废，业务消费者只接收边界返回的有效结果；终止使节点按既有失败机制收敛。控制日志只增不改；幂等、过期、跨会话、取消超时和审计失败均显式处理。

当前暂停限进程存活期间，重启后旧窗口只读；远端推理取消取决于提供方。窗口提供真实运行状态和返回结果，没有隐藏推理、token 流、独立终端或新增并行 Agent 调度能力。没有改写 Gate 签署、既有业务副作用或执行拓扑。

| 验证阶段 | 实际输出 | 说明 |
|---|---|---|
| 改动前模型/记忆/投影/UI 特征基线 | `73 passed in 23.76s` | 先固定原有行为 |
| 单次请求保持行为提取 | `46 passed in 1.02s` | 提取后通过，再增加控制包装 |
| 初始新窗口红灯 | `1 failed in 32.37s` | 尚无可点击入口；新控制模块另有导入收集错误，不当成已执行断言 |
| 跨运行审计身份红灯 | `1 failed, 20 deselected, 1 warning in 0.61s` | 有效指纹仍须校验所属运行/节点/会话 |
| 迟到回执跨新会话红灯 | `1 failed, 6 deselected in 7.12s` | 防止旧回执清空新会话草稿 |
| 取消超时作废记录红灯 | `1 failed, 22 deselected, 1 warning in 0.62s` | 旧尝试须在取消前退休，晚到结果不消费 |
| 相关综合验证 | `141 passed, 1 warning in 33.12s` | 控制、记忆、投影、S0、API/静态资源和浏览器；受控 provider |
| 尝试选择器/响应身份补充红灯 | `2 failed, 7 deselected in 13.36s` | 重开复位到最新；不匹配身份的响应禁用控制 |
| 最终受影响浏览器验证 | `28 passed in 35.78s` | 补充后只重跑浏览器集合，含原闸门与 S0 回归 |
| 扩展后端回归 | `2 failed, 189 passed, 4 skipped, 1 warning in 7.44s` | 仍为原历史夹具缺失两项，无新增既有回归失败 |
| 浏览器 + 实际 API + 受控异步 provider | `Agent window real API acceptance passed`；`consumed_outputs: 1`、`model_attempts: 4`、`pageerrors: []` | 暂停、补充并恢复、再次暂停、恢复、终止；只有有效结果被消费。工作流投影为测试装置，不是真实模型/仿真 |
| kb gate schema | `汇总：PASS=9 FAIL=1` | 历史归档缺失 |
| kb n5 reachability | `汇总：PASS=6 FAIL=1` | 历史用例夹具缺失 |
| 文档扫描（最终归档前） | `checked=820 skipped=10176 historical=834 missing=353` | 沿用环境缺件/扫描器解析限制 |
| 文档增量及链接 | `Additional unresolved inline references: {}`；`Changed Markdown links: all targets exist.` | 本轮无新增未解析引用 |
| 语法/补丁/冻结件 | `node --check`、`git diff --check` 通过；`Previous frozen evidence: unchanged.` | 桌面/手机截图已视觉检查 |
| 完整端到端 | 未运行 | 内网有效基线、UVS 插件和历史夹具缺失；请求边界验收不替代完整工作流 |

真实 provider 的取消/重发行为、真实节点消费者及失败后的槽释放、进程重启恢复和完整真机闭环仍需内网验收；当前不声称四道门全绿。

## 11 后续优化与特征重构整理（2026-10-21）

本轮仅整理和只读复核，未修改运行代码或实施后续功能。评估覆盖 HEAD `5f6cdb2` 加工作区既有修改；[审计](audit/AUDIT-20261021-specdd-followups.md) 按 F-ID 区分已确证缺陷、能力缺口、待测风险、保持行为重构与产品增强；[路线](plans/2026-10-21-specdd-followups.md) 给出规格、owner、特征基线、目标验收、依赖和回退边界。同一执行者复核，没有独立验证者。

最高优先级为 F01：基线列表把仅有空 manifest 的目录标为有效；N2 在非默认基线输入下仍传 v0；源码还显示创建入口缺完整基线校验、N0 未传选中 manifest。已确认局部行为，不声称已在内网复现整链影响。F02 的 guardian 旧提示、F03 文档工具根解析误判也经受控探针复核。S0-b、持久暂停与并行委派继续登记为未实现/待立项。

| 检查 | 本轮输出 / 状态 | 范围 |
|---|---|---|
| 受控只读探针 | `manifest_only_baseline: valid=true`；`n2_selected_baseline: requested=v-next, --from-baseline=v0`；`guardian_idle: 未实现（审计 A10）`；`tool_root_reference: local_exists=true, resolved=None` | 临时文件树，截获 N2 工具调用；没有运行真实工具、模型或仿真。退出码 0 表示观察脚本完成，不表示缺陷通过验收 |
| 全库文档扫描 | `checked=820 skipped=10209 historical=834 missing=353`；退出码 1 | 新评估/路线和导航写入后、§11 与证据入档前采样；外部缺件及原解析问题仍在，不声称零断链 |
| 本轮链接/来源定位 | `PASS: new document links, source line references and navigation anchors resolve.`；`PASS: audit finding IDs map to implementation slices.` | 仅新增评估、路线、证据，以及 README/STATUS 的新增入口 |
| 补丁空白检查 | 退出码 0，无输出 | `git diff --check` |
| 业务单测 / 浏览器 / kb / 完整端到端 | 未运行 | 文档整理无运行代码变更；既有结果保留在 §7–§10，不复用为本轮实测；内网限制持续有效 |

原始探针、复现方法和文档核验见 [本轮整理证据](evidence/SPECDD_FOLLOWUPS_20261021.md)（MD5 `de7cca1b8e08a7e8be332e62b340fc8b`）。本轮完成的是评估与计划，不是上述缺陷修复，也没有完成四道门全绿。

## 12 全站网页视觉重设计（2026-10-21）

用户选择专业清爽，最终澄清仅需浏览器网页，不开发桌面客户端或手机端专项设计。规格见 [Web UI §14](spec/WEB_UI_SPEC.md#14-全站网页视觉系统2026-10-21)，[计划](plans/2026-10-21-desktop-redesign.md)，[预览及命令证据](evidence/WEB_REDESIGN_20261021.md)（MD5 `3432596b4f5c2a5a4ffaddf0b11af353`）。同一执行者分阶段实施与验证，没有独立复核。

统一工作台及旧界面的颜色、字号、间距、表单、卡片、状态与焦点；四视图入口集中在侧栏，支持方向键和跳到工作区。S0、运行配置、执行阶段、Agent 卡片/窗口、闸门材料/操作、目录浏览器均已更新。状态、准出、草稿隔离与业务授权沿用既有 Host/API；未扩大环境写权。

| 检查 | 实际输出 / 状态 | 范围 |
|---|---|---|
| 实现前浏览器特征基线 | `28 passed in 41.26s` | 原 S0、闸门会话与 Agent 窗口 |
| 综合浏览器与静态页面验证 | `39 passed, 1 warning in 56.31s` | 配置行最后细调前；警告为既有 TestClient 弃用提示 |
| 最终受影响网页集合 | `8 passed in 15.59s` | 浏览器宽度 1280/1440/1920；四页、目录、长路径、Agent 控件、旧页返回、键盘导航及异常状态 |
| 实际 API 静态资源 | `PASS: shared styles and compatibility console are served by the actual API.` | 首页、共享令牌、主样式/脚本、旧页及旧页样式均 HTTP 200 |
| 脚本语法与补丁 | `node --check`、`git diff --check` 退出成功 | app.js、s0.js、agent-window.js；保留零外部依赖 |
| 预览与来源 | Chromium 截图已视觉检查 | 受控 API 数据，非真实模型/内网仿真；截图 MD5 见证据 |
| 文档与冻结件 | `PASS: changed Markdown links and screenshot targets resolve.`；`PASS: no additional unresolved inline paths versus HEAD.`；`PASS: previously frozen evidence contents are unchanged.`；`PASS: archived screenshot MD5 values match the evidence report.` | 变更文档增量；不声称全库零断链 |
| 业务全套 / kb 自测 / 完整端到端 | 未运行 | 本轮为网页展示与导航，不改后端判据；内网缺件限制沿用既有记录 |

验证中修正了旧页 events 响应及加载容器选择两处测试装置错误，原始失败输出见证据，不作为产品缺陷先红后绿。最终局部集合通过不等于再次执行完整业务四道门；本轮仍不声称四道门全绿。

## 13 下一阶段优化与重构成册（2026-10-21）

复核基线 `d7cf7c6`。用户要求准备后续优化/重构并成册提交；本轮交付 [执行手册](plans/OPTIMIZATION_PLAYBOOK.md)、[当前复核](audit/AUDIT-20261021-post-ui-roadmap.md) 与 [受控探针证据](evidence/NEXT_STAGE_REVIEW_20261021.md)（MD5 `0e1258c4bfe2b296ccde54f86f651604`）。同一执行者只读复核，不是独立终验。

F01–F12 延续原编号，新增 F13 首次错误反馈、F14 样式收敛、F15 规格/验证入口治理；手册列出优先级、owner、依赖、实施步骤、目标验收、回退、提交切片和领取模板。建议先完成基线准入/身份，再修能力与错误提示、隔离验证，随后拆分样式/前端/模型节点；S0-b、持久暂停和性能优化分别按协议、故障与测量推进。没有执行这些后续修复。

| 本轮检查 | 原始输出 / 状态 | 说明 |
|---|---|---|
| 基线只读探针 | `manifest_only: valid=true`；`manifest_array: exception=AttributeError`；`n2_baseline: requested=v-next, actual=v0` | 临时目录与截获参数；没有真实 N2 执行 |
| 能力提示 | `guardian_idle: summary=未实现（审计 A10）` | 已有 N11 实现与旧提示不一致 |
| 文档解析 | `tool_reference: local_exists=true, resolved=None, root=env?` | 本仓工具根解析误判仍在 |
| 网页首次失败探针 | `head=A\n加载中…\n读取失败`；`claims_previous_success=true`；`write_requests=0`；`page_errors=[]` | 受控首次 503，实际静态网页；证明现有反馈问题，不代表缺陷验收通过 |
| 文档链接与路径增量 | `PASS: changed Markdown links, anchors and source line references resolve.`；`PASS: no additional unresolved inline paths versus HEAD.` | 本轮变更范围，不声称全库缺件已消除 |
| 任务覆盖 | `PASS: F01-F15 task cards, priority table and dependency references agree.` | 总表、任务卡和依赖编号一致 |
| 冻结件与实现边界 | `PASS: prior evidence, history and audit content MD5 values are unchanged.`；`PASS: loop/kb implementation has no diff against HEAD.` | 旧证据/审计未回填，未改变业务实现 |
| 语法与补丁 | `PASS: read-only probe Python syntax is valid.`；`PASS: git diff --check.` | 探针 AST 解析及补丁空白检查 |
| 业务单测 / 完整浏览器集 / kb / 完整端到端 | 未运行 | 本轮是成册与只读复核，未改变实现；不复用 §12 为本轮结果 |

性能、进程杀断恢复、真实三库和非默认基线整链影响均未在本轮实测；不声称它们已复现事故、已修复或四道门全绿。既有环境限制和未完成能力继续有效。

## 14 F01 基线准入与全链身份（2026-10-21）

基线提交 `fb83ed0`。规格 [编排规格 §3.1](spec/LOOP_ORCHESTRATION_SPEC.md#31-基线准入与身份f01) 与
[Web UI §6.1/§6.4](spec/WEB_UI_SPEC.md)，计划见 [F01 切片计划](plans/2026-10-21-F01-baseline-admission.md)。
本切片由 Lead 实现；**会话内独立复核 `f01-verifier`（只读两轮：首轮 3 项必改 → 修复 → 二轮「可合并」）**，
复核报告未落盘为独立文件（流程偏差见 §19）；数字一律从命令输出复制。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 修改前红灯（临时回退三处接线） | `10 failed, 2 passed in 0.74s` | 空 manifest 对象仍 `valid=true`、数组 manifest 触发 500、N2 仍传 `--from-baseline v0` |
| 修改后新用例 | `12 passed in 0.60s` | 判据/准入零副作用/身份传递三类可观察行为 |
| 既有配置契约用例（含按新契约更新的一条） | `19 passed in 0.62s` | `test_list_baselines_reads_manifest` 原先把「只要 manifest 可解析」写死，已改判 `valid=false` + 显式缺件 |
| 真实基线 v0（本机只读环境根） | `v0 valid= True missing= [] errors= [] cases= 162 rtl_bytes= 2570240` | 新判据在真实七件套上通过，未误伤既有基线 |
| 全套单测 | `46 failed, 264 passed, 3 skipped, 1 warning in 11.91s` | 46 项与拉取后基线**同因**（`ENV_ROOT` 只读导致 `mkdir` OSError），非本轮回归；通过数 252→264 = 新增 12 项 |
| 补丁空白检查 | `git diff --check` 退出成功、无输出 | —— |

`real` 模式准入发生在建运行目录/隔离投影/写事件/占槽之前（用例以 spy 固定「未调用 `prepare_run_dir`」）；
`drill` 不做基线准入（走夹具），行为未变。**未运行**：kb 自测、端到端、真实**非默认基线**整链
（F01-d 阻塞：缺内网环境与有效非默认基线）。因此**不声称四道门全绿**，也不声称 F01 全部完成。

**独立复核（`f01-verifier`，只读、未改文件）**：结论「不建议按现状合并」，必改 3 项已在同一轮修复。

| 复核发现 | 处理 | 修复后验证 |
|---|---|---|
| N1/N2 仍各带 `or "v0"` 兜底，与「任何节点不得再出现硬编码 v0」不符 | 新增 `_selected_baseline()`：`run_meta` → 输入 → **fail closed**；API 层第二份 `or "v0"` 删除 | `tests/test_fix_real_chain.py -k n1`：`16 passed, 23 deselected in 1.16s`；新增 N2 缺身份用例 |
| 准入用例红态用「返回 None」的 spy，反而落盘 loop/None 与 stale 事件 | spy 改为「被调用即断言失败」；负例增加事件目录零新增断言；残留已清理 | 定向 `22 passed in 0.62s`；仓库无 loop/None 与新增 stale 件 |
| 规格称 `doc_fingerprint` 核指纹，实现只查存在 | 按 kb 唯一口径 `canon_lines_sha256` 重算（真实 v0 复算一致） | 真实 v0 仍 `valid= True`；篡改用例由绿转红 |
| 符号链接基线被列表静默跳过（坏件伪装成不存在） | 列表只收 `^v[0-9]+$` 形状；符号链接**列入**但 `valid=false` | 新增用例断言其出现在列表且报「符号链接」 |
| 绝对路径 artifact 无边界 | 限定在工作区根 / 环境根内，越界计入 `missing` | 代码收敛（边界用例待补） |

复核后全套：`46 failed, 269 passed, 3 skipped, 1 warning in 11.26s`（46 项同因但错类不同：44 项 `Errno 30`、2 项 `test_archive_e2` 的 `guard rc=3`/`FileNotFoundError`；均因 `ENV_ROOT` 只读；
通过数 252→269 = 新增 17 项）。定向：`24 passed in 0.64s`；`/api/baselines` 契约用例通过。

复核者二次回归结论：**可合并**（3 项必改均有代码+实测证据关闭，无新增中/高危）。其列出的低项已在本轮
顺手关闭：`host/baseline.py` docstring 与限根逻辑对齐；补 N1 fail-closed 与绝对路径越界两条用例。
仍余后续项见下。

**登记为后续（本轮不做）**：①`kb/tools/` 子进程未加 `-B`（既有行为，可向冻结目录写 `__pycache__`）；
②`services/contracts.py::baseline_chain()` 是第二套 manifest 扫描（进闸门材料，未复用 §3.1 判据）；
③`/api/baselines` 失败 detail 未带 `missing/errors`。

## 15 F02 能力说明与实际状态对齐（2026-10-21）

规格 [Web UI §4.3 能力事实](spec/WEB_UI_SPEC.md)、§7 第 6 条、§10-A9；计划见
[F02 切片计划](plans/2026-10-21-F02-capability-facts.md)。由 Lead 实现并自测，独立复核未做（流程偏差见 §19）。

旧结论「N11 证据守护未实现（审计 A10）」在四处已过期（服务端 note/summary、`app.js::deriveNote`、规格、既有用例），
而 `n11_review` 已有成链判断/返工/身份四方同值实现。本切片改为**服务端下发四维能力事实**，
UI 只消费、不再从 `idle` 或颜色推断。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 修改前红灯 | `3 failed, 7 passed in 0.64s` | 旧实现无 `capabilities`；guardian 文案含「未实现」 |
| 修改后单测 | `10 passed in 0.54s` | 四维字段、idle 不称未实现、standin≠real |
| 浏览器目录收集 | `10 passed, 3 skipped in 0.58s` | 浏览器模块因缺 playwright 整组 skip |
| 全套单测 | `46 failed, 271 passed, 3 skipped, 1 warning in 11.31s` | 46 项与拉取后基线同因（`ENV_ROOT` 只读），无新增回归 |
| 前端语法 | `node --check web/app.js` 通过 | 仅证明可加载，不替代浏览器行为 |

**未运行**：`tests/browser` 的真实 Chromium 断言。本机尝试安装时 PyPI 连接超时
（`ReadTimeoutError ... pypi.org`、`Could not find a version that satisfies the requirement playwright<2,>=1.50`），
系统存在 `/usr/bin/google-chrome`，但缺 `playwright` Python 包（PyPI 不可达）⇒ 浏览器用例仍无法在 pytest 中执行；因此**不声称 UI 已在浏览器中验证**。

## 16 F03-a 验证隔离最小切片（2026-10-21）

规格 [环境插件规格 三根表](../doc/spec/ENV_PLUGIN_SPEC.md)（新增 `STATE_ROOT` / `$LOOP_STATE_ROOT`）；
计划见 [F03-a 切片计划](plans/2026-10-21-F03a-test-isolation.md)。由 Lead 实现并自测，独立复核未做（流程偏差见 §19）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 修改前红灯（stash 三处改动） | `3 failed, 1 passed in 0.69s` | `$LOOP_STATE_ROOT` 注入/测试隔离/子进程 `-B` 先红 |
| 修改后 | `4 passed in 0.62s` | 四项全绿 |
| 全套单测 | `46 failed, 275 passed, 3 skipped, 1 warning in 11.23s` | 46 项同因（44 `Errno 30` + 2 `test_archive_e2` 同根因不同错类）；通过数 271→275 = 新增 4 项 |
| 冻结目录字节码 | `find kb/tools -name '*.pyc' -newermt <start>` 无输出 | kb 工具子进程已带 `-B` |

**验证边界**：共享 `loop/state/recovery` 由**沙箱 PID 命名空间外的常驻服务**持续改写（空闲 3 秒内容也会变，
沙箱内 `ps` 不可见），故不能用 mtime/md5 反证「测试未写共享 state」；证据改为进程内 `STATE_DIR`
指向一次性目录的断言。**未解决**：46 项 `ENV_ROOT` 只读失败（F03-b 需按测试类别注入可写数据根），
F03-c 文档解析器根解析，多环境按 `ENV_ID` 分区 state/槽键。

## 17 F03-b 软件层入口与新发现 F16（2026-10-21）

计划见 [F03-b 切片计划](plans/2026-10-21-F03b-software-layer.md)。新增
`loop/spikes/run_software_checks.sh`：可写影子数据根（`runs/` 新建、`index/conflicts/adjudication` 浅拷贝、
`baselines/` 与 drill 夹具轮 `RUN-20261015-120626` 符号链接）+ conftest 注入的 `$LOOP_STATE_ROOT`。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 默认根 | `46 failed, 275 passed, 3 skipped in 11.23s` | 46 项全为只读 `OSError` |
| 影子根首跑（未链夹具） | `44 failed, 271 passed, 9 skipped in 650.84s` | 失败转为 `AssertionError`（N0/N1 缺 drill 夹具） |
| 链接夹具后 `test_flow.py` | `11 failed`（18 项中） | 链路可执行，暴露 F16 |
| F16 修复后软件层全套 | `3 failed, 325 passed, 3 skipped in 83.51s` | 剩余 3 项为环境层（需可写 `ENV_ROOT`）；软件层已可重复执行 |

### F16 · N6 上下文预算超限（阻断）

```
RuntimeError: 闸门 G1_diff_confirm 已签署但恢复失败（run 已置 failed）：
  agent context budget exceeded（上下文预算）: 130546 > 120000 bytes
```

复现：`bash spikes/run_software_checks.sh tests/test_flow.py::test_gates_are_recorded_once_each`。
**构成实测**（探针包裹 `check_budget`）：N6 输入 41 KB（`targets` 36923）；**N8 输入 130546**
（主要项 `sandbox_cases` **120063**、`revision_points` 6453、contract 2728，其余为 checklist/rule/applied_edits
等小额项——逐项相加与 total 因序列化方式不严格相等）。**复核更正**：drill 只有 5 个用例文件且都 >6000 字符，
F16 前已在用片段；120063 来自片段 **after 文本在 excerpt/changed_regions 重复** + 15 行上下文窗口，
不是「小文件整篇下发」。超限在 N8，不是 N6。
`check_budget` 显式失败 ⇒ drill 全链在 G1 后收敛为 failed；默认只读根下因更早的 `mkdir` 失败而未暴露。
**未修**；修法：N8 按 touched 行分片 + 显式 `coverage`、消除 N6 `excerpt`/`excerpts` 重复、
必要时再按 provider 窗口重定预算（先改规格）。该缺陷使**四道门端到端在本机不可判为通过**。

**未完成**：F03-b 的测试分层标记（纯软件/受控插件/真实内网）与剩余失败分类、F03-c 文档解析。

## 18 F16 N8 上下文预算分片（2026-10-21）

规格 [上下文规格 C1](spec/AGENT_CONTEXT_SPEC.md)、[编排规格 N8 行](spec/LOOP_ORCHESTRATION_SPEC.md)；
计划见 [F16 切片计划](plans/2026-10-21-F16-n8-context-budget.md)。由 Lead 实现并自测，独立复核见本节末。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 修改前红灯（新用例） | `5 failed in 0.60s` | `build_sandbox_cases` 尚不存在 |
| 修改后新用例 | `5 passed in 0.56s` | 预算内全文 / 超预算降级 / 确定性 / 缺源闭锁 / 小输入保持 |
| N8 相关既有用例 | `51 passed in 1.29s` | 大文件强制片段规则保持不变 |
| 软件层单用例（原阻断） | `1 passed` | G1 后不再 budget failed |
| 软件层 `test_flow.py` | `18 passed in 26.54s` | 修复前同一入口 `11 failed` |
| 默认根全套 | `46 failed, 282 passed, 3 skipped, 1 warning in 11.29s` | 46 项同因（44 `Errno 30` + 2 `test_archive_e2` 同根因不同错类）；通过数 275→282 = 新增 7 项 |
| **软件层全套**（`run_software_checks.sh`） | `3 failed, 325 passed, 3 skipped, 1 warning in 83.51s (0:01:23)`（复核整改后；整改前 `323 passed / 75.95s`） | 修复前同一入口 `44 failed, 271 passed, 9 skipped in 650.84s`；剩余 3 项为**环境层**（archive/guard 需可写 `ENV_ROOT`、冻结见证），非软件层缺陷 |

实现：单文件 >6000 字符仍强制 `changed_regions`；其余默认全文；超
`N8_SANDBOX_BUDGET_BYTES`(60000) 按文件名顺序降级；`changed_regions` 不重复下发 after 文本
（after 只在 `excerpt`），按实际序列化大小计费；片段不可得即 fail closed（不静默抽样、不丢文件）。

**未运行**：浏览器（缺 `playwright` Python 包；系统有 `/usr/bin/google-chrome`）、kb 自测与端到端（`ENV_ROOT` 只读）。

### 18.1 独立复核（f16-verifier，只读）

结论：**建议合并**（无静默失败/丢文件，drill 已恢复）。必修改 3 项已在本轮修复：

| 复核发现 | 修复 | 验证 |
|---|---|---|
| 打包按单条求和，漏计数组括号/逗号 2n 字节 ⇒ 预算边界上可硬拒可行解 | 单条计费 +2 字节；结束时用实际序列化复核，并从后往前**确定性降级全文条目**直到装下 | 新增边界用例 `test_budget_boundary_does_not_reject_feasible_plan` |
| `used_bytes` 用默认 `json.dumps`，与真实 `AM.encoded` 口径不同（高估 209 B），注释不成立 | 改用 `AM.encoded`（与 `check_budget` 同一实现），删除被覆盖的死代码 `total_min` | 新增 `test_used_bytes_matches_compact_encoding` |
| 诊断与实测不符（drill 5 件全 >6000 字符，"小文件整篇"不成立）；`n=15→6` 无规格依据 | 更正 §17/计划的诊断；片段上下文窗口写入 C1（`N8_REGION_CONTEXT_LINES=6`） | 规格 C1 已同步 |

**勘误**：`6c88c06` 提交信息中「120063 + 9276 = 131046」的加和不准确（131046 是探针实测总输入，
不是两项相加）；以本节与 §17 的口径为准。

## 19 流程偏差与整改（2026-10-21）

本节记录本轮（`fb83ed0..HEAD`）**已发生**的 SpecDD 偏差，不补造证据、不回填历史。

| 偏差 | 事实 | 严重度 | 整改（后续切片执行） |
|---|---|---|---|
| 计划后置 | F01/F02/F03-a/F16 的计划与实测写在实现之后（同会话回填）；只有 F16 的 playbook 登记早于实现 | 中 | 计划必须在实现**前**单独提交（含切片/落点/验证门，不含实测） |
| 红灯事后制造 | F01/F03-a 先实现，再临时回退/stash 造红并记录；F02/F16 为测试先红 | 中 | 失败用例先提交并贴原始输出，再提交实现；禁止回退造红 |
| 独立验证未落盘 | F01 两轮、F16 一轮均为会话内只读 agent；仓库无独立报告文件 | 高 | 验证结论必须落 `doc/audit/Fxx-verify-<date>.md` 并记 md5，或明确写「无独立报告」 |
| 文档门缺证 | 前几个提交未跑 `check_doc_links.py`；本轮补跑：`checked=860 skipped=10688 historical=834 missing=6`，其中 2 条为本文档自身引用已删除的 loop/None（已改文案），其余为环境资产缺件 | 中 | 每个文档变更提交附该门输出；缺件按已知限制登记 |
| DoD 四道门未全绿 | 单测仅软件层可判（323 passed / 3 环境层 failed）；kb 自测与端到端未运行（`ENV_ROOT` 只读/内网缺件） | 高 | 维持「不声称合规」；内网侧补跑后回填 |
| 数字口径 | 两处加和错误、46 项失败表述过粗（实为 44 + 2） | 中 | 数字必须来自命令输出；跨字段加和需注明不适用情形 |
| 文档门自引用漂移 | 记录 missing 数时又把 `TB/top.sv` 写回文档，导致下次扫描 +1（F16-b 复核两次遇到） | 中 | 环境缺件登记 `KNOWN_MISSING`（`doc/audit/check_doc_links.py`）并写明理由；文档门以登记后 `missing=0` 为准 |
| 文档门诊断计数不稳定 | F02-b 连续三次记录 `skipped` 均与同树实测不符（11006→11029、11279→11302）：**记录动作本身**会新增被扫描的代码跨度 | 中 | 门禁只认**退出码 + `missing`**；`checked/skipped` 仅诊断、不回填；需要趋势时单独落盘快照文件而非写进被扫文档 |

## 20 F16-b coverage 语义与空沙盒闭锁（2026-10-21）

规格 [C1](spec/AGENT_CONTEXT_SPEC.md)、计划 [F16-b](plans/2026-10-21-F16b-coverage-and-empty-sandbox.md)。
按 §19 整改执行：**计划+规格先提交**（`2701b38`）→ **红灯用例提交**（`ef8b7b1`、`b55c982`）→ 实现提交（`1da772f` 等）→ 独立复核报告（`2c08420`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 失败用例先红（`ef8b7b1`） | `3 failed, 9 passed in 0.78s`（`DID NOT RAISE RuntimeError` ×3） | 缺目录 / 空目录 / applied 非空无文件；**5 条新增中 3 条真红**，另 2 条为护栏断言（红灯提交即绿） |
| 补充红灯（`b55c982`，复核必改 1） | `1 failed, 12 passed in 0.71s` | applied 部分缺文件未闭锁 |
| 实现后定向（文档化命令） | `59 passed in 1.46s` | `test_n8_context_budget.py + test_agent_context_memory.py` |
| 默认根全套 | `46 failed, 288 passed, 3 skipped, 1 warning in 12.38s` | 46 项同因（44 `Errno 30` + 2 归档）；通过数 282→288 |
| 软件层全套 | `3 failed, 331 passed, 3 skipped, 1 warning in 78.14s (0:01:18)` | 同上 3 项环境层；闭锁不误伤 5 个夹具用例 |
| 文档门 | `checked=881 skipped=10960 historical=834 missing=0` | 把环境缺件 `TB/top.sv` 登记进 `KNOWN_MISSING` 后零断链（登记理由见 §20.1；此前 877/10879/834/4 的自引用漂移已消除） |

实现：`build_sandbox_cases` 在无 `*.sv`（含目录缺失）时显式 `RuntimeError`，并**逐用例映射**检查
`applied_cases` 的每个文件都存在；`n8_check` 在闭锁时先 `ctx.node_failed` 再抛；
`coverage.complete` 语义写入 C1，N8 提示词同步解释（不是全文复核）。

### 20.1 独立复核（f16b-verifier，报告已落盘）

报告 [doc/audit/F16b-verify-20261021.md](audit/F16b-verify-20261021.md)，md5 `7994fddc6c32e9ec6c28b2446a446222`
（2026-10-21 回归复核版；初版 `22d24be…` 对应提交 `2c08420`）。

**首轮**：建议合并，2 项必改——① applied 部分缺文件未闭锁（已修：逐用例映射 + 红灯 `b55c982`）；
② §20 数字不可复现（已用文档化命令重测：59 passed / 46-288-3 / 3-331-3）。
**回归复核（`258c551`）**：① 闭锁消息含缺失与现有名单，红灯/复绿可复现；② drill 5 件夹具 50746B 未误伤；
③ 数字一致；④ 文档门自引用漂移已用 `KNOWN_MISSING` 登记 `TB/top.sv`（环境资产，本机未挂载）后止住：
`checked=881 skipped=10960 historical=834 missing=0`，退出码 0。

残余：错误消息内容与「节点级模型未被调用」尚无自动化断言；`complete` 仍恒 true（语义已写入 C1 与提示词）。

**未运行**：浏览器、kb 自测、端到端。

**§19 整改执行记录（F16-b）**：本轮已按新流程执行——计划+规格先提交（`2701b38`）、红灯用例单独提交
（`ef8b7b1`、`b55c982`）、实现后提交、验证者报告落盘（`2c08420`）并由 Lead 记录 md5；无回退造红，
提交顺序与红灯输出均可在 git 与本节核对。

## 21 F02-b 基线错误结构化 detail 与前端展示（2026-10-21）

规格 [Web UI §6.4 / §6.1](spec/WEB_UI_SPEC.md)、计划 [F02-b](plans/2026-10-21-F02b-baseline-error-detail.md)。
顺序遵循 §19：**计划+规格先提交**（`29626db`）→ **红灯用例**（`fcfefa3`）→ 实现（本节提交）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 失败用例先红 | `2 failed, 1 passed in 0.81s` | 未知基线 / 坏 manifest 的 400 只有 error |
| 实现后定向 | `3 passed in 0.76s` | 含「非基线 ValueError 形态不变」 |
| 前端语法 | `node --check web/app.js` 通过 | 不替代浏览器行为 |
| 默认根全套 | `46 failed, 291 passed, 3 skipped, 1 warning in 11.23s` | 46 项同因；通过数 288→291 |
| 软件层全套 | `3 failed, 334 passed, 3 skipped, 1 warning in 72.07s` | 仍为 3 项环境层（archive ×2、冻结见证） |
| 文档门（最终口径） | 退出码 `0`、`missing=0` | `checked/skipped` 是**诊断值**且会因记录动作本身改变（复核实测同一提交 11029/11302），**不再作为门禁数字**；详见 §21.1 |

实现：`api.py` 仅对 `BaselineInvalid` 返回 `{error, baseline, missing[], errors[]}`（取判据的 `details`，
不二次推导；其它 `ValueError` 形态不变）；`app.js` 的 `errText` 追加「缺件/违规」，配置视图基线提示与
目录选择器展示 `errors`；`BaselineInvalid` 的 message 改为只给身份（缺失件/违规由 detail 承载，避免 UI 双份展示），
`errors` 超过 3 条时标注总数。**未运行**：浏览器断言（缺 `playwright` Python 包；系统有 google-chrome）——
UI 仅有语法检查与静态审查，F13 一并补浏览器用例。

### 21.1 独立复核（f02b-verifier，报告已落盘）

报告 [doc/audit/F02b-verify-20261021.md](audit/F02b-verify-20261021.md)，md5 `47af1e563e6f736984c39888e4209e48`
（含回归复核小节；初版 md5 `36a66e6a…`）。首轮结论 **建议合并**，2 项必改：① 契约引用误写 §9（实为 **§6.4**）；
② 文档门计数不可复现。建议项：`errText` 去重、违规截断标注、浏览器表述更正为「缺 playwright 包、系统有 google-chrome」。

**回归复核（停在 `3b9475f`）的发现与最终处置**：
- 必改 1：当时仍漏 `STATUS §21` 一处 §9（与「5 处已修复」的表述矛盾）——已在后续提交补齐（含 F01 行的 §6.1/§9→§6.1/§6.4）。
- 必改 2：`skipped` 在 `3b9475f` 干净树实测 11302（记录 11279）——根因是**记录动作本身引入被扫描的代码跨度**。
  处置：门禁口径改为「退出码 0 + `missing=0`」，`checked/skipped` 仅作诊断且不再回填（见 §19 新行）。
- 诚实边界：独立复核**未覆盖**最后一处 §9 修复与本口径变更；登记为残余，下一轮切片复核一并确认。
复核已确认（`3b9475f` 状态）：detail 四字段与 `host.baseline.inspect` 逐项相等（无二次推导）、拒绝零副作用、
红灯（`git archive fcfefa3`）`2 failed, 1 passed` 真实、失败集与 `f4f0979` 逐个相同。

## 22 F13 首次失败 vs 刷新失败（2026-10-21/22）

计划 [F13](plans/2026-10-21-F13-first-refresh-errors.md)，规格 [Web UI §7.2](spec/WEB_UI_SPEC.md#72-首次加载首次失败与刷新失败2026-10-21-f13)。
顺序：**计划+规格**（`fd67ee3`）→ **红灯**（`91b85a4`）→ **实现**（`056f911`）→ **复核报告**（`274a406`）→
**整改**（`219fb70`）→ **复核建议项**（`d272a80`）。数字一律从命令输出复制。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯（模块不存在） | `7 failed in 1.19s` | `Cannot find module .../web/run-view-state.js` |
| 实现后定向 | `7 passed in 1.21s` | 五态判据纯函数受控执行（node） |
| 默认根 | `46 failed, 298 passed, 3 skipped, 1 warning in 11.89s` | 46 项同因（`ENV_ROOT` 只读） |
| 软件层 | `3 failed, 341 passed, 3 skipped, 1 warning in 73.83s` | 3 项环境层（archive×2 + 冻结见证） |
| 复核后整改定向 | `12 passed, 3 skipped, 1 warning in 1.61s` | 含 idle 断言与面板 8/8 断言说明 |
| 整改后默认根 | `46 failed, 299 passed, 3 skipped, 1 warning in 12.08s` | 失败集不变 |
| 整改后软件层 | `3 failed, 342 passed, 3 skipped, 1 warning in 73.89s` | 3 项环境层 |
| 建议项实现后定向 | `63 passed, 3 skipped, 1 warning in 1.64s` | run-view-state + web_smoke + browser + doc_links |

实现：唯一判据 `web/run-view-state.js`（loading/idle/first_error/loaded/stale_error）；`app.js` 记录
当前选择的成功时间与在途标记，代次隔离用 `isCurrent(runId+epoch+request)`；首次失败与陈旧失败都有可达
「重新读取」入口（只发详情 GET）；运行视图 5 个面板与闸门视图 3 处占位统一走 `panelHint()`，闸门头失败
改用 `status-pill fail`。

**独立复核**（[F13-verify-20261021.md](audit/F13-verify-20261021.md)，md5 `667b6d89b770dc808f9c093b365283f9`）：
首轮**不建议合并**（2 项必改：8 处占位仍判「加载中」、闸门头失败画成进行中蓝色）→ 整改 `219fb70` →
回归复核**可合并**（新必改 0；建议 6 条，已在 `d272a80` 实施：idle 同屏、闸门头复用判据、规格 idle 行、
面板断言 8/8、文案中性化、点击防抖）。**未复核**：`d272a80` 本身（登记为残余）。

**未运行**：`tests/browser` 整组（缺 `playwright` Python 包；系统有 `/usr/bin/google-chrome`）——
浏览器 DOM 断言一条未执行，**不声称 UI 已在浏览器验证**。

## 23 F03-b 测试分层与环境层入口（2026-10-22）

计划 [F03-b](plans/2026-10-21-F03b-test-layers.md)，规格 [环境插件规格 §4.1](spec/ENV_PLUGIN_SPEC.md)。
顺序：**计划+规格**（`1b0ed64`）→ **红灯**（`65d5f10`）→ **实现**（`9afc7e5`）→ **复核报告**（`e439eaa`）
→ **复核建议**（`4d1c65b`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯 | `6 failed in 2.42s` | 无 `env_layer` 标记注册/入口过滤/源码原因 |
| 实现后分层断言 | `6 passed in 2.45s` | 精确 3 项、`--strict-markers` 生效、入口收集期排除 |
| 默认根 | `46 failed, 305 passed, 3 skipped, 1 warning in 13.75s` | 3 项环境层仍**如实 FAILED**，不是 skip |
| 软件层 | `348 passed, 3 skipped, 3 deselected, 1 warning in 75.52s` | **0 failed**；3 项环境层被显式排除 |
| 建议项后软件层 | `429 passed, 3 skipped, 3 deselected, 1 warning in 81.82s` | 打印被排除清单（3 项逐条可见） |

实现：`pytest.ini` 注册 `env_layer` + `--strict-markers`；3 项环境层用例加标记并写明原因
（可写 `ENV_ROOT` / 冻结见证 / 布局）；`spikes/run_software_checks.sh` 默认 `-m "not env_layer"`，
`INCLUDE_ENV_LAYER=1` 可包含，并打印被排除用例清单与用户 `-m` 覆盖警告。

**独立复核**（[F03b-verify-20261022.md](audit/F03b-verify-20261022.md)，md5 `904e46d92a099a71a3c7f37dd94ec087`）：
**建议合并**（无阻断）。5 条建议中 3.1/3.2/3.5 已在 `4d1c65b` 实施；3.3（规格/测试两处清单）
判定保持契约编码，3.4（默认根失败数曾一次性漂移）按「串行静默复算」口径记录（见 §35）。
**未复核**：`4d1c65b` 本身（登记为残余）。

## 24 F03-c 文档路径检查根路由（2026-10-22）

计划 [F03-c](plans/2026-10-21-F03c-doc-link-roots.md)，规格 [环境插件规格 §4.2](spec/ENV_PLUGIN_SPEC.md)。
顺序：**计划+规格**（`407cfab`）→ **红灯**（`18d7e00`）→ **实现**（`c8c565b`）→ **复核报告**（`e439eaa`）
→ **整改 M1/M2**（`e392d1b`）→ **复核建议**（`2805c2b`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯 | `38 failed, 13 errors in 0.83s` | `Roots/classify/resolve/scan` 尚不存在 |
| 实现后定向 | `51 passed in 0.62s` | 所有权分类/诱饵根/退出码/历史件 |
| 真实全库扫描（实现后） | 退出码 `0`、`missing=0` | `env_missing`/`known_missing` 可见 |
| 默认根 | `46 failed, 356 passed, 3 skipped, 1 warning in 13.95s` | 失败集不变 |
| 软件层 | `399 passed, 3 skipped, 3 deselected, 1 warning in 75.89s` | 0 failed |
| 整改后定向 | `62 passed in 0.88s` | 目录形态/根解析复用/RootError |
| 整改后真实扫描 | 退出码 `0`、`missing=0` | `env_missing=11`、`known_missing=10`（可见） |

实现：按**路径所有权**路由（TOOL_ROOT / WORKSPACE_ROOT / ENV_ROOT / doc 回落）；`loop/` 不再回落环境根；
环境资产缺失单列 `[ENV-MISSING]`（可见、不计失败）；本仓/数据根断链 ⇒ `missing` + 退出码 1；
`KNOWN_MISSING` 打印原因；`root` 不可确定 ⇒ `[ROOT-ERROR]` + 退出码 2（复用 `kb_lib`，不写冻结目录字节码）。

**独立复核**（[F03c-verify-20261022.md](audit/F03c-verify-20261022.md)，md5 `dd9f06e9651f968702665b1b44deeffe`）：
首轮**不建议合并**（M1 无尾斜杠目录误路由、M2 第二套根解析）→ 整改 `e392d1b` → 回归复核**可合并**
（M1/M2 关闭、无新必改、口径未放宽：旧/新对同一文档的 missing/env_missing/known_missing 集合逐条相同）。
复核建议（死导入、`kb_lib` 归属校验）已在 `2805c2b` 实施，**未复核**（登记为残余）。

## 25 F16-c / F02-c 残余（2026-10-22）

计划 [F16-c/F02-c](plans/2026-10-21-F16c-F02c-residual.md)，规格 [Web UI §4.3](spec/WEB_UI_SPEC.md)、
[Agent 窗口规格](spec/AGENT_WINDOW_SPEC.md)。顺序：**计划+规格**（`c564b96`）→ **红灯**（`a878b2e`）
→ **实现**（`96cf86b`）→ **复核报告**（`0328222` 前）→ **建议项**（`a32b13e`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯（三个文件合并） | `15 failed, 15 passed, 1 warning in 1.46s` | **计数口径见下方勘误** |
| 实现后定向（5 文件） | `101 passed, 1 warning in 2.51s` | capability + n8 + context + control |
| 加 `test_agent_view.py` | `111 passed, 1 warning in 2.54s` | —— |
| 能力/格式化专项 | `15 passed, 1 warning in 1.39s` | 未知维度/standin≠真实/唯一格式化 |
| `api_ui_contract` | `2 failed, 6 passed` | 2 项为 `ENV_ROOT` 只读（环境层），不在本切片 |
| 默认根 | `46 failed, 375 passed, 3 skipped, 1 warning in 14.73s` | 失败集不变 |
| 软件层 | `418 passed, 3 skipped, 3 deselected, 1 warning in 76.74s` | 0 failed |

**勘误（复核者必改 1）**：红灯提交 `a878b2e` 的 `test_node_capabilities_equal_role_card_projection`
失败原因是**测试自身签名写错**（`TypeError: build_agents() takes 1 positional argument`），
不是「缺少 `node_capabilities`」；不能把它计入「能力缺失导致红灯」的证据。其余能力/格式化/N8 消息用例为真红。

实现：`agent_view.node_capabilities()` 复用 `_capabilities/_collect`（Host 节点返回 `None`）；
`GET /api/runs/{id}/agents/{node}` 下发 `capabilities`（未知维度保持 `None`）；
新增 `web/capabilities.js` 唯一格式化，`app.js`/`agent-window.js` 共用；N8 聚合预算不足错误消息补文件名与最小成本。

**独立复核**（[F16c-F02c-verify-20261022.md](audit/F16c-F02c-verify-20261022.md)，md5 `66f1cb98dbb7facf78816b6ac8ce1cab`）：
**建议合并**（代码层无阻断；2 项证据口径必改已在本节按原样记录：红灯归因、定向数字）。
建议项（窗口 API 精确期望、历史 attempt 语义澄清）已在 `a32b13e` 实施；格式化 guard 随 F05 提交。**未复核**该整改提交。

## 26 F15-a 规格与文档对齐（2026-10-22）

计划 [F15-a](plans/2026-10-21-F15a-doc-alignment.md)。顺序：**计划**（`a51193d`）→ **文档**（`86b6216`）
→ **复核报告**（`e439eaa`）→ **整改 M1/M2/M3**（`0328222`）。本切片无业务代码变更，不适用红灯。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 文档门（文档提交后） | 退出码 `0`、`missing=0` | `env_missing`/`known_missing` 可见 |
| 文档门（整改后） | 退出码 `0`、`missing=0` | —— |
| 业务单测/浏览器/kb/端到端 | 未运行 | 纯文档切片；不复用其它章节结果 |

实现：根 README 写权摘要对齐 AGENTS §3；删除现行入口的「单文件前端」「70/94 项」硬编码；数字统一指向
STATUS；`doc/README.md`/`doc/agents/README.md` 索引现状（2 份开工提示词、audit 含验证报告）；历史章节加
「历史采样/适用版本」标注（ENV_PLUGIN_SPEC §5、CHANGE_IMPACT_LOOP_SPEC 完成度行、2026-10-19 UI 计划）。

**独立复核**（[F15a-verify-20261022.md](audit/F15a-verify-20261022.md)，md5 `89adeb379e2bf1736d7e9551f3094e7d`）：
首轮**不建议合并**（3 项文字必改：§6 约束适用范围、UI 计划横幅把未实施的 F05 归为已拆分、agents 索引仍写 1 份）
→ 整改 `0328222`（同时实施 S2/S4）。**未复核**该整改提交（登记为残余）。

## 27 F06 模型请求机制与节点语义分离（2026-10-22）

计划 [F06](plans/2026-10-21-F06-model-request-split.md)，规格 [AGENT_CONTEXT_SPEC 实现结构](spec/AGENT_CONTEXT_SPEC.md)。
**纯重构切片**：先固定特征基线（重构前 `109 passed in 28.79s`），再提取；不适用红灯。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 重构前特征基线 | `109 passed, 1 warning in 28.79s` | test_flow + context + control + n8 + capability |
| 重构后同一命令 | `109 passed, 1 warning in 28.40s` | 行为特征不变 |
| 分层结构断言 | `4 passed in 0.58s` | 机制不含校验实现/单一 `_validate`/兼容导出 |
| 默认根（重构前基线快照） | `46 failed, 386 passed, 3 skipped, 1 warning in 16.39s` | 失败集与基线相同 |
| 默认根（`50383dc` 干净快照，复核者复算） | `46 failed, 390 passed, 3 skipped` | +4 = 新增结构断言；以该行为准 |

实现：新增 `model_common.py`、`model_request.py`（`validate` 注入）、`n6_facts.py`、`n10_semantics.py`、
`n11_guard.py`；`model_steps.py` 1470 行（原 2192）保留节点入口与兼容导出。测试仅迁移内部符号补丁落点
（`_ask`→`model_request.ask`、`_doc_bitdef_for`→`n6_facts`、`run_kb_tool`/`ledger` 注入），**期望值未改**。
`implementation_sha256` 现记录 `model_request.py` 指纹（属预期变化，不用它替代语义对照）。

**独立复核**（[F06-verify-20261022.md](audit/F06-verify-20261022.md)，md5 `67d29e2d29810631ce255d94bf4b2a77`）：
**建议合并**（条件性）；M1（STATUS §27 数字）已按本行/下表更正，M2（回填 md5）已在本节完成。
函数级 AST 对照 49 个旧函数逐字同一；提示词/Schema 零 diff；默认根失败集逐项相同。
**未复核**：`implementation_sha256` 覆盖边界建议（S1）、`_ask` 别名建议（S2）。

## 28 F05 前端按功能拆分（第一步：闸门会话判定，2026-10-22）

计划 [F05](plans/2026-10-21-F05-frontend-split.md)，规格 [Web UI §7.1 实现归属](spec/WEB_UI_SPEC.md)。
顺序：**计划+规格**（`cd47ca2`）→ **红灯**（`4a6bbd9`）→ **实现**（`37e0b26`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯 | `7 failed in 1.01s` | `gate-session.js` 不存在 |
| 实现后定向 | `19 passed, 3 skipped, 1 warning in 2.99s` | 纯函数 7 条 + F13/web smoke；browser skip |
| 默认根 | `46 failed, 397 passed, 3 skipped, 1 warning in 18.40s` | 失败集不变 |
| 软件层 | `440 passed, 3 skipped, 3 deselected, 1 warning in 82.38s` | 0 failed |

实现：`web/gate-session.js` 唯一判定（身份 key/新身份重置/撤回选项只清决策/提交互斥/选择三元组），
`app.js` 仍持状态与渲染、只消费纯函数；DOM id/事件/API 载荷未改。
**未完成（明确登记）**：运行/Agent/计数与配置/目录浏览的渲染提取（F05 后续步骤，需要浏览器特征集，
本机不可运行）。**未运行**：浏览器 P0/P1 交互验收（缺 playwright）。

## 29 F14 样式与断点收敛（静态清单 + 阻塞，2026-10-22）

计划 [F14](plans/2026-10-21-F14-style-convergence.md)，工具 `loop/spikes/css_inventory.py`（只读）。

| 静态事实（`css_inventory.py` 输出） | 值 |
|---|---|
| `web/tokens.css` | 17 行、1 条 `:root` 规则、0 媒体查询、0 `!important` |
| `web/app.css` | 730 行、795 条规则、14 条媒体查询、6 处 `!important`、98 组跨规则重复声明 |
| `web/legacy.css` | 75 行、2 条媒体查询、1 处 `!important` |
| 断点 | 1000/1100/1180/1200/760/850/1550/1600、1101–1390、761–1100、min 1101、prefers-reduced-motion×2 |

**决策：不盲改**。视觉等价需要默认/hover/focus/disabled/告警/模态态与断点交界的截图或计算样式对照；
本机缺 `playwright`（系统有 `/usr/bin/google-chrome`，PyPI 不可达），无法完成验收。
本轮只交付只读清单与验收条件；**未运行**：浏览器特征集、截图对照。**不声称视觉已验证**。

## 30 F07 Agent 历史读取测量（2026-10-22）

计划 [F07](plans/2026-10-21-F07-agent-read-measurement.md)，规格 [AGENT_WINDOW_SPEC](spec/AGENT_WINDOW_SPEC.md)
「测量基线与触发阈值」；脚本 `loop/spikes/measure_agent_read.py`（`--repeat 20`）。

| 样本 | attempts | events | 记录字节 | 响应体字节 | median | p95 | CPU/读 | tracemalloc 峰值 |
|---|---|---|---|---|---|---|---|---|
| small | 1 | 10 | 1485 | 3494 | 4.130 ms | 4.182 ms | 4.162 ms | 33813 B |
| medium | 10 | 100 | 204852 | 59148 | 31.804 ms | 31.888 ms | 31.604 ms | 475887 B |
| large | 50 | 1000 | 10024332 | 583949 | 240.868 ms | 242.764 ms | 240.489 ms | 12379317 B |

> 口径说明：本表是**加入 F10 的 `previous_input` 之后**在当前 HEAD 上的复跑（响应体因此比 F07 提交时点大：
> 提交时点三档为 `3470 / 39116 / 383917`）。CPU/读已按复核必改改为**测量循环内的 `process_time` 增量/repeat**
> （不含样本构造）；修复前三档列值（7.867/36.875/228.291）是进程累计口径，作废。

**决策**：三档均未达规格触发阈值（p95 > 500 ms 或响应体 > 1 MB）⇒ **不引入**缓存/分页/摘要列表。
**未测量**：控制回执延迟（需活跃 model 会话与真实 provider，本机不可运行）；真实 token 上限。

## 31 F08 封存发布与崩溃边界（2026-10-22）

计划 [F08](plans/2026-10-21-F08-sealed-recovery.md)，规格 [AGENT_CONTEXT_SPEC](spec/AGENT_CONTEXT_SPEC.md)
「封存与恢复」。顺序：**计划+规格**（`91c4c8e`）→ **红灯**（`aaf8974`）→ **实现**（`792bb48`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯 | `5 failed in 1.18s` | `record_state`/`seal_record` 不存在；半写记录整体抛错 |
| 实现后定向 | `76 passed, 1 warning in 2.50s` | f08_sealed + agent_control + context_memory |
| 默认根 | `46 failed, 402 passed, 3 skipped, 1 warning in 18.41s` | 失败集不变 |
| 软件层 | `445 passed, 3 skipped, 3 deselected, 1 warning in 81.01s` | 0 failed |

实现：`AM.record_state(path)` 只读四态（absent/incomplete/corrupt/committed）；`read_view` 对 incomplete
尝试标状态且不消费、其它尝试可读；corrupt 仍显式失败（保持既有安全契约）；`AM.seal_record` 公开，
`agent_control` 不再引用私有 `_sealed`；默认选中只从可消费记录取。故障注入用真实子进程
（数据/校验之间 `os._exit(9)`、写入循环 `SIGKILL`）与篡改校验，不是内存模拟。

**独立复核**（[F08-verify-20261022.md](audit/F08-verify-20261022.md)，md5 `974ec8bbf192b9acbad1c435f8b8dbe6`）：
**首轮不建议合并**（M1：`record_state` 绕过符号链接检查，安全契约回归）→ 整改 `500622a`（`record_state`/
`verify_attempt` 拒绝符号链接，`read_view` 读状态前补 `_safe`）→ 定向 `77 passed`。
**未复核**：整改 `500622a` 本身（登记为残余）。

## 32 F10 / F11（前半）只读可解释性（2026-10-22）

计划 [F10/F11](plans/2026-10-21-F10-F11-explainability.md)，规格 [AGENT_WINDOW_SPEC](spec/AGENT_WINDOW_SPEC.md)
「可解释性」。顺序：**计划+规格**（`954a9dc`）→ **红灯**（`088dfe6`）→ **实现**（`e58478d`）。

| 验证 | 原始输出（逐字复制） | 说明 |
|---|---|---|
| 红灯 | `9 failed in 1.18s` | 提交信息写「8 failed」为笔误，以此为准（模块不存在 9 条断言） |
| 实现后定向 | `41 passed, 3 skipped, 1 warning in 2.19s` | context_explain + capability + control + web_smoke；browser skip |
| 默认根 | `46 failed, 411 passed, 3 skipped, 1 warning in 18.97s` | 失败集不变 |
| 软件层 | `454 passed, 3 skipped, 3 deselected, 1 warning in 83.10s` | 0 failed |

实现：`web/context-explain.js` 纯函数（UTF-8 字节/预算占比、经验原因、尝试摘要、输入差异；token 估算恒为
`unknown`）；窗口新增两个只读区块；`read_view` 增加 `previous_input`（只读）；API 下发
`context_budget.limit_bytes`（Host 常量，前端不硬编码）；不新增请求、不改记录/筛选。
**未完成**：F11 分页/完整历史导航（F07 未达阈值）；F10 token 预检（需真实 provider）。
**独立复核**（[F10F11-verify-20261022.md](audit/F10F11-verify-20261022.md)，md5 `03a788dfc8a646e20da73e5f4bd1a07b`）：
**首轮不建议合并**（A1：窗口把嵌套 `request.input` 传给按顶层字段统计的 `budget()`，真实记录下预算恒 0 B）
→ 整改 `59f57e7`（传整条 `request`；`explain` 包 try/catch；补记录形状与接线断言）→ 定向 `14 passed, 3 skipped`。
**未复核**：整改 `59f57e7` 本身（登记为残余）。其余判定（只读、token 未知、previous_input、textContent-only）通过。
**未运行**：浏览器渲染（缺 playwright）。

## 33 阻塞与未完成清单（本轮结束状态）

| 项 | 状态 | 原因 / 已做部分 |
|---|---|---|
| F01-d 内网真实非默认基线整链 | **阻塞** | 缺内网环境与非默认有效基线；只完成软件层准入/身份切片（§14） |
| F04 S0-b 驱动/三库/准出闭环 | **阻塞** | 缺内网驱动与授权；S0-a 软件协议已交付，`ready_for_execution` 保持 false |
| F09 持久暂停 | **未开始（依赖 F08/F10 结论与 TriggerFlow durable 契约）** | F08 已做封存边界诊断，但续跑握手/显式恢复未实现 |
| F12 只读并行委派 | **暂缓** | 缺具体用例与测量；不引入第二个调度框架 |
| F15-b/CI | **部分** | 软件层入口已固化；本仓无 `.github`，**未部署 CI**，不声称 |
| F14 视觉验收 | **阻塞** | 缺浏览器/截图对照；只交付静态清单，未改样式 |
| F05 余下步骤 | **未完成** | 运行/Agent/计数、配置/目录浏览提取需要浏览器特征集 |
| F11 分页 / F10 token 预检 | **未完成** | F07 未达分页阈值；token 预检需真实 provider 能力 |
| 浏览器断言（全部切片） | **未运行** | 缺 `playwright` Python 包（系统有 google-chrome，PyPI 不可达） |
| kb 自测 / 端到端 | **未运行** | `ENV_ROOT` 只读、内网夹具缺失；不得用软件层结果替代 |
| F08 之后的 F09 恢复矩阵 | **未做** | 只登记观察矩阵，未实现新进程恢复握手 |

**口径纠正**：`TB/top.sv` 属「资产名不存在」（`ENV_ROOT/TB/` 下无 `top.sv`），不是「ENV_ROOT 未挂载」；
文档门把它单列为 `[ENV-MISSING]` 可见项，不计失败。

## 34 本批独立验证汇总与诚实边界（2026-10-22）

| 切片 | 复核报告 | md5 | 复核结论 | 整改 | 整改后是否再复核 |
|---|---|---|---|---|---|
| F13 | [F13-verify-20261021.md](audit/F13-verify-20261021.md) | `667b6d89b770dc808f9c093b365283f9` | 首轮不建议合并 → 回归可合并 | `219fb70`、`d272a80` | 回归复核覆盖 `219fb70`；`d272a80` **未复核** |
| F03-b | [F03b-verify-20261022.md](audit/F03b-verify-20261022.md) | `904e46d92a099a71a3c7f37dd94ec087` | 建议合并（无阻断） | `4d1c65b` | **未复核** |
| F03-c | [F03c-verify-20261022.md](audit/F03c-verify-20261022.md) | `dd9f06e9651f968702665b1b44deeffe` | 首轮不建议合并 → 回归可合并 | `e392d1b`、`2805c2b` | 回归复核覆盖 `e392d1b`；`2805c2b` **未复核** |
| F16-c/F02-c | [F16c-F02c-verify-20261022.md](audit/F16c-F02c-verify-20261022.md) | `66f1cb98dbb7facf78816b6ac8ce1cab` | 建议合并（2 项证据口径必改） | `a32b13e` | **未复核** |
| F15-a | [F15a-verify-20261022.md](audit/F15a-verify-20261022.md) | `89adeb379e2bf1736d7e9551f3094e7d` | 不建议合并（3 项文字必改） | `0328222` | **未复核** |
| F06 | [F06-verify-20261022.md](audit/F06-verify-20261022.md) | `67d29e2d29810631ce255d94bf4b2a77` | 建议合并（条件：STATUS 数字/回填） | 本节 + §27 | 条件已在 §27 关闭 |
| F07 | [F07-verify-20261022.md](audit/F07-verify-20261022.md) | `5df68f0ee6ee32e0418ae18d4d4ce320` | 建议合并（CPU 口径必改） | `9ebee73` | 是（复核者只读复跑整改后通过） |
| F08 | [F08-verify-20261022.md](audit/F08-verify-20261022.md) | `99c54df6ba8d74333f63b9ef2df22215` | 建议合并（符号链接回归 M1） | `500622a`、空目录 M2 修正 | 是（M1 复验通过；M2 已按观测矩阵修正） |
| F10/F11 | [F10F11-verify-20261022.md](audit/F10F11-verify-20261022.md) | `03a788dfc8a646e20da73e5f4bd1a07b` | 首轮不建议合并（预算传参错） | `59f57e7` | **未复核** |

> md5 为**最终全文 md5**（报告自引用限制说明见各报告末节）。本批所有复核者都是只读子代理：
> 只写各自报告、未改被测文件、未做 git 写命令（各报告已登记）。

### 34.1 最终门禁数字（从命令输出复制；串行执行）

| 门 | 命令 | 结果 | 判读 |
|---|---|---|---|
| 默认根单测 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q --tb=no` | `46 failed, 414 passed, 3 skipped, 1 warning in 18.87s` | 46 项为环境层（`ENV_ROOT` 只读 44 项 `Errno 30` + 2 项 archive），失败集与 §14–§32 基线相同；**不是全绿** |
| 软件层单测 | `cd loop && bash spikes/run_software_checks.sh --tb=no` | `457 passed, 3 skipped, 3 deselected, 1 warning in 80.73s` | 软件层 **0 failed**；3 项环境层被显式排除（非 skip） |
| 文档门 | `python3 doc/audit/check_doc_links.py` | 退出码 `0`；`missing=0`；`env_missing`/`known_missing` 可见 | 本仓断链为零；环境缺件单列不隐藏 |
| 端到端 | `cd loop && bash spikes/accept_v1_run.sh` | **未运行** | 缺可写 `ENV_ROOT`/UVS/内网夹具；不得用软件层结果替代 |
| kb 自测 | `kb/tools/_selftest_*.py` | **未运行** | 同上；不能声称通过 |
| 浏览器 | `tests/browser` | `3 skipped`（模块级） | 缺 `playwright` Python 包（系统有 `/usr/bin/google-chrome`）；UI 交互/视觉**未验证** |

**结论口径**：本批完成了 11 个软件可验证切片的计划、红灯/特征基线、实现与独立复核；
**kb 自测、端到端、浏览器验收与真实 provider 链路均未运行**，因此**不声称四道门全绿、也不声称合规**。
§33 的阻塞项保持可见；F14 的视觉验收与 F05 的余下渲染提取需要具备浏览器依赖的执行端。

### 34.2 本批流程偏差与纠正（不补造证据）

| 偏差 | 事实 | 处理 |
|---|---|---|
| 计划与实测顺序 | F07 的测量脚本先实跑、后提交计划；计划正文不含实测数字，但严格顺序应为计划先行 | 登记为偏差；数字仍只从命令输出进入 STATUS |
| 红灯数字笔误 | F10/F11 红灯提交信息写「8 failed」，实际 `9 failed` | §32 按实跑更正；复核报告亦记录 |
| 红灯归因错误 | F16-c 红灯中一条能力投影用例失败原因是**测试签名写错**（TypeError），不是能力缺失 | §25 勘误；不计入「能力缺失」证据 |
| 执行日志时间 | 初版执行日志的时间列曾按会话顺序估算 | 已用 `git log --format=%ad` 的实际提交时间替换 |
| 临时文档门变红 | 验证者在途写报告时，示例路径曾使文档门短暂 `missing>0` | 各 owner 改写模板写法后恢复 `missing=0`；不记为切片缺陷 |
| 整改后未再复核 | 9 份报告中有 4 份的整改提交未再次独立复核（F13 `d272a80`、F03-b `4d1c65b`、F03-c `2805c2b`、F16-c `a32b13e`、F15-a `0328222`、F10/F11 `59f57e7`；见 §34 表） | 逐条登记；不声称「复核通过」 |
| 红灯用例在实现提交中改写 | F08 红灯 `aaf8974` 对「篡改校验」的期望是「视图标 corrupt」，实现中改为「读取显式失败」并同步改了测试（`792bb48`）——属安全契约取舍，但违反「红灯提交后不再改测试期望」 | §31/§34 记录；后续切片若改期望须单独提交并说明 |
| 观测矩阵与实现口径 | F08 复核 M2：空 attempt 目录摘要曾标 `absent`（矩阵要求 `incomplete`） | 已在 `read_view` 映射为 `incomplete` 并补用例；`record_state` API 语义仍是 `absent`（诊断 API 与摘要状态分开） |

## 35 内网批次拉取后复核（2026-10-22）

用户要求拉取内网修订并审查。main 从 `fb83ed0` 快进至 `a19107c`。本轮不改业务代码，仅源码复核、受控测试和文档留证；同一执行者复核，不冒充独立终验。

[完整复核](audit/AUDIT-20261022-intranet-batch-review.md)、[原始命令与证据](evidence/INTRANET_REVIEW_20261022.md)（MD5 `976c315044d5c65ff4e8b3279c3c5bb9`）、[可复现探针](audit/parts/intranet-batch-probe.py)。注册表中的内网环境根/数据根在本机不存在，使用专属临时数据根及现有 conftest 的临时 state；测试不连接真实 provider/仿真器。

| 本轮检查 | 实际输出 / 状态 | 范围与判读 |
|---|---|---|
| 受影响集合及完整现有浏览器集 | `1 failed, 283 passed, 1 warning in 71.78s (0:01:11)` | 精确命令与失败栈见证据；唯一失败为 `test_sigkill_during_publish_loop_never_yields_consumable_partial` 的 checksum mismatch；不是全套软件层 |
| 浏览器收集 | `41 tests collected in 0.06s` | 均在上述集合内执行通过，无 browser skip；是受控网页/API，不是内网/真实模型验收 |
| F08 失败用例单独复跑 | `1 passed in 1.05s` | 随机终止落点相关，单次转绿不抹掉首次失败 |
| 确定性校验发布中断 | `child_exit=9, prior_state=committed, checksum_bytes=0, partial_state=corrupt, read_error=ValueError: agent record checksum mismatch: request.json` | R1：校验文件创建后退出使整个节点视图读取失败，旧完整尝试也不可读 |
| artifact 路径 | `kind=relative, valid=true, outside_all_allowed_roots=true`；`kind=absolute, valid=false, outside_all_allowed_roots=true` | R2：同一外部文件用相对路径绕过允许根，绝对路径被拒 |
| manifest 坏编码 | `http_status=500` | R3：临时非 UTF-8 manifest 使基线列表整体失败 |
| N8 默认预算 | `full_bytes=59341, budget=60000, actual=N8 上下文预算不足：分片后 61835 > 60000 bytes` | R4：全文有可行解，片段更大却被当作最小成本 |
| 窗口预算口径 | `host_bytes=72, displayed_bytes=1055` | R5：前端计入 offered/scope，并漏外层字段名/标点，与 Host 计费不同 |
| 文档门 | 退出码 `1`；`known_missing=10 env_missing=304 missing=116` | 报告/探针落盘后、证据与本节写入前；缺内网根与既有路径问题保持可见，不把它们全部当作代码回归，也不声称零断链 |
| 来源边界 | `PASS: existing evidence, history and audit content is unchanged.`；`PASS: reviewed loop/kb implementation is unchanged.`；`PASS: review probe Python syntax is valid.` | 旧件内容按 MD5 对照被测 HEAD，未修被测实现 |
| 新文档 / 补丁 | 新增 Markdown 链接、锚点、来源行号检查通过；`git diff --check` 退出成功 | 仅本轮新增文档及状态入口，不代表全库文档门通过 |
| 全套软件层 / kb / 完整端到端 / 真实 provider | 未运行 | 缺内网根/夹具；受影响集合不替代完整四道门 |

当前结论：F01/F02/F03/F05/F06/F13 等有实质修订，本轮受控网页路径通过；F08 发布空窗仍应优先修正，R2–R5 分别补边界用例后收口。R1–R5 均为未修复，不改写 §34 原采样；§33 的 S0-b、真实非默认基线整链、持久暂停等前置仍有效。完整四道门未通过。

## 36 Rocky 浏览器验证离线交付（2026-10-22）

用户要求将浏览器相关依赖放入 Git，内网拉取后安装；用户确认目标 Rocky Linux 8.10 / x86_64 / glibc 2.28，仓库记录 CPython 3.11。本轮新增离线增量包与校验/安装/运行工具，未修 §35 的业务缺陷。版本与全部 SHA-256 在 [资源清单](../loop/offline/browser-linux-x86_64/manifest.json)；[内网使用说明](../loop/offline/README.md)、[计划](plans/2026-10-22-browser-offline.md)、[原始证据](evidence/BROWSER_OFFLINE_20261022.md)（MD5 `51baa569374e8a15963af5991899451d`）。同一执行者分阶段实施与验证，没有独立终验。

| 检查 | 实际输出 / 状态 | 范围 |
|---|---|---|
| 资源大小与完整性 | `bundle_bytes=194484143`；`PASS: all vendor resources are listed; every Git object is below 50 MiB.`；`PASS: offline bundle platform and SHA-256 verification` | 固定 wheels/locks 与 Chrome 分片，普通 Git 交付，不依赖 LFS；每片与整体 SHA-256 |
| 新工具实现前 | `7 errors in 0.57s` | 新工具尚不存在，FileNotFoundError；不是既有产品缺陷红灯 |
| 工具边界 CPython 3.12 | `7 passed in 0.53s` | 完整性、平台、归档边界、路径选择 |
| 工具边界 CPython 3.11 | `7 passed in 0.59s` | 干净 venv 中相同断言 |
| 干净 CPython 3.11 / 3.12 离线安装 | `Successfully installed greenlet-3.2.5 playwright-1.64.0 pyee-13.0.1 typing_extensions-4.16.0` | pip 强制本地索引关闭与哈希，完整原始输出见证据；3.11.17 / 3.12.14 |
| 随包浏览器冒烟 | `PASS: local browser smoke; version=156.0.8078.47` | 解开原始发行包运行时至独立缓存，不安装系统包 |
| 已有系统浏览器冒烟 | `PASS: local browser smoke; version=154.0.8037.57; executable=/usr/bin/chromium` | 复用已安装可执行文件 |
| 随包 Chrome + CPython 3.11 浏览器集 | `41 passed in 55.22s` | 使用新 CLI `run --bundled`；受控网页/API，无 skip，非真实内网或模型链路 |
| 项目基础依赖一致性 | `No broken requirements found.` | 临时 CPython 3.11 venv 中 pip check；基础 requirements 在联网构建阶段安装，不属于 UI 离线增量包 |
| Rocky 8.10 容器断网安装 | wheel 安装成功；最终退出码 `1`，显式报告缺少 `libnspr4.so`、`libnss3.so`、X11/GBM 等系统库 | 真正 Docker `--network none`；最小镜像中 Chrome 启动**未通过**，不能写成 Rocky 浏览器验收通过 |
| Rocky/glibc 核心驱动检查 | `ldd (GNU libc) 2.28`；`PASS: CPython 3.11 / greenlet / Playwright imports on Rocky 8.10`；`v24.21.0` | 同一容器无网络，Python imports 与 driver/node 正常，未证明主机字体/所有共享库 |
| 链接/语法/补丁 | 本轮 Markdown 链接、锚点及资源路径有效；脚本 AST 解析、`git diff --check` 通过 | 变更范围检查；不覆盖 §35 全库文档门缺件 |
| 完整业务 / kb / 完整端到端 / 内网主机 Chrome | 未运行 | 本轮是验证依赖交付；原有外部资产和业务缺口不由浏览器包解决 |

**交付边界**：增量包依赖项目原有 `.venv`；Python 依赖和备用浏览器随 Git 提供，主机共享库/字体由 Rocky 提供。优先复用内网已有 `/usr/bin/google-chrome`；没有 Chrome 时可解包备用版本，但系统库缺件必须从匹配的内网 Rocky 8 RPM 源补齐后再运行。安装不自动联网下载、不执行 rpm/dpkg、不要求 root、不复制 Debian 系统库、不替换 glibc。浏览器测试缺包/缺库/跳过不冒充通过。

## 37 下一轮 SpecDD 规划与内网验证手册（2026-10-22）

用户要求规划后续优化/重构、补充内网可照做的验证步骤并推送。已核对远端 main，与编制基线 `343584c` 一致。本轮只交付文档：先 R1–R5 正确性收口，再 F14/F05 网页重构，F01-d/F04、F09、性能与 CI 按依赖启动；保留现有浏览器网页范围。

- [下一轮 SpecDD 计划](plans/2026-10-22-next-iteration-specdd.md)：任务 owner/写权、规格入口、未决决策、红灯/特征用例、切片顺序、退出门与回退。
- [内网验证手册](plans/2026-10-22-intranet-validation.md)：V0–V9 的版本/三根确认、离线浏览器、软件层、缺陷回归、网页人工矩阵、专用副本四道门、真实链路条件与证据冻结。
- [本轮交付检查证据](evidence/NEXT_ITERATION_PLAN_20261022.md)，MD5 `02e33f39c0c11c5b87a2eae0ecdaa5e0`；同一执行者编制与校核，无独立终验。

| 检查 | 原始输出 / 状态 | 判读 |
|---|---|---|
| 新计划/手册链接与命令 | `PASS: new plan/runbook Markdown targets, Bash syntax, embedded Python syntax and existing test paths.` | 目标存在、bash -n、嵌入 Python AST、现有测试文件路径；语法/入口检查不等于内网执行通过 |
| 离线资源完整性 | `PASS: offline bundle platform and SHA-256 verification` | verify 动作，本轮未重新安装或启动浏览器 |
| 全库文档门 | `known_missing=10 env_missing=304 missing=116`；`doc_links_exit=1` | 既有缺内网根/数据及路径问题保持可见，门未通过 |
| 与编制 HEAD 文档对照 | `PASS: whole-repository missing/env_missing finding sets match HEAD; new plan and runbook add no findings.` | 同根解析的缺失集合一致；临时对照脚本中文文件名转义问题已纠正，详见证据 |
| 旧件保护 | `PASS: existing evidence/history/audit, frozen kb and application files match HEAD byte-for-byte.` | 没有业务实现变更、旧证据回填或冻结目录修改 |
| 补丁格式 | git diff --check 退出成功 | 本轮文档改动 |
| 业务全套 / 浏览器回归 / kb / 完整端到端 / 真实 provider | 未运行 | 本次是规划交付；内网按验证手册执行后另增结果，不抄历史数字 |

**仍未关闭**：§35 的 R1–R5；§33 的真实链路、S0-b、持久暂停等依赖仍适用。§36 解决了离线依赖交付，未替内网主机完成浏览器或业务验收。本轮不声称四道门全绿或功能已完成。

## 38 内网修订经 bundle 合入与本地复核（2026-10-22）

本轮为**网络不可达条件下的手动同步**，不是常规 fetch：`git fetch/pull` 对 `https://github.com/rj-chenjunming/fpga_sim_workflow.git` 持续返回 `Received HTTP code 503 from proxy after CONNECT`（代理 `192.168.1.27:3128` 的 CONNECT 隧道对该目标失败；同期代理对普通 HTTP 与其它 HTTPS 目标正常，本机 `/etc/resolv.conf` 无 nameserver、无 VPN 路由，直连亦不通）。故改由外网执行端拉取后交付 `git bundle`，本机完成校验与合入。本轮不改业务代码，只合入、复核与留证；**同一执行者实施并验证，不冒充独立终验**。

### 38.1 同步事实

| 项 | 实际输出 / 状态 |
|---|---|
| 交付件摘要 | `cic-inc.bundle` md5 `45ceee9bb11624c5a0a6a6716a203e7d`；`cic-full.bundle` md5 `6433cf1e24d2c7cd310a2534944dd387`；与随附 `MD5SUMS.txt` 逐位一致 |
| `git bundle verify` | `is okay`；含 `8816dbce58cef1f46437f7a51bf423e4469ebedd refs/remotes/origin/main`；requires `a19107ce87065040fc79b8d2233477c87a2ace00`；`sha1` |
| `git fetch <bundle>` | `a19107c..8816dbc  origin/main -> origin/main` |
| SHA 对照 | 本机 `origin/main` == 外网镜像 HEAD == `8816dbce58cef1f46437f7a51bf423e4469ebedd`（未失真） |
| 合入方式 | `git merge --ff-only`；合入前 `git rev-list --count origin/main..HEAD` = 0、工作树干净 |
| 变更规模 | `3` 提交 / `32` 文件 / `+1493 -5`，另含离线资产约 `186 MiB`（工作树 `loop/offline`） |
| 合入的提交 | `d861ca3`（内网批次复核 R1–R5 登记）、`343584c`（Rocky 离线浏览器包）、`8816dbc`（下一轮 SpecDD 计划与内网验证手册） |
| 回滚锚点 | tag `pre-sync-20261022` = `a19107c`；回滚命令 `git reset --hard pre-sync-20261022` |
| 传输件清理 | `/home/work/chenjunming/fpga_sim/`（758M：两个 bundle + 镜像）已删除；大写 `FPGA_SIM` 环境仓未触碰 |
| 仓库体积 | `.git` `238M`（合入前 `52M`） |

### 38.2 本轮实测（数字从命令输出复制）

| 检查 | 命令 | 结果 |
|---|---|---|
| 软件层单测 | `cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh --tb=no` | `464 passed, 3 skipped, 3 deselected, 1 warning in 85.98s`（同一命令合入前为 `457 passed`，增量 7 项即新增离线工具用例；**0 failed**） |
| 离线包完整性 | `loop/.venv/bin/python loop/spikes/browser_offline.py verify` | `PASS: offline bundle platform and SHA-256 verification`，rc=0 |
| 文档门 | `python3 doc/audit/check_doc_links.py` | rc=0；`checked=1418 skipped=14250 historical=857 known_missing=10 env_missing=12 missing=0` |
| 对象体积声明 | 最大 blob | `46.0 MiB`（playwright wheel）；Chrome 分片 `40.0/40.0/40.0/18.1 MiB`；均 < 50 MiB，未用 LFS |
| 证据只增不改 | `git diff --name-status a19107c..HEAD -- doc/evidence doc/audit doc/history` | 5 项全为 `A`，无 `M`/`D` |
| §35 缺陷复现 | `loop/.venv/bin/python doc/audit/parts/intranet-batch-probe.py` | 与 §35 登记一致：`artifact relative valid=true outside=true` / `absolute valid=false`；`manifest http500`；`child_exit=9 prior_state=committed checksum_bytes=0 partial=corrupt`；`full_bytes=59341 budget=60000` 仍报 `61835 > 60000`；`host_bytes=72 displayed_bytes=1055` |

### 38.3 未运行与诚实边界

1. **端到端 `accept_v1_run.sh`、kb 自测、真实 provider、内网主机浏览器**：本轮**未运行**（缺可写 `ENV_ROOT` 与内网夹具）；软件层通过**不能**替代四道门。
2. **真远端未再核对**：代理仍不可达，`origin/main` 现由 bundle 手动维护；出网恢复后必须跑一次真实 `git fetch` 复核 sha，未复核前不得声称与远端一致。
3. 合入与验证为同一执行者，**无独立终验**。
4. §35 的 R1–R5 **全部未修复**；§33 的 F01-d、F04 S0-b、F09 等前置与阻塞不变。
5. 本机文档门 `missing=0` 与 §35 记录的 `missing=116` 口径不同：后者执行端缺注册内网根与历史夹具，属环境缺件，不是本仓断链。

### 38.4 本轮附带观察（未修复、未独立复核、待登记）

在合入前的源码复核中另发现一处**未收录于 R1–R5** 的风险：`n6_apply` 建沙箱目录时不清理残留（[host_steps.py:597](../loop/workflows/chunks/host_steps.py#L597)），N8 用 `glob("*.sv")` 收全部沙箱文件（[model_steps.py:660](../loop/workflows/chunks/model_steps.py#L660)），闭锁只校验「缺件」不校验「多余件」（[model_steps.py:673](../loop/workflows/chunks/model_steps.py#L673)），而三条返工回边复用同一 `run_dir`（[main_flow.py:90](../loop/workflows/main_flow.py#L90)）⇒ 返工轮目标缩水时，上一轮遗留的 `.sv` 可能被当作本轮已复核对象，短文件还会标 `coverage.complete=true`。**该项既未修复也未经独立复核**，建议在下一轮按 §37 顺序与 R4 同区间立项，先补红灯再改实现。

## 39 R 门缺陷收口：阶段 A 验证基线（2026-10-22）

按 [开工提示词](agents/开工提示词_R门缺陷与网页重构.md) 执行本轮。采样 `HEAD=5e2f8cb`，契约先行提交 `8669cd7`
（R1 原子发布 / R2–R3 基线边界 / R4 真实成本 / R5 预算计量写入 `doc/spec/*`）。执行计划见
[R 门执行计划](plans/2026-10-22-R-block-execution.md)，原始命令与输出见
[阶段 A 证据](evidence/R_BLOCK_A_20261022.md)（MD5 `47de12cab6bd9625a5378d3c5ab1ee1e`）。

| 步骤 | 命令 | 实际输出 | 判读 |
|---|---|---|---|
| V0 三根/版本 | `git rev-parse HEAD`；`git status -sb` | `5e2f8cb0149a95823d3f8ebd4cd0c729398fccf6`；`main...origin/main [ahead 2]`；CPython `3.11.7` | 采样可追踪；`/home` 为 `ro` 挂载，`ENV_ROOT` 只读 |
| V1 离线浏览器 verify | `loop/.venv/bin/python spikes/browser_offline.py verify` | `PASS: offline bundle platform and SHA-256 verification`（rc=0） | 包完整 |
| V1 安装 | `... browser_offline.py install` | `Successfully installed greenlet-3.2.5 playwright-1.64.0 pyee-13.0.1`；随后启动冒烟 `FAIL: TargetClosedError`（rc=1） | wheels 安装成功；失败因 **`$HOME` 只读**（Chrome 写 `~/.local/share` 被 EROFS 拒） |
| V1 真实启动 | `HOME=/tmp/h XDG_*=. .venv/bin/python spikes/browser_offline.py check` | `PASS: local browser smoke; version=152.0.7977.75; executable=/usr/bin/google-chrome`（rc=0） | 浏览器真实启动通过（前提：HOME 可写）；**未出现** `libnspr4/libnss3` 等缺件 |
| V2 软件层 | `HOME=… LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome bash spikes/run_software_checks.sh --tb=no` | `505 passed, 3 deselected, 1 warning in 142.96s`（rc=0） | 0 failed；`+41` 为 `tests/browser`（装包后不再 skip），`skipped` 3→0；非回归 |
| V3 浏览器回归 | `... spikes/browser_offline.py run` | `41 passed in 54.45s`（rc=0） | 0 skip；改前视觉基线在阶段 C 采集 |

**环境事实（本轮新增，命令必须带）**：浏览器用例需要
（a）`LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome`（或随包 Chrome）与（b）**可写 `HOME`/`XDG_CONFIG_HOME`/`XDG_CACHE_HOME`**。
缺任一条件时是 `error` 而不是 skip，不得当通过。默认根全量仍有 46 项已知环境层失败（`ENV_ROOT` 只读），不修、不 skip。

**未运行**：端到端 `accept_v1_run.sh`、kb 自测、真实 provider、内网主机浏览器（缺可写 `ENV_ROOT` 与内网夹具）。
§33 的 F01-d / F04 S0-b / F09 阻塞不变。阶段 B（R1–R6）与阶段 C（F14/F05）结果见后续 §40–§41。

## 40 R 门阶段 B 缺陷收口（R1–R6，2026-10-22）

契约先行 `8669cd7`（R1/R2/R3/R4/R5 条款）；R6 未决条款随本节追加。原始命令、红灯/绿灯与跨切片探针见
[阶段 B 证据](evidence/R_BLOCK_B_20261022.md)（MD5 `bc8c964c48313ffac9232cc803bce00e`）、
[收口探针](evidence/R_BLOCK_B_20261022_after_probe.py)（MD5 `30e15e4902da96fec2ad8a7d1ab6cbb8`）。

| 切片 | 红灯提交 | 实现提交 | 定向绿灯 | 独立复核（只读子代理） | 结论 |
|---|---|---|---|---|---|
| R1 原子发布 | `bfaaf9e`（`3 failed, 8 passed`） | `907697e` | `82 passed` | [R1-verify](audit/R1-verify-20261022.md) `b453265f4b268535461a482f4a67a272` | 建议合并，阻断 0 |
| R2 路径边界 | `039fc8f`（`2 failed, 3 passed` 定向；复核者整文件 `3 failed, 19 passed`） | `e279eac` | `31 passed`（复核者 `35 passed`） | [R2-verify](audit/R2-verify-20261022.md) `e0f13e9513a0c74206b49e9b2224d338` | 建议合并，阻断 0 |
| R3 坏编码隔离 | `74fb06d`（`4 failed`，真实 HTTP 500） | `96e9705` | `29 passed`（复核者 `42 passed`） | [R3-verify](audit/R3-verify-20261022.md) `3b09e50e2d7f60896b4b4d26fd85faff` | 建议合并，阻断 0 |
| R4 N8 真实成本 | `5199dd3`（`5 failed, 18 passed`） | `1a5f619` | `23 passed`（复核者 `75 passed`） | [R4-verify](audit/R4-verify-20261022.md) `e6882e79f6ddafcfb04d2aec06d96921` | 建议合并，阻断 0 |
| R5 预算口径 | `0ec6684`＋`34f62cc`（`10 failed, 9 passed`） | `746ec8d` | `67 passed` | [R5-verify](audit/R5-verify-20261022.md) `6fe36b627f8617f55be8818e91b541e8` | 建议合并，阻断 0 |
| R6 沙箱残留 | 未实现（确认探针 RED） | —— | —— | 无（未改行为） | **当前缺陷不成立**；防御性登记 |

**收口复验（Lead 串行）**：

| 检查 | 命令 | 实际输出 | 判读 |
|---|---|---|---|
| 受影响集合（8 文件） | `pytest -q --tb=no` 8 个切片测试文件 | `153 passed, 1 warning in 6.11s` | 0 failed / 0 skip |
| 跨切片收口探针 | `loop/.venv/bin/python doc/evidence/R_BLOCK_B_20261022_after_probe.py` | `R1_kill_before_checksum_publish ok`（`child_exit=9, checksum_published=false, state=incomplete, attempts={1:validated,2:incomplete}`）、`R2…ok`（相对/绝对均 `valid=false`）、`R3…ok`（`http_status=200, v1_valid=true, v2_valid=false`）、`R4…ok`（`used=59341, budget=60000, full_files=86, region_files=0`）、`R5…ok`（`host=api=window=86 B`，分项 46 + 开销 40 = 86，token `unknown`）、`fails=[]` | 五项均按现行契约独立复验通过（新协议，不依赖旧探针注入） |
| 软件层 | `HOME=… LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome bash spikes/run_software_checks.sh --tb=no` | `530 passed, 3 deselected, 1 warning in 141.94s`（rc=0） | 0 failed / 0 skip；较阶段 A `+25` 即本轮新增切片用例 |
| 文档门 | `python3 doc/audit/check_doc_links.py` | `checked=1507 skipped=17990 historical=857 known_missing=10 env_missing=12 missing=0`；rc=0 | 本仓断链 0；环境缺件保持可见 |

**R6 否决依据（不立项）**：纯函数探针可稳定复现「残留 `.sv` 被计入且 `coverage.complete=true`」，
但该输入状态在当前拓扑**不可由正常执行产生**（N5 只一次、返工回边只到 `n6_author`、每轮目标集强制全覆盖并重写、
跨 run 新目录）。按交付标准记录否决依据，防御性修法（清理沙箱 / `applied_cases` 白名单 / 多余件显式失败）
与触发条件写入 [AGENT_CONTEXT_SPEC](spec/AGENT_CONTEXT_SPEC.md)「未决（R6）」；未来出现第二个沙箱写入者、
可缩水目标集或同 `run_id` 复用目录时立项。

**未运行/边界**：端到端 `accept_v1_run.sh`、kb 自测、真实 provider、内网主机浏览器未运行（缺可写 `ENV_ROOT`/内网夹具）；
默认根全量仍有 46 项已知环境层失败。五份复核报告均由只读子代理撰写（只写报告、不改被测文件、不做 git 写命令）。
R6 未实现修法 ⇒ **不声称已关闭**。

## 41 阶段 C 网页样式收敛与最终门禁（F14-a / F14-b A–E，2026-10-22）

阶段 C 在 B 稳定后启动，实现 owner `web-refactor`，Lead 负责门禁/证据/整合。**F05-b/c 本轮未开始**（登记见 §41.5）。
证据（新增）：[F14-a 基线](evidence/R_BLOCK_C_20261022/style-inventory.md)、
[C/D/E 与终态](evidence/R_BLOCK_C_20261022/AFTER-VERIFY-CDE.md)、
[更正与冻结声明](evidence/R_BLOCK_C_20261022/CORRECTIONS-F14.md)、
[F14-b 独立复核](audit/F14b-verify-20261022.md)（只读子代理，建议合并、代码阻断 0、P2×2/P3×6/O1）。
冻结件：`AFTER-VERIFY.md` MD5 `9a388b5cb5038d4510f1da7021513171`；`MD5SUMS-F14B.txt` MD5 `48cd4a92694f4f2a5280d2bd0cc31e3e`。

### 41.1 切片、提交与验证

| 切片 | commit | 内容 | 计算样式 139 组合（v1 工具） | tests/browser | 冻结截图 42 对 |
|---|---|---|---|---|---|
| F14-a 基线 | `9ebb986` | 45 张改前截图 + 计算样式/焦点/断点矩阵 + 命令 | — | `41 passed` | — |
| A 布局/框架 | `837d2aa` | 删 51 条被完全覆盖声明 + 11 条整规则 | 113 组合 **0 差异** | `41 passed in 57.34s` | 42/42 相同 |
| A2 断点/reduce | `25714b3` | 删重复 `prefers-reduced-motion` 块（`!important` 声明 −2）；合并两份 760 **否决**（9 组合出现差异） | 139 **0** | `41 passed in 55.21s` | 42/42 相同 |
| B 通用控件 | `c06ca97` | 删 54 条声明 + 2 处令牌替换（后回退）+ 8 条整规则 | 139 **0** | `41 passed in 55.02s` | 42/42 相同 |
| B2 回退 | `1edd451` | 回退 3 条 `#fff→var(--panel)`（理由已更正，见 §41.3） | — | — | 回退后 42/42 相同 |
| C S0 | `f2d39fe` | 删 88 条声明 + 12 条整规则 | 139 **0** | `41 passed in 54.07s` | 42/42 相同 |
| D 运行/闸门 | `b4df6e6` | 删 81 条声明 + 8 条整规则 | 139 **0** | `41 passed in 62.71s` | 42/42 相同 |
| E Agent+旧页 | `7ecbb9c` | 删 60 条声明 + 4 条整规则；`legacy.css` 无可证冗余未改 | 139 **0** | `41 passed in 56.32s` | 42/42 相同 |

**终态静态事实（Lead 实测）**：`app.css` `57834 → 50069` 字节；规则 `795 → 751`；媒体块 `14 → 13`；
`!important` 声明 `app 6 → 4`（行 3 → 2）、`legacy 2`（行 1）、`tokens 0`；**新增 `!important` = 0**；
`legacy.css`/`tokens.css`/JS/HTML/`tests/**` 未改。命令：`loop/spikes/css_inventory.py`、
`grep -o "!important" loop/web/*.css | wc -l`、`git show 9ebb986:loop/web/app.css | wc -c`。

### 41.2 最终门禁（数字从命令输出复制）

| 门 | 命令 | 实际输出 | 判读 |
|---|---|---|---|
| 软件层 | `HOME=… LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome bash spikes/run_software_checks.sh --tb=no` | `530 passed, 3 deselected, 1 warning in 139.39s` | 0 failed / 0 skip |
| 默认根 | 同环境 `.venv/bin/python -m pytest -q --tb=no` | `46 failed, 487 passed, 1 warning in 74.98s` | 失败集与 §34.1 同集：44 × `Errno 30`（`ENV_ROOT` 只读）+ 2 × `test_archive_e2`（环境层）；非回归 |
| 浏览器 | `.venv/bin/python -m pytest -q tests/browser` | `41 passed in 55.92s` | 0 skip / 0 error |
| 文档门 | `python3 doc/audit/check_doc_links.py` | 见 §41.6 最终运行 | 目标 `missing=0` |

### 41.3 更正与流程偏差（不补造证据）

1. **撤回 B2 的「非等价」结论**：原称令牌化造成 `1920-gate-rejected` 14 像素 RGB ±1 差异，但引用的
   `raw/f14b-tokenization-diff.txt` 未入库，复核者重放得到 42/42 与终态相同。B2 回退**保留**，理由改为
   「缺少可复现证据证明逐像素等价，故不采用」。见 [CORRECTIONS-F14](evidence/R_BLOCK_C_20261022/CORRECTIONS-F14.md) §1。
2. **v2 全属性指纹工具未采用**：P2-2 指出的 docstring/实现不一致成立；按此改为真正遍历全部 longhand 后，
   对照实验（**同一份** CSS 放两个目录）仍报逐元素差异（`1280/run` 1056/1056、`1280/s0` 665/665）⇒ 系统性误报，
   已恢复提交版 v1（md5 `346d81bb7614c64817fa9fc9d14b018a`）。因此 **C/D/E 的「零差异」仍只有 v1 工具证据**，
   其静态支配性证明登记为未完成（§41.5）。
3. **数字更正**：`app.css` 改前字节 `57526 → 57834`；B 的「56」= 54 删除 + 2 令牌替换；760 合并否决实为
   **9 个（宽度,状态）组合**（390/759/760 × agent/run/s0，元素 52/52/111）；`sliceA` selfrepeat 对照日志产出于
   冻结时钟修复前，不作确定性证据；`commands.md` 未记 F14-b 命令（以 raw 日志与提交信息为准）。
4. **证据就地改写（O1，流程偏差）**：`b832525`/`5b85667` 把 C/D 结果就地追加进已提交的 `AFTER-VERIFY.md`
   与 `MD5SUMS-F14B.txt`（复核时两文件 md5 漂移）。已把两文件**恢复为 `70c4cfb` 冻结内容**（逐字节一致），
   C/D/E 结果改记入新增 `AFTER-VERIFY-CDE.md`；历史提交中的改写不抹除，按实登记。
5. **执行中断**：`web-refactor` 在纠正阶段被 Lead 中断（会话时长控制），其未提交的纠正由 Lead 按同一口径完成并复核；
   该阶段不再有新的实现改动。
6. **§29 计数口径更正**：`legacy.css` 的 `!important` 为 **1 行 / 2 处声明**（`animation`+`transition`），
   §29 的「1 处」是按行口径；`app.css` 为 3 行 / 6 处声明（终态 2 行 / 4 处）。另 §29 所述
   「本机缺 playwright」已由 §39 的离线包安装解决，本轮浏览器用例真实执行。

### 41.4 回退方式（每切片一行）

| 切片 | 回退 |
|---|---|
| R1 | `git revert 907697e bfaaf9e`（旧格式记录保持可读） |
| R2 | `git revert e279eac 039fc8f` |
| R3 | `git revert 96e9705 74fb06d` |
| R4 | `git revert 1a5f619 5199dd3`（不增大默认预算） |
| R5 | `git revert 746ec8d 34f62cc 0ec6684`（先回 UI 消费，再回 API 字段） |
| F14-a | `git revert 9ebb986`（仅证据，无行为） |
| F14-b A/A2/B/B2/C/D/E | 逐片 `git revert 837d2aa` / `25714b3` / `c06ca97` / `1edd451` / `f2d39fe` / `b4df6e6` / `7ecbb9c`；证据提交逐片 revert，冻结件不回填 |
| R6 | 无代码改动，无需回退 |

### 41.5 未关闭项（保持可见）

| 项 | 状态 | 原因 |
|---|---|---|
| F05-b/c 运行/Agent/计数与配置/目录渲染提取 | **未开始** | 本轮时间盒止于 F14-b；前置（R5、`agent-window.js`、浏览器特征集）已具备，下一轮按 [C/D/E 登记](evidence/R_BLOCK_C_20261022/AFTER-VERIFY-CDE.md) §5 接续 |
| C/D/E 删除声明的静态支配性证明 | **未完成** | 复核者已对 A/A2/B 做 140/140 证明；C/D/E 仅有 v1 浏览器指纹与截图证据，独立静态证明待补 |
| F14 人工视觉评审 / 真实 125%/150% 缩放 / `:hover`/`:focus` 动态态 | **未验证** | 无人工评审与真实缩放；不得声称视觉验收通过 |
| R6 沙箱多余件 | **防御性登记** | 当前拓扑不可达，未改行为（§40 否决依据） |
| F01-d / F04 S0-b / F09 | **阻塞** | 缺内网环境、驱动授权与恢复契约评审 |
| kb 自测 / 端到端 / 真实 provider / 内网主机浏览器 | **未运行** | 缺可写 `ENV_ROOT` 与内网夹具 |
| 四道门全绿 | **不声称** | 端到端与 kb 自测未运行；软件层 0 failed 不等于四道门通过 |

### 41.6 文档门

最终运行见本轮提交后的命令输出：`python3 doc/audit/check_doc_links.py` ⇒
`checked=… missing=0`（退出码 0；`known_missing=10`/`env_missing=12` 为已知环境缺件，不回填）。

### 41.7 复核补充：C/D/E 静态支配性证明与文档门最终数字（2026-10-22）

补齐 §41.5 登记的未关闭项「C/D/E 删除声明的静态支配性证明」：独立只读子代理用自写解析器
（不复用实现方删除工具）把 CSS 摊平为有序声明 token，按「后置 / 同一单选择器 / 同一属性 / 同重要性 /
上下文相同或更宽」证明支配。报告：[F14cde-verify](audit/F14cde-verify-20261022.md)（归档 `d019b78` 版 MD5
`e73e1e4dec8822ff29802f22e411643b`；复核者随后做**一次纯文字更正**（结论与数字不变），
当前版 MD5 `363c164503012c74ffb0b55a9b11a345`）。此前本节误记为 `771fc180…`（中间态），
已按 `md5sum` 实测更正（2026-10-22）。

| 结论 | 数字（命令输出复制） |
|---|---|
| 代码阻断项 | **0 个**（建议合并） |
| C/D/E 被删展开声明 | **274 条 = 112 + 92 + 70**，全部被存活声明支配，未匹配 **0** |
| 层叠语义独立校验 | 三个切片各 **28215** 组（单选择器, 属性, 重要性, 上下文）父/子「最后适用声明」比对，**0** 组不一致 |
| 改动面 | 三个提交只改 `app.css` + 3 份 raw；`legacy.css`/`tokens.css`/JS/HTML/`tests/**` 逐字节未变 |
| `!important` | C/D/E 前后均 **4 条 / 2 行**（累计 6→4 的变化全部在 A2） |
| 插入/值替换 | `inserted = 0`，子文件是父文件声明序列的严格子序列 |

**证据更正（复核后，已在新增/更正文件中落笔）**：v1 工具属性清单实测 **125** 项（非文档原称 149）；
v2 全属性工具尝试被对照实验否决，**不作为判据**；`7ecbb9c` 提交信息引用的
`raw/f14b-final2-verify.log` 由被否决的 v2 工具产出且未入库（Lead 删除以免误用）；
`f2d39fe` 提交信息写 `52605` 字节、复核实测 `52913`。提交信息不可改，按实登记。
更正后文件：`AFTER-VERIFY-CDE.md` MD5 `9c9d20d825f1dc4de2fe6169d5fdfb13`、
`CORRECTIONS-F14.md` MD5 `46fa428b0ac749a806a39b7160c88eb7`；
`F14b-verify-20261022.md` MD5 `ef5f73b8e77c5d9fd225ccac1e71e407`。

**文档门最终运行**：`python3 doc/audit/check_doc_links.py` ⇒
`checked=1548 skipped=19062 historical=857 known_missing=10 env_missing=12 missing=0`，退出码 `0`。
（`known_missing`/`env_missing` 为已知环境缺件诊断值，不回填；本仓断链 0。）

**仍未关闭**（保持可见）：F05-b/c 未开始；人工视觉评审 / 真实 125%/150% 缩放 / `:hover`/`:focus` 动态态未验证；
R6 防御性登记未立项；F01-d / F04 S0-b / F09 阻塞；kb 自测、端到端、真实 provider、内网主机浏览器未运行。
**不声称四道门全绿或合规。**
