"""SPEC-REV-01 R4/R2/R5 前端验收：全部节点可点、G1 before/after 双栏、S0 来源徽标。

真实静态页 + 受控 API（不模拟人工签署证据）：
  · 节点 chip → 独立 <dialog> 出现 → Esc 关闭 → 焦点回到 chip；
  · 轮询 1.5 s 重建四段流程不关闭/清空面板；
  · G1 每条差异有 before/after 双栏、行级 hunk（标行号）、encoding/夹具徽标与材料入口；
  · S0 来源徽标显示 s0_record_id 或「未经 S0 派生」，drill 不暗示环境就绪；
  · 窄屏无页面横向溢出。
"""
from __future__ import annotations

import pytest

from test_run_sessions import ui, static_url, select, tick, release, pw  # noqa: F401

GATE = "G1_diff_confirm"


def node_detail(node="N1", **overrides):
    data = {
        "run_id": "A", "node": node, "known": True, "kind": "host",
        "name": "输入摄取", "owner": "Host", "status": "ok",
        "started_at": 1792650932.891, "finished_at": 1792650933.5,
        "source": "drill_fixture",
        "summary": "N1：v0→v1，manifest 已产出",
        "detail": {"artifact": "/kb/runs/A/n1_manifest_new.json", "parent": "v0",
                   "allfiles_count": 3374, "cases_frozen": 162},
        "refs": ["/kb/runs/A/n1_manifest_new.json"],
        "events": [
            {"seq": 4, "kind": "node_started", "node": node, "status": "running",
             "ts": 1792650932.891},
            {"seq": 5, "kind": "node_finished", "node": node, "status": "ok",
             "ts": 1792650933.5, "detail": {"source": "drill_fixture"},
             "refs": ["/kb/runs/A/n1_manifest_new.json"]},
        ],
        "missing_fields": ["manifest_entries"],
        "authority": "projection",
    }
    data.update(overrides)
    return data


def failed_detail(node="N9_submit"):
    return {
        "run_id": "A", "node": node, "known": True, "kind": "host",
        "name": "提交全跑", "owner": "Host", "status": "failed",
        "started_at": 1792650940.0, "finished_at": 1792650941.0,
        "source": "kb_tool", "summary": "提交失败：模拟器不可用",
        "detail": {"error": "模拟器启动失败：UVS_LICENSE 未设置"},
        "refs": [],
        "events": [
            {"seq": 11, "kind": "node_started", "node": node, "status": "running",
             "ts": 1792650940.0},
            {"seq": 12, "kind": "node_failed", "node": node, "status": "failed",
             "ts": 1792650941.0, "detail": {"error": "模拟器启动失败：UVS_LICENSE 未设置"}},
        ],
        "missing_fields": [],
        "authority": "projection",
    }


def setup_run(api):
    v = api["views"]["A"]
    v.update(mode="drill", s0_record_id=None, baseline="v1.2-stable",
             node_history=[{"node": "N1", "status": "ok", "kind": "node_finished"},
                           {"node": "N6_apply", "status": "ok"},
                           {"node": "N9_submit", "status": "failed"},
                           {"node": "N15_select", "status": "ok"},
                           {"node": "N15_submit", "status": "ok"},
                           {"node": "HALT", "status": "halted"},
                           {"node": "N_FUTURE", "status": "ok"}])
    v["pending_interrupt"]["payload"]["gate"] = GATE
    api["nodes"][("A", "N1")] = node_detail()
    api["nodes"][("A", "N9_submit")] = failed_detail()
    return v


def open_run_view(page):
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()


def test_every_node_chip_opens_independent_dialog_and_escape_restores_focus(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)

    chip = page.locator('#viewRun [data-node-chip="N1"]')
    pw.expect(chip).to_be_visible()
    chip.click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndTitle")).to_contain_text("N1")
    # 五区块
    for heading in ("身份", "执行情况", "结果", "证据", "失败"):
        pw.expect(page.locator("#nodeDetail")).to_contain_text(heading)
    # 身份：服务端原值 + 来源/起止时间
    pw.expect(page.locator("#ndIdentity")).to_contain_text("drill_fixture")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("Host")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("2026-10-22")
    # 结果：summary + 结构化 detail
    pw.expect(page.locator("#ndSummary")).to_contain_text("N1：v0→v1")
    pw.expect(page.locator("#ndDetailBody")).to_contain_text("allfiles_count")
    # 执行情况：该节点事件切片，最近一条在前
    pw.expect(page.locator("#ndEvents")).to_contain_text("node_finished")
    seqs = page.locator("#ndEvents .nd-seq").all_inner_texts()
    assert seqs[:2] == ["#5", "#4"], seqs
    # 证据：存在性探测，不打开正文
    page.locator('#ndRefs button').first.click()
    pw.expect(page.locator("#ndRefs .nd-probe").first).to_contain_text("存在")
    # 未下发字段显式列出
    pw.expect(page.locator("#ndMissing")).to_contain_text("manifest_entries")
    # 固定诚实标注
    pw.expect(page.locator(".nd-foot")).to_contain_text("投影，非权威")

    # 轮询全量重建四段流程不得清掉/关闭面板
    tick(page)
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndTitle")).to_contain_text("N1")

    # Esc 关闭 + 焦点回到 chip
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator('#viewRun [data-node-chip="N1"]')).to_be_focused()

    # 键盘可达：Enter 打开、Space 打开
    page.locator('#viewRun [data-node-chip="N1"]').focus()
    page.keyboard.press("Enter")
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    page.locator('#viewRun [data-node-chip="N1"]').focus()
    page.keyboard.press(" ")
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    page.keyboard.press("Escape")
    assert not api["posts"], "节点面板不得产生写动作"


@pytest.mark.parametrize("node", ["N9_submit", "HALT", "N6_apply", "N15_submit", "N_FUTURE"])
def test_non_stage_and_unknown_nodes_are_clickable(ui, node):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    chip = page.locator(f'#viewRun [data-node-chip="{node}"]')
    chip.scroll_into_view_if_needed()
    chip.click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndSub")).to_contain_text(node)
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()


def test_failed_node_shows_error_text_and_never_claims_done(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N9_submit"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="N9_submit"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndFailure")).to_contain_text("模拟器启动失败：UVS_LICENSE 未设置")
    pw.expect(page.locator("#ndFailure")).to_contain_text("node_failed")
    # 状态原值，不折算「完成」
    pw.expect(page.locator("#ndStatus")).to_have_text("failed")
    pw.expect(page.locator("#nodeDetail")).not_to_contain_text("完成")
    page.keyboard.press("Escape")

    # 未知节点：known=false 空投影 + 原始事件，不 404、不静默不可点
    page.locator('#viewRun [data-node-chip="HALT"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="HALT"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndError")).to_contain_text("known=false")
    pw.expect(page.locator("#ndEvents")).to_contain_text("events 为空")


def test_stale_node_response_cannot_replace_reopened_panel(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    api["hold"] = lambda path: "/nodes/" in path

    page.locator('#viewRun [data-node-chip="N1"]').click()
    page.wait_for_timeout(80)
    assert len(api["pending"]) == 1, api["pending"]
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()

    # 重新打开：先回旧选择的过期回包，再回新请求；旧回包不得覆盖新面板
    api["nodes"][("A", "N1")] = node_detail(summary="N1：新请求的回包")
    page.locator('#viewRun [data-node-chip="N1"]').click()
    page.wait_for_timeout(80)
    assert len(api["pending"]) == 2
    release(page, api, node_detail(summary="N1：新请求的回包"), index=1)
    pw.expect(page.locator("#ndSummary")).to_contain_text("新请求的回包")
    release(page, api, node_detail(summary="N1：过期回包"), index=0)
    pw.expect(page.locator("#ndSummary")).to_contain_text("新请求的回包")
    pw.expect(page.locator("#ndSummary")).not_to_contain_text("过期回包")
    page.keyboard.press("Escape")


def test_gate_node_jumps_to_gate_view_and_model_node_offers_agent_window(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N3")] = node_detail(
        node="N3", name="差异语义总结", owner="analyst", source="model_standin",
        summary="3 组 / 27 条差异摘要", detail={"mode": "standin"})
    select(page, "A")
    open_run_view(page)

    # 闸门节点：可跳同源材料；Host 节点不提供 Agent 工作窗口入口
    page.locator('#viewRun [data-node-chip="N4"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#nodeDetail")).not_to_contain_text("打开 Agent 工作窗口")
    page.locator("#ndAgentJump button").click()
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator("#viewGate")).to_be_visible()

    # 模型节点：可跳 Agent 工作窗口（SPEC-REV-01 R6 边界）
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N3"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndAgentJump")).to_contain_text("打开 Agent 工作窗口")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("model_standin")
    page.keyboard.press("Escape")


def g1_payload(v):
    v["pending_interrupt"]["payload"]["entry_decisions_required"] = True
    v["pending_interrupt"]["payload"]["difference_items"] = {
        "present": True, "count": 2, "unresolved_count": 1, "unresolved_ids": ["D-002"],
        "entries": [
            {"entry_id": "D-001", "kind": "doc_entry", "change": "modified",
             "before": {"name": "dma_ctrl", "baud": 9600, "mode": "polling"},
             "after": {"name": "dma_ctrl", "baud": 115200, "mode": "polling"},
             "evidence": "doc/interface.md"},
            {"entry_id": "D-002", "kind": "rtl_file", "change": "modified",
             "segment": "sys_reg.v", "lines": [12], "encoding": "gbk",
             "drill_fixture": True,
             "before": "assign baud = 16'h0010;",
             "after": "assign baud = 16'h0064;",
             "diff_hunk": "@@ -11,3 +11,3 @@\n context line\n"
                           "-    assign baud = 16'h0010;\n"
                           "+    assign baud = 16'h0064;\n",
             "unresolved": "GBK 解码后仍需人工核对"},
        ],
    }
    v["pending_interrupt"]["payload"]["n3_digest"] = {
        "path": "/kb/runs/A/n3_digest.md", "exists": False}
    v["pending_interrupt"]["payload"]["host_trace"] = {
        "path": "/kb/runs/A/mock_change_applied.json", "exists": True,
        "changes": [{"id": "H-1", "kind": "mock", "old": "16'h0010", "new": "16'h0064",
                     "line_before": 12, "line_after": 12, "encoding": "gbk",
                     "rationale": "夹具替换寄存器默认值",
                     "evidence": "mock_change_applied.json"}]}


def test_g1_material_renders_before_after_hunk_encoding_and_entries(ui):
    page, api = ui
    v = setup_run(api)
    g1_payload(v)
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()

    material = page.locator("#gateMaterial")
    pw.expect(material.locator(".diff-item")).to_have_count(2)
    # 每条差异都有 before/after 双栏
    pw.expect(material.locator(".diff-pair")).to_have_count(2)
    pw.expect(material.locator(".diff-pane.before")).to_have_count(2)
    pw.expect(material.locator(".diff-pane.after")).to_have_count(2)
    pw.expect(material.locator(".diff-item").first.locator(".diff-text").first).to_contain_text("9600")
    pw.expect(material.locator(".diff-item").first.locator(".diff-pane.after .diff-text")).to_contain_text("115200")

    # doc_entry 变化字段先列，其余字段折叠
    first = material.locator(".diff-item").first
    pw.expect(first.locator(".diff-fields").first).to_contain_text("baud")
    pw.expect(first.locator(".diff-fields").first).to_contain_text("9600")
    pw.expect(first.locator(".diff-fields").first).to_contain_text("115200")
    pw.expect(first.locator(".diff-unchanged summary")).to_contain_text("其余字段未变（2 项）")

    # rtl_file 行级 hunk 带行号；encoding 与 drill 徽标
    second = material.locator(".diff-item").nth(1)
    pw.expect(second.locator(".diff-hunk")).to_be_visible()
    pw.expect(second.locator(".diff-hunk")).to_contain_text("16'h0064")
    line_numbers = second.locator(".diff-hunk .dh-no").all_inner_texts()
    assert "12" in line_numbers, line_numbers
    pw.expect(material).to_contain_text("编码 gbk（解码后对比）")
    pw.expect(material).to_contain_text("drill_fixture")
    pw.expect(material).to_contain_text("GBK 解码后仍需人工核对")
    # doc_entry 无 hunk 时显示原因，不是空白
    pw.expect(first.locator(".diff-nohunk")).to_contain_text("无行级 hunk")
    pw.expect(first.locator(".diff-nohunk")).to_contain_text("原因")

    # 材料入口：n3_digest 存在性（缺则未生成）+ Host 留痕 changes
    pw.expect(material).to_contain_text("n3_digest.md")
    pw.expect(material.locator(".material-extra").first).to_contain_text("未生成")
    pw.expect(material.locator(".host-trace-table")).to_contain_text("16'h0010 → 16'h0064")
    pw.expect(material.locator(".host-trace-table")).to_contain_text("夹具替换寄存器默认值")

    # 逐条处置未提供界面控件时必须显式提示"需走 API"，不让人盲签
    pw.expect(material).to_contain_text("该门要求逐条处置（entry_decisions）")
    pw.expect(material).to_contain_text("不得盲签")
    pw.expect(material.locator(".entry-decisions-sample")).to_contain_text("D-001")

    # 轮询重建材料后仍可判
    tick(page)
    pw.expect(page.locator("#gateMaterial .diff-pair")).to_have_count(2)
    pw.expect(page.locator("#gateMaterial .diff-hunk")).to_be_visible()


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_node_dialog_and_g1_material_have_no_page_overflow(ui, width):
    page, api = ui
    v = setup_run(api)
    g1_payload(v)
    page.set_viewport_size({"width": width, "height": 900})
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N1"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="N1"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = page.locator("#nodeDetail").bounding_box()
    assert box["width"] <= width + 1, box
    page.keyboard.press("Escape")


def test_s0_source_badge_distinguishes_record_from_drill(ui):
    page, api = ui
    v = setup_run(api)
    v["s0_record_id"] = "S0-20261022-01"
    select(page, "A")
    pw.expect(page.locator("#gateHead")).to_contain_text("S0 记录 S0-20261022-01")
    open_run_view(page)
    pw.expect(page.locator("#runHead")).to_contain_text("S0 记录 S0-20261022-01")
    pw.expect(page.locator("#runHead")).not_to_contain_text("未经 S0 派生")

    # drill 且无 S0 记录：显式「未经 S0 派生（drill 不覆盖 S0）」，不得暗示环境就绪
    api["views"]["B"]["mode"] = "drill"
    api["views"]["B"]["s0_record_id"] = None
    select(page, "B")
    open_run_view(page)
    pw.expect(page.locator("#runHead")).to_contain_text("未经 S0 派生（drill 不覆盖 S0）")
    pw.expect(page.locator("#runHead")).not_to_contain_text("环境就绪")
