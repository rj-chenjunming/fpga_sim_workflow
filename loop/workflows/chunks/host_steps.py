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
    # SPEC-REV-20 §3.2：N10 机器原因产物（逐例判据快照，供覆写前置/面板读取）
    "n10_cases": "n10_cases.json",
    "n12": "n12_report.md",
}

#: staged 输入约定：run_dir/staged 下必须成对提供新 RTL 镜像与文档（含同版本 regmap）。


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
# 保留既有流程快照的节点源码行号。



async def n0_baseline(data: Any) -> dict[str, Any]:
    """旧图入口；保持快照身份。"""
    from ..nodes.n0 import run
    return await run(data, ctx=ctx_of(data), run_kb_tool=run_kb_tool, drill_files=_drill_files)






















































def _drill_files() -> tuple[str, ...]:
    from ..context import DRILL_FILES

    return DRILL_FILES


# ---------------------------------------------------------------- N1


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


# 保留既有流程快照的节点源码行号。


























































async def n1_manifest(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n1 import run
    return await run(data, ctx_of=ctx_of, ARTIFACTS=ARTIFACTS, _load_json=_load_json, _selected_baseline=_selected_baseline, _fmt_value=_fmt_value, _manifest_summary=_manifest_summary, _short_digest=_short_digest, run_kb_tool=run_kb_tool)
































































# ---------------------------------------------------------------- N2


async def n2_diff(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n2 import run
    return await run(data, ctx_of=ctx_of, ARTIFACTS=ARTIFACTS, _load_json=_load_json, _selected_baseline=_selected_baseline, run_kb_tool=run_kb_tool)











































































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
    """保留流程快照身份的节点入口。"""
    from ..nodes.n5 import run
    return await run(data, ctx_of=ctx_of, ARTIFACTS=ARTIFACTS, _load_json=_load_json, _to_check_fields=_to_check_fields, run_kb_tool=run_kb_tool)

























































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
                f"{case}: edits[{i}].line 声明 {line}，但 edits[{i}].old 实际位于第 {actual} 行（不猜；line 必须逐字复制 excerpts[].text 片段行首「{actual}: 」里的行号，不得自己数行、不得从 1 重排）"
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


# 保留既有流程快照的节点源码行号。








































































































































































async def n6_apply(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n6_apply import run
    return await run(data, ctx_of=ctx_of, _case_state_args=_case_state_args, _ensure_case_state=_ensure_case_state, _sandbox_lib=_sandbox_lib, apply_edits=apply_edits, case_edits_from_output=case_edits_from_output, md5_file=md5_file, run_kb_tool=run_kb_tool, candidate_plan=candidate_plan, _import_candidates_or_fail=_import_candidates_or_fail, CI=CI)










































































































































































































# ---------------------------------------------------------------- N7


# 保留既有流程快照的节点源码行号。



















































async def n7_compile(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n7 import run
    return await run(data, ctx_of=ctx_of, _case_state_args=_case_state_args, md5_file=md5_file, run_guard=run_guard, run_kb_tool=run_kb_tool)































































































































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


# 保留既有流程快照的节点源码行号。








async def n16_promote(data: Any) -> dict[str, Any]:
    """保留流程快照身份的节点入口。"""
    from ..nodes.n16 import run
    return await run(data, ctx_of=ctx_of, ARTIFACTS=ARTIFACTS, _first_stderr_line=_first_stderr_line, _load_json=_load_json, _n16_result_path=_n16_result_path, _write_json=_write_json, run_kb_tool=run_kb_tool)

from host import agent_candidate_import as CI

# ---------------------------------------------------------------- N6 候选导入（S6/DS-06）

#: `n6_author` 里候选导入的四键（**G1 冻结**，S5/S6 两侧照此写）。
#: 生产方 = dsh 结果侧（`host/agent_backends/**`，SPEC-08 §4 ResultEnvelope 的
#: "候选产物清单及哈希"）；**该接线属 S5/真机步骤，登记为缺口**，C1 由夹具注入这四键。
CANDIDATE_ROOT_KEY = "candidate_root"
CANDIDATE_MANIFEST_KEY = "candidate_manifest"
CANDIDATE_BASELINE_KEY = "baseline"
CANDIDATE_EXECUTION_KEY = "execution_state"


def candidate_plan(author: dict[str, Any]) -> dict[str, Any] | None:
    """从 `n6_author` 读四键；**全缺 ⇒ None（无候选，既有路径完全不变）**。

    任一键存在 ⇒ 走导入分支：**缺件不降级**（缺清单/缺停止确认由导入判据判成显式拒绝），
    绝不因为"导入走不通"就退回"用模型回传的 edits 直接写"（那样会绕过 DS-06 的候选核对）。
    `attempt_root` 由 `_attempt_root_for` **按布局反推**（candidate 可能在 attempt 根下，
    也可能在 `work/` 下）：反推不到 ⇒ `None` ⇒ 导入显式拒绝（fail-closed，不用 `parent` 猜）。
    """
    keys = (CANDIDATE_ROOT_KEY, CANDIDATE_MANIFEST_KEY, CANDIDATE_BASELINE_KEY,
            CANDIDATE_EXECUTION_KEY)
    if not any(key in author for key in keys):
        return None
    root_text = author.get(CANDIDATE_ROOT_KEY)
    root = Path(str(root_text)) if root_text not in (None, "") else None
    return {
        "candidate_root": root,
        "attempt_root": _attempt_root_for(root),
        "manifest": author.get(CANDIDATE_MANIFEST_KEY),
        # 封存基线（可选）：给了就逐项核对源漂移；不给则如实标 drift_checked=False
        "baseline": author.get(CANDIDATE_BASELINE_KEY),
        "execution_state": author.get(CANDIDATE_EXECUTION_KEY),
    }


def _candidate_baseline_current(manifest: Any, targets: list[dict[str, Any]],
                                repo_root: Path, ctx: RunCtx) -> dict[str, str]:
    """现算源件 md5（源漂移判据的"当前基线"）：清单 `rel_path` 的 stem ⇒ 目标用例源件。"""
    by_case = {str(target.get("case")): target for target in targets}
    current: dict[str, str] = {}
    if not isinstance(manifest, dict):
        return current
    for rel in manifest:
        if not isinstance(rel, str) or not rel.strip():
            continue
        target = by_case.get(Path(rel).stem)
        if target is None:
            continue
        source = ctx.environment.source_case_path(repo_root, target)
        if source.is_file():
            current[rel] = md5_file(source)
    return current


def candidate_dir_for_attempt(attempt_root: Path) -> Path:
    """按 attempt 布局定位候选目录：`AttemptLayout.candidate`（布局**唯一**实现）。

    本函数只转调布局，不自己拼"candidate 在哪"的规则（红线 8）。布局把候选从 attempt 根
    移到 `work/` 内时，这里与调用方都自动跟随。
    """
    from host.agent_backends import dsh_assets as A

    layout = A.AttemptLayout.under(attempt_root)
    return Path(layout.candidate)


def _attempt_root_for(candidate_root: Path | None) -> Path | None:
    """从声明候选根**反推** attempt 根：逐级找"`candidate_dir_for_attempt(x) == 声明根"的 x。

    为什么不能再用 `candidate_root.parent`：候选可能在 attempt 根下（旧形态
    `<attempt>/candidate`），也可能在 `work/` 下（新形态 `<attempt>/work/candidate`）；
    写死 parent 会在换布局后把合法候选判成越界。
    判据仍只有布局一份（`candidate_dir_for_attempt`），本函数只做反推：
    - 反推不到 ⇒ `None`（fail-closed：不退回 parent 猜测，导入会显式拒绝）；
    - **符号链接祖先不参与反推**（跳过），声明根本身是链接也不参与（导入判据另拒）。
    """
    if candidate_root is None:
        return None
    try:
        if candidate_root.is_symlink():
            return None
        declared = candidate_root.resolve()
    except OSError:
        return None
    for ancestor in (candidate_root, *candidate_root.parents):
        try:
            if ancestor.is_symlink():
                continue
            if candidate_dir_for_attempt(ancestor).resolve() == declared:
                return ancestor
        except (OSError, ValueError):
            continue
    return None


def _candidate_layout_problem(plan: dict[str, Any]) -> str | None:
    """候选根必须**等于** attempt 布局的候选目录，且 attempt 根必须由布局反推得到。

    这是"写权只在每 attempt 隔离工作区的候选目录"的接线检查；路径穿越/链接/逃逸的判据
    仍只在 `agent_candidate_import`（本层不复制）。
    """
    declared, attempt_root = plan.get("candidate_root"), plan.get("attempt_root")
    if declared is None:
        return None
    if attempt_root is None:
        return (f"候选根无法按 attempt 布局反推 attempt 根：声明 {declared}"
                f"（{CI.RejectReason.CANDIDATE_ROOT_UNSAFE.value}；fail-closed，不猜 parent）")
    expected = candidate_dir_for_attempt(Path(attempt_root))
    try:
        matches = Path(declared).resolve() == expected.resolve()
    except OSError:
        matches = False
    if matches:
        return None
    return (f"候选根与 attempt 布局不符：声明 {declared} 期望 {expected}"
            f"（{CI.RejectReason.CANDIDATE_ROOT_UNSAFE.value}；只认布局里的 candidate）")


def _import_candidates_or_fail(
        ctx: RunCtx, plan: dict[str, Any], targets: list[dict[str, Any]],
        repo_root: Path) -> tuple[dict[str, CI.ImportedCandidate], dict[str, Any]]:
    """导入候选（**零写入**）；被拒 ⇒ `node_failed` + 显式异常（不退回 edits 直接写）。

    停止事实只**消费** `plan["execution_state"]`（"已确认停止"由控制层/封存事实给出，
    `n6_apply` 不自己再判停止 —— 红线 8：同判据不出现第二套实现）。
    """
    layout_problem = _candidate_layout_problem(plan)
    if layout_problem is not None:
        ctx.node_failed("N6_apply", message=f"候选导入被拒：{layout_problem}")
        raise ValueError(f"N6_apply：候选导入被拒（reason="
                         f"{CI.RejectReason.CANDIDATE_ROOT_UNSAFE.value}）：{layout_problem}")
    result = CI.import_candidates(
        plan["candidate_root"],
        manifest=plan["manifest"],
        execution_state=plan["execution_state"],
        attempt_root=plan["attempt_root"],
        baseline=plan["baseline"],
        baseline_current=_candidate_baseline_current(plan["manifest"], targets, repo_root, ctx),
        expected_cases={str(target.get("case")) for target in targets},
    )
    if not result.ok:
        ctx.node_failed(
            "N6_apply",
            message=f"候选导入被拒（{result.reason_value}）：{result.detail}",
        )
        raise ValueError(
            f"N6_apply：候选导入被拒（reason={result.reason_value}, "
            f"resend_allowed={str(result.resend_allowed).lower()}）：{result.detail}"
        )
    return result.by_case(), result.record()
