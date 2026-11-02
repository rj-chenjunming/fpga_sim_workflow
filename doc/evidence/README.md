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
| [`RTL_FOLDER_ENTRY_20261030/`](RTL_FOLDER_ENTRY_20261030/README.md) | **单一 RTL 文件夹一键派生真实链**（S0 §9）：真实 ENV_ROOT 只读挂载上 派生→冒烟→准出→自动切换→real 跑到 G1→签 G1 收口→切回→删副本 | 真实链 **PASS=32 FAIL=0**（`rc=0`）；六项 checks 全 `passed`、`ready_for_execution=true`；原 `ENV_ROOT` 零写入（`find -newer` 0）；软件层 **1999 passed**、浏览器 **166 passed**、端到端 **6 相全 rc=0**、kb 自测 10/9/28；md5 账本见 [`RTL_FOLDER_ENTRY_20261030.md5`](RTL_FOLDER_ENTRY_20261030.md5) |
| [`ENTRY_TWO_MODES_20261030/`](ENTRY_TWO_MODES_20261030/README.md) | **S0 入口「单输入二选一」**（S0 §9.9 / WEB_UI §15）：只给整套环境项目 ⇒ 选择性复制成副本、RTL 不替换（`rtl=skipped`）；只给 RTL 文件夹 ⇒ 环境资产取原始根 | 真实链（env 模式）**PASS=33 FAIL=0**（`rc=0`）：派生→冒烟→准出（五项 passed + `rtl=skipped`）→自动切换（`health.env_root`=副本）→real 跑到 G1→收口→原 `ENV_ROOT` 零写入→切回→删副本；软件层 **2039 passed**、浏览器 **180 passed**、端到端 **6 相全 rc=0**、kb 自测 10/9/28、文档门 `missing=0`；md5 账本见 [`ENTRY_TWO_MODES_20261030.md5`](ENTRY_TWO_MODES_20261030.md5) |
| [`KB_GATE_NO_IMPACT_20261030/`](KB_GATE_NO_IMPACT_20261030/README.md) | **冻结目录单独变更留证**：新增分流闸门 `G1_no_impact`（`kb_lib` 枚举/`version=2`/schema/`gate.py` 向后兼容） | 只**追加**一个闸门与两个决策值（既有三门语义不变）；`gate.py` 实测：新门可签可查、非法决策 rc=2、非 human rc=3、旧 v1 记录可读、v2 缺门 rc=4；kb 自测 `PASS=10/9/28`；md5 账本见 [`KB_GATE_NO_IMPACT_20261030.md5`](KB_GATE_NO_IMPACT_20261030.md5) |
| [`NO_IMPACT_GATE_20261030/`](NO_IMPACT_GATE_20261030/README.md) | **N5 必改=0 的 G1 分流支线**（业务 §12 / LOOP §14 / WEB_UI §16）：`no_impact_end`（HALT、不晋升）/ `full_regression`（跳 N6–N8 直接 N9 全量） | 分支/守卫/目标集/拓扑单测 **15 passed**（drill 两分支实测）；软件层 **2054 passed**、浏览器 **183 passed**、端到端 **=> ALL PASS**、kb 自测 10/9/28、文档门 `missing=0`；**real 全量回归未跑**（≈19 min/用例，如实登记）；md5 账本见 [`NO_IMPACT_GATE_20261030.md5`](NO_IMPACT_GATE_20261030.md5) |
| [`FIX_ACCEPTANCE_20261019.md`](FIX_ACCEPTANCE_20261019.md) | 审计阻断级 22 条 + F-01/F-02 修复轮的门禁证据 | 四道门全绿：pytest **197 passed**、kb 自测 10/9/7/16/13、端到端 **117/117 rc=0**、文档链接 missing=0；含审计项→修复落点→回归测试映射 |
| [`REAL_RUN_20261022.md`](REAL_RUN_20261022.md) | **真实模式（real）完整轮**：可写环境副本 + live 模型 + UVS 真机编译/全跑；暴露 JobRunner rc 缺陷（已修）与 G2 accept 不可达（登记）；停 G2，N16 不可达 | N9 真机全跑 3 例 rc=0 / 1465s；口径一 1687、UVM_ERROR 0；软件层 533 passed；冻结件 md5 见文内 §6 |
| [`SPEC_REV_01_IMPL_20261022.md`](SPEC_REV_01_IMPL_20261022.md) | SPEC-REV-01（全节点投影 / G1 可判材料 / 节点面板 / S0 徽标 / N2 GB18030）的实现与实测证据 | 软件层 **523 passed**；浏览器 **55 passed**；kb 自测 37/37、9/9、10/10；文档门 `missing=0`；**端到端未运行**（`ENV_ROOT` 只读）；同会话集成，无独立终验 |
| [`NODE_PANEL_REVISION_20261023.md`](NODE_PANEL_REVISION_20261023.md) | 节点面板统一修订（SPEC-REV-04 P-01～P-35）的实现与实测证据 | 软件层 **656 passed**；浏览器 **75 passed**；kb 自测 10/0、9/0；端到端 **117/117**；文档门 `missing=0`（数字见 STATUS §49/§50） |
| [`NODE_PANEL_ROUND3_20261023.md`](NODE_PANEL_ROUND3_20261023.md) | 第三轮补充修订（R3-01～R3-18）实测证据：N6 印记可解析（P0）、闸门 hard_block 落账、story/前端补齐、一致性与清理 | 软件层 **695 passed**；浏览器 **85 passed**；kb 自测 10/0、9/0；端到端 **117/117**；文档门 `missing=0`（数字见 STATUS §52）；真机复核未执行（服务未重启） |
| [`SPEC_MERGE_20261023.md`](SPEC_MERGE_20261023.md) | 上游 `origin/main`（3 提交）与本地节点面板 R3 工作树的集成：引用边界修复、SPEC-08/09 草案、SPEC-REV-02→04 与 STATUS 节号归一 | 定向单测 **113 passed**；浏览器 **43 passed**；web smoke **8 passed**；投影 41/20、API 契约 7/2（失败均只读数据根）；文档门 `missing=22` 全为 worktree 数据根缺件；已快进合入 main（317df8c）并推送 origin/main |
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
