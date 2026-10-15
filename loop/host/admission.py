"""单槽准入（外部容量 owner）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §7。

为什么必须是 host 持有的**单槽**而不是 TriggerFlow `concurrency=N`：
`uvs.setup` 是本仓库根下的全局单文件（`doc/AGENTS.md` §2 卡点 D），
同工作目录内并行跑两个用例会互相踩 `uvs.setup`。

**N9-3 修复**：锁带 `format_version`。陈旧判定**按格式版本决定解析哪些字段**；
遇到不认识的格式**拒绝自动清理并升级**，绝不用新格式的判据去读旧锁
（本轮演练实证：误判导致活动锁被删、约 10 分钟无互斥）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

CURRENT_FORMAT_VERSION = 1
#: 只有列在这里的格式版本才允许做「陈旧判定」。
SUPPORTED_FORMAT_VERSIONS: frozenset[int] = frozenset({1})

AcquireState = Literal["granted", "queued", "refused"]


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

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


def _owner_alive(info: dict[str, Any]) -> bool | None:
    """返回值：True=持有者活着；False=持有者已死；**None=无法判定（格式未知）**。

    `None` 是 N9-3 的关键分支：调用方必须**拒绝自动清理**，不得当作「已死」。
    """
    version = info.get("format_version")
    if version not in SUPPORTED_FORMAT_VERSIONS:
        return None
    pid = info.get("owner_pid")
    if not isinstance(pid, int) or pid <= 0:
        return None
    state, start = proc_state_start(pid)
    if state is None or state in TERMINAL_PROC_STATES:
        return False
    recorded = info.get("owner_start")
    if recorded is not None and start != recorded:
        # PID 被复用：原持有者已不存在。
        return False
    return True


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

    def __post_init__(self) -> None:
        self.state_dir = Path(self.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / "slot.lock"
        self.queue_path = self.state_dir / "queue.json"
        if self.audit_path is None:
            self.audit_path = self.state_dir / "admission_audit.jsonl"

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

    def status(self) -> dict[str, Any]:
        info = self.holder()
        alive = _owner_alive(info) if info else None
        return {
            "locked": info is not None,
            "holder": info,
            "holder_alive": alive,
            "holder_alive_known": alive is not None,
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
        queue.append({"job_id": owner.job_id, "tc": owner.tc, "seed": owner.seed, "requested_at": time.time()})
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

    def acquire(
        self,
        *,
        job_id: str,
        tc: str | None = None,
        seed: str | None = None,
        pid: int | None = None,
        note: str | None = None,
        force: bool = False,
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
        )
        try:
            self._write_lock(owner)
        except FileExistsError:
            pass
        else:
            self._audit("granted", job_id=job_id, tc=tc, seed=seed)
            return AcquireResult("granted", "lock_created", job_id, lock_path=self.lock_path)

        info = self.holder() or {}
        if info.get("job_id") == job_id:
            return AcquireResult("granted", "already_held_by_same_job", job_id, lock_path=self.lock_path)

        alive = _owner_alive(info)
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
        self._audit("reclaimed", job_id=job_id, holder=info, force=force, reason="owner_dead" if alive is False else "forced")
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
        try:
            self._write_lock(owner)
        except FileExistsError:
            return self._enqueue(owner, "race_after_reclaim")
        self._audit("granted", job_id=job_id, tc=tc, seed=seed, after="reclaim")
        return AcquireResult("granted", "reclaimed_dead_owner", job_id, lock_path=self.lock_path)

    def cancel_pending(self, job_id: str) -> bool:
        queue = self.queue()
        kept = [item for item in queue if item.get("job_id") != job_id]
        if len(kept) == len(queue):
            return False
        self.queue_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
        self._audit("dequeued", job_id=job_id)
        return True

    def release(self, *, job_id: str, handoff: bool = True) -> dict[str, Any] | None:
        """释放单槽；默认把槽**直接交接**给队首。幂等。"""
        info = self.holder()
        if info is not None and info.get("job_id") not in (None, job_id):
            self._audit("release_refused", job_id=job_id, holder_job_id=info.get("job_id"))
            return None
        if self.lock_path.exists():
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
            self._audit("released", job_id=job_id)

        granted_to: dict[str, Any] | None = None
        if handoff:
            queue = self.queue()
            while queue:
                head = queue.pop(0)
                self.queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
                result = self.acquire(
                    job_id=str(head.get("job_id")),
                    tc=head.get("tc"),
                    seed=head.get("seed"),
                    note="handoff",
                )
                if result.granted:
                    granted_to = {"job_id": head.get("job_id"), "tc": head.get("tc"), "seed": head.get("seed")}
                    break
                self._audit("handoff_skipped", job_id=head.get("job_id"), state=result.state, reason=result.reason)
            else:
                self.queue_path.write_text("[]", encoding="utf-8")
        return granted_to
