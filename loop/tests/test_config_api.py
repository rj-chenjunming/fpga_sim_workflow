"""只读配置面 API 的纯函数测试（Task 1）。

覆盖：基线列表、环境校验、目录浏览 allowlist（含符号链接逃逸）。
这些函数**只读**：不创建、不修改任何文件。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import config_api


def _mk_env(root: Path) -> Path:
    env = root / "SimEnv_DEMO"
    for name in ("RTL", "TB", "PKG", "TESTLIB"):
        (env / name).mkdir(parents=True)
    (env / "RTL" / "a.v").write_text("module a; endmodule\n", encoding="utf-8")
    (env / "TESTLIB" / "tc_a.sv").write_text("class tc_a; endclass\n", encoding="utf-8")
    (env / "uvs.setup").write_text("setup\n", encoding="utf-8")
    (env / "SIMLIB_RUN").mkdir()
    return env


def test_list_baselines_reads_manifest(tmp_path: Path) -> None:
    ws = tmp_path / "kb"
    v0 = ws / "baselines" / "v0"
    v0.mkdir(parents=True)
    (v0 / "manifest.json").write_text(json.dumps({
        "baseline": "v0", "created_at": "2026-10-15T12:05:55+0800", "parent": None,
        "cases_freeze": {"entries": 162},
    }), encoding="utf-8")
    out = config_api.list_baselines(ws)
    assert out["baselines"][0]["id"] == "v0"
    assert out["baselines"][0]["valid"] is True
    assert out["baselines"][0]["cases"] == 162


def test_list_baselines_marks_invalid(tmp_path: Path) -> None:
    ws = tmp_path / "kb"
    (ws / "baselines" / "v1").mkdir(parents=True)
    out = config_api.list_baselines(ws)
    assert out["baselines"][0]["valid"] is False
    assert "manifest.json" in out["baselines"][0]["missing"]


def test_check_env_ok(tmp_path: Path) -> None:
    env = _mk_env(tmp_path)
    reg = {"default": "demo", "environments": {"demo": {"path": str(env)}}}
    out = config_api.check_env(env, registry=reg, current_env_root=env)
    assert out["ok"] is True
    assert out["env_id"] == "demo"
    assert out["counts"]["cases"] == 1
    assert out["matches_current_process"] is True


def test_check_env_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        config_api.check_env(tmp_path / "nope", registry={}, current_env_root=tmp_path)


def test_list_dirs_respects_allowlist(tmp_path: Path) -> None:
    parent = tmp_path / "work"
    parent.mkdir()
    env = _mk_env(parent)
    roots = [parent, env]
    out = config_api.list_dirs(parent, allowed_roots=roots, registry={})
    names = [e["name"] for e in out["entries"]]
    assert "SimEnv_DEMO" in names
    with pytest.raises(PermissionError):
        config_api.list_dirs(tmp_path, allowed_roots=roots, registry={})


def test_list_dirs_skips_symlink_escape(tmp_path: Path) -> None:
    parent = tmp_path / "work"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (parent / "link").symlink_to(outside, target_is_directory=True)
    out = config_api.list_dirs(parent, allowed_roots=[parent], registry={})
    assert [e["name"] for e in out["entries"]] == []


def test_allowed_roots_cover_env_parent_and_grandparent(tmp_path: Path) -> None:
    env = _mk_env(tmp_path / "a" / "b")
    reg = {"environments": {"e": {"path": str(env)}}}
    roots = config_api.allowed_roots(reg, tmp_path / "kb")
    assert env.resolve() in roots
    assert env.parent.resolve() in roots
    assert env.parent.parent.resolve() in roots
