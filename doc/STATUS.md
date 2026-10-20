# 项目状态（唯一数字源）

> **本文件是数字的唯一权威**。其它文档引用这里，不各自抄一份。
> **本次采样**：2026-10-19T18:02+0800（修复轮终验，四道门全绿）；采样命令与输出见各节（数字一律复制，不手算）。
> **不声称合规**：审计发现但未修复的阻断项在 §5 保持可见。

---

## 1 版本与运行环境

| 项 | 值 | 来源 |
|---|---|---|
| 本仓 HEAD（采样时） | `b4a2443`（修复前基线，tag `pre-fix-20261019`）；修复提交见 `git log --oneline -3` | `git rev-parse --short HEAD` |
| 提交数（采样时） | 14（含基线提交） | `git rev-list --count HEAD` |
| Python | 3.11.7 | `loop/.venv/bin/python -V` |
| Agently | 4.1.4.8 | `pip show agently` |
| 环境仓（ENV_ROOT） | `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` | `environments.json` |
| 数据根（WORKSPACE_ROOT） | `ENV_ROOT/kb`（1.1G） | `du -sh`；决定见 `doc/spec/ENV_PLUGIN_SPEC.md` §7 |

## 2 质量门（修复后终验，2026-10-19）

| 门 | 命令 | 结果 | 说明 |
|---|---|---|---|
| 单测收集 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest --collect-only -q` | **200 tests collected** | 含修复回归（real 链路 / 生命周期 / kb 工具 / 晋升 API） |
| 单测执行 | `cd loop && flock /tmp/cic_loop_pytest.lock env LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | **200 passed, 0 failed**（72.21s） | 基线红 `test_view_projects_authority_not_just_events` 已修（身份复用 + 事件流残留） |
| kb 自测 · gate schema | `loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **10/10** | 需可写数据根 |
| kb 自测 · n5 可达性 | `loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **9/9** | 只读 |
| kb 自测 · n1 快照（F-01） | `loop/.venv/bin/python kb/tools/_selftest_n1_snapshot.py` | **7/7** | 新增；build/stage 不再 NameError |
| kb 自测 · case_state | `loop/.venv/bin/python kb/tools/_selftest_case_state.py` | **16/16** | 新增；含 check/I7 边界 |
| kb 自测 · n10 待裁决 | `loop/.venv/bin/python kb/tools/_selftest_n10_pending.py` | **13/13** | 新增；D1–D20 零改动 |
| 端到端终验 | `cd loop && LOOP_PORT=8098 bash spikes/accept_v1_run.sh` | **rc=0；117/117 断言**（相计数 50/27/18/8/8/6） | 4 代服务进程、3 次真重启；输出在 `loop/.logs/accept/`（本地、不入库） |
| 文档链接扫描 | `python3 doc/audit/check_doc_links.py` | **checked=777 / missing=0**（skipped=9424, historical=834） | 三根解析 + 行号后缀剥离 |

> **real 模式说明**：2026-10-20 已在**真实环境副本**（SCN_RTL_0D04）用 real 模式 + live LLM + 真实编译
> 跑通 **N0→N8**（N2/N5 与预登记答案一致；N7 5/5 编译 rc=0；N8 live pass）；N9 真实全跑按范围在提交后取消。
> 第二轮更长的 real 回归（N9 全跑 ≈50 min/用例）仍未执行；收紧 N6 输入（`api_semantics` + `rtl_effect`）后
> N6 五条修订已与预登记答案键一致（run8）。证据见 [`doc/evidence/REAL_RUN_SCN_RTL_0D04_20261020.md`](evidence/REAL_RUN_SCN_RTL_0D04_20261020.md)。

### 终验历史记录（不是本次实测）

`doc/evidence/ACCEPTANCE_V1.md`：**117/117** 断言（同一脚本、同一断言集）。本轮修复后复跑仍 117/117。

## 3 已知环境限制

1. **端到端必须独占 `loop/state`**：`accept_v1_run.sh` 与并发 pytest 共用 `loop/state/slot.lock` / 作业记录；
   并发会让 phase4 的「单槽被本作业持有」被其它测试伪造的锁污染。门禁顺序：先 pytest，再端到端。
2. **`tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run`** 仍假设
   `WORKSPACE_ROOT` 位于 `ENV_ROOT` 之内；工作区指向外部目录时该断言不成立（布局耦合，非本轮范围）。
3. **real 模式无 live provider 时**：N3/N10/N12 按 fail closed 处理（不再读夹具冒充）；真机端到端需配置模型提供方。
4. `n15_run` 在 drill 下是显式 no-op（不假装回归）；真实回归须 real 模式 + 单槽串行作业。

## 4 数据与归档

| 项 | 状态 |
|---|---|
| `ENV_ROOT/kb/{index,conflicts,baselines,runs,adjudication}` | 存在；`RUN-20261015-120626` 为冻结见证（只读） |
| `loop/state/` | 可删的运行时状态 |
| `doc/evidence/` | 验收报告 + 演练证据（内容冻结，只增不改） |

## 5 审计结论与修复状态（2026-10-19）

- 报告：`doc/audit/AUDIT-20261019-spec-conformance.md`；附录：`doc/audit/parts/`。
- 三路审计原始发现：规格↔实现 **49** 条、Agently 运行时 **44** 条、文档结构 **77** 条（含本轮已执行项）。
- **阻断级**（去重后 22 条）**已全部修复**：real 链路 N1/N6/N7/N9/N15 断裂；N8 模型失败默认 `pass`；
  单槽队列无唤醒；闸门「先签后恢复」失败楔死；槽按进程而非作业判活；N6 不产出沙箱导致 N9 测未修订用例；
  **外加实测 F-01（`n1_snapshot.py` 裸名 `kb_lib` NameError）与 F-02（`n2_diff.py` 主口径按 ENV_ROOT 解析）**。
- 同一轮还修了：I8 人触发真实晋升入口（`POST /api/runs/{id}/promote` + `services/promote.py`）、
  I18 waiting_gate/job/slot 区分、B2 写动作登记（spec §10.0 四个写动作）、证据聚合取最新轮/身份四方同值、
  N10 待裁决单一写者（[n10_pending.py](../kb/tools/n10_pending.py) + schema 加法扩展 `n10_items`）。
- 验收证据：`doc/evidence/FIX_ACCEPTANCE_20261019.md`（四道门命令与输出逐字复制）。
- **仍未修复（非阻断）**：审计报告 §4「重要/次要」中与本轮范围无关的条目仍保持可见；
  真机 real 全跑、72 条冲突清零、I3 双口径裁决仍需人工/环境执行。



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
