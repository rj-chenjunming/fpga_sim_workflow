# DSH_S4_20261028 · S4 投影与界面 证据档

> 冻结口径：本目录文件 **只读**（`chmod 444`），md5 记在目录之外（`doc/evidence/DSH_S4_20261028.md5`）。
> 契约：[SPEC-REV-16](../../spec/SPEC-REV-16-20261028.md)；计划：[2026-10-28-s4-projection-ui.md](../../plans/2026-10-28-s4-projection-ui.md)；
> 入口：[开工提示词 S4–S6](../../agents/开工提示词_S4-投影取证与候选导入.md) §4.1。
> 层：**C1（机制/本机）**。不含 C2（真实 DSH Web 实例内嵌）与 E（内网业务）。

## 1 结论三态

| 项 | 结论 | 依据 |
|---|---|---|
| **总结投影**（`OBS-02`） | **满足（C1）**：`progress` 字段按 `SPEC-REV-16 §2.1` 下发，卡片与窗口**同一实现**；刷新/重建同值 | `raw/red-green.md` S4-A；`services/agent_view.py:409/611/633` |
| **无进展告警**（`OBS-03`） | **满足（C1）**：判据 = 注入 `now` + 显式阈值 `NO_PROGRESS_THRESHOLD_S=600`；**只告警**（不改状态、不发命令）；红字含分钟/最后事件/最后错误；Agent 状态面无"在等人工"类文案（作用域 `#agentWindow`+`#agents`） | `tests/test_agent_view_projection.py`、`tests/browser/test_s4_projection_ui.py` |
| **未知保持未知**（`OBS-04`） | **满足（C1）**：`compaction.count`/`elapsed_s`/`last_tool`/`identity.*` 缺来源 ⇒ `null`+unknown；`standin`/`unknown` 与完成态分列；未显示 0 | 同上 + 反向抽检（`raw/reverse-sampling.md`） |
| **同源反代**（`OBS-05`/`OBS-06`） | **满足（C1）**：目标唯一来源 `<run_dir>/agent_instance.json`；R1–R20 逐条拒绝/改写；token 零回显；不可用态 503 + reason（HTML/JSON 双语义）；上游用**本地 loopback 假服务真跑**（含 POST `/api/*` 到达 + Origin/Referer 改写） | `tests/test_instance_proxy.py`（45 例）、`raw/s4-gate*.log` |
| **iframe 降级**（`OBS-07`） | **满足（真实上游未验）**：可用/不可用/探活失败三态都有明确呈现；降级块含原因 + 新标签页 + 导出会话副本；探测成功后才置"已内嵌" | `tests/browser/test_s4_projection_ui.py`（24 例） |
| **S3 接面**（`OBS-08`） | **满足（界面半边）**：accepted/applied/effective 三列分列；`scope_expiry` 恒"未判定"；WM availability/unavailable、EXP selected/rejected 只读透传；前端不重算 | 同上 + 反向抽检 |
| **内嵌真实 DSH Web** | **不可声称**：真实实例端口/令牌落账、iframe 内上游绝对资源路径（§9-10）、多帧 zstd 原文导出（§9-11）均未验 | `SPEC-REV-16 §9` |
| **C2 / E** | **不可声称**：本片不接真实 DSH/模型/内网业务 | 同上 |
| **四道门是否"全绿"** | **不声称全绿**：单测门 `3 failed` 是既有 `env_layer`（ENV_ROOT 只读）、`137 errors` 是浏览器缺 Chromium；**浏览器门单独全绿**（`138 passed`） | `raw/s4-gate1-unit.log`、`raw/s4-gate5-browser.log` |

## 2 收口门（Lead 独占窗口；原始输出见 `raw/`）

| 门 | 结果（命令输出复制） | 文件 |
|---|---|---|
| 单测（可写数据根 `<repo>/.dev-ws`） | `4 failed, 1607 passed, 1 warning, 137 errors in 407.31s` | `raw/s4-gate1-unit.log` |
| ↳ 3 failed | 既有 `@pytest.mark.env_layer`：`test_archive_e2`×2、`test_projection_and_frozen`×1（ENV_ROOT 只读，**环境缺件不冒充通过**） | 同上 |
| ↳ 第 4 failed | `test_gate_projection::test_start_honors_now`：**并发污染**（另一 pytest 进程用同一固定 `LOOP_NOW` 建出 `RUN-20310101-000000` ⇒ `运行目录已存在`）。全新数据根单独复跑 ⇒ `8 passed, 1 warning in 17.88s` | `raw/s4-recheck-gate_projection.log` |
| ↳ 137 errors | `tests/browser/**` 缺 Chromium（113 既有 + 24 新增；不并入四门） | `raw/s4-gate1-unit.log` |
| kb 自测 + env layer | `_selftest_gate_schema PASS=10` / `_selftest_n5_reachability PASS=9` / `_selftest_adjudicate_conflicts PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 13.40s`；**原 ENV_ROOT 零写入** | `raw/s4-gate2-kb.log` |
| 端到端（drill） | `phase 1 / 2 / 3 / 4 / 4b / 5` 全 `rc=0`，`=> ALL PASS` | `raw/s4-gate3-e2e.log` |
| 文档门 | `65 passed in 2.28s` | `raw/s4-gate4-doc.log` |
| **浏览器门（全量）** | `138 passed in 153.80s`（既有 114 + S4 新增 24，0 failed / 0 error） | `raw/s4-gate5-browser.log` |

## 3 独立复核（未参与实现，只报告不改）

- 结论：**无 P0；1×P1（已修）；7×P2（4 修 3 登记）**。
- P1-1「内嵌可用性没接当前 attempt」：服务端改为 `(node, attempt)` 粒度 + `attempt` 回显；前端显式带 `?attempt=`；补 2 条单测 + 2 条浏览器用例；复核者复测"把 attempt 钉成 1"的变异**已能被抓住**。
- P2 处置：`session-copy` 归属校验（修）、httpx INFO 日志压级（修，import 期生效 + import-time spy 用例）、R8 同时量 `raw_path`（修）、时间解析收敛到 `host/paths.py::now_epoch`（修）；角色卡 identity 为 null、`entries.availability` 转发口径、反代归属规则两处重复 → **登记未决**（`SPEC-REV-16 §9-12/13`、计划 §6-11/12）。
- 复核者的反向抽检 26+2 条与逐条结果：`raw/reverse-sampling.md`；其原始报告见 `raw/reviewer-final.md`。

## 4 纪律核对

- **写权**：`kb/**` 本轮**只有一处**改动——`kb/tools/kb_lib.py` 的 `GATE_MATERIAL_EXCLUDE_DIRS` 加 `agent_workspaces`（S5 C2a 的单独变更，见 S5 收口证据；理由：执行期暂存会合法变化，不排除会让签名后正常读写导致 `stateHash` 恒失配）。`loop/SETTINGS.yaml`、`loop/prompts/**` 本片**零改动**。
- **唯一判据（红线 8）**：无进展阈值/压缩计数/指令三态/预算/闸门枚举均只有一处实现；前端只做取整与标签映射（复核已用 `grep` + 变异验证）。
- **时间口径（红线 7）**：`now` 唯一入口 `paths.now_iso → paths.now_epoch`；S4 新增代码无 `datetime.now()/time.time()`；测试不用墙钟。
- **失败显式**：反代不可用/拒绝、投影缺来源、`execution_unknown` 都是显式状态 + reason，没有"在等人工"式伪装。
- **证据只增不改**：本目录冻结 444，md5 记在目录外。

## 5 复现命令

```bash
# 单测（可写数据根；绝对路径，别用 loop/.dev-ws）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# kb 自测 + env layer（派生 ENV_ROOT 副本，原 ENV_ROOT 零写入）
cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests

# 端到端（drill）
cd loop && bash spikes/provision_dev_workspace.sh
cd loop && LOOP_WORKSPACE=/home/work/chenjunming/change-impact-loop/.dev-ws LOOP_LLM_MODE=standin bash spikes/accept_v1_run.sh
cd loop && bash spikes/provision_dev_workspace.sh --cleanup

# 文档门 + 浏览器门
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_doc_links.py
cd loop && PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser
```

## 6 未做 / 不声称

1. 真实 DSH Web 实例的端口/令牌落账（`agent_instance.json` 写入方）属 S5；本片缺失即 `target_missing`。
2. iframe 内上游**绝对资源路径**未解决（不做 HTML 重写/`<base>` 注入），S5 真机实测后再定（`REV-16 §9-10`）。
3. 人类可读会话原文导出未实现（`session-copy` 只给解析事实；多帧 zstd 未验，`§9-11`）。
4. 卡片侧 `identity.attempt/session_id` 为 `null`（诚实值，跨层接线另开小片，`§9-12`）。
5. `ProgressLog` 事件 `ts` 与注入时钟不同源（drill 下 `silence_s` 夹 0，不产生假告警但可能掩盖停滞，`§9-8`）。
6. WebSocket/SSE 反代未支持（405）；`SETTINGS` 常驻实例源未实现（`§9-2`、`§9-6`）。
