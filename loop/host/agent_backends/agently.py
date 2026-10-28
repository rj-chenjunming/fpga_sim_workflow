"""Agently 传输适配；凭据只保留在内部，Host 决定是否接受候选。

**provider 是惰性解析的**（S5）：`select()` 只做"配置 + 模式"决策，构造本后端**不探测**
provider/凭据 —— 否则 `LOOP_LLM_MODE=standin` 下"按模式用替身"这条规则会顺手解析
Agently 凭据（DS-01 明确禁止"显式 dsh 借道解析 Agently 凭据"）。真正需要 provider 时
（`info`/`execute`/`redact`）解析一次并在同一实例内复用（配置快照在审计与 SDK 之间同源，
既有行为不变）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from host import model_provider as MP
from .base import BackendInfo, BackendRequest


class AgentlyBackend:
    """Agently 传输适配（也是 standin/drill 模式下**显式**的替身后端）。

    `selection` 只在"配置显式选了 dsh、但按 mode 规则用 agently 替身"时给出
    （见 `agent_backends.select` 的 `standin_mode`/`mode_drill` 规则）：它随 `metadata()`
    进请求封存记录，使"按模式替身"与"准入失败"可区分。普通 agently 选择不传，
    元数据形状保持原样（REG-01）。
    """

    def __init__(self, selection: dict[str, Any] | None = None):
        self._selection = selection
        self._config: Any | None = None

    @property
    def config(self):
        """provider 快照（惰性；同一实例只解析一次）。"""
        if self._config is None:
            self._config = MP.resolve()
        return self._config

    @property
    def info(self) -> BackendInfo:
        cfg = self.config
        return BackendInfo(cfg.available, cfg.model, cfg.plugin, cfg.reason)

    def metadata(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            'name': 'agently',
            'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        if self._selection is not None:
            meta['admission'] = self._selection
        return meta

    def redact(self, message: str) -> str:
        secret = self.config._api_key
        return message.replace(secret, '[redacted]') if secret else message

    async def execute(self, request: BackendRequest) -> dict[str, Any]:
        from agently import Agently

        cfg = MP.configure_agently(config=self.config)
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
