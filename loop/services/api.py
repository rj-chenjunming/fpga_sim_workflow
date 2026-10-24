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
import re
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from host import paths as P
from host.progress import ALLOWED_KINDS, ProgressLog
from services import node_view
from workflows.main_flow import RunManager, get_manager

import agently  # noqa: F401  (用于 /api/health 报版本)


def _manager() -> RunManager:
    return get_manager()


@asynccontextmanager
async def lifespan(app: FastAPI):
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
    roots = config_api.allowed_roots(registry, P.WORKSPACE_ROOT,
                                     settings_path=P.LOOP_DIR / 'SETTINGS.yaml', extra=[P.ENV_ROOT, P.STATE_DIR])
    return S0Store(P.STATE_DIR / 's0', roots)


@app.get('/api/s0')
def s0_index():
    store = _s0_store()
    return {'baseline': str(P.ENV_ROOT), 'allowed_roots': [str(p) for p in store.allowed_roots],
            'records': store.list(),
            # rehearsal=True 只说明"可以点一次本机演练"：既不表示环境就绪，也不表示 S0-b 已接入。
            'capabilities': {'prepare': True, 'rehearsal': True, 'tb_adapt': False, 'smoke': False}}


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


# ---------------------------------------------------------------- 静态前端

if P.WEB_DIR.is_dir():
    # 必须最后挂载：挂在 "/" 的 StaticFiles 会吞掉后续路由。
    app.mount("/", StaticFiles(directory=str(P.WEB_DIR), html=True), name="web")


def main() -> None:  # pragma: no cover - 手工入口
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(__import__("os").environ.get("LOOP_PORT", "8099")))
