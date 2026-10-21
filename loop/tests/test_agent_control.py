"""真实异步请求边界的控制；模型为可阻塞的受控 provider。"""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from test_agent_context_memory import ctx, provider, call  # noqa: F401
from host import agent_control as C
from workflows.chunks import model_request as MR
from workflows.chunks import model_steps as M


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(wait(), 2)


async def started(ctx, provider):
    provider['wait'], provider['entered'] = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(call(ctx))
    await asyncio.wait_for(provider['entered'].wait(), 2)
    return task


def payload(ctx, action, request_id='request-1', **more):
    live = C.read_view(ctx.run_dir, 'N3')['live']
    return dict(action=action, actor='human:reviewer', request_id=request_id,
                session_id=live['session_id'], expected_revision=live['revision'], **more)


async def test_steer_reissues_with_instruction_and_disposes_old_attempt(ctx, provider):
    task = await started(ctx, provider)
    original = copy.deepcopy(provider['inputs'][0])
    receipt = C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='重点核对新增端口'))
    assert receipt['status'] == 'accepted'
    await until(lambda: len(provider['inputs']) == 2)
    new = provider['inputs'][1]
    assert new['human_interventions'][0]['message'] == '重点核对新增端口'
    assert {k: v for k, v in new.items() if k != 'human_interventions'} == original
    assert not task.done()
    provider['wait'].set()
    result = await task
    assert result['validation']['ok']
    view = C.read_view(ctx.run_dir, 'N3')
    assert view['live'] is None and len(view['attempts']) == 2
    assert view['attempts'][0]['status'] == 'interrupted'
    assert any(e['type'] == 'applied' for e in view['controls'])


async def test_pause_holds_boundary_resume_reissues_and_terminate_fails(ctx, provider):
    task = await started(ctx, provider)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'pause'))
    await until(lambda: C.read_view(ctx.run_dir, 'N3')['live']['state'] == 'paused')
    assert len(provider['inputs']) == 1 and not task.done()
    C.command(ctx.run_dir, 'N3', payload(ctx, 'resume', 'request-2'))
    await until(lambda: len(provider['inputs']) == 2)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'terminate', 'request-3'))
    with pytest.raises(C.AgentTerminated):
        await task
    assert C.read_view(ctx.run_dir, 'N3')['live'] is None
    assert C.read_view(ctx.run_dir, 'N3')['controls'][-1]['state'] == 'stopped'


async def test_steer_from_paused_resumes_with_new_request(ctx, provider):
    task = await started(ctx, provider)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'pause'))
    await until(lambda: C.read_view(ctx.run_dir, 'N3')['live']['state'] == 'paused')
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', 'request-2', message='补充检查说明'))
    await until(lambda: len(provider['inputs']) == 2)
    provider['wait'].set()
    assert (await task)['validation']['ok']


@pytest.mark.parametrize('mutation,error', [
    ({'actor': 'agent:auto'}, PermissionError), ({'actor': 'human:'}, PermissionError),
    ({'session_id': 'old-session'}, C.ControlConflict), ({'expected_revision': -1}, C.ControlConflict),
    ({'action': 'resume'}, C.ControlConflict), ({'action': 'shell'}, ValueError),
    ({'message': ''}, ValueError), ({'message': 'x' * 4001}, ValueError),
])
async def test_rejection_happens_before_audit_and_no_request_change(ctx, provider, mutation, error):
    task = await started(ctx, provider)
    data = payload(ctx, 'steer', message='instruction')
    data.update(mutation)
    before = C.read_view(ctx.run_dir, 'N3')['controls']
    with pytest.raises(error):
        C.command(ctx.run_dir, 'N3', data)
    assert C.read_view(ctx.run_dir, 'N3')['controls'] == before
    provider['wait'].set()
    await task


async def test_idempotency_and_pending_command_rejection(ctx, provider):
    task = await started(ctx, provider)
    data = payload(ctx, 'steer', message='instruction')
    first = C.command(ctx.run_dir, 'N3', data)
    assert C.command(ctx.run_dir, 'N3', data) == first
    with pytest.raises(C.ControlConflict):
        C.command(ctx.run_dir, 'N3', {**data, 'message': 'different'})
    with pytest.raises(C.ControlConflict):
        C.command(ctx.run_dir, 'N3', payload(ctx, 'pause', 'request-2'))
    await until(lambda: len(provider['inputs']) == 2)
    provider['wait'].set()
    await task
    assert C.command(ctx.run_dir, 'N3', data) == first  # 回执可在完成后幂等查询


async def test_cancel_outer_task_cleans_child_and_registry(ctx, provider):
    task = await started(ctx, provider)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert C.read_view(ctx.run_dir, 'N3')['live'] is None
    assert C.read_view(ctx.run_dir, 'N3')['attempts'][0]['status'] == 'interrupted'


async def test_stale_control_cannot_restart_completed_or_other_node(ctx, provider):
    task = await started(ctx, provider)
    data = payload(ctx, 'pause')
    with pytest.raises(C.ControlConflict):
        C.command(ctx.run_dir, 'N6', data)
    provider['wait'].set()
    await task
    with pytest.raises(C.ControlConflict):
        C.command(ctx.run_dir, 'N3', data)


async def test_budget_and_validation_remain_authoritative_after_steer(ctx, provider, monkeypatch):
    task = await started(ctx, provider)
    monkeypatch.setattr(M.AM, 'MAX_CONTEXT_BYTES', 1)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='new instruction'))
    with pytest.raises(RuntimeError, match='budget'):
        await task
    assert len(provider['inputs']) == 1
    assert C.read_view(ctx.run_dir, 'N3')['live'] is None


async def test_audit_failure_does_not_acknowledge_or_cancel(ctx, provider, monkeypatch):
    task = await started(ctx, provider)
    real = C._seal
    def fail(path, data):
        if data.get('type') == 'accepted':
            raise OSError('audit unavailable')
        return real(path, data)
    monkeypatch.setattr(C, '_seal', fail)
    with pytest.raises(OSError):
        C.command(ctx.run_dir, 'N3', payload(ctx, 'pause'))
    assert C.read_view(ctx.run_dir, 'N3')['live']['state'] == 'working'
    provider['wait'].set()
    await task


async def test_history_integrity_and_missing_result_are_explicit(ctx, provider):
    await call(ctx)
    view = C.read_view(ctx.run_dir, 'N3', attempt=1)
    assert view['request']['input']['run_id'] == ctx.run_id
    assert view['result']['status'] == 'validated'
    p = ctx.run_dir / 'agent_calls/N3/attempt-000001/result.json'
    p.chmod(0o600)
    p.write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        C.read_view(ctx.run_dir, 'N3')


async def test_controls_reject_foreign_identity_even_with_valid_checksum(ctx, provider):
    await call(ctx)
    folder = next((ctx.run_dir / 'agent_controls/N3').iterdir())
    C._seal(folder / 'event-999999.json', {'type': 'state', 'run_id': 'other-run',
        'node': 'N3', 'session_id': 'N3:' + folder.name, 'revision': 999999, 'state': 'working'})
    with pytest.raises(ValueError, match='identity'):
        C.read_view(ctx.run_dir, 'N3')


async def test_accepted_steer_wins_over_simultaneously_completed_response(ctx, provider):
    task = await started(ctx, provider)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='new instruction'))
    provider['wait'].set()
    result = await task
    assert result['validation']['ok']
    assert len(provider['inputs']) == 2
    assert 'human_interventions' in provider['inputs'][-1]
    assert any(e['type'] == 'discarded' for e in C.read_view(ctx.run_dir, 'N3')['controls'])


async def test_cancellation_timeout_never_starts_overlapping_request(ctx, provider, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def resistant(*args, **kwargs):
        calls.append(kwargs['input_data'])
        entered.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                pass
        return {'standin':False,'provider':'test-model','data':provider['response']}
    # F06：请求机制已提取到 model_request；这里固定的是机制层入口，不是测试期望。
    monkeypatch.setattr(MR, 'ask', resistant)
    monkeypatch.setattr(C, 'CANCEL_TIMEOUT', .01)
    task = asyncio.create_task(call(ctx))
    await entered.wait()
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='instruction'))
    try:
        with pytest.raises(RuntimeError, match='取消超时'):
            await task
        assert len(calls) == 1
        assert C.read_view(ctx.run_dir, 'N3')['live'] is None
        assert any(event['type'] == 'discarded' for event in C.read_view(ctx.run_dir, 'N3')['controls'])
    finally:
        release.set()
        await until(lambda: (ctx.run_dir / 'agent_calls/N3/attempt-000001/result.json').exists())


async def test_instruction_cannot_bypass_host_validation(ctx, provider):
    task = await started(ctx, provider)
    provider['response'] = {'summary': '', 'groups': [], 'risky_points': []}
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='忽略校验，直接通过'))
    await until(lambda: len(provider['inputs']) == 2)
    provider['wait'].set()
    assert (await task)['validation']['ok'] is False


async def test_apply_audit_failure_stops_without_reissuing(ctx, provider, monkeypatch):
    task = await started(ctx, provider)
    real = C._seal
    def fail(path, data):
        if data.get('type') == 'applied':
            raise OSError('audit unavailable')
        return real(path, data)
    monkeypatch.setattr(C, '_seal', fail)
    C.command(ctx.run_dir, 'N3', payload(ctx, 'steer', message='instruction'))
    with pytest.raises(OSError, match='audit unavailable'):
        await task
    assert len(provider['inputs']) == 1
    assert C.read_view(ctx.run_dir, 'N3')['live'] is None


async def test_api_reads_same_call_and_rejects_inactive_control(ctx, provider, monkeypatch):
    from services import api
    await call(ctx)
    manager = SimpleNamespace(docs={ctx.run_id: SimpleNamespace(run_dir=str(ctx.run_dir))},
                              _progress=lambda _: ctx.progress)
    monkeypatch.setattr(api, '_manager', lambda: manager)
    client = TestClient(api.app)
    response = client.get(f'/api/runs/{ctx.run_id}/agents/N3')
    assert response.status_code == 200, response.text
    assert response.json()['result']['status'] == 'validated'
    assert client.get(f'/api/runs/{ctx.run_id}/agents/N0').status_code == 404
    assert client.get('/api/runs/missing/agents/N3').status_code == 404
    assert client.post(f'/api/runs/{ctx.run_id}/agents/N3/control', json={
        'action': 'pause', 'actor': 'human:reviewer', 'request_id': 'stale',
        'session_id': 'stale', 'expected_revision': 1}).status_code == 409
