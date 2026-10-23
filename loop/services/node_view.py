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

from . import node_story
#: R3-15：闸门节点 ↔ 闸门 id 只有一份定义（`services/node_registry.py`）；这里只做别名。
from .node_registry import GATE_ID_BY_NODE

#: `detail.source` 的合法执行路径（§10.4）。drill 夹具与 standin 必须能一眼看出。
SOURCE_ENUM: tuple[str, ...] = (
    "drill_fixture",
    "kb_tool",
    "model_live",
    "model_standin",
    "human_gate",
    "framework",
)

# GATE_ID_BY_NODE 的唯一定义在 `services/node_registry.py`（R3-15：同一事实不许两份）；
# 本模块以同名别名导出，外部 `node_view.GATE_ID_BY_NODE` 的引用保持不变。

#: 运行已终态（P-30）：只有这些状态才允许说"本轮没有走到这个节点"。
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"finished", "failed"})

#: 节点目录（name / owner / purpose）**由服务端下发**，前端 `NODE_META` 只是兜底，不得成为第二权威。
#: 名称与 `WEB_UI_SPEC.md` §4.2 的展示契约一致；内部节点与 HALT 见 §10.4；
#: `purpose` 是面板「这一步做什么」的一句话（SPEC-REV-04 R1），**不随数据变化**。
NODE_CATALOG: dict[str, dict[str, str]] = {
    "N0": {"name": "基线", "owner": "Host",
           "purpose": "把这次运行要用的工作目录准备好，并把闸门/基线状态初始化。"},
    "N1": {"name": "摄取", "owner": "Host",
           "purpose": "给当前代码和文档拍一张快照：多少文件、什么指纹、哪些用例，作为对比起点。"},
    "N2": {"name": "diff", "owner": "Host",
           "purpose": "把快照跟基线逐项比对：哪些文件改了、哪些还没对上。"},
    "N3": {"name": "总结", "owner": "analyst",
           "purpose": "让分析模型把原始差异翻成一句人话，讲清楚这次改了什么。"},
    "N4": {"name": "闸门1", "owner": "人",
           "purpose": "由人确认差异清单没问题；点了确认，流程才往下走。"},
    "N5": {"name": "影响", "owner": "Host",
           "purpose": "根据改动算出哪些用例必须改，并检查用例索引全不全。"},
    "N6": {"name": "修订", "owner": "author",
           "purpose": "让作者模型按影响清单改/补用例，并检查它的输出格式对不对。"},
    "N6_apply": {"name": "修订落盘", "owner": "Host",
                 "purpose": "把模型给的修改真正写进沙箱用例（每条唯一命中，并核对冻结指纹）。"},
    "N7": {"name": "编译", "owner": "Host",
           "purpose": "先把改过的用例编译一遍，确认语法和引用没问题。"},
    "N8": {"name": "复核", "owner": "checker",
           "purpose": "让检查模型静态看一遍修订后的用例，判断能不能进入全跑。"},
    "N9": {"name": "全跑", "owner": "Host",
           "purpose": "把选中的用例全部跑一遍（长作业），收双口径计数和日志证据。"},
    "N9_submit": {"name": "全跑提交", "owner": "Host",
                  "purpose": "把全跑作业交出去后先返回，流程停在等待作业完成。"},
    "N10": {"name": "对账", "owner": "checker",
            "purpose": "把全跑结果跟预期对账，判通过/失败，列出需要人工裁决的项。"},
    "N11": {"name": "守护", "owner": "guardian",
            "purpose": "检查证据链完整、身份一致；发现对不上就要求返工。"},
    "N12": {"name": "报告", "owner": "reporter",
            "purpose": "让报告模型写本轮评估报告，并核对它引用的证据都能对上。"},
    "N13": {"name": "闸门2", "owner": "人",
            "purpose": "由人验收报告：接受，或打回返工。"},
    "N14": {"name": "闸门3", "owner": "人",
            "purpose": "由人决定这轮做不做回归、发不发版。"},
    "N15_select": {"name": "回归选集", "owner": "TriggerFlow",
                   "purpose": "从影响面里挑出这轮要跑的回归用例。"},
    "N15": {"name": "回归", "owner": "TriggerFlow",
            "purpose": "跑回归作业，确认改动没有引入回退。"},
    "N15_submit": {"name": "回归提交", "owner": "TriggerFlow",
                   "purpose": "把回归作业交出去后进入等待。"},
    "N16": {"name": "晋升", "owner": "Host",
            "purpose": "把本轮的结论/基线状态晋升落盘（默认 dry-run，不真写）。"},
    "HALT": {"name": "终止", "owner": "TriggerFlow",
             "purpose": "流程在这里终止（闸门未放行或出现阻断）——只为记录原因。"},
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
    run_view: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把事件流投影成 §6.7 的节点详情（纯函数；不读盘、不写盘、不取墙钟）。

    `events` 是 `ProgressLog.read()` 的原始事件列表（调用方负责读取，本函数不碰文件系统）；
    `run_doc` 只消费 `mode` 与 `s0_record_id`（环境来源徽标的数据面）；
    `run_view` 只消费 `status`（P-30 未到达态）——**本函数仍不读盘**；
    `gate` / `report` 由调用方（`api.py`）按只读投影算好传入，这里只做形状校验与透传。
    """
    known = node in NODE_CATALOG
    meta = NODE_CATALOG.get(node) or {}
    # `events` 可能是一次性可迭代（生成器）⇒ 先实体化，后面既切节点片、也算全量事实。
    event_list = list(events)
    node_events = _events_for(event_list, node)
    # R3-10：本轮是否已提前终止（HALT 收尾事件存在）——只用于"未执行"的归因文案，
    # 不改事件、不写进投影字段（"停更早闸门时被说成演示模式"是归因错误）。
    run_halted = any(
        event.get("node") == "HALT" and event.get("kind") in _TERMINAL_KINDS
        for event in event_list
    )

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
    run_status = (run_view or {}).get("status") if isinstance(run_view, dict) else None
    mode = doc.get("mode") if doc.get("mode") is not None else (
        (run_view or {}).get("mode") if isinstance(run_view, dict) else None)
    started_present = any(event.get("kind") == "node_started" for event in node_events)
    # 展示投影（SPEC-REV-04 R1 + P 项）：服务端确定性生成的人话摘要；不改变任何原始字段。
    story = node_story.build_story(
        node,
        events=node_events,
        detail=detail,
        purpose=meta.get("purpose"),
        run_status=run_status,
        mode=mode,
        gate=gate,
        run_halted=run_halted,
        # R3-06：分组只用面板会展示的 refs（run 目录内），不把目录外路径带进展示投影。
        refs=refs,
    )
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
        # 面板的人话展示（purpose / headline / steps / key_results 等）；界面直接渲染，不自行拼装。
        "story": story,
        # P-30：运行态（只读投影；未到达态由 story 统一给文案）。
        "run_status": run_status,
        "run_terminal": bool(run_status in TERMINAL_RUN_STATUSES),
        # P-33：该节点是否有 node_started（没有就诚实标注"无开始事件"，不伪造步骤）。
        "node_started_present": started_present,
        # P-17/P-18：闸门节点二级差异清单（等待/已决策/无材料三态）；非闸门节点为 None。
        "gate": gate if isinstance(gate, dict) else None,
        # P-28：N12 报告只读视图入口（存在性 + 字节数；正文由独立端点给）。
        "report": report if isinstance(report, dict) else None,
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
    "GATE_ID_BY_NODE",
    "NODE_CATALOG",
    "REQUIRED_FIELDS",
    "SOURCE_ENUM",
    "TERMINAL_RUN_STATUSES",
    "build_node_detail",
]
