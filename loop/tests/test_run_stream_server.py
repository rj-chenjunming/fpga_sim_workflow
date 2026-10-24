"""U2-a（SPEC-REV-07 / SPEC-04 §6.9）：SSE 运行投影流生成逻辑的受控断言。

`services/run_stream.py` 只做传输：帧格式、变更检测（排除 updated_at 的规范化签名）、
心跳。投影仍由 RunManager.run_view 唯一产出——本测试不运行服务、不触碰业务判据。
sleep 与 fetch 均注入，测试不真实等待。
"""
from __future__ import annotations

import asyncio
import json

from services import run_stream as RS


class _Done(Exception):
    """注入的 sleep 在第 n 次后抛出，用于打断无限生成器。"""


def _fake_sleep(limit: int):
    calls = 0

    async def sleep(_s: float) -> None:
        nonlocal calls
        calls += 1
        if calls >= limit:
            raise _Done()

    return sleep


async def _collect(gen, limit: int):
    out: list[str] = []
    try:
        async for frame in gen:
            out.append(frame)
    except _Done:
        pass
    return out


def _views_fetch(views):
    it = iter(views)

    async def fetch():
        try:
            return next(it)
        except StopIteration:
            return views[-1]

    return fetch


def test_frame_format_single_line():
    assert RS.sse_frame("run_view", '{"a":1}') == 'event: run_view\ndata: {"a":1}\n\n'


def test_frame_format_multiline_data():
    assert RS.sse_frame("x", "a\nb") == "event: x\ndata: a\ndata: b\n\n"


def test_signature_ignores_volatile_updated_at():
    a = RS.payload_signature({"run_id": "A", "status": "running", "updated_at": "t1"})
    b = RS.payload_signature({"run_id": "A", "status": "running", "updated_at": "t2"})
    c = RS.payload_signature({"run_id": "A", "status": "failed", "updated_at": "t2"})
    assert a == b
    assert a != c


async def test_updated_at_churn_alone_does_not_reemit():
    views = [
        {"run_id": "A", "status": "running", "updated_at": "t1"},
        {"run_id": "A", "status": "running", "updated_at": "t2"},
        {"run_id": "A", "status": "running", "updated_at": "t3"},
    ]
    frames = await _collect(
        RS.run_view_stream(_views_fetch(views), interval_s=1.0, heartbeat_s=15.0,
                           sleep=_fake_sleep(3)),
        limit=3,
    )
    assert [f for f in frames if f.startswith("event: run_view")] == [
        'event: run_view\ndata: ' + json.dumps(views[0], ensure_ascii=False) + "\n\n"
    ]


async def test_real_change_emits_second_frame():
    views = [
        {"run_id": "A", "status": "running", "updated_at": "t1"},
        {"run_id": "A", "status": "waiting_gate", "updated_at": "t2"},
        {"run_id": "A", "status": "waiting_gate", "updated_at": "t3"},
    ]
    frames = await _collect(
        RS.run_view_stream(_views_fetch(views), interval_s=1.0, heartbeat_s=15.0,
                           sleep=_fake_sleep(3)),
        limit=3,
    )
    assert len([f for f in frames if f.startswith("event: run_view")]) == 2


async def test_unknown_run_first_fetch_emits_error_then_ends():
    async def fetch():
        raise KeyError("A")

    frames = []
    async for frame in RS.run_view_stream(fetch, interval_s=1.0, heartbeat_s=15.0,
                                          sleep=_fake_sleep(1)):
        frames.append(frame)
    assert frames == ['event: error\ndata: ' + json.dumps({"error": "unknown run"}) + "\n\n"]


async def test_run_disappears_after_frames_emits_gone_then_ends():
    views = [{"run_id": "A", "status": "running", "updated_at": "t1"}]
    state = {"n": 0}

    async def fetch():
        state["n"] += 1
        if state["n"] == 1:
            return views[0]
        raise KeyError("A")

    frames = []
    async for frame in RS.run_view_stream(fetch, interval_s=1.0, heartbeat_s=15.0,
                                          sleep=_fake_sleep(2)):
        frames.append(frame)
    assert [f.split("\n")[0] for f in frames] == ["event: run_view", "event: gone"]


async def test_heartbeat_pings_between_changes():
    view = {"run_id": "A", "status": "running", "updated_at": "t1"}
    frames = await _collect(
        RS.run_view_stream(_views_fetch([view]), interval_s=1.0, heartbeat_s=3.0,
                           sleep=_fake_sleep(6)),
        limit=6,
    )
    # 6 拍：第 1 拍首推 run_view；第 3、6 拍心跳 ping；其余静默。
    assert frames == [
        'event: run_view\ndata: ' + json.dumps(view, ensure_ascii=False) + "\n\n",
        ": ping\n\n",
        ": ping\n\n",
    ]
