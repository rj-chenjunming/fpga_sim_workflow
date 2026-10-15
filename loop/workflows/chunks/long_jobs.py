"""长任务节点：N9 全跑（提交 + 停放）/ N15 分层回归。

**这是本层最关键的形状**（spec §6）：
N9 不阻塞在 handler 里，而是「申请单槽 → 提交外部作业 → 图停在 `pause_for` 中断」。
理由：快照中若存在 `running` 帧，`load` 会 fail-closed
（`agently-triggerflow/references/recovery.md:75-77`）；一次全跑实测 ≈19 min，
修订后可达 22.8 h，阻塞式 handler 会让重启恢复直接不成立。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from host import paths as P

from ..context import RunCtx, ctx_of

#: 真实 N9 的对象用例（drill 夹具的全跑证据也来自它）
_REAL_CASE = "tc_pcie_rw_02"

#: drill 情景：真实子进程 + 真实产物，只有工作负载是夹具（必须标注 DRILL FIXTURE）。
SCENARIOS = ("happy", "dead_job", "cancel")


def _slot_job_id(ctx: RunCtx) -> str:
    return f"N9-{ctx.run_id}"


async def _acquire_slot(data: Any, ctx: RunCtx) -> dict[str, Any]:
    """申请单槽；排队时停在 `slot_wait` 中断上，用 `resume_to="self"` 重入本 chunk。"""
    assert ctx.admission is not None, "drill/real 运行都必须注入 admission"
    result = ctx.admission.acquire(job_id=_slot_job_id(ctx), tc="tc_pcie_rw_02", seed="1")
    if result.granted:
        ctx.event("admission_granted", node="N9", status="ok",
                  detail={"job_id": _slot_job_id(ctx), "reason": result.reason})
        return {"granted": True}
    if result.state == "queued":
        ctx.event("admission_queued", node="N9", status="waiting",
                  detail={"position": result.position, "reason": result.reason})
        await data.async_pause_for(
            type="slot_wait",
            interrupt_id=f"SLOT:{ctx.run_id}",
            payload={"queue_position": result.position, "reason": result.reason},
            resume_to="self",
        )
        return {"granted": False, "retry": True, "position": result.position}
    ctx.event("admission_refused", node="N9", status="refused",
              detail={"reason": result.reason, "holder": result.holder})
    raise PermissionError(f"单槽准入被拒：{result.reason}（N9-3：不认识的锁格式不得自动清理）")


async def n9_submit(data: Any) -> dict[str, Any]:
    """申请单槽 + 提交全跑作业。**返回后图即停放，执行不再是 `running`。**"""
    ctx = ctx_of(data)
    ctx.node_started("N9")
    gate = await _acquire_slot(data, ctx)
    if gate.get("retry"):
        return {"status": "slot_retry"}

    assert ctx.runner is not None
    run_dir: Path = ctx.run_dir
    log_name = f"{ctx.run_id}_tc_pcie_rw_02_1_DRILLFIXTURE.log"
    dest = run_dir / "evidence" / log_name

    if ctx.mode == "drill":
        if ctx.scenario == "dead_job":
            command = "kill -9 $$"          # 无 rc 文件 ⇒ 必须是 dead，不得当成功
        elif ctx.scenario == "cancel":
            command = "sleep 120"
        else:
            src = ctx.fixture / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
            arch = run_dir / "evidence" / "archive"
            arch_copy = arch / dest.name
            prov = arch / "DRILL_FIXTURE_PROVENANCE.txt"
            # drill 不跑 guard。为让界面能演示"归档腿已产出"的形态，
            # 这里按 guard 的**后置条件**造一份只读归档件，并留下来源标记；
            # 真实归档件由 kb/tools/run_guarded.sh 产出（带身份头）。
            command = (
                f"set -e; mkdir -p {str(arch)!r}; "
                f"cp {str(src)!r} {str(dest)!r}; "
                f"cp {str(src)!r} {str(arch_copy)!r}; chmod 444 {str(arch_copy)!r}; "
                f"printf '%s\\n%s\\n' "
                f"'DRILL FIXTURE：本归档目录由 drill 夹具产生，仅用于演示归档腿形态。' "
                f"'真实归档件由 kb/tools/run_guarded.sh 产出（只增不改 + 归档件只读）。' "
                f"> {str(prov)!r}; chmod 444 {str(prov)!r}"
            )
    else:
        # **真实路径必须走 evidence 包装层**：身份头 + 先归档再删 + 中止自愈 + 串行锁。
        # 直接调 run_uvs_new.sh 会绕过全部四项，`evidence/archive/` 必然为空（E-2 的另一半）。
        case_file = run_dir / "sandbox" / "TESTLIB" / f"{_REAL_CASE}.sv"
        if not case_file.is_file():
            case_file = Path(data.require_resource("repo_root")) / "TESTLIB" / f"{_REAL_CASE}.sv"
        command = (
            f"bash {str(P.KB_TOOLS / 'run_guarded.sh')!r} "
            f"--case-file {str(case_file)!r} --case-name {_REAL_CASE} --seed 1 "
            f"--mode full "
            f"--sandbox-root {str(run_dir / 'sandbox')!r} "
            f"--evidence-dir {str(run_dir / 'evidence')!r} "
            f"--run {ctx.run_id}"
        )

    record = ctx.runner.submit(
        run_id=ctx.run_id,
        node="N9",
        command=command,
        cwd=Path(data.require_resource("repo_root")),
        tc="tc_pcie_rw_02",
        seed="1",
        note=f"mode={ctx.mode} scenario={ctx.scenario} DRILL FIXTURE",
    )
    payload = {
        "job_id": record.job_id,
        "node": "N9",
        "phase": "running",
        "tc": "tc_pcie_rw_02",
        "seed": "1",
        "started_at": record.started_at,
        "log_path": record.log_path,
        "mode": ctx.mode,
        "scenario": ctx.scenario,
    }
    ctx.pending["n9_job_id"] = record.job_id
    await data.async_set_state("n9_job", payload)
    ctx.event("job_submitted", node="N9", status="running", detail=payload, refs=[record.log_path])
    ctx.node_finished("N9_submit", detail={"job_id": record.job_id, "scenario": ctx.scenario})
    return payload


async def n9_park(data: Any) -> dict[str, Any]:
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
        # 首次进入：停放。此刻执行处于 interrupt，落盘合法。
        await data.async_pause_for(
            type="job_done",
            interrupt_id=f"JOB:{job_id}",
            payload={"job_id": job_id, "node": "N9", "tc": job.get("tc"), "log_path": job.get("log_path"),
                     "wait_reason": "全跑为外部长任务；图必须停放而非阻塞 handler。"},
            resume_to="self",
        )
        return {"status": "waiting", "job_id": job_id}

    # 恢复分支：结局由 resume 载荷给出，但**取数一律回读日志**。
    try:
        payload = (getattr(data.resume, "value", None) or {}) if getattr(data, "resume", None) else {}
        phase = payload.get("phase")
        if phase == "dead":
            ctx.event("dead_job", node="N9", status="dead", detail=payload)
            raise RuntimeError(
                f"死任务 {job_id}：进程已终结但未留下 rc ⇒ 不得当成功，走失败分支。"
            )
        if phase == "cancelled":
            ctx.event("warning", node="N9", status="cancelled", detail=payload)
            raise RuntimeError(f"作业 {job_id} 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续。")

        ev = ctx.evidence()
        counts = ev.get("counts") or {}
        out = {
            "job_id": job_id,
            "resume_payload": payload,
            "evidence": ev,
            "counts": counts,
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
                                  "koutou2": (counts.get("koutou2") or {}).get("value")},
                          refs=[ev.get("path", "")])
        return out
    finally:
        # 铁律：成功 / 失败 / 取消都必须释放单槽，且幂等。
        # 少了这一步，死任务会把单槽永久占住，后续运行全部卡在 SLOT 中断（实测过）。
        if ctx.admission is not None:
            handoff = ctx.admission.release(job_id=_slot_job_id(ctx))
            if handoff:
                ctx.event("admission_granted", node="N9", status="handoff", detail=handoff)


# ---------------------------------------------------------------- N15


async def n15_select(data: Any) -> list[str]:
    """N15 选择要回归的用例集。

    `for_each` 的输入必须是**序列**，所以这里返回纯 list，元数据落 state。
    全部四种 G3 决策都存在；`full_now` / `subset_only` 在冲突未清零时被 I4 硬阻断。
    """
    ctx = ctx_of(data)
    ctx.node_started("N15_select")
    n5 = data.get_state("n5_impact") or {}
    cases = [c for c in (n5.get("must_change_cases") or []) if c]
    if not cases:
        cases = ["tc_pcie_rw_02"]
    await data.async_set_state("n15_set", {"cases": cases, "count": len(cases), "mode": ctx.mode})
    ctx.node_finished("N15_select", detail={"count": len(cases), "cases": cases})
    return cases


async def n15_case(data: Any) -> dict[str, Any]:
    """N15 单个用例的回归。

    真实并行只在**跨机**成立（`run_tc.py`，5 机 × 2 LIC）；
    本机受 `uvs.setup` 全局单文件约束 ⇒ `for_each` 的并发上限必须是 1。
    """
    ctx = ctx_of(data)
    case = data.input
    if isinstance(case, dict):
        case = case.get("case") or case.get("cases") or str(case)
    out = {
        "case": case,
        "mode": ctx.mode,
        "simulated": ctx.mode == "drill",
        "note": "drill 下不真跑仿真；真实 N15 经 run_tc.py 跨机执行。",
    }
    ctx.event("job_progress", node="N15", status="ok", detail=out, provisional=True)
    return out
