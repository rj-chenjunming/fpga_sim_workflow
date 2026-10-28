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
    # 只有**真闸门**才把对应节点标成 waiting。job_done 中断没有 payload.gate，
    # 而 GATE_NODES.get(非闸门节点) 也是 None —— 早先 `None == None` 会把 N3/N6/N8
    # 等模型角色误标成"等待人工"，连带阶段标签显示"等待人工"、节点 chip 显示"!"。
    if pending_interrupt and gate and GATE_NODES.get(node) == gate:
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


def node_capabilities(node: str, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """单节点能力事实：**复用** `_capabilities` 与 `_collect`，供 Agent 窗口消费同一来源。

    返回 `None` 表示该节点不是模型角色卡节点（Host 确定性步骤），不伪造能力结论。
    这里只做投影，不读 provider/UVS/夹具探针，未知维度保持 `None`。
    """
    role = next((item for item in AGENT_ROLES if node in item["nodes"]), None)
    if role is None:
        return None
    state = _collect(events).get(node)
    status = _status(node, state, None, None)
    return _capabilities(role, state, status)


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


# ==================================================================== S4 总结投影（OBS-02/03/04）
#
# 契约：[`SPEC-REV-16`](../../doc/spec/SPEC-REV-16-20261028.md) §2（字段表）/§2.2（压缩次数）
# /§3（无进展判据）/§4（时间口径）。三条纪律：
#   1. **投影不是权威**：本模块只读事件与已封存记录，不写文件、不改状态、不发命令；
#   2. **未知保持未知**：没有来源就 `None`（压缩次数**不得**退化成 0，时间不得用墙钟补）；
#   3. **判据只有一份**：`state`/`execution`/`elapsed_s` 复用上面既有的 `_status`/`_execution`
#      /`_elapsed`；压缩次数复用 `host/agent_backends/dsh_sdk.read_session_log`（不自写解码）。

#: 无进展告警阈值（秒）：**单一来源**，界面只显示服务端下发的 `threshold_s`，不自己带数。
NO_PROGRESS_THRESHOLD_S = 600

#: 受管元数据里的 session log 相对引用键（S5 落账前**没有生产者** ⇒ 压缩次数恒 `unknown`）。
#: 只接受相对 run_dir 的路径；绝对路径 / `..` / 符号链接一律拒绝（不开放任意路径读取）。
SESSION_LOG_REF_KEY = "session_log_ref"


def _num(value: Any) -> float | None:
    """只接受真数字（`bool` 不是时间）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _node_events(node: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """该节点的事件（含 `N6_request` 这类内部变体，与窗口过滤同一口径）。"""
    return [event for event in events
            if event.get("node") == node
            or str(event.get("node", "")).startswith(node + "_")]


def _last_event(node_events: list[dict[str, Any]], now: float | None) -> dict[str, Any] | None:
    """事件流里该节点的**最后一条**事件（任意 kind，含 warning），带年龄。"""
    if not node_events:
        return None
    event = node_events[-1]
    ts = _num(event.get("ts"))
    age = None
    if ts is not None and now is not None:
        age = max(0, int(float(now) - ts))
    return {"kind": event.get("kind"), "status": event.get("status"), "ts": ts, "age_s": age}


def _result_ts(result: dict[str, Any] | None) -> float | None:
    """记录的完成时间：只认记录里显式的 `finished_at`/`ts`。

    **不得**用文件 mtime 冒充：mtime 是宿主文件系统时间，与注入的 `now` 不同源。
    当前 `AM.Attempt.finish` 不写该字段 ⇒ 缺省 `None`（缺口已登记，S5 落账时补）。
    """
    if not isinstance(result, dict):
        return None
    return _num(result.get("finished_at")) or _num(result.get("ts"))


def _last_error(node_events: list[dict[str, Any]], result: dict[str, Any] | None
                ) -> dict[str, Any] | None:
    """最后错误：`node_failed.detail.message`（事件）→ 记录 `error`（同序取第一个有消息者）。"""
    for event in reversed(node_events):
        if event.get("kind") != "node_failed":
            continue
        detail = event.get("detail") or {}
        message = detail.get("message") if isinstance(detail, dict) else None
        if isinstance(message, str) and message.strip():
            return {"message": message, "ts": _num(event.get("ts")), "source": "node_failed"}
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, str) and error.strip():
            return {"message": error, "ts": _result_ts(result), "source": "attempt_result"}
    return None


def _silence(now: float | None, last_event: dict[str, Any] | None,
             result: dict[str, Any] | None) -> tuple[int | None, float | None]:
    """`(silence_s, t_last)`：`t_last = max(最后事件 ts, 最后结果 ts)`；缺哪个用哪个。"""
    if now is None:
        return None, None
    candidates = []
    if last_event is not None and last_event.get("ts") is not None:
        candidates.append(last_event["ts"])
    result_ts = _result_ts(result)
    if result_ts is not None:
        candidates.append(result_ts)
    if not candidates:
        return None, None
    t_last = max(candidates)
    return max(0, int(float(now) - t_last)), t_last


def _no_progress(status: str, now: float | None, silence_s: int | None,
                 t_last: float | None) -> dict[str, Any]:
    """无进展**只告警**（体检表 §2 裁决 #12）：不收敛、不终止、不重发。

    `n/a` 也给 `reason`（说明为什么不适用的状态），界面直接显示，不再自己判。
    """
    threshold = NO_PROGRESS_THRESHOLD_S
    cell = {"since_ts": t_last, "silence_s": silence_s, "threshold_s": threshold}
    if status != "working":
        return {"state": "n/a", **cell,
                "reason": f"状态不是 working（当前 {status}），不做无进展判定"}
    if now is None:
        return {"state": "unknown", **cell,
                "reason": "没有注入 now，无法判定无进展（不使用墙钟）"}
    if t_last is None:
        return {"state": "unknown", **cell,
                "reason": "缺少最后事件/最后结果时间，无法判定无进展"}
    if silence_s is not None and silence_s >= threshold:
        minutes = max(1, int(silence_s) // 60)
        return {"state": "warn", **cell,
                "reason": f"无进展 {minutes} 分钟（阈值 {threshold} 秒，最后事件/结果时间已记录）"}
    return {"state": "ok", **cell, "reason": None}


def _session_log_path(root: Path | None, request: dict[str, Any] | None,
                      result: dict[str, Any] | None,
                      explicit: Path | str | None) -> Path | None:
    """解析 session log 路径（受管元数据，**不接受客户端输入**）。

    顺序：显式参数（Host 进程内已知路径）→ 记录的 `session_log_ref`（相对 run_dir）。
    引用越界（绝对路径 / `..` / 符号链接 / 解析后不在 run 目录内）⇒ **显式失败**，
    不静默当成"没有来源"。没有来源 ⇒ `None`（压缩次数 `unknown`，不显示 0）。
    """
    if explicit is not None:
        return Path(explicit)
    reference = None
    for record in (result, request):
        if isinstance(record, dict) and record.get(SESSION_LOG_REF_KEY):
            reference = record[SESSION_LOG_REF_KEY]
            break
    if reference is None:
        return None
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError(f"{SESSION_LOG_REF_KEY} 必须是非空字符串：{reference!r}")
    if root is None:
        raise ValueError(f"{SESSION_LOG_REF_KEY} 存在但不知道 run 目录，拒绝解析")
    base = Path(root)
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{SESSION_LOG_REF_KEY} 越界（绝对路径或含 ..）：{reference!r}")
    target = base / candidate
    if target.is_symlink() or not target.resolve().is_relative_to(base.resolve()):
        raise ValueError(f"{SESSION_LOG_REF_KEY} 指向 run 目录之外或用了符号链接：{reference!r}")
    return target


def _compaction_view(path: Path | None) -> dict[str, Any]:
    """压缩次数：**只认** session log 的 `compaction/summary`（P7：事件流/projcache 都没有）。

    解析复用 `host/agent_backends/dsh_sdk.read_session_log`（唯一实现，本层不另写解码）。
    - 没有来源 / 源不可用 / 读不出事实 ⇒ `source="unknown"`、`count=None`（**不得显示 0**），
      `reason` 显式说明为什么（不静默）；
    - 源可用 ⇒ `source="session_log"`；`compaction/*` 里的显式失败进 `error`（不吞）。
    """
    if path is None:
        return {"source": "unknown", "count": None, "error": None, "reason": None, "path": None}
    from host.agent_backends import dsh_sdk as SDK  # 复用既有解析（不在 services 层复制）

    try:
        facts = SDK.read_session_log(path)
    except SDK.SessionLogError as exc:
        return {"source": "unknown", "count": None, "error": None,
                "reason": f"session log 不可读：{exc}", "path": str(path)}
    if facts.availability != SDK.AVAILABILITY_OK:
        return {"source": "unknown", "count": None, "error": None,
                "reason": f"session log 不可用：{facts.reason or '原因未给出'}",
                "path": facts.path or str(path)}
    errors = [item.error for item in facts.errors if item.error]
    return {"source": "session_log", "count": facts.count,
            "error": "；".join(errors) if errors else None,
            "reason": None, "path": facts.path or str(path)}


def progress_view(
    node: str,
    *,
    events: list[dict[str, Any]],
    run_dir: Path | None = None,
    request: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    live: dict[str, Any] | None = None,
    pending_interrupt: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    now: float | None = None,
    session_log: Path | str | None = None,
) -> dict[str, Any]:
    """单节点**只读总结投影**（SPEC-REV-16 §2；角色卡与 Agent 窗口**同一实现**）。

    参数：
    - `events`：ProgressLog 事件（ts 为 epoch 秒）；`request`/`result`：`agent_control.read_view`
      选中的封存记录（或 `None`）；`live`：活跃会话视图（只取 `session_id`）；
    - `now`：**Host 注入**的 epoch 秒（`host/paths.py::now_iso` 唯一入口）。`None` ⇒ 时间类字段保持未知；
    - `session_log`：Host 进程内已知的 session log 路径；缺省时用记录里的 `session_log_ref`。

    返回字段（契约冻结；`None` = 未知，不是 0/空完成）：
    `identity{run_id,node,attempt,session_id}`、`state`、`current_action`、`last_event`、
    `last_tool`（**恒 `None`**：工具事件尚无 Host 落账方，S5 接入后才有来源，不猜近似值）、
    `last_error`、`elapsed_s`、`silence_s`、`no_progress{state,since_ts,silence_s,threshold_s,reason}`、
    `compaction{source,count,error,reason,path}`、`execution`、`authority="projection"`。

    **附加可读字段**（`compaction.reason`、`no_progress.reason` 等）非契约必需：只用于给人解释
    "为什么是 unknown"，**消费方不得据此判定完成/失败/状态**（判据仍是 §2.1/§3 的 state 与阈值）。

    **已知未决（REV-16 未决清单，Lead 2026-10-28 复核 P2-2）**：角色卡调用本函数时不带
    `request`/`result`（`build_agents` 只有事件与产物），因此卡片上的 `identity.attempt`、
    `identity.session_id`、`last_error`(记录来源) 为 `null` —— 这是**诚实值**，不是缺陷；
    补齐需在 `run_view` 里按节点读 `agent_memory`（跨层接线，另开小片）。

    时间源口径（契约 §4，Lead 2026-10-28 裁决）：事件 `ts` 由 `host.progress.ProgressLog` 写入
    （真实运行 = 系统时钟）；`now` 只来自注入入口。两者**不同源**时（drill 固定了 `LOOP_NOW`）
    差值夹到 0、不得因此产生假告警；真实运行不注入时钟，两者同源。
    """
    states = _collect(events)
    state = states.get(node)
    status = _status(node, state, pending_interrupt, job)
    node_events = _node_events(node, events)

    last_event = _last_event(node_events, now)
    current_action = None
    if state is not None and state.last_kind:
        current_action = {"kind": state.last_kind, "status": state.last_status,
                          "ts": _num(state.last_ts)}
    silence_s, t_last = _silence(now, last_event, result)

    request_record = request if isinstance(request, dict) else None
    result_record = result if isinstance(result, dict) else None
    run_id = None
    for record in (result_record, request_record):
        if record is not None and isinstance(record.get("run_id"), str):
            run_id = record["run_id"]
            break
    if run_id is None and run_dir is not None:
        run_id = Path(run_dir).name
    attempt = None
    for record in (result_record, request_record):
        if record is not None:
            value = record.get("attempt")
            if isinstance(value, int) and not isinstance(value, bool):
                attempt = value
                break
    session_id = None
    for source in (result_record, live if isinstance(live, dict) else None):
        if source is not None and isinstance(source.get("session_id"), str):
            session_id = source["session_id"]
            break

    return {
        "identity": {"run_id": run_id, "node": node, "attempt": attempt,
                     "session_id": session_id},
        "state": status,
        "current_action": current_action,
        "last_event": last_event,
        "last_tool": None,
        "last_error": _last_error(node_events, result_record),
        "elapsed_s": _elapsed(state, status, now),
        "silence_s": silence_s,
        "no_progress": _no_progress(status, now, silence_s, t_last),
        "compaction": _compaction_view(
            _session_log_path(run_dir, request_record, result_record, session_log)),
        "execution": _execution(state, status),
        "authority": "projection",
    }


# ==================================================================== S3 解释面（OBS-08）

#: run/node_rework 终态到期**未在归约层判定**（S3 计划 §6.4-39）⇒ 界面写「未判定」，
#: **不得**显示"仍生效"（新契约裁决前保持未知，不静默补判据）。
SCOPE_EXPIRY_UNDETERMINED: dict[str, Any] = {
    "determined": False,
    "state": "unknown",
    "note": "run/node_rework 的终态到期归约尚未实现（S3 计划 §6.4-39）⇒ 到期未判定，不表示仍生效",
}


def _text_preview(text: Any, limit: int = 120) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    return text if len(text) <= limit else text[:limit] + "…"


def _instructions_block(root: Path) -> dict[str, Any]:
    """指令解释面：**三态分列**（accepted 回执 ≠ applied 已采用 ≠ effective 当前生效）。

    全部来自 `agent_control.instructions_view`（唯一归约实现）；本层只改列名、不重算。
    """
    from host import agent_control as AC

    projection = AC.instructions_view(Path(root))
    items: list[dict[str, Any]] = []
    for row in projection.get("instructions") or []:
        applied = row.get("applied_attempts") or []
        last_applied = applied[-1] if applied else None
        items.append({
            "id": row.get("instruction_id"),
            "scope": row.get("scope"),
            "target_nodes": list(row.get("target_nodes") or []),
            "state_accepted": "accepted" if row.get("accepted") else "unknown",
            "accepted_at": row.get("created_at"),
            "state_applied": "applied" if last_applied else "not_applied",
            # `applied_attempt` 是**标量**尝试号（界面按"尝试 #N"渲染）；节点身份放附加字段
            # `applied_ref`（run 作用域可被多节点采用，只留最后一个可审计引用）。
            "applied_attempt": (last_applied.get("attempt")
                                if isinstance(last_applied, dict) else None),
            "applied_ref": ({"node": last_applied.get("node"),
                             "attempt": last_applied.get("attempt")}
                            if isinstance(last_applied, dict) else None),
            "state_effective": "effective" if row.get("effective") else "not_effective",
            # `instructions_view.effective` 只回答"下一个尝试是否采纳"，不指向某次具体尝试 ⇒ 未知。
            "effective_attempt": None,
            "unavailable_reason": row.get("reason"),
            "text_preview": _text_preview(row.get("message")),
        })
    return {"revision": projection.get("revision", 0),
            "source": "agent_control.instructions_view", "items": items}


def _working_memory_block(request: dict[str, Any] | None) -> dict[str, Any]:
    """WM 只读诊断：availability / 每条来源 / `unavailable` 原因原样透传（不重算预算）。

    条目的 `availability="verified"` 是**转发口径**：来源条目出现在 Host 冷存的
    `working_memory_source_map.entries` 里，即表示 Host 已核验存在/版本一致（结论由
    `host/agent_working_memory` 给出）。本层不重新判定来源完整性，也不新增判据
    （Lead 2026-10-28 复核 P2-7 登记）。
    """
    base = {"recorded": False, "availability": "unknown", "snapshot_sha256": None,
            "mandatory_bytes": None, "limit_bytes": None, "over_budget": None,
            "items": [], "authority": "projection"}
    source_map = (request or {}).get("working_memory_source_map")
    if not isinstance(source_map, dict):
        return base
    items: list[dict[str, Any]] = []
    for entry in source_map.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        source_keys = entry.get("source_keys") or []
        items.append({"id": entry.get("entry_id"), "kind": entry.get("kind"),
                      "availability": "verified", "unavailable_reason": None,
                      "source_ref": entry.get("pointer") or (source_keys[0] if source_keys
                                                             else None)})
    for item in source_map.get("unavailable") or []:
        if not isinstance(item, dict):
            continue
        items.append({"id": f"{item.get('kind')}:{item.get('slot')}",
                      "kind": item.get("kind"), "availability": "unavailable",
                      "unavailable_reason": item.get("reason"), "source_ref": None})
    return {"recorded": True,
            "availability": source_map.get("availability") or "unknown",
            "snapshot_sha256": source_map.get("snapshot_sha256"),
            "mandatory_bytes": source_map.get("mandatory_bytes"),
            "limit_bytes": source_map.get("limit_bytes"),
            "over_budget": source_map.get("over_budget"),
            "items": items, "authority": "projection"}


def _experiences_block(request: dict[str, Any] | None) -> dict[str, Any]:
    """经验只读诊断：selected/rejected **照记录透传**（不重算适用性、不写回经验）。"""
    base = {"recorded": False, "catalog_version": None, "selection_mode": None,
            "batch": None, "rejection": None, "selected": [], "rejected": [],
            "diagnostics": [], "authority": "projection"}
    record = (request or {}).get("experience_selection")
    diagnostics = (request or {}).get("experience_diagnostics") or []
    if not isinstance(record, dict):
        return {**base, "diagnostics": [str(item) for item in diagnostics
                                       if isinstance(item, str)]}
    selected = [{"id": item.get("id"), "reason": "selected"}
                for item in record.get("selected") or [] if isinstance(item, dict)]
    rejected = [{"id": item.get("id"), "reason": item.get("reason")}
                for item in record.get("rejected") or [] if isinstance(item, dict)]
    return {"recorded": True,
            "catalog_version": record.get("catalog_version"),
            "selection_mode": record.get("selection_mode"),
            "batch": record.get("batch"),
            "rejection": record.get("rejection"),
            "selected": selected, "rejected": rejected,
            "diagnostics": [str(item) for item in diagnostics if isinstance(item, str)],
            "authority": "projection"}


def explain_view(view: dict[str, Any], *, root: Path) -> dict[str, Any]:
    """Agent 窗口 S3 解释面（SPEC-REV-16 §6.3）：只消费服务端结论，前端只渲染。

    - `instructions`：accepted/applied/effective 三态分列（唯一归约 = `agent_control`）；
    - `scope_expiry`：run/node_rework 终态到期**恒"未判定"**（缺口 §6.4-39）；
    - `working_memory`：availability/来源/`unavailable` 原因透传；
    - `experiences`：selected/rejected/diagnostics 透传。
    本函数**不**重算预算、闸门、Schema 校验、经验适用性或指令有效性（红线 8）。

    **附加可读字段**（`working_memory.recorded/authority`、`experiences.recorded/
    catalog_version/selection_mode/batch/rejection`、`instructions[*].target_nodes`、
    `instructions[*].applied_ref`）非契约表 (§6.3) 必需：供界面解释"未记录 vs 无条目"、
    以及标量 `applied_attempt` 对应的节点身份；消费方不得据此判定契约字段的语义或完整性。
    """
    request = view.get("request") if isinstance(view, dict) else None
    return {
        "instructions": _instructions_block(Path(root)),
        "scope_expiry": dict(SCOPE_EXPIRY_UNDETERMINED),
        "working_memory": _working_memory_block(request if isinstance(request, dict) else None),
        "experiences": _experiences_block(request if isinstance(request, dict) else None),
    }


def window_annotation(view: dict[str, Any], *, node: str, root: Path,
                      events: list[dict[str, Any]], now: float | None) -> dict[str, Any]:
    """Agent 窗口的 `{progress, explain}` 组合装配（`services/api.py` 一行并入窗口视图）。

    `view` = `agent_control.read_view(...)` 的返回；`root` = run 目录；`events` = 本 run 的
    ProgressLog 事件；`now` = Host 注入 epoch 秒。窗口与角色卡消费**同一** `progress_view`。
    """
    request = view.get("request") if isinstance(view, dict) else None
    result = view.get("result") if isinstance(view, dict) else None
    live = view.get("live") if isinstance(view, dict) else None
    progress = progress_view(
        node,
        events=list(events or []),
        run_dir=Path(root),
        request=request if isinstance(request, dict) else None,
        result=result if isinstance(result, dict) else None,
        live=live if isinstance(live, dict) else None,
        now=now,
    )
    return {"progress": progress, "explain": explain_view(view, root=Path(root))}


def build_agents(
    events: list[dict[str, Any]],
    *,
    run_dir: Path | None,
    pending_interrupt: dict[str, Any] | None = None,
    job: dict[str, Any] | None = None,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """把事件流翻译成 5 张角色卡（字段见 Spec §4.3）。

    `progress` = 每张卡的总结投影（SPEC-REV-16 §2.1），与 Agent 窗口**同一实现**；
    `now` 必须是 Host 注入的 epoch 秒（`contracts.run_view` 经 `host/paths.py::now_iso` 取）。
    """
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
                "progress": progress_view(
                    node, events=events, run_dir=run_dir, pending_interrupt=pending_interrupt,
                    job=job, now=now,
                ),
            }
        )
    return result
