"""F08：封存发布边界的进程终止注入与恢复诊断。

观察矩阵见 `doc/spec/AGENT_CONTEXT_SPEC.md`「封存与恢复」：
- `absent / incomplete / corrupt / committed` 由 `AM.record_state` 只读判定；
- 半写记录（数据在、校验缺）不得被消费；其它尝试照常可读；
- 故障注入用**真实子进程终止**（`os._exit` / `SIGKILL`），不是内存变量模拟。

边界：本文件证明记录层状态与读取容错；不证明持久暂停/续跑（F09），也不证明真实 provider 行为。
"""
from __future__ import annotations

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


def test_process_exit_between_data_and_checksum_is_incomplete_and_not_consumed(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    folder = ctx.run_dir / "agent_calls" / "N3" / "attempt-000001"
    folder.mkdir(parents=True)
    target = folder / "request.json"
    proc = run_child(f"""
        import os, sys
        sys.path.insert(0, {str(LOOP)!r})
        from pathlib import Path
        from host import agent_memory as AM
        AM._write_once(Path({str(target)!r}), b'{{"partial": true}}')
        os._exit(9)
    """)
    assert proc.returncode == 9, proc.stderr
    assert target.is_file() and not target.with_suffix(".sha256").is_file()
    assert AM.record_state(target) == "incomplete"
    with pytest.raises(ValueError, match="incomplete"):
        AM.verify_attempt(folder)
    # 读取视图不得整体抛错：该尝试标 incomplete，且不进入可消费记录
    view = C.read_view(ctx.run_dir, "N3")
    assert view["attempts"][0]["status"] == "incomplete"
    assert view["selected_attempt"] is None
    assert view["request"] is None and view["result"] is None


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
