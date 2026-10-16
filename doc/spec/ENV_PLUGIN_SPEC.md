# 环境插件规格（software standalone / environment as plugin）

> **定位**：软件是独立产品，环境是插件。软件可以被指向**任意**符合本规格的环境仓；
> 一个环境在软件侧的全部状态（索引/冲突/基线/运行记录）由软件自己管理。
>
> **现状**：本仓已从环境仓分离（历史按 5 个提交重放，内容逐字节一致），但**根解析拆分尚未实现**
> ⇒ 见 §5「分步计划」。在那之前本仓**还不能独立运行**。

---

## 1 三个根（必须分开，否则拆仓必坏）

拆分前只有一个根：`kb_lib.ROOT = dirname(dirname(kb/tools))`，它**同时**被用来定位
工具自己的 `kb/**` 和环境的 `RTL/ TB/ TESTLIB/ doc/ uvs.setup`。
`loop/host/paths.py` 更是"向上搜 `kb/tools/kb_lib.py`"。搬到新位置，两者同时失效。

| 根 | 含义 | 谁提供 | 典型值 |
|---|---|---|---|
| `TOOL_ROOT` | **软件仓根**（含 `kb/tools/kb_lib.py`） | 自锚定，不需要配置 | `/home/work/chenjunming/change-impact-loop` |
| `ENV_ROOT` | **被守卫的环境仓根**（插件） | `environments.yaml` / `$LOOP_ENV_ROOT` / `--env-root` | `…/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` |
| `WORKSPACE_ROOT` | **该环境的数据根**（软件管理） | `environments.yaml` 的 `workspace` / `$LOOP_WORKSPACE` | `<TOOL_ROOT>/workspaces/simenv-tcs9620-64ch` |

**解析优先级（单一实现，不许两套）**：
1. 命令行 `--env-root` / `--workspace`（最具体）
2. 环境变量 `$LOOP_ENV_ROOT` / `$LOOP_WORKSPACE`
3. `environments.yaml`（选定 env id 的 `path` / `workspace`）
4. **向后兼容回落**：若 `TOOL_ROOT` 自身含 `TESTLIB/`，则 `ENV_ROOT = TOOL_ROOT`、
   `WORKSPACE_ROOT = TOOL_ROOT/kb` —— 这正是拆仓前的布局，行为必须逐字节不变。
5. 以上都不成立 ⇒ **fail closed**：报错并列出缺什么，**不猜路径、不用默认值兜底**。

## 2 目标目录布局

```
<TOOL_ROOT>/                         # 软件（本仓）
├── environments.yaml                # 环境插件注册表
├── kb/
│   ├── README.md                    # 契约（口径/写权/红线）
│   ├── tools/**                     # Host 确定性程序（不上模型）
│   └── schema/**                    # JSON Schema 契约
├── loop/**                          # 编排层 + 界面 + 测试 + 验收装置
├── doc/spec/*.md, doc/agents/**      # 规格与角色定义
└── workspaces/<env-id>/**           # 软件管理的每环境数据（见 workspaces/README.md）

<ENV_ROOT>/                          # 环境（插件，只读）
├── RTL/ TB/ PKG/ TESTLIB/           # 冻结资产
├── doc/                             # 环境自带文档与工具（AGENTS.md / tools/ / skills/ / _notes/ / reference/）
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

| 门 | 期望 |
|---|---|
| `kb/tools/_selftest_gate_schema.py` | 10/10 |
| `kb/tools/_selftest_n5_reachability.py` | 9/9 |
| `loop` 单测 | 68/68 |
| `loop/spikes/accept_v1_run.sh` | rc=0、六相 116 断言 |
| **向后兼容**（不设任何环境变量，在旧布局下跑） | 上述四条**全部不变** |
| 冻结件复验 | 内容 md5 前后逐行一致（**不按 mtime**） |

## 5 分步计划（每步一个提交，每步独立可验）

### 第 3 步（**让新仓能跑**，不搬数据）
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

### 第 4 步（数据迁到工作区）
把该环境的数据复制（**不是移动**）到 `workspaces/simenv-tcs9620-64ch/`：
`kb/{index,conflicts,baselines,runs,adjudication}` + `kb/FIXTURE_IDENTITY.md` + `doc/spec/evidence/**`
（路径映射：`kb/runs/<id>` → `workspaces/<env>/runs/<id>`）。
必须产出 **迁移清单**：逐文件「旧路径 → 新路径 + 内容 md5（前后一致）」，并把旧的
`frozen_before.md5`/`frozen_after.md5` 里记录的是**旧路径**这一事实登记下来
（路径变了、内容没变 —— 这是"路径迁移"，不是"篡改证据"）。
**不动**环境仓里的任何一份原有内容（归档只增不改），只新增一份指针说明。

### 第 5 步（双仓复验）
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

- `[未决]` 第 4 步用**复制**还是**移动**：复制更安全（可回退、环境仓仍自洽），代价是 1.1G 冗余；
  移动则环境仓只剩冻结资产，但会使已归档证据的**路径**变化。
- `[风险]` `workspaces/*/runs/**` 与 `baselines/**` 不入 git ⇒ 靠目录 444 只读 + 外部 md5 账本保完整性，
  需要一条"数据根备份"的作业（当前没有）。
- `[风险]` 多个环境共享一个软件实例时的并发：单槽是按 `uvs.setup` 路径互斥的，
  **跨环境**默认可以并行（各自不同的 `uvs.setup`）—— 但当前 `run_guarded.sh` 的锁
  是否按 `ENV_ROOT` 分区，需要在第 3 步实现时明确并自证。
- `[待核]` `kb/README.md` 里"本目录只新增、不改已定稿基线资产"的表述需要按新布局重写
  （`kb/` 现在是纯软件目录，被守卫的对象在 `ENV_ROOT`）。
