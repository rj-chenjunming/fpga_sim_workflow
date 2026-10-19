"""模型语义节点：N3 / N6 / N8 / N10 / N11 / N12。

**真 ModelRequest**（经 `host.model_provider` 接入宿主已声明的 provider）。
分工严格遵循技能 `agently-request`：

- 模型只做**语义判断**：分组、修订 edits、复核意见、FAIL 三分类、证据链结论、叙述；
- **Host 拥有确定性校验**：schema/类型、offered-key 成员性、算术、数字一致性、身份四方同值、
  副作用（写沙箱/写产物/写用例态台账）。

本轮修复要点（审计 2026-10-19 §3）：
- **#1 N8 fail-closed（C3/B1）**：`validation.ok=False` / verdict 缺失 ⇒ `node_failed`，
  不得默认 `pass`。
- **#3 N6 结构化 edits（A6）**：模型只出 `{revisions:[{case, edits:[{line,old,new,basis}],
  rationale}], notes}`；Host 校验后由 `n6_apply` 施加（写沙箱/冻结 md5/记账）。
- **#15 N11 guardian（A10）**：业务 N11 = 证据守护（成链/不成链）；Host 做身份四方同值，
  不成链 ⇒ 显式 `N11_REWORK`（回边 N6）。
- **#18 N3/N10/N12 持久化与消费者（I8/A9/A20）**：N3 写 `n3_digest.md`、N10 写
  `n10_reconcile.md` + 待裁决清单（唯一写者 `kb/tools/n10_pending.py`）、N12 写
  `n12_report.md` 且 Host 校验 refs 可解析；解析/校验失败显式终止。
- **#11 I2 用例态（A3）**：N6（已修订待验）/ N8（已退回·static_check）/ N10（已验证通过，
  走 `kb/tools/case_state.py` 的 I3 合取门槛，模型/本层不能自封）。
- **#22 I7（C5/C6）**：N6 不再自增返工计数；只有 N8 判 rework 才 +1，统一 `>= limit`，
  超限发 `N8_ESCALATE`（拓扑改指 N13/gate2），首轮修订不消耗预算；cycles 只读台账。
- **C10**：N10 分类校验失败 ⇒ node_failed 阻断 gate2；**A21**：N3 解析失败 ⇒ 终止本轮。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from host import model_provider as MP
from host import paths as P

from ..context import RunCtx, ctx_of
from .host_steps import md5_file, run_kb_tool

PROMPTS_FILE = Path(__file__).resolve().parents[2] / "prompts" / "loop_nodes.yaml"

#: Host 侧确定性校验的输出种类（= prompt_key 的前缀）
_KNOWN_KINDS = frozenset({"n3", "n6", "n8", "n10", "n11", "n12"})

#: I7 缺省上限（权威仍在 case_state 台账；这里只是缺省值，不新增漂移常量）
DEFAULT_REWORK_LIMIT = 3

#: N10 待裁决清单里需要人裁决的分类（分类 2/3）
PENDING_CLASSES = ("本轮引入", "待裁决")


def load_prompts() -> dict[str, Any]:
    doc = yaml.safe_load(PROMPTS_FILE.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _family_reason() -> str:
    cfg = MP.resolve()
    return cfg.reason or "provider 不可用"


# ---------------------------------------------------------------- 小工具


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _artifact(ctx: RunCtx, name: str) -> Path:
    return ctx.run_dir / name


# ---------------------------------------------------------------- 用例态台账（I2）


def _case_state_path(ctx: RunCtx) -> Path:
    return ctx.run_dir / "case_states.json"


def _case_state_args(ctx: RunCtx) -> list[str]:
    return ["--state-file", str(_case_state_path(ctx))]


def _ensure_case_state(ctx: RunCtx) -> None:
    """建立**本轮**台账：文件缺失才 init；存在但 run_id 不符 ⇒ fail closed。

    台账是 per-run 状态（`case_states.json.run_id` 必须等于本 run）；Lead 已从
    `context.DRILL_FILES` 移除 `case_states.json`，所以身份错位是**真缺陷**，
    不得用 `--force` 覆盖（那会把上一轮/别人的台账当成本轮历史抹掉）。
    """
    path = _case_state_path(ctx)
    if path.is_file():
        existing = _read_json(path)
        if not isinstance(existing, dict):
            ctx.node_failed("N6", message=f"用例态台账不可解析：{path}")
            raise RuntimeError(f"case_state：台账不是合法 JSON：{path}")
        if existing.get("run_id") != ctx.run_id:
            ctx.node_failed(
                "N6",
                message=(f"用例态台账身份错位：run_id={existing.get('run_id')!r} "
                         f"!= {ctx.run_id!r}（per-run 文件不得复用）"),
            )
            raise RuntimeError(
                f"case_state：已有台账 run_id={existing.get('run_id')!r} 与 --run={ctx.run_id!r} "
                "不一致（身份错位）⇒ fail closed"
            )
        return
    res = run_kb_tool("case_state.py", ["init", "--run", ctx.run_id, *_case_state_args(ctx)])
    if res["rc"] not in (0, 3):  # 3 = 已存在（合法）
        raise RuntimeError(f"case_state.py init rc={res['rc']}: {res['stderr_tail'][-400:]}")


def _set_case_state(ctx: RunCtx, case: str, state: str, *, rework_cycles: int | None = None,
                    **fields: Any) -> dict[str, Any]:
    """经 `kb/tools/case_state.py set` 写台账（I2 的唯一写者；本层不直接改 JSON）。"""
    args = ["set", "--run", ctx.run_id, *_case_state_args(ctx), "--case", case, "--state", state]
    mapping = {
        "file": "--file",
        "md5_before": "--md5-before",
        "md5_after": "--md5-after",
        "sandbox_path": "--sandbox-path",
        "compile_rc": "--compile-rc",
        "static_check": "--static-check",
        "run_md5": "--run-md5",
        "script_egrep": "--script-egrep",
        "uvm_error": "--uvm-error",
        "obs_expected": "--obs-expected",
        "obs_observed": "--obs-observed",
        "evidence": "--evidence",
        "note": "--note",
        "updated_by": "--updated-by",
    }
    for key, value in fields.items():
        if value is None:
            continue
        if key == "uvm_summary_present":
            if value:
                args.append("--uvm-summary-present")
            continue
        flag = mapping.get(key)
        if flag is None:
            raise KeyError(f"未知的 case_state 字段：{key}")
        if isinstance(value, bool):
            args += [flag, str(value).lower()]
        else:
            args += [flag, str(value)]
    if fields.get("uvm_summary_present") is True:
        args.append("--uvm-summary-present")
    if rework_cycles is not None:
        args += ["--rework-cycles", str(rework_cycles)]
    return run_kb_tool("case_state.py", args)


def ledger(ctx: RunCtx) -> dict[str, Any]:
    """只读用例态台账（cycles 的**唯一**账本；缺失 = 还没写过，按 0/缺省）。"""
    doc = _read_json(_case_state_path(ctx)) or {}
    return {
        "path": str(_case_state_path(ctx)),
        "cases": doc.get("cases") or [],
        "rework_cycles": doc.get("rework_cycles") or {},
        "present": bool(doc),
        "by_case": {str(c.get("case")): c for c in (doc.get("cases") or []) if c.get("case")},
    }


def _cycles_and_limit(ctx: RunCtx, data: Any) -> tuple[int, int]:
    """返工计数只读台账（**不再**从 N6 自增的执行状态取，避免双账本）。"""
    led = ledger(ctx)
    rc = led.get("rework_cycles") or {}
    cycles = int(rc.get("n6_n8_cycles") or 0)
    limit = int(
        data.get_state("rework_limit")
        or rc.get("limit")
        or DEFAULT_REWORK_LIMIT
    )
    return cycles, max(limit, 1)


# ---------------------------------------------------------------- 降级替身


def _standin(ctx: RunCtx, node: str, artifact: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """确定性替身。**drill 才允许读夹具**；real 模式的 standin 只输出显式空/待补。"""
    use_fixture = ctx.mode == "drill"
    text = ctx.read_fixture_text(artifact) if use_fixture else None
    out: dict[str, Any] = {
        "standin": True,
        "provider": "none",
        "reason": f"未接入模型（{_family_reason()}）；本节点输出为确定性替身，非模型结论。",
        "node": node,
        "source": artifact if use_fixture else None,
        "artifact_present": text is not None,
        "fixture_used": use_fixture,
    }
    if text is not None:
        out["excerpt"] = text[:1200]
        out["bytes"] = len(text.encode("utf-8"))
    else:
        out["excerpt"] = ""
        out["note"] = "real 模式的 standin 不读 drill 夹具（禁止用夹具结论冒充本轮输出）。"
    if extra:
        out.update(extra)
    return out


# ---------------------------------------------------------------- 真请求


def _render_block(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value)


async def _ask(
    ctx: RunCtx,
    node: str,
    *,
    prompt_key: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """发一次真 ModelRequest。失败**不吞**：回报错误并交由调用方决定。"""
    from agently import Agently

    from prompts.node_schemas import SCHEMAS

    cfg = MP.configure_agently()
    kind = prompt_key.split("_", 1)[0]
    schema = SCHEMAS.get(kind)
    if schema is None:
        raise KeyError(f"没有 {prompt_key!r} 的输出契约（prompts/node_schemas.py）")
    spec = load_prompts().get(prompt_key) or {}
    info = _render_block(spec.get("info") or {})
    instruct = _render_block(spec.get("instruct") or [])

    agent = Agently.create_agent()
    try:
        data = await (
            agent.input(input_data)
            .info(info)
            .instruct(instruct)
            .output(schema, format="json")
            .async_get_data()
        )
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        elif isinstance(data, dict) and hasattr((data or {}).get("$result"), "model_dump"):
            data = data["$result"].model_dump()
    except Exception as exc:  # noqa: BLE001 - 原样回报给调用方，不伪造输出
        ctx.event(
            "warning", node=node, status="model_failed",
            detail={"prompt": prompt_key, "model": cfg.model, "error": f"{type(exc).__name__}: {exc}"},
        )
        return {
            "standin": False,
            "provider": cfg.model,
            "model_call_failed": True,
            "error": f"{type(exc).__name__}: {exc}",
        }

    ctx.event(
        "node_finished", node=f"{node}_model", status="ok",
        detail={"prompt": prompt_key, "model": cfg.model, "plugin": cfg.plugin},
    )
    return {"standin": False, "provider": cfg.model, "plugin": cfg.plugin, "data": data}


# ---------------------------------------------------------------- Host 侧校验


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _check_membership(label: str, offered: set[str], claimed: list[Any], problems: list[str]) -> set[str]:
    unknown = [str(c) for c in claimed if str(c) not in offered]
    if unknown:
        problems.append(f"{label} 出现未提供给模型的标识：{sorted(set(unknown))[:8]}")
    return {str(c) for c in claimed if str(c) in offered}


def _validate(kind: str, payload: dict[str, Any], *, offered: dict[str, Any]) -> dict[str, Any]:
    """Host 的确定性校验。返回 `{ok, problems, accepted}`。

    `kind` 由 `prompt_key` 前缀派生（`n12_report` → `n12`）。
    **未知 kind 必须显式报错**（历史上曾因归一化失配导致五个节点"没检查"看起来像"没问题"）。
    """
    problems: list[str] = []
    data = payload.get("data")
    accepted: dict[str, Any] = {}

    if payload.get("model_call_failed"):
        return {"ok": False, "problems": [payload.get("error", "模型调用失败")], "accepted": {}}
    if payload.get("standin"):
        return {"ok": True, "problems": [], "accepted": {}, "standin": True}
    if kind not in _KNOWN_KINDS:
        return {
            "ok": False,
            "problems": [f"未知校验 kind {kind!r}；已知 {sorted(_KNOWN_KINDS)}（校验未实现 = 不得判通过）"],
            "accepted": {},
        }
    if not isinstance(data, dict):
        return {"ok": False, "problems": [f"输出不是对象：{type(data).__name__}"], "accepted": {}}

    if kind == "n3":
        accepted["summary"] = str(data.get("summary") or "").strip()
        if not accepted["summary"]:
            problems.append("summary 为空")
        groups = _as_list(data.get("groups"))
        ok_groups = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            ids = _check_membership("groups.diff_ids", offered.get("diff_ids", set()),
                                    _as_list(g.get("diff_ids")), problems)
            seg = str(g.get("segment") or "")
            if offered.get("segments") and seg not in offered["segments"]:
                problems.append(f"groups.segment 未在 offered_segments 中：{seg!r}")
            ok_groups.append({"segment": seg, "kind": str(g.get("kind") or ""),
                              "diff_ids": sorted(ids), "why": str(g.get("why") or "")})
        accepted["groups"] = ok_groups
        accepted["risky_points"] = [str(x) for x in _as_list(data.get("risky_points"))]

    elif kind == "n6":
        offered_cases: set[str] = set(offered.get("cases") or ())
        revisions = [r for r in _as_list(data.get("revisions")) if isinstance(r, dict)]
        ok_revisions: list[dict[str, Any]] = []
        seen: list[str] = []
        for rev in revisions:
            case = str(rev.get("case") or "")
            if offered_cases and case not in offered_cases:
                problems.append(f"revisions.case 不在目标用例中：{case!r}")
                continue
            if case in seen:
                problems.append(f"revisions.case 重复：{case!r}（每个目标用例恰好一条）")
                continue
            seen.append(case)
            edits = [e for e in _as_list(rev.get("edits")) if isinstance(e, dict)]
            if not edits:
                problems.append(f"{case}: edits 为空（至少一条）")
                continue
            ok_edits: list[dict[str, Any]] = []
            for i, edit in enumerate(edits):
                try:
                    line = int(edit.get("line"))
                except (TypeError, ValueError):
                    problems.append(f"{case}: edits[{i}].line 不是整数")
                    continue
                old = str(edit.get("old") or "")
                new = str(edit.get("new") or "")
                basis = str(edit.get("basis") or "").strip()
                if not old:
                    problems.append(f"{case}: edits[{i}].old 为空")
                if not new:
                    problems.append(f"{case}: edits[{i}].new 为空")
                if old == new:
                    problems.append(f"{case}: edits[{i}] old==new（空改动）")
                if not basis:
                    problems.append(f"{case}: edits[{i}] 缺 basis")
                if line < 1:
                    problems.append(f"{case}: edits[{i}].line 必须 >=1")
                ok_edits.append({"line": line, "old": old, "new": new, "basis": basis})
            ok_revisions.append({"case": case, "edits": ok_edits,
                                 "rationale": str(rev.get("rationale") or "")})
        accepted["revisions"] = ok_revisions
        accepted["rework_resolution"] = [str(x) for x in _as_list(data.get("rework_resolution"))]
        accepted["notes"] = [str(x) for x in _as_list(data.get("notes"))]
        missing = sorted(offered_cases - set(seen))
        if missing:
            problems.append(f"缺少目标用例的 revision：{missing}")
        if not ok_revisions:
            problems.append("revisions 为空或全部被拒（必须覆盖全部目标用例）")

    elif kind == "n8":
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in ("pass", "rework"):
            problems.append(f"verdict 非法或缺失：{verdict!r}（只允许 pass/rework；缺失不得默认 pass）")
        findings = [f for f in _as_list(data.get("findings")) if isinstance(f, dict)]
        must_fix = [str(x) for x in _as_list(data.get("must_fix"))]
        basisless = [f for f in findings
                     if str(f.get("result", "")).lower() in ("fail", "不通过")
                     and not str(f.get("basis") or "").strip()]
        if basisless:
            problems.append(f"{len(basisless)} 条 fail 结论缺少 basis（空泛意见视为无效）")
        if verdict == "rework" and not must_fix:
            problems.append("verdict=rework 但 must_fix 为空（退回必须给必须修复项）")
        accepted.update({"verdict": verdict, "findings": findings, "must_fix": must_fix})

    elif kind == "n10":
        buckets = offered.get("buckets") or []
        by_id = {str(b["bucket_id"]): b for b in buckets}
        items = [i for i in _as_list(data.get("items")) if isinstance(i, dict)]
        seen: list[str] = []
        conflicts: list[dict[str, Any]] = []
        accepted_items: list[dict[str, Any]] = []
        allowed = ("既有缺陷", "本轮引入", "待裁决")
        for item in items:
            bid = str(item.get("bucket_id") or "")
            if bid not in by_id:
                problems.append(f"items.bucket_id 不在提供的桶里：{bid!r}")
                continue
            if bid in seen:
                problems.append(f"bucket_id 重复出现：{bid!r}（每个桶恰好一条）")
                continue
            seen.append(bid)
            cls = str(item.get("classification") or "")
            basis = str(item.get("basis") or "").strip()
            if cls not in allowed:
                problems.append(f"{bid} 的 classification 非法：{cls!r}（允许 {allowed}）")
            if not basis:
                problems.append(f"{bid} 缺 basis（空泛分类视为无效）")
            if cls == "本轮引入" and not by_id[bid].get("overlaps_revision_point"):
                conflicts.append({"bucket_id": bid, "claimed": cls,
                                  "host_fact": "该桶无地址落在 input.revision_points 上",
                                  "sample_addresses": by_id[bid].get("sample_addresses", [])})
            accepted_items.append({"bucket_id": bid, "classification": cls, "basis": basis,
                                   "entry_count": by_id[bid].get("entry_count"),
                                   "address_count": by_id[bid].get("address_count"),
                                   "overlaps_revision_point": by_id[bid].get("overlaps_revision_point")})
        missing = [b for b in by_id if b not in seen]
        if missing:
            problems.append(f"有 {len(missing)} 个桶未被分类：{missing[:6]}")
        if conflicts:
            problems.append(
                f"{len(conflicts)} 个桶被判「本轮引入」但 Host 事实显示不落在任何修订点上（不得采信）")
        tally: dict[str, int] = {}
        for it in accepted_items:
            tally[it["classification"]] = tally.get(it["classification"], 0) + int(it["entry_count"] or 0)
        accepted.update({
            "items": accepted_items,
            "summary": str(data.get("summary") or ""),
            "unclassified": [str(x) for x in _as_list(data.get("unclassified"))],
            "conflicts": conflicts,
            "entries_by_classification": tally,
            "buckets_expected": len(by_id),
            "buckets_classified": len(seen),
        })

    elif kind == "n11":
        chain = str(data.get("chain") or "").strip().lower()
        if chain not in ("intact", "broken"):
            problems.append(f"chain 非法或缺失：{chain!r}（只允许 intact/broken）")
        rework_requests = [r for r in _as_list(data.get("rework_requests")) if isinstance(r, dict)]
        if chain == "broken" and not rework_requests:
            problems.append("chain=broken 但没有 rework_requests（不成链必须给出返工请求）")
        if chain == "intact" and rework_requests:
            problems.append("chain=intact 却给了 rework_requests（自相矛盾）")
        accepted.update({
            "chain": chain,
            "reasons": [str(x) for x in _as_list(data.get("reasons"))],
            "rework_requests": rework_requests,
            "caveats": [str(x) for x in _as_list(data.get("caveats"))],
        })

    elif kind == "n12":
        quoted = data.get("counts_quoted")
        quoted = quoted if isinstance(quoted, dict) else {}
        auth = offered.get("counts") or {}
        mismatches: list[str] = []
        for key in ("koutou1", "koutou2"):
            expected = (auth.get(key) or {}).get("value")
            got = quoted.get(key)
            if isinstance(got, dict) and "value" in got:
                got = got["value"]
            if expected is not None and got is not None and got != expected:
                mismatches.append(f"{key}: 报告={got!r} 权威={expected!r}")
        if mismatches:
            problems.append("报告引用的数字与 Host 权威值不一致：" + "; ".join(mismatches))
        verdict = offered.get("verdict") or {}
        passed = verdict.get("passed")
        expected_claim = ("passed" if passed is True
                          else "not_passed" if passed is False else "undetermined")
        claimed = str(data.get("claimed_verdict") or "").strip()
        if claimed not in ("passed", "not_passed", "undetermined"):
            problems.append(f"claimed_verdict 非法或缺失：{claimed!r}")
        elif claimed != expected_claim:
            problems.append(
                f"claimed_verdict={claimed!r} 与 Host 权威判决 {expected_claim!r} 不一致")
        accepted.update({
            "title": str(data.get("title") or ""),
            "sections": [s for s in _as_list(data.get("sections")) if isinstance(s, dict)],
            "counts_quoted": quoted,
            "authoritative_counts": {k: (auth.get(k) or {}).get("value")
                                     for k in ("koutou1", "koutou2")},
            "counts_match_authority": not mismatches,
            "claimed_verdict": claimed,
            "expected_claimed_verdict": expected_claim,
            "open_items": [str(x) for x in _as_list(data.get("open_items"))],
        })

    return {"ok": not problems, "problems": problems, "accepted": accepted}


async def run_model_node(
    ctx: RunCtx,
    node: str,
    *,
    prompt_key: str,
    input_data: dict[str, Any],
    offered: dict[str, Any],
) -> dict[str, Any]:
    """发请求 + Host 校验，返回统一形状。"""
    cfg = MP.resolve()
    if not cfg.available:
        return {"mode": "standin", "standin": True, "provider": "none", "reason": cfg.reason}

    payload = await _ask(ctx, node, prompt_key=prompt_key, input_data=input_data)
    kind = prompt_key.split("_", 1)[0]
    validation = _validate(kind, payload, offered=offered)
    out = {
        "mode": "live" if not payload.get("standin") else "standin",
        "standin": bool(payload.get("standin")),
        "provider": payload.get("provider"),
        "plugin": payload.get("plugin"),
        "model_call_failed": bool(payload.get("model_call_failed")),
        "error": payload.get("error"),
        "validation": validation,
        "data": validation.get("accepted") or payload.get("data"),
        "input_digest": {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in input_data.items()},
    }
    ctx.event(
        "node_finished", node=f"{node}_request",
        status="ok" if validation["ok"] else "validation_failed",
        detail={"model": out["provider"], "mode": out["mode"],
                "problems": validation["problems"][:5]},
    )
    return out


# ---------------------------------------------------------------- N6 目标构造


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
        doc_bitdef = _doc_bitdef_from_diff(diff)
        segment = str(item.get("segment") or "")
        offset = str(item.get("offset") or "")
        if not doc_bitdef:
            problems.append(f"{case}: 拿不到文档位定义（entry_id={entry_id!r}）")
            continue
        if not (segment and offset):
            problems.append(f"{case}: 缺修订点（segment/offset）")
            continue
        display = f"{segment}+{offset}" if "+" not in offset else offset
        point = {
            "entry_id": entry_id or None,
            "segment": segment,
            "offset": offset,
            "display": display,
            "doc_bitdef": doc_bitdef,
        }
        existing = next((t for t in targets if t["case"] == case), None)
        if existing is not None:
            # 同一用例可能命中多个 offset（N5 逐条给）：合并修订点，别重复要求 revision
            existing["revision_points"].append(point)
            continue
        targets.append({
            "case": case,
            "file": file_rel,
            "md5": md5_file(source),
            "excerpt": excerpt,
            "revision_points": [point],
            "doc_bitdef": doc_bitdef,
            "why": str(item.get("why") or ""),
        })
    if problems and not lenient:
        ctx.node_failed("N6", message="N6 目标事实不完整：" + "；".join(problems[:5]))
        raise RuntimeError("N6：目标事实不完整（不允许让模型去编）：" + "；".join(problems[:8]))
    return targets


# ---------------------------------------------------------------- N3


def _compose_n3_markdown(out: dict[str, Any]) -> str:
    data = out.get("data") if isinstance(out.get("data"), dict) else {}
    lines = [
        "# N3 差异语义摘要",
        "",
        f"- 模型模式：`{out.get('mode')}`；provider：`{out.get('provider')}`",
        f"- 校验：`{(out.get('validation') or {}).get('ok')}`",
        "",
        "## 摘要",
        "",
        str(data.get("summary") or "(缺失)"),
        "",
        "## 分组",
        "",
    ]
    groups = data.get("groups") or []
    if not groups:
        lines.append("(无分组输出)")
    for g in groups:
        lines.append(
            f"- **{g.get('segment')} / {g.get('kind')}**：{', '.join(g.get('diff_ids') or [])}"
            f" —— {g.get('why')}"
        )
    lines += ["", "## 需人工重点确认", ""]
    risky = data.get("risky_points") or []
    lines += [f"- {r}" for r in risky] or ["(无)"]
    lines += ["", "## 元数据", "",
              f"- input_digest：`{json.dumps(out.get('input_digest') or {}, ensure_ascii=False)}`",
              ""]
    return "\n".join(lines)


async def n3_digest(data: Any) -> dict[str, Any]:
    """N3 差异摘要（模型节点）→ 落盘 `run_dir/n3_digest.md`。

    **A21**：模型调用/解析失败必须显式终止本轮，不得只记 problems 继续（空摘要不得进 Gate1）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N3")
    n2 = data.get_state("n2_diff") or {}
    diff_path = ctx.run_dir / "n2_diff.json"
    diffs: list[dict[str, Any]] = []
    try:
        diffs = (json.loads(diff_path.read_text(encoding="utf-8")).get("diffs") or [])[:40]
    except Exception:  # noqa: BLE001
        diffs = []

    input_data = {
        "run_id": ctx.run_id,
        "diffs": [
            {"entry_id": d.get("entry_id") or d.get("id"), "segment": d.get("segment"),
             "offset": d.get("offset"), "kind": d.get("kind"),
             "before": str(d.get("before"))[:200], "after": str(d.get("after"))[:200]}
            for d in diffs
        ],
        "offered_segments": sorted({str(d.get("segment")) for d in diffs if d.get("segment")}),
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
    ctx.node_finished("N3", status="ok" if out["mode"] in ("live", "standin") else "failed",
                      detail={"mode": out["mode"], "provider": out.get("provider"),
                              "problems": (out.get("validation") or {}).get("problems", [])[:3]},
                      refs=[str(digest_path)])
    return out


# ---------------------------------------------------------------- N6


async def n6_author(data: Any) -> dict[str, Any]:
    """N6 修订/补充（模型节点）：只出**结构化 edits**，不自己写文件。

    写权边界：Host 的 `n6_apply` 只写 `run_dir/sandbox/TESTLIB/`，不写冻结的 `TESTLIB/`。
    **I7**：本节点不再自增 `n6_n8_cycles`（返工预算只在 N8 判 rework 时消耗）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N6")
    cycles, limit = _cycles_and_limit(ctx, data)
    n5 = data.get_state("n5_impact") or {}
    n8 = data.get_state("n8_check") or {}
    n11 = data.get_state("n11_review") or {}
    cases = list(n5.get("must_change_cases") or [])

    rework_reasons = [str(f) for f in (n8.get("data") or {}).get("must_fix", [])] \
        if isinstance(n8.get("data"), dict) else []
    # N11 证据守护判 broken 时的返工请求也是 N6 的返工输入（否则回边后作者看不到原因）
    for req in n11.get("rework_requests") or []:
        if isinstance(req, dict):
            rework_reasons.append(
                f"{req.get('case')}: {req.get('what')}（依据：{req.get('basis')}）")

    targets = build_n6_targets(ctx, data)
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
        "must_change_count": n5.get("must_change_count"),
        "rule": ("只针对 targets 的用例；edits.old 必须逐字取自 targets[].excerpt.text 并且唯一；"
                 "拿不准写进 notes，不要猜。"),
        "write_scope_rule": "只写沙箱；Host 的 n6_apply 负责落盘，模型不得声称已改文件。",
    }
    out = await run_model_node(
        ctx, "N6", prompt_key="n6_author", input_data=input_data,
        offered={"cases": set(cases) | {t["case"] for t in targets}},
    )
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N6", "N6_author_note.md",
                               extra={"cycle": cycles + 1,
                                      "targets": [t["case"] for t in targets],
                                      "write_scope": str(ctx.run_dir / "sandbox" / "TESTLIB")})
    await data.async_set_state("n6_author", out)
    ctx.node_finished("N6", status=out["mode"],
                      detail={"mode": out["mode"], "cycle": cycles + 1,
                              "targets": len(targets),
                              "validation_ok": (out.get("validation") or {}).get("ok")})
    return out


# ---------------------------------------------------------------- N8


_CHECKLIST = [
    "地址必须写成 <段基址>+<块内偏移>，且与接口文档位定义表一致",
    "预期值以接口文档位定义表为准，不迁就 RTL",
    "失败必须让日志出现 *E（同时发 `uvm_error）",
    "禁止裸 wait(...)，每个等待必须有超时兜底",
    "禁止固定延时收尾，结束条件用 wait(test_done)",
    "白盒 uvm_hdl_force 必须成对 release 并检查返回值",
]


def _sandbox_code(ctx: RunCtx) -> tuple[list[dict[str, Any]], list[str]]:
    """取 N6 施加后的沙箱代码（N8 的复核对象）与目标用例名。"""
    applied = (ctx.run_dir / "sandbox" / "TESTLIB")
    files = sorted(applied.glob("*.sv")) if applied.is_dir() else []
    out = []
    for path in files:
        out.append({"file": path.name, "md5": md5_file(path),
                    "excerpt": path.read_text(encoding="utf-8", errors="replace")[:6000]})
    return out, [p.stem for p in files]


async def n8_check(data: Any) -> dict[str, Any]:
    """N8 静态复核（模型节点）→ 显式分叉到 N6（回边）/ N9 / N13（升级）。

    **fail-closed（#1/C3）**：模型调用失败、输出校验失败、verdict 缺失 ⇒ node_failed；
    绝不再 `verdict = ... or "pass"`。
    """
    ctx = ctx_of(data)
    ctx.node_started("N8")
    cycles, limit = _cycles_and_limit(ctx, data)
    n8_prev = data.get_state("n8_check") or {}
    n6_applied = data.get_state("n6_applied") or {}

    sandbox_cases, sandbox_names = _sandbox_code(ctx)
    revision_points: list[dict[str, Any]] = []
    for target in (data.get_state("n6_targets") or {}).get("targets") or []:
        revision_points.extend(target.get("revision_points") or [])

    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles,
        "sandbox_cases": sandbox_cases,
        "revision_points": revision_points,
        "checklist": _CHECKLIST,
        "rework_reasons": [str(f) for f in (n8_prev.get("data") or {}).get("must_fix", [])]
        if isinstance(n8_prev.get("data"), dict) else [],
        "rule": "verdict=rework 必须给逐条可核依据；只依据本 input 的材料，不得假设未提供的文件内容。",
    }
    out = await run_model_node(ctx, "N8", prompt_key="n8_check",
                               input_data=input_data,
                               offered={"cases": set(sandbox_names)})
    if out["mode"] == "standin":
        if ctx.mode == "real":
            ctx.node_failed("N8", message="real 模式下 N8 无真实模型输出 ⇒ 静态复核不得跳过")
            raise RuntimeError("N8：real 模式要求真实模型复核（standin 不得默认 pass）")
        # drill：夹具 check_C 的结论（accept_v1 依赖 drill 能继续到 G2）
        text = ctx.read_fixture_text("check_C.md") or ""
        rejected = "退回" in text and "通过" not in text
        out["data"] = _standin(ctx, "N8", "check_C.md", extra={
            "verdict": "rework" if rejected else "pass",
            "cycle": cycles, "limit": limit,
            "reject_basis": [ln for ln in text.splitlines() if "退回" in ln][:3],
        })
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N8", message=f"N8 校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N8：静态复核校验失败，不得进入 N9：{problems[:5]}")

    data_out = out.get("data") if isinstance(out.get("data"), dict) else {}
    verdict = str(data_out.get("verdict") or "").strip().lower()
    if verdict not in ("pass", "rework"):
        # 显式缺失/非法 ⇒ 失败（C3：不得默认 pass）
        ctx.node_failed("N8", message=f"N8 verdict 缺失/非法：{verdict!r}")
        raise RuntimeError(f"N8：verdict 缺失或非法（{verdict!r}）⇒ 不得放行到 N9")

    cases = [str(c.get("case")) for c in (n6_applied.get("cases") or []) if c.get("case")] or sandbox_names
    # drill 的 N8 是**替身复核**（夹具 check_C），不是本轮真实证据；不写本轮用例态台账。
    # 理由：I2 的 G2 前置把"本轮写入的待验"当阻断，drill 全跑证据必然不合格，
    # 若替身复核也写「已修订待验」就会把 accept_v1 的 drill 永久堵在 G2（Lead/WS-L 已确认）。
    write_ledger = ctx.mode == "real"
    if write_ledger:
        _ensure_case_state(ctx)
    else:
        ctx.event("warning", node="N8", status="drill_ledger_skipped",
                  detail={"rule": "drill 替身复核不写用例态台账；I2 以 real 证据为准"})
    if verdict == "rework" and write_ledger:
        new_cycles = cycles + 1
        ledger_cycles = min(new_cycles, limit)  # case_state 拒绝 > limit；==limit 合法（记录已到上限）
        for idx, case in enumerate(cases):
            res = _set_case_state(
                ctx, case, "已退回",
                rework_cycles=ledger_cycles if idx == 0 else None,
                static_check="reject",
                note=f"N8 静态复核退回（第 {new_cycles} 次返工；limit={limit}）",
                updated_by="loop:N8",
            )
            if res["rc"] != 0:
                ctx.node_failed("N8", message=f"case_state set 失败 rc={res['rc']}")
                raise RuntimeError(f"N8：用例态台账写失败 rc={res['rc']}: {res['stderr_tail'][-300:]}")
        escalated = new_cycles >= limit
        out["cycle"] = new_cycles
        out["limit"] = limit
        out["escalated"] = escalated
        await data.async_set_state("n8_check", out)
        if escalated:
            ctx.node_finished("N8", status="escalated",
                              detail={"verdict": "rework", "cycle": new_cycles,
                                      "limit": limit, "escalated": True,
                                      "reason": "N8 返工超限 ⇒ 升级 N13 人工裁决"})
            await data.async_emit("N8_ESCALATE", out)
            return out
        ctx.node_finished("N8", status="rework",
                          detail={"verdict": "rework", "cycle": new_cycles, "limit": limit})
        await data.async_emit("N8_REWORK", out)
        return out

    # pass：静态卡点 C 通过（态仍是「已修订待验」，卡点D 之后才能「已验证通过」）
    if write_ledger:
        for case in cases:
            res = _set_case_state(ctx, case, "已修订待验", static_check="pass",
                                  note="N8 静态复核通过（卡点C=pass；待卡点D）",
                                  updated_by="loop:N8")
            if res["rc"] != 0:
                ctx.node_failed("N8", message=f"case_state set 失败 rc={res['rc']}")
                raise RuntimeError(f"N8：用例态台账写失败 rc={res['rc']}")
    out["cycle"] = cycles
    out["limit"] = limit
    out["escalated"] = False
    await data.async_set_state("n8_check", out)
    ctx.node_finished("N8", status=out["mode"], detail={"verdict": "pass", "cycle": cycles})
    await data.async_emit("N8_PASS", out)
    return out


# ---------------------------------------------------------------- N10（Host 抽数 + 模型分类）


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
                      n7: dict[str, Any], n9: dict[str, Any]) -> dict[str, Any]:
    """组装 case_state `已验证通过` 的 I3 合取证据（缺一项就会被工具拒绝，本层不例外）。"""
    counts = (item or {}).get("counts") or {}
    imprints = (item or {}).get("imprints") or {}
    compile_rc = None
    for c in (n7.get("cases") or []):
        if str(c.get("case")) == case:
            compile_rc = c.get("rc")
            break
    static_check = None
    for c in ledger(ctx).get("cases") or []:
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


async def n10_reconcile(data: Any) -> dict[str, Any]:
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
                          detail={"both_zero": out["both_zero"]},
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
            fields = _case_pass_fields(ctx, case, item, n7, n9)
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
                              "pending": len(pending_items)},
                      refs=[str(reconcile_path)] + [str((cases.get(c) or {}).get("path") or "")
                                                    for c in target_cases][:4])
    return out


# ---------------------------------------------------------------- N11（guardian）


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


def _ledger_summary(ctx: RunCtx) -> dict[str, Any]:
    led = ledger(ctx)
    counts: dict[str, int] = {}
    for item in led.get("cases") or []:
        state = str(item.get("state") or "")
        counts[state] = counts.get(state, 0) + 1
    return {"path": led.get("path"), "present": led.get("present"),
            "cases": led.get("cases") or [], "state_counts": counts,
            "rework_cycles": led.get("rework_cycles") or {},
            "pending_verified": counts.get("已修订待验", 0)}


async def n11_review(data: Any) -> dict[str, Any]:
    """N11 证据守护（模型：成链判断；Host：身份四方同值 + 结论交叉核对）。

    **业务 N11 = guardian**（审计 #15/A10）：
    - 成链 ⇒ `N11_INTACT` → N12；
    - 不成链 ⇒ `N11_REWORK` → N6（显式回边），并带返工请求；
    - Host 事实「不一致」而模型说 intact ⇒ fail closed（模型不得替 Host 掩盖身份错位）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N11")
    n10 = data.get_state("n10_reconcile") or {}
    n9 = data.get_state("n9_result") or {}
    counts = n10.get("counts") or n9.get("counts") or {}
    evidence = n10.get("evidence") or n9.get("evidence") or {}

    if ctx.mode == "drill":
        host_identity: dict[str, Any] = {
            "run_id": ctx.run_id, "consistent": True, "mismatches": [],
            "cases": [], "mode": "drill",
            "note": "drill：身份链使用夹具，不做真实四方同值强判（real 才强判）。",
        }
    else:
        host_identity = _host_identity(ctx, data)

    input_data = {
        "run_id": ctx.run_id,
        "identity": host_identity,
        "counts": counts,
        "verdict": n10.get("verdict") or n9.get("verdict"),
        "evidence": {
            "path": (evidence or {}).get("path"),
            "present": (evidence or {}).get("present"),
            "cases": {
                case: {
                    "path": (item or {}).get("path"),
                    "present": (item or {}).get("present"),
                    "counts": (item or {}).get("counts"),
                    "imprints": (item or {}).get("imprints"),
                    "identity": (item or {}).get("identity"),
                }
                for case, item in ((n9.get("cases") or {}) if isinstance(n9.get("cases"), dict) else {}).items()
            },
        },
        "case_states": _ledger_summary(ctx),
        "rework": ctx.kb.load_rework(ctx.run_dir),
        "rule": ("只判证据链是否成链：身份四方同值且证据可解析=intact；任一缺失/不一致=broken。"
                 "任何一项缺失不得判 intact。"),
    }
    out = await run_model_node(ctx, "N11", prompt_key="n11_review", input_data=input_data,
                               offered={"counts": counts})
    if out["mode"] == "standin":
        if ctx.mode == "real":
            ctx.node_failed("N11", message="real 模式下 N11 无真实模型输出 ⇒ 证据守护不得跳过")
            raise RuntimeError("N11：real 模式要求真实 guardian 判成链（standin 不得判 intact）")
        out["data"] = _standin(ctx, "N11", "reconcile.md", extra={
            "chain": "intact",
            "reasons": ["drill/standin：按夹具证据链视为 intact（非模型结论）"],
            "rework_requests": [],
            "caveats": ["drill 替身，不构成真实证据守护结论"],
        })
    elif (out.get("validation") or {}).get("ok") is not True:
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N11", message=f"N11 校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N11：证据守护校验失败：{problems[:5]}")

    data_out = out.get("data") if isinstance(out.get("data"), dict) else {}
    model_chain = str(data_out.get("chain") or "").strip().lower()
    if model_chain not in ("intact", "broken"):
        ctx.node_failed("N11", message=f"N11 chain 缺失/非法：{model_chain!r}")
        raise RuntimeError("N11：chain 缺失或非法 ⇒ 不得放行 N12")

    host_consistent = bool(host_identity.get("consistent"))
    if not host_consistent and model_chain == "intact":
        # Host 事实说不一致，模型却判 intact ⇒ 模型结论不得覆盖 Host 事实
        ctx.node_failed("N11", message="模型判 intact 但 Host 身份四方同值不成立（不得掩盖身份错位）")
        raise RuntimeError(
            "N11：Host 身份校验失败（"
            + "；".join(host_identity.get("mismatches") or [])[:500]
            + "），模型不得判 intact"
        )
    rework_requests = list(data_out.get("rework_requests") or [])
    if not host_consistent and not rework_requests:
        rework_requests = [
            {"case": c.get("case"), "what": "补齐/重采证据并核对 md5 与 run_id",
             "basis": "; ".join(host_identity.get("mismatches") or [])[:300]}
            for c in host_identity.get("cases") or []
        ]
    chain_effective = "broken" if (not host_consistent or model_chain == "broken") else "intact"
    out["host_identity"] = host_identity
    out["chain_effective"] = chain_effective
    out["model_chain"] = model_chain
    out["rework_requests"] = rework_requests
    await data.async_set_state("n11_review", out)

    if chain_effective == "broken":
        # I7：证据守护返工同样吃掉返工预算（否则 broken↔N6 会无限循环）
        cycles, limit = _cycles_and_limit(ctx, data)
        new_cycles = cycles + 1
        _ensure_case_state(ctx)
        for idx, item in enumerate(ledger(ctx).get("cases") or []):
            case = str(item.get("case") or "")
            if not case:
                continue
            _set_case_state(
                ctx, case, "已修订待验",
                rework_cycles=min(new_cycles, limit) if idx == 0 else None,
                note=f"N11 证据链 broken ⇒ 回 N6 返工（第 {new_cycles} 次；limit={limit}）",
                updated_by="loop:N11",
            )
        out["cycle"] = new_cycles
        out["limit"] = limit
        await data.async_set_state("n11_review", out)
        if new_cycles >= limit:
            # I7：超限不再直接死掉，而是**升级 N13 人工裁决**（N11_ESCALATE→gate2，lifecycle 加边）
            ctx.node_finished(
                "N11", status="escalated",
                detail={"chain": "broken", "cycle": new_cycles, "limit": limit,
                        "escalated": True,
                        "reason": "N11 证据守护返工超限 ⇒ 升级 N13 人工裁决"},
            )
            await data.async_emit("N11_ESCALATE", out)
            return out
        ctx.node_finished("N11", status="broken",
                          detail={"chain": "broken", "host_consistent": host_consistent,
                                  "rework": len(rework_requests), "cycle": new_cycles,
                                  "limit": limit})
        await data.async_emit("N11_REWORK", out)
        return out
    ctx.node_finished("N11", status="intact",
                      detail={"chain": "intact", "host_consistent": host_consistent})
    await data.async_emit("N11_INTACT", out)
    return out


# ---------------------------------------------------------------- N12


def _resolve_ref(ctx: RunCtx, ref: str) -> Path | None:
    """N12 引用可解析性（path 或 `path#Lnn`）；解析不出即 None（拒发）。"""
    text = str(ref).strip()
    if not text:
        return None
    text = text.split("#", 1)[0].strip()
    if not text or text.startswith("line "):
        return None
    candidate = Path(text)
    candidates: list[Path] = []
    if candidate.is_absolute():
        candidates.append(candidate)
    else:
        candidates += [ctx.run_dir / text, P.WORKSPACE_ROOT / text, P.ENV_ROOT / text]
        if text.startswith("kb/"):
            candidates.append(P.KB_DIR / text[3:])
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _compose_n12_markdown(out: dict[str, Any]) -> str:
    data = out.get("data") if isinstance(out.get("data"), dict) else {}
    lines = [f"# {data.get('title') or '评估报告'}", "",
             f"- 模型模式：`{out.get('mode')}`；provider：`{out.get('provider')}`",
             f"- claimed_verdict：`{data.get('claimed_verdict')}`",
             ""]
    for section in data.get("sections") or []:
        heading = str(section.get("heading") or "")
        body = str(section.get("body_md") or "")
        refs = [str(r) for r in (section.get("refs") or [])]
        lines += [f"## {heading}", "", body, ""]
        if refs:
            lines.append("引用：" + "、".join(f"`{r}`" for r in refs))
            lines.append("")
    open_items = data.get("open_items") or []
    lines += ["## 未闭环项", ""] + ([f"- {x}" for x in open_items] or ["(无)"]) + [""]
    return "\n".join(lines)


async def n12_report(data: Any) -> dict[str, Any]:
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
    ctx.node_finished("N12", status=out["mode"],
                      detail={"mode": out["mode"],
                              "claimed_verdict": data_out.get("claimed_verdict"),
                              "refs": len(refs)},
                      refs=[str(report_path)] + [str(_resolve_ref(ctx, r)) for r in refs][:4])
    return out
