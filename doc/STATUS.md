# 项目状态（唯一数字源）

> **本文件是数字的唯一权威**。其它文档引用这里，不各自抄一份。
> **本次采样**：2026-10-19T15:29+0800；采样命令与输出见各节（数字一律复制，不手算）。
> **不声称合规**：审计发现但未修复的阻断项在 §5 保持可见。

---

## 1 版本与运行环境

| 项 | 值 | 来源 |
|---|---|---|
| 本仓 HEAD（采样时） | `dc7c69e`；整理后 HEAD 见 `git log --oneline -5`（本次共 4 个提交） | `git rev-parse --short HEAD` |
| 提交数（采样时） | 13 | `git rev-list --count HEAD` |
| Python | 3.11.7 | `loop/.venv/bin/python -V` |
| Agently | 4.1.4.8 | `pip show agently` |
| 环境仓（ENV_ROOT） | `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` | `environments.json` |
| 数据根（WORKSPACE_ROOT） | `ENV_ROOT/kb`（1.1G） | `du -sh`；决定见 `doc/spec/ENV_PLUGIN_SPEC.md` §7 |

## 2 质量门（本次整理后实测）

| 门 | 命令 | 结果 | 说明 |
|---|---|---|---|
| 单测收集 | `cd loop && .venv/bin/python -m pytest --collect-only -q` | **94 tests collected** | 含 UI 配置面/投影/契约/冒烟 |
| 单测执行 | `LOOP_WORKSPACE=<可写副本> .venv/bin/python -m pytest -q` | **91 passed / 3 failed** | 3 条失败均为环境/布局限制，见 §3 |
| kb 自测 · gate schema | `LOOP_WORKSPACE=<可写副本> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **10/10** | 需要可写数据根；默认数据根在只读沙箱内会失败 |
| kb 自测 · n5 可达性 | `loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **9/9** | 只读，无需写数据根 |
| 端到端终验 | `cd loop && bash spikes/accept_v1_run.sh` | **未复跑**（历史记录 117 断言） | 需写 `ENV_ROOT/SIMLIB_RUN` 与 `uvs.setup`；本会话沙箱对 ENV_ROOT 只读 |
| Web 冒烟 | `.venv/bin/python -m pytest tests/test_web_smoke.py -q` | **3/3** | 页面/静态资源/零外链/legacy 可用 |
| 文档链接扫描 | `python3 doc/audit/check_doc_links.py` | **checked=713 / missing=0** | 三根解析 + 行号后缀剥离；历史件（evidence/history）计入 historical=834 |

### 终验历史记录（不是本次实测）

`doc/evidence/ACCEPTANCE_V1.md`：**117/117** 断言，4 代服务进程、3 次真重启；相计数 **50/27/18/8/8/6**。
原始输出在 `loop/.logs/accept/`（本地、不入库）。

## 3 已知环境限制（本次整理采样时）

1. **ENV_ROOT 在本会话只读**（DSH 文件沙箱 workspace-write）：依赖写 `ENV_ROOT/SIMLIB_RUN`、`uvs.setup` 的测试无法复跑。
2. **`tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run`** 假设 `WORKSPACE_ROOT` 位于 `ENV_ROOT` 之内（`path.relative_to(P.REPO_ROOT)`）；当工作区指向外部目录时该断言不成立 ⇒ 已登记为布局耦合缺陷（审计报告）。
3. **`tests/test_archive_e2.py`** 需要可写 `ENV_ROOT`（`run_guarded.sh` 落 `SIMLIB_RUN`）。
4. 上述 3 条即 §2 的 3 failed；**不是业务代码回归**。
5. **已知 flaky**：`test_crash_recovery_delivers_dead_job_as_dead_not_done` 在整套执行中偶发失败、单测通过（审计 F-V1-06-FLAKY），与本轮 UI 改动无关。

## 4 数据与归档

| 项 | 状态 |
|---|---|
| `ENV_ROOT/kb/{index,conflicts,baselines,runs,adjudication}` | 存在；`RUN-20261015-120626` 为冻结见证（只读） |
| `loop/state/` | 可删的运行时状态 |
| `doc/evidence/` | 验收报告 + 演练证据（内容冻结，只增不改） |

## 5 审计结论（2026-10-19，只登记不修复）

- 报告：`doc/audit/AUDIT-20261019-spec-conformance.md`；附录：`doc/audit/parts/`。
- 三路审计原始发现：规格↔实现 **49** 条、Agently 运行时 **44** 条、文档结构 **77** 条（含本轮已执行项）。
- **阻断级**（去重后 22 条）：real 链路 N1/N6/N7/N9/N15 断裂；N8 模型失败默认 `pass`；单槽队列无唤醒；闸门「先签后恢复」失败楔死；槽按进程而非作业判活；N6 不产出沙箱导致 N9 测未修订用例。
- **结论**：本轮只做结构与文档整理；上述代码缺陷**未修复**，不得据此声称系统合规。

## 5.1 本次整理做了什么（2026-10-19）

| 类别 | 变更 |
|---|---|
| 结构归位 | `CHECKPOINT-*` → `doc/history/`；`doc/agents/_demo/`（32 件）→ `doc/evidence/demo/`；`loop/ACCEPTANCE_V1.md` → `doc/evidence/`；34 个 rename 内容逐字节一致 |
| 新增入口 | 根 `README.md`、根 `AGENTS.md`（流程/写权/红线/DoD）、`doc/README.md`、`doc/agents/README.md`、`doc/evidence/README.md`、`doc/history/README.md`、`doc/STATUS.md`（本文件） |
| 迁移记录 | `doc/evidence/demo/MIGRATION.md`（old→new + md5 未变声明）；`CHECKPOINT` 顶部「已过期」横幅 |
| 规格纠偏 | 三份 spec 的状态/完成度/数字/三根路径；`kb/README.md` 按三根重写；`workspaces/README.md` 修 `yaml→json`；`loop/README.md` 统一 117/70/9 |
| 审计落档 | `doc/audit/`（总报告 + 3 份附录 + `check_doc_links.py`） |
| 清理 | `.gitignore` 删两条本仓不存在的规则、`snap.json` 移出版本控制、清 `kb/tools/__pycache__` |
| **UI v1** | 两区运营台：`index.html`+`app.js`+`app.css`；旧界面 `legacy.html`；新增 `/api/baselines`、`/api/env/check`、`/api/fs/dirs`、`run_view.agents/stage_map/project`（见 `doc/spec/WEB_UI_SPEC.md`） |

## 6 待人工拍板（沿用，未变）

| # | 事项 | 材料 |
|---|---|---|
| 1 | I3 双口径分歧（口径一 1687 ≠ 0） | `ENV_ROOT/kb/adjudication/I3_dual_count_dispute.md` |
| 2 | 72 条冲突清零 | `ENV_ROOT/kb/adjudication/C_conflicts_triage.md` |
| 3 | 是否授权改 `TB/`（仅 I3 选项 b 需要） | 环境 `doc/AGENTS.md` 红线 1 |
| 4 | 真机全跑时间窗 | 单用例 ≈19 min，修订后可达 22.8 h |
