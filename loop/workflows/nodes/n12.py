"""n12_report 节点实现。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


async def run(data: Any, *, _artifact, _compose_n12_markdown, _ledger_summary, _n12_detail, _resolve_ref, _standin, _write_text, ctx_of, ledger, run_model_node) -> dict[str, Any]:
    """N12 报告（模型节点）→ 落盘 `run_dir/n12_report.md`。

    **#18/A20**：报告必须落盘；**引用不可解析 ⇒ 拒发（node_failed）**。
    **#22/I15**：结构化 `claimed_verdict` 与 Host 权威判决逐值比对（删除子串判据）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N12")
    n10 = data.get_state("n10_reconcile") or {}
    n5 = data.get_state("n5_impact") or {}
    n11 = data.get_state("n11_review") or {}
    n9 = data.get_state("n9_result") or {}
    counts = n10.get("counts") or n9.get("counts") or {}
    evidence = n10.get("evidence") or n9.get("evidence") or {}
    conflicts = ctx.kb.load_conflicts()

    verdict = n10.get("verdict") or n9.get("verdict") or {}
    input_data = {
        "run_id": ctx.run_id,
        "counts": counts,
        "verdict": verdict,
        "imprints": {k: {"consistent": v.get("consistent"),
                         "verified": v.get("verified_count"),
                         "observed": v.get("observed"), "expected": v.get("expected")}
                     for k, v in ((evidence or {}).get("imprints") or {}).items()},
        "cases": n9.get("cases") or {},
        "evidence_paths": n9.get("evidence_paths") or {},
        "chain": n11.get("chain_effective"),
        "must_change_count": n5.get("must_change_count"),
        "must_change_cases": n5.get("must_change_cases", []),
        "case_states": _ledger_summary(ctx),
        "conflicts": {"total": len(conflicts.get("items", [])),
                      "blocks_release": len([c for c in conflicts.get("items", [])
                                             if c.get("blocks_release")])},
        "rule": ("所有数字逐字引用本 input，禁止手算；claimed_verdict 必须与 input.verdict.passed "
                 "一致；sections[].refs 必须是可解析的产物路径。"),
    }
    out = await run_model_node(ctx, "N12", prompt_key="n12_report", input_data=input_data,
                               offered={"counts": counts, "verdict": verdict})
    if out["mode"] == "standin":
        if ctx.mode == "real":
            ctx.node_failed("N12", message="real 模式下 N12 无真实模型输出 ⇒ 不得发布报告")
            raise RuntimeError("N12：real 模式要求真实报告（standin 不得冒充）")
        fixture_text = ctx.read_fixture_text("n12_report.md")
        report_text = fixture_text if fixture_text is not None else (
            "# N12 评估报告（STANDIN）\n\n> drill 替身；非模型结论。\n")
        out["data"] = _standin(ctx, "N12", "n12_report.md", extra={
            "koutou1": (counts.get("koutou1") or {}).get("value"),
            "koutou2": (counts.get("koutou2") or {}).get("value"),
            "claimed_verdict": ("passed" if verdict.get("passed") is True
                                else "not_passed" if verdict.get("passed") is False
                                else "undetermined"),
            "number_rule": "报告里所有数字一律由命令输出复制，禁手算（doc/AGENTS.md 红线 10）。",
        })
        report_text_written = report_text
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N12", message=f"N12 校验失败（拒发）：{problems[:3]}")
        raise RuntimeError(f"N12：报告校验失败，拒发：{problems[:5]}")
    else:
        report_text_written = _compose_n12_markdown(out)

    data_out = out.get("data") if isinstance(out.get("data"), dict) else {}
    refs: list[str] = []
    for section in data_out.get("sections") or []:
        refs.extend(str(r) for r in (section.get("refs") or []))
    unresolved = [r for r in refs if _resolve_ref(ctx, r) is None]
    if unresolved:
        ctx.node_failed("N12", message=f"报告引用不可解析：{unresolved[:5]}")
        raise RuntimeError(f"N12：报告引用不可解析，拒发：{unresolved[:5]}")

    if ctx.mode == "drill":
        # drill：n0 已把夹具报告复制到 run_dir；确保内容与夹具一致（accept_v1 校验存在性/内容）
        fixture_text = ctx.read_fixture_text("n12_report.md")
        if fixture_text is not None:
            report_text_written = fixture_text

    report_path = _artifact(ctx, "n12_report.md")
    _write_text(report_path, report_text_written)
    out["report_path"] = str(report_path)
    out["refs_checked"] = refs
    out["unresolved_refs"] = unresolved
    out["authoritative_verdict"] = verdict
    await data.async_set_state("n12_report", out)
    # §10.4：detail 内的计数改名为 `ref_count`（`refs` 是**事件顶层**字段，同名会误导消费方）。
    ctx.node_finished("N12", status=out["mode"],
                      detail={"mode": out["mode"],
                              "claimed_verdict": data_out.get("claimed_verdict"),
                              "ref_count": len(refs),
                              **_n12_detail(data_out, refs=refs, unresolved=unresolved,
                                            ledger_cases=ledger(ctx).get("cases") or []),
                              "source": ("model_live" if out["mode"] == "live"
                                         else "model_standin"),
                              "summary": (f"N12：报告 claimed_verdict="
                                          f"{data_out.get('claimed_verdict')}，"
                                          f"引用 {len(refs)} 条（不可解析 {len(unresolved)} 条）；"
                                          f"mode={out['mode']}")},
                      refs=[str(report_path)] + [str(_resolve_ref(ctx, r)) for r in refs][:4])
    return out
