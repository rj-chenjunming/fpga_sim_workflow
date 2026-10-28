"""S3a WM：可重建工作记忆（REV-13 §6 / WM-01～05；先失败用例）。

本文件固定四类可观察断言，全部只看**载荷/记录**，不读实现细节：

- **WM-01**：同一明确来源重建 ⇒ 同一 `snapshot_sha256`；源版本变化 ⇒ 新指纹；
  重建不扫描"目录里最新一次"（孤儿 attempt 不被消费）。
- **WM-02**：五类条目齐全；`model_proposal` 绝不晋升 `observed_fact`；
  `open_issue` 沿用 H1/H2b 的 `issue_id`/`follow_up`，不新建关闭/重开规则。
- **WM-03**：源半件/篡改/越界/跨 run ⇒ `ValueError`；强制材料超预算 ⇒ 调用前失败、
  不截断、不调用模型（缺口只作报告，总预算仍由 `AM.check_budget` 唯一判定）。
- **WM-04/05**：`input_ref` 指向**本次实际发送**的 `input_data` 既有字段，可解析、无循环、
  不指向 `working_memory` 自身；已在输入中的正文不复制（大事实只留引用）；预算按真实序列化。
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json

import pytest

from host import agent_handoff as H
from host import agent_memory as AM
from host import agent_review as R
from host import agent_working_memory as WM
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.chunks import model_request as MR
from workflows.context import RunCtx

# `provider` 夹具（受控 Agently 替身，记录每次实际发送的 input）沿用既有范式；
# 只是复用夹具，不改变 `test_agent_context_memory.py` 的任何断言。
from test_agent_context_memory import provider, write_json  # noqa: F401

#: 每个测试唯一 run_id（纪律：同一 run_id 会把两次运行落进同一个 `kb/runs/<id>`）。
_RUNS = itertools.count(1)


@pytest.fixture
def ctx(tmp_path):
    root = tmp_path / "workspace"
    run_id = f"RUN-20300103-{next(_RUNS):06d}"
    run = root / "runs" / run_id
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    return RunCtx(run_id, run, "real", "happy", KbSources.from_workspace(root),
                  ProgressLog(tmp_path / "events", run_id))


def accept(kind, payload, *, offered):
    """机制层的替身校验器（真正判据仍是 `model_steps._validate`，这里是机制测试夹具）。"""
    return {"ok": True, "problems": [], "accepted": payload.get("data") or {}}


def n3_input(ctx, *, size: int = 20) -> dict:
    diffs = [{"entry_id": f"e{i}", "id": f"e{i}", "offsets": ["0x0"], "segment": "s",
              "kind": "modify", "before": "old-" + "a" * size, "after": "new-" + "b" * size}
             for i in range(3)]
    return {"run_id": ctx.run_id, "diffs": diffs,
            "offered_segments": sorted({d["segment"] for d in diffs}),
            "coverage": {"scope": "all_differences", "total": len(diffs),
                         "provided": len(diffs), "complete": True, "error": None}}


def n6_input(ctx, *, targets=None, must_fix=("fix mask", "fix mask")) -> dict:
    handoff = H.build(ctx, {"data": {"must_fix": list(must_fix)}}, {})
    targets = copy.deepcopy(targets or [{"case": "demo", "source_md5": "m",
                                        "excerpt": {"text": "old"}}])
    assignment = H.assignment(handoff, targets)
    return {"run_id": ctx.run_id, "cycle": 1, "targets": targets,
            "rework_reasons": [item["text"] for item in handoff["issues"]],
            "rework_handoff": handoff, "rework_assignment": assignment,
            "must_change_count": len(targets),
            "rule": "只针对 targets 的用例", "write_scope_rule": "只写沙箱"}


def sealed_author(ctx):
    """H2a/H2b 的**已封存** N6 作者来源（复用既有构造，不另造半件）。"""
    from test_agent_responses import sealed

    return sealed(ctx)


def reviewer_input(ctx, node: str = "N8") -> dict:
    """N8/N11 的真实输入形状：`author_handoff` 来自封存 N6，`review_assignment` 由 Host 构造。"""
    packet = H.for_reviewer(ctx, sealed_author(ctx), node)
    value = {"run_id": ctx.run_id, "author_handoff": packet}
    if node == "N8":
        value.update(sandbox_cases=[{"file": "demo.sv", "excerpt": "actual candidate"}],
                     coverage_summary={"full_files": 1, "region_files": 0,
                                       "used_bytes": 20, "budget_bytes": 60000},
                     revision_points=[{"case": "demo"}], applied_edits=[],
                     checklist="检查清单", rule="只依据本 input 的材料")
    else:
        value.update(identity={"consistent": True, "cases": [{"case": "demo"}]},
                     evidence={"present": True, "path": "evidence.log"},
                     counts={"koutou1": 1, "koutou2": 1}, case_states={},
                     verdict={"passed": True}, rule="只判证据链是否成链")
    value["review_assignment"] = R.prepare(node, value)
    return value


def review_response(node: str, value: dict, outcome: str = "closed") -> dict:
    """合法复核输出（形状对齐 `agent_review.validate`；只用于重建路径的夹具）。"""
    opened = outcome == "open"
    if node == "N8":
        out = {"verdict": "rework" if opened else "pass", "findings": [],
               "must_fix": ["repair candidate"] if opened else []}
        refs = ["/sandbox_cases/0/excerpt"]
    else:
        out = {"chain": "broken" if opened else "intact", "reasons": [], "caveats": [],
               "rework_requests": [{"case": "demo", "what": "repair identity",
                                    "basis": "md5"}] if opened else []}
        refs = ["/identity/consistent"]
    assigned = value["review_assignment"]
    out["issue_reviews"] = [
        {"issue_id": item["issue_id"],
         "review_context_sha256": assigned["review_context_sha256"],
         "outcome": outcome, "rationale": "checked against current material",
         "evidence_refs": list(refs), "rework_index": 0 if opened else None}
        for item in assigned["issues"]]
    return out


def entries_of(wm, kind: str) -> list[dict]:
    return [item for item in wm.payload["entries"] if item["kind"] == kind]


# ---------------------------------------------------------------- WM-01 确定性


def test_same_sources_rebuild_to_identical_snapshot(ctx):
    value = n6_input(ctx)
    first = WM.build(ctx, "N6", copy.deepcopy(value))
    second = WM.build(ctx, "N6", copy.deepcopy(value))
    assert first.payload == second.payload
    assert first.source_map == second.source_map
    assert first.payload["snapshot_sha256"] == AM.fingerprint(
        {"version": WM.WM_VERSION, "entries": first.payload["entries"],
         "unavailable": first.payload["unavailable"]})
    order = [(item["kind"], item["entry_id"]) for item in first.payload["entries"]]
    assert order == sorted(order)


def test_key_insertion_order_does_not_change_snapshot(ctx):
    value = n6_input(ctx)
    reordered = {key: value[key] for key in reversed(list(value))}
    assert WM.build(ctx, "N6", reordered).payload == WM.build(ctx, "N6", copy.deepcopy(value)).payload


def test_source_version_change_yields_new_snapshot(ctx):
    value = n6_input(ctx)
    first = WM.build(ctx, "N6", copy.deepcopy(value))
    changed = copy.deepcopy(value)
    changed["rework_handoff"]["issues"][0]["requirement"] = "另一条要求"
    changed["rework_handoff"]["issues"][0]["text"] = "另一条要求"
    changed["rework_reasons"] = ["另一条要求"]
    second = WM.build(ctx, "N6", changed)
    assert first.payload["snapshot_sha256"] != second.payload["snapshot_sha256"]
    # 旧快照不得被当当前事实：条目绑定的源版本指纹也变了（快照自身不提供"旧快照仍有效"的判定）
    changed_versions = {item["entry_id"]: item["resource_versions"]
                        for item in second.payload["entries"]}
    assert any(changed_versions[item["entry_id"]] != item["resource_versions"]
               for item in first.payload["entries"])
    third = copy.deepcopy(value)
    third["targets"][0]["excerpt"]["text"] = "changed"
    assert WM.build(ctx, "N6", third).payload["snapshot_sha256"] != first.payload["snapshot_sha256"]


def test_rebuild_ignores_orphan_latest_attempt(ctx):
    """重建只走明确来源，不扫描目录里的"最新一次"。"""
    value = n6_input(ctx)
    first = WM.build(ctx, "N6", copy.deepcopy(value))
    orphan = ctx.run_dir / "agent_calls" / "N6" / "attempt-000002"
    orphan.mkdir(parents=True)
    (orphan / "request.json").write_text("{broken", encoding="utf-8")
    assert WM.build(ctx, "N6", copy.deepcopy(value)).payload == first.payload


# ---------------------------------------------------------------- WM-02 五类条目


def test_only_declared_kinds_and_exactly_one_of_value_or_input_ref(ctx):
    value = reviewer_input(ctx, "N8")
    wm = WM.build(ctx, "N8", copy.deepcopy(value))
    assert wm.payload["version"] == WM.WM_VERSION
    assert {item["kind"] for item in wm.payload["entries"]} <= WM.ENTRY_KINDS
    for item in wm.payload["entries"]:
        assert ("value" in item) != ("input_ref" in item), item
        assert item["source_keys"], item
        assert item["applicability"] == {"node": "N8"}
        assert set(item["resource_versions"]) == set(item["source_keys"])


def test_model_proposal_is_never_promoted_to_fact(ctx):
    value = reviewer_input(ctx, "N8")
    wm = WM.build(ctx, "N8", copy.deepcopy(value))
    proposals = [item for item in wm.payload["entries"]
                 if str(item.get("input_ref", "")).startswith("/author_handoff")]
    assert proposals, "作者回应必须作为 model_proposal 条目出现"
    assert {item["kind"] for item in proposals} == {"model_proposal"}
    assert not [item for item in entries_of(wm, "observed_fact")
                if str(item.get("input_ref", "")).startswith("/author_handoff")]


def test_open_issue_entries_reuse_h1_identity_and_follow_up(ctx):
    value = n6_input(ctx)
    handoff = value["rework_handoff"]
    # H2b 的 follow_up 形状（复用既有字段，WM 只投影、不改写）
    handoff["issues"][0]["follow_up"] = {"issue_id": "issue-follow-up", "text": "repair"}
    wm = WM.build(ctx, "N6", copy.deepcopy(value))
    issues = entries_of(wm, "open_issue")
    assert len(issues) == len(handoff["issues"])
    for index, entry in enumerate(issues):
        assert entry["input_ref"] == f"/rework_handoff/issues/{index}"
        source = WM.resolve_input_ref(value, entry["input_ref"])
        assert source["issue_id"] == handoff["issues"][index]["issue_id"]
        assert source.get("follow_up") == handoff["issues"][index].get("follow_up")
        # 不新建关闭/重开规则：条目里不出现自造状态字段
        assert "status" not in entry and "closed" not in json.dumps(entry)
    # 同一 issue_id 跨轮沿用：identity 不再是 WM 重新生成的
    assert [WM.resolve_input_ref(value, item["input_ref"])["issue_id"]
            for item in issues] == [item["issue_id"] for item in handoff["issues"]]


def test_instructions_become_constraints_and_reuse_sent_body(ctx):
    value = n6_input(ctx)
    value["human_interventions"] = ["只改 TESTLIB，不要动 RTL"]
    wm = WM.build(ctx, "N6", copy.deepcopy(value),
                  instructions=tuple(value["human_interventions"]))
    constraints = [item for item in entries_of(wm, "constraint")
                   if str(item.get("input_ref", "")).startswith("/human_interventions")]
    assert constraints and constraints[0]["input_ref"] == "/human_interventions/0"
    assert WM.resolve_input_ref(value, constraints[0]["input_ref"]) == "只改 TESTLIB，不要动 RTL"


def test_instruction_not_sent_with_the_request_is_rejected_instead_of_copied(ctx):
    """约束只留引用：未随本次请求发送的指令不得复制正文，也不得留悬空索引。"""
    value = n6_input(ctx)
    with pytest.raises(ValueError, match="引用|发送"):
        WM.build(ctx, "N6", copy.deepcopy(value), instructions=("未随请求发送的指令",))


# ---------------------------------------------------------------- WM-03 失败显式


@pytest.mark.parametrize("fault", ["tamper", "half", "traversal", "cross_run", "symlink", "no_source"])
def test_broken_or_foreign_source_fails_explicitly(ctx, tmp_path, fault):
    value = reviewer_input(ctx, "N8")
    source = value["author_handoff"]["author_source"]
    folder = (ctx.run_dir / source["request_ref"]).parent
    if fault == "tamper":
        # 内容被换、校验和同步重算（`record_state` 看不出来）⇒ 仍须按指纹失败
        target = folder / "result.json"
        record = json.loads(target.read_text())
        record["status"] = "error"
        target.chmod(0o600)
        target.write_bytes(AM.encoded(record))
        digest = target.with_suffix(".sha256")
        digest.chmod(0o600)
        digest.write_text(hashlib.sha256(target.read_bytes()).hexdigest())
    elif fault == "half":
        (folder / "result.sha256").unlink()
    elif fault == "traversal":
        source["request_ref"] = "../outside/request.json"
        source["result_ref"] = "../outside/result.json"
    elif fault == "cross_run":
        # 两份文件彼此一致，但属于另一个 run
        for name in ("request", "result"):
            target = folder / f"{name}.json"
            record = json.loads(target.read_text())
            record["run_id"] = "RUN-19990101-000000"
            target.chmod(0o600)
            target.write_bytes(AM.encoded(record))
            digest = target.with_suffix(".sha256")
            digest.chmod(0o600)
            digest.write_text(hashlib.sha256(target.read_bytes()).hexdigest())
    elif fault == "symlink":
        destination = tmp_path / "moved"
        folder.rename(destination)
        folder.symlink_to(destination, target_is_directory=True)
    else:
        value["author_handoff"].pop("author_source")
    with pytest.raises(ValueError):
        WM.build(ctx, "N8", value)


async def test_mandatory_material_over_budget_fails_before_call(ctx, provider, monkeypatch):
    """强制材料超限 ⇒ 调用前失败、不截断、不抽样；缺口只报，总预算仍由 check_budget 判。"""
    provider["cfg"].available = True
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES", 400)
    value = n6_input(ctx, targets=[{"case": "demo", "excerpt": {"text": "x" * 800}}])
    with pytest.raises(RuntimeError, match="budget|预算") as excinfo:
        await MR.run_attempt(ctx, "N6", prompt_key="n6_author", input_data=value,
                             offered={"cases": {"demo"},
                                      "rework_assignment": value["rework_assignment"]},
                             validate=accept)
    assert "mandatory_bytes" in str(excinfo.value)          # 缺口报告可读
    assert provider["inputs"] == [] and provider["agents"] == []  # 未调用模型
    record = AM.verify_attempt(next((ctx.run_dir / "agent_calls" / "N6").iterdir()))
    assert record["result"]["status"] == "error"
    # 不截断：已封存的请求仍保留全部强制材料原文
    assert record["request"]["input"]["targets"][0]["excerpt"]["text"] == "x" * 800
    assert [item["requirement"] for item
            in record["request"]["input"]["rework_handoff"]["issues"]] == ["fix mask", "fix mask"]
    assert record["request"]["working_memory_source_map"]["over_budget"] is True


# ---------------------------------------------------------------- WM-04/05 载体与预算


@pytest.mark.parametrize("pointer", ["", "diffs", "/working_memory",
                                     "/working_memory/entries/0", "/missing",
                                     "/diffs/9", "/diffs/-1", "/diffs/01", "/diffs/0/nested"])
def test_input_ref_pointer_validation_rejects_self_cycle_and_absence(pointer):
    input_data = {"diffs": [{"a": 1}], "working_memory": {"entries": []}}
    with pytest.raises(ValueError):
        WM.resolve_input_ref(input_data, pointer)


@pytest.mark.parametrize("pointer,expected", [("/diffs", [{"a": 1}]), ("/diffs/0", {"a": 1}),
                                              ("/diffs/0/a", 1)])
def test_input_ref_pointer_resolves_existing_fields(pointer, expected):
    assert WM.resolve_input_ref({"diffs": [{"a": 1}]}, pointer) == expected


def test_large_fact_is_referenced_not_copied(ctx):
    big = "y" * 20000
    value = n6_input(ctx, targets=[{"case": "demo", "excerpt": {"text": big}}])
    wm = WM.build(ctx, "N6", copy.deepcopy(value))
    entry = next(item for item in wm.payload["entries"] if item.get("input_ref") == "/targets")
    assert "value" not in entry
    body = json.dumps(wm.payload, ensure_ascii=False)
    assert big not in body and "old" not in body
    assert len(AM.encoded(wm.payload)) < len(AM.encoded(big))
    assert WM.resolve_input_ref(value, entry["input_ref"]) == value["targets"]


async def test_input_refs_resolve_in_the_sent_request_and_budget_is_real(ctx, provider, monkeypatch):
    value = reviewer_input(ctx, "N8")
    measured: dict = {}
    real = AM.measure_budget

    def spy(input_data, contract):
        out = real(input_data, contract)
        measured.update(size=out["used_bytes"], input=input_data, contract=contract)
        return out

    monkeypatch.setattr(AM, "measure_budget", spy)
    out = await MR.run_attempt(ctx, "N8", prompt_key="n8_check", input_data=value,
                               offered={"cases": {"demo"}, "review_context": value},
                               validate=accept)
    sent = provider["inputs"][-1]
    payload = sent["working_memory"]
    assert payload["availability"] == "verified"
    assert payload["snapshot_sha256"]
    for entry in payload["entries"]:
        if "input_ref" in entry:
            # 引用必须在本条**实际发送**的输入里解析得到（空列表/空对象也是真实存在的字段值）
            assert WM.resolve_input_ref(sent, entry["input_ref"]) is not None
    # 预算仍是同一次真实序列化测量（唯一判据 `AM.measure_budget`/`check_budget`）
    assert measured["input"] == sent
    assert measured["size"] == real(sent, measured["contract"])["used_bytes"]
    without = {key: item for key, item in sent.items() if key != "working_memory"}
    assert measured["size"] > real(without, measured["contract"])["used_bytes"]
    assert measured["size"] <= AM.MAX_CONTEXT_BYTES
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    assert record["request"]["input"] == sent


async def test_run_attempt_seals_working_memory_and_cold_source_map(ctx, provider):
    value = n3_input(ctx)
    out = await MR.run_attempt(ctx, "N3", prompt_key="n3_digest", input_data=value,
                               offered={"diff_ids": {d["entry_id"] for d in value["diffs"]},
                                        "segments": {"s"}}, validate=accept)
    sent = provider["inputs"][-1]
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    sealed_input = record["request"]["input"]
    # 模型看到的与封存的同一份（随原 request 封存）
    assert sealed_input["working_memory"] == sent["working_memory"]
    assert sealed_input["working_memory"]["version"] == WM.WM_VERSION
    assert sealed_input["working_memory"]["availability"] in {"verified", "unavailable"}
    assert set(sealed_input["working_memory"]) == {"version", "availability",
                                                  "snapshot_sha256", "entries", "unavailable"}
    # source map 冷存：进 request 顶层，**不进**模型输入
    source_map = record["request"]["working_memory_source_map"]
    assert "working_memory_source_map" not in sent
    assert source_map["run_id"] == ctx.run_id and source_map["node"] == "N3"
    assert source_map["snapshot_sha256"] == sent["working_memory"]["snapshot_sha256"]
    assert source_map["entries"] and all(item["consumers"] == ["N3"]
                                         for item in source_map["entries"])
    assert {item["source_keys"][0] for item in source_map["entries"]} == set(source_map["sources"])
    # `input_digest` 形状保持 `{key: len|value}`，且**不计入机制层派生投影** `working_memory`
    # （展示摘录回到 S3 之前的字节口径；`request.input` 仍完整封存 working_memory）。
    assert set(out["input_digest"]) == set(sent) - {"working_memory"}
    assert "working_memory" not in out["input_digest"]


async def test_scope_and_v1_experiences_unchanged_by_working_memory(ctx, provider):
    """WM 必须在 `scope`/`experiences` 之后加入：v1 作用域逐值相等行为不许变。"""
    value = n3_input(ctx)
    await MR.run_attempt(ctx, "N3", prompt_key="n3_digest", input_data=value,
                         offered={"diff_ids": set(), "segments": {"s"}}, validate=accept)
    attempt = next((ctx.run_dir / "agent_calls" / "N3").iterdir())
    scope = AM.verify_attempt(attempt)["request"]["scope"]
    assert set(scope) == {"env_id", "baseline", "facts_sha256", "prompt_sha256", "schema_sha256"}
    source = ctx.kb.root / "runs" / "historical" / "note.md"
    source.parent.mkdir(parents=True)
    source.write_text("human checked evidence", encoding="utf-8")
    item = {"id": "lesson-1", "status": "approved", "approved_by": "human:reviewer",
            "scope": scope,
            "source": {"path": "runs/historical/note.md",
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
            "advice": "Check the mask against the current RTL."}
    write_json(ctx.kb.root / "adjudication" / "agent_experiences.json",
               {"version": 1, "items": [item]})
    await MR.run_attempt(ctx, "N3", prompt_key="n3_digest", input_data=value,
                         offered={"diff_ids": set(), "segments": {"s"}}, validate=accept)
    second = next(path for path in (ctx.run_dir / "agent_calls" / "N3").iterdir()
                  if path.name == "attempt-000002")
    record = AM.verify_attempt(second)
    assert record["request"]["scope"] == scope
    assert provider["inputs"][-1]["approved_experiences"][0]["id"] == "lesson-1"


# ---------------------------------------------------------------- 旧格式/缺来源


def test_legacy_or_missing_source_is_unavailable_not_verified(ctx):
    value = reviewer_input(ctx, "N8")
    value["author_handoff"] = {"availability": "legacy",
                               "author_source": value["author_handoff"]["author_source"]}
    wm = WM.build(ctx, "N8", copy.deepcopy(value))
    assert wm.payload["availability"] == "unavailable"
    assert any(item["kind"] == "model_proposal" for item in wm.payload["unavailable"])
    assert not entries_of(wm, "model_proposal")
    # 当前权威事实仍然保留（不因为一个来源旧就整体丢弃）
    assert entries_of(wm, "observed_fact")
    assert wm.payload["snapshot_sha256"]


def test_gate_facts_are_read_only_projection_and_absent_source_is_unavailable(ctx):
    base = {"run_id": ctx.run_id, "buckets": [], "revision_points": [], "counts": {}, "rule": "r"}
    without = WM.build(ctx, "N10", copy.deepcopy(base), gate_projection=None)
    assert without.payload["availability"] == "unavailable"
    assert any(item["kind"] == "human_decision" for item in without.payload["unavailable"])
    assert not entries_of(without, "human_decision")

    projection = {"present": True, "run_id": ctx.run_id, "anchor_ok": True,
                  "gates": {"G1_diff_confirm": {
                      "decision": "confirmed", "status": "signed", "actor": "human:operator",
                      "actor_kind": "human", "human_signed": True,
                      "signed_at": "2026-10-28T00:00:00+08:00", "note": "ok",
                      "rework_target": None, "history_len": 1}}}
    withgate = WM.build(ctx, "N10", copy.deepcopy(base), gate_projection=projection)
    assert withgate.payload["availability"] == "verified"
    entry = entries_of(withgate, "human_decision")[0]
    assert entry["value"]["gate"] == "G1_diff_confirm"
    assert entry["value"]["decision"] == "confirmed"
    assert entry["value"]["human_signed"] is True
    # 只投影、不判定：条目里没有自造的新决策/签署字段
    assert set(entry["value"]) <= {"gate", "decision", "actor", "actor_kind", "human_signed",
                                   "signed_at", "note", "rework_target", "history_len"}


@pytest.mark.parametrize("fault", ["anchor", "other_run", "absent"])
def test_unverified_gate_source_is_explicit(ctx, fault):
    projection = {"present": True, "run_id": ctx.run_id, "anchor_ok": True,
                  "gates": {"G1_diff_confirm": {
                      "decision": "confirmed", "status": "signed", "actor": "human:operator",
                      "actor_kind": "human", "human_signed": True,
                      "signed_at": "2026-10-28T00:00:00+08:00", "note": None,
                      "rework_target": None, "history_len": 1}}}
    if fault == "anchor":
        projection["anchor_ok"] = False
        with pytest.raises(ValueError):
            WM.build(ctx, "N10", {"run_id": ctx.run_id, "rule": "r"}, gate_projection=projection)
    elif fault == "other_run":
        projection["run_id"] = "RUN-19990101-000000"
        with pytest.raises(ValueError):
            WM.build(ctx, "N10", {"run_id": ctx.run_id, "rule": "r"}, gate_projection=projection)
    else:
        absent = {"present": False, "run_id": ctx.run_id, "reason": "账本缺失",
                  "gates": {}, "anchor_ok": None}
        wm = WM.build(ctx, "N12", {"run_id": ctx.run_id, "rule": "r"}, gate_projection=absent)
        assert wm.payload["availability"] == "unavailable"
        assert any(item["kind"] == "human_decision" for item in wm.payload["unavailable"])


# ---------------------------------------------------------------- H2b 回归（G-WM-1）


@pytest.mark.parametrize("node", ["N8", "N11"])
def test_review_reconstruction_survives_sealed_working_memory(ctx, node):
    """封存输入里带 `working_memory` 时，N8/N11 复核包仍能重建且上下文指纹不变。"""
    author = sealed_author(ctx)
    value = reviewer_input(ctx, node)
    wm = WM.build(ctx, node, copy.deepcopy(value))
    sealed_input = {**copy.deepcopy(value), "working_memory": wm.payload}
    # 机制层追加字段不参与节点业务事实指纹（与 human_interventions/approved_experiences 同一规则）
    assert (R.prepare(node, sealed_input)["review_context_sha256"]
            == value["review_assignment"]["review_context_sha256"])
    accepted = review_response(node, value)
    attempt = AM.Attempt(ctx, node, {"input": sealed_input})
    attempt.finish("validated", payload={"data": accepted},
                   validation={"ok": True, "accepted": accepted})
    state = {"data": copy.deepcopy(accepted), **attempt.refs()}
    if node == "N11":
        state["rework_requests"] = copy.deepcopy(accepted["rework_requests"])
        rebuilt = R.for_author(ctx, author, {}, state)
    else:
        rebuilt = R.for_author(ctx, author, state, {})
    assert rebuilt["issues"], "复核包必须能重建出问题身份"
    assert {item["issue_id"] for item in rebuilt["issues"]} >= {
        item["issue_id"] for item in accepted["issue_reviews"]}
