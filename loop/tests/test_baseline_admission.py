"""F01 基线准入与全链身份（编排规格 §3.1）。

这些用例固定三类可观察行为：

1. 坏件**不冒充有效**：空对象/数组/缺件/身份不符/指纹不符/parent 断链 ⇒ `valid=false`
   且给出原因，端点不抛 500；
2. 准入**零副作用**：real 模式在创建运行目录之前拒绝非法基线；
3. 身份**单一来源**：N2 使用选中的基线，不再硬编码 `v0`。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from host import paths as P
from host.progress import ProgressLog
from services import config_api
from services.contracts import KbSources
from workflows import main_flow
from workflows.chunks import host_steps
from workflows.context import RunCtx


# ---------------------------------------------------------------- 夹具


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_baseline(
    workspace_root: Path,
    baseline_id: str = "v1",
    *,
    parent: str | None = None,
    omit: tuple[str, ...] = (),
    tamper: str | None = None,
    declared_id: str | None = None,
) -> Path:
    """造一个「结构合法」的基线目录；`omit/tamper` 用于制造单点坏件。"""
    baseline_dir = workspace_root / "baselines" / baseline_id
    baseline_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "rtl_snapshot.tar": b"tar-bytes",
        "rtl_files.md5": b"deadbeef  RTL/a.sv\n",
        "allfiles.md5": b"cafebabe  RTL/b.sv\n",
        "doc_entries.txt": b"entry-1\nentry-2\n",
        "cases.md5": b"feedface  TESTLIB/tc.sv\n",
        "conflicts.json": b'{"schema": "kb/conflicts", "version": 1}\n',
    }
    for name, payload in files.items():
        if name in omit:
            continue
        (baseline_dir / name).write_bytes(payload)
    (baseline_dir / "evidence").mkdir(exist_ok=True)
    (baseline_dir / "evidence" / "index.md").write_text("# 证据包指针\n", encoding="utf-8")

    def digest(name: str) -> str:
        path = baseline_dir / name
        return _sha256(path) if path.is_file() else "0" * 64

    def rel(name: str) -> str:
        return f"baselines/{baseline_id}/{name}"

    manifest: dict[str, Any] = {
        "schema": "kb/manifest",
        "version": 1,
        "baseline": declared_id or baseline_id,
        "parent": parent,
        "created_at": "2026-10-21T20:00:00+0800",
        "created_by": "tests/test_baseline_admission.py",
        "package_sha256": "N/A(测试无交付包)",
        "rtl_snapshot": {
            "path": rel("rtl_snapshot.tar"),
            "sha256": digest("rtl_snapshot.tar"),
            "manifest_sha256": digest("rtl_files.md5"),
            "entries": 1,
        },
        "allfiles_manifest": {
            "path": rel("allfiles.md5"),
            "sha256": digest("allfiles.md5"),
            "entries": 1,
        },
        "doc_fingerprint": {
            "path": rel("doc_entries.txt"),
            "algo": "sha256-of-normalized-canonical-lines",
            "value": digest("doc_entries.txt"),
            "entries": 2,
        },
        "cases_freeze": {
            "path": rel("cases.md5"),
            "sha256": digest("cases.md5"),
            "entries": 1,
        },
        "conflicts_snapshot": {
            "path": rel("conflicts.json"),
            "sha256": digest("conflicts.json"),
            "entries": 0,
        },
        "commit": {"repo": "RTL", "ref": "N/A(测试)", "parseable": False},
        "evidence_index": rel("evidence/index.md"),
    }
    (baseline_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if tamper:
        target = baseline_dir / tamper
        target.write_bytes(target.read_bytes() + "  # 篡改\n".encode("utf-8"))
    return baseline_dir


# ---------------------------------------------------------------- 判据：有效/无效


def _entry(workspace_root: Path, baseline_id: str) -> dict[str, Any]:
    """走公开只读入口（`GET /api/baselines` 的实现）取单条，避免只测到新模块。"""
    report = config_api.list_baselines(workspace_root)
    for item in report["baselines"]:
        if item["id"] == baseline_id:
            return item
    raise AssertionError(f"列表里没有 {baseline_id}：{report}")




def test_valid_baseline_passes_admission(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1")
    record = _entry(tmp_path, "v1")
    assert record["valid"] is True
    assert record["missing"] == [] and record["errors"] == []


def test_empty_manifest_object_is_invalid(tmp_path: Path) -> None:
    baseline_dir = make_baseline(tmp_path, "v1")
    (baseline_dir / "manifest.json").write_text("{}", encoding="utf-8")
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("schema" in error for error in record["errors"])


def test_array_manifest_is_invalid_without_exception(tmp_path: Path) -> None:
    baseline_dir = make_baseline(tmp_path, "v1")
    (baseline_dir / "manifest.json").write_text("[]", encoding="utf-8")
    record = _entry(tmp_path, "v1")  # 旧实现这里 AttributeError ⇒ 端点 500
    assert record["valid"] is False
    assert any("JSON 对象" in error for error in record["errors"])


def test_missing_piece_is_reported(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1", omit=("rtl_snapshot.tar",))
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("rtl_snapshot" in item for item in record["missing"])


def test_identity_mismatch_is_invalid(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1", declared_id="v2")
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("不一致" in error for error in record["errors"])


def test_tampered_artifact_fingerprint_is_invalid(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1", tamper="allfiles.md5")
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("指纹不符" in error for error in record["errors"])


def test_parent_chain_missing_is_invalid(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v2", parent="v9")
    record = _entry(tmp_path, "v2")
    assert record["valid"] is False
    assert any("parent v9 无效" in error for error in record["errors"])


def test_parent_chain_valid(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1")
    make_baseline(tmp_path, "v2", parent="v1")
    assert _entry(tmp_path, "v2")["valid"] is True


def test_list_reports_bad_entries_without_raising(tmp_path: Path) -> None:
    make_baseline(tmp_path, "v1")
    bad = make_baseline(tmp_path, "v2")
    (bad / "manifest.json").write_text("{}", encoding="utf-8")
    listed = config_api.list_baselines(tmp_path)
    by_id = {item["id"]: item for item in listed["baselines"]}
    assert by_id["v1"]["valid"] is True
    assert by_id["v2"]["valid"] is False
    assert by_id["v2"]["errors"]


def test_symlink_baseline_is_listed_invalid_not_hidden(tmp_path: Path) -> None:
    real = make_baseline(tmp_path, "v1")
    (tmp_path / "baselines" / "v2").symlink_to(real, target_is_directory=True)
    report = config_api.list_baselines(tmp_path)
    by_id = {item["id"]: item for item in report["baselines"]}
    assert "v2" in by_id, "符号链接基线不得被静默跳过（坏件不能伪装成不存在）"
    assert by_id["v2"]["valid"] is False
    assert any("符号链接" in error for error in by_id["v2"]["errors"])


def test_doc_fingerprint_is_recomputed_with_kb_algorithm(tmp_path: Path) -> None:
    baseline_dir = make_baseline(tmp_path, "v1")
    entries = baseline_dir / "doc_entries.txt"
    entries.write_text(entries.read_text(encoding="utf-8") + "entry-3\n", encoding="utf-8")
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("doc_fingerprint" in error for error in record["errors"])


def test_absolute_artifact_path_outside_roots_is_missing(tmp_path: Path) -> None:
    outside = Path("/etc/hostname")
    if not outside.is_file():
        pytest.skip("本机没有 /etc/hostname（仅用于绝对路径越界用例）")
    baseline_dir = make_baseline(tmp_path, "v1")
    manifest = json.loads((baseline_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["allfiles_manifest"]["path"] = str(outside)
    manifest["allfiles_manifest"]["sha256"] = _sha256(outside)
    (baseline_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    record = _entry(tmp_path, "v1")
    assert record["valid"] is False
    assert any("allfiles_manifest" in item for item in record["missing"])


# ---------------------------------------------------------------- 准入：零副作用


async def test_start_real_rejects_baseline_before_creating_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """real 模式非法基线：400 等价拒绝，且**不建运行目录**。"""
    workspace = tmp_path / "workspace"
    (workspace / "baselines").mkdir(parents=True)
    monkeypatch.setattr(P, "KB_DIR", workspace)

    def must_not_prepare(*args: Any, **kw: Any) -> Any:
        raise AssertionError("准入拒绝必须发生在 prepare_run_dir 之前")

    monkeypatch.setattr(main_flow, "prepare_run_dir", must_not_prepare)
    events_before = sorted(p.name for p in Path(P.EVENTS_DIR).glob("*")) if Path(P.EVENTS_DIR).is_dir() else []

    manager = main_flow.RunManager()
    with pytest.raises(ValueError, match="未通过准入"):
        await manager.start(baseline="v9", mode="real")
    events_after = sorted(p.name for p in Path(P.EVENTS_DIR).glob("*")) if Path(P.EVENTS_DIR).is_dir() else []
    assert events_after == events_before, "拒绝前不得写事件流"


async def test_start_real_accepts_valid_baseline_past_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """正向对照：合法基线**通过**准入（之后才轮到建目录）。"""
    make_baseline(tmp_path, "v1")
    monkeypatch.setattr(P, "KB_DIR", tmp_path)

    prepared: list[tuple[Any, ...]] = []

    class _Admitted(Exception):
        """准入已过：在 prepare_run_dir 处显式打住（不进入真实流程）。"""

    def spy(*args: Any, **kw: Any) -> Any:
        prepared.append(args)
        raise _Admitted

    monkeypatch.setattr(main_flow, "prepare_run_dir", spy)

    manager = main_flow.RunManager()
    with pytest.raises(_Admitted):
        await manager.start(baseline="v1", mode="real")
    assert prepared != []


async def test_n1_fails_closed_without_baseline_identity(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "RUN-20261021-211000"
    run_dir.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / "conflicts").mkdir(parents=True)
    (workspace / "conflicts" / "conflicts.json").write_text("{}", encoding="utf-8")
    ctx = RunCtx(
        run_id="RUN-20261021-211000",
        run_dir=run_dir,
        mode="drill",
        scenario="happy",
        kb=KbSources.from_workspace(workspace),
        progress=ProgressLog(tmp_path / "events", "RUN-20261021-211000"),
        fixture=tmp_path / "fixture",
    )
    data = _FakeData(ctx, state={})
    with pytest.raises(RuntimeError, match="缺基线身份"):
        await host_steps.n1_manifest(data)


async def test_n2_fails_closed_without_baseline_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """缺身份不得回退 v0：宁可失败，也不要按另一版基线做 diff。"""
    run_dir = tmp_path / "runs" / "RUN-20261021-210000"
    run_dir.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / "conflicts").mkdir(parents=True)
    (workspace / "conflicts" / "conflicts.json").write_text("{}", encoding="utf-8")
    ctx = RunCtx(
        run_id="RUN-20261021-210000",
        run_dir=run_dir,
        mode="real",
        scenario="happy",
        kb=KbSources.from_workspace(workspace),
        progress=ProgressLog(tmp_path / "events", "RUN-20261021-210000"),
    )
    monkeypatch.setattr(host_steps, "run_kb_tool", lambda *a, **k: {"rc": 0})
    data = _FakeData(ctx, state={})
    with pytest.raises(RuntimeError, match="缺基线身份"):
        await host_steps.n2_diff(data)


# ---------------------------------------------------------------- 身份：N2 用选中基线


class _FakeData:
    def __init__(self, ctx: RunCtx, *, state: dict[str, Any] | None = None):
        self.input: dict[str, Any] = {}
        self.resources = {"loop_ctx": ctx}
        self.state = dict(state or {})
        self.emitted: list[tuple[str, Any]] = []

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        return self.resources[key]


async def test_n2_uses_selected_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = tmp_path / "runs" / "RUN-20261021-200000"
    run_dir.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / "conflicts").mkdir(parents=True)
    (workspace / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []}),
        encoding="utf-8",
    )
    ctx = RunCtx(
        run_id="RUN-20261021-200000",
        run_dir=run_dir,
        mode="real",
        scenario="happy",
        kb=KbSources.from_workspace(workspace),
        progress=ProgressLog(tmp_path / "events", "RUN-20261021-200000"),
    )

    calls: list[list[str]] = []

    def fake_tool(name: str, args: list[str], **kw: Any) -> dict[str, Any]:
        calls.append([name, *args])
        return {"rc": 3, "stderr_tail": ""}

    monkeypatch.setattr(host_steps, "run_kb_tool", fake_tool)

    data = _FakeData(ctx, state={"run_meta": {"baseline": "v7"}})
    await host_steps.n2_diff(data)

    assert calls, "N2 未调用 kb 工具"
    argv = calls[0]
    assert argv[argv.index("--from-baseline") + 1] == "v7"
    assert data.state["n2_diff"]["diff_count"] == 0
