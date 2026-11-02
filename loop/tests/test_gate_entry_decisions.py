"""G1 逐条处置的**提交前**判据（A1/A2/I1）。

背景（2026-10-30 真实链实测抓到）：G1 只给**闸门级**决策 `ignored` + 闸门级理由时，
`normalize_entry_decisions` 的"未逐条提交"分支把条目理由写成 `None` 且不校验 ⇒
`precheck_decision` 放行、`gate.py` 已签署、`_resumed` 的二次预检才失败 ⇒
HTTP 500 + 孤儿签名 + run 置 failed（闸门从此不可用）。

本用例把修复后的语义固定下来（拒绝发生在写账本**之前**）：
1. 未逐条提交 + `ignored`/`disputed` 且无理由 ⇒ 提交前失败；
2. 未逐条提交 + 有理由 ⇒ 每条差异条目继承该决策与理由；
3. 未逐条提交 + `confirmed` ⇒ 条目 `confirmed`、理由 `None`（不伪造理由）；
4. 显式逐条提交的覆盖/取值/理由/一致性判据保持原样。
"""
from __future__ import annotations

import pytest

from workflows.chunks.gates import GatePreconditionFailed, normalize_entry_decisions


def _diff(*entry_ids: str) -> dict:
    return {"entries": [{"entry_id": eid} for eid in entry_ids]}


def test_gate_level_ignored_without_reason_is_refused_before_signing() -> None:
    with pytest.raises(GatePreconditionFailed) as excinfo:
        normalize_entry_decisions(
            gate="G1_diff_confirm", decision="ignored",
            entry_decisions=None, diff=_diff("e1", "e2"),
        )
    assert "A2" in str(excinfo.value) and "ignored" in str(excinfo.value)


def test_gate_level_ignored_with_reason_propagates_to_entries() -> None:
    entries = normalize_entry_decisions(
        gate="G1_diff_confirm", decision="ignored",
        entry_decisions=None, diff=_diff("e1", "e2"),
        reason="人已逐条核对：本轮只验证到 N0–N3",
    )
    assert entries == {
        "e1": {"decision": "ignored", "reason": "人已逐条核对：本轮只验证到 N0–N3"},
        "e2": {"decision": "ignored", "reason": "人已逐条核对：本轮只验证到 N0–N3"},
    }


def test_gate_level_confirmed_does_not_invent_reason() -> None:
    entries = normalize_entry_decisions(
        gate="G1_diff_confirm", decision="confirmed",
        entry_decisions=None, diff=_diff("e1"),
    )
    assert entries == {"e1": {"decision": "confirmed", "reason": None}}


def test_explicit_entries_still_validated() -> None:
    # 覆盖全部 + 取值合法 + ignored 带理由 ⇒ 通过
    entries = normalize_entry_decisions(
        gate="G1_diff_confirm", decision="ignored",
        entry_decisions={
            "e1": {"decision": "ignored", "reason": "噪声"},
            "e2": {"decision": "confirmed"},
        },
        diff=_diff("e1", "e2"),
    )
    assert entries["e1"]["decision"] == "ignored" and entries["e1"]["reason"] == "噪声"
    assert entries["e2"] == {"decision": "confirmed", "reason": None}

    # 缺条目 ⇒ 拒绝
    with pytest.raises(GatePreconditionFailed) as missing:
        normalize_entry_decisions(
            gate="G1_diff_confirm", decision="ignored",
            entry_decisions={"e1": {"decision": "ignored", "reason": "x"}},
            diff=_diff("e1", "e2"),
        )
    assert "未覆盖全部" in str(missing.value)

    # 未知条目 ⇒ 拒绝
    with pytest.raises(GatePreconditionFailed):
        normalize_entry_decisions(
            gate="G1_diff_confirm", decision="ignored",
            entry_decisions={"e1": "ignored", "zzz": "ignored"},
            diff=_diff("e1"),
        )

    # 条目 ignored 无理由 ⇒ 拒绝（原有语义）
    with pytest.raises(GatePreconditionFailed) as no_reason:
        normalize_entry_decisions(
            gate="G1_diff_confirm", decision="ignored",
            entry_decisions={"e1": {"decision": "ignored"}},
            diff=_diff("e1"),
        )
    assert "必须给出理由" in str(no_reason.value)

    # disputed 条目但闸门决策不是 disputed ⇒ 拒绝（一致性）
    with pytest.raises(GatePreconditionFailed):
        normalize_entry_decisions(
            gate="G1_diff_confirm", decision="confirmed",
            entry_decisions={"e1": {"decision": "disputed", "reason": "有疑义"}},
            diff=_diff("e1"),
        )
