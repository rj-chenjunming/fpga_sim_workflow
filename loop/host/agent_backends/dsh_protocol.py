"""DSH headless NDJSON 协议层：帧解析、身份与终态判定（S1 / SPEC-REV-14 B4·B5）。

只做**纯解析与判定**：不启进程、不猜文本成功、不修补坏帧。
铁律（REV-13 §5.1 / REV-14 B5）：只有 `status.turn_end` 可以判完成；
`idle`、`messageId`、退出码、空 `final` 一律不放行；重复且冲突的终态必须失败。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Union

#: 允许出现的事件类型（fail-closed：未知类型直接 BadFrame，便于换版本时立刻暴露）
KNOWN_EVENT_TYPES = frozenset({"session", "status", "thinking", "text", "tool_call",
                               "tool_result", "final", "error"})


class ProtocolError(RuntimeError):
    """协议层失败基类（都出现在收口之前，调用方必须显式失败）。"""


class BadFrame(ProtocolError):
    """坏 JSON / 未知事件类型：拒绝并保留诊断，不忽略坏行。"""


class NoTerminal(ProtocolError):
    """没有 `turn_end`：不得把 idle / 退出码 0 / 空 final 当完成。"""


class ConflictingTerminal(ProtocolError):
    """出现互相冲突的多个终态。"""


class IdentityMismatch(ProtocolError):
    """会话身份（cwd/sessionId）与本次 attempt 不符。"""


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


def fold(frames: Iterable[Frame], *, expect_cwd: str | None = None) -> RunOutcome:
    """把帧流折成 RunOutcome；任何"不能确定完成"的情形都抛异常。"""
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
        # thinking/text/tool_call/tool_result/error：只保留在 events，不参与判定

    if session_id is None:
        raise NoTerminal("缺 session 身份帧（无法确认这是本次 attempt）")
    if not terminals:
        raise NoTerminal("无 turn_end（idle / 退出码 / 空 final 都不算完成）")
    if len(terminals) > 1:
        raise ConflictingTerminal(
            "出现 %d 个互相冲突的终态：%r" % (len(terminals), sorted(map(str, terminals))))

    reason = next(iter(terminals.values())).get("reason") or {}
    kind = reason.get("kind")
    error = reason.get("error") if isinstance(reason.get("error"), dict) else None
    if kind == "completed":
        return RunOutcome(status="completed", reason="completed", text=text,
                          usage=usage, session_id=session_id, cwd=cwd, events=tuple(events))
    return RunOutcome(status="failed", reason=str(kind or "unknown"), text=text,
                      code=(error or {}).get("code"),
                      message=(error or {}).get("message"),
                      usage=usage, session_id=session_id, cwd=cwd, events=tuple(events))
