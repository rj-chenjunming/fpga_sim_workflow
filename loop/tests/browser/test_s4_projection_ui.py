"""S4-C 界面验收：运行摘要投影 / 无进展红字 / S3 接面三列 / 内嵌两态与降级。

契约：[SPEC-REV-16](../../../doc/spec/SPEC-REV-16-20261028.md) §2（投影字段）、§3（无进展与文案禁令）、
§6（可用性端点、降级、`explain` 接面）。本文件只用**受控桩数据**，不调真实模型、不读真实运行目录。

纪律（红线 8）：
- 所有判断值（`no_progress.state`、`silence_s`、`threshold_s`、`compaction.count`、指令三态、
  WM 可用性、经验采用/拒用）都**只来自服务端字段**；用例故意下发"自相矛盾"的桩数据
  （如 `state=warn` 但 `silence_s` 远小于 `threshold_s`）来证明前端**不重算**判据。
- 文本一律走 `textContent`：桩里放 HTML 片段，断言页面上没有对应元素。

结构：窗口新增 `#awSummary`（运行摘要）+ `#awNoProgress`（红字告警）+ `#awS3`（accepted/applied/
effective 三列 + WM/EXP）+ `#awEmbed`（iframe 或降级块）。
"""
from urllib.parse import urlsplit

import pytest

from test_run_sessions import ui, static_url, select, tick, pw  # noqa: F401

NODE = 'N3'
#: SPEC-REV-16 §3.3 文案禁令（对整个页面文本生效）。
BANNED = ('在等人工', '等待人工', '等待处理', '待人工确认')


# ---------------------------------------------------------------- 桩数据
def progress(**over):
    """§2.1 字段；默认：运行中、无告警、压缩来源未知、执行方式为替身。"""
    data = {
        'identity': {'run_id': 'A', 'node': NODE, 'attempt': 2,
                     'session_id': NODE + ':session-000002'},
        'state': 'working',
        'current_action': {'kind': 'model_call', 'status': 'started', 'ts': 1000.0},
        'last_event': {'kind': 'model_call', 'status': 'started', 'ts': 1000.0, 'age_s': 12},
        'last_tool': {'name': 'read_file', 'status': 'ok', 'ts': 995.0},
        'last_error': {'message': 'provider timeout', 'ts': 990.0, 'source': 'request'},
        'elapsed_s': 120,
        'silence_s': 12,
        'no_progress': {'state': 'ok', 'silence_s': 12, 'since_ts': 1000.0,
                        'reason': '', 'threshold_s': 600},
        'compaction': {'count': None, 'source': 'unknown'},
        'execution': 'standin',
        'authority': 'projection',
    }
    data.update(over)
    return data


def explain(**over):
    """§6.3 服务端装配：前端只渲染，不判定。"""
    data = {
        'instructions': {
            'source': 'agent_control.instructions_view',
            'revision': 3,
            'items': [
                {'id': 'IL-1', 'scope': 'run', 'text_preview': '核对新增端口位宽',
                 'state_accepted': 'accepted', 'accepted_at': '2026-10-28T10:00:00Z',
                 'state_applied': 'not_applied', 'applied_attempt': None,
                 'state_effective': 'not_effective', 'effective_attempt': None,
                 'unavailable_reason': 'target_not_next_attempt'},
                {'id': 'IL-2', 'scope': 'attempt', 'text_preview': '保留现有断言',
                 'state_accepted': 'accepted', 'accepted_at': '2026-10-28T10:05:00Z',
                 'state_applied': 'applied', 'applied_attempt': 2,
                 'applied_ref': {'node': 'N3', 'attempt': 2},
                 'state_effective': 'effective', 'effective_attempt': 2,
                 'unavailable_reason': None},
            ],
        },
        'scope_expiry': {'determined': False, 'state': 'unknown',
                         'note': 'node_rework/run 终态到期未在归约层判定'},
        'working_memory': {'items': [
            {'id': 'N3.diffs', 'kind': 'observed_fact', 'availability': 'verified',
             'unavailable_reason': None, 'source_ref': '/diffs'},
            {'id': 'N3.coverage', 'kind': 'observed_fact', 'availability': 'unavailable',
             'unavailable_reason': '当前请求输入缺该字段', 'source_ref': '/coverage'},
        ]},
        'experiences': {
            'selected': [{'id': 'exp-ok', 'reason': 'applicable'}],
            'rejected': [{'id': 'exp-no', 'reason': 'baseline_mismatch'}],
        },
    }
    data.update(over)
    return data


def agent_view(payload_progress=None, payload_explain=None, **over):
    data = {
        'run_id': 'A', 'node': NODE,
        'live': {'session_id': NODE + ':session-000002', 'state': 'working', 'revision': 4,
                 'attempt': 2, 'available_actions': ['steer', 'pause', 'terminate']},
        'attempts': [{'attempt': 1, 'status': 'incomplete', 'model': 'test-model', 'cycle': 0},
                     {'attempt': 2, 'status': 'incomplete', 'model': 'test-model', 'cycle': 1}],
        'selected_attempt': 2,
        'request': {'input': {'run_id': 'A', 'task': NODE + ' input'}, 'info': 'task policy',
                    'model': 'test-model', 'instruct': 'check facts'},
        'result': None, 'events': [], 'controls': [],
        'capabilities': {'implemented': True, 'dependencies_ready': None,
                         'execution': 'standin', 'verification_scope': None},
        'context_budget': {'measured': False},
        'progress': progress() if payload_progress is None else payload_progress,
        'explain': explain() if payload_explain is None else payload_explain,
    }
    data.update(over)
    return data


def instance(**over):
    data = {'available': True, 'state': 'ready', 'reason': None,
            'url': '/instance/A/' + NODE + '/2/', 'embed': 'iframe',
            'authority': 'projection',
            # §6.1（S7c 只增）：反代只透传 HTTP，WebSocket 升级不通（§9-2）
            'stream': 'http_only'}
    data.update(over)
    return data


def session_copy(**over):
    """SPEC-REV-16 §6.2 稳定键：{available, reason, kind, facts, bytes, truncated}（无 content）。"""
    data = {'available': True, 'reason': None, 'kind': 'session_log_facts',
            'facts': {'compactions': 2, 'turns': 5}, 'bytes': 41, 'truncated': False}
    data.update(over)
    return data


# ---------------------------------------------------------------- 夹具
#: `inst=None` / `copy=None` 表示"后端没有该端点"（404）；缺省值才是默认桩。
MISSING = object()


def setup(ui, view=None, inst=MISSING, copy=MISSING, proxy=None):
    """受控 API：窗口 GET、/instance、/session-copy 全走桩；SSE 显式 404 ⇒ 轮询回退。"""
    page, ui_api = ui
    api = {
        'ui': ui_api,
        'view': view or agent_view(),
        'instance': instance() if inst is MISSING else inst,
        'copy': session_copy() if copy is MISSING else copy,
        'proxy': proxy or {'status': 200, 'json': {'available': True}},
        'posts': [], 'instance_reads': 0, 'copy_reads': 0, 'proxy_reads': 0,
        'requests': [], 'instance_by_attempt': {}, 'hold_proxy': False, 'pending_proxy': [],
    }

    def route_agents(route):
        url = urlsplit(route.request.url)
        path = url.path
        if route.request.method == 'GET':
            api['requests'].append(url.path + ('?' + url.query if url.query else ''))
        if route.request.method == 'POST':
            api['posts'].append((path, route.request.post_data_json))
            route.fulfill(json={'status': 'accepted', 'request_id': 'stub'})
            return
        if path.endswith('/stream'):
            route.fulfill(status=404, json={'detail': {'error': 'stream not stubbed'}})
            return
        if path.endswith('/instance'):
            api['instance_reads'] += 1
            payload = api['instance']
            query = dict(part.split('=', 1) for part in url.query.split('&') if '=' in part)
            if 'attempt' in query and int(query['attempt']) in api['instance_by_attempt']:
                payload = api['instance_by_attempt'][int(query['attempt'])]
            if payload is None:
                route.fulfill(status=404, json={'detail': {'error': 'not found'}})
            else:
                route.fulfill(json=payload)
            return
        if path.endswith('/session-copy'):
            api['copy_reads'] += 1
            if api['copy'] is None:
                route.fulfill(status=404, json={'detail': {'error': 'not found'}})
            else:
                route.fulfill(json=api['copy'])
            return
        route.fulfill(json=api['view'])

    def route_proxy(route):
        api['proxy_reads'] += 1
        accept = (route.request.headers or {}).get('accept', '')
        if 'application/json' in accept and api['hold_proxy']:
            api['pending_proxy'].append(route)
            return
        if 'application/json' in accept:
            route.fulfill(status=api['proxy']['status'], json=api['proxy']['json'])
        else:
            route.fulfill(status=200, content_type='text/html',
                          body='<html><body><p>stub instance</p></body></html>')

    page.route('**/api/runs/*/agents/**', route_agents)
    page.route('**/instance/**', route_proxy)
    select(page, 'A')
    page.locator('#segRun').click()
    page.locator('#agents [data-agent-node="' + NODE + '"]').click()
    # 首屏已渲染服务端投影（不预设运行状态与字段：缺失时也必须显示"未记录"而非空白）
    pw.expect(page.locator('#awSumIdentity')).not_to_contain_text('读取中')
    return page, api


def assert_agent_surface_has_no_human_wait_wording(page):
    """文案禁令作用域 = **Agent 运行状态面**（窗口 + 角色卡），不是整页。

    闸门视图的"等待人工决策"是闸门事实，属既有契约、不得被本用例牵连（Lead 2026-10-28 裁决）。
    """
    surfaces = {'#agentWindow': page.locator('#agentWindow').inner_text()}
    if page.locator('#agents').count():
        surfaces['#agents'] = page.locator('#agents').inner_text()
    for name, text in surfaces.items():
        for phrase in BANNED:
            assert phrase not in text, (name, phrase, text[:400])


# ---------------------------------------------------------------- 运行摘要
def test_summary_renders_server_fields_and_keeps_unknowns(ui):
    page, api = setup(ui)
    pw.expect(page.locator('#awSummary')).to_be_visible()
    pw.expect(page.locator('#awSumAction')).to_contain_text('model_call')
    pw.expect(page.locator('#awSumLastEvent')).to_contain_text('model_call')
    pw.expect(page.locator('#awSumLastTool')).to_contain_text('read_file')
    pw.expect(page.locator('#awSumLastError')).to_contain_text('provider timeout')
    pw.expect(page.locator('#awSumIdentity')).to_contain_text('session-000002')
    # standin 必须显示成替身，不得显示成真实完成（§2.3）
    pw.expect(page.locator('#awSumExecution')).to_contain_text('替身')
    pw.expect(page.locator('#awSumExecution')).not_to_contain_text('完成')
    # 压缩来源未知 ⇒ 显示「未知」，不得显示 0（§2.2）
    pw.expect(page.locator('#awSumCompaction')).to_contain_text('未知')
    assert page.locator('#awSumCompaction').inner_text().strip() != '0'
    pw.expect(page.locator('#awNoProgress')).to_be_hidden()
    assert_agent_surface_has_no_human_wait_wording(page)
    assert not api['posts']


def test_missing_progress_stays_unknown_not_zero(ui):
    view = agent_view()
    view.pop('progress')
    page, _ = setup(ui, view=view)
    pw.expect(page.locator('#awSummary')).to_contain_text('未记录')
    assert '0 次' not in page.locator('#awSummary').inner_text()
    pw.expect(page.locator('#awNoProgress')).to_be_hidden()
    assert_agent_surface_has_no_human_wait_wording(page)


def test_standin_execution_is_not_shown_as_real_completion(ui):
    page, _ = setup(ui, view=agent_view(payload_progress=progress(execution='standin', state='done')))
    pw.expect(page.locator('#awSumExecution')).to_contain_text('替身')
    pw.expect(page.locator('#awSumExecution')).not_to_contain_text('真实')


def test_failed_and_unknown_execution_are_reported_as_is(ui):
    failed_live = {'session_id': NODE + ':session-000002', 'state': 'failed', 'revision': 5,
                   'attempt': 2, 'available_actions': []}
    page, _ = setup(ui, view=agent_view(
        payload_progress=progress(state='failed', execution='unknown'), live=failed_live))
    # 失败显式：顶部状态与投影状态都写「失败」，不降级成"运行中"
    pw.expect(page.locator('#awStatus')).to_contain_text('失败')
    pw.expect(page.locator('#awSumState')).to_contain_text('失败')
    pw.expect(page.locator('#awSumState')).not_to_contain_text('完成')
    pw.expect(page.locator('#awSumExecution')).to_contain_text('未知')
    pw.expect(page.locator('#awSumExecution')).not_to_contain_text('替身')
    # 失败不是"在等人工"
    assert_agent_surface_has_no_human_wait_wording(page)


# ---------------------------------------------------------------- 无进展
def test_no_progress_warn_is_red_and_lists_event_and_error(ui):
    stalled = progress(no_progress={'state': 'warn', 'silence_s': 780, 'since_ts': 1000.0,
                                   'reason': '超过阈值无新事件', 'threshold_s': 600})
    page, api = setup(ui, view=agent_view(payload_progress=stalled))
    banner = page.locator('#awNoProgress')
    pw.expect(banner).to_be_visible()
    body = banner.inner_text()
    assert '无进展' in body and '13 分钟' in body  # 780 s 取整 = 13 分钟（只取整，不重算判据）
    assert 'model_call' in body                    # 最后事件
    assert 'provider timeout' in body              # 最后错误
    assert 'bad' in (banner.get_attribute('class') or '')
    # 只告警不收敛：状态仍是运行中、未发任何 /control 命令（§3.2）
    pw.expect(page.locator('#awStatus')).to_contain_text('运行中')
    assert not api['posts']
    assert_agent_surface_has_no_human_wait_wording(page)


def test_warn_comes_from_server_state_not_frontend_recompute(ui):
    """自相矛盾桩：state=warn 但 silence 远小于 threshold ⇒ 仍必须红字（前端不重算）。"""
    contradictory = progress(no_progress={'state': 'warn', 'silence_s': 130, 'since_ts': 1000.0,
                                         'reason': '服务端判定', 'threshold_s': 600})
    page, _ = setup(ui, view=agent_view(payload_progress=contradictory))
    banner = page.locator('#awNoProgress')
    pw.expect(banner).to_be_visible()
    pw.expect(banner).to_contain_text('2 分钟')


def test_unknown_no_progress_is_reported_unknown_not_ok(ui):
    unknown = progress(no_progress={'state': 'unknown', 'silence_s': None, 'since_ts': None,
                                    'reason': 'now 未注入或缺少最后事件时间', 'threshold_s': 600})
    page, _ = setup(ui, view=agent_view(payload_progress=unknown))
    pw.expect(page.locator('#awSumNoProgress')).to_contain_text('无进展未知')
    pw.expect(page.locator('#awSumNoProgress')).not_to_contain_text('正常')
    pw.expect(page.locator('#awNoProgress')).to_be_hidden()
    assert_agent_surface_has_no_human_wait_wording(page)


def test_ok_state_never_raises_banner_even_with_huge_silence(ui):
    huge = progress(no_progress={'state': 'ok', 'silence_s': 9999, 'since_ts': 1000.0,
                                 'reason': '', 'threshold_s': 600})
    page, _ = setup(ui, view=agent_view(payload_progress=huge))
    pw.expect(page.locator('#awSummary')).to_contain_text('model_call')
    pw.expect(page.locator('#awNoProgress')).to_be_hidden()


# ---------------------------------------------------------------- S3 接面
def test_s3_three_columns_keep_accepted_applied_effective_apart(ui):
    page, api = setup(ui)
    pw.expect(page.locator('#awS3')).to_be_visible()
    pw.expect(page.locator('#awS3 thead')).to_contain_text('accepted')
    pw.expect(page.locator('#awS3 thead')).to_contain_text('applied')
    pw.expect(page.locator('#awS3 thead')).to_contain_text('effective')
    row1 = page.locator('#awS3 tbody tr[data-instruction-id="IL-1"]')
    accepted1 = row1.locator('td.aw-s3-accepted')
    applied1 = row1.locator('td.aw-s3-applied')
    effective1 = row1.locator('td.aw-s3-effective')
    pw.expect(accepted1).to_contain_text('已接收')
    pw.expect(applied1).to_contain_text('未应用')
    pw.expect(applied1).not_to_contain_text('已应用')
    pw.expect(effective1).to_contain_text('未生效')
    pw.expect(effective1).not_to_contain_text('当前生效')
    pw.expect(effective1).to_contain_text('target_not_next_attempt')  # 原因原样来自服务端
    row2 = page.locator('#awS3 tbody tr[data-instruction-id="IL-2"]')
    pw.expect(row2.locator('td.aw-s3-applied')).to_contain_text('已应用')
    pw.expect(row2.locator('td.aw-s3-applied')).to_contain_text('#2')
    # applied_attempt 现在是 int；节点身份走附加字段 applied_ref，且不得渲染成 [object Object]
    pw.expect(row2.locator('td.aw-s3-applied')).to_contain_text('节点 N3')
    pw.expect(page.locator('#awS3')).not_to_contain_text('[object Object]')
    pw.expect(row2.locator('td.aw-s3-effective')).to_contain_text('当前生效')
    # 回执 ≠ 生效：同一行的 accepted 与 effective 不是同一句话
    assert accepted1.inner_text() != effective1.inner_text()
    assert_agent_surface_has_no_human_wait_wording(page)
    assert not api['posts']


def test_s3_scope_expiry_is_undetermined_and_wm_exp_are_readonly(ui):
    page, api = setup(ui)
    expiry = page.locator('#awS3Expiry')
    pw.expect(expiry).to_contain_text('未判定')
    pw.expect(expiry).not_to_contain_text('仍生效')
    wm = page.locator('#awS3Wm')
    pw.expect(wm).to_contain_text('N3.coverage')
    pw.expect(wm).to_contain_text('不可用')
    pw.expect(wm).to_contain_text('当前请求输入缺该字段')  # 原因原样透传
    exp = page.locator('#awS3Exp')
    pw.expect(exp).to_contain_text('exp-ok')
    pw.expect(exp).to_contain_text('exp-no')
    pw.expect(exp).to_contain_text('baseline_mismatch')
    assert not api['posts']  # 只读展示不发命令


def test_missing_explain_shows_not_recorded(ui):
    view = agent_view()
    view.pop('explain')
    page, _ = setup(ui, view=view)
    pw.expect(page.locator('#awS3')).to_contain_text('未记录')


# ---------------------------------------------------------------- 内嵌与降级
def test_available_instance_embeds_same_origin_url(ui):
    page, api = setup(ui, inst=instance())
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    src = page.locator('#awEmbedFrame').get_attribute('src')
    assert src.endswith('/instance/A/N3/2/')
    pw.expect(page.locator('#awEmbedFallback')).to_be_hidden()
    assert api['proxy_reads'] >= 1


def test_s8f_new_tab_prefers_direct_instance_url(ui):
    """S8f（REV-16 §6.1）：服务端给了 `direct_url` ⇒「在新标签页打开」指向**直连实例**。

    为什么不是反代 URL：反代只透传 HTTP，实时通道 `WS /api/remote.mux` 仍 405（§9-2）
    ⇒ 新标签页里的反代页面同样看不到会话列表。直连实例才有原生 WebSocket。
    """
    direct = 'http://127.0.0.1:43581/?token=T0KEN-managed'
    page, _ = setup(ui, inst=instance(direct_url=direct))
    link = page.locator('#awEmbedNewTab')
    assert link.get_attribute('href') == direct
    title = link.get_attribute('title')
    assert '直连' in title
    # 如实披露：token 会短暂进地址栏、仅本机可用
    assert 'token' in title
    assert '本机' in title
    # 内嵌仍然是同源反代 URL（不改内嵌语义）
    assert page.locator('#awEmbedFrame').get_attribute('src').endswith('/instance/A/N3/2/')


def test_s8f_new_tab_falls_back_to_proxy_url_without_direct(ui):
    """旧服务端/旧记录没有 `direct_url` ⇒ 退回反代 URL（不因为缺新字段就不给链接）。"""
    page, _ = setup(ui, inst=instance())
    link = page.locator('#awEmbedNewTab')
    assert link.get_attribute('href').endswith('/instance/A/N3/2/')
    assert '反代' in link.get_attribute('title')


def test_embedded_instance_discloses_websocket_stream_gap(ui):
    """S7c：内嵌成功 ≠ 完全可用 —— 必须**如实**说"实时流未接通"，不得静默半死。

    判据来源是服务端 `stream` 字段（能力事实），前端只渲染；断言文本含 WebSocket 与 §9-2，
    同时 iframe 仍然可见（不因实时流缺失就整块降级：页面可打开、可读快照）。
    """
    page, api = setup(ui, inst=instance())
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    pw.expect(page.locator('#awEmbedState')).to_contain_text('已内嵌')
    note = page.locator('#awEmbedStream')
    pw.expect(note).to_be_visible()
    pw.expect(note).to_contain_text('WebSocket')
    pw.expect(note).to_contain_text('§9-2')
    pw.expect(note).to_contain_text('在新标签页打开')
    assert not api['posts']


def test_old_metadata_without_stream_field_claims_nothing(ui):
    """旧服务端/旧记录没有 `stream` 字段 ⇒ 不显示这一行（不自己推断"有实时流"）。"""
    payload = instance()
    payload.pop('stream')
    page, _ = setup(ui, inst=payload)
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    pw.expect(page.locator('#awEmbedStream')).to_have_text('')


def test_degraded_instance_clears_stream_note(ui):
    page, _ = setup(ui, inst=instance(available=False, state='unavailable',
                                      reason='target_missing', url=None,
                                      embed='new_tab_only'))
    pw.expect(page.locator('#awEmbedFallback')).to_be_visible()
    pw.expect(page.locator('#awEmbedStream')).to_have_text('')


def test_unavailable_instance_degrades_with_reason_new_tab_and_session_copy(ui):
    page, api = setup(ui, inst=instance(available=False, state='unavailable',
                                        reason='target_missing', url=None,
                                        embed='new_tab_only'))
    block = page.locator('#awEmbedFallback')
    pw.expect(block).to_be_visible()
    pw.expect(block).to_contain_text('不可内嵌')
    pw.expect(block).to_contain_text('目标实例缺失')
    pw.expect(block).to_contain_text('在新标签页打开')
    pw.expect(block).to_contain_text('导出会话副本')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()
    # 导出会话副本：内容来自服务端 /session-copy（textContent，不拼 HTML）
    page.locator('#awSessionCopy').click()
    body = page.locator('#awSessionCopyBody')
    pw.expect(body).to_contain_text('session_log_facts')
    pw.expect(body).to_contain_text('非会话原文')
    pw.expect(body).to_contain_text('"compactions": 2')
    pw.expect(page.locator('#awEmbedCopyNote')).to_contain_text('kind=session_log_facts')
    assert api['copy_reads'] >= 1


def test_proxy_auth_failure_uses_same_fallback_not_white_screen(ui):
    page, api = setup(ui, inst=instance(),
                      proxy={'status': 503, 'json': {'available': False, 'state': 'unavailable',
                                                     'reason': 'upstream_auth'}})
    block = page.locator('#awEmbedFallback')
    pw.expect(block).to_be_visible()
    pw.expect(block).to_contain_text('不可内嵌')
    pw.expect(block).to_contain_text('401')
    pw.expect(block).to_contain_text('在新标签页打开')
    pw.expect(block).to_contain_text('导出会话副本')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()
    pw.expect(page.locator('#awEmbedState')).not_to_contain_text('已内嵌')
    # 401 不得显示成"需要人操作才能继续"
    assert_agent_surface_has_no_human_wait_wording(page)


def test_proxy_rejected_http_code_is_shown_verbatim(ui):
    """反代 400（`X-Instance-Proxy: rejected`）也要落到降级块并显示 HTTP 码，不改写成人工介入。"""
    page, _ = setup(ui, inst=instance(),
                    proxy={'status': 400, 'json': {'detail': {'error': 'rejected'}}})
    block = page.locator('#awEmbedFallback')
    pw.expect(block).to_contain_text('不可内嵌')
    pw.expect(block).to_contain_text('HTTP 400')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()
    assert_agent_surface_has_no_human_wait_wording(page)


def test_unavailable_session_copy_explains_reason(ui):
    """REV-16 §9-16（S7d）：`session_*` reason 必须给**中文说明**，不再直接甩英文枚举。

    枚举本身仍要可核（排障要靠它），所以两边都断言。
    """
    page, _ = setup(ui, inst=instance(available=False, state='unavailable',
                                      reason='target_missing', url=None),
                    copy=session_copy(available=False, reason='session_log_missing',
                                      kind=None, facts=None, bytes=None))
    page.locator('#awSessionCopy').click()
    note = page.locator('#awEmbedCopyNote')
    pw.expect(note).to_contain_text('session_log_missing')
    pw.expect(note).to_contain_text('元数据未声明会话日志')
    pw.expect(note).to_contain_text('会话副本不可用')


def test_unknown_session_reason_is_shown_verbatim_not_folded(ui):
    """未知 `session_*` 值原样显示（不折成"未知/不可用"这种模糊说法，也不猜含义）。"""
    page, _ = setup(ui, inst=instance(available=False, state='unavailable',
                                      reason='target_missing', url=None),
                    copy=session_copy(available=False, reason='session_future_value',
                                      kind=None, facts=None, bytes=None))
    page.locator('#awSessionCopy').click()
    note = page.locator('#awEmbedCopyNote')
    pw.expect(note).to_contain_text('session_future_value')
    assert '原因未知' not in note.text_content(), note.text_content()


def test_session_copy_without_kind_never_claims_full_text(ui):
    """缺 `kind` 时不得显示"会话副本全文"（稳定键契约里没有正文键）。"""
    page, _ = setup(ui, inst=instance(available=False, state='unavailable',
                                      reason='target_missing', url=None),
                    copy={'available': True, 'reason': None, 'kind': None,
                          'facts': {'compactions': 1}, 'bytes': 12, 'truncated': False})
    page.locator('#awSessionCopy').click()
    note = page.locator('#awEmbedCopyNote')
    pw.expect(note).to_contain_text('kind')
    pw.expect(page.locator('#awSessionCopyBody')).to_be_hidden()


def test_instance_and_session_copy_requests_carry_selected_attempt(ui):
    """P1-1：可用性/会话副本必须按**当前窗口选中的 attempt** 请求（服务端校验归属）。"""
    page, api = setup(ui, inst=instance(available=False, state='unavailable',
                                        reason='target_missing', url=None))
    pw.expect(page.locator('#awEmbedFallback')).to_contain_text('目标实例缺失')
    instance_urls = [u for u in api['requests'] if u.split('?')[0].endswith('/instance')]
    assert instance_urls and all('attempt=2' in u for u in instance_urls), instance_urls
    page.locator('#awSessionCopy').click()
    pw.expect(page.locator('#awEmbedCopyNote')).to_contain_text('kind')
    copy_urls = [u for u in api['requests'] if u.split('?')[0].endswith('/session-copy')]
    assert copy_urls and all('attempt=2' in u for u in copy_urls), copy_urls


def test_attempt_scoped_instance_two_states(ui):
    """attempt=2 可用 / attempt=1 不可用：切 attempt 后重新探并切换渲染（不沿用旧结论）。"""
    inst = instance()
    ui_api = ui[1]
    page, api = setup(ui, inst=inst)
    api['instance_by_attempt'] = {1: instance(available=False, state='unavailable',
                                             reason='target_missing', url=None)}
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    page.locator('#awAttempt').select_option('1')
    pw.expect(page.locator('#awEmbedFallback')).to_contain_text('目标实例缺失')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()
    assert any('attempt=1' in u for u in api['requests']), api['requests']
    page.locator('#awAttempt').select_option('')
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()


def test_probe_pending_does_not_claim_embedded(ui):
    """P2-5：探测中只能显示"正在确认可内嵌性"，成功后才置"已内嵌"。"""
    page, api = setup(ui, inst=instance())
    api['hold_proxy'] = True
    page.locator('#awRefresh').click()
    state = page.locator('#awEmbedState')
    pw.expect(state).to_contain_text('正在确认可内嵌性')
    pw.expect(state).not_to_contain_text('已内嵌')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()
    api['hold_proxy'] = False
    api['pending_proxy'].pop().fulfill(status=200, json={'available': True})
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    pw.expect(state).to_contain_text('已内嵌')


def test_refresh_reprobes_instance_and_recovers(ui):
    """一次不可用不得把同一 run/node 永久标死：刷新后重新读可用性（Lead 2026-10-28 口径）。"""
    page, api = setup(ui, inst=instance(available=False, state='unavailable',
                                        reason='target_missing', url=None))
    pw.expect(page.locator('#awEmbedFallback')).to_contain_text('目标实例缺失')
    reads_before = api['instance_reads']
    api['instance'] = instance()   # 服务端此刻已有可用实例
    page.locator('#awRefresh').click()
    pw.expect(page.locator('#awEmbedFrame')).to_be_visible()
    assert api['instance_reads'] > reads_before


def test_missing_instance_endpoint_degrades_instead_of_blank(ui):
    page, _ = setup(ui, inst=None)   # 旧后端没有该端点 ⇒ 404
    block = page.locator('#awEmbedFallback')
    pw.expect(block).to_contain_text('不可内嵌')
    pw.expect(page.locator('#awEmbedFrame')).to_be_hidden()


# ---------------------------------------------------------------- 安全与布局
def test_projection_text_is_not_html_and_narrow_layout_fits(ui):
    hostile = progress(last_error={'message': '<img src=x onerror=alert(1)>',
                                   'ts': 990.0, 'source': 'request'},
                       no_progress={'state': 'warn', 'silence_s': 780, 'since_ts': 1000.0,
                                    'reason': '<b>bad</b>', 'threshold_s': 600})
    page, _ = setup(ui, view=agent_view(payload_progress=hostile))
    pw.expect(page.locator('#awNoProgress')).to_be_visible()
    pw.expect(page.locator('#awSumLastError')).to_contain_text('<img')
    assert page.locator('#awSummary img').count() == 0
    assert page.locator('#awNoProgress b').count() == 0
    page.set_viewport_size({'width': 390, 'height': 844})
    tick(page)
    assert page.evaluate('document.getElementById("agentWindow").scrollWidth '
                         '<= innerWidth + 1')
    assert_agent_surface_has_no_human_wait_wording(page)


# ---------------------------------------------------------------- 角色卡
def test_agent_card_shows_progress_and_warn(ui):
    page, ui_api = ui
    stalled = progress(no_progress={'state': 'warn', 'silence_s': 780, 'since_ts': 1000.0,
                                    'reason': '超过阈值无新事件', 'threshold_s': 600})
    ui_api['views']['A']['agents'] = [{
        'role': 'analyst', 'name': 'simenv-analyst', 'nodes': ['N3'], 'active_node': 'N3',
        'status': 'working', 'last_action': 'model_call(started)', 'elapsed_s': 780,
        'summary': '已生成摘要', 'mode': 'drill', 'evidence': [],
        'capabilities': {'implemented': True, 'dependencies_ready': None,
                         'execution': 'standin', 'verification_scope': None},
        'progress': stalled,
    }]
    select(page, 'A')
    page.locator('#segRun').click()
    tick(page)
    card = page.locator('#agents .agent').first
    pw.expect(card).to_contain_text('无进展')
    pw.expect(card).to_contain_text('13 分钟')
    assert_agent_surface_has_no_human_wait_wording(page)
