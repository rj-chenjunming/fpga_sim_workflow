"""n10_reconcile 节点实现。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


async def run(data: Any, *, MP, PENDING_CLASSES, _artifact, _case_pass_fields, _cases_table, _classification_summary, _diffs_for_classification, _per_case_fail_buckets, _persist_pending, _reconcile_markdown, _set_case_state, _write_text, counts_text, ctx_of, ledger, run_model_node) -> dict[str, Any]:
    """N10 结果对账（Host 抽数 + 模型 FAIL 三分类）。

    - **Host 确定性**：两套口径/印记/身份一律来自 `host.evidence` 聚合，模型只对**桶**分类；
    - **持久化（#18/A9）**：`n10_reconcile.md` + 分类 2/3 → `kb/tools/n10_pending.py`；
    - **I2**：逐例写用例态（`已验证通过` 走工具合取门槛；证据不全由工具拒绝 ⇒ 本节点失败）；
    - **C10**：分类校验失败 ⇒ node_failed（阻断 gate2）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N10")
    diffs = _diffs_for_classification(ctx)

    if ctx.mode == "drill":
        ev = ctx.evidence()
        reconcile_text = ctx.read_fixture_text("reconcile.md") or ""
        from host.evidence import fail_buckets

        log_path = ctx.evidence_log()
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
        fb = fail_buckets(log_text, diffs)
        out = {
            "run_id": ctx.run_id,
            "evidence": ev,
            "counts": ev.get("counts"),
            "verdict": ev.get("verdict"),
            "target_cases": ["tc_pcie_rw_02"],
            "cases": {"tc_pcie_rw_02": {"present": ev.get("present"),
                                        "counts": ev.get("counts"),
                                        "imprints": ev.get("imprints"),
                                        "verdict": ev.get("verdict"),
                                        "path": ev.get("path")}},
            "both_zero": (ev.get("counts") or {}).get("both_zero"),
            "extraction_owner": "host:host/evidence.py（确定性；不经模型）",
            "fail_buckets": {
                "bucket_count": fb["bucket_count"],
                "merged_note": fb["merged_note"],
                "coverage": fb["coverage"],
                "revision_points": fb["revision_points"],
                "any_bucket_overlaps_revision_point": any(
                    b["overlaps_revision_point"] for b in fb["buckets"]),
                "extraction_owner": fb["extraction_owner"],
            },
        }
        classify_input = {
            "run_id": ctx.run_id,
            "revision_points": fb["revision_points"],
            "buckets": [
                {"bucket_id": b["bucket_id"], "channel": b["channel"], "range": b["range"],
                 "entry_count": b["entry_count"], "address_count": b["address_count"],
                 "sample_addresses": b["sample_addresses"],
                 "overlaps_revision_point": b["overlaps_revision_point"]}
                for b in fb["buckets"]
            ],
            "counts": ev.get("counts"),
            "rule": "数字与分桶由 Host 给出，不得改写；判「本轮引入」必须落在 revision_points 上。",
        }
        cls_out = await run_model_node(ctx, "N10", prompt_key="n10_fail_classify",
                                       input_data=classify_input, offered={"buckets": fb["buckets"]})
        if cls_out["mode"] == "standin":
            cls_out["data"] = {
                "standin": True, "provider": "none",
                "reason": f"未接入模型（{MP.resolve().reason}）；FAIL 三分类为确定性替身。",
                "excerpt": reconcile_text[:600],
                "classes": ["既有缺陷", "本轮引入", "待裁决"],
                "note": "分桶与计数仍是 Host 确定性的（见 fail_buckets）。",
            }
        ctx.event(
            "warning", node="N10", status="drill_ledger_skipped",
            detail={"drill_skips_case_state": True,
                    "reason": ("drill 的卡点D 证据是夹具且必然不合格（口径一≠0），写「已验证通过」"
                               "既不可能也不诚实；I2 以 real 证据为准")},
        )
        out["case_state_written"] = False
        out["fail_classification"] = cls_out
        out["pending_items"] = []
        out["pending_path"] = None
        reconcile_path = _artifact(ctx, "n10_reconcile.md")
        _write_text(reconcile_path, _reconcile_markdown(out))
        out["reconcile_md_path"] = str(reconcile_path)
        await data.async_set_state("n10_reconcile", out)
        ctx.node_finished("N10", status="pass" if out["both_zero"] else "fail",
                          detail={"both_zero": out["both_zero"],
                                  "cases_table": _cases_table(out.get("cases")),
                                  "classification": _classification_summary(
                                      bucket_count=fb.get("bucket_count"), items=None),
                                  "source": ("model_live" if cls_out["mode"] == "live"
                                             else "model_standin"),
                                  "summary": (
                                      f"N10：{len(out['target_cases'])} 个用例对账，"
                                      f"{counts_text(out.get('counts'))}，"
                                      f"both_zero={out['both_zero']}（{cls_out['mode']}）"
                                  )},
                          refs=[ev.get("path", ""), str(reconcile_path)])
        return out

    # ---------------------------------------------------------------- real
    n9 = data.get_state("n9_result") or {}
    cases = n9.get("cases") if isinstance(n9.get("cases"), dict) else {}
    if not cases:
        ctx.node_failed("N10", message="没有 N9 聚合证据（n9_result 缺失）")
        raise RuntimeError("N10：缺少 N9 聚合证据，不得对账")
    target_cases = [str(c) for c in (n9.get("target_cases") or [])]
    absent = [c for c in target_cases if not (cases.get(c) or {}).get("present")]
    if absent:
        ctx.node_failed("N10", message=f"证据不可用：{absent}")
        raise RuntimeError(f"N10：以下用例证据不可用：{absent}")

    fb = _per_case_fail_buckets(ctx, cases, diffs)
    classify_input = {
        "run_id": ctx.run_id,
        "revision_points": fb["revision_points"],
        "buckets": [
            {"bucket_id": b["bucket_id"], "channel": b["channel"], "range": b["range"],
             "entry_count": b["entry_count"], "address_count": b["address_count"],
             "sample_addresses": b["sample_addresses"],
             "overlaps_revision_point": b["overlaps_revision_point"]}
            for b in fb["buckets"]
        ],
        "counts": n9.get("counts"),
        "rule": "数字与分桶由 Host 给出，不得改写；判「本轮引入」必须落在 revision_points 上。",
    }
    cls_out = await run_model_node(ctx, "N10", prompt_key="n10_fail_classify",
                                   input_data=classify_input, offered={"buckets": fb["buckets"]})
    if cls_out["mode"] == "standin":
        ctx.node_failed(
            "N10",
            message="real 模式下 N10 无真实模型分类 ⇒ fail closed（real 端到端需 live provider；"
                    "standin 不冒充，不得放行 gate2）",
        )
        raise RuntimeError(
            "N10：real 模式要求 live provider 的 FAIL 三分类（standin 不冒充；real 端到端需 live provider）"
        )
    if (cls_out.get("validation") or {}).get("ok") is not True:
        problems = (cls_out.get("validation") or {}).get("problems") or ["分类校验失败"]
        ctx.node_failed("N10", message=f"N10 分类校验失败（阻断 gate2）：{problems[:3]}")
        raise RuntimeError(f"N10：FAIL 三分类校验失败，阻断 gate2：{problems[:5]}")

    cls_data = cls_out.get("data") if isinstance(cls_out.get("data"), dict) else {}
    bucket_by_id = {str(b["bucket_id"]): b for b in fb["buckets"]}
    pending_items: list[dict[str, Any]] = []
    for bucket in cls_data.get("items") or []:
        cls = str(bucket.get("classification") or "")
        if cls not in PENDING_CLASSES:
            continue
        src = bucket_by_id.get(str(bucket.get("bucket_id"))) or {}
        pending_items.append({
            "bucket_id": str(bucket.get("bucket_id")),
            "case": str(src.get("case") or ""),
            "classification": cls,
            "address_range": str(src.get("range") or ""),
            "count": int(src.get("entry_count") or 0),
            "basis": str(bucket.get("basis") or ""),
            "evidence_path": str((cases.get(str(src.get("case"))) or {}).get("path") or ""),
        })
    pending_meta = _persist_pending(ctx, pending_items)

    # I2：逐例写用例态（工具做 I3 合取门槛；被拒 ⇒ 本节点失败，不静默跳过）
    n7 = data.get_state("n7_compile") or {}
    n9_md5s = n9.get("run_md5s") or {}
    n9["run_md5s"] = n9_md5s
    for case in target_cases:
        item = cases.get(case) or {}
        verdict = item.get("verdict") or {}
        if verdict.get("passed"):
            fields = _case_pass_fields(ctx, case, item, n7, n9, ledger)
            res = _set_case_state(ctx, case, "已验证通过", **fields)
            if res["rc"] != 0:
                ctx.node_failed(
                    "N10",
                    message=f"{case} 判据通过但用例态写入被工具拒绝 rc={res['rc']}",
                )
                raise RuntimeError(
                    f"N10：{case} 证据通过但 case_state 拒绝写入（I3 合取缺项）："
                    f"{res['stderr_tail'][-400:]}"
                )
        else:
            _set_case_state(ctx, case, "已修订待验",
                            note="N10：卡点D 判据未通过 ⇒ 保持待验，不得称跑通",
                            updated_by="loop:N10")

    out = {
        "run_id": ctx.run_id,
        "evidence": n9.get("evidence"),
        "counts": n9.get("counts"),
        "verdict": n9.get("verdict") or {},
        "identity": n9.get("identity") or {},
        "target_cases": target_cases,
        "cases": cases,
        "both_zero": (n9.get("counts") or {}).get("both_zero"),
        "extraction_owner": "host:host/evidence.py（聚合确定性；不经模型）",
        "fail_buckets": {k: fb[k] for k in ("buckets", "revision_points", "merged_note")},
        "fail_classification": cls_out,
        **pending_meta,
        "pending_items": pending_items,
    }
    reconcile_path = _artifact(ctx, "n10_reconcile.md")
    _write_text(reconcile_path, _reconcile_markdown(out))
    out["reconcile_md_path"] = str(reconcile_path)
    await data.async_set_state("n10_reconcile", out)
    status = "pass" if (n9.get("verdict") or {}).get("passed") else "fail"
    ctx.node_finished("N10", status=status,
                      detail={"cases": len(target_cases),
                              "verdict_passed": (n9.get("verdict") or {}).get("passed"),
                              "pending": len(pending_items),
                              # P-26：逐用例表与失败分类摘要（只投影既有证据/模型输出）
                              "cases_table": _cases_table(cases),
                              "classification": _classification_summary(
                                  bucket_count=len(fb.get("buckets") or []),
                                  items=cls_data.get("items")),
                              "source": ("model_live" if cls_out["mode"] == "live"
                                         else "model_standin"),
                              "summary": (
                                  f"N10：{len(target_cases)} 个用例对账，"
                                  f"{counts_text(n9.get('counts'))}，"
                                  f"verdict_passed={(n9.get('verdict') or {}).get('passed')}，"
                                  f"待裁决 {len(pending_items)} 项（{cls_out['mode']}）"
                              )},
                      refs=[str(reconcile_path)] + [str((cases.get(c) or {}).get("path") or "")
                                                    for c in target_cases][:4])
    return out
