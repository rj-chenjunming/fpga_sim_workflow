# CASE-OVERRIDE 证据档 · 用例判据人签覆写（2026-11-02）

> 契约：[SPEC-REV-20](../spec/SPEC-REV-20-20261102.md)；计划：[2026-11-02-case-override](../plans/2026-11-02-case-override.md)；
> 本轮实测汇总：[STATUS §148](../STATUS.md)。
> 归档纪律：本目录**只增不改**；目录内文件的 md5 记在**目录之外**
> （[`CASE_OVERRIDE_20261102.md5`](../CASE_OVERRIDE_20261102.md5)，红线 10）。
> 目录内 `raw/` 原样保存命令输出，未做任何"整理后"改写。

## 1 变更性质

`kb/tools/case_state.py` 与 `kb/schema/case_states.schema.json` 属**冻结目录**。本次按
[AGENTS.md §3](../../AGENTS.md)「改语义需单独变更并留证」执行（先例：`G1_no_impact`，
[KB_GATE_NO_IMPACT_20261030](../KB_GATE_NO_IMPACT_20261030/README.md)）。冻结目录本次共动 **4 个文件**：

| 文件 | 本轮改动 | 当前 md5 |
|---|---|---|
| `kb/tools/case_state.py` | 新增 `override` 子命令（只增记录、批量全有或全无、写盘前拒绝矩阵、`--verify` 锚复核）；`check_ledger` info 增 `waived`（展示用，判据未变） | `6a43334647d630a40ec7b883561b0f8f` |
| `kb/schema/case_states.schema.json` | 条目新增 `overrides`（`action=[pass,revoke]`、`actor_kind=[human]`、`record_sha256` pattern、`machine` 快照） | `35f9fe952891b66f39148d32025dee63` |
| `kb/tools/_selftest_case_state.py` | 断言 16 → 55 条（拒绝矩阵、批量、撤销边界、锚/source_md5 复算、schema） | `da0c47b0a9332af1e652b70c855e9757` |
| `kb/README.md` | 子命令清单补 `override`（仅 1 行） | `81154bb2c5192ec9dffa30a2207f837b` |

**没有改的**：既有 `init/set/show/check` 行为与 rc 语义、四态字面量与含义、I2/I3/I7 判据、
`GATE_DECISIONS`、口径解析器（`host/evidence.py`）。机器判据仍唯一、不可改写（规格 O-1）。

## 2 本轮落点（哪些文件为本次新增/修改）

- 新增：`loop/services/case_override.py`、`loop/tests/test_case_override_api.py`、
  `loop/tests/test_case_states_waivers.py`、`loop/tests/test_n10_cases.py`、
  `loop/tests/browser/test_case_override.py`；`doc/spec/SPEC-REV-20-20261102.md`、
  `doc/plans/2026-11-02-case-override.md`、本目录。
- 修改（本轮 hunk 见 [`raw/s5-our-hunks.diff`](raw/s5-our-hunks.diff)）：`kb/**` 4 件（上表）、
  `loop/workflows/chunks/{n10_semantics,model_steps,host_steps}.py`、`loop/host/progress.py`、
  `loop/services/{api,contracts}.py`、`loop/web/{app.js,index.html,node-detail.js}`、
  `doc/spec/{CHANGE_IMPACT_LOOP_SPEC,LOOP_ORCHESTRATION_SPEC,WEB_UI_SPEC}.md`、
  `doc/README.md`。
- **会话前工作树本就不干净**（43 个文件有未提交改动，mtime 为 10-29/10-30）。因此
  `git diff` 的整文件 diff **不等于**本轮改动；上表与 `raw/s5-our-hunks.diff`（按
  `case_override|n10_cases|overrides|人签覆写|revoke|SPEC-REV-20` 等关键字抽取的 hunk）
  才是本轮改动范围。

## 3 四道门 + 浏览器门（数字从命令输出复制）

| 门 | 命令 | 结果 | 原始输出 |
|---|---|---|---|
| 单测（软件层，可写影子数据根） | `bash spikes/run_software_checks.sh -q --ignore=tests/browser` | **`2104 passed, 3 deselected, 1 warning in 273.16s`，rc=0** | [`raw/s5/01b-software-clean-and-kb.log`](raw/s5/01b-software-clean-and-kb.log) |
| kb 自测 | `bash spikes/run_env_layer_checks.sh --with-kb-selftests` | **`PASS=10 / PASS=9 / PASS=28`、`FAIL=0`；`3 passed, 24 deselected`；原 ENV_ROOT 零写入** | 同上 |
| 端到端 | `LOOP_WORKSPACE=<repo>/.dev-ws LOOP_PORT=8098 bash spikes/accept_v1_run.sh` | **phase 1/2/3/4/4b/5 全 rc=0 ⇒ ALL PASS** | [`raw/s5/04b-e2e-8098.log`](raw/s5/04b-e2e-8098.log)、[`raw/e2e/`](raw/e2e/) |
| 文档门 | `python3 doc/audit/check_doc_links.py` | 见 STATUS §148（无新增断链；只余既有 KNOWN-MISSING/ENV-MISSING） | STATUS §148 |
| 浏览器门（界面有改动 ⇒ 必跑） | `PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser` | **`199 passed in 200.18s`，rc=0** | [`raw/s5/05-browser-gate.log`](raw/s5/05-browser-gate.log) |

附加（S1 冻结目录专项，kb owner 实测）：`python3 kb/tools/_selftest_case_state.py` ⇒
**`汇总：PASS=55 FAIL=0`**（连跑两次一致）；红→绿证据见 [`raw/s1/`](raw/s1/)。

## 4 各片证据索引

| 片 | 证据 |
|---|---|
| S1 kb 冻结目录 | [`raw/s1/`](raw/s1/)（命令索引、红/绿、17 条 CLI 冒烟、受影响单测 423 passed）、[`raw/s1-kb-frozen-change.diff`](raw/s1-kb-frozen-change.diff) |
| S2 N10 产物 | [`raw/s2/`](raw/s2/)（先红 11 failed → 绿 11 passed；`s2-diff.log` 含 `model_steps.py` 两处接线行号；受影响回归 44 passed） |
| S3 服务层/API/投影 | [`raw/s3/`](raw/s3/)（先红 → 39 passed；受影响回归 276 passed；200/400/403/409 真实响应样例 `api-samples.log`；`s3-diff.log`） |
| S4 界面 | [`raw/s4/`](raw/s4/)（新浏览器用例先红 13 failed → 绿 16 passed；契约测试红证据 `01b`；web 源码守卫批） |
| S5 收口门 | [`raw/s5/`](raw/s5/)（见上表） |

## 5 边界（不声称的东西）

1. **21 h 真实全跑未跑**：只经单测 + drill 回放 + 既有真实轮只读快照验证；真实回归成本不折算。
2. e2e 使用 `LOOP_PORT=8098`：8099 被一个**跨沙箱残留监听**占用（`ss` 可见、`ps` 不可见，
   无法安全清理），换端口不等于降级（驱动器自带就绪探测与重启断言全过）。
3. 环境层 3 条用例只在**派生 ENV_ROOT 副本**上执行（红线 11：原 ENV_ROOT 零写入，脚本 `find -newer` 自证）。
4. 本目录是**材料**，不是闸门权威：`gates.json` + `gates.sha256` 仍是闸门权威；
   覆写记录在 `case_states.json` 的 `overrides[]`，其 `record_sha256` 可离线复算。
5. 未做：I4 冲突清零（仍归 `adjudicate_conflicts.py`）、报告正文重写、期望值数据修正
   （见规格 §10/§12）。
