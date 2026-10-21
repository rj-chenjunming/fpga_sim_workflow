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
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from host import paths as P
from host.progress import ProgressLog
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
    roots = config_api.allowed_roots(registry, P.WORKSPACE_ROOT,
                                     settings_path=P.LOOP_DIR / 'SETTINGS.yaml', extra=[P.ENV_ROOT])
    return S0Store(P.STATE_DIR / 's0', roots)


@app.get('/api/s0')
def s0_index():
    store = _s0_store()
    return {'baseline': str(P.ENV_ROOT), 'allowed_roots': [str(p) for p in store.allowed_roots],
            'records': store.list(), 'capabilities': {'prepare': True, 'tb_adapt': False, 'smoke': False}}


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
    try:
        run_id = await manager.start(baseline=baseline, mode=mode, scenario=scenario,
                                     now=payload.get("now"), project=str(project))
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
            "project": str(project), "created_at": getattr(doc, "created_at", None)}


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


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, since_seq: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return {"events": ProgressLog(P.EVENTS_DIR, run_id).read(since_seq=since_seq)}


# ---------------------------------------------------------------- gates

def _agent_root(run_id: str, node: str):
    from host import agent_control as control
    manager = _manager()
    if run_id not in manager.docs or node not in control.NODES:
        raise HTTPException(404, detail={'error': '运行或模型节点不存在'})
    return Path(manager.docs[run_id].run_dir)


@app.get('/api/runs/{run_id}/agents/{node}')
async def agent_window(run_id: str, node: str, attempt: int | None = Query(default=None, ge=1)):
    from host import agent_control as control
    root = _agent_root(run_id, node)
    try:
        view = control.read_view(root, node, attempt=attempt)
        events = _manager()._progress(run_id).read()
        view['events'] = [event for event in events
                          if event.get('node') == node or str(event.get('node', '')).startswith(node + '_')]
        # F02-c：窗口与角色卡消费同一来源的能力事实（未知维度保持 None，不在此另算）。
        from services import agent_view
        from host import agent_memory as AM
        view['capabilities'] = agent_view.node_capabilities(node, events)
        # F10：预算上限由 Host 常量下发，前端不硬编码（红线 8：不出现第二套同判据）。
        view['context_budget'] = {'limit_bytes': AM.MAX_CONTEXT_BYTES}
        return view
    except KeyError as exc:
        raise HTTPException(404, detail={'error': str(exc)}) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(422, detail={'error': str(exc)}) from exc


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
