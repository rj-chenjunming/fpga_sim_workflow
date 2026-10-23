"""节点详情的引用边界同时约束汇总和事件切片，不修改权威事件。"""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from host.progress import ProgressLog
from services import api, node_view


def _event(refs: list[str]) -> dict:
    return {
        "seq": 1, "ts": 100.0, "run_id": "RUN-20261023-000001", "node": "N2",
        "kind": "node_finished", "status": "ok", "provisional": False,
        "detail": {"summary": "N2：差异已生成", "source": "kb_tool"}, "refs": refs,
    }


@pytest.mark.parametrize("escape", ["absolute", "relative", "symlink"])
def test_event_refs_obey_run_boundary_without_mutating_events(tmp_path: Path, escape: str) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outside = tmp_path / "outside.log"
    outside.write_text("not served", encoding="utf-8")
    link = run_dir / "escape.log"
    link.symlink_to(outside)
    ref = {"absolute": str(outside), "relative": "../outside.log", "symlink": str(link)}[escape]
    event = _event(["n2_diff.json", ref])
    original = copy.deepcopy(event)

    got = node_view.build_node_detail(event["run_id"], "N2", events=[event], run_dir=str(run_dir))

    assert got["refs"] == ["n2_diff.json"]
    assert got["refs_omitted"] == 1
    assert got["events"][0]["refs"] == ["n2_diff.json"]
    assert got["events"][0]["refs_omitted"] == 1
    for key in ("seq", "kind", "status", "ts", "detail", "provisional"):
        assert got["events"][0][key] == original[key]
    assert event == original


def test_unscoped_projection_preserves_event_refs() -> None:
    """特征：不传 run_dir 的独立纯函数调用保持历史行为。"""
    event = _event(["n2_diff.json", "/outside/job.log"])
    got = node_view.build_node_detail(event["run_id"], "N2", events=[event])
    assert got["refs"] == event["refs"]
    assert got["events"][0]["refs"] == event["refs"]
    assert got["refs_omitted"] == 0


def test_node_endpoint_filters_event_refs_and_leaves_log_unchanged(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    event = _event(["n2_diff.json", str(tmp_path / "external.log")])
    log = ProgressLog(tmp_path / "events", event["run_id"])
    log.append("node_finished", node="N2", status="ok", detail=event["detail"], refs=event["refs"])
    before = log.path.read_bytes()
    manager = SimpleNamespace(docs={event["run_id"]: SimpleNamespace(
        mode="drill", s0_record_id=None, run_dir=str(run_dir),
    )})
    monkeypatch.setattr(api, "_manager", lambda: manager)
    monkeypatch.setattr(api.P, "EVENTS_DIR", log.dir)

    response = TestClient(api.app).get(f"/api/runs/{event['run_id']}/nodes/N2")

    assert response.status_code == 200
    body = response.json()
    assert body["refs"] == body["events"][0]["refs"] == ["n2_diff.json"]
    assert body["refs_omitted"] == body["events"][0]["refs_omitted"] == 1
    assert "external.log" not in response.text
    assert log.path.read_bytes() == before
