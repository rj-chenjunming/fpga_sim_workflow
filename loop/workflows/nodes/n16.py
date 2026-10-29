"""n16_promote 节点实现。"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any


async def run(data: Any, *, ctx_of, ARTIFACTS, _first_stderr_line, _load_json, _n16_result_path, _write_json, run_kb_tool) -> dict[str, Any]:
    """N16 晋升新基线（人触发、Host 原子执行）。

    **I4 由 `kb/tools/n16_promote.py` 无条件校验**（审计 #13/A18）：本 chunk 不再按
    G3 决策分流 —— 手工把 `G3=milestone/defer` 当成绕过口的漏洞就在这里堵住。

    身份（#21/C9）：`--trigger-by/--actor-kind` 一律取自 G3 的权威签署记录；
    缺失即 fail closed，**不再硬编码 human**。

    **默认 `--dry-run`**：真实晋升开关属于"人点晋升"入口（API/集成轮），
    本层任何情况下都不得真的写 `kb/baselines/`；真实基线上的正确行为是 rc=3 拒绝且零副作用。
    """
    ctx = ctx_of(data)
    ctx.node_started("N16")
    decisions = data.get_state("gate_decisions") or {}
    g3 = decisions.get("G3_regression_decision") or {}
    actor = g3.get("actor")
    actor_kind = g3.get("actor_kind") or (
        "human" if str(actor or "").startswith("human") else None
    )
    if not actor or actor_kind not in ("human", "host", "rehearsal", "model"):
        ctx.node_failed("N16", message="缺少 G3 签署记录（actor/actor_kind）⇒ 身份链断裂，拒绝晋升")
        raise PermissionError(
            "N16：晋升身份必须来自 G3 签署记录（actor/actor_kind）；缺失即拒绝（不得硬编码 human）"
        )

    # I7（#22/C5/C6）：N6↔N8 与 G2 返工**分开计数**，两侧统一 `>= limit` 即不得晋升。
    # 唯一账本 = case_state 台账（n6_n8_cycles）+ 执行状态（g2_rework_cycles，gates 写入）。
    ledger_doc = _load_json(ctx.run_dir / "case_states.json") or {}
    ledger_cycles = int(((ledger_doc.get("rework_cycles") or {}).get("n6_n8_cycles")) or 0)
    limit = int(
        data.get_state("rework_limit")
        or ((ledger_doc.get("rework_cycles") or {}).get("limit"))
        or 3
    )
    g2_cycles = int(data.get_state("g2_rework_cycles") or 0)
    if ledger_cycles >= limit or g2_cycles >= limit:
        ctx.node_failed(
            "N16",
            message=(f"I7：返工超限（n6_n8_cycles={ledger_cycles}, "
                     f"g2_rework_cycles={g2_cycles}, limit={limit}）⇒ 必须人工裁决"),
        )
        raise PermissionError(
            f"I7：返工计数已达/超过上限（n6_n8_cycles={ledger_cycles}, "
            f"g2_rework_cycles={g2_cycles}, limit={limit}）⇒ 不得晋升"
        )

    args = [
        "--run", ctx.run_id,
        "--trigger-by", str(actor),
        "--actor-kind", str(actor_kind),
        "--dry-run",
    ]
    if ctx.mode == "drill":
        args += ["--baselines-root", str(ctx.run_dir / "baseline_drill")]
        (ctx.run_dir / "baseline_drill").mkdir(parents=True, exist_ok=True)
    run = run_kb_tool("n16_promote.py", args)
    status = "ok" if run["rc"] == 0 else ("refused" if run["rc"] == 3 else "failed")
    result = {"cmd": run["cmd"], "rc": run["rc"], "mode": ctx.mode, "dry_run": True,
              "actor": actor, "actor_kind": actor_kind,
              "stdout_tail": run["stdout_tail"], "stderr_tail": run["stderr_tail"],
              "source": "kb_tool",
              # P-34：拒绝原因原文（面板据此写"晋升被拒：<原因>"，不靠 stderr 尾巴猜）
              "reason_line": _first_stderr_line(run["stderr_tail"]),
              "summary": (f"N16：dry-run 晋升 rc={run['rc']}（{status}），"
                          f"actor={actor}，actor_kind={actor_kind}")}
    # P-34：每次尝试都落结果件（只增不改；已存在则加序号），并把结果件列入 refs。
    result_path = _n16_result_path(ctx.run_dir)
    result["result_artifact"] = str(result_path)
    _write_json(result_path, {"schema": "loop/n16_result", "run_id": ctx.run_id, **result})
    await data.async_set_state("n16_promote", result)
    # §10.4：refs 只列**真实存在**的晋升留痕（不存在就不进 refs，不编造证据）。
    promote_refs = [
        str(path)
        for path in (ctx.run_dir / ARTIFACTS["n16"], ctx.run_dir / "promote_result.json",
                     result_path)
        if path.is_file()
    ]
    ctx.node_finished("N16", status=status, detail=result, refs=promote_refs)
    if run["rc"] not in (0, 3):
        raise RuntimeError(f"n16_promote rc={run['rc']}")
    return result
