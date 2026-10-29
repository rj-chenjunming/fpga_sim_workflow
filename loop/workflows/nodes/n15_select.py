"""n15_select 节点实现。"""
from __future__ import annotations
from pathlib import Path
from typing import Any


async def run(data: Any, *, _REAL_CASE, _full_regression_cases, ctx_of) -> list[str]:
    """N15 选择要回归的用例集。

    `full_now` = 全量用例（索引）；`subset_only` / `milestone_only` = 本轮受影响子集。
    返回纯 list（图上的 `for_each`/后继节点吃序列），元数据落 state。
    """
    ctx = ctx_of(data)
    ctx.node_started("N15_select")
    decisions = data.get_state("gate_decisions") or {}
    g3 = ((decisions.get("G3_regression_decision") or {}).get("decision")) or ""
    n5 = data.get_state("n5_impact") or {}
    affected = [c for c in (n5.get("must_change_cases") or []) if c]
    if g3 == "full_now":
        cases = _full_regression_cases() or affected
    else:
        cases = affected
    if not cases:
        cases = [_REAL_CASE]
    await data.async_set_state("n15_set", {"cases": cases, "count": len(cases),
                                           "mode": ctx.mode, "g3_decision": g3})
    ctx.node_finished("N15_select", detail={
        "count": len(cases), "g3": g3,
        # P-31：列出选中的用例名 + 本轮是否会真跑（real 会跑；drill 演示不跑）
        "cases": [str(c) for c in cases],
        "will_really_run": ctx.mode != "drill",
        "source": "framework",
        "summary": (f"N15_select：按 G3={g3 or '未签署'} 选出 {len(cases)} 个回归用例"),
    })
    return cases
