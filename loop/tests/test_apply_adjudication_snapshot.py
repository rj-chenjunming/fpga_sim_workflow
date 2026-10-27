"""E1 预备：`spikes/apply_conflict_adjudication.sh` 必须能核验**任意冻结快照**的指纹（红线 10）。

缺陷（2026-10-27 实测复现）：脚本把 72 条快照的 md5 **硬编码**，于是拿"带 4 条作者确认"的当前权威快照
（`doc/evidence/adjudication_author_confirm_20261027/`）跑，会被"快照指纹与登记不符"误挡（exit 3）——
E1 的"一条命令"因此落不了当前权威快照。修法是让指纹来源有优先级（`--expect-md5` > 快照自带 `md5.txt` >
**只对默认快照**的内置登记值）。

本测试固定四条不变式（全部走 `--dry-run`：不写数据根、不碰 `ENV_ROOT`）：

1. 快照自带 `md5.txt` ⇒ 用它核验并**通过**（新权威快照可被落账）；
2. 快照内容与 `md5.txt` 不符 ⇒ **必须红**（不能因为"有 md5.txt"就放行）；
3. 既无 `md5.txt` 又没给 `--expect-md5` ⇒ **必须红**（不许静默跳过核验）；
4. 给了 `--expect-md5` ⇒ 即使没有 `md5.txt` 也能通过（调用方显式给登记值）。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "loop" / "spikes" / "apply_conflict_adjudication.sh"
NEW_SNAPSHOT = REPO / "doc" / "evidence" / "adjudication_author_confirm_20261027"
OLD_SNAPSHOT = REPO / "doc" / "evidence" / "adjudication_20261027"

pytestmark = pytest.mark.skipif(
    not (REPO / "loop" / ".venv" / "bin" / "python").exists(),
    reason="脚本前置要求 loop/.venv/bin/python",
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """最小可写数据根：`conflicts/conflicts.json` 用冻结快照里的那份（schema 合法）。"""
    ws = tmp_path / "ws"
    (ws / "conflicts").mkdir(parents=True)
    shutil.copy(OLD_SNAPSHOT / "conflicts.json", ws / "conflicts" / "conflicts.json")
    return ws


def _run(ws: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), "--workspace", str(ws), "--dry-run", *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=300,
    )


def _md5(path: Path) -> str:
    import hashlib

    return hashlib.md5(path.read_bytes()).hexdigest()


def test_snapshot_with_own_md5_is_accepted(workspace: Path) -> None:
    """新权威快照（76 条记录、自带 md5.txt）必须能被核验并放行 —— 这就是 E1 欠的那条路径。"""
    proc = _run(workspace, "--snapshot", str(NEW_SNAPSHOT))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "指纹校验通过" in out, out[-2000:]
    assert "md5.txt" in out, f"应说明指纹来源是快照自带的 md5.txt：\n{out[-2000:]}"


def test_tampered_snapshot_is_rejected(workspace: Path, tmp_path: Path) -> None:
    """红线 10：内容与 md5.txt 不符必须红，不能因为"文件齐"就放行。"""
    snap = tmp_path / "snap-tampered"
    shutil.copytree(NEW_SNAPSHOT, snap)
    for name in ("adjudication.json", "conflicts.json"):
        (snap / name).chmod(0o644)
    with (snap / "adjudication.json").open("a", encoding="utf-8") as fh:
        fh.write("\n")                      # 只改一个字节也让 md5 变
    proc = _run(workspace, "--snapshot", str(snap))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 3, out[-3000:]
    assert "指纹与登记不符" in out, out[-2000:]


def test_snapshot_without_any_fingerprint_is_rejected(workspace: Path, tmp_path: Path) -> None:
    """既无 md5.txt 又没给 --expect-md5 ⇒ 显式失败（不许"没指纹就当通过"）。"""
    snap = tmp_path / "snap-no-md5"
    snap.mkdir()
    for name in ("adjudication.json", "conflicts.json"):
        shutil.copy(NEW_SNAPSHOT / name, snap / name)
    proc = _run(workspace, "--snapshot", str(snap))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 3, out[-3000:]
    assert "缺少可核指纹" in out, out[-2000:]


def test_expect_md5_flag_makes_it_verifiable(workspace: Path, tmp_path: Path) -> None:
    """调用方显式给登记值也能核验（快照不自带 md5.txt 时的手动路径）。"""
    snap = tmp_path / "snap-explicit"
    snap.mkdir()
    for name in ("adjudication.json", "conflicts.json"):
        shutil.copy(NEW_SNAPSHOT / name, snap / name)
    pair = f"{_md5(snap / 'adjudication.json')}:{_md5(snap / 'conflicts.json')}"
    proc = _run(workspace, "--snapshot", str(snap), "--expect-md5", pair)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out[-3000:]
    assert "指纹校验通过" in out and "--expect-md5" in out, out[-2000:]
