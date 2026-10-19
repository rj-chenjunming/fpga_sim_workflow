"""人触发 N16 真实晋升（`I8`）—— Host 侧动作，不依赖 TriggerFlow 执行是否存活。

为什么单独放这里
- spec I8 要求「**人触发 + Host 原子晋升**」：晋升不是模型/脚本的自主动作，也不能因为
  执行已 close 就失去能力（跑完 → 人看报告 → 人决定晋升，这是最常见顺序）。
- 因此本模块只做三件事：**验人**（actor 以 `human` 开头且与 G3 签署者逐字一致）、
  **验闸门**（G3 已由人签署、决策允许晋升）、**调权威工具**
  （`kb/tools/n16_promote.py --promote`，七件套 + parent 链 + I4 + I7 全在工具里）。
- 它**不伪造闸门**、不写 `baselines/`（写入只由 n16 工具原子完成）、不改执行图。

失败语义
- `PromoteError`（PermissionError 子类）⇒ 409/403：人/闸门/前置不满足；
- `ValueError` ⇒ 400：参数或 run 不存在；
- 其它异常 ⇒ 500。
每次尝试（含被拒）都落 `<run_dir>/promote_result.json`（只增不改：已成功过则拒绝重复晋升）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from host import gate_authority as GA
from host import paths as P

#: 允许晋升的 G3 决策。`defer` 是「本轮不做回归」⇒ 不得晋升；`pending` 不是动作。
PROMOTABLE_G3 = ("full_now", "subset_only", "milestone_only")


class PromoteError(PermissionError):
    """人/闸门/前置不满足（应映射为 403，而不是 500）。"""


def _now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def _run_dir(run_id: str) -> Path:
    return P.KB_RUNS / run_id


def _g3_record(run_id: str) -> dict[str, Any]:
    """从**权威账本**取 G3 记录；失败一律 fail closed（不猜）。"""
    auth = GA.authority_view(run_id)
    if not auth.get("present"):
        raise PromoteError("闸门账本不可读：%s" % (auth.get("reason") or "gates.json 缺失"))
    g3 = (auth.get("gates") or {}).get("G3_regression_decision") or {}
    if g3.get("status") != "signed":
        raise PromoteError("G3_regression_decision 尚未签署（status=%r）" % g3.get("status"))
    if not g3.get("human_signed"):
        raise PromoteError("G3 不是人工签署（human_signed=false，actor_kind=%r）"
                           % g3.get("actor_kind"))
    decision = g3.get("decision")
    if decision not in PROMOTABLE_G3:
        raise PromoteError("G3 决策 %r 不允许晋升（允许：%s）" % (decision, ", ".join(PROMOTABLE_G3)))
    return g3


def promote(run_id: str, actor: str | None, reason: str | None = None,
            now: str | None = None, *, timeout: float = 300.0) -> dict[str, Any]:
    """人触发一次真实晋升；返回可审计的结果字典。"""
    if not isinstance(actor, str) or not actor.startswith("human"):
        # I6：非 human actor 不得触发晋升（与闸门同理，拒绝发生在提交前）。
        raise PromoteError("I6：晋升必须由人触发（actor 必须以 'human' 开头，实际 %r）" % (actor,))

    run_dir = _run_dir(run_id)
    if not run_dir.is_dir():
        raise ValueError("未知 run_id：%s" % run_id)
    result_path = run_dir / "promote_result.json"
    if result_path.is_file():
        prev = json.loads(result_path.read_text(encoding="utf-8") or "{}")
        if prev.get("ok"):
            raise PromoteError("本轮已成功晋升过（%s）——归档只增不改，要再晋升请新开一轮"
                               % result_path.name)

    g3 = _g3_record(run_id)
    if str(g3.get("actor")) != actor:
        raise PromoteError("触发人必须与 G3 签署者一致：G3 actor=%r，请求 actor=%r"
                           % (g3.get("actor"), actor))

    cmd = [
        sys.executable, str(P.KB_TOOLS / "n16_promote.py"),
        "--run", run_id,
        "--trigger-by", actor,
        "--actor-kind", "human",
        "--promote",
    ]
    if now:
        cmd += ["--now", now]

    proc = subprocess.run(cmd, cwd=str(P.TOOL_ROOT), capture_output=True, text=True,
                          timeout=timeout)
    rec: dict[str, Any] = {
        "schema": "loop/promote_result",
        "run_id": run_id,
        "requested_at": _now_iso(),
        "actor": actor,
        "actor_kind": "human",
        "reason": reason,
        "g3": {"decision": g3.get("decision"), "actor": g3.get("actor"),
               "human_signed": g3.get("human_signed")},
        "cmd": " ".join(cmd),
        "rc": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-4000:],
        "stderr_tail": proc.stderr[-4000:],
    }
    result_path.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if proc.returncode == 0:
        return rec
    if proc.returncode == 3:
        raise PromoteError("晋升被权威拒绝（rc=3）：%s" % (proc.stderr.strip()[-600:] or "见 promote_result.json"))
    raise RuntimeError("n16_promote 异常退出 rc=%d：%s"
                       % (proc.returncode, proc.stderr.strip()[-600:]))
