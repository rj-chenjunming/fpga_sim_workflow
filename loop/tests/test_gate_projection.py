"""闸门投影的信任面：权威态 / 锚 / 对账，以及「拒绝不得写账本」「now 必须生效」。

动机（v1 真实 HTTP 终验 phase 1 的实测发现）：

1. **F-V1-02**：操作台的「闸门历史」原先是**事件流**投影 —— `actor` 是 HTTP 请求体里的
   **自报**字符串，既无 `human_signed` 也无 `actor_kind`；而前端 `renderGateHistory`
   恰恰在渲染 `json.actor_kind` ⇒ **徽章恒空**。于是"这道闸门到底是不是人类签的"
   这个操作台最该回答的问题，界面上答不了。权威只有一个：`gates.json` + `gates.sha256`。
2. **F-V1-01**：`RunManager.decide()` 原顺序是「先 `gate.py sign` 落权威、后查有无待处理中断」
   ⇒ 闸门已被决策时（双击按钮 / 两个标签页），`gates.json` 会追加一条**孤儿签名**，
   而执行侧毫无动作，用户只看到一个 400。违反本层自己的「拒绝必须发生在提交前」（§4.4）。
3. **F-V1-03**：`start(now=...)` 声明了却没用；`/api/runs` 收下 `now` 后**静默丢弃**，
   run_id 实际来自 `LOOP_NOW`/`KB_NOW` 或墙钟 ⇒ 调用方以为定住了身份，实际拿到另一个 run。
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from host import gate_authority as GA
from host import paths as P
from services import contracts
from services.api import app

HUMAN = "human:proj-test"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _new_run(client: TestClient, **kw) -> str:
    body = {"baseline": "v0", "mode": "drill"}
    body.update(kw)
    r = client.post("/api/runs", json=body)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def _wait_interrupt(client: TestClient, rid: str, prefix: str, *, timeout: float = 25.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = client.get(f"/api/runs/{rid}").json()
        if ((view.get("pending_interrupt") or {}).get("id") or "").startswith(prefix):
            return view
        if view.get("status") == "failed":
            raise AssertionError(f"运行失败：{view.get('error')}")
        time.sleep(0.3)
    raise AssertionError(f"未在 {timeout}s 内到达 {prefix}")


def _ledger(rid: str) -> dict:
    return json.loads((P.KB_RUNS / rid / "gates.json").read_text(encoding="utf-8"))


def test_decision_response_gate_state_is_authority_not_process_record(client: TestClient) -> None:
    """`gate_state` 必须真的是闸门态。

    v1 终验发现：该字段原先装的是 `gate.py` 的**子进程调用记录**（cmd/rc/stdout_tail）
    ⇒ 读 `gate_state.human_signed` 得到 undefined，界面在签署后看不出是否人签。
    """
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1")
    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "confirmed", "actor": HUMAN, "reason": "字段名核对"})
    assert r.status_code == 200, r.text
    body = r.json()

    gs = body["gate_state"]
    assert gs["human_signed"] is True
    assert gs["actor_kind"] == "human"
    assert gs["status"] == "signed"
    assert gs["history_len"] == 1
    assert "cmd" not in gs, "gate_state 里不得再是子进程记录"
    assert body["gate_tool"]["rc"] == 0 and "cmd" in body["gate_tool"]
    assert body["gates_authority"]["anchor_ok"] is True


def test_view_projects_authority_not_just_events(client: TestClient) -> None:
    """F-V1-02：视图必须带**权威**闸门态（含 human_signed / actor_kind / 锚）。"""
    rid = _new_run(client)
    view = _wait_interrupt(client, rid, "G1")

    au = view["gates_authority"]
    assert au["present"] is True, au
    assert au["anchor_ok"] is True, au          # 新状态必须带可复算锚
    assert "锚一致" in au["anchor_detail"]
    assert set(au["gates"]) == set(GA.gate_ids())

    g1 = au["gates"]["G1_diff_confirm"]
    assert g1["human_signed"] is False
    assert g1["status"] == "pending"
    assert g1["actor_kind"] is None
    assert g1["history_len"] == 0

    # 事件流投影**本身**确实缺 human_signed（这就是为什么必须另有权威态）
    assert view["gate_history"] == []
    assert all("human_signed" not in e for e in view["gate_history"])

    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "confirmed", "actor": HUMAN, "reason": "投影测试"})
    assert r.status_code == 200, r.text

    after = client.get(f"/api/runs/{rid}").json()
    au2 = after["gates_authority"]
    g1b = au2["gates"]["G1_diff_confirm"]
    assert g1b["human_signed"] is True
    assert g1b["actor_kind"] == "human"
    assert str(g1b["actor"]).startswith("human:")
    assert g1b["status"] == "signed"
    assert g1b["history_len"] == 1
    assert au2["anchor_ok"] is True
    assert au2["human_signed_all"] is False       # G2/G3 还没签
    assert au2["divergences"] == []               # 正常路径不得报分歧


def test_double_decide_leaves_no_orphan_signature(client: TestClient) -> None:
    """F-V1-01：闸门已被决策后再提交，必须**先拒后签**，账本一个字节都不动。"""
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1")

    r1 = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                     json={"decision": "confirmed", "actor": HUMAN, "reason": "第一次"})
    assert r1.status_code == 200, r1.text

    path = P.KB_RUNS / rid / "gates.json"
    led_before = _ledger(rid)
    hist_before = len(led_before["gates"]["G1_diff_confirm"]["history"])
    md5_before = hashlib.md5(path.read_bytes()).hexdigest()
    assert hist_before == 1

    # 伪造"第二次点击"：同一个闸门再来一次
    r2 = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                     json={"decision": "disputed", "actor": HUMAN, "reason": "双击"})
    assert r2.status_code == 400, r2.text
    assert "没有待处理中断" in json.dumps(r2.json(), ensure_ascii=False)
    assert "未写权威账本" in json.dumps(r2.json(), ensure_ascii=False)

    led_after = _ledger(rid)
    assert len(led_after["gates"]["G1_diff_confirm"]["history"]) == hist_before, \
        "拒绝路径不得往权威账本追加记录"
    assert hashlib.md5(path.read_bytes()).hexdigest() == md5_before, \
        "拒绝路径不得改动 gates.json（含锚）"


def test_start_honors_now(client: TestClient) -> None:
    """F-V1-03：`POST /api/runs` 的 `now` 必须真的决定 run 身份（不能静默丢弃）。"""
    now = "2031-01-01T00:00:00"
    rid = _new_run(client, now=now)
    assert rid == "RUN-20310101-000000", rid
    view = client.get(f"/api/runs/{rid}").json()
    assert view["created_at"] == now


def test_invalid_now_is_rejected(client: TestClient) -> None:
    r = client.post("/api/runs", json={"baseline": "v0", "mode": "drill", "now": "不是时间"})
    assert r.status_code == 400, r.text


def test_gate_divergence_is_reported_not_hidden(client: TestClient) -> None:
    rid = _new_run(client)
    _wait_interrupt(client, rid, "G1")
    r = client.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
                    json={"decision": "confirmed", "actor": HUMAN, "reason": "逐条核对差异"})
    assert r.status_code == 200, r.text
    view = client.get(f"/api/runs/{rid}").json()
    real_history = view["gate_history"]
    assert len(real_history) == 1

    # 伪造一份"事件流里什么都没有"的 run_doc：权威有 1 条、事件 0 条 ⇒ 必须报分歧
    doc = dict(view)
    doc["gate_history"] = []
    au = contracts._gates_authority(doc)
    assert au["divergences"], au
    assert au["divergences"][0]["gate"] == "G1_diff_confirm"
    assert au["divergences"][0]["event_count"] == 0
    assert au["divergences"][0]["authority_count"] == 1

    # 也不许反过来：形状对不上就是分歧，不是"以事件为准"
    doc2 = dict(view)
    doc2["gate_history"] = list(real_history) * 2
    au2 = contracts._gates_authority(doc2)
    assert au2["divergences"] and au2["divergences"][0]["event_count"] == 2


def test_authority_projection_fails_closed_without_ledger() -> None:
    """账本缺失 ⇒ 明说缺件，**不得**编造一份 pending 闸门态。"""
    au = contracts._gates_authority({"run_id": "RUN-19990101-000000", "gate_history": []})
    assert au["present"] is False
    assert au["gates"] == {}
    assert au["anchor_ok"] is None
    assert "不存在" in au["reason"]


def test_authority_view_rejects_unknown_run_shape() -> None:
    au = contracts._gates_authority({"gate_history": []})
    assert au["present"] is False and au["reason"] == "无 run_id"

