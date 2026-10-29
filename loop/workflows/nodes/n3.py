"""n3_digest 节点实现。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


async def run(data: Any, *, _artifact, _compose_n3_markdown, _n3_detail, _standin, _write_text, ctx_of, run_model_node) -> dict[str, Any]:
    """N3 差异摘要（模型节点）→ 落盘 `run_dir/n3_digest.md`。

    **A21**：模型调用/解析失败必须显式终止本轮，不得只记 problems 继续（空摘要不得进 Gate1）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N3")
    n2 = data.get_state("n2_diff") or {}
    diff_path = ctx.run_dir / "n2_diff.json"
    diffs: list[dict[str, Any]] = []
    context_error = None
    try:
        doc = json.loads(diff_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("diffs"), list) or any(not isinstance(d, dict) for d in doc["diffs"]):
            raise ValueError("diffs 必须是对象列表")
        diffs = doc["diffs"]
    except (OSError, ValueError) as exc:
        context_error = f"{type(exc).__name__}: {exc}"
        if ctx.mode == "real":
            ctx.node_failed("N3", message="N3 上下文缺失或格式错误：" + context_error)
            raise RuntimeError("N3 上下文缺失或格式错误：" + context_error) from exc
        diffs = []

    input_data = {
        "run_id": ctx.run_id,
        # P-14 ④：`id` / `offsets` 是 N2 产物**已有**的字段，显式下发让模型能说清
        # "是哪个文件、哪个偏移"（不新增取数、不构造证据）。
        "diffs": [
            {**d, "entry_id": d.get("entry_id") or d.get("id"), "id": d.get("id"),
             "offsets": d.get("offsets") or ([d["offset"]] if d.get("offset") else []),
             "segment": d.get("segment"),
             "offset": d.get("offset"), "kind": d.get("kind"),
             "before": str(d.get("before")), "after": str(d.get("after"))}
            for d in diffs
        ],
        "offered_segments": sorted({str(d.get("segment")) for d in diffs if d.get("segment")}),
        "coverage": {"scope": "all_differences", "total": len(diffs), "provided": len(diffs),
                     "complete": context_error is None, "error": context_error},
    }
    out = await run_model_node(
        ctx, "N3", prompt_key="n3_digest", input_data=input_data,
        offered={"diff_ids": {str(d.get("entry_id") or d.get("id")) for d in diffs},
                 "segments": set(input_data["offered_segments"])},
    )
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N3", "n3_digest.md",
                               extra={"diff_count": n2.get("diff_count")})
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N3", message=f"N3 校验失败，终止本轮：{problems[:3]}")
        raise RuntimeError(f"N3：差异摘要校验失败（不得把空摘要送 Gate1）：{problems[:5]}")

    if ctx.mode == "drill":
        fixture_text = ctx.read_fixture_text("n3_digest.md")
        text = fixture_text if fixture_text is not None else _compose_n3_markdown(out)
    elif out["mode"] == "standin":
        # real 端到端需要 live provider；standin **不冒充**模型结论（禁止用替身摘要进 Gate1）
        ctx.node_failed(
            "N3",
            message="real 模式下 N3 无真实模型输出 ⇒ fail closed（real 端到端需 live provider；"
                    "standin 不冒充模型结论）",
        )
        raise RuntimeError(
            "N3：real 模式要求 live provider（standin 不得作为差异摘要进入 Gate1；"
            "real 端到端需 live provider）"
        )
    else:
        text = _compose_n3_markdown(out)
    digest_path = _artifact(ctx, "n3_digest.md")
    _write_text(digest_path, text)
    out["artifact_path"] = str(digest_path)
    await data.async_set_state("n3_digest", out)
    # §10.4：模型节点 source 按 live/standin 取。
    # P-13/P-14：节点摘要**改用模型 summary**，组数降级为关键数字（`groups_count`）；
    # 没有模型输出（standin/drill）时如实说"模型摘要未下发"，不拿夹具正文冒充。
    source = "model_live" if out["mode"] == "live" else "model_standin"
    covered = n2.get("diff_count")
    detail_fields = _n3_detail(
        out, offered_segments_empty=not input_data["offered_segments"]
    )
    confirmations = detail_fields["digest_confirmations"] or []
    if detail_fields["digest_summary"]:
        summary = f"N3：{detail_fields['digest_summary']}"
        if confirmations:
            summary += f"（另有 {len(confirmations)} 条需要你确认）"
    else:
        summary = (f"N3：模型摘要未下发（{out['mode']} 模式未产出模型结论），"
                   f"覆盖 {covered if covered is not None else '未下发'} 条差异")
    ctx.node_finished("N3", status="ok" if out["mode"] in ("live", "standin") else "failed",
                      detail={"mode": out["mode"], "provider": out.get("provider"),
                              "problems": (out.get("validation") or {}).get("problems", [])[:3],
                              "source": source, "summary": summary, **detail_fields},
                      refs=[str(digest_path)])
    return out
