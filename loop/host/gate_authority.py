"""闸门权威的唯一入口：枚举来自 `kb/tools/kb_lib.py`，行为来自 `kb/tools/gate.py`。

为什么单独一个模块：编排层**不得手抄**闸门决策枚举。
实测踩过这个坑——本层曾自造 `full_regression` / `escalate_to_human` / `ignored_with_reason`，
而权威（`kb_lib.GATE_DECISIONS`）实际是
`G3 = {full_now, subset_only, milestone_only, defer, pending}`。
自造值的后果是用户点了一个**权威不认**的决策，得到 argparse 用法错误而不是清晰的业务拒绝。

分工：
- **数据（枚举）** 取自 `kb_lib` —— 单一来源，本层不复制；
- **行为（校验/签署/anchor）** 仍走 `gate.py` CLI —— F-GATE-01/02/03 的强制都实现在那里。

权威不可读时**fail closed**：宁可报错，也不要退回一份猜测的枚举。
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from host import paths as P


class GateAuthorityUnavailable(RuntimeError):
    """无法读取闸门权威 ⇒ 拒绝继续（不猜枚举）。"""


@lru_cache(maxsize=1)
def _kb_lib():
    """加载闸门权威模块，**且不写字节码**。

    `kb/tools/` 是冻结目录：普通 `import kb_lib` 会在其中写出
    `__pycache__/kb_lib.cpython-311.pyc`（实测发生过）。
    它不改任何源文件，但确实往冻结路径写了东西 —— 与冻结守卫矛盾，故禁止。
    """
    tools = str(P.KB_TOOLS)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import importlib

        return importlib.import_module("kb_lib")
    except Exception as exc:  # pragma: no cover - 环境损坏时才走
        raise GateAuthorityUnavailable(f"无法导入 kb_lib（闸门权威）：{exc}") from exc
    finally:
        sys.dont_write_bytecode = previous


@lru_cache(maxsize=1)
def gate_ids() -> tuple[str, ...]:
    kb = _kb_lib()
    ids = tuple(getattr(kb, "GATE_IDS", ()) or ())
    if not ids:
        raise GateAuthorityUnavailable("kb_lib.GATE_IDS 为空")
    return ids


@lru_cache(maxsize=1)
def decisions() -> dict[str, tuple[str, ...]]:
    """`{gate_id: (decision, ...)}` —— 原样取自权威。"""
    kb = _kb_lib()
    raw = getattr(kb, "GATE_DECISIONS", None)
    if not isinstance(raw, dict) or not raw:
        raise GateAuthorityUnavailable("kb_lib.GATE_DECISIONS 不可用")
    return {str(k): tuple(str(x) for x in v) for k, v in raw.items()}


#: `pending` 是**状态**（尚未决策），不是可从操作台提交的动作。
NON_ACTIONABLE = frozenset({"pending"})


def actionable_decisions(gate: str) -> tuple[str, ...]:
    allowed = decisions().get(gate)
    if allowed is None:
        raise GateAuthorityUnavailable(f"权威未定义闸门 {gate!r}；已知 {sorted(decisions())}")
    return tuple(d for d in allowed if d not in NON_ACTIONABLE)


def gate_kind(gate: str) -> str:
    kb = _kb_lib()
    kinds = getattr(kb, "GATE_KIND", {}) or {}
    return str(kinds.get(gate, gate))


def is_valid_decision(gate: str, decision: str) -> bool:
    """含 `pending`：状态合法性与"可提交动作"是两件事。"""
    return decision in decisions().get(gate, ())


#: 默认期望决策（与 `gate.py require-signed --expect` 的默认一致）。
DEFAULT_EXPECT = {
    "G1_diff_confirm": "confirmed",
    "G2_report_accept": "accept",
    "G3_regression_decision": None,  # 任意已决策
}


def human_readable(gate: str, decision: str) -> str:
    """仅用于界面文案；未知值原样返回，不再自造。"""
    return {
        "confirmed": "差异确认",
        "ignored": "忽略（须给理由）",
        "disputed": "有疑义 ⇒ 转人工裁决",
        "accept": "接受报告",
        "rework": "返工",
        "full_now": "立即全量回归",
        "subset_only": "仅受影响子集回归",
        "milestone_only": "仅里程碑",
        "defer": "暂缓",
        "pending": "待决策",
    }.get(decision, decision)


def authority_view(run_id: str) -> dict[str, Any]:
    """闸门**权威**读模型：`kb_lib.gate_get` + 锚复算 `kb_lib.gate_verify_anchor`。

    为什么必须有这个（实测缺口）：操作台的「闸门历史」原先是**事件流投影** —— 其中
    `actor` 是 HTTP 请求体里的**自报字符串**，既没有 `human_signed`、也没有 `actor_kind`；
    而前端 `renderGateHistory` 恰恰在渲染 `json.actor_kind`（于是徽章永远是空的）。
    也就是说，"这道闸门到底是不是人类签的"这个操作台最该回答的问题，**在界面上无法回答**。

    权威只有一个：`kb/runs/<run_id>/gates.json`（含 `history[]` append-only）+
    同目录 `gates.sha256` 防篡改锚。本函数**只投影**，不判定、不改写：
    - 账本缺失 ⇒ `present=false`（界面显示为缺件，不编造 `pending`）；
    - 锚不一致 ⇒ `anchor_ok=false` + 明说"状态被外部修改"（不抛异常，界面要能显示它）。
    """
    kb = _kb_lib()
    try:
        st = kb.gate_get(run_id)
    except FileNotFoundError:
        return {"present": False, "run_id": run_id, "reason": "gates.json 不存在（闸门账本未初始化）",
                "gates": {}, "anchor_ok": None}
    except Exception as exc:  # pragma: no cover - 磁盘损坏时才走
        return {"present": False, "run_id": run_id, "reason": f"{type(exc).__name__}: {exc}",
                "gates": {}, "anchor_ok": None}

    try:
        anchor_ok, anchor_detail = kb.gate_verify_anchor(run_id)
    except Exception as exc:  # pragma: no cover
        anchor_ok, anchor_detail = False, f"锚复算失败：{type(exc).__name__}: {exc}"

    gates: dict[str, Any] = {}
    for gid in gate_ids():
        item = (st.get("gates") or {}).get(gid) or {}
        hist = item.get("history") or []
        gates[gid] = {
            "decision": item.get("decision"),
            "status": item.get("status"),
            "actor": item.get("actor"),
            "actor_kind": item.get("actor_kind"),
            "human_signed": item.get("human_signed"),
            "signed_at": item.get("signed_at"),
            "note": item.get("note"),
            "rework_target": item.get("rework_target"),
            "history_len": len(hist),
            # 每条历史只投影"谁在何时签了什么"，正文留给 gates.json 本体
            "history": [
                {
                    "at": h.get("at"),
                    "decision": h.get("decision"),
                    "actor": h.get("actor"),
                    "actor_kind": h.get("actor_kind"),
                    "human_signed": h.get("human_signed"),
                    "note": h.get("note"),
                }
                for h in hist
            ],
        }

    return {
        "present": True,
        "run_id": st.get("run_id"),
        "source": str(Path(str(getattr(kb, "run_dir")(run_id))) / "gates.json"),
        "schema": st.get("schema"),
        "version": st.get("version"),
        "updated_at": st.get("updated_at"),
        "gates": gates,
        "all_signed": all((gates[g]["status"] == "signed") for g in gates),
        "human_signed_all": all(bool(gates[g]["human_signed"]) for g in gates),
        # None = legacy 无锚（未校验）；False = 被外部修改；True = 一致
        "anchor_ok": anchor_ok,
        "anchor_detail": anchor_detail,
    }


__all__ = [
    "GateAuthorityUnavailable",
    "actionable_decisions",
    "authority_view",
    "decisions",
    "gate_ids",
    "gate_kind",
    "human_readable",
    "is_valid_decision",
    "DEFAULT_EXPECT",
    "NON_ACTIONABLE",
    "Path",
]
