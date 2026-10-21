"""N11 证据守护辅助（F06）：Host 侧身份四方同值核对。

模型只做成链判断；本模块只提供 Host 事实，不改变判定权。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..context import RunCtx

def _host_identity(ctx: RunCtx, data: Any) -> dict[str, Any]:
    """身份**四方同值**（Host 确定性）：run_id / case / 审的 md5 / 跑的 md5。

    - 审的 md5 = `n6_applied.md5_after`（N6 冻结值）
    - 跑的 md5 = `n9_result.cases[case].identity.case_md5`（run_guarded 身份头，经 host.evidence）
    - 证据件必须存在且可解析（present=true）
    """
    applied = (data.get_state("n6_applied") or {}).get("cases") or []
    n9 = data.get_state("n9_result") or {}
    per_case = n9.get("cases") if isinstance(n9.get("cases"), dict) else {}
    cases: list[dict[str, Any]] = []
    mismatches: list[str] = []
    reviewed_by_case = {str(c.get("case")): c for c in applied if c.get("case")}
    for case, item in per_case.items():
        item = item or {}
        reviewed = reviewed_by_case.get(str(case)) or {}
        identity = item.get("identity") or {}
        run_md5 = identity.get("case_md5")
        reviewed_md5 = reviewed.get("md5_after")
        evidence_path = item.get("path")
        evidence_ok = bool(item.get("present")) and bool(evidence_path) and Path(str(evidence_path)).is_file()
        same_run = identity.get("run_id") == ctx.run_id
        same_case = identity.get("case") == case
        same_md5 = bool(reviewed_md5) and run_md5 == reviewed_md5
        consistent = bool(evidence_ok and same_run and same_case and same_md5)
        if not evidence_ok:
            mismatches.append(f"{case}: 证据件缺失或不可解析（{evidence_path!r}）")
        if not same_run:
            mismatches.append(f"{case}: run_id 不一致（identity={identity.get('run_id')!r}）")
        if not same_case:
            mismatches.append(f"{case}: case 不一致（identity={identity.get('case')!r}）")
        if not same_md5:
            mismatches.append(f"{case}: 审的 md5({reviewed_md5}) != 跑的 md5({run_md5})")
        cases.append({
            "case": str(case), "reviewed_md5": reviewed_md5,
            "run_md5": run_md5, "run_id": identity.get("run_id"),
            "seed": identity.get("seed"), "evidence_path": evidence_path,
            "evidence_present": evidence_ok, "consistent": consistent,
        })
    missing = sorted(set(reviewed_by_case) - set(per_case))
    for case in missing:
        mismatches.append(f"{case}: N9 没有该用例的证据")
    return {
        "run_id": ctx.run_id,
        "consistent": bool(cases) and not mismatches,
        "mismatches": mismatches,
        "cases": cases,
        "missing_cases": missing,
        "checked": ["run_id", "case", "reviewed_md5(n6_applied.md5_after)",
                    "run_md5(host.evidence identity from run_guarded header)"],
    }
