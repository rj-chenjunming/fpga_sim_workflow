"""S0「单一 RTL 文件夹一键入口」界面验收（WEB_UI_SPEC §15 / 计划 2026-10-30 §4 T3）。

受控替身：沿用 `test_run_sessions.ui`（已挂通用 `/api/**`）与 `test_web_layout.assert_fits`。
本文件在 `ui` fixture **之后**用 `page.route` 覆盖 from-rtl / advance / activate /
env/state / copies / switch-back（Playwright 后注册优先），因此不依赖 T1/T2 的真实后端。

覆盖（与任务 T3 的交付项同名同序）：
- A1 单输入二选一（S0 §9.9 / WEB_UI §15）：`#s0Mode` 默认「新版 RTL 文件夹」，只显示/要求
  `#s0Rtl` 且只发 `rtl_source`；切到「环境项目目录」只显示/要求 `#s0EnvDir` 且只发 `baseline`；
  另一个输入 hidden + disabled + 非 required（否则 reportValidity 会被隐藏输入卡住）。
- A1b 高级键（`baseline_version`/`work_env`）两种模式下都只在填了才发。
- A2c `entry="env_folder"` 的 `rtl=skipped` 渲染：「未替换（环境项目入口）」+ reason 原文，
  不当 passed、也不隐藏该步；`entry="rtl_folder"` 出现 skipped 一律按“不当作通过”显示。
- A2 阶段回执：#s0PhaseFlow 渲染六阶段，阶段文字来自服务端 checks/ports/smoke/
  ready_for_execution/env_switch/copy_plan/folder_warning。
- A3 端口 waiting：`#s0Ports` 列出 `ports.table` 并显示「提议来源未接入本入口」；
  「继续冒烟」被服务端拒绝时展示原文。
- A4 切换成功：准出后自动 POST activate ⇒ 轮询 /api/health（允许失败）⇒ 显示
  「已切换到派生环境 · 去新建运行」、写 sessionStorage["loop.s0Prefill"]、切到运行配置，
  且 `POST /api/runs` 带上 `s0_record_id`。
- A5 副本清单：大小/存在性/状态来自 GET /api/s0/copies；「删除副本」二次确认，
  取消不发请求，确认才 DELETE `?confirm=true`。
- A6 切回失败：POST /api/env/switch-back 的失败按服务端原文展示。
- A7 1280×720（及 1440/390）无水平溢出。

缺 Chromium 属环境缺件：`test_run_sessions` 已 `importorskip("playwright.sync_api")`，
本文件不另加 pytest.skip 兜底，避免把缺件当成通过。
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

from test_run_sessions import pw, ui, static_url, view  # noqa: F401
from test_web_layout import assert_fits

ENTRY = "/api/s0/from-rtl"

ENV_OK = {
    "ok": True, "matches_current_process": True, "path": "/fixture", "registered": True,
    "env_id": "TCS9620", "plugin_missing": [], "workspace_missing": [],
    "counts": {"rtl_files": 1210, "cases": 162},
}


# ---------------------------------------------------------------- 服务端记录形状（替身输入）

def record(**overrides):
    """`POST /api/s0/from-rtl` 返回的记录：字段名与 §4 冻结接口一致。"""
    base = {
        "id": "S0-T3-0001",
        "entry": "rtl_folder",
        "status": "prepared",
        "ready_for_execution": False,
        "baseline": "/fixture",
        "baseline_version": "v1.2-stable",
        "rtl_source": "/fixture/incoming/RTL",
        "rtl_prefix": "RTL",
        "work_env": "/TOOL/workspaces/fixture-derived-20261030",
        "origin_env_root": "/fixture",
        "smoke_case": "tc_smoke_01",
        "copy_plan": {"copied": ["TB", "PKG", "TESTLIB"],
                      "excluded_roots": ["kb/runs", "loop"],
                      "skipped": [{"rel": "TB/link.sv", "reason": "symlink",
                                   "target": "/fixture/TB/link.sv"}]},
        "folder_warning": {"same": 120, "added": 12, "removed": 3, "ratio": 0.125},
        "auto": {"phase": "awaiting_ports"},
        "checks": [
            {"key": "copy", "label": "完整派生工作副本", "status": "passed"},
            {"key": "rtl", "label": "新版 RTL 整体替换", "status": "passed"},
            {"key": "non_rtl", "label": "非 RTL 初检一致", "status": "passed"},
            {"key": "ports", "label": "接口核对与 TB 变更登记", "status": "waiting",
             "reason": "有端口差异未被任何 hunk 覆盖：dma_controller"},
            {"key": "smoke", "label": "副本三库编译冒烟", "status": "waiting"},
            {"key": "baseline", "label": "基线零写入见证", "status": "passed"},
        ],
        "ports": {"status": "waiting", "reason": "有端口差异未被任何 hunk 覆盖：dma_controller",
                  "table": [{"kind": "module", "module": "dma_controller",
                             "added": ["transfer_len"], "removed": [], "changed": ["addr_width"]},
                            {"kind": "module_added", "module": "new_fifo"}],
                  "evidence": {}, "derive": {}},
        "smoke": None,
        "env_switch": None,
        "blockers": [{"message": "端口差异待处置"}],
    }
    base.update(overrides)
    return base


def ready_record(**overrides):
    """准出记录：六项 passed + ready_for_execution=true（切换将被自动触发）。"""
    base = record(
        id="S0-T3-0002",
        ready_for_execution=True,
        auto={"phase": "ready"},
        smoke={"status": "passed", "reason": "三库编译 0 error；warning 与基线一致"},
        ports={"status": "passed", "reason": "派生成立、差异均已处置", "table": [], "evidence": {}},
        blockers=[],
    )
    base["checks"] = [dict(check, status="passed") for check in base["checks"]]
    base.update(overrides)
    return base


#: §9.9-2 固定理由原文（服务端落账，界面只显示）
ENV_RTL_REASON = ("环境项目入口：未提供新版 RTL，副本 RTL 与源环境逐文件一致"
                  "（copy 判据已覆盖），不做替换")


def env_record(**overrides):
    """`POST /api/s0/from-rtl` 在「只给 baseline」时的记录：entry=env_folder、rtl=skipped。"""
    base = {
        "id": "S0-T3-0003",
        "entry": "env_folder",
        "status": "prepared",
        "ready_for_execution": False,
        "baseline": "/fixture/env-project",
        "baseline_version": "ENV@env-project+20261030T120000Z",
        "rtl_source": None,
        "rtl_prefix": None,
        "rtl_plan": None,
        "folder_warning": None,
        "work_env": "/TOOL/workspaces/env-project-derived-1",
        "origin_env_root": "/fixture",
        "smoke_case": "tc_smoke_01",
        "copy_plan": {"copied": ["RTL", "TB", "PKG", "TESTLIB"],
                      "excluded_roots": ["loop", "kb/runs"], "skipped": []},
        "auto": {"phase": "awaiting_ports"},
        "checks": [
            {"key": "copy", "label": "选择性复制工作副本", "status": "passed"},
            # 服务端在 env_folder 下把该项 label 写成「RTL 未替换（环境项目入口）」。
            {"key": "rtl", "label": "RTL 未替换（环境项目入口）", "status": "skipped",
             "reason": ENV_RTL_REASON},
            {"key": "non_rtl", "label": "非 RTL 初检一致", "status": "passed"},
            {"key": "ports", "label": "接口核对与 TB 变更登记", "status": "passed",
             "reason": "派生成立、差异均已处置"},
            {"key": "smoke", "label": "副本三库编译冒烟", "status": "waiting"},
            {"key": "baseline", "label": "基线零写入见证", "status": "passed"},
        ],
        "ports": {"status": "passed", "reason": "派生成立、差异均已处置",
                  "table": [], "evidence": {}},
        "smoke": None,
        "env_switch": None,
        "blockers": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- 替身注册

def post_recorder(api, body, status=200):
    """记录 POST 并把 `body` 直接回给页面（该入口不需要人工放行）。"""
    def handler(route):
        api["posts"].append((urlsplit(route.request.url).path, route.request.post_data_json))
        route.fulfill(status=status, json=body)
    return handler


def route_entry(page, api, body, status=200):
    page.route("**" + ENTRY, post_recorder(api, body, status))


def route_copies(page, copies):
    page.route("**/api/s0/copies", lambda route: route.fulfill(json={"copies": copies}))


def route_env_state(page, state):
    page.route("**/api/env/state", lambda route: route.fulfill(json=state))


def open_advanced(page):
    """T3：高级键在折叠 <details> 里，需要展开才能编辑。"""
    page.locator("#s0Advanced").evaluate("el => { el.open = true }")


def prepare(page, rtl="/fixture/incoming/RTL"):
    """默认模式（新版 RTL 文件夹）：只填 #s0Rtl 即可提交。"""
    page.locator("#s0Rtl").fill(rtl)
    page.locator("#s0Prepare").click()
    page.wait_for_timeout(120)


def prepare_env(page, env_dir="/fixture/env-project"):
    """切到「环境项目目录」模式：只填 #s0EnvDir 即可提交（rtl 那一格不参与）。"""
    page.locator("#s0ModeEnv").check()
    page.locator("#s0EnvDir").fill(env_dir)
    page.locator("#s0Prepare").click()
    page.wait_for_timeout(120)


# ---------------------------------------------------------------- A1 表单
def test_a1_mode_radios_require_exactly_one_input(ui):
    page, api = ui
    advanced = page.locator("#s0Advanced")
    assert advanced.evaluate("el => el.tagName") == "DETAILS"
    assert advanced.evaluate("el => el.open") is False, "高级项默认折叠（UI 规范：收进「高级」）"
    for advanced_id in ("s0Version", "s0Work"):
        assert page.locator("#" + advanced_id).get_attribute("required") is None, advanced_id
    # §15：界面不展示“环境项目 + 新 RTL”组合 ⇒ 旧的高级 `#s0Baseline` 已移除。
    assert page.locator("#s0Baseline").count() == 0
    # 默认 rtl 模式：只显示/要求 #s0Rtl，环境项目那格 hidden + disabled。
    group = page.locator("#s0Mode")
    assert group.get_attribute("role") == "radiogroup"
    assert page.locator("#s0ModeRtl").is_checked()
    pw.expect(page.locator("#s0Rtl")).to_be_visible()
    pw.expect(page.locator("#s0EnvDir")).to_be_hidden()
    assert page.locator("#s0Rtl").get_attribute("required") is not None
    assert page.locator("#s0EnvDir").get_attribute("required") is None
    assert page.locator("#s0EnvDir").is_disabled()
    route_entry(page, api, record())
    prepare(page)
    # 只发 rtl_source：baseline 不出现（空值不发，默认由服务端 §9.1 决定）。
    assert api["posts"] == [(ENTRY, {"rtl_source": "/fixture/incoming/RTL"})]
    pw.expect(page.locator("#s0Result")).to_contain_text("S0-T3-0001")
    pw.expect(page.locator("#s0Result")).to_contain_text("一键入口")
    # rtl 模式下清空必填 ⇒ 不得提交。
    page.locator("#s0Rtl").fill("")
    page.locator("#s0Prepare").click()
    page.wait_for_timeout(120)
    assert len(api["posts"]) == 1, "RTL 模式没填文件夹不得提交"
    # 切到环境项目模式：只显示/要求 #s0EnvDir，之前填的 RTL 不再发送。
    page.locator("#s0ModeEnv").check()
    pw.expect(page.locator("#s0EnvDir")).to_be_visible()
    pw.expect(page.locator("#s0Rtl")).to_be_hidden()
    assert page.locator("#s0EnvDir").get_attribute("required") is not None
    assert page.locator("#s0Rtl").get_attribute("required") is None
    assert page.locator("#s0Rtl").is_disabled()
    page.locator("#s0Prepare").click()
    page.wait_for_timeout(120)
    assert len(api["posts"]) == 1, "环境项目模式没填目录不得提交"
    page.locator("#s0EnvDir").fill("/fixture/env-project")
    page.locator("#s0Prepare").click()
    page.wait_for_timeout(120)
    assert api["posts"][-1] == (ENTRY, {"baseline": "/fixture/env-project"})
    assert "rtl_source" not in api["posts"][-1][1]
    # 防重复提交：双击只发一次（沿用既有 busy 写法）。
    page.locator("#s0Prepare").evaluate("el => { el.click(); el.click(); }")
    page.wait_for_timeout(120)
    assert [p[0] for p in api["posts"]] == [ENTRY, ENTRY, ENTRY]


def test_a1b_advanced_values_are_forwarded_only_when_filled(ui):
    page, api = ui
    route_entry(page, api, record())
    open_advanced(page)
    page.locator("#s0Version").fill("v1.2")
    prepare(page)
    assert api["posts"] == [(ENTRY, {"rtl_source": "/fixture/incoming/RTL",
                                    "baseline_version": "v1.2"})]
    # env 模式：baseline（环境项目目录）+ 高级键；rtl_source 不出现。
    page.locator("#s0Work").fill("/fixture/work-env")
    prepare_env(page)
    assert api["posts"][-1] == (ENTRY, {"baseline": "/fixture/env-project",
                                       "baseline_version": "v1.2",
                                       "work_env": "/fixture/work-env"})


# ---------------------------------------------------------------- A2 阶段回执# ---------------------------------------------------------------- A2 阶段回执
def test_a2_phase_flow_renders_server_receipts(ui):
    page, api = ui
    route_entry(page, api, record())
    prepare(page)
    flow = page.locator("#s0PhaseFlow")
    for label in ("派生副本", "端口确认", "三库冒烟", "准出", "切换环境", "到运行配置"):
        pw.expect(flow).to_contain_text(label)
    text = flow.inner_text()
    # copy_plan / folder_warning 原样来自服务端字段（界面只排版，不重算）。
    assert "复制 3 项" in text, text
    assert "排除 2 项" in text and "kb/runs" in text, text
    assert "跳过 1 项" in text and "symlink" in text, text
    assert "目录告警" in text and "新增 12" in text and "缺失 3" in text, text
    assert "有端口差异未被任何 hunk 覆盖：dma_controller" in text, text
    # 既有容器不退化：检查清单 / 回执 / blockers 仍在服务端字段上。
    pw.expect(page.locator("#s0Checks")).to_contain_text("完整派生工作副本")
    pw.expect(page.locator("#s0Readiness")).to_contain_text("尚未准出")
    pw.expect(page.locator("#s0Blockers")).to_contain_text("端口差异待处置")
    assert not api["posts"][1:]


# ---------------------------------------------------------------- A2b/A2c skipped 渲染
def test_a2b_env_folder_shows_unreplaced_rtl_step(ui):
    """§9.9-3：`entry=env_folder` 的 `rtl=skipped` 显示「未替换（环境项目入口）」+ reason 原文。"""
    page, api = ui
    route_entry(page, api, env_record())
    prepare_env(page, "/fixture/env-project")
    assert api["posts"] == [(ENTRY, {"baseline": "/fixture/env-project"})], api["posts"]
    result = page.locator("#s0Result")
    pw.expect(result).to_contain_text("一键入口（环境项目入口）")
    pw.expect(result).to_contain_text("RTL：未替换（环境项目入口）")
    # 检查清单：RTL 那一项状态是「未替换（环境项目入口）」+ reason，且不被标成通过。
    rtl_item = page.locator("#s0Checks li").nth(1)
    pw.expect(rtl_item).to_contain_text("RTL 未替换（环境项目入口）")
    pw.expect(rtl_item).to_contain_text(ENV_RTL_REASON)
    assert "check-passed" not in (rtl_item.get_attribute("class") or ""), "skipped 不得显示成已验证"
    # 阶段回执仍是 6 步，派生阶段明示 RTL 未替换（不隐藏该步）。
    flow = page.locator("#s0PhaseFlow")
    pw.expect(flow.locator("li")).to_have_count(6)
    pw.expect(flow).to_contain_text("RTL 未替换（环境项目入口）")
    pw.expect(flow).to_contain_text(ENV_RTL_REASON)
    pw.expect(flow).to_contain_text("三库冒烟")
    assert not [p for p in api["posts"] if p[0] != ENTRY]


def test_a2c_skipped_is_never_passed_for_rtl_folder_entry(ui):
    """§9.9-2：`rtl_folder` 入口出现 skipped 属异常 ⇒ 按“不当作通过”显示，不掩盖。"""
    page, api = ui
    rec = record()
    rec["checks"][1] = dict(rec["checks"][1], status="skipped", reason="异常：不应跳过 RTL 替换")
    route_entry(page, api, rec)
    prepare(page)
    rtl_item = page.locator("#s0Checks li").nth(1)
    pw.expect(rtl_item).to_contain_text("skipped（不当作通过）")
    pw.expect(rtl_item).to_contain_text("异常：不应跳过 RTL 替换")
    assert "check-passed" not in (rtl_item.get_attribute("class") or "")
    # 派生阶段不能因此显示“已验证”
    flow_status = page.locator("#s0PhaseFlow li").first.locator(".flow-status")
    pw.expect(flow_status).not_to_have_text("已验证")


# ---------------------------------------------------------------- A3 端口 waiting
def test_a3_ports_waiting_shows_diff_table_and_hint(ui):
    page, api = ui
    route_entry(page, api, record())
    page.route("**/api/s0/S0-T3-0001/advance",
               post_recorder(api, {"detail": {"error": "ports 未 passed：仍有未处置差异"},
                                   "ok": False}, status=400))
    prepare(page)
    ports = page.locator("#s0Ports")
    pw.expect(ports).to_contain_text("dma_controller")
    pw.expect(ports).to_contain_text("transfer_len")
    pw.expect(ports).to_contain_text("addr_width")
    pw.expect(ports).to_contain_text("new_fifo")
    pw.expect(ports).to_contain_text("提议来源未接入本入口，需既有提议/确认端点处置")
    advance = page.locator("#s0Advance")
    pw.expect(advance).to_be_visible()
    advance.click()
    page.wait_for_timeout(120)
    assert ("/api/s0/S0-T3-0001/advance", {}) in api["posts"]
    # 被拒绝时展示服务端原文，不吞。
    pw.expect(ports).to_contain_text("ports 未 passed：仍有未处置差异")


# ---------------------------------------------------------------- A4 切换成功 + 预填
def test_a4_ready_record_switches_then_prefills_setup(ui):
    page, api = ui
    rec = ready_record()
    state = {"env_root": "/fixture", "fail_remaining": 2, "failures": 0, "activated": False}
    api["views"]["T3-RUN"] = view("T3-RUN")

    def health(route):
        if state["fail_remaining"] > 0:
            state["fail_remaining"] -= 1
            state["failures"] += 1
            route.fulfill(status=503, json={"detail": {"error": "server restarting"}})
            return
        route.fulfill(json={"ok": True, "env_root": state["env_root"],
                            "plugin_missing": [], "workspace_missing": []})

    def activate(route):
        api["posts"].append((urlsplit(route.request.url).path, route.request.post_data_json))
        state["activated"] = True
        state["env_root"] = rec["work_env"]
        route.fulfill(status=202, json={"switch": {"status": "pending",
                                                   "target_env_root": rec["work_env"]}})

    def runs(route):
        if route.request.method == "POST":
            api["posts"].append((urlsplit(route.request.url).path, route.request.post_data_json))
            route.fulfill(json={"run_id": "T3-RUN"})
            return
        route.fulfill(json={"runs": [{"run_id": rid, "status": "waiting_gate", "mode": "drill"}
                                     for rid in api["views"]]})

    page.route("**/api/health", health)
    page.route("**/api/s0/" + rec["id"] + "/activate", activate)
    page.route("**/api/env/state", lambda route: route.fulfill(json={
        "env_root": state["env_root"], "env_id": "TCS9620-DERIVED",
        "origin_env_root": "/fixture", "switch": {}, "baseline_source": "/fixture"}))
    route_copies(page, [])
    page.route("**/api/baselines", lambda route: route.fulfill(json={
        "baselines": [{"id": "v1.2-stable", "valid": True, "cases": 162, "parent": "v1.1"}]}))
    page.route("**/api/env/check?**", lambda route: route.fulfill(json=ENV_OK))
    page.route("**/api/runs", runs)
    route_entry(page, api, rec)

    prepare(page)
    # 准出后自动调 activate（不需要人工点）。
    assert ("/api/s0/" + rec["id"] + "/activate", {}) in api["posts"], api["posts"]
    pw.expect(page.locator("#s0SwitchMsg")).to_contain_text("切换进行中")
    # 切换期轮询 /api/health：前几次失败被允许，最终成功。
    for _ in range(8):
        page.clock.run_for(900)
        page.wait_for_timeout(120)
        if page.locator("#viewSetup").is_visible():
            break
    pw.expect(page.locator("#viewSetup")).to_be_visible()
    assert state["failures"] > 0, "轮询必须允许失败（替身曾返回 503）"
    # sessionStorage 预填被 app.js 读取：基线选中 + 运行 payload 带 s0_record_id。
    # 裁决 1：prefill 还记录切换成功时的实际环境根（health.env_root）。
    raw = page.evaluate("sessionStorage.getItem('loop.s0Prefill')")
    assert json.loads(raw) == {"s0_record_id": rec["id"], "baseline": "v1.2-stable",
                               "env_root": rec["work_env"]}, raw
    page.locator("#btnRefreshBaselines").click()
    pw.expect(page.locator("#setupBaseline")).to_have_value("v1.2-stable")
    page.locator("#setupCheck").click()
    pw.expect(page.locator("#btnStart")).to_be_enabled()
    page.locator("#btnStart").click()
    page.wait_for_timeout(200)
    run_posts = [p for p in api["posts"] if p[0] == "/api/runs"]
    assert run_posts, api["posts"]
    payload = run_posts[0][1]
    assert payload["baseline"] == "v1.2-stable", payload
    assert payload["s0_record_id"] == rec["id"], payload


def test_a4b_prefill_kept_when_baseline_missing_from_list(ui):
    """预填基线不在可用列表：不清空、不崩、只给提示；s0_record_id 仍随运行提交。

    裁决 1（2026-10-30）：携带 `env_root` 的预填说明“运行在经 S0 派生的环境里”，
    因此不再依赖 baseline 命中基线列表（默认 baseline_version=RTL@… 本就不是基线 id）。
    """
    page, api = ui
    api["views"]["T3-RUN2"] = view("T3-RUN2")

    def runs(route):
        if route.request.method == "POST":
            api["posts"].append((urlsplit(route.request.url).path, route.request.post_data_json))
            route.fulfill(json={"run_id": "T3-RUN2"})
            return
        route.fulfill(json={"runs": [{"run_id": rid, "status": "waiting_gate", "mode": "drill"}
                                     for rid in api["views"]]})

    page.route("**/api/baselines", lambda route: route.fulfill(json={
        "baselines": [{"id": "v1.2-stable", "valid": True, "cases": 162, "parent": "v1.1"}]}))
    page.route("**/api/env/check?**", lambda route: route.fulfill(json=ENV_OK))
    page.route("**/api/runs", runs)
    page.evaluate("""() => sessionStorage.setItem('loop.s0Prefill', JSON.stringify(
        {s0_record_id: 'S0-T3-9999', baseline: 'v9.9-missing',
         env_root: '/TOOL/workspaces/fixture-derived-1'}))""")
    page.locator("#segSetup").click()
    page.locator("#btnRefreshBaselines").click()
    note = page.locator("#s0PrefillNote")
    pw.expect(note).to_be_visible()
    pw.expect(note).to_contain_text("S0-T3-9999")
    pw.expect(note).to_contain_text("v9.9-missing")
    pw.expect(note).to_contain_text("预填已保留")
    # 不崩：回落到列表里的第一个可用基线，且预填数据仍在（可人工改回）。
    pw.expect(page.locator("#setupBaseline")).to_have_value("v1.2-stable")
    raw = page.evaluate("sessionStorage.getItem('loop.s0Prefill')")
    assert json.loads(raw)["baseline"] == "v9.9-missing"
    # 裁决 1：基线没命中也要带 s0_record_id（判据是 env_root，不是列表命中）。
    page.locator("#setupCheck").click()
    pw.expect(page.locator("#btnStart")).to_be_enabled()
    page.locator("#btnStart").click()
    page.wait_for_timeout(200)
    run_posts = [p for p in api["posts"] if p[0] == "/api/runs"]
    assert run_posts, api["posts"]
    assert run_posts[0][1]["s0_record_id"] == "S0-T3-9999", run_posts[0][1]
    assert run_posts[0][1]["baseline"] == "v1.2-stable", run_posts[0][1]


# ---------------------------------------------------------------- A5 副本清单 + 二次确认
def test_a5_copies_list_reports_size_existence_and_confirms_delete(ui):
    page, api = ui
    copies = [
        {"id": "S0-T3-0001", "work_env": "/TOOL/workspaces/fixture-derived-1",
         "exists": True, "bytes": 2097152, "rtl_prefix": "RTL",
         "status": "prepared", "ready_for_execution": True},
        {"id": "S0-T3-0002", "work_env": "/TOOL/workspaces/fixture-derived-2",
         "exists": False, "bytes": 0, "rtl_prefix": "RTL/SRC",
         "status": "failed", "ready_for_execution": False},
    ]
    route_copies(page, copies)
    deletes = []

    def delete(route):
        deletes.append((route.request.method,
                        urlsplit(route.request.url).path,
                        urlsplit(route.request.url).query))
        route.fulfill(json={"deleted": True, "work_env": "/TOOL/workspaces/fixture-derived-1"})

    page.route("**/api/s0/*/copy**", delete)
    page.locator("#s0CopiesRefresh").click()
    listing = page.locator("#s0Copies")
    pw.expect(listing).to_contain_text("S0-T3-0001")
    pw.expect(listing).to_contain_text("/TOOL/workspaces/fixture-derived-2")
    pw.expect(listing).to_contain_text("2.0 MB")
    pw.expect(listing).to_contain_text("存在")
    pw.expect(listing).to_contain_text("缺失")
    pw.expect(listing).to_contain_text("已准出")
    dialogs = []
    page.once("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    listing.locator("button:has-text('删除副本')").first.click()
    page.wait_for_timeout(120)
    assert dialogs, "删除副本必须先弹二次确认"
    # 裁决 3（2026-10-30）：文案 = 实现语义（删副本目录/数据根与运行产物，保留记录与报告）。
    assert "副本目录（即派生环境的数据根）" in dialogs[0], dialogs
    assert "不可恢复" in dialogs[0], dialogs
    assert "准备记录与报告保留" in dialogs[0], dialogs
    assert not deletes, "取消确认时不得发写请求"
    page.once("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    listing.locator("button:has-text('删除副本')").first.click()
    page.wait_for_timeout(200)
    assert deletes and deletes[0][0] == "DELETE", deletes
    assert deletes[0][1] == "/api/s0/S0-T3-0001/copy", deletes
    assert "confirm=true" in deletes[0][2], deletes
    pw.expect(listing).to_contain_text("已删除副本")


# ---------------------------------------------------------------- A6 切回失败原文
def test_a6_switch_back_failure_shows_server_text(ui):
    page, api = ui
    route_env_state(page, {"env_root": "/TOOL/workspaces/fixture-derived-1",
                           "origin_env_root": "/fixture", "switch": {"status": "active"}})
    page.route("**/api/env/switch-back",
               post_recorder(api, {"detail": {"error": "存在非终态运行，拒绝切换：R-1"}}, status=409))
    page.locator("#s0SwitchRefresh").click()
    pw.expect(page.locator("#s0Switch")).to_contain_text("/fixture")
    page.locator("#s0SwitchBack").click()
    page.wait_for_timeout(120)
    assert ("/api/env/switch-back", {}) in api["posts"]
    pw.expect(page.locator("#s0SwitchMsg")).to_contain_text("存在非终态运行，拒绝切换：R-1")


def test_a6b_switch_back_success_clears_prefill(ui):
    """裁决 1：切回原始环境成功后必须清掉 prefill，避免回原环境后的运行仍挂旧 s0_record_id。"""
    page, api = ui
    state = {"env_root": "/TOOL/workspaces/fixture-derived-1"}

    def health(route):
        route.fulfill(json={"ok": True, "env_root": state["env_root"],
                            "plugin_missing": [], "workspace_missing": []})

    page.route("**/api/health", health)
    route_env_state(page, {"env_root": state["env_root"],
                           "origin_env_root": "/fixture", "switch": {"status": "active"}})
    page.evaluate("""() => sessionStorage.setItem('loop.s0Prefill', JSON.stringify(
        {s0_record_id: 'S0-T3-0002', baseline: 'v1.2-stable',
         env_root: '/TOOL/workspaces/fixture-derived-1'}))""")

    def switch_back(route):
        api["posts"].append((urlsplit(route.request.url).path, route.request.post_data_json))
        state["env_root"] = "/fixture"
        route.fulfill(status=202, json={"switch": {"status": "pending",
                                                   "target_env_root": "/fixture"}})

    page.route("**/api/env/switch-back", switch_back)
    page.locator("#s0SwitchRefresh").click()
    page.locator("#s0SwitchBack").click()
    for _ in range(8):
        page.clock.run_for(900)
        page.wait_for_timeout(120)
        if "已切回原始环境" in page.locator("#s0SwitchMsg").inner_text():
            break
    pw.expect(page.locator("#s0SwitchMsg")).to_contain_text("已切回原始环境")
    assert page.evaluate("sessionStorage.getItem('loop.s0Prefill')") is None


# ---------------------------------------------------------------- A7 无水平溢出
@pytest.mark.parametrize("width,height", [(1280, 720), (1440, 900), (390, 844)])
def test_a7_entry_containers_have_no_horizontal_overflow(ui, width, height):
    page, api = ui
    page.set_viewport_size({"width": width, "height": height})
    rec = record(ports={"status": "waiting",
                        "reason": "有端口差异未被任何 hunk 覆盖：dma_controller",
                        "table": [{"kind": "module", "module": "dma_controller_with_long_name",
                                   "added": ["transfer_len_extended"], "removed": ["addr_width"],
                                   "changed": ["burst_length"]},
                                  {"kind": "module_added", "module": "new_fifo"}],
                        "evidence": {}})
    route_entry(page, api, rec)
    route_copies(page, [{"id": "S0-T3-0001",
                         "work_env": "/TOOL/workspaces/fixture-derived-with-a-long-name-20261030",
                         "exists": True, "bytes": 2097152, "rtl_prefix": "RTL/SRC",
                         "status": "prepared", "ready_for_execution": True}])
    route_env_state(page, {"env_root": "/TOOL/workspaces/fixture-derived-with-a-long-name-20261030",
                           "origin_env_root": "/fixture", "switch": {"status": "pending"}})
    open_advanced(page)
    page.locator("#s0CopiesRefresh").click()
    prepare(page)
    page.wait_for_timeout(120)
    assert_fits(page, "#s0Entry .card, #s0Entry .btn, #s0Form .input")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
