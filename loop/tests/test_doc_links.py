"""F03-c：文档路径检查器的根路由与分类（表驱动，受控临时根）。

规格：[ENV_PLUGIN_SPEC §4.2](../../doc/spec/ENV_PLUGIN_SPEC.md)：按**路径所有权**路由，
本仓/数据根断链必须让退出码为 1；环境资产缺失单独列 `env_missing`（可见、不计失败）；
`KNOWN_MISSING` 打印原因；历史件只计数。

这些用例不跑全库扫描的业务含义，只证明「哪个根、哪一类、退出码怎么算」。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "doc" / "audit" / "check_doc_links.py"


def _load():
    import sys

    name = "check_doc_links_f03c"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclass 的延迟注解解析要求模块已注册在 sys.modules（importlib 手动加载不会自动注册）。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = _load()


# ---------------------------------------------------------------- 分类（所有权）

@pytest.mark.parametrize("token,category", [
    ("kb/tools/gate.py", "tool"),
    ("kb/tools/kb_lib.py::_resolve_env_root", "tool"),
    ("kb/schema/manifest.schema.json", "tool"),
    ("kb/README.md", "tool"),
    ("loop/host/paths.py", "tool"),
    ("loop/web/app.js:1-5", "tool"),
    ("doc/spec/WEB_UI_SPEC.md", "doc"),
    ("doc/audit/check_doc_links.py", "doc"),
    ("workspaces/README.md", "tool"),
    ("README.md", "tool"),
    ("AGENTS.md", "tool"),
    ("environments.json", "tool"),
    ("kb/runs/RUN-1/view.json", "workspace"),
    ("kb/baselines/v0/manifest.json", "workspace"),
    ("kb/index/cases.json", "workspace"),
    ("kb/conflicts/conflicts.json", "workspace"),
    ("kb/adjudication/x.md", "workspace"),
    ("kb/FIXTURE_IDENTITY.md", "workspace"),
    ("RTL/SRC/a.v", "env"),
    ("TB/top.sv", "env"),
    ("PKG/x.sv", "env"),
    ("TESTLIB/tc_a.sv", "env"),
    ("SIMLIB_RUN/log/", "env"),
    ("uvs.setup", "env"),
    ("doc/AGENTS.md", "env"),
    ("doc/_notes/06.md", "env"),
    ("doc/skills/simenv-test/SKILL.md", "env"),
    ("doc/spec/evidence/loop_rehearsal/R.md", "env"),
    ("doc/SIM_ENV_TESTLIB_GUIDE.md", "doc"),
])
def test_classification_is_by_owner_root(token: str, category: str):
    assert C.classify(token) == category


@pytest.mark.parametrize("token", [
    "http://example.com/x", "https://example.com", "#anchor", "/abs/path",
    "src/main.py", "…/x", "a b c", "<TBD>", "${VAR}/x",
])
def test_non_paths_are_not_classified(token: str):
    assert C.classify(token) is None


# ---------------------------------------------------------------- 解析（哪个根）

@pytest.fixture
def roots(tmp_path: Path):
    tool = tmp_path / "tool"
    env = tmp_path / "env"
    workspace = tmp_path / "workspace"
    for base in (tool, env, workspace):
        base.mkdir()
    return C.Roots(tool=tool, env=env, workspace=workspace)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    return path


def test_tool_owned_paths_never_resolve_against_workspace_or_env(roots: C.Roots):
    # 诱饵：同名文件同时存在于数据根与环境根；工具/Schema 必须只认 TOOL_ROOT
    _touch(roots.workspace / "kb/tools/gate.py")
    _touch(roots.env / "kb/tools/gate.py")
    expected = _touch(roots.tool / "kb/tools/gate.py")
    resolved, where = C.resolve("kb/tools/gate.py", roots)
    assert resolved == expected and where == "tool"

    _touch(roots.workspace / "kb/schema/manifest.schema.json")
    schema = _touch(roots.tool / "kb/schema/manifest.schema.json")
    assert C.resolve("kb/schema/manifest.schema.json", roots)[0] == schema


def test_loop_paths_have_no_env_fallback(roots: C.Roots):
    """已迁走的 loop/ 旧路径不得被 ENV_ROOT 同名文件掩盖。"""
    _touch(roots.env / "loop/ACCEPTANCE_V1.md")
    resolved, where = C.resolve("loop/ACCEPTANCE_V1.md", roots)
    assert resolved is None
    assert "env" not in where


def test_workspace_owned_paths_resolve_against_workspace_only(roots: C.Roots):
    expected = _touch(roots.workspace / "runs/RUN-1/view.json")
    _touch(roots.env / "runs/RUN-1/view.json")  # 诱饵
    resolved, where = C.resolve("kb/runs/RUN-1/view.json", roots)
    assert resolved == expected and where == "workspace"


def test_env_assets_resolve_against_env_only(roots: C.Roots):
    expected = _touch(roots.env / "TB/top.sv")
    _touch(roots.tool / "TB/top.sv")  # 诱饵：仓里不应出现环境资产
    resolved, where = C.resolve("TB/top.sv", roots)
    assert resolved == expected and where == "env"


def test_env_doc_falls_back_only_when_tool_missing(roots: C.Roots):
    expected = _touch(roots.env / "doc/SIM_ENV_TESTLIB_GUIDE.md")
    resolved, where = C.resolve("doc/SIM_ENV_TESTLIB_GUIDE.md", roots)
    assert resolved == expected and where == "env-fallback"
    local = _touch(roots.tool / "doc/SIM_ENV_TESTLIB_GUIDE.md")
    resolved, where = C.resolve("doc/SIM_ENV_TESTLIB_GUIDE.md", roots)
    assert resolved == local and where == "tool"


@pytest.mark.parametrize("token", ["kb/tools/gate.py:56-60", "kb/tools/gate.py::main", "kb/tools/gate.py."])
def test_suffixes_are_stripped_before_resolution(roots: C.Roots, token: str):
    expected = _touch(roots.tool / "kb/tools/gate.py")
    assert C.resolve(token, roots)[0] == expected


# ---------------------------------------------------------------- 扫描与退出码

def _write_md(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_repo_broken_link_makes_exit_code_one(roots: C.Roots):
    _write_md(roots.tool, "doc/a.md", "见 `kb/tools/missing.py` 与 `TB/top.sv`\n")
    report = C.scan(roots)
    assert [f.token for f in report.missing] == ["kb/tools/missing.py"]
    assert [f.token for f in report.env_missing] == ["TB/top.sv"]
    assert report.exit_code == 1


def test_env_missing_is_visible_but_does_not_fail(roots: C.Roots):
    _write_md(roots.tool, "doc/a.md", "环境资产 `RTL/SRC/a.v` 本机未挂载\n")
    report = C.scan(roots)
    assert report.missing == []
    assert [f.token for f in report.env_missing] == ["RTL/SRC/a.v"]
    assert report.exit_code == 0


def test_known_missing_is_reported_with_reason(roots: C.Roots):
    _write_md(roots.tool, "doc/a.md", "计划位置 `workspaces/simenv-tcs9620-64ch/`\n")
    report = C.scan(roots)
    assert report.missing == []
    assert [f.token for f in report.known_missing] == ["workspaces/simenv-tcs9620-64ch/"]
    assert report.known_missing[0].reason
    assert report.exit_code == 0


def test_historical_docs_are_counted_not_judged(roots: C.Roots):
    _write_md(roots.tool, "doc/history/OLD.md", "旧路径 `kb/tools/vanished.py`\n")
    _write_md(roots.tool, "doc/evidence/demo/D.md", "旧路径 `loop/vanished.py`\n")
    report = C.scan(roots)
    assert report.missing == []
    assert report.historical == 2
    assert report.exit_code == 0


def test_resolved_and_skipped_are_counted(roots: C.Roots):
    _touch(roots.tool / "loop/host/paths.py")
    _write_md(roots.tool, "doc/a.md",
              "`loop/host/paths.py`、`http://example.com/x`、`a b`、`kb/runs/R1/view.json`\n")
    report = C.scan(roots)
    assert report.checked == 2          # 两个候选路径参与判定
    assert report.skipped >= 2          # URL 与含空格片段跳过
    assert [f.token for f in report.missing] == ["kb/runs/R1/view.json"]
