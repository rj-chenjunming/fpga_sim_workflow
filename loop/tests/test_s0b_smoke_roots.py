"""冒烟两侧工作根的判据：基线侧**永远**走可写代理根（基线零写入）。

背景（2026-10-30 真实链实测）：`run_guarded.sh` 在 `ROOT/SIMLIB_RUN/` 建锁；把 ROOT 直接
指向受守卫的环境根时——只读挂载 ⇒ rc=3 且**不产出编译日志**（smoke 假失败）；可写 ⇒ 写基线
（与 S0 §8.2-2「断言基线零写入」矛盾）。本用例把两件事固定下来：

1. `baseline_compile_root()` 只产生**指向基线资产的软链** + 自己的可写 `SIMLIB_RUN/`，
   基线树逐文件 md5 前后不变；
2. `run_smoke()` 的基线段 cwd/`LOOP_ENV_ROOT` 都指向代理根（候选段仍用副本），
   且 README 所述的候选/基线字段只增（`compile_root` / `root_mode`）。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from host import s0b


def _tree_md5(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.md5(path.read_bytes()).hexdigest()
    return result


def _mini_baseline(root: Path) -> Path:
    files = {
        "RTL/SRC/imports/a.v": "module a;\nendmodule\n",
        "TB/tbtop.sv": "module tbtop;\nendmodule\n",
        "PKG/p.sv": "package p;\nendpackage\n",
        "TESTLIB/tc_demo.sv": "module tc_demo;\nendmodule\n",
        "BIN/.keep": "",
        "TC/output/.keep": "",
        "all_define.txt": "`define X 1\n",
        "input.tcl": "# tcl\n",
        "uvs.setup": "# uvs setup\n",
        "doc/tools/run_local.sh": "#!/bin/sh\nexit 99\n",
        "doc/_run_artifacts/uvs.setup.orig": "# orig\n",
    }
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


@pytest.fixture()
def mini_baseline(tmp_path: Path) -> Path:
    return _mini_baseline(tmp_path / "baseline")


def test_baseline_compile_root_is_symlink_proxy_and_never_writes_baseline(
    mini_baseline: Path, tmp_path: Path
) -> None:
    before = _tree_md5(mini_baseline)
    smoke_root = tmp_path / "state" / "smoke"

    info = s0b.baseline_compile_root(mini_baseline, smoke_root)

    root = Path(info["root"])
    assert root.is_dir() and not root.is_symlink()
    # 每个存在的环境条目都变成指向基线的软链（不跟随复制，不产生基线写入）
    for name in ("RTL", "TB", "PKG", "TESTLIB", "BIN", "TC", "all_define.txt",
                 "input.tcl", "uvs.setup", "doc"):
        link = root / name
        assert link.is_symlink(), f"{name} 必须是软链"
        assert Path(link).resolve() == (mini_baseline / name).resolve()
    assert (root / "SIMLIB_RUN").is_dir() and not (root / "SIMLIB_RUN").is_symlink()
    # 不在白名单里的条目不出现（代理根不是基线的复制品）
    assert not (root / "kb").exists()
    # 基线逐文件 md5 前后一致（零写入；不按 mtime）
    assert _tree_md5(mini_baseline) == before
    assert info["baseline"] == str(mini_baseline)


def test_run_smoke_baseline_segment_uses_proxy_root(
    mini_baseline: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    for part in ("RTL", "TB", "PKG", "TESTLIB"):
        (work / part).mkdir(parents=True)
    folder = tmp_path / "S0-test"
    folder.mkdir()
    record = {"work_env": str(work), "baseline": str(mini_baseline), "tb_top": "TB/tbtop.sv"}

    calls: list[dict] = []

    class _Result:
        returncode = 0
        stdout = "fake"

    def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
        calls.append({"command": list(command), **kwargs})
        evidence = Path(command[command.index("--evidence-dir") + 1])
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "FIX_c_rtl.log").write_text("Compilation: 0 error(s), 0 warning(s)\n",
                                                encoding="utf-8")
        (evidence / "FIX_c_tb.log").write_text("Compilation: 0 error(s), 0 warning(s)\n",
                                               encoding="utf-8")
        return _Result()

    monkeypatch.setattr(s0b, "_uvlan_available", lambda: True)
    monkeypatch.setattr(s0b.subprocess, "run", fake_run)
    monkeypatch.setattr(s0b.uvs_logs, "parse_log", lambda path: {"path": str(path)})
    monkeypatch.setattr(s0b.uvs_logs, "summarize",
                        lambda reports: {"ok": True, "errors": 0, "warnings": 0, "warning_codes": {}})
    monkeypatch.setattr(s0b.uvs_logs, "warning_delta",
                        lambda base, cand: {"needs_evaluation": []})

    payload = s0b.run_smoke(record, folder, "tc_demo", "RUN-SMOKE")

    assert payload["status"] == "passed", payload
    assert len(calls) == 2, calls
    candidate, baseline = calls
    # 候选段：用副本根
    assert Path(candidate["cwd"]).resolve() == work.resolve()
    assert candidate["env"]["LOOP_ENV_ROOT"] == str(work)
    # 基线段：**必须**是代理根，不是基线本身（否则只读必失败 / 可写必污染基线）
    baseline_cwd = Path(baseline["cwd"])
    assert baseline_cwd.resolve() != mini_baseline.resolve()
    assert baseline["env"]["LOOP_ENV_ROOT"] == str(baseline_cwd)
    assert baseline_cwd.is_dir() and (baseline_cwd / "SIMLIB_RUN").is_dir()
    assert (baseline_cwd / "RTL").is_symlink()
    assert payload["baseline"]["root_mode"] == "proxy_readonly_baseline"
    assert payload["candidate"]["root_mode"] == "candidate_copy"
    assert Path(payload["baseline"]["compile_root"]) == baseline_cwd
