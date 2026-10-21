"""F02-b：`POST /api/runs` 在基线无效时返回**结构化** detail（missing / errors）。

契约见 [Web UI §6.4](../../doc/spec/WEB_UI_SPEC.md)。失败必须可诊断，而不是一段拼接文本。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from host import paths as P
from services.api import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _start(client: TestClient, baseline: str) -> object:
    return client.post("/api/runs", json={"baseline": baseline, "mode": "real"})


def test_unknown_baseline_returns_structured_detail(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "kb"
    (workspace / "baselines").mkdir(parents=True)
    monkeypatch.setattr(P, "KB_DIR", workspace)

    response = _start(client, "v99")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["baseline"] == "v99"
    assert isinstance(detail["missing"], list) and detail["missing"], detail
    assert isinstance(detail["errors"], list)
    assert detail["error"]


def test_bad_manifest_returns_errors_list(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "kb"
    baseline = workspace / "baselines" / "v9"
    baseline.mkdir(parents=True)
    (baseline / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(P, "KB_DIR", workspace)

    response = _start(client, "v9")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["baseline"] == "v9"
    assert isinstance(detail["missing"], list)
    assert isinstance(detail["errors"], list) and detail["errors"], detail
    # 结构化字段与 message 分工：message 不重复拼接 schema 违规（避免 UI 双份展示）。
    assert "schema" not in detail["error"], detail["error"]


def test_non_baseline_value_error_detail_shape_is_unchanged(
    client: TestClient,
) -> None:
    """非基线原因（mode 非法）仍是最小形态，不伪造 missing/errors。"""
    response = client.post("/api/runs", json={"baseline": "v0", "mode": "bogus"})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "error" in detail
    assert "missing" not in detail and "errors" not in detail
