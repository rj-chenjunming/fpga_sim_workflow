"""S7b 工具白名单（人工裁决 B2 / 2026-10-29；REV-14 D4、SPEC-08 §5/§10 D03）。

判据（不读实现也应成立）：

- 白名单**外**的工具调用被**显式拒绝**（`isError` + 可判 `error.info.code` + 可读原因），
  **不是**静默丢弃、不是"看起来没这个工具"；
- 白名单**内**的工具照常执行；`submit_result` **始终可用**（否则结构化提交通道断掉，
  任务必失败）；
- **开关关掉** ⇒ 回到 S6 现状：全量 harness，零拒绝（不因为"代码里有白名单"就默认收紧）；
- **配置坏掉** ⇒ **fail-closed**（全拒 + 可读原因），不得静默放开；
- 自检必须回显「白名单生效状态 + 有效工具面 + 一次真实 deny 取证」——
  "进程起来了 / 插件没报错"都不算准入（DS-08 的同一纪律）；
- **不声称**工具可见面被收窄到清单：0.2.1-rc.2 的 `tools.restrict()` 只接受**带 agent 作用域**
  的 ctx（`dsh-tools/lib/index.js:2991-2993` 显式抛错），插件拿不到全局可见面收窄 API。
  因此判据是 `effective = 可见面 ∩ 清单`，且清单外调用必须被 deny（可见但不可用）。

真 dsh 用例缺件即 `skip`（缺件是环境事实，不是通过）。真实 `toolNames` 收敛效果**未测**：
下面真机用例只证明"插件激活 + 配置到达 + deny 取到"，不证明模型侧工具面变小。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from host.agent_backends import dsh_allowlist as AL
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_process as DP
from host.agent_backends import dsh_selfcheck as SC

DSH_BIN = Path("/home/soft/DSH/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js")
NODE_BIN = Path("/home/soft/DSH/node/bin/node")
PLUGIN_SRC = A.PLUGIN_SOURCE_DIR / AL.PLUGIN_FILE

#: 真机 26 项可见面的**子集**（用于离线断言"分区成立"；完整 26 项见
#: doc/evidence/DSH_C2_20261029/raw/ds04_session_tools.json）
SURFACE = ("bash", "edit", "glob", "grep", "job_list", "read", "read_image",
           "send_message", "subagent", "submit_result", "web_fetch", "web_search",
           "workflow", "write")


# ================================================================== Host 侧判据（纯函数）

def test_default_allowed_matches_human_decision() -> None:
    """B2 裁决的允许面：文件读写/检索 + bash + 提交通道。"""
    assert set(AL.DEFAULT_ALLOWED) == {"read", "write", "edit", "glob", "grep",
                                       "bash", "submit_result"}


def test_decision_rejected_tools_are_not_allowed() -> None:
    """B2 裁决明确拒绝的工具一个都不在默认清单里（含 `job_*`、`subagent*`）。"""
    for name in ("web_search", "web_fetch", "subagent", "subagent_fork", "workflow",
                 "send_message", "present", "job_output", "job_list", "job_kill"):
        assert name not in AL.DEFAULT_ALLOWED, name


def test_bash_is_registered_accepted_exposure() -> None:
    """`bash` 保留但**单独登记**为已接受暴露面（不是顺手放进清单）。"""
    assert "bash" in AL.ACCEPTED_EXPOSURE
    assert "bash" in AL.DEFAULT_ALLOWED
    policy = AL.policy_from_settings({"enabled": True})
    assert policy.accepted_exposure == ("bash",)


def test_policy_disabled_by_default() -> None:
    """没有配置 ⇒ 开关关 ⇒ 渲染给插件的 env 为空（S6 现状，插件不会被挂）。"""
    policy = AL.policy_from_settings(None)
    assert policy.enabled is False
    assert policy.allowed == ()
    assert AL.render_env(policy) == {}


def test_policy_enabled_uses_default_allowed() -> None:
    policy = AL.policy_from_settings({"enabled": True})
    assert policy.enabled is True
    assert tuple(policy.allowed) == AL.DEFAULT_ALLOWED
    assert policy.source == "settings"


def test_policy_allowed_override_is_respected() -> None:
    policy = AL.policy_from_settings({"enabled": True, "allowed": ["read", "submit_result"]})
    assert tuple(policy.allowed) == ("read", "submit_result")
    assert policy.accepted_exposure == ()


def test_policy_allowed_override_requires_submit_result() -> None:
    """清单里没有 `submit_result` ⇒ 提交通道不可用 ⇒ 配置错误（不许静默）。"""
    with pytest.raises(AL.AllowlistConfigError) as excinfo:
        AL.policy_from_settings({"enabled": True, "allowed": ["read"]})
    assert "submit_result" in str(excinfo.value)


def test_policy_rejects_unknown_key() -> None:
    """拼错键名必须显式失败（`enabeld` 不得静默当作"没配置"）。"""
    with pytest.raises(AL.AllowlistConfigError) as excinfo:
        AL.policy_from_settings({"enabeld": True})
    assert "enabeld" in str(excinfo.value)


def test_policy_rejects_bad_enabled_type() -> None:
    with pytest.raises(AL.AllowlistConfigError):
        AL.policy_from_settings({"enabled": "yes"})


def test_policy_rejects_bad_allowed_entry() -> None:
    with pytest.raises(AL.AllowlistConfigError):
        AL.policy_from_settings({"enabled": True,
                                 "allowed": ["read", "submit_result", "read,write"]})


def test_policy_rejects_decision_rejected_name() -> None:
    """人工裁决拒绝的工具不得靠配置放进来（判据不是"配了就生效"）。"""
    with pytest.raises(AL.AllowlistConfigError) as excinfo:
        AL.policy_from_settings({"enabled": True,
                                 "allowed": ["read", "submit_result", "web_search"]})
    assert "web_search" in str(excinfo.value)


def test_policy_rejects_empty_allowed() -> None:
    with pytest.raises(AL.AllowlistConfigError):
        AL.policy_from_settings({"enabled": True, "allowed": []})


def test_policy_rejects_bash_without_accepted_exposure() -> None:
    """`bash` 在清单里但显式不认暴露面 ⇒ 自相矛盾，配置错误。"""
    with pytest.raises(AL.AllowlistConfigError) as excinfo:
        AL.policy_from_settings({"enabled": True, "accept_bash": False})
    assert "bash" in str(excinfo.value)


def test_policy_not_mapping_fails() -> None:
    with pytest.raises(AL.AllowlistConfigError):
        AL.policy_from_settings(["read"])


def test_render_env_roundtrip_with_parser() -> None:
    """Host 渲染的 env 必须能被插件侧逐字解析回同一份策略（唯一编码实现）。"""
    policy = AL.policy_from_settings({"enabled": True})
    env = AL.render_env(policy)
    assert list(env) == [AL.CONFIG_ENV]
    parsed = json.loads(env[AL.CONFIG_ENV])
    assert parsed["enabled"] is True
    assert tuple(parsed["allowed"]) == tuple(policy.allowed)


def test_fingerprint_tracks_switch_and_list() -> None:
    """开关/清单变化必须改变指纹（A2：旧探测不代表当前运行时）。"""
    off = AL.policy_fingerprint(AL.policy_from_settings(None))
    on = AL.policy_fingerprint(AL.policy_from_settings({"enabled": True}))
    narrow = AL.policy_fingerprint(AL.policy_from_settings(
        {"enabled": True, "allowed": ["read", "edit", "submit_result"]}))
    assert off != on
    assert on != narrow
    assert off.startswith("sha256:")


def test_fingerprint_is_stable() -> None:
    policy = AL.policy_from_settings({"enabled": True})
    assert AL.policy_fingerprint(policy) == AL.policy_fingerprint(policy)


# ================================================================== 自检回显校验

def _echo(**over) -> dict:
    """一份"全对"的白名单回显（fingerprint/effective/denied/probe 都自洽）。"""
    allowed = list(AL.DEFAULT_ALLOWED)
    surface = list(SURFACE)
    effective = sorted(set(surface) & set(allowed))
    denied = sorted(set(surface) - set(allowed))
    echo = {
        "plugin": AL.PLUGIN_ID,
        "applied": True,
        "enabled": True,
        "allowed": allowed,
        "configError": None,
        "toolCount": len(surface),
        "effective": effective,
        "denied": denied,
        "unknownAllowed": sorted(set(allowed) - set(surface)),
        "probe": {"name": "job_list", "denied": True, "code": AL.DENY_CODE,
                  "reason": "tool is not allowlisted"},
        "allowedProbe": {"name": "read", "denied": True, "code": "INVALID_ARGS",
                         "reason": "missing required parameter"},
        "enforceVisibility": True,
        "agentScope": {"attempted": True, "names": effective, "error": None},
    }
    echo.update(over)
    return echo


def _problems(echo, policy=None, surface=SURFACE) -> tuple[str, ...]:
    policy = policy or AL.policy_from_settings({"enabled": True})
    return AL.verify_echo(echo, policy, tool_names=list(surface))


def test_verify_echo_clean_passes() -> None:
    assert _problems(_echo()) == ()


def test_verify_echo_disabled_policy_accepts_absent_state() -> None:
    """开关关：插件没挂 ⇒ 没有回显 ⇒ 通过（S6 现状）。"""
    policy = AL.policy_from_settings(None)
    assert AL.verify_echo(None, policy, tool_names=list(SURFACE)) == ()


def test_verify_echo_disabled_policy_rejects_running_plugin() -> None:
    """开关关但插件在跑 ⇒ 状态自相矛盾，必须显式失败。"""
    policy = AL.policy_from_settings(None)
    problems = AL.verify_echo(_echo(), policy, tool_names=list(SURFACE))
    assert problems and "开关" in "；".join(problems)


def test_verify_echo_enabled_requires_state() -> None:
    """开关开但拿不到回显 ⇒ 不得以"进程起来了"当准入。"""
    problems = _problems(None)
    assert problems and "白名单" in "；".join(problems)


def test_verify_echo_requires_applied() -> None:
    problems = _problems(_echo(applied=False))
    assert problems


def test_verify_echo_requires_enabled_true() -> None:
    problems = _problems(_echo(enabled=False))
    assert problems


def test_verify_echo_rejects_config_error() -> None:
    problems = _problems(_echo(configError="bad json"))
    assert problems and "bad json" in "；".join(problems)


def test_verify_echo_rejects_allowed_mismatch() -> None:
    problems = _problems(_echo(allowed=["read", "submit_result"]))
    assert problems


def test_verify_echo_requires_submit_result_in_effective() -> None:
    """提交通道必须在有效面里（不在 ⇒ 任务必失败，不能当准入）。"""
    echo = _echo()
    echo["effective"] = [name for name in echo["effective"] if name != "submit_result"]
    problems = _problems(echo)
    assert problems and "submit_result" in "；".join(problems)


def test_verify_echo_rejects_effective_not_subset() -> None:
    echo = _echo()
    echo["effective"] = sorted(set(echo["effective"]) | {"web_search"})
    problems = _problems(echo)
    assert problems


def test_verify_echo_rejects_denied_mismatch() -> None:
    echo = _echo()
    echo["denied"] = [name for name in echo["denied"] if name != "web_search"]
    problems = _problems(echo)
    assert problems


def test_verify_echo_rejects_unknown_allowed() -> None:
    """清单里有、可见面里没有的名字 ⇒ 配置与 harness 漂移，必须显式失败。"""
    policy = AL.policy_from_settings(
        {"enabled": True, "allowed": ["read", "apply_patch", "submit_result"]})
    problems = AL.verify_echo(_echo(allowed=["read", "apply_patch", "submit_result"],
                                    effective=["read", "submit_result"],
                                    denied=sorted(set(SURFACE) - {"read", "submit_result"}),
                                    probe={"name": "job_list", "denied": True,
                                           "code": AL.DENY_CODE, "reason": "x"}),
                              policy, tool_names=list(SURFACE))
    assert problems and "apply_patch" in "；".join(problems)


def test_verify_echo_requires_deny_attestation() -> None:
    """没有任何 deny 取证 ⇒ 只证明"插件起来了"，不证明"拒绝真的生效"。"""
    problems = _problems(_echo(probe=None))
    assert problems and "取证" in "；".join(problems)


def test_verify_echo_rejects_attestation_without_deny() -> None:
    problems = _problems(_echo(probe={"name": "job_list", "denied": False,
                                      "code": None, "reason": None}))
    assert problems


def test_verify_echo_rejects_wrong_deny_code() -> None:
    problems = _problems(_echo(probe={"name": "job_list", "denied": True,
                                      "code": "SOMETHING_ELSE", "reason": "x"}))
    assert problems


def test_verify_echo_requires_allowed_branch_attestation() -> None:
    """只有 deny 取证不够：还得证明清单**内**的工具没被误拒（过紧同样是失败）。"""
    echo = _echo()
    echo.pop("allowedProbe")
    problems = _problems(echo)
    assert problems and "allowedProbe" in "；".join(problems)


def test_verify_echo_rejects_allowed_branch_denied() -> None:
    """允许分支被白名单拒绝 ⇒ 白名单过紧（任务工具面不可用）⇒ 显式失败。"""
    problems = _problems(_echo(allowedProbe={"name": "read", "denied": True,
                                             "code": AL.DENY_CODE, "reason": "x"}))
    assert problems and "过紧" in "；".join(problems)


def test_verify_echo_rejects_allowed_branch_outside_list() -> None:
    problems = _problems(_echo(allowedProbe={"name": "web_search", "denied": False,
                                             "code": None, "reason": "x"}))
    assert problems


def test_policy_enables_visibility_by_default() -> None:
    """默认策略两层全开：收窄可见面（模型看不到清单外工具）+ 派发前拒绝。"""
    policy = AL.policy_from_settings({"enabled": True})
    assert policy.enforce_visibility is True
    assert json.loads(AL.render_env(policy)[AL.CONFIG_ENV])["enforce_visibility"] is True


def test_policy_can_turn_visibility_off() -> None:
    policy = AL.policy_from_settings({"enabled": True, "enforce_visibility": False})
    assert policy.enforce_visibility is False
    assert "enforce_visibility" not in json.loads(AL.render_env(policy)[AL.CONFIG_ENV])


def test_policy_rejects_bad_visibility_type() -> None:
    with pytest.raises(AL.AllowlistConfigError):
        AL.policy_from_settings({"enabled": True, "enforce_visibility": "yes"})


def test_fingerprint_tracks_visibility_switch() -> None:
    """收窄开关变化也必须改变指纹（A2：可见面变了，旧探测不代表当前运行时）。"""
    on = AL.policy_fingerprint(AL.policy_from_settings({"enabled": True}))
    off = AL.policy_fingerprint(AL.policy_from_settings(
        {"enabled": True, "enforce_visibility": False}))
    assert on != off


def test_verify_echo_requires_agent_scope_when_enforcing() -> None:
    """开了收窄却拿不到 agent 作用域回显 ⇒ 收窄是否生效未知 ⇒ 显式失败。"""
    echo = _echo()
    echo.pop("agentScope")
    problems = _problems(echo)
    assert problems and "agentScope" in "；".join(problems)


def test_verify_echo_rejects_agent_scope_error() -> None:
    problems = _problems(_echo(agentScope={"attempted": True, "names": None,
                                           "error": "restrict 抛错"}))
    assert problems and "restrict 抛错" in "；".join(problems)


def test_verify_echo_rejects_agent_scope_not_narrowed() -> None:
    """agent 作用域面仍是全量面（收窄没生效）⇒ 显式失败，不得当准入。"""
    problems = _problems(_echo(agentScope={"attempted": True,
                                           "names": sorted(SURFACE), "error": None}))
    assert problems


def test_verify_echo_rejects_visibility_on_without_policy() -> None:
    """插件回显在收窄，但策略没开 ⇒ 运行面与配置不一致（看不出谁在收窄）。"""
    policy = AL.policy_from_settings({"enabled": True, "enforce_visibility": False})
    problems = AL.verify_echo(_echo(), policy, tool_names=list(SURFACE))
    assert problems and "enforce_visibility" in "；".join(problems)


def test_verify_echo_deny_only_mode_ignores_agent_scope() -> None:
    """收窄关掉时不得要求 agent 作用域回显（deny 层仍然要取证）。"""
    policy = AL.policy_from_settings({"enabled": True, "enforce_visibility": False})
    echo = _echo(enforceVisibility=False)
    echo.pop("agentScope")
    assert AL.verify_echo(echo, policy, tool_names=list(SURFACE)) == ()


def test_verify_echo_rejects_wrong_plugin() -> None:
    problems = _problems(_echo(plugin="s2-selfcheck"))
    assert problems


def test_plugin_and_selfcheck_constants_match_host_contract() -> None:
    """两份 .mjs 里的契约常量必须与 Host 常量逐字一致（漂移 = 回显对不上）。"""
    plugin = PLUGIN_SRC.read_text(encoding="utf-8")
    for needle in (AL.PLUGIN_ID, AL.CONFIG_ENV, AL.PROBE_ENV, AL.STATE_SERVICE,
                   AL.DENY_CODE, AL.DENY_NAME):
        assert needle in plugin, "插件缺契约常量 %r" % needle
    selfcheck = (A.PLUGIN_SOURCE_DIR / "selfcheck.mjs").read_text(encoding="utf-8")
    assert AL.STATE_SERVICE in selfcheck, "自检插件没读白名单服务（回显不可能成立）"
    assert AL.REPORT_KEY in selfcheck


# ================================================================== 插件（真 dsh-tools 内核，离线）

_HARNESS = r"""
import { Context } from '@deepseek-ai/cordis'
import Tools, { defineTool } from '@deepseek-ai/dsh-tools'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import { pathToFileURL } from 'node:url'

const plugin = await import(pathToFileURL(process.env.HARNESS_PLUGIN).href)
const ctx = new Context()
await ctx.plugin(SystemPrompt)
await ctx.plugin(Tools)
const tools = ctx.get('tools')
const ran = []
for (const name of (process.env.HARNESS_TOOLS || '').split(',').filter(Boolean)) {
  tools.register(defineTool({
    name,
    description: name,
    parameters: {},
    output: { schema: { type: 'string' }, render: (_a, value) => [{ type: 'text', text: value }] },
    async execute() { ran.push(name); return 'RAN:' + name },
  }))
}
await ctx.plugin(plugin)
const raw = ctx.get(process.env.HARNESS_SERVICE || '') ?? null
const state = raw && typeof raw.snapshot === 'function' ? raw.snapshot() : raw
const calls = {}
for (const name of (process.env.HARNESS_CALLS || '').split(',').filter(Boolean)) {
  const result = await tools.execute({
    callId: 'probe-' + name,
    name,
    arguments: {},
    signal: new AbortController().signal,
  })
  calls[name] = {
    isError: result.isError === true,
    text: (result.content || []).map((b) => b.text || '').join(''),
    code: result.error && result.error.info ? result.error.info.code : null,
    message: result.error ? result.error.message : null,
  }
}
console.log(JSON.stringify({
  state,
  calls,
  ran,
  schemas: tools.schemas().map((s) => s.name).sort(),
}))
"""


def _skip_node() -> str | None:
    if not NODE_BIN.is_file():
        return "本机无 node（%s）" % NODE_BIN
    if A.node_modules_for(DSH_BIN) is None:
        return "本机无该 DSH 安装（%s）" % DSH_BIN
    if not PLUGIN_SRC.is_file():
        return "仓内缺插件源码（%s）" % PLUGIN_SRC
    return None


def _run_plugin(tmp_path: Path, *, tools_csv: str, calls_csv: str,
                env: dict[str, str] | None = None) -> dict:
    """用**真 dsh-tools 内核**跑一次插件：真注册表 + 真 pre-execute 派发。"""
    work = tmp_path / "plugin-run"
    work.mkdir(parents=True, exist_ok=True)
    plugin = work / AL.PLUGIN_FILE
    shutil.copyfile(PLUGIN_SRC, plugin)
    node_modules = A.node_modules_for(DSH_BIN)
    link = work / "node_modules"
    if not link.exists():
        link.symlink_to(node_modules, target_is_directory=True)
    harness = work / "harness.mjs"
    harness.write_text(_HARNESS, encoding="utf-8")
    child_env = {k: v for k, v in os.environ.items()
                 if k not in {AL.CONFIG_ENV, AL.PROBE_ENV}}
    child_env.update({"HARNESS_PLUGIN": str(plugin), "HARNESS_TOOLS": tools_csv,
                      "HARNESS_CALLS": calls_csv, "HARNESS_SERVICE": AL.STATE_SERVICE})
    child_env.update(env or {})
    proc = subprocess.run([str(NODE_BIN), str(harness)], cwd=str(work), env=child_env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, "harness 失败：%s\n%s" % (proc.stdout, proc.stderr)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _policy_env(policy: AL.AllowlistPolicy | None = None) -> dict[str, str]:
    policy = policy or AL.policy_from_settings({"enabled": True})
    return AL.render_env(policy)


def test_plugin_denies_out_of_list_with_code_and_reason(tmp_path: Path) -> None:
    """清单外调用 ⇒ isError + 可判 code + 指出工具名与允许面（显式拒绝，不是静默丢弃）。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,submit_result,web_search",
                      calls_csv="web_search", env=_policy_env())
    call = out["calls"]["web_search"]
    assert call["isError"] is True
    assert call["code"] == AL.DENY_CODE
    assert "web_search" in call["text"]
    assert "read" in call["text"] and "submit_result" in call["text"]


def test_plugin_does_not_run_denied_body(tmp_path: Path) -> None:
    """被拒的工具体**不得执行**（拒绝必须发生在派发前）。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,submit_result,web_search",
                      calls_csv="web_search", env=_policy_env())
    assert out["ran"] == []


def test_plugin_allows_allowlisted_tools(tmp_path: Path) -> None:
    """清单内工具照常执行；`submit_result` 必须可用（提交通道不能因白名单断掉）。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,write,submit_result",
                      calls_csv="read,write,submit_result", env=_policy_env())
    for name in ("read", "write", "submit_result"):
        assert out["calls"][name]["isError"] is False, name
        assert out["calls"][name]["text"] == "RAN:" + name
    assert sorted(out["ran"]) == ["read", "submit_result", "write"]


def test_plugin_disabled_adds_no_denial(tmp_path: Path) -> None:
    """开关关（不渲染 env ⇒ 插件按未启用跑）⇒ 全量 harness 行为，零拒绝。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,submit_result,web_search",
                      calls_csv="web_search", env={})
    assert out["calls"]["web_search"]["isError"] is False
    assert out["ran"] == ["web_search"]


def test_plugin_malformed_config_denies_everything(tmp_path: Path) -> None:
    """配置坏掉 ⇒ fail-closed（全拒 + 原因），不得静默放开成全量 harness。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,submit_result",
                      calls_csv="read,submit_result", env={AL.CONFIG_ENV: "{not json"})
    for name in ("read", "submit_result"):
        assert out["calls"][name]["isError"] is True, name
        assert out["calls"][name]["code"] == AL.DENY_CODE
    assert out["ran"] == []
    assert out["state"]["configError"], "坏配置必须回显原因"


def test_plugin_unknown_tool_falls_through(tmp_path: Path) -> None:
    """拼写错误不是"越权"：未注册的名字交给引擎的 UNKNOWN_TOOL，不改既有错误语义。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv="read,submit_result",
                      calls_csv="not_a_tool", env=_policy_env())
    call = out["calls"]["not_a_tool"]
    assert call["isError"] is True
    assert call["code"] != AL.DENY_CODE, "未注册名被当成越权：白名单越界了判定范围"


def test_plugin_publishes_state_snapshot_for_selfcheck(tmp_path: Path) -> None:
    """自检要读的生效状态：插件名/开关/清单/有效面/被拒面必须自洽可判。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    out = _run_plugin(tmp_path, tools_csv=",".join(SURFACE), calls_csv="",
                      env=_policy_env())
    state = out["state"]
    assert state["plugin"] == AL.PLUGIN_ID
    assert state["applied"] is True and state["enabled"] is True
    assert tuple(state["allowed"]) == AL.DEFAULT_ALLOWED
    assert state["configError"] in (None, "")
    assert sorted(state["effective"]) == sorted(set(SURFACE) & set(AL.DEFAULT_ALLOWED))
    assert sorted(state["denied"]) == sorted(set(SURFACE) - set(AL.DEFAULT_ALLOWED))
    assert state["toolCount"] == len(SURFACE)


def test_plugin_selfcheck_echo_passes_host_verification(tmp_path: Path) -> None:
    """插件的真回显 + 自检取证必须能通过 Host 的唯一判据（两份实现不许漂移）。

    取证字段（`probe`）由自检插件写入（它是回显 owner）；这里按同名字段叠加，
    判的是"插件侧算出来的有效面/被拒面/清单"与 Host 侧期望是否逐字一致。
    """
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    # 离线 harness 没有 agent（收窄发生在 agent/created）⇒ 用 deny-only 策略同时渲染 env 与判据
    policy = AL.policy_from_settings({"enabled": True, "enforce_visibility": False})
    out = _run_plugin(tmp_path, tools_csv=",".join(SURFACE),
                      calls_csv="job_list", env=AL.render_env(policy))
    state = dict(out["state"])
    state["probe"] = {"name": "job_list", "denied": True, "code": AL.DENY_CODE,
                      "reason": out["calls"]["job_list"]["message"]}
    state["allowedProbe"] = {"name": "read", "denied": False, "code": None,
                             "reason": "ok"}
    assert AL.verify_echo(state, policy, tool_names=list(SURFACE)) == ()


def test_plugin_denies_all_rejected_names(tmp_path: Path) -> None:
    """裁决拒绝面逐个实测：每一个被拒名字都拿到同一可判 code。"""
    reason = _skip_node()
    if reason:
        pytest.skip(reason)
    rejected = ("web_search", "web_fetch", "subagent", "workflow", "send_message",
                "job_list", "job_kill", "job_output")
    out = _run_plugin(tmp_path, tools_csv=",".join(("read", "submit_result") + rejected),
                      calls_csv=",".join(rejected), env=_policy_env())
    for name in rejected:
        assert out["calls"][name]["isError"] is True, name
        assert out["calls"][name]["code"] == AL.DENY_CODE, name
    assert out["ran"] == []


# ================================================================== 真 dsh：回显 + deny 取证（不调模型）

def _skip_real() -> str | None:
    if not DSH_BIN.is_file():
        return "本机无该 DSH 安装（%s）" % DSH_BIN
    if not shutil.which("bwrap"):
        return "本机无 bwrap"
    if not PLUGIN_SRC.is_file():
        return "仓内缺插件源码（%s）" % PLUGIN_SRC
    return None


def _spec(layout: A.AttemptLayout, patches, env_extra) -> DP.AttemptSpec:
    return DP.AttemptSpec(
        attempt_key="RUN-TEST/N6/allowlist", cwd=layout.work, home=layout.home,
        task="只回复 OK", dsh_bin=DSH_BIN, node=NODE_BIN, patches=tuple(patches),
        profile="headless", timeout_s=180.0, wrap=True, env_extra=dict(env_extra),
        asset_dirs=(layout.plugin_dir, layout.patch_dir),
        state_dirs=(layout.selfcheck_dir,))


async def _boot_and_read(layout: A.AttemptLayout, plugins, env_extra: dict) -> dict:
    """起真 dsh（**无 key** ⇒ 到模型阶段必失败，但 boot/插件/自检都已完成）。

    这样拿到的回显是**真内核事实**，且不烧 token（不是"真实调用"）。
    """
    assets = A.materialize(layout, pins=A.ATTEMPT_PINS, plugins=tuple(plugins),
                           node_modules=A.node_modules_for(DSH_BIN))
    spec = _spec(layout, assets.patch_files, env_extra)
    with pytest.raises(DP.ProcessFailed):
        await DP.run_attempt(spec, on_start=None)
    return json.loads(layout.selfcheck_file().read_text(encoding="utf-8"))


async def test_real_dsh_allowlist_echo_and_deny_attestation(tmp_path: Path) -> None:
    """真 dsh：白名单插件激活、配置到达、回显有效面，并**真派发一次**取到 deny 原因。"""
    reason = _skip_real()
    if reason:
        pytest.skip(reason)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    policy = AL.policy_from_settings({"enabled": True, "enforce_visibility": False})
    env = {A.SELFCHECK_DIR_ENV: str(layout.selfcheck_dir),
           A.SELFCHECK_NONCE_ENV: "nonce-allowlist",
           A.ATTEMPT_KEY_ENV: "RUN-TEST/N6/allowlist"}
    env.update(AL.render_env(policy))
    report = await _boot_and_read(
        layout,
        (A.Plugin("s2-submit-result", "submit_result.mjs"),
         A.Plugin(AL.PLUGIN_ID, AL.PLUGIN_FILE),
         A.Plugin("s2-selfcheck", "selfcheck.mjs")),
        env)

    allowlist = report.get("allowlist")
    assert isinstance(allowlist, dict), "自检没回显白名单状态：不得以'进程起来了'当准入"
    assert allowlist["plugin"] == AL.PLUGIN_ID
    assert allowlist["enabled"] is True
    assert allowlist["configError"] in (None, "")
    surface = list(report["toolNames"])
    assert sorted(allowlist["effective"]) == sorted(set(surface) & set(AL.DEFAULT_ALLOWED))
    assert "submit_result" in allowlist["effective"]
    # 真派发一次：必须被拒，并带可判 code
    probe = allowlist.get("probe")
    assert isinstance(probe, dict), "没有 deny 取证：拒绝是否真的生效未知"
    assert probe["denied"] is True
    assert probe["code"] == AL.DENY_CODE
    assert isinstance(probe["reason"], str) and probe["reason"]
    # 允许分支：清单内工具必须走通派发、拿到的不是白名单拒绝码（排除"全拒"的假通过）
    allowed_probe = allowlist.get("allowedProbe")
    assert isinstance(allowed_probe, dict), "没有允许分支取证：无法排除白名单过紧"
    assert allowed_probe["name"] in AL.DEFAULT_ALLOWED
    assert allowed_probe["code"] != AL.DENY_CODE, allowed_probe
    # Host 唯一判据必须接受这份真回显
    assert AL.verify_echo(allowlist, policy, tool_names=surface) == ()


async def test_real_dsh_visibility_narrowed_to_allowlist(tmp_path: Path) -> None:
    """真 dsh + 收窄开着：**本 agent 的作用域可见面 = 允清单**（模型看不到清单外工具）。

    这是计划 §5 的验收（"自检回显的工具面 = 允清单"）唯一的可实现形态：
    全局注册表面无法由插件收窄（`tools.restrict()` 只接受 agent 作用域），
    所以判据落在 **agent 作用域视图**（`schemas(scopeOf(agentCtx))`，与官方投影同源）。
    """
    reason = _skip_real()
    if reason:
        pytest.skip(reason)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    policy = AL.policy_from_settings({"enabled": True})       # 默认：两层全开
    assert policy.enforce_visibility is True
    env = {A.SELFCHECK_DIR_ENV: str(layout.selfcheck_dir),
           A.SELFCHECK_NONCE_ENV: "nonce-narrow",
           A.ATTEMPT_KEY_ENV: "RUN-TEST/N6/allowlist"}
    env.update(AL.render_env(policy))
    report = await _boot_and_read(
        layout,
        (A.Plugin("s2-submit-result", "submit_result.mjs"),
         A.Plugin(AL.PLUGIN_ID, AL.PLUGIN_FILE),
         A.Plugin("s2-selfcheck", "selfcheck.mjs")),
        env)

    allowlist = report["allowlist"]
    surface = list(report["toolNames"])
    scope = allowlist.get("agentScope")
    assert isinstance(scope, dict), "开了收窄却没有 agent 作用域回显"
    assert scope["error"] in (None, "")
    assert sorted(scope["names"]) == sorted(set(surface) & set(AL.DEFAULT_ALLOWED)), \
        "agent 作用域可见面没收窄到清单：模型仍会看到清单外工具"
    assert "submit_result" in scope["names"]
    for rejected in ("web_search", "web_fetch", "subagent", "workflow", "send_message"):
        assert rejected not in scope["names"], rejected
    # 全局注册表面仍然是全量 harness（不能声称"全局工具面收敛"）
    assert len(surface) >= len(AL.DEFAULT_ALLOWED)
    assert AL.verify_echo(allowlist, policy, tool_names=surface) == ()


async def test_real_dsh_allowlist_disabled_echoes_absence(tmp_path: Path) -> None:
    """开关关 ⇒ 不挂插件 ⇒ 自检回显里没有白名单状态（S6 现状可复核）。"""
    reason = _skip_real()
    if reason:
        pytest.skip(reason)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    report = await _boot_and_read(
        layout,
        (A.Plugin("s2-submit-result", "submit_result.mjs"),
         A.Plugin("s2-selfcheck", "selfcheck.mjs")),
        {A.SELFCHECK_DIR_ENV: str(layout.selfcheck_dir),
         A.SELFCHECK_NONCE_ENV: "nonce-disabled",
         A.ATTEMPT_KEY_ENV: "RUN-TEST/N6/allowlist"})
    allowlist = report.get("allowlist")
    assert allowlist in (None, {}), "开关关但回显了白名单状态：状态与开关自相矛盾"
    policy = AL.policy_from_settings(None)
    assert AL.verify_echo(allowlist, policy, tool_names=list(report["toolNames"])) == ()


# ================================================================== 自检判据接线

def test_verify_session_reports_allowlist_problems(tmp_path: Path) -> None:
    """`verify_session` 必须把白名单回显并入准入 problems（缺回显 ⇒ 显式失败）。"""
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    report = {
        "plugin": "s2-selfcheck", "applied": True, "phase": "deferred", "pid": 1,
        "toolNames": list(SURFACE), "toolError": None,
        "sandboxDefaultMode": A.DEFAULT_SANDBOX_MODE, "sandboxModeError": None,
        "presetEcho": {"availability": "composition", "preset": A.DEFAULT_PRESET,
                       "resolved": {"preset": A.DEFAULT_PRESET,
                                    "sandbox": A.DEFAULT_SANDBOX_MODE,
                                    "approval": "ask"}},
        "home": str(layout.home),
    }
    path = layout.selfcheck_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    policy = AL.policy_from_settings({"enabled": True})
    result = SC.verify_session(layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
                               expected_preset=A.DEFAULT_PRESET, timeout_s=0.0,
                               allowlist_policy=policy)
    joined = "；".join(result.problems)
    assert not result.ok
    assert "白名单" in joined or AL.PLUGIN_ID in joined


def test_verify_session_accepts_clean_allowlist_echo(tmp_path: Path) -> None:
    """回显齐全 + deny 取证 ⇒ 白名单一项不进 problems（判据不误报）。"""
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    report = {
        "plugin": "s2-selfcheck", "applied": True, "phase": "deferred", "pid": 1,
        "toolNames": list(SURFACE), "toolError": None,
        "sandboxDefaultMode": A.DEFAULT_SANDBOX_MODE, "sandboxModeError": None,
        "presetEcho": {"availability": "composition", "preset": A.DEFAULT_PRESET,
                       "resolved": {"preset": A.DEFAULT_PRESET,
                                    "sandbox": A.DEFAULT_SANDBOX_MODE,
                                    "approval": "ask"}},
        "home": str(layout.home),
        "allowlist": _echo(),
    }
    path = layout.selfcheck_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    policy = AL.policy_from_settings({"enabled": True})
    result = SC.verify_session(layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
                               expected_preset=A.DEFAULT_PRESET, timeout_s=0.0,
                               allowlist_policy=policy)
    assert result.problems == ()


def test_verify_session_without_policy_unchanged(tmp_path: Path) -> None:
    """不传策略 ⇒ 旧行为完全不变（S1–S6 的既有准入判据不被本片改口径）。"""
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    report = {
        "plugin": "s2-selfcheck", "applied": True, "phase": "deferred", "pid": 1,
        "toolNames": ["read", "bash", "submit_result"], "toolError": None,
        "sandboxDefaultMode": A.DEFAULT_SANDBOX_MODE, "sandboxModeError": None,
        "presetEcho": {"availability": "composition", "preset": A.DEFAULT_PRESET,
                       "resolved": {"preset": A.DEFAULT_PRESET,
                                    "sandbox": A.DEFAULT_SANDBOX_MODE,
                                    "approval": "ask"}},
        "home": str(layout.home),
    }
    path = layout.selfcheck_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report), encoding="utf-8")
    result = SC.verify_session(layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
                               expected_preset=A.DEFAULT_PRESET, timeout_s=0.0)
    assert result.problems == ()
