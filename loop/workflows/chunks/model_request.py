"""模型请求机制（F06）：契约构造、单次请求、attempt 记录与控制包装。

**机制层不持有节点语义**：Host 校验器 `validate(kind, payload, offered=...)` 由调用方
（`model_steps`，唯一实现 `_validate`）注入；本模块不复制任何节点判据。

不变量：每次请求新 agent；预算检查在请求前；取消/重发不消费旧结果；
调用记录只增不改；`implementation_sha256` 记录本模块指纹。
**工作记忆（WM，REV-13 §6）只在这里接线**：`working_memory` 与 `input_data`/`approved_experiences`
同级进入 `request_input` 并随 `AM.Attempt` 封存；`source_map` 只冷存进 request 顶层，不进模型输入。
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from host import agent_backends as AB
from host import agent_memory as AM
from host import agent_working_memory as WM
from host import gate_authority as GA

from ..context import RunCtx
from .model_common import load_prompts

def render_block(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(f"- {k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        return "\n".join(f"- {v}" for v in value)
    return str(value)


def request_contract(prompt_key: str) -> dict[str, Any]:
    """集中构造一次请求的规则与输出形状，供调用和留痕共用。"""
    from prompts.node_schemas import SCHEMAS

    schema = SCHEMAS.get(prompt_key.split("_", 1)[0])
    if schema is None:
        raise KeyError(f"没有 {prompt_key!r} 的输出契约（prompts/node_schemas.py）")
    spec = load_prompts().get(prompt_key) or {}
    return {"info": render_block(spec.get("info") or {}),
            "instruct": render_block(spec.get("instruct") or []),
            "schema": schema.model_json_schema()}


async def ask(
    ctx: RunCtx,
    node: str,
    *,
    prompt_key: str,
    input_data: dict[str, Any],
    contract: dict[str, Any] | None = None,
    backend: AB.AgentBackend | None = None,
) -> dict[str, Any]:
    """发一次真 ModelRequest。失败**不吞**：回报错误并交由调用方决定。"""
    from prompts.node_schemas import SCHEMAS

    backend = backend if backend is not None else AB.select(node)
    schema = SCHEMAS.get(prompt_key.split("_", 1)[0])
    if schema is None:
        raise KeyError(f"没有 {prompt_key!r} 的输出契约（prompts/node_schemas.py）")
    contract = contract or request_contract(prompt_key)
    payload = await backend.execute(AB.BackendRequest(
        input_data=input_data, info=contract["info"], instruct=contract["instruct"], schema=schema))
    if payload.get("model_call_failed"):
        ctx.event("warning", node=node, status="model_failed",
                  detail={"prompt": prompt_key, "model": payload.get("provider"),
                          "error": payload.get("error")})
    else:
        ctx.event("node_finished", node=f"{node}_model", status="ok",
                  detail={"prompt": prompt_key, "model": payload.get("provider"),
                          "plugin": payload.get("plugin")})
    return payload


async def run_attempt(
    ctx: RunCtx,
    node: str,
    *,
    prompt_key: str,
    input_data: dict[str, Any],
    offered: dict[str, Any],
    validate,
) -> dict[str, Any]:
    """发请求 + Host 校验；调用记录只增不改，经验不取得业务写权。

    `validate` 是 Host 校验的唯一实现（节点语义），由调用方注入；机制层不复制判据。
    """
    backend = AB.select(node)
    cfg = backend.info
    backend_metadata = backend.metadata()
    contract = request_contract(prompt_key)
    contract["info"] += "\n" + AM.MEMORY_RULE
    if input_data.get('human_interventions'):
        contract['info'] += ('\n人工 human_interventions 仅为当前任务的补充指令；'
                             '不得覆盖原始事实、授权范围、输出 Schema、Host 校验或人工闸门。')
    scope = AM.scope_for(ctx, input_data, contract)
    lessons, diagnostics = AM.experiences(ctx, scope)
    request_input = AM.normalized({k: v for k, v in input_data.items() if k != "approved_experiences"})
    if lessons:
        request_input["approved_experiences"] = lessons
    # WM 必须在 scope/experiences 之后重建：v1 作用域指纹只由节点业务输入决定（REG-01/EXP-01）。
    # 闸门投影只给有该消费需求的节点（N10/N12），其余节点不注入无关历史。
    interventions = request_input.get("human_interventions")
    working_memory = WM.build(
        ctx, node, request_input,
        instructions=tuple(interventions) if isinstance(interventions, list) else (),
        gate_projection=(GA.authority_view(ctx.run_id) if WM.requires_gate(node) else None),
    )
    request_input["working_memory"] = working_memory.payload
    attempt = AM.Attempt(ctx, node, {
        "prompt_key": prompt_key, "cycle": input_data.get("cycle"),
        "input": request_input, **contract, "offered": offered, "scope": scope,
        "model": cfg.model if cfg.available else None,
        "plugin": cfg.plugin if cfg.available else None,
        "backend": backend_metadata,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "experience_diagnostics": diagnostics,
        "working_memory_source_map": working_memory.source_map,
    })
    for diagnostic in diagnostics:
        ctx.event("warning", node=node, status="experience_rejected", detail={"message": diagnostic})
    kind = prompt_key.split("_", 1)[0]
    try:
        try:
            AM.check_budget(request_input, contract)
        except RuntimeError as exc:
            # 预算准入的唯一判据仍是 `AM.check_budget`；这里只把"强制材料缺口"作为可读原因追加，
            # 不另立判据、不截断、不抽样（REV-13 §6.3 / WM-03）。
            if not working_memory.over_budget:
                raise
            raise RuntimeError(
                f"{exc}；工作记忆强制材料缺口：mandatory_bytes={working_memory.mandatory_bytes}"
                f" > {working_memory.limit_bytes}（不截断、不抽样，按缺口失败）") from exc
        if not cfg.available:
            out = {"mode": "standin", "standin": True, "provider": "none", "reason": cfg.reason}
        else:
            payload = await ask(ctx, node, prompt_key=prompt_key, input_data=request_input,
                                contract=contract, backend=backend)
            validation = validate(kind, payload, offered=offered)
    except BaseException as exc:
        message = f"{type(exc).__name__}: {exc}"
        safe_message = backend.redact(message)
        attempt.finish("interrupted" if isinstance(exc, asyncio.CancelledError) else "error",
                       error=safe_message, backend=backend_metadata)
        if safe_message != message:
            raise RuntimeError(safe_message) from None
        raise
    if not cfg.available:
        attempt.finish("standin", payload=out, validation=None, backend=backend_metadata)
        return {**out, **attempt.refs(), "experience_diagnostics": diagnostics, "backend": backend_metadata}
    attempt.finish("validated" if validation["ok"] else "validation_failed",
                   payload=payload, validation=validation, backend=backend_metadata)
    out = {
        "mode": "live" if not payload.get("standin") else "standin",
        "standin": bool(payload.get("standin")),
        "provider": payload.get("provider"),
        "plugin": payload.get("plugin"),
        "model_call_failed": bool(payload.get("model_call_failed")),
        "error": payload.get("error"),
        "validation": validation,
        "data": validation.get("accepted") or payload.get("data"),
        "input_digest": {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in request_input.items()},
        **attempt.refs(),
        "experience_diagnostics": diagnostics,
        "backend": backend_metadata,
    }
    ctx.event(
        "node_finished", node=f"{node}_request",
        status="ok" if validation["ok"] else "validation_failed",
        detail={"model": out["provider"], "mode": out["mode"],
                "problems": validation["problems"][:5]},
    )
    return out


async def run_model_node(ctx: RunCtx, node: str, *, prompt_key: str,
                         input_data: dict[str, Any], offered: dict[str, Any],
                         validate) -> dict[str, Any]:
    """人工控制只包围模型请求，消费者在本函数返回后才取得输出。"""
    from host import agent_control as control

    async def invoke(instructions):
        request = {k: v for k, v in input_data.items() if k != 'human_interventions'}
        if instructions:
            request['human_interventions'] = instructions
        return await run_attempt(ctx, node, prompt_key=prompt_key,
                                 input_data=request, offered=offered, validate=validate)

    return await control.execute(ctx, node, invoke)
