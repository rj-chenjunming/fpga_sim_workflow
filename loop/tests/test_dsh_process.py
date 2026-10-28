"""S1：DSH 执行器进程与协议（SPEC-REV-14 B4/B5/B8、设计 P4）。

不烧模型、不依赖真 dsh：协议用纯函数测；进程用 python stub 冒充 `dsh` CLI。
铁律：**退出码 0 / 空 final 都不算成功**；无 `turn_end` ⇒ 失败；bwrap 包裹只 bind attempt 目录。
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

from host.agent_backends import dsh_process as DP
from host.agent_backends import dsh_protocol as DPR

STUB = '''#!/usr/bin/env python3
import json, os, sys, time, subprocess
mode = os.environ.get("STUB_MODE", "ok")
argv = sys.argv[1:]
def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n"); sys.stdout.flush()
emit({"type": "session", "sessionId": "session-stub", "cwd": os.getcwd()})
if mode == "badframe":
    sys.stdout.write("this is not json\\n"); sys.stdout.flush()
elif mode == "no_terminal":
    emit({"type": "status", "phase": "turn_start", "turn": 1})
elif mode == "dup_terminal":
    emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
    emit({"type": "status", "phase": "turn_end", "reason": {"kind": "error", "error": {"code": "X", "message": "boom"}}})
elif mode == "refuse":
    emit({"type": "status", "phase": "turn_end",
          "reason": {"kind": "error", "error": {"code": "MISSING_CREDENTIAL", "message": "no key sk-SECRET"}}})
    emit({"type": "final", "text": ""})
elif mode == "hang":
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    open(os.environ["STUB_CHILD_PIDFILE"], "w").write(str(child.pid))
    time.sleep(60)
else:
    emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
    emit({"type": "final", "text": "OK"})
    emit({"type": "status", "phase": "step_end", "usage": {"inputTokens": 7, "outputTokens": 2}})
'''


def _stub(tmp_path: Path) -> Path:
    p = tmp_path / "dsh_stub.py"
    p.write_text(STUB, encoding="utf-8")
    p.chmod(0o755)
    return p


def _spec(tmp_path: Path, stub: Path, *, mode: str = "ok", wrap: bool = False,
          timeout_s: float = 30) -> DP.AttemptSpec:
    cwd = tmp_path / "attempt" / "work"
    home = tmp_path / "attempt" / "dsh-home"
    cwd.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    return DP.AttemptSpec(attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home, task="只回复 OK",
                          dsh_bin=stub, node=Path(sys.executable), patches=(),
                          timeout_s=timeout_s, wrap=wrap,
                          env_extra={"STUB_MODE": mode,
                                     "STUB_CHILD_PIDFILE": str(tmp_path / "child.pid")})


# ---------------------------------------------------------------- 协议（纯函数）

def _framed(stub_mode: str) -> list[str]:
    """把 STUB 的行为复制成内存帧，避免协议测试依赖子进程。"""
    base = ['{"type":"session","sessionId":"session-stub","cwd":"/w"}']
    if stub_mode == "ok":
        return base + ['{"type":"status","phase":"turn_end","reason":{"kind":"completed"}}',
                       '{"type":"final","text":"OK"}',
                       '{"type":"status","phase":"step_end","usage":{"inputTokens":7}}']
    if stub_mode == "no_terminal":
        return base + ['{"type":"status","phase":"turn_start","turn":1}']
    if stub_mode == "badframe":
        return base + ["not json"]
    if stub_mode == "dup_terminal":
        return base + ['{"type":"status","phase":"turn_end","reason":{"kind":"completed"}}',
                       '{"type":"status","phase":"turn_end","reason":{"kind":"error","error":{"code":"X"}}}']
    if stub_mode == "refuse":
        return base + ['{"type":"status","phase":"turn_end","reason":{"kind":"error","error":{"code":"MISSING_CREDENTIAL","message":"no key sk-SECRET"}}}',
                       '{"type":"final","text":""}']
    raise AssertionError(stub_mode)


def test_protocol_ok_completed() -> None:
    out = DPR.fold(_framed("ok"))
    assert out.status == "completed" and out.text == "OK"
    assert out.usage == {"inputTokens": 7}
    assert out.session_id == "session-stub" and out.cwd == "/w"


def test_protocol_badframe_is_explicit() -> None:
    with pytest.raises(DPR.BadFrame):
        DPR.fold(_framed("badframe"))


def test_protocol_missing_terminal_is_failure_even_with_exit_zero() -> None:
    with pytest.raises(DPR.NoTerminal):
        DPR.fold(_framed("no_terminal"))


def test_protocol_conflicting_terminal_is_failure() -> None:
    with pytest.raises(DPR.ConflictingTerminal):
        DPR.fold(_framed("dup_terminal"))


def test_protocol_error_reason_keeps_code() -> None:
    out = DPR.fold(_framed("refuse"))
    assert out.status == "failed"
    assert out.code == "MISSING_CREDENTIAL"
    assert out.text == ""


def test_protocol_identity_mismatch_rejected() -> None:
    with pytest.raises(DPR.IdentityMismatch):
        DPR.fold(_framed("ok"), expect_cwd="/other")


# ---------------------------------------------------------------- 进程（stub）

async def test_process_ok(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path))
    out = await DP.run_attempt(spec)
    assert out.status == "completed" and out.text == "OK"


async def test_process_no_terminal_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path), mode="no_terminal")
    with pytest.raises(DPR.NoTerminal):
        await DP.run_attempt(spec)


async def test_process_badframe_fails(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path), mode="badframe")
    with pytest.raises(DPR.BadFrame):
        await DP.run_attempt(spec)


async def test_process_refuse_is_failed_outcome(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path), mode="refuse")
    out = await DP.run_attempt(spec)
    assert out.status == "failed" and out.code == "MISSING_CREDENTIAL"
    # 协议层**不**做 redact（那是 backend 的职责，见 dsh.py）；这里只确认原始诊断被保留
    assert out.message == "no key sk-SECRET"
    assert out.text == ""


async def test_process_timeout_stops_group_and_cleans_children(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path), mode="hang", timeout_s=1.5)
    with pytest.raises(DP.StoppedOnTimeout):
        await DP.run_attempt(spec)
    pidfile = tmp_path / "child.pid"
    assert pidfile.exists(), "stub 未起子孙进程，用例无效"
    child = int(pidfile.read_text().strip())
    assert not Path(f"/proc/{child}").exists(), f"子孙进程 {child} 未被清理"


def test_build_argv_wraps_with_bwrap_and_binds_only_attempt(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path), wrap=True)
    argv = DP.build_argv(spec)
    text = " ".join(argv)
    assert "bwrap" in argv[0] or argv[0].endswith("bwrap")
    assert "--ro-bind" in argv and "--tmpfs" in argv
    assert str(spec.cwd) in argv          # attempt 目录被 bind
    assert "--unshare-pid" in argv        # 进程组/pid 隔离
    # 不得把宿主 home 写成可写挂载
    assert f"--bind {Path.home()} {Path.home()}" not in text


def test_build_env_is_allowlist_only(tmp_path: Path) -> None:
    spec = _spec(tmp_path, _stub(tmp_path))
    env = DP.build_env(spec)
    assert env.get("DSH_HOME") == str(spec.home)
    assert "PUBLIC_API_KEY" not in env or env.get("PUBLIC_API_KEY") == ""
    # 宿主上的无关变量不得透传
    assert "SSH_AUTH_SOCK" not in env and "HTTPS_PROXY" not in env or "HTTPS_PROXY" in spec.proxy_env
