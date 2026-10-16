"""验收 A1 / A3 / A4 / A5 / A7 / A8：闭环图、闸门、长任务停放与恢复。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from host import paths as P
from workflows.main_flow import RunManager

HUMAN = "human:test-operator"


async def wait_until(pred: Callable[[], bool], *, timeout: float = 20.0, interval: float = 0.2) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(interval)
    return False


def _interrupt_id(view: dict[str, Any]) -> str:
    return ((view.get("pending_interrupt") or {}).get("id") or "")


async def _drive_to_interrupt(m: RunManager, rid: str, prefix: str, *, timeout: float = 20.0) -> dict[str, Any]:
    ok = await wait_until(lambda: _interrupt_id(m.run_view(rid)).startswith(prefix), timeout=timeout)
    assert ok, f"未在 {timeout}s 内到达 {prefix} 中断；当前={_interrupt_id(m.run_view(rid))!r} status={m.run_view(rid)['status']}"
    return m.run_view(rid)


# --------------------------------------------------------------- A1

async def test_reaches_gate1_with_readable_interrupt() -> None:
    """A1：图可跑并停在闸门1，pending interrupt 可被**程序**读到（不靠读日志推断）。"""
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        view = await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        assert view["status"] == "waiting_gate"
        material = (view["pending_interrupt"] or {}).get("payload") or {}
        assert material["gate"] == "G1_diff_confirm"
        assert "未决条目" in material["invariant_note"]
        # 闸门1 时还没有全跑证据 ⇒ 必须显式登记"判据不可判"，不得默认为通过
        assert any(b["code"] == "I3_EVIDENCE_MISSING" for b in view["blockers"])
        assert view["can"]["judge_pass"] is False
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- A7

async def test_gate_rejects_non_human_actor() -> None:
    """A7 / I6：模型或演练 actor 不得越过闸门。"""
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        with pytest.raises(PermissionError):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor="model:gpt-x")
        # 被拒后权威闸门态必须仍是未签
        from workflows.chunks.host_steps import run_kb_tool

        check = run_kb_tool("gate.py", ["require-signed", "--run", rid, "--gate", "G1_diff_confirm"])
        assert check["rc"] != 0, "非人类 actor 被拒后闸门不得变成已签"
        assert m.run_view(rid)["status"] == "waiting_gate"
    finally:
        await m.stop_watching()


async def test_gate_rejects_illegal_decision_value() -> None:
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        with pytest.raises(ValueError):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="lgtm", actor=HUMAN)
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- A4 / A5

async def test_execution_parks_while_long_job_runs_and_survives_restart() -> None:
    """A4 + A5：作业在跑时执行处于**中断**（非 running），快照可落可载。

    这是长任务形状的核心断言：若 N9 阻塞在 handler 里，
    快照会带 `running` 帧 ⇒ `async_load` fail-closed（recovery.md:75-77）。
    """
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="cancel")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        view = await _drive_to_interrupt(m, rid, "JOB:", timeout=25.0)

        execution = m.executions[rid]
        assert execution.is_waiting() is True, "作业运行期间执行必须处于中断，而不是 running"
        assert view["job"]["phase"] == "running"
        snapshot = m._snapshot_path(rid)
        assert snapshot.is_file(), "停在中断上时应已落快照"

        # 真正跨"进程"验证：换一个 RunManager，从盘上快照恢复
        await m.stop_watching()
        m2 = RunManager()
        report = await m2.async_restore_all()
        assert rid in report["restored"], f"恢复失败：{report}"
        restored_view = m2.run_view(rid)
        assert restored_view["status"] == "waiting_gate"
        assert _interrupt_id(restored_view).startswith("JOB:")
        assert restored_view["job"]["job_id"] == view["job"]["job_id"], "恢复后必须附着到同一作业"

        # 恢复后取消：作业走 cancelled ⇒ 本轮无法满足 I3，必须**失败**而不是继续到闸门2
        m2.cancel_job(rid, view["job"]["job_id"])
        await wait_until(lambda: m2.docs[rid].error is not None, timeout=20.0)
        await m2.async_sync(rid)
        after = m2.run_view(rid)
        assert after["status"] == "failed", after["status"]
        assert "取消" in (m2.docs[rid].error or "")
        await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_crash_recovery_delivers_dead_job_as_dead_not_done() -> None:
    """F-V1-05：崩溃重启的**补投递**必须带权威相位，不得把死任务当"正常完成"。

    实测缺陷链：`JobRunner._persist_finish` 把更新后的**副本**写盘、`poll()` 却把
    **原记录**放进 `JobStatus.record` ⇒ 该记录的 `phase` 还停在 "running"；
    `async_restore_all()` 的补投递据此恢复 `n9_park`，于是死任务被当完成投递，
    run 带着 `koutou1=null` 一路走到 **G2 人工闸门**（而不是失败）。

    复现手法：让作业真的死掉（SIGKILL 进程组、不落 rc），再把盘上记录改回
    "crash 前"的样子（phase=running / delivered=false / finished_at=None），
    然后用**新的 RunManager** 走一遍崩溃恢复。
    """
    import os
    import signal

    from host import paths as P  # noqa: F401  (保持与本文件其它测试一致的导入风格)

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="cancel")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        view = await _drive_to_interrupt(m, rid, "JOB:", timeout=25.0)
        job_id = view["job"]["job_id"]

        rec = m.runner.record(job_id)
        assert rec is not None
        try:
            os.killpg(os.getpgid(int(rec["pid"])), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        rc_path = Path(rec["rc_path"])
        if rc_path.exists():
            rc_path.unlink()

        # 等 poll 把它判死（同时验证 poll 返回的 record 相位是权威的）
        ok = await wait_until(lambda: m.runner.poll(job_id).phase == "dead", timeout=15.0)
        status = m.runner.poll(job_id)
        assert ok, f"作业未被判死：{status}"
        assert status.record["phase"] == "dead", (
            "F-V1-05 根因回归：poll() 返回的 record['phase'] 必须是刚判定的相位，"
            f"实际 {status.record['phase']!r}"
        )

        # 伪造"崩溃现场"：记录仍停在 running / 未投递 / 无 finished_at
        stale = dict(rec)
        stale.update({"phase": "running", "delivered": False, "finished_at": None, "rc": None})
        m.runner.record_path(job_id).write_text(json.dumps(stale, ensure_ascii=False, indent=2), encoding="utf-8")

        await m.stop_watching()
        m2 = RunManager()
        report = await m2.async_restore_all()
        assert rid in report["restored"], f"恢复失败：{report}"

        done = await wait_until(lambda: m2.docs[rid].error is not None, timeout=25.0)
        assert done, f"死任务未被判失败，run 停在：{m2.run_view(rid)['status']}"
        assert "死任务" in (m2.docs[rid].error or ""), m2.docs[rid].error
        after = m2.run_view(rid)
        assert after["status"] == "failed", after["status"]
        kinds = [e["kind"] for e in m2._progress(rid).read()]
        assert "dead_job" in kinds, kinds
        await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_park_snapshot_is_written_without_opportunistic_sync() -> None:
    """F-V1-06a：停在长任务上必须**必然**落快照，不能靠"某次 `async_sync` 恰好看到"。

    实测缺陷：happy drill 从 G1 跑到 G2 只用约 1.3 s，两次 `async_sync` 都看到 `running`
    ⇒ 盘上只剩最早那份（停在 G1）快照，重启后回退到一个**账本已签**的闸门。
    """
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="cancel")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        parked = await _drive_to_interrupt(m, rid, "JOB:", timeout=25.0)

        # 断言对齐**当前停放的那个中断**，而不是看板上的 `view["job"]`：
        # 二者曾不一致 —— `_job_view` 取 `records[-1]`，那是按 `JOB-<hex>` 文件名字典序，
        # 与时间顺序无关。verifier 报的 F-V1-06-FLAKY 就是这么来的（快照里有 JOB:，
        # 但那是**另一个** id）。根因已修（改取 started_at 最新的作业），这里同时固定住它。
        parked_job = ((parked.get("pending_interrupt") or {}).get("payload") or {}).get("job_id")
        assert parked_job, parked
        assert parked["job"]["job_id"] == parked_job, (parked["job"], parked_job)

        snap = m._snapshot_path(rid)
        ok = await wait_until(lambda: snap.is_file() and parked_job in snap.read_text(encoding="utf-8"),
                              timeout=25.0)
        blob = snap.read_text(encoding="utf-8") if snap.is_file() else ""
        assert ok, "停在长任务上的快照没有被落盘（快照不能再靠碰运气）"
        assert "JOB:" in blob, "快照里必须含该作业的中断"
    finally:
        await m.stop_watching()


async def test_restore_redelivers_terminal_job_when_snapshot_is_stale() -> None:
    """F-V1-06c：快照停在**已终结且已投递**的作业中断上 ⇒ 必须按权威重投递结局，不得永久卡住。

    实测（拆仓后终验第 2 代）：补投递发生在快照落盘之后，盘上快照仍停在 `JOB:` 中断，
    而作业记录已是 `delivered=True` ⇒ 没有任何补投递会再来，run 永久卡在 JOB。
    重投递只读取已跑完作业的结局，**不重跑外部作业**。
    """
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="cancel")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        parked = await _drive_to_interrupt(m, rid, "JOB:", timeout=25.0)
        job_id = ((parked.get("pending_interrupt") or {}).get("payload") or {}).get("job_id")
        assert job_id, parked
        snap = m._snapshot_path(rid)
        ok = await wait_until(lambda: snap.is_file() and job_id in snap.read_text(encoding="utf-8"),
                              timeout=25.0)
        assert ok, "停在 JOB 上的快照未落盘"

        # 伪造"投递已发生、快照还停在 JOB"：作业落 rc（poll 判 done）+ 记录标 delivered=True
        rec = m.runner.record(job_id)
        Path(rec["rc_path"]).write_text("0", encoding="utf-8")
        forged = dict(rec)
        forged.update({"phase": "done", "rc": 0, "delivered": True})
        m.runner.record_path(job_id).write_text(json.dumps(forged, ensure_ascii=False, indent=2),
                                                encoding="utf-8")

        await m.stop_watching()
        m2 = RunManager()
        report = await m2.async_restore_all()
        assert rid in report["restored"], report
        moved = await wait_until(
            lambda: not (((m2.run_view(rid).get("pending_interrupt") or {}).get("id") or "").startswith("JOB:")),
            timeout=20.0)
        view = m2.run_view(rid)
        assert moved, f"仍卡在 JOB 中断：status={view['status']} pending={view.get('pending_interrupt')}"
        kinds = [(e["kind"], e.get("status")) for e in m2._progress(rid).read()]
        assert ("warning", "stale_snapshot_redeliver") in kinds, "重投递必须留显式事件（不得静默）"
        await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_restore_refuses_when_snapshot_lags_the_ledger() -> None:
    """F-V1-06b：快照落后于权威账本时必须**显式失败**，既不许卡死也不许静默重跑一轮。

    复现：把快照替换成"停在 G1、而 G1 已在账本里签过"的那一份。
    期望：恢复后 run 立刻 `failed` 并说明原因（而不是停在 G1 等人、也不是自动重跑一轮
    修订 + 仿真 —— 那是人没要求的副作用）。
    """
    from host import gate_authority as GA

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        snap = m._snapshot_path(rid)
        ok = await wait_until(lambda: snap.is_file(), timeout=10.0)
        assert ok, "G1 处应有快照"
        behind = Path(str(snap) + ".behind")
        behind.write_bytes(snap.read_bytes())          # 停在 G1 的那一份

        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)
        assert GA.authority_view(rid)["gates"]["G1_diff_confirm"]["human_signed"] is True

        # 把快照"倒回"到 G1 —— 模拟崩溃落在两次落盘之间
        await m.stop_watching()
        snap.write_bytes(behind.read_bytes())
        behind.unlink()

        m2 = RunManager()
        report = await m2.async_restore_all()
        reasons = " | ".join(str(f.get("reason")) for f in report["failed"])
        assert any("快照落后于权威账本" in r for r in [reasons]), report
        view = m2.run_view(rid)
        assert view["status"] == "failed", (view["status"], view.get("error"))
        assert "快照落后于权威账本" in (view.get("error") or ""), (
            view.get("error"), m2.docs[rid].error, m2.docs[rid].status,
            [n["node"] for n in view["node_history"]])
        kinds = [(e["kind"], e.get("status")) for e in m2._progress(rid).read()]
        assert ("warning", "snapshot_behind_ledger") in kinds, "对账结论必须留事件（不得静默）"
        # 关键：不得自动重放 ⇒ G2 仍未被签，且没有多跑一轮的痕迹
        assert GA.authority_view(rid)["gates"]["G2_report_accept"]["human_signed"] is False
        await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_dead_job_never_counts_as_success() -> None:
    """A5：死任务（进程没了且无 rc）必须走失败分支，不得当成功。"""
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="dead_job")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        await wait_until(lambda: m.docs[rid].error is not None, timeout=25.0)
        doc = m.docs[rid]
        assert doc.error is not None, "死任务应导致失败，而不是静默通过"
        assert "死任务" in doc.error
        view = m.run_view(rid)
        assert view["counts"] is None or view["counts"]["both_zero"] is False
        assert any(b["code"] in ("I3_EVIDENCE_MISSING", "I3_KOUTOU1_NONZERO") for b in view["blockers"])
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- 全链路

async def test_full_drill_loop_to_n16_refusal() -> None:
    """A1+A2+A3 全链路：三闸门全过，双计数并列，N16 在冲突未清零时拒绝。"""
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="2 条差异已逐条核对")
        await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)

        view = m.run_view(rid)
        counts = view["counts"]
        assert counts["koutou1"]["value"] > 0
        assert counts["koutou2"]["value"]["UVM_ERROR"] == 0
        assert counts["both_zero"] is False
        assert any(b["code"] == "I3_KOUTOU1_NONZERO" for b in view["blockers"])
        assert any(b["code"] == "I4_CONFLICTS_UNCLEARED" for b in view["blockers"])
        assert view["can"]["judge_pass"] is False
        assert view["can"]["promote"] is False

        gate2_material = (view["pending_interrupt"] or {}).get("payload") or {}
        assert "两套口径均为 0" in gate2_material["invariant_note"]

        await m.decide(run_id=rid, gate="G2_report_accept", decision="accept", actor=HUMAN,
                       reason="接受报告本身，不解除任何冲突")
        await _drive_to_interrupt(m, rid, "G3_regression_decision", timeout=20.0)

        # I4：冲突未清零 ⇒ full_now 必须被硬阻断，且**闸门必须仍然可用**。
        # 阻断若发生在恢复之后，一次误选就会消耗掉中断（max_resumes=1）
        # 并把执行打成 failed ⇒ 闸门从此不可用（实测踩到 self_resume_limit_reached）。
        with pytest.raises(PermissionError, match="I4"):
            await m.decide(run_id=rid, gate="G3_regression_decision", decision="full_now", actor=HUMAN)
        still = m.run_view(rid)
        assert still["status"] == "waiting_gate", f"误选后闸门不可用了：{still['status']}"
        assert ((still.get("pending_interrupt") or {}).get("id") or "").startswith("G3")

        # 非法枚举值也必须在提交前被拒，且同样不消耗中断
        with pytest.raises(ValueError, match="权威枚举"):
            await m.decide(run_id=rid, gate="G3_regression_decision", decision="full_regression", actor=HUMAN)
        assert m.run_view(rid)["status"] == "waiting_gate"

        await m.decide(run_id=rid, gate="G3_regression_decision", decision="milestone_only",
                       actor=HUMAN, reason="I4 未清零，只做里程碑")
        ok = await wait_until(lambda: any(n["node"] == "N16" for n in m.run_view(rid)["node_history"]), timeout=25.0)
        assert ok, "未到达 N16"
        n16 = [n for n in m.run_view(rid)["node_history"] if n["node"] == "N16"][-1]
        assert n16["status"] in ("refused", "ok"), n16
        assert n16["detail"]["dry_run"] is True, "N16 在本层必须 dry-run，绝不写 kb/baselines"

        gates = {g["gate"]: g["decision"] for g in m.run_view(rid)["gate_history"]}
        assert gates == {"G1_diff_confirm": "confirmed", "G2_report_accept": "accept",
                         "G3_regression_decision": "milestone_only"}

        # F-V1-04：走到 N16（无后继节点）之后必须**收敛为 finished**。
        # 原实现 `create_execution(auto_close=False)` 关掉了框架里唯一会把生命周期置为
        # CLOSED 的机制 ⇒ `is_closed()` 恒假、`status` 永远 `running`，而
        # `async_restore_all()` 会在每次重启时把这些僵尸 run 再恢复一遍。
        done = await wait_until(lambda: m.run_view(rid)["status"] == "finished", timeout=15.0)
        assert done, f"N16 之后未收敛：status={m.run_view(rid)['status']}"
    finally:
        await m.stop_watching()


async def test_g3_defer_halts_and_run_converges_to_finished() -> None:
    """F-V1-04：`defer` 是 I4 允许的合法选项 ⇒ 走 HALT，也必须**收敛为 finished**。

    实测缺陷：`G3=defer` 后 node_history 到 HALT，但 status 永远 `running`
    —— 界面看板永远显示"进行中"，且重启会被反复恢复。
    """
    from workflows.main_flow import reached_terminal

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN, reason="x")
        await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)
        await m.decide(run_id=rid, gate="G2_report_accept", decision="accept", actor=HUMAN, reason="x")
        await _drive_to_interrupt(m, rid, "G3_regression_decision", timeout=20.0)
        await m.decide(run_id=rid, gate="G3_regression_decision", decision="defer", actor=HUMAN,
                       reason="冲突未清零，本轮不发版")

        ok = await wait_until(lambda: m.run_view(rid)["status"] == "finished", timeout=15.0)
        view = m.run_view(rid)
        assert ok, f"defer/HALT 之后未收敛：status={view['status']}"
        nodes = [n["node"] for n in view["node_history"]]
        assert "HALT" in nodes, nodes
        assert "N16" not in nodes, "defer 不得走到 N16（不发版）"
        # 事件流层面也要能判出终止节点
        for_reached = reached_terminal(m._progress(rid).read())
        assert for_reached == "HALT", for_reached
        # 终止后不得再被当成"等一下会继续"的活运行
        assert view["can"]["promote"] is False
    finally:
        await m.stop_watching()


async def test_terminal_detection_helper() -> None:
    """`reached_terminal`：只看**最后一个节点事件**，且必须是终止节点的 node_finished。"""
    from workflows.main_flow import reached_terminal

    ev = lambda k, n, s="ok": {"kind": k, "node": n, "status": s}  # noqa: E731
    assert reached_terminal([ev("node_started", "N0"), ev("node_finished", "HALT", "halted")]) == "HALT"
    assert reached_terminal([ev("node_started", "N16"), ev("node_finished", "N16")]) == "N16"
    # 还没结束（最后一个节点事件是 started）
    assert reached_terminal([ev("node_finished", "N16"), ev("node_started", "N99")]) is None
    # 非终止节点
    assert reached_terminal([ev("node_finished", "N12")]) is None
    assert reached_terminal([]) is None


async def test_gates_are_recorded_once_each() -> None:
    """回归：固定 run_id 复用会伪造出"闸门签了两次"。这里断言不重复。"""
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)
        history = m.run_view(rid)["gate_history"]
        assert [g["gate"] for g in history].count("G1_diff_confirm") == 1, history
    finally:
        await m.stop_watching()


async def test_run_id_collision_is_refused() -> None:
    """同 LOOP_NOW 二次启动必须被拒（否则事件流续写、闸门账本被污染）。"""
    import os

    os.environ["LOOP_NOW"] = "2026-10-15T15:00:00"
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        with pytest.raises(FileExistsError):
            await m.start(baseline="v0", mode="drill")
    finally:
        await m.stop_watching()
        os.environ.pop("LOOP_NOW", None)


# --------------------------------------------------------------- A8

async def test_n16_on_real_baselines_refuses_with_zero_side_effects() -> None:
    """A8：真实 `kb/baselines/` 上 N16 必须拒绝（rc=3）且零副作用。"""
    from workflows.chunks.host_steps import run_kb_tool

    before = sorted(p.name for p in P.KB_BASELINES.iterdir() if p.is_dir())
    v0_files = sorted(p.name for p in (P.KB_BASELINES / "v0").rglob("*") if p.is_file())

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        result = run_kb_tool("n16_promote.py", ["--run", rid, "--trigger-by", "test", "--actor-kind", "human"])
        assert result["rc"] == 3, f"应拒绝，实际 rc={result['rc']}: {result['stdout_tail'][-400:]}"
        after = sorted(p.name for p in P.KB_BASELINES.iterdir() if p.is_dir())
        v0_after = sorted(p.name for p in (P.KB_BASELINES / "v0").rglob("*") if p.is_file())
        assert before == after, f"拒绝路径产生了副作用：{set(after) - set(before)}"
        assert v0_files == v0_after, "v0 基线被改动"
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- 单槽必须在终态释放

async def test_slot_is_released_after_successful_job() -> None:
    """成功路径：N9 作业结束后单槽必须释放（否则后续运行全部排队）。"""
    from host.admission import Admission

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)
        assert Admission(P.STATE_DIR).holder() is None, "作业结束后单槽仍被占用"
        assert Admission(P.STATE_DIR).queue() == []
    finally:
        await m.stop_watching()


async def test_slot_is_released_on_dead_job_failure() -> None:
    """失败路径（实测踩过的真缺陷）：死任务抛错时也必须释放单槽。

    修复前：`n9_park` 在 raise 前不 release ⇒ 单槽被永久占住 ⇒
    后续运行全部卡在 `SLOT:` 中断，把"一个 run 失败"放大成"全体挂起"。
    """
    from host.admission import Admission

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="dead_job")
    try:
        await _drive_to_interrupt(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN)
        await wait_until(lambda: m.docs[rid].error is not None, timeout=25.0)
        assert m.docs[rid].error is not None
        assert Admission(P.STATE_DIR).holder() is None, "死任务失败后单槽未释放"
        assert Admission(P.STATE_DIR).queue() == []
    finally:
        await m.stop_watching()
