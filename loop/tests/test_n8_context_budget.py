"""F16：N8 `sandbox_cases` 按预算确定性分片，逐件带 coverage，不丢文件。

契约见 [上下文规格 C1](../../doc/spec/AGENT_CONTEXT_SPEC.md)。这些用例覆盖：
预算内全文 → 超预算降级为变更片段 → 片段不可得时显式失败；两次构造结果一致。
"""

from __future__ import annotations

import difflib
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
    with pytest.raises(RuntimeError, match="N8 上下文预算") as excinfo:
        MS.build_sandbox_cases(sandbox, None, [], budget_bytes=1000)
    # F16-c：错误消息必须能定位到具体文件，不能只给泛化结论。
    assert "tc_big.sv" in str(excinfo.value)


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


# ---------------------------------------------------------------- F16-b 闭锁与语义

def test_missing_sandbox_dir_fails_closed(tmp_path: Path) -> None:
    """没有沙盒目录不能说「复核 0 件」通过。"""
    with pytest.raises(RuntimeError, match="沙盒|可复核"):
        MS.build_sandbox_cases(tmp_path / "nope" / "TESTLIB", None, [])


def test_empty_sandbox_fails_closed(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="沙盒|可复核"):
        MS.build_sandbox_cases(sandbox, None, [])


def test_applied_cases_without_files_fails_closed(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    applied = [{"case": "demo", "file": "TESTLIB/demo.sv", "edits": [{"line": 3}]}]
    with pytest.raises(RuntimeError, match="沙盒|可复核|缺"):
        MS.build_sandbox_cases(sandbox, None, applied)


def test_byte_level_determinism(tmp_path: Path) -> None:
    sandbox, source_root = _write_cases(tmp_path)
    first = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=20000)
    second = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=20000)
    assert AM.encoded(first[0]) == AM.encoded(second[0])


def test_complete_means_all_changed_regions_are_provided(tmp_path: Path) -> None:
    """coverage.complete=true 只承诺「全部变更区域已提供」，不是全文复核。"""
    import difflib
    sandbox, source_root = _write_cases(tmp_path, count=2, lines=80)
    files, _, _ = MS.build_sandbox_cases(sandbox, source_root, [], budget_bytes=6000)
    for item in files:
        coverage = item["coverage"]
        assert isinstance(coverage["complete"], bool)
        if coverage["mode"] == "changed_regions":
            before = (source_root / "TESTLIB" / item["file"]).read_text(encoding="utf-8").splitlines()
            after = (sandbox / item["file"]).read_text(encoding="utf-8").splitlines()
            expected = sum(1 for _ in difflib.SequenceMatcher(a=before, b=after).get_grouped_opcodes(n=6))
            assert coverage["regions"] == expected, (item["file"], coverage["regions"], expected)
            assert coverage["complete"] is True
            assert item["changed_regions"], "complete=true 必须确有变更区域"


def test_partial_missing_error_lists_missing_and_present_cases(tmp_path: Path) -> None:
    """F16-c：消息含缺失用例名与沙盒内现有用例名，便于定位是哪一件没被写出来。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    (sandbox / "a.sv").write_text("module a; endmodule\n", encoding="utf-8")
    applied = [
        {"case": "a", "file": "TESTLIB/a.sv", "edits": [{"line": 1}]},
        {"case": "b", "file": "TESTLIB/b.sv", "edits": [{"line": 2}]},
    ]
    with pytest.raises(RuntimeError) as excinfo:
        MS.build_sandbox_cases(sandbox, None, applied)
    message = str(excinfo.value)
    assert "b.sv" in message and "a.sv" in message


def test_empty_sandbox_error_names_expected_cases(tmp_path: Path) -> None:
    """F16-c：空沙盒闭锁时必须说明 applied_cases 期待哪些用例（或明确为空）。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    applied = [{"case": "demo", "file": "TESTLIB/demo.sv", "edits": [{"line": 1}]}]
    with pytest.raises(RuntimeError) as excinfo:
        MS.build_sandbox_cases(sandbox, None, applied)
    message = str(excinfo.value)
    assert "demo.sv" in message and "没有 *.sv" in message


def test_applied_case_missing_one_file_fails_closed(tmp_path: Path) -> None:
    """applied_cases 里有、沙盒里没有的用例必须显式失败（不能只判「全有/全无」）。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    (sandbox / "a.sv").write_text("module a; endmodule\n", encoding="utf-8")
    applied = [
        {"case": "a", "file": "TESTLIB/a.sv", "edits": [{"line": 1}]},
        {"case": "b", "file": "TESTLIB/b.sv", "edits": [{"line": 2}]},
    ]
    with pytest.raises(RuntimeError, match="b.sv|缺"):
        MS.build_sandbox_cases(sandbox, None, applied)


# ---------------------------------------------------------------- R4 真实序列化成本
#
# 契约：AGENT_CONTEXT_SPEC.md C1「按真实序列化成本选择表示（R4）」——每件每种表示的成本是
# 该件条目**实际紧凑序列化**的字节数（含 coverage/changed_regions/键名标点），可行成本取
# min(全文成本, 片段成本)。不得假定「片段一定更小」，也不得用近似字节数。

def _write_all_lines_changed(tmp_path: Path, *, count: int = 86) -> tuple[Path, Path]:
    """每件 20 行**全部变更**的短文件：片段带定位头与 before 文本，比全文更大（R4 原始观察）。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    source = tmp_path / "src" / "TESTLIB"
    sandbox.mkdir(parents=True)
    source.mkdir(parents=True)
    for index in range(count):
        name = f"tc{index:02}.sv"
        (sandbox / name).write_text("new code\n" * 20, encoding="utf-8")
        (source / name).write_text("old code\n" * 20, encoding="utf-8")
    return sandbox, tmp_path / "src"


def _write_broad_cases(tmp_path: Path) -> tuple[Path, Path]:
    """覆盖中文 / 转义 / 密集变更 / 删除 / 单行变更 / 多文件；预算大时全部应保持全文。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    source = tmp_path / "src" / "TESTLIB"
    sandbox.mkdir(parents=True)
    source.mkdir(parents=True)

    def pair(name: str, old: list[str], new: list[str]) -> None:
        (source / name).write_text("\n".join(old) + "\n", encoding="utf-8")
        (sandbox / name).write_text("\n".join(new) + "\n", encoding="utf-8")

    for index in range(86):
        pair(f"aa_{index:02d}.sv", ["old code"] * 20, ["new code"] * 20)
    pair("cn_all.sv", [f"// 旧注释{i} " + "汉" * 8 for i in range(10)],
         [f"// 新注释{i} " + "汉" * 10 for i in range(10)])
    pair("escape_all.sv",
         ['assign q = "old\\\\path";', "assign t = \"a\tb\";", "assign r = 1'b0;"],
         ['assign q = "new\\\\path";', "assign t = \"a\tb\";", "assign r = 1'b1;"])
    pair("dd_dense.sv", [f"// line {i} old" for i in range(20)],
         [f"// line {i} new " + "y" * 5 for i in range(20)])
    pair("deleted.sv", [f"// removed {i}" for i in range(30)],
         [f"// kept {i}" for i in range(5)])
    for index in range(4):
        lines = [f"// single {index} line {j} " + "x" * 30 for j in range(40)]
        changed = list(lines)
        changed[20] = f"// single {index} UPDATED " + "x" * 30
        pair(f"single_{index:02d}.sv", lines, changed)
    return sandbox, tmp_path / "src"


def _plan_bytes(files: list[dict]) -> int:
    return len(AM.encoded(files))


def test_all_lines_changed_uses_full_text_when_cheaper(tmp_path: Path) -> None:
    """全部行变更的小文件：片段更大 ⇒ 可行成本是全文；默认预算 59341 < 60000 必须可行。"""
    sandbox, source = _write_all_lines_changed(tmp_path)
    unlimited, _, _ = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=10**7)
    full_plan_bytes = _plan_bytes(unlimited)
    # 审计（STATUS §38.2 探针）原始数字：86 件全文序列化 59341 bytes。
    assert full_plan_bytes == 59341, full_plan_bytes
    files, names, summary = MS.build_sandbox_cases(sandbox, source, [])
    assert len(files) == len(names) == 86, "降级不得丢文件"
    assert {item["coverage"]["mode"] for item in files} == {"full_file"}, "全文更便宜时应选全文"
    assert summary["used_bytes"] == _plan_bytes(files) == full_plan_bytes
    assert summary["used_bytes"] <= MS.N8_SANDBOX_BUDGET_BYTES
    assert summary["full_files"] == 86 and summary["region_files"] == 0


def test_budget_equal_to_real_min_total_is_feasible(tmp_path: Path) -> None:
    """临界相等：预算正好等于全部候选最小成本之和 ⇒ 必须可行且用满。"""
    sandbox, source = _write_all_lines_changed(tmp_path)
    unlimited, _, _ = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=10**7)
    budget = _plan_bytes(unlimited)
    files, _, summary = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=budget)
    assert len(files) == 86
    assert summary["used_bytes"] == budget == _plan_bytes(files)
    assert summary["full_files"] == 86 and summary["region_files"] == 0


def test_below_real_min_total_rejected_with_real_min_cost(tmp_path: Path) -> None:
    """只有「全部候选最小可行成本之和」超预算才拒绝，且报真实成本而不是片段成本之和。"""
    sandbox, source = _write_all_lines_changed(tmp_path)
    unlimited, _, _ = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=10**7)
    min_total = _plan_bytes(unlimited)
    budget = min_total - 1
    with pytest.raises(RuntimeError) as excinfo:
        MS.build_sandbox_cases(sandbox, source, [], budget_bytes=budget)
    message = str(excinfo.value)
    assert f"{min_total} > {budget}" in message, message
    assert "61835" not in message, "不得把「片段成本之和」当作最小成本"
    assert "tc00.sv" in message and "不得静默抽样" in message


def test_all_lines_changed_is_byte_deterministic(tmp_path: Path) -> None:
    sandbox, source = _write_all_lines_changed(tmp_path)
    first = MS.build_sandbox_cases(sandbox, source, [])
    second = MS.build_sandbox_cases(sandbox, source, [])
    assert AM.encoded(first[0]) == AM.encoded(second[0])
    assert first[2] == second[2]


def test_broad_encodings_select_full_text_when_it_fits(tmp_path: Path) -> None:
    """中文/转义/密集变更/删除/多文件：预算恰好容纳全部全文 ⇒ 保持全文（默认全文规则）。"""
    sandbox, source = _write_broad_cases(tmp_path)
    names = sorted(path.name for path in sandbox.glob("*.sv"))
    unlimited, _, _ = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=10**7)
    budget = _plan_bytes(unlimited)
    files, out_names, summary = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=budget)
    assert [item["file"] for item in files] == names
    assert out_names == [Path(name).stem for name in names]
    assert {item["coverage"]["mode"] for item in files} == {"full_file"}
    assert summary == {"budget_bytes": budget, "used_bytes": budget,
                       "full_files": len(names), "region_files": 0}


def test_tight_budget_keeps_coverage_consistent_with_sent_content(tmp_path: Path) -> None:
    """装不下时按确定性顺序降级；coverage/summary 必须与实际发送内容一致，不得虚报 complete。"""
    sandbox, source = _write_broad_cases(tmp_path)
    names = sorted(path.name for path in sandbox.glob("*.sv"))
    unlimited, _, _ = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=10**7)
    budget = _plan_bytes(unlimited) - 1  # 全文只差 1 字节 ⇒ 至少一件必须降级
    files, out_names, summary = MS.build_sandbox_cases(sandbox, source, [], budget_bytes=budget)
    assert len(files) == len(out_names) == len(names), "不得丢文件"
    assert [item["file"] for item in files] == names
    assert summary["used_bytes"] == _plan_bytes(files) <= budget
    assert summary["region_files"] >= 1
    modes = [item["coverage"]["mode"] for item in files]
    assert summary["full_files"] == modes.count("full_file")
    assert summary["region_files"] == modes.count("changed_regions")
    assert summary["full_files"] + summary["region_files"] == len(names)
    for item in files:
        coverage = item["coverage"]
        sandbox_text = (sandbox / item["file"]).read_text(encoding="utf-8")
        before = (source / "TESTLIB" / item["file"]).read_text(encoding="utf-8").splitlines()
        after = sandbox_text.splitlines()
        groups = list(difflib.SequenceMatcher(a=before, b=after).get_grouped_opcodes(
            n=MS.N8_REGION_CONTEXT_LINES))
        expected = [(group[0][3] + 1, group[-1][4]) for group in groups]
        assert coverage["regions"] == len(expected), item["file"]
        assert [(region["after"]["start"], region["after"]["end"])
                for region in item["changed_regions"]] == expected
        assert coverage["complete"] is True
        if coverage["mode"] == "full_file":
            assert coverage["scope"] == "full_file"
            assert item["excerpt"] == sandbox_text
        else:
            assert coverage["scope"] == "all_changed_regions"
            for start, end in expected:
                assert f"// lines {start}-{end}\n" in item["excerpt"]
                assert "\n".join(after[start - 1:end]) in item["excerpt"]


def test_forced_region_large_file_never_falls_back_to_full_text(tmp_path: Path) -> None:
    """>6000 字符的大文件必须用片段；缺源/无变更 ⇒ fail closed，不得用全文顶替（R4 不解除既有规则）。"""
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    sandbox.mkdir(parents=True)
    (sandbox / "tc_big.sv").write_text("// " + "z" * 7000 + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="无法定位|N8 上下文") as excinfo:
        MS.build_sandbox_cases(sandbox, None, [], budget_bytes=10**7)
    assert "tc_big.sv" in str(excinfo.value)


def test_forced_region_large_file_stays_region_even_when_budget_ample(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox" / "TESTLIB"
    source = tmp_path / "src" / "TESTLIB"
    sandbox.mkdir(parents=True)
    source.mkdir(parents=True)
    old = ["// line " + "z" * 20 + f" {i}" for i in range(300)]
    new = ["// LINE " + "z" * 20 + f" {i}" for i in range(300)]
    (source / "tc_big.sv").write_text("\n".join(old) + "\n", encoding="utf-8")
    (sandbox / "tc_big.sv").write_text("\n".join(new) + "\n", encoding="utf-8")
    (sandbox / "small.sv").write_text("module s; endmodule\n", encoding="utf-8")
    (source / "small.sv").write_text("module s; endmodule\n", encoding="utf-8")
    files, _, _ = MS.build_sandbox_cases(sandbox, tmp_path / "src", [], budget_bytes=10**7)
    by_name = {item["file"]: item for item in files}
    assert by_name["tc_big.sv"]["coverage"]["mode"] == "changed_regions"
    assert by_name["small.sv"]["coverage"]["mode"] == "full_file"
