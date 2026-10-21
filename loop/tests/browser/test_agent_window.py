"""Agent 窗口的输入与异步身份隔离；真实静态页、受控 API。"""
from urllib.parse import urlsplit
import pytest

from test_run_sessions import ui, static_url, select, tick, pw  # noqa: F401


def agent_view(run='A', node='N3', state='working', revision=1):
    actions = {'working': ['steer', 'pause', 'terminate'], 'paused': ['steer', 'resume', 'terminate']}
    return {'run_id': run, 'node': node, 'live': {'session_id': node + ':session-000001',
            'state': state, 'revision': revision, 'attempt': 1, 'available_actions': actions.get(state, [])},
            'attempts': [{'attempt': 1, 'status': 'incomplete', 'model': 'test-model'}],
            'selected_attempt': 1, 'request': {'input': {'run_id': run, 'task': node + ' input'},
            'info': 'task policy', 'model': 'test-model', 'instruct': 'check facts'},
            'result': None, 'events': [], 'controls': []}


def setup_window(ui):
    page, old_api = ui
    api = {'views': {('A', 'N3'): agent_view(), ('A', 'N8'): agent_view(node='N8'),
                     ('A', 'N10'): agent_view(node='N10'), ('B', 'N3'): agent_view('B')},
           'posts': [], 'pending': [], 'hold': False}
    def route(route):
        parts = urlsplit(route.request.url).path.split('/')
        run, node = parts[3], parts[5]
        if route.request.method == 'POST':
            api['posts'].append((run, node, route.request.post_data_json))
            api['pending'].append(route)
        elif api['hold']:
            api['pending'].append(route)
        else:
            route.fulfill(json=api['views'].get((run, node), agent_view(run, node)))
    page.route('**/api/runs/*/agents/**', route)
    select(page, 'A')
    page.locator('#segRun').click()
    page.locator('#agents [data-agent-node="N3"]').click()
    pw.expect(page.locator('#agentWindow')).to_be_visible()
    pw.expect(page.locator('#awStatus')).to_contain_text('运行中')
    return page, api


def test_card_opens_actual_input_and_poll_preserves_draft(ui):
    page, api = setup_window(ui)
    page.locator('#awMessage').fill('请核对端口宽度')
    page.locator('#awMessage').focus()
    tick(page)
    pw.expect(page.locator('#awMessage')).to_have_value('请核对端口宽度')
    pw.expect(page.locator('#awMessage')).to_be_focused()
    page.locator('#awInputDetails').evaluate('el => el.open = true')
    pw.expect(page.locator('#awInput')).to_contain_text('N3 input')
    assert not api['posts']


def test_control_captures_session_revision_and_deduplicates(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:operator')
    page.locator('#awMessage').fill('检查新增端口')
    page.locator('#awSteer').evaluate('el => { el.click(); el.click(); }')
    page.wait_for_timeout(80)
    assert len(api['posts']) == 1
    run, node, data = api['posts'][0]
    assert run == 'A' and node == 'N3'
    assert {k: data[k] for k in ['action','actor','message','session_id','expected_revision']} == {
        'action':'steer','actor':'human:operator','message':'检查新增端口',
        'session_id':'N3:session-000001','expected_revision':1}
    assert data['request_id']
    api['pending'].pop().fulfill(status=409,json={'detail':{'error':'窗口状态已变化'}})
    pw.expect(page.locator('#awError')).to_contain_text('窗口状态已变化')
    pw.expect(page.locator('#awMessage')).to_have_value('检查新增端口')


def test_close_and_reopen_ignores_old_get_and_submission(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:operator')
    page.locator('#awMessage').fill('old instruction')
    page.locator('#awSteer').click()
    page.wait_for_timeout(80)
    old_post = api['pending'].pop()
    page.locator('#awClose').click()
    select(page, 'B')
    page.locator('#segRun').click()
    page.locator('#agents [data-agent-node="N3"]').click()
    pw.expect(page.locator('#awIdentity')).to_contain_text('B')
    page.locator('#awMessage').fill('B instruction')
    old_post.fulfill(json={'status':'accepted','request_id':'old'})
    page.wait_for_timeout(80)
    pw.expect(page.locator('#awMessage')).to_have_value('B instruction')
    pw.expect(page.locator('#awReceipt')).not_to_contain_text('已接收')
    api['hold'] = True
    page.locator('#awRefresh').click()
    page.wait_for_timeout(80)
    old_get = api['pending'].pop()
    page.locator('#awClose').click()
    api['hold'] = False
    select(page, 'A')
    page.locator('#segRun').click()
    page.locator('#agents [data-agent-node="N3"]').click()
    old_get.fulfill(json=agent_view('B'))
    page.wait_for_timeout(80)
    pw.expect(page.locator('#awIdentity')).to_contain_text('A')
    pw.expect(page.locator('#awIdentity')).not_to_contain_text('B')


def test_checker_can_switch_nodes_and_historical_call_is_readonly(ui):
    page, api = setup_window(ui)
    page.locator('#awClose').click()
    page.locator('#agents [data-agent-node="N8"]').click()
    page.locator('#awMessage').fill('N8 only')
    page.locator('#awNode').select_option('N10')
    pw.expect(page.locator('#awIdentity')).to_contain_text('N10')
    pw.expect(page.locator('#awMessage')).to_have_value('')
    api['views'][('A','N10')]['live'] = None
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awStatus')).to_contain_text('只读')
    pw.expect(page.locator('#awSteer')).to_be_disabled()


def test_paused_controls_follow_server_actions_and_escape_closes(ui):
    page, api = setup_window(ui)
    api['views'][('A','N3')] = agent_view(state='paused', revision=3)
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awStatus')).to_contain_text('已暂停')
    pw.expect(page.locator('#awResume')).to_be_enabled()
    pw.expect(page.locator('#awPause')).to_be_disabled()
    page.keyboard.press('Escape')
    pw.expect(page.locator('#agentWindow')).not_to_be_visible()
    assert not api['posts']


def test_agent_window_narrow_layout_and_text_is_not_html(ui):
    page, api = setup_window(ui)
    page.set_viewport_size({'width':390,'height':844})
    api['views'][('A','N3')]['request']['input']['task']='<img src=x onerror=alert(1)>'
    page.locator('#awRefresh').click()
    page.locator('#awInputDetails').evaluate('el => el.open = true')
    pw.expect(page.locator('#awInput')).to_contain_text('<img')
    assert page.locator('#awInput img').count() == 0
    assert page.evaluate('document.getElementById("agentWindow").scrollWidth <= innerWidth')


def test_old_control_receipt_cannot_clear_new_session_draft(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:operator')
    page.locator('#awMessage').fill('old session message')
    page.locator('#awSteer').click()
    page.wait_for_timeout(80)
    old_post = api['pending'].pop()
    api['views'][('A','N3')]['live']['session_id'] = 'N3:session-000002'
    tick(page)
    pw.expect(page.locator('#awMessage')).to_be_enabled()
    page.locator('#awMessage').fill('new session draft')
    old_post.fulfill(json={'status':'accepted'})
    page.wait_for_timeout(80)
    pw.expect(page.locator('#awMessage')).to_have_value('new session draft')
    pw.expect(page.locator('#awReceipt')).not_to_contain_text('已接收')


def test_reopen_resets_attempt_selector_to_follow_latest(ui):
    page, api = setup_window(ui)
    page.locator('#awAttempt').select_option('1')
    page.locator('#awClose').click()
    select(page, 'B')
    page.locator('#segRun').click()
    page.locator('#agents [data-agent-node="N3"]').click()
    pw.expect(page.locator('#awIdentity')).to_contain_text('B')
    pw.expect(page.locator('#awAttempt')).to_have_value('')


def test_mismatched_response_cannot_enable_control_for_other_run(ui):
    page, api = setup_window(ui)
    api['views'][('A','N3')]=agent_view('B')
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awError')).to_contain_text('身份')
    pw.expect(page.locator('#awSteer')).to_be_disabled()
