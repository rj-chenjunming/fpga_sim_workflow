#!/usr/bin/env python3
"""F07：Agent 历史读取的受控测量（**先测量，再决定缓存/分页**）。

测什么：`host/agent_control.read_view` 在小/中/大历史样本下的
读取字节、响应体大小、耗时分布（min/median/p95）、事件数、CPU 时间与 tracemalloc 峰值内存。
不测什么：真实 provider 的控制回执延迟（需要活跃 model 会话与真实 provider，本机不可运行）。

用法（只写系统临时目录，不写仓库/环境）：
  .venv/bin/python spikes/measure_agent_read.py            # 三档默认样本
  .venv/bin/python spikes/measure_agent_read.py --repeat 30
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP))

from host import agent_control as C  # noqa: E402
from host import agent_memory as AM  # noqa: E402
from host.progress import ProgressLog  # noqa: E402
from services.contracts import KbSources  # noqa: E402
from workflows.context import RunCtx  # noqa: E402

NODE = "N3"

#: (名字, attempt 数, 单条输入约字节, 事件数)
SAMPLES = [
    ("small", 1, 1_000, 10),
    ("medium", 10, 20_000, 100),
    ("large", 50, 200_000, 1_000),
]


def build_sample(root: Path, attempts: int, input_bytes: int, events: int) -> tuple[Path, Path]:
    run = root / "runs" / "RUN-F07-MEASURE"
    run.mkdir(parents=True, exist_ok=True)
    progress = ProgressLog(root / "events", run.name)
    ctx = RunCtx(run.name, run, "standin", "happy", KbSources.from_workspace(root), progress)
    payload = "x" * max(1, input_bytes)
    for _ in range(attempts):
        attempt = AM.Attempt(ctx, NODE, {"prompt_key": "n3_digest", "input": {"diff": payload}})
        attempt.finish("validated", payload={"summary": "s"}, validation={"ok": True})
    for index in range(events):
        progress.append("node_started", node=NODE, status="started",
                         ts=float(index), detail={"mode": "standin"})
    return run, progress.path


def _api_events(progress_path: Path) -> list[dict]:
    """与 `GET /api/runs/{id}/agents/{node}` 相同的事件过滤（node 或 <node>_ 前缀）。"""
    events: list[dict] = []
    if progress_path.is_file():
        for line in progress_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("node") == NODE or str(event.get("node", "")).startswith(NODE + "_"):
                events.append(event)
    return events


def measure(run: Path, progress_path: Path, repeat: int) -> dict:
    latencies: list[float] = []
    view: dict = {}
    tracemalloc.start()
    baseline = tracemalloc.get_traced_memory()[0]
    # CPU 用**本次测量循环的增量**，不是进程累计（复核必改 1：
    # 累计值含样本构造与前面档位，会出现 CPU > wall 的自相矛盾）。
    cpu_started = time.process_time()
    for _ in range(repeat):
        started = time.perf_counter()
        view = C.read_view(run, NODE)
        view = {**view, "events": _api_events(progress_path)}
        latencies.append((time.perf_counter() - started) * 1000.0)
    cpu_ms = (time.process_time() - cpu_started) * 1000.0 / max(1, repeat)
    peak = tracemalloc.get_traced_memory()[1] - baseline
    tracemalloc.stop()
    response_bytes = len(json.dumps(view, ensure_ascii=False).encode("utf-8"))
    record_bytes = 0
    for path in sorted((run / "agent_calls" / NODE).rglob("*")):
        if path.is_file():
            record_bytes += path.stat().st_size
    ordered = sorted(latencies)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {
        "attempts": len(view.get("attempts") or []),
        "events_in_view": len(view.get("events") or []),
        "record_bytes": record_bytes,
        "response_bytes": response_bytes,
        "latency_ms_min": round(ordered[0], 3),
        "latency_ms_median": round(statistics.median(ordered), 3),
        "latency_ms_p95": round(p95, 3),
        "cpu_ms_per_read": round(cpu_ms, 3),
        "tracemalloc_peak_bytes": peak,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=20)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="f07-measure-"))
    try:
        results = []
        for name, attempts, input_bytes, events in SAMPLES:
            root = work / name
            run, events_path = build_sample(root, attempts, input_bytes, events)
            row = {"sample": name, "attempts_target": attempts, "input_bytes": input_bytes,
                   "events_target": events, "events_file_bytes": events_path.stat().st_size}
            row.update(measure(run, events_path, args.repeat))
            results.append(row)
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
        print("\n# 测量口径")
        print("- read_view：单次读取当前最新 attempt 的完整视图（含全部 attempts 摘要、控制记录与"
              "与 API 同口径过滤后的事件列表）。")
        print("- latency：wall clock，重复 %d 次；cpu_ms_per_read 用测量循环内的"
              " process_time 增量/repeat（不含样本构造）。" % args.repeat)
        print("- tracemalloc_peak_bytes：measure 段内的净峰值（不含样本构造）。")
        print("- 控制回执延迟未测：需要活跃 model 会话与真实 provider（本机不可运行）。")
        print(f"- 临时样本目录：{work}")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
