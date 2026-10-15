"""验收 A2 / I3：两套口径与观测印记，数字必须能独立对账。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from host.evidence import (
    count_koutou1,
    evidence_view,
    imprint_consistency,
    parse_koutou2,
    parse_report_ids,
)


def test_koutou1_matches_independent_grep(fixture_log: Path) -> None:
    """口径一必须与 `grep -c '\\*E'` 逐值一致（独立命令，不共用代码）。"""
    text = fixture_log.read_text(encoding="utf-8", errors="replace")
    mine, _ = count_koutou1(text)
    grep = subprocess.run(
        ["grep", "-c", r"\*E", str(fixture_log)], capture_output=True, text=True
    )
    assert grep.returncode == 0, grep.stderr
    assert mine == int(grep.stdout.strip()), f"抽取值 {mine} != grep {grep.stdout.strip()}"


def test_dual_counts_diverge_and_both_are_recorded(fixture_log: Path) -> None:
    """本工程的核心事实：口径一 1687 ≠ 0，而口径二 UVM_ERROR=0。

    两套口径**都要在**，且**不得互相替代**。
    """
    text = fixture_log.read_text(encoding="utf-8", errors="replace")
    k1, _ = count_koutou1(text)
    k2, _ = parse_koutou2(text)
    assert k1 > 0, "夹具应含非零口径一"
    assert k2["UVM_ERROR"] == 0 and k2["UVM_FATAL"] == 0, "夹具口径二应为 0"

    view = evidence_view(fixture_log)
    counts = view["counts"]
    assert counts["koutou1"]["value"] == k1
    assert counts["koutou2"]["value"]["UVM_ERROR"] == 0
    assert counts["both_zero"] is False
    # 口径二为 0 不足以判绿
    assert view["verdict"]["passed"] is False
    assert any("口径一" in r for r in view["verdict"]["reasons"])


def test_imprint_three_way_consistency(fixture_log: Path) -> None:
    """观测印记三向一致：印记行存在 + by-id 计数 + 地址/值与期望一致。"""
    text = fixture_log.read_text(encoding="utf-8", errors="replace")
    result = imprint_consistency(text, "N6_FPGA_DATE_PCIE")
    assert result["checks"]["imprint_present"] is True
    assert result["checks"]["id_count_present"] is True
    assert result["checks"]["address_matches_expected"] is True
    assert result["checks"]["value_matches_expected"] is True
    assert result["failed_count"] == 0 and result["consistent"] is True
    assert result["observed"]["address"] == "0x0000+0x04"
    assert result["observed"]["value"] == "0x20260708"
    assert result["refs"] == ["tc_pcie_rw_02.sv:186"]


def test_parse_report_ids_isolated_to_ids_section(fixture_log: Path) -> None:
    """by-id 段解析不得把 severity 段的数字混进来。"""
    text = fixture_log.read_text(encoding="utf-8", errors="replace")
    ids = parse_report_ids(text)
    assert ids.get("N6_FPGA_DATE_PCIE") == 1
    assert "UVM_ERROR" not in ids


def test_missing_evidence_is_explicit_not_fabricated(tmp_path: Path) -> None:
    """E-2：证据缺失必须显式登记为缺陷，不得编造默认真值。"""
    view = evidence_view(tmp_path / "nope.log")
    assert view["present"] is False
    assert "E-2" in view["defect"]
