"""N10 分类与对账辅助（F06）：Host 抽数、FAIL 桶、待裁决落盘与 I3 证据字段。

**不持有模型判据**：分类结果由模型输出，Host 只做确定性校验/落盘（唯一写入者仍是
`kb/tools/n10_pending.py`）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from host import paths as P

from ..context import RunCtx
from .host_steps import run_kb_tool
from .model_common import read_json as _read_json, write_text as _write_text

#: N10 待裁决清单里需要人裁决的分类（分类 2/3）
PENDING_CLASSES = ("本轮引入", "待裁决")

def _diffs_for_classification(ctx: RunCtx) -> list[dict[str, Any]]:
    doc = _read_json(ctx.run_dir / "n2_diff.json") or {}
    return [d for d in (doc.get("diffs") or []) if isinstance(d, dict)]


def _per_case_fail_buckets(ctx: RunCtx, cases: dict[str, Any],
                           diffs: list[dict[str, Any]]) -> dict[str, Any]:
    """逐用例调用既有 Host 函数 `fail_buckets`（不复制解析器），并把桶 id 命名空间化。"""
    from host.evidence import fail_buckets

    buckets: list[dict[str, Any]] = []
    revision_points: list[dict[str, Any]] = []
    merged_notes: list[dict[str, Any]] = []
    for case, item in cases.items():
        path = Path(str((item or {}).get("path") or ""))
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        fb = fail_buckets(text, diffs)
        revision_points.extend(fb.get("revision_points") or [])
        for b in fb.get("buckets") or []:
            buckets.append({**b, "bucket_id": f"{case}:{b['bucket_id']}", "case": case})
        if fb.get("merged_note"):
            merged_notes.append({"case": case, **fb["merged_note"]})
    return {"buckets": buckets, "revision_points": revision_points,
            "merged_note": merged_notes or None}


def _reconcile_markdown(out: dict[str, Any]) -> str:
    counts = out.get("counts") or {}
    k1 = (counts.get("koutou1") or {}).get("value")
    k2 = (counts.get("koutou2") or {}).get("value")
    verdict = out.get("verdict") or {}
    lines = [
        "# N10 结果对账",
        "",
        f"- run_id：`{out.get('run_id')}`",
        f"- 目标用例：`{', '.join(out.get('target_cases') or [])}`",
        f"- 口径一（`*E` 文本行数）：**{k1}**",
        f"- 口径二（UVM Report Summary）：**{k2}**",
        f"- 判据：`{verdict.get('criterion')}` ⇒ **passed={verdict.get('passed')}**",
        f"- 身份四方同值：`{(out.get('identity') or {}).get('consistent')}`",
        "",
        "## 逐用例",
        "",
    ]
    for case, item in (out.get("cases") or {}).items():
        c = (item or {}).get("counts") or {}
        v = (item or {}).get("verdict") or {}
        lines.append(
            f"- `{case}`：口径一={(c.get('koutou1') or {}).get('value')} / "
            f"口径二={(c.get('koutou2') or {}).get('value')} ⇒ passed={v.get('passed')} "
            f"（{'; '.join(v.get('reasons') or []) or '无'}）"
        )
    lines += ["", "## FAIL 三分类", ""]
    classification = out.get("fail_classification") or {}
    cls_data = classification.get("data") if isinstance(classification.get("data"), dict) else {}
    for bucket in cls_data.get("items") or []:
        lines.append(f"- `{bucket.get('bucket_id')}` ⇒ {bucket.get('classification')}：{bucket.get('basis')}")
    if not (cls_data.get("items") or []):
        lines.append("(无分类输出)")
    lines += ["", "## 待裁决（分类 2/3）", ""]
    pending = out.get("pending_items") or []
    lines += [f"- `{p.get('bucket_id')}`：{p.get('classification')}" for p in pending] or ["(无)"]
    lines.append("")
    return "\n".join(lines)


def _persist_pending(ctx: RunCtx, items: list[dict[str, Any]]) -> dict[str, Any]:
    """把分类 2/3 落盘。**唯一写者**是 `kb/tools/n10_pending.py`（WS-K 提供）。

    工具未就绪时按 Lead 批准写 run-scoped 占位 `run_dir/n10_pending.json`，
    并在 state 里标注 `pending_written="run_scoped_placeholder"`（不冒充 workspace 权威）。
    """
    payload = {"run_id": ctx.run_id, "items": items, "count": len(items),
               "classes": PENDING_CLASSES}
    run_scoped = ctx.run_dir / "n10_pending.json"
    _write_text(run_scoped, json.dumps(payload, ensure_ascii=False, indent=2))
    tool = P.KB_TOOLS / "n10_pending.py"
    if not tool.is_file():
        return {"pending_path": str(run_scoped), "pending_written": "run_scoped_placeholder",
                "pending_count": len(items),
                "note": "kb/tools/n10_pending.py 未就绪 ⇒ 仅写 run-scoped 占位"}
    res = run_kb_tool("n10_pending.py", ["--run", ctx.run_id, "--items", str(run_scoped)])
    if res["rc"] != 0:
        ctx.node_failed("N10", message=f"n10_pending rc={res['rc']}")
        raise RuntimeError(
            f"N10：待裁决清单落盘失败 rc={res['rc']}: {res['stderr_tail'][-400:]}"
        )
    return {"pending_path": str(P.KB_CONFLICTS / "pending.json"),
            "pending_written": "kb/tools/n10_pending.py",
            "pending_count": len(items), "tool_stdout": res["stdout_tail"][-400:]}


def _case_pass_fields(ctx: RunCtx, case: str, item: dict[str, Any],
                      n7: dict[str, Any], n9: dict[str, Any], ledger_fn) -> dict[str, Any]:
    """组装 case_state `已验证通过` 的 I3 合取证据（缺一项就会被工具拒绝，本层不例外）。"""
    counts = (item or {}).get("counts") or {}
    imprints = (item or {}).get("imprints") or {}
    compile_rc = None
    for c in (n7.get("cases") or []):
        if str(c.get("case")) == case:
            compile_rc = c.get("rc")
            break
    static_check = None
    for c in ledger_fn(ctx).get("cases") or []:
        if str(c.get("case")) == case:
            static_check = c.get("static_check")
            break
    observed = None
    expected = None
    for marker, imp in imprints.items():
        if (imp or {}).get("consistent"):
            observed = ((imp.get("observed") or {}).get("id_count"))
            if isinstance(observed, int):
                expected = observed
                break
    run_md5 = ((n9.get("run_md5s") or {}).get(case)
               or ((item or {}).get("identity") or {}).get("case_md5"))
    return {
        "file": (item or {}).get("file"),
        "run_md5": run_md5,
        "compile_rc": compile_rc,
        "static_check": static_check,
        "script_egrep": ((counts.get("koutou1") or {}).get("value")),
        "uvm_error": (((counts.get("koutou2") or {}).get("value") or {}).get("UVM_ERROR")),
        # 判据 passed 已由 host.evidence 的 I3 合取（含"出现 UVM Report Summary"）判定；
        # per_case 显式带 has_report_summary 时优先，否则以 verdict.passed 为证（仅写通过态时才用）。
        "uvm_summary_present": bool(
            (item or {}).get("has_report_summary")
            if "has_report_summary" in (item or {})
            else (counts.get("koutou2") or {}).get("uvm_summary_present")
            if (counts.get("koutou2") or {}).get("uvm_summary_present") is not None
            else ((item or {}).get("verdict") or {}).get("passed") is True
        ),
        "obs_expected": expected,
        "obs_observed": observed,
        "evidence": (item or {}).get("path"),
        "note": "N10：卡点B rc=0 ∧ 卡点C pass ∧ 双口径皆 0 ∧ UVM 汇总 ∧ 印记一致",
        "updated_by": "loop:N10",
    }
