"""Web 冒烟测试（A7/A8）：页面可服务、零外链、legacy 可用、关键容器存在。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.api import app


def _get(path: str) -> str:
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response.text


def test_index_has_app_containers_and_no_external_assets() -> None:
    html = _get("/")
    for element_id in (
        'id="app"',
        'id="sidebar"',
        'id="runList"',
        'id="viewSetup"',
        'id="viewRun"',
        'id="viewGate"',
        'id="stages"',
        'id="agents"',
        'id="gatePanel"',
    ):
        assert element_id in html, f"缺少关键容器：{element_id}"
    assert "http://" not in html and "https://" not in html, "页面不得引用外部资源"


def test_static_assets_are_local_and_served() -> None:
    assert "app.js" in _get("/")
    js = _get("/app.js")
    assert "fetch(" in js
    assert "http://" not in js and "https://" not in js, "JS 不得引用外部资源"
    _get("/app.css")


def test_legacy_ui_still_served() -> None:
    html = _get("/legacy.html")
    assert "闸门操作台" in html, "旧界面必须保留一个迭代"


def test_gate_material_script_renders_n2_diff_entries() -> None:
    """G1 的「逐条差异」必须在页面上可见（否则 I1 的逐条核对只能空口 attestation）。

    这是**投影渲染契约**的静态断言：投影字段由后端下发（见 test_api_ui_contract 的
    `test_gate_material_projection_has_diff_entries`），前端必须消费它们。
    """
    js = _get("/app.js")
    for token in (
        "difference_items",
        "unresolved_entries",
        "renderDiffEntries",
        "diff-item",
    ):
        assert token in js, f"app.js 缺少差异清单渲染：{token}"
    css = _get("/app.css")
    assert ".diff-item" in css, "app.css 缺少差异条目样式"


def test_gate_view_has_entry_decision_controls() -> None:
    """G1 逐条处置必须有界面输入通道（SPEC-04 §4.4，2026-10-23 增补）。

    `entry_decisions_required=true` 时，闸门表单必须为每个唯一 entry_id 渲染控件，
    提交 payload 必须带 `entry_decisions`；选项一律取服务端下发，前端不得手抄枚举。
    **2026-10-26（R1+R2）**：该 flag 的判据唯一在服务端（WEB_UI_SPEC §4.4「判据归属」），
    前端只消费 flag，不得再按 `pending.gate` 自判——否则控件渲染/就绪判定/紧凑卡引导/
    节点面板 bridge 会各写一套判据，并出现"引导用户去没有控件的地方"的死角。
    """
    js = _get("/app.js")
    for token in (
        "entryDecisionsRequired",
        "renderEntryDecisionControls",
        "deriveEntryDecision",
        "validateEntryDecisions",
        "entry_decisions",
        "gate-entry",
    ):
        assert token in js, f"app.js 缺少逐条处置通道：{token}"
    assert "entryGateRequires" not in js, (
        "前端不得自判「哪道门要逐条处置」——判据归服务端 entry_decisions_required"
        "（WEB_UI_SPEC §4.4 判据归属；红线 8 口径唯一）"
    )
    css = _get("/app.css")
    assert ".gate-entry" in css, "app.css 缺少逐条处置控件样式"


def test_gate_reason_preflight_consumes_server_flags_only() -> None:
    """复核建议 A/B（2026-10-26）：

    A：报告结论的来源必须可见 —— 否则 drill 夹具（报告无 claimed_verdict 行）会出现
       "界面显示未通过、选项说无需理由"而无任何解释。
    B：中断载荷里的 decision_options 只是快照，界面不得拿它做前置判断（视图每次重算）。
    """
    js = _get("/app.js")
    assert "claimed_verdict_source" in js, "报告结论来源未在界面暴露（建议 A）"
    assert "payload.decision_options" not in js, (
        "界面不得消费中断载荷里的 decision_options 快照（建议 B）："
        "应以运行视图重算的 gate_options 为准"
    )
