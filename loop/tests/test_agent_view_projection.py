"""S4-A 投影新行为（先失败用例）：`progress` 总结投影 + 无进展告警 + S3 解释面。

契约：[`SPEC-REV-16`](../../doc/spec/SPEC-REV-16-20261028.md) §2（字段表）、§2.2（压缩次数）、
§3（无进展判据）、§4（时间口径）、§6.3（S3 接面）。验收编号 `OBS-02`/`OBS-03`/`OBS-04`/`OBS-08`（服务端半边）。

纪律（本文件逐条断言）：
1. **未知保持未知**：没有来源的字段一律 `None`（压缩次数**不得**退化成 0）；
2. **`now` 只走注入**：本文件不读墙钟（`time.time()`/`datetime.now()` 0 处），事件 ts 与 now 都是固定数；
3. **投影不是权威**：`warn` 只产字段，不改 `state`、不写文件、不发命令；
4. **只消费服务端结论**：accepted/applied/effective、WM availability、经验 selected/rejected 原样透传。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from host import agent_memory as AM
from host import agent_control as AC
from host import agent_backends as AB  # noqa: F401  （保证 host 包导入顺序与生产一致）
from host.agent_backends import dsh_sdk as SDK
from services import contracts
from services.agent_view import (
    NO_PROGRESS_THRESHOLD_S,
    build_agents,
    explain_view,
    progress_view,
    window_annotation,
)
from services.contracts import KbSources

#: 固定注入时间（epoch 秒）——本文件的 now 全部由参数传入，不取系统时钟。
NOW = 1_800_000_000.0
TS = NOW - 100.0


def _ev(seq: int, ts: float, node: str, kind: str, status: str = "ok",
        detail: dict | None = None) -> dict:
    return {"seq": seq, "ts": ts, "node": node, "kind": kind,
            "status": status, "detail": detail or {}, "refs": []}


def _run_root(tmp_path: Path, run_id: str = "RUN-20261028-120000") -> Path:
    root = tmp_path / run_id
    root.mkdir()
    return root


def _kb(tmp_path: Path) -> KbSources:
    base = tmp_path / "ws"
    base.mkdir(exist_ok=True)
    (base / "conflicts.json").write_text(
        json.dumps({"conflicts": [], "expected_total": 0}), encoding="utf-8")
    return KbSources(root=base, conflicts=base / "conflicts.json",
                     pending=base / "pending.json", baselines=base / "baselines")


# ==================================================================== §2.1 字段与未知

def test_progress_field_set_is_frozen() -> None:
    """字段名按契约 §2.1 冻结（界面按这张表渲染，改名即破坏）。"""
    progress = progress_view("N6", events=[], now=NOW)
    assert set(progress) == {
        "identity", "state", "current_action", "last_event", "last_tool", "last_error",
        "elapsed_s", "silence_s", "no_progress", "compaction", "execution", "authority",
    }
    assert set(progress["identity"]) == {"run_id", "node", "attempt", "session_id"}
    assert set(progress["no_progress"]) == {
        "state", "since_ts", "silence_s", "threshold_s", "reason"}
    assert progress["authority"] == "projection"
    # **附加**可读字段（契约表未列、非必需）：钉住存在性，防止将来被当成"多余字段"删掉；
    # 它们只解释"为什么是 unknown"，消费方不得据此判定完成/失败（见 progress_view docstring）。
    assert "reason" in progress["compaction"]
    assert "path" in progress["compaction"]


def test_progress_without_sources_keeps_everything_unknown(tmp_path: Path) -> None:
    """没有事件/没有记录/没有 now ⇒ 字段保持 None，不猜、不显示 0。"""
    progress = progress_view("N6", events=[], run_dir=_run_root(tmp_path), now=None)
    assert progress["identity"] == {"run_id": "RUN-20261028-120000", "node": "N6",
                                    "attempt": None, "session_id": None}
    assert progress["state"] == "idle"
    assert progress["current_action"] is None
    assert progress["last_event"] is None
    assert progress["last_tool"] is None
    assert progress["last_error"] is None
    assert progress["elapsed_s"] is None
    assert progress["silence_s"] is None
    assert progress["no_progress"]["state"] == "n/a"
    assert progress["no_progress"]["since_ts"] is None
    assert progress["no_progress"]["reason"], "n/a 也要给可读原因（界面不再自己判）"
    assert progress["compaction"]["source"] == "unknown"
    assert progress["compaction"]["count"] is None, "没有来源不得显示 0"
    assert progress["execution"] == "not_started"


def test_progress_identity_comes_from_records(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    request = {"run_id": root.name, "node": "N6", "attempt": 3}
    result = {"run_id": root.name, "node": "N6", "attempt": 3, "status": "validated",
              "session_id": "sess-abc", "ts": TS}
    progress = progress_view("N6", events=[], run_dir=root, request=request, result=result,
                             now=NOW)
    assert progress["identity"] == {"run_id": root.name, "node": "N6", "attempt": 3,
                                    "session_id": "sess-abc"}
    assert progress["elapsed_s"] is None, "没有 node_started ⇒ 耗时未知"


# ==================================================================== §3 无进展判据

def test_no_progress_ok_below_threshold() -> None:
    events = [_ev(1, TS, "N6", "node_started", "running")]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["state"] == "working"
    assert progress["silence_s"] == int(NOW - TS)
    assert progress["no_progress"] == {
        "state": "ok", "since_ts": TS, "silence_s": int(NOW - TS),
        "threshold_s": NO_PROGRESS_THRESHOLD_S, "reason": None,
    }


def test_no_progress_warn_exactly_at_threshold() -> None:
    """阈值边界：`silence_s >= threshold` 即 warn（等于也算，含端点的判据要钉住）。"""
    last = NOW - NO_PROGRESS_THRESHOLD_S
    events = [_ev(1, last, "N6", "node_started", "running")]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["no_progress"]["state"] == "warn"
    assert progress["no_progress"]["since_ts"] == last
    assert progress["no_progress"]["threshold_s"] == NO_PROGRESS_THRESHOLD_S
    minutes = NO_PROGRESS_THRESHOLD_S // 60
    assert f"{minutes} 分钟" in progress["no_progress"]["reason"], (
        "文案要含分钟数（界面红字直接用它）")


def test_no_progress_is_only_a_projection_not_a_state_change(tmp_path: Path) -> None:
    """warn 不改 state、不写文件（只告警不自动收敛）。"""
    root = _run_root(tmp_path)
    last = NOW - 3600.0
    events = [_ev(1, last, "N6", "node_started", "running")]
    before = sorted(p.name for p in root.iterdir())
    progress = progress_view("N6", events=events, run_dir=root, now=NOW)
    assert progress["state"] == "working"
    assert progress["no_progress"]["state"] == "warn"
    assert sorted(p.name for p in root.iterdir()) == before, "投影不得写文件"


def test_no_progress_unknown_when_now_missing() -> None:
    """有事件但没有注入 now ⇒ unknown（不猜、不用墙钟补）。"""
    events = [_ev(1, TS, "N6", "node_started", "running")]
    progress = progress_view("N6", events=events, now=None)
    assert progress["state"] == "working"
    assert progress["silence_s"] is None
    assert progress["no_progress"]["state"] == "unknown"
    assert progress["no_progress"]["reason"]


def test_no_progress_not_applicable_when_not_working() -> None:
    """idle/done/failed 都不告警，且都给出为什么 n/a。"""
    done = [_ev(1, NOW - 5000, "N6", "node_started", "running"),
            _ev(2, NOW - 4000, "N6", "node_finished", "ok")]
    progress = progress_view("N6", events=done, now=NOW)
    assert progress["state"] == "done"
    assert progress["no_progress"]["state"] == "n/a"
    assert "done" in progress["no_progress"]["reason"]
    assert progress["no_progress"]["since_ts"] == NOW - 4000

    failed = [_ev(1, NOW - 5000, "N6", "node_started", "running"),
              _ev(2, NOW - 4000, "N6", "node_failed", "failed", {"message": "boom"})]
    progress = progress_view("N6", events=failed, now=NOW)
    assert progress["no_progress"]["state"] == "n/a"
    assert "failed" in progress["no_progress"]["reason"]

    # 真闸门 waiting 也不告警（停滞 ≠ 等人工；判据只认 state，不认"看起来停了"）。
    gate_state = [_ev(1, NOW - 3000, "N4", "node_started", "running")]
    pending = {"id": "G1:0", "type": "gate_decision",
               "payload": {"gate": "G1_diff_confirm", "gate_node": "N4"}}
    progress = progress_view("N4", events=gate_state, pending_interrupt=pending, now=NOW)
    assert progress["state"] == "waiting"
    assert progress["no_progress"]["state"] == "n/a"
    assert "waiting" in progress["no_progress"]["reason"]


def test_no_progress_silence_clamped_non_negative() -> None:
    """事件 ts 晚于注入 now（两个时钟源不一致）时夹到 0，不产生负时长/假告警。"""
    events = [_ev(1, NOW + 500.0, "N6", "node_started", "running")]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["silence_s"] == 0
    assert progress["no_progress"]["state"] == "ok"


def test_last_event_and_current_action_track_last_node_event() -> None:
    events = [
        _ev(1, NOW - 300, "N6", "node_started", "running"),
        _ev(2, NOW - 200, "N6", "node_warning", "experience_rejected"),
        _ev(3, NOW - 100, "N6", "node_finished", "validation_failed"),
    ]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["last_event"] == {"kind": "node_finished", "status": "validation_failed",
                                      "ts": NOW - 100, "age_s": 100}
    assert progress["current_action"] == {"kind": "node_finished",
                                          "status": "validation_failed", "ts": NOW - 100}


def test_last_event_ignores_other_nodes() -> None:
    events = [_ev(1, NOW - 100, "N8", "node_started", "running")]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["last_event"] is None
    assert progress["state"] == "idle"


# ==================================================================== §2.1 最后错误 / 执行方式

def test_last_error_from_node_failed_event() -> None:
    events = [
        _ev(1, NOW - 300, "N6", "node_started", "running"),
        _ev(2, NOW - 200, "N6", "node_failed", "failed", {"message": "provider 403"}),
    ]
    progress = progress_view("N6", events=events, now=NOW)
    assert progress["last_error"] == {"message": "provider 403", "ts": NOW - 200,
                                      "source": "node_failed"}


def test_last_error_falls_back_to_attempt_record() -> None:
    result = {"run_id": "RUN-20261028-120000", "node": "N6", "attempt": 1,
              "status": "error", "error": "budget exceeded", "finished_at": TS}
    progress = progress_view("N6", events=[], request=None, result=result, now=NOW)
    assert progress["last_error"] == {"message": "budget exceeded", "ts": TS,
                                      "source": "attempt_result"}


def test_last_error_none_when_no_source() -> None:
    progress = progress_view("N6", events=[_ev(1, TS, "N6", "node_started", "running")],
                             now=NOW)
    assert progress["last_error"] is None, "没有错误记录就是 None，不编造"


def test_execution_separates_standin_from_real_completion() -> None:
    """standin/unknown 不得投影成真实完成：execution 与 state 分开给，界面两处都读。"""
    standin = [_ev(1, NOW - 100, "N6", "node_started", "running"),
               _ev(2, NOW - 50, "N6", "node_finished", "ok", {"mode": "standin"})]
    progress = progress_view("N6", events=standin, now=NOW)
    assert progress["state"] == "done"
    assert progress["execution"] == "standin"

    unknown = [_ev(1, NOW - 100, "N6", "node_started", "running"),
               _ev(2, NOW - 50, "N6", "node_finished", "ok")]
    assert progress_view("N6", events=unknown, now=NOW)["execution"] == "unknown"

    real = [_ev(1, NOW - 100, "N6", "node_started", "running"),
            _ev(2, NOW - 50, "N6", "node_finished", "ok", {"mode": "live"})]
    assert progress_view("N6", events=real, now=NOW)["execution"] == "real"


# ==================================================================== §2.2 压缩次数（只认 session log）

def test_compaction_unknown_without_source() -> None:
    progress = progress_view("N6", events=[], now=NOW)
    assert progress["compaction"] == {"source": "unknown", "count": None,
                                      "error": None, "reason": None, "path": None}


def test_compaction_reads_session_log_through_existing_parser(tmp_path: Path) -> None:
    """happy path：只经 `dsh_sdk.read_session_log`（复用既有解析，不另写解码）。"""
    facts = SDK.CompactionFacts(
        availability=SDK.AVAILABILITY_OK, count=2,
        records=(SDK.CompactionRecord(compaction_id="c1", time=10, seq=1,
                                      shadowed_token_count=100),
                 SDK.CompactionRecord(compaction_id="c2", time=20, seq=2,
                                      shadowed_token_count=50)),
        start_count=2, end_count=2, path="/tmp/session.log.zstd")
    calls: list[str] = []

    def fake_read(path, **kwargs):
        calls.append(str(path))
        return facts

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(SDK, "read_session_log", fake_read)
    try:
        progress = progress_view("N6", events=[], now=NOW,
                                 session_log=tmp_path / "session.log.zstd")
    finally:
        monkeypatch.undo()
    assert calls == [str(tmp_path / "session.log.zstd")]
    assert progress["compaction"]["source"] == "session_log"
    assert progress["compaction"]["count"] == 2
    assert progress["compaction"]["error"] is None


def test_compaction_failure_is_explicit() -> None:
    """`compaction/end.data.error` 存在 ⇒ error 非空（失败显式，不吞）。"""
    facts = SDK.CompactionFacts(
        availability=SDK.AVAILABILITY_OK, count=0,
        errors=(SDK.CompactionError(compaction_id="c1", error="context window exceeded",
                                    time=20),),
        start_count=1, end_count=1, path="/tmp/session.log.zstd")
    import unittest.mock as mock
    with mock.patch.object(SDK, "read_session_log", return_value=facts):
        progress = progress_view("N6", events=[], now=NOW, session_log="/tmp/x.zstd")
    assert progress["compaction"]["source"] == "session_log"
    assert progress["compaction"]["error"]
    assert "context window exceeded" in progress["compaction"]["error"]


def test_compaction_unavailable_source_keeps_count_unknown() -> None:
    """压缩源不可用 ⇒ source=unknown、count=None，但 reason 要显式说为什么。"""
    facts = SDK.CompactionFacts.unavailable("zstd 不可用", path="/tmp/x.zstd")
    import unittest.mock as mock
    with mock.patch.object(SDK, "read_session_log", return_value=facts):
        progress = progress_view("N6", events=[], now=NOW, session_log="/tmp/x.zstd")
    assert progress["compaction"]["source"] == "unknown"
    assert progress["compaction"]["count"] is None
    assert "zstd" in progress["compaction"]["reason"]


def test_compaction_garbage_log_is_explicit_not_zero(tmp_path: Path) -> None:
    """给了 session log 但读不出事实 ⇒ 显式 reason + count=None（不是 0）。"""
    bad = tmp_path / "session.log.zstd"
    bad.write_text("not-a-zstd-frame\n", encoding="utf-8")
    progress = progress_view("N6", events=[], now=NOW, session_log=bad)
    assert progress["compaction"]["source"] == "unknown"
    assert progress["compaction"]["count"] is None
    assert progress["compaction"]["reason"]


def test_compaction_ref_from_record_resolves_under_run_dir(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    log = root / "sessions" / "session.log.zstd"
    log.parent.mkdir()
    log.write_text("dummy", encoding="utf-8")
    facts = SDK.CompactionFacts(availability=SDK.AVAILABILITY_OK, count=1,
                                records=(SDK.CompactionRecord(compaction_id="c1", time=5),),
                                path=str(log))
    request = {"run_id": root.name, "node": "N6", "attempt": 1,
               "session_log_ref": "sessions/session.log.zstd"}
    import unittest.mock as mock
    with mock.patch.object(SDK, "read_session_log", return_value=facts) as called:
        progress = progress_view("N6", events=[], run_dir=root, request=request, now=NOW)
    called.assert_called_once_with(log)
    assert progress["compaction"]["count"] == 1


def test_compaction_ref_escape_is_rejected(tmp_path: Path) -> None:
    """受管元数据里的相对引用也不能越界（`..`/绝对路径/符号链接一律显式拒绝）。"""
    root = _run_root(tmp_path)
    for ref in ("../outside.log", "/etc/passwd"):
        request = {"run_id": root.name, "node": "N6", "attempt": 1, "session_log_ref": ref}
        with pytest.raises(ValueError):
            progress_view("N6", events=[], run_dir=root, request=request, now=NOW)


def test_compaction_ref_symlink_is_rejected(tmp_path: Path) -> None:
    """run 目录内的符号链接同样拒绝（防跳出 run 目录读任意文件）。"""
    root = _run_root(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("dummy", encoding="utf-8")
    link = root / "session.log.zstd"
    link.symlink_to(outside)
    request = {"run_id": root.name, "node": "N6", "attempt": 1,
               "session_log_ref": "session.log.zstd"}
    with pytest.raises(ValueError):
        progress_view("N6", events=[], run_dir=root, request=request, now=NOW)


def test_compaction_real_zstd_session_log_counts_summaries(tmp_path: Path) -> None:
    """端到端：真 zstd 多帧 session log ⇒ 只数 `compaction/summary`（prune 不混算）。"""
    zstd = shutil.which("zstd")
    if zstd is None:
        pytest.skip("本机没有 zstd（环境缺件，不是代码缺陷）")
    lines = [
        {"type": "session", "id": "s1"},
        {"type": "compaction/start", "seq": 1, "time": 10, "data": {"compactionId": "c1"}},
        {"type": "compaction/summary", "seq": 2, "time": 11,
         "data": {"compactionId": "c1", "shadowedTokenCount": 120}},
        {"type": "compaction/end", "seq": 3, "time": 12, "data": {"compactionId": "c1"}},
        {"type": "compaction/prune", "seq": 4, "time": 13, "data": {"shadowedTokenCount": 99}},
        {"type": "compaction/start", "seq": 5, "time": 20, "data": {"compactionId": "c2"}},
        {"type": "compaction/summary", "seq": 6, "time": 21,
         "data": {"compactionId": "c2", "shadowedTokenCount": 30}},
        {"type": "compaction/end", "seq": 7, "time": 22,
         "data": {"compactionId": "c2", "error": "budget"}},
    ]
    raw = ("\n".join(json.dumps(line) for line in lines) + "\n").encode("utf-8")
    log = tmp_path / "session.log.zstd"
    subprocess.run([zstd, "-q", "-f", "-o", str(log)], input=raw, check=True,
                   capture_output=True)
    progress = progress_view("N6", events=[], now=NOW, session_log=log)
    assert progress["compaction"]["source"] == "session_log"
    assert progress["compaction"]["count"] == 2, "只数 summary；prune/start/end 不混算"
    assert "budget" in (progress["compaction"]["error"] or "")


def test_compaction_missing_log_file_is_explicit(tmp_path: Path) -> None:
    progress = progress_view("N6", events=[], now=NOW,
                             session_log=tmp_path / "nope.zstd")
    assert progress["compaction"]["count"] is None
    assert progress["compaction"]["reason"]


# ==================================================================== §6.3 S3 解释面

def _view(run_root: Path, *, request: dict | None = None, result: dict | None = None,
          live: dict | None = None, selected: int | None = None) -> dict:
    return {"run_id": run_root.name, "node": (request or {}).get("node", "N6"),
            "live": live, "attempts": [],
            "selected_attempt": selected, "request": request, "result": result,
            "previous_input": None, "controls": [],
            "observation": "实际输入、节点事件和返回结果；不提供模型隐藏推理或 token 流。"}


def test_explain_empty_run_keeps_blocks_unknown(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    explain = explain_view(_view(root), root=root)
    assert set(explain) == {"instructions", "scope_expiry", "working_memory", "experiences"}
    assert explain["instructions"]["items"] == []
    assert explain["instructions"]["revision"] == 0
    assert explain["instructions"]["source"] == "agent_control.instructions_view"
    assert explain["scope_expiry"]["determined"] is False
    assert explain["scope_expiry"]["state"] == "unknown"
    assert explain["scope_expiry"]["note"], "未判定要写清原因，不得显示『仍生效』"
    assert explain["working_memory"]["availability"] == "unknown"
    assert explain["working_memory"]["items"] == []
    assert explain["experiences"]["recorded"] is False
    assert explain["experiences"]["selected"] == []
    assert explain["experiences"]["rejected"] == []
    # 附加可读字段（非契约表必需）：钉住存在性，供界面区分"未记录 vs 无条目"。
    assert explain["working_memory"]["authority"] == "projection"
    assert explain["working_memory"]["recorded"] is False
    assert explain["experiences"]["authority"] == "projection"
    assert explain["experiences"]["catalog_version"] is None
    assert explain["experiences"]["selection_mode"] is None


def test_explain_instructions_split_accepted_applied_effective(tmp_path: Path) -> None:
    """三态分列：回执 ≠ 已采用 ≠ 当前生效（禁合并）。"""
    root = _run_root(tmp_path)
    AC.submit(root, {"operation": "create", "actor": "human:reviewer",
                     "request_id": "req-1", "expected_instruction_revision": 0,
                     "message": "先核对 doc_bitdef 再加观测点", "scope": "run",
                     "target_nodes": ["N6"], "dependencies": []})
    # 一次**已封存**的请求证明 applied（applied 只从 request 记录来）
    attempt = root / "agent_calls" / "N6" / "attempt-000001"
    attempt.mkdir(parents=True)
    AM.seal_record(attempt / "request.json",
                   {"format_version": 1, "run_id": root.name, "node": "N6", "attempt": 1,
                    "instruction_projection": {
                        "effective_sha256": "x",
                        "adopted": [{"instruction_id": "ins-000001", "version": 1,
                                     "scope": "run", "message": "先核对 doc_bitdef 再加观测点",
                                     "event_revision": 1,
                                     "sealed_ref": "agent_controls/run/instruction-000001.json"}],
                        "not_adopted": []}})
    explain = explain_view(_view(root), root=root)
    item = explain["instructions"]["items"][0]
    assert item["id"] == "ins-000001"
    assert item["state_accepted"] == "accepted"
    assert item["accepted_at"]
    assert item["state_applied"] == "applied"
    # 契约为**标量**尝试号（s4-ui 按"尝试 #N"渲染）；节点身份是附加字段 applied_ref。
    assert item["applied_attempt"] == 1
    assert item["applied_ref"] == {"node": "N6", "attempt": 1}
    assert item["state_effective"] == "effective"
    assert item["text_preview"].startswith("先核对 doc_bitdef")


def test_explain_instructions_revoked_is_not_effective(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    AC.submit(root, {"operation": "create", "actor": "human:reviewer",
                     "request_id": "req-1", "expected_instruction_revision": 0,
                     "message": "旧指令", "scope": "run", "target_nodes": ["N6"],
                     "dependencies": []})
    AC.submit(root, {"operation": "revoke", "actor": "human:reviewer",
                     "request_id": "req-2", "expected_instruction_revision": 1,
                     "target_instruction_id": "ins-000001"})
    rows = explain_view(_view(root), root=root)["instructions"]["items"]
    assert [row["state_effective"] for row in rows] == ["not_effective"]
    assert rows[0]["state_applied"] == "not_applied"
    assert rows[0]["applied_attempt"] is None
    assert rows[0]["unavailable_reason"] == "revoked"


def test_explain_working_memory_passthrough(tmp_path: Path) -> None:
    """WM availability/unavailable 原因原样透传；前端不重算。"""
    root = _run_root(tmp_path)
    request = {"run_id": root.name, "node": "N6", "attempt": 1,
               "working_memory_source_map": {
                   "version": 1, "run_id": root.name, "node": "N6",
                   "snapshot_sha256": "sha", "availability": "unavailable",
                   "entries": [{"entry_id": "observed_fact:N6:diff",
                                "kind": "observed_fact", "source_keys": ["diff"],
                                "pointer": "/diff", "consumers": ["N6"]}],
                   "sources": {"diff": {"origin": "request_input", "pointer": "/diff",
                                        "sha256": "s", "kind": "observed_fact",
                                        "present": True}},
                   "unavailable": [{"kind": "open_issue", "slot": "issues",
                                    "reason": "当前请求输入缺该字段"}],
                   "mandatory_bytes": 100, "limit_bytes": 120000, "over_budget": False}}
    explain = explain_view(_view(root, request=request), root=root)
    wm = explain["working_memory"]
    assert wm["availability"] == "unavailable"
    assert wm["snapshot_sha256"] == "sha"
    assert wm["mandatory_bytes"] == 100 and wm["limit_bytes"] == 120000
    assert {item["id"]: item for item in wm["items"]} == {
        "observed_fact:N6:diff": {"id": "observed_fact:N6:diff", "kind": "observed_fact",
                                  "availability": "verified", "unavailable_reason": None,
                                  "source_ref": "/diff"},
        "open_issue:issues": {"id": "open_issue:issues", "kind": "open_issue",
                              "availability": "unavailable",
                              "unavailable_reason": "当前请求输入缺该字段",
                              "source_ref": None},
    }


def test_explain_experiences_passthrough_selected_rejected(tmp_path: Path) -> None:
    """经验 selected/rejected 必须照记录透传（不重算、不写回）。"""
    root = _run_root(tmp_path)
    request = {"run_id": root.name, "node": "N6", "attempt": 1,
               "experience_selection": {
                   "catalog_version": 2, "catalog_sha256": "sha",
                   "selection_mode": "v2_applicability", "applicable_context": {},
                   "selected": [{"id": "exp-1", "revision": 1, "kind": "exact_fact",
                                 "source": {"path": "runs/x.json", "sha256": "s"},
                                 "checks": {"source_integrity": "ok"}}],
                   "rejected": [{"id": "exp-2", "reason": "dependency_changed",
                                 "detail": "obs", "phase": "applicability"}],
                   "batch": {"candidates": 1, "bytes": 10, "limit_bytes": 4096,
                             "item_limit": 10, "enforced": True, "decision": "selected"}},
               "experience_diagnostics": ["exp-2: dependency_changed"]}
    explain = explain_view(_view(root, request=request), root=root)
    exp = explain["experiences"]
    assert exp["recorded"] is True
    assert exp["catalog_version"] == 2
    assert exp["selection_mode"] == "v2_applicability"
    assert exp["batch"]["decision"] == "selected"
    assert exp["selected"] == [{"id": "exp-1", "reason": "selected"}]
    assert exp["rejected"] == [{"id": "exp-2", "reason": "dependency_changed"}]
    assert exp["diagnostics"] == ["exp-2: dependency_changed"]
    # 附加可读字段：原样透传（不重算），且明确标记"记录存在"
    assert exp["authority"] == "projection"
    assert exp["rejection"] is None


def test_explain_scope_expiry_never_claims_still_effective(tmp_path: Path) -> None:
    """S3 缺口 §6.4-39：run/node_rework 终态到期未判定 ⇒ 固定"未判定"。"""
    root = _run_root(tmp_path)
    cell = explain_view(_view(root), root=root)["scope_expiry"]
    assert cell == {"determined": False, "state": "unknown", "note": cell["note"]}
    assert "未判定" in cell["note"]


#: OBS-03 文案禁令：整页文本不得把停滞伪装成人工介入（服务端半边先钉住）。
FORBIDDEN_PHRASES = ("在等人工", "等待人工", "等待处理", "待人工确认")


def test_server_projection_text_never_says_waiting_for_human(tmp_path: Path) -> None:
    """服务端下发的所有可读文案都不得出现"等人工"类措辞（界面红字直接用这些字符串）。"""
    root = _run_root(tmp_path)
    last = NOW - 3600.0
    events = [_ev(1, last, "N6", "node_started", "running"),
              _ev(2, last + 10, "N6", "node_failed", "failed",
                  {"message": "provider 403（重试耗尽）"})]
    # 造一个仍在工作且停滞的节点（warn），外加失败节点（failed 必须如实）
    working = [_ev(3, last, "N8", "node_started", "running")]
    payload = {
        "warn": progress_view("N8", events=working, run_dir=root, now=NOW),
        "failed": progress_view("N6", events=events, run_dir=root, now=NOW),
        "explain": explain_view(_view(root), root=root),
    }
    blob = json.dumps(payload, ensure_ascii=False)
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in blob, f"投影文案出现禁令措辞：{phrase!r}"
    assert payload["warn"]["no_progress"]["state"] == "warn"
    assert payload["failed"]["state"] == "failed", "失败必须显式，不得降级成运行中"


def test_explain_attempt_scope_expires_after_bound_attempt_finished(tmp_path: Path) -> None:
    """attempt 作用域：绑定尝试出现 result.json ⇒ 到期（state_expired/not_effective）。"""
    root = _run_root(tmp_path)
    # 先提交 ⇒ Host 预留的绑定尝试 = 1（`next_attempt` 取"首个空位"）
    AC.submit(root, {"operation": "create", "actor": "human:reviewer",
                     "request_id": "req-1", "expected_instruction_revision": 0,
                     "message": "只对这次重发有效", "scope": "attempt",
                     "target_nodes": ["N6"], "dependencies": []})
    row = explain_view(_view(root), root=root)["instructions"]["items"][0]
    assert row["scope"] == "attempt"
    assert row["state_effective"] == "effective", "尝试未结束时仍在有效集内"
    attempt = root / "agent_calls" / "N6" / "attempt-000001"
    attempt.mkdir(parents=True)
    AM.seal_record(attempt / "result.json",
                   {"format_version": 1, "run_id": root.name, "node": "N6",
                    "attempt": 1, "status": "error", "error": "boom"})
    row = explain_view(_view(root), root=root)["instructions"]["items"][0]
    assert row["state_effective"] == "not_effective"
    assert row["unavailable_reason"] == "bound_attempt_finished"


# ==================================================================== 窗口接线（单一实现）

def test_window_annotation_returns_progress_and_explain(tmp_path: Path) -> None:
    root = _run_root(tmp_path)
    request = {"run_id": root.name, "node": "N6", "attempt": 2}
    result = {"run_id": root.name, "node": "N6", "attempt": 2, "status": "validated",
              "session_id": "sess-9", "ts": TS}
    view = _view(root, request=request, result=result, selected=2)
    events = [_ev(1, TS, "N6", "node_started", "running"),
              _ev(2, TS + 10, "N6", "node_finished", "ok", {"mode": "standin"})]
    out = window_annotation(view, node="N6", root=root, events=events, now=NOW)
    assert set(out) == {"progress", "explain"}
    assert out["progress"]["identity"]["attempt"] == 2
    assert out["progress"]["identity"]["session_id"] == "sess-9"
    assert out["progress"]["execution"] == "standin"
    assert out["progress"]["state"] == "done"
    assert set(out["explain"]) == {"instructions", "scope_expiry", "working_memory",
                                   "experiences"}


def test_card_progress_and_window_progress_share_one_implementation(tmp_path: Path) -> None:
    """同一事件/同一 now ⇒ 角色卡 `progress` 与窗口 `progress` 逐字段相同（红线 8）。"""
    root = _run_root(tmp_path)
    events = [_ev(1, TS, "N6", "node_started", "running")]
    card = next(card for card in build_agents(events, run_dir=root, now=NOW)
                if card["role"] == "author")
    via_window = window_annotation(_view(root), node="N6", root=root, events=events,
                                   now=NOW)["progress"]
    assert card["progress"] == via_window


# ==================================================================== contracts.run_view 接线

def _run_doc(root: Path) -> dict:
    return {"run_id": root.name, "run_dir": str(root), "status": "running",
            "mode": "drill", "node_history": []}


def test_run_view_passes_injected_now_to_card_progress(monkeypatch, tmp_path: Path) -> None:
    """`now` 唯一入口：LOOP_NOW 注入 ⇒ 卡片 elapsed/silence 全部按注入时间算。"""
    monkeypatch.setenv("LOOP_NOW", "2026-10-28T12:00:00")
    epoch = datetime.fromisoformat("2026-10-28T12:00:00").timestamp()
    root = _run_root(tmp_path)
    events = [_ev(1, epoch - 90.0, "N6", "node_started", "running")]
    view = contracts.run_view(run_doc=_run_doc(root), kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=events)
    author = next(card for card in view["agents"] if card["role"] == "author")
    assert author["status"] == "working"
    assert author["elapsed_s"] == 90
    assert author["progress"]["silence_s"] == 90
    assert author["progress"]["no_progress"]["state"] == "ok"


def test_run_view_no_progress_warn_uses_module_threshold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOOP_NOW", "2026-10-28T12:00:00")
    epoch = datetime.fromisoformat("2026-10-28T12:00:00").timestamp()
    root = _run_root(tmp_path)
    events = [_ev(1, epoch - 700.0, "N6", "node_started", "running")]
    view = contracts.run_view(run_doc=_run_doc(root), kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=events)
    author = next(card for card in view["agents"] if card["role"] == "author")
    assert author["status"] == "working", "warn 只告警：卡片状态不得被改写"
    assert author["progress"]["no_progress"]["state"] == "warn"
    assert author["progress"]["no_progress"]["threshold_s"] == NO_PROGRESS_THRESHOLD_S


def test_run_view_rejects_unparsable_injected_now(monkeypatch, tmp_path: Path) -> None:
    """解析失败显式报错，不静默回退墙钟。"""
    monkeypatch.setenv("LOOP_NOW", "not-a-time")
    root = _run_root(tmp_path)
    with pytest.raises((ValueError, RuntimeError)):
        contracts.run_view(run_doc=_run_doc(root), kb=_kb(tmp_path), slot_status={},
                           job=None, evidence=None, events=[])


def test_run_view_existing_fields_unchanged(monkeypatch, tmp_path: Path) -> None:
    """既有字段一个都不能少（S4 只加 progress + now，不改形状）。"""
    monkeypatch.setenv("LOOP_NOW", "2026-10-28T12:00:00")
    root = _run_root(tmp_path)
    view = contracts.run_view(run_doc=_run_doc(root), kb=_kb(tmp_path), slot_status={},
                              job=None, evidence=None, events=[])
    for key in ("run_id", "run_dir", "status", "error", "notes", "current_node", "mode",
                "created_at", "updated_at", "node_history", "gate_history",
                "gates_authority", "pending_interrupt", "counts", "evidence", "job", "slot",
                "blockers", "can", "events", "project", "s0_record_id", "agents",
                "stage_map", "agents_authority", "gate_options", "rework",
                "difference_items", "case_states", "conflicts", "baselines",
                "server_authority"):
        assert key in view, key
    assert view["agents_authority"] == "projection"
    for card in view["agents"]:
        assert set(card) >= {"role", "name", "nodes", "active_node", "status",
                             "last_action", "elapsed_s", "summary", "mode", "evidence",
                             "note", "capabilities", "progress"}
