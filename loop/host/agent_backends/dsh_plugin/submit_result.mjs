// S2-a 提交工具（SPEC-REV-14 B1 / DS-02）：`--patch` insert 挂进 attempt 的 ESM 薄插件。
//
// 边界（谁判什么）：
// - **handler 不校验业务**：它只证明"引擎已收到这次提交"。返回的
//   `accepted: true` 的语义是"引擎已接收"，**不是**"业务通过"；
// - 业务通过与否的唯一实现是 Host 的 `loop/workflows/chunks/model_steps.py::_validate`，
//   本插件不复制判据、不猜结论；
// - **不写侧信道**：提交事实由 headless NDJSON 的 `tool_call`/`tool_result` 帧承载
//   （Host 的 `dsh_protocol.require_submission` 收口），插件不再落一份没有消费者的文件
//   （AGENTS §2.4：没有消费者的产物不得保留；独立复核 P2-5）。
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 's2-submit-result'
export const inject = ['tools']

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'submit_result',
    description: '提交本次任务的最终结构化结果。task_id 必须逐字等于任务里给出的 attempt 标识，'
      + 'payload 必须符合任务里给出的 schema；未提交或提交未被接收时任务按失败处理。',
    parameters: {
      task_id: { type: 'string', required: true, description: '本次 attempt 标识（逐字复制任务里的 task_id）' },
      summary: { type: 'string', required: true, description: '一句话结论' },
      payload: { type: 'json', description: '结构化成果：**必须是 JSON 对象**（直接把对象传进来；'
        + '不要传字符串化后的 JSON —— 字符串会被 Host 提交门以 BadSubmission 拒绝）。'
        + '内容必须符合任务里给出的 schema。' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(_args) {
      // accepted 的语义是"引擎已接收"（不是业务通过）；业务判据只由 Host 的 _validate 决定。
      return JSON.stringify({ accepted: true, problems: [] })
    },
  }))
}
