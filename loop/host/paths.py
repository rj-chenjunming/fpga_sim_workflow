"""仓库根与运行目录定位。

所有路径都从**真实文件位置**向上锚定（找 `kb/tools/kb_lib.py`），
不用 `../..` 这类脆弱相对路径 —— 该做法在本工程已踩过坑
（`apply_mock_change.py` 曾因 `../../..` 失效而 `ModuleNotFoundError`）。
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

_ANCHOR = Path("kb") / "tools" / "kb_lib.py"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _ANCHOR).is_file():
            return parent
    raise RuntimeError(f"无法从 {here} 向上找到 {_ANCHOR}；本模块必须位于本仓库内。")


REPO_ROOT: Path = repo_root()
LOOP_DIR: Path = REPO_ROOT / "loop"
KB_DIR: Path = REPO_ROOT / "kb"
KB_TOOLS: Path = KB_DIR / "tools"
KB_RUNS: Path = KB_DIR / "runs"
KB_BASELINES: Path = KB_DIR / "baselines"
KB_CONFLICTS: Path = KB_DIR / "conflicts"
STATE_DIR: Path = LOOP_DIR / "state"
JOBS_DIR: Path = STATE_DIR / "jobs"
RECOVERY_DIR: Path = STATE_DIR / "recovery"
EVENTS_DIR: Path = STATE_DIR / "events"
WEB_DIR: Path = LOOP_DIR / "web"

# 单槽锁与队列（见 doc/spec/LOOP_ORCHESTRATION_SPEC.md §7）
SLOT_LOCK: Path = STATE_DIR / "slot.lock"
SLOT_QUEUE: Path = STATE_DIR / "queue.json"
ADMISSION_AUDIT: Path = STATE_DIR / "admission_audit.jsonl"
GATE_LEDGER: Path = STATE_DIR / "gate_ledger.jsonl"

#: 真实 `uvs.setup` 是仓库根下的全局单文件 ⇒ 同工作目录内最多一个仿真/编译。
GLOBAL_SIM_SETUP: Path = REPO_ROOT / "uvs.setup"

FROZEN_FOR_WRITE = (
    "RTL",
    "TB",
    "PKG",
    "TESTLIB",
    "doc",
    "kb/baselines",
    "kb/index",
    "kb/conflicts",
    "kb/tools",
    "kb/schema",
    "SIMLIB",
    "LOG",
)


def now_iso(now: datetime | None = None) -> str:
    """可注入的时钟（确定性契约：时间字段是唯一允许的非确定性）。

    优先 `LOOP_NOW`，其次 `KB_NOW`，否则系统时间。
    """
    if now is not None:
        return now.isoformat()
    injected = os.environ.get("LOOP_NOW") or os.environ.get("KB_NOW")
    if injected:
        return injected
    return datetime.now().isoformat()


def make_run_id(now: datetime | None = None) -> str:
    """运行目录名，形状受 `kb/tools/gate.py` 的 `RUN-YYYYMMDD-HHMMSS` 校验约束。"""
    stamp = now_iso(now)
    try:
        dt = datetime.fromisoformat(stamp)
    except ValueError as exc:
        raise ValueError(f"LOOP_NOW/KB_NOW 不是可解析的 ISO 时间：{stamp!r}") from exc
    return f"RUN-{dt:%Y%m%d-%H%M%S}"


def ensure_state_dirs() -> None:
    for path in (STATE_DIR, JOBS_DIR, RECOVERY_DIR, EVENTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def within_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return False
    return True


def is_frozen_path(path: Path) -> bool:
    """编排层与 UI 一律不得写这些路径（`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §12）。"""
    try:
        rel = path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return True
    rel_str = rel.as_posix()
    return any(rel_str == item or rel_str.startswith(item + "/") for item in FROZEN_FOR_WRITE)
