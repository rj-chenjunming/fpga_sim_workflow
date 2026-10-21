"""N6 事实构造（F06）：文档位定义、API 语义、修订点与源码摘录。

只做 Host 侧**事实**构造，不做模型判定；`build_n6_targets` 是 N6 的唯一事实入口。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..context import RunCtx
from .host_steps import md5_file
from .model_common import read_json as _read_json

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


#: 从调用行里抽候选 callee 时忽略的语言关键字（其余候选再去源码里找定义）
_API_KEYWORDS = frozenset({
    "if", "else", "for", "foreach", "while", "do", "case", "begin", "end", "task",
    "function", "return", "new", "void", "int", "bit", "logic", "input", "output",
    "reg", "wire", "assign", "always", "initial", "repeat", "fork", "join", "wait",
    "posedge", "negedge", "this", "super",
})
_API_SEARCH_DIRS = ("TB", "TESTLIB")
_API_SEARCH_MAX_BYTES = 4 * 1024 * 1024  # 单文件上限，避免把超大生成件读进内存


def _call_candidates(window_text: str) -> list[str]:
    """从调用窗口抽 callee 名（`obj.method(` 与 `method(`），过滤关键字。"""
    names: list[str] = []
    for match in re.finditer(r"(?:\.|\b)([A-Za-z_]\w*)\s*\(", window_text):
        name = match.group(1)
        if name in _API_KEYWORDS:
            continue
        if name not in names:
            names.append(name)
    return names


def _extract_api_definition(text: str, callee: str) -> dict[str, Any] | None:
    """只读提取完整签名/函数体；不闭合的定义显式标记不完整。"""
    pattern = re.compile(r"\b(task|function)\b[^\n;]*?\b%s\s*\(" % re.escape(callee))
    match = pattern.search(text)
    if match is None:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    lines = text[start:].splitlines()
    sig_lines: list[str] = []
    depth = 0
    seen_paren = False
    sig_end = 0
    for idx, line in enumerate(lines):
        sig_lines.append(line)
        depth += line.count("(") - line.count(")")
        if "(" in line:
            seen_paren = True
        if seen_paren and depth <= 0 and ");" in line.replace(" ", ""):
            sig_end = idx
            break
        if seen_paren and depth <= 0 and line.strip().endswith(");"):
            sig_end = idx
            break
    signature = " ".join(x.strip() for x in sig_lines)
    body_lines: list[str] = []
    complete = False
    for line in lines[sig_end + 1:]:
        body_lines.append(line)
        if re.search(r"\bend(task|function)\b", line):
            complete = True
            break
    body = "\n".join(body_lines).strip()
    return {"signature": signature, "body": body, "complete": complete,
            "line": start_lines(text, match.start())}


def start_lines(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _find_api_definition(env_root: Path, case_text: str, callee: str,
                         cache: dict | None = None) -> dict[str, Any] | None:
    """先查本用例文件（本地 task/function），再查 ENV_ROOT/TB、TESTLIB 的定义。

    只做**只读文本扫描**，不执行任何环境脚本；找不到定义返回 None（由调用方标 not_found，
    不得让模型去猜参数语义）。
    """
    local = _extract_api_definition(case_text, callee)
    if local is not None:
        return {"callee": callee, "defined_in": "<case_file>", "source": "case_file",
                "signature": local["signature"], "body": local["body"], "complete": local["complete"]}
    if cache is None:
        cache = {}
    key = (str(env_root), callee)
    if key in cache:
        return cache[key]
    for dirname in _API_SEARCH_DIRS:
        root = env_root / dirname
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.sv")):
            try:
                if path.stat().st_size > _API_SEARCH_MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = _extract_api_definition(text, callee)
            if found is None:
                continue
            result = {
                "callee": callee,
                "defined_in": str(path.relative_to(env_root)),
                "source": f"scan:{dirname}",
                "signature": found["signature"],
                "body": found["body"],
                "complete": found["complete"],
            }
            cache[key] = result
            return result
    cache[key] = None
    return None


def _api_semantics_for(env_root: Path, source_text: str, line: int,
                       cache: dict | None = None) -> list[dict[str, Any]]:
    """取修订点附近调用的**测试台 API 语义**（signature + body），供 N6 判断实参角色。

    实测教训（2026-10-20 real 首跑）：`reg_field_test(addr, data_expmask, initial_dat, only_r)`
    的第 2 个数据参数是**期望掩码**、第 3 个是初始值；模型只看到调用行，把两者弄反，
    期望值改错（N7 只抓语法，抓不到）。把定义源码作为事实输入，模型才能按**参数名**定位。
    """
    if not source_text or line < 1:
        return []
    lines = source_text.splitlines()
    window = "\n".join(lines[max(0, line - 3):min(len(lines), line + 2)])
    semantics: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for callee in _call_candidates(window):
        found = _find_api_definition(env_root, source_text, callee, cache)
        if found is None:
            continue
        key = (found["callee"], found["signature"])
        if key in seen:
            continue
        seen.add(key)
        semantics.append(found)
    return semantics


#: RTL 截断/清零的常见写法：`{16'h0, wdata[15:0]}`（高半清零、低半保留）
_RTL_CONCAT_RE = re.compile(
    r"\{\s*(\d+)'([hb])([0-9a-fA-F_]+)\s*,\s*([A-Za-z_]\w*)\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*\}"
)


def _rtl_effect_hint(rtl_change: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从 RTL 新增行里抽**确定性的位截断事实**（readback mask / 保留位）。

    为什么由 Host 算而不是让模型推：实测 2026-10-20 real 第二轮，模型知道要改
    `data_expmask`，但把掩码应用到相反的一半（写 `0xffff_0000` / `0x1234_0000`）。
    `{16'h0, w[15:0]}` 的语义是确定的：保留 `[15:0]`、清 `[31:16]` ⇒ 期望值 = 写入值 &
    `0x0000ffff`。Host 把这条算术作为事实给模型，模型只负责选对实参与填值。
    """
    for change in rtl_change:
        hunk = str(change.get("hunk") or "")
        for line in hunk.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for match in _RTL_CONCAT_RE.finditer(line):
                const_bits = match.group(3).replace("_", "").strip()
                if const_bits.strip("0"):
                    continue  # 只处理"常量全 0"的截断（其余形态不当成确定事实）
                hi, lo = int(match.group(5)), int(match.group(6))
                if lo < 0 or hi < lo or hi > 31:
                    continue
                width = int(match.group(1))
                total = 32
                retained_mask = ((1 << (hi - lo + 1)) - 1) << lo
                cleared_mask = ((1 << total) - 1) ^ retained_mask
                cleared_hi = total - 1
                cleared_lo = hi + 1
                return {
                    "pattern": match.group(0).strip(),
                    "retained_bits": f"[{hi}:{lo}]",
                    "retained_mask": f"0x{retained_mask:08x}",
                    "cleared_bits": f"[{cleared_hi}:{cleared_lo}]" if cleared_lo <= cleared_hi else None,
                    "cleared_mask": f"0x{cleared_mask:08x}",
                    "rule": "期望读回值 = 写入值 & retained_mask；不得把掩码应用到相反的一半",
                    "zero_prefix_bits": width,
                    "source": change.get("file"),
                }
    return None


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
        source = repo_root / file_rel
        if not source.is_file():
            source = repo_root / "TESTLIB" / f"{case}.sv"
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
        api_semantics = _api_semantics_for(repo_root, text, line, api_cache)
        if any(not api.get("complete") for api in api_semantics):
            problems.append(f"{case}: API 定义上下文不完整")
            continue
        rtl_effect = _rtl_effect_hint(rtl_change)
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
