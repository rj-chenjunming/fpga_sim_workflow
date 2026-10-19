"""FastAPI 边界：闸门操作台 + 长任务看板。

定位（spec §1 / §10.2）：**UI 是 ExecutionExchange 适配器，不是权威**。
本层只做三件事：准入、投影、把闸门提交转交给权威（`kb/tools/gate.py`）+ 中断（TriggerFlow）。
**不实现自己的状态机**。

启动时 `async_restore_all()`：重新判定作业命运并从快照恢复执行
（快照里的 `running` 帧会让 `load` fail-closed，所以恢复前执行必须已停放）。
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
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


# ---------------------------------------------------------------- runs

@app.get("/api/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": _manager().list_runs()}


@app.post("/api/runs")
async def create_run(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    baseline = payload.get("baseline") or "v0"
    mode = payload.get("mode") or "drill"
    scenario = payload.get("scenario") or "happy"
    manager = _manager()
    try:
        run_id = await manager.start(baseline=baseline, mode=mode, scenario=scenario, now=payload.get("now"))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    # 回 `created_at`（verifier F-V1-03-NOTE）：调用方拿到的 run 身份应当自洽，
    # 不必再发一次 GET 才能确认"这个 run 是什么时候建的"。
    doc = manager.docs.get(run_id)
    return {"run_id": run_id, "mode": mode, "scenario": scenario,
            "created_at": getattr(doc, "created_at", None)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    manager = _manager()
    if run_id not in manager.docs:
        raise HTTPException(status_code=404, detail={"error": f"未知 run_id：{run_id}"})
    try:
        return manager.run_view(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)}) from exc


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, since_seq: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return {"events": ProgressLog(P.EVENTS_DIR, run_id).read(since_seq=since_seq)}


# ---------------------------------------------------------------- gates

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
    if not actor:
        raise HTTPException(
            status_code=400,
            detail={"error": "必须提供 actor，且必须以 'human' 开头（I6）。"},
        )
    try:
        result = await manager.decide(
            run_id=run_id, gate=gate_id, decision=str(decision), actor=str(actor),
            reason=str(reason) if reason else None,
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
