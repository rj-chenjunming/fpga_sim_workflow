"""H2b associations must refer to unmodified provider list positions."""
import copy

import pytest

from host import agent_review as R, agent_memory as AM, agent_handoff as H
from test_agent_context_memory import ctx, M, provider, Data  # noqa: F401
from test_agent_responses import sealed, inputs
from test_agent_review import review_input, response, review_record


@pytest.mark.parametrize('node', ['N8', 'N11'])
@pytest.mark.parametrize('fault', ['scalar', 'wrong_item', 'blank', 'unlinked_bad_item'])
@pytest.mark.parametrize('assigned', [True, False])
def test_rework_feedback_is_validated_before_coercion_or_filtering(ctx, node, fault, assigned):
    value = review_input(ctx, sealed(ctx), node)
    if not assigned:
        value['author_handoff']['issues'] = []
        value['review_assignment'] = R.prepare(node, value)
    out = response(node, value, 'open')
    key = 'must_fix' if node == 'N8' else 'rework_requests'
    if fault == 'scalar':
        out[key] = out[key][0]
    elif fault == 'wrong_item':
        # N11 used to drop this first item, silently shifting the linked index.
        out[key].insert(0, 42)
    elif fault == 'blank':
        out[key][0] = ' ' if node == 'N8' else {'case': 'demo', 'what': ' ', 'basis': 'md5'}
    else:
        out[key].append(None)
    before = copy.deepcopy(out)
    result = M._validate(node.lower(), {'data': out}, offered={'review_context': value})
    assert not result['ok'], 'malformed original feedback must not become accepted evidence'
    assert any('issue_reviews' in p for p in result['problems'])
    assert out == before


@pytest.mark.parametrize('node', ['N8', 'N11'])
@pytest.mark.parametrize('fault', ['invalid_verdict', 'empty_rework', 'pass_with_rework', 'unlinked_bad_item'])
def test_sealed_reconstruction_uses_same_feedback_contract_even_when_stale(ctx, node, fault):
    author = sealed(ctx)
    def alter(value, out):
        key = 'must_fix' if node == 'N8' else 'rework_requests'
        verdict = 'verdict' if node == 'N8' else 'chain'
        if fault == 'invalid_verdict':
            out[verdict] = 'unknown'
        elif fault == 'empty_rework':
            out[verdict] = 'rework' if node == 'N8' else 'broken'
        elif fault == 'pass_with_rework':
            out[key] = ['repair'] if node == 'N8' else [{'case': 'demo', 'what': 'repair', 'basis': 'md5'}]
        else:
            out[verdict] = 'rework' if node == 'N8' else 'broken'
            out[key] = [None]
    review = review_record(ctx, author, node, alter=alter)
    newer = sealed(ctx)
    with pytest.raises(ValueError, match='issue_reviews'):
        R.for_author(ctx, newer, review if node == 'N8' else {}, review if node == 'N11' else {})


@pytest.mark.parametrize('node', ['N8', 'N11'])
def test_legacy_call_without_assignment_keeps_compatibility(node):
    raw = {'verdict': 'rework', 'must_fix': [42]} if node == 'N8' else {
        'chain': 'broken', 'rework_requests': [None, {'case': 'demo', 'what': 'repair', 'basis': 'md5'}]}
    assert M._validate(node.lower(), {'data': raw}, offered={})['ok']


def test_standin_author_cannot_erase_prior_issue_history(ctx):
    author = sealed(ctx, status='standin')
    before = copy.deepcopy(author)
    original = inputs(ctx)[1]['issues']
    rebuilt = R.for_author(ctx, author, {}, {})
    assert {i['issue_id'] for i in rebuilt['issues']} == {i['issue_id'] for i in original}
    assert all(i['previous_outcome'] == 'unreviewed' and i['status'] == 'open'
               for i in rebuilt['lifecycle'])
    for node in ('N8', 'N11'):
        packet = H.for_reviewer(ctx, author, node)
        assert packet['availability'] == 'standin'
        assert not packet.get('responses') and not packet.get('candidate_sha256')
        assert R.prepare(node, {'author_handoff': packet})['issues'] == []
    assert author == before


@pytest.mark.parametrize('fault', ['run', 'targets', 'assignment'])
def test_standin_request_cannot_bypass_handoff_integrity(ctx, fault):
    def alter(request, output):
        value = request['input']
        if fault == 'run': value['rework_handoff']['run_id'] = 'other'
        elif fault == 'targets': value['targets'][0]['source_md5'] = 'changed'
        else: value['rework_assignment']['target_sha256'] = 'changed'
    author = sealed(ctx, status='standin', alter=alter)
    with pytest.raises(ValueError):
        R.for_author(ctx, author, {}, {})


@pytest.mark.parametrize('node', ['N8', 'N11'])
async def test_raw_feedback_failure_is_sealed_before_events_or_ledger_effects(ctx, provider, monkeypatch, node):
    ctx.mode = 'drill'
    library = ctx.run_dir / 'sandbox/TESTLIB'
    library.mkdir(parents=True)
    (library / 'demo.sv').write_text('actual candidate')
    author = sealed(ctx)
    async def ask(_ctx, _node, **kwargs):
        out = response(node, kwargs['input_data'], 'open')
        out['must_fix' if node == 'N8' else 'rework_requests'].insert(0, None)
        return {'data': out}
    def forbidden(*args, **kwargs):
        pytest.fail('invalid review must fail before ledger writes')
    monkeypatch.setattr(M.MR, 'ask', ask)
    monkeypatch.setattr(M, '_ensure_case_state', forbidden)
    monkeypatch.setattr(M, '_set_case_state', forbidden)
    data = Data(ctx, {'n6_author': author})
    with pytest.raises(RuntimeError):
        await getattr(M, 'n8_check' if node == 'N8' else 'n11_review')(data)
    assert not data.emitted
    record = AM.verify_attempt(next((ctx.run_dir / 'agent_calls' / node).iterdir()))
    assert record['result']['status'] == 'validation_failed'
    assert record['result']['validation']['ok'] is False
