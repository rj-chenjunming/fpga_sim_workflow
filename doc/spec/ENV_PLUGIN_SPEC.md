# 环境插件规格（software standalone / environment as plugin）

> S0 补充见 [S0_ENVIRONMENT_SPEC.md](S0_ENVIRONMENT_SPEC.md)：基线只读、派生副本准备。修订稿 `docs/ + run` 兼容 `doc/ + run`，不等于满足本文件既有运行插件的 `run_local/uvs.setup` 契约，进程不自动切换副本。

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

## 5 分步计划（每步一个提交，每步独立可验）

### 第 3 步（**让新仓能跑**，不搬数据）—— ✅ **已完成**（见本仓 git log）

**完成证据**（全部在**新布局**下、数据仍留在旧位置跑出来的）：
- `LOOP_ENV_ROOT=<旧环境仓> LOOP_WORKSPACE=<旧环境仓>/kb` 下：`loop` 单测 **当时 69/69**
  （当前基线 **70/70**，见 §4）；`loop/spikes/accept_v1_run.sh` **rc=0、六相 116 断言**
  （当前基线 **117**：50/27/18/8/8/6，见 §4）；`_selftest_gate_schema` **10/10**、
  `_selftest_n5_reachability` **9/9**。
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

1. 只新增 `kb/` 与 `doc/` 下文件；**绝不修改**环境的 `RTL/ TB/ PKG/ TESTLIB/` 与已定稿基线资产。
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
  （决定时 69/69 + 116/116；当前基线 70/70 + 117/117，见 §4）；② 要搬的恰好是**不可再生**的部分（`baselines/v0` 基线快照、
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
