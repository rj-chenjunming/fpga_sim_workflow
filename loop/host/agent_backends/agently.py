"""Agently 传输适配；凭据只保留在内部，Host 决定是否接受候选。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from host import model_provider as MP
from .base import BackendInfo, BackendRequest


class AgentlyBackend:
    def __init__(self):
        self._config = MP.resolve()
        cfg = self._config
        self.info = BackendInfo(cfg.available, cfg.model, cfg.plugin, cfg.reason)

    def metadata(self) -> dict[str, str]:
        return {'name': 'agently',
                'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def redact(self, message: str) -> str:
        secret = self._config._api_key
        return message.replace(secret, '[redacted]') if secret else message

    async def execute(self, request: BackendRequest) -> dict[str, Any]:
        from agently import Agently

        cfg = MP.configure_agently(config=self._config)
        agent = Agently.create_agent()
        try:
            data = await (agent.input(request.input_data).info(request.info)
                          .instruct(request.instruct).output(request.schema, format='json')
                          .async_get_data())
            if hasattr(data, 'model_dump'):
                data = data.model_dump()
            elif isinstance(data, dict) and hasattr(data.get('$result'), 'model_dump'):
                data = data['$result'].model_dump()
        except Exception as exc:
            message = f'{type(exc).__name__}: {exc}'
            if cfg._api_key:
                message = message.replace(cfg._api_key, '[redacted]')
            return {'standin': False, 'provider': cfg.model,
                    'model_call_failed': True, 'error': message}
        return {'standin': False, 'provider': cfg.model, 'plugin': cfg.plugin, 'data': data}
