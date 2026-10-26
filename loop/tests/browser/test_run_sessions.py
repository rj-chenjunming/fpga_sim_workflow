"""真实静态页的特征/竞态测试；API 是受控替身，不模拟人工签署证据。"""
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


def view(rid, baseline=None):
    return {
        "run_id": rid, "status": "waiting_gate", "mode": "drill",
        "baseline": baseline or rid + "-baseline", "node_history": [],
        "pending_interrupt": {"id": GATE + ":0", "type": "gate_decision",
                              "payload": {"gate": GATE, "cycle": 0}},
        "gate_options": {GATE: [{"value": "confirmed", "label": "服务端确认"},
                                {"value": "ignored", "label": "服务端忽略", "requires_reason": True}]},
    }


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
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
def ui(static_url):
    with pw.sync_playwright() as driver:
        executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
        browser = driver.chromium.launch(**({"executable_path": executable} if executable else {}))
        page = browser.new_page()
        page.clock.install()
        api = {"views": {rid: view(rid) for rid in ("A", "B")}, "hold": None,
               "pending": [], "posts": [], "errors": [], "nodes": {}}
        page.on("pageerror", lambda error: api["errors"].append(str(error)))

        def route_request(route):
            path = urlsplit(route.request.url).path
            if route.request.method == "POST":
                api["posts"].append((path, route.request.post_data_json))
                api["pending"].append(route)
                return
            if api["hold"] and api["hold"](path):
                api["pending"].append(route)
                return
            if path == "/api/health":
                body = {"ok": True, "env_root": "/fixture", "plugin_missing": [], "workspace_missing": []}
            elif path == "/api/baselines":
                body = {"baselines": []}
            elif path == "/api/s0":
                body = {"baseline": "/fixture", "records": [], "allowed_roots": ["/fixture"],
                        "capabilities": {"prepare": True, "rehearsal": True,
                                         "tb_adapt": False, "smoke": False}}
            elif path == "/api/runs":
                body = {"runs": [{"run_id": rid, "status": "waiting_gate", "mode": "drill"}
                                 for rid in api["views"]]}
            elif path.startswith("/api/runs/") and "/nodes/" in path:
                rest = path.split("/api/runs/", 1)[1]
                rid, node = rest.split("/nodes/", 1)
                body = api["nodes"].get((rid, node), {
                    "run_id": rid, "node": node, "known": False,
                    "authority": "projection", "events": []})
            elif path.endswith("/evidence/exists"):
                body = {"path": "/fixture/evidence", "exists": True, "bytes": 12}
            elif path.startswith("/api/runs/") and "/agents/" in path:
                # SPEC-09: AI chips now read the agent endpoint before secondary
                # node details. Empty history is a valid API response, not a run view.
                rid, node = path.split("/api/runs/", 1)[1].split("/agents/", 1)
                body = {"run_id": rid, "node": node, "live": None, "selected_attempt": None,
                        "attempts": [], "request": None, "result": None, "events": [], "controls": []}
            elif path.startswith("/api/runs/"):
                body = api["views"][path.rsplit("/", 1)[1]]
            else:
                body = {"ok": False}
            route.fulfill(json=body)

        page.route("**/api/**", route_request)
        page.goto(static_url)
        pw.expect(page.locator(".run-item")).to_have_count(2)
        yield page, api
        assert not api["errors"], api["errors"]
        browser.close()


def select(page, rid):
    page.locator(".run-item").filter(has_text=rid).click()


def open_gate(page, rid="A"):
    select(page, rid)
    pw.expect(page.locator("#viewGate")).to_be_visible()
    pw.expect(page.locator("#gatePanel [aria-label=actor]")).to_be_visible()


def fill(page, reason="reviewed"):
    page.locator('#gatePanel input[value="confirmed"]').check()
    page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
    page.locator('#gatePanel [aria-label="裁决理由"]').fill(reason)


def tick(page):
    page.clock.run_for(1600)
    page.wait_for_timeout(80)  # 让真实网络回调完成；不依赖机器执行速度排序请求


def release(page, api, body, status=200, index=0):
    route = api["pending"].pop(index)
    route.fulfill(status=status, json=body)
    page.wait_for_timeout(80)


def test_s0_default_view_and_unavailable_driver_are_explicit(ui):
    page, api = ui
    pw.expect(page.locator('#viewS0')).to_be_visible()
    pw.expect(page.locator('#s0Readiness')).to_contain_text('尚未准出')
    pw.expect(page.locator('#s0PhaseB')).to_contain_text('三库')
    pw.expect(page.locator('#s0PhaseB')).to_contain_text('未接入')
    assert not api['posts']


def test_s0_prepare_captures_paths_prevents_duplicate_and_shows_blockers(ui):
    page, api = ui
    for element, value in [('s0Baseline', '/fixture/baseline'), ('s0Version', 'v1'),
                           ('s0Rtl', '/fixture/src/rtl'), ('s0Work', '/fixture/baseline_wk_v2')]:
        page.locator('#' + element).fill(value)
    page.locator('#s0Prepare').evaluate('el => { el.click(); el.click(); }')
    page.wait_for_timeout(80)
    assert api['posts'] == [('/api/s0', {'baseline': '/fixture/baseline', 'baseline_version': 'v1',
                                       'rtl_source': '/fixture/src/rtl', 'work_env': '/fixture/baseline_wk_v2'})]
    release(page, api, {'id': 'S0-fixture', 'status': 'prepared', 'ready_for_execution': False,
                        'work_env': '/fixture/baseline_wk_v2', 'checks': [],
                        'blockers': [{'message': '三库未执行'}], 'report_url': '/api/s0/S0-fixture/report'})
    pw.expect(page.locator('#s0Readiness')).to_contain_text('尚未准出')
    pw.expect(page.locator('#s0Blockers')).to_contain_text('三库未执行')
    pw.expect(page.locator('#s0Result')).to_contain_text('/fixture/baseline_wk_v2')
    pw.expect(page.locator('#s0Report')).to_have_attribute('href', '/api/s0/S0-fixture/report')


def test_s0_rehearsal_runs_once_and_shows_four_checks_with_scope_notice(ui):
    """SPEC-05 §7：工作台可一键完成 S0-rehearsal，并明确"不是环境就绪、不是 S0-b"。"""
    page, api = ui
    record = {
        "id": "S0-REHEARSAL-0001", "status": "prepared",
        "work_env": "/state/s0-rehearsal/20261022/work",
        "ready_for_execution": False,
        "checks": [
            {"key": "copy", "label": "完整派生工作副本", "status": "passed"},
            {"key": "rtl", "label": "新版 RTL 整体替换", "status": "passed"},
            {"key": "non_rtl", "label": "非 RTL 初检一致", "status": "passed"},
            {"key": "ports", "label": "接口核对与 TB 变更登记", "status": "waiting"},
            {"key": "smoke", "label": "副本三库编译冒烟", "status": "waiting"},
            {"key": "baseline", "label": "基线零写入见证", "status": "passed"},
        ],
    }
    page.locator("#s0Rehearsal").click()
    release(page, api, record)
    box = page.locator("#s0RehearsalResult")
    pw.expect(box).to_contain_text("S0-a 链路已走通")
    pw.expect(box).to_contain_text("S0-REHEARSAL-0001")
    pw.expect(box).to_contain_text("完整派生工作副本")
    pw.expect(box).to_contain_text("副本三库编译冒烟")
    pw.expect(box).to_contain_text("不是环境就绪")
    assert [p[0] for p in api["posts"]].count("/api/s0/rehearsal") == 1


def test_s0_rejection_keeps_inputs_and_focus_survives_polling(ui):
    page, api = ui
    for element in ['s0Baseline', 's0Version', 's0Rtl', 's0Work']:
        page.locator('#' + element).fill('/fixture/value')
    page.locator('#s0Work').focus()
    tick(page)
    pw.expect(page.locator('#s0Work')).to_be_focused()
    page.locator('#s0Prepare').click()
    page.wait_for_timeout(80)
    release(page, api, {'detail': {'error': '目标已存在，不会覆盖'}}, 409)
    pw.expect(page.locator('#s0Error')).to_contain_text('目标已存在')
    pw.expect(page.locator('#s0Work')).to_have_value('/fixture/value')
    pw.expect(page.locator('#s0Prepare')).to_be_enabled()


@pytest.mark.parametrize('width', [390, 768])
def test_s0_narrow_view_has_no_page_horizontal_overflow(ui, width):
    page, _ = ui
    page.set_viewport_size({'width': width, 'height': 844})
    pw.expect(page.locator('#viewS0')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def test_characterization_server_options_and_poll_preserve_input_focus(ui):
    page, api = ui
    open_gate(page)
    pw.expect(page.locator("#gatePanel .option b")).to_have_text(["服务端确认", "服务端忽略"])
    fill(page)
    page.locator('#gatePanel [aria-label="裁决理由"]').focus()
    before = page.locator('#gatePanel [aria-label="裁决理由"]').element_handle()
    tick(page)
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("reviewed")
    assert page.evaluate("element => element === document.activeElement", before)
    assert not api["posts"]


def test_characterization_required_reason_prevents_post(ui):
    page, api = ui
    open_gate(page)
    page.locator('#gatePanel input[value="ignored"]').check()
    page.locator('#gatePanel [data-gate-submit]').click()
    pw.expect(page.locator("#gatePanel .gate-error")).to_contain_text("必须填写理由")
    assert not api["posts"]


def test_characterization_double_click_and_rejection_keep_draft(ui):
    page, api = ui
    open_gate(page)
    fill(page)
    page.locator('#gatePanel [data-gate-submit]').evaluate("el => { el.click(); el.click(); }")
    page.wait_for_timeout(80)
    assert api["posts"] == [(f"/api/runs/A/gates/{GATE}/decision",
                             {"decision": "confirmed", "actor": "human:reviewer", "reason": "reviewed"})]
    release(page, api, {"detail": {"error": "refused", "blockers": [{"code": "I4", "message": "blocked"}],
                                   "note": "gate unchanged"}}, 403)
    pw.expect(page.locator("#gatePanel .gate-error")).to_contain_text("I4：blocked")
    pw.expect(page.locator("#gatePanel .gate-error")).to_contain_text("gate unchanged")
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("reviewed")
    pw.expect(page.locator('#gatePanel [data-gate-submit]')).to_be_enabled()


def test_cross_run_draft_is_cleared(ui):
    page, _ = ui
    open_gate(page)
    fill(page)
    select(page, "B")
    pw.expect(page.locator("#gateHead")).to_contain_text("B")
    pw.expect(page.locator('#gatePanel [aria-label="actor"]')).to_have_value("human:")
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("")
    pw.expect(page.locator('#gatePanel [data-gate-submit]')).to_be_disabled()


@pytest.mark.parametrize("old_error", [False, True])
def test_late_selection_response_cannot_replace_new_run(ui, old_error):
    page, api = ui
    api["hold"] = lambda path: path == "/api/runs/A"
    select(page, "A")
    select(page, "B")
    pw.expect(page.locator("#gateHead")).to_contain_text("B")
    release(page, api, {"detail": {"error": "old error"}} if old_error else view("A", "OLD-A"),
            500 if old_error else 200)
    pw.expect(page.locator("#runHead")).to_contain_text("B-baseline")
    pw.expect(page.locator("#gateAlerts")).not_to_contain_text("old error")
    pw.expect(page.locator("#toast")).not_to_contain_text("old error")


def test_reselect_same_run_ignores_previous_selection_response(ui):
    page, api = ui
    api["hold"] = lambda path: path == "/api/runs/A"
    select(page, "A")
    select(page, "B")
    select(page, "A")
    page.wait_for_timeout(80)
    assert len(api["pending"]) == 2
    release(page, api, view("A", "NEW-A"), index=1)
    pw.expect(page.locator("#runHead")).to_contain_text("NEW-A")
    release(page, api, view("A", "OLD-A"))
    pw.expect(page.locator("#runHead")).to_contain_text("NEW-A")


def test_late_poll_cannot_replace_new_selection(ui):
    page, api = ui
    open_gate(page)
    api["hold"] = lambda path: path == "/api/runs/A"
    tick(page)
    assert len(api["pending"]) == 1
    select(page, "B")
    pw.expect(page.locator("#runHead")).to_contain_text("B-baseline")
    release(page, api, view("A", "OLD-POLL"))
    pw.expect(page.locator("#runHead")).to_contain_text("B-baseline")


@pytest.mark.parametrize("status", [200, 403])
def test_old_submission_cannot_clear_or_navigate_new_session(ui, status):
    page, api = ui
    open_gate(page)
    fill(page)
    page.locator('#gatePanel [data-gate-submit]').click()
    page.wait_for_timeout(80)
    select(page, "B")
    fill(page, "B reason")
    release(page, api, {} if status == 200 else {"detail": {"error": "A refused"}}, status)
    pw.expect(page.locator("#viewGate")).to_be_visible()
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("B reason")
    pw.expect(page.locator("#gatePanel .gate-error")).not_to_contain_text("A refused")
    assert api["posts"][0][0] == f"/api/runs/A/gates/{GATE}/decision"


def test_new_interrupt_same_gate_and_cycle_resets_draft(ui):
    page, api = ui
    open_gate(page)
    fill(page)
    api["views"]["A"]["pending_interrupt"]["id"] = "replacement-interrupt"
    tick(page)
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("")
    pw.expect(page.locator('#gatePanel [data-gate-submit]')).to_be_disabled()


def test_both_gate_forms_show_shared_inputs(ui):
    page, _ = ui
    open_gate(page)
    fill(page)
    page.locator("#segRun").click()
    pw.expect(page.locator('#gateCardBody [aria-label="actor"]')).to_have_value("human:reviewer")
    pw.expect(page.locator('#gateCardBody [aria-label="裁决理由"]')).to_have_value("reviewed")


def test_withdrawn_option_cannot_be_submitted(ui):
    page, api = ui
    open_gate(page)
    fill(page)
    api["views"]["A"]["gate_options"][GATE] = [{"value": "ignored", "label": "服务端忽略"}]
    tick(page)
    page.locator('#gatePanel [data-gate-submit]').evaluate("el => el.click()")
    page.wait_for_timeout(80)
    assert not api["posts"], "服务端撤回的选项不得提交"


def test_returning_to_submitting_gate_cannot_post_twice(ui):
    page, api = ui
    open_gate(page)
    fill(page)
    page.locator('#gatePanel [data-gate-submit]').click()
    page.wait_for_timeout(80)
    select(page, "B")
    select(page, "A")
    pw.expect(page.locator("#gateHead")).to_contain_text("A")
    page.locator('#gatePanel [data-gate-submit]').evaluate("el => el.click()")
    page.wait_for_timeout(80)
    assert len(api["posts"]) == 1
    pw.expect(page.locator('#gatePanel [data-gate-submit]')).to_have_text("提交中…")
    release(page, api, {"detail": {"error": "old refusal"}}, 403)
    pw.expect(page.locator('#gatePanel [data-gate-submit]')).to_have_text("提交闸门决策")
    pw.expect(page.locator("#gatePanel .gate-error")).not_to_contain_text("old refusal")


# ---- F13：首次失败 / 刷新失败 / 恢复（Web UI §7.2） -------------------------

def test_first_detail_failure_does_not_claim_loading_or_previous_success(ui):
    page, api = ui
    api["hold"] = lambda path: path == "/api/runs/A"
    select(page, "A")
    release(page, api, {"detail": {"error": "Service Unavailable"}}, 503)
    pw.expect(page.locator("#runHead")).to_contain_text("读取失败")
    pw.expect(page.locator("#runHead")).not_to_contain_text("加载中")
    pw.expect(page.locator("#runAlerts")).to_contain_text("尚无成功读取的数据")
    pw.expect(page.locator("#runAlerts")).not_to_contain_text("最近一次成功")
    pw.expect(page.locator("#runAlerts")).not_to_contain_text("上次成功")
    pw.expect(page.locator("#runRetry")).to_be_visible()
    # 同一屏的其它面板也不得再显示「加载中」（唯一判据，8 处占位全断言）
    for panel in ("#agents", "#countsBody", "#blockersBody", "#jobBody", "#eventsSummary",
                  "#gateHead", "#gateMaterial", "#gatePanel"):
        pw.expect(page.locator(panel)).not_to_contain_text("加载中")
    # 重新读取只重取当前运行详情；恢复后错误横幅消失
    page.locator("#runRetry").click()
    page.wait_for_timeout(80)
    release(page, api, view("A", "RECOVERED-A"))
    pw.expect(page.locator("#runHead")).to_contain_text("RECOVERED-A")
    pw.expect(page.locator("#runAlerts")).not_to_contain_text("读取运行视图失败")
    pw.expect(page.locator("#runRetry")).to_have_count(0)
    assert not api["posts"]


def test_gate_view_first_failure_uses_same_state_and_offers_retry(ui):
    page, api = ui
    api["hold"] = lambda path: path == "/api/runs/A"
    select(page, "A")
    release(page, api, {"detail": {"error": "Service Unavailable"}}, 503)
    page.locator("#segGate").click()
    pw.expect(page.locator("#gateAlerts")).to_contain_text("尚无成功读取的数据")
    pw.expect(page.locator("#gateHead")).to_contain_text("读取失败")
    pw.expect(page.locator("#gateHead")).not_to_contain_text("加载中")
    pw.expect(page.locator("#gateMaterial")).not_to_contain_text("加载中")
    pw.expect(page.locator("#gateRetry")).to_be_visible()
    page.locator("#gateRetry").click()
    page.wait_for_timeout(80)
    release(page, api, view("A"))
    pw.expect(page.locator("#gateAlerts")).not_to_contain_text("读取运行视图失败")
    pw.expect(page.locator("#gatePanel [aria-label=actor]")).to_be_visible()
    assert not api["posts"]


def test_refresh_failure_keeps_data_and_shows_expired_with_last_success(ui):
    page, api = ui
    select(page, "A")
    page.locator("#segRun").click()
    pw.expect(page.locator("#runHead")).to_contain_text("A-baseline")
    api["hold"] = lambda path: path == "/api/runs/A"
    tick(page)
    release(page, api, {"detail": {"error": "timeout"}}, 503)
    pw.expect(page.locator("#runHead")).to_contain_text("A-baseline")
    pw.expect(page.locator("#runHead")).not_to_contain_text("加载中")
    pw.expect(page.locator("#runAlerts")).to_contain_text("数据已过期")
    pw.expect(page.locator("#runAlerts")).to_contain_text("上次成功")
    pw.expect(page.locator("#runRetry")).to_be_visible()
    # 恢复后仍保留数据，且错误与重试入口消失
    page.locator("#runRetry").click()
    page.wait_for_timeout(80)
    release(page, api, view("A"))
    pw.expect(page.locator("#runAlerts")).not_to_contain_text("数据已过期")
    pw.expect(page.locator("#runRetry")).to_have_count(0)


def test_refresh_failure_does_not_rebuild_gate_form_or_lose_draft(ui):
    page, api = ui
    open_gate(page)
    fill(page)
    page.locator('#gatePanel [aria-label="裁决理由"]').focus()
    api["hold"] = lambda path: path == "/api/runs/A"
    tick(page)
    release(page, api, {"detail": {"error": "timeout"}}, 503)
    pw.expect(page.locator("#gateAlerts")).to_contain_text("数据已过期")
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_have_value("reviewed")
    pw.expect(page.locator('#gatePanel [aria-label="裁决理由"]')).to_be_focused()
    assert not api["posts"]
