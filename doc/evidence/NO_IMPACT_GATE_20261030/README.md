# 证据：N5 必改=0 的 G1 分流闸门 `G1_no_impact`（2026-10-30）

> 代码仓证据，冻结：本目录只增不改；md5 账本在目录外 `doc/evidence/NO_IMPACT_GATE_20261030.md5`。
> 同一执行者分阶段实施与验证，不声称独立复核。

## 1 范围

人 2026-10-30 要求接入 `LOOP §13-4` 登记的缺口，并五项拍板：
① 新增闸门 id `G1_no_impact`；② 触发用**宽口径**（只看 `must_change_count == 0`）；
③ `full_regression` 跳过 N6–N8、直接 N9 全量跑；④ `no_impact_end` = HALT + finished + 不晋升；
⑤ 只有 `no_impact_end` 强制理由。

契约：[业务 §12](../../spec/CHANGE_IMPACT_LOOP_SPEC.md) · [LOOP §14](../../spec/LOOP_ORCHESTRATION_SPEC.md) ·
[WEB_UI §16](../../spec/WEB_UI_SPEC.md)；计划：[zero-must-change-gate](../../plans/2026-10-30-zero-must-change-gate.md)；
冻结目录变更留证：[`../KB_GATE_NO_IMPACT_20261030/`](../KB_GATE_NO_IMPACT_20261030/README.md)。

## 2 实现要点

- N5 完成后按 `must_change_count == 0` 发 `N5_ZERO_MUST_CHANGE` / `N5_HAS_MUST_CHANGE`（只发一个）；
- 新节点 `N5b` + 闸门 `G1_no_impact`（`BRANCH_EVENTS`：`no_impact_end→G1_NO_IMPACT_END`（→`halt`）、
  `full_regression→G1_NO_IMPACT_FULL_REGRESSION`（→`n9_submit`））；
- 纵深防御：`_assert_no_impact_gate_allowed` 在进/签该门时复核 `must_change_count==0`（防绕过 resume 跳过修订）；
- `full_regression` 的真实目标集 = `kb/index/cases.json` 全部用例，逐例校验文件 md5 == 索引 md5，
  `n9_job.target_set="baseline_frozen_full"`（与 `n6_applied` 可区分，禁止静默回退）；
- 未出现的分流门不投影（`kb_lib.gate_applicable` 唯一判据），也不拖住 `all_signed`。

## 3 验收（数字从命令输出复制）

| 项 | 命令 | 结果 |
|---|---|---|
| 分支/守卫/目标集/拓扑单测 | `cd loop && bash spikes/run_software_checks.sh tests/test_no_impact_gate.py -q` | **`15 passed`**（`branch-tests.log`） |
| 软件层全量 | `cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser` | **`2054 passed, 3 deselected, 1 warning in 257.34s`**，`rc=0`（`software-gate.log`） |
| 浏览器（补充门） | `cd loop && PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… .venv/bin/python -m pytest -q tests/browser` | **`183 passed in 186.20s`**，`rc=0`（含新增 `tests/browser/test_gate_no_impact.py` 3 条） |
| 端到端 | `cd loop && LOOP_PORT=8197 LOOP_WORKSPACE=… bash spikes/accept_v1_run.sh` | 六相全 `rc=0` + **`=> ALL PASS`**（`e2e-accept.log`；A42 断言已按 LOOP §14 的分流门适用性更新） |
| 环境层 + kb 自测 | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests` | 见 `../KB_GATE_NO_IMPACT_20261030/kb-selftests.log` |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=3303 … missing=0`，`rc=0`（`doc-gate.log`；两本 md5 账本生成后复跑） |

## 4 drill 分支实测覆盖（`branch-tests.log` 内）

1. `test_drill_zero_must_change_ends_at_halt`：零必改 ⇒ 停 `G1_no_impact`（材料含两项选项、`gate_node=N5b`）⇒
   签 `no_impact_end` ⇒ run 收敛 `finished` 且节点历史含 `HALT`、**不含** `N6_author`/`N9_submit`；
2. `test_drill_full_regression_skips_revision_and_runs_n9`：签 `full_regression` ⇒ 节点历史**不含** `N6_author`、
   含 `N9_submit`/`N9`（drill 作业完成→恢复有固有竞态，故按**事件流**判定，不依赖瞬时 interrupt）；
3. 反向守卫：`must_change_count>0` 或状态缺失 ⇒ `_assert_no_impact_gate_allowed` 拒绝（不得借"零必改"跳过修订）；
4. 拓扑自检：`main_flow.BRANCH_DRIFT == {}`（`BRANCH_EVENTS` 与权威枚举逐值一致）。

## 5 边界（不声称）

- **real 全量回归未跑**：≈19 min/用例 × 全量，成本超本轮；`full_regression` 的 real 目标集构造与 fail-closed
  由单测证明（索引缺失/为空/md5 不符均显式失败），STATUS 如实登记。
- drill 的作业完成→恢复存在既有竞态（`resume_dispatch_failed … changed phase`），与本分支无关；
  测试按事件流断言，不把该竞态写成"通过"。
