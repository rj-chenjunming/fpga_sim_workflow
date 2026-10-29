"""n15_run 节点实现。"""
from __future__ import annotations
from pathlib import Path
from typing import Any


async def run(data: Any, *, _SEED, _acquire_slot, _combine_counts, _identity_summary, _md5_file, _n15_job_id, aggregate_evidence, ctx_of) -> dict[str, Any]:
    """N15 全量/分层回归（**单作业串行**，替代旧的 for_each(n15_case)）。

    - real：G3 集逐例 `run_guarded.sh --mode full`，串成一个作业；图停在 JOB 中断；
      恢复后逐例证据落盘（经 `host.evidence` 聚合），**不再发 provisional=True**。
    - drill：显式 `simulated=True` no-op（accept_v1 的 G3=defer 不走本支；单测触发时也不抛错）。
    - 跨机 `run_tc.py` 未接入 ⇒ 在状态里如实登记 `cross_machine="run_tc.py 未接入（本机串行）"`。
    """
    ctx = ctx_of(data)
    node = "N15"
    s15 = data.get_state("n15_set") or {}
    cases = [str(c) for c in (s15.get("cases") or []) if c]
    g3 = s15.get("g3_decision")

    if ctx.mode == "drill":
        ctx.node_started(node)
        out = {
            "mode": ctx.mode, "simulated": True, "executed": False,
            "set": cases, "count": len(cases), "g3_decision": g3,
            "cross_machine": "run_tc.py 未接入（本机串行）",
            "note": "drill：不真跑仿真；本节点在 drill 下为显式 no-op（不是终值冒充）。",
        }
        await data.async_set_state("n15_result", out)
        ctx.node_finished(node, status="ok", detail={
            "simulated": True, "count": len(cases), "job_id": None,
            # P-32：drill 不真跑 ⇒ executed=False / will_really_run=False（不是"未下发"）
            "cases": [str(c) for c in cases],
            "executed": False,
            "failed_cases": [],
            "will_really_run": False,
            "source": "framework",
            "summary": (f"N15：drill 显式 no-op（未真跑回归），回归集 {len(cases)} 个用例，"
                        f"G3={g3 or '未签署'}"),
        })
        return out

    job_state = data.get_state("n15_job") or {}
    job_id = job_state.get("job_id")
    submitted_here = False

    if not job_id:
        ctx.node_started(node)
        if not cases:
            ctx.node_failed(node, message="N15 回归集为空")
            raise RuntimeError("N15：回归集为空（G3 集未产出）⇒ 不得声称已回归")
        # 目标集：优先用沙箱件（本轮已修订），否则用仓库原件（分层回归的本意）
        applied = {str(c.get("case")): c for c in (data.get_state("n6_applied") or {}).get("cases") or []}
        entries: list[dict[str, Any]] = []
        repo_root = Path(data.require_resource("repo_root"))
        for case in cases:
            item = applied.get(case)
            if item and Path(str(item.get("sandbox_path"))).is_file():
                entries.append({"case": case, "sandbox_path": str(item["sandbox_path"]),
                                "md5": str(item.get("md5_after") or "")})
            else:
                src = repo_root / "TESTLIB" / f"{case}.sv"
                if not src.is_file():
                    ctx.node_failed(node, message=f"回归用例不存在：{src}")
                    raise FileNotFoundError(f"N15：回归用例不存在：{src}")
                entries.append({"case": case, "sandbox_path": str(src), "md5": _md5_file(src)})
        gate = await _acquire_slot(data, ctx, job_id=_n15_job_id(ctx),
                                   tc=",".join(cases), seed=_SEED, node=node)
        if gate.get("retry"):
            return {"status": "slot_retry"}
        evidence_dir = ctx.run_dir / "evidence"
        summary_path = ctx.run_dir / "sandbox" / "n15_run_summary.tsv"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        command = ctx.environment.serial_command(entries, sandbox_root=ctx.run_dir / "sandbox",
                                        evidence_dir=evidence_dir, run_id=ctx.run_id,
                                        summary_path=summary_path)
        try:
            record = ctx.runner.submit(
                run_id=ctx.run_id, node=node, command=command,
                cwd=repo_root, tc=",".join(cases), seed=_SEED,
                note=f"mode=real cases={len(cases)} G3={g3}",
            )
        except BaseException:
            if ctx.admission is not None:
                ctx.admission.release(job_id=_n15_job_id(ctx))
            raise
        md5s = {c["case"]: c["md5"] for c in entries}
        job_state = {
            "job_id": record.job_id, "node": node, "phase": "running",
            "tc": ",".join(cases), "seed": _SEED, "cases": cases,
            "expected_cases": cases, "md5s": md5s, "target_set": "g3_set",
            "g3_decision": g3, "started_at": record.started_at,
            "log_path": record.log_path, "sandbox_root": str(ctx.run_dir / "sandbox"),
            "evidence_dir": str(evidence_dir), "summary_path": str(summary_path),
            "cross_machine": "run_tc.py 未接入（本机串行）",
        }
        await data.async_set_state("n15_job", job_state)
        ctx.event("job_submitted", node=node, status="running", detail=job_state,
                  refs=[record.log_path])
        # P-33：提交型节点也要有开始事件 + 作业日志 refs（与 job_submitted 同源）。
        ctx.node_started("N15_submit")
        ctx.node_finished("N15_submit", detail={
            "job_id": record.job_id, "cases": len(cases),
            "source": "kb_tool",
            "summary": (f"N15_submit：已提交回归作业 {record.job_id}，"
                        f"覆盖 {len(cases)} 个用例（G3={g3 or '未签署'}）⇒ 图转入停放"),
        }, refs=[record.log_path])
        submitted_here = True
        job_id = record.job_id

    # 停放：本调用刚提交的作业要停；从 SLOT 中断恢复后提交的也要停。
    # 只有「从 JOB 中断恢复」（job_state 已在、本调用未提交）才直接进入取结局分支。
    if submitted_here or not getattr(data, "is_resume", False):
        await data.async_pause_for(
            type="job_done",
            interrupt_id=f"JOB:{job_id}",
            payload={"job_id": job_id, "node": node, "cases": job_state.get("cases"),
                     "wait_reason": "N15 回归为外部长任务；图必须停放而非阻塞 handler。"},
            resume_to="self",
        )
        return {"status": "waiting", "job_id": job_id}

    # 恢复：权威相位 + 逐例证据（不信任 resume 载荷数字）
    try:
        try:
            phase = ctx.runner.poll(str(job_id)).phase
        except Exception:
            phase = (getattr(data, "resume", None) and (data.resume.value or {}).get("phase"))
        if phase == "dead":
            ctx.event("dead_job", node=node, status="dead", detail={"job_id": job_id})
            raise RuntimeError(f"N15：死任务 {job_id}，不得当成功")
        if phase == "cancelled":
            raise RuntimeError(f"N15：作业 {job_id} 被取消 ⇒ 不得当回归完成")
        if phase != "done":
            raise RuntimeError(f"N15：作业相位 {phase!r} 非终态 ⇒ 不得当完成")

        case_names = [str(c) for c in (job_state.get("expected_cases") or cases)]
        md5s = {str(k): str(v) for k, v in (job_state.get("md5s") or {}).items()}
        logs = ctx.environment.collect_logs(Path(str(job_state.get("evidence_dir"))), case_names)
        missing = [c for c in case_names if c not in logs]
        if missing:
            ctx.node_failed(node, message=f"N15 缺证据日志：{missing}")
            raise RuntimeError(f"N15：以下用例没有 run.log：{missing} ⇒ 不得声称回归完成")
        aggregate = aggregate_evidence(ctx, logs=logs, cases=case_names,
                                       expected_md5=md5s, seed=_SEED)
        per_case = aggregate.get("per_case") or {}
        verdict = aggregate.get("verdict") or {}
        out = {
            "job_id": job_id, "mode": ctx.mode, "simulated": False, "executed": True,
            "set": case_names, "count": len(case_names), "g3_decision": g3,
            "cases": per_case, "evidence": aggregate,
            "counts": _combine_counts(per_case),
            "verdict": verdict,
            "identity": _identity_summary(aggregate, md5s),
            "evidence_paths": {c: str(p) for c, p in logs.items()},
            "cross_machine": "run_tc.py 未接入（本机串行；5机×2LIC 跨机调度未实现）",
            "authority_note": "终值来自逐例日志聚合；不使用 provisional 临时值。",
        }
        await data.async_set_state("n15_result", out)
        status = "pass" if verdict.get("passed") else "fail"
        ctx.event("job_finished", node=node, status=status,
                  detail={"job_id": job_id, "cases": len(case_names),
                          "passed": verdict.get("passed")},
                  refs=[out["evidence_paths"][c] for c in case_names][:6])
        failed_cases = [
            c for c in case_names
            if not (((per_case.get(c) or {}).get("verdict") or {}).get("passed"))
        ]
        ctx.node_finished(node, status=status,
                          detail={"cases": [str(c) for c in case_names],
                                  "case_count": len(case_names),
                                  "executed": True,
                                  "failed_cases": failed_cases,
                                  "will_really_run": True,
                                  "passed": verdict.get("passed"),
                                  "job_id": job_id,
                                  "source": "kb_tool",
                                  "summary": (f"N15：回归作业 {job_id} 完成，"
                                              f"{len(case_names)} 个用例，"
                                              f"passed={verdict.get('passed')}，"
                                              f"身份一致={out['identity']['consistent']}")})
        return out
    finally:
        if ctx.admission is not None:
            handoff = ctx.admission.release(job_id=_n15_job_id(ctx))
            if handoff:
                ctx.event("admission_granted", node=node, status="handoff", detail=handoff)
