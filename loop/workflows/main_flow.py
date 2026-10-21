"""稳定拓扑（N0–N16）与一次运行的生命周期。

本模块是**图与生命周期的唯一 owner**。业务判定不在本文件里（那在 kb 工具/节点里）。

拓扑要点（spec §3/§4）：
- 6↔8 是**显式回边**（`when("N8_REWORK").to(n6_author)`），不藏在 `while True` 里；
- N9 是**提交 + 停放**两段，执行在作业期间处于中断而非 `running`（重启恢复的前提）；
- N15 的扇出由 `for_each` 承载，且**并发上限=1**：`uvs.setup` 是仓库根下全局单文件，
  同工作目录禁止并发（真正的并行只跨机，经 `run_tc.py`）。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from agently import TriggerFlow

from host import gate_authority as GA
from host import paths as P
from host.admission import Admission, run_id_of_slot_job_id, slot_job_id
from host.job_runner import JobRunner
from host.progress import ProgressLog
from services import contracts
from services.contracts import KbSources

from .chunks import gates as gate_chunks
from .chunks.gates import (
    BRANCH_DRIFT,
    GATE_DECISIONS,
    GATE_IDS,
    gate1,
    gate2,
    gate3,
    halt,
)
from .chunks.host_steps import (
    n0_baseline,
    n1_manifest,
    n2_diff,
    n5_impact,
    n6_apply,
    n7_compile,
    n16_promote,
)
from .chunks.long_jobs import n9_park, n9_submit, n15_run, n15_select
from .chunks.model_steps import n10_reconcile, n11_review, n12_report, n3_digest, n6_author, n8_check
from .context import RESOURCE_KEY, RunCtx, prepare_run_dir, runtime_resources

# I17：**启动自检**。权威枚举与本层事件表漂移时立即炸，不带漂移启动。
gate_chunks.assert_topology_matches_authority()

#: 返工上限（I7）。N8 与 N16 都校验；本层只负责把回边**图示化**。
REWORK_LIMIT = 3

#: 单槽租约的节点前缀（`<节点>-<run_id>`，口径见 `host.admission.slot_job_id`）。
SLOT_NODES = ("N9", "N15", "N7")

#: 图里**再无后继**的节点。走到它们就意味着一轮结束。
#: 必须显式关闭执行：`create_execution(auto_close=False)` 关掉了框架里**唯一**会把
#: 生命周期置为 CLOSED 的机制（`_auto_close_monitor`，而它本身对 `is_waiting()` 是安全的，
#: 停放中的闸门不会被它关掉）⇒ 不显式关，`is_closed()` 永远为假、`status` 永远 `running`：
#: 界面看板永远显示"进行中"，而 `async_restore_all()` 会在每次重启时把这些僵尸 run
#: 再恢复一遍（它按 `status in ("waiting_gate","running")` 筛选）。
#: v1 终验实测：`G3=defer` 走到 HALT 后 `status=running` 永不收敛。
TERMINAL_NODES = frozenset({"HALT", "N16"})

LOOP_FLOW = TriggerFlow(name="change-impact-loop")

(
    LOOP_FLOW.to(n0_baseline)
    .to(n1_manifest)
    .to(n2_diff)
    .to(n3_digest)
    .to(gate1)
)

LOOP_FLOW.when("G1_CONFIRMED").to(n5_impact).to(n6_author).to(n6_apply).to(n7_compile).to(n8_check)
# 有疑义 / 忽略 ⇒ 不进入修订阶段，闭环显式终止（不假装收敛）
LOOP_FLOW.when("G1_IGNORED").to(halt)
LOOP_FLOW.when("G1_DISPUTED").to(halt)

# 显式回边：N8 退回 ⇒ 回 N6（返工计数只读 case_state 台账，上限由 N8/N16 校验）
LOOP_FLOW.when("N8_REWORK").to(n6_author)
# I7/A22：N8 超限不再直接终止，改指 N13 人工裁决（能力级闸门，载荷带升级原因）
LOOP_FLOW.when("N8_ESCALATE").to(gate2)
LOOP_FLOW.when("N8_PASS").to(n9_submit).to(n9_park).to(n10_reconcile).to(n11_review)

# N11 = 证据守护（A10）：成链 → N12；不成链 → 显式回边 N6（不得无条件落到 N12）
LOOP_FLOW.when("N11_INTACT").to(n12_report).to(gate2)
LOOP_FLOW.when("N11_REWORK").to(n6_author)
# I7/A22：N11 证据守护返工超限 ⇒ 升级 N13 人工裁决（不再直接失败/死循环）
LOOP_FLOW.when("N11_ESCALATE").to(gate2)

LOOP_FLOW.when("G2_REWORK").to(n6_author)
LOOP_FLOW.when("G2_ACCEPT").to(gate3)

# N15：单作业串行（`n15_run`），不再用 for_each —— 并发上限=1 的约束内化到单作业里，
# 拓扑上因此没有扇出/汇合。四个 G3 决策分支都存在（枚举取自权威，见 BRANCH_DRIFT 自检）。
LOOP_FLOW.when("G3_FULL_NOW").to(n15_select).to(n15_run).to(n16_promote)
LOOP_FLOW.when("G3_SUBSET_ONLY").to(n15_select).to(n15_run).to(n16_promote)
LOOP_FLOW.when("G3_MILESTONE").to(n15_select).to(n15_run).to(n16_promote)
LOOP_FLOW.when("G3_DEFER").to(halt)


def node_history(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """由事件流派生节点历史（不另做一份账，避免双写）。"""
    order: list[str] = []
    latest: dict[str, dict[str, Any]] = {}
    for e in events:
        if e.get("kind") not in ("node_started", "node_finished", "node_failed"):
            continue
        node = e.get("node")
        if not node:
            continue
        if node not in latest:
            order.append(node)
        latest[node] = {
            "node": node,
            "status": e.get("status"),
            "kind": e.get("kind"),
            "at": e.get("ts"),
            "detail": e.get("detail") or {},
        }
    return [latest[n] for n in order]


def reached_terminal(events: list[dict[str, Any]]) -> str | None:
    """最后一个**节点事件**若是终止节点的 `node_finished`，返回该节点名；否则 None。

    只看事件流、不另做一份账；`node_history` 的末项是"最近首次出现的节点"，
    不能用来判断"当前走到哪"。
    """
    last: dict[str, Any] | None = None
    for e in events:
        if e.get("kind") in ("node_started", "node_finished", "node_failed"):
            last = e
    if last is None or last.get("kind") != "node_finished":
        return None
    node = last.get("node")
    return node if node in TERMINAL_NODES else None


def gate_history(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "gate": (e.get("detail") or {}).get("gate"),
            "decision": (e.get("detail") or {}).get("decision"),
            "actor": (e.get("detail") or {}).get("actor"),
            "reason": (e.get("detail") or {}).get("reason"),
            "at": e.get("ts"),
        }
        for e in events
        if e.get("kind") == "gate_decided"
    ]


@dataclass
class RunDoc:
    run_id: str
    run_dir: str
    baseline: str | None
    mode: str
    scenario: str
    project: str | None = None
    status: str = "running"
    created_at: str = ""
    updated_at: str = ""
    pending_interrupt: dict[str, Any] | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": self.run_dir,
            "baseline": self.baseline,
            "project": self.project,
            "mode": self.mode,
            "scenario": self.scenario,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pending_interrupt": self.pending_interrupt,
            "error": self.error,
            "notes": self.notes,
        }


class RunManager:
    """运行的登记、恢复与对外投影。

    它**不是**并行状态机：状态权威 = TriggerFlow 执行 + `kb/tools/gate.py`；
    本类只持有进程内句柄与一份**只读投影**。
    """

    def __init__(self, *, repo_root: Path | None = None):
        P.ensure_state_dirs()
        self.repo_root = Path(repo_root or P.REPO_ROOT)
        self.kb = KbSources.from_workspace(P.WORKSPACE_ROOT)
        self.admission = Admission(P.STATE_DIR)
        self.runner = JobRunner(P.JOBS_DIR, self.admission)
        # 单槽的三处外部依赖由本类注册（admission 不反向 import 编排层）：
        #  - 作业相位探针（B5：锁判活看作业，不看 uvicorn 进程）
        #  - 队首存活校验（I5：死条目不得拿到锁）
        #  - 队列唤醒器（C2：release 交接后**真的**把队首执行唤醒）
        self.admission.set_job_probe(self.runner.phase_of)
        self.admission.set_queue_validator(self._slot_queue_head_alive)
        self.admission.set_resumer(self._on_slot_handoff)
        self.executions: dict[str, Any] = {}
        self.ctxs: dict[str, RunCtx] = {}
        self.docs: dict[str, RunDoc] = {}
        self._watch_task: asyncio.Task[Any] | None = None
        self._snap_task: asyncio.Task[Any] | None = None
        self._delivering: set[str] = set()
        #: 本次进程实例的唯一标识 —— 恢复时的**重投递必须换新的 `resume_request_id`**：
        #: 那是 TriggerFlow 的去重键，沿用旧 id 会被判"重复投递"而**静默拒绝**（实测：
        #: `resume_dispatch_failed ... changed phase`，而 `async_continue_with` 并不抛错），
        #: 于是 run 永久停在 JOB 中断上。
        self._boot_id = "P%dT%d" % (os.getpid(), int(time.time()))
        self._redeliver_n = 0
        self._load_docs()

    # ---------------- 投影持久化 ----------------

    def _view_path(self, run_id: str) -> Path:
        doc = self.docs.get(run_id)
        base = Path(doc.run_dir) if doc else P.KB_RUNS / run_id
        return base / "view.json"

    def _snapshot_path(self, run_id: str) -> Path:
        return P.RECOVERY_DIR / f"{run_id}.json"

    def _load_docs(self) -> None:
        roots = (P.KB_RUNS, P.STATE_DIR / "runs")
        for root in roots:
            if not root.is_dir():
                continue
            for view in sorted(root.glob("*/view.json")):
                try:
                    data = json.loads(view.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                run_id = data.get("run_id")
                if not run_id:
                    continue
                self.docs[run_id] = RunDoc(
                    run_id=run_id,
                    run_dir=data.get("run_dir", str(view.parent)),
                    baseline=data.get("baseline"),
                    mode=data.get("mode", "drill"),
                    scenario=data.get("scenario", "happy"),
                    status=data.get("status", "unknown"),
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    pending_interrupt=data.get("pending_interrupt"),
                    error=data.get("error"),
                    notes=data.get("notes", []),
                )

    def _persist(self, run_id: str) -> None:
        doc = self.docs[run_id]
        path = self._view_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _progress(self, run_id: str) -> ProgressLog:
        return ProgressLog(P.EVENTS_DIR, run_id)

    # ---------------- 单槽（C2/B5/I5） ----------------

    @staticmethod
    def _slot_job_ids_for(run_id: str) -> list[str]:
        return [slot_job_id(node, run_id) for node in SLOT_NODES]

    def _slot_queue_head_alive(self, entry: dict[str, Any]) -> bool:
        """I5：队首必须仍活着**且仍停在 SLOT 中断上**，否则是幽灵条目。

        队列是状态；死 run 留在队里会让后续 release 把锁交给一个再也不会有人的执行
        （然后整条队列饿死）。这里只做只读判定，不再写状态。
        """
        run_id = run_id_of_slot_job_id(str(entry.get("job_id") or ""))
        if not run_id:
            return False
        doc = self.docs.get(run_id)
        if doc is None or doc.status in ("failed", "finished"):
            return False
        execution = self.executions.get(run_id)
        if execution is None:
            # 本进程还没恢复它 ⇒ 不能把锁交给它（恢复时会重新申请/排队）。
            return False
        try:
            pending = execution.get_pending_interrupts() or {}
        except Exception:
            return False
        return any(str(key).startswith("SLOT:") for key in pending)

    def _on_slot_handoff(self, handoff: dict[str, Any]) -> bool:
        """C2：release 把槽交接给队首后，必须**真的唤醒**队首执行（否则永久停放）。

        由 `Admission.release()` 在交接成功后同步回调。本进程内能找到执行且有 SLOT 中断
        就排一个唤醒任务；找不到（别的进程持有/尚未恢复）返回 False，让 admission
        把锁收回继续下一个队首 —— 绝不允许"锁给了但没人会跑"。
        """
        run_id = run_id_of_slot_job_id(str(handoff.get("job_id") or ""))
        if not run_id:
            return False
        execution = self.executions.get(run_id)
        if execution is None:
            return False
        try:
            pending = execution.get_pending_interrupts() or {}
        except Exception:
            return False
        slot_keys = [str(k) for k in pending if str(k).startswith("SLOT:")]
        if not slot_keys:
            # 没有 SLOT 中断：它已经不在等槽（可能已自行恢复并持有锁）。
            return True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - 非事件循环上下文
            return False
        loop.create_task(self._resume_slot(run_id, slot_keys[0], handoff))
        return True

    async def _resume_slot(self, run_id: str, interrupt_id: str, handoff: dict[str, Any]) -> None:
        """把「槽给你了」投递给队首的 SLOT 中断（`resume_to="self"` 会重入 N9 提交段）。"""
        execution = self.executions.get(run_id)
        if execution is None:
            return
        self._redeliver_n += 1
        request_id = f"{run_id}:slot:{self._boot_id}:{self._redeliver_n}"
        try:
            await execution.async_continue_with(
                interrupt_id,
                {"slot": "granted", "job_id": handoff.get("job_id"),
                 "tc": handoff.get("tc"), "seed": handoff.get("seed")},
                resume_request_id=request_id,
                actor="host:admission",
            )
        except Exception as exc:
            await self._fail_run(
                run_id,
                f"单槽交接后唤醒失败（中断 {interrupt_id}）：{type(exc).__name__}: {exc}",
            )
            return
        if interrupt_id in (execution.get_pending_interrupts() or {}):
            await self._fail_run(
                run_id,
                f"单槽交接后唤醒未生效：中断 {interrupt_id} 仍在等待（resume 被拒）。",
            )
            return
        try:
            await self.async_sync(run_id)
        except Exception:  # pragma: no cover - 投影失败不得掀翻唤醒任务
            pass

    # ---------------- 失败收敛（I1/I2/I3） ----------------

    def _wait_status(self, pending: dict[str, Any]) -> str:
        """I18：按中断**类型**区分在等什么（不再把 JOB/SLOT 都投影成"等你决策"）。"""
        if not pending:
            return "waiting_gate"
        item = next(iter(pending.values())) or {}
        kind = str(item.get("type") or "")
        interrupt_id = str(item.get("id") or "")
        if kind == "gate_decision" or interrupt_id.startswith("G"):
            return "waiting_gate"
        if kind == "job_done" or interrupt_id.startswith("JOB:"):
            return "waiting_job"
        if kind == "slot_wait" or interrupt_id.startswith("SLOT:"):
            return "waiting_slot"
        return "waiting_interrupt"

    async def _close_execution(self, run_id: str, *, reason: str) -> Any:
        """显式关闭执行并记录 `close_result`（I3：失败/终态都必须关，不能挂着）。"""
        execution = self.executions.get(run_id)
        doc = self.docs.get(run_id)
        if execution is None or doc is None:
            return None
        try:
            if execution.is_closed():
                return None
            result = await execution.async_close(reason=reason, pending_interrupts="cancel")
        except Exception as exc:
            doc.notes.append(f"关闭执行失败（{reason}）：{type(exc).__name__}: {exc}")
            return None
        doc.notes.append(f"执行已关闭：reason={reason} close_result={type(result).__name__}")
        return result

    async def _fail_run(self, run_id: str, message: str, *, reason: str = "run_failed") -> None:
        """**失败必须显式收敛**：`failed` + `error` + 清 pending + 释放单槽 + close。

        旧实现的失败分支只 `doc.error=...`，执行永不 close、单槽可能永久占住，
        使"一个 run 失败"放大成"后续全部卡在 SLOT/JOB 中断"。
        """
        doc = self.docs.get(run_id)
        if doc is None:
            return
        if doc.error is None or doc.status != "failed":
            doc.error = str(message)
            doc.status = "failed"
        doc.pending_interrupt = None
        # 先摘队列（否则 release 可能把槽"交回"给刚失败的自己），再释放槽（幂等）。
        for slot_id in self._slot_job_ids_for(run_id):
            try:
                self.admission.cancel_pending(slot_id)
            except Exception:  # pragma: no cover
                pass
            try:
                self.admission.release(job_id=slot_id, handoff=True)
            except Exception:  # pragma: no cover
                pass
        ctx = self.ctxs.get(run_id)
        if ctx is not None:
            ctx.event(
                "warning", node="lifecycle", status="failed",
                detail={"message": str(message),
                        "rule": "失败必须显式收敛：status=failed + error + 清 pending + 关闭执行；"
                                "不得把崩溃伪装成'在等人工'"},
            )
        self._persist(run_id)
        await self._close_execution(run_id, reason=reason)

    def _last_node_failure(self, events: list[dict[str, Any]]) -> str | None:
        for event in reversed(events):
            if event.get("kind") == "node_failed":
                detail = event.get("detail") or {}
                node = event.get("node")
                msg = detail.get("message") or event.get("status")
                return f"{node}: {msg}" if node else str(msg)
        return None

    # ---------------- 启动 ----------------

    async def start(
        self,
        *,
        baseline: str | None = None,
        mode: str = "drill",
        scenario: str = "happy",
        now: str | None = None,
        project: str | None = None,
    ) -> str:
        if mode not in ("drill", "real"):
            raise ValueError("mode 必须是 drill 或 real")
        # 基线准入（编排规格 §3.1）：real 必须在**建运行目录 / 隔离残留投影 / 写事件流 /
        # 申请单槽之前**拒绝；判据只有 host/baseline.py 一处，API 层不重复校验。
        # drill 走夹具、不读基线资产，因此不做准入，但也不得据此声称基线已验证。
        from host import baseline as baseline_host

        baseline_id = baseline_host.normalize(baseline)
        if mode == "real":
            baseline_host.require(P.KB_DIR, baseline_id)
        # `now` 原本只声明不使用：HTTP 传了 `now`、`/api/runs` 也照收，
        # 但 run_id 与时间戳实际都来自 `LOOP_NOW`/`KB_NOW` 环境变量 ⇒ **静默忽略调用方的身份意图**。
        # 对交互式使用是实打实的坑：调用方以为定住了 run 身份，实际拿到另一个 run。
        # 现在显式生效，且优先级高于环境变量（更具体者胜）。
        dt: datetime | None = None
        if now:
            try:
                dt = datetime.fromisoformat(str(now))
            except ValueError as exc:
                raise ValueError(f"now 不是可解析的 ISO 时间：{now!r}") from exc
        run_id = P.make_run_id(dt)
        if (P.KB_RUNS / run_id / "gates.json").is_file() or (P.KB_RUNS / run_id / "view.json").is_file():
            # run_id 已存在 ⇒ 复用会污染闸门账本与事件流。
            # 实证：同一 LOOP_NOW 二次启动会让 gate_history 出现重复条目、事件 seq 续写。
            raise FileExistsError(
                f"运行目录 {run_id} 已存在；run_id 必须唯一（检查 LOOP_NOW/KB_NOW 是否被固定）。"
            )
        # 运行目录已被清理、但事件流/恢复快照还留着同名件 ⇒ 新 run 的事件流会混进上一轮的
        # gate_decided（"闸门被签过"的假象，实测：两个测试同秒拿到同一 run_id）。
        # 这两者是**投影件**（不是权威），把它隔离到 `.stale-<ts>` 保留追溯，新 run 从干净的
        # 事件流/快照开始；隔离失败则 fail closed（绝不覆盖）。
        quarantined: list[str] = []
        for stale in (P.EVENTS_DIR / f"{run_id}.jsonl", P.RECOVERY_DIR / f"{run_id}.json"):
            if not stale.is_file():
                continue
            target = stale.with_name(f"{stale.name}.stale-{int(time.time() * 1000)}")
            try:
                os.replace(stale, target)
            except OSError as exc:
                raise FileExistsError(
                    f"run 身份 {run_id} 的残留投影 {stale} 无法隔离（{exc}）⇒ 拒绝复用该身份。"
                ) from exc
            quarantined.append(str(target))
        run_dir = prepare_run_dir(run_id, mode=mode)
        progress = self._progress(run_id)
        ctx = RunCtx(
            run_id=run_id,
            run_dir=run_dir,
            mode=mode,
            scenario=scenario,
            kb=self.kb,
            progress=progress,
            admission=self.admission,
            runner=self.runner,
            pending={"rework_limit": REWORK_LIMIT},
        )
        doc = RunDoc(
            run_id=run_id,
            run_dir=str(run_dir),
            baseline=baseline_id,
            project=project or str(P.ENV_ROOT),
            mode=mode,
            scenario=scenario,
            created_at=P.now_iso(dt),
            updated_at=P.now_iso(dt),
        )
        if quarantined:
            doc.notes.append(
                "隔离了同 run 身份的残留投影件（运行目录已不存在，事件流/快照不得续写）："
                + "；".join(quarantined)
            )
        self.docs[run_id] = doc
        progress.append(
            "run_started",
            detail={"baseline": doc.baseline, "project": doc.project, "mode": mode,
                    "scenario": scenario, "drill_fixture": str(ctx.fixture)},
        )

        execution = LOOP_FLOW.create_execution(
            auto_close=False,
            runtime_resources={**runtime_resources(ctx), "repo_root": str(self.repo_root)},
        )
        self.executions[run_id] = execution
        self.ctxs[run_id] = ctx
        self._persist(run_id)
        self.start_watching()

        try:
            await execution.async_start(
                {"baseline": doc.baseline, "mode": mode, "scenario": scenario, "rework_limit": REWORK_LIMIT}
            )
        except Exception as exc:  # 单节点失败不得掀翻服务
            # I3：start 异常同样必须**显式收敛并关闭执行**，不能留下永不收敛的 execute。
            await self._fail_run(run_id, f"{type(exc).__name__}: {exc}")
            return run_id
        await self.async_sync(run_id)
        return run_id

    # ---------------- 同步投影 ----------------

    async def async_sync(self, run_id: str) -> dict[str, Any]:
        doc = self.docs[run_id]
        ctx = self.ctxs.get(run_id)
        execution = self.executions.get(run_id)
        events = self._progress(run_id).read()

        if execution is not None:
            try:
                waiting = execution.is_waiting()
            except Exception:
                waiting = False
            # I2：框架自己的状态是**权威之一**。只判 is_waiting/is_closed 时，
            # 框架把执行置 FAILED 的三者皆假 ⇒ run 永远 running、ticker 永久巡检、
            # 重启还会当 running 再恢复一遍（僵尸 run）。
            try:
                exec_status = execution.get_status()
            except Exception:
                exec_status = None
            if doc.error:
                # 失败优先于等待：执行失败后 is_waiting() 可能仍为真，
                # 若把 failed 显示成 waiting_gate，就等于把崩溃伪装成"在等人工"。
                doc.status = "failed"
                doc.pending_interrupt = None
                await self._close_execution(run_id, reason="run_failed")
            elif exec_status == "failed":
                detail = self._last_node_failure(events)
                await self._fail_run(run_id, f"执行被框架置为 failed：{detail or '见事件流/日志'}")
                return doc.as_dict()
            elif exec_status == "cancelled":
                await self._fail_run(run_id, "执行被取消 ⇒ 本轮终止（不得当作完成）。")
                return doc.as_dict()
            elif waiting:
                pending = execution.get_pending_interrupts() or {}
                doc.pending_interrupt = next(iter(pending.values())) if pending else None
                # I18：区分在等闸门/等作业/等单槽，界面不再一律显示"等你决策"。
                doc.status = self._wait_status(pending)
            elif execution.is_closed() or exec_status == "completed":
                doc.status = "finished"
                doc.pending_interrupt = None
            elif reached_terminal(events):
                # 走到无后继的节点（HALT / N16）且没有待处理中断 ⇒ 本轮结束。
                # 必须**显式**关执行，否则 `is_closed()` 永远为假（auto_close=False）。
                doc.status = "finished"
                doc.pending_interrupt = None
                await self._close_execution(run_id, reason="terminal_node_reached")
            else:
                doc.status = "running"
                doc.pending_interrupt = None
        doc.updated_at = P.now_iso()

        # 停在中断上时落一次快照：此刻执行非 running，save 合法且可 load。
        # **且必须是干净停车**（见 `_is_clean_park`）：半截快照会毒化下一次恢复。
        # 闸门/作业/单槽三种停放都要落盘（I18 拆分后不能只认 waiting_gate）。
        if execution is not None and str(doc.status).startswith("waiting"):
            if self._is_clean_park(execution):
                try:
                    execution.save(self._snapshot_path(run_id), require_idle=True)
                except Exception as exc:
                    state = f"snapshot 失败：{type(exc).__name__}: {exc}"
                    if state not in doc.notes:
                        doc.notes.append(state)

        self._persist(run_id)

        if ctx is not None and ctx.pending.get("n9_job_id"):
            job_id = ctx.pending["n9_job_id"]
            try:
                self.runner.poll(job_id)
            except KeyError:
                pass
        return doc.as_dict()

    # ---------------- 闸门决策 ----------------

    async def decide(
        self,
        *,
        run_id: str,
        gate: str,
        decision: str,
        actor: str,
        reason: str | None = None,
        resume_request_id: str | None = None,
        entry_decisions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """提交一次闸门决策。

        顺序（spec §5.8 「拒绝必须发生在提交前」）：
        ① 静态校验（闸门/枚举/可提交/actor）；② 业务前置（I1/I2/A2/I4）；
        ③ 确认**本门确有待处理中断**；④ 才签权威账本；⑤ 恢复执行。

        ④ 之后若恢复失败（chunk 抛错 / resume 被拒），必须**显式 failed + error + 关闭执行**
        （B4）：旧实现无 try/except ⇒ 中断已被消费、账本留孤儿签名、run 停在
        `waiting_gate` 但没有任何中断，既不能重签也不能续跑。
        """
        if gate not in GA.gate_ids():
            raise ValueError(f"未知闸门 {gate!r}；权威闸门 = {list(GA.gate_ids())}")
        if not GA.is_valid_decision(gate, decision):
            raise ValueError(
                f"闸门 {gate} 不接受决策 {decision!r}；权威枚举（kb_lib.GATE_DECISIONS）= "
                f"{list(GA.decisions().get(gate, ()))}"
            )
        if decision in GA.NON_ACTIONABLE:
            raise ValueError(f"{decision!r} 是状态而非可提交动作；请选择一个实际决策。")
        if not actor or not str(actor).startswith("human"):
            # I6：模型/演练 actor 不得越过闸门（与 kb/tools/gate.py 的 require-signed 一致）
            raise PermissionError("I6：闸门决策只接受 human actor（actor 必须以 'human' 开头）")

        execution = self.executions.get(run_id)
        if execution is None:
            raise KeyError(f"运行 {run_id} 不在本进程内（需先恢复）")
        doc = self.docs[run_id]
        run_dir = Path(doc.run_dir)

        # ② **提交前**业务前置（I1/I2/A2/I4 的唯一实现，与 `gates._resumed` 共用）：
        # 若放到恢复之后，用户的一次误选就会消耗掉中断（`max_resumes=1`）并把执行打成
        # failed —— 闸门从此不可用（实测踩过 `self_resume_limit_reached`）。
        try:
            pre = gate_chunks.precheck_decision(
                gate=gate,
                decision=decision,
                run_dir=run_dir,
                mode=doc.mode,
                reason=reason,
                kb=self.kb,
                entry_decisions=entry_decisions,
            )
        except gate_chunks.GatePreconditionFailed:
            raise

        # ③ **必须先确认本闸门确有待处理中断，再去写权威账本。**
        # 实测（v1 终验 phase 1）：原顺序是「先 `gate.py sign` 落权威、后查中断」，
        # 于是当闸门已被决策过（典型触发：操作台上双击按钮 / 两个标签页各点一次）时，
        # `gates.json` 会追加一条**孤儿签名**（`history` 变长、账本被改），
        # 而执行侧没有任何动作，用户只看到一个 400 —— 权威与被控对象悄悄分叉。
        pending = execution.get_pending_interrupts() or {}
        interrupt_id = None
        for key, item in pending.items():
            payload = (item or {}).get("payload") or {}
            if payload.get("gate") == gate or str(key).startswith(gate):
                interrupt_id = key
                break
        if interrupt_id is None:
            raise KeyError(
                f"闸门 {gate} 当前没有待处理中断（可能已被决策，或执行未停在该闸门）；"
                f"未写权威账本。pending={list(pending)}"
            )

        from .chunks.host_steps import run_kb_tool

        # ④ 签署：绑定**本轮证据指纹**（A17），让闸门决策可回指本轮产物。
        args = ["sign", gate, "--run", run_id, "--decision", decision,
                "--actor", actor, "--actor-kind", "human"]
        if reason:
            args += ["--note", reason]
        for artifact in gate_chunks.gate_artifacts(run_dir, gate):
            args += ["--artifact", artifact]
        signed = run_kb_tool("gate.py", args)
        if signed["rc"] != 0:
            raise PermissionError(
                f"闸门签署被 kb/tools/gate.py 拒绝（rc={signed['rc']}）：{signed['stderr_tail'][-400:]}"
            )

        # ⑤ 恢复：**失败必须显式收敛**（B4/C8）。恢复载荷里的逐条处置同时投递，
        # 让 `gates._resumed` 的纵深防御读到与本层 precheck 相同的输入。
        payload = {
            "decision": decision,
            "actor": actor,
            "reason": reason,
            "entry_decisions": pre.get("entries") or {},
        }
        request_id = resume_request_id or f"{run_id}:{interrupt_id}"
        try:
            await execution.async_continue_with(
                interrupt_id, payload, resume_request_id=request_id, actor=actor
            )
        except Exception as exc:
            await self._fail_run(
                run_id,
                f"闸门 {gate} 已签署但恢复失败（决策 {decision}）：{type(exc).__name__}: {exc}；"
                "run 已显式 failed 并关闭执行（账本里的本次签名视为未生效，需人工确认后重开一轮）。",
                reason="gate_resume_failed",
            )
            raise RuntimeError(
                f"闸门 {gate} 已签署但恢复失败（run 已置 failed）：{type(exc).__name__}: {exc}"
            ) from exc

        # 框架被拒时 `async_continue_with` 只打日志、不抛错 ⇒ 必须复核中断是否真被消费。
        if interrupt_id in (execution.get_pending_interrupts() or {}):
            await self._fail_run(
                run_id,
                f"闸门 {gate} 恢复未生效：中断 {interrupt_id} 仍在等待（resume 被去重或拒绝）；"
                "已签决策未生效，run 已显式 failed。",
                reason="gate_resume_not_effective",
            )
            raise RuntimeError(
                f"闸门 {gate} 恢复未生效：中断 {interrupt_id} 仍在等待；run 已置 failed"
            )

        await self.async_sync(run_id)
        doc = self.docs[run_id]
        if doc.status == "failed":
            # 闸门**已签署**，失败发生在恢复后的执行里（典型：drill 死任务在 continue 的
            # 同一次调用内就被判死，n9_park 因此失败）。此时 HTTP 不能报 500：客户端会
            # 误以为「没签成功」而重试，但中断已被消费 ⇒ 只能拿到 409，权威/被控对象分叉。
            # 正确做法：200 + `execution_failed=true` + 真实 error，让操作台把 run 显示为 failed。
            return {"ok": True, "gate": gate, "decision": decision, "sign": signed,
                    "entries": pre.get("entries") or {}, "warnings": pre.get("warnings") or [],
                    "execution_failed": True, "status": doc.status, "error": doc.error}
        return {"ok": True, "gate": gate, "decision": decision, "sign": signed,
                "entries": pre.get("entries") or {}, "warnings": pre.get("warnings") or [],
                "status": doc.status}

    # ---------------- 作业取消 ----------------

    def cancel_job(self, run_id: str, job_id: str) -> dict[str, Any]:
        ok = self.runner.cancel(job_id)
        ctx = self.ctxs.get(run_id)
        if ctx is not None:
            ctx.event("warning", node="N9", status="cancel_requested", detail={"job_id": job_id})
        return {"ok": ok, "job_id": job_id}

    # ---------------- 完成投递桥 ----------------

    async def _deliver(self, status: dict[str, Any], *, force: bool = False) -> None:
        """把作业结局投递给停在 `JOB:` 中断上的执行。

        `force=True` 时跳过"已投递"守卫 —— 只给**恢复陈旧快照**用：那时作业早已跑完并投递过，
        但盘上的快照还停在 JOB 中断（落盘发生在投递之前），若不强制重投递，run 会**永久卡住**
        （没有任何补投递会再来）。重投递只是读取已跑完作业的结局，**不重跑外部作业**。
        """
        record = status.get("record") or {}
        run_id = record.get("run_id")
        job_id = status.get("job_id")
        execution = self.executions.get(run_id)
        if execution is None:
            return
        if not force:
            # 幂等 + 防并发：同一作业只投递一次（看护任务与补投递可能同时看到它）
            if record.get("delivered") or job_id in self._delivering:
                return
            latest = self.runner.record(str(job_id)) or {}
            if latest.get("delivered"):
                return
        self._delivering.add(str(job_id))
        pending = execution.get_pending_interrupts() or {}
        interrupt_id = None
        for key, item in pending.items():
            payload = (item or {}).get("payload") or {}
            if payload.get("job_id") == job_id or str(key) == f"JOB:{job_id}":
                interrupt_id = key
                break
        if interrupt_id is None:
            # M12：找不到匹配中断不能静默 return —— 说明执行不在等这个作业，
            # 必须留下显式告警（否则"投递丢了"这件事在事件流里完全不可见）。
            self._delivering.discard(str(job_id))
            ctx = self.ctxs.get(run_id)
            if ctx is not None:
                ctx.event("warning", node="lifecycle", status="deliver_no_interrupt",
                          detail={"job_id": job_id, "phase": status.get("phase"),
                                  "pending": sorted(str(k) for k in pending),
                                  "rule": "作业已终结但执行并未停在它的 JOB 中断上 ⇒ 显式告警，不静默"})
            return
        base_req = f"{job_id}:{status.get('phase')}:{status.get('rc')}"
        if force:
            # 必须换新 id：旧 id 已被上一代进程消费掉，复用会被去重逻辑拒绝
            self._redeliver_n += 1
            request_id = f"{base_req}:restore:{self._boot_id}:{self._redeliver_n}"
        else:
            request_id = base_req
        await execution.async_continue_with(
            interrupt_id,
            {"job_id": job_id, "phase": status.get("phase"), "rc": status.get("rc")},
            resume_request_id=request_id,
            actor="host:job_runner",
        )
        # **核验执行体**：`async_continue_with` 在被拒时只打日志、不抛错（实测），
        # 若只看返回值就会把"没投成"当成功并 mark_delivered ⇒ run 永久卡住。
        if interrupt_id in (execution.get_pending_interrupts() or {}):
            self._delivering.discard(str(job_id))
            raise RuntimeError(
                "投递未生效：中断 %s 仍在等待（resume 被拒或未被消费）⇒ 不标记已投递"
                % interrupt_id
            )
        self.runner.mark_delivered(job_id, resume_request_id=request_id)
        self._delivering.discard(str(job_id))
        await self.async_sync(run_id)

    async def _watch_loop(self) -> None:
        async def on_finished(status: dict[str, Any]) -> None:
            try:
                await self._deliver(status)
            except Exception as exc:
                record = status.get("record") or {}
                run_id = record.get("run_id")
                if run_id and run_id in self.docs:
                    # 投递失败 = 本轮无法收敛：必须 failed+error+关闭执行，
                    # 不能只写 error 却继续显示"在等作业"（把崩溃伪装成等待）。
                    await self._fail_run(
                        run_id,
                        f"投递失败：{type(exc).__name__}: {exc}",
                        reason="deliver_failed",
                    )

        await self.runner.watch(on_finished=on_finished, interval=0.5)

    def start_watching(self) -> None:
        if self._watch_task is None or self._watch_task.done():
            self.runner._stopping = False
            self._watch_task = asyncio.create_task(self._watch_loop())
        # 快照不能靠"碰巧"：`async_sync()` 只在 start/decide/_deliver 结尾被调用，
        # 而这三处都可能正好看到执行在跑 ⇒ 该落的快照没人落。
        # 实测（F-V1-06）：happy drill 从 G1 一路跑到 G2 只用约 1.3 s，两次 `async_sync`
        # 都看到 `running`，于是**盘上只剩 G1 那一份快照**：重启后 run 回退到一个
        # **权威账本里已经签过**的闸门（`pending=['G1_diff_confirm:0']`）⇒ 恢复即卡死。
        # 这里按固定节拍巡检，保证"停在中继上"的执行在 ~0.5 s 内落盘。
        if self._snap_task is None or self._snap_task.done():
            self._snap_task = asyncio.create_task(self._snapshot_ticker())

    async def _snapshot_ticker(self) -> None:
        while not self.runner._stopping:
            for rid, doc in list(self.docs.items()):
                if doc.status in ("finished", "failed"):
                    continue
                try:
                    await self.async_sync(rid)
                except Exception:
                    pass
            # 0.2s：窗口越小，"停机落在两次落盘之间"的概率越低（但**不消除**，见 §4.6）
            await asyncio.sleep(0.2)

    async def stop_watching(self) -> None:
        self.runner.stop_watching()
        for attr in ("_watch_task", "_snap_task"):
            task = getattr(self, attr)
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
                setattr(self, attr, None)

    # ---------------- 重启恢复 ----------------

    @staticmethod
    def _is_clean_park(execution: Any) -> bool:
        """快照只许拍**干净的停车**：所有 waiting 中断都还没被派发（`resume_count < max`）。

        实测踩过：0.5s 节拍会拍到"已派发但接管尚未开始"的半截快照 ——
        中断 `status='waiting'` 而 `resume_count` 已等于 `max_resumes`。
        这种快照 load 得进来，但恢复时既不能重投递（"is not waiting"），
        也不会自己往下走 ⇒ 只能失败。**宁可不落盘，也不落一张半截快照**
        （保留上一张干净快照，由下游的"陈旧快照"两条规则去处置）。
        """
        for item in (execution.get_pending_interrupts() or {}).values():
            it = item or {}
            if it.get("status") not in (None, "waiting"):
                continue
            mx, cnt = it.get("max_resumes"), it.get("resume_count") or 0
            if mx is not None and cnt >= mx:
                return False
        return True

    def _stale_job_interrupts(self, execution: Any) -> list[tuple[str, str, str]]:
        """停在**已终结**作业的中断上 ⇒ 快照陈旧（落盘发生在投递之后又被回退）。

        返回 `[(interrupt_id, job_id, phase)]`。作业相位一律回读 `JobRunner.poll()`
        （rc 文件 + 进程存活 = 权威），不看快照里记了什么。
        """
        out: list[tuple[str, str, str]] = []
        for key, item in (execution.get_pending_interrupts() or {}).items():
            it = item or {}
            # 半截中断（已派发完）不可恢复 ⇒ 不算"陈旧作业"，免得强制投递必然失败
            mx, cnt = it.get("max_resumes"), it.get("resume_count") or 0
            if mx is not None and cnt >= mx:
                continue
            job_id = (it.get("payload") or {}).get("job_id")
            if not job_id:
                continue
            try:
                phase = self.runner.poll(str(job_id)).phase
            except Exception:
                continue
            if phase in ("done", "dead", "cancelled"):
                out.append((str(key), str(job_id), str(phase)))
        return out

    def _snapshot_behind_ledger(self, run_id: str, execution: Any) -> str | None:
        """恢复后与**权威账本**对账：若停在"账本已签"的闸门上，快照就是落后的 ⇒ 显式失败。

        实测（F-V1-06）：崩溃若落在两次落盘之间，载入的快照会回退到上一个闸门，而该闸门在
        `gates.json` 里**已经签过** ⇒ run 永远停在那里（既不能重签，也不会自己往前走）。

        **这里刻意不自动重放该决定**：重放 = 自动重跑一轮修订 + 仿真（可能是几十分钟的外部
        作业），而且是在人没要求的情况下。按本层一贯口径 —— 宁可显式失败，也不静默替人推进。
        """
        try:
            auth = GA.authority_view(run_id)
        except Exception:
            return None
        if auth.get("present") is not True:
            return None
        for key, item in (execution.get_pending_interrupts() or {}).items():
            gate = ((item or {}).get("payload") or {}).get("gate")
            if not gate:
                continue
            info = (auth.get("gates") or {}).get(gate) or {}
            if info.get("status") == "signed" and info.get("decision") not in (None, "pending"):
                return (
                    f"快照落后于权威账本：快照停在闸门 {gate}（中断 {key}），但 gates.json 里该闸门"
                    f"已是 {info.get('decision')!r}（actor={info.get('actor')!r}）。照快照继续会重复"
                    "签署/重复跑一轮 ⇒ 按失败处理；请人工确认后重开一轮。"
                )
        return None

    async def async_restore_all(self) -> dict[str, Any]:
        """崩溃重启后：重新判定作业命运 + 从快照恢复执行 + **复验外部租约**。

        - 快照里若有 `running` 帧，`load` 会 fail-closed（恢复前必须已停放）；
        - `undelivered` 的作业会被补投递（幂等靠 `resume_request_id`）；
        - 单槽/作业是**外部系统**，spec §8.5 要求恢复时重新验证 lease/fence 后才算 ready
          （B5：旧实现从不复核本 run 是否仍持锁）。
        """
        buckets = self.runner.reattach()
        restored: list[str] = []
        failed: list[dict[str, str]] = []
        #: 停在陈旧快照上的作业：job_id -> 权威相位（需要**强制**重投递）
        stale_jobs: dict[str, str] = {}

        for run_id, doc in list(self.docs.items()):
            if doc.status not in ("waiting_gate", "waiting_job", "waiting_slot", "running"):
                continue
            snap = self._snapshot_path(run_id)
            if not snap.is_file():
                # I1：无快照 ⇒ **显式失败**（旧实现只 append 进报告，doc 永远停在
                # "在等你决策"/running ⇒ 僵尸 run 会被每次重启反复恢复）。
                await self._fail_run(run_id, f"恢复失败：无快照（{snap}）⇒ 无法续跑；"
                                            "已显式 failed，请人工确认后重开一轮。",
                                      reason="restore_no_snapshot")
                failed.append({"run_id": run_id, "reason": "无快照"})
                continue
            run_dir = Path(doc.run_dir)
            ctx = RunCtx(
                run_id=run_id,
                run_dir=run_dir,
                mode=doc.mode,
                scenario=doc.scenario,
                kb=self.kb,
                progress=self._progress(run_id),
                admission=self.admission,
                runner=self.runner,
            )
            execution = LOOP_FLOW.create_execution(
                auto_close=False,
                runtime_resources={**runtime_resources(ctx), "repo_root": str(self.repo_root)},
            )
            try:
                await execution.async_load(
                    json.loads(snap.read_text(encoding="utf-8")),
                    runtime_resources={**runtime_resources(ctx), "repo_root": str(self.repo_root)},
                )
            except Exception as exc:
                # I1：load 异常 ⇒ 显式 failed + error + 清 pending + close。
                await self._fail_run(
                    run_id,
                    f"恢复失败：async_load 异常 {type(exc).__name__}: {exc}（快照 {snap}）",
                    reason="restore_load_failed",
                )
                failed.append({"run_id": run_id, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            self.executions[run_id] = execution
            self.ctxs[run_id] = ctx
            ctx.event("warning", node="restore", status="restored",
                      detail={"snapshot": str(snap), "undelivered_jobs": len(buckets.get("undelivered", []))})
            # 陈旧快照之一：停在**已终结作业**的中断上 ⇒ 记下来，稍后与正常补投递**走同一条路径**
            # 强制重投递（不重跑外部作业，只读取已存在的结局）。
            # 刻意不在这里自行投递：两条投递路径各带一套错误处理，就必然出现
            # "一条把异常吞掉、另一条设 doc.error" 的分裂（实测把死任务路径弄坏过一次）。
            for _key, jid, jphase in self._stale_job_interrupts(execution):
                stale_jobs[jid] = jphase
                ctx.event("warning", node="restore", status="stale_snapshot_redeliver",
                          detail={"job_id": jid, "phase": jphase,
                                  "rule": "快照停在已终结作业上 ⇒ 按 JobRunner.poll() 重投递其结局；"
                                          "外部作业不重跑，只读取已存在的结局"})

            # 陈旧快照之二：停在**账本已签**的闸门上（崩溃落在两次落盘之间）⇒ fail closed，
            # 绝不静默重跑一轮（那会重跑修订 + 仿真，可能是几十分钟的外部作业）。
            behind = self._snapshot_behind_ledger(run_id, execution)
            if behind:
                ctx.event("warning", node="restore", status="snapshot_behind_ledger",
                          detail={"reason": behind, "snapshot": str(snap)})
                await self._fail_run(run_id, behind, reason="snapshot_behind_ledger")
                failed.append({"run_id": run_id, "reason": behind})
                continue

            # 外部租约复验（B5 / spec §8.5）：停在 JOB/SLOT 上的 run 必须仍持有单槽，
            # 否则单槽互斥已被破坏（两个仿真并发踩 uvs.setup），fail closed。
            lease_ok = await self._restore_slot_lease(run_id, execution)
            if not lease_ok:
                failed.append({"run_id": run_id, "reason": "单槽租约复验失败"})
                continue
            restored.append(run_id)

        # **补投递必须在 start_watching() 之前**：否则看护任务会与补投递**并发投同一个作业**，
        # 第二个 resume 会被框架拒绝（实测 `resume_dispatch_failed … changed phase`）。
        to_deliver: list[dict[str, Any]] = list(buckets.get("undelivered", []))
        _seen = {str(r.get("job_id")) for r in to_deliver}
        for jid, jphase in stale_jobs.items():
            if jid in _seen:
                continue
            rec = self.runner.record(jid) or {}
            rec = dict(rec)
            rec["phase"] = jphase
            to_deliver.append(rec)

        for record in to_deliver:
            run_id = record.get("run_id")
            if run_id in self.executions:
                try:
                    await self._deliver(
                        {"job_id": record.get("job_id"), "phase": record.get("phase"),
                         "rc": record.get("rc"), "record": record},
                        force=str(record.get("job_id")) in stale_jobs,
                    )
                except Exception as exc:
                    failed.append({"run_id": str(run_id), "reason": f"补投递失败：{exc}"})
                    # **补投递失败必须让 run 失败**，不能只记进报告的 failed[]：
                    # 否则 doc.status 仍停在 `waiting_job`（"在等作业"）而执行其实已经崩了
                    # —— 正是 README §4.3 要防的"把崩溃伪装成在等人工"。
                    await self._fail_run(
                        run_id,
                        f"补投递失败：{type(exc).__name__}: {exc}",
                        reason="redeliver_failed",
                    )

        self.start_watching()
        return {
            "restored": restored,
            "failed": failed,
            "jobs": {k: len(v) for k, v in buckets.items()},
            "job_buckets": {k: [r.get("job_id") for r in v] for k, v in buckets.items()},
        }

    async def _restore_slot_lease(self, run_id: str, execution: Any) -> bool:
        """恢复时**重新验证外部租约**（B5 / spec §8.5）：单槽 + 作业身份。

        - 停在 `JOB:` 上：作业必须仍在跑，且单槽必须归本 run；锁丢失 ⇒ 按作业记录**重建**租约；
          锁被别人持有 ⇒ 单槽互斥已被破坏，显式失败（绝不并发踩 `uvs.setup`）。
        - 停在 `SLOT:` 上：本 run 在等槽 ⇒ 锁空则重建并唤醒；已给本 run 但没醒则补唤醒；
          别人持有则确保自己在队列里。
        """
        try:
            pending = execution.get_pending_interrupts() or {}
        except Exception:  # pragma: no cover
            return True
        slot_id = slot_job_id("N9", run_id)

        for key, item in pending.items():
            if not str(key).startswith("JOB:"):
                continue
            payload = (item or {}).get("payload") or {}
            job_id = payload.get("job_id")
            if not job_id:
                continue
            rec = self.runner.record(str(job_id)) or {}
            phase = self.runner.phase_of(str(job_id))
            if phase not in ("running", "cancelling"):
                # 已终结（或未知）⇒ 让补投递路径按权威相位处置，不在这里抢租约。
                return True
            holder = self.admission.holder() or {}
            holder_job = holder.get("job_id")
            if holder_job not in (None, slot_id):
                await self._fail_run(
                    run_id,
                    f"恢复租约复验失败：N9 作业 {job_id} 仍在跑（phase={phase}），"
                    f"但单槽被 {holder_job!r} 持有 ⇒ 单槽互斥已被破坏，拒绝并发仿真。",
                    reason="lease_conflict",
                )
                return False
            if holder_job is None:
                result = self.admission.acquire(
                    job_id=slot_id,
                    tc=payload.get("tc") or rec.get("tc"),
                    seed=payload.get("seed") or rec.get("seed"),
                    job_pid=int(rec["pid"]) if rec.get("pid") else None,
                    job_pid_start=rec.get("pid_start"),
                    note="restore_lease",
                )
                if result.granted:
                    self.admission.bind_job(
                        slot_job_id=slot_id, job_id=str(job_id),
                        job_pid=int(rec["pid"]) if rec.get("pid") else 0,
                        job_pid_start=rec.get("pid_start"),
                        job_record_id=str(job_id),
                    )
                ctx = self.ctxs.get(run_id)
                if ctx is not None:
                    ctx.event("admission_granted", node="N9", status="restore_lease",
                              detail={"job_id": slot_id, "state": result.state,
                                      "reason": result.reason})
                if not result.granted:
                    await self._fail_run(
                        run_id,
                        f"恢复租约复验失败：作业 {job_id} 仍在跑，但无法重建单槽租约"
                        f"（{result.state}: {result.reason}）",
                        reason="lease_rebuild_failed",
                    )
                    return False
            elif rec.get("pid"):
                # 锁还在但作业身份可能未绑定（v1 旧锁）⇒ 补绑，让判活走作业 pid/相位。
                self.admission.bind_job(
                    slot_job_id=slot_id, job_id=str(job_id),
                    job_pid=int(rec["pid"]), job_pid_start=rec.get("pid_start"),
                    job_record_id=str(job_id),
                )
            return True

        for key, item in pending.items():
            if not str(key).startswith("SLOT:"):
                continue
            payload = (item or {}).get("payload") or {}
            holder = self.admission.holder() or {}
            holder_job = holder.get("job_id")
            if holder_job == slot_id:
                # 锁已交给我们但执行没醒（进程恰好死在交接触发点）⇒ 补唤醒。
                self._on_slot_handoff({"job_id": slot_id, "tc": None, "seed": None})
                return True
            result = self.admission.acquire(
                job_id=slot_id,
                tc=payload.get("tc"),
                seed=payload.get("seed"),
                note="restore_queue",
            )
            ctx = self.ctxs.get(run_id)
            if ctx is not None:
                ctx.event("admission_queued", node="N9", status="restore",
                          detail={"state": result.state, "position": result.position,
                                  "reason": result.reason})
            if result.granted:
                self._on_slot_handoff({"job_id": slot_id, "tc": payload.get("tc"),
                                       "seed": payload.get("seed")})
            return True
        return True

    # ---------------- 对外视图 ----------------

    def _job_view(self, run_id: str) -> dict[str, Any] | None:
        ctx = self.ctxs.get(run_id)
        records = [r for r in self.runner.all_records() if r.get("run_id") == run_id]
        if not records:
            return None
        # 取**开始时刻最新**的那个作业，不能取 `records[-1]`：`all_records()` 是按
        # `JOB-<hex>` 文件名字典序排的，与时间顺序无关（hex 大小随机）。
        # 实测（verifier F-V1-06-FLAKY）：一个 run 有两次作业记录时（返工回边会重跑 N9），
        # 看板可能显示**上一个**作业，而执行其实停在新的那个上 ⇒ 界面与执行对不上。
        record = max(records, key=lambda r: r.get("started_at") or 0.0)
        job_id = str(record["job_id"])
        try:
            status = self.runner.poll(job_id)
            phase, rc = status.phase, status.rc
        except KeyError:
            phase, rc = record.get("phase"), record.get("rc")
        started = record.get("started_at") or 0.0
        import time as _t

        elapsed = max(0.0, (record.get("finished_at") or _t.time()) - started)
        eta = contracts.eta_for(record.get("sim_time_us"))
        return {
            "job_id": job_id,
            "node": record.get("node"),
            "phase": phase,
            "rc": rc,
            "tc": record.get("tc"),
            "seed": record.get("seed"),
            "started_at": started,
            "elapsed_s": round(elapsed, 1),
            "eta_seconds": eta["eta_seconds"],
            "eta_human": eta["eta_human"] if eta["eta_seconds"] else "未知（本作业未登记仿真时长）",
            "basis": eta["basis"] or f"实测模型 {contracts.SIM_US_PER_WALL_S} µs sim / 1 s wall（n={contracts.SIM_US_PER_WALL_S_N}，低置信）",
            "confidence": eta["confidence"],
            "log_path": record.get("log_path"),
            "log_tail": self.runner.tail_log(job_id, lines=12),
            "note": record.get("note"),
        }

    def _evidence_for(self, run_id: str) -> dict[str, Any] | None:
        ctx = self.ctxs.get(run_id)
        if ctx is None:
            doc = self.docs.get(run_id)
            if doc is None:
                return None
            log = Path(doc.run_dir) / "evidence" / "MISSING.log"
        else:
            log = ctx.evidence_log()
        from host.evidence import evidence_view

        ev = evidence_view(log)
        return ev if ev.get("present") else None

    def _status_of(self, doc: RunDoc, execution: Any, events: list[dict[str, Any]]) -> str:
        """投影时**再判一次**状态，不盲信落盘的 `doc.status`。

        为什么：`decide()` 里 `async_continue_with()` 返回后紧接着的 `async_sync()` 有可能
        跑在恢复段真正走完之前；若只信 `doc.status`，HALT/N16 这类终态就会**卡在 running**
        且再没有任何东西会来纠正它。这里用事件流兜底：最后一个节点事件是终止节点的
        `node_finished`、且当前没有待处理中断 ⇒ 就是 `finished`。

        C13/I2：`doc.error` 与**框架状态**优先于 `doc.status`（失败不得被投影成等待）。
        I18：等待态按中断类型区分（闸门/作业/单槽）。
        """
        if doc.error:
            return "failed"
        if execution is None:
            return doc.status
        try:
            exec_status = execution.get_status()
        except Exception:
            exec_status = None
        if exec_status == "failed":
            return "failed"
        if exec_status in ("cancelled",):
            return "failed"
        try:
            if execution.is_waiting():
                return self._wait_status(execution.get_pending_interrupts() or {})
            if execution.is_closed() or exec_status == "completed" or reached_terminal(events):
                return "finished"
        except Exception:
            return doc.status
        return doc.status

    def run_view(self, run_id: str) -> dict[str, Any]:
        doc = self.docs.get(run_id)
        if doc is None:
            raise KeyError(run_id)
        events = self._progress(run_id).read()
        execution = self.executions.get(run_id)
        pending = None
        if execution is not None:
            try:
                if execution.is_waiting():
                    p = execution.get_pending_interrupts() or {}
                    pending = next(iter(p.values())) if p else None
            except Exception:
                pending = None
        payload = doc.as_dict()
        payload["status"] = self._status_of(doc, execution, events)
        payload["pending_interrupt"] = pending or doc.pending_interrupt
        payload["node_history"] = node_history(events)
        payload["gate_history"] = gate_history(events)

        return contracts.run_view(
            run_doc=payload,
            kb=self.kb,
            slot_status=self.admission.status(),
            job=self._job_view(run_id),
            evidence=self._evidence_for(run_id),
            events=events,
        )

    def list_runs(self) -> list[dict[str, Any]]:
        out = []
        for run_id, doc in sorted(self.docs.items(), reverse=True):
            out.append(
                {
                    "run_id": run_id,
                    "status": doc.status,
                    "mode": doc.mode,
                    "baseline": doc.baseline,
                    "updated_at": doc.updated_at,
                    "current_node": (node_history(self._progress(run_id).read()) or [{}])[-1].get("node"),
                }
            )
        return out


MANAGER: RunManager | None = None


def get_manager() -> RunManager:
    global MANAGER
    if MANAGER is None:
        MANAGER = RunManager()
    return MANAGER
