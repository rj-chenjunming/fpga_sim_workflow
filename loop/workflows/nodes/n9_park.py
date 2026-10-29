"""n9_park 节点实现。"""
from __future__ import annotations
from pathlib import Path
from typing import Any


async def run(data: Any, *, _REAL_CASE, _SEED, _combine_counts, _drill_case_spec, _drill_replay_done, _identity_summary, _md5_file, _n9_detail, _slot_job_id, aggregate_evidence, counts_text, ctx_of) -> dict[str, Any]:
    """停在 `job_done` 中断上等外部完成。

    必须用 `resume_to="self"`：`resume_to="next"` 时 `pause_for` 的返回值是**中断描述符**，
    恢复载荷会直接流向下游 ⇒ **本 chunk 永远看不到作业结局**，
    死任务/取消会被静默当成继续（这是实测到的真 bug，不得再犯）。

    **恢复后以日志为权威重新取数**，不信任 resume 载荷里的数字
    （否则外部可以伪造"跑通"）。
    """
    ctx = ctx_of(data)
    job = data.get_state("n9_job") or {}
    job_id = job.get("job_id") or ctx.pending.get("n9_job_id")
    if not job_id:
        raise RuntimeError("N9 park 找不到 job_id：状态未落盘")

    if not getattr(data, "is_resume", False):
        await data.async_pause_for(
            type="job_done",
            interrupt_id=f"JOB:{job_id}",
            payload={"job_id": job_id, "node": "N9", "tc": job.get("tc"),
                     "log_path": job.get("log_path"), "cases": job.get("cases"),
                     "wait_reason": "全跑为外部长任务；图必须停放而非阻塞 handler。"},
            resume_to="self",
        )
        return {"status": "waiting", "job_id": job_id}

    payload = (getattr(data.resume, "value", None) or {}) if getattr(data, "resume", None) else {}
    try:
        try:
            phase = ctx.runner.poll(job_id).phase
        except Exception:
            phase = payload.get("phase")
        if payload.get("phase") and phase != payload.get("phase"):
            ctx.event("warning", node="N9", status="phase_disagreement",
                      detail={"job_id": job_id, "payload_phase": payload.get("phase"),
                              "authority_phase": phase,
                              "rule": "以权威（rc 文件 + 进程存活）为准，载荷只作提示"})
        if phase == "dead":
            ctx.event("dead_job", node="N9", status="dead", detail=payload)
            raise RuntimeError(f"死任务 {job_id}：进程已终结但未留下 rc ⇒ 不得当成功，走失败分支。")
        if phase == "cancelled":
            ctx.event("warning", node="N9", status="cancelled", detail=payload)
            raise RuntimeError(f"作业 {job_id} 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续。")
        if phase not in ("done",):
            raise RuntimeError(
                f"作业 {job_id} 的相位是 {phase!r}（既非 done 也非 dead/cancelled）⇒ "
                "不得按完成处理；按失败终止本轮。"
            )

        if ctx.mode == "drill":
            spec = _drill_case_spec(ctx)
            if spec:
                return await _drill_replay_done(ctx, data, job, job_id, payload, spec)
            ev = ctx.evidence()
            counts = ev.get("counts") or {}
            out = {
                "job_id": job_id,
                "resume_payload": payload,
                "evidence": ev,
                "counts": counts,
                "target_cases": job.get("cases") or [_REAL_CASE],
                "cases": {_REAL_CASE: {"present": ev.get("present"), "counts": counts,
                                       "verdict": ev.get("verdict"),
                                       "path": ev.get("path")}},
                "verdict": ev.get("verdict") or {},
                "authority_note": "resume 载荷只作提示；口径一/口径二/印记一律由日志重新抽取。",
            }
            ctx.pending["n9_result"] = out
            await data.async_set_state("n9_result", out)
            status = "pass" if counts.get("both_zero") else "fail"
            ctx.event("job_finished", node="N9", status=status,
                      detail={"job_id": job_id, "rc": payload.get("rc"),
                              "koutou1": (counts.get("koutou1") or {}).get("value"),
                              "koutou2": (counts.get("koutou2") or {}).get("value")},
                      refs=[ev.get("path", "")])
            ctx.node_finished("N9", status=status,
                              detail={"koutou1": (counts.get("koutou1") or {}).get("value"),
                                      "koutou2": (counts.get("koutou2") or {}).get("value"),
                                      "cases": len(out["target_cases"]),
                                      "job_id": job_id,
                                      **_n9_detail(
                                          cases=out.get("cases"),
                                          identity={
                                              "consistent": None, "mismatches": [],
                                              "source": ("drill_fixture：夹具日志无身份头，"
                                                         "未做身份四方同值"),
                                          }),
                                      "source": "drill_fixture",
                                      "summary": (f"N9：全跑作业 {job_id} 完成（drill 夹具），"
                                                  f"{counts_text(counts)}，"
                                                  f"both_zero={counts.get('both_zero')}")},
                              refs=[ev.get("path", "")])
            return out

        # ---------------------------------------------------------------- real
        case_names = [str(c) for c in (job.get("expected_cases") or job.get("cases") or [])]
        md5s = {str(k): str(v) for k, v in (job.get("md5s") or {}).items()}
        if not case_names:
            raise RuntimeError("N9 real 恢复后找不到目标用例集（n9_job 未落 cases）")
        # 沙箱件在跑之前/跑之后都必须与冻结值一致（审的 md5 == 跑的 md5）
        for case in case_names:
            sandbox = Path(str(job.get("sandbox_root") or "")) / "TESTLIB" / f"{case}.sv"
            if not sandbox.is_file():
                raise RuntimeError(f"N9：沙箱件不存在 {sandbox}（禁止回退未修订 TESTLIB）")
            if md5s.get(case) and _md5_file(sandbox) != md5s[case]:
                raise RuntimeError(f"N9：{case} 沙箱 md5 在跑后被改动 ⇒ 证据作废")
        logs = ctx.environment.collect_logs(Path(str(job.get("evidence_dir") or ctx.run_dir / "evidence")),
                                  case_names)
        missing = [c for c in case_names if c not in logs]
        if missing:
            # 跑挂了也要「采证并三分类」，但**没有日志**就没有证据 —— 不得默认通过
            ctx.node_failed("N9", message=f"缺 {len(missing)} 例证据日志：{missing}")
            raise RuntimeError(
                f"N9：以下用例没有 run.log（{missing}）⇒ 不得把'没跑出证据'当通过"
            )
        aggregate = aggregate_evidence(ctx, logs=logs, cases=case_names,
                                       expected_md5=md5s, seed=_SEED)
        per_case = aggregate.get("per_case") or {}
        not_present = [c for c in case_names if not (per_case.get(c) or {}).get("present")]
        if not_present:
            ctx.node_failed("N9", message=f"证据不可用（present=false）：{not_present}")
            raise RuntimeError(f"N9：证据不可用 {not_present} ⇒ 不得继续")
        counts = _combine_counts(per_case)
        verdict = aggregate.get("verdict") or {}
        identity = _identity_summary(aggregate, md5s)
        out = {
            "job_id": job_id,
            "resume_payload": payload,
            "target_cases": case_names,
            "run_md5s": md5s,
            "cases": per_case,
            "evidence": aggregate,
            "counts": counts,
            "verdict": verdict,
            "identity": identity,
            "evidence_paths": {c: str(p) for c, p in logs.items()},
            "authority_note": ("resume 载荷只作提示；两套口径/印记/身份由 host.evidence 聚合"
                               "（run_guarded 身份头）重新抽取。"),
        }
        ctx.pending["n9_result"] = out
        await data.async_set_state("n9_result", out)
        status = "pass" if verdict.get("passed") else "fail"
        ctx.event("job_finished", node="N9", status=status,
                  detail={"job_id": job_id, "rc": payload.get("rc"),
                          "cases": len(case_names),
                          "koutou1": (counts.get("koutou1") or {}).get("value"),
                          "koutou2": (counts.get("koutou2") or {}).get("value"),
                          "identity_consistent": identity["consistent"]},
                  refs=[out["evidence_paths"][c] for c in case_names][:6])
        ctx.node_finished("N9", status=status,
                          detail={"cases": len(case_names),
                                  "koutou1": (counts.get("koutou1") or {}).get("value"),
                                  "koutou2": (counts.get("koutou2") or {}).get("value"),
                                  "job_id": job_id,
                                  **_n9_detail(cases=per_case, identity=identity),
                                  "source": "kb_tool",
                                  "summary": (f"N9：全跑作业 {job_id} 完成，"
                                              f"{len(case_names)} 个用例，"
                                              f"{counts_text(counts)}，"
                                              f"身份一致={identity['consistent']}")},
                          refs=[out["evidence_paths"][c] for c in case_names][:6])
        return out
    finally:
        # 铁律：成功 / 失败 / 取消都必须释放单槽，且幂等。
        if ctx.admission is not None:
            handoff = ctx.admission.release(job_id=_slot_job_id(ctx))
            if handoff:
                ctx.event("admission_granted", node="N9", status="handoff", detail=handoff)
