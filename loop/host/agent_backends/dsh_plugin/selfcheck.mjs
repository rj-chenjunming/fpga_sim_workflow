/**
 * S2 启动自检插件（SPEC-REV-14 B2/B3、DS-08/DS-09；计划 §3.2）。
 *
 * 为什么需要它：dsh 的插件/工具加载失败**只出** `dsh: warning: 1 entry did not activate`，
 * 不阻断启动（P2 实测）⇒ "进程起来了"不能当准入。Host 必须在派发前拿到**运行时事实**：
 * 注册表里到底有哪些工具、部署的 sandbox 默认档是什么、permission preset 回显是什么。
 *
 * 边界：
 * - 只**读**运行时事实并落盘，不改策略、不注工具、不碰业务判据；
 * - 落盘位置 `$DSH_SELFCHECK_DIR/selfcheck.json`（attempt 目录内，bwrap 已 bind 回来）；
 * - **绝不写 stdout**（stdout 是 headless NDJSON 协议面，多一行就成坏帧）；诊断只走 stderr 且脱敏；
 * - 拿不到的事实写 null/unknown + reason，**不编造**（计划 §6-1）。
 *
 * 落盘时机：`apply` 时写 `phase:'apply'`（**诊断用**：那时工具注册表与服务可能还没就绪），
 * 之后**轮询到就绪**（工具清单非空 + 沙箱档取到 + preset 回显非 unknown
 * [+ 白名单启用时：生效面 + deny 取证]）再写 `phase:'deferred'`（**准入用**）；
 * 最长 5 s，超时仍写（Host 会显式失败）。Host 只认 `phase:'deferred'`；
 * 只有 apply 快照到达超时 ⇒ 显式失败（不可能拿它当准入）。
 *
 * S7b 增补（工具白名单，人工裁决 B2）：本插件**回显**白名单生效状态与有效工具面，
 * 并对"清单外工具"做**一次真派发取证**（`allowlist.probe`）——理由：白名单插件加载失败
 * 同样只出一条 warning，不阻断启动；"插件文件存在 / env 里有配置"都不能证明拒绝真的生效。
 * 取证只调**只读、无害**的工具（被拒时工具体不会执行；万一白名单失效，这个工具也不会改状态）。
 */

import { mkdirSync, renameSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

export const name = 's2-selfcheck'
export const inject = ['tools']

const PLUGIN = 's2-selfcheck'
const REPORT_FILE = 'selfcheck.json'
const REPORT_ENV = 'DSH_SELFCHECK_DIR'
// 每次 attempt 的随机 nonce / attempt 标识：写进报告供 Host 逐字比对 ——
// 复用同一 attempt root 时，没有它们 Host 会把"上一次"的快照当本次准入（复核 P1-1）。
const NONCE_ENV = 'DSH_SELFCHECK_NONCE'
const ATTEMPT_ENV = 'DSH_ATTEMPT_KEY'
// S7b：白名单插件发布生效状态的服务名（与 `dsh_allowlist.STATE_SERVICE` 逐字一致）。
// 读服务而不是读 env：服务存在 = 插件**真的激活了**（env 存在只说明 Host 写了配置）。
const ALLOWLIST_SERVICE = 's7ToolAllowlist'
const ALLOWLIST_KEY = 'allowlist'
const ALLOWLIST_PROBE_ENV = 'DSH_TOOL_ALLOWLIST_PROBE'
//: 取证候选：只读、无副作用的工具（被拒时工具体不执行；万一白名单失效也不会改状态）
const PROBE_CANDIDATES = ['job_list', 'get_goal', 'list_agents']
const PROBE_TIMEOUT_MS = 2000

/** 只写 stderr 的一行脱敏诊断（stdout 是协议面）。 */
function diagnose(message) {
  try {
    process.stderr.write(`[${PLUGIN}] ${String(message).replace(/\s+/g, ' ').slice(0, 500)}\n`)
  } catch {
    /* stderr 也写不了就只能放弃诊断，绝不影响启动路径 */
  }
}

function errorText(err) {
  if (err && typeof err === 'object' && 'message' in err) {
    return String(err.message || err)
  }
  return String(err)
}

/** 把 ctx 上可能拿不到的服务取成 {service, reason}（不抛）。 */
function service(ctx, key) {
  try {
    if (typeof ctx.get !== 'function') return { service: null, reason: 'ctx.get 不可用' }
    const value = ctx.get(key)
    if (!value) return { service: null, reason: `ctx.get(${JSON.stringify(key)}) 返回空` }
    return { service: value, reason: null }
  } catch (err) {
    return { service: null, reason: `ctx.get(${JSON.stringify(key)}) 抛错：${errorText(err)}` }
  }
}

/** B2：注册表可见的工具名（`ctx.tools.schemas()`）；取不到就 null + reason。 */
function toolNames(ctx) {
  const { service: tools, reason } = service(ctx, 'tools')
  if (!tools) return { toolNames: null, toolError: reason }
  try {
    const schemas = tools.schemas()
    if (!Array.isArray(schemas)) {
      return { toolNames: null, toolError: `ctx.tools.schemas() 返回 ${typeof schemas}（不是数组）` }
    }
    const names = schemas.map((s) => (s && typeof s.name === 'string' ? s.name : null))
    if (names.some((n) => n === null)) {
      return { toolNames: names.filter((n) => n !== null), toolError: 'schemas() 里有条目缺 name' }
    }
    return { toolNames: names, toolError: null }
  } catch (err) {
    return { toolNames: null, toolError: `ctx.tools.schemas() 抛错：${errorText(err)}` }
  }
}

/** B3 的一半：沙箱默认档（`ctx.sandboxPolicy.defaultMode`）。 */
function sandboxMode(ctx) {
  const { service: policy, reason } = service(ctx, 'sandboxPolicy')
  if (!policy) return { sandboxDefaultMode: null, sandboxModeError: reason }
  try {
    const mode = policy.defaultMode
    if (typeof mode !== 'string' || !mode) {
      return { sandboxDefaultMode: null, sandboxModeError: `defaultMode 非字符串（${typeof mode}）` }
    }
    return { sandboxDefaultMode: mode, sandboxModeError: null }
  } catch (err) {
    return { sandboxDefaultMode: null, sandboxModeError: `defaultMode 读取抛错：${errorText(err)}` }
  }
}

function names(options) {
  if (!Array.isArray(options)) return []
  return options.map((o) => (o && typeof o.value === 'string' ? o.value : null)).filter((v) => v !== null)
}

/**
 * B3 的另一半：permission preset 回显。
 *
 * 只用公开 API（`catalog()` / `defaultPreset` / `resolve(name)`）。apply 期**没有 session 对象**，
 * 而 `current(session)` 需要 session ⇒ session 级 preset 未回显（计划 §6-1），
 * 这里如实写 `scope: 'composition'` 并把拿到的值原样回显；实在拿不到就 `availability: 'unknown'`。
 */
function presetEcho(ctx) {
  const echo = {
    availability: 'unknown',
    scope: 'composition',
    sessionScoped: false,
    preset: null,
    api: [],
    defaultPreset: null,
    catalog: null,
    resolved: null,
    reason: null,
    resolveError: null,
    note: 'apply 期无 session 对象：session 级 preset 未回显（计划 §6-1）；此处回显 composition 默认值',
  }
  const { service: presets, reason } = service(ctx, 'permissionPresets')
  if (!presets) {
    echo.reason = reason
    return echo
  }

  try {
    if (typeof presets.catalog === 'function') {
      const catalog = presets.catalog()
      echo.api.push('catalog()')
      echo.catalog = {
        options: names(catalog && catalog.options),
        defaultOptions: names(catalog && catalog.defaultOptions),
        defaultPreset: catalog && typeof catalog.defaultPreset === 'string' ? catalog.defaultPreset : null,
      }
    }
  } catch (err) {
    echo.reason = `catalog() 抛错：${errorText(err)}`
  }

  try {
    const value = presets.defaultPreset
    if (typeof value === 'string' && value) {
      echo.defaultPreset = value
      echo.api.push('defaultPreset')
    }
  } catch (err) {
    echo.reason = `defaultPreset 读取抛错：${errorText(err)}`
  }

  // 回显值：settings/配置解析出的默认 preset 优先，其次 catalog 自报的 composition 默认
  echo.preset = echo.defaultPreset || (echo.catalog && echo.catalog.defaultPreset) || null

  if (echo.preset) {
    try {
      if (typeof presets.resolve === 'function') {
        const spec = presets.resolve(echo.preset)
        echo.api.push(`resolve(${echo.preset})`)
        echo.resolved = {
          preset: echo.preset,
          sandbox: spec && typeof spec.sandbox === 'string' ? spec.sandbox : null,
          approval: spec && typeof spec.approval === 'string' ? spec.approval : null,
        }
      }
    } catch (err) {
      // preset 名不在配置表里 ⇒ 回显「名字」有了但「档位包」拿不到：如实记，不编造
      echo.resolveError = errorText(err)
    }
    echo.availability = 'composition'
    if (!echo.reason) echo.reason = null
  } else {
    echo.reason = echo.reason || 'catalog()/defaultPreset 都没给出 preset 名'
  }
  return echo
}

/** 读白名单插件的生效状态（`ctx.get(ALLOWLIST_SERVICE)`）。
 *
 * 为什么读**服务**而不是读 env：服务存在 = 插件真的激活并跑过 `apply`；env 存在只说明
 * Host 写了配置。插件加载失败不阻断启动（B2）⇒ 只有服务能证明"拒绝判据已注册"。
 * 返回 `{state, error}`：`state === null` = 插件没挂（开关关）。
 */
function allowlistState(ctx) {
  try {
    if (typeof ctx.get !== 'function') return { state: null, error: 'ctx.get 不可用' }
    const service = ctx.get(ALLOWLIST_SERVICE)
    if (!service) return { state: null, error: null }
    const state = typeof service.snapshot === 'function' ? service.snapshot() : service
    if (!state || typeof state !== 'object') {
      return { state: null, error: `${ALLOWLIST_SERVICE}.snapshot() 返回 ${typeof state}` }
    }
    return { state, error: null }
  } catch (err) {
    return { state: null, error: `读取 ${ALLOWLIST_SERVICE} 抛错：${errorText(err)}` }
  }
}

/** 在"被拒面"里挑一个只读工具做一次**真派发取证**（异步、一次性；由 `apply` 触发）。
 *
 * 判据：清单外调用必须被**显式拒绝**。取证只认 `isError` + `error.info.code` + 可读 message；
 * 拿不到就如实写 null + reason（Host 会显式失败，不猜"应该没问题"）。
 *
 * S7b 第二个取证（`allowlistProbe` 的 `allowed` 分支）：清单**内**的一个只读工具也必须
 * 走通派发、拿到的不是白名单拒绝码。为什么需要：只有 deny 取证的话，"把一切都拒掉"的白名单
 * 同样能通过取证 —— 而那种白名单会让任务必失败。第二个取证用**空参数**派发，参数校验在
 * 工具体之前失败 ⇒ 只读工具不会真的读到/改到什么。
 */
const ALLOWED_PROBE_CANDIDATES = ['read', 'grep', 'glob']

async function dispatchProbe(ctx, name) {
  let tools = null
  try {
    tools = typeof ctx.get === 'function' ? ctx.get('tools') : null
  } catch (err) {
    tools = null
  }
  if (!tools || typeof tools.execute !== 'function') {
    return { attempted: false, name, denied: null, code: null,
             reason: 'ctx.tools.execute 不可用，无法取证' }
  }
  const signal = (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function')
    ? AbortSignal.timeout(PROBE_TIMEOUT_MS)
    : new AbortController().signal
  const callId = `${PLUGIN}-allowlist-probe-${name}-${process.pid}-${Date.now()}`
  try {
    const result = await tools.execute({ callId, name, arguments: {}, signal })
    const info = (result && result.error && result.error.info) || null
    const message = result && result.error && typeof result.error.message === 'string'
      ? result.error.message.slice(0, 500) : null
    return { attempted: true, name, denied: result ? result.isError === true : null,
             code: info && typeof info.code === 'string' ? info.code : null,
             reason: message, at: new Date().toISOString() }
  } catch (err) {
    return { attempted: true, name, denied: null, code: null,
             reason: `取证派发抛错：${errorText(err)}`, at: new Date().toISOString() }
  }
}

async function allowlistProbes(ctx, state) {
  const denied = Array.isArray(state.denied) ? state.denied : []
  const effective = Array.isArray(state.effective) ? state.effective : []
  const override = String(process.env[ALLOWLIST_PROBE_ENV] || '').trim()
  const denyName = override || PROBE_CANDIDATES.find((candidate) => denied.includes(candidate))
    || denied[0] || null
  const allowedName = ALLOWED_PROBE_CANDIDATES.find((candidate) => effective.includes(candidate))
    || null
  const probe = denyName
    ? await dispatchProbe(ctx, denyName)
    : { attempted: false, name: null, denied: null, code: null,
        reason: '被拒面为空：没有可取证的工具（白名单可能没收到清单）' }
  const allowedProbe = allowedName
    ? await dispatchProbe(ctx, allowedName)
    : { attempted: false, name: null, denied: null, code: null,
        reason: '生效面里没有可用的只读取证工具（read/grep/glob 都不在清单里）' }
  return { probe, allowedProbe }
}

/** 把"白名单状态 + 两份取证"合成回显（`probes` 由异步取证填入；缺失就是缺失，不编造）。 */
function allowlistEcho(ctx, probes) {
  const { state, error } = allowlistState(ctx)
  const probe = probes ? probes.probe : null
  const allowedProbe = probes ? probes.allowedProbe : null
  if (state === null) {
    return error === null ? null : { plugin: null, error, probe, allowedProbe }
  }
  return { ...state, probe: probe || null, allowedProbe: allowedProbe || null }
}

/** 从 CLI argv 里取 `--patch <path>`（运行时事实：本次真挂了哪些 overlay）。 */
function patchesFromArgv(argv) {
  const found = []
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--patch' && i + 1 < argv.length) {
      found.push(String(argv[i + 1]))
    } else if (typeof arg === 'string' && arg.startsWith('--patch=')) {
      found.push(arg.slice('--patch='.length))
    }
  }
  return found
}

function collect(ctx, phase, probes) {
  const tools = toolNames(ctx)
  const mode = sandboxMode(ctx)
  return {
    plugin: PLUGIN,
    applied: true,
    phase,
    pid: process.pid,
    toolNames: tools.toolNames,
    toolError: tools.toolError,
    sandboxDefaultMode: mode.sandboxDefaultMode,
    sandboxModeError: mode.sandboxModeError,
    presetEcho: presetEcho(ctx),
    home: process.env.DSH_HOME || process.env.HOME || null,
    patches: patchesFromArgv(process.argv.slice(2)),
    allowlist: allowlistEcho(ctx, probes),
    node: process.version,
    nonce: process.env[NONCE_ENV] ?? null,
    attemptKey: process.env[ATTEMPT_ENV] ?? null,
    writtenAt: new Date().toISOString(),
  }
}

/** 原子落盘：先写临时文件再 rename（Host 侧读到半截 JSON 会当坏 JSON ⇒ 显式失败）。 */
function writeReport(report) {
  const dir = process.env[REPORT_ENV]
  if (!dir) {
    diagnose(`缺 ${REPORT_ENV}：无处落自检报告（Host 会把"缺报告"判为失败）`)
    return false
  }
  const target = join(dir, REPORT_FILE)
  const temp = `${target}.tmp-${process.pid}`
  try {
    mkdirSync(dir, { recursive: true })
    writeFileSync(temp, `${JSON.stringify(report, null, 1)}\n`, 'utf8')
    renameSync(temp, target)
    return true
  } catch (err) {
    diagnose(`写自检报告失败（${target}）：${errorText(err)}`)
    return false
  }
}

function buildReport(ctx, phase, probes) {
  try {
    return collect(ctx, phase, probes)
  } catch (err) {
    // 自检自身失败也必须落到报告里：缺报告 = Host 显式失败，但要能看出原因
    diagnose(`自检收集失败：${errorText(err)}`)
    return { plugin: PLUGIN, applied: false, phase, pid: process.pid, error: errorText(err) }
  }
}

/** 准入快照的"就绪"判据：工具清单非空 + 沙箱档取到 + preset 回显不是 unknown
 * [+ 白名单启用时：生效面算得出来 + deny 取证已回]。
 *
 * 为什么需要轮询（C2 实测缺陷，2026-10-29）：`setTimeout(0)` 只等一个宏任务，
 * 在部分 boot 里其它插件的服务还没注册 ⇒ deferred 快照里 `toolNames=None`、
 * `sandboxPolicy`/`permissionPresets` 取不到（6 次真实 attempt 里 4 次这样）。
 * Host 会 fail-closed（正确），但准入判定变成了**竞态**。改为：就绪即写，
 * 未就绪则每 ${POLL_MS}ms 重试，最长 ${DEADLINE_MS}ms 后仍写（Host 仍会显式失败）。
 */
const READY_POLL_MS = 50
const READY_DEADLINE_MS = 5000

function ready(report) {
  const tools = report.toolNames
  const echo = report.presetEcho || {}
  const base = Array.isArray(tools) && tools.length > 0
    && typeof report.sandboxDefaultMode === 'string' && report.sandboxDefaultMode.length > 0
    && echo.availability !== 'unknown'
  if (!base) return false
  const allowlist = report.allowlist
  if (!allowlist || allowlist.enabled !== true) return true
  // 白名单启用：没算出生效面 / 还没拿到 deny 取证 ⇒ 还没就绪（Host 只认"证明生效"）
  const effective = Array.isArray(allowlist.effective) ? allowlist.effective : null
  const probe = allowlist.probe
  const allowedProbe = allowlist.allowedProbe
  if (effective === null || probe === null || probe === undefined
      || allowedProbe === null || allowedProbe === undefined) return false
  // 可见面收窄打开时，agent 作用域回显必须到位（收窄发生在 agent 创建时，晚于工具就绪）
  if (allowlist.enforceVisibility === true) {
    const scope = allowlist.agentScope
    if (!scope || typeof scope !== 'object') return false
    if (!Array.isArray(scope.names) && !scope.error) return false
  }
  return true
}

export function apply(ctx) {
  // 第一份是 **apply 期快照**：此时工具注册表与服务可能还没就绪（实测 toolNames=[]、
  // sandboxPolicy 取不到）⇒ Host 不得拿它当准入，只能当诊断；
  writeReport(buildReport(ctx, 'apply', null))
  // 第二份是 **deferred 快照**（准入快照）：等"就绪"再写（轮询，最长 5s）。
  // S7b：白名单启用时先做一次真派发取证。取证**不能**只在 apply 那一刻试一次：
  // 那时白名单服务/工具注册表可能都还没就绪（boot 竞态实测：apply 快照里
  // `toolNames=[]`、服务取不到）⇒ 在轮询里等条件满足再取证，只做一次。
  const started = Date.now()
  let probes = null
  const step = async () => {
    try {
      if (probes === null) {
        const { state } = allowlistState(ctx)
        const tools = toolNames(ctx)
        if (state && state.enabled === true
            && Array.isArray(tools.toolNames) && tools.toolNames.length > 0) {
          probes = await allowlistProbes(ctx, state)
        }
      }
    } catch (err) {
      diagnose(`白名单取证失败：${errorText(err)}`)
      probes = {
        probe: { attempted: false, name: null, denied: null, code: null,
                 reason: `取证抛错：${errorText(err)}` },
        allowedProbe: { attempted: false, name: null, denied: null, code: null,
                        reason: `取证抛错：${errorText(err)}` },
      }
    }
    const report = buildReport(ctx, 'deferred', probes)
    if (ready(report) || Date.now() - started >= READY_DEADLINE_MS) {
      writeReport(report)
      return
    }
    const next = setTimeout(step, READY_POLL_MS)
    if (next && typeof next.unref === 'function') next.unref()
  }
  const timer = setTimeout(step, 0)
  if (timer && typeof timer.unref === 'function') timer.unref()
}
