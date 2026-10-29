# S8 计划 · 独立复核 + D3 会话共享 + 小片清账 + 事件 ts 同源（四片，各自收口）

> 日期：2026-10-29。状态：**四片已收口 + S8e 反代硬化**（S8d 之后完成；未推送）。SpecDD ②产物：本文件 + §2 人工裁决记录 + §8 契约变更清单。
> 入口：[开工提示词 S8](../agents/开工提示词_S8-复核与D3收口.md) §3/§5/§6/§8。
> 契约沿用 [REV-13](../spec/SPEC-REV-13-20261026.md) §5/§7.3/§10、[REV-14](../spec/SPEC-REV-14-20261028.md) §3 D1–D4/§4 B1–B8、
> [SPEC-08](../spec/DSH_AGENT_RUNTIME_SPEC.md) §10/§12、[REV-16](../spec/SPEC-REV-16-20261028.md) §5/§6/§9/§10。
> **S8b 与 S8d 必须先落规格再实现**（§8）：DS-09 判据与事件时间源都是契约变更，不是"顺手改"。

## 1 开工基线（2026-10-29 实测，命令输出复制）

`HEAD=7b38c0e`（= 交接 `31a3c04` + S8 开工提示词提交），`git status --short` 空；
领先 `origin/main` **27**（= 交接时点 26 + 本次提示词提交 1，非漂移），**未推送**（人未授权）。

| 门 | 结果（本轮实测） |
|---|---|
| 单测（可写数据根 `<repo>/.dev-ws`） | `3 failed, 1770 passed, 1 warning, 141 errors in 427.28s`；3 failed 全是既有 `@pytest.mark.env_layer`，141 errors = `tests/browser/**` 缺 Chromium |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 11.73s`；**原 ENV_ROOT 零写入** |
| 端到端（drill） | phase `1/2/3/4/4b/5` 全 `rc=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.27s` |
| 浏览器门（三组 env） | `142 passed in 153.02s` |

与 STATUS §121.4（S7d 收口）**逐项相符**，零新增失败。

## 2 人工裁决记录（2026-10-29 本窗口，人已拍）

| # | 裁决 | 落地 |
|---|---|---|
| **B1 S8b · DS-09 判据** | 授权**治 (i)**：DS-09 **新增"来源判定"**，区分「`dsh` 自生成的会话签名 secret」与「Host 复制来的宿主凭据」；**不改写** `FORBIDDEN_HOME_ENTRIES` 的历史语义，只加来源判据 | §8-1 规格；web home 与 attempt `dsh-home` 共用（回到 REV-14 §D3 的契约），`dsh-web-home` 并列目录**取消** |
| **B2 S8d · 共享判据面** | 授权**按单独变更走**：改规格 → 特征测试固定现行为 → 迁移 → 留证 | §8-2 规格；`host/progress.py::ProgressLog.append` 时间源改注入时钟 |
| **B3 `dsh.web.enabled` 默认值** | **改默认为 `true`**：随 real attempt 自动起本地 Web 服务（多一个 loopback 子进程 + 端口）；失败**不阻断** attempt；attempt 结束后实例**保留** | `SETTINGS.yaml` + `dsh.py` 装配点；**这是改默认运行行为，已获授权并单独登记** |
| **B4 其余三项** | ① **不推送**；② **E（内网业务验收）记"未验证"**；③ **不做公平对照**（沿用 S7 裁决 B4） | 全片遵守 |

**未放宽**：`default_backend` 仍 `agently`；`select()` 之外不放开任何入口；`apply_edits`/`DS-06` 拒绝矩阵不放宽；
反代 R1–R20 与反代目标来源判据不动；`kb/**` 零改动；不 bind `0.0.0.0`。

## 3 切片与写权

| 片 | 内容 | 写权（唯一 writer） | 任务板 |
|---|---|---|---|
| **S8a** | S7 四片独立复核（**只报告不改**） | `s8a-reviewer`：`doc/audit/AUDIT-20261029-s7.md` + `parts/` | `task-1` |
| **S8c** | `identity` 冷读（§9-12）+ 9 条 `500` 定位 | `s8c-impl`：`services/agent_view.py`、`tests/**`（含 `tests/browser/**`）、`services/api.py` 仅必要时 | `task-2` |
| **S8b** | D3 会话共享 + 随 attempt 自动起实例 | `s8b-impl`：`host/agent_backends/{dsh_assets,dsh_web_instance,dsh}.py`、`host/web_instance_ctl.py`、相关 `tests/`；**Lead**：`doc/spec/**`。`loop/SETTINGS.yaml` 一行属 B3 裁决的耦合改动 ⇒ 授权 `s8b-impl` 作为本片唯一 writer，**Lead 复核最终 diff** | `task-3` |
| **S8d** | 事件 `ts` 同源（共享判据面） | `s8d-impl`：`host/progress.py`、相关 `tests/`、drill 夹具；**Lead**：`doc/spec/**` | `task-4`（`blocked_by: task-3`） |

**串行纪律**（`AGENTS.md` §3 + 开工提示词 §6-10）：
1. 片间共享文件（`dsh.py`/`dsh_assets.py`/`web_instance_ctl.py`/`services/**`/`loop/web/**`/`workflows/chunks/**`）**同一时刻只有一个 writer**。
2. S8a 与 S8c 写权不相交 ⇒ 并行；S8b 在 S8c 之后（`services/**` 有交叠风险）；S8d 最后（动共享判据面）。
3. **门独占**：全量 pytest / e2e / kb / 浏览器门**只由 Lead 在收口时串行跑**；各片开发期只跑受影响用例，
   且**各自用独立可写数据根**（`.dev-ws-s8a` / `.dev-ws-s8b` / `.dev-ws-s8c` / `.dev-ws-s8d`）——
   并发共用数据根 = 假红（S7 踩过，见提示词 §9-1）。

## 4 S8a 落点与验收（对象：S7 四片冻结证据与最终树）

| 项 | 内容 | 验收 |
|---|---|---|
| 冻结完整性 | `cd doc/evidence && md5sum -c DSH_S7{A,B,C,D}_20261029.md5` | 四份全绿，真实输出进报告；失败即停手报人 |
| 六重点 | 提示词 §5.1-2 的 a–f（材料面唯一来源/派生物闭包、allowlist 回退档、反代 reason 逐条 + 脱敏漏面、Web 实例 0600/原子写/token 泄露面 + DS-09 关系、S7d 三处"行为未变"） | 每条一个结论 + 证据（命令/文件:行号） |
| 反向抽检 | 关键判据变异成明显错误 ⇒ 用例必须变红 | 抓不住的**如实登记为"覆盖缺口"**，不算通过 |
| 产出 | `doc/audit/AUDIT-20261029-s7.md` + `parts/` | 报告头写「本轮是否修复 = **不修**」；P0/P1/P2 分级 |

**不做**：不修被测文件、不回填冻结件、不把"复核通过"写成"独立验证了业务正确性"。

## 5 S8b 落点与验收（对象：DS-09 来源判定 + 自动起实例 + D3 会话共享）

| 项 | 落点 | 验收 |
|---|---|---|
| DS-09 来源判定 | `host/agent_backends/dsh_assets.py`：`home_problems(home, *, provenance=…)` 增加**来源**参数与判定；`FORBIDDEN_HOME_ENTRIES` 常量**不改语义** | ① 宿主 `settings.yaml` 复制进 home ⇒ **仍拒**；② 内容是宿主凭据值 ⇒ **仍拒**；③ `dsh` 自生成的 `.credentials.yaml` ⇒ **放行**且记录 `source=dsh_generated`；④ 来源 `unknown` ⇒ **fail-closed 拒绝**；四个方向各有用例 |
| home 共用 | `host/web_instance_ctl.py::home_for_attempt` 改为 `<attempt>/dsh-home`；`dsh-web-home` 退场（保留读兼容：旧元数据指向旧 home 仍能 `stop`） | iframe 里能看到该 attempt 的会话列表（真机 DOM 断言 + 截图） |
| 随 attempt 自起 | `host/agent_backends/dsh.py::prepare_attempt`（或 `on_start` 前）在 `mode=real` 且 `web.enabled=true` 时调 `web_instance_ctl.ensure` | ① 起成功 ⇒ `agent_instance.json` 按当前 `(node, attempt)` 重写；② 起失败 ⇒ **attempt 继续**（降级为"不可内嵌"+ 原因），不抛断 attempt；③ attempt 结束**不 stop**（人还要看） |
| 默认开 | `loop/SETTINGS.yaml`：`dsh.web.enabled: true`（裁决 B3） | 默认 real attempt 会起实例；`enabled:false` 时回到 S7 行为（可回退） |
| UI | 会话列表非空（真机截图 + DOM 断言：能看到该 attempt 的 `session_id`） | 元数据随 attempt 切换而跟随 |

**不做**：不放宽反代拒绝矩阵；不把"内嵌成功"当"实时流可用"（WS 仍 405，界面继续如实披露）；不改 `default_backend`。

## 6 S8c 落点与验收（对象：`build_agents` + Playwright 全量 `(url,status)`）

| 项 | 落点 | 验收 |
|---|---|---|
| §9-12 identity | `services/agent_view.py::build_agents` 冷读 `agent_memory` 选中 attempt 的 request/result，**复用** `progress_view(request=…, result=…)` | 卡片与窗口 `identity` **同值同源**（用例逐字比对）；旧记录仍 `null`（不回填） |
| 9 条 `500` | 一次 Playwright 全量 `(url,status)` dump，分离看板页 / iframe 事件流 | 定位到就修（附用例）；不能修则**如实登记根因**，禁止把"没定位"写成"没问题" |

**唯一判据**：identity 提取只在 `progress_view` 一处，不得旁写第二份（红线 8）。

## 7 S8d 落点与验收（对象：`host/progress.py::ProgressLog.append`，共享判据面）

| 项 | 落点 | 验收 |
|---|---|---|
| 特征测试先行 | `tests/`：固定现行为（drill 下 `ts` 走墙钟、`silence_s` 夹 0） | 先红（新契约用例）；改造后转绿 |
| 时间源 | `append` 默认 `ts` 取 `host/paths.py::now_epoch()`（**唯一入口**），不得直接 `time.time()` | `grep time.time()` 在 `progress.py` 归零 |
| 判据 | `silence_s` 同源后自然 ≥0；`max(0,…)` 保留为防御但**不再是掩盖不同源的手段**；检测到 `ts > now`（不同源）⇒ 该字段 `unknown` + `unavailable_reason` | drill 下 `silence_s` 不再夹 0，且**不产生假告警**；真实运行行为不变 |
| 迁移 | 已冻结历史事件（墙钟 `ts`）冷读 | 不报假警、不回填；登记迁移影响面 |

## 8 契约变更清单（SpecDD ①：先改规格，再改实现）

1. **S8b / DS-09 来源判定** → `doc/spec/SPEC-REV-14-20261028.md` **只增 §9**（不改写 B3 与 D3 原文）：
   - 判据四档：`host_settings_copy` / `host_credential_value` / `dsh_generated` / `unknown`，前三档的识别依据与 `unknown ⇒ 拒绝`；
   - 记录字段：准入记录里每个禁止件的 `source` + `basis`（**不写凭据值、不回显 secret**）；
   - home 归属回到 D3「共用同一实例 home」，`dsh-web-home` 并列目录取消（记为 S7c 的临时偏离，S8b 收口）。
2. **S8d / 事件时间源** → `doc/spec/SPEC-REV-16-20261028.md` **只增 §4 一条**（不改写既有"实现期补充"）：
   - 事件 `ts` 必须经 `now_epoch()`；同源后 `silence_s` 自然非负；
   - 不同源（`ts > now`）⇒ `unknown` + 原因，不得夹成 0 冒充"无进展"；
   - 迁移：历史事件不回填。
3. **收口登记** → `SPEC-REV-16` §10 只增行：§9-12（S8c）、§9-8（S8d）、§9-6 后半（S8b 自动起）。
4. **S8e 反代硬化（由 S8a 复核 P1-2 / P2 派生，2026-10-29）** → `SPEC-REV-16` §5.4 **只增两条澄清**（不改写 R12 原文）：
   - R12 的"读 15 s"是**非流式**口径；`Accept: text/event-stream` 的请求不设读超时（连接超时 1 s 仍生效），
     响应头已发出后的读失败只允许干净结束 + 记日志（不得改 503）；
   - "token 永不出现在本服务日志"的覆盖面 = 所有 logger / handler / 字段（子 logger 冒泡、`extra=`、
     `exc_info` traceback、参数化 `%s` 合并后），判据仍是唯一一条 `token=<值>` → `token=<redacted>`。
   - 同一轮的 P2 修复（不需要新契约，属加固）：`session-copy` 的 reason 收敛到 §6.2 六项枚举（不透传 SDK 自由文本）、
     `_error_page` 插值一律 HTML 转义。

## 9 验证门（每片收口各自跑；`AGENTS.md` §4 是权威；**Lead 独占、串行**）

```bash
# 单测：先 cleanup 再 provision（残留半成品会造 70+ 假红）
cd loop && bash spikes/provision_dev_workspace.sh --cleanup
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# kb 自测 + 环境层（派生 ENV_ROOT 副本；原 ENV_ROOT 零写入）
cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests

# 端到端（drill）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# 文档门
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_doc_links.py

# 浏览器门（S8b/S8c 改界面或界面字段 ⇒ 必跑）
cd loop && PLAYWRIGHT_BROWSERS_PATH=/home/work/chenjunming/change-impact-loop/.pw-browsers \
  HOME=/home/work/chenjunming/change-impact-loop/.chrome-home \
  TMPDIR=/home/work/chenjunming/change-impact-loop/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser
```

## 10 未决（照实登记，不静默补实现）

| # | 未决 | 处置 |
|---|---|---|
| 1 | WebSocket/SSE 升级（REV-16 §9-2）**本轮不做** | 沿用 S7 裁决：已如实披露，性价比最低；界面继续写"实时流未接通" |
| 2 | 会话原文导出（REV-16 §9-11） | 登记；`session-copy` 仍只给 `session_log_facts` |
| 3 | `node_rework`/`run` 终态到期归约（S3 计划 §6.4-39） | 登记，另开小片；界面继续写"未判定" |
| 4 | Web 实例未套 bwrap（S7C 证据档 §7-5） | 登记（加固，非阻断） |
| 5 | N6 真机 `edits` 业务可疑（STATUS §118.3） | **N8/人**（业务正确性，机制层不判，本轮不冒充"已验证"） |
| 6 | E（内网业务验收） | 人裁决记"**未验证**"，不伪造环境 |
| 7 | 公平对照 | 不做（沿用 S7 裁决 B4） |
| 8 | **D3 产品路径（同源反代 iframe）被 `remote.mux` WebSocket 405 挡住** | S8b 真机实测：**机制达成**（直连实例可见该 attempt 的会话行）、**内嵌路径未达成**。两条可选后续**均需人裁决**：① 收口 REV-16 §9-2（WS 升级，本轮明示不做）；② 把"在新标签页打开"指向**直连实例**（人可看可说，但不内嵌）。**不写成"已达成"** |
| 9 | 多节点 Web 实例累积 | `_REGISTRY` 按 `(run,node)` 建键 ⇒ 一次 real run 走 N 节点会留 N 个 loopback 实例；`stop_all()`/`stop()` 可收。已写进 docstring（已知行为，非缺陷） |
| 10 | 时间不同源只有单方向可判别 + `elapsed_s` 未纳入 null 面 | REV-16 **§9-18**（S8d 收口时新登记）：反方向与"真的长期静止"不可区分 ⇒ `unknown` 不猜；`elapsed_s` 纳入须单独变更 |
| 11 | S8a 复核的 P2-6/P2-10/P2-11 + G4/G6 | 登记下一轮（无消费者字段 / 证据覆盖缺口 / 命名口径） |
| 12 | `DSH_S8D_20261029` 的 `--link-fixture` env_layer 夹具限制 | 实现者自查用 `-m "not env_layer"`；Lead 收口门用**完整 provision** 数据根（见 STATUS §127） |

## 11 STATUS 节号

§123 基线 · §124 S8a · §125 S8b · §126 S8c · §127 S8d · §128 S8 交接（若需要）。
数字**只从命令输出复制**；每片收口时四道门全部重跑并写新节。
