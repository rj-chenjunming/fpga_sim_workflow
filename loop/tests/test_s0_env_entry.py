"""S0 §9.9 单输入二选一：**环境项目入口**（`entry="env_folder"`）的 TDD 用例。

契约（`doc/spec/S0_ENVIRONMENT_SPEC.md` §9.9）：
- 只给 `baseline` ⇒ 环境项目入口：选择性复制成副本，**RTL 不替换**；`rtl` 检查 `skipped` + 固定理由；
- 只给 `rtl_source` ⇒ 现行 `rtl_folder`（环境资产取原始环境根）；
- 两者都给 ⇒ `rtl_folder`（兼容保留）；都为空 ⇒ 400；
- 准出判据唯一例外：`entry="env_folder"` 且 `rtl=skipped`，其余五项必须全 `passed`；其它情况 fail-closed；
- `_verify` 在 `rtl_source=null` 时跳过该项比对（不把 null 当漂移）；报告阻断项与准出同判据。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from host import paths as P
from host import s0 as s0_host
from host.s0 import ENV_ENTRY_NO_REPLACE, PreparationFailed, S0Store
from services import api


# ---------------------------------------------------------------- 夹具（最小可派生环境）

_RTL_FILES = {
    "SRC/dut.v": "module dut(\n    input clk,\n    input [7:0] din,\n    output [7:0] dout\n);\nendmodule\n",
    "SRC/imports/a.v": "module a_imp(\n    input clk\n);\nendmodule\n",
    "RTL_COMMON/common.v": "module common(\n    input clk\n);\nendmodule\n",
}
_ENV_FILES = {
    **{f"RTL/{rel}": text for rel, text in _RTL_FILES.items()},
    "TB/top.sv": "module top;\nendmodule\n",
    "PKG/pkg.sv": "package p;\nendpackage\n",
    "TESTLIB/tc_a.sv": "module tc_a;\nendmodule\n",
    "doc/index.md": "# 文档\n",
    "run": "#!/bin/sh\nexit 99\n",
    "all_define.txt": "-define SIM\n",
    "kb/baselines/v0/allfiles.md5": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  RTL/SRC/dut.v\n",
    "kb/index/index.json": "{}\n",
    "kb/conflicts/conflicts.csv": "id,kind\n",
    "kb/adjudication/adjudication.json": "[]\n",
    "loop/loop_entry.py": "# 软件目录：必须整目录排除\n",
    "SIMLIB_RUN/work/a.log": "sim log\n",
}


def _write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.fixture
def env_project(tmp_path: Path) -> Path:
    """一套完整的环境项目（含 kb 数据根）——环境项目入口的唯一输入。"""
    env = tmp_path / "env"
    _write_tree(env, _ENV_FILES)
    return env


@pytest.fixture
def store(tmp_path: Path) -> S0Store:
    root = tmp_path / "state" / "s0"
    root.mkdir(parents=True)
    return S0Store(root, [tmp_path])


@pytest.fixture
def copies_root(tmp_path: Path) -> Path:
    copies = tmp_path / "copies"
    copies.mkdir()
    return copies


def _prepare_env_entry(store: S0Store, env: Path, copies: Path, **extra) -> dict:
    payload = {"baseline": str(env), "now": "2026-10-30T08:00:00+00:00", **extra}
    return store.prepare_from_rtl(payload, default_baseline=env, origin_env_root=env,
                                  target_parent=copies)


# ---------------------------------------------------------------- 模式判定

def test_env_entry_prepare_does_not_replace_rtl(store: S0Store, env_project: Path, copies_root: Path) -> None:
    record = _prepare_env_entry(store, env_project, copies_root)
    work = Path(record["work_env"])

    assert record["entry"] == "env_folder"
    assert record["status"] == "prepared", record.get("error")
    assert record["rtl_source"] is None and record["rtl_prefix"] is None
    assert record["rtl_plan"] is None and record["folder_warning"] is None
    assert record["baseline_version"].startswith("ENV@env+"), record["baseline_version"]
    assert (work / "kb").is_dir(), "副本必须自包含数据根"
    # RTL 不替换 ⇒ 副本 RTL 与源环境逐文件一致（copy 判据覆盖，rtl 项只声明未替换）
    assert s0_host.manifest(work / "RTL") == s0_host.manifest(env_project / "RTL")

    checks = {row["key"]: row for row in record["checks"]}
    assert checks["copy"]["status"] == "passed"
    assert checks["rtl"]["status"] == "skipped"
    assert checks["rtl"]["reason"] == ENV_ENTRY_NO_REPLACE
    assert "未替换" in checks["rtl"]["label"]
    assert checks["non_rtl"]["status"] == "passed"
    assert checks["ports"]["status"] == "passed", record["ports"]
    assert checks["baseline"]["status"] == "passed"
    # 冒烟尚未跑 ⇒ 未准出（fail-closed），且没有伪造成 passed
    assert checks["smoke"]["status"] == "waiting"
    assert record["ready_for_execution"] is False
    assert record["auto"]["phase"] == "ready" or record["auto"]["phase"] == "awaiting_ports"


def test_both_empty_is_rejected(store: S0Store, env_project: Path, copies_root: Path) -> None:
    with pytest.raises(ValueError) as excinfo:
        store.prepare_from_rtl({}, default_baseline=env_project, origin_env_root=env_project,
                               target_parent=copies_root)
    assert "环境项目目录" in str(excinfo.value) and "新版 RTL 文件夹" in str(excinfo.value)


def test_both_given_keeps_rtl_folder_entry(store: S0Store, env_project: Path, copies_root: Path) -> None:
    incoming = env_project.parent / "incoming" / "RTL"
    incoming.mkdir(parents=True)
    _write_tree(incoming, _RTL_FILES)
    record = store.prepare_from_rtl(
        {"rtl_source": str(incoming), "baseline": str(env_project),
         "now": "2026-10-30T08:00:00+00:00"},
        default_baseline=env_project, origin_env_root=env_project, target_parent=copies_root)
    checks = {row["key"]: row["status"] for row in record["checks"]}
    assert record["entry"] == "rtl_folder"
    assert checks["rtl"] == "passed" and record["rtl_prefix"] == "RTL"


# ---------------------------------------------------------------- 准出判据（唯一例外）

def _record(entry: str, **statuses) -> dict:
    base = {"copy": "passed", "rtl": "passed", "non_rtl": "passed",
            "ports": "passed", "smoke": "passed", "baseline": "passed"}
    base.update(statuses)
    return {"status": "prepared", "error": None, "entry": entry,
            "checks": [{"key": key, "status": value} for key, value in base.items()]}


def test_ready_matrix(tmp_path: Path) -> None:
    assert s0_host.s0b.ready_for_execution(_record("env_folder", rtl="skipped"), tmp_path) is True
    assert s0_host.s0b.ready_for_execution(_record("rtl_folder", rtl="skipped"), tmp_path) is False
    assert s0_host.s0b.ready_for_execution(_record("env_folder", rtl="skipped", smoke="waiting"), tmp_path) is False
    assert s0_host.s0b.ready_for_execution(_record("env_folder", rtl="skipped", copy="failed"), tmp_path) is False
    assert s0_host.s0b.ready_for_execution(_record("env_folder"), tmp_path) is True
    missing = _record("env_folder", rtl="skipped")
    missing["checks"] = [row for row in missing["checks"] if row["key"] != "baseline"]
    assert s0_host.s0b.ready_for_execution(missing, tmp_path) is False
    unknown = _record("other", rtl="skipped")
    assert s0_host.s0b.ready_for_execution(unknown, tmp_path) is False


# ---------------------------------------------------------------- 漂移核验与报告

def test_verify_skips_missing_rtl_source(store: S0Store, env_project: Path, copies_root: Path) -> None:
    record = _prepare_env_entry(store, env_project, copies_root)
    fresh = store.get(record["id"])
    assert fresh["verification"]["errors"] == [], fresh["verification"]
    assert fresh["verification"]["drift"] == {}
    assert fresh["entry"] == "env_folder"
    assert fresh["ready_for_execution"] is False     # 冒烟未跑：仍 fail-closed


def test_report_excludes_skipped_from_blockers(store: S0Store, env_project: Path,
                                               copies_root: Path) -> None:
    record = _prepare_env_entry(store, env_project, copies_root)
    text = store.report_path(record["id"]).read_text(encoding="utf-8")
    assert "未替换（环境项目入口）" in text
    blocked = text.split("## 阻断项", 1)[1].split("##", 1)[0]
    assert "- rtl（" not in blocked, blocked
    assert "- smoke（" in blocked, blocked          # 冒烟未跑仍是阻断项


def test_advance_after_smoke_passes_makes_env_entry_ready(
        store: S0Store, env_project: Path, copies_root: Path, monkeypatch) -> None:
    record = _prepare_env_entry(store, env_project, copies_root)
    monkeypatch.setattr(s0_host.s0b, "run_smoke",
                        lambda *args, **kwargs: {"status": "passed", "reason": "", "at": "2026-10-30T08:10:00+00:00",
                                                 "case": "tc_a", "segments": {}})
    advanced = store.advance(record["id"], now="2026-10-30T08:10:00+00:00")
    checks = {row["key"]: row["status"] for row in advanced["checks"]}
    assert checks["smoke"] == "passed"
    assert checks["rtl"] == "skipped"
    assert advanced["ready_for_execution"] is True


# ---------------------------------------------------------------- HTTP 层（真实 store 接线）

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(P, "STATE_DIR", state)
    with TestClient(api.app) as test_client:
        yield test_client


def _wire(monkeypatch, tmp_path: Path, copies: Path) -> None:
    monkeypatch.setattr(api, "COPIES_ROOT", copies)
    monkeypatch.setenv("LOOP_BROWSE_ROOTS", str(tmp_path))


def test_api_only_baseline_returns_env_folder(client: TestClient, tmp_path: Path,
                                              monkeypatch: pytest.MonkeyPatch,
                                              env_project: Path, copies_root: Path) -> None:
    _wire(monkeypatch, tmp_path, copies_root)
    response = client.post("/api/s0/from-rtl", json={"baseline": str(env_project),
                                                     "now": "2026-10-30T08:00:00+00:00"})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["entry"] == "env_folder" and record["rtl_source"] is None
    checks = {row["key"]: row["status"] for row in record["checks"]}
    assert checks["rtl"] == "skipped" and checks["copy"] == "passed"


def test_api_both_empty_is_400(client: TestClient, tmp_path: Path,
                               monkeypatch: pytest.MonkeyPatch, copies_root: Path) -> None:
    _wire(monkeypatch, tmp_path, copies_root)
    response = client.post("/api/s0/from-rtl", json={})
    assert response.status_code == 400, response.text
    assert "环境项目目录" in json.dumps(response.json(), ensure_ascii=False)


def test_api_copies_and_delete_allow_env_folder(client: TestClient, tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch,
                                                env_project: Path, copies_root: Path) -> None:
    _wire(monkeypatch, tmp_path, copies_root)
    record = client.post("/api/s0/from-rtl", json={"baseline": str(env_project),
                                                   "now": "2026-10-30T08:00:00+00:00"}).json()
    listed = client.get("/api/s0/copies").json()["copies"]
    assert [row["id"] for row in listed] == [record["id"]]
    assert listed[0]["rtl_prefix"] is None
    deleted = client.delete("/api/s0/" + record["id"] + "/copy?confirm=true")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True
    assert not Path(record["work_env"]).exists()
