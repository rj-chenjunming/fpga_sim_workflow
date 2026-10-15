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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from agently import TriggerFlow

from host import gate_authority as GA
from host import paths as P
from host.admission import Admission
from host.job_runner import JobRunner
from host.progress import ProgressLog
from services import contracts
from services.contracts import KbSources

from .chunks.gates import BRANCH_DRIFT, GATE_DECISIONS, GATE_IDS, gate1, gate2, gate3, halt
from .chunks.host_steps import n0_baseline, n1_manifest, n2_diff, n5_impact, n7_compile, n16_promote
from .chunks.long_jobs import n9_park, n9_submit, n15_case, n15_select
from .chunks.model_steps import n10_reconcile, n11_review, n12_report, n3_digest, n6_author, n8_check
from .context import RESOURCE_KEY, RunCtx, prepare_run_dir, runtime_resources

#: 返工上限（I7）。N8 与 N16 都校验；本层只负责把回边**图示化**。
REWORK_LIMIT = 3

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

LOOP_FLOW.when("G1_CONFIRMED").to(n5_impact).to(n6_author).to(n7_compile).to(n8_check)
# 有疑义 / 忽略 ⇒ 不进入修订阶段，闭环显式终止（不假装收敛）
LOOP_FLOW.when("G1_IGNORED").to(halt)
LOOP_FLOW.when("G1_DISPUTED").to(halt)

# 显式回边：N8 退回 ⇒ 回 N6（返工计数由 N6 自增，上限由 N8/N16 校验）
LOOP_FLOW.when("N8_REWORK").to(n6_author)
LOOP_FLOW.when("N8_ESCALATE").to(halt)
LOOP_FLOW.when("N8_PASS").to(n9_submit).to(n9_park).to(n10_reconcile).to(n11_review).to(n12_report).to(gate2)

LOOP_FLOW.when("G2_REWORK").to(n6_author)
LOOP_FLOW.when("G2_ACCEPT").to(gate3)

# N15 的扇出由 for_each 承载。**并发上限=1**：uvs.setup 是仓库根下全局单文件，
# 同工作目录禁止并发（真正的并行只跨机，经 run_tc.py）。
# 四个 G3 决策分支都存在（枚举取自权威，见 chunks/gates.BRANCH_EVENTS 与 BRANCH_DRIFT 自检）。
LOOP_FLOW.when("G3_FULL_NOW").to(n15_select).for_each(concurrency=1).to(n15_case).end_for_each().to(n16_promote)
LOOP_FLOW.when("G3_SUBSET_ONLY").to(n15_select).for_each(concurrency=1).to(n15_case).end_for_each().to(n16_promote)
LOOP_FLOW.when("G3_MILESTONE").to(n15_select).for_each(concurrency=1).to(n15_case).end_for_each().to(n16_promote)
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
        self.kb = KbSources.from_repo(self.repo_root)
        self.admission = Admission(P.STATE_DIR)
        self.runner = JobRunner(P.JOBS_DIR, self.admission)
        self.executions: dict[str, Any] = {}
        self.ctxs: dict[str, RunCtx] = {}
        self.docs: dict[str, RunDoc] = {}
        self._watch_task: asyncio.Task[Any] | None = None
        self._snap_task: asyncio.Task[Any] | None = None
        self._delivering: set[str] = set()
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

    # ---------------- 启动 ----------------

    async def start(
        self,
        *,
        baseline: str | None = None,
        mode: str = "drill",
        scenario: str = "happy",
        now: str | None = None,
    ) -> str:
        if mode not in ("drill", "real"):
            raise ValueError("mode 必须是 drill 或 real")
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
            baseline=baseline or "v0",
            mode=mode,
            scenario=scenario,
            created_at=P.now_iso(dt),
            updated_at=P.now_iso(dt),
        )
        self.docs[run_id] = doc
        progress.append(
            "run_started",
            detail={"baseline": doc.baseline, "mode": mode, "scenario": scenario, "drill_fixture": str(ctx.fixture)},
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
            doc.error = f"{type(exc).__name__}: {exc}"
            doc.status = "failed"
            progress.append("node_failed", node="unknown", status="failed", detail={"message": doc.error})
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
            if doc.error:
                # 失败优先于等待：执行失败后 is_waiting() 可能仍为真，
                # 若把 failed 显示成 waiting_gate，就等于把崩溃伪装成"在等人工"。
                doc.status = "failed"
                doc.pending_interrupt = None
            elif waiting:
                doc.status = "waiting_gate"
                pending = execution.get_pending_interrupts()
                doc.pending_interrupt = next(iter(pending.values())) if pending else None
            elif execution.is_closed():
                doc.status = "finished"
                doc.pending_interrupt = None
            elif reached_terminal(events):
                # 走到无后继的节点（HALT / N16）且没有待处理中断 ⇒ 本轮结束。
                # 必须**显式**关执行，否则 `is_closed()` 永远为假（auto_close=False）。
                doc.status = "finished"
                doc.pending_interrupt = None
                try:
                    await execution.async_close(reason="terminal_node_reached")
                except Exception as exc:
                    doc.notes.append(f"关闭执行失败：{type(exc).__name__}: {exc}")
            else:
                doc.status = "running"
                doc.pending_interrupt = None
        doc.updated_at = P.now_iso()

        # 停在中断上时落一次快照：此刻执行非 running，save 合法且可 load。
        if execution is not None and doc.status == "waiting_gate":
            try:
                execution.save(self._snapshot_path(run_id), require_idle=True)
            except Exception as exc:
                doc.notes.append(f"snapshot 失败：{type(exc).__name__}: {exc}")

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
    ) -> dict[str, Any]:
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

        # **提交前**硬前置：这一点很关键。若把 I4 阻断放到恢复之后，
        # 用户的一次误选就会消耗掉中断（`max_resumes=1`）并把执行打成 failed
        # —— 闸门从此不可用。实测踩过：`self_resume_limit_reached`。
        if gate == "G3_regression_decision" and decision in ("full_now", "subset_only"):
            blocking = [c for c in self.kb.load_conflicts().get("items", []) if c.get("blocks_release")]
            if blocking:
                raise PermissionError(
                    f"I4：冲突未清零（{len(blocking)} 项 blocks_release）⇒ 不得选 {decision}；"
                    "闸门保持待决策，可改选 milestone_only / defer。"
                )

        # **必须先确认本闸门确有待处理中断，再去写权威账本。**
        # 实测（v1 终验 phase 1）：原顺序是「先 `gate.py sign` 落权威、后查中断」，
        # 于是当闸门已被决策过（典型触发：操作台上双击按钮 / 两个标签页各点一次）时，
        # `gates.json` 会追加一条**孤儿签名**（`history` 变长、账本被改），
        # 而执行侧没有任何动作，用户只看到一个 400 —— 权威与被控对象悄悄分叉。
        # 与本层既有的「拒绝必须发生在提交前」（§4.4）同一条纪律。
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

        args = ["sign", gate, "--run", run_id, "--decision", decision, "--actor", actor, "--actor-kind", "human"]
        if reason:
            args += ["--note", reason]
        signed = run_kb_tool("gate.py", args)
        if signed["rc"] != 0:
            raise PermissionError(
                f"闸门签署被 kb/tools/gate.py 拒绝（rc={signed['rc']}）：{signed['stderr_tail'][-400:]}"
            )

        await execution.async_continue_with(
            interrupt_id,
            {"decision": decision, "actor": actor, "reason": reason},
            resume_request_id=resume_request_id or f"{run_id}:{gate}:{decision}",
            actor=actor,
        )
        await self.async_sync(run_id)
        return {"ok": True, "gate": gate, "decision": decision, "sign": signed}

    # ---------------- 作业取消 ----------------

    def cancel_job(self, run_id: str, job_id: str) -> dict[str, Any]:
        ok = self.runner.cancel(job_id)
        ctx = self.ctxs.get(run_id)
        if ctx is not None:
            ctx.event("warning", node="N9", status="cancel_requested", detail={"job_id": job_id})
        return {"ok": ok, "job_id": job_id}

    # ---------------- 完成投递桥 ----------------

    async def _deliver(self, status: dict[str, Any]) -> None:
        record = status.get("record") or {}
        run_id = record.get("run_id")
        job_id = status.get("job_id")
        execution = self.executions.get(run_id)
        if execution is None:
            return
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
            self._delivering.discard(str(job_id))
            return
        request_id = f"{job_id}:{status.get('phase')}:{status.get('rc')}"
        await execution.async_continue_with(
            interrupt_id,
            {"job_id": job_id, "phase": status.get("phase"), "rc": status.get("rc")},
            resume_request_id=request_id,
            actor="host:job_runner",
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
                    self.docs[run_id].error = f"投递失败：{type(exc).__name__}: {exc}"
                    self._persist(run_id)

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
            await asyncio.sleep(0.5)

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
        """崩溃重启后：重新判定作业命运 + 从快照恢复执行。

        - 快照里若有 `running` 帧，`load` 会 fail-closed（恢复前必须已停放）；
        - `undelivered` 的作业会被补投递（幂等靠 `resume_request_id`）。
        """
        buckets = self.runner.reattach()
        restored: list[str] = []
        failed: list[dict[str, str]] = []

        for run_id, doc in list(self.docs.items()):
            if doc.status not in ("waiting_gate", "running"):
                continue
            snap = self._snapshot_path(run_id)
            if not snap.is_file():
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
                failed.append({"run_id": run_id, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            self.executions[run_id] = execution
            self.ctxs[run_id] = ctx
            ctx.event("warning", node="restore", status="restored",
                      detail={"snapshot": str(snap), "undelivered_jobs": len(buckets.get("undelivered", []))})
            # 快照落后于权威账本（崩溃落在两次落盘之间）⇒ fail closed，绝不静默重跑一轮
            behind = self._snapshot_behind_ledger(run_id, execution)
            if behind:
                ctx.event("warning", node="restore", status="snapshot_behind_ledger",
                          detail={"reason": behind, "snapshot": str(snap)})
                doc = self.docs.get(run_id)
                if doc is not None:
                    doc.error = behind
                    doc.status = "failed"
                    doc.pending_interrupt = None
                    self._persist(run_id)
                failed.append({"run_id": run_id, "reason": behind})
                continue
            restored.append(run_id)

        # **补投递必须在 start_watching() 之前**：否则看护任务会与补投递**并发投同一个作业**，
        # 第二个 resume 会被框架拒绝（实测 `resume_dispatch_failed … changed phase`）。
        for record in buckets.get("undelivered", []):
            run_id = record.get("run_id")
            if run_id in self.executions:
                try:
                    await self._deliver(
                        {"job_id": record.get("job_id"), "phase": record.get("phase"),
                         "rc": record.get("rc"), "record": record}
                    )
                except Exception as exc:
                    failed.append({"run_id": str(run_id), "reason": f"补投递失败：{exc}"})
                    # **补投递失败必须让 run 失败**，不能只记进报告的 failed[]：
                    # 否则 doc.status 仍停在 `waiting_gate`（"在等你决策"）而执行其实已经崩了
                    # —— 正是 README §4.3 要防的"把崩溃伪装成在等人工"。
                    doc = self.docs.get(run_id)
                    if doc is not None:
                        doc.error = f"补投递失败：{type(exc).__name__}: {exc}"
                        doc.status = "failed"
                        doc.pending_interrupt = None
                        self._persist(run_id)

        self.start_watching()
        return {
            "restored": restored,
            "failed": failed,
            "jobs": {k: len(v) for k, v in buckets.items()},
            "job_buckets": {k: [r.get("job_id") for r in v] for k, v in buckets.items()},
        }

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
        """
        if doc.error:
            return "failed"
        if doc.status in ("waiting_gate", "finished"):
            return doc.status
        if execution is None:
            return doc.status
        try:
            if execution.is_waiting():
                return "waiting_gate"
            if execution.is_closed() or reached_terminal(events):
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
