"""H2a: observable response coverage and sealed author→reviewer handoff."""
import copy

import pytest

from host import agent_handoff as H, agent_memory as AM
from prompts.node_schemas import N6Output
from test_agent_context_memory import ctx, provider, Data, M, n6_response  # noqa: F401


def inputs(ctx):
    handoff = H.build(ctx, {'data': {'must_fix': ['fix', 'fix']}},
                      {'rework_requests': [{'case': 'demo', 'what': 'identity', 'basis': 'md5'}]})
    targets = [{'case': 'demo', 'source_md5': 'original', 'excerpt': {'text': 'old'}}]
    assignment = H.assignment(handoff, targets)
    output = n6_response('demo', old='old')
    output['issue_responses'] = [
        {'issue_id': i['issue_id'], 'target_sha256': assignment['target_sha256'],
         'disposition': 'addressed', 'explanation': 'candidate edit for review',
         'edit_refs': [{'case': 'demo', 'edit_index': 0}]}
        for i in handoff['issues']]
    return targets, handoff, assignment, output


def sealed(ctx, *, status='validated', alter=None):
    targets, handoff, assignment, output = inputs(ctx)
    request = {'input': {'targets': targets, 'rework_handoff': handoff,
                         'rework_assignment': assignment}}
    if alter:
        alter(request, output)
    attempt = AM.Attempt(ctx, 'N6', request)
    attempt.finish(status, payload={'data': output},
                   validation={'ok': status == 'validated', 'accepted': output})
    return {'data': copy.deepcopy(output), **attempt.refs()}


def test_assignment_binds_targets_without_changing_occurrence_ids(ctx):
    targets, handoff, assignment, output = inputs(ctx)
    before = copy.deepcopy((targets, handoff, output))
    assert assignment == H.assignment(handoff, targets)
    assert H.validate_responses(output, assignment) == output['issue_responses']
    changed = copy.deepcopy(targets); changed[0]['source_md5'] = 'new'
    assert H.assignment(handoff, changed)['target_sha256'] != assignment['target_sha256']
    assert H.assignment(handoff, changed)['issues'] == handoff['issues']
    assert (targets, handoff, output) == before


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'unknown', 'version', 'closed',
    'blank', 'nonstring', 'not_list', 'not_object', 'no_edit', 'bad_case', 'bad_index',
    'bool_index', 'duplicate_edit', 'blocked_edit', 'wrong_issue_case'])
def test_invalid_responses_fail_before_candidate_consumption(ctx, fault):
    _, _, assignment, output = inputs(ctx)
    responses = output['issue_responses']; first = responses[0]
    if fault == 'missing': responses.pop()
    elif fault == 'duplicate': responses.append(copy.deepcopy(first))
    elif fault == 'unknown': first['issue_id'] = 'other'
    elif fault == 'version': first['target_sha256'] = 'stale'
    elif fault == 'closed': first['disposition'] = 'closed'
    elif fault == 'blank': first['explanation'] = '  '
    elif fault == 'nonstring': first['explanation'] = {'text': 'not a string'}
    elif fault == 'not_list': output['issue_responses'] = 'invalid'
    elif fault == 'not_object': responses[0] = 'invalid'
    elif fault == 'no_edit': first['edit_refs'] = []
    elif fault == 'bad_case': first['edit_refs'][0]['case'] = 'outside'
    elif fault == 'bad_index': first['edit_refs'][0]['edit_index'] = 1
    elif fault == 'bool_index': first['edit_refs'][0]['edit_index'] = False
    elif fault == 'duplicate_edit': first['edit_refs'] *= 2
    elif fault == 'blocked_edit': first['disposition'] = 'blocked'
    else: assignment['issues'][-1]['case'] = 'different'
    result = M._validate('n6', {'data': output},
                         offered={'cases': {'demo'}, 'rework_assignment': assignment},
                         run_dir=ctx.run_dir)
    assert result['ok'] is False
    assert any('issue_responses' in p for p in result['problems'])


@pytest.mark.parametrize('disposition', ['blocked', 'not_applicable'])
def test_unresolved_author_opinion_is_preserved_without_closure(ctx, disposition):
    _, _, assignment, output = inputs(ctx)
    for response in output['issue_responses']:
        response.update(disposition=disposition, edit_refs=[])
    result = M._validate('n6', {'data': output},
                         offered={'cases': {'demo'}, 'rework_assignment': assignment},
                         run_dir=ctx.run_dir)
    assert result['ok'] is True
    assert result['accepted']['issue_responses'] == output['issue_responses']
    assert all('status' not in r for r in result['accepted']['issue_responses'])


def test_empty_assignment_compatibility_and_schema(ctx):
    output = n6_response('demo', old='old')
    assignment = H.assignment(H.build(ctx, {}, {}), [])
    assert H.validate_responses(output, assignment) == []
    assert N6Output.model_validate(output).issue_responses == []
    _, _, _, populated = inputs(ctx)
    assert N6Output.model_validate(populated).issue_responses[0].disposition == 'addressed'
    result = M._validate('n6', {'data': populated}, offered={'cases': {'demo'}}, run_dir=ctx.run_dir)
    assert result['ok'] is False  # unsolicited identities must not be silently discarded


def test_review_packet_uses_sealed_record_and_filters_by_owner(ctx):
    author = sealed(ctx)
    before = copy.deepcopy(author)
    for node, count in [('N8', 2), ('N11', 1)]:
        packet = H.for_reviewer(ctx, author, node)
        assert packet == H.for_reviewer(ctx, author, node)
        assert packet['availability'] == 'verified'
        assert packet['author_source']['request_ref'] == author['request_ref']
        assert len(packet['issues']) == count
        assert all(i['node'] == node for i in packet['issues'])
        assert {r['issue_id'] for r in packet['responses']} == {i['issue_id'] for i in packet['issues']}
        assert packet['referenced_edits'][0]['edit'] == author['data']['revisions'][0]['edits'][0]
        assert len(packet['candidate_sha256']) == 64
        assert 'closed' not in packet
    assert author == before


@pytest.mark.parametrize('fault', ['state_changed', 'partial', 'bad_ref', 'failed', 'interrupted',
    'target_changed', 'wrong_run', 'wrong_version', 'issues_changed', 'bad_shape'])
def test_review_rejects_bad_or_stale_author_records(ctx, fault):
    def alter(req, out):
        if fault == 'target_changed': req['input']['targets'][0]['source_md5'] = 'changed'
        elif fault == 'wrong_run': req['input']['rework_assignment']['run_id'] = 'other'
        elif fault == 'wrong_version': req['input']['rework_assignment']['version'] = 99
        elif fault == 'issues_changed': req['input']['rework_assignment']['issues'] = []
        elif fault == 'bad_shape': req['input'] = []
    status = {'failed': 'validation_failed', 'interrupted': 'interrupted'}.get(fault, 'validated')
    author = sealed(ctx, status=status, alter=alter)
    if fault == 'state_changed': author['data']['issue_responses'][0]['explanation'] = 'unsealed'
    elif fault == 'partial': del author['result_ref']
    elif fault == 'bad_ref': author['request_ref'] = '../request.json'
    with pytest.raises(ValueError):
        H.for_reviewer(ctx, author, 'N8')


def test_legacy_missing_and_standin_do_not_invent_verified_responses(ctx):
    assert H.for_reviewer(ctx, {}, 'N8')['availability'] == 'unavailable'
    author = sealed(ctx)
    with pytest.raises(ValueError):
        H.for_reviewer(ctx, {'data': author['data']}, 'N8')
    def old_format(req, out):
        req['input'].pop('rework_assignment')
        out.pop('issue_responses')
    legacy = sealed(ctx, alter=old_format)
    assert H.for_reviewer(ctx, legacy, 'N8')['availability'] == 'legacy'
    standin = sealed(ctx, status='standin')
    assert H.for_reviewer(ctx, standin, 'N8')['availability'] == 'standin'
    assert not H.for_reviewer(ctx, standin, 'N8').get('responses')


def test_new_responses_cannot_be_downgraded_to_legacy(ctx):
    author = sealed(ctx, alter=lambda req, out: req['input'].pop('rework_assignment'))
    with pytest.raises(ValueError):
        H.for_reviewer(ctx, author, 'N8')


def test_malformed_unrecorded_state_rejected_explicitly(ctx):
    with pytest.raises(ValueError):
        H.for_reviewer(ctx, {'data': ['invalid']}, 'N8')


def test_reconstruction_uses_selected_attempt_not_newer_or_cancelled(ctx):
    from types import SimpleNamespace
    author = sealed(ctx)
    packet = H.for_reviewer(ctx, author, 'N8')
    sealed(ctx)
    sealed(ctx, status='interrupted')
    recovered = SimpleNamespace(run_dir=ctx.run_dir, run_id=ctx.run_id)
    assert H.for_reviewer(recovered, author, 'N8') == packet


@pytest.mark.parametrize('node', ['N8', 'N11'])
async def test_review_handoff_budget_is_enforced_and_untrimmed(ctx, provider, node):
    def large(req, output):
        for response in output['issue_responses']:
            response['explanation'] = 'required detail ' * 10000
    author = sealed(ctx, alter=large)
    ctx.mode = 'drill'
    lib = ctx.run_dir / 'sandbox/TESTLIB'; lib.mkdir(parents=True)
    (lib / 'demo.sv').write_text('module demo; endmodule\n')
    with pytest.raises(RuntimeError, match='context budget'):
        await getattr(M, {'N8': 'n8_check', 'N11': 'n11_review'}[node])(
            Data(ctx, {'n6_author': author}))
    assert not provider['inputs']
    record = AM.verify_attempt(next((ctx.run_dir / 'agent_calls' / node).iterdir()))
    assert record['result']['status'] == 'error'
    assert record['request']['input']['author_handoff'] == H.for_reviewer(ctx, author, node)


async def test_n6_seals_mapping_then_both_reviewers_receive_it(ctx, provider, monkeypatch):
    targets, _, assignment, output = inputs(ctx)
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: targets)
    data = Data(ctx, {'n8_check': {'data': {'must_fix': ['fix', 'fix']}},
                     'n11_review': {'rework_requests': [{'case': 'demo', 'what': 'identity', 'basis': 'md5'}]}})
    provider['response'] = output
    author = await M.n6_author(data)
    assert author['data']['issue_responses'] == output['issue_responses']
    request = AM.verify_attempt((ctx.run_dir / author['request_ref']).parent)['request']
    assert request['input']['rework_assignment'] == assignment
    assert request['offered']['rework_assignment'] == assignment
    ctx.mode = 'drill'
    lib = ctx.run_dir / 'sandbox/TESTLIB'; lib.mkdir(parents=True)
    (lib / 'demo.sv').write_text('module demo; endmodule\n')
    def review_rows(value, ref):
        assigned = value['review_assignment']
        return [{'issue_id': i['issue_id'], 'review_context_sha256': assigned['review_context_sha256'],
                 'outcome': 'closed', 'rationale': 'checked material', 'evidence_refs': [ref],
                 'rework_index': None} for i in assigned['issues']]
    provider['response'] = lambda value: {
        'verdict': 'pass', 'findings': [], 'must_fix': [],
        'issue_reviews': review_rows(value, '/sandbox_cases/0/excerpt')}
    await M.n8_check(data)
    assert provider['inputs'][-1]['author_handoff'] == H.for_reviewer(ctx, author, 'N8')
    provider['response'] = lambda value: {
        'chain': 'intact', 'reasons': [], 'rework_requests': [], 'caveats': [],
        'issue_reviews': review_rows(value, '/identity/consistent')}
    await M.n11_review(data)
    assert provider['inputs'][-1]['author_handoff'] == H.for_reviewer(ctx, author, 'N11')


async def test_n6_missing_response_is_sealed_failed_and_not_published(ctx, provider, monkeypatch):
    targets, _, _, output = inputs(ctx)
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: targets)
    output.pop('issue_responses'); provider['response'] = output
    data = Data(ctx, {'n8_check': {'data': {'must_fix': ['fix']}}})
    with pytest.raises(RuntimeError, match='N6'):
        await M.n6_author(data)
    assert not data.get_state('n6_author')
    record = AM.verify_attempt(next((ctx.run_dir / 'agent_calls/N6').iterdir()))
    assert record['result']['status'] == 'validation_failed'


@pytest.mark.parametrize('node', ['N8', 'N11'])
async def test_bad_author_prevents_reviewer_model_call(ctx, provider, node):
    ctx.mode = 'drill'
    lib = ctx.run_dir / 'sandbox/TESTLIB'; lib.mkdir(parents=True)
    (lib / 'demo.sv').write_text('module demo; endmodule\n')
    data = Data(ctx, {'n6_author': {'request_ref': 'bad'}})
    with pytest.raises(ValueError):
        await getattr(M, {'N8': 'n8_check', 'N11': 'n11_review'}[node])(data)
    assert not provider['inputs']
