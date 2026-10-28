# S4 独立复核终态报告（s4-reviewer，未参与实现；只报告不改）

> 采样：2026-10-29 00:14–00:15（窗口关闭后，冻结 md5 上重跑）。复核者未修改任何被测文件；反向抽检全部在 gitignored 私有副本 `loop/.logs/s4-verify/` 内进行（脚本 `scripts/final_reverse_checks.py`，已逐条 md5 复原；`s4-before.patch` 与四件备份保留）。

## 结论

- **P0 = 0，P1 = 0**。
- **可声称**：S4 三片（A 投影/无进展/S3 接面；B 同源反代；C 界面）在下列冻结 md5 上通过独立复核；定向单测 **137 passed**（5 文件）、S4 浏览器单文件 **24 passed**、**28 条反向抽检全红**（含上一轮唯一未变红的 attempt 变异）；红线 8 / 文案作用域 / 时间口径 / 未知保持未知逐条通过；`kb/**`、`loop/SETTINGS.yaml`、`loop/prompts/**` 中 **S4 三片零改动**。
- **不可声称**：① 真实 DSH Web 实例内嵌与 HTML 绝对路径（REV-16 §9-10）、人类可读会话原文导出（§9-11）；② S5/S6 其它切片未复核；③ 全量五道门数字以 Lead 实测为准（复核者只跑定向与单文件）；④ 冻结 md5 之外再有改动则本结论失效。

## 终态 md5 与用例数

| 文件 | md5 | 用例 |
|---|---|---|
| `services/instance_proxy.py` | `9f2029aa890a63a638160c880dcca9c4` | — |
| `services/api.py` | `5ac8871e95bc88995297152a8a5c7401` | — |
| `services/agent_view.py` | `8c1d94a775349f0e6ab4534c274319d9` | — |
| `services/contracts.py` | `cc1c5db5355a81b2a4f55f588036102a` | — |
| `host/paths.py` | `9547298e3ad1383e3bb3cc57fd4d117c` | — |
| `web/agent-window.js` | `c11f9b0d372e80ef3eccd044fe40032d` | — |
| `web/s4-view.js` | `1e017fbb99868d5072fa352267c6779a` | — |
| `tests/test_instance_proxy.py` | `f328a350f33a3c60f60c694289aeaaa3` | 45 passed |
| `tests/test_agent_view_projection.py` | `b6af168ce8080d75dc73fcac319e456b` | 39 passed |
| `tests/test_agent_view_baseline.py` | `1f75a75d1eeeda6336791b2d9ce67e27` | 37 passed |
| `tests/test_agent_view.py`（既有） | — | 12 passed |
| `tests/test_paths_isolation.py`（真实仓） | — | 4 passed |
| `tests/browser/test_s4_projection_ui.py` | `93d9fe4d3128c11d994399a072c3acde` | 24 passed in 24.36s |

## P1-1 闭合证据

上一轮"把 `availability()` 的 attempt 钉成 1 ⇒ 用例仍绿"的覆盖缺口已闭合，两条变异都红：

| 变异 | 用例 | 结果 |
|---|---|---|
| `availability()` 里 `load_target(run_dir, node, attempt)` → `load_target(..., 1)`（P1-AVAIL-pin1） | `test_p1_availability_scoped_to_node_and_attempt` | **RED** |
| `load_target` 里 `effective_attempt = attempt if attempt is not None else 1`（P1-TARGET-pin1） | 同上 | **RED** |

新增覆盖：`test_p1_availability_scoped_to_node_and_attempt`（tests/test_instance_proxy.py:985）、`test_p2_session_copy_scoped_to_node_and_attempt`（:1013）、浏览器 `test_instance_and_session_copy_requests_carry_selected_attempt` / `test_attempt_scoped_instance_two_states`。

## 28 条反向抽检（逐条 restored=True；未变红 0 条）

R1 R2 R3 R4 R6 R7 R9 R13 R14 R15 R16 R17 R18 R19 R20（R5/R8/R10/R11/R12 只读核验未变异）｜TOKEN-log｜TARGET-url（SSRF）｜P1-AVAIL-pin1｜P1-TARGET-pin1｜P2-OWNER（session-copy 归属）｜P2-SILENCE-import（import 期日志静音）｜NOPROG｜NOPROG-UNK｜STANDIN｜COMPACT｜ACCEPTED（revoked 用例）｜SCOPE｜SESSION-shape。

## 残余 P2（5 条，不阻塞冻结）

1. **契约同步（Lead 写权）**：§6.1 响应对象未含 `attempt` 回显字段；§6.2 未登记新 reason 族；§5.5 `REASONS` 仍 8 个（实现与契约逐字一致，**无第二套代理判据**）。→ 已由 Lead 补进 REV-16 §6.1/§6.2。
2. **归属判据两处实现**（`load_target` 与 `session_copy`）：语义一致，建议抽 `_owned_document()`。→ 登记 `REV-16 §9-15`。
3. **`test_p2_httpx_info_logging_never_prints_managed_token` docstring 不准/顺序耦合**：import 期保证由 `test_p2_import_time_silencing_is_explicit` 覆盖（实测 RED ⇒ 非空断言）。→ 登记 `REV-16 §9-17`。
4. **前端未映射 `session_*` reason**：直接显示英文枚举。→ 登记 `REV-16 §9-16`。
5. **角色卡 identity/last_error 恒 null**：已在 `agent_view.py:439` 登记为已知未决（诚实值）。→ `REV-16 §9-12`。

## 过程取证（供冻结引用）

- **S4 与 kb 写权分离**：`git status --porcelain -- kb loop/SETTINGS.yaml loop/prompts` 唯一命中是 `kb/tools/kb_lib.py`（`GATE_MATERIAL_EXCLUDE_DIRS` 加 `agent_workspaces`，属 S5 C2a 的单独变更）⇒ S4 三片零改动成立。
- **一处"假红"要记录**：在派生副本里跑 `tests/test_paths_isolation.py` 会红（`test_state_root_defaults_to_software_copy`），原因是 `host/paths.py::tool_root()` 从副本向上锚定到真实仓、`STATE_DIR` 与副本 `LOOP_DIR` 不同源；**真实仓跑 4 passed**。不是代码缺陷，但该用例对"在派生副本中运行"不鲁棒（S5/S6 复核时注意）。
- 复核者 00:01 前跑的 133/20/21 属窗口前旧态，未计入本报告。
