# S0 工作台验证记录

本轮仅采用用户修订稿 S0。先规格与计划，再既有特征基线、新增失败测试、实现及回归。同一执行者分阶段验证，不声称独立复核。统计权威见 ../STATUS.md §9。

## 能力与限制

S0-a 完整派生、RTL 整体替换、非 RTL 比对、基线前后指纹、准备报告、派生 context、只读漂移核验已实现。S0-b 的接口核对/自动适配/逐 hunk 登记和真实三库驱动尚未接入；ready_for_execution 保持 false。既有闭环未迁移为附件 S3；没有修改 S1–S4 或既有闸门。

使用临时受控工程验证软件，未访问内网仿真资产，未运行真实三库编译。

## 修改前特征基线与红灯

命令：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser/test_run_sessions.py loop/tests/test_web_smoke.py loop/tests/test_config_api.py -q

```text
25 passed, 1 warning in 21.12s
```

新增 Host 用例先出现 ModuleNotFoundError: No module named host.s0（收集失败，未执行断言）；新增 UI 用例先报 viewS0 不存在。报告丢失/写失败补充边界先失败，再修正落盘顺序。

```text
1 failed, 14 deselected in 7.33s
2 failed, 24 deselected, 1 warning in 0.78s
```

## 最终相关单测与浏览器

命令：LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser/test_run_sessions.py loop/tests/test_s0.py loop/tests/test_web_smoke.py loop/tests/test_config_api.py -q

```text

........................................................                 [100%]
=============================== warnings summary ===============================
loop/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /workspace/fpga_sim_workflow/loop/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
56 passed, 1 warning in 28.92s

```

## 扩展回归

使用独立空临时执行目录（非仿真环境）：LOOP_ENV_ROOT=<temp> LOOP_WORKSPACE=<temp>/kb LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py loop/tests/test_fix_real_chain.py loop/tests/test_admission_and_jobs.py loop/tests/test_agent_view.py loop/tests/test_config_api.py loop/tests/test_evidence.py loop/tests/test_fix_kbtools.py loop/tests/test_fix_integration.py loop/tests/test_web_smoke.py loop/tests/test_s0.py -q

该次扩展回归在新增报告边界用例前执行；之后只重跑受影响集合。剩余失败与上轮相同，依赖缺失历史夹具。

```text

=========================== short test summary info ============================
FAILED loop/tests/test_fix_real_chain.py::test_n6_apply_drill_copies_fixture_sandbox_and_never_fails
FAILED loop/tests/test_fix_real_chain.py::test_n3_writes_digest_file_drill_and_real_standin
2 failed, 163 passed, 4 skipped, 1 warning in 8.60s

```

## 真实浏览器 + 实际 API + 临时文件系统

脚本：/workspace/scratch/s0-browser-accept.py。起临时 FastAPI 服务，填写真实页面，派生临时工程、核对旧 RTL 删除和基线前后见证、重新核验 TB 漂移、检查窄屏溢出及 pageerror。没有模拟 API 响应，工程内容为软件测试夹具。

```text

{"result": "S0 browser + real API + controlled filesystem passed", "root": "/tmp/s0-browser-9lenn8na", "record": "S0-20261021T081348275883-bfc0e9ff2e", "pageerrors": []}

```

桌面、准备后、漂移、手机截图位于 /workspace/scratch/s0-desktop.png、s0-prepared.png、s0-drift.png、s0-mobile.png；已做视觉检查。截图为受控工程，不是真实项目数据。最后增加目录范围的折叠说明与文案修正未改变派生/闸门逻辑。

## kb 自测

命令：在各自独立临时 LOOP_ENV_ROOT / LOOP_WORKSPACE 下执行 loop/.venv/bin/python kb/tools/_selftest_gate_schema.py 及 _selftest_n5_reachability.py。

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
[FAIL] 10 归档 gates.json 仍过校验 (跳过：/tmp/s0-gate-check-zpnE3i/kb/runs/RUN-20261015-120626/gates.json 不存在)

汇总：PASS=9 FAIL=1

[PASS] 1 宏第2实参识别为调用点 (['I2C_SLV_RW', 'PCIE_REG_RW', 'PCIE_REG_RW_B'])
[PASS] 2 `define 定义行不算调用点 
[PASS] 3 普通调用不算宏调用 
[PASS] 4 FORKJN_FOR_BLK_PHASE 变体覆盖 
[PASS] 5 跨行宏实参覆盖 
[FAIL] 6 夹具存在 (跳过真实用例检查：/tmp/s0-n5-check-q25UM9/kb/runs/RUN-20261015-120626/sandbox/TESTLIB 不存在)
[PASS] 9 源不可读 ⇒ ok=False（调用方须标 static-only，不许猜 live） (用例源不可读（缺失/二进制）：/workspace/fpga_sim_workflow/kb/tools/__no_su)

汇总：PASS=6 FAIL=1

```

## 文档及其他门

全库 python3 doc/audit/check_doc_links.py 仍报缺失；缺内网环境及既有扫描器三根误报沿用。相较本轮开始新增的未解析 inline 项仅为授权范围描述引用的外部 TB/top.sv：AGENTS 中一次、S0 契约中两次。它们是明确未挂载的环境资产，不是仓库 Markdown 链接。变更文档实际 Markdown 链接均已验证目标存在。

```text

checked=818 skipped=10140 historical=834 missing=353
Changed Markdown links: all targets exist.
```

node --check 的 app.js / s0.js 与 git diff --check 通过。端到端 accept_v1_run.sh 未运行：内网有效基线/历史演练夹具/UVS 插件不可用，而且该脚本会清理当前运行状态；本次受控 S0 浏览器/API 验证不能替代它。四道门未全绿。

## 内网验收保留项

在内网挂载真实工程后，复核完整复制和内容见证；接入明确的外部接口差异及三库驱动契约，验证允许的 top.sv 改动逐 hunk 登记、越界拒绝、三库零 error、warning 评估、逐 hunk 否决回滚后重编译、基线零写；再将 S0 完整判据接入新版执行入口。云端不要求外传内网资产。
