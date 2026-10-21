"""F13 首次失败 / 刷新失败展示判据的受控断言（node 驱动纯函数）。

为什么用 node 而不是浏览器：本机缺 `playwright` Python 包（PyPI 不可达，系统有
`/usr/bin/google-chrome`），`tests/browser` 整组 skip。F13 的展示判据被提取成
`web/run-view-state.js` 的**纯函数**，因此可以在这里做真实执行断言，而不是只查源码字符串。

边界：本文件证明「判据函数对输入给出规定输出」，**不**证明真实浏览器 DOM 已渲染；
浏览器交互断言在 `tests/browser/test_run_sessions.py`（本机未运行，如实登记）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "run-view-state.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    """在 node 里加载 run-view-state.js 并求值表达式。"""
    script = (
        "const R = require(" + json.dumps(str(MODULE)) + ");\n"
        "const out = (" + expr + ");\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        [NODE, "-e", script], cwd=str(WEB.parent), capture_output=True, text=True, timeout=60
    )
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def _derive(**kwargs):
    return _eval("R.derive(" + json.dumps(kwargs) + ")")


def test_loading_state_says_loading_only():
    out = _derive(hasData=False, error=None, requesting=True, lastSuccessAt=None)
    assert out["kind"] == "loading"
    assert out["headStatusText"] == "加载中…"
    assert out["alertText"] == ""
    assert out["showRetry"] is False


def test_first_failure_does_not_claim_previous_success_or_loading():
    out = _derive(hasData=False, error="503 Service Unavailable", requesting=False, lastSuccessAt=None)
    assert out["kind"] == "first_error"
    assert out["headStatusText"] == "读取失败"
    assert "尚无成功读取的数据" in out["alertText"]
    assert "503 Service Unavailable" in out["alertText"]
    assert "加载中" not in out["alertText"]
    assert "最近一次成功" not in out["alertText"]
    assert "上次成功" not in out["alertText"]
    assert out["showRetry"] is True
    assert out["stale"] is False


def test_placeholder_idle_does_not_claim_loading():
    """无数据、无错误、无在途请求 ≠ 加载中（规格 §7.2 的「加载中」要求有在途请求）。"""
    out = _derive(hasData=False, error=None, requesting=False)
    assert out["kind"] == "idle"
    assert out["headStatusText"] == "尚未读取"


def test_loaded_state_has_no_alert_and_no_retry():
    out = _derive(hasData=True, error=None, requesting=False, lastSuccessAt=1700000000000)
    assert out["kind"] == "loaded"
    assert out["alertText"] == ""
    assert out["showRetry"] is False
    assert out["stale"] is False


def test_stale_refresh_failure_keeps_data_and_reports_last_success_time():
    ts = 1700000000000
    expected = datetime.fromtimestamp(ts / 1000).strftime("%H:%M:%S")
    out = _derive(hasData=True, error="timeout", requesting=False, lastSuccessAt=ts)
    assert out["kind"] == "stale_error"
    assert out["stale"] is True
    assert "数据已过期" in out["alertText"]
    assert "上次成功 " + expected in out["alertText"]
    assert "加载中" not in out["alertText"]
    assert out["showRetry"] is True
    # 有数据时顶栏仍由服务端 status 驱动，不由错误改写
    assert out["headStatusText"] == ""


def test_recovery_clears_alert_after_success():
    stale = _derive(hasData=True, error="timeout", requesting=False, lastSuccessAt=1700000000000)
    assert stale["kind"] == "stale_error" and stale["alertText"]
    recovered = _derive(hasData=True, error=None, requesting=False, lastSuccessAt=1700000005000)
    assert recovered["kind"] == "loaded"
    assert recovered["alertText"] == ""


def test_selection_reset_drops_previous_data_and_success_time():
    out = _eval("R.empty()")
    assert out == {"data": None, "error": None, "lastSuccessAt": None, "requesting": False}
    # 新选择即使旧运行有成功时间，也只能是「加载中」，不得显示上次成功
    derived = _derive(hasData=False, error=None, requesting=True, lastSuccessAt=None)
    assert derived["headStatusText"] == "加载中…"
    assert "上次成功" not in derived["alertText"]


def test_only_current_request_generation_may_write_state():
    a1 = {"runId": "A", "epoch": 1, "request": 1}
    b1 = {"runId": "B", "epoch": 2, "request": 2}
    a3 = {"runId": "A", "epoch": 3, "request": 3}
    assert _eval("R.isCurrent(" + json.dumps(a1) + "," + json.dumps(a1) + ")") is True
    # A→B→A：选择代次变了，旧 A 回包不得再更新当前状态
    assert _eval("R.isCurrent(" + json.dumps(a1) + "," + json.dumps(a3) + ")") is False
    # 跨运行回包
    assert _eval("R.isCurrent(" + json.dumps(b1) + "," + json.dumps(a3) + ")") is False
    # 同一代次内更晚的请求代次：旧请求回包作废
    a4 = {"runId": "A", "epoch": 3, "request": 4}
    assert _eval("R.isCurrent(" + json.dumps(a3) + "," + json.dumps(a4) + ")") is False
