"""HTTP 契约：配置面 + project 字段 + agent 投影（Task 3 / Task 7 A1–A6）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from host import paths as P
from services.api import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_baselines_endpoint(client: TestClient) -> None:
    r = client.get("/api/baselines")
    assert r.status_code == 200
    ids = [b["id"] for b in r.json()["baselines"]]
    assert "v0" in ids


def test_env_check_current_root(client: TestClient) -> None:
    r = client.get("/api/env/check", params={"path": str(P.ENV_ROOT)})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["matches_current_process"] is True


def test_env_check_rejects_bad_path(client: TestClient) -> None:
    r = client.get("/api/env/check", params={"path": "/nonexistent/dir"})
    assert r.status_code == 400


def test_fs_dirs_rejects_escape(client: TestClient) -> None:
    r = client.get("/api/fs/dirs", params={"path": "/etc"})
    assert r.status_code == 403


def test_fs_dirs_lists_env_parent(client: TestClient) -> None:
    r = client.get("/api/fs/dirs", params={"path": str(P.ENV_ROOT.parent)})
    assert r.status_code == 200
    names = [e["name"] for e in r.json()["entries"]]
    assert P.ENV_ROOT.name in names


def test_create_run_echoes_project(client: TestClient) -> None:
    r = client.post("/api/runs", json={
        "baseline": "v0", "mode": "drill", "project": str(P.ENV_ROOT),
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["project"] == str(P.ENV_ROOT)
    rid = body["run_id"]

    view = client.get(f"/api/runs/{rid}").json()
    assert view["project"] == str(P.ENV_ROOT)
    assert len(view["agents"]) == 5
    assert view["agents_authority"] == "projection"
    assert {n for s in view["stage_map"] for n in s["nodes"]} == {f"N{i}" for i in range(17)}


def test_create_run_rejects_other_project(client: TestClient) -> None:
    r = client.post("/api/runs", json={"baseline": "v0", "mode": "drill", "project": "/tmp"})
    assert r.status_code == 400
    assert "ENV_ROOT" in r.json()["detail"]["error"]


def test_gate_material_projection_has_diff_entries(client: TestClient) -> None:
    """G1 材料必须带逐条差异与未决标记（前端据此渲染，不再让用户空口确认）。"""
    r = client.post("/api/runs", json={
        "baseline": "v0", "mode": "drill", "project": str(P.ENV_ROOT),
    })
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    view = client.get(f"/api/runs/{rid}").json()
    pending = view.get("pending_interrupt") or {}
    assert pending.get("payload", {}).get("gate") == "G1_diff_confirm"

    mat = pending["payload"]
    diff = mat.get("difference_items") or {}
    assert diff.get("present") is True
    entries = diff.get("entries") or []
    assert diff.get("count") == len(entries) >= 1
    for entry in entries:
        assert "entry_id" in entry
        assert "unresolved" in entry
    assert diff.get("unresolved_count", 0) >= 1
    assert mat.get("unresolved_entries"), "G1 材料必须单列未决条目"


def test_frontend_event_whitelist_matches_server_authority() -> None:
    """SPEC-02 §9 / SPEC-REV-01 §D E2：前端静态兜底表必须与服务端 `ALLOWED_KINDS` 逐项相等。

    前端运行时已改为消费 `/api/health.event_kinds`；静态表只用于首屏。若两边漂移，
    就会重现"规格 8 / 服务端 15 / 前端 16"的三套口径，故用测试钉住。
    """
    import re
    from pathlib import Path

    from host.progress import ALLOWED_KINDS

    app_js = (Path(P.LOOP_DIR) / "web" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"var EVENT_WHITELIST = \{(.*?)\};", app_js, re.S)
    assert match, "app.js 里找不到 EVENT_WHITELIST 静态兜底表"
    keys = set(re.findall(r"\b([a-z_]+)\s*:\s*1\b", match.group(1)))
    assert keys == set(ALLOWED_KINDS), (
        "前端事件白名单与 host.progress.ALLOWED_KINDS 漂移："
        f"only_frontend={sorted(keys - set(ALLOWED_KINDS))} "
        f"only_server={sorted(set(ALLOWED_KINDS) - keys)}"
    )
