"""Browser layout acceptance using controlled responses, without simulation assets."""
import os
from pathlib import Path
from urllib.parse import urljoin

import pytest

from test_run_sessions import ui, static_url, select, release, pw  # noqa: F401
from test_agent_window import agent_view

# WEB_UI_SPEC §14「桌面布局」/ A10 的验收视口（宽×高）。高度是关键变量：
# 侧栏是 sticky 视口高容器，短视口下内容会溢出。
ACCEPTANCE_VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]
RAIL_ENTRIES = ('aside .rail-entry, aside #btnNew, aside #viewSeg button, '
                'aside .action-item, aside .run-item, aside .rail-foot')


def capture(page, name):
    root = os.environ.get('LOOP_VISUAL_ARTIFACTS')
    if root:
        target = Path(root)
        target.mkdir(parents=True, exist_ok=True)
        page.evaluate('scrollTo(0, 0)')
        page.screenshot(path=str(target / (name + '.png')), full_page=not name.endswith('-agent'))


def assert_fits(page, selector):
    """Keep real controls and evidence within their containers and viewport."""
    issues = page.locator(selector).evaluate_all('''elements => elements.flatMap(el => {
        if (!el.getClientRects().length) return [];
        const box = el.getBoundingClientRect();
        const parent = el.closest('.card, .agent-window, .step-card') || el.parentElement;
        const bounds = parent.getBoundingClientRect();
        return box.width > 0 && (box.left < -1 || box.right > innerWidth + 1 ||
            box.left < bounds.left - 1 || box.right > bounds.right + 1)
            ? [el.id || el.className] : [];
    })''')
    assert not issues, issues
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def assert_reachable(page, selector):
    """A10：侧栏入口必须「滚达得到」。sticky 视口高容器让页面滚动无法把它们带回视口，
    因此这里按用户真实手段（滚动最近的可滚动祖先）判定，而不是只看横向是否溢出。
    失败信息带实测包围盒与视口高，便于区分「布局缺陷」与「环境缺件」。"""
    issues = page.locator(selector).evaluate_all('''elements => elements.flatMap(el => {
        if (!el.getClientRects().length) return [];
        el.scrollIntoView({block: 'nearest', inline: 'nearest'});
        const box = el.getBoundingClientRect();
        const inside = box.top >= -1 && box.bottom <= innerHeight + 1 &&
            box.left >= -1 && box.right <= innerWidth + 1;
        return inside ? [] : [(el.id || el.className) + ' top=' + Math.round(box.top) +
            ' bottom=' + Math.round(box.bottom) + ' 视口高=' + innerHeight];
    })''')
    assert not issues, issues


def populate(api):
    v = api['views']['A']
    v.update(project='/simulation/projects/TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES',
             current_node='N4', baseline='v1.2-stable',
             node_history=[{'node': 'N' + str(n), 'status': 'done'} for n in range(4)],
             counts={'koutou1': {'value': 3, 'zero': False, 'label': '口径一 · 未收敛项'},
                     'koutou2': {'value': 1, 'zero': False, 'label': '口径二 · 用例状态'}},
             blockers=[{'severity': 'blocker', 'code': 'REVIEW_PENDING',
                        'message': '接口差异仍有未决条目，请先核对证据。'}],
             agents=[{'role': role, 'nodes': nodes,
                      'capabilities': {'implemented': True, 'dependencies_ready': None,
                                       'execution': 'not_started', 'verification_scope': None},
                      'status': 'done' if role == 'analyst' else 'idle',
                      'last_action': 'node_finished(ok)' if role == 'analyst' else '等待上游步骤',
                      'summary': '已生成接口变更摘要，等待人工复核。' if role == 'analyst' else None,
                      'mode': 'standin', 'elapsed_s': 12 if role == 'analyst' else None}
                     for role, nodes in [('analyst', ['N3']), ('author', ['N6']),
                                         ('checker', ['N8', 'N10']), ('guardian', ['N11']),
                                         ('reporter', ['N12'])]])
    v['pending_interrupt']['payload'].update(difference_items={
        'present': True, 'entries': [
            {'entry_id': 'D-001', 'kind': 'interface', 'change': 'modified',
             'segment': 'dma_controller.sv', 'lines': [128, 129],
             'unresolved': '新增端口位宽需要人工核对',
             'evidence': 'input [15:0] transfer_length → input [31:0] transfer_length'},
            {'entry_id': 'D-002', 'kind': 'register', 'change': 'added',
             'evidence': '新增状态寄存器，需补充边界激励。'}]}, unresolved_entries=['D-001'])


@pytest.mark.parametrize('width', [1280, 1440, 1920])
def test_workspace_views_and_agent_controls_fit_browser(ui, width):
    page, api = ui
    page.set_viewport_size({'width': width, 'height': 1000})
    populate(api)
    for field, value in [('s0Baseline', '/simulation/TCS9620/baseline-v1.2'),
                         ('s0Version', 'v1.2-stable'), ('s0Rtl', '/projects/TCS9620/rtl'),
                         ('s0Work', '/simulation/TCS9620/work-v1.3')]:
        page.locator('#' + field).fill(value)
    assert_fits(page, '#viewS0 .input, #viewS0 .btn, #viewSeg button')
    capture(page, f'{width}-environment')
    page.locator('#s0Work').fill('/simulation/projects/' + 'long-project-path/' * 8)
    assert_fits(page, '#s0Work')
    page.route('**/api/baselines', lambda route: route.fulfill(json={'baselines': [
        {'id': 'v1.2-stable', 'valid': True, 'cases': 162, 'parent': 'v1.1'},
        {'id': 'v1.1', 'valid': True, 'cases': 150}]}))
    page.route('**/api/env/check?**', lambda route: route.fulfill(json={
        'ok': True, 'matches_current_process': True, 'path': '/fixture', 'registered': True,
        'env_id': 'TCS9620', 'plugin_missing': [], 'workspace_missing': [],
        'counts': {'rtl_files': 1210, 'cases': 162}}))
    page.locator('#segSetup').click()
    page.locator('#btnRefreshBaselines').click()
    pw.expect(page.locator('#setupBaseline')).to_have_value('v1.2-stable')
    page.locator('#setupCheck').click()
    pw.expect(page.locator('#btnStart')).to_be_enabled()
    assert_fits(page, '#viewSetup .input, #viewSetup .btn')
    page.locator('#btnBaselineBrowse').click()
    pw.expect(page.locator('#dirPicker')).to_be_visible()
    assert_fits(page, '#dirPicker .btn')
    capture(page, f'{width}-configuration')
    page.locator('#btnDirClose').click()
    select(page, 'A')
    pw.expect(page.locator('#gateMaterial')).to_contain_text('transfer_length')
    assert_fits(page, '#viewGate .input, #viewGate .btn, #viewGate .diff-item')
    capture(page, f'{width}-gate')
    page.locator('#segRun').click()
    assert_fits(page, '#viewRun .agent, #viewRun .stage, #viewRun .btn')
    capture(page, f'{width}-monitor')
    page.route('**/api/runs/*/agents/**', lambda route: route.fulfill(json=agent_view()))
    page.locator('#agents [data-agent-node="N3"]').click()
    pw.expect(page.locator('#awSteer')).to_be_enabled()
    page.locator('#awMessage').fill('请核对新增端口位宽，并保留现有激励时序。')
    assert_fits(page, '#agentWindow .input, #agentWindow .btn')
    capture(page, f'{width}-agent')
    page.keyboard.press('Escape')
    assert not api['posts']


def test_async_loading_empty_and_error_states_remain_readable(ui):
    page, api = ui
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.locator('#segRun').click()
    pw.expect(page.locator('#runEmpty')).to_be_visible()
    capture(page, '1440-empty')
    api['hold'] = lambda path: path == '/api/runs/A'
    select(page, 'A')
    pw.expect(page.locator('#runHead')).to_contain_text('加载')
    capture(page, '1440-loading')
    page.wait_for_timeout(80)
    release(page, api, {'detail': {'error': '证据读取失败：' + '/simulation/long-project/' * 12}}, 503)
    pw.expect(page.locator('#runAlerts')).to_contain_text('证据读取失败')
    assert_fits(page, '#runAlerts .alert')
    capture(page, '1440-error')
    api['hold'] = None
    while api['pending']:
        api['pending'].pop().fulfill(json=api['views']['A'])
    assert not api['posts']


def test_sidebar_keyboard_navigation_and_skip_link_keep_focus(ui):
    page, api = ui
    page.locator('#segS0').focus()
    page.keyboard.press('ArrowDown')
    pw.expect(page.locator('#segSetup')).to_be_focused()
    pw.expect(page.locator('#viewSetup')).to_be_visible()
    pw.expect(page.locator('#segSetup')).to_have_attribute('aria-selected', 'true')
    pw.expect(page.locator('#segS0')).to_have_attribute('tabindex', '-1')
    page.keyboard.press('End')
    pw.expect(page.locator('#viewGate')).to_be_visible()
    page.keyboard.press('Home')
    pw.expect(page.locator('#viewS0')).to_be_visible()
    page.locator('.skip-link').focus()
    page.keyboard.press('Enter')
    pw.expect(page.locator('#workspace')).to_be_focused()
    assert not api['posts']


@pytest.mark.parametrize('width,height', ACCEPTANCE_VIEWPORTS)
def test_sidebar_entries_are_reachable_at_acceptance_viewports(ui, width, height):
    """A10：验收视口下侧栏每个入口都要可滚达且可点击。

    回归的是实测缺陷（2026-10-26）：`aside` 是 `position:sticky; height:calc(100vh-72px)`
    的视口高容器、内容却按内容撑高，`overflow` 为 `visible` ⇒ 短视口下「最近运行」条目被画在
    盒外，页面滚动因 sticky 无效，`scrollIntoView` 一分不动，条目永久不可点击。
    """
    page, api = ui
    page.set_viewport_size({'width': width, 'height': height})
    populate(api)
    pw.expect(page.locator('#actionBar .action-item')).to_have_count(2)
    pw.expect(page.locator('#runList .run-item')).to_have_count(2)
    assert_reachable(page, RAIL_ENTRIES)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(page, f'{width}x{height}-sidebar')
    # 可达 ⇒ 真能操作：点击运行 A（`populate` 填充的就是 A），闸门材料随之出现
    page.locator('#runList .run-item').first.click()
    pw.expect(page.locator('#gateMaterial')).to_contain_text('transfer_length')
    assert not api['posts']


@pytest.mark.parametrize('width', [1280, 1440, 1920])
def test_compatibility_console_has_return_path_and_fits_browser(ui, width):
    page, _ = ui
    page.set_viewport_size({'width': width, 'height': 1000})
    page.route('**/api/runs/*/events**', lambda route: route.fulfill(json={'events': [], 'last_seq': 0}))
    # 前端把当前视图同步进 URL（`#view=s0`），直接拼 `page.url + 'legacy.html'` 会把文件名
    # 拼到 hash 后面变成同页跳转（实测 2026-10-26）。按相对 URL 解析才是用户点链接的语义。
    page.goto(urljoin(page.url, 'legacy.html'))
    pw.expect(page.locator('.back-workspace')).to_be_visible()
    assert_fits(page, 'input, select, textarea, .btn')
    capture(page, f'{width}-legacy')
    page.locator('.back-workspace').click()
    pw.expect(page.locator('#viewS0')).to_be_visible()


def test_agent_cards_show_server_capability_facts(ui):
    """F02：能力四维由服务端下发，卡片如实显示；idle 不得再被说成「未实现」。"""
    page, api = ui
    populate(api)
    select(page, 'A')
    cards = page.locator('.agent')
    pw.expect(cards).to_have_count(5)
    texts = ' '.join(cards.all_inner_texts())
    assert '能力 实现 已实现' in texts
    assert '未实现' not in texts
    # idle 的 guardian 卡也带能力事实（未知维度显示「未知」，不猜）
    guardian = cards.filter(has_text='simenv-guardian')
    pw.expect(guardian).to_have_count(1)
    guardian_text = guardian.inner_text()
    assert '本次 未开始' in guardian_text
    assert '依赖 未知' in guardian_text
