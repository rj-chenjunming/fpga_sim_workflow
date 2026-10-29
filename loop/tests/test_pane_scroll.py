"""A11：闸门双栏独立滚动的判定纯函数（node 驱动，形态同 `test_gate_session.py`）。

`web/pane-scroll.js` 只做判定：滚动身份、重绘后应恢复的 `scrollTop`、是否该给 Tab 停靠点。
`app.js` 仍是唯一重绘 owner（持有 DOM、包渲染、设 `scrollTop`）；浏览器行为另见
`tests/browser/test_gate_panes.py`。本文件不证明浏览器交互，只证明判定口径。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "pane-scroll.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const P = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


IDENT = "P.identity('RUN-A', 'G1_diff_confirm', 0)"


def test_identity_covers_run_gate_and_cycle():
    """身份 = run_id + 闸门 + 轮次（WEB_UI_SPEC §5 第 3 条）：三者任一变化都必须是新身份。"""
    base = _eval(IDENT)
    assert _eval(IDENT) == base
    assert _eval("P.identity('RUN-B', 'G1_diff_confirm', 0)") != base
    assert _eval("P.identity('RUN-A', 'G2_report_signoff', 0)") != base
    assert _eval("P.identity('RUN-A', 'G1_diff_confirm', 1)") != base
    # 轮次 0 与 null（未开始）不得混为同一身份，否则会套用上一轮/无轮次的位置
    assert _eval(IDENT) != _eval("P.identity('RUN-A', 'G1_diff_confirm', null)")


def test_restore_keeps_position_only_for_same_identity():
    got = _eval("(function(){var k=" + IDENT + ";return P.restore({identity:k, top:240}, k);})()")
    assert got == 240
    other = _eval("(function(){var k1=" + IDENT + ";"
                  "var k2=P.identity('RUN-B','G1_diff_confirm',0);"
                  "return P.restore({identity:k1, top:240}, k2);})()")
    assert other == 0


def test_restore_is_defensive_about_missing_and_bad_values():
    """没有保存值 / 身份缺失 / 脏输入一律回顶，不抛异常、不返回 NaN。"""
    cases = [
        ("P.restore(null, " + IDENT + ")", 0),
        ("P.restore({identity:null, top:120}, " + IDENT + ")", 0),
        ("P.restore({identity:" + IDENT + ", top:null}, " + IDENT + ")", 0),
        ("P.restore({identity:" + IDENT + ", top:-30}, " + IDENT + ")", 0),
        ("P.restore({identity:" + IDENT + ", top:'abc'}, " + IDENT + ")", 0),
        ("P.restore({identity:" + IDENT + ", top:12.7}, " + IDENT + ")", 12),
        ("P.restore({identity:" + IDENT + ", top:9e9}, " + IDENT + ") > 0", True),
    ]
    for expr, expected in cases:
        assert _eval(expr) == expected, expr


def test_restore_does_not_mutate_input():
    expr = ("(function(){var k=" + IDENT + ";var saved={identity:k, top:88};"
            "P.restore(saved, k);return saved;})()")
    assert _eval(expr) == {"identity": _eval(IDENT), "top": 88}


def test_tab_stop_only_when_really_overflowing():
    """实际溢出才给 Tab 停靠点（§5 第 4 条）：+1 容差吸收亚像素/边框取整。"""
    assert _eval("P.isScrollable(600, 380)") is True
    assert _eval("P.isScrollable(380, 380)") is False
    assert _eval("P.isScrollable(381, 380)") is False
    assert _eval("P.isScrollable(382, 380)") is True
    assert _eval("P.isScrollable(NaN, 380)") is False
    assert _eval("P.isScrollable(600, null)") is False


def test_frontend_has_exactly_one_judging_module():
    """红线 8（口径唯一）的结构守卫：判定只在 `pane-scroll.js`，`app.js` 只转调不重算。

    对照 `test_gate_session.py::test_frontend_consumes_single_gate_session_module`（闸门会话）
    与 `test_capability_format.py::test_frontend_has_one_formatter_and_both_consumers_use_it`
    （能力格式化）的同类断言。本用例刻意不读运行结果、只读源码结构：
    失去它时，在 `app.js` 里另写一份 `scrollHeight > clientHeight` 判定不会有任何用例变红
    （本轮独立复核 M12 变异即绿）。
    """
    app = (WEB / "app.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "window.PaneScroll.identity" in app, "app.js 必须用 pane-scroll.js 的身份判据"
    assert "window.PaneScroll.restore" in app, "app.js 必须用 pane-scroll.js 的回填判据"
    assert "window.PaneScroll.isScrollable" in app, "app.js 必须用 pane-scroll.js 的溢出判据"
    # 不得自写第二套溢出比较（"是否溢出"只在本模块；`app.js` 里允许 `clientHeight > 0`
    # 这种"面板是否已布局"的可见性判断，那不是同一判据）
    assert "scrollHeight >" not in app, "app.js 不得自写溢出判据（应在 pane-scroll.js）"
    assert "clientHeight + 1" not in app, "app.js 不得自写溢出容差（应在 pane-scroll.js）"
    # 两栏身份都来自同一入口，且脚本顺序先于 app.js（同 gate-session 的口径）
    assert app.count("renderPanePreservingScroll(") == 3, "两栏应各一处调用 + 1 处定义"
    assert html.index('src="pane-scroll.js"') < html.index('src="app.js"')
    assert html.count('class="card-body gate-pane"') == 2
