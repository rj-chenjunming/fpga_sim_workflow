/**
 * S7b 工具白名单薄插件（人工裁决 B2 / 2026-10-29；REV-14 D4、SPEC-08 §5/§10 D03）。
 *
 * 为什么需要它：0.2.1-rc.2 的 harness 把全部工具（真机实测 26 项，含 `web_search`/`web_fetch`/
 * `subagent`/`workflow`）都给模型，而 `SETTINGS` 里没有任何"工具 allow/deny"的廉价键
 * （STATUS §115.6 / DSH_C2 证据 P1）。本插件用 dsh 的**派发前钩子**把"清单外调用"显式拒掉。
 *
 * 边界（谁判什么）：
 * - **判据只有一份**：允许/拒绝清单来自 Host 渲染的环境变量 `DSH_TOOL_ALLOWLIST`
 *   （`dsh_allowlist.render_env` 是唯一编码实现）；本插件**不解析 SETTINGS**、不猜默认值；
 * - **显式拒绝**：返回 `{kind:'deny', reason, info}`（`dsh-tools/lib/types/index.d.ts:445-455`
 *   的 `PreToolDecision`）。`reason` 是模型面文本（指出工具名 + 允许面），
 *   `info` = `{name, code}` 是机器可判身份（`ToolErrorInfo`，index.d.ts:377-385），
 *   模板取自引擎自己的 `tool-timeout-policy`（`info.name` 是错误类名、`info.code` 是稳定 code）；
 * - **不是静默丢弃**：被拒调用拿到 `isError=true` 的 tool_result + 可读原因，模型能改道；
 * - **不碰效果隔离**：不收窄沙箱、不注工具、不改 preset；白名单不是沙箱（REV-14 A8）；
 * - **不缩可见面**：`tools.restrict()` 只接受**带 agent 作用域**的 ctx
 *   （`dsh-tools/lib/index.js:2991-2993` 显式抛错），全局收窄不可能 ⇒ 本插件只做"可见但不可用"。
 *
 * 配置传递（取证见 §接线契约）：env `DSH_TOOL_ALLOWLIST`（compact JSON），
 * 因为 `dsh_process.build_env` 是唯一 env 白名单、attempt 内 env 由 Host 独占设置，
 * 而 patch 的 `config:` 是整块替换、坏形状只会在启动时出一条 `did not activate` warning。
 *
 * 生效状态通过 cordis 服务 `s7ToolAllowlist` 发布给自检插件：**自检必须回显"插件真的激活了"**，
 * 而不是靠 env 存在性猜（插件加载失败不阻断启动，见 REV-14 B2）。
 */

import { scopeOf } from '@deepseek-ai/dsh-scope'

export const name = 's7b-tool-allowlist'
export const inject = ['tools']

/** 策略 env（与 `dsh_allowlist.CONFIG_ENV` 逐字一致；两份都是常量，单测比对） */
export const CONFIG_ENV = 'DSH_TOOL_ALLOWLIST'
/** 取证工具名覆盖（与 `dsh_allowlist.PROBE_ENV` 逐字一致） */
export const PROBE_ENV = 'DSH_TOOL_ALLOWLIST_PROBE'
/** 生效状态服务名（与 `dsh_allowlist.STATE_SERVICE` 逐字一致） */
export const STATE_SERVICE = 's7ToolAllowlist'
/** 可判拒绝身份（与 `dsh_allowlist.DENY_CODE` / `DENY_NAME` 逐字一致） */
export const DENY_CODE = 'TOOL_NOT_ALLOWLISTED'
export const DENY_NAME = 'ToolNotAllowedError'

/** 配置允许的键（与 `dsh_allowlist.CONFIG_KEYS` 一致）：多一个就当坏配置 */
const CONFIG_KEYS = ['enabled', 'allowed', 'accept_bash', 'enforce_visibility']

function diagnose(message) {
  // stdout 是 headless NDJSON 协议面（多一行就成坏帧）；诊断只走 stderr
  try {
    process.stderr.write(`[${name}] ${String(message).replace(/\s+/g, ' ').slice(0, 500)}\n`)
  } catch {
    /* 诊断写不了也不影响拒绝判据 */
  }
}

function errorText(err) {
  if (err && typeof err === 'object' && 'message' in err) return String(err.message || err)
  return String(err)
}

/**
 * 解析 Host 渲染的配置。**不猜**：坏配置返回 `{config: null, error}`，调用方 fail-closed。
 * - 变量缺失/空 ⇒ `{config: null, error: null}` = 开关关（不该被挂上来，但挂了也不能放开）；
 * - 非 JSON / 非对象 / 未知键 / `enabled` 非布尔 / `allowed` 非字符串数组/空 ⇒ error。
 */
export function parseConfig(text) {
  if (text === undefined || text === null || String(text).trim() === '') {
    return { config: null, error: null }
  }
  let parsed
  try {
    parsed = JSON.parse(String(text))
  } catch (err) {
    return { config: null, error: `配置不是合法 JSON（${errorText(err)}）` }
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { config: null, error: `配置必须是 JSON 对象（实际 ${Array.isArray(parsed) ? 'array' : typeof parsed}）` }
  }
  const unknown = Object.keys(parsed).filter((key) => !CONFIG_KEYS.includes(key))
  if (unknown.length > 0) {
    return { config: null, error: `配置含未知键：${JSON.stringify(unknown)}` }
  }
  if (typeof parsed.enabled !== 'boolean') {
    return { config: null, error: `配置的 enabled 必须是布尔（实际 ${typeof parsed.enabled}）` }
  }
  if (!Array.isArray(parsed.allowed)) {
    return { config: null, error: `配置的 allowed 必须是数组（实际 ${typeof parsed.allowed}）` }
  }
  const allowed = []
  for (const entry of parsed.allowed) {
    if (typeof entry !== 'string' || entry.trim() === '') {
      return { config: null, error: `配置的 allowed 里有非字符串/空项：${JSON.stringify(entry)}` }
    }
    if (allowed.includes(entry)) {
      return { config: null, error: `配置的 allowed 里 ${JSON.stringify(entry)} 重复` }
    }
    allowed.push(entry)
  }
  if (parsed.enabled && allowed.length === 0) {
    return { config: null, error: '配置启用但 allowed 为空（所有工具都会被拒，提交通道也断）' }
  }
  if (parsed.accept_bash !== undefined && typeof parsed.accept_bash !== 'boolean') {
    return { config: null, error: `配置的 accept_bash 必须是布尔（实际 ${typeof parsed.accept_bash}）` }
  }
  if (parsed.enforce_visibility !== undefined && typeof parsed.enforce_visibility !== 'boolean') {
    return { config: null, error: `配置的 enforce_visibility 必须是布尔（实际 ${typeof parsed.enforce_visibility}）` }
  }
  return {
    config: {
      enabled: parsed.enabled,
      allowed,
      enforceVisibility: parsed.enforce_visibility === true,
    },
    error: null,
  }
}

/** 注册表**可见面**（`ctx.tools.schemas()`，全局视图）；取不到/为空 ⇒ null（调用方 fail-closed）。
 *
 * 为什么"空"也算不可用：boot 早期注册表还没就绪（自检实测 `toolNames=[]`）。若把空面当
 * "已知面"就会把每次调用误判成拼写错误而放行 ⇒ 白名单在最需要它的时刻失效。
 */
function surfaceNames(ctx) {
  try {
    if (typeof ctx.get !== 'function') return { names: null, error: 'ctx.get 不可用' }
    const tools = ctx.get('tools')
    if (!tools || typeof tools.schemas !== 'function') {
      return { names: null, error: 'ctx.tools.schemas 不可用' }
    }
    const schemas = tools.schemas()
    if (!Array.isArray(schemas)) {
      return { names: null, error: `schemas() 返回 ${typeof schemas}（不是数组）` }
    }
    const names = schemas.map((s) => (s && typeof s.name === 'string' ? s.name : null))
    if (names.some((n) => n === null)) {
      // 面不可信就整份不认（fail-closed）：半张清单会把"漏读的工具"误判成拼写错误而放行
      return { names: null, error: 'schemas() 里有条目缺 name（可见面不可信）' }
    }
    if (names.length === 0) {
      return { names: null, error: '工具清单为空（注册表可能尚未就绪）' }
    }
    return { names, error: null }
  } catch (err) {
    return { names: null, error: `schemas() 抛错：${errorText(err)}` }
  }
}

export function apply(ctx) {
  const { config, error } = parseConfig(process.env[CONFIG_ENV])
  const enabled = error === null && config !== null && config.enabled === true
  const allowed = config ? [...config.allowed] : []
  const allowedSet = new Set(allowed)
  const enforceVisibility = enabled && config.enforceVisibility === true
  //: 可见面收窄的运行时事实（`enforce_visibility` 打开时由 `agent/created` 填）
  let agentScope = null

  if (error) diagnose(`配置无效：${error}（按 fail-closed 拒绝一切工具调用）`)
  if (!enabled && !error) {
    diagnose(`未启用（缺 ${CONFIG_ENV} 或 enabled=false）：不注册拒绝判据（= S6 现状）`)
  }

  const denyReason = (toolName) => {
    if (error) {
      return `工具 ${JSON.stringify(toolName)} 被拒绝：本 attempt 的工具白名单配置无效`
        + `（${error}），按 fail-closed 拒绝一切工具调用。请报告该配置错误。`
    }
    return `工具 ${JSON.stringify(toolName)} 不在本 attempt 的工具白名单内；`
      + `允许的工具：${allowed.join(', ')}。请改用允许的工具完成任务。`
  }

  const deny = (toolName) => ({
    kind: 'deny',
    reason: denyReason(toolName),
    info: { name: DENY_NAME, code: DENY_CODE, reason: `tool=${toolName}` },
  })

  if (enforceVisibility) {
    // **可选第二层**：按 agent 作用域收窄**可见面**（模型看不到清单外的工具）。
    // 为什么只能按作用域：`tools.restrict()` 只接受带 agent 作用域的 ctx
    // （`dsh-tools/lib/index.js:2991-2993` 显式抛错），全局收窄不可能；官方用法见
    // `dsh-subagent/lib/index.js:395`（`childCtx.tools.restrict(composition.toolFilter)`）。
    // 为什么放在 `agent/created`：该事件在 agent 创建完成、模型请求之前 **await** 完
    // （`dsh-agent/lib/types/runtime-types.d.ts:227-233`）⇒ 第一个请求就已收窄。
    // **绝不抛**：该 listener 抛错会让 agent 创建失败（同一处文档）⇒ 只记录失败，让 Host 显式失败。
    ctx.on('agent/created', (payload) => {
      try {
        const agent = payload && payload.agent
        const agentCtx = agent && agent.ctx
        if (!agentCtx || !agentCtx.tools || typeof agentCtx.tools.restrict !== 'function') {
          agentScope = { attempted: true, names: null,
                         error: 'agent.ctx.tools.restrict 不可用（收窄可见面失败）',
                         at: new Date().toISOString() }
          return
        }
        const surface = surfaceNames(ctx)
        if (surface.names === null) {
          agentScope = { attempted: true, names: null,
                         error: `收窄可见面前拿不到工具面：${surface.error}`,
                         at: new Date().toISOString() }
          return
        }
        // restrict 的名字必须是**已知全局工具**（未知名/空过滤器都会抛）⇒ 取交集
        const allow = surface.names.filter((toolName) => allowedSet.has(toolName)).sort()
        if (allow.length === 0) {
          agentScope = { attempted: true, names: null,
                         error: '清单与全局可见面无交集：无可收窄的过滤器',
                         at: new Date().toISOString() }
          return
        }
        agentCtx.tools.restrict({ allow })
        // 读**作用域视图**：`schemas()` 省略 scope = **全局视图**（不会反映限制），
        // 必须显式给 scope key。key 取自 `scopeOf(agentCtx)`，与官方投影一致
        // （`dsh-cordis-host-runner/lib/index.js:582`：`ctx.tools.schemas(scopeOf(ctx))`）。
        const key = scopeOf(agentCtx)
        const scoped = agentCtx.tools.schemas(key).map((s) => s.name).sort()
        agentScope = { attempted: true, allow, names: scoped, error: null,
                       at: new Date().toISOString() }
      } catch (err) {
        agentScope = { attempted: true, names: null,
                       error: `收窄可见面抛错：${errorText(err)}`,
                       at: new Date().toISOString() }
      }
    })
  }

  if (enabled || error) {
    // `tools/pre-execute` 是**派发前** waterfall（index.d.ts:38-47）；返回 deny 即短路。
    // 全局 listener（本 ctx 无 agent 作用域）收到所有 agent 的调用。
    ctx.on('tools/pre-execute', (exec, next) => {
      const toolName = exec && typeof exec.name === 'string' ? exec.name : ''
      if (!error && !enabled) return next()
      if (!error && allowedSet.has(toolName)) return next()
      if (!error) {
        // 清单外的**已注册**工具才算越权；拼写错误保留引擎的 UNKNOWN_TOOL 语义
        const surface = surfaceNames(ctx)
        if (surface.names !== null && !surface.names.includes(toolName)) return next()
      }
      return deny(toolName)
    })
  }

  /** 生效状态快照：**每次现算**（apply 期注册表可能还没就绪，缓存会给出陈旧结论）。 */
  const snapshot = () => {
    const surface = surfaceNames(ctx)
    const base = {
      plugin: name,
      applied: true,
      enabled,
      allowed,
      acceptBash: config ? config.accept_bash !== false : null,
      enforceVisibility,
      agentScope,
      configError: error,
      service: STATE_SERVICE,
      readAt: new Date().toISOString(),
    }
    if (surface.names === null) {
      return { ...base, toolCount: null, toolError: surface.error,
               effective: null, denied: null, unknownAllowed: null }
    }
    const effective = surface.names.filter((n) => allowedSet.has(n)).sort()
    const denied = surface.names.filter((n) => !allowedSet.has(n)).sort()
    const unknownAllowed = allowed.filter((n) => !surface.names.includes(n)).sort()
    return { ...base, toolCount: surface.names.length, toolError: surface.error,
             effective, denied, unknownAllowed }
  }

  // 发布给自检：自检据此回显"插件真的激活了 + 生效面是什么"，而不是读 env 猜。
  ctx.provide(STATE_SERVICE, {
    plugin: name,
    enabled,
    allowed,
    enforceVisibility,
    configError: error,
    snapshot,
  })
}
