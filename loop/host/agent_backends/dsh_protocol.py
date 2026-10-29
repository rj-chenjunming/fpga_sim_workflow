"""DSH headless NDJSON 协议层：帧解析、终态判定、提交收口（S1 / S2-a；REV-14 B1·B4·B5）。

只做**纯解析与判定**：不启进程、不猜文本成功、不修补坏帧、不写文件。
铁律（REV-13 §5.1 / REV-14 B5）：只有 `status.turn_end` 可以判完成；
`idle`、`messageId`、退出码、空 `final` 一律不放行；重复且冲突的终态必须失败。
`completed` **还**要求恰一条被接受的 `submit_result` 提交（B1 / DS-02）。

两段式（刻意分开，避免把 S1 的既有语义改红）：

1. `fold`：只**收集**帧（含 `submit_result` 的原始「调用 + 结果」对），
   既有坏帧/无终态/冲突终态/身份不匹配语义**不变**；
2. `require_submission`：独立的**纯门**，把收集结果判成唯一 `Submission`；
   0 条 / 多条不同 / 同 callId 重复 / result 坏 / task_id 不符 ⇒ 显式失败，不得出候选。

业务判据不在这里：唯一实现是 `workflows/chunks/model_steps.py::_validate`。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Union

#: 允许出现的事件类型（fail-closed：未知类型直接 BadFrame，便于换版本时立刻暴露）
KNOWN_EVENT_TYPES = frozenset({"session", "status", "thinking", "text", "tool_call",
                               "tool_result", "final", "error"})

#: 结构化结果提交工具名（B1：`turn_end(completed)` + 提交被接受 = 唯一完成判据）
SUBMIT_TOOL = "submit_result"


class ProtocolError(RuntimeError):
    """协议层失败基类（都出现在收口之前，调用方必须显式失败）。"""


class BadFrame(ProtocolError):
    """坏 JSON / 未知事件类型：拒绝并保留诊断，不忽略坏行。"""


class NoTerminal(ProtocolError):
    """没有 `turn_end`：不得把 idle / 退出码 0 / 空 final 当完成。"""


class ConflictingTerminal(ProtocolError):
    """出现互相冲突的多个终态。"""


class IdentityMismatch(ProtocolError):
    """身份不符：会话 cwd 与本次 attempt 不符，或提交的 task_id 与 attempt_key 不符。"""


class NoSubmission(ProtocolError):
    """`completed` 但 0 条被接受的提交：不得出候选（B1 / DS-02）。"""


class ConflictingSubmissions(ProtocolError):
    """提交互相冲突：多条不同提交 / 同一 callId 重复 / 多条被接受。"""


class BadSubmission(ProtocolError):
    """提交帧结构坏：缺字段、payload 非对象、result 非 JSON、tool_result 非 completed。"""


@dataclass(frozen=True)
class SubmissionCall:
    """一次 `submit_result` 调用的原始帧（`fold` 收集；判定在 `require_submission`）。"""

    call_id: str | None
    input: Any
    results: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Submission:
    """被接受的（或待审计的）结构化提交；`accepted` 只表示「引擎已接收」。"""

    task_id: str
    summary: str
    payload: dict[str, Any]
    call_id: str
    accepted: bool
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunOutcome:
    status: str                       # completed | failed
    reason: str                       # completed | error | <kind>
    text: str = ""
    code: str | None = None
    message: str | None = None
    usage: dict[str, Any] | None = None
    session_id: str | None = None
    cwd: str | None = None
    events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    submission_calls: tuple[SubmissionCall, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.status == "completed"


Frame = Union[str, dict]


def parse_frame(line: Frame) -> dict[str, Any]:
    """一行一帧。空行/坏 JSON/缺 `type`/未知类型都 ⇒ BadFrame。"""
    if isinstance(line, dict):
        event = line
    else:
        text = str(line).strip()
        if not text:
            raise BadFrame("空帧")
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BadFrame("坏 JSON 帧：%r（%s）" % (text[:80], exc)) from None
    if not isinstance(event, dict):
        raise BadFrame("帧不是 JSON 对象：%r" % (str(event)[:80],))
    kind = event.get("type")
    if not isinstance(kind, str) or not kind:
        raise BadFrame("帧缺 type：%r" % (str(event)[:80],))
    if kind not in KNOWN_EVENT_TYPES:
        raise BadFrame("未知事件类型 %r（锁定版本的映射表里没有它）" % (kind,))
    return event


def _terminal_signature(reason: dict[str, Any]) -> tuple:
    error = reason.get("error") if isinstance(reason, dict) else None
    return (reason.get("kind") if isinstance(reason, dict) else None,
            (error or {}).get("code") if isinstance(error, dict) else None)


def _collect_submission_calls(events: Iterable[dict[str, Any]]) -> tuple[SubmissionCall, ...]:
    """把 `submit_result` 的调用与结果按 callId 配对（只收集，不判定）。"""
    events = list(events)
    calls = [event for event in events
             if event.get("type") == "tool_call" and event.get("tool") == SUBMIT_TOOL]
    results: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("type") != "tool_result":
            continue
        call_id = event.get("callId")
        if isinstance(call_id, str):
            results.setdefault(call_id, []).append(event)
    collected: list[SubmissionCall] = []
    for call in calls:
        call_id = call.get("callId")
        key = call_id if isinstance(call_id, str) else None
        collected.append(SubmissionCall(
            call_id=key, input=call.get("input"),
            results=tuple(results.get(key, ())) if key is not None else ()))
    return tuple(collected)


def fold(frames: Iterable[Frame], *, expect_cwd: str | None = None) -> RunOutcome:
    """把帧流折成 RunOutcome；任何"不能确定完成"的情形都抛异常。

    本函数只收集 `submit_result` 的原始调用/结果对（`submission_calls`），
    **不**判提交是否被接受 —— 那是 `require_submission` 的门（B1/DS-02）。
    """
    events: list[dict[str, Any]] = []
    session_id: str | None = None
    cwd: str | None = None
    text = ""
    usage: dict[str, Any] | None = None
    terminals: dict[tuple, dict[str, Any]] = {}

    for raw in frames:
        event = parse_frame(raw)
        events.append(event)
        kind = event["type"]
        if kind == "session":
            session_id = event.get("sessionId") or session_id
            cwd = event.get("cwd") or cwd
            if expect_cwd is not None and cwd is not None and cwd != expect_cwd:
                raise IdentityMismatch(
                    "会话 cwd 与本次 attempt 不符：期望 %r 实际 %r" % (expect_cwd, cwd))
        elif kind == "status":
            phase = event.get("phase")
            if phase == "turn_end":
                reason = event.get("reason") or {}
                if not isinstance(reason, dict):
                    raise BadFrame("turn_end.reason 不是对象：%r" % (str(reason)[:80],))
                terminals.setdefault(_terminal_signature(reason), event)
            elif phase == "step_end" and isinstance(event.get("usage"), dict):
                usage = event["usage"]
        elif kind == "final":
            text = str(event.get("text") or "")
        # thinking/text/tool_call/tool_result/error：只保留在 events，不参与终态判定

    if session_id is None:
        raise NoTerminal("缺 session 身份帧（无法确认这是本次 attempt）")
    if not terminals:
        raise NoTerminal("无 turn_end（idle / 退出码 / 空 final 都不算完成）")
    if len(terminals) > 1:
        raise ConflictingTerminal(
            "出现 %d 个互相冲突的终态：%r" % (len(terminals), sorted(map(str, terminals))))

    submission_calls = _collect_submission_calls(events)
    reason = next(iter(terminals.values())).get("reason") or {}
    kind = reason.get("kind")
    error = reason.get("error") if isinstance(reason.get("error"), dict) else None
    if kind == "completed":
        return RunOutcome(status="completed", reason="completed", text=text,
                          usage=usage, session_id=session_id, cwd=cwd,
                          events=tuple(events), submission_calls=submission_calls)
    return RunOutcome(status="failed", reason=str(kind or "unknown"), text=text,
                      code=(error or {}).get("code"),
                      message=(error or {}).get("message"),
                      usage=usage, session_id=session_id, cwd=cwd,
                      events=tuple(events), submission_calls=submission_calls)


# ---------------------------------------------------------------- 提交门（B1 / DS-02）

def _verdict(event: dict[str, Any]) -> dict[str, Any]:
    """校验一条 `tool_result` 并取出 `{accepted, problems}`；不合规 ⇒ BadSubmission。"""
    status = event.get("status")
    if status != "completed":
        raise BadSubmission(
            "submit_result 的 tool_result status=%r（只接受 completed）" % (status,))
    raw = event.get("result")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BadSubmission(
                "submit_result 的 result 不是 JSON：%r（%s）" % (raw[:80], exc)) from None
    elif isinstance(raw, dict):
        parsed = raw
    else:
        raise BadSubmission(
            "submit_result 的 result 缺失或类型不符：%r" % (type(raw).__name__,))
    if not isinstance(parsed, dict):
        raise BadSubmission("submit_result 的 result 不是 JSON 对象：%r" % (str(parsed)[:80],))
    accepted = parsed.get("accepted")
    if not isinstance(accepted, bool):
        raise BadSubmission(
            "submit_result 的 result 缺 accepted 布尔字段：%r" % (str(parsed)[:80],))
    problems = parsed.get("problems", [])
    if not isinstance(problems, list) or any(not isinstance(p, str) for p in problems):
        raise BadSubmission(
            "submit_result 的 result.problems 必须是字符串列表：%r" % (str(problems)[:80],))
    return {"accepted": accepted, "problems": tuple(problems)}


def _submission(call: SubmissionCall, verdict: dict[str, Any], *, expect_task_id: str | None) -> Submission:
    """校验一次调用的 `input` 并造 `Submission`；缺字段/payload 非对象/身份不符 ⇒ 抛。"""
    data = call.input
    if not isinstance(data, dict):
        raise BadSubmission("submit_result 调用（callId=%r）缺 input 对象" % (call.call_id,))
    task_id, summary, payload = data.get("task_id"), data.get("summary"), data.get("payload")
    if not isinstance(task_id, str) or not task_id:
        raise BadSubmission("submit_result 输入缺 task_id（必须是非空字符串）")
    if not isinstance(summary, str) or not summary:
        raise BadSubmission("submit_result 输入缺 summary（必须是非空字符串）")
    if not isinstance(payload, dict):
        # 判据不变（payload 必须是对象）；错误信息补"哪个字段/期望什么/收到什么"，
        # 便于人一眼定位（S6 第 4 次真机把 payload 传成 JSON 字符串，模型看不到这条）。
        hint = ("（收到的是字符串：请把对象本身作为 payload 参数传入，不要 stringify）"
                if isinstance(payload, str) else "")
        raise BadSubmission(
            "submit_result 输入的 payload 必须是 JSON 对象（期望 object，实际 %r）%s"
            % (type(payload).__name__, hint))
    if expect_task_id is not None and task_id != expect_task_id:
        raise IdentityMismatch(
            "提交的 task_id 与本次 attempt 不符：期望 %r 实际 %r" % (expect_task_id, task_id))
    return Submission(task_id=task_id, summary=summary, payload=payload,
                      call_id=str(call.call_id), accepted=verdict["accepted"],
                      problems=verdict["problems"])


def _fingerprint(submission: Submission) -> tuple:
    try:
        body = json.dumps(submission.payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        body = repr(submission.payload)
    return (submission.task_id, submission.summary, body)


def require_submission(outcome: RunOutcome, *, expect_task_id: str | None = None) -> Submission:
    """提交门（纯函数）：`completed` 之外 + 恰一条被接受的提交才返回 `Submission`。

    判据（写死在这里，调用方不得第二套实现，红线 8）：
    - 无提交 / 0 条被接受 ⇒ `NoSubmission`（不得出候选）；
    - 多条不同提交 / 同一 callId 重复 / 多条被接受 ⇒ `ConflictingSubmissions`；
    - `tool_result` status 非 completed、result 非 JSON、缺字段、payload 非对象 ⇒ `BadSubmission`；
    - `expect_task_id` 给定且提交的 `task_id` 不等 ⇒ `IdentityMismatch`（身份 join）。
    """
    if outcome.status != "completed":
        raise ProtocolError(
            "终态 %r 不是 completed：提交门只对完成终态生效（失败终态另走显式失败）"
            % (outcome.reason,))
    calls = outcome.submission_calls
    if not calls:
        raise NoSubmission(
            "终态 completed 但模型没有调用 submit_result（0 条提交，不得出候选）")

    seen: set[str] = set()
    for call in calls:
        if call.call_id is None:
            raise BadSubmission("submit_result 调用缺 callId，无法与 tool_result 配对")
        if call.call_id in seen:
            raise ConflictingSubmissions(
                "同一 callId %r 出现多次 submit_result 调用" % (call.call_id,))
        seen.add(call.call_id)
        if not call.results:
            raise BadSubmission(
                "submit_result 调用（callId=%r）没有对应 tool_result" % (call.call_id,))
        if len(call.results) > 1:
            raise ConflictingSubmissions(
                "callId=%r 有 %d 条 tool_result（重复，无法确定哪条生效）"
                % (call.call_id, len(call.results)))

    submissions = [_submission(call, _verdict(call.results[0]), expect_task_id=expect_task_id)
                   for call in calls]
    distinct = {_fingerprint(submission) for submission in submissions}
    if len(distinct) > 1:
        raise ConflictingSubmissions(
            "出现 %d 条互相不同的提交，无法确定唯一候选" % (len(distinct),))
    accepted = [submission for submission in submissions if submission.accepted]
    if len(accepted) > 1:
        raise ConflictingSubmissions(
            "出现 %d 条被接受的提交（只允许恰一条）" % (len(accepted),))
    if not accepted:
        problems = [problem for submission in submissions for problem in submission.problems]
        if problems:
            raise NoSubmission(
                "submit_result 提交被引擎拒绝：problems=%r（0 条被接受，不得出候选）"
                % (problems,))
        raise NoSubmission(
            "终态 completed 但有 0 条被接受的 submit_result 提交（不得出候选）")
    return accepted[0]
