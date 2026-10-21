# UI 会话可靠性：SpecDD 与特征测试驱动的局部重构

规格：[`WEB_UI_SPEC.md` §7.1](../spec/WEB_UI_SPEC.md)。本轮落点是运行选择→监控→人工闸门交互。

## 范围与 owner

| 关注点 | 唯一 owner / 落点 | 验证门 |
|---|---|---|
| 交互契约 | Lead / `doc/spec/WEB_UI_SPEC.md` §7.1 | 可观察行为与验收一一对应 |
| 选择、请求与草稿隔离 | UI 实现 owner / `loop/web/app.js` | Chromium 交互回归 |
| 特征与回归验证 | 本轮按顺序执行，验证阶段只报告结果 / `loop/tests/browser/` | 旧行为先绿、缺陷先红、改后全绿 |
| 业务权威 | 既有 Host / TriggerFlow / kb 工具 | 沿用 API 与后端测试，不迁移判定 |

本轮由同一执行者顺序切换角色，不声称做过独立复核。没有环境插件和历史夹具时，不伪造真实仿真结果。

## 顺序与验收

1. **特征基线**：真实 Chromium 加载原始静态页，拦截 API 模拟已知服务端响应；固定服务端选项原样展示、轮询保留输入和焦点、必填理由校验、防重复 POST、拒绝后原输入和 blockers 保留。先在修改实现前运行。
2. **缺陷复现**：同门同轮次跨运行草稿、A/B 请求乱序、A→B→A、轮询旧响应、提交时切换运行、服务端替换中断或撤回选项；新增行为先红。
3. **局部重构**：统一点击与轮询的详情读取入口，加入选择代次和请求序号；统一草稿/表单身份；限制异步提交回调的作用范围。每步保留既有 HTTP 请求形状和业务判定。
4. **UI 一致性**：两份闸门表单共享输入值，更新 DOM 值时避免无变化赋值，不替换焦点节点。
5. **验证与证据**：浏览器测试、可用后端测试、kb 自测、端到端和文档链接扫描分别记录。环境缺件导致的未运行或失败单列，不能称四门全绿。将本轮实测写入 `doc/STATUS.md`，追加冻结证据。

## 运行浏览器测试

```bash
cd loop
.venv/bin/python -m pip install -r requirements-ui.txt
# 使用已安装 Chromium；未安装时执行 .venv/bin/python -m playwright install chromium
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest tests/browser -q
```

浏览器测试通过静态 HTTP 服务器加载仓库原文件，API 延迟与失败由路由控制，绝不连接真实仿真或模型。
这些测试证明 UI 的交互隔离，不证明后端权限、执行恢复或真机仿真正确。

## 后续范围

整体优化仍可分为配置准入、执行反馈、异常恢复、证据与晋升等独立迭代；每轮先确认规格和特征基线，再改对应实现。本轮不替这些后续工作声称完成。

## 内网侧完整验收

用户已确认仿真环境和历史数据无法提供给云端；后续完整验收留在内网执行，不要求外传。使用包含本轮改动的软件副本以及**可写的测试环境副本**，不要把终验脚本指向正式运行状态。下面是待内网执行的命令，未在云端声称验证：

```bash
set -euo pipefail
# 在已应用本轮改动的软件仓根执行；替换为内网测试副本的实际路径
export LOOP_ENV_ROOT=/absolute/path/to/test-environment-copy
# 放在环境副本内以满足现有冻结见证测试的布局假设
export LOOP_WORKSPACE="$LOOP_ENV_ROOT/kb"
export LOOP_LLM_MODE=standin
test -f "$LOOP_ENV_ROOT/uvs.setup"
test -d "$LOOP_WORKSPACE/baselines/v0"
test -d "$LOOP_WORKSPACE/index"
test -d "$LOOP_WORKSPACE/conflicts"
test -d "$LOOP_WORKSPACE/runs/RUN-20261015-120626"

cd loop
# 先按内网依赖分发流程安装 requirements-ui.txt 与 Chromium；不关闭 TLS/包校验
# 逐项检查退出码，失败时停止并诊断，不继续累计“通过”
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest tests/browser -q
flock /tmp/cic_loop_pytest.lock .venv/bin/python -m pytest tests --ignore=tests/browser -q
cd ..
loop/.venv/bin/python kb/tools/_selftest_gate_schema.py
loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py
# 先停测试副本的服务，确认无其它测试或作业共用 loop/state；此脚本会删除运行时状态
(cd loop && LOOP_PORT=8098 bash spikes/accept_v1_run.sh)
loop/.venv/bin/python doc/audit/check_doc_links.py
```

离线替身闭环通过仍不代表真机全跑完成。真实仿真必须另外确认工具链、许可证、模型配置和独占时间窗，按既有真机流程验收。证据新增落档，不修改本轮已冻结的云端验证记录。
