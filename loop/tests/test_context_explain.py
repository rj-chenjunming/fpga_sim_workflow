"""F10/F11：上下文与尝试的只读解释（node 纯函数）。

证明：字节/占比按记录事实计算；经验原因只读展示；尝试差异只看输入顶层字段；
token 估算保持「未知」；展示层不读全局、不发请求。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "context-explain.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const C = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def test_byte_length_is_utf8_not_characters():
    assert _eval("C.byteLength('中')") == 3
    assert _eval("C.byteLength('abc')") == 3
    assert _eval("C.byteLength('')") == 0


def test_budget_rows_come_from_recorded_fields():
    request = {"input": {"diff": "中"}, "info": "规则", "instruct": "指令",
               "schema": {"type": "object"}}
    out = _eval("C.budget(" + json.dumps(request) + ", 120000)")
    labels = [row["label"] for row in out["rows"]]
    assert labels == ["input", "info", "instruct", "schema"]
    assert out["totalBytes"] == sum(row["bytes"] for row in out["rows"])
    assert out["limitBytes"] == 120000
    for row in out["rows"]:
        assert row["bytes"] > 0
        assert 0 <= row["percent"] <= 100
    assert out["tokenEstimate"] == "unknown"


def test_budget_without_fields_is_empty_and_unknown():
    out = _eval("C.budget({}, null)")
    assert out["rows"] == []
    assert out["totalBytes"] == 0
    assert out["limitBytes"] is None
    assert out["usage"] == "unknown"


def test_budget_usage_percent_uses_limit_when_known():
    request = {"input": "x" * 100}
    out = _eval("C.budget(" + json.dumps(request) + ", 1000)")
    assert out["usage"] == "known"
    assert out["usedPercent"] is not None


def test_experience_reasons_are_read_only_list():
    request = {"experience_diagnostics": ["mask-lesson: source changed", "x: rejected"]}
    out = _eval("C.experience(" + json.dumps(request) + ")")
    assert [row["message"] for row in out] == ["mask-lesson: source changed", "x: rejected"]
    assert _eval("C.experience({})") == []
    assert _eval('C.experience({"experience_diagnostics": null})') == []


def test_attempt_rows_sort_and_show_unknowns():
    attempts = [{"attempt": 2, "status": "validated", "model": "m", "cycle": 1},
                {"attempt": 1, "status": "incomplete"}]
    out = _eval("C.attempts(" + json.dumps(attempts) + ")")
    assert [row["attempt"] for row in out] == [1, 2]
    assert out[0]["model"] == "未知"
    assert out[0]["cycle"] == "未知"


def test_input_diff_reports_changed_added_and_removed_keys():
    prev = {"diffs": [], "human_interventions": [{"message": "old"}]}
    curr = {"diffs": [{"entry_id": "a"}], "human_interventions": [{"message": "old"}]}
    out = _eval("C.inputDiff(" + json.dumps(prev) + "," + json.dumps(curr) + ")")
    assert out["changed"] is True
    keys = [row["key"] for row in out["rows"]]
    assert keys == ["diffs"]
    assert out["rows"][0]["fromBytes"] < out["rows"][0]["toBytes"]

    added = _eval("C.inputDiff({}, {'new': 'x'})")
    assert [row["key"] for row in added["rows"]] == ["new"]
    removed = _eval("C.inputDiff({'old': 'x'}, {})")
    assert [row["key"] for row in removed["rows"]] == ["old"]

    same = _eval("C.inputDiff(" + json.dumps(prev) + "," + json.dumps(prev) + ")")
    assert same == {"changed": False, "rows": []}


def test_token_estimate_stays_unknown():
    assert _eval("C.tokenEstimate()") == "unknown"


def test_window_and_api_wire_the_read_only_explainer():
    window = (WEB / "agent-window.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "window.ContextExplain" in window
    # 接线必须传记录本身（字段在 request 顶层），不能只传嵌套 input（F10F11 复核必改 1）
    assert "X.budget(request, limit)" in window
    assert "X.budget(request.input" not in window
    assert "try {" in window and "explain(view)" in window, "展示失败不得阻断基本观察"
    assert html.index("context-explain.js") < html.index("agent-window.js")
    assert 'id="awBudget"' in html and 'id="awAttempts"' in html


def test_budget_record_shape_matches_what_window_passes():
    """按真实记录形状（字段在顶层）验证窗口调用的实参语义。"""
    record = {"input": {"diff": "中"}, "info": "规则", "instruct": "指令",
              "schema": {"type": "object"}, "offered": {"cases": ["a"]},
              "scope": {"env_id": "e"}}
    out = _eval("C.budget(" + json.dumps(record) + ", 1000)")
    assert [row["label"] for row in out["rows"]] == \
        ["input", "info", "instruct", "schema", "offered", "scope"]
    assert out["totalBytes"] > 0
