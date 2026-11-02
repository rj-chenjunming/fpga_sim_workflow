"""_enter 节点实现。"""
from __future__ import annotations
from typing import Any


async def run(ctx: RunCtx, data: Any, gate: str, *, _assert_no_impact_gate_allowed, GA, GATE_NODE, GATE_STAGE, _counts_for, _cycle, _cycles_view, _ledger_notes, _persist_cycles, _state_facts, contracts, decision_options) -> dict[str, Any]:
    _assert_no_impact_gate_allowed(ctx, data, gate)
    node = GATE_NODE[gate]
    cycles = _cycles_view(ctx, data)
    _persist_cycles(ctx, cycles)
    await data.async_set_state("g2_rework_cycles", cycles["g2_rework_cycles"])
    facts = _state_facts(data)
    ledger_notes = _ledger_notes(ctx)
    if ledger_notes:
        facts["_ledger_notes"] = ledger_notes
    material = contracts.gate_material(
        gate=gate,
        run_dir=ctx.run_dir,
        counts=_counts_for(data),
        kb=ctx.kb,
        pending_interrupt=None,
        job=None,
        stage=GATE_STAGE[gate],
        mode=ctx.mode,
        state_facts=facts,
        gate_decisions=data.get_state("gate_decisions") or {},
        cycles=cycles,
    )
    material["run_id"] = ctx.run_id
    material["cycle"] = _cycle(data, gate, ctx)
    # R3：选项里的理由前置必须反映**本轮**事实（G2 失败报告 / drill G1 attestation），
    # 否则中断载荷里下发的还是静态表，界面无法预检。
    diff_view = material.get("difference_items") or {}
    material["decision_options"] = decision_options(
        gate,
        claimed_verdict=contracts.report_claimed_verdict(ctx.run_dir),
        mode=ctx.mode,
        unresolved_count=diff_view.get("unresolved_count"),
    )
    material["gate_node"] = node
    material["authority_enums"] = {g: list(GA.decisions().get(g, ())) for g in GA.gate_ids()}
    ctx.event("gate_pending", node=node, status="waiting",
              detail={"gate": gate, "cycle": material["cycle"],
                      "hard_block": [b["code"] for b in material["hard_block"]],
                      "decision_options": [o["value"] for o in material["decision_options"]]})
    await data.async_set_state(f"gate_material::{gate}", material)
    await data.async_pause_for(
        type="gate_decision",
        interrupt_id=f"{gate}:{material['cycle']}",
        payload=material,
        resume_to="self",
    )
    return {"status": "waiting", "gate": gate}
