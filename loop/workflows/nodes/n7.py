"""n7_compile 节点实现。"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any


async def run(data: Any, *, ctx_of, _case_state_args, md5_file, run_guard, run_kb_tool) -> dict[str, Any]:
    """N7 只编译卡点B（≈2 s）：真实调用 `run_guarded.sh --mode compile-only`。

    曾查一个不存在的 `compile_only.sh` 并把 `rc=None` 记录后继续（审计 #7/A5）——
    现在**每个目标用例一条 rc + 日志**，rc!=0 ⇒ node_failed；走单槽短租约，finally 释放。
    """
    ctx = ctx_of(data)
    ctx.node_started("N7")
    sandbox_root = ctx.run_dir / "sandbox"
    sandbox = sandbox_root / "TESTLIB"
    result: dict[str, Any] = {"sandbox": str(sandbox)}

    if ctx.mode == "drill":
        text = ctx.read_fixture_text("check_C.md") or ""
        result.update({"rc": 0, "source": "drill_fixture", "check_c_present": bool(text),
                       "cases": [{"case": "drill", "rc": 0, "source": "drill_fixture"}],
                       "all_ok": True,
                       "failed_cases": []})
        # R3-09：drill 也下发用例数（与 real 分支同字段名 `case_count`；`cases` 形态不动），
        # 面板/summary 才能说"N 个用例都编译通过"而不是"用例数未下发"。
        result["case_count"] = len(result["cases"])
        result["summary"] = (
            "N7：drill 编译卡点B 以夹具 check_C.md 代替（未真跑编译；"
            f"check_C.md {'存在' if text else '缺失'}）"
        )
        await data.async_set_state("n7_compile", result)
        ctx.node_finished("N7", detail=result)
        return result

    applied = data.get_state("n6_applied") or {}
    cases = [c for c in (applied.get("cases") or []) if c.get("case") and c.get("sandbox_path")]
    if not cases:
        ctx.node_failed("N7", message="没有沙箱用例（N6_apply 未产出）⇒ 不得编译/进入 N9")
        raise RuntimeError("N7：沙箱用例缺失（fail closed，禁止回退未修订 TESTLIB）")

    # 冻结 md5 复核：审的对象 == 编译的对象（改了就作废，不猜）
    for item in cases:
        path = Path(str(item["sandbox_path"]))
        if not path.is_file():
            ctx.node_failed("N7", message=f"沙箱件缺失：{path}")
            raise FileNotFoundError(f"N7：沙箱件缺失：{path}")
        now = md5_file(path)
        if item.get("md5_after") and now != item["md5_after"]:
            ctx.node_failed("N7", message=f"{item['case']} 沙箱 md5 变了（{now} != {item['md5_after']}）")
            raise RuntimeError(
                f"N7：{item['case']} 沙箱件 md5 与 N6 冻结值不符（审的 md5 != 编译的 md5）"
            )

    assert ctx.admission is not None, "real/drill 运行都必须注入 admission"
    job_id = f"N7-{ctx.run_id}"
    case_names = [str(c["case"]) for c in cases]
    slot = ctx.admission.acquire(job_id=job_id, tc=",".join(case_names), seed="1")
    if not slot.granted:
        if slot.state == "queued":
            ctx.admission.cancel_pending(job_id)
        ctx.event("admission_refused", node="N7", status="refused",
                  detail={"reason": slot.reason, "holder": slot.holder})
        ctx.node_failed("N7", message=f"单槽准入失败：{slot.reason}")
        raise PermissionError(f"N7：单槽被占用（{slot.reason}）；短编译任务不排队，fail closed")
    ctx.event("admission_granted", node="N7", status="ok", detail={"job_id": job_id, "scope": "compile-only"})

    evidence_dir = ctx.run_dir / "evidence"
    per_case: list[dict[str, Any]] = []
    try:
        for item in cases:
            case = str(item["case"])
            res, evid = ctx.environment.compile_case(
                run_guard, case=case, case_file=str(item["sandbox_path"]),
                sandbox_root=sandbox_root, evidence_dir=evidence_dir, run_id=ctx.run_id,
            )
            per_case.append(
                {
                    "case": case,
                    "rc": res["rc"],
                    "case_file": str(item["sandbox_path"]),
                    "md5": item.get("md5_after"),
                    "evidence": evid,
                    "cmd": res["cmd"],
                    "stderr_tail": res["stderr_tail"][-500:],
                }
            )
            if res["rc"] != 0:
                ctx.event("warning", node="N7", status="compile_failed",
                          detail={"case": case, "rc": res["rc"]}, refs=evid)
                ctx.node_failed("N7", message=f"{case} 编译失败 rc={res['rc']}")
                await data.async_set_state("n7_compile", {
                    **result, "rc": res["rc"], "source": "run_guarded",
                    "cases": per_case, "all_ok": False,
                    "failed_case": case,
                })
                raise RuntimeError(
                    f"N7：{case} compile-only rc={res['rc']}（看证据 {evid[:2]}）"
                )
            # 卡点B 结果写台账（I2 的证据面；态仍是「已修订待验」）
            run_kb_tool(
                "case_state.py",
                [
                    "set", "--run", ctx.run_id, *_case_state_args(ctx),
                    "--case", case, "--state", "已修订待验",
                    "--compile-rc", str(res["rc"]),
                    "--note", "N7：卡点B compile-only rc=0（run_guarded.sh）",
                    "--updated-by", "loop:N7",
                ],
            )
    finally:
        handoff = ctx.admission.release(job_id=job_id)
        if handoff:
            ctx.event("admission_granted", node="N7", status="handoff", detail=handoff)

    result.update({"rc": 0, "source": "run_guarded", "cases": per_case, "all_ok": True,
                   "slot": {"job_id": job_id, "released": True}})
    await data.async_set_state("n7_compile", result)
    failed_cases = [str(c["case"]) for c in per_case if c.get("rc") != 0]
    ctx.node_finished(
        "N7",
        detail={
            "cases": len(per_case),
            "all_ok": True,
            "case_count": len(per_case),
            "failed_cases": failed_cases,
            "source": "kb_tool",
            "summary": (
                f"N7：{len(per_case)} 个沙箱用例编译 rc=0（run_guarded compile-only，"
                f"失败 {len(failed_cases)} 例）"
            ),
        },
        refs=[p for c in per_case for p in c["evidence"]][:6],
    )
    return result
