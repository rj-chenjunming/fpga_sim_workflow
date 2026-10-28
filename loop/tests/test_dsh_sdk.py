"""S2-c：DSH sdk stdio 观测面 + D2 压缩计数（SPEC-REV-14 B4/B7、§3-D2）。

判据（不读实现也应成立）：
- 方法/通知名只能是锁定版本 `0.2.1-rc.2` 的 7 + 4 个（类型文件逐字），多一个/少一个都是换版本；
- 坏行、非对象、`jsonrpc != "2.0"`、未知通知、既无 id 也无 method、未知 id 的响应 ⇒ **显式失败**；
- 响应按 `id` 匹配（**允许乱序**）；error frame 保留 wire `code/message/data`；超时 ⇒ `SdkTimeout`；
- `initialize` 的 `serverInfo.name`/`version` 与锁定值不符 ⇒ `SdkVersionMismatch`；
- 通知落账：`subagent.started/finished` 明细 + 计数、`session.status` 序列、`session.event` 计数与 kind 计数；
- D2：`compaction/summary` 条数 = 压缩次数；`compaction/end.data.error` **显式**登记（不吞）；
  zstd 缺失/解压失败 ⇒ `availability="unavailable"`，**不编数**。

显式降级线：真实 `session/prompt`→`session/wait` 全链路需要模型授权，本片**不验**（不发真实 prompt），
真机只做 `initialize` + `shutdown` 握手；stub 服务端是 C1 证据，**不冒充** C2。
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from host.agent_backends import dsh_process as DP
from host.agent_backends import dsh_sdk as SDK

# 真机安装位置（可用环境变量覆盖；不存在则相关用例 skip，不当通过）
REAL_NODE = Path(os.environ.get("LOOP_DSH_NODE", "/home/soft/DSH/node/bin/node"))
REAL_DSH_BIN = Path(os.environ.get(
    "LOOP_DSH_BIN",
    "/home/soft/DSH/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js"))
SDK_TYPES = Path("/home/soft/DSH/versions/0.2.1-rc.2/node_modules/"
                 "@deepseek-ai/dsh-sdk-protocol/lib/types/types.d.ts")
SESSION_EVENT_TYPES_JS = Path("/home/soft/DSH/versions/0.2.1-rc.2/node_modules/"
                              "@deepseek-ai/dsh-session/lib/types/known-event-types.js")


# ---------------------------------------------------------------- stub JSON-RPC 服务端

STUB = '''#!/usr/bin/env python3
"""最小 sdk 服务端替身：stdio NDJSON JSON-RPC 2.0（只用于单测，不烧模型）。"""
import json, os, sys

MODE = os.environ.get("SDK_STUB_MODE", "ok")
RECORD = os.environ.get("SDK_STUB_RECORD")
FRAMES = os.environ.get("SDK_STUB_RECORD_FRAMES")
SERVER_NAME = os.environ.get("SDK_STUB_SERVER_NAME", "deepseek-harness-sdk-runtime")
SERVER_VERSION = os.environ.get("SDK_STUB_SERVER_VERSION", "0.0.1")

RESULT_BY_METHOD = {"session/wait": {},
                    "session/working-directory/get": {"cwd": "/stub/cwd"},
                    "session/working-directory/set": {"cwd": "/stub/cwd"}}


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\\n")
    sys.stdout.flush()


def respond(rid, result):
    emit({"jsonrpc": "2.0", "id": rid, "result": result})


def notify(method, params):
    emit({"jsonrpc": "2.0", "method": method, "params": params})


def record_facts():
    if not RECORD:
        return
    with open(RECORD, "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv, "cwd": os.getcwd(), "env": dict(os.environ)}, fh)


record_facts()
if MODE == "exit_early":
    sys.exit(0)

pending = []
while True:
    line = sys.stdin.readline()
    if not line:
        break
    text = line.strip()
    if not text:
        continue
    if FRAMES:
        with open(FRAMES, "a", encoding="utf-8") as fh:
            fh.write(text + "\\n")
    frame = json.loads(text)
    method = frame.get("method")
    rid = frame.get("id")
    params = frame.get("params") or {}

    # —— 故意坏帧/坏行为（每个 mode 只做一件事，便于定位）
    if MODE == "bad_json":
        sys.stdout.write("this is not a frame\\n"); sys.stdout.flush(); continue
    if MODE == "not_object":
        sys.stdout.write("[1, 2, 3]\\n"); sys.stdout.flush(); continue
    if MODE == "bad_jsonrpc":
        emit({"jsonrpc": "1.0", "id": rid, "result": {}}); continue
    if MODE == "unknown_notification":
        notify("totally.unknown.notification", {}); continue
    if MODE == "no_id_no_method":
        emit({"jsonrpc": "2.0", "params": {}}); continue
    if MODE == "unknown_id":
        emit({"jsonrpc": "2.0", "id": 987654, "result": {}}); continue
    if MODE == "no_reply":
        continue
    if MODE == "ignore_shutdown" and method == "shutdown":
        continue
    if MODE == "out_of_order":
        pending.append((rid, method))
        if len(pending) == 2:
            for pid, pmethod in reversed(pending):
                respond(pid, RESULT_BY_METHOD.get(pmethod, {}))
        continue

    if method == "initialize":
        if MODE == "error_frame":
            emit({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32603, "message": "boom",
                            "data": {"detail": "provider route"}}})
        else:
            respond(rid, {"serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}})
    elif method == "session/prompt":
        sid = params.get("sessionId")
        respond(rid, {"messageId": "msg-%s" % rid})
        notify("session.status", {"sessionId": sid, "status": "running"})
        notify("session.event", {"sessionId": sid,
                                 "event": {"type": "subagent/catalog", "seq": 16, "time": 1,
                                           "data": {"childId": "child-1"}}})
        notify("subagent.started", {"parentSessionId": sid, "childSessionId": "child-1"})
        notify("session.status", {"sessionId": "child-1", "status": "running"})
        notify("session.status", {"sessionId": "child-1", "status": "idle"})
        notify("subagent.finished", {"provider": "spawn", "agentId": "child-1",
                                     "parentSessionId": sid, "childSessionId": "child-1",
                                     "status": "ok", "stopReason": "completed",
                                     "lastAssistantMessage": [{"type": "text", "text": "2"}]})
        notify("session.event", {"sessionId": sid,
                                 "event": {"type": "tool/result", "seq": 17, "time": 2, "data": {}}})
        notify("subagent.started", {"parentSessionId": sid, "childSessionId": "child-2"})
        notify("subagent.finished", {"provider": "spawn-fork", "agentId": "child-2",
                                     "parentSessionId": sid, "childSessionId": "child-2",
                                     "status": "error", "stopReason": "error"})
    elif method == "session/wait":
        respond(rid, {})
    elif method == "shutdown":
        respond(rid, {})
        sys.exit(0)
    else:
        emit({"jsonrpc": "2.0", "id": rid,
              "error": {"code": -32601, "message": "missing handler: %s" % method}})
'''


def _write_stub(tmp_path: Path) -> Path:
    path = tmp_path / "sdk_stub.py"
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    return path


@dataclasses.dataclass
class StubRun:
    client: SDK.SdkClient
    stub: Path
    root: Path
    home: Path
    env_extra: dict[str, str]
    env_path: Path
    frames_path: Path

    def env_record(self) -> dict[str, Any]:
        return json.loads(self.env_path.read_text(encoding="utf-8"))

    def frames(self) -> list[dict[str, Any]]:
        if not self.frames_path.exists():
            return []
        return [json.loads(line) for line in
                self.frames_path.read_text(encoding="utf-8").splitlines() if line.strip()]


@contextlib.asynccontextmanager
async def _running(tmp_path: Path, *, mode: str = "ok", server_name: str | None = None,
                   server_version: str | None = None, record_env: bool = False,
                   timeout_s: float = 10.0, api_key: str | None = None):
    stub = _write_stub(tmp_path)
    home = tmp_path / "dsh-home"
    home.mkdir(exist_ok=True)
    env_path = tmp_path / "stub-env.json"
    frames_path = tmp_path / "stub-frames.ndjson"
    env_extra = {"SDK_STUB_MODE": mode, "SDK_STUB_RECORD_FRAMES": str(frames_path)}
    if server_name:
        env_extra["SDK_STUB_SERVER_NAME"] = server_name
    if server_version:
        env_extra["SDK_STUB_SERVER_VERSION"] = server_version
    if record_env:
        env_extra["SDK_STUB_RECORD"] = str(env_path)
    client = SDK.SdkClient(node=sys.executable, bin=stub, cwd=tmp_path, home=home,
                           timeout_s=timeout_s, api_key=api_key, env_extra=env_extra)
    await client.start()
    run = StubRun(client=client, stub=stub, root=tmp_path, home=home, env_extra=env_extra,
                  env_path=env_path, frames_path=frames_path)
    try:
        yield run
    finally:
        await client.close(shutdown_timeout_s=1.0)


# ---------------------------------------------------------------- 映射表（B7 版本锁定）

def test_request_methods_are_locked_verbatim() -> None:
    assert set(SDK.REQUEST_METHODS) == {
        "initialize", "session/prompt", "session/resume", "session/wait",
        "session/working-directory/get", "session/working-directory/set", "shutdown"}
    assert len(SDK.REQUEST_METHODS) == 7


def test_notification_methods_are_locked_verbatim() -> None:
    assert set(SDK.NOTIFICATION_METHODS) == {
        "session.event", "session.status", "subagent.started", "subagent.finished"}
    assert len(SDK.NOTIFICATION_METHODS) == 4


def test_server_identity_and_versions_are_locked() -> None:
    assert SDK.SERVER_NAME == "deepseek-harness-sdk-runtime"
    assert SDK.SDK_PROTOCOL_VERSION == "0.2.1-rc.2"
    # wire 上的 serverInfo.version 不是包版本（实测 0.0.1）；换版本必须重录（B7）
    assert SDK.SERVERINFO_VERSION == "0.0.1"
    assert SDK.SDK_PROFILE == "sdk"


def test_mapping_table_matches_installed_types() -> None:
    if not SDK_TYPES.is_file():
        pytest.skip(f"缺 SDK 类型文件（{SDK_TYPES}）")
    text = SDK_TYPES.read_text(encoding="utf-8")
    for method in SDK.REQUEST_METHODS:
        assert f"'{method}'" in text, f"类型文件里没有请求方法 {method!r}"
    for method in SDK.NOTIFICATION_METHODS:
        assert f"'{method}'" in text, f"类型文件里没有通知 {method!r}"
    assert "deepseek-harness-sdk-runtime" in text


def test_compaction_kind_names_match_installed_session_vocabulary() -> None:
    assert set(SDK.COMPACTION_KINDS) == {"compaction/prune", "compaction/start",
                                        "compaction/summary", "compaction/end"}
    if not SESSION_EVENT_TYPES_JS.is_file():
        pytest.skip(f"缺 session 事件词表（{SESSION_EVENT_TYPES_JS}）")
    text = SESSION_EVENT_TYPES_JS.read_text(encoding="utf-8")
    for kind in SDK.COMPACTION_KINDS:
        assert f"'{kind}'" in text, f"事件词表里没有 {kind!r}"


# ---------------------------------------------------------------- 严格帧（显式失败）

@pytest.mark.parametrize("mode, expected", [
    ("bad_json", SDK.SdkBadFrame),
    ("not_object", SDK.SdkBadFrame),
    ("bad_jsonrpc", SDK.SdkBadFrame),
    ("unknown_notification", SDK.SdkUnknownNotification),
    ("no_id_no_method", SDK.SdkBadFrame),
    ("unknown_id", SDK.SdkBadFrame),
])
async def test_bad_frames_are_explicit(tmp_path: Path, mode: str, expected: type) -> None:
    async with _running(tmp_path, mode=mode) as run:
        with pytest.raises(expected):
            await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")


async def test_unknown_request_method_rejected_before_send(tmp_path: Path) -> None:
    async with _running(tmp_path, mode="no_reply") as run:
        with pytest.raises(SDK.SdkUnknownMethod):
            await run.client.request("session/not-a-method", {})
        assert not run.frames(), "未知方法不得落到 wire 上"


async def test_timeout_raises_sdk_timeout(tmp_path: Path) -> None:
    async with _running(tmp_path, mode="no_reply", timeout_s=0.4) as run:
        with pytest.raises(SDK.SdkTimeout):
            await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")


async def test_server_exit_early_is_explicit(tmp_path: Path) -> None:
    async with _running(tmp_path, mode="exit_early") as run:
        with pytest.raises(SDK.SdkServerClosed):
            await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")


async def test_error_frame_keeps_wire_code_message_data(tmp_path: Path) -> None:
    async with _running(tmp_path, mode="error_frame") as run:
        with pytest.raises(SDK.SdkResponseError) as caught:
            await run.client.initialize(cwd=tmp_path, provider="unregistered", model="m")
    assert caught.value.code == -32603
    assert caught.value.message == "boom"
    assert caught.value.data == {"detail": "provider route"}


@pytest.mark.parametrize("server_name, server_version", [
    ("deepseek-harness-sdk-runtime", "9.9.9"),
    ("some-other-runtime", "0.0.1"),
])
async def test_initialize_version_lock(tmp_path: Path, server_name: str,
                                      server_version: str) -> None:
    async with _running(tmp_path, server_name=server_name, server_version=server_version) as run:
        with pytest.raises(SDK.SdkVersionMismatch):
            await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")


async def test_initialize_ok_records_handshake(tmp_path: Path) -> None:
    async with _running(tmp_path) as run:
        info = await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        assert info["serverInfo"] == {"name": SDK.SERVER_NAME,
                                      "version": SDK.SERVERINFO_VERSION}
        handshake = run.client.observations().handshake
        assert handshake is not None
        assert handshake.name == SDK.SERVER_NAME
        assert handshake.version == SDK.SERVERINFO_VERSION


# ---------------------------------------------------------------- 乱序 / 通知落账

async def test_responses_are_matched_by_id_not_by_order(tmp_path: Path) -> None:
    async with _running(tmp_path, mode="out_of_order") as run:
        first, second = await asyncio.gather(
            run.client.request("session/wait", {"sessionId": "s1"}),
            run.client.request("session/working-directory/get", {"sessionId": "s1"}))
    # 服务端故意反序回执：若客户端按到达顺序配对，两个结果会互换
    assert first == {}
    assert second == {"cwd": "/stub/cwd"}


async def test_notifications_are_recorded(tmp_path: Path) -> None:
    async with _running(tmp_path) as run:
        await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        message_id = await run.client.session_prompt("s1", "hi")
        assert message_id.startswith("msg-"), "session/prompt 只回messageId（入队身份）"
        assert await run.client.session_wait("s1") == {}

        obs = run.client.observations()
        # subagent 明细 + 计数
        assert obs.subagents_started_count == 2
        assert obs.subagents_finished_count == 2
        started = obs.subagents_started
        assert started[0].parent_session_id == "s1"
        assert started[0].child_session_id == "child-1"
        finished = obs.subagents_finished
        assert finished[0].provider == "spawn"
        assert finished[0].status == "ok"
        assert finished[0].stop_reason == "completed"
        assert finished[0].parent_session_id == "s1"
        assert finished[0].child_session_id == "child-1"
        assert finished[0].last_assistant_message == ({"type": "text", "text": "2"},)
        assert finished[1].status == "error"
        assert finished[1].stop_reason == "error"
        assert finished[1].last_assistant_message == ()
        # session.status 序列（含子会话）
        assert obs.session_status == (("s1", "running"), ("child-1", "running"),
                                      ("child-1", "idle"))
        # session.event 计数 + kind 计数
        assert obs.session_event_count == 2
        assert dict(obs.session_event_kinds) == {"subagent/catalog": 1, "tool/result": 1}

        assert await run.client.shutdown() == {}


async def test_observations_are_readonly_snapshots(tmp_path: Path) -> None:
    async with _running(tmp_path) as run:
        await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        await run.client.session_prompt("s1", "第一轮")
        await run.client.session_wait("s1")      # 同步点：保证通知已全部落账
        first = run.client.observations()
        assert first.subagents_started_count == 2

        # 冻结快照：再发生通知不改旧快照
        await run.client.session_prompt("s1", "第二轮")
        await run.client.session_wait("s1")
        assert first.subagents_started_count == 2
        assert run.client.observations().subagents_started_count == 4

        # 只读视图：改不动
        with pytest.raises(dataclasses.FrozenInstanceError):
            first.subagents_started[0].child_session_id = "x"          # type: ignore[misc]
        with pytest.raises(TypeError):
            first.session_event_kinds["x"] = 1                          # type: ignore[index]
        with pytest.raises(dataclasses.FrozenInstanceError):
            first.session_event_count = 99                              # type: ignore[misc]


# ---------------------------------------------------------------- wire 形状 / 进程回收

async def test_wire_frames_match_locked_protocol(tmp_path: Path) -> None:
    async with _running(tmp_path) as run:
        await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        await run.client.session_prompt("s1", "hi")
        await run.client.session_wait("s1")
        await run.client.shutdown()
        frames = run.frames()

    methods = [frame.get("method") for frame in frames]
    assert methods == ["initialize", "session/prompt", "session/wait", "shutdown"]
    for frame in frames:
        assert frame["jsonrpc"] == "2.0"
        assert isinstance(frame["id"], int)
    prompt = frames[1]
    assert prompt["params"]["sessionId"] == "s1"
    assert prompt["params"]["contentBlocks"] == [{"type": "text", "text": "hi"}]
    # shutdown 的 params 在类型表里是 undefined ⇒ 不得凭空造一个
    assert "params" not in frames[3]


async def test_spawn_uses_allowlisted_env_from_dsh_process(tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDK_LEAK_SENTINEL", "should-not-leak")
    async with _running(tmp_path, record_env=True) as run:
        await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        record = run.env_record()
    expected = DP.build_env(DP.AttemptSpec(
        attempt_key="sdk-observation", cwd=tmp_path, home=run.home, task="",
        dsh_bin=run.stub, node=Path(sys.executable), profile="sdk", wrap=False,
        env_extra=run.env_extra))
    # stub 是 CPython：它启动时按 PEP 538 把 LC_CTYPE 塞进自己的 os.environ，
    # 那是解释器行为、不是白名单的一部分（白名单里没有 LC_CTYPE）
    observed_keys = set(record["env"]) - {"LC_CTYPE"}
    assert observed_keys == set(expected), "env 白名单必须是 dsh_process.build_env 同一口径"
    assert record["env"]["DSH_PROFILE"] == "sdk"
    assert record["env"]["DSH_HOME"] == str(run.home)
    assert record["env"]["HOME"] == str(run.home)
    assert "SDK_LEAK_SENTINEL" not in record["env"]
    assert "PUBLIC_API_KEY" not in record["env"]
    assert Path(record["cwd"]).resolve() == tmp_path.resolve()
    argv = record["argv"]
    assert "--profile" in argv and argv[argv.index("--profile") + 1] == "sdk"


async def test_api_key_goes_through_env_only(tmp_path: Path) -> None:
    async with _running(tmp_path, record_env=True, api_key="sk-TEST") as run:
        await run.client.initialize(cwd=tmp_path, provider="deepseek-official", model="m")
        record = run.env_record()
    assert record["env"]["PUBLIC_API_KEY"] == "sk-TEST"
    # 凭据只经 env：除 stub 自己的 env 记录外，本次运行不落任何含 key 的文件
    leaks = []
    for path in tmp_path.rglob("*"):
        if not path.is_file() or path == run.env_path:
            continue
        try:
            if "sk-TEST" in path.read_text(encoding="utf-8", errors="replace"):
                leaks.append(str(path.relative_to(tmp_path)))
        except OSError:
            continue
    assert leaks == [], f"凭据出现在文件里：{leaks}"


async def test_close_reaps_process_even_when_shutdown_hangs(tmp_path: Path) -> None:
    stub = _write_stub(tmp_path)
    home = tmp_path / "dsh-home"
    home.mkdir()
    client = SDK.SdkClient(node=sys.executable, bin=stub, cwd=tmp_path, home=home,
                           timeout_s=0.4,
                           env_extra={"SDK_STUB_MODE": "ignore_shutdown"})
    await client.start()
    try:
        await client.close(shutdown_timeout_s=0.2)
    finally:
        if not client.closed:
            await client.close(shutdown_timeout_s=0.2)
    assert client.closed
    assert client.returncode is not None, "close() 必须确保子进程被回收（TERM→KILL）"
    with pytest.raises(SDK.SdkServerClosed):
        await client.request("session/wait", {"sessionId": "s1"})


async def test_start_requires_existing_cwd(tmp_path: Path) -> None:
    stub = _write_stub(tmp_path)
    missing = tmp_path / "nope"
    client = SDK.SdkClient(node=sys.executable, bin=stub, cwd=missing,
                           home=tmp_path / "dsh-home")
    with pytest.raises(SDK.SdkProtocolError):
        await client.start()
    assert client.returncode is None


# ---------------------------------------------------------------- D2 压缩计数（纯函数）

HEADER_LINE = ('{"type":"session","version":4,"id":"session-x","createdAt":1793167185223,'
               '"cwd":"/w","isSeeded":false,"delegationDepth":0}')


def _summary(compaction_id: str, *, seq: int, time: int, tokens: int) -> dict[str, Any]:
    return {"type": "compaction/summary", "seq": seq, "time": time,
            "data": {"compactionId": compaction_id,
                     "summary": [{"type": "text", "text": "摘要"}],
                     "shadowedRange": {"start": 8, "end": 28},
                     "shadowedSeqs": [8, 9, 10],
                     "shadowedTokenCount": tokens,
                     "provider": "public", "model": "origin-deepseek-v4-1-flash",
                     "maxTokens": 4096,
                     "usage": {"inputTokens": 441, "outputTokens": 1581}}}


def _end(compaction_id: str, *, seq: int, time: int, error: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"compactionId": compaction_id, "turn": 1}
    if error is not None:
        data["error"] = error
    return {"type": "compaction/end", "seq": seq, "time": time, "data": data}


def _lines(*events: dict[str, Any]) -> list[str]:
    return [HEADER_LINE] + [json.dumps(event) for event in events]


def test_parse_compaction_counts_and_times() -> None:
    facts = SDK.parse_session_log_lines(_lines(
        {"type": "compaction/start", "seq": 35, "time": 1793167192541,
         "data": {"compactionId": "c1", "turn": 1}},
        _summary("c1", seq=36, time=1793167200835, tokens=3356),
        _end("c1", seq=38, time=1793167200837),
        {"type": "compaction/start", "seq": 39, "time": 1793167200838,
         "data": {"compactionId": "c2", "turn": 1}},
        _end("c2", seq=40, time=1793167206106,
             error="summary is not smaller than the shadowed content (1314 >= 1314)"),
        _summary("c3", seq=41, time=1793167300000, tokens=1200),
        _end("c3", seq=42, time=1793167300100),
        {"type": "compaction/prune", "seq": 27, "time": 1793167189406,
         "data": {"shadowedRange": {"start": 25, "end": 25}, "shadowedSeqs": [25],
                  "shadowedTokenCount": 3218}},
        {"type": "tool/result", "seq": 50, "time": 1793167400000, "data": {}},
    ))
    assert facts.availability == "ok"
    assert facts.count == 2, "压缩次数 = compaction/summary 条数"
    assert facts.compaction_ids == ("c1", "c3")
    assert facts.times == (1793167200835, 1793167300000)
    assert facts.freed_tokens == 3356 + 1200
    assert facts.start_count == 2 and facts.end_count == 3
    assert facts.prune_count == 1
    assert facts.error_count == 1, "compaction/end.error 必须显式登记，不吞"
    assert facts.errors[0].compaction_id == "c2"
    assert facts.errors[0].error.startswith("summary is not smaller")
    assert facts.failed is True


def test_parse_compaction_no_compaction_is_zero_not_success() -> None:
    facts = SDK.parse_session_log_lines(_lines(
        {"type": "tool/result", "seq": 1, "time": 1, "data": {}}))
    assert facts.availability == "ok"
    assert facts.count == 0 and facts.error_count == 0
    assert facts.failed is False


def test_parse_compaction_blank_lines_tolerated_but_bad_json_fails() -> None:
    lines = _lines(_summary("c1", seq=1, time=1, tokens=1)) + ["", "  "]
    assert SDK.parse_session_log_lines(lines).count == 1
    with pytest.raises(SDK.SessionLogError):
        SDK.parse_session_log_lines(["not json at all"])


def test_parse_compaction_missing_identity_fails_loud() -> None:
    broken = {"type": "compaction/summary", "seq": 1, "time": 1,
              "data": {"summary": [], "shadowedTokenCount": 1}}
    with pytest.raises(SDK.SessionLogError):
        SDK.parse_session_log_lines(_lines(broken))


def test_parse_compaction_summary_without_data_fails_loud() -> None:
    with pytest.raises(SDK.SessionLogError):
        SDK.parse_session_log_lines(['{"type":"compaction/summary","seq":1,"time":1}'])


def test_compaction_facts_reject_inconsistent_shape() -> None:
    with pytest.raises(ValueError):
        SDK.CompactionFacts(availability="unavailable", count=3)
    with pytest.raises(ValueError):
        SDK.CompactionFacts(availability="ok", count=1, reason="不该有原因")


# ---------------------------------------------------------------- D2 读真实格式（zstd）

def _zstd_available() -> bool:
    return shutil.which("zstd") is not None


def _write_multiframe_zstd(tmp_path: Path, parts: list[bytes]) -> Path:
    """把多段 JSONL 分别压成独立 zstd 帧后拼接——复刻真实 log 的追加写多帧形态。"""
    blob = b""
    for index, part in enumerate(parts):
        raw = tmp_path / f"part-{index}.jsonl"
        raw.write_bytes(part)
        blob += subprocess.run(["zstd", "-q", "-c", str(raw)], check=True,
                               capture_output=True).stdout
    target = tmp_path / "session.v4.jsonl.zstd"
    target.write_bytes(blob)
    return target


def test_read_session_log_decodes_multiframe_zstd(tmp_path: Path) -> None:
    if not _zstd_available():
        pytest.skip("缺 zstd（/usr/bin/zstd），解压用例跳过")
    first = ("\n".join(_lines(
        {"type": "compaction/start", "seq": 35, "time": 1, "data": {"compactionId": "c1"}},
        _summary("c1", seq=36, time=1793167200835, tokens=3356))) + "\n").encode()
    second = ("\n".join(_lines(
        _end("c1", seq=38, time=1793167200837),
        _end("c2", seq=40, time=1793167206106, error="truncated at the token cap"))) + "\n").encode()
    log = _write_multiframe_zstd(tmp_path, [first, second])
    facts = SDK.read_session_log(log)
    assert facts.availability == "ok"
    assert facts.count == 1, "多帧必须一次解全（否则会漏帧、少计数）"
    assert facts.error_count == 1
    assert facts.end_count == 2


def test_read_session_log_unavailable_without_zstd(tmp_path: Path) -> None:
    log = tmp_path / "session.v4.jsonl.zstd"
    log.write_bytes(b"\x28\xb5\x2f\xfd")
    facts = SDK.read_session_log(log, zstd=str(tmp_path / "no-such-zstd"))
    assert facts.availability == "unavailable"
    assert facts.count == 0 and facts.error_count == 0, "不可用时不得编数"
    assert facts.reason and "zstd" in facts.reason


def test_read_session_log_corrupt_archive_is_unavailable(tmp_path: Path) -> None:
    if not _zstd_available():
        pytest.skip("缺 zstd（/usr/bin/zstd），解压用例跳过")
    log = tmp_path / "session.v4.jsonl.zstd"
    log.write_bytes(b"definitely not a zstd frame")
    facts = SDK.read_session_log(log)
    assert facts.availability == "unavailable"
    assert facts.count == 0 and facts.reason


def test_read_session_log_missing_file_is_explicit(tmp_path: Path) -> None:
    with pytest.raises(SDK.SessionLogError):
        SDK.read_session_log(tmp_path / "nope.jsonl.zstd")


# ---------------------------------------------------------------- 真机握手（不发 prompt）

def _real_install_ready() -> bool:
    return REAL_NODE.is_file() and REAL_DSH_BIN.is_file()


@pytest.mark.skipif(not _real_install_ready(), reason="缺本机 node/dsh 安装，真机握手跳过")
async def test_real_sdk_initialize_shutdown_handshake(tmp_path: Path) -> None:
    """真 `--profile sdk` 只做 initialize + shutdown：**不发 session/prompt**（无模型授权）。"""
    home = tmp_path / "dsh-home"
    home.mkdir()
    client = SDK.SdkClient(node=REAL_NODE, bin=REAL_DSH_BIN, cwd=tmp_path, home=home,
                           timeout_s=120.0)
    await client.start()
    try:
        try:
            info = await client.initialize(cwd=tmp_path, provider="deepseek-official",
                                           model="deepseek-v4-1-flash")
        except SDK.SdkResponseError as exc:
            # provider 路由未注册时 DSH 用 -32603 显式拒绝；那是显式失败，不是静默
            assert exc.code == -32603, f"未预期错误码：{exc.code} {exc.message}"
            pytest.skip("真实 initialize 因 provider 路由返回 -32603；"
                        "error frame 已被显式化为 SdkResponseError（不重试、不 prompt）")
        assert info["serverInfo"]["name"] == SDK.SERVER_NAME
        assert info["serverInfo"]["version"] == SDK.SERVERINFO_VERSION
        assert await client.shutdown() == {}
    finally:
        await client.close(shutdown_timeout_s=5.0)
    assert client.returncode is not None
