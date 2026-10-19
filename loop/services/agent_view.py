"""从事件派生「agent 工作状态」投影（只读、非权威）。

为什么是投影而不是状态机：执行状态权威在 TriggerFlow 执行 + `kb/tools/gate.py`；
本模块只把事件流翻译成人能读的卡片，**不改任何状态、不写文件**。

已知缺口（审计 A10）：业务契约里 N11 = 证据守护，当前实现是评估节点；
本模块对 guardian 如实标注 `note`，不假装它在工作。
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
    {"role": "analyst", "name": "simenv-analyst", "nodes": ["N3"]},
    {"role": "author", "name": "simenv-author", "nodes": ["N6"]},
    {"role": "checker", "name": "simenv-checker", "nodes": ["N8", "N10"]},
    {"role": "guardian", "name": "simenv-guardian", "nodes": ["N11"]},
    {"role": "reporter", "name": "simenv-reporter", "nodes": ["N12"]},
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

GUARDIAN_NOTE = "N11 证据守护在业务契约中存在、当前实现为评估节点（该能力未实现，审计 A10）；本卡可能长期 idle。"


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


def _elapsed(state: _NodeState | None, status: str, now: float | None) -> int | None:
    if state is None or state.started_ts is None:
        return None
    end = state.finished_ts
    if end is None and status == "working" and now is not None:
        end = float(now)
    if end is None:
        return None
    return max(0, int(end - state.started_ts))


def _first_line(path: Path) -> str | None:
    """取第一行**正文**（跳过空行与 Markdown 标题），截断 120 字符。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        return stripped[:120]
    for line in lines:
        stripped = line.strip()
        if stripped:
            return stripped.lstrip("#").strip()[:120]
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
            summary = "未实现（审计 A10）"
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
            }
        )
    return result
