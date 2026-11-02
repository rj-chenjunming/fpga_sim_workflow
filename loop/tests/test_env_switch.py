"""S0 §9.6 切换状态机 + supervisor 的契约测试（TDD：先失败后实现）。

判据全部**不读源码**即可判定：
- `origin_env_root` 首次记录后不变（同值幂等、不同值报错）；
- `pending`/`active`/`history` 的读写与"进行中优先"的摘要口径；
- `build_request` 的字段与数据根解析（副本自包含 `<副本>/kb`、原始根用记录的数据根）；
- supervisor 两条决策路径：健康检查通过 ⇒ active；失败 ⇒ 停新进程 + 回退旧根 ⇒ rollback；
- 等待/超时/健康探测/进程全部可注入：本测试**不起服务、不碰真实端口、不杀测试进程**；
- lifespan：写 `server.json`、首次记录 origin、`/api/health` 与 `/api/env/state` 只增切换字段。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from host import env_switch
from host import paths as P
from host import switch_supervisor as sup
from services.api import app


@pytest.fixture(autouse=True)
def clean_switch_state():
    """切换状态在隔离的 `LOOP_STATE_ROOT` 下，但同一进程内测试之间要互相清空。"""
    shutil.rmtree(env_switch.state_dir(), ignore_errors=True)
    yield
    shutil.rmtree(env_switch.state_dir(), ignore_errors=True)


def _make_env(root: Path) -> Path:
    for name in ("RTL", "TB", "PKG", "TESTLIB"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def _derived_copy(tmp_path: Path) -> Path:
    """派生副本形态：环境四件套 + 自包含数据根 `<副本>/kb`（S0 §9.3）。"""
    work = _make_env(tmp_path / "derived")
    (work / "kb" / "baselines").mkdir(parents=True)
    return work


def _record_origin() -> Path:
    env_switch.record_origin(P.ENV_ROOT, workspace_root=P.WORKSPACE_ROOT)
    return Path(P.ENV_ROOT)


def _switch_request(tmp_path: Path, *, record_id: str | None = None) -> dict:
    target = _derived_copy(tmp_path)
    _record_origin()
    return env_switch.build_request(
        target_env_root=target,
        origin_env_root=env_switch.origin_env_root(),
        record_id=record_id,
        project=P.ENV_ROOT,
        app_dir=P.LOOP_DIR,
        host="127.0.0.1",
        port=8099,
        state_root=P.STATE_DIR,
    )


class _Proc:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def _run_supervisor(request: dict, *, health_for: str | None = None,
                    port_free: bool = True) -> tuple[dict, dict]:
    """用假进程/假健康检查跑一次决策；返回 (结论, 观测到的启动/停止记录)。"""
    seen = {"started": [], "stopped": []}
    target = Path(request["target_env_root"]).resolve()
    fallback = Path(request["fallback_env_root"]).resolve()
    wanted = Path(health_for).resolve() if health_for else target

    def start(req, *, env_root, workspace):
        seen["started"].append((str(Path(env_root).resolve()), str(Path(workspace).resolve())))
        return _Proc(4000 + len(seen["started"]))

    def probe(host, port, expect, *, timeout, interval, sleep, clock):
        return Path(expect).resolve() == wanted

    decision = sup.run(request, start=start, stop=seen["stopped"].append,
                       wait_free=lambda *a, **k: port_free,
                       probe=probe, sleep=lambda seconds: None, clock=lambda: 0.0)
    return decision, seen


# ---------------------------------------------------------------- 状态机与路径

def test_state_dir_lives_under_state_root() -> None:
    assert env_switch.state_dir() == Path(P.STATE_DIR) / "env-switch"


def test_origin_is_recorded_once_and_immutable(tmp_path: Path) -> None:
    first = _make_env(tmp_path / "env-a")
    second = _make_env(tmp_path / "env-b")

    env_switch.record_origin(first, workspace_root=tmp_path / "ws-a")
    assert env_switch.origin_env_root() == first.resolve()
    assert env_switch.origin_workspace_root() == (tmp_path / "ws-a").resolve()

    # 同值幂等：不报错、不覆盖
    before = env_switch.origin_path().read_bytes()
    env_switch.record_origin(first.resolve(), workspace_root=tmp_path / "ws-other")
    assert env_switch.origin_path().read_bytes() == before
    assert env_switch.origin_workspace_root() == (tmp_path / "ws-a").resolve()

    # 不同值必须显式报错（S0 §9.6 / 决定 17）
    with pytest.raises(ValueError, match="不得改为"):
        env_switch.record_origin(second)
    assert env_switch.origin_env_root() == first.resolve()


def test_origin_rejects_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="不存在或不是目录"):
        env_switch.record_origin(tmp_path / "nope")


def test_build_request_fields_and_workspace_resolution(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id="S0-DEMO-1")
    target = Path(request["target_env_root"])
    assert target.is_dir()

    assert request["kind"] == "env-switch"
    assert request["status"] == "pending"
    assert Path(request["target_env_root"]) == target
    # 副本自包含：数据根 = <副本>/kb（S0 §9.3）
    assert Path(request["target_workspace"]) == target / "kb"
    # 回退根 = 当前进程的环境根；数据根 = 当前进程的数据根
    assert Path(request["fallback_env_root"]) == Path(P.ENV_ROOT).resolve()
    assert Path(request["fallback_workspace"]) == Path(P.WORKSPACE_ROOT)
    assert Path(request["origin_env_root"]) == Path(P.ENV_ROOT).resolve()
    assert Path(request["app_dir"]) == Path(P.LOOP_DIR)
    assert request["host"] == "127.0.0.1" and request["port"] == 8099
    assert Path(request["state_root"]) == Path(P.STATE_DIR)
    # 目录一律由 build_request 给出（supervisor 不推导路径）
    assert Path(request["pending_path"]) == env_switch.pending_path()
    assert Path(request["active_path"]) == env_switch.active_path()
    assert Path(request["history_path"]) == env_switch.history_path()
    assert Path(request["record_dir"]) == Path(P.STATE_DIR) / "s0" / "S0-DEMO-1"
    assert request["log"].startswith(str(env_switch.state_dir() / "logs"))
    assert request["requested_at"] and request["timeouts"]["health_s"] > 0


def test_build_request_uses_recorded_origin_workspace_for_switch_back(tmp_path: Path) -> None:
    """切回原始根时目标数据根 = origin 当时记录的数据根（不是 `<origin>/kb`）。"""
    origin = _make_env(tmp_path / "origin-env")
    (tmp_path / "origin-ws").mkdir()
    env_switch.record_origin(origin, workspace_root=tmp_path / "origin-ws")
    current = _derived_copy(tmp_path / "current")   # 切换后的副本进程：数据根 = <副本>/kb
    request = env_switch.build_request(
        target_env_root=origin,
        origin_env_root=origin,
        record_id=None,
        project=current,
        app_dir=P.LOOP_DIR,
        host="127.0.0.1",
        port=8099,
        state_root=P.STATE_DIR,
    )
    assert Path(request["target_workspace"]) == (tmp_path / "origin-ws").resolve()
    assert Path(request["fallback_env_root"]) == current
    assert Path(request["fallback_workspace"]) == current / "kb"


def test_build_request_refuses_unknown_data_root(tmp_path: Path) -> None:
    _make_env(tmp_path / "target")
    _record_origin()
    with pytest.raises(ValueError, match="fallback_workspace|数据根"):
        env_switch.build_request(
            target_env_root=tmp_path / "target",
            origin_env_root=env_switch.origin_env_root(),
            record_id=None,
            project=tmp_path / "unknown-root",
            app_dir=P.LOOP_DIR,
            host="127.0.0.1",
            port=8099,
            state_root=P.STATE_DIR,
        )


def test_pending_roundtrip_and_summary_precedence(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id=None)
    assert env_switch.pending() is None and env_switch.summary() is None

    env_switch.write_pending(request)
    assert env_switch.pending()["target_env_root"] == request["target_env_root"]
    summary = env_switch.summary()
    assert summary["status"] == "pending"
    assert summary["target_env_root"] == request["target_env_root"]
    # 摘要只暴露冻结字段，不外泄内部路径字段
    assert set(summary) == set(env_switch.SUMMARY_FIELDS)

    env_switch.clear_pending(request)
    assert env_switch.pending() is None and env_switch.summary() is None


def test_write_pending_rejects_incomplete_request() -> None:
    with pytest.raises(ValueError, match="缺少字段"):
        env_switch.write_pending({"target_env_root": "/tmp/x"})


# ---------------------------------------------------------------- supervisor 决策

def test_supervisor_actives_when_health_reports_target(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id="S0-ACTIVE")
    record_dir = Path(request["record_dir"])
    record_dir.mkdir(parents=True)
    env_switch.write_pending(request)

    decision, seen = _run_supervisor(request)

    assert decision["status"] == "active"
    assert decision["finished_at"]
    assert decision["pid"] == 4001
    # 新服务必须用 target + target_workspace 起
    assert seen["started"] == [(str(Path(request["target_env_root"]).resolve()),
                               str(Path(request["target_workspace"]).resolve()))]
    assert seen["stopped"] == []
    # pending 收口 + active 落盘 + 摘要可取
    assert env_switch.pending() is None
    active = env_switch.active()
    assert active["status"] == "active"
    assert active["target_env_root"] == request["target_env_root"]
    assert env_switch.summary()["status"] == "active"
    # S0 记录目录的只读投影
    projection = json.loads((record_dir / "env-switch.json").read_text(encoding="utf-8"))
    assert projection["status"] == "active"
    assert projection["record_id"] == "S0-ACTIVE"
    # 只增历史：pending → active
    history = [json.loads(line) for line in
               env_switch.history_path().read_text(encoding="utf-8").splitlines()]
    assert [row["status"] for row in history][-2:] == ["pending", "active"]


def test_supervisor_rolls_back_and_restarts_fallback(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id=None)
    env_switch.write_pending(request)
    fallback = Path(request["fallback_env_root"]).resolve()

    decision, seen = _run_supervisor(request, health_for=str(fallback))

    assert decision["status"] == "rollback"
    assert decision["restored"] is True
    assert "健康检查未通过" in decision["reason"]
    # 先起新服务，健康失败后停掉它，再用 fallback 根起旧服务
    assert seen["started"] == [
        (str(Path(request["target_env_root"]).resolve()), str(Path(request["target_workspace"]).resolve())),
        (str(fallback), str(Path(request["fallback_workspace"]).resolve())),
    ]
    assert len(seen["stopped"]) == 1
    active = env_switch.active()
    assert active["status"] == "rollback"
    assert active["restored"] is True
    assert env_switch.pending() is None
    # 回滚不得冒充成功：派生副本仍存在（证据/数据根保留）
    assert Path(request["target_env_root"]).is_dir()


def test_supervisor_port_not_released_reports_old_service_still_serving(tmp_path: Path) -> None:
    """端口仍可连 ⇒ 旧服务还在正常服务：rollback + restored=true，且不启动任何新进程。"""
    request = _switch_request(tmp_path, record_id=None)
    decision, seen = _run_supervisor(request, port_free=False)
    assert decision["status"] == "rollback"
    assert decision["restored"] is True, "旧服务还在提供服务，不能谎称 restored=false"
    assert "旧服务仍在提供服务" in decision["reason"]
    # 不启动新服务，也不重起旧服务（旧服务本来就在跑）
    assert seen["started"] == []
    assert seen["stopped"] == []
    active = env_switch.active()
    assert active["status"] == "rollback" and active["restored"] is True


def test_supervisor_rollback_stops_unhealthy_fallback_and_gives_manual_path(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id=None)
    decision, seen = _run_supervisor(request, health_for=str(tmp_path / "nowhere"))
    assert decision["status"] == "rollback"
    assert decision["restored"] is False
    assert "回退服务健康检查未通过" in decision["reason"]
    assert "人工恢复" in decision["reason"], "必须给人工恢复路径"
    assert len(seen["started"]) == 2
    # 新服务 + 不健康的回退服务都必须被停掉（不留占端口的僵尸进程）
    assert len(seen["stopped"]) == 2


def test_supervisor_stamps_pid_into_pending(tmp_path: Path) -> None:
    """supervisor 启动第一步把自身 pid/启动时刻写回 pending（API 活判的唯一依据）。"""
    request = _switch_request(tmp_path, record_id=None)
    env_switch.write_pending(request)
    captured: dict = {}

    def runner(req):
        captured.update(req)
        return {"status": "active"}

    assert sup.main(["--pending", str(env_switch.pending_path())], runner=runner) == 0
    stamped = json.loads(env_switch.pending_path().read_text(encoding="utf-8"))
    assert stamped["supervisor_pid"] == os.getpid()
    assert isinstance(stamped["supervisor_started_ts"], float)
    assert captured["supervisor_pid"] == os.getpid()
    # 只加字段：原请求字段不变
    assert stamped["target_env_root"] == request["target_env_root"]
    assert stamped["requested_at"] == request["requested_at"]


# ---------------------------------------------------------------- 可注入的等待/探测

def test_wait_port_released_times_out_when_port_stays_open() -> None:
    ticks = [0.0]

    def clock() -> float:
        return ticks[0]

    def sleep(seconds: float) -> None:
        ticks[0] += seconds

    assert sup.wait_port_released("127.0.0.1", 8099, timeout=2.0, interval=0.5,
                                  sleep=sleep, clock=clock, probe=lambda *a: True) is False
    assert ticks[0] >= 2.0


def test_wait_port_released_succeeds_once_closed() -> None:
    calls = {"n": 0}

    def probe(host: str, port: int) -> bool:
        calls["n"] += 1
        return calls["n"] < 3

    assert sup.wait_port_released("h", 1, timeout=5.0, interval=0.1,
                                  sleep=lambda seconds: None, clock=lambda: 0.0,
                                  probe=probe) is True


def test_probe_health_requires_matching_env_root(tmp_path: Path) -> None:
    target = tmp_path / "derived"
    other = tmp_path / "other"
    answers = [{"env_root": str(other)}, {"env_root": str(target)}]
    assert sup.probe_health("127.0.0.1", 1, str(target), timeout=5.0, interval=0.1,
                            sleep=lambda seconds: None, clock=lambda: 0.0,
                            fetch=lambda host, port: answers.pop(0)) is True

    ticks = [0.0]

    def clock() -> float:
        return ticks[0]

    def sleep(seconds: float) -> None:
        ticks[0] += seconds

    # 根永远不对 ⇒ 超时失败（不能"服务活着就算切过去了"）
    assert sup.probe_health("127.0.0.1", 1, str(target), timeout=0.5, interval=0.1,
                            sleep=sleep, clock=clock,
                            fetch=lambda host, port: {"env_root": str(other)}) is False


def test_service_command_and_env(tmp_path: Path) -> None:
    request = {"app_dir": str(P.LOOP_DIR), "host": "127.0.0.1", "port": 9123,
               "state_root": str(P.STATE_DIR), "log": str(tmp_path / "switch.log")}
    command = sup.service_command(request)
    assert command[1:3] == ["-m", "uvicorn"]
    assert "services.api:app" in command
    assert command[command.index("--app-dir") + 1] == str(P.LOOP_DIR)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--port") + 1] == "9123"

    env = sup.service_env(request, env_root="/tmp/env", workspace="/tmp/env/kb", base={})
    assert env["LOOP_ENV_ROOT"] == "/tmp/env"
    assert env["LOOP_WORKSPACE"] == "/tmp/env/kb"
    assert env["LOOP_STATE_ROOT"] == str(P.STATE_DIR)
    assert env["LOOP_PORT"] == "9123"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(P.LOOP_DIR)


def test_load_request_accepts_file_and_inline_json(tmp_path: Path) -> None:
    payload = {"target_env_root": str(tmp_path), "port": 8099}
    path = tmp_path / "pending.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert sup.load_request(str(path)) == payload
    assert sup.load_request(json.dumps(payload)) == payload


def test_main_exit_codes(tmp_path: Path) -> None:
    spec = json.dumps({"target_env_root": str(tmp_path)})
    assert sup.main(["--pending", spec], runner=lambda request: {"status": "active"}) == 0
    assert sup.main(["--pending", spec], runner=lambda request: {"status": "rollback"}) == 1

    def boom(request):
        raise RuntimeError("supervisor 自身异常")

    assert sup.main(["--pending", spec], runner=boom) == 2


# ---------------------------------------------------------------- lifespan / health / env state

def test_lifespan_records_server_and_origin() -> None:
    with TestClient(app) as client:
        info = env_switch.server_info()
        assert info is not None
        assert info["pid"] == os.getpid()
        assert info["port"] == env_switch.server_port()
        assert Path(info["app_dir"]) == Path(P.LOOP_DIR)
        assert Path(info["env_root"]) == Path(P.ENV_ROOT)
        assert Path(env_switch.origin_env_root()) == Path(P.ENV_ROOT).resolve()

        health = client.get("/api/health").json()
        # 既有键不变，只增切换字段
        assert health["ok"] is True
        assert health["env_root"] == str(P.ENV_ROOT)
        assert Path(health["origin_env_root"]) == Path(P.ENV_ROOT).resolve()
        assert health["switch"] is None

        state = client.get("/api/env/state").json()
        assert set(state) == {"env_root", "env_id", "origin_env_root", "switch", "baseline_source"}
        assert state["env_root"] == str(P.ENV_ROOT)
        assert Path(state["origin_env_root"]) == Path(P.ENV_ROOT).resolve()
        assert Path(state["baseline_source"]) == Path(P.ENV_ROOT).resolve()
        assert state["switch"] is None


def test_health_and_env_state_expose_active_switch(tmp_path: Path) -> None:
    request = _switch_request(tmp_path, record_id=None)
    decision, _ = _run_supervisor(request)
    assert decision["status"] == "active"

    with TestClient(app) as client:
        switch = client.get("/api/health").json()["switch"]
        assert switch["status"] == "active"
        assert switch["target_env_root"] == request["target_env_root"]
        state = client.get("/api/env/state").json()
        assert state["switch"]["status"] == "active"
        assert state["switch"]["target_env_root"] == request["target_env_root"]
