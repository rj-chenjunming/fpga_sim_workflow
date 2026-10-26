"""Host 的只读返工意见投影；不持有问题关闭或业务写权。"""
import copy
import re
from pathlib import Path

from host import agent_memory as AM


def feedback(n8, n11):
    items = []
    if isinstance(n8.get('data'), dict):
        for value in n8['data'].get('must_fix', []):
            items.append({'node': 'N8', 'requirement': str(value), 'case': None,
                          'basis': None, 'text': str(value)})
    for req in n11.get('rework_requests') or []:
        if isinstance(req, dict):
            items.append({'node': 'N11', 'requirement': req.get('what'),
                          'case': req.get('case'), 'basis': req.get('basis'),
                          'text': f"{req.get('case')}: {req.get('what')}（依据：{req.get('basis')}）"})
    return items


def _source(ctx, node, state, snapshot):
    source = {'node': node, 'projection': 'workflow_state',
              'snapshot_sha256': AM.fingerprint(snapshot),
              'record_integrity': 'unrecorded', 'attempt': None,
              'request_ref': None, 'result_ref': None}
    if 'request_ref' not in state and 'result_ref' not in state:
        return source
    record, identity = _record(ctx, node, state)
    source.update(record_integrity='verified', attempt=identity['attempt'],
                  request_ref=state['request_ref'], result_ref=state['result_ref'],
                  request_sha256=AM.fingerprint(record['request']),
                  result_sha256=AM.fingerprint(record['result']))
    return source


def _record(ctx, node, state):
    request, result = state.get('request_ref'), state.get('result_ref')
    match = re.fullmatch(r'agent_calls/' + node + r'/attempt-([0-9]{6,})/request.json',
                         request) if isinstance(request, str) else None
    if not match or result != request.replace('/request.json', '/result.json'):
        raise ValueError('handoff source reference invalid')
    root = Path(ctx.run_dir).resolve()
    folder = Path(ctx.run_dir) / Path(request).parent
    for path in [folder, *folder.parents]:
        if path == Path(ctx.run_dir):
            break
        if path.is_symlink():
            raise ValueError('handoff source symlink rejected')
    if not folder.resolve().is_relative_to(root):
        raise ValueError('handoff source escapes run')
    try:
        record = AM.verify_attempt(folder)
    except (AttributeError, TypeError) as exc:
        raise ValueError('handoff source record shape invalid') from exc
    identity = {'run_id': ctx.run_id, 'node': node, 'attempt': int(match[1]), 'format_version': 1}
    if any(record['request'].get(k) != v for k, v in identity.items()):
        raise ValueError('handoff source identity mismatch')
    return record, identity


def build(ctx, n8, n11):
    """只验证源记录与快照身份；不把状态投影误当模型原文或业务验收。"""
    items = feedback(n8, n11)
    sources = {node: _source(ctx, node, state, [i for i in items if i['node'] == node])
               for node, state in [('N8', n8), ('N11', n11)]}
    issues = []
    positions = {'N8': 0, 'N11': 0}
    for item in items:
        node = item['node']
        position = positions[node]
        positions[node] += 1
        source = sources[node]
        identifier = AM.fingerprint({'version': 1, 'run_id': ctx.run_id,
                                     'source': source, 'position': position})
        issues.append({**item, 'issue_id': 'issue-' + identifier, 'source': source})
    return {'version': 1, 'run_id': ctx.run_id, 'issues': issues}


def assignment(handoff, targets):
    """Bind occurrences to the complete offered target snapshot, not applied files."""
    return {'version': 1, 'run_id': handoff['run_id'],
            'target_sha256': AM.fingerprint(targets),
            'issues': copy.deepcopy(handoff['issues'])}


def validate_responses(data, assigned):
    """Only structural claims and edit membership; never decide issue closure."""
    def reject(reason):
        raise ValueError('issue_responses: ' + reason)

    issues = (assigned or {}).get('issues', [])
    if not isinstance(issues, list) or any(
            not isinstance(i, dict) or not isinstance(i.get('issue_id'), str) for i in issues):
        reject('invalid assignment issues')
    by_id = {i['issue_id']: i for i in issues}
    if len(by_id) != len(issues):
        reject('duplicate assigned identity')
    responses = data.get('issue_responses', [])
    if not isinstance(responses, list):
        reject('expected list')
    revisions = {r['case']: r['edits'] for r in data.get('revisions', [])}
    seen = set()
    accepted = []
    for response in responses:
        if not isinstance(response, dict) or set(response) != {
                'issue_id', 'target_sha256', 'disposition', 'explanation', 'edit_refs'}:
            reject('invalid response fields')
        identifier = response['issue_id']
        if not isinstance(identifier, str) or identifier not in by_id or identifier in seen:
            reject('unknown or duplicate identity')
        seen.add(identifier)
        if response['target_sha256'] != assigned['target_sha256']:
            reject('target version mismatch')
        disposition = response['disposition']
        if disposition not in ('addressed', 'blocked', 'not_applicable'):
            reject('invalid disposition; author cannot close issues')
        if not isinstance(response['explanation'], str) or not response['explanation'].strip():
            reject('explanation required')
        refs = response['edit_refs']
        if not isinstance(refs, list) or bool(refs) != (disposition == 'addressed'):
            reject('edit references required only for addressed claims')
        used = set()
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {'case', 'edit_index'}:
                reject('invalid edit reference fields')
            case, index = ref['case'], ref['edit_index']
            if (not isinstance(case, str) or case not in revisions or type(index) is not int
                    or not 0 <= index < len(revisions[case])):
                reject('edit reference outside candidate')
            issue_case = by_id[identifier].get('case')
            if issue_case is not None and case != issue_case:
                reject('edit reference belongs to another case')
            if (case, index) in used:
                reject('duplicate edit reference')
            used.add((case, index))
        accepted.append(copy.deepcopy(response))
    if seen != set(by_id):
        reject('missing response for assigned issue')
    return accepted


def read_result(ctx, node, state):
    """Read one selected, sealed result; standin remains explicitly distinguishable."""
    record, identity = _record(ctx, node, state)
    source = {**identity, 'request_ref': state['request_ref'], 'result_ref': state['result_ref'],
              'request_sha256': AM.fingerprint(record['request']),
              'result_sha256': AM.fingerprint(record['result'])}
    result = record['result']
    if result.get('status') == 'standin':
        return record, source
    validation = result.get('validation')
    if (result.get('status') != 'validated' or not isinstance(validation, dict)
            or validation.get('ok') is not True):
        raise ValueError('author result is not validated')
    accepted = validation.get('accepted')
    if not isinstance(accepted, dict) or state.get('data') != accepted:
        raise ValueError('author state differs from sealed accepted result')
    return record, source


def for_reviewer(ctx, author, node):
    """Rebuild from the exact sealed N6 attempt, never from latest-by-directory."""
    if node not in ('N8', 'N11'):
        raise ValueError('unsupported handoff reviewer')
    if 'request_ref' not in author and 'result_ref' not in author:
        data = author.get('data', {})
        if not isinstance(data, dict):
            raise ValueError('author state shape invalid')
        if data.get('issue_responses'):
            raise ValueError('author responses have no sealed source')
        return {'availability': 'unavailable'}
    record, source = read_result(ctx, 'N6', author)
    standin = record['result']['status'] == 'standin'
    accepted = None if standin else record['result']['validation']['accepted']
    request = record['request'].get('input')
    if not isinstance(request, dict):
        raise ValueError('author request input shape invalid')
    if 'rework_assignment' not in request:
        if standin:
            return {'availability': 'standin', 'author_source': source}
        if accepted.get('issue_responses'):
            raise ValueError('author responses cannot downgrade to legacy')
        return {'availability': 'legacy', 'author_source': source}
    assigned = request['rework_assignment']
    handoff, targets = request.get('rework_handoff'), request.get('targets')
    if (not isinstance(handoff, dict) or handoff.get('version') != 1
            or handoff.get('run_id') != ctx.run_id or not isinstance(handoff.get('issues'), list)
            or not isinstance(targets, list) or assigned != assignment(handoff, targets)):
        raise ValueError('author assignment does not match run/targets/handoff')
    assigned_issues = assigned['issues']
    if any(not isinstance(i, dict) or not isinstance(i.get('issue_id'), str)
           or not i['issue_id'] or i.get('node') not in ('N8', 'N11') for i in assigned_issues):
        raise ValueError('author assignment issues invalid')
    if len({i['issue_id'] for i in assigned_issues}) != len(assigned_issues):
        raise ValueError('duplicate assigned identity')
    issues = [i for i in assigned_issues if i['node'] == node]
    if standin:
        # The Host's sealed assignment remains history even when no trustworthy
        # author response/candidate exists. Review assignment stays empty until a
        # verified author candidate is available; the next author must keep IDs.
        return {'availability': 'standin', 'author_source': source,
                'issues': copy.deepcopy(issues)}
    try:
        responses = validate_responses(accepted, assigned)
        selected = {i['issue_id'] for i in issues}
        responses = [r for r in responses if r['issue_id'] in selected]
        revisions = {r['case']: r['edits'] for r in accepted['revisions']}
        refs = sorted({(ref['case'], ref['edit_index'])
                       for response in responses for ref in response['edit_refs']})
        edits = [{'case': case, 'edit_index': index, 'edit': revisions[case][index]}
                 for case, index in refs]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError('author response record shape invalid') from exc
    return {'availability': 'verified', 'author_source': source,
            'target_sha256': assigned['target_sha256'],
            'candidate_sha256': AM.fingerprint({k: accepted.get(k) for k in
                                               ('revisions', 'observation_points')}),
            'issues': copy.deepcopy(issues), 'responses': responses,
            'referenced_edits': copy.deepcopy(edits)}
