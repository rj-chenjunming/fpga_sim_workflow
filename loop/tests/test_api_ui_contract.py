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
