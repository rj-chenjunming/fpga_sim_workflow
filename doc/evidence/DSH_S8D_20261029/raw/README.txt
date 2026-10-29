# DSH_S8D_20261029 · raw 转录（实现 owner 自跑，非 Lead 门）

纪律：本目录只放**命令原始输出**（逐字复制）；正式证据档（README/.md5/STATUS 数字）
由 Lead 生成。数字不得从本目录手抄进 STATUS 之外的权威文件。

| 文件 | 内容 | 对应命令 |
|---|---|---|
| 00-before-probe.txt | 改造**前** drill 实测（事件 ts 走墙钟、silence_s 夹 0） | `LOOP_NOW=2026-10-28T12:00:00 python -B <<probe>>`（见 05 同源） |
| 01-characterization-green.txt | 特征测试（钉旧行为）在旧实现上跑绿 | `pytest -q tests/test_progress_ts_source.py`（当时 3 条） |
| 02-new-contract-red.txt | 新契约用例在**旧实现**上的红（先失败用例） | 同上（当时 17 条：12 failed / 5 passed） |
| 03-affected-face-green.txt | 受影响面 7 个测试文件（改后） | `pytest -q tests/test_progress_ts_source.py tests/test_agent_view_projection.py tests/test_agent_view_baseline.py tests/test_agent_view.py tests/test_agent_view_identity_cold_read.py tests/test_instance_proxy.py tests/test_projection_and_frozen.py -m "not env_layer"` |
| 04-software-suite-post-change.txt | 软件层全量自查（不含 browser / env_layer） | `pytest -q tests --ignore=tests/browser -m "not env_layer"` |
| 05-after-probe.txt | 改造**后** drill 实测（同源 0s / +700s⇒warn / 历史墙钟⇒null+unknown） | 同 00 的探针，改后重跑 |
| 06-browser-obs03.txt | 浏览器 OBS-03/窗口子集（route-mock 桩） | `pytest -q tests/browser/test_s4_projection_ui.py tests/browser/test_agent_window.py` |
| 07-redline-grep-and-diffstat.txt | 红线 grep（`time.time()` 0 命中）+ diff --stat + git status | 见文件内 `$` 行 |

环境：数据根 `<repo>/.dev-ws-s8d`（`provision_dev_workspace.sh --link-fixture`），
`LOOP_LLM_MODE=standin`；浏览器用 `HOME=<repo>/.chrome-home-s8d`、`TMPDIR=<repo>/.chrome-tmp-s8d`、
`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers`。
