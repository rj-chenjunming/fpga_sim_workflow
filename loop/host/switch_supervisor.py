"""环境根切换 supervisor（独立进程，只用标准库；S0 §9.6 / ENV_PLUGIN_SPEC §8）。

用法::

    python -m host.switch_supervisor --pending <pending.json 或内联 JSON>

流程
1. 等旧进程释放端口；**超时且端口仍可连 ⇒ 旧服务还在正常服务**，直接落
   ``rollback / restored=true``（不启动新服务，不谎称"服务没了"）；
2. 端口已释放 ⇒ 以 ``LOOP_ENV_ROOT=<target>``、``LOOP_WORKSPACE=<target_workspace>``、
   同一 ``LOOP_STATE_ROOT`` 与端口起新服务
   （``python -m uvicorn services.api:app --app-dir <app_dir> --host <host> --port <port>``）；
3. 轮询 ``GET /api/health`` 且校验 ``env_root == target`` ⇒ 写 ``active.json``
   （``status=active``）退出 0；
4. 失败 ⇒ 杀新子进程，用 fallback 根按同法重起旧服务；回退服务也不健康时**停掉它**
   （别留占端口的僵尸）并给人工恢复路径，写 ``active.json``
   （``status=rollback`` + ``reason`` + ``restored``）退出 1。

supervisor 启动后**第一件事**是把自身 pid/启动时刻写回 pending（`stamp_pending`），
API 端据此用 ``host.admission.proc_state_start`` 判活并自动收口悬挂 pending。

本模块**不 import `host` 的其它模块**（尤其不 import `host.paths` / `host.env_switch`）：
目录、路径、超时全部来自 request —— request 的唯一来源是
`host/env_switch.build_request()`。这样 supervisor 在"服务正在退出"时也能独立跑，
不会因为环境变量/模块导入状态与旧服务不一致而走错目录。

所有等待与探测都可注入（`sleep`/`clock`/`start`/`stop`/`wait_free`/`probe`），
单测因此不需要真起服务、也不会碰真实端口。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

SERVICE_MODULE = "services.api:app"
DEFAULT_TIMEOUTS: dict[str, float] = {"port_s": 20.0, "health_s": 60.0, "interval_s": 0.5}
#: 停子进程的宽限（SIGTERM → SIGKILL）
STOP_GRACE_S = 10.0


def _log(message: str) -> None:
    """stdout 由 spawn 重定向到 `<state>/env-switch/logs/switch-*.log`。"""
    print(f"[switch] {message}", flush=True)


def _now() -> str:
    """时间字段的唯一注入入口（`LOOP_NOW` → `KB_NOW` → 墙钟）。

    与 `host/paths.py::now_iso` 同一优先级；此处刻意不 import `host.paths`
    （supervisor 只用标准库，避免依赖正在退出的服务进程环境），语义已在
    `tests/test_env_switch.py` 固定。
    """
    injected = os.environ.get("LOOP_NOW") or os.environ.get("KB_NOW")
    return injected or datetime.now().isoformat()


# ---------------------------------------------------------------- 服务命令/环境

def service_command(request: dict[str, Any]) -> list[str]:
    """新服务命令行（S0 §9.6 冻结形状：`python -m uvicorn services.api:app --app-dir ...`）。"""
    return [
        sys.executable,
        "-m",
        "uvicorn",
        SERVICE_MODULE,
        "--app-dir",
        str(request["app_dir"]),
        "--host",
        str(request["host"]),
        "--port",
        str(int(request["port"])),
    ]


def service_env(request: dict[str, Any], *, env_root: str, workspace: str,
                base: dict[str, str] | None = None) -> dict[str, str]:
    """新/旧服务的环境：只覆盖环境根、数据根、state 根与端口；其余沿用当前进程。"""
    env = dict(os.environ if base is None else base)
    env["LOOP_ENV_ROOT"] = str(env_root)
    env["LOOP_WORKSPACE"] = str(workspace)
    env["LOOP_STATE_ROOT"] = str(request.get("state_root") or "")
    env["LOOP_PORT"] = str(int(request["port"]))
    env["LOOP_HOST"] = str(request["host"])
    app_dir = str(request.get("app_dir") or "")
    if app_dir:
        previous = env.get("PYTHONPATH")
        env["PYTHONPATH"] = app_dir + (os.pathsep + previous if previous else "")
    return env


def start_service(request: dict[str, Any], *, env_root: str, workspace: str,
                  base_env: dict[str, str] | None = None) -> Any:
    """起一个服务子进程（独立 session；日志追加到 request["log"]）。"""
    log = Path(str(request["log"]))
    log.parent.mkdir(parents=True, exist_ok=True)
    stream = open(log, "ab")
    try:
        return subprocess.Popen(
            service_command(request),
            cwd=str(request.get("app_dir") or None),
            env=service_env(request, env_root=env_root, workspace=workspace, base=base_env),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=stream,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        stream.close()


def stop_service(proc: Any, *, grace_s: float = STOP_GRACE_S) -> None:
    """优雅停子进程：SIGTERM → 宽限 → SIGKILL（异常吞到"进程已不在"为止，其余照常）。"""
    if proc is None:
        return
    try:
        proc.terminate()
    except (OSError, AttributeError):
        return
    try:
        proc.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        proc.kill()
    except (OSError, AttributeError):
        return
    try:
        proc.wait(timeout=grace_s)
    except subprocess.TimeoutExpired:
        return


# ---------------------------------------------------------------- 端口与健康检查

def port_open(host: str, port: int, *, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port_released(host: str, port: int, *, timeout: float, interval: float,
                       sleep: Callable[[float], None] = time.sleep,
                       clock: Callable[[], float] = time.monotonic,
                       probe: Callable[[str, int], bool] = port_open) -> bool:
    """等旧端口释放；释放 ⇒ True，超时仍被占用 ⇒ False（失败路径，不静默继续）。"""
    deadline = clock() + float(timeout)
    while True:
        if not probe(host, int(port)):
            return True
        if clock() >= deadline:
            return False
        sleep(interval)


def fetch_health(host: str, port: int, *, timeout: float = 2.0) -> dict[str, Any]:
    url = f"http://{host}:{int(port)}/api/health"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - 只连本机回环
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"/api/health 返回的不是 JSON 对象：{url}")
    return payload


def probe_health(host: str, port: int, expect_env_root: str, *, timeout: float, interval: float,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 fetch: Callable[[str, int], dict[str, Any]] = fetch_health) -> bool:
    """轮询 `/api/health` 并校验 `env_root == expect`（**唯一判据**：健康且根对）。"""
    deadline = clock() + float(timeout)
    wanted = os.path.realpath(str(expect_env_root))
    while True:
        try:
            payload = fetch(host, int(port))
            if os.path.realpath(str(payload.get("env_root"))) == wanted:
                return True
        except (OSError, ValueError):
            pass  # 服务还没起来 / 还没响应：继续轮询，超时即失败
        if clock() >= deadline:
            return False
        sleep(interval)


# ---------------------------------------------------------------- 结论落盘

def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _append_history(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def decide(request: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """把请求 + 结论合成切换记录：先写 S0 记录投影，再写 active.json，最后清 pending。

    `active.json` 写失败 ⇒ 异常上抛（supervisor 退出 2、pending 保留：显式失败，
    不把"没落盘"伪装成切换成功）。S0 记录投影失败不阻断切换，但必须留痕。
    """
    record = dict(request)
    record.update(decision)
    record["finished_at"] = _now()
    record["record_write_error"] = None
    record_dir = request.get("record_dir")
    if record_dir:
        try:
            _write_json(Path(str(record_dir)) / "env-switch.json", record)
        except OSError as exc:
            record["record_write_error"] = str(exc)
            _log(f"S0 记录投影写入失败（切换结论仍落 active.json）：{exc}")
    _write_json(Path(str(request["active_path"])), record)
    try:
        Path(str(request["pending_path"])).unlink()
    except FileNotFoundError:
        pass
    _append_history(Path(str(request["history_path"])), {
        "at": record["finished_at"],
        "status": record["status"],
        "target_env_root": record.get("target_env_root"),
        "origin_env_root": record.get("origin_env_root"),
        "record_id": record.get("record_id"),
        "reason": record.get("reason"),
        "restored": record.get("restored"),
        "host": record.get("host"),
        "port": record.get("port"),
    })
    return record


def _pid(proc: Any) -> int | None:
    return getattr(proc, "pid", None)


# ---------------------------------------------------------------- 主流程

def run(request: dict[str, Any], *,
        start: Callable[..., Any] = start_service,
        stop: Callable[..., None] = stop_service,
        wait_free: Callable[..., bool] = wait_port_released,
        probe: Callable[..., bool] = probe_health,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """切换决策的唯一实现：成功 ⇒ active，失败 ⇒ 停新服务 + 回退旧根 ⇒ rollback。"""
    host = str(request["host"])
    port = int(request["port"])
    target = str(request["target_env_root"])
    timeouts = dict(DEFAULT_TIMEOUTS)
    timeouts.update(request.get("timeouts") or {})
    _log(f"target={target} port={host}:{port} record={request.get('record_id')}")

    freed = wait_free(host, port, timeout=timeouts["port_s"], interval=timeouts["interval_s"],
                      sleep=sleep, clock=clock)
    if not freed:
        # `wait_port_released` 只在"仍可连"时超时才返回 False ⇒ 旧服务还在正常服务。
        # 此时**不启动新服务**，也不写 restored=false（那等于宣称"服务没了"，是误导）。
        _log("旧端口未释放：旧服务仍在提供服务，不启动新服务")
        return decide(request, {
            "status": "rollback",
            "restored": True,
            "reason": (f"端口未释放：旧服务仍在提供服务（{host}:{port} 在 "
                       f"{timeouts['port_s']}s 内仍可连）"),
            "pid": None,
        })

    _log("旧端口已释放，启动新服务")
    new_proc = None
    reason: str | None = None
    try:
        new_proc = start(request, env_root=target, workspace=str(request["target_workspace"]))
    except OSError as exc:
        reason = f"新服务启动失败：{exc}"

    if reason is None:
        if probe(host, port, target, timeout=timeouts["health_s"], interval=timeouts["interval_s"],
                 sleep=sleep, clock=clock):
            _log("新服务健康检查通过（/api/health 的 env_root == target）")
            return decide(request, {"status": "active", "pid": _pid(new_proc)})
        reason = (f"新服务健康检查未通过：{timeouts['health_s']}s 内 /api/health 的 "
                  "env_root 未达到目标根")

    # ---- 回退：停新服务，用当前（fallback）根按同法重起旧服务
    if new_proc is not None:
        stop(new_proc)
        _log("已停止未就绪的新服务")
    fallback = str(request["fallback_env_root"])
    fallback_workspace = str(request["fallback_workspace"])
    manual = (f"人工恢复：确认 {host}:{port} 无残留进程后，"
              f"以原始根 {fallback} 手动启动服务")
    restored = False
    old_proc = None
    note = ""
    _log(f"回退：以 {fallback} 重起旧服务")
    try:
        old_proc = start(request, env_root=fallback, workspace=fallback_workspace)
    except OSError as exc:
        note = f"；回退服务启动失败：{exc}；{manual}"
    if old_proc is not None:
        restored = probe(host, port, fallback, timeout=timeouts["health_s"],
                         interval=timeouts["interval_s"], sleep=sleep, clock=clock)
        if not restored:
            # 不健康的回退进程会占着端口变成僵尸，必须停掉再交给人工恢复。
            stop(old_proc)
            _log("已停止未就绪的回退服务进程")
            note += f"；回退服务健康检查未通过，已停止该进程；{manual}"
    decision = {
        "status": "rollback",
        "reason": reason + note,
        "restored": bool(restored),
        # 未恢复时那个回退进程已被告知停止 ⇒ 不把它的 pid 当成"在跑的服务"（避免误导）。
        "pid": _pid(old_proc) if restored else None,
        "attempted_pid": _pid(old_proc),
    }
    _log(f"回滚结论：{decision['reason']}")
    return decide(request, decision)


# ---------------------------------------------------------------- CLI

def load_request(spec: str) -> dict[str, Any]:
    """`--pending` 接受 pending.json 路径或内联 JSON（单测/手工复演都方便）。"""
    raw = Path(spec)
    try:
        is_file = raw.is_file()
    except OSError:
        is_file = False
    text = raw.read_text(encoding="utf-8") if is_file else spec
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--pending 既不是可读的 JSON 文件，也不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("--pending 顶层必须是 JSON 对象")
    return payload


def stamp_pending(request: dict[str, Any]) -> bool:
    """把 supervisor 自己的 pid/启动时刻写回 pending.json（API 端**活判**的唯一依据）。

    必须在**任何等待之前**执行：API 端据此用 `host.admission.proc_state_start` 判活
    （进程不存在/僵尸 ⇒ 自动清 pending；活着 ⇒ 409 并给 pid + 已等待时长）。
    缺少 `supervisor_pid` 的 pending 视为历史/手写 ⇒ **不可活判**（不猜，走人工清理）。

    写失败**不阻断**切换（日志显式说明），只让活判退化为"不可活判"。
    本函数只写 pending（不含路径推导）：路径来自 request，与 `host.env_switch` 同一来源。
    """
    raw = request.get("pending_path")
    if not raw:
        _log("pending 无 pending_path：跳过 supervisor 活判戳")
        return False
    stamped = dict(request)
    stamped.update({
        "supervisor_pid": os.getpid(),
        "supervisor_started_ts": time.time(),
        "supervisor_started_at": _now(),
    })
    try:
        _write_json(Path(str(raw)), stamped)
    except OSError as exc:
        _log(f"pending 活判戳写入失败（切换继续，API 端将视为不可活判）：{exc}")
        return False
    request.update(stamped)
    _log(f"supervisor pid={os.getpid()} 已写入 pending（活判依据）")
    return True


def main(argv: Sequence[str] | None = None,
         *, runner: Callable[..., dict[str, Any]] = run) -> int:
    """退出码：0 = active，1 = rollback（回退后旧服务已重起），2 = supervisor 自身异常。"""
    parser = argparse.ArgumentParser(description="环境根切换 supervisor（S0 §9.6）")
    parser.add_argument("--pending", required=True, help="pending.json 路径或内联 JSON")
    args = parser.parse_args(argv)
    request = load_request(args.pending)
    # 活判戳先落盘：此后任何时刻 API 端都能确定"这个 pending 还有没有活 supervisor"。
    stamp_pending(request)
    try:
        record = runner(request)
    except Exception as exc:  # noqa: BLE001 - 独立进程：任何异常都要显式失败并留日志
        print(f"[switch] supervisor 异常：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2
    print(json.dumps({key: record.get(key) for key in
                      ("status", "target_env_root", "reason", "restored", "pid")},
                     ensure_ascii=False), flush=True)
    return 0 if record.get("status") == "active" else 1


if __name__ == "__main__":  # pragma: no cover - 子进程入口
    raise SystemExit(main())
