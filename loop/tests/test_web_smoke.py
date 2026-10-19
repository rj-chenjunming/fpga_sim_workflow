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
