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
import difflib
from functools import partial
from pathlib import Path
from typing import Any

from host import evidence as EV
from host import model_provider as MP
from host import paths as P
from host import agent_memory as AM
from host import agent_handoff as AH
from host import agent_review as AR

from ..context import RunCtx, ctx_of
from .host_steps import md5_file, run_kb_tool

#: Host 侧确定性校验的输出种类（= prompt_key 的前缀）
_KNOWN_KINDS = frozenset({"n3", "n6", "n8", "n10", "n11", "n12"})

#: I7 缺省上限（权威仍在 case_state 台账；这里只是缺省值，不新增漂移常量）
DEFAULT_REWORK_LIMIT = 3

#: P-25 方案 A：观测点印记名（与 `host/evidence.py` 的印记解析同前缀 `N6_`，不另写一套解析）。
_OBS_MARKER_RE = re.compile(r"N6_[A-Za-z0-9_]+")
#: 十六进制字面量（addr / offset / expected_value）：值必须带 `0x`，否则印记解析不到。
_HEX_LITERAL_RE = re.compile(r"0x[0-9A-Fa-f]+")



def _family_reason() -> str:
    cfg = MP.resolve()
    return cfg.reason or "provider 不可用"


# ---------------------------------------------------------------- 共享小工具（F06 已拆出）

from .model_common import (  # noqa: E402
    artifact as _artifact, case_edits_from_output, counts_text, load_prompts,
    read_json as _read_json, write_text as _write_text,
)
from . import model_request as MR  # noqa: E402
# F06：节点语义按模块拆分；这里保留兼容导出（消费者与测试不需要改 import）。
from .n6_facts import _api_semantics_for, build_n6_targets  # noqa: E402,F401
from .n10_semantics import (  # noqa: E402,F401
    PENDING_CLASSES, _case_pass_fields, _cases_table, _classification_summary,
    _diffs_for_classification, _per_case_fail_buckets,
    _persist_pending, _reconcile_markdown,
)
from .n11_guard import _host_identity  # noqa: E402,F401


def _request_contract(prompt_key: str) -> dict[str, Any]:
    """兼容导出：契约构造的唯一实现在 `model_request.request_contract`。"""
    return MR.request_contract(prompt_key)


async def _run_model_attempt(ctx: RunCtx, node: str, *, prompt_key: str,
                             input_data: dict[str, Any], offered: dict[str, Any]) -> dict[str, Any]:
    """兼容导出：单次 attempt 的机制在 `model_request`，Host 校验器仍由本模块注入。

    校验器绑定**本轮 run_dir**（R3-01：N6 观测点 marker 必须能解析到本 run 的文档条目快照）。
    """
    return await MR.run_attempt(ctx, node, prompt_key=prompt_key, input_data=input_data,
                                offered=offered, validate=partial(_validate, run_dir=ctx.run_dir))


async def run_model_node(ctx: RunCtx, node: str, *, prompt_key: str,
                         input_data: dict[str, Any], offered: dict[str, Any]) -> dict[str, Any]:
    """人工控制只包围模型请求，消费者在本函数返回后才取得输出（机制见 model_request）。

    R3-01：把 `ctx.run_dir` 绑进 Host 校验器 —— N6 观测点 marker 的可解析校验**必须**用
    本 run 冻结的文档条目快照（生产路径恒有 run 上下文，不得退化到跨 run 猜测）。
    """
    return await MR.run_model_node(ctx, node, prompt_key=prompt_key, input_data=input_data,
                                   offered=offered, validate=partial(_validate, run_dir=ctx.run_dir))


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


# ---------------------------------------------------------------- Host 侧校验


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _check_membership(label: str, offered: set[str], claimed: list[Any], problems: list[str]) -> set[str]:
    unknown = [str(c) for c in claimed if str(c) not in offered]
    if unknown:
        problems.append(f"{label} 出现未提供给模型的标识：{sorted(set(unknown))[:8]}")
    return {str(c) for c in claimed if str(c) in offered}


def _validate(kind: str, payload: dict[str, Any], *, offered: dict[str, Any],
              run_dir: Path | str | None = None) -> dict[str, Any]:
    """Host 的确定性校验。返回 `{ok, problems, accepted}`。

    `kind` 由 `prompt_key` 前缀派生（`n12_report` → `n12`）。
    **未知 kind 必须显式报错**（历史上曾因归一化失配导致五个节点"没检查"看起来像"没问题"）。

    `run_dir`（R3-01）：本轮 run 目录，用于「N6 观测点 marker 的期望必须可解析」——
    解析仍归 `host.evidence.resolve_expected_imprint`（本层不另写判据）。**该检查恒执行**：
    `run_dir=None` 时由解析器自己的回退链（跨 run 唯一命中 / current-index）解析，仍解析
    不到 ⇒ problem —— 不存在"调用方没绑 run_dir 就跳过校验"的旁路
    （"校验未实现/未执行 = 不得判通过"）。生产路径恒以 `ctx.run_dir` 绑定。
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

        # ---- P-25 方案 A：观测点印记（跨字段约束，Pydantic 做不了 ⇒ Host fail-closed）
        # ① 每个目标用例至少一条；② marker 唯一；③ marker 必须出现在**同用例**
        # `edits[].new` 里（防"只列不写"）；④ 格式/字段非法 ⇒ 记 problem（调用方 node_failed）。
        expected_cases = set(offered_cases) or {str(rev["case"]) for rev in ok_revisions}
        edits_new_by_case = {
            str(rev["case"]): [str(e.get("new") or "") for e in rev.get("edits") or []]
            for rev in ok_revisions
        }
        raw_points = [p for p in _as_list(data.get("observation_points")) if isinstance(p, dict)]
        ok_points: list[dict[str, Any]] = []
        # 唯一性（跨字段约束）与"最终可接受"分开记账：重复检测不因后续某项不合法而被绕过。
        seen_markers: dict[str, str] = {}
        marker_case: dict[str, str] = {}
        for index, point in enumerate(raw_points):
            label = f"observation_points[{index}]"
            case = str(point.get("case") or "")
            marker = str(point.get("marker") or "").strip()
            if expected_cases and case not in expected_cases:
                problems.append(f"{label}.case 不在目标用例中：{case!r}")
                continue
            if not _OBS_MARKER_RE.fullmatch(marker):
                problems.append(
                    f"{label}.marker 格式非法：{marker!r}（必须匹配 ^N6_[A-Za-z0-9_]+$）")
                continue
            if marker in seen_markers:
                problems.append(
                    f"{label}.marker 重复：{marker!r}（{seen_markers[marker]} 与 {case}；"
                    "印记必须唯一）")
                continue
            seen_markers[marker] = case
            bad_fields = [
                key for key in ("addr", "offset", "expected_value")
                if not _HEX_LITERAL_RE.fullmatch(str(point.get(key) or ""))
            ]
            basis = str(point.get("basis") or "").strip()
            if not basis:
                bad_fields.append("basis")
            if bad_fields:
                problems.append(
                    f"{label}（{marker or case}）字段非法/缺失：{bad_fields}"
                    "（addr/offset/expected_value 需 0x 十六进制字面量，basis 不得空）")
                continue
            if not any(marker in text for text in edits_new_by_case.get(case, [])):
                problems.append(
                    f"{case}: observation_points.marker {marker!r} 未出现在该用例 edits[].new 里"
                    "（只列不写 ⇒ 印记不会打印，I3 仍过不了）")
                continue
            # ---- R3-01：marker 的期望必须能从文档条目快照/索引解析出来。
            # 只对 ID 形态正确还不够：解析不到期望地址/值 ⇒ 日志里的印记永远被判
            # "期望不可解析"/"三向不一致"，I3 必失败 ⇒ 在请求前就 fail-closed（不静默放行）。
            # **恒执行**：不存在"调用方没绑 run_dir 就跳过校验"的旁路 —— run_dir=None 时由
            # `host/evidence.py` 自己的回退链（跨 run 唯一命中 / current-index）解析，仍解析
            # 不到 ⇒ problem。口径唯一：解析判据仍归 `host/evidence.py`。
            expected = EV.resolve_expected_imprint(marker, run_dir=run_dir)
            if not (expected.get("address") and expected.get("value")):
                reason = (
                    expected.get("value_note")
                    or f"文档条目快照/索引里没有匹配条目（resolved_by={expected.get('resolved_by') or '未解析'}）"
                )
                problems.append(
                    f"{label}.marker {marker!r} 的期望地址/值不可解析：{reason}"
                    "；marker 必须含 input.targets[].doc_bitdef.name（如条目 fpga_date ⇒ N6_fpga_date），"
                    "否则 host/evidence 解析不到、I3 必失败")
                continue
            marker_case[marker] = case
            ok_points.append({
                "case": case, "marker": marker, "addr": str(point.get("addr")),
                "offset": str(point.get("offset")),
                "expected_value": str(point.get("expected_value")), "basis": basis,
            })
        missing_points = sorted(
            c for c in expected_cases if c not in set(marker_case.values()))
        if missing_points:
            problems.append(
                f"缺少目标用例的 observation_points：{missing_points}"
                "（每个目标用例至少一条观测点印记）")
        accepted["observation_points"] = ok_points
        try:
            accepted["issue_responses"] = AH.validate_responses(
                {**accepted, 'issue_responses': data.get('issue_responses', [])},
                offered.get('rework_assignment'))
        except ValueError as exc:
            problems.append(str(exc))

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

    if kind in ('n8', 'n11'):
        try:
            accepted['issue_reviews'] = AR.validate(
                kind.upper(), data,
                offered.get('review_context'))
        except ValueError as exc:
            problems.append(str(exc))
    return {"ok": not problems, "problems": problems, "accepted": accepted}


# ---------------------------------------------------------------- N6 目标构造


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


def _n3_detail(out: dict[str, Any], *, offered_segments_empty: bool) -> dict[str, Any]:
    """N3 detail 的**投影字段**（P-13/P-14，契约 §3）：只从模型输出取值，不解析 md 正文。

    - `digest_summary` = 模型 `summary` 原文（面板据此显示"模型说了什么"）；
    - `digest_confirmations` = 模型 `risky_points` 原文列表；
    - `groups_count` = 模型分组条数（组数降级为关键数字，不再当节点摘要）；
    - `offered_segments_empty` = 本轮是否**没有段信息**（P-14：空 ⇒ 提示词不要求硬分组）。
    没有模型输出（standin/drill）⇒ 前三项显式 `None`（不拿夹具正文冒充模型结论）。
    """
    data = out.get("data") if isinstance(out.get("data"), dict) else {}
    live = out.get("mode") == "live"
    raw_summary = data.get("summary")
    digest_summary = (
        str(raw_summary).strip()
        if live and isinstance(raw_summary, str) and str(raw_summary).strip()
        else None
    )
    raw_conf = data.get("risky_points")
    digest_confirmations = (
        [str(x) for x in raw_conf]
        if live and isinstance(raw_conf, list) else None
    )
    groups = data.get("groups")
    return {
        "digest_summary": digest_summary,
        "digest_confirmations": digest_confirmations,
        "groups_count": len(groups) if live and isinstance(groups, list) else None,
        "offered_segments_empty": bool(offered_segments_empty),
    }


async def n3_digest(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n3 import run
    return await run(data, _artifact=_artifact, _compose_n3_markdown=_compose_n3_markdown, _n3_detail=_n3_detail, _standin=_standin, _write_text=_write_text, ctx_of=ctx_of, run_model_node=run_model_node)




























































































# ---------------------------------------------------------------- N6


def _observation_points(data_out: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """N6 detail 的观测点投影（P-25，契约：`[{case, marker, addr, offset, expected_value}]`）。

    只投影契约字段（`basis` 留在模型输出/调用记录里）；没有模型输出（standin/drill）⇒ None
    （显式"未下发"，不是空列表冒充"0 条观测点"）。
    """
    raw = data_out.get("observation_points") if isinstance(data_out, dict) else None
    if not isinstance(raw, list):
        return None
    return [
        {"case": point.get("case"), "marker": point.get("marker"),
         "addr": point.get("addr"), "offset": point.get("offset"),
         "expected_value": point.get("expected_value")}
        for point in raw if isinstance(point, dict)
    ]


async def n6_author(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n6_author import run
    return await run(data, AH=AH, AR=AR, _cycles_and_limit=_cycles_and_limit, _observation_points=_observation_points, _standin=_standin, build_n6_targets=build_n6_targets, case_edits_from_output=case_edits_from_output, ctx_of=ctx_of, run_model_node=run_model_node, _workspace_hint=_workspace_hint, _pin_candidate_baseline=_pin_candidate_baseline, _attach_candidate_channel=_attach_candidate_channel)
















































































# ---------------------------------------------------------------- N8


_CHECKLIST = [
    "用例代码的**地址实参保持原样**；revision_points 的 <段基址>+<块内偏移> 只用于对照文档，不得出现在代码里",
    "期望读回值必须与 input.rtl_change 描述的新行为一致；文档未同步的冲突要如实指出（不得为变绿改写入值/删检查）",
    "仅当本轮改动涉及失败路径/检查逻辑时才评估「失败必须让日志出现 *E（同时发 `uvm_error）」；只改期望值时本项标 N/A",
    "禁止裸 wait(...)，每个等待必须有超时兜底（只判本轮新增/改动的等待）",
    "禁止固定延时收尾，结束条件用 wait(test_done)",
    "白盒 uvm_hdl_force 必须成对 release 并检查返回值",
]


#: 单文件超过该字符数 ⇒ 必须用「源代码差异片段」（既有规则，防单文件过大）。
N8_FULL_FILE_CHARS = 6_000
#: N8 片段模式的上下文窗口（前后各 N 行；线性坐标取 after）。
N8_REGION_CONTEXT_LINES = 6
#: N8 沙箱代码分片预算（bytes，按 `AM.encoded` 紧凑序列化计）：约为 120000 总预算的一半，
#: 留出 contract / 台账 / summary 余量（F16）。
N8_SANDBOX_BUDGET_BYTES = 60_000


def build_sandbox_cases(
    sandbox_dir: Path | str,
    source_root: Path | str | None = None,
    applied_cases: list[dict[str, Any]] | None = None,
    *,
    budget_bytes: int | None = None,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """构造 N8 的 `sandbox_cases`：**每个文件都在**，按预算确定性降级，逐件带 `coverage`。

    规则（上下文规格 C1 / F16 / R4）：
    - 每件两种表示的成本是该件条目**实际紧凑序列化**的字节数（`AM.encoded`，含
      `coverage`/`changed_regions`/键名与标点）；不得用近似字节数或「片段一定更小」的假定。
    - 可行成本取 `min(全文成本, 片段成本)`；单文件 >6000 字符的受限件**只有片段成本**。
    - 默认全文；按文件名的确定性顺序，先预留后续件的可行成本，只有全文放不下才降级为片段。
    - 只有**全部候选件的最小可行成本之和**超过分片预算时才显式拒绝，不丢文件不静默抽样。
    - 片段不可得（缺源文件 / 无可定位变更）且是受限件 ⇒ **显式失败**。
    - 相同输入得到相同字节与相同覆盖汇总；`coverage`/`coverage_summary` 与实际发送内容一致。
    """
    budget = N8_SANDBOX_BUDGET_BYTES if budget_bytes is None else int(budget_bytes)
    if budget <= 0:
        raise ValueError("N8 沙箱分片预算必须为正数")
    applied = Path(sandbox_dir)
    source_base = Path(source_root) if source_root is not None else None
    files = sorted(applied.glob("*.sv")) if applied.is_dir() else []
    if not files:
        # fail closed（C1 / F16-b）：N6 施加后不应「没有可复核用例」，不得以 0 件通过。
        expected = [
            Path(c.get("sandbox_path") or c.get("file") or "?").name
            for c in applied_cases or [] if isinstance(c, dict)
        ]
        detail = f"applied_cases={expected}" if expected else "applied_cases 为空"
        raise RuntimeError(
            f"N8 无可复核的沙箱用例（{applied} 下没有 *.sv；{detail}）"
        )
    by_name = {Path(c.get("sandbox_path") or c.get("file") or "").name: c for c in applied_cases or []}
    present = {path.name for path in files}
    missing_cases = sorted(name for name in by_name if name and name not in present)
    if missing_cases:
        # 契约要求逐用例可定位（C1 / F16-b）：部分缺失也必须显式失败，不能只判全有/全无。
        raise RuntimeError(
            f"N8 沙盒缺少 applied_cases 对应的用例文件：{missing_cases}（沙盒内 {sorted(present)}）"
        )

    prepared: list[dict[str, Any]] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="strict")
        source = None
        regions: list[dict[str, Any]] = []
        if source_base is not None:
            source = source_base / str(by_name.get(path.name, {}).get("file") or f"TESTLIB/{path.name}")
            if not source.resolve().is_relative_to(source_base.resolve()):
                raise RuntimeError("N8 上下文源文件越界")
            if source.is_file():
                before = source.read_text(encoding="utf-8", errors="strict").splitlines()
                after = text.splitlines()
                matcher = difflib.SequenceMatcher(a=before, b=after)
                for group in matcher.get_grouped_opcodes(n=N8_REGION_CONTEXT_LINES):
                    _, a, _, c, _ = group[0]
                    _, _, b, _, d = group[-1]
                    regions.append({"before": {"start": a + 1, "end": b,
                                              "text": "\n".join(before[a:b])},
                                    "after": {"start": c + 1, "end": d,
                                              "text": "\n".join(after[c:d])}})
        prepared.append({"path": path, "text": text, "source": source, "regions": regions})

    def _entry(item: dict[str, Any], excerpt: str, mode: str,
               public_regions: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "file": item["path"].name,
            "md5": md5_file(item["path"]),
            "excerpt": excerpt,
            "source_md5": (
                md5_file(item["source"])
                if item["source"] is not None and item["source"].is_file()
                else None
            ),
            "changed_regions": public_regions,
            "coverage": {
                "mode": mode,
                "complete": True,
                "scope": "full_file" if mode == "full_file" else "all_changed_regions",
                "regions": len(public_regions),
            },
        }

    # 每件两种表示各按**真实紧凑序列化**计成本（R4）：包含 coverage/changed_regions 与键名标点，
    # 不做近似、不假定「片段一定更小」。可行成本 = min(全文成本, 片段成本)；受限大文件只有片段成本。
    plans: list[dict[str, Any]] = []
    for item in prepared:
        regions = item["regions"]
        region_excerpt = "\n\n".join(
            f"// lines {region['after']['start']}-{region['after']['end']}\n{region['after']['text']}"
            for region in regions
        ) if regions else None
        public_regions = [
            {"before": region["before"],
             "after": {"start": region["after"]["start"], "end": region["after"]["end"]}}
            for region in regions
        ]
        forced_region = len(item["text"]) > N8_FULL_FILE_CHARS
        full_entry = _entry(item, item["text"], "full_file", public_regions)
        region_entry = (
            _entry(item, region_excerpt, "changed_regions", public_regions)
            if region_excerpt is not None else None
        )
        if forced_region and region_entry is None:
            # 既有 fail-closed：受限大文件必须能定位变更（缺源/无变更 ⇒ 不猜，也不退回全文）。
            raise RuntimeError(
                "N8 上下文无法定位全部变更（缺源文件或没有可定位变更）："
                f"{item['path'].name}（{len(item['text'].encode('utf-8'))} bytes）"
            )
        full_cost = len(AM.encoded(full_entry))
        region_cost = len(AM.encoded(region_entry)) if region_entry is not None else None
        if forced_region:
            min_cost = region_cost
        elif region_cost is None:
            min_cost = full_cost
        else:
            min_cost = min(full_cost, region_cost)
        plans.append(
            {
                "item": item,
                "full_entry": full_entry,
                "region_entry": region_entry,
                "full_cost": full_cost,
                "region_cost": region_cost,
                "forced_region": forced_region,
                "min_cost": min_cost,
            }
        )
    # 数组整体的 `[`、`]` 与 (n-1) 个 `,` 也计入预算：`AM.encoded(list)` 由逐件编码拼接而成，
    # 精确开销为 n + 1（不再用「每条摊销 2 字节」的近似）。
    array_overhead = len(plans) + 1
    total_min = sum(plan["min_cost"] for plan in plans) + array_overhead
    if total_min > budget:
        # 只有「全部候选件的最小可行成本之和」超预算才拒绝；消息定位到具体文件（F16-c）。
        detail = ", ".join(
            f"{plan['item']['path'].name}({plan['min_cost']})" for plan in plans
        )
        raise RuntimeError(
            f"N8 上下文预算不足：全部候选件的最小可行成本合计仍需 {total_min} > {budget} bytes"
            f"（{detail}；不得静默抽样或丢文件）"
        )
    # 选择（R4）：文件名确定性顺序，默认全文；先预留后续件的**可行**成本再决定当前件，
    # 只有全文放不下才降级为片段。并列成本（全文成本 == 片段成本）时选全文：信息更多、
    # `coverage.mode=full_file` 语义更强，且不改变可行性判断。

    used = array_overhead
    full_files = 0
    region_files = 0
    out: list[dict[str, Any]] = []
    for index, plan in enumerate(plans):
        remaining_min = sum(later["min_cost"] for later in plans[index + 1:])
        can_full = (
            not plan["forced_region"]
            and used + plan["full_cost"] + remaining_min <= budget
        )
        entry = plan["full_entry"] if can_full else plan["region_entry"]
        cost = plan["full_cost"] if can_full else plan["region_cost"]
        if entry is None or cost is None:
            # 不可达：上面的最小成本检查保证可行，且受限件必有片段。保留显式失败而非静默跳过。
            raise RuntimeError(
                "N8 上下文预算不足且无法定位变更（缺源文件或没有可定位变更）："
                f"{plan['item']['path'].name}（剩余预算 {max(0, budget - used)} bytes）"
            )
        used += cost
        if can_full:
            full_files += 1
        else:
            region_files += 1
        out.append(entry)
    # 以**真实请求使用的紧凑序列化**复核（`AM.encoded` 与 check_budget 同一实现）。
    used = len(AM.encoded(out))
    if used > budget:
        # 兜底：只在片段确实更便宜时从后往前降级；不得硬拒可行解，也不得把降级变成放大成本。
        for index in range(len(out) - 1, -1, -1):
            if used <= budget:
                break
            plan = plans[index]
            if out[index]["coverage"]["mode"] != "full_file":
                continue
            if plan["region_entry"] is None or plan["region_cost"] >= plan["full_cost"]:
                continue
            out[index] = plan["region_entry"]
            used = len(AM.encoded(out))
            full_files -= 1
            region_files += 1
        if used > budget:
            detail = ", ".join(f"{plan['item']['path'].name}" for plan in plans)
            raise RuntimeError(
                f"N8 上下文预算不足：分片后 {used} > {budget} bytes（{detail}；不得静默抽样）"
            )
    summary = {
        "budget_bytes": budget,
        "used_bytes": used,
        "full_files": full_files,
        "region_files": region_files,
    }
    return out, [path.stem for path in files], summary


def _sandbox_code(ctx: RunCtx, source_root: Path | None = None,
                  applied_cases: list[dict[str, Any]] | None = None
                  ) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """取 N6 施加后的沙箱代码（N8 的复核对象）、目标用例名与分片汇总。"""
    return build_sandbox_cases(
        ctx.run_dir / "sandbox" / "TESTLIB", source_root, applied_cases
    )


def _author_handoff(ctx, data, node):
    try:
        return AH.for_reviewer(ctx, data.get_state('n6_author') or {}, node)
    except (ValueError, OSError) as exc:
        ctx.node_failed(node, message="作者回应来源核验失败", source="framework")
        raise ValueError('author handoff rejected') from exc


async def n8_check(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n8 import run
    return await run(data, AR=AR, _CHECKLIST=_CHECKLIST, _author_handoff=_author_handoff, _cycles_and_limit=_cycles_and_limit, _ensure_case_state=_ensure_case_state, _sandbox_code=_sandbox_code, _set_case_state=_set_case_state, _standin=_standin, ctx_of=ctx_of, run_model_node=run_model_node)






























































































































































# ---------------------------------------------------------------- N10（Host 抽数 + 模型分类）


async def n10_reconcile(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n10 import run
    return await run(data, MP=MP, PENDING_CLASSES=PENDING_CLASSES, _artifact=_artifact, _case_pass_fields=_case_pass_fields, _cases_table=_cases_table, _classification_summary=_classification_summary, _diffs_for_classification=_diffs_for_classification, _per_case_fail_buckets=_per_case_fail_buckets, _persist_pending=_persist_pending, _reconcile_markdown=_reconcile_markdown, _set_case_state=_set_case_state, _write_text=_write_text, counts_text=counts_text, ctx_of=ctx_of, ledger=ledger, run_model_node=run_model_node)


























































































































































































































# ---------------------------------------------------------------- N11（guardian）


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


def _identity_table(host_identity: dict[str, Any]) -> list[dict[str, Any]]:
    """N11 逐用例身份表（P-27）：只投影 Host 四方同值事实，不重做判定。

    字段映射（契约 §3）：`case_md5` = 跑的身份头里的 case md5（`run_md5` 同值，
    `host.evidence` 的 `identity.case_md5` 就是 case 文件指纹）；`audit_md5` = 审的 md5
    （N6 冻结值）；`consistent` = Host 四方同值结论。drill 无真实身份头 ⇒ 空表。
    """
    rows: list[dict[str, Any]] = []
    for item in host_identity.get("cases") or []:
        if not isinstance(item, dict):
            continue
        run_md5 = item.get("run_md5")
        rows.append({
            "case": item.get("case"),
            "run_id": item.get("run_id"),
            "case_md5": run_md5,
            "audit_md5": item.get("reviewed_md5"),
            "run_md5": run_md5,
            "consistent": item.get("consistent"),
        })
    return rows


async def n11_review(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n11 import run
    return await run(data, AR=AR, _author_handoff=_author_handoff, _cycles_and_limit=_cycles_and_limit, _ensure_case_state=_ensure_case_state, _host_identity=_host_identity, _identity_table=_identity_table, _ledger_summary=_ledger_summary, _set_case_state=_set_case_state, _standin=_standin, ctx_of=ctx_of, ledger=ledger, run_model_node=run_model_node)
































































































































































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


def _n12_detail(data_out: dict[str, Any], *, refs: list[str], unresolved: list[str],
                ledger_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """N12 detail 的投影字段（P-28，契约 §3）：引用可解析数 / 未闭环项 / 逐用例状态摘要。

    `refs_parseable_count` = 全部引用 - 不可解析引用（Host 已做过可解析性判定，这里只计数）；
    `cases_summary` 来自本轮用例态台账（N10 写入），不猜"应该是什么态"。
    """
    cases_summary: list[str] = []
    for item in ledger_cases:
        if not isinstance(item, dict) or not item.get("case"):
            continue
        state = item.get("state")
        cases_summary.append(
            f"{item['case']}：{state}" if state else f"{item['case']}：状态未下发"
        )
    return {
        "refs_parseable_count": len(refs) - len(unresolved),
        "open_items": [str(x) for x in (data_out.get("open_items") or [])],
        "cases_summary": cases_summary,
    }


async def n12_report(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n12 import run
    return await run(data, _artifact=_artifact, _compose_n12_markdown=_compose_n12_markdown, _ledger_summary=_ledger_summary, _n12_detail=_n12_detail, _resolve_ref=_resolve_ref, _standin=_standin, _write_text=_write_text, ctx_of=ctx_of, ledger=ledger, run_model_node=run_model_node)

from host import agent_candidate_import as CI
from .host_steps import CANDIDATE_BASELINE_KEY, CANDIDATE_EXECUTION_KEY, CANDIDATE_MANIFEST_KEY, CANDIDATE_ROOT_KEY

# ---------------------------------------------------------------- N6 候选通道（S6/DS-06）


def _candidate_contract_path(case: str) -> str:
    """候选契约路径（G1 冻结口径）：`TESTLIB/<case>.sv`。

    为什么由合同定而不是"扫到什么算什么"：清单键若来自扫描，导入的 `extra_file`（扫描-清单差）
    与 `hash_mismatch`（快照 vs 导入复算）在真机上就恒假；DS-06 的拒绝矩阵会变成空转。
    """
    return "TESTLIB/%s.sv" % case


def _candidate_execution_state(out: dict[str, Any]) -> str:
    """停止确认口径：只有"进程已退出且无 execution_unknown"才给 `stopped`，否则 `unknown`。

    dsh 的 `run_attempt` 只在进程结束且无残留后代后返回；`ExecutionUnknown` 是**抛异常**
    （没有 out）。所以拿到 live out 即"进程已退出"，但仍按口径复核 payload 标记：
    非 live / `model_call_failed` / error 含 `execution_unknown` ⇒ `unknown`
    （**不许**把未知当已停止，DS-05 禁止自动重发）。
    """
    if out.get("mode") != "live":
        return "unknown"
    if out.get("model_call_failed"):
        return "unknown"
    if "execution_unknown" in str(out.get("error") or ""):
        return "unknown"
    return "stopped"


def _sealed_attempt_workspace(ctx: RunCtx, out: dict[str, Any]) -> dict[str, Any] | None:
    """从**已封存**的 attempt 请求记录取 `attempt_workspace`（不读任务文本/客户端 hint）。

    记录不完整/校验失败/无本键 ⇒ None（没有候选通道 ⇒ 一个键都不产出，保持 legacy 路径）。
    """
    ref = out.get("request_ref")
    if not isinstance(ref, str) or not ref:
        return None
    try:
        record = AM.verify_attempt((ctx.run_dir / ref).parent)
    except (OSError, ValueError, KeyError):
        return None
    workspace = record["request"].get("attempt_workspace")
    return workspace if isinstance(workspace, dict) else None


def _candidate_root_from_workspace(ctx: RunCtx, workspace: dict[str, Any]) -> Path | None:
    """布局 `candidate`（封存记录里相对 run_dir）⇒ 绝对路径；越界/缺失/非目录 ⇒ None。"""
    rel = workspace.get("candidate")
    if not isinstance(rel, str) or not rel:
        return None
    try:
        root = (ctx.run_dir / rel).resolve()
    except OSError:
        return None
    run_root = ctx.run_dir.resolve()
    if run_root != root and run_root not in root.parents:
        return None
    return root if root.is_dir() else None


def _pin_candidate_baseline(data: Any, targets: list[dict[str, Any]]) -> dict[str, str]:
    """**起 prompt 前** pin 源件 md5（判源漂移 R16）：模型看到的是这份源件，之后变了就是漂移。

    取不到 `repo_root` 或缺件 ⇒ 跳过该件（不猜、不补）；缺项的后果是导入判 `source_drift`
    （无法证明无漂移 ⇒ 拒），不是静默放行。
    """
    try:
        repo_root = Path(data.require_resource("repo_root"))
    except (KeyError, TypeError):
        return {}
    pinned: dict[str, str] = {}
    for target in targets:
        case = str(target.get("case") or "")
        if not case:
            continue
        rel = _candidate_contract_path(case)
        source = repo_root / str(target.get("file") or rel)
        if source.is_file() and not source.is_symlink():
            pinned[rel] = md5_file(source)
    return pinned


def _workspace_hint(ctx: RunCtx, targets: list[dict[str, Any]]) -> dict[str, Any]:
    """本 attempt 工作区的**绝对路径**与**基线源件位置**（Host 已知事实）。

    为什么给：S6 真机前两次失败都在"模型不知道工作区/拿不到基线全文 ⇒ 去扫宿主机 FS"。
    路径与 `model_request.run_attempt` 的分配**同源**：`AC.next_attempt`（首个空位预测，
    Host 串行保证预测=实际；不一致时 model_request 已显式失败）+ `A.workspace_root`
    （布局唯一实现）；`source_files` 与 `model_request._attempt_sources` 的落点同源
    （`input/TESTLIB/<basename>`，`stage_sources` 只保留文件名）。本函数只读、不写盘。
    """
    from host import agent_control as AC
    from host.agent_backends import dsh_assets as A

    sequence = AC.next_attempt(ctx.run_dir, "N6")
    layout = A.AttemptLayout.under(A.workspace_root(ctx.run_dir, "N6", sequence))
    sources = ["input/TESTLIB/%s" % Path(str(target.get("file") or "")).name
               for target in targets if str(target.get("file") or "").strip()]
    return {
        "cwd": str(layout.work),
        "candidate": str(layout.candidate),
        "input": str(layout.input_dir),
        "source_files": sources,
        "rule": ("cwd 是你的工作目录；基线源件在 source_files（相对工作区根，只读）；"
                 "候选 = 该源件的整份内容 + 你的 edits，写到 candidate/TESTLIB/<case>.sv；"
                 "材料不足写 notes，不要扫描宿主机文件系统"),
    }


def _attach_candidate_channel(ctx: RunCtx, out: dict[str, Any], targets: list[dict[str, Any]],
                              baseline_pin: dict[str, str]) -> None:
    """S6/DS-06：dsh 隔离工作区存在时，把四键写进 N6 输出（**要么全给、要么全不给**）。

    - 键名与 `host_steps.candidate_plan` 同一组常量（不写第二份键名）；
    - `candidate_manifest`：键来自**合同**（`TESTLIB/<case>.sv`）、值来自**停止后快照**；
    - `baseline`：起 prompt 前 pin 的源件 md5（缺项 ⇒ 导入判源漂移，不静默放行）；
    - `execution_state`：只在确认停止时 `stopped`，否则 `unknown`。
    无工作区（agently/drill/旧记录/记录校验失败）⇒ 一个键都不加（legacy 路径，不半给）。
    """
    workspace = _sealed_attempt_workspace(ctx, out)
    if workspace is None or not targets:
        return
    candidate_root = _candidate_root_from_workspace(ctx, workspace)
    if candidate_root is None:
        return
    expected = [_candidate_contract_path(str(target.get("case")))
                for target in targets if target.get("case")]
    out[CANDIDATE_ROOT_KEY] = str(candidate_root)
    out[CANDIDATE_MANIFEST_KEY] = CI.snapshot_candidate_manifest(candidate_root, expected)
    out[CANDIDATE_BASELINE_KEY] = dict(baseline_pin)
    out[CANDIDATE_EXECUTION_KEY] = _candidate_execution_state(out)
