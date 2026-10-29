# S7a 证据档 · N6 收口 + DS-06 真机（2026-10-29）

> 状态：**N6 收口达成（真机 `submit accepted` + `validation.ok=true`）；DS-06 真机 = 通过
> （候选由 Host 导入并 `applied`，含"Host 重放同一次真实 attempt"的限定，见 §5）。**
> 执行者：Lead（实现 + 真机 + 收口）；**本片没有独立复核者**（与 S4 不同，照实说明，不声称独立验证）。
> 入口：[开工提示词 S7](../../agents/开工提示词_S7-暴露面收敛与真机收口.md) §4.1；计划
> [`2026-10-29-s7-exposure-convergence.md`](../../plans/2026-10-29-s7-exposure-convergence.md) §2-B1/§4。
> 契约沿用 [REV-13](../../spec/SPEC-REV-13-20261026.md) §4/§10（`DS-06`）、
> [REV-14](../../spec/SPEC-REV-14-20261028.md) §4 B1/B3、[SPEC-08](../../spec/DSH_AGENT_RUNTIME_SPEC.md) §5/§10（D04）/§12——
> **未新写替代契约**。
> 目录只增不改；冻结（444）与 `doc/evidence/DSH_S7A_20261029.md5` 由 Lead 在提交前一次完成。

## 1 结论（三态）

| 项 | 结论 |
|---|---|
| **N6 真机收口** | **通过**：`exit=completed`、wall **127.234 s**、`validation.ok=True`、`problems=[]`、`execution_state=stopped` |
| **六节点** | **6/6**（N3/N8/N10/N11/N12 见 STATUS §115.3；N6 = 本档 §5） |
| **DS-06 候选导入** | **通过**：`n6_apply.status=applied`、`candidate_import.ok=True`、5/5 `source=candidate_import`。**限定**：导入步骤是对**同一次真实 attempt 的候选与封存输出**的 Host 重放（探针把 `n6_targets` 喂成 1 个，Host 正确 fail-closed；见 §5.3） |
| 效果/成本对照 | **不作结论**（人工裁决 A4/B4：不跑 Agently 对照组 ⇒ 只能"探索/证据不足"） |

**不声称**：不声称业务正确（Host 只判结构与契约，模型 `edits` 的业务正确性属 N8/N12）；不声称工具面已收敛
（本片真机 `toolNames` 仍是 26 项全量 harness，收敛属 S7b）；不声称 E（内网业务验收）；不声称对照收益。

## 2 交付物

| 文件 | 变更 | 契约 |
|---|---|---|
| `loop/host/agent_backends/dsh_assets.py` | 新增 `N6_SUMMARY_NAME`/`N6_SUMMARY_SCHEMA`/`DERIVED_MATERIALS`/`NODE_MATERIALS`/`materials_for(node)`/`derive_material()`：**每节点材料面的唯一来源**；N6 只拿派生摘要 | REV-13 §5.4；S7a §4.1-1 |
| `loop/host/agent_backends/dsh.py` | `stage_inputs` 支持**派生物**（记 `derived_from{name,md5,size}`，源件坏/缺/链接一律显式失败）；`prepare_attempt` 材料缺省走 `materials_for(node)`，显式入参只用于用例；`_compose_task` 明确"payload 必须是对象、不是字符串" | REV-14 B1；DS-02 |
| `loop/host/agent_backends/dsh_plugin/submit_result.mjs` | `payload` 参数描述改为"**必须是 JSON 对象**；不要传字符串化后的 JSON（会被提交门拒）" | REV-14 B1（**判据未变**，只改模型可见说明） |
| `loop/host/agent_backends/dsh_protocol.py` | `payload` 非对象时错误信息写"期望 object / 实际类型 / 收到字符串时的修正提示" | DS-02（判据未变） |
| `loop/workflows/chunks/host_steps.py` | `apply_edits` 行号漂移错误信息点名字段、声明值、实际行号，并指出"line 该从哪来" | **判据未变**（old 唯一且落在声明行） |
| `loop/prompts/loop_nodes.yaml` | `n6_author.info.rules` 增加一条：`line` 必须**逐字复制** `excerpts[].text` 片段行首的十进制行号 | 模型输入文本（不改 schema/判据） |
| `loop/SETTINGS.yaml` | `dsh.timeout_s` **600 → 300**：与人工裁决 B1 的单次上限**同一个数**（S5 有过"文档写 120 s、实际 600 s"的违规） | 裁决 B1 |
| `loop/tests/test_n6_material_face.py`（新，12 例） | 材料面/派生物/每节点白名单/提交格式/错误信息可定位 | 各条 TDD |
| `loop/tests/test_fix_real_chain.py` | 1 条旧断言从钉旧错误文案改为钉"字段+声明值+实际行号" | 判据不变 |

## 3 材料面瘦身（生产性改动，不是探针作弊）

N6 的 attempt `input/` 由 `dsh_assets.materials_for("N6")` 决定 = **只放派生摘要**；目标用例源件仍由
`model_request._attempt_sources` → `stage_sources` 只读摆进 `input/TESTLIB/`。run 产物**原件一个字节没动**
（`n5_impact.json` 仍 345638 B 在 run 目录里当 Host 侧事实源）。

见 [`raw/material_face_before_after.md`](raw/material_face_before_after.md)：**528122 B → 16757 B（−96.8%）**。
派生摘要 1287 B，记录里写明"派生自 `n5_impact.json`（md5 `dd1306a4…`，345638 B）"，且只投影
`case/file/line/entry_id/segment/offset/rtl_files` + 计数 —— **不含原文 hunk/文档正文，不做任何判定**
（不是第二套判据）。

## 4 离线先行（不烧 token）

| 步 | 命令 | 结果 |
|---|---|---|
| dry-run | `probe_s7a.py --dry-run` | 材料面 16757 B；任务文本 `chars=17562`；`config_timeout_s=300` |
| 纯 Host 链路（S6 真实候选字节回放） | `probe_s7a.py --offline-chain` | `applied`；`md5_after=53f06f1b…` = S6 第 4 次真实候选 md5；`sandbox == real candidate bytes: True` |

第二条同时说明：S6 第 4 次真机的挡路石**只有行号元数据**——把模型真实提交的 `line 218` 按文件更正为
`217` 后，`apply_edits` 结果与模型自己写的候选**逐字节相同**（`EDITS_MISMATCH` 防线因此不会被误触发）。

RED → GREEN 与回归数字见 [`red-green.md`](red-green.md)。

## 5 真机（1 次调用，额度 4）

### 5.1 事实（`raw/s7a_live_RUN-20261029-100500.json`、`raw/attempts.jsonl`）

| 项 | 值 |
|---|---|
| run / attempt | `RUN-20261029-100500` / `N6/1` |
| exit / wall | `completed` / **127.234 s**（`assert config.timeout_s == 300` 在调用前通过；配置即裁决值） |
| usage | `inputTokens=176`、`outputTokens=651`、`cacheReadTokens=71552`、`totalTokens=72379`（**>60k 停手线，已停手报人；人裁决"额度不限制"**） |
| session_id | `session-3f1df466-cab1-4c83-b45e-369d5f37e30a` |
| 提交门 | `validation.ok=True`、`problems=[]`、`submit accepted` |
| 候选通道 | `execution_state=stopped`；模型自主为夹具 5 个目标各写一份候选（15717/25236/17461/21529/20375 B） |
| 压缩事实 | session log 可读（`availability=ok`），`compaction/summary` **0 条**（本轮未压缩，如实计 0 不是未知） |
| 工具面 | 自检回显 `toolNames` **26 项全量**（含 `web_search`/`web_fetch`/`subagent`/`workflow`）⇒ **本片不声称工具面收敛** |
| 双钉 / 身份 | `mode/defaultPreset` 回显均 `workspace-write`；`attemptKey=RUN-20261029-100500/N6/1` |

### 5.2 修的根因（对 S6 四次失败的收口）

| S6 根因 | S7a 处置 | 结果 |
|---|---|---|
| 345 KB `n5_impact.json` 诱导反复解析、300 s 未进写候选 | 材料面瘦身（§3） | **127 s 自然完成**，未再触 300 s |
| `submit_result.payload` 传成 JSON 字符串 ⇒ `BadSubmission` | 任务文本 + 工具描述双重要求"必须是对象"；`BadSubmission` 文案写"期望 object" | 本次**一次通过**提交门 |
| `edits[0].line=218` 与实际 217 不符 ⇒ `apply_edits` 拒 | prompt 规则钉"line 逐字复制片段行首行号"；错误信息可定位 | 本次 5 条 edits 的 line 全部命中 |

### 5.3 `n6_apply` 的两次结果（一次失败 = Host 正确 fail-closed，一次成功 = 重放）

1. **同 run 内**：`failed`，`N6_apply：revision 含非目标用例：['tc_bmc_i2c_04_dfx', …]`。
   原因 = **探针 bug**：live 模式把 `n6_targets` 喂成 1 个目标，而 `n6_author` 自己按夹具构建全部 5 个目标并
   产出 5 份候选 ⇒ Host 判"revision 含非目标用例"是**正确行为**。记 `raw/attempts_corrections.jsonl`，原行不回填。
2. **重放同一次 attempt**：按该次 attempt 的候选与封存输出重跑 `n6_apply`（**不调模型、不新起 attempt、不伪造事实**）
   ⇒ `applied`、`candidate_import.ok=True`、5/5 `source=candidate_import`、
   `md5_after` 与模型真实候选清单逐件相同（`9aa1fe46` / `5966e4db` / `311ad421` / `5096ea09` / `ec3c3242`）。
   见 `raw/s7a_replay_apply_RUN-20261029-100500.json`。

**DS-06 的判据形态**（`agent_candidate_import`，未改）：白名单后缀 + 路径安全 + 缺清单即拒 + 覆盖目标
+ 逐件复算 md5 + 额外文件扫描 + 总量 + 源漂移 + 停止确认。本次 5 件全绿，`drift_checked=true`。
**真机侧"换件"证据**沿用 S6 §4 的补充证据（在真实候选字节上 3/3 拒绝），本片不重做、也不冒充通过。

### 5.4 一处必须照实说的观察（不是本片判据面）

模型本次的 edits **业务上可疑**：它把 `REG_FPGA_DATE` 宏换成字面量并**新增了一个 `set_read` 观测块**，
其中 `SPI_MST(pid).set_read` 的签名在提供的材料里**没有依据**（模型自己在 `notes[3]` 里承认）。
Host 只判结构与契约（`_validate`、`apply_edits`、导入判据），**业务正确性属 N8/N12 与人工闸门**；
本档**不把"Host 校验通过"写成"业务正确"**。该观察登记进 STATUS，供 N8 复核。

## 6 收口门（干净 S7a 树：S7b/S7c 改动 `git stash` 后跑；数字从命令输出复制）

| 门 | 结果 |
|---|---|
| 单测（可写数据根 `<repo>/.dev-ws`） | `3 failed, 1655 passed, 1 warning, 137 errors in 396.97s`；3 failed **全部**是既有 `@pytest.mark.env_layer`（ENV_ROOT 只读）、137 errors = `tests/browser/**` 缺 Chromium |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 13.23s`；**原 ENV_ROOT 零写入** |
| 端到端（drill） | `phase 1–5 + 4b` 全 `rc=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.44s` |
| 浏览器门 | **未跑**：S7a 未改 `loop/web/**` 与 `services/contracts.py` 界面字段（AGENTS §4 只在该类改动时要求） |

差量对账：基线（§116.4）`1643 passed` → S7a 树 `1655 passed`（**+12 = `test_n6_material_face.py`**）；
`failed 3=3`、`errors 137=137`、`warnings 1=1`，**零新增失败**。
原始日志：`loop/.logs/s7a/gate{1..4}-*.log`（gitignored；数字已抄入本表）。

## 7 纪律核对

- **真实调用**：1 次，`attempts.jsonl` 一行（只增不改）；usage 全部拿到（非 unknown）；探针不入库，
  参数/上限/材料 md5/口径已落 raw 可重放。
- **超时真的生效**：`SETTINGS.dsh.timeout_s=300`，探针调用前 `assert config.timeout_s == 300`。
- **写权**：`kb/**` 零改动；`adjudication/agent_experiences.json` 未碰；`doc/evidence/**` 只增。
- **唯一判据（红线 8）**：材料面只有 `dsh_assets.materials_for`；派生物只有 `derive_material`；
  `apply_edits`/`_validate`/导入判据**一处未加**；错误文案改动不新增判据。
- **失败显式**：探针 bug 导致的一次 `n6_apply failed` 如实记录为 Host 正确 fail-closed，
  用 `attempts_corrections.jsonl` 更正，不改原行。
- **独立复核**：**无**（本片实现 + 真机 + 收口同由 Lead 完成；不声称独立验证）。

## 8 复现与索引

- 探针：`raw/probe_s7a.py`（`--dry-run` / `--offline-chain` / 默认 live / `--replay-apply`；
  live 需 `LOOP_LLM_MODE=live`，并 `assert config.timeout_s == 300`）。
- 记账：`raw/attempts.jsonl`（1 行）、`raw/attempts_corrections.jsonl`（探针 bug 更正）。
- 关键事实：`raw/n6_selfcheck_summary.json`、`raw/n6_attempt_record_summary.json`、
  `raw/n6_session_summary.json`、`raw/n6_candidate_listing.txt`、
  `raw/material_face_before_after.md`、`raw/s7a_dry_run.json`、`raw/s7a_offline_chain.json`、
  `raw/s7a_live_RUN-20261029-100500.json`、`raw/s7a_replay_apply_RUN-20261029-100500.json`。
- RED→GREEN：[`red-green.md`](red-green.md)。
- 一次性工作区（gitignored，可重建）：`loop/.logs/s7a/ws/runs/RUN-20261029-100500/`。
