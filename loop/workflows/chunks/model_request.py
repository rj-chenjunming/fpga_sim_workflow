"""模型请求机制（F06）：契约构造、单次请求、attempt 记录与控制包装。

**机制层不持有节点语义**：Host 校验器 `validate(kind, payload, offered=...)` 由调用方
（`model_steps`，唯一实现 `_validate`）注入；本模块不复制任何节点判据。

不变量：每次请求新 agent；预算检查在请求前；取消/重发不消费旧结果；
调用记录只增不改；`implementation_sha256` 记录本模块指纹。
**工作记忆（WM，REV-13 §6）只在这里接线**：`working_memory` 与 `input_data`/`approved_experiences`
同级进入 `request_input` 并随 `AM.Attempt` 封存；`source_map` 只冷存进 request 顶层，不进模型输入。
**经验分层（EXP，REV-13 §8）只在这里消费结论**：选择判据全部在 `agent_memory.select_experiences`
（v1 精确匹配 / v2 两阶段适用性）；本模块只把选中的建议放进 `request_input.approved_experiences`、
把选择记录（选中/拒用/目录指纹/适用上下文/批次判定）冷存进 request 顶层 `experience_selection`，
并在"加上经验会超总预算"时整批不采用（不截断、不取前 N；最终准入仍唯一 `AM.check_budget`）。
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from host import agent_backends as AB
from host import agent_control as AC
from host import agent_memory as AM
from host import agent_working_memory as WM
from host import gate_authority as GA
from host import paths as P

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
    request_meta: dict[str, Any] | None = None,
    execute_kwargs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """发一次真 ModelRequest。失败**不吞**：回报错误并交由调用方决定。

    `request_meta` 是 A2（REV-13 §5.2）的 Host 侧身份/契约引用：只由本机制填写，
    后端只读；缺省字段投影成 `legacy`/`unknown`（旧调用方不必改）。
    `execute_kwargs` 是 Host 分配的 attempt 执行面（如 dsh 的 `cwd`/`home`/`attempt_key`）：
    只来自 Host 分配，不从任务文本或客户端 hint 拼。
    """
    from prompts.node_schemas import SCHEMAS

    backend = backend if backend is not None else AB.select(node)
    schema = SCHEMAS.get(prompt_key.split("_", 1)[0])
    if schema is None:
        raise KeyError(f"没有 {prompt_key!r} 的输出契约（prompts/node_schemas.py）")
    contract = contract or request_contract(prompt_key)
    meta = request_meta or {}
    payload = await backend.execute(AB.BackendRequest(
        input_data=input_data, info=contract["info"], instruct=contract["instruct"], schema=schema,
        contract_version=meta.get("contract_version"), identity=meta.get("identity"),
        context_manifest_ref=meta.get("context_manifest_ref"),
        execution_grant_ref=meta.get("execution_grant_ref"),
        runtime_fingerprint=meta.get("runtime_fingerprint")), **(execute_kwargs or {}))
    if payload.get("model_call_failed"):
        ctx.event("warning", node=node, status="model_failed",
                  detail={"prompt": prompt_key, "model": payload.get("provider"),
                          "error": payload.get("error")})
    else:
        ctx.event("node_finished", node=f"{node}_model", status="ok",
                  detail={"prompt": prompt_key, "model": payload.get("provider"),
                          "plugin": payload.get("plugin")})
    return payload


def _attempt_sources(node: str, input_data: dict[str, Any]) -> tuple[tuple[Path, str], ...]:
    """Host 侧派生"外部只读源件"清单：**只在 N6 且 input_data 带 targets 时**给出。

    为什么只给 N6：候选通道要求模型写整份 `candidate/TESTLIB/<case>.sv`，没有基线全文就只能
    去扫宿主文件系统（S6 真机两次失败的原因）。其它节点/无 targets ⇒ 空元组（不给无关材料面）。
    路径来源 = Host 已知事实（`targets[].file`，相对 `ENV_ROOT`），不接受模型/客户端 hint。
    """
    if node != "N6":
        return ()
    targets = input_data.get("targets")
    if not isinstance(targets, list):
        return ()
    seen: list[tuple[Path, str]] = []
    for item in targets:
        if not isinstance(item, dict):
            continue
        relative = item.get("file")
        if not isinstance(relative, str) or not relative.strip():
            continue
        pair = (Path(P.ENV_ROOT), relative.strip())
        if pair not in seen:
            seen.append(pair)
    return tuple(seen)


async def run_attempt(
    ctx: RunCtx,
    node: str,
    *,
    prompt_key: str,
    input_data: dict[str, Any],
    offered: dict[str, Any],
    validate,
) -> dict[str, Any]:
    """在**请求作用域**声明 run 模式，再走单次 attempt（机制实现见 `_run_attempt`）。

    为什么是作用域而不是多加参数：`select(node)` 的调用形状是既有契约（测试用单参替身替换），
    加参数会让"没改到调用点"静默退回旧语义；作用域让"谁在什么模式下调用"显式可读，
    退出即还原（不泄漏到别的请求）。模式取值仍在 `agent_backends.select` 的唯一判据里消费。
    """
    with AB.run_mode(ctx.mode):
        return await _run_attempt(ctx, node, prompt_key=prompt_key, input_data=input_data,
                                  offered=offered, validate=validate)


async def _run_attempt(
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

    IL（REV-13 §7）只在这里接线：先归约**本节点本次尝试**的有效指令（唯一归约实现仍在
    `agent_control`），作为 WM 的 `constraint` 条目注入；请求封存 `instruction_revision` /
    本节点指纹 / 采用与未采用原因；结果返回后按**本节点**指纹复核，变化 ⇒ 结果丢弃、
    显式失败（`result.status` 仍用既有 `error`，不新增枚举值），不进消费者。
    """
    backend = AB.select(node)
    cfg = backend.info
    backend_metadata = backend.metadata()
    contract = request_contract(prompt_key)
    contract["info"] += "\n" + AM.MEMORY_RULE
    if input_data.get('human_interventions'):
        contract['info'] += ('\n人工 human_interventions 仅为当前任务的补充指令；'
                             '不得覆盖原始事实、授权范围、输出 Schema、Host 校验或人工闸门。')
    # IL：本次明确尝试的序号由 Host 预留（与 AM.Attempt 的取号算法同一实现派生），
    # 有效集归约/到期/作用域判据全部在 agent_control，这里只消费结论（红线 8）。
    attempt_sequence = AC.next_attempt(ctx.run_dir, node)
    instructions = AC.effective(ctx.run_dir, node, attempt=attempt_sequence)
    directives = instructions["adopted"]
    if directives:
        contract['info'] += ('\nworking_memory 的 constraint 条目是 Host 已封存的人工指令；'
                             '同为补充指令，不得覆盖原始事实、授权范围、输出 Schema、'
                             'Host 校验或人工闸门。')
    scope = AM.scope_for(ctx, input_data, contract)
    # EXP（REV-13 §8）：v1 目录沿用原精确匹配，v2 目录走两阶段适用性筛选；判据只在 agent_memory。
    selection = AM.select_experiences(ctx, scope, node=node, input_data=input_data)
    request_input = AM.normalized({k: v for k, v in input_data.items() if k != "approved_experiences"})
    # WM 必须在 scope/experiences 之后重建：v1 作用域指纹只由节点业务输入决定（REG-01/EXP-01）。
    # 闸门投影只给有该消费需求的节点（N10/N12），其余节点不注入无关历史。
    interventions = request_input.get("human_interventions")
    working_memory = WM.build(
        ctx, node, request_input,
        instructions=tuple(interventions) if isinstance(interventions, list) else (),
        gate_projection=(GA.authority_view(ctx.run_id) if WM.requires_gate(node) else None),
        directives=directives,
    )
    request_input["working_memory"] = working_memory.payload
    # EXP-03：可选经验批次按**剩余预算**判定 —— 加上经验后超上限 ⇒ 整批不采用（不截断、不取前 N），
    # 普通执行在必需材料完整时继续；最终准入判据仍唯一是 `AM.check_budget`（红线 8）。
    # **只对 v2 目录选择生效**（REG-01 邻域）：v1 命中经验就照旧采用，若因此超总预算，
    # 由 `AM.check_budget` 让节点显式失败（不静默弃用经验、不改变 v1 的可观察行为）。
    if selection.lessons:
        remaining = AM.measure_budget(request_input, contract)["used_bytes"]
        batch_bytes = AM.experience_batch_bytes(selection.lessons)
        if (selection.record.get("catalog_version") == 2
                and remaining + batch_bytes > AM.MAX_CONTEXT_BYTES):
            selection = selection.reject_batch(
                "budget_batch_rejected", stage="remaining_budget",
                detail=(f"remaining {remaining} + batch {batch_bytes} > "
                        f"{AM.MAX_CONTEXT_BYTES} bytes"),
                extra={"base_bytes": remaining})
        else:
            request_input["approved_experiences"] = selection.lessons
    diagnostics = selection.diagnostics
    # A2（REV-13 §5.2）：身份与契约引用由 Host 填写，后端只读。
    # `attempt_key` 与 dsh 的 attempt 标识同形（run/node/序号）：提交门的 task_id join 用它。
    attempt_key = f"{ctx.run_id}/{node}/{attempt_sequence}"
    request_identity = AB.RequestIdentity(
        run_id=ctx.run_id, node=node, attempt_key=attempt_key,
        generation=attempt_sequence)
    context_manifest_ref = "wm-sha256:" + AM.fingerprint(working_memory.source_map)
    # 运行时指纹由后端自报（dsh 给配置/版本指纹，agently 退到实现指纹）；都没有 ⇒ unknown，
    # 不拿预算/校验值冒充运行时事实。
    runtime_fingerprint = backend_metadata.get("runtime_fingerprint") or (
        "implementation-sha256:" + str(backend_metadata.get("implementation_sha256") or "unknown"))
    request_meta = {"contract_version": AB.CONTRACT_VERSION, "identity": request_identity,
                    "context_manifest_ref": context_manifest_ref,
                    # S6：Host 授权表尚未落地 ⇒ 缺省即 unknown（不编造引用）
                    "execution_grant_ref": None,
                    "runtime_fingerprint": runtime_fingerprint}
    # S5-C2a：需要隔离工作区的后端（dsh）由 Host 分配 `<run>/agent_workspaces/<node>/attempt-N/`，
    # `cwd/home` 从分配结果传进去（不看任务文本、不看客户端 hint）；不需要的后端（agently）不分配。
    prepare_attempt = getattr(backend, "prepare_attempt", None)
    # attempt 身份由 Host 给出（与 A2 identity / 提交门 task_id 同一个值，不两处派生）。
    # N6 的候选通道要求模型写整份 `TESTLIB/<case>.sv` ⇒ 必须把 targets 声明的源件以**只读**
    # 方式摆进 `input/TESTLIB/`（否则模型只能去扫宿主文件系统）。**只对 N6 + 有 targets 生效**。
    prepare_sources = _attempt_sources(node, input_data)
    workspace = prepare_attempt(ctx.run_dir, node, attempt_sequence,
                                attempt_key=request_identity.attempt_key,
                                sources=prepare_sources) \
        if callable(prepare_attempt) else None
    attempt = AM.Attempt(ctx, node, {
        "prompt_key": prompt_key, "cycle": input_data.get("cycle"),
        "input": request_input, **contract, "offered": offered, "scope": scope,
        "model": cfg.model if cfg.available else None,
        "plugin": cfg.plugin if cfg.available else None,
        "backend": backend_metadata,
        # A2 契约投影（旧记录没有本键 ⇒ 读出侧显示 legacy/unknown，不回填）
        "backend_contract": AB.contract_record(
            contract_version=AB.CONTRACT_VERSION, identity=request_identity,
            context_manifest_ref=context_manifest_ref,
            execution_grant_ref=None, runtime_fingerprint=runtime_fingerprint),
        # S5-C2a：工作区形状 + `input/` 白名单材料的 md5/size（DS-04 证据的复核入口）
        **({"attempt_workspace": workspace.record(run_dir=ctx.run_dir)}
           if workspace is not None else {}),
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "experience_diagnostics": diagnostics,
        "experience_selection": selection.record,
        "working_memory_source_map": working_memory.source_map,
        "instruction_revision": instructions["revision"],
        "instruction_projection": {
            "effective_sha256": instructions["effective_sha256"],
            # 实际采用的 ID/版本/来源（改写为紧凑副本，便于冷存追溯）；未采用也给明确原因。
            "adopted": [{key: item[key] for key in
                         ("instruction_id", "version", "scope", "message",
                          "event_revision", "sealed_ref")} for item in directives],
            "not_adopted": [{"instruction_id": item["instruction_id"],
                             "version": item["version"], "reason": item["reason"]}
                            for item in instructions["not_adopted"]],
        },
    })
    if attempt.identity["attempt"] != attempt_sequence:
        # 先封存失败事实（避免留下只有 request 的 incomplete 记录），再显式失败。
        message = (f'指令作用域预留的尝试序号 {attempt_sequence} 与实际 attempt '
                   f'{attempt.identity["attempt"]} 不一致；拒绝按错误尝试身份注入指令')
        attempt.finish("error", error=message, backend=backend_metadata)
        raise RuntimeError(message)
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
                                contract=contract, backend=backend, request_meta=request_meta,
                                execute_kwargs=(workspace.execute_kwargs()
                                                if workspace is not None else None))
            validation = validate(kind, payload, offered=offered)
    except BaseException as exc:
        message = f"{type(exc).__name__}: {exc}"
        safe_message = backend.redact(message)
        attempt.finish("interrupted" if isinstance(exc, asyncio.CancelledError) else "error",
                       error=safe_message, backend=backend_metadata)
        if safe_message != message:
            raise RuntimeError(safe_message) from None
        raise
    # 接受门（IL-03）：结果返回后按**本节点**有效指令指纹复核；变化 ⇒ 丢弃、显式失败。
    # 用指纹而不是目录 revision：改 N12 的指令不会取消 N6 的结果接受资格。
    rejection = None
    current = AC.effective(ctx.run_dir, node, attempt=attempt_sequence)
    if current["effective_sha256"] != instructions["effective_sha256"]:
        rejection = {"accepted": False, "reason": "effective_instruction_sha256_changed",
                     "requested_effective_sha256": instructions["effective_sha256"],
                     "current_effective_sha256": current["effective_sha256"],
                     "instruction_revision": instructions["revision"],
                     "current_instruction_revision": current["revision"]}
    if rejection is not None:
        message = (f'本节点有效指令在请求期间发生变化，结果按接受门丢弃、不进消费者'
                   f'（request={rejection["requested_effective_sha256"][:12]}，'
                   f'current={rejection["current_effective_sha256"][:12]}）')
        audit = {"error": message, "acceptance": rejection, "backend": backend_metadata}
        if cfg.available:
            audit.update({"payload": payload, "validation": validation})
        else:
            audit["payload"] = out
        attempt.finish("error", **audit)
        raise RuntimeError(message)
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
        # 展示摘录（`model_steps` 的 N3 digest markdown）回到 S3 之前的字节口径：
        # 不把机制层派生投影 `working_memory` 计入 key 集合；`request.input` 仍完整封存它。
        "input_digest": {k: (len(v) if isinstance(v, (list, dict)) else v)
                         for k, v in request_input.items() if k != "working_memory"},
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
