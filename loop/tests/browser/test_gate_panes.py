"""A11：闸门视图「材料 / 操作」双栏独立滚动（WEB_UI_SPEC §5 / §10 A11 / §14）。

受控替身（与 `test_run_sessions.py` 共用 `ui` fixture）：不模拟真实闸门证据，
只证明展示层的可观察行为——两栏各自滚动、互不带动、高度是上限、跨轮询重绘保持、
身份变化回顶、溢出时键盘可达、单列断点不启用局部滚动、页面无水平溢出。

视觉证据（非通过判据）：`LOOP_VISUAL_ARTIFACTS=<dir>` 时把三种视口的闸门视图截图落盘。
"""
import os
from pathlib import Path

import pytest

from test_run_sessions import ui, static_url, select, pw, tick, GATE  # noqa: F401

# 可判定口径（§14「闸门双栏局部滚动」）：上限 = clamp(300, 100dvh - 340, 720)
PANE_MAX_H_OFFSET = 340
PANE_MAX_H_MIN = 300
PANE_MAX_H_MAX = 720
ACCEPTANCE_VIEWPORTS = [(1280, 720), (1440, 900), (1920, 1080)]


def capture(page, name):
    """截图只是视觉检查件，不作通过判据（同 test_web_layout.py 的口径）。"""
    root = os.environ.get('LOOP_VISUAL_ARTIFACTS')
    if not root:
        return
    target = Path(root)
    target.mkdir(parents=True, exist_ok=True)
    # 把两栏那一排顶到视口上方合适位置（卡片头也要在画面里），再截图。
    page.evaluate('''() => {
        const row = document.querySelector('#viewGate .run-grid');
        if (row) window.scrollBy(0, row.getBoundingClientRect().top - 96);
    }''')
    page.wait_for_timeout(80)
    page.screenshot(path=str(target / (name + '.png')))


def pane_max_h(height):
    return min(max(PANE_MAX_H_MIN, height - PANE_MAX_H_OFFSET), PANE_MAX_H_MAX)


def long_entries(count=12):
    """长材料：12 条差异（每条带 evidence/行号），足以让材料栏真实溢出。"""
    return [{
        'entry_id': 'D-%03d' % i,
        'kind': 'interface',
        'change': 'modified',
        'segment': 'dma_controller_%02d.sv' % i,
        'lines': [100 + i, 101 + i],
        'unresolved': '新增端口位宽需要人工核对（第 %d 条）' % i,
        'evidence': 'input [15:0] transfer_length_%d → input [31:0] transfer_length_%d' % (i, i),
    } for i in range(1, count + 1)]


def populate_long_gate(api, count=12):
    """长材料 + 长操作：G1 逐条处置 12 条 ⇒ 操作栏也有 12 组控件。"""
    view = api['views']['A']
    view['pending_interrupt']['payload'].update({
        'gate_node': 'N4',
        'entry_decisions_required': True,
        'difference_items': {'present': True, 'mode': 'real', 'entries': long_entries(count)},
        'unresolved_entries': ['D-001'],
    })
    view['gate_options'][GATE] = [
        {'value': 'confirmed', 'label': '服务端确认'},
        {'value': 'ignored', 'label': '服务端忽略'},
        {'value': 'disputed', 'label': '服务端争议'},
    ]


def open_long_gate(page, api):
    populate_long_gate(api)
    select(page, 'A')
    pw.expect(page.locator('#viewGate')).to_be_visible()
    pw.expect(page.locator('#gateMaterial .diff-item')).to_have_count(12)
    pw.expect(page.locator('#gatePanel .gate-entry')).to_have_count(12)


def metrics(page, selector):
    return page.locator(selector).evaluate('''el => {
        const s = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {overflowY: s.overflowY, overflowX: s.overflowX, maxHeight: s.maxHeight,
                gutter: s.scrollbarGutter || null,
                top: Math.round(el.scrollTop), scrollHeight: el.scrollHeight,
                clientHeight: el.clientHeight, width: Math.round(r.width),
                tabindex: el.getAttribute('tabindex'), role: el.getAttribute('role'),
                label: el.getAttribute('aria-label'),
                overscrollY: s.overscrollBehaviorY,
                capToken: s.getPropertyValue('--gate-pane-max-h').trim(),
                pageY: Math.round(window.scrollY)};
    }''')


def bring_into_view(page, selector):
    page.locator(selector).scroll_into_view_if_needed()
    page.wait_for_timeout(60)
    box = page.locator(selector).bounding_box()
    return box


def wheel_over(page, selector, dy):
    """按用户真实手段滚动：把指针放在栏内再滚轮。"""
    box = page.locator(selector).bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + min(box['height'] / 2, 120))
    page.mouse.wheel(0, dy)
    page.wait_for_timeout(150)


@pytest.mark.parametrize('width,height', ACCEPTANCE_VIEWPORTS)
def test_panes_are_independent_scroll_containers_with_viewport_cap(ui, width, height):
    """B1：双栏下两栏都是局部滚动容器，高度受同一上限约束，卡片头不参与滚动。"""
    page, api = ui
    page.set_viewport_size({'width': width, 'height': height})
    open_long_gate(page, api)
    assert page.locator('.gate-pane').count() == 2
    for selector in ('#gateMaterial', '#gatePanel'):
        m = metrics(page, selector)
        assert m['overflowY'] == 'auto', (selector, m)
        assert m['overflowX'] == 'auto', (selector, m)
        # 横向溢出留在本栏内，不撑出页面水平滚动；滚到栏底不把整页顶走
        assert m['overscrollY'] == 'contain', (selector, m)
        # 上限是**一个** token（§5 第 2 条 / A11）：token 必须存在且解析值等于推导值
        assert m['capToken'], (selector, m)
        assert 'clamp' in m['capToken'], (selector, m)
        assert m['maxHeight'] == f'{pane_max_h(height)}px', (selector, m)
        # 并排对照不跳宽：两栏都预留滚动条槽位
        assert m['gutter'] == 'stable', (selector, m)
        assert m['clientHeight'] <= pane_max_h(height), (selector, m)
        # B2：长材料/长操作下两栏都真的溢出（否则后面「独立滚动」无意义）
        assert m['scrollHeight'] > m['clientHeight'] + 1, (selector, m)
        # 卡片头在滚动容器之外（结构判据），滚动时不动
        head = page.locator(selector).evaluate('el => el.previousElementSibling.className')
        assert 'card-head' in head, (selector, head)
    # 两栏高度上限一致（并排对照时同一把尺）
    heights = {name: metrics(page, sel)['maxHeight'] for name, sel in
               (('material', '#gateMaterial'), ('panel', '#gatePanel'))}
    assert len(set(heights.values())) == 1, heights
    # 页面仍无水平溢出（§14 桌面布局）
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    capture(page, f'gate-panes-{width}x{height}')


def test_scrolling_one_pane_moves_neither_the_other_nor_the_page(ui):
    """B3：滚材料栏 ⇒ 操作栏与页面不动；反之亦然。"""
    page, api = ui
    page.set_viewport_size({'width': 1440, 'height': 900})
    open_long_gate(page, api)
    bring_into_view(page, '#gateMaterial')
    page_before = metrics(page, '#gateMaterial')['pageY']
    wheel_over(page, '#gateMaterial', 400)
    material = metrics(page, '#gateMaterial')
    panel = metrics(page, '#gatePanel')
    assert material['top'] > 0, material
    assert panel['top'] == 0, panel
    assert material['pageY'] == page_before, (page_before, material)

    wheel_over(page, '#gatePanel', 400)
    assert metrics(page, '#gatePanel')['top'] > 0
    assert metrics(page, '#gateMaterial')['top'] == material['top']
    capture(page, 'gate-panes-1440x900-both-scrolled')
    # 滚到栏底后继续滚，不应把页面顶走（overscroll-behavior: contain）；capture 会滚页面，重取基准
    page_before = metrics(page, '#gateMaterial')['pageY']
    wheel_over(page, '#gateMaterial', 4000)
    assert metrics(page, '#gateMaterial')['pageY'] == page_before


def test_scroll_position_survives_polling_rerender(ui):
    """B4：1.5 s 全量重绘必须保持滚动位置（否则每轮被滚回顶部，功能不成立）。"""
    page, api = ui
    page.set_viewport_size({'width': 1440, 'height': 900})
    open_long_gate(page, api)
    bring_into_view(page, '#gateMaterial')
    page.evaluate('''() => {
        window.__paneMut = 0;
        new MutationObserver(records => { window.__paneMut += records.length; })
            .observe(document.getElementById('gateMaterial'), {childList: true});
    }''')
    wheel_over(page, '#gateMaterial', 300)
    top = metrics(page, '#gateMaterial')['top']
    assert top > 0
    tick(page)   # 一次真实轮询：renderLive 会 clearEl 重建材料栏
    tick(page)   # 再来一次，防「只保住第一次」
    assert page.evaluate('window.__paneMut') > 0, '材料栏没有被重绘，本用例证明不了「跨重绘保持」'
    assert metrics(page, '#gateMaterial')['top'] == top, metrics(page, '#gateMaterial')
    assert api['posts'] == []


def test_identity_change_resets_scroll_to_top(ui):
    """B5：身份 = run + gate + cycle。同身份重绘保持；身份变化回顶、不复用旧位置。

    **主判据用「切轮次」而不是「切运行」**（本轮独立复核 M4 变异发现的口径缺口）：切运行会经过
    一次"加载中/空态"重绘，那一次重绘本来就把 `mem.top` 归零，于是把身份接线写死成常量也能绿；
    切轮次走的是同一条 1.5 s 轮询重绘、内容始终是 12 条，只有身份判据能把它归零。
    """
    page, api = ui
    page.set_viewport_size({'width': 1440, 'height': 900})
    open_long_gate(page, api)
    bring_into_view(page, '#gateMaterial')
    wheel_over(page, '#gateMaterial', 300)
    top = metrics(page, '#gateMaterial')['top']
    assert top > 0
    # ① 同身份再轮询 ⇒ 保持（排除"任何重绘都回顶"的假绿）
    tick(page)
    assert metrics(page, '#gateMaterial')['top'] == top
    # ② 轮次 0→1（身份变化，内容不变）⇒ 回顶
    api['views']['A']['pending_interrupt']['payload']['cycle'] = 1
    tick(page)
    assert page.locator('#gateMaterial .diff-item').count() == 12
    assert metrics(page, '#gateMaterial')['top'] == 0, '轮次变化没有回顶：身份判据未接线'
    # ③ 轮次再变回 0（又一次身份变化）⇒ 仍回顶，不复用 ① 的位置
    api['views']['A']['pending_interrupt']['payload']['cycle'] = 0
    tick(page)
    assert metrics(page, '#gateMaterial')['top'] == 0
    # ④ 切运行同样回顶
    wheel_over(page, '#gateMaterial', 300)
    assert metrics(page, '#gateMaterial')['top'] > 0
    select(page, 'B')
    page.wait_for_timeout(120)
    assert metrics(page, '#gateMaterial')['top'] == 0


def test_overflowing_panes_are_keyboard_reachable_and_short_ones_are_not(ui):
    """B6：溢出 ⇒ region + aria-label + tabindex=0 且 PageDown 可滚；不溢出 ⇒ 不留 Tab 停靠点。"""
    page, api = ui
    page.set_viewport_size({'width': 1440, 'height': 900})
    open_long_gate(page, api)
    for selector, label in (('#gateMaterial', '闸门材料'), ('#gatePanel', '闸门操作')):
        m = metrics(page, selector)
        assert m['role'] == 'region', (selector, m)
        assert m['label'] == label, (selector, m)
        assert m['tabindex'] == '0', (selector, m)
    page.locator('#gateMaterial').focus()
    assert page.evaluate('document.activeElement.id') == 'gateMaterial'
    before = metrics(page, '#gateMaterial')['top']
    page.keyboard.press('PageDown')
    page.wait_for_timeout(120)
    assert metrics(page, '#gateMaterial')['top'] > before

    # 没有待决策闸门 ⇒ 材料栏内容很短：不溢出就不该有 Tab 停靠点
    api['views']['B']['pending_interrupt'] = None
    select(page, 'B')
    page.locator('#segGate').click()
    pw.expect(page.locator('#viewGate')).to_be_visible()
    page.wait_for_timeout(120)
    short = metrics(page, '#gateMaterial')
    assert short['scrollHeight'] <= short['clientHeight'] + 1, short
    assert short['tabindex'] is None, short
    assert short['role'] == 'region', short


def test_single_column_breakpoint_does_not_nest_scrolling(ui):
    """B7：≤1100px 单列断点回到页面自然流（嵌套滚动会和页面滚动抢手势）。"""
    page, api = ui
    page.set_viewport_size({'width': 1000, 'height': 900})
    open_long_gate(page, api)
    for selector in ('#gateMaterial', '#gatePanel'):
        m = metrics(page, selector)
        assert m['maxHeight'] == 'none', (selector, m)
        assert m['overflowY'] == 'visible', (selector, m)
        assert m['tabindex'] is None, (selector, m)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    # 仍然可读：内容不被裁掉（页面自然滚到底能看到最后一条）
    assert page.evaluate('''() => {
        const last = document.querySelectorAll('#gateMaterial .diff-item');
        return last.length > 0 && last[last.length - 1].getBoundingClientRect().height > 0;
    }''')
