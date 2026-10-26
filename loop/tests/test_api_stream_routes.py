"""两条 SSE 路由的 **HTTP 级**契约（SPEC-04 §6.9 / §6.10；STATUS §67.5 遗留项）。

分层：`test_run_stream_server.py` 已断言生成器内部（帧格式/心跳/变更检测/结束语义），
那是纯函数层；本文件只固定**路由层**三件事 ——
  1. 未知 run ⇒ 404（不是"200 然后推 error 帧"）；
  2. 成功响应 `Content-Type: text/event-stream`（前端据此决定走流还是回退轮询，
     WEB_UI_SPEC §7.3）；
  3. 首帧事件名正确（`run_view` / `agent_view`，SPEC-REV-07 U2-a/U2-b）。

替身只替换数据来源，不替换传输实现：路由仍走真实 `StreamingResponse` +
`services.run_stream`，因此帧格式与结束语义仍是生产代码路径。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient


def _client(monkeypatch, manager=None):
    """路由用 `api._manager()` 取运行集合；替身只给 `docs` 与 `run_view`。"""
    from services import api

    monkeypatch.setattr(api, "_manager", lambda: manager or SimpleNamespace(docs={}))
    return TestClient(api.app)


def _frames(text: str) -> list[list[str]]:
    """按 SSE 规范以空行切帧（帧内保留各行原文）。"""
    return [frame.splitlines() for frame in text.split("\n\n") if frame.strip()]


def _frame_of(frames: list[list[str]], event: str) -> list[str]:
    for frame in frames:
        if event in frame:
            return frame
    raise AssertionError(f"没有 {event} 帧：{frames}")


def _first_data(text: str) -> dict:
    line = next(line for line in text.splitlines() if line.startswith("data: "))
    return json.loads(line[len("data: "):])


def test_stream_routes_answer_404_for_unknown_run(monkeypatch):
    client = _client(monkeypatch)
    run_stream = client.get("/api/runs/RUN-NOT-EXIST/stream")
    assert run_stream.status_code == 404, run_stream.text
    assert "未知 run_id" in run_stream.json()["detail"]["error"]
    agent_stream = client.get("/api/runs/RUN-NOT-EXIST/agents/N3/stream")
    assert agent_stream.status_code == 404, agent_stream.text


def test_run_stream_route_emits_event_stream_and_run_view_first_frame(monkeypatch):
    view = {"run_id": "RUN-TEST-0001", "status": "waiting_gate", "gate": "G1_diff_confirm"}
    calls = {"n": 0}

    def run_view(_run_id: str) -> dict:
        calls["n"] += 1
        if calls["n"] > 1:
            # 第二拍起 run 消失 ⇒ 生成器推 gone 后正常结束；让响应能收敛，测试不悬挂。
            raise KeyError(_run_id)
        return dict(view)

    manager = SimpleNamespace(docs={"RUN-TEST-0001": SimpleNamespace(run_dir="/nonexistent")},
                              run_view=run_view)
    client = _client(monkeypatch, manager)
    response = client.get("/api/runs/RUN-TEST-0001/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    frames = _frames(response.text)
    assert "event: run_view" in response.text
    assert _first_data(response.text) == view
    # 数据帧必须是**单行** data（多行会被 SSE 拆成多条 data，恰好前端解析会碎）
    first = _frame_of(frames, "event: run_view")
    data_lines = [line for line in first if line.startswith("data: ")]
    assert len(data_lines) == 1, first
    assert json.loads(data_lines[0][len("data: "):]) == view
    assert "event: gone" in response.text, "run 消失必须显式 gone，不伪装存活"


def test_agent_stream_route_emits_event_stream_and_agent_view_first_frame(monkeypatch):
    from services import api

    payload = {"run_id": "RUN-TEST-0002", "node": "N3", "live": None, "attempts": []}
    calls = {"n": 0}

    monkeypatch.setattr(api, "_agent_root", lambda _run_id, _node: "/nonexistent")
    def agent_view(_root, run_id, node, _attempt):
        calls["n"] += 1
        if calls["n"] > 2:  # 1 次建连前预验证 + 1 次首帧，之后视为消失
            raise KeyError(run_id)
        return dict(payload)

    monkeypatch.setattr(api, "_agent_window_view", agent_view)
    client = _client(monkeypatch)
    response = client.get("/api/runs/RUN-TEST-0002/agents/N3/stream")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: agent_view" in response.text, "Agent 流必须用独立事件名（SPEC-04 §6.10）"
    assert _first_data(response.text) == payload
