"""长任务节点：N9 全跑（提交 + 停放）/ N15 分层回归。

**这是本层最关键的形状**（spec §6）：
N9 不阻塞在 handler 里，而是「申请单槽 → 提交外部作业 → 图停在 `pause_for` 中断」。
理由：快照中若存在 `running` 帧，`load` 会 fail-closed
（`agently-triggerflow/references/recovery.md:75-77`）；一次全跑实测 ≈19 min，
修订后可达 22.8 h，阻塞式 handler 会让重启恢复直接不成立。

本轮修复要点（审计 2026-10-19 §3）：
- **#8 N9（A7）**：目标集不再固定 `tc_pcie_rw_02`，而是从 `n6_applied`（沙箱件 +
  冻结 md5）取全部受影响用例；逐例 `run_guarded.sh --mode full` **串联为单个作业**；
  沙箱缺失 / md5 不符 ⇒ fail closed（禁止回退未修订 TESTLIB）；作业身份头
  （tc/seed/md5）与 n9_job 落账一致。
- **#9 N15（A15/I13）**：真实执行 G3 选出的回归集（本机串行；`run_tc.py` 跨机未接入
  ⇒ 如实登记在状态里）；每用例证据落盘；**删除 `provisional=True` 的冒充**。
- **#13/N15-drill**：drill 下不真跑仿真，但显式标注 `simulated=True`（不是把临时值
  当终值）。
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from host import paths as P

from ..context import RunCtx, ctx_of
from .model_common import counts_text

#: drill 夹具的固定全跑用例（accept_v1 的 117 断言依赖该形状，drill 分支保持不变）
_REAL_CASE = "tc_pcie_rw_02"

#: drill 情景：真实子进程 + 真实产物，只有工作负载是夹具（必须标注 DRILL FIXTURE）。
SCENARIOS = ("happy", "dead_job", "cancel")

#: drill 分支种子（与既有夹具/断言一致）
_SEED = "1"


def _slot_job_id(ctx: RunCtx) -> str:
    return f"N9-{ctx.run_id}"


def _n15_job_id(ctx: RunCtx) -> str:
    return f"N15-{ctx.run_id}"


async def _acquire_slot(data: Any, ctx: RunCtx, *, job_id: str, tc: str,
                        seed: str = _SEED, node: str = "N9") -> dict[str, Any]:
    """申请单槽；排队时停在 `slot_wait` 中断上，用 `resume_to="self"` 重入本 chunk。"""
    assert ctx.admission is not None, "drill/real 运行都必须注入 admission"
    result = ctx.admission.acquire(job_id=job_id, tc=tc, seed=seed)
    if result.granted:
        ctx.event("admission_granted", node=node, status="ok",
                  detail={"job_id": job_id, "reason": result.reason})
        return {"granted": True}
    if result.state == "queued":
        ctx.event("admission_queued", node=node, status="waiting",
                  detail={"position": result.position, "reason": result.reason})
        await data.async_pause_for(
            type="slot_wait",
            interrupt_id=f"SLOT:{ctx.run_id}",
            payload={"queue_position": result.position, "reason": result.reason},
            resume_to="self",
        )
        return {"granted": False, "retry": True, "position": result.position}
    ctx.event("admission_refused", node=node, status="refused",
              detail={"reason": result.reason, "holder": result.holder})
    raise PermissionError(f"单槽准入被拒：{result.reason}（N9-3：不认识的锁格式不得自动清理）")


# ---------------------------------------------------------------- 目标集 / 作业


def _target_cases(data: Any) -> list[dict[str, Any]]:
    """N9 的目标用例集：**只认 N6 冻结的沙箱件**（fail closed，不回退 TESTLIB）。"""
    applied = data.get_state("n6_applied") or {}
    out: list[dict[str, Any]] = []
    for item in applied.get("cases") or []:
        if not item.get("case") or not item.get("sandbox_path"):
            continue
        out.append(
            {
                "case": str(item["case"]),
                "sandbox_path": str(item["sandbox_path"]),
                "md5": str(item.get("md5_after") or ""),
                "file": str(item.get("file") or ""),
            }
        )
    return out


def _md5_file(path: Path) -> str:
    import hashlib

    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_targets(cases: list[dict[str, Any]]) -> None:
    """提交作业前复核：沙箱件必须存在且 md5 == N6 冻结值。"""
    if not cases:
        raise RuntimeError(
            "没有已修订的沙箱用例（n6_applied 为空）⇒ 不得全跑；"
            "禁止回退到未修订的 TESTLIB（审计 A7/B3 fail closed）"
        )
    for item in cases:
        path = Path(item["sandbox_path"])
        if not path.is_file():
            raise FileNotFoundError(f"沙箱用例缺失：{path}（禁止回退 TESTLIB）")
        if item.get("md5"):
            now = _md5_file(path)
            if now != item["md5"]:
                raise RuntimeError(
                    f"{item['case']} 沙箱 md5 已变（{now} != {item['md5']}）⇒ 审的对象 != 跑的对象"
                )


def _serial_guard_command(cases: list[dict[str, Any]], *, sandbox_root: Path,
                          evidence_dir: Path, run_id: str, summary_path: Path) -> str:
    """把「逐用例 run_guarded full」拼成**一个** bash 作业（串行，单槽内）。

    作业自身总是 exit 0：单例 rc 记进 summary，交 N10 三分类（审计 A8 要求
    「跑挂 ⇒ 采证并三分类」而不是直接终止）。基础设施缺失（没有日志）由 park 判失败。
    """
    guard = str(P.KB_TOOLS / "run_guarded.sh")
    lines = [
        "set -u",
        f"mkdir -p {shlex.quote(str(evidence_dir))}",
        ": > " + shlex.quote(str(summary_path)),
    ]
    for item in cases:
        case = item["case"]
        cmd = (
            f"bash {shlex.quote(guard)}"
            f" --case-file {shlex.quote(item['sandbox_path'])}"
            f" --case-name {shlex.quote(case)}"
            f" --seed {_SEED}"
            f" --mode full"
            f" --sandbox-root {shlex.quote(str(sandbox_root))}"
            f" --evidence-dir {shlex.quote(str(evidence_dir))}"
            f" --run {shlex.quote(run_id)}"
        )
        lines.append(f"echo '=== BEGIN {case} ==='")
        lines.append(cmd)
        lines.append("__rc=$?")
        lines.append(
            f"printf '%s|%s\\n' {shlex.quote(case)} \"$__rc\" >> {shlex.quote(str(summary_path))}"
        )
        lines.append(f"echo '=== END {case} rc='\"$__rc\"' ==='")
    lines.append("exit 0")
    return "\n".join(lines)


def _collect_case_logs(evidence_dir: Path, cases: list[str], *, seed: str = _SEED) -> dict[str, Path]:
    """按 run_guarded 的命名约定找每例**权威** run.log（不解析内容，交给 evidence 聚合）。"""
    out: dict[str, Path] = {}
    if not evidence_dir.is_dir():
        return out
    for case in cases:
        candidates = sorted(
            p for p in evidence_dir.glob(f"*_{case}_{seed}_run.log")
            if not p.name.endswith("_guard.log")
        )
        if candidates:
            out[case] = candidates[-1]
    return out


def aggregate_evidence(
    ctx: RunCtx,
    *,
    logs: dict[str, Path],
    cases: list[str],
    expected_md5: dict[str, str],
    seed: str = _SEED,
) -> dict[str, Any]:
    """**唯一**的多用例证据聚合入口（WS-K 提供；本层不解析多种日志格式）。

    TODO(WS-K): `host.evidence.extract_run` / `aggregate_evidence` 就绪后这里直接转发；
    两者都缺失时 **fail closed**（不在这里复制一套日志解析器）。
    单测通过 monkeypatch 本函数注入 fake 聚合结果。
    """
    from host import evidence as E

    # 优先用手上**精确的当轮日志映射**（`_collect_case_logs` 已按时间戳取最新件）：
    # 返工回边会在同一 run_dir 留下上一轮日志，按目录重扫可能把旧证据当本轮。
    agg = getattr(E, "aggregate_evidence", None)
    if callable(agg):
        try:
            return agg(logs, seed=seed, expected_md5=expected_md5, run_id=ctx.run_id)
        except TypeError:
            pass  # 接口形状不同 ⇒ 退回到 run_dir 入口（WS-K 保证至少有一个可用）
    extract = getattr(E, "extract_run", None)
    if callable(extract):
        return extract(ctx.run_dir, cases=cases, expected_md5=expected_md5)
    raise RuntimeError(
        "evidence 聚合接口未就绪（host.evidence.extract_run/aggregate_evidence 均缺失）"
        "⇒ 不得自行解析多份日志；按失败处理"
    )


def _combine_counts(per_case: dict[str, Any]) -> dict[str, Any]:
    """把逐用例 counts 合成看板/N10 用的并列双计数（数字来自聚合结果，不手算新口径）。"""
    k1 = 0
    k2: dict[str, int] = {}
    refs: list[str] = []
    for case, item in per_case.items():
        counts = item.get("counts") or {}
        k1 += int((counts.get("koutou1") or {}).get("value") or 0)
        for key, value in ((counts.get("koutou2") or {}).get("value") or {}).items():
            k2[key] = int(k2.get(key, 0)) + int(value or 0)
        refs.extend((counts.get("koutou1") or {}).get("refs") or [])
        refs.extend((counts.get("koutou2") or {}).get("refs") or [])
    both_zero = k1 == 0 and k2.get("UVM_ERROR") == 0 and k2.get("UVM_FATAL") == 0
    return {
        "koutou1": {"label": "口径一（`*E` 文本行数，逐用例求和）", "value": k1,
                    "zero": k1 == 0, "refs": refs[:8]},
        "koutou2": {"label": "口径二（UVM Report Summary，逐用例求和）", "value": k2,
                    "zero": k2.get("UVM_ERROR") == 0 and k2.get("UVM_FATAL") == 0,
                    "refs": []},
        "both_zero": both_zero,
        "per_case": {case: (item.get("counts") or {}) for case, item in per_case.items()},
        "note": "多用例：两套口径分别取、逐例并列再求和；不得互相替代（spec I3）。",
    }


def _identity_summary(aggregate: dict[str, Any], md5s: dict[str, str]) -> dict[str, Any]:
    ident = aggregate.get("identity") or {}
    mismatches = list(ident.get("mismatches") or [])
    for case, expected in md5s.items():
        got = ((aggregate.get("per_case") or {}).get(case) or {}).get("identity") or {}
        if got.get("case_md5") and expected and got["case_md5"] != expected:
            mismatches.append(f"{case}: 跑的 md5 {got['case_md5']} != 审的 md5 {expected}")
    return {"consistent": bool(ident.get("consistent", not mismatches)) and not mismatches,
            "mismatches": mismatches, "source": ident.get("source")}


# ---------------------------------------------------------------- N9 提交


async def n9_submit(data: Any) -> dict[str, Any]:
    """申请单槽 + 提交全跑作业。**返回后图即停放，执行不再是 `running`。**

    real：一个作业串行跑**全部**受影响用例（目标集取 n6_applied 冻结件）。
    drill：保持既有夹具形态（accept_v1 的断言依赖它）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N9")
    assert ctx.runner is not None
    run_dir: Path = ctx.run_dir
    evidence_dir = run_dir / "evidence"

    if ctx.mode == "drill":
        gate = await _acquire_slot(data, ctx, job_id=_slot_job_id(ctx), tc=_REAL_CASE)
        if gate.get("retry"):
            return {"status": "slot_retry"}
        log_name = f"{ctx.run_id}_tc_pcie_rw_02_1_DRILLFIXTURE.log"
        dest = evidence_dir / log_name
        if ctx.scenario == "dead_job":
            command = "kill -9 $$"          # 无 rc 文件 ⇒ 必须是 dead，不得当成功
        elif ctx.scenario == "cancel":
            command = "sleep 120"
        else:
            src = ctx.fixture / "evidence" / "20261015-125305_tc_pcie_rw_02_1_run.log"
            arch = evidence_dir / "archive"
            arch_copy = arch / dest.name
            prov = arch / "DRILL_FIXTURE_PROVENANCE.txt"
            # **必须放在子 shell 里跑 `set -e`**：JobRunner 会在命令之后追加
            # `__rc=$?; echo $__rc > <rc>`；若命令串顶层 `set -e` 因 cp 失败退出，
            # rc 文件就永远写不出来 ⇒ poll() 判 dead ⇒ 下游把「归档件已存在」误判成死任务。
            # 第二轮（G2 rework 回边再次 N9）的归档件是 444，直接 cp 会 Permission denied ⇒
            # 先 `rm -f` 目标再写（归档只增不改的语义由文件名/内容保证，本处是同一 drill 副本重建）。
            command = (
                "( set -e; "
                f"mkdir -p {str(arch)!r}; "
                f"rm -f {str(dest)!r} {str(arch_copy)!r}; "
                f"cp {str(src)!r} {str(dest)!r}; "
                f"cp {str(src)!r} {str(arch_copy)!r}; chmod 444 {str(arch_copy)!r}; "
                f"rm -f {str(prov)!r}; "
                f"printf '%s\\n%s\\n' "
                f"'DRILL FIXTURE：本归档目录由 drill 夹具产生，仅用于演示归档腿形态。' "
                f"'真实归档件由 kb/tools/run_guarded.sh 产出（只增不改 + 归档件只读）。' "
                f"> {str(prov)!r}; chmod 444 {str(prov)!r}"
                " )"
            )
        try:
            record = ctx.runner.submit(
                run_id=ctx.run_id, node="N9", command=command,
                cwd=Path(data.require_resource("repo_root")),
                tc=_REAL_CASE, seed=_SEED,
                note=f"mode={ctx.mode} scenario={ctx.scenario} DRILL FIXTURE",
            )
        except BaseException:
            # 铁律：acquire → submit 之间失败也必须释放单槽（否则后续全部卡在 SLOT）
            if ctx.admission is not None:
                ctx.admission.release(job_id=_slot_job_id(ctx))
            raise
        payload = {
            "job_id": record.job_id, "node": "N9", "phase": "running",
            "tc": _REAL_CASE, "seed": _SEED, "cases": [_REAL_CASE],
            "expected_cases": [_REAL_CASE], "md5s": {}, "target_set": "drill_fixture",
            "started_at": record.started_at, "log_path": record.log_path,
            "mode": ctx.mode, "scenario": ctx.scenario,
            "sandbox_root": str(run_dir / "sandbox"), "evidence_dir": str(evidence_dir),
        }
        ctx.pending["n9_job_id"] = record.job_id
        await data.async_set_state("n9_job", payload)
        ctx.event("job_submitted", node="N9", status="running", detail=payload, refs=[record.log_path])
        ctx.node_finished("N9_submit", detail={
            "job_id": record.job_id, "scenario": ctx.scenario,
            "source": "drill_fixture",
            "summary": (f"N9_submit：已提交全跑作业 {record.job_id}"
                        f"（drill 夹具，scenario={ctx.scenario}）⇒ 图转入停放"),
        })
        return payload

    # ---------------------------------------------------------------- real
    cases = _target_cases(data)
    _verify_targets(cases)
    case_names = [c["case"] for c in cases]
    gate = await _acquire_slot(data, ctx, job_id=_slot_job_id(ctx),
                               tc=",".join(case_names), seed=_SEED)
    if gate.get("retry"):
        return {"status": "slot_retry"}

    summary_path = run_dir / "sandbox" / "n9_run_summary.tsv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    command = _serial_guard_command(cases, sandbox_root=run_dir / "sandbox",
                                    evidence_dir=evidence_dir, run_id=ctx.run_id,
                                    summary_path=summary_path)
    try:
        record = ctx.runner.submit(
            run_id=ctx.run_id, node="N9", command=command,
            cwd=Path(data.require_resource("repo_root")),
            tc=",".join(case_names), seed=_SEED,
            note=f"mode=real cases={len(case_names)} sandbox_only",
        )
    except BaseException:
        if ctx.admission is not None:
            ctx.admission.release(job_id=_slot_job_id(ctx))
        raise
    md5s = {c["case"]: c["md5"] for c in cases}
    payload = {
        "job_id": record.job_id, "node": "N9", "phase": "running",
        "tc": ",".join(case_names), "seed": _SEED,
        "cases": case_names, "expected_cases": case_names, "md5s": md5s,
        "target_set": "n6_applied", "started_at": record.started_at,
        "log_path": record.log_path, "sandbox_root": str(run_dir / "sandbox"),
        "evidence_dir": str(evidence_dir), "summary_path": str(summary_path),
        "mode": ctx.mode, "scenario": ctx.scenario,
        "identity": {"cases": case_names, "md5s": md5s, "seed": _SEED, "run_id": ctx.run_id},
    }
    ctx.pending["n9_job_id"] = record.job_id
    await data.async_set_state("n9_job", payload)
    ctx.event("job_submitted", node="N9", status="running", detail=payload,
              refs=[record.log_path, str(summary_path)])
    ctx.node_finished("N9_submit", detail={
        "job_id": record.job_id, "cases": len(case_names),
        "source": "kb_tool",
        "summary": (f"N9_submit：已提交全跑作业 {record.job_id}，"
                    f"覆盖 {len(case_names)} 个沙箱用例 ⇒ 图转入停放"),
    })
    return payload


async def n9_park(data: Any) -> dict[str, Any]:
    """停在 `job_done` 中断上等外部完成。

    必须用 `resume_to="self"`：`resume_to="next"` 时 `pause_for` 的返回值是**中断描述符**，
    恢复载荷会直接流向下游 ⇒ **本 chunk 永远看不到作业结局**，
    死任务/取消会被静默当成继续（这是实测到的真 bug，不得再犯）。

    **恢复后以日志为权威重新取数**，不信任 resume 载荷里的数字
    （否则外部可以伪造"跑通"）。
    """
    ctx = ctx_of(data)
    job = data.get_state("n9_job") or {}
    job_id = job.get("job_id") or ctx.pending.get("n9_job_id")
    if not job_id:
        raise RuntimeError("N9 park 找不到 job_id：状态未落盘")

    if not getattr(data, "is_resume", False):
        await data.async_pause_for(
            type="job_done",
            interrupt_id=f"JOB:{job_id}",
            payload={"job_id": job_id, "node": "N9", "tc": job.get("tc"),
                     "log_path": job.get("log_path"), "cases": job.get("cases"),
                     "wait_reason": "全跑为外部长任务；图必须停放而非阻塞 handler。"},
            resume_to="self",
        )
        return {"status": "waiting", "job_id": job_id}

    payload = (getattr(data.resume, "value", None) or {}) if getattr(data, "resume", None) else {}
    try:
        try:
            phase = ctx.runner.poll(job_id).phase
        except Exception:
            phase = payload.get("phase")
        if payload.get("phase") and phase != payload.get("phase"):
            ctx.event("warning", node="N9", status="phase_disagreement",
                      detail={"job_id": job_id, "payload_phase": payload.get("phase"),
                              "authority_phase": phase,
                              "rule": "以权威（rc 文件 + 进程存活）为准，载荷只作提示"})
        if phase == "dead":
            ctx.event("dead_job", node="N9", status="dead", detail=payload)
            raise RuntimeError(f"死任务 {job_id}：进程已终结但未留下 rc ⇒ 不得当成功，走失败分支。")
        if phase == "cancelled":
            ctx.event("warning", node="N9", status="cancelled", detail=payload)
            raise RuntimeError(f"作业 {job_id} 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续。")
        if phase not in ("done",):
            raise RuntimeError(
                f"作业 {job_id} 的相位是 {phase!r}（既非 done 也非 dead/cancelled）⇒ "
                "不得按完成处理；按失败终止本轮。"
            )

        if ctx.mode == "drill":
            ev = ctx.evidence()
            counts = ev.get("counts") or {}
            out = {
                "job_id": job_id,
                "resume_payload": payload,
                "evidence": ev,
                "counts": counts,
                "target_cases": job.get("cases") or [_REAL_CASE],
                "cases": {_REAL_CASE: {"present": ev.get("present"), "counts": counts,
                                       "verdict": ev.get("verdict"),
                                       "path": ev.get("path")}},
                "verdict": ev.get("verdict") or {},
                "authority_note": "resume 载荷只作提示；口径一/口径二/印记一律由日志重新抽取。",
            }
            ctx.pending["n9_result"] = out
            await data.async_set_state("n9_result", out)
            status = "pass" if counts.get("both_zero") else "fail"
            ctx.event("job_finished", node="N9", status=status,
                      detail={"job_id": job_id, "rc": payload.get("rc"),
                              "koutou1": (counts.get("koutou1") or {}).get("value"),
                              "koutou2": (counts.get("koutou2") or {}).get("value")},
                      refs=[ev.get("path", "")])
            ctx.node_finished("N9", status=status,
                              detail={"koutou1": (counts.get("koutou1") or {}).get("value"),
                                      "koutou2": (counts.get("koutou2") or {}).get("value"),
                                      "cases": len(out["target_cases"]),
                                      "job_id": job_id,
                                      "source": "drill_fixture",
                                      "summary": (f"N9：全跑作业 {job_id} 完成（drill 夹具），"
                                                  f"{counts_text(counts)}，"
                                                  f"both_zero={counts.get('both_zero')}")},
                              refs=[ev.get("path", "")])
            return out

        # ---------------------------------------------------------------- real
        case_names = [str(c) for c in (job.get("expected_cases") or job.get("cases") or [])]
        md5s = {str(k): str(v) for k, v in (job.get("md5s") or {}).items()}
        if not case_names:
            raise RuntimeError("N9 real 恢复后找不到目标用例集（n9_job 未落 cases）")
        # 沙箱件在跑之前/跑之后都必须与冻结值一致（审的 md5 == 跑的 md5）
        for case in case_names:
            sandbox = Path(str(job.get("sandbox_root") or "")) / "TESTLIB" / f"{case}.sv"
            if not sandbox.is_file():
                raise RuntimeError(f"N9：沙箱件不存在 {sandbox}（禁止回退未修订 TESTLIB）")
            if md5s.get(case) and _md5_file(sandbox) != md5s[case]:
                raise RuntimeError(f"N9：{case} 沙箱 md5 在跑后被改动 ⇒ 证据作废")
        logs = _collect_case_logs(Path(str(job.get("evidence_dir") or ctx.run_dir / "evidence")),
                                  case_names)
        missing = [c for c in case_names if c not in logs]
        if missing:
            # 跑挂了也要「采证并三分类」，但**没有日志**就没有证据 —— 不得默认通过
            ctx.node_failed("N9", message=f"缺 {len(missing)} 例证据日志：{missing}")
            raise RuntimeError(
                f"N9：以下用例没有 run.log（{missing}）⇒ 不得把'没跑出证据'当通过"
            )
        aggregate = aggregate_evidence(ctx, logs=logs, cases=case_names,
                                       expected_md5=md5s, seed=_SEED)
        per_case = aggregate.get("per_case") or {}
        not_present = [c for c in case_names if not (per_case.get(c) or {}).get("present")]
        if not_present:
            ctx.node_failed("N9", message=f"证据不可用（present=false）：{not_present}")
            raise RuntimeError(f"N9：证据不可用 {not_present} ⇒ 不得继续")
        counts = _combine_counts(per_case)
        verdict = aggregate.get("verdict") or {}
        identity = _identity_summary(aggregate, md5s)
        out = {
            "job_id": job_id,
            "resume_payload": payload,
            "target_cases": case_names,
            "run_md5s": md5s,
            "cases": per_case,
            "evidence": aggregate,
            "counts": counts,
            "verdict": verdict,
            "identity": identity,
            "evidence_paths": {c: str(p) for c, p in logs.items()},
            "authority_note": ("resume 载荷只作提示；两套口径/印记/身份由 host.evidence 聚合"
                               "（run_guarded 身份头）重新抽取。"),
        }
        ctx.pending["n9_result"] = out
        await data.async_set_state("n9_result", out)
        status = "pass" if verdict.get("passed") else "fail"
        ctx.event("job_finished", node="N9", status=status,
                  detail={"job_id": job_id, "rc": payload.get("rc"),
                          "cases": len(case_names),
                          "koutou1": (counts.get("koutou1") or {}).get("value"),
                          "koutou2": (counts.get("koutou2") or {}).get("value"),
                          "identity_consistent": identity["consistent"]},
                  refs=[out["evidence_paths"][c] for c in case_names][:6])
        ctx.node_finished("N9", status=status,
                          detail={"cases": len(case_names),
                                  "koutou1": (counts.get("koutou1") or {}).get("value"),
                                  "koutou2": (counts.get("koutou2") or {}).get("value"),
                                  "job_id": job_id,
                                  "source": "kb_tool",
                                  "summary": (f"N9：全跑作业 {job_id} 完成，"
                                              f"{len(case_names)} 个用例，"
                                              f"{counts_text(counts)}，"
                                              f"身份一致={identity['consistent']}")},
                          refs=[out["evidence_paths"][c] for c in case_names][:6])
        return out
    finally:
        # 铁律：成功 / 失败 / 取消都必须释放单槽，且幂等。
        if ctx.admission is not None:
            handoff = ctx.admission.release(job_id=_slot_job_id(ctx))
            if handoff:
                ctx.event("admission_granted", node="N9", status="handoff", detail=handoff)


# ---------------------------------------------------------------- N15


def _full_regression_cases() -> list[str]:
    """全量回归集：取索引里的全部用例（索引缺失 ⇒ 空，调用方如实登记）。"""
    path = P.KB_DIR / "index" / "cases.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return [str(c.get("case")) for c in (doc.get("cases") or []) if c.get("case")]


async def n15_select(data: Any) -> list[str]:
    """N15 选择要回归的用例集。

    `full_now` = 全量用例（索引）；`subset_only` / `milestone_only` = 本轮受影响子集。
    返回纯 list（图上的 `for_each`/后继节点吃序列），元数据落 state。
    """
    ctx = ctx_of(data)
    ctx.node_started("N15_select")
    decisions = data.get_state("gate_decisions") or {}
    g3 = ((decisions.get("G3_regression_decision") or {}).get("decision")) or ""
    n5 = data.get_state("n5_impact") or {}
    affected = [c for c in (n5.get("must_change_cases") or []) if c]
    if g3 == "full_now":
        cases = _full_regression_cases() or affected
    else:
        cases = affected
    if not cases:
        cases = [_REAL_CASE]
    await data.async_set_state("n15_set", {"cases": cases, "count": len(cases),
                                           "mode": ctx.mode, "g3_decision": g3})
    ctx.node_finished("N15_select", detail={
        "count": len(cases), "g3": g3,
        "source": "framework",
        "summary": (f"N15_select：按 G3={g3 or '未签署'} 选出 {len(cases)} 个回归用例"),
    })
    return cases


async def n15_run(data: Any) -> dict[str, Any]:
    """N15 全量/分层回归（**单作业串行**，替代旧的 for_each(n15_case)）。

    - real：G3 集逐例 `run_guarded.sh --mode full`，串成一个作业；图停在 JOB 中断；
      恢复后逐例证据落盘（经 `host.evidence` 聚合），**不再发 provisional=True**。
    - drill：显式 `simulated=True` no-op（accept_v1 的 G3=defer 不走本支；单测触发时也不抛错）。
    - 跨机 `run_tc.py` 未接入 ⇒ 在状态里如实登记 `cross_machine="run_tc.py 未接入（本机串行）"`。
    """
    ctx = ctx_of(data)
    node = "N15"
    s15 = data.get_state("n15_set") or {}
    cases = [str(c) for c in (s15.get("cases") or []) if c]
    g3 = s15.get("g3_decision")

    if ctx.mode == "drill":
        ctx.node_started(node)
        out = {
            "mode": ctx.mode, "simulated": True, "executed": False,
            "set": cases, "count": len(cases), "g3_decision": g3,
            "cross_machine": "run_tc.py 未接入（本机串行）",
            "note": "drill：不真跑仿真；本节点在 drill 下为显式 no-op（不是终值冒充）。",
        }
        await data.async_set_state("n15_result", out)
        ctx.node_finished(node, status="ok", detail={
            "simulated": True, "count": len(cases), "job_id": None,
            "source": "framework",
            "summary": (f"N15：drill 显式 no-op（未真跑回归），回归集 {len(cases)} 个用例，"
                        f"G3={g3 or '未签署'}"),
        })
        return out

    job_state = data.get_state("n15_job") or {}
    job_id = job_state.get("job_id")
    submitted_here = False

    if not job_id:
        ctx.node_started(node)
        if not cases:
            ctx.node_failed(node, message="N15 回归集为空")
            raise RuntimeError("N15：回归集为空（G3 集未产出）⇒ 不得声称已回归")
        # 目标集：优先用沙箱件（本轮已修订），否则用仓库原件（分层回归的本意）
        applied = {str(c.get("case")): c for c in (data.get_state("n6_applied") or {}).get("cases") or []}
        entries: list[dict[str, Any]] = []
        repo_root = Path(data.require_resource("repo_root"))
        for case in cases:
            item = applied.get(case)
            if item and Path(str(item.get("sandbox_path"))).is_file():
                entries.append({"case": case, "sandbox_path": str(item["sandbox_path"]),
                                "md5": str(item.get("md5_after") or "")})
            else:
                src = repo_root / "TESTLIB" / f"{case}.sv"
                if not src.is_file():
                    ctx.node_failed(node, message=f"回归用例不存在：{src}")
                    raise FileNotFoundError(f"N15：回归用例不存在：{src}")
                entries.append({"case": case, "sandbox_path": str(src), "md5": _md5_file(src)})
        gate = await _acquire_slot(data, ctx, job_id=_n15_job_id(ctx),
                                   tc=",".join(cases), seed=_SEED, node=node)
        if gate.get("retry"):
            return {"status": "slot_retry"}
        evidence_dir = ctx.run_dir / "evidence"
        summary_path = ctx.run_dir / "sandbox" / "n15_run_summary.tsv"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        command = _serial_guard_command(entries, sandbox_root=ctx.run_dir / "sandbox",
                                        evidence_dir=evidence_dir, run_id=ctx.run_id,
                                        summary_path=summary_path)
        try:
            record = ctx.runner.submit(
                run_id=ctx.run_id, node=node, command=command,
                cwd=repo_root, tc=",".join(cases), seed=_SEED,
                note=f"mode=real cases={len(cases)} G3={g3}",
            )
        except BaseException:
            if ctx.admission is not None:
                ctx.admission.release(job_id=_n15_job_id(ctx))
            raise
        md5s = {c["case"]: c["md5"] for c in entries}
        job_state = {
            "job_id": record.job_id, "node": node, "phase": "running",
            "tc": ",".join(cases), "seed": _SEED, "cases": cases,
            "expected_cases": cases, "md5s": md5s, "target_set": "g3_set",
            "g3_decision": g3, "started_at": record.started_at,
            "log_path": record.log_path, "sandbox_root": str(ctx.run_dir / "sandbox"),
            "evidence_dir": str(evidence_dir), "summary_path": str(summary_path),
            "cross_machine": "run_tc.py 未接入（本机串行）",
        }
        await data.async_set_state("n15_job", job_state)
        ctx.event("job_submitted", node=node, status="running", detail=job_state,
                  refs=[record.log_path])
        ctx.node_finished("N15_submit", detail={
            "job_id": record.job_id, "cases": len(cases),
            "source": "kb_tool",
            "summary": (f"N15_submit：已提交回归作业 {record.job_id}，"
                        f"覆盖 {len(cases)} 个用例（G3={g3 or '未签署'}）⇒ 图转入停放"),
        })
        submitted_here = True
        job_id = record.job_id

    # 停放：本调用刚提交的作业要停；从 SLOT 中断恢复后提交的也要停。
    # 只有「从 JOB 中断恢复」（job_state 已在、本调用未提交）才直接进入取结局分支。
    if submitted_here or not getattr(data, "is_resume", False):
        await data.async_pause_for(
            type="job_done",
            interrupt_id=f"JOB:{job_id}",
            payload={"job_id": job_id, "node": node, "cases": job_state.get("cases"),
                     "wait_reason": "N15 回归为外部长任务；图必须停放而非阻塞 handler。"},
            resume_to="self",
        )
        return {"status": "waiting", "job_id": job_id}

    # 恢复：权威相位 + 逐例证据（不信任 resume 载荷数字）
    try:
        try:
            phase = ctx.runner.poll(str(job_id)).phase
        except Exception:
            phase = (getattr(data, "resume", None) and (data.resume.value or {}).get("phase"))
        if phase == "dead":
            ctx.event("dead_job", node=node, status="dead", detail={"job_id": job_id})
            raise RuntimeError(f"N15：死任务 {job_id}，不得当成功")
        if phase == "cancelled":
            raise RuntimeError(f"N15：作业 {job_id} 被取消 ⇒ 不得当回归完成")
        if phase != "done":
            raise RuntimeError(f"N15：作业相位 {phase!r} 非终态 ⇒ 不得当完成")

        case_names = [str(c) for c in (job_state.get("expected_cases") or cases)]
        md5s = {str(k): str(v) for k, v in (job_state.get("md5s") or {}).items()}
        logs = _collect_case_logs(Path(str(job_state.get("evidence_dir"))), case_names)
        missing = [c for c in case_names if c not in logs]
        if missing:
            ctx.node_failed(node, message=f"N15 缺证据日志：{missing}")
            raise RuntimeError(f"N15：以下用例没有 run.log：{missing} ⇒ 不得声称回归完成")
        aggregate = aggregate_evidence(ctx, logs=logs, cases=case_names,
                                       expected_md5=md5s, seed=_SEED)
        per_case = aggregate.get("per_case") or {}
        verdict = aggregate.get("verdict") or {}
        out = {
            "job_id": job_id, "mode": ctx.mode, "simulated": False, "executed": True,
            "set": case_names, "count": len(case_names), "g3_decision": g3,
            "cases": per_case, "evidence": aggregate,
            "counts": _combine_counts(per_case),
            "verdict": verdict,
            "identity": _identity_summary(aggregate, md5s),
            "evidence_paths": {c: str(p) for c, p in logs.items()},
            "cross_machine": "run_tc.py 未接入（本机串行；5机×2LIC 跨机调度未实现）",
            "authority_note": "终值来自逐例日志聚合；不使用 provisional 临时值。",
        }
        await data.async_set_state("n15_result", out)
        status = "pass" if verdict.get("passed") else "fail"
        ctx.event("job_finished", node=node, status=status,
                  detail={"job_id": job_id, "cases": len(case_names),
                          "passed": verdict.get("passed")},
                  refs=[out["evidence_paths"][c] for c in case_names][:6])
        ctx.node_finished(node, status=status,
                          detail={"cases": len(case_names),
                                  "passed": verdict.get("passed"),
                                  "job_id": job_id,
                                  "source": "kb_tool",
                                  "summary": (f"N15：回归作业 {job_id} 完成，"
                                              f"{len(case_names)} 个用例，"
                                              f"passed={verdict.get('passed')}，"
                                              f"身份一致={out['identity']['consistent']}")})
        return out
    finally:
        if ctx.admission is not None:
            handoff = ctx.admission.release(job_id=_n15_job_id(ctx))
            if handoff:
                ctx.event("admission_granted", node=node, status="handoff", detail=handoff)


async def n15_case(data: Any) -> dict[str, Any]:
    """**已废弃**：旧的 `for_each` 单例节点（只发 provisional，不跑任何东西）。

    拓扑已改为 `n15_select → n15_run`（单作业串行 + 真实证据）。保留符号只为兼容
    尚未更新的导入；不再发 `job_progress(provisional=True)` 冒充进度。
    """
    ctx = ctx_of(data)
    case = data.input
    if isinstance(case, dict):
        case = case.get("case") or case.get("cases") or str(case)
    out = {"case": case, "mode": ctx.mode, "executed": False, "deprecated": True,
           "note": "N15 已改为 n15_run 单作业串行；本节点不再执行、不再发临时进度。"}
    ctx.event("warning", node="N15", status="deprecated_node", detail=out)
    return out
