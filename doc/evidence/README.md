# `doc/evidence/` —— 验收与演练证据（**只增不改、内容冻结**）

> 本目录放**一次性验收 / 演练的冻结证据**，不是运行数据。
> 每轮运行数据（`manifest` / `diff` / `impact` / `gates` / `evidence`）在
> **`WORKSPACE_ROOT/runs/<run_id>/**`**，本机当前 = `ENV_ROOT/kb/runs/`（见
> [`doc/spec/ENV_PLUGIN_SPEC.md`](../spec/ENV_PLUGIN_SPEC.md) §1）。
>
> **纪律**：`doc/evidence/**` **只增不改**；引用冻结件必须带 md5；移动件必须留 MIGRATION 或「已过期」横幅
> （[`AGENTS.md`](../../AGENTS.md) 红线 12）。本目录**不写**任何会被后续覆盖的运行状态。

---

## 1 目录内容

| 路径 | 是什么 | 关键数字 / 说明 |
|---|---|---|
| [`ACCEPTANCE_V1.md`](ACCEPTANCE_V1.md) | v1 真实 HTTP 终验报告（闸门操作台 + 长任务看板） | **117/117 断言**（相 50/27/18/8/8/6）= 四代服务进程、3 次真重启、零配置连跑两轮 `rc=0`；含 F-V1-01…07 + F-V1-06c/08 共 9 条缺陷与修法 |
| [`REAL_RUN_SCN_RTL_0D04_20261020.md`](REAL_RUN_SCN_RTL_0D04_20261020.md) | **首次 real 模式**在真实环境副本上的跑通记录（N0→N8） | 真实 LLM + 真实编译；N2/N5 与预登记答案一致、N7 5/5 rc=0、N8 live pass；含 5 个真实缺陷的修复与 N6 质量 finding |
| [`FIX_ACCEPTANCE_20261019.md`](FIX_ACCEPTANCE_20261019.md) | 审计阻断级 22 条 + F-01/F-02 修复轮的门禁证据 | 四道门全绿：pytest **197 passed**、kb 自测 10/9/7/16/13、端到端 **117/117 rc=0**、文档链接 missing=0；含审计项→修复落点→回归测试映射 |
| [`SPEC_REV_01_IMPL_20261022.md`](SPEC_REV_01_IMPL_20261022.md) | SPEC-REV-01（全节点投影 / G1 可判材料 / 节点面板 / S0 徽标 / N2 GB18030）的实现与实测证据 | 软件层 **523 passed**；浏览器 **55 passed**；kb 自测 37/37、9/9、10/10；文档门 `missing=0`；**端到端未运行**（`ENV_ROOT` 只读）；同会话集成，无独立终验 |
| [`demo/`](demo/) | 团队演练（**只编译、不仿真**）冻结证据，共 32 件 | `accept/`（验收演练）、`evidence/`（编译/运行前证据）、`review/`（检查）、`guard/`（守护）、`TESTLIB_sandbox/`（沙箱用例）；入口 [`demo/README.md`](demo/README.md) |
| [`demo/MIGRATION.md`](demo/MIGRATION.md) | 迁移记录：doc/agents/_demo/ → `doc/evidence/demo/` | 目录级 + 关键件级 old→new 映射、内容 md5 未变声明、内部历史路径字符串说明 |

## 2 怎么复跑

```bash
# v1 终验（117 断言；约 3 分钟；rc=0 即全过）
cd loop && bash spikes/accept_v1_run.sh
```

- 原始输出落 `loop/.logs/accept/{driver.log,server.out,phase*.txt}`，**不入库**（根 `.gitignore` 已忽略 `loop/.logs/`）。
- 终验会写 `ENV_ROOT/SIMLIB_RUN` 与 `uvs.setup` 自愈；**需要可写的 `ENV_ROOT`**。
  2026-10-19 修复轮的 DSH 会话已具备可写 `ENV_ROOT`，端到端已实测 **117/117、rc=0**
  （证据见 [`FIX_ACCEPTANCE_20261019.md`](FIX_ACCEPTANCE_20261019.md)；状态见 [`doc/STATUS.md`](../STATUS.md)）。
- **并发纪律**：端到端与 pytest 不得同时跑（共用 `loop/state` 单槽锁）；先 pytest 后 e2e。
- 演练证据是**历史冻结件**，不可重跑回填；如需新一轮演练，另建新目录并在文件头标注时间。

## 3 迁移与引用

- 2026-10-19：loop/ACCEPTANCE_V1.md → 本目录；doc/agents/_demo/ → [`demo/`](demo/)。
  两处均以 `git mv` 迁移，**内容逐字节未变**。
- 演练证据内含 doc/agents/_demo/... 字符串的文件是**历史路径**，保留原样；引用时请用 `demo/...`
  新路径，并说明历史字符串见 [`demo/MIGRATION.md`](demo/MIGRATION.md)。
- 证据冻结 ≠ 结论冻结：若发现证据本身有缺陷，**开勘误/复验件**（新增文件），不回头改原证据
  （与 `demo/README.md` §「关于不改冻结件」同一原则）。
