"""HTTP 契约测试（TestClient，无需外部服务）。

覆盖前端的全部接口，并把两条**必须在提交前**发生的拒绝固化下来：
- I6 actor 非 human ⇒ 403，且闸门不得变成已签；
- 非法枚举 ⇒ 400，且**不消耗闸门中断**（闸门仍可用）。
  实测踩过：阻断若发生在恢复之后，一次误选会把执行打成 failed
  （`self_resume_limit_reached`），闸门从此不可用。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from host import gate_authority as GA
from services.api import app

HUMAN = "human:api-test"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _new_run(client: TestClient, **kw) -> str:
    body = {"baseline": "v0", "mode": "drill"}
    body.update(kw)
    r = client.post("/api/runs", json=body)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def _wait_interrupt(client: TestClient, rid: str, prefix: str, *, timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = client.get(f"/api/runs/{rid}").json()
        if ((view.get("pending_interrupt") or {}).get("id") or "").startswith(prefix):
            return view
        if view.get("status") == "failed":
            raise AssertionError(f"运行失败：{view}")
        time.sleep(0.3)
    raise AssertionError(f"未在 {timeout}s 内到达 {prefix}")


def test_health_and_static_ui(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["ok"] is True
    assert health["agently"].startswith("4.1.4")
    # SPEC-02 §9：事件 kind 白名单的唯一权威经 /api/health 下发（前端不手抄）
    from host.progress import ALLOWED_KINDS

    assert health["event_kinds"] == sorted(ALLOWED_KINDS)
    html = client.get("/").text
    assert "<!DOCTYPE html>" in html
    assert "http://" not in html and "https://" not in html, "前端不得有外链"


def test_gate_options_come_from_authority(client: TestClient) -> None:
    """界面按钮必须由服务端下发，且与 `kb_lib.GATE_DECISIONS` 逐值一致。"""
    rid = _new_run(client)
    view = _wait_interrupt(client, rid, "G1_diff_confirm")
    options = view["gate_options"]
    assert set(options) == set(GA.gate_ids())
    for gate, opts in options.items():
        assert [o["value"] for o in opts] == list(GA.actionable_decisions(gate))
    material = (view["pending_interrupt"] or {}).get("payload") or {}
    assert [o["value"] for o in material["decision_options"]] == list(
        GA.actionable_decisions("G1_diff_confirm")
    )


def test_rejections_happen_before_consuming_the_interrupt(client: TestClient) -> None:
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")

    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "confirmed", "actor": "model:gpt-x", "reason": "越权"})
    assert r.status_code == 403
    assert client.get(f"/api/runs/{rid}").json()["status"] == "waiting_gate"

    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "lgtm", "actor": HUMAN, "reason": "非法枚举"})
    assert r.status_code == 400
    assert "权威枚举" in r.json()["detail"]["error"]
    assert client.get(f"/api/runs/{rid}").json()["status"] == "waiting_gate"

    # 闸门仍然可用
    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "confirmed", "actor": HUMAN, "reason": "已核对"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_i4_blocks_full_now_without_killing_the_gate(client: TestClient) -> None:
    """I4 阻断必须在提交前发生：误选之后闸门依旧可决策。"""
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                json={"decision": "confirmed", "actor": HUMAN, "reason": "ok"})
    _wait_interrupt(client, rid, "G2_report_accept")
    client.post(f"/api/runs/{rid}/gates/G2_report_accept/decision",
                json={"decision": "accept", "actor": HUMAN, "reason": "ok"})
    view = _wait_interrupt(client, rid, "G3_regression_decision")

    r = client.post(f"/api/runs/{rid}/gates/G3_regression_decision/decision",
                    json={"decision": "full_now", "actor": HUMAN, "reason": "试越 I4"})
    assert r.status_code == 403
    assert "I4" in r.json()["detail"]["error"]
    after = client.get(f"/api/runs/{rid}").json()
    assert after["status"] == "waiting_gate"
    assert ((after.get("pending_interrupt") or {}).get("id") or "").startswith("G3")

    # 旧的自造值必须被权威枚举拒绝
    r = client.post(f"/api/runs/{rid}/gates/G3_regression_decision/decision",
                    json={"decision": "full_regression", "actor": HUMAN, "reason": "自造值"})
    assert r.status_code == 400
    assert "full_now" in r.json()["detail"]["error"]

    r = client.post(f"/api/runs/{rid}/gates/G3_regression_decision/decision",
                    json={"decision": "milestone_only", "actor": HUMAN, "reason": "I4 未清零"})
    assert r.status_code == 200


def test_dual_counts_and_e2_are_exposed(client: TestClient) -> None:
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                json={"decision": "confirmed", "actor": HUMAN, "reason": "ok"})
    view = _wait_interrupt(client, rid, "G2_report_accept")

    counts = view["counts"]
    assert counts["koutou1"]["value"] > 0 and counts["koutou1"]["zero"] is False
    assert counts["koutou2"]["value"]["UVM_ERROR"] == 0 and counts["koutou2"]["zero"] is True
    assert counts["both_zero"] is False
    assert view["can"]["judge_pass"] is False
    assert {b["code"] for b in view["blockers"]} >= {"I3_KOUTOU1_NONZERO", "I4_CONFLICTS_UNCLEARED"}
    assert view["evidence"]["imprints"]["N6_FPGA_DATE_PCIE"]["consistent"] is True

    ex = client.get(f"/api/runs/{rid}/evidence/exists",
                    params={"ref": "kb/runs/RUN-20261015-120626/evidence/archive"}).json()
    assert ex["exists"] is False and "E-2" in (ex.get("note") or "")


def test_events_endpoint_is_whitelisted(client: TestClient) -> None:
    from host.progress import ALLOWED_KINDS

    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    events = client.get(f"/api/runs/{rid}/events", params={"since_seq": 0}).json()["events"]
    assert events
    assert {e["kind"] for e in events} <= ALLOWED_KINDS
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
