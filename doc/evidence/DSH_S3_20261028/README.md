# DSH S3 实测与证据（2026-10-28）：WM / IL / EXP 三片（C1 机制）

> 归档件，**只增不改**；原始产物在本目录 `raw/`，冻结方式见 §6。
> 目的：为 [S3 计划](../../plans/2026-10-28-s3-wm-il-exp.md)、[REV-13](../../spec/SPEC-REV-13-20261026.md) §6/§7/§8 与
> [REV-14](../../spec/SPEC-REV-14-20261028.md) §5 A4/A5/A6 的 WM-01～05、IL-01～04、EXP-01～03 提供实测。
> **本目录不是四道门的唯一数字源**：四道门命令与数字只在 [STATUS §112](../../STATUS.md) 维护；本目录保存**原始输出**。
> 分层：C1（机制/受控 provider）≠ C2（真实 DSH/模型）≠ E（内网业务）。**本片全部为 C1**，未跑真实模型。

## 1 结论（三态，照实）

| 项 | 结论 | 决定性证据 |
|---|---|---|
| **WM 可重建工作记忆（REV-13 §6）** | **过（C1）**：唯一构造者 `host/agent_working_memory.py`；五类条目、`input_ref` JSON Pointer（禁自引用/循环/外部未读）、确定性 `snapshot_sha256`、封存来源核验（半件/篡改/跨 run 显式失败）、旧格式不标 verified、强制材料超预算调用前失败 | `loop/tests/test_agent_working_memory.py`（39 用例，WM-01～05）；本目录 `raw/unit.log` |
| **IL 指令生命周期（REV-13 §7）** | **过（C1）**：run 作用域事件 `agent_controls/run/instruction-<seq>.json`（封存、只增、1..N 连续）、CAS、`request_id` 幂等（含 target）、supersede 单事件原子、attempt/node_rework/run 作用域与到期、单写者锁、`accepted/applied/effective` 分离、结果后按本节点指纹复核（迟到结果丢弃） | `loop/tests/test_agent_instruction_lifecycle.py`（68 用例，IL-01～04）；同上 |
| **EXP 经验分层（REV-13 §8）** | **过（C1）**：v1 逐值行为保持；v2 两阶段（源完整性 → 当前事实适用性）、两类适用性（exact_fact 必须非空 typed 依赖 / general_advice 必须有已批准环境策略或契约范围）、审计指纹与适用条件分离、批次超限整批拒用、不自动晋升；离线迁移/校验只读 + 草稿 | `loop/tests/test_agent_experience_applicability.py`（84 用例，EXP-01～03）；本目录 `raw/migrate-*.json` |
| **前置行为不回归（REG-01）** | **过（C1）**：`scope_for` 未改、v1 选择输出 23 场景差分 0 difference、H2b `review_context_sha256` 旧值不变、旧 `/control` 控制路径代码零改动（追加段仅 2 B 分隔空行） | 计划 §6.4-46 的口径说明；`git diff 06519d7..HEAD -- loop/host/agent_control.py` 的删除行仅模块 docstring |
| **四道门（终版树）** | 单测 `3 failed(env_layer)/1394 passed/113 errors(browser 缺件)`；kb 自测 `PASS=10/9/28 FAIL=0` + env_layer `3 passed` + 原 ENV_ROOT 零写入；e2e `phase1–5 rc=0 / ALL PASS`；文档门 `65 passed` | `raw/unit.log`、`raw/kb-layer.log`、`raw/e2e.log`、`raw/doc.log`；数字同 [STATUS §112](../../STATUS.md) |
| **准入未放开** | **过**：`dsh` 仍 `BackendUnavailable`、`SETTINGS.dsh.enabled=false`；本片未改 `agent_backends` | `tests/test_agent_backends.py`、`test_dsh_backend.py` |

## 2 复现命令（数字从输出复制，别抄本页）

```bash
# 单测（终版树；数据根必须用绝对路径 <repo>/.dev-ws）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws \
  LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# kb 自测 + env layer（派生 ENV_ROOT 副本，原 ENV_ROOT 零写入）
cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests

# 端到端（drill）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws \
  LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# 文档门（先清理 .dev-ws / .env-copy）
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_doc_links.py
```

迁移工具演示（`raw/migrate-*`）：在临时工作区 `workspace/adjudication/agent_experiences.json` 写一条 v1 已批准条目
（源 `runs/historical/note.md`），然后

```bash
cd loop
.venv/bin/python -m host.experience_migrate --catalog <ws>/adjudication/agent_experiences.json --validate
.venv/bin/python -m host.experience_migrate --catalog <ws>/adjudication/agent_experiences.json \
  --out <ws>/../drafts/agent_experiences.v2.json
.venv/bin/python -m host.experience_migrate --catalog <ws>/adjudication/agent_experiences.json \
  --out <ws>/adjudication/agent_experiences.json          # 拒绝覆盖输入（rc=1）
.venv/bin/python -m host.experience_migrate --catalog <ws>/adjudication/agent_experiences.json \
  --out <ws>/adjudication/draft/x.json                    # 拒绝写 adjudication/（rc=1）
```

`raw/migrate-demo-md5.txt` 记录人工目录 md5 前后相同（`d344222f…`）、`adjudication/` 下未生成 `draft/`。

## 3 独立复核（未参与实现，只报告不改）

- 静态 1×P1（IL 幂等指纹漏 `target_instruction_id`，同 `request_id`+同 revision 换目标会返回旧回执）+
  13×P2；**P1 与 6×P2 已修**，其余登记缺口（计划 §6.4）。
- 动态：16/16 反向抽检（每条必测至少 1 条：改坏实现 ⇒ 用例变红 ⇒ 还原后 sha256 与 `git diff` 均一致），
  独立复跑全量单测门 `3 failed(env_layer)/1394 passed/113 errors` 与文档门 `65 passed`。
- 复核者**未**改被测文件、未提交、未写 STATUS；结论："可按 C1 声称已实现/断言可证伪"，
  但不能声称"四道门全通过（kb/e2e 由 Lead 跑）/TDD 时序有独立证据/C2/E/IL+EXP 全量语义完整"。
- 复核原文摘要见 [STATUS §112.5](../../STATUS.md) 与 [计划 §6.4](../../plans/2026-10-28-s3-wm-il-exp.md)。

## 4 与 STATUS 的关系

本目录只存**原始输出**与复现配方；通过/失败的正式记录与"未做/不声称"清单以 [STATUS §112](../../STATUS.md) 为准。
`env_layer 3 failed` 与 `tests/browser 113 errors` 是**本机环境缺件**（ENV_ROOT 只读、无 Chromium），
照实记录，**不算通过**，也不并入四道门。

## 5 不声称

- 不声称 C2：未接真实 DSH/模型（`select()` 仍 `BackendUnavailable`、`enabled=false`）；未跑真实工具/长会话/压缩边界。
- 不声称 E：无内网工程验收；drill 只证拓扑与机制。
- 不声称已完成：run 终态到期（§6.4-39）、`context_manifest_ref`（§6.4-40）、§7.3 主动停止（§6.4-43）、
  运行期开关（§6-1）、UI/S4 投影（§6-20）、DSH 冷材料补读（§6-6）。
- 不声称经验选择"语义正确"：v2 判据是确定性 typed 规则，无模型/关键词相似度；经验永不签闸门/改计数。

## 6 冻结方式

`raw/` 与 `README.md` 一律 `chmod 444`；目录项不参与 md5，md5 清单记在**本目录之外**：
`doc/evidence/DSH_S3_20261028.md5`（`cd doc/evidence/DSH_S3_20261028 && find . -type f | sort | xargs md5sum > ../DSH_S3_20261028.md5`），
校验：`cd doc/evidence/DSH_S3_20261028 && md5sum -c ../DSH_S3_20261028.md5`。冻结后只增不改。
