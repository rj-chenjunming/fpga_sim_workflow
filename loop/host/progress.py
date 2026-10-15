"""稳定应用事件投影（进度流的唯一出口）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §9。

两条硬约束（来自 stream-bridge 要求）：
1. **不得把 raw parser 路径当日志协议暴露给前端** —— 事件只有白名单 `kind`，
   日志原文只以 `refs`（路径 + 行号）出现。
2. 临时计数必须能被最终校验值覆盖并降级 `provisional`，否则前端会把
   中间值当结论。
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

#: 白名单。不在其中的 kind 一律拒绝写入（宁可报错，不要静默产生不可解释的事件）。
ALLOWED_KINDS: frozenset[str] = frozenset(
    {
        "run_started",
        "node_started",
        "node_finished",
        "node_failed",
        "job_submitted",
        "job_progress",
        "job_finished",
        "dead_job",
        "gate_pending",
        "gate_decided",
        "admission_queued",
        "admission_granted",
        "admission_refused",
        "warning",
        "run_finished",
    }
)


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    run_id: str
    node: str | None
    kind: str
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)
    provisional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProgressLog:
    """每个 run 一份 JSONL 事件流；进程内按 run 加锁串行追加。"""

    def __init__(self, events_dir: Path, run_id: str):
        self.dir = Path(events_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.path = self.dir / f"{run_id}.jsonl"
        self._lock = threading.Lock()
        self._seq = self._last_seq()

    def _last_seq(self) -> int:
        last = 0
        if self.path.is_file():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    last = max(last, int(json.loads(line).get("seq", 0)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
        return last

    def append(
        self,
        kind: str,
        *,
        node: str | None = None,
        status: str = "info",
        detail: dict[str, Any] | None = None,
        refs: Iterable[str] = (),
        provisional: bool = False,
        ts: float | None = None,
    ) -> Event:
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"progress kind 不在白名单内：{kind!r}；允许：{sorted(ALLOWED_KINDS)}")
        for ref in refs:
            text = str(ref)
            lowered = text.lower()
            for banned in ("parser", "token_stream", "raw_event", "delta_path"):
                if banned in lowered:
                    raise ValueError(f"refs 不得暴露解析器内部路径（命中 {banned!r}）：{text!r}")
        with self._lock:
            self._seq += 1
            event = Event(
                seq=self._seq,
                ts=time.time() if ts is None else ts,
                run_id=self.run_id,
                node=node,
                kind=kind,
                status=status,
                detail=detail or {},
                refs=[str(r) for r in refs],
                provisional=provisional,
            )
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
            return event

    def read(self, *, since_seq: int = 0) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.path.is_file():
            return out
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if int(item.get("seq", 0)) > since_seq:
                out.append(item)
        return out


def supervise_frozen_paths(paths: Iterable[Path]) -> list[str]:
    """给测试用的冻结见证：返回**内容 md5** 清单（不得只按 mtime 判定）。

    `doc/AGENTS.md` §4.3 明确禁止按 mtime 判「未改动」。
    """
    import hashlib

    digest = hashlib.md5()
    lines: list[str] = []
    for path in sorted({Path(p) for p in paths}):
        if not path.is_file():
            continue
        digest = hashlib.md5()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path}")
    return lines


__all__ = ["ALLOWED_KINDS", "Event", "ProgressLog", "supervise_frozen_paths", "os"]
