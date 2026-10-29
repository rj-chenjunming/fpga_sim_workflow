"""halt 节点实现。"""
from __future__ import annotations
from typing import Any


async def run(data: Any, *, GA, GATE_LABEL_CN, ctx_of) -> dict[str, Any]:
    """闸门要求裁决 / 忽略 / 暂缓时，闭环**显式终止**，不假装收敛。"""
    ctx = ctx_of(data)
    decisions = data.get_state("gate_decisions") or {}
    decision_map = {g: d.get("decision") for g, d in decisions.items()}
    # P-35：终止原因写**白话**（原值仍原样留在 `decisions` 与既有 `{闸门: 决策}` 字段里）。
    parts = [
        f"{GATE_LABEL_CN.get(gate, gate)}选了「{GA.human_readable(gate, str(decision))}」"
        for gate, decision in decision_map.items() if decision
    ]
    reason_text = ("本轮在 " + "；".join(parts) + " 处终止，所以不继续往下走"
                   if parts else "闸门未放行，所以本轮不继续往下走")
    ctx.event("warning", node="HALT", status="halted",
              detail={"reason": reason_text, "decisions": decision_map})
    # §10.4：HALT 的 summary 用终止原因原文；detail 原有的 `{闸门: 决策}` 字段原样保留。
    decisions_text = "；".join(f"{gate}={item.get('decision')}" for gate, item in decisions.items())
    ctx.node_finished("HALT", status="halted", detail={
        **decision_map,
        "reason": reason_text,
        "decisions": decision_map,
        "source": "framework",
        "summary": ("HALT：" + reason_text
                    + (f"（{decisions_text}）" if decisions_text else "（无闸门决策）")),
    })
    return {"halted": True, "decisions": decision_map}
