"""F03-b：测试分层标记的机器可读边界（环境层 vs 纯软件层）。

这些断言检查的是**分层元数据**，不是业务行为：
1. `-m env_layer` 精确选中 3 项环境层用例；
2. 未注册标记必须让 pytest 收集失败（`--strict-markers` 生效）；
3. 软件层入口默认在**收集阶段**就排除这 3 项并报告被排除数；
4. 3 项用例在源码中写明「为什么属于环境层」。

它们不证明这 3 项通过——本机 `ENV_ROOT` 只读，环境层只能如实失败（见 STATUS）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[1]

ENV_LAYER_CASES = {
    ("tests/test_archive_e2.py", "test_guard_compile_only_archives_evidence_readonly"),
    ("tests/test_archive_e2.py", "test_guard_archive_is_bounded_and_excludes_guard_log"),
    ("tests/test_projection_and_frozen.py", "test_frozen_witness_before_after_drill_run"),
}
ENV_LAYER_IDS = {f"{rel}::{name}" for rel, name in ENV_LAYER_CASES}

#: 源码里必须出现的环境层原因关键词（任一条）。
REASON_KEYWORDS = ("可写 ENV_ROOT", "冻结见证", "布局")


def _pytest(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(LOOP), capture_output=True, text=True, timeout=timeout,
    )


def test_env_layer_marker_selects_exactly_the_environment_cases():
    proc = _pytest(["--collect-only", "-q", "-m", "env_layer",
                    "tests/test_archive_e2.py", "tests/test_projection_and_frozen.py"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    collected = {line.strip() for line in proc.stdout.splitlines() if "::" in line}
    assert collected == ENV_LAYER_IDS, collected


@pytest.mark.parametrize("rel,name", sorted(ENV_LAYER_CASES))
def test_environment_layer_cases_state_why_in_source(rel: str, name: str):
    source = (LOOP / rel).read_text(encoding="utf-8")
    marked = re.search(
        r"@pytest\.mark\.env_layer[^\n]*\n(?:\s*@[^\n]*\n)*\s*def " + re.escape(name) + r"\b",
        source,
    )
    assert marked, f"{rel}::{name} 缺少 @pytest.mark.env_layer"
    block = source[marked.end(): marked.end() + 1200]
    assert any(keyword in block for keyword in REASON_KEYWORDS), (
        f"{rel}::{name} 未写明环境层原因（可写 ENV_ROOT / 冻结见证 / 布局）"
    )


def test_unknown_marker_fails_collection_with_strict_markers(tmp_path: Path):
    bad = tmp_path / "test_unknown_marker.py"
    bad.write_text(
        "import pytest\n\n@pytest.mark.not_a_real_marker\ndef test_x():\n    pass\n",
        encoding="utf-8",
    )
    proc = _pytest(["--collect-only", "-q", "-c", str(LOOP / "pytest.ini"),
                    "-p", "no:cacheprovider", str(bad)])
    output = proc.stdout + proc.stderr
    assert proc.returncode != 0, output
    assert "not_a_real_marker" in output, output


def test_software_entry_excludes_env_layer_at_collection():
    """入口默认排除环境层：收集阶段就报 deselected，而不是跑起来再 skip。"""
    proc = subprocess.run(
        ["bash", "spikes/run_software_checks.sh", "--collect-only", "-q"],
        cwd=str(LOOP), capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "deselected" in proc.stdout, proc.stdout + proc.stderr
