"""n1_manifest 节点实现。"""
from __future__ import annotations
import json
import shutil
from pathlib import Path
from typing import Any


async def run(data: Any, *, ctx_of, ARTIFACTS, _load_json, _selected_baseline, _fmt_value, _manifest_summary, _short_digest, run_kb_tool) -> dict[str, Any]:
    """N1 建立/摄取 manifest（含 parent 链）。

    real：`n1_snapshot.py stage --parent <baseline> --run <id> [staged 来源]`。
    曾因**缺 `--parent`** 导致 argparse rc=2（审计 #6/A19）——现在 parent 必填且显式落账。
    """
    ctx = ctx_of(data)
    ctx.node_started("N1")
    target = ctx.run_dir / ARTIFACTS["n1"]
    result: dict[str, Any] = {"artifact": str(target)}

    baseline = _selected_baseline(data, "N1")

    if ctx.mode == "drill":
        doc = _load_json(ctx.fixture_path("n1_manifest_new.json"))
        if doc is None:
            ctx.node_failed("N1", message="夹具缺 n1_manifest_new.json")
            raise FileNotFoundError("夹具缺 n1_manifest_new.json")
        target.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update({"parent": doc.get("parent") or baseline, "source": "drill_fixture"})
    else:
        try:
            staged = ctx.environment.staged_inputs(ctx.run_dir)
        except FileNotFoundError as exc:
            ctx.node_failed("N1", message=f"staged 输入不完整：{exc}")
            raise
        args = ["stage", "--run", ctx.run_id, "--parent", baseline]
        if staged.get("present"):
            for spec in staged["rtl_src"]:
                args += ["--rtl-src", spec]
            args += ["--doc-src", str(staged["doc_src"]), "--regmap", str(staged["regmap"])]
            args += ["--trigger-by", "loop:N1", "--actor-kind", "host"]
        run = run_kb_tool("n1_snapshot.py", args, timeout=1800)
        result.update(run)
        result["parent"] = baseline
        result["source"] = "kb_tool"
        result["staged"] = staged
        if run["rc"] not in (0, 3):
            ctx.node_failed("N1", message=f"n1_snapshot stage rc={run['rc']}")
            raise RuntimeError(
                f"n1_snapshot stage rc={run['rc']}: {run['stderr_tail'][-500:]}"
            )

    if not target.is_file():
        # 不许把"没产出 manifest"当成功（旧实现只把 node_finished 标 failed 就继续）
        ctx.node_failed("N1", message="n1_snapshot 未产出 manifest")
        raise FileNotFoundError(f"N1 未产出 {target}")
    doc = _load_json(target) or {}
    result["parent"] = doc.get("parent", result.get("parent"))
    # §10.4：N1 必须给 manifest 摘要（allfiles 条目数 + sha256、cases 冻结数、doc 指纹、
    # commit 可解析性）。数字全部来自产物自身字段，本层不新算、不猜。
    summary_fields = _manifest_summary(doc if isinstance(doc, dict) else {})
    result["manifest"] = summary_fields
    commit_state = summary_fields["commit_parseable"]
    result["summary"] = (
        f"N1：allfiles {_fmt_value(summary_fields['allfiles_entries'])} 条"
        f"（sha256 {_short_digest(summary_fields['allfiles_sha256'])}），"
        f"cases 冻结 {_fmt_value(summary_fields['cases_frozen'])} 个，"
        f"doc 指纹 {_short_digest(summary_fields['doc_fingerprint'])}，"
        f"commit "
        + ("可解析" if commit_state is True else "不可解析" if commit_state is False else "未下发")
        + f"；parent={result['parent']}"
    )
    await data.async_set_state("manifest", result)
    ctx.node_finished("N1", status="ok", detail=result, refs=[str(target)])
    return result
