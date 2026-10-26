# `loop/` — 变更影响闭环的编排层与操作界面

> **数字口径**：本文件不内嵌单测/断言数量；当前实测以 [`doc/STATUS.md`](../doc/STATUS.md) 为唯一数字源。
> 下文出现的 `117`/`70`/`94` 等字样是 2026-10-19/20 的**历史采样**，已在原处标注。

> **Agent 工作窗口**：在“运行监控”点击角色卡片或名字进入。可看当前节点的事件、完整输入、提示词快照、输出及 Host 校验；checker 可切换 N8/N10，尝试选择器可查历史。填写 `human:<name>` 后可补充指令并重跑、暂停、恢复或终止当前节点，动作由服务端下发。暂停/重跑会取消本地旧请求并新建尝试，旧响应不进入下游；终止使本轮按失败收敛。关闭窗口不停止执行。当前暂停限服务进程存活期间，重启后历史只读；远端推理取消取决于提供方。契约见 [Agent 工作窗口](../doc/spec/AGENT_WINDOW_SPEC.md)。

> **S0 工作台增量**：默认首页为“环境准备”，契约见 [S0 环境准备](../doc/spec/S0_ENVIRONMENT_SPEC.md)。填写完整基线、新 RTL、版本声明和新副本绝对路径，执行完整派生与内容核验；已有目录不覆盖。允许路径沿用服务端浏览根配置，可通过 `LOOP_BROWSE_ROOTS` 扩展挂载目录（页面可展开查看范围）。准备记录在本软件 `loop/state/s0`，报告和派生 context 位于各记录目录；不覆盖用户 context。S0-b 接口适配、三库驱动、新版执行入口尚未接入，页面持续显示阻断。现有运行与闸门通过左侧工作台导航访问，保持旧契约。

> **全站网页视觉升级**：深墨侧栏、雾白工作区和青绿操作色；环境准备、配置、监控、人工闸门、目录浏览器、Agent 窗口与旧界面共享视觉令牌。仅浏览器网页，无桌面客户端或手机端专项适配。侧栏可用方向键、Home/End 切页，页面提供“跳到工作区”键盘入口。契约见 [Web UI §14](../doc/spec/WEB_UI_SPEC.md#14-全站网页视觉系统2026-10-21)，预览和验证见 [网页重设计证据](../doc/evidence/WEB_REDESIGN_20261021.md)。

> **状态**：P0 可运行（drill 全链历史验收 117/117；审计阻断项已修复并补回归；2026-10-20 已在真实环境副本上 **real N0→N8 跑通**——证据见 `doc/evidence/REAL_RUN_SCN_RTL_0D04_20261020.md`；更长的 N9 真实全跑仍未做。以上为历史/能力描述，当前实测数字见 STATUS）。
> **上游契约**：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（业务与不变量 I1–I8）
> **本层契约**：`doc/spec/LOOP_ORCHESTRATION_SPEC.md`（owner / 生命周期 / 长任务 / 准入 / 恢复 / 投影）

---

## 1 这层是什么

把上游 16 个节点（N0–N16）与三道人工闸门落成**可交互、可重启、可拒绝**的系统：

- **编排**：`agently` TriggerFlow 的稳定拓扑（源码内定义），3 道闸门 = durable graph interrupt；
- **界面**：FastAPI + 无框架静态页（`index.html` + 按功能拆分的 `app.js` / `s0.js` / `agent-window.js` /
  `run-view-state.js` / `capabilities.js` + 共享 CSS 令牌，零外链、无构建步骤）—— 两区运营台：
  配置（基线/项目目录）→ 运行（四段流程 + agent 卡）→ 闸门操作；旧界面存档在 `legacy.html`；
- **准入**：单槽（`uvs.setup` 是仓库根下全局单文件）+ 队列 + 取消；
- **恢复**：执行快照 + 记录库，跨进程重启后能重新附着到在跑的作业。

### 它不是

- 不是第二个状态机。**状态权威 = TriggerFlow 执行 + `kb/tools/gate.py`**；界面只是只读投影 + 传输。
- 不重新实现业务判定。N2/N5/N16 一律调用既有 `kb/tools/*.py`。
- 不写冻结资产。`ENV_ROOT/{RTL,TB,PKG,TESTLIB,doc}`、`<WORKSPACE_ROOT>/{baselines,index,conflicts,runs}`、
  `kb/{tools,schema}` 全部只读（`host/paths.FROZEN_FOR_WRITE` / 各写者守卫）。

---

## 2 快速开始

> **运行前提（拆仓后）**：本层是**独立软件**，环境是**插件**。环境与数据位置登记在
> `environments.json` 里 ⇒ **直接 `./run.sh` 即可**，零配置。
> 需要临时指到别处时用环境变量覆盖（优先级高于注册表）：
> ```bash
> export LOOP_ENV_ROOT=<环境仓路径>    # 被守卫的 RTL/TB/PKG/TESTLIB + doc + uvs.setup
> export LOOP_WORKSPACE=<数据根路径>    # 该环境的 index/conflicts/baselines/runs
> ```
> 软件根（TOOL_ROOT）自锚定、不需要配置；任一必需项缺失时**fail closed 并说明缺什么**，
> 绝不猜路径。三个根的解析规则与插件契约见 `doc/spec/ENV_PLUGIN_SPEC.md`。
>
> **快照纪律**：只允许落**干净停车**的快照 —— 已派发完（`resume_count >= max_resumes`）的中断
> 一律不落盘（`_is_clean_park`）。半截快照 load 得进来，但恢复时必然失败
> （`interrupt ... is not waiting`）。见 §4.6。
> `/api/health` 会外显 `plugin_missing`（环境缺件）与 `workspace_missing`（数据找不到）。

```bash
cd loop
./run.sh                      # 默认 http://127.0.0.1:8099
LOOP_PORT=9000 ./run.sh       # 换端口
```

> **远程访问（Windows → 服务器）**：服务只绑 `127.0.0.1`，远程一律走 SSH 隧道；
> 服务器侧用 `bash loop/remote/serve.sh`（或 `--sandbox` 用可写副本），
> Windows 侧用 `loop\remote\connect-loop.bat` / `.ps1`。详见
> [`loop/remote/README.md`](remote/README.md)。

> **人工操作手册**（起服务 → 配置 → 三道闸门 → 终点判读/排障）：
> [`../doc/UI_RUNBOOK.md`](../doc/UI_RUNBOOK.md)。

环境已建好（Python 3.11.7 + agently 4.1.4.8）：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
```

**`agently` 钉 4.1.4.8**：技能文档与参考工程都对齐这一代 API
（`flow.to/when/for_each`、`execution.pause_for/continue_with`）。
镜像上有更新版本（4.1.4.10），但其 `TriggerFlow` 表面已重构，不为未文档化的 API 猜签名。

跑测试：

```bash
cd loop && .venv/bin/python -m pytest -q      # 用例数/耗时见 doc/STATUS.md
```

运行 UI 特征与异步交互回归（真实 Chromium，API 使用受控响应；不需要环境仓夹具）：

```bash
cd loop
.venv/bin/python -m pip install -r requirements-ui.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests/browser -q
# 使用系统 Chromium 时：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest tests/browser -q
```

未安装 Playwright 时浏览器测试会明确跳过，不能据此声称 UI 已验证。测试范围与重构约束见
[`会话可靠性计划`](../doc/plans/2026-10-21-ui-session-reliability.md)；整体优化顺序见
[`工作流优化评估`](../doc/audit/AUDIT-20261021-workflow-priorities.md)。

**只读沙箱 / 无 `~/.cache` 时的实测要点（2026-10-26）**：
- 浏览器下载目录不在仓外：`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers`。
  **当前仍建议单独跑浏览器门、不并入全量单测**，但理由已从「稳定性未修」变成「时长与口径」：
  未装 Chromium 时 browser 用例以 setup 错误计入（快，不影响软件层结论）；装上后全量执行约
  120 s（2026-10-26 实测 108 passed），叠加在单测 301 s 之上会让门变慢，且仍需可写
  `HOME`/`TMPDIR` 与浏览器二进制，不适合作为软件层门的硬前置。
  直连下载被代理掐断时加 `PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright`。
- 系统 Chrome 需要**可写 HOME/TMPDIR**（只读 HOME 会让 Chrome 启动即退）：
  `HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome`。
- **浏览器门现状（2026-10-26 更新，数字见 `doc/STATUS.md` §75.6）**：
  `tests/browser/test_web_layout.py` **12 passed**、`tests/browser/` 全量 **108 passed / 0 failed**。
  此前两条根因已闭合：①替身没给上游 U2-a/U2-b 的两条 SSE 端点打桩（已补显式 404 桩，degrade 到轮询回退）；
  ②`aside` 是 sticky 视口高容器却 `overflow:visible`，矮视口下「最近运行」条目落在视口外且
  **页面滚动无法救回**（已改为侧栏自身滚动，契约见 [WEB_UI_SPEC §14](../doc/spec/WEB_UI_SPEC.md)、
  判据 A10）。**仍不等于 UI 已全面验证**：浏览器用例只覆盖受控替身下的布局与交互，
  真实后端长连接与视觉核对仍需人工；移动端（窄于 ≈371 px）不做适配，属契约外（§1/§12/§14）。

内网无法连接 PyPI 时，仓库提供 [Rocky Linux 浏览器离线包](offline/README.md)：

```bash
# 在 loop 目录；已有项目 .venv，无需 pip 联网或 playwright install
.venv/bin/python spikes/browser_offline.py install
.venv/bin/python spikes/browser_offline.py run
```

支持 Rocky Linux 8.10 / x86_64 / glibc 2.28 的 Python 3.11；另附 Python 3.12 wheel。
优先复用系统 Chrome，缺浏览器时使用 Git 内的备用运行时；共享库缺件会显式失败。来源、校验和、强制随包版本与缓存位置见离线说明。

Agent 上下文与记忆规则见 [`AGENT_CONTEXT_SPEC`](../doc/spec/AGENT_CONTEXT_SPEC.md)：新调用在本 run 的
`agent_calls/` 下保存输入、规则版本、输出与校验；已确认经验由人维护，按来源和作用域只读筛选。
使用与核验命令见该规格末节；独立测试为 `tests/test_agent_context_memory.py`，不要求内网仿真夹具。

---

## 3 目录

```
loop/
  run.sh                    启动（uvicorn）
  requirements.txt          运行/测试依赖（agently 钉 4.1.4.8）
  pytest.ini                测试配置
  SETTINGS.yaml             provider 非机密配置（密钥不落仓库）
  host/                     host 侧 owner（不碰业务判定）
    paths.py                三根锚定（复用 kb_lib 解析器）+ 冻结守卫
    admission.py            单槽准入 / 队列 / 审计（N9-3 修复：锁带 format_version）
    job_runner.py           长任务提交 / 看护 / 重附着 / 取消
    progress.py             稳定应用事件投影（白名单 kind）
    evidence.py             两套口径与观测印记的**抽取器**（数字全由文件数出）
    gate_authority.py       闸门枚举的唯一来源（取自 kb_lib，本层不手抄）
    model_provider.py       provider 解析/注入（env → SETTINGS.yaml → 宿主 DSH）
  workflows/
    context.py              一次运行的 host 依赖（经 runtime_resources 注入）
    main_flow.py            稳定拓扑 N0–N16 + RunManager（生命周期/恢复/投影）
    chunks/host_steps.py    N0 N1 N2 N5 N7 N16（调 kb 工具）
    chunks/model_steps.py   N3 N6 N8 N10 N11 N12（真 ModelRequest + Host 校验；见 §5）
    chunks/long_jobs.py     N9 提交+停放 / N15 回归
    chunks/gates.py         三道闸门（pause/resume + 显式分叉）
  prompts/                  节点 request 契约（loop_nodes.yaml + node_schemas.py）
  services/
    contracts.py            对外投影 + 六项信任缺口的服务端判定
    api.py                  FastAPI（唯一入口）
  web/index.html            运营台骨架（左栏 + 配置/运行/闸门三视图）
  web/app.js                会话协调 owner：数据层/轮询/渲染装配/目录浏览器/闸门提交（零外链）
  web/s0.js                 环境准备（S0-a）视图
  web/agent-window.js       Agent 工作窗口（观察 + 请求边界干预）
  web/run-view-state.js     运行详情展示状态唯一判据（加载/首次失败/陈旧/恢复）
  web/capabilities.js       能力事实唯一格式化（角色卡与工作窗口共用）
  web/tokens.css            主工作台与旧界面的共享视觉令牌（零外链）
  web/app.css               主工作台组件与页面布局
  web/legacy.html           旧界面存档（保留一个迭代）
  web/legacy.css            旧界面的配套视觉样式
  web/mockup.html           v1 设计样张（只读参考）
  tests/                    用例数见 doc/STATUS.md（含 UI 契约与冒烟）
  spikes/                   `accept_v1.py`（带断言的 v1 终验）+ `accept_v1_run.sh`（单次调用内起停 4 代服务）
  state/                    槽/队列/事件/快照（可删）
```

真实终验报告在 `doc/evidence/ACCEPTANCE_V1.md`（2026-10-19 历史验收 117/117，3 次真重启；已移出本目录；现行见 STATUS）。

---

## 4 四条会让人踩坑的设计决定

### 4.1 长任务必须"停放"而不是"阻塞"

`agently-triggerflow/references/recovery.md:75-77`：快照里若有 `running` 帧，**`load` fail-closed**。

所以 N9 拆成两段：

```
n9_submit: 申请单槽 → 提交外部作业 → 记 job_id 进 state → 返回
n9_park:   pause_for(type="job_done", resume_to="self")
           ← 此刻执行是 interrupt，不是 running ⇒ 快照可落可载
           外部完成 → job_runner 看护回调 → execution.continue_with(...)
```

**必须用 `resume_to="self"`**：用 `"next"` 时 `pause_for` 的返回值是**中断描述符**而非恢复载荷，
本 chunk 永远看不到作业结局，死任务会被静默当成继续（这是实测到的真 bug）。

恢复后**以日志为权威重新取数**，不信任 resume 载荷里的数字。

### 4.2 单槽是 host 持有的，不是 TriggerFlow 并发

`uvs.setup` 是本仓库根下的全局单文件 ⇒ 同工作目录最多一个仿真/编译。
`concurrency=N` 在这里是错的。真正的并行只跨机（`run_tc.py`，5 机 × 2 LIC）。

**锁带 `format_version`**：陈旧判定按格式版本决定解析哪些字段；
遇到不认识的格式**拒绝自动清理并升级人工**（N9-3：误删活动锁曾导致约 10 分钟无互斥）。

**终态必须释放**：成功/失败/取消都要释放且幂等。修复前死任务会把槽永久占住，
把一个 run 的失败放大成后续全体挂起。

### 4.3 闸门枚举不许手抄

`kb_lib.GATE_DECISIONS` 是唯一来源：

| 闸门 | 权威枚举 |
|---|---|
| `G1_diff_confirm` | `confirmed` / `ignored` / `disputed` / `pending` |
| `G2_report_accept` | `accept` / `rework` / `pending` |
| `G3_regression_decision` | `full_now` / `subset_only` / `milestone_only` / `defer` / `pending` |

本层曾自造 `full_regression` / `escalate_to_human` / `ignored_with_reason`，
结果用户点到一个权威不认的值，收到的是 argparse 用法错误而不是业务拒绝。
现在：`host/gate_authority.py` 从 `kb_lib` 导入，`chunks/gates.validate_branches()` 做漂移自检，
`run_view.gate_options` 把枚举下发给界面 —— **前端只渲染，无从漂移**。

**`pending` 是状态，不是可提交动作。**

### 4.4 拒绝必须发生在提交前

I6（非 human actor）与 I4（冲突未清零时选全量/子集回归）都在
`RunManager.decide()` 里**先判**，再签、再恢复。

原因：`pause_for(resume_to="self")` 的 `max_resumes=1`。若阻断发生在恢复之后，
用户的一次误选就会消耗掉中断并把执行打成 `failed`（实测 `self_resume_limit_reached`），
**闸门从此不可用**。现在误选得到 403/400，闸门保持待决策。

### 4.5 v1 终验抓出的 9 个缺陷（都已修，见 `doc/evidence/ACCEPTANCE_V1.md`）

这份验收的价值主要不在"全绿"，而在它**把只靠读代码看不出的问题逼出来了**。逐条要点：

| id | 一句话 | 关键回归 |
|---|---|---|
| F-V1-01 | 拒绝路径**先写权威账本后查中断** ⇒ 双击按钮会在 `gates.json` 留一条**孤儿签名** | 拒绝后 `gates.json` md5 不变 |
| F-V1-02 | 操作台的「闸门历史」来自**事件流**（actor 是自报、无 `human_signed`），而前端在渲染服务端**从不发送**的 `actor_kind` ⇒ 徽章恒空；"谁签的"答不了 | 投影 `gates_authority` + 逐门对账 `divergences` |
| F-V1-03 | `POST /api/runs` 的 `now` 被静默丢弃 | `test_start_honors_now` |
| F-V1-04 | `auto_close=False` 关掉了唯一会置 CLOSED 的机制 ⇒ **`finished` 是死代码**，HALT/N16 后永远 `running`，重启还会反复恢复僵尸 run | `reached_terminal()` + 显式 `async_close` |
| F-V1-05 | `_persist_finish` 写副本、`poll()` 留原记录 ⇒ **崩溃恢复把死任务当正常完成**投递，run 带 `koutou1=null` 走到 G2 | 相位一律回读 `JobRunner.poll()` |
| F-V1-06 | 落快照靠"某次 `async_sync` 恰好看到 waiting_gate" ⇒ 盘上只剩上一份 ⇒ 重启**回退到已签闸门** | 0.5 s 快照节拍 + 落后于账本时显式失败 |
| F-V1-06c | 快照停在**已终结作业**中断上 ⇒ run 永久卡在 `JOB:`（补投递已发生在落盘之前） | `_stale_job_interrupts()` 按 `JobRunner.poll()` 权威相位强制重投递 |
| F-V1-07 | 投影**不带 `error`** ⇒ 失败的 run 在界面上只剩一个 "failed" | 投影补 `error`/`notes`，前端醒目渲染 |
| F-V1-08 | 重投递复用旧 `resume_request_id` 被 TriggerFlow **静默拒绝** ⇒ run 永久卡住 | 换新 id + 投递后核验中断已被消费 |

还有一条同类的字段名与内容不符：`decision` 响应的 `gate_state` 原先装的是子进程调用记录
（`cmd`/`rc`/`stdout_tail`）⇒ 已拆成 `gate_state`（权威态）/ `gate_tool`（调用记录）/ `gates_authority`。

### 4.6 快照与权威账本的关系（**新增的硬纪律**）

快照是"某一刻"的执行影像，`gates.json` 才是权威。恢复时两者可能不一致：崩溃落在两次落盘之间，
载入的快照会停在**已经签过**的闸门上。此时本层的选择是**显式失败并说明原因**
（`snapshot_behind_ledger`），**不是**自动重放那个决定 —— 重放等于在没人要求的情况下自动重跑
一整轮修订 + 仿真（可能是几十分钟的外部作业）。宁可红，也不静默替人推进。

---

## 5 当前限制（不得当成已具备）

| 项 | 现状 |
|---|---|
| 模型节点 | **已接真 ModelRequest**：N3/N6/N8/N11/N12 走宿主已声明的 provider（`openai-responses`，`origin-deepseek-v4-1-flash`），5/5 实测 live 且 Host 校验零问题。凭据不可用时自动退回**显式标注**的确定性替身（`standin=True`），离线测试即走此路径。 |
| N10 对账 | **数字与分桶归 Host**（`host/evidence.py`，确定性、零丢失：夹具上 1622/1622 地址、1687/1687 条目），**三分类归模型**（24 个桶逐桶判定）。Host 校验覆盖性/枚举/依据，并交叉核对「本轮引入」是否真落在修订点上（不重叠的断言记为冲突且不采信）。夹具实测：模型把 24/24 桶判为既有缺陷 ⇒ 1687 条目，Host 冲突 0。 |
| real 模式 | N9 已改为经 `kb/tools/run_guarded.sh --mode full`（身份头 + 归档 + 自愈 + 串行锁），但**未在真机跑过一次完整全跑**（单用例 ≈19 min，修订后可达 22.8 h）；归档腿本身已用 `uvlan` 桩在真实代码路径上验证。 |
| N15 回归 | drill 下不真跑；`for_each(concurrency=1)` 已就位，跨机 `run_tc.py` 未接。 |
| N16 晋升 | 本层**恒为 `--dry-run`**，绝不写 `<WORKSPACE_ROOT>/baselines/`。 |
| F-N16-04 | 拒绝后残留 `staged/` 仍在（界面作为告警呈现，未清理）。 |
| E-2 | **已修**：`run_guarded.sh` 归档腿原只 glob `$ROOT/SIMLIB_RUN/log`，与 `compile-only`/`full` 实际落点 `$EVIDENCE_DIR` 不符 ⇒ 必空；且这两个模式没启动轮询。现候选路径覆盖两处、两分支都轮询、归档件 444 只读、加稳定性判定防半截件堆积、`_guard.log` 不自我归档；N9 真实路径也改为走 `run_guarded.sh --mode full`。归档的演练轮**不回填**（它是冻结见证）。 |
| 单机单用户 | 无鉴权、无多用户；`actor` 只是自报字符串（**权威凭据是账本里的 `human_signed`**）。 |
| 快照竞态窗口 | 0.5 s 节拍把"重启回退到已签闸门"的概率压到很低，但**未消除**：窗口内被杀 ⇒ 恢复会显式失败（见 §4.6），需人工重开一轮。 |
| 单槽 `holder_alive` 语义 | 当前由 `host/admission.py::_owner_alive` 按锁里的 `owner_pid` + `/proc` starttime 判**进程**存活；重启后 `owner_pid` 指向已死的 uvicorn，于是 `holder_alive=false`，而作业其实还活着（`phase=running`）。本轮实测未发现别的 run 能借此抢占；该字段应改判“**作业**是否存活”而非“进程是否存活”，**待办**。 |
| I3 判绿 | 口径一 = 1687 ≠ 0 是**既有缺陷**（不是本轮引入）。三选项/推荐/成本见 `<WORKSPACE_ROOT>/adjudication/I3_dual_count_dispute.md`，**需人拍板**；在拍板前 `I3_KOUTOU1_NONZERO` 维持 blocker。 |
| 冲突清零 | 72 条全 `blocks_release=true` ⇒ 晋升永久阻断。分组、批裁判据、清零路径见 `<WORKSPACE_ROOT>/adjudication/C_conflicts_triage.md`，**需人拍板**。 |

---

## 5.1 模型接入（provider）

配置在 `SETTINGS.yaml`（非机密）+ `host/model_provider.py`（解析与注入）：

1. **密钥不落仓库**：优先 `$LOOP_LLM_API_KEY`，其次宿主 DSH 凭据库
   `~/.dsh/.credentials.yaml` 的 `refs.<apiKeyEnv>`。对外投影（`/api/health`）**不含密钥**。
2. **端点不硬编码**：留空即复用宿主 `~/.dsh/settings.yaml` 已声明的 provider，
   避免在仓库里再抄一份内部地址而漂移。
3. **proxy 必须显式设**：插件 `request_builder.py:324` 写死
   `client_options.setdefault("trust_env", False)` ⇒ 环境代理**不会**被 httpx 读取。
   不设直接 DNS 失败（实测 `[Errno -2] Name or service not known`）。
   留空则取 shell 的 `HTTPS_PROXY/HTTP_PROXY`。
4. **`max_tokens` 要给足**：本网关模型是推理模型，32 tokens 会被 `reasoning_content` 吃光、
   `content` 为空且 `finish_reason=length`（实测）。
5. **`LOOP_LLM_MODE=standin`** 强制离线（测试套件默认如此）；`live` 要求必须真拿到 provider。

契约分三处、各归其主：

| 关注点 | 归属 |
|---|---|
| 字段形状（类型/必填/枚举）| `prompts/node_schemas.py`（Pydantic）|
| 行为规则（info / instruct 散文）| `prompts/loop_nodes.yaml` |
| 确定性验收（数字一致性、offered-key 成员性、否决规则）| `workflows/chunks/model_steps.py::_validate` |

**为什么形状用 Pydantic 而不是 YAML**：YAML 没有元组，`["str", "说明"]` 会被解析成列表，
于是模型把标量返回成单元素列表（实测 `verdict=['rework']`、`assessment=[...]`），
`counts_quoted` 变成空字典。

验证装置（可复跑）：

```bash
cd loop
.venv/bin/python spikes/probe_provider.py        # 端点连通 + 最小请求
LOOP_LLM_MODE=live .venv/bin/python spikes/verify_live_nodes.py   # 5 个语义节点逐个 live
LOOP_LLM_MODE=live .venv/bin/python spikes/verify_live_n10.py     # N10 分桶分类 live（Host 抽数+模型分类）
.venv/bin/python -m pytest -q                    # 离线（替身）；数量见 doc/STATUS.md
```

## 6 drill 夹具

`<WORKSPACE_ROOT>/runs/RUN-20261015-120626/**`（**只读**；当前 `WORKSPACE_ROOT = ENV_ROOT/kb`）。选它是因为一个目录同时覆盖：
双计数分歧（口径一 1687 / 口径二 `UVM_ERROR=0`）、死任务、印记三向一致、
闸门拒绝、篡改检测、staging 残留 —— 而真实全跑不能作为交互开发循环。

drill 与 real 的差别**只在节点数据来源**，运行目录两者都是 `<WORKSPACE_ROOT>/runs/<run_id>`
（硬约束：`kb/tools/gate.py` 经 `kb_lib.run_dir` 唯一口径解析路径；根由
`$LOOP_ENV_ROOT` / `$LOOP_WORKSPACE` 或 `environments.json` 注册表决定，见 `doc/spec/ENV_PLUGIN_SPEC.md` §1）。

drill 运行目录带 `.loop_drill` 标记，测试据此清理**自己创建的**目录，绝不触碰归档。

**本地需要可写数据根时**（本机 `WORKSPACE_ROOT` 常常就是只读的 `ENV_ROOT/kb`，而软件层测试要写
`runs/`、slot、events）：

```bash
cd loop
bash spikes/provision_dev_workspace.sh        # 复制 drill 夹具 + baselines/index/conflicts/adjudication
                                              # 到 <repo>/.dev-ws（约 738 MB，不入库）
LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
bash spikes/provision_dev_workspace.sh --cleanup   # 跑文档门前必须清理
```

不预置数据根时，drill/基线相关用例会因「夹具不完整 / 基线为空」失败 —— 那是环境缺件，
不是代码缺陷（口径差异见 `doc/STATUS.md` §71.5）。数据根出现在仓库内时，
`doc/audit/check_doc_links.py` 会把拷贝来的环境文档一并扫入，故**文档门要在清理之后跑**。

**drill 情景**：`happy`（拷夹具全跑日志）/ `dead_job`（`kill -9 $$`，无 rc ⇒ 必须判死）/
`cancel`（`sleep 120`，从界面取消）。

---

## 7 已验证什么

`tests/`（数量见 STATUS）+ 一次**真实 HTTP 终验**（2026-10-19 历史采样 117 断言）（`doc/evidence/ACCEPTANCE_V1.md`：117/117 断言，4 代服务进程、
3 次真重启，含"重附着到仍在跑的长任务""跨重启不丢单槽"）。关键断言：

- 口径一与 `grep -c '\*E'` **独立对账一致**；两套口径并列、`both_zero=false` 时**不得判绿**；
- 观测印记三向一致（印记行 / by-id 计数 / 地址与值）逐项通过；
- 全链路 N0→N16 三道闸门，`gate_history` 每道**恰好一次**；
- 作业运行期间执行处于 **interrupt**（`is_waiting()`），换 `RunManager` 从快照恢复后
  **重新附着到同一作业**；
- 死任务与取消**都走失败**，且都**释放单槽**；
- 非 human actor、非法枚举、I4 阻断三类拒绝**不消耗中断**，闸门仍可用；
- N16 在真实 `<WORKSPACE_ROOT>/baselines/` 上 **rc=3 且零副作用**（v0 与目录清单不变）；
- 冻结见证：完整 drill 运行前后 `TESTLIB/`、`<WORKSPACE_ROOT>/baselines/v0/`、`doc/AGENTS.md`、
  `kb/tools/gate.py` 的**内容 md5 清单逐行不变**（不按 mtime 判）。

## 8 界面不做的事

- 不判绿/判红（一切 `passed` / `can` / `blockers` 由服务端算）。
- 不编辑 `TESTLIB/`（v1 写权仍在作者角色 + 沙箱）。
- 不改基线、不改冲突清单。
- **四个**写动作（已登记在 `doc/spec/LOOP_ORCHESTRATION_SPEC.md` §10.0，均经服务端校验）：
  **提交闸门决策**、**取消作业**、**新建运行**、**人触发晋升（N16/I8）**。
  > 晋升入口只允许 human actor 且必须与 G3 签署者逐字一致；真实写盘由
  > `kb/tools/n16_promote.py --promote` 原子完成（API 不写 `baselines/`、不伪造闸门）。
