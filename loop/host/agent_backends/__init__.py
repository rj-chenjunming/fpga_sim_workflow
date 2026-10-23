"""Agent 执行后端；Host 保留校验、封存与控制的唯一写权。"""
import yaml

from host import paths as P
from .agently import AgentlyBackend
from .base import AgentBackend, BackendRequest

SETTINGS_FILE = P.LOOP_DIR / 'SETTINGS.yaml'


class BackendConfigurationError(ValueError):
    """服务端配置不合法；诊断不回显配置原文。"""


class BackendUnavailable(RuntimeError):
    """显式选择的后端未通过准入，不允许静默切换。"""


def select(node: str) -> AgentBackend:
    """先检查后端选择，再解析后端自己的 provider。"""
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
    if nodes.get(node, default) == 'dsh':
        raise BackendUnavailable('DSH backend unavailable: verified runtime interface and D0 admission evidence required')
    return AgentlyBackend()
