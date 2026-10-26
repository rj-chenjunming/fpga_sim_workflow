"""Version-bound reviewer decisions and read-only rework lifecycle projection."""
import copy
import re

from host import agent_handoff as H, agent_memory as AM


_RULES = {
    'N8': '原要求已满足或有证据证明不适用；仅依据本次提供的沙箱变更范围复核。',
    'N11': '原要求已满足或有证据证明不适用；依据当前身份/证据链，Host consistent 必须为 true。',
}
_ROOTS = {'N8': {'sandbox_cases', 'revision_points', 'applied_edits'},
          'N11': {'identity', 'evidence', 'case_states'}}
_PRIMARY = {'N8': {'sandbox_cases'}, 'N11': {'identity', 'evidence'}}


def prepare(node, value):
    if node not in _RULES:
        raise ValueError('unsupported issue reviewer')
    facts = {k: v for k, v in value.items() if k not in
             ('review_assignment', 'human_interventions', 'approved_experiences')}
    packet = value.get('author_handoff') or {}
    issues = packet.get('issues', []) if packet.get('availability') == 'verified' else []
    return {'version': 1, 'reviewer': node,
            'author_source': copy.deepcopy(packet.get('author_source')),
            'target_sha256': packet.get('target_sha256'),
            'candidate_sha256': packet.get('candidate_sha256'),
            'review_context_sha256': AM.fingerprint(facts),
            'issues': [{'issue_id': i['issue_id'], 'case': i.get('case'),
                        'requirement': i['requirement'], 'acceptance': _RULES[node]}
                       for i in issues]}


def _evidence_root(node, pointer, context):
    """Resolve only in-memory JSON Pointer; never interpret refs as file paths."""
    if not isinstance(pointer, str) or not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        raise ValueError('invalid evidence pointer')
    parts = [p.replace('~1', '/').replace('~0', '~') for p in pointer[1:].split('/')]
    if parts[0] not in _ROOTS[node]:
        raise ValueError('evidence outside current review materials')
    value = context
    try:
        for part in parts:
            if isinstance(value, list):
                if not re.fullmatch(r'0|[1-9][0-9]*', part):
                    raise ValueError('invalid evidence index')
                value = value[int(part)]
            elif isinstance(value, dict):
                value = value[part]
            else:
                raise ValueError('evidence pointer crosses scalar')
    except (KeyError, IndexError) as exc:
        raise ValueError('evidence pointer missing') from exc
    if value is None or value == '' or value == [] or value == {}:
        raise ValueError('evidence pointer is empty')
    return parts[0]


def validate(node, output, context):
    """One deterministic validator for both fresh output and sealed reconstruction."""
    try:
        return _validate(node, output, context)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError('issue_reviews: ' + str(exc)) from exc


def _validate(node, output, context):
    reviews = output.get('issue_reviews', [])
    if not isinstance(reviews, list):
        raise ValueError('expected list')
    if context is None:
        if reviews:
            raise ValueError('no offered review assignment')
        return []
    assigned = prepare(node, context)
    if context.get('review_assignment') != assigned:
        raise ValueError('assignment differs from current materials')
    expected = {i['issue_id']: i for i in assigned['issues']}
    if len(expected) != len(assigned['issues']):
        raise ValueError('duplicate assigned identity')
    requests = output.get('must_fix' if node == 'N8' else 'rework_requests', [])
    if not isinstance(requests, list):
        raise ValueError('invalid rework requests')
    overall = output.get('verdict' if node == 'N8' else 'chain')
    passing, reworking = ('pass', 'rework') if node == 'N8' else ('intact', 'broken')
    if overall not in (passing, reworking):
        raise ValueError('invalid overall review verdict')
    if (overall == passing and requests) or (overall == reworking and not requests):
        raise ValueError('verdict and rework requests are inconsistent')
    # Validate every original position before resolving any issue's index. Filtering
    # or coercion would silently bind a decision to different provider feedback.
    for request in requests:
        if node == 'N8':
            if not isinstance(request, str) or not request.strip():
                raise ValueError('empty or non-string repair requirement')
        elif not isinstance(request, dict) or any(
                not isinstance(request.get(k), str) or not request[k].strip()
                for k in ('case', 'what', 'basis')):
            raise ValueError('invalid repair requirement')
    seen = set()
    for row in reviews:
        if not isinstance(row, dict) or set(row) != {
                'issue_id', 'review_context_sha256', 'outcome', 'rationale', 'evidence_refs', 'rework_index'}:
            raise ValueError('invalid review fields')
        identifier = row['issue_id']
        if not isinstance(identifier, str) or identifier not in expected or identifier in seen:
            raise ValueError('unknown/cross-owner/duplicate issue')
        seen.add(identifier)
        if row['review_context_sha256'] != assigned['review_context_sha256']:
            raise ValueError('stale review context')
        if not isinstance(row['rationale'], str) or not row['rationale'].strip():
            raise ValueError('rationale required')
        refs = row['evidence_refs']
        if not isinstance(refs, list) or not refs:
            raise ValueError('evidence references required')
        roots = {_evidence_root(node, ref, context) for ref in refs}
        if len(set(refs)) != len(refs):
            raise ValueError('duplicate evidence pointer')
        outcome, index = row['outcome'], row['rework_index']
        if outcome == 'closed':
            if index is not None or not roots.intersection(_PRIMARY[node]):
                raise ValueError('closure requires primary material and no rework index')
            if node == 'N11' and (context.get('identity') or {}).get('consistent') is not True:
                raise ValueError('Host identity prohibits closure')
        elif outcome == 'open':
            if overall != ('rework' if node == 'N8' else 'broken'):
                raise ValueError('open issue prohibits pass/intact')
            if type(index) is not int or not 0 <= index < len(requests):
                raise ValueError('open issue requires valid rework index')
            request = requests[index]
            if node == 'N11':
                if expected[identifier]['case'] is not None and request['case'] != expected[identifier]['case']:
                    raise ValueError('repair linked to wrong case')
        else:
            raise ValueError('invalid review outcome')
    if seen != set(expected):
        raise ValueError('missing per-issue review')
    return copy.deepcopy(reviews)


def _selected_review(ctx, node, state, packet):
    """Classify missing/old/stale explicitly; corrupt or rejected records are errors."""
    if state.get('data') is not None and not isinstance(state['data'], dict):
        raise ValueError('invalid review state shape')
    if 'request_ref' not in state and 'result_ref' not in state:
        if (state.get('data') or {}).get('issue_reviews'):
            raise ValueError('review claims have no sealed source')
        return 'unreviewed', [], None
    record, source = H.read_result(ctx, node, state)
    if record['result']['status'] == 'standin':
        return 'unreviewed', [], source
    context = record['request'].get('input')
    accepted = record['result']['validation']['accepted']
    if not isinstance(context, dict):
        raise ValueError('invalid review input record')
    if 'review_assignment' not in context:
        if accepted.get('issue_reviews'):
            raise ValueError('new review cannot downgrade to legacy')
        return 'unreviewed', [], source
    reviews = validate(node, accepted, context)
    if node == 'N11':
        # Host can append requests, but must not replace/reorder sealed model requests.
        sealed_requests = accepted.get('rework_requests', [])
        if (state.get('rework_requests') or [])[:len(sealed_requests)] != sealed_requests:
            raise ValueError('review follow-up differs from sealed requests')
    if context['review_assignment']['author_source'] != packet.get('author_source'):
        return 'stale_review', [], source
    if context.get('author_handoff') != packet:
        raise ValueError('review material differs from selected author')
    return 'reviewed', reviews, source


def for_author(ctx, author, n8, n11):
    """Each new author candidate reopens prior closures; immutable history stays sealed."""
    if any(not isinstance(state, dict) for state in (author, n8, n11)):
        raise ValueError('invalid handoff state shape')
    fresh = H.build(ctx, n8, n11)
    carried, lifecycle, consumed = [], [], set()
    for node, state in [('N8', n8), ('N11', n11)]:
        packet = H.for_reviewer(ctx, author, node)
        status, reviews, source = _selected_review(ctx, node, state, packet)
        by_id = {row['issue_id']: row for row in reviews}
        new_items = [i for i in fresh['issues'] if i['node'] == node]
        for original in packet.get('issues', []):
            issue = copy.deepcopy(original)
            row = by_id.get(issue['issue_id'])
            outcome = row['outcome'] if row else ('unreviewed' if status == 'reviewed' else status)
            if row and outcome == 'open':
                index = row['rework_index']
                if index >= len(new_items):
                    raise ValueError('review follow-up not present in current state')
                follow_up = new_items[index]
                issue['follow_up'] = copy.deepcopy(follow_up)
                consumed.add(follow_up['issue_id'])
            carried.append(issue)
            lifecycle.append({'issue_id': issue['issue_id'], 'previous_outcome': outcome,
                              'status': 'reopened' if outcome == 'closed' else 'open',
                              'review_source': source,
                              'review_context_sha256': row['review_context_sha256'] if row else None})
    if not carried:
        return fresh
    identifiers = {i['issue_id'] for i in carried}
    consumed.update(i['follow_up']['issue_id'] for i in carried if i.get('follow_up'))
    for issue in fresh['issues']:
        if issue['issue_id'] not in identifiers and issue['issue_id'] not in consumed:
            carried.append(issue)
            identifiers.add(issue['issue_id'])
            lifecycle.append({'issue_id': issue['issue_id'], 'previous_outcome': 'new',
                              'status': 'open', 'review_source': None, 'review_context_sha256': None})
    return {**fresh, 'issues': carried, 'lifecycle': lifecycle}
