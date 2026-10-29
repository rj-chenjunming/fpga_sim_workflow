"""n2_diff 节点实现。"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any


async def run(data: Any, *, ctx_of, ARTIFACTS, _load_json, _selected_baseline, run_kb_tool) -> dict[str, Any]:
    """N2 差异对比。

    退出码语义**只以 `kb/tools/n2_diff.py` 为准**（SPEC-REV-01 §D E1）：
    `0` 成功；`3` = blocking 输入缺口（**不产出** `n2_diff.json`，写 `n2_diff.gap.json/.md`）；
    `4` = selfcheck 失败。因此 3/4 都必须显式失败——不得把"没产出差异清单"当成"0 条差异"。
    """
    ctx = ctx_of(data)
    ctx.node_started("N2")
    target = ctx.run_dir / ARTIFACTS["n2"]
    result: dict[str, Any] = {"artifact": str(target)}

    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n2_diff.json"))
        if doc is None:
            ctx.node_failed("N2", message="夹具缺 n2_diff.json")
            raise FileNotFoundError("夹具缺 n2_diff.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result["rc"] = 0
        result["source"] = "drill_fixture"
    else:
        # 身份单一来源（编排规格 §3.1）：入口解析一次，N0 写 run_meta，N1/N2 消费同一值。
        # 旧实现这里硬编码 "v0" ⇒ 选 v-next 仍按 v0 做 diff；现在缺身份即 fail closed。
        from_baseline = _selected_baseline(data, "N2")
        run = run_kb_tool(
            "n2_diff.py",
            ["--from-baseline", from_baseline, "--to-manifest", str(ctx.run_dir / ARTIFACTS["n1"]),
             "--run", ctx.run_id, "--out-dir", str(ctx.run_dir)],
        )
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] == 3:
            gap = ctx.run_dir / "n2_diff.gap.json"
            ctx.node_failed(
                "N2",
                message=("N2 存在 blocking 输入缺口（n2_diff rc=3），本轮未产出 n2_diff.json；"
                         f"缺口报告 = {gap}（不得当成『0 条差异』）"),
            )
            raise RuntimeError(
                "n2_diff rc=3：blocking 输入缺口，未产出 n2_diff.json（见 n2_diff.gap.json）"
            )
        if run["rc"] != 0:
            ctx.node_failed("N2", message=f"n2_diff rc={run['rc']}")
            raise RuntimeError(f"n2_diff rc={run['rc']}")

    doc = _load_json(target) or {}
    diffs = doc.get("diffs", []) if isinstance(doc, dict) else []
    pending = [d.get("entry_id") or d.get("id") for d in diffs if d.get("unresolved")]
    offsets = doc.get("offsets") if isinstance(doc, dict) else None
    result.update(
        {
            "has_change": doc.get("has_change"),
            "diff_count": len(diffs),
            "diff_ids": [d.get("entry_id") or d.get("id") for d in diffs][:20],
            "pending_entries": pending,
            # WS-L 的 G1 前置/派生也消费逐条 diffs（与 run_dir/n2_diff.json 同源，双读容错）
            "diffs": diffs,
            "self_check_ok": (doc.get("checks") or {}).get("self_check_ok"),
            # §10.4：三路统计原样取自 N2 产物（`routes` 是工具给出的逐路结论，不重算）。
            "routes": doc.get("routes") if isinstance(doc, dict) else None,
            "offsets": offsets if isinstance(offsets, list) else [],
            "unresolved_count": len(pending),
        }
    )
    kind_counts: dict[str, int] = {}
    for item in diffs:
        key = str(item.get("kind") or "unknown")
        kind_counts[key] = kind_counts.get(key, 0) + 1
    kinds_text = "、".join(f"{k} {v}" for k, v in sorted(kind_counts.items())) or "无"
    result["summary"] = (
        f"N2：差异 {len(diffs)} 条（{kinds_text}），未决 {len(pending)} 条，"
        f"offset {len(result['offsets'])} 条；has_change={doc.get('has_change')}，"
        f"self_check_ok={result['self_check_ok']}"
    )
    await data.async_set_state("n2_diff", result)
    ctx.node_finished("N2", detail=result, refs=[str(target)])
    return result
