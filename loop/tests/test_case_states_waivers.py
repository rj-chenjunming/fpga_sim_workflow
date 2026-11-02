"""S3 · 用例态投影里的「人签豁免 + 机器原判」（SPEC-REV-20 §6）。

断言口径（不读实现也能判）：
- 投影在豁免后**同时**给出机器原判（passed/criterion/reasons/evidence）与人签记录
  （actor/reason/decided_at/action/prev_state），并给出汇总计数（豁免数 / 待验数）；
- `case_failures` 来自 `n10_cases.json`（S2 产物的唯一读侧实现 `n10_semantics.load_cases`）；
  旧 run 缺件 ⇒ `present=false` + `missing` 明说缺哪件，**不**解析 `n10_reconcile.md`；
- 豁免后 I2 blocker 自动消失（判据仍是 `state`，没有第二套判据）；
- N16 前置用 `kb/tools/case_state.py check --json` 的 `info.waived` 与「无 I2 问题」证明，
  **不**在服务层重写 I2；
- G2 `accept` 前置**不变**：报告 `not_passed` 时仍 `requires_reason=true`。
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from host import paths as P
from host.progress import ProgressLog
from services import case_override, contracts
from services.contracts import KbSources

PENDING = "已修订待验"
PASS = "已验证通过"
HUMAN = "human:chenjunming"
REASON = "期望值来自旧文档条目；实测值与本变预期一致，属期望过期"
MACHINE_REASON = "印记 N6_pcie_test_tc_rtc_05 三向不一致：['value_matches_expected']"


def _kb(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(P.KB_TOOLS / "case_state.py"), *args],
        cwd=str(P.REPO_ROOT), capture_output=True, text=True,
    )


def _new_run_id() -> str:
    """run_id 必须匹配 kb schema 的 `^RUN-[0-9]{8}-[0-9]{6}$`（每测试唯一）。"""
    return f"RUN-20261102-{uuid.uuid4().int % 1_000_000:06d}"


def _provision(tmp_path: Path, cases: tuple[str, ...] = ("tc_rtc_05", "tc_rtc_10")) -> SimpleNamespace:
    run_id = _new_run_id()
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    ledger = run_dir / "case_states.json"
    assert _kb("init", "--run", run_id, "--state-file", str(ledger)).returncode == 0
    for case in cases:
        res = _kb("set", "--run", run_id, "--state-file", str(ledger),
                  "--case", case, "--state", PENDING, "--note", "N10 判据未通过 ⇒ 待验")
        assert res.returncode == 0, res.stderr
    machine = run_dir / "n10_cases.json"
    machine.write_text(json.dumps({
        "schema": "loop/n10_cases",
        "run_id": run_id,
        "created_at": "2026-11-02T13:00:00+0800",
        "criterion": "聚合判据 = 各用例 I3 判据的合取（含印记三向一致）",
        "cases": {
            case: {
                "case": case,
                "passed": False,
                "criterion": "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致",
                "reasons": [MACHINE_REASON],
                "counts": {"koutou1": {"value": 0, "zero": True},
                           "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}, "zero": True},
                           "both_zero": True},
                "imprints": {"N6_pcie_test_tc_rtc_05": {
                    "consistent": False, "checks": {"value_matches_expected": False}}},
                "evidence": {"path": f"evidence/20261102-130000_{case}_1_run.log",
                             "md5": "a" * 32, "bytes": 123456},
            }
            for case in cases
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return SimpleNamespace(run_id=run_id, run_dir=run_dir, ledger=ledger,
                           machine=machine, tmp_path=tmp_path)


def _waive(run: SimpleNamespace, cases: list[str], *, action: str = "pass") -> dict[str, Any]:
    return case_override.submit(
        run_id=run.run_id, run_dir=run.run_dir, run_status="waiting_gate",
        payload={"action": action, "cases": cases, "actor": HUMAN, "reason": REASON},
        progress=ProgressLog(run.tmp_path / "events", run.run_id),
    )


def _kb_sources(tmp_path: Path) -> KbSources:
    return KbSources.from_workspace(tmp_path / "ws")


def _counts_zero() -> dict[str, Any]:
    return {"koutou1": {"label": "口径一", "value": 0, "zero": True},
            "koutou2": {"label": "口径二", "value": {"UVM_ERROR": 0, "UVM_FATAL": 0},
                        "zero": True, "uvm_summary_present": True},
            "both_zero": True}


# ================================================================ 台账读模型


def test_case_states_view_exposes_waiver_and_machine_verdict(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    _waive(run, ["tc_rtc_05"])

    view = contracts.case_states_view(run.run_dir)
    waiver = next(c for c in view["cases"] if c["case"] == "tc_rtc_05")
    plain = next(c for c in view["cases"] if c["case"] == "tc_rtc_10")

    assert waiver["state"] == PASS
    assert waiver["waived"] is True
    assert waiver["waiver"]["actor"] == HUMAN
    assert waiver["waiver"]["reason"] == REASON
    assert waiver["waiver"]["action"] == "pass"
    assert waiver["waiver"]["prev_state"] == PENDING
    assert waiver["waiver"]["decided_at"]
    # O-5：机器原判与人签豁免同屏，机器结论不被改写
    machine = waiver["waiver"]["machine"]
    assert machine["passed"] is False
    assert machine["reasons"] == [MACHINE_REASON]
    assert machine["criterion"]
    assert machine["evidence"]["md5"] == "a" * 32

    assert plain["waived"] is False and plain["waiver"] is None
    assert plain["state"] == PENDING


def test_case_waivers_view_counts_waived_and_pending(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    _waive(run, ["tc_rtc_05"])

    view = contracts.case_waivers_view(run.run_dir)

    assert view["count"] == 1 and view["count_waived"] == 1
    assert [c["case"] for c in view["cases"]] == ["tc_rtc_05"]
    assert view["pending_count"] == 1
    assert view["pending"] == ["tc_rtc_10"]
    assert view["present"] is True and view["path"].endswith("case_states.json")


# ================================================================ 机器原因（case_failures）


def test_case_failures_view_copies_n10_cases(tmp_path: Path) -> None:
    run = _provision(tmp_path)

    view = contracts.case_failures_view(run.run_dir)

    assert view["present"] is True and view["missing"] is None
    assert view["count"] == 2
    item = view["cases"]["tc_rtc_05"]
    assert item["passed"] is False
    assert item["reasons"] == [MACHINE_REASON], "原因必须原文，不翻译不截断"
    assert item["criterion"]
    assert item["evidence"]["path"].endswith("_run.log")
    assert item["evidence"]["md5"] == "a" * 32
    assert item["counts"]["koutou1"]["value"] == 0
    assert item["imprints"]["N6_pcie_test_tc_rtc_05"]["consistent"] is False


def test_case_failures_view_missing_for_old_run(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    run.machine.unlink()
    # 旧 run 只有对账 md：**不得**反解析出第二套判据
    (run.run_dir / "n10_reconcile.md").write_text(
        "# N10 结果对账\n\n- `tc_rtc_05`：口径一=0 ⇒ passed=False（三向不一致）\n",
        encoding="utf-8")

    view = contracts.case_failures_view(run.run_dir)

    assert view["present"] is False
    assert view["missing"] == "n10_cases.json"
    assert view["cases"] == {}


# ================================================================ 闸门材料 / run_view


def test_gate_material_g2_has_waivers_and_failures_and_no_i2(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    _waive(run, ["tc_rtc_05"])

    material = contracts.gate_material(
        gate="G2_report_accept", run_dir=run.run_dir, counts=_counts_zero(),
        kb=_kb_sources(tmp_path), pending_interrupt=None, run_status="waiting_gate",
    )

    assert material["case_waivers"]["count"] == 1
    # 可签性判定必须随材料下发（run 处于等待闸门 ⇒ enabled；前端不得自判）
    assert material["case_override"]["enabled"] is True
    assert material["case_override"]["blocked_reason"] is None
    assert material["case_waivers"]["cases"][0]["machine"]["passed"] is False
    assert material["case_failures"]["present"] is True
    assert material["case_failures"]["cases"]["tc_rtc_05"]["reasons"] == [MACHINE_REASON]
    # 只豁免一例 ⇒ I2 仍拦另一例（判据仍是 state，没有第二套判据）
    i2 = next(b for b in material["blockers"] if b["code"] == "I2_CASES_PENDING")
    assert i2["items"] == ["tc_rtc_10"], i2

    # 两例都豁免 ⇒ I2 自动消失
    _waive(run, ["tc_rtc_10"])
    material = contracts.gate_material(
        gate="G2_report_accept", run_dir=run.run_dir, counts=_counts_zero(),
        kb=_kb_sources(tmp_path), pending_interrupt=None, run_status="waiting_gate",
    )
    codes = [b["code"] for b in material["blockers"]]
    assert "I2_CASES_PENDING" not in codes, codes
    assert material["case_states"]["pending_own"] == []
    assert material["case_waivers"]["count"] == 2


def test_run_view_includes_case_waivers(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    _waive(run, ["tc_rtc_05"])

    view = contracts.run_view(
        run_doc={"run_id": run.run_id, "run_dir": str(run.run_dir),
                 "status": "waiting_gate", "mode": "real", "baseline": "v0"},
        kb=_kb_sources(tmp_path), slot_status={}, job=None, evidence=None, events=[],
    )

    assert view["case_waivers"]["count"] == 1
    assert view["case_waivers"]["cases"][0]["case"] == "tc_rtc_05"
    assert view["case_waivers"]["cases"][0]["machine"]["passed"] is False
    # 既有字段不变（追加只增键）
    assert view["case_states"]["count"] == 2
    # 「能不能签」由服务端单一函数下发（run_view 带 run 状态）
    assert view["case_override"]["enabled"] is True
    assert view["case_override"]["cases"]["tc_rtc_10"]["actions"]["pass"]["available"] is True
    assert view["case_override"]["cases"]["tc_rtc_10"]["machine_present"] is True


# ================================================================ 可签性投影（服务端单一判据）


def test_case_override_projection_enabled_and_per_case(tmp_path: Path) -> None:
    run = _provision(tmp_path)

    proj = contracts.case_override_view(run.run_dir, run_status="waiting_gate")

    assert proj["enabled"] is True and proj["blocked_reason"] is None
    entry = proj["cases"]["tc_rtc_05"]
    assert entry["state"] == PENDING and entry["machine_present"] is True
    assert entry["actions"]["pass"] == {"available": True, "blocked_reason": None}
    # revoke 维度：当前待验（机器没判过它失败以外…）⇒ 撤销不可用（§4-4）
    assert entry["actions"]["revoke"]["available"] is False
    assert "§4-4" in entry["actions"]["revoke"]["blocked_reason"]

    # 豁免后：pass 不可再签、revoke 可签（逐动作维度）
    _waive(run, ["tc_rtc_05"])
    proj = contracts.case_override_view(run.run_dir, run_status="waiting_gate")
    entry = proj["cases"]["tc_rtc_05"]
    assert entry["state"] == PASS
    assert entry["actions"]["pass"]["available"] is False
    assert "§4-4" in entry["actions"]["pass"]["blocked_reason"]
    assert entry["actions"]["revoke"] == {"available": True, "blocked_reason": None}


def test_case_override_projection_blocked_when_not_waiting_or_missing_machine(
        tmp_path: Path) -> None:
    run = _provision(tmp_path)

    running = contracts.case_override_view(run.run_dir, run_status="running")
    assert running["enabled"] is False
    assert "§4-6" in running["blocked_reason"] and "running" in running["blocked_reason"]
    for entry in running["cases"].values():
        assert entry["actions"]["pass"]["available"] is False
        assert entry["actions"]["revoke"]["available"] is False

    run.machine.unlink()
    missing = contracts.case_override_view(run.run_dir, run_status="waiting_gate")
    assert missing["enabled"] is False
    # 规格 §6.1 固定文案（旧轮不能盲签）
    assert missing["blocked_reason"] == contracts.NO_MACHINE_REASON
    entry = missing["cases"]["tc_rtc_05"]
    assert entry["machine_present"] is False
    assert entry["actions"]["pass"]["available"] is False
    assert contracts.NO_MACHINE_REASON in entry["actions"]["pass"]["blocked_reason"]

    # run 状态未知（调用方没下发）⇒ 不猜：显式禁用
    unknown = contracts.case_override_view(run.run_dir)
    assert unknown["enabled"] is False and "未下发" in unknown["blocked_reason"]


# ================================================================ N16 前置（不重写 I2）


def test_n16_check_ledger_after_waiver_has_no_i2_problem(tmp_path: Path) -> None:
    run = _provision(tmp_path)
    _waive(run, ["tc_rtc_05"])
    _waive(run, ["tc_rtc_10"])

    proc = _kb("check", "--run", run.run_id, "--state-file", str(run.ledger), "--json")
    assert proc.returncode == 0, proc.stderr
    info = json.loads(proc.stdout)

    assert info["waived"] == ["tc_rtc_05", "tc_rtc_10"], info
    assert info["pending"] == []
    assert not any("I2" in p or PENDING in p for p in info["problems"]), info["problems"]


# ================================================================ G2 accept 前置不变


def test_g2_accept_still_requires_reason_for_not_passed() -> None:
    options = contracts.gate_decision_options("G2_report_accept", claimed_verdict="not_passed")
    accept = next(o for o in options if o["value"] == "accept")
    assert accept["requires_reason"] is True, "SPEC-REV-12 方案 D：not_passed 时 accept 仍须理由"
    options_passed = contracts.gate_decision_options("G2_report_accept", claimed_verdict="passed")
    accept_passed = next(o for o in options_passed if o["value"] == "accept")
    assert accept_passed["requires_reason"] is False
