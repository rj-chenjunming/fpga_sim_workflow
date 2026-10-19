# 变更影响闭环（Change Impact Loop）

> **一句话**：给 FPGA 仿真环境做一套「改一笔 RTL/文档 → 自动算出哪些用例必须改 → 走三道人工闸门 → 跑回归 → 原子晋升基线」的闭环工具，并提供一个本地可交互的操作台。
>
> **本仓是软件仓**（独立产品），环境是**插件**：软件可以指向任意符合插件契约的环境仓，本仓不存放被守卫的 `RTL/ TB/ PKG/ TESTLIB/`。
>
> **当前状态**：`drill` 链路可运行；`real` 链路尚未闭合。代码级偏差已登记在 [`doc/audit/AUDIT-20261019-spec-conformance.md`](doc/audit/AUDIT-20261019-spec-conformance.md)，**本轮只审计不修复**。数字与门状态见 [`doc/STATUS.md`](doc/STATUS.md)。

---

## 1 组成

| 目录 | 是什么 | 入口 |
|---|---|---|
| `loop/` | 编排层 + HTTP 服务 + 单文件前端 + 测试 + 验收装置（Agently TriggerFlow） | [`loop/README.md`](loop/README.md) |
| `kb/` | Host 确定性工具（不上模型）+ JSON Schema + 契约 | [`kb/README.md`](kb/README.md) |
| `doc/spec/` | 三份契约：业务篇 / 编排篇 / 环境插件篇 | [`doc/README.md`](doc/README.md) |
| `doc/agents/` | 6 个角色定义 + 开工提示词 | [`doc/agents/README.md`](doc/agents/README.md) |
| `doc/evidence/` | 验收报告与演练证据（只读、内容冻结） | [`doc/evidence/README.md`](doc/evidence/README.md) |
| `doc/history/` | 拆仓前的历史快照（不是现状） | [`doc/history/README.md`](doc/history/README.md) |
| `doc/audit/` | 2026-10-19 规格一致性审计（只登记不修复） | [`doc/audit/README.md`](doc/audit/README.md) |
| `workspaces/` | 每环境数据的**约定**落点（当前 default 环境数据仍在环境仓） | [`workspaces/README.md`](workspaces/README.md) |

### 它不是

- 不是第二个状态机：状态权威 = TriggerFlow 执行 + `kb/tools/gate.py`。
- 不重新实现业务判定：N2/N5/N16 一律调用 `kb/tools/*.py`。
- 不写冻结资产：环境的 `RTL/ TB/ PKG/ TESTLIB/` 一律只读。

---

## 2 三个根（先看这个再跑）

| 根 | 含义 | 谁决定 | 本机取值 |
|---|---|---|---|
| `TOOL_ROOT` | 软件仓根（自锚定） | 代码向上找 `kb/tools/kb_lib.py` | 本仓 |
| `ENV_ROOT` | 被守卫的环境仓（插件） | `environments.json` / `$LOOP_ENV_ROOT` | `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` |
| `WORKSPACE_ROOT` | 该环境的数据根（索引/冲突/基线/运行记录） | `environments.json` 的 `workspace` / `$LOOP_WORKSPACE` | `ENV_ROOT/kb`（数据未搬，见 `doc/spec/ENV_PLUGIN_SPEC.md` §7） |

解析优先级与 fail-closed 规则见 [`doc/spec/ENV_PLUGIN_SPEC.md`](doc/spec/ENV_PLUGIN_SPEC.md) §1。

---

## 3 快速开始

```bash
# 起界面（单机单用户；默认 http://127.0.0.1:8099）
cd loop && ./run.sh

# 单测（离线，模型节点走确定性替身）
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q

# kb 自测（只读环境；写 TMP 运行目录，需要可写 WORKSPACE_ROOT）
loop/.venv/bin/python kb/tools/_selftest_gate_schema.py        # 期望 10/10
loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py    # 期望 9/9

# 端到端终验（117 断言；会写 ENV_ROOT/SIMLIB_RUN，需环境仓可写）
cd loop && rm -rf state spikes/.accept_v1_state.json && bash spikes/accept_v1_run.sh
```

> **沙箱注意**：本次整理所在的 DSH 会话把 `ENV_ROOT` 挂为只读，因此终验与 `test_archive_e2` 无法在本会话复跑；这是运行环境限制，不是代码缺陷。详见 [`doc/STATUS.md`](doc/STATUS.md)。
>
> **从 Windows 远程访问**（服务器起服务 + SSH 隧道，服务只绑 `127.0.0.1`）：见 [`loop/remote/README.md`](loop/remote/README.md)。

---

## 4 文档怎么读

0. 想看「是什么、怎么转」和流程图 → [`doc/OVERVIEW.md`](doc/OVERVIEW.md)。
1. 先读本文件 §2（三个根）与 [`AGENTS.md`](AGENTS.md)（流程/写权/红线）。
2. 业务要改什么、为什么 → `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`。
3. 一次运行怎么活、怎么停、怎么恢复 → `doc/spec/LOOP_ORCHESTRATION_SPEC.md`。
4. 软件与环境怎么解耦、数据放哪 → `doc/spec/ENV_PLUGIN_SPEC.md`。
5. 哪里和 spec 不一致 → `doc/audit/AUDIT-20261019-spec-conformance.md`。
6. 界面/交互怎么改 → `doc/spec/WEB_UI_SPEC.md`（设计样张 `loop/web/mockup.html`）。

---

## 5 红线（摘要，完整版见 `AGENTS.md`）

1. 只新增 `kb/` 与 `doc/` 下文件（软件仓）；环境的 `RTL/ TB/ PKG/ TESTLIB/` 与已定稿基线资产**绝不修改**。
2. 数字一律由命令输出复制，禁止手算；唯一数字源是 `doc/STATUS.md`。
3. 归档只增不改；已冻结运行目录绝不回填。
4. 闸门枚举权威 = `kb_lib.GATE_DECISIONS`；前端与脚本不许手抄。
5. `human_signed` 只在 `actor_kind="human"` 时为真。
6. 时间字段是唯一允许的非确定性，必须经 `--now`/`KB_NOW` 注入。
7. 单槽：`uvs.setup` 是环境根下全局单文件 ⇒ 同环境禁止并发。
8. 发现缺陷只报告不改（由对应 owner 改）；独立验证者不修被测文件。
9. 判「未改动」按内容 md5，不按 mtime。
10. 不写 `ENV_ROOT` 除 `SIMLIB_RUN/` 与 `uvs.setup`（自愈还原）之外的任何文件。
