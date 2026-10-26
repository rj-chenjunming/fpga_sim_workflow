"""验收 A1 / A3 / A4 / A5 / A7 / A8：闭环图、闸门、长任务停放与恢复。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        assert restored_view["status"] == "waiting_job", "I18：停在 JOB 上应投影为 waiting_job（不是 waiting_gate）"
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        # 崩溃发生在**投递之前** ⇒ 盘上的 view.json 还是停放态。
        # 修复后（I1/I3）看护任务一旦发现死任务会立刻把 run 置 failed 并落盘；
        # 那本身是正确行为，但会跳过本用例要测的"补投递"路径，所以这里把崩溃现场
        # 的投影也回滚到投递前（与上面伪造作业记录的意图一致）。
        m.docs[rid].status = "waiting_job"
        m.docs[rid].error = None
        m._persist(rid)
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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


def test_clean_park_rejects_half_dispatched_interrupt() -> None:
    """F-V1-06d：快照只许拍**干净停车** —— 已派发完（resume_count >= max）的中断不许落盘。

    实测：0.2/0.5s 节拍会拍到"已派发但接管未开始"的半截快照（`status='waiting'` 而
    `resume_count` 已等于 `max_resumes`）。这种快照 load 得进来，但恢复时既不能重投递
    （`is not waiting`）也不会自己往下走 ⇒ 只能失败。宁可不落盘。
    """
    class _Ex:
        def __init__(self, interrupts):
            self._i = interrupts

        def get_pending_interrupts(self):
            return self._i

    clean = _Ex({"JOB:J": {"status": "waiting", "resume_count": 0, "max_resumes": 1}})
    half = _Ex({"JOB:J": {"status": "waiting", "resume_count": 1, "max_resumes": 1}})
    done = _Ex({"G1:0": {"status": "resumed", "resume_count": 1, "max_resumes": 1}})
    assert RunManager._is_clean_park(clean) is True
    assert RunManager._is_clean_park(half) is False
    # 已结束（非 waiting）的中断不参与判定
    assert RunManager._is_clean_park(done) is True
    assert RunManager._is_clean_park(_Ex({})) is True


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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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

        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        events = m._progress(rid).read()
        for_reached = reached_terminal(events)
        assert for_reached == "HALT", for_reached
        # P-35：终止原因必须是**白话字符串** + 逐门决策映射；既有 `{闸门: 决策}` 字段不得删
        halt = _node_final(events, "HALT")["detail"]
        assert isinstance(halt["reason"], str) and "闸门3" in halt["reason"], halt["reason"]
        assert "defer" not in halt["reason"], "白话原因里不得只写原始枚举"
        assert halt["decisions"] == {"G1_diff_confirm": "confirmed",
                                     "G2_report_accept": "accept",
                                     "G3_regression_decision": "defer"}
        assert halt["G3_regression_decision"] == "defer", "既有逐门字段必须原样保留"
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
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
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor=HUMAN,
                       reason="已逐条核对 2 条差异")
        await wait_until(lambda: m.docs[rid].error is not None, timeout=25.0)
        assert m.docs[rid].error is not None
        assert Admission(P.STATE_DIR).holder() is None, "死任务失败后单槽未释放"
        assert Admission(P.STATE_DIR).queue() == []
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- S2 宿主数据面（契约 §3 / §2.5）


def _node_final(events: list[dict[str, Any]], node: str) -> dict[str, Any]:
    rows = [e for e in events
            if e.get("node") == node and e.get("kind") in ("node_finished", "node_failed")]
    assert rows, f"{node} 没有收尾事件"
    return rows[-1]


async def _drive_full_drill(m: RunManager, rid: str) -> None:
    """drill 全链走到 N16（三闸门都经人类 actor 决策；与既有全链用例同一路径）。"""
    await _drive_to_interrupt(m, rid, "G1_diff_confirm")
    await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                   actor=HUMAN, reason="已逐条核对 2 条差异")
    await _drive_to_interrupt(m, rid, "G2_report_accept", timeout=25.0)
    await m.decide(run_id=rid, gate="G2_report_accept", decision="accept",
                   actor=HUMAN, reason="接受报告")
    await _drive_to_interrupt(m, rid, "G3_regression_decision", timeout=20.0)
    await m.decide(run_id=rid, gate="G3_regression_decision", decision="milestone_only",
                   actor=HUMAN, reason="I4 未清零，只做里程碑")
    ok = await wait_until(
        lambda: any(n["node"] == "N16" for n in m.run_view(rid)["node_history"]), timeout=30.0)
    assert ok, f"未到达 N16：status={m.run_view(rid)['status']}"


async def test_s2_detail_fields_and_gate_ledger_on_full_drill_run() -> None:
    """契约 §3/§2.5：新 detail 字段来自既有产物；闸门逐条处置落账；提交节点有开始事件。

    断言只认事件 detail / run 目录里的真实产物（drill 夹具），不 mock 判据。
    """
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    run_dir = P.KB_RUNS / rid
    try:
        await _drive_full_drill(m, rid)
        events = m._progress(rid).read()

        # ---- N3（P-13/P-14）：模型摘要字段 + 空段信息标记
        n3 = _node_final(events, "N3")["detail"]
        assert {"digest_summary", "digest_confirmations", "groups_count",
                "offered_segments_empty"} <= set(n3)
        assert n3["offered_segments_empty"] is False, "夹具差异带段信息"
        assert n3["digest_summary"] is None, "standin 不得拿夹具正文冒充模型结论"
        assert n3["groups_count"] is None, "standin 无模型分组输出 ⇒ 显式未下发（不写 0）"
        assert "模型摘要未下发" in n3["summary"]
        # P-14 ④：模型输入带 N2 已有的 id/offsets（不新增取数）
        request = json.loads(
            (run_dir / "agent_calls" / "N3" / "attempt-000001" / "request.json")
            .read_text(encoding="utf-8"))
        for diff in request["input"]["diffs"]:
            assert "id" in diff and "offsets" in diff and isinstance(diff["offsets"], list)

        # ---- N5（P-19）：待查数/用例只从 n5 产物 to_check 取
        n5_product = json.loads((run_dir / "n5_impact.json").read_text(encoding="utf-8"))
        n5 = _node_final(events, "N5")["detail"]
        assert n5["to_check_count"] == len(n5_product["to_check"])
        assert n5["to_check_cases"] == sorted(
            {str(x["case"]) for x in n5_product["to_check"] if x.get("case")})
        # P-19：headline 要「另有 N 个待查（用例）」⇒ 去重用例数单列；条目数保留
        assert n5["to_check_case_count"] == len(n5["to_check_cases"])
        assert n5["to_check_count"] >= 0 and n5["to_check_case_count"] >= 0
        assert n5["to_check_case_count"] <= n5["to_check_count"]

        # ---- N0 措辞（裁决 #6 / P-01 A）：新 drill run 说「预置数据（夹具）」
        n0 = _node_final(events, "N0")["detail"]
        assert "预置数据（夹具）初始化" in n0["summary"], n0["summary"]
        assert "drill 夹具初始化" not in n0["summary"], "旧串（drill 夹具初始化）不得再出现"

        # ---- N6 / N6_apply（P-20/P-21/P-25）：逐用例修改摘要与 N6 同源
        n6 = _node_final(events, "N6")["detail"]
        assert n6["case_edits"] is None, "standin 无模型 edits ⇒ 显式未下发"
        assert n6["case_edits_source"] == "n6_output"
        assert n6["observation_points"] is None, \
            "standin/drill 无模型观测点输出 ⇒ 显式 null（不是空列表冒充 0 条）"
        n6a = _node_final(events, "N6_apply")["detail"]
        assert n6a["case_edits"] is None
        sandbox_cases = sorted(p.stem for p in (run_dir / "sandbox" / "TESTLIB").glob("*.sv"))
        assert n6a["applied_cases"] == sandbox_cases
        assert len(n6a["applied_cases"]) == n6a["cases"]

        # ---- N8（P-23）：检查项/必须修改/轮次/上限
        n8 = _node_final(events, "N8")["detail"]
        assert n8["check_count"] is None, "standin 未产出 findings ⇒ 显式未下发（不写 0）"
        assert n8["must_fix_count"] is None
        assert isinstance(n8["cycle"], int) and isinstance(n8["limit"], int)

        # ---- N9（P-24）：逐用例计数/示例行/身份/用例明细
        n9 = _node_final(events, "N9")["detail"]
        assert n9["koutou1_by_case"] == {"tc_pcie_rw_02": n9["koutou1"]}
        assert n9["example_line"].startswith("line "), n9["example_line"]
        assert n9["identity"]["consistent"] is None, "drill 无身份头 ⇒ 不判一致"
        assert n9["cases_detail"][0]["case"] == "tc_pcie_rw_02"
        assert {"case", "koutou1", "uvm_error", "uvm_fatal", "passed"} <= set(
            n9["cases_detail"][0])

        # ---- R3-09：drill 下提交/编译节点也要下发"用例数"（story headline 才有数可说）
        n9_submit = _node_final(events, "N9_submit")["detail"]
        assert n9_submit["cases"] == 1, n9_submit
        assert _node_final(events, "N7")["detail"]["case_count"] == 1, "drill N7 缺 case_count"

        # ---- N10（P-26）：逐用例对账表 + 失败分类摘要
        n10 = _node_final(events, "N10")["detail"]
        row = n10["cases_table"][0]
        assert {"case", "koutou1", "uvm_error", "uvm_fatal", "imprints_ok",
                "imprints_missing", "passed", "reasons"} <= set(row)
        assert {"buckets", "既有缺陷", "本轮引入", "待裁决"} <= set(n10["classification"])
        assert n10["classification"]["buckets"] == 24, "夹具 1687 行归并成 24 个地址区间"
        assert n10["classification"]["本轮引入"] is None, "standin 无模型分类 ⇒ 显式未下发"

        # ---- N11（P-27）：身份表/未闭环/返工请求条数
        n11 = _node_final(events, "N11")["detail"]
        assert n11["identity_table"] == [], "drill 无真实身份头 ⇒ 空表（不是编 3 行）"
        assert isinstance(n11["unclosed"], list) and n11["unclosed"]
        assert n11["rework_requests_count"] == 0

        # ---- N12（P-28）：可解析引用数 / 未闭环项 / 用例状态摘要
        n12 = _node_final(events, "N12")["detail"]
        assert n12["refs_parseable_count"] == n12["ref_count"] - 0
        assert isinstance(n12["open_items"], list) and isinstance(n12["cases_summary"], list)

        # ---- N15_select / N15（P-31/P-32）：用例名 + 是否真跑
        n15s = _node_final(events, "N15_select")["detail"]
        assert n15s["cases"] and all(isinstance(c, str) for c in n15s["cases"])
        assert sorted(n15s["cases"]) == n5["must_change_cases"], \
            "milestone_only 的回归集 = 本轮受影响子集（用例名必须列出）"
        assert n15s["will_really_run"] is False, "drill 演示不真跑"
        n15 = _node_final(events, "N15")["detail"]
        assert n15["cases"] == n15s["cases"]
        assert n15["executed"] is False and n15["will_really_run"] is False
        assert n15["failed_cases"] == []

        # ---- N16（P-34）：拒绝原因原文 + 每次尝试的结果件
        n16 = _node_final(events, "N16")["detail"]
        assert n16["reason_line"].startswith("[FAIL]"), n16["reason_line"]
        result_path = Path(n16["result_artifact"])
        assert result_path.is_file() and result_path.name == "n16_result.json"
        assert str(result_path) in _node_final(events, "N16")["refs"]

        # ---- P-33：提交型节点有 node_started + 收尾 refs 带作业日志
        started = [e for e in events if e.get("kind") == "node_started"
                   and e.get("node") == "N9_submit"]
        assert started, "N9_submit 缺 node_started"
        submitted = [e for e in events if e.get("kind") == "job_submitted"
                     and e.get("node") == "N9"]
        submit_final = _node_final(events, "N9_submit")
        assert submitted and submit_final["refs"][:1] == submitted[-1]["refs"][:1], \
            "N9_submit 收尾 refs 必须与 job_submitted 同源"

        # ---- §2.5：闸门逐条处置落账（append-only，S3 只读消费）
        diff_ids = {d.get("entry_id") or d.get("id") for d in
                    json.loads((run_dir / "n2_diff.json").read_text(encoding="utf-8"))["diffs"]}
        decided_events = {e["detail"]["gate"]: e["detail"] for e in events
                          if e.get("kind") == "gate_decided"}
        for gate in ("G1_diff_confirm", "G2_report_accept", "G3_regression_decision"):
            ledger_path = run_dir / "decisions" / f"{gate}.json"
            assert ledger_path.is_file(), f"缺 {ledger_path}"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            assert ledger["schema"] == "loop/gate_entries"
            assert ledger["gate"] == gate and ledger["run_id"] == rid
            latest = ledger["records"][-1]
            assert {"cycle", "decided_at", "decision", "actor", "reason", "entries"} <= set(latest)
            assert latest["decided_at"] == decided_events[gate]["signed_at"], \
                "decided_at 必须取权威签署时间（不新取墙钟）"
            assert latest["decision"] == decided_events[gate]["decision"]
        g1 = json.loads((run_dir / "decisions" / "G1_diff_confirm.json")
                        .read_text(encoding="utf-8"))["records"][-1]
        assert set(g1["entries"]) == diff_ids, "逐条处置必须覆盖全部差异条目"
        assert decided_events["G1_diff_confirm"]["entries"] == g1["entries"], \
            "gate_decided.detail.entries 与落账同源"

        # ---- 唯一存储位置（2026-10-26，CHANGE_IMPACT_LOOP_SPEC §7 口径订正）
        # 逐条处置只落 `decisions/<gate>.json` + `gate_decided.detail.entries`；
        # `gates.json` 是权威 + sha256 锚，**不得**再存一份副本（两个来源 ⇒ 红线 8；
        # 且锚会随内容变化）。这不是 schema 禁止（`gate.additionalProperties` 为 true），
        # 而是设计选择 + 编排规格明文禁止反推。写入不变量见 tests/test_gate_ledger.py。
        authority = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))
        # 顶层键也算（结构化判定的补集：恢复旧版全文子串能覆盖到的顶部形态）
        assert "entry_decisions" not in authority, \
            "逐条处置不得进 gates.json 顶层（唯一来源是 decisions/<gate>.json）"
        # 结构化判定（不用全文子串：人工理由原文里出现这个词也不该假红）
        gates_obj = authority.get("gates") if isinstance(authority, dict) else None
        offending = [gid for gid, gate in (gates_obj or {}).items()
                     if isinstance(gate, dict) and "entry_decisions" in gate]
        assert not offending, \
            f"逐条处置不得进 gates.json（唯一来源是 decisions/<gate>.json）：{offending}"

        # ---- R3-04（P-15）：签署时"当时的硬阻断"必须落账（材料快照，白名单三字段）
        pending_codes = {e["node"]: e["detail"]["hard_block"] for e in events
                         if e.get("kind") == "gate_pending"}
        for gate, gate_node in (("G1_diff_confirm", "N4"), ("G2_report_accept", "N13"),
                                ("G3_regression_decision", "N14")):
            latest_gate = json.loads(
                (run_dir / "decisions" / f"{gate}.json").read_text(encoding="utf-8")
            )["records"][-1]
            assert "hard_block" in latest_gate, f"{gate} 的落账缺 hard_block 快照"
            blocks = latest_gate["hard_block"]
            assert isinstance(blocks, list), blocks
            assert [b["code"] for b in blocks] == pending_codes[gate_node], \
                f"{gate} 落账的硬阻断必须等于本门开启时材料里的快照"
            for block in blocks:
                assert set(block) == {"code", "title", "message"}, block
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- S2 投影纯函数（真实产物形状驱动）


def test_n6_case_edits_projection_is_shared_by_n6_and_n6_apply() -> None:
    from workflows.chunks.model_common import case_edits_from_output

    accepted = {"revisions": [
        {"case": "tc_a", "edits": [{"line": 12, "old": "x", "new": "y"},
                                   {"line": 30, "old": "p", "new": "q"}],
         "rationale": "模型自述：依据 rtl_change"},
        {"case": "tc_b", "edits": [{"line": 4, "old": "m", "new": "n"}]},
    ]}
    out = case_edits_from_output(accepted)
    assert [row["case"] for row in out] == ["tc_a", "tc_b"]
    assert out[0]["edit_count"] == 2
    assert out[0]["edits"][1] == {"line": 30, "old": "p", "new": "q"}
    assert "rationale" not in out[0], "摘要只带用例/位置/旧→新，不带模型自述"
    assert case_edits_from_output(None) is None
    assert case_edits_from_output({"standin": True}) is None


def test_n3_live_detail_projection_uses_model_summary() -> None:
    from workflows.chunks.model_steps import _n3_detail

    live = {"mode": "live", "data": {
        "summary": "sys_reg.v 第 171-172 行把 fpga_date 复位值改成 2026_0708，读回期望要跟着改。",
        "groups": [{"segment": "0x0000", "kind": "rtl_file"}],
        "risky_points": ["缺段信息无法分组（依据：offered_segments 为空）"],
    }}
    detail = _n3_detail(live, offered_segments_empty=True)
    assert detail["digest_summary"].startswith("sys_reg.v")
    assert detail["digest_confirmations"] == ["缺段信息无法分组（依据：offered_segments 为空）"]
    assert detail["groups_count"] == 1
    assert detail["offered_segments_empty"] is True
    standin = _n3_detail({"mode": "standin", "data": {"excerpt": "夹具"}},
                         offered_segments_empty=False)
    assert standin["digest_summary"] is None and standin["groups_count"] is None
    assert standin["digest_confirmations"] is None
    assert standin["offered_segments_empty"] is False


def test_n10_cases_table_and_classification_projection() -> None:
    from workflows.chunks.n10_semantics import _cases_table, _classification_summary

    cases = {
        "tc_a": {
            "counts": {"koutou1": {"value": 1687},
                       "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
            "imprints": {"N6_FPGA_DATE_PCIE": {
                "consistent": True,
                "expected": {"address": "0x0000+0x04", "value": "0x2026_0708"}}},
            "verdict": {"passed": False, "reasons": ["口径一 = 1687 ≠ 0"]},
        },
        "tc_b": {
            "counts": {"koutou1": {"value": 0},
                       "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
            "imprints": {"N6_FPGA_DATE_PCIE": {"consistent": False,
                                               "expected": {"address": "0x0000+0x04"}}},
            "verdict": {"passed": False, "reasons": ["印记 N6_FPGA_DATE_PCIE 三向不一致"]},
        },
    }
    rows = _cases_table(cases)
    assert [r["case"] for r in rows] == ["tc_a", "tc_b"]
    assert rows[0]["imprints_ok"] is True and rows[0]["imprints_missing"] == []
    assert rows[1]["imprints_ok"] is False
    assert rows[1]["imprints_missing"] == ["N6_FPGA_DATE_PCIE"]
    assert rows[0]["koutou1"] == 1687 and rows[0]["uvm_error"] == 0
    assert rows[1]["reasons"] == ["印记 N6_FPGA_DATE_PCIE 三向不一致"]

    items = [{"classification": "既有缺陷"}, {"classification": "既有缺陷"},
             {"classification": "待裁决"}]
    summary = _classification_summary(bucket_count=24, items=items)
    assert summary["buckets"] == 24
    assert (summary["既有缺陷"], summary["本轮引入"], summary["待裁决"]) == (2, 0, 1)
    assert summary["source"] == "n10_output"
    missing = _classification_summary(bucket_count=24, items=None)
    assert missing["既有缺陷"] is None and missing["source"] == "not_classified"


def test_n11_identity_table_and_n12_detail_projection() -> None:
    from workflows.chunks.model_steps import _identity_table, _n12_detail

    host_identity = {"cases": [
        {"case": "tc_a", "run_id": "RUN-1", "reviewed_md5": "a" * 32,
         "run_md5": "a" * 32, "consistent": True},
        {"case": "tc_b", "run_id": "RUN-1", "reviewed_md5": "b" * 32,
         "run_md5": "c" * 32, "consistent": False},
    ]}
    rows = _identity_table(host_identity)
    assert [r["case"] for r in rows] == ["tc_a", "tc_b"]
    assert rows[1]["audit_md5"] == "b" * 32 and rows[1]["run_md5"] == "c" * 32
    assert rows[1]["case_md5"] == rows[1]["run_md5"]
    assert rows[1]["consistent"] is False

    data = {"open_items": ["tc_a 仍『已修订待验』"]}
    detail = _n12_detail(data, refs=["a/b.md", "c.md"], unresolved=["c.md"],
                         ledger_cases=[{"case": "tc_a", "state": "已修订待验"},
                                       {"case": "tc_b"}])
    assert detail["refs_parseable_count"] == 1
    assert detail["open_items"] == ["tc_a 仍『已修订待验』"]
    assert detail["cases_summary"] == ["tc_a：已修订待验", "tc_b：状态未下发"]


def test_n9_detail_projection_from_real_aggregate_shape() -> None:
    from workflows.chunks.long_jobs import _n9_detail

    per_case = {
        "tc_b": {"counts": {"koutou1": {"value": 0, "refs": []},
                            "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
                 "verdict": {"passed": True}},
        "tc_a": {"counts": {"koutou1": {"value": 1687,
                                        "refs": ["line 359: ... *E @ADDR[0x84] ..."]},
                            "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
                 "verdict": {"passed": False, "reasons": ["口径一 = 1687 ≠ 0"]}},
    }
    detail = _n9_detail(cases=per_case,
                        identity={"consistent": True, "mismatches": [],
                                  "source": "guard_header"})
    assert detail["koutou1_by_case"] == {"tc_a": 1687, "tc_b": 0}
    assert detail["example_line"].startswith("line 359"), "示例行只取非零用例的第一条参考"
    assert [r["case"] for r in detail["cases_detail"]] == ["tc_a", "tc_b"]
    assert detail["cases_detail"][0]["passed"] is False
    assert detail["identity"] == {"consistent": True, "mismatches": [],
                                  "source": "guard_header"}
    empty = _n9_detail(cases={}, identity={"consistent": None, "mismatches": []})
    assert empty["example_line"] is None and empty["koutou1_by_case"] == {}


def _n6_revision(case: str, marker: str) -> dict[str, Any]:
    """一条符合 R3-01 口径的 N6 revision：marker 作 UVM_INFO 的 **ID**，写在 edits[].new 里。"""
    new_text = (
        f'uvm_info("{marker}", $sformatf("OK 0x0000+0x04 fpga_date = 0x%08h", '
        'actual), UVM_LOW);'
    )
    return {"case": case, "rationale": "按 rtl_change 修订期望值并加观测点",
            "edits": [{"line": 3, "old": "check(0x0000+0x04, 8'h23);",
                       "new": new_text, "basis": "input.targets[0].revision_points[0].offset=0x4"}]}


def _n6_run_dir(tmp_path: Path) -> Path:
    """R3-01：给直接调用 `_validate` 的单测一个**显式** run 级文档条目快照。

    `_validate` 的「marker 期望必须可解析」**恒执行**（没有"没绑 run_dir 就跳过"的旁路），
    所以直接调用必须传 run_dir；形状照 drill 真实产物：`<run>/doc_entries.jsonl`。
    """
    run_dir = tmp_path / "n6_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "doc_entries.jsonl").write_text(
        json.dumps({"entry_id": "0x0000#0x0004", "name": "fpga_date",
                    "segment": "0x0000", "offset_global": "0x0004",
                    "reset": "2026_0708"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return run_dir


def _n6_payload(points: list[dict[str, Any]], revision_markers: dict[str, str] | None = None
                ) -> dict[str, Any]:
    markers = revision_markers or {p["case"]: p["marker"] for p in points}
    return {"data": {
        "revisions": [_n6_revision(case, marker) for case, marker in markers.items()],
        "observation_points": points,
        "rework_resolution": [], "notes": [],
    }}


def _observation_point(case: str, marker: str, **overrides: Any) -> dict[str, Any]:
    point = {"case": case, "marker": marker, "addr": "0x0000", "offset": "0x04",
             "expected_value": "0x20260708",
             "basis": "input.targets[0].revision_points[0].offset=0x4；doc_bitdef reset=2026_0708"}
    point.update(overrides)
    return point


def test_n6_observation_points_schema_accepts_legal_output(tmp_path: Path) -> None:
    """P-25 方案 A：schema 收合法观测点 + Host 校验把它的契约字段投影出来。"""
    from prompts.node_schemas import N6ObservationPoint, N6Output, N6Revision
    from workflows.chunks.model_steps import _observation_points, _validate

    run_dir = _n6_run_dir(tmp_path)
    point = N6ObservationPoint(**_observation_point("tc_demo", "N6_FPGA_DATE"))
    output = N6Output(revisions=[N6Revision(**_n6_revision("tc_demo", "N6_FPGA_DATE"))],
                      observation_points=[point], rework_resolution=[], notes=[])
    assert output.observation_points[0].marker == "N6_FPGA_DATE"

    result = _validate("n6", _n6_payload([_observation_point("tc_demo", "N6_FPGA_DATE")]),
                       offered={"cases": {"tc_demo"}}, run_dir=run_dir)
    assert result["ok"] is True, result["problems"]
    assert result["accepted"]["observation_points"][0]["marker"] == "N6_FPGA_DATE"
    assert result["accepted"]["observation_points"][0]["addr"] == "0x0000"
    # detail 投影只带契约字段（basis 不进 detail），无模型输出 ⇒ None
    assert _observation_points(result["accepted"]) == [{
        "case": "tc_demo", "marker": "N6_FPGA_DATE", "addr": "0x0000",
        "offset": "0x04", "expected_value": "0x20260708"}]
    assert _observation_points(None) is None
    assert _observation_points({"standin": True}) is None

    with pytest.raises(ValueError):
        N6ObservationPoint(**_observation_point("tc_demo", "FPGA_DATE"))


def test_n6_observation_points_fail_closed_reasons(tmp_path: Path) -> None:
    """P-25：缺用例观测点 / marker 只列不写 / marker 格式非法 ⇒ Host 校验必须失败并点名。"""
    from workflows.chunks.model_steps import _validate

    run_dir = _n6_run_dir(tmp_path)
    both = {"cases": {"tc_demo", "tc_other"}}
    # ① 缺某个用例的观测点
    result = _validate("n6", _n6_payload([_observation_point("tc_demo", "N6_A")]),
                       offered=both, run_dir=run_dir)
    assert result["ok"] is False
    assert any("缺少目标用例的 observation_points" in p and "tc_other" in p
               for p in result["problems"]), result["problems"]
    # ② marker 出现在观测点里但没写进同用例 edits[].new（只列不写）
    payload = _n6_payload(
        [_observation_point("tc_demo", "N6_A"), _observation_point("tc_other", "N6_B")],
        revision_markers={"tc_demo": "N6_A", "tc_other": "N6_OTHER"})
    result = _validate("n6", payload, offered=both, run_dir=run_dir)
    assert result["ok"] is False
    assert any("未出现在该用例 edits[].new" in p and "N6_B" in p
               for p in result["problems"]), result["problems"]
    # ③ marker 格式非法
    result = _validate("n6", _n6_payload([_observation_point("tc_demo", "FPGA_DATE")]),
                       offered={"cases": {"tc_demo"}}, run_dir=run_dir)
    assert result["ok"] is False
    assert any("marker 格式非法" in p for p in result["problems"]), result["problems"]
    # ④ 重复 marker / 非法十六进制值
    dup = _n6_payload([_observation_point("tc_demo", "N6_A"),
                       _observation_point("tc_demo", "N6_A")],
                      revision_markers={"tc_demo": "N6_A"})
    assert any("marker 重复" in p
               for p in _validate("n6", dup, offered=both, run_dir=run_dir)["problems"])
    bad_hex = _n6_payload([_observation_point("tc_demo", "N6_A", expected_value="20260708")])
    result = _validate("n6", bad_hex, offered={"cases": {"tc_demo"}}, run_dir=run_dir)
    assert any("expected_value" in p for p in result["problems"]), result["problems"]


async def test_n6_author_fails_closed_when_observation_points_invalid(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P-25：观测点约束失败 ⇒ N6 **立即** node_failed（不得静默继续到 N6_apply）。"""
    from test_fix_real_chain import FakeData, _n5_n2_for_targets
    from workflows.chunks import model_steps

    ctx = _real_run_ctx(tmp_path)
    env = tmp_path / "env"
    (env / "TESTLIB").mkdir(parents=True)
    (env / "TESTLIB" / "tc_demo.sv").write_text(
        "module tc_demo;\n  initial begin\n    check(0x0000+0x04, 8'h23);\n  end\nendmodule\n",
        encoding="utf-8")
    _n5_n2_for_targets(ctx)

    async def invalid(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"mode": "live", "standin": False, "provider": "fake",
                "validation": {"ok": False,
                               "problems": ["缺少目标用例的 observation_points：['tc_demo']"]},
                "data": {"revisions": [], "observation_points": []}}

    monkeypatch.setattr(model_steps, "run_model_node", invalid)
    data = FakeData(resources={"repo_root": env}, input={"baseline": "v0"})
    with pytest.raises(RuntimeError, match="observation_points"):
        await model_steps.n6_author(data)
    failed = [e for e in ctx.progress.read()
              if e.get("kind") == "node_failed" and e.get("node") == "N6"]
    assert failed, "观测点校验失败必须留 node_failed（不得静默继续）"
    assert "observation_points" in failed[-1]["detail"]["message"]


def test_p25_n6_prompt_requires_observation_points() -> None:
    """P-25：提示词必须要求观测点打印实际值、marker 写进 edits，形态带 0x 前缀。"""
    from workflows.chunks.model_common import load_prompts

    spec = load_prompts()["n6_author"]
    rules = " ".join(spec["info"]["rules"])
    instruct = " ".join(spec["instruct"])
    assert "observation_points" in rules and "至少" in rules, rules
    assert "edits[].new" in rules and "只列不写" in rules, rules
    assert "0x%08h" in instruct and "实际读回" in instruct, instruct
    assert "N6_<检查点名>" in rules


def test_n5_to_check_projection_counts_items_and_cases() -> None:
    """P-19：待查条目数与去重用例数分开下发；产物没有 `to_check` ⇒ 两者显式 None。"""
    from workflows.chunks.host_steps import _to_check_fields

    doc = {"to_check": [
        {"case": "tc_a", "entry_id": None},
        {"case": "tc_a", "entry_id": "0x0000#0x0004"},   # 同一用例的多条待查
        {"case": "tc_b"},
        {"entry_id": None},                              # 没有 case 名：只计条目
    ]}
    fields = _to_check_fields(doc)
    assert fields["to_check_count"] == 4, "条目数与产品清单一致（与 must_change_count 同口径）"
    assert fields["to_check_cases"] == ["tc_a", "tc_b"]
    assert fields["to_check_case_count"] == 2
    assert fields["to_check_case_count"] <= fields["to_check_count"]

    absent = _to_check_fields({"must_change": []})
    assert absent == {"to_check_count": None, "to_check_cases": [],
                      "to_check_case_count": None}
    assert _to_check_fields({"to_check": "stdout 里的一行"})["to_check_case_count"] is None


def test_n16_result_artifact_numbering(tmp_path: Path) -> None:
    from workflows.chunks.host_steps import _n16_result_path

    assert _n16_result_path(tmp_path).name == "n16_result.json"
    (tmp_path / "n16_result.json").write_text("{}", encoding="utf-8")
    assert _n16_result_path(tmp_path).name == "n16_result.2.json"
    (tmp_path / "n16_result.2.json").write_text("{}", encoding="utf-8")
    assert _n16_result_path(tmp_path).name == "n16_result.3.json"


def test_p14_prompt_requires_conditional_grouping_and_summary_order() -> None:
    """P-14 ①–③：提示词与 schema 必须写清「空段不硬分组 / 先说改了什么 / 风险+依据」。"""
    from prompts.node_schemas import N3Output
    from workflows.chunks.model_common import load_prompts

    spec = load_prompts()["n3_digest"]
    instruct = " ".join(spec["instruct"])
    rules = " ".join(spec["info"]["rules"])
    assert "offered_segments" in instruct and "不硬分组" in instruct, instruct
    assert "先说改了什么" in instruct and "影响面" in instruct, instruct
    assert "一句风险 + 依据" in instruct, instruct
    assert "offered_segments 为空时不要分组" in rules, rules
    props = N3Output.model_json_schema()["properties"]
    assert "offered_segments" in props["groups"]["description"]
    assert "先说改了什么" in props["summary"]["description"]
    assert "一句风险 + 依据" in props["risky_points"]["description"]


def _real_run_ctx(tmp_path: Path):
    """构造 real 模式 RunCtx（复用既有 real-chain 测试的 fake admission/runner）。"""
    from host.progress import ProgressLog
    from services.contracts import KbSources
    from test_fix_real_chain import FakeAdmission, FakeRunner, use_ctx
    from workflows.context import RunCtx

    run_id = "RUN-20261023-191500"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    kb_root = tmp_path / "kb"
    (kb_root / "conflicts").mkdir(parents=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []},
                   ensure_ascii=False), encoding="utf-8")
    kb = KbSources.from_workspace(kb_root)
    return use_ctx(RunCtx(run_id=run_id, run_dir=run_dir, mode="real", scenario="happy",
                          kb=kb, progress=ProgressLog(tmp_path / "events", run_id),
                          admission=FakeAdmission(), runner=FakeRunner()))


async def test_n9_n15_real_detail_fields_and_submit_started(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """P-24/P-32/P-33 的 **real 分支**：执行语义与提交节点开始事件。

    用真实产物形状（沙箱件 + evidence 日志 + Host 聚合契约）驱动，判据仍是真实代码给出。
    """
    from test_fix_real_chain import FakeData, _fake_aggregate, _write_case_log
    from workflows.chunks import long_jobs

    ctx = _real_run_ctx(tmp_path)
    monkeypatch.setattr(long_jobs, "aggregate_evidence", _fake_aggregate)
    cases = ["tc_demo", "tc_other"]
    md5s: dict[str, str] = {}
    for case in cases:
        sandbox = ctx.run_dir / "sandbox" / "TESTLIB" / f"{case}.sv"
        sandbox.parent.mkdir(parents=True, exist_ok=True)
        sandbox.write_text("module x; endmodule\n", encoding="utf-8")
        md5s[case] = long_jobs._md5_file(sandbox)
        _write_case_log(ctx, case)
    job = {"job_id": "JOB-0001", "node": "N9", "cases": cases, "expected_cases": cases,
           "md5s": md5s, "seed": "1", "sandbox_root": str(ctx.run_dir / "sandbox"),
           "evidence_dir": str(ctx.run_dir / "evidence")}
    resume = FakeData(state={"n9_job": job})
    resume.is_resume = True
    resume.resume = SimpleNamespace(value={"job_id": "JOB-0001", "phase": "done", "rc": 0})
    await long_jobs.n9_park(resume)
    events = ctx.progress.read()
    n9 = _node_final(events, "N9")["detail"]
    assert n9["identity"]["consistent"] is True, "real 分支必须下发身份四方同值结论"
    assert n9["koutou1_by_case"] == {"tc_demo": 0, "tc_other": 0}
    assert n9["example_line"] is None, "口径一全 0 ⇒ 无示例行（不编）"
    assert [r["case"] for r in n9["cases_detail"]] == cases

    env = tmp_path / "env"
    (env / "TESTLIB").mkdir(parents=True)
    (env / "TESTLIB" / "tc_demo.sv").write_text("module tc_demo; endmodule\n", encoding="utf-8")
    state15 = {"n15_set": {"cases": ["tc_demo"], "g3_decision": "milestone_only"}}
    data = FakeData(resources={"repo_root": env}, state=dict(state15))
    parked = await long_jobs.n15_run(data)
    assert parked["status"] == "waiting"
    resume15 = FakeData(resources={"repo_root": env},
                        state={**state15, "n15_job": data.get_state("n15_job")})
    resume15.is_resume = True
    resume15.resume = SimpleNamespace(value={"job_id": "JOB-0001", "phase": "done", "rc": 0})
    _write_case_log(ctx, "tc_demo")
    await long_jobs.n15_run(resume15)
    events = ctx.progress.read()
    n15 = _node_final(events, "N15")["detail"]
    assert n15["executed"] is True and n15["will_really_run"] is True
    assert n15["cases"] == ["tc_demo"] and n15["failed_cases"] == []
    assert any(e.get("kind") == "node_started" and e.get("node") == "N15_submit"
               for e in events), "N15_submit 缺 node_started"
    submit_final = _node_final(events, "N15_submit")
    submitted = [e for e in events if e.get("kind") == "job_submitted" and e.get("node") == "N15"]
    assert submit_final["refs"][:1] == submitted[-1]["refs"][:1]
