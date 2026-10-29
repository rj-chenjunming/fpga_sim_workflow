"""n11_review 节点实现。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


async def run(data: Any, *, AR, _author_handoff, _cycles_and_limit, _ensure_case_state, _host_identity, _identity_table, _ledger_summary, _set_case_state, _standin, ctx_of, ledger, run_model_node) -> dict[str, Any]:
    """N11 证据守护（模型：成链判断；Host：身份四方同值 + 结论交叉核对）。

    **业务 N11 = guardian**（审计 #15/A10）：
    - 成链 ⇒ `N11_INTACT` → N12；
    - 不成链 ⇒ `N11_REWORK` → N6（显式回边），并带返工请求；
    - Host 事实「不一致」而模型说 intact ⇒ fail closed（模型不得替 Host 掩盖身份错位）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N11")
    n10 = data.get_state("n10_reconcile") or {}
    n9 = data.get_state("n9_result") or {}
    counts = n10.get("counts") or n9.get("counts") or {}
    evidence = n10.get("evidence") or n9.get("evidence") or {}

    if ctx.mode == "drill":
        host_identity: dict[str, Any] = {
            "run_id": ctx.run_id, "consistent": True, "mismatches": [],
            "cases": [], "mode": "drill",
            "note": "drill：身份链使用夹具，不做真实四方同值强判（real 才强判）。",
        }
    else:
        host_identity = _host_identity(ctx, data)

    input_data = {
        "run_id": ctx.run_id,
        "identity": host_identity,
        "author_handoff": _author_handoff(ctx, data, 'N11'),
        "counts": counts,
        "verdict": n10.get("verdict") or n9.get("verdict"),
        "evidence": {
            "path": (evidence or {}).get("path"),
            "present": (evidence or {}).get("present"),
            "cases": {
                case: {
                    "path": (item or {}).get("path"),
                    "present": (item or {}).get("present"),
                    "counts": (item or {}).get("counts"),
                    "imprints": (item or {}).get("imprints"),
                    "identity": (item or {}).get("identity"),
                }
                for case, item in ((n9.get("cases") or {}) if isinstance(n9.get("cases"), dict) else {}).items()
            },
        },
        "case_states": _ledger_summary(ctx),
        "rework": ctx.kb.load_rework(ctx.run_dir),
        "rule": ("只判证据链是否成链：身份四方同值且证据可解析=intact；任一缺失/不一致=broken。"
                 "任何一项缺失不得判 intact。"),
    }
    input_data['review_assignment'] = AR.prepare('N11', input_data)
    out = await run_model_node(ctx, "N11", prompt_key="n11_review", input_data=input_data,
                               offered={"counts": counts, 'review_context': input_data})
    if out["mode"] == "standin":
        if ctx.mode == "real":
            ctx.node_failed("N11", message="real 模式下 N11 无真实模型输出 ⇒ 证据守护不得跳过")
            raise RuntimeError("N11：real 模式要求真实 guardian 判成链（standin 不得判 intact）")
        out["data"] = _standin(ctx, "N11", "reconcile.md", extra={
            "chain": "intact",
            "reasons": ["drill/standin：按夹具证据链视为 intact（非模型结论）"],
            "rework_requests": [],
            "caveats": ["drill 替身，不构成真实证据守护结论"],
        })
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N11", message=f"N11 校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N11：证据守护校验失败：{problems[:5]}")

    data_out = out.get("data") if isinstance(out.get("data"), dict) else {}
    model_chain = str(data_out.get("chain") or "").strip().lower()
    if model_chain not in ("intact", "broken"):
        ctx.node_failed("N11", message=f"N11 chain 缺失/非法：{model_chain!r}")
        raise RuntimeError("N11：chain 缺失或非法 ⇒ 不得放行 N12")

    host_consistent = bool(host_identity.get("consistent"))
    if not host_consistent and model_chain == "intact":
        # Host 事实说不一致，模型却判 intact ⇒ 模型结论不得覆盖 Host 事实
        ctx.node_failed("N11", message="模型判 intact 但 Host 身份四方同值不成立（不得掩盖身份错位）")
        raise RuntimeError(
            "N11：Host 身份校验失败（"
            + "；".join(host_identity.get("mismatches") or [])[:500]
            + "），模型不得判 intact"
        )
    rework_requests = list(data_out.get("rework_requests") or [])
    if not host_consistent and not rework_requests:
        rework_requests = [
            {"case": c.get("case"), "what": "补齐/重采证据并核对 md5 与 run_id",
             "basis": "; ".join(host_identity.get("mismatches") or [])[:300]}
            for c in host_identity.get("cases") or []
        ]
    chain_effective = "broken" if (not host_consistent or model_chain == "broken") else "intact"
    out["host_identity"] = host_identity
    out["chain_effective"] = chain_effective
    out["model_chain"] = model_chain
    out["rework_requests"] = rework_requests
    # P-27：逐用例身份表 / 未闭环项 / 返工请求条数（三个分支共用同一投影，不各算一套）
    identity_table = _identity_table(host_identity)
    unclosed = [str(x) for x in (data_out.get("caveats") or [])]
    rework_requests_count = len(rework_requests)
    await data.async_set_state("n11_review", out)

    n11_source = "model_live" if out["mode"] == "live" else "model_standin"
    if chain_effective == "broken":
        # I7：证据守护返工同样吃掉返工预算（否则 broken↔N6 会无限循环）
        cycles, limit = _cycles_and_limit(ctx, data)
        new_cycles = cycles + 1
        _ensure_case_state(ctx)
        for idx, item in enumerate(ledger(ctx).get("cases") or []):
            case = str(item.get("case") or "")
            if not case:
                continue
            _set_case_state(
                ctx, case, "已修订待验",
                rework_cycles=min(new_cycles, limit) if idx == 0 else None,
                note=f"N11 证据链 broken ⇒ 回 N6 返工（第 {new_cycles} 次；limit={limit}）",
                updated_by="loop:N11",
            )
        out["cycle"] = new_cycles
        out["limit"] = limit
        await data.async_set_state("n11_review", out)
        if new_cycles >= limit:
            # I7：超限不再直接死掉，而是**升级 N13 人工裁决**（N11_ESCALATE→gate2，lifecycle 加边）
            ctx.node_finished(
                "N11", status="escalated",
                detail={"chain": "broken", "cycle": new_cycles, "limit": limit,
                        "escalated": True,
                        "identity_table": identity_table,
                        "unclosed": unclosed,
                        "rework_requests_count": rework_requests_count,
                        "reason": "N11 证据守护返工超限 ⇒ 升级 N13 人工裁决",
                        "source": n11_source,
                        "summary": (f"N11：证据链 broken 第 {new_cycles} 次，已达上限 {limit}"
                                    f" ⇒ 升级 N13 人工裁决（{out['mode']}）")},
            )
            await data.async_emit("N11_ESCALATE", out)
            return out
        ctx.node_finished("N11", status="broken",
                          detail={"chain": "broken", "host_consistent": host_consistent,
                                  "rework": len(rework_requests), "cycle": new_cycles,
                                  "limit": limit,
                                  "identity_table": identity_table,
                                  "unclosed": unclosed,
                                  "rework_requests_count": rework_requests_count,
                                  "source": n11_source,
                                  "summary": (f"N11：证据链 broken（第 {new_cycles} 次，"
                                              f"上限 {limit}；Host 身份四方同值"
                                              f"{'成立' if host_consistent else '不成立'}）"
                                              f"⇒ 回 N6 返工，返工请求 "
                                              f"{len(rework_requests)} 条（{out['mode']}）")})
        await data.async_emit("N11_REWORK", out)
        return out
    ctx.node_finished("N11", status="intact",
                      detail={"chain": "intact", "host_consistent": host_consistent,
                              "identity_table": identity_table,
                              "unclosed": unclosed,
                              "rework_requests_count": rework_requests_count,
                              "source": n11_source,
                              "summary": (f"N11：证据链 intact（Host 身份四方同值"
                                          f"{'成立' if host_consistent else '不成立'}，"
                                          f"返工请求 {len(rework_requests)} 条；"
                                          f"{out['mode']}）")})
    await data.async_emit("N11_INTACT", out)
    return out
