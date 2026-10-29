"""S4-C 界面验收：运行摘要投影 / 无进展红字 / S3 接面三列 / 内嵌两态与降级。

契约：[SPEC-REV-16](../../../doc/spec/SPEC-REV-16-20261028.md) §2（投影字段）、§3（无进展与文案禁令）、
§6（可用性端点、降级、`explain` 接面）。本文件只用**受控桩数据**，不调真实模型、不读真实运行目录。

纪律（红线 8）：
- 所有判断值（`no_progress.state`、`silence_s`、`threshold_s`、`compaction.count`、指令三态、
  WM 可用性、经验采用/拒用）都**只来自服务端字段**；用例故意下发"自相矛盾"的桩数据
  （如 `state=warn` 但 `silence_s` 远小于 `threshold_s`）来证明前端**不重算**判据。
- 文本一律走 `textContent`：桩里放 HTML 片段，断言页面上没有对应元素。

结构：窗口新增 `#awSummary`（运行摘要）+ `#awNoProgress`（红字告警）+ `#awS3`（accepted/applied/
effective 三列 + WM/EXP）+ `#awEmbed`（实例执行结果：状态 + 会话事实 + 直连入口；**无 iframe**，见 SPEC-REV-17 §2）。
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
    """SPEC-REV-16 §6.2 稳定键：{available, reason, kind, facts, bytes, truncated}（无 content）。

    `facts` 形状 = `dsh_sdk.CompactionFacts`（§9-11：这是**解析事实**，不是会话原文）。
    SPEC-REV-17 §2-4 的"执行结果"块逐项渲染 count/records/errors/start→end/prune，不重算。
    """
    data = {'available': True, 'reason': None, 'kind': 'session_log_facts',
            'facts': {'availability': 'ok', 'count': 2,
                      'records': [{'kind': 'compaction', 'ts': 1.0},
                                  {'kind': 'compaction', 'ts': 2.0}],
                      'errors': [], 'start_count': 3, 'end_count': 5, 'prune_count': 1,
                      'reason': None, 'path': '/host/sessions/s.log',
                      # S8k（SPEC-REV-18）：人参与反馈次数与计数依据，同一份 facts 下发
                      'human_messages': 1,
                      'human_messages_basis': 'source.kind=user,dedupe=id|rpcId,skipped=0'},
            'bytes': 41, 'truncated': False, 'attempt': 2}
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


# ---------------------------------------------------------------- S8j 实例执行结果（无 iframe）
#: SPEC-REV-17 §2：窗口不再内嵌实例页面，改为「执行结果/状态 + 打开真实用例」。
#: `direct_url` 形状见 REV-16 §6.1：`http://<loopback>:<port>/?token=<受管 token>`。
DIRECT = 'http://127.0.0.1:43581/?token=T0KEN-managed'


def test_s8j_window_renders_no_embed_surface(ui):
    """§2-1：窗口**没有**内嵌面。

    判据与服务端下发什么无关：即便服务端仍写 `embed: "iframe"`，界面也不得渲染
    iframe/object/embed（内嵌面已取消，反代不透传 WebSocket，REV-16 §9-2）。
    """
    page, _ = setup(ui, inst=instance(direct_url=DIRECT))
    assert page.locator('#agentWindow iframe').count() == 0
    assert page.locator('#agentWindow object').count() == 0
    assert page.locator('#agentWindow embed').count() == 0
    assert page.locator('#awEmbedFrame').count() == 0
    assert page.locator('#awEmbedFallback').count() == 0


def test_s8j_ready_instance_shows_status_facts_and_direct_entry(ui):
    """§2-2/4/5：就绪态 = 状态 + 事实（数字逐字来自 `facts`）+ 直连入口（披露 token 与本机限制）。"""
    page, api = setup(ui, inst=instance(direct_url=DIRECT))
    pw.expect(page.locator('#awEmbedState')).to_have_text('实例就绪')
    facts = page.locator('#awEmbedFacts').inner_text()
    for piece in ('压缩成功 2 次', '记录 2 条', '错误 0 条', '起止 3→5', '剪枝 1 次',
                  '人参与 1 次', 'session_log_facts'):
        assert piece in facts, (piece, facts)
    pw.expect(page.locator('#awEmbedCopyNote')).to_contain_text('41 B')
    entry = page.locator('#awEmbedDirect')
    pw.expect(entry).to_be_visible()
    assert entry.get_attribute('href') == DIRECT
    title = entry.get_attribute('title')
    assert 'token' in title and '本机' in title, title
    pw.expect(page.locator('#awEmbedStream')).to_contain_text('WebSocket')
    pw.expect(page.locator('#awEmbedStream')).to_contain_text('§9-2')
    # §2-7：打开即读会话事实，不需要先点按钮
    assert api['copy_reads'] >= 1
    assert not api['posts']


def test_s8j_zero_is_real_value_and_missing_is_unknown(ui):
    """§2-4：`0` 是服务端真实值必须显示 0；缺字段显示「未知」，不得折算成 0（红线 8：不自己判）。"""
    page, _ = setup(ui, inst=instance(direct_url=DIRECT),
                    copy=session_copy(facts={'availability': 'ok', 'count': 0,
                                             'records': [], 'errors': [],
                                             'start_count': 0, 'end_count': 0}))
    pw.expect(page.locator('#awEmbedFacts')).to_contain_text('压缩成功 0 次')
    facts = page.locator('#awEmbedFacts').inner_text()
    assert '压缩成功 0 次' in facts, facts
    assert '记录 0 条' in facts and '错误 0 条' in facts, facts
    assert '起止 0→0' in facts, facts
    assert '剪枝 未知' in facts, facts     # prune_count 缺字段 ⇒ 未知
    assert '剪枝 0' not in facts, facts


def test_s8j_unavailable_instance_is_explicit_and_gives_no_fake_entry(ui):
    """§2-2/4/5：不可用必须给原因；无 `url`/`direct_url` ⇒ 入口隐藏（不给假链接）；不出现 0 假数。"""
    page, _ = setup(ui, inst=instance(available=False, state='unavailable',
                                      reason='target_missing', url=None, direct_url=None),
                    copy=session_copy(available=False, reason='session_log_missing',
                                      kind=None, facts=None, bytes=None))
    pw.expect(page.locator('#awEmbedState')).to_have_text('不可用')
    reason = page.locator('#awEmbedReason').inner_text()
    assert '目标实例缺失' in reason and 'target_missing' in reason, reason
    facts = page.locator('#awEmbedFacts').inner_text()
    assert '不可用' in facts and '元数据未声明会话日志' in facts, facts
    assert '0 条' not in facts and '0 次' not in facts, facts
    pw.expect(page.locator('#awEmbedDirect')).to_be_hidden()
    assert_agent_surface_has_no_human_wait_wording(page)


def test_s8j_entry_falls_back_to_proxy_url_and_discloses_gap(ui):
    """§2-5：旧服务端没有 `direct_url` ⇒ 回退反代 `url`，并在 `title` 里披露实时流未接通。"""
    page, _ = setup(ui, inst=instance())
    entry = page.locator('#awEmbedDirect')
    pw.expect(entry).to_be_visible()
    assert entry.get_attribute('href').endswith('/instance/A/N3/2/')
    assert '反代' in entry.get_attribute('title')


def test_s8j_no_embedding_probe_request(ui):
    """§2-6：内嵌面取消 ⇒ 探测无消费者：窗口不得再向上游页面要 `Accept: application/json`。"""
    page, api = setup(ui, inst=instance(direct_url=DIRECT))
    pw.expect(page.locator('#awEmbedState')).to_have_text('实例就绪')
    assert api['proxy_reads'] == 0, api['proxy_reads']


def test_s8j_stream_note_absent_when_server_omits_field(ui):
    """§2-3：服务端不下发 `stream` ⇒ 该行空白（不自己推断"有实时流"）。"""
    payload = instance(direct_url=DIRECT)
    payload.pop('stream')
    page, _ = setup(ui, inst=payload)
    pw.expect(page.locator('#awEmbedStream')).to_have_text('')


def test_s8j_refresh_button_rereads_facts_and_unfolds_raw_block(ui):
    """§2-8：首屏不铺原始 JSON；点「刷新执行结果」重读并展开解析事实（`textContent`，非 HTML）。"""
    page, api = setup(ui, inst=instance(direct_url=DIRECT))
    body = page.locator('#awSessionCopyBody')
    pw.expect(body).to_be_hidden()
    reads = api['copy_reads']
    page.locator('#awSessionCopy').click()
    pw.expect(body).to_contain_text('session_log_facts')
    pw.expect(body).to_contain_text('非会话原文')
    pw.expect(body).to_contain_text('"prune_count": 1')
    assert api['copy_reads'] > reads


def test_s8j_missing_kind_never_claims_content(ui):
    """§2-4/8：缺 `kind` ⇒ 事实类型未知：不给数字结论，原始块保持隐藏。"""
    page, _ = setup(ui, inst=instance(direct_url=DIRECT),
                    copy={'available': True, 'reason': None, 'kind': None,
                          'facts': {'count': 1}, 'bytes': 12, 'truncated': False})
    page.locator('#awSessionCopy').click()
    pw.expect(page.locator('#awSessionCopyBody')).to_be_hidden()
    facts = page.locator('#awEmbedFacts').inner_text()
    assert 'kind' in facts and '压缩成功' not in facts, facts


def test_s8j_attempt_switch_rereads_both_endpoints_scoped_by_attempt(ui):
    """§2-7 + REV-16 §6.1：切换 attempt 后两个端点都重读，且**都带** `?attempt=`（不跨 attempt 借用）。"""
    page, api = setup(ui, inst=instance(direct_url=DIRECT))
    api['instance_by_attempt'] = {1: instance(available=False, state='unavailable',
                                             reason='target_missing', url=None,
                                             direct_url=None)}
    page.locator('#awAttempt').select_option('1')
    pw.expect(page.locator('#awEmbedState')).to_have_text('不可用')
    pw.expect(page.locator('#awEmbedDirect')).to_be_hidden()
    for path in ('/instance', '/session-copy'):
        urls = [u for u in api['requests'] if u.split('?')[0].endswith(path)]
        assert urls, path
        # 切换后**最新**一次读取必须按选中的 attempt 请求（首屏那次是 attempt=2，属正常）
        assert 'attempt=1' in urls[-1], (path, urls)
    page.locator('#awAttempt').select_option('')
    pw.expect(page.locator('#awEmbedState')).to_have_text('实例就绪')
    pw.expect(page.locator('#awEmbedDirect')).to_be_visible()


def test_s8k_human_feedback_count_is_rendered(ui):
    """S8k（SPEC-REV-18 §3）：执行结果行补「人参与 N 次」；数字与依据都来自服务端 `facts`。

    口径 = 会话日志里 `source.kind == "user"` 的消息条数（唯一判据在 `dsh_sdk`），界面只渲染。
    """
    page, _ = setup(ui, inst=instance(direct_url=DIRECT))
    facts = page.locator('#awEmbedFacts')
    pw.expect(facts).to_contain_text('人参与 1 次')
    text = facts.inner_text()
    assert '压缩成功 2 次' in text, text


def test_s8k_human_count_zero_is_a_real_value(ui):
    """`0` 是真实值（会话里没人说话）：必须显示 0，不得折成「未知」。"""
    page, _ = setup(ui, inst=instance(direct_url=DIRECT),
                    copy=session_copy(facts={'availability': 'ok', 'count': 0,
                                             'records': [], 'errors': [],
                                             'start_count': 0, 'end_count': 0,
                                             'prune_count': 0, 'human_messages': 0,
                                             'human_messages_basis':
                                                 'source.kind=user,dedupe=id|rpcId,skipped=0'}))
    pw.expect(page.locator('#awEmbedFacts')).to_contain_text('人参与 0 次')


def test_s8k_human_count_unknown_when_field_absent(ui):
    """旧服务端/旧记录没有 `human_messages` ⇒ 显示「未知」，不得补 0、不得猜。"""
    payload = session_copy()
    payload['facts'].pop('human_messages')
    payload['facts'].pop('human_messages_basis')
    page, _ = setup(ui, inst=instance(direct_url=DIRECT), copy=payload)
    pw.expect(page.locator('#awEmbedFacts')).to_contain_text('人参与 未知')
    text = page.locator('#awEmbedFacts').inner_text()
    assert '人参与 0' not in text, text


def test_s8j_missing_endpoint_is_explicit_not_blank(ui):
    """旧后端没有 `/instance` ⇒ 明确「不可用」+ 原因，不白屏、不假装就绪。"""
    page, _ = setup(ui, inst=None)
    pw.expect(page.locator('#awEmbedState')).to_have_text('不可用')
    pw.expect(page.locator('#awEmbedReason')).to_contain_text('原因')
    pw.expect(page.locator('#awEmbedDirect')).to_be_hidden()


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
