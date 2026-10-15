"""Host 确定性节点：N0 / N1 / N2 / N5 / N7 / N16。

这些节点**只调用既有 `kb/tools/*.py`**，不重新实现业务判定
（业务权威在 kb 工具里，编排层不复制）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from host import paths as P

from ..context import RunCtx, ctx_of

#: 节点 → 落盘产物名
ARTIFACTS = {
    "n1": "n1_manifest_new.json",
    "n2": "n2_diff.json",
    "n5": "n5_impact.json",
    "n16": "n16_promote.json",
}


def run_kb_tool(tool: str, args: list[str], *, timeout: float | None = None) -> dict[str, Any]:
    """以子进程调用 kb 工具；rc 语义由工具自己定义（3 = 铁律拒绝，不是崩溃）。"""
    cmd = [sys.executable, str(P.KB_TOOLS / tool), *args]
    proc = subprocess.run(
        cmd,
        cwd=str(P.REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {
        "cmd": " ".join(cmd),
        "rc": proc.returncode,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------- N0


async def n0_baseline(data: Any) -> dict[str, Any]:
    """N0 选基线并建运行目录，同时把**权威闸门态**初始化。

    `gate.py init` 是刻意的一步：不能从夹具拷 `gates.json` 进来，
    否则「闸门已签」会凭空成立（那是本轮演练的教训面）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N0")
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if ctx.mode == "drill":
        for name in _drill_files():
            dest = ctx.copy_fixture(name)
            if dest is not None:
                copied.append(str(dest))
        ctx.notes.append(f"drill 夹具：{ctx.fixture}")

    gate_init = run_kb_tool("gate.py", ["init", "--run", ctx.run_id])
    if gate_init["rc"] not in (0, 3):
        # rc=3 = 已存在（不覆盖签署），这是合法状态，不当作失败。
        ctx.node_failed("N0", message=f"gate.py init rc={gate_init['rc']}")
        raise RuntimeError(f"gate.py init rc={gate_init['rc']}: {gate_init['stderr_tail'][-300:]}")

    payload = {
        "run_id": ctx.run_id,
        "run_dir": str(ctx.run_dir),
        "mode": ctx.mode,
        "baseline": data.input.get("baseline") if isinstance(data.input, dict) else None,
        "gate_init_rc": gate_init["rc"],
    }
    await data.async_set_state("run_meta", payload)
    ctx.node_finished(
        "N0",
        detail={"mode": ctx.mode, "fixture_files": len(copied), "gate_init_rc": gate_init["rc"]},
        refs=[str(ctx.run_dir)],
    )
    return payload


def _drill_files() -> tuple[str, ...]:
    from ..context import DRILL_FILES

    return DRILL_FILES


# ---------------------------------------------------------------- N1


async def n1_manifest(data: Any) -> dict[str, Any]:
    """N1 建立/摄取 manifest（含 parent 链）。"""
    ctx = ctx_of(data)
    ctx.node_started("N1")
    target = ctx.run_dir / ARTIFACTS["n1"]
    result: dict[str, Any] = {"artifact": str(target)}

    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n1_manifest_new.json"))
        if doc is None:
            ctx.node_failed("N1", message="夹具缺 n1_manifest_new.json")
            raise FileNotFoundError("夹具缺 n1_manifest_new.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result["parent"] = doc.get("parent")
        result["source"] = "drill_fixture"
    else:
        run = run_kb_tool("n1_snapshot.py", ["stage", "--run", ctx.run_id])
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] not in (0, 3):
            ctx.node_failed("N1", message=f"n1_snapshot rc={run['rc']}")
            raise RuntimeError(f"n1_snapshot rc={run['rc']}")

    doc = _load_json(target) or {}
    result["parent"] = doc.get("parent", result.get("parent"))
    await data.async_set_state("manifest", result)
    ctx.node_finished("N1", status="ok" if target.is_file() else "failed", detail=result, refs=[str(target)])
    return result


# ---------------------------------------------------------------- N2


async def n2_diff(data: Any) -> dict[str, Any]:
    """N2 差异对比。rc=3 是**业务码**（有差异），不是错误。"""
    ctx = ctx_of(data)
    ctx.node_started("N2")
    target = ctx.run_dir / ARTIFACTS["n2"]
    result: dict[str, Any] = {"artifact": str(target)}

    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n2_diff.json"))
        if doc is None:
            ctx.node_failed("N2", message="夹具缺 n2_diff.json")
            raise FileNotFoundError("夹具缺 n2_diff.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result["rc"] = 0
        result["source"] = "drill_fixture"
    else:
        run = run_kb_tool(
            "n2_diff.py",
            ["--from-baseline", "v0", "--to-manifest", str(ctx.run_dir / ARTIFACTS["n1"]),
             "--run", ctx.run_id, "--out-dir", str(ctx.run_dir)],
        )
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] not in (0, 3):
            ctx.node_failed("N2", message=f"n2_diff rc={run['rc']}")
            raise RuntimeError(f"n2_diff rc={run['rc']}")

    doc = _load_json(target) or {}
    diffs = doc.get("diffs", []) if isinstance(doc, dict) else []
    result.update(
        {
            "has_change": doc.get("has_change"),
            "diff_count": len(diffs),
            "diff_ids": [d.get("entry_id") or d.get("id") for d in diffs][:20],
            "pending_entries": [d.get("entry_id") or d.get("id") for d in diffs if d.get("unresolved")],
            "self_check_ok": (doc.get("checks") or {}).get("self_check_ok"),
        }
    )
    await data.async_set_state("n2_diff", result)
    ctx.node_finished("N2", detail=result, refs=[str(target)])
    return result


# ---------------------------------------------------------------- N5


async def n5_impact(data: Any) -> dict[str, Any]:
    """N5 影响分析。**只在闸门1 有权威签署后允许执行。**

    这里做的是纵深防御：即使 `gate.py` 前置校验被绕过，本节点仍会拒绝。
    """
    ctx = ctx_of(data)
    ctx.node_started("N5")
    target = ctx.run_dir / ARTIFACTS["n5"]

    signed = run_kb_tool(
        "gate.py",
        ["require-signed", "--run", ctx.run_id, "--gate", "G1_diff_confirm", "--expect", "confirmed"],
    )
    if signed["rc"] != 0:
        ctx.node_failed("N5", message=f"I1：G1 未获人类确认，拒绝进入修订阶段（rc={signed['rc']}）")
        raise PermissionError("I1：G1_diff_confirm 未获人类 confirmed 签署，N5 拒绝执行")

    result: dict[str, Any] = {"artifact": str(target), "gate1_rc": signed["rc"]}
    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n5_impact.json"))
        if doc is None:
            ctx.node_failed("N5", message="夹具缺 n5_impact.json")
            raise FileNotFoundError("夹具缺 n5_impact.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update({"rc": 0, "source": "drill_fixture"})
    else:
        run = run_kb_tool("n5_impact.py", ["--run", ctx.run_id, "--out-dir", str(ctx.run_dir)])
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] not in (0, 3):
            ctx.node_failed("N5", message=f"n5_impact rc={run['rc']}")
            raise RuntimeError(f"n5_impact rc={run['rc']}")

    doc = _load_json(target) or {}
    must_change = doc.get("must_change", []) if isinstance(doc, dict) else []
    result.update(
        {
            "must_change_count": len(must_change),
            "must_change_cases": sorted({m.get("case") for m in must_change if m.get("case")}),
            "index_complete": doc.get("index_complete"),
            "index_gaps": doc.get("index_gaps", []),
        }
    )
    await data.async_set_state("n5_impact", result)
    ctx.node_finished("N5", detail=result, refs=[str(target)])
    return result


# ---------------------------------------------------------------- N7


async def n7_compile(data: Any) -> dict[str, Any]:
    """N7 只编译（≈2 s）。短任务，可内联，不必走单槽停等。"""
    ctx = ctx_of(data)
    ctx.node_started("N7")
    sandbox = ctx.run_dir / "sandbox" / "TESTLIB"
    result: dict[str, Any] = {"sandbox": str(sandbox)}

    if ctx.mode == "drill":
        # 夹具演练轮已有卡点B 结论（rc=0 两段）；drill 直接采用夹具记录。
        text = ctx.read_fixture_text("check_C.md") or ""
        result.update({"rc": 0, "source": "drill_fixture", "check_c_present": bool(text)})
    else:
        run = run_kb_tool("compile_only.sh", []) if (P.KB_TOOLS / "compile_only.sh").is_file() else None
        result.update(run or {"rc": None, "note": "compile_only.sh 未由本层调用（真实编译经 run_guarded.sh 单槽）"})

    await data.async_set_state("n7_compile", result)
    ctx.node_finished("N7", detail=result)
    return result


# ---------------------------------------------------------------- N16


async def n16_promote(data: Any) -> dict[str, Any]:
    """N16 晋升新基线（人触发、Host 原子执行）。

    **默认 `--dry-run`**：本层在任何情况下都不得真的写 `kb/baselines/`。
    真实基线上的正确行为是 **rc=3 拒绝且零副作用**（F-N16-01/02 已实现）。
    """
    ctx = ctx_of(data)
    ctx.node_started("N16")
    decisions = data.get_state("gate_decisions") or {}
    g3 = (decisions.get("G3_regression_decision") or {}).get("decision")
    if g3 in ("full_now", "subset_only"):
        conflicts = ctx.kb.load_conflicts().get("items", [])
        blocking = [c for c in conflicts if c.get("blocks_release")]
        if blocking:
            ctx.node_failed("N16", message=f"I4：冲突未清零（{len(blocking)} 项 blocks_release），拒绝 {g3} 晋升")
            raise PermissionError("I4：冲突未清零，不得晋升")

    args = [
        "--run", ctx.run_id,
        "--trigger-by", str(data.get_state("gate_actor") or "host"),
        "--actor-kind", "human",
        "--dry-run",
    ]
    if ctx.mode == "drill":
        args += ["--baselines-root", str(ctx.run_dir / "baseline_drill")]
        (ctx.run_dir / "baseline_drill").mkdir(parents=True, exist_ok=True)
    run = run_kb_tool("n16_promote.py", args)
    result = {"cmd": run["cmd"], "rc": run["rc"], "mode": ctx.mode, "dry_run": True,
              "stdout_tail": run["stdout_tail"], "stderr_tail": run["stderr_tail"]}
    await data.async_set_state("n16_promote", result)
    status = "ok" if run["rc"] == 0 else ("refused" if run["rc"] == 3 else "failed")
    ctx.node_finished("N16", status=status, detail=result)
    if run["rc"] not in (0, 3):
        raise RuntimeError(f"n16_promote rc={run['rc']}")
    return result
