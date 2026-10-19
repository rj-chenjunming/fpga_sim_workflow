"""集成修复的验收测试：人触发晋升（I8/N16）边界 + 拒绝语义。

覆盖审计阻断项 #14（I8 无真实晋升、无独立人触发）与 #21（N16 身份语义）的**边界**：
- 非 human actor 必须在**任何写盘之前**被拒（I6）；
- G3 未签 / 非人签 / defer 决策不得晋升；
- 触发人必须与 G3 签署者逐字一致；
- 真实路径必须给工具传 `--promote`（dry-run 只用于 drill）；
- 每次尝试（含被拒/成功）都留 `promote_result.json`；已成功过不得重复晋升。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

LOOP_DIR = Path(__file__).resolve().parents[1]
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))

from host import paths as P  # noqa: E402
from services import promote as svc  # noqa: E402

RUN_ID = "RUN-20261019-120000"


def _fake_g3(**over):
    g3 = {"status": "signed", "human_signed": True, "actor_kind": "human",
          "actor": "human:alice", "decision": "subset_only", "signed_at": "2026-10-19T12:00:00+0800"}
    g3.update(over)
    return g3


class _Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """把 run 目录与 G3 判定都换成可控假对象（不写权威环境）。"""
    runs = tmp_path / "runs"
    rd = runs / RUN_ID
    rd.mkdir(parents=True)
    monkeypatch.setattr(P, "KB_RUNS", runs)
    monkeypatch.setattr(P, "TOOL_ROOT", tmp_path)
    return rd


def test_promote_rejects_nonhuman_actor(fake_env):
    with pytest.raises(svc.PromoteError) as ei:
        svc.promote(RUN_ID, "model:bot")
    assert "I6" in str(ei.value)
    assert not (fake_env / "promote_result.json").exists(), "拒绝必须发生在写盘之前"


@pytest.mark.parametrize("over,needle", [
    ({"status": "pending"}, "尚未签署"),
    ({"human_signed": False, "actor_kind": "rehearsal"}, "不是人工签署"),
    ({"decision": "defer"}, "不允许晋升"),
])
def test_promote_requires_signed_human_and_promotable_g3(fake_env, monkeypatch, over, needle):
    # 走**真实** `_g3_record`（只替换权威读取），确保校验逻辑本身被测试到
    monkeypatch.setattr(svc.GA, "authority_view", lambda rid: {
        "present": True,
        "gates": {"G3_regression_decision": _fake_g3(**over)},
    })
    with pytest.raises(svc.PromoteError) as ei:
        svc.promote(RUN_ID, "human:alice")
    assert needle in str(ei.value)


def test_promote_requires_actor_equal_to_g3_signer(fake_env, monkeypatch):
    monkeypatch.setattr(svc, "_g3_record", lambda rid: _fake_g3(actor="human:alice"))
    with pytest.raises(svc.PromoteError) as ei:
        svc.promote(RUN_ID, "human:bob")
    assert "一致" in str(ei.value)


def test_promote_calls_tool_with_promote_flag_and_records_result(fake_env, monkeypatch):
    monkeypatch.setattr(svc, "_g3_record", lambda rid: _fake_g3())
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        return _Proc(0, out="[kb] promoted v1", err="")

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    rec = svc.promote(RUN_ID, "human:alice", reason="人工复核通过", now="2026-10-19T12:00:00+0800")

    assert rec["ok"] is True and rec["rc"] == 0
    assert "--promote" in seen["cmd"], seen["cmd"]
    assert "--dry-run" not in seen["cmd"], seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--trigger-by") + 1] == "human:alice"
    assert seen["cmd"][seen["cmd"].index("--actor-kind") + 1] == "human"
    saved = json.loads((fake_env / "promote_result.json").read_text(encoding="utf-8"))
    assert saved["actor"] == "human:alice" and saved["reason"] == "人工复核通过"


def test_promote_refusal_rc3_is_explicit_and_recorded(fake_env, monkeypatch):
    monkeypatch.setattr(svc, "_g3_record", lambda rid: _fake_g3())
    monkeypatch.setattr(svc.subprocess, "run", lambda cmd, **kw: _Proc(3, err="I4: 冲突未清零"))
    with pytest.raises(svc.PromoteError) as ei:
        svc.promote(RUN_ID, "human:alice")
    assert "rc=3" in str(ei.value)
    saved = json.loads((fake_env / "promote_result.json").read_text(encoding="utf-8"))
    assert saved["ok"] is False and saved["rc"] == 3
    assert "I4" in saved["stderr_tail"]


def test_promote_refuses_second_successful_promotion(fake_env, monkeypatch):
    monkeypatch.setattr(svc, "_g3_record", lambda rid: _fake_g3())
    monkeypatch.setattr(svc.subprocess, "run", lambda cmd, **kw: _Proc(0))
    svc.promote(RUN_ID, "human:alice")
    with pytest.raises(svc.PromoteError) as ei:
        svc.promote(RUN_ID, "human:alice")
    assert "已成功晋升过" in str(ei.value)


def test_promote_unknown_run_is_value_error(fake_env):
    with pytest.raises(ValueError):
        svc.promote("RUN-20990101-000000", "human:alice")


# ---------------------------------------------------------------- 闸门 API：I1 逐条处置透传

class _FakeManager:
    def __init__(self):
        self.docs = {RUN_ID: object()}
        self.captured = None

    async def decide(self, **kw):
        self.captured = kw
        return {"ok": True, "gate": kw["gate"], "decision": kw["decision"],
                "sign": {"rc": 0}, "entries": kw.get("entry_decisions") or {},
                "warnings": []}

    def run_view(self, run_id):
        return {"blockers": []}


def test_decision_api_passes_entry_decisions_through(monkeypatch):
    """I1：real 模式下 N2 有未决条目时，HTTP 必须能把逐条处置送到 decide()。"""
    from services import api

    fake = _FakeManager()
    monkeypatch.setattr(api, "_manager", lambda: fake)
    entries = {"0x0000#0x0004": {"decision": "confirmed", "reason": "已核对"}}
    resp = asyncio.run(api.submit_decision(
        RUN_ID, "G1_diff_confirm",
        {"decision": "confirmed", "actor": "human:alice", "reason": "逐条核对",
         "entry_decisions": entries},
    ))
    assert resp.status_code == 200
    assert fake.captured["entry_decisions"] == entries
    body = json.loads(resp.body)
    assert body["entries"] == entries


def test_decision_api_rejects_non_object_entry_decisions(monkeypatch):
    from fastapi import HTTPException
    from services import api

    fake = _FakeManager()
    monkeypatch.setattr(api, "_manager", lambda: fake)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(api.submit_decision(
            RUN_ID, "G1_diff_confirm",
            {"decision": "confirmed", "actor": "human:alice", "entry_decisions": ["not", "a", "dict"]},
        ))
    assert ei.value.status_code == 400
    assert fake.captured is None, "非法形状必须在调用 decide 之前被拒"
