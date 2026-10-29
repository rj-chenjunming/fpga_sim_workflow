"""DSH 后端（S1 骨架 + S2-a 结构化候选 + S5 受控准入）：配置锁定 + 进程/协议编排 + 候选收口。

边界（REV-13 §2 / REV-14 §2、B1/B5·DS-02）：
- 只做"起 attempt → 收帧 → 按**终态 + 提交**出候选"，**不**持有业务写权、不签闸门、
  不做业务校验（唯一判据是 `workflows/chunks/model_steps._validate`，此处不复制）；
- 候选只来自 `submit_result` 提交（`dsh_protocol.require_submission` 的唯一 `Submission`），
  **没有** `text` 占位、没有 `note`：没提交/未被接受 ⇒ 显式失败（`model_call_failed`）；
- **准入的唯一判据在本模块 `admit()`**（S5）：`enabled` + bin 指纹 + 版本匹配 +
  DS-08/09 静态自检 + mode 允许，任一不满足 ⇒ 可判的 `Admission` 失败；
  `agent_backends.select()` 只是消费它（不另写一套判据，红线 8）。
- attempt 可写档位 = `ATTEMPT_PINS`（`workspace-write` 双钉，B3/DS-09）：启动自检把**实际回显**
  逐字比对回钉死值，不符即拒；attempt home 不得含宿主 settings/凭据。
- 停执行（REV-13 §7.3/DS-05）：取消 ⇒ `dsh_process` 停进程组并确认；停不确认 ⇒
  `ExecutionUnknown` 上抛（不产生候选、不冒充"已停"）。

attempt 目录（`dsh_assets` 负责物化，本模块只读用）：bwrap 包裹把宿主 home 遮蔽，
插件与 patch 必须落在 attempt 目录内，侧信道 `DSH_SELFCHECK_DIR` 也在这里。

**随 attempt 自动起 Web 实例**（S8b 收口，REV-14 §3-D3 / §9.3；裁决 B3）：`prepare_attempt`
在 `mode=real` 且 `SETTINGS.dsh.web.enabled=true` 时调 `web_instance_ctl.ensure(...)`，
实例 home **就是**该 attempt 的 `dsh-home`（人在 GUI 里因此能看到这次 attempt 的会话）。
三条纪律：① 起失败**绝不阻断** attempt（Web 只是观测面）——记录里落 `web={state,reason,embed}`；
② 落账由 `ensure` 按当前 `(node, attempt)` 重写 `agent_instance.json`；③ attempt 结束**不 stop**
（人还要看）。

**attempt 隔离工作区**（S5-C2a，REV-13 §5.4）：`<run>/agent_workspaces/<node>/attempt-00000N/`
下 `{work, dsh-home, candidate, input}`；`cwd`/`home` **只由 Host 传入**（不许从任务文本或
客户端 hint 拼），`input/` 只放白名单材料（拷入前算 md5 进 attempt 记录）。`candidate/` 本片
不写入（S6 才写）。缺工作区/缺 home/材料越界 ⇒ 显式抛错，不回退。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from host import model_provider as MP
from host import paths as P
from . import BackendConfigurationError, BackendUnavailable, current_run_mode
from . import dsh_allowlist as AL
from . import dsh_assets as A
from . import dsh_process as DP
from . import dsh_protocol as DPR
from . import dsh_selfcheck as SC
from .base import CONTRACT_VERSION, BackendInfo, BackendRequest, ExecutionUnknown

LOG = logging.getLogger(__name__)

#: 配置允许字段（多一个就拒绝：避免"悄悄接受未实现开关"）
CONFIG_KEYS = frozenset({"enabled", "version", "node", "bin", "bin_sha256", "profile",
                         "timeout_s", "stop_grace_s", "wrap", "patches", "api_key_env",
                         "tool_allowlist",
                         # S7c：常驻 Web 实例的配置块（REV-16 §5.2 #2 / §9-6）。
                         # 只是"允许被启动"；**没有任何代码自启动它**（见 host/web_instance_ctl.py）。
                         "web"})
SETTINGS_FILE = P.LOOP_DIR / "SETTINGS.yaml"

#: 提交插件（B1：结构化结果的唯一通道；入口 id 由 `dsh_assets` 写进 patch 的 insert）
SUBMIT_PLUGIN = A.Plugin("s2-submit-result", "submit_result.mjs")
#: 启动自检插件（B2/B3；必须排在提交插件**之后**，deferred 快照才看得到 `submit_result`）
SELFCHECK_PLUGIN = A.Plugin("s2-selfcheck", "selfcheck.mjs")
#: S7b 工具白名单插件（裁决 B2；dispatch 钩子 + 收窄 agent 可见面）。
#: 只挂**一个**插件：开关关 ⇒ 不挂（= S6 现状），不靠插件内部"什么都不做"。
ALLOWLIST_PLUGIN = A.Plugin(AL.PLUGIN_ID, AL.PLUGIN_FILE)
#: 自检预算：插件 deferred 快照在 boot 后立刻写，20 s 是"给慢机留量"，超时即显式失败
SELFCHECK_TIMEOUT_S = 20.0
#: 生产 attempt 的钉死档位（B3/DS-09：`mode` + `defaultPreset` 双钉 workspace-write）。
#: 为什么不是 `A.Pins()`：默认档是"无 attempt 归属时的失败安全 read-only"，会放大/收窄语义；
#: 写权裁决（2026-10-28）是"只在每 attempt 隔离工作区内可写"，所以 attempt 路径显式用它。
ATTEMPT_PINS = A.ATTEMPT_PINS
#: dsh 包名（版本锁定的对象；换版本必须重新录制，不得沿用，REV-14 B7/A9）
DSH_PACKAGE = "@deepseek-ai/dsh"
#: 准入记录里的稳定 code（可判；界面/证据按它区分"按 mode 替身"与"准入失败"）
ADMITTED = "admitted"


def web_config_from_settings(document: dict | None = None):
    """S7c 适配层：把 `SETTINGS.dsh.web` 装成 `dsh_web_instance.WebInstanceConfig`。

    为什么在这里：`DshConfig` 是 frozen dataclass（不能挂属性），而 Web 实例配置要复用
    `dsh` 的 `node`/`bin`/`version`（版本锁定与指纹校验都在 `DshConfig`）。**不另立第二份
    node/bin 解析**（红线 8）；`dsh_web_instance` 有意不 import 本模块（避免双向依赖）。
    """
    from . import dsh_web_instance as WI

    return WI.config_from_settings(document, base=config_from_settings(document))


def _attest_probe_file() -> Path | None:
    """DS-10 遮蔽探针：优先用宿主 home 下**已存在**的仓内文件。

    本机 `$HOME` 只读（实测 `touch` ⇒ `Read-only file system`），不能临时造探针；
    用仓内 `AGENTS.md` 即可（它就在宿主 home 之下，P0 也用它做同一断言）。
    返回值必须位于宿主 home 之下，否则"遮蔽"没有意义 ⇒ 交给 `attest_wrap` 显式失败。
    """
    candidate = Path(P.TOOL_ROOT) / "AGENTS.md"
    try:
        if candidate.is_file() and Path.home().resolve() in candidate.resolve().parents:
            return candidate
    except OSError:
        pass
    return None


@dataclass(frozen=True)
class DshConfig:
    enabled: bool
    version: str
    node: Path
    bin: Path
    bin_sha256: str
    profile: str = "headless"
    timeout_s: float = 600.0
    stop_grace_s: float = 5.0
    wrap: bool = True
    patches: tuple[Path, ...] = ()
    api_key_env: str = "PUBLIC_API_KEY"
    #: S7b 工具白名单策略（缺省 = 未启用 = S6 现状；判据全在 `dsh_allowlist`，本类只持有）
    tool_allowlist: AL.AllowlistPolicy = AL.DISABLED_POLICY

    def verify(self, *, wrap_required: bool = True) -> None:
        """准入：enabled + 文件在 + 指纹匹配 + 版本声明 + **bwrap 包裹**。

        `wrap_required=True`（默认，且 `config_from_settings` 的唯一路径）意味着
        **配置里关掉包裹就不能启用 dsh**：否则一个布尔就静默关掉 DS-08/DS-09/DS-10
        三项准入并照常出候选（独立复核 P1-2 复现）。单测/诊断若要跑"无包裹"的桩进程，
        必须在代码里显式构造 `DshBackend(config, diagnostic_unwrapped=True)`，
        且候选会标 `isolation="unwrapped-diagnostic"`（不得冒充生产形态）。
        """
        if not self.enabled:
            raise BackendUnavailable("dsh 后端未启用（agent_runtime.dsh.enabled=false）")
        for label, path in (("node", self.node), ("bin", self.bin)):
            if not Path(path).is_file():
                raise BackendUnavailable("dsh 后端不可用：%s 不存在（%s）" % (label, path))
        actual = hashlib.sha256(Path(self.bin).read_bytes()).hexdigest()
        if actual != self.bin_sha256:
            raise BackendUnavailable(
                "dsh 后端不可用：bin 指纹不匹配（声明 %s…，实际 %s…）"
                % (self.bin_sha256[:12], actual[:12]))
        if not self.version:
            raise BackendConfigurationError("dsh 后端配置缺 version（版本锁定是准入条件）")
        if wrap_required and not self.wrap:
            raise BackendConfigurationError(
                "dsh 后端要求 bwrap 包裹（wrap=true）：包裹是 DS-08/DS-09/DS-10 的准入前提；"
                "单测/诊断请显式用 DshBackend(config, diagnostic_unwrapped=True)")


def config_from_settings(document: dict[str, Any] | None = None) -> DshConfig:
    """从 `SETTINGS.yaml` 读 `loop.agent_runtime.dsh`；未知字段/坏类型 ⇒ 配置错误。"""
    if document is None:
        try:
            document = yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            raise BackendConfigurationError("agent runtime: 无法读取有效 SETTINGS YAML") from None
    runtime = ((document or {}).get("loop") or {}).get("agent_runtime") or {}
    raw = runtime.get("dsh") or {}
    if not isinstance(raw, dict):
        raise BackendConfigurationError("agent_runtime.dsh 必须是 mapping")
    unknown = set(raw) - CONFIG_KEYS
    if unknown:
        raise BackendConfigurationError("agent_runtime.dsh 含未知字段：%s" % sorted(unknown))

    def _req(name: str) -> Any:
        if name not in raw:
            raise BackendConfigurationError("agent_runtime.dsh 缺必填字段 %r" % name)
        return raw[name]

    patches = tuple(Path(p) for p in (raw.get("patches") or ()))
    try:
        tool_allowlist = AL.policy_from_settings(raw.get("tool_allowlist"))
    except AL.AllowlistConfigError as exc:
        raise BackendConfigurationError(
            "agent_runtime.dsh.tool_allowlist 非法：%s" % exc) from None
    config = DshConfig(
        enabled=bool(_req("enabled")), version=str(_req("version")),
        node=Path(str(_req("node"))), bin=Path(str(_req("bin"))),
        bin_sha256=str(_req("bin_sha256")), profile=str(raw.get("profile") or "headless"),
        timeout_s=float(raw.get("timeout_s") or 600.0),
        stop_grace_s=float(raw.get("stop_grace_s") or 5.0),
        wrap=bool(raw.get("wrap", True)), patches=patches,
        api_key_env=str(raw.get("api_key_env") or "PUBLIC_API_KEY"),
        tool_allowlist=tool_allowlist)
    return config


def installed_version(dsh_bin: Path | str) -> tuple[str | None, str | None]:
    """读**锁定安装**的 `@deepseek-ai/dsh` 版本：返回 `(version, error)`。

    版本是准入条件（REV-14 A9/B7：0.1.x/0.2.x 不默认兼容，换版本必须重录）。
    从 bin 路径向上找带 `package.json` 的安装根 —— 找不到/坏 JSON/名字不符 ⇒ 显式原因，
    **不**拿配置里的声明值当"实际版本"（那是自己证明自己）。
    """
    for parent in Path(dsh_bin).parents:
        manifest = parent / "package.json"
        if not manifest.is_file():
            continue
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return None, "package.json 不可读或坏 JSON（%s）：%s" % (manifest, exc)
        if isinstance(document, dict) and document.get("name") == DSH_PACKAGE:
            version = document.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip(), None
            return None, "%s 的 package.json 缺 version（%s）" % (DSH_PACKAGE, manifest)
    return None, "从 %s 向上找不到 %s 的 package.json（安装树不完整）" % (dsh_bin, DSH_PACKAGE)


def runtime_fingerprint(config: "DshConfig") -> str:
    """运行时指纹（A2）：版本 + bin 指纹 + profile + attempt 钉死档位。

    为什么进请求记录：配置/档位一变，旧探测与旧结论就不再代表当前运行时（CL-01 的同一条纪律）。
    """
    payload = {"schema": "loop/dsh-runtime-fingerprint/1",
               "version": config.version, "bin_sha256": config.bin_sha256,
               "profile": config.profile,
               "pins": {"sandbox_mode": ATTEMPT_PINS.sandbox_mode,
                        "default_preset": ATTEMPT_PINS.default_preset}}
    # S7b：白名单策略进指纹（A2）。**只在启用时**加键 —— 开关关时保持 S6 旧指纹，
    # 让历史 attempt 记录仍可比；开关一变指纹必变，旧探测不再代表当前运行时。
    if config.tool_allowlist.enabled:
        payload["tool_allowlist"] = AL.policy_fingerprint(config.tool_allowlist)
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def allowlist_record(facts: dict[str, Any], policy: "AL.AllowlistPolicy"
                     ) -> dict[str, Any] | None:
    """attempt 记录里白名单的可复核投影（有消费者的最小集；开关关 ⇒ None，不留空字段）。"""
    if not policy.enabled:
        return None
    echo = facts.get(AL.REPORT_KEY)
    if not isinstance(echo, dict):
        return None
    scope = echo.get("agentScope") if isinstance(echo.get("agentScope"), dict) else {}
    probe = echo.get("probe") if isinstance(echo.get("probe"), dict) else {}
    return {"enabled": echo.get("enabled"), "allowed": echo.get("allowed"),
            "effective": echo.get("effective"),
            "deniedCount": len(echo.get("denied") or []),
            "agentScope": scope.get("names"), "probeCode": probe.get("code"),
            "policyFingerprint": AL.policy_fingerprint(policy)}


@dataclass(frozen=True)
class StaticSelfcheck:
    """准入期的 DS-08/DS-09 静态判定结果（不起进程）。`ok` 只由 `problems` 决定。"""

    problems: tuple[str, ...]
    facts: dict[str, Any]

    @property
    def ok(self) -> bool:
        return not self.problems


def static_selfcheck(config: "DshConfig") -> StaticSelfcheck:
    """DS-08/DS-09 中**不启进程就能判**的部分（准入前置；运行时回显另在 `execute` 里验）。

    判据（每条都能反向抽检）：
    1. attempt 双钉档位必须是 `workspace-write`/`workspace-write`（B3；单钉会被覆盖）；
    2. 由唯一生成实现产出的 patch 文本里必须真的出现这两条钉（不另拼 YAML）；
    3. 档位表自洽（钉的档必须在表里，且表的沙箱档 = 钉的沙箱档）；
    4. 两个插件源码在仓内（缺 ⇒ `submit_result` 不会出现在工具清单里，只 warning 不阻断）；
    5. 从 bin 能推出 `node_modules`（插件 import `@deepseek-ai/dsh-tools` 的解析根）。

    **不判**工具清单/preset 回显本身：那是运行时事实（deferred 快照），由 `execute` 的
    `on_start` 钩子逐次比对，缺则不派发（DS-08）。
    """
    problems: list[str] = []
    pins = ATTEMPT_PINS
    if not pins.sandbox_mode or pins.sandbox_mode != pins.default_preset:
        problems.append(
            "DS-09：attempt 双钉必须同档（sandbox_mode=%r，defaultPreset=%r）：只钉一半会被"
            "用户层覆盖（P3 实测）" % (pins.sandbox_mode, pins.default_preset))
    if pins.sandbox_mode != A.ATTEMPT_SANDBOX_MODE:
        problems.append("DS-09：attempt 档位必须是 %r（写权裁决：只在 attempt 工作区内可写），"
                        "实际 %r" % (A.ATTEMPT_SANDBOX_MODE, pins.sandbox_mode))
    text = A.pins_patch(pins)
    for needle in ("sandbox-policy", "mode: %s" % pins.sandbox_mode,
                   "permission", "defaultPreset: %s" % pins.default_preset):
        if needle not in text:
            problems.append("DS-09：钉死 patch 缺 %r（双钉不成立）" % needle)
    table = A.PRESET_TABLE.get(pins.default_preset)
    if table is None:
        problems.append("DS-09：钉死档 %r 不在 preset 表里（patch 的 config 是整块替换，"
                        "必须带完整 presets 表）" % pins.default_preset)
    elif table[0] != pins.sandbox_mode:
        problems.append("DS-09：preset %r 的沙箱档 %r ≠ 钉死沙箱档 %r（双钉自相矛盾）"
                        % (pins.default_preset, table[0], pins.sandbox_mode))
    mounted = [(SUBMIT_PLUGIN, "工具清单里不会有 submit_result")]
    if config.tool_allowlist.enabled:
        mounted.append((ALLOWLIST_PLUGIN,
                        "工具白名单不会生效（清单外调用不会被拒、可见面也不会收窄）"))
    mounted.append((SELFCHECK_PLUGIN, "启动自检不会回显工具清单/档位"))
    plugins = []
    for plugin, consequence in mounted:
        source = A.PLUGIN_SOURCE_DIR / plugin.filename
        plugins.append({"entry": plugin.entry_id, "source": str(source),
                        "present": source.is_file()})
        if not source.is_file():
            problems.append(
                "DS-08：插件源码缺失 %s（实测表现：`dsh: warning: 1 entry did not activate` "
                "不阻断启动，但%s）" % (source, consequence))
    node_modules = A.node_modules_for(config.bin)
    if node_modules is None:
        problems.append(
            "DS-08：从 dsh bin（%s）向上推不出 node_modules：插件 import "
            "`%s-tools` 解析不到，只会 `did not activate`（工具缺失不是准入）"
            % (config.bin, DSH_PACKAGE))
    return StaticSelfcheck(problems=tuple(problems), facts={
        "pins": {"sandbox_mode": pins.sandbox_mode, "default_preset": pins.default_preset},
        "pins_patch_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "plugins": plugins,
        "node_modules": str(node_modules) if node_modules is not None else None,
        "runtime_check": "per_attempt_deferred_snapshot",
    })


@dataclass(frozen=True)
class Admission:
    """一次准入判定的**全部事实**（`ok` 只由 `code == admitted` 决定）。

    `rule`/`code`/`requested`/`effective` 四个字段必须都在：界面与证据要能区分
    「按 mode 规则用替身」和「准入失败」，也要能看出"是谁做的决定"。
    """

    node: str
    code: str
    rule: str = "admission"
    requested: str = "dsh"
    effective: str = "dsh"
    checks: tuple[tuple[str, str], ...] = ()
    reason: str | None = None
    detail: tuple[str, ...] = ()
    version: str | None = None
    runtime_fingerprint: str | None = None

    @property
    def ok(self) -> bool:
        return self.code == ADMITTED

    def record(self) -> dict[str, Any]:
        """封存/界面投影（随 `backend.metadata()` 进请求记录；无秘密）。"""
        return {"rule": self.rule, "code": self.code, "requested": self.requested,
                "effective": self.effective, "node": self.node,
                "checks": {name: value for name, value in self.checks},
                "reason": self.reason or (self.detail[0] if self.detail else None),
                "detail": list(self.detail), "version": self.version,
                "runtime_fingerprint": self.runtime_fingerprint}

    def message(self) -> str:
        """可判的失败诊断：缺哪一项、钉死值/实际值（不回显配置原文/凭据）。"""
        missing = [name for name, value in self.checks if value != "ok"] or [self.code]
        return ("DSH backend unavailable: admission=%s node=%s missing=%s（准入要求 "
                "enabled=true + bin 指纹 + 版本匹配 + DS-08/09 静态自检 + mode 允许；"
                "不满足即失败，不回退 agently）%s"
                % (self.code, self.node, ",".join(missing),
                   "：" + "；".join(self.detail) if self.detail else ""))


def admit(config: "DshConfig", *, node: str) -> Admission:
    """DSH 后端的**唯一**准入判据（S5）：enabled → verify(包裹必填) → 版本 → 指纹 → 静态自检。

    只判"能不能用这个后端"，不判 mode（drill/live 的分层归 `select()` 的显式规则），
    也不判业务；任何一步不满足都返回可判的 `Admission`（调用方抛 `BackendUnavailable`）。
    """
    checks: list[tuple[str, str]] = []

    def fail(code: str, detail: list[str], **extra: Any) -> Admission:
        return Admission(node=node, code=code, checks=tuple(checks),
                         detail=tuple(detail), **extra)

    if not config.enabled:
        return fail("disabled", ["agent_runtime.dsh.enabled=false（实现存在不等于放行）"])
    checks.append(("enabled", "ok"))
    try:
        config.verify(wrap_required=True)
    except BackendUnavailable as exc:
        message = str(exc)
        code = "fingerprint_mismatch" if "指纹" in message else "not_verified"
        return fail(code, [message])
    except BackendConfigurationError as exc:
        return fail("not_verified", [str(exc)])
    checks.append(("verify", "ok"))
    version, error = installed_version(config.bin)
    if version is None:
        return fail("version_unknown", [error or "版本未知"])
    if version != config.version:
        return fail("version_mismatch",
                    ["声明 version=%r，安装树实际 %r（版本锁定：换版本必须重录，不得沿用旧结论）"
                     % (config.version, version)], version=version)
    checks.append(("version", "ok"))
    fingerprint = runtime_fingerprint(config)
    checks.append(("runtime_fingerprint", "ok"))
    selfcheck = static_selfcheck(config)
    if not selfcheck.ok:
        return fail("selfcheck_failed", list(selfcheck.problems),
                    version=version, runtime_fingerprint=fingerprint)
    checks.append(("selfcheck", "ok"))
    return Admission(node=node, code=ADMITTED, checks=tuple(checks),
                     version=version, runtime_fingerprint=fingerprint)


@dataclass(frozen=True)
class AttemptWorkspace:
    """一次 attempt 的隔离工作区（Host 分配；`execute` 的唯一 cwd/home 来源）。"""

    attempt_key: str
    root: Path
    layout: A.AttemptLayout
    materials: tuple[dict[str, Any], ...] = ()
    #: S8b：随 attempt 起的 Web 实例事实（**不含 token**）。
    #: `{state: ready|unavailable|disabled, reason, embed: iframe|new_tab_only, node, attempt, ...}`。
    #: 起不来只是"不可内嵌"，attempt 照常跑（REV-14 §9.3 / 裁决 B3）。
    web: dict[str, Any] = field(default_factory=dict)

    def execute_kwargs(self) -> dict[str, Any]:
        """传给 `DshBackend.execute` 的关键字（cwd/home 来自 Host，不来自任务文本）。"""
        return {"attempt_key": self.attempt_key, "cwd": self.layout.work,
                "home": self.layout.home}

    def record(self, *, run_dir: Path | str) -> dict[str, Any]:
        """封存投影（相对 run_dir，便于证据复核；不含宿主绝对路径）。"""
        base = Path(run_dir)

        def rel(path: Path) -> str:
            try:
                return Path(path).relative_to(base).as_posix()
            except ValueError:
                return str(path)

        return {"attempt_key": self.attempt_key, "root": rel(self.root),
                "work": rel(self.layout.work), "home": rel(self.layout.home),
                "candidate": rel(self.layout.candidate), "input": rel(self.layout.input_dir),
                "materials": list(self.materials),
                # S8b：随 attempt 起的 Web 实例（起不来 ⇒ 不可内嵌 + 原因；不含 token）
                "web": dict(self.web),
                # REV-14 §9.2：准入记录里的 home 来源判定（`[{name, source, basis}]`，
                # **零回显**：只有文件名/来源枚举/不含值的描述）。缺失 = 未判定（不等于通过）。
                "home_provenance": A.home_provenance(self.layout.home).record()}


def stage_inputs(layout: A.AttemptLayout, run_dir: Path | str, *,
                 materials: tuple[str, ...] = A.INPUT_MATERIALS) -> tuple[dict[str, Any], ...]:
    """把白名单材料**只读**拷进 attempt `input/`，逐件算 md5/size 供证据复核。

    判据（显式失败，不降级）：
    1. 源只能是**本 run 目录内**的普通文件（`..`/绝对路径/符号链接越界 ⇒ 抛错）；
    2. 只有白名单名字进得来（整目录拷贝被禁止）；
    3. 缺失的白名单材料**不补、不猜**，也不让整个 attempt 因此失败（该节点本来就不需要它），
       但缺件事实会记进 `materials` 便于下游判断"模型看到的是什么"；
    4. **派生物**（`dsh_assets.DERIVED_MATERIALS`）由 Host 从 run 产物投影而来（S7a：N6 不塞
       `n5_impact.json` 全文），记录里写明"派生自哪个源件 + 源件 md5/size"，源件坏/缺一律显式。
    """
    run_root = Path(run_dir).resolve()
    layout.input_dir.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []

    def _read_material(name: str) -> bytes | None:
        if Path(name).name != name or name in ("", ".", ".."):
            raise BackendConfigurationError(
                "dsh input 材料名非法（只接受 run 目录下的裸文件名）：%r" % (name,))
        source = run_root / name
        if source.is_symlink():
            raise BackendConfigurationError(
                "dsh input 材料是符号链接（拒绝逃逸）：%s" % source)
        if not source.is_file():
            return None
        try:
            if source.resolve() != (run_root / name).resolve():
                raise BackendConfigurationError("dsh input 材料越界：%s" % source)
            return source.read_bytes()
        except OSError as exc:
            raise BackendConfigurationError(
                "dsh input 材料不可读（%s）：%s" % (source, exc)) from None

    for name in materials:
        derived_from = A.DERIVED_MATERIALS.get(name)
        if derived_from is not None:
            payload = _read_material(derived_from)
            if payload is None:
                staged.append({"name": name, "present": False, "md5": None, "size": None,
                               "derived_from": {"name": derived_from, "md5": None, "size": None}})
                continue
            try:
                produced = A.derive_material(name, payload)
            except A.AssetError as exc:
                raise BackendConfigurationError(
                    "dsh input 派生物 %r 生成失败（源件 %r）：%s" % (name, derived_from, exc)
                ) from None
            (layout.input_dir / name).write_bytes(produced)
            staged.append({"name": name, "present": True,
                           "md5": hashlib.md5(produced).hexdigest(), "size": len(produced),
                           "derived_from": {"name": derived_from,
                                            "md5": hashlib.md5(payload).hexdigest(),
                                            "size": len(payload)}})
            continue
        payload = _read_material(name)
        if payload is None:
            staged.append({"name": name, "present": False, "md5": None, "size": None})
            continue
        (layout.input_dir / name).write_bytes(payload)
        staged.append({"name": name, "present": True,
                       "md5": hashlib.md5(payload).hexdigest(), "size": len(payload)})
    return tuple(staged)


def _schema_json(schema: Any) -> str:
    """把节点 schema 序列化进任务文本。

    `model_request.ask` 传下来的通常是 pydantic 模型**类**（不是 dict），
    这里按鸭子类型取 `model_json_schema()`；取不到可序列化 schema ⇒ 显式配置错误，
    不把类名字符串当 schema 糊进提示词（那会让模型拿到无意义的参数要求）。
    """
    if not isinstance(schema, dict):
        dump = getattr(schema, "model_json_schema", None)
        if callable(dump):
            schema = dump()
    if not isinstance(schema, dict):
        raise BackendConfigurationError(
            "dsh 任务文本需要可序列化的 schema（dict 或带 model_json_schema() 的对象），"
            "实际是 %r" % (type(schema).__name__,))
    return json.dumps(schema, ensure_ascii=False, indent=1, sort_keys=True)


#: 任务文本的固定首行（见 `_compose_task` 的"别以 `-` 开头"说明）。
TASK_HEADER = "[task] 以下是本次任务。"


def _compose_task(request: BackendRequest, *, attempt_key: str) -> str:
    """任务文本：上下文包 + **提交契约**（B1：结构化结果只能经 `submit_result` 回来）。

    `task_id` 逐字等于 `attempt_key`：提交门据此做身份 join（不符 ⇒ IdentityMismatch）。
    schema 也写进任务文本：模型拿到的参数要求与 Host 的 `_validate` 同源（此处不判业务）。

    **首行必须是固定标题**（C2 实测缺陷，2026-10-29）：dsh CLI 把 `--json` 的下一个 argv
    当值解析，而各节点的 `instruct` 经 `render_block` 后常以 `- ` 开头（列表项）⇒ 整段任务
    被当成选项解析，进程在 boot 阶段就以 `unknown option '- …'` 退出（rc=1、stderr 为空，
    极难定位）。所以任务文本首字符永远不是 `-`。
    """
    schema = request.schema
    if schema is None:
        schema_text = "（本节点未给 schema：payload 仍必须是 JSON 对象）"
    else:
        schema_text = _schema_json(schema)
    return (TASK_HEADER + "\n\n[instruct]\n%s\n\n[info]\n%s\n\n[input]\n%s\n\n[submit]\n"
            "做完分析后**必须**调用 submit_result 工具提交结果；没有被接受的提交，"
            "本次任务按失败处理（不会因为回复文本而被当成完成）：\n"
            "- task_id：必须逐字等于 %r（本次 attempt 标识，不得改写/缩写/省略）\n"
            "- summary：一句话结论\n"
            "- payload：**JSON 对象**（直接把对象作为参数传进来；**不要**传字符串化后的 JSON —— "
            "字符串会被提交门以 BadSubmission 拒绝，不得把结构化结果当字符串），"
            "必须符合下面的 schema\n"
            "[schema]\n%s\n"
            % (request.instruct, request.info,
               json.dumps(request.input_data, ensure_ascii=False, indent=1),
               attempt_key, schema_text))


class DshBackend:
    """`AgentBackend` 协议实现。默认不可用，需显式配置 + 准入（`admit`）通过。"""

    def __init__(self, config: DshConfig | None = None, *,
                 diagnostic_unwrapped: bool = False,
                 admission: Admission | None = None,
                 model_options: dict[str, Any] | None = None) -> None:
        """`diagnostic_unwrapped=True` 只给单测/诊断（stub CLI 不产生运行时事实）。

        生产路径（`config_from_settings` + `admit`）必须 `wrap=true`：见 `DshConfig.verify`。
        `admission` 是**准入证据**（谁做的决定、哪些检查通过），随 `metadata()` 进请求记录；
        诊断形态不传（不得冒充生产准入）。
        """
        self._config = config or config_from_settings()
        self._diagnostic_unwrapped = bool(diagnostic_unwrapped)
        self._admission = admission
        #: 生成 overlay 的模型参数覆盖（**仅** C2 探针用：如 P7 的小窗口阈值触发压缩）；
        #: 生产路径为 None（参数只来自 `host/model_provider`，不接受 SETTINGS 之外的私有开关）。
        self._model_options = dict(model_options or {}) or None
        if self._diagnostic_unwrapped and self._config.wrap:
            raise BackendConfigurationError(
                "diagnostic_unwrapped 与 wrap=true 矛盾（诊断模式要求 wrap=false）")
        self._config.verify(wrap_required=not self._diagnostic_unwrapped)
        self.info = BackendInfo(True, "dsh/%s" % self._config.version, "dsh", None)

    @property
    def config(self) -> DshConfig:
        return self._config

    @property
    def admission(self) -> Admission | None:
        """本次后端实例的准入证据（生产路径非 None；诊断形态恒 None）。"""
        return self._admission

    def metadata(self) -> dict[str, Any]:
        """随请求封存的实现指纹 + **A2 运行时事实**（契约版本/运行时指纹/准入证据）。"""
        meta: dict[str, Any] = {
            "name": "dsh", "version": self._config.version,
            "bin_sha256": self._config.bin_sha256,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "contract_version": CONTRACT_VERSION,
            "runtime_fingerprint": runtime_fingerprint(self._config)}
        if self._admission is not None:
            meta["admission"] = self._admission.record()
        return meta

    def _api_key(self) -> str | None:
        """本次 attempt 用的密钥值：**只进子进程 env**，不落文件、不打印。

        来源顺序：进程 env（`api_key_env` 名）→ `host/model_provider` 解析出的凭据
        （宿主 DSH 凭据库 `refs.<apiKeyEnv>`）。为什么允许第二条：凭据住在宿主凭据库，
        进程 env 通常没有；但**注入方式仍只有 env**（REV-14 D1：不落盘、不进 patch 文件）。
        """
        name = self._config.api_key_env
        secret = os.environ.get(name) if name else None
        if secret:
            return secret
        try:
            cfg = MP.resolve()
        except Exception:                      # 凭据层异常不影响诊断/脱敏路径
            return None
        return getattr(cfg, "_api_key", None) or None

    def redact(self, message: str) -> str:
        secret = self._api_key()
        return message.replace(secret, "[redacted]") if secret else message

    def _failure(self, message: str, **extra: Any) -> dict[str, Any]:
        """显式失败（不返回假候选、不回退到文本）：error 必须 redact。"""
        return {"standin": False, "provider": "dsh/%s" % self._config.version,
                "model_call_failed": True, "error": self.redact(message), **extra}

    def _contract_problems(self, request: BackendRequest, *, attempt_key: str) -> list[str]:
        """A2 准入（REV-13 §5.2）：不认识的契约版本 / 身份对不上 ⇒ 显式失败，不出候选。

        为什么在**执行前**判：身份 join 失败意味着"提交回来的不是这次 attempt 的结果"，
        与 `submit_result` 的 `task_id` 校验同一条纪律（不复制业务判据，只比身份）。
        身份从**参数**比（不存实例状态：同一 backend 被复用/并发时不会互相覆盖）。
        """
        problems: list[str] = []
        version = request.contract_version
        if version is not None and version != CONTRACT_VERSION:
            problems.append("不支持的 contract_version=%r（本实现只认 %r）"
                            % (version, CONTRACT_VERSION))
        identity = request.identity
        if identity is not None and identity.attempt_key not in (None, ""):
            if identity.attempt_key != attempt_key:
                problems.append("identity.attempt_key=%r 与本次 attempt %r 不一致（身份 join 失败，"
                                "不得把别次结果当本次候选）"
                                % (identity.attempt_key, attempt_key))
        return problems

    def prepare_attempt(self, run_dir: Path | str, node: str, sequence: int, *,
                        attempt_key: str | None = None,
                        materials: tuple[str, ...] | None = None,
                        sources: tuple[tuple[Path, str], ...] = ()) -> AttemptWorkspace:
        """分配（并物化）一次 attempt 的隔离工作区；**cwd/home 的唯一来源**。

        为什么在 backend 里：布局常量（`dsh_assets`）与 attempt 资产物化是同一个 owner；
        Host（`model_request`）只负责"给哪个 run/node/第几次尝试 + attempt 身份"，
        **不**各自拼路径、**不**各自拼 attempt 身份（`attempt_key` 由 Host 传，缺省才派生：
        提交门的 `task_id` join 与 A2 `identity.attempt_key` 必须是同一个值，不许两处漂移）。

        `materials` 缺省走**每节点白名单** `dsh_assets.materials_for(node)`（S7a：N6 只拿派生
        摘要，不拿 345 KB 的 `n5_impact.json` 全文）；显式传入只用于用例/诊断，生产调用方不拼。
        `agent_calls/**` 是封存记录目录，这里绝不往里放工作区（见 `A.WORKSPACE_DIRNAME`）。
        """
        root = A.workspace_root(run_dir, node, int(sequence))
        layout = A.AttemptLayout.under(root)
        layout.prepare()
        chosen = A.materials_for(node) if materials is None else tuple(materials)
        staged = list(stage_inputs(layout, run_dir, materials=chosen))
        if sources:
            # 外部只读源件（N6 目标用例源件）：**逐个显式声明**，不整目录、不跟随链接
            staged.extend(A.stage_sources(layout, tuple(sources)))
        key = attempt_key or "%s/%s/%d" % (Path(run_dir).name, node, int(sequence))
        # **DS-09 必须先于起资源**（独立复核 P1；AGENTS §2「拒绝发生在提交前」+ REV-14 §9.3）：
        # 起 Web 实例会让一个 dsh 进程**读这个 home**，所以 home 里若已有该拒的宿主件，
        # 必须在起进程**之前**拒（否则"先读了再拒"，隔离意图已破）。判据只有一处
        # （`dsh_assets.home_problems`，本模块不重算）。
        # 顺序效果：首次 attempt home 为空 ⇒ 无问题 ⇒ 起实例 ⇒ dsh 自生成 `.credentials.yaml`
        # ⇒ 之后 `materialize`/`_preflight` 判 `dsh_generated` **放行**（共用 home 的落地前提）；
        # 预先复制了宿主 `settings.yaml`/宿主凭据 ⇒ **起进程前**就显式失败。
        problems = A.home_problems(layout.home)
        if problems:
            raise A.AssetError("DS-09 attempt home 不合规（起实例之前就拒）：%s"
                               % "；".join(problems))
        # S8b（D3 收口 / 裁决 B3）：随 attempt 起本地 Web 实例。
        web = self._web_attempt(run_dir, node, int(sequence))
        return AttemptWorkspace(attempt_key=key, root=root, layout=layout,
                                materials=tuple(staged), web=web)

    def _web_attempt(self, run_dir: Path | str, node: str, attempt: int) -> dict[str, Any]:
        """随 attempt 自动起本地 Web 实例（S8b 收口，REV-14 §3-D3 / §9.3；裁决 B3）。

        准入判据只有两条：`run_mode == "real"` **且** `SETTINGS.dsh.web.enabled=true`
        （后者由 `web_instance_ctl.ensure` 自己判并抛 `web_disabled`：本模块不复制配置判据）。

        **失败绝不阻断 attempt**（Web 只是"人看/人说"的观测面，不是执行通道）：
        `WebCtlError` ⇒ 记录 `reason` 枚举；其它异常 ⇒ 记 `web_start_failed` + 异常**类名**
        （异常消息可能带端点/凭据片段，**不进记录、不回显**）。返回的事实**不含 token**
        （token 只进受管元数据 `agent_instance.json`）。

        **已知边界（如实登记）**：实例登记表按 `(run, node)` 建键，换 node 不释放先前节点
        ⇒ 一次 real run 走 N 个节点会同时留 N 个 loopback 实例（进程数随节点数增长）。
        这是裁决 B3「attempt 结束不 stop（人还要看）」的预期后果；收干净靠
        `web_instance_ctl.stop_all()` / 逐 `(run, node)` 的 `stop()`。
        """
        if current_run_mode() != "real":
            return {"state": "disabled", "reason": "run_mode_not_real",
                    "embed": "new_tab_only", "node": node, "attempt": int(attempt)}
        # 延迟 import：`web_instance_ctl` 反向 import 本模块（模块级 import 会成环）
        from host import web_instance_ctl as WC

        try:
            facts = WC.ensure(run_dir, node, int(attempt))
        except WC.WebCtlError as exc:
            state = "disabled" if exc.reason == "web_disabled" else "unavailable"
            LOG.warning("dsh web instance not available: node=%s attempt=%s reason=%s",
                        node, attempt, exc.reason)
            return {"state": state, "reason": exc.reason, "embed": "new_tab_only",
                    "node": node, "attempt": int(attempt)}
        except Exception as exc:                 # noqa: BLE001 - 观测面失败一律不阻断 attempt
            LOG.warning("dsh web instance start failed: node=%s attempt=%s error=%s",
                        node, attempt, type(exc).__name__)
            return {"state": "unavailable", "reason": "web_start_failed",
                    "detail": type(exc).__name__, "embed": "new_tab_only",
                    "node": node, "attempt": int(attempt)}
        # 只留可审计、无秘密的字段（token/完整 home 路径不进 attempt 记录）
        return {"state": "ready", "reason": None, "embed": "iframe",
                "node": node, "attempt": int(attempt),
                "host": facts.get("host"), "port": facts.get("port"),
                # S8h（REV-14 §9.4）：GUI 里的模型配置是否已继承（不可用时界面如实提示）
                "provider": facts.get("provider"),
                "reused": bool(facts.get("reused"))}

    def _provider(self):
        """本次 attempt 的 provider 解析结果（**唯一来源** `host/model_provider`）。"""
        cfg = MP.resolve()
        if not cfg.available:
            raise A.AssetError(
                "dsh attempt 需要 provider overlay，但 model_provider 不可用：%s"
                % (cfg.reason or "原因未给出"))
        return cfg

    def _proxy_env(self) -> dict[str, str]:
        """把 provider 的代理配置带进 attempt env（**必须显式**）。

        为什么必须：宿主 `.env` 的代理不会被 Node 的 fetch/undici 自动读取（`trust_env=False`
        同源问题，P0 实测成功形态里就显式传了 `HTTPS_PROXY`）；不带就 `dsh: TRANSPORT:
        Connection error`（C2 首跑实测）。只传代理地址，不传凭据；loopback 目标不带（MP 已判定）。
        """
        proxy = (self._provider().proxy or "").strip()
        if not proxy:
            return {}
        return {"HTTPS_PROXY": proxy, "HTTP_PROXY": proxy,
                "https_proxy": proxy, "http_proxy": proxy}

    def _provider_overlay(self) -> A.ProviderOverlay:
        """生成 attempt 的 provider overlay：**唯一来源**是 `host/model_provider` 的解析结果。

        为什么生成（而不是静态 patch 文件 + SETTINGS 引用）：SETTINGS 纪律反对"仓里再抄一份
        内部端点"（会漂移）；生成式同时保证**只写 `apiKeyEnv` 的名字、不写密钥值**。
        provider 不可用/端点缺失 ⇒ `AssetError`（execute 会显式失败，不猜端点、不发请求）。
        """
        cfg = self._provider()
        return A.provider_overlay(family=cfg.family, base_url=cfg.base_url, model=cfg.model,
                                  api_key_env=cfg.api_key_env,
                                  model_options=self._model_options)

    def _layout_for(self, cwd: Path, home: Path) -> A.AttemptLayout:
        """attempt 布局校验（不物化）：`root = cwd.parent`，`home` 必须同属该 root。"""
        root = Path(cwd).parent
        if Path(home).parent != root:
            raise BackendConfigurationError(
                "dsh attempt 布局错误：home 必须与 cwd 同属一个 attempt root"
                "（cwd.parent=%s，home.parent=%s）" % (root, Path(home).parent))
        return A.AttemptLayout.under(root)

    def _plugins(self) -> tuple[A.Plugin, ...]:
        """本次 attempt 要挂的插件。顺序固定：提交 → 白名单（启用时）→ 自检。

        为什么自检必须最后：它的 deferred 快照要看到 `submit_result` 工具与
        `s7ToolAllowlist` 服务（白名单插件 apply 时 provide）；顺序反了自检只会回显 None。
        """
        if self._config.tool_allowlist.enabled:
            return (SUBMIT_PLUGIN, ALLOWLIST_PLUGIN, SELFCHECK_PLUGIN)
        return (SUBMIT_PLUGIN, SELFCHECK_PLUGIN)

    def _spec(self, request: BackendRequest, *, attempt_key: str,
              cwd: Path, home: Path) -> DP.AttemptSpec:
        """attempt 资产物化 + 进程规格。

        - 插件/侧信道都在 attempt 目录内（包裹内宿主路径与仓内路径都不可写），
          并用 `asset_dirs`/`state_dirs` 把它们显式 bind 进包裹：
          attempt 目录若落在 `--tmpfs /tmp` 或宿主 home 下，不显式 bind 时 dsh 读不到自己的
          patch（实测形态 `failed to read overlay … ENOENT` ⇒ 插件只出 "did not activate"）；
        - patch 顺序：钉死（B3 双钉 = `ATTEMPT_PINS`/workspace-write）→ `config.patches`
          （外部 overlay 副本）→ 插件 insert（提交插件在前、自检插件在后，自检的 deferred
          快照才看得到 `submit_result`）。
        """
        layout = self._layout_for(cwd, home)
        # 候选落点必须在 cwd（work）之内：dsh 应用层的 workspace-write 边界就是工作区，
        # 兄弟目录要 danger-full-access 审批（headless 必 unavailable）——真机已复现。
        A.check_layout(layout)
        if Path(layout.candidate) != Path(cwd) / "candidate":
            raise BackendConfigurationError(
                "candidate 必须是 cwd/candidate（实际 %s，cwd=%s）"
                % (layout.candidate, cwd))
        assets = A.materialize(layout, pins=ATTEMPT_PINS,
                               provider=(None if self._diagnostic_unwrapped
                                         else self._provider_overlay()),
                               plugins=self._plugins(),
                               extra_patches=tuple(self._config.patches),
                               node_modules=A.node_modules_for(self._config.bin))
        # nonce 是本次 attempt 的一次性身份：插件必须回显，Host 逐字比对
        # （否则复用 attempt root 时旧快照会被当准入 —— 独立复核 P1-1）。
        # 只进 spec 的 env，不存实例状态：同一 backend 实例被复用/并发时不会互相覆盖。
        nonce = uuid.uuid4().hex
        return DP.AttemptSpec(
            attempt_key=attempt_key, cwd=Path(cwd), home=Path(home),
            task=_compose_task(request, attempt_key=attempt_key),
            dsh_bin=self._config.bin, node=self._config.node,
            patches=assets.patch_files, profile=self._config.profile,
            timeout_s=self._config.timeout_s, stop_grace_s=self._config.stop_grace_s,
            wrap=self._config.wrap,
            # 密钥只进 env（不落文件、不进 patch）；来源见 `_api_key()`
            api_key=(os.environ.get(self._config.api_key_env)
                     if self._diagnostic_unwrapped else self._api_key()),
            api_key_env=self._config.api_key_env,
            proxy_env=({} if self._diagnostic_unwrapped else self._proxy_env()),
            env_extra={A.SELFCHECK_DIR_ENV: str(layout.selfcheck_dir),
                       A.SELFCHECK_NONCE_ENV: nonce,
                       A.ATTEMPT_KEY_ENV: attempt_key,
                       # S7b：策略只经 env 传给插件（唯一编码实现 `AL.render_env`；
                       # 关掉时返回 {}，进程 env 与 S6 逐字相同）
                       **AL.render_env(self._config.tool_allowlist)},
            # `input/` 是**授权材料面**：与 patch/插件资产分开（语义不同），同样以 `--ro-bind`
            # 进包裹 —— 模型只能读材料，不能改材料（attempt 目录也可能落在被 tmpfs 遮蔽的位置）。
            asset_dirs=(layout.plugin_dir, layout.patch_dir),
            material_dirs=(layout.input_dir,),
            # 候选落点是**模型可写**的唯一业务目录（S6 导入只读它）。它在 `work/` 内 ⇒ 已被 cwd
            # 的 `--bind` 覆盖；这里仍显式列出，让"模型可写业务落点"在 argv/证据里可见（幂等 bind）。
            # 只挂 `candidate/` 这一层，不放宽到 attempt root / run_dir。
            write_dirs=(layout.candidate,),
            state_dirs=(layout.selfcheck_dir,))

    async def _preflight(self, spec: DP.AttemptSpec, layout: A.AttemptLayout,
                         *, contract: dict[str, Any] | None = None
                         ) -> dict[str, Any] | None:
        """spawn 之前的准入（DS-09/DS-10）：不通过就返回显式失败，不启动进程、不出候选。

        包裹模式（`wrap=true`，仓内默认）下两项硬性：home 最小化（DS-09）、bwrap 自证（DS-10）；
        启动自检（DS-08）在 `on_start` 里做（见 `execute`）。`wrap=false` **只能**经代码里显式
        `diagnostic_unwrapped=True` 进入（配置路径已被 `verify` 拒绝），此时候选标
        `isolation="unwrapped-diagnostic"`，不假装自检通过。
        """
        if self._diagnostic_unwrapped:
            # 只有代码里显式声明的诊断模式才跳过；配置布尔**不能**走到这里（verify 已拦）
            return None
        extra = {"contract": contract} if contract is not None else {}
        problems = SC.verify_home(layout.home)
        if problems:
            return self._failure("DS-09 attempt home 不合规：%s" % "；".join(problems), **extra)
        probe_file = _attest_probe_file()
        # 同步探针不能卡事件循环（最长 2×60 s）：放线程池跑
        attest = await asyncio.to_thread(SC.attest_wrap, spec, probe_file=probe_file)
        if not attest.ok:
            return self._failure("DS-10 包裹自证失败：%s" % "；".join(attest.problems), **extra)
        return None

    async def execute(self, request: BackendRequest, *, attempt_key: str = "adhoc/1",
                      cwd: Path | None = None, home: Path | None = None) -> dict[str, Any]:
        """起一次 attempt；失败一律显式（`model_call_failed`），不返回假候选。

        - A2（REV-13 §5.2）：不认识的契约版本/身份不符 ⇒ 起进程前就显式失败；
          请求的 A2 投影随候选一起回显（`contract`），由 Host 封存。
        - 停执行（§7.3/DS-05）：取消会真的停掉进程组；**停不确认** ⇒ `ExecutionUnknown`
          上抛（不产生候选、不冒充"已停"），由控制层落 `execution_unknown` 并禁止重发。
        """
        if cwd is None or home is None:
            raise BackendConfigurationError(
                "DshBackend.execute 需要显式 cwd 与 home（每 attempt 独立；不得落到宿主目录）")
        problems = self._contract_problems(request, attempt_key=attempt_key)
        if problems:
            return self._failure("dsh 请求契约不合规：%s" % "；".join(problems),
                                 contract=request.contract())
        layout = self._layout_for(Path(cwd), Path(home))
        try:
            spec = self._spec(request, attempt_key=attempt_key,
                              cwd=Path(cwd), home=Path(home))
        except A.AssetError as exc:
            return self._failure("dsh attempt 资产物化失败：%s" % exc,
                                 contract=request.contract())
        rejected = await self._preflight(spec, layout, contract=request.contract())
        if rejected is not None:
            return rejected

        selfcheck: dict[str, Any] | None = None
        on_start = None
        if not self._diagnostic_unwrapped:
            # 身份从**实际传给子进程的 env** 取，保证"验的就是 run 的那份"
            expected_nonce = spec.env_extra.get(A.SELFCHECK_NONCE_ENV)
            expected_attempt = spec.env_extra.get(A.ATTEMPT_KEY_ENV)
            if not expected_nonce or not expected_attempt:
                return self._failure(
                    "dsh attempt 缺自检身份（nonce/attemptKey）：不得以'进程起来了'当准入",
                    contract=request.contract())

            async def on_start() -> None:                    # noqa: D401 - 准入钩子
                nonlocal selfcheck
                # DS-08/09：期望档位取**本次 attempt 的钉死值**（ATTEMPT_PINS，workspace-write），
                # 不是模块的保守默认（read-only）；回显不符即拒。
                result = await SC.averify_session(
                    layout, timeout_s=SELFCHECK_TIMEOUT_S,
                    expected_mode=ATTEMPT_PINS.sandbox_mode,
                    expected_preset=ATTEMPT_PINS.default_preset,
                    expected_nonce=expected_nonce,
                    expected_attempt_key=expected_attempt,
                    # S7b：白名单回显也进准入（缺回显/无效面/无 deny 取证 ⇒ 显式失败）
                    allowlist_policy=self._config.tool_allowlist)
                result.require_ok()
                facts = result.facts
                echo = facts.get("presetEcho") if isinstance(facts.get("presetEcho"), dict) else {}
                # 只保留有消费者的投影：attempt 记录/证据可复核"当时看到什么、钉的是什么"
                selfcheck = {"phase": facts.get("phase"),
                             "toolCount": len(facts.get("toolNames") or []),
                             "sandboxDefaultMode": facts.get("sandboxDefaultMode"),
                             "presetEcho": facts.get("presetEcho"),
                             "pinnedMode": ATTEMPT_PINS.sandbox_mode,
                             "pinnedPreset": ATTEMPT_PINS.default_preset,
                             "echoedPreset": echo.get("preset"),
                             "toolAllowlist": allowlist_record(
                                 facts, self._config.tool_allowlist)}

        try:
            outcome = await DP.run_attempt(spec, on_start=on_start)
        except ExecutionUnknown:
            # 停不确认：不得降级成普通失败（那会让控制层记 applied / 自动重发）。原样上抛。
            raise
        except DP.LeftoverChildren as exc:
            raise ExecutionUnknown(
                "execution_unknown：%s（停止无法确认 ⇒ 禁止自动重发）" % exc) from exc
        except (DPR.ProtocolError, DP.AttemptError, SC.SelfCheckFailed) as exc:
            return self._failure(str(exc), contract=request.contract())
        if outcome.status != "completed":
            code = "，code=%s" % outcome.code if outcome.code else ""
            return self._failure("dsh 未完成（reason=%s%s）：%s"
                                 % (outcome.reason, code,
                                    outcome.message or "无诊断"),
                                 contract=request.contract())
        # 完成判据（B5/DS-02）：终态 completed **且** 恰一条被接受的提交；
        # 提交门是唯一实现（dsh_protocol），这里不复制判据。
        try:
            submission = DPR.require_submission(outcome, expect_task_id=attempt_key)
        except DPR.ProtocolError as exc:
            return self._failure(str(exc), contract=request.contract())
        payload = {"standin": False, "provider": "dsh/%s" % self._config.version,
                   "plugin": "dsh", "data": submission.payload,
                   "task_id": submission.task_id, "summary": submission.summary,
                   "session_id": outcome.session_id, "usage": outcome.usage,
                   "isolation": ("unwrapped-diagnostic" if self._diagnostic_unwrapped
                                 else "bwrap"),
                   # A2：请求的契约投影随候选回显，由 Host 封存（旧记录缺省 legacy/unknown）
                   "contract": request.contract()}
        if selfcheck is not None:
            payload["selfcheck"] = selfcheck
        return payload
