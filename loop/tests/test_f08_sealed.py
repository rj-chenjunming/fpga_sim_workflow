"""F08：封存发布边界的进程终止注入与恢复诊断。

观察矩阵见 `doc/spec/AGENT_CONTEXT_SPEC.md`「封存与恢复」：
- `absent / incomplete / corrupt / committed` 由 `AM.record_state` 只读判定；
- 半写记录（数据在、校验缺）不得被消费；其它尝试照常可读；
- 故障注入用**真实子进程终止**（`os._exit` / `SIGKILL`），不是内存变量模拟。

边界：本文件证明记录层状态与读取容错；不证明持久暂停/续跑（F09），也不证明真实 provider 行为。
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from host import agent_control as C
from host import agent_memory as AM
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.context import RunCtx

LOOP = Path(__file__).resolve().parents[1]


def make_ctx(tmp_path: Path, name: str = "RUN-F08-TEST") -> RunCtx:
    run = tmp_path / "runs" / name
    run.mkdir(parents=True)
    return RunCtx(run.name, run, "standin", "happy",
                  KbSources.from_workspace(tmp_path), ProgressLog(tmp_path / "events", run.name))


def run_child(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, timeout=120,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def test_fully_published_record_is_committed(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    attempt = AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest", "input": {"x": 1}})
    attempt.finish("validated", payload={"summary": "s"})
    assert AM.record_state(attempt.path / "request.json") == "committed"
    assert AM.record_state(attempt.path / "result.json") == "committed"
    AM.verify_attempt(attempt.path)


def _publish_fault_child(target: Path, body: str) -> subprocess.CompletedProcess:
    """在真实子进程里按**规格固定的发布协议**注入故障点后 `os._exit(9)`。

    故障点来自 `AGENT_CONTEXT_SPEC.md`「原子发布（R1）」：② `fsync` 临时件、③ 以
    `os.link` 不可覆盖发布最终名。不是内存 mock：半件真的落盘，进程真的终止。
    """
    return run_child(
        "import os, sys\n"
        f"sys.path.insert(0, {str(LOOP)!r})\n"
        "from pathlib import Path\n"
        "from host import agent_memory as AM\n"
        f"target = Path({str(target)!r})\n"
        + textwrap.dedent(body)
    )


def test_process_exit_between_data_and_checksum_is_incomplete_and_not_consumed(tmp_path: Path) -> None:
    """故障点：数据已发布到最终名、校验和尚未发布时终止（第 2 次原子发布前）。"""
    ctx = make_ctx(tmp_path)
    AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"}).finish("validated", payload={})
    folder = ctx.run_dir / "agent_calls" / "N3" / "attempt-000002"
    folder.mkdir(parents=True)
    target = folder / "request.json"
    proc = _publish_fault_child(target, """
        real_link = os.link
        published = []
        def link_then_exit(src, dst, **kwargs):
            published.append(str(dst))
            if len(published) == 2:
                os._exit(9)  # 数据已发布；校验和发布前终止
            return real_link(src, dst, **kwargs)
        os.link = link_then_exit
        AM.seal_record(target, {"prompt_key": "n3_digest", "input": {"x": 1}})
    """)
    assert proc.returncode == 9, (
        "旧实现没有不可覆盖的原子发布点（os.link 未被调用），数据/校验和直接以 "
        "O_EXCL 落在最终名上；缺陷正是发布空窗。stderr=" + proc.stderr)
    assert target.is_file() and not target.with_suffix(".sha256").is_file()
    assert AM.record_state(target) == "incomplete"
    with pytest.raises(ValueError, match="incomplete"):
        AM.verify_attempt(folder)
    # 读取视图不得整体抛错：该尝试标 incomplete，且不进入可消费记录；旧完整尝试仍可读
    view = C.read_view(ctx.run_dir, "N3")
    assert [item["status"] for item in view["attempts"]] == ["validated", "incomplete"]
    assert view["selected_attempt"] == 1
    assert view["request"]["prompt_key"] == "n3_digest"


def test_kill_while_writing_publish_temp_leaves_final_name_absent(tmp_path: Path) -> None:
    """故障点：私有临时件只写了一半时终止 ⇒ 最终名下不存在（旧实现留下半截 request.json）。"""
    ctx = make_ctx(tmp_path)
    AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"}).finish("validated", payload={})
    folder = ctx.run_dir / "agent_calls" / "N3" / "attempt-000002"
    folder.mkdir(parents=True)
    target = folder / "request.json"
    proc = _publish_fault_child(target, """
        real_fsync = os.fsync
        def fsync_half(fd):
            try:
                size = os.fstat(fd).st_size
                os.ftruncate(fd, max(1, size // 2))  # 半截内容真的落盘
            except OSError:
                pass
            real_fsync(fd)
            os._exit(9)  # 第一次同步（临时件）时终止，尚未发布
        os.fsync = fsync_half
        AM.seal_record(target, {"payload": "x" * 20000})
    """)
    assert proc.returncode == 9, proc.stderr
    # 最终名下只可能「不存在」或「完整」：半件只能存在于私有临时名中
    assert not target.exists() and not target.with_suffix(".sha256").exists()
    assert AM.record_state(target) == "absent"
    leftovers = sorted(p.name for p in folder.iterdir())
    assert leftovers, "半件必须留在私有临时件里，可作为诊断证据"
    for name in leftovers:
        assert not name.endswith(("request.json", "result.json", ".sha256")), name
    view = C.read_view(ctx.run_dir, "N3")
    assert [item["status"] for item in view["attempts"]] == ["validated", "incomplete"]
    assert view["selected_attempt"] == 1
    # 旧完整尝试仍可核验（半件只影响自己）
    earlier = ctx.run_dir / "agent_calls" / "N3" / "attempt-000001"
    assert AM.verify_attempt(earlier)["result"]["status"] == "validated"


def test_kill_after_checksum_publish_leaves_verifiable_record(tmp_path: Path) -> None:
    """故障点：两次发布都已完成、目录同步前终止 ⇒ 已发布件仍可核验（发布点之后只增不减）。"""
    ctx = make_ctx(tmp_path)
    AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"}).finish("validated", payload={})
    folder = ctx.run_dir / "agent_calls" / "N3" / "attempt-000002"
    folder.mkdir(parents=True)
    target = folder / "request.json"
    digest = target.with_suffix(".sha256")
    proc = _publish_fault_child(target, """
        real_link = os.link
        published = []
        def link_then_exit(src, dst, **kwargs):
            result = real_link(src, dst, **kwargs)
            published.append(str(dst))
            if len(published) == 2:
                os._exit(9)  # 校验和已原子发布；返回前终止
            return result
        os.link = link_then_exit
        AM.seal_record(target, {"prompt_key": "n3_digest", "input": {"x": 1},
                                "run_id": "RUN-F08-TEST", "node": "N3", "attempt": 2})
    """)
    assert proc.returncode == 9, (
        "旧实现没有不可覆盖的原子发布点（os.link 未被调用），无法在该故障点终止；stderr=" + proc.stderr)
    assert AM.record_state(target) == "committed"
    assert digest.read_text().strip() == hashlib.sha256(target.read_bytes()).hexdigest()
    view = C.read_view(ctx.run_dir, "N3")
    assert view["attempts"][-1]["status"] == "incomplete"  # 结果未写：只有请求
    assert view["request"]["prompt_key"] == "n3_digest" and view["result"] is None


def test_concurrent_seal_of_same_record_has_exactly_one_winner(tmp_path: Path) -> None:
    """竞争写同一编号：不可覆盖发布 ⇒ 恰好一个成功，失败者不覆盖已发布件。"""
    ctx = make_ctx(tmp_path)
    folder = ctx.run_dir / "agent_calls" / "N3" / "attempt-000001"
    folder.mkdir(parents=True)
    target = folder / "request.json"
    start = time.time() + 1.2
    script = f"""
        import os, sys, time
        sys.path.insert(0, {str(LOOP)!r})
        from pathlib import Path
        from host import agent_memory as AM
        payload = sys.argv[1]
        time.sleep(max(0.0, {start!r} - time.time()))
        AM.seal_record(Path({str(target)!r}), {{"prompt_key": "n3_digest", "payload": payload}})
    """
    procs = [subprocess.Popen([sys.executable, "-c", textwrap.dedent(script), payload],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
             for payload in ("A", "B")]
    outcomes = [(p.wait(timeout=60), p.stderr.read()) for p in procs]
    winners = [stderr for code, stderr in outcomes if code == 0]
    assert len(winners) == 1, outcomes
    assert "FileExistsError" in "".join(stderr for code, stderr in outcomes if code != 0)
    assert AM.record_state(target) == "committed"
    body = json.loads(target.read_bytes())
    assert body["payload"] in {"A", "B"}


def test_zero_byte_checksum_is_corrupt_not_incomplete(tmp_path: Path) -> None:
    """0 字节校验文件在旧协议下可由进程终止产生；新协议下不会再出现，但它仍是篡改信号，显式失败。"""
    ctx = make_ctx(tmp_path)
    attempt = AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"})
    attempt.finish("validated", payload={})
    digest = attempt.path / "request.sha256"
    os.chmod(digest, 0o600)
    digest.write_bytes(b"")
    assert AM.record_state(attempt.path / "request.json") == "corrupt"
    with pytest.raises(ValueError, match="checksum"):
        C.read_view(ctx.run_dir, "N3")


def test_sigkill_during_publish_loop_never_yields_consumable_partial(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    script = f"""
        import sys
        sys.path.insert(0, {str(LOOP)!r})
        from pathlib import Path
        from host import agent_memory as AM
        from host.progress import ProgressLog
        from services.contracts import KbSources
        from workflows.context import RunCtx
        root = Path({str(tmp_path)!r})
        run = root / "runs" / "RUN-F08-TEST"
        ctx = RunCtx(run.name, run, "standin", "happy", KbSources.from_workspace(root),
                     ProgressLog(root / "events", run.name))
        payload = "y" * 20000
        for _ in range(2000):
            attempt = AM.Attempt(ctx, "N6", {{"prompt_key": "n6_author", "input": {{"x": payload}}}})
            attempt.finish("validated", payload={{"revisions": []}})
    """
    child = subprocess.Popen([sys.executable, "-c", textwrap.dedent(script)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    time.sleep(0.35)
    child.send_signal(signal.SIGKILL)
    child.wait(timeout=10)

    view = C.read_view(ctx.run_dir, "N6")  # 不得整体抛错
    called = sorted(p.name for p in (ctx.run_dir / "agent_calls" / "N6").glob("attempt-*"))
    assert called, "样本必须至少写出一个尝试目录"
    states = [AM.record_state(ctx.run_dir / "agent_calls" / "N6" / name / "request.json")
              for name in called]
    assert set(states) <= {"absent", "incomplete", "corrupt", "committed"}
    for summary in view["attempts"]:
        if summary["status"] == "committed" or summary["status"] == "validated":
            assert summary["status"] == "validated", summary
    # 新尝试只增不复用
    fresh = AM.Attempt(ctx, "N6", {"prompt_key": "n6_author"})
    assert fresh.path.name == f"attempt-{len(called) + 1:06d}"


def test_corrupt_checksum_is_diagnosed_not_consumed(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    attempt = AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"})
    attempt.finish("validated", payload={})
    digest = attempt.path / "request.sha256"
    os.chmod(digest, 0o600)
    digest.write_text("0" * 64, encoding="utf-8")
    assert AM.record_state(attempt.path / "request.json") == "corrupt"
    with pytest.raises(ValueError, match="checksum|corrupt"):
        AM.verify_attempt(attempt.path)
    # 篡改是显式失败（保持既有安全契约），不是被当成有效记录消费
    with pytest.raises(ValueError, match="checksum"):
        C.read_view(ctx.run_dir, "N3")


def test_empty_attempt_dir_is_reported_incomplete(tmp_path: Path) -> None:
    """观测矩阵：建目录后、写数据前被终止 ⇒ 摘要 incomplete（目录存在即是证据）。"""
    ctx = make_ctx(tmp_path)
    (ctx.run_dir / "agent_calls" / "N3" / "attempt-000001").mkdir(parents=True)
    view = C.read_view(ctx.run_dir, "N3")
    assert view["attempts"][0]["status"] == "incomplete"
    assert view["selected_attempt"] is None


def test_symlinked_record_is_explicit_failure(tmp_path: Path) -> None:
    """复核 M1：符号链接必须在读状态前显式失败，不能静默变成 incomplete。"""
    ctx = make_ctx(tmp_path)
    attempt = AM.Attempt(ctx, "N3", {"prompt_key": "n3_digest"})
    attempt.finish("validated", payload={})
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    request_file = attempt.path / "request.json"
    request_file.chmod(0o600)
    request_file.unlink()
    request_file.symlink_to(outside)
    with pytest.raises(ValueError, match="符号链接|越界"):
        AM.record_state(request_file)
    with pytest.raises(ValueError, match="符号链接|越界"):
        C.read_view(ctx.run_dir, "N3")
    with pytest.raises(ValueError, match="符号链接|越界"):
        AM.verify_attempt(attempt.path)


def test_public_seal_api_used_by_control_module() -> None:
    assert hasattr(AM, "seal_record"), "封存写入必须有公开接口"
    source = (LOOP / "host" / "agent_control.py").read_text(encoding="utf-8")
    assert "AM._sealed" not in source, "跨模块不得直接调用私有 _sealed"
    assert "AM.seal_record" in source
