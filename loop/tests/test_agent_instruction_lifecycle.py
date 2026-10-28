"""S3b IL：run 作用域指令生命周期（REV-13 §7 / IL-01～04；**先失败用例**）。

本文件固定四类可观察断言，全部只看**封存记录与投影**，不读实现细节：

- **IL-01 作用域**：`attempt` 只作用于 Host 预留的那一次替代尝试（该尝试终态即到期，
  不滚到后续返工）；`node_rework` 只作用于同 run 同节点；`run` 只作用于目标节点白名单；
  **绝不跨 run**。
- **IL-02 原子与幂等**：`supersede` 是**单个**事件（旧失效 + 新条目同时成立，读取器看不到
  双生效/都失效的中间态）；`revoke`/`supersede` 目标必须当前有效；同 `request_id` 同载荷
  返回原回执、不同载荷冲突；CAS revision 不符冲突且**写前拒绝**。
- **IL-03 恢复与迟到结果**：重启只从已提交事件归约有效集，不重放命令/不重发请求、旧 session
  不可控制；请求封存本节点有效指令指纹，结果返回后指纹变化 ⇒ 结果丢弃、显式失败、不进消费者
  （不新增 `result.status` 枚举值）。
- **IL-04 旧语义保持**：旧 `/control` 的会话内语义、命令指纹与幂等/409 语义不变，旧会话指令
  **不会**自动升级成 run 指令；`accepted` / `applied` / `effective` 是三个不同事实。

外加 API 路由/状态码（400/403/404/409/503，GET 损坏审计 422）、只增不改与封存不可覆盖、
单写者锁拒绝、WM 注入（constraint 条目 + 冷存来源，**不新增顶层 input 键**）与预算红线。
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from host import agent_control as C
from host import agent_memory as AM
from host import agent_working_memory as WM
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.context import RunCtx

# 受控 provider / 请求入口沿用既有夹具（只复用夹具，不改既有断言）。
from test_agent_context_memory import call, provider, write_json  # noqa: F401
from test_agent_control import started, until  # noqa: F401

_RUNS = itertools.count(1)


# ---------------------------------------------------------------- 夹具与助手


@pytest.fixture
def ctx(tmp_path):
    root = tmp_path / "workspace"
    run_id = f"RUN-20300105-{next(_RUNS):06d}"
    run = root / "runs" / run_id
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    return RunCtx(run_id, run, "real", "happy", KbSources.from_workspace(root),
                  ProgressLog(tmp_path / "events", run_id))


@pytest.fixture
def other_run(tmp_path):
    """同工作区的**另一个 run**（IL-01「绝不跨 run」的反向对照）。"""
    root = tmp_path / "workspace"
    run_id = f"RUN-20300105-{next(_RUNS):06d}"
    run = root / "runs" / run_id
    run.mkdir(parents=True)
    write_json(run / "view.json", {"baseline": "v0"})
    return RunCtx(run_id, run, "real", "happy", KbSources.from_workspace(root),
                  ProgressLog(tmp_path / "events", run_id))


def payload(root, operation="create", **fields):
    """POST 载荷（create 默认字段齐全；revoke 只带目标 ID）。"""
    data = {"operation": operation, "actor": "human:operator",
            "request_id": "req-1", "expected_instruction_revision": 0}
    if operation in ("create", "supersede"):
        data.update(message="重点核对新增端口", scope="run", target_nodes=["N3"])
    data.update(fields)
    return data


def event_files(root):
    return sorted((Path(root) / "agent_controls" / "run").glob("instruction-*.json"))


def read_event(root, sequence):
    return json.loads(event_files(root)[sequence - 1].read_text())


def one_attempt(ctx, sequence, node="N3"):
    return AM.verify_attempt(ctx.run_dir / "agent_calls" / node / f"attempt-{sequence:06d}")


def request_record(ctx, sequence, node="N3"):
    """只读**已封存请求**（请求在途时 result 还不存在，`verify_attempt` 会判半件）。"""
    folder = ctx.run_dir / "agent_calls" / node / f"attempt-{sequence:06d}"
    data = (folder / "request.json").read_bytes()
    digest = (folder / "request.sha256").read_text().strip()
    assert hashlib.sha256(data).hexdigest() == digest
    return json.loads(data)


def projection(ctx, node="N3", attempt=1):
    return request_record(ctx, attempt, node)["instruction_projection"]


def api_client(monkeypatch, *runs):
    """TestClient + 受控 manager（docs 决定 404 口径；不启动 lifespan）。"""
    from services import api
    docs = {run_id: SimpleNamespace(run_dir=str(run_dir)) for run_id, run_dir in runs}
    manager = SimpleNamespace(docs=docs,
                              _progress=lambda _run_id: SimpleNamespace(read=lambda: []))
    monkeypatch.setattr(api, "_manager", lambda: manager)
    return TestClient(api.app)


# ---------------------------------------------------------------- IL-01 作用域


async def test_attempt_scope_binds_only_the_reserved_attempt(ctx, provider):
    """`attempt` 绑定 Host 预留的下一次明确尝试；该尝试终态即到期，不滚到后续返工。"""
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="attempt", target_nodes=["N3"]))
    assert receipt["status"] == "accepted"
    assert receipt["instruction"]["bound_attempt"] == {"node": "N3", "attempt": 1}

    first = await call(ctx)
    assert first["validation"]["ok"]
    adopted = projection(ctx, attempt=1)["adopted"]
    assert [item["instruction_id"] for item in adopted] == [receipt["instruction"]["id"]]
    assert adopted[0]["event_revision"] == 1
    assert adopted[0]["sealed_ref"] == "agent_controls/run/instruction-000001.json"
    assert adopted[0]["message"] == "重点核对新增端口"

    second = await call(ctx)
    assert second["validation"]["ok"]
    later = projection(ctx, attempt=2)
    assert later["adopted"] == []
    assert [(item["instruction_id"], item["reason"]) for item in later["not_adopted"]] == [
        (receipt["instruction"]["id"], "bound_to_other_attempt")]

    entry = C.instructions_view(ctx.run_dir)["instructions"][0]
    assert entry["state"] == "expired"
    assert entry["applied_attempts"] == [{"node": "N3", "attempt": 1}]
    assert entry["effective"] is False


def test_node_rework_scope_stays_on_the_same_node(ctx):
    """`node_rework` = 同 run 同节点后续尝试；不落到别的节点，也绝不跨 run。"""
    receipt = C.submit(ctx.run_dir, payload(
        ctx.run_dir, scope="node_rework", target_nodes=["N3"]))
    for attempt in (1, 2, 3):
        proj = C.effective(ctx.run_dir, "N3", attempt=attempt)
        assert [item["instruction_id"] for item in proj["adopted"]] == [
            receipt["instruction"]["id"]]
    other = C.effective(ctx.run_dir, "N6", attempt=1)
    assert other["adopted"] == []
    assert [(item["instruction_id"], item["reason"]) for item in other["not_adopted"]] == [
        (receipt["instruction"]["id"], "node_not_in_target_nodes")]
    assert C.effective(ctx.run_dir, "N3", attempt=1)["effective_sha256"] != other["effective_sha256"]


def test_run_scope_uses_the_target_node_whitelist(ctx):
    """`run` 作用域 = 同 run 指定节点白名单；白名单外的节点显式登记未采用原因。"""
    receipt = C.submit(ctx.run_dir, payload(
        ctx.run_dir, scope="run", target_nodes=["N6", "N8"]))
    for node in ("N6", "N8"):
        proj = C.effective(ctx.run_dir, node, attempt=1)
        assert [item["instruction_id"] for item in proj["adopted"]] == [
            receipt["instruction"]["id"]]
    outside = C.effective(ctx.run_dir, "N3", attempt=1)
    assert outside["adopted"] == []
    assert outside["not_adopted"][0]["reason"] == "node_not_in_target_nodes"
    view = C.instructions_view(ctx.run_dir)
    assert set(view["effective"]) == {"N6", "N8"}
    assert view["effective"]["N6"]["instruction_ids"] == [receipt["instruction"]["id"]]


def test_instructions_never_cross_runs(ctx, other_run):
    """绝不跨 run：另一个 run 读到空集；把事件复制过去 ⇒ 身份不符显式失败。"""
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"]))
    assert C.effective(other_run.run_dir, "N3")["adopted"] == []
    assert C.effective(other_run.run_dir, "N3")["revision"] == 0

    target = other_run.run_dir / "agent_controls" / "run"
    target.mkdir(parents=True)
    source = event_files(ctx.run_dir)[0]
    (target / source.name).write_bytes(source.read_bytes())
    (target / source.with_suffix(".sha256").name).write_bytes(
        source.with_suffix(".sha256").read_bytes())
    with pytest.raises(ValueError, match="run|身份"):
        C.instructions_view(other_run.run_dir)
    assert receipt["instruction"]["id"]


def test_declared_resource_dependency_expires_the_instruction(ctx):
    """显式依赖变化 ⇒ 到期；未知依赖类型与缺件在写前拒绝（不猜）。"""
    artifact = ctx.run_dir / "artifact.txt"
    artifact.write_text("v1", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    receipt = C.submit(ctx.run_dir, payload(
        ctx.run_dir, dependencies=["resource:artifact.txt"]))
    assert read_event(ctx.run_dir, 1)["instruction"]["dependency_versions"] == {
        "resource:artifact.txt": digest}
    proj = C.effective(ctx.run_dir, "N3", attempt=1)
    assert [item["instruction_id"] for item in proj["adopted"]] == [receipt["instruction"]["id"]]

    artifact.write_text("v2", encoding="utf-8")
    expired = C.effective(ctx.run_dir, "N3", attempt=1)
    assert expired["adopted"] == []
    assert [(item["instruction_id"], item["reason"]) for item in expired["not_adopted"]] == [
        (receipt["instruction"]["id"], "dependency_changed")]
    entry = C.instructions_view(ctx.run_dir)["instructions"][0]
    assert entry["state"] == "expired" and entry["reason"] == "dependency_changed"

    with pytest.raises(ValueError, match="依赖"):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, request_id="req-2", expected_instruction_revision=1,
            dependencies=["unknown:something"]))
    with pytest.raises(ValueError, match="依赖"):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, request_id="req-3", expected_instruction_revision=1,
            dependencies=["resource:missing.txt"]))
    assert len(event_files(ctx.run_dir)) == 1


# ---------------------------------------------------------------- IL-02 原子/幂等/CAS


async def test_supersede_is_one_atomic_event_and_revoke_never_revives(ctx):
    """supersede 单事件原子（旧失效 + 新条目）；revoke/supersede 目标必须当前有效。"""
    first = C.submit(ctx.run_dir, payload(ctx.run_dir))
    old = first["instruction"]["id"]
    second = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="supersede", request_id="req-2",
        expected_instruction_revision=1, target_instruction_id=old,
        message="改为核对端口位宽", scope="run", target_nodes=["N3"]))
    new = second["instruction"]["id"]
    assert new != old and second["instruction"]["version"] == 2
    assert second["replaces_instruction_id"] == old

    events = event_files(ctx.run_dir)
    assert len(events) == 2, "supersede 必须是一个原子事件，不能拆成两次写入"
    raw = read_event(ctx.run_dir, 2)
    assert raw["operation"] == "supersede"
    assert raw["replaces_instruction_id"] == old
    assert raw["instruction"]["id"] == new

    view = C.instructions_view(ctx.run_dir)
    states = {item["instruction_id"]: item["state"] for item in view["instructions"]}
    assert states == {old: "superseded", new: "valid"}
    assert view["revision"] == 2
    assert [item["instruction_id"] for item in C.effective(
        ctx.run_dir, "N3", attempt=1)["adopted"]] == [new]

    third = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="revoke", request_id="req-3",
        expected_instruction_revision=2, target_instruction_id=new))
    assert third["instruction"] is None
    view = C.instructions_view(ctx.run_dir)
    states = {item["instruction_id"]: item["state"] for item in view["instructions"]}
    assert states == {old: "superseded", new: "revoked"}, "撤销新条目不得复活被替代的旧条目"
    assert C.effective(ctx.run_dir, "N3", attempt=1)["adopted"] == []

    with pytest.raises(C.ControlConflict):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, operation="revoke", request_id="req-stale-revoke",
            expected_instruction_revision=3, target_instruction_id=old))
    with pytest.raises(C.ControlConflict):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, operation="supersede", request_id="req-stale-supersede",
            expected_instruction_revision=3, target_instruction_id=old,
            message="重放已失效目标", scope="run", target_nodes=["N3"]))
    with pytest.raises(C.ControlConflict):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, operation="revoke", request_id="req-4",
            expected_instruction_revision=3, target_instruction_id="ins-999999"))
    assert len(event_files(ctx.run_dir)) == 3


async def test_request_id_idempotency_and_conflicting_payload(ctx):
    """同 request_id 同载荷 ⇒ 原回执；同 request_id 不同载荷 ⇒ 冲突（写前拒绝）。"""
    data = payload(ctx.run_dir)
    first = C.submit(ctx.run_dir, data)
    assert C.submit(ctx.run_dir, copy.deepcopy(data)) == first
    assert len(event_files(ctx.run_dir)) == 1, "幂等重放不得追加事件"

    with pytest.raises(C.ControlConflict, match="request_id"):
        C.submit(ctx.run_dir, {**data, "message": "换个说法"})
    with pytest.raises(C.ControlConflict, match="request_id"):
        C.submit(ctx.run_dir, {**data, "scope": "node_rework"})
    with pytest.raises(C.ControlConflict, match="request_id"):
        C.submit(ctx.run_dir, {**data, "target_nodes": ["N3", "N6"]})
    assert len(event_files(ctx.run_dir)) == 1
    assert C.instructions_view(ctx.run_dir)["revision"] == 1
    # 幂等只比对声明的载荷：依赖资源在两次重放之间变化不改变「同 request_id 同声明」的语义
    (ctx.run_dir / "artifact.txt").write_text("v1", encoding="utf-8")
    dependency_payload = payload(ctx.run_dir, request_id="req-dependency",
                                 expected_instruction_revision=1,
                                 dependencies=["resource:artifact.txt"])
    first_dependency = C.submit(ctx.run_dir, dependency_payload)
    (ctx.run_dir / "artifact.txt").write_text("v2", encoding="utf-8")
    assert C.submit(ctx.run_dir, dependency_payload) == first_dependency
    assert len(event_files(ctx.run_dir)) == 2


async def test_cas_revision_mismatch_is_write_before_reject(ctx):
    """CAS：`expected_instruction_revision` = 已提交事件数；不符 ⇒ 冲突且零写入。"""
    with pytest.raises(C.ControlConflict, match="revision|revision"):
        C.submit(ctx.run_dir, payload(ctx.run_dir, expected_instruction_revision=3))
    assert event_files(ctx.run_dir) == []
    assert C.instructions_view(ctx.run_dir)["revision"] == 0

    C.submit(ctx.run_dir, payload(ctx.run_dir))
    with pytest.raises(C.ControlConflict):
        C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-2",
                                      expected_instruction_revision=0))
    assert len(event_files(ctx.run_dir)) == 1


@pytest.mark.parametrize("mutation,error", [
    ({"unknown_field": 1}, ValueError),
    ({"operation": "apply"}, ValueError),
    ({"scope": "global"}, ValueError),
    ({"message": ""}, ValueError),
    ({"message": "   "}, ValueError),
    ({"message": "x" * 4001}, ValueError),
    ({"target_nodes": []}, ValueError),
    ({"target_nodes": ["N0"]}, ValueError),
    ({"target_nodes": ["N3", "N6"], "scope": "attempt"}, ValueError),
    ({"target_nodes": ["N3", "N6"], "scope": "node_rework"}, ValueError),
    ({"actor": "agent:auto"}, PermissionError),
    ({"actor": "human:"}, PermissionError),
    ({"request_id": "bad id!"}, ValueError),
    ({"expected_instruction_revision": -1}, ValueError),
    ({"expected_instruction_revision": "1"}, ValueError),
    ({"dependencies": ["unknown:x"]}, ValueError),
])
def test_write_before_rejections_cover_fields_enums_actor_and_dependencies(ctx, mutation, error):
    data = payload(ctx.run_dir)
    data.update(mutation)
    with pytest.raises(error):
        C.submit(ctx.run_dir, data)
    assert event_files(ctx.run_dir) == []
    assert not (ctx.run_dir / "agent_controls" / "run").exists() or not event_files(ctx.run_dir)


@pytest.mark.parametrize("operation,fields", [
    ("revoke", {}),
    ("revoke", {"message": "撤销时不许带内容"}),
    ("create", {"target_instruction_id": "ins-000001"}),
])
def test_operation_specific_fields_are_strict(ctx, operation, fields):
    """create/revoke/supersede 的字段集合严格：多带/少带都在写前拒绝。"""
    with pytest.raises(ValueError):
        C.submit(ctx.run_dir, payload(ctx.run_dir, operation=operation, **fields))
    assert event_files(ctx.run_dir) == []


# ---------------------------------------------------------------- IL-03 恢复/迟到结果


async def test_restart_rebuilds_effective_set_without_replaying(ctx):
    """重启只从已提交事件归约有效集；不重放命令、不重发请求、不复活旧 session。"""
    first = C.submit(ctx.run_dir, payload(ctx.run_dir))
    second = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="supersede", request_id="req-2",
        expected_instruction_revision=1, target_instruction_id=first["instruction"]["id"],
        message="换成新约束", scope="run", target_nodes=["N3"]))
    files = [path.name for path in event_files(ctx.run_dir)]
    contents = [path.read_bytes() for path in event_files(ctx.run_dir)]

    C._ACTIVE.clear()  # 进程内状态为零：只剩盘上事件
    view = C.instructions_view(ctx.run_dir)
    assert [item["instruction_id"] for item in view["instructions"] if item["state"] == "valid"] == [
        second["instruction"]["id"]]
    assert [item["instruction_id"] for item in C.effective(
        ctx.run_dir, "N3", attempt=1)["adopted"]] == [second["instruction"]["id"]]

    assert [path.name for path in event_files(ctx.run_dir)] == files, "恢复不得追加指令事件"
    assert [path.read_bytes() for path in event_files(ctx.run_dir)] == contents
    assert not (ctx.run_dir / "agent_controls" / "N3").exists(), "恢复不得复活旧控制 session"
    assert not (ctx.run_dir / "agent_calls" / "N3").exists(), "恢复不得重发请求"


async def test_late_result_is_discarded_when_this_node_effective_set_changes(ctx, provider):
    """请求封存本节点指纹；返回后指纹变化 ⇒ 结果丢弃、显式失败、不进消费者。"""
    task = await started(ctx, provider)
    baseline = projection(ctx, attempt=1)
    assert baseline["adopted"] == [] and baseline["not_adopted"] == []
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"]))
    provider["wait"].set()
    with pytest.raises(RuntimeError, match="指令|丢弃"):
        await task
    C.read_view(ctx.run_dir, "N3")  # live 已注销、审计可读

    record = one_attempt(ctx, 1)
    result = record["result"]
    assert result["status"] == "error", "不新增 result.status 枚举值"
    assert result["acceptance"]["accepted"] is False
    assert result["acceptance"]["reason"] == "effective_instruction_sha256_changed"
    assert result["acceptance"]["current_instruction_revision"] == 1
    # 接受门留痕可追溯：请求时的指纹/目录 revision 与丢弃时的当前值都在记录里
    assert (result["acceptance"]["requested_effective_sha256"]
            == record["request"]["instruction_projection"]["effective_sha256"])
    assert result["acceptance"]["current_effective_sha256"] != (
        result["acceptance"]["requested_effective_sha256"])
    assert record["request"]["instruction_revision"] == 0
    assert receipt["instruction"]["id"] not in json.dumps(
        record["request"]["instruction_projection"]), "结果丢弃：该指令不得被记成已采用"
    assert C.read_view(ctx.run_dir, "N3")["live"] is None


async def test_other_node_change_does_not_cancel_inflight_result(ctx, provider):
    """改别的节点指令不得取消本节点结果（指纹只覆盖适用条目）。"""
    other = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N6"]))
    task = await started(ctx, provider)
    assert projection(ctx, attempt=1)["not_adopted"] == [
        {"instruction_id": other["instruction"]["id"], "version": 1,
         "reason": "node_not_in_target_nodes"}]
    superseded = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="supersede", request_id="req-2",
        expected_instruction_revision=1, target_instruction_id=other["instruction"]["id"],
        message="新的 N6 指令", scope="run", target_nodes=["N6"]))
    provider["wait"].set()
    result = await task
    assert result["validation"]["ok"]
    assert one_attempt(ctx, 1)["result"]["status"] == "validated"
    assert [item["instruction_id"] for item in C.effective(
        ctx.run_dir, "N6", attempt=1)["adopted"]] == [superseded["instruction"]["id"]]


async def test_restart_does_not_reissue_the_last_request(ctx, provider):
    """恢复不自动启动请求：归约后没有新的 attempt/命令事件。"""
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"]))
    await call(ctx)
    assert len(list((ctx.run_dir / "agent_calls" / "N3").iterdir())) == 1
    C._ACTIVE.clear()
    C.instructions_view(ctx.run_dir)
    C.effective(ctx.run_dir, "N3", attempt=2)
    assert len(list((ctx.run_dir / "agent_calls" / "N3").iterdir())) == 1
    assert one_attempt(ctx, 1)["request"]["instruction_projection"]["adopted"][0][
        "instruction_id"] == receipt["instruction"]["id"]


# ---------------------------------------------------------------- IL-04 旧语义保持


async def test_legacy_control_semantics_unchanged_and_not_upgraded(ctx, provider):
    """旧 `/control` 的会话内指令不自动升级成 run 指令；回执字段保持。"""
    task = await started(ctx, provider)
    live = C.read_view(ctx.run_dir, "N3")["live"]
    data = {"action": "steer", "actor": "human:reviewer", "request_id": "request-1",
            "session_id": live["session_id"], "expected_revision": live["revision"],
            "message": "重点核对新增端口"}
    receipt = C.command(ctx.run_dir, "N3", data)
    assert receipt["status"] == "accepted" and receipt["signature"]
    assert C.command(ctx.run_dir, "N3", copy.deepcopy(data)) == receipt  # 幂等查询保持
    with pytest.raises(C.ControlConflict):
        C.command(ctx.run_dir, "N3", {**data, "message": "不同内容"})
    # 旧路径只写 session 事件：不建 run 子目录、不进 IL 有效集
    assert not (ctx.run_dir / "agent_controls" / "run").exists()
    assert C.instructions_view(ctx.run_dir)["instructions"] == []
    await until(lambda: len(provider["inputs"]) == 2)
    assert C.effective(ctx.run_dir, "N3", attempt=2)["adopted"] == []
    provider["wait"].set()
    result = await task
    assert result["validation"]["ok"]
    assert C.effective(ctx.run_dir, "N3", attempt=2)["adopted"] == [], "会话指令不得留在 run 作用域"
    assert C.read_view(ctx.run_dir, "N3")["live"] is None
    assert not (ctx.run_dir / "agent_controls" / "run").exists()


async def test_accepted_applied_effective_are_distinct_facts(ctx, provider):
    """回执=accepted；请求实际采用=applied；当前有效集成员=effective，三者分开投影。"""
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="attempt", target_nodes=["N3"]))
    assert receipt["status"] == "accepted"
    assert "applied" not in receipt and "effective" not in receipt, (
        "回执不得把 accepted 当成 applied/effective")
    entry = C.instructions_view(ctx.run_dir)["instructions"][0]
    assert entry["accepted"] is True
    assert entry["applied_attempts"] == []
    assert entry["state"] == "valid" and entry["effective"] is True

    await call(ctx)
    entry = C.instructions_view(ctx.run_dir)["instructions"][0]
    assert entry["accepted"] is True
    assert entry["applied_attempts"] == [{"node": "N3", "attempt": 1}]
    assert entry["state"] == "expired" and entry["effective"] is False


# ---------------------------------------------------------------- 封存/只增不改


async def test_instruction_events_are_sealed_and_append_only(ctx):
    """事件走 `AM.seal_record`（数据→校验和）、只增不改、不可覆盖；目录 revision = 事件数。"""
    first = C.submit(ctx.run_dir, payload(ctx.run_dir))
    files = event_files(ctx.run_dir)
    assert [path.name for path in files] == ["instruction-000001.json"]
    data_file = files[0]
    assert data_file.with_suffix(".sha256").is_file()
    raw = json.loads(data_file.read_text())
    assert raw["format_version"] == 2
    assert raw["run_id"] == ctx.run_id
    assert raw["revision"] == 1
    assert raw["operation"] == "create"
    assert raw["actor"] == "human:operator"
    assert raw["request_id"] == "req-1"
    assert raw["instruction"]["scope"] == "run"
    assert raw["instruction"]["target_nodes"] == ["N3"]
    assert raw["instruction"]["id"] == first["instruction"]["id"]
    assert data_file.stat().st_mode & 0o777 == 0o400, "封存记录不可写"

    before = data_file.read_bytes()
    C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-2",
                                  expected_instruction_revision=1))
    assert [path.name for path in event_files(ctx.run_dir)] == [
        "instruction-000001.json", "instruction-000002.json"]
    assert data_file.read_bytes() == before, "旧事件零改动"
    with pytest.raises(OSError):
        AM.seal_record(data_file, raw)  # 同名封存不可覆盖
    assert C.instructions_view(ctx.run_dir)["revision"] == 2


@pytest.mark.parametrize("fault", ["tamper", "incomplete", "gap"])
def test_corrupt_instruction_audit_fails_explicitly(ctx, fault, monkeypatch):
    """审计损坏 ⇒ 显式失败（不悄悄清空指令继续执行）；GET 侧映射 422。"""
    C.submit(ctx.run_dir, payload(ctx.run_dir))
    C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-2",
                                  expected_instruction_revision=1))
    files = event_files(ctx.run_dir)
    if fault == "tamper":
        files[0].chmod(0o600)
        files[0].write_text("{}")
        match = "checksum"
    elif fault == "incomplete":
        files[0].with_suffix(".sha256").unlink()
        match = "不完整|incomplete|checksum"
    else:
        files[0].chmod(0o600)
        files[0].unlink()
        files[0].with_suffix(".sha256").unlink()
        match = "连续|gap|缺失"
    with pytest.raises(ValueError, match=match):
        C.instructions_view(ctx.run_dir)
    with pytest.raises(C.ControlConflict, match=match):  # 无法确定 revision ⇒ 拒绝覆盖未知状态
        C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-3",
                                      expected_instruction_revision=2))
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"
    assert client.get(url).status_code == 422
    assert client.post(url, json=payload(ctx.run_dir)).status_code == 409


def test_single_writer_lock_rejects_concurrently(ctx):
    """单写者：锁被占用 ⇒ 显式拒绝（`ControlConflict`），零写入并留诊断。"""
    with C.write_lock(ctx.run_dir):
        with pytest.raises(C.ControlConflict, match="锁|单写者"):
            C.submit(ctx.run_dir, payload(ctx.run_dir))
        assert event_files(ctx.run_dir) == []
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir))  # 释放后可写
    assert receipt["status"] == "accepted"
    assert len(event_files(ctx.run_dir)) == 1


# ---------------------------------------------------------------- WM 注入与预算


async def test_effective_instructions_enter_working_memory_without_new_input_keys(ctx, provider):
    """注入走 WM 的 `constraint` 条目（value + 封存事件来源），不新增顶层 input 键。"""
    baseline = await call(ctx)
    before = provider["inputs"][-1]
    receipt = C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"]))
    assert baseline["validation"]["ok"]
    after_result = await call(ctx)
    assert after_result["validation"]["ok"]
    sent = provider["inputs"][-1]

    assert set(sent) == set(before), "不得新增顶层 input 键"
    directives = [entry for entry in sent["working_memory"]["entries"]
                  if entry["kind"] == "constraint"
                  and entry["entry_id"].startswith("constraint:N3:directive[")]
    assert len(directives) == 1
    directive = directives[0]
    assert directive["value"] == {"instruction_id": receipt["instruction"]["id"],
                                  "version": 1, "scope": "run",
                                  "message": "重点核对新增端口"}
    assert "input_ref" not in directive
    assert directive["source_keys"] == ["instruction_event.000001"]

    record = request_record(ctx, 2)
    assert record["instruction_revision"] == 1
    assert record["instruction_projection"]["adopted"][0]["instruction_id"] == [
        receipt["instruction"]["id"]][0]
    source = record["working_memory_source_map"]["sources"]["instruction_event.000001"]
    assert source["origin"] == "agent_controls/run"
    assert source["sealed_ref"] == "agent_controls/run/instruction-000001.json"
    assert source["instruction_id"] == receipt["instruction"]["id"]
    assert source["version"] == 1
    assert "instruction_projection" not in sent, "投影只冷存 request 顶层"


async def test_instruction_material_that_breaks_budget_fails_before_model_call(ctx, provider,
                                                                               monkeypatch):
    """预算红线：指令材料使请求超限 ⇒ 调用前失败、不截断、不调用模型（口径仍唯一）。"""
    first = await call(ctx)
    assert first["validation"]["ok"]
    record = one_attempt(ctx, 1)["request"]
    measured = AM.measure_budget(record["input"],
                                 {key: record[key] for key in ("info", "instruct", "schema")})
    C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"],
                                  message="约束" * 500))
    monkeypatch.setattr(AM, "MAX_CONTEXT_BYTES", measured["used_bytes"])
    with pytest.raises(RuntimeError, match="budget|预算"):
        await call(ctx)
    assert len(provider["inputs"]) == 1, "超预算必须在模型调用之前失败"


@pytest.mark.parametrize("directive", [
    # 缺 ID
    {"version": 1, "message": "m", "scope": "run", "event_revision": 1,
     "sealed_ref": "agent_controls/run/instruction-000001.json"},
    # 空 message
    {"instruction_id": "ins-000001", "version": 1, "message": "   ", "scope": "run",
     "event_revision": 1, "sealed_ref": "agent_controls/run/instruction-000001.json"},
    # 缺封存事件 revision / 缺来源引用
    {"instruction_id": "ins-000001", "version": 1, "message": "m", "scope": "run"},
    {"instruction_id": "ins-000001", "version": 1, "message": "m", "scope": "run",
     "event_revision": 1},
    # 版本非法
    {"instruction_id": "ins-000001", "version": 0, "message": "m", "scope": "run",
     "event_revision": 1, "sealed_ref": "agent_controls/run/instruction-000001.json"},
])
def test_working_memory_rejects_malformed_directives(ctx, directive):
    with pytest.raises(ValueError):
        WM.build(ctx, "N3", {"run_id": ctx.run_id, "diffs": []}, directives=[directive])


def test_working_memory_accepts_directive_and_counts_it_as_mandatory(ctx):
    value = {"run_id": ctx.run_id, "diffs": []}
    without = WM.build(ctx, "N3", copy.deepcopy(value))
    withdirective = WM.build(ctx, "N3", copy.deepcopy(value), directives=[{
        "instruction_id": "ins-000001", "version": 1, "message": "重点核对新增端口",
        "scope": "run", "event_revision": 1,
        "sealed_ref": "agent_controls/run/instruction-000001.json"}])
    assert without.payload["snapshot_sha256"] != withdirective.payload["snapshot_sha256"]
    assert withdirective.mandatory_bytes > without.mandatory_bytes
    entry = next(item for item in withdirective.payload["entries"]
                 if item["kind"] == "constraint")
    assert entry["value"]["message"] == "重点核对新增端口"
    assert withdirective.source_map["sources"]["instruction_event.000001"]["sealed_ref"].endswith(
        "instruction-000001.json")


# ---------------------------------------------------------------- API 路由与状态码


def test_api_instruction_endpoints_and_status_codes(monkeypatch, ctx):
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"

    empty = client.get(url)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"run_id": ctx.run_id, "revision": 0,
                            "instructions": [], "effective": {}}
    assert client.get("/api/runs/missing/instructions").status_code == 404
    assert client.post("/api/runs/missing/instructions", json=payload(ctx.run_dir)).status_code == 404

    created = client.post(url, json=payload(ctx.run_dir))
    assert created.status_code == 200, created.text
    receipt = created.json()
    assert receipt["status"] == "accepted" and receipt["instruction_revision"] == 1
    assert receipt["instruction"]["scope"] == "run"

    bad = [
        ({**payload(ctx.run_dir), "unknown": 1}, 400),
        ({**payload(ctx.run_dir), "message": ""}, 400),
        ({**payload(ctx.run_dir), "scope": "global"}, 400),
        ({**payload(ctx.run_dir), "target_nodes": ["N0"]}, 400),
        ({**payload(ctx.run_dir), "actor": "agent:auto"}, 403),
        ({**payload(ctx.run_dir, request_id="req-2"), "expected_instruction_revision": 0}, 409),
        ({**payload(ctx.run_dir), "expected_instruction_revision": 1,
          "message": "不同内容"}, 409),
        (payload(ctx.run_dir, "revoke", request_id="req-4",
                 expected_instruction_revision=1,
                 target_instruction_id="ins-999999"), 409),
    ]
    for body, status in bad:
        response = client.post(url, json=body)
        assert response.status_code == status, (body, response.text)
    assert len(event_files(ctx.run_dir)) == 1, "被拒绝的请求不得写事件"

    view = client.get(url).json()
    assert view["revision"] == 1
    assert view["instructions"][0]["state"] == "valid"
    assert view["instructions"][0]["accepted"] is True
    assert view["instructions"][0]["applied_attempts"] == []
    assert view["effective"]["N3"]["instruction_ids"] == [receipt["instruction"]["id"]]


def test_api_instruction_read_errors_are_explicit(monkeypatch, ctx):
    """GET 侧损坏审计 ⇒ 422（与既有 agents 视图同口径），空集合与读取失败不同状态。"""
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"
    assert client.get(url).status_code == 200
    C.submit(ctx.run_dir, payload(ctx.run_dir))
    path = event_files(ctx.run_dir)[0]
    path.chmod(0o600)
    path.write_text("{}")
    corrupt = client.get(url)
    assert corrupt.status_code == 422, corrupt.text
    assert "error" in corrupt.json()["detail"]


def test_api_audit_write_failure_returns_503(monkeypatch, ctx):
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"

    def fail(path, value):
        raise OSError("audit unavailable")

    monkeypatch.setattr(C, "_seal", fail)
    response = client.post(url, json=payload(ctx.run_dir))
    assert response.status_code == 503, response.text
    assert event_files(ctx.run_dir) == []


def test_api_lock_conflict_returns_409_and_then_succeeds(monkeypatch, ctx):
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"
    with C.write_lock(ctx.run_dir):
        blocked = client.post(url, json=payload(ctx.run_dir))
        assert blocked.status_code == 409, blocked.text
        assert "锁" in blocked.json()["detail"]["error"] or "单写者" in blocked.json()["detail"]["error"]
    assert event_files(ctx.run_dir) == []
    assert client.post(url, json=payload(ctx.run_dir)).status_code == 200
    assert len(event_files(ctx.run_dir)) == 1


def test_api_legacy_control_route_and_instruction_route_coexist(monkeypatch, ctx):
    """旧 `/control` 路由行为不变（404/409 口径），新端点不复用节点参数。"""
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    assert client.get(f"/api/runs/{ctx.run_id}/agents/N0").status_code == 404
    assert client.get(f"/api/runs/{ctx.run_id}/agents/N3").status_code == 200
    stale = client.post(f"/api/runs/{ctx.run_id}/agents/N3/control", json={
        "action": "pause", "actor": "human:reviewer", "request_id": "stale",
        "session_id": "stale", "expected_revision": 1})
    assert stale.status_code == 409
    assert not (ctx.run_dir / "agent_controls" / "run").exists()


# ---------------------------------------------------------------- 复核修复（2026-10-28 独立复核 1×P1 + 4×P2）


async def test_idempotency_fingerprint_includes_target_instruction_id(ctx):
    """P1-1：`target_instruction_id` 必须参与命令指纹 —— 同 request_id 换 target 不得返回旧回执。"""
    first = C.submit(ctx.run_dir, payload(ctx.run_dir))
    second = C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-2",
                                           expected_instruction_revision=1))
    assert first["instruction"]["id"] != second["instruction"]["id"]
    revoke = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="revoke", request_id="req-revoke",
        expected_instruction_revision=2, target_instruction_id=first["instruction"]["id"]))
    assert revoke["replaces_instruction_id"] == first["instruction"]["id"]

    # 同 request_id + 同 expected revision，只是换 target ⇒ 冲突（不能静默返回上一条回执）
    with pytest.raises(C.ControlConflict, match="request_id"):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, operation="revoke", request_id="req-revoke",
            expected_instruction_revision=2,
            target_instruction_id=second["instruction"]["id"]))
    assert len(event_files(ctx.run_dir)) == 3, "换 target 的重放不得写事件"
    states = {item["instruction_id"]: item["state"]
              for item in C.instructions_view(ctx.run_dir)["instructions"]}
    assert states[first["instruction"]["id"]] == "revoked"
    assert states[second["instruction"]["id"]] == "valid", "未被撤销的目标必须仍有效"

    # 同 request_id + 同 target 重放 ⇒ 原回执、事件数不变
    replay = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="revoke", request_id="req-revoke",
        expected_instruction_revision=2, target_instruction_id=first["instruction"]["id"]))
    assert replay == revoke
    assert len(event_files(ctx.run_dir)) == 3

    # supersede 同 request_id + 同替代内容，换 target 同样必须冲突
    third = C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-3",
                                          expected_instruction_revision=3))
    fourth = C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-4",
                                           expected_instruction_revision=4))
    supersede = C.submit(ctx.run_dir, payload(
        ctx.run_dir, operation="supersede", request_id="req-supersede",
        expected_instruction_revision=5, target_instruction_id=third["instruction"]["id"],
        message="统一替代内容"))
    with pytest.raises(C.ControlConflict, match="request_id"):
        C.submit(ctx.run_dir, payload(
            ctx.run_dir, operation="supersede", request_id="req-supersede",
            expected_instruction_revision=5,
            target_instruction_id=fourth["instruction"]["id"], message="统一替代内容"))
    assert supersede["instruction"]["version"] == 2
    assert len(event_files(ctx.run_dir)) == 6


def test_api_conflicts_when_same_request_id_targets_another_instruction(monkeypatch, ctx):
    """P1-1（API 层）：换 target 的同 request_id 重放 ⇒ 409，且不得静默撤销/替代别的指令。"""
    client = api_client(monkeypatch, (ctx.run_id, ctx.run_dir))
    url = f"/api/runs/{ctx.run_id}/instructions"
    first = C.submit(ctx.run_dir, payload(ctx.run_dir))
    second = C.submit(ctx.run_dir, payload(ctx.run_dir, request_id="req-2",
                                           expected_instruction_revision=1))
    assert client.post(url, json=payload(
        ctx.run_dir, operation="revoke", request_id="req-revoke",
        expected_instruction_revision=2,
        target_instruction_id=first["instruction"]["id"])).status_code == 200
    conflict = client.post(url, json=payload(
        ctx.run_dir, operation="revoke", request_id="req-revoke",
        expected_instruction_revision=2,
        target_instruction_id=second["instruction"]["id"]))
    assert conflict.status_code == 409, conflict.text
    view = client.get(url).json()
    states = {item["instruction_id"]: item["state"] for item in view["instructions"]}
    assert states[second["instruction"]["id"]] == "valid"
    assert view["revision"] == 3


def test_next_attempt_uses_first_free_slot_like_am_attempt(ctx):
    """P2-2：`next_attempt` 与 `AM.Attempt` 同一「首个空位」算法（不是 max+1）。"""
    directory = ctx.run_dir / "agent_calls" / "N3"
    (directory / "attempt-000001").mkdir(parents=True)
    (directory / "attempt-000003").mkdir()
    assert C.next_attempt(ctx.run_dir, "N3") == 2
    attempt = AM.Attempt(ctx, "N3", {"input": {}})
    assert attempt.identity["attempt"] == 2, "同一算法的直接证据：AM.Attempt 也落在 2"


async def test_reserved_attempt_mismatch_seals_error_result(ctx, provider, monkeypatch):
    """P2-2：预留序号与实际 attempt 不一致 ⇒ 先封存 `error` 结果再显式失败（不留半件）。"""
    monkeypatch.setattr(C, "next_attempt", lambda *args, **kwargs: 99)
    with pytest.raises(RuntimeError, match="尝试|序号"):
        await call(ctx)
    record = AM.verify_attempt(ctx.run_dir / "agent_calls" / "N3" / "attempt-000001")
    assert record["result"]["status"] == "error", "不得留下只有 request 的 incomplete 记录"
    assert "99" in record["result"]["error"] or "尝试" in record["result"]["error"]
    assert record["request"]["instruction_projection"]["effective_sha256"]


async def test_transient_half_published_event_is_read_after_one_retry(ctx, monkeypatch):
    """P2-7：data 在、`.sha256` 未落盘的瞬时窗口 ⇒ 有界单次重试后读取成功。"""
    C.submit(ctx.run_dir, payload(ctx.run_dir))
    real = C._read
    calls = {"n": 0}

    def flaky(root, path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise FileNotFoundError(path.name)
        return real(root, path)

    monkeypatch.setattr(C, "_read", flaky)
    view = C.instructions_view(ctx.run_dir)
    assert calls["n"] == 2, "必须恰有一次有界重试"
    assert view["revision"] == 1 and view["instructions"][0]["state"] == "valid"


def test_permanent_incomplete_or_tampered_event_fails_explicitly(ctx, monkeypatch):
    """P2-7 反向：永久缺件重试一次后显式失败；校验和不匹配（篡改）**不重试**。"""
    C.submit(ctx.run_dir, payload(ctx.run_dir))
    counter = {"n": 0}

    def tampered(root, path):
        counter["n"] += 1
        raise ValueError(f"agent record checksum mismatch: {path.name}")

    monkeypatch.setattr(C, "_read", tampered)
    with pytest.raises(ValueError, match="checksum"):
        C.instructions_view(ctx.run_dir)
    assert counter["n"] == 1, "校验和不匹配是篡改/损坏，不得重试"

    counter["n"] = 0

    def missing(root, path):
        counter["n"] += 1
        raise FileNotFoundError(path.name)

    monkeypatch.setattr(C, "_read", missing)
    with pytest.raises(ValueError, match="不完整|incomplete"):
        C.instructions_view(ctx.run_dir)
    assert counter["n"] == 2, "有界单次重试后仍不完整 ⇒ 显式失败"


DIRECTIVE = {"instruction_id": "ins-000001", "version": 1, "message": "重点核对新增端口",
             "scope": "run", "event_revision": 1,
             "sealed_ref": "agent_controls/run/instruction-000001.json"}


@pytest.mark.parametrize("mutation", [
    {"scope": "global"},
    {"scope": None},
    {"sealed_ref": "../instruction-000001.json"},
    {"sealed_ref": "/etc/instruction-000001.json"},
    {"sealed_ref": "agent_controls/run/instruction-1.json"},
    {"sealed_ref": "agent_controls/elsewhere/instruction-000001.json"},
    {"sealed_ref": "agent_controls/run/instruction-000002.json"},
    {"sealed_ref": ""},
])
def test_working_memory_rejects_bad_directive_scope_or_source(ctx, mutation):
    """P2-8：指令条目的 scope 枚举与封存来源引用（本 run 内、无逃逸）显式校验。"""
    with pytest.raises(ValueError):
        WM.build(ctx, "N3", {"run_id": ctx.run_id, "diffs": []},
                 directives=[{**DIRECTIVE, **mutation}])


def test_working_memory_rejects_symlinked_directive_source(ctx):
    """P2-8：封存来源是符号链接 ⇒ 显式失败（不跟随到 run 外）。"""
    directory = ctx.run_dir / "agent_controls" / "run"
    directory.mkdir(parents=True)
    (directory / "elsewhere.json").write_text("{}", encoding="utf-8")
    (directory / "instruction-000001.json").symlink_to(directory / "elsewhere.json")
    with pytest.raises(ValueError, match="符号链接|越界"):
        WM.build(ctx, "N3", {"run_id": ctx.run_id, "diffs": []}, directives=[DIRECTIVE])


async def test_instruction_lock_lives_outside_the_audit_directory(ctx):
    """P2-9：单写者锁在 run 根（不在 `agent_controls/**`），审计目录只含封存事件。"""
    with C.write_lock(ctx.run_dir):
        lock = ctx.run_dir / ".agent-instruction-writer.lock"
        assert lock.is_file(), "锁文件必须在 run 根"
        assert not (ctx.run_dir / "agent_controls" / "run" / ".lock").exists()
    C.submit(ctx.run_dir, payload(ctx.run_dir))
    audit = ctx.run_dir / "agent_controls" / "run"
    assert sorted(path.name for path in audit.iterdir()) == [
        "instruction-000001.json", "instruction-000001.sha256"], "审计目录只增不改：无锁文件"
    assert (ctx.run_dir / ".agent-instruction-writer.lock").is_file()


async def test_input_digest_excludes_working_memory(ctx, provider):
    """P2-10：`input_digest` 不把机制层派生投影 `working_memory` 计入（S3 之前字节口径）。"""
    first = await call(ctx)
    sent = provider["inputs"][-1]
    assert "working_memory" in sent
    assert "working_memory" not in first["input_digest"]
    assert set(first["input_digest"]) == set(sent) - {"working_memory"}
    C.submit(ctx.run_dir, payload(ctx.run_dir, scope="run", target_nodes=["N3"]))
    second = await call(ctx)
    assert "working_memory" in provider["inputs"][-1]
    assert "working_memory" not in second["input_digest"]
    assert set(second["input_digest"]) == set(first["input_digest"]), (
        "目录里有指令也不得改变展示摘录的键集合")
