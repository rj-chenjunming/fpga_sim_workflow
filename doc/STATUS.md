# 项目状态（唯一数字源）

> **本文件是数字的唯一权威**。其它文档引用这里，不各自抄一份。
> **本次采样**：2026-10-19T18:02+0800（修复轮终验，四道门全绿）；采样命令与输出见各节（数字一律复制，不手算）。
> **最新补充采样**：2026-10-21 云环境优化、S0 与 Agent 工作窗口，见 §7–§10；后续优化整理见 §11；全站网页视觉升级见 §12；下一阶段执行手册与当前复核见 §13。旧采样保留为历史；本轮没有四道门全绿。
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
