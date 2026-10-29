"""S7b 工具白名单的 **Host 侧唯一判据**（人工裁决 B2 / 2026-10-29；REV-14 D4、SPEC-08 §5/§10 D03）。

三件事，一份实现（AGENTS 红线 8：不许出现第二套同判据）：

1. **解析策略**：`SETTINGS.yaml` 的 `loop.agent_runtime.dsh.tool_allowlist` → `AllowlistPolicy`
   （纯函数；未知键/坏类型/与裁决冲突一律 `AllowlistConfigError`，不吞成默认值）；
2. **渲染配置**：把策略渲染成**插件唯一能读的那份 env**（`render_env`；插件不解析 SETTINGS，
   避免同一份策略两个解析器）；
3. **校验回显**：判自检报告里的 `allowlist` 是否证明"白名单真的生效了"
   （插件名/开关/清单/有效面/被拒面/**一次真 deny 取证** + **一次允许分支取证**
   [+ 开了收窄时：**agent 作用域可见面 = 清单**]），并算策略指纹（A2）。

不做什么（边界要写清，否则会被当成新的隔离证明）：

- **不判 deny 本身**：拒绝发生在 dsh 进程里（`tools/pre-execute` 钩子，
  `dsh_plugin/tool_allowlist.mjs`）。Host 只判"回显是否证明它生效"，不复制拒绝逻辑；
  两层判据：① **可见面收窄**（`agent/created` + `agent.ctx.tools.restrict`，模型看不到清单外工具）；
  ② **派发前拒绝**（`tools/pre-execute` 的 deny：即使工具仍可见/仍被派发也拿不到执行）；
- **可见面收窄是"按 agent 作用域"的第二层，不是全局收窄**：0.2.1-rc.2 的
  `tools.restrict()` 只接受**带 agent 作用域**的 ctx（
  `node_modules/@deepseek-ai/dsh-tools/lib/index.js:2991-2993` 显式抛错：
  "requires a scoped context (agent.ctx)"），所以插件在 `agent/created`（
  `dsh-agent/lib/types/runtime-types.d.ts:227-233`，agent 创建完成、模型请求前 await 完）
  里调 `agent.ctx.tools.restrict({allow})`——官方用法见
  `dsh-subagent/lib/index.js:395`。该层由 `enforce_visibility` 显式开关控制；
  **关掉时**判据退化为 `effective = 可见面 ∩ 清单` + 清单外调用被 deny（可见但不可用）。
  两层都不改变效果隔离：白名单不是沙箱（REV-14 A8）；
- **不代替效果隔离**：白名单不是沙箱（REV-13 §5.4 / REV-14 A8）。bwrap/双钉一点没放宽；
- 不做 I/O、不联网、不读 SETTINGS 文件：只用传入的 dict 与自检回显。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

SUBMIT_TOOL = "submit_result"

#: 插件身份（patch insert 的 entry id 必须逐字一致；自检回显里逐字比对）
PLUGIN_ID = "s7b-tool-allowlist"
#: 插件文件名（`dsh_plugin/` 下；由 `dsh_assets.materialize` 拷进 attempt 插件目录）
PLUGIN_FILE = "tool_allowlist.mjs"
#: 插件发布生效状态的 cordis 服务名（自检据此回显"插件真的激活了"，而不是读 env 猜）
STATE_SERVICE = "s7ToolAllowlist"
#: 策略 env（**唯一**配置传递通道；理由见 `render_env`）
CONFIG_ENV = "DSH_TOOL_ALLOWLIST"
#: 取证工具名覆盖（可选；不给则由插件在"被拒面"里自选一个只读工具）
PROBE_ENV = "DSH_TOOL_ALLOWLIST_PROBE"
#: 自检报告里的回显键
REPORT_KEY = "allowlist"
#: 拒绝的可判错误身份（模型面文本给原因，`error.info` 给机器可判的 name/code）
DENY_CODE = "TOOL_NOT_ALLOWLISTED"
DENY_NAME = "ToolNotAllowedError"

#: **人工裁决 B2（2026-10-29）的允许面**——名字必须是 0.2.1-rc.2 harness 里的**真实**工具名。
#: 实测 26 项全量面见 `doc/evidence/DSH_C2_20261029/raw/ds04_session_tools.json`：
#: `job_output/job_list/job_kill/web_search/web_fetch/submit_result/todo_write/exit_plan_mode/
#: get_goal/create_goal/update_goal/working_directory/read/write/edit/glob/grep/skill/bash/
#: read_image/send_message/interrupt_agent/list_agents/subagent/subagent_fork/workflow`。
#:
#: **裁决字面 vs 实测的差异（显式登记，不静默丢）**：裁决写的是
#: `read/list/grep/glob/write/edit/apply_patch`，但本版本 harness **没有** `list`（目录列举由
#: `glob`/`bash` 承担）与 `apply_patch`（那个工具属于未挂载的 `dsh-tool-str-replace-editor`）。
#: 因此清单只收**真实存在**的名字；多出来的两个名字若写进清单，会被 `verify_echo` 的
#: `unknownAllowed` 判为漂移并显式失败（这也是我们想要的：清单必须与 harness 对得上）。
DEFAULT_ALLOWED: tuple[str, ...] = (
    "read", "write", "edit", "glob", "grep", "bash", SUBMIT_TOOL,
)

#: **单独登记为已接受暴露面**的工具（裁决 B2）：`bash` 保留（N6 实测用它做 `ls`/`md5sum`，
#: 禁掉显著降低成功率）。不是"顺手放进清单"：它必须在策略里显式认账（`accept_bash`），
#: 并在自检回显与指纹里单独出现，供证据逐条引用。
ACCEPTED_EXPOSURE: tuple[str, ...] = ("bash",)

#: 裁决**明确拒绝**的工具（登记用：配置不许把它们放进来；拒绝判据仍是"不在清单里"，
#: 本元组只用于在解析期拦"配置把已拒工具放回清单"这种自相矛盾）。
DECISION_REJECTED: tuple[str, ...] = (
    "web_search", "web_fetch", "subagent", "subagent_fork", "workflow",
    "send_message", "present", "job_output", "job_list", "job_kill",
)

#: SETTINGS 里 `tool_allowlist` 允许的键（多一个就拒绝：不静默接受未实现开关）
CONFIG_KEYS = frozenset({"enabled", "allowed", "accept_bash", "enforce_visibility"})

#: 工具名允许的字符集（也是 env 编码安全的前提：不会出现逗号/引号歧义）
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.:-]+$")
#: 指纹口径版本（改口径必须换版本，旧指纹不得沿用）
_FINGERPRINT_SCHEMA = "loop/dsh-tool-allowlist/1"


class AllowlistConfigError(Exception):
    """`tool_allowlist` 配置不合法（调用方必须显式失败，不得 fallback 成全量 harness）。

    刻意**不**继承 `BackendConfigurationError`：本模块保持零依赖（可被任何上层引用），
    由 `dsh.py` 统一翻译成后端配置错误（见 §接线契约）。
    """


@dataclass(frozen=True)
class AllowlistPolicy:
    """一份可判的白名单策略（`enabled=False` 时 `allowed` 必须为空）。

    `source` 只用于回显/证据（`settings` = 来自 SETTINGS；`default` = 未配置）。
    """

    enabled: bool = False
    allowed: tuple[str, ...] = ()
    accept_bash: bool = False
    #: 是否额外做**按 agent 作用域**的可见面收窄（模型看不到清单外的工具）。
    #: 默认开：这才是计划 §5 的验收（"自检回显的工具面 = 允清单"）；关掉只剩 deny 层，
    #: 模型仍会看到 26 项全量面、把回合浪费在被拒调用上（真内核实测见 §报告）。
    enforce_visibility: bool = True
    source: str = "default"

    @property
    def accepted_exposure(self) -> tuple[str, ...]:
        """本策略里**实际认账**的已接受暴露面（清单里没有 `bash` 就没有）。"""
        return tuple(name for name in ACCEPTED_EXPOSURE if name in self.allowed)

    @property
    def denied_names(self) -> tuple[str, ...]:
        """裁决拒绝面里"现在会被拒"的那部分（证据/报告用；不是判据）。"""
        return tuple(name for name in DECISION_REJECTED if name not in self.allowed)


#: 未配置时的策略（= S6 现状：插件不挂、零拒绝）
DISABLED_POLICY = AllowlistPolicy()


def _tool_names(value: Any, *, field: str) -> tuple[str, ...]:
    """校验并规范化一个工具清单：列表、非空、名字合法、不重复、不含已拒工具。"""
    if not isinstance(value, (list, tuple)):
        raise AllowlistConfigError("tool_allowlist.%s 必须是列表（实际 %s）"
                                   % (field, type(value).__name__))
    names: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry.strip():
            raise AllowlistConfigError("tool_allowlist.%s 里有非字符串/空项：%r"
                                       % (field, entry))
        name = entry.strip()
        if not _TOOL_NAME.match(name):
            raise AllowlistConfigError(
                "tool_allowlist.%s 里的工具名 %r 不合法（只允许字母/数字/`_`/`.`/`:`/`-`；"
                "工具名必须与 dsh harness 注册名逐字一致）" % (field, name))
        if name in names:
            raise AllowlistConfigError("tool_allowlist.%s 里 %r 重复（无语义，只会掩盖编辑错误）"
                                       % (field, name))
        if name in DECISION_REJECTED:
            raise AllowlistConfigError(
                "tool_allowlist.%s 里 %r 是人工裁决 B2（2026-10-29）**明确拒绝**的工具，"
                "配置不能把它放回清单；要改这条裁决必须走规格变更（不是改 SETTINGS）"
                % (field, name))
        names.append(name)
    if not names:
        raise AllowlistConfigError("tool_allowlist.%s 不能为空（空清单 ⇒ 所有工具被拒、"
                                   "提交通道也断，任务必失败）" % field)
    return tuple(names)


def policy_from_settings(raw: Any) -> AllowlistPolicy:
    """把 `SETTINGS.yaml` 的 `dsh.tool_allowlist`（原始 dict）解析成策略。

    判据（每条都能反向抽检）：
    1. 缺省/`None` ⇒ **开关关**（S6 现状），不是"默认收紧"；
    2. 必须是 mapping，键必须是 `CONFIG_KEYS` 的子集（拼错键名 ⇒ 显式失败）；
    3. `enabled` 必须是**布尔**（`"yes"`/`1` 之类不猜）；
    4. `allowed` 缺省 = `DEFAULT_ALLOWED`（人工裁决）；给了就按给的，但必须：
       非空、名字合法不重复、不含裁决拒绝面、**必须含 `submit_result`**（否则提交通道断）；
    5. `enforce_visibility`：必须是布尔，缺省 **true**（两层全开：收窄可见面 + 派发前拒绝）；
    6. `accept_bash`：`bash` 在清单里却显式 `false` ⇒ 自相矛盾，显式失败。
    """
    if raw is None:
        return DISABLED_POLICY
    if not isinstance(raw, dict):
        raise AllowlistConfigError("agent_runtime.dsh.tool_allowlist 必须是 mapping（实际 %s）"
                                   % type(raw).__name__)
    unknown = set(raw) - CONFIG_KEYS
    if unknown:
        raise AllowlistConfigError("agent_runtime.dsh.tool_allowlist 含未知字段：%s（允许 %s）"
                                   % (sorted(unknown), sorted(CONFIG_KEYS)))

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise AllowlistConfigError("tool_allowlist.enabled 必须是布尔（实际 %r）" % (enabled,))
    if not enabled:
        return DISABLED_POLICY

    allowed = (_tool_names(raw["allowed"], field="allowed")
               if "allowed" in raw else DEFAULT_ALLOWED)
    if SUBMIT_TOOL not in allowed:
        raise AllowlistConfigError(
            "tool_allowlist.allowed 缺 %r：没有它结构化提交通道不可用（任务必失败），"
            "不能当合法配置" % SUBMIT_TOOL)

    enforce_visibility = raw.get("enforce_visibility", True)
    if not isinstance(enforce_visibility, bool):
        raise AllowlistConfigError("tool_allowlist.enforce_visibility 必须是布尔（实际 %r）"
                                   % (enforce_visibility,))
    accept_bash = raw.get("accept_bash", True)
    if not isinstance(accept_bash, bool):
        raise AllowlistConfigError("tool_allowlist.accept_bash 必须是布尔（实际 %r）"
                                   % (accept_bash,))
    if "bash" in allowed and not accept_bash:
        raise AllowlistConfigError(
            "tool_allowlist.allowed 含 'bash' 但 accept_bash=false：自相矛盾。"
            "`bash` 是**已接受暴露面**（裁决 B2），要么显式认账（accept_bash: true），"
            "要么把它移出清单")
    return AllowlistPolicy(enabled=True, allowed=tuple(allowed), accept_bash=accept_bash,
                           enforce_visibility=enforce_visibility, source="settings")


def render_env(policy: AllowlistPolicy) -> dict[str, str]:
    """把策略渲染成插件读的那份 env（**唯一编码实现**；开关关 ⇒ 空 dict）。

    为什么用 env 而不是 patch 的 `config:`：见 §接线契约的取证（`dsh.py` 已用 env 传
    侧信道，`dsh_process.build_env` 是白名单；patch 的 `config` 是**整块替换**，坏形状只会
    让条目 `did not activate` 出一条 warning，不在准入路径上显形）。env 的好处是：
    插件被挂上但配置没到 ⇒ 自检回显 `configError`/`enabled=false` ⇒ Host 显式失败。
    """
    if not policy.enabled:
        return {}
    payload = {"enabled": True, "allowed": list(policy.allowed)}
    if policy.enforce_visibility:
        payload["enforce_visibility"] = True
    if not policy.accept_bash:
        payload["accept_bash"] = False
    return {CONFIG_ENV: json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":"))}


def policy_fingerprint(policy: AllowlistPolicy) -> str:
    """策略指纹（A2）：开关/清单/已接受暴露面一变，旧探测与旧结论就不再代表当前运行时。"""
    payload = {"schema": _FINGERPRINT_SCHEMA,
               "enabled": bool(policy.enabled),
               "allowed": sorted(policy.allowed),
               "accepted_exposure": sorted(policy.accepted_exposure),
               "enforce_visibility": bool(policy.enforce_visibility)}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _sorted_names(value: Any) -> tuple[str, ...] | None:
    """把回显里的名字列表规范成排好序的 tuple；不是字符串列表 ⇒ None（判不过）。"""
    if not isinstance(value, (list, tuple)):
        return None
    names = []
    for entry in value:
        if not isinstance(entry, str):
            return None
        names.append(entry)
    return tuple(sorted(names))


def _tool_surface(tool_names: Iterable[Any] | None) -> set[str] | None:
    if tool_names is None:
        return None
    try:
        names = {str(name) for name in tool_names}
    except TypeError:
        return None
    return names or None


def verify_echo(echo: Any, policy: AllowlistPolicy, *,
                tool_names: Iterable[Any] | None) -> tuple[str, ...]:
    """把自检报告的白名单回显判成 problems（空 tuple = 通过）。

    这是**准入判据**，所以每条都必须是"不读实现也能反向抽检"的事实：
    插件真的激活了（`applied`）、开关一致（`enabled`）、清单逐字是本次策略
    （`allowed`）、有效面/被拒面与 `toolNames` 分区一致、`submit_result` 在有效面里、
    **至少一次真 deny 取证**且 code 可判。缺任何一条 ⇒ 只证明"进程起来了"。
    """
    problems: list[str] = []
    if not policy.enabled:
        # 开关关：允许"没有回显"（插件根本没挂 = S6 现状）；但不允许"回显说自己在跑"
        if isinstance(echo, dict) and echo.get("enabled") is True:
            problems.append(
                "S7b：白名单开关关（SETTINGS 未启用），但插件回显 enabled=true —— "
                "开关与实际运行状态矛盾，拒绝生效面未知，不得当准入")
        return tuple(problems)

    if not isinstance(echo, dict):
        return ("S7b：拿不到白名单回显（allowlist=%r）——'进程起来了/插件没报错'都不算准入"
                "（DS-08 的同一纪律）" % (echo,),)

    if echo.get("plugin") != PLUGIN_ID:
        problems.append("S7b：白名单回显 plugin=%r ≠ %r（不是本片的插件在回显）"
                        % (echo.get("plugin"), PLUGIN_ID))
    if echo.get("applied") is not True:
        problems.append("S7b：白名单插件未完成 apply（applied=%r）：激活失败在 dsh 里只出"
                        " `warning: … did not activate`，不阻断启动 ⇒ 拒绝面未知"
                        % (echo.get("applied"),))
    if echo.get("enabled") is not True:
        problems.append("S7b：白名单回显 enabled=%r（策略要求启用）：插件没按配置生效"
                        % (echo.get("enabled"),))
    config_error = echo.get("configError")
    if config_error:
        problems.append("S7b：白名单插件配置无效（configError=%r）：插件按 fail-closed "
                        "全拒（或未注册拒绝判据），不能当准入" % (config_error,))

    echo_allowed = _sorted_names(echo.get("allowed"))
    if echo_allowed is None or echo_allowed != tuple(sorted(policy.allowed)):
        problems.append("S7b：回显清单与本次策略不一致（回显=%r，期望=%r）"
                        % (echo.get("allowed"), list(policy.allowed)))

    surface = _tool_surface(tool_names)
    if surface is None:
        problems.append("S7b：拿不到工具清单（toolNames=%r），无法判有效面"
                        % (tool_names,))
        return tuple(problems)

    expected_effective = tuple(sorted(surface & set(policy.allowed)))
    expected_denied = tuple(sorted(surface - set(policy.allowed)))
    expected_unknown = tuple(sorted(set(policy.allowed) - surface))

    echo_effective = _sorted_names(echo.get("effective"))
    if echo_effective is None or echo_effective != expected_effective:
        problems.append("S7b：有效工具面回显=%r ≠ 期望（可见面 ∩ 清单）=%r"
                        % (echo.get("effective"), list(expected_effective)))
    echo_denied = _sorted_names(echo.get("denied"))
    if echo_denied is None or echo_denied != expected_denied:
        problems.append("S7b：被拒工具面回显=%r ≠ 期望（可见面 − 清单）=%r"
                        % (echo.get("denied"), list(expected_denied)))
    if expected_unknown:
        problems.append(
            "S7b：清单里有工具在本 harness 可见面里不存在：%s —— 清单与 harness 漂移"
            "（本版本无 list/apply_patch，见 §DEFAULT_ALLOWED 注释）"
            % (list(expected_unknown),))

    if SUBMIT_TOOL not in expected_effective:
        problems.append(
            "S7b：%r 不在有效工具面里（清单=%r，可见面含它=%r）：结构化提交通道不可用 ⇒ "
            "任务必失败，不能当准入"
            % (SUBMIT_TOOL, list(policy.allowed), SUBMIT_TOOL in surface))

    probe = echo.get("probe")
    if not isinstance(probe, dict):
        problems.append("S7b：没有 deny 取证（probe=%r）：只证明插件起来了，没证明"
                        "'清单外调用真的被拒'" % (probe,))
        return tuple(problems)
    probe_name = probe.get("name")
    if not isinstance(probe_name, str) or not probe_name:
        problems.append("S7b：deny 取证缺工具名（probe.name=%r）" % (probe_name,))
    elif probe_name in set(policy.allowed):
        problems.append("S7b：deny 取证的工具 %r 在允许清单里（取证无效：那本来该放行）"
                        % (probe_name,))
    if probe.get("denied") is not True:
        problems.append("S7b：deny 取证显示未被拒绝（denied=%r，reason=%r）：白名单可能没生效"
                        % (probe.get("denied"), probe.get("reason")))
    if probe.get("code") != DENY_CODE:
        problems.append("S7b：deny 取证 code=%r ≠ %r（拒绝不可判：分不清「白名单拒绝」"
                        "与其它失败）" % (probe.get("code"), DENY_CODE))
    reason = probe.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        problems.append("S7b：deny 取证没有可读原因（reason=%r）" % (reason,))

    # 第二个取证：清单**内**的工具必须能走通派发（拿到的不是白名单拒绝码）。
    # 为什么必须：只有 deny 取证时，"把所有工具都拒掉"的白名单同样能通过取证，
    # 而那种白名单会让任务必失败（提交通道也断）——那正是"过紧"的假通过。
    allowed_probe = echo.get("allowedProbe")
    if not isinstance(allowed_probe, dict):
        problems.append("S7b：没有「允许分支」取证（allowedProbe=%r）：无法排除"
                        "'白名单把所有工具都拒掉'" % (allowed_probe,))
        return tuple(problems)
    allowed_name = allowed_probe.get("name")
    if not isinstance(allowed_name, str) or not allowed_name:
        problems.append("S7b：允许分支取证缺工具名（allowedProbe.name=%r）"
                        % (allowed_name,))
    elif allowed_name not in set(policy.allowed):
        problems.append("S7b：允许分支取证的工具 %r 不在允许清单里（取证选错了对象）"
                        % (allowed_name,))
    elif allowed_name not in expected_effective:
        problems.append("S7b：允许分支取证的工具 %r 不在有效工具面里（无法证明放行）"
                        % (allowed_name,))
    if allowed_probe.get("code") == DENY_CODE:
        problems.append("S7b：允许分支取证显示清单**内**的工具被白名单拒绝（name=%r）："
                        "白名单过紧，任务工具面不可用" % (allowed_name,))

    # 可见面收窄（可选层）：开关打开时，必须有"本 agent 的作用域可见面 = 清单∩全局面"的回显。
    echo_enforce = echo.get("enforceVisibility") is True
    if echo_enforce and not policy.enforce_visibility:
        problems.append("S7b：插件回显 enforceVisibility=true，但策略没开 enforce_visibility —— "
                        "运行面与配置不一致，看不出是谁在收窄可见面")
    if policy.enforce_visibility:
        scope = echo.get("agentScope")
        if not isinstance(scope, dict):
            problems.append("S7b：开了可见面收窄但拿不到 agent 作用域回显（agentScope=%r）——"
                            "收窄是否生效未知（agent 可能还没创建）" % (scope,))
            return tuple(problems)
        if scope.get("error"):
            problems.append("S7b：可见面收窄失败（agentScope.error=%r）：模型仍会看到清单外工具"
                            % (scope.get("error"),))
        scope_names = _sorted_names(scope.get("names"))
        if scope_names is None or scope_names != expected_effective:
            problems.append("S7b：agent 作用域可见面回显=%r ≠ 期望（清单∩全局面）=%r"
                            % (scope.get("names"), list(expected_effective)))
    return tuple(problems)
