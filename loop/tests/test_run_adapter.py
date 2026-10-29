import subprocess
from pathlib import Path

from host.run_adapter import collect_case_logs, serial_guard_command


def test_serial_guard_preserves_order_and_individual_return_codes(tmp_path: Path):
    guard = tmp_path / "fake guard.sh"
    guard.write_text('case "$4" in second) exit 7;; *) exit 0;; esac\n')
    summary = tmp_path / "summary file"
    cases = [{"case": "first", "sandbox_path": "/tmp/a file"},
             {"case": "second", "sandbox_path": "/tmp/b file"}]
    cmd = serial_guard_command(cases, guard=guard, sandbox_root=tmp_path / "sandbox",
                               evidence_dir=tmp_path / "evidence", run_id="RUN-1", summary_path=summary)
    result = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert result.returncode == 0
    assert summary.read_text().splitlines() == ["first|0", "second|7"]


def test_collect_case_logs_selects_latest_and_omits_absent(tmp_path: Path):
    for name in ("20260101_alpha_1_run.log", "20260102_alpha_1_run.log", "20260103_other_1_run.log"):
        (tmp_path / name).touch()
    assert collect_case_logs(tmp_path, ["alpha", "missing"]) == {"alpha": tmp_path / "20260102_alpha_1_run.log"}
    assert collect_case_logs(tmp_path / "missing", ["alpha"]) == {}
