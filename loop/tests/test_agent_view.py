"""agent 状态投影测试（Task 2）。

投影只从事件派生，不读执行内部状态；缺失产物要如实显示，不编造。
"""

from __future__ import annotations

from pathlib import Path

from services.agent_view import AGENT_ROLES, STAGES, build_agents


def _ev(seq: int, ts: float, node: str, kind: str, status: str = "ok",
        detail: dict | None = None) -> dict:
    return {"seq": seq, "ts": ts, "node": node, "kind": kind,
            "status": status, "detail": detail or {}, "refs": []}


def _by_role(agents: list[dict]) -> dict[str, dict]:
    return {a["role"]: a for a in agents}


def test_stage_map_covers_every_node_once() -> None:
    covered = [n for stage in STAGES for n in stage["nodes"]]
    assert len(covered) == 17
    assert set(covered) == {f"N{i}" for i in range(17)}


def test_all_roles_present_even_without_events(tmp_path: Path) -> None:
    agents = build_agents([], run_dir=tmp_path, now=0)
    assert [a["role"] for a in agents] == [r["role"] for r in AGENT_ROLES]
    assert all(a["status"] == "idle" for a in agents)


def test_working_and_done(tmp_path: Path) -> None:
    events = [
        _ev(1, 100, "N3", "node_started", "running"),
        _ev(2, 112, "N3", "node_finished", "ok", {"mode": "live"}),
        _ev(3, 200, "N6", "node_started", "running"),
    ]
    agents = _by_role(build_agents(events, run_dir=tmp_path, now=215))
    assert agents["analyst"]["status"] == "done"
    assert agents["analyst"]["elapsed_s"] == 12
    assert agents["analyst"]["mode"] == "live"
    assert agents["author"]["status"] == "working"
    assert agents["author"]["elapsed_s"] == 15


def test_failed_and_summary(tmp_path: Path) -> None:
    (tmp_path / "n3_digest.md").write_text("# 摘要\n3 组 / 27 条差异\n", encoding="utf-8")
    events = [
        _ev(1, 100, "N3", "node_started", "running"),
        _ev(2, 101, "N3", "node_failed", "failed", {"message": "boom"}),
    ]
    agent = _by_role(build_agents(events, run_dir=tmp_path, now=102))["analyst"]
    assert agent["status"] == "failed"
    assert "3 组 / 27 条差异" in agent["summary"]
    assert "n3_digest.md" in agent["evidence"]


def test_checker_uses_latest_node(tmp_path: Path) -> None:
    (tmp_path / "check_C.md").write_text("静态复核：通过（3 条依据）\n", encoding="utf-8")
    (tmp_path / "reconcile.md").write_text("对账：口径一 1687 / 口径二 0\n", encoding="utf-8")
    events = [
        _ev(1, 10, "N8", "node_started", "running"),
        _ev(2, 20, "N8", "node_finished", "ok"),
        _ev(3, 30, "N10", "node_started", "running"),
        _ev(4, 40, "N10", "node_finished", "ok"),
    ]
    agent = _by_role(build_agents(events, run_dir=tmp_path, now=41))["checker"]
    assert agent["status"] == "done"
    assert "对账" in agent["summary"]
    assert agent["evidence"] == ["reconcile.md"]


def test_guardian_reports_known_gap(tmp_path: Path) -> None:
    agent = _by_role(build_agents([], run_dir=tmp_path, now=0))["guardian"]
    assert agent["status"] == "idle"
    assert "未实现" in (agent["note"] or "")


def test_last_action_recorded(tmp_path: Path) -> None:
    events = [_ev(1, 1, "N12", "node_started", "running"),
              _ev(2, 2, "N12", "node_finished", "validation_failed")]
    agent = _by_role(build_agents(events, run_dir=tmp_path, now=3))["reporter"]
    assert agent["last_action"].startswith("node_finished")
    assert agent["status"] == "done"
