"""F02-c：能力事实的**唯一**前端格式化实现（node 驱动）。

app.js 与 agent-window.js 都只调用 `web/capabilities.js`；未知维度显示「未知」，
`idle`/`standin` 不得显示为真实完成。本文件不证明浏览器渲染，只证明格式化口径。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "capabilities.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _line(caps):
    script = (
        "const C = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(C.line(" + json.dumps(caps) + ")));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def test_unknown_dimensions_are_shown_as_unknown():
    text = _line({"implemented": True, "dependencies_ready": None,
                  "execution": "not_started", "verification_scope": None})
    assert "已实现" in text
    assert "依赖 未知" in text
    assert "本次 未开始" in text
    assert "验证范围 未知" in text


def test_not_implemented_and_missing_dependencies_are_explicit():
    text = _line({"implemented": False, "dependencies_ready": False,
                  "execution": "unknown", "verification_scope": "单元"})
    assert "未实现" in text
    assert "依赖 缺失" in text
    assert "本次 未知" in text
    assert "验证范围 单元" in text


@pytest.mark.parametrize("execution,label", [
    ("standin", "替身"), ("real", "真实"), ("not_started", "未开始"),
    ("unknown", "未知"), ("something-new", "未知"),
])
def test_execution_values_are_server_facts(execution: str, label: str):
    text = _line({"implemented": True, "dependencies_ready": None,
                  "execution": execution, "verification_scope": None})
    assert f"本次 {label}" in text


def test_standin_is_not_reported_as_real_completion():
    standin = _line({"implemented": True, "dependencies_ready": None,
                     "execution": "standin", "verification_scope": None})
    assert "真实" not in standin and "已完成" not in standin


def test_missing_capabilities_render_nothing():
    assert _line(None) == ""
    assert _line({}) == ""


def test_frontend_has_one_formatter_and_both_consumers_use_it():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    window = (WEB / "agent-window.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "function capabilityLine" not in app, "app.js 不得保留第二套格式化"
    assert "window.Capabilities.line" in app
    assert "window.Capabilities.line" in window
    assert html.index("capabilities.js") < html.index("app.js")
    assert html.index("capabilities.js") < html.index("agent-window.js")
