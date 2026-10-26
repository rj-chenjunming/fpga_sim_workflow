import copy
from types import SimpleNamespace

import pytest

from host import agent_handoff as H, agent_memory as AM
from test_agent_context_memory import ctx, provider, Data, M  # noqa: F401


def state(ctx, node='N8'):
    a = AM.Attempt(ctx, node, {'input': {}, 'schema': {}})
    data = {'must_fix': ['fix', 'fix']}
    a.finish('validated', payload={'data': data}, validation={'ok': True, 'accepted': data})
    return {'data': data, **a.refs()}


def test_stable_order_duplicates_and_no_mutation(ctx):
    n8 = state(ctx)
    n11 = {'rework_requests': [{'case': 'a', 'what': 'repair', 'basis': 'evidence'}]}
    before = copy.deepcopy((n8, n11))
    a = H.build(ctx, n8, n11)
    assert a == H.build(ctx, n8, n11)
    assert (n8, n11) == before
    assert [i['text'] for i in a['issues']] == ['fix', 'fix', 'a: repair（依据：evidence）']
    assert len({i['issue_id'] for i in a['issues']}) == 3
    assert a['issues'][0]['source']['record_integrity'] == 'verified'
    assert a['issues'][2]['source']['record_integrity'] == 'unrecorded'
    assert a['issues'][2]['case'] == 'a'
    assert a['issues'][0]['case'] is None
    assert all('status' not in i for i in a['issues'])


def test_ids_bind_run_attempt_and_feedback(ctx):
    first = state(ctx)
    original = H.build(ctx, first, {})['issues'][0]['issue_id']
    assert original != H.build(ctx, state(ctx), {})['issues'][0]['issue_id']
    changed = copy.deepcopy(first)
    changed['data']['must_fix'][0] = 'other'
    assert original != H.build(ctx, changed, {})['issues'][0]['issue_id']
    plain = {'data': {'must_fix': ['fix']}}
    other = SimpleNamespace(run_id='other', run_dir=ctx.run_dir)
    assert H.build(ctx, plain, {}) != H.build(other, plain, {})


@pytest.mark.parametrize('fault', ['partial', 'traversal', 'absolute', 'other_node',
    'tampered', 'missing', 'identity', 'symlink', 'shape'])
def test_invalid_provenance_is_rejected(ctx, fault, tmp_path):
    n8 = state(ctx)
    folder = (ctx.run_dir / n8['request_ref']).parent
    if fault == 'partial':
        del n8['result_ref']
    elif fault == 'traversal':
        n8['request_ref'] = '../outside/request.json'
    elif fault == 'absolute':
        n8['request_ref'] = str(ctx.run_dir / n8['request_ref'])
    elif fault == 'other_node':
        n8 = state(ctx, 'N11')
    elif fault == 'tampered':
        p = folder / 'result.json'
        p.chmod(0o600)
        p.write_text('{}')
    elif fault == 'missing':
        (folder / 'result.sha256').unlink()
    elif fault in ('identity', 'shape'):
        # Both files agree with one another but belong to the wrong run.
        import json, hashlib
        for name in ['request', 'result']:
            p = folder / (name + '.json')
            value = json.loads(p.read_text()); value['run_id'] = 'other'
            if fault == 'shape':
                value = []
            p.chmod(0o600); p.write_bytes(AM.encoded(value))
            digest = p.with_suffix('.sha256'); digest.chmod(0o600)
            digest.write_text(hashlib.sha256(p.read_bytes()).hexdigest())
    else:
        destination = tmp_path / 'moved'
        folder.rename(destination)
        folder.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError):
        H.build(ctx, n8, {})


async def test_n6_receives_and_seals_handoff(ctx, provider, monkeypatch):
    provider['cfg'].available = False
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: [])
    n8 = state(ctx)
    out = await M.n6_author(Data(ctx, {'n8_check': n8}))
    record = AM.verify_attempt((ctx.run_dir / out['request_ref']).parent)
    request = record['request']['input']
    assert request['rework_handoff'] == H.build(ctx, n8, {})
    assert request['rework_reasons'] == ['fix', 'fix']


async def test_bad_upstream_prevents_n6_model_request(ctx, provider, monkeypatch):
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: [])
    with pytest.raises(ValueError):
        await M.n6_author(Data(ctx, {'n8_check': {'request_ref': 'bad'}}))
    assert not provider['inputs']
    assert not (ctx.run_dir / 'agent_calls/N6').exists()


async def test_handoff_counts_toward_budget_without_truncation(ctx, provider, monkeypatch):
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: [])
    text = 'required evidence ' * 10000
    with pytest.raises(RuntimeError, match='context budget'):
        await M.n6_author(Data(ctx, {'n8_check': {'data': {'must_fix': [text]}}}))
    assert not provider['inputs']
    record = AM.verify_attempt(next((ctx.run_dir / 'agent_calls/N6').iterdir()))
    assert record['request']['input']['rework_handoff']['issues'][0]['requirement'] == text
    assert record['result']['status'] == 'error'
