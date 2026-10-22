"""基线准入与身份的**唯一判据**（F01）。

契约见 `doc/spec/LOOP_ORCHESTRATION_SPEC.md` §3.1。这里的纪律：

- **一处判据**：只读列表（`GET /api/baselines`）与运行创建（`RunManager.start`）
  共用本模块，编排层与 API 层都不许再写一份近似规则（红线 8）。
- **只读**：准入不写任何文件（不落临时件；kb 权威经 `paths.kb_module()` 读取，
  该入口禁写字节码，`kb/tools/` 是冻结目录）。
- **失败显式**：`missing`/`errors` 为空才算有效；坏件不抛 500，也不拿空数组冒充成功。
- **身份一致**：`manifest.baseline` 必须等于目录名；parent 链必须可回放（成环/超深即拒）。

七件套的判据来源是 manifest 自身（`kb/schema/manifest.schema.json` 的 6 个 artifact 字段
+ `evidence_index`），本模块不另定义一份清单，只按声明路径核验落盘与指纹。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from host import paths as P

BASELINE_ID_RE = re.compile(r"^v[0-9]+$")
MANIFEST = "manifest.json"
RTL_FILES_MD5 = "rtl_files.md5"
#: parent 链最大回溯深度（防病态深链；正常一轮只增一版）
MAX_PARENT_DEPTH = 32

#: manifest 里需要核验落盘 + 指纹的 artifact：字段名 → 使用的摘要键
_ARTIFACTS: tuple[tuple[str, str | None], ...] = (
    ("rtl_snapshot", "sha256"),
    ("allfiles_manifest", "sha256"),
    ("cases_freeze", "sha256"),
    ("conflicts_snapshot", "sha256"),
    # doc_fingerprint 的 value 是「规范化条目行的 sha256」：落盘件是条目集，重算走
    # kb 权威的 `canon_lines_sha256`（单一口径，不在本层复制第二套算法）。
    ("doc_fingerprint", "value"),
)


class BaselineInvalid(ValueError):
    """基线未通过准入。`details` 带 `missing`/`errors`，供 HTTP 400 直接展示。"""

    def __init__(self, baseline_id: str, details: dict[str, Any]):
        self.baseline_id = baseline_id
        self.details = details
        # 只给身份：缺失件/违规由 `details` 承载，避免 API/UI 同时展示 message 与数组造成重复。
        super().__init__(f"基线 {baseline_id!r} 未通过准入（详情见 missing/errors）")


def normalize(value: Any) -> str:
    """缺省语义固定为 `v0`（规格 §3.1）；不做其它猜测。"""
    text = str(value).strip() if value is not None else ""
    return text or "v0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_errors(doc: Any) -> list[str]:
    """用 kb 权威校验 manifest；权威不可读时 **fail closed**（不当有效）。"""
    try:
        kb = P.kb_module()
        errors = kb.validate(doc, kb.load_schema("manifest"))
        return [f"manifest 不合 schema：{e}" for e in errors]
    except Exception as exc:  # pragma: no cover - 仅在环境损坏时走到
        return [f"无法读取 manifest 权威判据：{type(exc).__name__}: {exc}"]


def _allowed_roots(workspace_root: Path) -> tuple[Path, ...]:
    """artifact 路径的**允许根集合**（唯一来源）：工作区数据根、其父、环境根。

    与旧绝对路径分支保持同一集合，不扩大：`<root>/../<path>` 的兼容写法落在「其父」里，
    因此仍然通过；再往上（`../..`）就越界。
    """
    roots: list[Path] = []
    for base in (workspace_root, workspace_root.parent, Path(P.ENV_ROOT)):
        resolved = base.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _inside_roots(candidate: Path, roots: tuple[Path, ...]) -> bool:
    return any(candidate == base or base in candidate.parents for base in roots)


def _resolved_or_none(candidate: Path) -> Path | None:
    """resolve 失败（断链/循环链接）⇒ `None`：拒绝而不是把异常抛到端点。"""
    try:
        return candidate.resolve()
    except (OSError, RuntimeError):
        return None


def _artifact_path(workspace_root: Path, raw: Any) -> Path | None:
    """解析 manifest 内 artifact 路径（**唯一**的路径边界判据，R2）。

    清单内路径按**环境仓根**书写（如 `kb/baselines/v0/rtl_snapshot.tar`）；拆分数据根后
    也可能出现相对 `<WORKSPACE_ROOT>` 的写法。相对路径解析基准：
    `<root>/<path>` → `<root>/../<path>`（后者兼容按环境根书写的清单）。

    **统一边界判据（R2）**：绝对与相对候选都先 `resolve()`（跟随符号链接），再判是否落在
    允许根集合（见 `_allowed_roots`），**先判边界再读/哈希**。`..` 越界、相对符号链接逃逸、
    断链/循环链接与绝对越界走**同一条**判据 ⇒ `None`（调用方计入 `missing`）。
    返回值是**已 resolve** 的目标：读/哈希只碰判定过的位置。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        candidates: tuple[Path, ...] = (candidate,)
    else:
        candidates = tuple(base / candidate for base in (workspace_root, workspace_root.parent))
    roots = _allowed_roots(workspace_root)
    # 解析顺序保持不变：先取存在的候选；都不存在时回退到第一个「合法根内」候选，
    # 让调用方按 missing 报出声明路径（越界/断链仍是 None）。
    fallback: Path | None = None
    for item in candidates:
        resolved = _resolved_or_none(item)
        if resolved is None or not _inside_roots(resolved, roots):
            continue
        if fallback is None:
            fallback = resolved
        if resolved.exists():
            return resolved
    return fallback


def inspect(
    workspace_root: Path | str,
    baseline_id: str,
    *,
    deep: bool = True,
    _seen: set[str] | None = None,
) -> dict[str, Any]:
    """核验一个基线目录。只读；任何异常都收敛成 `errors`，不向外抛。"""
    root = Path(workspace_root)
    bid = str(baseline_id)
    record: dict[str, Any] = {
        "id": bid,
        "path": str(root / "baselines" / bid),
        "valid": False,
        "missing": [],
        "errors": [],
        "created_at": None,
        "parent": None,
        "cases": None,
        "rtl_snapshot_bytes": None,
    }
    missing: list[str] = record["missing"]
    errors: list[str] = record["errors"]

    if not BASELINE_ID_RE.match(bid):
        errors.append(f"基线号必须形如 v<数字>，实际 {bid!r}")
        return record

    seen = set() if _seen is None else _seen
    if bid in seen:
        errors.append(f"parent 链成环（重复出现 {bid}）")
        return record
    if len(seen) >= MAX_PARENT_DEPTH:
        errors.append(f"parent 链超过 {MAX_PARENT_DEPTH} 层")
        return record
    seen.add(bid)

    baseline_dir = root / "baselines" / bid
    if baseline_dir.is_symlink():
        errors.append("基线目录不得是符号链接")
        return record
    if not baseline_dir.is_dir():
        missing.append(f"baselines/{bid}/")
        return record

    manifest_path = baseline_dir / MANIFEST
    if not manifest_path.is_file():
        missing.append(MANIFEST)
        return record
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        # R3：坏编码只让**该条** invalid；不得用 errors="ignore" 改写清单内容来掩盖，
        # 也不得让解码异常冒到列表端点（旧实现 ⇒ GET /api/baselines 整体 500）。
        errors.append(f"{MANIFEST} 编码不是 UTF-8（解码失败）：{type(exc).__name__}: {exc}")
        return record
    except OSError as exc:
        errors.append(f"{MANIFEST} 无法读取：{type(exc).__name__}: {exc}")
        return record
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(f"{MANIFEST} 无法解析：{type(exc).__name__}: {exc}")
        return record
    if not isinstance(doc, dict):
        # 旧实现直接 doc.get(...) ⇒ list/str 触发 AttributeError，端点 500。
        errors.append(f"{MANIFEST} 必须是 JSON 对象，实际是 {type(doc).__name__}")
        return record

    errors.extend(_schema_errors(doc))
    record.update(
        {
            "created_at": doc.get("created_at"),
            "parent": doc.get("parent"),
            "cases": (doc.get("cases_freeze") or {}).get("entries")
            if isinstance(doc.get("cases_freeze"), dict)
            else None,
        }
    )

    declared = doc.get("baseline")
    if declared != bid:
        errors.append(f"manifest.baseline={declared!r} 与目录名 {bid!r} 不一致")

    for field, digest_key in _ARTIFACTS:
        artifact = doc.get(field)
        if not isinstance(artifact, dict):
            missing.append(f"manifest.{field}")
            continue
        declared_path = artifact.get("path")
        resolved = _artifact_path(root, declared_path)
        if resolved is None or not resolved.is_file():
            missing.append(f"{field}: {declared_path!r}")
            continue
        if field == "rtl_snapshot":
            record["rtl_snapshot_bytes"] = resolved.stat().st_size
        if digest_key and deep:
            expected = artifact.get(digest_key)
            try:
                if field == "doc_fingerprint":
                    kb = P.kb_module()
                    actual = kb.canon_lines_sha256(
                        resolved.read_text(encoding="utf-8").splitlines()
                    )
                else:
                    actual = _sha256(resolved)
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{field} 无法读取：{exc}")
                continue
            except Exception as exc:  # kb 权威不可用等：fail closed，不当有效
                errors.append(f"{field} 无法按 kb 口径重算：{type(exc).__name__}: {exc}")
                continue
            if expected != actual:
                errors.append(f"{field} 指纹不符：manifest={expected} 实际={actual}")

    # `rtl_files.md5` 不在 manifest 的 artifact 字段里，是 rtl_snapshot.manifest_sha256 的落盘件。
    rtl_snapshot = doc.get("rtl_snapshot")
    if isinstance(rtl_snapshot, dict):
        expected = rtl_snapshot.get("manifest_sha256")
        rtl_manifest = baseline_dir / RTL_FILES_MD5
        if not rtl_manifest.is_file():
            missing.append(f"{RTL_FILES_MD5}（rtl_snapshot.manifest_sha256 的落盘件）")
        elif deep and expected:
            try:
                actual = _sha256(rtl_manifest)
            except OSError as exc:
                errors.append(f"{RTL_FILES_MD5} 无法读取：{exc}")
            else:
                if actual != expected:
                    errors.append(f"{RTL_FILES_MD5} 指纹不符：manifest={expected} 实际={actual}")

    evidence_index = doc.get("evidence_index")
    evidence_path = _artifact_path(root, evidence_index)
    if evidence_path is None or not evidence_path.is_file():
        missing.append(f"evidence_index: {evidence_index!r}")

    parent = doc.get("parent")
    if parent is not None:
        if not isinstance(parent, str) or not BASELINE_ID_RE.match(parent):
            errors.append(f"parent 非法：{parent!r}")
        else:
            parent_record = inspect(root, parent, deep=deep, _seen=seen)
            if not parent_record["valid"]:
                details = "；".join([*parent_record["missing"], *parent_record["errors"]])
                errors.append(f"parent {parent} 无效：{details}")

    record["valid"] = not missing and not errors
    return record


def require(workspace_root: Path | str, baseline_id: str) -> dict[str, Any]:
    """准入：不通过即抛 `BaselineInvalid`（`ValueError` 子类 ⇒ HTTP 400）。"""
    record = inspect(workspace_root, baseline_id)
    if not record["valid"]:
        raise BaselineInvalid(str(baseline_id), record)
    return record


def list_baselines(workspace_root: Path | str) -> dict[str, Any]:
    """`<WORKSPACE_ROOT>/baselines/*` 的只读投影（不递归、不跟随符号链接目录）。"""
    root = Path(workspace_root).resolve()
    items: list[dict[str, Any]] = []
    baselines_dir = root / "baselines"
    if baselines_dir.is_dir():
        for child in sorted(baselines_dir.iterdir(), key=lambda path: path.name):
            # 只列**基线号形状**的条目（`.staging-*` 等不是基线）；符号链接不静默跳过，
            # 而是交给 inspect 判成 `valid=false` —— 坏件不得伪装成"不存在"。
            if not BASELINE_ID_RE.match(child.name):
                continue
            if not child.is_dir() and not child.is_symlink():
                continue
            record = inspect(root, child.name)
            item = {key: record[key] for key in (
                "id", "path", "created_at", "parent", "cases",
                "rtl_snapshot_bytes", "valid", "missing", "errors",
            )}
            items.append(item)
    return {"baselines": items, "workspace_root": str(root)}
