# Agent 工作窗口验证记录

执行顺序：先规格/计划，既有特征基线，保持行为的单次调用提取，新增失败用例，再实现与回归。同一实现者分阶段验证，不声称独立复核。统计权威见 ../STATUS.md §10。

## 交付边界

卡片可进入绑定 run/node/session/attempt 的窗口；读取实际输入、提示词、Host 事件、结果与控制审计。模型请求边界支持 steer/pause/resume/terminate；旧尝试作废，重发新增 attempt，Host 消费者只在控制边界返回后取得输出。窗口不展示隐藏推理或伪造 token 流。

暂停只在当前服务进程存活时恢复；重启后的旧会话只读。取消超时禁止重叠请求，节点显式失败，晚到输出不消费。远端是否停止推理由提供方决定。没有修改 kb 闸门、业务副作用写权或执行拓扑。

## 特征基线与保持行为的提取

命令：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py loop/tests/test_agent_view.py loop/tests/browser/test_run_sessions.py -q

```text

........................................................................ [ 98%]
.                                                                        [100%]
73 passed in 23.76s

```

提取后：loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q

```text

..............................................                           [100%]
46 passed in 1.02s

```

## 新增失败用例

新控制模块缺失时为导入/收集错误，未执行断言；不把它说成业务断言失败。新窗口入口缺失、跨会话迟到回执、控制记录跨运行身份、取消超时缺少作废记录、尝试选择器和响应身份边界均先复现失败。


agent-window-red.log

```text
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
ERROR loop/tests/test_agent_control.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 warning, 1 error in 0.33s
```


agent-window-browser-red.log

```text
loop/.venv/lib/python3.12/site-packages/playwright/_impl/_connection.py:636: TimeoutError
=========================== short test summary info ============================
FAILED loop/tests/browser/test_agent_window.py::test_card_opens_actual_input_and_poll_preserves_draft
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 32.37s
```


agent-window-identity-red.log

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED loop/tests/test_agent_control.py::test_controls_reject_foreign_identity_even_with_valid_checksum
1 failed, 20 deselected, 1 warning in 0.61s
```


agent-window-session-red.log

```text

loop/tests/browser/test_agent_window.py:154: AssertionError
=========================== short test summary info ============================
FAILED loop/tests/browser/test_agent_window.py::test_old_control_receipt_cannot_clear_new_session_draft
1 failed, 6 deselected in 7.12s
```


agent-window-timeout-red.log

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED loop/tests/test_agent_control.py::test_cancellation_timeout_never_starts_overlapping_request
1 failed, 22 deselected, 1 warning in 0.62s
```


agent-window-selector-red.log

```text
loop/tests/browser/test_agent_window.py:173: AssertionError
=========================== short test summary info ============================
FAILED loop/tests/browser/test_agent_window.py::test_reopen_resets_attempt_selector_to_follow_latest
FAILED loop/tests/browser/test_agent_window.py::test_mismatched_response_cannot_enable_control_for_other_run
2 failed, 7 deselected in 13.36s
```

## 最终相关测试

命令：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/test_agent_control.py loop/tests/test_agent_context_memory.py loop/tests/test_agent_view.py loop/tests/test_s0.py loop/tests/test_config_api.py loop/tests/test_web_smoke.py loop/tests/browser/test_agent_window.py loop/tests/browser/test_run_sessions.py -q

```text

........................................................................ [ 51%]
.....................................................................    [100%]
=============================== warnings summary ===============================
loop/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /workspace/fpga_sim_workflow/loop/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
141 passed, 1 warning in 33.12s

```

之后仅补充尝试选择器重开复位和响应身份拒绝，最终重跑受影响浏览器集合：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser/test_agent_window.py loop/tests/browser/test_run_sessions.py -q

```text

............................                                             [100%]
28 passed in 35.78s

```

## 扩展回归

独立空临时执行目录：LOOP_ENV_ROOT=<temp> LOOP_WORKSPACE=<temp>/kb LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_control.py loop/tests/test_agent_context_memory.py loop/tests/test_fix_real_chain.py loop/tests/test_admission_and_jobs.py loop/tests/test_agent_view.py loop/tests/test_config_api.py loop/tests/test_evidence.py loop/tests/test_fix_kbtools.py loop/tests/test_fix_integration.py loop/tests/test_web_smoke.py loop/tests/test_s0.py -q

```text

=========================== short test summary info ============================
FAILED loop/tests/test_fix_real_chain.py::test_n6_apply_drill_copies_fixture_sandbox_and_never_fails
FAILED loop/tests/test_fix_real_chain.py::test_n3_writes_digest_file_drill_and_real_standin
2 failed, 189 passed, 4 skipped, 1 warning in 7.44s

```

剩余失败与上轮相同，依赖内网历史夹具；未引入新的既有回归失败。

## 浏览器 + 实际 API + 异步请求边界

脚本：/workspace/scratch/agent-window-accept.py。临时 FastAPI 服务使用真实控制 API、真实请求记录及 Host 校验，provider 为可取消/阻塞的受控函数；不是 live 模型或真机仿真，主工作流投影由测试装置提供。浏览器执行暂停、补充指令并恢复、再次暂停、恢复及终止；核对新请求收到指令、消费者只收到有效输出、终止后失败。

```text

{"result": "Agent window real API acceptance passed", "model": "controlled fixture; no live provider", "commands": ["pause", "steer", "pause", "resume", "terminate"], "consumed_outputs": 1, "model_attempts": 4, "pageerrors": [], "root": "/tmp/agent-window-accept-j_l720ks"}

```

已目视检查桌面与手机截图：/workspace/scratch/agent-window-desktop.png、/workspace/scratch/agent-window-mobile.png。手机模态内容可滚动，控制按钮经实际点击验证。

## 其他质量门

kb 自测各用独立临时数据根，命令为 loop/.venv/bin/python kb/tools/_selftest_gate_schema.py 和 _selftest_n5_reachability.py；缺历史归档项仍失败。

```text

[PASS] 1 check 名 'gate-state' 可解析 
[PASS] 2 check 名 'gate_state' 可解析 
[PASS] 3 两种拼法解析到同一个 schema 
[PASS] 4 schema 的 anchor.algo const 与 kb_lib._ANCHOR_ALGO 同源 (schema='sha256-of-canonical-state-without-anchor' code='sha256-of-canonical-state-without-anchor')
[PASS] 5 gate_init + gate_set 的产出过 gate_state.schema.json 
[PASS] 6 锚算法字段 == _ANCHOR_ALGO ({'algo': 'sha256-of-canonical-state-without-anchor', 'file': 'gates.sha256', 'value': '0aa9369aa4efa47325a0005499dd157167342ea61263b04726debd28d9f5eeac'})
[PASS] 7 algo 常量写错一词 ⇒ 写路径抛 SchemaError (对象 不符合 gate_state.schema.json：
  - $.anchor.algo: const 不符：期望 'sha256-of-canonic)
[PASS] 8 被拒时账本一个字节都没动（check 在 write_json 之前） (before=1b04eaca6994 after=1b04eaca6994)
[PASS] 9 被拒后 G2 仍是 pending（无半签） 
[FAIL] 10 归档 gates.json 仍过校验 (跳过：/tmp/agent-window-kb-gate-DTYBnQ/kb/runs/RUN-20261015-120626/gates.json 不存在)

汇总：PASS=9 FAIL=1

[PASS] 1 宏第2实参识别为调用点 (['I2C_SLV_RW', 'PCIE_REG_RW', 'PCIE_REG_RW_B'])
[PASS] 2 `define 定义行不算调用点 
[PASS] 3 普通调用不算宏调用 
[PASS] 4 FORKJN_FOR_BLK_PHASE 变体覆盖 
[PASS] 5 跨行宏实参覆盖 
[FAIL] 6 夹具存在 (跳过真实用例检查：/tmp/agent-window-kb-n5-D1c3xr/kb/runs/RUN-20261015-120626/sandbox/TESTLIB 不存在)
[PASS] 9 源不可读 ⇒ ok=False（调用方须标 static-only，不许猜 live） (用例源不可读（缺失/二进制）：/workspace/fpga_sim_workflow/kb/tools/__no_su)

汇总：PASS=6 FAIL=1

```

全库文档检查 python3 doc/audit/check_doc_links.py 在最终归档前采样：

```text

checked=820 skipped=10176 historical=834 missing=353

Additional unresolved inline references: {}
Changed Markdown links: all targets exist.
Previous frozen evidence: unchanged.
```

文档全库未通过，沿用未挂载环境与原扫描器解析问题；本轮未增加未解析引用。node --check 的 app.js / agent-window.js 及 git diff --check 通过。原端到端 accept_v1_run.sh 未运行，内网基线/UVS 插件/历史夹具不可用，本次请求边界验收不能替代完整工作流。四道门未全绿，不宣称完全合规。

## 内网保留验收

用实际 provider 验证请求取消、超时与重发，核对真实 N3/N6/N8/N10/N11/N12 的结果消费者及失败收敛、槽释放；重启时检查旧会话不可继续控制。继续执行既有单测、kb 自测及完整端到端；不要求把内网资产传到云端。
