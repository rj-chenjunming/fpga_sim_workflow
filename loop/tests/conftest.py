"""pytest 公共夹具。

关键纪律：**每个测试必须用唯一的 run_id**。
实证：固定 `LOOP_NOW` 会让两次运行落进同一个 `kb/runs/<run_id>`，
事件流续写、`gate_history` 出现重复条目 —— 那会伪造出"闸门签了两次"的假象。
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# 测试套件默认**离线**：模型节点退回确定性替身，保证快、可重复、无网络依赖。
# 真实链路验证走 `spikes/probe_provider.py` 与显式 `LOOP_LLM_MODE=live` 的运行。
os.environ.setdefault("LOOP_LLM_MODE", "standin")

# 软件 state 隔离（F03-a）：jobs/recovery/events/单槽锁不写共享 `loop/state`。
# 必须在 `from host import paths as P` 之前设置——`STATE_DIR` 在 import 期解析一次。
import atexit  # noqa: E402
import tempfile  # noqa: E402

_STATE_ROOT = Path(tempfile.mkdtemp(prefix="loop-state-"))
os.environ["LOOP_STATE_ROOT"] = str(_STATE_ROOT)
atexit.register(shutil.rmtree, _STATE_ROOT, ignore_errors=True)

LOOP_DIR = Path(__file__).resolve().parents[1]
if str(LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(LOOP_DIR))

from host import paths as P  # noqa: E402


def _drill_dirs() -> set[Path]:
    return {p.parent for p in P.KB_RUNS.glob("*/.loop_drill")}


@pytest.fixture(autouse=True)
def clean_drill_runs():
    """测试隔离：重置进程内单例 + 清理本层自己创建的 drill 运行目录。

    为什么必须重置单例：`RunManager` 是模块级单例，其后台看护任务会在
    目录被清理后**再次** `_persist`，用 `mkdir(exist_ok=True)` 把目录重建出来
    （实测留下只有 `view.json`、没有 `.loop_drill` 标记的残留目录）。

    只清理带 `.loop_drill` 标记的目录 —— 绝不触碰归档运行目录（归档只增不改）。
    """
    from workflows import main_flow

    main_flow.MANAGER = None
    before = _drill_dirs()
    yield
    for path in _drill_dirs() - before:
        shutil.rmtree(path, ignore_errors=True)
        # **事件流/快照也要清**：`RunManager.start()` 现在把"同名事件流/快照存在"也算身份占用
        # （防止新 run 的事件流混进上一轮的 gate_decided）。只删运行目录会留下这层残留，
        # 让同一秒内的下一个测试被判身份冲突。清的是本层自己创建的 drill run 的投影件。
        for extra in (P.EVENTS_DIR / f"{path.name}.jsonl", P.RECOVERY_DIR / f"{path.name}.json"):
            try:
                extra.unlink()
            except FileNotFoundError:
                pass
    main_flow.MANAGER = None


@pytest.fixture(autouse=True)
def isolated_slot():
    """每个测试从「无锁、无队列」开始。

    只做**隔离**，不在拆卸时断言"无泄漏"：有些测试刻意让 run 停在 N9
    （那是合法的槽占用，不是泄漏）。真泄漏由 `test_flow.py` 里的
    `test_slot_is_released_after_terminal_job_*` 专门断言。
    """
    for name in ("slot.lock", "queue.json"):
        path = P.STATE_DIR / name
        if path.exists():
            path.unlink()
    yield
    for name in ("slot.lock", "queue.json"):
        path = P.STATE_DIR / name
        if path.exists():
            path.unlink()


@pytest.fixture
def repo_root() -> Path:
    return P.REPO_ROOT


@pytest.fixture
def fixture_run() -> Path:
    path = P.KB_RUNS / "RUN-20261015-120626"
    if not path.is_dir():
        pytest.skip("归档演练轮夹具不存在")
    return path


@pytest.fixture
def fixture_log(fixture_run: Path) -> Path:
    return fixture_run / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
