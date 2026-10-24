"""U2-a（SPEC-REV-07 / SPEC-04 §6.9）：SSE 运行投影流的生成逻辑。

只做传输三件事：帧格式、变更检测、心跳节拍。投影本身仍由 `RunManager.run_view`
唯一产出（调用方注入 `fetch_view`）；本模块不构造第二份判据、不写任何文件、
不新增事件 kind。`sleep` 与 `fetch_view` 可注入，测试不真实等待（SPEC-04 §6.9）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, AsyncIterator, Awaitable, Callable

#: 每次投影刷新都会变、但**不代表内容变化**的字段；不参与变更检测（SPEC-04 §6.9）。
VOLATILE_KEYS: tuple[str, ...] = ("updated_at",)


def sse_frame(event: str, data: str) -> str:
    """一帧 SSE：`event:` 行 + 逐行 `data:` 前缀 + 空行。多行 data 按规范逐行前缀。"""
    lines = "".join("data: " + line + "\n" for line in (data.splitlines() or [""]))
    return f"event: {event}\n{lines}\n"


def payload_signature(view: dict[str, Any]) -> str:
    """规范化 JSON 签名（排除易变字段）：签名不变 ⇒ 视图内容未变 ⇒ 不推送。"""
    cleaned = {k: v for k, v in view.items() if k not in VOLATILE_KEYS}
    canon = json.dumps(cleaned, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


async def run_view_stream(
    fetch_view: Callable[[], Awaitable[dict[str, Any]]],
    *,
    interval_s: float = 1.0,
    heartbeat_s: float = 15.0,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> AsyncIterator[str]:
    """SSE 生成器：首拍必推；此后仅签名变化时推 `run_view`，节拍到点发 `: ping`。

    - `fetch_view` 首拍即抛 `KeyError` ⇒ 推 `error` 后结束（路由层应先 404，此处为纵深防御）；
    - 流建立后 run 消失（后续抛 `KeyError`）⇒ 推 `gone` 后正常结束，不伪装存活；
    - 客户端断开由 Starlette 关闭生成器（GeneratorExit），无泄漏路径。
    """
    do_sleep = sleep or asyncio.sleep
    beats_per_ping = max(1, round(heartbeat_s / interval_s))
    last_sig: str | None = None
    beats = 0
    while True:
        try:
            view = await fetch_view()
        except KeyError:
            if last_sig is None:
                yield sse_frame("error", json.dumps({"error": "unknown run"}))
            else:
                yield sse_frame("gone", json.dumps({"error": "run disappeared"}))
            return
        sig = payload_signature(view)
        if sig != last_sig:
            last_sig = sig
            yield sse_frame("run_view", json.dumps(view, ensure_ascii=False, default=str))
        beats += 1
        if beats >= beats_per_ping:
            beats = 0
            yield ": ping\n\n"
        await do_sleep(interval_s)
