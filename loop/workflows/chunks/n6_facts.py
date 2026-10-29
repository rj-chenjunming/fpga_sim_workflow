"""N6 事实构造（F06）：文档位定义、API 语义、修订点与源码摘录。

只做 Host 侧**事实**构造，不做模型判定；`build_n6_targets` 是 N6 的唯一事实入口。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..context import RunCtx
from .host_steps import md5_file
from .model_common import read_json as _read_json
from host.environment_sv import _api_semantics_for, _rtl_effect_hint  # 兼容导出

def _doc_bitdef_from_diff(diff: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(diff, dict):
        return None
    raw = diff.get("after")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
    elif isinstance(raw, dict):
        parsed = raw
    else:
        return None
    if not isinstance(parsed, dict):
        return None
    keep = ("name", "segment", "offset_global", "reset", "rw", "bytes",
            "bitdef_present", "entry_id")
    out = {k: parsed.get(k) for k in keep if parsed.get(k) is not None}
    return out or None


def _doc_bitdef_from_snapshot(ctx: RunCtx, entry_id: str) -> dict[str, Any] | None:
    """从**本轮文档条目快照**取位定义（`bundle/doc_entries.jsonl`）。

    为什么必须有这条：`_doc_bitdef_from_diff` 只在「N2 的差异条目本身是 doc_entry」时
    才有 `after` JSON。真实 RTL-only 改动（本仓最常见）里，N2 的差异条目是 **RTL 文件**，
    `diffs_by_id` 里没有 `0x0d00#0x0d04`，于是 N6 会把「拿不到文档位定义」当失败
    —— 实测 2026-10-20 real 首跑就死在这里（N5 已正确给出 5 个必须用例）。
    文档条目快照是 N1 冻结进本轮 bundle 的权威输入（与 baseline doc_fingerprint 同源）。
    """
    if not entry_id:
        return None
    snapshot = ctx.run_dir / "bundle" / "doc_entries.jsonl"
    if not snapshot.is_file():
        return None
    keep = ("name", "segment", "offset_global", "reset", "rw", "bytes",
            "bitdef_present", "entry_id")
    for line in snapshot.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict) or str(rec.get("entry_id")) != str(entry_id):
            continue
        out = {k: rec.get(k) for k in keep if rec.get(k) is not None}
        if not out:
            return None
        out["source"] = f"run_snapshot:{snapshot.relative_to(ctx.run_dir)}"
        return out
    return None


def _doc_bitdef_for(ctx: RunCtx, entry_id: str, diff: dict[str, Any] | None) -> dict[str, Any] | None:
    """位定义取数：diff 里的 doc_entry（drill/文档变更）优先，其次本轮文档条目快照。"""
    return _doc_bitdef_from_diff(diff) or _doc_bitdef_from_snapshot(ctx, entry_id)


def _excerpt(text: str, line: int, *, radius: int = 15) -> dict[str, Any]:
    lines = text.splitlines()
    if line < 1 or line > len(lines):
        raise ValueError(f"目标行号 {line} 超出文件行数 {len(lines)}")
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    body = "\n".join(f"{n:>6}: {lines[n - 1]}" for n in range(start, end + 1))
    return {"start": start, "end": end, "line": line, "text": body}


def build_n6_targets(ctx: RunCtx, data: Any) -> list[dict[str, Any]]:
    """Host 签发 N6 的**有界任务事实**：目标用例 + 源码摘录 + 修订点 + 文档位定义。

    拿不到（源文件缺失 / 无修订点 / 无文档位定义）⇒ **显式失败**（real），
    不给空值让模型去编（审计 C11/I14 的教训）。
    """
    n5_doc = _read_json(ctx.run_dir / "n5_impact.json") or {}
    n2_doc = _read_json(ctx.run_dir / "n2_diff.json") or {}
    must_change = [m for m in (n5_doc.get("must_change") or []) if isinstance(m, dict)]
    diffs = [d for d in (n2_doc.get("diffs") or []) if isinstance(d, dict)]
    diffs_by_id = {str(d.get("entry_id") or d.get("id") or ""): d for d in diffs}
    repo_root = Path(data.require_resource("repo_root"))
    lenient = ctx.mode == "drill"

    targets: list[dict[str, Any]] = []
    problems: list[str] = []
    api_cache: dict[tuple[str, str], dict[str, Any] | None] = {}
    for item in must_change:
        case = str(item.get("case") or "")
        if not case:
            continue
        file_rel = str(item.get("file") or f"TESTLIB/{case}.sv")
        source = ctx.environment.author_case_path(repo_root, file_rel, case)
        if not source.is_file():
            problems.append(f"{case}: 源用例不存在（{file_rel}）")
            continue
        text = source.read_text(encoding="utf-8", errors="strict")
        line = int(item.get("line") or 0)
        try:
            excerpt = _excerpt(text, line)
        except ValueError as exc:
            problems.append(f"{case}: {exc}")
            continue
        entry_id = str(item.get("entry_id") or "")
        diff = diffs_by_id.get(entry_id)
        doc_bitdef = _doc_bitdef_for(ctx, entry_id, diff)
        segment = str(item.get("segment") or "")
        offset = str(item.get("offset") or "")
        if not doc_bitdef:
            problems.append(f"{case}: 拿不到文档位定义（entry_id={entry_id!r}）")
            continue
        if not (segment and offset):
            problems.append(f"{case}: 缺修订点（segment/offset）")
            continue
        display = f"{segment}+{offset}" if "+" not in offset else offset
        rtl_files = [str(x) for x in (item.get("rtl_files") or [])]
        rtl_change: list[dict[str, Any]] = []
        for d in diffs:
            did = str(d.get("entry_id") or d.get("id") or "")
            if did in rtl_files and str(d.get("kind") or "") == "rtl_file":
                rtl_change.append({
                    "file": did,
                    "lines": d.get("lines") or [],
                    "offsets": d.get("offsets") or [],
                    "hunk": d.get("diff_hunk"),
                })
        if not rtl_change:  # N5 未给 rtl_files 时：按 offset 命中取 RTL hunk
            for d in diffs:
                if not d.get("diff_hunk"):
                    continue
                if offset and offset in [str(o) for o in (d.get("offsets") or [])]:
                    rtl_change.append({
                        "file": str(d.get("entry_id") or d.get("id") or ""),
                        "lines": d.get("lines") or [],
                        "offsets": d.get("offsets") or [],
                        "hunk": d.get("diff_hunk"),
                    })
        api_semantics = ctx.environment.api_semantics(repo_root, text, line, api_cache)
        if any(not api.get("complete") for api in api_semantics):
            problems.append(f"{case}: API 定义上下文不完整")
            continue
        rtl_effect = ctx.environment.rtl_effect(rtl_change)
        point = {
            "entry_id": entry_id or None,
            "segment": segment,
            "offset": offset,
            "display": display,
            "doc_bitdef": doc_bitdef,
            "rtl_change": rtl_change,
            "api_semantics": api_semantics,
            "rtl_effect": rtl_effect,
        }
        existing = next((t for t in targets if t["case"] == case), None)
        if existing is not None:
            # 同一用例可能命中多个 offset（N5 逐条给）：合并修订点，别重复要求 revision
            existing["revision_points"].append(point)
            existing["excerpts"].append(excerpt)
            known = {(a.get("callee"), a.get("signature")) for a in existing.get("api_semantics") or []}
            for api in api_semantics:
                if (api.get("callee"), api.get("signature")) not in known:
                    existing.setdefault("api_semantics", []).append(api)
            continue
        targets.append({
            "case": case,
            "file": file_rel,
            "md5": md5_file(source),
            "excerpt": excerpt,
            "excerpts": [excerpt],
            "revision_points": [point],
            "doc_bitdef": doc_bitdef,
            "rtl_change": rtl_change,
            "api_semantics": list(api_semantics),
            "rtl_effect": rtl_effect,
            "why": str(item.get("why") or ""),
        })
    if problems and not lenient:
        ctx.node_failed("N6", message="N6 目标事实不完整：" + "；".join(problems[:5]))
        raise RuntimeError("N6：目标事实不完整（不允许让模型去编）：" + "；".join(problems[:8]))
    return targets
