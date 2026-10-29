"""_resumed 节点实现。"""
from __future__ import annotations
from typing import Any


async def run(ctx: RunCtx, data: Any, gate: str, *, BRANCH_EVENTS, GA, GATE_NODE, GatePreconditionFailed, _cycle, _cycles_view, _material_hard_block, _persist_cycles, _planned_entries, append_decision_ledger, authority_record, human_signed_flag, precheck_decision) -> dict[str, Any]:
    node = GATE_NODE[gate]
    resume = getattr(data, "resume", None)
    value = (resume.value if resume is not None else None) or {}
    decision = value.get("decision")
    actor = value.get("actor")
    reason = value.get("reason")

    if not isinstance(decision, str) or not GA.is_valid_decision(gate, decision):
        options = list(GA.decisions().get(gate, ()))
        ctx.node_failed(node, message=f"非法决策 {decision!r}（权威枚举：{options}）")
        raise GatePreconditionFailed(f"非法决策 {decision!r}；{gate} 的权威枚举是 {options}")
    if decision in GA.NON_ACTIONABLE:
        raise GatePreconditionFailed(f"{decision!r} 是状态而非可提交动作；请选择一个实际决策。")
    if actor and not str(actor).startswith("human"):
        raise GatePreconditionFailed("I6：闸门决策只接受 human actor。")

    # 纵深防御：提交前判定在 `RunManager.decide()` 已做过一次；这里再算一次
    # （防止绕过 API 的 resume —— 例如恢复补投递/脚本直接 continue_with）。
    entry_decisions = _planned_entries(data)
    pre = precheck_decision(
        gate=gate, decision=decision, run_dir=ctx.run_dir, mode=ctx.mode,
        reason=reason, kb=ctx.kb, entry_decisions=entry_decisions,
    )

    # 权威复核：闸门必须已在 gate.py 里获得人类签署（纵深防御，UI 说"已通过"不算数）。
    # **必须带 `--expect <本门决策>`**：默认期望是 G1=confirmed/G2=accept，
    # 若不带，ignored/disputed/rework 签后被默认期望打回 ⇒ 中断已消耗、执行 FAILED、
    # 账本留孤儿签名（C1/B4，实测过 self_resume_limit_reached）。
    from ..chunks.host_steps import run_kb_tool

    check = run_kb_tool(
        "gate.py", ["require-signed", "--run", ctx.run_id, "--gate", gate, "--expect", decision]
    )
    if check["rc"] != 0:
        ctx.node_failed(node, message=f"authority check failed rc={check['rc']}")
        raise GatePreconditionFailed(
            f"闸门 {gate} 未在 kb/tools/gate.py 中获得权威签署（决策 {decision!r}，rc={check['rc']}）："
            "UI 的提交不算权威。"
        )

    cycles = _cycles_view(ctx, data)
    # C6/I7：G2=rework 自增**独立**计数（N6↔N8 的预算不被人为返工消耗）。
    if gate == "G2_report_accept" and decision == "rework":
        cycles["g2_rework_cycles"] = int(cycles.get("g2_rework_cycles") or 0) + 1
    _persist_cycles(ctx, cycles)
    await data.async_set_state("g2_rework_cycles", cycles["g2_rework_cycles"])
    if cycles["n6_n8_cycles"]:
        await data.async_set_state("n6_n8_cycles", cycles["n6_n8_cycles"])

    auth = authority_record(ctx, gate)
    # R3-04：签署时材料里的硬阻断快照（提交前材料 `gate_material::<gate>`；缺失 ⇒ []）。
    # 只进 `decisions/<gate>.json` 落账（读侧唯一来源），不改 `gate_decisions` 既有形状。
    hard_block_snapshot = _material_hard_block(data, gate)
    record = {
        "decision": decision,
        "actor": actor,
        "actor_kind": "human",
        "signed_at": auth.get("signed_at"),
        "reason": reason if reason is not None else auth.get("note"),
        "artifacts": auth.get("artifacts") or [],
        "entries": pre.get("entries") or {},
        "cycle": _cycle(data, gate, ctx),
    }
    decisions = dict(data.get_state("gate_decisions") or {})
    decisions[gate] = record
    await data.async_set_state("gate_decisions", decisions)
    await data.async_set_state("gate_actor", actor)
    ctx.event("gate_decided", node=node, status=decision,
              detail={"gate": gate, "decision": decision, "actor": actor, "reason": reason,
                      "signed_at": record["signed_at"], "artifacts": record["artifacts"],
                      # P-15/P-18：逐条处置随事件下发（新 run）；S3 另从 decisions/ 落账读
                      "entries": record["entries"]})
    # §2.5 落账：record 组装后、node_finished 前（append-only）。S3 的已决策态逐条处置只信这份。
    # R3-04：落账额外带"当时的硬阻断"快照（`hard_block`），不改 record 在 state/事件里的既有形状。
    append_decision_ledger(ctx, gate, {**record, "hard_block": hard_block_snapshot})

    branch = (BRANCH_EVENTS.get(gate) or {}).get(decision)
    if not branch:
        # I17 的后半条：未知分支必须在**发事件前**显式失败，不得 KeyError 落到楔死路径。
        ctx.node_failed(node, message=f"{gate} 的决策 {decision!r} 在本层没有下游事件（拓扑落后于权威）")
        raise GatePreconditionFailed(
            f"{gate} 的决策 {decision!r} 没有映射到下游事件；BRANCH_EVENTS 与权威漂移。"
        )
    # §10.4：闸门节点的 source=`human_gate`、summary 说明"给了什么决策/是否人签/有没有理由"，
    # `human_signed` 只从权威 `gates.json` 读（事件流里的 actor 是自报字符串，不算凭据）。
    signed = human_signed_flag(ctx, gate)
    signed_text = ("已由人签署（human_signed=true）" if signed is True
                   else "非人签署（human_signed=false）" if signed is False
                   else "签署状态未下发")
    gates_json = ctx.run_dir / "gates.json"
    ctx.node_finished(
        node,
        status=decision,
        detail={
            "gate": gate,
            "decision": decision,
            "branch": branch,
            "actor": actor,
            "source": "human_gate",
            "human_signed": signed,
            "summary": (f"{node} {gate}：决策 {decision}，{signed_text}，"
                        f"理由{'已给出' if reason else '未给出'}，下游事件 {branch}"),
        },
        refs=[str(gates_json)] if gates_json.is_file() else [],
    )
    await data.async_emit(branch, {"gate": gate, "decision": decision, "actor": actor,
                                   "entry_decisions": record["entries"]})
    return {"gate": gate, "decision": decision, "branch": branch}
