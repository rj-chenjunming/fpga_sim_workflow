"""FastAPI 边界：闸门操作台 + 长任务看板。

定位（spec §1 / §10.2）：**UI 是 ExecutionExchange 适配器，不是权威**。
本层负责准入、投影、转交操作；闸门归 `kb/tools/gate.py`，S0 派生归 `host/s0.py`。
**不实现自己的状态机**。

启动时 `async_restore_all()`：重新判定作业命运并从快照恢复执行
（快照里的 `running` 帧会让 `load` fail-closed，所以恢复前执行必须已停放）。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, NoReturn

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from host import env_switch
from host import paths as P
from host.progress import ALLOWED_KINDS, ProgressLog
from services import case_override, instance_proxy, node_view
from workflows.main_flow import RunManager, get_manager

import agently  # noqa: F401  (用于 /api/health 报版本)


def _manager() -> RunManager:
    return get_manager()


#: 派生副本的唯一父目录（S0 §9.1）；删除副本的包含性判据也用它（唯一来源，红线 8）
COPIES_ROOT: Path = P.TOOL_ROOT / "workspaces"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 切换链启动自检（S0 §9.6）：
    # ① 记录本进程服务信息（supervisor/界面据此定位 pid/port/host/app_dir）；
    # ② 首次启动时把**当前**环境根记为 origin（之后不变；有 active 切换说明本进程
    #    自己就是被切过去的副本，绝不能把副本记成原始根）。
    env_switch.record_server()
    if env_switch.origin_env_root() is None and env_switch.active() is None:
        env_switch.record_origin(P.ENV_ROOT, workspace_root=P.WORKSPACE_ROOT)
    manager = _manager()
    report = await manager.async_restore_all()
    app.state.restore_report = report
    yield
    await manager.stop_watching()


app = FastAPI(title="变更影响闭环 · 编排层", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------- health

@app.get("/api/health")
def health() -> dict[str, Any]:
    import importlib.metadata as md

    from host import model_provider as MP

    # 切换摘要（只增键，不改既有键）：origin_env_root + 最近/进行中的切换。
    # 状态文件损坏不能让健康检查整体 500（服务还活着），但必须外显"不可读"。
    try:
        origin_env_root = env_switch.origin_env_root()
        switch_summary: dict[str, Any] | None = env_switch.summary()
    except ValueError as exc:
        origin_env_root = None
        switch_summary = {"status": "unreadable", "error": str(exc)}
    return {
        "ok": True,
        "repo_root": str(P.REPO_ROOT),
        # 拆仓后的三根与插件自检（界面/验收据此判断"环境是否挂上"）
        "tool_root": str(P.TOOL_ROOT),
        "env_root": str(P.ENV_ROOT),
        "env_id": P.ENV_ID,
        "workspace_root": str(P.WORKSPACE_ROOT),
        "plugin_missing": P.missing_plugin_parts(),
        # 工作区数据是否找得到（指错地方时症状是"索引缺口"，必须在健康检查里说清）
        "workspace_missing": P.missing_workspace_parts(),
        "agently": md.version("agently"),
        "python": sys.version.split()[0],
        # 模型 provider 状态（**不含密钥**）：界面据此显示"模型节点是 live 还是替身"
        "llm": MP.status(),
        # 事件 kind 白名单的**唯一权威**（SPEC-02 §9）：/api/health 下发，界面消费，不手抄。
        "event_kinds": sorted(ALLOWED_KINDS),
        "restore_report": getattr(app.state, "restore_report", None) if hasattr(app, "state") else None,
        "server_authority": "闸门态权威在 kb/tools/gate.py（gate_state + anchor）；界面与 HTTP 层都是只读投影 + 传输。",
        # S0 §9.6：切换后健康检查必须显示新根；原始根恒为派生源（决定 17）。
        "origin_env_root": str(origin_env_root) if origin_env_root is not None else None,
        "switch": switch_summary,
    }


# ---------------------------------------------------------------- 配置面（只读）

@app.get("/api/baselines")
def baselines_api() -> dict[str, Any]:
    """列出数据根下的基线版本（只读；供配置视图选择）。"""
    from services import config_api

    return config_api.list_baselines(P.WORKSPACE_ROOT)


@app.get("/api/env/check")
def env_check_api(path: str = Query(...)) -> dict[str, Any]:
    """只读校验候选环境仓根；不创建、不修改任何文件。"""
    from services import config_api

    registry = config_api.load_registry(P.TOOL_ROOT / "environments.json")
    try:
        return config_api.check_env(path, registry=registry, current_env_root=P.ENV_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


@app.get("/api/fs/dirs")
def fs_dirs_api(path: str = Query(...)) -> dict[str, Any]:
    """列出一层目录；allowlist 见 config_api.allowed_roots（realpath 越界 ⇒ 403）。"""
    from services import config_api

    registry = config_api.load_registry(P.TOOL_ROOT / "environments.json")
    roots = config_api.allowed_roots(
        registry,
        P.WORKSPACE_ROOT,
        settings_path=P.TOOL_ROOT / "loop" / "SETTINGS.yaml",
    )
    try:
        return config_api.list_dirs(path, allowed_roots=roots, registry=registry)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail={"error": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


# ---------------------------------------------------------------- S0 preparation (separate from existing runs)

def _s0_store():
    from host.s0 import S0Store
    from services import config_api
    registry = config_api.load_registry(P.TOOL_ROOT / 'environments.json')
    # STATE_DIR 是 S0-rehearsal 输入/副本的根：必须在允许根内，否则 `_path` 会误拒。
    # COPIES_ROOT 是派生副本的唯一父目录（S0 §9.1 默认 work_env 落点；from-rtl 的
    # target_parent 与删除守卫共用它，避免"能派生却不在允许根内"）。
    roots = config_api.allowed_roots(registry, P.WORKSPACE_ROOT,
                                     settings_path=P.LOOP_DIR / 'SETTINGS.yaml',
                                     extra=[P.ENV_ROOT, P.STATE_DIR, COPIES_ROOT])
    return S0Store(P.STATE_DIR / 's0', roots)


@app.get('/api/s0')
def s0_index():
    store = _s0_store()
    return {'baseline': str(P.ENV_ROOT), 'allowed_roots': [str(p) for p in store.allowed_roots],
            'records': store.list(),
            # rehearsal=True 只说明"可以点一次本机演练"，不表示环境就绪。
            # 2026-10-27：S0-b 的 tb_adapt / smoke 后端已接入（派生+提议/确认+落盘、三库编译冒烟+基线增量）；
            # 界面（D5）仍显示灰态，故这里描述的是**后端能力**，不是界面状态。
            'capabilities': {'prepare': True, 'rehearsal': True, 'tb_adapt': True, 'smoke': True,
                             # from_rtl 反映 T1 冻结接口是否已接入（未接入 ⇒ 该端点 501，
                             # 界面据此禁用"派生并校验 →"；API 层不实现第二套派生逻辑）。
                             'from_rtl': hasattr(store, 'prepare_from_rtl'),
                             'env_switch': True}}


@app.post('/api/s0')
async def s0_prepare(payload: dict[str, Any] = Body(default={})):
    from host.s0 import PreparationFailed
    try:
        return await asyncio.to_thread(_s0_store().prepare, payload)
    except FileExistsError as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(403, detail={'error': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    except PreparationFailed as exc:
        raise HTTPException(422, detail={'error': str(exc), 'record': exc.record}) from exc
    except OSError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


@app.post('/api/s0/rehearsal')
async def s0_rehearsal(payload: dict[str, Any] = Body(default={})):
    """S0-rehearsal：一次性的"copy → 整体替换 RTL → 核验"，只证明链路可走。

    - **不接受任何客户端路径**（防任意写）：body 只允许可选 `now`（含时区 ISO 时间），
      其余键一律 400；输入由 Host 在软件 state 目录下自造。
    - 记录写进 `STATE_DIR/s0/`（与真实 S0 记录同源），每次点击都是新记录、新目录。
    - 不写 `ENV_ROOT`、不签闸门、不改变运行；`ready_for_execution` 仍恒 false（S0-b 未接入）。
    - 失败沿用既有 `PreparationFailed` 语义：`status=failed` + `error` + 422（记录保留）。
    """
    from host.s0 import PreparationFailed
    unknown = sorted(str(key) for key in payload if key != 'now')
    if unknown:
        raise HTTPException(400, detail={'error': (
            'S0 演练不接受客户端路径参数：' + '、'.join(unknown)
            + '；只允许可选 now（含时区 ISO 时间），演练输入由服务端在软件 state 下自造')})
    try:
        return await asyncio.to_thread(_s0_store().rehearse, payload.get('now'))
    except FileExistsError as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except PermissionError as exc:
        raise HTTPException(403, detail={'error': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    except PreparationFailed as exc:
        raise HTTPException(422, detail={'error': str(exc), 'record': exc.record}) from exc
    except OSError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


# ---------------------------------------------------------------- RTL 文件夹一键入口（S0 §9）

#: 非终态 run（停放态与运行中都算"占着环境"；决定 14：活跃 run 拒绝派生/切换）
RUN_ACTIVE_STATUSES = frozenset({"running", "waiting_gate", "waiting_job", "waiting_slot"})


def _active_runs() -> list[dict[str, Any]]:
    return [run for run in _manager().list_runs() if run.get("status") in RUN_ACTIVE_STATUSES]


def _reject_if_active_runs(action: str) -> None:
    """活跃 run 时拒绝派生/切换：拒绝发生在任何写盘之前（AGENTS.md §2 硬性纪律 5）。"""
    active = _active_runs()
    if not active:
        return
    shown = "、".join(f"{run.get('run_id')}({run.get('status')})" for run in active[:5])
    more = f" 等 {len(active)} 个" if len(active) > 5 else ""
    raise HTTPException(409, detail={"error": (
        f"存在非终态运行，拒绝{action}：{shown}{more}；请等运行结束或先收口。")})


def _s0_error_from_rtl(exc: Exception) -> NoReturn:
    """from-rtl 的错误映射（S0 §9.1/§9.2）：403 = 路径不在允许根，409 = 目标占用。

    注意与既有 S0-b 的 `_s0_call` 口径不同（那里 PermissionError ⇒ 400）：
    本端点的 403 是"客户端给的浏览路径越界"，必须让人看见"没权限访问这个目录"。
    """
    from host.s0 import PreparationFailed

    if isinstance(exc, FileExistsError):
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, detail={'error': str(exc)}) from exc
    if isinstance(exc, PreparationFailed):
        raise HTTPException(422, detail={'error': str(exc), 'record': exc.record}) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    if isinstance(exc, OSError):
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    raise exc


@app.post('/api/s0/from-rtl')
async def s0_from_rtl(payload: dict[str, Any] = Body(default={})):
    """S0 §9.9：**单输入二选一** —— 只给 `rtl_source`（新版 RTL 文件夹）或只给 `baseline`（环境项目目录）。

    两者都给 = 环境项目 + 新版 RTL（兼容保留，界面不展示）；都为空 = 400（由 Host 判据给出可读理由）。
    本层只做三件事：把**原始根**作为默认基线源传下去、把副本父目录限定到 `COPIES_ROOT`、
    把 `ValueError/PermissionError/FileExistsError/PreparationFailed/OSError` 映射成既有
    400/403/409/422。**派生逻辑只有一份（T1）**，这里不实现第二套，也不在此判定模式。
    """
    store = _s0_store()
    prepare = getattr(store, 'prepare_from_rtl', None)
    if prepare is None:
        # T1 冻结接口未落地：显式 501，不伪造 200、不在此处补一份派生。
        raise HTTPException(501, detail={'error': (
            'S0Store.prepare_from_rtl 尚未接入（T1 冻结接口）；本端点只委派，'
            '不在 API 层实现第二套派生逻辑。')})
    _reject_if_active_runs('派生新副本')
    try:
        origin = env_switch.origin_env_root() or Path(P.ENV_ROOT)
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    try:
        return await asyncio.to_thread(
            prepare, payload,
            default_baseline=origin,
            origin_env_root=origin,
            target_parent=COPIES_ROOT,
        )
    except Exception as exc:  # noqa: BLE001 - 映射集中在 `_s0_error_from_rtl`（未知异常原样上抛）
        _s0_error_from_rtl(exc)


@app.post('/api/s0/{record_id}/advance')
def s0_advance(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0 §9.5-2/3：端口处置完后继续（T1 的 `advance` 在 ports=passed 时自动跑一次冒烟）。"""
    from host.s0 import PreparationFailed

    store = _s0_store()
    advance = getattr(store, 'advance', None)
    if advance is None:
        raise HTTPException(501, detail={'error': 'S0Store.advance 尚未接入（T1 冻结接口）'})
    try:
        return advance(record_id, smoke_case=payload.get('smoke_case') or None,
                       now=payload.get('now'))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={'error': '准备记录不存在'}) from exc
    except FileExistsError as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    except PreparationFailed as exc:
        raise HTTPException(422, detail={'error': str(exc), 'record': exc.record}) from exc
    except OSError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


# ---------------------------------------------------------------- 环境根切换（S0 §9.6）

def _shutdown_process() -> None:
    """生产默认退出钩子：`SIGTERM` ⇒ **uvicorn 的优雅退出**（先停止接受新连接、关连接/端口）。

    刻意**不用** `os._exit` / `SIGKILL`：uvicorn CLI 对 SIGTERM 注册了 `should_exit=True`
    的优雅路径；硬杀会丢响应，并让 supervisor 的"等端口释放"退化成纯超时。
    supervisor 只有在端口真正释放后才能接手，所以这里必须是优雅退出。
    """
    signal.raise_signal(signal.SIGTERM)


#: 可注入钩子（模块级；**生产** = 真起 supervisor + 真退出本进程）。
#: 测试必须替换这两个名字：任何测试都绝不真起 supervisor、绝不真杀测试进程。
SPAWN_SUPERVISOR = env_switch.spawn_supervisor
SHUTDOWN_SERVER = _shutdown_process


def _request_shutdown(delay_s: float | None = None) -> None:
    """后台**延迟**退出本进程：先把 202 响应写完，再交班给 supervisor。

    默认 `LOOP_SWITCH_EXIT_DELAY=0.5` 是"响应落盘后再退"的最小延迟；
    测试可用 0 立即触发（注入钩子，不会真退出）。
    """
    if delay_s is None:
        raw = os.environ.get("LOOP_SWITCH_EXIT_DELAY", "0.5")
        try:
            delay_s = float(raw)
        except ValueError as exc:
            raise HTTPException(500, detail={
                'error': f'LOOP_SWITCH_EXIT_DELAY 不是数字：{raw!r}'}) from exc
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        raise HTTPException(500, detail={'error': '切换需要事件循环（lifespan 未就绪）'}) from exc
    handler = SHUTDOWN_SERVER
    loop.call_later(float(delay_s), handler)


def _pending_supervisor_state(pending: dict[str, Any]) -> tuple[str, str]:
    """进行中的切换是否还有活 supervisor：`alive` / `dead` / `unknown`。

    **唯一判据** = `host.admission.proc_state_start`（它已经正确处理"pid 存在但僵尸"），
    本处不另写 /proc 解析（红线 8）。
    `unknown` = 不可活判（缺 `supervisor_pid` 的历史/手写 pending，或本机无 /proc）：
    调用方必须保持 409 并给人工清理路径，**不得猜成已死自动清理**。
    """
    from host import admission

    raw = pending.get("supervisor_pid")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return "unknown", f"pending 缺少可用 supervisor_pid（{raw!r}；历史或手写 pending）"
    if not Path("/proc").is_dir():
        return "unknown", f"本机无 /proc 或不可读，无法判断 supervisor pid={raw} 存活"
    state, _start = admission.proc_state_start(raw)
    if state is None:
        return "dead", f"supervisor pid={raw} 已不存在"
    if state in admission.TERMINAL_PROC_STATES:
        return "dead", f"supervisor pid={raw} 已终结（state={state}）"
    return "alive", f"supervisor pid={raw} 仍在运行（state={state}）"


def _pending_waited(pending: dict[str, Any]) -> str:
    raw = pending.get("supervisor_started_ts")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return "等待时长未知"
    return f"已等待 {max(0.0, time.time() - float(raw)):.1f}s"


def _reject_pending_switch() -> None:
    """有未收口的 pending 时拒绝再发起切换；**死的 supervisor 自动收口**（S0 §9.6）。

    - supervisor 进程不存在/僵尸 ⇒ 删 pending + 落只增历史 `supervisor_dead_auto_clear`，
      然后放行（悬挂 pending 不再把切换永久卡死）；
    - supervisor 活着 ⇒ 409（pid + 已等待时长）；
    - 不可活判（缺 pid / 无 /proc）⇒ 409 + 人工清理路径（不猜）。
    """
    pending = env_switch.pending()
    if pending is None:
        return
    verdict, detail = _pending_supervisor_state(pending)
    if verdict == "dead":
        env_switch.clear_pending(pending, reason="supervisor_dead_auto_clear")
        return
    target = pending.get('target_env_root')
    record = pending.get('record_id')
    if verdict == "alive":
        raise HTTPException(409, detail={'error': (
            f"已有进行中的环境切换（target={target}，record={record}）：{detail}，"
            f"{_pending_waited(pending)}；等它收口后再发起"
            "（supervisor 结束后本状态会自动收口，无需人工介入）。")})
    manual = env_switch.pending_path()
    raise HTTPException(409, detail={'error': (
        f"存在无法自动收口的进行中切换（target={target}，record={record}）：{detail}。"
        f"人工清理路径：确认没有正在重启的服务后删除 {manual}，再重试。")})


def _build_switch_request(*, target_env_root: Path, record_id: str | None,
                          now: str | None = None) -> dict[str, Any]:
    """构造切换请求：原始根必须已记录；目标/当前数据根由 `env_switch` 唯一解析。

    `now`（body 里的可选时间字段）只覆盖 `requested_at`：时间注入的唯一入口仍是
    `LOOP_NOW`/`KB_NOW`，这里不新造第二套时钟。
    """
    try:
        origin = env_switch.origin_env_root()
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    if origin is None:
        raise HTTPException(409, detail={'error': (
            '尚未记录原始环境根（origin_env_root），拒绝切换：重启服务完成记录后再试'
            '（S0 §9.6：派生源恒为原始根）。')})
    try:
        request = env_switch.build_request(
            target_env_root=target_env_root,
            origin_env_root=origin,
            record_id=record_id,
            project=P.ENV_ROOT,
            app_dir=P.LOOP_DIR,
            host=env_switch.server_host(),
            port=env_switch.server_port(),
            state_root=P.STATE_DIR,
        )
    except ValueError as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    if now:
        request['requested_at'] = str(now)
    return request


def _write_switch_projection(record_dir: str | None, record: dict[str, Any]) -> None:
    """S0 记录目录里的只读投影 `env-switch.json`（T1 的 `get()` 只读合并，字段名 env_switch）。"""
    if not record_dir:
        return
    folder = Path(record_dir)
    if not folder.is_dir():
        raise FileNotFoundError(f'S0 记录目录不存在：{folder}')
    tmp = folder / f'.env-switch.json.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')
    os.replace(tmp, folder / 'env-switch.json')


def _start_switch(record_id: str | None, request: dict[str, Any]) -> None:
    """先写 pending（+记录投影）→ 起 supervisor → 后台退出本进程。

    顺序有意为之：**先落盘再起进程**（重启后界面能看到 pending 未收口），
    且任何一步失败都在"环境根未改变"的前提下退回并显式报错。
    """
    env_switch.write_pending(request)
    try:
        _write_switch_projection(request.get('record_dir'), request)
    except OSError as exc:
        env_switch.clear_pending(request)
        raise HTTPException(503, detail={
            'error': f'切换记录投影写入失败：{exc}；环境根未改变。'}) from exc
    try:
        SPAWN_SUPERVISOR(request)
    except OSError as exc:
        env_switch.clear_pending(request)
        raise HTTPException(503, detail={
            'error': f'无法启动切换 supervisor：{exc}；环境根未改变。'}) from exc
    _request_shutdown()


@app.post('/api/s0/{record_id}/activate')
async def s0_activate(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0 §9.6：切换到派生副本。202 = 已受理；结论写在 `active.json`（active/rollback）。"""
    store = _s0_store()
    try:
        record = await asyncio.to_thread(store.get, record_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={'error': '准备记录不存在'}) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    _reject_pending_switch()
    _reject_if_active_runs('切换环境根')
    if record.get('ready_for_execution') is not True:
        failed = [str(check.get('key')) for check in record.get('checks') or []
                  if check.get('status') != 'passed']
        raise HTTPException(409, detail={'error': (
            f"该 S0 记录未准出（ready_for_execution=false），拒绝切换：{record_id}；"
            f"未通过检查：{'、'.join(failed) or '未知'}")})
    work_env = Path(str(record.get('work_env') or ''))
    if not work_env.is_dir():
        raise HTTPException(409, detail={'error': f'副本不存在或不是目录：{work_env}；拒绝切换。'})
    data_root = work_env / 'kb'
    if not data_root.is_dir():
        raise HTTPException(409, detail={'error': (
            f'副本缺少数据根 {data_root}（S0 §9.3：派生副本自包含 WORKSPACE_ROOT=<副本>/kb）；'
            '拒绝切换。')})
    request = _build_switch_request(target_env_root=work_env, record_id=record_id,
                                    now=payload.get('now'))
    _start_switch(record_id, request)
    return JSONResponse(status_code=202, content={'switch': request})


@app.get('/api/env/state')
def env_state() -> dict[str, Any]:
    """当前根 / 原始根 / 切换摘要 / 派生基线源（只读投影，S0 §9.6 + WEB_UI §15）。"""
    try:
        origin = env_switch.origin_env_root()
        switch = env_switch.summary()
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    return {
        'env_root': str(P.ENV_ROOT),
        'env_id': P.ENV_ID,
        'origin_env_root': str(origin) if origin is not None else None,
        'switch': switch,
        # 派生源恒为原始根（副本不当基线，防套娃；决定 17）
        'baseline_source': str(origin) if origin is not None else str(P.ENV_ROOT),
    }


@app.post('/api/env/switch-back')
async def env_switch_back(payload: dict[str, Any] = Body(default={})):
    """S0 §9.6：以原始根为目标反向执行同一流程；副本不删（它是数据根与证据）。"""
    try:
        origin = env_switch.origin_env_root()
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    if origin is None:
        raise HTTPException(409, detail={'error': '尚未记录原始环境根（origin_env_root），无法切回。'})
    _reject_pending_switch()
    _reject_if_active_runs('切回原始环境根')
    if Path(P.ENV_ROOT).resolve() == origin.resolve():
        raise HTTPException(409, detail={'error': f'当前已在原始环境根：{origin}；无需切回。'})
    try:
        active = env_switch.active() or {}
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    record_id = active.get('record_id')
    request = _build_switch_request(target_env_root=origin, record_id=record_id,
                                    now=payload.get('now'))
    _start_switch(record_id, request)
    return JSONResponse(status_code=202, content={'switch': request})


# ---------------------------------------------------------------- 派生副本清单（S0 §9.3/§9.6）

def _s0_records_root() -> Path:
    store = _s0_store()
    root = getattr(store, 'root', None)
    if root is None:
        raise HTTPException(500, detail={'error': 'S0 记录根不可用'})
    return Path(root)


def _raw_s0_records(root: Path) -> list[dict[str, Any]]:
    """直接读 `record.json`（**不调 `get()`**：那会重算漂移/端口并重写报告，清单页不能有副作用）。

    损坏记录不进清单（单条 `GET /api/s0/{id}` 会显式报错，不在列表里静默冒充）。
    """
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob('S0-*/record.json'), reverse=True):
        try:
            if path.is_symlink() or path.parent.is_symlink():
                continue
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _dir_bytes(root: Path) -> int:
    """副本实际占用（只算常规文件，不跟随软链；单项读失败只少算该项，不整体报错）。"""
    total = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if not Path(current, name).is_symlink()]
        for name in files:
            entry = Path(current, name)
            try:
                if entry.is_symlink():
                    continue
                total += entry.stat().st_size
            except OSError:
                continue
    return total


@app.get('/api/s0/copies')
def s0_copies() -> dict[str, Any]:
    """S0 §9.3 副本清单：列 `entry` 为 `rtl_folder`/`env_folder` 的派生副本（形状冻结，WEB_UI §15）。"""
    root = _s0_records_root()
    copies: list[dict[str, Any]] = []
    for row in _raw_s0_records(root):
        if row.get('entry') not in ('rtl_folder', 'env_folder'):
            continue
        raw_work = row.get('work_env')
        work = Path(str(raw_work)) if raw_work else None
        exists = bool(work is not None and work.is_dir() and not work.is_symlink())
        copies.append({
            'id': row.get('id'),
            'work_env': str(work) if work is not None else None,
            'exists': exists,
            'bytes': _dir_bytes(work) if exists and work is not None else 0,
            'rtl_prefix': row.get('rtl_prefix'),
            'status': row.get('status'),
            'ready_for_execution': row.get('ready_for_execution') is True,
        })
    return {'copies': copies}


@app.delete('/api/s0/{record_id}/copy')
def s0_delete_copy(record_id: str, confirm: bool = Query(default=False)) -> dict[str, Any]:
    """删除副本目录（**不删记录**；二次确认；只允许删 `COPIES_ROOT` 下的派生副本）。"""
    if not confirm:
        raise HTTPException(400, detail={'error': (
            '删除副本必须二次确认：confirm=true（副本是数据根与证据，删除不可恢复；'
            '准备记录保留）')})
    if not S0_RECORD_ID_RE.fullmatch(record_id):
        raise HTTPException(400, detail={'error': f'S0 记录 ID 非法：{record_id}'})
    folder = _s0_records_root() / record_id
    try:
        row = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={'error': '准备记录不存在'}) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail={'error': f'准备记录不可读：{exc}'}) from exc
    if not isinstance(row, dict) or row.get('entry') not in ('rtl_folder', 'env_folder'):
        raise HTTPException(409, detail={'error': (
            '只有 entry=rtl_folder/env_folder 的派生副本可删除；普通 S0 准备记录不走这里。')})
    raw_work = row.get('work_env')
    if not raw_work:
        raise HTTPException(422, detail={'error': '准备记录缺少 work_env，无法定位副本目录。'})
    work = Path(str(raw_work))
    try:
        resolved = work.resolve()
        copies_root = COPIES_ROOT.resolve()
    except OSError as exc:
        raise HTTPException(422, detail={'error': f'副本路径不可解析：{exc}'}) from exc
    try:
        resolved.relative_to(copies_root)
    except ValueError as exc:
        raise HTTPException(400, detail={'error': (
            f'副本路径不在 {copies_root} 下，拒绝删除：{resolved}'
            '（环境根/基线原件永不由界面删除）')}) from exc
    if work.is_symlink():
        raise HTTPException(400, detail={'error': f'副本是符号链接，拒绝删除：{work}'})
    if resolved == Path(P.ENV_ROOT).resolve():
        raise HTTPException(409, detail={'error': (
            f'该副本正是当前环境根，拒绝删除：{resolved}；先切回原始根。')})
    # 只拒"正在被使用"的两种（WEB_UI §15：切回后副本保留、但可手动清理）：
    #   ① 当前根（上一条，resolve 后相等）；
    #   ② **在飞 pending** 的目标。
    # 最近一次 `active` 的 target 不作拒绝依据：`status=="rollback"`、或切回原环境后
    # `active.target` 仍是副本（而当前根已不是它）时，副本只是数据/证据，必须可删 ——
    # 用 active 一味拒绝会让它永远删不掉。`status=="active" && target==目标` 等价于
    # "当前根就是它"，已由 ① 覆盖。
    try:
        in_flight = env_switch.pending() or {}
    except ValueError as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc
    pending_target = in_flight.get('target_env_root')
    if pending_target and Path(str(pending_target)).resolve() == resolved:
        raise HTTPException(409, detail={'error': (
            f'该副本是**在飞切换**的目标环境根，拒绝删除：{resolved}；等切换收口后再删。')})
    if not resolved.is_dir():
        return {'deleted': False, 'work_env': str(resolved)}
    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        raise HTTPException(422, detail={'error': f'删除副本失败：{exc}'}) from exc
    return {'deleted': True, 'work_env': str(resolved)}


@app.get('/api/s0/{record_id}/report')
def s0_report(record_id: str):
    try:
        path = _s0_store().report_path(record_id)
    except ValueError as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    if not path.is_file():
        raise HTTPException(404, detail={'error': '准备报告不存在'})
    return FileResponse(path, media_type='text/markdown; charset=utf-8', filename='env-check-report.md')


@app.get('/api/s0/{record_id}')
def s0_get(record_id: str):
    try:
        return _s0_store().get(record_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={'error': '准备记录不存在'}) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc

def _s0_call(action: str, record_id: str, **kwargs):
    """S0-b 的四个写入口共用错误映射（缺记录 404 / 参数 400 / 冲突 409）。"""
    try:
        return getattr(_s0_store(), action)(record_id, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail={'error': '准备记录不存在'}) from exc
    except FileExistsError as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc


@app.post('/api/s0/{record_id}/proposals')
def s0_propose(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0-b：记录逐 hunk 提议（模型/Host 写；**不碰副本 TB**）。"""
    return _s0_call('propose', record_id, hunks=payload.get('hunks') or [],
                    actor=payload.get('actor') or '', now=payload.get('now'))


@app.post('/api/s0/{record_id}/confirmations')
def s0_confirm(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0-b：人逐条确认/否决（只增不改，带锚；不接受 model:/host:）。"""
    return _s0_call('confirm', record_id, hunk_id=payload.get('hunk_id') or '',
                    decision=payload.get('decision') or '',
                    actor=payload.get('actor') or '', reason=payload.get('reason') or '',
                    now=payload.get('now'))


@app.post('/api/s0/{record_id}/apply')
def s0_apply(record_id: str):
    """S0-b：把**已确认**的 hunk 落进副本 TB 顶层，返回前后 md5。"""
    return _s0_call('apply', record_id)


@app.post('/api/s0/{record_id}/smoke')
def s0_smoke(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0-b：在副本内跑三库编译冒烟（驱动 = kb/tools/run_guarded.sh --mode compile-only）。"""
    case = payload.get('case') or ''
    if not case:
        raise HTTPException(400, detail={'error': '需要 case（TESTLIB 下的用例名）'})
    return _s0_call('smoke', record_id, case=case, now=payload.get('now'))


@app.post('/api/s0/{record_id}/warnings')
def s0_warning(record_id: str, payload: dict[str, Any] = Body(default={})):
    """S0-b：人对"新增/上升的 warning code"给出评估结论（只追加、带锚）。"""
    code = payload.get('code') or ''
    if not code:
        raise HTTPException(400, detail={'error': '需要 code（如 Warning-120162）'})
    return _s0_call('accept_warning', record_id, code=code,
                    actor=payload.get('actor') or '', reason=payload.get('reason') or '',
                    now=payload.get('now'))


@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": _manager().list_runs()}


#: S0 记录 id 的合法格式（唯一校验入口；见 SPEC-05 §6 / WEB_UI §4.5）。
S0_RECORD_ID_RE = re.compile(r"^S0-[A-Za-z0-9_-]+$")


def _s0_record_id(value: Any) -> str | None:
    """校验可选 `s0_record_id`：缺省/None ⇒ None；给了就必须匹配格式，否则 400。"""
    if value is None:
        return None
    if not isinstance(value, str) or not S0_RECORD_ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail={
            "error": (f"s0_record_id 格式非法：{value!r}；"
                      "合法格式 = ^S0-[A-Za-z0-9_-]+$（省略表示未经 S0 派生）"),
        })
    return value


def _check_s0_record_for_run(record_id: str | None, mode: str | None) -> None:
    """C12（2026-10-27 裁决 A）：S0 记录**传了才校验**，不传不强制。

    为什么只对 `real` 校验：drill 不覆盖 S0（S0_ENVIRONMENT_SPEC §6.1「drill 不覆盖 S0」），
    `s0_record_id` 在 drill 下只是来源徽标；而 `real` 是要拿环境真跑的，若记录没准出
    （`ready_for_execution != true`）就必须**在提交前**拒绝（AGENTS.md §2 硬性纪律 5），
    不能默认兜底（S0_ENVIRONMENT_SPEC §8.4 第 4 条）。

    S0-b 未接入时 `S0Store.get()` 会把 `ready_for_execution` **归一为 false**（S0 §3 恒假）
    ⇒ 该规则等于"real + 带 S0 记录 一律拒"，这是**有意的 fail-closed**：没准出的副本不许真跑，
    且准出只能由真实核验产生、不能被记录文件自称（文件写 true 也会被 get() 归一回 false）。
    要用 real 就别带 S0 记录（现状），或先把 S0-b（接口适配 + 三库冒烟）做完；
    S0-b 接入后 `get()` 才可能返回 true，届时本判据自然放行。
    """
    if not record_id or (mode or "drill") != "real":
        return
    try:
        record = _s0_store().get(record_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail={
            "error": (f"S0 记录不存在：{record_id}（s0_record_id 必须是已存在的准备记录；"
                      "省略表示未经 S0 派生）"),
        }) from exc
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail={
            "error": f"S0 记录不可用：{record_id}：{exc}",
        }) from exc
    if record.get("ready_for_execution") is not True:
        raise HTTPException(status_code=400, detail={
            "error": (f"该 S0 记录尚未准出（ready_for_execution=false）：{record_id} ⇒ real 运行被拒。"
                      "可改用 mode=drill，或先完成 S0-b（TB 接口适配 + 三库冒烟）后再跑。"),
        })


@app.post("/api/runs")
async def create_run(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    # 缺省语义只在入口解析一次（RunManager.start → host.baseline.normalize）；
    # API 层不再自带第二份 `or "v0"`，否则两处默认会漂移。
    baseline = payload.get("baseline")
    mode = payload.get("mode") or "drill"
    scenario = payload.get("scenario") or "happy"
    project = payload.get("project") or str(P.ENV_ROOT)
    # 三根在进程启动时解析；跨环境切换必须重启，不能静默换根（Web UI Spec §6.4）。
    if Path(project).resolve() != Path(P.ENV_ROOT).resolve():
        raise HTTPException(status_code=400, detail={
            "error": "project 必须等于当前进程 ENV_ROOT；跨环境需以该环境重启服务。",
            "current_env_root": str(P.ENV_ROOT),
        })
    manager = _manager()
    s0_record_id = _s0_record_id(payload.get("s0_record_id"))
    _check_s0_record_for_run(s0_record_id, mode)   # C12：传了才校验（real 必须准出）
    try:
        run_id = await manager.start(baseline=baseline, mode=mode, scenario=scenario,
                                     now=payload.get("now"), project=str(project),
                                     s0_record_id=s0_record_id)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    except ValueError as exc:
        from host.baseline import BaselineInvalid

        if isinstance(exc, BaselineInvalid):
            # 结构化拒绝（Web UI §6.4）：missing/errors 直接取判据（唯一来源），不在 API 层二次推导。
            details = exc.details
            raise HTTPException(status_code=400, detail={
                "error": str(exc),
                "baseline": exc.baseline_id,
                "missing": list(details.get("missing") or []),
                "errors": list(details.get("errors") or []),
            }) from exc
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    # 回 `created_at`（verifier F-V1-03-NOTE）：调用方拿到的 run 身份应当自洽，
    # 不必再发一次 GET 才能确认"这个 run 是什么时候建的"。
    doc = manager.docs.get(run_id)
    return {"run_id": run_id, "mode": mode, "scenario": scenario,
            "project": str(project), "created_at": getattr(doc, "created_at", None),
            "s0_record_id": s0_record_id}


@app.post("/api/runs/{run_id}/promote")
async def promote_run(run_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """人触发 N16 真实晋升（I8）。

    只做边界三件事：验人（必须以 human 开头且与 G3 签署者一致）、验 G3 权威记录、
    把动作交给 `services/promote.py`（它再调 `kb/tools/n16_promote.py --promote`）。
    **不伪造闸门、不写 baselines、不依赖执行是否已 close。**
    """
    from services import promote as promote_svc

    actor = payload.get("actor")
    reason = payload.get("reason")
    try:
        return await asyncio.to_thread(
            promote_svc.promote, run_id, actor,
            str(reason) if reason else None, payload.get("now"),
        )
    except promote_svc.PromoteError as exc:
        raise HTTPException(status_code=403, detail={
            "error": str(exc),
            "note": "被拒 = 人/闸门/前置不满足；拒绝发生在任何写盘之前（账本无孤儿签名）。",
        }) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    manager = _manager()
    if run_id not in manager.docs:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    try:
        view = manager.run_view(run_id)
        from host import agent_control as control
        for agent in view.get('agents', []):
            for node in agent.get('nodes', []):
                live = control.live_view(manager.docs[run_id].run_dir, node)
                if live:
                    agent['live_control'] = live
                    break
        return view
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """SSE 运行投影流（SPEC-04 §6.9 / SPEC-REV-07 U2-a）：只读传输，仅变化时推送。

    推送内容 = 既有 run_view 投影（与 GET /api/runs/{run_id} 同源）；本路由不构造
    第二份判据、不新增事件 kind、不写文件。run_view 是同步读盘，放线程池避免阻塞事件循环。
    客户端断开由 Starlette 关闭生成器；断线回退轮询由客户端承担（SPEC-04 §7.3）。
    """
    from services import run_stream

    manager = _manager()
    if run_id not in manager.docs:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})

    async def fetch_view() -> dict[str, Any]:
        return await asyncio.to_thread(manager.run_view, run_id)

    return StreamingResponse(
        run_stream.run_view_stream(fetch_view),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, since_seq: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return {"events": ProgressLog(P.EVENTS_DIR, run_id).read(since_seq=since_seq)}


@app.get("/api/runs/{run_id}/nodes/{node}")
def get_node_detail(run_id: str, node: str) -> dict[str, Any]:
    """节点执行详情投影（SPEC-02 §10.4 / SPEC-04 §6.7）。

    只读：不写盘、不触发重跑、不返回文件内容（唯一例外 = P-28 的报告只读端点）。
    - 未知 run ⇒ 404（`detail.error`）；
    - 未知节点 ⇒ **200** + `known=false` 的空投影（不用 404 冒充"节点不存在"）。
    """
    manager = _manager()
    doc = manager.docs.get(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    run_dir = getattr(doc, "run_dir", None)
    events = ProgressLog(P.EVENTS_DIR, run_id).read()
    # 运行视图只用于三件事：运行态（P-30 未到达）、闸门逐条材料（P-17/P-18）、
    # 以及闸门权威决策（P-15/P-16）。判定仍只在服务端既有实现里，这里不新算判据。
    try:
        view = manager.run_view(run_id)
    except KeyError:
        view = None
    gate = None
    gate_id = node_view.GATE_ID_BY_NODE.get(node)
    if gate_id and isinstance(view, dict):
        from services import contracts

        def _last_terminal_detail(target: str) -> dict[str, Any]:
            """该节点最后一条 node_finished 的 detail（只读事件流；无 ⇒ 空字典）。"""
            found: dict[str, Any] = {}
            for event in events:
                if event.get("node") == target and event.get("kind") == "node_finished":
                    detail = event.get("detail")
                    if isinstance(detail, dict):
                        found = detail
            return found

        # 裁决 #2：G2/G3 的只读待确认项来自服务端既有材料（N12 未闭环项 / N15_select 选集）。
        n12_detail = _last_terminal_detail("N12")
        select_detail = _last_terminal_detail("N15_select")
        gate = contracts.gate_entries_view(
            gate=gate_id,
            run_dir=Path(run_dir) if run_dir else None,
            diff=view.get("difference_items"),
            pending_interrupt=view.get("pending_interrupt"),
            gate_options=view.get("gate_options"),
            authority=((view.get("gates_authority") or {}).get("gates") or {}).get(gate_id),
            node_events=[event for event in events if event.get("node") == node],
            mode=view.get("mode"),
            run_status=view.get("status"),
            case_states=view.get("case_states"),
            conflicts=view.get("conflicts"),
            blockers=view.get("blockers"),
            n12_open_items=n12_detail.get("open_items"),
            selected_cases=select_detail.get("cases"),
        )
    report = _report_block(run_dir) if node == "N12" else None
    return node_view.build_node_detail(
        run_id,
        node,
        events=events,
        run_doc={"mode": doc.mode, "s0_record_id": getattr(doc, "s0_record_id", None)},
        run_dir=run_dir,
        run_view=view,
        gate=gate,
        report=report,
    )


# ---------------------------------------------------------------- P-28 报告只读视图

#: 报告只读端点的白名单：唯一允许的文件名（不接受任意路径）。
REPORT_WHITELIST: frozenset[str] = frozenset({"n12_report.md"})
#: 正文大小上限：超出即截断并标 `truncated=true`（不报 500）。
REPORT_MAX_BYTES = 512 * 1024


def _report_path(run_dir: str | Path | None, name: str) -> Path:
    """把白名单名解析成 run 目录内的真实路径；越界一律拒绝（防符号链接/`..`）。"""
    import os

    if name not in REPORT_WHITELIST:
        raise HTTPException(status_code=403, detail={
            "error": f"报告路径不在白名单：{name!r}；只允许 {sorted(REPORT_WHITELIST)}",
        })
    if run_dir is None:
        raise HTTPException(status_code=404, detail={"error": "运行目录未下发"})
    base = os.path.realpath(str(run_dir))
    target = os.path.realpath(os.path.join(base, name))
    if target != os.path.join(base, name) or os.path.dirname(target) != base:
        raise HTTPException(status_code=403, detail={"error": "报告路径越出 run 目录，已拒绝"})
    return Path(target)


def _report_block(run_dir: str | Path | None) -> dict[str, Any] | None:
    """N12 面板的报告入口（存在性 + 字节数；**不含正文**）。"""
    if run_dir is None:
        return None
    try:
        target = _report_path(run_dir, "n12_report.md")
    except HTTPException:
        return None
    if not target.is_file():
        return {"file": "n12_report.md", "available": False, "bytes": None}
    try:
        size = target.stat().st_size
    except OSError:
        return {"file": "n12_report.md", "available": False, "bytes": None}
    return {"file": "n12_report.md", "available": True, "bytes": size}


@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: str, path: str | None = Query(default=None)) -> dict[str, Any]:
    """本轮报告全文（P-28）：**白名单 + 只读 + 大小上限 + 不越 run 目录**。

    只给本 run 的 `n12_report.md`；`path` 参数只接受白名单值（其余 403），
    不开放任意路径探测。正文超过上限即截断并标 `truncated=true`。
    """
    manager = _manager()
    doc = manager.docs.get(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    name = path or "n12_report.md"
    target = _report_path(getattr(doc, "run_dir", None), name)
    if not target.is_file():
        raise HTTPException(status_code=404, detail={"error": "本轮没有报告文件（n12_report.md）"})
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=422, detail={"error": f"报告读取失败：{exc}"}) from exc
    truncated = len(data) > REPORT_MAX_BYTES
    text = data[:REPORT_MAX_BYTES].decode("utf-8", errors="replace")
    return {
        "run_id": run_id,
        "file": name,
        "path": str(target),
        "bytes": len(data),
        "truncated": truncated,
        "content": text,
        "authority": "projection",
    }


# ---------------------------------------------------------------- gates

def _agent_root(run_id: str, node: str):
    from host import agent_control as control
    manager = _manager()
    if run_id not in manager.docs or node not in control.NODES:
        raise HTTPException(404, detail={'error': '运行或模型节点不存在'})
    return Path(manager.docs[run_id].run_dir)


def _agent_window_view(root: Path, run_id: str, node: str, attempt: int | None) -> dict[str, Any]:
    """GET /agents/{node} 与其 SSE 流（§6.10）共用的**唯一**视图装配（口径同源，红线 8）。

    抛错口径也一致：KeyError ⇒ 404 语义、OSError/ValueError ⇒ 422 语义，由两条路由各自映射。
    """
    from host import agent_control as control
    from host import agent_memory as AM
    from services import agent_view

    view = control.read_view(root, node, attempt=attempt)
    events = _manager()._progress(run_id).read()
    view['events'] = [event for event in events
                      if event.get('node') == node or str(event.get('node', '')).startswith(node + '_')]
    # F02-c：窗口与角色卡消费同一来源的能力事实（未知维度保持 None，不在此另算）。
    view['capabilities'] = agent_view.node_capabilities(node, events)
    # F10/R5：预算事实由 Host 唯一测量（总量与 AM.check_budget 同一实现），前端只消费。
    view['context_budget'] = AM.context_budget(view.get('request'), attempt=view.get('selected_attempt'))
    # SPEC-REV-16 §2.1/§6.3：总结投影 + S3 解释面。唯一装配实现是 `agent_view.window_annotation`
    # （窗口与角色卡消费同一 `progress_view`，红线 8）；`now` 只从 `host/paths.py::now_iso`
    # 的注入入口取（`contracts.now_epoch()`），解析失败抛 ValueError ⇒ 路由按既有口径映射 422。
    from services import contracts as _contracts
    view.update(agent_view.window_annotation(view, node=node, root=root, events=events,
                                             now=_contracts.now_epoch()))
    return view


@app.get('/api/runs/{run_id}/agents/{node}')
async def agent_window(run_id: str, node: str, attempt: int | None = Query(default=None, ge=1)):
    root = _agent_root(run_id, node)
    try:
        return _agent_window_view(root, run_id, node, attempt)
    except KeyError as exc:
        raise HTTPException(404, detail={'error': str(exc)}) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


@app.get('/api/runs/{run_id}/agents/{node}/stream')
async def agent_window_stream(run_id: str, node: str, attempt: int | None = Query(default=None, ge=1)):
    """SSE Agent 窗口流（SPEC-04 §6.10 / SPEC-REV-07 U2-b）：推送 = GET 同一装配。

    建立连接前按 GET 同口径预验证一次（404/422）；此后传输/心跳/变更检测复用
    §6.9 的唯一实现（事件名 agent_view）。流中记录损坏 ⇒ 生成器异常结束、连接断开，
    客户端回退轮询并由 GET 的 422 暴露真实错误；控制 POST（SPEC-07）不经流上行。
    """
    from services import run_stream

    root = _agent_root(run_id, node)
    try:
        _agent_window_view(root, run_id, node, attempt)
    except KeyError as exc:
        raise HTTPException(404, detail={'error': str(exc)}) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc

    async def fetch_view() -> dict[str, Any]:
        return await asyncio.to_thread(_agent_window_view, root, run_id, node, attempt)

    return StreamingResponse(
        run_stream.run_view_stream(fetch_view, interval_s=1.5, heartbeat_s=15.0,
                                   event_name="agent_view"),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.post('/api/runs/{run_id}/agents/{node}/control')
async def agent_command(run_id: str, node: str, payload: dict[str, Any] = Body(default={})):
    from host import agent_control as control
    root = _agent_root(run_id, node)
    try:
        return control.command(root, node, payload)
    except PermissionError as exc:
        raise HTTPException(403, detail={'error': str(exc)}) from exc
    except control.ControlConflict as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    except OSError as exc:
        raise HTTPException(503, detail={'error': f'控制审计写入失败：{exc}'}) from exc


# ---------------------------------------------------------------- run 作用域指令（IL，REV-13 §7）

def _run_root(run_id: str) -> Path:
    """run 级端点共用的 404 口径：与 `_agent_root` 同一 `manager.docs` 判据（不另立规则）。"""
    manager = _manager()
    if run_id not in manager.docs:
        raise HTTPException(404, detail={'error': '运行不存在'})
    return Path(manager.docs[run_id].run_dir)


@app.get('/api/runs/{run_id}/instructions')
async def run_instructions(run_id: str):
    """当前有效条目/版本/来源/失效原因（历史只读）；空集合与读取失败不是同一状态。

    `accepted`/`applied`/`effective` 由服务端分别投影（回执≠生效）；本端点不写任何文件。
    审计损坏 ⇒ 422（与既有 agents 视图同口径），不静默清空指令继续。
    """
    from host import agent_control as control
    root = _run_root(run_id)
    try:
        return await asyncio.to_thread(control.instructions_view, root)
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


@app.post('/api/runs/{run_id}/instructions')
async def run_instruction_command(run_id: str, payload: dict[str, Any] = Body(default={})):
    """create/revoke/supersede（必带 actor/request_id/expected_instruction_revision）。

    回执只表示 accepted；applied 与 effective 由 GET 从封存记录/有效集投影。
    错误映射与既有 `/control` 一致：400 数据错、403 actor 错、409 冲突/过期、503 审计写失败。
    """
    from host import agent_control as control
    root = _run_root(run_id)
    try:
        return await asyncio.to_thread(control.submit, root, payload)
    except PermissionError as exc:
        raise HTTPException(403, detail={'error': str(exc)}) from exc
    except control.ControlConflict as exc:
        raise HTTPException(409, detail={'error': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, detail={'error': str(exc)}) from exc
    except OSError as exc:
        raise HTTPException(503, detail={'error': f'指令审计写入失败：{exc}'}) from exc


@app.post("/api/runs/{run_id}/gates/{gate_id}/decision")
async def submit_decision(
    run_id: str,
    gate_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    manager = _manager()
    if run_id not in manager.docs:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    decision = payload.get("decision")
    actor = payload.get("actor")
    reason = payload.get("reason")
    entry_decisions = payload.get("entry_decisions")
    if entry_decisions is not None and not isinstance(entry_decisions, dict):
        raise HTTPException(status_code=400, detail={
            "error": "entry_decisions 必须是 {entry_id: {decision, reason}} 的对象（I1 逐条处置）。"
        })
    if not actor:
        raise HTTPException(
            status_code=400,
            detail={"error": "必须提供 actor，且必须以 'human' 开头（I6）。"},
        )
    try:
        result = await manager.decide(
            run_id=run_id, gate=gate_id, decision=str(decision), actor=str(actor),
            reason=str(reason) if reason else None,
            entry_decisions=entry_decisions,
        )
    except PermissionError as exc:
        view = manager.run_view(run_id)
        return JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "error": str(exc),
                    "blockers": [b for b in view["blockers"] if b["severity"] == "blocker"],
                    "note": "被拒 = 权威（kb/tools/gate.py 或 I4 前置）拒绝，不是界面错误。",
                }
            },
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc

    # 字段名必须与内容相符（v1 终验发现）：原 `gate_state` 实际装的是 `gate.py` 的
    # **子进程调用记录**（cmd/rc/stdout_tail）—— 读 `gate_state.human_signed` 只会得到 undefined，
    # 界面因此在签署后**看不出**闸门是不是人签的。现在拆成两个字段：
    #   · `gate_tool`  —— 原始调用记录（审计用，保留）
    #   · `gate_state` —— **权威**闸门态（kb/tools/gate.py 的 gates.json 那一条）
    from host import gate_authority as GA

    auth = GA.authority_view(run_id)
    return JSONResponse(content={
        "ok": True,
        "decision": result["decision"],
        "gate": result["gate"],
        "gate_state": (auth.get("gates") or {}).get(gate_id),
        "gates_authority": auth,
        "gate_tool": json.loads(json.dumps(result["sign"], default=str)),
        "entries": result.get("entries") or {},
        "warnings": result.get("warnings") or [],
    })


# ---------------------------------------------------------------- 用例判据人签覆写（SPEC-REV-20 §7）


@app.post("/api/runs/{run_id}/cases/override")
async def override_case_verdicts(
    run_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> JSONResponse:
    """把人看过机器原因后的「认定通过 / 撤销」转交 kb 台账唯一写者，并回投影。

    本端点**不写** `case_states.json`（唯一写者是 `kb/tools/case_state.py override`），
    也不改机器判据/报告：只做 run 状态前置（§4-6）、CLI 转交与「机器原判 + 人签豁免」投影。
    错误映射（§7）：400 形状 / 403 前置矩阵 1–7（detail.blockers 逐条）/ 409 台账损坏或锚
    复核失败（detail.reason）/ 500 仅未预期异常。
    """
    manager = _manager()
    doc = manager.docs.get(run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    # 事件 node 与 gate_decided 同风格：取当前等待闸门（缺失 ⇒ None，不猜）
    pending = getattr(doc, "pending_interrupt", None) or {}
    gate = str(pending.get("id") or "").split(":")[0] or None
    try:
        result = await asyncio.to_thread(
            case_override.submit,
            run_id=run_id, run_dir=Path(doc.run_dir), run_status=str(doc.status),
            payload=payload, gate=gate,
        )
    except case_override.OverrideBadRequest as exc:
        raise HTTPException(status_code=400, detail={"error": exc.message}) from exc
    except case_override.OverrideRejected as exc:
        return JSONResponse(status_code=403, content={
            "detail": {
                "error": exc.message,
                "blockers": exc.blockers,
                "note": "被拒 = 前置（§4-1~§4-7）不满足或 run 不在等待闸门；台账一字节未动。",
            }
        })
    except case_override.OverrideConflict as exc:
        return JSONResponse(status_code=409, content={
            "detail": {"error": exc.message, "reason": exc.reason,
                       "note": "台账与机器原因件不一致到无法判定（kb rc=4）⇒ 拒绝追加。"}
        })
    except RuntimeError as exc:  # 未预期故障：显式 500，不换默认值
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
    return JSONResponse(content=result)


# ---------------------------------------------------------------- jobs

@app.post("/api/runs/{run_id}/jobs/{job_id}/cancel")
def cancel_job(run_id: str, job_id: str) -> dict[str, Any]:
    return _manager().cancel_job(run_id, job_id)


# ---------------------------------------------------------------- evidence existence

_PATHISH = (".log", ".md", ".json", ".sv", ".csv", ".txt", ".v")


def _resolve_ref_candidates(raw: str) -> list[Path]:
    """相对引用的解析基准。

    拆仓后**数据在工作区根、冻结资产在环境根**，写死一个基准必然有一半找不到；
    因此按「工作区 → 环境」依次探，且兼容历史里 `kb/runs/...` 这种写法
    （剥掉 `kb/` 前缀后按工作区解析）。
    """
    base = Path(raw)
    if base.is_absolute():
        return [base]
    out: list[Path] = []
    parts = base.parts
    if parts and parts[0] == "kb":
        out.append(P.WORKSPACE_ROOT.joinpath(*parts[1:]))
    out.append(P.WORKSPACE_ROOT / raw)
    out.append(P.ENV_ROOT / raw)
    return out


@app.get("/api/runs/{run_id}/evidence/exists")
def evidence_exists(run_id: str, ref: str = Query(...)) -> dict[str, Any]:
    """E-2 修复的界面侧一半：**先探测存在性**，缺失显示为显式缺陷而非 404。"""
    raw = ref.strip()
    # `file.sv:186` 这类源码行引用不是文件路径，不做文件系统探测
    if ":" in raw and not raw.startswith("/") and not raw.count("/"):
        head, _, tail = raw.rpartition(":")
        if tail.isdigit() and head.endswith(".sv"):
            return {"exists": None, "path": raw, "note": "源码行引用，不按文件路径探测"}
    candidates = _resolve_ref_candidates(raw)
    for candidate in candidates:
        if candidate.is_file():
            return {"exists": True, "path": str(candidate), "bytes": candidate.stat().st_size}
        # 目录型引用（如 evidence/archive/）也要能判空
        if candidate.is_dir():
            entries = [p.name for p in candidate.iterdir()]
            return {
                "exists": bool(entries),
                "path": str(candidate),
                "is_dir": True,
                "entries": len(entries),
                "note": "目录为空 ⇒ 按 E-2 显示为证据缺失" if not entries else None,
            }
    return {"exists": False, "path": str(candidates[-1]),
            "tried": [str(c) for c in candidates], "note": "证据缺失（E-2）"}


# ---------------------------------------------------------------- 实例同源反代（SPEC-REV-16 §5）

# 反代 = "人在 GUI 里看/说"的旁路会话面（REV-14 D3）。判据全部在 `services/instance_proxy.py`：
# 目标只来自受管元数据（`<run_dir>/agent_instance.json`）、只允许 loopback、R1–R20 拒绝矩阵、
# token 不进日志/错误体/响应、不可用态显式（503 + `X-Instance-Proxy`）。
# **必须声明在文件末尾的 `app.mount("/", StaticFiles(...))` 之前**：挂在 "/" 的 StaticFiles
# 会吞掉后加的路由（实测：mount 之后再 `@app.get` ⇒ 404 Not Found）。
@app.api_route("/instance/{run_id}/{node}/{attempt}/{path:path}",
               methods=list(instance_proxy.ALLOWED_METHODS))
async def instance_proxy_route(request: Request, run_id: str, node: str,
                               attempt: str, path: str):
    """唯一反代入口：GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS 原样透传（CONNECT/TRACE/Upgrade ⇒ 405）。"""
    root = _agent_root(run_id, node)
    return await instance_proxy.forward(request, run_dir=root, run_id=run_id, node=node,
                                        attempt=attempt, path=path)


@app.get("/api/runs/{run_id}/agents/{node}/instance")
def instance_availability_api(run_id: str, node: str,
                              attempt: int | None = Query(default=None, ge=1)):
    """§6.1 可用性元数据（只读投影；不返回 token，端口之外不暴露宿主细节）。

    归属是 **(node, attempt)** 粒度：`attempt` 可显式带（与元数据不符 ⇒ `target_missing`），
    省略则由受管元数据决定并在响应 `attempt` 回显（多 attempt 不能钉死 1）。
    """
    root = _agent_root(run_id, node)
    payload = instance_proxy.availability(root, run_id=run_id, node=node, attempt=attempt)
    # S8f（REV-16 §6.1 第 4 条）：响应含 `direct_url`（承载受管 token）⇒ 不得进任何缓存层。
    return JSONResponse(payload, headers={"cache-control": "no-store"})


@app.get("/api/runs/{run_id}/agents/{node}/session-copy")
def instance_session_copy_api(run_id: str, node: str,
                              attempt: int | None = Query(default=None, ge=1)):
    """§6.2 会话副本导出（复用 `dsh_sdk.read_session_log`；缺失/归属不符显式说原因）。"""
    root = _agent_root(run_id, node)
    return instance_proxy.session_copy(root, node=node, attempt=attempt)


# ---------------------------------------------------------------- 静态前端

if P.WEB_DIR.is_dir():
    # 必须最后挂载：挂在 "/" 的 StaticFiles 会吞掉后续路由。
    app.mount("/", StaticFiles(directory=str(P.WEB_DIR), html=True), name="web")


def main() -> None:  # pragma: no cover - 手工入口
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(__import__("os").environ.get("LOOP_PORT", "8099")))
