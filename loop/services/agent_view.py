"""从事件派生「agent 工作状态」投影（只读、非权威）。

为什么是投影而不是状态机：执行状态权威在 TriggerFlow 执行 + `kb/tools/gate.py`；
本模块只把事件流翻译成人能读的卡片，**不改任何状态、不写文件**。

能力展示（F02）：每张卡下发 `capabilities` 四维事实（实现/依赖/本次执行方式/验证范围），
未知维度保持 `None`；`idle` 只表示本次未开始，不表示「未实现」。UI 不得从状态或颜色推断能力。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: 四段流程（展示契约；与 `doc/spec/WEB_UI_SPEC.md` §4.2 一致）。
STAGES: list[dict[str, Any]] = [
    {"key": "ingest", "name": "摄取", "nodes": ["N0", "N1", "N2", "N3", "N4"]},
    {"key": "revise", "name": "修订", "nodes": ["N5", "N6", "N7", "N8"]},
    {"key": "verify", "name": "验证", "nodes": ["N9", "N10", "N11", "N12"]},
    {"key": "decide", "name": "决策", "nodes": ["N13", "N14", "N15", "N16"]},
]

#: 6 个模型角色里出现在卡片上的 5 个（Host 单独一行，不占角色卡）。
AGENT_ROLES: list[dict[str, Any]] = [
    {"role": "analyst", "name": "simenv-analyst", "nodes": ["N3"], "implemented": True},
    {"role": "author", "name": "simenv-author", "nodes": ["N6"], "implemented": True},
    {"role": "checker", "name": "simenv-checker", "nodes": ["N8", "N10"], "implemented": True},
    # N11 已有成链判断/返工实现（model_steps.n11_review）；审计 A10 的「未实现」结论已过期。
    {"role": "guardian", "name": "simenv-guardian", "nodes": ["N11"], "implemented": True},
    {"role": "reporter", "name": "simenv-reporter", "nodes": ["N12"], "implemented": True},
]

#: 每个节点可读的一行结论（产物第一行）；缺失就如实说缺失。
ARTIFACTS: dict[str, str] = {
    "N3": "n3_digest.md",
    "N6": "N6_author_note.md",
    "N8": "check_C.md",
    "N10": "reconcile.md",
    "N12": "n12_report.md",
}

GATE_NODES: dict[str, str] = {
    "N4": "G1_diff_confirm",
    "N13": "G2_report_accept",
    "N14": "G3_regression_decision",
}

GUARDIAN_NOTE = "N11 证据守护（成链判断/返工）已实现；本卡为事件投影，验证范围以服务端证据为准。"
GUARDIAN_IDLE_SUMMARY = "待命：本次尚未进入 N11"


class _NodeState:
    __slots__ = ("started_ts", "finished_ts", "last_ts", "last_kind", "last_status",
                 "failed", "failed_message", "mode")

    def __init__(self) -> None:
        self.started_ts: float | None = None
        self.finished_ts: float | None = None
        self.last_ts: float | None = None
        self.last_kind: str | None = None
        self.last_status: str | None = None
        self.failed = False
        self.failed_message: str | None = None
        self.mode: str | None = None


def _base_node(node: str) -> str:
    """`N3_request` 这类内部事件归一到 `N3`（只为取 mode，不改变动作）。"""
    if node.endswith("_request"):
        return node[: -len("_request")]
    return node


def _collect(events: list[dict[str, Any]]) -> dict[str, _NodeState]:
    states: dict[str, _NodeState] = {}
    for event in events:
        raw_node = event.get("node")
        if not raw_node:
            continue
        node = _base_node(str(raw_node))
        state = states.setdefault(node, _NodeState())
        ts = event.get("ts")
        kind = event.get("kind")
        status = event.get("status")
        detail = event.get("detail") or {}
        if kind == "node_started" and state.started_ts is None and isinstance(ts, (int, float)):
            state.started_ts = float(ts)
        if kind == "node_finished":
            if isinstance(ts, (int, float)):
                state.finished_ts = float(ts)
            if status == "failed":
                state.failed = True
        if kind == "node_failed":
            state.failed = True
            state.failed_message = detail.get("message")
        if kind in ("node_started", "node_finished", "node_failed") and isinstance(ts, (int, float)):
            state.last_ts = float(ts)
            state.last_kind = str(kind)
            state.last_status = str(status) if status is not None else None
        mode = detail.get("mode")
        if isinstance(mode, str) and mode:
            state.mode = mode
    return states


def _choose(nodes: list[str], states: dict[str, _NodeState]) -> str:
    present = [n for n in nodes if n in states]
    if not present:
        return nodes[0]
    return max(present, key=lambda n: states[n].last_ts or 0.0)


def _status(node: str, state: _NodeState | None, pending_interrupt: dict[str, Any] | None,
            job: dict[str, Any] | None) -> str:
    if state is None:
        return "idle"
    if state.failed:
        return "failed"
    gate = (pending_interrupt or {}).get("payload", {}).get("gate") if pending_interrupt else None
    if pending_interrupt and GATE_NODES.get(node) == gate:
        return "waiting"
    if node == "N9" and job and job.get("phase") == "running":
        return "waiting"
    if state.last_kind == "node_started" and state.finished_ts is None:
        return "working"
    if state.finished_ts is not None:
        return "done"
    return "idle"


def _execution(state: _NodeState | None, status: str) -> str:
    """本次执行方式：`not_started / standin / real / unknown`（未知不猜）。"""
    if state is None or status == "idle":
        return "not_started"
    mode = (state.mode or "").strip().lower()
    if mode in ("live", "real"):
        return "real"
    if mode == "standin":
        return "standin"
    return "unknown"


def _capabilities(role: dict[str, Any], state: _NodeState | None, status: str) -> dict[str, Any]:
    """四维能力事实（Spec §4.3 F02）。未知维度保持 `None`，不用默认值冒充。"""
    return {
        "implemented": bool(role.get("implemented", True)),
        # 本层没有 provider/UVS/夹具探针 ⇒ 依赖是否齐备是**未知**，不猜。
        "dependencies_ready": None,
        "execution": _execution(state, status),
        "verification_scope": None,
    }


def _elapsed(state: _NodeState | None, status: str, now: float | None) -> int | None:
    if state is None or state.started_ts is None:
        return None
    end = state.finished_ts
    if end is None and status == "working" and now is not None:
        end = float(now)
    if end is None:
        return None
    return max(0, int(end - state.started_ts))


def _clean(text: str) -> str:
    return text.replace("**", "").replace("`", "").strip().strip("：:").strip()


def _after_colon(line: str) -> str | None:
    for sep in ("：", ": "):
        if sep in line:
            tail = _clean(line.split(sep, 1)[1])
            if tail:
                return tail[:120]
    return None


def _first_line(path: Path) -> str | None:
    """取一行**结论**：优先含「结论」的行，其次第一段正文（跳过标题/引用/元数据）。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    # 1) 结论行（docs 的约定：结论通常写在「结论（一句话）：…」里）
    for line in lines:
        stripped = line.strip().lstrip("-*> ").strip()
        if "结论" in stripped:
            tail = _after_colon(stripped)
            if tail:
                return tail
    # 2) 第一段正文：跳过标题、引用、列表元数据、表格、代码围栏、分隔线
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ">", "|", "```", "---", "===")):
            continue
        if stripped.startswith("- "):
            tail = _after_colon(stripped)
            if tail and len(tail) >= 8:
                return tail
            continue
        cleaned = _clean(stripped)
        if len(cleaned) >= 8:
            return cleaned[:120]
    # 3) 兜底：第一行非空文本
    for line in lines:
        cleaned = _clean(line.strip().lstrip("#>* "))
        if cleaned:
            return cleaned[:120]
    return None


def _summary(node: str, run_dir: Path | None) -> tuple[str, list[str]]:
    artifact = ARTIFACTS.get(node)
    if artifact and run_dir is not None:
        path = Path(run_dir) / artifact
        if path.is_file():
            return (_first_line(path) or "产物为空"), [artifact]
    return "产物未生成", []


def build_agents(
    events: list[dict[str, Any]],
    *,
    run_dir: Path | None,
    pending_interrupt: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """把事件流翻译成 5 张角色卡（字段见 Spec §4.3）。"""
    states = _collect(events)
    result: list[dict[str, Any]] = []
    for role in AGENT_ROLES:
        node = _choose(role["nodes"], states)
        state = states.get(node)
        status = _status(node, state, pending_interrupt, job)
        summary, evidence = _summary(node, run_dir)
        note = GUARDIAN_NOTE if role["role"] == "guardian" else None
        if role["role"] == "guardian" and status == "idle":
            summary = GUARDIAN_IDLE_SUMMARY
        result.append(
            {
                "role": role["role"],
                "name": role["name"],
                "nodes": list(role["nodes"]),
                "active_node": node,
                "status": status,
                "last_action": (
                    f"{state.last_kind}({state.last_status})"
                    if state and state.last_kind else "—"
                ),
                "elapsed_s": _elapsed(state, status, now),
                "summary": summary,
                "mode": (state.mode if state and state.mode else "—"),
                "evidence": evidence,
                "note": note,
                "capabilities": _capabilities(role, state, status),
            }
        )
    return result
