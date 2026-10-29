"""现有环境的串行仿真命令和日志定位；作业生命周期由 Host 负责。"""

import shlex
from pathlib import Path
from typing import Any


def serial_guard_command(cases: list[dict[str, Any]], *, guard: Path, sandbox_root: Path,
                         evidence_dir: Path, run_id: str, summary_path: Path) -> str:
    lines = ["set -u", f"mkdir -p {shlex.quote(str(evidence_dir))}",
             ": > " + shlex.quote(str(summary_path))]
    for item in cases:
        case = item["case"]
        cmd = (
            f"bash {shlex.quote(str(guard))}"
            f" --case-file {shlex.quote(item['sandbox_path'])}"
            f" --case-name {shlex.quote(case)}"
            f" --seed 1 --mode full"
            f" --sandbox-root {shlex.quote(str(sandbox_root))}"
            f" --evidence-dir {shlex.quote(str(evidence_dir))}"
            f" --run {shlex.quote(run_id)}"
        )
        lines.append(f"echo '=== BEGIN {case} ==='")
        lines.append(cmd)
        lines.append("__rc=$?")
        lines.append(f"printf '%s|%s\\n' {shlex.quote(case)} \"$__rc\" >> {shlex.quote(str(summary_path))}")
        lines.append(f"echo '=== END {case} rc='\"$__rc\"' ==='")
    lines.append("exit 0")
    return "\n".join(lines)


def collect_case_logs(evidence_dir: Path, cases: list[str], *, seed: str = "1") -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not evidence_dir.is_dir():
        return out
    for case in cases:
        candidates = sorted(p for p in evidence_dir.glob(f"*_{case}_{seed}_run.log")
                            if not p.name.endswith("_guard.log"))
        if candidates:
            out[case] = candidates[-1]
    return out
