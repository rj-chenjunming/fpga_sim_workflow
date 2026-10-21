"""F03-a 验证隔离最小切片：软件 state 根可注入 + kb 工具子进程不写冻结目录。

契约见 `doc/spec/ENV_PLUGIN_SPEC.md`（三根 + `$LOOP_STATE_ROOT`）。这些用例只证明
「测试与独立副本不再写共享 state」与「子进程不写 `kb/tools/__pycache__`」，
**不证明**测试已按环境/数据根完全隔离（那属 F03 后续切片）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]


def _run_python(code: str, env_overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(LOOP_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_state_root_can_be_injected(tmp_path: Path) -> None:
    root = tmp_path / "state-root"
    proc = _run_python("from host import paths as P; print(P.STATE_DIR)",
                       {"LOOP_STATE_ROOT": str(root)})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(root)


def test_state_root_defaults_to_software_copy() -> None:
    proc = _run_python("from host import paths as P; print(P.STATE_DIR)",
                       {"LOOP_STATE_ROOT": None})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(LOOP_DIR / "state")


def test_test_process_does_not_write_shared_state() -> None:
    """本进程（pytest）的 state 根必须是隔离目录，派生路径也随之隔离。"""
    from host import paths as P

    assert P.STATE_DIR != P.LOOP_DIR / "state", "测试进程仍在写共享软件 state"
    assert "loop-state-" in str(P.STATE_DIR)
    assert P.JOBS_DIR == P.STATE_DIR / "jobs"
    assert P.RECOVERY_DIR == P.STATE_DIR / "recovery"
    assert P.EVENTS_DIR == P.STATE_DIR / "events"
    assert P.SLOT_LOCK == P.STATE_DIR / "slot.lock"
    assert P.SLOT_QUEUE == P.STATE_DIR / "queue.json"


def test_kb_tool_subprocess_forbids_bytecode(monkeypatch) -> None:
    """`kb/tools/` 是冻结目录：子进程必须带 `-B`，不得写 `__pycache__`。"""
    from workflows.chunks import host_steps

    captured: dict[str, list[str]] = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
        captured["cmd"] = list(cmd)
        return _Proc()

    monkeypatch.setattr(host_steps.subprocess, "run", fake_run)
    host_steps.run_kb_tool("gate.py", ["init", "--run", "RUN-20261021-200000"])
    cmd = captured["cmd"]
    assert cmd[1] == "-B", cmd
    assert cmd[2].endswith("kb/tools/gate.py"), cmd
