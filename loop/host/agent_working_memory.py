"""Host 的可重建工作记忆（REV-13 §6）：只投影当前业务状态明确引用的有效记录。

为什么单独一个模块：WM 是**派生投影**，不是第二套账本。它不读目录里"最新一次"、不写业务状态、
不自写落盘文件、不自建判据。本模块只做四件事：

1. 按**节点字段注册表**把已在本次请求 `input_data` 中的既有字段投影成五类条目
   （`observed_fact` / `human_decision` / `model_proposal` / `open_issue` / `constraint`）；
2. 已在输入中的正文只留 `input_ref`（JSON Pointer 指向同一请求的既有字段），**不复制**（WM-05）；
3. 用 `agent_memory` 的 `encoded`/`fingerprint`/`verify_attempt` 做**确定性指纹**与**来源核验**：
   同一明确来源重建 ⇒ 同一 `snapshot_sha256`（WM-01）；源版本变化 ⇒ 新指纹；
   源半件/篡改/越界/跨 run ⇒ `ValueError`（节点失败，不吞）；
4. 不可信/缺失来源如实登记进 `unavailable[]`（旧格式/缺来源**不标 verified**），
   并保留当前权威事实，不编造。

明确不做：语义摘要/总结模型、向量检索、第二套 issue 关闭/重开规则、第二套预算判据。
预算准入仍唯一走 `AM.measure_budget`/`check_budget`；本模块只额外报告**强制材料的字节缺口**
（`mandatory_bytes`），供调用方在超限时给出可读原因，**不得**替代或绕过总预算检查。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from host import agent_memory as AM

WM_VERSION = 1
AVAILABILITY_VERIFIED = "verified"
AVAILABILITY_UNAVAILABLE = "unavailable"

#: WM-02 的五类条目；模型判断永远是 `model_proposal`，绝不晋升为 `observed_fact`。
ENTRY_KINDS = frozenset({"observed_fact", "human_decision", "model_proposal",
                         "open_issue", "constraint"})

#: 强制条目（REV-13 §6.3）：必需事实、未解决问题与已生效约束不得为省预算而删除。
MANDATORY_KINDS = frozenset({"observed_fact", "open_issue", "constraint"})

#: 本片接线的模型节点（与 `agent_memory.Attempt` 的节点枚举一致）。
ROLES = frozenset({"N3", "N6", "N8", "N10", "N11", "N12"})

#: 需要"闸门可读事实"的节点（设计 §5 表：N10/N12 = 证据分类事实/Host 计数/闸门可读事实）。
#: 其它节点没有该消费需求 ⇒ 不注入（"没有消费需求的历史不注入"，REV-13 §6.2）。
_GATE_CONSUMERS = frozenset({"N10", "N12"})

#: 节点字段注册表：`slot` 稳定命名（进 `entry_id`/`source_map`），`pointer` 指同一请求 `input_data`。
#: `items=True` 表示逐项扇出（只有问题列表需要保留逐条身份），其余整字段一条引用。
#: `packet=True` 表示该字段是作者交接包：只有 `availability=verified` 且来源可核验时才投影。
_RULES: dict[str, tuple[dict[str, Any], ...]] = {
    "N3": (
        {"slot": "diffs", "pointer": "/diffs", "kind": "observed_fact"},
        {"slot": "coverage", "pointer": "/coverage", "kind": "observed_fact"},
    ),
    "N6": (
        {"slot": "targets", "pointer": "/targets", "kind": "observed_fact"},
        {"slot": "rework_handoff.issues", "pointer": "/rework_handoff/issues",
         "kind": "open_issue", "items": True},
        {"slot": "rule", "pointer": "/rule", "kind": "constraint"},
        {"slot": "write_scope_rule", "pointer": "/write_scope_rule", "kind": "constraint"},
    ),
    "N8": (
        {"slot": "sandbox_cases", "pointer": "/sandbox_cases", "kind": "observed_fact"},
        {"slot": "coverage_summary", "pointer": "/coverage_summary", "kind": "observed_fact"},
        {"slot": "revision_points", "pointer": "/revision_points", "kind": "observed_fact"},
        {"slot": "applied_edits", "pointer": "/applied_edits", "kind": "observed_fact"},
        {"slot": "author_handoff", "pointer": "/author_handoff",
         "kind": "model_proposal", "packet": True},
        {"slot": "review_assignment.issues", "pointer": "/review_assignment/issues",
         "kind": "open_issue", "items": True},
        {"slot": "checklist", "pointer": "/checklist", "kind": "constraint"},
        {"slot": "rule", "pointer": "/rule", "kind": "constraint"},
    ),
    "N10": (
        {"slot": "buckets", "pointer": "/buckets", "kind": "observed_fact"},
        {"slot": "revision_points", "pointer": "/revision_points", "kind": "observed_fact"},
        {"slot": "counts", "pointer": "/counts", "kind": "observed_fact"},
        {"slot": "rule", "pointer": "/rule", "kind": "constraint"},
    ),
    "N11": (
        {"slot": "identity", "pointer": "/identity", "kind": "observed_fact"},
        {"slot": "evidence", "pointer": "/evidence", "kind": "observed_fact"},
        {"slot": "counts", "pointer": "/counts", "kind": "observed_fact"},
        {"slot": "case_states", "pointer": "/case_states", "kind": "observed_fact"},
        {"slot": "author_handoff", "pointer": "/author_handoff",
         "kind": "model_proposal", "packet": True},
        {"slot": "review_assignment.issues", "pointer": "/review_assignment/issues",
         "kind": "open_issue", "items": True},
        {"slot": "rule", "pointer": "/rule", "kind": "constraint"},
    ),
    "N12": (
        {"slot": "counts", "pointer": "/counts", "kind": "observed_fact"},
        {"slot": "verdict", "pointer": "/verdict", "kind": "observed_fact"},
        {"slot": "imprints", "pointer": "/imprints", "kind": "observed_fact"},
        {"slot": "cases", "pointer": "/cases", "kind": "observed_fact"},
        {"slot": "case_states", "pointer": "/case_states", "kind": "observed_fact"},
        {"slot": "conflicts", "pointer": "/conflicts", "kind": "observed_fact"},
        {"slot": "must_change_cases", "pointer": "/must_change_cases", "kind": "observed_fact"},
        {"slot": "rule", "pointer": "/rule", "kind": "constraint"},
    ),
}

#: run 作用域指令条目的 scope 枚举（与 `agent_control.IL_SCOPES` 同契约）。
_DIRECTIVE_SCOPES = frozenset({"attempt", "node_rework", "run"})
#: IL 封存事件来源引用：只允许本 run 的 `agent_controls/run/instruction-<seq>.json`。
_DIRECTIVE_REF = re.compile(r"agent_controls/run/instruction-(\d{6,})\.json")

_POINTER_ESCAPE = re.compile(r"~(?![01])")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_SEALED_REF = re.compile(r"agent_calls/(N(?:3|6|8|10|11|12))/attempt-([0-9]{6,})/request\.json")


def requires_gate(node: str) -> bool:
    """该节点是否消费"闸门可读事实"（只有它们需要只读闸门投影）。"""
    return node in _GATE_CONSUMERS


def resolve_input_ref(input_data: Any, pointer: str) -> Any:
    """解析 `input_ref`：JSON Pointer 指向**同一请求 `input_data`** 的既有字段。

    只做**存在性与边界**检查，不解释业务语义。拒绝：非字符串/不以 `/` 开头/非法 `~` 转义、
    以 `working_memory` 为根（自引用即循环）、缺失路径、越界或非规范索引、穿过标量。
    """
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError(f"working memory input_ref 非法：{pointer!r}")
    if _POINTER_ESCAPE.search(pointer):
        raise ValueError(f"working memory input_ref 转义非法：{pointer!r}")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
    if parts[0] == "working_memory":
        raise ValueError("working memory input_ref 不得指向 working_memory 自身（自引用/循环）")
    value = input_data
    for part in parts:
        if isinstance(value, dict):
            if part not in value:
                raise ValueError(f"working memory input_ref 缺失：{pointer!r}")
            value = value[part]
        elif isinstance(value, list):
            if not _INDEX.fullmatch(part):
                raise ValueError(f"working memory input_ref 索引非法：{pointer!r}")
            index = int(part)
            if index >= len(value):
                raise ValueError(f"working memory input_ref 越界：{pointer!r}")
            value = value[index]
        else:
            raise ValueError(f"working memory input_ref 穿过标量：{pointer!r}")
    return value


def _lookup(input_data: dict, pointer: str) -> tuple[bool, Any]:
    """注册表取字段：`(是否可得, 值)`。缺失字段只标 unavailable，不猜也不造。"""
    if (not isinstance(pointer, str) or not pointer.startswith("/")
            or _POINTER_ESCAPE.search(pointer) or pointer[1:].split("/")[0] == "working_memory"):
        raise ValueError(f"working memory 字段注册表指针非法：{pointer!r}")
    try:
        value = resolve_input_ref(input_data, pointer)
    except ValueError:
        return False, None
    return (False, None) if value is None else (True, value)


def _verify_sealed_source(ctx, source: Any) -> None:
    """核验 WM 引用的封存来源：跨 run / 越界 / 符号链接 / 半件 / 篡改 ⇒ `ValueError`。

    复用 `AM.verify_attempt`（封存校验的唯一实现）与 `AM.fingerprint`（指纹的唯一实现）；
    本函数只补 WM 需要的**身份**与**记录的指纹**两项检查，不另写校验和算法。
    """
    if not isinstance(source, dict):
        raise ValueError("working memory 来源缺少 source")
    request_ref, result_ref = source.get("request_ref"), source.get("result_ref")
    if not isinstance(request_ref, str) or not isinstance(result_ref, str):
        raise ValueError("working memory 来源引用不完整")
    match = _SEALED_REF.fullmatch(request_ref)
    if not match or result_ref != request_ref.replace("/request.json", "/result.json"):
        raise ValueError("working memory 来源引用非法")
    run_dir = Path(ctx.run_dir)
    folder = run_dir / Path(request_ref).parent
    current = folder
    while True:
        if current.is_symlink():
            raise ValueError("working memory 来源使用符号链接")
        if current == run_dir:
            break
        if current == current.parent:
            raise ValueError("working memory 来源越出本 run")
        current = current.parent
    if not folder.resolve().is_relative_to(run_dir.resolve()):
        raise ValueError("working memory 来源越出本 run")
    try:
        record = AM.verify_attempt(folder)
    except (OSError, ValueError) as exc:
        raise ValueError(f"working memory 来源记录不可用：{exc}") from exc
    identity = {"run_id": ctx.run_id, "node": match[1], "attempt": int(match[2])}
    for name in ("request", "result"):
        for key, expected in identity.items():
            if record[name].get(key) != expected:
                raise ValueError(f"working memory 来源 {name} 身份不匹配：{key}")
    for key, name in (("request_sha256", "request"), ("result_sha256", "result")):
        expected = source.get(key)
        if expected is not None and expected != AM.fingerprint(record[name]):
            raise ValueError(f"working memory 来源 {name} 指纹不匹配")


def _packet_state(ctx, packet: Any) -> str | None:
    """作者交接包是否可标 verified：`None` = 可信；返回字符串 = 不可信原因。"""
    if not isinstance(packet, dict):
        raise ValueError("working memory 作者交接包形状非法")
    availability = packet.get("availability")
    if availability in {"standin", "legacy", "unavailable"}:
        return f"作者交接 availability={availability}（旧格式/替身不标 verified）"
    if availability != "verified":
        raise ValueError(f"working memory 作者交接 availability 非法：{availability!r}")
    if not isinstance(packet.get("author_source"), dict):
        raise ValueError("working memory 作者交接声称 verified 但缺 author_source")
    _verify_sealed_source(ctx, packet["author_source"])
    return None


def _unavailable(rule: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"kind": rule["kind"], "slot": rule["slot"], "reason": reason}


def _entry(entry_id: str, kind: str, source_key: str, node: str, *,
           pointer: str | None = None, value: Any = None, sha256: str) -> dict[str, Any]:
    """一条 WM 条目：**二选一** `value` 或 `input_ref`（WR-05 载体要求）。"""
    entry: dict[str, Any] = {
        "entry_id": entry_id, "kind": kind, "source_keys": [source_key],
        "applicability": {"node": node}, "resource_versions": {source_key: sha256},
    }
    if pointer is not None:
        entry["input_ref"] = pointer
    else:
        entry["value"] = value
    return entry


def _gate_entries(ctx, node: str, projection: Any) -> tuple[list, list, dict]:
    """只读投影已核验闸门事实：不判定、不重签、不自造决策枚举。"""
    if projection is None:
        return [], [{"kind": "human_decision", "slot": "gate_authority",
                     "reason": "没有已核验的闸门投影来源"}], {}
    if not isinstance(projection, dict):
        raise ValueError("working memory 闸门投影形状非法")
    if projection.get("anchor_ok") is False:
        raise ValueError("working memory 闸门来源被外部修改（锚不一致），拒绝标 verified")
    if not projection.get("present"):
        reason = projection.get("reason") or "闸门账本不可用"
        return [], [{"kind": "human_decision", "slot": "gate_authority",
                     "reason": f"闸门账本不可用：{reason}"}], {}
    if projection.get("run_id") != ctx.run_id:
        raise ValueError("working memory 闸门投影属于另一个 run")
    entries, sources = [], {}
    for gate in sorted(projection.get("gates") or {}):
        item = projection["gates"][gate] or {}
        if item.get("human_signed") is not True or not item.get("decision"):
            continue
        value = {"gate": gate, "decision": item.get("decision"), "actor": item.get("actor"),
                 "actor_kind": item.get("actor_kind"), "human_signed": True,
                 "signed_at": item.get("signed_at"), "note": item.get("note"),
                 "rework_target": item.get("rework_target"),
                 "history_len": item.get("history_len")}
        key = f"gate_authority.{gate}"
        sha = AM.fingerprint(value)
        sources[key] = {"origin": "gate_authority", "pointer": None, "sha256": sha,
                        "kind": "human_decision", "present": True}
        entries.append(_entry(f"human_decision:{node}:{gate}", "human_decision", key, node,
                              value=value, sha256=sha))
    if not entries:
        return [], [{"kind": "human_decision", "slot": "gate_authority",
                     "reason": "无已核验人工决策（没有由 human 签署的闸门事实）"}], {}
    return entries, [], sources


def _instruction_entries(node: str, input_data: dict, instructions: Iterable[Any]) -> tuple[list, dict]:
    """已生效的人工指令 ⇒ `constraint`；**只引用**本次已发送的正文，不复制（WM-05）。"""
    provided = input_data.get("human_interventions")
    provided = provided if isinstance(provided, list) else []
    entries, sources = [], {}
    for index, instruction in enumerate(instructions or ()):
        message = instruction.get("message") if isinstance(instruction, dict) else instruction
        if not isinstance(message, str) or not message.strip():
            raise ValueError("working memory 指令缺少非空 message")
        if instruction not in provided:
            # 不复制正文、也不留"指向未发送材料"的索引：指令必须先随本次请求发送。
            raise ValueError("working memory 指令未随本次请求发送（只允许引用已发送正文）")
        pointer = f"/human_interventions/{provided.index(instruction)}"
        key = f"instruction.{index:04d}"
        sha = AM.fingerprint(instruction)
        sources[key] = {"origin": "request_input", "pointer": pointer, "sha256": sha,
                        "kind": "constraint", "present": True}
        entries.append(_entry(f"constraint:{node}:instruction[{index:04d}]", "constraint", key,
                              node, pointer=pointer, sha256=sha))
    return entries, sources


def _directive_entries(ctx, node: str, directives: Iterable[Any]) -> tuple[list, dict]:
    """run 作用域有效指令（IL）⇒ `constraint` 条目：`value` + 封存事件来源。

    为什么不复用 `human_interventions` 的 `input_ref`：run 指令由 Host 从**已封存事件**归约，
    不是客户端在本次输入里发的正文；因此按契约把它作为 `value` 条目注入（不新增顶层 input 键），
    `source_keys` 指向封存事件（`sealed_ref` + `event_revision`），便于冷存追溯。

    有效集归约与封存校验的唯一实现是 `agent_control`（红线 8：不出现第二套同判据）；
    这里只校验**载荷形状**（scope 枚举、封存来源必须指向本 run 的
    `agent_controls/run/instruction-<seq>.json` 且无逃逸/符号链接）并投影，
    形状非法 ⇒ 显式失败（不猜、不静默丢弃）。
    """
    entries, sources, seen = [], {}, set()
    for index, item in enumerate(directives or ()):
        if not isinstance(item, dict):
            raise ValueError("working memory 指令条目必须是对象")
        instruction_id = item.get("instruction_id")
        version = item.get("version")
        message = item.get("message")
        scope = item.get("scope")
        event_revision = item.get("event_revision")
        sealed_ref = item.get("sealed_ref")
        if not isinstance(instruction_id, str) or not instruction_id.strip():
            raise ValueError("working memory 指令条目缺少 instruction_id")
        if instruction_id in seen:
            raise ValueError(f"working memory 指令条目重复：{instruction_id}")
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError("working memory 指令条目 version 非法")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("working memory 指令条目缺少非空 message")
        if isinstance(event_revision, bool) or not isinstance(event_revision, int) or event_revision < 1:
            raise ValueError("working memory 指令条目缺少封存事件 revision")
        if not isinstance(sealed_ref, str) or not sealed_ref.strip():
            raise ValueError("working memory 指令条目缺少封存来源引用")
        if scope not in _DIRECTIVE_SCOPES:
            raise ValueError(f"working memory 指令条目 scope 非法：{scope!r}")
        match = _DIRECTIVE_REF.fullmatch(sealed_ref)
        if match is None:
            raise ValueError(f"working memory 指令来源引用非法：{sealed_ref!r}")
        if int(match.group(1)) != event_revision:
            raise ValueError("working memory 指令来源 revision 与引用不一致")
        run_dir = Path(ctx.run_dir)
        source = run_dir / sealed_ref
        if source.is_symlink() or not source.resolve().is_relative_to(run_dir.resolve()):
            raise ValueError("working memory 指令来源越界或使用符号链接")
        seen.add(instruction_id)
        value = {"instruction_id": instruction_id, "version": version,
                 "scope": item.get("scope"), "message": message}
        key = f"instruction_event.{event_revision:06d}"
        sha = AM.fingerprint(value)
        sources[key] = {"origin": "agent_controls/run", "sealed_ref": sealed_ref,
                        "event_revision": event_revision, "instruction_id": instruction_id,
                        "version": version, "sha256": sha, "kind": "constraint", "present": True}
        entries.append(_entry(f"constraint:{node}:directive[{index:04d}]", "constraint", key,
                              node, value=value, sha256=sha))
    return entries, sources


def _mandatory_bytes(entries: list[dict], input_data: dict) -> int:
    """强制材料的紧凑序列化字节（`AM.encoded`，与预算同一实现）。

    只作**缺口报告**：超限时调用方据此给出可读原因，准入仍唯一由 `AM.check_budget` 判定。
    """
    materials = []
    for entry in entries:
        if entry["kind"] not in MANDATORY_KINDS:
            continue
        material = (resolve_input_ref(input_data, entry["input_ref"])
                    if "input_ref" in entry else entry["value"])
        materials.append({"entry_id": entry["entry_id"], "kind": entry["kind"],
                          "material": material})
    return len(AM.encoded(materials))


@dataclass(frozen=True)
class WorkingMemory:
    """一次请求的工作记忆投影：模型侧载荷 + Host 侧冷存 source map + 缺口报告。"""

    payload: dict[str, Any]
    source_map: dict[str, Any]
    mandatory_bytes: int
    limit_bytes: int
    over_budget: bool


def build(ctx, node: str, input_data: dict[str, Any], *,
          instructions: Iterable[Any] = (), gate_projection: Any = None,
          directives: Iterable[Any] = ()) -> WorkingMemory:
    """从当前业务状态的**明确来源**重建工作记忆（不扫描目录、不重放效果、不调用模型）。

    - `input_data`：本次**实际发送**的请求输入（`input_ref` 只指向它，天然满足"索引≠材料已送达"）；
    - `instructions`：本次已生效的**会话内**人工指令（旧 `/control` 语义；引用已发送正文）；
    - `gate_projection`：`gate_authority.authority_view(run_id)` 的只读投影（只有 N10/N12 消费）；
    - `directives`：run 作用域有效指令（IL，`agent_control.effective()` 的归约结果）；
      作为 `constraint` 条目以 `value` 注入，来源指向封存事件，**不新增顶层 input 键**。
    """
    if node not in ROLES:
        raise ValueError(f"working memory 不支持的节点：{node!r}")
    if not isinstance(input_data, dict):
        raise ValueError("working memory 的输入必须是对象")
    if "working_memory" in input_data:
        raise ValueError("working memory 不得嵌套：input_data 已包含 working_memory")

    entries: list[dict] = []
    unavailable: list[dict] = []
    sources: dict[str, dict] = {}
    for rule in _RULES[node]:
        present, material = _lookup(input_data, rule["pointer"])
        if not present:
            unavailable.append(_unavailable(rule, "当前请求输入缺该字段"))
            continue
        if rule.get("packet"):
            reason = _packet_state(ctx, material)
            if reason is not None:
                unavailable.append(_unavailable(rule, reason))
                continue
        if rule.get("items"):
            if not isinstance(material, list):
                unavailable.append(_unavailable(rule, "来源不是列表，无法逐项投影"))
                continue
            for index, item in enumerate(material):
                if rule["kind"] == "open_issue" and (
                        not isinstance(item, dict) or not isinstance(item.get("issue_id"), str)
                        or not item["issue_id"]):
                    raise ValueError("working memory open_issue 来源条目不完整（缺 issue_id）")
                pointer = f"{rule['pointer']}/{index}"
                key = f"{rule['slot']}#{index:04d}"
                sha = AM.fingerprint(item)
                sources[key] = {"origin": "request_input", "pointer": pointer, "sha256": sha,
                                "kind": rule["kind"], "present": True}
                entries.append(_entry(f"{rule['kind']}:{node}:{rule['slot']}[{index:04d}]",
                                      rule["kind"], key, node, pointer=pointer, sha256=sha))
            continue
        sha = AM.fingerprint(material)
        key = rule["slot"]
        sources[key] = {"origin": "request_input", "pointer": rule["pointer"], "sha256": sha,
                        "kind": rule["kind"], "present": True}
        entries.append(_entry(f"{rule['kind']}:{node}:{rule['slot']}", rule["kind"], key, node,
                              pointer=rule["pointer"], sha256=sha))

    if requires_gate(node):
        gate_entries, gate_unavailable, gate_sources = _gate_entries(ctx, node, gate_projection)
        entries.extend(gate_entries)
        unavailable.extend(gate_unavailable)
        sources.update(gate_sources)
    instruction_entries, instruction_sources = _instruction_entries(node, input_data, instructions)
    entries.extend(instruction_entries)
    sources.update(instruction_sources)
    directive_entries, directive_sources = _directive_entries(ctx, node, directives)
    entries.extend(directive_entries)
    sources.update(directive_sources)

    entries.sort(key=lambda item: (item["kind"], item["entry_id"]))
    unavailable.sort(key=lambda item: (item["kind"], item["slot"]))
    availability = AVAILABILITY_VERIFIED if not unavailable else AVAILABILITY_UNAVAILABLE
    snapshot = AM.fingerprint({"version": WM_VERSION, "entries": entries,
                               "unavailable": unavailable})
    mandatory_bytes = _mandatory_bytes(entries, input_data)
    limit = AM.MAX_CONTEXT_BYTES
    payload = {"version": WM_VERSION, "availability": availability,
               "snapshot_sha256": snapshot, "entries": entries, "unavailable": unavailable}
    source_map = {
        "version": WM_VERSION, "run_id": ctx.run_id, "node": node,
        "snapshot_sha256": snapshot, "availability": availability,
        "entries": [{"entry_id": item["entry_id"], "kind": item["kind"],
                     "source_keys": list(item["source_keys"]),
                     "pointer": item.get("input_ref"), "consumers": [node]}
                    for item in entries],
        "sources": {key: sources[key] for key in sorted(sources)},
        "unavailable": unavailable,
        "mandatory_bytes": mandatory_bytes, "limit_bytes": limit,
        "over_budget": mandatory_bytes > limit,
    }
    return WorkingMemory(payload=payload, source_map=source_map,
                         mandatory_bytes=mandatory_bytes, limit_bytes=limit,
                         over_budget=mandatory_bytes > limit)


__all__ = [
    "AVAILABILITY_UNAVAILABLE", "AVAILABILITY_VERIFIED", "ENTRY_KINDS", "MANDATORY_KINDS",
    "ROLES", "WM_VERSION", "WorkingMemory", "build", "requires_gate", "resolve_input_ref",
]
