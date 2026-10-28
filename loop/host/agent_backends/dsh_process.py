"""DSH 每 attempt 一个受管进程（S1 / SPEC-REV-14 B8·DS-10、REV-13 §5.3/§5.4）。

职责：**只做进程生命周期**（bwrap 包裹、env 白名单、超时、`TERM→KILL` 进程组、残留检查），
协议判定交给 `dsh_protocol`，业务校验仍归 Host 的 `_validate`。

不变量：
- 每次 attempt 独立进程、独立 session；不 resume 用户的会话（D3 的会话面在看板侧，不在这里）。
- 包裹（`wrap=True`）时：全盘只读 + 宿主 home 遮蔽 + 只 bind attempt 的 cwd/home + env 白名单。
  **不声称**挡 `/proc/<pid>/environ`（P0 实测同 uid 可读；D1 残余风险）。
- 超时/停机：`TERM` → 宽限 → `KILL` 进程组；停机后仍有子孙 ⇒ `LeftoverChildren`（execution_unknown 语义）。
"""
from __future__ import annotations

import asyncio
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path

from . import dsh_protocol as DPR


class AttemptError(RuntimeError):
    """进程层失败基类。"""


class ProcessFailed(AttemptError):
    """dsh 非零退出（且在超时之外）。"""


class StoppedOnTimeout(AttemptError):
    """超时后被停止；**不产生候选**，调用方必须显式失败。"""


class LeftoverChildren(AttemptError):
    """停机后仍能观察到同进程组成员的子孙（无法证明已停）。"""


#: 允许透传给 dsh 的最小环境变量（其余一律不透传；`env -i` 的等价物）
_BASE_ENV_KEYS = ("PATH", "HOME", "DSH_HOME", "DSH_PROFILE", "LANG", "LC_ALL",
                  "PYTHONDONTWRITEBYTECODE", "TZ")
_MIN_PATH = "/usr/bin:/bin"


@dataclass(frozen=True)
class AttemptSpec:
    attempt_key: str                      # 形如 RUN-…/N6/2（用于 issue/孤儿定位）
    cwd: Path                             # attempt 工作副本（唯一可写挂载之一）
    home: Path                            # 本 attempt 的 DSH_HOME（私有）
    task: str
    dsh_bin: Path
    node: Path
    patches: tuple[Path, ...] = ()
    profile: str = "headless"
    timeout_s: float = 600.0
    stop_grace_s: float = 5.0
    wrap: bool = True                     # bwrap 包裹（生产 True；单测可关）
    api_key: str | None = None            # 只进 env；不落文件
    api_key_env: str = "PUBLIC_API_KEY"
    proxy_env: dict[str, str] = field(default_factory=dict)
    env_extra: dict[str, str] = field(default_factory=dict)   # 显式白名单（测试/诊断）


def build_env(spec: AttemptSpec) -> dict[str, str]:
    """白名单环境：不继承宿主；凭据只经 env；代理需显式给。"""
    env = {"PATH": spec.env_extra.get("PATH", _MIN_PATH),
           "HOME": str(spec.home), "DSH_HOME": str(spec.home),
           "DSH_PROFILE": spec.profile, "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("LANG", "LC_ALL", "TZ"):
        value = spec.env_extra.get(key)
        if value:
            env[key] = value
    if spec.api_key:
        env[spec.api_key_env] = spec.api_key
    env.update({k: v for k, v in spec.proxy_env.items() if k and v})
    env.update({k: v for k, v in spec.env_extra.items() if k and k not in env})
    return env


def build_argv(spec: AttemptSpec) -> list[str]:
    """argv 用数组（绝不拼 shell 字符串）；包裹时只 bind attempt 的 cwd/home。"""
    inner = [str(spec.node), str(spec.dsh_bin), "--profile", spec.profile]
    for patch in spec.patches:
        inner += ["--patch", str(patch)]
    inner += ["--json", spec.task]
    if not spec.wrap:
        return inner
    host_home = str(Path.home())
    return ["bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--tmpfs", host_home,
            "--bind", str(spec.cwd), str(spec.cwd),
            "--bind", str(spec.home), str(spec.home),
            "--unshare-pid",
            "--die-with-parent",
            "--new-session",
            *inner]


def _group_members(pgid: int) -> list[int]:
    """扫描 /proc 找同进程组成员（停机自证；读不到就当空，不假装成功由调用方判定）。"""
    members: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open("/proc/%d/stat" % pid, "r", encoding="utf-8", errors="replace") as fh:
                fields = fh.read().rsplit(")", 1)[-1].split()
            pgrp = int(fields[2])
        except (OSError, ValueError, IndexError):
            continue
        if pgrp == pgid:
            members.append(pid)
    return members


async def _stop_group(proc: asyncio.subprocess.Process, grace_s: float) -> None:
    """TERM → 宽限 → KILL 整个进程组。"""
    for sig, wait_s in ((signal.SIGTERM, grace_s), (signal.SIGKILL, 10.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), wait_s)
            return
        except asyncio.TimeoutError:
            continue


async def run_attempt(spec: AttemptSpec, *, on_event=None) -> DPR.RunOutcome:
    """起一次 attempt：收帧、判终态；失败一律显式抛（不返回假候选）。"""
    argv = build_argv(spec)
    env = build_env(spec)
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=str(spec.cwd), env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True)

    wait_task = asyncio.create_task(proc.wait())
    out_task = asyncio.create_task(proc.stdout.read())
    err_task = asyncio.create_task(proc.stderr.read())
    timed_out = False
    try:
        await asyncio.wait_for(asyncio.gather(out_task, err_task, wait_task, return_exceptions=True),
                               timeout=spec.timeout_s)
    except asyncio.TimeoutError:
        timed_out = True
        await _stop_group(proc, spec.stop_grace_s)
        await asyncio.wait({out_task, err_task, wait_task}, timeout=10.0)

    def _value(task: "asyncio.Task[bytes]", default: bytes = b"") -> bytes:
        return task.result() if task.done() and not task.cancelled() and task.exception() is None \
            else default

    stdout, stderr = _value(out_task), _value(err_task)
    rc = proc.returncode
    leftovers = _group_members(proc.pid)
    if leftovers:
        raise LeftoverChildren(
            "attempt %s 停机后仍有同组进程存活：%s" % (spec.attempt_key, leftovers[:5]))
    if timed_out:
        raise StoppedOnTimeout(
            "attempt %s 超时 %.1fs 后被停止（TERM→KILL）" % (spec.attempt_key, spec.timeout_s))
    if rc != 0:
        tail = stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise ProcessFailed("attempt %s dsh 退出码 %s：%s"
                            % (spec.attempt_key, rc, " | ".join(tail)))

    lines = stdout.decode("utf-8", "replace").splitlines()
    for line in lines:
        if on_event is not None and line.strip():
            on_event(DPR.parse_frame(line))
    return DPR.fold(lines, expect_cwd=str(spec.cwd))
