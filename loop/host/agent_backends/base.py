"""单次候选生成契约；无业务写权，不代表原生 DSH 协议。

**A2 请求字段**（REV-13 §5.2 / REV-14 A2）：`contract_version`、`identity`、
`context_manifest_ref`、`execution_grant_ref`、`runtime_fingerprint` 由 **Host 填写**、后端只读。
旧调用方不填 ⇒ 全部缺省，`contract_record()` 投影为 `legacy`/`unknown`（**只读兼容，不回填**），
不得据缺省值推定"已具备新能力"。

本模块只放**形状与投影**：不解析凭据、不读配置、不启进程；判据（准入/校验/闸门）不在 base.py。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

#: 请求契约版本（A2）。不认识的版本由后端显式拒绝，不做兼容猜测。
CONTRACT_VERSION = 1

#: 缺省投影里代替"缺失"的稳定标记（证据/界面可直接判）
LEGACY = "legacy"
UNKNOWN = "unknown"


class ExecutionUnknown(RuntimeError):
    """在途执行**无法确认已停止**（DS-05 / REV-13 §7.3）。

    为什么单独一个类型：控制层必须能把它与"已确认停止"区分开 —— 前者要落
    `execution_unknown`、禁自动重发；用 `CancelledError` 冒充"已停"就是骗自己。
    定义在 base.py 是因为两个写者都要用它（进程层 `dsh_process` 抛出，
    控制层 `agent_control` 判定），且不得因此形成第二套停止判据。
    """


@dataclass(frozen=True)
class RequestIdentity:
    """一次请求的 Host 侧身份（A2）。缺省字段投影成 `unknown`，不猜。"""

    run_id: str | None = None
    node: str | None = None
    attempt_key: str | None = None
    generation: int | None = None
    control_session_id: str | None = None

    def record(self) -> dict[str, Any]:
        """封存/展示投影：缺失 ⇒ `unknown`（不显示空串，避免与"空值合法"混淆）。"""
        out: dict[str, Any] = {}
        for name in ("run_id", "node", "attempt_key", "generation", "control_session_id"):
            value = getattr(self, name)
            out[name] = UNKNOWN if value is None or value == "" else value
        return out


def contract_record(*, contract_version: int | None = None,
                    identity: RequestIdentity | None = None,
                    context_manifest_ref: str | None = None,
                    execution_grant_ref: str | None = None,
                    runtime_fingerprint: str | None = None) -> dict[str, Any]:
    """A2 的唯一投影实现（请求封存与候选回显共用；旧记录缺省 ⇒ legacy/unknown）。"""
    return {
        "contract_version": LEGACY if contract_version is None else contract_version,
        "identity": identity.record() if identity is not None else UNKNOWN,
        "context_manifest_ref": context_manifest_ref or UNKNOWN,
        "execution_grant_ref": execution_grant_ref or UNKNOWN,
        "runtime_fingerprint": runtime_fingerprint or UNKNOWN,
    }


def read_contract(request: dict[str, Any] | None) -> dict[str, Any]:
    """**读出侧**的 A2 投影：负责"旧记录只读兼容"。

    历史记录没有 `backend_contract`（或字段不全）⇒ 显示 `legacy`/`unknown`；
    **不回填、不推断**已具备新能力（REV-13 §11 / REV-14 §8）。
    """
    request = request if isinstance(request, dict) else {}
    raw = request.get("backend_contract")
    if not isinstance(raw, dict):
        return contract_record()
    identity = raw.get("identity")
    if isinstance(identity, dict):
        identity = RequestIdentity(**{name: identity.get(name) for name in
                                      ("run_id", "node", "attempt_key", "generation",
                                       "control_session_id")})
    else:
        identity = None
    try:
        version = int(raw["contract_version"])
    except (KeyError, TypeError, ValueError):
        version = None
    return contract_record(contract_version=version, identity=identity,
                           context_manifest_ref=raw.get("context_manifest_ref"),
                           execution_grant_ref=raw.get("execution_grant_ref"),
                           runtime_fingerprint=raw.get("runtime_fingerprint"))


@dataclass(frozen=True)
class BackendRequest:
    input_data: dict[str, Any]
    info: str
    instruct: str
    schema: Any
    #: A2（REV-13 §5.2）：全部可选 —— 旧调用方不填也合法，只是投影为 legacy/unknown。
    contract_version: int | None = None
    identity: RequestIdentity | None = None
    context_manifest_ref: str | None = None
    execution_grant_ref: str | None = None
    runtime_fingerprint: str | None = None

    def contract(self) -> dict[str, Any]:
        """本请求的 A2 投影（封存/回显用的唯一形状）。"""
        return contract_record(contract_version=self.contract_version,
                               identity=self.identity,
                               context_manifest_ref=self.context_manifest_ref,
                               execution_grant_ref=self.execution_grant_ref,
                               runtime_fingerprint=self.runtime_fingerprint)


@dataclass(frozen=True)
class BackendInfo:
    available: bool
    model: str | None
    plugin: str | None
    reason: str | None


class AgentBackend(Protocol):
    info: BackendInfo

    def metadata(self) -> dict[str, Any]: ...

    def redact(self, message: str) -> str: ...

    async def execute(self, request: BackendRequest) -> dict[str, Any]: ...
