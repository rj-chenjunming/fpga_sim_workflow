"""E-2 回归：`evidence/archive/` 归档腿必须真的产出只读归档件。

E-2（`REHEARSAL_REPORT.md:146`，major/N11）：
> `evidence/archive/` 为空 ⇒ run_guarded 的"先归档再删"腿在本次全跑里没有留下只读归档件
> 违反 spec §7.7「归档只增不改；归档件置只读」

机制原因（本文件用实证固定下来）：`archive_sweep` 只 glob
`$ROOT/SIMLIB_RUN/log/<case>_<seed>_*.log`，而 `compile-only`/`full` 模式的全部日志
写在 `$EVIDENCE_DIR/<stamp>_<case>_<seed>_*.log` —— **目录与命名都不匹配**，
于是这两种模式下 `archive/` 永远为空；且这两个模式**根本没有启动轮询**。
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

from host import paths as P

CASE = "tc_bmc_i2c_01"

UVLAN_STUB = """#!/usr/bin/env bash
# 桩：把 -logfile 指向的文件写出行，模拟 uvlan 两段编译（仅用于归档腿自测）
logf=""
while [ $# -gt 0 ]; do case "$1" in -logfile) logf="$2"; shift 2;; *) shift;; esac; done
if [ -n "$logf" ]; then printf 'STUB uvlan %s\\ncompile 0 error(s)\\n' "$(basename "$logf")" >> "$logf"; fi
exit 0
"""


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture
def guard_run(tmp_path: Path) -> dict:
    """用真实 `run_guarded.sh` 跑一次 `--mode compile-only`（uvlan 用桩）。"""
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    uvlan = stub_dir / "uvlan"
    uvlan.write_text(UVLAN_STUB, encoding="utf-8")
    uvlan.chmod(0o755)

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sandbox = tmp_path / "sandbox"

    setup_md5_before = _md5(P.REPO_ROOT / "uvs.setup")
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}:{env.get('PATH', '')}"
    proc = subprocess.run(
        [
            "bash", str(P.KB_TOOLS / "run_guarded.sh"),
            "--case-file", str(P.REPO_ROOT / "TESTLIB" / f"{CASE}.sv"),
            "--case-name", CASE, "--seed", "1",
            "--mode", "compile-only",
            "--sandbox-root", str(sandbox),
            "--evidence-dir", str(evidence),
            "--run", "RUN-E2-TEST",
        ],
        cwd=str(P.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    return {
        "proc": proc,
        "evidence": evidence,
        "sandbox": sandbox,
        "archive": evidence / "archive",
        "setup_md5_before": setup_md5_before,
    }


def test_guard_compile_only_archives_evidence_readonly(guard_run: dict) -> None:
    """核心断言：compile-only/full 模式的证据件必须进入 `archive/`，且只读。"""
    proc = guard_run["proc"]
    assert proc.returncode == 0, f"guard rc={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-1000:]}"

    archive: Path = guard_run["archive"]
    assert archive.is_dir(), "archive/ 未创建"
    names = sorted(p.name for p in archive.iterdir())
    assert names, "E-2 复现：archive/ 为空"

    assert any(n.endswith("_c_rtl.log") for n in names), f"缺 _c_rtl 归档件：{names}"
    assert any(n.endswith("_c_tb.log") for n in names), f"缺 _c_tb 归档件：{names}"

    # spec §7.7：归档件置只读
    for path in archive.iterdir():
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o444, f"归档件不是只读（{oct(mode)}）：{path.name}"


def test_guard_archive_is_bounded_and_excludes_guard_log(guard_run: dict) -> None:
    """归档必须**只增不改且不爆炸**，且不把主证据原件（guard.log）自我归档。"""
    archive: Path = guard_run["archive"]
    names = sorted(p.name for p in archive.iterdir())
    assert len(names) <= 12, f"归档件数量异常（半截件堆积？）：{len(names)} -> {names}"
    assert not any("_guard.log" in n for n in names), "guard.log 是主证据原件，不得自我归档"
    # 名字里 STAMP 只应出现一次（曾出现双时间戳 `20261015-143020_20261015-143020_...`）
    for name in names:
        stamp_stem = name.split("_")[0]
        assert name.count(stamp_stem) == 1, f"归档名出现重复时间戳：{name}"


def test_guard_cleans_up_scratch_and_leaves_frozen_state(guard_run: dict) -> None:
    """scratch 目录必须清理；`uvs.setup` 不得被改；仓库根不得残留锁。"""
    evidence: Path = guard_run["evidence"]
    assert not (evidence / ".archive_sig").exists(), "稳定判定 scratch 目录未清理"
    assert _md5(P.REPO_ROOT / "uvs.setup") == guard_run["setup_md5_before"], "uvs.setup 被改动"
    assert not (P.REPO_ROOT / ".compile_only.lock").exists(), "仓库根残留 .compile_only.lock"


# --------------------------------------------------------------- 闭环侧

async def test_drill_run_produces_readonly_archive_and_clears_e2() -> None:
    """闭环侧：drill 运行后 archive/ 非空且只读 ⇒ E-2 阻断项消失。"""
    from workflows.main_flow import RunManager

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    try:
        ex = m.executions[rid]
        for _ in range(80):
            if ex.is_waiting():
                break
            import asyncio

            await asyncio.sleep(0.1)
        await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed", actor="human:e2")
        import asyncio

        for _ in range(150):
            view = m.run_view(rid)
            if ((view.get("pending_interrupt") or {}).get("id") or "").startswith("G2"):
                break
            await asyncio.sleep(0.2)
        view = m.run_view(rid)

        archive = Path(view["run_dir"]) / "evidence" / "archive"
        assert archive.is_dir() and any(archive.iterdir()), "drill 归档腿未产出"
        for path in archive.iterdir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o444, f"归档件不是只读：{path}"
        codes = {b["code"] for b in view["blockers"]}
        assert "E2_EVIDENCE_ARCHIVE_EMPTY" not in codes, "E-2 阻断项应当已消失"
        # 判据仍必须是"双计数"，不能因为归档好了就变绿
        assert "I3_KOUTOU1_NONZERO" in codes
    finally:
        await m.stop_watching()


def test_evidence_log_prefers_run_log_over_guard_log(tmp_path: Path) -> None:
    """`evidence/` 里同时有 `_guard.log` 与 `_run.log` 时，必须选**全跑权威件**。

    guard.log 内部也复述 `*E` 汇总行，选错文件会让判据跑到包装层日志上。
    """
    from workflows.context import RunCtx
    from services.contracts import KbSources

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "20260101-000000_tc_a_1_guard.log").write_text("*E summary line\n", encoding="utf-8")
    (evidence / "20260101-000000_tc_a_1_run.log").write_text(
        "UVM Report Summary\nUVM_ERROR :    0\nUVM_FATAL :    0\n", encoding="utf-8"
    )
    ctx = RunCtx(
        run_id="RUN-TEST",
        run_dir=tmp_path,
        mode="drill",
        scenario="happy",
        kb=KbSources.from_repo(P.REPO_ROOT),
        progress=None,  # type: ignore[arg-type]
    )
    assert ctx.evidence_log().name.endswith("_run.log")


def test_real_mode_n9_routes_through_guarded_wrapper() -> None:
    """真实 N9 必须经 `run_guarded.sh --mode full`。

    直接调 `run_uvs_new.sh` 会绕过身份头 / 先归档再删 / 中止自愈 / 串行锁四项，
    `evidence/archive/` 必然为空 —— 那是 E-2 的另一半。
    """
    from workflows.chunks.long_jobs import _REAL_CASE

    src = (P.LOOP_DIR / "workflows" / "chunks" / "long_jobs.py").read_text(encoding="utf-8")
    assert "run_guarded.sh" in src, "N9 真实路径未走 evidence 包装层"
    assert "--mode full" in src
    assert "run_uvs_new.sh -c" not in src, "不得再直接调 run_uvs_new.sh -c（会绕过归档腿）"
    assert _REAL_CASE == "tc_pcie_rw_02"
