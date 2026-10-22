# 内网批次拉取后复核 · 原始证据

日期：2026-10-22（Asia/Shanghai）。被测提交：`a19107c`，比较基线：`fb83ed0`。本轮只复核，无业务修复；同一执行者源码审查和受控验证，不冒充独立终验。汇总见 [STATUS §35](../STATUS.md#35-内网批次拉取后复核2026-10-22)，问题解释见 [复核报告](../audit/AUDIT-20261022-intranet-batch-review.md)。

## 受影响集合与浏览器

从 loop 目录运行，临时业务根为空目录，软件 state 由现有 conftest 独立注入；没有使用真实基线或历史运行，没有改动任何产品实现。命令：

```bash
mkdir -p /tmp/intranet-review-20261022/workspace
PYTHONDONTWRITEBYTECODE=1 LOOP_WORKSPACE=/tmp/intranet-review-20261022/workspace LOOP_LLM_MODE=standin LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest -q tests/test_baseline_admission.py tests/test_api_baseline_detail.py tests/test_capability_facts.py tests/test_capability_format.py tests/test_paths_isolation.py tests/test_test_layers.py tests/test_doc_links.py tests/test_f06_structure.py tests/test_f08_sealed.py tests/test_n8_context_budget.py tests/test_context_explain.py tests/test_gate_session.py tests/test_run_view_state.py tests/test_agent_context_memory.py tests/test_agent_control.py tests/test_agent_view.py tests/test_web_smoke.py tests/browser --tb=short
```

原始 stdout/stderr，退出码 1：

```text
........................................................................ [ 25%]
.........................................F.............................. [ 50%]
........................................................................ [ 76%]
....................................................................     [100%]
=================================== FAILURES ===================================
_______ test_sigkill_during_publish_loop_never_yields_consumable_partial _______
tests/test_f08_sealed.py:104: in test_sigkill_during_publish_loop_never_yields_consumable_partial
    view = C.read_view(ctx.run_dir, "N6")  # 不得整体抛错
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
host/agent_control.py:89: in read_view
    raise ValueError(f'agent record checksum mismatch: {request_file.name}')
E   ValueError: agent record checksum mismatch: request.json
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /workspace/fpga_sim_workflow/loop/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_f08_sealed.py::test_sigkill_during_publish_loop_never_yields_consumable_partial
1 failed, 283 passed, 1 warning in 71.78s (0:01:11)
```

浏览器集合收集命令：`PYTHONDONTWRITEBYTECODE=1 LOOP_WORKSPACE=/tmp/intranet-review-20261022/workspace .venv/bin/python -m pytest --collect-only -q tests/browser`。

```text
41 tests collected in 0.06s
```

它们均包含在上面的受影响集合中，唯一失败是 F08 后端故障注入用例，浏览器没有失败或跳过。本轮未另跑软件层全套，不能把局部集合冒充全库结果。

## 失败用例单独复跑

从 loop 目录，命令：

```bash
PYTHONDONTWRITEBYTECODE=1 LOOP_WORKSPACE=/tmp/intranet-review-20261022/workspace LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest -q tests/test_f08_sealed.py::test_sigkill_during_publish_loop_never_yields_consumable_partial --tb=short
```

原始输出，pytest 退出码 0：

```text
.                                                                        [100%]
1 passed in 1.05s
```

这次通过不抹掉首次失败；说明随机终止落点不稳定。下面用确定性落点复现发布窗口。

## 确定性受控探针

仓库根运行：

```bash
PYTHONDONTWRITEBYTECODE=1 loop/.venv/bin/python doc/audit/parts/intranet-batch-probe.py
```

[源码](../audit/parts/intranet-batch-probe.py) 只写自动清理的临时目录。坏编码探针使用真实 FastAPI 路由、替换只读工作区定位、不运行 lifespan；校验发布探针在实际 seal_record 的校验文件创建步骤注入真实子进程退出；N8 使用默认沙箱预算；预算显示调用真实 Node 模块。没有调用 provider、仿真或真实 kb 写工具。退出码 0 代表观察完成。

原始 stdout：

```jsonl
{"probe": "artifact_boundary", "kind": "relative", "valid": true, "outside_all_allowed_roots": true}
{"probe": "artifact_boundary", "kind": "absolute", "valid": false, "outside_all_allowed_roots": true}
{"probe": "manifest_encoding", "http_status": 500}
{"probe": "checksum_publication_crash", "child_exit": 9, "prior_state": "committed", "checksum_bytes": 0, "partial_state": "corrupt", "read_error": "ValueError: agent record checksum mismatch: request.json"}
{"probe": "n8_feasible_full_plan", "full_bytes": 59341, "budget": 60000, "actual": "N8 上下文预算不足：分片后 61835 > 60000 bytes"}
{"probe": "context_budget", "host_bytes": 72, "displayed_bytes": 1055}
```

stderr 为既有 FastAPI TestClient 弃用提示，不影响上述观察。

## 文档门与环境限制

仓库根：`PYTHONDONTWRITEBYTECODE=1 loop/.venv/bin/python doc/audit/check_doc_links.py`，退出码 1。采样在复核报告/探针落盘后、本文及 STATUS 更新前。原始输出头：

```text
TOOL_ROOT = /workspace/fpga_sim_workflow
ENV_ROOT  = /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
WORKSPACE = /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/kb
checked=1412 skipped=14143 historical=857 known_missing=10 env_missing=304 missing=116
```

本机注册表指向的 ENV_ROOT/WORKSPACE_ROOT 不存在。工作区数据引用因此会进入 missing，环境资产进入 env_missing；还包含已有仓库路径问题，不能全部归为本轮代码错误或全部当作外部缺件忽略。没有通过伪造目录/夹具将门禁刷绿，没有用该结果推翻上一执行端特定根配置下的采样。

未运行：内网真实非默认基线链路、完整业务单测、kb 自测、完整端到端、真实 provider、S0-b 三库。没有重新开展 F14 样式改动或截图验收。

已核对旧证据/历史/审计内容 MD5 与被测 HEAD 相同、loop/kb 实现无差异、探针 Python 语法有效。新文档链接与补丁检查汇总见 STATUS §35。本文冻结后不回填，MD5 记录在目录外的 STATUS。
