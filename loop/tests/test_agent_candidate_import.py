"""S6 候选导入（DS-06）拒绝矩阵 + Host 独占应用（C1）。

失败用例编号（R1–R19，见 task-7 与 S5/S6 计划 §4）：

  R1  执行未停止（running/prepared/starting）           ⇒ execution_not_stopped，不重发
  R2  停止未知（execution_unknown/缺省/unknown）        ⇒ execution_unknown，不重发
  R3  候选根缺失/不是目录                                ⇒ candidate_root_missing
  R4  候选根是链接 / 不在 attempt 根内 / 非绝对路径      ⇒ candidate_root_unsafe
  R5  清单缺失或形状坏                                   ⇒ manifest_missing / manifest_malformed
  R6  绝对路径                                          ⇒ path_absolute
  R7  `..` 穿越                                          ⇒ path_escape
  R8  文件或父目录是符号链接                             ⇒ path_symlink
  R9  非普通文件（目录/fifo）                            ⇒ not_regular_file
  R10 后缀不在白名单                                     ⇒ suffix_not_allowed
  R11 超单文件大小上限                                   ⇒ file_too_large（不截断）
  R12 超总量上限                                         ⇒ total_too_large
  R13 校验后换件（复算 md5 ≠ 清单）                      ⇒ hash_mismatch
  R14 额外文件                                           ⇒ extra_file
  R15 清单声明但缺件                                     ⇒ candidate_missing
  R16 源漂移（封存基线 ≠ 现算基线）                      ⇒ source_drift
  R17 目标覆盖不一致                                     ⇒ target_coverage
  R18 合法候选：结构化输出 + 零写入                      ⇒ ok
  R19 大小与清单声明不符                                 ⇒ size_mismatch

纪律：全部落 `tmp_path`；**不写 ENV_ROOT / WORKSPACE_ROOT**；不跑真仿真、不调模型。
n6_apply 侧的"候选内容 == apply(基线, edits)"（EDITS_MISMATCH）是**关键防线**：
候选不能绕过 `apply_edits` 的 `old` 唯一命中判据。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from host import agent_candidate_import as CI
from host import agent_memory as AM
from host.agent_backends import dsh_assets as A
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.chunks import host_steps, model_steps as M
from workflows.context import RunCtx

RUN_ID = "RUN-20261028-233000"


# ================================================================ 夹具 / 工具


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def _write_candidate(cand: Path, rel: str, text: str) -> dict[str, Any]:
    """写一件候选并返回其清单条目 `{md5, size}`（清单形状由 G1 冻结）。"""
    path = cand / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    data = path.read_bytes()
    return {"md5": _md5(data), "size": len(data)}


def _snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """目录树快照（相对路径 → 大小/mtime/内容 md5）：用于断言"零写入"。"""
    out: dict[str, tuple[int, int, str]] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            out[str(path.relative_to(root))] = (-1, -1, os.readlink(path))
        elif path.is_file():
            out[str(path.relative_to(root))] = (
                path.stat().st_size, path.stat().st_mtime_ns, _md5(path.read_bytes()))
    return out


@pytest.fixture
def attempt(tmp_path: Path) -> Path:
    """一个 attempt 根：目录形状由 `AttemptLayout` 决定（候选可能在根下或 `work/` 下）。"""
    from host.agent_backends import dsh_assets as A

    root = tmp_path / "attempt"
    layout = A.AttemptLayout.under(root)
    layout.prepare()
    (layout.candidate / "TESTLIB").mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def cand(attempt: Path) -> Path:
    """候选目录：**只从布局字段取**（不在测试里硬编码 `attempt/candidate`）。"""
    return host_steps.candidate_dir_for_attempt(attempt)


def _import(cand: Path | str | None, attempt: Path | str | None, *,
            manifest: Any, state: Any = "stopped",
            baseline: dict[str, str] | None = None,
            baseline_current: dict[str, str] | None = None,
            expected_cases: set[str] | None = None,
            policy: CI.CandidatePolicy | None = None) -> CI.ImportResult:
    return CI.import_candidates(
        cand, manifest=manifest, execution_state=state, attempt_root=attempt,
        baseline=baseline, baseline_current=baseline_current,
        expected_cases=expected_cases, policy=policy)


def _assert_rejected(result: CI.ImportResult, reason: CI.RejectReason) -> None:
    """拒绝必须可判、可读，且**不留半件**（零候选）。"""
    assert result.ok is False, result.record()
    assert result.reason is reason, result.record()
    assert result.reason_value == reason.value
    assert result.candidates == (), "拒绝时不得返回任何候选（不留半件）"
    assert result.detail, "拒绝必须带可判 detail"


# ================================================================ 常量/白名单


def test_whitelist_and_limits_are_explicit_constants() -> None:
    """白名单/大小上限是**显式常量**（不是"默认允许其它"）。"""
    assert CI.ALLOWED_SUFFIXES == frozenset({".sv", ".svh", ".v", ".vh", ".md", ".txt"})
    assert CI.MAX_CANDIDATE_BYTES > 0
    assert CI.MAX_CANDIDATE_TOTAL_BYTES >= CI.MAX_CANDIDATE_BYTES


# ================================================================ R1 / R2：停止确认


@pytest.mark.parametrize("state", ["prepared", "starting", "running"])
def test_r1_rejects_when_execution_not_stopped(cand: Path, attempt: Path, state: str) -> None:
    """R1：未停止 ⇒ 拒绝导入；本次结果不得自动重发。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    result = _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}, state=state)
    _assert_rejected(result, CI.RejectReason.EXECUTION_NOT_STOPPED)
    assert result.resend_allowed is False
    assert result.execution_state == state


@pytest.mark.parametrize("state", ["execution_unknown", "unknown", None])
def test_r2_rejects_when_stop_unknown_and_never_resends(
        cand: Path, attempt: Path, state: Any) -> None:
    """R2：停止未知 ⇒ 不导入、不重发（DS-05）。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    result = _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}, state=state)
    _assert_rejected(result, CI.RejectReason.EXECUTION_UNKNOWN)
    assert result.resend_allowed is False


# ================================================================ R3 / R4：候选根


def test_r3_rejects_missing_candidate_root(tmp_path: Path, attempt: Path) -> None:
    result = _import(tmp_path / "nope", attempt, manifest={"TESTLIB/tc_demo.sv": {}})
    _assert_rejected(result, CI.RejectReason.CANDIDATE_ROOT_MISSING)


def test_r4_rejects_candidate_root_symlink_and_escape(cand: Path, attempt: Path,
                                                      tmp_path: Path) -> None:
    """R4：候选根是链接 / 不在 attempt 根内 / 非绝对路径 ⇒ 拒。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    manifest = {"TESTLIB/tc_demo.sv": entry}

    link = tmp_path / "cand-link"
    link.symlink_to(cand, target_is_directory=True)
    _assert_rejected(_import(link, attempt, manifest=manifest),
                     CI.RejectReason.CANDIDATE_ROOT_UNSAFE)

    outside = tmp_path / "outside-candidate"
    (outside / "TESTLIB").mkdir(parents=True)
    (outside / "TESTLIB" / "tc_demo.sv").write_text("module tc_demo;\nendmodule\n", encoding="utf-8")
    _assert_rejected(_import(outside, attempt, manifest=manifest),
                     CI.RejectReason.CANDIDATE_ROOT_UNSAFE)

    # 相对路径：无法证明在 attempt 内 ⇒ 失败安全
    rel = os.path.relpath(cand, Path.cwd())
    _assert_rejected(_import(rel, attempt, manifest=manifest),
                     CI.RejectReason.CANDIDATE_ROOT_UNSAFE)

    # 没给 attempt 根 ⇒ 同样不能证明 ⇒ 拒（不降级）
    _assert_rejected(_import(cand, None, manifest=manifest),
                     CI.RejectReason.CANDIDATE_ROOT_UNSAFE)


# ================================================================ R5：清单


def test_r5_rejects_missing_or_malformed_manifest(cand: Path, attempt: Path) -> None:
    """R5：没有清单 ⇒ 拒（无法判换件）；形状坏 ⇒ 拒。"""
    _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    _assert_rejected(_import(cand, attempt, manifest=None), CI.RejectReason.MANIFEST_MISSING)
    _assert_rejected(_import(cand, attempt, manifest={}), CI.RejectReason.MANIFEST_MISSING)
    _assert_rejected(_import(cand, attempt, manifest=["TESTLIB/tc_demo.sv"]),
                     CI.RejectReason.MANIFEST_MALFORMED)
    # 缺 md5 ⇒ 无法判换件
    _assert_rejected(_import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": {"size": 28}}),
                     CI.RejectReason.MANIFEST_MALFORMED)
    # md5 不是 32 位十六进制
    _assert_rejected(
        _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": {"md5": "deadbeef", "size": 28}}),
        CI.RejectReason.MANIFEST_MALFORMED)
    # 缺 size
    _assert_rejected(
        _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": {"md5": "0" * 32}}),
        CI.RejectReason.MANIFEST_MALFORMED)


# ================================================================ R6 / R7：路径


def test_r6_rejects_absolute_path(cand: Path, attempt: Path, tmp_path: Path) -> None:
    target = tmp_path / "etc-x.sv"
    target.write_text("module x;\nendmodule\n", encoding="utf-8")
    data = target.read_bytes()
    manifest = {str(target): {"md5": _md5(data), "size": len(data)}}
    _assert_rejected(_import(cand, attempt, manifest=manifest), CI.RejectReason.PATH_ABSOLUTE)


@pytest.mark.parametrize("rel", ["../escape.sv", "TESTLIB/../../escape.sv", "./../x.sv"])
def test_r7_rejects_path_traversal(cand: Path, attempt: Path, rel: str) -> None:
    # 在候选根外**真的**放一个文件，证明 `..` 不是纸面拒绝
    outside = attempt / "escape.sv"
    outside.write_text("module escape;\nendmodule\n", encoding="utf-8")
    data = outside.read_bytes()
    manifest = {rel: {"md5": _md5(data), "size": len(data)}}
    _assert_rejected(_import(cand, attempt, manifest=manifest), CI.RejectReason.PATH_ESCAPE)


# ================================================================ R8：符号链接


def test_r8_rejects_file_and_parent_symlink(cand: Path, attempt: Path, tmp_path: Path) -> None:
    """R8：文件本身或任一父段是链接 ⇒ 拒（链接逃逸）。"""
    outside = tmp_path / "outside"
    outside.mkdir()
    real = outside / "tc_demo.sv"
    real.write_text("module tc_demo;\nendmodule\n", encoding="utf-8")
    data = real.read_bytes()
    manifest = {"TESTLIB/tc_demo.sv": {"md5": _md5(data), "size": len(data)}}

    (cand / "TESTLIB" / "tc_demo.sv").symlink_to(real)
    _assert_rejected(_import(cand, attempt, manifest=manifest), CI.RejectReason.PATH_SYMLINK)

    (cand / "TESTLIB" / "tc_demo.sv").unlink()
    (cand / "TESTLIB").rmdir()
    (cand / "TESTLIB").symlink_to(outside, target_is_directory=True)
    _assert_rejected(_import(cand, attempt, manifest=manifest), CI.RejectReason.PATH_SYMLINK)


# ================================================================ R9：非普通文件


def test_r9_rejects_directory_and_fifo(cand: Path, attempt: Path) -> None:
    """R9：目录/特殊文件不是候选件。"""
    (cand / "TESTLIB" / "tc_demo.sv").mkdir()
    manifest = {"TESTLIB/tc_demo.sv": {"md5": "0" * 32, "size": 0}}
    _assert_rejected(_import(cand, attempt, manifest=manifest),
                     CI.RejectReason.NOT_REGULAR_FILE)

    (cand / "TESTLIB" / "tc_demo.sv").rmdir()
    fifo = cand / "TESTLIB" / "tc_demo.sv"
    os.mkfifo(fifo)
    try:
        _assert_rejected(_import(cand, attempt, manifest=manifest),
                         CI.RejectReason.NOT_REGULAR_FILE)
    finally:
        fifo.unlink()


# ================================================================ R10：后缀


@pytest.mark.parametrize("rel", ["TESTLIB/tc_demo.sh", "TESTLIB/tc_demo.py", "TESTLIB/tc_demo"])
def test_r10_rejects_suffix_outside_whitelist(cand: Path, attempt: Path, rel: str) -> None:
    entry = _write_candidate(cand, rel, "echo hi\n")
    _assert_rejected(_import(cand, attempt, manifest={rel: entry}),
                     CI.RejectReason.SUFFIX_NOT_ALLOWED)


# ================================================================ R11 / R12 / R19：大小


def test_r11_rejects_oversize_file_without_truncating(cand: Path, attempt: Path) -> None:
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "x" * 128)
    policy = CI.CandidatePolicy(max_file_bytes=64)
    _assert_rejected(_import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}, policy=policy),
                     CI.RejectReason.FILE_TOO_LARGE)
    # 不截断：候选件内容原样（本模块零写入）
    assert (cand / "TESTLIB/tc_demo.sv").read_text(encoding="utf-8") == "x" * 128


def test_r12_rejects_total_over_limit(cand: Path, attempt: Path) -> None:
    first = _write_candidate(cand, "TESTLIB/tc_a.sv", "a" * 40)
    second = _write_candidate(cand, "TESTLIB/tc_b.sv", "b" * 40)
    policy = CI.CandidatePolicy(max_file_bytes=64, max_total_bytes=70)
    _assert_rejected(
        _import(cand, attempt, manifest={"TESTLIB/tc_a.sv": first, "TESTLIB/tc_b.sv": second},
                policy=policy),
        CI.RejectReason.TOTAL_TOO_LARGE)


def test_r19_rejects_declared_size_mismatch(cand: Path, attempt: Path) -> None:
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    entry = {**entry, "size": entry["size"] + 1}
    _assert_rejected(_import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}),
                     CI.RejectReason.SIZE_MISMATCH)


# ================================================================ R13 / R14 / R15


def test_r13_rejects_hash_mismatch_after_validation(cand: Path, attempt: Path) -> None:
    """R13：校验后换件 —— 导入前复算 md5 与清单声明不符 ⇒ 拒。

    刻意做**同长度**换件（只改内容不改大小），否则会先被 R19/SIZE_MISMATCH 拦下，
    这条用例就测不到"哈希复算"这一步。
    """
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    (cand / "TESTLIB" / "tc_demo.sv").write_text("module tc_demo;\nendmodulX\n",
                                                 encoding="utf-8")
    _assert_rejected(_import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}),
                     CI.RejectReason.HASH_MISMATCH)


def test_r14_rejects_extra_file(cand: Path, attempt: Path) -> None:
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    _write_candidate(cand, "TESTLIB/unlisted.sv", "module unlisted;\nendmodule\n")
    _assert_rejected(_import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry}),
                     CI.RejectReason.EXTRA_FILE)


def test_r15_rejects_declared_but_missing_file(cand: Path, attempt: Path) -> None:
    manifest = {"TESTLIB/tc_demo.sv": {"md5": "0" * 32, "size": 28}}
    _assert_rejected(_import(cand, attempt, manifest=manifest),
                     CI.RejectReason.CANDIDATE_MISSING)


# ================================================================ R16 / R17


def test_r16_rejects_source_drift(cand: Path, attempt: Path) -> None:
    """R16：封存基线 md5 ≠ 现算基线 md5 ⇒ 源漂移。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    manifest = {"TESTLIB/tc_demo.sv": entry}
    _assert_rejected(
        _import(cand, attempt, manifest=manifest,
                baseline={"TESTLIB/tc_demo.sv": "a" * 32},
                baseline_current={"TESTLIB/tc_demo.sv": "b" * 32}),
        CI.RejectReason.SOURCE_DRIFT)
    # 封存基线缺项 ⇒ 无法证明无漂移 ⇒ 同样拒
    _assert_rejected(
        _import(cand, attempt, manifest=manifest,
                baseline={}, baseline_current={"TESTLIB/tc_demo.sv": "b" * 32}),
        CI.RejectReason.SOURCE_DRIFT)


def test_r17_rejects_target_coverage_mismatch(cand: Path, attempt: Path) -> None:
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    manifest = {"TESTLIB/tc_demo.sv": entry}
    _assert_rejected(
        _import(cand, attempt, manifest=manifest, expected_cases={"tc_demo", "tc_other"}),
        CI.RejectReason.TARGET_COVERAGE)
    # 多出一件非目标用例
    extra = _write_candidate(cand, "TESTLIB/tc_extra.sv", "module tc_extra;\nendmodule\n")
    _assert_rejected(
        _import(cand, attempt, manifest={**manifest, "TESTLIB/tc_extra.sv": extra},
                expected_cases={"tc_demo"}),
        CI.RejectReason.TARGET_COVERAGE)


# ================================================================ R18：合法路径


def test_r18_accepts_valid_candidate_and_writes_nothing(cand: Path, attempt: Path) -> None:
    """R18：合法候选 ⇒ 结构化输出（内容/哈希/基线），且**零写入**。"""
    text = "module tc_demo;\n  check(0x0000+0x04, 0xdead_c0de);\nendmodule\n"
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", text)
    baseline = {"TESTLIB/tc_demo.sv": "c" * 32}
    before = _snapshot(attempt)

    result = _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry},
                     baseline=baseline, baseline_current={"TESTLIB/tc_demo.sv": "c" * 32},
                     expected_cases={"tc_demo"})

    assert result.ok is True, result.record()
    assert result.reason is None
    assert result.drift_checked is True
    assert result.resend_allowed is True
    assert result.total_bytes == entry["size"]
    (imported,) = result.candidates
    assert imported.case == "tc_demo"
    assert imported.path == "TESTLIB/tc_demo.sv"
    assert imported.text == text
    assert imported.md5 == entry["md5"]
    assert imported.baseline_md5 == "c" * 32
    assert list(result.by_case()) == ["tc_demo"]
    # 结构化投影可直接进 payload/证据
    record = result.record()
    assert record["ok"] is True and record["files"][0]["md5"] == entry["md5"]
    assert "text" not in record, "投影不带正文（避免把候选内容塞进状态）"
    # attempt 根之外/之内都零写入（快照逐项相同）
    assert _snapshot(attempt) == before


def test_r18_without_baseline_reports_drift_not_checked(cand: Path, attempt: Path) -> None:
    """未给封存基线 ⇒ 导入可过，但如实标 `drift_checked=False`（不冒充已核对）。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    result = _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry})
    assert result.ok is True and result.drift_checked is False


def test_manifest_paths_are_normalized_before_extra_file_scan(cand: Path, attempt: Path) -> None:
    """清单键的 `a//b`、`a/./b` 等价于 `a/b`：否则合法候选会被 R14 误判成"额外文件"。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    result = _import(cand, attempt, manifest={"TESTLIB//./tc_demo.sv": entry},
                     expected_cases={"tc_demo"})
    assert result.ok is True, result.record()
    assert result.candidates[0].path == "TESTLIB/tc_demo.sv"
    # 两个原始键规范化后撞车 ⇒ 清单坏（不静默取其一）
    _assert_rejected(
        _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry,
                                         "TESTLIB//tc_demo.sv": entry}),
        CI.RejectReason.MANIFEST_MALFORMED)


def test_baseline_keys_are_normalized_for_drift_check(cand: Path, attempt: Path) -> None:
    """封存基线键也要规范化：否则会把"同一路径的两种写法"误判成源漂移。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    result = _import(cand, attempt, manifest={"TESTLIB/tc_demo.sv": entry},
                     baseline={"TESTLIB//tc_demo.sv": "d" * 32},
                     baseline_current={"TESTLIB/tc_demo.sv": "d" * 32})
    assert result.ok is True, result.record()
    assert result.drift_checked is True


# ================================================================ n6_apply 接线


@pytest.fixture
def env_repo(tmp_path: Path) -> Path:
    """假 ENV_ROOT（只含 TESTLIB 用例源文件；源件绝不被改）。"""
    root = tmp_path / "env"
    (root / "TESTLIB").mkdir(parents=True)
    (root / "TESTLIB" / "tc_demo.sv").write_text(
        "module tc_demo;\n"
        "  // line 2\n"
        "  check(0x0000+0x04, 0x2023_0804);\n"
        "  check(0x0000+0x08, 0xdead_beef);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return root


@pytest.fixture
def ctx(tmp_path: Path, env_repo: Path) -> RunCtx:
    run_dir = tmp_path / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    kb_root = tmp_path / "kb"
    (kb_root / "conflicts").mkdir(parents=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        json.dumps({"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []},
                   ensure_ascii=False), encoding="utf-8")
    return RunCtx(run_id=RUN_ID, run_dir=run_dir, mode="real", scenario="happy",
                  kb=KbSources.from_workspace(kb_root),
                  progress=ProgressLog(tmp_path / "events", RUN_ID))


class FakeData:
    """triggerflow state 替身（与真实 `data` 的 get_state/async_set_state 同形）。"""

    def __init__(self, *, resources: dict[str, Any], state: dict[str, Any]):
        self.resources = dict(resources)
        self.resources.setdefault("loop_ctx", None)
        self.state = dict(state)
        self.emitted: list[tuple[str, Any]] = []

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        return self.resources[key]

    async def async_emit(self, event: str, payload: Any) -> None:
        self.emitted.append((event, payload))


#: n6_apply 施加的 edits（old 在源文件里唯一命中）
_EDITS = [{"line": 4, "old": "0xdead_beef", "new": "0xdead_c0de", "basis": "0x0000#0x0008"}]
#: 施加后的期望全文（候选人写的候选件必须与它逐字一致）
_APPLIED_TEXT = ("module tc_demo;\n"
                 "  // line 2\n"
                 "  check(0x0000+0x04, 0x2023_0804);\n"
                 "  check(0x0000+0x08, 0xdead_c0de);\n"
                 "endmodule\n")


def _targets() -> dict[str, Any]:
    return {"targets": [{"case": "tc_demo", "file": "TESTLIB/tc_demo.sv"}]}


def _author(*, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    author: dict[str, Any] = {
        "mode": "live",
        "data": {"revisions": [{"case": "tc_demo", "edits": _EDITS, "rationale": "文档 reset 值更新"}]},
        "validation": {"ok": True, "problems": [], "accepted": {}},
    }
    if candidate is not None:
        author.update(candidate)
    return author


def _candidate_block(cand: Path, env_repo: Path, *, text: str = _APPLIED_TEXT,
                     state: Any = "stopped") -> dict[str, Any]:
    """构造 `n6_author` 里的四键候选块（G1 冻结键名）。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", text)
    source_md5 = hashlib.md5((env_repo / "TESTLIB" / "tc_demo.sv").read_bytes()).hexdigest()
    return {"candidate_root": str(cand),
            "candidate_manifest": {"TESTLIB/tc_demo.sv": entry},
            "baseline": {"TESTLIB/tc_demo.sv": source_md5},
            "execution_state": state}


def _data(ctx: RunCtx, env_repo: Path, author: dict[str, Any]) -> FakeData:
    return FakeData(resources={"repo_root": env_repo, "loop_ctx": ctx},
                    state={"n6_targets": _targets(), "n6_author": author})


async def _run_n6(ctx: RunCtx, env_repo: Path, author: dict[str, Any]) -> dict[str, Any]:
    """跑 n6_apply（`ctx_of` 从 `loop_ctx` 资源取回当前 RunCtx）。"""
    return await host_steps.n6_apply(_data(ctx, env_repo, author))


def _failed_events(ctx: RunCtx) -> list[dict[str, Any]]:
    return [e for e in ctx.progress.read()
            if e.get("kind") == "node_failed" and e.get("node") == "N6_apply"]


async def test_n6_apply_imports_candidate_before_applying(
        ctx: RunCtx, env_repo: Path, cand: Path) -> None:
    """R18 接线：有候选 ⇒ 先导入（白名单+哈希+停止+基线）再施加；沙箱件 == 候选快照。"""
    author = _author(candidate=_candidate_block(cand, env_repo))
    out = await _run_n6(ctx, env_repo, author)

    assert out["status"] == "applied" and out["count"] == 1
    case = out["cases"][0]
    assert case["source"] == "candidate_import"
    assert case["candidate"]["md5"] == case["md5_after"]
    sandbox = Path(case["sandbox_path"])
    assert sandbox.read_text(encoding="utf-8") == _APPLIED_TEXT
    imported = out["candidate_import"]
    assert imported["ok"] is True and imported["drift_checked"] is True
    assert imported["execution_state"] == "stopped"
    # 源件不被改（Host 只写沙箱）
    assert "0xdead_beef" in (env_repo / "TESTLIB" / "tc_demo.sv").read_text(encoding="utf-8")


@pytest.mark.parametrize("state,expected", [
    ("execution_unknown", "execution_unknown"),
    ("running", "execution_not_stopped"),
])
async def test_n6_apply_rejects_candidate_when_execution_not_confirmed(
        ctx: RunCtx, env_repo: Path, cand: Path, state: str, expected: str) -> None:
    """R1/R2 接线：停止未确认 ⇒ 显式失败（failed + error），绝不回退"直接用模型 edits 写"。"""
    author = _author(candidate=_candidate_block(cand, env_repo, state=state))
    with pytest.raises(ValueError, match=expected):
        await _run_n6(ctx, env_repo, author)

    assert not (ctx.run_dir / "sandbox" / "TESTLIB" / "tc_demo.sv").exists(), \
        "导入被拒时不得写入沙箱（不许退回模型 edits 直接写）"
    failed = _failed_events(ctx)
    assert failed and expected in json.dumps(failed[-1], ensure_ascii=False)


async def test_n6_apply_rejects_candidate_hash_mismatch_and_writes_nothing(
        ctx: RunCtx, env_repo: Path, cand: Path) -> None:
    """R13 接线：校验后换件 ⇒ 显式失败、零写入。"""
    block = _candidate_block(cand, env_repo)
    (cand / "TESTLIB" / "tc_demo.sv").write_text(_APPLIED_TEXT.replace("c0de", "feed"),
                                                 encoding="utf-8")
    with pytest.raises(ValueError, match="hash_mismatch"):
        await _run_n6(ctx, env_repo, _author(candidate=block))
    assert not (ctx.run_dir / "sandbox" / "TESTLIB").exists() or not any(
        (ctx.run_dir / "sandbox" / "TESTLIB").iterdir())


async def test_n6_apply_rejects_candidate_missing_manifest(
        ctx: RunCtx, env_repo: Path, cand: Path) -> None:
    """R5 接线：有候选根但没清单 ⇒ 拒（不因缺件而降级为"用 edits 直接写"）。"""
    block = _candidate_block(cand, env_repo)
    block.pop("candidate_manifest")
    with pytest.raises(ValueError, match="manifest_missing"):
        await _run_n6(ctx, env_repo, _author(candidate=block))
    assert not (ctx.run_dir / "sandbox" / "TESTLIB").exists() or not any(
        (ctx.run_dir / "sandbox" / "TESTLIB").iterdir())


async def test_n6_apply_rejects_candidate_root_outside_layout(
        ctx: RunCtx, env_repo: Path, attempt: Path) -> None:
    """候选根只认 attempt 布局的 `candidate/`（work/ 等旁路一律拒：写权只在候选目录）。"""
    work = attempt / "work"
    work.mkdir(exist_ok=True)
    entry = _write_candidate(work, "TESTLIB/tc_demo.sv", _APPLIED_TEXT)
    source_md5 = hashlib.md5((env_repo / "TESTLIB" / "tc_demo.sv").read_bytes()).hexdigest()
    block = {"candidate_root": str(work),
             "candidate_manifest": {"TESTLIB/tc_demo.sv": entry},
             "baseline": {"TESTLIB/tc_demo.sv": source_md5},
             "execution_state": "stopped"}
    with pytest.raises(ValueError, match="candidate_root_unsafe"):
        await _run_n6(ctx, env_repo, _author(candidate=block))
    assert not (ctx.run_dir / "sandbox" / "TESTLIB").exists() or not any(
        (ctx.run_dir / "sandbox" / "TESTLIB").iterdir())


def test_candidate_dir_for_attempt_comes_from_layout_only(attempt: Path) -> None:
    """布局接线：候选目录**只**从 `AttemptLayout.candidate` 取，本层不另写一套规则。"""
    from host.agent_backends import dsh_assets as A

    assert host_steps.candidate_dir_for_attempt(attempt) == A.AttemptLayout.under(attempt).candidate


def test_attempt_root_reverse_derivation_for_both_layout_shapes(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """① 旧形态 `<attempt>/candidate` 与新形态 `<attempt>/work/candidate` 都能反推 attempt 根。"""
    # 旧形态（用同一套反推逻辑 + 旧布局函数模拟）
    old = tmp_path / "old"
    (old / "candidate").mkdir(parents=True)
    monkeypatch.setattr(host_steps, "candidate_dir_for_attempt",
                        lambda root: Path(root) / "candidate")
    assert host_steps._attempt_root_for(old / "candidate") == old

    # 新形态（候选在 work/ 下）
    new = tmp_path / "new"
    (new / "work" / "candidate").mkdir(parents=True)
    monkeypatch.setattr(host_steps, "candidate_dir_for_attempt",
                        lambda root: Path(root) / "work" / "candidate")
    assert host_steps._attempt_root_for(new / "work" / "candidate") == new
    # 反推不到 ⇒ None（fail-closed，不猜 parent）
    (tmp_path / "stray" / "candidate").mkdir(parents=True)
    assert host_steps._attempt_root_for(tmp_path / "stray" / "candidate") is None


async def test_n6_apply_rejects_candidate_root_not_derivable_from_layout(
        ctx: RunCtx, env_repo: Path, tmp_path: Path) -> None:
    """② 目录"看起来像但不是布局算出的" ⇒ 显式拒绝 `candidate_root_unsafe`（fail-closed）。"""
    stray = tmp_path / "stray" / "not-a-candidate"
    (stray / "TESTLIB").mkdir(parents=True)
    entry = _write_candidate(stray, "TESTLIB/tc_demo.sv", _APPLIED_TEXT)
    source_md5 = hashlib.md5((env_repo / "TESTLIB" / "tc_demo.sv").read_bytes()).hexdigest()
    block = {"candidate_root": str(stray),
             "candidate_manifest": {"TESTLIB/tc_demo.sv": entry},
             "baseline": {"TESTLIB/tc_demo.sv": source_md5},
             "execution_state": "stopped"}
    with pytest.raises(ValueError, match="candidate_root_unsafe"):
        await _run_n6(ctx, env_repo, _author(candidate=block))
    assert not (ctx.run_dir / "sandbox" / "TESTLIB").exists() or not any(
        (ctx.run_dir / "sandbox" / "TESTLIB").iterdir())


def test_attempt_root_reverse_derivation_skips_symlink_ancestors(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """③ 符号链接祖先不参与反推：只能经由链接祖先成立的根 ⇒ None（不认）。"""
    outside = tmp_path / "outside"
    (outside / "work" / "candidate").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(host_steps, "candidate_dir_for_attempt",
                        lambda root: Path(root) / "work" / "candidate")
    declared = link / "work" / "candidate"   # 必须穿过符号链接祖先 ``link`` 才能对上布局
    assert host_steps._attempt_root_for(declared) is None


async def test_n6_apply_rejects_candidate_that_bypasses_edits(
        ctx: RunCtx, env_repo: Path, cand: Path) -> None:
    """关键防线（EDITS_MISMATCH）：候选内容 != apply(基线, edits) ⇒ 拒，候选不能绕过唯一命中判据。

    清单哈希是**自洽**的（声明值与候选内容一致，R13 过），所以只有施加阶段的一致性检查能发现
    "候选越过了 edits 校验"。
    """
    forged = _APPLIED_TEXT.replace("0xdead_c0de", "0xdead_feed")
    block = _candidate_block(cand, env_repo, text=forged)
    with pytest.raises(ValueError, match=str(CI.RejectReason.EDITS_MISMATCH.value)):
        await _run_n6(ctx, env_repo, _author(candidate=block))
    assert not (ctx.run_dir / "sandbox" / "TESTLIB").exists() or not any(
        (ctx.run_dir / "sandbox" / "TESTLIB").iterdir()), "候选与 edits 不一致 ⇒ 不写沙箱"


async def test_n6_apply_without_candidate_keeps_legacy_behavior(
        ctx: RunCtx, env_repo: Path) -> None:
    """无候选四键 ⇒ 既有路径不变（source=env_root，edits 直接施加）。"""
    out = await _run_n6(ctx, env_repo, _author())
    assert out["status"] == "applied"
    assert out["cases"][0]["source"] == "env_root"
    assert "candidate_import" not in out
    assert Path(out["cases"][0]["sandbox_path"]).read_text(encoding="utf-8") == _APPLIED_TEXT


async def test_n6_apply_candidate_import_writes_nothing_outside_sandbox(
        ctx: RunCtx, env_repo: Path, cand: Path, attempt: Path) -> None:
    """attempt 根（work/home/candidate）在导入+施加后**逐项不变**（Host 只写 run_dir 沙箱/台账）。"""
    author = _author(candidate=_candidate_block(cand, env_repo))
    before = _snapshot(attempt)
    await _run_n6(ctx, env_repo, author)
    assert _snapshot(attempt) == before, "n6_apply 不得改写 attempt 内的候选/工作副本"


async def test_real_attempt_layout_candidate_is_resolved_and_imported(
        ctx: RunCtx, env_repo: Path) -> None:
    """真机形态 `<run>/agent_workspaces/N6/attempt-000001/{work,dsh-home,candidate,input}`。

    离线验证三件事（不发真实调用）：
    1. `AttemptLayout.candidate` 由 s5-admit 提供，`candidate_dir_for_attempt` **读布局字段**；
    2. 四键 resolver 从该路径推出 `attempt_root`；
    3. 导入+施加后沙箱件 == 候选快照，且 attempt 内零写入。
    """
    import hashlib as _hashlib

    from host.agent_backends import dsh_assets as A

    workspace = A.workspace_root(ctx.run_dir, "N6", 1)
    layout = A.AttemptLayout.under(workspace)
    layout.prepare()
    # resolver 读布局字段（布局把候选移到 work/ 下也自动跟随；不在测试里硬编码位置）
    assert host_steps.candidate_dir_for_attempt(workspace) == layout.candidate
    assert host_steps._attempt_root_for(layout.candidate) == workspace
    assert layout.candidate.resolve().is_relative_to(workspace.resolve())

    (layout.candidate / "TESTLIB").mkdir(parents=True)
    (layout.candidate / "TESTLIB" / "tc_demo.sv").write_text(_APPLIED_TEXT, encoding="utf-8")
    data = (layout.candidate / "TESTLIB" / "tc_demo.sv").read_bytes()
    manifest = {"TESTLIB/tc_demo.sv": {"md5": _hashlib.md5(data).hexdigest(), "size": len(data)}}
    baseline = {"TESTLIB/tc_demo.sv":
                _hashlib.md5((env_repo / "TESTLIB" / "tc_demo.sv").read_bytes()).hexdigest()}
    block = {"candidate_root": str(layout.candidate), "candidate_manifest": manifest,
             "baseline": baseline, "execution_state": "stopped"}

    before = _snapshot(workspace)
    out = await _run_n6(ctx, env_repo, _author(candidate=block))

    assert out["status"] == "applied"
    case = out["cases"][0]
    assert case["source"] == "candidate_import"
    assert case["candidate"]["md5"] == manifest["TESTLIB/tc_demo.sv"]["md5"]
    assert Path(case["sandbox_path"]).read_text(encoding="utf-8") == _APPLIED_TEXT
    assert out["candidate_import"]["execution_state"] == "stopped"
    assert out["candidate_import"]["drift_checked"] is True
    # Host 只写 run_dir 的沙箱/台账；attempt 工作区零写入
    assert _snapshot(workspace) == before


# ================================================================ 生产接线（n6_author 四键）

_FOUR_KEYS = (host_steps.CANDIDATE_ROOT_KEY, host_steps.CANDIDATE_MANIFEST_KEY,
              host_steps.CANDIDATE_BASELINE_KEY, host_steps.CANDIDATE_EXECUTION_KEY)


def _sealed_live_out(ctx: RunCtx, workspace) -> dict[str, Any]:
    """造一条"已封存 attempt 记录 + live 输出"（生产接线读的就是这条记录里的 attempt_workspace）。

    路径一律从 `AttemptLayout` 取（候选可能在根下或 `work/` 下；测试不硬编码位置）。
    """
    from host.agent_backends import dsh_assets as A

    layout = A.AttemptLayout.under(workspace)

    def rel(path) -> str:
        return Path(path).relative_to(ctx.run_dir).as_posix()

    sealed = AM.Attempt(ctx, "N6", {
        "prompt_key": "n6_author", "input": {},
        "attempt_workspace": {
            "attempt_key": "x",
            "root": rel(layout.root),
            "candidate": rel(layout.candidate),
            "work": rel(layout.work),
            "home": rel(layout.home),
            "input": rel(layout.input_dir),
            "materials": [],
        }})
    sealed.finish("validated", payload={"revisions": []}, validation={"ok": True})
    return {"mode": "live", "standin": False, "model_call_failed": False, "error": None,
            "validation": {"ok": True, "problems": [], "accepted": {}},
            "data": {"revisions": [{"case": "tc_demo", "edits": _EDITS, "rationale": "r"}]},
            **sealed.refs()}


async def test_n6_author_produces_four_keys_then_n6_apply_imports(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产接线端到端：n6_author 产四键（合同键+停止快照+pre-prompt 基线+stopped），
    n6_apply 消费它走 `candidate_import`（不再退回"直接用模型 edits"）。"""
    workspace = A.workspace_root(ctx.run_dir, "N6", 1)
    layout = A.AttemptLayout.under(workspace)
    layout.prepare()
    (layout.candidate / "TESTLIB").mkdir(parents=True)
    (layout.candidate / "TESTLIB" / "tc_demo.sv").write_text(_APPLIED_TEXT, encoding="utf-8")
    out = _sealed_live_out(ctx, workspace)

    target = {"case": "tc_demo", "file": "TESTLIB/tc_demo.sv", "excerpt": {"text": "x"}}

    async def fake_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return out

    monkeypatch.setattr(M, "run_model_node", fake_run)
    monkeypatch.setattr(M, "build_n6_targets", lambda *a, **k: [target])
    data = FakeData(resources={"repo_root": env_repo, "loop_ctx": ctx},
                    state={"n5_impact": {"must_change_cases": ["tc_demo"]}})

    author_out = await M.n6_author(data)

    for key in _FOUR_KEYS:  # 四键**全给**
        assert key in author_out, key
    assert author_out["candidate_root"] == str(layout.candidate)
    manifest = author_out["candidate_manifest"]
    assert set(manifest) == {"TESTLIB/tc_demo.sv"}, "清单键必须来自合同，不看目录里有什么"
    assert manifest["TESTLIB/tc_demo.sv"]["md5"] == hashlib.md5(
        _APPLIED_TEXT.encode("utf-8")).hexdigest()
    assert author_out["baseline"] == {"TESTLIB/tc_demo.sv": hashlib.md5(
        (env_repo / "TESTLIB" / "tc_demo.sv").read_bytes()).hexdigest()}
    assert author_out["execution_state"] == "stopped"
    assert data.state["n6_author"] is author_out, "四键随 n6_author 输出封存进状态"

    applied = await host_steps.n6_apply(FakeData(
        resources={"repo_root": env_repo, "loop_ctx": ctx},
        state={"n6_targets": _targets(), "n6_author": author_out}))
    case = applied["cases"][0]
    assert case["source"] == "candidate_import"
    assert applied["candidate_import"]["ok"] is True
    assert applied["candidate_import"]["execution_state"] == "stopped"
    assert Path(case["sandbox_path"]).read_text(encoding="utf-8") == _APPLIED_TEXT


async def test_n6_author_without_workspace_gives_no_keys(
        ctx: RunCtx, env_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无隔离工作区（agently/drill/旧记录）⇒ 四键**全不给**（legacy 路径，不半给）。"""
    out = {"mode": "live", "standin": False, "model_call_failed": False, "error": None,
           "validation": {"ok": True, "problems": [], "accepted": {}},
           "data": {"revisions": [{"case": "tc_demo", "edits": _EDITS, "rationale": "r"}]}}
    target = {"case": "tc_demo", "file": "TESTLIB/tc_demo.sv", "excerpt": {"text": "x"}}

    async def fake_run(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return out

    monkeypatch.setattr(M, "run_model_node", fake_run)
    monkeypatch.setattr(M, "build_n6_targets", lambda *a, **k: [target])
    data = FakeData(resources={"repo_root": env_repo, "loop_ctx": ctx},
                    state={"n5_impact": {"must_change_cases": ["tc_demo"]}})

    author_out = await M.n6_author(data)
    for key in _FOUR_KEYS:
        assert key not in author_out, key


@pytest.mark.parametrize("out,expected", [
    ({"mode": "live"}, "stopped"),
    ({"mode": "standin"}, "unknown"),
    ({"mode": "live", "model_call_failed": True}, "unknown"),
    ({"mode": "live", "error": "execution_unknown：停机后仍有同组进程存活"}, "unknown"),
])
def test_candidate_execution_state_never_upgrades_unknown(
        out: dict[str, Any], expected: str) -> None:
    """停止口径：未知/失败**不得**被当成 `stopped`（DS-05 不许把未知当已停）。"""
    assert M._candidate_execution_state(out) == expected


def test_snapshot_manifest_uses_contract_keys_only(cand: Path) -> None:
    """停止后快照：键只来自合同；额外文件/链接/缺失/越界一律不进清单（留给导入判据拒）。"""
    entry = _write_candidate(cand, "TESTLIB/tc_demo.sv", "module tc_demo;\nendmodule\n")
    _write_candidate(cand, "TESTLIB/extra.sv", "module extra;\nendmodule\n")
    (cand / "TESTLIB" / "link.sv").symlink_to(cand / "TESTLIB" / "tc_demo.sv")
    manifest = CI.snapshot_candidate_manifest(cand, [
        "TESTLIB/tc_demo.sv", "TESTLIB//./tc_demo.sv", "TESTLIB/missing.sv",
        "TESTLIB/link.sv", "/etc/passwd", "TESTLIB/../escape.sv"])
    assert set(manifest) == {"TESTLIB/tc_demo.sv"}
    assert manifest["TESTLIB/tc_demo.sv"] == entry
