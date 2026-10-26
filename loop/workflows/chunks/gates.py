"""三道人工闸门（N4 / N13 / N14）。

契约（spec §5）：
- **中断**归 TriggerFlow（`pause_for` 是 durable graph interrupt）；
- **决策权威**归 `kb/tools/gate.py`（gate_state + `history[]` + `gates.sha256` + `anchor`）；
- **UI 只做传输**，不持有"已通过"。

`resume_to="self"` 让本 chunk 在恢复时**重新进入**并读到 `data.resume.value`，
从而显式分叉到下游事件 —— 契合"恢复行为必须落在下游 chunk / 显式 resume 事件里，
不得依赖挂起的 Python 帧"。

**枚举不在这里手写**：合法决策一律取自 `host.gate_authority`（背后是 `kb_lib`）。
自造枚举已实测踩坑（本层曾把 G3 写成 `full_regression`，而权威是 `full_now`）。

**本轮修复**：
- B4/C1：`require-signed` 必须带**本门实际决策**（`--expect`），否则 `ignored/rework`
  在签后被默认期望打回、执行被框架置 FAILED，账本留孤儿签名；
- A1/I1：G1 放行前读 N2 未决条目（real 必须逐条 `entry_decisions`；drill 可用
  「reason 即逐条核对 attestation」）；A2：ignored/disputed/rework 强制 reason；
- A3/I2：G2 放行前读用例态台账，**本轮**存在「已修订待验」⇒ 拒绝（历史/夹具条目不阻断）；
- C6/I7：G2=rework 自增**独立**计数 `g2_rework_cycles`（N6↔N8 计数仍在 case_state 台账）；
- A23：闸门材料补齐三闸门各自输入（差异清单/冲突快照/报告+用例态+计数/评估结论+refs）；
- B9：blockers 按阶段裁剪（G1 不评 I3）；B5-A：`standin_model_nodes` 由实际 mode 投影；
- I17：权威枚举漂移在**启动自检**里炸（不再等运行到 `BRANCH_EVENTS[gate][decision]` KeyError）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from host import gate_authority as GA
from services import contracts

from ..context import RunCtx, ctx_of


class GatePreconditionFailed(PermissionError):
    """闸门前置不满足（I1 / I4 / I6 / I7）。"""


#: 决策 → 下游事件名。这张表是**本层唯一自有的部分**（事件名属于本层拓扑）。
BRANCH_EVENTS: dict[str, dict[str, str]] = {
    "G1_diff_confirm": {
        "confirmed": "G1_CONFIRMED",
        "ignored": "G1_IGNORED",
        "disputed": "G1_DISPUTED",
    },
    "G2_report_accept": {"accept": "G2_ACCEPT", "rework": "G2_REWORK"},
    "G3_regression_decision": {
        "full_now": "G3_FULL_NOW",
        "subset_only": "G3_SUBSET_ONLY",
        "milestone_only": "G3_MILESTONE",
        "defer": "G3_DEFER",
    },
}

#: 闸门 → 节点名（纯展示元数据）
GATE_NODE = {"G1_diff_confirm": "N4", "G2_report_accept": "N13", "G3_regression_decision": "N14"}

#: 闸门 → 材料阶段（与 contracts.GATE_STAGE 同一口径）
GATE_STAGE = contracts.GATE_STAGE

#: 这些决策必须给出理由（A2：忽略/有疑义/返工不能无理由落账）。
#: 集合本体在 `services.contracts`（与选项下发同源，红线 8）；此处仅保留旧名做别名。
REASON_REQUIRED = contracts.REASON_REQUIRED_DECISIONS

#: 条目级处置的合法值（与闸门单选分支同名，便于与 BRANCH_EVENTS 对齐）。
ENTRY_DECISIONS = frozenset({"confirmed", "ignored", "disputed"})

#: 逐条处置落账目录（实施计划 §2.5；S3 只读消费，路径 `run_dir/decisions/<gate>.json`）。
DECISIONS_DIR = "decisions"

#: 闸门 → 白话名称（只用于 HALT 终止原因；决策中文仍取自权威 `human_readable`）。
GATE_LABEL_CN = {
    "G1_diff_confirm": "闸门1（差异确认）",
    "G2_report_accept": "闸门2（报告验收）",
    "G3_regression_decision": "闸门3（回归决策）",
}


def _ledger_entries(entries: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """落账只写契约字段（decision / reason），不把内部附加键（source 等）写进账本。"""
    out: dict[str, dict[str, Any]] = {}
    for entry_id, value in (entries or {}).items():
        item = value if isinstance(value, dict) else {"decision": value, "reason": None}
        out[str(entry_id)] = {"decision": item.get("decision"),
                              "reason": item.get("reason")}
    return out


def _ledger_hard_block(blocks: Any) -> list[dict[str, Any]]:
    """落账白名单：只写 `code/title/message` 三个契约字段（R3-04，不多写内部键）。"""
    out: list[dict[str, Any]] = []
    for block in (blocks or []):
        if isinstance(block, dict):
            out.append({"code": block.get("code"), "title": block.get("title"),
                        "message": block.get("message")})
    return out


def _material_hard_block(data: Any, gate: str) -> list[dict[str, Any]]:
    """本门**开启时**材料里的硬阻断快照（`gate_material::<gate>`，R3-04）。

    只取契约三字段。材料缺失/不可读 ⇒ `[]`（"材料里没有"就是空列表）；
    绝不拿**现在**的 blockers 冒充"当时的阻断项"（那是两回事）。
    """
    try:
        material = data.get_state(f"gate_material::{gate}")
    except Exception:  # pragma: no cover - state 读取本身失败也不得编造
        return []
    if not isinstance(material, dict):
        return []
    return _ledger_hard_block(material.get("hard_block"))


def append_decision_ledger(ctx: RunCtx, gate: str, record: dict[str, Any]) -> Path:
    """把本次闸门的**逐条处置**追加到 `run_dir/decisions/<gate>.json`（只增不改）。

    形状见实施计划 §2.5；`decided_at` 取权威 `gates.json` 的 `signed_at`（**不新取墙钟**，
    时间仍是单一注入入口）。落账件是 S3「已决策态逐条处置」的唯一来源：
    损坏/形状不对必须**显式失败**，不得静默覆盖（那会抹掉已签闸门的处置记录）。
    """
    path = ctx.run_dir / DECISIONS_DIR / f"{gate}.json"
    records: list[dict[str, Any]] = []
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"闸门处置落账不可解析：{path}（{exc}）") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("records"), list):
            raise RuntimeError(f"闸门处置落账形状非法：{path}（缺 records 列表）")
        records = list(doc["records"])
    records.append({
        "cycle": record.get("cycle"),
        "decided_at": record.get("signed_at"),
        "decision": record.get("decision"),
        "actor": record.get("actor"),
        "reason": record.get("reason"),
        "entries": _ledger_entries(record.get("entries")),
        # R3-04（P-15）：把"签署时**当时**的硬阻断"快照进落账 —— 已决策态面板只能信这份，
        # 旧 run 没有该键 ⇒ 读侧明说"未留存"，不拿现在的 blockers 冒充当时。
        "hard_block": _ledger_hard_block(record.get("hard_block")),
    })
    payload = {"schema": "loop/gate_entries", "gate": gate,
               "run_id": ctx.run_id, "records": records}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def validate_branches() -> dict[str, list[str]]:
    """自检：本层的事件表必须与权威的可提交决策**逐值一致**。

    返回 `{gate: [问题...]}`；非空即表示拓扑落后于权威（不得静默）。
    """
    problems: dict[str, list[str]] = {}
    try:
        for gate in GA.gate_ids():
            allowed = set(GA.actionable_decisions(gate))
            mapped = set(BRANCH_EVENTS.get(gate, {}))
            missing = sorted(allowed - mapped)
            extra = sorted(mapped - allowed)
            if missing or extra:
                problems[gate] = [f"权威有但本层无事件: {missing}", f"本层有但权威无: {extra}"]
    except GA.GateAuthorityUnavailable as exc:  # pragma: no cover
        problems["__authority__"] = [str(exc)]
    return problems


BRANCH_DRIFT = validate_branches()


def assert_topology_matches_authority() -> None:
    """I17：**启动自检**。权威枚举漂移 ⇒ 立即炸，而不是等运行到 KeyError 才楔死。

    在 `main_flow` 导入时调用（拓扑在这里定义，漂移就该在加载拓扑时暴露）。
    """
    if BRANCH_DRIFT:
        raise RuntimeError(
            "闸门事件表与权威枚举不一致（spec §5.7 启动自检）："
            f"{BRANCH_DRIFT}；请先修 BRANCH_EVENTS 或权威，不得带漂移启动。"
        )


def _counts_for(data: Any) -> dict[str, Any] | None:
    r = data.get_state("n10_reconcile") or data.get_state("n9_result")
    if isinstance(r, dict) and r.get("counts"):
        return r["counts"]
    return None


def _cycles_view(ctx: RunCtx, data: Any) -> dict[str, Any]:
    """I7 计数读模型：N6↔N8 取 case_state 台账；G2 返工取 execution state。

    两个计数**不共用预算**（C6）：N6↔N8 由 N8 判定写入台账，G2 返工由本层在
    G2=rework 恢复时自增。host 侧同时把快照写到 `<run_dir>/rework_cycles.json`，
    供不持有 execution 的投影（`services/contracts.py`）读到同一份数字。
    """
    state_n6 = int(data.get_state("n6_n8_cycles") or 0)
    state_g2 = int(data.get_state("g2_rework_cycles") or 0)
    file_view = contracts.rework_counts(ctx.run_dir, extra={"g2_rework_cycles": state_g2})
    n6 = max(state_n6, int(file_view.get("n6_n8_cycles") or 0))
    g2 = max(state_g2, int(file_view.get("g2_rework_cycles") or 0))
    limit = int(data.get_state("rework_limit") or file_view.get("limit") or contracts.REWORK_LIMIT_DEFAULT)
    return {"n6_n8_cycles": n6, "g2_rework_cycles": g2, "limit": limit,
            "source": file_view.get("source"), "case_state_source": file_view.get("case_state_source")}


def _persist_cycles(ctx: RunCtx, cycles: dict[str, Any]) -> None:
    """把分离计数快照写到 run 目录（host 侧唯一写者；投影只读它）。"""
    path = ctx.run_dir / "rework_cycles.json"
    try:
        path.write_text(json.dumps(cycles, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:  # pragma: no cover - 磁盘异常不阻断闸门
        return


def _cycle(data: Any, gate: str, ctx: RunCtx | None = None) -> int | str:
    """中断 id 带上返工轮次，避免回边后与已消费的中断撞 id。

    G2 的轮次 = `n6_n8_cycles` + `g2_rework_cycles`：N8 的 rework 与人工 G2 返工
    **各走一条回边**，只用一个计数时第二次 G2 的 interrupt id 会重复 ⇒ resume 请求
    被去重逻辑静默拒绝，run 永久停在 G2（B4 同类楔死）。
    """
    if gate != "G2_report_accept":
        return 0
    if ctx is not None:
        cycles = _cycles_view(ctx, data)
        return f"{cycles['n6_n8_cycles']}-{cycles['g2_rework_cycles']}"
    n6 = int(data.get_state("n6_n8_cycles") or 0)
    g2 = int(data.get_state("g2_rework_cycles") or 0)
    return f"{n6}-{g2}"


def decision_options(
    gate: str,
    *,
    claimed_verdict: str | None = None,
    mode: str | None = None,
    unresolved_count: Any = None,
) -> list[dict[str, Any]]:
    """操作台的决策按钮**由服务端给出**，来源是权威 —— 前端因此无从漂移。

    R3（2026-10-26）：实现委托给 `contracts.gate_decision_options()`，与运行视图的
    `gate_options` 及 `precheck_decision` 共用同一理由判据（红线 8）。
    `mode` / `unresolved_count` 承载 drill G1 attestation 那条规则（独立复核条件 1）。
    """
    return contracts.gate_decision_options(
        gate, claimed_verdict=claimed_verdict, mode=mode, unresolved_count=unresolved_count
    )


def authority_record(ctx: RunCtx, gate: str) -> dict[str, Any]:
    """本门在权威账本里的那一条（signed_at / artifacts / note）。

    `host.gate_authority.authority_view()` 是只读投影，刻意不带 artifacts 正文；
    这里直接读 `gates.json` 拿签署绑定的证据指纹（A17），缺失一律空、不猜。
    """
    try:
        doc = json.loads((ctx.run_dir / "gates.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    item = ((doc.get("gates") or {}).get(gate) or {})
    return dict(item) if isinstance(item, dict) else {}


def human_signed_flag(ctx: RunCtx, gate: str) -> bool | None:
    """权威 `gates.json` 里的 `human_signed`（**只读**；缺失/不可解析 ⇒ None，不猜）。

    红线：`human_signed` 只在 `actor_kind="human"` 时为真，唯一凭据是
    `gates.json` + `gates.sha256` 锚（AGENTS.md §5 第 5 条）。事件流里的 actor 是自报字符串，
    不能当签署凭据。
    """
    try:
        doc = json.loads((ctx.run_dir / "gates.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    item = ((doc.get("gates") or {}).get(gate) or {})
    value = item.get("human_signed")
    return value if isinstance(value, bool) else None


def gate_artifacts(run_dir: Path, gate: str) -> list[str]:
    """闸门签署时绑定的证据指纹（A17）：`<相对路径> md5=<...>`。

    只列**此刻真实存在**的产物；不存在的件不写进来（不编造证据）。
    路径取相对 run 目录，审计时按 run 目录可回指。
    """
    names = {
        "G1_diff_confirm": ("n2_diff.json", "n3_digest.md"),
        "G2_report_accept": ("n12_report.md", "reconcile.md", "n9_result.json", "check_C.md"),
        "G3_regression_decision": ("n12_report.md", "n11_review.json"),
    }.get(gate, ())
    out: list[str] = []
    rd = Path(run_dir)
    for name in names:
        path = rd / name
        if not path.is_file():
            continue
        try:
            digest = hashlib.md5(path.read_bytes()).hexdigest()
        except OSError:  # pragma: no cover
            continue
        out.append(f"{name} md5={digest}")
    evidence = rd / "evidence"
    if gate in ("G2_report_accept", "G3_regression_decision") and evidence.is_dir():
        logs = sorted(p for p in evidence.glob("*.log") if not p.name.endswith("_guard.log"))
        for path in logs[:2]:
            try:
                digest = hashlib.md5(path.read_bytes()).hexdigest()
            except OSError:  # pragma: no cover
                continue
            out.append(f"evidence/{path.name} md5={digest}")
    return out


def normalize_entry_decisions(
    *,
    gate: str,
    decision: str,
    entry_decisions: dict[str, Any] | None,
    diff: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """校验并归一「逐条处置」（A1）。

    - 覆盖：给 `entry_decisions` 时**必须覆盖全部差异条目**（不能只挑自己想处理的）；
    - 取值：ENTRY_DECISIONS（confirmed/ignored/disputed）；
    - 理由：ignored/disputed 必须带理由；
    - 一致性：逐条处置与闸门单选分支必须一致（有 disputed ⇒ 整门 disputed；
      否则有 ignored ⇒ 整门 ignored；否则 confirmed）。
    返回 `{entry_id: {"decision":..., "reason":...}}`。
    """
    entries = diff.get("entries") or []
    ids = [str(e.get("entry_id")) for e in entries if e.get("entry_id")]
    if not entry_decisions:
        return {eid: {"decision": decision, "reason": None} for eid in ids}
    normalized: dict[str, dict[str, Any]] = {}
    unknown = sorted(set(entry_decisions) - set(ids))
    if unknown:
        raise GatePreconditionFailed(
            f"I1：entry_decisions 含未知条目 {unknown}；本轮差异条目 = {ids}"
        )
    missing = sorted(set(ids) - set(entry_decisions))
    if missing:
        raise GatePreconditionFailed(
            f"I1：entry_decisions 未覆盖全部差异条目（缺 {missing}）⇒ 不得放行。"
        )
    for eid, raw in entry_decisions.items():
        if isinstance(raw, dict):
            value = str(raw.get("decision") or "")
            reason = raw.get("reason")
        else:
            value, reason = str(raw), None
        if value not in ENTRY_DECISIONS:
            raise GatePreconditionFailed(
                f"I1：条目 {eid} 的处置 {value!r} 非法；合法值 = {sorted(ENTRY_DECISIONS)}"
            )
        if value in ("ignored", "disputed") and not (isinstance(reason, str) and reason.strip()):
            raise GatePreconditionFailed(f"I1：条目 {eid} 判 {value} 必须给出理由。")
        normalized[eid] = {"decision": value, "reason": reason}
    values = {v["decision"] for v in normalized.values()}
    if "disputed" in values and decision != "disputed":
        raise GatePreconditionFailed("I1：有条目判 disputed ⇒ 闸门决策必须是 disputed。")
    if "disputed" not in values and "ignored" in values and decision not in ("ignored", "confirmed"):
        raise GatePreconditionFailed("I1：有条目判 ignored 且无 disputed ⇒ 决策应为 ignored/confirmed。")
    if "disputed" not in values and "ignored" not in values and decision != "confirmed":
        raise GatePreconditionFailed("I1：全部条目 confirmed ⇒ 闸门决策必须是 confirmed。")
    return normalized


def precheck_decision(
    *,
    gate: str,
    decision: str,
    run_dir: Path,
    mode: str,
    reason: str | None,
    kb: contracts.KbSources,
    entry_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """**提交前**判定（A1/A2/A3/I4）。`decide()` 签署前与 `_resumed` 纵深防御共用同一实现。

    违反即抛 `GatePreconditionFailed`（= PermissionError），**不写账本、不消耗中断**。
    """
    if decision in REASON_REQUIRED and not (isinstance(reason, str) and reason.strip()):
        raise GatePreconditionFailed(
            f"A2：{decision!r} 必须给出理由（reason），不得无理由落账。"
        )

    result: dict[str, Any] = {"entries": {}, "warnings": []}

    if gate == "G1_diff_confirm":
        diff = contracts.diff_entries_view(run_dir, mode=mode)
        if decision == "confirmed" and diff.get("unresolved_count"):
            # 「没有逐条处置时，drill 用非空 reason 作『已逐条核对』attestation」这一步
            # 由**唯一判据**决定；外层不再另写 `mode == "drill"`（红线 8 / 复核残留 1）。
            drill_attestation = contracts.decision_requires_reason(
                gate, decision, mode=mode, unresolved_count=diff.get("unresolved_count")
            )
            if entry_decisions:
                result["entries"] = normalize_entry_decisions(
                    gate=gate, decision=decision, entry_decisions=entry_decisions, diff=diff
                )
            elif drill_attestation:
                # drill 夹具的 N2 产出于修 F-02 之前（旧编码判定）⇒ 历史未决条目
                # 不能阻断人工闸门；把「已逐条核对」的 attestation（非空 reason）作为处置凭据。
                if not (isinstance(reason, str) and reason.strip()):
                    raise GatePreconditionFailed(
                        "I1：N2 有未决差异条目。drill 模式须给出非空 reason（作为"
                        "「已逐条核对」的证明），或提交覆盖全部条目的 entry_decisions。"
                    )
                result["entries"] = {
                    str(e.get("entry_id")): {
                        "decision": "confirmed",
                        "reason": reason,
                        "source": "drill_reason_attestation",
                        "legacy_drill_fixture": bool(e.get("legacy_drill_fixture")),
                    }
                    for e in diff.get("entries") or []
                    if e.get("entry_id")
                }
                result["warnings"].append("drill：未决条目按 reason attestation 处置（夹具历史件）")
            else:
                raise GatePreconditionFailed(
                    f"I1：N2 有 {diff['unresolved_count']} 条未决差异条目"
                    f"（{diff.get('unresolved_ids')}）⇒ real 模式必须提交 entry_decisions "
                    "覆盖**全部**条目（confirmed/ignored/disputed；ignored/disputed 带理由）。"
                )
        else:
            result["entries"] = normalize_entry_decisions(
                gate=gate, decision=decision, entry_decisions=entry_decisions, diff=diff
            )

    elif gate == "G2_report_accept" and decision == "accept":
        cases = contracts.case_states_view(run_dir, created_at=contracts.run_created_at(run_dir))
        pending = cases.get("pending_own") or []
        verdict = contracts.report_claimed_verdict(run_dir)
        # 与下发选项**同一判据**（红线 8）：选项说"必须理由" ⇔ 这里拒绝无理由的 accept。
        if contracts.decision_requires_reason(gate, decision, verdict):
            # SPEC-REV-12 R1 方案 D：失败报告允许接受，但**必须显式理由**；
            # accept 只表示"接受这份未通过的报告"，不等于判据通过（N16 仍受 I3/I4 阻断）。
            if not (isinstance(reason, str) and reason.strip()):
                raise GatePreconditionFailed(
                    "D：本轮报告结论为 not_passed（未通过）⇒ 接受失败报告必须给出理由（reason）。"
                    f"仍有 {len(pending)} 个用例「已修订待验」：接受报告不等于判据通过，"
                    "N16 仍受 I3/I4 阻断。"
                )
            result["warnings"].append(
                "报告结论 not_passed：accept 作为失败收口（已给理由）；"
                f"{len(pending)} 个用例仍待验，不得称跑通"
            )
        elif pending:
            raise GatePreconditionFailed(
                f"I2：本轮仍有 {len(pending)} 个用例「已修订待验」"
                f"（{pending}）⇒ 不得接受报告（I2：待验不得称跑通）。"
            )

    if gate == "G3_regression_decision" and decision in ("full_now", "subset_only"):
        blocking = [c for c in kb.load_conflicts().get("items", []) if c.get("blocks_release")]
        if blocking:
            raise GatePreconditionFailed(
                f"I4：冲突未清零（{len(blocking)} 项 blocks_release）⇒ 不得选 {decision}；"
                "闸门保持待决策，可改选 milestone_only / defer。"
            )
    return result


def _planned_entries(data: Any) -> dict[str, Any] | None:
    """恢复载荷里的逐条处置（若有）。"""
    resume = getattr(data, "resume", None)
    value = (getattr(resume, "value", None) or {}) if resume is not None else {}
    entries = value.get("entry_decisions") or value.get("entries")
    return entries if isinstance(entries, dict) else None


def _state_facts(data: Any) -> dict[str, Any]:
    """闸门材料消费的 execution state 键（命名与 WS-R 冻结口径一致；全部容错读）。"""
    keys = (
        "n2_diff", "n5_impact", "n6_applied", "n8_check", "n9_job", "n9_result",
        "n10_reconcile", "n11_review", "n12_report", "gate_decisions",
    )
    out: dict[str, Any] = {}
    for key in keys:
        value = data.get_state(key)
        if value is not None:
            out[key] = value
    return out


def _ledger_notes(ctx: RunCtx) -> list[dict[str, Any]]:
    """drill 下"替身复核不写用例态台账"的显式标记（原样进闸门材料）。"""
    try:
        events = ctx.progress.read()
    except Exception:  # pragma: no cover
        return []
    return [
        {"node": e.get("node"), "status": e.get("status"), "detail": e.get("detail") or {}}
        for e in events
        if e.get("kind") == "warning" and e.get("status") == "drill_ledger_skipped"
    ]


async def _enter(ctx: RunCtx, data: Any, gate: str) -> dict[str, Any]:
    node = GATE_NODE[gate]
    cycles = _cycles_view(ctx, data)
    _persist_cycles(ctx, cycles)
    await data.async_set_state("g2_rework_cycles", cycles["g2_rework_cycles"])
    facts = _state_facts(data)
    ledger_notes = _ledger_notes(ctx)
    if ledger_notes:
        facts["_ledger_notes"] = ledger_notes
    material = contracts.gate_material(
        gate=gate,
        run_dir=ctx.run_dir,
        counts=_counts_for(data),
        kb=ctx.kb,
        pending_interrupt=None,
        job=None,
        stage=GATE_STAGE[gate],
        mode=ctx.mode,
        state_facts=facts,
        gate_decisions=data.get_state("gate_decisions") or {},
        cycles=cycles,
    )
    material["run_id"] = ctx.run_id
    material["cycle"] = _cycle(data, gate, ctx)
    # R3：选项里的理由前置必须反映**本轮**事实（G2 失败报告 / drill G1 attestation），
    # 否则中断载荷里下发的还是静态表，界面无法预检。
    diff_view = material.get("difference_items") or {}
    material["decision_options"] = decision_options(
        gate,
        claimed_verdict=contracts.report_claimed_verdict(ctx.run_dir),
        mode=ctx.mode,
        unresolved_count=diff_view.get("unresolved_count"),
    )
    material["gate_node"] = node
    material["authority_enums"] = {g: list(GA.decisions().get(g, ())) for g in GA.gate_ids()}
    ctx.event("gate_pending", node=node, status="waiting",
              detail={"gate": gate, "cycle": material["cycle"],
                      "hard_block": [b["code"] for b in material["hard_block"]],
                      "decision_options": [o["value"] for o in material["decision_options"]]})
    await data.async_set_state(f"gate_material::{gate}", material)
    await data.async_pause_for(
        type="gate_decision",
        interrupt_id=f"{gate}:{material['cycle']}",
        payload=material,
        resume_to="self",
    )
    return {"status": "waiting", "gate": gate}


async def _resumed(ctx: RunCtx, data: Any, gate: str) -> dict[str, Any]:
    node = GATE_NODE[gate]
    resume = getattr(data, "resume", None)
    value = (resume.value if resume is not None else None) or {}
    decision = value.get("decision")
    actor = value.get("actor")
    reason = value.get("reason")

    if not isinstance(decision, str) or not GA.is_valid_decision(gate, decision):
        options = list(GA.decisions().get(gate, ()))
        ctx.node_failed(node, message=f"非法决策 {decision!r}（权威枚举：{options}）")
        raise GatePreconditionFailed(f"非法决策 {decision!r}；{gate} 的权威枚举是 {options}")
    if decision in GA.NON_ACTIONABLE:
        raise GatePreconditionFailed(f"{decision!r} 是状态而非可提交动作；请选择一个实际决策。")
    if actor and not str(actor).startswith("human"):
        raise GatePreconditionFailed("I6：闸门决策只接受 human actor。")

    # 纵深防御：提交前判定在 `RunManager.decide()` 已做过一次；这里再算一次
    # （防止绕过 API 的 resume —— 例如恢复补投递/脚本直接 continue_with）。
    entry_decisions = _planned_entries(data)
    pre = precheck_decision(
        gate=gate, decision=decision, run_dir=ctx.run_dir, mode=ctx.mode,
        reason=reason, kb=ctx.kb, entry_decisions=entry_decisions,
    )

    # 权威复核：闸门必须已在 gate.py 里获得人类签署（纵深防御，UI 说"已通过"不算数）。
    # **必须带 `--expect <本门决策>`**：默认期望是 G1=confirmed/G2=accept，
    # 若不带，ignored/disputed/rework 签后被默认期望打回 ⇒ 中断已消耗、执行 FAILED、
    # 账本留孤儿签名（C1/B4，实测过 self_resume_limit_reached）。
    from .host_steps import run_kb_tool

    check = run_kb_tool(
        "gate.py", ["require-signed", "--run", ctx.run_id, "--gate", gate, "--expect", decision]
    )
    if check["rc"] != 0:
        ctx.node_failed(node, message=f"authority check failed rc={check['rc']}")
        raise GatePreconditionFailed(
            f"闸门 {gate} 未在 kb/tools/gate.py 中获得权威签署（决策 {decision!r}，rc={check['rc']}）："
            "UI 的提交不算权威。"
        )

    cycles = _cycles_view(ctx, data)
    # C6/I7：G2=rework 自增**独立**计数（N6↔N8 的预算不被人为返工消耗）。
    if gate == "G2_report_accept" and decision == "rework":
        cycles["g2_rework_cycles"] = int(cycles.get("g2_rework_cycles") or 0) + 1
    _persist_cycles(ctx, cycles)
    await data.async_set_state("g2_rework_cycles", cycles["g2_rework_cycles"])
    if cycles["n6_n8_cycles"]:
        await data.async_set_state("n6_n8_cycles", cycles["n6_n8_cycles"])

    auth = authority_record(ctx, gate)
    # R3-04：签署时材料里的硬阻断快照（提交前材料 `gate_material::<gate>`；缺失 ⇒ []）。
    # 只进 `decisions/<gate>.json` 落账（读侧唯一来源），不改 `gate_decisions` 既有形状。
    hard_block_snapshot = _material_hard_block(data, gate)
    record = {
        "decision": decision,
        "actor": actor,
        "actor_kind": "human",
        "signed_at": auth.get("signed_at"),
        "reason": reason if reason is not None else auth.get("note"),
        "artifacts": auth.get("artifacts") or [],
        "entries": pre.get("entries") or {},
        "cycle": _cycle(data, gate, ctx),
    }
    decisions = dict(data.get_state("gate_decisions") or {})
    decisions[gate] = record
    await data.async_set_state("gate_decisions", decisions)
    await data.async_set_state("gate_actor", actor)
    ctx.event("gate_decided", node=node, status=decision,
              detail={"gate": gate, "decision": decision, "actor": actor, "reason": reason,
                      "signed_at": record["signed_at"], "artifacts": record["artifacts"],
                      # P-15/P-18：逐条处置随事件下发（新 run）；S3 另从 decisions/ 落账读
                      "entries": record["entries"]})
    # §2.5 落账：record 组装后、node_finished 前（append-only）。S3 的已决策态逐条处置只信这份。
    # R3-04：落账额外带"当时的硬阻断"快照（`hard_block`），不改 record 在 state/事件里的既有形状。
    append_decision_ledger(ctx, gate, {**record, "hard_block": hard_block_snapshot})

    branch = (BRANCH_EVENTS.get(gate) or {}).get(decision)
    if not branch:
        # I17 的后半条：未知分支必须在**发事件前**显式失败，不得 KeyError 落到楔死路径。
        ctx.node_failed(node, message=f"{gate} 的决策 {decision!r} 在本层没有下游事件（拓扑落后于权威）")
        raise GatePreconditionFailed(
            f"{gate} 的决策 {decision!r} 没有映射到下游事件；BRANCH_EVENTS 与权威漂移。"
        )
    # §10.4：闸门节点的 source=`human_gate`、summary 说明"给了什么决策/是否人签/有没有理由"，
    # `human_signed` 只从权威 `gates.json` 读（事件流里的 actor 是自报字符串，不算凭据）。
    signed = human_signed_flag(ctx, gate)
    signed_text = ("已由人签署（human_signed=true）" if signed is True
                   else "非人签署（human_signed=false）" if signed is False
                   else "签署状态未下发")
    gates_json = ctx.run_dir / "gates.json"
    ctx.node_finished(
        node,
        status=decision,
        detail={
            "gate": gate,
            "decision": decision,
            "branch": branch,
            "actor": actor,
            "source": "human_gate",
            "human_signed": signed,
            "summary": (f"{node} {gate}：决策 {decision}，{signed_text}，"
                        f"理由{'已给出' if reason else '未给出'}，下游事件 {branch}"),
        },
        refs=[str(gates_json)] if gates_json.is_file() else [],
    )
    await data.async_emit(branch, {"gate": gate, "decision": decision, "actor": actor,
                                   "entry_decisions": record["entries"]})
    return {"gate": gate, "decision": decision, "branch": branch}


def make_gate(gate: str):
    async def _gate(data: Any) -> dict[str, Any]:
        ctx = ctx_of(data)
        if getattr(data, "is_resume", False):
            return await _resumed(ctx, data, gate)
        ctx.node_started(GATE_NODE[gate])
        return await _enter(ctx, data, gate)

    _gate.__name__ = f"gate_{gate}"
    return _gate


gate1 = make_gate("G1_diff_confirm")
gate2 = make_gate("G2_report_accept")
gate3 = make_gate("G3_regression_decision")


async def halt(data: Any) -> dict[str, Any]:
    """闸门要求裁决 / 忽略 / 暂缓时，闭环**显式终止**，不假装收敛。"""
    ctx = ctx_of(data)
    decisions = data.get_state("gate_decisions") or {}
    decision_map = {g: d.get("decision") for g, d in decisions.items()}
    # P-35：终止原因写**白话**（原值仍原样留在 `decisions` 与既有 `{闸门: 决策}` 字段里）。
    parts = [
        f"{GATE_LABEL_CN.get(gate, gate)}选了「{GA.human_readable(gate, str(decision))}」"
        for gate, decision in decision_map.items() if decision
    ]
    reason_text = ("本轮在 " + "；".join(parts) + " 处终止，所以不继续往下走"
                   if parts else "闸门未放行，所以本轮不继续往下走")
    ctx.event("warning", node="HALT", status="halted",
              detail={"reason": reason_text, "decisions": decision_map})
    # §10.4：HALT 的 summary 用终止原因原文；detail 原有的 `{闸门: 决策}` 字段原样保留。
    decisions_text = "；".join(f"{gate}={item.get('decision')}" for gate, item in decisions.items())
    ctx.node_finished("HALT", status="halted", detail={
        **decision_map,
        "reason": reason_text,
        "decisions": decision_map,
        "source": "framework",
        "summary": ("HALT：" + reason_text
                    + (f"（{decisions_text}）" if decisions_text else "（无闸门决策）")),
    })
    return {"halted": True, "decisions": decision_map}


#: 闸门 id 列表（取自权威，仅暴露用）
GATE_IDS = GA.gate_ids()

#: 合法决策全量（取自权威，仅暴露用）
GATE_DECISIONS = GA.decisions()
