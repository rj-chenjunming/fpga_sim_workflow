# F02 能力说明与实际状态对齐 · 切片计划

> 承接 [优化与重构执行手册](OPTIMIZATION_PLAYBOOK.md) 批次 A 的 F02（P1/缺陷）。只登记本切片的规格、落点、验收与实测；数字只回填 [STATUS](../STATUS.md)。

| 项 | 内容 |
|---|---|
| 类型 | 缺陷修复（提示漂移）+ 投影字段增强 |
| 基线提交 | `fb83ed0`（实现期）／`7731f96`（F01 已归档） |
| 唯一 owner | 服务投影 owner（服务端事实）＋ UI owner（消费同一来源）；本切片由 Lead 实现并自测，**未指派独立验证者** |
| 规格位置 | [Web UI §4.3 能力事实](../spec/WEB_UI_SPEC.md)、§7 第 6 条、§10-A9 |
| 允许修改 | `loop/services/agent_view.py`、`loop/web/app.js`、`loop/tests/test_agent_view.py`、`loop/tests/browser/test_web_layout.py`、`doc/spec/WEB_UI_SPEC.md`、本计划、`doc/STATUS.md` |
| 不修改 | 冻结目录 `kb/**`、`doc/evidence/**`、`doc/history/**`、执行拓扑、闸门、N11 语义 |

## 1 问题

「N11 证据守护未实现（审计 A10）」的旧结论被写在四处，而 [n11_review](../../loop/workflows/chunks/model_steps.py) 已实现成链判断/返工/身份四方同值：

1. 服务端 `agent_view.GUARDIAN_NOTE` 与 guardian idle 时的 `summary`；
2. 前端 `app.js::deriveNote` 的兜底文案；
3. 规格 §4.3「已知缺口」与 §7 第 6 条；
4. `tests/test_agent_view.py::test_guardian_reports_known_gap` 把旧结论当成契约。

同时 UI 从 `idle` 推断能力、`standin` 与真实执行混在同一个 `mode` 字符串里，无法区分「实现存在 / 依赖齐备 / 本次执行方式 / 验证范围」。

## 2 目标可观察行为

- 每张卡带 `capabilities = {implemented, dependencies_ready, execution, verification_scope}`：
  `implemented` 为布尔；`dependencies_ready`/`verification_scope` 未知时为 `null`；
  `execution ∈ {not_started, standin, real, unknown}`。
- `idle` 只表示「本次尚未开始」：guardian idle 的摘要为「待命」，任何文案不得出现「未实现」。
- `standin` 不得被显示成真实完成；`live/real` 映射为 `real`。
- UI 只消费服务端字段；本地派生卡（服务端无该角色）显式标注「能力事实未知」。

## 3 不变量

1. **单一事实源**：能力事实只由服务端 `agent_view` 计算；前端不得再从状态/颜色推断。
2. **未知保持未知**：没有 provider/UVS/夹具探针的维度写 `null`，不用 `false` 冒充。
3. **向后兼容**：新增字段只增不改，旧客户端仍可读 `status/summary/mode`。
4. **不夸大验证**：`verification_scope` 未知即 `null`，不声称真实模型或真机已验证。

## 4 切片与验证

| 切片 | 内容 | 验证 |
|---|---|---|
| F02-a | 规格 §4.3/§7-6/§10-A9 | 文档链接与锚点可达 |
| F02-b | 失败用例：idle 不得「未实现」、四维字段、standin/real 区分 | 先红 `3 failed, 7 passed` |
| F02-c | 服务端 `_capabilities()` + 文案；前端 `capabilityLine()` 渲染 | 单测转绿；`node --check` |
| F02-d | 浏览器断言（有 Chromium 的环境执行） | 本机**未运行**（见 §5） |

## 5 实测（数字从命令输出复制）

| 验证 | 原始输出 | 结论 |
|---|---|---|
| 修改前红灯 | `3 failed, 7 passed in 0.64s` | 旧实现无 `capabilities`、guardian 文案含「未实现」 |
| 修改后单测 | `10 passed in 0.54s` | 四维事实/idle 文案/standin-real 区分 |
| 浏览器用例收集 | `10 passed, 3 skipped in 0.58s` | 浏览器模块因缺 playwright 整组 skip |
| 全套单测 | `46 failed, 271 passed, 3 skipped, 1 warning` | 46 项与拉取后基线同因（`ENV_ROOT` 只读），无新增回归 |
| 前端语法 | `node --check web/app.js` 通过 | 仅证明可加载，不替代浏览器行为 |

**未运行**：`tests/browser` 的真实 Chromium 断言（本机 `pip install playwright` 无网络到 PyPI、
系统无 Chromium）。因此本轮**不声称** UI 已在浏览器中验证；新增用例留给具备 Chromium 的环境执行。

## 6 回退

还原 `agent_view._capabilities` 与前端 `capabilityLine` 即可；`status/summary/mode` 等旧字段保持可读，历史审计记录不回填。
