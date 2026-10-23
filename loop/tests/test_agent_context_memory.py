"""C1/M1/M2：受控 provider 的请求与落盘行为，独立于内网环境。"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.chunks import model_steps as M
from workflows.chunks import n6_facts as N6
from workflows.context import RunCtx


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


class Data:
    def __init__(self, ctx, state=None, root=None):
        self.state = state or {}
        self.resources = {"loop_ctx": ctx, "repo_root": root or ctx.run_dir / "source"}
        self.emitted = []

    def get_state(self, key):
        return self.state.get(key)

    def require_resource(self, key):
        return self.resources[key]

    async def async_set_state(self, key, value):
        self.state[key] = value

    async def async_emit(self, key, value):
        self.emitted.append(key)


# ---------------------------------------------------------------- N6 合法输出夹具（P-25 方案 A）
#
# 背景：`n6_author` 现在对模型输出做 fail-closed 校验（每个目标用例至少一条观测点、
# marker 唯一、必须出现在同用例 `edits[].new` 里，且 marker 的期望必须能从**本 run** 的
# 文档条目快照解析出来 —— R3-01）。下面这些 characterization 用例检验的是
# **上下文刷新/远端修订点是否进入请求**，所以只把 provider 响应换成合法形状，
# **不放宽任何断言**。

#: 观测点 marker：必须是 UVM_INFO 的 **ID**，且含文档条目名（`fpga_date`）才能解析到期望。
#: （`fpga_date` 条目由下面 `ctx` 夹具写进 run 级 `doc_entries.jsonl`。）
N6_MARKER = "N6_FPGA_DATE"


def n6_new_text(marker: str = N6_MARKER) -> str:
    """一条合法的观测点打印（marker 是 UVM_INFO 的 ID；打印实际读回值；值带 `0x`）。"""
    return ('uvm_info("' + marker + '", $sformatf("OK 0x0000+0x04 fpga_date = 0x%08h", '
            'actual), UVM_LOW);')


def n6_observation_point(case: str, marker: str = N6_MARKER) -> dict:
    return {"case": case, "marker": marker, "addr": "0x0000", "offset": "0x04",
            "expected_value": "0x20260708", "basis": "doc_bitdef bits=31:0"}


def n6_response(case: str, *, old: str, line: int = 1,
                rework_resolution: list[str] | None = None) -> dict:
    """合法 N6 输出：revisions 覆盖 case、edits[].new 含同用例 marker、observation_points 对齐。"""
    return {"revisions": [{"case": case, "rationale": "按 doc_bitdef 修订并加观测点",
                           "edits": [{"line": line, "old": old, "new": n6_new_text(),
                                      "basis": "doc_bitdef bits=31:0"}]}],
            "observation_points": [n6_observation_point(case)],
            "rework_resolution": list(rework_resolution or []), "notes": []}


@pytest.fixture
def ctx(tmp_path):
    root = tmp_path / "workspace"
    run = root / "runs" / "RUN-20300101-010101"
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    # R3-01：N6 观测点 marker 的期望必须能从**本 run** 的文档条目快照解析出来
    # （`host.evidence.resolve_expected_imprint(marker, run_dir=…)`）；解析不到 ⇒ fail-closed。
    # 这里给 run 级快照一条 `fpga_date`，让 `N6_FPGA_DATE` 可解析（不靠跨 run 猜测）。
    (run / "doc_entries.jsonl").write_text(
        json.dumps({"entry_id": "0x0000#0x0004", "name": "fpga_date",
                    "segment": "0x0000", "offset_global": "0x0004",
                    "reset": "2026_0708"}, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return RunCtx(run.name, run, "real", "happy", KbSources.from_workspace(root),
                  ProgressLog(tmp_path / "events", run.name))


@pytest.fixture
def provider(monkeypatch):
    from agently import Agently
    cfg = SimpleNamespace(available=True, model="test-model", plugin="test-plugin",
                          reason=None, _api_key="never-record-this-secret")
    calls = {"inputs": [], "agents": [], "response": {"summary": "summary", "groups": [], "risky_points": []}}

    class Agent:
        def input(self, value):
            calls["inputs"].append(copy.deepcopy(value))
            return self

        def info(self, value):
            calls["info"] = value
            return self

        def instruct(self, value):
            calls["instruct"] = value
            return self

        def output(self, schema, **_):
            calls["schema"] = schema
            return self

        async def async_get_data(self):
            if "error" in calls:
                raise calls["error"]
            if "wait" in calls:
                calls["entered"].set()
                await calls["wait"].wait()
            return copy.deepcopy(calls["response"])

    def create():
        agent = Agent()
        calls["agents"].append(agent)
        return agent

    monkeypatch.setattr(M.MP, "resolve", lambda: cfg)
    monkeypatch.setattr(M.MP, "configure_agently", lambda: cfg)
    monkeypatch.setattr(Agently, "create_agent", create)
    calls["cfg"] = cfg
    return calls


async def call(ctx, **changes):
    args = {"prompt_key": "n3_digest", "input_data": {"run_id": ctx.run_id, "diffs": []},
            "offered": {"diff_ids": set(), "segments": set()}}
    args.update(changes)
    return await M.run_model_node(ctx, "N3", **args)


async def test_characterization_fresh_agent_and_existing_output_validation(ctx, provider):
    first = await call(ctx)
    second = await call(ctx)
    assert provider["agents"][0] is not provider["agents"][1]
    assert first["data"] == second["data"] == {"summary": "summary", "groups": [], "risky_points": []}
    assert first["validation"]["ok"] is True
    provider["response"]["summary"] = ""
    bad = await call(ctx)
    assert bad["validation"]["ok"] is False


async def test_characterization_small_n3_keeps_order_and_artifact(ctx, provider):
    diffs = [{"entry_id": "a", "segment": "s", "before": "old", "after": "new"},
             {"entry_id": "b", "segment": "s", "before": "old2", "after": "new2"}]
    write_json(ctx.run_dir / "n2_diff.json", {"diffs": diffs})
    await M.n3_digest(Data(ctx))
    assert [d["entry_id"] for d in provider["inputs"][0]["diffs"]] == ["a", "b"]
    assert (ctx.run_dir / "n3_digest.md").is_file()


async def test_characterization_small_n8_reads_code_and_emits_pass(ctx, provider):
    ctx.mode = "drill"
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    lib.mkdir(parents=True)
    (lib / "demo.sv").write_text("module demo;\nendmodule\n")
    provider["response"] = {"verdict": "pass", "findings": [], "must_fix": []}
    data = Data(ctx)
    await M.n8_check(data)
    assert provider["inputs"][0]["sandbox_cases"][0]["excerpt"] == "module demo;\nendmodule\n"
    assert data.emitted == ["N8_PASS"]


async def test_n8_closure_fails_before_any_model_call(ctx, provider):
    """F16-c：闭锁必须发生在模型调用之前（不创建 agent、不产生请求）。"""
    ctx.mode = "drill"
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    lib.mkdir(parents=True)
    data = Data(ctx)
    with pytest.raises(RuntimeError, match="沙盒|可复核"):
        await M.n8_check(data)
    assert provider["agents"] == []
    assert provider["inputs"] == []
    assert data.emitted == []


async def test_n8_full_request_stays_within_context_budget(ctx, provider, monkeypatch):
    """F16-c：真实 N8 请求（触发分片）的整请求大小由 check_budget 实测且 ≤ 上限。"""
    ctx.mode = "drill"
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    src = ctx.run_dir / "source" / "TESTLIB"
    lib.mkdir(parents=True)
    src.mkdir(parents=True)
    for index in range(20):
        body = [f"// case {index} line {line} " + "x" * 60 for line in range(50)]
        changed = list(body)
        changed[25] = f"// UPDATED case {index} " + "y" * 60
        (src / f"tc_{index:02d}.sv").write_text("\n".join(body) + "\n", encoding="utf-8")
        (lib / f"tc_{index:02d}.sv").write_text("\n".join(changed) + "\n", encoding="utf-8")
    sizes: list[int] = []
    real = M.AM.check_budget

    def spy(input_data, contract):
        size = real(input_data, contract)
        sizes.append(size)
        return size

    monkeypatch.setattr(M.AM, "check_budget", spy)
    provider["response"] = {"verdict": "pass", "findings": [], "must_fix": []}
    await M.n8_check(Data(ctx))
    assert sizes, "N8 请求必须经过 check_budget 守门"
    assert max(sizes) <= M.AM.MAX_CONTEXT_BYTES, sizes
    summary = provider["inputs"][0]["coverage_summary"]
    assert summary["used_bytes"] <= M.N8_SANDBOX_BUDGET_BYTES
    assert summary["region_files"] >= 1, "大输入应触发分片（否则断言没有覆盖 F16 场景）"


async def test_characterization_author_receives_last_rework(ctx, provider, monkeypatch):
    monkeypatch.setattr(M, "build_n6_targets", lambda *args: [{"case": "demo", "excerpt": {"text": "old"}}])
    provider["response"] = n6_response("demo", old="old", rework_resolution=["fixed"])
    await M.n6_author(Data(ctx, {"n8_check": {"data": {"must_fix": ["fix mask"]}},
                               "n11_review": {"rework_requests": [{"case": "demo", "what": "check evidence", "basis": "md5"}]}}))
    reasons = provider["inputs"][0]["rework_reasons"]
    assert "fix mask" in reasons and any("check evidence" in reason for reason in reasons)


async def test_n3_all_diffs_and_full_values_are_sent(ctx, provider):
    diffs = [{"entry_id": str(i), "segment": "s", "before": "x" * 210 + "TAIL", "after": "y" * 210 + "END"}
             for i in range(45)]
    write_json(ctx.run_dir / "n2_diff.json", {"diffs": diffs})
    await M.n3_digest(Data(ctx))
    offered = provider["inputs"][0]["diffs"]
    assert [d["entry_id"] for d in offered] == [str(i) for i in range(45)]
    assert offered[-1]["before"].endswith("TAIL") and offered[-1]["after"].endswith("END")


async def test_author_sees_distant_revision_points_in_same_case(ctx, provider, monkeypatch):
    root = ctx.run_dir / "source"
    (root / "TESTLIB").mkdir(parents=True)
    (root / "TESTLIB" / "demo.sv").write_text("\n".join(f"unique_line_{i}" for i in range(1, 201)))
    write_json(ctx.run_dir / "n5_impact.json", {"must_change": [
        {"case": "demo", "file": "TESTLIB/demo.sv", "line": line,
         "entry_id": f"entry-{line}", "segment": "s", "offset": str(line)} for line in (3, 190)]})
    write_json(ctx.run_dir / "n2_diff.json", {"diffs": []})
    monkeypatch.setattr(N6, "_doc_bitdef_for", lambda *args: {"bits": "31:0"})
    provider["response"] = n6_response("demo", old="unique_line_3", line=3)
    await M.n6_author(Data(ctx, root=root))
    target = provider["inputs"][0]["targets"][0]
    assert len(target["excerpts"]) == 2
    assert [item["line"] for item in target["excerpts"]] == [3, 190]
    assert "unique_line_190" in target["excerpts"][1]["text"]


def test_all_resolved_apis_include_complete_large_definition(tmp_path):
    root = tmp_path / "env"
    (root / "TB").mkdir(parents=True)
    for i in range(4):
        body = "\n".join(f"// body {n}" for n in range(140))
        (root / "TB" / f"api_{i}.sv").write_text(f"task api_{i}(input int data);\n{body}\nTAIL_RULE_{i};\nendtask\n")
    result = M._api_semantics_for(root, "\n".join(f"api_{i}(1);" for i in range(4)), 2)
    assert len(result) == 4
    assert all(f"TAIL_RULE_{i}" in result[i]["body"] for i in range(4))
    assert all(item["complete"] for item in result)


@pytest.mark.parametrize("initially_missing", [False, True])
async def test_author_api_facts_refresh_between_calls(ctx, provider, monkeypatch, initially_missing):
    root = ctx.run_dir / "source"
    (root / "TESTLIB").mkdir(parents=True)
    (root / "TB").mkdir()
    (root / "TESTLIB" / "demo.sv").write_text("api_demo(1);\n")
    api = root / "TB" / "api.sv"
    if not initially_missing:
        api.write_text("task api_demo(input int data);\nOLD_RULE;\nendtask\n")
    write_json(ctx.run_dir / "n5_impact.json", {"must_change": [
        {"case": "demo", "file": "TESTLIB/demo.sv", "line": 1,
         "entry_id": "entry", "segment": "s", "offset": "1"}]})
    write_json(ctx.run_dir / "n2_diff.json", {"diffs": []})
    monkeypatch.setattr(N6, "_doc_bitdef_for", lambda *args: {"bits": "31:0"})
    provider["response"] = n6_response("demo", old="api_demo(1);", line=1)
    await M.n6_author(Data(ctx, root=root))
    api.write_text("task api_demo(input int data);\nNEW_RULE;\nendtask\n")
    await M.n6_author(Data(ctx, root=root))
    apis = provider["inputs"][-1]["targets"][0]["api_semantics"]
    assert len(apis) == 1 and "NEW_RULE" in apis[0]["body"]


@pytest.mark.parametrize("delete", [False, True])
async def test_n8_large_tail_changes_and_deletions_have_before_after(ctx, provider, delete):
    ctx.mode = "drill"
    root = ctx.run_dir / "source"
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    (root / "TESTLIB").mkdir(parents=True)
    lib.mkdir(parents=True)
    before = "\n".join(f"// filler {i}" for i in range(800)) + "\nassert(OLD_VALUE);\n"
    after = before.replace("assert(OLD_VALUE);", "" if delete else "assert(NEW_VALUE);")
    (root / "TESTLIB" / "demo.sv").write_text(before)
    (lib / "demo.sv").write_text(after)
    provider["response"] = {"verdict": "pass", "findings": [], "must_fix": []}
    await M.n8_check(Data(ctx, root=root))
    case = provider["inputs"][0]["sandbox_cases"][0]
    assert case["coverage"]["complete"] is True
    assert case["coverage"]["mode"] == "changed_regions"
    assert "assert(OLD_VALUE)" in json.dumps(case["changed_regions"])
    if not delete:
        assert "assert(NEW_VALUE)" in case["excerpt"]


async def test_large_n8_without_source_fails_before_provider(ctx, provider):
    lib = ctx.run_dir / "sandbox" / "TESTLIB"
    lib.mkdir(parents=True)
    (lib / "demo.sv").write_text("x" * 7000)
    with pytest.raises(RuntimeError, match="上下文|context"):
        await M.n8_check(Data(ctx))
    assert not provider["inputs"]


async def test_context_budget_rejects_without_truncation_or_provider(ctx, provider, monkeypatch):
    from host import agent_memory as AM
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES", 100)
    with pytest.raises(RuntimeError, match="budget|预算"):
        await call(ctx, input_data={"run_id": ctx.run_id, "diffs": ["x" * 500]})
    assert not provider["inputs"]
    record = AM.verify_attempt(next((ctx.run_dir / "agent_calls" / "N3").iterdir()))
    assert record["result"]["status"] == "error"


@pytest.mark.parametrize("source", [None, "{", '{"diffs":{}}', '{"diffs":[1]}'])
async def test_n3_missing_or_invalid_context_fails_before_provider(ctx, provider, source):
    if source is not None:
        (ctx.run_dir / "n2_diff.json").write_text(source)
    with pytest.raises(RuntimeError, match="上下文"):
        await M.n3_digest(Data(ctx))
    assert not provider["inputs"]


async def test_trace_preserves_requests_results_and_reserves_new_attempt(ctx, provider):
    from host import agent_memory as AM
    a = await call(ctx)
    first_bytes = {p.name: p.read_bytes() for p in (ctx.run_dir / a["request_ref"]).parent.iterdir()}
    b = await call(ctx)  # 新调用不能复用上次文件；序号不依赖 cycle 或内存计数
    assert a["request_ref"] != b["request_ref"]
    first = AM.verify_attempt((ctx.run_dir / a["request_ref"]).parent)
    assert first["request"]["input"] == provider["inputs"][0]
    assert first["result"]["status"] == "validated"
    assert first["result"]["payload"]["data"] == provider["response"]
    assert all(p.read_bytes() == first_bytes[p.name] for p in (ctx.run_dir / a["request_ref"]).parent.iterdir())
    assert "never-record-this-secret" not in json.dumps(first)
    assert first["request"]["schema"]["properties"]["summary"]
    assert first["request"]["offered"]["diff_ids"] == []


async def test_new_process_reserves_attempt_without_reusing_previous_files(ctx, provider):
    a = await call(ctx)
    script = """import sys
from pathlib import Path
from types import SimpleNamespace
from host.agent_memory import Attempt
path=Path(sys.argv[1]); attempt=Attempt(SimpleNamespace(run_dir=path,run_id=path.name), 'N3', {})
attempt.finish('standin'); print(attempt.path.name)
"""
    result = subprocess.run([sys.executable, "-c", script, str(ctx.run_dir)], cwd=M.P.LOOP_DIR,
                            capture_output=True, text=True, check=True)
    b = await call(ctx)
    assert result.stdout.strip() not in (Path(a["request_ref"]).parent.name, Path(b["request_ref"]).parent.name)


async def test_result_write_failure_does_not_return_model_output(ctx, provider, monkeypatch):
    from host import agent_memory as AM
    original = AM._write_once

    def refuse(path, content):
        if path.name == "result.json":
            raise OSError("result storage failed")
        original(path, content)

    monkeypatch.setattr(AM, "_write_once", refuse)
    with pytest.raises(OSError, match="result storage failed"):
        await call(ctx)
    assert len(provider["inputs"]) == 1
    attempt = next((ctx.run_dir / "agent_calls" / "N3").iterdir())
    with pytest.raises(ValueError, match="incomplete"):
        AM.verify_attempt(attempt)


@pytest.mark.parametrize("failure", ["validation", "exception", "standin"])
async def test_trace_failure_and_standin_are_not_validated(ctx, provider, failure):
    from host import agent_memory as AM
    if failure == "validation":
        provider["response"]["summary"] = ""
    elif failure == "exception":
        provider["error"] = RuntimeError("provider failed never-record-this-secret")
    else:
        provider["cfg"].available = False
    out = await call(ctx)
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    assert record["result"]["status"] == ("standin" if failure == "standin" else "validation_failed")
    assert "never-record-this-secret" not in json.dumps(record)


@pytest.mark.parametrize("node,prompt,response,offered", [
    ("N10", "n10_fail_classify", {"items": [], "summary": "none", "unclassified": []}, {"buckets": []}),
    ("N11", "n11_review", {"chain": "intact", "reasons": ["identity checked"], "rework_requests": [], "caveats": []}, {}),
    ("N12", "n12_report", {"title": "report", "sections": [], "counts_quoted": {},
                          "claimed_verdict": "undetermined", "open_items": []}, {"counts": {}, "verdict": {}}),
])
async def test_other_semantic_nodes_keep_validation_and_record_references(ctx, provider, node, prompt, response, offered):
    from host import agent_memory as AM
    provider["response"] = response
    out = await M.run_model_node(ctx, node, prompt_key=prompt, input_data={"run_id": ctx.run_id}, offered=offered)
    assert out["validation"]["ok"] is True
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    assert record["request"]["node"] == node and record["result"]["status"] == "validated"


async def test_verify_cli_checks_integrity_without_printing_input(ctx, provider):
    out = await call(ctx, input_data={"run_id": ctx.run_id, "private_source": "do-not-print-source"})
    path = (ctx.run_dir / out["request_ref"]).parent
    args = [sys.executable, "-m", "host.agent_memory", "--verify", str(path)]
    result = subprocess.run(args, cwd=M.P.LOOP_DIR, capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["ok"] is True
    assert "do-not-print-source" not in result.stdout
    request = path / "request.json"
    assert request.stat().st_mode & 0o222 == 0
    request.chmod(0o600); request.write_text("{}")
    invalid = subprocess.run(args, cwd=M.P.LOOP_DIR, capture_output=True, text=True)
    assert invalid.returncode == 1 and json.loads(invalid.stdout)["ok"] is False


async def test_cancelled_call_is_recorded_as_interrupted(ctx, provider):
    from host import agent_memory as AM
    provider["wait"] = asyncio.Event()
    provider["entered"] = asyncio.Event()
    task = asyncio.create_task(call(ctx))
    await asyncio.wait_for(provider["entered"].wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    attempt = next((ctx.run_dir / "agent_calls" / "N3").iterdir())
    assert AM.verify_attempt(attempt)["result"]["status"] == "interrupted"


async def test_audit_write_failure_prevents_model_call(ctx, provider):
    (ctx.run_dir / "agent_calls").write_text("blocked")
    with pytest.raises(OSError):
        await call(ctx)
    assert not provider["inputs"]


async def test_configuration_error_does_not_store_authentication_value(ctx, provider, monkeypatch):
    from host import agent_memory as AM

    def broken_configuration():
        raise RuntimeError("transport setup failed: never-record-this-secret")

    monkeypatch.setattr(M.MP, "configure_agently", broken_configuration)
    with pytest.raises(RuntimeError):
        await call(ctx)
    attempt = next((ctx.run_dir / "agent_calls" / "N3").iterdir())
    record = AM.verify_attempt(attempt)
    assert record["result"]["status"] == "error"
    assert "never-record-this-secret" not in json.dumps(record)


async def test_tampered_and_incomplete_records_are_rejected(ctx, provider):
    from host import agent_memory as AM
    out = await call(ctx)
    path = ctx.run_dir / out["request_ref"]
    path.chmod(0o600)
    path.write_text("{}")
    with pytest.raises(ValueError, match="checksum|指纹"):
        AM.verify_attempt(path.parent)
    incomplete = ctx.run_dir / "incomplete"
    incomplete.mkdir()
    with pytest.raises(ValueError, match="incomplete|不完整"):
        AM.verify_attempt(incomplete)


async def approved_catalog(ctx, provider):
    from host import agent_memory as AM
    out = await call(ctx)
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    source = ctx.kb.root / "runs" / "historical" / "note.md"
    source.parent.mkdir(parents=True)
    source.write_text("human checked evidence")
    item = {"id": "lesson-1", "status": "approved", "approved_by": "human:reviewer",
            "scope": record["request"]["scope"], "source": {"path": "runs/historical/note.md",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}, "advice": "Check the mask against the current RTL."}
    catalog = ctx.kb.root / "adjudication" / "agent_experiences.json"
    write_json(catalog, {"version": 1, "items": [item]})
    return catalog, item, source


async def test_only_approved_matching_experience_is_consumed_and_never_written(ctx, provider):
    catalog, _, _ = await approved_catalog(ctx, provider)
    before = catalog.read_bytes()
    run_id = "RUN-20300101-010102"
    run_dir = ctx.kb.root / "runs" / run_id
    write_json(run_dir / "view.json", {"baseline": "v0"})
    next_ctx = RunCtx(run_id, run_dir, "real", "happy", ctx.kb, ProgressLog(ctx.progress.dir, run_id))
    out = await call(next_ctx)
    assert provider["inputs"][-1]["approved_experiences"][0]["id"] == "lesson-1"
    assert "当前事实" in provider["info"]
    assert catalog.read_bytes() == before
    assert out["experience_diagnostics"] == []


@pytest.mark.parametrize("reason", ["unapproved", "prompt", "schema", "env", "baseline", "unknown_baseline", "facts", "source", "escape", "symlink", "duplicate", "too_many", "advice_size", "catalog_version"])
async def test_inapplicable_experiences_are_excluded_with_diagnostics(ctx, provider, reason, tmp_path):
    catalog, item, source = await approved_catalog(ctx, provider)
    entries = [item]
    if reason == "unapproved": item["approved_by"] = "model:author"
    elif reason == "prompt": item["scope"]["prompt_sha256"] = "old"
    elif reason == "schema": item["scope"]["schema_sha256"] = "old"
    elif reason == "env": item["scope"]["env_id"] = "other-env"
    elif reason == "baseline": write_json(ctx.run_dir / "view.json", {"baseline": "v1"})
    elif reason == "unknown_baseline": (ctx.run_dir / "view.json").unlink()
    elif reason == "facts": item["scope"]["facts_sha256"] = "changed"
    elif reason == "source": source.write_text("changed")
    elif reason == "escape": item["source"]["path"] = "../secret.txt"
    elif reason == "symlink":
        outside = tmp_path / "outside.txt"; outside.write_bytes(source.read_bytes())
        source.unlink(); source.symlink_to(outside)
    elif reason == "duplicate": entries.append(copy.deepcopy(item))
    elif reason == "too_many": entries = [dict(item, id=f"lesson-{i}") for i in range(11)]
    elif reason == "advice_size": item["advice"] = "x" * 4001
    write_json(catalog, {"version": 0 if reason == "catalog_version" else 1, "items": entries})
    out = await call(ctx)
    assert not provider["inputs"][-1].get("approved_experiences")
    assert out["experience_diagnostics"]
