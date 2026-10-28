"""Agent 执行后端；Host 保留校验、封存与控制的唯一写权。

**选择的三层**（SPEC-08 §3 / REV-13 §5.1 / 人工裁决 2026-10-28），每层都是显式规则：

1. **配置**：`loop.agent_runtime.default_backend`（缺省 agently）+ `node_backends`
   （六个模型节点 N3/N6/N8/N10/N11/N12 任一可显式选 `dsh`；未列入的节点按 default）；
2. **模式**（按①→④顺序判定，顺序本身是契约，人工裁决 2026-10-28 定稿）：
   - ① `run_mode` 未声明（旧/未知调用）⇒ **严格失败**（保持现行语义，不默认当 `real`）；
   - ② `LOOP_LLM_MODE=standin`（任何 `run_mode`）⇒ **Agently 替身** + `admission.rule='standin_mode'`
     （standin 的模式定义就是"模型用确定性替身"，契约上不用原生后端；不是准入失败后的回落）；
   - ③ `run_mode='drill'` ⇒ **Agently 替身** + `admission.rule='mode_drill'`；
   - ④ 其余（`real` + `live`/未设）⇒ 完整受控准入链。
3. **准入**：第④类走 `dsh.admit()` 的**唯一**判据（enabled + bin 指纹 + 版本匹配
   + DS-08/09 静态自检）；任一不满足 ⇒ `BackendUnavailable` + 可判 `err.admission['code']`，
   **绝不**返回 `AgentlyBackend`。

`run_mode` 由请求作用域声明（`workflows/chunks/model_request.run_attempt` 用 `run_mode()` 进入），
因此 `select(node)` 的调用形状不变（既有调用点/测试替身不必改写）；也可显式传参覆盖。
"""
from __future__ import annotations

import contextlib
import os
from contextvars import ContextVar
from typing import Any, Iterator

import yaml

from host import paths as P
from .agently import AgentlyBackend
from .base import (CONTRACT_VERSION, AgentBackend, BackendRequest,
                   ExecutionUnknown, RequestIdentity, contract_record, read_contract)

SETTINGS_FILE = P.LOOP_DIR / 'SETTINGS.yaml'

#: 允许的 run 模式（与 `RunCtx.mode` 同一枚举；不认识的模式显式拒绝）
RUN_MODES = frozenset({'drill', 'real'})
#: `LOOP_LLM_MODE` 的离线值（与 `model_provider` 同一来源判断）
STANDIN = 'standin'

#: 请求作用域内的 run 模式声明（`select` 的唯一读取点；默认 None = 未声明）
_RUN_MODE: ContextVar[str | None] = ContextVar('loop_agent_run_mode', default=None)


class BackendConfigurationError(ValueError):
    """服务端配置不合法；诊断不回显配置原文。"""


class BackendUnavailable(RuntimeError):
    """显式选择的后端未通过准入，不允许静默切换。

    `admission` 是可判的准入记录（`rule`/`code`/`requested`/`effective`/`checks`/`detail`）：
    界面与证据据此区分"按 mode 用替身"与"准入失败"，不必解析错误文本。
    """

    def __init__(self, message: str, *, admission: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.admission = admission or {}


@contextlib.contextmanager
def run_mode(mode: str) -> Iterator[None]:
    """在一次请求范围内声明 run 模式（`drill`/`real`）。

    为什么用请求作用域而不是多加一个必须传的参数：`select(node)` 的调用形状是既有契约
    （测试用单参替身替换它），加参数会让"没改到调用点"静默退回旧语义。作用域声明让
    "谁在什么模式下调用"成为显式上下文，并在退出时还原（不泄漏到别的请求）。
    """
    if mode not in RUN_MODES:
        raise BackendConfigurationError('agent runtime: invalid run_mode')
    token = _RUN_MODE.set(mode)
    try:
        yield
    finally:
        _RUN_MODE.reset(token)


def current_run_mode() -> str | None:
    """当前请求作用域声明的 run 模式（未声明 ⇒ None；不得当成 real）。"""
    return _RUN_MODE.get()


def _mode_admission(node: str, *, rule: str, code: str, effective: str,
                    reason: str) -> dict[str, Any]:
    """按 mode 的显式决策记录（与准入失败同形状，便于界面/证据统一消费）。"""
    return {'rule': rule, 'code': code, 'requested': 'dsh', 'effective': effective,
            'node': node, 'checks': {}, 'reason': reason, 'detail': [reason],
            'version': None, 'runtime_fingerprint': None}


def select(node: str, *, run_mode: str | None = None,
           llm_mode: str | None = None) -> AgentBackend:
    """先检查后端选择与模式，再解析后端自己的 provider（判据不在这里复制）。"""
    from host.agent_control import NODES

    if node not in NODES:
        raise BackendConfigurationError('agent runtime: unsupported model node')
    try:
        document = yaml.safe_load(SETTINGS_FILE.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, yaml.YAMLError):
        raise BackendConfigurationError('agent runtime: cannot read valid SETTINGS YAML') from None
    if not isinstance(document, dict) or not isinstance(document.get('loop', {}), dict):
        raise BackendConfigurationError('agent runtime: SETTINGS and loop must be mappings')
    runtime = document.get('loop', {}).get('agent_runtime', {})
    if not isinstance(runtime, dict) or set(runtime) - {'default_backend', 'node_backends', 'dsh'}:
        raise BackendConfigurationError('agent runtime: invalid configuration fields')
    default = runtime.get('default_backend', 'agently')
    nodes = runtime.get('node_backends', {})
    if not isinstance(nodes, dict) or set(nodes) - NODES:
        raise BackendConfigurationError('agent runtime: invalid node_backends mapping')
    if any(value not in ('agently', 'dsh') for value in (default, *nodes.values())):
        raise BackendConfigurationError('agent runtime: unsupported backend selection')
    if not isinstance(runtime.get('dsh', {}), dict):
        raise BackendConfigurationError('agent runtime: dsh configuration must be a mapping')
    requested = nodes.get(node, default)
    if requested != 'dsh':
        return AgentlyBackend()

    # ---- 顺序判定（人工裁决 2026-10-28 定稿；顺序本身是契约，别重排）----
    mode = run_mode if run_mode is not None else current_run_mode()
    if mode is not None and mode not in RUN_MODES:
        raise BackendConfigurationError('agent runtime: invalid run_mode')
    if mode is None:
        # ① 旧/未知调用：不默认当 real（保住 DS-01 的严格语义）。
        raise BackendUnavailable(
            'DSH backend unavailable: run_mode 未声明（旧/未知调用不得默认当 real；'
            '请在请求作用域用 run_mode(...) 声明 drill/real）',
            admission=_mode_admission(
                node, rule='mode_rules', code='mode_unspecified', effective='dsh',
                reason='run_mode 未声明 ⇒ 保持现行严格语义（不默认 real）'))
    if (llm_mode or os.environ.get('LOOP_LLM_MODE') or 'live').strip().lower() == STANDIN:
        # ② `standin` 的模式定义就是"模型用确定性替身"：契约上**不使用任何原生后端**。
        #    这是模式规则（不是 dsh 准入失败后的回落），所以要显式记 rule='standin_mode'；
        #    否则一堆 mode=real 的特征用例会因为"配置里列了 dsh"而成批变红 —— 那是判错了模式语义。
        return AgentlyBackend(selection=_mode_admission(
            node, rule='standin_mode', code='substituted', effective='agently',
            reason='LOOP_LLM_MODE=standin：模型用确定性替身，按模式规则不选原生后端'
                   '（不是"dsh 不可用后回落"；run_mode 仍如实记录，不冒充 real）'))
    if mode == 'drill':
        # ③ drill 是确定性替身模式：同样**契约上不选原生后端**。显式记录"是谁做的决定"，
        #    不得把替身记成 effective='dsh'（否则界面/证据会把演练当真实接入）。
        return AgentlyBackend(selection=_mode_admission(
            node, rule='mode_drill', code='substituted', effective='agently',
            reason='run_mode=drill：按 mode 的显式规则用 Agently 确定性替身，'
                   '不尝试 dsh（不是"dsh 不可用后回落"）'))
    # ④ 其余（real + live/未设）⇒ 完整受控准入链；任一不满足即 BackendUnavailable。

    from . import dsh as D

    try:
        config = D.config_from_settings(document)
    except BackendConfigurationError as exc:
        raise BackendUnavailable(
            'DSH backend unavailable: admission=config_invalid node=%s：%s' % (node, exc),
            admission=_mode_admission(
                node, rule='admission', code='config_invalid', effective='dsh',
                reason=str(exc))) from None
    admission = D.admit(config, node=node)
    if not admission.ok:
        raise BackendUnavailable(admission.message(), admission=admission.record())
    try:
        return D.DshBackend(config, admission=admission)
    except BackendUnavailable as exc:
        # 准入与构造之间状态变了（bin 被替换等）：同样是准入失败，不静默重试/不换后端。
        record = _mode_admission(node, rule='admission', code='not_verified',
                                 effective='dsh', reason=str(exc))
        raise BackendUnavailable('DSH backend unavailable: %s' % exc,
                                 admission=record) from None


__all__ = [
    'BackendConfigurationError', 'BackendUnavailable', 'BackendRequest',
    'CONTRACT_VERSION', 'ExecutionUnknown', 'RequestIdentity', 'RUN_MODES',
    'contract_record', 'current_run_mode', 'read_contract', 'run_mode', 'select',
]
