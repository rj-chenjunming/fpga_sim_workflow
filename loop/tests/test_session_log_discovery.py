"""S8l（SPEC-REV-19 §2）：会话日志发现 —— `session_dir_name` 与 `find_latest_session_log`。

纪律：只认该 attempt 的 cwd 编码目录；同目录取 mtime 最新（并列按会话名最大，保证确定性）；
符号链接/非普通文件跳过；没有就 `None`（调用方给既有 `session_log_missing`，不编造空会话）。
"""
from __future__ import annotations

import os
from pathlib import Path

from host.agent_backends import dsh_sdk as SDK

HOME = "/run/agent_workspaces/N3/attempt-000001/dsh-home"
WORK = "/run/agent_workspaces/N3/attempt-000001/work"


def _session(home, cwd: str, session_id: str, *, mtime: float, name: str | None = None):
    directory = os.path.join(home, "sessions", SDK.session_dir_name(cwd), "session-" + session_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name or SDK.SESSION_LOG_NAME)
    with open(path, "wb") as handle:
        handle.write(b'{"type":"session","id":"s-1"}\n')
    os.utime(path, (mtime, mtime))
    return Path(path)


def test_session_dir_name_encodes_cwd_like_dsh():
    """唯一实现（红线 8）：`/<a>/<b>` → `--a-b--`，路径里真实的 `-`/`.` 原样保留。"""
    assert SDK.session_dir_name("/home/x/y-work") == "--home-x-y-work--"
    assert SDK.session_dir_name("/home/a.b/c-d") == "--home-a.b-c-d--"


def test_finds_session_of_the_attempt_cwd_only(tmp_path):
    home = tmp_path / "dsh-home"
    ours = _session(home, WORK, "1111", mtime=100.0)
    _session(home, "/other/work", "2222", mtime=999.0)      # 别的工作区：更新也不许借
    assert SDK.find_latest_session_log(home, work=WORK) == ours


def test_picks_newest_mtime_within_same_cwd(tmp_path):
    home = tmp_path / "dsh-home"
    _session(home, WORK, "aaaa", mtime=100.0)
    newest = _session(home, WORK, "bbbb", mtime=300.0)
    assert SDK.find_latest_session_log(home, work=WORK) == newest


def test_same_mtime_tie_breaks_on_session_name(tmp_path):
    home = tmp_path / "dsh-home"
    _session(home, WORK, "aaaa", mtime=200.0)
    winner = _session(home, WORK, "zzzz", mtime=200.0)
    assert SDK.find_latest_session_log(home, work=WORK) == winner


def test_skips_symlinked_and_suspicious_files(tmp_path):
    home = tmp_path / "dsh-home"
    real = _session(home, WORK, "1111", mtime=100.0)
    outside = tmp_path / "outside.jsonl.zstd"
    outside.write_bytes(b"x")
    directory = os.path.dirname(real)
    os.symlink(outside, os.path.join(directory, "session-2222"))
    os.makedirs(os.path.join(directory, "session-3333"), exist_ok=True)
    os.symlink(outside, os.path.join(directory, "session-3333", SDK.SESSION_LOG_NAME))
    assert SDK.find_latest_session_log(home, work=WORK) == real


def test_returns_none_without_sessions_dir(tmp_path):
    assert SDK.find_latest_session_log(tmp_path / "dsh-home", work=WORK) is None


def test_returns_none_when_no_matching_cwd(tmp_path):
    home = tmp_path / "dsh-home"
    _session(home, "/other/work", "1111", mtime=100.0)
    assert SDK.find_latest_session_log(home, work=WORK) is None


def test_ignores_other_file_names(tmp_path):
    home = tmp_path / "dsh-home"
    directory = os.path.join(home, "sessions", SDK.session_dir_name(WORK), "session-1111")
    os.makedirs(directory, exist_ok=True)
    (os.path.join(directory, "other.jsonl.zstd"))
    with open(os.path.join(directory, "other.jsonl.zstd"), "wb") as handle:
        handle.write(b"x")
    assert SDK.find_latest_session_log(home, work=WORK) is None
