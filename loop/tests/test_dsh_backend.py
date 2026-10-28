"""S1：DSH 后端骨架（配置锁定 + 编排；默认不可用）。"""
from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from host.agent_backends import BackendConfigurationError, BackendUnavailable
from host.agent_backends import dsh as D
from host.agent_backends.base import BackendRequest

STUB = '''#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("STUB_MODE", "ok")
def emit(o): sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
emit({"type": "session", "sessionId": "s-stub", "cwd": os.getcwd()})
if mode == "refuse":
    emit({"type": "status", "phase": "turn_end",
          "reason": {"kind": "error", "error": {"code": "MISSING_CREDENTIAL", "message": "bad sk-SECRET"}}})
    emit({"type": "final", "text": ""})
else:
    emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
    emit({"type": "final", "text": "OK"})
    emit({"type": "status", "phase": "step_end", "usage": {"inputTokens": 3}})
'''


STUB_REFUSE = STUB.replace('mode = os.environ.get("STUB_MODE", "ok")', 'mode = "refuse"')


def _stub(tmp_path: Path, body: str = STUB) -> Path:
    p = tmp_path / ("dsh_stub_%d.py" % abs(hash(body)))
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


def _config(tmp_path: Path, stub: Path, **over) -> D.DshConfig:
    base = dict(enabled=True, version="0.2.1-rc.2", node=Path(__import__("sys").executable),
                bin=stub, bin_sha256=hashlib.sha256(stub.read_bytes()).hexdigest(),
                timeout_s=30.0, wrap=False)
    base.update(over)
    return D.DshConfig(**base)


def _request() -> BackendRequest:
    return BackendRequest(input_data={"a": 1}, info="i", instruct="do", schema={"type": "object"})


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    cwd = tmp_path / "attempt" / "work"; home = tmp_path / "attempt" / "home"
    cwd.mkdir(parents=True); home.mkdir(parents=True)
    return cwd, home


def test_disabled_is_unavailable(tmp_path: Path) -> None:
    stub = _stub(tmp_path)
    with pytest.raises(BackendUnavailable):
        D.DshBackend(_config(tmp_path, stub, enabled=False))


def test_fingerprint_mismatch_is_unavailable(tmp_path: Path) -> None:
    stub = _stub(tmp_path)
    with pytest.raises(BackendUnavailable):
        D.DshBackend(_config(tmp_path, stub, bin_sha256="0" * 64))


def test_unknown_config_key_rejected(tmp_path: Path) -> None:
    doc = {"loop": {"agent_runtime": {"dsh": {"enabled": True, "version": "x",
                                              "node": "/n", "bin": "/b", "bin_sha256": "0" * 64,
                                              "mystery": 1}}}}
    with pytest.raises(BackendConfigurationError):
        D.config_from_settings(doc)


async def test_execute_without_submission_is_explicit_failure(tmp_path: Path) -> None:
    """S2（B1/B5）：`turn_end(completed)` 但**没有** `submit_result` 提交 ⇒ 不得出候选。

    S1 的 `text` 占位与 `note` 在 S2 已删除（结构化候选只走提交工具）；成功路径见
    `tests/test_dsh_candidate.py`（stub 真发 tool_call/tool_result）。
    """
    stub = _stub(tmp_path); cwd, home = _dirs(tmp_path)
    backend = D.DshBackend(_config(tmp_path, stub), diagnostic_unwrapped=True)
    payload = await backend.execute(_request(), attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "submit_result" in payload["error"]
    assert "text" not in payload and "note" not in payload


async def test_execute_requires_explicit_dirs(tmp_path: Path) -> None:
    stub = _stub(tmp_path)
    backend = D.DshBackend(_config(tmp_path, stub), diagnostic_unwrapped=True)
    with pytest.raises(BackendConfigurationError):
        await backend.execute(_request())


async def test_execute_failure_is_explicit_and_redacted(tmp_path: Path, monkeypatch) -> None:
    stub = _stub(tmp_path, STUB_REFUSE); cwd, home = _dirs(tmp_path)
    monkeypatch.setenv("PUBLIC_API_KEY", "sk-SECRET")
    backend = D.DshBackend(_config(tmp_path, stub), diagnostic_unwrapped=True)
    payload = await backend.execute(_request(), attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "sk-SECRET" not in payload["error"]
    assert "[redacted]" in payload["error"]


def test_shipped_settings_do_not_bypass_admission() -> None:
    """仓内 SETTINGS 的 dsh 段**不因实现存在而放行**（原"必须默认关闭"的旧假设已随人工裁决更新）。

    判据分两半，都不依赖"配置里是否写了 enabled"：
    1. 配置可解析 + 生产路径 `verify(wrap_required=True)` 通过（指纹/版本/包裹齐备才算锁住）；
    2. **`run_mode` 未声明时 `select()` 仍 `BackendUnavailable`**（旧/未知调用不得默认当 real，
       也不得因为配置里启用了 dsh 就偷偷用起来）；
    3. `enabled=False` 时 `DshBackend` 必抛（用 tmp 配置造，不依赖仓内取值）。
    """
    from host import agent_backends as B

    cfg = D.config_from_settings()
    cfg.verify(wrap_required=True)
    with pytest.raises(BackendUnavailable):
        B.select("N3")
    with pytest.raises(BackendUnavailable):
        D.DshBackend(dataclasses.replace(cfg, enabled=False))


def test_shipped_pin_matches_actual_binary_when_present() -> None:
    """指纹钉与实际安装一致；安装变了这条会红（提示重新录制 manifest）。"""
    cfg = D.config_from_settings()
    if not cfg.bin.is_file():
        pytest.skip("本机没有该 DSH 安装（CI/异机）——指纹比对不适用")
    actual = hashlib.sha256(cfg.bin.read_bytes()).hexdigest()
    assert actual == cfg.bin_sha256, "dsh bin 指纹漂移：请按 P0 重新录制 manifest 并更新 SETTINGS/REV"


def test_wrap_off_cannot_enable_backend_from_config(tmp_path: Path) -> None:
    """独立复核 P1-2：配置里 `wrap:false` 不能静默关掉 DS-08/09/10 准入。

    生产路径（`config_from_settings` → `verify()`）要求 `wrap=true`；只有代码里显式
    `diagnostic_unwrapped=True` 的诊断/单测路径才允许无包裹，且候选会标 `unwrapped-diagnostic`。
    """
    stub = _stub(tmp_path)
    cfg = _config(tmp_path, stub)          # wrap=False（_config 默认给测试省 bwrap）
    with pytest.raises(BackendConfigurationError, match="wrap=true"):
        D.DshBackend(cfg)
    # 诊断开关与 wrap=true 互斥（不许两边都声明）
    with pytest.raises(BackendConfigurationError, match="矛盾"):
        D.DshBackend(_config(tmp_path, stub, wrap=True), diagnostic_unwrapped=True)


STUB_SUBMIT = '''#!/usr/bin/env python3
import json, os, sys
def emit(o): sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
emit({"type": "session", "sessionId": "s-stub", "cwd": os.getcwd()})
emit({"type": "tool_call", "callId": "c1", "tool": "submit_result",
      "input": {"task_id": "RUN-TEST/N6/1", "summary": "一句话", "payload": {"verdict": "pass"}}})
emit({"type": "tool_result", "callId": "c1", "status": "completed",
      "result": json.dumps({"accepted": True, "problems": []})})
emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
emit({"type": "final", "text": "OK"})
emit({"type": "status", "phase": "step_end", "usage": {"inputTokens": 3}})
'''


async def test_diagnostic_payload_is_marked_unwrapped(tmp_path: Path) -> None:
    """诊断模式必须自曝身份：`isolation` 不能冒充 bwrap。"""
    stub = _stub(tmp_path, STUB_SUBMIT)
    cwd, home = _dirs(tmp_path)
    backend = D.DshBackend(_config(tmp_path, stub), diagnostic_unwrapped=True)
    payload = await backend.execute(_request(), attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home)
    assert "model_call_failed" not in payload, payload.get("error")
    assert payload["data"] == {"verdict": "pass"}
    assert payload["isolation"] == "unwrapped-diagnostic"
    assert "selfcheck" not in payload, "无包裹就没有运行时自检事实，不得伪造"
