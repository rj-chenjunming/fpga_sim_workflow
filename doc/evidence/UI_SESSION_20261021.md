# UI 会话可靠性验证证据（2026-10-21）

基线：`5f6cdb2`。本轮先对整体工作流做风险评估，再实施 UI 会话隔离；没有更改业务权威。

规格：[UI §7.1](../spec/WEB_UI_SPEC.md)；计划：[实施计划](../plans/2026-10-21-ui-session-reliability.md)；
实测数字入口：[STATUS §7](../STATUS.md)。本记录为同一执行者的验证，不声称独立复核。

## 命令与边界

在软件仓根执行：

```bash
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser -q -k characterization
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser -q -k 'not characterization'
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser -q -k returning
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest loop/tests/browser -q
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests -q
LOOP_LLM_MODE=standin loop/.venv/bin/python -m pytest loop/tests/test_admission_and_jobs.py loop/tests/test_agent_view.py loop/tests/test_config_api.py loop/tests/test_evidence.py loop/tests/test_fix_kbtools.py loop/tests/test_fix_integration.py loop/tests/test_web_smoke.py -q
LOOP_WORKSPACE=/tmp/fpga-kb-validation loop/.venv/bin/python kb/tools/_selftest_gate_schema.py
LOOP_WORKSPACE=/tmp/fpga-kb-validation loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py
loop/.venv/bin/python doc/audit/check_doc_links.py
node --check loop/web/app.js
git diff --check
```

全套后端在修改实现前运行；它不包含当时尚未新增的浏览器测试。浏览器各阶段按测试文件与实现的推进顺序运行，修改前失败是预期的红灯证据。

浏览器运行原始 HTML/JS/CSS，用 API 替身控制响应时序和拒绝，不调用真实模型或仿真，不形成真实人工签署。最终覆盖请求乱序、跨运行草稿、中断更换、表单双向同步、重复提交与拒绝恢复。

## 各阶段输出摘要

### 修改前特征

```text
3 passed, 10 deselected in 5.66s
```

### 修改前新增回归

```text
8 failed, 2 passed, 3 deselected in 54.02s
```

### 提交中切回：修改前

```text
1 failed, 13 deselected in 7.25s
```

### 最终浏览器回归

```text
14 passed in 20.81s
```

### 后端相关验证

```text
56 passed, 4 skipped, 1 warning in 6.33s
```

### 修改前后端全套

```text
61 failed, 132 passed, 6 skipped, 1 warning, 3 errors in 17.10s
```

### gate schema

```text
汇总：PASS=9 FAIL=1
```

### n5 可达性

```text
汇总：PASS=6 FAIL=1
```

## 未通过门的诊断

修改前全套后端失败包含：原主机目录缺失与只读路径写入错误、当前基线列表为空、插件目录不存在、历史 drill sandbox 缺失后返回 drill_noop 而测试期望 drill_fixture、冻结见证缺失。没有把这些结果改写成通过，也没有用合成文件冒充原归档。

kb schema 自测的历史归档兼容项失败；n5 自测的真实用例项因夹具缺失未执行。全库路径扫描还混有扫描器将软件工具与 schema 解析到外部环境的既有问题。本轮未改扫描器，也未改冻结历史文档。

端到端终验没有运行，前置环境插件、有效基线、索引和历史夹具不在当前机器。

## 服务烟测

通过子进程从 loop 目录启动 uvicorn，仅绑定环回地址；查询健康与静态资源后停止自己启动的进程。输出：

```text
/ 200 12982
/app.js 200 96724
/legacy.html 200 87425
health: {"ok": true, "plugin_missing": ["RTL/", "TB/", "PKG/", "TESTLIB/", "uvs.setup"], "workspace_missing": ["index", "conflicts", "baselines", "runs"]}
```

JS 语法与 diff 空白检查退出成功。没有发布环境，没有提交或推送代码，没有运行真机仿真。

## 新增文档检查与环境草稿

使用原扫描器的候选解析规则，将当前 Markdown 的缺失路径与 Git HEAD 内容逐项对比（Git 路径使用 NUL 分隔以保留中文文件名），并解析本轮新增文档的 Markdown 链接：

```text
Additional unresolved inline paths versus HEAD: 0
New document Markdown links resolve.
```

这只证明本轮没有新增路径缺失，不能替代全库零断链验收。

已保存环境草稿的 install_script 与 start_skill，包含 Python 依赖安装、Chromium 交互验证、本地服务启动及外部环境缺件说明。保存结果为 saved、requires_publish=true；它不执行安装、不补齐插件，也不代表已发布或已验证新任务恢复。
