"""S2 · N10 落盘 `<run_dir>/n10_cases.json`（SPEC-REV-20 §3.2）。

设计纪律（断言不看源码也能判）：
- **只搬运**：逐例 `passed/criterion/reasons/counts/imprints` 与 `n9_result.cases[*]` 的既有值**完全相等**；
- **不重算**：日志内容与搬运值相反时，产物仍写机器原判（Host 不重新判 pass/fail，不改机器结论 O-1）；
- **证据现算**：`evidence.md5/bytes` 由 Host 落盘时对权威 run.log 计算；文件缺失 ⇒ 显式 `None`，不编造；
- **失败显式**：写盘失败 ⇒ `n10_cases_written=False` + `warning` 事件，不抛异常、不静默吞；
- **旧 run**：无该件时读侧显式 `missing`，不解析 `n10_reconcile.md`（不做第二套解析）；
- `host_steps.ARTIFACTS` 登记 `n10_cases.json`。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.chunks import host_steps, model_steps, n10_semantics
from workflows.context import RunCtx

RUN_ID = "RUN-20261102-120000"

_CURRENT_CTX: Any = None


class FakeData:
    """最小 TriggerFlow 状态替身（只实现节点用到的接口）。"""

    def __init__(self, *, state: dict[str, Any] | None = None) -> None:
        assert _CURRENT_CTX is not None, "测试未设置当前 RunCtx"
        self.state = dict(state or {})
        self.resources = {"loop_ctx": _CURRENT_CTX}
        self.is_resume = False
        self.resume = None
        self.emitted: list[tuple[str, Any]] = []

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        return self.resources[key]

    async def async_emit(self, event: str, payload: Any) -> None:
        self.emitted.append((event, payload))


@pytest.fixture
def kb_root(tmp_path: Path) -> Path:
    root = tmp_path / "kb"
    (root / "conflicts").mkdir(parents=True)
    (root / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []},
                   ensure_ascii=False), encoding="utf-8")
    return root


def _ctx(tmp_path: Path, kb_root: Path, *, mode: str = "real",
         fixture: Path | None = None) -> RunCtx:
    global _CURRENT_CTX
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = RunCtx(
        run_id=RUN_ID, run_dir=run_dir, mode=mode, scenario="happy",
        kb=KbSources.from_workspace(kb_root),
        progress=ProgressLog(tmp_path / "events", RUN_ID),
        fixture=fixture or (tmp_path / "fixture"),
    )
    _CURRENT_CTX = ctx
    if mode == "drill":
        ctx.fixture.mkdir(parents=True, exist_ok=True)
    return ctx


def _write_log(ctx: RunCtx, name: str, text: str) -> Path:
    evidence = ctx.run_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    path = evidence / name
    path.write_text(text, encoding="utf-8")
    return path


#: 与日志内容**相反**的机器原判：日志"看起来通过"，n9 判不通过 ⇒ 产物必须照抄 n9（证明不重算）。
_PASSING_LOG = "UVM Report Summary\nUVM_ERROR :    0\nUVM_FATAL :    0\n"


def _machine_out(log: Path, *, passed: bool = False) -> dict[str, Any]:
    """`n9_result` 形状的最小夹具（字段全部来自既有 N9 聚合）。"""
    return {
        "run_id": RUN_ID,
        "verdict": {"passed": passed,
                    "criterion": "聚合判据 = 各用例 I3 判据的合取（含印记三向一致）"},
        "cases": {
            "tc_rtc_05": {
                "present": True,
                "path": str(log),
                "has_report_summary": True,
                "counts": {
                    "koutou1": {"label": "口径一", "value": 3, "zero": False},
                    "koutou2": {"label": "口径二", "value": {"UVM_ERROR": 0, "UVM_FATAL": 0},
                                "zero": True, "uvm_summary_present": True},
                    "both_zero": False,
                },
                "imprints": {
                    "N6_pcie_test_tc_rtc_05": {
                        "consistent": False,
                        "checks": {"value_matches_expected": False},
                        "expected": {"address": "0x0000+0x04", "value": "0x2026_0708"},
                    },
                },
                "verdict": {
                    "passed": passed,
                    "reasons": ["印记 N6_pcie_test_tc_rtc_05 三向不一致：['value_matches_expected']"],
                    "criterion": "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致",
                },
            },
        },
    }


def _read_artifact(ctx: RunCtx) -> dict[str, Any]:
    path = ctx.run_dir / n10_semantics.N10_CASES_FILE
    assert path.is_file(), f"必须落盘 {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ================================================================ 搬运（不重算）


def test_persist_copies_machine_verdicts_verbatim(tmp_path: Path, kb_root: Path) -> None:
    """产物逐例字段 = `n9_result.cases` 的既有值（值相等，不重算、不新增判据）。"""
    ctx = _ctx(tmp_path, kb_root)
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)
    out = _machine_out(log, passed=False)

    meta = n10_semantics._persist_cases(ctx, out)
    assert meta["n10_cases_written"] is True
    doc = _read_artifact(ctx)

    assert doc["schema"] == "loop/n10_cases"
    assert doc["run_id"] == RUN_ID
    assert doc["created_at"], "created_at 必须落盘（经 host.paths.now_iso 单一时间入口）"
    assert doc["criterion"] == out["verdict"]["criterion"]

    case = doc["cases"]["tc_rtc_05"]
    src = out["cases"]["tc_rtc_05"]
    assert case["case"] == "tc_rtc_05"
    assert case["passed"] is False
    assert case["passed"] == src["verdict"]["passed"]
    assert case["criterion"] == src["verdict"]["criterion"]
    assert case["reasons"] == src["verdict"]["reasons"]
    assert case["counts"] == src["counts"]
    assert case["imprints"] == src["imprints"]


def test_persist_does_not_recompute_from_log(tmp_path: Path, kb_root: Path) -> None:
    """日志内容"通过"、N9 判不通过 ⇒ 产物仍是 N9 原判（O-1：机器结论不得改写）。"""
    ctx = _ctx(tmp_path, kb_root)
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)
    out = _machine_out(log, passed=False)
    out["verdict"]["criterion"] = "SENTINEL-聚合判据（原样搬运，不由日志重推）"
    out["cases"]["tc_rtc_05"]["verdict"]["criterion"] = "SENTINEL-逐例判据"

    n10_semantics._persist_cases(ctx, out)
    doc = _read_artifact(ctx)

    assert doc["cases"]["tc_rtc_05"]["passed"] is False, "不得因日志看着像通过就改判 pass"
    assert doc["cases"]["tc_rtc_05"]["criterion"] == "SENTINEL-逐例判据"
    assert doc["criterion"] == "SENTINEL-聚合判据（原样搬运，不由日志重推）"


def test_persist_computes_evidence_md5_and_bytes(tmp_path: Path, kb_root: Path) -> None:
    """证据 md5/bytes 在落盘时对权威 run.log 现算（身份可复核）。"""
    ctx = _ctx(tmp_path, kb_root)
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)

    n10_semantics._persist_cases(ctx, _machine_out(log))
    doc = _read_artifact(ctx)
    evidence = doc["cases"]["tc_rtc_05"]["evidence"]

    assert evidence["path"] == str(log)
    assert evidence["md5"] == hashlib.md5(log.read_bytes()).hexdigest()
    assert evidence["bytes"] == log.stat().st_size


def test_persist_missing_evidence_is_explicit_not_fabricated(tmp_path: Path,
                                                              kb_root: Path) -> None:
    """证据件不存在 ⇒ `md5/bytes` 显式为 None（不编造），路径照旧留存。"""
    ctx = _ctx(tmp_path, kb_root)
    absent = ctx.run_dir / "evidence" / "nope_run.log"

    n10_semantics._persist_cases(ctx, _machine_out(absent))
    evidence = _read_artifact(ctx)["cases"]["tc_rtc_05"]["evidence"]

    assert evidence["path"] == str(absent)
    assert evidence["md5"] is None, "缺件时不得给出 md5"
    assert evidence["bytes"] is None


def test_persist_write_failure_is_explicit(tmp_path: Path, kb_root: Path,
                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """写盘失败 ⇒ `written=False` + `warning` 事件；不抛异常、不静默吞。"""
    ctx = _ctx(tmp_path, kb_root)
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)

    def boom(path: Path, payload: dict[str, Any]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(n10_semantics, "_write_json", boom)
    meta = n10_semantics._persist_cases(ctx, _machine_out(log))

    assert meta["n10_cases_written"] is False
    assert "disk full" in meta["n10_cases_error"]
    kinds = [json.loads(line) for line in ctx.progress.path.read_text(encoding="utf-8").splitlines()]
    warnings = [e for e in kinds
                if e.get("kind") == "warning" and e.get("status") == "n10_cases_not_written"]
    assert len(warnings) == 1, "落盘失败必须留一条显式 warning 事件"
    assert not (ctx.run_dir / n10_semantics.N10_CASES_FILE).exists()


# ================================================================ 读侧（旧 run 缺件）


def test_load_cases_missing_is_explicit_for_old_run(tmp_path: Path, kb_root: Path) -> None:
    """旧 run 无 `n10_cases.json` ⇒ 读侧显式 missing（不解析 n10_reconcile.md）。"""
    ctx = _ctx(tmp_path, kb_root)
    (ctx.run_dir / "n10_reconcile.md").write_text(
        "# N10 结果对账\n\n- `tc_demo`：口径一=0 ⇒ passed=False（三向不一致）\n",
        encoding="utf-8")

    doc = n10_semantics.load_cases(ctx.run_dir)

    assert doc["present"] is False
    assert doc["missing"] == "n10_cases.json"
    assert doc["cases"] == {}, "不得从 n10_reconcile.md 反解析出第二套判据"


def test_load_cases_roundtrip(tmp_path: Path, kb_root: Path) -> None:
    """读回已落盘产物（读侧唯一实现，与写侧同源）。"""
    ctx = _ctx(tmp_path, kb_root)
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)
    n10_semantics._persist_cases(ctx, _machine_out(log))

    doc = n10_semantics.load_cases(ctx.run_dir)
    assert doc["present"] is True
    assert doc["run_id"] == RUN_ID
    assert sorted(doc["cases"]) == ["tc_rtc_05"]


# ================================================================ 登记与 N10 集成


def test_artifacts_registry_lists_n10_cases() -> None:
    """`host_steps.ARTIFACTS` 登记产物名（refs/读侧按名解析）。"""
    assert host_steps.ARTIFACTS["n10_cases"] == "n10_cases.json"
    assert host_steps.ARTIFACTS["n10"] == "n10_reconcile.md"


async def test_n10_real_landing_writes_cases_artifact(tmp_path: Path, kb_root: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """N10 real 分支：落盘产物 + result 带回路径 + node_finished refs 含该件。"""
    ctx = _ctx(tmp_path, kb_root, mode="real")
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)
    n9 = _machine_out(log)
    n9["target_cases"] = ["tc_rtc_05"]
    n9["evidence"] = {"path": str(log), "present": True}

    async def classify(*_a: Any, **_k: Any) -> dict[str, Any]:
        payload = {"items": [], "summary": "无待裁决", "unclassified": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": payload},
                "data": payload, "provider": "fake"}

    def fake_tool(tool: str, args: list[str], **_kw: Any) -> dict[str, Any]:
        return {"cmd": "fake", "rc": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(model_steps, "run_model_node", classify)
    monkeypatch.setattr(model_steps, "run_kb_tool", fake_tool)
    monkeypatch.setattr(n10_semantics, "run_kb_tool", fake_tool)

    data = FakeData(state={"n9_result": n9, "n7_compile": {"cases": []}})
    out = await model_steps.n10_reconcile(data)

    path = Path(out["n10_cases_path"])
    assert path == ctx.run_dir / "n10_cases.json" and path.is_file()
    assert out["n10_cases_written"] is True
    doc = _read_artifact(ctx)
    assert doc["cases"]["tc_rtc_05"]["passed"] is False
    assert doc["cases"]["tc_rtc_05"]["reasons"] == n9["cases"]["tc_rtc_05"]["verdict"]["reasons"]

    events = [json.loads(line) for line in
              ctx.progress.path.read_text(encoding="utf-8").splitlines()]
    finished = [e for e in events
                if e.get("kind") == "node_finished" and e.get("node") == "N10"]
    assert finished, "N10 必须留 node_finished"
    assert str(path) in (finished[-1].get("refs") or []), "产物必须登记进 refs"


async def test_n10_drill_landing_also_writes_cases_artifact(
        tmp_path: Path, kb_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """drill 分支同样落盘（夹具回放也需要产物；值取夹具的既有 verdict）。"""
    ctx = _ctx(tmp_path, kb_root, mode="drill")
    _write_log(ctx, "20261102-120000_tc_pcie_rw_02_1_run.log", _PASSING_LOG)
    (ctx.fixture / "reconcile.md").write_text("# 夹具对账\n", encoding="utf-8")

    async def standin(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"mode": "standin", "standin": True, "validation": {"ok": True, "problems": []},
                "data": {"standin": True}, "provider": "none"}

    monkeypatch.setattr(model_steps, "run_model_node", standin)
    data = FakeData(state={})
    out = await model_steps.n10_reconcile(data)

    path = Path(out["n10_cases_path"])
    assert path.is_file()
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["run_id"] == RUN_ID
    assert "tc_pcie_rw_02" in doc["cases"]
    assert doc["cases"]["tc_pcie_rw_02"]["passed"] == out["cases"]["tc_pcie_rw_02"]["verdict"]["passed"]


async def test_n10_landing_failure_does_not_fail_the_node(
        tmp_path: Path, kb_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """产物缺失的后果是"本轮不可覆写"（服务层 fail-closed），**不是** N10 整轮失败。"""
    ctx = _ctx(tmp_path, kb_root, mode="real")
    log = _write_log(ctx, "20261102-120000_tc_rtc_05_1_run.log", _PASSING_LOG)
    n9 = _machine_out(log)
    n9["target_cases"] = ["tc_rtc_05"]

    async def classify(*_a: Any, **_k: Any) -> dict[str, Any]:
        payload = {"items": [], "summary": "", "unclassified": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": payload},
                "data": payload, "provider": "fake"}

    def fake_tool(tool: str, args: list[str], **_kw: Any) -> dict[str, Any]:
        return {"cmd": "fake", "rc": 0, "stdout_tail": "", "stderr_tail": ""}

    def boom(path: Path, payload: dict[str, Any]) -> None:
        raise OSError("read-only run dir")

    monkeypatch.setattr(model_steps, "run_model_node", classify)
    monkeypatch.setattr(model_steps, "run_kb_tool", fake_tool)
    monkeypatch.setattr(n10_semantics, "run_kb_tool", fake_tool)
    monkeypatch.setattr(n10_semantics, "_write_json", boom)

    out = await model_steps.n10_reconcile(FakeData(state={"n9_result": n9, "n7_compile": {"cases": []}}))

    assert out["n10_cases_written"] is False
    assert "read-only run dir" in out["n10_cases_error"]
    assert (ctx.run_dir / "n10_reconcile.md").is_file(), "既有对账文件仍要写（不得因新产物失败而丢）"
