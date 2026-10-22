"""节点执行详情投影（SPEC-02 §10.4 / SPEC-04 §6.7）与 G1 可判材料（SPEC-REV-01 R2/R4）。

固定的是**投影契约**，不是实现细节：

- 已知节点有身份（name/owner）与 §10.4 的逐节点下限字段；
- 未知节点返回 `known=false` 的空投影（200，**不**用 404 冒充"节点不存在"）；
- 历史 run 缺新字段只列 `missing_fields`，不回填、不报错；
- 端点只读（不写盘），只有未知 run 才 404；
- G1 材料逐条带 `before`/`after`/`diff_hunk`/`encoding`，并能打开 N3 摘要与 Host 留痕。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from host import paths as P
from services import node_view
from services.api import app

HUMAN = "human:node-detail-test"

#: §6.7 的响应字段下限（只增不改：实现可多给，不得少给）。
SHAPE_KEYS = {
    "run_id", "node", "known", "name", "owner", "status", "kind",
    "started_at", "finished_at", "source", "summary", "detail",
    "refs", "events", "missing_fields", "authority",
}


def _ev(seq: int, ts: float, kind: str, node: str, status: str,
        detail: dict[str, Any] | None = None, refs: tuple[str, ...] = ()) -> dict[str, Any]:
    """与 `host.progress.Event.as_dict()` 同形的事件（顶层带 refs）。"""
    return {
        "seq": seq, "ts": ts, "run_id": "RUN-TEST-0001", "node": node,
        "kind": kind, "status": status, "detail": detail or {},
        "refs": list(refs), "provisional": False,
    }


# ---------------------------------------------------------------- 纯函数投影

def test_known_node_projection_has_shape_identity_and_lower_bound_fields() -> None:
    events = [
        _ev(1, 100.0, "node_started", "N0", "running"),
        _ev(2, 100.5, "node_finished", "N0", "ok", {
            "mode": "drill", "fixture_files": 11, "gate_init_rc": 0,
            "baseline": "v0", "source": "drill_fixture",
            "summary": "N0：drill 夹具初始化，复制 11 个夹具文件，gate.py init rc=0",
        }, ("/runs/RUN-TEST-0001",)),
    ]
    got = node_view.build_node_detail(
        "RUN-TEST-0001", "N0", events=events,
        run_doc={"mode": "drill", "s0_record_id": None},
    )
    assert SHAPE_KEYS <= set(got), sorted(SHAPE_KEYS - set(got))
    assert got["authority"] == "projection"
    assert got["run_id"] == "RUN-TEST-0001" and got["node"] == "N0"
    assert got["known"] is True
    assert got["name"] and got["owner"] == "Host"
    assert got["status"] == "ok" and got["kind"] == "node_finished"
    assert got["started_at"] == 100.0 and got["finished_at"] == 100.5
    assert got["source"] == "drill_fixture"
    assert got["summary"].startswith("N0：")
    # refs 来自**事件顶层**（node_history 投影会丢弃它），按事件顺序合并去重
    assert got["refs"] == ["/runs/RUN-TEST-0001"]
    # 事件切片：最近一条在前
    assert [e["seq"] for e in got["events"]] == [2, 1]
    assert got["missing_fields"] == []
    # run 文档只取 mode / s0_record_id（S0 来源徽标的数据面）
    assert got["mode"] == "drill" and got["s0_record_id"] is None


def test_refs_are_limited_to_run_dir_and_external_refs_are_counted(tmp_path: Path) -> None:
    """SPEC-04 §6.7：refs 只给 run 目录内路径；目录外引用只计数、不给路径。"""
    inside = str(tmp_path / "n2_diff.json")
    outside = "/home/someone/loop/state/jobs/JOB-1.log"
    events = [
        _ev(1, 100.0, "node_started", "N2", "running"),
        _ev(2, 100.5, "node_finished", "N2", "ok", {
            "source": "kb_tool", "summary": "N2：差异 2 条",
            "routes": {}, "unresolved_count": 0, "offsets": [],
        }, (inside, outside)),
    ]
    got = node_view.build_node_detail(
        "RUN-TEST-0001", "N2", events=events,
        run_doc={"mode": "drill", "s0_record_id": None}, run_dir=str(tmp_path),
    )
    assert got["refs"] == [inside]
    assert got["refs_omitted"] == 1

    # 没有 run_dir 的纯函数直用（单测/外部消费）不做过滤，保持旧行为可复现
    unfiltered = node_view.build_node_detail("RUN-TEST-0001", "N2", events=events)
    assert unfiltered["refs"] == [inside, outside]
    assert unfiltered["refs_omitted"] == 0


@pytest.mark.parametrize(
    "node,event_detail,extra_keys",
    [
        ("N1", {
            "source": "drill_fixture", "summary": "N1：allfiles 3374 条",
            "manifest": {"allfiles_entries": 3374, "allfiles_sha256": "a" * 64,
                         "cases_frozen": 162, "doc_fingerprint": "b" * 64,
                         "commit_parseable": True},
        }, {"manifest.allfiles_entries", "manifest.allfiles_sha256",
            "manifest.cases_frozen", "manifest.doc_fingerprint",
            "manifest.commit_parseable"}),
        ("N2", {
            "source": "kb_tool", "summary": "N2：差异 2 条",
            "routes": {"allfiles": {"ok": True}}, "unresolved_count": 1,
            "offsets": [{"entry_id": "0x0000#0x0004"}],
        }, {"routes", "unresolved_count", "offsets"}),
        ("N3", {"source": "model_standin", "summary": "N3：替身摘要"},
         {"source", "summary"}),
        ("N4", {"source": "human_gate", "summary": "N4：人类决策 confirmed",
                "human_signed": True, "gate": "G1_diff_confirm",
                "decision": "confirmed"},
         {"human_signed"}),
        ("N5", {"source": "drill_fixture", "summary": "N5：必改 1 个用例",
                "index_gap_count": 0}, {"index_gap_count"}),
        ("N7", {"source": "kb_tool", "summary": "N7：编译 1 个用例",
                "failed_cases": []}, {"failed_cases"}),
        ("N9", {"source": "drill_fixture", "summary": "N9：全跑完成",
                "job_id": "JOB-AB12"}, {"job_id"}),
        ("N9_submit", {"source": "drill_fixture", "summary": "N9_submit：已提交",
                       "job_id": "JOB-AB12"}, {"job_id"}),
        ("N12", {"source": "model_standin", "summary": "N12：报告",
                 "ref_count": 3}, {"ref_count"}),
        ("N16", {"source": "kb_tool", "summary": "N16：dry-run rc=0"}, set()),
        ("HALT", {"source": "framework", "summary": "HALT：闸门未放行"}, set()),
    ],
)
def test_lower_bound_fields_per_node(node: str, event_detail: dict[str, Any],
                                     extra_keys: set[str]) -> None:
    events = [
        _ev(1, 10.0, "node_started", node, "running"),
        _ev(2, 11.0, "node_finished", node, "ok", event_detail),
    ]
    got = node_view.build_node_detail("RUN-TEST-0001", node, events=events)
    assert got["known"] is True, node
    assert got["missing_fields"] == [], (node, got["missing_fields"])
    for key in extra_keys:
        assert _nested(got["detail"], key) is not None, key


def _nested(detail: dict[str, Any], dotted: str) -> Any:
    cur: Any = detail
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def test_unknown_node_returns_displayable_empty_projection() -> None:
    events = [
        _ev(1, 10.0, "node_started", "N77", "running"),
        _ev(2, 11.0, "node_finished", "N77", "ok", {"note": "未来节点"}),
    ]
    got = node_view.build_node_detail("RUN-TEST-0001", "N77", events=events)
    assert SHAPE_KEYS <= set(got)
    assert got["known"] is False
    assert got["name"] is None and got["owner"] is None
    # 原始事件与 detail 仍要能看（不得因为"不认识"就丢证据）
    assert got["detail"] == {"note": "未来节点"}
    assert [e["seq"] for e in got["events"]] == [2, 1]
    assert got["missing_fields"] == ["summary", "source"]


def test_not_yet_started_known_node_is_empty_but_known() -> None:
    got = node_view.build_node_detail("RUN-TEST-0001", "N2", events=[])
    assert got["known"] is True
    assert got["status"] is None and got["started_at"] is None
    assert got["detail"] == {} and got["events"] == []
    # 未下发就是未下发：必含字段全部列进 missing_fields，不补默认值
    assert set(got["missing_fields"]) == {"summary", "source", "routes",
                                         "unresolved_count", "offsets"}


def test_historical_run_missing_fields_are_reported_without_backfill() -> None:
    """旧 run 的 detail 是旧形状（无 summary/source/manifest）⇒ 只列缺失，不改事件。"""
    historical = {"artifact": "/runs/RUN-OLD/n1_manifest_new.json", "parent": "v0",
                  "source": "drill_fixture"}
    events = [
        _ev(1, 10.0, "node_started", "N1", "running"),
        _ev(2, 11.0, "node_finished", "N1", "ok", historical),
    ]
    got = node_view.build_node_detail("RUN-OLD", "N1", events=events)
    assert got["detail"] == historical, "投影不得回填/改写历史 detail"
    assert got["source"] == "drill_fixture"
    assert got["summary"] is None
    assert "summary" in got["missing_fields"]
    for key in ("manifest.allfiles_entries", "manifest.cases_frozen",
                "manifest.doc_fingerprint", "manifest.commit_parseable"):
        assert key in got["missing_fields"], got["missing_fields"]
    assert got["detail"] == events[-1]["detail"], "原事件对象不得被就地修改"


def test_status_is_raw_value_not_normalized() -> None:
    """闸门=决策值、N8/N11/N16/HALT 各自语义 ⇒ 原值下发，不归一成 ok/failed。"""
    cases = [
        ("N4", "confirmed"), ("N8", "escalated"), ("N11", "broken"),
        ("N16", "refused"), ("HALT", "halted"),
    ]
    for node, status in cases:
        got = node_view.build_node_detail(
            "RUN-TEST-0001", node,
            events=[_ev(1, 10.0, "node_finished", node, status,
                        {"source": "framework", "summary": "x"})],
        )
        assert got["status"] == status, node


def test_node_failed_carries_source_and_summary(tmp_path: Path) -> None:
    """失败事件同样要能回答"走的是哪条路径、为什么失败"（面板不得显示"完成"）。"""
    from host.progress import ProgressLog
    from services.contracts import KbSources
    from workflows.context import RunCtx

    def _ctx(mode: str) -> RunCtx:
        return RunCtx(
            run_id="RUN-TEST-0002", run_dir=tmp_path, mode=mode, scenario="happy",
            kb=KbSources.from_workspace(tmp_path),
            progress=ProgressLog(tmp_path / "events", "RUN-TEST-0002"),
        )

    drill = _ctx("drill")
    drill.node_failed("N2", message="夹具缺 n2_diff.json")
    event = drill.progress.read()[-1]
    assert event["kind"] == "node_failed"
    assert event["detail"]["message"] == "夹具缺 n2_diff.json"
    assert event["detail"]["source"] == "drill_fixture"
    assert event["detail"]["summary"].startswith("N2：")
    projection = node_view.build_node_detail(
        "RUN-TEST-0002", "N2", events=drill.progress.read())
    assert projection["status"] == "failed"
    assert projection["source"] == "drill_fixture" and projection["summary"]

    real = _ctx("real")
    expected = [("N2", "kb_tool"), ("N4", "human_gate"), ("N3", "model_standin"),
                ("N15_select", "framework"), ("N99", None)]
    for node, source in expected:
        real.node_failed(node, message="x")
        assert real.progress.read()[-1]["detail"]["source"] == source, node


# ---------------------------------------------------------------- 端点

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _start(client: TestClient, **kw) -> str:
    body: dict[str, Any] = {"baseline": "v0", "mode": "drill"}
    body.update(kw)
    r = client.post("/api/runs", json=body)
    assert r.status_code == 200, r.text
    return r.json()["run_id"]


def _wait_interrupt(client: TestClient, rid: str, prefix: str, *, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = client.get(f"/api/runs/{rid}").json()
        if ((view.get("pending_interrupt") or {}).get("id") or "").startswith(prefix):
            return view
        if view.get("status") == "failed":
            raise AssertionError(f"运行失败：{view.get('error')}")
        time.sleep(0.2)
    raise AssertionError(f"未在 {timeout}s 内到达 {prefix}")


def _decide(client: TestClient, rid: str, gate: str, decision: str,
            reason: str = "已核对") -> None:
    r = client.post(f"/api/runs/{rid}/gates/{gate}/decision",
                    json={"decision": decision, "actor": HUMAN, "reason": reason})
    assert r.status_code == 200, r.text


def _drive_full_chain(client: TestClient) -> str:
    """跑到 N16（drill 全链；三闸门都经人类 actor 决策）。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    _decide(client, rid, "G1_diff_confirm", "confirmed")
    _wait_interrupt(client, rid, "G2_report_accept")
    _decide(client, rid, "G2_report_accept", "accept")
    _wait_interrupt(client, rid, "G3_regression_decision")
    _decide(client, rid, "G3_regression_decision", "milestone_only", "I4 未清零，只做里程碑")
    deadline = time.time() + 60
    while time.time() < deadline:
        view = client.get(f"/api/runs/{rid}").json()
        if any(n.get("node") == "N16" for n in view.get("node_history") or []):
            return rid
        if view.get("status") == "failed":
            raise AssertionError(f"运行失败：{view.get('error')}")
        time.sleep(0.2)
    raise AssertionError("未在 60s 内到达 N16")


def test_endpoint_unknown_run_is_404(client: TestClient) -> None:
    r = client.get("/api/runs/RUN-19700101-000000/nodes/N1")
    assert r.status_code == 404
    assert "error" in r.json()["detail"]


def test_endpoint_unknown_node_is_known_false_not_404(client: TestClient) -> None:
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    r = client.get(f"/api/runs/{rid}/nodes/N99")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["known"] is False and body["node"] == "N99"
    assert body["detail"] == {}


def test_drill_full_chain_every_node_has_summary_and_source(client: TestClient) -> None:
    """R4 验收核心：**新 run 的每个节点**都要有 `summary` + `source`（不是只有端点）。"""
    rid = _drive_full_chain(client)
    view = client.get(f"/api/runs/{rid}").json()
    nodes = [n["node"] for n in view["node_history"]]
    for expected in ("N0", "N1", "N2", "N3", "N4", "N5", "N6", "N6_apply", "N7", "N8",
                     "N9", "N9_submit", "N10", "N11", "N12", "N13", "N14",
                     "N15_select", "N15", "N16"):
        assert expected in nodes, f"节点 {expected} 未出现在 node_history：{nodes}"

    for node in nodes:
        r = client.get(f"/api/runs/{rid}/nodes/{node}")
        assert r.status_code == 200, (node, r.text)
        body = r.json()
        assert body["known"] is True, node
        assert isinstance(body["detail"], dict) and body["detail"], node
        assert body["summary"], f"{node} 缺 detail.summary"
        assert body["source"] in node_view.SOURCE_ENUM, (node, body["source"])
        assert body["missing_fields"] == [], (node, body["missing_fields"])

    # 逐节点 source 按实际执行路径（drill 夹具 / 替身模型 / 人类闸门 / Host 框架）
    for node in ("N0", "N1", "N2", "N5", "N7", "N9", "N9_submit"):
        assert client.get(f"/api/runs/{rid}/nodes/{node}").json()["source"] == "drill_fixture", node
    for node in ("N3", "N6", "N8", "N10", "N11", "N12"):
        assert client.get(f"/api/runs/{rid}/nodes/{node}").json()["source"] == "model_standin", node
    for node in ("N4", "N13", "N14"):
        gate_body = client.get(f"/api/runs/{rid}/nodes/{node}").json()
        assert gate_body["source"] == "human_gate", node
        assert gate_body["detail"]["human_signed"] is True, node
    assert client.get(f"/api/runs/{rid}/nodes/N15_select").json()["source"] == "framework"
    assert client.get(f"/api/runs/{rid}/nodes/N16").json()["source"] == "kb_tool"

    # N1/N2/N9/N12 的下限字段确实有真数字（取自各节点自己的 result，不是新算）
    n1 = client.get(f"/api/runs/{rid}/nodes/N1").json()["detail"]["manifest"]
    assert n1["allfiles_entries"] > 0 and n1["allfiles_sha256"]
    assert n1["cases_frozen"] > 0 and n1["doc_fingerprint"]
    assert n1["commit_parseable"] is True
    n2 = client.get(f"/api/runs/{rid}/nodes/N2").json()["detail"]
    assert n2["routes"] and isinstance(n2["offsets"], list)
    assert n2["unresolved_count"] == len(n2["pending_entries"])
    n9 = client.get(f"/api/runs/{rid}/nodes/N9").json()["detail"]
    assert n9["job_id"]
    n12 = client.get(f"/api/runs/{rid}/nodes/N12").json()
    assert "ref_count" in n12["detail"]
    assert "refs" not in n12["detail"], "detail.refs 与事件顶层 refs 同名冲突 ⇒ 已改名 ref_count"

    # 端点只读：跑完之后（没有任何后台写）GET 不得改变 run 目录与事件流落盘
    run_dir = Path(view["run_dir"])
    before = _tree(run_dir) | {("events", P.EVENTS_DIR / f"{rid}.jsonl"): _stamp(P.EVENTS_DIR / f"{rid}.jsonl")}
    for node in ("N0", "N9_submit", "N99"):
        client.get(f"/api/runs/{rid}/nodes/{node}")
    after = _tree(run_dir) | {("events", P.EVENTS_DIR / f"{rid}.jsonl"): _stamp(P.EVENTS_DIR / f"{rid}.jsonl")}
    assert after == before, "节点详情端点必须只读（不得写盘/新增文件）"


def _stamp(path: Path) -> tuple[int, int]:
    st = path.stat()
    return (st.st_size, st.st_mtime_ns)


def _tree(root: Path) -> dict[tuple[str, Path], tuple[int, int]]:
    out: dict[tuple[str, Path], tuple[int, int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[("file", path)] = _stamp(path)
    return out


def test_halt_node_projection_has_summary(client: TestClient) -> None:
    """HALT 只有一个 reason 字段的旧形状 → 补 summary 后仍能原样看到决策原文。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    _decide(client, rid, "G1_diff_confirm", "confirmed")
    _wait_interrupt(client, rid, "G2_report_accept")
    _decide(client, rid, "G2_report_accept", "accept")
    _wait_interrupt(client, rid, "G3_regression_decision")
    _decide(client, rid, "G3_regression_decision", "defer", "冲突未清零，本轮不发版")

    deadline = time.time() + 30
    while time.time() < deadline:
        body = client.get(f"/api/runs/{rid}/nodes/HALT").json()
        if body["status"] == "halted":
            break
        time.sleep(0.2)
    assert body["known"] is True and body["status"] == "halted"
    assert body["summary"] and "HALT" in body["summary"]
    assert body["detail"]["G3_regression_decision"] == "defer", "原始决策字段必须保留"
    assert body["missing_fields"] == []


# ---------------------------------------------------------------- G1 材料可判（R2）

def test_g1_material_entries_carry_before_after_hunk_encoding(client: TestClient) -> None:
    rid = _start(client)
    view = _wait_interrupt(client, rid, "G1_diff_confirm")
    material = (view.get("pending_interrupt") or {}).get("payload") or {}

    entries = (material.get("difference_items") or {}).get("entries") or []
    assert entries, "G1 材料必须有逐条差异"
    for entry in entries:
        for key in ("before", "after", "diff_hunk", "encoding"):
            assert key in entry, (key, sorted(entry))
        # 保留既有字段（只增不改）
        for key in ("entry_id", "kind", "change", "unresolved", "evidence", "lines"):
            assert key in entry, key
    assert any(e["before"] for e in entries), "至少一条要有变更前原文"
    assert any(e["after"] for e in entries), "至少一条要有变更后原文"
    # 夹具的 rtl_file 产出于 R3 之前 ⇒ 没有 encoding 时必须显式 null，不得编造
    assert all(e["encoding"] is None or isinstance(e["encoding"], str) for e in entries)

    n3 = material.get("n3_digest") or {}
    assert n3.get("exists") is True and str(n3.get("path")).endswith("n3_digest.md")

    trace = material.get("host_trace") or {}
    assert trace.get("exists") is True, "drill 的 staged/mock_change_applied.json 必须被复制并投影"
    assert trace.get("changes"), trace
    for change in trace["changes"]:
        for key in ("id", "kind", "old", "new", "line_before", "line_after",
                    "encoding", "rationale", "evidence"):
            assert key in change, (key, sorted(change))
    assert {c["id"] for c in trace["changes"]} >= {"M1"}


def test_n0_copies_host_trace_into_the_run_dir(client: TestClient) -> None:
    """drill 的 N0 复制清单必须含 Host 留痕（否则 G1 看不到"改了什么"的来源）。"""
    rid = _start(client)
    view = _wait_interrupt(client, rid, "G1_diff_confirm")
    run_dir = Path(view["run_dir"])
    assert (run_dir / "staged" / "mock_change_applied.json").is_file()
    n0 = client.get(f"/api/runs/{rid}/nodes/N0").json()
    assert n0["detail"]["fixture_files"] >= 11, n0["detail"]


# ---------------------------------------------------------------- S0 字段（R5）

def test_s0_record_id_roundtrip(client: TestClient) -> None:
    r = client.post("/api/runs", json={
        "baseline": "v0", "mode": "drill", "s0_record_id": "S0-20261022-REHEARSAL-01",
        "now": "2026-10-22T08:00:01",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    view = client.get(f"/api/runs/{rid}").json()
    assert view["s0_record_id"] == "S0-20261022-REHEARSAL-01"
    # 节点详情投影也带同一个来源（面板据此显示"未经 S0 派生"/"S0 记录 …"）
    node = client.get(f"/api/runs/{rid}/nodes/N0").json()
    assert node["s0_record_id"] == "S0-20261022-REHEARSAL-01"


def test_s0_record_id_defaults_to_null(client: TestClient) -> None:
    rid = _start(client, now="2026-10-22T08:00:02")
    assert client.get(f"/api/runs/{rid}").json()["s0_record_id"] is None


def test_s0_record_id_survives_restart(client: TestClient) -> None:
    """来源必须落进 run 文档（`view.json`），否则重启后徽标会凭空消失。"""
    r = client.post("/api/runs", json={
        "baseline": "v0", "mode": "drill", "s0_record_id": "S0-PERSIST-01",
        "now": "2026-10-22T08:00:04",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["run_id"]
    stored = json.loads((P.KB_RUNS / rid / "view.json").read_text(encoding="utf-8"))
    assert stored["s0_record_id"] == "S0-PERSIST-01"


@pytest.mark.parametrize("bad", ["", "S0", "S0-", "s0-abc", "S0 abc", "S0-abc/def", 123])
def test_s0_record_id_invalid_is_400_without_side_effects(client: TestClient, bad: Any) -> None:
    r = client.post("/api/runs", json={"baseline": "v0", "mode": "drill",
                                       "s0_record_id": bad, "now": "2026-10-22T08:00:03"})
    assert r.status_code == 400, r.text
    assert "s0_record_id" in r.json()["detail"]["error"]
    # 拒绝发生在建运行之前 ⇒ 不得留下运行目录
    assert not (P.KB_RUNS / "RUN-20261022-080003").exists()
