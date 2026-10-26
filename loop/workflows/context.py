"""一次运行的上下文（host 依赖经 runtime_resources 注入）。

为什么必须走 runtime_resources 而不是闭包：
执行快照**不序列化** live 对象（客户端、回调、信号量、锁），
`async_load(..., runtime_resources=...)` 要求**重新注入**。
闭包捕获会让恢复后的执行拿不到这些依赖（`agently-triggerflow/references/recovery.md`）。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from host.admission import Admission
from host.evidence import evidence_view
from host.job_runner import JobRunner
from host.progress import ProgressLog
from host import paths as P
from services.agent_view import AGENT_ROLES, GATE_NODES
from services.contracts import KbSources

RESOURCE_KEY = "loop_ctx"

#: 模型语义节点与闸门节点：从 `services.agent_view` **派生**（不手抄第二份表，
#: 避免"哪些节点是模型节点"出现两套口径）。
_MODEL_NODES: frozenset[str] = frozenset(
    node for role in AGENT_ROLES for node in role["nodes"]
)
_GATE_NODES: frozenset[str] = frozenset(GATE_NODES)

#: 失败事件 `detail.source` 的缺省（§10.4 的同一枚举；drill 走夹具、real 走 kb 工具）。
_KB_TOOL_NODES: frozenset[str] = frozenset(
    {"N0", "N1", "N2", "N5", "N7", "N9", "N9_submit", "N15_submit", "N16"}
)
#: 失败事件缺省里"框架/Host 自身判定"的节点（没有外部工具或模型参与）。
_FRAMEWORK_NODES: frozenset[str] = frozenset({"N6_apply", "N15_select", "N15", "HALT"})

#: drill 夹具：归档演练轮。选它的原因——一个目录同时覆盖
#: 双计数分歧（1687 vs 0）、死任务、印记 1/1/1、闸门拒绝、篡改检测、staging 残留，
#: 而真实全跑单用例 ≈19 min、修订后可达 22.8 h，不能作为交互开发循环。
DEFAULT_DRILL_FIXTURE = "RUN-20261015-120626"


def drill_fixture_run() -> Path:
    """选定 drill 夹具目录（SPEC-REV-05 R2：可参数化，缺省保持旧夹具）。

    `LOOP_DRILL_FIXTURE` 的取值规则：
    - 空 / 未设 ⇒ `WORKSPACE/runs/RUN-20261015-120626`（legacy，端到端断言依赖它）；
    - 绝对路径 ⇒ 原样使用；
    - 含 `/` 的相对值 ⇒ 相对 `WORKSPACE_ROOT`（如 `fixtures/drill-real-20261024`）；
    - 纯名字 ⇒ `WORKSPACE/runs/<名字>`。
    """
    raw = (os.environ.get("LOOP_DRILL_FIXTURE") or "").strip()
    if not raw:
        return P.KB_RUNS / DEFAULT_DRILL_FIXTURE
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    if "/" in raw:
        return Path(P.WORKSPACE_ROOT) / candidate
    return P.KB_RUNS / raw


#: 夹具的必需输入（缺任一 ⇒ 启动期显式失败，不静默回退到旧夹具）。
DRILL_REQUIRED_FILES: tuple[str, ...] = (
    "n1_manifest_new.json",
    "n2_diff.json",
    "n5_impact.json",
    "n12_report.md",
)


def validate_drill_fixture(path: Path) -> list[str]:
    """返回缺失项（空列表 = 通过）。只做存在性/目录判断，不解释内容。"""
    missing = [name for name in DRILL_REQUIRED_FILES if not (Path(path) / name).is_file()]
    if not (Path(path) / "evidence").is_dir():
        missing.append("evidence/")
    return missing


FIXTURE_RUN = drill_fixture_run()

#: 夹具里的全跑证据（含 UVM Report Summary 与 1687 条 `*E`）；legacy 单例路径使用。
FIXTURE_EVIDENCE_LOG = FIXTURE_RUN / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"

DRILL_FILES = (
    "n1_manifest_new.json",
    "n2_diff.json",
    "n2_diff.md",
    "n3_digest.md",
    "n5_impact.json",
    "n5_impact.md",
    "N6_author_note.md",
    "check_C.md",
    "reconcile.md",
    "n12_report.md",
    # Host 留痕（SPEC-REV-01 R2 / WEB_UI §4.4）：G1 材料要能打开"改了什么"的来源。
    # 只复制这一份摘要文件；夹具的 `staged/rtl|doc|regmap` 仍不进 run 目录
    # （drill 不走 staged 摄入路径，复制整套会让 N1 误以为提供了 staged 输入）。
    "staged/mock_change_applied.json",
)
#: 注意：**刻意不复制 `case_states.json`**。用例态台账是 **per-run** 文件
#: （`case_states.json` 的 `run_id` 必须等于本 run）：把归档轮的台账种进新 run
#: 会被 `kb/tools/case_state.py` 判为身份错位（rc=4），也会伪造"本轮用例态"。
#: 本轮台账由 N6/N8/N10 的 Host 步骤用 `case_state.py init/set` 现建。
#: 注意：**刻意不复制 `gates.json`**。夹具里的 gates.json 是演练签署
#: （`human_signed=false`），复制进来会让「闸门已签」凭空成立。
#: 新运行的闸门态必须由 `kb/tools/gate.py init` 从空开始建。


@dataclass
class RunCtx:
    """一次运行的 host 侧依赖与身份。"""

    run_id: str
    run_dir: Path
    mode: str
    scenario: str
    kb: KbSources
    progress: ProgressLog
    admission: Admission | None = None
    runner: JobRunner | None = None
    fixture: Path = field(default_factory=drill_fixture_run)
    pending: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    # ---------- 事件 ----------

    def event(self, kind: str, **kw: Any) -> None:
        self.progress.append(kind, **kw)

    def node_started(self, node: str) -> None:
        self.event("node_started", node=node, status="running")

    def node_finished(self, node: str, *, status: str = "ok", detail: dict[str, Any] | None = None,
                      refs: list[str] | None = None) -> None:
        self.event("node_finished", node=node, status=status, detail=detail or {}, refs=refs or [])

    def node_failed(self, node: str, *, message: str, source: str | None = None,
                    summary: str | None = None) -> None:
        """失败事件：`message` 原文 + `source` + `summary`（§10.4：面板不得显示"完成"）。

        `source` 缺省按节点族解析（`failed_source`）：drill 走夹具、real 走 kb 工具、
        模型节点按当前模型配置取 live/standin、闸门取 human_gate。**不是**"猜能力"，
        只是标注这条失败发生在哪条执行路径上；解析不出就显式 null。
        `summary` 缺省用 `message` 原文拼成一行（不新造数字/结论）。
        """
        self.event(
            "node_failed",
            node=node,
            status="failed",
            detail={
                "message": message,
                "source": source if source is not None else self.failed_source(node),
                "summary": summary if summary is not None else f"{node}：{message}",
            },
        )

    def failed_source(self, node: str) -> str | None:
        """失败事件的执行路径缺省（§10.4 枚举；解析不出 ⇒ None，不猜）。"""
        if node in _GATE_NODES:
            return "human_gate"
        if node in _MODEL_NODES:
            from host import model_provider as MP

            return "model_live" if MP.resolve().available else "model_standin"
        if node in _KB_TOOL_NODES:
            return "drill_fixture" if self.mode == "drill" else "kb_tool"
        if node in _FRAMEWORK_NODES:
            return "framework"
        return None

    # ---------- 夹具 ----------

    def fixture_path(self, name: str) -> Path:
        return self.fixture / name

    def copy_fixture(self, name: str, *, dest_name: str | None = None) -> Path | None:
        src = self.fixture / name
        if not src.is_file():
            return None
        dest = self.run_dir / (dest_name or name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def read_fixture_text(self, name: str) -> str | None:
        src = self.fixture / name
        if not src.is_file():
            return None
        return src.read_text(encoding="utf-8", errors="replace")

    # ---------- 证据 ----------

    def evidence_log(self) -> Path:
        """本 run 的**权威**全跑日志。

        加了 `run_guarded.sh` 包装层后，`evidence/` 里除了 `<stamp>_<case>_<seed>_run.log`
        还会有一份 `_guard.log` —— 后者内部也复述了 `*E` 汇总行，
        若不排除就会把**包装层日志**当成权威全跑日志（判据会跑到错的文件上）。
        """
        evid = self.run_dir / "evidence"
        missing = evid / "MISSING.log"
        if not evid.is_dir():
            return missing
        candidates = [p for p in sorted(evid.glob("*.log")) if not p.name.endswith("_guard.log")]
        if not candidates:
            return missing

        def has_summary(path: Path) -> bool:
            try:
                return "UVM Report Summary" in path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return False

        # ① 优先"带 UVM 汇总的 run.log"（全跑权威件）
        for path in candidates:
            if path.name.endswith("_run.log") and has_summary(path):
                return path
        # ② 其次任意带 UVM 汇总的件
        for path in candidates:
            if has_summary(path):
                return path
        # ③ 再次任意含 `*E` 的件（编译期证据也可能带失败行）
        for path in candidates:
            try:
                if "*E" in path.read_text(encoding="utf-8", errors="replace"):
                    return path
            except OSError:
                continue
        # ④ 都不像全跑证据：返回第一个（判据会如实判"判据不可判"）
        return candidates[0]

    def evidence(self) -> dict[str, Any]:
        return evidence_view(self.evidence_log())


def ctx_of(data: Any) -> RunCtx:
    """从 runtime resources 取回本次运行的上下文。

    `data.require_resource` 在缺失时**fail closed**（不给默认值）——这是刻意的：
    恢复后忘记重新注入依赖，必须立刻炸，而不是拿一个空上下文继续跑。
    """
    ctx = data.require_resource(RESOURCE_KEY)
    if not isinstance(ctx, RunCtx):
        raise TypeError(f"{RESOURCE_KEY} 必须是 RunCtx，实际 {type(ctx)!r}")
    return ctx


def runtime_resources(ctx: RunCtx) -> dict[str, Any]:
    return {RESOURCE_KEY: ctx}


def prepare_run_dir(run_id: str, *, mode: str) -> Path:
    """运行目录 = `kb/runs/<run_id>`。

    **两种模式都用这个根**，原因是硬约束而非偏好：`kb/tools/gate.py` 经
    `kb_lib.run_dir(run_id)` 唯一口径解析路径（`kb/runs/<run_id>/gates.json`，无环境变量覆盖）。
    把 drill 放到别处，会让闸门权威文件与运行目录分家。

    drill 与 real 的差别**只在节点的数据来源**（夹具 vs 真跑 kb 工具），不在目录。
    夹具目录 `kb/runs/RUN-20261015-120626` 始终**只读**。
    """
    run_dir = P.KB_RUNS / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if mode == "drill":
        # 标记只读来源 + 供测试/清理识别"本层创建的运行目录"，避免误伤归档。
        (run_dir / ".loop_drill").write_text(
            f"created_by=loop\ndrill_fixture={drill_fixture_run()}\n", encoding="utf-8"
        )
    return run_dir
