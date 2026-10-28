"""DSH 后端（S1 骨架 + S2-a 结构化候选）：配置锁定 + 进程/协议编排 + 候选收口。

边界（REV-13 §2 / REV-14 §2、B1/B5·DS-02）：
- 只做"起 attempt → 收帧 → 按**终态 + 提交**出候选"，**不**持有业务写权、不签闸门、
  不做业务校验（唯一判据是 `workflows/chunks/model_steps._validate`，此处不复制）；
- 候选只来自 `submit_result` 提交（`dsh_protocol.require_submission` 的唯一 `Submission`），
  **没有** `text` 占位、没有 `note`：没提交/未被接受 ⇒ 显式失败（`model_call_failed`）；
- 不进入 `agent_backends.select()` 的可用路径：未显式启用/指纹不匹配 ⇒ `BackendUnavailable`。

attempt 目录（`dsh_assets` 负责物化，本模块只读用）：bwrap 包裹把宿主 home 遮蔽，
插件与 patch 必须落在 attempt 目录内，侧信道 `DSH_SELFCHECK_DIR` 也在这里。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from host import paths as P
from . import BackendConfigurationError, BackendUnavailable
from . import dsh_assets as A
from . import dsh_process as DP
from . import dsh_protocol as DPR
from . import dsh_selfcheck as SC
from .base import BackendInfo, BackendRequest

#: 配置允许字段（多一个就拒绝：避免"悄悄接受未实现开关"）
CONFIG_KEYS = frozenset({"enabled", "version", "node", "bin", "bin_sha256", "profile",
                         "timeout_s", "stop_grace_s", "wrap", "patches", "api_key_env"})
SETTINGS_FILE = P.LOOP_DIR / "SETTINGS.yaml"

#: 提交插件（B1：结构化结果的唯一通道；入口 id 由 `dsh_assets` 写进 patch 的 insert）
SUBMIT_PLUGIN = A.Plugin("s2-submit-result", "submit_result.mjs")
#: 启动自检插件（B2/B3；必须排在提交插件**之后**，deferred 快照才看得到 `submit_result`）
SELFCHECK_PLUGIN = A.Plugin("s2-selfcheck", "selfcheck.mjs")
#: 自检预算：插件 deferred 快照在 boot 后立刻写，20 s 是"给慢机留量"，超时即显式失败
SELFCHECK_TIMEOUT_S = 20.0


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
    config = DshConfig(
        enabled=bool(_req("enabled")), version=str(_req("version")),
        node=Path(str(_req("node"))), bin=Path(str(_req("bin"))),
        bin_sha256=str(_req("bin_sha256")), profile=str(raw.get("profile") or "headless"),
        timeout_s=float(raw.get("timeout_s") or 600.0),
        stop_grace_s=float(raw.get("stop_grace_s") or 5.0),
        wrap=bool(raw.get("wrap", True)), patches=patches,
        api_key_env=str(raw.get("api_key_env") or "PUBLIC_API_KEY"))
    return config


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


def _compose_task(request: BackendRequest, *, attempt_key: str) -> str:
    """任务文本：上下文包 + **提交契约**（B1：结构化结果只能经 `submit_result` 回来）。

    `task_id` 逐字等于 `attempt_key`：提交门据此做身份 join（不符 ⇒ IdentityMismatch）。
    schema 也写进任务文本：模型拿到的参数要求与 Host 的 `_validate` 同源（此处不判业务）。
    """
    schema = request.schema
    if schema is None:
        schema_text = "（本节点未给 schema：payload 仍必须是 JSON 对象）"
    else:
        schema_text = _schema_json(schema)
    return ("%s\n\n[info]\n%s\n\n[input]\n%s\n\n[submit]\n"
            "做完分析后**必须**调用 submit_result 工具提交结果；没有被接受的提交，"
            "本次任务按失败处理（不会因为回复文本而被当成完成）：\n"
            "- task_id：必须逐字等于 %r（本次 attempt 标识，不得改写/缩写/省略）\n"
            "- summary：一句话结论\n"
            "- payload：JSON 对象，必须符合下面的 schema\n"
            "[schema]\n%s\n"
            % (request.instruct, request.info,
               json.dumps(request.input_data, ensure_ascii=False, indent=1),
               attempt_key, schema_text))


class DshBackend:
    """`AgentBackend` 协议实现。默认不可用，需显式配置且指纹匹配。"""

    def __init__(self, config: DshConfig | None = None, *,
                 diagnostic_unwrapped: bool = False) -> None:
        """`diagnostic_unwrapped=True` 只给单测/诊断（stub CLI 不产生运行时事实）。

        生产路径（`config_from_settings`）必须 `wrap=true`：见 `DshConfig.verify`。
        """
        self._config = config or config_from_settings()
        self._diagnostic_unwrapped = bool(diagnostic_unwrapped)
        if self._diagnostic_unwrapped and self._config.wrap:
            raise BackendConfigurationError(
                "diagnostic_unwrapped 与 wrap=true 矛盾（诊断模式要求 wrap=false）")
        self._config.verify(wrap_required=not self._diagnostic_unwrapped)
        self.info = BackendInfo(True, "dsh/%s" % self._config.version, "dsh", None)

    @property
    def config(self) -> DshConfig:
        return self._config

    def metadata(self) -> dict[str, str]:
        return {"name": "dsh", "version": self._config.version,
                "bin_sha256": self._config.bin_sha256,
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def redact(self, message: str) -> str:
        secret = os.environ.get(self._config.api_key_env)
        return message.replace(secret, "[redacted]") if secret else message

    def _failure(self, message: str) -> dict[str, Any]:
        """显式失败（不返回假候选、不回退到文本）：error 必须 redact。"""
        return {"standin": False, "provider": "dsh/%s" % self._config.version,
                "model_call_failed": True, "error": self.redact(message)}

    def _layout_for(self, cwd: Path, home: Path) -> A.AttemptLayout:
        """attempt 布局校验（不物化）：`root = cwd.parent`，`home` 必须同属该 root。"""
        root = Path(cwd).parent
        if Path(home).parent != root:
            raise BackendConfigurationError(
                "dsh attempt 布局错误：home 必须与 cwd 同属一个 attempt root"
                "（cwd.parent=%s，home.parent=%s）" % (root, Path(home).parent))
        return A.AttemptLayout.under(root)

    def _spec(self, request: BackendRequest, *, attempt_key: str,
              cwd: Path, home: Path) -> DP.AttemptSpec:
        """attempt 资产物化 + 进程规格。

        - 插件/侧信道都在 attempt 目录内（包裹内宿主路径与仓内路径都不可写），
          并用 `asset_dirs`/`state_dirs` 把它们显式 bind 进包裹：
          attempt 目录若落在 `--tmpfs /tmp` 或宿主 home 下，不显式 bind 时 dsh 读不到自己的
          patch（实测形态 `failed to read overlay … ENOENT` ⇒ 插件只出 "did not activate"）；
        - patch 顺序：钉死（B3 双钉）→ `config.patches`（外部 overlay 副本）→ 插件 insert
          （提交插件在前、自检插件在后，自检的 deferred 快照才看得到 `submit_result`）。
        """
        layout = self._layout_for(cwd, home)
        assets = A.materialize(layout, pins=A.Pins(),
                               plugins=(SUBMIT_PLUGIN, SELFCHECK_PLUGIN),
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
            api_key=os.environ.get(self._config.api_key_env),
            api_key_env=self._config.api_key_env,
            env_extra={A.SELFCHECK_DIR_ENV: str(layout.selfcheck_dir),
                       A.SELFCHECK_NONCE_ENV: nonce,
                       A.ATTEMPT_KEY_ENV: attempt_key},
            asset_dirs=(layout.plugin_dir, layout.patch_dir),
            state_dirs=(layout.selfcheck_dir,))

    async def _preflight(self, spec: DP.AttemptSpec,
                         layout: A.AttemptLayout) -> dict[str, Any] | None:
        """spawn 之前的准入（DS-09/DS-10）：不通过就返回显式失败，不启动进程、不出候选。

        包裹模式（`wrap=true`，仓内默认）下两项硬性：home 最小化（DS-09）、bwrap 自证（DS-10）；
        启动自检（DS-08）在 `on_start` 里做（见 `execute`）。`wrap=false` **只能**经代码里显式
        `diagnostic_unwrapped=True` 进入（配置路径已被 `verify` 拒绝），此时候选标
        `isolation="unwrapped-diagnostic"`，不假装自检通过。
        """
        if self._diagnostic_unwrapped:
            # 只有代码里显式声明的诊断模式才跳过；配置布尔**不能**走到这里（verify 已拦）
            return None
        problems = SC.verify_home(layout.home)
        if problems:
            return self._failure("DS-09 attempt home 不合规：%s" % "；".join(problems))
        probe_file = _attest_probe_file()
        # 同步探针不能卡事件循环（最长 2×60 s）：放线程池跑
        attest = await asyncio.to_thread(SC.attest_wrap, spec, probe_file=probe_file)
        if not attest.ok:
            return self._failure("DS-10 包裹自证失败：%s" % "；".join(attest.problems))
        return None

    async def execute(self, request: BackendRequest, *, attempt_key: str = "adhoc/1",
                      cwd: Path | None = None, home: Path | None = None) -> dict[str, Any]:
        """起一次 attempt；失败一律显式（`model_call_failed`），不返回假候选。"""
        if cwd is None or home is None:
            raise BackendConfigurationError(
                "DshBackend.execute 需要显式 cwd 与 home（每 attempt 独立；不得落到宿主目录）")
        layout = self._layout_for(Path(cwd), Path(home))
        try:
            spec = self._spec(request, attempt_key=attempt_key,
                              cwd=Path(cwd), home=Path(home))
        except A.AssetError as exc:
            return self._failure("dsh attempt 资产物化失败：%s" % exc)
        rejected = await self._preflight(spec, layout)
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
                    "dsh attempt 缺自检身份（nonce/attemptKey）：不得以'进程起来了'当准入")

            async def on_start() -> None:                    # noqa: D401 - 准入钩子
                nonlocal selfcheck
                result = await SC.averify_session(
                    layout, timeout_s=SELFCHECK_TIMEOUT_S,
                    expected_nonce=expected_nonce,
                    expected_attempt_key=expected_attempt)
                result.require_ok()
                facts = result.facts
                # 只保留有消费者的投影：attempt 记录/证据可复核"当时看到什么"
                selfcheck = {"phase": facts.get("phase"),
                             "toolCount": len(facts.get("toolNames") or []),
                             "sandboxDefaultMode": facts.get("sandboxDefaultMode"),
                             "presetEcho": facts.get("presetEcho")}

        try:
            outcome = await DP.run_attempt(spec, on_start=on_start)
        except (DPR.ProtocolError, DP.AttemptError, SC.SelfCheckFailed) as exc:
            return self._failure(str(exc))
        if outcome.status != "completed":
            code = "，code=%s" % outcome.code if outcome.code else ""
            return self._failure("dsh 未完成（reason=%s%s）：%s"
                                 % (outcome.reason, code,
                                    outcome.message or "无诊断"))
        # 完成判据（B5/DS-02）：终态 completed **且** 恰一条被接受的提交；
        # 提交门是唯一实现（dsh_protocol），这里不复制判据。
        try:
            submission = DPR.require_submission(outcome, expect_task_id=attempt_key)
        except DPR.ProtocolError as exc:
            return self._failure(str(exc))
        payload = {"standin": False, "provider": "dsh/%s" % self._config.version,
                   "plugin": "dsh", "data": submission.payload,
                   "task_id": submission.task_id, "summary": submission.summary,
                   "session_id": outcome.session_id, "usage": outcome.usage,
                   "isolation": ("unwrapped-diagnostic" if self._diagnostic_unwrapped
                                 else "bwrap")}
        if selfcheck is not None:
            payload["selfcheck"] = selfcheck
        return payload
