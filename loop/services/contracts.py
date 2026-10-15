"""对外投影（服务端唯一判定处）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §10。

两条铁律：
1. **判绿/判红一律在服务端算**（前端不参与判定，防伪造）。
2. **UI 不是权威**：闸门通过以 `kb/tools/gate.py` 的 gate_state + `anchor` 为准，
   这里只是把权威的读模型投影出来；缺件一律显式登记为缺陷，**不得编造默认值**。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 实测吞吐：wall ≈ sim_time × activity factor，约 3.78–3.80 µs sim / 1 s wall。
#: **n=2**，置信低，必须在界面上标注，不得当承诺。
SIM_US_PER_WALL_S = 3.79
SIM_US_PER_WALL_S_N = 2
REWORK_LIMIT_DEFAULT = 3

Severity = str  # "blocker" | "warning" | "info" | "defect"


@dataclass
class KbSources:
    """kb/ 只读输入。缺失即显式报告，绝不回退到假值。"""

    root: Path
    conflicts: Path
    pending: Path
    baselines: Path
    conflicts_all_block_release: bool = False
    _cache: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_repo(cls, repo_root: Path) -> "KbSources":
        kb = Path(repo_root) / "kb"
        return cls(
            root=kb,
            conflicts=kb / "conflicts" / "conflicts.json",
            pending=kb / "conflicts" / "pending.json",
            baselines=kb / "baselines",
        )

    def load_conflicts(self) -> dict[str, Any]:
        if "conflicts" in self._cache:
            return self._cache["conflicts"]
        try:
            doc = json.loads(self.conflicts.read_text(encoding="utf-8"))
        except FileNotFoundError:
            doc = {"_missing": True, "items": []}
        except json.JSONDecodeError as exc:
            doc = {"_corrupt": str(exc), "items": []}
        items = doc.get("conflicts") if isinstance(doc, dict) else None
        doc["items"] = items if isinstance(items, list) else []
        self._cache["conflicts"] = doc
        return doc

    def load_rework(self, run_dir: Path | None) -> dict[str, Any]:
        if run_dir is None:
            return {"n6_n8_cycles": None, "limit": REWORK_LIMIT_DEFAULT, "source": None}
        path = Path(run_dir) / "case_states.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"n6_n8_cycles": None, "limit": REWORK_LIMIT_DEFAULT, "source": str(path), "missing": True}
        rc = doc.get("rework_cycles") or {}
        return {
            "n6_n8_cycles": rc.get("n6_n8_cycles"),
            "limit": rc.get("limit", REWORK_LIMIT_DEFAULT),
            "source": str(path),
        }

    def baseline_chain(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self.baselines.is_dir():
            return out
        for path in sorted(self.baselines.iterdir()):
            manifest = path / "manifest.json"
            if not path.is_dir() or not manifest.is_file():
                continue
            try:
                doc = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            out.append(
                {
                    "name": path.name,
                    "manifest": str(manifest),
                    "parent": doc.get("parent"),
                    "created_at": doc.get("created_at") or doc.get("generated_at"),
                }
            )
        return out


def compute_blockers(
    *,
    run_dir: Path | None,
    counts: dict[str, Any] | None,
    kb: KbSources,
    slot_status: dict[str, Any] | None,
    job: dict[str, Any] | None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    """六项信任缺口的**服务端**判定（spec §10.1）。"""
    blockers: list[dict[str, Any]] = []
    rd = Path(run_dir) if run_dir else None

    # ① I3 第 4 项：口径一 ≠ 0
    if counts is None:
        blockers.append(
            {
                "code": "I3_EVIDENCE_MISSING",
                "severity": "blocker",
                "title": "无全跑证据，判据不可判",
                "message": "尚未产出 N9 全跑日志 ⇒ 两套口径都无法取数，不得判绿。",
                "refs": [],
            }
        )
    else:
        k1 = counts.get("koutou1", {})
        k2 = counts.get("koutou2", {})
        if not k1.get("zero"):
            blockers.append(
                {
                    "code": "I3_KOUTOU1_NONZERO",
                    "severity": "blocker",
                    "title": f"口径一 = {k1.get('value')} ≠ 0（I3 第 4 项不成立）",
                    "message": (
                        "口径二为 0 **不足以**判绿。口径一由 `*E` 文本行数而来，"
                        "其非零是既有缺陷所致（本轮修订点 0x0000+0x04 未命中）。"
                        "根因方向：TB/AGENTS/PCIE-Agent/pcie_sequence.sv:598 走 uvm_info 而非 `uvm_error`。"
                    ),
                    "refs": list(k1.get("refs", []))[:5],
                }
            )
        if not k2.get("zero"):
            blockers.append(
                {
                    "code": "I3_KOUTOU2_NONZERO",
                    "severity": "blocker",
                    "title": "口径二 UVM_ERROR/UVM_FATAL ≠ 0",
                    "message": f"UVM 汇总：{k2.get('value')}",
                    "refs": list(k2.get("refs", []))[:5],
                }
            )

    # ② E-2：证据归档目录为空 ⇒ 「查看原始证据」不可得
    if rd is not None:
        archive = rd / "evidence" / "archive"
        if archive.is_dir() and not any(archive.iterdir()):
            blockers.append(
                {
                    "code": "E2_EVIDENCE_ARCHIVE_EMPTY",
                    "severity": "defect",
                    "title": "证据归档目录为空（E-2）",
                    "message": "`evidence/archive/` 无条目 ⇒ 原始证据链接不可得。界面须显式标注，不得给 404。",
                    "refs": [str(archive)],
                }
            )

    # ③ N9-3 锁格式 + F-N16-04 staging 残留
    if slot_status and slot_status.get("locked") and slot_status.get("holder_alive_known") is False:
        blockers.append(
            {
                "code": "N93_UNRECOGNIZED_LOCK_FORMAT",
                "severity": "blocker",
                "title": "单槽锁格式不可判定（N9-3）",
                "message": (
                    "锁存在但格式版本不认识 ⇒ 已**拒绝自动清理并升级人工**。"
                    "禁止用新格式判据读旧锁（本轮演练因此误删活动锁、约 10 分钟无互斥）。"
                ),
                "refs": [str(slot_status.get("holder"))],
            }
        )
    if rd is not None:
        for residue_name in ("staged", ".staging-v1"):
            residue = rd / residue_name
            if residue.is_dir() and any(residue.iterdir()):
                n = sum(1 for _ in residue.rglob("*"))
                blockers.append(
                    {
                        "code": "F_N16_04_STAGING_RESIDUE",
                        "severity": "warning",
                        "title": f"拒绝后残留 `{residue_name}/`（F-N16-04）",
                        "message": f"{residue_name}/ 残留 {n} 项；N16 拒绝路径未清理暂存区。",
                        "refs": [str(residue)],
                    }
                )

    # ④ I4：冲突清单未清零 ⇒ 阻断发版/晋升
    cdoc = kb.load_conflicts()
    items = cdoc.get("items", [])
    blocking = [i for i in items if i.get("blocks_release")]
    if cdoc.get("_missing"):
        blockers.append(
            {
                "code": "I4_CONFLICTS_MISSING",
                "severity": "blocker",
                "title": "冲突清单缺失",
                "message": f"找不到 {kb.conflicts} ⇒ I4 无法判定，按未清零处理。",
                "refs": [str(kb.conflicts)],
            }
        )
    elif blocking:
        blockers.append(
            {
                "code": "I4_CONFLICTS_UNCLEARED",
                "severity": "blocker",
                "title": f"冲突未清零：{len(blocking)}/{len(items)} 项 blocks_release",
                "message": "按 I4「清单未清零不发版」⇒ 阻断 full_now/subset_only 选项与晋升动作。",
                "refs": [str(kb.conflicts)],
                "items": [i.get("id") for i in blocking][:12],
            }
        )

    # ⑤ I7：返工计数与上限
    rework = kb.load_rework(rd)
    cycles, limit = rework.get("n6_n8_cycles"), rework.get("limit")
    if cycles is not None and limit is not None and cycles >= limit:
        blockers.append(
            {
                "code": "I7_REWORK_LIMIT",
                "severity": "blocker",
                "title": f"返工次数 {cycles} 已达上限 {limit}",
                "message": "I7：修订↔退回循环超限 ⇒ 升级人工裁决，不得自动继续。",
                "refs": [str(rework.get("source"))],
            }
        )

    # ⑥ 容量：长任务 ETA（不是阻断项，但必须显式呈现）
    if job and job.get("phase") in ("running", "cancelling"):
        blockers.append(
            {
                "code": "CAPACITY_LONG_TASK",
                "severity": "info",
                "title": "单槽被长任务占用",
                "message": (
                    f"作业 {job.get('job_id')} 运行中；ETA {job.get('eta_human')}。"
                    f"单槽原因：uvs.setup 是仓库根下全局单文件，同目录禁止并发。"
                ),
                "refs": [job.get("log_path")],
            }
        )

    if stage == "n16_promote":
        blockers = [b for b in blockers if b["code"] in ("I4_CONFLICTS_UNCLEARED", "I7_REWORK_LIMIT", "I3_EVIDENCE_MISSING")]
    return blockers


def eta_for(sim_time_us: float | None) -> dict[str, Any]:
    """按实测吞吐给 ETA。低置信必须外显。"""
    if sim_time_us is None:
        return {"eta_seconds": None, "eta_human": "未知", "basis": None, "confidence": "none"}
    seconds = sim_time_us / SIM_US_PER_WALL_S
    return {
        "eta_seconds": round(seconds, 1),
        "eta_human": humanize_seconds(seconds),
        "basis": f"{SIM_US_PER_WALL_S} µs sim / 1 s wall（n={SIM_US_PER_WALL_S_N}，低置信）",
        "confidence": "low",
    }


def humanize_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    if seconds < 90:
        return f"{seconds:.0f} s"
    minutes = seconds / 60
    if minutes < 90:
        return f"{minutes:.1f} min"
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} d"


def gate_material(
    *,
    gate: str,
    run_dir: Path | None,
    counts: dict[str, Any] | None,
    kb: KbSources,
    pending_interrupt: dict[str, Any] | None,
    job: dict[str, Any] | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """闸门材料。**只放材料，不放权限。**"""
    blockers = compute_blockers(
        run_dir=run_dir, counts=counts, kb=kb, slot_status=None, job=job, stage=stage
    )
    blocking = [b for b in blockers if b["severity"] in ("blocker", "defect")]
    return {
        "gate": gate,
        "interrupt": pending_interrupt,
        "counts": counts,
        "blockers": blockers,
        "hard_block": [b for b in blocking if b["severity"] == "blocker"],
        "defects": [b for b in blocking if b["severity"] == "defect"],
        "rework": kb.load_rework(run_dir),
        "conflicts": _conflict_summary(kb),
        "baselines": kb.baseline_chain(),
        "invariant_note": {
            "G1_diff_confirm": "I1：存在未决条目不得进入修订阶段。",
            "G2_report_accept": "I3：两套口径均为 0 才可判跑通；I4：清单未清零不发版。",
            "G3_regression_decision": "I4：冲突未清零时不得选 full_now/subset_only；I6：模型不得替人决策。",
        }.get(gate, ""),
        "actor_policy": "actor_kind 必须为 human；rehearsal/模型 actor 在 require-signed 下被拒（I6 / F-GATE-01）。",
    }


def _conflict_summary(kb: KbSources) -> dict[str, Any]:
    doc = kb.load_conflicts()
    items = doc.get("items", [])
    return {
        "total": len(items),
        "expected_total": doc.get("expected_total"),
        "blocks_release": len([i for i in items if i.get("blocks_release")]),
        "open": len([i for i in items if i.get("status") == "open"]),
        "source": str(kb.conflicts),
        "consistent": doc.get("expected_total") in (None, len(items)),
    }


def _gates_authority(run_doc: dict[str, Any]) -> dict[str, Any]:
    """闸门**权威**态 + 与事件流投影的逐门对账（F-V1-02）。

    为什么必须有：`gate_history` 是**事件流**投影 —— 里面的 `actor` 是 HTTP 请求体里的
    **自报字符串**，没有 `human_signed`、也没有 `actor_kind`；而前端 `renderGateHistory`
    恰恰在渲染 `json.actor_kind`，于是那个徽章**永远是空的**。
    操作台最该回答的问题 ——「这道闸门到底是不是人类签的、账本有没有被改过」——
    只有权威（`kb/tools/gate.py` 的 gates.json + gates.sha256）答得了。
    """
    from host import gate_authority as GA

    run_id = run_doc.get("run_id")
    if not run_id:
        return {"present": False, "reason": "无 run_id", "gates": {}, "anchor_ok": None, "divergences": []}
    try:
        auth = GA.authority_view(run_id)
    except GA.GateAuthorityUnavailable as exc:
        # 权威不可读 ⇒ fail closed：明说不可读，绝不退回一份猜测的闸门态
        return {"present": False, "reason": f"闸门权威不可读：{exc}",
                "gates": {}, "anchor_ok": None, "divergences": []}

    # 事件流（自报）vs 权威（账本）：分歧必须显式呈现，**不得静默取其一**
    history = run_doc.get("gate_history") or []
    divergences: list[dict[str, Any]] = []
    for gid, item in (auth.get("gates") or {}).items():
        evs = [e for e in history if e.get("gate") == gid]
        ev_decisions = [e.get("decision") for e in evs]
        au_decisions = [h.get("decision") for h in (item.get("history") or [])]
        if len(ev_decisions) != len(au_decisions) or ev_decisions != au_decisions:
            divergences.append({
                "gate": gid,
                "event_count": len(ev_decisions),
                "authority_count": len(au_decisions),
                "event_decisions": ev_decisions,
                "authority_decisions": au_decisions,
                "note": "事件流与权威账本不一致 ⇒ 以权威为准，并把该分歧登记为缺陷来源。",
            })

    auth["divergences"] = divergences
    return auth


def run_view(
    *,
    run_doc: dict[str, Any],
    kb: KbSources,
    slot_status: dict[str, Any],
    job: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    events: list[dict[str, Any]],
    stage: str | None = None,
) -> dict[str, Any]:
    """看板 + 操作台共用的运行视图。"""
    run_dir = Path(run_doc["run_dir"]) if run_doc.get("run_dir") else None
    counts = (evidence or {}).get("counts")
    blockers = compute_blockers(
        run_dir=run_dir, counts=counts, kb=kb, slot_status=slot_status, job=job, stage=stage
    )
    return {
        "run_id": run_doc.get("run_id"),
        "run_dir": str(run_dir) if run_dir else None,
        "baseline": run_doc.get("baseline"),
        "status": run_doc.get("status", "unknown"),
        # 失败原因必须投影出来：`status=failed` 却没有 `error`，操作台就只能显示"失败了"
        # 而说不出为什么（实测：N9 死任务 / 补投递失败 / 快照落后于账本 三条路径全都被吞掉）。
        "error": run_doc.get("error"),
        "notes": run_doc.get("notes") or [],
        "current_node": run_doc.get("current_node"),
        "mode": run_doc.get("mode", "unknown"),
        "created_at": run_doc.get("created_at"),
        "updated_at": run_doc.get("updated_at"),
        "node_history": run_doc.get("node_history", []),
        # 事件流记录（自报）：保留原样，供对账与追溯；**它不是权威**。
        "gate_history": run_doc.get("gate_history", []),
        # 权威闸门态（gates.json + gates.sha256 锚）：界面据此回答"谁签的、改没改过"。
        "gates_authority": _gates_authority(run_doc),
        "pending_interrupt": run_doc.get("pending_interrupt"),
        "counts": counts,
        "evidence": evidence,
        "job": job,
        "slot": slot_status,
        "blockers": blockers,
        "can": {
            "judge_pass": not any(b["severity"] == "blocker" for b in blockers),
            "promote": not any(
                b["code"] in ("I4_CONFLICTS_UNCLEARED", "I7_REWORK_LIMIT", "I3_EVIDENCE_MISSING")
                for b in blockers
            ),
        },
        "events": events,
        "gate_options": _gate_options(),
        "rework": kb.load_rework(run_dir),
        "conflicts": _conflict_summary(kb),
        "baselines": kb.baseline_chain(),
        "server_authority": "闸门态权威在 kb/tools/gate.py（gate_state + anchor）；本视图是只读投影。",
    }


def _gate_options() -> dict[str, list[dict[str, Any]]]:
    """把权威枚举投影给界面，使前端**无从**自造决策值。

    实测教训：本层与前端曾各自写死一份 `full_regression`，
    而权威（`kb_lib.GATE_DECISIONS`）是 `full_now`。
    现在按钮由服务端下发，前端只渲染。
    """
    from host import gate_authority as GA

    out: dict[str, list[dict[str, Any]]] = {}
    for gate in GA.gate_ids():
        out[gate] = [
            {
                "value": d,
                "label": GA.human_readable(gate, d),
                "requires_reason": d in ("ignored", "rework", "disputed"),
            }
            for d in GA.actionable_decisions(gate)
        ]
    return out
