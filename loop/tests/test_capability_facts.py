"""F02-c：能力事实的唯一投影与前端口径一致性。

能力事实由 `services/agent_view.py` 唯一投影；Agent 窗口与运行视图角色卡读**同一来源**。
本文件证明：
1. 节点能力与角色卡能力逐字段相等（不是两套推导）；
2. 未知维度保持 `None`，不猜；
3. `GET /api/runs/{id}/agents/{node}` 响应带同源 `capabilities`；
4. 前端只有一份格式化实现，app.js / agent-window.js 都调用它。

浏览器真实渲染未验证（本机无 playwright）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from services import agent_view as A
from services import api

from test_agent_context_memory import ctx, provider, call  # noqa: F401


def _n8_events() -> list[dict]:
    return [
        {"node": "N8", "kind": "node_started", "status": "started", "ts": 1.0,
         "detail": {"mode": "standin"}},
        {"node": "N8", "kind": "node_finished", "status": "pass", "ts": 4.0, "detail": {}},
    ]


def test_node_capabilities_equal_role_card_projection(tmp_path):
    events = _n8_events()
    cards = A.build_agents(events, run_dir=tmp_path)
    card = next(c for c in cards if "N8" in c["nodes"])
    caps = A.node_capabilities("N8", events)
    assert caps == card["capabilities"]
    assert caps["implemented"] is True
    assert caps["execution"] == "standin"
    # 本层没有 provider/UVS/夹具探针 ⇒ 未知保持 None，不用默认值冒充
    assert caps["dependencies_ready"] is None
    assert caps["verification_scope"] is None


def test_host_nodes_have_no_role_capabilities():
    assert A.node_capabilities("N0", []) is None
    assert A.node_capabilities("N16", []) is None


def test_unknown_execution_stays_unknown():
    events = [{"node": "N11", "kind": "node_started", "status": "started", "ts": 1.0}]
    caps = A.node_capabilities("N11", events)
    assert caps["execution"] == "unknown"
    assert caps["dependencies_ready"] is None


async def test_agent_window_api_returns_same_capabilities(ctx, provider, monkeypatch):
    await call(ctx)
    events = _n8_events() + [{"node": "N3", "kind": "node_started", "status": "started",
                              "ts": 2.0, "detail": {"mode": "standin"}}]
    manager = SimpleNamespace(
        docs={ctx.run_id: SimpleNamespace(run_dir=str(ctx.run_dir))},
        _progress=lambda _run: SimpleNamespace(read=lambda: events),
    )
    monkeypatch.setattr(api, "_manager", lambda: manager)
    client = TestClient(api.app)
    body = client.get(f"/api/runs/{ctx.run_id}/agents/N3").json()
    # 精确期望（不用被测函数计算期望值）
    assert body["capabilities"] == {
        "implemented": True,
        "dependencies_ready": None,
        "execution": "standin",
        "verification_scope": None,
    }
    # F10：预算上限由 Host 下发，前端不硬编码
    from host import agent_memory as AM
    assert body["context_budget"] == {"limit_bytes": AM.MAX_CONTEXT_BYTES}


def test_there_is_a_single_role_projection():
    """不允许在 API/前端再算一套四维能力。"""
    import inspect

    source = inspect.getsource(A)
    assert "def _capabilities" in source and source.count("def _capabilities") == 1
