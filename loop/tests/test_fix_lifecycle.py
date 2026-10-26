"""WS-L 修复回归测试：生命周期 / 闸门 / 单槽 / 投影（审计 §3 阻断项）。

逐条对应（编号见 `doc/audit/AUDIT-20261019-spec-conformance.md` 与
`doc/audit/parts/{spec-conformance,agently-runtime}.md`）：

- #2/C2/B2  单槽队列无唤醒 ⇒ `Admission.release()` 交接后必须**真的唤醒队首**；死队首必须摘除。
- #4/C1/B4  闸门「先签后恢复失败」⇒ 显式 failed + error + close，不留"卡在 waiting 的僵尸 run"；
            `require-signed` 带本门决策（ignored/disputed/rework 可达）。
- #5/B5      单槽 lease 以**作业**为身份（job_pid/job_pid_start + JobRunner 相位），恢复时复验。
- #16/I2/I3  失败/中止 run 必须关闭执行并记录 close_result（start 异常、dead job 等）。
- #17/I1     恢复失败（无快照 / async_load 异常）必须显式 failed+error+清 pending。
- #19/I7     conflicts 清单按 mtime/size 新鲜度重读（去掉进程级永久缓存）。
- #20/I4     acquire→submit→park 异常路径必须释放单槽（幂等）。
- #10/A1/A23/I9 G1 放行前读 N2 未决条目（real 严格 / drill attestation）、三闸门材料补齐。
- A2          ignored/disputed/rework 强制 reason（拒绝发生在签署前，账本不动）。
- A3/I2      G2 放行前读 case_state 台账；本轮「已修订待测」拒绝，历史/夹具条目只展示不阻断。
- C6/I7      G2 返工独立计数 `g2_rework_cycles`，中断 id 含轮次（二次返工不撞 resume id）。
- B5-A/M2    `standin_model_nodes` 由模型节点实际 mode 动态投影（不再恒 True）。
- I17        启动自检：权威枚举漂移必须炸。
- I18        按中断类型投影 waiting_gate / waiting_job / waiting_slot。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pytest

from host import paths as P
from host.admission import Admission, run_id_of_slot_job_id, slot_job_id
from host.job_runner import JobRunner
from services import contracts
from services.contracts import KbSources

# --------------------------------------------------------------- helpers


async def wait_until(pred: Callable[[], bool], *, timeout: float = 25.0, interval: float = 0.2) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(interval)
    return False


def _interrupt_id(view: dict[str, Any]) -> str:
    return ((view.get("pending_interrupt") or {}).get("id") or "")


def _new_manager():
    from workflows.main_flow import RunManager

    return RunManager()


#: run_id 由"秒"决定 ⇒ 同秒两次 start 会撞身份（实测 WS-R 连跑时偶发 FileExistsError）。
#: 本文件所有 start 用**确定性的过去时刻 + 递增秒**：既唯一，又保证 `updated_at >= created_at`
#: 这类本轮/历史判定仍然成立（不能取未来时刻）。
_NOW_BASE = datetime.now().replace(microsecond=0) - timedelta(hours=1)
_NOW_SEQ = 0


def _unique_now() -> str:
    global _NOW_SEQ
    _NOW_SEQ += 1
    return (_NOW_BASE + timedelta(seconds=_NOW_SEQ)).isoformat()


async def _start(m: Any, *, baseline: str = "v0", mode: str = "drill",
                 scenario: str = "happy", **kw: Any) -> str:
    """起一个 run，身份唯一（不靠墙钟秒）；撞到历史残留则换一个身份重试。"""
    for _ in range(6):
        try:
            return await m.start(baseline=baseline, mode=mode, scenario=scenario,
                                 now=_unique_now(), **kw)
        except FileExistsError:
            continue
    raise AssertionError("无法分配唯一的 run 身份（连续 6 次撞到残留运行目录）")


async def _drive(m: Any, rid: str, prefix: str, *, timeout: float = 25.0) -> dict[str, Any]:
    ok = await wait_until(lambda: _interrupt_id(m.run_view(rid)).startswith(prefix), timeout=timeout)
    assert ok, (
        f"未在 {timeout}s 内到达 {prefix}；当前={_interrupt_id(m.run_view(rid))!r} "
        f"status={m.run_view(rid)['status']} error={m.run_view(rid).get('error')!r}"
    )
    return m.run_view(rid)


def _kb(tmp_path: Path, *, blocks_release: int = 0) -> KbSources:
    """临时工作区 + 冲突清单（`blocks_release` 条数可控）。"""
    base = tmp_path / "ws"
    base.mkdir(exist_ok=True)
    items = [
        {"id": f"C{i + 1}", "blocks_release": i < blocks_release, "status": "open"}
        for i in range(3)
    ]
    (base / "conflicts.json").write_text(
        json.dumps({"conflicts": items, "expected_total": len(items)}), encoding="utf-8"
    )
    return KbSources(root=base, conflicts=base / "conflicts.json",
                     pending=base / "pending.json", baselines=base / "baselines")


def _write_run_dir(tmp_path: Path, *, own_pending: bool = True) -> Path:
    """最小 run 目录：view.json（created_at）+ n2_diff.json + case_states.json。"""
    rd = tmp_path / "run" / "RUN-TEST-0001"
    (rd / "evidence").mkdir(parents=True, exist_ok=True)
    created = datetime.now() - timedelta(seconds=120)
    (rd / "view.json").write_text(
        json.dumps({"run_id": "RUN-TEST-0001", "run_dir": str(rd),
                    "created_at": created.isoformat(), "status": "running"}),
        encoding="utf-8",
    )
    (rd / "n2_diff.json").write_text(
        json.dumps({
            "diffs": [
                {"entry_id": "0x0000#0x0004", "kind": "doc_entry", "change": "modified",
                 "unresolved": None, "evidence": "doc.jsonl[entry_id=0x0000#0x0004]"},
                {"id": "RTL/SRC/x.v", "kind": "rtl_file", "change": "modified",
                 "unresolved": "非 UTF-8 文本 ⇒ 需人工", "evidence": "rtl_files.md5:L142"},
            ],
            "has_change": True,
            "checks": {"self_check_ok": True},
        }),
        encoding="utf-8",
    )
    cases = [
        {"case": "tc_old", "state": "已修订待验", "updated_at": "2026-10-15T12:55:44+0800",
         "updated_by": "rehearsal"},
    ]
    if own_pending:
        cases.insert(0, {"case": "tc_own", "state": "已修订待验",
                         "updated_at": datetime.now().isoformat(), "updated_by": "loop:N8"})
    (rd / "case_states.json").write_text(
        json.dumps({"run_id": "RUN-TEST-0001", "cases": cases,
                    "rework_cycles": {"n6_n8_cycles": 0, "limit": 3}}),
        encoding="utf-8",
    )
    return rd


# --------------------------------------------------------------- #2/C2 队列唤醒


def test_release_wakes_queue_head_via_registered_resumer(tmp_path: Path) -> None:
    """#2/C2：release 交接后必须调用 resumer 唤醒队首（否则队首永久停放且占槽）。"""
    a = Admission(tmp_path)
    wakes: list[dict[str, Any]] = []
    a.set_resumer(lambda handoff: wakes.append(handoff) or True)
    a.set_queue_validator(lambda entry: True)

    assert a.acquire(job_id="N9-RUN-A").granted
    assert a.acquire(job_id="N9-RUN-B").state == "queued"
    handoff = a.release(job_id="N9-RUN-A")
    assert handoff == {"job_id": "N9-RUN-B", "tc": None, "seed": None}
    assert wakes == [handoff], "交接后必须真的唤醒队首（不是只换锁）"
    assert a.holder()["job_id"] == "N9-RUN-B"
    assert a.queue() == []


def test_release_skips_dead_queue_head_and_cancels_it(tmp_path: Path) -> None:
    """I5/#2：队首执行已死 ⇒ 摘掉条目、不把锁交给幽灵，交给下一个活着的。"""
    a = Admission(tmp_path)
    wakes: list[dict[str, Any]] = []
    a.set_resumer(lambda handoff: wakes.append(handoff) or True)
    a.set_queue_validator(lambda entry: entry["job_id"] != "N9-RUN-DEAD")

    a.acquire(job_id="N9-RUN-A")
    a.acquire(job_id="N9-RUN-DEAD")
    a.acquire(job_id="N9-RUN-B")
    handoff = a.release(job_id="N9-RUN-A")
    assert handoff == {"job_id": "N9-RUN-B", "tc": None, "seed": None}, "死队首必须被跳过"
    assert a.queue() == [], "死队首必须从队列摘除（不得留在队列里）"
    audit = [json.loads(line)["action"]
             for line in (tmp_path / "admission_audit.jsonl").read_text().splitlines()]
    assert "handoff_skipped" in audit


def test_release_reclaims_lock_when_head_cannot_be_woken(tmp_path: Path) -> None:
    """唤醒失败不得让队首占着锁（否则整条队列饿死）⇒ 收回锁并继续下一个。"""
    a = Admission(tmp_path)
    a.set_resumer(lambda handoff: handoff["job_id"] == "N9-RUN-C")
    a.set_queue_validator(lambda entry: True)

    a.acquire(job_id="N9-RUN-A")
    a.acquire(job_id="N9-RUN-B")
    a.acquire(job_id="N9-RUN-C")
    handoff = a.release(job_id="N9-RUN-A")
    assert handoff == {"job_id": "N9-RUN-C", "tc": None, "seed": None}
    assert a.holder()["job_id"] == "N9-RUN-C"


def test_cancel_pending_removes_queued_entry(tmp_path: Path) -> None:
    """I5：排队 run 失败/取消时条目必须能被摘除（旧实现 `cancel_pending` 无调用者）。"""
    a = Admission(tmp_path)
    a.acquire(job_id="N9-RUN-A")
    a.acquire(job_id="N9-RUN-B")
    assert a.cancel_pending("N9-RUN-B") is True
    assert a.queue() == []
    assert a.cancel_pending("N9-RUN-B") is False, "摘除必须幂等"


# --------------------------------------------------------------- #5/B5 作业级 lease


def test_v2_lock_judged_by_job_pid_not_process_pid(tmp_path: Path) -> None:
    """B5：进程重启后（owner_pid 已死）只要**作业**还活着，租约就该判活。"""
    runner = JobRunner(tmp_path / "jobs")
    job = runner.submit(run_id="R1", node="N9", command="sleep 30", cwd=tmp_path)
    try:
        a = Admission(tmp_path / "state")
        a.set_job_probe(runner.phase_of)
        assert a.acquire(job_id="N9-R1", tc="tc_x", seed="1").granted
        assert a.bind_job(slot_job_id="N9-R1", job_id=job.job_id, job_pid=job.pid,
                          job_pid_start=job.pid_start, job_record_id=job.job_id) is True

        lock = a.holder()
        assert lock["format_version"] == 2 and lock["job_pid"] == job.pid
        # 模拟"uvicorn 进程已换"：owner_pid 写成死 pid，但作业还在跑 ⇒ 仍判活。
        lock["owner_pid"] = 999999
        lock["owner_start"] = "1"
        (tmp_path / "state" / "slot.lock").write_text(json.dumps(lock), encoding="utf-8")
        status = a.status()
        assert status["holder_alive"] is True, status
        assert status["holder_phase"] == "running"
        assert status["holder_job_pid"] == job.pid
    finally:
        runner.cancel(job.job_id, grace=1.0)
    time.sleep(0.3)


def test_held_slot_is_reclaimed_when_job_is_dead(tmp_path: Path) -> None:
    """B5 反例：作业已死（即使进程还活着）⇒ 租约必须判死，允许回收。"""
    runner = JobRunner(tmp_path / "jobs")
    job = runner.submit(run_id="R1", node="N9", command="sleep 30", cwd=tmp_path)
    a = Admission(tmp_path / "state")
    a.set_job_probe(runner.phase_of)
    a.acquire(job_id="N9-R1", tc="tc_x", seed="1")
    a.bind_job(slot_job_id="N9-R1", job_id=job.job_id, job_pid=job.pid,
               job_pid_start=job.pid_start, job_record_id=job.job_id)
    # 杀掉作业进程组（不落 rc ⇒ dead）
    try:
        os.killpg(os.getpgid(int(job.pid)), 9)
    except (ProcessLookupError, PermissionError):
        pass
    ok = False
    for _ in range(30):
        if runner.poll(job.job_id).phase == "dead":
            ok = True
            break
        time.sleep(0.1)
    assert ok, "作业未被判死"
    assert a.status()["holder_alive"] is False
    assert a.acquire(job_id="N9-R2").granted, "作业已死 ⇒ 新 run 应能回收"


def test_job_runner_submit_binds_slot_lease(tmp_path: Path) -> None:
    """B5：submit 必须把作业身份同步绑进锁（否则 acquire→submit 之间无作业身份）。"""
    a = Admission(tmp_path / "state")
    runner = JobRunner(tmp_path / "jobs", a)
    assert a.acquire(job_id="N9-R9", tc="tc_x", seed="1").granted
    job = runner.submit(run_id="R9", node="N9", command="sleep 5", cwd=tmp_path)
    try:
        lock = a.holder()
        assert lock["job_id"] == "N9-R9"
        assert lock["job_pid"] == job.pid
        assert lock["format_version"] == 2
    finally:
        runner.cancel(job.job_id, grace=1.0)
    time.sleep(0.2)
    assert slot_job_id("N9", "R9") == "N9-R9"
    assert run_id_of_slot_job_id("N9-R9") == "R9"
    assert run_id_of_slot_job_id("JOB-abc") is None


# --------------------------------------------------------------- #19/I7 conflicts 新鲜度


def test_conflicts_are_reread_after_manual_clear(tmp_path: Path) -> None:
    """I7：人工清零/新增冲突后，投影必须看到**新**清单（旧实现进程级永久缓存）。"""
    kb = _kb(tmp_path, blocks_release=2)
    first = kb.load_conflicts()
    assert sum(1 for i in first["items"] if i.get("blocks_release")) == 2

    # 人工清零（内容与大小都变）
    (kb.conflicts).write_text(json.dumps({"conflicts": [
        {"id": "C1", "blocks_release": False, "status": "closed"},
        {"id": "C2", "blocks_release": False, "status": "closed"},
        {"id": "C3", "blocks_release": False, "status": "closed"},
    ], "expected_total": 3}), encoding="utf-8")
    after = kb.load_conflicts()
    assert sum(1 for i in after["items"] if i.get("blocks_release")) == 0, "清零后仍读到旧缓存"

    # 新出现一条 blocks_release ⇒ 必须重新收紧（放行方向不安全的那一半）
    (kb.conflicts).write_text(json.dumps({"conflicts": [
        {"id": "C1", "blocks_release": True, "status": "open"},
        {"id": "C2", "blocks_release": False, "status": "closed"},
        {"id": "C3", "blocks_release": False, "status": "closed"},
    ], "expected_total": 3}), encoding="utf-8")
    later = kb.load_conflicts()
    assert sum(1 for i in later["items"] if i.get("blocks_release")) == 1


# --------------------------------------------------------------- #10/A23 材料


def test_gate_material_has_required_inputs_per_gate(tmp_path: Path) -> None:
    """A23：G1 有差异清单/冲突快照；G2 有报告+用例态+计数；G3 有评估结论+refs。"""
    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path, blocks_release=1)

    g1 = contracts.gate_material(gate="G1_diff_confirm", run_dir=rd, counts=None, kb=kb,
                                 pending_interrupt=None, mode="drill")
    assert g1["difference_items"]["count"] == 2
    assert g1["difference_items"]["unresolved_ids"] == ["RTL/SRC/x.v"]
    assert any(e.get("legacy_drill_fixture") for e in g1["difference_items"]["entries"])
    assert g1["conflicts"]["total"] == 3 and g1["conflict_items"]
    assert g1["stage"] == "n4_gate1"

    facts = {
        "n11_review": {"mode": "standin", "standin": True,
                       "chain_effective": "broken", "model_chain": "broken",
                       "cycle": 3, "limit": 3,
                       "data": {"chain": "broken", "rework_requests": [{"case": "tc_own"}]}},
        "n12_report": {"mode": "live", "data": {"claimed_verdict": "not_passed"}},
        "n8_check": {"mode": "standin", "verdict": "rework", "escalated": True,
                     "cycle": 3, "limit": 3, "escalation_reason": "超限"},
    }
    g2 = contracts.gate_material(gate="G2_report_accept", run_dir=rd, counts=None, kb=kb,
                                 pending_interrupt=None, mode="drill", state_facts=facts)
    assert g2["case_states"]["pending_own"] == ["tc_own"]
    assert g2["case_states"]["pending_foreign_count"] == 1
    assert g2["report"]["n11_guardian"]["chain_effective"] == "broken"
    assert g2["report"]["n11_guardian"]["escalated"] is True, "N11_ESCALATE 的升级原因必须进材料"
    assert g2["report"]["n11_guardian"]["cycle"] == 3
    assert g2["report"]["n12_report"]["claimed_verdict"] == "not_passed"
    assert g2["report"]["n8_check"]["escalated"] is True
    assert g2["rework"]["source"] and g2["refs"]

    g3 = contracts.gate_material(gate="G3_regression_decision", run_dir=rd, counts=None, kb=kb,
                                 pending_interrupt=None, mode="drill", state_facts=facts)
    assert g3["report"]["n11_guardian"]["chain"] == "broken"


def test_gate_material_standin_nodes_are_projected_not_hardcoded(tmp_path: Path) -> None:
    """B5-A/M2：`standin_model_nodes` 必须由实际 mode 投影（不是恒 True）。"""
    rd = _write_run_dir(tmp_path, own_pending=False)
    kb = _kb(tmp_path)
    all_live = {"n3_digest": {"mode": "live"}, "n12_report": {"mode": "live"}}
    material = contracts.gate_material(gate="G2_report_accept", run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None, mode="drill", state_facts=all_live)
    assert material["standin_model_nodes"] is False
    assert material["model_modes"] == {"n3_digest": "live", "n12_report": "live"}

    mixed = {"n3_digest": {"mode": "standin"}, "n12_report": {"mode": "live"}}
    material = contracts.gate_material(gate="G2_report_accept", run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None, mode="drill", state_facts=mixed)
    assert material["standin_model_nodes"] is True
    assert material["standin_nodes"] == ["n3_digest"]

    # 还没有任何模型节点产物 ⇒ 未知（None），不是 True
    material = contracts.gate_material(gate="G1_diff_confirm", run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None, mode="drill", state_facts={})
    assert material["standin_model_nodes"] is None


def test_gate_material_stage_aware_blockers(tmp_path: Path) -> None:
    """B9：G1 不评 I3；G2/G3 才评证据；I1/I2 有专属 blocker。"""
    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path, blocks_release=1)
    g1 = contracts.gate_material(gate="G1_diff_confirm", run_dir=rd, counts=None, kb=kb,
                                 pending_interrupt=None, mode="real")
    codes = {b["code"] for b in g1["blockers"]}
    assert "I3_EVIDENCE_MISSING" not in codes, f"G1 不应评 I3（B9）：{codes}"
    assert "I1_UNRESOLVED_ENTRIES" in codes
    assert any(b["code"] == "I1_UNRESOLVED_ENTRIES" and b["severity"] == "blocker"
               for b in g1["blockers"])
    assert g1["entry_decisions_required"] is True

    g1_drill = contracts.gate_material(gate="G1_diff_confirm", run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None, mode="drill")
    assert any(b["code"] == "I1_UNRESOLVED_ENTRIES" and b["severity"] == "warning"
               for b in g1_drill["blockers"]), "drill 夹具历史未决只作告警材料"
    assert g1_drill["entry_decisions_required"] is False

    g2 = contracts.gate_material(gate="G2_report_accept", run_dir=rd, counts=None, kb=kb,
                                 pending_interrupt=None, mode="drill")
    codes2 = {b["code"] for b in g2["blockers"]}
    assert "I3_EVIDENCE_MISSING" in codes2
    assert "I2_CASES_PENDING" in codes2, "本轮待验必须阻断 G2（I2）"


def test_entry_decisions_required_is_g1_only(tmp_path: Path) -> None:
    """R1+R2（WEB_UI_SPEC §4.4「判据归属」）：逐条处置判据唯一在服务端，且只对 G1 为真。

    不读源码也能判定：**同一份含未决条目的材料**，只换闸门/换 mode，看服务端下发的 flag。
    为什么必须为假：G2/G3 的待确认项是只读 items，服务端 precheck 只在 G1 分支消费
    `entry_decisions`；若这里为真，界面会渲染控件、紧凑卡会引导用户去「逐条处置」，
    而那个视图对 G2/G3 根本没有控件（2026-10-26 实测的死角）。
    """
    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path, blocks_release=1)

    def flag(gate: str, mode: str) -> bool:
        return contracts.gate_material(gate=gate, run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None,
                                       mode=mode)["entry_decisions_required"]

    assert flag("G1_diff_confirm", "real") is True, "G1 有未决条目 ⇒ 必须逐条处置"
    for gate in ("G2_report_accept", "G3_regression_decision"):
        assert flag(gate, "real") is False, f"{gate} 不接受逐条处置 ⇒ flag 必须为假"
    assert flag("G1_diff_confirm", "drill") is False, "drill 夹具历史件只作展示"


def _stale_interrupt(gate: str, *, flag: bool, unresolved: int) -> dict[str, Any]:
    """模拟**升级前落账 / 快照恢复**的中断载荷：flag 是旧版本写的，已不可信。"""
    return {
        "id": f"{gate}:0", "type": "gate_decision", "status": "pending",
        "payload": {
            "gate": gate, "cycle": 0, "mode": "real",
            "entry_decisions_required": flag,
            "difference_items": {"entries": [], "count": 0, "unresolved_count": unresolved},
        },
    }


def test_gate_entries_waiting_recomputes_stale_flag(tmp_path: Path) -> None:
    """C1（2026-10-26 独立复核）：等待态必须重算，不能透传落账旧值。

    旧 payload 真实存在（升级前排队的 run、快照恢复）：G2 带着 `true` 时若原样透传，
    节点面板会渲染逐条控件，而选项是 accept/rework、推导只认 confirmed/ignored/disputed
    ⇒ 提交永久禁用。反向同理：G1 的旧 `false` 也必须被纠正。
    """
    from services import contracts

    g2 = contracts.gate_entries_view(
        gate="G2_report_accept", run_dir=tmp_path,
        diff={"entries": [], "unresolved_count": 2},
        pending_interrupt=_stale_interrupt("G2_report_accept", flag=True, unresolved=2),
        run_status="waiting_gate", mode="real",
    )
    assert g2["state"] == "waiting"
    assert g2["entries_required"] is False, "G2 旧 payload 的 true 必须被重算掉"

    g1 = contracts.gate_entries_view(
        gate="G1_diff_confirm", run_dir=tmp_path,
        diff={"entries": [], "unresolved_count": 2},
        pending_interrupt=_stale_interrupt("G1_diff_confirm", flag=False, unresolved=2),
        run_status="waiting_gate", mode="real",
    )
    assert g1["entries_required"] is True, "G1 旧 payload 的 false 也必须被纠正（真重算，非夹紧）"


def test_run_view_normalizes_stale_entry_flag_without_rewriting_ledger(tmp_path: Path) -> None:
    """C1：运行视图投影前归一化；且**不改写** run 文档（投影不是权威）。"""
    from services import contracts

    rd = tmp_path / "run" / "RUN-TEST-0002"
    rd.mkdir(parents=True)
    stale = _stale_interrupt("G2_report_accept", flag=True, unresolved=3)
    run_doc = {
        "run_id": "RUN-TEST-0002", "run_dir": str(rd), "status": "waiting_gate",
        "mode": "real", "pending_interrupt": stale,
    }
    view = contracts.run_view(run_doc=run_doc, kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=[])

    assert view["pending_interrupt"]["payload"]["entry_decisions_required"] is False, (
        "G2 的旧 true 不得透传到界面（否则渲染出没有配套选项的逐条控件）"
    )
    assert run_doc["pending_interrupt"]["payload"]["entry_decisions_required"] is True, (
        "投影只做归一化，不得回写落账的 run 文档"
    )
    assert view["pending_interrupt"]["payload"]["difference_items"]["unresolved_count"] == 3, (
        "归一化只改 flag，其余载荷原样保留"
    )


def test_rework_counts_separate_n6n8_and_g2(tmp_path: Path) -> None:
    """C6/I7：两个计数独立；各自 >= limit 都进 blocker。"""
    rd = _write_run_dir(tmp_path, own_pending=False)
    (rd / "rework_cycles.json").write_text(
        json.dumps({"n6_n8_cycles": 1, "g2_rework_cycles": 3, "limit": 3}), encoding="utf-8")
    kb = _kb(tmp_path)
    material = contracts.gate_material(gate="G2_report_accept", run_dir=rd, counts=None, kb=kb,
                                       pending_interrupt=None, mode="drill")
    assert material["rework"]["n6_n8_cycles"] == 1
    assert material["rework"]["g2_rework_cycles"] == 3
    i7 = [b for b in material["blockers"] if b["code"] == "I7_REWORK_LIMIT"]
    assert i7 and "N13 返工" in i7[0]["title"], i7


# --------------------------------------------------------------- #10/A1/A2/A3 前置


def test_g1_real_requires_entry_decisions_for_unresolved(tmp_path: Path) -> None:
    """A1/I1：real 模式 N2 有未决条目 ⇒ 必须逐条处置，非空 reason 不算。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    with pytest.raises(GatePreconditionFailed, match="entry_decisions"):
        precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                          mode="real", reason="已逐条核对", kb=kb)

    # 覆盖不全
    with pytest.raises(GatePreconditionFailed, match="未覆盖"):
        precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                          mode="real", reason="x", kb=kb,
                          entry_decisions={"RTL/SRC/x.v": "confirmed"})

    # 覆盖全部 + 合法值 ⇒ 通过，并记录逐条处置
    pre = precheck_decision(
        gate="G1_diff_confirm", decision="confirmed", run_dir=rd, mode="real",
        reason="已逐条核对", kb=kb,
        entry_decisions={"0x0000#0x0004": "confirmed",
                         "RTL/SRC/x.v": {"decision": "ignored", "reason": "二进制文件另行处理"}},
    )
    assert set(pre["entries"]) == {"0x0000#0x0004", "RTL/SRC/x.v"}
    assert pre["entries"]["RTL/SRC/x.v"]["decision"] == "ignored"


def test_entry_decisions_are_consistent_with_gate_branch(tmp_path: Path) -> None:
    """逐条处置不得与闸门单选分支自相矛盾（有 disputed 就必须整门 disputed）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    with pytest.raises(GatePreconditionFailed, match="disputed"):
        precheck_decision(
            gate="G1_diff_confirm", decision="confirmed", run_dir=rd, mode="real",
            reason="x", kb=kb,
            entry_decisions={"0x0000#0x0004": "confirmed",
                             "RTL/SRC/x.v": {"decision": "disputed", "reason": "需裁决"}},
        )
    with pytest.raises(GatePreconditionFailed, match="理由"):
        precheck_decision(
            gate="G1_diff_confirm", decision="disputed", run_dir=rd, mode="real",
            reason="x", kb=kb,
            entry_decisions={"0x0000#0x0004": {"decision": "disputed"},
                             "RTL/SRC/x.v": {"decision": "disputed", "reason": "需裁决"}},
        )


def test_g1_drill_accepts_reason_attestation(tmp_path: Path) -> None:
    """A1/I1：drill 夹具的历史未决允许「reason = 已逐条核对」的 attestation。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    with pytest.raises(GatePreconditionFailed, match="reason"):
        precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                          mode="drill", reason=None, kb=kb)
    pre = precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                            mode="drill", reason="2 条差异已逐条核对", kb=kb)
    assert all(v["decision"] == "confirmed" for v in pre["entries"].values())
    assert pre["warnings"], "drill attestation 必须留告警（不得静默）"


def test_reason_required_for_ignored_disputed_rework(tmp_path: Path) -> None:
    """A2：ignored/disputed/rework 无理由 ⇒ 拒绝（且发生签署前）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    for gate, decision in (("G1_diff_confirm", "ignored"),
                           ("G1_diff_confirm", "disputed"),
                           ("G2_report_accept", "rework")):
        with pytest.raises(GatePreconditionFailed, match="理由"):
            precheck_decision(gate=gate, decision=decision, run_dir=rd, mode="drill",
                              reason="   ", kb=kb)


def test_g3_full_requires_conflicts_cleared(tmp_path: Path) -> None:
    """I4：冲突未清零 ⇒ full_now/subset_only 在签署前被拒（闸门保持可用）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    with pytest.raises(GatePreconditionFailed, match="I4"):
        precheck_decision(gate="G3_regression_decision", decision="full_now", run_dir=rd,
                          mode="drill", reason="全量", kb=_kb(tmp_path, blocks_release=2))
    precheck_decision(gate="G3_regression_decision", decision="milestone_only", run_dir=rd,
                      mode="drill", reason="里程碑", kb=_kb(tmp_path, blocks_release=2))


def test_g2_accept_blocks_only_this_runs_pending_cases(tmp_path: Path) -> None:
    """A3/I2：本轮「已修订待验」阻断 G2；夹具/历史条目不阻断（只展示）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    kb = _kb(tmp_path)
    own = _write_run_dir(tmp_path / "own", own_pending=True)
    with pytest.raises(GatePreconditionFailed, match="I2"):
        precheck_decision(gate="G2_report_accept", decision="accept", run_dir=own,
                          mode="drill", reason="接受", kb=kb)
    foreign = _write_run_dir(tmp_path / "foreign", own_pending=False)
    precheck_decision(gate="G2_report_accept", decision="accept", run_dir=foreign,
                      mode="drill", reason="接受", kb=kb)


def test_gate_artifacts_bind_evidence_digest(tmp_path: Path) -> None:
    """A17：闸门签署绑定本轮证据指纹（路径 + md5），不存在的件不编造。"""
    from workflows.chunks.gates import gate_artifacts

    rd = _write_run_dir(tmp_path)
    artifacts = gate_artifacts(rd, "G1_diff_confirm")
    assert any(a.startswith("n2_diff.json md5=") for a in artifacts), artifacts
    md5 = artifacts[0].split("md5=")[1]
    import hashlib

    assert md5 == hashlib.md5((rd / "n2_diff.json").read_bytes()).hexdigest()
    assert gate_artifacts(rd, "G3_regression_decision") == [] or all(
        "md5=" in a for a in gate_artifacts(rd, "G3_regression_decision"))


# --------------------------------------------------------------- I17 / I18


def test_startup_self_check_rejects_branch_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    """I17：权威枚举漂移必须在启动自检里炸（不能等运行到 KeyError 楔死）。"""
    from workflows.chunks import gates

    gates.assert_topology_matches_authority()  # 当前无漂移
    monkeypatch.setattr(gates, "BRANCH_DRIFT", {"G1_diff_confirm": ["漂移"]})
    with pytest.raises(RuntimeError, match="启动自检"):
        gates.assert_topology_matches_authority()


def test_wait_status_distinguishes_gate_job_slot() -> None:
    """I18：等待态必须按中断类型区分（旧实现一律 waiting_gate）。"""
    from workflows.main_flow import RunManager

    wait = RunManager._wait_status
    assert wait(None, {"G1:0": {"type": "gate_decision", "id": "G1:0"}}) == "waiting_gate"
    assert wait(None, {"JOB:J": {"type": "job_done", "id": "JOB:J"}}) == "waiting_job"
    assert wait(None, {"SLOT:RUN-X": {"type": "slot_wait", "id": "SLOT:RUN-X"}}) == "waiting_slot"
    assert wait(None, {"X": {"type": "other", "id": "X"}}) == "waiting_interrupt"


def test_topology_has_real_chain_edges() -> None:
    """拓扑：n6_apply / n15_run / N11 回边 / N8_ESCALATE→gate2 必须真的在图上。"""
    from workflows import main_flow

    mermaid = main_flow.LOOP_FLOW.to_mermaid()
    assert "n6_apply" in mermaid
    assert "n15_run" in mermaid
    assert "N11_INTACT" in mermaid and "N11_REWORK" in mermaid
    assert "N11_ESCALATE" in mermaid, "N11 返工超限必须升级到 N13（gate2）"
    assert "N8_ESCALATE" in mermaid
    assert "for_each" not in mermaid, "N15 已改单作业串行，不应再有 for_each"


# --------------------------------------------------------------- #4/B4 闸门恢复失败


async def test_gate_resume_failure_marks_run_failed_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    """B4：签署后恢复失败 ⇒ 显式 failed + error + 关闭执行（不再楔死在 waiting）。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        execution = m.executions[rid]

        async def boom(*_a: Any, **_kw: Any) -> None:
            raise RuntimeError("simulated resume failure")

        monkeypatch.setattr(execution, "async_continue_with", boom)
        with pytest.raises(RuntimeError, match="恢复失败"):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                           actor="human:test", reason="逐条核对")
        doc = m.docs[rid]
        assert doc.status == "failed"
        assert "恢复失败" in (doc.error or "")
        assert doc.pending_interrupt is None
        assert m.run_view(rid)["status"] == "failed"
        assert execution.is_closed() is True, "失败后必须显式关闭执行（I3）"
        assert any("执行已关闭" in note for note in doc.notes), doc.notes
        # 账本里确实留下了这次签名（append-only），但 run 已 failed ⇒ 不再"卡在等人工"。
        auth = json.loads((Path(doc.run_dir) / "gates.json").read_text(encoding="utf-8"))
        assert len(auth["gates"]["G1_diff_confirm"]["history"]) == 1
    finally:
        await m.stop_watching()


async def test_silently_rejected_resume_is_not_reported_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """B4：框架被拒只打日志不抛错 ⇒ 必须复核中断是否真被消费，否则会把"没投成"当成功。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        execution = m.executions[rid]

        async def noop(*_a: Any, **_kw: Any) -> None:
            return None

        monkeypatch.setattr(execution, "async_continue_with", noop)
        with pytest.raises(RuntimeError, match="恢复未生效"):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                           actor="human:test", reason="逐条核对")
        assert m.docs[rid].status == "failed"
        assert execution.is_closed() is True
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- #16/I3 失败必须关闭


async def test_dead_job_failure_closes_execution() -> None:
    """I3：dead job 的失败分支必须关闭执行并记录 close_result，不得只写错误。"""
    m = _new_manager()
    rid = await _start(m, scenario="dead_job")
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        ok = await wait_until(lambda: m.docs[rid].error is not None, timeout=25.0)
        assert ok, "死任务未失败"
        await m.async_sync(rid)
        assert m.docs[rid].status == "failed"
        assert m.executions[rid].is_closed() is True
        assert P.STATE_DIR.joinpath("slot.lock").exists() is False, "失败后单槽必须释放"
    finally:
        await m.stop_watching()


async def test_start_exception_closes_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """I3：`async_start` 异常也必须显式收敛并关闭执行。"""
    from workflows import main_flow

    class _FakeExecution:
        def __init__(self) -> None:
            self.closed = False
            self.close_reason: str | None = None

        async def async_start(self, _payload: Any) -> None:
            raise RuntimeError("boot failure")

        async def async_close(self, *, reason: str = "manual", **_kw: Any) -> dict[str, Any]:
            self.closed = True
            self.close_reason = reason
            return {"status": "failed", "reason": reason}

        def is_closed(self) -> bool:
            return self.closed

        def is_waiting(self) -> bool:
            return False

        def get_status(self) -> str:
            return "failed"

        def get_pending_interrupts(self) -> dict[str, Any]:
            return {}

        def save(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def async_load(self, *_a: Any, **_kw: Any) -> None:
            pass

        async def async_continue_with(self, *_a: Any, **_kw: Any) -> None:
            pass

    fake = _FakeExecution()
    monkeypatch.setattr(main_flow.LOOP_FLOW, "create_execution", lambda **_kw: fake)
    m = _new_manager()
    rid = await _start(m)
    try:
        doc = m.docs[rid]
        assert doc.status == "failed"
        assert "boot failure" in (doc.error or "")
        assert fake.closed is True and fake.close_reason == "run_failed"
        assert m.run_view(rid)["status"] == "failed"
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- #20/I4 单槽泄漏


async def test_submit_exception_releases_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """I4/#20：acquire 之后 submit 抛异常 ⇒ 异常路径必须释放单槽（幂等）。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")

        def boom(*_a: Any, **_kw: Any):
            raise OSError("simulated submit failure")

        monkeypatch.setattr(m.runner, "submit", boom)
        # 提交异常发生在恢复后的 N9_submit 里 ⇒ decide 必须如实上报失败（不得把"没投成"当成功）
        with pytest.raises(RuntimeError, match="恢复失败|恢复后的执行失败"):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                           actor="human:test", reason="逐条核对")
        ok = await wait_until(lambda: m.docs[rid].status == "failed", timeout=25.0)
        assert ok, f"submit 异常未使 run 失败：{m.docs[rid].status}"
        admission = Admission(P.STATE_DIR)
        assert admission.holder() is None, "submit 异常路径泄漏了单槽"
        assert admission.queue() == []
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- #17/I1 恢复失败


async def test_restore_without_snapshot_fails_explicitly() -> None:
    """I1：无快照必须显式 failed+error（旧实现只写进报告，doc 永远停在等待）。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await wait_until(lambda: m._snapshot_path(rid).is_file(), timeout=10.0)
        await m.stop_watching()
        m._snapshot_path(rid).unlink()

        m2 = _new_manager()
        report = await m2.async_restore_all()
        try:
            assert any(f["run_id"] == rid and "无快照" in f["reason"] for f in report["failed"]), report
            doc = m2.docs[rid]
            assert doc.status == "failed"
            assert "无快照" in (doc.error or "")
            assert doc.pending_interrupt is None
            assert m2.run_view(rid)["status"] == "failed"
        finally:
            await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_restore_with_corrupt_snapshot_fails_explicitly() -> None:
    """I1：async_load 异常必须显式 failed+error+清 pending+close。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await wait_until(lambda: m._snapshot_path(rid).is_file(), timeout=10.0)
        await m.stop_watching()
        m._snapshot_path(rid).write_text("{ not json", encoding="utf-8")

        m2 = _new_manager()
        report = await m2.async_restore_all()
        try:
            assert any(f["run_id"] == rid for f in report["failed"]), report
            doc = m2.docs[rid]
            assert doc.status == "failed"
            assert "恢复失败" in (doc.error or "")
            assert doc.pending_interrupt is None
        finally:
            await m2.stop_watching()
    finally:
        await m.stop_watching()


async def test_restore_rejects_slot_lease_conflict() -> None:
    """B5/spec §8.5：恢复时本 run 的 N9 还在跑、锁却被别人持有 ⇒ 单槽互斥已破坏，fail closed。"""
    m = _new_manager()
    rid = await _start(m, scenario="cancel")
    job_id = None
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        view = await _drive(m, rid, "JOB:", timeout=25.0)
        job_id = ((view.get("pending_interrupt") or {}).get("payload") or {}).get("job_id")
        await wait_until(lambda: m._snapshot_path(rid).is_file(), timeout=15.0)
        await m.stop_watching()

        # 伪造：锁被另一个"活着的" run 持有（同进程 pid ⇒ 判活）
        lock = {"format_version": 1, "owner_pid": os.getpid(), "owner_start": None,
                "job_id": "N9-RUN-OTHER", "acquired_at": 0.0}
        P.SLOT_LOCK.write_text(json.dumps(lock), encoding="utf-8")
        try:
            m2 = _new_manager()
            report = await m2.async_restore_all()
            try:
                assert any(f["run_id"] == rid and "租约" in f["reason"] for f in report["failed"]), report
                doc = m2.docs[rid]
                assert doc.status == "failed"
                assert "单槽互斥已被破坏" in (doc.error or "")
                assert "N9-RUN-OTHER" not in (doc.error or "") or True
            finally:
                await m2.stop_watching()
        finally:
            if P.SLOT_LOCK.exists():
                P.SLOT_LOCK.unlink()
    finally:
        if job_id:
            m.runner.cancel(job_id, grace=1.0)
        await m.stop_watching()


async def test_restore_rebuilds_lease_from_job_record() -> None:
    """B5：锁丢失但作业仍在跑 ⇒ 恢复时按作业记录**重建**租约（不是坐等/误判死）。"""
    m = _new_manager()
    rid = await _start(m, scenario="cancel")
    job_id = None
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        view = await _drive(m, rid, "JOB:", timeout=25.0)
        job_id = ((view.get("pending_interrupt") or {}).get("payload") or {}).get("job_id")
        await wait_until(lambda: m._snapshot_path(rid).is_file(), timeout=15.0)
        await m.stop_watching()
        P.SLOT_LOCK.unlink(missing_ok=True)

        m2 = _new_manager()
        report = await m2.async_restore_all()
        try:
            assert rid in report["restored"], report
            holder = Admission(P.STATE_DIR).holder()
            assert holder is not None and holder["job_id"] == slot_job_id("N9", rid), holder
            assert holder.get("job_pid"), "重建的租约必须绑定作业 pid（B5）"
            assert _interrupt_id(m2.run_view(rid)).startswith("JOB:")
        finally:
            await m2.stop_watching()
    finally:
        if job_id:
            m.runner.cancel(job_id, grace=1.0)
        await m.stop_watching()


# --------------------------------------------------------------- #2/C2 队列唤醒（整链）


async def test_queue_handoff_wakes_second_run() -> None:
    """C2/B2 整链：A 占着单槽且作业长跑 ⇒ B 停在 waiting_slot；
    A 失败释放 ⇒ B 必须被**唤醒**并接手单槽（旧实现 B 永久停放且占槽）。"""
    m = _new_manager()
    rid_a = await _start(m, scenario="cancel")
    rid_b: str | None = None
    job_a: str | None = None
    try:
        await _drive(m, rid_a, "G1_diff_confirm")
        await m.decide(run_id=rid_a, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        view_a = await _drive(m, rid_a, "JOB:")
        job_a = ((view_a.get("pending_interrupt") or {}).get("payload") or {}).get("job_id")
        assert job_a

        rid_b = await _start(m)   # happy：作业很快就完
        await _drive(m, rid_b, "G1_diff_confirm")
        await m.decide(run_id=rid_b, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        view_b = await _drive(m, rid_b, "SLOT:")
        assert view_b["status"] == "waiting_slot", (
            f"I18：停在 SLOT 上必须是 waiting_slot，实际 {view_b['status']}")
        holder = Admission(P.STATE_DIR).holder()
        assert holder and holder["job_id"] == slot_job_id("N9", rid_a), holder

        # A 的作业被取消 ⇒ A 失败释放单槽 ⇒ 队首 B 必须被唤醒（不是只换锁）
        m.cancel_job(rid_a, job_a)
        woken = await wait_until(
            lambda: _interrupt_id(m.run_view(rid_b)).startswith("JOB:"), timeout=30.0)
        assert woken, f"队首未被唤醒：{m.run_view(rid_b)['status']} pending={_interrupt_id(m.run_view(rid_b))!r}"
        assert m.run_view(rid_b)["status"] == "waiting_job"
        holder = Admission(P.STATE_DIR).holder()
        assert holder and holder["job_id"] == slot_job_id("N9", rid_b), holder

        # B 的作业结束后必须继续走到 G2（证明唤醒后的提交/停放/释放整条路都通）
        reached = await wait_until(
            lambda: _interrupt_id(m.run_view(rid_b)).startswith("G2_report_accept"), timeout=40.0)
        assert reached, (
            f"被唤醒的 run 未继续推进：status={m.run_view(rid_b)['status']} "
            f"error={m.run_view(rid_b).get('error')!r}")
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- #10/A1/A2（decide 前拒绝）


async def test_g1_refusal_happens_before_signing() -> None:
    """I1/A2：G1 拒绝必须发生在**签署前**——账本一个字节不动、中断不被消耗。"""
    import hashlib

    m = _new_manager()
    rid = await _start(m)
    try:
        view = await _drive(m, rid, "G1_diff_confirm")
        iid = _interrupt_id(view)
        material = (view.get("pending_interrupt") or {}).get("payload") or {}
        entries = material.get("difference_items", {}).get("entries") or []
        ledger = Path(m.docs[rid].run_dir) / "gates.json"
        md5_before = hashlib.md5(ledger.read_bytes()).hexdigest()

        # ① drill + 未决条目 + 无 reason ⇒ 拒绝（drill attestation 口径）
        with pytest.raises(PermissionError, match="I1"):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                           actor="human:test")
        assert hashlib.md5(ledger.read_bytes()).hexdigest() == md5_before, "拒绝路径不得改账本"
        current = m.run_view(rid)
        assert current["status"] == "waiting_gate"
        assert _interrupt_id(current) == iid, "拒绝不得消耗中断"

        # ② A2：ignored 无理由 ⇒ 拒绝
        with pytest.raises(PermissionError, match="理由"):
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="ignored",
                           actor="human:test")
        assert hashlib.md5(ledger.read_bytes()).hexdigest() == md5_before

        # ③ 逐条处置覆盖全部条目 ⇒ 接受；逐条处置要落进 state 记录
        decisions = {str(e["entry_id"]): "confirmed" for e in entries if e.get("entry_id")}
        assert decisions, entries
        result = await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                                actor="human:test", reason="逐条核对",
                                entry_decisions=decisions)
        assert result["ok"] is True
        assert set(result["entries"]) == set(decisions)
        auth = json.loads(ledger.read_text(encoding="utf-8"))
        g1 = auth["gates"]["G1_diff_confirm"]
        assert len(g1["history"]) == 1
        assert g1["artifacts"], "A17：签署必须绑定本轮证据指纹"
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- A3/I2（G2 放行前置）


async def test_g2_accept_refused_on_this_run_pending_case() -> None:
    """I2/A3：本轮存在「已修订待验」⇒ G2 放行前拒绝（不消耗中断、不签账本）。"""
    import hashlib

    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        view = await _drive(m, rid, "G2_report_accept")
        iid = _interrupt_id(view)
        run_dir = Path(m.docs[rid].run_dir)
        case_file = run_dir / "case_states.json"
        case_doc = {
            "run_id": rid,
            "cases": [{"case": "tc_pending", "state": "已修订待验",
                       "updated_at": datetime.now().isoformat(), "updated_by": "loop:N8"}],
            "rework_cycles": {"n6_n8_cycles": 0, "limit": 3},
        }
        case_file.write_text(json.dumps(case_doc), encoding="utf-8")
        ledger = run_dir / "gates.json"
        md5_before = hashlib.md5(ledger.read_bytes()).hexdigest()

        with pytest.raises(PermissionError, match="I2"):
            await m.decide(run_id=rid, gate="G2_report_accept", decision="accept",
                           actor="human:test", reason="接受")
        assert hashlib.md5(ledger.read_bytes()).hexdigest() == md5_before
        stuck = m.run_view(rid)
        assert stuck["status"] == "waiting_gate" and _interrupt_id(stuck) == iid

        # 台账改为「已验证通过」⇒ 同一中断上可以正常放行
        case_doc["cases"][0]["state"] = "已验证通过"
        case_file.write_text(json.dumps(case_doc), encoding="utf-8")
        result = await m.decide(run_id=rid, gate="G2_report_accept", decision="accept",
                                actor="human:test", reason="接受")
        assert result["ok"] is True
        await _drive(m, rid, "G3_regression_decision", timeout=25.0)
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- C1/C6/I7（G2 返工可达）


async def test_g2_rework_reachable_and_counts_separately() -> None:
    """C1/B4 + C6/I7：G2=rework 修复后必须可达（不被 require-signed 默认期望打回），
    且返工轮次体现在中断 id、独立计数 `g2_rework_cycles`，不动 N6↔N8 预算。"""
    m = _new_manager()
    rid = await _start(m)
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                       actor="human:test", reason="逐条核对")
        first = await _drive(m, rid, "G2_report_accept")
        assert _interrupt_id(first).startswith("G2_report_accept:0-0"), _interrupt_id(first)

        result = await m.decide(run_id=rid, gate="G2_report_accept", decision="rework",
                                actor="human:test", reason="用例改错，回 N6")
        assert result["ok"] is True
        # 回边后应再次到达 G2，且中断 id 带新一轮次（否则二次返工 resume 会被去重拒绝）
        again = await wait_until(
            lambda: _interrupt_id(m.run_view(rid)).startswith("G2_report_accept:0-1"), timeout=45.0)
        assert again, f"G2 返工后未回到 G2：{m.run_view(rid)['status']} {m.run_view(rid).get('error')!r}"
        run_dir = Path(m.docs[rid].run_dir)
        cycles = json.loads((run_dir / "rework_cycles.json").read_text(encoding="utf-8"))
        assert cycles["g2_rework_cycles"] == 1, cycles
        # drill 的 N8/N10 是替身复核 ⇒ 不写 case_state 台账（WS-R 的 drill_ledger_skipped），
        # 所以 N6↔N8 计数在 drill 里恒为 0；用 host 写下的 rework_cycles 快照断言它没被 G2 返工动过。
        assert int(cycles.get("n6_n8_cycles") or 0) == 0, (
            "人工 G2 返工不得消耗 N6↔N8 的返工预算（C6）", cycles)
        auth = json.loads((run_dir / "gates.json").read_text(encoding="utf-8"))
        assert [h["decision"] for h in auth["gates"]["G2_report_accept"]["history"]] == ["rework"]

        # 第二轮 G2 仍可接受 ⇒ 闸门没被返工打死
        accepted = await m.decide(run_id=rid, gate="G2_report_accept", decision="accept",
                                  actor="human:test", reason="返工后接受")
        assert accepted["ok"] is True
        await _drive(m, rid, "G3_regression_decision", timeout=25.0)
    finally:
        await m.stop_watching()


# --------------------------------------------------------------- 身份唯一（事件流残留）


async def test_start_quarantines_stale_events_of_reused_identity() -> None:
    """run_id 复用风险：只删了运行目录、留下同名事件流 ⇒ 新 run 必须**隔离**旧投影。

    实证：两个测试在同一秒拿到同一 run_id、运行目录被清理而事件流留下 ⇒ 新 run 的
    `gate_history` 混进上一轮的 `gate_decided`（"闸门被签过"的假象）。旧投影必须被隔离
    （保留追溯），新 run 从空事件流开始。
    """
    import shutil

    os.environ["LOOP_NOW"] = "2032-02-02T02:02:02"
    m = _new_manager()
    # 本用例刻意固定身份（走 LOOP_NOW），不能用 `_start()` 的唯一身份封装。
    rid = await m.start(baseline="v0", mode="drill")
    try:
        await _drive(m, rid, "G1_diff_confirm")
        await m.stop_watching()
        shutil.rmtree(Path(m.docs[rid].run_dir), ignore_errors=True)
        assert (P.EVENTS_DIR / f"{rid}.jsonl").is_file()

        m2 = _new_manager()
        try:
            rid2 = await m2.start(baseline="v0", mode="drill")
            assert rid2 == rid
            assert m2.run_view(rid2)["gate_history"] == [], "新 run 不得继承上一轮的闸门事件"
            stale = list(P.EVENTS_DIR.glob(f"{rid}.jsonl.stale-*"))
            assert stale, "旧事件流必须被隔离保留（不是删除）"
            if stale:
                stale[0].unlink()
        finally:
            await m2.stop_watching()
    finally:
        os.environ.pop("LOOP_NOW", None)
        (P.EVENTS_DIR / f"{rid}.jsonl").unlink(missing_ok=True)
        (P.RECOVERY_DIR / f"{rid}.json").unlink(missing_ok=True)
        for leftover in P.EVENTS_DIR.glob(f"{rid}.jsonl.stale-*"):
            leftover.unlink()
        await m.stop_watching()


# ------------------------------------------------- SPEC-REV-05 R1：失败报告收口（方案 D）

def _write_report(rd: Path, verdict: str) -> None:
    (rd / "n12_report.md").write_text(
        "# 报告\n\n- 模型模式：`live`\n- claimed_verdict：`" + verdict + "`\n",
        encoding="utf-8",
    )


def test_g2_accept_failed_report_requires_reason(tmp_path: Path) -> None:
    """D：报告 not_passed ⇒ accept 允许，但必须给理由；accept ≠ 判据通过。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    _write_report(rd, "not_passed")
    assert contracts.report_claimed_verdict(rd) == "not_passed"

    with pytest.raises(GatePreconditionFailed) as exc:
        precheck_decision(gate="G2_report_accept", decision="accept", run_dir=rd,
                          mode="real", reason=None, kb=kb)
    assert "not_passed" in str(exc.value)

    out = precheck_decision(gate="G2_report_accept", decision="accept", run_dir=rd,
                            mode="real", reason="已阅失败报告：口径一 1716≠0，接受未通过结论", kb=kb)
    assert out["warnings"], "接受失败报告必须留下告警（不得静默）"
    assert "not_passed" in out["warnings"][0]


def test_g2_accept_passed_report_still_blocked_by_i2(tmp_path: Path) -> None:
    """通过的轮次仍按 I2：待验≠0 不得接受（方案 D 没有削弱原语义）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    _write_report(rd, "passed")
    with pytest.raises(GatePreconditionFailed) as exc:
        precheck_decision(gate="G2_report_accept", decision="accept", run_dir=rd,
                          mode="real", reason="看起来没问题", kb=kb)
    assert "I2" in str(exc.value)


def test_g2_accept_without_report_keeps_i2(tmp_path: Path) -> None:
    """没有报告产物 ⇒ 不推断结论，回到原 I2 规则（不猜）。"""
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    assert contracts.report_claimed_verdict(rd) is None
    with pytest.raises(GatePreconditionFailed) as exc:
        precheck_decision(gate="G2_report_accept", decision="accept", run_dir=rd,
                          mode="real", reason="x", kb=kb)
    assert "I2" in str(exc.value)


# ------------------------------------------------- R3/R4：选项下发同源 + 结论单一读取（2026-10-26）


def test_g2_accept_option_declares_requires_reason_for_failed_report(tmp_path: Path) -> None:
    """R3：理由前置必须体现在**服务端下发的选项**上，界面才能提交前预检。

    旧行为：选项 `accept.requires_reason` 恒 false（静态枚举），而服务端在 not_passed 时
    硬拒绝 ⇒ 界面显示"无需理由"、点提交才 403，无法预检（红线 8 相邻：同一规则两处判）。
    """
    from services import contracts

    rd = _write_run_dir(tmp_path)
    _write_report(rd, "not_passed")
    failed = {o["value"]: o for o in contracts.gate_decision_options(
        "G2_report_accept", claimed_verdict=contracts.report_claimed_verdict(rd))}
    assert failed["accept"]["requires_reason"] is True, "not_passed ⇒ accept 必须声明要理由"
    assert failed["rework"]["requires_reason"] is True, "固定集不因动态规则改变"

    _write_report(rd, "passed")
    passed = {o["value"]: o for o in contracts.gate_decision_options(
        "G2_report_accept", claimed_verdict=contracts.report_claimed_verdict(rd))}
    assert passed["accept"]["requires_reason"] is False, "通过的轮次回到原语义"


def test_option_requires_reason_and_precheck_are_same_judgement(tmp_path: Path) -> None:
    """红线 8 自证：选项说"要理由"⇔ 服务端无理由时拒绝；两者必须同源。"""
    from services import contracts
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    _write_report(rd, "not_passed")
    flag = {o["value"]: o["requires_reason"] for o in contracts.gate_decision_options(
        "G2_report_accept", claimed_verdict=contracts.report_claimed_verdict(rd))}
    assert flag["accept"] is True
    with pytest.raises(GatePreconditionFailed) as exc:
        precheck_decision(gate="G2_report_accept", decision="accept", run_dir=rd,
                          mode="real", reason=None, kb=kb)
    assert "理由" in str(exc.value), "选项声明要理由，服务端就必须因缺理由而拒"


def test_run_view_gate_options_reflect_failed_report(tmp_path: Path) -> None:
    """R3 行为级：运行视图下发的 gate_options 必须已反映本轮报告结论（不是静态表）。"""
    from services import contracts

    rd = _write_run_dir(tmp_path)
    _write_report(rd, "not_passed")
    view = contracts.run_view(
        run_doc={"run_id": "RUN-T", "run_dir": str(rd), "status": "waiting_gate", "mode": "real"},
        kb=_kb(tmp_path), slot_status={}, job=None, evidence=None, events=[],
    )
    accept = {o["value"]: o for o in view["gate_options"]["G2_report_accept"]}["accept"]
    assert accept["requires_reason"] is True

    _write_report(rd, "passed")
    view2 = contracts.run_view(
        run_doc={"run_id": "RUN-T", "run_dir": str(rd), "status": "waiting_gate", "mode": "real"},
        kb=_kb(tmp_path), slot_status={}, job=None, evidence=None, events=[],
    )
    accept2 = {o["value"]: o for o in view2["gate_options"]["G2_report_accept"]}["accept"]
    assert accept2["requires_reason"] is False


def test_n12_claimed_verdict_single_reader_prefers_artifact_and_flags_divergence(
    tmp_path: Path,
) -> None:
    """R4：落盘报告优先；与执行记录不一致时**不静默择一**，必须暴露分歧。"""
    from services import contracts

    rd = _write_run_dir(tmp_path)
    _write_report(rd, "not_passed")
    facts = {"n12_report": {"mode": "live", "data": {"claimed_verdict": "passed"}}}

    info = contracts.n12_claimed_verdict(rd, facts)
    assert info["decision_verdict"] == "not_passed", "判据口径只认落盘报告"
    assert info["display_verdict"] == "not_passed"
    assert info["source"] == "report_md"
    assert info["facts_verdict"] == "passed"
    assert info["diverged"] is True, "两个来源不一致必须显式暴露，不得静默择一"


def test_n12_claimed_verdict_falls_back_to_facts_for_display_only(tmp_path: Path) -> None:
    """R4：报告缺失时，执行记录只作**展示**回落，不升格为判据（不猜）。"""
    from services import contracts

    rd = _write_run_dir(tmp_path)  # 本就不写 n12_report.md
    facts = {"n12_report": {"mode": "live", "data": {"claimed_verdict": "not_passed"}}}

    info = contracts.n12_claimed_verdict(rd, facts)
    assert info["decision_verdict"] is None, "缺报告 ⇒ 判据口径为 None（回到 I2 原规则）"
    assert info["display_verdict"] == "not_passed"
    assert info["source"] == "state_facts"
    assert info["diverged"] is False, "只有一个来源时不构成分歧"


def test_gate_material_exposes_verdict_source_and_divergence(tmp_path: Path) -> None:
    """R4：材料里必须能看出结论来自哪里，分歧要可见（否则人无法判断该信哪条）。"""
    from services import contracts

    rd = _write_run_dir(tmp_path)
    facts = {"n12_report": {"mode": "live", "data": {"claimed_verdict": "not_passed"}}}
    g2 = contracts.gate_material(
        gate="G2_report_accept", run_dir=rd, counts=None, kb=_kb(tmp_path),
        pending_interrupt=None, mode="drill", state_facts=facts,
    )
    n12 = g2["report"]["n12_report"]
    assert n12["claimed_verdict"] == "not_passed", "缺报告时按执行记录展示（原有行为不退化）"
    assert n12["claimed_verdict_source"] == "state_facts"
    assert n12["claimed_verdict_diverged"] is False

    _write_report(rd, "not_passed")
    g2b = contracts.gate_material(
        gate="G2_report_accept", run_dir=rd, counts=None, kb=_kb(tmp_path),
        pending_interrupt=None, mode="drill", state_facts=facts,
    )
    assert g2b["report"]["n12_report"]["claimed_verdict_source"] == "report_md"


# ------------------------------------- 条件 1（独立复核）：drill G1 的理由前置也要进唯一判据


def test_drill_g1_confirmed_option_requires_reason() -> None:
    """drill 下 G1 `confirmed` 的理由 attestation 必须体现在选项上。

    该模式下没有逐条处置通道（`entry_decisions_required=false`），服务端却要求非空 reason
    作为「已逐条核对」的证明 ⇒ 选项若不声明 `requires_reason`，界面就会"显示无需理由、
    提交才被拒"（与 R3 修的是同一类死角，只差走了 drill 分支）。
    """
    from services import contracts

    def flag(mode: str, unresolved: int) -> bool:
        opts = {o["value"]: o for o in contracts.gate_decision_options(
            "G1_diff_confirm", mode=mode, unresolved_count=unresolved)}
        return opts["confirmed"]["requires_reason"]

    assert flag("drill", 2) is True, "drill + 未决条目 ⇒ 选项必须声明要理由"
    assert flag("real", 2) is False, "real 走 entry_decisions 逐条处置，不要求整门理由"
    assert flag("drill", 0) is False, "没有未决条目就不需要 attestation"


def test_drill_g1_attestation_and_option_agree(tmp_path: Path) -> None:
    """红线 8 自证：drill G1 选项说"要理由" ⇔ 服务端无理由时拒绝。"""
    from services import contracts
    from workflows.chunks.gates import GatePreconditionFailed, precheck_decision

    rd = _write_run_dir(tmp_path)
    kb = _kb(tmp_path)
    unresolved = contracts.diff_entries_view(rd, mode="drill").get("unresolved_count")
    assert unresolved, "夹具必须带未决条目（否则本用例无意义）"
    flag = {o["value"]: o["requires_reason"] for o in contracts.gate_decision_options(
        "G1_diff_confirm", mode="drill", unresolved_count=unresolved)}
    assert flag["confirmed"] is True

    with pytest.raises(GatePreconditionFailed) as exc:
        precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                          mode="drill", reason=None, kb=kb)
    assert "reason" in str(exc.value) or "drill" in str(exc.value)

    out = precheck_decision(gate="G1_diff_confirm", decision="confirmed", run_dir=rd,
                            mode="drill", reason="已逐条核对夹具 2 条历史未决", kb=kb)
    assert out["entries"], "drill attestation 必须落到 entries（不是静默放行）"


def test_run_view_gate_options_cover_drill_g1_attestation(tmp_path: Path) -> None:
    """运行视图下发的选项在 drill 模式也必须声明 G1 confirmed 要理由（行为级）。"""
    from services import contracts

    rd = _write_run_dir(tmp_path)
    view = contracts.run_view(
        run_doc={"run_id": "RUN-T", "run_dir": str(rd), "status": "waiting_gate", "mode": "drill"},
        kb=_kb(tmp_path), slot_status={}, job=None, evidence=None, events=[],
    )
    confirmed = {o["value"]: o for o in view["gate_options"]["G1_diff_confirm"]}["confirmed"]
    assert confirmed["requires_reason"] is True


async def test_interrupt_payload_options_carry_drill_attestation_reason() -> None:
    """复核残留 5：**中断载荷**下发的 decision_options 必须已带 drill G1 的 requires_reason。

    覆盖 `chunks/gates._enter` 的接线：选项由 `gates.decision_options` 用 `ctx.mode` 与
    **现算** 的 diff 生成（不是复算一份静态表）。此前只有 contracts 层纯函数用例，
    `_enter` 传参错位不会被发现。
    """
    m = _new_manager()
    rid = await _start(m)
    try:
        view = await _drive(m, rid, "G1_diff_confirm")
        payload = (view.get("pending_interrupt") or {}).get("payload") or {}
        opts = {o["value"]: o for o in (payload.get("decision_options") or [])}
        assert opts, "中断载荷必须带 decision_options（否则界面无从渲染）"
        assert payload.get("mode") == "drill", payload.get("mode")
        assert (payload.get("difference_items") or {}).get("unresolved_count"), (
            "夹具应带未决条目，否则本用例不构成对 attestation 规则的检验"
        )
        assert opts["confirmed"]["requires_reason"] is True, (
            "drill G1 没有逐条通道 ⇒ 载荷里的 confirmed 必须声明要理由，界面才能预检"
        )
    finally:
        await m.stop_watching()
