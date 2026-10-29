"""N6 application node."""
from __future__ import annotations
import hashlib
import shutil
from pathlib import Path
from typing import Any

async def run(data: Any, *, ctx_of, _case_state_args, _ensure_case_state, _sandbox_lib, apply_edits, case_edits_from_output, md5_file, run_kb_tool, candidate_plan, _import_candidates_or_fail, CI) -> dict[str, Any]:
    """N6 的 **Host 沙箱写入步骤**：模型只出 edits，写盘/校验/冻结/记账都在这里。

    - 只写 `run_dir/sandbox/TESTLIB/`（不写冻结的 `TESTLIB/`）；
    - 逐条校验 `old` 在声明行唯一命中，0/多次 ⇒ fail closed；
    - 冻结 md5（写后复算，并 chmod 444）；
    - 调 `kb/tools/case_state.py set --state 已修订待验` 记账（I2 写入者）；
    - **S6/DS-06 候选导入**：`n6_author` 带四键（`candidate_root`/`candidate_manifest`/
      `baseline`/`execution_state`，G1 冻结）⇒ **先**按白名单+哈希+停止确认导入
      （`host.agent_candidate_import`，纯判据零写入），再交本函数的 `apply_edits` 施加；
      导入被拒 ⇒ 显式失败（**不**退回"用模型回传的 edits 直接写"）。缺四键 ⇒ 既有路径不变。
    - drill：直接采用夹具沙箱件（复制到 run_dir），夹具缺失则 no-op + note，**不失败**。
    """
    ctx = ctx_of(data)
    ctx.node_started("N6_apply")
    sandbox_lib = _sandbox_lib(ctx)

    if ctx.mode == "drill":
        fixture_lib = ctx.fixture / "sandbox" / "TESTLIB"
        copied: list[dict[str, Any]] = []
        if fixture_lib.is_dir():
            sandbox_lib.mkdir(parents=True, exist_ok=True)
            for src in sorted(fixture_lib.glob("*.sv")):
                dest = sandbox_lib / src.name
                shutil.copy2(src, dest)
                copied.append(
                    {
                        "case": src.stem,
                        "file": f"TESTLIB/{src.name}",
                        "sandbox_path": str(dest),
                        "md5_before": md5_file(src),
                        "md5_after": md5_file(dest),
                        "edits": 0,
                        "case_state_rc": None,
                        "source": "drill_fixture",
                    }
                )
        payload = {
            "run_id": ctx.run_id,
            "mode": ctx.mode,
            "status": "drill_fixture" if copied else "drill_noop",
            "sandbox_root": str(ctx.run_dir / "sandbox"),
            "cases": copied,
            "targets": [],
            "count": len(copied),
            "note": (
                "drill：直接采用归档演练轮夹具沙箱件（只读夹具 → 运行目录副本）"
                if copied
                else "drill：夹具无沙箱件 ⇒ no-op（drill 不要求结构化 edits）"
            ),
        }
        if not copied:
            ctx.event("warning", node="N6_apply", status="drill_noop",
                      detail={"note": payload["note"]})
        await data.async_set_state("n6_applied", payload)
        # P-21：逐用例修改清单与 N6 **同源**（同一投影函数）；drill 无模型输出 ⇒ None。
        author_out = data.get_state("n6_author") or {}
        drill_authors = author_out.get("data") if isinstance(author_out.get("data"), dict) else None
        ctx.node_finished("N6_apply", status="ok",
                          detail={
                              "status": payload["status"],
                              "cases": len(copied),
                              "case_edits": case_edits_from_output(drill_authors),
                              "applied_cases": [str(c["case"]) for c in copied if c.get("case")],
                              "source": "drill_fixture",
                              "summary": (
                                  f"N6_apply：drill 采用夹具沙箱件 {len(copied)} 个"
                                  "（未施加结构化 edits，未写用例态台账）"
                                  if copied else
                                  "N6_apply：drill 夹具无沙箱件 ⇒ 显式 no-op"
                              ),
                          },
                          refs=[str(sandbox_lib)] if copied else [])
        return payload

    # ---------------------------------------------------------------- real
    author = data.get_state("n6_author") or {}
    targets_state = data.get_state("n6_targets") or {}
    targets = [t for t in (targets_state.get("targets") or []) if t.get("case")]
    if not targets:
        ctx.node_failed("N6_apply", message="没有目标用例（n6_targets 为空）⇒ 不得进入 N7")
        raise RuntimeError("N6_apply：目标用例集为空（N5 必改清单为空或未产出）")

    if author.get("mode") == "standin" or author.get("model_call_failed"):
        ctx.node_failed("N6_apply", message="real 模式下 N6 无真实模型输出 ⇒ 不得凭空写沙箱")
        raise RuntimeError("N6_apply：real 模式要求结构化模型输出（standin 不允许写沙箱）")
    validation = author.get("validation") or {}
    if validation.get("ok") is not True:
        problems = validation.get("problems") or ["未知校验失败"]
        ctx.node_failed("N6_apply", message=f"N6 输出校验未通过：{problems[:3]}")
        raise ValueError(f"N6_apply：N6 输出未通过 Host 校验：{problems[:5]}")

    author_data = author.get("data") if isinstance(author.get("data"), dict) else {}
    revisions = [r for r in (author_data.get("revisions") or []) if isinstance(r, dict)]
    by_case: dict[str, dict[str, Any]] = {}
    for rev in revisions:
        case = str(rev.get("case") or "")
        if case in by_case:
            ctx.node_failed("N6_apply", message=f"重复的 revision：{case}")
            raise ValueError(f"N6_apply：用例 {case} 出现多条 revision（每个目标用例恰好一条）")
        by_case[case] = rev

    target_cases = [str(t["case"]) for t in targets]
    missing = [c for c in target_cases if c not in by_case]
    extra = [c for c in by_case if c not in target_cases]
    if missing:
        ctx.node_failed("N6_apply", message=f"缺少目标用例的 revision：{missing}")
        raise ValueError(f"N6_apply：以下目标用例没有 revision：{missing}")
    if extra:
        ctx.node_failed("N6_apply", message=f"revision 含非目标用例：{extra}")
        raise ValueError(f"N6_apply：revision 含非目标用例：{extra}")

    repo_root = Path(data.require_resource("repo_root"))
    # S6/DS-06：**有候选 ⇒ 先导入再应用**（导入是纯判据、零写入；被拒即显式失败）。
    # 无候选四键 ⇒ `candidate_plan` 返回 None，既有语义与 drill 分支完全不变。
    plan = candidate_plan(author)
    imported: dict[str, CI.ImportedCandidate] = {}
    candidate_record: dict[str, Any] | None = None
    if plan is not None:
        imported, candidate_record = _import_candidates_or_fail(ctx, plan, targets, repo_root)
    _ensure_case_state(ctx)
    sandbox_lib.mkdir(parents=True, exist_ok=True)
    applied: list[dict[str, Any]] = []

    for target in targets:
        case = str(target["case"])
        rev = by_case[case]
        edits = [e for e in (rev.get("edits") or []) if isinstance(e, dict)]
        if not edits:
            ctx.node_failed("N6_apply", message=f"{case} 的 edits 为空")
            raise ValueError(f"N6_apply：{case} 的 edits 为空（至少一条）")
        source = ctx.environment.source_case_path(repo_root, target)
        if not source.is_file():
            ctx.node_failed("N6_apply", message=f"源用例不存在：{source}")
            raise FileNotFoundError(f"N6_apply：源用例不存在：{source}")
        text = source.read_text(encoding="utf-8", errors="strict")
        md5_before = md5_file(source)
        new_text, applied_edits = apply_edits(text, edits, case=case)
        candidate = imported.get(case)
        if candidate is not None:
            # **关键防线**：候选内容必须等于 apply(基线, edits) 的结果 —— 否则候选绕过了
            # `apply_edits` 的唯一命中判据（DS-06「候选文件不能绕过 edits/目标范围/源指纹校验」）。
            applied_md5 = hashlib.md5(new_text.encode("utf-8")).hexdigest()
            if applied_md5 != candidate.md5:
                ctx.node_failed(
                    "N6_apply",
                    message=(f"{case} 候选内容与 edits 施加结果不一致"
                             f"（{CI.RejectReason.EDITS_MISMATCH.value}）：候选 {candidate.md5} "
                             f"≠ 施加 {applied_md5}"),
                )
                raise ValueError(
                    f"N6_apply：候选内容与 edits 施加结果不一致"
                    f"（{CI.RejectReason.EDITS_MISMATCH.value}）：{case}"
                )
        dest = sandbox_lib / source.name
        if dest.exists():
            dest.chmod(0o644)
        dest.write_text(new_text, encoding="utf-8")
        md5_after = md5_file(dest)
        if md5_after == md5_before:
            ctx.node_failed("N6_apply", message=f"{case} 施加后 md5 未变（空改动）")
            raise ValueError(f"N6_apply：{case} 施加后 md5 未变")
        dest.chmod(0o444)

        set_res = run_kb_tool(
            "case_state.py",
            [
                "set", "--run", ctx.run_id, *_case_state_args(ctx),
                "--case", case,
                "--state", "已修订待验",
                "--file", str(target.get("file") or f"TESTLIB/{source.name}"),
                "--md5-before", md5_before,
                "--md5-after", md5_after,
                "--sandbox-path", str(dest),
                "--note", f"N6_apply：施加 {len(applied_edits)} 条 edits（Host 校验 old 唯一命中）",
                "--updated-by", "loop:N6_apply",
            ],
        )
        if set_res["rc"] != 0:
            # 记账失败 ⇒ 沙箱件不得留在"看起来已应用"的状态
            dest.chmod(0o644)
            dest.unlink(missing_ok=True)
            ctx.node_failed("N6_apply", message=f"case_state set rc={set_res['rc']}（{case}）")
            raise RuntimeError(
                f"N6_apply：case_state set 失败 rc={set_res['rc']}: {set_res['stderr_tail'][-400:]}"
            )
        record: dict[str, Any] = {
            "case": case,
            "file": str(target.get("file") or f"TESTLIB/{source.name}"),
            "sandbox_path": str(dest),
            "md5_before": md5_before,
            "md5_after": md5_after,
            "edits": len(applied_edits),
            "applied_edits": applied_edits,
            "case_state_rc": set_res["rc"],
            # 候选导入过 == 沙箱件内容 == 候选快照；否则如实标 env_root（既有语义）
            "source": "candidate_import" if candidate is not None else "env_root",
            "rationale": str(rev.get("rationale") or ""),
        }
        if candidate is not None:
            record["candidate"] = {
                "path": candidate.path,
                "md5": candidate.md5,
                "size": candidate.size,
                "baseline_md5": candidate.baseline_md5,
                "execution_state": (candidate_record or {}).get("execution_state"),
            }
        applied.append(record)

    payload = {
        "run_id": ctx.run_id,
        "mode": ctx.mode,
        "status": "applied",
        "sandbox_root": str(ctx.run_dir / "sandbox"),
        "cases": applied,
        "targets": targets,
        "count": len(applied),
        "case_state_path": str(ctx.run_dir / "case_states.json"),
    }
    if candidate_record is not None:
        # 结构化导入结论（ok/reason/execution_state/drift_checked/文件清单及哈希）
        payload["candidate_import"] = candidate_record
    await data.async_set_state("n6_applied", payload)
    edits_total = sum(c["edits"] for c in applied)
    detail: dict[str, Any] = {
        "status": "applied",
        "cases": len(applied),
        "edits": edits_total,
        # P-21：逐用例修改清单（与 N6 同源）+ 实际写入的用例名
        "case_edits": case_edits_from_output(author_data),
        "applied_cases": [str(c["case"]) for c in applied if c.get("case")],
        "source": "framework",
        "summary": (
            f"N6_apply：{len(applied)} 个用例写入沙箱，共施加 {edits_total} 条 edits"
            "（old 唯一命中校验 + 冻结 md5 + 用例态记账）"
        ),
    }
    if candidate_record is not None:
        detail["candidate_import"] = candidate_record
    ctx.node_finished(
        "N6_apply",
        detail=detail,
        refs=[c["sandbox_path"] for c in applied],
    )
    return payload
