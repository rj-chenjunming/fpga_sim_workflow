"""S4-B 同源反代：拒绝矩阵 / 转发与头改写 / 不可用态（SPEC-REV-16 §5；`OBS-05`/`OBS-06`）。

分层（与实现同形，避免"路由能过、判据没测"）：
- **纯函数层**：`validate_path` / `validate_host` / `validate_query` / `load_target` /
  `rewrite_location` / `narrow_csp` / `rewrite_set_cookie`。R1–R8、R14–R18 的字面输入
  （字面 `..`、绝对 URI、控制字符、超长）在这一层直测 —— TestClient 会把字面 `..` 归一化，
  只有纯函数能稳定固定判据。
- **路由层**：`TestClient(api.app, base_url="http://127.0.0.1:8099")` + **真实本地 loopback 假上游**
  （`http.server.ThreadingHTTPServer`，端口 0）。真跑一次转发：上游真收到改写后的 `Host`、
  改写后的 `Origin`/`Sec-Fetch-Site`、无 hop-by-hop/X-Forwarded-*、无客户端目标参数。

不接真 DSH：本片只验反代机制（REV-16 §9-1/§9-2）；`agent_instance.json` 的写入方属 S5。
用例名与 SPEC-REV-16 §5.3 编号一一对应（`test_r01_...` … `test_r20_...`）。
"""

from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from services import instance_proxy

RUN_ID = "RUN-S4B-0001"
NODE = "N3"
BOARD = "http://127.0.0.1:8099"
PREFIX = f"/instance/{RUN_ID}/{NODE}/1/"
SEKRET = "SEKRET-managed-token-9f3a"


def _asgi_call(path: str, raw_path: str, *, method: str = "GET", query: str = "",
               headers: list[tuple[bytes, bytes]] | None = None) -> tuple[int, dict, bytes]:
    """绕过 httpx 的**客户端归一化**（httpx 会把字面 `..` 归一化掉）直接喂 ASGI scope。

    生产里 uvicorn 交出的正是这样一对：`path` 已解一次、`raw_path` 保原文。因此
    "字面 `..`"（R1）与"双编码"（R3）这类判据能在路由层真跑，而不是只测纯函数。
    """
    import asyncio

    from services import api

    raw_headers = headers or [(b"host", b"127.0.0.1:8099"), (b"accept", b"*/*")]
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path,
        "raw_path": raw_path.encode("latin-1"), "query_string": query.encode("latin-1"),
        "root_path": "", "headers": raw_headers,
        "server": ("127.0.0.1", 8099), "client": ("127.0.0.1", 50000),
    }
    messages: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        messages.append(message)

    asyncio.run(api.app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    response_headers = {key.decode().lower(): value.decode()
                        for key, value in start["headers"]}
    return int(start["status"]), response_headers, body



# ---------------------------------------------------------------- 本地 loopback 假上游


class FakeUpstream:
    """可编程的 loopback 上游；记录每次请求的方法/路径/头/体（真跑，不是 mock）。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.status = 200
        self.headers: list[tuple[str, str]] = [("Content-Type", "text/html; charset=utf-8")]
        self.body = b"<html><body>fake-dsh</body></html>"
        self.delay_s = 0.0
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw_body = self.rfile.read(length) if length else b""
                outer.calls.append({
                    "method": self.command,
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                    "body": raw_body,
                })
                if outer.delay_s:
                    time.sleep(outer.delay_s)
                payload = b"" if self.command == "HEAD" else outer.body
                self.send_response(outer.status)
                for name, value in outer.headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(outer.body)))
                self.end_headers()
                if payload:
                    self.wfile.write(payload)

            do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _handle

            def log_message(self, *args: object) -> None:  # 测试不往 stderr 打访问日志
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def authority(self) -> str:
        return f"127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def last(self) -> dict:
        assert self.calls, "上游一次都没被请求"
        return self.calls[-1]


@pytest.fixture
def upstream():
    server = FakeUpstream()
    try:
        yield server
    finally:
        server.close()


def _free_port() -> int:
    """拿一个当前无人监听的 loopback 端口（R11 用；有极小概率被抢，故只取一次即可）。"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


# ---------------------------------------------------------------- 夹具：受管元数据 + 客户端


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """run 目录（名字 = run_id：`read_view` 的封存记录身份要求 `run_id == 目录名`）。"""
    path = tmp_path / RUN_ID
    path.mkdir()
    return path


def write_instance(
    run_dir: Path,
    *,
    port: int,
    host: str = "127.0.0.1",
    token: str | None = None,
    node: str = NODE,
    attempt: int = 1,
    **extra: object,
) -> Path:
    """Host 落账的实例声明（S5 才写；本片只读，测试用夹具冒充写入方）。"""
    payload: dict[str, object] = {
        "node": node, "attempt": attempt, "host": host, "port": port,
        "written_at": "2026-10-28T00:00:00+08:00",
    }
    if token is not None:
        payload["token"] = token
    payload.update(extra)
    path = run_dir / "agent_instance.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, run_dir: Path) -> TestClient:
    """路由层客户端：**不跑 lifespan**，只替换 `_manager`（与既有 agents 用例同范式）。

    `base_url` 必须是 loopback 名，否则 R7 会先把请求拒掉（TestClient 默认 Host=`testclient`）。
    """
    from services import api

    docs = {RUN_ID: SimpleNamespace(run_dir=str(run_dir))}
    manager = SimpleNamespace(docs=docs,
                              _progress=lambda _run_id: SimpleNamespace(read=lambda: []))
    monkeypatch.setattr(api, "_manager", lambda: manager)
    # 不跟随重定向：反代自己的 303（token → cookie 交换）与上游 302 都要能观察到原样响应
    return TestClient(api.app, base_url=BOARD, follow_redirects=False)


# ================================================================ R1–R8：请求面拒绝


def test_r01_literal_dotdot_segment_rejected(client: TestClient, run_dir: Path) -> None:
    """R1：字面 `..` 段直接拒绝；请求不得打到上游。

    路由层用 ASGI scope 直喂（httpx 会把字面 `..` 在客户端就归一化掉，那样测的是 httpx）；
    线上真实客户端可以发出这种请求，所以判据必须在服务端。
    """
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path(f"a/../b", f"/instance/{RUN_ID}/{NODE}/1/a/../b")
    assert caught.value.rule == "R1"

    status, headers, body = _asgi_call(f"/instance/{RUN_ID}/{NODE}/1/a/../b",
                                       f"/instance/{RUN_ID}/{NODE}/1/a/../b")
    assert status == 400, body
    assert headers["x-instance-proxy"] == "rejected"
    assert json.loads(body)["detail"]["rule"] == "R1"


def test_r02_percent_encoded_dotdot_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R2：一次编码的 `..`（`%2e%2e`）解码后拒绝。"""
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path(f"../../etc", f"/instance/{RUN_ID}/{NODE}/1/%2e%2e/%2e%2e/etc")
    assert caught.value.rule == "R2"

    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/%2e%2e/%2e%2e/etc")
    assert response.status_code == 400, response.text
    assert response.headers["x-instance-proxy"] == "rejected"
    assert response.json()["detail"]["rule"] == "R2"
    assert not upstream.calls, "被拒的请求不得转发到上游"


def test_r03_double_encoded_dotdot_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R3：双编码（`%252e%252e`）再解一次同样见 `..` ⇒ 拒绝。

    纯函数是唯一能稳定区分 R2/R3 的一层：路由层经 TestClient 二次解码后落在 R1/R2/R3 之一，
    所以路由断言只要求"拒绝了、没转发"。
    """
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path("%2e%2e/x", f"/instance/{RUN_ID}/{NODE}/1/%252e%252e/x")
    assert caught.value.rule == "R3"

    # 线上形态：uvicorn 把 `%252e%252e` 只解一次 ⇒ path="%2e%2e/x"、raw_path 保原文
    status, headers, body = _asgi_call(f"/instance/{RUN_ID}/{NODE}/1/%2e%2e/x",
                                       f"/instance/{RUN_ID}/{NODE}/1/%252e%252e/x")
    assert status == 400, body
    assert json.loads(body)["detail"]["rule"] == "R3"

    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/%252e%252e/x")
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["rule"] in {"R1", "R2", "R3"}
    assert not upstream.calls


def test_r04_encoded_slash_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R4：编码的 `/`（`%2f`/`%2F`）会改变段边界 ⇒ 拒绝（看 raw_path，不看已解码 path）。"""
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path("a/b", f"/instance/{RUN_ID}/{NODE}/1/a%2Fb")
    assert caught.value.rule == "R4"

    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/a%2Fb")
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["rule"] == "R4"
    assert not upstream.calls


def test_r05_absolute_uri_and_scheme_relative_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R5：绝对 URI / 协议相对 / authority 位含 `@` ⇒ 拒绝。"""
    for path, raw in [
        ("/etc/passwd", f"/instance/{RUN_ID}/{NODE}/1//etc/passwd"),
        ("//evil.example/x", f"/instance/{RUN_ID}/{NODE}/1///evil.example/x"),
        ("http://evil.example/x", f"/instance/{RUN_ID}/{NODE}/1/http://evil.example/x"),
        ("user@evil.example/x", f"/instance/{RUN_ID}/{NODE}/1/user@evil.example/x"),
    ]:
        with pytest.raises(instance_proxy.Rejected) as caught:
            instance_proxy.validate_path(path, raw)
        assert caught.value.rule == "R5", (path, raw)

    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/http://evil.example/x")
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["rule"] == "R5"
    assert not upstream.calls


def test_r06_control_chars_and_backslash_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R6：控制字符（含 NUL —— uvicorn 实测 `%00` 会变成真 NUL）与 `\\` ⇒ 拒绝。"""
    for bad in ("a\x00b", "a\x1fb", "a\x7fb", "a\\b"):
        with pytest.raises(instance_proxy.Rejected) as caught:
            instance_proxy.validate_path(bad, f"/instance/{RUN_ID}/{NODE}/1/{bad}")
        assert caught.value.rule == "R6", repr(bad)

    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/a%00b")
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["rule"] == "R6"
    assert not upstream.calls


def test_r07_host_must_be_loopback(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R7：`Host` 只认本服务 loopback 名（可带端口）；其余一律 400，且不转发。"""
    for good in ("127.0.0.1", "127.0.0.1:8099", "localhost:8099", "[::1]:8099", "LOCALHOST"):
        assert instance_proxy.validate_host(good) == good
    for bad in ("evil.example", "127.0.0.1.evil.example", "127.0.0.1:abc",
                "127.0.0.1:99999", "127.0.0.1:0", "", " 127.0.0.1", "localhost:8099/x"):
        with pytest.raises(instance_proxy.Rejected) as caught:
            instance_proxy.validate_host(bad)
        assert caught.value.rule == "R7", bad

    write_instance(run_dir, port=upstream.port)
    rejected = client.get(f"/instance/{RUN_ID}/{NODE}/1/", headers={"Host": "evil.example"})
    assert rejected.status_code == 400, rejected.text
    assert rejected.json()["detail"]["rule"] == "R7"
    assert not upstream.calls

    # 合法 loopback Host 照常转发（证明 R7 不是把所有请求都拒了）
    ok = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert ok.status_code == 200, ok.text
    assert upstream.last()["headers"]["host"] == upstream.authority


def test_r08_oversized_path_or_query_rejected(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R8：path > 2048 或 query > 4096 ⇒ 拒绝。"""
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path("a" * (instance_proxy.MAX_PATH_LEN + 1), "/instance/x")
    assert caught.value.rule == "R8"
    # P2-4：R8 也量**原始编码**长度（否则长编码串可绕过"path>2048"）
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_path("a", "/instance/" + "a" * instance_proxy.MAX_PATH_LEN)
    assert caught.value.rule == "R8"
    with pytest.raises(instance_proxy.Rejected) as caught:
        instance_proxy.validate_query("a=" + "b" * instance_proxy.MAX_QUERY_LEN)
    assert caught.value.rule == "R8"

    write_instance(run_dir, port=upstream.port)
    long_path = client.get(f"/instance/{RUN_ID}/{NODE}/1/" + "a" * 5000)
    assert long_path.status_code == 400, long_path.text
    long_query = client.get(f"/instance/{RUN_ID}/{NODE}/1/?q=" + "b" * 5000)
    assert long_query.status_code == 400, long_query.text
    assert not upstream.calls


def test_rejected_response_negotiates_html(client: TestClient, run_dir: Path) -> None:
    """拒绝态同样走内容协商：iframe 导航拿到 HTML 而不是 JSON 裸文本。"""
    write_instance(run_dir, port=_free_port())
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/%2e%2e/x",
                          headers={"Accept": "text/html,application/xhtml+xml"})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "R2" in response.text


# ================================================================ R9–R13：受管目标与不可用态


def test_r09_non_loopback_or_bad_port_target_unavailable(client: TestClient, run_dir: Path) -> None:
    """R9：元数据目标非 loopback / 端口非法 ⇒ 显式不可用（不静默转发）。"""
    cases = [
        ({"host": "10.0.0.5", "port": 8080}, "target_not_loopback"),
        ({"host": "0.0.0.0", "port": 8080}, "target_not_loopback"),
        ({"host": "127.0.0.1", "port": 0}, "target_invalid"),
        ({"host": "127.0.0.1", "port": 70000}, "target_invalid"),
        ({"host": "127.0.0.1", "port": "abc"}, "target_invalid"),
        ({"host": "127.0.0.1", "port": True}, "target_invalid"),
    ]
    for spec, reason in cases:
        write_instance(run_dir, **spec)  # type: ignore[arg-type]
        response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
        assert response.status_code == 503, (spec, response.text)
        assert response.headers["x-instance-proxy"] == "unavailable"
        assert response.json()["reason"] == reason, (spec, response.text)
        assert response.json()["state"] == "unavailable"


def test_r10_missing_or_mismatched_metadata_unavailable(client: TestClient, run_dir: Path) -> None:
    """R10：元数据缺失 / node 或 attempt 不匹配 / 坏 JSON ⇒ 显式 `target_missing`/`target_invalid`。"""
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 503
    assert response.json()["reason"] == "target_missing"

    write_instance(run_dir, port=8080, node="N6")
    assert client.get(f"/instance/{RUN_ID}/{NODE}/1/").json()["reason"] == "target_missing"

    write_instance(run_dir, port=8080, attempt=2)
    assert client.get(f"/instance/{RUN_ID}/{NODE}/1/").json()["reason"] == "target_missing"

    (run_dir / "agent_instance.json").write_text("{not json", encoding="utf-8")
    assert client.get(f"/instance/{RUN_ID}/{NODE}/1/").json()["reason"] == "target_invalid"


def test_r11_unreachable_upstream_unavailable(client: TestClient, run_dir: Path) -> None:
    """R11：上游连接拒绝 ⇒ 503 `upstream_unreachable`（不是 500 空白）。"""
    write_instance(run_dir, port=_free_port())
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 503, response.text
    assert response.json()["reason"] == "upstream_unreachable"
    assert response.headers["x-instance-proxy"] == "unavailable"


def test_r12_upstream_timeout_unavailable(
    client: TestClient, run_dir: Path, upstream: FakeUpstream, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12：上游超时 ⇒ 503 `upstream_timeout`（常量可注入，测试不空转 15 s）。"""
    monkeypatch.setattr(instance_proxy, "READ_TIMEOUT_S", 0.15)
    upstream.delay_s = 0.6
    write_instance(run_dir, port=upstream.port)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 503, response.text
    assert response.json()["reason"] == "upstream_timeout"


def test_r13_upstream_auth_failures_unavailable(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """R13：上游 401/403 ⇒ 503 `upstream_auth`；不得把上游的鉴权体当页面转给浏览器。"""
    write_instance(run_dir, port=upstream.port)
    upstream.body = b"<html>upstream login wall</html>"
    for status in (401, 403):
        upstream.status = status
        response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
        assert response.status_code == 503, response.text
        assert response.json()["reason"] == "upstream_auth"
        assert "upstream login wall" not in response.text


def test_unavailable_html_vs_json_negotiation(client: TestClient, run_dir: Path) -> None:
    """§5.5：`Accept: text/html`（iframe 导航）⇒ HTML 错误页；否则 JSON。两种都不回显 token。"""
    write_instance(run_dir, port=_free_port(), token=SEKRET)

    html = client.get(f"/instance/{RUN_ID}/{NODE}/1/", headers={"Accept": "text/html"})
    assert html.status_code == 503
    assert html.headers["content-type"].startswith("text/html")
    assert "不可用" in html.text and "在新标签页打开" in html.text
    assert SEKRET not in html.text

    payload = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert payload.status_code == 503
    assert payload.json() == {
        "available": False, "state": "unavailable", "reason": "upstream_unreachable",
        "url": None, "embed": "new_tab_only", "authority": "projection",
    }
    assert SEKRET not in payload.text


# ================================================================ R14–R20：转发与头改写


def test_r14_client_target_params_dropped(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R14：客户端 `?token=`/`?url=`/`?port=`（任意大小写）一律丢弃，不进上游；其余 query 保留。"""
    with pytest.raises(instance_proxy.Rejected):
        instance_proxy.validate_query("q=" + "x" * instance_proxy.MAX_QUERY_LEN)
    assert instance_proxy.validate_query("keep=1&token=CLIENT&Url=http%3A%2F%2Fevil.example&PORT=1234&b=2") == "keep=1&b=2"

    write_instance(run_dir, port=upstream.port, token=SEKRET)
    response = client.get(
        f"/instance/{RUN_ID}/{NODE}/1/?keep=1&token=CLIENT&url=http://evil.example/&port=1234",
        headers={"Cookie": "dsh-auth--x=v1.payload.sig"},
    )
    assert response.status_code == 200, response.text
    path = upstream.last()["path"]
    assert path == "/?keep=1", path
    assert "CLIENT" not in path and "evil.example" not in path and "1234" not in path


def test_r15_upstream_location_rewritten_and_token_stripped(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R15：上游 `Location` 指向上游绝对地址/带 token ⇒ 改写为同源前缀路径并剥离 token。"""
    assert instance_proxy.rewrite_location(
        "http://127.0.0.1:18710/next?token=SEKRET&a=1",
        target=instance_proxy.InstanceTarget(host="127.0.0.1", port=18710, token=SEKRET, node=NODE, attempt=1),
        prefix_root=PREFIX,
        injected_token=None,
    ) == PREFIX + "next?a=1"
    assert instance_proxy.rewrite_location(
        "./",
        target=instance_proxy.InstanceTarget(host="127.0.0.1", port=18710, token=None, node=NODE, attempt=1),
        prefix_root=PREFIX,
        injected_token=None,
    ) == PREFIX

    write_instance(run_dir, port=upstream.port, token=SEKRET)
    upstream.status = 303
    upstream.body = b""
    upstream.headers = [
        ("Location", f"http://{upstream.authority}/next?token={SEKRET}&a=1"),
        ("Set-Cookie", "dsh-auth--x=v1.payload.sig; Path=/; HttpOnly; SameSite=Strict"),
    ]
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/",
                          headers={"Cookie": "dsh-auth--x=v1.payload.sig"})
    assert response.status_code == 303, response.text
    assert response.headers["location"] == PREFIX + "next?a=1", response.headers["location"]
    assert SEKRET not in str(dict(response.headers))


def test_r16_forwarded_and_proxy_headers_not_forwarded(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R16：`Forwarded`/`X-Forwarded-*`/`Via`/`Proxy-*` 与 hop-by-hop 头一律不转发。"""
    write_instance(run_dir, port=upstream.port)
    client.get(
        f"/instance/{RUN_ID}/{NODE}/1/",
        headers={
            "Forwarded": "for=1.2.3.4;proto=http",
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": "1.2.3.4",
            "Via": "1.1 evil.example",
            "Proxy-Connection": "keep-alive",
            "Proxy-Authorization": "Basic Zm9vOmJhcg==",
            "Connection": "keep-alive",
            "Keep-Alive": "timeout=5",
            "TE": "trailers",
            "Trailer": "X-Trailer",
            "Authorization": "Bearer board-secret",
            "Accept-Encoding": "br",
        },
    )
    seen = upstream.last()["headers"]
    for name in ("forwarded", "x-forwarded-host", "x-forwarded-proto", "x-forwarded-for",
                 "via", "proxy-connection", "proxy-authorization", "keep-alive",
                 "te", "trailer", "authorization"):
        assert name not in seen, f"{name} 不应转发：{seen}"
    # 表示层协商归本层：客户端 Accept-Encoding 不得原样转发（否则丢掉 Content-Encoding 后
    # 浏览器会收到"标称 identity 的压缩字节"）；上游看到的是 HTTP 客户端自己的协商值。
    assert seen.get("accept-encoding") != "br", seen


def test_r17_set_cookie_domain_dropped_and_path_scoped(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R17：`Set-Cookie` 删 `Domain`、`Path` 收到实例前缀；其余属性逐字保留。"""
    write_instance(run_dir, port=upstream.port)
    upstream.headers = [
        ("Set-Cookie",
         "dsh-auth--abc=v1.payload.sig; Domain=evil.example; Path=/; Max-Age=2592000; "
         "HttpOnly; SameSite=Strict"),
    ]
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1, cookies
    cookie = cookies[0]
    assert "domain" not in cookie.lower(), cookie
    assert f"Path={PREFIX}" in cookie, cookie
    assert "Max-Age=2592000" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie


def test_r18_multiple_csp_headers_each_narrowed(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R18：上游多个 CSP 头逐个处理：只把 `frame-ancestors` 换成 `'self'`，其余指令逐字保留。"""
    write_instance(run_dir, port=upstream.port)
    first = "default-src 'self'; frame-ancestors https://evil.example"
    second = "script-src 'self'; frame-ancestors 'none'; object-src 'none'"
    upstream.headers = [("Content-Type", "text/html; charset=utf-8"),
                        ("Content-Security-Policy", first),
                        ("Content-Security-Policy", second)]
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    policies = response.headers.get_list("content-security-policy")
    assert len(policies) == 2, policies
    assert policies[0] == "default-src 'self'; frame-ancestors 'self'", policies[0]
    assert policies[1] == "script-src 'self'; frame-ancestors 'self'; object-src 'none'", policies[1]


def test_r18_csp_without_frame_ancestors_untouched(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R18 反向：没有 `frame-ancestors` 的 CSP 不得被改，也不得凭空新增 CSP。"""
    write_instance(run_dir, port=upstream.port)
    original = "default-src 'self'; img-src data:"
    upstream.headers = [("Content-Security-Policy", original)]
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.headers.get_list("content-security-policy") == [original]
    assert instance_proxy.narrow_csp(original) == original


def test_r19_upstream_5xx_passed_through_with_reason(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R19：上游 5xx ⇒ 状态码透传，但加 `X-Instance-Proxy: unavailable` + `upstream_error`。"""
    write_instance(run_dir, port=upstream.port)
    upstream.status = 500
    upstream.body = b"<html>upstream boom</html>"
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 500, response.text
    assert response.headers["x-instance-proxy"] == "unavailable"
    assert response.headers["x-instance-proxy-reason"] == "upstream_error"
    assert "upstream boom" in response.text


def test_r20_x_frame_options_always_dropped(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """R20：上游 `X-Frame-Options`（有值/缺失）一律不向下透传（同源 iframe 需要）。"""
    write_instance(run_dir, port=upstream.port)
    for value in ("DENY", "SAMEORIGIN", "ALLOW-FROM https://evil.example"):
        upstream.headers = [("Content-Type", "text/html; charset=utf-8"),
                            ("X-Frame-Options", value)]
        response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
        assert "x-frame-options" not in response.headers, value

    upstream.headers = [("Content-Type", "text/html; charset=utf-8")]
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert "x-frame-options" not in response.headers


# ================================================================ OBS-05：同源语义（决定性命中）


def test_obs05_post_api_forwarded_with_same_origin_rewrite(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """`OBS-05` 决定性证据：POST `/api/*` 经反代**真到达**假上游，且同源语义被恢复。

    断言四件事：① method 保留；② `Origin`/`Referer` 已改写为上游 authority；
    ③ `Sec-Fetch-Site` 改写为 `same-origin`；④ 客户端 `?token=`/`?url=` 没进上游。
    （DSH Web 的 `/api` 会按 Origin/`sec-fetch-site` 围栏回 403 —— P8 实测；不改写就"能开不能点"。）
    """
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    upstream.headers = [("Content-Type", "application/json")]
    upstream.body = b'{"ok":true}'
    response = client.post(
        f"/instance/{RUN_ID}/{NODE}/1/api/session/list?limit=5&token=CLIENT&url=http://evil.example",
        headers={
            "Origin": BOARD,
            "Referer": f"{BOARD}/instance/{RUN_ID}/{NODE}/1/",
            "Sec-Fetch-Site": "cross-site",
            "Content-Type": "application/json",
            "Cookie": "dsh-auth--abc=v2.payload.sig",
        },
        content=b'{"cursor":"x"}',
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}

    call = upstream.last()
    assert call["method"] == "POST"
    assert call["path"] == "/api/session/list?limit=5", call["path"]
    assert call["headers"]["origin"] == f"http://{upstream.authority}", call["headers"].get("origin")
    assert call["headers"]["referer"].startswith(f"http://{upstream.authority}/"), call["headers"].get("referer")
    assert call["headers"]["sec-fetch-site"] == "same-origin"
    assert call["body"] == b'{"cursor":"x"}'
    assert SEKRET not in call["path"]


def test_obs05_options_forwarded(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """OPTIONS 也原样透传（CORS 预检/liveness 探测不该被反代自己吃掉）。"""
    write_instance(run_dir, port=upstream.port)
    upstream.status = 204
    upstream.headers = [("Allow", "GET, POST")]
    upstream.body = b""
    response = client.options(f"/instance/{RUN_ID}/{NODE}/1/api/session/list")
    assert response.status_code == 204, response.text
    assert upstream.last()["method"] == "OPTIONS"


def test_connect_trace_and_upgrade_rejected_405(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """§5.1：`CONNECT`/`TRACE`/WebSocket 升级一律 405（升级支持是 §9-2 未决）。"""
    write_instance(run_dir, port=upstream.port)
    for method in ("CONNECT", "TRACE"):
        response = client.request(method, f"/instance/{RUN_ID}/{NODE}/1/")
        assert response.status_code == 405, (method, response.status_code)
    upgrade = client.get(f"/instance/{RUN_ID}/{NODE}/1/",
                         headers={"Upgrade": "websocket", "Connection": "Upgrade"})
    assert upgrade.status_code == 405, upgrade.text
    assert not upstream.calls


# ================================================================ 凭据：token 注入但不回显


def test_managed_token_injected_only_when_no_cookie(
    client: TestClient, run_dir: Path, upstream: FakeUpstream, caplog: pytest.LogCaptureFixture
) -> None:
    """§5.4：元数据有 token 且请求无 cookie ⇒ 上游 query 带 `token=`；响应/日志一律不回显。"""
    caplog.set_level(logging.DEBUG)
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    upstream.status = 303
    upstream.body = b""
    upstream.headers = [("Location", "./"),
                        ("Set-Cookie", "dsh-auth--abc=v1.payload.sig; Path=/; HttpOnly; SameSite=Strict")]

    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/", headers={"Accept": "*/*"})
    assert response.status_code == 303, response.text
    assert upstream.last()["path"] == f"/?token={SEKRET}"
    assert SEKRET not in response.text
    assert SEKRET not in str(dict(response.headers))
    assert SEKRET not in caplog.text

    upstream.calls.clear()
    again = client.get(f"/instance/{RUN_ID}/{NODE}/1/",
                       headers={"Cookie": "dsh-auth--abc=v1.payload.sig"})
    assert again.status_code == 303
    assert "token=" not in upstream.last()["path"], upstream.last()["path"]


def test_token_never_echoed_in_unavailable_errors_and_logs(
    client: TestClient, run_dir: Path, upstream: FakeUpstream, caplog: pytest.LogCaptureFixture
) -> None:
    """§5.4/§5.5：token 不出现在错误体、响应头、JSON、日志里（上游 401 路径同样）。"""
    caplog.set_level(logging.DEBUG)
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    upstream.status = 401
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 503
    assert SEKRET not in response.text
    assert SEKRET not in str(dict(response.headers))
    assert SEKRET not in response.headers.get("x-instance-proxy-reason", "")
    assert SEKRET not in caplog.text


def test_unreachable_error_does_not_echo_token(client: TestClient, run_dir: Path) -> None:
    """不可达态的错误体里也不得出现 token（连"上游 URL"都不拼进错误体）。"""
    write_instance(run_dir, port=_free_port(), token=SEKRET)
    for accept in ("*/*", "text/html"):
        response = client.get(f"/instance/{RUN_ID}/{NODE}/1/", headers={"Accept": accept})
        assert response.status_code == 503
        assert SEKRET not in response.text


# ================================================================ 可用性端点 / 会话副本端点


def test_availability_endpoint_ready(client: TestClient, run_dir: Path, upstream: FakeUpstream) -> None:
    """§6.1：可用时给出 url/embed；**不返回** token 与端口之外的宿主细节。"""
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/instance").json()
    assert payload == {
        "available": True, "state": "ready", "reason": None,
        "url": PREFIX, "embed": "iframe", "authority": "projection", "attempt": 1,
    }
    assert SEKRET not in json.dumps(payload)


def test_availability_endpoint_unavailable(client: TestClient, run_dir: Path) -> None:
    """§6.1：缺元数据 ⇒ `available=false` + 可判 reason + `embed=new_tab_only`（降级线用）。"""
    payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/instance").json()
    assert payload == {
        "available": False, "state": "unavailable", "reason": "target_missing",
        "url": None, "embed": "new_tab_only", "authority": "projection", "attempt": None,
    }


def test_session_copy_unavailable_reason(client: TestClient, run_dir: Path) -> None:
    """§6.2：会话副本不可用必须显式说原因（当前无 Host 落账的 session log ⇒ `session_log_missing`）。"""
    payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy").json()
    assert payload == {
        "available": False, "reason": "session_metadata_missing", "kind": None,
        "facts": None, "bytes": None, "truncated": False, "attempt": None,
    }


def _write_session_log(run_dir: Path) -> Path:
    """造一份真 zstd session log（真跑 `zstd -dc` + `parse_session_log_lines`，不 mock 解码）。"""
    plain = run_dir / "session.jsonl"
    plain.write_text(
        '{"type":"session","id":"s-1"}\n'
        '{"type":"compaction/summary","time":1770000000,"seq":1,'
        '"data":{"compactionId":"c-1","shadowedTokenCount":123}}\n',
        encoding="utf-8",
    )
    compressed = run_dir / "session.jsonl.zst"
    subprocess.run(["zstd", "-q", "-f", str(plain), "-o", str(compressed)], check=True)
    plain.unlink()
    return compressed


def test_session_copy_returns_session_log_facts(
    client: TestClient, run_dir: Path
) -> None:
    """§6.2 修正：只返回 **session log 解析事实**（`kind="session_log_facts"`），不声称原文。"""
    if shutil.which("zstd") is None:
        pytest.skip("zstd 不可用（环境缺件，不是代码缺陷）")
    log_path = _write_session_log(run_dir)
    write_instance(run_dir, port=_free_port(), session_log=log_path.name)

    payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy").json()
    assert payload["available"] is True, payload
    assert payload["kind"] == "session_log_facts"
    assert payload["reason"] is None
    assert payload["truncated"] is False
    assert payload["bytes"] and payload["bytes"] > 0
    facts = payload["facts"]
    assert facts["availability"] == "ok"
    assert facts["count"] == 1
    assert facts["records"] == [{"compaction_id": "c-1", "time": 1770000000,
                                 "seq": 1, "shadowed_token_count": 123}]
    assert facts["start_count"] == 0 and facts["end_count"] == 0
    assert payload["attempt"] == 1
    assert "content" not in payload, "不得返回未经验证的会话原文"


def test_session_copy_rejects_absolute_and_escaping_paths(
    client: TestClient, run_dir: Path, tmp_path: Path
) -> None:
    """§5.2：`session_log` 只允许相对 run_dir；绝对路径/越界/符号链接 ⇒ `session_log_invalid`。"""
    outside = tmp_path / "outside.log"
    outside.write_text("x", encoding="utf-8")

    for ref in (str(outside), "../outside.log", "sub/../../outside.log"):
        write_instance(run_dir, port=_free_port(), session_log=ref)
        payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy").json()
        assert payload == {"available": False, "reason": "session_log_invalid",
                           "kind": None, "facts": None, "bytes": None,
                           "truncated": False, "attempt": 1}, (ref, payload)

    # 符号链接：指到 run_dir **外面**时靠越界判据也会拒；指到里面时必须靠"禁符号链接"判据。
    inside = run_dir / "inside.log"
    inside.write_text("x", encoding="utf-8")
    for link, target in ((run_dir / "link-out.log", outside), (run_dir / "link-in.log", inside)):
        link.symlink_to(target)
        write_instance(run_dir, port=_free_port(), session_log=link.name)
        payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy").json()
        assert payload["reason"] == "session_log_invalid", (link.name, payload)


def test_session_copy_missing_log_file_is_explicit(
    client: TestClient, run_dir: Path
) -> None:
    """相对路径合法但文件不存在 ⇒ `session_log_unavailable`（不是 500、不伪造事实）。"""
    write_instance(run_dir, port=_free_port(), session_log="not-there.jsonl.zst")
    payload = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy").json()
    assert payload["available"] is False
    assert payload["reason"] == "session_log_unavailable"
    assert payload["attempt"] == 1


def test_unknown_run_and_node_are_404(client: TestClient, run_dir: Path) -> None:
    """run/node 不存在沿用既有 agents 端点口径（404），不是空白 500。"""
    assert client.get(f"/instance/RUN-NOT-EXIST/{NODE}/1/").status_code == 404
    assert client.get(f"/instance/{RUN_ID}/N99/1/").status_code == 404
    assert client.get(f"/api/runs/{RUN_ID}/agents/N99/instance").status_code == 404


# ================================================================ 接线与不回归


def test_static_mount_and_existing_routes_not_shadowed(client: TestClient) -> None:
    """新路由必须挂在 `app.mount("/", StaticFiles(...))` 之前：首页与既有 API 都不能被吞。"""
    index = client.get("/")
    assert index.status_code == 200
    assert "<!DOCTYPE html>" in index.text
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True


def test_proxy_never_writes_run_dir(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """§5.4：不写 run 目录（只读元数据；转发后目录内容与 mtime 不变）。"""
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    before = {p.name: p.stat().st_mtime_ns for p in run_dir.rglob("*")}
    assert client.get(f"/instance/{RUN_ID}/{NODE}/1/").status_code == 200
    after = {p.name: p.stat().st_mtime_ns for p in run_dir.rglob("*")}
    assert after == before


def test_only_managed_metadata_can_choose_target(
    client: TestClient, run_dir: Path, upstream: FakeUpstream
) -> None:
    """§5.2：客户端给的 `host/port/url`（query 与请求头）不能改变目标 —— 目标只来自元数据。"""
    write_instance(run_dir, port=upstream.port)
    dead_port = _free_port()
    response = client.get(
        f"/instance/{RUN_ID}/{NODE}/1/?host=127.0.0.1&port={dead_port}&url=http://127.0.0.1:{dead_port}/",
        headers={"X-Target-Host": "127.0.0.1", "X-Target-Port": str(dead_port)},
    )
    assert response.status_code == 200, response.text
    assert upstream.calls, "目标必须仍是被管元数据里的上游"
    assert "port=" not in upstream.last()["path"] and "host=" not in upstream.last()["path"]


# ================================================================ api.py 接线：窗口并入投影/解释面


def _seal_window_request(run_dir: Path) -> None:
    """造一条最小 committed 请求记录（`agent_control.read_view` 的可读输入）。"""
    from host import agent_memory as AM

    attempt_dir = run_dir / "agent_calls" / NODE / "attempt-000001"
    attempt_dir.mkdir(parents=True)
    AM.seal_record(attempt_dir / "request.json", {
        "run_id": RUN_ID, "node": NODE, "attempt": 1,
        "model": "standin", "cycle": 1, "instruct": "接线用例",
    })


def test_agent_window_carries_progress_and_explain(
    client: TestClient, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`_agent_window_view` 接入 `agent_view.window_annotation`：窗口 GET 多两块，既有字段不动。

    契约字段见 SPEC-REV-16 §2.1（progress）与 §6.3（explain）；`now` 只从 `LOOP_NOW`
    注入入口取，`silence_s` 因此可判（不是墙钟）。
    """
    from datetime import datetime

    from services import api

    _seal_window_request(run_dir)
    stamp = "2026-10-28T00:00:00+08:00"
    monkeypatch.setenv("LOOP_NOW", stamp)
    now = datetime.fromisoformat(stamp).timestamp()
    events = [{"seq": 1, "node": NODE, "kind": "node_started", "status": "ok",
               "ts": now - 1800}]
    monkeypatch.setattr(api, "_manager", lambda: SimpleNamespace(
        docs={RUN_ID: SimpleNamespace(run_dir=str(run_dir))},
        _progress=lambda _run_id: SimpleNamespace(read=lambda: events)))

    response = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}")
    assert response.status_code == 200, response.text
    payload = response.json()
    # 既有窗口字段不回归（§8：新增键，不改既有响应字段）
    for kept in ("node", "request", "events", "capabilities", "context_budget"):
        assert kept in payload, kept

    progress = payload["progress"]
    assert set(progress) == {
        "identity", "state", "current_action", "last_event", "last_tool", "last_error",
        "elapsed_s", "silence_s", "no_progress", "compaction", "execution", "authority",
    }, sorted(progress)
    assert progress["authority"] == "projection"
    assert progress["identity"]["run_id"] == RUN_ID
    assert progress["identity"]["node"] == NODE
    assert progress["identity"]["attempt"] == 1
    # 注入 now ⇒ 静默时长可判（1800 s），阈值来自契约常量
    assert progress["silence_s"] == 1800
    assert progress["no_progress"]["threshold_s"] == 600
    assert progress["no_progress"]["state"] == "warn"
    assert progress["no_progress"]["silence_s"] == 1800

    explain = payload["explain"]
    assert set(explain) == {"instructions", "scope_expiry", "working_memory", "experiences"}
    assert explain["scope_expiry"]["determined"] is False
    assert explain["scope_expiry"]["state"] == "unknown"


def test_agent_window_progress_uses_injected_now_not_wall_clock(
    client: TestClient, run_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """同一事件、只改 `LOOP_NOW` ⇒ `silence_s` 随之变：证明判据走注入入口（红线 7）。"""
    from datetime import datetime

    from services import api

    _seal_window_request(run_dir)
    base = datetime.fromisoformat("2026-10-28T00:00:00+08:00").timestamp()
    events = [{"seq": 1, "node": NODE, "kind": "node_started", "status": "ok",
               "ts": base - 300}]

    def _client_for(stamp: str) -> dict:
        monkeypatch.setenv("LOOP_NOW", stamp)
        monkeypatch.setattr(api, "_manager", lambda: SimpleNamespace(
            docs={RUN_ID: SimpleNamespace(run_dir=str(run_dir))},
            _progress=lambda _run_id: SimpleNamespace(read=lambda: events)))
        reply = client.get(f"/api/runs/{RUN_ID}/agents/{NODE}")
        assert reply.status_code == 200, reply.text
        return reply.json()["progress"]

    early = _client_for("2026-10-28T00:05:00+08:00")
    assert early["silence_s"] == 600
    assert early["no_progress"]["state"] == "warn"
    later = _client_for("2026-10-28T00:01:00+08:00")
    assert later["silence_s"] == 360
    assert later["no_progress"]["state"] == "ok"


# ================================================================ 独立复核处置（P1-1 / P2-1 / P2-3 / P2-4）


def test_p1_availability_scoped_to_node_and_attempt(
    client: TestClient, run_dir: Path
) -> None:
    """P1-1：可用性按 **(node, attempt)** 粒度；省略 attempt 由受管元数据决定（不得钉死 1）。"""
    write_instance(run_dir, port=_free_port(), attempt=2)
    base = f"/api/runs/{RUN_ID}/agents/{NODE}/instance"

    two = client.get(base, params={"attempt": 2}).json()
    assert two["available"] is True and two["reason"] is None
    assert two["attempt"] == 2
    assert two["url"] == f"/instance/{RUN_ID}/{NODE}/2/"

    one = client.get(base, params={"attempt": 1}).json()
    assert one["available"] is False
    assert one["reason"] == "target_missing"
    assert one["attempt"] == 1

    default = client.get(base).json()
    assert default["available"] is True, default
    assert default["attempt"] == 2, "省略 attempt 时必须回显元数据声明的 attempt"
    assert default["url"].endswith("/2/"), default["url"]

    # 声明是别的节点 ⇒ 归属不符（target_missing），不拿他人实例冒充
    write_instance(run_dir, port=_free_port(), node="N6", attempt=1)
    other = client.get(base, params={"attempt": 1}).json()
    assert other["available"] is False and other["reason"] == "target_missing"


def test_p2_session_copy_scoped_to_node_and_attempt(
    client: TestClient, run_dir: Path
) -> None:
    """P2-1：会话副本归属校验 —— 任意节点/attempt 窗口不能导出别人的会话事实。"""
    write_instance(run_dir, port=_free_port(), attempt=2)
    base = f"/api/runs/{RUN_ID}/agents/{NODE}/session-copy"

    ok = client.get(base, params={"attempt": 2}).json()
    assert ok["reason"] == "session_log_missing" and ok["attempt"] == 2, ok

    wrong_attempt = client.get(base, params={"attempt": 1}).json()
    assert wrong_attempt == {
        "available": False, "reason": "session_owner_mismatch", "kind": None,
        "facts": None, "bytes": None, "truncated": False, "attempt": 1,
    }, wrong_attempt

    default = client.get(base).json()
    assert default["reason"] == "session_log_missing" and default["attempt"] == 2, default

    write_instance(run_dir, port=_free_port(), node="N6", attempt=2)
    other = client.get(base, params={"attempt": 2}).json()
    assert other["reason"] == "session_owner_mismatch", other


def test_p2_httpx_info_logging_never_prints_managed_token(
    client: TestClient, run_dir: Path, upstream: FakeUpstream,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """P2-3：httpx 在 INFO 会打印完整 URL（受管 token 在 query 里）⇒ 显式压到 WARNING。

    两半都要测：① import 时就显式配置了 httpx/httpcore（不能靠第三方库碰巧设过级别）；
    ② 真实请求在 INFO 级别下日志里也没有 token。
    """
    # ① 幂等且可恢复：别人把级别放开后，我们的函数仍把它压回 WARNING
    logging.getLogger("httpx").setLevel(logging.INFO)   # 模拟第三方库放开
    instance_proxy.silence_http_client_logging()
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING

    # ② 真实请求：管理 token 真的注入到上游 query，但日志（含 INFO）里没有它
    caplog.set_level(logging.INFO)
    write_instance(run_dir, port=upstream.port, token=SEKRET)
    response = client.get(f"/instance/{RUN_ID}/{NODE}/1/")
    assert response.status_code == 200, response.text
    assert upstream.last()["path"].endswith(f"token={SEKRET}"), upstream.last()["path"]
    assert SEKRET not in caplog.text


def test_p2_import_time_silencing_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """P2-3：`import services.instance_proxy` 本身就要配置 httpx/httpcore（不是只提供函数）。"""
    import importlib

    seen: list[str | None] = []
    real_get_logger = logging.getLogger

    def spy(name: str | None = None):  # noqa: ANN001 - 复刻 logging.getLogger 签名
        seen.append(name)
        return real_get_logger(name)

    monkeypatch.setattr(logging, "getLogger", spy)
    importlib.reload(instance_proxy)
    assert "httpx" in seen, f"import 时没有配置 httpx logger：{seen}"
    assert "httpcore" in seen, f"import 时没有配置 httpcore logger：{seen}"
