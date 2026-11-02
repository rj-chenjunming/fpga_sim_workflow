"""S3 · 用例判据人签覆写 HTTP 端点（SPEC-REV-20 §4/§7/§9）。

覆盖口径（不读实现也能判）：
- §4 拒绝矩阵 **逐条** 403（1 actor / 2 reason / 3 用例不在台账 / 4 状态不符 /
  5 机器原因缺失·用例缺失·passed≠false·reasons 空 / 6 run 非等待闸门 / 7 批量全有或全无）；
- 请求体形状错 ⇒ 400（cases 空/非数组/action 不在枚举）；
- 台账损坏/锚复核失败（kb rc=4）⇒ 409（detail.reason 写明复核失败）；
- 200 路径 ⇒ 状态真变 `已验证通过`、投影同时给「机器原判 + 人签豁免」、
  run 进度流里出现可读回的 `case_override` 事件；
- **拒绝时台账一字节不动**（md5 前后相等）。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from host import paths as P
from host.progress import ProgressLog
from services import api as api_mod

PENDING = "已修订待验"
PASS = "已验证通过"
HUMAN = "human:chenjunming"
REASON = "期望值来自旧文档条目；实测值与本变预期一致，属期望过期"


# ---------------------------------------------------------------- 夹具（真实 kb CLI 准备前置）


def _kb(*args: str) -> subprocess.CompletedProcess:
    """调**真实** kb CLI 准备台账（唯一写者；测试不自己拼 ledger JSON）。"""
    return subprocess.run(
        [sys.executable, "-B", str(P.KB_TOOLS / "case_state.py"), *args],
        cwd=str(P.REPO_ROOT), capture_output=True, text=True,
    )


def _new_run_id() -> str:
    """run_id 必须匹配 kb schema 的 `^RUN-[0-9]{8}-[0-9]{6}$`（每测试唯一）。"""
    return f"RUN-20261102-{uuid.uuid4().int % 1_000_000:06d}"


def _machine_doc(run_id: str, cases: tuple[str, ...]) -> dict[str, Any]:
    """`n10_cases.json` 的契约形状（S2 产物；服务/CLI 只读它）。"""
    return {
        "schema": "loop/n10_cases",
        "run_id": run_id,
        "created_at": "2026-11-02T13:00:00+0800",
        "criterion": "聚合判据 = 各用例 I3 判据的合取（含印记三向一致）",
        "cases": {
            case: {
                "case": case,
                "passed": False,
                "criterion": "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致",
                "reasons": [f"印记 N6_pcie_test_{case} 三向不一致：['value_matches_expected']"],
                "counts": {"koutou1": {"value": 0, "zero": True},
                           "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}, "zero": True},
                           "both_zero": True},
                "imprints": {f"N6_pcie_test_{case}": {
                    "consistent": False,
                    "checks": {"value_matches_expected": False}}},
                "evidence": {"path": f"evidence/20261102-130000_{case}_1_run.log",
                             "md5": "a" * 32, "bytes": 123456},
            }
            for case in cases
        },
    }


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


@pytest.fixture
def run(tmp_path: Path) -> SimpleNamespace:
    """本轮 run 目录：真实台账（两例 `已修订待验`）+ 真实形状的机器原因件。"""
    run_id = _new_run_id()
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    ledger = run_dir / "case_states.json"
    res = _kb("init", "--run", run_id, "--state-file", str(ledger))
    assert res.returncode == 0, res.stderr
    for case in ("tc_rtc_05", "tc_rtc_10"):
        res = _kb("set", "--run", run_id, "--state-file", str(ledger),
                  "--case", case, "--state", PENDING, "--note", "N10 判据未通过 ⇒ 待验")
        assert res.returncode == 0, res.stderr
    machine = run_dir / "n10_cases.json"
    machine.write_text(json.dumps(_machine_doc(run_id, ("tc_rtc_05", "tc_rtc_10")),
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    return SimpleNamespace(run_id=run_id, run_dir=run_dir, ledger=ledger,
                           machine=machine, tmp_path=tmp_path)


def _client(monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, *,
            status: str = "waiting_gate") -> TestClient:
    doc = SimpleNamespace(run_dir=str(run.run_dir), status=status, pending_interrupt=None)

    class FakeManager:
        def __init__(self) -> None:
            self.docs = {run.run_id: doc}

    monkeypatch.setattr(api_mod, "_manager", lambda: FakeManager())
    # 不用 `with`（不触发 lifespan）：本文件只验路由/状态码映射。
    return TestClient(api_mod.app)


def _post(client: TestClient, run: SimpleNamespace, **payload: Any):
    body: dict[str, Any] = {"action": "pass", "cases": ["tc_rtc_05"], "actor": HUMAN,
                            "reason": REASON}
    body.update(payload)
    return client.post(f"/api/runs/{run.run_id}/cases/override", json=body)


def _reasons_in(resp) -> str:
    """403 体的全部人读文本（error + blockers[].message）拼起来，便于断言"哪一条"。"""
    detail = resp.json().get("detail") or {}
    parts = [str(detail.get("error") or "")]
    for blocker in detail.get("blockers") or []:
        if isinstance(blocker, dict):
            parts.extend(str(blocker.get(k) or "") for k in ("title", "message", "code"))
    return " | ".join(p for p in parts if p)


def _ledger(run: SimpleNamespace) -> dict[str, Any]:
    return json.loads(run.ledger.read_text(encoding="utf-8"))


def _state_of(run: SimpleNamespace, case: str) -> str:
    for item in _ledger(run)["cases"]:
        if item.get("case") == case:
            return str(item.get("state"))
    raise AssertionError(f"台账里没有 {case}")


def _events(run_id: str) -> list[dict[str, Any]]:
    return [e for e in ProgressLog(P.EVENTS_DIR, run_id).read()
            if e.get("kind") == "case_override"]


# ================================================================ 200 路径


def test_override_pass_returns_200_projection_and_readable_event(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)

    resp = _post(client, run)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True and body["action"] == "pass"
    assert body["results"] == [{"case": "tc_rtc_05", "state": PASS}]
    assert body["warnings"] == []

    # 台账真变（唯一写者是 kb CLI：overrides 链 + state）
    ledger = _ledger(run)
    assert _md5(run.ledger) != before, "200 路径必须真的落盘"
    entry = next(c for c in ledger["cases"] if c["case"] == "tc_rtc_05")
    assert entry["state"] == PASS
    assert len(entry["overrides"]) == 1
    record = entry["overrides"][0]
    assert record["action"] == "pass" and record["actor"] == HUMAN
    assert record["prev_state"] == PENDING and record["machine"]["passed"] is False
    assert record["record_sha256"]

    # 投影必须同时给「机器原判 + 人签豁免」（O-5）
    waivers = body["case_waivers"]
    assert waivers["count"] == 1
    item = waivers["cases"][0]
    assert item["case"] == "tc_rtc_05" and item["action"] == "pass"
    assert item["actor"] == HUMAN and item["reason"] == REASON and item["decided_at"]
    assert item["prev_state"] == PENDING
    assert item["machine"]["passed"] is False
    assert item["machine"]["reasons"], "机器原判原因必须随豁免一起下发"

    # 事件进 run 进度流且可读回（§9）
    events = _events(run.run_id)
    assert len(events) == 1, events
    event = events[0]
    assert event["status"] == "pass"
    detail = event["detail"]
    assert detail["action"] == "pass" and detail["actor"] == HUMAN
    assert detail["reason"] == REASON and detail["cases"] == ["tc_rtc_05"]
    assert detail["machine"]["tc_rtc_05"]["passed"] is False
    assert detail["summary"], "事件必须带一行可读 summary（与 gate_decided 同风格）"
    assert event["refs"], "事件必须带 refs（台账/机器原因件）"


def test_override_batch_pass_then_revoke_appends_never_rewrites(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    client = _client(monkeypatch, run)
    resp = _post(client, run, cases=["tc_rtc_05", "tc_rtc_10"])
    assert resp.status_code == 200, resp.text
    assert [r["state"] for r in resp.json()["results"]] == [PASS, PASS]
    assert resp.json()["case_waivers"]["count"] == 2

    resp = _post(client, run, action="revoke", cases=["tc_rtc_05", "tc_rtc_10"])
    assert resp.status_code == 200, resp.text
    assert [r["state"] for r in resp.json()["results"]] == [PENDING, PENDING]
    assert resp.json()["case_waivers"]["count"] == 0
    ledger = _ledger(run)
    for case in ("tc_rtc_05", "tc_rtc_10"):
        entry = next(c for c in ledger["cases"] if c["case"] == case)
        assert [o["action"] for o in entry["overrides"]] == ["pass", "revoke"], "撤销只能追加"
    assert len(_events(run.run_id)) == 2


# ================================================================ §4 拒绝矩阵（403，台账不动）


@pytest.mark.parametrize("actor", ["model:gpt", "host:loop", "chenjunming", "human:", ""])
def test_matrix_1_actor_must_be_human_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, actor: str) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, actor=actor)
    assert resp.status_code == 403, resp.text
    assert "§4-1" in _reasons_in(resp), _reasons_in(resp)
    assert _md5(run.ledger) == before, "拒绝 ⇒ 台账一字节不动"


@pytest.mark.parametrize("reason", ["", "   ", "\n\t"])
def test_matrix_2_blank_reason_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, reason: str) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, reason=reason)
    assert resp.status_code == 403, resp.text
    assert "§4-2" in _reasons_in(resp)
    assert _md5(run.ledger) == before


def test_matrix_3_case_not_in_ledger_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, cases=["tc_not_there"])
    assert resp.status_code == 403, resp.text
    assert "§4-3" in _reasons_in(resp)
    assert _md5(run.ledger) == before


def test_matrix_4_state_mismatch_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    res = _kb("set", "--run", run.run_id, "--state-file", str(run.ledger),
              "--case", "tc_rtc_10", "--state", "未改", "--note", "本轮未改")
    assert res.returncode == 0, res.stderr
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, cases=["tc_rtc_10"])
    assert resp.status_code == 403, resp.text
    assert "§4-4" in _reasons_in(resp)
    assert _md5(run.ledger) == before

    # 单一判据：端点拒绝理由与只读投影**同一函数**算出（界面据此禁用按钮，不会两套口径）
    from services import contracts

    proj = contracts.case_override_view(run.run_dir, run_status="waiting_gate")
    assert proj["enabled"] is True
    assert proj["cases"]["tc_rtc_10"]["actions"]["pass"]["available"] is False
    assert "§4-4" in proj["cases"]["tc_rtc_10"]["actions"]["pass"]["blocked_reason"]
    assert proj["cases"]["tc_rtc_05"]["actions"]["pass"]["available"] is True


@pytest.mark.parametrize("variant", ["missing_file", "missing_case", "passed_true", "no_reasons"])
def test_matrix_5_machine_reasons_required_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, variant: str) -> None:
    doc = _machine_doc(run.run_id, ("tc_rtc_05", "tc_rtc_10"))
    if variant == "missing_file":
        run.machine.unlink()
    elif variant == "missing_case":
        doc["cases"].pop("tc_rtc_05")
    elif variant == "passed_true":
        doc["cases"]["tc_rtc_05"]["passed"] = True
    elif variant == "no_reasons":
        doc["cases"]["tc_rtc_05"]["reasons"] = []
    if variant != "missing_file":
        run.machine.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run)
    assert resp.status_code == 403, resp.text
    if variant == "missing_file":
        # 规格 §3.2/§6.1 固定文案：旧轮机器原因未留存 ⇒ 不能盲签
        assert "该轮机器原因未留存（早于覆写功能），不能盲签" in _reasons_in(resp), _reasons_in(resp)
    else:
        assert "§4-5" in _reasons_in(resp), _reasons_in(resp)
    assert _md5(run.ledger) == before


@pytest.mark.parametrize("status", ["running", "waiting_job", "finished", "failed"])
def test_matrix_6_run_not_waiting_gate_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, status: str) -> None:
    client = _client(monkeypatch, run, status=status)
    before = _md5(run.ledger)
    resp = _post(client, run)
    assert resp.status_code == 403, resp.text
    assert "§4-6" in _reasons_in(resp), _reasons_in(resp)
    assert status in _reasons_in(resp), "拒绝必须说明当前 run 状态"
    assert _md5(run.ledger) == before


def test_matrix_7_batch_is_all_or_nothing_403(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, cases=["tc_rtc_05", "tc_not_there"])
    assert resp.status_code == 403, resp.text
    assert "§4-3" in _reasons_in(resp)
    assert _md5(run.ledger) == before, "批量里任一例不满足 ⇒ 整批不写"
    assert _state_of(run, "tc_rtc_05") == PENDING
    assert not _events(run.run_id), "被拒不得留成功事件"


# ================================================================ 400 / 404 / 409


@pytest.mark.parametrize("payload", [
    {"action": "maybe"},
    {"cases": []},
    {"cases": "tc_rtc_05"},
    {"cases": [123]},
])
def test_bad_request_shape_400(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace, payload: dict[str, Any]) -> None:
    client = _client(monkeypatch, run)
    before = _md5(run.ledger)
    resp = _post(client, run, **payload)
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["error"]
    assert _md5(run.ledger) == before


def test_unknown_run_404(monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    client = _client(monkeypatch, run)
    resp = client.post("/api/runs/RUN-NOT-EXIST/cases/override",
                       json={"action": "pass", "cases": ["tc_rtc_05"], "actor": HUMAN,
                             "reason": REASON})
    assert resp.status_code == 404


def test_broken_anchor_409_with_recheck_reason(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    """kb rc=4（锚复核失败）⇒ 409，detail.reason 写明哪条复核失败；台账不动。"""
    client = _client(monkeypatch, run)
    assert _post(client, run).status_code == 200
    ledger = _ledger(run)
    entry = next(c for c in ledger["cases"] if c["case"] == "tc_rtc_05")
    entry["overrides"][0]["reason"] = "被篡改的理由（record_sha256 不再匹配）"
    run.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    before = _md5(run.ledger)

    resp = _post(client, run, action="revoke")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "record_sha256" in detail["reason"], detail
    assert _md5(run.ledger) == before, "锚复核失败 ⇒ 拒绝追加（台账不动）"


def test_corrupt_ledger_409_not_disguised_as_rule_violation(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    """台账不可解析 ⇒ 409（"无法判定"），不得伪装成 §4-3「用例不在台账」的 403。"""
    run.ledger.write_text("{ not json", encoding="utf-8")
    before = _md5(run.ledger)
    client = _client(monkeypatch, run)

    resp = _post(client, run)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "不可解析" in detail["reason"], detail
    assert _md5(run.ledger) == before


def test_ledger_identity_mismatch_409(
        monkeypatch: pytest.MonkeyPatch, run: SimpleNamespace) -> None:
    """台账 run_id ≠ 请求 run_id（别轮的台账）⇒ 409，不得当成本轮规则不满足。"""
    ledger = _ledger(run)
    ledger["run_id"] = "RUN-20261102-999999"
    run.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    before = _md5(run.ledger)
    client = _client(monkeypatch, run)

    resp = _post(client, run)

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "身份错位" in detail["reason"] and "RUN-20261102-999999" in detail["reason"]
    assert _md5(run.ledger) == before
