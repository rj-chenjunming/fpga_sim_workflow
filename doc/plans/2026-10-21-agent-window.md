# Agent 工作窗口实施计划

契约：[Agent 工作窗口](../spec/AGENT_WINDOW_SPEC.md)。同一实现者分阶段验证，不声称独立复核。

| 顺序 | 唯一 owner / 落点 | 验证 |
|---|---|---|
| 特征基线 | 模型调用、记录、Agent 投影、UI 会话 | 改实现前通过 |
| 局部提取 | model_steps.py 单次请求函数 | 保持返回值、校验、记录 |
| 控制边界 | Host agent_control.py + 请求包装 | 先失败用例，真实取消/重发、旧结果不消费、任务不重叠 |
| API | services/api.py | 固定范围读取与核验、命令身份/过期拒绝 |
| 窗口 | web/agent-window.js + app.js / HTML / CSS | 浏览器交互、回包隔离、表单不重建 |
| 证据 | STATUS + 新增冻结证据 | 受影响及扩展回归、文档门，明确内网限制 |

不改 kb 闸门或执行拓扑，不新增 agent 调度器。暂停只在当前进程模型请求边界生效，重启后旧窗口只读；不伪装 durable interrupt。保留已有 S0、Agent 记忆和闸门 UI 变化。
