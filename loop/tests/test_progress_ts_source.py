"""S8d：事件 `ts` 与注入时钟同源（**共享判据面**变更，单独变更流程）。

契约：[`SPEC-REV-16`](../../doc/spec/SPEC-REV-16-20261028.md) §4「事件时间源（S8d 收口，2026-10-29）」，
配套 §3（无进展判据 `OBS-03`）、§10（§9-8 收口）、§7（`OBS-03`/`OBS-04` 验收）。
计划：[2026-10-29-s8-review-and-d3.md](../../doc/plans/2026-10-29-s8-review-and-d3.md) §7（裁决 B2）。

本文件分三段，段名即用途：

1. **特征测试**（`test_feature_*`）：先在**旧实现**上跑绿，固定当时的可观察行为
   （drill 固定 `LOOP_NOW` 时事件 `ts` 走墙钟、`silence_s` 被 `max(0, …)` 夹成 0）；
   改造后按新契约**更新**（不是删除）——每条 `test_feature_*` 的 docstring 都写明
   「旧钉什么 → 新钉什么」，`test_feature_explicit_ts_argument_is_used_verbatim` 属新旧一致的不变量。
2. **新契约用例**（`test_new_*`）：改造前必须**红**（先失败用例），实现后转绿。
3. **迁移用例**（`test_migration_*`）：冻结历史事件不回填、旧 run 冷读走 `unknown`、
   冻结时钟下的节点次序 tie-break。

纪律：
- 时间只经 `host/paths.py` 的注入入口取（`LOOP_NOW`/`KB_NOW`）；断言不比较"语义上的墙钟值"，
  只在"证明当前实现走墙钟"的特征断言里用**区间**（`time.time()` 前后采样）而不是绝对值。
- **唯一判据一份**：不同源判别只看 `ts > now`（投影层一处实现），前端不重算。
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path

import pytest

from host import paths as P
from host.progress import ProgressLog
from services import contracts
from services.agent_view import (
    NO_PROGRESS_THRESHOLD_S,
    build_agents,
    progress_view,
    window_annotation,
)
from services.contracts import KbSources

#: drill 固定注入时刻（**过去**）：墙钟此刻在它之后 ⇒ 旧实现写出的事件 `ts` 会晚于注入 `now`。
DRILL_NOW = "2026-10-28T12:00:00"
RUN_ID = "RUN-20261028-120000"
NODE = "N6"


def _drill_now() -> float:
    """注入时刻的 epoch（与生产同一解析入口，不自己 `fromisoformat`）。"""
    return datetime.fromisoformat(DRILL_NOW).timestamp()


def _advance(monkeypatch: pytest.MonkeyPatch, seconds: float) -> float:
    """把注入时钟往前推 `seconds` 秒，返回新的 epoch（drill 的"时间前进"只有这一条路）。"""
    stamp = datetime.fromtimestamp(_drill_now() + seconds).isoformat()
    monkeypatch.setenv("LOOP_NOW", stamp)
    return P.now_epoch()


def _ev(seq: int, ts: float, node: str, kind: str, status: str = "ok",
        detail: dict | None = None) -> dict:
    return {"seq": seq, "ts": ts, "node": node, "kind": kind,
            "status": status, "detail": detail or {}, "refs": []}


def _kb(tmp_path: Path) -> KbSources:
    base = tmp_path / "ws"
    base.mkdir(exist_ok=True)
    (base / "conflicts.json").write_text('{"conflicts": [], "expected_total": 0}',
                                         encoding="utf-8")
    return KbSources(root=base, conflicts=base / "conflicts.json",
                     pending=base / "pending.json", baselines=base / "baselines")


# ==================================================================== 1) 特征测试（改前绿）
#
# 每条都记「旧钉什么」；`#new` 行是改造后按契约改写的断言（见文件顶部纪律 1）。

def test_feature_event_ts_uses_injected_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """特征：`ProgressLog.append` 的默认 `ts` 与注入 `now` **同源**。

    - **旧钉**（S8d 改造前，用例名 `test_feature_event_ts_uses_wall_clock_under_injected_now`）：
      写的是系统时钟，落在 `time.time()` 前后采样区间内，且因注入时刻在过去 ⇒ `ts > now_epoch()`。
    - **新钉**（本轮改造后）：`ts == now_epoch()`（`LOOP_NOW` 注入值），且**不再**等于墙钟。
    """
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    injected = P.now_epoch()
    log = ProgressLog(tmp_path / "events", RUN_ID)

    wall_before = time.time()
    event = log.append("node_started", node=NODE, status="running")
    wall_after = time.time()

    assert event.ts == injected, "事件 ts 必须来自注入时钟（同源）"
    assert not (wall_before - 5 <= event.ts <= wall_after + 5), "不得再是墙钟"
    # 落盘值与返回值一致（事件流是唯一出口）。
    assert log.read()[-1]["ts"] == event.ts


def test_feature_silence_is_unknown_when_ts_ahead_of_injected_now(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """特征：事件 `ts` 晚于注入 `now`（不同源）时，`silence_s` 取 `null` + 原因，**不告警**。

    - **旧钉**（S8d 改造前，用例名 `test_feature_silence_is_clamped_to_zero_when_ts_ahead_of_injected_now`）：
      `silence_s == 0`、`age_s == 0`、`no_progress.state == "ok"` —— 用 `max(0, …)` 把不同源
      夹成"真的很安静"。
    - **新钉**（本轮改造后）：`silence_s is None`、`last_event.age_s is None` +
      `unavailable_reason="ts_source_mismatch"`、`no_progress.state == "unknown"` 且不告警。
    """
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    now = P.now_epoch()
    # 事件 ts 用**墙钟形态**（= 注入 now + 26h 那种历史形状）：这里不写事件文件，直接从
    # 注入 now 之后的时刻构造，避免依赖本机系统时钟距离。
    log = ProgressLog(tmp_path / "events", RUN_ID)
    log.append("node_started", node=NODE, status="running", ts=now + 26 * 3600.0)

    progress = progress_view(NODE, events=log.read(), now=now)

    assert progress["state"] == "working"
    assert progress["silence_s"] is None, "不得再夹成 0"
    assert progress["last_event"]["age_s"] is None
    assert progress["last_event"]["unavailable_reason"] == "ts_source_mismatch"
    assert progress["no_progress"]["state"] == "unknown", "不同源不得是 ok"
    assert progress["no_progress"]["silence_s"] is None
    assert progress["no_progress"]["unavailable_reason"] == "ts_source_mismatch"


def test_feature_explicit_ts_argument_is_used_verbatim(tmp_path: Path) -> None:
    """特征（**新旧一致**）：显式传 `ts=` 的行为不变（回放/用例/历史重建要用）。"""
    log = ProgressLog(tmp_path / "events", RUN_ID)
    event = log.append("job_progress", node=NODE, ts=1_800_000_000.5)
    assert event.ts == 1_800_000_000.5
    assert log.read()[-1]["ts"] == 1_800_000_000.5


# ==================================================================== 2) 新契约（改前必须红）

def test_new_event_ts_comes_from_injected_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新契约（§4 S8d）：事件 `ts` 必须经 `now_epoch()` ⇒ drill 下等于注入时刻。"""
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    injected = P.now_epoch()
    log = ProgressLog(tmp_path / "events", RUN_ID)

    event = log.append("node_started", node=NODE, status="running")

    assert event.ts == injected, "事件 ts 必须是注入时钟（同源），不是墙钟"
    assert log.read()[-1]["ts"] == injected


def test_new_event_ts_follows_injected_clock_moves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入时钟前进 ⇒ 后写的事件 `ts` 跟着前进（不是一次性冻结的常量）。"""
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    log = ProgressLog(tmp_path / "events", RUN_ID)
    first = log.append("node_started", node=NODE, status="running", ts=None)
    later_now = _advance(monkeypatch, 90)
    second = log.append("job_progress", node=NODE, ts=None)
    assert first.ts == _drill_now()
    assert second.ts == later_now
    assert second.ts - first.ts == 90.0


def test_new_unparsable_injected_now_fails_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """注入时钟不可解析 ⇒ **显式失败**，不回退墙钟（否则事件会悄悄换源）。

    失败显式纪律（AGENTS.md §2 硬性纪律 3）：宁可让调用方看到 `ValueError`，
    也不要写出一条"看起来正常、其实来自另一个时钟"的事件。
    """
    monkeypatch.setenv("LOOP_NOW", "not-a-time")
    log = ProgressLog(tmp_path / "events", RUN_ID)
    with pytest.raises(ValueError):
        log.append("node_started", node=NODE, status="running")
    assert not (tmp_path / "events" / f"{RUN_ID}.jsonl").exists(), "不得写出半条事件"


def test_new_progress_module_has_no_direct_wall_clock() -> None:
    """红线 7 的**结构断言**：`host/progress.py` 与投影层都不得直接取墙钟。

    与 `grep "time.time()" loop/host/progress.py` 等价（交付要求该 grep 归零）；
    写成用例是为了让"有人日后加回墙钟"立刻变红。
    """
    root = Path(__file__).resolve().parents[1]
    progress_src = (root / "host" / "progress.py").read_text(encoding="utf-8")
    agent_view_src = (root / "services" / "agent_view.py").read_text(encoding="utf-8")
    assert "time.time()" not in progress_src
    assert "now_epoch" in progress_src, "默认 ts 必须显式经 `host/paths.py::now_epoch`"
    assert "time.time" not in agent_view_src
    assert "datetime.now" not in agent_view_src


def test_new_real_run_without_injection_still_uses_wall_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实运行不注入时钟 ⇒ 事件 `ts` 与投影 `now` **同源**（系统时钟），行为不变。"""
    monkeypatch.delenv("LOOP_NOW", raising=False)
    monkeypatch.delenv("KB_NOW", raising=False)
    log = ProgressLog(tmp_path / "events", RUN_ID)
    before = time.time()
    event = log.append("node_started", node=NODE, status="running")
    after = time.time()
    now = P.now_epoch()
    assert before - 5 <= event.ts <= after + 5, "不注入时仍取系统时钟"
    assert abs(event.ts - now) <= 5, "事件 ts 与投影 now 同源（真实运行不变量）"


def test_new_drill_silence_is_naturally_nonnegative_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """drill 同源后 `silence_s` **自然非负**：能真的数出 700 秒并越过阈值告警。

    这条是"不再靠 `max(0, …)`"的证据：700 是算出来的真值，不是夹出来的。
    """
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    log = ProgressLog(tmp_path / "events", RUN_ID)
    log.append("node_started", node=NODE, status="running")

    same = progress_view(NODE, events=log.read(), now=P.now_epoch())
    assert same["silence_s"] == 0
    assert same["no_progress"]["state"] == "ok"
    assert same["no_progress"]["unavailable_reason"] is None
    assert same["last_event"]["age_s"] == 0
    assert same["last_event"]["unavailable_reason"] is None

    now_later = _advance(monkeypatch, 700)
    stalled = progress_view(NODE, events=log.read(), now=now_later)
    assert stalled["silence_s"] == 700
    assert stalled["no_progress"]["state"] == "warn"
    assert stalled["no_progress"]["silence_s"] == 700
    assert stalled["no_progress"]["threshold_s"] == NO_PROGRESS_THRESHOLD_S
    assert stalled["no_progress"]["unavailable_reason"] is None
    assert f"{700 // 60} 分钟" in stalled["no_progress"]["reason"], (
        "分钟数取自服务端 silence_s（700 s ⇒ 11 分钟），前端不重算")


def test_new_mismatch_yields_null_with_reason_and_no_warn() -> None:
    """不同源（`ts > now`）⇒ 受影响字段 `null` + `unavailable_reason`，**不告警**。

    契约 §4 第二条：不得夹成 0 冒充"真的没有进展"。
    """
    now = 1_800_000_000.0
    ahead = now + 500.0
    progress = progress_view(NODE, events=[_ev(1, ahead, NODE, "node_started", "running")],
                            now=now)

    assert progress["state"] == "working", "投影不改状态（告警/未知都不是状态）"
    assert progress["silence_s"] is None, "不得夹成 0"
    assert progress["last_event"]["age_s"] is None, "不得夹成 0"
    assert progress["last_event"]["unavailable_reason"] == "ts_source_mismatch"
    assert progress["last_event"]["ts"] == ahead, "时间戳本身照实下发（只是年龄不可算）"
    cell = progress["no_progress"]
    assert cell["state"] == "unknown", "不同源不得是 ok/warn（判据不可用）"
    assert cell["silence_s"] is None
    assert cell["unavailable_reason"] == "ts_source_mismatch"
    assert cell["since_ts"] == ahead
    assert cell["threshold_s"] == NO_PROGRESS_THRESHOLD_S
    assert "不同源" in cell["reason"], "原因必须可读（界面直接显示）"


def test_new_mismatch_never_warns_even_for_huge_skew() -> None:
    """OBS-03：`warn` 只由"同源 now + 显式阈值"产生；差得再离谱也不得告警。"""
    now = 1_800_000_000.0
    progress = progress_view(
        NODE, events=[_ev(1, now + 10 ** 9, NODE, "node_started", "running")], now=now)
    assert progress["no_progress"]["state"] != "warn"
    assert progress["no_progress"]["state"] == "unknown"
    assert progress["silence_s"] is None


def test_new_same_source_boundary_ts_equal_now_is_zero_not_unknown() -> None:
    """边界：`ts == now` 是**同源**（差 0），不得误判成不同源（判据是严格 `>`）。"""
    now = 1_800_000_000.0
    progress = progress_view(NODE, events=[_ev(1, now, NODE, "node_started", "running")],
                             now=now)
    assert progress["silence_s"] == 0
    assert progress["no_progress"]["state"] == "ok"
    assert progress["no_progress"]["unavailable_reason"] is None
    assert progress["last_event"]["unavailable_reason"] is None


def test_new_mismatch_can_come_from_result_ts_alone() -> None:
    """记录侧（`result.ts`）不同源同样必须判为不可算（不只看事件）。"""
    now = 1_800_000_000.0
    root = Path("/tmp/does-not-matter")
    result = {"run_id": RUN_ID, "node": NODE, "attempt": 1, "ts": now + 300.0}
    events = [_ev(1, now - 100.0, NODE, "node_started", "running")]  # 同源事件 ⇒ working
    progress = progress_view(NODE, events=events, run_dir=root, result=result, now=now)
    assert progress["silence_s"] is None
    assert progress["no_progress"]["unavailable_reason"] == "ts_source_mismatch"
    assert progress["no_progress"]["state"] == "unknown"


def test_new_run_view_card_reports_mismatch_unknown_not_warn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """接线（`contracts.run_view`）：旧 run 的墙钟事件 + 注入 now ⇒ 卡片 `unknown`，不告警。"""
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    epoch = _drill_now()
    root = tmp_path / RUN_ID
    root.mkdir()
    events = [_ev(1, epoch + 3600.0, NODE, "node_started", "running")]  # 墙钟 = 注入 + 1h
    run_doc = {"run_id": root.name, "run_dir": str(root), "status": "running",
               "mode": "drill", "node_history": []}
    view = contracts.run_view(run_doc=run_doc, kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=events)
    author = next(card for card in view["agents"] if card["role"] == "author")
    assert author["status"] == "working"
    assert author["progress"]["silence_s"] is None
    assert author["progress"]["no_progress"]["state"] == "unknown"
    assert author["progress"]["no_progress"]["unavailable_reason"] == "ts_source_mismatch"


def test_new_card_and_window_share_the_mismatch_judgment(tmp_path: Path) -> None:
    """红线 8：同一事件/同一 `now` ⇒ 卡片与窗口的 `progress` 逐字相同（含 mismatch 理由）。"""
    root = tmp_path / RUN_ID
    root.mkdir()
    now = 1_800_000_000.0
    events = [_ev(1, now + 120.0, NODE, "node_started", "running")]
    card = next(card for card in build_agents(events, run_dir=root, now=now)
                if card["role"] == "author")
    via_window = window_annotation({}, node=NODE, root=root, events=events, now=now)
    assert card["progress"] == via_window["progress"]


# ==================================================================== 3) 迁移（历史不回填）

def _write_frozen_events(path: Path, events: list[dict]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
                            for event in events), encoding="utf-8")


def test_migration_frozen_wall_clock_events_are_not_backfilled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§4 第三条：已冻结的历史事件（墙钟 `ts`）**不回填、不改写**；冷读走 `unknown`。"""
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    epoch = _drill_now()
    events_dir = tmp_path / "events"
    path = events_dir / f"{RUN_ID}.jsonl"
    _write_frozen_events(path, [_ev(1, epoch + 94250.0, NODE, "node_started", "running")])
    digest_before = hashlib.md5(path.read_bytes()).hexdigest()

    log = ProgressLog(events_dir, RUN_ID)          # 冷读既有事件流（append 之前）
    progress = progress_view(NODE, events=log.read(), now=P.now_epoch())

    assert progress["silence_s"] is None
    assert progress["no_progress"]["state"] == "unknown"
    assert hashlib.md5(path.read_bytes()).hexdigest() == digest_before, "事件文件不得被改写"
    assert log.read()[0]["ts"] == epoch + 94250.0, "历史 ts 原样保留（不回填成注入时钟）"


def test_migration_old_run_cold_read_never_fakes_no_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """旧 run（墙钟事件）+ 注入 now 在过去 ⇒ 既不说"没进展"也不说"在推进"，只说不确定。"""
    monkeypatch.setenv("LOOP_NOW", DRILL_NOW)
    epoch = _drill_now()
    events = [_ev(1, epoch + 86400.0, NODE, "node_started", "running")]
    progress = progress_view(NODE, events=events, now=epoch)
    assert progress["no_progress"]["state"] == "unknown"
    assert progress["last_event"]["age_s"] is None
    blob = str(progress["no_progress"]["reason"])
    for banned in ("在等人工", "等待人工", "等待处理", "待人工确认"):
        assert banned not in blob


def test_migration_frozen_clock_tie_breaks_by_event_order(tmp_path: Path) -> None:
    """drill 冻结时钟 ⇒ 同一 run 事件 `ts` 全相同；"最近活跃节点"只能靠事件流顺序判。

    迁移取向：`_choose` 保持原语义（最近活跃节点），**同一 ts 时用 `seq` 次序**做 tie-break；
    ts 不同时行为不变（见 `test_choose_latest_node_or_first_declared`）。
    """
    epoch = 1_800_000_000.0
    events = [_ev(1, epoch, "N8", "node_started", "running"),
              _ev(2, epoch, "N10", "node_started", "running")]
    cards = build_agents(events, run_dir=None, now=epoch)
    checker = next(card for card in cards if card["role"] == "checker")
    assert checker["active_node"] == "N10"
