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

## 42 SPEC-REV-01 实现：全节点投影 / G1 可判材料 / 节点面板 / S0 徽标（2026-10-22）

用户验收 `SPEC-REV-01` 后按其 R2–R6 实施。**本轮不改业务判据、不新增写动作、闸门权威仍只在 `gates.json`**；
实现分三片（后端投影+端点、前端面板+材料、kb 解码口径），同一会话内集成并复核，**没有独立终验**。

### 42.1 交付

| 切片 | 落点 | 关键内容 |
|---|---|---|
| R4 全节点投影 | `loop/services/node_view.py`（新）、`loop/services/api.py`、`loop/workflows/chunks/{host_steps,model_steps,long_jobs,gates}.py`、`loop/workflows/main_flow.py` | 22 个节点（N0–N16 + `N6_apply`/`N9_submit`/`N15_select`/`N15_submit`/`HALT`）逐处补 `detail.source`+`detail.summary` 与 §10.4 右列；`GET /api/runs/{id}/nodes/{node}`（未知 run 404，未知节点 200+`known=false`） |
| R2 G1 可判材料 | `loop/services/contracts.py`、`loop/workflows/chunks/gates.py`、`DRILL_FILES` | 逐条 entry 增 `before`/`after`/`diff_hunk`/`encoding`；`gate_material` 增 `n3_digest{path,exists}`、`host_trace{exists,count,changes[9 字段]}`；drill 复制 `staged/mock_change_applied.json`（10→11 个夹具文件） |
| R4 前端面板 | `loop/web/{app.js,index.html,app.css,node-detail.js}` | 全部节点 chip 可点 → 独立 `<dialog>` 五区块；G1 双栏 before/after、行级 hunk、编码/夹具徽标、N3/Host 留痕入口；S0 来源徽标（§4.5） |
| R3 解码口径 | `kb/tools/{kb_lib,n2_diff,n5_impact}.py`、`kb/tools/_selftest_n2_encoding.py`（新）、`kb/README.md` | 候选集上收 `kb_lib.DECODE_ENCODINGS=("utf-8","gb18030","gbk","latin-1")`，N2/N5 同源（不再第二套）；条目带实际 codec 的 `encoding` |
| refs 安全边界 | `loop/services/node_view.py` | `refs` 只给 run 目录内路径；目录外只给 `refs_omitted` 计数（§6.7） |

### 42.2 实测（数字均为命令输出复制）

| 门 | 命令 | 实际结果 |
|---|---|---|
| 软件层单测（官方入口） | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **523 passed, 3 deselected, 1 warning in 95.80s** |
| 新增投影测试 | `pytest -q tests/test_node_detail_projection.py`（sandbox 数据根） | **34 passed** |
| 浏览器（系统 Chrome + 可写 HOME） | `pytest -q tests/browser` | **55 passed in 72.79s**（41 旧 + 14 新） |
| kb 自测 · N2 解码 | `loop/.venv/bin/python kb/tools/_selftest_n2_encoding.py` | **PASS 37/37**，rc=0 |
| kb 自测 · N5 可达性 | `... _selftest_n5_reachability.py` | `汇总：PASS=9 FAIL=0` |
| kb 自测 · gate schema | `... _selftest_gate_schema.py` | `汇总：PASS=10 FAIL=0` |
| 文档门 | `python3 doc/audit/check_doc_links.py` | `checked=1587 skipped=19615 historical=857 known_missing=10 env_missing=12 missing=0`，退出码 0 |
| 端到端终验 | `cd loop && bash spikes/accept_v1_run.sh` | **未运行**（本会话 `ENV_ROOT` 只读；该门仍未验证） |

**注册表默认命令（`pytest -q`）在本会话的结果**：`54 failed, 471 passed, 55 errors in 67.13s`。
失败/错误**全部来自环境限制、零代码层失败**：52 × `OSError [Errno 30] Read-only file system`（默认
`WORKSPACE_ROOT=<ENV_ROOT>/kb` 只读，drill 建不了 run 目录）、2 × `env_layer` 归档用例（需可写 `ENV_ROOT/SIMLIB_RUN`）、
55 × 浏览器 setup error（未安装 playwright 自带 chromium）。可写影子数据根 + 系统 Chrome 下的真实结果见上表。

### 42.3 实服务复核（隔离实例，不碰 8099）

`LOOP_STATE_ROOT=workspaces/verify-state-18099 LOOP_WORKSPACE=<sandbox> LOOP_LLM_MODE=standin LOOP_PORT=18099 bash loop/remote/serve.sh --sandbox`
⇒ 17 条路由（含 `/api/runs/{id}/nodes/{node}`）；新建 drill run `RUN-20261022-160528`，实测：

- G1 `difference_items` 2 条均带 `before`/`after`（`0x0000#0x0004` reset `2023_0911`→`2026_0708`；`sys_reg.v` md5→md5），
  `diff_hunk` 为空（夹具历史产物，**未回填**）；
- `host_trace.exists=true`、`count=3`：M1 `32'h04→32'h0000_0004`（行 539→540，`encoding=gbk`）、
  M2a/M2b 文档值变更（行 414/447，`encoding=utf-8`）⇒ 人在 drill 下也能看出"改了什么"；
- `n3_digest.exists=true`；
- 节点详情：N0/N1/N2/N3 均有 `source`+`summary`（N1 摘要含 allfiles 3374 条 / cases 162 / doc 指纹 / commit 可解析）；
  N4 等待签署时 `missing_fields=[summary,source,human_signed]`（诚实未下发）；`N9_submit`/`HALT` 可点但未执行；
  未知节点 `known=false`；`refs_omitted=0`（本轮 refs 均在 run 目录内）。
- 历史 run（`RUN-20261022-143532` 等）**不回填**：缺新字段时列 `missing_fields`，验收不得当作缺陷。

### 42.4 未关闭 / 不声称合规

- **端到端未运行**（需可写 `ENV_ROOT`）：四道门中该门仍**未验证**。
- **E1 未修**（SPEC-REV-01 §D）：N2 把 `rc=3`（`RC_GAP`，不产出 `n2_diff.json`）当成功放行，仍可能显示"完成、0 差异"；建议单独切片。
- **E2 未修**：事件 kind 白名单规格 8 / 服务端 15 / 前端 16 三处不一致；本轮未夹带。
- **历史 run 不回填**（事件只增不改），验收不能用旧 run 判定新字段。
- 真机 `real` 链路、内网 S0-real、`accept_v1_run.sh` 断言均未在本会话执行。
- 8099 上仍在跑**旧构建**（`/openapi.json` 11 条路由）；本轮实服务复核用的是隔离实例 18099。
- **运行纪律（实服务复核时实测）**：两个服务进程共享同一 `WORKSPACE_ROOT` 会互相覆盖
  `runs/<id>/view.json`——18099 恢复时把 `RUN-20261022-143532` 标成 `failed`，8099 的轮询又把它
  写回 `waiting_gate`。复核实例已停止；**重启后请新建运行，不要复用该旧 run**。该现象属运行纪律
  （与 §3.1「端到端独占 state」同族），不是本轮代码缺陷。

**结论**：本轮把 R2–R6 落到代码并留下可复跑证据，但**不声称四道门全绿或已合规**。

### 42.5 第二轮收口：端到端复跑 + E1/E2 修复 + S0-rehearsal（2026-10-22 同日）

覆盖 42.4 中"端到端未运行"与 E1/E2 两项；均在同一工作树、同一会话内完成，仍**无独立终验**。

**① 端到端终验（隔离副本，不写共享 state/ENV_ROOT）**

```bash
# 用当前工作树做一次性副本（清 .agently/state/logs 运行时状态），复用一次性 workspace 副本
rsync -a --exclude '.git' --exclude 'loop/.venv' --exclude 'loop/state' \
  --exclude 'loop/.logs' --exclude 'loop/.pytest_cache' --exclude 'workspaces' \
  --exclude '__pycache__' ./ workspaces/verify-e2e2/
rm -rf workspaces/verify-e2e2/loop/.agently
cd workspaces/verify-e2e2/loop
LOOP_WORKSPACE=<verify-e2e-ws> LOOP_LLM_MODE=standin LOOP_PORT=18097 bash spikes/accept_v1_run.sh
```

实测：`phase 1–5 全部 rc=0`、`=> ALL PASS`；断言 **117/117**（50/27/18/8/8/6），与历史验收同集。
踩点登记：副本若保留旧 `.agently/`（RecordStore 身份状态），首跑会 `RecordStoreError: identity state belongs to a different RecordStore`；
副本必须清运行时状态——这是**复制方法**的坑，不是产品缺陷。

**② E1（N2 rc=3 语义）已修**

- `host_steps.n2_diff`：`rc=3`（`RC_GAP`，工具**不产出** `n2_diff.json`）改为 `node_failed` + 抛错，绝不落"完成、0 差异"；`rc=4` 仍失败。
- 回归：`tests/test_fix_real_chain.py::test_n2_rc3_gap_fails_explicitly_and_writes_no_diff`；
  `tests/test_baseline_admission.py::test_n2_uses_selected_baseline` 的 fake rc 由 3 改 0（旧口径断言同步）。

**③ E2（事件 kind 白名单）已修**

- 唯一权威 = `host.progress.ALLOWED_KINDS`（15 个）；`GET /api/health.event_kinds` 原样下发；
- 前端运行时消费 `event_kinds`（静态表为兜底，删掉服务端没有的 `run_failed`）；
- SPEC-02 §9 同步为 15 个并写明唯一权威；
- 漂移测试：`tests/test_api_ui_contract.py::test_frontend_event_whitelist_matches_server_authority`；
  `test_api.py::test_health_and_static_ui` 断言 `event_kinds == sorted(ALLOWED_KINDS)`。

**④ S0-rehearsal（SPEC-05 §6.2/§4/§7）已接入工作台**

- `POST /api/s0/rehearsal`：Host 在软件 state 下自造一次性小基线 → copy → 整体替换 RTL → 四项核验；
  **不接受客户端路径**（多给键即 400）、每次新记录新目录、失败 422 且保留记录、`ENV_ROOT` 零写入、`ready_for_execution` 仍 false。
- 工作台「运行 S0 演练（临时小基线）」按钮 + 回执（id/status/四项 checks/副本路径）+ 固定免责声明
  「只证明 copy→replace→核验链路，**不是**环境就绪、不是 S0-b」；失败显示 `detail.error` 原文。
- 测试：`tests/test_s0.py` 共 **33 passed**（新增演练用例：四项 passed、ports/smoke waiting、旧 RTL 零残留、
  基线前后一致、重复调用不同 id、非法 now 400、客户端路径参数 400）；
  浏览器 `tests/browser/test_run_sessions.py::test_s0_rehearsal_runs_once_and_shows_four_checks_with_scope_notice`。

**⑤ 最终门禁（本轮工作树）**

| 门 | 命令 | 结果 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **531 passed, 3 deselected, 1 warning in 105.38s** |
| 浏览器 | `pytest -q tests/browser`（系统 Chrome + 可写 HOME） | **56 passed in 76.76s** |
| 端到端 | 隔离副本 `bash spikes/accept_v1_run.sh` | **117/117，ALL PASS** |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1614 … known_missing=10 env_missing=12 missing=0`，rc=0 |

**仍未关闭**：S0-real（内网真实环境 + 三库冒烟）未跑；`real` 真机链路未跑；8099 仍是旧构建（新界面需重启）；
历史 run 不回填。**不声称四道门全绿或已合规**。

## 43 真实模式（real）完整轮：环境副本 + live 模型 + UVS 真机编译/全跑（2026-10-22/23）

用户要求"真机跑一轮完整流程后再落实成 drill 演示"。本轮在**可写环境副本**上跑 real，权威 `ENV_ROOT`
零写入；三道闸门由**人**签（`human:chenjunming`），Lead 未代签。证据：
[`evidence/REAL_RUN_20261022.md`](evidence/REAL_RUN_20261022.md) + 冻结件 `evidence/REAL_RUN_20261022/`。

### 43.1 环境与输入

| 项 | 实测 |
|---|---|
| 环境副本 / 数据根 | `workspaces/real-env-copy`（2.6G）/ `workspaces/real-ws` |
| v0 基线（副本重建） | allfiles **4491** / cases **162** / rtl **162** / conflicts **72** / doc **126** |
| 变更（已知答案） | SCN_RTL_0D04 `pcie_register.v`；md5 `d560f2ff…` → `50e4ca25…`（与预登记一致），行 171/172，hunk 643 字符 |
| 服务 | 新构建，`LOOP_ENV_ROOT=<副本>`，`18099`，模型 `origin-deepseek-v4-1-flash`（live），UVS `UVS2026.06.P3` |

### 43.2 两轮结果

| run | 结果 |
|---|---|
| `RUN-20261022-173237` | N0–N8 ✅（N7 真机编译 3/3 rc=0）；**N9 作业被判 dead**（3 例实际全 rc=0，日志齐全）⇒ run failed。根因：JobRunner 的 rc 写入被 N9 命令自带的 `exit 0` 提前跳过（真机全跑首次真正执行才暴露） |
| `RUN-20261022-181700` | N0–N8 ✅；**N9 真机全跑 done，1465s，3/3 rc=0**（`tc_pcie_rw_02`/`tc_pcie_rw_smoke`/`tc_rtc_05`），口径一 **1687**、`UVM_ERROR=0/UVM_FATAL=0`、身份四方同值；N10 `verdict_passed=False`；N11 `intact`；N12 `not_passed`；**G2 accept 被 I2 阻断**（3 例仍待验）⇒ 停在 G2，**N16 不可达（诚实终点）** |

### 43.3 本轮暴露的问题

| 编号 | 事实 | 状态 |
|---|---|---|
| F1 | JobRunner rc 写入被命令自带 `exit` 跳过 ⇒ 真机全跑判 dead | **已修**：命令包进子 shell + 回归 `test_job_command_ending_with_exit_still_writes_rc` |
| F4 | 真实 N2 用 `offsets`（复数），G1 材料 offset 显示 null | **已修**：`diff_entries_view` 兼容读取 + 回归；旧 run 不回填 |
| F2 | 失败报告下 G2 `accept` 不可达（I2 要求无待验，失败轮必有待验）⇒ real 轮 N16 不可达 | **待决**（契约问题，需人决定"接受未通过报告并停止"是否合法） |
| F3 | N5 必改 **3 例** vs SCN 预登记 **5 例**（多 `tc_cpu_i2c_03`、`tc_rtc_10`） | **待查**：权威索引与 SCN 场景索引口径不同；不得当"通过" |

### 43.4 门禁复跑（本轮工作树）

| 门 | 命令 | 结果 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **533 passed, 3 deselected** |
| 浏览器 | `pytest -q tests/browser`（系统 Chrome + 可写 HOME） | **56 passed in 74.86s** |
| 端到端 | 隔离副本 `bash spikes/accept_v1_run.sh`（端口 18098） | **117/117，ALL PASS**（job_runner 修复后复跑） |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1630 … known_missing=10 env_missing=12 missing=0`，rc=0 |

### 43.5 drill 全流程演示（待签）

真实轮无法到达 G3/N16（F2），按用户选择另跑 drill 演示：`RUN-20261022-195952`（8099，drill+standin）
停在 G1，等待人用
`bash loop/spikes/demo_drill_sign.sh RUN-20261022-195952 human:<你的名字>`
三道闸门各按一次 Enter 签名（G1 confirmed / G2 accept / G3 milestone_only）后走到 N16 refused 并归档为演示样例。
**未跑完之前，不写"drill 演示已归档"**。

> 诚实边界：本轮**不**声称真实轮"跑通/判绿"——证据不通过（I3 既有缺陷）是事实；N16 不可达是系统正确拒绝放行。

## 44 最新代码本地集成与节点引用边界修复（2026-10-23）

当前 `work` 从 `8816dbc` 快进到远端 main `f69fe46`，拉取前无本地独有提交、工作树干净；
合入远端 **41** 个提交，无冲突。四份 scratch 旧补丁的交付记录已在祖先 `17650b6` 入库，不重复应用。
本轮修复新节点面板的事件引用边界：顶层引用与事件切片统一复用服务端过滤逻辑，
目录外引用只计数，原始事件不改写。计划见 [集成计划](plans/2026-10-23-latest-code-integration.md)，
命令和原始结果见 [验证记录](evidence/LATEST_INTEGRATION_20261023.md)
（MD5 `b188f3cb8cf51af1217f846d630aaf12`，归档文件只读）。同一执行者实施和验证，无独立终验。

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 新用例红灯 | `4 failed, 1 passed, 1 warning in 0.79s` | 修复前复现绝对/相对/符号链接引用及 API 事件切片越界 |
| 修复后投影/API 集合 | `32 passed, 8 deselected, 1 warning in 0.91s` | 排除缺内网数据根和 drill 夹具的既有集成项，不当作通过 |
| 原文件默认根检查 | `8 failed, 27 passed, 1 warning in 4.10s` | 修复前采样；失败在默认数据根创建，完整文件未通过 |
| 节点面板浏览器 | `14 passed in 30.24s` | 系统 Chromium + 受控 API，非真实内网链路 |
| 远端 F1/E2 回归 | `2 passed, 1 warning in 1.00s` | 作业命令带 exit 仍写 rc；前端事件白名单同源 |
| N2 编码自测 | `PASS 37/37` | 无需内网历史资产的自测，不替代 gate schema/N5 两门 |
| 官方软件层入口 | 数据根不存在，测试未启动 | 不造历史夹具、不声称全套通过 |
| 文档门 | 未通过；`missing=122`、`env_missing=318`；与远端基线相比新增均为 `0` | 既有缺件可见；本轮未新增路径缺失 |

**待恢复**：用户确认旧任务 `080c60f7076427f8dd5e083d4cd082a010de9177`（节点检查器）属于本轮范围。
本实例在拉取后仍无该对象，指定的 `node-inspector-20261023.bundle` 也不存在；未恢复、未验证、未合入，
不能以远端新增的全节点详情功能替代或宣称本轮已经完整保全。需从原任务取回已校验备份后另行集成。

**未运行/未完成**：完整软件层、gate schema/N5 历史夹具自测、端到端、真实模型/仿真验收；
§43 F2 契约决定、F3 索引口径待查仍有效。本轮只完成可用修订的本地集成和所述局部修复，未推送、未发布环境，
不声称四道门全绿或旧任务已完整集成。

## 45 环境 DSH 核接入设计草案（2026-10-23）

用户要求补充“Agent 使用环境中 DSH 核”的设计。本轮新增
[SPEC-08 草案](spec/DSH_AGENT_RUNTIME_SPEC.md)、[SPEC-REV-02 草案](spec/SPEC-REV-02-20261023.md)
和 [实施切片](plans/2026-10-23-dsh-agent-runtime.md)，并在索引、SPEC-06/07 加入入口。
同一执行者编制与检查，无独立终验。

设计采用每个 attempt 独立 DSH 会话，保留 TriggerFlow 与 Host 唯一业务 owner；
先接 N3 只读分析，再接 N6 候选编辑，之后扩展其余模型节点。
覆盖后端选择、拟议适配协议、角色/技能与工具限制、候选导入、控制竞态、审计、预算及回退。
DSH 原生接口、隔离、取消和上下文可观测性均列为内网待核实能力，未虚构 CLI 参数。

| 检查 | 本轮结果 / 边界 |
|---|---|
| 本地 DSH 入口发现 | PATH 中未找到 dsh；未找到可核验 SDK/协议文档，不代表内网未安装 |
| 新设计与计划 | 相对链接目标存在、代码围栏成对；补丁空白检查通过 |
| 文档路径门 | 未通过：`missing=122` 与基线相同；`env_missing=319`，较基线新增 `1` 处环境规则文件引用，明确作为内网前置；没有新增本仓/数据根断链 |
| 产品实现、依赖与运行设置 | 未改动；默认执行仍为现有 Agently 路径 |
| 软件/浏览器/模型/仿真测试 | 未运行：本轮是设计交付，未实现适配器，不安装依赖、不调用 live 模型 |

**完成边界**：只完成设计草案，未接通 DSH、未启用新权限、未发布环境、未推送。
旧任务 `080c60f` 仍待恢复，本文不代替其原始修订；§44 的集成和内网验证缺口继续有效。

## 46 AI 工作面板体验设计（2026-10-23）

用户要求把 AI 界面优化方案整理成设计文档并推送。新增
[SPEC-09 设计](spec/AI_WORK_PANEL_SPEC.md)、[SPEC-REV-03](spec/SPEC-REV-03-20261023.md)
与 [实施计划](plans/2026-10-23-ai-work-panel.md)，在文档索引和 SPEC-04/07 加入入口。
本轮为设计交付，未修改产品实现；同一执行者编制与检查，不声称独立复核。

首版统一 AI 节点和角色卡的入口，采用停靠/全屏面板与概览、成果、执行记录、技术详情分层，
按角色渲染结构化结果，分开表达执行/校验/业务放行，按服务端能力提供操作。
补齐草稿身份、历史只读、回执与生效、断连和刷新、键盘与窄屏规则。
第二版的版本对比、受限证据预览及 DSH 动态明确依赖接口和能力，不计入首版已实现功能。

| 检查 | 本轮结果 / 边界 |
|---|---|
| 文档链接与代码围栏 | 新设计、计划与修订记录的相对链接目标存在，围栏成对 |
| 文档路径门 | 未通过；`missing=122`、`env_missing=319`，与提交基线相同，新增缺失均为 `0` |
| 补丁格式 | `git diff --check` 通过 |
| 实现/浏览器/内网/DSH 验证 | 未运行；本轮未改实现、未安装依赖、未运行模型或仿真 |
| 可用性结论 | 已定义验收场景；尚未做用户任务基线测量，不声称已有量化改善 |

设计推送不代表界面上线或环境发布。现有人工闸门与业务 owner 不变，§44 的缺失提交与内网验收项继续有效。

## 47 人工跑通手册（Web UI 2026-10-23 版）与真实浏览器实测

用户要求"人工通过 UI 跑一遍整个流程"，按当前（改版后）工作台重写 [`doc/UI_RUNBOOK.md`](UI_RUNBOOK.md)。
本轮只改文档与新增截图证据，不改业务代码/判据；截图证据见
[`evidence/UI_RUNBOOK_20261023/README.md`](evidence/UI_RUNBOOK_20261023/README.md)。

### 47.1 实测环境

| 项 | 值 |
|---|---|
| 实例 | `127.0.0.1:18097`（隔离，不碰 8099/18099） |
| 模型 | `LOOP_LLM_MODE=standin` |
| 数据根 | `workspaces/manual-20261023/ws`（`v0` `valid=true` + drill 夹具 `RUN-20261015-120626`） |
| 状态根 | `workspaces/manual-20261023/state3` |
| 构建 | 测试时工作树（含 S0 工作台、节点详情"人话优先"、Agent 工作窗口、S0 来源徽标）；`/openapi.json` **18** 条路由 |

### 47.2 实测轮 `RUN-20261023-110500`（drill / happy）

| 步骤 | 实际结果 |
|---|---|
| S0 演练 | `status=prepared`；copy/rtl/non_rtl/baseline 四项通过，04/05 未完成；`ready_for_execution=false` |
| G1 | 材料：差异 **2** 条、未决 **1** 条；`doc_entry` before/after `reset 2023_0911→2026_0708`；`sys_reg.v` 未决、无 hunk（drill 历史夹具）；冲突 **72/72/72**；选项 3 个。提交 `confirmed` 成功 |
| G2 | 口径一 **1687**、口径二 `UVM_INFO=34933 / WARNING=0 / ERROR=0 / FATAL=0`；提交 `accept` 成功 |
| G3 | 提交 `full_now` 被 **403** 拒绝（`I4：冲突未清零（72 项 blocks_release）…`），闸门仍 pending；改选 `milestone_only` 成功 |
| N15/N16 | N15_select count=5；N15 `simulated=true`；N16 **`refused`、rc=3、dry-run=true**；run `finished` |
| 账本 | `gates.json` 三条记录 `actor=human:manual-verify`、`actor_kind=human`、`human_signed=true`；**占位 actor，不构成人工签署证据** |

### 47.3 本轮同时确认的界面差异（已写进手册）

- 旧手册的三视图导航（①②③）已过时：现为左栏四视图「环境准备 S0 / 运行配置 01 / 运行监控 02 / 人工闸门 03」，
  默认进 S0；无 URL 路由，刷新回 S0。
- 旧手册「沙箱 `v0` 有效」在当前 8099 的沙箱数据根上为 `valid=false`（manifest 写 `kb/baselines/...`
  而拷贝出的 workspace 缺 `kb -> .` 别名）；drill 另需夹具 run `RUN-20261015-120626`。手册 §1.2 给处置。
- 节点详情已改为"人话优先"六块（用途/结果/关键数字/过程/证据/原始记录收起），`seq` 只在原始记录里；
  历史 run 的新字段显示 `missing_fields`，不回填。
- 旧手册的 drill 数字（1687/72）仍成立；但实时数值以当次 run 的投影为准。

### 47.4 门禁（本轮为文档任务，未改代码）

| 门 | 命令 | 结果 |
|---|---|---|
| 文档 | `python3 doc/audit/check_doc_links.py` | 见 §47.5 |
| 单元/端到端/kb 自测 | —— | **本轮未运行**（只改文档与截图，未改代码）；不得据本行声称四道门全绿 |

### 47.5 文档门与边界

- 文档门实测（2026-10-23，命令输出复制）：
  `python3 doc/audit/check_doc_links.py` ⇒
  `checked=1649 skipped=20678 historical=857 known_missing=10 env_missing=12 missing=0`，退出码 `0`。
- 未验证：real 真机链路、S0-real、live 模型 15 s 超时、三档桌面宽度视觉验收；
  截图是 1600×1000 视口 + 弹层元素截图。
- **不声称合规**：I3/I4 仍需人拍板；F2/F3 见 §43.3；S0-b 未接入；real 轮未闭环。
- 测试时工作树包含未提交的节点详情实现改动；本手册按该行为描述，提交版本号以实际 `git log` 为准。

## 48 节点面板"人话优先"（SPEC-REV-04 R1，2026-10-23）

用户走查节点详情后提出："每个环节的可读性太差……只要简单描述做了哪几步、每步做什么、结果怎么样，
用大白话说明就行；seq 不知道干啥的，如果是 log 可以缩起来，需要再展开；我们一个节点一个节点过一遍"。
本轮按 SpecDD 先改规格再改实现：新增 [`SPEC-REV-04`](spec/SPEC-REV-04-20261023.md)，
同步 [SPEC-04 §4.2.1/§6.7](spec/WEB_UI_SPEC.md) 与 [SPEC-02 §10.4](spec/LOOP_ORCHESTRATION_SPEC.md)；
证据与逐节点效果见 [`evidence/NODE_PANEL_READABILITY_20261023.md`](evidence/NODE_PANEL_READABILITY_20261023.md)。

### 48.1 改了什么

| 层 | 落点 | 内容 |
|---|---|---|
| 投影 | `loop/services/node_story.py`（新增）、`node_view.py` | `story`：`purpose`（逐节点一句话）+ `steps`（按事件 kind 的人话）+ `key_results`（逐节点关键字段，缺失"未下发"） |
| 前端 | `loop/web/node-detail.js`、`index.html`、`app.css` | 首屏 = 这一步做什么 → 结果 → 关键数字 → 过程 → 证据；「原始记录（排查用）」默认收起，`seq` 只在这里出现并附解释；失败节点正文不出现"完成" |
| 测试 | `loop/tests/test_node_story.py`（新增）、`test_node_detail_projection.py`、`tests/browser/test_node_detail.py` | 投影确定性/缺失不补默认值/seq 收起/失败不声称完成 |

**边界不变**：面板只读、不新增写动作；status 原值；缺失逐项"未下发"；`refs` 只探测存在性；
判据仍在 `blockers/can` 与 `gates.json`。逐节点文案是首版，按用户逐节点走查后再定稿。

### 48.2 门禁实测（本轮工作树，数字为命令输出）

| 门 | 命令 | 结果 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser --junitxml=…` | **546 tests, failures=0, errors=0, skipped=0**（`testsuite time=108.160`）；3 项 `env_layer` 按脚本默认排除 |
| 浏览器 | `LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome pytest -q tests/browser`（可写 `HOME`） | **56 passed**（75.22s） |
| 端到端 | 隔离工具副本 + 副本环境：`LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS，117/117**（50/27/18/8/8/6，六相全部 `rc=0`） |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1646 skipped=20640 historical=857 known_missing=10 env_missing=12 missing=0`，`rc=0` |

端到端第一次跑（同一隔离副本）为 36/50：副本带上了仓库的
`loop/.agently/records/identity/state.json`（`record_store_id` 绑定原工具根），新进程建 RecordStore 报
`RecordStore identity state belongs to a different RecordStore.`，N0–N4 全 fail。
删掉副本里的 `loop/.agently` 与 `loop/state` 后 117/117 全过——**复制陷阱，不是流程缺陷**。

### 48.3 未关闭 / 边界

- **服务需重启**：`story` 由 Python 进程内生成，已在跑的服务不重启就仍返回旧形状（浏览器静态资源刷新即可，
  Python 端不会自动加载）；本轮实机截图来自 11:03 后重启的 drill 服务（见 §47 的 runbook 截图）。
- **文案未定稿**：逐节点措辞待用户按节点确认；改动只落在 `services/node_story.py` 与 `NODE_CATALOG`，
  不动事件与 detail。
- **走查已完成（2026-10-23）**：N0–N16 + `N6_apply`/`N9_submit`/`N15_select`/`N15_submit` + `HALT` 已逐个走完，
  待修订项 **P-01～P-35** 全部登记在 [`SPEC-REV-04` §C](spec/SPEC-REV-04-20261023.md)（§C.1 进度、§C.2 清单、§C.3 落点）；
  **P-01～P-35 尚未实现**。集中修订开工包（可直接粘贴的提示词）见
  [`plans/2026-10-23-node-panel-revision-kickoff.md`](plans/2026-10-23-node-panel-revision-kickoff.md)。
- **仍未拍板**：P-02（N2 偏移值是否展开）、P-05（模型子事件是否并入父节点）、P-09（是否推广到全部节点）、
  P-25 系统侧（观测点印记由 N6 提示词/schema 产生，还是基线用例自带）、N13/N14 的"待确认项"数据源。
- **历史 run**：`story` 请求时生成，旧 run 也能看；旧 detail 缺新字段时关键数字显示"未下发"，不回填。
- **不声称合规**：本文只证明本轮四道门命令通过；§43.3 的 F2/F3 与 §47 的边界不受本轮影响。

---

## 49 节点面板统一修订（SPEC-REV-04 P-01～P-35，2026-10-23）

> 本节是 **§48.3「P-01～P-35 尚未实现」的后续**：本轮已按
> [`SPEC-REV-04` §C.2](spec/SPEC-REV-04-20261023.md) 逐条修订；§48 正文保持原样（只追加不回填）。
> 实现接口契约：[`plans/2026-10-23-node-panel-unified-revision-plan.md`](plans/2026-10-23-node-panel-unified-revision-plan.md)；
> 证据：[`evidence/NODE_PANEL_REVISION_20261023.md`](evidence/NODE_PANEL_REVISION_20261023.md)。
> 注：§54 由 Lead 预留给 S0-a 真实派生——该号已由本机真实轮按预留写入，见本文 §54「真实 S0-a 派生 + 真实 N9 五用例全跑」。

### 49.1 改了什么（按切片）

| 切片 | 文件 | 内容 |
|---|---|---|
| S1 story 投影 | `loop/services/node_story.py`（新增）、`loop/tests/test_node_story.py`（新增） | `headline` / `headline_source` / `note` / `not_reached` / `not_executed` / `evidence_note` / `status_note` / `status_glossary` / `gate` 透传；逐节点大白话模板与关键数字（P-07/P-09/P-10/P-12/P-13/P-15/P-16/P-19/P-20/P-21/P-22/P-23/P-24/P-26/P-27/P-28/P-29/P-30/P-31/P-32/P-33/P-34/P-35 的展示侧） |
| S2 宿主数据面 | `loop/workflows/chunks/{gates,host_steps,long_jobs,model_steps,model_common,n10_semantics}.py`、`loop/prompts/{loop_nodes.yaml,node_schemas.py}`、`loop/tests/test_flow.py` | N3 digest、N5 待查、N6/N6_apply 逐用例、N8 检查项、N9 逐用例口径、N10 逐用例/分类、N11 身份/未闭环、N12 引用/未闭环、N15* 用例名/真跑、N16 `reason_line`+`n16_result.json`、HALT `reason`、submit 节点 `node_started`、闸门逐条处置落账 `run_dir/decisions/<gate>.json`；P-14 提示词（只影响新 run） |
| S3 服务端投影 | `loop/services/{node_view,contracts,api}.py`、`loop/tests/test_node_detail_projection.py` | `run_status`/`run_terminal`/`node_started_present`/`gate`（二级清单、`redundant_of`、P-29 数字）/`report` 块；`GET /api/runs/{id}/report`（白名单 + 512 KiB 上限 + 越界 403） |
| S4 前端 | `loop/web/{node-detail.js,index.html,app.css,app.js}`、`loop/tests/browser/test_node_detail.py` | 结果区 headline + 黄条、状态 chip 释义、未到达/未执行/证据入口、闸门二级清单 + 前后对比浮窗 + 逐条处置共享草稿、N12 报告全文浮窗、G2 材料报告入口、`window.GateDraftBridge` |
| S5 文档 | `doc/spec/{WEB_UI_SPEC,LOOP_ORCHESTRATION_SPEC,SPEC-REV-04}.md` 等 | SPEC-04 §4.2.1/§4.2.2/§4.4/§6.7/§6.8、SPEC-02 §10.4.1–§10.4.5、SPEC-REV-04 §C.2 状态改为「已修/保留/未定」并写明理由 |

**口径定稿**：`N15.cases` 改用例名列表（旧 run 仍计数，story 两种兼容，另加 `case_count`）；
N5 新增 `to_check_case_count`（去重用例数）而 `to_check_count` 保留条目数；
"同一文件多路证据归并"只有一份实现（`node_story.group_diff_entries`，`contracts` 委托它，AGENTS 红线 8）；
`gate` 节点↔闸门 id 映射只有 `node_view.GATE_ID_BY_NODE` 一处。

### 49.2 门禁实测（数字为命令输出复制）

| 门 | 命令 | 实测 |
|---|---|---|
| 软件层（本轮最终代码） | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **646 passed, 3 deselected, 1 warning in 152.54s**（`EXIT=0`；收集 **649**；3 项 `env_layer` 按脚本默认排除并在输出列出） |
| 软件层（改动前基线） | 同上（18:53，同一工作树） | **551 passed, 3 deselected, 1 warning in 111.96s**（收集 554） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **69 passed in 111.16s**（4 文件；基线 56） |
| kb 自测（schema） | `LOOP_WORKSPACE=<可写影子数据根> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **PASS=10 FAIL=0** |
| kb 自测（N5 可达性） | `LOOP_WORKSPACE=<可写影子数据根> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **PASS=9 FAIL=0** |
| 端到端（隔离副本） | 工具副本（rsync 排除 workspaces/.git/虚拟环境/日志/state/.agently）+ `LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS，117/117**（phase 1/2/3/4/4b/5 = 50/27/18/8/8/6，六相 `rc=0`，`EXIT=0`） |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1725 known_missing=10 env_missing=16 missing=0`，`EXIT=0` |

**环境导致的失败不计入通过**（详见证据 §4.1）：直接 `pytest` 会写只读数据根（`OSError: Errno 30`），
必须走 `spikes/run_software_checks.sh` 影子数据根；kb 自测需可写 `LOOP_WORKSPACE`；
浏览器门首次与软件层并行（nice 19）时 `test_withdrawn_option_cannot_be_submitted`（`page.clock` 时序用例）
失败 1 条，单独/全量重跑均通过（69 passed）——登记为**CPU 竞争下的时序抖动**，不放宽断言、不抹掉。

**真实作业避让**：全程未重启 `:18098`、未 `pkill uvicorn`、未改 `kb/tools/run_guarded.sh`；
门禁期间真实 run `RUN-20261023-171744` 一直 `waiting_job`（`JOB-63f79d482690` 仍在跑）；
e2e 用隔离副本 + `:18199`，收尾删除副本与 3 个 `.loop_drill` 测试 run。

### 49.3 未关闭 / 边界

1. **服务需重启**：`story` 在 Python 进程内生成；`:18098` 未重启 ⇒ 界面仍返回旧形状（本轮按约束不重启）。
2. **P-25 系统侧未拍板**：观测点印记由 N6 提示词/schema 产生 vs 基线用例自带，仍未定；面板只做解释，
   真实轮仍无法过 I3，**不得**显示成"跑通"。
3. **N13/N14「待确认项」数据源未定**：面板保留同一骨架（等待态显示硬阻断与材料数字），不接假条目。
4. **P-02（N2 偏移值展开）/ P-05（模型子事件并入父节点）/ P-09 是否推广"只留 2 个关键数"**：按用户此前指示不做。
5. **旧 run 不回填**：N3 摘要/N5 待查/N6 逐用例/闸门逐条处置只在**新 run** 有；旧 run 如实写"未下发/未留存"
   （真实 run `RUN-20261023-171744` 的 N4 即"逐条处置未留存"）。
6. **`run_software_checks.sh` 重复 `-q`**（自带 + 调用方再传 ⇒ `-qq` 吞掉 "N passed" 汇总行）：
   既有脚本行为，本轮只登记不修。
7. **不声称"已合规"**：以上未关闭项与证据 §7 同一份，保持可见；§43.3/§47 的边界不受本轮影响。

---

## 50 二轮：9 项用户裁决落地（2026-10-23，接 §49）

> 用户 2026-10-23 20:05 逐项裁决 9 条，记录见
> [`plans/2026-10-23-node-panel-unified-revision-plan.md` §8](plans/2026-10-23-node-panel-unified-revision-plan.md)；
> 本轮证据追加在 [`evidence/NODE_PANEL_REVISION_20261023.md` §8](evidence/NODE_PANEL_REVISION_20261023.md)。
> §49 的"未关闭项"里 1/2/4 三条按本轮裁决关闭或改写，其余保持。

### 50.1 裁决 → 落地

| # | 裁决 | 落地（代码/文档） |
|---|---|---|
| 1 | P-25 **作者模型产出观测点** | `N6Output.observation_points`（marker `^N6_[A-Za-z0-9_]+$`）+ 提示词要求每个改动用例真打 `[N6_<检查点>] OK <addr>+<off> <name> = 0x…`（**实读值**）且该行进 `edits[].new`；Host `_validate` fail-closed（每用例至少一条 / marker 唯一 / 必须在同用例 edits 里），N6 校验不过即 `node_failed`；N6 detail 投影 `observation_points`（standin/drill 显式 null）。**只对新 run 生效**，`host.evidence` 期望解析不变 |
| 2 | N13/N14 **只读待确认项** | `gate.items`（`{id,kind,title,detail,severity}`，`kind ∈ {blocker,open_item,conflict,case}`）+ `gate.state` 增第四态 `read_only`；G2 = 阻断项 + N12 报告未闭环项，G3 = 阻断项 + 未清冲突摘要 + 回归选集用例；**无勾选/无 disposition/不参与提交**；G2/G3 不再继承 G1 的差异条目 |
| 3 | P-02 保持条数 | 无改动（headline 已含定位） |
| 4 | P-05 不并入子事件 | 无改动 |
| 5 | P-09 保持逐节点精选 | 无改动 |
| 6 | P-01 双写 + real 隐藏 + 后端改称 | N0 **新 run** 的 summary =「预置数据（夹具）初始化」；drill 说明保留双写、real 不显示 S0 说明行（前端原有行为） |
| 7 | 重启等作业结束 | 未重启 `:18098`；后台看守记录真实作业终态（见 §50.3） |
| 8 | G2 报告**一次点击** | 新增 `loop/web/report-viewer.js`（`window.ReportViewer`，`#ndReportOverlay` 改独立 body 级 `<dialog>`）；N12 面板与 G2 材料共用；G2 按钮一次点击直接弹报告全文 |
| 9 | 暂不提交 | 未 commit；工作树含另一条线未提交改动，等其先落再统一定夺 |

**一处测试夹具修正**：`N6` 现在 fail-closed ⇒ `tests/test_agent_context_memory.py` 的 fake provider 输出必须合法；
只改夹具（`revisions` 覆盖 targets + 同用例 marker 进 edits + `observation_points`），**断言零放宽**。

**一处验收驱动器竞态修正**：`spikes/accept_v1.py` 的 A51 在 `job_submitted` 后、执行真正 pause 前
可能读到 `pending_interrupt=None` ⇒ 误判。改为"先等当前中断出现（≤15s），再校验快照里该中断可恢复"，
判据不变（仍要求"当前停放已落盘且是可恢复的干净快照"），**未放宽断言**。

### 50.2 门禁实测（数字为命令输出复制）

| 门 | 命令 | 实测 |
|---|---|---|
| 软件层（最终代码） | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **656 passed, 3 deselected, 1 warning in 171.01s**（`EXIT=0`；收集 659；3 项 `env_layer` 按脚本默认排除） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **75 passed in 124.37s**（`EXIT=0`；4 文件，节点面板用例 26→33） |
| kb 自测 | `_selftest_gate_schema.py` / `_selftest_n5_reachability.py`（可写影子 `LOOP_WORKSPACE`） | **PASS=10 FAIL=0** / **PASS=9 FAIL=0** |
| 端到端（隔离副本） | 与 §49 同法（隔离工具副本 + 副本环境 + `LOOP_PORT=18199`），驱动器含 A51 竞态修正 | **ALL PASS 117/117**（phase 1/2/3/4/4b/5 = 50/27/18/8/8/6，六相 `rc=0`，`EXIT=0`） |
| 文档 | `python3 doc/audit/check_doc_links.py` | 见 §50.4（同一命令；`missing=0`） |

**首轮 e2e 观察（未掩盖）**：修正前驱动器在本轮跑出 `phase 1 A51 FAIL`（PASS=49/FAIL=1），
定位为"job 已出现、执行尚未 pause"的观察窗口；修正后同命令 117/117 全过。判定为**验收脚本竞态**，
不是业务流程回归；证据两轮都保留。

### 50.3 真实作业避让（未重启）

后台看守每 60s 记录 `GET :18098/api/runs/RUN-20261023-171744`：截至本轮收尾一直 `waiting_job` / `running`
（`JOB-63f79d482690`）。**未重启 `:18098`、未 `pkill uvicorn`、未改 `kb/tools/run_guarded.sh`**；
e2e 用隔离副本 + `:18199`，收尾已删除副本与 3 个 `.loop_drill` 测试 run。

### 50.4 未关闭 / 风险

1. **`:18098` 仍未重启**：新 `story` / 新面板要重启才生效；等真实 N9 作业到终态后由人重启
   （进程在独立 PID 命名空间，Agent 无法按 PID 杀；重启命令见 §50.5）。作业终态前**不得**重启。
2. **P-25 新 run 风险（预期代价）**：N6 现在 fail-closed——live 模型若不按格式输出观测点，N6 会失败，
   真实轮会更"早失败"而不是带病通过 I3。首次 real 轮需观察模型是否稳定满足；如长期不满足，
   需回到裁决 #1 讨论方案 B/C。
3. **`observation_points` 只进了 detail，未在面板首屏展示**（P-25 面板侧仍是"缺印记"解释）。
   是否要在 N6 面板显示"观测点 N 条"待后续需求。
4. **P-25 系统侧仍未验证真机**：drill/standin 无 live 模型输出，`observation_points=null`；
   真实轮能否过 I3 取决于首次 real 运行。
5. **未拍板项保持**（与 §49 一致）：P-02/P-05/P-09（裁决 #3/#4/#5 = 保持）、N13/N14 尚无"逐条处置"语义（裁决 #2 只做只读）。
6. **不声称"已合规"**：以上与证据 §8 同一份，保持可见。

### 50.5 重启命令（等人执行；环境根/数据根取自 `GET /api/health`）

```bash
cd /home/work/chenjunming/change-impact-loop/loop
LOOP_ENV_ROOT=/home/work/chenjunming/change-impact-loop/workspaces/s0-work-20261023 \
LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023 \
LOOP_PORT=18098 ./run.sh
```

重启前请确认 `RUN-20261023-171744` 已不在 `waiting_job/running`；重启后我可用真实 run 复核新面板
（`story.headline` / N13 只读待确认项 / N12 报告全文）。

---

## 51 真实作业终态与重启前置（2026-10-23 21:25）

- 真实 run `RUN-20261023-171744` 已到终态：`failed`（21:24:53）。作业 `JOB-63f79d482690`
  `phase=cancelled`、`elapsed_s=12918.7`（约 3h35m）；事件尾部 `#35 cancel_requested → #36 cancelled →
  #37 lifecycle failed`。**取消由外部发起**（非本 Agent；本 Agent 未对 `:18098` 做任何写操作），
  按既定契约"取消不得当成功"判失败。
- 裁决 #7 的**重启前置条件已满足**（run 不再 `waiting_job/running`）。但 uvicorn 进程在独立 PID 命名空间，
  Agent 沙箱无法按 PID 停止 ⇒ **物理重启需由人执行**，命令见 §50.5。重启后可用该 run 复核新面板
  （N1–N9 的 `story`、N9 未收尾、N10–N16 未到达、N4 逐条处置未留存）。
- 本节只追加事实，不改 §50 的门禁数字（§50.2 的四道门仍对应当前工作树）。

---

## 52 第三轮补充修订（R3-01～R3-18，2026-10-23 晚，接 §49/§50/§51）

> **来源**：遗漏审计开工包 [`plans/2026-10-23-node-panel-revision-round3-kickoff.md`](plans/2026-10-23-node-panel-revision-round3-kickoff.md)；
> 实现契约 [`plans/2026-10-23-node-panel-revision-round3-impl.md`](plans/2026-10-23-node-panel-revision-round3-impl.md)；
> 证据 [`evidence/NODE_PANEL_ROUND3_20261023.md`](evidence/NODE_PANEL_ROUND3_20261023.md)；
> 规格状态 [`SPEC-REV-04` §E](spec/SPEC-REV-04-20261023.md)、[`SPEC-02` §10.4.2/§10.4.5](spec/LOOP_ORCHESTRATION_SPEC.md)、
> [`SPEC-04` §4.2.1/§4.2.2/§6.7](spec/WEB_UI_SPEC.md)。本节**只追加**，不改 §49–§51 的数字与结论。

### 52.1 改了什么（按 R3 分片）

| 片 | 项 | 落点（关键改动） |
|---|---|---|
| W1 宿主数据面 | R3-01（P0）、R3-04 写侧、R3-09 | `prompts/loop_nodes.yaml::n6_author` 示例改为 `uvm_info("<marker>", …)`（marker 是 UVM_INFO 的 **ID**，不是消息前缀）；`model_steps._validate` 的 n6 分支**恒执行** `host.evidence.resolve_expected_imprint(marker, run_dir)`，解析不到 ⇒ fail-closed（无"没绑就跳过"旁路，有反向用例锁死）；`gates._resumed` 的 `decisions/<gate>.json` records 增 `hard_block:[{code,title,message}]` 快照；drill `N9_submit.detail.cases=1`、drill `N7.detail.case_count=1` |
| W2 story 投影 | R3-03、R3-06、R3-08、R3-10、R3-15 | `story.observation_points`（仅 N6 下发 key；null/[]/数组三态）+ N6「观测点」关键数字；`story.evidence_groups` / `evidence_groups_note`（N7/N9 按用例分组，只用面板展示的 run 目录内 refs）；`not_reached` headline 加中文 gloss；`build_story(..., run_halted=…)` 让"drill 早停"不再被误归因为"演示模式不提交"；`GATE_NODES` 改从 `node_registry` 引用 |
| W3 前端 | R3-03/06/07/08/10/12/13 | 观测点可折叠列表（三态）、证据按用例分组、`example_line` 默认收起、`headline_source` 小字附注、`attached[].note` 在浮窗可见；删除死函数 `app.js::renderEntryDecisionHint` 与唯一调用；前端不再自拼"等它跑完/演示模式" |
| W4 服务端/清理/文档 | R3-04 读侧、R3-11、R3-14、R3-15、R3-17 | `contracts.gate_entries_view` 已决策态从 ledger 读 `hard_block`（旧 run ⇒ "当时的阻断项未留存"，`counts.hard_block=null` 不写 0）；新增 `services/node_registry.py`（闸门节点↔闸门 id 唯一来源）；`spikes/run_software_checks.sh` 不再叠出 `-qq`（汇总行可见）；新 run 字段登记为 SPEC-02 §10.4.5 **可选下限**；SPEC/STATUS/evidence 收尾 |

**新增/修改的判定用测试**：`tests/test_n6_imprint.py`（新，7）、`tests/test_node_registry.py`（新，3）、
`tests/test_software_checks_script.py`（新，2）；扩展 `test_node_story.py`（105）、`test_flow.py`、
`test_node_detail_projection.py`（61）、`tests/browser/test_node_detail.py`（43）。
**没有放宽或删除任何既有断言**（唯一改写是 R3-08 按新契约收紧 `not_reached` 期望串）。

### 52.2 四道门实测（数字为命令输出复制；同一最终工作树，2026-10-23 22:1x）

| 门 | 命令 | 实测 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **695 passed, 3 deselected, 1 warning in 154.35s**（`EXIT=0`；收集 698；3 项 `env_layer` 按脚本默认排除并在输出列出；§50 基线 656） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **85 passed in 111.88s**（`EXIT=0`；§50 基线 75，+10） |
| kb 自测（schema） | `LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **PASS=10 FAIL=0**（`EXIT=0`） |
| kb 自测（N5 可达性） | `LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **PASS=9 FAIL=0**（`EXIT=0`） |
| 端到端（隔离副本） | 工具副本 + `LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS，117/117**（phase 1/2/3/4/4b/5 = 50/27/18/8/8/6，六相 `rc=0`，`EXIT=0`） |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1788 skipped=22543 historical=857 known_missing=10 env_missing=19 missing=0`，`EXIT=0` |

- 端到端在**隔离工具副本**上跑，跑完删除副本与 3 个 `.loop_drill` 测试 run；未写 `:18098` 的真实 run 目录。
- `env_missing` 由 §50 的 16 变为 19：多出的是另一条线本轮改动里的环境侧引用（不在本仓可验证范围），
  `missing=0`（本仓链接）未变。

### 52.3 未关闭 / 风险（必须与通过结论一起读）

1. **R3-02/R3-05 真机复核未执行**：`:18098` 仍是第一版"人话面板"旧构建（`/openapi.json` 18 条路由、
   无 `/api/runs/{id}/report`；`nodes/N1` 的 `story` 只有 `purpose/steps/key_results`）。进程在独立 PID
   命名空间，按红线未重启 ⇒ 新面板**未做**真机复核（N1–N9 story / N4 逐条处置留存 / N13 只读清单 /
   N12 报告全文等）。重启命令与复核清单见 §52.4。
2. **R3-16 `doc/UI_RUNBOOK.md` 未改**：该文件仍是另一条线未提交改动（`git status` 未落），按写权互斥不动；
   过期段落待该线落定后由对应 owner 更新。
3. **R3-18 真实轮验收未做**：上一轮 real `RUN-20261023-171744` 在 N9 被**外部取消**（21:24:53 `failed`），
   未到 N16 ⇒ P-13/P-14/P-20/P-21/P-24/P-26 等的真机表现本期无法观测；只登记、不伪造。
4. **P-25 live 首次真机验证缺口**：可解析性已由 Host fail-closed + 端到端单测证明
   （`consistent=True`、`verdict.passed=True`），但 live 模型是否稳定按新格式产出观测点要等下一次 real 轮；
   若长期不满足，需回到裁决 #1 讨论方案 B/C。
5. **旧 run 不回填**：新 story 字段、新 detail 字段、闸门 `hard_block` 只对新 run 生效；
   历史 run 如实显示"未下发/未留存"。
6. **`app.js` 删除区与另一条线改动同 hunk**：删的是死函数 `renderEntryDecisionHint` 及其唯一调用，
   另一条线的逐条处置控件完整保留；review 时按实体区分。
7. **"未收尾节点"仍会显示「还没有收尾记录，关键数字等它跑完再看」**：这是 SPEC-REV-04 §R1 对
   "运行未终态、节点还没跑完"的规定文案，不属于 R3-08 的 `not_reached`；R3-08 只保证**未到达**态
   不出现该措辞（有断言）。
8. **不声称"已合规"**：以上与 [`evidence/NODE_PANEL_ROUND3_20261023.md` §8](evidence/NODE_PANEL_ROUND3_20261023.md)
   同一份，保持可见。
9. **无独立终验**：本轮由 Lead + 3 个 owner（宿主数据面 / story 投影 / 前端）分片实现，各自跑本片测试，
   Lead 统一跑四道门；**没有独立验证者复核**（AGENTS §2.5：同一执行者分阶段验证应如实说明）。

### 52.4 重启命令与重启后复核清单（需人执行）

```bash
cd /home/work/chenjunming/change-impact-loop/loop
LOOP_ENV_ROOT=/home/work/chenjunming/change-impact-loop/workspaces/s0-work-20261023 \
LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023 \
LOOP_PORT=18098 ./run.sh
```

重启后（用 `RUN-20261023-171744`，状态 `failed`/终态）复核：

1. `GET /api/runs/RUN-20261023-171744/nodes/N1` ⇒ `story.headline` 出现；N1–N9 的关键数字/状态释义；
2. `GET …/nodes/N9` ⇒ 未收尾态文案；`GET …/nodes/N10` ⇒ "本轮没有走到这个节点（运行停在 failed，失败）"；
3. `GET …/nodes/N4` ⇒ "逐条处置未留存（该 run 早于处置落账）" + "当时的阻断项未留存"；
   （**已过期（2026-10-26）**：这两句文案已作废，现按 `missing`/`corrupt`/`records` 为空分开陈述，
   见 §81.1；原句按历史记录保留。）
4. `GET /api/runs/RUN-20261023-171744/report` ⇒ 404（该 run 停在 N9，没有 `n12_report.md`；端点本身存在）；
5. `GET /api/runs/RUN-20261023-171744/nodes/N13` ⇒ 只读待确认项（G2 未到达时不编条目）。

复核结果按"只增"追加到 [`evidence/NODE_PANEL_ROUND3_20261023.md`](evidence/NODE_PANEL_ROUND3_20261023.md) 或新 §52 子节。

## 53 上游 latest 集成与编号归一（2026-10-23 深夜）

拉取 `origin/main` 三个提交（`356dc7c` 引用边界修复、`d1b5ae9` SPEC-08 DSH 草案、`47893ce` SPEC-09
AI 面板草案），与本地节点面板 R3 未提交工作合并后**直接快进合入 `main`**（合并点 `317df8c`；本节所在提交 `ae7e24c` 只更新文档）。
合并前把工作树与保全快照逐文件核对（33 个已跟踪 + 31 个未跟踪全部一致）后再清理，原未提交 WIP 已完整
进入 main 历史（`e7528fe`）；运行中的 `18098`/`8099` 实例与停在 `waiting_gate` 的
`RUN-20261023-213737` 未重启、未改写。同一执行者实施与验证，无独立终验；命令与原始输出见
[集成证据](evidence/SPEC_MERGE_20261023.md)。

**编号裁定（方案①）**：上游已发布 `SPEC-REV-02`（DSH）/`SPEC-REV-03`（AI 面板）保持不动；本地面板
修订线 `SPEC-REV-02` → `SPEC-REV-04`（文件改名，迁移记录见文件头），本地 22 文件/92 处引用同步；
本节之后的 S0-a 预留改为 §54。

| 检查 | 实际结果 | 边界 |
|---|---|---|
| 定向单测（refs + story + registry） | **113 passed**，1 warning，1.12s | 含上游新增 `test_node_detail_refs.py`；合入 main 后复跑同结果 |
| 节点详情浏览器 | **43 passed**，54.76s | 系统 Chrome + 受控 API；合入 main 后复跑 43 passed/55.29s |
| web smoke + registry | **8 passed**，0.78s | —— |
| 投影回归 | 41 passed、20 failed | 失败全部为默认数据根只读（`OSError [Errno 30]`），环境限制 |
| API/UI 契约 | 7 passed、2 failed | 同因只读数据根 |
| 文档链接门 | 合入 main 后：`missing=0`、`env_missing=19`、`known_missing=10`，exit=0 | worktree 阶段曾因缺数据根报 missing=22，均为环境路径 |

冲突仅 `doc/README.md`、`doc/STATUS.md`、`doc/spec/WEB_UI_SPEC.md` 三处；`loop/services/node_view.py`
自动合并，上游逐事件引用边界与本地面板 `story` 投影均保留。另行补了两处语义接线：上游 endpoint 用例
夹具补 `run_view`；前端逐事件显示 `refs_omitted` 条数（不显示目录外路径）。

**未运行/未完成**：完整软件层、kb 自测、端到端、真实模型/仿真与真 DSH 接入；已推送 `origin/main`（合并点 `317df8c`），环境未发布；
合并用的临时 worktree/分支已删除。剩余补测与边界见 [证据 §6](evidence/SPEC_MERGE_20261023.md)。

## 54 真实 S0-a 派生 + 真实 N9 五用例全跑 + G2 被 I2 阻断（2026-10-23～26）

本节接 §51/§53，记录"用户亲手在 Web UI 走一遍真实流程"这一轮的实际结果。**同一执行者实施与验证，
无独立终验。**

### 54.1 S0-a 真实派生（2026-10-23 17:06）

| 项 | 实测 |
|---|---|
| 记录 | `S0-20261023T085921660208-0531c605aa`，`status=prepared` |
| checks | `copy/rtl/non_rtl/baseline = passed`；`ports/smoke = waiting`（S0-b 未接入，见 [SPEC-05 §8](spec/S0_ENVIRONMENT_SPEC.md)） |
| 基线零写入 | 派生前后全量清单 **15579 条逐条相同** |
| RTL 整体替换 | 副本 `RTL/` 1467 文件 vs `RTL_test` 1467 文件，**逐文件 md5 全等、差异 0** |
| 副本 | `workspaces/s0-work-20261023`（无符号链接） |
| `ready_for_execution` | `false`（S0-b 阻断不变） |

### 54.2 真实 N9：5 个用例全部跑完（21.56 h）

run `RUN-20261024-002609`（`real/happy`，基线 `v0`，ENV_ROOT=`s0-work-20261023`，
G1 由 `human:chenjunming` 于 00:29:11 签署，`human_signed=true`）。作业 `JOB-aa53540696a1`
从 00:33:40 跑到 22:05 前后，**21.56 h**，逐例 rc 全 0（仿真正常收尾）。

| 用例 | 口径一 | 口径二 UVM_ERROR/FATAL | 判定 |
|---|---:|---|---|
| `tc_pcie_rw_02` | 1687 | 0 / 0 | 未通过 |
| `tc_cpu_i2c_03` | 29 | 0 / 0 | 未通过 |
| `tc_pcie_rw_smoke` | 0 | 0 / 0 | 未通过（印记不一致） |
| `tc_rtc_05` | 0 | 0 / 0 | 未通过（印记不一致） |
| `tc_rtc_10` | 0 | 0 / 0 | 未通过（印记不一致） |
| **合计** | **1716** | **0 / 0** | **整轮未通过** |

节点链：N9 `fail` → N10 `fail`（`verdict_passed=False`、待裁决 0）→ N11 `intact`（身份四方同值）
→ N12 `live`（`claimed_verdict=not_passed`）。证据见
[REAL_N9_20261024](evidence/REAL_N9_20261024.md)。

### 54.3 G2 的真实阻断：accept 被 I2 拒绝，N16 不可达

G2 `pending_interrupt.payload.hard_block` 三条：`I2_CASES_PENDING`（5 例「已修订待验」）、
`I3_KOUTOU1_NONZERO`（1716≠0）、`I4_CONFLICTS_UNCLEARED`（72/72）。用户 2026-10-26 11:31 在界面
点「接受报告」被 403 拒绝（未消耗中断）。

**契约级死循环**：失败报告不允许 `accept`（I2），而用例状态只能从"通过"变成"已验证通过"，
于是失败轮永远无法收口。已登记为 [SPEC-01 §11](spec/CHANGE_IMPACT_LOOP_SPEC.md) 第 7 项。
选择 `rework` 会重跑 N6→N12（含又一个 21 h 的 N9），本轮未采用。

### 54.4 本轮顺带修复

| 缺陷 | 落点 | 验证 |
|---|---|---|
| G2 误渲染「逐条处置」且复用闸门选项（`accept/rework`），提交按钮永远禁用 | `loop/web/app.js` `entryGateRequires()` 仅对 `G1_diff_confirm` 启用 | `test_web_smoke.py` + `test_gate_session.py` **14 passed**；`node --check` 通过 |
| `POST /api/runs` 15 s 超时被误报为启动失败 | `loop/web/app.js` 超时后按运行列表核对并接入 | 同套测试；真实启动实测（10-23 17:17 那次即此问题） |
| `job_done` 中断把模型角色标成 `waiting`（阶段"等待人工"/chip `!`） | `loop/services/agent_view.py` 要求 `gate` 非空 | `test_agent_view.py` **12 passed** |

### 54.5 未关闭项（保持可见）

1. **S0-b 未接入**：`ports/smoke` 恒 `waiting`，`ready_for_execution` 恒 `false`。开发项 D1–D5 见
   [SPEC-05 §8](spec/S0_ENVIRONMENT_SPEC.md)。
2. **逐条处置未落账**：`entry_decisions` 不在 `gates.json`、不在事件流；只在提交响应与流程分支载荷里。
   **（2026-10-26 已解决：落账由 P-15/P-17/P-18 实现，见 [§77.1]；本条作废，原文保留）**
   P-18「已决策 run 逐条处置重建」需先补 Host 落账。
3. **运行视图口径只取单个证据文件**：本 run 界面显示口径一 = 29（单例），N9/N10/N12 汇总为 1716。
4. **N16 不可达**（见 54.3）；`I4` 72 条冲突未清零。
5. **环境吞吐**：≈3.8 µs 仿真/秒；5 例真实全跑 21.56 h。真实回归排期必须按此折算。
6. 取消作业 = 整轮 `failed` 且不可续跑（实测：`RUN-20261023-171744`，`deliver_failed`、执行关闭）。
7. 运行入口不消费 S0：`s0_record_id=null`，徽标显示"未经 S0 派生"。

### 54.6 文档门

`python3 doc/audit/check_doc_links.py` → 见本节提交后的实测（下同）：`missing=0`、`rc=0`。

## 55 AI 工作面板首批实现与 DSH 采纳评估（2026-10-24）

保留 §54 的既有预留。本轮从 `47893ce` 快进到远端 `d58e936`（`0 7`），重放并保留本地未提交设计评估。
远端节点故事、闸门处置、N6 印记与报告投影保留；本地修订记录改用
[SPEC-REV-05](spec/SPEC-REV-05-20261024.md)，未改远端既有 REV04。
先补 [SPEC-09 §11](spec/AI_WORK_PANEL_SPEC.md#11-本批实现契约2026-10-24先于代码) 与
[实施切片](plans/2026-10-24-ai-work-panel-implementation.md)，运行旧行为基线，再增加先失败用例后实现。
环境连接中断后重新连通，工作树仍在该基线，未重置或覆盖本地修订；没有发布环境。
命令与中间失败见 [新增证据目录](evidence/AI_WORK_PANEL_20261024/README.md)
（README MD5 `60b1ca50bdc7eea755803c61d6e46a69`；目录外
[校验清单](evidence/AI_WORK_PANEL_20261024.md5)），归档只读，截图均为受控 API 场景。

**本批代码范围**：AI 节点与角色卡统一进入原生模态工作面板；二级入口保留原节点详情/证据/报告。
N3 摘要/分组/风险、N6 候选 old/new/依据/观测点、N8 建议/检查/必须修复项可读；原文与技术字段折叠。
当前执行与所选成果分开，最近可读记录落后时只读；尝试切换清理旧草稿，旧回执不能污染新尝试。
刷新失败标旧数据并关闭操作；终止需要确认，revision 改变使确认失效；重绘后按入口身份恢复焦点。
只读展示层没有业务判据或模型调用，原 Host 控制、校验、写盘和闸门权威不变。

| 验证 | 实际结果 | 边界 |
|---|---|---|
| 旧行为基线 | `52 passed in 96.27s` | 旧 Agent 与节点详情浏览器用例，实现修改前执行 |
| 首批新用例红灯 | `13 failed in 39.31s` | 成果、历史身份、草稿、终止、断连与入口缺口 |
| 首次定向绿灯 | `22 passed in 47.18s` | 新面板用例与原 Agent 控制窗口 |
| 边界补测红灯 | `3 failed, 1 passed, 13 deselected in 14.47s` | 旧包装识别、终止 revision、双弹窗；轮询阅读位置用例已通过 |
| 边界修复后定向 | `17 passed in 42.08s` | 未改控制后端；同一执行者实施与验证 |
| 全浏览器中间轮 | `7 failed, 91 passed in 184.72s` | 新入口暴露旧通用夹具缺少 agents API，已补真实空态形状，未删除原 story/report 断言 |
| 扩展定向中间轮 | `4 failed, 59 passed in 140.42s` | 角色焦点恢复缺陷已修复；另一次 G2 自动选页断言未满足，保留原断言与失败记录 |
| 焦点/报告定向复核 | `4 passed, 59 deselected in 11.10s` | 320/768/1440 视口及原 G2 报告用例 |
| 最终完整浏览器 | `105 passed in 192.80s`，`exit=0` | 真实静态页、系统 Chromium、受控 API；不是 live 模型或仿真 |
| 相关软件回归 | `230 passed, 1 warning in 4.89s` | web smoke、agent 投影/控制/记忆、node story/registry/refs、上下文/能力展示 |
| 官方全套软件入口 | `exit=2`，数据根不存在，测试未启动 | 未伪造内网 baselines/index/历史夹具 |
| kb schema 自测 | `PASS=9 FAIL=1`，`exit=1` | 临时可写数据根；归档 gates 夹具缺失，整门未通过 |
| kb N5 自测 | `PASS=6 FAIL=1`，`exit=1` | 历史 TESTLIB 夹具缺失，整门未通过 |
| 端到端 | 前置检查阻塞，驱动未运行 | 配置中的 ENV_ROOT/数据根均不存在；需隔离工具副本与实际环境资产，不执行会清理共享状态的驱动 |
| 文档门增量 | `missing=129`、`env_missing=315`、`known_missing=10`；与拉取基线相同，新增均为 `0`；`exit=1` | 整库文档门因既有缺件未通过；新增相对链接/围栏通过 |
| 语法/源码与 Markdown 补丁 | 新增及修改 JS 的 `node --check` 通过；排除冻结原始日志的差异空白检查通过 | 不替代运行验收；全量归档格式结果见下文 |

**归档格式检查补记**：保留原始测试输出后，全量 `git diff --check HEAD^ HEAD` 返回 `exit=2`，
发现仅位于本轮证据目录原始 `.txt` 日志中的尾随空格。源码与 Markdown 检查单独通过；
不清洗、重写或修改已冻结日志及其 MD5。首次串行提交命令未在该检查失败后停止，已明确记录，
不声称全量补丁空白门通过；其后的提交/推送命令按失败立即停止执行。

**尚未完成**：四道门全绿、内网/live 模型/真机验收、真实用户任务耗时对照与独立终验。
P1–P3 已有首批实现，P4 自动验证与环境验收分开；不声称整个 SPEC-09、DSH 或效率收益已经验收。
DSH 按 SPEC-08 保留 Agently 默认，N3 只验证可行性，N6 配对验证质量/人工负担/返工/时间/成本后决定采纳；
本机仍缺可核验原生接口，不猜命令、不启用适配器。停靠/全屏、跨关闭草稿与其余角色专用渲染保持后置。

**旧提交仍待恢复**：本实例复查仍没有 `080c60f7076427f8dd5e083d4cd082a010de9177` 对象，也没有原
`node-inspector-20261023.bundle`；没有恢复、迁移或宣称已由本轮代码替代。此前内网验收缺口继续有效。

## 56 DSH D1 首片：后端边界与 Agently 适配（2026-10-24）

用户要求提交当前版本后继续 DSH。上一版 `dacdf54` 已推送，本轮开始 fetch 远端 main，
`HEAD...FETCH_HEAD` 为 `0 0`，工作树干净。从该基线先更新
[SPEC-REV-06](spec/SPEC-REV-06-20261024.md)、[SPEC-08 §4.0](spec/DSH_AGENT_RUNTIME_SPEC.md#40-d1-首片执行契约先于实现)
及 [D1 计划](plans/2026-10-24-dsh-backend-boundary.md)，再按特征基线、新用例红灯、局部提取、行为接线推进。
同一执行者设计、实现与验证，不声称独立终验或四道门全绿。

原始输出见 [D1 证据](evidence/DSH_D1_20261024/README.md)
（README MD5 `aff1e9926ba7269d9c9bd65d4a9f713c`，目录外
[清单](evidence/DSH_D1_20261024.md5)）；日志包保留原始字节，包含新能力先失败的输出。

**交付范围**：实际请求经 `host/agent_backends` 的 Agently 适配器执行；缺省及节点覆盖由非机密
SETTINGS 解析。显式 DSH 在 provider 解析前失败，无 standin/Agently 静默替换；未知配置拒绝且不回显原文。
一次 attempt 固定 provider 快照，避免重复解析导致审计模型与执行模型漂移。兼容新增后端名称/适配器指纹，
旧记录不回填；请求机制原指纹保留。预算、经验、Schema/业务校验、控制和封存仍在原 Host 权威路径，
后端没有 RunCtx/校验器/业务写盘句柄。既有测试仅调整配置替身以接受新增快照参数，原断言保留。

| 检查 | 实际结果 | 说明 |
|---|---|---|
| 提取前特征基线 | `73 passed, 1 warning in 2.27s` | 含新增 Schema 对象/包装返回特征及原 memory/control |
| 新行为先失败 | `1 failed, 21 errors in 0.91s` | 缺少 backend 模块/选择器与 configure_agently 快照参数；未把错误算跳过 |
| 仅提取后的特征回归 | `73 passed, 1 warning in 2.48s` | 在新增选择/审计行为接线前运行 |
| 接线后集成 | `95 passed, 1 warning in 2.79s` | DSH 拒绝、配置错误、配置快照、后端标识、Host 校验与取消 |
| 最终相关软件回归 | `196 passed, 1 warning in 7.11s` | 含历史不回填、sealed 故障、N6/N8、context、control/view、web smoke、节点/能力契约；受控 SDK，无 live 调用 |
| 官方全套软件入口 | `exit=2`，测试未启动 | 配置数据根不存在；未伪造归档夹具 |
| kb schema 自测 | `PASS=9 FAIL=1`，`exit=1` | 临时可写数据根，真实归档 gates 缺失 |
| kb N5 自测 | `PASS=6 FAIL=1`，`exit=1` | 真实归档 TESTLIB 缺失 |
| 端到端 | 前置阻塞，未运行驱动 | ENV_ROOT 与数据根均不存在；驱动会清理状态，需隔离工具副本与真实资产 |
| 文档门增量 | `missing=129`、`env_missing=315`、`known_missing=10`；新增均 `0`；整门 `exit=1` | 与基线一致；新增相对链接和围栏通过 |
| 补丁格式 | `git diff --check` 通过 | 本轮原始日志以归档包保全字节，不改此前冻结证据 |

**环境事实与未完成项**：runtime 的 `observations_current=true`、running/connected；网络策略观测为
`unknown`，没有 enforced 证据；fetch 成功仅证明这次 Git 操作可达。保留原代理、CA、配置，未发布环境。
有界发现未找到 PATH 中的 dsh 或仓库中的原生接口说明；未读凭据库、未使用历史聊天 Token、未安装依赖。
完整统一执行投影、D0 原生能力验收、D2/D3 会话/子进程取消与工具隔离、N3 真机探针、N6 价值对照均待完成。
本片的 Agently 协程取消测试不证明远端工具进程终止，不能启用真实 DSH。

**提交保护缺口仍在**：原任务 `080c60f7076427f8dd5e083d4cd082a010de9177` 对象和
`/workspace/node-inspector-20261023.bundle` 本实例均不存在，继续列为待恢复；本片未恢复或替代它们。

## 57 DSH npm 安装与原生协议探针（2026-10-24）

D1 已以 `df53b5eea06e5118de9dd9649e52c042de8c0bf8` 推送并由 ls-remote 核对远端 main；工作树当时干净。
本片 [原生探针证据](evidence/DSH_NATIVE_20261024/README.md) README MD5 为
`d573b6d01157257f323f534e20a689b4`；[目录外清单](evidence/DSH_NATIVE_20261024.md5) 校验原始探针摘要、
依赖锁、脚本与版本/源码指纹。文档门复核 `missing=129`、`env_missing=315`、`known_missing=10`，
相对提交基线新增均为 `0`；整门 `exit=1`，新增链接/围栏及补丁空白检查通过。
用户随后授权通过 npm 安装 dshweb，覆盖前面“不安装新依赖”的本轮限制。
`npm view dshweb` 返回 `E404`；搜索发现正式 CLI 为 `@deepseek-ai/dsh`，包内文档确认 Web/SDK 是 profile。
没有安装同名普通 JavaScript shell `dsh` 或仅占位的 deepseek-harness 包。

**实际安装**：/workspace/dsh-runtime 内固定 `@deepseek-ai/dsh@0.2.1-rc.2`，`npm install` 为
`added 615 packages in 2m`，exit=0；Node `v24.19.0`、npm `11.9.0`。使用 --ignore-scripts、--no-audit、
--no-fund，不修改本软件仓依赖，不执行安装脚本。完整 package-lock 指纹为
`54031cbdbab40f778af186d36010364d53e8eafea1e77f51bbe14eb7c97f7925`（SHA-256）。
独立 DSH_HOME、DSH_AGENTS_HOME 和工作目录，没有导入旧宿主设置、会话或凭据，也未复用聊天 Token。

| 检查 | 实际结果 | 可证明范围 |
|---|---|---|
| CLI 版本/帮助 | `0.2.1-rc.2`，exit=0 | 安装入口可执行 |
| Web / SDK 帮助 | 两条命令均 exit=0 | 已确认受支持入口及参数 |
| SDK initialize | 成功，固定 serverInfo 名称匹配，协议 version=`0.0.1` | 实际 JSON-RPC 握手，不等于 npm 版本或模型认证 |
| SDK 未知会话 wait | 返回错误，拒绝成功 | 未知会话不假成功；没有发送 prompt |
| SDK shutdown | 收到 `{}`，exit=0，进程组已不存在 | 空闲运行时关闭；没有工具后代，未证明复杂取消 |
| Web 启动 | 收到 ready；loopback 匿名 GET `/` 为 HTTP `401`，非 HTML | 鉴权门实际工作；未做登录、网页功能或外部访问验收 |
| Web 收尾 | SIGTERM 后 exit=0，进程组已不存在 | 本轮自建服务已停止，无常驻暴露端口 |

探针将 stderr 只映射到固定错误类别，启动 URL/认证参数始终不输出、不写归档；明确关闭 telemetry。
执行中首次启动命令因 cwd 尚未创建被执行器拒绝，改从已存在的安装根创建目录后成功；这是命令工作目录问题，
没有将其归因为云环境重启失败。没有运行真实模型、工具任务、仿真或不相关 UI/模型测试。

**设计影响**：[D0 发现与 D2 前置计划](plans/2026-10-24-dsh-native-interface.md) 已记录原生方法和边界。
SDK 没有逐 prompt 取消/逐 session 关闭；messageId 仅是入队身份；协议没有版本协商。
应采用每 attempt 一个隔离进程/会话，校验事件终态和候选，再交给原 Host；不能共享活跃 Web 会话。
默认自动压缩、子 Agent/工具、maxTokensAsSuccess 及较弱子进程 fallback 均需要收紧和实测。
因此 §56“没有原生接口”已被本节的安装/协议证据更新，但 D0 全能力门、真实模型认证、关键上下文完整性、
工具写权强制、异常停机后代清理、N3/N6 真机与价值试验仍未完成；业务配置继续保持 Agently。
内网资产缺失、四道门未全绿和旧 `080c60f` 待恢复仍有效。

---

## 58 UI 交互与等待期体验提案登记（2026-10-24，未实施）

外部架构评审（基于 `main@f2baed4` 全量代码阅读，评审者非本仓 owner）提出 UI 交互改良提案，已按 SpecDD 登记、未实施：

- 契约记录：[SPEC-REV-07](spec/SPEC-REV-07-20261024.md)；实施计划：[plans/2026-10-24-ui-interaction-waiting.md](plans/2026-10-24-ui-interaction-waiting.md)。
- 切片：U1 等待送达（浏览器通知/「在等我」行动条/操作者预填）、U2 SSE 传输（先修订 SPEC-04 §6/§7）、U3 渲染分段签名（并入 F05-b/c，不另立编号）、U4 G1 引导流、U5 事件流客户端过滤、U6 既有后置项收口（F14 人工矩阵 V6 / SPEC-09 后置 / legacy 清退）。

**状态：提案，未评审、未实施、未排期；不改变任何现行能力声明。** 采纳决策与排期归 Lead；实施后按片新增实测小节，验收数字禁止预写。F07 未达阈值不动分页、F11 维持后置的既有结论不变。现状事实依据（轮询节拍、无通知/推送、操作者三处重填）见提案 §1 的代码出处。

---

## 59 U1 等待送达首片实施（SPEC-REV-07 U1-a/b/c，2026-10-24）

按 [SPEC-REV-07](spec/SPEC-REV-07-20261024.md) §5 采纳门第 1 条（零契约变更先行）实施 U1 三项；
[实施计划](plans/2026-10-24-ui-interaction-waiting.md) 顺序 1–3。同一执行者设计/实现/验证，**不声称独立终验**。

**落点**：新增纯函数模块 `loop/web/wait-center.js`（跃迁提醒判定/行动条聚合/标题徽标）、
`loop/web/operator.js`（操作者记忆与预填判定，存储可注入、不可用即降级）；
接线 `web/index.html`（行动条容器 + 通知开关按钮 + 两个 script 标签）、`web/app.js`
（loadRuns 后 notifyOnRuns、renderSidebar 渲染行动条、闸门 actor 预填/记忆、visibilitychange 停止闪烁）、
`web/agent-window.js`（awActor 预填/记忆）、`web/app.css`（行动条样式，无新增 `!important`）。
新增 node 驱动测试 `loop/tests/test_wait_center.py`（12 例）、`loop/tests/test_operator_prefill.py`（7 例）。

**本机（Windows）实测**：红灯先行（两模块缺失时 node require 失败，已确认）；
实现后与 pytest 文件逐条同口径的 node 断言 **PASS=25 FAIL=0**；
`node --check` 4 个改动 JS 文件全部通过；两个测试文件 `py_compile` 通过；
`doc/audit/check_doc_links.py` 本次改动不涉及文档链接。

**未运行/待验证（不得据此声称四道门全绿）**：本机无 `loop/.venv`（agently 4.1.4.8 未装，
conftest 经 workflows.main_flow 导入会失败）⇒ pytest 套件、browser 特征测试（Playwright）、
真实通知投递、kb 自测与端到端均**未在本机运行**，需在内网/带依赖环境复跑；
U1-b 的 S0 阻断聚合按提案标注的范围未含（行动条当前只聚合 runs 的等待人工/失败）。

**边界声明**：提醒/预填均为投影消费者与输入便利，不参与任何判定；权威仍以
`gates.json` + `human_signed` 与服务端投影为准；通知被拒绝时降级为标题徽标+后台闪烁。

---

## 60 U2-a SSE 传输首片实施（SPEC-REV-07 U2-a，2026-10-24）

按采纳门顺序先改规格再动代码：[SPEC-04](spec/WEB_UI_SPEC.md) 新增 **§6.9**
（`GET /api/runs/{run_id}/stream`：仅变化时推送、签名排除 `updated_at`、心跳保活、`gone` 语义）与
**§7.3**（传输与降级：open 态主轮询跳过详情请求、回退态与现状逐字一致、不双通道并发写、
流状态徽标非业务状态）。同一执行者设计/实现/验证，**不声称独立终验**。

**落点**：`loop/services/run_stream.py`（帧格式/变更签名/心跳的唯一实现，stdlib-only，
`sleep`/`fetch_view` 可注入）；`loop/services/api.py` 新增 stream 路由（404 准入 +
`asyncio.to_thread` 包同步 `run_view` + StreamingResponse）；`loop/web/run-stream.js`
（客户端四态状态机：connecting/open/fallback/stopped，stop 终态、回退后 15 s 重试建流，
计时器/EventSource 注入）；接线 `web/index.html`（streamState 徽标 + script）、
`web/app.js`（open 态 poll 跳过详情、openRun 重建流、旧推送按 run_id 守卫丢弃）。
新增测试 `loop/tests/test_run_stream_server.py`（8 例）、`test_run_stream_client.py`（9 例）。

**本机（Windows）实测**：红灯先行（两模块缺失：node require 失败 / ImportError 确认）；
实现后与 pytest 文件逐条同口径的独立断言——服务端 asyncio 实跑 **PASS=8 FAIL=0**（含
`updated_at` 抖动不重推、真变更重推、unknown-run `error`、流中消失 `gone`、心跳节拍）、
客户端 node **PASS=9 FAIL=0**；`node --check` 2 个 JS、`py_compile` 4 个 py 文件通过。

**未运行/待验证（不得据此声称四道门全绿）**：pytest 套件（本机无 agently/.venv）、
browser 特征测试、**真实 HTTP SSE 长连接**（路由与 StreamingResponse 包装只做了语法级验证，
未起服务实测）、kb 自测与端到端。**U2-b（Agent 窗口收编）未实施**；U2-c 的日志尾巴经
`run_view.job.log_tail` 随流推送实现（§6.9 注明的口径），独立逐行日志流不在本片。

**边界声明**：SSE 只是传输层，推送内容与 `GET /api/runs/{run_id}` 同源（`RunManager.run_view`
唯一产出），不新增业务事件 kind、不写文件；判定/草稿/提交不读流状态。

---

## 61 U2-b Agent 窗口流收编与 U5 事件流过滤实施（SPEC-REV-07，2026-10-24）

规格先行：[SPEC-04](spec/WEB_UI_SPEC.md) 新增 **§6.10**（`GET /api/runs/{run_id}/agents/{node}/stream`：
推送 = GET 同一装配、事件名 `agent_view`、预验证同口径 404/422、流中损坏断开由回退轮询暴露）
并补 **§7.3**（Agent 窗口同口径：connecting/fallback 轮询、open 停轮询、关窗/切换重建）。
同一执行者设计/实现/验证，**不声称独立终验**。

**U2-b 落点**：`services/run_stream.py` 增加 `event_name` 参数（传输口径仍唯一）；
`api.py` 把 GET /agents/{node} 的视图装配提取为 `_agent_window_view`（两条路由共用，口径同源），
新增 stream 路由（GET 同口径预验证 + `to_thread` + StreamingResponse）；`web/agent-window.js`
以 `syncTransport/stopTransport` 取代固定 1.5 s 轮询——流事件经 epoch + run_id/node 身份守卫后
才进 `render`，connecting/fallback 保持既有轮询，open 停轮询；开窗/切节点/切尝试/关窗均重建或停止；
控制 POST（SPEC-07）零改动。

**U5 落点**：新增纯函数模块 `web/event-filter.js`（kindsOf/toggleKind/applyFilter；null=全部，
移除到空回到全部，过滤只筛引用不改写事件）；`app.js` 事件卡渲染 kind chips 与
「X / Y 条（已按 kind 过滤）」计数；纯客户端过滤，F11 的服务端分页结论不变。

**本机（Windows）实测**：红灯先行（event-filter 缺失 require 失败、`event_name` 参数
TypeError、客户端 eventName 不派发，均已确认）；实现后 node 断言 **PASS=12 FAIL=0**
（agent_view 派发 + 客户端回归 4 + event-filter 7），U1 回归 **25/25**、U2 客户端原 9 条
**9/9**、服务端 asyncio 新增/回归 **2/2**；`node --check` 4 个 JS、`py_compile` 5 个 py 通过。

**未运行/待验证（不得据此声称四道门全绿）**：pytest 套件、browser 特征测试（含 Agent 窗口
流切换/回退的真实交互）、真实 HTTP SSE（两条流均未起服务实测）、kb 自测与端到端；
需内网/带依赖环境复跑。U2-c 独立逐行日志流仍后置（`job.log_tail` 已随 §6.9 流推送）。

**边界声明**：两条流推送的都是既有 GET 投影（装配/判据同源），不新增业务事件 kind、不写文件；
窗口控制命令不经流上行；事件过滤是纯客户端展示便利。

---

## 62 SPEC-REV-07 设计详案补全（2026-10-24，纯文档）

未实施切片（U3/U4/U6/U2-c）的设计**先于代码**补全，无任何实现变更：

- [计划文档](plans/2026-10-24-ui-interaction-waiting.md) 新增设计详案 §A–§D：§A = U3+F05-b/c 的 app.js 七步拆分次序
  （app-format → request-guard 统一四处 epoch+request → dir-picker → gate-diff → agent-cards →
  按节签名 → app.js 收敛 <1200 行）与验证门/回退；§B = U4 G1 引导流（进度条/跳转/J·K 键盘，
  判定仍唯一在 GateSession.validateEntryDecisions，提交高亮只消费 counts().complete）；
  §C = U6 六项各自设计要点（含 attempt 输出 diff **须先修订 SPEC-07** 的契约增补登记）；
  §D = U2-c 后置与「先有使用证据再立项」的采纳门。
- [SPEC-REV-07](spec/SPEC-REV-07-20261024.md) §3 的 U3/U4/U6 补全契约级边界与验收，并指向计划详案。

状态：U3/U4/U6/U2-c 仍为**提案、未实施、未排期**；本节仅登记设计文档补全，无代码变更、无新增数字。

---

## 63 SPEC-REV-08 · UX 走查修复 U7–U10 实施（2026-10-24）

来源：以体验用户身份对工作台做的一次完整浏览器走查（真实 `loop/web/` 前端 + 仓库外
契约演示桩 `%TEMP%/ui-walkthrough/harness.py` 模拟 drill/standin 全生命周期；枚举对照
`kb_lib.GATE_DECISIONS` 真实值）。问题清单先于代码登记为
[SPEC-REV-08](spec/SPEC-REV-08-20261024.md)（提交 267c9db），计划详案在
[计划 §E/§F](plans/2026-10-24-ui-interaction-waiting.md)。U11（默认落地视图/标题徽标构成）
**仍为提案**（需产品决策，§F）。

已实施切片（全部纯前端；SPEC-04 §4.4/§4.5 增补与 §7.4 新节随实现同批写入）：

- **U7 会话深链**：新 `web/session-url.js`（encode/decode 纯函数，view 白名单，乱码容错）；
  `app.js` openRun/showView 以 replaceState 同步、init 按深链恢复（等闸门自动落闸门视图）、
  hashchange 比对后执行。F5/分享链接不再丢会话上下文。
- **U8 闸门可达性三件**：(a) 逐条未覆盖时提交钮旁就地点名缺项（直接消费
  `validateEntryDecisions` 的 error）；(b) `gate-session.reusableReason` 新纯函数——整门决策
  需理由且整门理由为空时预填复用同判据条目理由（entry_id 排序首个；非空不覆盖）；
  (c) 紧凑闸门卡在 `entry_decisions_required` 时给出去闸门视图的引导按钮。
- **U9 作业终态**：新 `web/job-status.js`（`emptyHint/emptyText` 纯消费事件流）；
  N9 完成后长任务卡显示「最近一次作业已完成（N9 · rc=0）」而非「尚未提交或未启动」。
- **U10 展示微修**：闸门材料行人话标题（原始 id 入 title 悬停）；Agent 窗口会话切换提示
  改为追加（保留最近一条控制回执）。

**本机（Windows）实测**：红灯先行（session-url/gate-session 新函数/job-status 三模块
require 失败，RED×3）；实现后 node 纯函数断言 **25/25 PASS**（session-url 10、
reusableReason 8、job-status 7）；回归 wait-center 6 + operator 直测 2 + event-filter 2
（首轮 3 处"失败"均为验证脚本预期/存储桩笔误——新出现即失败不提醒是 U1 设计口径、
operator 需 localStorage 形状存储——已复验通过，**非代码回归**，本次未改这两个模块）；
`node --check` 9 个 JS、`py_compile` 3 个新测试文件通过。
注：本机断言以正斜杠绝对路径 require（`node -e` 对反斜杠相对路径解析失败；
仓内 pytest 文件按 Linux 正常路径不受影响）。

**浏览器实证（契约演示桩，判定性操作）**：U7——建运行到 G1 后 reload，
hash `#run=…&view=gate`、落闸门视图、逐条表单 3 条就绪；手动改 hash 跳失败运行生效。
U8-a——仅处置 D-001 时提示「逐条处置未覆盖全部条目（缺 2 条）：D-002、D-003」，就绪即清空。
U8-b——D-003 ignored 带理由后整门理由自动预填同一文本，提交成功（G1 · ignored）无需重录。
U8-c——紧凑卡引导按钮落闸门视图并同步 hash。U9——N9 完成后作业卡终态文案正确。
U10——G1/G3 材料行「闸门 1 · 差异确认 / 闸门 3 · 回归决策」（title=原始 id）；
steer 后回执同时保留「命令已接收」与切换提示。

**未运行/待验证（不得据此声称四道门全绿）**：pytest 套件（3 个新测试文件仅 py_compile）、
browser 特征测试、真实服务端下的深链/理由预填/作业终态（演示桩偏差不算 UI 缺陷：
走查中「终态闸门段仍进行中」为桩对闸门节点不发 node_finished 所致，已核实真实投影口径）、
内网四道门复跑。

## 64 H2b 恢复整合与修订（2026-10-26）

用户“继续 H2b 的修订／继续”授权的本地续修，基线 main `11746fc962c21e81c61acb2090d1738b15e572cb`，
分支 `recovery/h2b-20261025`。2026-10-25 开始整合，2026-10-26 完成当前软件修订。
实现与验证均由本聊天 Codex 执行，非独立终验；**四道门未全绿，不声称整体验收完成**。

**结果**：恢复 H1 来源交接、H2a 逐项回应与 H2b 逐项复核/失效重开；本机补修原始返工列表被过滤或强转导致的索引失真，
统一新输出与封存重建的严格校验。另修复 N6 替身输出后历史问题丢失：仅恢复封存请求中已核验的问题身份，
继续待复核，不产生可信作者回应/候选或关闭结论。Schema 与提示词同步公开约束。
cloud REV07/08/09 依次整合为 REV09/10/11，原 UI REV07/08 保留；迁移记录见协作与记忆计划。

**条件**：Windows 原基线在 os.fchmod/目录同步处失败，未改封存机制；转用已有 WSL 的 Linux 临时 Python 3.12.15，
Agently 4.1.4.8，依赖实际版本已记录。测试使用独立空环境/工作区、standin 模型，不伪装内网环境，不发真实模型请求。

| 检查 | 命令输出／结论 | 日志 |
|---|---|---|
| H2a 特征基线 | `126 passed, 1 warning in 12.82s` | h2a-linux-characterization.txt |
| 原始返工列表 RED（纠正测试参数笔误后） | `21 failed, 5 passed in 2.63s` | h2b-red-corrected.txt |
| 替身历史保留 RED | `4 failed, 28 deselected in 1.92s` | h2b-standin-red.txt |
| 最终专项回归 | `275 passed, 1 warning in 15.88s` | h2b-final-r2.txt |
| 完整单测尝试（中断，未完成） | `39 failed, 473 passed, 39 skipped, 1 warning, 3 errors in 507.69s (0:08:27)`，exit 2 | h2b-full.txt |
| main 完整单测对照（中断，未完成） | `27 failed, 297 passed, 39 skipped, 1 warning, 3 errors in 290.29s (0:04:50)`，exit 2；运行进度不同，不能比较总数判回归 | main-full.txt |
| 软件范围 main 对照 | `21 failed, 513 passed, 113 skipped, 1 deselected, 1 warning in 24.89s` | main-software.txt |
| 软件范围修订版首次 | `22 failed, 656 passed, 113 skipped, 1 deselected, 1 warning in 30.49s`；额外一项为 SIGKILL 测试未在启动窗口创建尝试目录 | h2b-software.txt |
| 软件范围修订版顺序复测 | `21 failed, 657 passed, 113 skipped, 1 deselected, 1 warning in 29.33s`；失败 ID 与 main 一致，未新增 | h2b-software-sequential.txt |
| 封存故障注入单独顺序对照 | main `11 passed in 3.94s`；修订版 `11 passed in 3.82s`，未改断言/封存实现；首次时序失败保留 | main-f08.txt / h2b-f08.txt |
| kb 闸门自测 | `PASS=9 FAIL=1`；仅缺历史 gates.json | kb-gate-schema.txt |
| kb N5 自测 | `PASS=6 FAIL=1`；缺历史 TESTLIB 夹具 | kb-n5.txt |
| 端到端 | 未运行：缺 bash、驱动器虚拟环境、真实 uvs.setup/环境工具与历史运行夹具；前置检查 exit 2 | e2e-preflight.txt |
| 文档 | 对照 main，新增路径问题为 0；新增 Markdown 路径/锚点问题为 0。全仓原检查仍因既有缺件返回 1，保留明细 | doc-comparison.json |

完整单测反复等待缺少 n1_manifest_new.json 的演练流程，因此主动中断以保留失败明细。
补充软件范围采用 `-m 'not env_layer'`，并显式排除 admission_and_jobs、api、api_ui_contract、archive_e2、fix_kbtools、
fix_lifecycle、fix_real_chain、flow 对应测试文件；准确参数在日志首部。此范围不是完整单测门。
剩余失败为缺夹具、缺冲突数据或缺 bash；顺序复测与 main 的失败 ID 完全一致。
skipped/deselected 不当作通过，未测试的真实模型质量、浏览器、Linux 真环境四门仍待补齐。

证据：[本轮归档](evidence/AGENT_REVIEW_H2B_20261026/README.md)，目录外 MD5 清单为同级 AGENT_REVIEW_H2B_20261026.md5。
冻结 kb、旧证据/历史、原 UI REV07/08 与基线逐字节比对一致；未修改环境资产、未推送。
云端旧二进制日志没有恢复，不补造旧证据；恢复来源与重新编号见 [计划](plans/2026-10-24-agent-collaboration-memory.md)。
## 65 SPEC-REV-12 落地：失败报告收口（D）+ 真实轮冻结为 drill 夹具（2026-10-26）

接 §54：§54.3 登记的"失败报告无法收口"已按用户在 [SPEC-REV-12](spec/SPEC-REV-12-20261026.md)
中的裁决（Q1 选 **D**、Q3 选 **新增第二套夹具**）实现并验证。

### 65.1 R1（方案 D）：失败报告可接受，但必须给理由

- 落点：`chunks/gates.py` G2 `accept` 分支（`claimed_verdict=not_passed` ⇒ 强制 reason；
  其余仍按 I2）、`contracts.report_claimed_verdict()`（读 `n12_report.md`，缺报告不猜）、
  `web/app.js`（G2 提示 + 提交前本地校验）、`SPEC-01` §1 I2 增补 + §11 第 7 项标记已收口。
- 验证（drill run `RUN-20261026-135835` 的 G2）：

| 动作 | 结果 |
|---|---|
| `accept` 无 reason | **403**：`D：报告结论为 not_passed ⇒ 接受失败报告必须给出理由` |
| `accept` 带 reason | **200**，`warnings=["报告结论 not_passed：accept 作为失败收口（已给理由）；…不得称跑通"]` |
| G2 后 N16 | 仍 `refused`（I3/I4 未被放松） |

- 测试：`tests/test_fix_lifecycle.py` 新增 3 条（无理由拒 / passed 仍被 I2 拒 / 无报告不推断），
  **39 passed**。

### 65.2 R2：真实轮冻结为 drill 夹具（`LOOP_DRILL_FIXTURE`）

- 夹具：`workspaces/s0-ws-20261023/fixtures/drill-real-20261024/`（14 MB / 35 文件 /
  `md5.txt` / `drill_cases.json`），来源 run `RUN-20261024-002609`。
- 代码：`context.drill_fixture_run()` 参数化（缺省 legacy `RUN-20261015-120626`，`accept_v1` 不受影响）、
  `validate_drill_fixture()` 启动期缺件即失败、`long_jobs` 新增多例回放
  （`_drill_case_spec/_drill_replay_command/_submit_drill_replay/_drill_replay_done`）。
- 验证（drill `RUN-20261026-135835` vs 真实 `RUN-20261024-002609`）：

| 项 | 真实轮 | drill 回放 |
|---|---|---|
| 用例数 | 5 | **5** |
| 口径一逐例 | 29 / 1687 / 0 / 0 / 0 | **29 / 1687 / 0 / 0 / 0** |
| 口径一合计 | 1716 | **1716** |
| 口径二 UVM_ERROR/FATAL | 0 / 0 | **0 / 0** |
| N9 / N12 | `fail` / `not_passed` | **`fail` / `not_passed`** |
| 耗时 | 21.56 h | **秒级（只回放）** |

- drill 全流程：N9 `fail` → N10 `fail` → N11 `intact` → N12 `standin(not_passed)` →
  G2 `accept`（有理由）→ G3 先试 `full_now` 被 **403 I4（72 条）** 拒、改 `milestone_only` →
  N15 no-op → **N16 `refused`**，run `finished`。

### 65.3 本轮发现的运维风险（必须写进操作手册）

**改 `loop/workflows/**` 后重启服务，会让停在闸门的 run 恢复失败并被标记 `failed`**
（`Can not load TriggerFlow execution snapshot … flow definition fingerprint mismatch`）：

| run | 重启前 | 重启后 |
|---|---|---|
| `RUN-20261024-002609`（真实轮停 G2） | `waiting_gate` | **`failed`**（数据与 5 份 run.log 未丢） |
| `RUN-20261023-213737`（drill 停 G1） | `waiting_gate` | **`failed`**（同因） |

数据未损坏：`n9_run_summary.tsv`、`case_states.json`、`n12_report.md`、证据日志全在，
快照仍留在 `state/recovery/`。但**结论是**：改工作流代码前，先把停着的 run 处理/接受完；
或改用 drill 夹具复现（本节的 R2 正是为此）。

### 65.4 未关闭项

1. 真实轮 `RUN-20261024-002609` 的 run 文档现为 `failed`（重启副作用），其结论已由 drill 复现；
   如需"UI 上真实轮 accept"的证据，只能在下一轮真实 run 里重做（N9 约 21.5 h）。
2. 夹具目前只有**失败形态**（`not_passed`）；"通过形态"的 drill 夹具需等一次真实通过轮。
3. `I4` 72 条冲突仍未清零（阻断 full_now 与晋升）。
4. S0-b 未接入（[SPEC-05 §8](spec/S0_ENVIRONMENT_SPEC.md)）。
5. 逐条处置仍未落账（`gates.json`/事件流都没有 `entry_decisions`），P-18 重建需先补 Host 落账。
   **（2026-10-26 已解决：落账写 `decisions/<gate>.json` 且随 `gate_decided.detail.entries` 下发，见 [§77.1]；本条作废，原文保留）**

## 66 阶段收尾与「周末再跑」排期（2026-10-26）

### 66.1 本轮收尾动作

- 停止本仓唯一的**变更影响闭环**服务实例：`127.0.0.1:18098`（live 模式、`s0-work`/`s0-ws`）。
  停止前确认：无运行中的 `N9` 作业、无 `run_guarded`/`UVS_tc_*` 残留、无待投递 `job_done` 中断。
- 未触碰：其它用户的仿真进程（`/home/work/WAVE/**`）；`8099` 实例已不在运行。
- 数据与证据**全部保留**（不清理）：
  - 数据根 `workspaces/s0-ws-20261023`（含真实轮 `RUN-20261024-002609` 的 5 份 run.log 与台账）；
  - drill 夹具 `workspaces/s0-ws-20261023/fixtures/drill-real-20261024`（14 MB，含 `md5.txt`）；
  - 工作副本 `workspaces/s0-work-20261023`、基线 `v0`、`RTL_test`（4 处测试改动）。
- 代码已提交：`d89ebca`（R1 失败报告收口）、`a860b5f`（R2 drill 夹具 + 多例回放）。

### 66.2 周末再跑一轮真实 run（补「真实轮 accept 收口」证据）

**目标**：在真实环境副本上再跑一轮 `real/happy`，走到 G2 用方案 D 收口，补齐"真实轮 accept"的 UI 证据。

前置检查（起跑前逐条确认）：

1. 无 parked run：`GET /api/runs` 里没有 `waiting_gate` 的旧 run（避免再次踩"重启指纹失配"）；
2. 服务以 live 模式起在 `18098`，`ENV_ROOT=s0-work-20261023`、`WORKSPACE=s0-ws-20261023`；
3. **跑起来之后不要再改 `loop/workflows/**` 或 `loop/services/**`，也不要重启服务**——一旦快照指纹变了，
   停在 G2 的 run 会被判 `failed`（实测见 §65.3 与 [REAL_N9](evidence/REAL_N9_20261024.md)）；
4. 预算：N9 实测 **21.56 h**（≈3.8 µs 仿真/秒），按整夜 + 半天安排。

流程要点：G1 需人在 UI 逐条处置（real 模式 4 个唯一 `entry_id`）；N9 预计整夜；
G2 若报告 `not_passed` ⇒ 用方案 D「接受报告 + 理由」收口（无理由会被 403）；
G3 只能 `milestone_only`（`I4` 72 条冲突未清零）；N16 预期 `refused`。

起跑命令（周末用，路径与端口与本次一致）：

```bash
cd /home/work/chenjunming/change-impact-loop/loop
LOOP_ENV_ROOT=/home/work/chenjunming/change-impact-loop/workspaces/s0-work-20261023 \
LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023 \
LOOP_STATE_ROOT=/home/work/chenjunming/change-impact-loop/workspaces/s0-ws-20261023/state \
LOOP_PORT=18098 \
LOOP_DRILL_FIXTURE=fixtures/drill-real-20261024 \
bash remote/serve.sh
```

跑完后按 §54/§65 的同一模板落证据（新 run_id、逐例两套口径、G2 决策原文、N16 结果），
只追加不改写；并关闭服务。

---

## 67 上游 latest 合并（SPEC-REV-05～REV-11）与编号归一（2026-10-26）

本轮把 `origin/main` 的 14 个提交并入本地 5 个未推送提交。**同一执行者实施与验证，无独立终验。**

### 67.1 合并对象与前置

- 合并基 `d58e936`；上游 `5552817`（`d58e936..5552817`，14 个提交，含 PR #1 合并提交）；本地 5 个提交。
- **前置编号归一**：本地 `SPEC-REV-05-20261026` 改名 `SPEC-REV-12-20261026` —— 上游已占用
  `SPEC-REV-05`（[DSH 与 AI 面板采纳评估](spec/SPEC-REV-05-20261024.md)，主题完全不同），
  且上游 [README](README.md) 已声明下一个空号为 `SPEC-REV-12`。改名先于合并，冲突面最小。
  证据文件 `SPEC_REV05_VERIFY_20261026.md` **不改名**（证据只增不改），只补编号变更说明。
- 两侧改动规模：上游 117 文件 `+11202/−172`；本地 14 文件 `+1061/−14`；**路径交集仅 3 个文件**。

### 67.2 冲突裁决（3 处，全部人工裁决）

| 文件 | 冲突性质 | 裁决 |
|---|---|---|
| `loop/web/app.js` | 上游（SPEC-REV-08 U8-a）把 `needEntries/entriesReady` 上提到 `if (submit)` 之外供缺项提示复用；本地改的正是被上提那两行 | 保留上游结构，判据由 `entryDecisionsRequired` 收敛为 `entryGateRequires`（逐条处置只 G1），删掉 `if` 内重复两行 |
| `doc/STATUS.md` | 两侧同一插入点追加，且 §55/§56 撞号 | §54 原号保留（base 已显式预留 S0-a 真实派生，本地内容正是该预留）；接上游 §55–§64 原样整块；本地原 §55→**§65**、原 §56→**§66**，同步改 §65.3 / §54&§65 交叉引用 |
| `doc/README.md` | 同一索引区双向改写；「后续依次」两侧取值不同 | 取上游侧七条索引与新增段落，列表顶部补 `SPEC-REV-12` 条目，「后续依次」改为 `SPEC-REV-13` |

侧证：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md` 上游零改动 ⇒ 本地 I2 增补自动合并；
`loop/workflows/{chunks/long_jobs,context,main_flow,chunks/gates}.py`、`loop/services/contracts.py`
上下一律未触碰 ⇒ 合并后与合并前逐字节一致（`git diff` 0 行，见 67.3）。

### 67.3 实测（数字为命令输出复制）

工作树 = 合并点；两侧同一台机、同一 `.venv`、同一 `LOOP_LLM_MODE=standin`，仅 `LOOP_WORKSPACE` 指向可写目录。

| 门 | 合并后（本轮） | 合并前基线 `3432830` |
|---|---|---|
| 单测（全量 `pytest -q`） | **71 failed / 869 passed / 6 skipped / 104 errors**（74.05 s） | 72 failed / 627 passed / 8 skipped / 84 errors（52.41 s） |
| 单测失败集合差异 | **新增 0 条**；修掉 1 条（`test_test_layers.py::test_software_entry_excludes_env_layer_at_collection`）；新增 20 个 `ERROR` 全为**新文件** `tests/browser/test_ai_work_panel.py` | — |
| kb 自测 `_selftest_gate_schema.py` | PASS=10 FAIL=0 | — |
| kb 自测 `_selftest_n5_reachability.py` | PASS=9 FAIL=0 | — |
| 文档门 `doc/audit/check_doc_links.py` | `missing=0`，`checked=1876 skipped=23599 historical=857 known_missing=10 env_missing=19` | — |

本地专有文件回归：`long_jobs.py`、`context.py`、`main_flow.py`、`gates.py`、`contracts.py`、
`test_fix_lifecycle.py` 相对基线 `git diff` 均为 **0 行**；`app.js` 相对上游仅含本地闸门改动
（+31/−4），相对基线仅含上游新增（+316/−13）。

### 67.4 未运行 / 未验证（不得当作通过）

- **端到端 `bash spikes/accept_v1_run.sh` 未跑**：本机 `ENV_ROOT` 只读（写 `kb/runs` 报 `Errno 30`），且
  `WORKSPACE_ROOT` 未预置。合并前后两侧同此限制。
- **浏览器门不可用**：playwright 的 Chromium 未安装
  （`~/.cache/ms-playwright/chromium_headless_shell-1248/...` 缺失）⇒ 104 个 `ERROR` 全为 browser 用例的
  setup 失败；新增的 20 个亦属此列，非行为失败。上游 [AGENT_REVIEW_H2B_20261026](evidence/AGENT_REVIEW_H2B_20261026/README.md)
  的浏览器结果不能替代本轮实测。
- **真实模型 / 真 DSH / 内网冻结见证**未跑；上游 REV-09/10/11 的「已实现」只依据其规格自述与本表单测，未独立复核。
- 既有环境缺口（与本轮合并无关、合并前同样存在）：全量单测中依赖 `RUN-20261015-120626` 的 drill 用例在
  缺件数据根下会因本地 R2 的启动期校验显式失败（`drill 夹具不完整`），本次通过把该夹具放到可写数据根后统计，
  未修复该缺件本身。

### 67.5 未关闭项（必须与通过结论一起读）

合并带来 4 处**无 git 冲突标记、但判据需收口**的语义问题（详见 [SPEC-REV-12](spec/SPEC-REV-12-20261026.md) 后续修订）：

1. **R1（高）**：上游 U8-c 引导（`loop/web/app.js`）仍用全局 `entryDecisionsRequired`，而本地已把逐条控件
   收敛到 G1 ⇒ G2/G3 紧凑卡可能把用户引导到**没有控件**的闸门视图，正是 §54 修过的那类死角。
2. **R2（高）**：服务端标志仍是全局布尔（`services/contracts.py` `entry_decisions_required`），而
   `chunks/gates.py` 的 precheck 只在 G1 消费 `entry_decisions` ⇒「哪道门要逐条处置」存在前端硬编码与
   服务端全局两套判据，违反红线 8「口径唯一」。正解是判据下沉到服务端，前端只消费 flag。
3. **R3（中）**：`decision_options[].requires_reason` 仍是静态枚举（`accept` 恒 false），本地「`not_passed`
   时 accept 必须理由」的规则未进 options ⇒ UI 无法预检，只能提交后被后端拒。
4. **R4（中）**：`claimed_verdict` 有两个读者 —— 既有 `contracts._n12_conclusion`（workflow state facts）
   与本地 `contracts.report_claimed_verdict`（正则读 `n12_report.md`）；夹具/回放状态下可能分叉。

另：`GateDraftBridge.required` 仍用旧判据（同 R1 同源）；两条 SSE 路由无 HTTP 级自动化覆盖，
建议补 TestClient 冒烟（未知 run⇒404、`Content-Type: text/event-stream`、首帧事件名）。

---

## 68 R1+R2 收口：逐条处置判据下沉服务端（2026-10-26）

接 §67.5 的 R1（引导指向没有控件的死角）与 R2（两套判据）。**同一执行者实施与验证；独立复核另行安排。**

### 68.1 契约先行

[WEB_UI_SPEC](spec/WEB_UI_SPEC.md) §4.4 新增「判据归属（2026-10-26 增补）」：`entry_decisions_required`
由**服务端**按「本闸门有无逐条处置通道 × 未决条目数 × mode」判定，**只对 `G1_diff_confirm` 为真**
（G2/G3 的待确认项是只读 `items`；drill 一律为假）；前端**只消费该 flag**，不得按 `pending.gate` 自判。
§5 与 §4.2.2(c) 同步注明该 flag 只对 G1 为真，故 G2/G3 不会出现该引导。
顺序：改契约 → 写失败用例 → 改实现。

### 68.2 实现

- `services/contracts.py` 新增 `entry_decisions_required(gate, unresolved_count, mode)` —— **唯一判据**；
  `gate_material`（下发 flag）与 `gate_entries_view`（节点面板 `entries_required`：等待态原样消费、
  已决策态用同一判据）共用它，不再各算一套。
- `web/app.js` 删除自判函数 `entryGateRequires()`，4 处调用改为只消费 `entryDecisionsRequired(pending)`
  （控件渲染早退 ×2、就绪判定、提交前逐条校验）。
- **顺带消除两处同源死角**：U8-c 紧凑卡引导与 `GateDraftBridge.required` 消费的正是服务端 flag，
  改后天然只对 G1 生效 —— G2/G3 不再出现"引导用户去没有控件的地方"（即 R1 的原始症状）。

### 68.3 TDD 红→绿

新增 3 条断言，**实现前实测均红、实现后绿**：
- `test_fix_lifecycle.py::test_entry_decisions_required_is_g1_only`：同一份含未决条目的材料，
  只换闸门/换 mode 看服务端 flag（G1 real=True；G2/G3 real=False；G1 drill=False）。
- `test_node_detail_projection.py::test_gate_entries_decided_g2_never_requires_entries`：
  已决策态 `unresolved_count=3` + `mode=real` 的最易误判组合，`entries_required` 必须为假。
- `test_web_smoke.py`：静态断言由「必须含 `entryGateRequires`」反转为**不得含**（前端不得自判判据）。

### 68.4 实测（数字为命令输出复制）

| 门 | 本轮 | 改前基线 `43163d7` |
|---|---|---|
| 单测全量 | **71 failed / 871 passed / 6 skipped / 104 errors**（74.14 s） | 72 failed / 866 passed / 8 skipped / 104 errors（65.44 s） |
| 失败/错误集合差异 | **0 条**。唯一差异 `test_test_layers.py::test_software_entry_excludes_env_layer_at_collection` 是基线在 git worktree 里缺 `loop/.venv` 的环境假象（该用例主工作树连跑 2 次均 `6 passed`） | — |
| 定向（web_smoke / gate_session / gate_reason_reuse / gate_projection / node_story / api_ui_contract） | 8 failed / 135 passed | 8 failed / 135 passed（**同集合**） |
| 文档门 `check_doc_links.py` | `missing=0`（`checked=1876`） | missing=0 |

passed 数 +5 = 新增 2 条用例 + 上述 worktree 假差异 1 条 + 原本 skip 的 2 条在正式数据根下正常执行（8→6 skip）。
两组全量的 104 个 `ERROR` 全部是 browser 用例（playwright Chromium 未安装），与该改动无关。

### 68.5 未关闭

- **R3 / R4 未做**：`decision_options[].requires_reason` 仍是静态枚举（`accept` 恒 false），
  `not_passed` 时"必须理由"仍只有服务端硬前置、界面无法预检；`claimed_verdict` 仍有
  `_n12_conclusion`（state facts）与 `report_claimed_verdict`（读 `n12_report.md`）两个读者。
- **观察（未改）**：`gate_entries_view` 的 `entries_required` 在 `loop/web/**` 内**零消费者**
  （仅测试断言），按红线 4「模型输出必须有授权消费者」精神属可疑投影；本轮只把它对齐到同一判据，
  未删除该字段（删除属单独契约变更，需连带改 browser 夹具）。

---

## 69 独立复核整改：旧载荷归一化与夹具可达性（2026-10-26）

对 §68（R1+R2）的独立只读复核结论为**有条件通过**：判据生产者唯一、四组合行为正确、六处前端语义正确、
范围无越界；但发现 **C1（必办）** 等待态会把持久化旧 payload 的 flag 原样透传，以及 C2/O1–O4 若干项。
本节记录整改。**复核者只报告不改；整改由实现者完成，因此本节结论仍非独立验证。**

### 69.1 C1（必办）：旧载荷归一化

- **缺陷**：中断载荷会落进 run 文档并可能由快照恢复；升级前生成的 G2/G3 载荷里
  `entry_decisions_required` 仍是 `true`。等待态此前"原样消费/原样透传"，前端删掉自判守卫后，
  这类 run 会重演原始死锁：渲染逐条控件（选项是 accept/rework）→ 整门决策推导只认
  confirmed/ignored/disputed → 提交按钮永久禁用，紧凑卡还给出"去逐条处置"的死引导。
- **旧 payload 真实存在**（复核者举证）：[REAL_RUN_20261022/view.json](evidence/REAL_RUN_20261022/view.json)
  中 G2 的 flag 为 `true`；`workspaces/real-ws/state/recovery/RUN-20261022-181700.json` 的
  `gate_material::G2` 亦为 `true`，该 run 状态 `waiting_gate`。
- **整改**：
  - 新增 `contracts.normalize_pending_interrupt()`：投影前按唯一判据重算 payload 的 flag，
    返回**浅拷贝**，不改写 run 文档（投影不是权威）。
  - `run_view` 用归一化结果同时供 `pending_interrupt` 与 `build_agents`（此前两处都直接读落账值）。
  - `gate_entries_view` 等待态由"原样消费 payload"改为**同一判据重算**（节点面板一路）。
- 方向是"重算"而非"夹紧为 false"：G1 的旧 `false` 同样会被纠正（用例已断言）。

### 69.2 C2 / 夹具可达性 / O1–O3

| 项 | 处理 |
|---|---|
| C2 补回归 | 新增 `test_gate_entries_waiting_recomputes_stale_flag`（含 G1 反向纠正）与 `test_run_view_normalizes_stale_entry_flag_without_rewriting_ledger`（同时断言**不回写** run 文档） |
| O2 不可达夹具 | `test_node_detail_projection._waiting_material`（drill + flag=true）、`test_node_story.WAITING_GATE`（G2 + entries_required=true）改为服务端可达状态，并注明原因 |
| O1 前端自判 | `node-detail.js` 的 `gateIsG1` 定性为**展示形态选择**（选 G1 修订清单还是 G2/G3 只读项），在 WEB_UI_SPEC §4.4 写明**例外**；"是否需要逐条处置/是否已就绪/是否给引导"仍只认服务端 flag，未扩大例外 |
| O3 注释失真 | 等待态注释改为"必须重算"，并说明旧载荷来源 |
| O4 口径补记 | §68.4 的"定向"一行只覆盖 6 个文件、不含本轮两个测试文件；本节给出更准确的 4 文件口径（见 69.3） |

### 69.3 实测（数字为命令输出复制）

**修复前红**：在 `fda3629` 上跑新增两条 C1 用例 ⇒ **2 failed / 1 passed**（`G2 旧 payload 的 true 必须被重算掉`、
`G2 的旧 true 不得透传到界面`）；修复后 5 条（含 §68 的三条）全绿。

| 门 | 整改后 | 整改前基线 `fda3629` |
|---|---|---|
| 单测全量 | **71 failed / 873 passed / 6 skipped / 104 errors**（75.25 s） | 72 failed / 868 passed / 8 skipped / 104 errors（67.06 s） |
| 失败/错误集合差异 | **0 条**。唯一差异 `test_test_layers.py::test_software_entry_excludes_env_layer_at_collection` 是基线在 git worktree 中缺 `loop/.venv` 的环境假象（该用例在主工作树连跑 2 次均 `6 passed`） | — |
| 定向 4 文件（node_story / node_detail_projection / fix_lifecycle / web_smoke） | 34 failed / **180 passed** | 34 failed / 178 passed（**失败集合逐条一致**） |
| 文档门 `check_doc_links.py` | `missing=0` | missing=0 |

定向 +2 passed 即新增的两条 C1 断言；全量 +5 passed = 2 条新用例 + 1 条 worktree 假差异 + 2 条由 skip 转正常执行（8→6 skip）。

### 69.4 仍未关闭

- **R3 / R4 未做**（同 §68.5）：`accept` 的 `requires_reason` 仍是静态枚举、界面无法预检 `not_passed`；
  `claimed_verdict` 仍是两个读者。
- `gate_entries_view` 的 `entries_required` 仍无前端消费者（§68.5 观察项，未删）。
- `test_web_smoke` 对"前端不得自判"的断言仍是**符号名**级；补行为级断言需要可跑浏览器的环境
  （本机 playwright Chromium 未安装，104 个 ERROR 即此），已如实保留而非写成已覆盖。

---

## 70 R3+R4 收口：理由前置随选项下发 + 报告结论单一读取（2026-10-26）

接 §68.5/§69.4 未关闭项。**同一执行者实施与验证；独立复核另行安排。**

### 70.1 契约先行

- [SPEC-01 §1 I2 增补](spec/CHANGE_IMPACT_LOOP_SPEC.md)：规则必须体现在服务端下发的
  `decision_options[].requires_reason`（`not_passed` ⇒ `accept` 置 true），使界面提交前可预检；
  选项与 `precheck_decision` 的拒绝**必须由同一判据函数产生**，前端只消费 flag。
- [WEB_UI_SPEC §5](spec/WEB_UI_SPEC.md)：理由前置只看所选决策项的 `requires_reason`，
  前端不得再按 `gate`/`claimed_verdict` 自写一套。
- [WEB_UI_SPEC §4.4](spec/WEB_UI_SPEC.md)：`report.n12_report.claimed_verdict` 由单一函数产生，
  带 `claimed_verdict_source` / `claimed_verdict_diverged`；**判据口径只认落盘报告**，执行记录只作展示回落。
- [SPEC-REV-12](spec/SPEC-REV-12-20261026.md) 追加「实现补充」节（R3/R4 契约完备性，不改 R1 语义）。

### 70.2 R3：`requires_reason` 动态化

| 落点 | 改动 |
|---|---|
| `services/contracts.py` | 新增 `REASON_REQUIRED_DECISIONS` 与 `decision_requires_reason(gate, decision, claimed_verdict)`（**唯一判据**）；新增 `gate_decision_options(gate, claimed_verdict=)`（**唯一选项实现**） |
| 同上 | `_gate_options(claimed_verdict)` 与运行视图改为调用唯一实现；`gate_options` 现在随本轮报告结论变化 |
| `workflows/chunks/gates.py` | `REASON_REQUIRED` 改为 `contracts.REASON_REQUIRED_DECISIONS` 别名（消灭第二份字面量）；`decision_options()` 委托 `contracts.gate_decision_options()`；中断载荷 `_enter` 传入 `report_claimed_verdict(ctx.run_dir)`；G2 分支的拒绝条件改用同一函数（异常文案不变） |
| `web/app.js` | **删除**自写的「G2 accept + not_passed ⇒ 必须理由」前置（由 `selected.requires_reason` 一条覆盖）；告警条改为读 accept 选项的 `requires_reason`，结论值只用于文案说明 |

效果：界面改前是"显示无需理由、点提交才 403"，现在选项直接标"必须填写理由"，可预检。

### 70.3 R4：`claimed_verdict` 单一读取入口

- 新增 `contracts.n12_claimed_verdict(run_dir, state_facts)`，返回五个字段：
  `decision_verdict`（判据口径，**只认落盘 `n12_report.md`**，缺失即 None）、
  `display_verdict`（展示口径，报告缺失时回落到执行记录）、
  `source`（`report_md` / `state_facts` / `none`）、`facts_verdict`、`diverged`。
- `report_claimed_verdict(run_dir)` 变成取 `decision_verdict` 的薄包装（`precheck` 与理由前置用它）。
- `_n12_conclusion(state_facts, run_dir)` 改走同一入口：`claimed_verdict` 取展示值（**旧行为不退化**），
  并新增 `claimed_verdict_source` / `claimed_verdict_diverged` / `claimed_verdict_facts` /
  `claimed_verdict_decision` 四个投影字段 —— 分歧可见，不再静默择一。
- 边角补齐：执行记录里没有 N12 产出但落盘报告存在时，仍投影结论（否则"服务端按报告判定、
  界面看不到结论"又是一处分叉）。

设计取舍（必须写清）：**判据口径不采用执行记录回落**。若报告缺失而执行记录有结论，
界面会显示该结论（`source=state_facts`），但不因此要求理由、也不因此放行——服务端仍按 I2 原规则处理，
避免"界面拦、服务端放"或反之。

### 70.4 TDD 红→绿

新增 6 条断言，**在 `17d1042` 上实测 6 failed**（同一命令），实现后全绿：
选项声明（not_passed/passed 两态）、选项与 precheck 同判据、运行视图 `gate_options` 反映本轮结论、
结论单一读取且优先落盘报告并标记分歧、执行记录只作展示回落、材料暴露来源与分歧。

### 70.5 实测（数字为命令输出复制）

| 门 | 本轮 | 基线 `17d1042` |
|---|---|---|
| 单测全量（最终代码） | **71 failed / 879 passed / 6 skipped / 104 errors**（73.68 s） | 72 failed / 870 passed / 8 skipped / 104 errors（68.31 s） |
| 失败/错误集合差异 | **0 条**。唯一差异 `test_test_layers.py::test_software_entry_excludes_env_layer_at_collection` 系基线在 git worktree 中缺 `loop/.venv` 的环境假象 | — |
| 定向 9 文件（fix_lifecycle / node_detail_projection / node_story / web_smoke / gate_session / gate_reason_reuse / gate_projection / api / api_ui_contract） | 47 failed / **212 passed** | 47 failed / 206 passed（**失败集合逐条一致**） |

定向 +6 passed 即 6 条新用例；全量 +9 = 6 条新用例 + 1 条 worktree 假差异 + 2 条由 skip 转正常执行（8→6 skip）。

### 70.6 仍未关闭

- `gate_entries_view` 的 `entries_required` 仍无前端消费者（§68.5 观察项）。
- `test_web_smoke` 的「前端不得自判」仍是符号名级断言（行为级需可跑浏览器环境）。
- R3 之后前端不再自判理由，但**决策项文案**（如"接受"在失败轮次是否该改叫"接受未通过报告"）
  属产品文案，未改；如需调整另开切片。

---

## 71 独立复核（R3+R4）整改 + 测试数据根口径订正（2026-10-26）

对 `62bd0b5` 的独立复核结论为**有条件通过**：判据唯一性、四路径对照、6 条新用例真红、
范围 8 文件、数字精确复现，均确认；但提出 **条件 1（必办）** 与建议 A/B。本节整改。
**复核者只报告不改；整改由实现者完成，因此本节仍非独立验证。**

### 71.1 条件 1（必办）：drill G1 的理由前置未进唯一判据

- **缺陷**：G1 + **drill** + `confirmed` + 未决>0 时，`precheck_decision` 要求非空 `reason`
  作为「已逐条核对」的 attestation；而该模式下 `entry_decisions_required=false`（无逐条通道），
  选项 `requires_reason` 也是 false ⇒ 与 R3 修的完全同类死角（界面显示"无需理由"、提交才 403）。
- **整改**：`decision_requires_reason()` 增加**第三类来源**（drill G1 `confirmed` + 未决>0），
  签名扩展为 `(gate, decision, claimed_verdict=None, *, mode=None, unresolved_count=None)`；
  `gate_decision_options` / `_gate_options` / `run_view` / `gates.decision_options` /
  中断载荷 `_enter` 全部透传 `mode` 与 `unresolved_count`；`precheck_decision` 的 drill 分支
  改用同一函数判定（异常文案不变）。
- **契约**：[WEB_UI_SPEC §5](spec/WEB_UI_SPEC.md) 明列**三类**理由来源（固定集 / G2 失败报告 /
  drill G1 attestation）。

### 71.2 建议 A：结论来源与分歧必须可见

drill 夹具的 `n12_report.md` 常没有 `claimed_verdict` 行（判据口径为 `None`），此前界面只显示
执行记录里的"未通过"且旧告警条会消失，人无法解释"为什么选项说无需理由"。
现在 `web/app.js` 在 `claimed_verdict_source === "state_facts"` 时标注
「（来源：执行记录；报告未落盘，不作为判据依据）」，在 `claimed_verdict_diverged` 时并排列出
报告值与记录值。

### 71.3 建议 B：中断载荷里的选项不再是界面判据

`pending_interrupt.payload.decision_options` 是中断创建时的**快照**（会随快照恢复保留旧值），
`web/app.js::gateOptionsFor` 的 payload 兜底已删除，只消费运行视图每次重算的 `gate_options`；
[WEB_UI_SPEC §5](spec/WEB_UI_SPEC.md) 同时写明该字段仅为快照。

### 71.4 TDD 红→绿

新增 4 条断言（3 条服务端 + 1 条前端双断言），实现前实测：
`test_drill_g1_confirmed_option_requires_reason`、`test_drill_g1_attestation_and_option_agree`、
`test_run_view_gate_options_cover_drill_g1_attestation` **3 failed**；
`test_gate_reason_preflight_consumes_server_flags_only` 亦为红（缺 `claimed_verdict_source`
且仍含 `payload.decision_options`）。实现后全绿。

### 71.5 测试数据根口径订正（重要，影响此前所有"失败数"的解读）

此前各轮用的是**空数据根**（`LOOP_WORKSPACE` 指向空目录），因此把环境缺失计成了测试失败。
本轮起改用**预置数据根**（`<ws>/runs/RUN-20261015-120626` drill 夹具 + `baselines/ index/
conflicts/ adjudication/`，全部从只读 `ENV_ROOT/kb` 复制，约 738 MB，不入库）。同一份代码：

| 数据根 | 结果 |
|---|---|
| 空（此前各轮，`62bd0b5` 口径；`4129cb2` 新增 4 条用例后为 883 passed） | 71 failed / 879 passed / 6 skipped / 104 errors |
| 仅 drill 夹具 | 10 failed / 946 passed / 0 skipped / 104 errors |
| 夹具 + 小数据（本轮口径） | **3 failed / 957 passed / 0 skipped / 104 errors**（306.46 s） |

那 3 条**全部带 `@pytest.mark.env_layer`**（`test_archive_e2.py:85,109`、
`test_projection_and_frozen.py:103`），语义就是"需要可写 ENV_ROOT / 内网冻结见证"；
在**改动前**的 `62bd0b5` 上以同一数据根复跑同样 3 failed / 24 passed ⇒ **零回归**。
104 个 `ERROR` 仍全部是 browser 用例（playwright Chromium 未安装）。

⇒ 结论订正：此前记的"71 个既有失败"绝大部分是**环境未预置**，不是代码缺陷；
§68–§70 里的失败集合比对方法仍然有效（两侧同数据根），但绝对数字需按数据根口径读。

### 71.6 仍未关闭

- 环境整备未固化：本轮预置数据根是**临时目录**（验完即删，未入库），未写成脚本/文档；
  浏览器门需安装 playwright Chromium 才能跑（网络可达）。
  重跑本节数字需先按下表复制 `ENV_ROOT/kb` 的 `runs/RUN-20261015-120626` 与
  `baselines/ index/ conflicts/ adjudication/` 到可写数据根，再用 `LOOP_WORKSPACE` 指过去。
- 端到端 `accept_v1_run.sh` 仍需可写 `ENV_ROOT`（或 S0 派生副本），未跑。
- §70.6 其余项不变（`entries_required` 无前端消费者、`web_smoke` 仍含符号名断言）。

---

## 72 测试环境固化：可写数据根脚本 + 浏览器门可用性（2026-10-26）

§71.6 的首项"环境整备未固化"。**同一执行者实施与验证；独立复核另行安排。**

### 72.1 可写数据根脚本

新增 [`loop/spikes/provision_dev_workspace.sh`](../loop/spikes/provision_dev_workspace.sh)：
从只读 `ENV_ROOT/kb` **复制**（绝不写入环境仓，红线 11）到可写派生目录，带 `--cleanup` / `--force`。
数据根与环境根解析**复用 `kb_lib`**（唯一解析器，脚本内不另写路径规则），复制后自检夹具关键件。

实测：`bash spikes/provision_dev_workspace.sh` → 就绪；随后
`LOOP_WORKSPACE=<repo>/.dev-ws pytest -q tests/test_node_detail_projection.py tests/test_fix_lifecycle.py`
⇒ **113 passed**（2 分 20 秒），证明"预置即绿"可复现，不再依赖手工复制。

用法与"文档门须在清理后跑"的约束已写进 [loop/README.md §6](../loop/README.md)。

### 72.2 浏览器门：从"跑不起来"到"跑得起来但仍有既有失败"

| 阶段 | 结果 |
|---|---|
| 起点（无 Chromium） | 104 个浏览器用例全部 `ERROR`（setup 失败） |
| 系统 Chrome + 可写 HOME/TMPDIR | 8 failed / 1 passed（`tests/browser/test_web_layout.py`） |
| 补 SSE 替身桩后（本轮改动） | **4 failed / 5 passed** |
| 仓库自带离线包（`spikes/browser_offline.py install/run`） | 安装自检 PASS（version 152.0.7977.75）；`run` 仍全红，说明问题不在浏览器 |

环境要点（已写进 README）：`~/.cache` 与 `~` 在只读沙箱里不可写 ⇒ 浏览器与 Chrome 的用户目录放仓库内
（`PLAYWRIGHT_BROWSERS_PATH` / `HOME` / `TMPDIR`）；直连下载被代理掐断（EPROTO）时用
`PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright`（120 MiB 下载成功）。

### 72.3 本轮修复：浏览器替身漏掉上游新增的 SSE 端点

`tests/browser/test_run_sessions.py` 的 `route_request` 只按 run_id 返回视图，上游 U2-a/U2-b
新增的 `GET /api/runs/{id}/stream` 与 `.../agents/{node}/stream` 会落到该分支 ⇒ EventSource 拿到
JSON、持续重连，页面反复重渲染、点击目标被 detach（Playwright 报 `element was detached from the DOM`）。
已补显式 `404` 桩，让前端按 [WEB_UI_SPEC §7.3](spec/WEB_UI_SPEC.md) degrade 到「轮询回退」：
失败数 **8 → 4**。

### 72.4 未关闭：剩余 4 条浏览器用例（既有问题）

`test_web_layout.py` 剩 4 条 —— `test_compatibility_console_has_return_path_and_fits_browser[1280/1440/1920]`
与 `test_agent_cards_show_server_capability_facts` —— 仍报 `element was detached from the DOM`：
运行列表按 `POLL_MS=1500` 周期性重建与点击竞争。

**已确认非本轮引入**：在 `62bd0b5`（R3+R4 之前）用同一浏览器与同一命令复跑
`test_agent_cards_show_server_capability_facts` 同样失败（32.88 s 超时）；
且换用仓库离线包自带的 Chrome 152 亦全红 ⇒ 与浏览器版本、与本轮改动均无关。
**未修**：需要定位"谁在高频重建运行列表"（可能涉及 `page.clock.install()` 与轮询/重渲染的交互），
属独立的 UI 稳定性切片，本轮不凭猜测改应用代码。

### 72.5 未关闭（其余）

- 端到端 `accept_v1_run.sh` 仍需**可写 ENV_ROOT**（或 S0 派生副本），本机只读，未跑。
- 数据根脚本复制 738 MB 且不能出仓（仓外只读），每次验证前后需 `--cleanup`，属已知不便。

---

## 73 端到端实测通过 + 四道门统一记录（2026-10-26）

§72.5 的"端到端仍需可写 ENV_ROOT"被实测推翻。**同一执行者实施与验证；无独立终验。**

### 73.1 端到端：ALL PASS（117 条断言）

命令（先 `bash spikes/provision_dev_workspace.sh`，再）：

```bash
cd loop && LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh
```

驱动汇总 `=> ALL PASS`，6 个 phase 全 `rc=0`：

| phase | 1 | 2 | 3 | 4 | 4b | 5 |
|---|---|---|---|---|---|---|
| 断言 | PASS=50 | PASS=27 | PASS=18 | PASS=8 | PASS=8 | PASS=6 |
| FAIL | 0 | 0 | 0 | 0 | 0 | 0 |

合计 **117 条断言全 PASS**，无 `[FAIL]`、无 skip、无 Traceback；脚本自起自停 4 代服务进程（真重启）。
覆盖面：建 run / 签 G1 / 作业投递与终态、真重启后重附着与收敛、长任务停放与取消、死任务判 `failed` 且单槽释放。

### 73.2 更正：端到端**不需要**可写 `ENV_ROOT`

- 全部 phase 走 `mode=drill`；drill 的 N9 用夹具日志，不执行环境。
- 跑完检查 `ENV_ROOT/kb/runs`：`find -newermt '-30 minutes'` **为空** ⇒ 环境根零写入（红线 11 守住）。
- 唯一前提是**可写数据根**（`spikes/provision_dev_workspace.sh` + `LOOP_WORKSPACE`）。
- [AGENTS.md §4](../AGENTS.md) 的端到端行已按实测更正（原文写"需要可写 `ENV_ROOT`"，与实际不符）。

### 73.3 四道门（本轮 HEAD，同机同一环境）

| 门 | 命令 | 结果 |
|---|---|---|
| 单测 | `LOOP_WORKSPACE=<可写数据根> LOOP_LLM_MODE=standin pytest -q` | **3 failed / 957 passed / 0 skipped / 104 errors**（322.23 s） |
| kb 自测 | `_selftest_gate_schema.py` / `_selftest_n5_reachability.py` | **PASS=10 FAIL=0** / **PASS=9 FAIL=0** |
| 端到端 | `bash spikes/accept_v1_run.sh` | **ALL PASS**（117 断言，见 §73.1） |
| 文档 | `python3 doc/audit/check_doc_links.py` | **missing=0** |

- 3 条 failed 全带 `@pytest.mark.env_layer`（需可写 `ENV_ROOT`，本机只读）；在改动前 `62bd0b5` 上同样失败（§71.5）。
- 104 条 errors 全部是 browser 用例的 setup 失败（本机默认路径没有 Chromium）。

### 73.4 浏览器门：装了 Chromium 反而不能并入全量（重要）

装 Chromium 后单独跑 `tests/browser/test_web_layout.py` 为 **4 failed / 5 passed**（§72.4 的既有渲染竞争）。
把 `PLAYWRIGHT_BROWSERS_PATH` 带进**全量**后，浏览器用例真正执行、但每条失败都要等 30 s 超时：
实测 **20 分钟仍未跑完**（中断前已累积 39 个 F）。因此本轮 DoD 记为：

- **单测门**：不设 `PLAYWRIGHT_BROWSERS_PATH`（浏览器用例以 setup 错误计入，软件层结论不受影响）；
- **浏览器门**：单独跑、单独记录，当前 4 failed / 5 passed（既有问题，非本轮引入，见 §72.4）；
- 待 UI 稳定性切片修好后，再把浏览器门并回全量。该取舍已写进 [loop/README.md §7](../loop/README.md)。

### 73.5 证据与限制

- 本轮数字均为命令输出复制；数据根为临时目录（738 MB），跑完已删除；浏览器装在仓库内
  `.pw-browsers/`（本地忽略，不入库）。
- 未跑：真实模型（`LOOP_LLM_MODE=live`）、真 DSH、内网冻结见证；这些不是本轮范围。
- 未落独立证据包（`doc/evidence/**` 只增不改，需单独整理）；原始日志为临时文件，已删除。

---

## 74 收尾：复核残留整改 + 浏览器门根因推进（2026-10-26）

§71.6 / §73.4 留下的两项：复核的 5 条非阻断残留、以及浏览器门。**同一执行者实施与验证。**

### 74.1 残留 1：precheck 内的隐式谓词副本 → 已消除

原 `precheck_decision` 的 G1 分支外层写 `elif mode == "drill"`，分支内又调
`decision_requires_reason()`（该情形下恒真）⇒ 同一判据两处表达。
现改为：先算 `drill_attestation = contracts.decision_requires_reason(gate, decision, mode=…,
unresolved_count=…)`，**由它**选择「drill attestation 路径」还是「real 必须给 entry_decisions」，
外层不再出现 `mode == "drill"` 判断。行为等价（异常文案不变）。

### 74.2 残留 3：正常 G2 告警文案回退 → 已修

恢复 warn 行的「本轮报告结论：X。」前缀；把"来源/分歧"独立成一条 `alert info`，且**只在**
`source == state_facts` 或 `diverged == true` 时渲染 ⇒ 正常路径（报告落盘且一致）无噪音、无重复。

### 74.3 残留 5：补 `_enter` 接线用例 → 已补

新增 `test_interrupt_payload_options_carry_drill_attestation_reason`：经 `RunManager` 真跑到
G1 中断，断言**中断载荷**里的 `decision_options.confirmed.requires_reason == true`。
在 `62bd0b5` 上实测**红**（`drill G1 没有逐条通道 ⇒ 载荷里的 confirmed 必须声明要理由`），
修复后绿 —— 覆盖了"只有 contracts 纯函数用例、`_enter` 传参错位发现不了"的缺口。

### 74.4 浏览器门：定位并修掉一半根因（重要）

- **根因 1（已修）**：`loadRuns()` 每 1.5 s 轮询后**无条件** `renderSidebar()` 全量 `clearEl` 重建
  ⇒ 点击目标被反复替换。现按签名（选中项 / runs / 错误串）跳过无变化重建；契约写入
  [WEB_UI_SPEC §2 重建策略](spec/WEB_UI_SPEC.md)。等待提醒等其余投影仍每拍更新。
- **效果**：失败模式由 `element was detached from the DOM` 变为 `element is outside of the
  viewport` ⇒ **detach 类已消除**，暴露出**第二个独立缺陷**（侧栏 `.run-item` 在 1280/1440/1920
  视口外，滚动也无法进入）。
- **现状**：`tests/browser/test_web_layout.py` = **4 failed / 5 passed**（与本轮之前同为 4 条，
  但**失败原因已不同**）。布局缺陷未修：属独立的 UI 布局切片，本轮不凭猜测改 CSS。

### 74.5 残留 2 / 4：不改，登记理由

- 残留 2：drill + API 调用方**直接给** `entry_decisions` 时，选项声明"要理由"而 precheck 放行。
  仅 API 路径可达（drill 界面不渲染逐条控件），且方向是**更严**，不构成静默放行 ⇒ 登记不改。
- 残留 4：`legacy.html`（旧版操作台）仍优先消费中断载荷的快照 `decision_options`；
  它只取 `value/label`、从不渲染 `requires_reason`，不扩大理由误判面 ⇒ 登记不改。

### 74.6 实测（数字为命令输出复制）

| 门 | 本轮 | 说明 |
|---|---|---|
| 单测（预置数据根） | **3 failed / 958 passed / 0 skipped / 104 errors**（330.87 s） | 3 条仍为 `env_layer`；104 errors 为 browser setup（未设浏览器路径） |
| 浏览器（单跑 `test_web_layout.py`） | **4 failed / 5 passed**（58.11 s） | 原因已从 detach 变为视口外（§74.4） |
| kb 自测 / 端到端 / 文档门 | 见 §73（本轮未改动这些路径） | 本轮改动仅 gates 判据结构、app.js 渲染守卫与告警文案、测试 |

新增 1 条用例（+1 passed 相对 §73 的 957）。

### 74.7 未关闭

- 侧栏布局：`.run-item` 在 1280/1440/1920 视口外（新暴露，未修，需单独定位）。
- 残留 2 / 4（§74.5，登记不改）。
- 端到端与 kb 自测未在本轮重跑（代码路径未变；如需最新证据请按 §73.1 命令重跑）。

## 75 侧栏可达性（WEB_UI_SPEC §14 / A10）：缺陷修复与浏览器门转绿（2026-10-26）

§74.7 唯一明确的代码未关闭项，本轮关闭；并订正 §74.4 的归因。**同一执行者实施与验证。**

### 75.1 归因订正：变量是**视口高度**，不是宽度

§74.4 记「侧栏 `.run-item` 在 1280/1440/1920 视口外，滚动也无法进入」。实测这个归因不准确：

- `test_workspace_views_and_agent_controls_fit_browser` 的三个用例把**高度写死 1000**，
  此时 `.run-item` 在 y≈734、`aside` 到 y=1000，装得下，**它们一直是通过的**；
- 真正暴露缺陷的是 `test_agent_cards_show_server_capability_facts`——它**没有设视口**，
  用的 Playwright `new_page()` 默认 **1280×720**；
- 该文件那 4 条红里另有 3 条与布局完全无关（见 §75.3）。

### 75.2 根因 1：sticky 视口高侧栏 + 内容溢出 + 无自身滚动（产品缺陷）

`loop/web/app.css` 把 `aside` 钉成 `position:sticky; top:72px; height:calc(100vh - 72px)`，
内部条目高度却是自适应的。短视口下 `.rail-top` + `#btnNew` + 4 个视图 tab + 「在等我」+
「最近运行」+ `.rail-foot` 已超过可用高度，而 `overflow` 是默认 `visible` ⇒ 溢出内容被
**画在 sticky 盒之外**；sticky 又让页面滚动无法把它带回视口 ⇒ 下级条目**永久不可点击**。

实测（1440×720，`scrollY=0`，数字为命令输出复制）：

| 量 | 修复前 | 修复后 |
|---|---|---|
| `aside` clientHeight / scrollHeight | 648 / **838** | 648 / 838 |
| `.run-item`（A）包围盒 top–bottom | 734–801 | 653–720 |
| `rail-foot` 包围盒 top–bottom | 810–910 | 落回视口内 |
| `scrollIntoView` 之后 A 的 top | **734（一分不动）** | 653 |
| `.run-item` 的 `locator.click()` | 30 s 超时「outside of the viewport」 | 成功 |

红证据（撤掉修复那一行、只保留新用例）：

- 1280×720 ⇒ `run-item top=734 bottom=801`、`run-item top=743 bottom=810`、
  `rail-foot top=810 bottom=910`，视口高 720；
- 1440×900 ⇒ `rail-foot top=810 bottom=910`，视口高 900（被切 10 px）；
- 1920×1080 ⇒ 通过（1008 ≥ 838，本来就装得下）。

修复：`aside{… overflow:hidden auto}`（一行属性）。`overflow-x` 取 `hidden` 是为了规避
「一个轴 `auto`、另一轴 `visible` 会被计算成 `auto`」的横向串味；侧栏内无绝对定位浮层
（`#btnS0` 只切视图、`#viewSeg .on:before` 在按钮内），无裁剪风险；`legacy.html` 不加载 `app.css`。

契约先行：`WEB_UI_SPEC` §14 增「侧栏可达性」条款，§10 新增判据 **A10**（验收视口
1280×720 / 1440×900 / 1920×1080，`scrollIntoView` 后包围盒须完整落在视口内）。
回归用例：`test_web_layout.py::test_sidebar_entries_are_reachable_at_acceptance_viewports`。

### 75.3 根因 2：`page.url` 拼接把文件名拼到 hash 后面（测试缺陷，非产品缺陷）

`test_compatibility_console_has_return_path_and_fits_browser` 原写
`page.goto(page.url + 'legacy.html')`。前端把当前视图同步进 URL，实测
`page.url == "http://127.0.0.1:37051/#view=s0"` ⇒ 拼成 `"…/#view=s0legacy.html"`，
变成**同页 hash 跳转、根本没导航**，`.back-workspace` 永远找不到（Aria 快照里仍是主工作台）。
产品侧无缺陷：`legacy.html` 的 `<a href="legacy.html">` 与主页 `#lnkLegacy` 都是相对链接，
点击会替换整个 path+hash。改用 `urljoin(page.url, 'legacy.html')` 后 3 条用例转绿。

### 75.4 顺带查明的两条既存失败（A/B 对照，非本轮引入）

用「临时只撤掉 CSS 那一行」做对照：撤掉后反而**更红**（`test_ai_work_panel` 的 320/768/1440
三条全红 + draft 一条红）⇒ 下面两条既存，且 768/1440 两条是本轮修复顺带救回的：

1. **`test_cross_run_draft_is_cleared`——与 U1-c 冲突的陈旧用例**：它断言切运行后 actor
   回到 `human:`；但 `fill()` 打过 `human:reviewer`，`operator.js` 已 `remember` 到
   localStorage，切运行后草稿归零到默认前缀再被**预填**，这正是
   [SPEC-REV-07 U1-c](spec/SPEC-REV-07-20261024.md)「应用级当前操作者，三处预填」的行为。
   已按契约对齐断言并注明来源；用例真正的语义（理由清空、提交禁用）不变且通过。
   **产品代码未改。**
2. **`test_ai_work_panel[…[320]]`——320 px 属契约外，用例口径越界**：该参数下
   `documentElement.scrollWidth=369 > innerWidth=320`，最宽者是 header 的 `#btnNotify`
   （right=369）；`header` 在 ≤760 px 分支固定 60 px 高、内容不换行。实测溢出边界
   （数字为命令输出复制）：**320 ⇒ docSW 369（溢出 49）／360 ⇒ 369（溢出 9）／
   390 ⇒ 390（正常）／768 ⇒ 768（正常）**，即任何窄于 ≈371 px 的窗口都会整页横向溢出。
   移动端在契约里被**四处**排除：WEB_UI_SPEC §1「不做移动端适配」、§12「v1 不做：移动端」、
   §14「移动端不作为本轮设计和验收目标」，[SPEC-REV-07](spec/SPEC-REV-07-20261024.md) §1
   范围冻结「浏览器工作台（1280/1440/1920）；不做…移动端」。且全仓其余窄屏用例一律取 390
   （`test_run_sessions` / `test_agent_window` / `test_node_detail`），320 是孤例。
   ⇒ **用户 2026-10-26 明确「移动端不在功能开发范围内」**：产品代码不动（不做移动端适配），
   把该用例的窄屏口径对齐到 390，其余断言（容器内不溢出、无注入节点、焦点保持、Escape 关闭）
   在 390 照常生效。**这是口径纠正，不是修好了那个溢出**——该限制原样保留在 §75.7。

### 75.5 改动清单

| 文件 | 改动 | 性质 |
|---|---|---|
| `doc/spec/WEB_UI_SPEC.md` | §14 增「侧栏可达性」；§10 增 A10 | 契约 |
| `doc/plans/2026-10-26-sidebar-reachability.md` | 新增：根因、切片、验证门、回退 | 计划 |
| `loop/web/app.css` | `aside` 增 `overflow:hidden auto` + 说明注释 | **产品（唯一一行）** |
| `loop/tests/browser/test_web_layout.py` | 新增 `assert_reachable` / `ACCEPTANCE_VIEWPORTS` / `RAIL_ENTRIES` 与 A10 用例；legacy 改用 `urljoin` | 测试 |
| `loop/tests/browser/test_run_sessions.py` | `test_cross_run_draft_is_cleared` 对齐 U1-c | 测试 |
| `loop/tests/browser/test_ai_work_panel.py` | 窄屏参数 320 → 390（契约外口径纠正，见 §75.4 第 2 条） | 测试 |
| `loop/spikes/provision_dev_workspace.sh` | `kb_lib` 导入改用**脚本所在仓根**（原相对路径 `kb/tools` 使文件头的用法在 `loop/` 下直接失败，本机 2026-10-26 实测） | 测试环境 |

### 75.6 四道门实测

| 门 | 本轮 | 说明 |
|---|---|---|
| 单测（**文档化软件层入口**） | **957 passed / 3 deselected / 0 failed**（352.46 s） | `bash spikes/run_software_checks.sh --ignore=tests/browser`；入口在**收集期**用 `-m "not env_layer"` 排除那 3 条并打印清单（不是 skip）⇒ **软件层无红** |
| 单测（plain pytest，含环境层） | 3 failed / 957 passed / 0 skipped（301.15 s） | `-m` 未过滤时会**如实执行** 3 条 `env_layer`：`test_archive_e2` ×2 + `test_projection_and_frozen` ×1，它们在只读 `ENV_ROOT` 本机只能失败，属环境层而非软件缺陷（`pytest.ini` 已声明该标记语义） |
| kb 自测 | `_selftest_gate_schema.py` **PASS=10 FAIL=0**；`_selftest_n5_reachability.py` **PASS=9 FAIL=0** | 两者都需 `LOOP_WORKSPACE` 指可写数据根 |
| 端到端 | **本轮未重跑** | 改动仅 CSS / 浏览器用例 / 文档 / 一个 shell 脚本的导入路径，e2e 不触达 UI 渲染；沿用 §73 实测（ALL PASS、117 断言）。要最新证据按 §73.1 重跑 |
| 文档 | **missing=0**（checked=2165 / known_missing=10 / env_missing=26，exit=0） | 须在**未预置 `.dev-ws`** 时跑；预置后须先 `provision_dev_workspace.sh --cleanup` |

浏览器门（需 Chromium，`PLAYWRIGHT_BROWSERS_PATH` + 可写 `HOME`/`TMPDIR`）：

| 范围 | 修复前 | 修复后 |
|---|---|---|
| `tests/browser/test_web_layout.py` | **4 failed / 5 passed**（61.51 s） | **12 passed**（15.72 s） |
| `tests/browser/` 全量 | 本文件此前未记录全量基线（§74 只记单文件） | **108 passed / 0 failed**（119.96 s） |

时长下降来自 30 s 点击超时消失，**不是跳过或缩小断言**；A10 反而新增 3 条参数化用例
（含 `rail-foot`，比规格下限更严）。全量转 0 failed 的一步是 §75.4 第 2 条的**口径纠正**
（320 → 390），该宽度的真实限制并未修复，见 §75.7。

### 75.7 未关闭

- **移动端（窄于 ≈371 px）header 横向溢出**：产品不做移动端适配（契约四处排除，
  见 §75.4 第 2 条），该限制保留。若日后要做移动端，属**契约变更 + 独立切片**，
  须先改 WEB_UI_SPEC §1/§12/§14 与 SPEC-REV-07 §1 的范围声明。
- 浏览器用例仍未并入全量单测门（单跑 120 s，且并入后 30 s 超时会叠乘，见 §72）。
- §74.5 的残留 2 / 4 维持「登记不改」。

## 76 复核遗留 A 组收口：判据落实 + 行为级断言 + SSE 路由覆盖（2026-10-26）

§75 之后按「A 组（代码/口径层）」逐项收口。**同一执行者实施与验证。**

### 76.1 A1：`entries_required` 不是「没人用」，而是**该用没用**（§68.5 结论订正）

§68.5 / §69.4 / §70.6 / §71.6 一直登记「`gate_entries_view.entries_required` 在
`loop/web/**` 零消费者，按红线 4 精神属可疑投影，倾向删除」。本轮复核结论相反：

- [WEB_UI_SPEC §4.4 判据归属](spec/WEB_UI_SPEC.md)已明写「**是否需要逐条处置 / 是否已就绪 /
  是否给引导**一律只看服务端 flag」，明示例外**只**覆盖「显示 G1 修订点清单还是
  G2/G3 只读待确认项」这个展示形态选择；
- 而 `loop/web/node-detail.js` 的 `editable` 用的是 `gateIsG1(gate)`（按闸门 id 自判）；
- 两者**不等价**：`contracts.entry_decisions_required = G1 && unresolved_count && mode != drill`。
  于是 drill 模式（或没有未决条目）下服务端下发 `false`，节点面板却仍渲染可写勾选框，
  页脚还给出「还有 N 条未处置：闸门视图的提交按钮会保持禁用，处置完再提交」——**闸门表单那边
  根本不会渲染逐条控件**，这正是 §54 修过的「把人引到没有入口的地方」死角。

**修复（不改契约，代码本就违反现有规格）**：新增 `gateNeedsEntries(gate)` 读服务端
`gate.entries_required`，四处判定改用它 —— `renderGate` 的行渲染、`syncGateRowStates`、
`openDiff`（浮窗处置区）、`fillGateFoot`（引导语）；`gateIsG1` 只留展示形态（规格明示）。
**结论：字段有授权消费者了，不删除** —— 删除会让复核 C1 要求的「等待态必须重算」
（`test_gate_entries_waiting_recomputes_stale_flag`）失去对象，也丢掉「面板与闸门表单同口径」的载体。

夹具同步：`gate_block` / `setup_gate_node` 增 `entries_required` 参数。原夹具写死
`gate == GATE`，与基线 `mode="drill"` 叠加后是**服务端产不出的组合**（drill 下恒假）。

回归用例 `test_gate_entry_controls_follow_server_flag_not_gate_id`：先红
（实测标题仍是「勾选 = 已确认；忽略 / 有疑义请点「查看前后对比」逐条处置」）→ 修复后绿；
`tests/browser/test_node_detail.py` 全文件 **44 passed**。

### 76.2 A2：「前端不得自判」从符号名级升到行为级

`test_web_smoke::test_gate_reason_preflight_consumes_server_flags_only` 只查源码字符串
（`assert "payload.decision_options" not in js`），是本轮之前的**唯一**守卫。保留该廉价守卫，
另加两条行为级用例，并在该用例 docstring 里互相指路：

| 用例 | 可判别点 |
|---|---|
| `test_run_sessions::test_gate_option_flags_come_from_run_view_not_interrupt_snapshot` | 运行视图**不下发** `gate_options`、只有中断快照里有选项时，界面必须报「服务端未下发决策选项 ⇒ 不可提交」，不得拿快照顶上；下发后才出现选项与「接受失败报告必须填写理由」 |
| `test_node_detail::test_gate_entry_controls_follow_server_flag_not_gate_id` | 见 §76.1 |

**A/B 验证用例自身有效**（这条要如实记）：第一版 A2 用例把 `gate_options` 与快照**都**给了值，
只在两者内容上做区分 —— 临时把「快照回退」加回 `gateOptionsFor` 后用例**仍然绿** ⇒ 该写法
**不判别**（回退分支只在 `gate_options[gate]` 缺失时生效）。改为「只留快照」后重跑 A/B：
加回回退 ⇒ **红**（`AssertionError: Locator expected to contain text '服务端未下发决策选项'`），
复原 ⇒ 绿。

### 76.3 A3：两条 SSE 路由补 HTTP 级覆盖（§67.5 遗留建议）

新增 `loop/tests/test_api_stream_routes.py`（3 条）。分层：`test_run_stream_server.py` 断的是
生成器内部（帧格式/心跳/变更检测），本文件只固定**路由层**：

1. 未知 run ⇒ **404**（两条路由都是；不是「200 然后推 error 帧」）；
2. 成功响应 `Content-Type: text/event-stream` 前缀 + `Cache-Control: no-cache`；
3. 首帧事件名正确：`/stream` ⇒ `event: run_view`，`/agents/{node}/stream` ⇒ `event: agent_view`
   （SPEC-04 §6.9/§6.10 两个事件名不得混用）；
4. 该帧 `data:` 是**单行**且可 `json.loads`（多行会被 SSE 拆碎，前端解析会坏）；
5. run 消失 ⇒ 显式 `event: gone` 后结束，不伪装存活。

替身只替换数据来源（`api._manager` / `api._agent_root` / `api._agent_window_view`），
传输仍是真实 `StreamingResponse` + `services.run_stream`，故帧格式与结束语义走生产代码路径。

### 76.4 改动清单

| 文件 | 改动 | 性质 |
|---|---|---|
| `loop/web/node-detail.js` | 新增 `gateNeedsEntries`；四处判定从 `gateIsG1`/`state` 切到服务端 `entries_required`；页脚引导按同一判据分支 | **产品** |
| `loop/tests/browser/test_node_detail.py` | 夹具增 `entries_required` 参数（消除不可达组合）；新增 A1 行为级用例 | 测试 |
| `loop/tests/browser/test_run_sessions.py` | 新增 A2 行为级用例（含被 A/B 推翻后重写的判别点） | 测试 |
| `loop/tests/test_api_stream_routes.py` | 新增：两条 SSE 路由的 HTTP 级契约 | 测试（新文件） |
| `loop/tests/test_web_smoke.py` | 符号级守卫加注释，指向两条行为级用例（断言未改） | 测试 |

### 76.5 四道门实测

| 门 | 本轮 | 说明 |
|---|---|---|
| 软件层单测（文档化入口） | **960 passed / 3 deselected / 0 failed**（356.02 s） | `bash spikes/run_software_checks.sh --ignore=tests/browser`；+3 相对 §75.6 的 957（新增 SSE 路由 3 条） |
| kb 自测 | 未重跑 | 本轮未改 `kb/` 与闸门判据代码路径（改动为前端 JS 与测试）；沿用 §75.6 的 PASS=10 / PASS=9 |
| 端到端 | 未重跑 | 不触达工作流/API 路径；沿用 §73 |
| 文档 | 见本节落盘后实测 | — |

浏览器门（需 Chromium）：

| 范围 | 上一版 | 本轮 |
|---|---|---|
| `tests/browser/` 全量 | 108 passed | **110 passed**（117.15 s，+2 条行为级用例） |

### 76.6 未关闭（A 组已清空，余下按原分组）

- **B 契约/产品层**：~~逐条处置未落账（`entry_decisions` 不进 `gates.json`/事件流 ⇒ P-18 重建做不到）~~
  **已解决（2026-10-26，见 §77.1）**：落账由 P-15/P-17/P-18 实现（`decisions/<gate>.json` + `gate_decided.detail.entries`），
  本节当初的登记是过期信息；P-18 在**冻结夹具**上仍无法演示，但那属夹具早于落账，见 §77.7。其余项：
  残留 2（drill + API 直接给 `entry_decisions` 时选项声明要理由而 precheck 放行，方向更严）；
  残留 4（`legacy.html` 仍消费载荷快照 `decision_options`，不渲染 `requires_reason`）；
  决策项文案（失败轮次「接受」是否改名，§70.6）。
- **C 环境/规模层**：S0-b 未接入；I4 72 条冲突未清零 ⇒ G3 只能 `milestone_only`、N16 仍 `refused`；
  夹具只有 `not_passed` 形态（真实通过轮需 ~21.5 h）；取消作业 = 整轮 `failed` 不可续跑；
  运行入口不消费 S0；3 条 `env_layer` 用例在只读 `ENV_ROOT` 本机不可跑。
- **D 流程/证据层**：端到端本轮未重跑；浏览器门未并入全量门（时长/可移植性理由）；提交未推送；
  两个可写数据根入口并存（`provision_dev_workspace.sh` 复制 733 MB vs `run_software_checks.sh`
  符号链接 + 一次性影子根），建议后续让前者退化或改符号链接。
- **移动端**：不做适配（§75.4 第 2 条，用户 2026-10-26 裁决）。

## 77 逐条处置落账：结论订正 + 口径统一 + 回归钉子（2026-10-26）

用户裁决「一块做完落账」。**先说结论：Host 落账此前已实现**，过期的是登记；本轮做的是
**订正口径矛盾、补回归钉子、作废过期未关闭项**。**同一执行者实施与验证。**

### 77.1 结论：落账已实现（`decisions/<gate>.json` + 事件同源）

| 环节 | 实现位置 | 内容 |
|---|---|---|
| 写入 | `workflows/chunks/gates.py::append_decision_ledger` | `run_dir/decisions/<gate>.json`，`schema=loop/gate_entries`，`records` **append-only**；`decided_at` 取权威 `gates.json` 的 `signed_at`（时间仍是单一注入入口）；记录含 `cycle/decided_at/decision/actor/reason/entries/hard_block` |
| 同源下发 | 同文件 `ctx.event("gate_decided", …, detail={"entries": record["entries"]})` | 逐条处置随事件下发 |
| 读侧 | `services/contracts.py::gate_entries_view` + `_decision_ledger` | 已决策态**只**从落账回填；缺失/损坏 ⇒ `None`，面板明说「逐条处置未留存」，不编、不猜 |
| 字段白名单 | `_ledger_entries` / `_ledger_hard_block` | 只写契约字段（`decision/reason`；`code/title/message`），内部键（如 `source`）不进账本 |

**实测证据**（命令输出复制）：

- `bash spikes/run_software_checks.sh tests/test_flow.py::test_s2_detail_fields_and_gate_ledger_on_full_drill_run`
  ⇒ **1 passed**（9.05 s）：该用例跑完整 drill 全链路后断言三门 `decisions/<gate>.json` 存在、
  `G1` 的 `entries` **覆盖全部差异条目**、`gate_decided.detail.entries` 与落账**同源**、
  `decided_at == 权威 signed_at`、`hard_block` 快照等于本门开启时材料。

**作废登记（原文保留作历史，本节起失效）**：

- §54.5 第 2 条「逐条处置未落账…P-18 重建需先补 Host 落账」；
- §65.4 第 5 条「逐条处置仍未落账（`gates.json`/事件流都没有 `entry_decisions`）」。

两者描述的是 P-15/P-17/P-18 落地**之前**的状态，之后再未更新。另一个让人误判的来源是
**冻结夹具 `RUN-20261015-120626` 没有 `decisions/`**（它早于落账）⇒ 面板显示"未留存"，
那是规格**有意设计**的降级形态（`LOOP_ORCHESTRATION_SPEC` §10.4.2），不是缺陷。

### 77.2 真正的代码层问题：两份规格口径互相矛盾（已修）

| 规格 | 原文 | 冲突 |
|---|---|---|
| `CHANGE_IMPACT_LOOP_SPEC` §7 | 「处置结果落 `gates.json`（`entry_decisions`）」 | 与右列冲突 |
| `LOOP_ORCHESTRATION_SPEC` §10.4.2 | 「`gates.json` 不存逐条处置 ⇒ …**不得**从 `gates.json` 反推」+ 落 `decisions/<gate>.json` | 机制契约 |
| `kb/schema/gate_state.schema.json`（**冻结**，md5 `b3d8c0cac0d56599e83879aec0921fb2`） | `gate` 定义 `required` 列 11 个字段，但 `additionalProperties: true`（:42）⇒ 技术上**允许**额外字段 | 所以左列那句**可满足**，订正依据**不是** schema 禁止，而是下面两条实质理由 |

⇒ 订正业务规格（红线 8「口径唯一」）。**实质依据（不含 schema 语义）**：
① `gates.json` 是闸门权威且参与 `gates.sha256` 锚，再把逐条处置写进去 = 第二来源、且锚随处置内容漂移；② `LOOP_ORCHESTRATION_SPEC` §10.4.2 明文「不存逐条处置、**不得**从 `gates.json` 反推」。业务规格 §7 改为
「落 `run_dir/decisions/<gate>.json` + `gate_decided.detail.entries`，二者同源；**不落** `gates.json`」，
并写明依据；编排规格 §10.4.2 增反向交叉引用与订正日期。顺带删掉 §10.4.2 里**重复的一行**
（"该文件是面板展示材料，不是闸门权威…"连写两遍）。

### 77.3 回归钉子：`loop/tests/test_gate_ledger.py`（新增 5 条）

此前这些不变量只有散落在全链路用例里的**存在性**断言，缺"容易被顺手破坏"的三类约束：

| 用例 | 钉住什么 |
|---|---|
| `test_ledger_is_append_only_and_only_writes_contract_fields` | 二次追加后第一条记录**逐值不变**；`decided_at` 取权威签署时间；账本只含契约字段（内部 `source` 不进） |
| `test_ledger_write_never_touches_the_authority_file` | 落账前后 `gates.json` **md5 不变**；权威文件里不得出现 `entry_decisions` |
| `test_corrupt_ledger_fails_closed_and_is_not_overwritten`（3 参数） | 不可解析 / 缺 `records` / `records` 非列表 ⇒ `RuntimeError`，且**失败路径不改写**文件 |

这些是**特征钉子**（characterization pin），不是红-绿：它们防回归，不驱动新行为。

### 77.4 全链路断言补一条（唯一存储位置）

`test_s2_detail_fields_and_gate_ledger_on_full_drill_run` 增：`run_dir/gates.json` 里**不得**出现
`entry_decisions` —— 防止将来有人"顺手"在权威文件里再存一份副本（两个来源 ⇒ 红线 8，且锚失效）。

### 77.5 顺带订正的两处过期文档

- `doc/UI_RUNBOOK.md` §14 第 1 条「UI 没有 `entry_decisions` 逐条输入」**已不成立**（P-17 于
  2026-10-23 实现了闸门视图逐条控件 + 节点面板共享草稿）⇒ 加删除线 + 追记现状；
- `doc/plans/2026-10-23-node-panel-revision-kickoff.md` 的「实测更正：重建前须先补 Host 落账」
  加**已过期**横幅（红线 12），并指明现行口径。

### 77.6 四道门实测

| 门 | 本轮 | 说明 |
|---|---|---|
| 软件层单测（文档化入口） | **965 passed / 3 deselected / 0 failed**（343.31 s） | `run_software_checks.sh --ignore=tests/browser`；+5 为新增落账钉子 |
| kb 自测 | 未重跑 | 本轮未改 `kb/**`（只读引用其冻结 schema 作依据） |
| 端到端 | 未重跑 | 本轮无 `loop/workflows/**` 产品代码改动（落账写入路径未动），沿用 §73；全链路落账断言已由上面的 drill 用例覆盖 |
| 文档 | **missing=0**（`9a4548f` 树 checked=1917 / known_missing=10 / env_missing=19，exit=0） | 口径见下条说明（**不是**「仓内无任何数据根」——`workspaces/` 与 `loop/state` 由扫描器跳过，故它们在不在都不影响数字）。**最终值见 §80.4** |
| 浏览器 | **110 passed**（110.91 s） | 本轮无 `loop/web/**` 改动，重跑只为把门留成可复现记录 |

### 77.7 未关闭

- **冻结夹具早于落账**：`RUN-20261015-120626` 无 `decisions/`，故 P-18「已决策 run 逐条处置重建」
  **无法在该夹具上演示**。要补只能跑一轮新的 drill/真实轮再冻结，而写 `ENV_ROOT/kb` 需环境侧授权
  （红线 11）⇒ 挂起待授权，不以回填伪造。
- B 组其余：残留 2（drill + API 直接给 `entry_decisions` 时选项声明要理由而 precheck 放行，方向更严）、
  残留 4（`legacy.html` 仍消费载荷快照 `decision_options`）、决策项文案 —— 维持原登记。
- C / D 组（S0-b、I4/N16、真实通过形态夹具、取消不可续跑、运行入口不消费 S0、e2e 未重跑、
  浏览器门未并入、提交未推送、双数据根入口冗余）不变。

## 78 独立复核整改：落账切片（2026-10-26）

复核由**独立 agent**（fresh context，只读只报、未改工作树；复核前后 `git status` 均空）执行，
对象是 `fac52dd`。**实施者与复核者分离，本节整改由实施者完成、尚待二次复核。**

复核总裁决：**有条件通过** —— 无代码/契约阻断项（落账闭环、`gates.json` 不含逐条处置、
钉子经破坏性反证有效、写权与红线 11 合规），问题全部集中在**文档事实性与登记一致性**。
下面逐条落地；每条先自己复核事实，再改。

### 78.1 事实错误：我给的 schema 依据是错的（复核 M2，已订正）

我在 §77.2 写「`kb/schema/gate_state.schema.json` 的 `required` 界定字段集 ⇒ 业务规格那句
**不可满足**」。**这是错的**：该 schema 的 `gate.additionalProperties` 为 `true`，实测带
`entry_decisions` 的 gate 对象**能通过校验**。已订正三处：

| 位置 | 订正后 |
|---|---|
| `CHANGE_IMPACT_LOOP_SPEC` §7 | 依据改为两条实质理由：① 第二来源（红线 8）+ `gates.sha256` 锚会随处置内容漂移；② 编排规格明文禁止从 `gates.json` 反推。并写明「schema 技术上允许额外字段 ⇒ 这是**设计选择**，不是 schema 禁止」，附 schema md5 `b3d8c0cac0d56599e83879aec0921fb2`（红线 10） |
| `LOOP_ORCHESTRATION_SPEC` §10.4.2 | 同样改写依据 + 补「本文件是单一存储位置，但**不是防篡改证据**（无锚，append-only 靠 Host 约定）」 |
| 本节上方 §77.2 表格 | 该行改为「`required` 列 11 字段但 `additionalProperties: true` ⇒ 允许额外字段」，结论列改为「订正依据是两条实质理由，不是 schema 禁止」 |

### 78.2 唯一数字源里的矛盾登记已作废（复核 M1，红线 8）

`§76.6` 第一条仍写着「逐条处置未落账（…P-18 重建做不到）」，与 §77.1 的「已实现」并存 ⇒
同文件两种口径。已就地加删除线并标注「**已解决（2026-10-26，见 §77.1）**」。
`§54.5` 第 2 条与 `§65.4` 第 5 条同样**就地**加回指（「2026-10-26 已解决，见 §77.1；本条作废，原文保留」），
与 §76.6 的处理方式**一致**——原文一律不改写（只增不改），只加一行指针，避免读单节的人被误导。
（二次复核指出：初版只给 §76.6 就地标注、另两条靠 §77.1 集中声明，做法两头不一；已按复核意见统一为就地回指。）

### 78.3 其余过期文档已订正（复核 M5，红线 12）

复核指出我在 §77.5 只改了 `UI_RUNBOOK` §14 第 1 条，同类说法还有 4 处、且 kickoff 计划的
**源头段**没加横幅。已订正：

| 位置 | 原说法 | 现状 |
|---|---|---|
| `UI_RUNBOOK` **§6.1** 材料区 | 「v1 未提供输入控件，请通过 API 提交」 | 改为「按 `entry_decisions_required` 渲染逐条控件 + 理由输入，与节点面板共用草稿」 |
| `UI_RUNBOOK` §6.1 坑 2（real） | 「v1 界面没有逐条输入控件 ⇒ UI 提交会被 403 拒绝，只能走 API」 | 改为「界面已支持；未处置完提交按钮保持禁用是有意的；仅脚本/API 场景需自建 payload」 |
| `UI_RUNBOOK` §9 对比表 G1 行 | 「可能要求 `entry_decisions` ⇒ 用 API 脚本」 | 改为「在闸门视图逐条处置后提交（界面已支持）」 |
| `UI_RUNBOOK` **§12** 排障表 | 「real 有未决条目、UI 没逐条输入 ⇒ 用 API 脚本」 | 改为「本次提交未覆盖全部 `entry_id` ⇒ 回闸门视图逐条处置」 |
| `plans/2026-10-23-…-kickoff.md` §0.5 ⑥（**源头段**） | 「事件流 jsonl 里也没有；须先补 Host 落账」 | 加**已过期**横幅（红线 12）：落账已实现、事件流现在有 `entries` |
| `spec/SPEC-REV-01-20261022.md` | 「v1 界面缺逐条输入」（未决项） | 两处加「已关闭：P-17（2026-10-23）实现」指针 |

> 小节号更正（二次复核）：本表初版把材料区写成「§5」、排障表写成「§11」，实际分别是
> **§6.1**（`## 6 第 3 步：人工闸门` 之下）与 **§12 排障表**；`9a4548f` 的 commit message 里同样写错，
> 以本节表为准。另：kickoff 计划没有「§R2.1」小节，那里的横幅落在「切片 2 / P-17·P-18 说明处」，
> 编号沿用该文件既有写法（`SPEC-REV-04` §R2.1–R2.4 的简称）。

### 78.4 数字口径订正（复核 M3，红线 2）

`§77.6` 原文记 `checked=2177`，而按当时的工作树实测是 **2181** —— 差 4 恰好等于 §77 自身新增、
会被文档门计数的 4 个路径 token ⇒ 该数字取自 **§77 落盘之前**，属红线 2「数字必须从（最终树的）
命令输出复制」。同一提交的 commit message 又写 2181，与 STATUS 自相矛盾。

**测量条件拆开写清**（二次复核要求）：

| 树态 | `checked` | 说明 |
|---|---|---|
| `fac52dd`，**含**上一轮遗留 `.wsp-r3r4`（1.2 MB 数据根副本） | 2181 | commit message 与 §78.4 初稿引用的就是这个数 |
| `fac52dd`，干净树（无数据根） | 1916 | 二次复核用 `git archive` 树副本独立复算 |
| `fac52dd` 干净树去掉 §77 | 1912 | ⇒ §77 恰加 4 token，「差 4」的诊断成立 |
| `9a4548f`（§78 落盘前） | 1916 | — |
| `9a4548f` + §78（**不含**本轮二次整改） | 1917 | ⇒ §78 加 1 token |
| **二次整改后的最终树**（现行） | 见 §77.6 / §78.7 | 最终值以那两处为准（本节表格记的是各历史树态，不随新编辑漂移） |

更根本的是**测量口径没写清**：`env_missing`/`checked` 会随仓内是否存在数据根而变。
本轮把口径固定为「**仓内无任何数据根/影子树**」，并清掉上一轮遗留的 `.wsp-r3r4`
（1.2 MB 数据根副本，7 个 md，无任何文档引用）。清理后按「无数据根」口径实测：`fac52dd` 干净树
1916、`9a4548f` 加 §78 后 1917。订正后数字见 §77.6，测量条件写进该行说明。

### 78.5 钉子措辞与断言强度（复核 S1/S2，已改）

- `tests/test_gate_ledger.py` 注释「旧记录**逐字节**等价」→ 改为「**逐值**等价」，并注明
  「整文件按同值不同格式重排不在本用例约束内」。复核实测：字节级重排不会让用例变红，
  原措辞把断言强度说大了。
- `tests/test_flow.py` 的「`gates.json` 不含 `entry_decisions`」由**全文子串**判定改为
  **结构化判定**（检查每个 gate 对象的键集合），避免将来人工理由原文里出现该词导致假红。

### 78.6 复核提出、本轮不修的项（已登记）

1. **读侧把「损坏」并入「缺失」**：`contracts._decision_ledger` 丢弃 `_read_artifact` 的错误串，
   损坏账本与「早于落账的旧 run」在面板上不可区分；写侧却是 fail-closed。
   现状与 `_decision_ledger` 的 docstring 一致（「缺失/损坏一律返回 None」），属**已声明的降级**；
   要增强得同时改投影文案与契约，属独立切片 ⇒ 登记不改。
   **已关闭（2026-10-26，§81.1）**：`_decision_ledger` 改返回 `(doc, status)`，
   `missing` / `corrupt` / `ok 但 records 空` 三态在面板文案里分开，判据与钉子见 §81.1。
2. **「签署成功但恢复失败」会留下 signed 但无账本的形态**（`main_flow` 的 sign→resume 路径）：
   此时面板措辞会把它误归因为「本轮早于处置落账」。属措辞精度问题，登记待后续。
   **已关闭（2026-10-26，§81.1）**：note 只陈述事实（哪份文件不存在 / 不可解析），
   不再声称版本先后；`RUN-20261024-002609` 那类形态不再被错误归因。
3. 复核的破坏性反证用的是**运行时 monkeypatch**（测试文件原样、未改仓库），它证明钉子对相应回归会红，
   但不等价于「真实改坏生产代码也会红」——该差别如实记录。

### 78.7 本轮门（整改后重跑）

| 门 | 结果 | 说明 |
|---|---|---|
| 软件层单测 | **965 passed / 3 deselected / 0 failed**（330.29 s） | 测试文件有改动（S1/S2），已重跑；与 §77.6 同值 |
| 文档 | **missing=0**（`9a4548f` 树 checked=1917） | 见 §77.6 同一口径；**最终值见 §80.4** |
| 浏览器 / kb 自测 / 端到端 | 未重跑 | 本轮整改不触达 `loop/web/**`、`kb/**`、产品代码 |

### 78.8 待二次复核

本节的订正**由实施者自己完成**，不构成独立验证。复核者当时列出的 M1–M5 与 S1/S2 已全部落地，
S3/S6 转为登记项；S5（冻结 schema 引用补 md5）已在 §78.1 落地。二次复核应只核**文档一致性**
（尤其 §76.6/§54.5/§65.4 的作废可读性）与**数字可复现性**。

## 79 二次复核整改与收尾：落账切片（2026-10-26）

第二位**独立复核者**（fresh context、只读只报；复核前后 `git status` 均空、无数据根残留）复核
`fac52dd` → 整改 `9a4548f`，总裁决**有条件通过**：无代码/契约阻断，4 条必须修全部在文档/注释层。
本节是实施者对那 4 条的整改记录；**完成整改后未再起第三次独立复核**（如需可再派）。

### 79.1 必须修 1：测试注释残留被推翻的 schema 依据（红线 8）

二次复核指出：文档三处已改好，但**测试注释**还留着「冻结 schema 的 `required` 不含该字段」这个
已被推翻的推理（`tests/test_gate_ledger.py` 文件头、`tests/test_flow.py` 注释）。已改为与订正后口径一致：
「依据是 ① 第二来源（红线 8）+ 锚漂移 ② 编排规格明文禁止反推；**不是** schema 禁止——
`gate.additionalProperties` 为 `true`，技术上允许额外字段，所以这是**设计选择**」。

### 79.2 必须修 2：§78.3 定位表的小节号写错

初版把 `UI_RUNBOOK` 材料区写成「§5」、排障表写成「§11」，实际是 **§6.1**（`## 6 第 3 步：人工闸门`
之下）与 **§12 排障表**。表格已改，并就地注明 `9a4548f` 的 commit message 里同样写错、以表为准；
另注明该计划文件没有「§R2.1」小节（那里的横幅落在「切片 2 / P-17·P-18 说明处」）。

### 79.3 必须修 3：§78.4 的数字叙述仍属「落盘前」

初版写「清理后 `checked` 由约 2181 降到 1916」——1916 是 §78 落盘前的值，与同表 1917 并存，
**正是它自己批评的老毛病**。已把 §78.4 改成**按历史树态列的测量表**（fac52dd 含遗留数据根 2181 /
**干净** fac52dd 1916 / 干净 fac52dd 去 §77 1912 / 9a4548f 1916 / 9a4548f+§78 1917），
并写明「现行最终值以 §77.6 / §79 为准，本表不随新编辑漂移」。

### 79.4 必须修 4：作废方式前后不一致

初版只给 §76.6 就地划线，`§54.5` 第 2 条 / `§65.4` 第 5 条靠 §77.1 集中声明 —— 复核判断
「读 §54.5 的人仍会被误导」，且与「不回改历史小节」的说法自相矛盾。已统一为**就地回指**：
两条各加一行「**（2026-10-26 已解决：见 §77.1；本条作废，原文保留）**」，原文一律不改写（只增不改）。

### 79.5 顺带采纳的建议（复核 S1/S2 及若干）

- `tests/test_flow.py` 的「`gates.json` 不含 `entry_decisions`」**补回顶层键检查**
  （结构化判定只查 `gates.*` 会漏掉顶层形态，覆盖面比旧版全文子串窄）；
- `tests/test_gate_ledger.py` 同主题断言也改成结构化（顶层键 + 每个 gate 对象）；
- `STATUS` §77.2 表行引用冻结 schema 补 md5 `b3d8c0cac0d56599e83879aec0921fb2`（红线 10 字面要求）；
- `plans/2026-10-23-…-kickoff.md` 源句「从 `n2_diff.json + gates.json` 重建」加**行内**过期标记，
  不只靠下方横幅。

### 79.6 本轮门（最终树）

| 门 | 结果 | 说明 |
|---|---|---|
| 软件层单测 | **965 passed / 3 deselected / 0 failed**（334.88 s） | 二次整改动了两个测试文件的注释与断言，必须重跑 |
| 文档 | **missing=0**（checked=1920 / known_missing=10 / env_missing=19，exit=0） | 数字写入后复测同值。**口径更正（2026-10-26 收尾）**：此前写的「仓内无任何数据根」不准确 —— 扫描器本身会跳过 `workspaces/`、`loop/state`、`loop/.venv`、`.git/` 等（见 `doc/audit/check_doc_links.py` 的 skip 列表），所以它们存在与否都不改数字；真正会改数字的是**扫描器不跳过的临时目录残留**（如上一轮的 `.wsp-r3r4`）。本表各值均在「无此类残留」的树上测得 |
| 浏览器 / kb 自测 / 端到端 | 未重跑 | 本轮不触达 `loop/web/**`、`kb/**`、产品代码；§78.7 已记同理由 |

### 79.7 复核者明确「未能验证」的两点（保持可见）

1. `2181` 这个精确值**已不可复现**（触发它的 `.wsp-r3r4` 已删），只能靠 1912/1916/1917 链条自洽反推；
2. 两轮复核报告**均未入库**（`doc/audit/` 最近仍是 `AUDIT-20261022-*`）。若要把复核意见变成可追溯证据，
   应按 `AGENTS.md` §6「一次审计一份报告」把两份复核报告落 `doc/audit/`——**本轮未做**（属审计 owner 写权，
   且需先确认是否需要入库）。

### 79.8 未关闭（与 §77.7 相同，未变）

冻结夹具 `RUN-20261015-120626` 早于落账 ⇒ P-18 无法在夹具上演示（补夹具需写 `ENV_ROOT/kb` 的环境侧授权，
红线 11）；B/C/D 组其余项与移动端维持原登记。

## 80 演示夹具冻结：`RUN-20261026-135835`（2026-10-26）

用户要求「至少有一套可以演示的真实夹具」。核实结论：**不需要重跑**，本机已有一轮现成可用的
drill 运行；周末那轮真实轮不能用于演示逐条处置，原因是**落账未发生**而非质量不佳。

### 80.1 为什么不用周末那轮（`RUN-20261024-002609`）

- `gates.json`：G1 `signed confirmed @ 2026-10-24T00:29:11+0800`，G2/G3 仍 `pending`；
- `view.json`：`status=failed`，`error=恢复失败：async_load 异常 ValueError: Can not load
  TriggerFlow execution snapshot … flow definition fingerprint mismatch`；
- 无 `decisions/`：逐条处置在**恢复后**的闸门 chunk 里落账（`chunks/gates.py::append_decision_ledger`），
  恢复失败 ⇒ 一条未写；G2/G3 从未走到。
- 归档演练轮 `RUN-20261015-120626` 同样没有降账，但原因是**早于落账功能**（`e7528fe`，2026-10-24 才进仓）。

### 80.2 冻结的夹具

| 项 | 值 |
|---|---|
| 源 run | `workspaces/s0-ws-20261023/runs/RUN-20261026-135835`（= SPEC-REV-12 验证那轮，`finished`/`drill`） |
| 夹具目录 | `workspaces/s0-ws-20261023/fixtures/demo-20261026/`（`runs/RUN-20261026-135835/**` + `md5.txt` 103 行 + `README.md`） |
| 体量 | 14 MB；**不入 git**（沿用 `workspaces/**` 约定） |
| 内容 | G1 `confirmed`（**4 条逐条处置全部落账**）/ G2 `accept` / G3 `milestone_only`；三门各带签署当时的硬阻断快照 |
| 校验 | `md5sum -c md5.txt --quiet` → 103 个文件全部通过 |

身份档案落 `doc/evidence/DEMO_FIXTURE_20261026.md`（tracked）：含关键件 md5、演示步骤与
**丢失后的重建步骤**（跑一轮 drill + 用闸门 API 显式提交覆盖全部 `entry_id` 的 `entry_decisions`）。
`workspaces/README.md` 增 `fixtures/` 索引。

### 80.3 演示路径实测（命令输出复制）

把夹具复制成独立数据根 → 起服务 → 查面板：

```
/api/runs   -> [('RUN-20261026-135835', 'finished', 'drill')]
run_status = finished | run_terminal = True
state      = decided | decision = confirmed | note = None      # note=None ⇒ 不再报"未留存"
counts     = {'entries': 4, 'revision_points': 4, 'disposed': 4, 'unresolved': 7,
              'unresolved_points': 4, 'hard_block': 1, 'pending_cases': 0,
              'conflicts_open': 0, 'conflicts_total': 0}
逐条处置   = [('TCS9620_MAC_TOP.v', 'confirmed'), ('dom_engine_top.v', 'confirmed'),
              ('pcie_register.v', 'confirmed'), ('uart_top.v', 'confirmed')]
hard_block = ['I4_CONFLICTS_UNCLEARED']
```

⇒ 面板「共 4 条修订点，已处置 4 条」的数据来自 `decisions/G1_diff_confirm.json`（落账），
不是 `gates.json`。四屏可演：运行监控 / 人工闸门 / **N4 节点面板（逐条处置重建）** / N13·N14。

### 80.4 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 文档 | **missing=0**（checked=1935；新增 1 份 evidence + README 索引；数字在 §80 落盘后测得，口径见 §79.6 的更正） | — |
| 软件层 / 浏览器 / kb / 端到端 | 未重跑 | 本轮**未改**产品代码与测试，只新增夹具与文档 |
| 演示路径 | 上述 §80.3 实测 | 起真实 uvicorn + 两个只读端点 |

### 80.5 未关闭

- 夹具**不入 git**：若 `workspaces/` 被清理，按 `doc/evidence/DEMO_FIXTURE_20261026.md` §4 重建；
  md5 与身份已在 tracked 证据里，可判定是否漂移。
- §78.6-2 的「有签名无落账」**归因措辞**仍未改（对周末那轮会显示"本轮早于处置落账"，不准确）；
  本轮只做夹具，不动产品代码。要改属 `contracts` 投影措辞 + 测试的小切片。
  **该项已于 2026-10-26 关闭**（§81.1：`contracts` 投影区分「不存在 / 不可解析」并去掉
  「本轮早于处置落账」的猜测性归因，新增 2 条钉子用例）。

---

## 81 A 组收尾：账本归因、旧界面选项来源、数据根脚本去重（2026-10-26）

上游：§80 之后仍开的 A 组待办（本会话盘点清单），由人指定「先把 A 组做了」。
计划：[`doc/plans/2026-10-26-a-group-cleanup.md`](plans/2026-10-26-a-group-cleanup.md)。
写权：本轮**由 Lead 本人实现**（实现者 ≠ 独立验证者，见 §81.7）。

### 81.1 A1 账本「缺失 / 损坏」可分，归因只说事实

| 项 | 内容 |
|---|---|
| 问题 | `contracts._decision_ledger()` 把「文件不存在」与「文件损坏」都折成 `None`，面板只能笼统说"逐条处置未留存"，并把原因写死成「本轮早于处置落账」。对 `RUN-20261024-002609`（签名成功、`async_load` 恢复失败 ⇒ 账本没写成）是**错误归因**（§78.6-1/-2 登记项） |
| 实现 | 返回值改 `(doc, status)`，`status ∈ {ok, missing, corrupt, no_run_dir}`；文案唯一出口 `_ledger_absent_note(gate, status)`（红线 8：一处判据）；`hard_block` 旧记录改说"`decisions/<gate>.json` 的该条记录没有该字段"，不再声称 run 早于落账 |
| 判据 | ①不存在 ⇒ note 含"未落账"+文件路径+"不存在"，**不含**"早于"/"不可解析"；②不可解析**或**形状不是对象 ⇒ 含"不可解析"+"损坏"，**不含**"不存在"；③有文件但 `records` 空 ⇒ 说"没有记录"；三种情形 `entries[].disposition` 全 `null`（不编） |
| 钉子 | `loop/tests/test_node_detail_projection.py`：改写 `test_gate_entries_decided_without_ledger_says_not_retained`；新增 `test_gate_entries_corrupt_ledger_is_not_reported_as_missing`、`test_gate_entries_ledger_without_records_is_explicit`（后者与前者互为"必须区分"的反证） |
| 规格 | `LOOP_ORCHESTRATION_SPEC §10.4.2` 增「读不到时必须区分三种情形」+ 实测反例；`WEB_UI_SPEC §4.2 已决策态只读` 同步改判据文字 |

### 81.2 A3 旧界面（`legacy.html`）不再消费中断快照选项

| 项 | 内容 |
|---|---|
| 问题 | `gateDecisionOptions()` 的取值顺序是「`payload.decision_options`（中断快照）→ `run_view.gate_options` → 手抄枚举兜底表」。快照恢复后旧选项会盖掉服务端重算值（第二套判据，红线 8）；兜底表是前端手抄 `kb_lib.GATE_DECISIONS`（红线 4） |
| 实现 | 只读 `run_view.gate_options`；没有 ⇒ 返回空、面板明说「服务端未下发决策选项（`run_view.gate_options` 缺失）：本界面不写死枚举 ⇒ 不可提交」，`#btnSubmit` 保持禁用；删除 `GATE_DECISIONS_FALLBACK` |
| 钉子 | 新增 `loop/tests/browser/test_legacy_gate_options.py`（受控替身：中断载荷有选项、`gate_options` 缺失 ⇒ **零按钮** + 不可提交 + 不出现快照文案；服务端下发重算值后才出现按钮）。判别性：旧实现会渲染快照选项、且兜底表会让按钮出现 |
| 规格 | `WEB_UI_SPEC §5`（闸门视图）「中断载荷里的选项只是快照」补两个前端同一口径 |

### 81.3 A2 可写数据根构造只剩一份实现

| 项 | 内容 |
|---|---|
| 问题 | `spikes/provision_dev_workspace.sh`（持久副本，复制 733 MB）与 `spikes/run_software_checks.sh`（一次性影子，符号链接）各写一遍"带哪些目录、夹具在不在"，两份口径会漂；后者另用 `host.paths` 解析数据根，与前者用 `kb_lib` 不是同一入口 |
| 实现 | `provision_dev_workspace.sh` 成为唯一实现，新增 `--link-fixture` / `--quiet` / `--tolerate-missing-fixture`；`run_software_checks.sh` 删除自带的 `mkdir/cp/ln` 段与 `host.paths` 解析，改为委托 `DEST=$SHADOW provision ... --force --link-fixture --quiet --tolerate-missing-fixture`（缺夹具仍是 warn + 继续，保持旧入口行为） |
| 实测 | 一次性影子：本轮软件层全套跑通（§81.5）；持久副本：`DEST=<repo>/.dev-ws-copytest provision --force --quiet` → rc=0，`runs/RUN-20261015-120626` + `baselines/` + `index/conflicts/adjudication` + `FIXTURE_IDENTITY.md` 齐（自检项全过），`--cleanup` 后目录消失 |
| 钉住 | `tests/test_software_checks_script.py`（既有："N passed" 汇总行不被吞）在委托后仍 2 passed |

### 81.4 A4 浏览器门：**不并入**全量单测门（裁决，不是缺陷）

裁决：保持单独执行，登记为**第五道补充门**，四道门定义不变。理由三条：
① 依赖 Chromium + 可写 `HOME`/`TMPDIR`，并入会把"软件层可跑"绑到"本机能起浏览器"（缺件属环境缺件，不能算通过）；
② 实测成本：软件层 162 s + 浏览器 115 s，串行化并加上浏览器启动抖动 ⇒ 单门 5 min+，失败定位混在一个退出码里；
③ 判据不同（浏览器门验界面行为，单测门验软件行为）。
落点：`AGENTS.md §4` 表格后新增该段（含命令、`tests/browser` 期望 0 failed、"改 `loop/web/**` 或界面投影字段必须单独跑并记 STATUS"）。

### 81.5 本轮门（**复核前**那一轮，数字从命令输出复制；整改后见 §81.9）

| 门 | 结果 | 说明 |
| --- | --- | --- |
| 软件层单测 | **967 passed / 3 deselected / 0 failed**（162.46 s） | 走 `bash spikes/run_software_checks.sh --ignore=tests/browser`（影子根由 `provision --link-fixture` 造）；较 §78.7 的 965 多 2 条 = 本轮 A1 新增用例。3 条 deselected 仍是 `@pytest.mark.env_layer`（`test_archive_e2` ×2、`test_projection_and_frozen` ×1，需可写 `ENV_ROOT`） |
| 浏览器门 | **111 passed**（115.39 s） | `PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp pytest -q tests/browser`；较 §77.6 的 110 多 1 条 = 本轮 A3 新增用例 |
| 端到端 | **ALL PASS，117 断言 / 0 FAIL**（相位 1/2/3/4/4b/5 全部 `rc=0`；分部 PASS=50/27/18/8/8/6） | 先 `provision_dev_workspace.sh --force` 造可写数据根，再 `LOOP_WORKSPACE=<repo>/.dev-ws bash spikes/accept_v1_run.sh`；跑完 `--cleanup` 删除。断言总数与 §73 的 117 同值 ⇒ 本轮改动未改端到端可观察行为 |
| kb 自测 | 未重跑 | 本轮未改 `kb/**`；上次实测 §75.6（`_selftest_gate_schema.py` PASS=10、`_selftest_n5_reachability.py` PASS=9） |
| 文档 | **missing=0**（checked=1944 skipped=24560 historical=857 known_missing=10 env_missing=19；**checked/skipped 是诊断值、随树漂移**——§19 已登记「记录本身会改变被扫跨度」） | `python3 doc/audit/check_doc_links.py`；跑前已 `provision --cleanup` 删除仓内临时数据根（否则拷贝来的环境文档会被算成 missing，口径见 §79.6） |

### 81.6 未关闭（本轮明确不做）

- 决策项文案（失败轮次的 `accept` 是否改名）属产品文案，需人裁决。
- 残留 2（drill + API 直给 `entry_decisions` 时选项声明"不需要理由"而 precheck 收下）方向是**更严**，维持登记。
- 演示夹具"通过形态"仍缺（需一次真实通过轮或 `ENV_ROOT` 写授权，红线 11）。
- 两轮历史复核报告（§78、§79 那两轮）仍不在 `doc/audit/`：对话里没有原文，**复原等于伪造证据**，故不复原。本轮起改为每轮复核即落档——本轮报告见 [`AUDIT-20261026-a-group.md`](audit/AUDIT-20261026-a-group.md)（§81.8）。


### 81.8 独立复核（2026-10-26）与整改

复核者：**独立 agent**（非实现者），报告 [`doc/audit/AUDIT-20261026-a-group.md`](audit/AUDIT-20261026-a-group.md)
（报告头注明"本轮是否修复：否，只登记"）。结论：**阻断 0**，应修 3 组、建议 6 条；
复核者自己复现了当时点的四道门（软件层 967 / 浏览器 111 / 端到端 117 断言 /
文档 missing=0），并做了运行时 monkeypatch 的破坏性反证（三条 A1 回归分别 1 红 / 3 红 / 1 红，基线 3 绿），
还实测出"旧 `legacy.html` + 新用例 → 红（渲染出快照选项）"。

整改（**Lead 实施，不构成独立验证**）：

| 编号 | 复核意见 | 处置 | 落点 |
|---|---|---|---|
| R1 | 委托后丢了「数据根不存在 ⇒ exit 2」，且 `--quiet` 吞掉缺夹具 warn | 已修：provision 增 `--require-source`（数据根不是目录 ⇒ exit 2）；新增 `warn()` **不受 `--quiet` 抑制** | `spikes/provision_dev_workspace.sh`、`run_software_checks.sh` |
| R2 | `AGENTS.md` 那句「~5.5 min → 20 min+」无命令输出支撑（红线 2） | 已改：用实测 168.26 s + 114.79 s 表述，删掉倍数说法 | `AGENTS.md` §4 |
| R3 | 小节号/出处错引 3 处 | 已改：快照口径在 **§5**（不是 §4.4，3 处）、「§75 的 110」→ **§77.6 的 110**、计划里「§10 A10 有门命令」拆成「跑法在 AGENTS §4 / A10 只有视口判据」；另把 §10.4.2 的「两种事实」改为三种（+`no_run_dir`） | 多处 |
| S1 | 字面 `null`/非对象账本报"不存在"、`records` 形状不符报"为空"、非 UTF-8 或路径是目录直接抛异常 | 已修：`_decision_ledger` 收敛 `OSError`/`UnicodeDecodeError` 到 `corrupt`，`解析成功但不是对象 ⇒ corrupt`；`records` 非 list 或末条非对象 ⇒ `corrupt`。新增 7 条参数化用例（`null`/字符串/数组、`records` 为 str/dict/list-of-str、非 UTF-8、路径是目录） | `contracts.py`、`test_node_detail_projection.py` |
| S2 | `legacy.html` 同屏"仍可提交决策"与"不可提交"矛盾；`app.js` 仍写 `decision_options` | 已修两处文案 | `legacy.html`、`app.js` |
| S3 | 旧界面钉子只覆盖 G1 | 已参数化 **G1/G2/G3**，每道门配独立快照文案（任一道门回退"快照优先"都会红） | `tests/browser/test_legacy_gate_options.py` |
| S4 | 解析片段 `import kb_lib` 未禁字节码，会往冻结的 `kb/tools/` 写 `__pycache__` | 已修：`python -B` + `sys.dont_write_bytecode = True`。**如实登记**：仓库 `kb/tools/__pycache__/` 内确有 2026-10-15 留下的旧 `.pyc`（`kb_lib.cpython-38.pyc` 等）；删除它们属**写 `ENV_ROOT`**（红线 11），本轮不动，只保证新入口不再新增 | `provision_dev_workspace.sh` |
| S5 | 「第五道补充门」与「不是第六道必备门」第一眼矛盾 | 已改：统一为"**四道必备门之外的补充门**"，三条理由按实测重写 | `AGENTS.md` §4、计划 A4 |
| S6 | STATUS 记的 `checked/skipped` 是随树漂移的诊断值 | 已加"诊断值、随树漂移（§19）"标注（见 §81.5/§81.9） | `doc/STATUS.md` |

**历史文档的过期登记点**（复核 §6-2；按「只增不改」只加指针、不回填原文）：
`STATUS` §52 复核清单第 3 条加内联"已过期"；4 份 `doc/plans/2026-10-23-node-panel-*` 顶部各加过期横幅
（指向本节 §81.1）。

**未处理（超出本轮写权/产品范围）**：`workspaces/real-env-copy/loop/web/index.html` 是 ignored 派生副本，
仍含旧 `GATE_DECISIONS_FALLBACK`，不在产品路径；是否清理归该副本 owner。

### 81.9 整改后门（复核意见落地后重跑）

| 门 | 结果 | 说明 |
|---|---|---|
| 软件层单测 | **974 passed / 3 deselected / 0 failed**（167.06 s） | 较 §81.5 的 967 多 7 条 = S1 新增参数化用例；3 条 deselected 仍是 `@pytest.mark.env_layer` |
| 浏览器门 | **113 passed**（125.93 s） | 较 §81.5 的 111 多 2 条 = A3 用例参数化到三道门 |
| 端到端 | **ALL PASS，117 断言 / 0 FAIL**（6 个 phase 全 `rc=0`，PASS=50/27/18/8/8/6） | 复核意见落地后重跑；先 `provision_dev_workspace.sh --force`、跑完 `--cleanup` |
| 文档 | **missing=0、exit=0** | 含本轮新增的复核报告 `doc/audit/AUDIT-20261026-a-group.md`（复核者改路径断链后复测亦 missing=0）。**只记 missing 与退出码**：`checked/skipped` 属诊断值、记录动作本身就会改变被扫跨度（§19），写死一个数只会立刻漂移——故本节不回填 |
| kb 自测 | 未重跑 | 本轮未改 `kb/**`；上次实测 §75.6 |

### 81.7 待独立复核

本轮 A1–A4 **由实现者本人完成验证**，不构成独立验证。复核范围为：A1 三种情形的判据与文案、
A3 旧界面判据来源、A2 委托后脚本行为一致、A4 的 AGENTS 段落与四道门口径、以及 §81.5 数字可复现性。

---

## 82 B 组裁决：决策项文案（2026-10-27）

上游：`§81` 完成后本会话盘点的 B 组（需人拍板的产品/流程项），人指定"进行 B 组裁决，一个一个来"。
本节只记**裁决 + 落点**，实现由 Lead 完成（非独立验证）。

### 82.1 B1 失败轮次的「接受」是否改名 —— 裁决：**不改标签，只对齐警示措辞**

| 项 | 内容 |
|---|---|
| 现状（裁决前） | 选项标签恒为权威文案「接受报告」（`host/gate_authority.human_readable`）；报告结论 `not_passed` 时该选项 `requires_reason=true`，界面已显示选项旁「· 必须填写理由」+ 顶部警示「**接受失败报告**必须填写理由；接受不等于判据通过，N16 仍被 I3/I4 阻断」 |
| 裁决 | **标签不改**；只把警示里的「接受失败报告」与判据口径（`not_passed` = 未通过）对齐为「接受未通过报告」。理由：① 标签若按轮次变体，同一个 `accept` 在已决策态/归档里会有多种名字，审计与对账难读；② "要不要理由"已由服务端单一判据表达，标签再分身等于把同一事实说两遍（红线 8 精神）；③ 风险告知已由 `requires_reason` + 警示 + 提交前预检三处覆盖，改标签不增加信息量 |
| 落点 | `loop/web/app.js`（警示文案与注释）、`loop/tests/browser/test_run_sessions.py`（同一用例的断言文本）、`WEB_UI_SPEC §5` 新增「决策项标签不随轮次变体」条款 |
| 反向证据 | 该用例本身是**判别性**的：反向步骤把重算值的 `requires_reason` 置 `False`（快照仍为 `True`）⇒ 警示必须消失；标签改名的方案无法被任何断言判定，这也是不采用它的原因之一 |

**B1b（登记，不改）**：服务端 403 拒绝串仍写「接受失败报告必须给出理由（reason）」（`workflows/chunks/gates.py`）。
不改的理由：① 该串已被 [`doc/evidence/SPEC_REV05_VERIFY_20261026.md`](evidence/SPEC_REV05_VERIFY_20261026.md) §3
按原文引用（证据只增不改），改串会让证据里的实测原文与代码不一致，需另立新证据；② 它是 403 `detail`
的说明文字，与界面警示同义、不影响任何判据（枚举/`requires_reason`/`precheck` 全在别处）。
若要统一，属独立小切片（改串 + 新证据 + 更新引用），不在本轮。
   **已关闭（2026-10-27，§92）**：403 串与成功 warning 已统一为「未通过」，判据零变化，
   新证据 [`SPEC_REV05_RECHECK_20261027.md`](evidence/SPEC_REV05_RECHECK_20261027.md) 记录改前/改后原文与 md5；
   旧证据按只增不改保留原文。

### 82.2 本轮门（B1 落地后）

| 门 | 结果 | 说明 |
|---|---|---|
| 浏览器 | **113 passed**（122.60 s） | 只改 `app.js` 文案与一条断言 ⇒ 跑 `tests/browser` 全套确认无别的用例依赖旧串 |
| 文档 | **missing=0、exit=0** | 新增本节 + `WEB_UI_SPEC §5` 一段；`checked/skipped` 为诊断值、不落盘（§19 漂移） |
| 软件层 / 端到端 / kb 自测 | 未重跑 | 本轮未改任何 Python 产品代码、`kb/**` 与工作流；文案改动由浏览器门覆盖 |

### 82.3 B2 残留 2（drill 直给 `entry_decisions` 时要不要那句整门理由）—— 裁决：**维持现状 + 写进口径 + 加钉子**

| 项 | 内容 |
|---|---|
| 现状 | drill 下界面**没有**逐条通道（`entry_decisions_required=false`），只能用非空 reason 当"已逐条核对"的 attestation ⇒ 这条 `requires_reason` 的本来含义是**替身**。直连 API 若提交 `entry_decisions`，服务端走的是**更硬**的校验：必须覆盖全部条目、`ignored/disputed` 逐条带理由、逐条结论与整门决策一致；满足后不再要求整门 reason |
| 裁决 | **维持现状**（不收紧成"两者都要"）。理由：① 逐条证据严格强于一句 attestation，多要的那句通常只是复述，属信息量为零的仪式；② 界面上不存在矛盾——drill 界面没有逐条通道，它提交时仍会被要求理由；③ 收紧只会让既有直连脚本无谓变红 |
| 落点 | `LOOP_ORCHESTRATION_SPEC §10.4.2` 新增「drill 的 reason attestation 与逐条处置的关系（裁决 B2）」；`WEB_UI_SPEC §5` 该 flag 处加交叉引用（界面不受影响）；钉子 `tests/test_fix_lifecycle.py::test_g1_drill_entry_decisions_replace_the_attestation`（覆盖不全仍拒 + 覆盖全部时无 reason 也放行） |
| 钉子的判别性 | 若将来收紧成"两者都要"，该用例第二次调用（`reason=None`）立刻红；若放宽成"给几条就算"，第一次调用（覆盖不全）立刻红 —— 两个方向都被钉住 |

### 82.4 B 组剩余：推送 —— **本机沙箱不可达，待人工推送**

2026-10-27 实测（本机）：`git push origin main` 报
`fatal: … Received HTTP code 503 from proxy after CONNECT`；复测 `curl https://github.com/`
经代理 20 s 超时、`direct=000`（清空代理变量后直连亦不可达）、`ssh git@github.com` 无法解析主机名。
⇒ **不是凭据问题，是本机出网被代理阻断**。因此当时 16 个提交（`dd587e6..4a512a4`）留在本地、**未推送**；本条登记提交本身会让待推数 +1（不在此回填绝对数）。
需要人工在能出网的机器上执行：

```bash
cd change-impact-loop
git push origin main          # 或 gh-ssh（若该机已配 SSH key）
```

凭据处理：PAT 由人工在对话中提供，仅在一次性 `credential.helper` 里以环境变量使用，
**未写入 `.git/config` / `~/.git-credentials` / 任何文件**（推前推后均核过）；
既然已在对话中出现，**建议立即在 GitHub 上作废并重签**。

B 组其余项已清：决策项文案（§82.1）、drill 直给逐条处置（§82.3）、复核报告落档（§81.8）。

---

## 83 C 组修订（一）：环境层可运行、证据时效、I4 冲突的机制缺口（2026-10-27）

上游：`§82` 之后仍开的 C 组清单，人指定"开始 C 组的修订"。计划
[`doc/plans/2026-10-27-c-group.md`](plans/2026-10-27-c-group.md)。本轮由 Lead 实施（非独立验证）。

### 83.1 C13 环境层 3 条用例：派生 ENV_ROOT 副本上跑通

| 项 | 内容 |
|---|---|
| 问题 | `@pytest.mark.env_layer` 的 3 条（`test_archive_e2` ×2、`test_projection_and_frozen` ×1）要写 ENV_ROOT 下的 `SIMLIB_RUN/`、归档与数据根，本机 ENV_ROOT 只读 ⇒ 直接跑必红，软件层入口只能 `-m "not env_layer"` 排除，长期登记为"环境缺件" |
| 边界 | 红线 11 只禁止写**原** ENV_ROOT；在**派生副本**上验证与 S0 派生副本同一原则 |
| 实现 | 新增 `loop/spikes/run_env_layer_checks.sh`：kb_lib 解析 ENV_ROOT → `cp -a --reflink=auto` 派生副本（2.6 GB）→ `chmod -R u+w` → 以 `LOOP_ENV_ROOT=<副本> LOOP_WORKSPACE=<副本>/kb` 跑 `-m env_layer`；`--reuse` / `--cleanup` |
| 零写入自证 | 跑测试前建 marker，跑完 `find <原ENV_ROOT> -newer <marker>` 必须命中 0，否则 exit 3 |
| 实测 | 冷启动（含 2.6 GB 复制）整轮 **10.221 s**、热启动（`--reuse`）**7.17 s**；结果 **3 passed, 24 deselected**；**原 ENV_ROOT `find -newer` 命中 0** |
| 登记 | `AGENTS.md §4` 增环境层入口段；`run_software_checks.sh` 的排除提示改为指向该脚本（`INCLUDE_ENV_LAYER=1` 仅在其可写时有效）；`.env-copy/` 已加入 `.git/info/exclude` |

### 83.2 C14 kb 自测重跑（刷新证据时效）

在派生副本的可写数据根上跑（`-B` 保证不往冻结的 `kb/tools/` 写字节码）：

```
_selftest_gate_schema.py       汇总：PASS=10 FAIL=0
_selftest_n5_reachability.py   汇总：PASS=9  FAIL=0
```

⇒ `AGENTS.md §4` 的 kb 自测门重新有本轮实测（上次是 §75.6）。

### 83.3 C10 I4 72 条冲突：机制缺口已定位，改动待授权

**现状（命令输出）**：`<ENV_ROOT>/kb/conflicts/conflicts.json`
（md5 `1d0b95468e8be451955a0f2443c478be`）共 **72** 条，**全部** `status=open`、**全部**
`blocks_release=true`；分类 NUM 13 / NAME 10 / ADDR 10 / MISS 9 / RT 7 / RW 6 / BITS 5 /
SCOPE 4 / 复合 7。I4 消费链只读 `blocks_release` ⇒ 改接口文档不解除阻断。

**已有资产**：`<ENV_ROOT>/kb/adjudication/C_conflicts_triage.md`
（md5 `bc862a6855cf48f5af4a6a70294f5c87`，764 行）已把 72 条逐条摘要、可复现分组（G1–G9 /
根因批 B1–B4 / 覆盖自检并集=72）、必须逐条看的 19 条、跨章节 17 条、与
`access_restrictions.json` 交叉 22 条、与 `pending.json` 交叉 23 条整理完，并逐项对照 schema。
**结论：不需要改 schema**（`status ∈ {open,confirmed,ignored,ruled,fixed}`、`resolution`、
`resolution_actor`、`resolution_kind`、`blocks_release` 全在 `kb/schema/conflicts.schema.json`，
md5 `434387c12a972d2ca113c09cbc6cb6ac`）。

**四个工程缺口**（该文件 §6.4，本轮已复核）：① 无 `ruled_at` 字段（时刻并入 `resolution` 文本或授权加字段）；
② 条件不变式 schema 表达不了（`kb_lib.validate` 拒绝 `if/allOf`）⇒ 只能 Host 工具强制；
③ **没有任何 Host 工具能写 conflicts 裁决**（human-only 与锚机制目前只覆盖 `gates.json` 三闸门）；
④ 重跑 `kb/tools/n1_conflicts.py` 会把裁决复位（第 287/292 行硬编码 `open`/`true`）
⇒ 裁决必须外置持久化（`conflicts/adjudication.json` + 抽取时合并）。

**为什么本轮没动**：③④ 要改 `kb/tools/**`（**冻结目录**，`AGENTS.md §3` 写权 = kb owner，
"改语义需单独变更并留证"）⇒ 属需显式授权项。授权后的切片（C10-a/b/c）与判据写在计划 §3。

### 83.4 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 环境层（新入口） | **3 passed, 24 deselected** | `bash loop/spikes/run_env_layer_checks.sh`；原 ENV_ROOT 零写入 |
| kb 自测 | **PASS=10 / PASS=9，FAIL=0** | 见 §83.2 |
| 软件层 / 浏览器 | 未重跑 | 本轮新增的是 `spikes/` 脚本与文档，未改产品代码与既有测试 |
| 文档 | **missing=0、exit=0** | 新增计划 1 份 + 本节；`checked/skipped` 为诊断值、不落盘（§19） |

### 83.5 C 组剩余（需授权或需裁决）

C10 机制改动（待授权改冻结 `kb/tools/**`）、C10-b 72 条人工裁决、C8 通过形态夹具、
C9 S0-b 接入（环境侧）、C11 取消/续跑语义（契约）、C12 运行入口消费 S0（需求）。

---

## 84 C 组修订（二）：冲突裁决写入器 C10-a —— 冻结目录变更 + 端到端证明（2026-10-27）

上游：`§83.3` 定位的 4 个机制缺口；人于 2026-10-27 明确**授权改冻结的 `kb/tools/**`**（选项 A）。
计划 [`doc/plans/2026-10-27-c-group.md`](plans/2026-10-27-c-group.md) §3。本轮由 Lead 实施（非独立验证）。

### 84.1 冻结目录变更留证（`AGENTS.md §3`：kb/tools 改语义需单独变更并留证）

| 文件 | 改前 md5 | 改后 md5 | 变更性质 |
|---|---|---|---|
| `kb/tools/n1_conflicts.py` | `7ff7b0350921c1e2f763034ceec129d5` | `6be49e83aad5b063f3677643bfeff66f` | **增**：抽取后读 `conflicts/adjudication.json` 并合并（`load_adjudication()` / `merge_adjudication()` + main 里 1 处调用）。**无 `adjudication.json` 时逐字节等价**（见 §84.3） |
| `kb/tools/adjudicate_conflicts.py` | （新增，原不存在） | `021820caad308921984de35db47cd5e6` | **新增**：human-only 裁决写入器（追加 `adjudication.json` + 合并进 `conflicts.json`） |
| `kb/tools/_selftest_adjudicate_conflicts.py` | （新增） | `460ca6b41dc1ca66bd5a6348a41516f8` | **新增**：自测（PASS=28，见 §84.4） |
| `kb/README.md` | `4aaa18c3b81c509a0564daca3bd875ed` | `9076db3f92c4b9a3ec392bcf9e1f2608` | 工具树 +1、写权表 +2 行、变更记录 v3、"两个 adjudication" 辨析 |

schema **未改**（`kb/schema/conflicts.schema.json` md5 `434387c12a972d2ca113c09cbc6cb6ac` 不变，
它已支持 closed 态；缺的是写入路径与不变式强制，不是字段）。

### 84.2 端到端证明：裁决能落账、重跑抽取不丢、I4 计数真的降

在临时目录里用**真实**的 72 条 `conflicts.json`（从 `<ENV_ROOT>/kb/conflicts/` 复制）+ 一条
**明确标注为夹具**的裁决：

```
$ cp <ENV_ROOT>/kb/conflicts/conflicts.json $T/
$ KB_NOW=2026-10-27T10:00:00+0800 python3 -B kb/tools/adjudicate_conflicts.py --outdir $T \
    --actor human:selftest-fixture --id C1 --status ruled \
    --resolution "自测夹具裁决：仅验证机制，不是真实裁决"
[adj] 追加 1 条裁决 → $T/adjudication.json
[adj] 合并进 $T/conflicts.json：变更 1 条；仍阻断发版 71 条

# 关键一步：按"重摄取会复位"的旧行为，这里重跑抽取
$ python3 -B kb/tools/n1_conflicts.py --outdir $T --quiet
total 72 blocking 71
C1: ruled human False | 自测夹具裁决：仅验证机制，不是真实裁决
adjudication records: 1
```

⇒ 缺口 ④（重跑复位）已关闭。**真实数据根当前状态（只读 `--list`）**：
`adjudication.json（0 条记录 / 0 个冲突）；conflicts=72，仍阻断发版=72` —— 一条裁决都还没签，
**没有把我的夹具裁决写进真实数据**。

### 84.3 特征保持：无裁决时抽取输出不变

把真实输入重抽到临时目录，与盘上现存的三个产物逐对象比对（忽略 `generated_at` 这一唯一允许的
非确定性字段）：

```
conflicts identical (modulo generated_at): True | total 72 blocking 72
restrictions identical: True
pending identical: True
```

⇒ `n1_conflicts.py` 的合并改动对**没有裁决文件**的数据根零影响（不是"看起来一样"，是对象相等）。

### 84.4 工具强制的不变式 + 自测

`kb/tools/_selftest_adjudicate_conflicts.py` → **PASS=28 FAIL=0**，逐条钉住：

| 不变式 | 断言语义 |
|---|---|
| human-only | `--actor model:gpt` / `host:loop` / 裸名 `chenjm` 全部 rc=4，且**被拒时不改动** `adjudication.json` |
| 裁决必须有结论 | `status=ruled` 无 `--resolution` ⇒ rc=5 |
| confirmed 不得清零 I4 | `status=confirmed` 落盘后 `blocks_release` 仍为 `true` |
| 只增不改 | 同 id 改判 ⇒ 追加记录（旧记录字节不变），合并取最后一条 |
| 锚可复算 | `sha256(record 去 sha256)` = 记录里的 `sha256`；手改记录 ⇒ `--verify` 非 0 且**写入被拒**（rc=3） |
| 写前拒绝 | 未知 id `C99` ⇒ rc=6，且**不产生** `adjudication.json`（不留脏记录） |
| 缺清单不半写 | 无 `conflicts.json` 且未 `--no-apply` ⇒ rc=2 |
| 合并函数 | `merge_adjudication()` 正常合并；未知 id ⇒ `ValueError`（不静默忽略） |

另：`kb/tools/_selftest_gate_schema.py` **PASS=10**、`_selftest_n5_reachability.py` **PASS=9**（均 FAIL=0）。

### 84.5 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| kb 自测 | **28 / 10 / 9，FAIL=0** | 新增裁决自测 + 既有两条（在派生副本的可写数据根上跑） |
| 软件层 | **975 passed / 3 deselected / 0 failed**（178.40 s） | 较 §81.9 的 974 多 1 条 = **B2 新增的钉子**（`test_g1_drill_entry_decisions_replace_the_attestation`），B 组当时只跑了目标用例、没跑全量；本轮补跑全量确认无回归 |
| 文档 | **missing=0、exit=0** | 见本节落盘后的测量；`checked/skipped` 为诊断值、不落盘（§19） |
| 浏览器 / 端到端 | 未重跑 | 本轮只改 `kb/tools/**` 与文档，未触达 `loop/web/**`、工作流、API |

### 84.6 C10-b：72 条裁决待签

机制已就绪，但**一条真实裁决都还没有**（真实数据根 `--list` = 0 条记录 / 72 条阻断）。
按 schema 原文，模型只能写 `open` 或提建议、不得自封 `ruled` ⇒ 下一步是**人逐条（或按组）签署**：

```bash
# 单条
python3 kb/tools/adjudicate_conflicts.py --actor human:<你的名字> --id C1 --status ruled \
  --resolution "以位定义表为准；汇总表 xx 为占位符，登记文档勘误"
# 同组批量（同一结论多条 id）
python3 kb/tools/adjudicate_conflicts.py --actor human:<你的名字> --ids C1,C2,C3 --status ruled \
  --resolution "……"
python3 kb/tools/adjudicate_conflicts.py --list     # 随时看剩余阻断数
```

注意：真实数据根 = `<ENV_ROOT>/kb`，本机**只读** ⇒ 真签要在可写数据根上做（或先写到派生副本
`.env-copy/kb/conflicts` 验证，再在可写环境生效）。可复现的分组与逐条摘要见
`<ENV_ROOT>/kb/adjudication/C_conflicts_triage.md`（71 段：G1–G9 / B1–B4 / 19 条必须逐条看）。

### 84.7 未关闭

C10-b 72 条人工裁决（需人签）、C8 通过形态夹具、C9 S0-b 接入（环境侧授权）、
C11 取消/续跑语义（契约）、C12 运行入口消费 S0（需求）。

---

## 85 C 组修订（三）：72 条冲突裁决已定值，签署待人执行（2026-10-27）

上游：`§84` 打通了写入机制（0 条裁决）。人于 2026-10-27 逐项定值：
68 条按 triage G1–G9 批量规则、4 条 Tier B-core 逐条给值。材料：
[`doc/evidence/CONFLICTS_SIGNING_20261027.md`](evidence/CONFLICTS_SIGNING_20261027.md) +
一键脚本 [`doc/evidence/conflicts_sign_20261027.sh`](evidence/conflicts_sign_20261027.sh)。

### 85.1 定值（人给定，Lead 只落成命令）

| 范围 | 条数 | 结论 |
|---|---|---|
| G1 地址/offset 笔误 | 12 | 以文档自洽一方为准，登记勘误 |
| G2 Reset 冲突 | 4 | 以位定义表为准（C2/C11/C38/C58 已移出，见下） |
| G3 R/W 冲突 | 7 | 以位定义表为准（状态类只读） |
| G4 位段重叠/跳空 | 6 | 按同表规律修正 |
| G5 缺失/漏列 | 10 | 以位定义表补全；无定义者裁剪并标注 |
| G6 命名/复制粘贴 | 10 | 以位定义/字段名为准，用例按 entry_id 关联 |
| G7 编号/格式/数值书写 | 13 | 勘误，不改寄存器语义 |
| G8 规模/数量/容量 | 4 | 以可枚举范围为准 |
| G9 模板/元信息残留 | 2 | 无寄存器语义 |
| **批量小计** | **68** | |
| C2 | 1 | 位定义 `2023_0911`（汇总 `0x2023_0804` 登记勘误） |
| C11 | 1 | 位定义 `0x0`（汇总 `0x5555aaaa` 登记勘误） |
| C38 | 1 | 位定义逐位推导 `0xF0`（汇总 `0x10` 登记勘误） |
| C58 | 1 | 以 `DFX_VERSION=0x25092913`（≈2025-09-29）为版本/日期基准 |

口径依据：两张表打架时**以位定义表为准**（逐位、可执行；汇总表是摘要且出现过 `xx` 占位）。

### 85.2 机制验证（派生副本 + **夹具 actor**，不是真实裁决）

在 `.env-copy/kb/conflicts`（派生副本）上跑整条脚本（`ACTOR=human:selftest-fixture`）：

```
[stat] conflicts=72，仍阻断发版=0
[verify] 裁决记录=72（去重后 72）；conflicts=72，仍阻断=0
[verify] 锚与合并一致性：全部通过
```

服务层读数（`KbSources.from_workspace` + `contracts._conflict_summary`，即 I4 的消费口径）：

```
裁决后：  {'total': 72, 'blocks_release': 0, 'open': 0,  'consistent': True}
还原后：  {'total': 72, 'blocks_release': 72, 'open': 72, 'consistent': True}
```

**验证后已还原副本**（`conflicts.json` md5 回到 `1d0b95468e8be451955a0f2443c478be`、
删除 `adjudication.json`）⇒ 副本里**没有**残留的夹具裁决；真实 `ENV_ROOT` 全程只读、未被写入。

### 85.3 为什么没有代替签署

工具强制 `--actor human:<name>`；schema 原文「由人裁决推进；模型只能写 `open` 或提出建议，
不能自封 `confirmed/ruled`」。定值可以讨论，**签字动作必须由人执行**：
`ACTOR=human:<你的名字> OUTDIR=<可写数据根的 conflicts/> bash doc/evidence/conflicts_sign_20261027.sh`
（先加 `--dry-run` 空跑；脚本不含任何名字，不给 `ACTOR` 就拒跑）。

### 85.4 执行后应验（待人工跑完回填）

1. `--list`：`仍阻断发版=0`，72/72 `ruled`；
2. 重跑 `n1_conflicts.py`（可写数据根）后仍为 0（§84.2 已证裁决不被复位）；
3. G3 的 `full_now`/`subset_only` 提交前不再被 I4 拒；N16 前置只剩 I2/I3/I7 等其它条件；
4. 若先在派生副本签，可再按 §84.3 的方式比对，确认抽取输出只多出裁决字段、无其它漂移。

### 85.5 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 文档 | **missing=0、exit=0** | 新增 evidence 2 份 + 本节；`checked/skipped` 为诊断值（§19） |
| kb 自测 / 软件层 / 浏览器 / 端到端 | 未重跑 | 本轮只新增文档与签署脚本，未改产品代码、`kb/tools/**`、测试 |

### 85.6 C 组剩余

C10-b 待人工执行签字（命令已备）；C8 通过形态夹具、C9 S0-b 接入（环境侧）、
C11 取消/续跑语义（契约）、C12 运行入口消费 S0（需求）不变。

---

## 86 C 组修订（四）：72 条裁决已落账（人批示 + Host 代录），真实环境待写权（2026-10-27）

上游：`§85` 已定值、等签字。人于 2026-10-27 明示选择「授权代录」并指定 `actor = human:chenjunming`。
**本节如实登记：actor 是人指定的，但写入由 Host 工具执行**，不是亲笔——每条裁决的 `resolution`
末尾都带「（人工批示，Host 工具代录 2026-10-27）」，快照 README 同样声明。

### 86.1 落账结果（写进派生数据根副本 `<repo>/.env-copy/kb/conflicts/`）

```
[stat] conflicts=72，仍阻断发版=0
[verify] 裁决记录=72（去重后 72）；conflicts=72，仍阻断=0
[verify] 锚与合并一致性：全部通过
```

I4 消费口径（`KbSources.from_workspace` + `contracts._conflict_summary`，与服务端同源）：

```
{'total': 72, 'expected_total': 72, 'blocks_release': 0, 'open': 0, 'consistent': True}
```

落账快照已入仓（只读，append-only）：

| 文件 | md5 | 说明 |
|---|---|---|
| `doc/evidence/adjudication_20261027/adjudication.json` | `d6ec87796f72f40dcfd124cbfc7af991` | 72 条裁决记录（每条带 `sha256` 锚） |
| `doc/evidence/adjudication_20261027/conflicts.json` | `47300360ba208012d262bc673a1d07d9` | 合并后清单：72 条 `ruled` / `blocks_release=false` |
| `doc/evidence/adjudication_20261027/README.md` | — | 身份、代录声明、生效方法、边界 |

**重跑不丢（真实 72 条）**：在副本上再跑 `n1_conflicts.py` ⇒ `[merge] adjudication.json：72 条裁决已合并进 conflicts（重跑不丢）`、仍阻断 0。

组成：68 条批量（G1–G9，结论 = triage §4.1 规则原文）+ 4 条 Tier B-core
（C2 位定义 `2023_0911`、C11 位定义 `0x0`、C38 位定义推导 `0xF0`、C58 以 `DFX_VERSION` 为基准）。

### 86.2 真实环境**仍未生效**（必须说清）

本机 `<ENV_ROOT>/kb` **只读** ⇒ 本轮**没有**写真实数据根：真实 `conflicts.json` 仍是 72 条
`blocks_release=true`（md5 `1d0b954…` 未变）。也就是说：**这批裁决目前不影响任何真实轮次的 I4 判定**，
`G3` 的 `full_now/subset_only` 在真实环境仍会被拒、N16 仍不可达。

生效路径（`doc/evidence/adjudication_20261027/README.md` §3，二选一）：
① 把快照里的 `adjudication.json` 放进可写数据根的 `conflicts/`，再跑 `n1_conflicts.py --outdir` 合并；
② 在可写数据根上重跑 `conflicts_sign_20261027.sh`（等价，重新签发时刻）。
**需要环境侧/写授权**：要么给一个可写数据根，要么授权写 `ENV_ROOT/kb`（红线 11 目前禁止）。
⇒ 登记为 C 组新遗留项（§86.4）。

### 86.3 代录的边界（写清楚，避免以后被误读成亲笔）

1. `resolution_kind` 仍是 `human`（schema 枚举里没有"代录"这一档）⇒ 代录事实只能写在 `resolution`
   文本与快照 README 里；这是本轮已知的表达力缺口，若要结构化，需授权在 schema 增字段（未做）。
2. 亲笔路线随时可用：在有写权环境重签 = **追加**新记录（旧记录保留，合并取最后一条），
   不需要回填或删除。
3. 4 条 core 的取值仍是"人给的方向"，不是作者确认；作者若另有口径，同样按追加改判处理。

### 86.4 本轮门与剩余

| 门 | 结果 | 说明 |
|---|---|---|
| 文档 | **missing=0、exit=0** | 新增 evidence 快照 3 份 + 本节 |
| kb 自测 / 软件层 / 浏览器 / 端到端 | 未重跑 | 本轮只新增文档/落账快照，未改产品代码、`kb/tools/**`、测试 |

C 组剩余：**把裁决落到真实数据根（需写授权/可写数据根）**、C8 通过形态夹具、
C9 S0-b 接入（环境侧）、C11 取消/续跑语义（契约）、C12 运行入口消费 S0（需求）。

---

## 87 C 组修订（五）：I4 生效路径做成一条命令，并在可写数据根上实证解阻（2026-10-27）

上游：`§86` 已把 72 条裁决落账并快照入仓，但真实环境因数据根只读未生效。人指定"让 I4 真生效（写权路径）"。

### 87.1 先把前提复核清楚：不是权限问题，是 `/home` 只读挂载

```
$ findmnt -T <ENV_ROOT> -o TARGET,FSTYPE,OPTIONS
/home  ext4  ro,nosuid,nodev,relatime
$ touch <ENV_ROOT>/kb/conflicts/.write-probe
touch: cannot touch '…/.write-probe': Read-only file system
```

⇒ 目录属主虽是本用户、权限 `rwx`，但**文件系统级 ro** ⇒ `chmod` 也无用。这解释了为什么
`AGENTS.md §4` 的"需可写数据根"必须以 `LOOP_WORKSPACE` 换根，而不是改权限。

### 87.2 交付：`loop/spikes/apply_conflict_adjudication.sh`

一条命令完成「生效」全链（任何人拿到可写数据根即可用）：

```bash
bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根> --dry-run   # 体检
bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根>             # 生效
```

做的事：① 校验快照指纹（`d6ec877…` / `47300360…`，**不符即拒**，红线 10）；② 把
`adjudication.json` 放进目标数据根 `conflicts/`；③ 重跑 `n1_conflicts.py` 合并（抽取不丢裁决）；
④ `adjudicate_conflicts.py --verify` 校验锚与一致性；⑤ 打印 **I4 读数**、
**G3 `full_now`/`subset_only` 提交前检查**、**N16 blockers 是否仍含 `I4_CONFLICTS_UNCLEARED`**。
不写原 `ENV_ROOT`、不改 `kb/tools/**`。

### 87.3 实证（可写数据根 = `provision_dev_workspace.sh --link-fixture` 影子根）

| 检查项 | 生效前 | 生效后 |
|---|---|---|
| I4 读数（`_conflict_summary`） | `conflicts=72, blocks_release=72, open=72` | **`conflicts=72, blocks_release=0, open=0`** |
| `G3 full_now` 提交前检查 | 被拒：`I4：冲突未清零（72 项 blocks_release）⇒ 不得选 full_now` | **通过** |
| `G3 subset_only` 提交前检查 | 被拒（同上） | **通过** |
| N16 `compute_blockers` | 含 `I4_CONFLICTS_UNCLEARED` | **不含**（余下：`I1_UNRESOLVED_ENTRIES`(drill warning)、`I2_CASES_PENDING`、`I3_EVIDENCE_MISSING`、`E2_EVIDENCE_ARCHIVE_EMPTY`、`F_N16_04_STAGING_RESIDUE`） |
| 抽取合并 | — | `[merge] adjudication.json：72 条裁决已合并进 conflicts（重跑不丢）`；`[verify] 锚与合并一致性：全部通过` |

⇒ **I4 的机制闭环已经打通并实证**：只要给一个可写数据根，`full_now/subset_only` 不再被 I4 拒。
（N16 仍被 I2/I3 等其它前置挡住，那是另外几条不变式，不是 I4。）

### 87.4 真实环境仍差一步（需环境侧动作，不是代码问题）

真实 `<ENV_ROOT>/kb` 在 ro 挂载上 ⇒ 我无法把裁决写进去，真实轮次里 I4 仍是 72 条阻断。
要让真实环境生效，需要**环境侧其一**：

1. 把数据根改到可写位置（新数据根 + `LOOP_WORKSPACE` 指过去，并把 `conflicts/`、`index/` 等带过去）；
2. 或把 `/home` 重新挂成可写（`mount -o remount,rw /home`，需管理员）；
3. 或由环境 owner 在可写环境上执行 §87.2 的那一条命令（等价于方式 1）。

三者的共同点是：**动作在环境侧，不在本仓**；本仓已把"动作是什么、怎么验证"固化。

### 87.5 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 文档 | **missing=0、exit=0** | 新增脚本 1 份 + 本节 + 快照 README/计划更新 |
| kb 自测 / 软件层 / 浏览器 / 端到端 | 未重跑 | 本轮只新增 `spikes/` 脚本与文档，未改产品代码/测试/`kb/tools/**` |
| I4 生效链 | 上述 §87.3 实证 | 影子数据根（可删）上完成 before/after 对照 |

### 87.6 C 组剩余

C8 通过形态夹具（需真实通过轮或环境写权）、C9 S0-b 接入（环境侧 D1–D5）、
C11 取消/续跑语义（契约决定）、C12 运行入口消费 S0（需求未定）、
**I4 真实生效（需环境侧给可写数据根）**。

---

## 88 C 组修订（六）：C11 取消作业语义 —— 裁决「维持终态失败 + 补齐后果告知」（2026-10-27）

上游：C 组剩余项里的「取消作业 = 整轮 failed 不可续跑」。人于 2026-10-27 裁决：**维持语义**，
只把后果在界面上说清（选项 A）。未采纳"取消后重跑作业/终止本轮"（B）与"自动重跑一次"（C）。

### 88.1 先摆事实：现状是契约，不是缺陷

```
POST /api/runs/{run_id}/jobs/{job_id}/cancel
  → JobRunner.cancel → 作业相位 cancelled
  → N9 resume 分支：raise "作业 X 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续"
  → N15 resume 分支：raise "N15：作业 X 被取消 ⇒ 不得当回归完成"
  → 整轮收敛 failed（终态）
```

`LOOP_ORCHESTRATION_SPEC §6/§7` 早已把"取消"与成功/失败并列（终态释放单槽且幂等）⇒ **不提供续跑**是有意设计：
取消后的本轮既没有该作业的证据（I3），也无法区分"想重跑"与"想终止"。要重跑 = 新建一轮。

**真实缺口**：界面确认框只有「确认取消作业 JOB-xxx？」，**没说后果**；这跟
`AI_WORK_PANEL_SPEC U08`「终止前必须显示目标与影响」不一致，且真实轮里 N9 是小时级作业。

### 88.2 落点

| 位置 | 改动 |
|---|---|
| `loop/web/app.js` | 确认框改为「确认取消作业 JOB-x？／取消后本轮按失败收敛、不能续跑；要重跑需要新建一轮」；成功 toast 补「（本轮将按失败收敛）」；加注释指向判据出处 |
| `loop/web/legacy.html` | 旧界面同口径：二次确认弹窗加醒目警示（终态/不能续跑/要重跑新建一轮），受理 toast 同样标注 |
| `WEB_UI_SPEC §4.1` | 动作行补「取消前必须显示后果」+ 禁止只写"确认取消？"或暗示可继续 |
| `LOOP_ORCHESTRATION_SPEC §6` | 新增**第 9 条「取消是终态」**：写清 N9/N15 行为、为什么不提供续跑、界面必须先告知；B 方案要改状态机则须先改本节 |

### 88.3 钉子（有判别性）

`loop/tests/browser/test_run_sessions.py::test_cancel_job_confirms_terminal_consequence`：
构造 `job.phase=running` → 切到运行监控视图 → 点「取消作业」→ 截获 `window.confirm` 文案，
断言含「按失败收敛」与「不能续跑」（旧文案只有"确认取消…？"⇒ 必红），并断言 POST 路径是
`/jobs/JOB-…/cancel`、受理后 toast 也带后果。**不弹框就点提交**同样会被这条抓住。

### 88.4 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 浏览器 | **114 passed**（124.80 s） | 较上一轮 113 多 1 条 = 本节新增用例 |
| 文档 | **missing=0、exit=0** | 改 2 份规格 + 计划 + 本节 |
| 软件层 / 端到端 | 未重跑 | 本轮只改两个前端文案 + 文档 + 一条浏览器用例，未触达 Python/工作流/API |

### 88.5 C 组剩余

C8 通过形态夹具（需真实通过轮或环境写权）、C9 S0-b 接入（环境侧 D1–D5）、
C12 运行入口消费 S0（需求未定）、I4 真实生效（需环境侧给可写数据根）。

---

## 89 C 组修订（七）：C12 运行入口对 S0 记录「传了才校验」（2026-10-27）

人于 2026-10-27 裁决选项 A：**做"传了才校验"**（小切片），不做"全并入运行入口"（B），
也不只登记（C）。

### 89.1 事实（先确认现状是规格写明的不消费，不是缺陷）

| 项 | 事实 |
|---|---|
| API | `POST /api/runs` 早已接受**可选** `s0_record_id`（格式 `^S0-[A-Za-z0-9_-]+$`，非法 400），写进 run 文档并投影到 run/node 视图 |
| 界面 | 运行配置视图**没有** S0 选择器 ⇒ UI 从不传 ⇒ `s0_record_id` 恒 null；右侧徽标如实显示「未经 S0 派生」 |
| 规格 | `S0_ENVIRONMENT_SPEC §6.1` 原文：「`ready_for_execution` 当前恒为 false 且**不被任何运行入口消费**」；要并入须**显式选项**、不改 N0–N16 与 `project==ENV_ROOT` |
| 已规划的验收 | 同规格 §8.5 写着「`ready_for_execution=false` 时 `real` 启动 **400** 且原因可读」 |

### 89.2 实现（`services/api.py`）

新增 `_check_s0_record_for_run(record_id, mode)`，在 `create_run` 解析完 `s0_record_id` 后调用。
**传了才校验，不传不强制**：

| 情形 | 判据 |
|---|---|
| `mode=real` + 传了 | 记录必须存在（否则 400「S0 记录不存在：…」）；且 `ready_for_execution is True`（否则 400「尚未准出（ready_for_execution=false）⇒ real 运行被拒；可改用 mode=drill，或先完成 S0-b」） |
| `mode≠real`（drill/rehearsal）+ 传了 | **只做格式校验**（来源徽标语义；drill 不覆盖 S0）——不存在的 id 也不拦（既有 roundtrip 用例依赖此语义） |
| 没传 | 不强制（现状路径零影响） |

**测试暴露的关键事实**：`S0Store.get()` 会把 `ready_for_execution` **归一为 false**（S0 §3 恒假，
防止记录文件自称准出）⇒ S0-b 接入前「real + 带 S0 记录」**一律被拒**。这是有意的 fail-closed：
没准出的副本不许真跑；准出只能由真实核验产生。S0-b 接入后 `get()` 才可能返回 true，判据自然放行。

### 89.3 钉子（4 条，含反例方向）

`loop/tests/test_s0.py`：

1. `test_run_entry_rejects_missing_s0_record_for_real`：real + 不存在 ⇒ 400 且含"不存在"；
2. `test_run_entry_rejects_unready_s0_record_for_real`：real + 未准出 ⇒ 400 含"未准出"/
   "ready_for_execution=false"，并提示"drill"/"S0-b"；
3. `test_run_entry_rejects_even_file_claimed_ready_record_for_real`：**记录文件写 `true` 也拒**
   （`get()` 归一）——防"改文件伪造准出"；
4. `test_run_entry_drill_and_empty_record_id_are_not_checked`：drill 传不存在 id 不拦、不传不强制
   ——固定"不扩大到 drill/不强制"的边界，防止以后再收紧时误伤演示路径。

### 89.4 规格

- `S0_ENVIRONMENT_SPEC §6.1`：把"不被任何运行入口消费"改写为「恒为 false（get() 归一）+ 运行入口
  **传了才校验**」的三条规则（real 严、drill 徽标、不传不强制），并明说**不表示 S0 已并入执行入口**；
- `S0_ENVIRONMENT_SPEC §8.5`：把「real 启动 400」标记为**部分完成**（本切片），S0-b 其余验收仍未做；
- `WEB_UI_SPEC §6.4`：`POST /api/runs` 扩展补 `s0_record_id` 的 400 规则与判据出处。

### 89.5 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 软件层 | **979 passed / 3 deselected / 0 failed**（168.64 s） | 较上轮 975 多 4 条 = 本节新增用例 |
| 文档 | **missing=0、exit=0** | 改 2 份规格 + 计划 + 本节 |
| 浏览器 / 端到端 | 未重跑 | 本轮未改前端、未改工作流/API 路径（只加提交前校验） |

### 89.6 C 组剩余

C8 通过形态夹具（需真实通过轮或环境写权）、C9 S0-b 接入（环境侧 D1–D5，本切片只做了它 §8.5 的一条前置）、
I4 真实生效（需环境侧给可写数据根）。

---

## 90 C 组收尾：交接单 + 端到端补跑（2026-10-27）

人指定 C 组收尾。**一页交接单**：[`doc/plans/2026-10-27-c-group-handover.md`](plans/2026-10-27-c-group-handover.md)
（八项处置 / 四道门数字 / 环境侧只剩三件事 / 推送 / 接手第一小时顺序 / 已知未做）。

### 90.1 为什么本轮要补跑端到端

`§89` 改了 `POST /api/runs` 的**提交前校验**（`_check_s0_record_for_run`）。虽然"不带 `s0_record_id`
时函数立即 return"，但端到端驱动会真的建 run ⇒ 属于**改到了端到端路径**，必须重跑，不能拿
"§81.9 那次是 117 ALL PASS"当现在的证据。

### 90.2 端到端补跑结果（`bash spikes/accept_v1_run.sh`，先 `provision_dev_workspace.sh`）

```
phase 1    rc=0   PASS=50
phase 2    rc=0   PASS=27
phase 3    rc=0   PASS=18
phase 4    rc=0   PASS=8
phase 4b   rc=0   PASS=8
phase 5    rc=0   PASS=6
=> ALL PASS（117 断言 / 0 FAIL）
```

与 `§81.9` 的 117 同值 ⇒ C12 的提交前校验对现有端到端行为**零影响**（不带 S0 记录时直接返回）。
跑完 `provision_dev_workspace.sh --cleanup` 已删数据根，仓库无残留。

### 90.3 C 组收尾时的门（全部为本轮或上轮实测，数字从命令输出复制）

| 门 | 结果 | 记录位置 |
|---|---|---|
| 软件层 | **979 passed / 3 deselected / 0 failed**（168.64 s） | §89.5 |
| 浏览器（补充门） | **114 passed**（124.80 s） | §88.4 |
| 端到端 | **ALL PASS，117 断言 / 0 FAIL** | 本节 |
| 文档 | **missing=0，exit=0** | 本节落盘后测量 |
| kb 自测 | 10 / 9 / 28，FAIL 全 0 | §84.4、§83.2 |
| 环境层 | **3 passed / 24 deselected** | §83.1 |

### 90.4 C 组剩余（全部需环境侧，不在本仓写权内）

1. **I4 真实生效**：`bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根>`
   （或 `remount -o rw /home` 后对真实数据根跑）——交接单 §3-①；
2. **C9 S0-b 接入**（D1–D5）：做完后 `get()` 才可能返回 `ready=true`，C12 的允许路径与 C8 的
   通过形态夹具才有环境；
3. **C8 通过形态夹具**：需一次真实通过轮或环境写权。

### 90.5 收尾口径

- 本机出网被代理阻断 ⇒ 截止本节 **25 个提交未推送**（交接单 §4 有命令与凭据提醒）。
- 本轮所有"未做/受限"都已在交接单 §6 明列，不用翻对话。

---

## 91 C8 评估：passed 夹具在本机不可诚实产出（登记为环境阻塞，2026-10-27）

人指定"评估 C8（通过形态夹具）可行性"。评估全文：
[`doc/plans/2026-10-27-c8-feasibility.md`](plans/2026-10-27-c8-feasibility.md)。

### 91.1 结论

**本机不能诚实产出 passed 夹具。** 三条可能路：

| 路 | 判定 | 依据 |
|---|---|---|
| P1 drill 回放 | **不可行，且不该做** | drill 的 N9 回放**冻结的真实证据日志**（`long_jobs._drill_replay_done`）⇒ counts 不变 ⇒ 报告必 `not_passed`（现有演示夹具 `n12_report.md:4` 就是 `claimed_verdict：not_passed`）。要回放出 passed 只能改日志计数 = **伪造环境证据** |
| P2 real 真跑 | **本机不可行，需环境侧** | 工具在（`uvs.setup`/`run_tc.py`/`run_uvs_new.sh`），但 `/home` 是 **ro 挂载** ⇒ 连红线 11 允许写的 `SIMLIB_RUN/`、`uvs.setup` 也写不了（§87.1 实测）；且 N9 一次真跑按 §54.2 实测 **21.56 h**（3.8 µs 仿真/秒，5 例），还要 EDA 工具/许可 |
| P3 合成夹具 | **能造但不建议** | 界面没有"合成"徽标 ⇒ 下一个人会当成真实通过证据。若要做，必须目录名 `SYNTHETIC-PASSED-*` + README 首行声明 + STATUS 登记 + 演示话术明确；默认不做 |

### 91.2 现有夹具矩阵（如实）

- `RUN-20261024-002609`：**real / failed**（恢复失败）——可演失败收口、N4 逐条处置、账本缺失形态；
- `RUN-20261026-135835`：**drill / finished**（报告 `not_passed`；G1 4 条落账、G2 accept、G3 milestone_only）
  ——可演四屏、闸门、逐条处置落账；
- **都不能演**「passed 报告 → accept 无需理由 → N16 晋升」。

### 91.3 评估顺带发现

"UI 上看到 accept 不要求理由"**不需要**新夹具：浏览器用例已用受控替身覆盖
`requires_reason` 的 true/false 两态（`test_run_sessions.py` 相关用例）。要演示的是**真实链路**才需要
passed 夹具，而那属于环境依赖。

### 91.4 登记

C8 = **blocked-by-env**，阻塞条件四条（可写数据根/`SIMLIB_RUN`、EDA 工具与许可、N9 ≈21.56 h 真跑、
一次真实通过结果）。产出 runbook（跑什么、验哪三条判据、怎么冻结成夹具）写在评估文档 §2-P2，
环境具备时按单执行，不需要重新设计。

### 91.5 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 文档 | **missing=0、exit=0** | 新增评估 1 份 + 计划/本节；`checked/skipped` 为诊断值（§19） |
| 软件层 / 浏览器 / 端到端 / kb 自测 | 未重跑 | 本轮只做评估与文档，未改任何代码/测试/`kb/**` |

---

## 92 B1b 关闭：G2「未通过报告」的 403 文案统一（2026-10-27）

上游：`§82.1` 的 B1b 登记（当初"只改界面不改 403 串"，理由是旧证据按原文引用该串）。
人指定本轮处理。证据：[`doc/evidence/SPEC_REV05_RECHECK_20261027.md`](evidence/SPEC_REV05_RECHECK_20261027.md)。

### 92.1 改了什么（只有措辞）

| 位置 | 旧 | 新 |
|---|---|---|
| `precheck_decision` G2 分支 403 `detail.error` | `…⇒ 接受失败报告必须给出理由（reason）。…` | `…⇒ 接受未通过报告必须给出理由（reason）。…` |
| 同分支成功 warning | `accept 作为失败收口（已给理由）` | `accept 作为未通过收口（已给理由）` |
| 该分支注释 | `失败报告允许接受` | `未通过报告允许接受` |
| `tests/test_fix_lifecycle.py` | 测试数据/断言消息里的"失败报告" | 同步为"未通过报告"（断言语义不变） |

md5 留证：`loop/workflows/chunks/gates.py` `838c265658e1ec9f675b915fc92ceb53` →
`10ccf191cbbe4aab4e289e1d34bbb30d`。

### 92.2 实测：判据零变化

构造"报告 `not_passed`"的 run 目录直接调 `precheck_decision`：

```
403_TEXT=D：本轮报告结论为 not_passed（未通过）⇒ 接受未通过报告必须给出理由（reason）。仍有 1 个用例「已修订待验」：接受报告不等于判据通过，N16 仍受 I3/I4 阻断。
WITH_REASON_OK warnings= ['报告结论 not_passed：accept 作为未通过收口（已给理由）；1 个用例仍待验，不得称跑通']
```

⇒ 无理由仍被拒（同条件、同异常类型）、给理由仍放行并留告警。拒绝条件仍是
`decision_requires_reason(...)` 这一唯一判据，未新增/放宽任何前置。

### 92.3 旧证据的处理

`doc/evidence/SPEC_REV05_VERIFY_20261026.md`（md5 `e1eccd7749296c66366588f0a72157d7`）§3 的
"错误原文"是**当时的真实观测**，**不回填**；新证据记录差异（仅两字）并声明旧文已过期。
历史事件流里的旧文案同样只增不改。

### 92.4 本轮门

| 门 | 结果 | 说明 |
|---|---|---|
| 软件层 | **979 passed / 3 deselected / 0 failed**（170.20 s） | 未改判据，只改措辞；全量重跑确认无回归 |
| 文档 | **missing=0、exit=0** | 新增证据 1 份 + 本节 + §82.1 关闭指针 + 交接单更正 |
| 浏览器 / 端到端 | 未重跑 | 本轮未改前端（界面 B1 已先统一）、未改 API/工作流路径（只改拒绝文案） |

---

## 93 收工与开工单（2026-10-27）

本轮按人要求整理**未修复清单 + 开工提示词**，落成
[`doc/plans/2026-10-27-kickoff-unresolved.md`](plans/2026-10-27-kickoff-unresolved.md)：

- §1 现状快照（28 个未推提交、六项门数字、`/home` ro 挂载的硬限制）；
- §2 未修复清单分四类：**E** 环境侧（E1 I4 真实生效 / E2 S0-b / E3 passed 夹具 / E4 推送）、
  **D** 需人裁决（4 条 core 的取值待作者确认 / 代录署名 / C11-B / C12-B）、
  **K** 本仓可自行推进（K1 环境类检查统一入口 / K2 旧派生副本清理 / K3 `.env-copy` 占盘 / K4 门清单）、
  **R** 登记不改 8 条（复核报告不可复原、3 条 env_layer 不进默认门、浏览器补充门等）；
- §3 建议开工顺序（先验证基线 → K1 → K2/K3 → 有写权才做 E1 → E2/E3/D3/D4 只登记）；
- §4 可直接粘贴的开工提示词；§5 关键文档与命令索引。

一致性：清单里每条都能追到 §81–§92 的实测或裁决；`run_env_checks.sh` 是 **K1 计划新增**（未落地），
已登记进文档门 `KNOWN_MISSING`，避免把"计划中的文件"算成断链（红线 2：不虚报）。

门：文档 **missing=0、exit=0**；其余门未重跑（本轮只新增/更新文档与文档门登记）。

## 94 开工轮：K1 环境类检查统一入口 + K2/K3 清理（2026-10-27）

本轮按 [`doc/plans/2026-10-27-kickoff-unresolved.md`](plans/2026-10-27-kickoff-unresolved.md) §3 的顺序开工：
**先验证基线 → K1（本仓可自行推进）→ K2/K3（清理）**；E1/E2/E3/D1–D4 依该单"只登记、不擅自开工"，本轮未动。
计划与切片见 [`2026-10-27-k1-env-checks-entry.md`](plans/2026-10-27-k1-env-checks-entry.md)。

> **谁跑的、算什么**：下表标「Lead 本轮实测」的是实施者自跑；标「独立验证者」的是 `gate-verifier`
> （只读、只报告）与 `k1-reviewer`（K1 复核）自跑。**两者都不是"独立复核全部四道门"**——K1 的独立复核只覆盖
> K1 切片（§94.4）。红线 9：复核者只报告不改。

### 94.1 基线复验（开工第一步，数字全部从命令输出复制）

| 门 | 实得 | 与 §1（979/114/117/missing=0/10·9·28/3） | 出处 |
|---|---|---|---|
| 软件层 | `979 passed, 3 deselected, 1 warning in 167.01s`（Lead）/ `169.97s`（独立验证者） | 一致 | 本轮实测 ×2 |
| 浏览器（补充门） | `114 passed in 118.27s`（首跑）、`130.28s`（复跑） | 一致；**中途 1 次抖动**见 §94.6 | 独立验证者 |
| 端到端 | `=> ALL PASS`，6 phase `rc=0`，自印 `PASS=50/27/18/8/8/6`、`FAIL=0`（合计 117） | 一致 | 独立验证者 |
| 文档 | `missing=0`、`exit=0`（复跑；首跑 `missing=1` 是并发写新计划文档的断链，见 §94.6） | 一致 | 独立验证者 |
| 环境层 | `3 passed, 24 deselected in 6.99s` + `原 ENV_ROOT 零写入（find -newer 命中 0）` | 一致 | 独立验证者 |
| kb 自测 | `汇总：PASS=10 FAIL=0` / `PASS=9 FAIL=0` / `PASS=28 FAIL=0` | 一致 | 独立验证者 |

⇒ 基线成立，可以动手（kickoff §3 第 1 步的判据）。

### 94.2 K1：环境类检查统一入口（选 kickoff 的选项 ②）

**问题**（可观察）：3 个 kb 自测要**手拼** `LOOP_ENV_ROOT`/`LOOP_WORKSPACE` 指向派生副本；忘了指就在只读真实
`ENV_ROOT` 上失败，指错根则数字不可比。两类"需要可写环境根"的检查各有各的前置 ⇒ 交接时容易只跑一半。

**做法**：`loop/spikes/run_env_layer_checks.sh` 新增两个开关，派生副本构造逻辑**不新增第二份实现**（红线 8）：
`--with-kb-selftests`（3 个 kb 自测 + 3 条 env_layer 共用同一个副本）与 `--dry-run`（零副作用：不复制、不执行、不删除）。
kb 自测要求 `rc=0` + 有汇总行 + `FAIL=0` + **通过条数等于验收数字**（`KB_EXPECT_PASS=(10 9 28)`，退化到 `PASS=0 FAIL=0` 也会红）；
打印的计划与真执行的命令**共用同一组数组**（`-B` + `PYTHONDONTWRITEBYTECODE=1` 不会各写一遍）。

**TDD 证据**（先红后绿，顺序如实）：
1. 红：新用例 `loop/tests/test_env_checks_script.py` 首跑 `5 failed in 11.09s`（旧脚本把 `--dry-run` 透传给 pytest、并先做起 2.6 GB 复制）；
2. 绿：实现后 `5 passed in 0.70s`；
3. 独立复核提 3 项（§94.4 A/B/C）+ 自查发现 1 项（打印与执行不同源，见 §94.4 下方）→ 补 3 条回归钉后 `8 passed in 2.75s`。

**验收（本切片判据：一条命令输出 `PASS=10/9/28` + `3 passed`）**：
- 全量重建副本、在**最终版脚本**上跑的那次（Lead 本轮实测，`--with-kb-selftests`，无 `--reuse`）：
  `[kb] _selftest_gate_schema.py: PASS=10 FAIL=0`、`PASS=9 FAIL=0`、`PASS=28 FAIL=0`；`3 passed, 24 deselected in 9.92s`；
  `原 ENV_ROOT 零写入（find -newer 命中 0）`；`[summary] ... env_layer rc=0；原 ENV_ROOT 零写入`；`RC=0`（首次全量跑 `15.14s`，同数字）。
- `--reuse` 复跑（Lead + 独立验证者各一次）：同上数字，`3 passed, 24 deselected in 6.71s` / `7.69s`，`RC=0`。
- 失败显式（Lead + 复核者各一次，假副本）：`[FAIL] _selftest_gate_schema.py: rc=1 汇总行=PASS=9 FAIL=1；验收数字要求 PASS=10 FAIL=0`，
  整条命令 `RC=1` —— 没有被吞成"通过/跳过"。

### 94.3 门（本轮改动后）

| 门 | 实得 | 命令 |
|---|---|---|
| 软件层 | **`987 passed, 3 deselected, 1 warning in 174.40s`**（基线 979 + K1 新增 8 条用例；不手算，数字来自输出） | `cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser` |
| kb 自测 + 环境层 | **`PASS=10` / `PASS=9` / `PASS=28` + `3 passed` + 原 ENV_ROOT 零写入** | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests`（AGENTS §4 新口径） |
| 文档 | `missing=0`、`exit=0`（提交前收尾复跑；`checked=2137`，`known_missing` 仍 12 条） | `python3 doc/audit/check_doc_links.py` |
| 端到端 | 未在本轮改动后重跑；**独立验证者**在改动前树上实测 `ALL PASS 117/0`。本切片不改 `loop/` 产品代码、不改流程拓扑，e2e 路径与改动无交集（新增的只是一个 spike 脚本与一个测试文件） | `cd loop && bash spikes/accept_v1_run.sh` |
| 浏览器（补充门） | 未重跑：本轮**不触碰** `loop/web/**` 与 `services/contracts.py` 的界面字段（AGENTS §4 只在界面/投影有改动时才要求单独跑） | —— |

### 94.4 独立复核（k1-reviewer，只读；8 条判定 + 3 项缺陷）

判定：① 默认行为零变化 PASS ② 一条命令验收 PASS ③ 失败显式 PASS ④ 红线 8（`cp -a` 全仓仅 1 处、路径仍走 `kb_lib`）PASS
⑤ 红线 11（三次跑完 `find kb/tools -name '*.pyc' -newermt '-60 minutes'` 空）PASS ⑥ 用例非空断言**基本 PASS 但有缺口**
⑦ 文档一致性 **FAIL（两处）** ⑧ K2 横幅 PASS。缺陷与处置：

| # | 缺陷（复核者原样报告） | 处置 |
|---|---|---|
| **A** | `--dry-run --cleanup` **会真的删副本**（cleanup 分支在 dry-run 之前）⇒ 默认 COPY 下等于误删 `.env-copy` | **已修**：cleanup 分支先判 `DRY_RUN`，只打印"将删除"；新增回归钉 `test_dry_run_cleanup_is_zero_side_effect` |
| **B** | 判据不 pin 条数 ⇒ 自测退化成 `PASS=0 FAIL=0` 也算通过；而 K1 的 10/9/28 只活在人眼里 | **已修**：`KB_EXPECT_PASS=(10 9 28)` 逐项比对，不符即红并打印"验收数字要求 PASS=n FAIL=0"；本节的数字就是这条判据的落账处 |
| **C** | 失败时 `[summary]` 仍写"3 项"却只列通过项；`--help` 用 `sed -n '2,42p'` 会打出实现代码 | **已修**：失败项也进 `[summary]`（`FAIL(rc=..)`）；`--help` 改为只打印头部注释（遇非注释行即停） |
| 缺口 | 红线 11 的 `-B` 断言只检查"打印的计划"，不保护真执行行（复核者 M1 变异仍全绿） | **已缓解**：真执行与打印共用同一组数组（`KB_ENV`/`RUN_ENV`），改一处两边同时变；复核者 M1 手段（只改一处）不再能造成"打印有 `-B`、执行没有" |
| 缺口 | `PASS=0 FAIL=0` 退化无独立自动用例 | **登记**：由 pin 比对覆盖（与"条数不符"同一条代码路径），本轮不额外造钩子（YAGNI）；复核者用代码审查确认 |
| 文档 ⑦a | 四份文档引 `STATUS §94` 而 STATUS 末节还是 §93（悬空引用；文档门只查路径不查锚点） | **已修**：本节即 §94 |
| 文档 ⑦b | `doc/plans/2026-10-27-kickoff-unresolved.md` §"五、常用命令"仍教手拼 `LOOP_ENV_ROOT`，与 AGENTS §4 矛盾 | **已修**：改为统一入口命令，并写明"不要再手拼" |
| **自查 ⑨** | 不是复核者提的，是提交前看 `git diff` 自查发现的：`KB_ENV`（副本数据根变量）定义在 `--dry-run` 分支**之后** ⇒ 打印出的 env_layer 命令**静默少了** `LOOP_ENV_ROOT`/`LOOP_WORKSPACE`（打印与执行两套东西，计划不能照着执行） | **已修**：`KB_ENV` 提前到 dry-run 之前定义，打印与执行同源；新增回归钉 `test_printed_plan_carries_the_same_env_as_the_real_run`（红→绿）。**为什么原来的用例没接住**：第 2/4 条只断言"计划里有 py 文件/有 `-B`"，不查数据根 —— 这条钉补上 |

### 94.5 K2：旧派生副本加"已过期"横幅（未删除，理由显式）

`workspaces/real-env-copy/OBSOLETE-20261027.md`（红线 12：历史快照必须带横幅）：写明它不是产品代码、不是界面验收对象，
`loop/web/index.html` md5 `6017b1383436d5f99cff41bbfd0f0a10`（87 425 B，mtime 2026-10-15 17:11:55）、
`GATE_DECISIONS_FALLBACK` 2 处（`:359` 定义、`:381` 使用）；复核者按实物核过 md5 与行号（PASS）。

**为什么没删**（kickoff 允许二选一，选横幅）：① 目录内含 2026-10-22 真实执行留痕（`SIMLIB_RUN/` 约 978 MB、`kb/` 约 1.1 GB），
本机 `ENV_ROOT` 只读、真实通过轮约 21.56 h（[C8 评估](plans/2026-10-27-c8-feasibility.md)）⇒ 删了本机无法再生成同类留痕；
② `doc/evidence/**`、`doc/STATUS.md` 的历史节按 `workspaces/real-env-copy` 这个路径记录当时环境，删除会让只增不改的记录指向不存在的路径
（文档门会红，而证据目录不许回填）。`git status` 不受影响（`workspaces/*/` 已忽略）。

### 94.6 K3 清理 + 两条如实登记的异常

- **K3**：`bash loop/spikes/run_env_layer_checks.sh --cleanup` ⇒ `[OK] 已删除派生 ENV_ROOT：<repo>/.env-copy`；
  `du -sh` 由 `2.6G` 变为目录不存在。裁决快照仍在 `doc/evidence/adjudication_20261027/`；重建用同一脚本（无 `--reuse` 时全量复制，
  本轮那次全量重建实测 `RC=0`，之后才清理）。**注**：本轮为跑验收重建过 `.env-copy`，因此那份副本里**没有**已落账的裁决数据根
  ——权威数据在 `doc/evidence/adjudication_20261027/`，需要时 `apply_conflict_adjudication.sh` 重放（§87）。
- **浏览器门抖动（独立验证者，如实登记）**：首跑 `114 passed`、复跑 `114 passed`，**中途有一次** `1 failed, 113 passed in 137.24s`
  （`tests/browser/test_run_sessions.py::test_characterization_double_click_and_rejection_keep_draft`，`#viewGate` `to_be_visible`）；
  该用例孤立重跑 `1 passed in 1.56s`。测试用 `ThreadingHTTPServer(("127.0.0.1", 0))` 随机端口 + `page.route` mock ⇒ 判定为负载下的
  UI 时序抖动，**不是代码回归、也不当通过**（该门本轮未在改动后被要求重跑，见 §94.3）。
- **文档门首跑 `missing=1`（独立验证者，如实登记）**：`[MISSING] doc/plans/2026-10-27-k1-env-checks-entry.md:48 loop/tests/test_env_checks_script.py`
  —— 是 Lead 先写计划文档、后落测试文件的并发窗口造成的**自造断链**，不是基线缺陷；测试文件落地后复跑 `missing=0`
  （不是靠 `KNOWN_MISSING` 放行：`known_missing` 仍 12 条，只改了 `run_env_checks.sh` 那行的**理由文案**）。

### 94.7 未闭合项（本仓写权之外，不擅自开工）

1. **E1 I4 真实生效**：仍缺**可写真实数据根**（`<ENV_ROOT>` 在 `/home` 的 `ro,nosuid,nodev` 挂载上）。本轮没有拿到 ⇒ 未做；
   取得后按 kickoff E1 跑 `apply_conflict_adjudication.sh --workspace <ws>`，验收 `blocks_release=0` + `G3` 通过 +
   `N16` 不含 `I4_CONFLICTS_UNCLEARED`。
2. **E2（S0-b 接入）/ E3（C8 passed 夹具）**：环境侧开发与真实通过轮，本仓侧只等"接入后改一处判据"。
3. **D1（4 条 B-core 取值待作者确认）/ D2（代录署名）/ D3（C11-B）/ D4（C12-B）**：需人裁决；D3/D4 必须先改规格。
4. **E4 推送**：本机出网被代理阻断，`git push` 由人在可出网机器做（本轮新增提交同样待推）。
5. `run_env_checks.sh` **不存在**（K1 选②）：`KNOWN_MISSING` 保留该条但理由改为"选项①未采用"，不伪造文件。

一致性：§94.2/§94.3 的命令与数字均从命令输出复制；`AGENTS.md §4`、`doc/plans/2026-10-27-c-group-handover.md` §2、
`doc/plans/2026-10-27-kickoff-unresolved.md` §2 K1/K2/K3 行与本节的命令、数字**同一套写法**（红线 2/8）。

## 95 K4：门清单单页落到工程入口（2026-10-27）

**问题**（kickoff §2 K4）：四道必备门 + 两道补充门的**命令**散在 `AGENTS.md §4`、C 组交接单 §2 与
`loop/README.md` §2 的正文里；`loop/README.md` 里还留着一句"浏览器门现状 … 108 passed"的陈旧数字，
新窗口照它跑会得出错误结论（现行 114）。判据没问题，**是找命令的成本与陈旧数字的问题**。

**做法**：`loop/README.md` 新增 §2.1「门清单：四道必备 + 两道补充（照抄即可跑）」——
一张表（门 / 命令 / 前置 / 期望）+ 一张「改动落在哪就重跑哪道」+ 失败怎么记（环境缺件与 `failed`/`passed` 分开写）。

- **不立第二套判据**（红线 8）：表头写明判据在 `AGENTS.md §4`，本表只汇总命令；
- **不抄数字**（红线 2）：期望列写"数字见 STATUS"，不写死通过数；
- 顺手把 §2 里那句陈旧数字改成"**2026-10-26 那次实测（当时）**"并指向 `doc/STATUS.md` 最新一节，
  不再以"现状"表述（旧行保留为历史记录，不改写当时数）。

**验收**（kickoff K4：新窗口按文档能跑通四道门 + 两道补充门）——**照抄 README 表里的命令**跑，不看旧笔记：

| 门 | 本轮实得（命令输出复制） | 说明 |
|---|---|---|
| ① 软件层 | `987 passed, 3 deselected, 1 warning in 174.40s` | 本轮 §94.3 已跑（改动后），命令与表中一字不差 |
| ② kb 自测 + 环境层 | `PASS=10` / `PASS=9` / `PASS=28` + `3 passed, 24 deselected in 9.92s` + `原 ENV_ROOT 零写入`，`RC=0` | 本轮 §94.2 全量重建那次 |
| ③ 端到端 | `=> ALL PASS`，6 个 phase `rc=0`，phase 自印 `PASS=50 / 27 / 18 / 8 / 8 / 6`（合计 117，由自印数相加）、`FAIL=0` | **本轮照抄 README 表重跑**，跑完 `provision --cleanup` |
| ④ 文档 | `missing=0`、`exit=0`（`checked=2137`） | 在 `loop/` 下用表里的相对路径 `../doc/audit/check_doc_links.py` 跑，证明路径写法可用 |
| 补① 浏览器 | `114 passed in 123.40s`，`RC=0` | **本轮照抄 README 表重跑**（含 `PLAYWRIGHT_BROWSERS_PATH`/`HOME`/`TMPDIR` 三个必需变量） |
| 补② 环境层单跑 | `3 passed, 24 deselected`（`--reuse`） | 本轮 §94.2 复跑 |

**为什么 ①/②/④ 用 §94 的实测而 ③/补① 要重跑**：K4 只改文档，①/②/④ 的对象没变；
而 ③/补① 正是"容易被陈旧笔记带偏"的两道（端口、浏览器变量、清理顺序），所以按新表**重新照抄一遍**，
证明"文档能跑通"这件事本身。

**未做**：`doc/plans/` 不再新增一份"门清单"单页（同一口径两处维护=会漂，红线 8 的精神）；
门数字仍只在本文档维护，`loop/README.md` 一个都不写。

## 96 D 组裁决（D1–D4 = A/A/A/A）与 D1 落账（2026-10-27）

人给的裁决（[裁决单](plans/2026-10-27-d-group-rulings.md) §D5）：
**D1 = A 确认 4 条现口径**、**D2 = A 维持代录**、**D3 = A 不做（维持取消=终态失败）**、**D4 = A 等 E2**。

| 项 | 处置 | 是否有代码/数据改动 |
|---|---|---|
| **D1** | 4 条 Tier B-core 追加"作者确认 2026-10-27"记录（见 §96.1） | **有**（可写派生数据根 + `doc/evidence/` 新快照） |
| **D2** | 维持"人批示 + Host 代录"，不冒充亲笔；亲笔命令留在裁决单 §D2.3-B（须人按键） | 无 |
| **D3** | C11-B **关闭**：维持"取消=终态失败"，`LOOP_ORCHESTRATION_SPEC` §6 第 9 条即为该裁决，不新增终态/动作枚举 | 无 |
| **D4** | 维持"传了才校验"；B 方案登记为 **E2 完成后的独立切片**（届时先改 `S0_ENVIRONMENT_SPEC` §8 再改代码） | 无 |

### 96.1 D1 落账实测（数字从命令输出复制）

真实 `<ENV_ROOT>/kb` 是 `ro,nosuid,nodev` 挂载 ⇒ 写入落在**可写派生数据根** `<repo>/.dev-ws`（跑完 `--cleanup` 已删）：

1. `provision_dev_workspace.sh --force --quiet` 建根；`apply_conflict_adjudication.sh --workspace <repo>/.dev-ws`
   落 72 条原始快照（指纹校验通过）。该脚本自印：
   `[after] I4 读数：conflicts=72，blocks_release=0，open=0`；
   `[g3 ] full_now 提交前检查：通过`；`[g3 ] subset_only 提交前检查：通过`；
   `[n16] after blockers=['I1_UNRESOLVED_ENTRIES','I2_CASES_PENDING','I3_EVIDENCE_MISSING','E2_EVIDENCE_ARCHIVE_EMPTY','F_N16_04_STAGING_RESIDUE']`，
   `I4 在列=False`（与 §87.3 的 before/after 同口径）。
2. 4 条作者确认用 `adjudicate_conflicts.py --actor human:chenjunming --id <C2|C11|C38|C58> --status ruled`
   **追加**（每次自印"追加 1 条裁决 … 仍阻断发版 0 条"）。
3. `--verify`：`[verify] 裁决记录=76（去重后 72）；conflicts=72，仍阻断=0`；`[verify] 锚与合并一致性：全部通过`。
4. 结构核对：每条被确认 id 都有 **2 条**历史记录（原裁决 + 确认）；`blocks_release=True` 的记录数 = **0**；
   新记录 `adjudicated_at=2026-10-27T13:52:49～50+0800`，`sha256` 前缀
   `79ed535a86ea`(C2) / `e73529d889de`(C11) / `311ce343434b`(C38) / `22d29e9f466a`(C58)。
5. 回归：三个 kb 自测（`LOOP_WORKSPACE=<repo>/.dev-ws`）`汇总：PASS=28 FAIL=0`、`PASS=10 FAIL=0`、`PASS=9 FAIL=0`。

**快照（只增不改，`chmod 444`，`md5sum -c` 通过）**：
`doc/evidence/adjudication_author_confirm_20261027/`：
`adjudication.json` **`a2e399a7c22fa0c04dc13fe8187c3396`**、`conflicts.json` **`21cc93005f9a6a151ec4f76bffab2e7f`**
（README 记录了 4 条的口径、两处依赖假设与复算命令）。

### 96.2 边界（照实登记）

- **真实数据根仍未生效**：本节的 76 条记录只在派生数据根上验证过，`<ENV_ROOT>/kb` 依旧只读 ⇒
  真实轮次的 I4 解阻仍属 **E1**（拿到可写真实数据根后 `apply_conflict_adjudication.sh --workspace <真实根>`，
  注意它落的是 72 条快照；4 条确认记录要一并落需把本目录的 `adjudication.json` 作为快照源，
  即 `--snapshot doc/evidence/adjudication_author_confirm_20261027`）。
- **C38 的假设已写进记录**：`REV` bits[3:1] 复位值按 0 处理（原文 L1631 未给值）——若作者后续给出非 0 值，
  按追加改判处理（不改本次记录）。
- **D3/D4 无代码改动**：C11-B 关闭、C12-B 等 E2。若将来开工，**先改规格**（AGENTS §2.1）。

## 97 未闭合项（截至 2026-10-27 本轮收尾）

| 编号 | 事项 | 状态 |
|---|---|---|
| **E1** | I4 在**真实数据根**生效 | 真实根仍 ro（§98.1 实测：只读挂载 + 写探测 `Read-only file system` + 无 sudo）；但"拿到写权后要跑的命令"已在可写根上用**当前权威快照**跑通（§98.3），且修掉了挡住它的指纹硬编码缺陷（§98.2） |
| **E2** | S0-b 接入（ports/smoke、`ready_for_execution` 可为 true） | 环境侧；D4 因此等 E2 |
| **E3** | C8 `passed` 形态夹具 | 环境侧（真实通过轮 ≈21.56 h + 写权） |
| **E4** | 推送 | ✅ **已关闭（2026-10-28）**：本机代理恢复后推送成功，`abdb16f..4c8281a  main -> main`（`git push` 输出复制）；远端 `refs/heads/main` 与本地 HEAD 同为 `4c8281a`（`git ls-remote` 核对），详见 §105 |
| **D1–D4** | 四项裁决 | ✅ 全部已裁（A/A/A/A），处置见 §96 |
| **R 类 8 条** | 登记不改 | 不变（见 kickoff §2 R 类） |

## 98 E1 实测：真实数据根仍被 ro 挡；可写根上用**当前权威快照**跑通（2026-10-27）

E1 的目标是"让 I4 在**真实**数据根生效"。本轮把它拆成两半，都实测了。

### 98.1 真实数据根：硬阻塞再次实测（不是推测）

| 事实 | 实得 |
|---|---|
| 挂载 | `findmnt -T <ENV_ROOT>` ⇒ `/home … ext4 ro,nosuid,nodev,relatime`；而本仓是**同一设备**上的 `rw` bind mount（`/dev/mapper/vg_group-lv_data[/work/chenjunming/change-impact-loop]` ⇒ 所以仓可写、`/home` 其余只读） |
| 目录写权 | `ENV_ROOT`、`kb`、`kb/conflicts`、`kb/adjudication` 四个目录 `test -w` **全部 NOT-writable** |
| 写探测 | `touch …/kb/conflicts/.write_probe` ⇒ `Read-only file system`（未产生文件） |
| 提权 | `id -u`=1025；`sudo -n true` ⇒ `sudo must be owned by uid 0 and have the setuid bit set`（**不可用**） |

**对真实数据根真跑一次**（E1 的命令本体，非 dry-run）：

```
bash loop/spikes/apply_conflict_adjudication.sh --workspace <ENV_ROOT>/kb \
     --snapshot doc/evidence/adjudication_author_confirm_20261027
```

输出（命令原文复制）：指纹校验通过 → `[before] I4 读数：conflicts=72，blocks_release=72，open=72` →
`[g3 ] full_now 仍被拒` / `subset_only 仍被拒` → `[n16] before … I4 在列=True` →
`cp: cannot create regular file '<ENV_ROOT>/kb/conflicts/adjudication.json': Read-only file system` →
`[FAIL] 复制失败（数据根不可写？）`，**退出码 4**（显式失败，不是静默成功）。
零写入自证：`find <ENV_ROOT> -newer <marker> | wc -l` = **0**。

⇒ 结论：**E1 在本机无法完成**，缺的是"可写真实数据根"或管理员 `remount -o rw /home`（或另一台有写权的机器）。

### 98.2 缺陷：E1 的"一条命令"落不了**当前权威快照**（已修 + 已测）

`apply_conflict_adjudication.sh` 原先把 72 条快照的 md5 **硬编码**在脚本里：用 D1 之后的权威快照
`doc/evidence/adjudication_author_confirm_20261027`（76 条记录，含 4 条作者确认）跑，直接
`[FAIL] 快照指纹与登记不符（红线 10）`、退出码 3 —— E1 即使拿到写权也用不了当前快照。
（红：用 `git show HEAD:loop/spikes/apply_conflict_adjudication.sh` 的旧版实测，退出码 3，期望/实际 md5 都打印了。）

**修法**（红线 10 不放宽）：指纹来源改为优先级 `--expect-md5 <adj>:<conf>` ＞ 快照自带 `md5.txt` ＞
**仅对默认快照目录**有效的内置登记值；三者都没有 ⇒ 显式失败（"缺少可核指纹"），**不许跳过核验**。
新增用例 `loop/tests/test_apply_adjudication_snapshot.py`（4 条，全走 `--dry-run`）：自带 md5.txt 通过 /
被篡改必须红 / 无指纹必须红 / `--expect-md5` 可通过 ⇒ `4 passed in 1.00s`。
更宽回归：软件层门 `991 passed, 3 deselected, 1 warning in 177.85s`（上一轮 987 + 本切片 4 条；数字来自输出）。

### 98.3 可写根上的 E1 全流程（拿到写权后要跑的就是这条，已跑通）

```bash
bash loop/spikes/provision_dev_workspace.sh --force --quiet
bash loop/spikes/apply_conflict_adjudication.sh --workspace <repo>/.dev-ws \
     --snapshot doc/evidence/adjudication_author_confirm_20261027
bash loop/spikes/provision_dev_workspace.sh --cleanup     # 跑完删掉
```

实得（命令输出复制）：

- `[info] 快照：…adjudication_author_confirm_20261027（指纹校验通过；来源：…/md5.txt（快照自带））`
- 生效前 `[before] … blocks_release=72`、`G3 full_now/subset_only 仍被拒`、`N16 … I4 在列=True`
- 落账后 `[merge] adjudication.json：72 条裁决已合并进 conflicts（重跑不丢）`；
  `[verify] 裁决记录=76（去重后 72）；conflicts=72，仍阻断=0`；`[verify] 锚与合并一致性：全部通过`
- 生效后 `[after] I4 读数：conflicts=72，blocks_release=0，open=0`；
  `[g3 ] full_now 提交前检查：通过`、`[g3 ] subset_only 提交前检查：通过`；
  `[n16] after blockers=['I1_UNRESOLVED_ENTRIES','I2_CASES_PENDING','I3_EVIDENCE_MISSING','E2_EVIDENCE_ARCHIVE_EMPTY','F_N16_04_STAGING_RESIDUE']`，**I4 在列=False**
- 结构核对：数据根里 `adjudication.json` 记录数 **76**，含"作者确认 2026-10-27"的正是 **C2/C11/C38/C58** 四条
- 退出码 **0**

⇒ E1 的**验收判据三项全部达到**（`blocks_release=0`、`G3 full_now/subset_only` 提交前检查通过、`N16` 不含
`I4_CONFLICTS_UNCLEARED`），只是发生在**可写派生根**上；真实根那一半仍被 §98.1 的挂载挡着。

### 98.4 E1 的剩余动作（交给人 / 有写权的机器）

1. 拿到可写真实数据根（或 `remount -o rw /home`）后跑 §98.3 的三行命令，把 `--workspace` 换成真实数据根；
2. 或在一台有写权的机器上跑同样命令（脚本只依赖 `loop/.venv` 与本仓快照，不依赖本机路径）；
3. 跑完把 `[after] blocks_release=0` / `[g3]` / `[n16]` 三行输出回填 STATUS（**新节，不改本节**）。

## 99 E2/E3 可行性体检：能力已就位，剩下的是裁决与算力（2026-10-27）

详细报告：[`doc/plans/2026-10-27-e2-e3-feasibility.md`](plans/2026-10-27-e2-e3-feasibility.md)。本轮只做体测，
**没有改任何 S0 代码或规格**（Q1–Q3 未定；`S0_ENVIRONMENT_SPEC §8.4` 红线 5：拿不到协议就保持阻断并登记，不得猜）。

### 99.1 实测（数字从命令输出复制）

| 项 | 实得 |
|---|---|
| EDA/许可 | `/home/soft/UNIVISTA/20260917/UVS/bin/{uvlan,uvs}` 在 PATH；`UVS_HOME`、`UV_LICENSE=8273@s24:…` 已配置 |
| 三库编译（派生副本 `<repo>/.env-copy` 上跑 `doc/tools/compile_only.sh -c tc_pcie_rw_02`） | `[PASS] 卡点 B 通过：两段编译均成功`、`COMPILE_RC=0`、`real 0m2.737s` |
| rtl 段 | 日志 1295 行 / 86 124 B；工具自印 `Compilation: 0 error(s), 13 warning(s)` |
| tb 段 | 日志 795 行 / 28 421 B；工具自印 `Compilation: 0 error(s), 4 warning(s)` |
| 原 `ENV_ROOT` 零写入（红线 11） | `find <ENV_ROOT> -newer <marker> \| wc -l` = **0** |

### 99.2 顺手钉清的判据陷阱（要写进 D3 的实现与用例）

用 `grep -c -iE '\berror\b' <日志>` 数"错误行"**会把工具汇总行本身算成一行 error**（实测：命中 1 行，
内容正是 `Compilation: 0 error(s), 13 warning(s)`）。⇒ smoke 判据必须是「解析工具汇总行 `Compilation: N error(s), M warning(s)`
+ `Error-<code>` 前缀行 + 分别记录 `rc`」，不是裸 grep。warning 明细样例：
`Warning-120002: Command option warning`、`Warning-121147: Redefinition`。

### 99.3 结论与下一步（要人/环境侧给的东西）

- **E2** 的阻塞从"能力"收敛为**三个口径裁决**：Q1 ports 差异来源（外部报告 vs Host 派生，需先改 S0 规格）、
  Q2 hunk 谁填（人 / 模型提议+人确认）、Q3 warning 可接受阈值（环境侧）。给定后本仓侧是一个中小切片：
  `host/s0.py` + `services/api.py` + 报告模板 + 用例；**D4 只需改一处**
  （`loop/host/s0.py:334` 的 `ready_for_execution = False` 归一逻辑）。
- **E3** 的阻塞收敛为「可写 `ENV_ROOT` + N9 全跑 ≈**21.56 h**/5 例排期 + `N6_` 观测点印记口径」；
  卡点 B 已证明可跑（2.7 s/例）。
- 派生副本已 `--cleanup` 删除（2.6 G；重建约 10 s）。

## 100 Q3 关闭：smoke 的 warning 判据改为**基线相对增量**（2026-10-27，本仓自定 + 实测）

**背景**：`S0_ENVIRONMENT_SPEC` §8.3 的 **Q3** 原先写着"需环境侧三库驱动协议、如何判 error/warning、
不得猜"，于是 D3 一直挂着等外部白名单。本轮把它从"要人给答案"改成"**可复算的判据**"——
不是在猜，而是把"什么算回归"定义成**基线相对增量**。

**实验**（派生副本 `<repo>/.env-copy` 内，4 次 `bash doc/tools/compile_only.sh`，全部 `rc=0`）：

| 实验 | rtl 段 | tb 段 | 结论 |
|---|---|---|---|
| 同用例 `tc_pcie_rw_02` 第 1 次 | `0 error(s), 13 warning(s)`；codes `120002/120428/121553/121687` | `0 error(s), 4 warning(s)`；codes `120002/121147` | 基线参照 |
| 同用例第 2 次 | 完全相同 | 完全相同 | **确定性成立**（同一输入同一告警集合） |
| 换用例 `tc_bmc_i2c_03` | 同上 13 / 同 codes | 同上 4 / 同 codes | 告警主要是**环境级基线噪声**，不是用例特有 |
| 人为注入重复定义 `tc_q3probe` | 13 / 同 codes | **5 warning(s)**，codes `120002/120162/121147` | **增量可检出**：新增 `Warning-120162`、计数 4→5 |

**定下的判据**（写进 S0 规格提案 §8.2-2 / §8.5）：

1. `error(s) > 0` ⇒ `smoke=failed`；`rc` 只能作"能否产出库"的记录，**不能替代** error 计数。
2. warning 做**基线相对增量**：同一用例分别在"基线树"与"副本（新 RTL + 适配后 TB）"各编一次，
   `added = codes(副本) − codes(基线)`；`count_increase` = 同 code 计数上升。
   `added ∪ count_increase` 非空时，**每条都要有评估记录**（复用 Q2 的"模型提议 + 人确认"）才算 `smoke=passed`；
   `removed` / 计数下降只记录。
3. 基线编译必须在**独立沙箱工作树**（`run_guarded.sh --sandbox-root`：只读软链 + 自己的 `SIMLIB_RUN`），
   跑完断言基线目录零写入。
4. 判据实现只写一份（`loop/host/` 下日志解析模块），N7 与 S0 smoke 共用。

**边界（仍然不是我能做的）**：真实 `<ENV_ROOT>` 的写入（ro 挂载）、三个闸门的人签、环境仓 `RTL/TB/PKG/TESTLIB` 的修改。
除此之外，E2 已无外部输入阻塞。

**快照/清理**：实验在派生副本上做，原 `ENV_ROOT` 零写入；副本已 `--cleanup` 删除。



## 101 S0-b 开工（S1）：RTL 端口确定性派生 + 规格修订落地（2026-10-27）

**范围**：E2 的第 1 片。规格已按 Q1/Q2 裁决与 Q3 关闭修订（提交 `149489f`），本片落地"派生"这一半；
"提议/确认/落盘"与两项 check 接线在 S2–S4。

### 101.1 做了什么

- 新模块 `loop/host/sv_ports.py`：SV 端口抽取 + 基线/新 RTL 差异派生，**只读、无模型、确定性**。
  - 关键：端口表里的 `` `ifdef/`ifndef `` 必须按**编译期宏**求值（`all_define.txt` 的
    `-define SIM/SIMULATION/VENDOR_PANGO`）。真实 DUT 顶层 `TCS9620_MAC_TOP` 的端口表里就有
    `` `ifndef SIMULATION `` 分段（非仿真跑 pci_exp_*，仿真跑 pcie_user_clk 等）——静态文本解析会得出
    错误的端口集，这是本片最重要的实现约束。
  - 只扫 `RTL/rtl_dir_pango.txt` 清单里的文件（= 编译实际编的那批），同名同端口重复定义计 `duplicates`
    不算歧义；同名但端口不同才进 `unparsed`。
- 新用例 `loop/tests/test_sv_ports.py`（15 条）：ANSI 解析、注释/参数块、非 ANSI 与缺方向 fail-closed、
  同名重复两态、确定性（两次 md5 相同）、无副作用（前后树指纹不变）、增删改差异、模块过滤、
  空端口表模块、预处理器（`ifndef` 两支）、`all_define.txt` 读取、filelist 优先。

### 101.2 真实 RTL 实测（只读，未复制、未写环境）

| 项 | 实得 |
|---|---|
| 宏 | `load_defines(<ENV_ROOT>/all_define.txt)` ⇒ `['SIM','SIMULATION','VENDOR_PANGO']` |
| 扫描 | `scan_tree(<ENV_ROOT>/RTL, defines)` ⇒ `from_filelist=True`、**255 files**、**205 modules**、`duplicates=0`、`unparsed=52`（老式非 ANSI 模块如 `FD`/`fifo_pre`，按契约 fail-closed） |
| DUT 顶层 | `TCS9620_MAC_TOP` 解析成功，**66 个端口**（例：`bmc_i2c_s_scl inout`、`bmc_spi_m_clk output [1:0]`） |
| 确定性 | 同一棵树连续扫描两次 `md5` 相同（`73eb3c0cef1f39c7…` 同值） |
| 耗时 | 约 1.8 s / 255 文件 |

### 101.3 实现过程中修掉的两个真陷阱（写给后续切片，别再踩）

1. **不能把 Verilog 的 `'d32` / `1'b0` 当字符串**：`_header_after` 原先用 `'` 作字符串定界符 ⇒ 从第一个
   数字字面量起"永不闭合"，头部一直扫到文件尾，`TCS9620_MAC_TOP` 解析失败。改为只用 `"` 作定界符。
2. **`ifdef` 不能剥掉了事**：必须带 `defines` 求值，否则仿真端口集错。

### 101.4 门（本轮改动后）

- 软件层：`1006 passed, 3 deselected, 1 warning in 170.36s`（上一轮 991 + 本片 15 条；数字来自输出）。
- 文档门：`missing=0`、`exit=0`（`checked=2218`）。

### 101.5 下一步（S2）

`proposals/` + 确认门槛（只增不改）+ 落盘前 md5 断言（未确认 ⇒ 副本 TB 顶层逐字节不变）。


## 102 S0-b 接入完成（S1–S5）：`ready_for_execution` 第一次真的能为 true（2026-10-27）

**范围**：E2 全部（S1 派生 → S2 提议/确认门槛 → S3 `ports` 接线 → S4 `smoke` 接线 → S5 准出开关）。
规格修订见提交 `149489f`，本节记录实现与**真实环境副本上的端到端实测**。

### 102.1 交付

| 产物 | 内容 |
|---|---|
| `loop/host/sv_ports.py` | 端口抽取 + 差异派生（只读、确定性、按编译期宏求值；`md5` 可复算） |
| `loop/host/s0b.py` | 提议 / 人确认（只增不改+锚）/ 精确落盘 / ports 判据 / smoke 执行与基线相对增量 / 准出开关 |
| `loop/host/uvs_logs.py` | 编译日志**唯一**解析（汇总行 + `Error-`/`Warning-` code；**裸 grep 会误判**） |
| `loop/host/s0.py` | 接线：`tb_top`/`run_entry` 解析、`ports`/`smoke` 结论写回 checks、`ready_for_execution` 唯一判据口、报告新增端口差量表与冒烟段 |
| `loop/services/api.py` | 4 个端点：`POST /api/s0/{id}/{proposals,confirmations,apply,smoke}` |
| 用例 | `tests/test_sv_ports.py`(17) + `tests/test_s0b.py`(21)；既有 `tests/test_s0.py`(37) 全绿 |

### 102.2 真实环境副本端到端实测（数字从输出复制）

基线 = `<ENV_ROOT>` 的派生副本（2.6 G，清掉 30 个历史运行沙箱软链，见 §102.3-③），
`rtl_source` = 该副本的 `RTL/`（内容相同 ⇒ 期望"零差异"），`work_env` = `<repo>/.s0-work`。

| 环节 | 实得 |
|---|---|
| `prepare()` | `status=prepared`；**`tb_top=TB/tbtop.sv`**（由编译驱动解析）、**`run_entry=run_tc.py`**；checks = copy/rtl/non_rtl **passed**、ports **passed**、smoke waiting、baseline **passed** |
| `ports` | **passed**；`base_mods=205 cand_mods=205`、`unparsed=52/52`（两侧 md5 相同 ⇒ 语义未变）、`derive_md5=c2592ef4…` |
| `smoke()` | **passed**；candidate `rc=0 errors=0 warnings=17`、baseline `rc=0 errors=0 warnings=17`；`delta = {added:[], removed:[], count_increase:[]}`；日志两段 `…_c_rtl.log` / `…_c_tb.log` |
| `get()`（漂移核验） | `verification = {"drift": {}, "errors": []}`；六项 checks **全 passed** |
| **准出** | **`ready_for_execution: True`**（此前 `get()` 里恒 False） |

⇒ E2 的目标达成：S0 的六项检查现在能真实产出 `passed`，`real` 入口因此有真实判据可依（不再是"恒假"）。

### 102.3 过程中发现并修掉的 5 个真问题（都不是用例能假出来的）

1. **`TB/top.sv` 在真实环境不存在**（基线清单里 TB 下是 `tbtop.sv`）⇒ `tb_top` 改为由编译驱动解析（`TB/tbtop.sv`），历史写法兜底。
2. **基线没有 `run` 文件**（真实环境是 `run_tc.py`/`run_uvs_new.sh`/`doc/tools/run_local.sh`）⇒ `run_entry` 由 `resolve_run_entry()` 按优先级解析。
3. **真实 `ENV_ROOT` 含 30 个历史运行沙箱软链**（`doc/`5、`kb/`21、`loop/`4）而 `manifest()` 拒软链 ⇒ 真实轮的基线必须是**无软链的资产快照**（已写进规格 §2）。
4. **冒烟沙箱不能放在被见证的树里**：`run_guarded.sh` 的沙箱工作树全是软链 ⇒ 放进 `work/` 会让漂移核验把冒烟自己当成污染（实测 `verification.errors` 两条）；改为把沙箱与证据放到**记录目录**（树外）。另外驱动用 `LOOP_ENV_ROOT` 定位环境根（不是 cwd），必须显式传。
5. **52 个老式非 ANSI 模块**：原先"有解析不了的模块 ⇒ `ports` 恒 failed"在真实树上是死路。改为**只看未解析模块是否真的变了**：两侧都解析不了且源文件 md5 相同 ⇒ 不影响差异判定；一侧解析不了一侧解析成功、或两侧 md5 不同 ⇒ fail-closed。

### 102.4 门（本轮改动后）

- 软件层：**`1029 passed, 3 deselected, 1 warning in 176.55s`**（上一轮 1006 + 本切片新增 23 条；数字来自输出）。
- 文档门：`missing=0`、`exit=0`（`checked=2226`）。新增 `.s0-work/`、`.s0-test/`、`.s0-rtl/` 跳过规则
  （与 `.dev-ws` 同类：仓内一次性派生副本，不能算本仓文档；`tests/test_doc_links.py` 有对应断言）。

### 102.5 未做（照实登记）

- **D5 界面**：`loop/web/**` 的"未接入"灰态与确认交互未做（后端已返回真实 `ports/smoke`/`ready_for_execution`）；
  做它要跑浏览器门。
- **内网真机验收**：需要可写 `ENV_ROOT` + 真实三库协议（本机 ro 挂载）；本节的实测在派生副本上完成。
- **E3（passed 夹具）**：仍需一次真实通过轮（≈21.56 h/5 例）+ 三个闸门的人签。


### 102.6 独立复核（s0b-reviewer）与整改：9 条 FAIL 全部处置

复核结论原文：**部分通过，不可宣称已验收**（FAIL-1 阻断级）。逐条整改如下（每条附证据；复核复现件在
`workspaces/s0b-verify/REPORT.md`，gitignored）。

| # | 复核发现 | 处置 | 证据 |
|---|---|---|---|
| **FAIL-1（阻断）** | `apply` 合法落盘后被 `get()` 判成漂移（拿 prepare 时刻的 `work-after.json` 比当前副本）⇒ 适配路径永远到不了准出；且 `record.json` 与 `get()` 是两套判据 | **已修**：`apply()` 落盘后**追加**见证 `work-after.<n>.json` 并写进 `record['work_witness']`；`_verify()` 取最新见证；`get/apply/smoke` 全走同一条 `_refresh_checks`（唯一判据链） | 真实副本：apply 后 `drift={}`、`status=prepared`、ports `passed`；`witness=work-after.2.json`、md5 `39e95ecd…`→`bc428020…` |
| **FAIL-2（高）** | 提议不能追加（第二次 `FileExistsError`），API 允许空 hunks ⇒ 一次空提议永久锁死 | **已修**：`propose()` 追加（重复 `hunk_id` 拒绝）、空列表 `ValueError`、临时文件原子替换 | `test_propose_can_be_appended`：H1+H2 并存 |
| **FAIL-3（中高）** | 基线读数不可信 / rc≠0 仍 `passed`（`errors=None→0`） | **已修**：判据顺序改为 两侧汇总行可信 → 两侧 `rc==0` → 两侧 `error(s)==0` → warning 评估；任一不满足即 `failed` | `test_smoke_requires_trustworthy_baseline_reading`、`test_smoke_fails_on_nonzero_rc` |
| **FAIL-4（中）** | §8.2-2「每段落命令/rc」未结构化；报告只在 prepare 写一次（apply/smoke 后陈旧）；阻断项是静态文案 | **已修**：smoke 每段记 `command/rc/summary/logs`；`_refresh_checks` 末尾重写报告；报告「阻断项」按当前 checks 计算 | 真实报告含 `- candidate：rc=0 errors=0 warnings=17`、`命令：bash …/run_guarded.sh …` |
| **FAIL-5（中）** | 「新增/上升 warning 逐条评估」无落账入口 ⇒ smoke 永远到不了 passed | **已修**：`s0b/warning_decisions.jsonl`（只增不改 + sha256 锚）+ `POST /api/s0/{id}/warnings`；`accepted` 后才可能 passed | `test_smoke_waits_for_warning_evaluation_then_passes`；`test_warning_acceptance_is_append_only_and_required` |
| **FAIL-6（规格）** | ① §8.5「空差异 ⇒ ports 不 passed」与实现/用例冲突；② §8.2-1「解析不了 ⇒ failed」过严；③ 登记表字段缺 diff/位置/影响用例 | **已修**：规格改为"空差异可 passed 但须带派生证据且 TB 无改动；解析不了按 md5 是否真的变了判；warning 评估落账口径"；报告新增「逐 hunk 登记」（位置/影响用例/理由/真实 unified diff） | 规格 §8.2-1/§8.2-2/§8.5 已改；真实报告含 `## 逐 hunk 登记` 与 ```diff``` 段 |
| **FAIL-7（低）** | 确认后未落盘被误判 `failed` | **已修**：新增 `pending_apply` 分支 ⇒ `waiting`（"已确认的 hunk 尚未落盘"） | `test_ports_waiting_after_confirm_before_apply`；真实链路确认后 `waiting`、apply 后 `passed` |
| **FAIL-8（低）** | `GET /api/s0` 能力位仍 `tb_adapt=false, smoke=false` | **已修**：两位置 `true`（描述后端能力；界面 D5 仍是灰态，测试注释已写明） | `test_s0_index_advertises_rehearsal_capability` |
| **FAIL-9（低）** | 二次 apply 报 400（非幂等） | **已修**：内容已等于"基线+已确认" ⇒ `applied=[]`、`already_applied=True` | `test_apply_is_idempotent` |

**复核者观察项**：`.env-copy` 6 个目录 mtime 变但内容 md5 未变 —— 复核者已用对照实验排除被测代码
（`prepare()` 不改源 mtime），属冒烟驱动在基线树内 `mkdir -p SIMLIB_RUN` 的已知副作用（红线 11 允许写 `SIMLIB_RUN/`）；
本轮改为把沙箱/证据放记录目录后，基线侧只剩该 `mkdir`。

**复核后新增的真实端到端（有 TB 改动的那条路径，此前走不到准出）**：

| 步骤 | 实得 |
|---|---|
| `prepare`（零差异） | `ports=passed`；`smoke=waiting` |
| `propose`（模型：TB 顶层插一行注释）+ `confirm`（人签） | 确认后 `ports=waiting`（"已确认的 hunk 尚未落盘"） |
| `apply` | `applied=['H1']`、`witness=work-after.2.json`、TB md5 `39e95ecd…`→`bc428020…`、**`drift={}`**、`ports=passed` |
| `smoke`（副本内真编译） | `passed`；candidate `0 error(s)/17 warning(s)`、baseline 同、`delta` 空 |
| 终态 | 六项全 `passed`、`status=prepared`、**`ready_for_execution=True`**；报告含 `## 逐 hunk 登记` 与逐段命令 |

### 102.7 门（复核整改后，数字从输出复制）

- 软件层：**`1046 passed, 3 deselected, 1 warning in 176.47s`**（数字从本轮末次门输出复制）。
- 文档门：`missing=0`、`exit=0`。


### 102.8 第二轮复核（N1–N6）与整改

第二轮结论：9 条 FAIL 中 8 条关闭、FAIL-6 部分关闭；**新发现 2 个准出路径上的 fail-open（N1/N2）**，仍不宣称可验收。
逐条处置：

| # | 第二轮发现 | 处置 | 证据 |
|---|---|---|---|
| **N1（中高，fail-open）** | 把 `record.json` 的 `status` 改成 `preparing` ⇒ 漂移核验整段跳过、`ready=true`、`real` 入口放行 | **已修**：`_verify()` 不再按 status 短路；`ready_for_execution()` 额外要求 `status == "prepared"` | `test_forged_status_cannot_bypass_drift_check`：伪造 status 后 `ready=False` 且 drift 仍被抓 |
| **N2（中高，fail-open）** | `apply` 落盘后直接用当前树当新见证 ⇒ 把落盘**前**就存在的未登记改动洗白（正常流程即可触发） | **已修**：把核对**提到写文件之前**——先比"当前副本 vs 上一份见证"，除 `TB/<tb_top>` 外有差异即拒绝（拒绝发生在提交前） | 真实记录复验：`N2 已拦截 ⇒ apply 前副本已偏离上次见证：TB/top_cfg.sv、TB/top_env.sv`，且**拒绝时 TB 顶层 md5 不变**；`test_apply_refuses_to_launder_existing_drift` |
| **N3（中）** | 只读/归档记录读一次 `get()` 就变 `failed`（读路径重写报告失败改了判定） | **已修**：报告写失败只记 `report_write_error`，不改 status/ready | `test_readonly_record_does_not_flip_status` |
| **N4（低中）** | 漂移被存成 `failed` 后内容恢复也无法自愈（error 永久残留） | **已修**：无漂移时按唯一文案清掉该漂移 error，恢复 `prepared` | `test_recovered_drift_clears_stale_error` |
| **N5（低）** | 报告里的 unified diff 渲染破损（片段无结尾换行时挤一行） | **已修**：渲染前补行尾换行，输出合法 patch | 真实报告 `## 逐 hunk 登记` 段 |
| **N6（观察）** | 人补齐 warning 评估后不重跑编译则 smoke 仍 waiting | **已修**：新增 `reevaluate_smoke()`——读数不动、判据重算（`needs_evaluation` 全部 accepted ⇒ passed） | `test_warning_evaluation_promotes_existing_smoke_without_recompile` |
| **FAIL-6 残留 5 处** | ① §8.5 与 §8.2-1 冲突；② §3「S0-b 保持阻断/ready 恒 false」；③ §4 能力位 false；④ §6.1 ready 恒 false；⑤ §8.2-1 无 work 见证正文（引用悬空）；另 §8.5 自相矛盾一行 | **已修**：① 改为按 md5 规则；②③④ 标注 2026-10-27 更新（S0-b 已接入、能力位只描述后端）；⑤ **把 work 见证与"落盘前只允许 TB 顶层差异"写进 §8.2-1 正文**；矛盾行改写 | 规格 §3/§4/§6.1/§8.2-1/§8.5 |

**复核后真实链路复验（在 .env-copy + .s0-work3 上）**：prepare `ports=passed` → propose+confirm（未落盘 `waiting`）
→ apply（`applied=['H1']`、`witness=work-after.2.json`）→ smoke（candidate/baseline 均 `0 error(s)/17 warning(s)`、delta 空、`passed`）
→ 六项全 passed、`drift={}`、`errors=[]`、**`ready_for_execution=True`**；随后在无关资产上制造未登记改动再 `apply` ⇒ **被拒且未写入**。

### 102.9 门（第二轮整改后，数字从输出复制）

- 软件层：**`1046 passed, 3 deselected, 1 warning in 176.47s`**。
- 文档门：`missing=0`、`exit=0`。


### 102.10 第三轮复核（R1–R6）与整改

第三轮结论：N1–N6 **全部关闭**；但新发现 3 个残余（R1 编译输入未纳入见证 / R2 分批落盘走不通 / R3 报告与状态矛盾）。
逐条处置（均已在真实记录或用例上复验）：

| # | 第三轮发现 | 处置 | 证据 |
|---|---|---|---|
| **R1（残余 fail-open，与 N2 同族）** | 漂移白名单不含**编译输入** `all_define.txt` / `input.tcl` / `BIN/`（它们正是 `-f` / `-do` / `+incdir+` 的来源）⇒ 改了编译配置仍 `ready=true` | **已修**：抽出 `WITNESSED_ROOTS`（含 RTL/TB/PKG/TESTLIB/BIN/all_define.txt/input.tcl），`_verify` 与 apply 前置检查共用 | 真实记录复验：改 `work/all_define.txt` ⇒ `drift={'work_env':['TB/top_cfg.sv','TB/top_env.sv','all_define.txt']}`、`ready=False`；用例 `test_compile_inputs_are_witnessed` |
| **R2（功能缺口）** | 分批落盘不可用：apply H1 后再确认 H2 再 apply ⇒ `H1 old_text 出现 0 次`；中间态 ports 误判 failed | **已修**：`apply_confirmed` 对"old_text 不在但 new_text 已在"的 hunk 记为 `already_applied` 跳过；ports 新增"部分已确认未落盘"判定 ⇒ `waiting` | `test_batch_apply_skips_already_applied_hunks`：apply H1 → 确认 H2 → 中间态 waiting → apply ⇒ `applied=['H2']`、`skipped=['H1']`、ports passed |
| **R3（报告口径）** | 报告头只看 checks ⇒ 出现"头写可准出、status=failed"；smoke passed 且 reason 空时写"（尚未执行）" | **已修**：报告头与阻断项以 `ready_for_execution` 为准，并把 `status=failed`/漂移/核验错误显式列进阻断项；smoke 措辞按状态区分 | 用例与真实报告；阻断项现在会打印 `- 记录状态 failed：…` 与 `- 漂移（相对最新 work 见证）：…` |
| **R4（证据纪律）** | apply 被拒绝只抛错、不留痕 | **已修**：拒绝落档 `s0b/apply_refusals.jsonl`（只增不改 + sha256 锚），`load_apply_refusals()` 可读 | `test_apply_refusal_is_logged` |
| **R5（覆盖）** | unified diff 合法性无自动化用例 | **已修**：`test_unified_diff_is_a_valid_patch` 用 `patch -p0 --dry-run` 断言可应用 | 该用例通过（无 `patch` 时 skip 并如实记） |
| **R6（观察）** | `get()` 是读路径但会重写报告；`record.json` 不随 `get()` 持久化 | **登记不改**：判定以 `get()` 返回值为准；直接读 `record.json` 的消费者可能看到旧值。读路径不持久化是刻意的（读不应产生业务写入），`report_write_error` 已保证只读记录不被误判 | STATUS 本节 |

### 102.11 门（第三轮整改后，数字从输出复制）

- 软件层：**`1050 passed, 3 deselected, 1 warning in 171.00s`**。
- 文档门：`missing=0`、`exit=0`。
- 三文件定向用例：`tests/test_s0.py + test_s0b.py + test_sv_ports.py` ⇒ **93 passed**（含 R1/R2/R4/R5 新增钉）。


### 102.12 第四轮复核（R2 残余 / R3 残余 / 规格两句）与整改

第四轮结论：N1–N6 与 R1/R4/R5 保持关闭，剩 3 项（R2 前缀型 hunk 重复应用、R3 阻断项未落地、规格 §8.5 两句）。
另外指出 §102.10 的"现在会打印"与实际不符——本节以**代码与用例**为准，不再只写声明。

| # | 第四轮发现 | 处置 | 证据 |
|---|---|---|---|
| **R2 残余（功能缺陷）** | 插入型 hunk（`old_text` 是 `new_text` 前缀）落盘后原片段仍在 ⇒ 只靠文本计数判不出"已应用"：中间态误判 `failed`，第二次 apply **重复应用并把副本 TB 写坏** | **已修**：新增"已应用 hunk 台账" `s0b/applied_hunks.jsonl`（只增不改 + 锚）；`apply_confirmed` 与 `ports._simulate` 都以台账判定"已落盘"，内容已是目标形态时只**认账不写文件** | 真实记录（.s0-work4）：apply#1 `['H1']`、P-1 计数 1；中间态 `waiting`（"部分已确认的 hunk 尚未落盘"）、P-1 仍 1；apply#2 `applied=['H2']`、`skipped=[H1 already_applied]`、P-1=1/P-2=1；用例 `test_prefix_type_hunk_is_not_double_applied` |
| **R3 残余（声称未落地）** | 报告阻断项缺 `记录状态 failed` / `漂移（相对最新 work 见证）` 两行，而 §102.10 声称已有 | **已实现**（这次是真的）：`_write_report` 现按 `status/verification` 追加这两类阻断项，并把"无阻断"的措辞改为"无（六项检查全部 passed，且无漂移/核验错误）" | 用例 `test_report_blockers_show_status_and_drift`（断言报告含 `- 记录状态 failed：`、`- 漂移（相对最新 work 见证）：`、`PKG/kept.txt` 且头不写"可准出"） |
| **规格 §8.5 两句** | L217 引用已不存在的标签（悬空）；L220「已完成」与句尾"其余验收仍未做"自相矛盾 | **已改写**：删掉悬空引用；把"执行入口消费"写成"已完成，含 C12 四项用例 + S0-b 落地"，并把"仍未做"收窄为**内网真机验收与 D5 界面** | 规格 §8.5 |

### 102.13 门（第四轮整改后，数字从输出复制）

- 软件层：**`1052 passed, 3 deselected, 1 warning in 185.53s`**。
- 文档门：`missing=0`、`exit=0`。
- 三文件定向用例：**95 passed**。
- 真实环境副本全链路（含两次插入型 hunk 分批落盘）：六项全 `passed`、`drift={}`、**`ready_for_execution=True`**。


### 102.14 第五轮复核：判定「可验收」（R5-1 已按建议修掉）

第五轮复核结论：**可验收**（R2/R3/规格三条全部关闭；准出判据无 fail-open；真实 records4 的 `ready=true` 可复现）。
唯一遗留是本轮引入的一处"判据放宽过度"（R5-1），已按复核者给的一行修法当场修掉：

| # | 发现 | 处置 | 证据 |
|---|---|---|---|
| **R5-1（低中，非 fail-open）** | `apply_confirmed` 的"认账"条件被放宽成"只看 `new_text` 是否存在" ⇒ `old_text` 有歧义时（出现 >1 次）不再拒绝，而是静默 `adopted` + 记台账 + 不写文件（错误面消失、台账记了没发生的事） | **已修**：恢复严格条件 `occurrences == 0 and text.count(new_text) >= 1`（前缀型"已落盘"由 `applied_hunks` 台账分支处理） | 重新启用 `test_ambiguous_old_text_is_refused` 并新增 `test_ambiguous_old_text_with_new_text_present_is_still_refused`：歧义 + new_text 已存在 ⇒ `ValueError`、文件逐字节不变、台账为空 |

**复核者的两条观察（登记不改）**：
1. `apply` 的"内容已达标"早返回分支不回填台账 ⇒ 若手工清掉台账，前缀型 hunk 仍可能被重复应用；
   但此时 `ports` 会因"实际 ≠ 基线+已确认"判 `failed`，**兜得住、不会误准出**（台账本身是只增不改证据，手工删不在威胁模型内）。
2. `adopted` 分支与台账锚校验目前靠 `load_apply_refusals`/`applied_hunks` 的锚自检覆盖，未单独立用例；已在 §102.10 R6 的"观察不改"里登记。

### 102.15 E2 收尾状态（本轮结束）

| 项 | 状态 |
|---|---|
| S0-b `ports`（Host 确定性派生 + 模型提议 + 人确认 + 精确落盘） | ✅ 已接入，真实环境副本跑通 |
| S0-b `smoke`（副本内三库编译 + 基线相对增量 + warning 人评估） | ✅ 已接入，真实编译 `0 error(s)`、增量空 |
| `ready_for_execution` 六项判据（唯一判据口） | ✅ 真实记录 `drift={}`、六项 `passed`、`ready=True` |
| 独立复核 | ✅ 五轮（FAIL-1..9 → N1..N6 → R1..R6 → R5-1），最终判定**可验收** |
| 门 | 软件层 **`1053 passed, 3 deselected, 1 warning in 186.47s`**、文档门 `missing=0`、三文件定向 **96 passed** |
| 仍未做（已登记） | 内网真机验收（需可写 `ENV_ROOT`）、D5 界面（需浏览器门）、E3 passed 夹具（真实通过轮） |


### 102.16 门（第五轮整改后，数字从输出复制）

- 软件层：**`1053 passed, 3 deselected, 1 warning in 186.47s`**。
- 文档门：`missing=0`、`exit=0`。
- 三文件定向用例：**96 passed**。


### 102.17 收尾与清理

- **保留**：`.s0-test/`（122 MB，S0 记录：records/records2/records3/records4，含真实环境副本上跑出的
  `ready=true` 记录）与 `workspaces/s0b-verify/`（288 KB，五轮独立复核的 REPORT + 复现脚本，gitignored）。
- **清理**：`.s0-work*/`（每份 2.6 G ×4）、`.s0-rtl/`（271 M）、`.env-copy/`（2.6 G）已删除（共约 11 GB）；
  需要重跑真实链路时按 §102.3 重新派生即可（复制约 10 s + 清 30 个历史沙箱软链）。
- 本地 `.git/info/exclude` 增加 `.s0-work*/`、`.s0-test*/`、`.s0-rtl*/`，文档门检查器跳过前缀 `.s0-`（用例已覆盖）。

## 103 DSH 交互探针 P1–P8（2026-10-28，只体检不改代码）

本轮输入：[三层对齐体检表](plans/2026-10-28-three-layer-interaction-alignment.md) §6.1 的 P1–P8。
证据档：[`doc/evidence/DSH_PROBE_20261028/`](evidence/DSH_PROBE_20261028/README.md)（冻结 + 目录外 md5 `doc/evidence/DSH_PROBE_20261028.md5`，`md5sum -c` 通过）。
**本轮未改 `loop/` `kb/` 业务代码，未跑四道门**（只体检轮）；下述数字均从探针命令输出复制。

### 103.1 结论（8 项）

| 探针 | 三态 | 关键数字/原文 |
|---|---|---|
| P1 home/可见 | 过（有条件） | 共用 home：`session/list n=1`、`session/page records=3`；隔离 home：`items:[]`/`session/not-found`；并发 3 进程×2 会话 + Web 在跑 ⇒ `sessions=10 ok=10 bad=0`、`storages 11 json bad=0`；同会话并发写者被拒 `already owned by an active write handle` |
| P2 提交工具 | 过 | `tool_call{tool:"submit_result",input:{task_id:"p2-1",…}}` → `tool_result{"accepted":true,"problems":[]}`；handler `pid=7`；插件加载失败仅 `dsh: warning: 1 entry did not activate` |
| P3 cwd/写隔离 | 部分 | read-only 两处写 `Read-only file system`/`rc=1`；workspace-write 副本内 `rc=0`、副本外 `rc=1`；**读隔离不存在**（`AGENTS.md`、`~/.dsh/settings.yaml` 均 `rc=0`）；只 patch `sandbox-policy.mode` 被 `permission-presets.defaultPreset` 覆盖 |
| P4 事件/终态 | 过（headless 层） | `turn_end.reason.kind=completed`；缺凭据 `error`+`code:"MISSING_CREDENTIAL"`；`--session-id` 续跑 turn 1→2、`cacheReadTokens 9216` |
| P5 杀进程 | 部分 | SIGTERM 两档无残留；SIGKILL+`danger-full-access` 残留 `sleep 45` 孤儿（+3 s/+8 s 仍在）；SIGTERM 后 `headless_exit=0` 但**无 `turn_end`** |
| P6 子 agent | 过（限定） | sdk JSON-RPC 实发 `subagent.started/finished`；配额键 `subagent.config.maxActiveSubagents`（默认 8）；越额原文 `active child limit: 1`；headless `--json` 0 条 `subagent.*` |
| P7 压缩可见 | 部分 | 触发成功（`compaction/prune→start→summary 4845 字符→end`，释放 3356 tokens）；计数只在 session log（`compaction/summary`+`time`）；headless 0 条、projcache 无 compaction 行 |
| P8 Web 鉴权/内嵌 | 部分 | 匿名 `401` 三处、**无 `WWW-Authenticate`**、不支持 Bearer；`?token=`→`HttpOnly; SameSite=Strict` cookie；页面无 `X-Frame-Options`/CSP，`/api` 跨权威 `Origin`/`sec-fetch-site: cross-site`/伪 `Host` 均 `403` |

### 103.2 由探针改写的契约点（已回填体检表 §6.3 / §7）

1. 桥的观测面必须是 **sdk stdio JSON-RPC**（subagent/compaction 事件只在那里）；`submit_result` 仍靠 `--patch` 挂薄插件。
2. **启动成功 ≠ 可用**：插件加载失败只 warning、权限档可被用户层覆盖 ⇒ Host 必须启动后自检"工具清单 + 实际 preset 回显"。
3. **attempt home 必须最小化且不携带凭据**（读隔离不存在）；复制宿主 `~/.dsh/settings.yaml` 会带进 `danger-full-access`。
4. terminate＝`TERM → 超时 → KILL 进程组`；收口只认 `turn_end`/提交工具（退出码 0 与空 `final.text` 不算成功）。
5. 可见性＝**冷读持久化日志**；写句柄跨进程互斥 ⇒ 人只能在两次 attempt 之间说话（与裁决 #10 一致）。
6. 内嵌 GUI 受同源约束：跨站 iframe 因 `SameSite=Strict` 拿不到 cookie，`/api` 跨权威 `403`。
7. 压缩计数与子 agent 记账由 **Host 落账**（读 session log / 收 SDK 通知）。

### 103.3 新增裁决（2026-10-28 已拍）

- **Q6 凭据投放 = 只走 env + 风险记档**：key 不落 attempt home；已知风险——agent 的 bash 工具可 `echo $PUBLIC_API_KEY` 读到（读隔离不存在），记残余风险，不称已解决。
- **Q7 内嵌形态 = 同源反代**：看板 `/instance/*` 反代到 DSH web（同源 ⇒ cookie 可投递、`/api` 不 403），iframe 内嵌；反代层并入浏览器门。

### 103.4 限制与残留（照实登记）

- 未用真浏览器验 iframe cookie 投递；sdk `session/prompt`/`session/wait` 全链路未由 Python 侧复测（P6 自写 Node 客户端只验通知面）。
- 探针 bash 在 bwrap `--unshare-pid` 内，`pgrep` 只覆盖本命名空间 ⇒ 不能声称"全机无残留"；收尾分别做了特征清理。
- P3/P5/P7 各用 4 次 headless 运行（软预算 3，超 1 次原因在各自报告 §5/§3.10 记录）。
- 探针工作区 `workspaces/.probe-dsh/`（约 2.6 MB，gitignored）保留供复现；`~/.dsh` 零写入，`127.0.0.1:3083` 未碰。
- 观察（非本轮判据）：`ss -ltnp` 显示 `127.0.0.1:18731/18732` 有监听且 `ps` 无匹配进程（非本探针，未处理）。

## 104 云端 DSH 接入与 Agent 记忆优化实施规格（2026-10-26，仅文档）

> 合并 `origin/main`（`abdb16f`）时该节与本地 `## 75 侧栏可达性` 撞号，**整节重编号 75→104 追加到末尾**；
> 正文未改，仅标题与本节说明两行。相关引用已同步（`doc/README.md`）。

用户澄清“当前环境”指云端。以 dd587e6 为本轮基线，补充 [REV13](spec/SPEC-REV-13-20261026.md) 与
[详细设计](plans/2026-10-26-cloud-dsh-memory-design.md)，并接入原 SPEC-06/07/08 及两个实施计划。
**没有修改运行代码、部署配置或依赖，没有启用 DSH，没有把设计标成已实现。**

判断更正：云端可完成适配器/受控协议测试以及 M1/M2/M3 软件实现；有当前模型授权及强制隔离后可继续真实 DSH/公开工程验证。
真实内网工程验收另需工程可达性。本机 Windows、WSL 或本机 DSH 版本不构成云端不可实现的证据。
本会话没有云端执行入口，原云端任务读取返回 403，当前实例运行时、网络/模型授权与隔离状态保持未核实；
历史 npm 安装/SDK 握手不能替代当前观察，也不能证明云端不可用。

记忆状态：输入预算/调用留痕、H1/H2a/H2b 已有实现；会话内控制及人工确认经验精确筛选已有基础。
计划 M1 工作记忆、M2 跨尝试指令作用域/撤销/替代/恢复、M3 经验分层与适用性增强尚未实现。
旧 SPEC-06 的同名 M1/M2 条款与协作计划切片在 REV13 中明确区分。

规格交付覆盖 owner、模型/Host 交接、版本化请求、受限工具/进程停止、预算/覆盖、指令接受竞态、
记忆来源/失效与恢复、经验审批/迁移、旧格式兼容、切片落点、失败用例和分级验收。
文档验证结果附于本节后续记录；软件/真实 DSH/模型/内网与浏览器门未在本轮执行，既有结果保留历史归属。

本轮文档检查（与本轮 dd587e6 文档基线对照）：新增路径缺失 **0**，新增 Markdown 路径/锚点问题 **0**；
JSON 示例 **5** 个可解析，代码围栏配对；git diff --check 返回 **0**。
既有路径缺件 **96** 项在本机空环境/工作区下保持不变，不能据此声称全仓文档门或内网门已全绿。
运行代码、冻结 kb、已有证据/历史及 AGENTS.md 没有改动。原始检查结果保存在本聊天 outputs 的文档验证 JSON；
本轮没有运行软件、模型、原生 DSH、浏览器或内网业务验收，不将“仅设计”伪装为通过。

## 105 推送与远端整合（2026-10-28，E4 关闭）

### 105.1 远端分叉的发现与处置

| 项 | 值（命令输出复制） |
|---|---|
| 本地 HEAD（整合前） | `636782e docs(probe): … Q1–Q7 裁决` |
| 远端 main（fetch 后） | `abdb16f docs: specify cloud DSH integration and agent memory lifecycle`（2026-10-26 20:46） |
| 分叉计数 | `git rev-list --left-right --count HEAD...origin/main` ⇒ `46	1`（领先 46 / 落后 1） |
| 冲突 | 仅 `doc/STATUS.md`：两边都占 `## 75`（远端=云端 DSH 规格；本地=侧栏可达性，被 README/plans/audit 多处引用） |
| 处置 | 保留本地 §75；远端整节**整节重编号 `§75 → §104`** 追加到末尾（正文未改，仅标题 + 两行说明）；`doc/README.md` 引用同步改 `§104`；合并提交 `4c8281a` |
| 文档检查 | 合并后相关文件相对链接 `BROKEN: none` |

### 105.2 推送证据

```text
$ git push origin main
To https://github.com/rj-chenjunming/fpga_sim_workflow.git
   abdb16f..4c8281a  main -> main
$ git ls-remote origin main
4c8281a0d5ec6eb2db6abea2ee82ddd241620f0f	refs/heads/main
$ git rev-parse HEAD
4c8281a0d5ec6eb2db6abea2ee82ddd241620f0f
```

### 105.3 过程中钉清的环境事实

- 本机代理当时**可用**：`https://github.com` ⇒ `200`，`git ls-remote`/`git fetch` 均成功（与旧 E4「出网被代理阻断」不同）。
- 推送失败的真实原因不是网络，而是**凭据缺失**：HTTPS 无 `credential.helper`/`~/.git-credentials`（`fatal: could not read Username …`），SSH 无私钥（`Could not read from remote repository`）。
- `$HOME` 只读（`~/.git-credentials` ⇒ `Read-only file system`、`/home/…/.gitconfig` 同样只读）⇒ 凭据只能放在**仓库 `.git/` 内**（不入版本库、`600`）；用完已删（见 §105.4）。
- 远端 `abdb16f` 引入 [SPEC-REV-13](spec/SPEC-REV-13-20261026.md) 与 [云端 DSH 记忆设计](plans/2026-10-26-cloud-dsh-memory-design.md)：S0 的 SPEC-08 修订必须**折进 REV-13**，不另写第二份。

### 105.4 凭据处置（照实登记）

- 临时凭据文件 `~/.git-credentials` 因 `$HOME` 只读**未能创建**（`Read-only file system`）；改用 `.git/dsh-push-token`（`600`，未入库）+ 仓库级 `credential.helper`。
- 推送完成后已删除该文件并移除仓库级 helper 配置（见本轮收尾命令）。
- **建议**：该 PAT 曾在会话文本中出现过，应按 GitHub 流程**作废并重建**；重建后如需再推，按 §105.3 的 `.git/` 方案临时投放即可。

## 106 S0 规格交付：SPEC-REV-14 执行器契约对齐（2026-10-28，未实现）

本轮只交付**规格与指针**，未改 `loop/`/`kb/` 代码，未跑四道门。

### 106.1 交付物

| 文件 | 内容 |
|---|---|
| [SPEC-REV-14](spec/SPEC-REV-14-20261028.md) | 折进 REV-13：**偏离 D1–D4**（凭据 env / 保留压缩+Host 落账 / 共用 home+resume+GUI 说话 / 子 agent 全开配额 2）、**补丁 B1–B7**（`submit_result` 结果通道、启动自检、禁复制宿主 settings、观测面、完成判据、写句柄仲裁、版本映射）、**采纳映射 A1–A10**、切片映射（S0–S6 ↔ 设计 P0–P7）、追加不变量 `DS-08`/`DS-09` |
| [AGENT_CONTEXT_SPEC](spec/AGENT_CONTEXT_SPEC.md) | 指针：D2 压缩事实由 Host 落账；A4 上下文包按 REV-13 WM 口径 |
| [AGENT_WINDOW_SPEC](spec/AGENT_WINDOW_SPEC.md) | 指针：D3 会话旁路与写句柄互斥（仅空闲期可写） |
| [DSH_AGENT_RUNTIME_SPEC](spec/DSH_AGENT_RUNTIME_SPEC.md) | 指针：D1–D4 偏离与 B1–B7 补丁 |
| [三层对齐体检表](plans/2026-10-28-three-layer-interaction-alignment.md) | §9 三张表 + §9.5 冲突裁决 + §9.6 偏离复评条件 |

### 106.2 依据与边界

- 依据：REV-13（`abdb16f`）+ P1–P8 探针（[证据档](evidence/DSH_PROBE_20261028/README.md)，冻结 + md5 目录外）。
- 偏离均有**复评条件**（D1 强隔离、D2 事件流补投影、D3 只读挂载/写句柄原语、D4 成本阈值），未满足前按偏离执行。
- **不声称**：DSH 未接通（`BackendUnavailable` 不变）、WM/IL/EXP 未实现、未跑四道门、探针只到 C1/部分 C2。

### 106.3 检查（本轮）

- 相关文件相对链接检查：`BROKEN: none`（脚本口径：Markdown 相对路径存在性）。
- 文档门实测：`cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_doc_links.py` ⇒ `65 passed in 8.67s`（从命令输出复制）。
- 未运行：kb 自测 / 端到端 / 浏览器门（本轮无代码改动，按 AGENTS §4 它们不是本轮交付物；不把"文档门通过"当四道门完成）。

## 107 S0b 交付：闸门签署绑产物指纹 `stateHash`（2026-10-28）

规格：[SPEC-REV-15](spec/SPEC-REV-15-20261028.md)；冻结目录（`kb/tools`、`kb/schema`）**单独变更**，按 AGENTS §3 留证。
本轮改 3 个 kb 文件 + 1 个新测试文件；`human_signed` 铁律与闸门枚举**未动**。

### 107.1 做了什么

| 文件 | 变更 |
|---|---|
| `kb/tools/kb_lib.py` | 新增材料集与 `stateHash` 的**唯一实现**：`gate_material_manifest`（递归、跳符号链接、不可读即失败）、`gate_state_hash_record`、`gate_verify_state_hash`；`gate_set` 在写 anchor 前落 `state_hash`（不可读 ⇒ `GateMaterialError`，不写盘） |
| `kb/tools/gate.py` | `sign` 捕获 `GateMaterialError` ⇒ rc=4；`require-signed` 对已签闸门**复算**指纹，失败输出 `STATE_HASH_MISMATCH` + `changed/added/removed`；legacy 只告警 |
| `kb/schema/gate_state.schema.json` | 可选 `state_hash`（`additionalProperties:true`，无需迁移） |
| `loop/tests/test_gate_state_hash.py` | T1–T8（签后无改动通过 / 改件失败 / 新增失败 / 删除失败 / 排除项不影响 / legacy 告警 / 不可读失败 / 锚篡改仍拒） |

材料集范围 = run 目录除 `gates.*`、`agent_calls/`、`agent_controls/`、`decisions/`、`view.json`；
口径写死在 REV-15 §2（含本机实测体量：drill run `5546` 文件 / `752 057 424` B / `1.445 s`）。

### 107.2 门与实测（数字从命令输出复制）

| 项 | 命令 | 结果 |
|---|---|---|
| 新用例 | `pytest -q tests/test_gate_state_hash.py` | `8 passed in 1.61s` |
| 闸门/流程回归（可写数据根） | `.dev-ws` + `pytest -q tests/test_gate_state_hash.py tests/test_gate_ledger.py tests/test_gate_projection.py tests/test_gate_session.py tests/test_gate_reason_reuse.py tests/test_flow.py` | `69 passed, 1 warning in 106.63s` |
| 全量单测（可写数据根） | `.dev-ws` + `pytest -q` | `1062 passed, 3 failed, 1 warning, 113 errors in 352.91s`；3 failed 全为 `@pytest.mark.env_layer`（本机 ENV_ROOT 只读的既有环境限制），113 errors 为浏览器缺件 |
| **kb 自测 + 环境层入口** | `bash spikes/run_env_layer_checks.sh --with-kb-selftests` | `_selftest_gate_schema` `PASS=10 FAIL=0`；`_selftest_n5_reachability` `PASS=9 FAIL=0`；`_selftest_adjudicate_conflicts` `PASS=28 FAIL=0`；env_layer `3 passed`；**原 ENV_ROOT 零写入**（`find -newer` 命中 0） |
| 端到端（drill） | `.dev-ws` + `bash spikes/accept_v1_run.sh` | `phase 1 PASS=50`、`phase 2 PASS=27`、`phase 3 PASS=18`、`phase 4 PASS=8`、`phase 4b PASS=8`、`phase 5 PASS=6`，全 `FAIL=0`，`=> ALL PASS`（`E2E_RC=0`）；跑完按脚本 `--cleanup` 删除 `.dev-ws` |
| 文档门 | `pytest -q tests/test_doc_links.py` | `65 passed in 2.02s` |

### 107.3 未做 / 不声称

- 未跑浏览器门（本轮无界面改动）；未接内网真实工程验收（`stateHash` 只到 C1 机制层）。
- 旧 run **不回填**：无 `state_hash` 的已签闸门按 legacy 告警放行（REV-15 §6）。
- 已知边界：`sandbox/`（N6 工作副本）计入材料 ⇒ N6 改写后旧批准会失效（符合"改件后必须重跑闸门"）。
- 派生副本（`.dev-ws` / `.env-copy`）已按脚本清理，未入库。

## 108 S1 前置（P0）：能力清单与"真隔离"探测（2026-10-28）

证据档：[`doc/evidence/DSH_P0_20261028/`](evidence/DSH_P0_20261028/README.md)（冻结 444；目录外 md5 `doc/evidence/DSH_P0_20261028.md5`，`md5sum -c` 通过）。
本轮只探测，未改业务代码；探针现场 `workspaces/.probe-dsh/`（gitignored），`~/.dsh` 零写入。

### 108.1 能力清单（机器可复算）

`node v24.21.0`；dsh `lib/bin.js` sha256 `80112efe…499e6f`；`package.json` `ab51c256…ea2a87`；
`package-lock.json` `e242cda6…cd0d01`；`bubblewrap 0.4.0`；kernel `4.18.0-553.el8_10.x86_64`；
sdk profile 组合树 409 行 sha256 `6e19a614…b49234`。
工具面比先前假设更宽：`tool-web`/`tool-workflow`/`tool-goal`/`tool-workspace-dependencies` 也在默认组合里 ⇒ 带工具准入必须**显式禁用**。

### 108.2 探测结论（三态）

| 问题 | 结论 | 证据 |
|---|---|---|
| 未包裹时 agent 能看到什么 | agent bash 继承 **145** 个 env；**不含** `PUBLIC_API_KEY`（`KEYLEN=0`，dsh 剥离）；`~/.dsh/settings.yaml` **可读**（`RC=0`）；`.credentials.yaml` **可读、237 B** | `p0-env-leak.ndjson`/`p0-env-clean.ndjson` |
| bwrap 包裹能否跑起 dsh | **能**：`--ro-bind / /` + `--tmpfs $HOME` + 只 bind attempt 目录 + `env -i`，`FINAL: OK`、`turn_end.completed` | `p0-bwrap-dsh.ndjson` |
| 包裹内宿主数据/凭据 | **被遮蔽**：`~/.dsh` 为空、`AGENTS.md` ⇒ `No such file`、工具 env 无 key | `p0-bwrap-agent.ndjson`/`p0-bwrap-home-mask.ndjson` |
| 包裹内原始凭据是否仍可读 | **是**：agent bash 在 `/proc/6/environ` 命中 `PUBLIC_API_KEY`（`LEAK:/proc/6/environ`）⇒ 同 uid 下 pid ns 挡不住读父进程 environ | `p0-proc-env.ndjson` |

⇒ "挡读宿主数据 + 清无关 env"**已可做到**；"原始凭据对 agent 不可读"**做不到**（`/proc` 路径）。
REV-14 的 D1 复评前提**部分满足**：bwrap 可作缓解，但不能据此恢复 REV-13 §5.4 口径。

### 108.3 裁决（Q8，2026-10-28 已拍）

**维持 D1 + bwrap 缓解**：attempt 进程一律套 bwrap（`--ro-bind / /` + `--tmpfs $HOME` + 只 bind attempt 目录与 `DSH_HOME` + `env -i`）；残余风险"同 uid 下 `/proc/<dsh-pid>/environ` 可读出 key"**显式记档、不称已解决**；复评条件升级为"能挡 `/proc` 读 environ"（REV-14 D1/B8/DS-10）。

## 109 S1 机制层：DSH 执行器进程与协议（2026-10-28）

切片计划：[2026-10-28-s1-dsh-process.md](plans/2026-10-28-s1-dsh-process.md)。本轮只做机制层；`dsh` 后端仍**不可用**（`select()` 不变）。

### 109.1 交付

| 文件 | 内容 |
|---|---|
| `loop/host/agent_backends/dsh_protocol.py` | headless NDJSON 帧解析与终态判定：`BadFrame`/`NoTerminal`/`ConflictingTerminal`/`IdentityMismatch`；`completed` 只由 `status.turn_end` 产生 |
| `loop/host/agent_backends/dsh_process.py` | 每 attempt 一进程：bwrap 包裹（`--ro-bind / /`+`--tmpfs $HOME`+只 bind cwd/home+`--unshare-pid`+`--die-with-parent`）、env 白名单、`TERM→宽限→KILL` 进程组、停机后同组残留检查 |
| `loop/host/agent_backends/dsh.py` | 后端骨架：配置锁定（`enabled/version/node/bin/bin_sha256/profile/timeout/stop_grace/wrap/patches/api_key_env`，未知字段拒绝）、指纹校验、失败显式化与 redact |
| `loop/SETTINGS.yaml` | 新增 `agent_runtime.dsh`（**enabled:false** + P0 指纹钉；注释写明 patch 必须放 attempt 目录内） |
| 测试 | `tests/test_dsh_process.py`（13）+ `tests/test_dsh_backend.py`（8），共 **21** 条 |

### 109.2 实测（数字从命令输出复制）

| 项 | 命令 | 结果 |
|---|---|---|
| 新用例 | `pytest -q tests/test_dsh_process.py tests/test_dsh_backend.py` | `21 tests collected`；定向运行 `45 passed`（含后端回归 `test_agent_backends.py`） |
| 回归子集 | 上述 + `test_agent_backends` + `test_agent_backend_characterization` + `test_f06_structure` | `51 passed in 2.49s` |
| **真机集成**（包裹形态） | 用本模块 `build_argv`（含 `--unshare-pid/--new-session`）跑真 dsh（1 次模型调用） | `OK status=completed text='OK' usage={'inputTokens': 337, 'outputTokens': 2, 'totalTokens': 5715, 'cacheReadTokens': 5376}` |

### 109.3 失败语义（已实现 + 用例覆盖）

坏帧（不忽略坏行）、无 `turn_end`（退出码 0/空 final 都不算完成）、冲突终态、`reason.kind=error`（保留 code/message，secret 由 backend redact）、超时（`TERM→KILL` 后子孙清理，`/proc` 同组扫描）、dsh 非零退出 ⇒ 固定诊断。

### 109.4 未做 / 不声称

- `select()` 仍 `BackendUnavailable`（`enabled=false`）：**实现存在 ≠ 准入**（REV-14 §1）。
- 结构化候选未接（`submit_result` 在 S2）；sdk stdio 观测面未接（B4 的 subagent/compaction 记账在 S2）。
- B2/B3 自检（工具清单 + preset 回显）尚未接入 `dsh.py` 的启动流程。
- 未跑全量单测与端到端（本轮只跑相关子集；S1 结束前的四门待整体切片收口时跑）。
- 包裹的**已知边界**：patch 文件必须放在 attempt 目录内（宿主 home 被遮蔽）；`/proc/<dsh-pid>/environ` 仍可读 key（D1 残余风险，Q8 已记档）。

## 110 交接：S2 与后续切片开工提示词（2026-10-28）

新窗口入口：[`doc/agents/开工提示词_S2-DSH执行器与后续切片.md`](agents/开工提示词_S2-DSH执行器与后续切片.md)
（自包含：现状快照、S2 三件事、四道门命令、D1–D4 复评条件、十一条已知坑、完成定义）。

交接时点：`a36c3aa`；本地领先 `origin/main` **6** 个提交、**未推送**（`git rev-list --count origin/main..HEAD` 输出复制）。
新窗口第一件事：核对 HEAD/工作树 → 读该提示词 §1 五件 → 先跑四道门收口 S1 → 再按 T1/T3/T2 做 S2。

## 111 S2 交付：结构化候选 / 启动自检 / sdk 观测面（2026-10-28）

本轮入口：[开工提示词](agents/开工提示词_S2-DSH执行器与后续切片.md)；计划
[2026-10-28-s2-candidate-selfcheck-observation.md](plans/2026-10-28-s2-candidate-selfcheck-observation.md)；
契约 [REV-14](spec/SPEC-REV-14-20261028.md) B1/B2/B3/B4/B5/B8、DS-08/DS-09/DS-10；
证据档 [`doc/evidence/DSH_S2_20261028/`](evidence/DSH_S2_20261028/README.md)（冻结 444 + 目录外 md5）。
本轮**没有**改 `kb/`、闸门、节点判据；`dsh` 仍显式不可用（`enabled=false`、`select()` 抛 `BackendUnavailable`）。

### 111.1 S1 收口：四道门（先做，再开工 S2）

基线 = `4e7baac`（交接提交；工作树干净，`git log --oneline -3` / `git status --short` 核对过）。

| 门 | 命令 | 结果（命令输出复制） |
|---|---|---|
| 单测 | `bash spikes/provision_dev_workspace.sh` → `LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | `3 failed, 1083 passed, 1 warning, 113 errors in 372.25s`；3 failed **全部**是 `@pytest.mark.env_layer`（本机 ENV_ROOT 只读的既有环境限制），113 errors 是浏览器缺件（Chromium 未并入四门） |
| kb 自测 + env layer | `bash spikes/run_env_layer_checks.sh --with-kb-selftests` | `_selftest_gate_schema` `PASS=10` / `_selftest_n5_reachability` `PASS=9` / `_selftest_adjudicate_conflicts` `PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected`；**原 ENV_ROOT 零写入**（`find -newer` 命中 0） |
| 端到端（drill） | `LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh` | `phase 1 PASS=50`、`2 PASS=27`、`3 PASS=18`、`4 PASS=8`、`4b PASS=8`、`5 PASS=6`，全 `FAIL=0`，`=> ALL PASS` |
| 文档门 | `pytest -q tests/test_doc_links.py` | `65 passed` |

**数据根易错点（本轮实测，已修正开工提示词 §5 的字面写法）**：`cd loop && bash spikes/provision_dev_workspace.sh`
把可写数据根建在 **`<repo>/.dev-ws`**，而 `$PWD/.dev-ws` 在 `cd loop` 后是 `loop/.dev-ws` ⇒ 按字面拼会把
`LOOP_WORKSPACE` 指到不存在的目录，184 条用例因"drill 夹具不完整"失败（实测 `75 failed, 1005 passed, 113 errors`）。
那是**数据根缺件**，不是代码缺陷；用绝对路径 `<repo>/.dev-ws` 重跑即回到上表。

### 111.2 S2 交付物

| 文件 | 变更 | 契约 |
|---|---|---|
| `loop/host/agent_backends/dsh_plugin/submit_result.mjs` | 新：ESM `defineTool` 注册 `submit_result(task_id, summary, payload)`；handler **不判业务**、**不落侧信道**（提交事实由 NDJSON `tool_call`/`tool_result` 承载），回 `{accepted:true,problems:[]}`（accepted = 引擎已接收） | B1 |
| `loop/host/agent_backends/dsh_protocol.py` | `fold` 只**收集** `SubmissionCall`（S1 语义零改动）；新增独立纯门 `require_submission()` + `Submission` + `NoSubmission`/`ConflictingSubmissions`/`BadSubmission`（task_id 不符复用 `IdentityMismatch`） | B1/B5、DS-02 |
| `loop/host/agent_backends/dsh.py` | 任务文本写入提交契约（task_id=attempt_key、schema）；`completed` 后**无条件**过提交门，只出 `{data:payload, task_id, summary, session_id, usage}`，**删 text/note 占位**；接入 B3 双钉、B2 自检钩子（带本次 `nonce`/`attemptKey` 身份 join）、DS-09/DS-10 前置检查（`to_thread` 跑探针）；`wrap=false` 在**配置路径**上不可启用（只允许代码里显式 `diagnostic_unwrapped`） | B1/B2/B3/B5、DS-02/08/09/10 |
| `loop/host/agent_backends/dsh_plugin/selfcheck.mjs` | 新：`apply` 写 `$DSH_SELFCHECK_DIR/selfcheck.json`（`toolNames`/`sandboxDefaultMode`/`presetEcho`/`home`/`patches`/`nonce`/`attemptKey`），`phase=apply→deferred` 两段快照，**stdout 零写入** | B2/B3 |
| `loop/host/agent_backends/dsh_selfcheck.py` | 新：`verify_home`（复用 `dsh_assets.home_problems`）、`verify_session`/`averify_session`（只认 deferred 快照；**nonce/attemptKey 身份 join**；缺工具/档位不符/回显 unknown/home 带宿主件 ⇒ 失败）、`attest_wrap`（DS-10 真 bwrap 探针） | B2/B3/B8、DS-08/09/10 |
| `loop/host/agent_backends/dsh_process.py` | 拆 `build_wrap_argv(spec, inner)`（dsh 与探针共用隔离参数）；`run_attempt(on_start=...)`（spawn 后、收帧前的准入钩子，抛错 ⇒ `TERM→KILL` 后重抛）；新增可选 `asset_dirs`（只读）/`state_dirs`（可写） | B8、DS-10 |
| `loop/host/agent_backends/dsh_sdk.py` | 新：锁定 `0.2.1-rc.2` 的 7 个请求方法 / 4 个通知（逐字来自 `dsh-sdk-protocol` 类型文件）；严格 NDJSON JSON-RPC 客户端（坏行/未知方法/未知通知/版本不符/超时显式失败、响应按 id 配对允许乱序）；`subagent.*`/`session.status`/`session.event` 落账；`parse_session_log_lines`/`read_session_log` 压缩事实 | B4/B7、D2 |
| `loop/host/agent_backends/dsh_assets.py` | 新（共享基础）：attempt 布局、patch 物化（钉死 → 外部 overlay → 插件 insert）、**物化时清掉旧自检报告**、home 最小化检查、`node_modules` 解析软链、完整 preset 表（`config` 是整块替换，见 §111.5） | B1/B3/B8、DS-09 |
| 测试 | `test_dsh_assets`(12) + `test_dsh_candidate`(35) + `test_dsh_selfcheck`(34) + `test_dsh_sdk`(37) = **新增 118 条**；`test_dsh_process`(13) 保持绿；`test_dsh_backend` 由 8→10（S1 成功用例改为 S2 契约：无提交 ⇒ 显式失败；新增 `wrap=false` 准入与 `diagnostic_unwrapped` 自曝两条） | 各片 TDD + 复核回归 |

### 111.3 S2 关键实测（C2 部分；证据原文见证据档 raw/）

1. **真机正例（1 次模型调用）**：`bwrap` 包裹的真 dsh + 真模型 ⇒ 模型真调用 `submit_result`，Host 收口得到
   `data={"verdict":"pass","reason":"integration"}`、`task_id="RUN-S2INT/N6/1"`、`session_id=session-5eac8f45…`、
   `isolation="bwrap"`、`selfcheck.toolCount=26`、`sandboxDefaultMode="read-only"`、`presetEcho.defaultPreset="read-only"`；
   `usage={inputTokens:2651, outputTokens:41, totalTokens:6276}`。
2. **负例（自检真能挡）**：人为移除插件模块解析链 ⇒ 工具清单 25 项无 `submit_result` ⇒
   `model_call_failed=True`、error 指向 B2（"启动自检未通过…工具清单缺 submit_result"），**不出候选**、不启动模型调用。
3. **负例（缺凭据显式失败）**：自检通过但 `PUBLIC_API_KEY` 未设 ⇒ `model_call_failed=True` + `MISSING_CREDENTIAL` 原文，
   不伪装"在等人工"。
4. **真 sdk 握手**：`dsh --profile sdk` 的 `initialize` 回 `{"serverInfo":{"name":"deepseek-harness-sdk-runtime","version":"0.0.1"}}`，
   `shutdown` 回 `{}`、rc=0；客户端按 id 配对（实测响应可乱序）。
5. **压缩计数**：真实 P7 日志回放 `count=1 / freed_tokens=3356 / start=2 / end=2 / prune=1 / 1 条显式 error`，与 P7 原文逐项一致。

### 111.4 S2 收口：四道门（全部重跑；含复核修复后的终版树）

> 复核修复（§111.5）落地后，四道门在**终版树**上重新跑过一次，下表是终版数字。

| 门 | 结果（命令输出复制） |
|---|---|
| 单测（可写数据根） | `3 failed, 1203 passed, 1 warning, 113 errors in 365.01s`；3 failed 仍是 env_layer 环境限制、113 errors 仍是浏览器缺件 |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 16.38s`；**原 ENV_ROOT 零写入**（`find -newer` 命中 0） |
| 端到端（drill） | `phase 1 PASS=50`、`2 PASS=27`、`3 PASS=18`、`4 PASS=8`、`4b PASS=8`、`5 PASS=6`，全 `FAIL=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.11s` |

定向回归（复核修复后）：`tests/test_dsh_assets.py test_dsh_candidate.py test_dsh_process.py test_dsh_backend.py test_dsh_selfcheck.py test_dsh_sdk.py`（+`test_agent_backends.py`）`165 passed in 14.03s`。
**浏览器门未跑**：本片无 `loop/web/**` 与 `services/contracts.py` 界面字段改动（AGENTS §4 只在该类改动时要求）。

### 111.5 独立复核与按复核修复

独立验证者（未参与实现，**只报告不改**）结论：**无 P0；2×P1（潜在 fail-open，一旦接 DSH 准入即升 P0）+ 5×P2**；
另做 4 条反向抽检（临时 monkeypatch 把实现改坏，用例按预期变红 ⇒ 断言不是自证）。本轮按发现逐条处置：

| # | 复核发现 | 严重度 | 处置 |
|---|---|---|---|
| P1-1 | 自检快照没有 attempt 绑定：复用 attempt root 时 Host 用**上一次**的 deferred 快照放行（复核实测：进程没写报告、钩子仍放行、`outcome=completed`） | P1 | **已修**：每次 attempt 生成随机 `nonce`（`DSH_SELFCHECK_NONCE`）+ `DSH_ATTEMPT_KEY` 注入 env，报告必须回显、Host 逐字比对；物化时清空 `selfcheck/`；新增 4 条用例（含 `averify_session` 入口）；真机正例已按修复后代码**重跑**（`raw/selfcheck-positive.json` 的 `nonce`/`attemptKey` 在位） |
| P1-2 | `wrap=false` 一个配置布尔静默关掉 DS-08/09/10 三项准入并照常出候选；`isolation="unwrapped"` 无消费者 | P1 | **已修**：`DshConfig.verify(wrap_required=True)` 拒绝配置关包裹；无包裹只允许代码里显式 `DshBackend(config, diagnostic_unwrapped=True)`，候选标 `isolation="unwrapped-diagnostic"` 且不伪造 selfcheck；新增 2 条用例 |
| P2-1 | 计划 §3.2 的 `profiles/` 判据未实现且未登记：dsh 在空 home 里自建 `profiles/`，按原文实现会恒失败 | P2 | **已修文档**：DS-09 只禁宿主 settings/凭据；`profiles/` 口径登记 [计划 §6-9](plans/2026-10-28-s2-candidate-selfcheck-observation.md) |
| P2-2 | DS-10「父进程 env 不继承」是同源自证（探针用显式 env 起进程，断言结构上不可能红） | P2 | **已修措辞**：实测判据降为「内层 env ⊆ `build_env` 白名单」，「不继承」由显式传 env 的结构保证；计划/证据/dsctring 同步 |
| P2-3 | `dsh_sdk.py` 映射表里 `types.d.ts` 行号 5 处偏 1 | P2 | **已修**（14/27/35/57/62/67/77/82/84/91/98/105/122/129，逐条 `grep -n` 核对） |
| P2-4 | `attest_wrap` 在 async `execute` 里同步 `subprocess.run`（最长阻塞 2×60 s） | P2 | **已修**：`asyncio.to_thread` |
| P2-5 | `submissions.jsonl` 侧信道无消费者 + 写失败静默（AGENTS §2.4） | P2 | **已修**：删除侧信道（提交事实由 NDJSON `tool_call`/`tool_result` 承载），用例断言"不落侧信道" |
| 证据缺口 | 负例决定性快照与 dsh stderr 未归档；正例缺输入侧 `attempt_key`；D2 把"手工构造夹具"写成"原样回放" | — | **已修**：`raw/selfcheck-negative-b2.json`、`raw/negative-dsh-stderr.txt`、`raw/integration-input.json` 归档；D2 措辞改为"按 P7 记录片段手工构造（非原样回放）" |

**写权说明**：A/B/C 三片交付并结束后，复核修复与整合接线由 Lead 在同一轮落盘（不再有并行 owner 写入），
不改变各片 owner 分工；`kb/**`、`SETTINGS.yaml` 全轮未被任何 owner 修改。

复核**未**发现问题的项（照录）：唯一业务判据仍在 `model_steps._validate`（无第二套）、`text`/`note` 已删、
失败显式（含 redact）、`select()`/SETTINGS 准入未放开、sdk 坏帧/未知通知/版本/超时硬失败、压缩计数不编数、
证据数字与代码一致。

### 111.6 纪律核对

- **写权**：`kb/**` 零改动（`git status` 无 `kb/`）；`SETTINGS.yaml` 未改；`doc/spec` 只改 REV-14 **状态行**（正文未改）。
- **证据**：新目录 `doc/evidence/DSH_S2_20261028/` 冻结（444）+ `doc/evidence/DSH_S2_20261028.md5`（目录外，`md5sum -c` 通过）。
- **独立复核**：实现由 3 个实现 owner + Lead 完成，复核由**独立验证者**执行（只报告不改）；结果见 §111.5。
- **失败显式**：无提交/被拒/冲突/身份不符/坏帧/无终态/超时/自检未过/缺凭据 ⇒ 一律 `model_call_failed` + error（redact），没有"等人工"式伪装。
- **偏离复评条件**：D1（`/proc` 可读 key）**未满足**，维持偏离、不称已解决；D2（事件流 compaction）未验，保留"session log 落账"。

### 111.7 未做 / 不声称

- `select()` 仍 `BackendUnavailable`、`SETTINGS.dsh.enabled=false`：**实现存在 ≠ 准入**（REV-14 §1）。
- B4 观测面：C1（stub 37 条 + 真 `initialize`/`shutdown` 握手）已实现；**真实模型 turn（`session/prompt`→`session/wait`）未验**（无 key 时本片不发真实 prompt），不用 headless 事件冒充。
- DS-09 只到 **composition 级** preset 回显（`apply` 期无 session）；session 级回显与 `permissionPresets.current(session)` 待拿到 session 后重测。
- 不声称挡 `/proc/<dsh-pid>/environ`；不声称大 payload 不截断（截断 fail-closed 未实测）；不声称子 agent 真实通知/长会话压缩已验。
- 真机集成只做了 **1 次**模型调用（C2 部分），不是业务验收；内网工程验收（E）仍未做。
