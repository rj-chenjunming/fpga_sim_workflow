"""S7c 接线后真机验证：Host 起实例 → 落账 → 看板同源反代整链（不调模型、不烧 token）。

验证清单（开工提示词 §4.3-3 / REV-16 §5–§6）：
① 可用性端点 `ready` 且 `url` 指向正确 attempt；
② iframe 目标页经反代可取回真实页面（`<base href="./">`、资源全相对）；
③ `/api` 不 403（带 cookie 的 POST RPC 200）；
④ cookie 由同源投递（`?token=` 首跳 303 + `Set-Cookie` 的 Path 收到实例前缀）；
⑤ token 不出现在日志/响应/错误页；
⑥ 实例停止后 ⇒ 显式 `unavailable: target_missing`（不连死端口）。

不启动真实浏览器（iframe 截图取证由 `s7c-proxy` 的 Playwright 探针单独完成，见证据档 §3）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

LOOP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LOOP))

from host import web_instance_ctl as C  # noqa: E402

RUN_ID = os.environ.get("S7C_RUN_ID", "RUN-20261029-103000")
NODE = "N6"
ATTEMPT = 1
WORKSPACE = Path(os.environ["LOOP_WORKSPACE"])
RUN_DIR = WORKSPACE / "runs" / RUN_ID
PORT = int(os.environ.get("S7C_DASH_PORT", "8199"))
BASE = f"http://127.0.0.1:{PORT}"
OUT = Path(__file__).resolve().parent


def _req(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None,
         follow: bool = False) -> tuple[int, dict, bytes]:
    request = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler() if follow else _NoRedirect())
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):  # noqa: D401 - 不跟随 302，要看首跳头
        return None


def _free_port() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _session_log_ref() -> str | None:
    attempt_dir = RUN_DIR / "agent_workspaces" / NODE / ("attempt-%06d" % ATTEMPT)
    logs = sorted((attempt_dir / "dsh-home" / "sessions").rglob("session.v4.jsonl.zstd"))
    if not logs:
        return None
    return logs[0].relative_to(RUN_DIR).as_posix()


def main() -> int:
    report: dict = {"run_id": RUN_ID, "node": NODE, "attempt": ATTEMPT}
    # 看板只索引 `runs/*/view.json`（RunManager._load_docs）。本次 run 由 S7a 探针直接建目录，
    # 没有完整编排台账 ⇒ 补一份**投影** doc 才能从看板读它（标注来源，不冒充编排产物）。
    view = RUN_DIR / "view.json"
    if not view.exists():
        from host import paths as PP
        view.write_text(json.dumps({
            "run_id": RUN_ID, "run_dir": str(RUN_DIR), "baseline": None, "mode": "real",
            "scenario": "happy", "status": "unknown",
            "created_at": PP.now_iso(), "updated_at": PP.now_iso(),
            "notes": ["S7c 真机验证用：目录由 S7a 探针直接创建（无完整编排台账）；"
                      "本 view.json 仅用于让看板索引进该 run。"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        report["view_doc_written"] = str(view)
    session_ref = _session_log_ref()
    facts = C.ensure(RUN_DIR, NODE, ATTEMPT, session_log=session_ref, enable=True)
    report["instance"] = facts
    token = json.loads((RUN_DIR / "agent_instance.json").read_text())["token"]
    report["token_len"] = len(token or "")
    report["tokens_echoed"] = []

    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.api:app", "--host", "127.0.0.1",
         "--port", str(PORT), "--log-level", "info"],
        cwd=str(LOOP), env={**os.environ, "LOOP_WORKSPACE": str(WORKSPACE)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log_lines: list[str] = []
    try:
        for _ in range(120):
            try:
                status, _h, _b = _req("GET", BASE + "/api/health")
                if status == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.25)
        else:
            raise SystemExit("看板未就绪")

        prefix = f"/instance/{RUN_ID}/{NODE}/{ATTEMPT}"
        # ① 可用性端点
        status, _h, body = _req("GET", f"{BASE}/api/runs/{RUN_ID}/agents/{NODE}/instance?attempt={ATTEMPT}")
        meta = json.loads(body)
        report["availability"] = {"status": status, "body": meta}
        assert status == 200 and meta["state"] == "ready", meta
        assert meta["url"] == prefix + "/" and meta["attempt"] == ATTEMPT, meta

        # ④ 首跳：?token= 交换 → 303 + cookie（token 被打回同源相对路径）
        target = f"{BASE}{prefix}/?token={token}"
        status, headers, body1 = _req("GET", target)
        set_cookie = headers.get("set-cookie", "")
        report["first_hop"] = {"status": status, "location": headers.get("location"),
                               "set_cookie_path_has_prefix": prefix + "/" in set_cookie,
                               "body_len": len(body1)}
        assert status in (302, 303), status
        loc = headers.get("location", "")
        assert "token=" not in loc, loc
        cookie = set_cookie.split(";")[0]

        # ② 带 cookie 取真实页面
        headers2 = {"Cookie": cookie}
        status, headers, page = _req("GET", f"{BASE}{prefix}/", headers=headers2)
        html = page.decode("utf-8", "replace")
        refs = [chunk.split("\"")[0] for chunk in html.split("href=\"")[1:]] + \
               [chunk.split("\"")[0] for chunk in html.split("src=\"")[1:]]
        absolute = [r for r in refs if r.startswith("/")]
        report["index"] = {"status": status, "bytes": len(page),
                           "has_base_dot": '<base href="./"' in html,
                           "absolute_refs": absolute[:5], "ref_count": len(refs)}
        assert status == 200 and '<base href="./"' in html, status
        assert not absolute, absolute

        # ③ /api 不 403（同源反代下带 cookie 的 POST RPC）
        status, headers, body3 = _req(
            "POST", f"{BASE}{prefix}/api/session/list",
            headers={"Cookie": cookie, "Content-Type": "application/json",
                     "Origin": BASE, "Referer": f"{BASE}{prefix}/"},
            data=b"{}")
        report["api_post"] = {"status": status, "body": body3.decode("utf-8", "replace")[:200]}
        assert status == 200, (status, body3[:200])

        # ⑤ token 零回显：扫描所有已收集的响应体/头
        blobs = [body1, page, body3, body]
        for name, value in list(meta.items()):
            blobs.append(str(value).encode())
        if token:
            report["tokens_echoed"] = [i for i, blob in enumerate(blobs)
                                       if token.encode() in blob]
            assert not report["tokens_echoed"], "token 出现在响应里"

        # 会话副本（session_log 接线）：只给解析事实
        status, _h, body4 = _req(
            "GET", f"{BASE}/api/runs/{RUN_ID}/agents/{NODE}/session-copy?attempt={ATTEMPT}")
        copy = json.loads(body4)
        report["session_copy"] = {"status": status, "available": copy.get("available"),
                                  "kind": copy.get("kind")}
    finally:
        C.stop(RUN_DIR, NODE)
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log_lines = (server.stdout.read() or "").splitlines() if server.stdout else []
        server.stdout and server.stdout.close()

    # ⑥ 实例停后：显式降级（target_missing），且元数据已清
    if server.poll() is None:
        pass
    server2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "services.api:app", "--host", "127.0.0.1",
         "--port", str(PORT), "--log-level", "warning"],
        cwd=str(LOOP), env={**os.environ, "LOOP_WORKSPACE": str(WORKSPACE)},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(120):
            try:
                if _req("GET", BASE + "/api/health")[0] == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError):
                pass
            time.sleep(0.25)
        status, _h, body = _req(
            "GET", f"{BASE}/api/runs/{RUN_ID}/agents/{NODE}/instance?attempt={ATTEMPT}")
        meta = json.loads(body)
        report["after_stop"] = {"status": status, "body": meta,
                                "metadata_exists": (RUN_DIR / "agent_instance.json").exists()}
    finally:
        server2.terminate()
        try:
            server2.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server2.kill()

    leaked = [line for line in log_lines if token and token in line]
    report["token_in_dashboard_log"] = len(leaked)
    assert not leaked, "token 出现在看板日志里"
    (OUT / "wired_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = (report["availability"]["body"]["state"] == "ready"
          and report["index"]["status"] == 200
          and report["api_post"]["status"] == 200
          and report["after_stop"]["body"]["state"] == "unavailable"
          and report["after_stop"]["body"]["reason"] == "target_missing"
          and not report["after_stop"]["metadata_exists"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
