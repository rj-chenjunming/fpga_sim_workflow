"""SPEC-08 D1：Host 边界、选择准入与受控 SDK 的行为测试。"""
import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from test_agent_context_memory import ctx, provider, call  # noqa: F401
from host import agent_memory as AM, model_provider as MP


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from host import agent_backends as B
    path = tmp_path / 'SETTINGS.yaml'
    monkeypatch.setattr(B, 'SETTINGS_FILE', path)

    def write(runtime):
        path.write_text(yaml.safe_dump({'loop': {'agent_runtime': runtime}}))
        return B

    write({})
    return write


async def test_default_backend_identity_is_sealed_and_not_taken_from_input(ctx, provider, settings):
    settings({})
    out = await call(ctx, input_data={'backend': 'dsh', 'run_id': ctx.run_id})
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    backend = record['request']['backend']
    assert backend == record['result']['backend'] == out['backend']
    assert backend['name'] == 'agently'
    from host.agent_backends import agently
    assert backend['implementation_sha256'] == hashlib.sha256(Path(agently.__file__).read_bytes()).hexdigest()
    assert 'never-record-this-secret' not in json.dumps(record)
    assert record['result']['status'] == 'validated'


@pytest.mark.parametrize('runtime', [
    {'default_backend': 'dsh'},
    {'node_backends': {'N3': 'dsh'}},
])
async def test_explicit_dsh_under_standin_mode_is_a_scoped_substitution(ctx, monkeypatch, settings, runtime):
    """S5 契约变更（人工裁决 2026-10-28 规则②）：`LOOP_LLM_MODE=standin` ⇒ 按**模式**用替身。

    旧断言「standin + 显式 dsh ⇒ `BackendUnavailable`」只对 `run_mode` **未知**的直调成立
    （严格语义，判据唯一实现在 `agent_backends.select`，用例见
    `tests/test_dsh_admission.py::test_unspecified_run_mode_keeps_strict_semantics`）。
    经 `model_request` 的请求已声明 run 模式，standin 的定义是"模型用确定性替身"，
    契约上**不选任何原生后端**；这是模式规则，不是 dsh 准入失败后的回落。

    替身决策必须是**纯的**：不探测 Agently provider/凭据（`select` 阶段不解析），
    也不写请求记录（拒绝/替身都发生在提交前）。
    """
    B = settings(runtime)
    monkeypatch.setenv('LOOP_LLM_MODE', 'standin')
    def forbidden():
        pytest.fail('standin/drill 的模式决策不得解析 Agently provider/凭据')
    monkeypatch.setattr(MP, 'resolve', forbidden)
    with B.run_mode('real'):
        backend = B.select('N3')
    assert backend.metadata()['name'] == 'agently'
    record = backend.metadata()['admission']
    assert record['rule'] == 'standin_mode' and record['code'] == 'substituted'
    assert record['requested'] == 'dsh' and record['effective'] == 'agently'
    assert record['reason']
    assert not (ctx.run_dir / 'agent_calls').exists()
    # 严格语义不许被放宽：`run_mode` 未声明的直调仍显式失败（同一判据，不另写一套）
    with pytest.raises(B.BackendUnavailable):
        B.select('N3')


async def test_node_override_precedes_default_and_does_not_select_other_node(ctx, provider, settings):
    B = settings({'default_backend': 'dsh', 'node_backends': {'N3': 'agently'}})
    assert (await call(ctx))['validation']['ok']
    with pytest.raises(B.BackendUnavailable):
        B.select('N6')


@pytest.mark.parametrize('runtime', [None, [], 'secret-marker',
    {'default_backend': 'secret-marker'}, {'node_backends': []},
    {'node_backends': {'N4': 'agently'}}, {'node_backends': {'N6': 'secret-marker'}},
    {'unknown-secret-marker': True}, {'dsh': []},
])
def test_bad_config_fails_without_echo_or_provider(settings, monkeypatch, runtime):
    B = settings(runtime)
    monkeypatch.setattr(MP, 'resolve', lambda: pytest.fail('must reject before provider'))
    with pytest.raises(B.BackendConfigurationError) as error:
        B.select('N3')
    assert 'secret-marker' not in str(error.value)


@pytest.mark.parametrize('text', ['loop: [', '[]', 'loop: []', 'loop: null'])
def test_bad_settings_document_is_not_silently_ignored(settings, monkeypatch, text):
    B = settings({})
    B.SETTINGS_FILE.write_text(text)
    monkeypatch.setattr(MP, 'resolve', lambda: pytest.fail('must reject before provider'))
    with pytest.raises(B.BackendConfigurationError):
        B.select('N3')


async def test_missing_runtime_section_keeps_existing_standin(ctx, provider, settings):
    B = settings({})
    B.SETTINGS_FILE.write_text('loop:\n  llm: {}\n')
    provider['cfg'].available = False
    provider['cfg'].reason = 'offline-test'
    out = await call(ctx)
    assert out['standin'] is True and out['reason'] == 'offline-test'
    assert not provider['agents']
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    assert record['result']['status'] == 'standin'
    assert record['request']['model'] is None
    assert record['result']['backend']['name'] == 'agently'


async def test_config_snapshot_is_used_once_for_audit_and_sdk(ctx, provider, settings, monkeypatch):
    settings({})
    resolutions, configured = [], []
    def resolve():
        resolutions.append(True)
        assert len(resolutions) == 1
        return provider['cfg']
    def configure(*, config):
        configured.append(config)
        return config
    monkeypatch.setattr(MP, 'resolve', resolve)
    monkeypatch.setattr(MP, 'configure_agently', configure)
    out = await call(ctx)
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    assert len(resolutions) == 1 and configured == [provider['cfg']]
    assert record['request']['model'] == out['provider'] == provider['cfg'].model


def test_configure_agently_accepts_prepared_snapshot_without_resolving(monkeypatch):
    from agently import Agently
    cfg = MP.ProviderConfig(available=True, plugin='OpenAICompatible', family='chat',
        base_url='https://model.invalid', model='test', api_key_env='TEST_KEY',
        max_tokens=100, timeout_s=1, _api_key='synthetic-test-key')
    applied = {}
    monkeypatch.setattr(MP, 'resolve', lambda **_: pytest.fail('must use prepared snapshot'))
    monkeypatch.setattr(Agently, 'set_settings', lambda key, value: applied.update({key: value}))
    assert MP.configure_agently(config=cfg) is cfg
    assert applied['plugins.ModelRequester.OpenAICompatible.model'] == 'test'
    assert applied['plugins.ModelRequester.OpenAICompatible.api_key'] == 'synthetic-test-key'
    with pytest.raises(ValueError):
        MP.configure_agently(config=cfg, model='different')


async def test_backend_candidate_still_passes_the_only_host_validator(ctx, provider, settings, monkeypatch):
    B = settings({})
    backend = B.select('N3')
    requests = []
    async def execute(request):
        requests.append(request)
        return {'standin': False, 'provider': 'test-model', 'backend': 'dsh',
                'data': {'summary': '', 'groups': [], 'risky_points': []}}
    monkeypatch.setattr(backend, 'execute', execute)
    monkeypatch.setattr(B, 'select', lambda node: backend)
    out = await call(ctx)
    assert out['validation']['ok'] is False
    assert out['backend']['name'] == 'agently'
    assert len(requests) == 1
    assert not hasattr(requests[0], 'ctx') and not hasattr(requests[0], 'validate')
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    assert requests[0].input_data == record['request']['input']
    assert record['result']['status'] == 'validation_failed'


async def test_adapter_cancellation_propagates_and_is_sealed(ctx, provider, settings):
    settings({})
    provider['wait'], provider['entered'] = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(call(ctx))
    await asyncio.wait_for(provider['entered'].wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    record = AM.verify_attempt(next((ctx.run_dir / 'agent_calls/N3').iterdir()))
    assert record['result']['status'] == 'interrupted'
    assert record['result']['backend']['name'] == 'agently'


async def test_agent_view_exposes_backend_for_new_records_without_backfilling_history(ctx, provider, settings):
    from host import agent_control as C
    settings({})
    old = AM.Attempt(ctx, 'N3', {'input': {}, 'model': 'historical-model'})
    old.finish('standin', payload={'standin': True})
    before = {p.name: p.read_bytes() for p in old.path.iterdir()}
    out = await call(ctx)
    view = C.read_view(ctx.run_dir, 'N3')
    assert view['request']['backend'] == view['result']['backend'] == out['backend']
    historical = C.read_view(ctx.run_dir, 'N3', attempt=1)
    assert 'backend' not in historical['request']
    assert 'backend' not in historical['result']
    assert {p.name: p.read_bytes() for p in old.path.iterdir()} == before


def test_missing_settings_and_host_node_fail_closed(settings, monkeypatch):
    B = settings({})
    monkeypatch.setattr(MP, 'resolve', lambda: pytest.fail('must reject before provider'))
    B.SETTINGS_FILE.unlink()
    with pytest.raises(B.BackendConfigurationError):
        B.select('N3')
    with pytest.raises(B.BackendConfigurationError):
        B.select('N4')
