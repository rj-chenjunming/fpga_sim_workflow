"""F05：闸门会话判定纯函数的受控断言（node 驱动）。

`web/gate-session.js` 只做判定：身份 key、草稿协调、提交互斥。app.js 仍是唯一会话协调
owner（持有状态、渲染、发请求）。本文件不证明浏览器交互，只证明判定口径。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "gate-session.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const G = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def _pending(rid="A", iid="G1:0", gate="G1_diff_confirm", cycle=0):
    return {"id": iid, "gate": gate, "cycle": cycle, "runId": rid}


def test_session_key_is_identity_quadruple():
    key = _eval("G.sessionKey('A', {id:'G1:0', gate:'G1_diff_confirm', cycle:0})")
    assert json.loads(key) == ["A", "G1:0", "G1_diff_confirm", 0]
    other = _eval("G.sessionKey('A', {id:'G1:1', gate:'G1_diff_confirm', cycle:1})")
    assert key != other


def test_new_identity_creates_fresh_draft():
    out = _eval(
        "G.reconcile({key:'old', actor:'human:me', reason:'x'}, "
        "{runId:'A', pending:{id:'G1:0',gate:'G1_diff_confirm',cycle:0}, options:[{value:'confirmed'}]})"
    )
    assert out["changed"] is True
    draft = out["draft"]
    assert draft["actor"] == "human:"
    assert draft["reason"] == ""
    assert draft["decision"] is None
    assert json.loads(draft["key"]) == ["A", "G1:0", "G1_diff_confirm", 0]


def test_same_identity_keeps_draft_and_focus_inputs():
    first = _eval(
        "G.reconcile({key:null}, {runId:'A', "
        "pending:{id:'G1:0',gate:'G1_diff_confirm',cycle:0}, options:[{value:'confirmed'},{value:'ignored'}]})"
    )
    draft = first["draft"]
    draft["actor"] = "human:reviewer"
    draft["reason"] = "reviewed"
    draft["decision"] = "ignored"
    out = _eval(
        "G.reconcile(" + json.dumps(draft) + ", {runId:'A', "
        "pending:{id:'G1:0',gate:'G1_diff_confirm',cycle:0}, "
        "options:[{value:'confirmed'},{value:'ignored'}]})"
    )
    assert out["changed"] is False
    assert out["draft"]["actor"] == "human:reviewer"
    assert out["draft"]["reason"] == "reviewed"
    assert out["draft"]["decision"] == "ignored"


def test_withdrawn_option_clears_decision_only():
    key = _eval("G.sessionKey('A', {id:'G1:0', gate:'G1_diff_confirm', cycle:0})")
    draft = {
        "key": key,
        "gate": "G1_diff_confirm", "decision": "ignored", "actor": "human:reviewer",
        "reason": "reviewed", "submitting": False, "error": None, "blockers": None, "note": None,
    }
    out = _eval(
        "G.reconcile(" + json.dumps(draft) + ", {runId:'A', "
        "pending:{id:'G1:0',gate:'G1_diff_confirm',cycle:0}, options:[{value:'confirmed'}]})"
    )
    assert out["changed"] is False
    assert out["draft"]["decision"] is None, "服务端撤回的选项必须清空，不得继续提交"
    assert out["draft"]["reason"] == "reviewed", "清空决策不得丢草稿"


def test_submission_mutex_is_per_identity():
    ledger = {}
    assert _eval("G.isSubmitting({}, 'k1')") is False
    assert _eval("G.beginSubmission({}, 'k1').started") is True
    ledger = json.loads(_eval("JSON.stringify(G.beginSubmission({}, 'k1').ledger)"))
    assert _eval("G.isSubmitting(" + json.dumps(ledger) + ", 'k1')") is True
    # 同身份重复提交不再开始（前端幂等）
    assert _eval("G.beginSubmission(" + json.dumps(ledger) + ", 'k1').started") is False
    # 其他身份不受影响
    both = json.loads(_eval("JSON.stringify(G.beginSubmission(" + json.dumps(ledger) + ", 'k2').ledger)"))
    assert _eval("G.isSubmitting(" + json.dumps(both) + ", 'k2')") is True
    ended = json.loads(_eval("JSON.stringify(G.endSubmission(" + json.dumps(both) + ", 'k1'))"))
    assert _eval("G.isSubmitting(" + json.dumps(ended) + ", 'k1')") is False
    assert _eval("G.isSubmitting(" + json.dumps(ended) + ", 'k2')") is True


def test_same_selection_checks_all_three_identity_parts():
    a = {"runId": "A", "epoch": 1, "request": 2}
    b = {"runId": "A", "epoch": 1, "request": 2}
    assert _eval("G.sameSelection(" + json.dumps(a) + "," + json.dumps(b) + ")") is True
    for field, value in (("runId", "B"), ("epoch", 2), ("request", 3)):
        mutated = dict(a)
        mutated[field] = value
        assert _eval("G.sameSelection(" + json.dumps(a) + "," + json.dumps(mutated) + ")") is False


def test_frontend_consumes_single_gate_session_module():
    app = (WEB / "app.js").read_text(encoding="utf-8")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "function gateSessionKey" not in app, "app.js 不得保留第二套身份判定"
    assert "window.GateSession" in app
    assert html.index("gate-session.js") < html.index("app.js")


# ---------------------------------------------------------------- 逐条处置（SPEC-04 §4.4 2026-10-23）
# 口径必须与 gates.normalize_entry_decisions 一致：有 disputed ⇒ disputed；
# 否则有 ignored ⇒ ignored；否则 confirmed；未选完 ⇒ null（不猜）。

def test_derive_entry_decision_follows_authority_order():
    cases = {
        '["confirmed","confirmed"]': "confirmed",
        '["confirmed","ignored"]': "ignored",
        '["ignored","disputed"]': "disputed",
        '["disputed"]': "disputed",
    }
    for expr, want in cases.items():
        assert _eval("G.deriveEntryDecision(" + expr + ")") == want
    # 未选完 / 非法值 ⇒ null，不得用默认值补齐
    assert _eval("G.deriveEntryDecision(['confirmed', null])") is None
    assert _eval("G.deriveEntryDecision([])") is None
    assert _eval("G.deriveEntryDecision(['nope'])") is None


def test_validate_entry_decisions_requires_full_coverage_and_reasons():
    ids = ["a.v", "b.v"]
    ok = json.loads(_eval(
        "JSON.stringify(G.validateEntryDecisions("
        + json.dumps({"a.v": {"decision": "confirmed"}, "b.v": {"decision": "ignored", "reason": "仅注释"}})
        + "," + json.dumps(ids) + ",['confirmed','ignored','disputed']))"
    ))
    assert ok["ok"] is True
    assert ok["entry_decisions"]["b.v"] == {"decision": "ignored", "reason": "仅注释"}

    missing = json.loads(_eval(
        "JSON.stringify(G.validateEntryDecisions("
        + json.dumps({"a.v": {"decision": "confirmed"}})
        + "," + json.dumps(ids) + ",['confirmed','ignored','disputed']))"
    ))
    assert missing["ok"] is False
    assert "未覆盖" in missing["error"]

    no_reason = json.loads(_eval(
        "JSON.stringify(G.validateEntryDecisions("
        + json.dumps({"a.v": {"decision": "disputed"}, "b.v": {"decision": "confirmed"}})
        + "," + json.dumps(ids) + ",['confirmed','ignored','disputed']))"
    ))
    assert no_reason["ok"] is False
    assert "必须填写理由" in no_reason["error"]

    bad_value = json.loads(_eval(
        "JSON.stringify(G.validateEntryDecisions("
        + json.dumps({"a.v": {"decision": "accept"}, "b.v": {"decision": "confirmed"}})
        + "," + json.dumps(ids) + ",['confirmed','ignored','disputed']))"
    ))
    assert bad_value["ok"] is False
    assert "非法" in bad_value["error"]
