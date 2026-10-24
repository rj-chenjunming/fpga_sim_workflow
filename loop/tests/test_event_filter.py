"""U5（SPEC-REV-07）：事件流客户端过滤的纯函数受控断言（node 驱动）。

`web/event-filter.js` 只做筛选判定：kind 集合推导、勾选切换、过滤应用。
纯客户端过滤，清除过滤即还原全量（F11 的服务端分页结论不变）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "event-filter.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const F = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def _events():
    return [
        {"seq": 1, "kind": "run_started", "node": None},
        {"seq": 2, "kind": "node_started", "node": "N0"},
        {"seq": 3, "kind": "node_finished", "node": "N0"},
        {"seq": 4, "kind": "node_started", "node": "N3"},
        {"seq": 5, "kind": "gate_decided", "node": "N4"},
    ]


def test_kinds_of_unique_in_first_seen_order():
    assert _eval("F.kindsOf(" + json.dumps(_events()) + ")") == [
        "run_started", "node_started", "node_finished", "gate_decided"
    ]


def test_kinds_of_empty():
    assert _eval("F.kindsOf([])") == []
    assert _eval("F.kindsOf(null)") == []


def test_toggle_from_null_selects_single_kind():
    assert _eval("F.toggleKind(null, 'node_started')") == ["node_started"]


def test_toggle_adds_then_removes_back_to_null():
    out = _eval(
        "(function(){let a=F.toggleKind(null,'node_started');"
        "a=F.toggleKind(a,'gate_decided');"
        "const both=a.slice();"
        "a=F.toggleKind(a,'node_started');"
        "const after=a; a=F.toggleKind(a,'gate_decided');"
        "return [both,after,a];})()"
    )
    assert out == [["node_started", "gate_decided"], ["gate_decided"], None]


def test_apply_filter_null_returns_all():
    events = _events()
    assert _eval(f"F.applyFilter({json.dumps(events)}, null).length") == len(events)


def test_apply_filter_subset_only_matching_kinds():
    out = _eval(
        f"F.applyFilter({json.dumps(_events())}, ['node_started','gate_decided'])"
    )
    assert [e["seq"] for e in out] == [2, 4, 5]


def test_apply_filter_preserves_order_and_identity():
    """过滤不复制、不改写事件对象，只筛选引用（上游渲染契约不变）。"""
    out = _eval(
        "(function(){const ev=" + json.dumps(_events()) + ";"
        "const filtered=F.applyFilter(ev,['run_started']);"
        "return [filtered.length, filtered[0] === ev[0]];})()"
    )
    assert out == [1, True]
