"""模型语义节点：N3 / N6 / N8 / N11 / N12。

**真 ModelRequest**（经 `host.model_provider` 接入宿主已声明的 provider）。
分工严格遵循技能 `agently-request`：

- 模型只做**语义判断**：分组、修订意图、复核意见、评估、叙述；
- **Host 拥有确定性校验**：schema/类型、offered-key 成员性、算术、数字一致性、副作用；
- 每个节点的输出都带 `validation` 结果；校验失败**不静默接受**。

降级：provider 不可用时（无凭据 / `LOOP_LLM_MODE=standin`）退回**显式标注**的
确定性替身（`standin=True`），绝不假装有模型输出。离线测试即走此路径。

**N10 不在这里**：结果对账的数字抽取是 Host 确定性的（`host/evidence.py`），
口径判定不能交给模型。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from host import model_provider as MP

from ..context import RunCtx, ctx_of

PROMPTS_FILE = Path(__file__).resolve().parents[2] / "prompts" / "loop_nodes.yaml"


def load_prompts() -> dict[str, Any]:
    doc = yaml.safe_load(PROMPTS_FILE.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def _family_reason() -> str:
    cfg = MP.resolve()
    return cfg.reason or "provider 不可用"


# ---------------------------------------------------------------- 降级替身


def _standin(ctx: RunCtx, node: str, artifact: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    text = ctx.read_fixture_text(artifact)
    out: dict[str, Any] = {
        "standin": True,
        "provider": "none",
        "reason": f"未接入模型（{_family_reason()}）；本节点输出为确定性替身，非模型结论。",
        "node": node,
        "source": artifact,
        "artifact_present": text is not None,
    }
    if text is not None:
        out["excerpt"] = text[:1200]
        out["bytes"] = len(text.encode("utf-8"))
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
            # Pydantic 契约：类型/必填/枚举精确，避免 YAML 列表被当成"数组输出"
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

#: 已实现确定性校验的输出种类（= prompt_key 的前缀）
_KNOWN_KINDS = frozenset({"n3", "n6", "n8", "n11", "n12"})


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
    **这里曾有过一个静默失效的 bug**：分支比对 `"n12"` 而调用方传的是 `"n12_report"`，
    于是五个节点的校验一条都没跑、`problems` 恒为空 —— "没问题"和"没检查"看起来一样。
    现在未知 kind 会**显式报错**，不再静默通过。
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
            ids = _check_membership("groups.diff_ids", offered.get("diff_ids", set()), _as_list(g.get("diff_ids")), problems)
            seg = str(g.get("segment") or "")
            if offered.get("segments") and seg not in offered["segments"]:
                problems.append(f"groups.segment 未在 offered_segments 中：{seg!r}")
            ok_groups.append({"segment": seg, "kind": str(g.get("kind") or ""), "diff_ids": sorted(ids),
                              "why": str(g.get("why") or "")})
        accepted["groups"] = ok_groups
        accepted["risky_points"] = [str(x) for x in _as_list(data.get("risky_points"))]

    elif kind == "n6":
        plan = _as_list(data.get("plan"))
        ok_plan = []
        for item in plan:
            if not isinstance(item, dict):
                continue
            case = str(item.get("case") or "")
            if offered.get("cases") and case not in offered["cases"]:
                problems.append(f"plan.case 不在目标用例中：{case!r}")
                continue
            ok_plan.append({
                "case": case,
                "change_intent": str(item.get("change_intent") or ""),
                "basis_offsets": [str(x) for x in _as_list(item.get("basis_offsets"))],
                "risk": str(item.get("risk") or ""),
            })
        accepted["plan"] = ok_plan
        accepted["rework_resolution"] = [str(x) for x in _as_list(data.get("rework_resolution"))]
        accepted["notes"] = [str(x) for x in _as_list(data.get("notes"))]
        if offered.get("cases") and not ok_plan:
            problems.append("plan 为空或全部被拒（必须针对给定目标用例）")

    elif kind == "n8":
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in ("pass", "rework"):
            problems.append(f"verdict 非法：{verdict!r}（只允许 pass/rework）")
        findings = [f for f in _as_list(data.get("findings")) if isinstance(f, dict)]
        must_fix = [str(x) for x in _as_list(data.get("must_fix"))]
        basisless = [f for f in findings if str(f.get("result", "")).lower() in ("fail", "不通过") and not str(f.get("basis") or "").strip()]
        if basisless:
            problems.append(f"{len(basisless)} 条 fail 结论缺少 basis（空泛意见视为无效）")
        if verdict == "rework" and not must_fix:
            problems.append("verdict=rework 但 must_fix 为空（退回必须给必须修复项）")
        accepted.update({"verdict": verdict, "findings": findings, "must_fix": must_fix})

    elif kind == "n11":
        assessment = str(data.get("assessment") or "").strip().lower()
        if assessment not in ("satisfied", "needs_rework"):
            problems.append(f"assessment 非法：{assessment!r}")
        counts = offered.get("counts") or {}
        k1_nonzero = not ((counts.get("koutou1") or {}).get("zero", True))
        if assessment == "satisfied" and k1_nonzero:
            problems.append("口径一非 0 却判 satisfied（违反判据）")
        accepted.update({
            "assessment": assessment,
            "reasons": [str(x) for x in _as_list(data.get("reasons"))],
            "rework_requests": [r for r in _as_list(data.get("rework_requests")) if isinstance(r, dict)],
            "caveats": [str(x) for x in _as_list(data.get("caveats"))],
        })

    elif kind == "n12":
        # 关键反幻觉校验：报告引用的数字必须与 Host 计算的权威值一致
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
        statement = str(data.get("verdict_statement") or "")
        verdict = offered.get("verdict") or {}
        if verdict.get("passed") is False and "跑通" in statement and "不得" not in statement and "未" not in statement:
            problems.append("判据未通过却在报告里宣称跑通")
        accepted.update({
            "title": str(data.get("title") or ""),
            "sections": [s for s in _as_list(data.get("sections")) if isinstance(s, dict)],
            "counts_quoted": quoted,
            "authoritative_counts": {k: (auth.get(k) or {}).get("value") for k in ("koutou1", "koutou2")},
            "counts_match_authority": not mismatches,
            "verdict_statement": statement,
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
    # `n12_report` → `n12`：分支键必须是归一后的种类，
    # 否则校验会静默失配（曾发生：problems 恒为空，看起来"没问题"）。
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
        detail={"model": out["provider"], "problems": validation["problems"][:5]},
    )
    return out


# ---------------------------------------------------------------- N3


async def n3_digest(data: Any) -> dict[str, Any]:
    """N3 差异摘要（模型节点）。"""
    ctx = ctx_of(data)
    ctx.node_started("N3")
    n2 = data.get_state("n2_diff") or {}
    diff_path = ctx.run_dir / "n2_diff.json"
    diffs: list[dict[str, Any]] = []
    try:
        import json

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
    await data.async_set_state("n3_digest", out)
    ctx.node_finished("N3", status=out["mode"],
                      detail={"mode": out["mode"], "provider": out.get("provider"),
                              "problems": (out.get("validation") or {}).get("problems", [])[:3]})
    return out


# ---------------------------------------------------------------- N6


async def n6_author(data: Any) -> dict[str, Any]:
    """N6 修订/补充（模型节点）。

    本轮只产出**修订方案**；实际改写沙箱文件由 Host 的独立步骤执行
    （写权边界：作者只写沙箱 `run_dir/sandbox/TESTLIB/`，不写 `TESTLIB/`）。
    """
    ctx = ctx_of(data)
    cycles = int(data.get_state("n6_n8_cycles") or 0)
    ctx.node_started("N6")
    n5 = data.get_state("n5_impact") or {}
    n8 = data.get_state("n8_check") or {}
    cases = list(n5.get("must_change_cases") or [])

    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles + 1,
        "targets": [
            {"case": c, "write_scope": str(ctx.run_dir / "sandbox" / "TESTLIB")} for c in cases
        ],
        "rework_reasons": [str(f) for f in (n8.get("data") or {}).get("must_fix", [])] if isinstance(n8.get("data"), dict) else [],
        "must_change_count": n5.get("must_change_count"),
        "write_scope_rule": "只写沙箱；TESTLIB/ 不由本层写。",
    }
    out = await run_model_node(
        ctx, "N6", prompt_key="n6_author", input_data=input_data,
        offered={"cases": set(cases)},
    )
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N6", "N6_author_note.md",
                               extra={"cycle": cycles + 1, "targets": cases,
                                      "write_scope": str(ctx.run_dir / "sandbox" / "TESTLIB")})
    await data.async_set_state("n6_author", out)
    await data.async_set_state("n6_n8_cycles", cycles + 1)
    ctx.node_finished("N6", status=out["mode"], detail={"mode": out["mode"], "cycle": cycles + 1})
    return out


# ---------------------------------------------------------------- N8


async def n8_check(data: Any) -> dict[str, Any]:
    """N8 静态复核（模型节点）→ 显式分叉到 N6（回边）或 N9。"""
    ctx = ctx_of(data)
    ctx.node_started("N8")
    cycles = int(data.get_state("n6_n8_cycles") or 0)
    limit = int(data.get_state("rework_limit") or 3)
    n6 = data.get_state("n6_author") or {}
    n8_prev = data.get_state("n8_check") or {}

    # **复核范围必须与"能看到的东西"一致** —— 这是一次契约设计错误的修正。
    # 早先不管有没有沙箱文件都用同一份**代码级**检查项（`*E`、裸 `wait`、force 成对 release），
    # 而 N6 本轮只产出**修订方案** ⇒ 方案文档当然过不了代码检查
    # ⇒ 模型连续 3 次判 rework ⇒ I7 上限升级 HALT，闭环永远到不了 N10/N11/N12。
    sandbox_lib = ctx.run_dir / "sandbox" / "TESTLIB"
    sandbox_files = sorted(sandbox_lib.glob("*.sv")) if sandbox_lib.is_dir() else []
    code_excerpts: list[dict[str, str]] = []
    if sandbox_files:
        scope = "plan_and_code"
        checklist = [
            "地址必须写成 <段基址>+<块内偏移>，且与接口文档位定义表一致",
            "预期值以接口文档位定义表为准，不迁就 RTL",
            "失败必须让日志出现 *E（同时发 `uvm_error）",
            "禁止裸 wait(...)，每个等待必须有超时兜底",
            "禁止固定延时收尾，结束条件用 wait(test_done)",
            "白盒 uvm_hdl_force 必须成对 release 并检查返回值",
        ]
        code_excerpts = [
            {"file": f.name, "excerpt": f.read_text(encoding="utf-8", errors="replace")[:4000]}
            for f in sandbox_files[:3]
        ]
    else:
        # 只有方案可审：按"方案完备性"判，**不得**用代码级判据否决一份方案
        scope = "plan_only"
        checklist = [
            "方案必须覆盖 input.plan 的每一个目标用例，且不回退成泛泛而谈",
            "basis_offsets 必须形如 <段基址>+<块内偏移>，且非空",
            "change_intent 必须说明改什么与为什么，不得只复述差异标题",
            "每条必须声明风险或不确定性",
            "若 input.rework_reasons 非空，方案必须逐条回应上一轮退回意见",
        ]

    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles,
        "review_scope": scope,
        "scope_note": (
            "本 input 只提供修订方案，未提供用例源码 ⇒ 只审方案完备性，"
            "**不得**以代码级判据（`*E` / 裸 wait / force 成对 release）否决方案。"
            if scope == "plan_only"
            else "本 input 同时提供方案与沙箱用例源码摘要 ⇒ 可同时审代码级判据。"
        ),
        "plan": (n6.get("data") or {}).get("plan", []) if isinstance(n6.get("data"), dict) else [],
        "rework_reasons": [str(f) for f in (n8_prev.get("data") or {}).get("must_fix", [])]
        if isinstance(n8_prev.get("data"), dict)
        else [],
        "sandbox_code": code_excerpts,
        "checklist": checklist,
        "rule": "verdict=rework 必须给逐条可核依据；只依据本 input 的材料，不得假设未提供的文件内容。",
    }
    out = await run_model_node(ctx, "N8", prompt_key="n8_check", input_data=input_data, offered={})
    if out["mode"] == "standin":
        text = ctx.read_fixture_text("check_C.md") or ""
        rejected = "退回" in text and "通过" not in text
        if ctx.scenario == "rework_once" and cycles <= 1:
            rejected = True
        out["data"] = _standin(ctx, "N8", "check_C.md", extra={
            "verdict": "rework" if rejected else "pass",
            "cycle": cycles, "limit": limit,
            "reject_basis": [ln for ln in text.splitlines() if "退回" in ln][:3],
        })
    verdict = str((out.get("data") or {}).get("verdict") or "pass").lower()
    await data.async_set_state("n8_check", out)

    if verdict != "rework":
        ctx.node_finished("N8", status=out["mode"], detail={"verdict": "pass", "cycle": cycles})
        await data.async_emit("N8_PASS", out)
        return out
    if cycles >= limit:
        ctx.node_finished("N8", status="escalated", detail={"verdict": "rework", "cycle": cycles, "limit": limit})
        await data.async_emit("N8_ESCALATE", out)
        return out
    ctx.node_finished("N8", status="rework", detail={"verdict": "rework", "cycle": cycles, "limit": limit})
    # 显式回边：修订↔退回循环由**图上的边**承载，不在 handler 里 while。
    await data.async_emit("N8_REWORK", out)
    return out


# ---------------------------------------------------------------- N10（Host 确定性，非模型）


async def n10_reconcile(data: Any) -> dict[str, Any]:
    """N10 结果对账。

    与其他节点不同，这里的**数字抽取是 Host 确定性的**（`host.evidence`），
    因为口径判定绝不能交给模型（spec I3 / `doc/AGENTS.md` 红线 3）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N10")
    ev = ctx.evidence()
    reconcile_text = ctx.read_fixture_text("reconcile.md") or ""
    out = {
        "evidence": ev,
        "counts": ev.get("counts"),
        "verdict": ev.get("verdict"),
        "extraction_owner": "host:host/evidence.py（确定性；不经模型）",
        "fail_classification": {
            "standin": True,
            "provider": "none",
            "note": "FAIL 三分类本轮仍由确定性替身给出；见 README §5 限制。",
            "excerpt": reconcile_text[:600],
            "classes": ["既有缺陷", "本轮引入", "待裁决"],
        },
        "both_zero": (ev.get("counts") or {}).get("both_zero"),
    }
    await data.async_set_state("n10_reconcile", out)
    ctx.node_finished("N10", status="pass" if out["both_zero"] else "fail",
                      detail={"both_zero": out["both_zero"]}, refs=[ev.get("path", "")])
    return out


# ---------------------------------------------------------------- N11


async def n11_review(data: Any) -> dict[str, Any]:
    """N11 评估（模型节点）。"""
    ctx = ctx_of(data)
    ctx.node_started("N11")
    n10 = data.get_state("n10_reconcile") or {}
    counts = n10.get("counts") or {}
    ev = n10.get("evidence") or {}
    input_data = {
        "run_id": ctx.run_id,
        "counts": counts,
        "verdict": n10.get("verdict"),
        "imprints": {k: {"consistent": v.get("consistent"), "verified": v.get("verified_count"),
                         "failed": v.get("failed_count"), "observed": v.get("observed"),
                         "expected": v.get("expected")}
                     for k, v in (ev.get("imprints") or {}).items()},
        "rework": ctx.kb.load_rework(ctx.run_dir),
        "rule": "口径一非 0 不得判 satisfied；不得替人做发版决策。",
    }
    out = await run_model_node(ctx, "N11", prompt_key="n11_review", input_data=input_data,
                               offered={"counts": counts})
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N11", "reconcile.md", extra={"needs_rework": False})
    await data.async_set_state("n11_review", out)
    ctx.node_finished("N11", status=out["mode"], detail={"mode": out["mode"]})
    return out


# ---------------------------------------------------------------- N12


async def n12_report(data: Any) -> dict[str, Any]:
    """N12 报告（模型节点）。数字必须逐字引用 Host 权威值。"""
    ctx = ctx_of(data)
    ctx.node_started("N12")
    n10 = data.get_state("n10_reconcile") or {}
    n5 = data.get_state("n5_impact") or {}
    n11 = data.get_state("n11_review") or {}
    counts = n10.get("counts") or {}
    ev = n10.get("evidence") or {}
    conflicts = ctx.kb.load_conflicts()

    input_data = {
        "run_id": ctx.run_id,
        "counts": counts,
        "verdict": n10.get("verdict"),
        "imprints": {k: {"consistent": v.get("consistent"), "verified": v.get("verified_count"),
                         "observed": v.get("observed"), "expected": v.get("expected")}
                     for k, v in (ev.get("imprints") or {}).items()},
        "case_states": ctx.kb.load_rework(ctx.run_dir),
        "must_change_count": n5.get("must_change_count"),
        "must_change_cases": n5.get("must_change_cases", []),
        "assessment": (n11.get("data") or {}).get("assessment") if isinstance(n11.get("data"), dict) else None,
        "conflicts": {"total": len(conflicts.get("items", [])),
                      "blocks_release": len([c for c in conflicts.get("items", []) if c.get("blocks_release")])},
        "rule": "所有数字逐字引用本 input，禁止手算；必须写明「口径二为 0 不足以判绿」。",
    }
    out = await run_model_node(ctx, "N12", prompt_key="n12_report", input_data=input_data,
                               offered={"counts": counts, "verdict": n10.get("verdict")})
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N12", "n12_report.md", extra={
            "koutou1": (counts.get("koutou1") or {}).get("value"),
            "koutou2": (counts.get("koutou2") or {}).get("value"),
            "number_rule": "报告里所有数字一律由命令输出复制，禁手算（doc/AGENTS.md 红线 10）。",
        })
    else:
        # 数字一致性以 **Host 权威值**为准；模型引用有出入时以权威覆盖并留痕
        out["authoritative_counts"] = {
            "koutou1": (counts.get("koutou1") or {}).get("value"),
            "koutou2": (counts.get("koutou2") or {}).get("value"),
        }
    await data.async_set_state("n12_report", out)
    ctx.node_finished("N12", status=out["mode"],
                      detail={"mode": out["mode"],
                              "counts_match": (out.get("validation") or {}).get("accepted", {}).get("counts_match_authority")})
    return out
