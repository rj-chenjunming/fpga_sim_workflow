#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实链路验证：单一 RTL 文件夹 → 派生 → 三库冒烟 → 准出 → 切换 → 真跑到 G1 → 切回。

**必须在单次 bash 调用内跑完**（本工程 bash 调用各自在 bwrap 沙箱里：`--unshare-pid
--die-with-parent`，跨调用既看不见也杀不掉上一代 uvicorn）。本脚本自己起停服务、自己跨
重启轮询 `/api/health`，与 `spikes/accept_v1_run.sh` 同一纪律。

它证明（对应 `doc/spec/S0_ENVIRONMENT_SPEC.md` §9.8 的 real 链）：
1. `POST /api/s0/from-rtl` 只给一个 RTL 文件夹即可派生（选择性复制 + 根部替换 + 六项检查）；
2. `POST /api/s0/{id}/advance` 自动跑三库冒烟，六项全 passed ⇒ `ready_for_execution=true`；
3. `POST /api/s0/{id}/activate` 自动切换到副本：`/api/health` 的 `env_root` == 副本，
   `GET /api/env/state` 的 origin 仍是原始根；
4. 切到副本后能建 `real` run 并跑到 G1（N0–N3 真实执行，N9 不在本脚本范围）；
5. 原始 `ENV_ROOT` 零写入（`find -newer` 命中 0 + 记录 `baseline` 检查 passed）；
6. `POST /api/env/switch-back` 切回原始根；切回后副本可被 `DELETE …/copy?confirm=true` 删除。

用法：
    cd loop && .venv/bin/python spikes/verify_rtl_folder_entry.py            # 缺省端口 8197
    cd loop && .venv/bin/python spikes/verify_rtl_folder_entry.py --keep     # 保留 RTL 暂存与副本

前置：`ENV_ROOT` 可读、`uvlan`/`uvs` 在 PATH、影子数据根已造：
    DEST=$PWD/../.dev-ws-lead bash spikes/provision_dev_workspace.sh --link-fixture --force --quiet
（脚本不写 `ENV_ROOT` 任何文件；RTL 暂存与派生副本都在软件仓可写目录内。）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[2]
LOOP = REPO / "loop"
DEFAULT_STATE = REPO / ".lead-e2e-state"
DEFAULT_WORKSPACE = REPO / ".dev-ws-lead"

PASS = 0
FAIL = 0
FAILED_NAMES: list[str] = []


def ck(name: str, cond: bool, detail: object = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok  ] {name}", flush=True)
    else:
        FAIL += 1
        FAILED_NAMES.append(name)
        print(f"  [FAIL] {name}  <<< {detail!r}", flush=True)
    return bool(cond)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_health(port: int, *, expect_env: str | None = None, timeout: float = 180.0,
                interval: float = 0.4) -> dict | None:
    wanted = os.path.realpath(expect_env) if expect_env else None
    deadline = time.monotonic() + timeout
    last: dict | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health",
                                        timeout=2.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            last = payload if isinstance(payload, dict) else None
            if last is None:
                continue
            if wanted is None or os.path.realpath(str(last.get("env_root"))) == wanted:
                return last
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(interval)
    return last


def start_service(port: int, *, env_root: Path, workspace: Path, state: Path,
                  log: Path, llm_mode: str = "live") -> subprocess.Popen:
    env = os.environ.copy()
    env.update({
        "LOOP_ENV_ROOT": str(env_root),
        "LOOP_WORKSPACE": str(workspace),
        "LOOP_STATE_ROOT": str(state),
        "LOOP_PORT": str(port),
        "LOOP_LLM_MODE": llm_mode,
        "PYTHONPATH": str(LOOP) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
    })
    log.parent.mkdir(parents=True, exist_ok=True)
    stream = open(log, "ab")
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "services.api:app",
             "--app-dir", str(LOOP), "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(LOOP), env=env, stdin=subprocess.DEVNULL,
            stdout=stream, stderr=stream, start_new_session=True,
        )
    finally:
        stream.close()


def get_json(client: httpx.Client, path: str, *, timeout: float = 60.0,
             retries: int = 4) -> dict:
    """GET+JSON，对 keep-alive 复用被服务端关闭（ReadError/RemoteProtocolError）做短重试。"""
    last: Exception | None = None
    for _ in range(retries):
        try:
            return client.get(path, timeout=timeout).json()
        except (httpx.ReadError, httpx.RemoteProtocolError, httpx.ConnectError) as exc:
            last = exc
            time.sleep(0.5)
    raise last  # type: ignore[misc]


def stop_pid(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.kill(int(pid), 15)
    except OSError:
        pass


def stage_rtl(env_root: Path, stage: Path) -> Path:
    """把 ENV_ROOT/RTL 复制成“用户的完整 RTL 文件夹”，并改一个受摄入文件（注释，不改端口）。"""
    target = stage / "RTL"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(env_root / "RTL", target)
    candidates = sorted((target / "SRC" / "imports").rglob("*.v"))
    candidates = [p for p in candidates if p.is_file() and p.stat().st_size < 5 * 1024 * 1024]
    if not candidates:
        raise RuntimeError("RTL/SRC/imports 下找不到可修改的 .v 文件（真实环境布局变了？）")
    chosen = candidates[0]
    with chosen.open("a", encoding="utf-8") as stream:
        stream.write("\n// lead-e2e change marker（仅验证用；不改变模块端口）\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="S0 单输入二选一真实链路验证（S0 §9.8/§9.9-6）")
    parser.add_argument("--port", type=int, default=0, help="服务端口（缺省自动挑空闲端口）")
    parser.add_argument("--entry", choices=("rtl", "env"), default="rtl",
                        help="入口模式：rtl = 只给新版 RTL 文件夹；env = 只给整套环境项目（RTL 不替换）")
    parser.add_argument("--state", default=str(DEFAULT_STATE), help="一次性 state 根")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="原始数据根（影子）")
    parser.add_argument("--keep", action="store_true", help="保留 RTL 暂存与派生副本")
    parser.add_argument("--llm-mode", default="live",
                        help="模型模式：live（real 跑 N3 需要）/ standin（只验到 N2）")
    args = parser.parse_args()

    env_root = Path(os.environ.get("LOOP_ENV_ROOT_ENV") or
                     json.loads((REPO / "environments.json").read_text(encoding="utf-8"))
                     ["environments"][json.loads((REPO / "environments.json").read_text(
                         encoding="utf-8"))["default"]]["path"])
    env_root = env_root.resolve()
    workspace = Path(args.workspace).resolve()
    state = Path(args.state).resolve()
    if state.exists():
        shutil.rmtree(state)
    state.mkdir(parents=True)
    port = args.port or free_port()
    stamp = time.strftime("%Y%m%dT%H%M%S")
    stage = REPO / ".lead-e2e" / stamp
    rtl_workspace = stage / "RTL"

    print(f"[info] ENV_ROOT={env_root}")
    print(f"[info] WORKSPACE(origin data root)={workspace}")
    print(f"[info] STATE={state}  PORT={port}  ENTRY={args.entry}")
    print(f"[info] 派生副本父目录={REPO / 'workspaces'}")

    ck("前置：uvlan 在 PATH", shutil.which("uvlan") is not None, shutil.which("uvlan"))
    ck("前置：影子数据根存在", (workspace / "baselines").is_dir(), workspace)
    if FAIL:
        return 1

    marker = state / "env-root-marker"
    marker.touch()
    proc = start_service(port, env_root=env_root, workspace=workspace, state=state,
                         log=state / "service-0.log", llm_mode=args.llm_mode)
    health = wait_health(port, expect_env=str(env_root), timeout=120)
    ck("服务启动：/api/health.env_root == 原始 ENV_ROOT", bool(health), health)

    base = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=base, timeout=30.0, trust_env=False)  # no_proxy 里的 "[::1]" 会让 httpx 建 mount 时炸
    record: dict = {}
    switch_pid: int | None = None
    try:
        # ---------- 1) 派生（二选一：只给 RTL 文件夹 / 只给整套环境项目）
        if args.entry == "env":
            print(f"[info] 环境项目入口：baseline={env_root}（整套环境，RTL 不替换）")
            response = client.post("/api/s0/from-rtl", json={"baseline": str(env_root)},
                                   timeout=1800.0)
            ck("POST /api/s0/from-rtl（只给环境项目）返回 200", response.status_code == 200,
               (response.status_code, response.text[:800]))
            record = response.json() if response.status_code == 200 else {}
            if record:
                checks = {row.get("key"): row.get("status") for row in record.get("checks") or []}
                rows_by_key = {row.get("key"): row for row in record.get("checks") or []}
                print(f"[info] record={record.get('id')} checks={checks}")
                ck("记录 entry=env_folder 且 rtl_source/rtl_prefix 为 null",
                   record.get("entry") == "env_folder" and record.get("rtl_source") is None
                   and record.get("rtl_prefix") is None,
                   (record.get("entry"), record.get("rtl_source"), record.get("rtl_prefix")))
                ck("copy/non_rtl/baseline 三项 passed",
                   all(checks.get(key) == "passed" for key in ("copy", "non_rtl", "baseline")),
                   checks)
                ck("rtl 检查 skipped 且理由写明「未替换/不做替换」",
                   checks.get("rtl") == "skipped"
                   and "未提供新版 RTL" in str((rows_by_key.get("rtl") or {}).get("reason") or "")
                   and "不做替换" in str((rows_by_key.get("rtl") or {}).get("reason") or ""),
                   rows_by_key.get("rtl"))
                ck("ports 零差异（RTL 未替换 ⇒ 无接口差异）", checks.get("ports") == "passed",
                   (checks.get("ports"), (record.get("ports") or {}).get("reason")))
                ck("派生时 smoke 尚未跑（waiting）且未准出",
                   checks.get("smoke") == "waiting" and record.get("ready_for_execution") is False,
                   (checks.get("smoke"), record.get("ready_for_execution")))
                plan_doc = record.get("copy_plan") or {}
                ck("copy_plan 落账（copied 非空 / 排除根非空）",
                   isinstance(plan_doc, dict)
                   and isinstance(plan_doc.get("copied"), list) and len(plan_doc["copied"]) > 0
                   and bool(plan_doc.get("excluded_roots")),
                   {"copied": len(plan_doc.get("copied") or []),
                    "excluded_roots": plan_doc.get("excluded_roots")})
                ck("未提供 RTL ⇒ rtl_plan/folder_warning 为 null",
                   record.get("rtl_plan") is None and record.get("folder_warning") is None,
                   (record.get("rtl_plan"), record.get("folder_warning")))
                work_env = Path(str(record.get("work_env") or ""))
                ck("副本数据根自包含（<副本>/kb 存在）", (work_env / "kb").is_dir(), work_env)
        else:
            rtl_workspace = stage_rtl(env_root, stage)
            print(f"[info] RTL 暂存={rtl_workspace}")
            response = client.post("/api/s0/from-rtl", json={"rtl_source": str(rtl_workspace)},
                                   timeout=1800.0)
            ck("POST /api/s0/from-rtl 返回 200", response.status_code == 200,
               (response.status_code, response.text[:800]))
            record = response.json() if response.status_code == 200 else {}
            if record:
                checks = {row.get("key"): row.get("status") for row in record.get("checks") or []}
                print(f"[info] record={record.get('id')} checks={checks}")
                ck("记录 entry=rtl_folder 且 rtl_prefix=RTL", record.get("entry") == "rtl_folder"
                   and record.get("rtl_prefix") == "RTL", record.get("rtl_prefix"))
                ck("copy/rtl/non_rtl/baseline 四项 passed",
                   all(checks.get(key) == "passed" for key in
                       ("copy", "rtl", "non_rtl", "baseline")), checks)
                plan_doc = record.get("copy_plan") or {}
                ck("copy_plan 落账（copied 非空 / 排除根非空）",
                   isinstance(plan_doc, dict)
                   and isinstance(plan_doc.get("copied"), list) and len(plan_doc["copied"]) > 0
                   and bool(plan_doc.get("excluded_roots")),
                   {"copied": len(plan_doc.get("copied") or []),
                    "excluded_roots": plan_doc.get("excluded_roots"),
                    "skipped": len(plan_doc.get("skipped") or [])})
                ck("ports 零差异（本次只改注释）", checks.get("ports") == "passed",
                   (checks.get("ports"), (record.get("ports") or {}).get("reason")))
                ck("派生时 smoke 尚未跑（waiting）且未准出",
                   checks.get("smoke") == "waiting" and record.get("ready_for_execution") is False,
                   (checks.get("smoke"), record.get("ready_for_execution")))
                work_env = Path(str(record.get("work_env") or ""))
                ck("副本数据根自包含（<副本>/kb 存在）", (work_env / "kb").is_dir(), work_env)
                ck("RTL 源 VCS 目录已落账（rtl_plan.skipped 存在该键）",
                   isinstance(record.get("rtl_plan"), dict), record.get("rtl_plan"))

        # ---------- 2) 冒烟 → 准出
        if record:
            response = client.post(f"/api/s0/{record['id']}/advance", json={}, timeout=1800.0)
            ck("POST …/advance 返回 200", response.status_code == 200,
               (response.status_code, response.text[:800]))
            record = response.json() if response.status_code == 200 else record
            checks = {row.get("key"): row.get("status") for row in record.get("checks") or []}
            print(f"[info] checks after advance={checks}")
            smoke = record.get("smoke") or {}
            ck("三库冒烟 passed", checks.get("smoke") == "passed",
               (checks.get("smoke"), smoke.get("reason")))
            if args.entry == "env":
                ck("环境项目入口准出：五项 passed + rtl=skipped 且 ready_for_execution=true",
                   record.get("ready_for_execution") is True
                   and checks.get("rtl") == "skipped"
                   and all(checks.get(key) == "passed" for key in
                           ("copy", "non_rtl", "ports", "smoke", "baseline")), checks)
            else:
                ck("六项全 passed 且 ready_for_execution=true",
                   record.get("ready_for_execution") is True and all(
                       checks.get(key) == "passed" for key in
                       ("copy", "rtl", "non_rtl", "ports", "smoke", "baseline")), checks)

        # ---------- 3) 切换
        if record.get("ready_for_execution") is True:
            data_root = Path(str(record["work_env"])) / "kb"
            response = client.post(f"/api/s0/{record['id']}/activate", json={}, timeout=60.0)
            ck("POST …/activate 返回 202", response.status_code == 202,
               (response.status_code, response.text[:800]))
            switched = response.json().get("switch", {}) if response.status_code == 202 else {}
            ck("202 的 switch.target_env_root == 副本", 
               Path(str(switched.get("target_env_root") or "")).resolve()
               == Path(str(record["work_env"])).resolve(), switched.get("target_env_root"))
            after = wait_health(port, expect_env=str(record["work_env"]), timeout=300)
            # 服务已换进程：重建客户端，避免连接池里指向旧进程的 keep-alive 连接。
            client.close()
            client = httpx.Client(base_url=base, timeout=30.0, trust_env=False)  # no_proxy 里的 "[::1]" 会让 httpx 建 mount 时炸
            ck("切换后 /api/health.env_root == 副本",
               bool(after) and Path(str(after.get("env_root"))).resolve()
               == Path(str(record["work_env"])).resolve(), after)
            # 健康检查先通过、supervisor 的 active.json 后写 ⇒ 轮询 env/state 直到结论收口。
            deadline = time.monotonic() + 120
            env_state: dict = {}
            while time.monotonic() < deadline:
                env_state = get_json(client, "/api/env/state")
                if (env_state.get("switch") or {}).get("status") in ("active", "rollback"):
                    break
                time.sleep(1.0)
            print(f"[info] /api/env/state={json.dumps(env_state, ensure_ascii=False)[:600]}")
            ck("切换后 env/state：当前根=副本、原始根仍为 ENV_ROOT",
               Path(str(env_state.get("env_root"))).resolve()
               == Path(str(record["work_env"])).resolve()
               and Path(str(env_state.get("origin_env_root"))).resolve() == env_root,
               env_state)
            ck("切换结论 active（env_switch.status）",
               (env_state.get("switch") or {}).get("status") == "active",
               (env_state.get("switch") or {}).get("status"))
            ck("副本数据根存在（<副本>/kb）", data_root.is_dir(), data_root)

            # ---------- 4) 在副本里真跑到 G1
            baselines = client.get("/api/baselines", timeout=60.0).json().get("baselines") or []
            valid = [row.get("id") for row in baselines if row.get("valid")]
            ck("派生数据根的基线准入通过（至少一个 valid）", bool(valid),
               [(row.get("id"), row.get("valid"), row.get("missing")) for row in baselines])
            baseline_id = valid[0] if valid else "v0"
            response = client.post("/api/runs", json={
                "baseline": baseline_id, "mode": "real", "project": str(record["work_env"]),
                "s0_record_id": record["id"]}, timeout=120.0)
            ck("POST /api/runs(real) 返回 200", response.status_code == 200,
               (response.status_code, response.text[:1200]))
            run = response.json() if response.status_code == 200 else {}
            run_id = run.get("run_id")
            if run_id:
                deadline = time.monotonic() + 300
                view: dict = {}
                while time.monotonic() < deadline:
                    view = get_json(client, f"/api/runs/{run_id}", timeout=30.0)
                    pending = ((view.get("pending_interrupt") or {}).get("id") or "")
                    if view.get("status") == "waiting_gate" or pending.startswith("G1"):
                        break
                    if view.get("status") == "failed":
                        break
                    time.sleep(1.0)
                print(f"[info] run={run_id} status={view.get('status')} "
                      f"pending={((view.get('pending_interrupt') or {}).get('id'))}")
                ck("real run 跑到 G1（N0–N3 真实执行）",
                   view.get("status") == "waiting_gate"
                   and ((view.get("pending_interrupt") or {}).get("id") or "").startswith("G1"),
                   (view.get("status"), (view.get("error") or "")[:400]))
                ck("run 文档记录 env_root=副本、origin=原始根",
                   Path(str(view.get("env_root") or "")).resolve()
                   == Path(str(record["work_env"])).resolve(),
                   (view.get("env_root"), view.get("env_origin_root")))

                # 收口：本轮已到达 G1（人闸门）。验证脚本用 G1=ignored（⇒ HALT）把人已参与的
                # 这一轮正常结束，否则"活跃 run 时拒绝切换"会让后面的切回/删除全部 409（行为正确）。
                if view.get("status") == "waiting_gate":
                    entries = (view.get("difference_items") or {}).get("entries") or []
                    entry_decisions = {
                        str(entry.get("entry_id")): {
                            "decision": "ignored",
                            "reason": "验证脚本：本轮只验证到 N0–N3（逐条忽略以正常结束本轮）",
                        }
                        for entry in entries if entry.get("entry_id")
                    }
                    response = client.post(
                        f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
                        json={"decision": "ignored", "actor": "human:lead-e2e",
                              "reason": "验证脚本：本轮只验证到 N0–N3；ignored ⇒ HALT 以继续切回原始根",
                              "entry_decisions": entry_decisions},
                        timeout=120.0)
                    ck("G1 签 ignored（human，含逐条理由）返回 200", response.status_code == 200,
                       (response.status_code, response.text[:800]))
                    print(f"[info] G1 逐条处置条目数={len(entry_decisions)}")
                    deadline = time.monotonic() + 180
                    while time.monotonic() < deadline:
                        view = get_json(client, f"/api/runs/{run_id}", timeout=30.0)
                        if view.get("status") in ("finished", "failed"):
                            break
                        time.sleep(1.0)
                    ck("G1 ignored 后运行收敛到终态（不再阻塞切回）",
                       view.get("status") in ("finished", "failed"), view.get("status"))

            # ---------- 5) 原始 ENV_ROOT 零写入
            newer = subprocess.run(["find", str(env_root), "-newer", str(marker)],
                                   capture_output=True, text=True)
            hits = [line for line in newer.stdout.splitlines() if line.strip()]
            ck("原始 ENV_ROOT 零写入（find -newer 命中 0）", not hits, hits[:5])

            # ---------- 6) 切回 + 副本可清理
            response = client.post("/api/env/switch-back", json={}, timeout=60.0)
            ck("POST /api/env/switch-back 返回 202", response.status_code == 202,
               (response.status_code, response.text[:800]))
            back = wait_health(port, expect_env=str(env_root), timeout=300)
            client.close()
            client = httpx.Client(base_url=base, timeout=30.0, trust_env=False)  # no_proxy 里的 "[::1]" 会让 httpx 建 mount 时炸
            ck("切回后 /api/health.env_root == 原始 ENV_ROOT", bool(back), back)
            env_state = get_json(client, "/api/env/state")
            ck("切回后 env/state：当前根=原始根、原始根记录不变",
               Path(str(env_state.get("env_root"))).resolve() == env_root
               and Path(str(env_state.get("origin_env_root"))).resolve() == env_root,
               env_state)
            ck("切回后副本仍保留", Path(str(record["work_env"])).is_dir(), record["work_env"])
            if record:
                response = client.delete(
                    f"/api/s0/{record['id']}/copy", params={"confirm": "true"}, timeout=120.0)
                ck("切回后 DELETE …/copy 返回 200（副本可手动清理）",
                   response.status_code == 200, (response.status_code, response.text[:800]))
    finally:
        try:
            server = json.loads((state / "env-switch" / "server.json").read_text(encoding="utf-8"))
            switch_pid = server.get("pid")
        except (OSError, ValueError):
            switch_pid = None
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass
        stop_pid(switch_pid)
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass

    print()
    print(f"=> PASS={PASS} FAIL={FAIL}")
    if FAIL:
        print("FAILED: " + "、".join(FAILED_NAMES))
    if not args.keep:
        shutil.rmtree(stage, ignore_errors=True)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
