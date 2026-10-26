import copy
from types import SimpleNamespace

import pytest

from host import agent_handoff as H, agent_memory as AM, agent_review as R
from test_agent_context_memory import ctx, provider, Data, M, n6_response  # noqa: F401
from test_agent_responses import sealed, inputs


def review_input(ctx, author, node='N8'):
    value = {'run_id': ctx.run_id, 'author_handoff': H.for_reviewer(ctx, author, node)}
    if node == 'N8':
        value.update(sandbox_cases=[{'file': 'demo.sv', 'excerpt': 'actual candidate'}],
                     revision_points=[{'case': 'demo'}], applied_edits=[])
    else:
        value.update(identity={'consistent': True, 'cases': [{'case': 'demo'}]},
                     evidence={'present': True}, case_states={})
    value['review_assignment'] = R.prepare(node, value)
    return value


def response(node, value, outcome='closed'):
    opened = outcome == 'open'
    if node == 'N8':
        out = {'verdict': 'rework' if opened else 'pass', 'findings': [],
               'must_fix': ['repair candidate'] if opened else []}
        refs = ['/sandbox_cases/0/excerpt']
    else:
        out = {'chain': 'broken' if opened else 'intact', 'reasons': [], 'caveats': [],
               'rework_requests': [{'case': 'demo', 'what': 'repair identity', 'basis': 'md5'}] if opened else []}
        refs = ['/identity/consistent']
    assigned = value['review_assignment']
    out['issue_reviews'] = [
        {'issue_id': i['issue_id'], 'review_context_sha256': assigned['review_context_sha256'],
         'outcome': outcome, 'rationale': 'checked against current material',
         'evidence_refs': refs[:], 'rework_index': 0 if opened else None}
        for i in assigned['issues']]
    return out


def review_record(ctx, author, node='N8', outcome='closed', *, alter=None, status='validated'):
    value = review_input(ctx, author, node)
    out = response(node, value, outcome)
    if alter:
        alter(value, out)
    attempt = AM.Attempt(ctx, node, {'input': value})
    attempt.finish(status, payload={'data': out}, validation={'ok': status == 'validated', 'accepted': out})
    state = {'data': copy.deepcopy(out), **attempt.refs()}
    if node == 'N11':
        state['rework_requests'] = copy.deepcopy(out['rework_requests'])
    return state


@pytest.mark.parametrize('node', ['N8', 'N11'])
def test_review_binds_full_current_material_and_requires_per_issue_verdict(ctx, node):
    author = sealed(ctx); value = review_input(ctx, author, node)
    before = copy.deepcopy(value)
    out = response(node, value)
    assert R.prepare(node, value) == value['review_assignment']
    assert all(i['acceptance'] and i['requirement'] for i in value['review_assignment']['issues'])
    checked = M._validate(node.lower(), {'data': out}, offered={'review_context': value})
    assert checked['ok'] is True
    assert checked['accepted']['issue_reviews'] == out['issue_reviews']
    key = 'sandbox_cases' if node == 'N8' else 'evidence'
    value[key] = [{'changed': 'new snapshot'}]
    value['review_assignment'] = R.prepare(node, value)
    assert value['review_assignment']['review_context_sha256'] != before['review_assignment']['review_context_sha256']
    assert M._validate(node.lower(), {'data': out}, offered={'review_context': value})['ok'] is False


@pytest.mark.parametrize('node', ['N8', 'N11'])
@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'unknown', 'other_owner', 'stale',
    'blank', 'no_refs', 'nonexistent_ref', 'claim_as_evidence', 'bad_type', 'extra', 'closed_index',
    'open_no_index', 'open_bool_index', 'open_outside', 'open_pass', 'wrong_context'])
def test_invalid_review_is_rejected(ctx, node, fault):
    author = sealed(ctx); value = review_input(ctx, author, node)
    out = response(node, value, 'open' if fault.startswith('open') else 'closed')
    row = out['issue_reviews'][0]
    if fault == 'missing': out['issue_reviews'].pop()
    elif fault == 'duplicate': out['issue_reviews'].append(copy.deepcopy(row))
    elif fault == 'unknown': row['issue_id'] = 'unknown'
    elif fault == 'other_owner':
        other = H.for_reviewer(ctx, author, 'N11' if node == 'N8' else 'N8')
        row['issue_id'] = other['issues'][0]['issue_id']
    elif fault == 'stale': row['review_context_sha256'] = 'old'
    elif fault == 'blank': row['rationale'] = ' '
    elif fault == 'no_refs': row['evidence_refs'] = []
    elif fault == 'nonexistent_ref': row['evidence_refs'] = ['/sandbox_cases/500']
    elif fault == 'claim_as_evidence': row['evidence_refs'] = ['/author_handoff/responses/0/explanation']
    elif fault == 'bad_type': row['rationale'] = ['not a string']
    elif fault == 'extra': row['approved_by'] = 'human'
    elif fault == 'closed_index': row['rework_index'] = 0
    elif fault == 'open_no_index': row['rework_index'] = None
    elif fault == 'open_bool_index': row['rework_index'] = False
    elif fault == 'open_outside': row['rework_index'] = 999
    elif fault == 'open_pass': out['verdict' if node == 'N8' else 'chain'] = 'pass' if node == 'N8' else 'intact'
    else: value['review_assignment']['reviewer'] = 'N6'
    checked = M._validate(node.lower(), {'data': out}, offered={'review_context': value})
    assert checked['ok'] is False
    assert any('issue_reviews' in p for p in checked['problems'])


def test_identity_failure_cannot_be_closed_and_known_case_cannot_be_misassociated(ctx):
    value = review_input(ctx, sealed(ctx), 'N11')
    value['identity']['consistent'] = False
    value['review_assignment'] = R.prepare('N11', value)
    out = response('N11', value)
    with pytest.raises(ValueError): R.validate('N11', out, value)
    out = response('N11', value, 'open')
    out['rework_requests'][0]['case'] = 'other'
    with pytest.raises(ValueError): R.validate('N11', out, value)


@pytest.mark.parametrize('node', ['N8', 'N11'])
def test_new_candidate_reopens_closed_issues_and_keeps_ids_without_mutating_history(ctx, node):
    author = sealed(ctx)
    review = review_record(ctx, author, node)
    before = copy.deepcopy((author, review))
    states = {'N8': {}, 'N11': {}, node: review}
    rebuilt = R.for_author(ctx, author, states['N8'], states['N11'])
    original = H.for_reviewer(ctx, author, node)['issues']
    rows = {r['issue_id']: r for r in rebuilt['lifecycle']}
    for issue in original:
        assert issue['issue_id'] in {i['issue_id'] for i in rebuilt['issues']}
        row = rows[issue['issue_id']]
        assert row['previous_outcome'] == 'closed'
        assert row['status'] == 'reopened'
        assert row['review_source']['request_ref'] == review['request_ref']
    recovered = SimpleNamespace(run_dir=ctx.run_dir, run_id=ctx.run_id)
    review_record(ctx, author, node, status='interrupted')  # orphan, never selected
    assert R.for_author(recovered, author, states['N8'], states['N11']) == rebuilt
    assert (author, review) == before


@pytest.mark.parametrize('node', ['N8', 'N11'])
def test_open_feedback_reuses_existing_ids_and_only_unlinked_findings_are_new(ctx, node):
    author = sealed(ctx)
    def add(value, out):
        if node == 'N8': out['must_fix'].append('new separate problem')
        else: out['rework_requests'].append({'case': 'demo', 'what': 'new problem', 'basis': 'new evidence'})
    review = review_record(ctx, author, node, 'open', alter=add)
    # Adding output feedback does not change review input snapshot.
    states = {'N8': {}, 'N11': {}, node: review}
    rebuilt = R.for_author(ctx, author, states['N8'], states['N11'])
    assert len(rebuilt['issues']) == 4  # three original occurrences plus one unlinked finding
    original = H.for_reviewer(ctx, author, node)['issues']
    by_id = {i['issue_id']: i for i in rebuilt['issues']}
    for issue in original:
        assert by_id[issue['issue_id']]['source'] == issue['source']
        assert by_id[issue['issue_id']]['follow_up']['source']['request_ref'] == review['request_ref']
    assert all(r['status'] == 'open' for r in rebuilt['lifecycle'])


def test_stale_review_does_not_close_new_author_and_legacy_is_unreviewed(ctx):
    old_author = sealed(ctx); review = review_record(ctx, old_author)
    author = sealed(ctx)
    rebuilt = R.for_author(ctx, author, review, {})
    assert {r['previous_outcome'] for r in rebuilt['lifecycle']} == {'stale_review', 'unreviewed'}
    assert all(r['status'] == 'open' for r in rebuilt['lifecycle'])
    assert R.for_author(ctx, {}, {}, {}) == H.build(ctx, {}, {})
    legacy = {'data': {'must_fix': ['legacy']}}
    assert all(r['status'] == 'open' for r in R.for_author(ctx, author, legacy, {})['lifecycle'])


@pytest.mark.parametrize('fault', ['state_changed', 'wrong_assignment', 'failure', 'partial', 'unrecorded_claim', 'followup_changed', 'stale_followup_changed'])
def test_invalid_review_record_fails_instead_of_downgrading(ctx, fault):
    author = sealed(ctx)
    def alter(value, out):
        if fault == 'wrong_assignment': value['review_assignment']['review_context_sha256'] = 'wrong'
    review = review_record(ctx, author, 'N11', 'open', alter=alter,
                           status='validation_failed' if fault == 'failure' else 'validated')
    if fault == 'state_changed': review['data']['issue_reviews'][0]['rationale'] = 'unsealed'
    elif fault == 'partial': review.pop('result_ref')
    elif fault == 'unrecorded_claim': review = {'data': review['data']}
    elif fault in ('followup_changed', 'stale_followup_changed'):
        review['rework_requests'][0]['what'] = 'unsealed'
        if fault == 'stale_followup_changed': author = sealed(ctx)
    with pytest.raises(ValueError): R.for_author(ctx, author, {}, review)


async def test_actual_nodes_seal_review_reopen_on_rework_and_preserve_real_rework_edges(ctx, provider, monkeypatch):
    author = sealed(ctx)
    targets = inputs(ctx)[0]
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: targets)
    # Stub existing ledger I/O only; run real N8/N11 branching/counters and model request sealing.
    monkeypatch.setattr(M, '_ensure_case_state', lambda *_: None)
    monkeypatch.setattr(M, '_set_case_state', lambda *a, **kw: {'rc': 0})
    monkeypatch.setattr(M, '_host_identity', lambda *_: {'consistent': True, 'cases': []})
    lib = ctx.run_dir / 'sandbox/TESTLIB'; lib.mkdir(parents=True)
    (lib/'demo.sv').write_text('actual candidate')
    data = Data(ctx, {'n6_author': author})
    outcomes = {'N8': 'closed', 'N11': 'open'}
    async def ask(ctx, node, **kwargs):
        value = kwargs['input_data']
        if node != 'N6': return {'data': response(node, value, outcomes[node])}
        out = n6_response('demo', old='old')
        out['issue_responses'] = [
            {'issue_id': i['issue_id'], 'target_sha256': value['rework_assignment']['target_sha256'],
             'disposition': 'blocked', 'explanation': 'needs review', 'edit_refs': []}
            for i in value['rework_assignment']['issues']]
        return {'data': out}
    monkeypatch.setattr(M.MR, 'ask', ask)
    checked = await M.n8_check(data)
    assert checked['data']['issue_reviews'][0]['outcome'] == 'closed'
    guarded = await M.n11_review(data)
    assert 'N11_REWORK' in data.emitted
    assert guarded['data']['issue_reviews'][0]['outcome'] == 'open'
    new_author = await M.n6_author(data)
    record = AM.verify_attempt((ctx.run_dir/new_author['request_ref']).parent)
    history = record['request']['input']['rework_handoff']['lifecycle']
    assert [r['status'] for r in history] == ['reopened', 'reopened', 'open']
    assert len(new_author['data']['issue_responses']) == 3
    outcomes['N8'] = 'open'; data.emitted.clear()
    ctx.mode = 'drill'
    await M.n8_check(data)
    assert data.emitted == ['N8_ESCALATE']


def test_correct_source_ref_cannot_mask_changed_author_material(ctx):
    author = sealed(ctx)
    def alter(value, out):
        value['author_handoff']['candidate_sha256'] = 'forged candidate'
        value['review_assignment'] = R.prepare('N8', value)
        out.update(response('N8', value))
    review = review_record(ctx, author, alter=alter)
    with pytest.raises(ValueError): R.for_author(ctx, author, review, {})


def test_stale_followup_does_not_duplicate_issue_on_another_round(ctx):
    author = sealed(ctx)
    review = review_record(ctx, author, outcome='open')
    handoff = R.for_author(ctx, author, review, {})
    targets = inputs(ctx)[0]
    assigned = H.assignment(handoff, targets)
    output = n6_response('demo', old='old')
    output['issue_responses'] = [
        {'issue_id': i['issue_id'], 'target_sha256': assigned['target_sha256'],
         'disposition': 'blocked', 'explanation': 'needs review', 'edit_refs': []}
        for i in assigned['issues']]
    a = AM.Attempt(ctx, 'N6', {'input': {'targets': targets, 'rework_handoff': handoff,
                                       'rework_assignment': assigned}})
    a.finish('validated', payload={'data': output}, validation={'ok': True, 'accepted': output})
    newer = {'data': output, **a.refs()}
    rebuilt = R.for_author(ctx, newer, review, {})
    assert len(rebuilt['issues']) == len(handoff['issues']) == 3
    assert {i['issue_id'] for i in rebuilt['issues']} == {i['issue_id'] for i in handoff['issues']}


def test_malformed_state_rejected_as_provenance_error(ctx):
    with pytest.raises(ValueError):
        R.for_author(ctx, sealed(ctx), {'data': ['not an object']}, {})


def test_standin_cannot_close_and_json_pointer_escaping_is_supported(ctx):
    author = sealed(ctx)
    review = review_record(ctx, author, status='standin')
    rebuilt = R.for_author(ctx, author, review, {})
    assert all(i['status'] == 'open' and i['previous_outcome'] == 'unreviewed'
               for i in rebuilt['lifecycle'])
    value = review_input(ctx, author, 'N11')
    value['evidence']['a/b'] = {'~v': 'current proof'}
    value['review_assignment'] = R.prepare('N11', value)
    out = response('N11', value)
    out['issue_reviews'][0]['evidence_refs'] = ['/evidence/a~1b/~0v']
    assert R.validate('N11', out, value) == out['issue_reviews']


async def test_carried_history_is_budgeted_without_dropping_issues(ctx, provider, monkeypatch):
    text = 'historical requirement ' * 10000
    def large(request, output):
        for key in ('rework_handoff', 'rework_assignment'):
            request['input'][key]['issues'][0].update(requirement=text, text=text)
    author = sealed(ctx, alter=large)
    monkeypatch.setattr(M, 'build_n6_targets', lambda *_: inputs(ctx)[0])
    data = Data(ctx, {'n6_author': author})
    with pytest.raises(RuntimeError, match='context budget'):
        await M.n6_author(data)
    assert not provider['inputs']
    records = sorted((ctx.run_dir/'agent_calls/N6').iterdir())
    record = AM.verify_attempt(records[-1])
    assert record['result']['status'] == 'error'
    assert record['request']['input']['rework_handoff']['issues'][0]['requirement'] == text


@pytest.mark.parametrize('node', ['N8', 'N11'])
async def test_missing_review_is_sealed_failed_before_node_pass(ctx, provider, monkeypatch, node):
    ctx.mode = 'drill'
    lib = ctx.run_dir/'sandbox/TESTLIB'; lib.mkdir(parents=True)
    (lib/'demo.sv').write_text('actual candidate')
    author = sealed(ctx)
    provider['response'] = {'verdict': 'pass', 'must_fix': [], 'findings': []} if node == 'N8' else {
        'chain': 'intact', 'rework_requests': [], 'reasons': [], 'caveats': []}
    data = Data(ctx, {'n6_author': author})
    with pytest.raises(RuntimeError):
        await getattr(M, {'N8': 'n8_check', 'N11': 'n11_review'}[node])(data)
    assert not data.emitted
    record = AM.verify_attempt(next((ctx.run_dir/'agent_calls'/node).iterdir()))
    assert record['result']['status'] == 'validation_failed'
