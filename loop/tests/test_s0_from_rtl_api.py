"""S0 §9.1/§9.5/§9.6 新端点的 HTTP 契约测试（TDD）。

覆盖（形状见计划 §4「T2 API（形状冻结）」）：
- `POST /api/s0/from-rtl`：200 形状 + 委派参数（default_baseline 恒为原始根、target_parent 唯一）、
  400/403/409/422 错误映射、T1 接口未接入时 501、活跃 run 拒绝；
- `POST /api/s0/{id}/advance`：委派（smoke_case/now）与 404/400/501；
- `POST /api/s0/{id}/activate`：未准出/缺数据根/活跃 run/有 pending ⇒ 409；正常 ⇒ 202 且
  **只写 pending、只调注入钩子**（绝不真起 supervisor、绝不真杀测试进程）；
- `POST /api/env/switch-back`：无 origin / 已在 origin ⇒ 409；从副本 ⇒ 202（目标=origin）；
- `GET /api/s0/copies`：只列 `entry=rtl_folder`，带 exists/bytes/rtl_prefix/status/ready；
- `DELETE /api/s0/{id}/copy?confirm=true`：二次确认守卫、只删副本目录不删记录、
  越界与"当前/最近环境根"拒绝。

S0Store 一律用替身（monkeypatch `services.api._s0_store`）：T1 的 `prepare_from_rtl`/`advance`
接口在 T1 合入前可能还没有，这里固定的是 **API 层契约**，不复制任何派生逻辑。
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from host import env_switch
from host import paths as P
from host.s0 import PreparationFailed, S0Store
from services import api


# ---------------------------------------------------------------- 夹具与替身

@pytest.fixture
def state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把软件 state 根指到临时目录（切换状态/记录投影都落这里，不碰真实 `loop/state`）。"""
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setattr(P, "STATE_DIR", root)
    return root


@pytest.fixture
def client(state_root: Path):
    """带 lifespan 的 TestClient：启动时写 `server.json` 并记录 origin。"""
    with TestClient(api.app) as test_client:
        yield test_client


class FakeStore:
    """最小 S0Store 替身：只记录调用/抛预置错误，不做任何派生。"""

    def __init__(self, root: Path, *, record: dict | None = None,
                 prepare_result: dict | None = None,
                 advance_result: dict | None = None) -> None:
        self.root = Path(root)
        self.record = record
        self.prepare_result = prepare_result
        self.advance_result = advance_result
        self.prepare_calls: list[dict] = []
        self.advance_calls: list[dict] = []
        self.get_calls: list[str] = []
        self.prepare_error: Exception | None = None
        self.advance_error: Exception | None = None
        self.get_error: Exception | None = None

    def prepare_from_rtl(self, payload, *, default_baseline, origin_env_root, target_parent):
        self.prepare_calls.append({
            "payload": payload,
            "default_baseline": default_baseline,
            "origin_env_root": origin_env_root,
            "target_parent": target_parent,
        })
        if self.prepare_error is not None:
            raise self.prepare_error
        return self.prepare_result

    def advance(self, record_id, *, smoke_case=None, now=None):
        self.advance_calls.append({"record_id": record_id, "smoke_case": smoke_case, "now": now})
        if self.advance_error is not None:
            raise self.advance_error
        return self.advance_result

    def get(self, record_id):
        self.get_calls.append(record_id)
        if self.get_error is not None:
            raise self.get_error
        return self.record


class FakeManager:
    """`_manager()` 替身：本文件只用到 `list_runs()`；lifespan 的两个钩子给空实现。"""

    def __init__(self, runs: list[dict]) -> None:
        self.runs = runs

    def list_runs(self) -> list[dict]:
        return list(self.runs)

    async def async_restore_all(self) -> dict:
        return {"restored": []}

    async def stop_watching(self) -> None:
        return None


def _use_store(monkeypatch: pytest.MonkeyPatch, store) -> None:
    monkeypatch.setattr(api, "_s0_store", lambda: store)


def _make_env(root: Path) -> Path:
    for name in ("RTL", "TB", "PKG", "TESTLIB"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _derived_copy(tmp_path: Path) -> Path:
    work = _make_env(tmp_path / "derived")
    (work / "kb" / "baselines").mkdir(parents=True)
    return work


def _write_record(root: Path, record_id: str, **fields) -> Path:
    folder = Path(root) / record_id
    folder.mkdir(parents=True, exist_ok=True)
    row = {"id": record_id, **fields}
    (folder / "record.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return folder


def _ready_record(work: Path, record_id: str = "S0-DERIVED-1") -> dict:
    return {
        "id": record_id,
        "entry": "rtl_folder",
        "status": "prepared",
        "work_env": str(work),
        "ready_for_execution": True,
        "rtl_prefix": "RTL",
        "checks": [
            {"key": key, "status": "passed"}
            for key in ("copy", "rtl", "non_rtl", "ports", "smoke", "baseline")
        ],
    }


def _install_switch_hooks(monkeypatch: pytest.MonkeyPatch) -> dict:
    """spawn/shutdown 必须可注入：本测试绝不真起 supervisor、绝不真杀测试进程。"""
    seen: dict = {"spawned": [], "shutdowns": []}
    monkeypatch.setattr(api, "SPAWN_SUPERVISOR",
                        lambda request: seen["spawned"].append(request) or 4321)
    monkeypatch.setattr(api, "SHUTDOWN_SERVER", lambda: seen["shutdowns"].append(True))
    monkeypatch.setenv("LOOP_SWITCH_EXIT_DELAY", "0")
    return seen


def _wait_until(predicate, *, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _write_pending_raw(**fields) -> Path:
    """手写/历史 pending（默认**没有** supervisor_pid ⇒ 不可活判）。"""
    path = env_switch.pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"status": "pending", "target_env_root": "/tmp/other-env", "record_id": "S0-OLD"}
    row.update(fields)
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------- POST /api/s0/from-rtl

def test_from_rtl_delegates_with_frozen_defaults(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    result = {"id": "S0-FROM-RTL-1", "entry": "rtl_folder", "status": "prepared"}
    store = FakeStore(tmp_path / "records", prepare_result=result)
    _use_store(monkeypatch, store)
    payload = {"rtl_source": str(tmp_path / "RTL"),
               "baseline_version": "RTL@demo+20261030T000000Z"}

    response = client.post("/api/s0/from-rtl", json=payload)

    assert response.status_code == 200, response.text
    assert response.json() == result
    assert len(store.prepare_calls) == 1
    call = store.prepare_calls[0]
    # payload 原样下传（缺省值由 T1 落账，API 不补第二套默认）
    assert call["payload"] == payload
    # baseline 缺省 = 原始根（本进程启动时已记录）
    assert Path(call["default_baseline"]) == Path(P.ENV_ROOT).resolve()
    assert Path(call["origin_env_root"]) == Path(P.ENV_ROOT).resolve()
    # 副本父目录是唯一来源 COPIES_ROOT（= <TOOL_ROOT>/workspaces）
    assert Path(call["target_parent"]) == api.COPIES_ROOT


def test_from_rtl_uses_recorded_origin_as_baseline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    origin = _make_env(tmp_path / "origin-env")
    env_switch.record_origin(origin, workspace_root=tmp_path / "origin-ws")
    store = FakeStore(tmp_path / "records", prepare_result={"id": "S0-X"})
    _use_store(monkeypatch, store)

    with TestClient(api.app) as client:
        response = client.post("/api/s0/from-rtl", json={"rtl_source": str(tmp_path / "RTL")})

    assert response.status_code == 200, response.text
    call = store.prepare_calls[0]
    # 派生源恒为原始根：即使当前进程根不同，也用记录的 origin（决定 17）
    assert Path(call["default_baseline"]) == origin.resolve()
    assert Path(call["origin_env_root"]) == origin.resolve()
    # lifespan 不应把当前进程根覆盖成 origin
    assert Path(env_switch.origin_env_root()) == origin.resolve()


@pytest.mark.parametrize("error,status", [
    (ValueError("目录名必须为 RTL 或 SRC"), 400),
    (PermissionError("路径不在服务端允许根内"), 403),
    (FileExistsError("目标已存在，不会覆盖"), 409),
    (OSError("磁盘写失败"), 422),
])
def test_from_rtl_error_mapping(client: TestClient, tmp_path: Path,
                                monkeypatch: pytest.MonkeyPatch, state_root: Path,
                                error: Exception, status: int) -> None:
    store = FakeStore(tmp_path / "records")
    store.prepare_error = error
    _use_store(monkeypatch, store)

    response = client.post("/api/s0/from-rtl", json={"rtl_source": str(tmp_path / "RTL")})

    assert response.status_code == status, response.text
    assert str(error) in response.json()["detail"]["error"]


def test_from_rtl_preparation_failed_returns_422_with_record(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    record = {"id": "S0-FAILED-1", "status": "failed", "error": "RTL 目录为空"}
    store = FakeStore(tmp_path / "records")
    store.prepare_error = PreparationFailed(record)
    _use_store(monkeypatch, store)

    response = client.post("/api/s0/from-rtl", json={"rtl_source": str(tmp_path / "RTL")})

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["record"] == record
    assert "RTL 目录为空" in detail["error"]


def test_from_rtl_returns_501_when_t1_interface_absent(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    class NoPrepare:
        def __init__(self) -> None:
            self.root = tmp_path / "records"

    _use_store(monkeypatch, NoPrepare())

    response = client.post("/api/s0/from-rtl", json={"rtl_source": str(tmp_path / "RTL")})

    # 不伪造 200、不在 API 层补派生：T1 未接入就显式说不支持
    assert response.status_code == 501, response.text
    assert "prepare_from_rtl" in response.json()["detail"]["error"]


def test_from_rtl_rejects_active_runs(client: TestClient, tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    store = FakeStore(tmp_path / "records", prepare_result={"id": "S0-X"})
    _use_store(monkeypatch, store)
    monkeypatch.setattr(api, "_manager",
                        lambda: FakeManager([{"run_id": "RUN-A", "status": "waiting_gate"}]))

    response = client.post("/api/s0/from-rtl", json={"rtl_source": str(tmp_path / "RTL")})

    assert response.status_code == 409, response.text
    error = response.json()["detail"]["error"]
    assert "RUN-A(waiting_gate)" in error
    # 拒绝发生在任何派生之前
    assert store.prepare_calls == []


# ---------------------------------------------------------------- POST /api/s0/{id}/advance

def test_advance_delegates_smoke_case_and_now(client: TestClient, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch,
                                              state_root: Path) -> None:
    result = {"id": "S0-DERIVED-1", "ready_for_execution": True}
    store = FakeStore(tmp_path / "records", advance_result=result)
    _use_store(monkeypatch, store)

    response = client.post("/api/s0/S0-DERIVED-1/advance",
                           json={"smoke_case": "tc_a.sv", "now": "2026-10-30T01:00:00+08:00"})

    assert response.status_code == 200, response.text
    assert response.json() == result
    assert store.advance_calls == [{"record_id": "S0-DERIVED-1", "smoke_case": "tc_a.sv",
                                    "now": "2026-10-30T01:00:00+08:00"}]


@pytest.mark.parametrize("error,status", [
    (FileNotFoundError("准备记录不存在"), 404),
    (ValueError("ports 未 passed，不能冒烟"), 400),
])
def test_advance_error_mapping(client: TestClient, tmp_path: Path,
                               monkeypatch: pytest.MonkeyPatch, state_root: Path,
                               error: Exception, status: int) -> None:
    store = FakeStore(tmp_path / "records")
    store.advance_error = error
    _use_store(monkeypatch, store)
    response = client.post("/api/s0/S0-DERIVED-1/advance", json={})
    assert response.status_code == status, response.text


def test_advance_returns_501_when_t1_interface_absent(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    class NoAdvance:
        def __init__(self) -> None:
            self.root = tmp_path / "records"

    _use_store(monkeypatch, NoAdvance())
    response = client.post("/api/s0/S0-DERIVED-1/advance", json={})
    assert response.status_code == 501, response.text
    assert "advance" in response.json()["detail"]["error"]


# ---------------------------------------------------------------- POST /api/s0/{id}/activate

def test_activate_rejects_missing_record(client: TestClient, tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    store = FakeStore(tmp_path / "records")
    store.get_error = FileNotFoundError("S0 记录不存在")
    _use_store(monkeypatch, store)
    response = client.post("/api/s0/S0-NOPE/activate", json={})
    assert response.status_code == 404, response.text


def test_activate_rejects_not_ready_record(client: TestClient, tmp_path: Path,
                                           monkeypatch: pytest.MonkeyPatch,
                                           state_root: Path) -> None:
    work = _derived_copy(tmp_path)
    record = _ready_record(work)
    record["ready_for_execution"] = False
    record["checks"][3]["status"] = "waiting"   # ports
    store = FakeStore(tmp_path / "records", record=record)
    _use_store(monkeypatch, store)
    seen = _install_switch_hooks(monkeypatch)

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 409, response.text
    error = response.json()["detail"]["error"]
    assert "未准出" in error and "ports" in error
    assert seen["spawned"] == [] and env_switch.pending() is None


def test_activate_rejects_copy_without_data_root(client: TestClient, tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch,
                                                 state_root: Path) -> None:
    work = _make_env(tmp_path / "derived-no-kb")   # 缺 <副本>/kb ⇒ 切过去数据根是空的
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    seen = _install_switch_hooks(monkeypatch)

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 409, response.text
    assert "数据根" in response.json()["detail"]["error"]
    assert seen["spawned"] == []


def test_activate_rejects_active_runs(client: TestClient, tmp_path: Path,
                                      monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    work = _derived_copy(tmp_path)
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    seen = _install_switch_hooks(monkeypatch)
    monkeypatch.setattr(api, "_manager",
                        lambda: FakeManager([{"run_id": "RUN-B", "status": "waiting_slot"}]))

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 409, response.text
    assert "RUN-B(waiting_slot)" in response.json()["detail"]["error"]
    assert seen["spawned"] == [] and env_switch.pending() is None


def test_activate_rejects_pending_without_supervisor_pid_with_manual_path(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """缺 supervisor_pid（历史/手写 pending）⇒ 不可活判：409 + 人工清理路径，不自动清。"""
    work = _derived_copy(tmp_path)
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    seen = _install_switch_hooks(monkeypatch)
    _write_pending_raw()   # 无 supervisor_pid

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 409, response.text
    error = response.json()["detail"]["error"]
    assert "无法自动收口" in error
    assert str(env_switch.pending_path()) in error   # 明确人工清理路径
    assert seen["spawned"] == []
    assert env_switch.pending() is not None          # 不猜成已死、不自动删除


def test_pending_with_dead_supervisor_is_auto_cleared_and_switch_proceeds(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """supervisor pid 已不存在 ⇒ 自动清 pending + 落只增历史，然后正常切换（不再永久 409）。"""
    work = _derived_copy(tmp_path)
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    monkeypatch.setattr(api, "_manager", lambda: FakeManager([]))
    seen = _install_switch_hooks(monkeypatch)
    (state_root / "s0" / "S0-DERIVED-1").mkdir(parents=True)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()                                      # 已退出且已回收 ⇒ pid 是死的
    _write_pending_raw(supervisor_pid=dead.pid)

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 202, response.text
    history = [json.loads(line) for line in
               env_switch.history_path().read_text(encoding="utf-8").splitlines()]
    cleared = [row for row in history if row.get("reason") == "supervisor_dead_auto_clear"]
    assert cleared, "自动收口必须留只增历史"
    assert cleared[-1]["status"] == "cleared"
    assert cleared[-1]["supervisor_pid"] == dead.pid
    # 新的切换已受理（pending 被新请求覆盖）
    assert env_switch.pending()["target_env_root"] == str(work)
    assert len(seen["spawned"]) == 1


def test_pending_with_live_supervisor_keeps_409_with_pid_and_waited(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """supervisor 进程还活着 ⇒ 409，并给出 pid 与已等待时长（不自动清）。"""
    work = _derived_copy(tmp_path)
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    seen = _install_switch_hooks(monkeypatch)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        _write_pending_raw(supervisor_pid=child.pid, supervisor_started_ts=time.time() - 2.5)
        response = client.post("/api/s0/S0-DERIVED-1/activate", json={})
        assert response.status_code == 409, response.text
        error = response.json()["detail"]["error"]
        assert f"pid={child.pid}" in error
        assert "已等待" in error
        assert seen["spawned"] == []
        assert env_switch.pending() is not None
    finally:
        child.terminate()
        child.wait(timeout=10)


def test_activate_returns_202_and_never_kills_test_process(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    work = _derived_copy(tmp_path)
    record = _ready_record(work, "S0-DERIVED-2")
    store = FakeStore(tmp_path / "records", record=record)
    _use_store(monkeypatch, store)
    monkeypatch.setattr(api, "_manager", lambda: FakeManager([]))
    seen = _install_switch_hooks(monkeypatch)
    record_dir = state_root / "s0" / "S0-DERIVED-2"
    record_dir.mkdir(parents=True)

    response = client.post("/api/s0/S0-DERIVED-2/activate",
                           json={"now": "2026-10-30T02:00:00+08:00"})

    assert response.status_code == 202, response.text
    switch = response.json()["switch"]
    assert switch["status"] == "pending"
    assert Path(switch["target_env_root"]) == work.resolve()
    assert switch["record_id"] == "S0-DERIVED-2"
    # body 的 now 只覆盖 requested_at（时间注入唯一入口仍是 LOOP_NOW/KB_NOW）
    assert switch["requested_at"] == "2026-10-30T02:00:00+08:00"
    # 注入钩子被调用（生产路径才会真起 supervisor / 真退出本进程）
    assert len(seen["spawned"]) == 1 and seen["spawned"][0]["target_env_root"] == str(work)
    assert _wait_until(lambda: bool(seen["shutdowns"])), "后台退出钩子未被调用"
    # 先写 pending；S0 记录目录有只读投影
    assert env_switch.pending()["target_env_root"] == str(work)
    projection = json.loads((record_dir / "env-switch.json").read_text(encoding="utf-8"))
    assert projection["status"] == "pending"
    # 环境根没有变：active 仍为空（切换结论只能由 supervisor 落盘）
    assert env_switch.active() is None


def test_activate_returns_503_when_spawn_fails_and_clears_pending(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    work = _derived_copy(tmp_path)
    store = FakeStore(tmp_path / "records", record=_ready_record(work))
    _use_store(monkeypatch, store)
    monkeypatch.setattr(api, "_manager", lambda: FakeManager([]))
    monkeypatch.setattr(api, "SPAWN_SUPERVISOR", lambda request: (_ for _ in ()).throw(
        OSError("无法 fork")))
    monkeypatch.setattr(api, "SHUTDOWN_SERVER", lambda: pytest.fail("spawn 失败不得退出本进程"))
    record_dir = state_root / "s0" / "S0-DERIVED-1"
    record_dir.mkdir(parents=True)

    response = client.post("/api/s0/S0-DERIVED-1/activate", json={})

    assert response.status_code == 503, response.text
    assert "环境根未改变" in response.json()["detail"]["error"]
    assert env_switch.pending() is None


# ---------------------------------------------------------------- 退出钩子（优雅退出，不是硬杀）

def test_default_shutdown_hook_is_graceful_sigterm(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认钩子 = SIGTERM（uvicorn 优雅退出路径），**不是** os._exit/SIGKILL。"""
    raised: list[int] = []
    monkeypatch.setattr(api.signal, "raise_signal", lambda sig: raised.append(sig))

    assert api.SHUTDOWN_SERVER is api._shutdown_process
    api._shutdown_process()

    assert raised == [signal.SIGTERM]


def test_request_shutdown_schedules_delay_before_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """202 返回后**延迟**退出：默认 0.5s 后再触发钩子，避免响应没写完就断连。"""
    monkeypatch.delenv("LOOP_SWITCH_EXIT_DELAY", raising=False)
    scheduled: list = []

    class FakeLoop:
        def call_later(self, delay, callback):
            scheduled.append(delay)
            callback()

    monkeypatch.setattr(api.asyncio, "get_running_loop", lambda: FakeLoop())
    monkeypatch.setattr(api, "SHUTDOWN_SERVER", lambda: scheduled.append("shutdown"))

    api._request_shutdown()

    assert scheduled[0] == 0.5, "默认最小延迟必须是正的（先让 202 响应写完）"
    assert scheduled[1] == "shutdown"


# ---------------------------------------------------------------- POST /api/env/switch-back

def test_switch_back_rejects_without_origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            state_root: Path) -> None:
    # 不跑 lifespan ⇒ 没有 origin 记录
    client = TestClient(api.app)
    response = client.post("/api/env/switch-back", json={})
    assert response.status_code == 409, response.text
    assert "原始环境根" in response.json()["detail"]["error"]


def test_switch_back_rejects_when_already_at_origin(client: TestClient,
                                                    state_root: Path) -> None:
    response = client.post("/api/env/switch-back", json={})
    assert response.status_code == 409, response.text
    assert "已在原始环境根" in response.json()["detail"]["error"]


def test_switch_back_returns_202_from_derived_root(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    origin = _make_env(tmp_path / "origin-env")
    origin_workspace = tmp_path / "origin-ws"
    origin_workspace.mkdir()
    env_switch.record_origin(origin, workspace_root=origin_workspace)
    derived = _derived_copy(tmp_path)
    monkeypatch.setattr(P, "ENV_ROOT", derived)
    monkeypatch.setattr(P, "WORKSPACE_ROOT", derived / "kb")
    seen = _install_switch_hooks(monkeypatch)
    monkeypatch.setattr(api, "_manager", lambda: FakeManager([]))

    with TestClient(api.app) as client:
        response = client.post("/api/env/switch-back", json={})

    assert response.status_code == 202, response.text
    switch = response.json()["switch"]
    assert Path(switch["target_env_root"]) == origin.resolve()
    assert Path(switch["target_workspace"]) == origin_workspace.resolve()
    assert Path(switch["fallback_env_root"]) == derived
    assert Path(switch["fallback_workspace"]) == derived / "kb"
    assert len(seen["spawned"]) == 1
    assert _wait_until(lambda: bool(seen["shutdowns"]))


def test_switch_back_auto_clears_dead_pending(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state_root: Path) -> None:
    """切回也走同一前置：死 supervisor 的 pending 自动收口后放行（S0 §9.6 双向）。"""
    origin = _make_env(tmp_path / "origin-env")
    (tmp_path / "origin-ws").mkdir()
    env_switch.record_origin(origin, workspace_root=tmp_path / "origin-ws")
    derived = _derived_copy(tmp_path)
    monkeypatch.setattr(P, "ENV_ROOT", derived)
    monkeypatch.setattr(P, "WORKSPACE_ROOT", derived / "kb")
    _install_switch_hooks(monkeypatch)
    monkeypatch.setattr(api, "_manager", lambda: FakeManager([]))
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _write_pending_raw(supervisor_pid=dead.pid)

    with TestClient(api.app) as client:
        response = client.post("/api/env/switch-back", json={})

    assert response.status_code == 202, response.text
    assert Path(response.json()["switch"]["target_env_root"]) == origin.resolve()
    history = [json.loads(line) for line in
               env_switch.history_path().read_text(encoding="utf-8").splitlines()]
    assert any(row.get("reason") == "supervisor_dead_auto_clear" for row in history)


# ---------------------------------------------------------------- GET /api/s0/copies

def test_copies_lists_only_rtl_folder_records(client: TestClient, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch,
                                              state_root: Path) -> None:
    records = tmp_path / "records"
    work = _derived_copy(tmp_path)
    (work / "RTL" / "a.v").write_text("module a; endmodule\n", encoding="utf-8")
    (work / "kb" / "baselines" / "v0.json").write_text("{}\n", encoding="utf-8")
    _write_record(records, "S0-A", entry="rtl_folder", work_env=str(work),
                  rtl_prefix="RTL", status="prepared", ready_for_execution=True)
    _write_record(records, "S0-B", work_env=str(tmp_path / "plain"),
                  status="prepared", ready_for_execution=False)   # 普通 S0-a 记录：不列
    _write_record(records, "S0-C", entry="rtl_folder",
                  work_env=str(tmp_path / "gone"),
                  rtl_prefix="RTL/SRC", status="failed", ready_for_execution=False)
    _use_store(monkeypatch, FakeStore(records))

    response = client.get("/api/s0/copies")

    assert response.status_code == 200, response.text
    copies = {row["id"]: row for row in response.json()["copies"]}
    assert set(copies) == {"S0-A", "S0-C"}
    assert copies["S0-A"]["exists"] is True
    assert copies["S0-A"]["rtl_prefix"] == "RTL"
    assert copies["S0-A"]["status"] == "prepared"
    assert copies["S0-A"]["ready_for_execution"] is True
    assert copies["S0-A"]["bytes"] == sum(
        path.stat().st_size for path in work.rglob("*") if path.is_file())
    assert copies["S0-C"]["exists"] is False and copies["S0-C"]["bytes"] == 0


# ---------------------------------------------------------------- DELETE /api/s0/{id}/copy

def _copies_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    records = tmp_path / "records"
    copies_root = tmp_path / "workspaces"
    work = copies_root / "demo-derived-1"
    (work / "RTL").mkdir(parents=True)
    (work / "RTL" / "a.v").write_text("module a; endmodule\n", encoding="utf-8")
    _write_record(records, "S0-A", entry="rtl_folder", work_env=str(work), rtl_prefix="RTL")
    return records, copies_root, work


@pytest.mark.parametrize("query", ["", "?confirm=false"])
def test_delete_copy_requires_double_confirmation(client: TestClient, tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch,
                                                  state_root: Path, query: str) -> None:
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)

    response = client.delete(f"/api/s0/S0-A/copy{query}")

    assert response.status_code == 400, response.text
    assert "confirm=true" in response.json()["detail"]["error"]
    assert work.is_dir()   # 未确认 ⇒ 什么都没删


def test_delete_copy_removes_only_directory_not_record(client: TestClient, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       state_root: Path) -> None:
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 200, response.text
    assert response.json() == {"deleted": True, "work_env": str(work.resolve())}
    assert not work.exists()
    # 记录保留（证据只增不改）
    assert (records / "S0-A" / "record.json").is_file()


def test_delete_copy_reports_not_deleted_when_directory_absent(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    records = tmp_path / "records"
    copies_root = tmp_path / "workspaces"
    copies_root.mkdir()
    gone = copies_root / "gone"
    _write_record(records, "S0-A", entry="rtl_folder", work_env=str(gone))
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is False


def test_delete_copy_refuses_path_outside_copies_root(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    records, copies_root, _ = _copies_fixture(tmp_path)
    outside = _make_env(tmp_path / "outside")
    _write_record(records, "S0-A", entry="rtl_folder", work_env=str(outside))
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 400, response.text
    assert "拒绝删除" in response.json()["detail"]["error"]
    assert outside.is_dir()


def test_delete_copy_refuses_current_env_root(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)
    monkeypatch.setattr(P, "ENV_ROOT", work)

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 409, response.text
    assert "当前环境根" in response.json()["detail"]["error"]
    assert work.is_dir()


def test_delete_copy_after_switch_back_is_allowed(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """切回原环境后（active.target 仍是副本但当前根不是它）⇒ 副本必须可手动清理。"""
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)
    monkeypatch.setattr(P, "ENV_ROOT", tmp_path / "origin-env")   # 当前根已切回原始根
    env_switch.active_path().parent.mkdir(parents=True, exist_ok=True)
    env_switch.active_path().write_text(json.dumps({
        "status": "active", "target_env_root": str(work.resolve())}), encoding="utf-8")

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert not work.exists()
    # 记录保留
    assert (records / "S0-A" / "record.json").is_file()


def test_delete_copy_allows_rollback_target(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """active.status=rollback（切换失败回退）⇒ 副本未被使用，可删。"""
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)
    monkeypatch.setattr(P, "ENV_ROOT", tmp_path / "origin-env")
    env_switch.active_path().parent.mkdir(parents=True, exist_ok=True)
    env_switch.active_path().write_text(json.dumps({
        "status": "rollback", "restored": True,
        "target_env_root": str(work.resolve())}), encoding="utf-8")

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert not work.exists()


def test_delete_copy_refuses_in_flight_pending_target(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """在飞切换的目标副本正在被 supervisor 接手，拒绝删除。"""
    records, copies_root, work = _copies_fixture(tmp_path)
    _use_store(monkeypatch, FakeStore(records))
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)
    monkeypatch.setattr(P, "ENV_ROOT", tmp_path / "origin-env")
    _write_pending_raw(target_env_root=str(work.resolve()), supervisor_pid=os.getpid())

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 409, response.text
    assert "在飞切换" in response.json()["detail"]["error"]
    assert work.is_dir()


def test_delete_copy_rejects_record_without_rtl_folder_entry(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    records = tmp_path / "records"
    plain = _make_env(tmp_path / "plain")
    _write_record(records, "S0-A", work_env=str(plain))
    _use_store(monkeypatch, FakeStore(records))

    response = client.delete("/api/s0/S0-A/copy?confirm=true")

    assert response.status_code == 409, response.text
    assert "rtl_folder" in response.json()["detail"]["error"]
    assert plain.is_dir()


def test_delete_copy_missing_record_404(client: TestClient, tmp_path: Path,
                                        monkeypatch: pytest.MonkeyPatch,
                                        state_root: Path) -> None:
    _use_store(monkeypatch, FakeStore(tmp_path / "records"))
    response = client.delete("/api/s0/S0-NOPE/copy?confirm=true")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------- 与 T1 真实实现的端到端接线

def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


_RTL_FILES = {
    "SRC/dut.v": ("module dut(\n    input clk,\n    input [7:0] din,\n"
                  "    output [7:0] dout\n);\nendmodule\n"),
    "SRC/imports/a.v": "module a_imp(\n    input clk\n);\nendmodule\n",
    "RTL_COMMON/common.v": "module common(\n    input clk\n);\nendmodule\n",
    "vendor.v": "module vendor(\n    input clk\n);\nendmodule\n",
}
_MINI_BASELINE = {
    **{f"RTL/{rel}": text for rel, text in _RTL_FILES.items()},
    "TB/top.sv": ("module top;\n  dut u_dut(.clk(clk), .din(din), .dout(dout));\n"
                  "endmodule\n"),
    "PKG/pkg.sv": "package p;\nendpackage\n",
    "TESTLIB/tc_a.sv": "module tc_a;\nendmodule\n",
    "doc/index.md": "# 文档\n",
    "run": "#!/bin/sh\nexit 99\n",
    "all_define.txt": "-define SIM\n",
    "kb/baselines/v0/allfiles.md5": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  RTL/SRC/dut.v\n",
    "kb/index/index.json": "{}\n",
    "kb/conflicts/conflicts.csv": "id,kind\n",
    "kb/adjudication/adjudication.json": "[]\n",
    "loop/loop_entry.py": "# 软件目录：必须整目录排除\n",
    "SIMLIB_RUN/work/a.log": "sim log\n",
}


def _mini_project(tmp_path: Path) -> tuple[Path, Path]:
    baseline = tmp_path / "env"
    _write_tree(baseline, _MINI_BASELINE)
    incoming = tmp_path / "incoming" / "RTL"   # 目录名必须是 RTL/SRC（§9.2）
    _write_tree(incoming, _RTL_FILES)
    return baseline, incoming


@pytest.mark.skipif(not hasattr(S0Store, "prepare_from_rtl"),
                    reason="T1 的 S0Store.prepare_from_rtl 未合入")
def test_from_rtl_end_to_end_with_real_store_then_list_and_delete_copy(
        client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        state_root: Path) -> None:
    """真实 T1 实现接线：from-rtl（200/记录/副本）→ copies 清单 → 删除副本（记录保留）。"""
    baseline, incoming = _mini_project(tmp_path)
    copies_root = tmp_path / "copies"
    copies_root.mkdir()
    # 派生副本落点是唯一来源 COPIES_ROOT；浏览根允许 tmp（等价于界面从允许根里选目录）
    monkeypatch.setattr(api, "COPIES_ROOT", copies_root)
    monkeypatch.setenv("LOOP_BROWSE_ROOTS", str(tmp_path))

    response = client.post("/api/s0/from-rtl", json={
        "rtl_source": str(incoming),
        "baseline": str(baseline),
        "now": "2026-10-30T12:00:00+00:00",
    })

    assert response.status_code == 200, response.text
    record = response.json()
    work = Path(record["work_env"])
    assert record["entry"] == "rtl_folder"
    assert record["status"] == "prepared"
    assert record["rtl_prefix"] == "RTL"
    assert Path(record["baseline"]) == baseline.resolve()
    # baseline 缺省是原始根（本进程启动时记录），显式 baseline 覆盖它但 origin 仍是原始根
    assert Path(record["origin_env_root"]) == Path(P.ENV_ROOT).resolve()
    assert copies_root.resolve() in work.parents
    assert (work / "kb").is_dir(), "副本必须自包含数据根（S0 §9.3）"
    checks = {row["key"]: row["status"] for row in record["checks"]}
    assert checks["copy"] == "passed" and checks["rtl"] == "passed"
    assert checks["non_rtl"] == "passed" and checks["baseline"] == "passed"
    assert "loop" in record["copy_plan"]["excluded_roots"]
    assert "SIMLIB_RUN" in record["copy_plan"]["excluded_roots"]
    # 记录投影（T1 的 get() 合并 env-switch.json）：此时还没切换
    assert "env_switch" not in client.get("/api/s0/" + record["id"]).json()

    listed = client.get("/api/s0/copies").json()["copies"]
    assert [row["id"] for row in listed] == [record["id"]]
    assert listed[0]["exists"] is True and listed[0]["bytes"] > 0
    assert listed[0]["rtl_prefix"] == "RTL" and listed[0]["status"] == "prepared"

    deleted = client.delete("/api/s0/" + record["id"] + "/copy?confirm=true")

    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert not work.exists()
    # 记录保留（证据只增不改）
    assert (state_root / "s0" / record["id"] / "record.json").is_file()
