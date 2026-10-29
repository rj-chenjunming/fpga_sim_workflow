"""S1：DSH 后端骨架（配置锁定 + 编排；默认不可用）。"""
from __future__ import annotations

import dataclasses
import hashlib
import json
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

# ================================================================== S8b：随 attempt 自动起 Web 实例
# 契约（REV-14 §3-D3 / §9.3；裁决 B3）：
#   ① `mode=real` 且 `dsh.web.enabled=true` ⇒ attempt 装配点自动 `web_instance_ctl.ensure(...)`；
#   ② 起失败**绝不阻断** attempt（Web 只是观测面）⇒ 记录里落"不可内嵌 + 原因"；
#   ③ `agent_instance.json` 按当前 `(node, attempt)` 重写（落账由 `ensure` 做；见 test_web_instance_ctl）；
#   ④ attempt 结束**不 stop**（人还要看）。

def _web_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *,
                 failure: BaseException | None = None):
    """把 `web_instance_ctl.ensure` 换成记录桩；返回 (run_dir, stub, calls, backend)。"""
    import host.web_instance_ctl as WC

    stub = _stub(tmp_path, STUB_SUBMIT)
    # 目录名与 stub 的 `task_id`（RUN-TEST/N6/1）对齐：提交门的身份 join 用的是派生出的 attempt_key
    run_dir = tmp_path / "runs" / "RUN-TEST"
    run_dir.mkdir(parents=True)
    calls: list[tuple] = []

    def fake_ensure(run_dir_arg, node, attempt, **kwargs):
        calls.append((Path(run_dir_arg), node, int(attempt), kwargs))
        if failure is not None:
            raise failure
        return {"node": node, "attempt": int(attempt), "host": "127.0.0.1",
                "port": 18777, "reused": False, "startup_s": 3.1}

    monkeypatch.setattr(WC, "ensure", fake_ensure)
    # `diagnostic_unwrapped`：本组只验装配点接线，不真跑 bwrap/自检（参数形状与 web 无关）
    return run_dir, stub, calls, D.DshBackend(_config(tmp_path, stub), diagnostic_unwrapped=True)


def test_real_attempt_auto_starts_web_instance_and_records_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`mode=real` ⇒ 装配点真的调 `ensure(run_dir, node, attempt)`，记录里 `embed=iframe`。"""
    import host.agent_backends as B

    run_dir, _stub_path, calls, backend = _web_attempt(tmp_path, monkeypatch)
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    assert [(item[0], item[1], item[2]) for item in calls] == [(run_dir, "N6", 1)]
    web = workspace.record(run_dir=run_dir)["web"]
    assert web["state"] == "ready" and web["embed"] == "iframe"
    assert (web["node"], web["attempt"], web["port"]) == ("N6", 1, 18777)
    assert "token" not in json.dumps(web), "装配记录不得回显 token"


def test_web_metadata_follows_the_current_attempt(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """换 attempt ⇒ `ensure` 收到的是**当前** `(node, attempt)`（落账由它按当前元组重写）。"""
    import host.agent_backends as B

    run_dir, _stub_path, calls, backend = _web_attempt(tmp_path, monkeypatch)
    with B.run_mode("real"):
        backend.prepare_attempt(run_dir, "N6", 1)
        second = backend.prepare_attempt(run_dir, "N6", 2)
    assert [item[2] for item in calls] == [1, 2]
    assert second.record(run_dir=run_dir)["web"]["attempt"] == 2


def test_web_instance_is_not_started_outside_real_mode(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 `real`（drill / 未声明）⇒ 一次都不起：drill 与单测不许多一个 loopback 子进程。"""
    import host.agent_backends as B

    run_dir, _stub_path, calls, backend = _web_attempt(tmp_path, monkeypatch)
    backend.prepare_attempt(run_dir, "N6", 1)                  # 未声明 run_mode
    with B.run_mode("drill"):
        drill = backend.prepare_attempt(run_dir, "N6", 2)
    assert calls == []
    web = drill.record(run_dir=run_dir)["web"]
    assert (web["state"], web["reason"]) == ("disabled", "run_mode_not_real")


def test_web_disabled_config_records_disabled_and_never_blocks(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`web.enabled=false`（回退档）⇒ `ensure` 抛 `web_disabled`；attempt 照常装配。"""
    import host.web_instance_ctl as WC
    import host.agent_backends as B

    run_dir, _stub_path, _calls, backend = _web_attempt(
        tmp_path, monkeypatch, failure=WC.WebCtlError("web_disabled", "dsh.web.enabled=false"))
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    web = workspace.record(run_dir=run_dir)["web"]
    assert (web["state"], web["reason"], web["embed"]) == (
        "disabled", "web_disabled", "new_tab_only")


async def test_web_start_failure_does_not_block_the_attempt(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """起失败 ⇒ attempt 仍跑通并出候选（只有记录里多一条"不可内嵌 + 原因"）。"""
    import host.web_instance_ctl as WC
    import host.agent_backends as B

    run_dir, _stub_path, _calls, backend = _web_attempt(
        tmp_path, monkeypatch, failure=WC.WebCtlError("start_timeout", "30s 内没等到公告行"))
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    payload = await backend.execute(_request(), **workspace.execute_kwargs())
    assert payload.get("model_call_failed") is not True, payload.get("error")
    assert payload["data"] == {"verdict": "pass"}, "起失败不得打断 attempt"
    web = workspace.record(run_dir=run_dir)["web"]
    assert (web["state"], web["reason"], web["embed"]) == (
        "unavailable", "start_timeout", "new_tab_only")


async def test_unexpected_web_error_is_contained_and_named(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """非 `WebCtlError` 的异常同样被收住（记 `web_start_failed` + 异常类名，不回显消息）。"""
    import host.agent_backends as B

    run_dir, _stub_path, _calls, backend = _web_attempt(
        tmp_path, monkeypatch, failure=RuntimeError("secret-ish boom"))
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    web = workspace.record(run_dir=run_dir)["web"]
    assert (web["state"], web["reason"]) == ("unavailable", "web_start_failed")
    assert web["detail"] == "RuntimeError"
    assert "boom" not in json.dumps(web), "不回显异常消息（可能带秘密）"


async def test_attempt_end_does_not_stop_the_web_instance(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """attempt 结束**不 stop**（人还要看）：整条 execute 路径一次 `stop` 都不许发。"""
    import host.web_instance_ctl as WC
    import host.agent_backends as B

    run_dir, _stub_path, _calls, backend = _web_attempt(tmp_path, monkeypatch)
    stops: list[tuple] = []
    monkeypatch.setattr(WC, "stop", lambda *a, **k: stops.append((a, k)))
    monkeypatch.setattr(WC, "stop_all", lambda *a, **k: stops.append((a, k)))
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    payload = await backend.execute(_request(), **workspace.execute_kwargs())
    assert payload["data"] == {"verdict": "pass"}
    assert stops == [], "attempt 结束不得停实例（人还要在 GUI 里看/说话）"


def test_ds09_rejection_happens_before_the_web_instance_starts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """顺序契约（复核 P1）：home 已含宿主件 ⇒ **起实例之前**就拒（不起进程、不写落账）。

    为什么这是硬要求：起 Web 实例会让一个 dsh 进程去**读这个 home**；若"先读了再拒"，
    REV-14 §9.3 的隔离意图与 AGENTS §2「拒绝发生在提交前」都已被破坏。
    """
    from host.agent_backends import dsh_assets as A
    from services import instance_proxy as IP
    import host.agent_backends as B

    run_dir, _stub_path, calls, backend = _web_attempt(tmp_path, monkeypatch)
    layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
    layout.prepare()
    (layout.home / "settings.yaml").write_text("llm-pi-ai: {}\\n", encoding="utf-8")
    with B.run_mode("real"):
        with pytest.raises(A.AssetError) as info:
            backend.prepare_attempt(run_dir, "N6", 1)
    assert "settings.yaml" in str(info.value)
    assert calls == [], "DS-09 拒绝必须发生在起 Web 实例之前"
    assert not (run_dir / IP.METADATA_NAME).exists(), "拒了就不许留指向死端口的落账"


def test_dsh_generated_home_passes_the_gate_and_then_starts_the_instance(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """共用 home 的落地形态：home 里已有 dsh 自生成件 ⇒ 判 `dsh_generated` 放行 ⇒ 正常起实例。"""
    from host.agent_backends import dsh_assets as A
    import host.agent_backends as B

    run_dir, _stub_path, calls, backend = _web_attempt(tmp_path, monkeypatch)
    layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
    layout.prepare()
    (layout.home / ".credentials.yaml").write_text(
        "version: 1\nrecords:\n  client-connection/browser-session:\n    kind: grant\n"
        "    payload:\n      version: 1\n      secret: fake-secret-0123456789abcdef\n",
        encoding="utf-8")
    with B.run_mode("real"):
        workspace = backend.prepare_attempt(run_dir, "N6", 1)
    assert len(calls) == 1, "自生成件不得挡住共用 home 的第二次 attempt"
    record = workspace.record(run_dir=run_dir)
    assert record["web"]["state"] == "ready"
    assert [item["source"] for item in record["home_provenance"]] == ["dsh_generated"]
