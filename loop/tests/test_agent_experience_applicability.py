"""S3c EXP：经验分层（REV-13 §8 / EXP-01～03；**先失败用例**）。

本文件固定四类可观察断言，全部只看**封存请求记录 + 选择入口返回值 + 工具 CLI**，
不读实现内部结构（反向抽检时删实现必红）：

- **EXP-01 两类适用性与 v1 保持**：v1 目录（`{version:1, items[]}`，`scope` 逐值相等）
  在请求路径上行为不变；v2 `exact_fact` 绑定当前事实（typed 依赖），依赖变 ⇒ 拒用
  （`dependency_changed`）；v2 `general_advice` 在已批准的节点/环境/契约范围内可跨 run 复用，
  不要求整请求字节相同。
- **EXP-02 审计指纹 ≠ 适用条件**：v1 的 `scope_for` 仍是请求审计指纹；v2 选择**不用** scope
  判复用（把 scope 换成人造值也不影响 v2 选择，但仍让 v1 条目失效）；源记录完整性（目录格式/
  人工批准/revision/来源路径+sha256）与当前事实适用性（typed 依赖/节点/环境/契约）**分两阶段**
  检查并分别记进选择记录（`phase` 字段）。
- **EXP-03 选择与预算**：批次超显式字节上限、或加上经验后超 `MAX_CONTEXT_BYTES` ⇒ **整批拒用**
  + 候选 ID/原因（`budget_batch_rejected`），不截断、不取前 N 条；强制事实/工作记忆照常；
  模型结果不写回经验目录，迁移草稿不自动晋升。
- **迁移工具**：`python -m host.experience_migrate --catalog … [--validate] [--out …]` 只读校验
  v1/v2 并输出机器可读报告，`--out` 只产出 `status:"draft"` 候选草稿（新文件），拒绝覆盖输入、
  拒绝写入 `adjudication/`。

夹具复用 `test_agent_context_memory`（受控 provider / `call` / `write_json`），**每个测试唯一 run_id**
（`tests/conftest.py` 纪律）。
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

import pytest

from host import agent_memory as AM
from host import paths as P
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.context import RunCtx

# 只复用夹具与既有请求入口，不改既有断言（v1 特征用例仍由原文件独立证明）。
from test_agent_context_memory import call, provider, write_json  # noqa: F401

_RUNS = itertools.count(1)

DEFAULT_ADVICE = "结合当前 RTL 核对掩码；历史结论不能作为本轮通过凭据。"
DEFAULT_SOURCE = "runs/historical/note.md"
#: general_advice 的"已批准环境策略"（收紧 2 后必须显式声明；测试里写明而非隐式放宽）。
APPROVED_POLICY = f"{P.ENV_ID}/real"


# ---------------------------------------------------------------- 夹具与助手


@pytest.fixture
def ctx(tmp_path):
    root = tmp_path / "workspace"
    run_id = f"RUN-20300201-{next(_RUNS):06d}"
    run = root / "runs" / run_id
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    return RunCtx(run_id, run, "real", "happy", KbSources.from_workspace(root),
                  ProgressLog(tmp_path / "events", run_id))


def other_run(ctx, tmp_path):
    """同工作区的另一个 run（EXP-01「通用建议可跨 run 复用」的正向对照）。"""
    run_id = f"RUN-20300201-{next(_RUNS):06d}"
    run = ctx.kb.root / "runs" / run_id
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    return RunCtx(run_id, run, "real", "happy", ctx.kb,
                  ProgressLog(tmp_path / "events", run_id))


def catalog_path(ctx):
    return ctx.kb.root / "adjudication" / "agent_experiences.json"


def write_catalog(ctx, items, version=2):
    path = catalog_path(ctx)
    write_json(path, {"version": version, "items": items})
    return path


def data_file(ctx, rel, text):
    path = ctx.kb.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def source_ref(ctx, rel=DEFAULT_SOURCE, text="human checked evidence"):
    path = data_file(ctx, rel, text)
    return {"path": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def file_dependency(ctx, rel, text=None):
    """`file_sha256` 依赖：路径相对**数据根**，sha 取当前内容。"""
    path = ctx.kb.root / rel
    if text is not None:
        data_file(ctx, rel, text)
    return {"type": "file_sha256", "path": rel,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def v2_item(ctx, item_id="advice-1", *, revision=1, status="approved",
            approved_by="human:reviewer", kind="general_advice", advice=DEFAULT_ADVICE,
            nodes=("N3",), environment_policy=None, contract_versions=None,
            dependencies=(), source=None):
    applicability = {"nodes": list(nodes), "dependencies": list(dependencies)}
    if environment_policy is not None:
        applicability["environment_policy"] = environment_policy
    if contract_versions is not None:
        applicability["contract_versions"] = list(contract_versions)
    return {"id": item_id, "revision": revision, "status": status,
            "approved_by": approved_by, "kind": kind, "advice": advice,
            "source": copy.deepcopy(source) if source is not None else source_ref(ctx),
            "applicability": applicability}


def select(ctx, *, node="N3", input_data=None, scope=None):
    data = {"run_id": ctx.run_id, "diffs": []} if input_data is None else input_data
    if scope is None:
        scope = AM.scope_for(ctx, data, {"info": "", "instruct": "", "schema": {}})
    return AM.select_experiences(ctx, scope, node=node, input_data=data)


def attempt_of(ctx, out):
    return AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)


def record_of(ctx, out):
    """只读**已封存请求**的顶层记录（与模型实际收到的 input 同一份）。"""
    return attempt_of(ctx, out)["request"]


def rejected_reasons(record):
    """选择记录 `experience_selection` 的拒用原因集合（记录形状即契约）。"""
    return {entry["reason"] for entry in record["rejected"]}


def run_migrate(*args):
    return subprocess.run([sys.executable, "-m", "host.experience_migrate", *args],
                          cwd=str(P.LOOP_DIR), capture_output=True, text=True)


# ---------------------------------------------------------------- v1 保持（EXP-01 / REG-01）


async def test_v1_catalog_behavior_is_unchanged_on_the_request_path(ctx, provider):
    """v1：`scope` 逐值相等 ⇒ 注入；诊断为空；记录标明 legacy 选择模式。"""
    first = await call(ctx)
    scope = record_of(ctx, first)["scope"]
    source = data_file(ctx, DEFAULT_SOURCE, "human checked evidence")
    item = {"id": "lesson-1", "status": "approved", "approved_by": "human:reviewer",
            "scope": copy.deepcopy(scope), "advice": DEFAULT_ADVICE,
            "source": {"path": DEFAULT_SOURCE,
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
    path = write_catalog(ctx, [item], version=1)
    before = path.read_bytes()

    out = await call(ctx)
    record = record_of(ctx, out)
    assert [entry["id"] for entry in record["input"]["approved_experiences"]] == ["lesson-1"]
    assert out["experience_diagnostics"] == []
    selection = record["experience_selection"]
    assert selection["catalog_version"] == 1
    assert selection["selection_mode"] == "legacy_scope_match"
    assert selection["catalog_sha256"] == hashlib.sha256(before).hexdigest()
    assert [entry["id"] for entry in selection["selected"]] == ["lesson-1"]
    assert selection["batch"]["decision"] == "selected"
    # 只读：目录与人工内容零写入
    assert path.read_bytes() == before


async def test_v1_public_experiences_api_is_unchanged(ctx):
    """`experiences()` 对外行为保持：无目录 ⇒ 空；v1 命中 ⇒ id/advice/source 三键。"""
    assert AM.experiences(ctx, {"baseline": "v0"}) == ([], [])
    source = data_file(ctx, DEFAULT_SOURCE, "human checked evidence")
    scope = {"env_id": P.ENV_ID, "baseline": "v0", "facts_sha256": "f",
             "prompt_sha256": "p", "schema_sha256": "s"}
    item = {"id": "lesson-1", "status": "approved", "approved_by": "human:reviewer",
            "scope": scope, "advice": DEFAULT_ADVICE,
            "source": {"path": DEFAULT_SOURCE,
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}
    write_catalog(ctx, [item], version=1)
    lessons, diagnostics = AM.experiences(ctx, scope)
    assert diagnostics == []
    assert lessons == [{"id": "lesson-1", "advice": DEFAULT_ADVICE,
                        "source": {"path": DEFAULT_SOURCE,
                                   "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}]


# ---------------------------------------------------------------- EXP-01 两类适用性


async def test_exact_fact_is_used_while_declared_fact_is_current(ctx, provider):
    dependency = file_dependency(ctx, "baseline_index.txt", "index-v0")
    write_catalog(ctx, [v2_item(ctx, kind="exact_fact", nodes=("N3",),
                                dependencies=[dependency])])

    out = await call(ctx)
    record = record_of(ctx, out)
    injected = record["input"]["approved_experiences"]
    assert [entry["id"] for entry in injected] == ["advice-1"]
    assert injected[0]["kind"] == "exact_fact" and injected[0]["revision"] == 1
    checks = record["experience_selection"]["selected"][0]["checks"]
    assert checks["dependencies"] == [{"type": "file_sha256", "result": "ok"}]
    assert out["validation"]["ok"] is True


async def test_exact_fact_is_rejected_after_dependency_change(ctx, provider):
    dependency = file_dependency(ctx, "baseline_index.txt", "index-v0")
    write_catalog(ctx, [v2_item(ctx, kind="exact_fact", nodes=("N3",),
                                dependencies=[dependency])])
    await call(ctx)
    data_file(ctx, "baseline_index.txt", "index-v1-changed")  # 当前事实变化，其余输入不变

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    assert any("dependency_changed" in diagnostic for diagnostic in out["experience_diagnostics"])
    assert rejected_reasons(record["experience_selection"]) == {"dependency_changed"}
    assert attempt_of(ctx, out)["result"]["status"] == "validated", "经验拒用不得使普通执行失败"


async def test_general_advice_is_reused_across_runs_in_approved_scope(ctx, provider, tmp_path):
    """general_advice：不同 run、不同输入事实，只要已批准范围成立就复用（不要求字节相同）。"""
    write_catalog(ctx, [v2_item(ctx, kind="general_advice", nodes=("N3",),
                                environment_policy=APPROVED_POLICY,
                                dependencies=[{"type": "env", "env_id": P.ENV_ID},
                                              {"type": "baseline", "value": "v0"}])])
    first = other_run(ctx, tmp_path)
    second = other_run(ctx, tmp_path)

    for run, diffs in ((first, []), (second, [{"entry_id": "a", "before": "x", "after": "y"}])):
        out = await call(run, input_data={"run_id": run.run_id, "diffs": diffs})
        record = record_of(run, out)
        assert [entry["id"] for entry in record["input"]["approved_experiences"]] == ["advice-1"], \
            (run.run_id, out["experience_diagnostics"])
        assert record["experience_selection"]["selected"][0]["kind"] == "general_advice"


async def test_audit_fingerprint_change_breaks_v1_scope_but_not_general_advice(ctx, provider):
    """EXP-02：审计指纹（`scope_for`）变化 ⇒ v1 拒用；v2 general_advice 不受影响。"""
    one = await call(ctx)
    scope = record_of(ctx, one)["scope"]
    source = data_file(ctx, DEFAULT_SOURCE, "human checked evidence")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    v1_item = {"id": "legacy-lesson", "status": "approved", "approved_by": "human:reviewer",
               "scope": copy.deepcopy(scope), "advice": DEFAULT_ADVICE,
               "source": {"path": DEFAULT_SOURCE, "sha256": digest}}
    write_catalog(ctx, [v1_item], version=1)

    changed = {"run_id": ctx.run_id, "diffs": [{"entry_id": "z", "before": "old", "after": "new"}]}
    out = await call(ctx, input_data=changed)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    assert any("scope mismatch" in diagnostic for diagnostic in out["experience_diagnostics"]), \
        "v1 诊断文案保持：`<id>: scope mismatch`"

    write_catalog(ctx, [v2_item(ctx, item_id="legacy-lesson", kind="general_advice",
                                advice=DEFAULT_ADVICE,
                                environment_policy=APPROVED_POLICY)])
    out = await call(ctx, input_data=changed)
    record = record_of(ctx, out)
    assert [entry["id"] for entry in record["input"]["approved_experiences"]] == ["legacy-lesson"]
    assert out["experience_diagnostics"] == []


def test_v2_selection_does_not_use_the_audit_scope(ctx):
    """EXP-02：把 scope 换成人造值，v2 选择逐值不变（scope 只是审计指纹）。"""
    write_catalog(ctx, [v2_item(ctx, kind="general_advice", nodes=("N3",),
                                environment_policy=APPROVED_POLICY)])
    real = select(ctx)
    forged = select(ctx, scope={"env_id": "forged", "baseline": "forged",
                               "facts_sha256": "forged", "prompt_sha256": "forged",
                               "schema_sha256": "forged"})
    assert [entry["id"] for entry in real.lessons] == ["advice-1"]
    assert forged.lessons == real.lessons
    assert forged.record["applicable_context"] == real.record["applicable_context"]


# ---------------------------------------------------------------- EXP-01 范围与 typed 依赖


@pytest.mark.parametrize("mutate,reason", [
    (lambda item: item["applicability"].update(nodes=["N6"]), "environment_mismatch"),
    (lambda item: item["applicability"].update(environment_policy="other-env/real"),
     "environment_mismatch"),
    (lambda item: item["applicability"].update(environment_policy=f"{P.ENV_ID}/drill"),
     "environment_mismatch"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "env", "env_id": "other-env"}]), "environment_mismatch"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "mode", "value": "drill"}]), "environment_mismatch"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "baseline", "value": "v9"}]), "dependency_changed"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "contract", "version": 2}]), "contract_incompatible"),
    (lambda item: item["applicability"].update(contract_versions=[2]), "contract_incompatible"),
    (lambda item: item["applicability"].update(contract_versions=[]), "contract_incompatible"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "semantic_similarity", "value": "0.9"}]), "unknown_dependency"),
    (lambda item: item["applicability"].update(
        dependencies=[{"type": "baseline", "value": "v0", "weight": 1}]), "invalid_applicability"),
    (lambda item: item["applicability"].update(nodes=[]), "invalid_applicability"),
    (lambda item: item["applicability"].update(nodes=["N99"]), "invalid_applicability"),
    (lambda item: item["applicability"].update(nodes="N3"), "invalid_applicability"),
    (lambda item: item["applicability"].update(dependencies="env"),
     "invalid_applicability"),
    (lambda item: item["applicability"].update(similarity_threshold=0.7),
     "invalid_applicability"),
    (lambda item: item.update(kind="hint"), "invalid_item"),
    (lambda item: item.update(revision=0), "invalid_item"),
    (lambda item: item.update(extra_field="x"), "invalid_item"),
    (lambda item: item.update(advice=""), "invalid_item"),
    (lambda item: item.update(advice="x" * 4001), "invalid_item"),
    (lambda item: item.update(source="not-an-object"), "invalid_item"),
    (lambda item: item.update(status="draft"), "not_approved"),
    (lambda item: item.update(status="revoked"), "revoked"),
    (lambda item: item.update(approved_by="model:author"), "not_approved"),
    (lambda item: item.update(approved_by="human:   "), "not_approved"),
])
def test_inapplicable_v2_items_are_excluded_with_reason(ctx, mutate, reason):
    item = v2_item(ctx, kind="exact_fact",
                   dependencies=[{"type": "env", "env_id": P.ENV_ID}])
    mutate(item)
    write_catalog(ctx, [item])
    selection = select(ctx)
    assert selection.lessons == []
    assert rejected_reasons(selection.record) == {reason}, selection.record["rejected"]
    assert selection.record["rejected"][0]["id"] == "advice-1"
    assert reason in AM.REJECT_REASONS
    assert any(reason in diagnostic for diagnostic in selection.diagnostics)
    assert not any(DEFAULT_ADVICE[:8] in diagnostic for diagnostic in selection.diagnostics), \
        "诊断只报非秘密 ID/规则，不回显建议正文"


@pytest.mark.parametrize("mutate,reason", [
    (lambda ctx, item: data_file(ctx, DEFAULT_SOURCE, "tampered-content"), "source_corrupt"),
    (lambda ctx, item: item["source"].update(
        {"path": "runs/historical/missing.md"}), "source_missing"),
    (lambda ctx, item: item["source"].update({"path": "../outside.md"}), "source_corrupt"),
    (lambda ctx, item: item["source"].update({"path": "/etc/passwd"}), "source_corrupt"),
    (lambda ctx, item: item["source"].update({"path": "conflicts/conflicts.json"}),
     "source_corrupt"),
    (lambda ctx, item: item["source"].pop("sha256"), "source_corrupt"),
])
def test_bad_sources_are_rejected_before_applicability(ctx, mutate, reason):
    item = v2_item(ctx, kind="exact_fact")
    mutate(ctx, item)
    write_catalog(ctx, [item])
    selection = select(ctx)
    assert selection.lessons == []
    assert rejected_reasons(selection.record) == {reason}, selection.record["rejected"]
    assert selection.record["rejected"][0]["phase"] == "source_integrity"


def test_symlink_escaping_the_data_root_is_rejected(ctx, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("outside data", encoding="utf-8")
    link = ctx.kb.root / "runs" / "historical" / "link.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside)
    item = v2_item(ctx, kind="exact_fact",
                   source={"path": "runs/historical/link.md",
                           "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()})
    write_catalog(ctx, [item])
    selection = select(ctx)
    assert selection.lessons == []
    assert rejected_reasons(selection.record) == {"source_corrupt"}


def test_two_phases_are_ordered_and_recorded_separately(ctx):
    """源完整性先于当前事实适用性；两阶段各记 `phase`（EXP-02）。"""
    broken = v2_item(ctx, item_id="broken", kind="exact_fact", nodes=["N6"])
    broken["source"]["path"] = "../outside.md"          # 阶段①坏
    inapplicable = v2_item(ctx, item_id="inapplicable", kind="exact_fact", nodes=["N6"],
                          dependencies=[{"type": "env", "env_id": P.ENV_ID}])
    write_catalog(ctx, [broken, inapplicable])
    selection = select(ctx)
    phases = {entry["id"]: entry["phase"] for entry in selection.record["rejected"]}
    assert phases == {"broken": "source_integrity", "inapplicable": "applicability"}
    assert {entry["reason"] for entry in selection.record["rejected"]} == {
        "source_corrupt", "environment_mismatch"}


def test_targets_dependency_uses_current_request_input_fingerprint(ctx):
    targets = [{"case": "demo", "excerpt": {"text": "old"}}]
    dependency = {"type": "targets_sha256", "value": AM.fingerprint(targets)}
    write_catalog(ctx, [v2_item(ctx, kind="exact_fact", nodes=("N6",),
                                dependencies=[dependency])])
    matched = select(ctx, node="N6", input_data={"targets": copy.deepcopy(targets)})
    assert [entry["id"] for entry in matched.lessons] == ["advice-1"]

    changed = select(ctx, node="N6",
                     input_data={"targets": [{"case": "demo", "excerpt": {"text": "new"}}]})
    assert changed.lessons == [] and rejected_reasons(changed.record) == {"dependency_changed"}

    absent = select(ctx, node="N6", input_data={"diffs": []})
    assert absent.lessons == [] and rejected_reasons(absent.record) == {"unknown_dependency"}


@pytest.mark.parametrize("path", ["../outside.txt", "/etc/passwd", "runs/../outside.txt",
                                  "missing/file.txt"])
def test_file_dependency_is_unresolvable_outside_or_absent(ctx, path):
    item = v2_item(ctx, kind="exact_fact", nodes=("N3",),
                   dependencies=[{"type": "file_sha256", "path": path, "sha256": "0" * 64}])
    write_catalog(ctx, [item])
    selection = select(ctx)
    assert selection.lessons == []
    assert rejected_reasons(selection.record) == {"unknown_dependency"}


def test_baseline_dependency_with_unknown_current_baseline_is_rejected(ctx):
    (ctx.run_dir / "view.json").unlink()
    write_catalog(ctx, [v2_item(ctx, kind="exact_fact", nodes=("N3",),
                                dependencies=[{"type": "baseline", "value": "v0"}])])
    selection = select(ctx)
    assert selection.lessons == []
    assert rejected_reasons(selection.record) == {"unknown_dependency"}


def test_selection_is_sorted_by_id_deterministically(ctx):
    write_catalog(ctx, [v2_item(ctx, item_id=item_id, kind="general_advice",
                                environment_policy=APPROVED_POLICY)
                        for item_id in ("zeta", "alpha", "mike")])
    first, second = select(ctx), select(ctx)
    assert [entry["id"] for entry in first.lessons] == ["alpha", "mike", "zeta"]
    assert first.record["selected"] == second.record["selected"]
    assert first.record["applicable_context"] == second.record["applicable_context"]


async def test_selection_record_carries_catalog_fingerprint_and_context(ctx, provider):
    path = write_catalog(ctx, [v2_item(ctx, kind="general_advice",
                                        environment_policy=APPROVED_POLICY)])
    out = await call(ctx)
    record = record_of(ctx, out)
    selection = record["experience_selection"]
    assert selection["catalog_version"] == 2
    assert selection["catalog_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert selection["applicable_context"] == {
        "node": "N3", "env_id": P.ENV_ID, "mode": "real", "baseline": "v0",
        "contract_version": AM.CONTRACT_VERSION}
    assert AM.CONTRACT_VERSION == 1
    assert record["input"]["working_memory"]["version"] == 1


# ---------------------------------------------------------------- EXP-02 目录级拒用


@pytest.mark.parametrize("case", ["unknown_version", "items_not_a_list",
                                   "duplicate_ids", "item_not_an_object"])
def test_invalid_catalogs_are_rejected_whole(ctx, case):
    if case == "unknown_version":
        version, items = 3, []
    elif case == "items_not_a_list":
        version, items = 2, "not-a-list"
    elif case == "duplicate_ids":
        version = 2
        items = [v2_item(ctx, item_id="same", kind="general_advice"),
                 v2_item(ctx, item_id="same", kind="general_advice")]
    else:
        version, items = 2, ["not-an-object"]
    write_catalog(ctx, items, version=version)
    selection = select(ctx)
    assert selection.lessons == [], case
    assert selection.diagnostics and "experience catalog rejected" in selection.diagnostics[0]
    assert selection.record["batch"]["decision"] == "catalog_rejected"


def test_catalog_over_explicit_item_limit_is_rejected_whole(ctx):
    assert AM.EXPERIENCE_V2_MAX_ITEMS == 10
    write_catalog(ctx, [v2_item(ctx, item_id=f"advice-{i:02d}", kind="general_advice")
                        for i in range(AM.EXPERIENCE_V2_MAX_ITEMS + 1)])
    selection = select(ctx)
    assert selection.lessons == []
    assert "experience catalog rejected" in selection.diagnostics[0]


# ---------------------------------------------------------------- EXP-03 预算整批拒用


async def test_batch_over_explicit_byte_limit_is_rejected_whole(ctx, provider, monkeypatch):
    assert AM.EXPERIENCE_BATCH_MAX_BYTES == 8000
    monkeypatch.setattr(AM, "EXPERIENCE_BATCH_MAX_BYTES", 10)
    write_catalog(ctx, [v2_item(ctx, item_id="advice-a", kind="general_advice",
                                environment_policy=APPROVED_POLICY),
                        v2_item(ctx, item_id="advice-b", kind="general_advice",
                                environment_policy=APPROVED_POLICY)])

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences"), "整批拒用，不得取前 N 条"
    assert any("budget_batch_rejected" in message for message in out["experience_diagnostics"])
    batch = record["experience_selection"]["batch"]
    assert batch["decision"] == "rejected" and batch["reason"] == "budget_batch_rejected"
    assert record["experience_selection"]["selected"] == []
    candidates = {entry["id"] for entry in record["experience_selection"]["rejected"]}
    assert candidates == {"advice-a", "advice-b"}
    assert {entry["reason"] for entry in record["experience_selection"]["rejected"]} == {
        "budget_batch_rejected"}
    assert attempt_of(ctx, out)["result"]["status"] == "validated", \
        "经验整批拒用不得使普通执行失败"
    assert record["input"]["working_memory"]["entries"], "强制事实/工作记忆照常"


async def test_remaining_budget_rejects_whole_batch_without_truncation(ctx, provider,
                                                                     monkeypatch):
    write_catalog(ctx, [v2_item(ctx, item_id="advice-a", kind="general_advice",
                                advice="A" * 1200, environment_policy=APPROVED_POLICY),
                        v2_item(ctx, item_id="advice-b", kind="general_advice",
                                advice="B" * 1200, environment_policy=APPROVED_POLICY)])
    first = await call(ctx)
    record = record_of(ctx, first)
    lessons = record["input"]["approved_experiences"]
    assert [entry["id"] for entry in lessons] == ["advice-a", "advice-b"]
    contract = {key: record[key] for key in ("info", "instruct", "schema")}
    without = {key: value for key, value in record["input"].items()
               if key != "approved_experiences"}
    base = AM.measure_budget(without, contract)["used_bytes"]
    batch_bytes = AM.experience_batch_bytes(lessons)
    assert batch_bytes <= AM.EXPERIENCE_BATCH_MAX_BYTES
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES", base + batch_bytes - 1)

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    batch = record["experience_selection"]["batch"]
    assert batch["decision"] == "rejected" and batch["reason"] == "budget_batch_rejected"
    assert batch["stage"] == "remaining_budget"
    assert attempt_of(ctx, out)["result"]["status"] == "validated"
    assert any("budget_batch_rejected" in message for message in out["experience_diagnostics"])
    # 不截断：候选 ID 全部保留在拒用清单里
    assert {entry["id"] for entry in record["experience_selection"]["rejected"]} == {
        "advice-a", "advice-b"}


def test_experience_batch_bytes_is_the_single_measurement(ctx):
    lessons = [{"id": "a", "advice": "x"}]
    assert AM.experience_batch_bytes(lessons) == len(
        AM.encoded({"approved_experiences": lessons}))
    assert AM.experience_batch_bytes([]) == len(AM.encoded({"approved_experiences": []}))


# ---------------------------------------------------------------- EXP-03 不自动晋升 / 不写回


async def test_catalog_is_read_only_and_model_output_is_never_promoted(ctx, provider):
    write_catalog(ctx, [v2_item(ctx, kind="general_advice",
                                environment_policy=APPROVED_POLICY)])
    path = catalog_path(ctx)
    before = path.read_bytes()
    listing = sorted(p.name for p in path.parent.iterdir())

    await call(ctx)
    await call(ctx)
    assert path.read_bytes() == before
    assert sorted(p.name for p in path.parent.iterdir()) == listing
    assert json.loads(path.read_text(encoding="utf-8"))["items"][0]["status"] == "approved"


# ---------------------------------------------------------------- 迁移/校验工具


def test_migration_validate_reports_machine_readable_and_is_read_only(ctx):
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"env_id": P.ENV_ID, "baseline": "v0",
                                   "facts_sha256": "f", "prompt_sha256": "p",
                                   "schema_sha256": "s"},
                         "advice": DEFAULT_ADVICE, "source": source_ref(ctx)}], version=1)
    path = catalog_path(ctx)
    before = path.read_bytes()

    result = run_migrate("--catalog", str(path), "--validate")
    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert report["version"] == 1
    assert report["catalog_sha256"] == hashlib.sha256(before).hexdigest()
    assert [entry["id"] for entry in report["items"]] == ["lesson-1"]
    assert report["items"][0]["accepted"] is True
    assert report["scope"] == "source_integrity_only", "校验不假装核验了当前事实"
    assert path.read_bytes() == before


def test_migration_validate_flags_bad_source(ctx):
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"baseline": "v0"}, "advice": DEFAULT_ADVICE,
                         "source": source_ref(ctx)}], version=1)
    data_file(ctx, DEFAULT_SOURCE, "content changed after approval")
    path = catalog_path(ctx)
    before = path.read_bytes()

    result = run_migrate("--catalog", str(path), "--validate")
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["ok"] is False
    assert report["items"][0]["accepted"] is False
    assert report["items"][0]["reason"] == "source_corrupt"
    assert path.read_bytes() == before


def test_migration_out_refuses_to_overwrite_input_or_write_adjudication(ctx):
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"baseline": "v0"}, "advice": DEFAULT_ADVICE,
                         "source": source_ref(ctx)}], version=1)
    path = catalog_path(ctx)
    before = path.read_bytes()

    same = run_migrate("--catalog", str(path), "--out", str(path))
    assert same.returncode != 0
    assert json.loads(same.stdout)["ok"] is False
    assert path.read_bytes() == before

    directory = ctx.kb.root / "adjudication" / "draft"
    target = directory / "agent_experiences.v2.json"
    refused = run_migrate("--catalog", str(path), "--out", str(target))
    assert refused.returncode != 0
    assert json.loads(refused.stdout)["ok"] is False
    assert not directory.exists(), "拒绝写到 adjudication/ 目录（不建目录、不写文件）"


def test_migration_out_writes_draft_candidate_with_condition_changes(ctx):
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"env_id": P.ENV_ID, "baseline": "v0",
                                   "facts_sha256": "f", "prompt_sha256": "p",
                                   "schema_sha256": "s"},
                         "advice": DEFAULT_ADVICE, "source": source_ref(ctx)}], version=1)
    path = catalog_path(ctx)
    before = path.read_bytes()
    draft = ctx.kb.root / "drafts" / "agent_experiences.v2.json"

    result = run_migrate("--catalog", str(path), "--out", str(draft))
    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert report["ok"] is True
    assert draft.is_file()
    assert path.read_bytes() == before, "迁移不修改人工目录"
    document = json.loads(draft.read_text(encoding="utf-8"))
    assert document["version"] == 2
    item = document["items"][0]
    assert item["id"] == "lesson-1"
    assert item["status"] == "draft" and item["approved_by"] is None
    assert item["revision"] == 1
    assert item["advice"] == DEFAULT_ADVICE
    assert item["source"] == source_ref(ctx) or item["source"]["sha256"] == \
        hashlib.sha256((ctx.kb.root / DEFAULT_SOURCE).read_bytes()).hexdigest()
    kinds = {dependency["type"] for dependency in item["applicability"]["dependencies"]}
    assert kinds == {"env", "baseline"}, "可迁移的显式条件保留为 typed 依赖"
    assert item["applicability"]["nodes"] == [], "节点白名单必须由人填写，工具不猜"
    entry = report["migration"][0]
    assert entry["old_id"] == "lesson-1" and entry["new_id"] == "lesson-1"
    assert entry["new_revision"] == 1
    assert entry["kind"] == "exact_fact"
    assert entry["condition_changes"], "必须给出条件变化说明"
    assert any("facts_sha256" in note for note in entry["condition_changes"])

    # 再写一次（同路径已存在）⇒ 拒绝覆盖已产出的候选件
    again = run_migrate("--catalog", str(path), "--out", str(draft))
    assert again.returncode != 0


async def test_migrated_draft_is_not_consumed_until_a_human_approves(ctx, provider):
    """不自动晋升：草稿是 `status:"draft"`，放进人工目录也**不可用**。"""
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"env_id": P.ENV_ID, "baseline": "v0",
                                   "facts_sha256": "f", "prompt_sha256": "p",
                                   "schema_sha256": "s"},
                         "advice": DEFAULT_ADVICE, "source": source_ref(ctx)}], version=1)
    path = catalog_path(ctx)
    draft = ctx.kb.root / "drafts" / "agent_experiences.v2.json"
    assert run_migrate("--catalog", str(path), "--out", str(draft)).returncode == 0
    path.write_bytes(draft.read_bytes())  # 模拟人把候选草稿放到人工目录（但未审批）

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    assert rejected_reasons(record["experience_selection"]) == {"not_approved"}
    assert any("not_approved" in message for message in out["experience_diagnostics"])


def test_migration_validate_accepts_v2_catalog_but_states_its_scope(ctx):
    """`--validate` 也覆盖 v2：只报源完整性，且显式声明没核验当前事实。"""
    write_catalog(ctx, [v2_item(ctx, kind="general_advice",
                                environment_policy=APPROVED_POLICY)], version=2)
    path = catalog_path(ctx)
    before = path.read_bytes()
    result = run_migrate("--catalog", str(path), "--validate")
    report = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert report["ok"] is True and report["version"] == 2
    assert report["items"][0]["accepted"] is True
    assert report["scope"] == "source_integrity_only"
    assert any("运行上下文" in note for note in report["notes"])
    assert path.read_bytes() == before


def test_migration_out_refuses_version_two_input_and_unknown_version(ctx):
    write_catalog(ctx, [v2_item(ctx, kind="general_advice",
                                environment_policy=APPROVED_POLICY)], version=2)
    path = catalog_path(ctx)
    draft = ctx.kb.root / "drafts" / "v2.json"
    refused = run_migrate("--catalog", str(path), "--out", str(draft))
    assert refused.returncode != 0
    assert "already version 2" in json.loads(refused.stdout)["error"]
    assert not draft.exists()

    write_catalog(ctx, [], version=3)
    unknown = run_migrate("--catalog", str(path), "--validate")
    assert unknown.returncode != 0
    assert json.loads(unknown.stdout)["error"] == "format/version"


# ------------------------------------------------- 收紧（Lead 裁决 2026-10-28）：适用性不得 fail-open
#
# 依据 REV-13 §8.3：exact_fact「绑定明确资源/事实的当前内容、环境及必要基线；每个依赖由既有
# Host 事实解析器核验」；general_advice「绑定已批准的节点/任务类别、环境策略及契约兼容范围」。
# 设计 §7：「缺依赖不是"通用"的理由」。没有依赖的 exact_fact 永远检测不到资源变化；没有
# 环境/契约范围的 general_advice 等于无条件跨环境套用 —— 两者都是 fail-open，必须拒用。


def test_exact_fact_without_typed_dependencies_is_rejected(ctx):
    """收紧 1：exact_fact 必须声明至少一条 typed 依赖（否则无法检测当前事实变化）。"""
    write_catalog(ctx, [v2_item(ctx, kind="exact_fact", nodes=("N3",), dependencies=[])])
    selection = select(ctx)
    assert selection.lessons == [], "无依赖的 exact_fact 不得被选中"
    entry = selection.record["rejected"][0]
    assert entry["reason"] == "invalid_applicability"
    assert entry["phase"] == "applicability"
    assert "exact_fact requires explicit typed dependencies" in entry["detail"]
    assert any("invalid_applicability" in message for message in selection.diagnostics)


@pytest.mark.parametrize("declared,selected,reason", [
    ({}, False, "invalid_applicability"),
    # 依赖非空**不能**替代"已批准的环境/契约范围"（设计 §7：缺依赖不是通用的理由，
    # 反过来依赖也不是范围；环境/契约范围必须显式声明）
    ({"dependencies": [{"type": "env", "env_id": P.ENV_ID}]}, False, "invalid_applicability"),
    ({"contract_versions": []}, False, "invalid_applicability"),
    ({"environment_policy": f"{P.ENV_ID}/real"}, True, None),
    ({"contract_versions": [1]}, True, None),
    ({"environment_policy": f"{P.ENV_ID}/real", "contract_versions": [1]}, True, None),
])
def test_general_advice_requires_approved_environment_or_contract_range(ctx, declared,
                                                                      selected, reason):
    """收紧 2：general_advice 必须声明非空 environment_policy 或非空 contract_versions。"""
    fields = {"kind": "general_advice", "nodes": ("N3",), "dependencies": []}
    fields.update(declared)
    write_catalog(ctx, [v2_item(ctx, **fields)])
    outcome = select(ctx)
    if selected:
        assert [entry["id"] for entry in outcome.lessons] == ["advice-1"], outcome.diagnostics
        assert outcome.record["rejected"] == []
        return
    assert outcome.lessons == []
    entry = outcome.record["rejected"][0]
    assert entry["reason"] == reason
    assert entry["phase"] == "applicability"
    assert ("general_advice requires an approved environment policy or contract range"
            in entry["detail"])
    assert any(reason in message for message in outcome.diagnostics)


def test_general_advice_with_environment_policy_mismatch_still_needs_current_env(ctx):
    """批准范围存在但当前环境不符 ⇒ environment_mismatch（收紧不放宽既有环境判定）。"""
    write_catalog(ctx, [v2_item(ctx, kind="general_advice", nodes=("N3",),
                                environment_policy="other-env/real")])
    outcome = select(ctx)
    assert outcome.lessons == []
    assert rejected_reasons(outcome.record) == {"environment_mismatch"}


async def test_migrated_draft_needs_human_completion_after_partial_approval(ctx, provider):
    """迁移草稿在新规则下仍是"需人工填写"：只补审批、不补 nodes ⇒ 不可选中。

    草稿形状 = `exact_fact` + `dependencies:[env,baseline]`（满足收紧 1）+ `nodes:[]`
    （不满足"节点非空"，由人填写）；此处模拟"人只把 status/approved_by 改成 approved"，
    证明它不会因为迁移自动生成的字段而变成可批准/可选择。
    """
    write_catalog(ctx, [{"id": "lesson-1", "status": "approved",
                         "approved_by": "human:reviewer",
                         "scope": {"env_id": P.ENV_ID, "baseline": "v0",
                                   "facts_sha256": "f", "prompt_sha256": "p",
                                   "schema_sha256": "s"},
                         "advice": DEFAULT_ADVICE, "source": source_ref(ctx)}], version=1)
    path = catalog_path(ctx)
    draft = ctx.kb.root / "drafts" / "agent_experiences.v2.json"
    assert run_migrate("--catalog", str(path), "--out", str(draft)).returncode == 0
    document = json.loads(draft.read_text(encoding="utf-8"))
    item = document["items"][0]
    assert item["applicability"]["nodes"] == []
    assert item["applicability"]["dependencies"], "草稿必须带已迁移的显式依赖（收紧 1）"
    # 模拟人**只**补审批字段（不动 nodes）
    item["status"] = "approved"
    item["approved_by"] = "human:reviewer"
    write_catalog(ctx, document["items"], version=2)

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    assert rejected_reasons(record["experience_selection"]) == {"invalid_applicability"}
    assert not record["input"].get("approved_experiences")


# ------------------------------------------- 复核修复 A（P2-11）：目录存在但无法采用时排障口径
#
# "目录不存在 = 未配置"与"目录存在但解析/版本非法 = 配置坏了"是两件事：前者 legacy 空态，
# 后者必须在选择记录里明确标成 `selection_mode="catalog_rejected"` + 原因，否则排障会误以为
# 走的是正常 legacy 精确匹配。行为不变：整目录不采用、不注入、诊断仍走 `experience catalog rejected: …`。


@pytest.mark.parametrize("content,reason,detail", [
    ('{"version": 2, "items": [', "catalog_unparsable", "JSONDecodeError"),
    ('not-json-at-all', "catalog_unparsable", "JSONDecodeError"),
])
def test_unparsable_catalog_records_catalog_rejected_mode(ctx, content, reason, detail):
    path = catalog_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    selection = select(ctx)
    assert selection.lessons == [], "坏目录整目录不采用、不注入"
    record = selection.record
    assert record["selection_mode"] == "catalog_rejected"
    assert record["rejection"] == {"reason": reason, "detail": detail}
    assert record["batch"]["decision"] == "catalog_rejected"
    assert record["selected"] == [] and record["rejected"] == []
    assert selection.diagnostics and all(
        "experience catalog rejected" in message for message in selection.diagnostics)


def test_unreadable_catalog_records_catalog_rejected_mode(ctx):
    path = catalog_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir()  # 目录存在但不是文件 ⇒ 读取失败
    selection = select(ctx)
    assert selection.lessons == []
    record = selection.record
    assert record["selection_mode"] == "catalog_rejected"
    assert record["rejection"]["reason"] == "catalog_unreadable"
    assert record["rejection"]["detail"] == "IsADirectoryError"
    assert record["catalog_sha256"] is None
    assert record["batch"]["decision"] == "catalog_rejected"


@pytest.mark.parametrize("document,detail", [
    ({"version": 3, "items": []}, "format/version"),
    ({"version": 2, "items": "not-a-list"}, "format/version"),
    ({"version": 1, "items": [{"id": "x"}, {"id": "x"}]},
     "items must be unique objects with non-empty id"),
])
def test_invalid_version_or_format_records_catalog_rejected_mode(ctx, document, detail):
    path = catalog_path(ctx)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    selection = select(ctx)
    assert selection.lessons == []
    record = selection.record
    assert record["selection_mode"] == "catalog_rejected"
    assert record["rejection"] == {"reason": "catalog_invalid", "detail": detail}
    assert record["batch"]["decision"] == "catalog_rejected"
    assert selection.diagnostics and all(
        "experience catalog rejected" in message for message in selection.diagnostics)


def test_absent_catalog_keeps_the_legacy_empty_state(ctx):
    """无目录 = 未配置：旧行为不变（空选择、无诊断、legacy 空态）。"""
    selection = select(ctx)
    assert selection.lessons == [] and selection.diagnostics == []
    record = selection.record
    assert record["selection_mode"] == "legacy_scope_match"
    assert record["catalog_version"] is None and record["catalog_sha256"] is None
    assert record["batch"]["decision"] == "no_applicable_items"
    assert "rejection" not in record


# ------------------------------------ 复核修复 C（P2-6）：剩余预算整批拒用只在 v2 目录生效
#
# v1 目录（`{version:1}`，scope 逐值相等）是既有行为：命中经验就采用；若因此超总预算，
# 旧行为是 `AM.check_budget` 让**节点显式失败**（RuntimeError，不调用模型），而不是静默弃用
# 经验继续执行。v2 才按"剩余预算"整批不采用（EXP-03）。两者记录必须各自自洽：
# v1 `batch.enforced=false` ⇒ decision 不得是 rejected；v2 `enforced=true` ⇒ rejected 有 reason/stage。


def v1_lesson(ctx, scope):
    """构造一条与当前请求 scope 逐值相等的 v1 条目（来源 + 指纹就地核验）。"""
    source = data_file(ctx, DEFAULT_SOURCE, "human checked evidence")
    return {"id": "lesson-1", "status": "approved", "approved_by": "human:reviewer",
            "scope": copy.deepcopy(scope), "advice": DEFAULT_ADVICE,
            "source": {"path": DEFAULT_SOURCE,
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}}


def latest_request(ctx, node="N3"):
    """最新一次尝试的封存 request（失败尝试也有 result=error，可直接 verify_attempt）。"""
    folder = sorted((ctx.run_dir / "agent_calls" / node).iterdir())[-1]
    return AM.verify_attempt(folder)


async def measure_v1_batch_over_budget(ctx, provider, monkeypatch):
    """铺一条 v1 命中经验，测量 base/batch 字节后把总预算压到"加上经验即超"。"""
    first = await call(ctx)                       # 先取当前请求的审计 scope
    write_catalog(ctx, [v1_lesson(ctx, record_of(ctx, first)["scope"])], version=1)
    measured = await call(ctx)                    # 正常一次：拿到实际注入的经验
    record = record_of(ctx, measured)
    lessons = record["input"]["approved_experiences"]
    assert [entry["id"] for entry in lessons] == ["lesson-1"]
    contract = {key: record[key] for key in ("info", "instruct", "schema")}
    without = {key: value for key, value in record["input"].items()
               if key != "approved_experiences"}
    base = AM.measure_budget(without, contract)["used_bytes"]
    # 用**真实序列化**测量"加上经验后"的总量，再把上限压到刚好低于它：
    # v1 走旧路径时唯一判据是 `AM.check_budget` 的精确测量（不是 base+batch 的保守估计）。
    with_experiences = {**without, "approved_experiences": lessons}
    actual = AM.measure_budget(with_experiences, contract)["used_bytes"]
    assert actual > base, "断言环境无效：加上经验必须真的更大"
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES", actual - 1)
    return len(provider["inputs"])


async def test_v1_experience_over_budget_fails_at_check_budget_without_model_call(
        ctx, provider, monkeypatch):
    """① v1 + 超预算 ⇒ 旧行为：`check_budget` 让节点失败（RuntimeError），不调用模型。"""
    calls_before = await measure_v1_batch_over_budget(ctx, provider, monkeypatch)
    with pytest.raises(RuntimeError, match="budget|预算"):
        await call(ctx)
    assert len(provider["inputs"]) == calls_before, "v1 超预算必须在调用模型前失败"
    attempt = latest_request(ctx)
    assert attempt["result"]["status"] == "error"
    assert attempt["request"]["input"].get("approved_experiences"), \
        "v1 不得静默弃用经验：失败原因应是总预算，而不是把经验拿掉后继续执行"


async def test_v1_batch_record_never_contradicts_itself(ctx, provider, monkeypatch):
    """③ v1 记录不自相矛盾：`batch.enforced=false` 且 decision 不是 rejected（无 reason/stage）。"""
    await measure_v1_batch_over_budget(ctx, provider, monkeypatch)
    with pytest.raises(RuntimeError, match="budget|预算"):
        await call(ctx)
    attempt = latest_request(ctx)
    selection = attempt["request"]["experience_selection"]
    assert selection["catalog_version"] == 1
    assert selection["selection_mode"] == "legacy_scope_match"
    batch = selection["batch"]
    assert batch["enforced"] is False
    assert batch["decision"] not in ("rejected", "budget_batch_rejected")
    assert "reason" not in batch and "stage" not in batch, batch
    assert [entry["id"] for entry in selection["selected"]] == ["lesson-1"]


async def test_v2_remaining_budget_still_rejects_batch_and_continues(ctx, provider,
                                                                    monkeypatch):
    """② v2 + 超预算 ⇒ 保持 EXP-03：整批不采用（enforced=true + rejected/reason/stage），节点继续。"""
    write_catalog(ctx, [v2_item(ctx, item_id="advice-a", kind="general_advice",
                                advice="A" * 1200, environment_policy=APPROVED_POLICY),
                        v2_item(ctx, item_id="advice-b", kind="general_advice",
                                advice="B" * 1200, environment_policy=APPROVED_POLICY)])
    first = await call(ctx)
    record = record_of(ctx, first)
    lessons = record["input"]["approved_experiences"]
    assert [entry["id"] for entry in lessons] == ["advice-a", "advice-b"]
    contract = {key: record[key] for key in ("info", "instruct", "schema")}
    without = {key: value for key, value in record["input"].items()
               if key != "approved_experiences"}
    base = AM.measure_budget(without, contract)["used_bytes"]
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES",
                        base + AM.experience_batch_bytes(lessons) - 1)

    out = await call(ctx)
    record = record_of(ctx, out)
    assert not record["input"].get("approved_experiences")
    assert attempt_of(ctx, out)["result"]["status"] == "validated"
    selection = record["experience_selection"]
    assert selection["catalog_version"] == 2
    batch = selection["batch"]
    assert batch["enforced"] is True
    assert batch["decision"] == "rejected" and batch["reason"] == "budget_batch_rejected"
    assert batch["stage"] == "remaining_budget"
    assert {entry["id"] for entry in selection["rejected"]} == {"advice-a", "advice-b"}
