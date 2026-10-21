# Agent 上下文与记忆验证证据（2026-10-21）

本轮按用户授权，先更新根 AGENTS.md、[规格](../spec/AGENT_CONTEXT_SPEC.md)和[计划](../plans/2026-10-21-agent-context-memory.md)，再固定特征、运行红灯、局部提取和实现。
实测入口：[STATUS §8](../STATUS.md)。本记录由同一执行者产生，不声称独立复核或真实模型质量评估。

## 命令

从软件仓根执行，模型请求由测试 provider 接管，不访问真实服务：

```bash
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k characterization
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k 'not characterization'
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k missing_or_invalid_context
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k distant
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k configuration_error
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q -k 'resolved_apis or api_facts'
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py -q
```

红灯命令在对应实现前运行；特征测试在原实现和保持行为的提取后分别通过。

扩展回归使用独立临时目录作为既有工具 subprocess 的 cwd。该目录没有仿真资产、基线或历史夹具，不是对真实环境的替代：

```bash
validation_root=$(mktemp -d /tmp/fpga-agent-regression-XXXXXX)
LOOP_ENV_ROOT="$validation_root" LOOP_WORKSPACE="$validation_root/kb" LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_agent_context_memory.py loop/tests/test_fix_real_chain.py loop/tests/test_admission_and_jobs.py loop/tests/test_agent_view.py loop/tests/test_config_api.py loop/tests/test_evidence.py loop/tests/test_fix_kbtools.py loop/tests/test_fix_integration.py loop/tests/test_web_smoke.py -q
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/browser -q
```

为区分回归与已有缺件，将 HEAD 通过 git archive 解包到临时测试快照，再应用上轮 UI 补丁，在同样的空执行目录条件下运行上述既有测试集合（不含本轮新增测试）。没有创建 Git worktree；当前仓库和原历史资产没有被修改。失败用例名称在前后两次相同。

## 原始输出摘要

### 原特征基线

```text
4 passed, 22 deselected in 0.73s
```

### 保持行为的提取

```text
4 passed, 22 deselected in 0.68s
```

### 新功能红灯

```text
22 failed, 4 deselected in 1.00s
```

### 源错误红灯

```text
4 failed, 28 deselected in 0.62s
```

### 远处修订点红灯

```text
1 failed, 37 deselected in 0.60s
```

### 认证异常红灯

```text
1 failed, 42 deselected in 0.60s
```

### API 定义和缓存红灯

```text
3 failed, 43 deselected in 0.65s
```

### 最终独立测试

```text
46 passed in 1.04s
```

### 扩展回归

```text
2 failed, 139 passed, 4 skipped, 1 warning in 8.07s
```

### 修改前快照回归

```text
2 failed, 93 passed, 4 skipped, 1 warning in 8.63s
```

### UI 回归

```text
14 passed in 21.32s
```

## 失败与跳过的解释

修改前后共同失败：

```text
FAILED loop/tests/test_fix_real_chain.py::test_n6_apply_drill_copies_fixture_sandbox_and_never_fails
FAILED loop/tests/test_fix_real_chain.py::test_n3_writes_digest_file_drill_and_real_standin
```

前者需要原归档 sandbox/TESTLIB，后者需要原 n3_digest.md。云端没有内网历史夹具；没有改断言或用新文件冒充归档来消除失败。跳过项仍依赖原 fixture_run。

本轮没有执行真实 provider、真实编译仿真或完整端到端。kb 工具语义未改，原归档兼容自测的缺件限制沿用 STATUS §7，没有将其记作本轮通过。

## 可观察能力与保留边界

独立测试实际捕获各语义节点的请求、验证只读记录及摘要 CLI，包含跨进程的尝试分配、错误/取消/替身状态、写盘失败、来源逃逸/指纹变化、事实/规则版本不符和人工确认筛选。CLI 不重发模型请求、不默认输出源码。

调用记录的 validated 仅表示该次模型返回通过既有 Host 输出校验，不代表节点最终通过或整轮发布获批。人工确认经验仍由当前事实和既有业务校验约束；没有新建授权或执行状态机。

上轮冻结 UI 证据保持原内容；本轮证据完成后只读冻结并在目录外记录 MD5。

## 文档与原证据核验

全库扫描仍报告既有缺件；对当前文档与 Git HEAD 使用相同候选解析规则逐项比对（NUL 分隔保留中文路径），并检查本轮新增 Markdown 链接：

```text
checked=810 skipped=10117 historical=834 missing=350
Additional unresolved inline paths versus HEAD: 0
New document Markdown links resolve.
```

这不替代全库零断链门。diff 空白检查通过。
上轮 [UI 证据](UI_SESSION_20261021.md) 的 MD5 为 `8cace0dd60779e87ee59162f1a209c74`，目录外校验清单复验输出 OK；原文件未修改。
