"""Host 管理的请求记录与人工经验筛选；不写业务状态、不重发请求。"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from host import paths as P

MAX_CONTEXT_BYTES = 120_000
MEMORY_RULE = ("历史 approved_experiences 仅是有来源的参考。当前事实、当前文档和 Host 校验优先；"
               "不得据历史经验签署闸门、忽略 blockers、改写计数或宣称本轮已通过。")


def normalized(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalized(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((normalized(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def encoded(value: Any) -> bytes:
    return json.dumps(normalized(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def scope_for(ctx, input_data: dict, contract: dict) -> dict:
    try:
        baseline = json.loads((ctx.run_dir / "view.json").read_text()).get("baseline")
    except (OSError, ValueError, AttributeError):
        baseline = None
    facts = {k: v for k, v in input_data.items()
             if k not in {"run_id", "cycle", "rework_reasons", "approved_experiences"}}
    return {"env_id": P.ENV_ID, "baseline": baseline,
            "facts_sha256": fingerprint(facts),
            "prompt_sha256": fingerprint({k: contract[k] for k in ("info", "instruct")}),
            "schema_sha256": fingerprint(contract["schema"])}


class SourceRejected(ValueError):
    """来源核验失败（`reason` 是 EXP 拒用原因，`str(exc)` 保持 v1 诊断原文）。"""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(message)


def resolve_source(root: Path, source: Any) -> tuple[str, str]:
    """核验 `source{path,sha256}`：路径必须落在数据根 `runs/` 内且 SHA-256 一致。

    **v1/v2 共用**这一处路径逃逸与锚规则（v1 诊断文案仍是原文：
    `source escapes workspace runs or missing` / `source fingerprint mismatch`）。
    `reason` 只做 v2 原因区分（`source_missing` / `source_corrupt`），不改变 v1 文本。
    """
    rel = Path(source["path"])  # KeyError/TypeError 原样抛出：v1 逐条诊断依赖其原文
    base = Path(root).resolve()
    runs = (base / "runs").resolve()
    resolved = (base / rel).resolve()
    if (rel.is_absolute() or not rel.parts or rel.parts[0] != "runs" or ".." in rel.parts
            or not runs.is_relative_to(base) or not resolved.is_relative_to(runs)):
        raise SourceRejected("source_corrupt", "source escapes workspace runs or missing")
    if not resolved.is_file():
        raise SourceRejected("source_missing", "source escapes workspace runs or missing")
    sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if sha != source.get("sha256"):
        raise SourceRejected("source_corrupt", "source fingerprint mismatch")
    return rel.as_posix(), sha


def _load_catalog(path: Path) -> tuple[Any, bytes | None, str | None]:
    """读取并解析经验目录；返回 `(doc, raw, error_type_name)`。

    `error_type_name` 保留 v1 的诊断口径（`OSError` / `JSONDecodeError` / …）。
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, type(exc).__name__
    try:
        return json.loads(raw.decode("utf-8")), raw, None
    except (ValueError, TypeError) as exc:
        return None, raw, type(exc).__name__


def _v1_pass(doc: Any, ctx, scope: dict) -> tuple[list[dict], list[str], str | None, str]:
    """v1 选择（原 `experiences()` 的逻辑原样；诊断文案逐值保持）。

    第 3 项是"整目录/整批被拒"的原因分类（用于选择记录的 `decision`/排障口径）：
    `"catalog"`（格式/版本/数量/重复 ID 不合格）、`"baseline"`（当前基线未知）、`None`；
    第 4 项是目录级拒用的细节（规则名，进 `experience_selection.rejection.detail`）。
    """
    try:
        items = catalog_items_v1(doc)
    except CatalogRejected as exc:
        return [], ["experience catalog rejected: ValueError"], "catalog", exc.reason
    if not scope.get("baseline"):
        return [], ["experience catalog rejected: current baseline unknown"], "baseline", ""
    selected, diagnostics = [], []
    for item in items:
        try:
            actor = item.get("approved_by")
            if item.get("status") != "approved" or not isinstance(actor, str) or not actor.startswith("human:") or not actor[6:].strip():
                raise ValueError("human confirmation missing")
            if item.get("scope") != scope:
                raise ValueError("scope mismatch")
            advice = item.get("advice")
            if not isinstance(advice, str) or not advice.strip() or len(advice) > 4000:
                raise ValueError("invalid advice size")
            source = item.get("source") or {}
            path, sha = resolve_source(ctx.kb.root, source)
            selected.append({"id": item["id"], "advice": advice,
                             "source": {"path": path, "sha256": sha}})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            diagnostics.append(f"{item['id']}: {exc}")
    return selected, diagnostics, None, ""


def experiences(ctx, scope: dict) -> tuple[list[dict], list[str]]:
    """v1 经验选择（对外行为保持：`{version:1}` 目录、scope 逐值相等、只读）。

    **兼容导出，不是第二套选择入口**：仅供 v1 审计/测试与既有调用使用；生产路径唯一走
    `select_experiences`（v1/v2 统一入口，含两阶段适用性与批次判定）。
    """
    path = ctx.kb.root / "adjudication" / "agent_experiences.json"
    if not path.exists():
        return [], []
    doc, _, error = _load_catalog(path)
    if error is not None:
        return [], [f"experience catalog rejected: {error}"]
    selected, diagnostics, _, _ = _v1_pass(doc, ctx, scope)
    return selected, diagnostics


BILLING_FIELDS = ("info", "instruct", "schema")


# ---------------------------------------------------------------------------
# EXP：经验分层（REV-13 §8；必测 EXP-01～03）
#
# 版本分派：`version == 1` ⇒ v1 原样（`_v1_pass`）；`version == 2` ⇒ 本段新逻辑；
# 其它 ⇒ 整目录拒用（复用 v1 的 `experience catalog rejected` 诊断）。
#
# 两阶段检查（顺序固定，诊断分开记 `phase`）：
#   ① 源完整性：目录格式/版本/人工批准/条目 revision/来源路径+sha256（`source_integrity_v2`）；
#   ② 当前事实适用性：typed 依赖 + 节点/环境/契约范围（`_applicability_checks`）。
#
# 拒用原因（EXP-03 的枚举为下限；`invalid_item`/`invalid_applicability` 是 v2 声明的细分）：
# `not_approved` / `revoked` / `source_missing` / `source_corrupt` / `dependency_changed` /
# `unknown_dependency` / `contract_incompatible` / `environment_mismatch` /
# `invalid_item` / `invalid_applicability` / `budget_batch_rejected`。
# 诊断只报非秘密 ID/规则，不回显凭据或建议正文。
# ---------------------------------------------------------------------------

#: 请求/经验契约的唯一显式版本 token（`general_advice` 的兼容范围与 typed `contract` 依赖都比对它）。
CONTRACT_VERSION = 1
#: 可选经验批次的显式字节上限（`experience_batch_bytes` 唯一计量；超出 ⇒ 整批拒用）。
EXPERIENCE_BATCH_MAX_BYTES = 8000
#: v2 目录的显式条目上限（旧版 ≤10 条规则保持）。
EXPERIENCE_V2_MAX_ITEMS = 10
EXP_KINDS = frozenset({"exact_fact", "general_advice"})
#: 与 `Attempt` 的节点枚举/`WM.ROLES` 同一集合（N3/N6/N8/N10/N11/N12），不新增节点类型。
EXP_NODES = frozenset({"N3", "N6", "N8", "N10", "N11", "N12"})
REJECT_REASONS = frozenset({
    "not_approved", "revoked", "source_missing", "source_corrupt", "dependency_changed",
    "unknown_dependency", "contract_incompatible", "environment_mismatch",
    "invalid_item", "invalid_applicability", "budget_batch_rejected"})

_V2_ITEM_FIELDS = frozenset({"id", "revision", "status", "approved_by", "kind", "advice",
                             "source", "applicability"})
_V2_APPLICABILITY_FIELDS = frozenset({"nodes", "environment_policy", "contract_versions",
                                      "dependencies"})
#: typed 依赖的字段白名单：声明了别的键 = 声明不合法（`invalid_applicability`）。
_DEPENDENCY_FIELDS: dict[str, tuple[str, ...]] = {
    "baseline": ("value",), "env": ("env_id",), "mode": ("value",),
    "contract": ("version",), "targets_sha256": ("value",),
    "file_sha256": ("path", "sha256")}


class ItemRejected(ValueError):
    """单条目或整目录拒用（`reason` 取自 `REJECT_REASONS` 或目录级说明）。"""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason if not detail else f"{reason}: {detail}")


class CatalogRejected(ItemRejected):
    """目录级拒用（格式/版本/条目数/重复 ID）——整目录不采用。"""


@dataclass(frozen=True)
class ExperienceSelection:
    """一次经验选择的完整结果：注入项 + 诊断（list[str] 兼容）+ 请求记录投影。"""

    lessons: list[dict]
    diagnostics: list[str]
    record: dict[str, Any]

    def reject_batch(self, reason: str, *, stage: str, detail: str = "",
                     extra: dict[str, Any] | None = None) -> "ExperienceSelection":
        """整批拒用（EXP-03）：清空注入项、候选 ID 全部进拒用清单，**不截断、不取前 N**。"""
        record = json.loads(json.dumps(self.record, ensure_ascii=False))
        rejected = list(record.get("rejected") or [])
        for entry in record.get("selected") or []:
            rejected.append({"id": entry["id"], "reason": reason, "detail": detail,
                             "phase": "batch"})
        record["selected"] = []
        record["rejected"] = rejected
        batch = dict(record.get("batch") or {})
        batch.update({"decision": "rejected", "reason": reason, "stage": stage})
        batch.update(extra or {})
        record["batch"] = batch
        message = f"experience batch rejected: {reason}" + (f" ({detail})" if detail else "")
        return ExperienceSelection([], self.diagnostics + [message], record)


def experience_batch_bytes(lessons: Any) -> int:
    """可选经验批次的紧凑序列化字节（**唯一实现**；批次上限与剩余预算都从这里取数）。"""
    return len(encoded({"approved_experiences": lessons}))


def applicability_context(ctx, *, node: str) -> dict:
    """Host 的当前适用性上下文（复用既有身份：`P.ENV_ID` / `ctx.mode` / view.json baseline）。

    与 `scope_for` 的审计指纹**分离**：这里只描述"当前事实/环境是什么"，不参与审计指纹计算。
    """
    try:
        baseline = json.loads((ctx.run_dir / "view.json").read_text()).get("baseline")
    except (OSError, ValueError, AttributeError):
        baseline = None
    return {"node": node, "env_id": P.ENV_ID, "mode": ctx.mode,
            "baseline": baseline, "contract_version": CONTRACT_VERSION}


def catalog_items_v1(doc: Any) -> list[dict]:
    """v1 目录格式（版本/条目对象/数量/重复 ID）；不合法 ⇒ `CatalogRejected` 整目录拒用。

    这是 v1 选择与迁移工具共用的**同一条**目录判据（v1 诊断文本由 `_v1_pass` 保持原文）。
    """
    if (not isinstance(doc, dict) or doc.get("version") != 1
            or not isinstance(doc.get("items"), list)):
        raise CatalogRejected("format/version")
    items = doc["items"]
    if len(items) > 10:
        raise CatalogRejected("catalog exceeds ten entries")
    ids = [item.get("id") if isinstance(item, dict) else None for item in items]
    if (any(not isinstance(item_id, str) or not item_id for item_id in ids)
            or len(set(ids)) != len(ids)):
        raise CatalogRejected("items must be unique objects with non-empty id")
    return items


def catalog_items_v2(doc: Any) -> list[dict]:
    """v2 目录格式（版本/条目对象/数量/重复 ID）；不合法 ⇒ `CatalogRejected` 整目录拒用。"""
    if (not isinstance(doc, dict) or doc.get("version") != 2
            or not isinstance(doc.get("items"), list)):
        raise CatalogRejected("format/version")
    items = doc["items"]
    if len(items) > EXPERIENCE_V2_MAX_ITEMS:
        raise CatalogRejected(f"catalog exceeds {EXPERIENCE_V2_MAX_ITEMS} entries")
    ids = [item.get("id") if isinstance(item, dict) else None for item in items]
    if (any(not isinstance(item_id, str) or not item_id for item_id in ids)
            or len(set(ids)) != len(ids)):
        raise CatalogRejected("items must be unique objects with non-empty id")
    return items


def source_integrity_v2(item: dict, root: Path) -> dict:
    """阶段①：条目声明/人工批准/revision/来源路径+sha256（**不**核验当前事实适用性）。"""
    if not isinstance(item, dict):
        raise ItemRejected("invalid_item", "item is not an object")
    unknown = sorted(set(item) - _V2_ITEM_FIELDS)
    if unknown:
        raise ItemRejected("invalid_item", f"unknown fields: {', '.join(unknown)}")
    if not isinstance(item.get("id"), str) or not item["id"]:
        raise ItemRejected("invalid_item", "invalid or missing id")
    revision = item.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ItemRejected("invalid_item", "revision must be an integer >= 1")
    status = item.get("status")
    if status == "revoked":
        raise ItemRejected("revoked", "item revoked by human")
    if status != "approved":
        raise ItemRejected("not_approved", "status is not approved")
    actor = item.get("approved_by")
    if not isinstance(actor, str) or not actor.startswith("human:") or not actor[6:].strip():
        raise ItemRejected("not_approved", "human confirmation missing")
    if item.get("kind") not in EXP_KINDS:
        raise ItemRejected("invalid_item", "kind must be exact_fact or general_advice")
    advice = item.get("advice")
    if (not isinstance(advice, str) or not advice.strip()
            or len(advice) > 4000):
        raise ItemRejected("invalid_item", "invalid advice size")
    source = item.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise ItemRejected("invalid_item", "source must declare path and sha256")
    if not isinstance(source.get("sha256"), str):
        raise ItemRejected("source_corrupt", "source fingerprint mismatch")
    try:
        path, sha = resolve_source(root, source)
    except SourceRejected as exc:
        raise ItemRejected(exc.reason, str(exc)) from None
    return {"id": item["id"], "revision": revision, "kind": item["kind"], "advice": advice,
            "source": {"path": path, "sha256": sha}}


def _data_path(root: Path, rel: Any) -> Path | None:
    """在数据根内解析相对路径；绝对路径/`..`/符号链接逃逸/缺件 ⇒ None（不可核验）。"""
    if not isinstance(rel, str) or not rel:
        return None
    path = Path(rel)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        return None
    base = Path(root).resolve()
    resolved = (base / path).resolve()
    if not resolved.is_relative_to(base):
        return None
    return resolved if resolved.is_file() else None


def _validate_dependency(dep: Any) -> str:
    """声明形状校验（阶段②的第一步）：返回 `type`；不合法 ⇒ `invalid_applicability`。"""
    if not isinstance(dep, dict):
        raise ItemRejected("invalid_applicability", "dependency must be an object")
    kind = dep.get("type")
    if not isinstance(kind, str) or not kind:
        raise ItemRejected("invalid_applicability", "dependency type missing")
    if kind not in _DEPENDENCY_FIELDS:
        raise ItemRejected("unknown_dependency", f"unknown dependency type: {kind}")
    fields = _DEPENDENCY_FIELDS[kind]
    unknown = sorted(set(dep) - {"type", *fields})
    if unknown:
        raise ItemRejected("invalid_applicability",
                           f"dependency {kind} unknown fields: {', '.join(unknown)}")
    if kind == "baseline":
        if "value" not in dep:
            raise ItemRejected("invalid_applicability", "baseline dependency needs value")
    elif kind == "env":
        if not isinstance(dep.get("env_id"), str) or not dep["env_id"]:
            raise ItemRejected("invalid_applicability", "env dependency needs env_id")
    elif kind == "mode":
        if dep.get("value") not in ("real", "drill"):
            raise ItemRejected("invalid_applicability", "mode dependency must be real or drill")
    elif kind == "contract":
        version = dep.get("version")
        if not isinstance(version, int) or isinstance(version, bool):
            raise ItemRejected("invalid_applicability",
                               "contract dependency needs integer version")
    elif kind == "targets_sha256":
        if not isinstance(dep.get("value"), str) or not dep["value"]:
            raise ItemRejected("invalid_applicability",
                               "targets_sha256 dependency needs value")
    else:  # file_sha256
        if not isinstance(dep.get("path"), str) or not dep["path"]:
            raise ItemRejected("invalid_applicability", "file_sha256 dependency needs path")
        if not isinstance(dep.get("sha256"), str) or not dep["sha256"]:
            raise ItemRejected("invalid_applicability", "file_sha256 dependency needs sha256")
    return kind


def resolve_dependency(dep: dict, *, root: Path, context: dict,
                       input_data: Any) -> str | None:
    """typed 依赖解析（**唯一实现**）：None = 通过，否则返回拒用原因。

    - 不可解析/不可核验（未知 type、缺 targets、缺件、逃逸、当前基线未知）⇒ `unknown_dependency`；
    - 可解析但当前事实不同 ⇒ `dependency_changed` / `environment_mismatch` / `contract_incompatible`。

    **原因映射**（只报规则名，不回显材料）：`baseline`/`targets_sha256`/`file_sha256` 不符 ⇒
    `dependency_changed`；`env`/`mode` 不符 ⇒ `environment_mismatch`；`contract` 版本不符 ⇒
    `contract_incompatible`。
    """
    kind = dep["type"]
    if kind == "baseline":
        if context.get("baseline") is None:
            return "unknown_dependency"
        return None if normalized(dep["value"]) == normalized(context["baseline"]) \
            else "dependency_changed"
    if kind == "env":
        return None if dep["env_id"] == context["env_id"] else "environment_mismatch"
    if kind == "mode":
        return None if dep["value"] == context["mode"] else "environment_mismatch"
    if kind == "contract":
        return None if dep["version"] == CONTRACT_VERSION else "contract_incompatible"
    if kind == "targets_sha256":
        if not isinstance(input_data, dict) or "targets" not in input_data:
            return "unknown_dependency"
        return None if fingerprint(input_data["targets"]) == dep["value"] \
            else "dependency_changed"
    if kind == "file_sha256":
        resolved = _data_path(root, dep["path"])
        if resolved is None:
            return "unknown_dependency"
        try:
            sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError:
            return "unknown_dependency"
        return None if sha == dep["sha256"] else "dependency_changed"
    return "unknown_dependency"


def _applicability_checks(item: dict, *, node: str, context: dict, root: Path,
                          input_data: Any) -> dict:
    """阶段②：节点/环境策略/契约兼容范围 + 全部 typed 依赖逐项核验（依声明顺序短路）。

    原因映射：节点白名单不含当前节点或 `environment_policy` 不符 ⇒ `environment_mismatch`；
    声明的 `contract_versions` 不含 `CONTRACT_VERSION` ⇒ `contract_incompatible`；
    依赖结论取自 `resolve_dependency`；声明形状坏 ⇒ `invalid_applicability`。
    """
    applicability = item.get("applicability")
    if not isinstance(applicability, dict):
        raise ItemRejected("invalid_applicability", "applicability must be an object")
    unknown = sorted(set(applicability) - _V2_APPLICABILITY_FIELDS)
    if unknown:
        raise ItemRejected("invalid_applicability",
                           f"applicability unknown fields: {', '.join(unknown)}")
    nodes = applicability.get("nodes")
    if (not isinstance(nodes, list) or not nodes
            or any(not isinstance(entry, str) or not entry for entry in nodes)):
        raise ItemRejected("invalid_applicability", "nodes must be a non-empty list")
    if len(set(nodes)) != len(nodes) or any(entry not in EXP_NODES for entry in nodes):
        raise ItemRejected("invalid_applicability", "nodes must be unique known node ids")
    policy = applicability.get("environment_policy")
    if policy is not None and (not isinstance(policy, str) or not policy.strip()):
        raise ItemRejected("invalid_applicability", "environment_policy must be a string")
    versions = applicability.get("contract_versions")
    if versions is not None:
        if (not isinstance(versions, list)
                or any(not isinstance(entry, int) or isinstance(entry, bool)
                       for entry in versions)
                or len(set(versions)) != len(versions)):
            raise ItemRejected("invalid_applicability",
                               "contract_versions must be unique integers")
    dependencies = applicability.get("dependencies")
    if not isinstance(dependencies, list):
        raise ItemRejected("invalid_applicability", "dependencies must be a list")
    for dependency in dependencies:
        _validate_dependency(dependency)
    # 适用性不得 fail-open（Lead 裁决 2026-10-28；REV-13 §8.3 / 设计 §7）：
    # ① exact_fact 必须绑定当前事实——没有 typed 依赖就永远检测不到资源变化；
    # ② general_advice 必须绑定已批准的环境策略或契约兼容范围——typed 依赖是额外核验，
    #    不替代批准范围（"缺依赖不是通用的理由"，反过来"有依赖也不等于有范围"）。
    if item["kind"] == "exact_fact" and not dependencies:
        raise ItemRejected("invalid_applicability",
                           "exact_fact requires explicit typed dependencies")
    if item["kind"] == "general_advice" and policy is None and not versions:
        raise ItemRejected(
            "invalid_applicability",
            "general_advice requires an approved environment policy or contract range")

    checks: dict[str, Any] = {}
    if node not in nodes:
        raise ItemRejected("environment_mismatch", f"current node {node} not approved")
    checks["nodes"] = "ok"
    if policy is not None:
        expected = f"{context['env_id']}/{context['mode']}"
        if policy != expected:
            raise ItemRejected("environment_mismatch", "environment_policy mismatch")
        checks["environment_policy"] = "ok"
    else:
        checks["environment_policy"] = "absent"
    if versions is not None:
        if CONTRACT_VERSION not in versions:
            raise ItemRejected("contract_incompatible",
                               "current contract version not in approved versions")
        checks["contract_versions"] = "ok"
    else:
        checks["contract_versions"] = "absent"
    results = []
    for dependency in dependencies:
        reason = resolve_dependency(dependency, root=root, context=context,
                                    input_data=input_data)
        results.append({"type": dependency["type"], "result": reason or "ok"})
        if reason:
            raise ItemRejected(reason, f"dependency {dependency['type']}: {reason}")
    checks["dependencies"] = results
    return checks


def _legacy_record(context: dict, *, catalog_version: Any, catalog_sha: str | None,
                   lessons: Sequence[dict] = (), diagnostics: Sequence[str] = (),
                   rejected_reason: str | None = None) -> dict:
    """v1 选择记录（保持 legacy 语义；不做 v2 的批次字节判定）。"""
    if rejected_reason == "catalog":
        decision = "catalog_rejected"
    elif rejected_reason == "baseline":
        decision = "baseline_unknown"
    elif lessons:
        decision = "selected"
    elif diagnostics:
        decision = "rejected_items"
    else:
        decision = "no_applicable_items"
    return {"catalog_version": catalog_version, "catalog_sha256": catalog_sha,
            "selection_mode": "legacy_scope_match", "applicable_context": dict(context),
            "selected": [{"id": entry["id"], "revision": None, "kind": None,
                          "source": dict(entry["source"]),
                          "checks": {"scope_equal": True}} for entry in lessons],
            "rejected": [], "rejected_structured": False,
            "batch": {"candidates": len(lessons),
                      "bytes": experience_batch_bytes(list(lessons)),
                      "limit_bytes": EXPERIENCE_BATCH_MAX_BYTES,
                      "item_limit": 10, "enforced": False, "decision": decision}}


def _rejected_record(context: dict, *, catalog_version: Any, catalog_sha: str | None,
                     reason: str, detail: str = "") -> dict:
    """目录**存在但无法采用**（读取/解析/版本/格式非法）时的选择记录。

    与"目录不存在/未配置"的 legacy 空态区分：`selection_mode="catalog_rejected"` 且带
    `rejection{reason,detail}`，避免排障时被误读成正常 legacy 精确匹配。行为不变：
    整目录不采用、不注入，诊断仍走 `experience catalog rejected: …`。
    `reason` 只能是非秘密规则名（`catalog_unreadable`/`catalog_unparsable`/`catalog_invalid`）。
    """
    record = _legacy_record(context, catalog_version=catalog_version, catalog_sha=catalog_sha,
                            rejected_reason="catalog")
    record["selection_mode"] = "catalog_rejected"
    record["rejection"] = {"reason": reason, "detail": detail}
    return record


def _v2_selection(ctx, raw: bytes, doc: Any, context: dict, node: str,
                  input_data: Any) -> ExperienceSelection:
    """v2 选择：两阶段筛选 → 按 id 确定性排序 → 显式批次上限（不截断、不取前 N）。"""
    record: dict[str, Any] = {
        "catalog_version": 2, "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "selection_mode": "v2_applicability", "applicable_context": dict(context),
        "selected": [], "rejected": [],
        "batch": {"candidates": 0, "bytes": 0, "limit_bytes": EXPERIENCE_BATCH_MAX_BYTES,
                  "item_limit": EXPERIENCE_V2_MAX_ITEMS, "enforced": True,
                  "decision": "no_applicable_items"}}
    try:
        items = catalog_items_v2(doc)
    except CatalogRejected as exc:
        record.update({"selection_mode": "catalog_rejected",
                       "rejection": {"reason": "catalog_invalid", "detail": exc.reason}})
        record["batch"]["decision"] = "catalog_rejected"
        return ExperienceSelection([], [f"experience catalog rejected: {exc.reason}"], record)

    selected: list[dict] = []
    rejected: list[dict] = []
    diagnostics: list[str] = []
    for item in items:
        try:
            entry = source_integrity_v2(item, ctx.kb.root)
        except ItemRejected as exc:
            rejected.append({"id": str(item.get("id") or "<missing>"), "reason": exc.reason,
                             "detail": exc.detail, "phase": "source_integrity"})
            diagnostics.append(f"{item.get('id') or '<missing>'}: {exc.reason}")
            continue
        try:
            checks = _applicability_checks(item, node=node, context=context,
                                           root=ctx.kb.root, input_data=input_data)
        except ItemRejected as exc:
            rejected.append({"id": entry["id"], "reason": exc.reason,
                             "detail": exc.detail, "phase": "applicability"})
            diagnostics.append(f"{entry['id']}: {exc.reason}")
            continue
        selected.append({**entry, "checks": checks})

    selected.sort(key=lambda entry: entry["id"])  # 确定性顺序；不引入学习排序/相似度
    lessons = [{"id": entry["id"], "revision": entry["revision"], "kind": entry["kind"],
                "advice": entry["advice"], "source": dict(entry["source"])}
               for entry in selected]
    record["selected"] = [{"id": entry["id"], "revision": entry["revision"],
                           "kind": entry["kind"], "source": dict(entry["source"]),
                           "checks": entry["checks"]} for entry in selected]
    record["rejected"] = rejected
    batch_bytes = experience_batch_bytes(lessons)
    record["batch"].update({"candidates": len(lessons), "bytes": batch_bytes,
                            "decision": "selected" if lessons else "no_applicable_items"})
    selection = ExperienceSelection(lessons, diagnostics, record)
    if lessons and batch_bytes > EXPERIENCE_BATCH_MAX_BYTES:
        return selection.reject_batch(
            "budget_batch_rejected", stage="batch_bytes",
            detail=f"{batch_bytes} > {EXPERIENCE_BATCH_MAX_BYTES} bytes",
            extra={"candidates": len(lessons), "checked_bytes": batch_bytes})
    return selection


def select_experiences(ctx, scope: dict, *, node: str,
                       input_data: Any) -> ExperienceSelection:
    """EXP 选择入口（v1 走 `_v1_pass` 原样；v2 走适用性分层）。

    `scope` 仍由 `scope_for` 计算并随请求封存（审计指纹）；**v2 不使用它判复用**
    （EXP-02：审计指纹 ≠ 适用条件）。本函数不写任何目录、不晋升经验。
    """
    context = applicability_context(ctx, node=node)
    path = ctx.kb.root / "adjudication" / "agent_experiences.json"
    if not path.exists():
        return ExperienceSelection([], [], _legacy_record(
            context, catalog_version=None, catalog_sha=None, rejected_reason=None))
    doc, raw, error = _load_catalog(path)
    if error is not None:
        return ExperienceSelection(
            [], [f"experience catalog rejected: {error}"],
            _rejected_record(context, catalog_version=None,
                             catalog_sha=(hashlib.sha256(raw).hexdigest()
                                          if raw is not None else None),
                             reason=("catalog_unreadable" if raw is None
                                     else "catalog_unparsable"),
                             detail=error))
    version = doc.get("version") if isinstance(doc, dict) else None
    catalog_sha = hashlib.sha256(raw).hexdigest() if raw is not None else None
    if version == 2:
        return _v2_selection(ctx, raw, doc, context, node, input_data)
    lessons, diagnostics, rejected_reason, rejected_detail = _v1_pass(doc, ctx, scope)
    if rejected_reason == "catalog":
        return ExperienceSelection(lessons, diagnostics, _rejected_record(
            context, catalog_version=version, catalog_sha=catalog_sha,
            reason="catalog_invalid", detail=rejected_detail))
    return ExperienceSelection(lessons, diagnostics, _legacy_record(
        context, catalog_version=version, catalog_sha=catalog_sha,
        lessons=lessons, diagnostics=diagnostics, rejected_reason=rejected_reason))


def measure_budget(input_data: Any, contract: dict) -> dict:
    """Host 唯一的预算测量（C1/R5）：紧凑序列化 `{input, info, instruct, schema}`。

    计量口径只有这一份：准入 `check_budget` 与对外展示 `context_budget` 都从这里取数。
    分项为各字段值的紧凑序列化字节；`overhead_bytes` 是外层键名/冒号/逗号/花括号的显式开销，
    保证 `sum(breakdown) + overhead == used_bytes`。
    """
    fields = {"input": input_data, **contract}
    breakdown = {key: len(encoded(value)) for key, value in fields.items()}
    total = len(encoded(fields))
    return {"used_bytes": total, "breakdown": breakdown,
            "overhead_bytes": total - sum(breakdown.values()), "limit_bytes": MAX_CONTEXT_BYTES}


def check_budget(input_data: dict, contract: dict) -> int:
    size = measure_budget(input_data, contract)["used_bytes"]
    if size > MAX_CONTEXT_BYTES:
        raise RuntimeError(f"agent context budget exceeded（上下文预算）: {size} > {MAX_CONTEXT_BYTES} bytes")
    return size


def context_budget(request: Any, attempt: int | None = None) -> dict:
    """把**已封存记录**投影成窗口可解释的预算事实（只读，不回写历史 request 文件）。

    记录带齐 `input`/`info`/`instruct`/`schema` 时用 `measure_budget` 重算，与准入同一实现；
    缺计费材料（旧记录）⇒ `measured=False` 且总量保持 `None`，不估算、不拿记录大小冒充。
    `storage` 是 `offered`/`scope` 等**未发送**材料的记录存储大小，单列、不计费。
    token 一律 `unknown`（没有测量依据，不用字节折算）。
    """
    measure = {"measured": False, "used_bytes": None, "breakdown": {}, "overhead_bytes": None,
               "limit_bytes": MAX_CONTEXT_BYTES, "used_percent": None, "usage": "unknown",
               "storage": {"offered_bytes": None, "scope_bytes": None},
               "token_estimate": "unknown", "attempt": attempt}
    if not isinstance(request, dict):
        return measure
    for key in ("offered", "scope"):
        if key in request:
            measure["storage"][f"{key}_bytes"] = len(encoded(request[key]))
    if not isinstance(request.get("input"), dict) or any(key not in request for key in BILLING_FIELDS):
        return measure
    measured = measure_budget(request["input"], {key: request[key] for key in BILLING_FIELDS})
    limit = measured["limit_bytes"]
    measure.update({**measured, "measured": True,
                    "usage": "known" if limit else "unknown",
                    "used_percent": round(measured["used_bytes"] / limit * 100) if limit else None})
    return measure


def _sync_directory(folder: Path) -> None:
    """同步目录项；不承诺断电持久性（R1 契约只承诺进程终止）。"""
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_once(path: Path, content: bytes) -> None:
    """把内容**不可覆盖地原子发布**到 `path`（R1，`AGENT_CONTEXT_SPEC` 原子发布条款）。

    私有临时件（同目录）→ `fsync` → `os.link`（已存在则失败）→ 删除临时件 → 同步目录。
    任一点被终止时，最终名下只可能「不存在」或「完整」；临时件名不参与读取扫描。
    本函数仍是「一次写成」，与历史的 `_write_once` 语义一致，只是不再边写边暴露最终名。
    """
    path = Path(path)
    folder = path.parent
    fd, temp_name = tempfile.mkstemp(prefix=".publish-", suffix=".tmp", dir=folder)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        os.link(temp, path)  # 不可覆盖：已发布的同名记录绝不被改写
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()
        _sync_directory(folder)


def seal_record(path: Path, value: Any) -> None:
    """公开封存接口：写数据 + 校验和（唯一发布点；顺序固定 数据 → 校验和）。"""
    content = encoded(value)
    _write_once(path, content)
    _write_once(path.with_suffix(".sha256"), hashlib.sha256(content).hexdigest().encode("ascii"))


#: 兼容别名（历史调用与测试仍可使用；新代码走 `seal_record`）。
_sealed = seal_record


def record_state(path: Path) -> str:
    """只读诊断一次记录文件：`absent / incomplete / corrupt / committed`（F08）。

    - `absent`：文件不存在；
    - `incomplete`：数据在、校验和缺失（进程在两步之间被终止的典型状态）；
    - `corrupt`：校验和不匹配或 JSON 不可解析；
    - `committed`：内容与校验和一致且可解析。
    本函数不修文件、不删除、不回填。
    """
    path = Path(path)
    digest_path = path.with_suffix(".sha256")
    # 符号链接是安全信号（F08 复核 M1）：显式失败，不得静默降级成普通状态。
    if path.is_symlink() or digest_path.is_symlink():
        raise ValueError("agent record 路径使用符号链接")
    if not path.is_file():
        return "absent"
    if not digest_path.is_file():
        return "incomplete"
    try:
        content = path.read_bytes()
        expected = digest_path.read_text().strip()
    except OSError:
        return "incomplete"
    if hashlib.sha256(content).hexdigest() != expected:
        return "corrupt"
    try:
        json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "corrupt"
    return "committed"


class Attempt:
    def __init__(self, ctx, node: str, request: dict):
        if not re.fullmatch(r"N(?:3|6|8|10|11|12)", node):
            raise ValueError(f"unsupported model node: {node}")
        self.ctx = ctx
        root = ctx.run_dir / "agent_calls" / node
        root.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while True:
            self.path = root / f"attempt-{sequence:06d}"
            try:
                self.path.mkdir()
                break
            except FileExistsError:
                sequence += 1
        self.identity = {"format_version": 1, "run_id": ctx.run_id, "node": node,
                         "attempt": sequence}
        _sealed(self.path / "request.json", {**request, **self.identity,
                "memory_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def finish(self, status: str, **result) -> None:
        _sealed(self.path / "result.json", {**result, **self.identity, "status": status})

    def refs(self) -> dict:
        return {"request_ref": (self.path / "request.json").relative_to(self.ctx.run_dir).as_posix(),
                "result_ref": (self.path / "result.json").relative_to(self.ctx.run_dir).as_posix()}


def verify_attempt(path: Path) -> dict:
    out = {}
    for name in ("request", "result"):
        target = Path(path) / f"{name}.json"
        if target.is_symlink() or target.with_suffix(".sha256").is_symlink():
            raise ValueError("agent record 路径使用符号链接")
        try:
            content = (path / f"{name}.json").read_bytes()
            expected = (path / f"{name}.sha256").read_text().strip()
        except OSError as exc:
            raise ValueError(f"incomplete agent record: {name}") from exc
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"agent record checksum mismatch: {name}")
        out[name] = json.loads(content)
    keys = ("format_version", "run_id", "node", "attempt")
    if any(out["request"].get(k) != out["result"].get(k) for k in keys):
        raise ValueError("agent record identity mismatch")
    return out


#: A2（REV-13 §5.2）请求契约的读出入口：旧记录缺省 `legacy`/`unknown`，只读不回填。
#: 唯一实现在 `agent_backends.base.read_contract`（延迟导入：本模块在包初始化早期被引用）。
def contract_view(request: dict | None) -> dict:
    from host.agent_backends.base import read_contract

    return read_contract(request)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify agent records without reissuing requests.")
    parser.add_argument("--verify", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = verify_attempt(args.verify)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "run_id": record["request"]["run_id"],
                      "node": record["request"]["node"], "attempt": record["request"]["attempt"],
                      "status": record["result"]["status"], "scope": record["request"].get("scope")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
