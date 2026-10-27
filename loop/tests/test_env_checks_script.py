"""K1：环境类检查统一入口（`spikes/run_env_layer_checks.sh --with-kb-selftests`）。

背景（[K1 计划](../../doc/plans/2026-10-27-k1-env-checks-entry.md)、`doc/STATUS.md` §94）：
3 个 kb 自测此前要**手拼** `LOOP_ENV_ROOT` / `LOOP_WORKSPACE` 指向派生副本；忘了指就会在
只读真实 `ENV_ROOT` 上失败，指错根则数字不可比。统一入口把它们挂到**同一个派生副本**上，
一条命令输出 `PASS=10` / `PASS=9` / `PASS=28` 与 `3 passed`。

本测试只固定**可观察契约**（用 `--dry-run`：不复制 2.6 GB、不执行检查、不需要可写 ENV_ROOT
⇒ 属于纯软件层，不加 `env_layer` 标记）：

1. 开关可发现（`--help` 列出全部开关，不靠读源码）；
2. 加了开关后计划里**两类检查都在**（3 个 kb 自测 + env_layer 的 pytest 命令）；
3. 不加开关时**不声称**覆盖 kb 自测（证明开关真的接上了覆盖范围，而不是写死打印）；
4. `--dry-run` **不创建**派生副本（COPY 指向不存在的临时路径，跑完仍不存在）；
5. kb 自测命令必须带 `-B` + `PYTHONDONTWRITEBYTECODE=1`（`kb/tools/**` 冻结，红线 11：
   不许写 `__pycache__`）。

实际通过/失败数字由 `doc/STATUS.md` 记录，本测试**不**执行 2.6 GB 复制与真实检查。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[1]
REPO = LOOP.parent
SCRIPT = LOOP / "spikes" / "run_env_layer_checks.sh"

#: kb 自测清单（与脚本同一份契约；这里是"必须被覆盖"的名单，不是实现）。
KB_SELFTESTS = (
    "_selftest_gate_schema.py",
    "_selftest_n5_reachability.py",
    "_selftest_adjudicate_conflicts.py",
)

pytestmark = pytest.mark.skipif(
    not (LOOP / ".venv" / "bin" / "python").exists(),
    reason="脚本前置要求 loop/.venv/bin/python（本机无则无法验证脚本行为）",
)


def _run(*args: str, copy: Path | None = None, timeout: int = 180
         ) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if copy is not None:
        env["COPY"] = str(copy)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=timeout, env=env,
    )


def _dry_run(copy: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run("--dry-run", *args, copy=copy)


def test_help_lists_the_unified_flags() -> None:
    """K1 能力必须可发现：帮助里能看到统一入口的四个开关。"""
    proc = _run("--help", timeout=60)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    for flag in ("--with-kb-selftests", "--dry-run", "--reuse", "--cleanup"):
        assert flag in out, f"--help 未列出 {flag}：\n{out[-2000:]}"


def test_dry_run_with_selftests_covers_both_layers(tmp_path: Path) -> None:
    """一条命令覆盖两类检查：3 个 kb 自测 + env_layer 的 pytest 命令都要在计划里。"""
    copy = tmp_path / "env-copy-dry"
    proc = _dry_run(copy, "--with-kb-selftests")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    for name in KB_SELFTESTS:
        assert name in out, f"计划里缺少 kb 自测 {name}：\n{out[-2000:]}"
    assert "-m env_layer" in out, out[-2000:]
    assert "tests/test_archive_e2.py" in out and "tests/test_projection_and_frozen.py" in out


def test_printed_plan_carries_the_same_env_as_the_real_run(tmp_path: Path) -> None:
    """打印的计划必须与真执行同源：两类检查都要带副本的 `LOOP_ENV_ROOT`/`LOOP_WORKSPACE`。

    回归背景（2026-10-27 自查）：`KB_ENV` 曾定义在 dry-run 分支**之后**，于是打印出的 env_layer
    命令**静默少了** `LOOP_ENV_ROOT`/`LOOP_WORKSPACE`（打印与执行两套东西）。计划里的命令必须能被
    人照着直接复制执行，否则"计划"就是装饰。
    """
    copy = tmp_path / "env-copy-sameenv"
    proc = _dry_run(copy, "--with-kb-selftests")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    env_lines = [ln for ln in out.splitlines() if "-m env_layer" in ln]
    assert len(env_lines) == 1, env_lines
    for line in [*env_lines, *[ln for ln in out.splitlines() if any(n in ln for n in KB_SELFTESTS)]]:
        assert f"LOOP_ENV_ROOT={copy}" in line, f"计划里的命令缺少副本数据根：{line}"
        assert f"LOOP_WORKSPACE={copy}/kb" in line, f"计划里的命令缺少副本数据根：{line}"


def test_dry_run_does_not_copy_the_derived_env_root(tmp_path: Path) -> None:
    """`--dry-run` 只打印计划：不得复制 2.6 GB、不得建副本目录。"""
    copy = tmp_path / "env-copy-must-stay-absent"
    proc = _dry_run(copy, "--with-kb-selftests")
    assert proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]
    assert not copy.exists(), "--dry-run 不得创建派生 ENV_ROOT 副本"
    assert "--reuse" in (proc.stdout + proc.stderr) or "派生副本" in (proc.stdout + proc.stderr)


def test_kb_selftest_commands_avoid_pyc_in_frozen_tools_dir(tmp_path: Path) -> None:
    """红线 11：kb 自测必须带 `-B`，且禁用字节码写入（`kb/tools/**` 是冻结目录）。"""
    proc = _dry_run(tmp_path / "env-copy-pyc", "--with-kb-selftests")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    kb_lines = [ln for ln in out.splitlines() if any(n in ln for n in KB_SELFTESTS)]
    assert len(kb_lines) == len(KB_SELFTESTS), kb_lines
    for line in kb_lines:
        assert " -B " in line, f"kb 自测命令缺少 -B：{line}"
        assert "PYTHONDONTWRITEBYTECODE=1" in line, f"kb 自测命令未禁用字节码：{line}"


def test_dry_run_without_flag_does_not_claim_selftests(tmp_path: Path) -> None:
    """对照面：不加开关时计划里**不得**出现 kb 自测（开关真的接上了覆盖范围）。"""
    proc = _dry_run(tmp_path / "env-copy-plain")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    for name in KB_SELFTESTS:
        assert name not in out, f"未加 --with-kb-selftests 却声称会跑 {name}：\n{out[-2000:]}"
    assert "未启用" in out, f"应显式说明 kb 自测未启用：\n{out[-2000:]}"


def test_dry_run_cleanup_is_zero_side_effect(tmp_path: Path) -> None:
    """独立复核 A 项回归钉：`--dry-run --cleanup` **不得真的删除**副本。

    旧实现里 `--cleanup` 分支在前，`--dry-run --cleanup` 会 `rm -rf` 掉默认 `.env-copy`
    （2.6 GB，且是唯一派生副本）。`--dry-run` 的契约是"只打印计划"，删除属副作用。
    """
    copy = tmp_path / "keep-me"
    copy.mkdir()
    proc = _run("--dry-run", "--cleanup", copy=copy)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-2000:]
    assert copy.exists(), "--dry-run 必须零副作用：副本被删了"
    assert "将删除" in out, f"应打印『将删除』而不是真删：\n{out[-2000:]}"


def test_failure_is_explicit_when_selftest_cannot_pass(tmp_path: Path) -> None:
    """判据钉：kb 自测跑不通过时必须**显式失败**（非 0 + `[FAIL]`），不许吞成通过/跳过。

    造一个空派生副本（只有 `kb/`，没有历史夹具）：3 个自测必然不达标（`FAIL>0` 或条数不符），
    因此整条命令必须非 0，且每个自测名都要出现在输出里（可见，不是静默跳过）。
    """
    fake = tmp_path / "fake-env"
    (fake / "kb").mkdir(parents=True)
    proc = _run("--with-kb-selftests", "--reuse", copy=fake, timeout=300)
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, f"自测未达标却返回 0：\n{out[-3000:]}"
    assert "[FAIL]" in out, out[-3000:]
    for name in KB_SELFTESTS:
        assert name in out, f"失败自测 {name} 未出现在输出里（静默跳过？）：\n{out[-3000:]}"
    assert "验收数字要求" in out, f"失败原因应指出验收数字：\n{out[-3000:]}"
