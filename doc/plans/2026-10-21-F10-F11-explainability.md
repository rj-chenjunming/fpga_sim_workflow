# F10 / F11（前半）上下文与尝试的只读可解释性 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F10（上下文/经验可解释）与 F11 前半
> （尝试摘要、输入/输出差异；分页契约仍受 F07 测量限制）。
> 原则：**只读展示，不改变筛选/预算结果**；未知 token 保持未知；不新增模型调用。

| 项 | 内容 |
|---|---|
| 类型 | 只读可解释性（UI + 纯函数展示层；不改 Host 判据） |
| 基线提交 | `792bb48` |
| 唯一 owner | 上下文 owner（展示）+ UI owner |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [AGENT_WINDOW_SPEC](../spec/AGENT_WINDOW_SPEC.md) 新增「可解释性」；[AGENT_CONTEXT_SPEC C1/M1/M2] 只读约束 |
| 允许修改 | `loop/web/`（新增 context-explain.js；改 agent-window.js/index.html）、`loop/tests/`（node 判据）、`doc/spec/AGENT_WINDOW_SPEC.md`、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | 预算/经验筛选判据、`request.json` 内容、API 契约、`kb/**`、冻结证据 |

## 1 问题

Agent 窗口能看到输入/结果，但用户无法回答：
- 这次请求的字节预算由哪些部分构成？离上限还有多少？
- 哪条人工确认经验被采用/被拒？原因是什么？
- 多个 attempt 之间输入差异在哪？（排障时需要“为什么这次不一样”）
- token 预估没有测量依据 ⇒ 必须保持未知，不能用字符数冒充。

## 2 目标可观察行为

1. 预算构成：按记录里的 `request` 字段（input/prompt/info/instruct/schema）展示各部分的 UTF-8 字节与占比；
   总量与 `MAX_CONTEXT_BYTES` 并列展示（来自记录事实，不重新发请求）。
2. 经验解释：展示 `experience_diagnostics`（采用/拒绝原因），只读且不改变筛选结果。
3. 尝试摘要：attempt 列表带 status/model/cycle；选中某次时显示它与上一条可比较尝试的输入差异
   （变化的顶层字段 + 字节变化），相同则明确「无差异」。
4. token 估算：没有测量依据 ⇒ 显示「未知（未测量）」，不得用字节数折算冒充 token。
5. 展示不会导致额外模型请求、不会改写任何记录；未知/缺字段显示「未知」。

## 3 不变量

1. 纯函数展示层（`web/context-explain.js`）不读全局、不发请求、不写 DOM；未知保持未知。
2. Host 判据零变化：预算检查、经验筛选、调用记录格式都不改。
3. 窗口关闭/切换不改变任何记录；展示失败不影响观察基本状态。
4. 只用 `textContent` 渲染字符串（禁止 innerHTML）。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F10/F11-1 | 规格「可解释性」+ 本计划 | 文档门 |
| F10/F11-2 | 红灯：`tests/test_context_explain.py`（node 纯函数：字节/占比/经验原因/尝试差异/未知） | 先红 |
| F10/F11-3 | 实现：模块 + 窗口两处只读区块；无新增请求 | 定向 + `node --check` + web smoke |
| F10/F11-4 | 独立复核报告（`doc/audit/`，只读子代理） | 展示不改变判据；md5 记入 STATUS |
| F10/F11-5 | STATUS §32 | 命令/输出逐字复制；浏览器未运行单列 |

**未完成**：F11 的筛选/完整历史导航依赖 F07 分页契约（本轮测量未达阈值，不引入分页）；
F10 的 provider token 预检需要真实 provider 能力，未测量前不做。浏览器渲染未验证（缺 playwright）。

## 5 回退

移除两个只读展示区块与模块即可；记录与判据不变。
