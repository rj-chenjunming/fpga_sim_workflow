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
from host import agent_candidate_import as CI
from host import agent_memory as AM
from host import agent_handoff as AH
from host import agent_review as AR

from ..context import RunCtx, ctx_of
from .host_steps import (
    CANDIDATE_BASELINE_KEY, CANDIDATE_EXECUTION_KEY, CANDIDATE_MANIFEST_KEY, CANDIDATE_ROOT_KEY,
    md5_file, run_kb_tool,
)

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


async def n6_author(data: Any) -> dict[str, Any]:
    """N6 修订/补充（模型节点）：只出**结构化 edits**，不自己写文件。

    写权边界：Host 的 `n6_apply` 只写 `run_dir/sandbox/TESTLIB/`，不写冻结的 `TESTLIB/`。
    **I7**：本节点不再自增 `n6_n8_cycles`（返工预算只在 N8 判 rework 时消耗）。
    **S6/DS-06 候选通道**：dsh attempt 隔离工作区存在时，输出带四键（`candidate_root` /
    `candidate_manifest` / `baseline` / `execution_state`），供 `n6_apply` 先导入再施加；
    无工作区（agently/drill/旧记录）⇒ 四键**全不给**（legacy 路径），不半给、不降级。
    """
    ctx = ctx_of(data)
    ctx.node_started("N6")
    cycles, limit = _cycles_and_limit(ctx, data)
    n5 = data.get_state("n5_impact") or {}
    n8 = data.get_state("n8_check") or {}
    n11 = data.get_state("n11_review") or {}
    cases = list(n5.get("must_change_cases") or [])

    try:
        rework_handoff = AR.for_author(ctx, data.get_state('n6_author') or {}, n8, n11)
    except (ValueError, OSError) as exc:
        ctx.node_failed("N6", message="返工交接来源核验失败", source="framework")
        raise ValueError("N6 handoff provenance rejected") from exc
    rework_reasons = [item['text'] for item in rework_handoff['issues']]

    targets = build_n6_targets(ctx, data)
    rework_assignment = AH.assignment(rework_handoff, targets)
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
        "rework_handoff": rework_handoff,
        "rework_assignment": rework_assignment,
        "must_change_count": n5.get("must_change_count"),
        "rule": ("只针对 targets 的用例；edits.old 必须逐字取自 targets[].excerpt.text 并且唯一；"
                 "拿不准写进 notes，不要猜。"),
        # S6/DS-06：写权只在 attempt 隔离工作区的候选目录（模型不能写共享 TESTLIB/沙箱）
        "write_scope_rule": ("只写本次 attempt 的 candidate/TESTLIB/<case>.sv（与 work/ 同级）；"
                             "Host 在确认停止后导入候选并落沙箱，模型不得声称已改共享 TESTLIB/沙箱。"),
        # S6-DS06-02：把 Host 已知的工作区绝对路径 + 基线源件位置直接给模型（前两轮实测：
        # 模型去 `find / -name TESTLIB` 找材料，120/300 s 内没写候选）。只给路径，不放宽判据。
        "workspace": _workspace_hint(ctx, targets),
    }
    # S6/DS-06：候选基线必须在**起 prompt 之前** pin（模型看到的源件；之后变了就是漂移）。
    # 只有 real 会产生 attempt 隔离工作区（dsh）；drill/standin 不产生候选通道。
    baseline_pin = _pin_candidate_baseline(data, targets) if ctx.mode == "real" else {}
    out = await run_model_node(
        ctx, "N6", prompt_key="n6_author", input_data=input_data,
        offered={"cases": set(cases) | {t["case"] for t in targets},
                 "rework_assignment": rework_assignment},
    )
    if out["mode"] == "standin":
        out["data"] = _standin(ctx, "N6", "N6_author_note.md",
                               extra={"cycle": cycles + 1,
                                      "targets": [t["case"] for t in targets],
                                      "write_scope": str(ctx.run_dir / "sandbox" / "TESTLIB")})
    elif (out.get("validation") or {}).get("ok") is not True:
        # P-25：观测点/edits 的 Host 校验失败必须**立刻显式失败**（不得静默继续到 N6_apply），
        # 与 N3/N8/N11/N12 的 fail-closed 一致；错误里带缺哪个用例 / 哪个 marker。
        problems = (out.get("validation") or {}).get("problems") or ["模型输出解析/校验失败"]
        ctx.node_failed("N6", message=f"N6 修订输出校验失败（fail-closed）：{problems[:3]}")
        raise RuntimeError(f"N6：修订输出未通过 Host 校验（含观测点约束）：{problems[:5]}")
    # S6/DS-06：实验证通过后接候选通道（四键要么全给、要么全不给）；由 n6_apply 消费。
    _attach_candidate_channel(ctx, out, targets, baseline_pin)
    await data.async_set_state("n6_author", out)
    validation_ok = (out.get("validation") or {}).get("ok")
    source = "model_live" if out["mode"] == "live" else "model_standin"
    # P-20：逐用例修改摘要由模型输出**确定性投影**（Host 不猜"改了哪一处"）；
    # 与 N6_apply 的清单同源（同一函数），没有模型输出时显式 None。
    case_edits = case_edits_from_output(out.get("data") if isinstance(out.get("data"), dict) else None)
    observation_points = _observation_points(
        out.get("data") if isinstance(out.get("data"), dict) else None)
    ctx.node_finished("N6", status=out["mode"],
                      detail={"mode": out["mode"], "cycle": cycles + 1,
                              "targets": len(targets),
                              "validation_ok": validation_ok,
                              "source": source,
                              "case_edits": case_edits,
                              "case_edits_source": "n6_output",
                              "observation_points": observation_points,
                              "summary": (
                                  f"N6：第 {cycles + 1} 轮修订，目标 {len(targets)} 个用例，"
                                  "输出校验"
                                  + ("通过" if validation_ok is True
                                     else "未通过" if validation_ok is False else "未下发")
                                  + f"（{out['mode']}）"
                              )})
    return out


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
    """N8 静态复核（模型节点）→ 显式分叉到 N6（回边）/ N9 / N13（升级）。

    **fail-closed（#1/C3）**：模型调用失败、输出校验失败、verdict 缺失 ⇒ node_failed；
    绝不再 `verdict = ... or "pass"`。
    """
    ctx = ctx_of(data)
    ctx.node_started("N8")
    cycles, limit = _cycles_and_limit(ctx, data)
    n8_prev = data.get_state("n8_check") or {}
    n6_applied = data.get_state("n6_applied") or {}

    try:
        sandbox_cases, sandbox_names, sandbox_coverage = _sandbox_code(
            ctx, Path(data.require_resource("repo_root")), n6_applied.get("cases") or [])
    except RuntimeError as exc:
        # 闭锁必须留下显式 node_failed，避免 run.error 退化成泛化信息（复核残余项）。
        ctx.node_failed("N8", message=str(exc))
        raise
    revision_points: list[dict[str, Any]] = []
    for target in (data.get_state("n6_targets") or {}).get("targets") or []:
        revision_points.extend(target.get("revision_points") or [])

    applied_edits = [
        {"case": c.get("case"), "file": c.get("file"), "edits": c.get("edits") or []}
        for c in (n6_applied.get("cases") or []) if isinstance(c, dict)
    ]
    input_data = {
        "run_id": ctx.run_id,
        "cycle": cycles,
        "sandbox_cases": sandbox_cases,
        "coverage_summary": sandbox_coverage,
        "revision_points": revision_points,
        "applied_edits": applied_edits,
        "author_handoff": _author_handoff(ctx, data, 'N8'),
        "checklist": _CHECKLIST,
        "rework_reasons": [str(f) for f in (n8_prev.get("data") or {}).get("must_fix", [])]
        if isinstance(n8_prev.get("data"), dict) else [],
        "rule": ("verdict=rework 必须给逐条可核依据；只依据本 input 的材料，不得假设未提供的文件内容。"
                 "sandbox_cases[].coverage.mode=changed_regions 时只对这些变更区域内的 touched 行负责，"
                 "coverage_summary 说明全文/片段各多少件。"),
    }
    input_data['review_assignment'] = AR.prepare('N8', input_data)
    out = await run_model_node(ctx, "N8", prompt_key="n8_check",
                               input_data=input_data,
                               offered={"cases": set(sandbox_names), 'review_context': input_data})
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
    # P-23：模型实际检查项数与必须修改项数（Host 只做**计数**，判据仍是模型输出+校验）。
    # 没有 findings/must_fix（standin/drill 替身）⇒ 显式 None，不拿 0 冒充"检查了 0 项"。
    findings = data_out.get("findings")
    must_fix = data_out.get("must_fix")
    check_count = len(findings) if isinstance(findings, list) else None
    must_fix_count = len(must_fix) if isinstance(must_fix, list) else None
    if verdict not in ("pass", "rework"):
        # 显式缺失/非法 ⇒ 失败（C3：不得默认 pass）
        ctx.node_failed("N8", message=f"N8 verdict 缺失/非法：{verdict!r}")
        raise RuntimeError(f"N8：verdict 缺失或非法（{verdict!r}）⇒ 不得放行到 N9")

    cases = [str(c.get("case")) for c in (n6_applied.get("cases") or []) if c.get("case")] or sandbox_names
    n8_source = "model_live" if out["mode"] == "live" else "model_standin"
    # drill 的 N8 是**替身复核**（夹具 check_C），不是本轮真实证据；不写本轮用例态台账。
    # 理由：I2 的 G2 前置把"本轮写入的待验"当阻断，drill 全跑证据必然不合格，
    # 若替身复核也写「已修订待验」就会把 accept_v1 的 drill 永久堵在 G2（Lead/WS-L 已确认）。
    write_ledger = ctx.mode == "real"
    if write_ledger:
        _ensure_case_state(ctx)
    else:
        ctx.event("warning", node="N8", status="drill_ledger_skipped",
                  detail={"rule": "drill 替身复核不写用例态台账；I2 以 real 证据为准"})
    if verdict == 'rework' and not write_ledger:
        out.update(cycle=cycles, limit=limit, escalated=True)
        await data.async_set_state('n8_check', out)
        ctx.node_finished('N8', status='escalated', detail={
            'verdict': 'rework', 'cycle': cycles, 'limit': limit, 'source': n8_source,
            'escalated': True,
            'summary': 'N8：drill 静态复核退回，升级人工裁决；无真实返工计数，不自动回环'})
        await data.async_emit('N8_ESCALATE', out)
        return out
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
                                      "check_count": check_count,
                                      "must_fix_count": must_fix_count,
                                      "reason": "N8 返工超限 ⇒ 升级 N13 人工裁决",
                                      "source": n8_source,
                                      "summary": (f"N8：静态复核 rework 第 {new_cycles} 次，"
                                                  f"已达上限 {limit} ⇒ 升级 N13 人工裁决"
                                                  f"（{out['mode']}）")})
            await data.async_emit("N8_ESCALATE", out)
            return out
        ctx.node_finished("N8", status="rework",
                          detail={"verdict": "rework", "cycle": new_cycles, "limit": limit,
                                  "check_count": check_count,
                                  "must_fix_count": must_fix_count,
                                  "source": n8_source,
                                  "summary": (f"N8：静态复核 rework（第 {new_cycles} 次，"
                                              f"上限 {limit}）⇒ 回 N6 返工（{out['mode']}）")})
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
    ctx.node_finished("N8", status=out["mode"],
                      detail={"verdict": "pass", "cycle": cycles, "limit": limit,
                              "check_count": check_count,
                              "must_fix_count": must_fix_count,
                              "source": n8_source,
                              "summary": (f"N8：静态复核 pass（第 {cycles} 轮，上限 {limit}，"
                                          f"{len(cases)} 个用例；{out['mode']}）")})
    await data.async_emit("N8_PASS", out)
    return out


# ---------------------------------------------------------------- N10（Host 抽数 + 模型分类）


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
                          detail={"both_zero": out["both_zero"],
                                  "cases_table": _cases_table(out.get("cases")),
                                  "classification": _classification_summary(
                                      bucket_count=fb.get("bucket_count"), items=None),
                                  "source": ("model_live" if cls_out["mode"] == "live"
                                             else "model_standin"),
                                  "summary": (
                                      f"N10：{len(out['target_cases'])} 个用例对账，"
                                      f"{counts_text(out.get('counts'))}，"
                                      f"both_zero={out['both_zero']}（{cls_out['mode']}）"
                                  )},
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
            fields = _case_pass_fields(ctx, case, item, n7, n9, ledger)
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
                              "pending": len(pending_items),
                              # P-26：逐用例表与失败分类摘要（只投影既有证据/模型输出）
                              "cases_table": _cases_table(cases),
                              "classification": _classification_summary(
                                  bucket_count=len(fb.get("buckets") or []),
                                  items=cls_data.get("items")),
                              "source": ("model_live" if cls_out["mode"] == "live"
                                         else "model_standin"),
                              "summary": (
                                  f"N10：{len(target_cases)} 个用例对账，"
                                  f"{counts_text(n9.get('counts'))}，"
                                  f"verdict_passed={(n9.get('verdict') or {}).get('passed')}，"
                                  f"待裁决 {len(pending_items)} 项（{cls_out['mode']}）"
                              )},
                      refs=[str(reconcile_path)] + [str((cases.get(c) or {}).get("path") or "")
                                                    for c in target_cases][:4])
    return out


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
        "author_handoff": _author_handoff(ctx, data, 'N11'),
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
    input_data['review_assignment'] = AR.prepare('N11', input_data)
    out = await run_model_node(ctx, "N11", prompt_key="n11_review", input_data=input_data,
                               offered={"counts": counts, 'review_context': input_data})
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
    # P-27：逐用例身份表 / 未闭环项 / 返工请求条数（三个分支共用同一投影，不各算一套）
    identity_table = _identity_table(host_identity)
    unclosed = [str(x) for x in (data_out.get("caveats") or [])]
    rework_requests_count = len(rework_requests)
    await data.async_set_state("n11_review", out)

    n11_source = "model_live" if out["mode"] == "live" else "model_standin"
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
                        "identity_table": identity_table,
                        "unclosed": unclosed,
                        "rework_requests_count": rework_requests_count,
                        "reason": "N11 证据守护返工超限 ⇒ 升级 N13 人工裁决",
                        "source": n11_source,
                        "summary": (f"N11：证据链 broken 第 {new_cycles} 次，已达上限 {limit}"
                                    f" ⇒ 升级 N13 人工裁决（{out['mode']}）")},
            )
            await data.async_emit("N11_ESCALATE", out)
            return out
        ctx.node_finished("N11", status="broken",
                          detail={"chain": "broken", "host_consistent": host_consistent,
                                  "rework": len(rework_requests), "cycle": new_cycles,
                                  "limit": limit,
                                  "identity_table": identity_table,
                                  "unclosed": unclosed,
                                  "rework_requests_count": rework_requests_count,
                                  "source": n11_source,
                                  "summary": (f"N11：证据链 broken（第 {new_cycles} 次，"
                                              f"上限 {limit}；Host 身份四方同值"
                                              f"{'成立' if host_consistent else '不成立'}）"
                                              f"⇒ 回 N6 返工，返工请求 "
                                              f"{len(rework_requests)} 条（{out['mode']}）")})
        await data.async_emit("N11_REWORK", out)
        return out
    ctx.node_finished("N11", status="intact",
                      detail={"chain": "intact", "host_consistent": host_consistent,
                              "identity_table": identity_table,
                              "unclosed": unclosed,
                              "rework_requests_count": rework_requests_count,
                              "source": n11_source,
                              "summary": (f"N11：证据链 intact（Host 身份四方同值"
                                          f"{'成立' if host_consistent else '不成立'}，"
                                          f"返工请求 {len(rework_requests)} 条；"
                                          f"{out['mode']}）")})
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
    # §10.4：detail 内的计数改名为 `ref_count`（`refs` 是**事件顶层**字段，同名会误导消费方）。
    ctx.node_finished("N12", status=out["mode"],
                      detail={"mode": out["mode"],
                              "claimed_verdict": data_out.get("claimed_verdict"),
                              "ref_count": len(refs),
                              **_n12_detail(data_out, refs=refs, unresolved=unresolved,
                                            ledger_cases=ledger(ctx).get("cases") or []),
                              "source": ("model_live" if out["mode"] == "live"
                                         else "model_standin"),
                              "summary": (f"N12：报告 claimed_verdict="
                                          f"{data_out.get('claimed_verdict')}，"
                                          f"引用 {len(refs)} 条（不可解析 {len(unresolved)} 条）；"
                                          f"mode={out['mode']}")},
                      refs=[str(report_path)] + [str(_resolve_ref(ctx, r)) for r in refs][:4])
    return out
