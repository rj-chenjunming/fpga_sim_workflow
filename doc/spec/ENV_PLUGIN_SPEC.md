# SPEC-03 · 环境插件规格（software standalone / environment as plugin）

> 编号：**SPEC-03**（文件名不变；编号与修订记录见 [SPEC-REV-01](SPEC-REV-01-20261022.md)）。

> S0 补充见 [S0_ENVIRONMENT_SPEC.md](S0_ENVIRONMENT_SPEC.md)：基线只读、派生副本准备。修订稿 `docs/ + run` 兼容 `doc/ + run`，不等于满足本文件既有运行插件的 `run_local/uvs.setup` 契约，进程不自动切换副本。
> run 与 S0 的关系（run 文档必须带可空的 `s0_record_id`；drill 不覆盖 S0）见该文件 §6。

> **定位**：软件是独立产品，环境是插件。软件可以被指向**任意**符合本规格的环境仓；
> 一个环境在软件侧的全部状态（索引/冲突/基线/运行记录）由软件自己管理。
>
> **现状**：本仓已从环境仓分离（历史按 5 个提交重放，内容逐字节一致）；**第 3 步（三根解析 + 新仓可跑）已完成**，
> 见 §5。数据**不搬**：当前 `workspace` 指向数据实际位置（`ENV_ROOT/kb`），决定与理由见 §7。
> 本仓因此可独立运行；第 4/5 步的状态见 §5。

---

## 1 三个根（必须分开，否则拆仓必坏）

拆分前只有一个根：`kb_lib.ROOT = dirname(dirname(kb/tools))`，它**同时**被用来定位
工具自己的 `kb/**` 和环境的 `RTL/ TB/ TESTLIB/ doc/ uvs.setup`。
`loop/host/paths.py` 更是"向上搜 `kb/tools/kb_lib.py`"。搬到新位置，两者同时失效。

| 根 | 含义 | 谁提供 | 典型值 |
|---|---|---|---|
| `TOOL_ROOT` | **软件仓根**（含 `kb/tools/kb_lib.py`） | 自锚定，不需要配置 | `/home/work/chenjunming/change-impact-loop` |
| `ENV_ROOT` | **被守卫的环境仓根**（插件） | `environments.json` / `$LOOP_ENV_ROOT`（`--env-root` **未实现**，见下） | `…/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` |
| `WORKSPACE_ROOT` | **该环境的数据根**（软件管理） | `environments.json` 的 `workspace` / `$LOOP_WORKSPACE`（`--workspace` **未实现**） | 目标：`<TOOL_ROOT>/workspaces/simenv-tcs9620-64ch`；**当前 = `<ENV_ROOT>/kb`**（§7 决定暂不搬） |
| `STATE_ROOT` | **软件 state 根**：`jobs/`、`recovery/`、`events/`、单槽锁与队列 | `$LOOP_STATE_ROOT`；缺省 `<TOOL_ROOT>/loop/state` | 测试/独立副本必须指向隔离目录（F03-a）；生产保持缺省 |

> **注册表为什么是 JSON 而不是 YAML**：`kb/tools/**` 必须**只用 stdlib**（项目既有约束：环境里没有 `pyyaml`），
> 自己写一个 YAML 子集解析器会把「解析错 ⇒ 环境根解错」这种静默故障引进来。JSON 是 stdlib 且无歧义。

**解析优先级（单一实现 `kb/tools/kb_lib.py::_resolve_env_root` / `_resolve_workspace_root`，不许两套）**：
1. ~~命令行 `--env-root` / `--workspace`~~ —— **未实现项**：本仓所有入口（`loop`、`kb/tools/*`）都只读环境变量与注册表；
   该条承诺**待补实现或删除**（审计登记：`doc/audit/parts/spec-conformance.md` A19 附近同族的路径/入口缺口）。
2. 环境变量 `$LOOP_ENV_ROOT` / `$LOOP_WORKSPACE`（最具体）
3. `environments.json`（选定 env id 的 `path` / `workspace`）
4. **向后兼容回落**：若 `TOOL_ROOT` 自身含 `TESTLIB/`，则 `ENV_ROOT = TOOL_ROOT`、
   `WORKSPACE_ROOT = TOOL_ROOT/kb` —— 这正是拆仓前的布局，行为必须逐字节不变。
5. 以上都不成立 ⇒ **fail closed**：报错并列出缺什么，**不猜路径、不用默认值兜底**。

## 2 目标目录布局（与当前实际对照）

> **当前实际（2026-10-19，`environments.json`）**：`WORKSPACE_ROOT = <ENV_ROOT>/kb` ——
> `index/conflicts/baselines/runs/adjudication` 仍落在环境仓的 `kb/` 下（该目录同时保留拆仓前的
> schema/tools 副本）；本仓 `workspaces/` 目前只有 `README.md` + `.gitkeep`。
> 下列上半部分是**目标布局**；数据迁移（第 4 步）已决定**暂不执行**，理由见 §7。

```
<TOOL_ROOT>/                         # 软件（本仓）
├── environments.json                # 环境插件注册表
├── kb/
│   ├── README.md                    # 契约（口径/写权/红线）
│   ├── tools/**                     # Host 确定性程序（不上模型）
│   └── schema/**                    # JSON Schema 契约
├── loop/**                          # 编排层 + 界面 + 测试 + 验收装置
├── doc/                             # 规格 / 角色 / 证据 / 历史
│   ├── spec/*.md                    #   契约
│   ├── agents/**                    #   角色定义
│   ├── evidence/**                  #   验收与演练证据（只增不改）
│   └── history/**                   #   历史快照（只增不改）
└── workspaces/<env-id>/**           # 【目标】软件管理的每环境数据（当前为空；见上）

<ENV_ROOT>/                          # 环境（插件，只读）
├── RTL/ TB/ PKG/ TESTLIB/           # 冻结资产
├── doc/                             # 环境自带文档与工具（AGENTS.md / tools/ / skills/ / _notes/ / reference/）
├── kb/                              # 【当前数据根】WORKSPACE_ROOT 指向这里（§7：数据不搬）
├── uvs.setup                        # 全局单文件 ⇒ 单槽的物理依据
└── SIMLIB_RUN/                      # 运行产物落点（环境侧运行时状态）
```

## 3 插件契约（环境必须提供什么）

| 键 | 相对 `ENV_ROOT` | 用途 | 缺了怎么办 |
|---|---|---|---|
| `frozen` | `RTL TB PKG TESTLIB` | 被守卫的冻结资产 | 报错（缺任何一项 ⇒ rc≠0） |
| `sim_setup` | `uvs.setup` | 单槽依据 + 中止自愈 | 报错 |
| `run_local` | `doc/tools/run_local.sh` | 冻结的真机驱动 | 报错（`--mode full` 时） |
| `sim_setup_orig` | `doc/_run_artifacts/uvs.setup.orig` | 自愈还原源 | 报错（`--mode full` 时） |
| `sim_workdir` | `SIMLIB_RUN` | 运行产物落点 | 可自动创建 |
| `env_agents` | `doc/AGENTS.md` | 环境红线 | 警告（不阻断） |

**软件对环境的承诺**：除了 `SIMLIB_RUN/` 与 `uvs.setup`（自愈还原）之外，**不写环境的任何文件**；
`frozen` 下的路径一律拒绝写入（沿用现有 `FROZEN_FOR_WRITE` 守卫，但基准改为 `ENV_ROOT`）。

## 4 测试基线（拆仓必须保持）

> 数字源：`doc/STATUS.md`（唯一数字源）；当前收集/通过数与失败集以 STATUS 最新章节为准，
> 本节不再抄写历史数字。历史 70/70 与 117 断言见 `doc/evidence/ACCEPTANCE_V1.md`。

| 门 | 期望 |
|---|---|
| `kb/tools/_selftest_gate_schema.py` | 全部断言通过（需可写 `WORKSPACE_ROOT` 与历史夹具） |
| `kb/tools/_selftest_n5_reachability.py` | 全部断言通过 |
| `loop` 单测（默认根） | 失败集与 STATUS 记录的**环境层基线相同**；不得新增软件层失败 |
| `loop` 单测（软件层入口，见 §4.1） | 排除环境层后 **0 failed** |
| `loop/spikes/accept_v1_run.sh` | rc=0、六相断言完整（需可写 `ENV_ROOT`） |
| **向后兼容**（不设任何环境变量，在旧布局下跑） | 上述四条**全部不变** |
| 冻结件复验 | 内容 md5 前后逐行一致（**不按 mtime**） |

### 4.1 测试分层与环境层标记（F03-b）

测试分三层，**层级是执行条件的事实，不是通过/失败的口径**：

| 层 | 需要什么 | 入口 |
|---|---|---|
| 纯软件层 | 可写影子数据根 + 一次性 `$LOOP_STATE_ROOT`；**不需要**可写 `ENV_ROOT` | `loop/spikes/run_software_checks.sh`（默认） |
| 环境层 | 可写 `ENV_ROOT`、UVS/许可证、内网冻结见证 | 默认根 pytest；本机只能如实失败并登记 |
| 真实链路层 | 上文 + 有效非默认基线 + 单槽 + provider | 内网执行端（本机未运行） |

规则：

1. 需要可写 `ENV_ROOT` 或内网冻结见证的用例必须带 `@pytest.mark.env_layer`，并在测试内**写明原因**
   （可写 `ENV_ROOT` / 冻结见证 / 布局要求）。当前 3 项：
   `tests/test_archive_e2.py::test_guard_compile_only_archives_evidence_readonly`、
   `tests/test_archive_e2.py::test_guard_archive_is_bounded_and_excludes_guard_log`、
   `tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run`。
2. `loop/pytest.ini` 注册 `env_layer` 标记并启用 `--strict-markers`：未注册标记必须让 pytest 直接失败，
   不得静默出现「拼写错误的标记其实没生效」。
3. `run_software_checks.sh` **默认**以 `-m "not env_layer"` 运行，并在输出中显式打印被排除的用例数；
   `INCLUDE_ENV_LAYER=1` 可包含环境层（用于有可写 `ENV_ROOT` 的执行端）。
4. **不得用 `skip` 冒充通过**：默认根仍如实执行并失败这 3 项；标记只用于分层选择，不改变默认根结果。
5. 软件层入口的结论只覆盖纯软件层；它不能替代 kb 自测、端到端或真实链路验收。

### 4.2 文档路径检查的根路由（F03-c）

`doc/audit/check_doc_links.py` 是**唯一**的文档路径判据（不另写第二套）。它按「谁拥有这个路径」路由：

| 路径类别 | 解析根 | 例 |
|---|---|---|
| 本仓工具 / Schema / 文档 / 代码 | `TOOL_ROOT` | `kb/tools/*`、`kb/schema/*`、`kb/README.md`、`loop/*`、`doc/spec/*`、`workspaces/*`、根 `README.md` |
| 数据根 | `WORKSPACE_ROOT` | `kb/runs/`、`kb/baselines/`、`kb/index/`、`kb/conflicts/`、`kb/adjudication/`、`kb/FIXTURE_IDENTITY.md` |
| 环境资产 | `ENV_ROOT` | `RTL/`、`TB/`、`PKG/`、`TESTLIB/`、`SIMLIB_RUN/`、`uvs.setup`、`doc/AGENTS.md`、`doc/_notes/`、`doc/skills/`、`doc/tools/`、`doc/spec/evidence/` |
| 环境文档回落 | 仅当 `TOOL_ROOT` 不存在时用 `ENV_ROOT` | `doc/SIM_ENV_TESTLIB_GUIDE.md`（环境仓自带文档） |

判定与退出码：

1. **本仓/数据根**路径解析不到 ⇒ `missing`，**退出码 1**（真正的断链必须失败）。
   `loop/` 前缀**不做**环境回落：旧路径（如已迁走的 `loop/ACCEPTANCE_V1.md`）必须暴露，不得被环境仓同名文件掩盖。
2. **环境资产**解析不到 ⇒ 记入 `env_missing`，逐条打印 `[ENV-MISSING]`，**可见但不计失败**（本机未挂载内网
   `ENV_ROOT` 资产属环境缺件，不是本仓断链）。不得把它静默过滤掉。
3. `KNOWN_MISSING` 登记的「文档故意引用、本仓确实不存在」的缺口 ⇒ `known_missing`，打印原因，不计失败。
4. `doc/history/`、`doc/evidence/demo/` 内的历史路径 ⇒ 计入 `historical`，不判失败（只增不改的历史快照）。
5. 行号后缀（`:64-67`）、符号后缀（`::func`）、URL/锚点/模板/变量 ⇒ 先按既有契约剥离或跳过。
6. 判定只看**退出码 + `missing`**；`checked/skipped` 是诊断值，不写回文档（见 STATUS §19）。

### 4.3 浏览器验证的离线交付

内网验证工具支持 Rocky Linux 8.10 / x86_64 / glibc 2.28 的 CPython 3.11；可附带 CPython 3.12 用于云端复验。离线包是浏览器增量依赖，项目原有 requirements 仍需先安装。

- 离线资源通过普通 Git 交付，清单锁定来源、版本、平台、每个文件 SHA-256 与浏览器归档整体 SHA-256。大归档可分片，不依赖 Git LFS 或安装时网络。
- 安装前验证平台和全部资源完整性；pip 必须只读本地 wheel 并校验固定哈希，不读取外部索引、不自动下载浏览器。
- 浏览器路径优先由显式配置选择，其次系统 Chrome/Chromium，最后随包运行时；显式无效路径必须拒绝，不能悄悄选另一浏览器。用户可强制验证随包版本。
- 随包浏览器只解包到独立软件缓存，不安装系统 RPM、不要求 root、不写环境资产。解包必须拒绝路径越界、链接/设备等非预期归档条目。
- 检查入口先真实启动浏览器并验证本地页面，再执行现有浏览器测试；缺 Python 包、浏览器或共享库、资源损坏均显式非零。零测试或整组跳过不能记为通过。
- 共享库与字体属于主机依赖，缺件须明确报告；云端通过不代表 Rocky 主机已完成验收，系统库不得从不同发行版盲目复制替换。

## 5 分步计划（每步一个提交，每步独立可验）

### 第 3 步（**让新仓能跑**，不搬数据）—— ✅ **已完成**（见本仓 git log）

**完成证据**（全部在**新布局**下、数据仍留在旧位置跑出来的）：
- `LOOP_ENV_ROOT=<旧环境仓> LOOP_WORKSPACE=<旧环境仓>/kb` 下：`loop` 单测 **当时 69/69**
  （**历史采样**；现行数字见 STATUS）；`loop/spikes/accept_v1_run.sh` **rc=0、六相 116 断言**
  （**历史采样**；后续验收记录 117 见 STATUS）；`_selftest_gate_schema`、`_selftest_n5_reachability`
  的当前结果按 STATUS 记录。
- **向后兼容**（旧布局回落）实测：`TOOL_ROOT` 下有 `TESTLIB/` 时 `ENV_ROOT=TOOL_ROOT`、
  `WORKSPACE_ROOT=TOOL_ROOT/kb`，三个取值逐项与拆仓前一致。
- **fail closed** 实测：无 `$LOOP_ENV_ROOT`、注册表无可用条目、且非旧布局 ⇒ 报错并列出缺什么。
- 顺带修掉两个**只在恢复路径触发**的真缺陷：**F-V1-06c**（快照停在已终结作业上 ⇒ 永久卡在 JOB）
  与 **F-V1-08**（重投递复用旧 `resume_request_id` 被静默拒绝）。详见
  **`doc/evidence/ACCEPTANCE_V1.md` §3**（该报告已从 `loop/ACCEPTANCE_V1.md` 迁入 `doc/evidence/`）。

**仍未做**：第 4 步（把数据搬进 `workspaces/`）——**已决定暂不执行**（§7）；第 5 步（双仓独立复验）——**待做**。

#### 第 3 步原始计划（供对照）
改动：
1. `kb/tools/kb_lib.py`：按 §1 实现三个根与解析器；`env_path(*p)` 新增；
   **`root_path(*p)` 保留为 `env_path` 的别名**（现有调用语义都是在找环境文件，不改语义）；
   `kb_path(*p)` 改为指向 `WORKSPACE_ROOT`；新增 `check_env()` 自检插件面齐全。
2. `kb/tools/{n1_case_scan,n1_conflicts,n1_doc_entries,n1_snapshot,n2_diff,n5_impact,n16_promote}.py`、
   `_selftest_*.py`：环境用法改 `K.env_path(...)`；`kb/index|conflicts|baselines|runs` 默认值改 `K.kb_path(...)`。
3. `kb/tools/run_guarded.sh`：`ROOT` → `ENV_ROOT`（`$LOOP_ENV_ROOT` 优先，否则旧回落）。
4. `loop/host/paths.py`：`ENV_ROOT`/`WORKSPACE_ROOT` **直接复用 `kb_lib` 的解析器**（单一口径，
   经同款 `sys.dont_write_bytecode` 守卫加载——`kb/tools` 是冻结目录，不许写 `.pyc`）；
   `GLOBAL_SIM_SETUP = ENV_ROOT/"uvs.setup"`；`KB_DIR/KB_RUNS/KB_BASELINES/KB_CONFLICTS` → `WORKSPACE_ROOT`。
5. `loop/services/contracts.py`、`loop/workflows/chunks/host_steps.py` 等处**写死的 `kb/...` 相对路径**
   改为经 `P.KB_*` 常量（UI 与投影里不许出现硬编码数据路径）。

**验收**：用 `LOOP_ENV_ROOT=<旧环境仓> LOOP_WORKSPACE=<旧环境仓>/kb` 在新仓跑满 §4 六条门
—— 此时**一行数据都不用搬**（旧数据根恰好就是旧 `kb/`）。

### 第 4 步（数据迁到工作区）—— ⏸ **暂不执行**（决定与理由见 §7）
把该环境的数据复制（**不是移动**）到 `workspaces/simenv-tcs9620-64ch/`：
`kb/{index,conflicts,baselines,runs,adjudication}` + `kb/FIXTURE_IDENTITY.md` + `doc/spec/evidence/**`
（路径映射：`kb/runs/<id>` → `workspaces/<env>/runs/<id>`）。
必须产出 **迁移清单**：逐文件「旧路径 → 新路径 + 内容 md5（前后一致）」，并把旧的
`frozen_before.md5`/`frozen_after.md5` 里记录的是**旧路径**这一事实登记下来
（路径变了、内容没变 —— 这是"路径迁移"，不是"篡改证据"）。
**不动**环境仓里的任何一份原有内容（归档只增不改），只新增一份指针说明。

### 第 5 步（双仓复验）—— ⏳ **待做**
由**独立验证者**在两个布局下各跑一遍 §4 六条门 + 冻结件复验，重点是**向后兼容**那一行。
不通过就不算拆仓完成。

## 6 不可协商的约束（继承自环境仓，拆仓后继续有效）

1. **本条只约束软件对环境的写入**：软件不得新增/修改环境仓文件，**绝不修改**环境的 `RTL/ TB/ PKG/ TESTLIB/`
   与已定稿基线资产。本仓内部的实现写权见 [`AGENTS.md`](../../AGENTS.md) §3（`loop/**`、`kb/tools/**`、
   `doc/spec/**` 等各有唯一 owner），**不得把本条误读为「本仓只许新增 kb/ 与 doc/」**（AGENTS §5 红线 1）。
2. 数字一律由命令输出复制，禁止手算。
3. 归档只增不改；已冻结的运行目录**绝不回填**。
4. 闸门枚举权威 = `kb_lib.GATE_DECISIONS`，不许手抄；`pending` 是状态不是动作。
5. `human_signed` 只在 `actor_kind="human"` 时为真；权威凭据是 `gates.json` + `gates.sha256` 锚。
6. **单槽**：`uvs.setup` 是环境根下的全局单文件 ⇒ 同工作目录禁止并发。
7. 时间字段是唯一允许的非确定性，必须经 `--now`/`KB_NOW` 单一入口注入。
8. **口径唯一**：不许出现第二套同判据实现。
9. 发现缺陷只报告不改；独立验证者不修被测文件。
10. 判「未改动」按**内容 md5**，不按 mtime。

## 7 风险与未决

- ✅ `[已决定：第 4 步暂不执行]` **数据不搬，`workspace` 指向数据的实际位置**（本环境 = 环境仓的 `kb/`）。
  理由三条：① 功能上不需要 —— `WORKSPACE_ROOT` 可指向任意位置，已在新布局下端到端验证
  （决定时 69/69 + 116/116，均为**历史采样**；现行数字见 STATUS）；② 要搬的恰好是**不可再生**的部分（`baselines/v0` 基线快照、
  `runs/RUN-20261015-120626` 真机全跑见证、演练证据），搬动只增加"路径迁移"的审计成本
  （已归档的 `frozen_*.md5` 记的是旧路径）、不增加任何能力；③ 把同一环境的数据**劈成两半**
  （历史在旧仓、新增在新仓）比两种极端都糟。
  **什么时候才值得搬**：环境仓要交出去 / 归档 / 重写历史时；或要同时管多个环境、
  希望数据集中备份时（那时应另建**数据仓**，而不是塞进软件仓）。
- ✅ `[已修]` 注册表的 `workspace` 曾写成软件仓内的 `workspaces/<id>`（当时是空目录），
  零配置运行会去找空目录，症状表现为"索引缺口 / 冲突清单缺失"这类**难懂**的失败。
  现 `environments.json` 的 `workspace` 指向 `<ENV_ROOT>/kb`，并新增 `check_workspace()` /
  `/api/health.workspace_missing` 把"数据找不到"与"数据坏了"区分开。
- `[风险]` `<WORKSPACE_ROOT>/runs/**` 与 `<WORKSPACE_ROOT>/baselines/**` 不入 git
  ⇒ 靠目录 444 只读 + 外部 md5 账本保完整性，需要一条"数据根备份"的作业（当前没有）。
- ⚠ `[部分自证]` 多个环境共享一个软件实例时的并发：`run_guarded.sh` 的**包装锁**按 `ENV_ROOT` 分区
  （`$ROOT/SIMLIB_RUN/.run_guarded.lock` 与 `$ROOT/.compile_only.lock`，`ROOT=ENV_ROOT`）；
  但**编排层单槽** `loop/host/admission.py` 的 `slot.lock` 落在 `STATE_ROOT`（缺省 `TOOL_ROOT/loop/state/`），
  是**软件实例级全局锁** ⇒ 多环境共享一个软件实例时仍串行。
  该场景未测；若要真正按环境并行，需把 `STATE_ROOT` 或槽键按 `ENV_ID` 分区（审计待办）。
  `$LOOP_STATE_ROOT` 只解决「测试与独立副本不写共享 state」（F03-a），**不代表**已按环境隔离。
- ✅ `[已修]` `kb/README.md` 已按三根重写：本仓 `kb/` = `README.md` + `schema/` + `tools/`；
  运行数据写作 `<WORKSPACE_ROOT>/{index,conflicts,baselines,runs,adjudication}`（当前 = `ENV_ROOT/kb/…`）。

## 8 派生副本作为环境根（2026-10-30）

> 契约来源：[S0 §9](S0_ENVIRONMENT_SPEC.md#9-单一-rtl-文件夹入口一键派生与自动切换2026-10-30)。只增不改 §1 的解析顺序。

1. **解析**：`$LOOP_ENV_ROOT` 优先于注册表 ⇒ 派生副本无需登记即可作为 `ENV_ROOT`
   （`kb_lib._resolve_env_root`）；`ENV_ID` 回落为副本目录名，未注册**不是错误**，健康检查/界面如实显示。
2. **零写承诺不变**：原环境除 `SIMLIB_RUN/`、`uvs.setup`（自愈）外零写入；派生副本的一切运行产物写副本自身。
3. **数据根**：派生环境 `WORKSPACE_ROOT = <work>/kb`（副本自包含，见 S0 §9.3）；原数据根不被本次派生写。
4. **单槽**仍按软件实例全局（`STATE_ROOT/slot.lock`）：同一时刻只允许一个环境根在跑；切换前必须拒绝活跃 run。
5. **原始根记录**：`<STATE_DIR>/env-switch/` 持久化 `origin_env_root`；派生源恒为原始根（禁止副本当基线）；
   切换与切回双向可审计，注册表（`environments.json`）**不因切换被写**，副本不因切回被删。

## 2026-10-29 节点模块化：N7 编译适配边界（首个切片）

目标：保持现有 TriggerFlow、节点身份、输入状态、事件、台账、返回和恢复格式不变，逐步分离节点职责与环境机制。本节先约束 N7，其他节点尚未改造或验证；总体实施计划见 [节点模块化评估](../plans/2026-10-28-node-modularity-assessment.md)。

- N7 仍由 Host 唯一负责沙箱和哈希核验、单槽准入与释放、失败收敛、用例台账、事件及状态；环境编译适配只负责生成现有 `run_guarded.sh --mode compile-only` 调用并收集其编译日志引用，不判断通过、不写台账、不分配资源。
- 适配器收到用例名、沙箱文件、sandbox 根、证据目录和 run_id；返回原执行结果及按现有命名规则发现的日志引用。调用失败、超时与缺文件保持原有语义，不伪造成功。现有真实环境写权和 kb 唯一解析器不变。
- 节点执行顺序、事件名称、产物和 TriggerFlow 拓扑保持不变；不引入新的配置格式或第二套调度、状态、判据。旧 run/快照格式不变；跨版本实际恢复仍需验证，不能由设计推断通过。
- 验证：先运行重构前 N7 特征测试，改后同样测试通过；新增适配器契约测试检查参数和日志匹配、缺目录；再按本仓四门执行可用部分并如实记录缺件。当前只有一个真实环境实现，第二环境适用性未验证。

### N9/N15 环境运行调用边界（进行中）

- Host 的 N9/N15 节点继续拥有目标与哈希校验、单槽、作业提交、停放/恢复、结果校验及状态事件；环境适配模块只负责既有 full 作业命令生成与 run.log 定位，不运行作业、不写业务台账、不决定通过。固定种子、逐例顺序、摘要、返回值、日志选择与旧行为一致。
- 现有 drill 回放沿用同一日志定位规则；不因此声称真实仿真已验收。长任务进程、中断载荷、节点名称及原始证据格式不变；跨版本恢复须另行实际验证。

### N7/N9/N15 运行能力注入（开发接口，进行中）

- 单次运行 `RunCtx` 注入一个仿真适配能力；默认实现复用本仓现有编译/运行命令及日志定位。节点只通过该能力调用对应操作，Host 保持单槽、作业状态、证据判据与业务写入。无配置选择器、无动态插件发现，也不改变对外界面。
- 注入仅为进程内受控开发接口；当前重启恢复只构造默认实现，不支持自定义适配器跨重启恢复或声称第二环境可用。实现前先证明默认行为及替身被调用；未来提供外部选择时，必须先设计版本固定与 fail-closed 恢复。

### N1/N6 环境输入能力（进行中）

- N1 暂存 RTL/文档/寄存器映射的现有完整性与路径规则，以及 N6 来源用例文件定位规则由环境能力实现；N1 继续调用 kb 唯一快照权威，N6 继续独占沙箱应用、哈希与台账。缺项时仍按现有错误处理，行为不变。
- 环境能力字段改名为 `RunCtx.environment` 以涵盖输入与执行；这是进程内资源，并非新增持久化格式，当前仍只支持默认适配器恢复。真实其他环境和定制恢复未实现。

### 既有流程快照兼容（在研）

- 本轮对同路径原版与当前版进行了流程定义指纹对照，发现处理函数的源码行号会影响引擎生成的节点标识。改变 handler 文件/行号可能导致旧快照无法载入；不得仅凭函数名相同声称可恢复。
- 在未实现正式版本迁移前，现有图入口保持原模块、名称和源码行号；有意留出的注释/空行是兼容保留区。必须在同一路径比较变更前后流程指纹，并另做实际保存/载入验证；定制环境的恢复问题仍未解决。

### 节点模块分离与旧图入口（进行中）

- 保留既有 TriggerFlow 入口函数的模块、名称和行号，以兼容旧快照的定义指纹；入口只负责调用对应节点模块，实际节点行为和明确依赖在节点模块中实现。禁止入口自行新增判据、事件或第二套状态；每次拆分必须先固定成功/失败行为，再对比指纹及加载快照。
- 这种兼容入口是过渡措施；新节点应使用稳定身份注册，不能仅靠源码行号作为长期插件契约。自定义环境选择与恢复尚未接入。

### 模型节点模块（进行中）

- N3/N6/N8/N10/N11/N12 的实际 handler 按节点拆分；原 `model_steps` 中同名入口、定义位置和参数保留以维持 TriggerFlow 旧图身份。共用模型请求、输入预算、封存、验证器与业务台账仍保持单一实现；入口只注入现有依赖，不新增模型请求或改变提示词、事件及授权消费者。
- 拆分必须保留原有引用和受控测试注入点，避免重复业务判据；通过节点特征、模型调用及上下文回归后，再检查同路径图指纹和原版快照载入。真实模型效果与真实环境仍分别待验。

### N9/N15 节点文件拆分（进行中）

- N9 的提交/停放与 N15 的选集/运行保持独立阶段；各阶段逻辑移到对应节点模块，原 `long_jobs` 入口位置保持旧图身份。单槽/作业器和中断载荷、结果归并、drill 回放、失败收敛依赖继续由原机制提供，禁止新增并行状态机。

### 人工闸门与 HALT 的节点模块（进行中）

- G1/G2/G3 共用唯一闸门处理实现，按既有门 ID 参数区分；其原 `make_gate` 生成的入口及位置不变。人工签署、预检、权威台账、事件和中断语义不复制；进入/恢复实现拆入独立节点模块，现有判据按依赖注入。
- HALT 独立模块保留旧图入口及终态行为。拆分须验证决策、签署与阻断测试，真实等待中断跨版本恢复仍需历史夹具核验。

### N6 环境事实提取（进行中）

- 现有 SystemVerilog 调用定义扫描与 RTL 位截断事实提取属于环境能力，由现有环境适配器实现并提供给 N6。保留原算法、上下文覆盖、失败语义与输出形状；模型仍负责语义修订，Host 校验和台账权威不变。旧的公开导出只作兼容别名，不保留第二套实现。
- 该提取只证明当前格式的保持行为，不证明其他语言或环境可用；不完整或缺失的环境事实不得凭空补全。

### 2026-11-02 主线整合边界

远端零必改分流、N10 逐例机器判据与人工覆写契约保持权威；节点拆分只迁移实现，不改变事件、状态、准入和失败语义。N5 事件、G1_no_impact 进入与恢复前置、N9 全量目标身份核验、N10 机器原因持久化必须接入节点并有现行主线特征测试。流程拓扑变更后的旧快照兼容不能由旧指纹或源码行号断言，需同路径分别验证。环境选择和定制适配器恢复仍未实现。

当前主线新增零必改分流后拓扑发生变化。本次整合优先保留 f710079 主线的图处理函数身份并以同一路径快照验证；旧 46b4d7c 及更早图的快照迁移尚无契约，不得声称跨拓扑恢复，必须显式登记并在恢复失败时关闭执行。
