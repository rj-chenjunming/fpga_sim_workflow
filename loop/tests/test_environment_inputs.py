from pathlib import Path

from host.environment_inputs import author_case_path, source_case_path, staged_inputs


def test_author_fallback_preserves_existing_source_rule(tmp_path: Path):
    fallback = tmp_path / "TESTLIB" / "case.sv"
    fallback.parent.mkdir()
    fallback.write_text("module x; endmodule")
    assert author_case_path(tmp_path, "missing.sv", "case") == fallback
    preferred = tmp_path / "preferred.sv"
    preferred.touch()
    assert author_case_path(tmp_path, "preferred.sv", "case") == preferred
    assert source_case_path(tmp_path, {"case": "case", "file": "missing.sv"}) == tmp_path / "missing.sv"


def test_missing_staged_directory_is_explicit(tmp_path: Path):
    assert staged_inputs(tmp_path) == {"present": False, "staged_dir": str(tmp_path / "staged")}
