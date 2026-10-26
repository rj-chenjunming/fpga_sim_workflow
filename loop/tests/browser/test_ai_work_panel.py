"""SPEC-09 §11: rendered results and controls observable through the real page."""
import pytest
from test_agent_window import setup_window, agent_view
from test_run_sessions import ui, static_url, pw, tick  # noqa: F401


def result(data, status='validated', *, accepted=None, standin=False):
    return {'status': status, 'payload': {'data': data, 'standin': standin},
            'validation': {'ok': status == 'validated', 'problems': [] if status == 'validated' else ['依据不匹配'],
                           'accepted': accepted if accepted is not None else data}}


def show(page, api, node, output):
    if node != 'N3':
        page.locator('#awClose').click()
        page.locator(f'#agents [data-agent-node="{node}"]').click()
    api['views'][('A', node)] = agent_view(node=node)
    api['views'][('A', node)]['result'] = output
    page.locator('#awRefresh').click()


def test_n3_accepted_result_is_readable_and_raw_is_collapsed(ui):
    page, api = setup_window(ui)
    show(page, api, 'N3', result({'summary': '原始候选'}, accepted={
        'summary': '寄存器位宽从 8 扩为 16，影响读写检查',
        'groups': [{'segment': '0x1000', 'kind': '位宽', 'diff_ids': ['D1'], 'why': '接口同步'}],
        'risky_points': ['检查高位读回 <img src=x onerror=alert(1)>']}))
    pw.expect(page.locator('#awResults')).to_contain_text('寄存器位宽从 8 扩为 16', timeout=1200)
    pw.expect(page.locator('#awResults')).to_contain_text('D1')
    pw.expect(page.locator('#awResults')).to_contain_text('接口同步')
    pw.expect(page.locator('#awValidation')).to_have_text('系统校验通过；业务放行另行判定')
    assert page.locator('#awResults img').count() == 0
    pw.expect(page.locator('#awOutput')).not_to_be_visible()
    assert not api['posts']


def test_n6_candidates_show_edits_basis_and_observation_points(ui):
    page, api = setup_window(ui)
    show(page, api, 'N6', result({'revisions': [{'case': 'tc_width', 'rationale': '端口变更 D1',
        'edits': [{'line': 14, 'old': 'read(8);', 'new': 'read(16);', 'basis': 'D1:14'}]}],
        'observation_points': [{'case': 'tc_width', 'marker': 'N6_width', 'addr': '0x1000',
                                'offset': '0x04', 'expected_value': '0x0010', 'basis': '新位定义'}],
        'notes': ['尚需编译验证'], 'rework_resolution': ['补上高位检查']}))
    pw.expect(page.locator('#awResults')).to_contain_text('tc_width', timeout=1200)
    for text in ['read(8);', 'read(16);', 'D1:14', 'N6_width', '0x0010', '尚需编译验证', '补上高位检查']:
        pw.expect(page.locator('#awResults')).to_contain_text(text)
    pw.expect(page.locator('#awResults')).to_contain_text('候选编辑；实际写入状态请查看节点执行详情')


def test_n8_suggestion_and_rejected_candidate_are_distinct_from_host(ui):
    page, api = setup_window(ui)
    show(page, api, 'N8', result({'verdict': 'rework', 'findings': [
        {'item': '高位检查', 'result': 'fail', 'basis': 'tc_width:14'}],
        'must_fix': ['补上断言']}, status='validation_failed'))
    pw.expect(page.locator('#awResults')).to_contain_text('AI 建议：返工', timeout=1200)
    for text in ['候选 / 未通过校验', '依据不匹配', '高位检查', 'tc_width:14', '补上断言']:
        pw.expect(page.locator('#awResults')).to_contain_text(text)
    pw.expect(page.locator('#awValidation')).not_to_contain_text('系统校验通过')


def test_standin_and_unrecognized_old_records_never_claim_validation(ui):
    page, api = setup_window(ui)
    show(page, api, 'N3', result({'summary': '替身摘要'}, standin=True))
    pw.expect(page.locator('#awMode')).to_contain_text('演练替身', timeout=1200)
    pw.expect(page.locator('#awValidation')).not_to_contain_text('系统校验通过')
    api['views'][('A', 'N3')]['result'] = {'status': 'old-format', 'unexpected': {'summary': '不可猜'}}
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awResults')).to_contain_text('结构未识别，请查看原始输出')
    pw.expect(page.locator('#awValidation')).to_contain_text('old-format')


def test_unknown_payload_shape_keeps_raw_access_without_invented_summary(ui):
    page, api = setup_window(ui)
    show(page, api, 'N3', result({'legacy_summary': '旧记录不可丢失'}))
    pw.expect(page.locator('#awResults')).to_contain_text('结构未识别，请查看原始输出', timeout=1200)
    page.locator('#awTechnical').evaluate('el => el.open = true')
    page.locator('#awOutputDetails').evaluate('el => el.open = true')
    pw.expect(page.locator('#awOutput')).to_be_visible()
    pw.expect(page.locator('#awOutput')).to_contain_text('旧记录不可丢失')


def test_no_records_does_not_mean_not_started(ui):
    page, api = setup_window(ui)
    api['views'][('A', 'N3')].update(live=None, request=None, result=None, attempts=[], selected_attempt=None)
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awResults')).to_contain_text('暂无可读取记录，执行状态未确认', timeout=1200)
    pw.expect(page.locator('#awControlForm')).not_to_be_visible()


def test_follow_latest_readable_history_is_readonly_even_with_new_live(ui):
    page, api = setup_window(ui)
    v = api['views'][('A', 'N3')]
    v['live']['attempt'] = 2
    v['result'] = result({'summary': '旧版成果'})
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awSelection')).to_contain_text('历史只读', timeout=1200)
    pw.expect(page.locator('#awSelection')).to_contain_text('当前执行 #2')
    pw.expect(page.locator('#awControlForm')).not_to_be_visible()
    pw.expect(page.locator('#awSteer')).to_be_disabled()
    v['selected_attempt'] = 2
    v['attempts'].append({'attempt': 2, 'status': 'incomplete'})
    v['result'] = None
    page.locator('#awCurrent').click()
    pw.expect(page.locator('#awControlForm')).to_be_visible()
    pw.expect(page.locator('#awSelection')).not_to_contain_text('历史只读')
    pw.expect(page.locator('#awResults')).not_to_contain_text('旧版成果')
    assert not api['posts']


def test_live_attempt_change_clears_old_draft_and_ignores_old_receipt(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:reviewer')
    page.locator('#awMessage').fill('旧尝试')
    page.locator('#awSteer').click()
    page.wait_for_timeout(80)
    old_post = api['pending'].pop()
    v = api['views'][('A', 'N3')]
    v['live']['attempt'] = 2
    v['selected_attempt'] = 2
    tick(page)
    pw.expect(page.locator('#awMessage')).to_have_value('', timeout=1200)
    page.locator('#awMessage').fill('新尝试草稿')
    old_post.fulfill(json={'status': 'accepted'})
    page.wait_for_timeout(80)
    pw.expect(page.locator('#awMessage')).to_have_value('新尝试草稿')
    pw.expect(page.locator('#awReceipt')).not_to_contain_text('命令已接收')


def test_terminate_requires_explicit_confirmation_and_can_cancel(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:reviewer')
    page.locator('#awTerminate').click()
    assert not api['posts'], 'termination must not be sent before confirmation'
    pw.expect(page.locator('#awStopConfirm')).to_contain_text('N3', timeout=1200)
    pw.expect(page.locator('#awStopConfirm')).to_contain_text('失败收敛')
    page.locator('#awStopCancel').click()
    pw.expect(page.locator('#awStopConfirm')).not_to_be_visible()
    page.locator('#awTerminate').click()
    page.locator('#awStopApply').click()
    page.wait_for_timeout(80)
    assert len(api['posts']) == 1
    assert api['posts'][0][2]['action'] == 'terminate'
    api['pending'].pop().fulfill(json={'status': 'accepted'})


def test_changed_revision_invalidates_termination_confirmation(ui):
    page, api = setup_window(ui)
    page.locator('#awActor').fill('human:reviewer')
    page.locator('#awTerminate').click()
    api['views'][('A', 'N3')]['live']['revision'] = 2
    tick(page)
    pw.expect(page.locator('#awStopConfirm')).not_to_be_visible(timeout=1200)
    page.locator('#awStopApply').evaluate('el => el.click()')
    assert not api['posts']


def test_poll_preserves_reading_position_and_result_dom(ui):
    page, api = setup_window(ui)
    show(page, api, 'N3', result({'summary': '稳定成果'}))
    pw.expect(page.locator('#awResults')).to_contain_text('稳定成果')
    api['views'][('A', 'N3')]['events'] = [
        {'kind': 'event', 'status': 'running', 'detail': {'i': i}} for i in range(60)]
    page.locator('#awRefresh').click()
    page.wait_for_timeout(80)
    page.locator('#awTimeline').evaluate('el => { el.parentElement.open = true; el.scrollTop = 100; }')
    page.locator('#awResults').evaluate('el => window.savedResultNode = el.firstElementChild')
    page.locator('#awMessage').fill('继续核对')
    page.locator('#awMessage').focus()
    tick(page)
    assert page.locator('#awResults').evaluate('el => el.firstElementChild === window.savedResultNode')
    assert page.locator('#awTimeline').evaluate('el => el.scrollTop') == 100
    pw.expect(page.locator('#awMessage')).to_be_focused()
    pw.expect(page.locator('#awMessage')).to_have_value('继续核对')


def test_refresh_failure_keeps_marked_old_results_and_disables_control(ui):
    page, api = setup_window(ui)
    show(page, api, 'N3', result({'summary': '保留这份成果'}))
    pw.expect(page.locator('#awResults')).to_contain_text('保留这份成果', timeout=1200)
    api['hold'] = True
    page.locator('#awRefresh').click()
    page.wait_for_timeout(80)
    api['pending'].pop().abort('failed')
    pw.expect(page.locator('#awFreshness')).to_contain_text('旧数据')
    pw.expect(page.locator('#awResults')).to_contain_text('保留这份成果')
    pw.expect(page.locator('#awSteer')).to_be_disabled()
    api['hold'] = False
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awFreshness')).not_to_contain_text('旧数据')


@pytest.mark.parametrize('node,stage', [('N3', None), ('N6', '修订'), ('N8', '修订'), ('N10', '验证')])
def test_ai_chip_and_role_share_panel_with_secondary_node_details(ui, node, stage):
    page, api = setup_window(ui)
    page.locator('#awClose').click()
    chip = page.locator(f'#viewRun [data-node-chip="{node}"]')
    if not chip.is_visible() and stage:
        page.locator('#viewRun .stage-head', has_text=stage).click()
    chip.click()
    pw.expect(page.locator('#agentWindow')).to_be_visible(timeout=1200)
    pw.expect(page.locator('#awNode')).to_have_value(node)
    pw.expect(page.locator('#nodeDetail')).not_to_be_visible()
    page.locator('#awNodeDetails').click()
    pw.expect(page.locator('#agentWindow')).not_to_be_visible()
    pw.expect(page.locator('#nodeDetail')).to_be_visible()
    page.keyboard.press('Escape')
    pw.expect(chip).to_be_focused()


def test_node_details_returns_to_single_agent_panel(ui):
    page, api = setup_window(ui)
    page.locator('#awNodeDetails').click()
    pw.expect(page.locator('#nodeDetail')).to_be_visible()
    page.locator('#ndAgentJump button').click()
    pw.expect(page.locator('#agentWindow')).to_be_visible()
    pw.expect(page.locator('#nodeDetail')).not_to_be_visible(timeout=1200)


@pytest.mark.parametrize('width', [320, 768, 1440])
def test_candidate_content_and_controls_fit_narrow_and_desktop_views(ui, width):
    from test_web_layout import assert_fits, capture
    page, api = setup_window(ui)
    page.set_viewport_size({'width': width, 'height': 900})
    show(page, api, 'N6', result({'revisions': [{'case': 'tc_register_width', 'rationale': '依据 D1 扩展高位读写检查',
        'edits': [{'line': 14, 'old': 'read(' + 'a' * 160 + ');',
                   'new': 'read(16); <img src=x onerror=alert(1)>', 'basis': 'D1:14'}]}],
        'notes': ['候选内容仍需实际应用与编译验证'], 'rework_resolution': []}))
    pw.expect(page.locator('#awResults')).to_contain_text('tc_register_width')
    assert_fits(page, '#agentWindow .btn, #agentWindow .input, #awResults pre')
    assert page.locator('#awResults img').count() == 0
    assert page.locator('#agentWindow').evaluate('el => el.scrollWidth <= el.clientWidth')
    page.locator('#awTechnical').evaluate('el => el.open = true')
    page.locator('#awMessage').fill('请补上高位断言')
    page.locator('#awMessage').focus()
    tick(page)
    pw.expect(page.locator('#awMessage')).to_be_focused()
    assert page.locator('#awTechnical').evaluate('el => el.open')
    page.locator('#awTechnical').evaluate('el => el.open = false')
    page.locator('#agentWindow').evaluate('el => el.scrollTop = 0')
    capture(page, f'{width}-n6-agent')
    page.keyboard.press('Escape')
    pw.expect(page.locator('#agentWindow')).not_to_be_visible()
    pw.expect(page.locator('#agents [data-agent-node="N6"]')).to_be_focused()
