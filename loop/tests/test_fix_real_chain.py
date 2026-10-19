"""WS-R real 链路修复的回归测试（审计 2026-10-19 §3：N1/N3/N6/N7/N8/N9/N10/N11/N12/N15 + I2/I7）。

设计纪律：
- **不跑真仿真**：runner / run_guarded / evidence 聚合一律用 fake 注入；
- **不写 ENV_ROOT / WORKSPACE_ROOT**：所有产物落 `tmp_path`（case_state 用 `--state-file`）；
- 每个 ID 至少覆盖「成功 / 失败(fail-closed)」两条路径。

覆盖：
  #6/A19 N1（--parent + staged 完整性）          test_n1_*
  #7/A5  N7（真 compile-only + 短租约 + rc!=0）  test_n7_*
  #3/A6  N6（结构化 edits → n6_apply 沙箱/冻结/记账） test_n6_*
  #8/A7  N9（目标集/单作业/沙箱 md5 fail-closed） test_n9_*
  #9/A15 N15（真执行/终值证据，删 provisional）   test_n15_*
  #1/C3  N8 fail-closed                          test_n8_*
  #15/A10 N11 guardian（成链/不成链/身份四方同值） test_n11_*
  #18/I8 N3/N10/N12 落盘 + refs 可解析           test_n3_*, test_n10_*, test_n12_*
  #11/I2 用例态台账（N6/N8/N10 写入者）           test_i2_*
  #22/I7 返工计数（首轮不消耗、>=limit 升级）     test_i7_*
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from host import paths as P
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.chunks import host_steps, long_jobs, model_steps
from workflows.context import RunCtx

RUN_ID = "RUN-20261019-180000"

#: 当前测试的 RunCtx（ctx_of 从 `loop_ctx` 资源取回；测试里由 FakeData 自动注入）
_CURRENT_CTX: Any = None


def use_ctx(ctx: RunCtx) -> RunCtx:
    global _CURRENT_CTX
    _CURRENT_CTX = ctx
    return ctx


# ================================================================ fakes


class FakeData:
    def __init__(self, *, input: dict[str, Any] | None = None,
                 resources: dict[str, Any] | None = None,
                 state: dict[str, Any] | None = None):
        self.input = input or {}
        self.resources = dict(resources or {})
        self.resources.setdefault("loop_ctx", _CURRENT_CTX)
        if "loop_ctx" not in self.resources:
            raise RuntimeError("测试未设置当前 RunCtx（use_ctx）")
        self.state = dict(state or {})
        self.emitted: list[tuple[str, Any]] = []
        self.paused: list[dict[str, Any]] = []
        self.is_resume = False
        self.resume = None

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        if key not in self.resources:
            raise KeyError(f"resource 缺失：{key}")
        return self.resources[key]

    async def async_pause_for(self, **kw: Any) -> dict[str, Any]:
        self.paused.append(kw)
        return kw

    async def async_emit(self, event: str, payload: Any) -> None:
        self.emitted.append((event, payload))


class FakeAdmission:
    def __init__(self, *, state: str = "granted"):
        self.state = state
        self.acquired: list[dict[str, Any]] = []
        self.released: list[dict[str, Any]] = []
        self.cancelled: list[str] = []

    def acquire(self, **kw: Any) -> SimpleNamespace:
        self.acquired.append(kw)
        return SimpleNamespace(granted=self.state == "granted", state=self.state,
                               reason="fake", job_id=kw.get("job_id"), position=1,
                               holder={"job_id": "other"})

    def release(self, **kw: Any) -> None:
        self.released.append(kw)
        return None

    def cancel_pending(self, job_id: str) -> bool:
        self.cancelled.append(job_id)
        return True


class FakeRunner:
    def __init__(self, *, phase: str = "done", rc: int = 0):
        self.phase = phase
        self.rc = rc
        self.submitted: list[dict[str, Any]] = []

    def submit(self, **kw: Any) -> SimpleNamespace:
        self.submitted.append(kw)
        return SimpleNamespace(job_id=f"JOB-{len(self.submitted):04d}",
                               started_at=0.0, log_path=f"/tmp/{kw.get('node')}.log")

    def poll(self, job_id: str) -> SimpleNamespace:
        return SimpleNamespace(phase=self.phase, rc=self.rc)


def _md5(path: Path) -> str:
    return host_steps.md5_file(Path(path))


@pytest.fixture
def env_repo(tmp_path: Path) -> Path:
    """假的 ENV_ROOT（只含 TESTLIB 用例源文件）。"""
    root = tmp_path / "env"
    (root / "TESTLIB").mkdir(parents=True)
    (root / "TESTLIB" / "tc_demo.sv").write_text(
        "module tc_demo;\n"
        "  // line 2 is inert\n"
        "  check(0x0000+0x04, 0x2023_0804);\n"
        "  check(0x0000+0x04, 0x2023_0804);  // duplicate for fail path\n"
        "  check(0x0000+0x08, 0xdead_beef);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    (root / "TESTLIB" / "tc_other.sv").write_text(
        "module tc_other;\n  check(0x0000+0x04, 0x2023_0804);\nendmodule\n", encoding="utf-8"
    )
    return root


@pytest.fixture
def ctx(tmp_path: Path, env_repo: Path) -> RunCtx:
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    kb_root = tmp_path / "kb"
    (kb_root / "conflicts").mkdir(parents=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []}
                   , ensure_ascii=False), encoding="utf-8")
    kb = KbSources.from_workspace(kb_root)
    return use_ctx(RunCtx(
        run_id=RUN_ID, run_dir=run_dir, mode="real", scenario="happy", kb=kb,
        progress=ProgressLog(tmp_path / "events", RUN_ID),
        admission=FakeAdmission(), runner=FakeRunner(),
    ))


def _case_state_init(ctx: RunCtx) -> None:
    res = host_steps.run_kb_tool(
        "case_state.py", ["init", "--run", ctx.run_id,
                          "--state-file", str(ctx.run_dir / "case_states.json")])
    assert res["rc"] in (0, 3), res


def _case_state_set(ctx: RunCtx, case: str, state: str, **extra: str) -> dict[str, Any]:
    args = ["set", "--run", ctx.run_id, "--state-file", str(ctx.run_dir / "case_states.json"),
            "--case", case, "--state", state]
    for key, value in extra.items():
        args += [f"--{key.replace('_', '-')}", str(value)]
    return host_steps.run_kb_tool("case_state.py", args)


def _ledger(ctx: RunCtx) -> dict[str, Any]:
    return json.loads((ctx.run_dir / "case_states.json").read_text(encoding="utf-8"))


def _sandbox_case(ctx: RunCtx, name: str = "tc_demo") -> dict[str, Any]:
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    lib.mkdir(parents=True, exist_ok=True)
    dest = lib / f"{name}.sv"
    dest.write_text("module x;\n  check(0x0000+0x04, 0x2026_0708);\nendmodule\n", encoding="utf-8")
    return {"case": name, "file": f"TESTLIB/{name}.sv", "sandbox_path": str(dest),
            "md5_before": "before", "md5_after": _md5(dest), "edits": 1}


def _n5_n2_for_targets(ctx: RunCtx, *, case: str = "tc_demo", line: int = 3,
                       entry_id: str = "0x0000#0x0004") -> None:
    (ctx.run_dir / "n5_impact.json").write_text(json.dumps({
        "must_change": [{"case": case, "file": f"TESTLIB/{case}.sv", "line": line,
                         "segment": "0x0000", "offset": "0x4", "entry_id": entry_id,
                         "why": "offset 直接命中"}],
        "must_change_over_budget": [], "must_change_unreachable": [],
    }, ensure_ascii=False), encoding="utf-8")
    (ctx.run_dir / "n2_diff.json").write_text(json.dumps({
        "diffs": [{"entry_id": entry_id, "id": entry_id, "kind": "doc_entry",
                   "segment": "0x0000", "offset": "0x4",
                   "after": json.dumps({"name": "fpga_date", "segment": "0x0000",
                                        "offset_global": "0x0004", "reset": "2026_0708",
                                        "rw": "R", "bytes": 4, "bitdef_present": True})}],
    }, ensure_ascii=False), encoding="utf-8")


def _fake_aggregate(ctx: RunCtx, *, logs: dict[str, Path], cases: list[str],
                    expected_md5: dict[str, str], seed: str = "1") -> dict[str, Any]:
    per_case: dict[str, Any] = {}
    for case in cases:
        per_case[case] = {
            "path": str(logs[case]), "present": True,
            "counts": {
                "koutou1": {"label": "口径一", "value": 0, "zero": True, "refs": []},
                "koutou2": {"label": "口径二", "value": {"UVM_ERROR": 0, "UVM_FATAL": 0},
                            "zero": True, "refs": [], "uvm_summary_present": True},
                "both_zero": True,
            },
            "imprints": {"N6_FPGA_DATE_PCIE": {"consistent": True,
                                              "observed": {"id_count": 1},
                                              "expected": {"address": "0x0000+0x04"},
                                              "refs": []}},
            "verdict": {"passed": True, "reasons": [], "criterion": "fake"},
            "identity": {"run_id": ctx.run_id, "case": case,
                         "case_md5": expected_md5[case], "seed": seed,
                         "case_file": str(logs[case]), "source": "guard_header"},
        }
    return {"per_case": per_case, "totals": {"cases": len(cases), "present": len(cases),
                                             "passed": len(cases), "failed": 0},
            "verdict": {"passed": True, "reasons": [], "criterion": "fake"},
            "identity": {"consistent": True, "mismatches": [], "source": "guard_header"},
            "imprint_consistent": True,
            "aggregate": {"totals": {"cases": len(cases)},
                          "counts": {"koutou1_sum": 0, "koutou2": {"UVM_ERROR": 0}}},
            }


def _write_case_log(ctx: RunCtx, case: str) -> Path:
    evidence = ctx.run_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    path = evidence / f"20261019-120000_{case}_1_run.log"
    path.write_text("UVM Report Summary\nUVM_ERROR :    0\nUVM_FATAL :    0\n", encoding="utf-8")
    return path


# ================================================================ #6/A19 N1


async def test_n1_real_passes_required_parent_and_uses_env_defaults(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#6/A19：real 的 stage 必须带 `--parent`（缺它 argparse rc=2，real 必挂）。"""
    calls: list[list[str]] = []

    def fake_tool(tool: str, args: list[str], **kw: Any) -> dict[str, Any]:
        calls.append([tool, *args])
        (ctx.run_dir / "n1_manifest_new.json").write_text(
            json.dumps({"parent": "v3"}), encoding="utf-8")
        return {"cmd": "fake", "rc": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(host_steps, "run_kb_tool", fake_tool)
    data = FakeData(state={"run_meta": {"baseline": "v3"}},
                    resources={"repo_root": env_repo})
    out = await host_steps.n1_manifest(data)
    assert out["parent"] == "v3"
    joined = " ".join(calls[0])
    assert "stage" in joined and "--parent v3" in joined
    assert "--rtl-src" not in joined, "没有 staged 输入时应使用 ENV_ROOT 现态"


async def test_n1_staged_inputs_are_passed_with_mapping(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#6/A19：staged/{RTL,doc,regmap} 存在时走显式输入并校验完整性。"""
    staged = ctx.run_dir / "staged"
    for rel in ("RTL/SRC/imports", "RTL/RTL_COMMON"):
        (staged / rel).mkdir(parents=True)
        (staged / rel / "x.v").write_text("module x; endmodule\n", encoding="utf-8")
    (staged / "doc").mkdir()
    (staged / "doc" / "iface.md").write_text("# doc\n", encoding="utf-8")
    (staged / "regmap.json").write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_tool(tool: str, args: list[str], **kw: Any) -> dict[str, Any]:
        calls.append([tool, *args])
        (ctx.run_dir / "n1_manifest_new.json").write_text(
            json.dumps({"parent": "v0"}), encoding="utf-8")
        return {"cmd": "fake", "rc": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(host_steps, "run_kb_tool", fake_tool)
    data = FakeData(input={"baseline": "v0"}, resources={"repo_root": env_repo})
    out = await host_steps.n1_manifest(data)
    assert out["staged"]["present"] is True
    joined = " ".join(calls[0])
    assert "--doc-src" in joined and "--regmap" in joined
    assert f"{staged / 'RTL/SRC/imports'}=RTL/SRC/imports" in calls[0]


async def test_n1_incomplete_staged_fails_closed_without_calling_tool(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#6：staged 提供但不完整 ⇒ 显式失败，不回落 ENV_ROOT（不猜）。"""
    (ctx.run_dir / "staged" / "RTL").mkdir(parents=True)
    called: list[Any] = []
    monkeypatch.setattr(host_steps, "run_kb_tool",
                        lambda *a, **k: called.append(a) or {"rc": 0})
    data = FakeData(resources={"repo_root": env_repo})
    with pytest.raises(FileNotFoundError, match="staged 输入不完整"):
        await host_steps.n1_manifest(data)
    assert called == []


# ================================================================ #3/A6 N6


async def test_n6_apply_writes_sandbox_only_and_freezes_md5_into_ledger(
        ctx: RunCtx, env_repo: Path) -> None:
    """#3/A6：模型 edits → Host 写沙箱、冻结 md5、写 case_state（已修订待验）。"""
    _n5_n2_for_targets(ctx)
    data = FakeData(resources={"repo_root": env_repo}, state={
        "n6_targets": {"targets": [{
            "case": "tc_demo", "file": "TESTLIB/tc_demo.sv",
            "revision_points": [{"segment": "0x0000", "offset": "0x4"}]}]},
        "n6_author": {"mode": "live", "data": {"revisions": [{
            "case": "tc_demo",
            "edits": [{"line": 5, "old": "0xdead_beef", "new": "0xdead_c0de",
                       "basis": "0x0000#0x0004 reset 2026_0708"}],
            "rationale": "文档 reset 值更新",
        }]}, "validation": {"ok": True, "problems": [], "accepted": {}}},
    })
    out = await host_steps.n6_apply(data)
    assert out["status"] == "applied" and out["count"] == 1
    sandbox = Path(out["cases"][0]["sandbox_path"])
    assert sandbox.is_file()
    assert sandbox.parent == ctx.run_dir / "sandbox" / "TESTLIB"
    assert "0xdead_c0de" in sandbox.read_text(encoding="utf-8")
    assert _md5(sandbox) == out["cases"][0]["md5_after"]
    # 冻结：写后置只读
    assert sandbox.stat().st_mode & 0o200 == 0
    ledger = _ledger(ctx)
    assert ledger["cases"][0]["state"] == "已修订待验"
    assert ledger["cases"][0]["md5_after"] == out["cases"][0]["md5_after"]
    # 源文件绝不被改
    assert "0x2023_0804" in (env_repo / "TESTLIB" / "tc_demo.sv").read_text(encoding="utf-8")


async def test_n6_apply_rejects_non_unique_old_and_writes_nothing(
        ctx: RunCtx, env_repo: Path) -> None:
    """#3/A6：`old` 在文件里命中 0/多次 ⇒ fail closed（不猜位置），不落沙箱。"""
    _n5_n2_for_targets(ctx)
    data = FakeData(resources={"repo_root": env_repo}, state={
        "n6_targets": {"targets": [{"case": "tc_demo", "file": "TESTLIB/tc_demo.sv"}]},
        "n6_author": {"mode": "live", "data": {"revisions": [{
            "case": "tc_demo",
            "edits": [{"line": 3, "old": "0x2023_0804", "new": "0x1",
                       "basis": "b"}],
        }]}, "validation": {"ok": True, "problems": [], "accepted": {}}},
    })
    with pytest.raises(ValueError, match="命中 2 次|命中 [0-9]+ 次"):
        await host_steps.n6_apply(data)
    assert not (ctx.run_dir / "sandbox" / "TESTLIB" / "tc_demo.sv").exists()


async def test_n6_apply_rejects_line_mismatch_and_missing_revision(
        ctx: RunCtx, env_repo: Path) -> None:
    """#3/A6：old 不在声明行 ⇒ 拒绝；目标用例缺 revision ⇒ 拒绝。"""
    _n5_n2_for_targets(ctx)

    def payload(edit_line: int, revisions: list[dict[str, Any]]) -> FakeData:
        return FakeData(resources={"repo_root": env_repo}, state={
            "n6_targets": {"targets": [{"case": "tc_demo", "file": "TESTLIB/tc_demo.sv"}]},
            "n6_author": {"mode": "live", "data": {"revisions": revisions},
                          "validation": {"ok": True, "problems": [], "accepted": {}}},
        })

    with pytest.raises(ValueError, match="与声明的 line"):
        await host_steps.n6_apply(payload(3, [{
            "case": "tc_demo",
            "edits": [{"line": 3, "old": "0xdead_beef", "new": "0x1", "basis": "b"}],
        }]))
    with pytest.raises(ValueError, match="没有 revision"):
        await host_steps.n6_apply(payload(3, []))


async def test_n6_apply_drill_copies_fixture_sandbox_and_never_fails(
        ctx: RunCtx, env_repo: Path, tmp_path: Path) -> None:
    """drill 兼容硬约束：夹具沙箱件复制到 run_dir；夹具缺失 ⇒ no-op 不失败。"""
    ctx.mode = "drill"
    ctx.fixture = P.KB_RUNS / "RUN-20261015-120626"
    data = FakeData(resources={"repo_root": env_repo})
    out = await host_steps.n6_apply(data)
    assert out["status"] == "drill_fixture"
    assert out["count"] >= 1
    assert (ctx.run_dir / "sandbox" / "TESTLIB").is_dir()

    ctx2 = use_ctx(RunCtx(run_id=RUN_ID, run_dir=tmp_path / "runs2" / RUN_ID, mode="drill",
                  scenario="happy", kb=ctx.kb,
                  progress=ProgressLog(tmp_path / "events2", RUN_ID),
                  admission=FakeAdmission(), runner=FakeRunner(),
                  fixture=tmp_path / "no_fixture"))
    (ctx2.run_dir).mkdir(parents=True)
    out2 = await host_steps.n6_apply(FakeData(resources={"repo_root": env_repo}))
    assert out2["status"] == "drill_noop" and out2["count"] == 0


# ================================================================ #7/A5 N7


async def test_n7_real_runs_guarded_compile_only_per_case_and_releases_slot(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#7/A5：逐例真 compile-only（沙箱件）+ rc 证据；短租约 finally 释放。"""
    item = _sandbox_case(ctx)
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [item]}})
    guard_calls: list[list[str]] = []

    def fake_guard(args: list[str], *, timeout: float | None = None) -> dict[str, Any]:
        guard_calls.append(args)
        case = args[args.index("--case-name") + 1]
        evidence = Path(args[args.index("--evidence-dir") + 1])
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / f"20261019-120000_{case}_1_c_rtl.log").write_text("rc=0\n", encoding="utf-8")
        (evidence / f"20261019-120000_{case}_1_c_tb.log").write_text("rc=0\n", encoding="utf-8")
        return {"cmd": "fake", "rc": 0, "stdout_tail": "", "stderr_tail": ""}

    monkeypatch.setattr(host_steps, "run_guard", fake_guard)
    out = await host_steps.n7_compile(data)
    assert out["all_ok"] is True and out["cases"][0]["rc"] == 0
    assert guard_calls and guard_calls[0][guard_calls[0].index("--mode") + 1] == "compile-only"
    assert guard_calls[0][guard_calls[0].index("--case-file") + 1] == item["sandbox_path"]
    assert len(out["cases"][0]["evidence"]) == 2
    assert ctx.admission.acquired and ctx.admission.released
    assert all(call["job_id"].startswith("N7-") for call in ctx.admission.acquired)


async def test_n7_compile_failure_is_node_failed_and_still_releases(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#7/A5：rc!=0 ⇒ node_failed + raise；单槽仍必须释放。"""
    item = _sandbox_case(ctx)
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [item]}})
    monkeypatch.setattr(host_steps, "run_guard",
                        lambda *a, **k: {"cmd": "fake", "rc": 3,
                                         "stdout_tail": "", "stderr_tail": "compile error"})
    with pytest.raises(RuntimeError, match="compile-only rc=3"):
        await host_steps.n7_compile(data)
    assert ctx.admission.released, "编译失败后单槽未释放"


async def test_n7_slot_busy_fails_closed_without_waiting(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#7+I12：短任务不排队；queued ⇒ cancel_pending + 显式失败。"""
    item = _sandbox_case(ctx)
    ctx.admission = FakeAdmission(state="queued")
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [item]}})
    monkeypatch.setattr(host_steps, "run_guard", lambda *a, **k: pytest.fail("不得执行"))
    with pytest.raises(PermissionError, match="单槽被占用"):
        await host_steps.n7_compile(data)
    assert ctx.admission.cancelled


async def test_n7_missing_or_changed_sandbox_fails_closed(
        ctx: RunCtx, env_repo: Path) -> None:
    """#7+A7：沙箱缺失 / md5 与冻结值不符 ⇒ fail closed（禁止编译未修订原件）。"""
    missing = FakeData(resources={"repo_root": env_repo}, state={
        "n6_applied": {"cases": [{"case": "tc_demo", "sandbox_path": str(ctx.run_dir / "nope.sv"),
                                  "md5_after": "x"}]}})
    with pytest.raises(FileNotFoundError, match="沙箱件缺失"):
        await host_steps.n7_compile(missing)

    item = _sandbox_case(ctx)
    item["md5_after"] = "0" * 32
    changed = FakeData(resources={"repo_root": env_repo},
                       state={"n6_applied": {"cases": [item]}})
    with pytest.raises(RuntimeError, match="md5 与 N6 冻结值不符"):
        await host_steps.n7_compile(changed)


# ================================================================ #8/A7 N9


async def test_n9_real_submits_one_serial_job_for_all_target_cases(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#8/A7：目标集取 n6_applied 全部用例，串成**一个**作业；身份头一致。"""
    a = _sandbox_case(ctx, "tc_demo")
    b = _sandbox_case(ctx, "tc_other")
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [a, b]}})
    out = await long_jobs.n9_submit(data)
    assert out["cases"] == ["tc_demo", "tc_other"]
    assert out["md5s"]["tc_demo"] == a["md5_after"]
    record = ctx.runner.submitted[0]
    command = record["command"]
    assert command.count("run_guarded.sh") == 2
    assert "--mode full" in command and "tc_demo" in command and "tc_other" in command
    assert out["job_id"] == "JOB-0001"
    assert ctx.admission.acquired and ctx.admission.acquired[0]["tc"] == "tc_demo,tc_other"


async def test_n9_sandbox_missing_or_md5_changed_fails_before_submit(
        ctx: RunCtx, env_repo: Path) -> None:
    """#8/A7：沙箱缺失 / md5 不符 ⇒ fail closed（禁止回退未修订 TESTLIB）。"""
    data = FakeData(resources={"repo_root": env_repo}, state={"n6_applied": {"cases": []}})
    with pytest.raises(RuntimeError, match="没有已修订的沙箱用例"):
        await long_jobs.n9_submit(data)

    item = _sandbox_case(ctx)
    item["md5_after"] = "0" * 32
    bad = FakeData(resources={"repo_root": env_repo},
                   state={"n6_applied": {"cases": [item]}})
    with pytest.raises(RuntimeError, match="沙箱 md5 已变"):
        await long_jobs.n9_submit(bad)
    assert ctx.runner.submitted == [], "校验失败不得提交作业"


def _n9_job_and_resume(ctx: RunCtx, cases: list[str], md5s: dict[str, str]) -> tuple[FakeData, FakeData]:
    job = {"job_id": "JOB-0001", "node": "N9", "cases": cases, "expected_cases": cases,
           "md5s": md5s, "seed": "1", "sandbox_root": str(ctx.run_dir / "sandbox"),
           "evidence_dir": str(ctx.run_dir / "evidence")}
    first = FakeData(state={"n9_job": job})
    resume = FakeData(state={"n9_job": job})
    resume.is_resume = True
    resume.resume = SimpleNamespace(value={"job_id": "JOB-0001", "phase": "done", "rc": 0})
    return first, resume


async def test_n9_park_aggregates_evidence_and_releases_slot(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#8/A7：恢复后以逐例证据聚合（不信任 resume 数字），终值落 state 并释放单槽。"""
    cases = ["tc_demo", "tc_other"]
    md5s = {}
    for case in cases:
        sandbox = ctx.run_dir / "sandbox" / "TESTLIB" / f"{case}.sv"
        sandbox.parent.mkdir(parents=True, exist_ok=True)
        sandbox.write_text("module x; endmodule\n", encoding="utf-8")
        md5s[case] = _md5(sandbox)
        _write_case_log(ctx, case)
    monkeypatch.setattr(long_jobs, "aggregate_evidence", _fake_aggregate)
    first, resume = _n9_job_and_resume(ctx, cases, md5s)

    parked = await long_jobs.n9_park(first)
    assert parked["status"] == "waiting"
    out = await long_jobs.n9_park(resume)
    assert out["target_cases"] == cases
    assert out["counts"]["both_zero"] is True
    assert out["identity"]["consistent"] is True
    assert out["verdict"]["passed"] is True
    assert ctx.admission.released and ctx.admission.released[0]["job_id"] == f"N9-{RUN_ID}"
    kinds = [e["kind"] for e in ctx.progress.read()]
    assert "job_finished" in kinds


async def test_n9_park_missing_case_log_is_fail_closed(
        ctx: RunCtx, env_repo: Path) -> None:
    """#8/A7：没有日志 ⇒ 不得把「没跑出证据」当通过（fail closed）。"""
    cases = ["tc_demo"]
    sandbox = ctx.run_dir / "sandbox" / "TESTLIB" / "tc_demo.sv"
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    sandbox.write_text("module x; endmodule\n", encoding="utf-8")
    _, resume = _n9_job_and_resume(ctx, cases, {"tc_demo": _md5(sandbox)})
    with pytest.raises(RuntimeError, match="没有 run.log"):
        await long_jobs.n9_park(resume)


# ================================================================ #9/A15 N15


async def test_n15_real_submits_serial_job_and_reports_final_not_provisional(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#9/A15/I13：真实回归走单作业串行；终值来自日志聚合，不再发 provisional。"""
    cases = ["tc_demo"]
    monkeypatch.setattr(long_jobs, "aggregate_evidence", _fake_aggregate)
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n15_set": {"cases": cases, "g3_decision": "milestone_only"}})
    parked = await long_jobs.n15_run(data)
    assert parked["status"] == "waiting"
    assert ctx.runner.submitted and "--mode full" in ctx.runner.submitted[0]["command"]

    resume = FakeData(resources={"repo_root": env_repo},
                      state={"n15_set": {"cases": cases, "g3_decision": "milestone_only"},
                             "n15_job": data.get_state("n15_job")})
    resume.is_resume = True
    resume.resume = SimpleNamespace(value={"job_id": "JOB-0001", "phase": "done", "rc": 0})
    _write_case_log(ctx, "tc_demo")
    out = await long_jobs.n15_run(resume)
    assert out["executed"] is True and out["simulated"] is False
    assert "run_tc.py 未接入" in out["cross_machine"]
    assert ctx.admission.released
    blob = json.dumps(ctx.progress.read(), ensure_ascii=False)
    assert '"provisional": true' not in blob, "终值不得再冒充临时进度"


async def test_n15_drill_is_explicit_noop_without_failing(ctx: RunCtx) -> None:
    """drill 兼容：n15_run 不真跑、不抛错、显式 simulated=True。"""
    ctx.mode = "drill"
    data = FakeData(state={"n15_set": {"cases": ["tc_pcie_rw_02"], "g3_decision": "defer"}})
    out = await long_jobs.n15_run(data)
    assert out["simulated"] is True and out["executed"] is False
    assert ctx.runner.submitted == []


# ================================================================ #1/C3 + #22/I7 N8


async def test_n8_real_standin_is_fail_closed(ctx: RunCtx, env_repo: Path) -> None:
    """#1/C3：real 下没有真实复核输出 ⇒ 不得默认 pass。"""
    _sandbox_case(ctx)
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [_sandbox_case(ctx)]}})
    with pytest.raises(RuntimeError, match="standin"):
        await model_steps.n8_check(data)


async def test_n8_validation_failure_and_missing_verdict_are_node_failed(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#1/C3：validation.ok=False / verdict 缺失 ⇒ node_failed（严禁 `or "pass"`）。"""
    _sandbox_case(ctx)
    state = {"n6_applied": {"cases": [_sandbox_case(ctx)]}}

    async def failed(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False, "validation": {"ok": False, "problems": ["bad"]},
                "data": None, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", failed)
    with pytest.raises(RuntimeError, match="校验失败"):
        await model_steps.n8_check(FakeData(resources={"repo_root": env_repo}, state=state))

    async def missing_verdict(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": {}},
                "data": {}, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", missing_verdict)
    with pytest.raises(RuntimeError, match="verdict 缺失或非法"):
        await model_steps.n8_check(FakeData(resources={"repo_root": env_repo}, state=state))


async def test_n8_pass_writes_static_check_and_rework_counts_to_ledger(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#11/I2 + #1：N8 pass ⇒ 台账 static_check=pass；rework ⇒ 已退回且计数 +1。"""
    _case_state_init(ctx)
    _case_state_set(ctx, "tc_demo", "已修订待验", md5_after="m", file="TESTLIB/tc_demo.sv")
    state = {"n6_applied": {"cases": [_sandbox_case(ctx)], "targets": []}}

    def out_factory(verdict: str):  # noqa: ANN202
        async def _fn(*a: Any, **k: Any) -> dict[str, Any]:
            data = {"verdict": verdict, "findings": [], "must_fix": []}
            return {"mode": "live", "standin": False,
                    "validation": {"ok": True, "problems": [], "accepted": data},
                    "data": data, "provider": "fake"}
        return _fn

    monkeypatch.setattr(model_steps, "run_model_node", out_factory("pass"))
    fake = FakeData(resources={"repo_root": env_repo}, state=state)
    await model_steps.n8_check(fake)
    assert _ledger(ctx)["cases"][0]["static_check"] == "pass"
    assert ("N8_PASS" in [e for e, _ in fake.emitted])

    monkeypatch.setattr(model_steps, "run_model_node", out_factory("rework"))
    fake2 = FakeData(resources={"repo_root": env_repo}, state=state)
    await model_steps.n8_check(fake2)
    led = _ledger(ctx)
    assert led["cases"][0]["state"] == "已退回"
    assert led["rework_cycles"]["n6_n8_cycles"] == 1
    assert "N8_REWORK" in [e for e, _ in fake2.emitted]


async def test_i7_rework_limit_escalates_and_first_revision_does_not_consume(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#22/I7：首轮修订不消耗预算；返工到 limit ⇒ N8_ESCALATE（不再 rework/halt）。"""
    _case_state_init(ctx)
    _n5_n2_for_targets(ctx)
    # 首轮：N6 不得自增（台账无 rework_cycles 变化）
    async def standin(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "standin", "standin": True, "validation": {"ok": True, "problems": []},
                "data": {}, "provider": "none"}

    monkeypatch.setattr(model_steps, "run_model_node", standin)
    n6_data = FakeData(resources={"repo_root": env_repo}, input={"baseline": "v0"})
    await model_steps.n6_author(n6_data)
    led = _ledger(ctx)
    assert (led.get("rework_cycles") or {}).get("n6_n8_cycles", 0) == 0

    _case_state_set(ctx, "tc_demo", "已修订待验", rework_cycles=2)
    _case_state_set(ctx, "tc_demo", "已修订待验", static_check="pass")

    async def rework(*a: Any, **k: Any) -> dict[str, Any]:
        data = {"verdict": "rework", "findings": [{"item": "x", "result": "fail", "basis": "f:1"}],
                "must_fix": ["fix it"]}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": data},
                "data": data, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", rework)
    fake = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [_sandbox_case(ctx)]}})
    out = await model_steps.n8_check(fake)
    assert out["escalated"] is True
    assert "N8_ESCALATE" in [e for e, _ in fake.emitted]
    assert "N8_REWORK" not in [e for e, _ in fake.emitted]
    assert _ledger(ctx)["rework_cycles"]["n6_n8_cycles"] == 3  # == limit：记录已到上限


# ================================================================ #15/A10 N11


def _n11_state(ctx: RunCtx, *, reviewed: str, run_md5: str) -> dict[str, Any]:
    evidence_path = _write_case_log(ctx, "tc_demo")
    return {
        "n6_applied": {"cases": [{"case": "tc_demo", "md5_after": reviewed}]},
        "n9_result": {"cases": {"tc_demo": {
            "present": True, "path": str(evidence_path),
            "identity": {"run_id": ctx.run_id, "case": "tc_demo", "case_md5": run_md5,
                         "seed": "1"},
        }}},
        "n10_reconcile": {"counts": {"both_zero": True}, "verdict": {"passed": True}},
    }


async def test_n11_drill_standin_emits_intact(ctx: RunCtx) -> None:
    """drill 兼容：N11 standin 必须发 N11_INTACT（accept_v1 要走到 G2）。"""
    ctx.mode = "drill"
    data = FakeData(state={})
    out = await model_steps.n11_review(data)
    assert out["chain_effective"] == "intact"
    assert "N11_INTACT" in [e for e, _ in data.emitted]


async def test_n11_real_standin_is_fail_closed(ctx: RunCtx, env_repo: Path) -> None:
    """#15/A10：real 下无真实 guardian 结论 ⇒ 不得判 intact。"""
    data = FakeData(resources={"repo_root": env_repo},
                    state=_n11_state(ctx, reviewed="a" * 32, run_md5="a" * 32))
    with pytest.raises(RuntimeError, match="standin"):
        await model_steps.n11_review(data)


async def test_n11_host_identity_mismatch_forces_broken_and_rework_edge(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#15/A10：身份四方同值不成立 ⇒ chain=broken + N11_REWORK（显式回边 N6）。"""
    async def broken(*a: Any, **k: Any) -> dict[str, Any]:
        data = {"chain": "broken",
                "reasons": ["审的 md5 != 跑的 md5"],
                "rework_requests": [{"case": "tc_demo", "what": "重采证据", "basis": "md5 不符"}],
                "caveats": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": data},
                "data": data, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", broken)
    fake = FakeData(resources={"repo_root": env_repo},
                    state=_n11_state(ctx, reviewed="a" * 32, run_md5="b" * 32))
    out = await model_steps.n11_review(fake)
    assert out["chain_effective"] == "broken"
    assert out["host_identity"]["consistent"] is False
    assert out["rework_requests"]
    assert "N11_REWORK" in [e for e, _ in fake.emitted]


async def test_n11_model_cannot_claim_intact_against_host_facts(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#15/A10：Host 事实不一致而模型判 intact ⇒ fail closed（不得掩盖身份错位）。"""
    async def intact(*a: Any, **k: Any) -> dict[str, Any]:
        data = {"chain": "intact", "reasons": ["看起来没问题"], "rework_requests": [], "caveats": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": data},
                "data": data, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", intact)
    fake = FakeData(resources={"repo_root": env_repo},
                    state=_n11_state(ctx, reviewed="a" * 32, run_md5="b" * 32))
    with pytest.raises(RuntimeError, match="不得判 intact"):
        await model_steps.n11_review(fake)


# ================================================================ #18/#11 N3/N10/N12 + I2


async def test_n3_writes_digest_file_drill_and_real_standin(
        ctx: RunCtx, env_repo: Path, tmp_path: Path) -> None:
    """#18/A21：N3 落盘；drill 从夹具写、real standin 不冒充夹具。"""
    ctx.mode = "drill"
    ctx.fixture = P.KB_RUNS / "RUN-20261015-120626"
    data = FakeData(state={"n2_diff": {"diff_count": 2}})
    await model_steps.n3_digest(data)
    written = (ctx.run_dir / "n3_digest.md").read_text(encoding="utf-8")
    fixture = ctx.read_fixture_text("n3_digest.md")
    assert fixture is not None and written == fixture

    ctx2 = use_ctx(RunCtx(run_id=RUN_ID, run_dir=tmp_path / "runs2" / RUN_ID, mode="real",
                  scenario="happy", kb=ctx.kb, progress=ProgressLog(tmp_path / "e2", RUN_ID),
                  admission=FakeAdmission(), runner=FakeRunner()))
    ctx2.run_dir.mkdir(parents=True)
    # real+standin ⇒ fail closed（real 端到端需 live provider；standin 不冒充）
    with pytest.raises(RuntimeError, match="live provider"):
        await model_steps.n3_digest(FakeData(state={"n2_diff": {}}))
    assert not (ctx2.run_dir / "n3_digest.md").exists()


async def test_n3_validation_failure_aborts_round(
        ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    """#18/A21：N3 解析失败 ⇒ 显式终止（不得把空摘要送进闸门1）。"""
    async def failed(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False, "validation": {"ok": False, "problems": ["bad"]},
                "data": None, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", failed)
    with pytest.raises(RuntimeError, match="N3：差异摘要校验失败"):
        await model_steps.n3_digest(FakeData(state={"n2_diff": {}}))


def _n10_state(ctx: RunCtx) -> tuple[FakeData, dict[str, Any], Path]:
    _case_state_init(ctx)
    _case_state_set(ctx, "tc_demo", "已修订待验", static_check="pass", compile_rc=0)
    log = ctx.run_dir / "evidence" / "20261019-120000_tc_demo_1_run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "UVM_INFO tc_demo.sv(10) @ 1.0 us [PCIE_REG_RD@3DW] *E @ADDR[0x4] -> DATA[0x0] != EXP[0xffffffff]\n"
        "UVM Report Summary\n"
        "UVM_ERROR :    0\n"
        "UVM_FATAL :    0\n",
        encoding="utf-8",
    )
    (ctx.run_dir / "n2_diff.json").write_text(json.dumps({
        "diffs": [{"entry_id": "0x0000#0x0004", "id": "0x0000#0x0004",
                   "segment": "0x0000", "offset": "0x4", "kind": "doc_entry"}],
    }, ensure_ascii=False), encoding="utf-8")
    n9 = {
        "target_cases": ["tc_demo"], "run_md5s": {"tc_demo": "m" * 32},
        "counts": {"koutou1": {"value": 0, "zero": True}, "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}, "zero": True}, "both_zero": True},
        "verdict": {"passed": True, "reasons": []},
        "identity": {"consistent": True, "mismatches": []},
        "evidence": {"path": str(log), "present": True},
        "cases": {"tc_demo": {
            "present": True, "path": str(log), "has_report_summary": True,
            "counts": {"koutou1": {"value": 0, "zero": True},
                       "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}, "zero": True,
                                   "uvm_summary_present": True},
                       "both_zero": True},
            "imprints": {"N6_FPGA_DATE_PCIE": {"consistent": True, "verified_count": 4,
                                              "observed": {"id_count": 1},
                                              "expected": {"address": "0x0000+0x04"}}},
            "verdict": {"passed": True, "reasons": []},
            "identity": {"run_id": ctx.run_id, "case": "tc_demo", "case_md5": "m" * 32},
        }},
    }
    state = {"n9_result": n9, "n7_compile": {"cases": [{"case": "tc_demo", "rc": 0}]}}
    return FakeData(resources={"repo_root": ctx.run_dir}, state=state), n9, log


async def test_n10_persists_reconcile_and_pending_and_writes_case_state(
        ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    """#18/A9 + #11/I2：对账文件 + 待裁决清单落盘；通过用例写「已验证通过」。"""
    data, n9, _log = _n10_state(ctx)
    pending_calls: list[list[str]] = []
    real_tool = model_steps.run_kb_tool

    def fake_tool(tool: str, args: list[str], **kw: Any) -> dict[str, Any]:
        if tool == "n10_pending.py":
            pending_calls.append(args)
            return {"cmd": "fake", "rc": 0, "stdout_tail": "ok", "stderr_tail": ""}
        return real_tool(tool, args, **kw)

    monkeypatch.setattr(model_steps, "run_kb_tool", fake_tool)

    async def classify(*a: Any, **k: Any) -> dict[str, Any]:
        buckets = (k.get("offered") or {}).get("buckets") or []
        items = [{"bucket_id": b["bucket_id"], "classification": "待裁决",
                  "basis": "地址落在修订点，需人裁决"} for b in buckets]
        payload = {"items": items, "summary": "需裁决", "unclassified": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": payload},
                "data": payload, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", classify)
    out = await model_steps.n10_reconcile(data)
    assert out["pending_items"], "分类 2/3 必须产 pending items"
    assert pending_calls, "必须调用 n10_pending.py（唯一写者）"
    assert Path(out["reconcile_md_path"]).is_file()
    assert Path(out["pending_path"]).is_file() or out["pending_written"].startswith("kb/tools")
    assert _ledger(ctx)["cases"][0]["state"] == "已验证通过"


async def test_n10_classification_validation_failure_blocks_gate2(
        ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    """#18/C10：N10 分类校验失败 ⇒ node_failed（不得带空分类进 N11/N12）。"""
    data, _n9, _log = _n10_state(ctx)

    async def failed(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False,
                "validation": {"ok": False, "problems": ["bad bucket"]},
                "data": None, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", failed)
    with pytest.raises(RuntimeError, match="FAIL 三分类校验失败"):
        await model_steps.n10_reconcile(data)


async def test_n10_real_standin_is_fail_closed(ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    data, _n9, _log = _n10_state(ctx)
    monkeypatch.setattr(model_steps, "run_model_node",
                        awaitable_standin())
    with pytest.raises(RuntimeError, match="standin"):
        await model_steps.n10_reconcile(data)


def awaitable_standin():  # noqa: ANN001
    async def _fn(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "standin", "standin": True, "validation": {"ok": True, "problems": []},
                "data": {}, "provider": "none"}
    return _fn


async def test_n12_writes_report_and_rejects_unresolvable_refs(
        ctx: RunCtx, monkeypatch: pytest.MonkeyPatch) -> None:
    """#18/A20：报告落盘；refs 不可解析 ⇒ 拒发。"""
    log = _write_case_log(ctx, "tc_demo")
    state = {
        "n10_reconcile": {"counts": {"koutou1": {"value": 0}, "koutou2": {"value": {"UVM_ERROR": 0}}},
                          "verdict": {"passed": False}},
        "n9_result": {"cases": {"tc_demo": {"present": True, "path": str(log)}},
                      "evidence_paths": {"tc_demo": str(log)}},
        "n11_review": {"chain_effective": "intact"},
        "n5_impact": {"must_change_count": 1, "must_change_cases": ["tc_demo"]},
    }
    good = {"title": "报告", "claimed_verdict": "not_passed",
            "counts_quoted": {"koutou1": 0, "koutou2": {"UVM_ERROR": 0}},
            "sections": [{"heading": "证据", "body_md": "见日志", "refs": [str(log)]}],
            "open_items": []}

    async def ok(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": good},
                "data": good, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", ok)
    data = FakeData(state=dict(state))
    out = await model_steps.n12_report(data)
    assert Path(out["report_path"]).is_file()
    assert out["refs_checked"] == [str(log)] and out["unresolved_refs"] == []

    bad = dict(good, sections=[{"heading": "x", "body_md": "y", "refs": ["no/such/file.md"]}])

    async def unresolved(*a: Any, **k: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": bad},
                "data": bad, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", unresolved)
    data2 = FakeData(state=dict(state))
    report_path = ctx.run_dir / "n12_report.md"
    if report_path.exists():
        report_path.unlink()
    with pytest.raises(RuntimeError, match="引用不可解析"):
        await model_steps.n12_report(data2)
    assert not report_path.exists(), "引用不可解析 ⇒ 不得落报告（拒发）"


async def test_n12_real_standin_is_fail_closed(ctx: RunCtx) -> None:
    data = FakeData(state={"n10_reconcile": {"counts": {}, "verdict": {}}})
    with pytest.raises(RuntimeError, match="standin"):
        await model_steps.n12_report(data)


# ================================================================ 回归：drill 夹具台账不得冒充本轮


async def test_case_state_identity_mismatch_fails_closed(ctx: RunCtx) -> None:
    """回归（WS-K/Lead 报的 drill 污染）：run_id 不符 ⇒ fail closed，不得 --force 覆盖。"""
    (ctx.run_dir / "case_states.json").write_text(json.dumps({
        "schema": "kb/run/case_states", "version": 1,
        "run_id": "RUN-20261015-120626", "updated_at": "2026-10-15T12:55:44+0800",
        "cases": [{"case": "tc_old", "state": "已修订待验"}],
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(RuntimeError, match="身份错位"):
        model_steps._ensure_case_state(ctx)
    # 旧台账不得被覆盖（fail closed 不产生副作用）
    assert json.loads((ctx.run_dir / "case_states.json").read_text(encoding="utf-8"))["run_id"] == "RUN-20261015-120626"


async def test_n11_rework_budget_is_bounded_by_limit(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """I7：证据链 broken 的返工也吃预算；到 limit ⇒ 显式失败升级人工（不死循环）。"""
    _case_state_init(ctx)
    _case_state_set(ctx, "tc_demo", "已修订待验", rework_cycles=2)
    _case_state_set(ctx, "tc_demo", "已修订待验", static_check="pass")

    async def broken(*a: Any, **k: Any) -> dict[str, Any]:
        data = {"chain": "broken", "reasons": ["md5 不符"],
                "rework_requests": [{"case": "tc_demo", "what": "重采", "basis": "md5"}],
                "caveats": []}
        return {"mode": "live", "standin": False,
                "validation": {"ok": True, "problems": [], "accepted": data},
                "data": data, "provider": "fake"}

    monkeypatch.setattr(model_steps, "run_model_node", broken)
    fake = FakeData(resources={"repo_root": env_repo},
                    state=_n11_state(ctx, reviewed="a" * 32, run_md5="b" * 32))
    out = await model_steps.n11_review(fake)
    # 超限 ⇒ 升级 N13（N11_ESCALATE→gate2），不再直接失败/死循环
    assert "N11_ESCALATE" in [e for e, _ in fake.emitted]
    assert out["cycle"] == 3 and out["limit"] == 3
    assert _ledger(ctx)["rework_cycles"]["n6_n8_cycles"] == 3
    statuses = [e["status"] for e in ctx.progress.read() if e.get("node") == "N11"]
    assert "escalated" in statuses, statuses


async def test_n6_author_consumes_n11_rework_requests(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """回边契约：N11_REWORK 的返工请求必须进入下一轮 N6 的 input.rework_reasons。"""
    _n5_n2_for_targets(ctx)
    captured: dict[str, Any] = {}

    async def capture(*a: Any, **k: Any) -> dict[str, Any]:
        captured.update(k.get("input_data") or {})
        return {"mode": "standin", "standin": True, "validation": {"ok": True, "problems": []},
                "data": {}, "provider": "none"}

    monkeypatch.setattr(model_steps, "run_model_node", capture)
    fake = FakeData(resources={"repo_root": env_repo}, state={
        "n11_review": {"rework_requests": [{"case": "tc_demo", "what": "重采证据",
                                            "basis": "审的 md5 != 跑的 md5"}]},
        "n5_impact": {"must_change_cases": ["tc_demo"], "must_change_count": 1},
    })
    await model_steps.n6_author(fake)
    assert any("重采证据" in r for r in captured.get("rework_reasons") or []), captured


async def test_drill_case_state_skip_is_explicit_not_silent(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Lead 裁决：drill 不写 case_state 必须**显式留痕**（drill_skips_case_state 事件），不得静默跳过。"""
    ctx.mode = "drill"
    _sandbox_case(ctx)
    data = FakeData(resources={"repo_root": env_repo},
                    state={"n6_applied": {"cases": [_sandbox_case(ctx)]}})
    await model_steps.n8_check(data)
    skip_events = [e for e in ctx.progress.read()
                   if e.get("status") == "drill_ledger_skipped"]
    assert skip_events, [e.get("status") for e in ctx.progress.read()]
    assert "drill 替身复核不写用例态台账" in (skip_events[0].get("detail") or {}).get("rule", "")


# ================================================================ drill N9 第二轮（G2 rework）回归


async def test_drill_n9_second_round_survives_readonly_archive(
        ctx: RunCtx, env_repo: Path, tmp_path: Path) -> None:
    """回归（WS-L 实测）：drill 第二轮 N9 不能因归档件 444 而 cp 失败并丢 rc。

    JobRunner 在命令后追加 `__rc=$?; echo $__rc > rc`；若命令串顶层 `set -e` 因 cp 失败
    退出 ⇒ rc 文件写不出 ⇒ poll() 判 dead ⇒ 把「归档件已存在」误判成死任务。
    修法：`set -e` 放子 shell + 先 `rm -f` 目标。这里直接执行两轮命令并验证 rc=0。
    """
    import subprocess

    ctx.mode = "drill"
    fixture = tmp_path / "fixture"
    (fixture / "evidence").mkdir(parents=True)
    (fixture / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log").write_text(
        "UVM Report Summary\nUVM_ERROR :    0\n", encoding="utf-8")
    ctx.fixture = fixture
    data = FakeData(resources={"repo_root": env_repo})
    out = await long_jobs.n9_submit(data)
    assert out["job_id"] == "JOB-0001"
    command = ctx.runner.submitted[0]["command"]
    assert "( set -e;" in command and "rm -f" in command

    rc_path = tmp_path / "drill_job.rc"
    for round_no in (1, 2):
        wrapped = f"{command}\n__rc=$?\necho $__rc > {str(rc_path)!r}\nexit $__rc"
        proc = subprocess.run(["/bin/bash", "-lc", wrapped], cwd=str(env_repo),
                              capture_output=True, text=True)
        assert rc_path.is_file(), f"第 {round_no} 轮 rc 文件未写出：{proc.stderr[-500:]}"
        assert rc_path.read_text(encoding="utf-8").strip() == "0", (
            f"第 {round_no} 轮 rc != 0：{proc.stderr[-800:]}")
        arch = ctx.run_dir / "evidence" / "archive" / f"{RUN_ID}_tc_pcie_rw_02_1_DRILLFIXTURE.log"
        assert arch.is_file()
        assert arch.stat().st_mode & 0o200 == 0, "归档件必须只读（444）"
    prov = ctx.run_dir / "evidence" / "archive" / "DRILL_FIXTURE_PROVENANCE.txt"
    assert prov.is_file() and prov.stat().st_mode & 0o200 == 0
