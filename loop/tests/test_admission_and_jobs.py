"""验收 A5 / A6 / N9-3：单槽准入与长任务作业器。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from host.admission import Admission
from host.job_runner import JobRunner


def test_slot_is_single_and_second_waits(tmp_path: Path) -> None:
    """A6：并发两次申请，第二个排队而非并行。"""
    a = Admission(tmp_path)
    first = a.acquire(job_id="JOB-A", tc="tc_x", seed="1")
    second = a.acquire(job_id="JOB-B", tc="tc_y", seed="2")
    assert first.granted is True
    assert second.state == "queued" and second.position == 1
    assert a.holder()["job_id"] == "JOB-A"
    assert a.status()["queue_depth"] == 1


def test_release_hands_slot_to_queue_head(tmp_path: Path) -> None:
    a = Admission(tmp_path)
    a.acquire(job_id="JOB-A")
    a.acquire(job_id="JOB-B")
    granted = a.release(job_id="JOB-A")
    assert granted == {"job_id": "JOB-B", "tc": None, "seed": None}
    assert a.holder()["job_id"] == "JOB-B"
    assert a.status()["queue_depth"] == 0


def test_unknown_lock_format_is_refused_not_reclaimed(tmp_path: Path) -> None:
    """**N9-3 回归测试**：不认识的锁格式必须拒绝并升级，绝不能自动清理。

    本轮演练的真实故障：新代码用新格式判据去读旧锁 ⇒ 判为陈旧 ⇒
    删掉**活动锁** ⇒ 约 10 分钟无互斥。
    """
    a = Admission(tmp_path)
    lock = tmp_path / "slot.lock"
    lock.write_text(json.dumps({"owner_pid": 999999, "job_id": "OLD"}), encoding="utf-8")
    result = a.acquire(job_id="JOB-NEW")
    assert result.state == "refused"
    assert result.reason == "unrecognized_lock_format"
    assert lock.exists(), "不得清理不认识的锁"
    audit = [json.loads(line)["action"] for line in (tmp_path / "admission_audit.jsonl").read_text().splitlines()]
    assert "refused" in audit and "reclaimed" not in audit


def test_dead_owner_is_reclaimed(tmp_path: Path) -> None:
    """已知格式 + 持有者已死 ⇒ 允许回收（与上一条形成对照）。"""
    a = Admission(tmp_path)
    (tmp_path / "slot.lock").write_text(
        json.dumps({"format_version": 1, "owner_pid": 999999, "owner_start": "1",
                    "job_id": "DEAD", "acquired_at": 0}),
        encoding="utf-8",
    )
    result = a.acquire(job_id="JOB-NEW")
    assert result.granted is True and result.reason == "reclaimed_dead_owner"


def test_job_command_ending_with_exit_still_writes_rc(tmp_path: Path) -> None:
    """N9 real 全跑命令以 `exit 0` 结尾：rc 写入不能被它提前跳过。

    真实实证（2026-10-22 real 轮）：N9 三个用例全部 rc=0（证据日志齐全），
    但作业被判 `dead`（rc 文件缺失）⇒ 整个 run failed。根因是 JobRunner 把
    `__rc=$?; echo $__rc > <rc>` 追加在命令**之后**，命令自己的 `exit 0` 先退出了 shell。
    """
    runner = JobRunner(tmp_path / "jobs")
    rec = runner.submit(run_id="R1", node="N9",
                        command="echo working; exit 0", cwd=tmp_path)
    deadline = time.time() + 10
    status = runner.poll(rec.job_id)
    while status.phase == "running" and time.time() < deadline:
        time.sleep(0.05)
        status = runner.poll(rec.job_id)
    assert status.phase == "done", status
    assert status.rc == 0
    assert Path(rec.rc_path).is_file(), "rc 文件必须由 wrapper 写出"


def test_job_lifecycle_done_cancelled_dead(tmp_path: Path) -> None:
    """三态判定：有 rc ⇒ done；取消 ⇒ cancelled；无 rc 且进程没了 ⇒ **dead**。"""
    runner = JobRunner(tmp_path / "jobs")

    ok = runner.submit(run_id="R1", node="N9", command="echo hello", cwd=tmp_path)
    assert runner.poll(ok.job_id).phase == "running"
    time.sleep(0.7)
    status = runner.poll(ok.job_id)
    assert status.phase == "done" and status.rc == 0
    assert "hello" in " ".join(runner.tail_log(ok.job_id))

    long_job = runner.submit(run_id="R1", node="N9", command="sleep 60", cwd=tmp_path)
    runner.cancel(long_job.job_id, grace=2.0)
    assert runner.poll(long_job.job_id).phase == "cancelled"

    killed = runner.submit(run_id="R1", node="N9", command="sleep 60", cwd=tmp_path)
    os.kill(int(killed.pid), 9)
    time.sleep(0.4)
    # 僵尸态的 /proc 仍存在 —— 必须仍判为 dead，绝不能当成功
    assert runner.poll(killed.job_id).phase == "dead"


def test_reattach_reports_undelivered(tmp_path: Path) -> None:
    """A5：崩溃重启后能判定命运，且把"已结束但未投递"的作业挑出来补投。"""
    runner = JobRunner(tmp_path / "jobs")
    rec = runner.submit(run_id="R1", node="N9", command="true", cwd=tmp_path)
    time.sleep(0.6)
    buckets = runner.reattach()
    assert rec.job_id in [r["job_id"] for r in buckets["undelivered"]]
    runner.mark_delivered(rec.job_id, resume_request_id="rr-1")
    assert rec.job_id not in [r["job_id"] for r in runner.reattach()["undelivered"]]
