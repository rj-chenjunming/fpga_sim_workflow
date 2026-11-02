"""G1 分流闸门 `G1_no_impact`（LOOP §14）的操作台渲染与提交拦截（软件层补充门）。

受控替身（复用 `test_run_sessions.ui`）：构造 pending 中断 `G1_no_impact:0`，
只想证明展示层可观察行为：
1. 闸门标题/节点来自 `GATE_META`（「闸门 1 分流 · 零必改…」/`N5b`）；
2. 两个决策按钮的文字**取自服务端** `gate_options`（不得前端手抄）；
3. 选 `no_impact_end` 时理由必填（空理由不发请求）；选 `full_regression` 不必填理由；
4. 提交体 `{decision, actor, reason}` 与所选一致。

判据来源：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §14 + `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md` §12。
"""
from __future__ import annotations

import pytest

from test_run_sessions import ui, static_url, select, pw  # noqa: F401

GATE = "G1_no_impact"
END_LABEL = "本变无影响用例，结束（须给理由）"
FULL_LABEL = "转全量回归"


def branch_options():
    return [
        {"value": "no_impact_end", "label": END_LABEL, "requires_reason": True},
        {"value": "full_regression", "label": FULL_LABEL, "requires_reason": False},
    ]


def open_branch_gate(page, api):
    view = api["views"]["A"]
    view["pending_interrupt"] = {
        "id": GATE + ":0", "type": "gate_decision",
        "payload": {"gate": GATE, "cycle": 0, "gate_node": "N5b",
                    "decision_options": branch_options()},
    }
    view["gate_options"] = {GATE: branch_options()}
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()
    pw.expect(page.locator('#gatePanel [aria-label="actor"]')).to_be_visible()


def test_head_and_options_render_from_server(ui):
    page, api = ui
    open_branch_gate(page, api)
    head = page.locator("#gateHead")
    pw.expect(head).to_contain_text("闸门 1 分流")
    pw.expect(head).to_contain_text("零必改")
    # 选项文字来自服务端下发（改文案即改这里）
    pw.expect(page.locator('#gatePanel input[value="no_impact_end"]')).to_be_attached()
    pw.expect(page.locator('#gatePanel input[value="full_regression"]')).to_be_attached()
    pw.expect(page.locator("#gatePanel")).to_contain_text(END_LABEL)
    pw.expect(page.locator("#gatePanel")).to_contain_text(FULL_LABEL)


def test_end_decision_requires_reason_and_does_not_post_without_it(ui):
    page, api = ui
    open_branch_gate(page, api)
    page.locator('#gatePanel input[value="no_impact_end"]').check()
    page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
    page.locator('#gatePanel [data-gate-submit]').click()
    pw.expect(page.locator("#gatePanel .gate-error")).to_contain_text("必须填写理由")
    assert not api["posts"]

    page.locator('#gatePanel [aria-label="裁决理由"]').fill("本变无影响用例，结束")
    page.locator('#gatePanel [data-gate-submit]').click()
    page.wait_for_timeout(80)
    assert api["posts"], "填了理由后应提交"
    path, body = api["posts"][0]
    assert path == f"/api/runs/A/gates/{GATE}/decision"
    assert body["decision"] == "no_impact_end"
    assert body["actor"] == "human:reviewer"
    assert body["reason"] == "本变无影响用例，结束"


def test_full_regression_does_not_require_reason(ui):
    page, api = ui
    open_branch_gate(page, api)
    page.locator('#gatePanel input[value="full_regression"]').check()
    page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
    page.locator('#gatePanel [data-gate-submit]').click()
    page.wait_for_timeout(80)
    assert api["posts"], "full_regression 无需理由，应直接提交"
    path, body = api["posts"][0]
    assert path == f"/api/runs/A/gates/{GATE}/decision"
    assert body["decision"] == "full_regression"
    assert body["actor"] == "human:reviewer"
