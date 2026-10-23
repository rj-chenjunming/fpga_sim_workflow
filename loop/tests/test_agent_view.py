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


def test_guardian_capability_facts_when_idle(tmp_path: Path) -> None:
    """F02：N11 已实现（成链判断/返工）；idle 只表示本次未开始，不得说「未实现」。"""
    agent = _by_role(build_agents([], run_dir=tmp_path, now=0))["guardian"]
    assert agent["status"] == "idle"
    assert "未实现" not in (agent["note"] or "")
    assert "未实现" not in agent["summary"]
    facts = agent["capabilities"]
    assert facts["implemented"] is True
    assert facts["execution"] == "not_started"
    # 未知维度必须保持未知，不得用 false/猜测值填充
    assert facts["dependencies_ready"] is None
    assert facts["verification_scope"] is None


def test_every_card_exposes_capability_facts(tmp_path: Path) -> None:
    """四维能力事实由服务端下发，五张卡都有，UI 不需要自己推断。"""
    agents = build_agents([], run_dir=tmp_path, now=0)
    for agent in agents:
        facts = agent["capabilities"]
        assert set(facts) == {"implemented", "dependencies_ready", "execution", "verification_scope"}
        assert isinstance(facts["implemented"], bool)
        assert facts["execution"] == "not_started"


def test_execution_dimension_distinguishes_standin_and_real(tmp_path: Path) -> None:
    """本次执行方式如实反映事件里的 mode；standin 不得被显示成真实完成。"""
    standin_events = [
        _ev(1, 10, "N11", "node_started", "running"),
        _ev(2, 20, "N11", "node_finished", "ok", {"mode": "standin"}),
    ]
    guardian = _by_role(build_agents(standin_events, run_dir=tmp_path, now=21))["guardian"]
    assert guardian["status"] == "done"
    assert guardian["capabilities"]["execution"] == "standin"

    real_events = [
        _ev(1, 10, "N11", "node_started", "running"),
        _ev(2, 20, "N11", "node_finished", "ok", {"mode": "live"}),
    ]
    guardian = _by_role(build_agents(real_events, run_dir=tmp_path, now=21))["guardian"]
    assert guardian["capabilities"]["execution"] == "real"


def test_last_action_recorded(tmp_path: Path) -> None:
    events = [_ev(1, 1, "N12", "node_started", "running"),
              _ev(2, 2, "N12", "node_finished", "validation_failed")]
    agent = _by_role(build_agents(events, run_dir=tmp_path, now=3))["reporter"]
    assert agent["last_action"].startswith("node_finished")
    assert agent["status"] == "done"


def test_summary_prefers_conclusion_line(tmp_path: Path) -> None:
    (tmp_path / "check_C.md").write_text(
        "# N8 静态复核\n\n- **复核人**：checker\n- **卡点 C 结论（一句话）**：**5 通过 / 0 退回**\n",
        encoding="utf-8",
    )
    events = [_ev(1, 10, "N8", "node_started", "running"),
              _ev(2, 20, "N8", "node_finished", "ok")]
    agent = _by_role(build_agents(events, run_dir=tmp_path, now=21))["checker"]
    assert "5 通过 / 0 退回" in agent["summary"]


def test_job_interrupt_without_gate_does_not_mark_roles_waiting(tmp_path: Path) -> None:
    """job_done 中断没有 payload.gate：不得把模型角色标成 waiting（2026-10-23）。

    回归：`GATE_NODES.get(非闸门节点) is None` 与 `gate is None` 相等，曾让
    N3/N6/N8 等角色恒为 "waiting"，阶段标签因此误显示「等待人工」。
    """
    events = [
        _ev(1, 100, "N3", "node_started", "running"),
        _ev(2, 112, "N3", "node_finished", "ok", {"mode": "live"}),
        _ev(3, 200, "N9", "node_started", "running"),
    ]
    job = {"job_id": "J-1", "phase": "running"}
    pending = {"id": "JOB:J-1", "type": "job_done",
               "payload": {"job_id": "J-1", "node": "N9", "wait_reason": "长任务"}}
    agents = _by_role(build_agents(events, run_dir=tmp_path, pending_interrupt=pending,
                                   job=job, now=215))
    assert agents["analyst"]["status"] == "done", "N3 已结束，不得因 job 中断变 waiting"
    assert agents["author"]["status"] == "idle"
    assert agents["checker"]["status"] == "idle"


def test_real_gate_interrupt_still_marks_gate_role_waiting(tmp_path: Path) -> None:
    events = [
        _ev(1, 100, "N3", "node_started", "running"),
        _ev(2, 112, "N3", "node_finished", "ok"),
    ]
    pending = {"id": "G1:0", "type": "gate_decision",
               "payload": {"gate": "G1_diff_confirm", "gate_node": "N4"}}
    agents = _by_role(build_agents(events, run_dir=tmp_path, pending_interrupt=pending, now=120))
    assert agents["analyst"]["status"] == "done"
    # 闸门节点 N4 不在模型角色里，但真闸门不得把其他角色误标 waiting
    assert agents["author"]["status"] == "idle"
