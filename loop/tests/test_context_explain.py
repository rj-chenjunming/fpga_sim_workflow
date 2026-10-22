"""F10/F11 + R5：上下文与尝试的只读解释（node 纯函数）。

证明：预算**只消费 Host 的测量**（不另求和/占比/上限判断）；经验原因只读展示；
尝试差异只看输入顶层字段；token 估算保持「未知」；展示层不读全局、不发请求。
跨层断言：同一已封存请求的 `AM.check_budget` == API `context_budget` == 窗口显示总量。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from services import api

from test_agent_context_memory import call, ctx, provider  # noqa: F401

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


def host_measure(**overrides) -> dict:
    """一份 Host 下发形状的 context_budget（数值由 Host 测量；窗口不得自行推导）。"""
    measure = {"measured": True, "used_bytes": 100,
               "breakdown": {"input": 60, "info": 10, "instruct": 10, "schema": 10},
               "overhead_bytes": 10, "limit_bytes": 120000, "used_percent": 0,
               "usage": "known", "storage": {"offered_bytes": 900, "scope_bytes": 155},
               "token_estimate": "unknown", "attempt": 1}
    measure.update(overrides)
    return measure


def test_byte_length_is_utf8_not_characters():
    assert _eval("C.byteLength('中')") == 3
    assert _eval("C.byteLength('abc')") == 3
    assert _eval("C.byteLength('')") == 0


def test_budget_only_consumes_host_numbers_without_resumming():
    out = _eval("C.budget(" + json.dumps(host_measure()) + ")")
    assert [row["label"] for row in out["rows"]] == ["input", "info", "instruct", "schema"]
    assert [row["bytes"] for row in out["rows"]] == [60, 10, 10, 10]
    # 总量直接取 Host 的 used_bytes；不出现前端求和/占比（红线 8）
    assert out["totalBytes"] == 100
    assert out["overheadBytes"] == 10
    assert out["usedPercent"] == 0
    assert out["limitBytes"] == 120000
    assert out["usage"] == "known"
    assert out["tokenEstimate"] == "unknown"
    for row in out["rows"]:
        assert "percent" not in row, "占比必须由 Host 下发，前端不得另算"


def test_storage_sizes_are_reported_separately_from_billing():
    out = _eval("C.budget(" + json.dumps(host_measure()) + ")")
    # offered/scope 是记录存储大小：不在计费行里，单列
    assert "offered" not in [row["label"] for row in out["rows"]]
    assert "scope" not in [row["label"] for row in out["rows"]]
    assert out["storage"] == {"offeredBytes": 900, "scopeBytes": 155}
    assert out["totalBytes"] == 100, "存储大小不得计入预算总量"


def test_unmeasured_record_stays_unknown():
    """旧记录缺计费材料 ⇒ Host 判未知；窗口不得用自身字节数冒充。"""
    measure = {"measured": False, "used_bytes": None, "breakdown": {}, "overhead_bytes": None,
               "limit_bytes": 120000, "used_percent": None, "usage": "unknown",
               "storage": {"offered_bytes": None, "scope_bytes": None},
               "token_estimate": "unknown", "attempt": None}
    out = _eval("C.budget(" + json.dumps(measure) + ")")
    assert out["measured"] is False
    assert out["rows"] == []
    assert out["totalBytes"] is None
    assert out["overheadBytes"] is None
    assert out["usage"] == "unknown"
    assert out["tokenEstimate"] == "unknown"


def test_unknown_limit_has_no_fake_percent():
    measure = host_measure(limit_bytes=None, used_percent=None, usage="unknown")
    out = _eval("C.budget(" + json.dumps(measure) + ")")
    assert out["measured"] is True
    assert out["limitBytes"] is None
    assert out["usedPercent"] is None, "上限未知时不得显示假比例"
    assert out["usage"] == "unknown"


def test_empty_measure_is_unknown():
    out = _eval("C.budget(null)")
    assert out["rows"] == [] and out["totalBytes"] is None and out["usage"] == "unknown"


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
    # 窗口只把 Host 下发的 context_budget 交给纯函数，不传记录、不自己数
    assert "X.budget(view.context_budget)" in window
    assert "X.budget(request" not in window
    assert "try {" in window and "explain(view)" in window, "展示失败不得阻断基本观察"
    assert html.index("context-explain.js") < html.index("agent-window.js")
    assert 'id="awBudget"' in html and 'id="awAttempts"' in html


def test_explainer_keeps_no_second_billing_criterion():
    """纯函数层不得保留字段清单/求和：计费分项与总量都来自 Host（红线 8）。"""
    import re
    source = MODULE.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)  # 只看代码，不看注释
    assert "FIELDS" not in code
    assert "total +=" not in code
    assert "jsonBytes(request[" not in code
    assert "offered" not in code.split("function storage")[0], \
        "offered/scope 只能出现在 Host 下发的 storage 里，不能进计费行"


async def test_cross_layer_host_budget_matches_api_and_window(ctx, provider, monkeypatch):  # noqa: F811
    """R5 验收：同一已封存请求，AM.check_budget == API used_bytes == 窗口显示总量。"""
    from host import agent_memory as AM
    await call(ctx, input_data={"run_id": ctx.run_id, "diffs": [],
                                "note": "中文与转义 \"q\"\n第二行",
                                "human_interventions": [{"actor": "human:a", "message": "补充"}]})
    attempt = next((ctx.run_dir / "agent_calls" / "N3").iterdir())
    request = AM.verify_attempt(attempt)["request"]
    expected = AM.check_budget(request["input"],
                               {k: request[k] for k in ("info", "instruct", "schema")})
    manager = SimpleNamespace(
        docs={ctx.run_id: SimpleNamespace(run_dir=str(ctx.run_dir))},
        _progress=lambda _run: SimpleNamespace(read=lambda: []),
    )
    monkeypatch.setattr(api, "_manager", lambda: manager)
    client = TestClient(api.app)
    body = client.get(f"/api/runs/{ctx.run_id}/agents/N3").json()
    measure = body["context_budget"]
    # ① API 下发 Host 的测量，而不是前端可另算的原始记录
    assert measure["measured"] is True
    assert measure["used_bytes"] == expected
    assert measure["limit_bytes"] == AM.MAX_CONTEXT_BYTES
    assert set(measure["breakdown"]) == {"input", "info", "instruct", "schema"}
    assert sum(measure["breakdown"].values()) + measure["overhead_bytes"] == measure["used_bytes"]
    assert measure["token_estimate"] == "unknown"
    assert measure["attempt"] == 1
    # ② 记录存储大小（offered/scope 未发送给模型）单列、不计费
    assert measure["storage"]["offered_bytes"] == len(AM.encoded(request["offered"]))
    assert measure["storage"]["scope_bytes"] == len(AM.encoded(request["scope"]))
    assert measure["storage"]["offered_bytes"] > 0 and measure["storage"]["scope_bytes"] > 0
    # offered/scope 不计费：总量仍等于 Host 准入字节
    assert measure["used_bytes"] == expected
    # ③ 窗口显示总量与 Host 准入字节完全相同（不是行求和）
    shown = _eval("C.budget(" + json.dumps(measure) + ")")
    assert shown["totalBytes"] == expected
    assert shown["overheadBytes"] == measure["overhead_bytes"]
    assert shown["usedPercent"] == measure["used_percent"]
    assert [row["bytes"] for row in shown["rows"]] == \
        [measure["breakdown"][k] for k in ("input", "info", "instruct", "schema")]
    assert shown["tokenEstimate"] == "unknown"
