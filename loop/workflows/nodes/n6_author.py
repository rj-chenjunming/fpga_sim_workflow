"""N6 author node."""
from __future__ import annotations
from typing import Any

async def run(data: Any, *, AH, AR, _cycles_and_limit, _observation_points, _standin, build_n6_targets, case_edits_from_output, ctx_of, run_model_node, _workspace_hint, _pin_candidate_baseline, _attach_candidate_channel) -> dict[str, Any]:
    """N6 修订/补充（模型节点）：只出**结构化 edits**，不自己写文件。

    写权边界：Host 的 `n6_apply` 只写 `run_dir/sandbox/TESTLIB/`，不写冻结的 `TESTLIB/`。
    **I7**：本节点不再自增 `n6_n8_cycles`（返工预算只在 N8 判 rework 时消耗）。
    **S6/DS-06 候选通道**：dsh attempt 隔离工作区存在时，输出带四键（`candidate_root` /
    `candidate_manifest` / `baseline` / `execution_state`），供 `n6_apply` 先导入再施加；
    无工作区（agently/drill/旧记录）⇒ 四键**全不给**（legacy 路径），不半给、不降级。
    """
    ctx = ctx_of(data)
    ctx.node_started("N6")
    cycles, limit = _cycles_and_limit(ctx, data)
    n5 = data.get_state("n5_impact") or {}
    n8 = data.get_state("n8_check") or {}
    n11 = data.get_state("n11_review") or {}
    cases = list(n5.get("must_change_cases") or [])

    try:
        rework_handoff = AR.for_author(ctx, data.get_state('n6_author') or {}, n8, n11)
    except (ValueError, OSError) as exc:
        ctx.node_failed("N6", message="返工交接来源核验失败", source="framework")
        raise ValueError("N6 handoff provenance rejected") from exc
    rework_reasons = [item['text'] for item in rework_handoff['issues']]

    targets = build_n6_targets(ctx, data)
    rework_assignment = AH.assignment(rework_handoff, targets)
    await data.async_set_state("n6_targets", {
        "targets": targets,
        "count": len(targets),
        "source": "n5_impact.json + n2_diff.json + ENV_ROOT/TESTLIB 源码摘录",
        "mode": ctx.mode,
    })

    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles + 1,
        "targets": targets,
        "rework_reasons": rework_reasons,
        "rework_handoff": rework_handoff,
        "rework_assignment": rework_assignment,
        "must_change_count": n5.get("must_change_count"),
        "rule": ("只针对 targets 的用例；edits.old 必须逐字取自 targets[].excerpt.text 并且唯一；"
                 "拿不准写进 notes，不要猜。"),
        # S6/DS-06：写权只在 attempt 隔离工作区的候选目录（模型不能写共享 TESTLIB/沙箱）
        "write_scope_rule": ("只写本次 attempt 的 candidate/TESTLIB/<case>.sv（与 work/ 同级）；"
                             "Host 在确认停止后导入候选并落沙箱，模型不得声称已改共享 TESTLIB/沙箱。"),
        # S6-DS06-02：把 Host 已知的工作区绝对路径 + 基线源件位置直接给模型（前两轮实测：
        # 模型去 `find / -name TESTLIB` 找材料，120/300 s 内没写候选）。只给路径，不放宽判据。
        "workspace": _workspace_hint(ctx, targets),
    }
    # S6/DS-06：候选基线必须在**起 prompt 之前** pin（模型看到的源件；之后变了就是漂移）。
    # 只有 real 会产生 attempt 隔离工作区（dsh）；drill/standin 不产生候选通道。
    baseline_pin = _pin_candidate_baseline(data, targets) if ctx.mode == "real" else {}
    out = await run_model_node(
        ctx, "N6", prompt_key="n6_author", input_data=input_data,
        offered={"cases": set(cases) | {t["case"] for t in targets},
                 "rework_assignment": rework_assignment},
    )
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N6", "N6_author_note.md",
                               extra={"cycle": cycles + 1,
                                      "targets": [t["case"] for t in targets],
                                      "write_scope": str(ctx.run_dir / "sandbox" / "TESTLIB")})
    elif (out.get("validation") or {}).get("ok") is not True:
        # P-25：观测点/edits 的 Host 校验失败必须**立刻显式失败**（不得静默继续到 N6_apply），
        # 与 N3/N8/N11/N12 的 fail-closed 一致；错误里带缺哪个用例 / 哪个 marker。
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N6", message=f"N6 修订输出校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N6：修订输出未通过 Host 校验（含观测点约束）：{problems[:5]}")
    # S6/DS-06：实验证通过后接候选通道（四键要么全给、要么全不给）；由 n6_apply 消费。
    _attach_candidate_channel(ctx, out, targets, baseline_pin)
    await data.async_set_state("n6_author", out)
    validation_ok = (out.get("validation") or {}).get("ok")
    source = "model_live" if out["mode"] == "live" else "model_standin"
    # P-20：逐用例修改摘要由模型输出**确定性投影**（Host 不猜"改了哪一处"）；
    # 与 N6_apply 的清单同源（同一函数），没有模型输出时显式 None。
    case_edits = case_edits_from_output(out.get("data") if isinstance(out.get("data"), dict) else None)
    observation_points = _observation_points(
        out.get("data") if isinstance(out.get("data"), dict) else None)
    ctx.node_finished("N6", status=out["mode"],
                      detail={"mode": out["mode"], "cycle": cycles + 1,
                              "targets": len(targets),
                              "validation_ok": validation_ok,
                              "source": source,
                              "case_edits": case_edits,
                              "case_edits_source": "n6_output",
                              "observation_points": observation_points,
                              "summary": (
                                  f"N6：第 {cycles + 1} 轮修订，目标 {len(targets)} 个用例，"
                                  "输出校验"
                                  + ("通过" if validation_ok is True
                                     else "未通过" if validation_ok is False else "未下发")
                                  + f"（{out['mode']}）"
                              )})
    return out
