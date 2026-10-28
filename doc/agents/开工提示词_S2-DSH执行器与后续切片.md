# 开工提示词 · S2 与 DSH 执行器后续切片（2026-10-28 交接）

> 用途：**在新窗口第一条消息直接整段粘贴**（或说「按 `doc/agents/开工提示词_S2-DSH执行器与后续切片.md` 开工」）。
> 交接时点：`a36c3aa`（S1 机制层已交付）；本地**领先 origin/main 6 个提交、未推送**。
> 本文自包含：读完这一份 + 文中"必读"四件，即可开工，不需要历史聊天。

---

## 0 给新窗口的第一条消息（可直接粘贴）

```text
接手 /home/work/chenjunming/change-impact-loop（change-impact-loop 软件仓）。
按 doc/agents/开工提示词_S2-DSH执行器与后续切片.md 开工：先读 §1 必读四件，再按 §4 任务做 S2
（submit_result 结构化候选 / sdk stdio 观测面 / B2-B3 启动自检），并先跑 §5 的四道门收口 S1。
遵守 §6 纪律与 §7 已知坑；开工前先 `git log --oneline -3` 与 `git status --short` 核对现场。
```

---

## 1 必读（按顺序，别跳）

| # | 文件 | 读它是为了 |
|---|---|---|
| 1 | [`AGENTS.md`](../../AGENTS.md) | 流程权威：SpecDD 顺序、四道门命令、写权、红线 |
| 2 | [`doc/STATUS.md`](../STATUS.md) §103/§105/§106/§107/§108/§109 | 本轮实测与门（**唯一数字源**；别在别处抄数字） |
| 3 | [`SPEC-REV-13`](../spec/SPEC-REV-13-20261026.md)、[`REV-14`](../spec/SPEC-REV-14-20261028.md)、[`REV-15`](../spec/SPEC-REV-15-20261028.md) | 执行器契约、D1–D4 偏离与复评条件、闸门 stateHash |
| 4 | [三层对齐体检表](../plans/2026-10-28-three-layer-interaction-alignment.md) §2/§6.3/§7/§9 | 目标态 12 条、Q1–Q8 裁决、与 REV-13 的冲突处置 |
| 5 | 证据档：[`DSH_PROBE_20261028`](../evidence/DSH_PROBE_20261028/README.md)、[`DSH_P0_20261028`](../evidence/DSH_P0_20261028/README.md)、[`S1 计划`](../plans/2026-10-28-s1-dsh-process.md) | 探针结论（哪些是实测、哪些是残余风险） |

> 两份证据档都是**冻结件（444 + 目录外 md5）**：只读，不许改；新证据另开目录并同样冻结。

## 2 现状快照（交接时）

| 切片 | 状态 | 证据 |
|---|---|---|
| S0 规格（REV-14：D1–D4 偏离 + B1–B7 补丁 + 切片映射） | ✅ 已交付 | STATUS §106 |
| S0b 闸门绑产物指纹 `stateHash`（kb 冻结目录单独变更 + T1–T8） | ✅ 已实现并过门 | STATUS §107、REV-15 |
| P0 能力清单 + 真隔离探测（bwrap 挡宿主数据；`/proc` 仍泄 key） | ✅ 已交付 | STATUS §108、P0 证据档 |
| S1 机制层（`dsh_protocol`/`dsh_process`/`dsh.py` + SETTINGS 段 + 21 用例 + 真机包裹集成） | ✅ 已交付**机制**；**未跑全量四门** | STATUS §109 |
| S2（结构化候选 / sdk 观测面 / 启动自检） | ⬜ **本轮任务** | 待建 |
| S3–S6（WM/IL/EXP、投影界面、C2、D4） | ⬜ 后续 | REV-14 §6 映射 |

**关键红线**：`agent_backends.select()` 对 dsh 仍抛 `BackendUnavailable`（`SETTINGS` 里 `enabled:false`）。
**实现存在 ≠ 准入**：不得为了"跑通"把它改成默认放行。

## 3 下一阶段（S2）的三件事

### T1 结构化候选：`submit_result` 收口（B1 + DS-02）
- 探针已证：`--patch` 挂 ESM 插件 → 模型真调用 → `tool_call`/`tool_result` 事件与 handler 在 DSH 子进程执行（证据档 P2）。
- 要落成：**插件源码进仓**（放 `loop/host/agent_backends/dsh_plugin/` 或明确位置），`submit_result(task_id, summary, payload)` 的 handler **不校验业务**，只把 payload 交给 Host 的 `_validate`（唯一判据仍在 `workflows/chunks/model_steps.py`）。
- 收口判定：`turn_end(kind=completed)` **且** `submit_result` 已接受；缺一不得出候选（`dsh.py` 目前的 `text` 占位必须去掉）。

### T2 sdk stdio 观测面（B4）
- 事实：`subagent.started/finished` 与 compaction 事实**只**在 sdk 协议/session log；headless `--json` 里 0 条。
- 要做：`session/prompt`、`session.event`、`session.status`、`session/wait` 的最小客户端（REV-13 §5.1 要求先锁版本与类型映射，不许编方法名）；`subagent.*` 与压缩计数落账（Host 侧）。
- 若 S2 内无法稳定：**显式降级**并把 B4 的观测面标"未实现"，不要用 headless 假装。

### T3 启动自检（B2/B3 + DS-08/DS-09/DS-10）
- B2：插件/工具加载失败只出 `dsh: warning: 1 entry did not activate`（探针 P2）⇒ 起会话后必须验"工具清单含 `submit_result`"，缺则显式失败。
- B3：权限档会被用户层 `permission-presets.defaultPreset` 覆盖（探针 P3）⇒ `sandbox-policy.mode` + `defaultPreset` **双钉**并回显实际值。
- DS-10：bwrap 包裹生效（宿主 home 不可读 + 无关 env 不继承）；**不含** `/proc` environ（D1 残余风险）。

## 4 开工动作清单（建议顺序）

1. `git log --oneline -3 && git status --short`；确认 HEAD 是 `a36c3aa` 且工作树干净。
2. 读 §1 五件（约 20 分钟）；把 D1–D4 的**复评条件**抄到自己的笔记里（别改规格）。
3. **先跑四道门收口 S1**（见 §5），把数字写进 STATUS 新节；红/缺件照实登记。
4. 再按 T1 → T3 → T2 顺序做（T2 依赖锁定版本与类型，放最后；T1/T3 不依赖 sdk 协议）。
5. 每片：先失败用例（`loop/tests/test_dsh_*.py`），再实现，再受影响回归；提交信息写清"哪条契约/哪条证据"。
6. 收口时更新 STATUS（新节，只增），必要时更新 REV-14 的状态行（**不改历史正文**）。

## 5 四道门（命令照抄；`AGENTS.md` §4 是权威）

```bash
# 单测（必须可写数据根，否则 drill/基线类用例会因缺件失败——那是环境缺件，不是代码缺陷）
cd loop && bash spikes/provision_dev_workspace.sh          # 先造 .dev-ws
cd loop && LOOP_WORKSPACE=$PWD/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
cd loop && bash spikes/provision_dev_workspace.sh --cleanup   # 跑文档门前必须清理

# kb 自测 + 环境层（派生 ENV_ROOT 副本，原 ENV_ROOT 零写入）
cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests
# 期望：PASS=10 / PASS=9 / PASS=28 + env_layer 3 passed

# 端到端（drill，可写数据根）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=$PWD/.dev-ws LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh
cd loop && bash spikes/provision_dev_workspace.sh --cleanup
# 期望：phase 1–5 全 rc=0，ALL PASS

# 文档门
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_doc_links.py
```

> 参考数字（本轮实测，别当自己的门结果抄）：S1 定向子集 `51 passed`、真机包裹集成 `status=completed text=OK`、
> S0b 全量 `1062 passed, 3 failed(env_layer), 113 errors(browser)`、文档门 `65 passed`。**四门必须自己重跑并记录**。

## 6 纪律（硬约束）

1. **SpecDD**：改行为先改规格；规格缺口登记进 §未决，不静默补实现（`AGENTS.md` §2）。
2. **写权**：`kb/**` 冻结目录改语义必须**单独变更 + 留证**；证据/历史只增不改；`doc/STATUS.md` 是唯一数字源。
3. **不声称**：C1（机制）≠ C2（真实内核 + 模型）≠ E（内网业务）；探针/握手/演练都不是业务验收。
4. **失败显式**：`failed` + `error` + 关闭执行；**不许**把崩溃/超时/缺件伪装成"在等人工"。
5. **偏离带复评条件**：D1 凭据、D2 压缩、D3 共用 home+resume+GUI 说话、D4 子 agent 配额 2——每条都有触发条件，条件满足要回来重评（REV-14 §3）。
6. **独立复核**：实现者不得同时声称独立验证；发现缺陷只报告，修复走 SpecDD。
7. **推送**：需人授权 + 凭据（`$HOME` 只读 ⇒ 只能临时放仓库 `.git/`，用完删；PAT 用后建议作废重建）。

## 7 已知坑（本轮实测踩过，别再踩）

| 坑 | 事实 | 对策 |
|---|---|---|
| `/tmp` 跨 bash 调用不共享 | 每次调用独立临时区 | 产物一律放仓内（`workspaces/.probe-dsh/` 等 gitignored 路径） |
| `$HOME` 只读 | `~/.dsh`、`~/.gitconfig`、`~/.git-credentials` 都不能写 | 凭据/配置走仓内 `.git/` 或 `workspaces/`；环境变量注入 |
| 宿主 settings 带 `danger-full-access` | 复制 `~/.dsh/settings.yaml` 进 attempt home ⇒ 越界写 rc=0 | attempt home **最小化**；`mode`+`defaultPreset` 双钉并回显 |
| plugin 加载失败只 warning | `1 entry did not activate` 不阻断启动 | 启动自检工具清单（B2） |
| headless 无 subagent/compaction 事件 | 0 条 | 观测面只能 sdk 协议 + session log（B4） |
| patch 文件被 bwrap 遮蔽 | 宿主 home 被 `--tmpfs` 掉 | patch 必须放 **attempt 目录内** |
| `/proc/<dsh-pid>/environ` 可读 key | 同 uid，pid ns 挡不住 | D1 残余风险，记档；**不要**声称已挡 |
| bwrap 0.4.0 无 `--clearenv` | 需要 `env -i` 替代 | 进程层已用白名单 env 实现 |
| `pgrep -af 'sleep 45'` 会匹配自己 | 命令文本含匹配串 | 用 `pgrep -P` 走子孙链 |
| 浏览器门缺件 | 113 errors（无 Chromium） | 单独门、单独记；不要并入四道门 |
| `.dev-ws`/`.env-copy` 派生副本 | 体积大（733 MB / 2.6 GB） | 跑完 `--cleanup`；跑文档门前必须清理 |

## 8 完成定义（S2 收口）

- T1/T2/T3 各自的先失败用例转绿；受影响回归无红（记录 passed/failed/skipped）；
- 四道门在本片收口时**全部重跑**并写 STATUS（数字从命令输出复制）；
- `select()` 的准入条件仍显式（启用 + 指纹 + 自检通过），未通过则保持 `BackendUnavailable`；
- 证据新增（新目录冻结 + md5 目录外）；STATUS 新节；提交信息可追溯到契约条款与证据。

**不要做的事**：不要改 kb 语义而不单独变更；不要为了跑通把 `enabled`/`select()` 放行；不要重跑探针当验收；不要 push 未授权；不要把"机制能跑"写成"CM/业务可用"。
