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
from test_baseline_admission import make_baseline


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


# ------------------------------------------------- R3：manifest 解码失败隔离
#
# 契约：非 UTF-8 的 manifest 只让**该条** invalid + errors（编排规格 §3.1 条款 4
# 「解码失败隔离」），不得使整个列表端点 500，也不得用 errors="ignore" 改写清单。


def test_non_utf8_manifest_does_not_break_baseline_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3 红灯：一个坏编码 manifest 曾让真实 `GET /api/baselines` 整体 500。"""
    workspace = tmp_path / "kb"
    make_baseline(workspace, "v1")
    bad = make_baseline(workspace, "v2")
    (bad / "manifest.json").write_bytes(b"\xff\xfe")
    monkeypatch.setattr(P, "WORKSPACE_ROOT", workspace)

    # 默认 TestClient 会把服务端异常重新抛出：这里要观察真实 HTTP 状态码。
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        response = raw_client.get("/api/baselines")

    assert response.status_code == 200, response.text
    by_id = {item["id"]: item for item in response.json()["baselines"]}
    assert by_id["v1"]["valid"] is True, by_id["v1"]
    assert by_id["v2"]["valid"] is False, by_id["v2"]
    assert by_id["v2"]["errors"], by_id["v2"]
    assert any(
        word in error for error in by_id["v2"]["errors"] for word in ("解码", "编码", "UTF-8")
    ), by_id["v2"]


def test_non_utf8_manifest_real_start_is_rejected_with_structured_errors(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3：real 选坏编码基线 ⇒ HTTP 400 + 结构化 errors（不是 500，也不建 run）。"""
    workspace = tmp_path / "kb"
    bad = make_baseline(workspace, "v9")
    (bad / "manifest.json").write_bytes(b"\xff\xfe")
    monkeypatch.setattr(P, "KB_DIR", workspace)

    from workflows import main_flow

    def must_not_prepare(*args: object, **kwargs: object) -> object:
        raise AssertionError("坏编码基线必须在 prepare_run_dir 之前被拒绝")

    monkeypatch.setattr(main_flow, "prepare_run_dir", must_not_prepare)

    response = _start(client, "v9")
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert detail["baseline"] == "v9"
    assert isinstance(detail["missing"], list)
    assert isinstance(detail["errors"], list) and detail["errors"], detail

