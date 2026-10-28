"""离线经验目录迁移/校验（REV-13 §8.2 / 计划 §3.3）：只读校验 + 产出 v2 候选草稿。

为什么是一个独立 CLI 而不是运行期能力：**审批与迁移是人做的事**。Host 只读人工目录
（`adjudication/agent_experiences.json`），选择路径永远不写它；本工具只把 v1 目录读成
一份机器可读报告，并在显式 `--out` 时产出 **v2 候选草稿**（新文件），人确认后才替换目录。

CLI：

    python -m host.experience_migrate --catalog <path> [--validate] [--out <new-path>] [--root <data-root>]

- `--validate`：只读校验 v1/v2 目录并输出机器可读 JSON 报告（`scope=source_integrity_only`，
  即只做**源完整性**：目录格式/版本/人工批准/revision/重复 ID/来源路径+sha256；
  不假装核验当前事实适用性——那需要运行上下文，见 EXP-02 两阶段检查）。
- `--out`：生成 v2 **候选草稿**（新文件；条目 `status:"draft"`、`approved_by:null`），
  报告给出 `old_id → new_id/revision` 与**条件变化说明**。拒绝覆盖 `--catalog` 指向的文件、
  拒绝写任何含 `adjudication` 目录段的路径、拒绝覆盖已存在的输出件。
- `--root`：数据根（来源路径相对它解析）。缺省按目录约定推导：
  `<root>/adjudication/agent_experiences.json` ⇒ root = 上级目录；不符合该布局时显式指定。

纪律：不修改人工目录、不改旧请求/源归档、不自动晋升、不改变已批准条目的用途或宽化范围；
报告只输出非秘密 ID/规则（不回显凭据或材料正文）；v2 选择/依赖解析判据全部复用
`host.agent_memory`（本工具不复制第二套判据）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from host import agent_memory as AM

#: 报告里标注的校验深度：只做源完整性，不假装核验了当前事实。
VALIDATION_SCOPE = "source_integrity_only"


def derive_root(catalog: Path) -> Path:
    """数据根推导：`<root>/adjudication/agent_experiences.json` ⇒ `<root>`；否则取同级目录。"""
    catalog = Path(catalog)
    if catalog.parent.name == "adjudication":
        return catalog.parent.parent
    return catalog.parent


def _v1_item_report(item: Any, root: Path) -> dict:
    """v1 条目**源完整性**检查（不比对 scope：审计指纹不是 v2 适用条件）。"""
    if not isinstance(item, dict):
        raise AM.ItemRejected("invalid_item", "item is not an object")
    if not isinstance(item.get("id"), str) or not item["id"]:
        raise AM.ItemRejected("invalid_item", "invalid or missing id")
    status = item.get("status")
    if status == "revoked":
        raise AM.ItemRejected("revoked", "item revoked by human")
    if status != "approved":
        raise AM.ItemRejected("not_approved", "status is not approved")
    actor = item.get("approved_by")
    if not isinstance(actor, str) or not actor.startswith("human:") or not actor[6:].strip():
        raise AM.ItemRejected("not_approved", "human confirmation missing")
    advice = item.get("advice")
    if (not isinstance(advice, str) or not advice.strip()
            or len(advice) > 4000):
        raise AM.ItemRejected("invalid_item", "invalid advice size")
    if not isinstance(item.get("scope"), dict):
        raise AM.ItemRejected("invalid_item", "v1 item must declare scope")
    source = item.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise AM.ItemRejected("invalid_item", "source must declare path and sha256")
    if not isinstance(source.get("sha256"), str):
        raise AM.ItemRejected("source_corrupt", "source fingerprint mismatch")
    try:
        path, sha = AM.resolve_source(root, source)
    except AM.SourceRejected as exc:
        raise AM.ItemRejected(exc.reason, str(exc)) from None
    return {"id": item["id"], "revision": None, "status": status,
            "source": {"path": path, "sha256": sha}}


def _base_report(catalog: Path, root: Path, raw: bytes | None,
                 version: Any) -> dict:
    return {"ok": False, "mode": "validate", "catalog": str(catalog),
            "catalog_sha256": (hashlib.sha256(raw).hexdigest() if raw is not None else None),
            "version": version, "root": str(root), "scope": VALIDATION_SCOPE,
            "counts": {"items": 0, "accepted": 0, "rejected": 0},
            "items": [], "notes": []}


def _read(catalog: Path) -> tuple[dict | None, bytes | None, str | None]:
    if not catalog.is_file():
        return None, None, "catalog not found"
    try:
        raw = catalog.read_bytes()
    except OSError as exc:
        return None, None, f"catalog unreadable: {type(exc).__name__}"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, TypeError) as exc:
        return None, raw, f"catalog unparsable: {type(exc).__name__}"
    return document, raw, None


def _items_for(document: Any) -> tuple[int, list[dict]]:
    """按版本选择共用的目录判据（v1/v2 各一条，均来自 `agent_memory`）。"""
    version = document.get("version") if isinstance(document, dict) else None
    if version == 2:
        return 2, AM.catalog_items_v2(document)
    return 1, AM.catalog_items_v1(document)


def _inspect(document: Any, root: Path) -> tuple[int, list[dict], list[dict], list[dict]]:
    """返回 `(version, items, accepted, rejected_entries)`；目录级不合法 ⇒ `AM.CatalogRejected`。"""
    version, items = _items_for(document)
    accepted, rejected = [], []
    for item in items:
        item_id = item.get("id") if isinstance(item, dict) else None
        try:
            entry = (_v1_item_report(item, root) if version == 1
                     else AM.source_integrity_v2(item, root))
        except AM.ItemRejected as exc:
            rejected.append({"id": str(item_id or "<missing>"), "revision": None,
                             "status": (item.get("status") if isinstance(item, dict) else None),
                             "accepted": False, "reason": exc.reason, "detail": exc.detail})
            continue
        accepted.append({**entry, "accepted": True, "reason": None, "detail": ""})
    return version, items, accepted, rejected


def validate_catalog(catalog: Path, root: Path | None = None) -> dict:
    """只读校验：输出源完整性报告（机器可读）；不写任何文件。"""
    catalog = Path(catalog)
    root = Path(root) if root is not None else derive_root(catalog)
    document, raw, error = _read(catalog)
    version = document.get("version") if isinstance(document, dict) else None
    report = _base_report(catalog, root, raw, version)
    if error is not None:
        report["error"] = error
        return report
    try:
        version, _, accepted, rejected = _inspect(document, root)
    except AM.CatalogRejected as exc:
        report.update({"version": version, "error": exc.reason})
        return report
    report.update({
        "version": version,
        "items": accepted + rejected,
        "counts": {"items": len(accepted) + len(rejected),
                   "accepted": len(accepted), "rejected": len(rejected)},
        "ok": not rejected,
    })
    if version == 2:
        report["notes"].append(
            "v2 目录只做源完整性校验：typed 依赖/节点/环境/契约适用性需要运行上下文；"
            "声明级 applicability 规则（exact_fact 必须声明 typed 依赖、general_advice 必须有"
            "已批准的环境策略或契约范围）由选择路径按 invalid_applicability 拒用，"
            "本工具不重复判定、也不把它当作已通过")
    return report


def _draft_from_v1(item: dict, root: Path) -> tuple[dict, dict]:
    """把一条已通过源完整性检查的 v1 条目转成 v2 **候选草稿** + 迁移说明。

    只迁移能**忠实表达**的条件（`env_id` → typed `env`、`baseline` → typed `baseline`）；
    v1 scope 里的 facts/prompt/schema 指纹在 v2 没有对应依赖类型，必须由人确认，
    因此草稿 `nodes` 留空（不可选择）并逐条列出条件变化。
    """
    scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
    dependencies: list[dict] = []
    if isinstance(scope.get("env_id"), str) and scope["env_id"]:
        dependencies.append({"type": "env", "env_id": scope["env_id"]})
    if scope.get("baseline") is not None:
        dependencies.append({"type": "baseline", "value": scope["baseline"]})
    changes = ["applicability.nodes 为空：必须由人工填写节点白名单（工具不猜）",
               "v1 的 scope 是请求审计指纹，不是 v2 适用条件；等价性未经证明，需人工确认"]
    if scope.get("facts_sha256"):
        changes.append("scope.facts_sha256 无对应 typed 依赖：exact_fact 的当前事实覆盖"
                       "需人工补齐 file_sha256 / targets_sha256 等依赖")
    if scope.get("prompt_sha256"):
        changes.append("scope.prompt_sha256 无对应 typed 依赖：v2 不按提示词指纹匹配")
    if scope.get("schema_sha256"):
        changes.append("scope.schema_sha256 无对应 typed 依赖：v2 不按 Schema 指纹匹配")
    draft = {"id": item["id"], "revision": 1, "status": "draft", "approved_by": None,
             "kind": "exact_fact", "advice": item["advice"],
             "source": {"path": item["source"]["path"], "sha256": item["source"]["sha256"]},
             "applicability": {"nodes": [], "dependencies": dependencies}}
    migration = {"old_id": item["id"], "old_revision": None, "new_id": item["id"],
                 "new_revision": 1, "kind": draft["kind"], "status": draft["status"],
                 "legacy_scope": scope, "condition_changes": changes}
    return draft, migration


def migrate(catalog: Path, out: Path, root: Path | None = None) -> dict:
    """校验并把 v1 目录转成 v2 候选草稿（新文件）；拒绝覆盖输入/写人工目录/覆盖已有件。"""
    catalog = Path(catalog)
    out = Path(out)
    root = Path(root) if root is not None else derive_root(catalog)
    document, raw, error = _read(catalog)
    version = document.get("version") if isinstance(document, dict) else None
    report = _base_report(catalog, root, raw, version)
    report.update({"mode": "migrate", "out": str(out), "target_version": 2,
                   "migration": [], "skipped": []})
    if error is not None:
        report["error"] = error
        return report
    if out.resolve() == catalog.resolve():
        report["error"] = "refuse to overwrite the input catalog"
        return report
    if "adjudication" in out.resolve().parts:
        report["error"] = "refuse to write inside an adjudication directory"
        return report
    if out.exists():
        report["error"] = "refuse to overwrite an existing draft"
        return report
    try:
        version, items, accepted, rejected = _inspect(document, root)
    except AM.CatalogRejected as exc:
        report.update({"version": version, "error": exc.reason})
        return report
    report["version"] = version
    if version != 1:
        report["error"] = "only version 1 catalogs need migration (input is already version 2)"
        return report
    drafts, migrations = [], []
    for entry in accepted:
        item = next(candidate for candidate in items if candidate.get("id") == entry["id"])
        draft, migration = _draft_from_v1(item, root)
        drafts.append(draft)
        migrations.append(migration)
    drafts.sort(key=lambda draft: draft["id"])
    migrations.sort(key=lambda entry: entry["old_id"])
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x", encoding="utf-8") as stream:  # 独占创建：绝不覆盖
            stream.write(json.dumps({"version": 2, "items": drafts}, ensure_ascii=False,
                                    indent=2) + "\n")
    except OSError as exc:
        report["error"] = f"draft write failed: {type(exc).__name__}"
        return report
    report.update({
        "ok": True, "migration": migrations, "skipped": rejected,
        "items": accepted + rejected,
        "counts": {"items": len(accepted) + len(rejected),
                   "accepted": len(accepted), "rejected": len(rejected)},
        "notes": ["草稿条目 status=draft / approved_by=null：人确认并重新批准前不可被选择路径使用",
                  "原人工目录、旧请求与源归档零改动"],
    })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a human-approved experience catalog, or draft a v2 candidate file.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--validate", action="store_true",
                        help="read-only source-integrity report (default when --out is absent)")
    parser.add_argument("--out", type=Path, default=None,
                        help="write a v2 candidate draft to this NEW file (never the input)")
    parser.add_argument("--root", type=Path, default=None,
                        help="data root used to resolve source paths (default: derived from catalog)")
    args = parser.parse_args(argv)
    if args.out is not None:
        report = migrate(args.catalog, args.out, args.root)  # 迁移报告含逐条校验明细
    else:
        report = validate_catalog(args.catalog, args.root)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
