"""旧界面（`legacy.html`）的闸门决策按钮只认服务端**每次重算**的 `run_view.gate_options`。

回归背景（2026-10-26 A3 / WEB_UI_SPEC §4.4「中断载荷里的选项只是快照」、红线 4/8）：
`legacy.html` 曾经按「先 `payload.decision_options`（中断快照）→ 再 `run_view.gate_options`
→ 最后一张手抄枚举兜底表」取按钮。前两者顺序颠倒 ⇒ 快照恢复出来的旧选项会盖掉服务端重算值
（第二套判据，红线 8）；兜底表则是前端手抄 `kb_lib.GATE_DECISIONS`（红线 4）。

本测试用受控替身构造「快照里有选项 + `gate_options` 缺失」这一形态，断言：
**不给按钮、明确说不可提交、提交按钮禁用**；服务端下发重算值后才出现按钮。
替身不模拟签署证据，只验证界面判据来源。
"""
from __future__ import annotations

import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="安装 requirements-ui.txt 运行浏览器验收")

GATE = "G1_diff_confirm"
# 中断载荷里的**快照**选项：界面不得据它渲染（只有 run_view.gate_options 才是判据）。
SNAPSHOT = [{"value": "confirmed", "label": "快照里的确认"}]


def _view(gate_options):
    return {
        "run_id": "A", "status": "waiting_gate", "mode": "drill", "node_history": [],
        "pending_interrupt": {
            "id": GATE + ":0", "type": "gate_decision",
            "payload": {"gate": GATE, "cycle": 0, "decision_options": SNAPSHOT},
        },
        "gate_options": dict(gate_options),
    }


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:  # noqa: D102 - 静音访问日志
        pass


@pytest.fixture(scope="module")
def static_url():
    web = Path(__file__).resolve().parents[2] / "web"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(web)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def legacy(static_url):
    with pw.sync_playwright() as driver:
        executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
        browser = driver.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page()
        api = {"gate_options": {}, "errors": []}
        page.on("pageerror", lambda error: api["errors"].append(str(error)))

        def route_request(route):
            path = urlsplit(route.request.url).path
            if path == "/api/health":
                body = {"ok": True, "env_root": "/fixture", "plugin_missing": [],
                        "workspace_missing": []}
            elif path == "/api/baselines":
                body = {"baselines": []}
            elif path == "/api/runs":
                body = {"runs": [{"run_id": "A", "status": "waiting_gate", "mode": "drill"}]}
            elif path.endswith("/events"):
                body = {"events": []}
            elif path == "/api/runs/A":
                body = _view(api["gate_options"])
            else:
                body = {"ok": False}
            route.fulfill(json=body)

        page.route("**/api/**", route_request)
        page.goto(f"{static_url}/legacy.html")
        yield page, api
        assert not api["errors"], api["errors"]
        browser.close()


def test_legacy_does_not_render_snapshot_decision_options(legacy):
    page, api = legacy
    buttons = page.locator("#fButtons")
    # 服务端没下发重算值 ⇒ 不渲染任何决策按钮，且明确说"不可提交"（快照不算数）。
    pw.expect(buttons).to_contain_text("服务端未下发决策选项")
    assert buttons.locator(".dec-btn").count() == 0
    assert "快照里的确认" not in buttons.inner_text()
    assert page.eval_on_selector("#btnSubmit", "el => el.disabled") is True

    # 服务端下发重算值后才出现按钮（来源唯一 = run_view.gate_options）。
    api["gate_options"] = {GATE: [{"value": "confirmed", "label": "服务端确认"},
                                 {"value": "ignored", "label": "服务端忽略"}]}
    pw.expect(buttons.locator(".dec-btn")).to_have_count(2)
    pw.expect(buttons).to_contain_text("服务端确认")
    assert "快照里的确认" not in buttons.inner_text()
