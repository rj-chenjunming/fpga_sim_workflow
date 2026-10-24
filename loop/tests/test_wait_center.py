"""U1-a/U1-b（SPEC-REV-07）：等待送达判定的纯函数受控断言（node 驱动）。

`web/wait-center.js` 只做判定：状态跃迁何时提醒、行动条聚合哪些条目、标题徽标。
app.js 仍是唯一会话协调 owner（持有状态、渲染、Notification DOM）。
本文件不证明浏览器交互与真实通知投递，只证明判定口径。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "wait-center.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const W = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def _runs(*pairs):
    return [{"run_id": rid, "status": st} for rid, st in pairs]


def test_first_snapshot_never_alerts():
    assert _eval(
        "W.deriveAlerts(null, [{run_id:'A', status:'waiting_gate'}])"
    ) == []


def test_entering_waiting_gate_alerts():
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'running'}], [{run_id:'A', status:'waiting_gate'}])"
    ) == [{"run_id": "A", "from": "running", "to": "waiting_gate", "kind": "gate"}]


def test_staying_in_same_status_never_alerts():
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'waiting_gate'}], [{run_id:'A', status:'waiting_gate'}])"
    ) == []


def test_entering_failed_alerts():
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'waiting_job'}], [{run_id:'A', status:'failed'}])"
    ) == [{"run_id": "A", "from": "waiting_job", "to": "failed", "kind": "failed"}]


def test_leaving_waiting_job_alerts_job_done():
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'waiting_job'}], [{run_id:'A', status:'running'}])"
    ) == [{"run_id": "A", "from": "waiting_job", "to": "running", "kind": "job_done"}]


def test_job_to_gate_in_one_poll_emits_gate_only():
    """同一拍既有「作业结束」又有「等到人」⇒ 只提醒更需要人的一类（闸门优先）。"""
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'waiting_job'}], [{run_id:'A', status:'waiting_gate'}])"
    ) == [{"run_id": "A", "from": "waiting_job", "to": "waiting_gate", "kind": "gate"}]


def test_new_run_without_prev_entry_never_alerts():
    assert _eval(
        "W.deriveAlerts([{run_id:'A', status:'running'}], "
        "[{run_id:'A', status:'running'}, {run_id:'B', status:'waiting_gate'}])"
    ) == []


def test_multiple_runs_alert_in_snapshot_order():
    out = _eval(
        "W.deriveAlerts([{run_id:'A', status:'running'},{run_id:'B', status:'running'}], "
        "[{run_id:'B', status:'waiting_gate'},{run_id:'A', status:'failed'}])"
    )
    assert [item["run_id"] for item in out] == ["B", "A"]
    assert [item["kind"] for item in out] == ["gate", "failed"]


def test_derive_actions_gates_first_then_failed():
    out = _eval(
        "W.deriveActions([{run_id:'A', status:'failed'},{run_id:'B', status:'waiting_gate'},"
        "{run_id:'C', status:'running'},{run_id:'D', status:'finished'}])"
    )
    assert out == [
        {"run_id": "B", "status": "waiting_gate", "kind": "gate"},
        {"run_id": "A", "status": "failed", "kind": "failed"},
    ]


def test_derive_actions_empty_when_no_attention():
    assert _eval("W.deriveActions([])") == []
    assert _eval(
        "W.deriveActions([{run_id:'A', status:'running'},{run_id:'B', status:'finished'}])"
    ) == []


def test_attention_counts_only_gate_and_failed():
    assert _eval(
        "W.attentionCount([{run_id:'A', status:'waiting_gate'},{run_id:'B', status:'failed'},"
        "{run_id:'C', status:'running'}])"
    ) == 2
    assert _eval("W.attentionCount([])") == 0


def test_badge_title_prefix_and_plain():
    assert _eval("W.badgeTitle('FPGA Flow', 0)") == "FPGA Flow"
    assert _eval("W.badgeTitle('FPGA Flow', 3)") == "(3) FPGA Flow"
