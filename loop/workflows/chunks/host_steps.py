"""Host 确定性节点：N0 / N1 / N2 / N5 / N6_apply / N7 / N16。

这些节点**只调用既有 `kb/tools/*.py` / `kb/tools/run_guarded.sh`**，不重新实现业务判定
（业务权威在 kb 工具里，编排层不复制）。

本轮修复要点（审计 2026-10-19 §3）：
- **#6 N1（A19）**：`n1_snapshot.py stage` 必须带 `--parent`；新增 staged 输入约定
  `run_dir/staged/{RTL,doc,regmap.json}` —— 存在则用 `--rtl-src/--doc-src/--regmap`
  并做完整性校验，不存在则用 ENV_ROOT 现态。
- **#3 N6 沙箱（A6/B3）**：新增 `n6_apply` —— 模型只出结构化 edits，Host 逐条校验
  `old` 在声明行唯一命中后施加，只写 `run_dir/sandbox/TESTLIB/*.sv`，冻结 md5 并
  调 `kb/tools/case_state.py set` 记账（I2 写入者）。drill 分支直接采用夹具沙箱件。
- **#7 N7（A5/I12）**：真实调用 `run_guarded.sh --mode compile-only`（每个目标用例、
  沙箱件），rc!=0 ⇒ node_failed；落编译证据；走单槽短租约（finally release）。
- **N16**：I4 由 kb 工具**无条件**校验（chunk 不再按 G3 分流）；身份来自 G3 签署记录，
  缺失 fail closed（不再硬编码 human）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from host import paths as P

from ..context import RunCtx, ctx_of
from .model_common import case_edits_from_output

#: 节点 → 落盘产物名
ARTIFACTS = {
    "n1": "n1_manifest_new.json",
    "n2": "n2_diff.json",
    "n5": "n5_impact.json",
    "n16": "n16_promote.json",
    "n3": "n3_digest.md",
    "n10": "n10_reconcile.md",
    "n12": "n12_report.md",
}

#: staged 输入约定：run_dir/staged 下必须成对提供新 RTL 镜像与文档（含同版本 regmap）。
STAGED_DEFAULT_RTL = ("RTL/SRC/imports", "RTL/RTL_COMMON")


# ---------------------------------------------------------------- 子进程


def run_kb_tool(tool: str, args: list[str], *, timeout: float | None = None) -> dict[str, Any]:
    """以子进程调用 kb 工具；rc 语义由工具自己定义（3 = 铁律拒绝，不是崩溃）。"""
    # `-B`：`kb/tools/` 是冻结目录，子进程导入 kb_lib 时不得写出 `__pycache__`。
    cmd = [sys.executable, "-B", str(P.KB_TOOLS / tool), *args]
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


def run_guard(args: list[str], *, timeout: float | None = None) -> dict[str, Any]:
    """调用 `kb/tools/run_guarded.sh`（身份头 / 先归档再删 / 中止自愈 / 串行锁的唯一入口）。

    单测通过 monkeypatch 本函数注入 fake runner，**不跑真仿真**。
    """
    cmd = ["bash", str(P.KB_TOOLS / "run_guarded.sh"), *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(P.REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        rc = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        rc = -9
        stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = f"TimeoutExpired: {exc}"
    return {
        "cmd": " ".join(cmd),
        "rc": rc,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-2000:],
    }


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _sandbox_lib(ctx: RunCtx) -> Path:
    return ctx.run_dir / "sandbox" / "TESTLIB"


def _selected_baseline(data: Any, node: str) -> str:
    """基线身份的**唯一解析**：`run_meta` → 运行输入 → **fail closed**。

    入口（`RunManager.start`）已把缺省语义定为 `v0` 并写进 `RunDoc`/`run_meta`；
    节点层不再各自兜底 `v0`（旧实现 N1/N2 各有一份 `or "v0"`，正是身份漂移的来源）。
    """
    run_meta = data.get_state("run_meta") or {}
    value = run_meta.get("baseline")
    if not value and isinstance(data.input, dict):
        value = data.input.get("baseline")
    text = str(value).strip() if value is not None else ""
    if not text:
        ctx_of(data).node_failed(node, message=f"{node}：缺基线身份（run_meta/input 均未给出）")
        raise RuntimeError(f"{node}：缺基线身份，拒绝按默认值继续")
    return text


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

    baseline_value = data.input.get("baseline") if isinstance(data.input, dict) else None
    payload = {
        "run_id": ctx.run_id,
        "run_dir": str(ctx.run_dir),
        "mode": ctx.mode,
        "baseline": baseline_value,
        "gate_init_rc": gate_init["rc"],
    }
    await data.async_set_state("run_meta", payload)
    # §10.4：N0 必须给 baseline + source + summary（drill 必须能看出是夹具）。
    if ctx.mode == "drill":
        source = "drill_fixture"
        # 裁决 #6（P-01 A）：新 run 的 drill 措辞改为「预置数据（夹具）初始化」（旧 run 不回填）。
        summary = (f"N0：预置数据（夹具）初始化（复制 {len(copied)} 个夹具文件，"
                   f"复制清单 {len(_drill_files())} 项），gate.py init rc={gate_init['rc']}，"
                   f"baseline={baseline_value}")
    else:
        source = "kb_tool"
        summary = (f"N0：真实运行目录初始化（未复制夹具），gate.py init rc={gate_init['rc']}，"
                   f"baseline={baseline_value}")
    ctx.node_finished(
        "N0",
        detail={
            "mode": ctx.mode,
            "fixture_files": len(copied),
            "gate_init_rc": gate_init["rc"],
            "baseline": baseline_value,
            "source": source,
            "summary": summary,
        },
        refs=[str(ctx.run_dir)],
    )
    return payload


def _drill_files() -> tuple[str, ...]:
    from ..context import DRILL_FILES

    return DRILL_FILES


# ---------------------------------------------------------------- N1


def staged_inputs(ctx: RunCtx) -> dict[str, Any]:
    """解析并**完整性校验** `run_dir/staged/` 约定。

    约定（本层新增，供 real 模式摄入新 RTL 包 + 新文档）：
      staged/RTL/SRC/imports/**, staged/RTL/RTL_COMMON/**   （完整镜像，缺一即失败）
      staged/doc/<唯一一份 .md> 或 staged/doc.md
      staged/regmap.json          （与 staged 文档同版本；缺则失败，防止用旧位定义索引）

    返回 `{present: False}` 表示未提供 staged（用 ENV_ROOT 现态）；
    提供了但不完整 ⇒ 抛 FileNotFoundError（调用方 node_failed，不猜、不回落）。
    """
    staged = ctx.run_dir / "staged"
    if not staged.is_dir():
        return {"present": False, "staged_dir": str(staged)}

    problems: list[str] = []
    rtl_args: list[str] = []
    for rel in STAGED_DEFAULT_RTL:
        src = staged / rel
        if not src.is_dir():
            problems.append(f"缺 {src}（staged RTL 必须是默认摄入范围的完整镜像）")
            continue
        if not any(src.iterdir()):
            problems.append(f"{src} 为空目录")
            continue
        # n1_snapshot 的映射语法：绝对路径=DEST_REL（否则 tar 里会出现绝对路径/暂存路径）
        rtl_args.append(f"{src}={rel}")

    doc_src: str | None = None
    doc_dir = staged / "doc"
    if doc_dir.is_dir():
        docs = sorted(doc_dir.glob("*.md"))
        if len(docs) == 1:
            doc_src = str(docs[0])
        elif not docs:
            problems.append(f"{doc_dir} 下没有 .md 文档")
        else:
            problems.append(f"{doc_dir} 下必须恰好 1 份 .md（实际 {len(docs)}）")
    elif doc_dir.is_file():
        doc_src = str(doc_dir)
    elif (staged / "doc.md").is_file():
        doc_src = str(staged / "doc.md")
    else:
        problems.append(f"缺 staged 文档（{doc_dir} 或 staged/doc.md）")

    regmap = staged / "regmap.json"
    if doc_src and not regmap.is_file():
        problems.append(f"staged 文档存在但缺 {regmap}（文档指纹必须与位定义索引同版本）")
    if problems:
        raise FileNotFoundError("staged 输入不完整：" + "；".join(problems))
    return {
        "present": True,
        "staged_dir": str(staged),
        "rtl_src": rtl_args,
        "doc_src": doc_src,
        "regmap": str(regmap),
    }


def _fmt_value(value: Any) -> str:
    """把产物里的值写进一行摘要：缺失就写"未下发"，不猜、不补默认值。"""
    return "未下发" if value is None or value == "" else str(value)


def _short_digest(value: Any) -> str:
    """摘要里只放前 12 位（完整值仍在 `detail` 里，可审计）。"""
    text = "" if value is None else str(value)
    if not text:
        return "未下发"
    return text[:12] + "…" if len(text) > 12 else text


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    """N1 manifest 摘要（条目数/指纹/冻结数/commit 可解析性）—— 全部取自产物字段本身。"""
    allfiles = manifest.get("allfiles_manifest") or {}
    cases = manifest.get("cases_freeze") or {}
    doc_fp = manifest.get("doc_fingerprint") or {}
    commit = manifest.get("commit") or {}
    return {
        "allfiles_entries": allfiles.get("entries"),
        "allfiles_sha256": allfiles.get("sha256"),
        "cases_frozen": cases.get("entries"),
        "doc_fingerprint": doc_fp.get("value"),
        "commit_parseable": commit.get("parseable"),
    }


async def n1_manifest(data: Any) -> dict[str, Any]:
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
            staged = staged_inputs(ctx)
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


# ---------------------------------------------------------------- N2


async def n2_diff(data: Any) -> dict[str, Any]:
    """N2 差异对比。

    退出码语义**只以 `kb/tools/n2_diff.py` 为准**（SPEC-REV-01 §D E1）：
    `0` 成功；`3` = blocking 输入缺口（**不产出** `n2_diff.json`，写 `n2_diff.gap.json/.md`）；
    `4` = selfcheck 失败。因此 3/4 都必须显式失败——不得把"没产出差异清单"当成"0 条差异"。
    """
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
        # 身份单一来源（编排规格 §3.1）：入口解析一次，N0 写 run_meta，N1/N2 消费同一值。
        # 旧实现这里硬编码 "v0" ⇒ 选 v-next 仍按 v0 做 diff；现在缺身份即 fail closed。
        from_baseline = _selected_baseline(data, "N2")
        run = run_kb_tool(
            "n2_diff.py",
            ["--from-baseline", from_baseline, "--to-manifest", str(ctx.run_dir / ARTIFACTS["n1"]),
             "--run", ctx.run_id, "--out-dir", str(ctx.run_dir)],
        )
        result.update(run)
        result["source"] = "kb_tool"
        if run["rc"] == 3:
            gap = ctx.run_dir / "n2_diff.gap.json"
            ctx.node_failed(
                "N2",
                message=("N2 存在 blocking 输入缺口（n2_diff rc=3），本轮未产出 n2_diff.json；"
                         f"缺口报告 = {gap}（不得当成『0 条差异』）"),
            )
            raise RuntimeError(
                "n2_diff rc=3：blocking 输入缺口，未产出 n2_diff.json（见 n2_diff.gap.json）"
            )
        if run["rc"] != 0:
            ctx.node_failed("N2", message=f"n2_diff rc={run['rc']}")
            raise RuntimeError(f"n2_diff rc={run['rc']}")

    doc = _load_json(target) or {}
    diffs = doc.get("diffs", []) if isinstance(doc, dict) else []
    pending = [d.get("entry_id") or d.get("id") for d in diffs if d.get("unresolved")]
    offsets = doc.get("offsets") if isinstance(doc, dict) else None
    result.update(
        {
            "has_change": doc.get("has_change"),
            "diff_count": len(diffs),
            "diff_ids": [d.get("entry_id") or d.get("id") for d in diffs][:20],
            "pending_entries": pending,
            # WS-L 的 G1 前置/派生也消费逐条 diffs（与 run_dir/n2_diff.json 同源，双读容错）
            "diffs": diffs,
            "self_check_ok": (doc.get("checks") or {}).get("self_check_ok"),
            # §10.4：三路统计原样取自 N2 产物（`routes` 是工具给出的逐路结论，不重算）。
            "routes": doc.get("routes") if isinstance(doc, dict) else None,
            "offsets": offsets if isinstance(offsets, list) else [],
            "unresolved_count": len(pending),
        }
    )
    kind_counts: dict[str, int] = {}
    for item in diffs:
        key = str(item.get("kind") or "unknown")
        kind_counts[key] = kind_counts.get(key, 0) + 1
    kinds_text = "、".join(f"{k} {v}" for k, v in sorted(kind_counts.items())) or "无"
    result["summary"] = (
        f"N2：差异 {len(diffs)} 条（{kinds_text}），未决 {len(pending)} 条，"
        f"offset {len(result['offsets'])} 条；has_change={doc.get('has_change')}，"
        f"self_check_ok={result['self_check_ok']}"
    )
    await data.async_set_state("n2_diff", result)
    ctx.node_finished("N2", detail=result, refs=[str(target)])
    return result


# ---------------------------------------------------------------- N5


def _to_check_fields(doc: Any) -> dict[str, Any]:
    """N5 待查条目投影（P-19）：只从产物 `to_check` 取，不解析 stdout、不猜数字。

    - `to_check_count`：产物 `to_check` 的**条目数**（与 `must_change_count` 同口径）；
    - `to_check_cases`：去重后的**用例名**；
    - `to_check_case_count`：去重用例数（面板 headline 要的「另有 N 个待查（用例）」）。
    `to_check` 不是列表（含产物没有该键）⇒ 三个值全显式 None/[]，不写 0 冒充"没有待查"。
    """
    to_check = doc.get("to_check") if isinstance(doc, dict) else None
    if not isinstance(to_check, list):
        return {"to_check_count": None, "to_check_cases": [], "to_check_case_count": None}
    cases = sorted({
        str(item.get("case")) for item in to_check
        if isinstance(item, dict) and item.get("case")
    })
    return {"to_check_count": len(to_check), "to_check_cases": cases,
            "to_check_case_count": len(cases)}


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
    index_gaps = doc.get("index_gaps", [])
    # P-19：待查条目**只从 N5 产物 `to_check` 取**（不解析 stdout、不猜数字）。
    result.update(
        {
            "must_change_count": len(must_change),
            "must_change_cases": sorted({m.get("case") for m in must_change if m.get("case")}),
            "index_complete": doc.get("index_complete"),
            "index_gaps": index_gaps,
            # §10.4：索引缺口计数（取自 N5 产物自身，不重算判据）
            "index_gap_count": len(index_gaps) if isinstance(index_gaps, list) else 0,
            # P-19：待查条目数 / 去重用例数 / 用例名
            **_to_check_fields(doc),
        }
    )
    gap_count = result["index_gap_count"]
    cases_text = "、".join(result["must_change_cases"]) or "无"
    result["summary"] = (
        f"N5：必改 {result['must_change_count']} 个用例（{cases_text}），"
        f"索引缺口 {gap_count} 条，index_complete={result['index_complete']}；"
        f"gate1 签署校验 rc={result['gate1_rc']}"
    )
    await data.async_set_state("n5_impact", result)
    ctx.node_finished("N5", detail=result, refs=[str(target)])
    return result


# ---------------------------------------------------------------- N6_apply


def _case_state_args(ctx: RunCtx) -> list[str]:
    """用例态台账的唯一写者：`kb/tools/case_state.py`。

    显式 `--state-file` 指向本 run 目录：测试可落到 tmp_path，
    生产下落点仍是 `run_dir/case_states.json`（与 N16 前置检查同源）。
    """
    return ["--state-file", str(ctx.run_dir / "case_states.json")]


def _ensure_case_state(ctx: RunCtx) -> dict[str, Any]:
    """初始化台账（已存在 ⇒ rc=3 是合法状态，不覆盖）。"""
    res = run_kb_tool("case_state.py", ["init", "--run", ctx.run_id, *_case_state_args(ctx)])
    if res["rc"] not in (0, 3):
        raise RuntimeError(f"case_state.py init rc={res['rc']}: {res['stderr_tail'][-400:]}")
    return res


def _occurrences(text: str, needle: str) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + 1


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def apply_edits(text: str, edits: list[dict[str, Any]], *, case: str) -> tuple[str, list[dict[str, Any]]]:
    """逐条校验并把 edits 施加到源码文本（**不猜**：old 必须唯一且落在声明行）。

    失败一律抛 ValueError（调用方 node_failed），不返回"尽力而为"的结果。
    """
    validated: list[tuple[int, str, str, dict[str, Any]]] = []
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise ValueError(f"{case}: edits[{i}] 不是对象")
        try:
            line = int(edit.get("line"))
        except (TypeError, ValueError):
            raise ValueError(f"{case}: edits[{i}].line 不是整数：{edit.get('line')!r}")
        old = str(edit.get("old") or "")
        new = str(edit.get("new") or "")
        basis = str(edit.get("basis") or "")
        if not old:
            raise ValueError(f"{case}: edits[{i}].old 为空")
        if old == new:
            raise ValueError(f"{case}: edits[{i}] 的 old==new（空改动不得提交）")
        if not basis.strip():
            raise ValueError(f"{case}: edits[{i}] 缺 basis（无依据的修订不得施加）")
        hits = _occurrences(text, old)
        if len(hits) != 1:
            raise ValueError(
                f"{case}: edits[{i}].old 在源文件命中 {len(hits)} 次（必须恰好 1 次，不猜）"
            )
        actual = _line_of(text, hits[0])
        if actual != line:
            raise ValueError(
                f"{case}: edits[{i}].old 实际位于第 {actual} 行，与声明的 line={line} 不符（不猜）"
            )
        validated.append((line, old, new, edit))

    out = text
    for line, old, new, _edit in sorted(validated, key=lambda x: (-x[0], -len(x[1]))):
        idx = out.find(old)
        if idx < 0:
            raise ValueError(f"{case}: 施加过程中找不到 old（第 {line} 行）：{old[:60]!r}")
        if _line_of(out, idx) != line:
            # 前面的编辑改变了行号 ⇒ 声明行与当前对象不一致，拒绝"猜位置"
            raise ValueError(f"{case}: 施加时 old 行号漂移到 {_line_of(out, idx)}（声明 {line}）")
        out = out[:idx] + new + out[idx + len(old):]
    if out == text:
        raise ValueError(f"{case}: edits 未改变文件内容")
    return out, [
        {"line": line, "old_len": len(old), "new_len": len(new), "basis": str(edit.get("basis") or "")}
        for line, old, new, edit in validated
    ]


def _source_case_path(repo_root: Path, target: dict[str, Any]) -> Path:
    rel = str(target.get("file") or "")
    case = str(target.get("case") or "")
    if rel:
        return repo_root / rel
    return repo_root / "TESTLIB" / f"{case}.sv"


async def n6_apply(data: Any) -> dict[str, Any]:
    """N6 的 **Host 沙箱写入步骤**：模型只出 edits，写盘/校验/冻结/记账都在这里。

    - 只写 `run_dir/sandbox/TESTLIB/`（不写冻结的 `TESTLIB/`）；
    - 逐条校验 `old` 在声明行唯一命中，0/多次 ⇒ fail closed；
    - 冻结 md5（写后复算，并 chmod 444）；
    - 调 `kb/tools/case_state.py set --state 已修订待验` 记账（I2 写入者）；
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
        source = _source_case_path(repo_root, target)
        if not source.is_file():
            ctx.node_failed("N6_apply", message=f"源用例不存在：{source}")
            raise FileNotFoundError(f"N6_apply：源用例不存在：{source}")
        text = source.read_text(encoding="utf-8", errors="strict")
        md5_before = md5_file(source)
        new_text, applied_edits = apply_edits(text, edits, case=case)
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
        applied.append(
            {
                "case": case,
                "file": str(target.get("file") or f"TESTLIB/{source.name}"),
                "sandbox_path": str(dest),
                "md5_before": md5_before,
                "md5_after": md5_after,
                "edits": len(applied_edits),
                "applied_edits": applied_edits,
                "case_state_rc": set_res["rc"],
                "source": "env_root",
                "rationale": str(rev.get("rationale") or ""),
            }
        )

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
    await data.async_set_state("n6_applied", payload)
    edits_total = sum(c["edits"] for c in applied)
    ctx.node_finished(
        "N6_apply",
        detail={
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
        },
        refs=[c["sandbox_path"] for c in applied],
    )
    return payload


# ---------------------------------------------------------------- N7


def _compile_evidence(evidence_dir: Path, case: str, seed: str) -> list[str]:
    """编译证据件（run_guarded compile-only 落 `*_c_rtl.log` / `*_c_tb.log`）。"""
    if not evidence_dir.is_dir():
        return []
    out: list[str] = []
    for pattern in (f"*_{case}_{seed}_c_rtl.log", f"*_{case}_{seed}_c_tb.log",
                    f"*_{case}_{seed}_c_xli_lib.log"):
        out.extend(str(p) for p in sorted(evidence_dir.glob(pattern)))
    return out


async def n7_compile(data: Any) -> dict[str, Any]:
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
            res = run_guard(
                [
                    "--case-file", str(item["sandbox_path"]),
                    "--case-name", case,
                    "--seed", "1",
                    "--mode", "compile-only",
                    "--sandbox-root", str(sandbox_root),
                    "--evidence-dir", str(evidence_dir),
                    "--run", ctx.run_id,
                ],
                timeout=900,
            )
            evid = _compile_evidence(evidence_dir, case, "1")
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


# ---------------------------------------------------------------- N16


def _first_stderr_line(text: str) -> str | None:
    """stderr 首行原文（P-34：拒绝原因取原文，不翻译、不截断成结论）。"""
    for line in (text or "").splitlines():
        if line.strip():
            return line.rstrip()
    return None


def _n16_result_path(run_dir: Path) -> Path:
    """每次晋升尝试各留一件 `n16_result.json`；已存在 ⇒ `n16_result.<n>.json`。

    刻意与"人触发真实晋升"的 `promote_result.json` 分开：dry-run 与真实晋升不得互相覆盖。
    """
    path = Path(run_dir) / "n16_result.json"
    n = 2
    while path.exists():
        path = Path(run_dir) / f"n16_result.{n}.json"
        n += 1
    return path


async def n16_promote(data: Any) -> dict[str, Any]:
    """N16 晋升新基线（人触发、Host 原子执行）。

    **I4 由 `kb/tools/n16_promote.py` 无条件校验**（审计 #13/A18）：本 chunk 不再按
    G3 决策分流 —— 手工把 `G3=milestone/defer` 当成绕过口的漏洞就在这里堵住。

    身份（#21/C9）：`--trigger-by/--actor-kind` 一律取自 G3 的权威签署记录；
    缺失即 fail closed，**不再硬编码 human**。

    **默认 `--dry-run`**：真实晋升开关属于"人点晋升"入口（API/集成轮），
    本层任何情况下都不得真的写 `kb/baselines/`；真实基线上的正确行为是 rc=3 拒绝且零副作用。
    """
    ctx = ctx_of(data)
    ctx.node_started("N16")
    decisions = data.get_state("gate_decisions") or {}
    g3 = decisions.get("G3_regression_decision") or {}
    actor = g3.get("actor")
    actor_kind = g3.get("actor_kind") or (
        "human" if str(actor or "").startswith("human") else None
    )
    if not actor or actor_kind not in ("human", "host", "rehearsal", "model"):
        ctx.node_failed("N16", message="缺少 G3 签署记录（actor/actor_kind）⇒ 身份链断裂，拒绝晋升")
        raise PermissionError(
            "N16：晋升身份必须来自 G3 签署记录（actor/actor_kind）；缺失即拒绝（不得硬编码 human）"
        )

    # I7（#22/C5/C6）：N6↔N8 与 G2 返工**分开计数**，两侧统一 `>= limit` 即不得晋升。
    # 唯一账本 = case_state 台账（n6_n8_cycles）+ 执行状态（g2_rework_cycles，gates 写入）。
    ledger_doc = _load_json(ctx.run_dir / "case_states.json") or {}
    ledger_cycles = int(((ledger_doc.get("rework_cycles") or {}).get("n6_n8_cycles")) or 0)
    limit = int(
        data.get_state("rework_limit")
        or ((ledger_doc.get("rework_cycles") or {}).get("limit"))
        or 3
    )
    g2_cycles = int(data.get_state("g2_rework_cycles") or 0)
    if ledger_cycles >= limit or g2_cycles >= limit:
        ctx.node_failed(
            "N16",
            message=(f"I7：返工超限（n6_n8_cycles={ledger_cycles}, "
                     f"g2_rework_cycles={g2_cycles}, limit={limit}）⇒ 必须人工裁决"),
        )
        raise PermissionError(
            f"I7：返工计数已达/超过上限（n6_n8_cycles={ledger_cycles}, "
            f"g2_rework_cycles={g2_cycles}, limit={limit}）⇒ 不得晋升"
        )

    args = [
        "--run", ctx.run_id,
        "--trigger-by", str(actor),
        "--actor-kind", str(actor_kind),
        "--dry-run",
    ]
    if ctx.mode == "drill":
        args += ["--baselines-root", str(ctx.run_dir / "baseline_drill")]
        (ctx.run_dir / "baseline_drill").mkdir(parents=True, exist_ok=True)
    run = run_kb_tool("n16_promote.py", args)
    status = "ok" if run["rc"] == 0 else ("refused" if run["rc"] == 3 else "failed")
    result = {"cmd": run["cmd"], "rc": run["rc"], "mode": ctx.mode, "dry_run": True,
              "actor": actor, "actor_kind": actor_kind,
              "stdout_tail": run["stdout_tail"], "stderr_tail": run["stderr_tail"],
              "source": "kb_tool",
              # P-34：拒绝原因原文（面板据此写"晋升被拒：<原因>"，不靠 stderr 尾巴猜）
              "reason_line": _first_stderr_line(run["stderr_tail"]),
              "summary": (f"N16：dry-run 晋升 rc={run['rc']}（{status}），"
                          f"actor={actor}，actor_kind={actor_kind}")}
    # P-34：每次尝试都落结果件（只增不改；已存在则加序号），并把结果件列入 refs。
    result_path = _n16_result_path(ctx.run_dir)
    result["result_artifact"] = str(result_path)
    _write_json(result_path, {"schema": "loop/n16_result", "run_id": ctx.run_id, **result})
    await data.async_set_state("n16_promote", result)
    # §10.4：refs 只列**真实存在**的晋升留痕（不存在就不进 refs，不编造证据）。
    promote_refs = [
        str(path)
        for path in (ctx.run_dir / ARTIFACTS["n16"], ctx.run_dir / "promote_result.json",
                     result_path)
        if path.is_file()
    ]
    ctx.node_finished("N16", status=status, detail=result, refs=promote_refs)
    if run["rc"] not in (0, 3):
        raise RuntimeError(f"n16_promote rc={run['rc']}")
    return result
