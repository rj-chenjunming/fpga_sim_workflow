# 未修复清单与开工提示词（2026-10-27，新窗口用）

> **怎么用**：把本文件 §4 的代码块整段复制给新窗口/新会话即可开工；§2 是它要处理的清单，
> §3 是建议顺序。本文件是**交接性质**（不是新契约），事实与数字都能在 `doc/STATUS.md` §81–§92 找到出处。

## 1 现状快照（2026-10-27 收工时）

| 项 | 值 |
|---|---|
| 分支 / 提交 | `main`，工作树干净；**29 个提交未推送**（`a34886d` 收工时 28，本开工单提交后 29；本机出网被代理阻断） |
| 最近提交 | `a34886d fix(B1b)`（403 文案统一） |
| 软件层门 | **979 passed / 3 deselected / 0 failed** |
| 浏览器门（补充门） | **114 passed** |
| 端到端 | **ALL PASS，117 断言 / 0 FAIL** |
| 文档门 | **missing=0，exit=0** |
| kb 自测 | `_selftest_gate_schema` **10**、`_selftest_n5_reachability` **9**、`_selftest_adjudicate_conflicts` **28** |
| 环境层用例 | **3 passed / 24 deselected**（派生 ENV_ROOT 副本上跑） |
| 环境硬限制 | `<ENV_ROOT>` 在 `/home` 的 **ro 挂载**上（`ro,nosuid,nodev`）⇒ 任何写 `ENV_ROOT` 的动作都不可行（含红线 11 允许的 `SIMLIB_RUN/`） |
| 磁盘 | `.env-copy/` 2.6 GB（派生 ENV_ROOT，含已签裁决数据根；git 已忽略）；`workspaces/real-env-copy/` 为旧派生副本（ignored） |

> **2026-10-27 开工轮更新（本表是收工时快照，不回溯改）**：K1 已落地（一条命令跑 kb 自测 + env_layer）、
> K2 已加过期横幅、K3 已清理 `.env-copy`；软件层门因新增 K1 用例不再是 979。数字与命令见
> [STATUS §94](../STATUS.md)，未闭合项仍是 E1/E2/E3/D1–D4（环境侧或需人裁决）。

## 2 未修复清单（按"谁能推进"分类）

### E 类：环境侧才能推进（本仓已把动作固化成命令/runbook）

| 编号 | 事项 | 现状（为什么没修） | 怎么处理 | 验收判据 |
|---|---|---|---|---|
| **E1** | **I4 真实生效**：72 条冲突裁决还没写进真实数据根 | 已落账到派生副本并快照入仓（`doc/evidence/adjudication_20261027/`，md5 `d6ec877…`/`47300360…`）；真实 `ENV_ROOT/kb` 是 ro 挂载 ⇒ 写不进 | 拿到**可写数据根**后：`bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根>`（先 `--dry-run`）；或 `remount -o rw /home` 后对真实数据根跑 | `blocks_release=0`；`G3 full_now/subset_only` 提交前检查通过；N16 blockers 不含 `I4_CONFLICTS_UNCLEARED`（§87.3 有 before/after 对照） |
| **E2** | **C9 S0-b 接入**（`ports`/`smoke` 恒 waiting） | 环境插件侧 D1–D5（`TB/top.sv` 接口适配、逐 hunk 登记、三库冒烟）未做；`S0Store.get()` 因此把 `ready_for_execution` **归一为 false** | 环境侧开发；本仓侧接入验收清单在 `S0_ENVIRONMENT_SPEC §8`。接入后 **只需改一处判据**：`get()` 的归一逻辑（放开到真实核验结果） | S0 规格 §8.5 全部；`test_s0.py` 新增/改期望；`GET /api/s0/{id}` 能返回 `ready=true` |
| **E3** | **C8 passed 形态夹具** | 只有 `real/failed` 与 `drill/finished`（报告 `not_passed`）两套；drill 回放拿不到 passed（改日志=伪造证据） | 环境可写 + EDA 工具/许可后，按 [`2026-10-27-c8-feasibility.md`](2026-10-27-c8-feasibility.md) §2-P2 runbook 跑一次真实通过轮（N9 ≈**21.56 h**，吞吐 ≈3.8 µs/s），再冻结成夹具 | N9 每例 `rc=0` 且错误标记行=0；印记三向一致；报告 `claimed_verdict=passed`；I2/I3 清零；夹具带 `md5.txt`（`md5sum -c` 通过）+ README |
| **E4** | **推送 29 个提交** | 本机 `git push` 报 `Received HTTP code 503 from proxy after CONNECT`；清代理直连亦不可达 | 在能出网的机器：`cd change-impact-loop && git push origin main` | `git rev-list --count origin/main..HEAD` = 0。**顺手把对话里出现过的 PAT 作废重签**（本仓从未落盘） |

### D 类：需人裁决 / 外部输入

| 编号 | 事项 | 现状 | 需要谁做什么 |
|---|---|---|---|
| **D1** | 4 条 Tier B-core 的取值只有"人给的方向"，作者未确认 | C2/C11/C38 以位定义为准、C58 以 `DFX_VERSION` 为基准，已按人批示落账（每条 resolution 末尾注明"人工批示，Host 工具代录"） | 作者或文档 owner 给出口径；若不同，按**追加改判**处理（`adjudicate_conflicts.py --id C2 --status ruled --resolution …`，不改历史） |
| **D2** | 裁决 actor 是 `human:chenjunming` 但写入是 Host 代录 | 代录事实写在每条 `resolution` 与快照 README，不冒充亲笔 | 若要亲笔：在有写权环境重跑 `doc/evidence/conflicts_sign_20261027.sh`（追加记录，历史保留） |
| **D3** | C11-B：取消后"重跑作业 / 终止本轮"二选一（未做） | 当前取消=终态失败（已裁决 A 方案并补齐后果告知） | 若要做，**先改** `LOOP_ORCHESTRATION_SPEC §6 第 9 条`与 §5，再改状态机/API/UI/测试；属中大型切片 |
| **D4** | C12-B：把 S0 真正并入运行入口（未做） | 当前只做"传了才校验"（A 方案） | 需 E2 完成 + 显式 `s0_rehearsal` 选项 + N0 消费派生副本 + 调整 `project==ENV_ROOT` 约束；须先改规格 |

### K 类：本仓可自行推进（无外部依赖）

| 编号 | 事项 | 现状 | 怎么做 | 验收 |
|---|---|---|---|---|
| **K1** | **kb 自测没有入口脚本**：目前要手动 `LOOP_ENV_ROOT/LOOP_WORKSPACE` 指向派生副本（`_selftest_gate_schema.py` 直接跑会在真实 ENV_ROOT 上失败） | ✅ **已完成（2026-10-27，选 ②）**：`run_env_layer_checks.sh --with-kb-selftests` 一条命令跑 3 个 kb 自测 + 3 条 env_layer，共用同一个派生副本；实测 `PASS=10/9/28` + `3 passed`、原 ENV_ROOT 零写入（[STATUS §94](../STATUS.md)） | 二选一：① 新增 `loop/spikes/run_env_checks.sh`，先建/复用派生副本再跑 3 个 kb 自测 + 3 条 env_layer；② 或让 `run_env_layer_checks.sh` 加 `--with-kb-selftests` | 一条命令输出 `PASS=10` / `PASS=9` / `PASS=28` + `3 passed`；更新 `AGENTS.md §4` 与交接单 |
| **K2** | **旧派生副本 `workspaces/real-env-copy/` 仍在**，其中 `loop/web/index.html` 含已删除的 `GATE_DECISIONS_FALLBACK`（2 处） | ✅ **已加过期横幅（2026-10-27）**：`workspaces/real-env-copy/OBSOLETE-20261027.md`（带 index.html 的 md5 与 2 处行号）。**未删除**的理由：内含 2026-10-22 真实执行的 `SIMLIB_RUN/`（978 MB）与 `kb/`（1.1 GB）留痕，且冻结证据按该路径引用当时环境（删了文档门会红） | 删除该副本，或在其内加"已过期"横幅说明不可作为新版前端验收对象 | 目录消失或带横幅；`git status` 不受影响 |
| **K3** | `.env-copy/` 2.6 GB 占盘（含已签裁决的派生数据根） | ✅ **已清理（2026-10-27）**：`run_env_layer_checks.sh --cleanup` 执行后目录消失（`du -sh` 2.6 G → 不存在）；裁决快照仍在 `doc/evidence/adjudication_20261027/`，需要时重建见 STATUS §94 | `bash loop/spikes/run_env_layer_checks.sh --cleanup`（下次重建约 10 s） | 目录消失；需要时能重建 |
| **K4** | 环境层/浏览器门的"必须单独跑"口径只在 AGENTS 与交接单里 | ✅ **已落地（2026-10-27）**：[`loop/README.md` §2.1](../../loop/README.md) 新增"门清单：四道必备 + 两道补充"（命令/前置/期望 + "改动落在哪就重跑哪道"），判据仍以 `AGENTS.md §4` 为权威、数字只指向 `doc/STATUS.md` | 可选：在 `doc/plans/` 里补一条"门清单"单页，或在 `loop/README.md` 里加门命令表 | 新窗口按文档能跑通四道门 + 两道补充门（实测见 STATUS §95） |

### R 类：登记不改（有理由，别当缺陷重开）

1. **两轮历史复核报告未入 `doc/audit/`**：对话里已无原文，复原=伪造证据；已改为"每轮复核即落档"（本轮起）。
2. **3 条 `@pytest.mark.env_layer` 用例不在默认全量门**：环境缺件；已有单独入口
   `run_env_layer_checks.sh`（红线 11 用 `find -newer` 自证原环境零写入）。
3. **浏览器门不并入全量单测门**：补充门（裁决 A4，STATUS §81.4），理由写在 `AGENTS.md §4`。
4. **`SPEC-REV-12` 里的"接受失败报告"**：概念表述（非 403 原文），不改；403 原文已统一（§92）。
5. **`<ENV_ROOT>/kb/tools/` 下历史 `.pyc`**：属 `ENV_ROOT` 写入范畴（红线 11），不删；新入口已用 `-B`/`dont_write_bytecode` 不再新增。
6. **移动端适配**：已裁决不在功能开发范围。
7. **drill 直给 `entry_decisions` 不额外要求整门理由**：方向更严，裁决维持现状（§82.3）。
8. **STATUS 不落盘 `checked/skipped`**：诊断值随树漂移（§19）。

## 3 建议开工顺序

1. **先验证基线**（15 分钟）：`git status` / `git log --oneline -30` / 跑四道门（§5 命令）。
   数字应与 §1 一致；不一致先查清楚再动手。
2. **K1**（小、能立刻让"环境类检查"一条命令跑完，后续验证都受益）。
3. **K2/K3**（清理类，5 分钟）。
4. 若此时拿到了**可写数据根** ⇒ **E1**（I4 生效）+ 复验 G3/N16 路径；否则跳过。
5. **E2 / E3** 属环境侧排期；本仓能做的只有"接入后改一处判据"与"跑完冻结夹具"。
6. **D3 / D4** 一律"先改规格再改代码"，且需人明确要做。

## 4 开工提示词（整段复制给新窗口）

```text
你在仓库 /home/work/chenjunming/change-impact-loop（分支 main）开工。这是一个"变更影响闭环"软件仓，
流程权威是 AGENTS.md，业务/机制契约在 doc/spec/*.md。请先按下面顺序读，再动手。

一、开工先读（不要跳）
1) AGENTS.md（全篇，尤其 §2 SpecDD、§3 写权、§4 四道门、§5 红线 12 条）
2) doc/STATUS.md 的 §81–§92（上一轮 A/B/C 组的实测与裁决记录）
3) doc/plans/2026-10-27-kickoff-unresolved.md（未修复清单 + 处理办法，就是你手上这份）
4) doc/plans/2026-10-27-c-group-handover.md（C 组交接单：门数字、环境侧三件事、接手第一小时顺序）
5) 触及相关切片时再读对应规格：doc/spec/{CHANGE_IMPACT_LOOP,LOOP_ORCHESTRATION,WEB_UI,S0_ENVIRONMENT}_SPEC.md

二、当前状态（2026-10-27 收工）
- 工作树干净；29 个提交未推送（收工时 28，开工单提交后 29；本机出网被 HTTP 代理阻断，推送由人做，你不要尝试改 git 凭据）。
- 门：软件层 979 passed / 3 deselected；浏览器 114 passed；端到端 117 断言 ALL PASS；文档 missing=0；
  kb 自测 10/9/28；环境层 3 passed。
- 环境硬限制：<ENV_ROOT> 在 /home 的 ro 挂载上（ro,nosuid,nodev）。任何写 ENV_ROOT 的动作都不可行。
  需要可写数据根时用 loop/spikes/provision_dev_workspace.sh（一次性影子）或
  loop/spikes/run_env_layer_checks.sh（派生 ENV_ROOT 副本，含零写入自证）。
- 只读纪律：<ENV_ROOT>/kb 与 doc/evidence/**、doc/history/** 只增不改；冻结目录 kb/tools/**、kb/schema/**
  要改必须先拿到人授权，并留改前/改后 md5（红线 10）。

三、本轮任务队列（按顺序做，一次只做一项，做完停下报告）
1) 先验证基线：git status、git log --oneline -30，并按 §5 命令跑四道门；数字与上面不一致就先查原因，
   不要继续往下做。
2) K1：给"环境类检查"做统一入口（kb 自测 3 个 + env_layer 3 条，一条命令跑完），
   并更新 AGENTS.md §4 与交接单。验收：一条命令输出 PASS=10 / PASS=9 / PASS=28 + 3 passed。
3) K2/K3：清理 workspaces/real-env-copy（或加过期横幅）与 .env-copy（run_env_layer_checks.sh --cleanup）。
4) 若有人给了可写数据根：做 E1（bash loop/spikes/apply_conflict_adjudication.sh --workspace <ws>），
   并复验 G3 full_now/subset_only 与 N16 blockers 不再含 I4_CONFLICTS_UNCLEARED。
5) E2/E3/D3/D4 只登记、不擅自开工；它们需要环境侧或人裁决（D3/D4 必须先改规格）。

四、做事方式（本仓硬纪律）
- SpecDD：先读规格 → 需要时先改规格 → 写计划 doc/plans/ → 先失败用例（TDD）→ 实现 → 四道门 → STATUS 落账。
- 数字一律从命令输出复制，不许手算；唯一数字源 doc/STATUS.md。
- 不得声称"独立验证"：实现者自己跑的门只能写"本轮实测"；需要独立复核时另起 agent，且复核者只报告不改。
- 环境不可用就如实登记（failed/skipped/未运行分开写），不许把跳过当通过、不许伪造夹具或环境。
- 完成一项就 commit（中文 commit message，说明"改了什么/为什么/怎么验证"），不要攒着一起提交。
- 用户偏好：一次只做一项，做完先报告再继续；报告要短、给数字与出处（文件:行）。

五、常用命令
- 软件层：cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser
- 浏览器：cd loop && PLAYWRIGHT_BROWSERS_PATH=$PWD/../.pw-browsers HOME=$PWD/../.chrome-home \
    TMPDIR=$PWD/../.chrome-tmp .venv/bin/python -m pytest -q tests/browser
- 端到端：cd loop && bash spikes/provision_dev_workspace.sh --force --quiet && \
    LOOP_WORKSPACE=$PWD/../.dev-ws bash spikes/accept_v1_run.sh   # 跑完 provision --cleanup
- 文档门：python3 doc/audit/check_doc_links.py    # 跑前先删仓内临时数据根（.dev-ws/.env-copy 已加跳过规则）
- 环境层：cd loop && bash spikes/run_env_layer_checks.sh          # 3 passed，自证原 ENV_ROOT 零写入
- kb 自测：cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests --reuse
    # 一条命令 = 3 个 kb 自测（PASS=10/9/28）+ 3 条 env_layer，共用派生副本（K1，2026-10-27）
    # **不要再手拼 LOOP_ENV_ROOT/LOOP_WORKSPACE**：忘了指就在只读真实根上失败（AGENTS.md §4）

六、汇报格式（每完成一项）
1) 做了什么（改了哪些文件）2) 判据/为什么这么改 3) 命令与输出数字 4) 门的结果 5) 未闭合项与下一步建议。
```

## 5 关键文档与命令索引

| 用途 | 位置 |
|---|---|
| 流程权威 / 写权 / 门 / 红线 | [`AGENTS.md`](../../AGENTS.md) |
| 唯一数字源与全部实测记录 | [`doc/STATUS.md`](../STATUS.md) §81–§92 |
| C 组交接单（环境侧三件事） | [`2026-10-27-c-group-handover.md`](2026-10-27-c-group-handover.md) |
| C8 评估与 passed 夹具 runbook | [`2026-10-27-c8-feasibility.md`](2026-10-27-c8-feasibility.md) |
| 72 条冲突裁决材料与命令 | [`CONFLICTS_SIGNING_20261027.md`](../evidence/CONFLICTS_SIGNING_20261027.md)、[`conflicts_sign_20261027.sh`](../evidence/conflicts_sign_20261027.sh) |
| 裁决落账快照 | [`adjudication_20261027/README.md`](../evidence/adjudication_20261027/README.md) |
| 演示夹具（可用） | [`DEMO_FIXTURE_20261026.md`](../evidence/DEMO_FIXTURE_20261026.md) |
| I4 生效脚本 | `loop/spikes/apply_conflict_adjudication.sh` |
| 环境层用例入口 | `loop/spikes/run_env_layer_checks.sh` |
| 数据根预置 | `loop/spikes/provision_dev_workspace.sh` |
