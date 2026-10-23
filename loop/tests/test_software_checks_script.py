"""R3-14：`spikes/run_software_checks.sh` 不得吞掉 pytest 的 "N passed" 汇总行。

回归背景（STATUS §49.3 第 6 条）：脚本自带 `-q`，调用方再传 `-q` 时命令行变成 `pytest -qq`，
pytest 的 `-qq` 会隐藏汇总行 ⇒ 门禁输出只剩点号，无法从命令输出复制通过/失败数字。
本测试用一份很小的既有测试文件当探针，分别按「调用方带 -q」与「不带 -q」跑脚本，
断言两种调用都仍然输出 `<N> passed`。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

LOOP_DIR = Path(__file__).resolve().parents[1]
SCRIPT = LOOP_DIR / "spikes" / "run_software_checks.sh"
PROBE = "tests/test_f06_structure.py"

pytestmark = pytest.mark.skipif(
    not (LOOP_DIR / ".venv" / "bin" / "python").exists(),
    reason="脚本前置要求 loop/.venv/bin/python（本机无则无法验证脚本行为）",
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(LOOP_DIR), capture_output=True, text=True, timeout=600,
    )


def _assert_summary_line(res: subprocess.CompletedProcess[str]) -> None:
    assert res.returncode == 0, (res.stdout[-3000:], res.stderr[-3000:])
    # 只要求"汇总行存在且报告了至少 1 条通过"（探针文件的用例数可能随重构变化）。
    assert re.search(r"\b[1-9]\d* passed\b", res.stdout), res.stdout[-3000:]
    assert "no tests ran" not in res.stdout


def test_caller_q_does_not_swallow_the_summary_line() -> None:
    _assert_summary_line(_run(PROBE, "-q"))


def test_default_run_keeps_the_summary_line() -> None:
    _assert_summary_line(_run(PROBE))
