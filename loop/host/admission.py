"""单槽准入（外部容量 owner）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §7。

为什么必须是 host 持有的**单槽**而不是 TriggerFlow `concurrency=N`：
`uvs.setup` 是本仓库根下的全局单文件（`doc/AGENTS.md` §2 卡点 D），
同工作目录内并行跑两个用例会互相踩 `uvs.setup`。

**N9-3 修复**：锁带 `format_version`。陈旧判定**按格式版本决定解析哪些字段**；
遇到不认识的格式**拒绝自动清理并升级**，绝不用新格式的判据去读旧锁
（本轮演练实证：误判导致活动锁被删、约 10 分钟无互斥）。

**B5 修复（lease 以作业为身份）**：格式 v2 在锁里增加 `job_pid / job_pid_start`。
判活时**优先看被提交的外部作业**（`JobRunner.poll()` 的相位 + 作业 pid），
只有作业尚未绑定（acquire 之后、submit 之前的短窗口，或历史 v1 锁）才回退看进程。
旧实现把 uvicorn 进程当 owner ⇒ 进程重启后仍在跑的外部作业的锁被判死、可被下一个 run 抢占，
两个仿真并发踩 `uvs.setup`（spec §7 单槽失效）。

**C2 修复（队列唤醒）**：`release()` 把槽交接给队首后，必须**真的把队首的执行唤醒**，
否则队首永久停在 `SLOT:` 中断且（旧实现）还持有锁。唤醒由 RunManager 注册的 `resumer`
完成（本模块不 import 编排层，避免反向依赖）；交接前先问 `queue_validator` 队首是否还活着，
死条目直接 `cancel_pending` 并跳过（I5：队列是状态，必须有终止清理）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

#: v1 = 进程 owner（历史）；v2 = 作业 owner（`job_pid`/`job_pid_start`）。
CURRENT_FORMAT_VERSION = 2
#: 只有列在这里的格式版本才允许做「陈旧判定」。
SUPPORTED_FORMAT_VERSIONS: frozenset[int] = frozenset({1, 2})

AcquireState = Literal["granted", "queued", "refused"]

#: 作业身份已终结的相位（与 `host/job_runner.poll()` 同一口径）。
TERMINAL_JOB_PHASES: frozenset[str] = frozenset({"done", "dead", "cancelled"})
LIVE_JOB_PHASES: frozenset[str] = frozenset({"running", "cancelling"})


def slot_job_id(node: str, run_id: str) -> str:
    """单槽租约 id 的唯一口径：`<节点>-<run_id>`。

    编排层的 chunk 用 `N9-<run_id>` / `N7-<run_id>` / `N15-<run_id>` 申请槽；
    `JobRunner.submit()` 用同一口径把**作业身份**绑定进锁（B5），
    两处各写一份字符串就会漂移，故只在这里定义。
    """
    return f"{node}-{run_id}"


def run_id_of_slot_job_id(job_id: str | None) -> str | None:
    """从租约 id 反解 run_id（`N9-RUN-2026...` ⇒ `RUN-2026...`）；不匹配返回 None。"""
    if not job_id or "-" not in job_id:
        return None
    head, _, rest = job_id.partition("-")
    if head not in ("N9", "N7", "N15") or not rest:
        return None
    return rest


def proc_state_start(pid: int) -> tuple[str | None, str | None]:
    """一次读取 `/proc/<pid>/stat`，返回 `(state, starttime)`。

    - `state`（字段 3）**必须看**：子进程被杀死后父进程尚未 `wait` 时，
      `/proc/<pid>` 仍然存在（僵尸态 `Z`）。只看"pid 存在"会把死作业判成在跑。
    - `starttime`（字段 22）用于防 PID 复用。

    `comm`（字段 2）可能含空格和括号，所以从**最后一个 `)`** 之后开始切分；
    该处剩余部分从字段 3 起，故 state 是下标 0，starttime 是下标 19。
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    close = raw.rfind(")")
    if close < 0:
        return None, None
    fields = raw[close + 2 :].split()
    if not fields:
        return None, None
    start = fields[19] if len(fields) > 19 else None
    return fields[0], start


#: 这些 state 表示"进程已终结"（僵尸/正在消亡）。
TERMINAL_PROC_STATES = frozenset({"Z", "X", "x"})


def _proc_start_time(pid: int) -> str | None:
    return proc_state_start(pid)[1]


def _pid_alive(pid: Any, start: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    state, current = proc_state_start(pid)
    if state is None or state in TERMINAL_PROC_STATES:
        return False
    if start is not None and current != start:
        # PID 被复用：原持有者已不存在。
        return False
    return True


@dataclass(frozen=True)
class SlotOwner:
    format_version: int
    owner_pid: int
    owner_start: str | None
    job_id: str
    tc: str | None = None
    seed: str | None = None
    acquired_at: float = 0.0
    note: str | None = None
    #: 被提交的外部作业身份（B5）。acquire 时未知，`JobRunner.submit()` 绑定。
    #: `job_id` 是**租约 id**（`N9-<run>`，用于归属/交接）；`job_record_id` 才是
    #: `JobRunner` 的记录 id（`JOB-<hex>`，用于查相位）。两者混用会让探针永远查不到作业。
    job_pid: int | None = None
    job_pid_start: str | None = None
    job_record_id: str | None = None

    def as_json(self) -> dict[str, Any]:
        out = asdict(self)
        # spec §7 的字段名是 `start_ts`；`acquired_at` 是历史落盘字段，两个都写。
        out["start_ts"] = out["acquired_at"]
        return out


def _owner_alive(info: dict[str, Any], *, job_phase: Callable[[str], str | None] | None = None) -> bool | None:
    """返回值：True=持有者活着；False=持有者已死；**None=无法判定（格式未知）**。

    `None` 是 N9-3 的关键分支：调用方必须**拒绝自动清理**，不得当作「已死」。
    """
    version = info.get("format_version")
    if version not in SUPPORTED_FORMAT_VERSIONS:
        return None

    if version >= 2 and job_phase is not None:
        record_id = info.get("job_record_id") or (
            info.get("job_id") if str(info.get("job_id") or "").startswith("JOB-") else None
        )
        if record_id:
            try:
                phase = job_phase(str(record_id))
            except Exception:
                phase = None
            if phase in TERMINAL_JOB_PHASES:
                # 作业已终结 ⇒ 租约已死，**即使 uvicorn 进程还活着**（B5 的 (a)）。
                return False
            if phase in LIVE_JOB_PHASES:
                return True

    if version >= 2:
        job_pid = info.get("job_pid")
        if isinstance(job_pid, int) and job_pid > 0:
            return _pid_alive(job_pid, info.get("job_pid_start"))
        # v2 但作业尚未绑定（acquire→submit 的短窗口）⇒ 回退到进程 owner。

    return _pid_alive(info.get("owner_pid"), info.get("owner_start"))


@dataclass
class AcquireResult:
    state: AcquireState
    reason: str
    job_id: str
    position: int | None = None
    holder: dict[str, Any] | None = None
    lock_path: Path | None = None

    @property
    def granted(self) -> bool:
        return self.state == "granted"

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["lock_path"] = str(self.lock_path) if self.lock_path else None
        out["granted"] = self.granted
        return out


@dataclass
class Admission:
    """单槽准入 + FIFO 队列 + 审计流水。"""

    state_dir: Path
    audit_path: Path | None = None
    _unused: tuple[()] = field(default=())
    #: 由 RunManager 注册（本模块不 import 编排层）：作业相位探针 / 队首存活校验 / 唤醒器。
    _job_phase: Callable[[str], str | None] | None = field(default=None, repr=False)
    _queue_validator: Callable[[dict[str, Any]], bool] | None = field(default=None, repr=False)
    _resumer: Callable[[dict[str, Any]], bool] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.state_dir = Path(self.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / "slot.lock"
        self.queue_path = self.state_dir / "queue.json"
        if self.audit_path is None:
            self.audit_path = self.state_dir / "admission_audit.jsonl"

    # ---------- 外部依赖注册（RunManager） ----------

    def set_job_probe(self, probe: Callable[[str], str | None] | None) -> None:
        """注册作业相位探针：`job_id -> phase|None`（RunManager 用 `JobRunner.poll()` 实现）。"""
        self._job_phase = probe

    def set_queue_validator(self, validator: Callable[[dict[str, Any]], bool] | None) -> None:
        """注册队首存活校验：返回 False 的队首被视为死条目（跳过 + cancel_pending）。"""
        self._queue_validator = validator

    def set_resumer(self, resumer: Callable[[dict[str, Any]], bool] | None) -> None:
        """注册队列唤醒器：`handoff -> 是否已把队首执行唤醒`。"""
        self._resumer = resumer

    # ---------- 读 ----------

    def holder(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.lock_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            # 半写入的锁：不猜，按无法判定处理。
            return {"format_version": None, "_corrupt": True}

    def queue(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        return data if isinstance(data, list) else []

    def holder_phase(self) -> str | None:
        """持有者对应**作业**的权威相位（无作业/无探针返回 None）。"""
        info = self.holder() or {}
        record_id = info.get("job_record_id") or (
            info.get("job_id") if str(info.get("job_id") or "").startswith("JOB-") else None
        )
        if not record_id or self._job_phase is None:
            return None
        try:
            return self._job_phase(str(record_id))
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        info = self.holder()
        alive = _owner_alive(info, job_phase=self._job_phase) if info else None
        return {
            "locked": info is not None,
            "holder": info,
            "holder_alive": alive,
            "holder_alive_known": alive is not None,
            # 作业级归属（B5）：界面要能回答"这条锁是进程的还是哪个作业的"。
            "holder_job_id": (info or {}).get("job_id"),
            "holder_job_pid": (info or {}).get("job_pid"),
            "holder_phase": self.holder_phase(),
            "format_version": (info or {}).get("format_version"),
            "queued": self.queue(),
            "queue_depth": len(self.queue()),
        }

    # ---------- 审计 ----------

    def _audit(self, action: str, **fields: Any) -> None:
        assert self.audit_path is not None
        record = {"ts": time.time(), "action": action, **fields}
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    # ---------- 写 ----------

    def _enqueue(self, owner: SlotOwner, reason: str) -> AcquireResult:
        queue = self.queue()
        for item in queue:
            if item.get("job_id") == owner.job_id:
                pos = queue.index(item) + 1
                return AcquireResult("queued", reason, owner.job_id, position=pos)
        queue.append({"job_id": owner.job_id, "tc": owner.tc, "seed": owner.seed,
                      "requested_at": time.time()})
        self.queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        self._audit("queued", job_id=owner.job_id, position=len(queue), reason=reason)
        return AcquireResult("queued", reason, owner.job_id, position=len(queue))

    def _write_lock(self, owner: SlotOwner) -> None:
        """原子占锁：`O_CREAT|O_EXCL` 是单机上唯一可靠的互斥原语。"""
        payload = json.dumps(owner.as_json(), ensure_ascii=False, indent=2)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)

    def _replace_lock(self, info: dict[str, Any]) -> None:
        """改写已有锁（绑定作业身份）。先写临时文件再 `os.replace`，避免半截锁。"""
        tmp = self.lock_path.with_suffix(".lock.tmp")
        tmp.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.lock_path)

    def _unlink_lock(self) -> bool:
        try:
            self.lock_path.unlink()
            return True
        except FileNotFoundError:
            return False

    # ---------- 作业身份绑定（B5） ----------

    def bind_job(
        self,
        *,
        slot_job_id: str,
        job_id: str,
        job_pid: int,
        job_pid_start: str | None = None,
        job_record_id: str | None = None,
    ) -> bool:
        """把已提交的外部作业身份写进租约（`JobRunner.submit()` 调用）。

        只改**自己的**锁：持有者的 `job_id` 必须仍是 `slot_job_id`，否则审计拒绝。
        这样进程崩溃后新进程能凭作业 pid/相位判活，而不是用 uvicorn pid 误判。
        """
        info = self.holder()
        if info is None:
            self._audit("bind_refused", slot_job_id=slot_job_id, job_id=job_id, reason="no_lock")
            return False
        if info.get("job_id") != slot_job_id:
            self._audit("bind_refused", slot_job_id=slot_job_id, job_id=job_id,
                        reason="held_by_other", holder_job_id=info.get("job_id"))
            return False
        updated = dict(info)
        updated["format_version"] = CURRENT_FORMAT_VERSION
        updated["job_pid"] = int(job_pid)
        updated["job_pid_start"] = job_pid_start
        if job_record_id is not None:
            updated["job_record_id"] = job_record_id
        try:
            self._replace_lock(updated)
        except OSError as exc:  # pragma: no cover - 磁盘异常
            self._audit("bind_failed", slot_job_id=slot_job_id, job_id=job_id, error=str(exc))
            return False
        self._audit("job_bound", slot_job_id=slot_job_id, job_id=job_id, job_pid=job_pid,
                    job_record_id=job_record_id)
        return True

    # ---------- 申请 / 释放 ----------

    def acquire(
        self,
        *,
        job_id: str,
        tc: str | None = None,
        seed: str | None = None,
        pid: int | None = None,
        note: str | None = None,
        force: bool = False,
        job_pid: int | None = None,
        job_pid_start: str | None = None,
    ) -> AcquireResult:
        owner = SlotOwner(
            format_version=CURRENT_FORMAT_VERSION,
            owner_pid=os.getpid() if pid is None else pid,
            owner_start=_proc_start_time(os.getpid() if pid is None else pid),
            job_id=job_id,
            tc=tc,
            seed=seed,
            acquired_at=time.time(),
            note=note,
            job_pid=job_pid,
            job_pid_start=job_pid_start,
        )
        try:
            self._write_lock(owner)
        except FileExistsError:
            pass
        else:
            self._audit("granted", job_id=job_id, tc=tc, seed=seed)
            return AcquireResult("granted", "lock_created", job_id, lock_path=self.lock_path)

        info = self.holder() or {}
        alive = _owner_alive(info, job_phase=self._job_phase)
        if info.get("job_id") == job_id and alive is not False:
            # M14：即便 job_id 相同，也要先确认持有者还活着（旧锁可能是死 run 留下的）。
            return AcquireResult("granted", "already_held_by_same_job", job_id, lock_path=self.lock_path)

        if alive is None and not force:
            # N9-3：不认识的锁格式 ⇒ 不清理、不排队抢，升级给人。
            self._audit("refused", job_id=job_id, reason="unrecognized_lock_format", holder=info)
            return AcquireResult(
                "refused",
                "unrecognized_lock_format",
                job_id,
                holder=info,
                lock_path=self.lock_path,
            )

        if alive is True and not force:
            return self._enqueue(owner, "slot_busy_by_live_owner")

        # 持有者已死（或显式 force）：清理并重试一次。
        self._audit("reclaimed", job_id=job_id, holder=info, force=force,
                    reason="owner_dead" if alive is False else "forced")
        self._unlink_lock()
        try:
            self._write_lock(owner)
        except FileExistsError:
            return self._enqueue(owner, "race_after_reclaim")
        self._audit("granted", job_id=job_id, tc=tc, seed=seed, after="reclaim")
        return AcquireResult("granted", "reclaimed_dead_owner", job_id, lock_path=self.lock_path)

    def cancel_pending(self, job_id: str) -> bool:
        """把排队条目摘掉（排队 run 失败/取消时必须调用；I5）。"""
        queue = self.queue()
        kept = [item for item in queue if item.get("job_id") != job_id]
        if len(kept) == len(queue):
            return False
        self.queue_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        self._audit("dequeued", job_id=job_id)
        return True

    def release(self, *, job_id: str, handoff: bool = True) -> dict[str, Any] | None:
        """释放单槽；默认把槽**直接交接**给队首并**唤醒它**。幂等。

        返回 `{"job_id","tc","seed"}` = 实际交接给谁；未交接返回 None。
        """
        info = self.holder()
        if info is not None and info.get("job_id") not in (None, job_id):
            self._audit("release_refused", job_id=job_id, holder_job_id=info.get("job_id"))
            return None
        if self.lock_path.exists():
            self._unlink_lock()
            self._audit("released", job_id=job_id)

        granted_to: dict[str, Any] | None = None
        if handoff:
            queue = self.queue()
            while queue:
                head = queue.pop(0)
                self.queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
                head_job_id = str(head.get("job_id"))
                # I5：队首必须是**还活着且仍在等槽**的执行；死条目直接摘掉，别把锁交给幽灵。
                if self._queue_validator is not None:
                    try:
                        alive_head = bool(self._queue_validator(head))
                    except Exception:
                        alive_head = False
                    if not alive_head:
                        self._audit("handoff_skipped", job_id=head_job_id, reason="queue_head_dead")
                        continue
                result = self.acquire(
                    job_id=head_job_id,
                    tc=head.get("tc"),
                    seed=head.get("seed"),
                    note="handoff",
                )
                if not result.granted:
                    self._audit("handoff_skipped", job_id=head_job_id, state=result.state,
                                reason=result.reason)
                    continue
                wake = {"job_id": head.get("job_id"), "tc": head.get("tc"), "seed": head.get("seed")}
                woke = True
                if self._resumer is not None:
                    try:
                        woke = bool(self._resumer(wake))
                    except Exception as exc:  # pragma: no cover - 唤醒器内部异常
                        self._audit("handoff_wake_failed", job_id=head_job_id, error=str(exc))
                        woke = False
                if not woke:
                    # 唤醒不了 ⇒ 不能让它占着锁（否则全队列饿死）；把锁收回，继续下一个。
                    self._audit("handoff_skipped", job_id=head_job_id, reason="wake_failed")
                    self._unlink_lock()
                    continue
                self._audit("handoff", from_job_id=job_id, to_job_id=head_job_id)
                granted_to = wake
                break
            else:
                self.queue_path.write_text("[]", encoding="utf-8")
        return granted_to
