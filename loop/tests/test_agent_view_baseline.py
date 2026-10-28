"""S4-A 特征测试：固定 `services/agent_view.py` **既有**可观察行为（不改行为）。

为什么先写这一份：S4 要给角色卡/窗口新增 `progress`（总结投影）与 `explain`（S3 接面），
而这些字段要**复用**既有的 `_status` / `_execution` / `_elapsed` / `_collect`。重构前先用
不读源码也能判定的断言把旧语义钉住（AGENTS §2.1-3），否则"新增字段"会悄悄改掉旧卡片状态。

本文件只断言**现状**；新行为（progress/no_progress/compaction/explain）在
`test_agent_view_projection.py` 里先写失败用例。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.agent_view import (
    AGENT_ROLES,
    GATE_NODES,
    _collect,
    _elapsed,
    _execution,
    _status,
    build_agents,
    node_capabilities,
)


def _ev(seq: int, ts: float, node: str, kind: str, status: str = "ok",
        detail: dict | None = None) -> dict:
    return {"seq": seq, "ts": ts, "node": node, "kind": kind,
            "status": status, "detail": detail or {}, "refs": []}


def _by_role(agents: list[dict]) -> dict[str, dict]:
    return {a["role"]: a for a in agents}


# ---------------------------------------------------------------- 卡片形状（固定既有字段集）

def test_card_keys_are_frozen(tmp_path: Path) -> None:
    """角色卡字段集合是既有契约：新增字段只能**加**，不能悄悄改名/删旧字段。"""
    agents = build_agents([], run_dir=tmp_path, now=0)
    assert [a["role"] for a in agents] == [r["role"] for r in AGENT_ROLES]
    for card in agents:
        assert set(card) >= {
            "role", "name", "nodes", "active_node", "status", "last_action",
            "elapsed_s", "summary", "mode", "evidence", "note", "capabilities",
        }
    assert set(agents[0]["capabilities"]) == {
        "implemented", "dependencies_ready", "execution", "verification_scope",
    }


def test_card_roles_and_nodes_are_frozen() -> None:
    assert [(r["role"], tuple(r["nodes"])) for r in AGENT_ROLES] == [
        ("analyst", ("N3",)),
        ("author", ("N6",)),
        ("checker", ("N8", "N10")),
        ("guardian", ("N11",)),
        ("reporter", ("N12",)),
    ]
    assert GATE_NODES == {"N4": "G1_diff_confirm", "N13": "G2_report_accept",
                          "N14": "G3_regression_decision"}


def test_empty_events_all_idle_not_started(tmp_path: Path) -> None:
    for card in build_agents([], run_dir=tmp_path, now=0):
        assert card["status"] == "idle"
        assert card["active_node"] == card["nodes"][0]
        assert card["last_action"] == "—"
        assert card["mode"] == "—"
        assert card["elapsed_s"] is None
        assert card["evidence"] == []
        assert card["capabilities"]["execution"] == "not_started"


def test_summary_reports_missing_and_present_artifact(tmp_path: Path) -> None:
    """产物缺失就如实说缺失；存在则取一行结论并给出证据文件名。"""
    assert _by_role(build_agents([], run_dir=tmp_path, now=0))["author"]["summary"] == "产物未生成"
    (tmp_path / "n3_digest.md").write_text("# 摘要\n3 组 / 27 条差异\n", encoding="utf-8")
    events = [_ev(1, 100, "N3", "node_started", "running"),
              _ev(2, 112, "N3", "node_finished", "ok", {"mode": "live"})]
    analyst = _by_role(build_agents(events, run_dir=tmp_path, now=120))["analyst"]
    assert "3 组 / 27 条差异" in analyst["summary"]
    assert analyst["evidence"] == ["n3_digest.md"]


def test_guardian_idle_summary_is_standby(tmp_path: Path) -> None:
    guardian = _by_role(build_agents([], run_dir=tmp_path, now=0))["guardian"]
    assert "待命" in guardian["summary"]
    assert "未实现" not in guardian["summary"]
    assert guardian["note"] is not None
    assert _by_role(build_agents([], run_dir=tmp_path, now=0))["analyst"]["note"] is None


# ---------------------------------------------------------------- _status 五态语义

@pytest.mark.parametrize("node", ["N3", "N6", "N8", "N10", "N11", "N12"])
def test_status_idle_without_events(node: str) -> None:
    assert _status(node, None, None, None) == "idle"


def test_status_working_done_failed() -> None:
    started = _collect([_ev(1, 100, "N3", "node_started", "running")])["N3"]
    assert _status("N3", started, None, None) == "working"

    done = _collect([_ev(1, 100, "N3", "node_started", "running"),
                     _ev(2, 112, "N3", "node_finished", "ok")])["N3"]
    assert _status("N3", done, None, None) == "done"

    finished_failed = _collect([_ev(1, 100, "N3", "node_started", "running"),
                                _ev(2, 112, "N3", "node_finished", "failed")])["N3"]
    assert _status("N3", finished_failed, None, None) == "failed"

    failed_only = _collect([_ev(1, 100, "N3", "node_started", "running"),
                            _ev(2, 101, "N3", "node_failed", "failed",
                                {"message": "boom"})])["N3"]
    assert _status("N3", failed_only, None, None) == "failed"


def test_status_waiting_only_for_matching_gate() -> None:
    """waiting 只能由**真闸门**产生：非闸门中断不得让模型角色变 waiting。"""
    state = _collect([_ev(1, 100, "N3", "node_started", "running")])["N3"]
    gate = {"id": "G1:0", "type": "gate_decision",
            "payload": {"gate": "G1_diff_confirm", "gate_node": "N4"}}
    assert _status("N4", state, gate, None) == "waiting"
    assert _status("N3", state, gate, None) == "working"

    job_done = {"id": "JOB:J-1", "type": "job_done",
                "payload": {"job_id": "J-1", "node": "N9", "wait_reason": "长任务"}}
    assert _status("N3", state, job_done, {"phase": "running"}) == "working"


def test_status_n9_waiting_while_job_running() -> None:
    state = _collect([_ev(1, 100, "N9", "node_started", "running")])["N9"]
    assert _status("N9", state, None, {"phase": "running"}) == "waiting"
    assert _status("N9", state, None, {"phase": "done"}) == "working"


def test_status_event_without_terminal_kind_stays_idle() -> None:
    """只有 warning 之类事件（无 started/finished）时保持 idle，不猜 working。"""
    state = _collect([_ev(1, 100, "N3", "node_warning", "experience_rejected")])["N3"]
    assert state.started_ts is None and state.last_kind is None
    assert _status("N3", state, None, None) == "idle"


# ---------------------------------------------------------------- _execution 四态语义

def test_execution_not_started_for_idle_or_missing_state() -> None:
    assert _execution(None, "idle") == "not_started"
    # 现状：没有节点状态就没有本次执行方式（即便 status 传 working 也按"未开始"）——
    # 这是既有语义，S4 只**复用**它，不改。未知 mode 才落到 unknown（见下一个用例）。
    assert _execution(None, "working") == "not_started"
    state = _collect([_ev(1, 1, "N3", "node_started", "running")])["N3"]
    assert _execution(state, "idle") == "not_started"


@pytest.mark.parametrize("mode,expected", [
    ("live", "real"), ("real", "real"), ("Real", "real"), (" live ", "real"),
    ("standin", "standin"), ("StandIn", "standin"),
    (None, "unknown"), ("", "unknown"), ("dry", "unknown"),
])
def test_execution_modes(mode: str | None, expected: str) -> None:
    detail = {"mode": mode} if mode is not None else {}
    state = _collect([_ev(1, 1, "N3", "node_started", "running"),
                      _ev(2, 2, "N3", "node_finished", "ok", detail)])["N3"]
    assert _execution(state, "done") == expected


def test_execution_last_mode_wins() -> None:
    """mode 取**最后**一条带 mode 的事件（旧 mode 不被后续无 mode 事件覆盖）。"""
    state = _collect([
        _ev(1, 1, "N3", "node_started", "running", {"mode": "standin"}),
        _ev(2, 2, "N3", "node_finished", "ok"),
    ])["N3"]
    assert state.mode == "standin"
    assert _execution(state, "done") == "standin"


# ---------------------------------------------------------------- _elapsed 语义（未知保持 None）

def test_elapsed_none_when_unknown() -> None:
    assert _elapsed(None, "idle", None) is None
    assert _elapsed(None, "idle", 100.0) is None
    only_finished = _collect([_ev(1, 10, "N3", "node_finished", "ok")])["N3"]
    assert _elapsed(only_finished, "done", 100.0) is None


def test_elapsed_done_uses_finished_and_ignores_now() -> None:
    state = _collect([_ev(1, 100, "N3", "node_started", "running"),
                      _ev(2, 112, "N3", "node_finished", "ok")])["N3"]
    assert _elapsed(state, "done", 999.0) == 12
    assert _elapsed(state, "done", None) == 12


def test_elapsed_working_uses_injected_now_only() -> None:
    state = _collect([_ev(1, 100, "N3", "node_started", "running")])["N3"]
    assert _elapsed(state, "working", 215.0) == 115
    assert _elapsed(state, "working", None) is None  # 没有注入 now ⇒ 不拿墙钟凑数


def test_elapsed_failed_without_finished_is_none() -> None:
    state = _collect([_ev(1, 100, "N3", "node_started", "running"),
                      _ev(2, 101, "N3", "node_failed", "failed", {"message": "boom"})])["N3"]
    assert _elapsed(state, "failed", 200.0) is None


def test_elapsed_never_negative() -> None:
    state = _collect([_ev(1, 100, "N3", "node_started", "running"),
                      _ev(2, 90, "N3", "node_finished", "ok")])["N3"]
    assert _elapsed(state, "done", None) == 0


# ---------------------------------------------------------------- _collect / _choose

def test_collect_normalizes_request_suffix_for_mode_only() -> None:
    """`N3_request` 归一到 `N3` 只为取 mode，不改变动作。"""
    states = _collect([_ev(1, 5, "N3_request", "node_request", "info", {"mode": "standin"})])
    assert set(states) == {"N3"}
    assert states["N3"].mode == "standin"
    assert states["N3"].last_kind is None  # 不是三类节点事件 ⇒ 不参与 last_*


def test_collect_keeps_first_started_and_last_terminal() -> None:
    state = _collect([
        _ev(1, 100, "N3", "node_started", "running"),
        _ev(2, 110, "N3", "node_started", "running"),   # 重复 started 不覆盖第一次
        _ev(3, 120, "N3", "node_finished", "ok"),
        _ev(4, 130, "N3", "node_finished", "failed"),   # 最后一次终态生效
    ])["N3"]
    assert state.started_ts == 100
    assert state.finished_ts == 130
    assert state.last_kind == "node_finished"
    assert state.failed is True


def test_choose_latest_node_or_first_declared() -> None:
    events = [_ev(1, 10, "N8", "node_started", "running"),
              _ev(2, 20, "N10", "node_started", "running")]
    agents = _by_role(build_agents(events, run_dir=None, now=25))
    assert agents["checker"]["active_node"] == "N10"
    assert agents["checker"]["status"] == "working"
    assert agents["checker"]["elapsed_s"] == 5
    assert _by_role(build_agents([], run_dir=None, now=0))["checker"]["active_node"] == "N8"


# ---------------------------------------------------------------- node_capabilities

def test_node_capabilities_none_for_host_nodes() -> None:
    """非模型角色节点（Host 确定性步骤）返回 None：不伪造能力结论。"""
    for node in ("N0", "N4", "N9", "N13", "N15"):
        assert node_capabilities(node, []) is None


def test_node_capabilities_reuses_card_implementation() -> None:
    events = [_ev(1, 10, "N11", "node_started", "running"),
              _ev(2, 20, "N11", "node_finished", "ok", {"mode": "standin"})]
    facts = node_capabilities("N11", events)
    card = _by_role(build_agents(events, run_dir=None, now=21))["guardian"]
    assert facts == card["capabilities"]
    assert facts == {"implemented": True, "dependencies_ready": None,
                     "execution": "standin", "verification_scope": None}


def test_node_capabilities_ignores_other_nodes_events() -> None:
    events = [_ev(1, 10, "N3", "node_started", "running"),
              _ev(2, 20, "N3", "node_finished", "ok", {"mode": "live"})]
    assert node_capabilities("N6", events)["execution"] == "not_started"
