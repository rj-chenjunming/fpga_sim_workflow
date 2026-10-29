"""仿真环境能力：默认实现适配现有 run_guarded 环境。"""

from pathlib import Path
from typing import Any, Callable, Protocol

from . import paths
from .compile_adapter import compile_case
from .environment_inputs import author_case_path, staged_inputs, source_case_path
from .environment_sv import _api_semantics_for, _rtl_effect_hint
from .run_adapter import collect_case_logs, serial_guard_command


class SimulationAdapter(Protocol):
    def staged_inputs(self, run_dir: Path) -> dict[str, Any]: ...

    def source_case_path(self, repo_root: Path, target: dict[str, Any]) -> Path: ...

    def author_case_path(self, repo_root: Path, file_rel: str, case: str) -> Path: ...

    def api_semantics(self, env_root: Path, text: str, line: int, cache: dict) -> list[dict[str, Any]]: ...

    def rtl_effect(self, changes: list[dict[str, Any]]) -> dict[str, Any] | None: ...

    def compile_case(self, runner: Callable[..., dict[str, Any]], *, case: str, case_file: str,
                     sandbox_root: Path, evidence_dir: Path, run_id: str) -> tuple[dict[str, Any], list[str]]: ...

    def serial_command(self, cases: list[dict[str, Any]], *, sandbox_root: Path,
                       evidence_dir: Path, run_id: str, summary_path: Path) -> str: ...

    def collect_logs(self, evidence_dir: Path, cases: list[str], *, seed: str = "1") -> dict[str, Path]: ...


class GuardedSimulation:
    def staged_inputs(self, run_dir):
        return staged_inputs(run_dir)

    def source_case_path(self, repo_root, target):
        return source_case_path(repo_root, target)

    def author_case_path(self, repo_root, file_rel, case):
        return author_case_path(repo_root, file_rel, case)

    def api_semantics(self, env_root, text, line, cache):
        return _api_semantics_for(env_root, text, line, cache)

    def rtl_effect(self, changes):
        return _rtl_effect_hint(changes)

    def compile_case(self, runner, **kwargs):
        return compile_case(runner, **kwargs)

    def serial_command(self, cases, **kwargs):
        return serial_guard_command(cases, guard=paths.KB_TOOLS / "run_guarded.sh", **kwargs)

    def collect_logs(self, evidence_dir, cases, *, seed="1"):
        return collect_case_logs(evidence_dir, cases, seed=seed)
