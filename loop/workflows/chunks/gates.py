"""三道人工闸门（N4 / N13 / N14）。

契约（spec §5）：
- **中断**归 TriggerFlow（`pause_for` 是 durable graph interrupt）；
- **决策权威**归 `kb/tools/gate.py`（gate_state + `history[]` + `gates.sha256` + `anchor`）；
- **UI 只做传输**，不持有"已通过"。

`resume_to="self"` 让本 chunk 在恢复时**重新进入**并读到 `data.resume.value`，
从而显式分叉到下游事件 —— 契合"恢复行为必须落在下游 chunk / 显式 resume 事件里，
不得依赖挂起的 Python 帧"。

**枚举不在这里手写**：合法决策一律取自 `host.gate_authority`（背后是 `kb_lib`）。
自造枚举已实测踩坑（本层曾把 G3 写成 `full_regression`，而权威是 `full_now`）。
"""

from __future__ import annotations

from typing import Any

from host import gate_authority as GA
from services import contracts

from ..context import RunCtx, ctx_of


class GatePreconditionFailed(PermissionError):
    """闸门前置不满足（I1 / I4 / I6 / I7）。"""


#: 决策 → 下游事件名。这张表是**本层唯一自有的部分**（事件名属于本层拓扑）。
BRANCH_EVENTS: dict[str, dict[str, str]] = {
    "G1_diff_confirm": {
        "confirmed": "G1_CONFIRMED",
        "ignored": "G1_IGNORED",
        "disputed": "G1_DISPUTED",
    },
    "G2_report_accept": {"accept": "G2_ACCEPT", "rework": "G2_REWORK"},
    "G3_regression_decision": {
        "full_now": "G3_FULL_NOW",
        "subset_only": "G3_SUBSET_ONLY",
        "milestone_only": "G3_MILESTONE",
        "defer": "G3_DEFER",
    },
}

#: 闸门 → 节点名（纯展示元数据）
GATE_NODE = {"G1_diff_confirm": "N4", "G2_report_accept": "N13", "G3_regression_decision": "N14"}


def validate_branches() -> dict[str, list[str]]:
    """自检：本层的事件表必须与权威的可提交决策**逐值一致**。

    返回 `{gate: [问题...]}`；非空即表示拓扑落后于权威（不得静默）。
    """
    problems: dict[str, list[str]] = {}
    try:
        for gate in GA.gate_ids():
            allowed = set(GA.actionable_decisions(gate))
            mapped = set(BRANCH_EVENTS.get(gate, {}))
            missing = sorted(allowed - mapped)
            extra = sorted(mapped - allowed)
            if missing or extra:
                problems[gate] = [f"权威有但本层无事件: {missing}", f"本层有但权威无: {extra}"]
    except GA.GateAuthorityUnavailable as exc:  # pragma: no cover
        problems["__authority__"] = [str(exc)]
    return problems


BRANCH_DRIFT = validate_branches()


def _counts_for(data: Any) -> dict[str, Any] | None:
    r = data.get_state("n10_reconcile") or data.get_state("n9_result")
    if isinstance(r, dict) and r.get("counts"):
        return r["counts"]
    return None


def _cycle(data: Any, gate: str) -> int:
    """中断 id 带上返工轮次，避免回边后与已消费的中断撞 id。"""
    if gate == "G2_report_accept":
        return int(data.get_state("n6_n8_cycles") or 0)
    return 0


def decision_options(gate: str) -> list[dict[str, Any]]:
    """操作台的决策按钮**由服务端给出**，来源是权威 —— 前端因此无从漂移。"""
    return [
        {
            "value": d,
            "label": GA.human_readable(gate, d),
            "requires_reason": d in ("ignored", "rework", "disputed"),
        }
        for d in GA.actionable_decisions(gate)
    ]


async def _enter(ctx: RunCtx, data: Any, gate: str) -> dict[str, Any]:
    node = GATE_NODE[gate]
    material = contracts.gate_material(
        gate=gate,
        run_dir=ctx.run_dir,
        counts=_counts_for(data),
        kb=ctx.kb,
        pending_interrupt=None,
        job=None,
        stage="n16_promote" if gate == "G3_regression_decision" else None,
    )
    material["run_id"] = ctx.run_id
    material["cycle"] = _cycle(data, gate)
    material["standin_model_nodes"] = True
    material["decision_options"] = decision_options(gate)
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


async def _resumed(ctx: RunCtx, data: Any, gate: str) -> dict[str, Any]:
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

    # 权威复核：闸门必须已在 gate.py 里获得人类签署（纵深防御，UI 说"已通过"不算数）。
    from .host_steps import run_kb_tool

    check = run_kb_tool("gate.py", ["require-signed", "--run", ctx.run_id, "--gate", gate])
    if check["rc"] != 0:
        ctx.node_failed(node, message=f"authority check failed rc={check['rc']}")
        raise GatePreconditionFailed(
            f"闸门 {gate} 未在 kb/tools/gate.py 中获得权威签署（rc={check['rc']}）：UI 的提交不算权威。"
        )

    # I4：全量/子集回归而冲突未清零 ⇒ 硬阻断
    if gate == "G3_regression_decision" and decision in ("full_now", "subset_only"):
        blocking = [c for c in ctx.kb.load_conflicts().get("items", []) if c.get("blocks_release")]
        if blocking:
            ctx.node_failed(node, message=f"I4：{len(blocking)} 项冲突 blocks_release 未清零")
            raise GatePreconditionFailed(
                f"I4：冲突未清零（{len(blocking)} 项 blocks_release）⇒ 不得选 {decision}。"
            )

    decisions = dict(data.get_state("gate_decisions") or {})
    decisions[gate] = {"decision": decision, "actor": actor, "reason": reason, "cycle": _cycle(data, gate)}
    await data.async_set_state("gate_decisions", decisions)
    await data.async_set_state("gate_actor", actor)
    ctx.event("gate_decided", node=node, status=decision,
              detail={"gate": gate, "decision": decision, "actor": actor, "reason": reason})

    branch = BRANCH_EVENTS[gate][decision]
    ctx.node_finished(node, status=decision, detail={"gate": gate, "decision": decision,
                                                     "branch": branch, "actor": actor})
    await data.async_emit(branch, {"gate": gate, "decision": decision, "actor": actor})
    return {"gate": gate, "decision": decision, "branch": branch}


def make_gate(gate: str):
    async def _gate(data: Any) -> dict[str, Any]:
        ctx = ctx_of(data)
        if getattr(data, "is_resume", False):
            return await _resumed(ctx, data, gate)
        ctx.node_started(GATE_NODE[gate])
        return await _enter(ctx, data, gate)

    _gate.__name__ = f"gate_{gate}"
    return _gate


gate1 = make_gate("G1_diff_confirm")
gate2 = make_gate("G2_report_accept")
gate3 = make_gate("G3_regression_decision")


async def halt(data: Any) -> dict[str, Any]:
    """闸门要求裁决 / 忽略 / 暂缓时，闭环**显式终止**，不假装收敛。"""
    ctx = ctx_of(data)
    decisions = data.get_state("gate_decisions") or {}
    reason = {g: d.get("decision") for g, d in decisions.items()}
    ctx.event("warning", node="HALT", status="halted",
              detail={"reason": "闸门未放行 ⇒ 本轮不继续", "decisions": reason})
    ctx.node_finished("HALT", status="halted", detail=reason)
    return {"halted": True, "decisions": reason}


#: 闸门 id 列表（取自权威，仅暴露用）
GATE_IDS = GA.gate_ids()

#: 合法决策全量（取自权威，仅暴露用）
GATE_DECISIONS = GA.decisions()
