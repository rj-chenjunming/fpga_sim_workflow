"""DSH 后端骨架（S1）：配置锁定 + 进程/协议编排。

边界（REV-13 §2 / REV-14 §2）：
- 只做"起 attempt → 收帧 → 按终态出候选"，**不**持有业务写权、不签闸门、不改节点判据；
- 不进入 `agent_backends.select()` 的可用路径：未显式启用/指纹不匹配 ⇒ `BackendUnavailable`；
- 结构化候选走 `submit_result`（S2），本片先返回**文本 + usage**，并明确标注不是业务结论。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from host import paths as P
from . import BackendConfigurationError, BackendUnavailable
from . import dsh_process as DP
from . import dsh_protocol as DPR
from .base import BackendInfo, BackendRequest

#: 配置允许字段（多一个就拒绝：避免"悄悄接受未实现开关"）
CONFIG_KEYS = frozenset({"enabled", "version", "node", "bin", "bin_sha256", "profile",
                         "timeout_s", "stop_grace_s", "wrap", "patches", "api_key_env"})
SETTINGS_FILE = P.LOOP_DIR / "SETTINGS.yaml"


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

    def verify(self) -> None:
        """准入：文件在 + 指纹匹配 + 版本声明；任何一项不满足都显式拒绝。"""
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


def _compose_task(request: BackendRequest) -> str:
    """S1 占位：把 info/instruct/input 合成一个任务文本（S2 换成上下文包 + 提交工具）。"""
    return ("%s\n\n[info]\n%s\n\n[input]\n%s"
            % (request.instruct, request.info,
               json.dumps(request.input_data, ensure_ascii=False, indent=1)))


class DshBackend:
    """`AgentBackend` 协议实现（骨架）。默认不可用，需显式配置且指纹匹配。"""

    def __init__(self, config: DshConfig | None = None) -> None:
        self._config = config or config_from_settings()
        self._config.verify()
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

    def _spec(self, request: BackendRequest, *, attempt_key: str,
              cwd: Path, home: Path) -> DP.AttemptSpec:
        return DP.AttemptSpec(
            attempt_key=attempt_key, cwd=Path(cwd), home=Path(home),
            task=_compose_task(request), dsh_bin=self._config.bin, node=self._config.node,
            patches=self._config.patches, profile=self._config.profile,
            timeout_s=self._config.timeout_s, stop_grace_s=self._config.stop_grace_s,
            wrap=self._config.wrap,
            api_key=os.environ.get(self._config.api_key_env),
            api_key_env=self._config.api_key_env)

    async def execute(self, request: BackendRequest, *, attempt_key: str = "adhoc/1",
                      cwd: Path | None = None, home: Path | None = None) -> dict[str, Any]:
        """起一次 attempt；失败一律显式（`model_call_failed`），不返回假候选。"""
        if cwd is None or home is None:
            raise BackendConfigurationError(
                "DshBackend.execute 需要显式 cwd 与 home（每 attempt 独立；不得落到宿主目录）")
        spec = self._spec(request, attempt_key=attempt_key, cwd=Path(cwd), home=Path(home))
        try:
            outcome = await DP.run_attempt(spec)
        except (DPR.ProtocolError, DP.AttemptError) as exc:
            return {"standin": False, "provider": "dsh/%s" % self._config.version,
                    "model_call_failed": True, "error": self.redact(str(exc))}
        if outcome.status != "completed":
            return {"standin": False, "provider": "dsh/%s" % self._config.version,
                    "model_call_failed": True,
                    "error": self.redact(outcome.message or "dsh 未完成（%s）" % outcome.reason)}
        return {"standin": False, "provider": "dsh/%s" % self._config.version,
                "plugin": "dsh", "text": outcome.text, "usage": outcome.usage,
                "session_id": outcome.session_id,
                "note": "S1 骨架：结构化候选由 submit_result 提供（S2），此处 text 不是业务结论"}
