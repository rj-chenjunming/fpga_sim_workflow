"""单次候选生成契约；无业务写权，不代表原生 DSH 协议。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendRequest:
    input_data: dict[str, Any]
    info: str
    instruct: str
    schema: Any


@dataclass(frozen=True)
class BackendInfo:
    available: bool
    model: str | None
    plugin: str | None
    reason: str | None


class AgentBackend(Protocol):
    info: BackendInfo

    def metadata(self) -> dict[str, str]: ...

    def redact(self, message: str) -> str: ...

    async def execute(self, request: BackendRequest) -> dict[str, Any]: ...
