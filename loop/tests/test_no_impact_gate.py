"""LOOP §14：N5 必改=0 的 G1 分流闸门 `G1_no_impact`（TDD）。

契约：
- `CHANGE_IMPACT_LOOP_SPEC.md` §12（业务：两个决策与语义）；
- `LOOP_ORCHESTRATION_SPEC.md` §14（机制：闸门身份/拓扑/目标集/验收）；
- 冻结目录变更留证：`doc/plans/2026-10-30-zero-must-change-gate.md`。

覆盖：
1. 冻结枚举与 schema 形状（`GATE_IDS` 末尾追加；`version=2`；`gate.py` 对 v1 旧记录仍可读）；
2. 权威投影：中文标签、决策选项、`requires_reason`（仅 `no_impact_end`）、未出现的分流门不投影；
3. 纵深防御：`must_change_count != 0` 时不得进入/签署该门；
4. N5 出口事件：必改=0 ⇒ `N5_ZERO_MUST_CHANGE`，否则 `N5_HAS_MUST_CHANGE`（只发一个）；
5. 全量回归目标集：取自 `kb/index/cases.json`，文件 md5 必须与索引一致（审的对象 == 跑的对象）；
6. 拓扑：`BRANCH_EVENTS` 与权威逐值一致（启动自检不漂移）。
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
KB_LIB = REPO / "kb" / "tools" / "kb_lib.py"
GATE_PY = REPO / "kb" / "tools" / "gate.py"
SCHEMA = REPO / "kb" / "schema" / "gate_state.schema.json"


# ================================================================ 夹具


def _tmp_run_key(index: int = 0) -> str:
    return "RUN-20261030-%06d" % (230000 + index)


def _write_gates_state(root: Path, run_key: str, *, version: int, gates: dict) -> None:
    folder = root / "runs" / run_key
    folder.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": "kb/gate-state", "version": version, "run_id": run_key,
        "created_at": "2026-10-30T22:00:00+08:00",
        "manifest_from": None, "manifest_to": None,
        "gates": gates,
    }
    (folder / "gates.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def _gate_row(gate_id: str, kind: str) -> dict:
    return {"gate_id": gate_id, "kind": kind, "status": "pending", "decision": "pending",
            "actor": None, "actor_kind": None, "human_signed": False, "signed_at": None,
            "note": None, "rework_target": None, "artifacts": [], "history": []}


# ================================================================ 1 冻结枚举 / schema / gate.py


def test_enum_appends_only_the_authorized_branch_gate() -> None:
    from host import gate_authority as GA

    ids = GA.gate_ids()
    assert ids[:3] == ("G1_diff_confirm", "G2_report_accept", "G3_regression_decision"), ids
    assert ids[3:] == ("G1_no_impact",), ids
    assert GA.gate_kind("G1_no_impact") == "diff_confirm"
    assert GA.decisions()["G1_no_impact"] == ("no_impact_end", "full_regression", "pending")
    assert GA.actionable_decisions("G1_no_impact") == ("no_impact_end", "full_regression")


def test_schema_allows_v1_legacy_and_v2_new() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["enum"] == [1, 2]
    gates = schema["properties"]["gates"]
    assert gates["required"] == ["G1_diff_confirm", "G2_report_accept", "G3_regression_decision"]
    assert "G1_no_impact" in gates["properties"]
    assert "G1_no_impact" in schema["definitions"]["gate"]["properties"]["gate_id"]["enum"]


def test_kb_gate_init_writes_v2_and_new_gate_can_be_signed(tmp_path: Path) -> None:
    sys.path.insert(0, str(KB_LIB.parent))
    import kb_lib as K  # noqa: E402  （读冻结目录，测试内临时 run 键）

    key = _tmp_run_key(0)
    try:
        st = K.gate_init(key, None, None)
        assert st["version"] == 2
        assert set(st["gates"]) == set(K.GATE_IDS)   # 写盘按 sort_keys，顺序不作判据
        assert st["gates"]["G1_no_impact"]["kind"] == "diff_confirm"
        signed = K.gate_set(key, "G1_no_impact", "no_impact_end", "张三", "human",
                            note="本变无影响用例")
        row = signed["gates"]["G1_no_impact"]
        assert row["status"] == "signed" and row["human_signed"] is True
        assert row["history"][-1]["decision"] == "no_impact_end"
        assert K.gate_verify_anchor(key)[0] is True
    finally:
        import shutil
        shutil.rmtree(K.run_dir(key), ignore_errors=True)


def test_gate_py_reads_v1_legacy_but_rejects_v2_missing_new_gate(tmp_path: Path) -> None:
    from host import paths as P

    root = Path(P.KB_DIR)
    v1_key, v2_key = _tmp_run_key(10), _tmp_run_key(11)
    gates3 = {gid: _gate_row(gid, kind) for gid, kind in (
        ("G1_diff_confirm", "diff_confirm"),
        ("G2_report_accept", "report_accept"),
        ("G3_regression_decision", "regression_decision"))}
    try:
        _write_gates_state(root, v1_key, version=1, gates=gates3)
        legacy = subprocess.run([sys.executable, str(GATE_PY), "show", "--run", v1_key],
                                capture_output=True, text=True)
        assert legacy.returncode == 0, legacy.stderr + legacy.stdout

        gates4 = dict(gates3)          # 故意缺 G1_no_impact
        _write_gates_state(root, v2_key, version=2, gates=gates4)
        broken = subprocess.run([sys.executable, str(GATE_PY), "show", "--run", v2_key],
                                capture_output=True, text=True)
        assert broken.returncode == 4, broken.stdout + broken.stderr
        assert "G1_no_impact" in (broken.stderr + broken.stdout)
    finally:
        import shutil
        for key in (v1_key, v2_key):
            shutil.rmtree(root / "runs" / key, ignore_errors=True)


# ================================================================ 2 权威投影


def test_labels_and_reason_requirement() -> None:
    from host import gate_authority as GA
    from services import contracts

    assert "结束" in GA.human_readable("G1_no_impact", "no_impact_end")
    assert "全量回归" in GA.human_readable("G1_no_impact", "full_regression")

    options = {o["value"]: o for o in contracts.gate_decision_options("G1_no_impact")}
    assert set(options) == {"no_impact_end", "full_regression"}
    assert options["no_impact_end"]["requires_reason"] is True
    assert options["full_regression"]["requires_reason"] is False
    assert contracts.decision_requires_reason("G1_no_impact", "no_impact_end") is True
    assert contracts.decision_requires_reason("G1_no_impact", "full_regression") is False


def test_unused_branch_gate_is_not_projected_and_does_not_block_all_signed() -> None:
    """未出现的分流门既不投影、也不拖住 `all_signed`（正常运行不能被读成"还有门没签"）。"""
    from host import gate_authority as GA
    from host import paths as P
    from services import contracts

    sys.path.insert(0, str(KB_LIB.parent))
    import kb_lib as K  # noqa: E402

    key = _tmp_run_key(12)
    try:
        K.gate_init(key, None, None)
        for gate, decision in (("G1_diff_confirm", "confirmed"),
                               ("G2_report_accept", "accept"),
                               ("G3_regression_decision", "defer")):
            K.gate_set(key, gate, decision, "张三", "human", note="selftest")
        view = GA.authority_view(key)
        assert "G1_no_impact" not in view["gates"]          # 未出现 ⇒ 不投影
        assert view["all_signed"] is True                   # 也不拖住"全签"
        assert view["human_signed_all"] is True

        # 出现在本轮（签署过）⇒ 必须投影
        K.gate_set(key, "G1_no_impact", "full_regression", "张三", "human", note="转全量回归")
        view = GA.authority_view(key)
        assert view["gates"]["G1_no_impact"]["decision"] == "full_regression"
        exported = contracts._gates_authority({"run_id": key})
        assert "G1_no_impact" in exported["gates"] and "G1_no_impact" in view["gates"]
    finally:
        import shutil
        shutil.rmtree(Path(P.KB_DIR) / "runs" / key, ignore_errors=True)


# ================================================================ 3 纵深防御


class _FakeData:
    def __init__(self, state: dict | None = None):
        self.state = dict(state or {})
        self.emitted: list[tuple[str, object]] = []
        self.paused: list[dict] = []

    async def async_set_state(self, key, value) -> None:
        self.state[key] = value

    def get_state(self, key):
        return self.state.get(key)

    async def async_emit(self, event, payload=None) -> None:
        self.emitted.append((event, payload))

    async def async_pause_for(self, **kw) -> dict:
        self.paused.append(kw)
        return kw

    def require_resource(self, key):
        raise KeyError(key)


def test_guard_rejects_gate_when_must_change_not_zero() -> None:
    from workflows.chunks.gates import GatePreconditionFailed, _assert_no_impact_gate_allowed

    _assert_no_impact_gate_allowed(None, _FakeData({"n5_impact": {"must_change_count": 0}}), "G1_no_impact")
    with pytest.raises(GatePreconditionFailed):
        _assert_no_impact_gate_allowed(None, _FakeData({"n5_impact": {"must_change_count": 2}}), "G1_no_impact")
    with pytest.raises(GatePreconditionFailed):
        _assert_no_impact_gate_allowed(None, _FakeData({}), "G1_no_impact")
    # 其它门不受影响
    _assert_no_impact_gate_allowed(None, _FakeData({}), "G1_diff_confirm")


# ================================================================ 4 N5 出口事件


def _n5_ctx(tmp_path: Path, fixture: dict) -> object:
    from host import paths as P
    from services.contracts import KbSources
    from workflows.context import RunCtx, ProgressLog

    run_dir = tmp_path / "runs" / "RUN-20261030-220000"
    run_dir.mkdir(parents=True)
    fix = tmp_path / "fixture"
    fix.mkdir()
    (fix / "n5_impact.json").write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    kb_root = tmp_path / "kb"
    (kb_root / "conflicts").mkdir(parents=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []}),
        encoding="utf-8")
    return RunCtx(run_id="RUN-20261030-220000", run_dir=run_dir, mode="drill", scenario="happy",
                  kb=KbSources.from_workspace(kb_root),
                  progress=ProgressLog(tmp_path / "events", "RUN-20261030-220000"),
                  fixture=fix)


class _N5Data(_FakeData):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx

    def require_resource(self, key):
        return self._ctx if key == "loop_ctx" else (_ for _ in ()).throw(KeyError(key))


@pytest.mark.asyncio
async def test_n5_zero_branch_emits_only_zero_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows.chunks import host_steps

    ctx = _n5_ctx(tmp_path, {"must_change": [], "to_check": [{"case": "tc_a"}],
                             "index_complete": True, "index_gaps": []})
    monkeypatch.setattr(host_steps, "run_kb_tool", lambda *a, **k: {"rc": 0})
    data = _N5Data(ctx)
    result = await host_steps.n5_impact(data)
    assert result["must_change_count"] == 0 and result["zero_must_change"] is True
    assert [e for e, _ in data.emitted] == ["N5_ZERO_MUST_CHANGE"], data.emitted


@pytest.mark.asyncio
async def test_n5_has_must_change_emits_only_has_event(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows.chunks import host_steps

    ctx = _n5_ctx(tmp_path, {"must_change": [{"case": "tc_a"}], "index_complete": True, "index_gaps": []})
    monkeypatch.setattr(host_steps, "run_kb_tool", lambda *a, **k: {"rc": 0})
    data = _N5Data(ctx)
    result = await host_steps.n5_impact(data)
    assert result["must_change_count"] == 1 and result["zero_must_change"] is False
    assert [e for e, _ in data.emitted] == ["N5_HAS_MUST_CHANGE"], data.emitted


# ================================================================ 5 全量回归目标集


def _index_fixture(tmp_path: Path, cases: list[dict]) -> tuple[Path, Path]:
    from host import paths as P

    env = tmp_path / "env"
    (env / "TESTLIB").mkdir(parents=True)
    for item in cases:
        target = env / item["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("module x; endmodule\n", encoding="utf-8")
        item["md5"] = __import__("hashlib").md5(target.read_bytes()).hexdigest()
    kb = tmp_path / "kb"
    (kb / "index").mkdir(parents=True)
    (kb / "index" / "cases.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")
    return kb, env


def test_full_regression_targets_use_index_and_verify_md5(tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from host import paths as P
    from workflows.chunks import long_jobs

    kb, env = _index_fixture(tmp_path, [
        {"case": "tc_a", "file": "TESTLIB/tc_a.sv"},
        {"case": "tc_b", "file": "TESTLIB/tc_b.sv"},
    ])
    monkeypatch.setattr(P, "KB_DIR", kb)
    monkeypatch.setattr(P, "ENV_ROOT", env)

    targets = long_jobs._baseline_full_targets()
    assert [t["case"] for t in targets] == ["tc_a", "tc_b"]
    assert all(Path(t["sandbox_path"]).is_file() and t["md5"] for t in targets)

    (env / "TESTLIB" / "tc_b.sv").write_text("module y; endmodule\n", encoding="utf-8")
    with pytest.raises(RuntimeError) as excinfo:
        long_jobs._baseline_full_targets()
    assert "md5" in str(excinfo.value)


def test_full_regression_targets_fail_closed_without_index(tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from host import paths as P
    from workflows.chunks import long_jobs

    kb = tmp_path / "kb"
    (kb / "index").mkdir(parents=True)
    monkeypatch.setattr(P, "KB_DIR", kb)
    monkeypatch.setattr(P, "ENV_ROOT", tmp_path / "env")
    with pytest.raises(RuntimeError) as excinfo:
        long_jobs._baseline_full_targets()
    assert "全量回归集不可用" in str(excinfo.value)

    (kb / "index" / "cases.json").write_text('{"cases": []}', encoding="utf-8")
    with pytest.raises(RuntimeError) as excinfo:
        long_jobs._baseline_full_targets()
    assert "全量回归集为空" in str(excinfo.value)


def test_full_regression_flag_reads_gate_decision() -> None:
    from workflows.chunks import long_jobs

    data = _FakeData({"gate_decisions": {"G1_no_impact": {"decision": "full_regression"}}})
    assert long_jobs._no_impact_full_regression(data) is True
    data = _FakeData({"gate_decisions": {"G1_no_impact": {"decision": "no_impact_end"}}})
    assert long_jobs._no_impact_full_regression(data) is False
    assert long_jobs._no_impact_full_regression(_FakeData({})) is False


# ================================================================ 6 拓扑


def test_topology_matches_authority_and_has_branch_events() -> None:
    from workflows.chunks import gates as gate_chunks
    from workflows import main_flow

    assert main_flow.BRANCH_DRIFT == {}
    assert gate_chunks.GATE_NODE["G1_no_impact"] == "N5b"
    assert gate_chunks.BRANCH_EVENTS["G1_no_impact"] == {
        "no_impact_end": "G1_NO_IMPACT_END",
        "full_regression": "G1_NO_IMPACT_FULL_REGRESSION",
    }
    source = Path(main_flow.__file__).read_text(encoding="utf-8")
    assert "N5_ZERO_MUST_CHANGE" in source and "N5_HAS_MUST_CHANGE" in source

# ================================================================ 7 drill 端到端分支


def _zero_fixture(tmp_path: Path) -> Path:
    """复制缺省 drill 夹具，把 N5 结论改成"必改=0"（其余件原样，保证链路可跑）。"""
    import shutil

    from workflows.context import DEFAULT_DRILL_FIXTURE, DRILL_REQUIRED_FILES
    from host import paths as P

    src = Path(P.KB_RUNS) / DEFAULT_DRILL_FIXTURE
    assert src.is_dir(), f"缺省 drill 夹具不存在：{src}"
    dest = tmp_path / "fixture-zero"
    shutil.copytree(src, dest)
    (dest / "n5_impact.json").write_text(
        json.dumps({"must_change": [], "to_check": [], "index_complete": True, "index_gaps": []},
                   ensure_ascii=False), encoding="utf-8")
    for name in DRILL_REQUIRED_FILES:
        assert (dest / name).is_file(), name
    return dest


async def _drive_to(m, rid: str, prefix: str, *, timeout: float = 30.0) -> dict:
    import asyncio

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        view = m.run_view(rid)
        pending = (view.get("pending_interrupt") or {}).get("id") or ""
        if pending.startswith(prefix):
            return view
        if view.get("status") in ("finished", "failed"):
            raise AssertionError(f"未到 {prefix} 就结束：status={view.get('status')} error={view.get('error')}")
        await asyncio.sleep(0.2)
    raise AssertionError(f"未在 {timeout}s 内到达 {prefix}：{m.run_view(rid).get('pending_interrupt')}")


async def test_drill_zero_must_change_ends_at_halt(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows.main_flow import RunManager

    monkeypatch.setenv("LOOP_DRILL_FIXTURE", str(_zero_fixture(tmp_path)))
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="happy")
    try:
        await _drive_to(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="已逐条核对")
        view = await _drive_to(m, rid, "G1_no_impact")
        payload = (view.get("pending_interrupt") or {}).get("payload") or {}
        values = [o["value"] for o in payload.get("decision_options") or []]
        assert values == ["no_impact_end", "full_regression"], values
        assert payload.get("gate_node") == "N5b"
        assert payload.get("gate") == "G1_no_impact"

        await m.decide(run_id=rid, gate="G1_no_impact", decision="no_impact_end",
                       actor="human:test", reason="本变无影响用例，结束")
        import asyncio
        for _ in range(60):
            view = m.run_view(rid)
            if view.get("status") == "finished":
                break
            await asyncio.sleep(0.2)
        assert view.get("status") == "finished", view
        nodes = [e.get("node") for e in view.get("node_history") or []]
        assert "HALT" in nodes, nodes
        assert "N6_author" not in nodes, nodes      # 零必改 ⇒ 不得进入修订阶段
        assert "N9_submit" not in nodes, nodes
    finally:
        await m.stop_watching()


async def test_drill_full_regression_skips_revision_and_runs_n9(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from workflows.main_flow import RunManager

    monkeypatch.setenv("LOOP_DRILL_FIXTURE", str(_zero_fixture(tmp_path)))
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="happy")
    try:
        await _drive_to(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="已逐条核对")
        await _drive_to(m, rid, "G1_no_impact")
        await m.decide(run_id=rid, gate="G1_no_impact", decision="full_regression",
                       actor="human:test", reason="")
        # drill 作业完成极快 ⇒ `JOB:` 中断是瞬态（甚至可能撞上 resume 竞态），因此
        # 判据改看**事件流**（不依赖瞬时 interrupt）：必须出现 N9_submit/N9，且绝不出现 N6_author。
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 60
        events: list[dict] = []
        while loop.time() < deadline:
            events = list(m._progress(rid).read())
            nodes = {e.get("node") for e in events if e.get("kind") == "node_finished"}
            if {"N9_submit", "N9"} <= nodes:
                break
            await asyncio.sleep(0.2)
        nodes = [e.get("node") for e in events if e.get("kind") == "node_finished"]
        assert "N6_author" not in nodes, nodes      # 跳过修订
        assert "N9_submit" in nodes and "N9" in nodes, nodes
    finally:
        await m.stop_watching()
