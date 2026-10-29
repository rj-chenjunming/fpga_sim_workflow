from pathlib import Path

from host.compile_adapter import compile_case


def test_compile_case_passes_environment_arguments_and_collects_logs(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "run_tc_demo_1_c_tb.log").write_text("tb")
    (evidence / "run_tc_other_1_c_tb.log").write_text("other")
    calls = []

    def runner(args, *, timeout):
        calls.append((args, timeout))
        return {"rc": 0, "cmd": "guard", "stderr_tail": ""}

    result, refs = compile_case(runner, case="tc_demo", case_file=tmp_path / "case.sv",
                                sandbox_root=tmp_path / "sandbox", evidence_dir=evidence,
                                run_id="RUN-1")
    assert result["rc"] == 0
    assert calls == [(["--case-file", str(tmp_path / "case.sv"), "--case-name", "tc_demo",
                       "--seed", "1", "--mode", "compile-only", "--sandbox-root",
                       str(tmp_path / "sandbox"), "--evidence-dir", str(evidence),
                       "--run", "RUN-1"], 900)]
    assert refs == [str(evidence / "run_tc_demo_1_c_tb.log")]


def test_compile_case_preserves_failure_and_missing_logs(tmp_path: Path):
    failure = {"rc": 7, "cmd": "guard", "stderr_tail": "failure"}
    result, refs = compile_case(lambda args, *, timeout: failure, case="case", case_file=tmp_path / "case",
                                sandbox_root=tmp_path, evidence_dir=tmp_path / "absent", run_id="RUN-1")
    assert result is failure
    assert refs == []
