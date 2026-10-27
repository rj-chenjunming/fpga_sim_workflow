"""S0-b 判据：派生 → 提议 → 人确认 → 落盘 → 冒烟读数 → 准出开关。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §8.2 / §8.4 红线 6-7（2026-10-27 修订）。
这些用例只钉"不读源码也能判"的五条：

1. **未确认不落盘**：没有 `human:` 确认时，副本 TB 顶层逐字节不变；
2. **确认只增不改**：同一 hunk 再确认是追加（旧记录保留且带锚，改锚即报错）；
3. **精确替换**：`old_text` 必须恰好出现一次，否则拒绝落盘（不猜位置）；
4. **ports 判据**：派生不成立 ⇒ failed；差异未覆盖/未确认 ⇒ waiting；内容与"基线+已确认"一致 ⇒ passed；
5. **冒烟读数**：`Compilation: 0 error(s)` 不能被当成 1 条错误；warning 走基线相对增量；
   六项全 passed 才 `ready_for_execution=True`。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from host import s0b, uvs_logs
from host.s0 import S0Store


def _tb(text: str) -> str:
    return text


@pytest.fixture()
def store_env(tmp_path):
    """可写数据根 + 基线（含 TB/top.sv，因为夹具里没有编译驱动的 tbtop.sv）。"""
    baseline = tmp_path / "baseline"
    for name in ("RTL", "TB", "PKG", "TESTLIB", "docs"):
        (baseline / name).mkdir(parents=True)
    (baseline / "RTL/dut.v").write_text(
        "module dut_top(\n    input  [7:0] din,\n    output     dout\n);\nendmodule\n",
        encoding="utf-8")
    (baseline / "TB/top.sv").write_text(
        "module top;\n  dut_top u_dut(.din(din), .dout(dout));\nendmodule\n", encoding="utf-8")
    (baseline / "run").write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    (baseline / "all_define.txt").write_text("-define SIM\n", encoding="utf-8")
    rtl = tmp_path / "src/rtl"
    rtl.mkdir(parents=True)
    (rtl / "dut.v").write_text(
        "module dut_top(\n    input  [7:0] din,\n    output     dout\n);\nendmodule\n",
        encoding="utf-8")
    store = S0Store(tmp_path / "records", [tmp_path])
    payload = dict(baseline=str(baseline), baseline_version="v1", rtl_source=str(rtl),
                   work_env=str(tmp_path / "work"), now="2026-10-27T12:00:00+00:00")
    return store, payload, tmp_path


def _prepare(store_env):
    store, payload, tmp = store_env
    record = store.prepare(payload)
    return store, record, Path(payload["baseline"]), Path(payload["work_env"]), store.root / record["id"]


# ---------------------------------------------------------------- TB 顶层解析

def test_resolve_tb_top_prefers_compile_driver(tmp_path: Path) -> None:
    assert s0b.driver_tb_top() == "TB/tbtop.sv"          # 仓库里的 run_guarded.sh 就编这个
    (tmp_path / "TB").mkdir()
    (tmp_path / "TB/tbtop.sv").write_text("module tbtop; endmodule\n", encoding="utf-8")
    assert s0b.resolve_tb_top(tmp_path) == "TB/tbtop.sv"


def test_resolve_tb_top_falls_back_to_legacy_name(tmp_path: Path) -> None:
    (tmp_path / "TB").mkdir()
    (tmp_path / "TB/top.sv").write_text("module top; endmodule\n", encoding="utf-8")
    assert s0b.resolve_tb_top(tmp_path) == "TB/top.sv"


def test_resolve_run_entry_accepts_real_env_names(tmp_path: Path) -> None:
    """契约原写 `run` 文件，真实环境没有；run_tc.py / run_uvs_new.sh / doc/tools/run_local.sh 都算入口。"""
    (tmp_path / "run_tc.py").write_text("# 真实环境的运行入口\n", encoding="utf-8")
    assert s0b.resolve_run_entry(tmp_path) == "run_tc.py"
    (tmp_path / "run").write_text("#!/bin/sh\n", encoding="utf-8")
    assert s0b.resolve_run_entry(tmp_path) == "run"          # 契约写法优先
    with pytest.raises(ValueError):
        s0b.resolve_run_entry(tmp_path / "empty-path")


def test_resolve_tb_top_never_guesses(tmp_path: Path) -> None:
    (tmp_path / "TB").mkdir()
    with pytest.raises(ValueError):
        s0b.resolve_tb_top(tmp_path)


# ---------------------------------------------------------------- 提议

def test_propose_requires_model_or_host_actor(store_env) -> None:
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    with pytest.raises(ValueError):
        s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "a", "new_text": "b",
                              "reason": "r"}], actor="human:someone")
    assert not (folder / "s0b/proposals.json").exists()


def test_propose_validates_hunk_shape(store_env) -> None:
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    base = {"hunk_id": "H1", "file": "TB/top.sv", "old_text": "x", "new_text": "y", "reason": "r"}
    with pytest.raises(ValueError):                       # file 不在 TB/ 下
        s0b.propose(folder, [dict(base, file="../etc/passwd")], actor="model:m")
    with pytest.raises(ValueError):                       # old_text == new_text
        s0b.propose(folder, [dict(base, new_text="x")], actor="model:m")
    with pytest.raises(ValueError):                       # 缺 reason
        s0b.propose(folder, [dict(base, reason="")], actor="model:m")


# ---------------------------------------------------------------- 确认（只增不改）

def test_confirm_requires_human_and_known_hunk(store_env) -> None:
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "a", "new_text": "b",
                          "reason": "r"}], actor="model:m")
    with pytest.raises(ValueError):
        s0b.confirm(folder, "H1", "confirmed", actor="model:m")
    with pytest.raises(ValueError):
        s0b.confirm(folder, "H9", "confirmed", actor="human:me")


def test_confirmations_are_append_only_with_anchor(store_env) -> None:
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "a", "new_text": "b",
                          "reason": "r"}], actor="model:m")
    s0b.confirm(folder, "H1", "rejected", actor="human:me", reason="先不改")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me", reason="改成这样")
    rows = s0b.load_confirmations(folder)
    assert [r["decision"] for r in rows] == ["rejected", "confirmed"]      # 历史保留
    assert s0b.decisions_of(folder) == {"H1": "confirmed"}                 # 最后一条生效
    # 改锚必须被发现（只增不改的机制证据）
    path = folder / "s0b/confirmations.jsonl"
    tampered = path.read_text(encoding="utf-8").replace("human:me", "human:evil", 1)
    path.write_text(tampered, encoding="utf-8")
    with pytest.raises(ValueError):
        s0b.load_confirmations(folder)


# ---------------------------------------------------------------- 落盘（仅已确认）

def test_unconfirmed_hunk_never_touches_tb(store_env) -> None:
    store, record, baseline, work, folder = _prepare(store_env)
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": ".din(din)",
                          "new_text": ".din(din), .extra(1'b0)", "reason": "新增端口"}],
                actor="model:m")
    before = (work / record["tb_top"]).read_bytes()
    result = store.apply(record["id"])
    assert result["applied"] == []
    assert (work / record["tb_top"]).read_bytes() == before


def test_confirmed_hunk_is_applied_exactly(store_env) -> None:
    store, record, baseline, work, folder = _prepare(store_env)
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": ".din(din)",
                          "new_text": ".din(din[7:0])", "reason": "位宽对齐",
                          "addresses": ["dut_top:din"]}], actor="model:m")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me")
    result = store.apply(record["id"])
    assert result["applied"] == ["H1"]
    assert result["md5_before"] != result["md5_after"]
    assert ".din(din[7:0])" in (work / record["tb_top"]).read_text(encoding="utf-8")


def test_ambiguous_old_text_is_refused(store_env) -> None:
    store, record, baseline, work, folder = _prepare(store_env)
    text = (work / record["tb_top"]).read_text(encoding="utf-8")
    (work / record["tb_top"]).write_text(text.replace("endmodule", "endmodule\n// endmodule\n"),
                                         encoding="utf-8")
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "endmodule",
                          "new_text": "endmodule // x", "reason": "歧义探针"}], actor="model:m")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me")
    with pytest.raises(ValueError):
        store.apply(record["id"])


# ---------------------------------------------------------------- ports 判据

def test_ports_passed_when_no_diff_and_tb_untouched(store_env) -> None:
    store, record, *_ = _prepare(store_env)
    assert record["tb_top"] == "TB/top.sv"
    assert {c["key"]: c["status"] for c in record["checks"]}["ports"] == "passed"


def test_ports_waiting_when_diff_not_yet_proposed(store_env) -> None:
    store, payload, tmp = store_env
    (Path(payload["rtl_source"]) / "dut.v").write_text(
        "module dut_top(\n    input  [7:0] din,\n    input extra,\n    output     dout\n);\nendmodule\n",
        encoding="utf-8")
    record = store.prepare(payload)
    assert {c["key"]: c["status"] for c in record["checks"]}["ports"] == "waiting"
    assert record["ports"]["table"][0]["module"] == "dut_top"
    assert record["ready_for_execution"] is False


def test_ports_passed_when_diff_rejected_and_tb_unchanged(store_env) -> None:
    """差异被**人明确否决**（不改 TB）也算处置完毕——但必须有人签。"""
    store, payload, tmp = store_env
    (Path(payload["rtl_source"]) / "dut.v").write_text(
        "module dut_top(\n    input  [7:0] din,\n    input extra,\n    output     dout\n);\nendmodule\n",
        encoding="utf-8")
    record = store.prepare(payload)
    folder = store.root / record["id"]
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "dut_top u_dut",
                          "new_text": "dut_top u_dut2", "reason": "不适用", "addresses": ["dut_top"]}],
                actor="model:m")
    s0b.confirm(folder, "H1", "rejected", actor="human:me", reason="该端口 TB 不连")
    fresh = store.get(record["id"])
    assert {c["key"]: c["status"] for c in fresh["checks"]}["ports"] == "passed"


def test_ports_failed_when_derivation_not_ok(store_env) -> None:
    store, payload, tmp = store_env
    (Path(payload["rtl_source"]) / "legacy.v").write_text(
        "module legacy(a, b);\n  input a;\n  output b;\nendmodule\n", encoding="utf-8")
    record = store.prepare(payload)
    assert {c["key"]: c["status"] for c in record["checks"]}["ports"] == "failed"
    assert record["ready_for_execution"] is False


def test_ports_failed_when_tb_has_unregistered_change(store_env) -> None:
    store, record, baseline, work, folder = _prepare(store_env)
    text = (work / record["tb_top"]).read_text(encoding="utf-8")
    (work / record["tb_top"]).write_text(text.replace("u_dut", "u_dut_hand"), encoding="utf-8")
    fresh = store.get(record["id"])
    assert {c["key"]: c["status"] for c in fresh["checks"]}["ports"] == "failed"
    assert "未登记" in fresh["ports"]["reason"] or "不一致" in fresh["ports"]["reason"]


# ---------------------------------------------------------------- 冒烟读数

def test_summary_line_is_the_only_error_source(tmp_path: Path) -> None:
    log = tmp_path / "x_c_rtl.log"
    log.write_text("Warning-120002: Command option warning\nWarning-121147: Redefinition\n"
                   "Compilation: 0 error(s), 13 warning(s)\n", encoding="utf-8")
    report = uvs_logs.parse_log(log)
    assert report.ok is True and report.errors == 0 and report.warnings == 13
    assert report.warning_codes == {"Warning-120002": 1, "Warning-121147": 1}
    assert "error" in log.read_text(encoding="utf-8")     # 文本里有 error 字样，但不是错误计数


def test_missing_summary_is_not_zero_errors(tmp_path: Path) -> None:
    log = tmp_path / "x_c_tb.log"
    log.write_text("something exploded\n", encoding="utf-8")
    report = uvs_logs.parse_log(log)
    assert report.ok is False and report.errors is None and report.warnings is None


def test_warning_delta_flags_added_and_count_increase() -> None:
    delta = uvs_logs.warning_delta({"Warning-120002": 1, "Warning-121147": 1},
                                   {"Warning-120002": 1, "Warning-120162": 1, "Warning-121147": 3})
    assert delta["added"] == ["Warning-120162"]
    assert delta["count_increase"] == [{"code": "Warning-121147", "baseline": 1, "candidate": 3}]
    assert delta["needs_evaluation"] == ["Warning-120162", "Warning-121147"]


def test_smoke_without_eda_is_waiting_not_passed(store_env, monkeypatch) -> None:
    store, record, *_ = _prepare(store_env)
    monkeypatch.setattr(s0b, "_uvlan_available", lambda: False)
    result = store.smoke(record["id"], case="tc_demo")
    assert result["status"] == "waiting" and "uvlan" in result["reason"]
    fresh = store.get(record["id"])
    assert {c["key"]: c["status"] for c in fresh["checks"]}["smoke"] == "waiting"
    assert fresh["ready_for_execution"] is False


# ---------------------------------------------------------------- 准出开关

def test_ready_requires_all_six_checks_passed() -> None:
    record = {"checks": [{"key": k, "status": "passed"} for k in
                         ("copy", "rtl", "non_rtl", "ports", "smoke", "baseline")]}
    assert s0b.ready_for_execution(record, Path(".")) is True
    record["checks"][4]["status"] = "waiting"
    assert s0b.ready_for_execution(record, Path(".")) is False
    record["checks"][4]["status"] = "passed"
    record["error"] = "boom"
    assert s0b.ready_for_execution(record, Path(".")) is False


# ---------------------------------------------------------------- 复核整改回归钉（2026-10-27）

def test_apply_then_get_is_not_drift_and_can_leave_ready(store_env) -> None:
    """复核 FAIL-1：合法授权落盘后不能被自己的"派生时见证"判成漂移。"""
    store, record, baseline, work, folder = _prepare(store_env)
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": ".din(din)",
                          "new_text": ".din(din[7:0])", "reason": "位宽对齐",
                          "addresses": ["dut_top:din"]}], actor="model:m")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me")
    result = store.apply(record["id"])
    assert result["applied"] == ["H1"] and result.get("witness")
    fresh = store.get(record["id"])
    assert fresh["status"] == "prepared", fresh.get("error")
    assert fresh["verification"]["drift"] == {}
    assert {c["key"]: c["status"] for c in fresh["checks"]}["ports"] == "passed"


def test_apply_is_idempotent(store_env) -> None:
    """复核 FAIL-9：已落盘的 hunk 再 apply 不能报错。"""
    store, record, baseline, work, folder = _prepare(store_env)
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": ".din(din)",
                          "new_text": ".din(din[7:0])", "reason": "位宽对齐"}], actor="model:m")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me")
    first = store.apply(record["id"])
    second = store.apply(record["id"])
    assert first["applied"] == ["H1"]
    assert second["applied"] == [] and second.get("already_applied") is True


def test_propose_can_be_appended(store_env) -> None:
    """复核 FAIL-2：第二次提议必须**追加**（不能 FileExistsError，也不能空列表锁死）。"""
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": "a", "new_text": "b",
                          "reason": "r1"}], actor="model:m")
    s0b.propose(folder, [{"hunk_id": "H2", "file": "TB/top.sv", "old_text": "c", "new_text": "d",
                          "reason": "r2"}], actor="model:m")
    assert [h["hunk_id"] for h in s0b.load_proposals(folder)] == ["H1", "H2"]
    with pytest.raises(ValueError):
        s0b.propose(folder, [], actor="model:m")


def test_ports_waiting_after_confirm_before_apply(store_env) -> None:
    """复核 FAIL-7：确认了但还没落盘 ⇒ waiting（不是 failed）。"""
    store, payload, tmp = store_env
    (Path(payload["rtl_source"]) / "dut.v").write_text(
        "module dut_top(\n    input  [7:0] din,\n    input extra,\n    output dout\n);\nendmodule\n",
        encoding="utf-8")
    record = store.prepare(payload)
    folder = store.root / record["id"]
    s0b.propose(folder, [{"hunk_id": "H1", "file": "TB/top.sv", "old_text": ".din(din)",
                          "new_text": ".din(din), .extra(1'b0)", "reason": "新增端口",
                          "addresses": ["dut_top:extra"]}], actor="model:m")
    s0b.confirm(folder, "H1", "confirmed", actor="human:me")
    fresh = store.get(record["id"])
    assert {c["key"]: c["status"] for c in fresh["checks"]}["ports"] == "waiting"
    assert "落盘" in fresh["ports"]["reason"]


def _fake_smoke(tmp_path, monkeypatch, *,
                candidate=(0, "Compilation: 0 error(s), 4 warning(s)"),
                baseline=(0, "Compilation: 0 error(s), 4 warning(s)")):
    """把 run_guarded 的 subprocess 换成夹具：按 --evidence-dir 落两段日志。"""
    import subprocess as real

    def fake_run(command, **kwargs):
        evidence = Path(command[command.index("--evidence-dir") + 1])
        evidence.mkdir(parents=True, exist_ok=True)
        label = "candidate" if "candidate" in str(evidence) else "baseline"
        rc, summary = candidate if label == "candidate" else baseline
        for segment in ("rtl", "tb"):
            (evidence / f"20261027-000000_tc_x_1_c_{segment}.log").write_text(
                summary + "\n", encoding="utf-8")
        return real.CompletedProcess(command, rc, stdout="", stderr="")

    monkeypatch.setattr(s0b, "_uvlan_available", lambda: True)
    monkeypatch.setattr(s0b.subprocess, "run", fake_run)


def _smoke_env(store_env):
    store, record, baseline, work, folder = _prepare(store_env)
    return store, record, folder


def test_smoke_requires_trustworthy_baseline_reading(store_env, monkeypatch) -> None:
    """复核 FAIL-3：基线日志缺汇总行 ⇒ 增量不可信 ⇒ 不得 passed。"""
    store, record, folder = _smoke_env(store_env)
    _fake_smoke(store_env[2], monkeypatch, baseline=(0, "garbage without summary"))
    result = s0b.run_smoke(record, folder, "tc_x", "R1")
    assert result["status"] == "failed" and "基线" in result["reason"]


def test_smoke_fails_on_nonzero_rc(store_env, monkeypatch) -> None:
    store, record, folder = _smoke_env(store_env)
    _fake_smoke(store_env[2], monkeypatch, candidate=(3, "Compilation: 0 error(s), 0 warning(s)"))
    assert s0b.run_smoke(record, folder, "tc_x", "R2")["status"] == "failed"
    _fake_smoke(store_env[2], monkeypatch, baseline=(2, "Compilation: 0 error(s), 0 warning(s)"))
    assert s0b.run_smoke(record, folder, "tc_x", "R3")["status"] == "failed"


def test_smoke_passes_with_identical_warnings_and_records_command(store_env, monkeypatch) -> None:
    store, record, folder = _smoke_env(store_env)
    _fake_smoke(store_env[2], monkeypatch)
    result = s0b.run_smoke(record, folder, "tc_x", "R4")
    assert result["status"] == "passed"
    assert result["candidate"]["command"][:2] == ["bash", str(s0b.COMPILE_DRIVER)]
    assert result["warning_delta"]["needs_evaluation"] == []


def test_smoke_waits_for_warning_evaluation_then_passes(store_env, monkeypatch) -> None:
    """复核 FAIL-5：新增 warning ⇒ waiting；人评估后才 passed。"""
    store, record, folder = _smoke_env(store_env)
    _fake_smoke(store_env[2], monkeypatch,
                candidate=(0, "Warning-120162: new\nCompilation: 0 error(s), 1 warning(s)"))
    first = s0b.run_smoke(record, folder, "tc_x", "R5")
    assert first["status"] == "waiting" and first["unaccepted_warnings"] == ["Warning-120162"]
    s0b.accept_warning(folder, "Warning-120162", actor="human:me", reason="工具已知噪声")
    second = s0b.run_smoke(record, folder, "tc_x", "R6")
    assert second["status"] == "passed"


def test_warning_acceptance_is_append_only_and_required(store_env) -> None:
    """复核 FAIL-5：新增/上升的 warning 必须有人评估（只追加、带锚）才可能 passed。"""
    store, record, *_ = _prepare(store_env)
    folder = store.root / record["id"]
    row = s0b.accept_warning(folder, "Warning-120162", actor="human:me", reason="工具已知噪声")
    assert row["decision"] == "accepted"
    assert s0b.accepted_warnings(folder) == {"Warning-120162"}
    with pytest.raises(ValueError):
        s0b.accept_warning(folder, "Warning-120162", actor="model:m", reason="自封")
    with pytest.raises(ValueError):
        s0b.accept_warning(folder, "not-a-code", actor="human:me", reason="x")
    with pytest.raises(ValueError):
        s0b.accept_warning(folder, "Warning-1", actor="human:me", reason="")   # 必须给理由
