"""S2-a：结构化候选（`submit_result` 收口；SPEC-REV-14 B1/B5 · DS-02）。

不烧模型、不联网：协议用内存帧单测，进程用 python stub 冒充 `dsh` CLI
（与 `tests/test_dsh_process.py` 同一写法：`wrap=False`，行为由 `STUB_MODE` 选）。

判据（不读实现也应成立）：
- `completed` **且**恰一条被接受提交 ⇒ 候选 `data` 就是被提交的 payload，
  且**没有** `text`/`note` 占位（S1 占位必须删除）；
- 无提交 / 提交被拒 / 两条不同提交 / task_id 与 attempt_key 不符 / 调用无结果 /
  坏 result JSON / payload 非对象 ⇒ 显式失败（`model_call_failed=True` + error），
  不得把"没提交"包装成成功；
- `turn_end=error` 即使已提交 ⇒ 失败（完成判据 = 终态 + 提交两者都满足，B5）；
- 协议层默认（`require_submission=False`）保持 S1 语义：无提交不抛 —— 这是
  `tests/test_dsh_process.py` 既有用例的前提，本片不得改变它。
"""
from __future__ import annotations

import dataclasses
import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

from host.agent_backends import BackendConfigurationError
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_protocol as DPR
from host.agent_backends.base import BackendRequest

ATTEMPT_KEY = "RUN-TEST/N6/1"

#: stub 冒充 dsh CLI：只吐 NDJSON（协议面），行为由 STUB_MODE 选，噪声可复现。
STUB = '''#!/usr/bin/env python3
import json, os, sys
mode = os.environ.get("STUB_MODE", "ok")
TASK_ID = os.environ.get("STUB_TASK_ID", "RUN-TEST/N6/1")
SUMMARY = "一句话结论"
PAYLOAD = {"verdict": "pass", "problems": []}

def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n")
    sys.stdout.flush()

def submit(task_id=None, payload=None, call_id="call-1", accepted=True,
           status="completed", result=None, with_result=True):
    emit({"type": "tool_call", "callId": call_id, "tool": "submit_result",
          "input": {"task_id": TASK_ID if task_id is None else task_id,
                    "summary": SUMMARY,
                    "payload": PAYLOAD if payload is None else payload}})
    if not with_result:
        return
    if result is None:
        result = json.dumps({"accepted": accepted,
                             "problems": [] if accepted else ["engine rejected"]})
    emit({"type": "tool_result", "callId": call_id, "status": status, "result": result})

def terminal(kind="completed"):
    if kind == "completed":
        emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
        emit({"type": "final", "text": "DONE"})
        emit({"type": "status", "phase": "step_end", "usage": {"inputTokens": 11, "outputTokens": 3}})
    else:
        emit({"type": "status", "phase": "turn_end",
              "reason": {"kind": "error",
                         "error": {"code": "MISSING_CREDENTIAL", "message": "no key sk-SECRET"}}})

emit({"type": "session", "sessionId": "session-stub", "cwd": os.getcwd()})
if mode == "ok":
    submit()
elif mode == "no_submission":
    pass
elif mode == "rejected":
    submit(accepted=False)
elif mode == "conflict":
    submit(call_id="call-1")
    submit(call_id="call-2", payload={"verdict": "fail"})
elif mode == "wrong_task":
    submit(task_id="OTHER-RUN/N6/9")
elif mode == "missing_result":
    submit(with_result=False)
elif mode == "bad_json":
    submit(result="this is not json")
elif mode == "nonobject_payload":
    submit(payload=[1, 2, 3])
elif mode == "status_failed":
    submit(status="failed")
elif mode == "error_after_submit":
    submit()
    terminal("error")
elif mode == "dup_call_id":
    submit(call_id="call-1")
    submit(call_id="call-1")
else:
    raise SystemExit("unknown STUB_MODE: " + mode)
if mode != "error_after_submit":
    terminal()
'''


# ---------------------------------------------------------------- 夹具

def _stub(tmp_path: Path) -> Path:
    path = tmp_path / "dsh_candidate_stub.py"
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    return path


def _config(stub: Path, *, patches: tuple[Path, ...] = ()) -> D.DshConfig:
    return D.DshConfig(
        enabled=True, version="0.2.1-rc.2", node=Path(sys.executable), bin=stub,
        bin_sha256=hashlib.sha256(stub.read_bytes()).hexdigest(),
        timeout_s=30.0, wrap=False, patches=patches)


def _attempt(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "attempt"
    cwd, home = root / "work", root / "dsh-home"
    cwd.mkdir(parents=True)
    home.mkdir(parents=True)
    return root, cwd, home


def _backend(tmp_path: Path, *, mode: str = "ok",
             patches: tuple[Path, ...] = (), captured: dict[str, Any] | None = None) -> D.DshBackend:
    """后端 + 唯一测试接缝：把 `STUB_MODE` 并进 `env_extra`（stub 靠它选行为）。

    只改 env，不改被测代码路径：`_spec` 的产物（patches/env_extra/资产）仍走实现。
    """
    backend = D.DshBackend(_config(_stub(tmp_path), patches=patches),
                          diagnostic_unwrapped=True)
    original = backend._spec

    def _spec_with_mode(request: BackendRequest, *, attempt_key: str, cwd: Path,
                        home: Path) -> Any:
        spec = original(request, attempt_key=attempt_key, cwd=cwd, home=home)
        if captured is not None:
            captured["spec"] = spec
        return dataclasses.replace(
            spec, env_extra={**spec.env_extra, "STUB_MODE": mode})

    backend._spec = _spec_with_mode  # type: ignore[method-assign]
    return backend


def _request() -> BackendRequest:
    return BackendRequest(input_data={"diff": "…"}, info="info",
                          instruct="做静态复核", schema={"type": "object",
                                                         "required": ["verdict"]})


async def _run(tmp_path: Path, mode: str, *, patches: tuple[Path, ...] = (),
               captured: dict[str, Any] | None = None) -> dict[str, Any]:
    _root, cwd, home = _attempt(tmp_path)
    backend = _backend(tmp_path, mode=mode, patches=patches, captured=captured)
    return await backend.execute(_request(), attempt_key=ATTEMPT_KEY, cwd=cwd, home=home)


# ---------------------------------------------------------------- 协议层（纯函数）

def _frames(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"type": "session", "sessionId": "session-stub", "cwd": "/w"}, *extra]


def _call(call_id: str = "call-1", *, task_id: str = ATTEMPT_KEY,
          payload: Any = None, summary: str = "一句话结论") -> dict[str, Any]:
    return {"type": "tool_call", "callId": call_id, "tool": "submit_result",
            "input": {"task_id": task_id, "summary": summary,
                      "payload": {"verdict": "pass"} if payload is None else payload}}


def _result(call_id: str = "call-1", *, accepted: Any = True,
            status: str = "completed", result: Any = None) -> dict[str, Any]:
    if result is None:
        result = '{"accepted": true, "problems": []}' if accepted is True else \
                 '{"accepted": false, "problems": ["engine rejected"]}'
    return {"type": "tool_result", "callId": call_id, "status": status, "result": result}


_COMPLETED = {"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}}


def _gate(*extra: dict[str, Any], expect_task_id: str | None = ATTEMPT_KEY) -> DPR.Submission:
    """折叠帧 + 过提交门（顺序与 dsh.py 一致：先 `fold` 收集，再 `require_submission` 判定）。"""
    return DPR.require_submission(DPR.fold(_frames(*extra)), expect_task_id=expect_task_id)


def test_protocol_fold_collects_submission_calls() -> None:
    out = DPR.fold(_frames(_call(), _result(), _COMPLETED))
    assert out.status == "completed"
    (call,) = out.submission_calls
    assert call.call_id == "call-1" and call.input["task_id"] == ATTEMPT_KEY
    assert len(call.results) == 1 and call.results[0]["status"] == "completed"


def test_protocol_gate_returns_single_accepted_submission() -> None:
    sub = _gate(_call(), _result(), _COMPLETED)
    assert sub.task_id == ATTEMPT_KEY and sub.summary == "一句话结论"
    assert sub.payload == {"verdict": "pass"}
    assert sub.call_id == "call-1" and sub.accepted is True and sub.problems == ()


def test_protocol_fold_default_keeps_s1_semantics_without_submission() -> None:
    """fold 只**收集**、不判提交：S1 的"无提交也 completed"语义必须继续成立。"""
    out = DPR.fold(_frames(_COMPLETED))
    assert out.status == "completed" and out.submission_calls == ()


def test_protocol_gate_no_submission_is_explicit_failure() -> None:
    with pytest.raises(DPR.NoSubmission, match="submit_result"):
        _gate(_COMPLETED)


def test_protocol_gate_rejected_submission_is_no_submission() -> None:
    with pytest.raises(DPR.NoSubmission, match="rejected|拒绝"):
        _gate(_call(), _result(accepted=False), _COMPLETED)


def test_protocol_gate_rejected_submission_keeps_problems_in_error() -> None:
    """被拒提交的诊断（problems）必须出现在错误里，便于审计；不得静默。"""
    with pytest.raises(DPR.NoSubmission, match="engine rejected"):
        _gate(_call(), _result(accepted=False), _COMPLETED)


def test_protocol_gate_conflicting_submissions_rejected() -> None:
    with pytest.raises(DPR.ConflictingSubmissions):
        _gate(_call(call_id="call-1"), _result(call_id="call-1"),
              _call(call_id="call-2", payload={"verdict": "fail"}),
              _result(call_id="call-2"), _COMPLETED)


def test_protocol_gate_duplicate_call_id_rejected() -> None:
    with pytest.raises(DPR.ConflictingSubmissions):
        _gate(_call(call_id="call-1"), _result(call_id="call-1"),
              _call(call_id="call-1"), _result(call_id="call-1"), _COMPLETED)


def test_protocol_gate_tool_call_without_result_rejected() -> None:
    with pytest.raises(DPR.BadSubmission, match="tool_result"):
        _gate(_call(), _COMPLETED)


def test_protocol_gate_result_not_json_rejected() -> None:
    with pytest.raises(DPR.BadSubmission, match="JSON|json"):
        _gate(_call(), _result(result="not json"), _COMPLETED)


def test_protocol_gate_result_missing_accepted_field_rejected() -> None:
    with pytest.raises(DPR.BadSubmission, match="accepted"):
        _gate(_call(), _result(result='{"problems": []}'), _COMPLETED)


def test_protocol_gate_tool_result_status_not_completed_rejected() -> None:
    with pytest.raises(DPR.BadSubmission, match="completed|status"):
        _gate(_call(), _result(status="failed"), _COMPLETED)


def test_protocol_gate_payload_must_be_object() -> None:
    with pytest.raises(DPR.BadSubmission, match="payload"):
        _gate(_call(payload=[1, 2, 3]), _result(), _COMPLETED)


def test_protocol_gate_missing_call_id_rejected() -> None:
    call = _call()
    call.pop("callId")
    with pytest.raises(DPR.BadSubmission, match="callId"):
        _gate(call, _result(), _COMPLETED)


def test_protocol_gate_call_id_mismatch_rejected() -> None:
    """提交调用的 callId 与结果对不上 ⇒ 调用没有结果 ⇒ 显式失败（不得猜）。"""
    with pytest.raises(DPR.BadSubmission, match="tool_result"):
        _gate(_call(call_id="call-1"), _result(call_id="call-9"), _COMPLETED)


def test_protocol_gate_ignores_other_tools() -> None:
    """其它工具的 call/tool_result 不参与提交判定（只认 submit_result）。"""
    other_call = {"type": "tool_call", "callId": "bash-1", "tool": "bash", "input": {}}
    other_result = {"type": "tool_result", "callId": "bash-1",
                    "status": "completed", "result": "fine"}
    sub = _gate(_call(), _result(), other_call, other_result, _COMPLETED)
    assert sub.call_id == "call-1"


def test_protocol_gate_task_id_mismatch_is_identity_failure() -> None:
    frames = _frames(_call(task_id="OTHER/N6/9"), _result(), _COMPLETED)
    with pytest.raises(DPR.IdentityMismatch, match="task_id"):
        DPR.require_submission(DPR.fold(frames), expect_task_id=ATTEMPT_KEY)
    # 未声明 expect_task_id 时门不做身份 join（身份比较需要 attempt 上下文）
    sub = DPR.require_submission(DPR.fold(frames))
    assert sub.task_id == "OTHER/N6/9"


def test_protocol_gate_rejects_non_completed_terminal() -> None:
    """提交门只对 completed 生效；失败终态不得被当成"已收口"。"""
    out = DPR.fold(_frames({"type": "status", "phase": "turn_end",
                            "reason": {"kind": "error", "error": {"code": "X"}}}))
    with pytest.raises(DPR.ProtocolError):
        DPR.require_submission(out)


# ---------------------------------------------------------------- 后端 + stub CLI

async def test_execute_completed_with_submission_returns_payload(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    payload = await _run(tmp_path, "ok", captured=captured)
    assert payload["standin"] is False and payload["plugin"] == "dsh"
    assert payload["provider"] == "dsh/0.2.1-rc.2"
    assert payload["data"] == {"verdict": "pass", "problems": []}   # data 就是提交的 payload
    assert payload["task_id"] == ATTEMPT_KEY and payload["summary"] == "一句话结论"
    assert payload["session_id"] == "session-stub"
    assert payload["usage"] == {"inputTokens": 11, "outputTokens": 3}
    # S1 占位必须删除：不得有 text / note
    assert "text" not in payload and "note" not in payload
    assert "model_call_failed" not in payload


async def test_execute_without_submission_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "no_submission")
    assert payload["model_call_failed"] is True
    assert "submit_result" in payload["error"] and "data" not in payload
    assert "text" not in payload and "note" not in payload


async def test_execute_rejected_submission_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "rejected")
    assert payload["model_call_failed"] is True
    assert "submit_result" in payload["error"] and "data" not in payload


async def test_execute_conflicting_submissions_fail(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "conflict")
    assert payload["model_call_failed"] is True and "data" not in payload


async def test_execute_duplicate_call_id_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "dup_call_id")
    assert payload["model_call_failed"] is True and "data" not in payload


async def test_execute_task_id_mismatch_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "wrong_task")
    assert payload["model_call_failed"] is True and "data" not in payload
    assert "task_id" in payload["error"]
    assert ATTEMPT_KEY in payload["error"] or "identity" in payload["error"].lower()


async def test_execute_tool_call_without_result_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "missing_result")
    assert payload["model_call_failed"] is True and "data" not in payload


async def test_execute_bad_result_json_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "bad_json")
    assert payload["model_call_failed"] is True and "data" not in payload


async def test_execute_payload_not_object_fails(tmp_path: Path) -> None:
    payload = await _run(tmp_path, "nonobject_payload")
    assert payload["model_call_failed"] is True and "data" not in payload


async def test_execute_error_turn_after_submission_fails(tmp_path: Path, monkeypatch) -> None:
    """终态是 error：即使已提交也不得返回候选（B5：终态 + 提交缺一不可）。"""
    monkeypatch.setenv("PUBLIC_API_KEY", "sk-SECRET")
    payload = await _run(tmp_path, "error_after_submit")
    assert payload["model_call_failed"] is True and "data" not in payload
    assert "MISSING_CREDENTIAL" in payload["error"]
    assert "sk-SECRET" not in payload["error"] and "[redacted]" in payload["error"]


# ---------------------------------------------------------------- attempt 资产（B1 挂载）

async def test_execute_materializes_plugin_and_selfcheck_dir(tmp_path: Path) -> None:
    root, cwd, home = _attempt(tmp_path)
    provider = tmp_path / "provider.yml"
    provider.write_text("- id: llm-deepseek\n  config: {}\n", encoding="utf-8")
    captured: dict[str, Any] = {}
    backend = _backend(tmp_path, mode="ok", patches=(provider,), captured=captured)
    await backend.execute(_request(), attempt_key=ATTEMPT_KEY, cwd=cwd, home=home)

    spec = captured["spec"]
    plugin = root / "plugin" / "submit_result.mjs"
    assert plugin.is_file(), "插件必须复制进 attempt 目录（包裹内仓内路径不可见）"
    assert (root / "plugin" / "selfcheck.mjs").is_file(), "自检插件也必须复制进 attempt 目录"
    assert spec.env_extra["DSH_SELFCHECK_DIR"] == str(root / "selfcheck")
    # 包裹内必须显式 bind attempt 资产（只读）与侧信道（可写），否则 dsh 读不到自己的 patch
    assert tuple(spec.asset_dirs) == (root / "plugin", root / "patches")
    assert tuple(spec.state_dirs) == (root / "selfcheck",)
    # patch 顺序（S2 契约）：B3 双钉 → config.patches → 提交插件 → 自检插件
    assert [Path(p).name for p in spec.patches] == [
        "00-pins.yml", "01-extra-provider.yml",
        "10-plugin-s2-submit-result.yml", "10-plugin-s2-selfcheck.yml"], \
        "patch 顺序：钉死在前，config.patches 居中，插件 insert 在后（自检插件排最后）"
    insert = Path(spec.patches[2]).read_text(encoding="utf-8")
    assert "- insert:" in insert and str(plugin) in insert
    assert str(A.PLUGIN_SOURCE_DIR) not in insert, "patch 必须指向 attempt 目录内的副本"


async def test_compose_task_names_tool_and_attempt_key(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    await _run(tmp_path, "ok", captured=captured)
    task = captured["spec"].task
    assert "submit_result" in task
    assert ATTEMPT_KEY in task, "task_id 必须逐字等于本次 attempt_key"
    assert "payload" in task and "summary" in task
    # schema 必须写进任务文本（结构化对象的要求来源）
    assert "verdict" in task


class _FakeSchema:
    """冒充 pydantic 模型类：`model_request.ask` 传下来的就是这个形态。"""

    @staticmethod
    def model_json_schema() -> dict[str, Any]:
        return {"type": "object", "properties": {"verdict": {"type": "string"}}}


async def test_compose_task_serializes_model_schema(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}
    _root, cwd, home = _attempt(tmp_path)
    backend = _backend(tmp_path, mode="ok", captured=captured)
    request = BackendRequest(input_data={}, info="i", instruct="do", schema=_FakeSchema())
    await backend.execute(request, attempt_key=ATTEMPT_KEY, cwd=cwd, home=home)
    assert '"verdict"' in captured["spec"].task


async def test_unserializable_schema_is_configuration_error(tmp_path: Path) -> None:
    """拿不到可序列化 schema ⇒ 显式配置错误（不得把类名糊进提示词）。"""
    _root, cwd, home = _attempt(tmp_path)
    backend = _backend(tmp_path, mode="ok")
    request = BackendRequest(input_data={}, info="i", instruct="do", schema=object())
    with pytest.raises(BackendConfigurationError, match="schema"):
        await backend.execute(request, attempt_key=ATTEMPT_KEY, cwd=cwd, home=home)


async def test_execute_missing_plugin_source_is_explicit_failure(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """缺插件源码 ⇒ 显式失败（不得静默跳过、更不得以"进程起来了"当成功）。"""
    empty = tmp_path / "empty_plugin_src"
    empty.mkdir()
    monkeypatch.setattr(A, "PLUGIN_SOURCE_DIR", empty)
    payload = await _run(tmp_path, "ok")
    assert payload["model_call_failed"] is True and "data" not in payload
    assert "submit_result.mjs" in payload["error"]


async def test_attempt_layout_mismatch_is_configuration_error(tmp_path: Path) -> None:
    _root, cwd, _home = _attempt(tmp_path)
    stray_home = tmp_path / "elsewhere" / "dsh-home"
    stray_home.mkdir(parents=True)
    backend = _backend(tmp_path, mode="ok")
    with pytest.raises(BackendConfigurationError, match="attempt"):
        await backend.execute(_request(), attempt_key=ATTEMPT_KEY, cwd=cwd, home=stray_home)


# ---------------------------------------------------------------- 插件源码契约

def test_plugin_source_contract() -> None:
    source = A.PLUGIN_SOURCE_DIR / "submit_result.mjs"
    assert source.is_file(), "插件源码必须进仓：%s" % source
    body = source.read_text(encoding="utf-8")
    assert "export const name = 's2-submit-result'" in body
    assert "export const inject = ['tools']" in body
    assert "ctx.tools.register(defineTool(" in body
    assert "name: 'submit_result'" in body
    assert "from '@deepseek-ai/dsh-tools'" in body, "不得抄探针的绝对路径 import"
    # 插件不落没有消费者的侧信道（提交事实由 NDJSON tool_call/tool_result 承载）
    assert "appendFileSync" not in body and "submissions.jsonl" not in body
    assert "DSH_SELFCHECK_DIR" not in body, "提交插件不应依赖自检侧信道"
    assert "accepted: true" in body and "problems: []" in body
    assert "PROBE_SUBMIT_LOG" not in body and "/home/" not in body
