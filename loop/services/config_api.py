"""只读配置面：基线列表 / 环境校验 / 目录浏览。

设计约束（`doc/spec/WEB_UI_SPEC.md` §6、§8）：
- **只读**：本模块不创建、不修改任何文件；目录不存在就报错，不兜底。
- 目录浏览必须走 allowlist（注册环境 path / 父 / 祖父、数据根 `baselines/`、
  `loop/SETTINGS.yaml` 的 `loop.ui.browse_roots`、`$LOOP_BROWSE_ROOTS`），
  且用 `resolve()` 后的真实路径判越界（防符号链接逃逸）。
- 错误用异常表达：`ValueError`（路径非法/不存在）→ API 400；
  `PermissionError`（越界）→ API 403。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

FROZEN_DEFAULT: tuple[str, ...] = ("RTL", "TB", "PKG", "TESTLIB")
WORKSPACE_PARTS: tuple[str, ...] = ("index", "conflicts", "baselines", "runs")
MARKER_FILES: tuple[str, ...] = ("uvs.setup", "manifest.json")
MARKER_DIRS: tuple[str, ...] = ("RTL", "TB", "PKG", "TESTLIB")


# ---------------------------------------------------------------- 基础工具


def load_registry(path: Path | str) -> dict[str, Any]:
    """读环境插件注册表；坏文件返回空 dict（调用方按 fail closed 处理）。"""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _is_under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _find_env_entry(registry: dict[str, Any], target: Path) -> tuple[str | None, dict[str, Any] | None]:
    for env_id, entry in (registry.get("environments") or {}).items():
        raw = (entry or {}).get("path")
        if not raw:
            continue
        try:
            if _resolve(raw) == target:
                return str(env_id), entry
        except OSError:
            continue
    return None, None


# ---------------------------------------------------------------- 基线


def list_baselines(workspace_root: Path | str) -> dict[str, Any]:
    """列出 `<WORKSPACE_ROOT>/baselines/*`（只读）。

    判据只有一处：`host/baseline.py`（编排规格 §3.1）。本层不重复实现完整性校验——
    历史缺陷正来自这里「只要 manifest 能解析就 valid=true」。
    """
    from host import baseline as baseline_host

    return baseline_host.list_baselines(workspace_root)


# ---------------------------------------------------------------- 环境校验


def check_env(
    path: Path | str,
    *,
    registry: dict[str, Any],
    current_env_root: Path | str,
) -> dict[str, Any]:
    """只读校验一个候选环境仓根（必须是目录）。"""
    target = _resolve(path)
    if not target.is_dir():
        raise ValueError(f"目录不存在或不是目录：{path}")

    env_id, entry = _find_env_entry(registry, target)
    entry = entry or {}
    provides = entry.get("provides") or {}
    frozen = tuple(entry.get("frozen") or FROZEN_DEFAULT)

    plugin_missing = [name for name in frozen if not (target / name).is_dir()]
    sim_setup = provides.get("sim_setup", "uvs.setup")
    if not (target / sim_setup).is_file():
        plugin_missing.append(sim_setup)

    warnings: list[str] = []
    run_local = provides.get("run_local")
    if run_local and not (target / run_local).is_file():
        warnings.append(f"缺少 {run_local}（real 模式不可用）")
    sim_orig = provides.get("sim_setup_orig")
    if sim_orig and not (target / sim_orig).is_file():
        warnings.append(f"缺少 {sim_orig}（中止自愈不可用）")
    if entry and not entry.get("workspace"):
        warnings.append("注册表未登记 workspace（数据根）")

    workspace_missing: list[str] = []
    workspace_root = None
    if entry.get("workspace"):
        workspace_root = _resolve(entry["workspace"])
        workspace_missing = [name for name in WORKSPACE_PARTS if not (workspace_root / name).is_dir()]

    rtl = target / "RTL"
    rtl_files = sum(1 for p in rtl.rglob("*") if p.is_file()) if rtl.is_dir() else 0
    testlib = target / "TESTLIB"
    cases = sum(1 for p in testlib.glob("*.sv") if p.is_file()) if testlib.is_dir() else 0

    sim_workdir = provides.get("sim_workdir", "SIMLIB_RUN")
    workdir = target / sim_workdir
    writable = {
        "frozen": all(os.access(target / name, os.W_OK) for name in frozen if (target / name).exists()),
        "sim_workdir": (
            (workdir.is_dir() and os.access(workdir, os.W_OK))
            or (not workdir.exists() and os.access(target, os.W_OK))
        ),
    }

    return {
        "path": str(target),
        "ok": not plugin_missing,
        "registered": env_id is not None,
        "env_id": env_id,
        "plugin_missing": plugin_missing,
        "workspace_missing": workspace_missing,
        "workspace_root": str(workspace_root) if workspace_root else None,
        "counts": {"rtl_files": rtl_files, "cases": cases},
        "writable": writable,
        "warnings": warnings,
        "matches_current_process": target == _resolve(current_env_root),
    }


# ---------------------------------------------------------------- 目录浏览


def _settings_browse_roots(settings_path: Path) -> list[Path]:
    """读 `loop.SETTINGS.yaml` 的 `loop.ui.browse_roots`（可选；失败即空）。"""
    try:
        import yaml  # 编排层 venv 已有；kb/tools 才限制 stdlib

        doc = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
        values = ((doc.get("loop") or {}).get("ui") or {}).get("browse_roots") or []
        return [_resolve(v) for v in values if isinstance(v, str) and v.strip()]
    except Exception:
        return []


def allowed_roots(
    registry: dict[str, Any],
    workspace_root: Path | str,
    *,
    settings_path: Path | str | None = None,
    extra: Iterable[Path | str] | None = None,
) -> list[Path]:
    """目录浏览 allowlist（全部 resolve 后去重）。"""
    roots: set[Path] = set()
    for entry in (registry.get("environments") or {}).values():
        raw = (entry or {}).get("path")
        if not raw:
            continue
        try:
            env = _resolve(raw)
        except OSError:
            continue
        roots.update({env, env.parent, env.parent.parent})
    roots.add(_resolve(Path(workspace_root) / "baselines"))
    if settings_path:
        roots.update(_settings_browse_roots(Path(settings_path)))
    for chunk in os.environ.get("LOOP_BROWSE_ROOTS", "").split(os.pathsep):
        if chunk.strip():
            roots.add(_resolve(chunk))
    for item in extra or []:
        roots.add(_resolve(item))
    return sorted(roots, key=lambda p: str(p))


def list_dirs(
    path: Path | str,
    *,
    allowed_roots: Iterable[Path | str],
    registry: dict[str, Any],
) -> dict[str, Any]:
    """列出一层目录（只目录；不读文件内容；resolve 后校验越界）。"""
    roots = [_resolve(r) for r in allowed_roots]
    target = _resolve(path)
    if not any(_is_under(target, root) for root in roots):
        raise PermissionError(f"路径不在允许的浏览根内：{path}")
    if not target.is_dir():
        raise ValueError(f"目录不存在或不是目录：{path}")

    entries: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        try:
            real = child.resolve()
        except OSError:
            continue
        if not any(_is_under(real, root) for root in roots):
            continue
        if not real.is_dir():
            continue
        markers = [name for name in MARKER_FILES if (real / name).is_file()]
        markers += [f"{name}/" for name in MARKER_DIRS if (real / name).is_dir()]
        env_id, _ = _find_env_entry(registry, real)
        entries.append(
            {
                "name": child.name,
                "is_env": env_id is not None,
                "env_id": env_id,
                "markers": markers,
            }
        )

    parent = None
    if any(_is_under(target.parent, root) for root in roots):
        parent = str(target.parent)
    return {
        "path": str(target),
        "parent": parent,
        "roots": [str(r) for r in roots],
        "entries": entries,
    }
