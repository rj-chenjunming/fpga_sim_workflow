"""n8_check 节点实现。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


async def run(data: Any, *, AR, _CHECKLIST, _author_handoff, _cycles_and_limit, _ensure_case_state, _sandbox_code, _set_case_state, _standin, ctx_of, run_model_node) -> dict[str, Any]:
    """N8 静态复核（模型节点）→ 显式分叉到 N6（回边）/ N9 / N13（升级）。

    **fail-closed（#1/C3）**：模型调用失败、输出校验失败、verdict 缺失 ⇒ node_failed；
    绝不再 `verdict = ... or "pass"`。
    """
    ctx = ctx_of(data)
    ctx.node_started("N8")
    cycles, limit = _cycles_and_limit(ctx, data)
    n8_prev = data.get_state("n8_check") or {}
    n6_applied = data.get_state("n6_applied") or {}

    try:
        sandbox_cases, sandbox_names, sandbox_coverage = _sandbox_code(
            ctx, Path(data.require_resource("repo_root")), n6_applied.get("cases") or [])
    except RuntimeError as exc:
        # 闭锁必须留下显式 node_failed，避免 run.error 退化成泛化信息（复核残余项）。
        ctx.node_failed("N8", message=str(exc))
        raise
    revision_points: list[dict[str, Any]] = []
    for target in (data.get_state("n6_targets") or {}).get("targets") or []:
        revision_points.extend(target.get("revision_points") or [])

    applied_edits = [
        {"case": c.get("case"), "file": c.get("file"), "edits": c.get("edits") or []}
        for c in (n6_applied.get("cases") or []) if isinstance(c, dict)
    ]
    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles,
        "sandbox_cases": sandbox_cases,
        "coverage_summary": sandbox_coverage,
        "revision_points": revision_points,
        "applied_edits": applied_edits,
        "author_handoff": _author_handoff(ctx, data, 'N8'),
        "checklist": _CHECKLIST,
        "rework_reasons": [str(f) for f in (n8_prev.get("data") or {}).get("must_fix", [])]
        if isinstance(n8_prev.get("data"), dict) else [],
        "rule": ("verdict=rework 必须给逐条可核依据；只依据本 input 的材料，不得假设未提供的文件内容。"
                 "sandbox_cases[].coverage.mode=changed_regions 时只对这些变更区域内的 touched 行负责，"
                 "coverage_summary 说明全文/片段各多少件。"),
    }
    input_data['review_assignment'] = AR.prepare('N8', input_data)
    out = await run_model_node(ctx, "N8", prompt_key="n8_check",
                               input_data=input_data,
                               offered={"cases": set(sandbox_names), 'review_context': input_data})
    if out["mode"] == "standin":
        if ctx.mode == "real":
            ctx.node_failed("N8", message="real 模式下 N8 无真实模型输出 ⇒ 静态复核不得跳过")
            raise RuntimeError("N8：real 模式要求真实模型复核（standin 不得默认 pass）")
        # drill：夹具 check_C 的结论（accept_v1 依赖 drill 能继续到 G2）
        text = ctx.read_fixture_text("check_C.md") or ""
        rejected = "退回" in text and "通过" not in text
        out["data"] = _standin(ctx, "N8", "check_C.md", extra={
            "verdict": "rework" if rejected else "pass",
            "cycle": cycles, "limit": limit,
            "reject_basis": [ln for ln in text.splitlines() if "退回" in ln][:3],
        })
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N8", message=f"N8 校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N8：静态复核校验失败，不得进入 N9：{problems[:5]}")

    data_out = out.get("data") if isinstance(out.get("data"), dict) else {}
    verdict = str(data_out.get("verdict") or "").strip().lower()
    # P-23：模型实际检查项数与必须修改项数（Host 只做**计数**，判据仍是模型输出+校验）。
    # 没有 findings/must_fix（standin/drill 替身）⇒ 显式 None，不拿 0 冒充"检查了 0 项"。
    findings = data_out.get("findings")
    must_fix = data_out.get("must_fix")
    check_count = len(findings) if isinstance(findings, list) else None
    must_fix_count = len(must_fix) if isinstance(must_fix, list) else None
    if verdict not in ("pass", "rework"):
        # 显式缺失/非法 ⇒ 失败（C3：不得默认 pass）
        ctx.node_failed("N8", message=f"N8 verdict 缺失/非法：{verdict!r}")
        raise RuntimeError(f"N8：verdict 缺失或非法（{verdict!r}）⇒ 不得放行到 N9")

    cases = [str(c.get("case")) for c in (n6_applied.get("cases") or []) if c.get("case")] or sandbox_names
    n8_source = "model_live" if out["mode"] == "live" else "model_standin"
    # drill 的 N8 是**替身复核**（夹具 check_C），不是本轮真实证据；不写本轮用例态台账。
    # 理由：I2 的 G2 前置把"本轮写入的待验"当阻断，drill 全跑证据必然不合格，
    # 若替身复核也写「已修订待验」就会把 accept_v1 的 drill 永久堵在 G2（Lead/WS-L 已确认）。
    write_ledger = ctx.mode == "real"
    if write_ledger:
        _ensure_case_state(ctx)
    else:
        ctx.event("warning", node="N8", status="drill_ledger_skipped",
                  detail={"rule": "drill 替身复核不写用例态台账；I2 以 real 证据为准"})
    if verdict == 'rework' and not write_ledger:
        out.update(cycle=cycles, limit=limit, escalated=True)
        await data.async_set_state('n8_check', out)
        ctx.node_finished('N8', status='escalated', detail={
            'verdict': 'rework', 'cycle': cycles, 'limit': limit, 'source': n8_source,
            'escalated': True,
            'summary': 'N8：drill 静态复核退回，升级人工裁决；无真实返工计数，不自动回环'})
        await data.async_emit('N8_ESCALATE', out)
        return out
    if verdict == "rework" and write_ledger:
        new_cycles = cycles + 1
        ledger_cycles = min(new_cycles, limit)  # case_state 拒绝 > limit；==limit 合法（记录已到上限）
        for idx, case in enumerate(cases):
            res = _set_case_state(
                ctx, case, "已退回",
                rework_cycles=ledger_cycles if idx == 0 else None,
                static_check="reject",
                note=f"N8 静态复核退回（第 {new_cycles} 次返工；limit={limit}）",
                updated_by="loop:N8",
            )
            if res["rc"] != 0:
                ctx.node_failed("N8", message=f"case_state set 失败 rc={res['rc']}")
                raise RuntimeError(f"N8：用例态台账写失败 rc={res['rc']}: {res['stderr_tail'][-300:]}")
        escalated = new_cycles >= limit
        out["cycle"] = new_cycles
        out["limit"] = limit
        out["escalated"] = escalated
        await data.async_set_state("n8_check", out)
        if escalated:
            ctx.node_finished("N8", status="escalated",
                              detail={"verdict": "rework", "cycle": new_cycles,
                                      "limit": limit, "escalated": True,
                                      "check_count": check_count,
                                      "must_fix_count": must_fix_count,
                                      "reason": "N8 返工超限 ⇒ 升级 N13 人工裁决",
                                      "source": n8_source,
                                      "summary": (f"N8：静态复核 rework 第 {new_cycles} 次，"
                                                  f"已达上限 {limit} ⇒ 升级 N13 人工裁决"
                                                  f"（{out['mode']}）")})
            await data.async_emit("N8_ESCALATE", out)
            return out
        ctx.node_finished("N8", status="rework",
                          detail={"verdict": "rework", "cycle": new_cycles, "limit": limit,
                                  "check_count": check_count,
                                  "must_fix_count": must_fix_count,
                                  "source": n8_source,
                                  "summary": (f"N8：静态复核 rework（第 {new_cycles} 次，"
                                              f"上限 {limit}）⇒ 回 N6 返工（{out['mode']}）")})
        await data.async_emit("N8_REWORK", out)
        return out

    # pass：静态卡点 C 通过（态仍是「已修订待验」，卡点D 之后才能「已验证通过」）
    if write_ledger:
        for case in cases:
            res = _set_case_state(ctx, case, "已修订待验", static_check="pass",
                                  note="N8 静态复核通过（卡点C=pass；待卡点D）",
                                  updated_by="loop:N8")
            if res["rc"] != 0:
                ctx.node_failed("N8", message=f"case_state set 失败 rc={res['rc']}")
                raise RuntimeError(f"N8：用例态台账写失败 rc={res['rc']}")
    out["cycle"] = cycles
    out["limit"] = limit
    out["escalated"] = False
    await data.async_set_state("n8_check", out)
    ctx.node_finished("N8", status=out["mode"],
                      detail={"verdict": "pass", "cycle": cycles, "limit": limit,
                              "check_count": check_count,
                              "must_fix_count": must_fix_count,
                              "source": n8_source,
                              "summary": (f"N8：静态复核 pass（第 {cycles} 轮，上限 {limit}，"
                                          f"{len(cases)} 个用例；{out['mode']}）")})
    await data.async_emit("N8_PASS", out)
    return out
