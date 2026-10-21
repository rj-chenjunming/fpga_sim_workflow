# Agent 上下文与记忆优化复核

> 本轮是否修复：**是**。先按用户要求更新 SpecDD 流程与契约，再固定特征、执行失败用例并实现。
> 本轮同一执行者顺序实现与验证，不声称独立复核。数字以 [STATUS §8](../STATUS.md) 为准。

## 问题、落点与验收

| 问题 | 本轮修正 | 对应行为测试 |
|---|---|---|
| 差异条数/字段长度静默截断 | N3 提供全部差异及 before/after；源缺失或结构错误在 real 调用前失败 | `test_n3_all_diffs_and_full_values_are_sent`、`test_n3_missing_or_invalid_context_fails_before_provider` |
| 同一用例多个修订点只提供首处片段 | N6 提供全部 excerpts，保留兼容字段；提示词与 Schema 描述同步 | `test_author_sees_distant_revision_points_in_same_case` |
| API 文本截断及跨轮正/负缓存陈旧 | 提供完整已解析定义；缓存限制在本次构造，下一轮重读 | `test_all_resolved_apis_include_complete_large_definition`、`test_author_api_facts_refresh_between_calls` |
| 长文件尾部修改/删除不可见 | N8 用原件与沙箱的实际差异定位全部变更前后片段；缺来源时不猜测大文件范围 | `test_n8_large_tail_changes_and_deletions_have_before_after`、`test_large_n8_without_source_fails_before_provider` |
| 上下文无统一预算 | 请求整体 UTF-8 大小检查，超限先记录错误再拒绝，不发模型请求 | `test_context_budget_rejects_without_truncation_or_provider` |
| 模型调用只有当前状态和粗摘要 | 按 run/node/attempt 独占分配只读 request/result 与 SHA-256；输出记录引用与核验 CLI | `test_trace_preserves_requests_results_and_reserves_new_attempt`、`test_new_process_reserves_attempt_without_reusing_previous_files`、`test_verify_cli_checks_integrity_without_printing_input` |
| 失败、替身、取消和存储异常易混为成功 | 分别记录状态；落盘失败阻止继续消费；已知认证值不进入异常记录 | `test_trace_failure_and_standin_are_not_validated`、`test_cancelled_call_is_recorded_as_interrupted`、`test_result_write_failure_does_not_return_model_output`、`test_configuration_error_does_not_store_authentication_value` |
| 跨运行经验缺乏适用范围与来源规则 | 人工确认目录只读；精确匹配环境/基线/事实/规则，复验来源指纹与路径；拒用有诊断 | `test_only_approved_matching_experience_is_consumed_and_never_written`、`test_inapplicable_experiences_are_excluded_with_diagnostics` |

测试入口：[独立测试](../../loop/tests/test_agent_context_memory.py)。规格：[AGENT_CONTEXT_SPEC](../spec/AGENT_CONTEXT_SPEC.md)；计划：[本轮计划](../plans/2026-10-21-agent-context-memory.md)。

## 回归边界

上轮未提交的 UI 改动与冻结证据保留。扩展回归使用独立临时执行目录让既有 subprocess 工具能获得合法 cwd；目录没有仿真资产、基线或归档，因此不被当作真实环境替代品。
再将 HEAD 加上上轮 UI 补丁解包到临时测试快照，运行同一组既有测试，确认本轮剩余的历史夹具失败在原实现也存在。没有创建 Git worktree、改原历史夹具或修改这些断言来消除失败。

两个既有 N3 测试仅补齐其隔离场景的有效差异输入，原“无 live provider 失败”和“校验失败终止”的断言保持不变；真实缺输入已有新增先失败测试覆盖。

## 保留限制

- 审批字段与文件指纹是单机流程与完整性机制，不是多用户认证或不可抵赖签名。
- 核验记录只证明文件与所记指纹一致；不重发模型调用，也不能证明模型语义正确。
- 经验是保守匹配的人工建议，不能替代当前证据或变更业务判定；自动学习与经验 UI 未实现。
- API 定义仍是文本提取，完整 SystemVerilog 语义需要原有编译/仿真与内网验收。
- 内网环境、历史夹具与真实模型质量不在云端验证结论内；kb 原归档兼容、全链端到端及全库零断链门仍未满足。

本轮冻结证据：[AGENT_CONTEXT_MEMORY_20261021.md](../evidence/AGENT_CONTEXT_MEMORY_20261021.md)（MD5 `ee9d296a736ac2b354104a078caa34df`）。
