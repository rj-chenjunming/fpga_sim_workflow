"""节点执行详情投影（只读、非权威）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §10.4（逐节点下限表）与
`doc/spec/WEB_UI_SPEC.md` §6.7（`GET /api/runs/{run_id}/nodes/{node}`）。

四条硬约束（验收会核）：

1. **范围 = 全部节点**：N0–N16 + 四段之外的内部节点（`N6_apply` / `N9_submit` /
   `N15_select` / `N15_submit`）+ `HALT`；未知节点返回 `known=false` 的空投影，
   **不**用 404 冒充"节点不存在"。
2. **数据来源唯一**：事件流（`ProgressLog.read()` 的原始事件，`refs` 只在事件顶层）
   + `node_finished` / `node_failed` 的 `detail`。本模块**不读盘、不写盘**，
   不做任何业务判定，也不从产物文件反推数字。
3. **不猜、不补默认值**：必含字段缺失只进 `missing_fields`，历史 run **不回填**。
4. **status 原值**：闸门=决策值、N8/N11/N16/HALT 各自语义，原样下发，不归一化。

时间字段一律来自事件 `ts`（本模块不取墙钟），因此同一事件流得到逐字节相同的投影。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

#: `detail.source` 的合法执行路径（§10.4）。drill 夹具与 standin 必须能一眼看出。
SOURCE_ENUM: tuple[str, ...] = (
    "drill_fixture",
    "kb_tool",
    "model_live",
    "model_standin",
    "human_gate",
    "framework",
)

#: 节点目录（name / owner）**由服务端下发**，前端 `NODE_META` 只是兜底，不得成为第二权威。
#: 名称与 `WEB_UI_SPEC.md` §4.2 的展示契约一致；内部节点与 HALT 见 §10.4。
NODE_CATALOG: dict[str, dict[str, str]] = {
    "N0": {"name": "基线", "owner": "Host"},
    "N1": {"name": "摄取", "owner": "Host"},
    "N2": {"name": "diff", "owner": "Host"},
    "N3": {"name": "总结", "owner": "analyst"},
    "N4": {"name": "闸门1", "owner": "人"},
    "N5": {"name": "影响", "owner": "Host"},
    "N6": {"name": "修订", "owner": "author"},
    "N6_apply": {"name": "修订落盘", "owner": "Host"},
    "N7": {"name": "编译", "owner": "Host"},
    "N8": {"name": "复核", "owner": "checker"},
    "N9": {"name": "全跑", "owner": "Host"},
    "N9_submit": {"name": "全跑提交", "owner": "Host"},
    "N10": {"name": "对账", "owner": "checker"},
    "N11": {"name": "守护", "owner": "guardian"},
    "N12": {"name": "报告", "owner": "reporter"},
    "N13": {"name": "闸门2", "owner": "人"},
    "N14": {"name": "闸门3", "owner": "人"},
    "N15_select": {"name": "回归选集", "owner": "TriggerFlow"},
    "N15": {"name": "回归", "owner": "TriggerFlow"},
    "N15_submit": {"name": "回归提交", "owner": "TriggerFlow"},
    "N16": {"name": "晋升", "owner": "Host"},
    "HALT": {"name": "终止", "owner": "TriggerFlow"},
}

#: §10.4 逐节点下限（右列"必须补到"）。点号表示 `detail` 内的嵌套键。
#: `summary` / `source` 是**所有**节点（含未知节点）的下限。
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "N0": ("summary", "source", "baseline"),
    "N1": (
        "summary", "source",
        "manifest.allfiles_entries", "manifest.allfiles_sha256",
        "manifest.cases_frozen", "manifest.doc_fingerprint",
        "manifest.commit_parseable",
    ),
    "N2": ("summary", "source", "routes", "unresolved_count", "offsets"),
    "N3": ("summary", "source"),
    "N4": ("summary", "source", "human_signed"),
    "N5": ("summary", "source", "index_gap_count"),
    "N6": ("summary", "source"),
    "N6_apply": ("summary", "source"),
    "N7": ("summary", "source", "failed_cases"),
    "N8": ("summary", "source"),
    "N9": ("summary", "source", "job_id"),
    "N9_submit": ("summary", "source", "job_id"),
    "N10": ("summary", "source"),
    "N11": ("summary", "source"),
    "N12": ("summary", "source", "ref_count"),
    "N13": ("summary", "source", "human_signed"),
    "N14": ("summary", "source", "human_signed"),
    "N15_select": ("summary", "source"),
    "N15": ("summary", "source", "job_id"),
    "N15_submit": ("summary", "source", "job_id"),
    "N16": ("summary", "source"),
    "HALT": ("summary", "source"),
}

#: 未知/未来节点的下限：只要求 §10.4 的"每个节点必含"两项。
DEFAULT_REQUIRED: tuple[str, ...] = ("summary", "source")

_TERMINAL_KINDS = frozenset({"node_finished", "node_failed"})


def _events_for(events: Iterable[dict[str, Any]], node: str) -> list[dict[str, Any]]:
    """该节点的**原始事件切片**（按 seq 升序；直接使用字典，不做任何改写）。"""
    out = [e for e in events if e.get("node") == node]
    out.sort(key=lambda e: int(e.get("seq") or 0))
    return out


def _has_field(detail: dict[str, Any], dotted: str) -> bool:
    """字段是否**已下发**（键存在即算下发；显式 `null` 也是下发，不是"缺失"）。"""
    cur: Any = detail
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def _text(detail: dict[str, Any], key: str) -> str | None:
    value = detail.get(key)
    return value if isinstance(value, str) and value else None


def _refs(events: Sequence[dict[str, Any]]) -> list[str]:
    """事件**顶层** refs 的合并（去重、保持首次出现顺序）。"""
    out: list[str] = []
    for event in events:
        for ref in event.get("refs") or []:
            text = str(ref)
            if text and text not in out:
                out.append(text)
    return out


def _inside_run_dir(ref: str, run_dir: str) -> bool:
    """`refs` 只允许 run 目录内路径（SPEC-04 §6.7）；相对路径按 run 目录解析。"""
    import os

    base = os.path.realpath(run_dir)
    candidate = ref if os.path.isabs(ref) else os.path.join(base, ref)
    candidate = os.path.realpath(candidate)
    return candidate == base or candidate.startswith(base + os.sep)


def _split_refs(refs: Sequence[str], run_dir: str | None) -> tuple[list[str], int]:
    """把 refs 分成「run 目录内（可展示）」与「目录外（只计数，不给路径）」。

    规格依据：SPEC-04 §6.7「`refs` 只给 run 目录内路径；不返回文件内容」。
    目录外引用（如 `loop/state/jobs/*.log`）**不展示路径**，只把条数如实告诉操作员，
    避免面板变成任意路径探测器。
    """
    if not run_dir:
        return list(refs), 0
    inside = [ref for ref in refs if _inside_run_dir(ref, run_dir)]
    return inside, len(refs) - len(inside)


def _slice(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """面板用的事件切片：最近一条在前（§4.2.1 "按 seq 排列，最近一条在前"）。"""
    out: list[dict[str, Any]] = []
    for event in reversed(events):
        out.append({
            "seq": event.get("seq"),
            "kind": event.get("kind"),
            "status": event.get("status"),
            "ts": event.get("ts"),
            "detail": event.get("detail") or {},
            "refs": list(event.get("refs") or []),
            "provisional": bool(event.get("provisional")),
        })
    return out


def build_node_detail(
    run_id: str,
    node: str,
    *,
    events: Iterable[dict[str, Any]] = (),
    run_doc: dict[str, Any] | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    """把事件流投影成 §6.7 的节点详情（纯函数；不读盘、不写盘、不取墙钟）。

    `events` 是 `ProgressLog.read()` 的原始事件列表（调用方负责读取，本函数不碰文件系统）；
    `run_doc` 只消费 `mode` 与 `s0_record_id`（环境来源徽标的数据面）。
    """
    known = node in NODE_CATALOG
    meta = NODE_CATALOG.get(node) or {}
    node_events = _events_for(events, node)

    terminal: dict[str, Any] | None = None
    for event in node_events:
        if event.get("kind") in _TERMINAL_KINDS:
            terminal = event

    detail = dict(terminal.get("detail") or {}) if terminal is not None else {}
    if terminal is not None:
        status = terminal.get("status")
        kind = terminal.get("kind")
        finished_at = terminal.get("ts")
    elif node_events:
        status = node_events[-1].get("status")
        kind = node_events[-1].get("kind")
        finished_at = None
    else:
        status = None
        kind = None
        finished_at = None

    started_at = None
    for event in node_events:
        if event.get("kind") == "node_started":
            started_at = event.get("ts")
            break

    required = REQUIRED_FIELDS.get(node, DEFAULT_REQUIRED)
    missing = [field for field in required if not _has_field(detail, field)]

    doc = run_doc or {}
    refs, refs_omitted = _split_refs(_refs(node_events), run_dir)
    return {
        "run_id": run_id,
        "node": node,
        "known": known,
        # 身份按**服务端目录**下发；未知节点给 None（前端兜底显示"未知节点"），不编中文名。
        "name": meta.get("name"),
        "owner": meta.get("owner"),
        # status 原值：闸门=决策值、N8/N11/N16/HALT 各自语义，不归一化。
        "status": status,
        "kind": kind,
        "started_at": started_at,
        "finished_at": finished_at,
        "source": _text(detail, "source"),
        "summary": _text(detail, "summary"),
        "detail": detail,
        # `node_history` 投影会丢弃顶层 refs ⇒ 这里合并展示，但不改写任何一类数据。
        "refs": refs,
        # 运行目录外的引用只计数、不给路径（§6.7 安全边界）。
        "refs_omitted": refs_omitted,
        "events": _slice(node_events),
        "missing_fields": missing,
        "authority": "projection",
        # 只读投影附带的环境来源（§4.5 徽标；drill 不覆盖 S0）。
        "mode": doc.get("mode"),
        "s0_record_id": doc.get("s0_record_id"),
    }


__all__ = [
    "DEFAULT_REQUIRED",
    "NODE_CATALOG",
    "REQUIRED_FIELDS",
    "SOURCE_ENUM",
    "build_node_detail",
]
