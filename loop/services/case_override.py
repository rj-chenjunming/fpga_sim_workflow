"""用例判据人签覆写服务（SPEC-REV-20 §4/§6/§7/§9）。

分工（唯一 owner）：
- **写**：`kb/tools/case_state.py override` 是台账唯一写者（追加 `overrides[]`、一次落盘、
  拒绝矩阵 §4 全在写盘前判）。本层**绝不**写 `case_states.json`。
- **判 run 状态**：O-7 是编排层事实（`run.status`），kb 不管 ⇒ 本层前置（§4-6）。
- **读**：机器原因只来自 `<run_dir>/n10_cases.json`（N10 Host 落盘），读侧唯一实现是
  `workflows.chunks.n10_semantics.load_cases`；**不**解析 `n10_reconcile.md`、不做第二套判据。
- **投影**：机器原判与人签豁免**同时**下发（O-5），`n12_report.md` 不重写、报告仍显示未通过。

错误映射（§7）：请求形状 ⇒ 400；前置矩阵 1–7 ⇒ 403（逐条写明哪一条）；台账损坏/锚复核失败
（kb rc=4）或缺件到无法判定 ⇒ 409（`reason` 明说）；其余未预期异常才 500。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from host import paths as P
from host.progress import ProgressLog

from .agent_view import GATE_NODES
from .contracts import (
    OVERRIDE_ACTIONS, OVERRIDE_WAITING_GATE, case_failures_view, case_override_view,
    case_states_view, case_waivers_view,
)

#: 覆写动作枚举（与 `kb/tools/case_state.py` 的 `--revoke` 语义一一对应）
ACTIONS: tuple[str, ...] = OVERRIDE_ACTIONS
#: 只允许在**等待闸门**时签/撤销（O-7；run 状态是编排层事实）
WAITING_GATE = OVERRIDE_WAITING_GATE
LEDGER_FILE = "case_states.json"
#: kb 工具的退出码语义（`kb/tools/case_state.py` 头部声明，不另造）
RC_OK, RC_USAGE, RC_REJECT, RC_BROKEN = 0, 2, 3, 4

#: 闸门 → 节点（事件 node 与 `gate_decided` 同风格；查不到就 None，不猜）
_NODE_BY_GATE = {gate: node for node, gate in GATE_NODES.items()}


class OverrideError(Exception):
    """覆写失败的基类（API 层据此映射 HTTP 状态码）。"""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class OverrideBadRequest(OverrideError):
    """请求体形状不对（§7 的 400）。"""

    status_code = 400


class OverrideRejected(OverrideError):
    """前置不满足（§4 的 1–7）⇒ 403；`blockers` 逐条写清是哪一条。"""

    status_code = 403

    def __init__(self, message: str, blockers: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.blockers = blockers


class OverrideConflict(OverrideError):
    """台账与机器原因件不一致到无法判定（kb rc=4）或缺件 ⇒ 409。"""

    status_code = 409

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


# ---------------------------------------------------------------- 入参


def _validate_payload(payload: dict[str, Any] | None) -> tuple[str, list[str], str, str]:
    """§7 的 400 只有形状错；actor/reason 的**语义**判据在 kb（§4-1/§4-2），这里只归一。"""
    payload = payload if isinstance(payload, dict) else {}
    action = payload.get("action")
    if action not in ACTIONS:
        raise OverrideBadRequest(
            f"action 必须是 {'/'.join(ACTIONS)}（得到 {action!r}）；撤销请用 action=\"revoke\"。")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise OverrideBadRequest("cases 必须是非空数组（批量一次签：每例一条记录、全有或全无）。")
    if not all(isinstance(case, str) and case.strip() for case in cases):
        raise OverrideBadRequest("cases 的每一项都必须是非空字符串（用例名）。")
    actor = payload.get("actor")
    reason = payload.get("reason")
    # 非字符串原样 str() 交给 kb 判（§4-1/§4-2 唯一判据不复制到本层）
    return (str(action), [str(c) for c in cases],
            "" if actor is None else str(actor),
            "" if reason is None else str(reason))


# ---------------------------------------------------------------- kb CLI


def _kb_override_args(run_id: str, ledger: Path, action: str, cases: list[str],
                      actor: str, reason: str) -> list[str]:
    args = [sys.executable, "-B", str(P.KB_TOOLS / "case_state.py"), "override",
            "--run", run_id, "--state-file", str(ledger),
            "--actor", actor, "--reason", reason]
    for case in cases:
        args += ["--case", case]
    if action == "revoke":
        args.append("--revoke")
    return args


def _clean(text: str) -> str:
    """去掉 kb 拒绝文案里的尾部「台账未写盘」宣告（保留 §4 编号与具体不满足项）。"""
    for tail in ("⇒ 台账**未写盘**", "⇒ 台账**一字节未动**", "⇒ 台账**未改动**"):
        text = text.replace(tail, "")
    return text.strip()


def _bullets(stderr: str) -> list[str]:
    """从 kb 的 `[FAIL] …` 段落里抽出逐条拒绝理由（`  - §4-x …`）。

    单条拒绝（如 §4-1/§4-2）没有 `- ` 列表形式 ⇒ 退化成那一行 `[FAIL]` 原文，
    仍然写清是哪一条（不输出"参数错误"这种笼统说法）。
    """
    out: list[str] = []
    for line in (stderr or "").splitlines():
        text = line.strip()
        if text.startswith("- "):
            out.append(_clean(text[2:]))
    if out:
        return [item for item in out if item]
    first = _clean(_first_fail(stderr))
    return [first] if first else []


def _first_fail(stderr: str) -> str:
    for line in (stderr or "").splitlines():
        text = line.strip()
        if text.startswith("[FAIL]"):
            return text[len("[FAIL]"):].strip()
    return (stderr or "").strip().splitlines()[0] if (stderr or "").strip() else "kb 拒绝（无输出）"


def _blockers(reasons: list[str], *, run_id: str, run_status: str) -> list[dict[str, Any]]:
    """与闸门端点同风格的 blockers（逐条：哪一条 §4 不满足）。"""
    items: list[dict[str, Any]] = []
    for reason in reasons or ["§4 前置不满足（kb 未给出逐条理由）"]:
        row = ""
        for token in reason.split():
            if token.startswith("§4-"):
                row = token
                break
        items.append({
            "code": f"CASE_OVERRIDE_{row.replace('§', '').replace('-', '_') or 'PRECONDITION'}",
            "severity": "blocker",
            "title": f"覆写前置不满足（{row or '§4'}）",
            "message": reason,
            "refs": [f"run={run_id}", f"run_status={run_status}"],
        })
    return items


def _run_kb(args: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=str(P.REPO_ROOT), capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as exc:  # 不吞：超时是故障，不是拒绝
        raise RuntimeError(f"kb/tools/case_state.py override 超时（{timeout}s）：{exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"kb/tools/case_state.py override 无法执行：{exc}") from exc


# ---------------------------------------------------------------- 投影


def _machine_summary(run_dir: Path, cases: list[str]) -> dict[str, Any]:
    """事件/响应里的机器原因摘要（原文 reasons，不翻译不截断）。"""
    failures = case_failures_view(run_dir)
    out: dict[str, Any] = {}
    for case in cases:
        item = (failures.get("cases") or {}).get(case) or {}
        if not item:
            out[case] = {"present": False, "machine_missing": failures.get("missing")}
            continue
        out[case] = {
            "present": True,
            "passed": item.get("passed"),
            "criterion": item.get("criterion"),
            "reasons": list(item.get("reasons") or []),
            "evidence": item.get("evidence") or {},
        }
    return out


def _summary_text(action: str, cases: list[str], actor: str, machine: dict[str, Any]) -> str:
    """一行可读 summary（与 gate_decided 的 node_finished summary 同风格）。"""
    failed = [c for c, m in machine.items() if m.get("passed") is False]
    reasons = sum(len(m.get("reasons") or []) for m in machine.values())
    what = "人签认定通过" if action == "pass" else "撤销人签豁免"
    tail = ("报告仍显示本轮未通过（n12_report.md 不重写）" if action == "pass"
            else "用例态回到「已修订待验」")
    return (f"case_override：{what} {len(cases)} 例（{actor}）；"
            f"机器原判 failed={len(failed)} 例、机器原因 {reasons} 条；{tail}")


# ---------------------------------------------------------------- 入口


def submit(
    *,
    run_id: str,
    run_dir: Path | str,
    run_status: str,
    payload: dict[str, Any] | None,
    progress: ProgressLog | None = None,
    gate: str | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """执行一次覆写动作并返回 §7 的 200 投影。

    抛 `OverrideBadRequest`（400）/ `OverrideRejected`（403）/ `OverrideConflict`（409）；
    其余异常上抛（500）。**服务层不写台账**：写盘只在 kb CLI 里发生。
    """
    action, cases, actor, reason = _validate_payload(payload)
    run_dir = Path(run_dir)

    # 台账结构性问题（不可解析 / 身份错位）⇒ 409（与 kb rc=4 同类）：先于 §4 前置判，
    # 否则会被误报成「用例不在台账」（§4-3 403），把"无法判定"伪装成"规则不满足"。
    ledger = run_dir / LEDGER_FILE
    led = case_states_view(run_dir)
    if ledger.exists() and not led.get("present"):
        raise OverrideConflict(
            f"台账不可解析 ⇒ 无法判定（{led.get('error')}）",
            reason=f"{ledger}：{led.get('error')}（拒绝改动；先修复台账或换一份副本）",
        )
    if led.get("present") and led.get("run_id") not in (None, run_id):
        raise OverrideConflict(
            f"台账身份错位：run_id={led.get('run_id')!r} != {run_id!r} ⇒ 无法判定",
            reason=(f"身份错位：{ledger} 的 run_id={led.get('run_id')!r} 与请求的 "
                    f"run_id={run_id!r} 不一致（不得用别的轮的台账签本轮）"),
        )

    # §4 前置：与只读投影**同一函数**（`contracts.case_override_view`）——不另写一套判据。
    # 被这里放行、但 CLI 仍拒绝的情形按 CLI 的 rc 透传（403/409），不吞。
    view = case_override_view(run_dir, run_status=str(run_status))
    if not view["enabled"]:
        raise OverrideRejected(
            str(view.get("blocked_reason") or "§4 前置不满足（可签性判定未通过）"),
            _blockers([str(view.get("blocked_reason") or "§4 前置不满足")],
                      run_id=run_id, run_status=str(run_status)),
        )
    problems: list[str] = []
    for case in cases:
        entry = view["cases"].get(case)
        if entry is None:
            problems.append(f"§4-3 用例 {case!r} 不在台账（覆写不新增用例）")
            continue
        verdict = (entry.get("actions") or {}).get(action) or {}
        if not verdict.get("available"):
            problems.append(str(verdict.get("blocked_reason")
                                or f"{case} 当前不可执行 {action}"))
    if problems:
        raise OverrideRejected(problems[0], _blockers(problems, run_id=run_id,
                                                     run_status=str(run_status)))

    args = _kb_override_args(run_id, ledger, action, cases, actor, reason)
    proc = _run_kb(args, timeout=timeout)

    if proc.returncode == RC_USAGE:  # 2：请求形状（kb 侧同口径）
        raise OverrideBadRequest(
            f"{_first_fail(proc.stderr)}（kb rc=2：请求形状不对，未写台账）")
    if proc.returncode == RC_REJECT:  # 3：§4 拒绝矩阵 1/2/3/4/5/7（台账一字节不动）
        reasons = _bullets(proc.stderr)
        raise OverrideRejected(
            _first_fail(proc.stderr),
            _blockers(reasons, run_id=run_id, run_status=str(run_status)),
        )
    if proc.returncode == RC_BROKEN:  # 4：台账损坏/锚复核失败（§4-8）
        raise OverrideConflict(
            f"台账/机器原因件不一致到无法判定（kb rc=4）：{_first_fail(proc.stderr)}",
            reason=(proc.stderr or "").strip() or "kb rc=4：台账损坏或缺件（无输出）",
        )
    if proc.returncode != RC_OK:  # 未预期：显式失败，不换默认值
        raise RuntimeError(
            f"kb/tools/case_state.py override rc={proc.returncode}："
            f"{(proc.stderr or proc.stdout or '').strip()[-600:]}")

    # ---- 读回投影（读侧唯一实现；不写台账、不改写机器结论）
    state_view = case_states_view(run_dir)
    state_by_case = {str(c.get("case")): c.get("state") for c in state_view["cases"]}
    machine = _machine_summary(run_dir, cases)
    waivers = case_waivers_view(run_dir)
    failures = case_failures_view(run_dir)

    warnings: list[str] = []
    if not failures.get("present"):
        # kb 已拒绝过缺件，走到这里说明读侧与写侧短暂不一致 ⇒ 显式告警（不静默）
        warnings.append(f"机器原因件读侧缺失：{failures.get('missing')}")
    for case in cases:
        summary = machine.get(case) or {}
        if summary.get("passed") is not False:
            warnings.append(
                f"{case} 的机器原判不是 failed（passed={summary.get('passed')!r}）⇒ "
                "本次覆写缺少可读的机器失败原因，请在报告中显式说明")

    _append_event(
        progress or ProgressLog(P.EVENTS_DIR, run_id),
        action=action, actor=actor, reason=reason, cases=cases,
        machine=machine, states={c: state_by_case.get(c) for c in cases},
        ledger=ledger, run_dir=run_dir, gate=gate,
    )
    return {
        "ok": True,
        "action": action,
        "results": [{"case": case, "state": state_by_case.get(case)} for case in cases],
        "case_waivers": waivers,
        "warnings": warnings,
    }


def _append_event(progress: ProgressLog, *, action: str, actor: str, reason: str,
                  cases: list[str], machine: dict[str, Any], states: dict[str, Any],
                  ledger: Path, run_dir: Path, gate: str | None) -> Any:
    """追加 `case_override` 事件（append-only、可回放；与 gate_decided 同风格）。"""
    refs = [str(ledger)]
    machine_path = run_dir / "n10_cases.json"
    if machine_path.is_file():
        refs.append(str(machine_path))
    return progress.append(
        "case_override",
        node=_NODE_BY_GATE.get(gate or ""),
        status=action,
        detail={
            "action": action,
            "actor": actor,
            "reason": reason,
            "cases": list(cases),
            "states": states,
            # 机器原因摘要（原文 reasons；机器结论未被改写）
            "machine": machine,
            "gate": gate,
            "summary": _summary_text(action, cases, actor, machine),
            "rule": ("人签例外：机器判据未改写、n12_report.md 不重写；"
                     "报告与面板必须同时显示机器原判（O-1/O-5）"),
        },
        refs=refs,
    )
