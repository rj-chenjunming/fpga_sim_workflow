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
from host.evidence import evidence_view

from ..context import RunCtx, ctx_of
from .model_common import counts_text

#: drill 夹具的固定全跑用例（accept_v1 的 117 断言依赖该形状，drill 分支保持不变）
_REAL_CASE = "tc_pcie_rw_02"

#: drill 情景：真实子进程 + 真实产物，只有工作负载是夹具（必须标注 DRILL FIXTURE）。
SCENARIOS = ("happy", "dead_job", "cancel")

#: drill 分支种子（与既有夹具/断言一致）
_SEED = "1"

#: drill 多例夹具清单（SPEC-REV-05 R2）：存在则按清单**回放全部用例**；
#: 缺省（旧夹具没有该文件）保持单例 drill 分支，accept_v1 的断言不受影响。
DRILL_CASES_FILE = "drill_cases.json"


def _drill_case_spec(ctx: RunCtx) -> list[dict[str, Any]] | None:
    """读夹具的多例清单；不存在/不完整 ⇒ None（回退 legacy 单例路径）。"""
    path = Path(ctx.fixture) / DRILL_CASES_FILE
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    items = doc.get("cases") if isinstance(doc, dict) else None
    if not isinstance(items, list) or not items:
        return None
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        case = str(item.get("case") or "").strip()
        run_log = str(item.get("run_log") or "").strip()
        if not case or not run_log:
            continue
        out.append({
            "case": case,
            "run_log": run_log,
            "rc": int(item.get("rc") or 0),
            "compile_logs": dict(item.get("compile_logs") or {}),
        })
    return out or None


def _drill_replay_command(spec: list[dict[str, Any]], *, fixture_dir: Path,
                          evidence_dir: Path, summary_path: Path) -> str:
    """把夹具证据**复制**成 run 证据目录（只回放，不重跑仿真）。

    产物形状刻意与 `run_guarded.sh` 一致（`<case>_<seed>_run.log` +
    `<case>_<seed>_c_{rtl,tb,uvs}.log` + `n9_run_summary.tsv`），
    这样下游聚合/面板不需要第二套口径。
    """
    parts = [
        "( set -e;",
        f" mkdir -p {shlex.quote(str(evidence_dir))};",
        f" : > {shlex.quote(str(summary_path))};",
    ]
    for item in spec:
        case = item["case"]
        source = Path(fixture_dir) / "evidence" / item["run_log"]
        # 命名必须满足 `_collect_case_logs` 的约定 `*_<case>_<seed>_run.log`：
        # 真实件带时间戳前缀；回放件用固定 `fixture` 前缀（不能省，否则聚合找不到）。
        dest = Path(evidence_dir) / f"fixture_{case}_{_SEED}_run.log"
        parts.append(f" rm -f {shlex.quote(str(dest))};"
                     f" cp {shlex.quote(str(source))} {shlex.quote(str(dest))};")
        for kind, name in (item.get("compile_logs") or {}).items():
            compile_src = Path(fixture_dir) / "evidence" / str(name)
            compile_dest = Path(evidence_dir) / f"fixture_{case}_{_SEED}_{kind}.log"
            parts.append(f" rm -f {shlex.quote(str(compile_dest))};"
                         f" cp {shlex.quote(str(compile_src))} {shlex.quote(str(compile_dest))};")
        parts.append(f" printf '%s|%s\\n' {shlex.quote(case)} {int(item['rc'])}"
                     f" >> {shlex.quote(str(summary_path))};")
    parts.append(" )")
    return "".join(parts)


async def _submit_drill_replay(data: Any, ctx: RunCtx, spec: list[dict[str, Any]], *,
                               run_dir: Path, evidence_dir: Path) -> dict[str, Any]:
    """drill 多例回放：一次作业覆盖清单里的全部用例（停止点/单槽语义与 real 相同）。"""
    case_names = [item["case"] for item in spec]
    summary_path = run_dir / "sandbox" / "n9_run_summary.tsv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    gate = await _acquire_slot(data, ctx, job_id=_slot_job_id(ctx),
                               tc=",".join(case_names), seed=_SEED)
    if gate.get("retry"):
        return {"status": "slot_retry"}
    command = _drill_replay_command(spec, fixture_dir=Path(ctx.fixture),
                                    evidence_dir=evidence_dir, summary_path=summary_path)
    try:
        record = ctx.runner.submit(
            run_id=ctx.run_id, node="N9", command=command,
            cwd=Path(data.require_resource("repo_root")),
            tc=",".join(case_names), seed=_SEED,
            note=f"mode=drill cases={len(case_names)} fixture_replay",
        )
    except BaseException:
        if ctx.admission is not None:
            ctx.admission.release(job_id=_slot_job_id(ctx))
        raise
    payload = {
        "job_id": record.job_id, "node": "N9", "phase": "running",
        "tc": ",".join(case_names), "seed": _SEED, "cases": case_names,
        "expected_cases": case_names, "md5s": {}, "target_set": "drill_fixture_replay",
        "started_at": record.started_at, "log_path": record.log_path,
        "mode": ctx.mode, "scenario": ctx.scenario,
        "sandbox_root": str(run_dir / "sandbox"), "evidence_dir": str(evidence_dir),
        "summary_path": str(summary_path),
        "fixture": str(ctx.fixture),
        "pre_md5s": True,
    }
    ctx.pending["n9_job_id"] = record.job_id
    await data.async_set_state("n9_job", payload)
    ctx.event("job_submitted", node="N9", status="running", detail=payload,
              refs=[record.log_path, str(summary_path)])
    ctx.node_started("N9_submit")
    ctx.node_finished("N9_submit", detail={
        "job_id": record.job_id, "cases": len(case_names),
        "source": "drill_fixture",
        "summary": (f"N9_submit：已提交全跑作业 {record.job_id}（drill 夹具回放，"
                    f"覆盖 {len(case_names)} 个用例）⇒ 图转入停放"),
    }, refs=[record.log_path, str(summary_path)])
    return payload


async def _drill_replay_done(ctx: RunCtx, data: Any, job: dict[str, Any], job_id: str,
                             payload: dict[str, Any], spec: list[dict[str, Any]]) -> dict[str, Any]:
    """drill 多例回放完成：逐例重新抽数（不信任载荷），口径合并后判 pass/fail。"""
    case_names = [item["case"] for item in spec]
    evidence_dir = Path(str(job.get("evidence_dir") or (ctx.run_dir / "evidence")))
    logs = ctx.environment.collect_logs(evidence_dir, case_names)
    missing = [c for c in case_names if c not in logs]
    if missing:
        ctx.node_failed("N9", message=f"缺 {len(missing)} 例证据日志：{missing}")
        raise RuntimeError(f"N9：以下用例没有 run.log（{missing}）⇒ 不得把'没跑出证据'当通过")
    per_case: dict[str, Any] = {}
    for case, path in logs.items():
        view = evidence_view(path)
        per_case[case] = {
            "present": view.get("present"),
            "counts": view.get("counts") or {},
            "verdict": view.get("verdict") or {},
            "path": str(path),
        }
    not_present = [c for c in case_names if not (per_case.get(c) or {}).get("present")]
    if not_present:
        ctx.node_failed("N9", message=f"证据不可用（present=false）：{not_present}")
        raise RuntimeError(f"N9：证据不可用 {not_present} ⇒ 不得继续")
    counts = _combine_counts(per_case)
    out = {
        "job_id": job_id,
        "resume_payload": payload,
        "target_cases": case_names,
        "cases": per_case,
        "evidence": {"per_case": per_case, "source": "drill_fixture_replay"},
        "counts": counts,
        "verdict": {"passed": bool(counts.get("both_zero"))},
        "identity": {"consistent": None, "mismatches": [],
                     "source": "drill_fixture_replay：夹具日志无身份头，未做身份四方同值"},
        "authority_note": "drill 回放：口径由日志重新抽取；不重跑仿真。",
    }
    ctx.pending["n9_result"] = out
    await data.async_set_state("n9_result", out)
    status = "pass" if counts.get("both_zero") else "fail"
    ctx.event("job_finished", node="N9", status=status,
              detail={"job_id": job_id, "rc": payload.get("rc"),
                      "koutou1": (counts.get("koutou1") or {}).get("value"),
                      "koutou2": (counts.get("koutou2") or {}).get("value"),
                      "replay": True},
              refs=[str(p) for p in logs.values()])
    ctx.node_finished("N9", status=status,
                      detail={"koutou1": (counts.get("koutou1") or {}).get("value"),
                              "koutou2": (counts.get("koutou2") or {}).get("value"),
                              "cases": len(case_names),
                              "job_id": job_id,
                              "replay": True,
                              **_n9_detail(cases=per_case,
                                           identity={"consistent": None, "mismatches": [],
                                                     "source": "drill_fixture_replay"}),
                              "source": "drill_fixture",
                              "summary": (f"N9：全跑作业 {job_id} 完成（drill 夹具回放，"
                                          f"{len(case_names)} 例），{counts_text(counts)}，"
                                          f"both_zero={counts.get('both_zero')}")},
                      refs=[str(p) for p in logs.values()])
    return out



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


# ---------------------------------------------------------------- N9/N15 detail 投影


def _n9_rows(cases: dict[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """N9 逐用例计数投影（P-24）：只读 `host.evidence` 聚合的既有字段，不重算口径。"""
    k1_by_case: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for case in sorted(cases or {}):
        item = (cases or {}).get(case) or {}
        counts = item.get("counts") or {}
        uvm = (counts.get("koutou2") or {}).get("value") or {}
        k1 = (counts.get("koutou1") or {}).get("value")
        k1_by_case[str(case)] = k1 if isinstance(k1, int) else None
        rows.append({"case": str(case), "koutou1": k1,
                     "uvm_error": uvm.get("UVM_ERROR"),
                     "uvm_fatal": uvm.get("UVM_FATAL"),
                     "passed": (item.get("verdict") or {}).get("passed")})
    return k1_by_case, rows


def _koutou1_example(cases: dict[str, Any] | None) -> str | None:
    """口径一的**一行示例**（P-24 ③）：取第一条非零用例的参考行；没有 ⇒ None（不编）。"""
    for case in sorted(cases or {}):
        counts = ((cases or {}).get(case) or {}).get("counts") or {}
        k1 = (counts.get("koutou1") or {}).get("value")
        refs = (counts.get("koutou1") or {}).get("refs") or []
        if isinstance(k1, int) and k1 > 0 and refs:
            return str(refs[0])
    return None


def _n9_detail(*, cases: dict[str, Any] | None,
               identity: dict[str, Any]) -> dict[str, Any]:
    """N9 detail 的投影字段（P-24，契约 §3）。`identity` 由调用方按模式给出事实。"""
    k1_by_case, rows = _n9_rows(cases)
    return {"koutou1_by_case": k1_by_case,
            "example_line": _koutou1_example(cases),
            "identity": identity,
            "cases_detail": rows}


# ---------------------------------------------------------------- N9 提交


# 保留既有流程快照的节点源码行号。


















































async def n9_submit(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n9_submit import run
    return await run(data, _REAL_CASE=_REAL_CASE, _SEED=_SEED, _acquire_slot=_acquire_slot, _drill_case_spec=_drill_case_spec, _slot_job_id=_slot_job_id, _submit_drill_replay=_submit_drill_replay, _target_cases=_target_cases, _verify_targets=_verify_targets, ctx_of=ctx_of)




































































































































async def n9_park(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n9_park import run
    return await run(data, _REAL_CASE=_REAL_CASE, _SEED=_SEED, _combine_counts=_combine_counts, _drill_case_spec=_drill_case_spec, _drill_replay_done=_drill_replay_done, _identity_summary=_identity_summary, _md5_file=_md5_file, _n9_detail=_n9_detail, _slot_job_id=_slot_job_id, aggregate_evidence=aggregate_evidence, counts_text=counts_text, ctx_of=ctx_of)







































































































































































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
    """保留流程快照身份的节点入口。"""
    from ..nodes.n15_select import run
    return await run(data, _REAL_CASE=_REAL_CASE, _full_regression_cases=_full_regression_cases, ctx_of=ctx_of)



























async def n15_run(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n15_run import run
    return await run(data, _SEED=_SEED, _acquire_slot=_acquire_slot, _combine_counts=_combine_counts, _identity_summary=_identity_summary, _md5_file=_md5_file, _n15_job_id=_n15_job_id, aggregate_evidence=aggregate_evidence, ctx_of=ctx_of)



















































































































































































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
