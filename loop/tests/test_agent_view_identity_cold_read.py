"""S8c / REV-16 §9-12 收口（先失败用例）：角色卡从**已封存记录**冷读 identity。

契约：[`SPEC-REV-16`](../../doc/spec/SPEC-REV-16-20261028.md) §2.1（`identity.attempt`/
`identity.session_id`/`last_error` 的来源）与 §10 的 §9-12 行（"把已封存记录（`agent_memory`
选中的 attempt 的 request/result）冷读进 `build_agents`，再喂给已有的
`progress_view(request=…, result=…)`"）。

本文件逐条钉住的判据（不读源码也能判定）：

1. **唯一判据**：卡片取"哪个 attempt"必须与窗口同源（`agent_control.read_view` 的选择规则），
   卡片**不得**自己再写一份"取最新 attempt"的判据（红线 8）；
2. **同值同源**：同一 run/同一 `now` 下，卡片 `progress.identity` 与窗口 `progress.identity`
   **逐字相同**（含 `attempt`/`session_id`），且整个 `progress` 逐字段相同；
3. **不回填历史**：没有记录 / 记录里没有该字段 ⇒ 仍是 `None`（未知就是未知，不猜 0 不猜 1）；
4. **失败显式**：记录损坏时卡片不静默当成"没有记录"（卡片 `note` 给出原因），窗口仍按既有
   422 口径显式失败 —— 两条出口共用同一份冷读判据。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from host import agent_backends as AB  # noqa: F401  （保证 host 包导入顺序与生产一致）
from host import agent_control as AC
from host import agent_memory as AM
from services import contracts
from services.agent_view import build_agents, window_annotation
from services.contracts import KbSources

#: 固定注入时间（epoch 秒）——本文件不读墙钟，`now` 全部由参数传给被测函数。
NOW = 1_800_000_000.0
TS = NOW - 30.0


def _run_root(tmp_path: Path, run_id: str = "RUN-20261029-120000") -> Path:
    root = tmp_path / run_id
    root.mkdir()
    return root


def _ev(seq: int, ts: float, node: str, kind: str, status: str = "ok",
        detail: dict | None = None) -> dict:
    return {"seq": seq, "ts": ts, "node": node, "kind": kind,
            "status": status, "detail": detail or {}, "refs": []}


def _seal_attempt(root: Path, node: str, attempt: int, *,
                  input_data: dict | None = None,
                  result: dict | None = None) -> Path:
    """按生产口径封存一次调用尝试（`AM.seal_record`：数据 → 校验和）。

    `result=None` ⇒ 只写 request（等价于"进程在两步之间被终止/正在执行"）。
    """
    folder = root / "agent_calls" / node / f"attempt-{attempt:06d}"
    folder.mkdir(parents=True, exist_ok=True)
    request = {"format_version": 1, "run_id": root.name, "node": node, "attempt": attempt,
               "model": "test-model", "input": input_data or {}}
    AM.seal_record(folder / "request.json", request)
    if result is not None:
        AM.seal_record(folder / "result.json",
                       {"format_version": 1, "run_id": root.name, "node": node,
                        "attempt": attempt, **result})
    return folder


def _tamper(folder: Path, name: str = "request.json") -> None:
    """把已封存记录改坏（校验和不变）⇒ `record_state` 判 `corrupt`。

    `AM.seal_record` 发布的文件名是 `0o400`（不可改写），所以先改权限再覆盖：
    数据变了、`.sha256` 还是旧的 ⇒ 校验和不匹配。
    """
    path = folder / name
    path.chmod(0o600)
    path.write_text('{"run_id": "tampered"}', encoding="utf-8")


def _by_role(cards: list[dict], role: str) -> dict:
    return next(card for card in cards if card["role"] == role)


def _window_progress(root: Path, node: str, events: list[dict], *, attempt: int | None = None,
                     now: float | None = NOW) -> dict:
    """窗口端点的**同一装配**（`services/api.py::_agent_window_view` 的服务端核心）。"""
    view = AC.read_view(root, node, attempt=attempt)
    return window_annotation(view, node=node, root=root, events=events, now=now)["progress"]


# ==================================================================== 冷读选中尝试

def test_card_identity_cold_reads_selected_attempt(tmp_path: Path) -> None:
    """卡片 `identity` 必须来自封存记录（attempt + session_id 都是真值，不再是恒 null）。"""
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "validated", "session_id": "sess-1",
                                         "ts": TS - 100})
    _seal_attempt(root, "N6", 2, result={"status": "validated", "session_id": "sess-2",
                                         "ts": TS})
    events = [_ev(1, TS - 120, "N6", "node_started", "running"),
              _ev(2, TS, "N6", "node_finished", "ok", {"mode": "standin"})]

    card = _by_role(build_agents(events, run_dir=root, now=NOW), "author")

    assert card["progress"]["identity"] == {
        "run_id": root.name, "node": "N6", "attempt": 2, "session_id": "sess-2"}
    # 选择判据必须是"最后一个**有记录**的尝试"（与窗口同源），不是"最新目录号"。
    assert card["progress"]["state"] == "done"


def test_card_identity_uses_same_selection_rule_as_window(tmp_path: Path) -> None:
    """**半写**尝试（数据在、校验和缺失 ⇒ `incomplete`）不参与选择 ⇒ 卡片与窗口都回落到 1。

    这条是"唯一判据"的关键反例：如果卡片自己按目录号取最新，会给出 attempt 2；
    窗口（`agent_control.read_view` 的 `record_state` 口径）给 attempt 1 —— 两处不一致即红线 8 违例。
    """
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "validated", "session_id": "sess-1",
                                         "ts": TS - 100})
    half = root / "agent_calls" / "N6" / "attempt-000002"
    half.mkdir(parents=True)
    (half / "request.json").write_text(  # 无 .sha256 ⇒ incomplete（进程在两步之间被终止）
        json.dumps({"run_id": root.name, "node": "N6", "attempt": 2}), encoding="utf-8")
    events = [_ev(1, TS, "N6", "node_started", "running")]

    card_progress = _by_role(build_agents(events, run_dir=root, now=NOW), "author")["progress"]
    window_progress = _window_progress(root, "N6", events)

    assert card_progress["identity"]["attempt"] == 1
    assert card_progress["identity"] == window_progress["identity"]


def test_card_identity_follows_request_only_attempt(tmp_path: Path) -> None:
    """只有 request（还在执行）的尝试**参与**选择（`session_id` 因此仍是未知）。

    与上一条配对：选择判据不是"只看有 result 的尝试"，也不是"取最新目录"，而是
    `read_view` 的既有口径 —— 卡片必须与窗口**同值**，不论页面作者怎么想。
    """
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "validated", "session_id": "sess-1",
                                         "ts": TS - 100})
    _seal_attempt(root, "N6", 2)  # 只有 request：正在执行
    events = [_ev(1, TS, "N6", "node_started", "running")]

    card_progress = _by_role(build_agents(events, run_dir=root, now=NOW), "author")["progress"]
    window_progress = _window_progress(root, "N6", events)

    assert card_progress["identity"] == {"run_id": root.name, "node": "N6",
                                         "attempt": 2, "session_id": None}
    assert card_progress["identity"] == window_progress["identity"]


def test_card_identity_null_when_no_records(tmp_path: Path) -> None:
    """没有记录 ⇒ 保持 `None`（未知就是未知，不回填成 0/1）。"""
    root = _run_root(tmp_path)
    card = _by_role(build_agents([_ev(1, TS, "N6", "node_started", "running")],
                                 run_dir=root, now=NOW), "author")
    assert card["progress"]["identity"] == {"run_id": root.name, "node": "N6",
                                           "attempt": None, "session_id": None}
    assert card["note"] is None, "没有记录不是错误，不得写诊断说明"


def test_card_identity_missing_session_id_stays_null(tmp_path: Path) -> None:
    """旧记录没有 `session_id` ⇒ 该字段仍是 `None`（其余真值照填，不整块丢弃）。"""
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "validated", "ts": TS})
    card = _by_role(build_agents([_ev(1, TS, "N6", "node_finished", "ok")],
                                 run_dir=root, now=NOW), "author")
    assert card["progress"]["identity"] == {"run_id": root.name, "node": "N6",
                                           "attempt": 1, "session_id": None}


def test_card_without_run_dir_keeps_identity_unknown() -> None:
    """`run_dir=None`（既有调用形态）⇒ 不冷读、identity 保持未知，不抛异常。"""
    card = _by_role(build_agents([_ev(1, TS, "N6", "node_started", "running")],
                                 run_dir=None, now=NOW), "author")
    assert card["progress"]["identity"] == {"run_id": None, "node": "N6",
                                           "attempt": None, "session_id": None}


def test_card_last_error_comes_from_selected_attempt_result(tmp_path: Path) -> None:
    """记录来源的 `last_error`：选中的 attempt 的 `error` 必须下发给卡片（与窗口同值）。"""
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "error", "error": "provider 403（重试耗尽）",
                                         "ts": TS})
    events = [_ev(1, TS - 5, "N6", "node_started", "running")]
    card = _by_role(build_agents(events, run_dir=root, now=NOW), "author")
    window = _window_progress(root, "N6", events)

    assert card["progress"]["last_error"] == {
        "message": "provider 403（重试耗尽）", "ts": TS, "source": "attempt_result"}
    assert card["progress"]["last_error"] == window["last_error"]


# ==================================================================== 卡片 == 窗口（逐字）

@pytest.mark.parametrize("attempts", [1, 3])
def test_card_and_window_identity_are_byte_identical(tmp_path: Path, attempts: int) -> None:
    """同一 run/同一 now：卡片 `progress` 与窗口 `progress` **逐字段相同**（含 identity）。"""
    root = _run_root(tmp_path)
    for index in range(1, attempts + 1):
        _seal_attempt(root, "N6", index,
                      result={"status": "validated", "session_id": f"sess-{index}",
                              "ts": TS - (attempts - index)})
    events = [_ev(1, TS - 200, "N6", "node_started", "running"),
              _ev(2, TS, "N6", "node_finished", "ok", {"mode": "standin"})]

    card_progress = _by_role(build_agents(events, run_dir=root, now=NOW), "author")["progress"]
    window_progress = _window_progress(root, "N6", events)

    assert card_progress["identity"] == window_progress["identity"]
    assert card_progress["identity"]["attempt"] == attempts
    assert json.dumps(card_progress, sort_keys=True, ensure_ascii=False) == \
        json.dumps(window_progress, sort_keys=True, ensure_ascii=False), \
        "卡片与窗口必须是同一份进度投影（红线 8：不许出现第二套判据）"


def test_card_and_window_read_live_session_identically(tmp_path: Path, monkeypatch) -> None:
    """活跃会话（live）也是 `session_id` 的来源之一：卡片与窗口必须取到同一个值。"""
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "run", "ts": TS})
    monkeypatch.setattr(AC, "live_view",
                        lambda _root, _node: {"session_id": "live-sess-7", "state": "working"})
    events = [_ev(1, TS, "N6", "node_started", "running")]

    card_progress = _by_role(build_agents(events, run_dir=root, now=NOW), "author")["progress"]
    window_progress = _window_progress(root, "N6", events)

    assert card_progress["identity"]["session_id"] == "live-sess-7"
    assert card_progress["identity"] == window_progress["identity"]


# ==================================================================== 记录损坏：失败显式

def test_card_corrupt_record_keeps_identity_unknown_and_says_why(tmp_path: Path) -> None:
    """记录校验和不匹配 ⇒ 卡片不假装"没有记录"：identity 未知 + `note` 写明原因，看板不崩。

    窗口侧仍按既有 422 口径显式失败（同一份冷读判据的两种出口，见模块 docstring 第 4 条）。
    """
    root = _run_root(tmp_path)
    folder = _seal_attempt(root, "N6", 1, result={"status": "validated", "ts": TS})
    _tamper(folder)

    card = _by_role(build_agents([_ev(1, TS, "N6", "node_started", "running")],
                                 run_dir=root, now=NOW), "author")

    assert card["progress"]["identity"]["attempt"] is None
    assert card["note"], "记录不可读时必须显式说明，不得静默降级成『没有记录』"
    assert "agent" in card["note"] and "记录" in card["note"]
    with pytest.raises(ValueError):
        AC.read_view(root, "N6")


def test_card_broken_record_does_not_break_other_cards(tmp_path: Path) -> None:
    """一个节点的记录坏了，其它角色卡照常投影（投影不得让整块看板失效）。"""
    root = _run_root(tmp_path)
    folder = _seal_attempt(root, "N6", 1, result={"status": "validated", "ts": TS})
    _tamper(folder)
    _seal_attempt(root, "N3", 1, result={"status": "validated", "session_id": "sess-n3",
                                         "ts": TS})
    events = [_ev(1, TS, "N3", "node_started", "running"),
              _ev(2, TS, "N6", "node_started", "running")]

    cards = build_agents(events, run_dir=root, now=NOW)

    assert _by_role(cards, "analyst")["progress"]["identity"]["session_id"] == "sess-n3"
    assert _by_role(cards, "author")["progress"]["identity"]["attempt"] is None


# ==================================================================== 看板接线（run_view）

def _kb(tmp_path: Path) -> KbSources:
    base = tmp_path / "ws"
    base.mkdir(exist_ok=True)
    (base / "conflicts.json").write_text(
        json.dumps({"conflicts": [], "expected_total": 0}), encoding="utf-8")
    return KbSources(root=base, conflicts=base / "conflicts.json",
                     pending=base / "pending.json", baselines=base / "baselines")


def test_run_view_cards_carry_real_identity(monkeypatch, tmp_path: Path) -> None:
    """看板（`GET /api/runs/{run}` 的服务端视图）下发的角色卡也必须带真实 identity。"""
    monkeypatch.setenv("LOOP_NOW", "2026-10-29T12:00:00")
    epoch = 1_793_246_400.0  # 2026-10-29T12:00:00（Asia/Shanghai = 本地时区）
    root = _run_root(tmp_path)
    _seal_attempt(root, "N6", 1, result={"status": "validated", "session_id": "sess-n6",
                                         "ts": epoch - 10})
    events = [_ev(1, epoch - 60, "N6", "node_started", "running")]
    run_doc = {"run_id": root.name, "run_dir": str(root), "status": "running",
               "mode": "drill", "node_history": []}

    view = contracts.run_view(run_doc=run_doc, kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=events)

    author = _by_role(view["agents"], "author")
    assert author["progress"]["identity"] == {
        "run_id": root.name, "node": "N6", "attempt": 1, "session_id": "sess-n6"}
