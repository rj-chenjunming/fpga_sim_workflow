"""n5_impact 节点实现。"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any


async def run(data: Any, *, ctx_of, ARTIFACTS, _load_json, _to_check_fields, run_kb_tool) -> dict[str, Any]:
    """N5 影响分析。**只在闸门1 有权威签署后允许执行。**

    这里做的是纵深防御：即使 `gate.py` 前置校验被绕过，本节点仍会拒绝。
    """
    ctx = ctx_of(data)
    ctx.node_started("N5")
    target = ctx.run_dir / ARTIFACTS["n5"]

    signed = run_kb_tool(
        "gate.py",
        ["require-signed", "--run", ctx.run_id, "--gate", "G1_diff_confirm", "--expect", "confirmed"],
    )
    if signed["rc"] != 0:
        ctx.node_failed("N5", message=f"I1：G1 未获人类确认，拒绝进入修订阶段（rc={signed['rc']}）")
        raise PermissionError("I1：G1_diff_confirm 未获人类 confirmed 签署，N5 拒绝执行")

    result: dict[str, Any] = {"artifact": str(target), "gate1_rc": signed["rc"]}
    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n5_impact.json"))
        if doc is None:
            ctx.node_failed("N5", message="夹具缺 n5_impact.json")
            raise FileNotFoundError("夹具缺 n5_impact.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update({"rc": 0, "source": "drill_fixture"})
    else:
        run = run_kb_tool("n5_impact.py", ["--run", ctx.run_id, "--out-dir", str(ctx.run_dir)])
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] not in (0, 3):
            ctx.node_failed("N5", message=f"n5_impact rc={run['rc']}")
            raise RuntimeError(f"n5_impact rc={run['rc']}")

    doc = _load_json(target) or {}
    must_change = doc.get("must_change", []) if isinstance(doc, dict) else []
    index_gaps = doc.get("index_gaps", [])
    # P-19：待查条目**只从 N5 产物 `to_check` 取**（不解析 stdout、不猜数字）。
    result.update(
        {
            "must_change_count": len(must_change),
            "must_change_cases": sorted({m.get("case") for m in must_change if m.get("case")}),
            "index_complete": doc.get("index_complete"),
            "index_gaps": index_gaps,
            # §10.4：索引缺口计数（取自 N5 产物自身，不重算判据）
            "index_gap_count": len(index_gaps) if isinstance(index_gaps, list) else 0,
            # P-19：待查条目数 / 去重用例数 / 用例名
            **_to_check_fields(doc),
        }
    )
    gap_count = result["index_gap_count"]
    cases_text = "、".join(result["must_change_cases"]) or "无"
    result["summary"] = (
        f"N5：必改 {result['must_change_count']} 个用例（{cases_text}），"
        f"索引缺口 {gap_count} 条，index_complete={result['index_complete']}；"
        f"gate1 签署校验 rc={result['gate1_rc']}"
    )
    await data.async_set_state("n5_impact", result)
    ctx.node_finished("N5", detail=result, refs=[str(target)])
    return result
