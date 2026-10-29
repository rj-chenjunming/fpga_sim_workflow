"""n9_submit 节点实现。"""
from __future__ import annotations
from pathlib import Path
from typing import Any


async def run(data: Any, *, _REAL_CASE, _SEED, _acquire_slot, _drill_case_spec, _slot_job_id, _submit_drill_replay, _target_cases, _verify_targets, ctx_of) -> dict[str, Any]:
    """申请单槽 + 提交全跑作业。**返回后图即停放，执行不再是 `running`。**

    real：一个作业串行跑**全部**受影响用例（目标集取 n6_applied 冻结件）。
    drill：保持既有夹具形态（accept_v1 的断言依赖它）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N9")
    assert ctx.runner is not None
    run_dir: Path = ctx.run_dir
    evidence_dir = run_dir / "evidence"

    if ctx.mode == "drill":
        # SPEC-REV-05 R2：夹具带多例清单 ⇒ 回放全部用例；否则保持 legacy 单例分支。
        spec = _drill_case_spec(ctx)
        if spec:
            return await _submit_drill_replay(data, ctx, spec, run_dir=run_dir,
                                              evidence_dir=evidence_dir)
        gate = await _acquire_slot(data, ctx, job_id=_slot_job_id(ctx), tc=_REAL_CASE)
        if gate.get("retry"):
            return {"status": "slot_retry"}
        log_name = f"{ctx.run_id}_tc_pcie_rw_02_1_DRILLFIXTURE.log"
        dest = evidence_dir / log_name
        if ctx.scenario == "dead_job":
            command = "kill -9 $$"          # 无 rc 文件 ⇒ 必须是 dead，不得当成功
        elif ctx.scenario == "cancel":
            command = "sleep 120"
        else:
            src = ctx.fixture / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
            arch = evidence_dir / "archive"
            arch_copy = arch / dest.name
            prov = arch / "DRILL_FIXTURE_PROVENANCE.txt"
            # **必须放在子 shell 里跑 `set -e`**：JobRunner 会在命令之后追加
            # `__rc=$?; echo $__rc > <rc>`；若命令串顶层 `set -e` 因 cp 失败退出，
            # rc 文件就永远写不出来 ⇒ poll() 判 dead ⇒ 下游把「归档件已存在」误判成死任务。
            # 第二轮（G2 rework 回边再次 N9）的归档件是 444，直接 cp 会 Permission denied ⇒
            # 先 `rm -f` 目标再写（归档只增不改的语义由文件名/内容保证，本处是同一 drill 副本重建）。
            command = (
                "( set -e; "
                f"mkdir -p {str(arch)!r}; "
                f"rm -f {str(dest)!r} {str(arch_copy)!r}; "
                f"cp {str(src)!r} {str(dest)!r}; "
                f"cp {str(src)!r} {str(arch_copy)!r}; chmod 444 {str(arch_copy)!r}; "
                f"rm -f {str(prov)!r}; "
                f"printf '%s\\n%s\\n' "
                f"'DRILL FIXTURE：本归档目录由 drill 夹具产生，仅用于演示归档腿形态。' "
                f"'真实归档件由 kb/tools/run_guarded.sh 产出（只增不改 + 归档件只读）。' "
                f"> {str(prov)!r}; chmod 444 {str(prov)!r}"
                " )"
            )
        try:
            record = ctx.runner.submit(
                run_id=ctx.run_id, node="N9", command=command,
                cwd=Path(data.require_resource("repo_root")),
                tc=_REAL_CASE, seed=_SEED,
                note=f"mode={ctx.mode} scenario={ctx.scenario} DRILL FIXTURE",
            )
        except BaseException:
            # 铁律：acquire → submit 之间失败也必须释放单槽（否则后续全部卡在 SLOT）
            if ctx.admission is not None:
                ctx.admission.release(job_id=_slot_job_id(ctx))
            raise
        payload = {
            "job_id": record.job_id, "node": "N9", "phase": "running",
            "tc": _REAL_CASE, "seed": _SEED, "cases": [_REAL_CASE],
            "expected_cases": [_REAL_CASE], "md5s": {}, "target_set": "drill_fixture",
            "started_at": record.started_at, "log_path": record.log_path,
            "mode": ctx.mode, "scenario": ctx.scenario,
            "sandbox_root": str(run_dir / "sandbox"), "evidence_dir": str(evidence_dir),
        }
        ctx.pending["n9_job_id"] = record.job_id
        await data.async_set_state("n9_job", payload)
        ctx.event("job_submitted", node="N9", status="running", detail=payload, refs=[record.log_path])
        # P-33：提交型节点也要有开始事件（面板才有"开始/结束区间"，不再只有一步"结束"）。
        ctx.node_started("N9_submit")
        ctx.node_finished("N9_submit", detail={
            "job_id": record.job_id, "scenario": ctx.scenario,
            # R3-09：drill 也下发"覆盖用例数"（= 本轮 drill 目标用例数，与 real 分支同字段名），
            # 面板/summary 才能说"覆盖 N 个用例"而不是"覆盖用例数未下发"。
            "cases": len(payload.get("cases") or []),
            "source": "drill_fixture",
            "summary": (f"N9_submit：已提交全跑作业 {record.job_id}"
                        f"（drill 夹具，scenario={ctx.scenario}）⇒ 图转入停放"),
        }, refs=[record.log_path])
        return payload

    # ---------------------------------------------------------------- real
    cases = _target_cases(data)
    _verify_targets(cases)
    case_names = [c["case"] for c in cases]
    gate = await _acquire_slot(data, ctx, job_id=_slot_job_id(ctx),
                               tc=",".join(case_names), seed=_SEED)
    if gate.get("retry"):
        return {"status": "slot_retry"}

    summary_path = run_dir / "sandbox" / "n9_run_summary.tsv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    command = ctx.environment.serial_command(cases, sandbox_root=run_dir / "sandbox",
                                    evidence_dir=evidence_dir, run_id=ctx.run_id,
                                    summary_path=summary_path)
    try:
        record = ctx.runner.submit(
            run_id=ctx.run_id, node="N9", command=command,
            cwd=Path(data.require_resource("repo_root")),
            tc=",".join(case_names), seed=_SEED,
            note=f"mode=real cases={len(case_names)} sandbox_only",
        )
    except BaseException:
        if ctx.admission is not None:
            ctx.admission.release(job_id=_slot_job_id(ctx))
        raise
    md5s = {c["case"]: c["md5"] for c in cases}
    payload = {
        "job_id": record.job_id, "node": "N9", "phase": "running",
        "tc": ",".join(case_names), "seed": _SEED,
        "cases": case_names, "expected_cases": case_names, "md5s": md5s,
        "target_set": "n6_applied", "started_at": record.started_at,
        "log_path": record.log_path, "sandbox_root": str(run_dir / "sandbox"),
        "evidence_dir": str(evidence_dir), "summary_path": str(summary_path),
        "mode": ctx.mode, "scenario": ctx.scenario,
        "identity": {"cases": case_names, "md5s": md5s, "seed": _SEED, "run_id": ctx.run_id},
    }
    ctx.pending["n9_job_id"] = record.job_id
    await data.async_set_state("n9_job", payload)
    ctx.event("job_submitted", node="N9", status="running", detail=payload,
              refs=[record.log_path, str(summary_path)])
    ctx.node_started("N9_submit")
    ctx.node_finished("N9_submit", detail={
        "job_id": record.job_id, "cases": len(case_names),
        "source": "kb_tool",
        "summary": (f"N9_submit：已提交全跑作业 {record.job_id}，"
                    f"覆盖 {len(case_names)} 个沙箱用例 ⇒ 图转入停放"),
    }, refs=[record.log_path, str(summary_path)])
    return payload
