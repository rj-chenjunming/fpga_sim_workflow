# 修复轮验收证据（2026-10-19）

> **性质**：本轮修复（审计阻断级 22 条 + 实测 F-01/F-02）的**门禁证据快照**，只增不改。
> **数字权威**：本文件只复制命令输出；数字的唯一权威仍是 [`doc/STATUS.md`](../STATUS.md)。
> **运行环境**：ENV_ROOT=`/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES`，
> WORKSPACE=ENV_ROOT/kb，Python 3.11.7，Agently 4.1.4.8，`LOOP_LLM_MODE=standin`。
> **基线**：修复前提交 `b4a2443`（tag `pre-fix-20261019`）。

---

## 1 门禁总表

| 门 | 命令 | 结果 |
|---|---|---|
| 单测 | `cd loop && flock /tmp/cic_loop_pytest.lock env LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | **197 passed, 1 warning in 72.34s**（197 collected） |
| kb 自测（5 支） | 见 §2 | **10/10、9/9、7/7、16/16、13/13** 全 PASS |
| 端到端 | `cd loop && LOOP_PORT=8098 bash spikes/accept_v1_run.sh` | **rc=0；117/117 断言**，相计数 50/27/18/8/8/6 |
| 文档链接 | `python3 doc/audit/check_doc_links.py` | **checked=772 / missing=0**（skipped=9323, historical=834） |

---

## 2 kb 自测输出（逐字）

```text
$ loop/.venv/bin/python kb/tools/_selftest_gate_schema.py
汇总：PASS=10 FAIL=0

$ loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py
汇总：PASS=9 FAIL=0

$ loop/.venv/bin/python kb/tools/_selftest_n1_snapshot.py
汇总：PASS=7 FAIL=0

$ loop/.venv/bin/python kb/tools/_selftest_case_state.py
汇总：PASS=16 FAIL=0

$ loop/.venv/bin/python kb/tools/_selftest_n10_pending.py
汇总：PASS=13 FAIL=0
```

---

## 3 端到端输出（驱动汇总逐字）

```text
$ cd loop && LOOP_PORT=8098 bash spikes/accept_v1_run.sh
...
================= 驱动汇总 =================
  phase 1    rc=0     # PASS=50 FAIL=0
  phase 2    rc=0     # PASS=27 FAIL=0
  phase 3    rc=0     # PASS=18 FAIL=0
  phase 4    rc=0     # PASS=8  FAIL=0
  phase 4b   rc=0     # PASS=8  FAIL=0
  phase 5    rc=0     # PASS=6  FAIL=0
  => ALL PASS
```

关键事实（取自本次 phase 输出）：

- 4 代服务进程、3 次真重启；重启后重附着到**同一个**作业（B3/D2），跨重启单槽未丢（D3）。
- 闸门决策先判后签：拒绝矩阵（I6 403 / 自造枚举 400 / I4 403 / 缺 actor 400）**未消耗中断**，
  账本仍是白纸（A23–A25/A45）；签署后权威态 `human_signed=true` 且锚一致（A46–A48）。
- 两套口径并列：口径一 **1687**、口径二 `UVM_ERROR=0`，`both_zero=false`、`verdict.passed=false`（B7–B12）。
- 冲突未清零（72/72 `blocks_release`）⇒ `full_now`/`subset_only` 提交前被拒 403（B23/B24），
  `defer` 放行且终点 HALT、**未走 N16**（B27/C7b）；N16 dry-run 对 `kb/baselines` 零副作用（C9）。
- 长任务停放为 `waiting_job`（I18），单槽持有者带作业身份（v2 lease，D0–D4）；
  取消后 run 为 `failed` 且单槽释放（D6/D7）；死任务判 `failed` 并释放单槽（E1/E2）。

> 端到端原始输出在 `loop/.logs/accept/`（本地，不入库）。

---

## 4 本轮修复的验收覆盖（按审计阻断项）

| 审计项 | 修复落点（实现） | 回归测试（文件::用例） |
|---|---|---|
| #1 real N1 断（缺 `--parent`） | `loop/workflows/chunks/host_steps.py`（stage + staged 完整镜像） | `tests/test_fix_real_chain.py` |
| #3/#6 N6 不产沙箱/冻结 md5 | `host_steps.n6_apply` + `model_steps.n6_author` | 同上 |
| #7 N7 假编译 | `host_steps.n7_compile`（`run_guarded.sh --mode compile-only`） | 同上 |
| #8 N9 硬编码单例/静默回落 | `long_jobs.n9_submit/n9_park`（目标集 + 单作业 + fail closed） | 同上 |
| #9 N15 无真实回归 | `long_jobs.n15_select/n15_run`（最终态，非 provisional） | 同上 |
| #1/#15 N8 默认 pass / N11 无守护 | `model_steps.n8_check` / `n11_review`（Host 身份 join） | 同上 |
| #18 N3/N10/N12 不落盘 | `model_steps` 落 `n3_digest.md`/`reconcile.md`/`n12_report.md` | 同上 |
| #2 单槽队列无唤醒 | `host/admission.py` resumer + `main_flow._on_slot_handoff` | `tests/test_fix_lifecycle.py` |
| #4 闸门先签后恢复楔死 | `main_flow.decide`（先判后签 + 失败显式收敛） | 同上 |
| #5 槽按进程判活 | `admission` v2 作业级 lease + `main_flow._restore_slot_lease` | 同上 |
| #17 恢复失败只写报告 | `main_flow.async_restore_all`（fail → `_fail_run`） | 同上 |
| #19 conflicts 永久缓存 | `services/contracts.py` mtime+size 新鲜度 | 同上 |
| #20 单槽泄漏 | `main_flow._fail_run` 幂等释放 + long_jobs try/finally | 同上 |
| #10 闸门材料缺输入/I1 | `contracts.gate_material` + `gates.precheck_decision` | 同上 |
| #11 I2 无写入者 | `model_steps._ensure_case_state` + case_state 工具 | `tests/test_fix_real_chain.py` |
| #12 I3 印记不入 verdict | `host/evidence.py` `_verdict` 三向一致 | `tests/test_evidence.py` / `tests/test_fix_kbtools.py` |
| #13 I4 可被 G3 分流绕过 | `kb/tools/n16_promote.py` I4 无条件 | `tests/test_fix_kbtools.py` |
| #14 I8 无真实晋升 | `services/promote.py` + `POST /api/runs/{id}/promote` + `n16_promote --promote` | `tests/test_fix_integration.py` |
| #21 N16 身份硬编码 | `n16_promote.precheck_identity`（与 G3 逐字一致） | `tests/test_fix_kbtools.py` |
| #22 I7 边界不一致 | [case_state.py](../../kb/tools/case_state.py) 的 `check_ledger` 唯一判据，统一 `>= limit` | `tests/test_fix_kbtools.py` / `test_fix_lifecycle.py` |
| F-01 `n1_snapshot.py` NameError | [n1_snapshot.py](../../kb/tools/n1_snapshot.py)（`K.kb_path`） | [_selftest_n1_snapshot.py](../../kb/tools/_selftest_n1_snapshot.py) |
| F-02 `n2_diff.py` 主口径错位 | `kb/tools/n2_diff.py`（`K.data_path`） | `tests/test_fix_kbtools.py` |

---

## 5 复跑纪律（必须遵守）

1. pytest 与端到端**不得并发**：二者共用 `loop/state` 的单槽锁/作业记录；并发会让端到端的
   「单槽由本作业持有」被测试伪造的锁污染（本轮实测过一次假失败，已由“先 pytest 后 e2e”消除）。
2. pytest 一律 `flock /tmp/cic_loop_pytest.lock` 串行。
3. 端到端会清理 `loop/state` 与 `kb/runs/RUN-*/.loop_drill`；不要在跑的过程中做别的写操作。
