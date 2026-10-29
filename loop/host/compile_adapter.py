"""现有仿真环境的编译调用和编译日志定位。"""

from pathlib import Path
from typing import Any, Callable


def compile_case(runner: Callable[..., dict[str, Any]], *, case: str, case_file: str | Path,
                 sandbox_root: Path, evidence_dir: Path, run_id: str) -> tuple[dict[str, Any], list[str]]:
    result = runner(
        ["--case-file", str(case_file), "--case-name", case, "--seed", "1",
         "--mode", "compile-only", "--sandbox-root", str(sandbox_root),
         "--evidence-dir", str(evidence_dir), "--run", run_id],
        timeout=900,
    )
    refs: list[str] = []
    if evidence_dir.is_dir():
        for kind in ("rtl", "tb", "xli_lib"):
            refs.extend(str(path) for path in sorted(evidence_dir.glob(f"*_{case}_1_c_{kind}.log")))
    return result, refs
