"""U9（SPEC-REV-08）：长任务卡空态判定的纯函数受控断言（node 驱动）。

`web/job-status.js` 从事件流（服务端既有投影）取最近 job_finished/dead_job，
区分「无作业记录」「最近一次作业已完成」「作业已死亡」三种空态文案。
展示推导与 deriveAgentStatus 同模式：只消费事件，不新增判据、不写状态。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "job-status.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const J = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def test_no_job_events_is_none():
    assert _eval("J.emptyHint([])") == {"kind": "none"}
    assert _eval("J.emptyHint([{kind:'node_started', node:'N9'}])") == {"kind": "none"}
    assert _eval("J.emptyText([])") is None


def test_finished_job_hint():
    hint = _eval(
        "J.emptyHint([{kind:'job_submitted', node:'N9', detail:{job_id:'J1'}},"
        "{kind:'job_finished', node:'N9', detail:{rc:0, job_id:'J1'}}])")
    assert hint == {"kind": "finished", "node": "N9", "rc": 0, "jobId": "J1"}


def test_dead_job_hint():
    hint = _eval(
        "J.emptyHint([{kind:'dead_job', node:'N9', detail:{job_id:'J2'}}])")
    assert hint == {"kind": "dead", "node": "N9", "rc": None, "jobId": "J2"}


def test_latest_terminal_wins():
    hint = _eval(
        "J.emptyHint([{kind:'job_finished', node:'N9', detail:{rc:1}},"
        "{kind:'job_finished', node:'N9', detail:{rc:0}}])")
    assert hint["rc"] == 0


def test_missing_details_tolerated():
    hint = _eval("J.emptyHint([{kind:'job_finished', node:'N9'}])")
    assert hint == {"kind": "finished", "node": "N9", "rc": None, "jobId": None}


def test_finished_text_mentions_node_and_rc():
    text = _eval(
        "J.emptyText([{kind:'job_finished', node:'N9', detail:{rc:0}}])")
    assert "N9" in text and "已完成" in text


def test_dead_text_mentions_dead_job():
    text = _eval("J.emptyText([{kind:'dead_job', node:'N9'}])")
    assert "dead_job" in text or "死亡" in text
