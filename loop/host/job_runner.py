"""长任务作业器（外部作业的提交 / 看护 / 重附着 / 取消）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §6。

**它不是第二个状态机**：它只做一件事——把「外部进程结束」这个事实
**投递**进 TriggerFlow 的中断账本（`execution.continue_with`）。
这正是 `ExecutionExchange` 的角色（host UI/webhook/queue 传输适配），
唯一的恢复入口是 `continue_with`。

为什么长任务必须"提交后停放"而不是阻塞在 handler 里：
`agently-triggerflow/references/recovery.md` 明确——快照里若有
`running` / `cancel_requested` 帧，**load 会 fail-closed**。
一次全跑实测 `Elapsed 1140.79s`，修订后规模可达 22.8 h，
阻塞式 handler 会让重启恢复直接不成立。

完成判定靠**作业自己写 rc 文件**，而不是靠父进程的 `Popen.poll()`：
这样本进程崩溃重启后，新进程仍能凭 `/proc` + rc 文件判定作业命运。
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from .admission import Admission, TERMINAL_PROC_STATES, _proc_start_time, proc_state_start

JOB_FORMAT_VERSION = 1

JobPhase = str  # "running" | "done" | "dead" | "cancelled" | "cancelling"


@dataclass
class JobRecord:
    job_id: str
    run_id: str
    node: str
    argv: list[str]
    cwd: str
    log_path: str
    rc_path: str
    pid: int
    pid_start: str | None
    pgid: int
    started_at: float
    format_version: int = JOB_FORMAT_VERSION
    finished_at: float | None = None
    rc: int | None = None
    cancel_requested: bool = False
    delivered: bool = False
    resume_request_id: str | None = None
    tc: str | None = None
    seed: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobStatus:
    job_id: str
    phase: JobPhase
    rc: int | None
    alive: bool | None
    record: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "phase": self.phase, "rc": self.rc, "alive": self.alive, "record": self.record}


class JobRunner:
    def __init__(self, jobs_dir: Path, admission: Admission | None = None):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.admission = admission
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._stopping = False

    # ---------- 路径 ----------

    def record_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def log_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.log"

    def rc_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.rc"

    # ---------- 提交 ----------

    def submit(
        self,
        *,
        run_id: str,
        node: str,
        command: str,
        cwd: Path,
        tc: str | None = None,
        seed: str | None = None,
        note: str | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        job_id = job_id or f"JOB-{uuid.uuid4().hex[:12]}"
        log_path = self.log_path(job_id)
        rc_path = self.rc_path(job_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if rc_path.exists():
            rc_path.unlink()

        # 用 shell 包一层，作业自己落 rc —— 这是跨重启唯一可靠的完成凭据。
        wrapped = f"{command}\n__rc=$?\necho $__rc > {str(rc_path)!r}\nexit $__rc"
        log_fh = log_path.open("wb")
        proc = subprocess.Popen(
            ["/bin/bash", "-lc", wrapped],
            cwd=str(cwd),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # 独立进程组 ⇒ 取消能连同子进程一起收
        )
        try:
            pgid = os.getpgid(proc.pid)
        except OSError:
            pgid = proc.pid

        record = JobRecord(
            job_id=job_id,
            run_id=run_id,
            node=node,
            argv=["/bin/bash", "-lc", command],
            cwd=str(cwd),
            log_path=str(log_path),
            rc_path=str(rc_path),
            pid=proc.pid,
            pid_start=_proc_start_time(proc.pid),
            pgid=pgid,
            started_at=time.time(),
            tc=tc,
            seed=seed,
            note=note,
        )
        self._procs[job_id] = proc
        self.record_path(job_id).write_text(
            json.dumps(record.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record

    # ---------- 查询 ----------

    def record(self, job_id: str) -> dict[str, Any] | None:
        try:
            return json.loads(self.record_path(job_id).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def all_records(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.jobs_dir.glob("JOB-*.json")):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return out

    def _pid_alive(self, record: dict[str, Any]) -> bool:
        """僵尸子进程不能算活着（父进程未 wait 时 `/proc` 仍在）。"""
        pid = int(record["pid"])
        state, start = proc_state_start(pid)
        if state is None or state in TERMINAL_PROC_STATES:
            return False
        recorded = record.get("pid_start")
        return recorded in (None, start)

    def poll(self, job_id: str) -> JobStatus:
        """三态判定：rc 文件存在 ⇒ 完成（权威）；否则看进程是否活着；否则死任务。

        「已请求取消 + 进程已终结 + 无 rc」⇒ `cancelled`（取消是**我方动作**，与死任务区分开）。
        """
        record = self.record(job_id)
        if record is None:
            raise KeyError(f"未知作业：{job_id}")

        rc_path = Path(record["rc_path"])
        if rc_path.is_file():
            try:
                rc = int(rc_path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                rc = -1
            phase: JobPhase = "cancelled" if record.get("cancel_requested") else "done"
            self._persist_finish(job_id, record, rc=rc, phase=phase)
            return JobStatus(job_id, phase, rc, False, self.record(job_id) or record)

        if self._pid_alive(record):
            phase = "cancelling" if record.get("cancel_requested") else "running"
            return JobStatus(job_id, phase, None, True, record)

        # 进程已终结且没有 rc：取消请求 ⇒ cancelled；否则**死任务**（不许当成功）。
        phase = "cancelled" if record.get("cancel_requested") else "dead"
        self._persist_finish(job_id, record, rc=None, phase=phase)
        return JobStatus(job_id, phase, None, False, self.record(job_id) or record)

    def _persist_finish(self, job_id: str, record: dict[str, Any], *, rc: int | None, phase: str) -> None:
        if record.get("finished_at") is not None and record.get("rc") == rc and record.get("phase") == phase:
            return
        record = dict(record)
        record["finished_at"] = record.get("finished_at") or time.time()
        record["rc"] = rc
        record["phase"] = phase
        self.record_path(job_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def tail_log(self, job_id: str, *, lines: int = 20) -> list[str]:
        path = self.log_path(job_id)
        if not path.is_file():
            return []
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        except OSError:
            return []

    # ---------- 取消 ----------

    def cancel(self, job_id: str, *, grace: float = 5.0) -> bool:
        record = self.record(job_id)
        if record is None:
            return False
        record = dict(record)
        record["cancel_requested"] = True
        self.record_path(job_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.killpg(int(record["pgid"]), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            return False
        proc = self._procs.get(job_id)
        if proc is not None:
            try:
                proc.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(int(record["pgid"]), signal.SIGKILL)
                except OSError:
                    pass
        return True

    # ---------- 重附着 ----------

    def reattach(self) -> dict[str, list[dict[str, Any]]]:
        """崩溃重启后重新判定所有作业命运。

        - `running`：进程仍在 ⇒ 重新挂上完成投递；
        - `dead`：rc 缺失且进程不在 ⇒ **记死任务**，走失败分支（不得当成功）；
        - `done` 且未投递 ⇒ 补投递（幂等靠 `resume_request_id`）。
        """
        buckets: dict[str, list[dict[str, Any]]] = {"running": [], "done": [], "dead": [], "undelivered": []}
        for record in self.all_records():
            if record.get("format_version", JOB_FORMAT_VERSION) != JOB_FORMAT_VERSION:
                buckets.setdefault("unknown_format", []).append(record)
                continue
            status = self.poll(str(record["job_id"]))
            buckets.setdefault(status.phase, []).append(status.record)
            if status.phase in ("done", "dead", "cancelled") and not status.record.get("delivered"):
                buckets["undelivered"].append(status.record)
        return buckets

    def mark_delivered(self, job_id: str, *, resume_request_id: str) -> None:
        record = self.record(job_id)
        if record is None:
            return
        record = dict(record)
        record["delivered"] = True
        record["resume_request_id"] = resume_request_id
        self.record_path(job_id).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 完成投递桥 ----------

    async def watch(
        self,
        *,
        on_finished: Callable[[dict[str, Any]], Awaitable[None]],
        interval: float = 1.0,
    ) -> None:
        """把「外部作业结束」投递进中断账本。

        这是 host 侧的外部传输适配器：跨进程只有文件可见，
        因此这里用轮询读 `rc` 是**唯一诚实**的机制（不是用轮询替代框架内的信号/汇合）。
        """
        while not self._stopping:
            for record in self.all_records():
                if record.get("delivered"):
                    continue
                status = self.poll(str(record["job_id"]))
                if status.phase in ("done", "dead", "cancelled"):
                    await on_finished(status.as_dict())
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise

    def stop_watching(self) -> None:
        self._stopping = True
