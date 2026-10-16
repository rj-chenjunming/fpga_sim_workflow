"""仓库根与运行目录定位。

所有路径都从**真实文件位置**向上锚定（找 `kb/tools/kb_lib.py`），
不用 `../..` 这类脆弱相对路径 —— 该做法在本工程已踩过坑
（`apply_mock_change.py` 曾因 `../../..` 失效而 `ModuleNotFoundError`）。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

_ANCHOR = Path("kb") / "tools" / "kb_lib.py"


def tool_root() -> Path:
    """**软件仓根**（含 `kb/tools/kb_lib.py`）。自锚定，不需要配置。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / _ANCHOR).is_file():
            return parent
    raise RuntimeError(f"无法从 {here} 向上找到 {_ANCHOR}；本模块必须位于软件仓内。")


TOOL_ROOT: Path = tool_root()


@lru_cache(maxsize=1)
def _kblib():
    """加载三根解析器的**唯一实现**（`kb/tools/kb_lib.py`），且不写字节码。

    口径只有一份：环境/工作区/软件三个根一律由 `kb_lib` 决定，本模块**不自己抄**
    一套环境变量名 —— 两套解析必然漂移。
    `kb/tools/` 是冻结目录：普通 import 会在其中写出 `__pycache__`（实测发生过）。
    """
    tools = str(TOOL_ROOT / "kb" / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import importlib

        return importlib.import_module("kb_lib")
    finally:
        sys.dont_write_bytecode = previous


_KB = _kblib()
#: **环境（插件）根**：被守卫的仓库（RTL/TB/PKG/TESTLIB + doc + uvs.setup）
ENV_ROOT: Path = Path(_KB.ENV_ROOT)
#: **工作区数据根**：该环境的索引/冲突/基线/运行记录（软件管理）
WORKSPACE_ROOT: Path = Path(_KB.WORKSPACE_ROOT)
ENV_ID: str = str(_KB.ENV_ID)

#: 向后兼容别名：拆仓前 `REPO_ROOT` == 被守卫的环境仓根
REPO_ROOT: Path = ENV_ROOT
LOOP_DIR: Path = TOOL_ROOT / "loop"
KB_TOOLS: Path = TOOL_ROOT / "kb" / "tools"
KB_SCHEMA: Path = TOOL_ROOT / "kb" / "schema"
KB_DIR: Path = WORKSPACE_ROOT
KB_RUNS: Path = WORKSPACE_ROOT / "runs"
KB_BASELINES: Path = WORKSPACE_ROOT / "baselines"
KB_CONFLICTS: Path = WORKSPACE_ROOT / "conflicts"


def missing_plugin_parts() -> list[str]:
    """环境插件面缺什么（空 = 齐全）。**不猜、不兜底**，由 /api/health 外显。"""
    return list(_KB.check_env())
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

#: 真实 `uvs.setup` 是**环境根**下的全局单文件 ⇒ 同工作目录内最多一个仿真/编译。
GLOBAL_SIM_SETUP: Path = ENV_ROOT / "uvs.setup"

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


def within_env(path: Path) -> bool:
    """是否落在**环境仓**内（旧名 `within_repo` 的语义）。"""
    try:
        path.resolve().relative_to(ENV_ROOT)
    except ValueError:
        return False
    return True


#: 旧名兼容
within_repo = within_env


def _rel_within(path: Path, base: Path):
    try:
        return path.resolve().relative_to(base).as_posix()
    except (ValueError, OSError):
        return None


def is_frozen_path(path: Path) -> bool:
    """编排层与 UI 一律不得写这些路径（`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §12）。

    拆仓后冻结面横跨三个根：`RTL/TB/PKG/TESTLIB/doc` 在**环境根**下，
    `kb/tools`/`kb/schema` 在**软件根**下，`kb/baselines|index|conflicts` 在**工作区数据根**下。
    三个根一个都不匹配 ⇒ 视为仓外 ⇒ 同样拒绝写（fail closed，与拆仓前一致）。
    """
    inside_any = False
    for base in (TOOL_ROOT, ENV_ROOT, WORKSPACE_ROOT):
        rel_str = _rel_within(path, base)
        if rel_str is None:
            continue
        inside_any = True
        if any(rel_str == item or rel_str.startswith(item + "/") for item in FROZEN_FOR_WRITE):
            return True
    return not inside_any
