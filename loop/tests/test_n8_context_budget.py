"""F16：N8 `sandbox_cases` 按预算确定性分片，逐件带 coverage，不丢文件。

契约见 [上下文规格 C1](../../doc/spec/AGENT_CONTEXT_SPEC.md)。这些用例覆盖：
预算内全文 → 超预算降级为变更片段 → 片段不可得时显式失败；两次构造结果一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from host import agent_memory as AM
from workflows.chunks import model_steps as MS


def _write_cases(tmp_path: Path, *, count: int = 8, lines: int = 60) -> tuple[Path, Path]:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    source = tmp_path / "src" / "TESTLIB"
    sandbox.mkdir(parents=True)
    source.mkdir(parents=True)
    for index in range(count):
        name = f"tc_{index:02d}.sv"
        body = [f"// case {index} line {line} " + "x" * 40 for line in range(lines)]
        (sandbox / name).write_text("\n".join(body) + "\n", encoding="utf-8")
        changed = list(body)
        changed[lines // 2] = f"// UPDATED case {index} " + "y" * 40
        (source / name).write_text("\n".join(changed) + "\n", encoding="utf-8")
    return sandbox, tmp_path / "src"


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _entries_bytes(files: list[dict]) -> int:
    """与真实请求同一序列化实现（check_budget 使用 AM.encoded）。"""
    return len(AM.encoded(files))


def test_sandbox_cases_fit_budget_without_dropping_files(tmp_path: Path) -> None:
    sandbox, source_root = _write_cases(tmp_path)
    files, names, summary = MS.build_sandbox_cases(
        sandbox, source_root, [], budget_bytes=20000
    )
    assert len(files) == 8, "降级不得丢文件"
    assert len(names) == 8
    total = _entries_bytes(files)
    assert total <= 20000, total
    for item in files:
        coverage = item["coverage"]
        assert coverage["mode"] in ("full_file", "changed_regions")
        assert coverage["complete"] is True
        assert coverage["scope"]
    modes = {item["coverage"]["mode"] for item in files}
    assert modes == {"full_file", "changed_regions"}, modes
    assert summary["budget_bytes"] == 20000
    assert summary["used_bytes"] == total
    assert summary["full_files"] + summary["region_files"] == 8


def test_changed_regions_stay_locatable(tmp_path: Path) -> None:
    sandbox, source_root = _write_cases(tmp_path, count=3, lines=40)
    files, _, _ = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=6000)
    for item in files:
        coverage = item["coverage"]
        assert coverage["mode"] == "changed_regions"
        assert coverage["regions"] >= 1
        assert item["changed_regions"], "片段模式下必须保留可定位的变更区间"


def test_budget_is_deterministic(tmp_path: Path) -> None:
    sandbox, source_root = _write_cases(tmp_path)
    first = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=20000)
    second = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=20000)
    assert [item["file"] for item in first[0]] == [item["file"] for item in second[0]]
    assert [item["coverage"]["mode"] for item in first[0]] == [
        item["coverage"]["mode"] for item in second[0]
    ]
    assert first[2] == second[2]


def test_unlocatable_change_fails_closed(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    (sandbox / "tc_big.sv").write_text("// " + "z" * 5000 + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="N8 上下文预算"):
        MS.build_sandbox_cases(sandbox, None, [], budget_bytes=1000)


def test_small_input_keeps_full_text(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    (sandbox / "tc_small.sv").write_text("module demo;\nendmodule\n", encoding="utf-8")
    files, _, summary = MS.build_sandbox_cases(sandbox, None, [])
    assert files[0]["coverage"]["mode"] == "full_file"
    assert files[0]["excerpt"] == "module demo;\nendmodule\n"
    assert summary["region_files"] == 0


def test_budget_boundary_does_not_reject_feasible_plan(tmp_path: Path) -> None:
    """2n 尾差不得把可行解硬拒：全降级可行时，必须降级而不是抛「预算不足」。"""
    sandbox, source_root = _write_cases(tmp_path, count=3, lines=40)
    _, _, unlimited = MS.build_sandbox_cases(
        sandbox, source_root, [], budget_bytes=10_000_000
    )
    budget = unlimited["used_bytes"] - 1  # 比「全部全文」少 1 字节，必然要降级
    files, names, summary = MS.build_sandbox_cases(
        sandbox, source_root, [], budget_bytes=budget
    )
    assert len(files) == 3 and len(names) == 3
    assert summary["used_bytes"] <= budget
    assert summary["region_files"] >= 1
    assert summary["full_files"] + summary["region_files"] == 3


def test_used_bytes_matches_compact_encoding(tmp_path: Path) -> None:
    sandbox, source_root = _write_cases(tmp_path, count=2, lines=30)
    files, _, summary = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=20000)
    assert summary["used_bytes"] == len(AM.encoded(files))
    assert summary["used_bytes"] <= 20000
