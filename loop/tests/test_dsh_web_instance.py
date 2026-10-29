"""S7c：Host 起常驻 DSH Web 实例 + `agent_instance.json` 落账（REV-16 §5.2 #1 / §9-1）。

不烧模型、不依赖真 dsh：用 **python stub 冒充 `node bin.js --profile web`**
（stub 自己 bind 一个真 loopback HTTP 端口并按实测形态打印 `dsh web:` 公告行）。
真机取证（一次性、不入库）在 `loop/.logs/s7c/`：`--port 0` ⇒ 实际端口在公告行里；
匿名 `GET /` ⇒ 401；`?token=` ⇒ 303 + cookie。

铁律（本文件固定住的不变式）：
- **token 永不进**日志 / `repr` / `describe()`；只进受管元数据文件（0600）。
- 就绪判据 = 匿名 `GET /` **401**，不是"进程起来了"、也不是"端口能连上"。
- 失败的起实例必须**收干净**（不留下半死进程）。
- 写出的元数据必须能过**读者**（`services.instance_proxy.load_target`）的判据 —— 写入方不重抄判据。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from host.agent_backends import dsh_web_instance as WI
from services import instance_proxy

#: 实测公告行的 token 长度（P1/P8 + S7c 探针 #1 一致：43 字符）
REAL_TOKEN_LEN = 43
#: stub 用的假 token：43 个 `T`（任何日志里出现它都是泄密）
STUB_TOKEN = "T" * REAL_TOKEN_LEN

STUB = r'''#!/usr/bin/env python3
"""冒充 `node <bin.js> --profile web`：解析 --port，bind 真端口，按实测形态打印公告行。"""
import http.server, json, os, sys, threading, time
from pathlib import Path

sidecar = Path(__file__ + ".mode")
mode = sidecar.read_text(encoding="utf-8").strip() if sidecar.is_file() else "ok"
Path(__file__ + ".pid").write_text(str(os.getpid()), encoding="utf-8")
TOKEN = "T" * 43

argv = sys.argv[1:]
port_arg = 0
for index, item in enumerate(argv):
    if item == "--port":
        port_arg = int(argv[index + 1])

if mode == "crash":
    sys.stderr.write("stub: refusing to start\n")
    sys.exit(3)
if mode == "silent":
    time.sleep(120)
    sys.exit(0)
if mode == "nonloopback":
    print("dsh web: http://0.0.0.0:1234/?token=" + TOKEN, flush=True)
    time.sleep(120)
    sys.exit(0)
if mode == "noport":
    print("dsh web: http://127.0.0.1/?token=" + TOKEN, flush=True)
    time.sleep(120)
    sys.exit(0)
if mode == "garbage":
    print("dsh web: not-a-url", flush=True)
    time.sleep(120)
    sys.exit(0)

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        open_gate = mode == "open"
        body = b"open" if open_gate else b"dsh web authentication required\n"
        self.send_response(200 if open_gate else 401)
        self.send_header("content-length", str(len(body)))
        self.send_header("content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

server = http.server.ThreadingHTTPServer(("127.0.0.1", port_arg), Handler)
actual_port = server.server_address[1]
print("dsh web: http://127.0.0.1:%d/?token=%s" % (actual_port, TOKEN), flush=True)
server.serve_forever()
'''


def _stub(tmp_path: Path, mode: str = "ok") -> Path:
    path = tmp_path / "dsh_web_stub.py"
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    (tmp_path / "dsh_web_stub.py.mode").write_text(mode, encoding="utf-8")
    return path


def _config(tmp_path: Path, stub: Path, **overrides) -> WI.WebInstanceConfig:
    base = dict(enabled=True, node=Path(sys.executable), bin=stub,
                version="0.2.1-rc.2", home=tmp_path / "home",
                host="127.0.0.1", preferred_port=0,
                start_timeout_s=20.0, stop_grace_s=2.0)
    base.update(overrides)
    return WI.WebInstanceConfig(**base)


def _wait_pid_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


# ================================================================ 公告行解析（实测形态）

def test_parse_launch_line_real_probe_shape():
    """判据：**逐字**用探针 #1 的公告行形态（token 已脱敏但长度/字符集是实测事实）。"""
    token = "A" * REAL_TOKEN_LEN
    target = WI.parse_launch_line(f"dsh web: http://127.0.0.1:44239/?token={token}")
    assert target is not None
    assert (target.host, target.port, target.token) == ("127.0.0.1", 44239, token)
    assert target.origin == "http://127.0.0.1:44239"


def test_parse_launch_line_ignores_non_announcement_lines():
    assert WI.parse_launch_line("dsh web: opening the default browser; pass --no-open to disable") is None
    assert WI.parse_launch_line("dsh: warning: 1 entry did not activate") is None
    assert WI.parse_launch_line("") is None


@pytest.mark.parametrize("line,reason", [
    (f"dsh web: http://127.0.0.1/?token={'A' * REAL_TOKEN_LEN}", "launch_url_invalid"),   # 无端口：不猜
    (f"dsh web: http://0.0.0.0:1234/?token={'A' * REAL_TOKEN_LEN}", "launch_url_not_loopback"),
    (f"dsh web: file:///tmp/x?token={'A' * REAL_TOKEN_LEN}", "launch_url_invalid"),
])
def test_parse_launch_line_rejects_bad_targets(line: str, reason: str):
    with pytest.raises(WI.WebInstanceError) as excinfo:
        WI.parse_launch_line(line)
    assert excinfo.value.reason == reason


def test_launch_target_repr_redacts_token():
    target = WI.parse_launch_line(f"dsh web: http://127.0.0.1:9/?token={STUB_TOKEN}")
    assert STUB_TOKEN not in repr(target)
    assert "redacted 43 chars" in repr(target)


def test_authority_formatting_matches_proxy_reader():
    """口径唯一：写方与读者对 authority 的格式化必须同形（v4 与 v6 两种）。"""
    for host in ("127.0.0.1", "::1", "localhost"):
        mine = WI.LaunchTarget(host=host, port=8123, token=None).authority
        theirs = instance_proxy.InstanceTarget(host=host, port=8123, node="N3", attempt=1).authority
        assert mine == theirs


# ================================================================ 配置（SETTINGS 嵌套）

BASE = SimpleNamespace(node=Path("/opt/node"), bin=Path("/opt/bin.js"), version="0.2.1-rc.2")


def _doc(**web) -> dict:
    return {"loop": {"agent_runtime": {"dsh": {"version": "0.2.1-rc.2", "web": web}}}}


def test_config_defaults_disabled_and_home_derived_from_workspace_root():
    config = WI.config_from_settings(_doc(), base=BASE)
    assert config.enabled is False
    assert config.home == Path(__import__("host.paths", fromlist=["paths"]).WORKSPACE_ROOT) / "dsh-web-home"
    assert (config.node, config.bin, config.version) == (BASE.node, BASE.bin, BASE.version)


def test_config_reads_documented_nesting():
    config = WI.config_from_settings(
        _doc(enabled=True, home="/tmp/h", host="localhost", preferred_port=18710,
             start_timeout_s=12, stop_grace_s=1), base=BASE)
    assert config.enabled is True
    assert config.home == Path("/tmp/h")
    assert (config.host, config.preferred_port) == ("localhost", 18710)
    assert (config.start_timeout_s, config.stop_grace_s) == (12.0, 1.0)


def test_config_rejects_unknown_keys():
    """REV-16 §9-6 同款纪律：未知字段必须显式拒绝（不悄悄接受未实现开关）。"""
    with pytest.raises(WI.WebConfigError) as excinfo:
        WI.config_from_settings(_doc(enabled=True, base_path="/x"), base=BASE)
    assert excinfo.value.reason == "unknown_keys"


def test_config_rejects_non_loopback_host_and_bad_port():
    with pytest.raises(WI.WebConfigError) as excinfo:
        WI.config_from_settings(_doc(enabled=True, host="0.0.0.0"), base=BASE)
    assert excinfo.value.reason == "host_not_loopback"
    with pytest.raises(WI.WebConfigError) as excinfo:
        WI.config_from_settings(_doc(enabled=True, preferred_port=70000), base=BASE)
    assert excinfo.value.reason == "bad_port"


# ================================================================ argv / env

def test_build_argv_binds_one_concrete_loopback_and_never_opens_browser(tmp_path):
    config = _config(tmp_path, _stub(tmp_path))
    argv = WI.build_argv(config, 0)
    assert argv[0] == str(Path(sys.executable))
    assert argv[1] == str(config.bin)
    assert argv[argv.index("--profile") + 1] == "web"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "0"
    assert "--no-open" in argv
    assert argv.count("--port") == 1


def test_build_env_carries_no_credentials(tmp_path):
    """Web 面不调模型 ⇒ 不传凭据；这条是 `/proc/<pid>/environ` 暴露面的减法。"""
    config = _config(tmp_path, _stub(tmp_path))
    env = WI.build_env(config)
    assert env["DSH_HOME"] == str(config.home) and env["HOME"] == str(config.home)
    assert env["DSH_PROFILE"] == "web"
    assert "PUBLIC_API_KEY" not in env
    assert not any("KEY" in name or "TOKEN" in name.upper() for name in env)


# ================================================================ 端口策略

def test_resolve_port_prefers_free_port():
    assert WI.resolve_port(0) == (0, False)


def test_resolve_port_falls_back_when_preferred_is_busy():
    holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    try:
        port = holder.getsockname()[1]
        assert WI.resolve_port(port) == (0, True)
    finally:
        holder.close()


# ================================================================ 起 / 停（真进程 stub）

def test_start_reports_actual_port_and_verifies_auth_gate(tmp_path):
    stub = _stub(tmp_path)
    instance = WI.start(_config(tmp_path, stub))
    try:
        assert instance.is_running()
        assert instance.target.port > 0
        assert instance.target.token == STUB_TOKEN
        assert instance.port_requested == 0 and instance.port_fallback is False
        assert instance.startup_s is not None and instance.startup_s >= 0
    finally:
        instance.stop()
    assert instance.is_running() is False


def test_start_rejects_instance_without_auth_gate(tmp_path):
    """匿名 `GET /` 返回 200 ⇒ token 门没上 ⇒ **显式失败**，不得当就绪。"""
    instance = WI.WebInstance(_config(tmp_path, _stub(tmp_path, "open")))
    with pytest.raises(WI.WebInstanceError) as excinfo:
        instance.start()
    assert excinfo.value.reason == "health_unexpected_status"
    assert instance.is_running() is False


def test_start_crashed_process_fails_explicitly_and_leaves_nothing(tmp_path):
    instance = WI.WebInstance(_config(tmp_path, _stub(tmp_path, "crash")))
    with pytest.raises(WI.WebInstanceError) as excinfo:
        instance.start()
    assert excinfo.value.reason == "exited_before_launch"
    assert instance.is_running() is False


def test_start_timeout_is_explicit_and_kills_the_process(tmp_path):
    stub = _stub(tmp_path, "silent")
    instance = WI.WebInstance(_config(tmp_path, stub, start_timeout_s=0.8))
    with pytest.raises(WI.WebInstanceError) as excinfo:
        instance.start()
    assert excinfo.value.reason == "start_timeout"
    pid_file = stub.parent / "dsh_web_stub.py.pid"
    assert _wait_pid_gone(int(pid_file.read_text(encoding="utf-8"))), "失败的起实例留下了半死进程"


@pytest.mark.parametrize("mode", ["nonloopback", "noport", "garbage"])
def test_start_rejects_unusable_announcement(tmp_path, mode: str):
    instance = WI.WebInstance(_config(tmp_path, _stub(tmp_path, mode), start_timeout_s=5))
    with pytest.raises(WI.WebInstanceError):
        instance.start()
    assert instance.is_running() is False


def test_start_refuses_disabled_config(tmp_path):
    instance = WI.WebInstance(_config(tmp_path, _stub(tmp_path), enabled=False))
    with pytest.raises(WI.WebConfigError) as excinfo:
        instance.start()
    assert excinfo.value.reason == "web_disabled"


def test_token_never_reaches_logs_repr_or_describe(tmp_path, caplog):
    caplog.set_level("DEBUG")
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        assert STUB_TOKEN not in repr(instance)
        assert STUB_TOKEN not in json.dumps(instance.describe(), ensure_ascii=False)
        assert instance.target.token == STUB_TOKEN  # 只允许在这里（受管内存）
    finally:
        instance.stop()
    for record in caplog.records:
        assert STUB_TOKEN not in record.getMessage()
        assert STUB_TOKEN not in str(record.args)


# ================================================================ 元数据落账

def test_metadata_document_has_exactly_the_spec_fields(tmp_path):
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        document = instance.metadata(node="N3", attempt=2)
    finally:
        instance.stop()
    assert set(document) == {"node", "attempt", "host", "port", "token", "written_at"}
    assert (document["node"], document["attempt"]) == ("N3", 2)
    assert document["host"] == "127.0.0.1" and document["port"] > 0
    assert document["token"] == STUB_TOKEN


def test_metadata_includes_relative_session_log(tmp_path):
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        assert instance.metadata(node="N3", attempt=1,
                                 session_log="agents/N3/attempt-1/session.v4.jsonl.zstd")["session_log"] \
            == "agents/N3/attempt-1/session.v4.jsonl.zstd"
        for bad in ("/abs/session.log", "../escape/session.log", ""):
            with pytest.raises(WI.WebInstanceError) as excinfo:
                instance.metadata(node="N3", attempt=1, session_log=bad)
            assert excinfo.value.reason == "session_log_invalid"
    finally:
        instance.stop()


def test_write_metadata_is_atomic_0600_and_replaces(tmp_path):
    run_dir = tmp_path / "run"
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        path = instance.write_metadata(run_dir, node="N3", attempt=1)
    finally:
        instance.stop()
    assert path == run_dir / "agent_instance.json"
    assert (path.stat().st_mode & 0o777) == 0o600
    assert list(run_dir.glob(".*tmp*")) == []
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["node"] == "N3"

    second = {"node": "N3", "attempt": 2, "host": "127.0.0.1", "port": 1,
              "token": None, "written_at": "2026-10-29T00:00:00"}
    WI.write_metadata_document(run_dir, second)
    assert json.loads(path.read_text(encoding="utf-8")) == second


def test_metadata_roundtrip_through_proxy_reader(tmp_path):
    """**写入方 / 读者契约**：写出来的东西必须能被 `instance_proxy` 判成 ready。

    写入方不重抄 loopback/端口判据（红线 8）：这里用读者自己的 `load_target`/`availability`
    做闭环，而不是在测试里断言"我认为合法"。
    """
    run_dir = tmp_path / "run"
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        instance.write_metadata(run_dir, node="N3", attempt=4)
        target = instance_proxy.load_target(run_dir, "N3", 4)
        assert (target.host, target.port) == ("127.0.0.1", instance.target.port)
        meta = instance_proxy.availability(run_dir, run_id="RUN-S7C", node="N3", attempt=4)
        assert meta["available"] is True and meta["state"] == "ready"
        assert meta["url"] == "/instance/RUN-S7C/N3/4/"
        assert meta["attempt"] == 4
    finally:
        instance.stop()


def test_clear_metadata_makes_reader_report_target_missing(tmp_path):
    run_dir = tmp_path / "run"
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    try:
        instance.write_metadata(run_dir, node="N3", attempt=1)
        assert instance_proxy.availability(run_dir, run_id="R", node="N3",
                                           attempt=1)["available"] is True
        assert WI.clear_metadata(run_dir) is True
        meta = instance_proxy.availability(run_dir, run_id="R", node="N3", attempt=1)
        assert (meta["available"], meta["reason"]) == (False, "target_missing")
        assert WI.clear_metadata(run_dir) is False  # 幂等
    finally:
        instance.stop()


def test_stop_can_remove_metadata(tmp_path):
    run_dir = tmp_path / "run"
    instance = WI.start(_config(tmp_path, _stub(tmp_path)))
    instance.write_metadata(run_dir, node="N3", attempt=1)
    assert (run_dir / "agent_instance.json").is_file()
    instance.stop(remove_metadata=run_dir)
    assert not (run_dir / "agent_instance.json").exists()
