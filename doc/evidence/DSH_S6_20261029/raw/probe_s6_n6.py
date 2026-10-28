"""S6 真机 N6 候选导入探针（**最多 1 次真实调用**；--dry-run 不调模型）。

用法（授权后）：
  cd loop && LOOP_LLM_MODE=live .venv/bin/python .logs/s6/probe_s6_n6.py \
      --ws .logs/s6/ws --raw ../doc/evidence/DSH_S6_20261029/raw
不写 ENV_ROOT；密钥只在内存（输出统一脱敏）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# 从 loop/ 运行：CWD 即包根；状态根放探针目录（不写 loop/state）。
sys.path.insert(0, os.environ.get("S6_LOOP_DIR") or os.getcwd())
_STATE = Path(os.environ.get("S6_LOOP_DIR") or os.getcwd()).resolve() / ".logs" / "s6" / "state"
os.environ.setdefault("LOOP_STATE_ROOT", str(_STATE))


from host import paths as P  # noqa: E402
from host.progress import ProgressLog  # noqa: E402
from services.contracts import KbSources  # noqa: E402
from workflows.chunks import host_steps, model_steps as M  # noqa: E402
from workflows.chunks import n6_facts  # noqa: E402
from workflows.context import RunCtx  # noqa: E402

FIXTURE = P.KB_RUNS / "RUN-20261015-120626"


class Data:
    def __init__(self, ctx: RunCtx, repo_root: Path, state: dict[str, Any] | None = None):
        self.resources = {"repo_root": repo_root, "loop_ctx": ctx}
        self.state = dict(state or {})
        self.emitted: list[Any] = []

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        return self.resources[key]

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    async def async_emit(self, key: str, value: Any) -> None:
        self.emitted.append(key)


def redact(text: str) -> str:
    for value in (os.environ.get("PUBLIC_API_KEY"), os.environ.get("LOOP_LLM_API_KEY")):
        if value and len(value) > 8:
            text = text.replace(value, "[redacted]")
    try:
        from host import model_provider as MP

        secret = getattr(MP.resolve(), "_api_key", None)
        if secret and len(secret) > 8:
            text = text.replace(secret, "[redacted]")
    except Exception:  # noqa: BLE001 - 脱敏尽力而为，不因解析失败中断
        pass
    return text


def prepare(ws: Path, run_id: str) -> tuple[RunCtx, Path, list[dict[str, Any]]]:
    run_dir = ws / "runs" / run_id
    if run_dir.exists():
        raise SystemExit("run_dir 已存在（拒绝复用 run 身份）：%s" % run_dir)
    run_dir.mkdir(parents=True)
    # 探针材料最小化（Lead 第 3 次授权条件 2）：只留 n2 diff + 最小 n5（build_n6_targets 必需）
    # + 单条 doc_entries（Host 侧 marker 校验必需）。**不塞 345 KB 的 n5_impact**。
    shutil.copy2(FIXTURE / "n2_diff.json", run_dir / "n2_diff.json")
    n5_full = json.loads((FIXTURE / "n5_impact.json").read_text(encoding="utf-8"))
    items = [m for m in (n5_full.get("must_change") or []) if isinstance(m, dict)]
    keep = {k: items[0][k] for k in ("case", "file", "line", "entry_id", "segment", "offset")
            if items[0].get(k) is not None}
    (run_dir / "n5_impact.json").write_text(
        json.dumps({"must_change": [keep], "must_change_count": 1}, ensure_ascii=False),
        encoding="utf-8")
    marker_lines = [line for line in (FIXTURE / "bundle" / "doc_entries.jsonl")
                    .read_text(encoding="utf-8").splitlines() if "fpga_date" in line]
    (run_dir / "doc_entries.jsonl").write_text(
        (marker_lines[0] if marker_lines else "{}") + "\n", encoding="utf-8")
    kb_root = ws / "kb"
    (kb_root / "conflicts").mkdir(parents=True, exist_ok=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        '{"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []}', encoding="utf-8")
    ctx = RunCtx(run_id=run_id, run_dir=run_dir, mode="real", scenario="happy",
                 kb=KbSources.from_workspace(kb_root),
                 progress=ProgressLog(ws / "events", run_id))
    targets = n6_facts.build_n6_targets(ctx, Data(ctx, P.ENV_ROOT))
    return ctx, P.ENV_ROOT, targets


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=".logs/s6/ws")
    ap.add_argument("--raw", default="../doc/evidence/DSH_S6_20261029/raw")
    ap.add_argument("--run-id", default="RUN-20261029-S6-02")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ws = Path(args.ws).resolve()
    raw = Path(args.raw).resolve()
    raw.mkdir(parents=True, exist_ok=True)

    run_id, timeout_s = args.run_id, float(args.timeout)
    # Lead 条件 1：上限必须真的生效（外层 cap + 断言；不靠"说说而已"）
    assert 0 < timeout_s <= 300.0, "timeout cap 必须 >0 且 ≤300 s，实际 %r" % (timeout_s,)
    ctx, repo_root, targets = prepare(ws, run_id)
    target = targets[0]
    print("target:", target.get("case"), "| file:", target.get("file"),
          "| line:", (target.get("excerpt") or {}).get("line"))
    print("targets:", len(targets), "| repo_root:", repo_root)
    data = Data(ctx, repo_root)
    if args.dry_run:
        print("workspace hint:", M._workspace_hint(ctx, targets))
        print("dry-run OK：输入可构造、未调用模型；run_dir =", ctx.run_dir)
        return 0

    if os.environ.get("LOOP_LLM_MODE", "").strip().lower() != "live":
        raise SystemExit("必须显式 LOOP_LLM_MODE=live 才允许真实调用")

    started = time.time()
    exit_kind, error = "completed", None
    try:
        out = await asyncio.wait_for(M.n6_author(data), timeout_s)
    except asyncio.TimeoutError:
        exit_kind, error = "failed", f"timeout>{timeout_s}s（已停止，不重发）"
        out = {}
    except Exception as exc:  # noqa: BLE001 - 失败如实记录、不掩盖
        exit_kind, error = "failed", f"{type(exc).__name__}: {exc}"
        out = {}
    wall_s = round(time.time() - started, 3)

    usage: dict[str, Any] = {"inputTokens": "unknown", "outputTokens": "unknown",
                             "totalTokens": "unknown", "cacheReadTokens": "unknown"}
    session_id, backend, attempt_rel = "unknown", "unknown", "unknown"
    calls = sorted((ctx.run_dir / "agent_calls" / "N6").glob("attempt-*"))
    if calls:
        attempt_rel = calls[0].relative_to(ctx.run_dir).as_posix()
        from host import agent_memory as AM

        try:
            rec = AM.verify_attempt(calls[0])
            payload = rec["result"].get("payload") or {}
            got = payload.get("usage") or {}
            if isinstance(got, dict) and got:
                usage = {k: got.get(k, "unknown") for k in usage}
            session_id = payload.get("session_id") or "unknown"
            backend = payload.get("provider") or "unknown"
        except (OSError, ValueError):
            pass

    candidate_files: list[str] = []
    workspace = sorted((ctx.run_dir / "agent_workspaces" / "N6").glob("attempt-*"))
    if workspace:
        cand = workspace[0] / "candidate"
        candidate_files = sorted(p.relative_to(cand).as_posix()
                                 for p in cand.rglob("*") if p.is_file())
    keys = (host_steps.CANDIDATE_ROOT_KEY, host_steps.CANDIDATE_MANIFEST_KEY,
            host_steps.CANDIDATE_BASELINE_KEY, host_steps.CANDIDATE_EXECUTION_KEY)
    channel = {k: out.get(k) for k in keys} if out else {}
    params = {"run_id": run_id, "target": {k: target.get(k) for k in ("case", "file")},
              "repo_root": str(repo_root), "backend": backend,
              "candidate_files": candidate_files, "channel": channel,
              "wall_s": wall_s, "timeout_s": timeout_s}
    (raw / "n6_params.json").write_text(
        json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")

    applied: dict[str, Any] = {}
    if out:
        try:
            await data.async_set_state("n6_targets", {"targets": [target]})
            applied = await host_steps.n6_apply(data)
        except Exception as exc:  # noqa: BLE001 - 导入失败也是证据（显式失败、不回退）
            applied = {"status": "failed", "error": redact(f"{type(exc).__name__}: {exc}")}
    result = {"run_id": run_id, "exit": exit_kind,
              "error": redact(str(error)) if error else None,
              "wall_s": wall_s, "usage": usage, "session_id": session_id,
              "candidate_files": candidate_files, "channel": channel,
              "apply_status": applied.get("status"),
              "apply_cases": [{k: c.get(k) for k in ("case", "source", "md5_after")}
                              for c in (applied.get("cases") or [])],
              "candidate_import": applied.get("candidate_import"),
              "apply_error": redact(str(applied.get("error") or "")) if applied.get("status") == "failed" else None}
    (raw / "n6_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    line = {"attempt_key": f"{run_id}/N6/1", "exit": exit_kind, "wall_s": wall_s,
            "usage": usage, "session_id": session_id, "backend": backend,
            "attempt_record": attempt_rel,
            "stop_confirmed": channel.get(host_steps.CANDIDATE_EXECUTION_KEY) if channel else None,
            "candidate_files": candidate_files, "apply_status": applied.get("status"),
            "error": redact(str(error)) if error else None}
    with (raw / "attempts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    print("RESULT:", json.dumps(line, ensure_ascii=False))
    return 0 if exit_kind == "completed" and applied.get("status") == "applied" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
