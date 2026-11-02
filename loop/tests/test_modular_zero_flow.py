"""完整图的合成数据测试；不替代历史夹具、真实模型或 FPGA 仿真验收。"""
import asyncio
import json

import pytest

from workflows.main_flow import RunManager


async def wait_view(manager, run_id, predicate):
    for _ in range(150):
        view = manager.run_view(run_id)
        if predicate(view):
            return view
        assert view['status'] != 'failed', view.get('error')
        await asyncio.sleep(0.1)
    pytest.fail(f'timed out: {manager.run_view(run_id)}')


@pytest.mark.parametrize('decision', ['no_impact_end', 'full_regression'])
async def test_synthetic_zero_branch_restores_and_obeys_decision(tmp_path, monkeypatch, decision):
    fixture = tmp_path / 'synthetic-zero-fixture'
    (fixture / 'evidence').mkdir(parents=True)
    documents = {
        'n1_manifest_new.json': {'parent': 'synthetic-baseline'},
        'n2_diff.json': {'has_change': False, 'diffs': [], 'entries': [],
                         'checks': {'self_check_ok': True}},
        'n5_impact.json': {'must_change': [], 'to_check': [],
                           'index_complete': True, 'index_gaps': []},
    }
    for name, payload in documents.items():
        (fixture / name).write_text(json.dumps(payload), encoding='utf8')
    (fixture / 'n12_report.md').write_text('Synthetic fixture: no real verification.\n', encoding='utf8')
    monkeypatch.setenv('LOOP_DRILL_FIXTURE', str(fixture))
    manager = RunManager()
    restored = None
    run_id = await manager.start(baseline='synthetic-baseline', mode='drill', scenario='cancel')
    def at_gate(gate):
        return lambda view: str((view.get('pending_interrupt') or {}).get('id') or '').startswith(gate)
    try:
        await wait_view(manager, run_id, at_gate('G1_diff_confirm:'))
        await manager.decide(run_id=run_id, gate='G1_diff_confirm', decision='confirmed',
                             actor='human:test', reason='synthetic test')
        await wait_view(manager, run_id, at_gate('G1_no_impact:'))
        await manager.stop_watching()
        restored = RunManager()
        report = await restored.async_restore_all()
        assert run_id in report['restored'], report
        await wait_view(restored, run_id, at_gate('G1_no_impact:'))
        await restored.decide(run_id=run_id, gate='G1_no_impact', decision=decision,
                              actor='human:test', reason='synthetic decision')
        if decision == 'no_impact_end':
            view = await wait_view(restored, run_id, lambda v: v['status'] == 'finished')
            nodes = {n['node'] for n in view['node_history']}
            assert 'HALT' in nodes and 'N9_submit' not in nodes
        else:
            view = await wait_view(restored, run_id, at_gate('JOB:'))
            assert view['status'] == 'waiting_job'
            assert restored.executions[run_id].is_waiting()
            nodes = {n['node'] for n in view['node_history']}
            assert 'N9_submit' in nodes
            restored.cancel_job(run_id, view['job']['job_id'])
            for _ in range(150):
                await restored.async_sync(run_id)
                if restored.run_view(run_id)['status'] == 'failed':
                    break
                await asyncio.sleep(0.1)
            assert restored.run_view(run_id)['status'] == 'failed'
        assert not ({'N6', 'N6_author', 'N6_apply', 'N7', 'N8'} & nodes)
    finally:
        if restored is not None:
            view = restored.run_view(run_id)
            job = view.get('job') or {}
            if job.get('phase') == 'running':
                restored.cancel_job(run_id, job['job_id'])
            await restored.stop_watching()
        await manager.stop_watching()
