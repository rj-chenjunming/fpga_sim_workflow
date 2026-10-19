"""验收 A9 / A10：进度流投影白名单、冻结见证、六项信任缺口判定。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from host import paths as P
from host.progress import ALLOWED_KINDS, ProgressLog
from services.contracts import KbSources, compute_blockers


# --------------------------------------------------------------- A9

def test_progress_rejects_unknown_kind(tmp_path: Path) -> None:
    """A9：非白名单 kind 一律拒绝写入（宁可报错，不要产生不可解释的事件）。"""
    log = ProgressLog(tmp_path, "RUN-TEST")
    log.append("node_started", node="N0")
    with pytest.raises(ValueError, match="白名单"):
        log.append("token_stream_delta", node="N3")


def test_progress_rejects_parser_internal_refs(tmp_path: Path) -> None:
    """不得把 raw parser 路径当日志协议暴露给前端。"""
    log = ProgressLog(tmp_path, "RUN-TEST")
    with pytest.raises(ValueError, match="解析器内部路径"):
        log.append("node_finished", node="N3", refs=["events/parser/delta_path.json"])


def test_run_view_events_are_whitelisted_only(tmp_path: Path) -> None:
    """真实写入的事件流里只允许出现白名单 kind。"""
    log = ProgressLog(tmp_path, "RUN-WHITELIST")
    for kind in ("run_started", "node_started", "node_finished", "gate_pending", "gate_decided"):
        log.append(kind, node="N2")
    events = log.read()
    assert events and {e["kind"] for e in events} <= ALLOWED_KINDS
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))


# --------------------------------------------------------------- 六项缺口判定

def test_conflicts_are_uncleared_and_block_release() -> None:
    """I4：冲突清单未清零 ⇒ 阻断发版/晋升。数字由实际文件数出来。"""
    kb = KbSources.from_workspace(P.WORKSPACE_ROOT)
    summary = kb.load_conflicts()
    items = summary["items"]
    assert len(items) > 0
    blocking = [i for i in items if i.get("blocks_release")]
    assert len(blocking) > 0, "夹具/索引应存在 blocks_release=true 的冲突"

    blockers = compute_blockers(run_dir=None, counts=None, kb=kb, slot_status=None, job=None)
    codes = {b["code"] for b in blockers}
    assert "I4_CONFLICTS_UNCLEARED" in codes
    assert "I3_EVIDENCE_MISSING" in codes


def test_koutou2_zero_alone_does_not_green_light() -> None:
    """核心红线：口径二为 0 而口径一非 0 时，必须仍是 blocker。"""
    kb = KbSources.from_workspace(P.WORKSPACE_ROOT)
    counts = {
        "koutou1": {"value": 1687, "zero": False, "refs": ["line 359: ..."]},
        "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}, "zero": True, "refs": []},
        "both_zero": False,
    }
    blockers = compute_blockers(run_dir=None, counts=counts, kb=kb, slot_status=None, job=None)
    codes = {b["code"] for b in blockers}
    assert "I3_KOUTOU1_NONZERO" in codes
    assert not any(b["code"] == "I3_KOUTOU2_NONZERO" for b in blockers)


def test_capacity_notice_is_info_not_blocker() -> None:
    kb = KbSources.from_workspace(P.WORKSPACE_ROOT)
    job = {"job_id": "JOB-1", "phase": "running", "eta_human": "5.0 min", "log_path": "x.log"}
    blockers = compute_blockers(run_dir=None, counts=None, kb=kb, slot_status=None, job=job)
    cap = [b for b in blockers if b["code"] == "CAPACITY_LONG_TASK"]
    assert cap and cap[0]["severity"] == "info"


# --------------------------------------------------------------- A10

def _witness(paths_md5_files: list[Path]) -> list[str]:
    """内容 md5 清单（`doc/AGENTS.md` §4.3 禁止只按 mtime 判未改动）。"""
    lines = []
    for path in sorted(paths_md5_files):
        digest = hashlib.md5()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  {path.relative_to(P.REPO_ROOT)}")
    return lines


def _frozen_files() -> list[Path]:
    return (
        sorted(p for p in (P.REPO_ROOT / "TESTLIB").glob("*.sv"))
        + sorted(p for p in (P.KB_BASELINES / "v0").rglob("*") if p.is_file())
        + [P.REPO_ROOT / "doc" / "AGENTS.md", P.KB_DIR / "tools" / "gate.py"]
    )


def test_frozen_witness_before_after_drill_run() -> None:
    """A10：一次完整 drill 运行不得改动任何冻结件。"""
    import asyncio

    from workflows.main_flow import RunManager

    before = _witness(_frozen_files())
    rtl_before = sorted(p.name for p in (P.REPO_ROOT / "RTL").rglob("*") if p.is_file())[:2000]

    async def drive() -> None:
        m = RunManager()
        rid = await m.start(baseline="v0", mode="drill")
        try:
            ex = m.executions[rid]
            for _ in range(100):
                if ex.is_waiting():
                    break
                await asyncio.sleep(0.1)
            await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor="human:witness",
                       reason="已逐条核对差异")
            for _ in range(150):
                view = m.run_view(rid)
                if ((view.get("pending_interrupt") or {}).get("id") or "").startswith("G2"):
                    break
                await asyncio.sleep(0.2)
        finally:
            await m.stop_watching()

    asyncio.run(drive())

    after = _witness(_frozen_files())
    modified = sorted(set(before) - set(after))
    deleted = [line for line in before if line.split("  ", 1)[1] not in {x.split("  ", 1)[1] for x in after}]
    assert modified == [], f"冻结件被改动：{modified}"
    assert deleted == [], f"冻结件被删除：{deleted}"
    assert sorted(p.name for p in (P.REPO_ROOT / "RTL").rglob("*") if p.is_file())[:2000] == rtl_before


def test_frozen_path_guard_covers_expected_prefixes() -> None:
    """冻结守卫本身要能判对，否则 A10 的见证是空的。"""
    for rel in ("RTL/a.v", "TB/b.sv", "PKG/c.sv", "TESTLIB/tc_a.sv", "doc/AGENTS.md",
                "kb/baselines/v0/manifest.json", "kb/tools/gate.py", "kb/index/regmap.json"):
        assert P.is_frozen_path(P.REPO_ROOT / rel) is True, rel
    for rel in ("loop/web/index.html", "loop/tests/test_flow.py", "kb/runs/RUN-X/n2_diff.json"):
        assert P.is_frozen_path(P.REPO_ROOT / rel) is False, rel


# --------------------------------------------------------------- 权威枚举不漂移

def test_gate_branch_events_match_authority() -> None:
    """本层的事件表必须与 `kb_lib.GATE_DECISIONS` 逐值一致。

    实测踩坑：本层曾自造 `full_regression`（权威是 `full_now`），
    用户于是点到一个**权威不认**的决策，收到 argparse 用法错误而不是业务拒绝。
    """
    from host import gate_authority as GA
    from workflows.chunks.gates import BRANCH_DRIFT, validate_branches

    assert validate_branches() == {}, f"拓扑落后于权威：{validate_branches()}"
    assert BRANCH_DRIFT == {}
    for gate in GA.gate_ids():
        assert set(GA.actionable_decisions(gate)) <= set(GA.decisions()[gate])


def test_run_view_exposes_authoritative_gate_options() -> None:
    """界面按钮必须由服务端下发，来源是权威。"""
    from host import gate_authority as GA
    from services.contracts import _gate_options

    options = _gate_options()
    assert set(options) == set(GA.gate_ids())
    for gate, opts in options.items():
        values = [o["value"] for o in opts]
        assert values == list(GA.actionable_decisions(gate)), gate
        assert "pending" not in values, "pending 是状态，不是可提交动作"


def test_kb_lib_import_does_not_write_bytecode_into_frozen_dir() -> None:
    """导入闸门权威**不得**在冻结目录 `kb/tools/` 里写字节码。

    实测发生过：`import kb_lib` 会生成 `kb/tools/__pycache__/kb_lib.cpython-311.pyc`。
    它不改源文件，但确实往冻结路径写了东西 —— 与冻结守卫矛盾。
    """
    import sys

    from host import gate_authority as GA

    pyc = P.KB_TOOLS / "__pycache__" / f"kb_lib.cpython-{sys.version_info.major}{sys.version_info.minor}.pyc"
    had = pyc.exists()
    if had:
        pyc.unlink()
    try:
        sys.modules.pop("kb_lib", None)
        GA._kb_lib.cache_clear()
        GA._kb_lib()
        assert not pyc.exists(), f"导入 kb_lib 往冻结目录写了字节码：{pyc}"
    finally:
        sys.modules.pop("kb_lib", None)
        GA._kb_lib.cache_clear()
        GA._kb_lib()


def test_authority_restores_bytecode_flag() -> None:
    """导入权威不得把 `sys.dont_write_bytecode` 留在改动状态。"""
    import sys

    from host import gate_authority as GA

    before = sys.dont_write_bytecode
    GA._kb_lib.cache_clear()
    GA._kb_lib()
    assert sys.dont_write_bytecode == before


# --------------------------------------------------------------- prompt 契约

def test_prompt_contract_file_parses_and_is_complete() -> None:
    """`prompts/loop_nodes.yaml` 必须可解析，且五个节点都有 info/instruct/output。

    这条测试是被一次真事故催生的：YAML 里一个未转义的内层双引号
    （`"不得把"跑通"当结论"`）让整份文件解析失败，N3 之前的节点全部报错，
    而错误只在运行时以 `ParserError` 露出。
    """
    from workflows.chunks.model_steps import load_prompts

    prompts = load_prompts()
    expected = {"n3_digest", "n6_author", "n8_check", "n11_review", "n12_report"}
    assert expected <= set(prompts), f"缺节点契约：{expected - set(prompts)}"
    from prompts.node_schemas import SCHEMAS

    for key in expected:
        spec = prompts[key]
        assert spec.get("info"), f"{key} 缺 info"
        assert spec.get("instruct"), f"{key} 缺 instruct"
        # 输出**形状**归代码所有（Pydantic），不放在 YAML 里
        assert key.split("_", 1)[0] in SCHEMAS, f"{key} 没有输出契约"


def test_offline_mode_forces_standin_not_fake_model() -> None:
    """`LOOP_LLM_MODE=standin` 必须报"不可用"，不得静默假装有模型。"""
    import os

    from host import model_provider as MP

    prev = os.environ.get("LOOP_LLM_MODE")
    os.environ["LOOP_LLM_MODE"] = "standin"
    try:
        cfg = MP.resolve()
        assert cfg.available is False
        assert "standin" in (cfg.reason or "")
        assert cfg.public()["has_api_key"] is False
    finally:
        if prev is None:
            os.environ.pop("LOOP_LLM_MODE", None)
        else:
            os.environ["LOOP_LLM_MODE"] = prev


def test_provider_public_projection_never_leaks_key() -> None:
    """`status()` 对外投影不得含密钥字段或密钥值。"""
    from host import model_provider as MP

    pub = MP.resolve().public()
    assert "_api_key" not in pub
    assert "api_key" not in pub or pub.get("api_key") is None
    for value in pub.values():
        if isinstance(value, str):
            assert not value.startswith("sk-"), "对外投影泄露了形如 sk- 的密钥"


# --------------------------------------------------------------- Host 校验必须真的会拦

def test_host_validation_actually_fires() -> None:
    """模型输出的确定性校验必须在**违规时报警**。

    这条测试来自一次静默失效：`_validate` 的分支比对 `"n12"`，而调用方传的是
    `"n12_report"` ⇒ 五个节点的校验一条都没跑、`problems` 恒为空。
    "没问题"和"没检查"在结果上看起来完全一样，所以必须有反面用例。
    """
    from workflows.chunks.model_steps import _validate

    # 未知 kind：不得判通过
    bad = _validate("n12_report", {"data": {"title": "x"}}, offered={})
    assert bad["ok"] is False and "未知校验 kind" in bad["problems"][0]

    # N12：报告引用的数字与 Host 权威值不一致
    r = _validate(
        "n12",
        {"data": {"title": "t", "counts_quoted": {"koutou1": 999, "koutou2": {"UVM_ERROR": 0}},
                  "claimed_verdict": "not_passed"}},
        offered={"counts": {"koutou1": {"value": 1687}, "koutou2": {"value": {"UVM_ERROR": 0}}},
                 "verdict": {"passed": False}},
    )
    assert r["ok"] is False, r
    assert any("权威值不一致" in p for p in r["problems"]), r["problems"]
    assert r["accepted"]["counts_match_authority"] is False

    # N12：结构化结论与 Host 权威判决不一致（旧的「跑通」子串判据已删除）
    r = _validate(
        "n12",
        {"data": {"title": "t", "counts_quoted": {"koutou1": 1687}, "claimed_verdict": "passed"}},
        offered={"counts": {"koutou1": {"value": 1687}}, "verdict": {"passed": False}},
    )
    assert r["ok"] is False and any("claimed_verdict" in p for p in r["problems"]), r["problems"]

    # N8：verdict=rework 但 must_fix 为空 / fail 缺依据
    r = _validate("n8", {"data": {"verdict": "rework", "findings": [{"result": "fail", "basis": ""}],
                                  "must_fix": []}}, offered={})
    assert r["ok"] is False
    assert any("缺少 basis" in p for p in r["problems"])
    assert any("must_fix 为空" in p for p in r["problems"])

    # N8：非法 verdict
    assert _validate("n8", {"data": {"verdict": "maybe"}}, offered={})["ok"] is False

    # N11：guardian 判 broken 却未给返工请求（业务 N11 = 证据守护）
    r = _validate("n11", {"data": {"chain": "broken", "rework_requests": []}},
                  offered={"counts": {"koutou1": {"value": 1687, "zero": False}}})
    assert r["ok"] is False and any("rework_requests" in p for p in r["problems"])

    # N6：revisions 里出现未提供的用例（模型只出结构化 edits）
    r = _validate("n6", {"data": {"revisions": [{"case": "tc_not_offered",
                                                "edits": [{"line": 1, "old": "a", "new": "b", "basis": "x"}]}]}},
                  offered={"cases": {"tc_a"}})
    assert r["ok"] is False and any("不在目标用例中" in p for p in r["problems"])

    # N3：diff_ids 出现未提供的标识 / segment 越界
    r = _validate("n3", {"data": {"summary": "s",
                                 "groups": [{"segment": "0xFFFF", "diff_ids": ["X1"], "kind": "k"}]}},
                  offered={"diff_ids": {"E1"}, "segments": {"0x0000"}})
    assert r["ok"] is False and len(r["problems"]) >= 2, r["problems"]


def test_host_validation_accepts_conforming_output() -> None:
    """合规输出必须判通过（否则校验会变成"一律拒绝"）。"""
    from workflows.chunks.model_steps import _validate

    r = _validate(
        "n12",
        {"data": {"title": "报告", "counts_quoted": {"koutou1": 1687, "koutou2": {"UVM_ERROR": 0}},
                  "claimed_verdict": "not_passed", "sections": [{"heading": "h"}]}},
        offered={"counts": {"koutou1": {"value": 1687}, "koutou2": {"value": {"UVM_ERROR": 0}}},
                 "verdict": {"passed": False}},
    )
    assert r["ok"] is True, r["problems"]
    assert r["accepted"]["counts_match_authority"] is True

    r3 = _validate("n3", {"data": {"summary": "改了 2 条", "groups": [{"segment": "0x0000", "diff_ids": ["E1"],
                                                                    "kind": "reset"}],
                                  "risky_points": ["x"]}},
                   offered={"diff_ids": {"E1"}, "segments": {"0x0000"}})
    assert r3["ok"] is True, r3["problems"]
    assert r3["accepted"]["groups"][0]["diff_ids"] == ["E1"]


# --------------------------------------------------------------- N10 分桶与分类校验

def test_fail_buckets_lose_nothing() -> None:
    """分桶必须**零丢失**：地址数与条目数都要对得上，且逐项报出合并量。"""
    import json
    from host.evidence import fail_address_table, fail_buckets

    log = P.KB_RUNS / "RUN-20261015-120626" / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
    if not log.is_file():
        pytest.skip("夹具不存在")
    text = log.read_text(encoding="utf-8", errors="replace")
    n2 = json.loads((P.KB_RUNS / "RUN-20261015-120626" / "n2_diff.json").read_text(encoding="utf-8"))
    table = fail_address_table(text)
    fb = fail_buckets(text, n2.get("diffs", []))

    assert table["unmatched_lines"] == 0, "有含 *E 但不含 @ADDR[...] 的行必须显式报告"
    assert table["matched_entries"] == table["total_entries"]
    cov = fb["coverage"]
    assert cov["addresses_in_buckets"] == cov["distinct_addresses"], cov
    assert cov["entries_in_buckets"] == cov["total_entries"], cov
    assert fb["bucket_count"] <= 24
    assert fb["merged_note"] is not None  # 发生过合并就必须报告


def test_fail_buckets_revision_overlap_is_host_computed() -> None:
    """是否落在修订点上由 **Host** 算，不采信任何模型断言。"""
    import json
    from host.evidence import fail_buckets

    log = P.KB_RUNS / "RUN-20261015-120626" / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
    if not log.is_file():
        pytest.skip("夹具不存在")
    text = log.read_text(encoding="utf-8", errors="replace")
    n2 = json.loads((P.KB_RUNS / "RUN-20261015-120626" / "n2_diff.json").read_text(encoding="utf-8"))
    fb = fail_buckets(text, n2.get("diffs", []))
    # 夹具里修订点是 0x0000+0x4，失败地址从 0x84 起 ⇒ 不应有桶重叠
    assert fb["revision_points"], "修订点不应为空"
    assert fb["any_bucket_overlaps_revision_point"] is False
    assert all(b["overlaps_revision_point"] is False for b in fb["buckets"])


def test_n10_validator_catches_model_overreach() -> None:
    """N10 校验：覆盖性、枚举、依据、以及「本轮引入」的 Host 事实交叉核对。"""
    from workflows.chunks.model_steps import _validate

    buckets = [
        {"bucket_id": "B1", "channel": "RD", "range": "0x8000-0x80ff",
         "entry_count": 64, "address_count": 64, "sample_addresses": ["0x8000"],
         "overlaps_revision_point": False},
        {"bucket_id": "B2", "channel": "WR", "range": "0x0000-0x00ff",
         "entry_count": 4, "address_count": 2, "sample_addresses": ["0x0004"],
         "overlaps_revision_point": True},
    ]

    # ① 模型把不重叠的桶判成本轮引入 ⇒ 必须报冲突且不采信
    r = _validate("n10", {"data": {"items": [
        {"bucket_id": "B1", "classification": "本轮引入", "basis": "看起来像"},
        {"bucket_id": "B2", "classification": "本轮引入", "basis": "落在 0x0000+0x4"},
    ], "summary": "s", "unclassified": []}}, offered={"buckets": buckets})
    assert r["ok"] is False
    assert r["accepted"]["conflicts"] and r["accepted"]["conflicts"][0]["bucket_id"] == "B1"
    assert any("不得采信" in p for p in r["problems"])
    # Host 仍按桶的 entry_count 聚合（模型不逐地址说话）
    assert r["accepted"]["entries_by_classification"]["本轮引入"] == 68

    # ② 漏桶 / 重复 / 非法枚举 / 空依据
    r = _validate("n10", {"data": {"items": [
        {"bucket_id": "B1", "classification": "既有缺陷", "basis": "x"},
        {"bucket_id": "B1", "classification": "既有缺陷", "basis": "x"},
        {"bucket_id": "B9", "classification": "既有缺陷", "basis": "x"},
    ], "summary": "s", "unclassified": []}}, offered={"buckets": buckets})
    codes = " ".join(r["problems"])
    assert "不在提供的桶里" in codes and "重复出现" in codes and "未被分类" in codes

    r = _validate("n10", {"data": {"items": [
        {"bucket_id": "B1", "classification": "可能就是吧", "basis": ""},
        {"bucket_id": "B2", "classification": "既有缺陷", "basis": "ok"},
    ], "summary": "s", "unclassified": []}}, offered={"buckets": buckets})
    assert r["ok"] is False
    assert any("classification 非法" in p for p in r["problems"])
    assert any("缺 basis" in p for p in r["problems"])


def test_n10_validator_accepts_conforming_classification() -> None:
    from workflows.chunks.model_steps import _validate

    buckets = [{"bucket_id": "B1", "entry_count": 64, "address_count": 64,
                "sample_addresses": ["0x8000"], "overlaps_revision_point": False}]
    r = _validate("n10", {"data": {"items": [
        {"bucket_id": "B1", "classification": "既有缺陷", "basis": "通道 RD，修订点不在该范围"}
    ], "summary": "全部既有", "unclassified": []}}, offered={"buckets": buckets})
    assert r["ok"] is True, r["problems"]
    assert r["accepted"]["entries_by_classification"] == {"既有缺陷": 64}
    assert r["accepted"]["buckets_classified"] == 1
