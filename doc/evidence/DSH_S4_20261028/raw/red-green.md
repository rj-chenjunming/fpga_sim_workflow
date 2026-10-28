# S4 三片 TDD 记录（RED → GREEN，数字从命令输出复制）

> 时点：2026-10-28/29 本窗口。命令均在 `loop/` 下执行。RED 数字为"实现前先失败"的证据；GREEN 为实现后定向通过。

## S4-A 总结投影 / 无进展 / S3 解释面（owner: s4-proj）

| 阶段 | 命令 | 结果 |
|---|---|---|
| 特征测试（先固定既有行为） | `pytest -q tests/test_agent_view.py tests/test_agent_view_baseline.py` | `49 passed`（既有 16 + 特征 33） |
| RED | `pytest -q tests/test_agent_view_projection.py` | `1 error in 0.18s`（`ImportError: NO_PROGRESS_THRESHOLD_S`） |
| GREEN | `pytest -q tests/test_agent_view.py tests/test_agent_view_baseline.py tests/test_agent_view_projection.py` | `86 passed` |
| GREEN（+控制权回归） | 上述 + `tests/test_agent_control.py` | `108 passed` |
| 增测后 | 四文件（含 P2-6 后） | `111 passed` → `115 passed`（含 `test_paths_isolation`） |
| 反向抽检 | 改坏实现→跑对应用例 | 阈值 600→60000 ⇒ 2 failed；`count` unknown→0 ⇒ 2 failed；`contracts` 不传 now ⇒ 3 failed；`accepted` 当 `applied` ⇒ 1 failed；越界/符号链接校验失效 ⇒ 2 failed；**每次复原后 86/111 passed** |

## S4-B 同源反代（owner: s4-proxy）

| 阶段 | 命令 | 结果 |
|---|---|---|
| RED | `pytest -q tests/test_instance_proxy.py` | `1 error in 0.42s`（`ImportError: cannot import name 'instance_proxy'`） |
| GREEN（首版） | 同上 | `38 passed, 1 warning in 13.76s` |
| GREEN（复核 P1-1/P2-1/P2-3/P2-4 后） | 同上 | `45 passed, 1 warning in 14.47s` |
| 受影响回归（可写数据根 `.dev-ws`） | 11 文件组合 | `250 passed` → `254 passed, 1 warning in 36.15s` |
| 反向抽检 | 30 个变异 | **28 被抓**；2 条如实登记：`M16` 删"绝对路径前置判据"与越界判据**行为等价**、`M23` 初版"只断言 logger.level"是**空断言**（已替换为 import-time spy 用例，替换后可抓） |

## S4-C 界面（owner: s4-ui）

| 阶段 | 命令 | 结果 |
|---|---|---|
| 特征基线 | `pytest -q tests/browser/test_agent_window.py tests/browser/test_ai_work_panel.py` | `29 passed in 33.27s` |
| RED | `pytest -q tests/browser/test_s4_projection_ui.py` | `15 failed, 2 passed in 131.41s`（缺 `#awSummary/#awS3/#awEmbed` 等） |
| GREEN 迭代 | 单文件 | 18 → 20 → 23 → **24 passed** |
| 受影响浏览器文件 | 6 既有 + 1 新 | `134 passed in 164.54s`（owner 自跑；收口门为 `138 passed in 153.80s`） |
| 反向抽检 | 6 条 + P1-1/P2-5 各 1 条 | ①`state!=='warn'` 守卫放宽 ⇒ RED ②`count=null`→0 ⇒ RED ③`scope_expiry`→"仍生效" ⇒ RED ④`accepted`→applied 列 ⇒ RED ⑤`standin`→真实完成 ⇒ RED ⑥不可用仍渲染 iframe ⇒ RED（首两次"改坏"被后续 `showFallback` 抵消=**无效锚点**，改锚点后 RED，已如实记录）；P1-1 `withAttempt` 恒不带 attempt ⇒ RED；P2-5 探测前置"已内嵌" ⇒ RED |

## S4 收口门（Lead 独占窗口，`raw/s4-gate*.log` 为原始输出）

| 门 | 命令 | 结果 |
|---|---|---|
| 单测 | `provision_dev_workspace.sh` → `LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin pytest -q` | `4 failed, 1607 passed, 1 warning, 137 errors in 407.31s`；3 failed = 既有 `env_layer`（ENV_ROOT 只读）、1 failed = **并发污染**（`test_start_honors_now` 撞 `RUN-20310101-000000`，见 `raw/s4-recheck-gate_projection.log` 单独复跑 `8 passed`）；137 errors = `tests/browser/**` 缺 Chromium |
| kb 自测 + env layer | `run_env_layer_checks.sh --with-kb-selftests` | `PASS=10/9/28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 13.40s`；原 ENV_ROOT 零写入 |
| 端到端 | `accept_v1_run.sh`（drill） | `phase 1–5 + 4b` 全 `rc=0`，`=> ALL PASS` |
| 文档门 | `pytest -q tests/test_doc_links.py` | `65 passed in 2.28s` |
| 浏览器门（全量） | 三组 env + `pytest -q tests/browser` | `138 passed in 153.80s` |
