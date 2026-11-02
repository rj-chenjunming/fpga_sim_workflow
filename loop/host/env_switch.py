"""环境根切换：状态持久化、请求构造、supervisor 启动（S0 §9.6 / ENV_PLUGIN_SPEC §8）。

**唯一写者约定**（AGENTS.md §1「每个决策/状态/效果恰好一个 owner」）

- 本模块写 `<STATE_DIR>/env-switch/` 下的**状态机**文件：
  - `origin.json`   原始环境根（首次记录后不变；派生源恒为它，禁止副本当基线）
  - `pending.json`  进行中的切换请求（由本模块写，`switch_supervisor` 消费后删除）
  - `active.json`   最近一次切换结论（`status ∈ {active, rollback}`）
  - `history.jsonl` 只增的切换审计（pending / 结论 / origin 记录各一行）
  - `server.json`   本进程服务信息（pid / port / host / app_dir / 三根）
  - `logs/`         supervisor 与子服务的日志
- S0 记录目录里的只读投影 `env-switch.json` 也由切换链写（`record_dir` 来自本模块的
  `build_request`）；`host/s0.py` 只读它，不写这里的任何文件。
- 状态推进（`pending → active/rollback`）归独立进程 `host/switch_supervisor.py`：
  它**只消费本模块 `build_request()` 给出的路径与字段**，不自己推导目录 —— 避免两套路径口径。

**不变量**

- `origin_env_root` 首次记录后不变：重复记录同值幂等，不同值 `ValueError`（S0 §9.6 / 决定 17）。
- 切换前必须写 `pending.json`；结论只写 `active.json`（并清掉 `pending`），历史只增不改。
- 本模块不判定"服务是否真的切过去了"：那是 supervisor 的 `/api/health` 校验（不在此处猜）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from host import paths as P

#: 切换状态目录名（`<STATE_DIR>/env-switch`）
SWITCH_DIRNAME = "env-switch"
#: 缺省服务端口/主机（`loop/run.sh` 用 `LOOP_PORT`，缺省 8099；绑定 127.0.0.1）
DEFAULT_PORT = 8099
DEFAULT_HOST = "127.0.0.1"
#: 等待/超时缺省（秒）：可经环境变量覆盖，便于真实环境调参而不改代码
DEFAULT_TIMEOUTS: dict[str, float] = {"port_s": 20.0, "health_s": 60.0, "interval_s": 0.5}

#: `/api/env/state` 与 `/api/health` 共用的切换摘要字段（唯一投影，红线 8）
SUMMARY_FIELDS = (
    "status",
    "target_env_root",
    "target_workspace",
    "origin_env_root",
    "record_id",
    "requested_at",
    "finished_at",
    "reason",
    "restored",
    "host",
    "port",
)

#: 切换请求的必填字段（缺一个就拒绝写 pending：宁可显式失败，不留半截状态）
REQUIRED_REQUEST_FIELDS = (
    "target_env_root",
    "target_workspace",
    "fallback_env_root",
    "fallback_workspace",
    "app_dir",
    "host",
    "port",
    "state_root",
    "pending_path",
    "active_path",
    "history_path",
    "log",
)


# ---------------------------------------------------------------- 目录与 JSON 读写

def state_dir() -> Path:
    """`<STATE_DIR>/env-switch`：切换状态的唯一根（`LOOP_STATE_ROOT` 隔离后自然跟随）。"""
    return Path(P.STATE_DIR) / SWITCH_DIRNAME


def origin_path() -> Path:
    return state_dir() / "origin.json"


def pending_path() -> Path:
    return state_dir() / "pending.json"


def active_path() -> Path:
    return state_dir() / "active.json"


def history_path() -> Path:
    return state_dir() / "history.jsonl"


def server_path() -> Path:
    return state_dir() / "server.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    """读状态文件：不存在 ⇒ None；损坏/不可读 ⇒ 显式 `ValueError`（不静默换默认值）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"切换状态文件不可读：{path}：{exc}") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"切换状态文件不可解析：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"切换状态文件顶层必须是 JSON 对象：{path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    """原子写（先写临时件再 `os.replace`）：半截状态不会被下游当成有效结论。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    return path


def _append_history(event: dict[str, Any]) -> None:
    """只增审计：一行一个事件（pending / 结论 / origin），不修改历史行。"""
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------- 原始环境根

def origin_env_root() -> Path | None:
    """持久化的原始环境根；未记录 ⇒ None（**不回落**到当前根，避免把副本当原始根）。"""
    data = _read_json(origin_path())
    raw = (data or {}).get("env_root")
    return Path(str(raw)) if raw else None


def origin_workspace_root() -> Path | None:
    """原始环境根当时的数据根（切回时用；未记录 ⇒ None）。"""
    data = _read_json(origin_path())
    raw = (data or {}).get("workspace_root")
    return Path(str(raw)) if raw else None


def record_origin(env_root: Path, workspace_root: Path | None = None) -> None:
    """首次记录原始环境根；之后不变（同值幂等、不同值报错）。

    `workspace_root` 一并落账：切回原环境时要恢复**原始数据根**（不是 `<origin>/kb`，
    原环境的数据根通常在工作区目录下，见 ENV_PLUGIN_SPEC §3）。
    """
    target = Path(env_root)
    if not target.is_dir():
        raise ValueError(f"原始环境根不存在或不是目录：{target}")
    resolved = target.resolve()
    existing = _read_json(origin_path())
    if existing is not None:
        current = existing.get("env_root")
        same = False
        if current:
            try:
                same = Path(str(current)).resolve() == resolved
            except OSError:  # 已记录的根当前不可达 ⇒ 视为不同值（fail closed）
                same = False
        if not same:
            raise ValueError(
                f"原始环境根已记录为 {current}，不得改为 {resolved}"
                "（S0 §9.6 / 决定 17：origin_env_root 首次记录后不变）")
        return
    workspace = Path(workspace_root) if workspace_root is not None else None
    if workspace is None and resolved == Path(P.ENV_ROOT).resolve():
        workspace = Path(P.WORKSPACE_ROOT)
    event = {
        "env_root": str(resolved),
        "workspace_root": str(workspace.resolve()) if workspace is not None else None,
        "recorded_at": P.now_iso(),
    }
    _write_json(origin_path(), event)
    _append_history({"at": event["recorded_at"], "status": "origin", "env_root": event["env_root"]})


# ---------------------------------------------------------------- pending / active 投影

def active() -> dict[str, Any] | None:
    """最近一次切换结论（`status=active|rollback`）；无结论 ⇒ None。"""
    return _read_json(active_path())


def pending() -> dict[str, Any] | None:
    """进行中的切换请求；无 ⇒ None（有 pending 说明切换未收口）。"""
    return _read_json(pending_path())


def summary() -> dict[str, Any] | None:
    """界面/健康检查消费的**唯一**切换摘要：进行中的 pending 优先，其次最近结论。"""
    record = pending() or active()
    if record is None:
        return None
    return {key: record.get(key) for key in SUMMARY_FIELDS}


def write_pending(request: dict[str, Any]) -> Path:
    """把切换请求落 pending.json（切换的第一步；supervisor 只认这个文件）。"""
    missing = [key for key in REQUIRED_REQUEST_FIELDS if not request.get(key)]
    if missing:
        raise ValueError("切换请求缺少字段：" + "、".join(missing))
    written = _write_json(Path(str(request["pending_path"])), request)
    _append_history({
        "at": P.now_iso(),
        "status": "pending",
        "target_env_root": request.get("target_env_root"),
        "origin_env_root": request.get("origin_env_root"),
        "record_id": request.get("record_id"),
        "host": request.get("host"),
        "port": request.get("port"),
    })
    return written


def clear_pending(request: dict[str, Any] | None = None, *, reason: str | None = None) -> None:
    """撤销 pending（spawn 失败等未发生切换的场景；历史行保留）。

    `reason` 给定 ⇒ 追加一条**只增历史**（如 `supervisor_dead_auto_clear`），让
    "自动收口"可审计；不给 ⇒ 纯清理（spawn 失败由 HTTP 503 说明，无需历史）。
    只有真的删掉了 pending 才写历史（并发下重复收口不产生重复行）。
    """
    record = dict(request or {})
    raw = record.get("pending_path") or pending_path()
    try:
        Path(str(raw)).unlink()
    except FileNotFoundError:
        return
    if reason:
        _append_history({
            "at": P.now_iso(),
            "status": "cleared",
            "reason": str(reason),
            "target_env_root": record.get("target_env_root"),
            "origin_env_root": record.get("origin_env_root"),
            "record_id": record.get("record_id"),
            "supervisor_pid": record.get("supervisor_pid"),
        })


# ---------------------------------------------------------------- 本进程服务信息

def _argv_value(flag: str) -> str | None:
    """从命令行取 `--flag value` / `--flag=value`（uvicorn CLI 的 `--port/--host`）。

    为什么需要：服务可能以 `uvicorn services.api:app --port 9000` 启动而没设 `LOOP_PORT`；
    这时 `server.json` 若只信环境变量就会把端口写错，supervisor 会等错端口。
    """
    argv = sys.argv
    for index, item in enumerate(argv):
        if item == flag and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(flag + "="):
            return item.split("=", 1)[1]
    return None


def server_port() -> int:
    """本服务端口：`LOOP_PORT` → 命令行 `--port` → 缺省 8099（与 `loop/run.sh` 同一入口）。"""
    raw = os.environ.get("LOOP_PORT") or _argv_value("--port")
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"服务端口不是整数：{raw!r}") from exc


def server_host() -> str:
    return os.environ.get("LOOP_HOST") or _argv_value("--host") or DEFAULT_HOST


def server_info() -> dict[str, Any] | None:
    return _read_json(server_path())


def record_server(*, port: int | None = None, host: str | None = None,
                  app_dir: Path | None = None) -> dict[str, Any]:
    """记录本进程服务信息（lifespan 启动时调用；supervisor 据此定位端口与 app-dir）。"""
    data = {
        "pid": os.getpid(),
        "port": int(port) if port is not None else server_port(),
        "host": host or server_host(),
        "app_dir": str(app_dir or P.LOOP_DIR),
        "env_root": str(P.ENV_ROOT),
        "workspace_root": str(P.WORKSPACE_ROOT),
        "state_root": str(P.STATE_DIR),
        "started_at": P.now_iso(),
    }
    _write_json(server_path(), data)
    return data


# ---------------------------------------------------------------- 切换请求构造

def _timeouts() -> dict[str, float]:
    out = dict(DEFAULT_TIMEOUTS)
    for key, env_name in (("port_s", "LOOP_SWITCH_PORT_TIMEOUT"),
                          ("health_s", "LOOP_SWITCH_HEALTH_TIMEOUT"),
                          ("interval_s", "LOOP_SWITCH_INTERVAL")):
        raw = os.environ.get(env_name)
        if not raw:
            continue
        try:
            out[key] = float(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} 不是数字：{raw!r}") from exc
    return out


def _safe_stamp() -> str:
    return re.sub(r"[^0-9A-Za-z]+", "", P.now_iso()) or "switch"


def _target_workspace(target: Path, origin: Path | None) -> Path | None:
    """目标环境的数据根：切回原始根 ⇒ 原始数据根；切到副本 ⇒ `<副本>/kb`（自包含）。"""
    if origin is not None and target.resolve() == origin.resolve():
        return origin_workspace_root()
    return target / "kb"


def _fallback_workspace(project: Path, origin: Path | None) -> Path | None:
    """**当前**服务的数据根（回滚重起旧服务用）。当前进程自己的根是权威。"""
    resolved = project.resolve()
    if resolved == Path(P.ENV_ROOT).resolve():
        return Path(P.WORKSPACE_ROOT)
    if origin is not None and resolved == origin.resolve():
        return origin_workspace_root()
    candidate = project / "kb"
    if candidate.is_dir():
        return candidate
    info = server_info()
    if info and info.get("env_root") and info.get("workspace_root"):
        try:
            if Path(str(info["env_root"])).resolve() == resolved:
                return Path(str(info["workspace_root"]))
        except OSError:
            return None
    return None


def build_request(*, target_env_root: Path, origin_env_root: Path | None,
                  record_id: str | None, project: Path, app_dir: Path,
                  host: str, port: int, state_root: Path) -> dict[str, Any]:
    """构造切换请求（**路径与字段的唯一来源**：supervisor 不再推导任何目录）。

    - `project` = 当前服务正在提供的环境根（失败回退的根）；
    - `target_env_root` = 要切过去的根（派生副本或原始根）；
    - 数据根按 S0 §9.3 / ENV_PLUGIN_SPEC §3 解析（副本自包含、原始根用记录的数据根）。
    """
    target = Path(target_env_root)
    origin = Path(origin_env_root) if origin_env_root is not None else None
    current = Path(project)
    root = Path(state_root)
    switch_dir = root / SWITCH_DIRNAME

    target_workspace = _target_workspace(target, origin)
    fallback_workspace = _fallback_workspace(current, origin)
    missing = [label for label, value in (
        ("目标环境数据根 target_workspace", target_workspace),
        ("当前环境数据根 fallback_workspace", fallback_workspace),
    ) if value is None]
    if missing:
        raise ValueError(
            "无法确定" + "、".join(missing) + f"：target={target} current={current}；"
            "原始根需先由服务启动时记录（origin.json），派生副本需含 kb/ 数据根（S0 §9.3）")

    return {
        "kind": "env-switch",
        "status": "pending",
        "target_env_root": str(target),
        "target_workspace": str(target_workspace),
        "origin_env_root": str(origin) if origin is not None else None,
        "fallback_env_root": str(current),
        "fallback_workspace": str(fallback_workspace),
        "record_id": record_id or None,
        "record_dir": str(root / "s0" / record_id) if record_id else None,
        "app_dir": str(Path(app_dir)),
        "host": str(host),
        "port": int(port),
        "state_root": str(root),
        "pending_path": str(switch_dir / "pending.json"),
        "active_path": str(switch_dir / "active.json"),
        "history_path": str(switch_dir / "history.jsonl"),
        "log": str(switch_dir / "logs" / f"switch-{_safe_stamp()}.log"),
        "requested_at": P.now_iso(),
        "timeouts": _timeouts(),
    }


# ---------------------------------------------------------------- supervisor 启动

def spawn_supervisor(request: dict[str, Any]) -> int:
    """起独立 session 的 `python -m host.switch_supervisor --pending <pending.json>`。

    独立 session（`start_new_session=True`）⇒ 本进程优雅退出不会带走 supervisor；
    stdout/stderr 落 `request["log"]`；返回 supervisor pid（不等待，不阻塞请求）。
    """
    pending = Path(str(request.get("pending_path") or pending_path()))
    log = Path(str(request.get("log") or (state_dir() / "logs" / "supervisor.log")))
    log.parent.mkdir(parents=True, exist_ok=True)
    app_dir = str(request.get("app_dir") or P.LOOP_DIR)
    env = os.environ.copy()
    env["PYTHONPATH"] = app_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["LOOP_STATE_ROOT"] = str(request.get("state_root") or P.STATE_DIR)
    with open(log, "ab") as stream:
        proc = subprocess.Popen(
            [sys.executable, "-m", "host.switch_supervisor", "--pending", str(pending)],
            cwd=app_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
            close_fds=True,
        )
    return int(proc.pid)
