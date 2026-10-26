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
    "refs", "events", "missing_fields", "authority", "story",
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
    # 真实路径的 N2 用 offsets（复数）列表：投影必须兼容，单数字段取首项
    assert all(isinstance(e.get("offsets"), list) for e in entries)

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


def test_g1_entry_offset_falls_back_to_offsets_list(tmp_path: Path) -> None:
    """真实 N2 产物只有 `offsets`（复数）时，`offset` 必须回退为首项（否则材料丢 offset）。"""
    from services import contracts

    (tmp_path / "n2_diff.json").write_text(json.dumps({
        "has_change": True,
        "diffs": [{
            "kind": "rtl_file", "id": "RTL/x.v", "entry_id": "RTL/x.v",
            "change": "modified", "before": "a" * 32, "after": "b" * 32,
            "evidence": "RTL/x.v:L171（逐文件 md5 变化）",
            "diff_hunk": "@@ -1 +1 @@\n- 32'h04\n+ 32'h0000_0004",
            "lines": [171, 172], "offsets": ["0xd04"], "encoding": "utf-8",
            "unresolved": None,
        }],
    }), encoding="utf-8")
    view = contracts.diff_entries_view(tmp_path, mode="real")
    entry = view["entries"][0]
    assert entry["offsets"] == ["0xd04"]
    assert entry["offset"] == "0xd04"
    assert entry["diff_hunk"].startswith("@@")


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


# ---------------------------------------------------------------- 闸门二级清单（P-17/P-18/P-29）

def _diff_entry(entry_id: str, kind: str, **over) -> dict[str, Any]:
    """与 `contracts.diff_entries_view` 同形的差异条目（只给投影字段）。"""
    base = {
        "entry_id": entry_id, "kind": kind, "change": "modified", "unresolved": None,
        "evidence": "baselines/v0/allfiles.md5:L1", "lines": [], "offset": None,
        "offsets": [], "segment": None, "before": None, "after": None,
        "diff_hunk": None, "encoding": None, "legacy_drill_fixture": False,
    }
    base.update(over)
    return base


def _waiting_material(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": "G1_diff_confirm:0", "type": "gate_decision", "status": "pending",
        "payload": {
            "gate": "G1_diff_confirm", "cycle": 0, "mode": "drill",
            "entry_decisions_required": True,
            "difference_items": {
                "entries": entries, "count": len(entries),
                "unresolved_count": len([e for e in entries if e.get("unresolved")]),
            },
            "hard_block": [{"code": "I1_UNRESOLVED_ENTRIES", "severity": "blocker",
                            "title": "N2 有 2 条未决差异条目", "message": "I1：…"}],
        },
    }


def test_gate_entries_merge_md5_only_into_attached_evidence() -> None:
    """同一文件的 allfile(md5) + rtl_file(hunk) 合并成 1 条修订点（P-11/P-18）。"""
    from services import contracts

    path = "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v"
    diff = {"entries": [
        _diff_entry(path, "allfile", unresolved="②路无文本 hunk", before="5fcc", after="18fc"),
        _diff_entry(path, "rtl_file", lines=[171, 172], offset="0xd04",
                    diff_hunk="@@ -168,7 +168,8 @@", encoding="utf-8"),
        _diff_entry("RTL/other.v", "rtl_file"),  # 另一个文件的纯行级条目
    ], "unresolved_count": 1}
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", diff=diff, pending_interrupt=_waiting_material(diff["entries"]),
        gate_options={"G1_diff_confirm": [{"value": "confirmed", "label": "差异确认"}]},
        mode="drill",
    )
    assert gate["state"] == "waiting"
    assert gate["counts"]["revision_points"] == 2, "md5-only 附证据不得计入修订点"
    assert gate["counts"]["entries"] == 2
    first = gate["entries"][0]
    assert first["entry_id"] == path
    assert first["has_hunk"] is True and first["lines"] == [171, 172]
    assert first["title"].startswith("内容有改动") and "171–172" in first["title"]
    assert first["attached"] and first["attached"][0]["redundant_of"] == path
    assert first["attached"][0]["kind"] == "allfile"
    assert gate["counts"]["unresolved_points"] == 1, "需人工处置条数按唯一 entry_id 计"
    assert gate["hard_block"] and gate["hard_block"][0]["code"] == "I1_UNRESOLVED_ENTRIES"
    assert gate["entries_required"] is True


def test_gate_entries_decided_g2_never_requires_entries(tmp_path: Path) -> None:
    """R1+R2：已决策态也不得按"未决条目数"给 G2/G3 置 entries_required。

    与等待态同一判据（WEB_UI_SPEC §4.4「判据归属」）：只有 G1 有逐条处置通道。
    这里 `unresolved_count=3` 且 `mode=real`（最容易被误判成"要逐条处置"的组合）。
    """
    from services import contracts

    gate = contracts.gate_entries_view(
        gate="G2_report_accept", run_dir=tmp_path,
        diff={"entries": [_diff_entry("RTL/a.v", "rtl_file", diff_hunk="@@ -1 +1 @@")],
              "unresolved_count": 3},
        authority={"status": "signed", "decision": "accept", "actor": HUMAN,
                   "actor_kind": "human", "human_signed": True},
        mode="real",
    )
    assert gate["state"] == "decided"
    assert gate["entries_required"] is False, "G2 不收逐条处置 ⇒ 已决策态同样必须为假"


def test_gate_entries_decided_reads_host_ledger(tmp_path: Path) -> None:
    """已决策态：逐条处置来自 `decisions/<gate>.json`（不从 gates.json 猜）。"""
    from services import contracts

    path = "RTL/a.v"
    (tmp_path / "decisions").mkdir()
    (tmp_path / "decisions" / "G1_diff_confirm.json").write_text(json.dumps({
        "schema": "loop/gate_entries", "gate": "G1_diff_confirm", "run_id": "RUN-X",
        "records": [{"cycle": 0, "decided_at": "2026-10-23T10:00:00+08:00",
                     "decision": "confirmed", "actor": HUMAN, "reason": "已核对",
                     "entries": {path: {"decision": "confirmed", "reason": None}},
                     # R3-04：Host 签署时一并落"当时的硬阻断"快照
                     "hard_block": [{"code": "I1_UNRESOLVED_ENTRIES",
                                     "title": "N2 有 1 条未决差异条目",
                                     "message": "I1：有 1 条差异还没逐条处置"}]}],
    }, ensure_ascii=False), encoding="utf-8")
    diff = {"entries": [_diff_entry(path, "rtl_file", lines=[9],
                                    diff_hunk="@@ -9,3 +9,4 @@")],
            "unresolved_count": 0}
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", run_dir=tmp_path, diff=diff,
        authority={"status": "signed", "decision": "confirmed", "actor": HUMAN,
                   "actor_kind": "human", "human_signed": True,
                   "signed_at": "2026-10-23T10:00:00+08:00", "note": "已核对", "history_len": 1},
        gate_options={"G1_diff_confirm": [{"value": "confirmed", "label": "差异确认"}]},
        mode="real",
    )
    assert gate["state"] == "decided"
    assert gate["decision"]["decision"] == "confirmed"
    assert gate["decision"]["reason"] == "已核对"
    assert gate["entries"][0]["disposition"] == {"decision": "confirmed", "reason": None}
    assert gate["counts"]["disposed"] == 1
    assert gate["note"] is None
    # R3-04：已决策态的"当时的硬阻断"只从 ledger 快照读（不拿现在的 blockers 冒充当时）
    assert gate["hard_block"] == [{"code": "I1_UNRESOLVED_ENTRIES",
                                   "title": "N2 有 1 条未决差异条目",
                                   "message": "I1：有 1 条差异还没逐条处置"}]
    assert gate["counts"]["hard_block"] == 1


def test_gate_decided_ledger_without_hard_block_says_not_retained(tmp_path: Path) -> None:
    """R3-04：早于落账的旧 run（ledger 无 `hard_block` 键）⇒ 明说未留存，不写 0 冒充"没有硬阻断"。"""
    from services import contracts

    path = "RTL/a.v"
    (tmp_path / "decisions").mkdir()
    (tmp_path / "decisions" / "G1_diff_confirm.json").write_text(json.dumps({
        "schema": "loop/gate_entries", "gate": "G1_diff_confirm", "run_id": "RUN-OLD",
        "records": [{"cycle": 0, "decided_at": "2026-10-22T10:00:00+08:00",
                     "decision": "confirmed", "actor": HUMAN, "reason": "旧 run",
                     "entries": {path: {"decision": "confirmed", "reason": None}}}],
    }, ensure_ascii=False), encoding="utf-8")
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", run_dir=tmp_path,
        diff={"entries": [_diff_entry(path, "rtl_file", diff_hunk="@@ -1 +1 @@")],
              "unresolved_count": 0},
        authority={"status": "signed", "decision": "confirmed", "actor": HUMAN},
        mode="real",
    )
    assert gate["state"] == "decided"
    assert gate["hard_block"] == []
    assert gate["counts"]["hard_block"] is None, "未留存 ≠ 0 条"
    assert gate["note"] and "当时的阻断项未留存" in gate["note"]
    assert "逐条处置未留存" not in gate["note"], "逐条处置已落账，不得误报"


def test_gate_entries_decided_without_ledger_says_not_retained(tmp_path: Path) -> None:
    from services import contracts

    diff = {"entries": [_diff_entry("RTL/a.v", "rtl_file", diff_hunk="@@ -1 +1 @@")],
            "unresolved_count": 1}
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", run_dir=tmp_path, diff=diff,
        authority={"status": "signed", "decision": "confirmed", "actor": HUMAN},
        mode="real",
    )
    assert gate["state"] == "decided"
    assert gate["note"] and "未留存" in gate["note"]
    assert gate["entries"][0]["disposition"] is None


def test_gate_entries_no_material_is_explicit() -> None:
    """G1 没材料 ⇒ 明说差异清单未下发；G2 没材料 ⇒ 明说待确认项未下发（口径不同，不混用）。"""
    from services import contracts

    g1 = contracts.gate_entries_view(gate="G1_diff_confirm", diff={}, mode="drill")
    assert g1["state"] == "no_material"
    assert g1["entries"] == [] and g1["counts"]["revision_points"] == 0
    assert g1["note"] and "差异清单未下发" in g1["note"]

    g2 = contracts.gate_entries_view(gate="G2_report_accept", diff={}, mode="drill")
    assert g2["state"] == "no_material" and g2["entries"] == [] and g2["items"] == []
    assert g2["note"] and "待确认项" in g2["note"]


def test_node_detail_carries_run_status_and_waiting_gate_block(client: TestClient) -> None:
    """等待态 N4 面板：run_status + 二级清单 + 硬阻断（P-29 数据面）。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    body = client.get(f"/api/runs/{rid}/nodes/N4").json()
    assert body["run_status"] == "waiting_gate"
    assert body["run_terminal"] is False
    gate = body["gate"]
    assert gate and gate["state"] == "waiting"
    assert gate["counts"]["revision_points"] == len(gate["entries"]) >= 1
    assert gate["decision"] is None
    # drill 夹具不要求逐条处置（服务端 I1 只在 real 严格）；界面仍可勾选草稿。
    assert gate["entries_required"] is False
    assert all(entry.get("disposition") is None for entry in gate["entries"])
    assert isinstance(gate["hard_block"], list)


def test_node_detail_decided_gate_shows_dispositions(client: TestClient) -> None:
    """已决策态：逐条处置从 `decisions/G1_diff_confirm.json` 回填（Host 落账）。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    _decide(client, rid, "G1_diff_confirm", "confirmed")
    deadline = time.time() + 30
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/api/runs/{rid}/nodes/N4").json()
        if body.get("gate") and body["gate"]["state"] == "decided":
            break
        time.sleep(0.2)
    gate = body["gate"]
    assert gate["state"] == "decided", body
    assert gate["decision"]["decision"] == "confirmed"
    assert gate["note"] is None, "Host 已落账 ⇒ 不得再报'逐条处置未留存'"
    assert gate["counts"]["disposed"] == gate["counts"]["entries"] >= 1
    assert all(entry["disposition"]["decision"] == "confirmed" for entry in gate["entries"])


def test_node_started_present_flag(client: TestClient) -> None:
    """P-33：提交型节点补 node_started 后，面板才能诚实说"有开始/结束区间"。"""
    rid = _drive_full_chain(client)
    for node in ("N0", "N9", "N9_submit"):
        body = client.get(f"/api/runs/{rid}/nodes/{node}").json()
        assert body["node_started_present"] is True, node


def test_unreached_node_in_terminal_run(client: TestClient) -> None:
    """P-30：运行已终态且节点无事件 ⇒ story.not_reached（不得说"等它跑完"）。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    _decide(client, rid, "G1_diff_confirm", "confirmed")
    _wait_interrupt(client, rid, "G2_report_accept")
    _decide(client, rid, "G2_report_accept", "accept")
    _wait_interrupt(client, rid, "G3_regression_decision")
    _decide(client, rid, "G3_regression_decision", "defer", "冲突未清零")
    deadline = time.time() + 30
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/api/runs/{rid}/nodes/N15")
        if body.json()["run_status"] in ("finished", "failed"):
            break
        time.sleep(0.2)
    body = client.get(f"/api/runs/{rid}/nodes/N15").json()
    assert body["run_status"] in ("finished", "failed")
    assert body["run_terminal"] is True
    assert body["story"]["not_reached"] is True
    assert "等它跑完" not in body["story"]["headline"]


# ---------------------------------------------------------------- 报告只读视图（P-28）

def test_report_endpoint_rejects_non_whitelisted_path(client: TestClient) -> None:
    rid = _start(client)
    r = client.get(f"/api/runs/{rid}/report", params={"path": "../../etc/passwd"})
    assert r.status_code == 403, r.text
    r = client.get(f"/api/runs/{rid}/report", params={"path": "n9_result.json"})
    assert r.status_code == 403 and "白名单" in r.json()["detail"]["error"]


def test_report_endpoint_missing_is_404_and_node_block_says_unavailable(client: TestClient) -> None:
    rid = _start(client)
    run_dir = Path(client.get(f"/api/runs/{rid}").json()["run_dir"])
    # drill 夹具会带一份 n12_report.md；删掉才能测"本轮没有报告"的分支。
    for name in ("n12_report.md",):
        target = run_dir / name
        if target.exists() or target.is_symlink():
            target.unlink()
    r = client.get(f"/api/runs/{rid}/report")
    assert r.status_code == 404
    body = client.get(f"/api/runs/{rid}/nodes/N12").json()
    assert body["report"] == {"file": "n12_report.md", "available": False, "bytes": None}


def test_report_endpoint_reads_only_this_run_report(client: TestClient) -> None:
    rid = _drive_full_chain(client)
    run_dir = Path(client.get(f"/api/runs/{rid}").json()["run_dir"])
    text = "# 本轮评估报告\n\n结论：未通过。\n"
    (run_dir / "n12_report.md").write_text(text, encoding="utf-8")
    body = client.get(f"/api/runs/{rid}/nodes/N12").json()
    assert body["report"]["available"] is True and body["report"]["bytes"] == len(text.encode())
    r = client.get(f"/api/runs/{rid}/report")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["file"] == "n12_report.md" and got["truncated"] is False
    assert got["content"] == text
    # 只读：读一次不得改变文件
    assert (run_dir / "n12_report.md").read_text(encoding="utf-8") == text


def test_report_endpoint_truncates_oversized_report(client: TestClient) -> None:
    from services import api as api_mod

    rid = _drive_full_chain(client)
    run_dir = Path(client.get(f"/api/runs/{rid}").json()["run_dir"])
    payload = "x" * (api_mod.REPORT_MAX_BYTES + 1024)
    (run_dir / "n12_report.md").write_text(payload, encoding="utf-8")
    got = client.get(f"/api/runs/{rid}/report").json()
    assert got["truncated"] is True
    assert len(got["content"]) == api_mod.REPORT_MAX_BYTES
    assert got["bytes"] == len(payload.encode())


def test_report_path_refuses_symlink_escape(client: TestClient, tmp_path: Path) -> None:
    """白名单名 + 符号链接也不得越出 run 目录（只读端点不能变成任意路径探测器）。"""
    rid = _drive_full_chain(client)
    run_dir = Path(client.get(f"/api/runs/{rid}").json()["run_dir"])
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    target = run_dir / "n12_report.md"
    if target.exists():
        target.unlink()
    target.symlink_to(outside)
    r = client.get(f"/api/runs/{rid}/report")
    assert r.status_code == 403, r.text


def test_gate_entries_use_the_single_grouping_rule() -> None:
    """AGENTS 红线 8：G1 清单与 N2 结果必须是**同一套**归并口径（不出现第二份实现）。"""
    from services import contracts, node_story

    path = "RTL/a.v"
    entries = [
        _diff_entry(path, "allfile", unresolved="②路无 hunk"),
        _diff_entry(path, "rtl_file", lines=[9], diff_hunk="@@ -9 +9 @@"),
        _diff_entry("RTL/b.v", "rtl_file"),
    ]
    story_groups = node_story.group_diff_entries(entries)
    gate_groups = contracts._group_diff_entries(entries)
    assert [g["entry_id"] for g in story_groups] == [g["entry_id"] for g in gate_groups]
    assert len(gate_groups) == len(story_groups) == 2
    # 归并后每条修订点都带一件附证据（redundant_of 指向主条目）
    assert gate_groups[0]["attached"][0]["redundant_of"] == path


def test_gate_waiting_counts_carry_p29_numbers() -> None:
    """P-29：等待态关键数字（硬阻断/待验用例/未清冲突）来自服务端材料，不由界面自己数。"""
    from services import contracts

    entries = [_diff_entry("RTL/a.v", "rtl_file", diff_hunk="@@ -1 +1 @@")]
    pending = _waiting_material(entries)
    pending["payload"]["case_states"] = {"pending_own": ["tc_a", "tc_b", "tc_c"]}
    pending["payload"]["conflicts"] = {"open": 72, "total": 72, "blocks_release": 72}
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", diff={"entries": entries},
        pending_interrupt=pending, run_status="waiting_gate", mode="real",
    )
    counts = gate["counts"]
    assert counts["hard_block"] == 1
    assert counts["pending_cases"] == 3
    assert counts["conflicts_open"] == 72 and counts["conflicts_total"] == 72


def test_gate_decided_counts_without_material_are_null_not_zero() -> None:
    """缺材料 ⇒ None（不写 0 冒充"没有硬阻断/没有冲突"）。"""
    from services import contracts

    entries = [_diff_entry("RTL/a.v", "rtl_file", diff_hunk="@@ -1 +1 @@")]
    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", diff={"entries": entries},
        authority={"status": "signed", "decision": "confirmed", "actor": HUMAN},
        mode="real",
    )
    counts = gate["counts"]
    assert counts["pending_cases"] is None and counts["conflicts_open"] is None


# ---------------------------------------------------------------- G2/G3 只读待确认项（裁决 #2）

def test_g1_has_no_readonly_items_list() -> None:
    """G1 用 `entries` 做逐条处置；`items` 只属于 G2/G3（不出现第二套处置）。"""
    from services import contracts

    gate = contracts.gate_entries_view(
        gate="G1_diff_confirm", diff={"entries": [_diff_entry("RTL/a.v", "rtl_file")]},
        mode="real",
    )
    assert gate["items"] == []


def test_g2_items_are_readonly_blockers_and_report_open_items() -> None:
    from services import contracts

    items = contracts.gate_entries_view(
        gate="G2_report_accept", diff={}, mode="real",
        blockers=[{"code": "I2_CASES_PENDING", "severity": "blocker",
                   "title": "本轮仍有 3 个用例「已修订待验」", "message": "I2：…"},
                  {"code": "CAPACITY_LONG_TASK", "severity": "info", "title": "槽位", "message": "x"}],
        n12_open_items=["3 个用例仍『已修订待验』"],
    )["items"]
    kinds = [item["kind"] for item in items]
    assert kinds == ["blocker", "open_item"], kinds
    assert items[0]["id"] == "blocker:I2_CASES_PENDING"
    assert items[0]["detail"] == "I2：…"
    # 只读：不给 disposition 字段（界面不得据此提交逐条处置）
    assert all("disposition" not in item for item in items)


def test_g3_items_carry_conflicts_and_regression_cases() -> None:
    from services import contracts

    gate = contracts.gate_entries_view(
        gate="G3_regression_decision", diff={}, mode="real",
        blockers=[{"code": "I4_CONFLICTS_UNCLEARED", "severity": "blocker",
                   "title": "冲突未清零", "message": "I4"}],
        conflicts={"open": 72, "total": 126, "blocks_release": 72},
        selected_cases=["tc_pcie_rw_02", "tc_rtc_05"],
    )
    kinds = [item["kind"] for item in gate["items"]]
    assert kinds == ["blocker", "conflict", "case", "case"], kinds
    assert "72/126" in gate["items"][1]["title"]
    assert gate["items"][2]["title"] == "tc_pcie_rw_02"


def test_g2_readonly_items_state_is_read_only() -> None:
    from services import contracts

    gate = contracts.gate_entries_view(
        gate="G2_report_accept", diff={}, mode="real",
        blockers=[{"code": "I2_CASES_PENDING", "severity": "blocker", "title": "t", "message": "m"}],
    )
    assert gate["state"] == "read_only" and gate["note"] is None
    empty = contracts.gate_entries_view(gate="G2_report_accept", diff={}, mode="real")
    assert empty["state"] == "no_material" and empty["items"] == []
    assert empty["note"] and "未下发" in empty["note"]


def test_n13_waiting_projection_carries_readonly_items(client: TestClient) -> None:
    """G2 等待态：面板拿到只读待确认项（阻断项白话），且仍然没有 disposition/勾选语义。"""
    rid = _start(client)
    _wait_interrupt(client, rid, "G1_diff_confirm")
    _decide(client, rid, "G1_diff_confirm", "confirmed")
    _wait_interrupt(client, rid, "G2_report_accept")
    body = client.get(f"/api/runs/{rid}/nodes/N13").json()
    gate = body["gate"]
    assert gate["state"] == "waiting"
    assert gate["counts"]["hard_block"] >= 1
    assert gate["items"], "G2 等待态必须给出只读待确认项"
    assert gate["items"][0]["kind"] == "blocker"
    assert all("disposition" not in item for item in gate["items"])
    assert gate["entries"] == [] or gate["entries_required"] is False


def test_n14_decided_projection_lists_regression_cases(client: TestClient) -> None:
    """G3 已决策 + N15_select 已跑 ⇒ 只读清单里能看到回归选集用例。"""
    rid = _drive_full_chain(client)
    body = client.get(f"/api/runs/{rid}/nodes/N14").json()
    gate = body["gate"]
    assert gate["state"] == "decided"
    kinds = [item["kind"] for item in gate["items"]]
    assert "case" in kinds, kinds
    cases = [item["title"] for item in gate["items"] if item["kind"] == "case"]
    assert cases and all(isinstance(case, str) and case for case in cases)
    assert all("disposition" not in item for item in gate["items"])


# ---------------------------------------------------------------- R3-11：新 run 可选下限
#
# 新 run 才下发的 detail 字段**不得**进 `REQUIRED_FIELDS`（否则旧 run 每个节点都报 missing）；
# 它们登记为 SPEC-02 §10.4.5 的"可选下限"：新 run 必须下发（显式 `null` 也算下发），
# 旧 run 缺失不算缺陷（`missing_fields` 不受影响）。

OPTIONAL_NEW_RUN_FIELDS: dict[str, tuple[str, ...]] = {
    "N3": ("digest_summary", "digest_confirmations", "groups_count", "offered_segments_empty"),
    "N5": ("to_check_case_count", "to_check_cases"),
    "N6": ("case_edits", "case_edits_source", "observation_points"),
    "N6_apply": ("case_edits", "applied_cases"),
    "N7": ("case_count",),
    "N8": ("check_count", "must_fix_count", "cycle", "limit"),
    "N9": ("koutou1_by_case", "example_line", "identity", "cases_detail"),
    "N9_submit": ("cases",),
    "N10": ("cases_table", "classification"),
    "N11": ("identity_table", "unclosed", "rework_requests_count"),
    "N12": ("refs_parseable_count", "open_items", "cases_summary"),
    "N15_select": ("will_really_run",),
    "N15": ("will_really_run", "executed", "failed_cases"),
    "N16": ("reason_line", "result_artifact"),
}


def test_optional_new_run_fields_are_not_required_lower_bounds() -> None:
    for node, fields in OPTIONAL_NEW_RUN_FIELDS.items():
        required = set(node_view.REQUIRED_FIELDS.get(node, node_view.DEFAULT_REQUIRED))
        for field in fields:
            assert field not in required, (
                f"{node}.{field} 是新 run 才下发的可选下限，不得塞进该节点的 REQUIRED_FIELDS"
                "（否则旧 run 全报 missing）"
            )


def test_new_run_drill_chain_carries_optional_fields(client: TestClient) -> None:
    """新 drill 全链：可选下限字段必须**存在**（显式 null 也算下发）。"""
    rid = _drive_full_chain(client)
    for node, fields in OPTIONAL_NEW_RUN_FIELDS.items():
        body = client.get(f"/api/runs/{rid}/nodes/{node}").json()
        detail = body["detail"]
        for field in fields:
            assert field in detail, f"{node}.{field} 未下发（新 run 可选下限）"
        assert body["missing_fields"] == [], (node, body["missing_fields"])


def _old_style_detail(node: str) -> dict[str, Any]:
    """只含 `REQUIRED_FIELDS` 下限的老形状 detail（模拟旧 run：没有可选下限字段）。"""
    out: dict[str, Any] = {}
    for dotted in node_view.REQUIRED_FIELDS.get(node, node_view.DEFAULT_REQUIRED):
        parts = dotted.split(".")
        cur = out
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = "x"
    return out


def test_old_run_missing_optional_fields_is_not_flagged_missing() -> None:
    for node in OPTIONAL_NEW_RUN_FIELDS:
        detail = _old_style_detail(node)
        events = [
            _ev(1, 100.0, "node_started", node, "running"),
            _ev(2, 100.5, "node_finished", node, "ok", detail),
        ]
        body = node_view.build_node_detail("RUN-OLD", node, events=events,
                                           run_doc={"mode": "drill"})
        assert body["missing_fields"] == [], (node, body["missing_fields"])
        for field in OPTIONAL_NEW_RUN_FIELDS[node]:
            assert field not in body["detail"], (node, field)
