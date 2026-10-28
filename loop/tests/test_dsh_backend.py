"""S1：DSH 后端骨架（配置锁定 + 编排；默认不可用）。"""
from __future__ import annotations

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


async def test_execute_ok_returns_text_and_usage(tmp_path: Path) -> None:
    stub = _stub(tmp_path); cwd, home = _dirs(tmp_path)
    backend = D.DshBackend(_config(tmp_path, stub))
    payload = await backend.execute(_request(), attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home)
    assert payload["standin"] is False
    assert payload["text"] == "OK" and payload["usage"] == {"inputTokens": 3}
    assert payload["note"].startswith("S1 骨架")


async def test_execute_requires_explicit_dirs(tmp_path: Path) -> None:
    stub = _stub(tmp_path)
    backend = D.DshBackend(_config(tmp_path, stub))
    with pytest.raises(BackendConfigurationError):
        await backend.execute(_request())


async def test_execute_failure_is_explicit_and_redacted(tmp_path: Path, monkeypatch) -> None:
    stub = _stub(tmp_path, STUB_REFUSE); cwd, home = _dirs(tmp_path)
    monkeypatch.setenv("PUBLIC_API_KEY", "sk-SECRET")
    backend = D.DshBackend(_config(tmp_path, stub))
    payload = await backend.execute(_request(), attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "sk-SECRET" not in payload["error"]
    assert "[redacted]" in payload["error"]


def test_shipped_settings_are_disabled_by_default() -> None:
    """仓内 SETTINGS 的 dsh 段必须默认关闭（不因实现存在而放行）。"""
    cfg = D.config_from_settings()
    assert cfg.enabled is False
    with pytest.raises(BackendUnavailable):
        D.DshBackend(cfg)


def test_shipped_pin_matches_actual_binary_when_present() -> None:
    """指纹钉与实际安装一致；安装变了这条会红（提示重新录制 manifest）。"""
    cfg = D.config_from_settings()
    if not cfg.bin.is_file():
        pytest.skip("本机没有该 DSH 安装（CI/异机）——指纹比对不适用")
    actual = hashlib.sha256(cfg.bin.read_bytes()).hexdigest()
    assert actual == cfg.bin_sha256, "dsh bin 指纹漂移：请按 P0 重新录制 manifest 并更新 SETTINGS/REV"
