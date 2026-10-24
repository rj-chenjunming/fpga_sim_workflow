"""U8-b（SPEC-REV-08）：整门理由复用判定的纯函数受控断言（node 驱动）。

`gate-session.js` 增 `reusableReason(entryDecisions, derived, options)`：推导出的整门决策
需要理由且逐条处置里已有同判据非空理由时，给出可预填文本（entry_id 排序首个，确定性）。
判定口径仍只在 GateSession；app.js 只在整门理由为空时预填，不覆盖用户输入。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "gate-session.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const G = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)

OPTS = ("[{value:'confirmed'},{value:'ignored',requires_reason:true},"
        "{value:'disputed',requires_reason:true}]")


def test_returns_null_when_no_derived():
    assert _eval("G.reusableReason({}, null, " + OPTS + ")") is None


def test_returns_null_when_decision_needs_no_reason():
    assert _eval(
        "G.reusableReason({a:{decision:'ignored',reason:'r'}}, 'confirmed', " + OPTS + ")"
    ) is None


def test_returns_null_when_no_matching_entry_reason():
    assert _eval(
        "G.reusableReason({a:{decision:'confirmed',reason:'r'}}, 'ignored', " + OPTS + ")"
    ) is None
    assert _eval(
        "G.reusableReason({a:{decision:'ignored',reason:'  '}}, 'ignored', " + OPTS + ")"
    ) is None


def test_returns_first_sorted_matching_reason():
    assert _eval(
        "G.reusableReason({b:{decision:'ignored',reason:'第二条'},"
        "a:{decision:'ignored',reason:'第一条'}}, 'ignored', " + OPTS + ")"
    ) == "第一条"


def test_ignores_other_decisions_reasons():
    assert _eval(
        "G.reusableReason({a:{decision:'disputed',reason:'争议理由'},"
        "b:{decision:'ignored',reason:'忽略理由'}}, 'ignored', " + OPTS + ")"
    ) == "忽略理由"


def test_trims_reason():
    assert _eval(
        "G.reusableReason({a:{decision:'ignored',reason:'  带空格  '}}, 'ignored', " + OPTS + ")"
    ) == "带空格"


def test_tolerates_null_store_and_options():
    assert _eval("G.reusableReason(null, 'ignored', " + OPTS + ")") is None
    assert _eval("G.reusableReason({a:{decision:'ignored',reason:'r'}}, 'ignored', null)") is None
