"""对外投影（服务端唯一判定处）。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §10。

两条铁律：
1. **判绿/判红一律在服务端算**（前端不参与判定，防伪造）。
2. **UI 不是权威**：闸门通过以 `kb/tools/gate.py` 的 gate_state + `anchor` 为准，
   这里只是把权威的读模型投影出来；缺件一律显式登记为缺陷，**不得编造默认值**。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import node_story
from .agent_view import STAGES, build_agents

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
    def from_workspace(cls, workspace_root: Path) -> "KbSources":
        """指向**该环境的工作区数据根**（拆仓前它恰好是 `<env>/kb/`）。

        不能再用 `repo_root/"kb"`：拆仓后环境仓里没有 kb/ 数据了，
        数据在软件侧 `workspaces/<env-id>/` 下（`environments.json` 的 `workspace`）。
        """
        base = Path(workspace_root)
        return cls(
            root=base,
            conflicts=base / "conflicts" / "conflicts.json",
            pending=base / "conflicts" / "pending.json",
            baselines=base / "baselines",
        )

    def load_conflicts(self) -> dict[str, Any]:
        """读冲突清单；**按 mtime+size 判新鲜度**，不再永久缓存（I7）。

        旧实现把结果缓存在进程级 `KbSources` 上 ⇒ I4 权威冻结在服务启动时刻：
        人工清零后仍判"未清零"，新出现的 `blocks_release` 又被忽略（放行方向不安全）。
        这里每次读盘只比一次 `stat`，内容未变就复用已解析对象（性能与新鲜度兼得），
        变了（或文件消失/重新出现）就重读。
        """
        try:
            stat = self.conflicts.stat()
            stamp: tuple[Any, ...] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        cached = self._cache.get("conflicts")
        if isinstance(cached, tuple) and cached[0] == stamp:
            return cached[1]
        if stamp is None:
            doc: dict[str, Any] = {"_missing": True, "items": []}
        else:
            try:
                doc = json.loads(self.conflicts.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                doc = {"_corrupt": str(exc), "items": []}
        items = doc.get("conflicts") if isinstance(doc, dict) else None
        doc["items"] = items if isinstance(items, list) else []
        self._cache["conflicts"] = (stamp, doc)
        return doc

    def invalidate(self) -> None:
        """丢掉所有进程级缓存（测试与"人工刚改完清单"的场景可显式调用）。"""
        self._cache.clear()

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


def _read_artifact(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    """读 run 目录里的 JSON 产物：`(doc, error)`。缺失/损坏都**显式**返回，不编造。"""
    if path is None:
        return None, "无路径"
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "缺失"
    except json.JSONDecodeError as exc:
        return None, f"不可解析：{exc}"


def _iso_epoch(value: Any) -> float | None:
    """ISO 时间 → epoch。无时区的按**本机时区**解释（时间字段只允许经单一入口注入）。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo or timezone.utc)
    return dt.timestamp()


def run_created_at(run_dir: Path | None) -> str | None:
    """本 run 的创建时刻（`<run_dir>/view.json` 的 `created_at`）。"""
    if run_dir is None:
        return None
    doc, _ = _read_artifact(Path(run_dir) / "view.json")
    return str((doc or {}).get("created_at") or "") or None


#: 报告结论的合法值（与 `loop/prompts/node_schemas.py` 的 `claimed_verdict` 同一枚举）。
REPORT_VERDICTS: tuple[str, ...] = ("passed", "not_passed", "undetermined")


def report_claimed_verdict(run_dir: Path | None) -> str | None:
    """从 `n12_report.md` 读报告自报结论（SPEC-REV-05 R1：失败报告的 accept 通道依据）。

    只认产物里的字面声明；文件缺失/无该行 ⇒ `None`（不猜、不按目录名推断）。
    该值只用于**是否要求理由**这一条前置，不参与判据（判据仍是 I2/I3/I4）。
    """
    if run_dir is None:
        return None
    path = Path(run_dir) / "n12_report.md"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(
        r"claimed_verdict\s*[：:]\s*`?(" + "|".join(REPORT_VERDICTS) + r")`?",
        text,
    )
    return match.group(1) if match else None


def diff_entries_view(run_dir: Path | None, *, mode: str | None = None) -> dict[str, Any]:
    """N2 差异清单（A1/A23：G1 材料必须逐条列出，人才能逐条确认/忽略/转人工）。

    未决条目（`unresolved` 非空）单列。drill 模式下，夹具的未决条目会被标
    `legacy_drill_fixture`：该夹具的 n2 产出于修 F-02 之前（旧编码判定），
    不能把它的历史未决当成**本轮**的未决去阻断人工闸门 —— 但材料必须如实列出。
    """
    path = Path(run_dir) / "n2_diff.json" if run_dir is not None else None
    doc, error = _read_artifact(path)
    entries: list[dict[str, Any]] = []
    if isinstance(doc, dict):
        for item in doc.get("diffs") or []:
            if not isinstance(item, dict):
                continue
            entry_id = item.get("entry_id") or item.get("id")
            unresolved = item.get("unresolved")
            entries.append(
                {
                    "entry_id": entry_id,
                    "kind": item.get("kind"),
                    "change": item.get("change"),
                    "unresolved": unresolved,
                    "evidence": item.get("evidence"),
                    "lines": item.get("lines") or [],
                    # 真实路径的 N2 用 `offsets`（复数）列表；drill 夹具用 `offset`（单数）。
                    # 投影只做兼容读取，不改产物：单数字段缺失时取列表首项，两者都保留给界面。
                    "offset": item.get("offset") or next(iter(item.get("offsets") or []), None),
                    "offsets": item.get("offsets") or [],
                    "segment": item.get("segment"),
                    # R2（SPEC-REV-01）：变更本体与解码事实必须逐条下发，界面才能双栏对照；
                    # 缺失一律显式 None（**不**用路径/空串冒充"没有变化"）。
                    "before": item.get("before"),
                    "after": item.get("after"),
                    "diff_hunk": item.get("diff_hunk"),
                    "encoding": item.get("encoding"),
                    # drill 夹具的历史未决：标注来源，不当作本轮待处置项
                    "legacy_drill_fixture": bool(unresolved) and mode == "drill",
                }
            )
    unresolved_ids = [e["entry_id"] for e in entries if e.get("unresolved")]
    return {
        "path": str(path) if path is not None else None,
        "present": isinstance(doc, dict),
        "error": error,
        "count": len(entries),
        "entries": entries,
        "unresolved_ids": unresolved_ids,
        "unresolved_count": len(unresolved_ids),
        "has_change": (doc or {}).get("has_change") if isinstance(doc, dict) else None,
        "self_check_ok": ((doc or {}).get("checks") or {}).get("self_check_ok") if isinstance(doc, dict) else None,
        "mode": mode,
    }


#: I2 的固定四态（kb/tools/case_state.py 与 kb/schema/case_states.schema.json 是权威）。
CASE_PENDING = "已修订待验"
CASE_PASS = "已验证通过"
CASE_REJECTED = "已退回"
CASE_UNTOUCHED = "未改"


def case_states_view(run_dir: Path | None, *, created_at: str | None = None) -> dict[str, Any]:
    """用例态台账读模型（A3/I2）。

    **只把"本轮写入"的条目算作本轮的待验**：drill 会把归档演练轮的
    `case_states.json` 复制进新 run 目录，那些条目是**历史件**（updated_at 早于本轮
    created_at）—— 按裸文件无条件阻断会让所有 drill 永久卡在 G2，那是把归档夹具
    当成本轮事实。历史条目仍如实进材料并标 `foreign`（可审），但不阻断。
    """
    path = Path(run_dir) / "case_states.json" if run_dir is not None else None
    doc, error = _read_artifact(path)
    created = _iso_epoch(created_at)
    cases: list[dict[str, Any]] = []
    if isinstance(doc, dict):
        for item in doc.get("cases") or []:
            if not isinstance(item, dict):
                continue
            updated = _iso_epoch(item.get("updated_at"))
            own = True if created is None else (updated is None or updated >= created)
            cases.append(
                {
                    "case": item.get("case"),
                    "state": item.get("state"),
                    "updated_at": item.get("updated_at"),
                    "updated_by": item.get("updated_by"),
                    "file": item.get("file"),
                    "own": own,
                }
            )
    pending_own = [c for c in cases if c["state"] == CASE_PENDING and c["own"]]
    pending_foreign = [c for c in cases if c["state"] == CASE_PENDING and not c["own"]]
    return {
        "path": str(path) if path is not None else None,
        "present": isinstance(doc, dict),
        "error": error,
        "created_at": created_at,
        "cases": cases,
        "count": len(cases),
        "pending_own": [c["case"] for c in pending_own],
        "pending_foreign_count": len(pending_foreign),
        "pending_foreign": [c["case"] for c in pending_foreign],
        "rework_cycles": (doc or {}).get("rework_cycles") if isinstance(doc, dict) else None,
    }


def rework_counts(run_dir: Path | None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """I7 的**分离计数**：`n6_n8_cycles`（N6↔N8）与 `g2_rework_cycles`（N13 返工）。

    唯一账本：N6↔N8 在 case_state 台账；G2 返工在 host 写下的
    `<run_dir>/rework_cycles.json`（与 execution state 同值，由 gates 写入）。
    """
    doc, error = _read_artifact(Path(run_dir) / "rework_cycles.json" if run_dir is not None else None)
    cycles_doc = dict(doc or {})
    if extra:
        for key, value in extra.items():
            if value is not None:
                cycles_doc[key] = value
    cs = case_states_view(run_dir)
    cs_cycles = (cs.get("rework_cycles") or {}) if isinstance(cs.get("rework_cycles"), dict) else {}
    n6n8 = cycles_doc.get("n6_n8_cycles")
    if n6n8 is None:
        n6n8 = cs_cycles.get("n6_n8_cycles") or 0
    g2 = cycles_doc.get("g2_rework_cycles") or 0
    limit = cycles_doc.get("limit") or cs_cycles.get("limit") or REWORK_LIMIT_DEFAULT
    return {
        "n6_n8_cycles": n6n8,
        "g2_rework_cycles": g2,
        "limit": limit,
        "source": str(Path(run_dir) / "rework_cycles.json") if run_dir is not None else None,
        "case_state_source": cs.get("path"),
        "missing": error == "缺失" and not cs.get("present"),
    }


#: 按闸门阶段裁剪 blockers（B9：G1 不评 I3 —— 那时 N9 还没发生）。
#: 值 = 该阶段**允许出现**的 blocker code。`None` = 不裁剪（看板/全局视图）。
STAGE_BLOCKER_CODES: dict[str, frozenset[str]] = {
    "n4_gate1": frozenset(
        {
            "I1_UNRESOLVED_ENTRIES",
            "I4_CONFLICTS_UNCLEARED",
            "I4_CONFLICTS_MISSING",
            "N93_UNRECOGNIZED_LOCK_FORMAT",
            "F_N16_04_STAGING_RESIDUE",
            "CAPACITY_LONG_TASK",
        }
    ),
    "n13_gate2": frozenset(
        {
            "I2_CASES_PENDING",
            "I3_EVIDENCE_MISSING",
            "I3_KOUTOU1_NONZERO",
            "I3_KOUTOU2_NONZERO",
            "I4_CONFLICTS_UNCLEARED",
            "I4_CONFLICTS_MISSING",
            "I7_REWORK_LIMIT",
            "E2_EVIDENCE_ARCHIVE_EMPTY",
            "N93_UNRECOGNIZED_LOCK_FORMAT",
            "F_N16_04_STAGING_RESIDUE",
            "CAPACITY_LONG_TASK",
        }
    ),
    "n14_gate3": frozenset(
        {
            "I2_CASES_PENDING",
            "I3_EVIDENCE_MISSING",
            "I4_CONFLICTS_UNCLEARED",
            "I4_CONFLICTS_MISSING",
            "I7_REWORK_LIMIT",
            "N93_UNRECOGNIZED_LOCK_FORMAT",
            "CAPACITY_LONG_TASK",
        }
    ),
    "n16_promote": frozenset(
        {"I2_CASES_PENDING", "I4_CONFLICTS_UNCLEARED", "I7_REWORK_LIMIT", "I3_EVIDENCE_MISSING"}
    ),
}


def compute_blockers(
    *,
    run_dir: Path | None,
    counts: dict[str, Any] | None,
    kb: KbSources,
    slot_status: dict[str, Any] | None,
    job: dict[str, Any] | None,
    stage: str | None = None,
    mode: str | None = None,
    extras: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """六项信任缺口的**服务端**判定（spec §10.1）+ I1/I2 放行前置。"""
    blockers: list[dict[str, Any]] = []
    rd = Path(run_dir) if run_dir else None
    extras = extras or {}

    # ⓪ I1：差异条目未决（A1）。real 是 blocker；drill 夹具的历史未决降为 warning。
    diff = extras.get("diff") or diff_entries_view(rd, mode=mode)
    if diff.get("present") and diff.get("unresolved_count"):
        severity = "warning" if mode == "drill" else "blocker"
        blockers.append(
            {
                "code": "I1_UNRESOLVED_ENTRIES",
                "severity": severity,
                "title": f"N2 有 {diff['unresolved_count']} 条未决差异条目",
                "message": (
                    "I1：存在未决条目不得进入修订阶段。逐条处置需经 `entry_decisions` 覆盖全部条目"
                    "（confirmed/ignored/disputed，ignored/disputed 必须带理由）；"
                    "drill 夹具的历史未决条目仅作材料展示（标 legacy_drill_fixture）。"
                ),
                "refs": [diff.get("path")] if diff.get("path") else [],
                "items": diff.get("unresolved_ids")[:12],
            }
        )

    # ⓪' I2：本轮仍存在「已修订待验」用例（A3）
    cases = extras.get("case_states") or case_states_view(rd, created_at=run_created_at(rd))
    if cases.get("pending_own"):
        blockers.append(
            {
                "code": "I2_CASES_PENDING",
                "severity": "blocker",
                "title": f"本轮仍有 {len(cases['pending_own'])} 个用例「已修订待验」",
                "message": (
                    "I2：存在「待验」不得称跑通。本轮报告结论为 not_passed ⇒ 允许「接受报告」"
                    "作为失败收口，但必须填写理由（SPEC-REV-05 R1）；N16 仍受 I3/I4 阻断。"
                    if report_claimed_verdict(rd) == "not_passed"
                    else "I2：存在「待验」不得称跑通/接受报告；先完成全跑并写入「已验证通过」。"
                ),
                "refs": [cases.get("path")] if cases.get("path") else [],
                "items": cases.get("pending_own")[:12],
            }
        )

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

    # ⑤ I7：返工计数与上限（**分离计数**：N6↔N8 与 G2 返工各自 `>= limit`）
    rework = extras.get("rework") or rework_counts(rd)
    limit = rework.get("limit") or REWORK_LIMIT_DEFAULT
    over = [
        (raw_key, rework.get(key))
        for key, raw_key in (("n6_n8_cycles", "N6↔N8"), ("g2_rework_cycles", "N13 返工"))
        if isinstance(rework.get(key), int) and rework.get(key) >= limit
    ]
    if over:
        blockers.append(
            {
                "code": "I7_REWORK_LIMIT",
                "severity": "blocker",
                "title": "；".join(f"{name} 次数 {value} 已达上限 {limit}" for name, value in over),
                "message": "I7：返工循环超限 ⇒ 升级人工裁决，不得自动继续/不得晋升。",
                "refs": [str(rework.get("source")), str(rework.get("case_state_source"))],
                "counters": {raw_key: rework.get(key) for key, raw_key in
                             (("n6_n8_cycles", "N6↔N8"), ("g2_rework_cycles", "N13 返工"))},
                "limit": limit,
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

    allowed = STAGE_BLOCKER_CODES.get(stage or "")
    if allowed is not None:
        blockers = [b for b in blockers if b["code"] in allowed]
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


#: 闸门 → 材料阶段（决定 blockers 裁剪口径与"此刻该有什么材料"）。
GATE_STAGE: dict[str, str] = {
    "G1_diff_confirm": "n4_gate1",
    "G2_report_accept": "n13_gate2",
    "G3_regression_decision": "n14_gate3",
}


def _model_node_view(state_facts: dict[str, Any], key: str) -> dict[str, Any] | None:
    """模型节点 state 的只读摘要（`mode` 三态 live/standin/failed + data 关键字段）。"""
    doc = state_facts.get(key)
    if not isinstance(doc, dict):
        return None
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    return {
        "node": key,
        "mode": doc.get("mode"),
        "standin": bool(doc.get("standin")),
        "provider": doc.get("provider"),
        "data": data,
    }


def model_modes(state_facts: dict[str, Any]) -> dict[str, str]:
    """**动态**汇总模型节点的实际 mode（删除 `standin_model_nodes=True` 硬编码，B5-A/M2）。"""
    out: dict[str, str] = {}
    for key in ("n3_digest", "n6_author", "n8_check", "n10_reconcile", "n11_review", "n12_report"):
        doc = state_facts.get(key)
        if isinstance(doc, dict) and isinstance(doc.get("mode"), str):
            out[key] = str(doc["mode"])
    return out


def _n11_conclusion(state_facts: dict[str, Any]) -> dict[str, Any] | None:
    """N11 证据守护结论（旧字段 assessment/satisfied 容错读，新字段 chain/rework_requests 优先）。"""
    view = _model_node_view(state_facts, "n11_review")
    if view is None:
        return None
    data = view["data"]
    chain = data.get("chain")
    if chain is None:
        old = str(data.get("assessment") or "").strip().lower()
        if old in ("satisfied", "needs_rework"):
            chain = "intact" if old == "satisfied" else "broken"
    rework = data.get("rework_requests")
    if rework is None and data.get("needs_rework"):
        rework = ["needs_rework（旧字段）"]
    doc = state_facts.get("n11_review") or {}
    chain_effective = doc.get("chain_effective") or chain
    return {
        "mode": view["mode"],
        "chain": chain,
        "model_chain": doc.get("model_chain") or chain,
        "chain_effective": chain_effective,
        "host_identity": doc.get("host_identity"),
        # I7/A22：N11 证据守护返工超限 ⇒ N11_ESCALATE 升级到 N13，材料必须给出原因。
        "escalated": bool(doc.get("escalated")) or (
            str(doc.get("cycle") or "") != "" and doc.get("cycle") is not None
            and int(doc.get("cycle") or 0) >= int(doc.get("limit") or REWORK_LIMIT_DEFAULT)),
        "cycle": doc.get("cycle"),
        "limit": doc.get("limit"),
        "reasons": data.get("reasons") or [],
        "rework_requests": rework or [],
        "caveats": data.get("caveats") or [],
    }


def _n8_conclusion(state_facts: dict[str, Any]) -> dict[str, Any] | None:
    """N8 静态复核结论 + 升级信息（N8_ESCALATE→gate2 时人工要看到原因）。"""
    doc = state_facts.get("n8_check")
    if not isinstance(doc, dict):
        return None
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    return {
        "mode": doc.get("mode"),
        "verdict": doc.get("verdict") or data.get("verdict"),
        "escalated": bool(doc.get("escalated")),
        "cycle": doc.get("cycle"),
        "limit": doc.get("limit"),
        "findings": data.get("findings") or [],
        "reason": doc.get("escalation_reason") or data.get("reason"),
    }


def _n12_conclusion(state_facts: dict[str, Any]) -> dict[str, Any] | None:
    """N12 报告结论（旧 verdict_statement 容错；新 claimed_verdict 优先）。"""
    doc = state_facts.get("n12_report")
    if not isinstance(doc, dict):
        return None
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    claimed = data.get("claimed_verdict")
    legacy = data.get("verdict_statement")
    return {
        "mode": doc.get("mode"),
        "claimed_verdict": claimed if claimed is not None else None,
        "legacy_verdict_statement": legacy,
        # 报告文件（A20：报告必须落盘；材料给的是路径 + 存在性，不把正文塞进协议）
        "report_path": doc.get("report_path") or data.get("report_path"),
        "refs_checked": doc.get("refs_checked"),
        "unresolved_refs": doc.get("unresolved_refs") or data.get("unresolved_refs") or [],
    }


def _latest_signing(state_facts: dict[str, Any], gate: str) -> dict[str, Any] | None:
    """本闸门最近一次决策记录（含 signed_at/reason/artifacts/entries，供 N16 消费）。"""
    decisions = state_facts.get("gate_decisions")
    if not isinstance(decisions, dict):
        return None
    item = decisions.get(gate)
    return dict(item) if isinstance(item, dict) else None


def gate_material(
    *,
    gate: str,
    run_dir: Path | None,
    counts: dict[str, Any] | None,
    kb: KbSources,
    pending_interrupt: dict[str, Any] | None,
    job: dict[str, Any] | None = None,
    stage: str | None = None,
    mode: str | None = None,
    state_facts: dict[str, Any] | None = None,
    gate_decisions: dict[str, Any] | None = None,
    cycles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """闸门材料。**只放材料，不放权限。**

    A23：三闸门必须补齐 spec 要求的输入 ——
    G1 差异清单 + 冲突快照；G2 报告 + 用例态 + 计数 + 评估结论；G3 评估结论 + 冲突态。
    缺失的件一律显式标 `missing`，**不编造**。
    """
    facts = dict(state_facts or {})
    if gate_decisions is not None:
        facts["gate_decisions"] = gate_decisions
    rd = Path(run_dir) if run_dir else None
    stage = stage or GATE_STAGE.get(gate)
    created = run_created_at(rd)
    diff = diff_entries_view(rd, mode=mode)
    cases = case_states_view(rd, created_at=created)
    rework = cycles or rework_counts(rd)
    extras = {"diff": diff, "case_states": cases, "rework": rework}
    blockers = compute_blockers(
        run_dir=rd, counts=counts, kb=kb, slot_status=None, job=job, stage=stage,
        mode=mode, extras=extras,
    )
    blocking = [b for b in blockers if b["severity"] in ("blocker", "defect")]
    conflicts = _conflict_summary(kb)
    conflict_items = kb.load_conflicts().get("items", [])
    modes = model_modes(facts)
    standin_nodes = sorted([k for k, v in modes.items() if v == "standin"]) if modes else None
    evidence_path = (rd / "evidence") if rd is not None else None
    material = {
        "gate": gate,
        "stage": stage,
        "mode": mode,
        "interrupt": pending_interrupt,
        "counts": counts,
        "blockers": blockers,
        "hard_block": [b for b in blocking if b["severity"] == "blocker"],
        "defects": [b for b in blocking if b["severity"] == "defect"],
        "rework": rework,
        # G1 输入：差异清单（逐条）+ 冲突快照
        "difference_items": diff,
        # G2/G3 输入：用例态台账（本轮/历史分离）
        "case_states": cases,
        # G2 输入：报告 + 评估结论 + 计数；G3 输入：评估结论
        "report": {
            "n2_diff": diff.get("path"),
            "n3_digest": str(rd / "n3_digest.md") if rd is not None else None,
            "n9_evidence": str(evidence_path) if evidence_path is not None else None,
            "n11_guardian": _n11_conclusion(facts),
            "n12_report": _n12_conclusion(facts),
            "n8_check": _n8_conclusion(facts),
            "n10_reconcile": _model_node_view(facts, "n10_reconcile"),
        },
        "n6_applied": facts.get("n6_applied"),
        # R2：G1 材料的两个入口（存在性探测；正文不进协议）
        "n3_digest": n3_digest_view(rd),
        "host_trace": host_trace_view(rd),
        # drill 的台账跳过标记（N8/N10 替身复核不写 case_state）——原样展示给操作员，
        # 让"I2 为什么没在这条 run 上出现"可解释（不静默省略）。
        "ledger_notes": facts.get("_ledger_notes") or [],
        "conflicts": conflicts,
        "conflict_items": [
            {"id": i.get("id"), "blocks_release": i.get("blocks_release"), "status": i.get("status")}
            for i in conflict_items[:12]
        ],
        "baselines": kb.baseline_chain(),
        # B5-A / M2：模型节点替身与否由**实际 mode**投影（不再恒 True）。
        "model_modes": modes,
        "standin_model_nodes": (bool(standin_nodes) if standin_nodes is not None else None),
        "standin_nodes": standin_nodes,
        # I1：未决条目需要逐条处置（real 严格，drill 夹具历史件只作展示）
        "entry_decisions_required": bool(diff.get("unresolved_count")) and mode != "drill",
        "unresolved_entries": diff.get("unresolved_ids", []),
        # 本闸门的决策记录（N16 消费 signed_at/reason/artifacts/entries）
        "decision_record": _latest_signing(facts, gate),
        "invariant_note": {
            "G1_diff_confirm": "I1：存在未决条目不得进入修订阶段。",
            "G2_report_accept": "I3：两套口径均为 0 才可判跑通；I2：待验用例不得称跑通；I4：清单未清零不发版。",
            "G3_regression_decision": "I4：冲突未清零时不得选 full_now/subset_only；I6：模型不得替人决策。",
        }.get(gate, ""),
        "actor_policy": "actor_kind 必须为 human；rehearsal/模型 actor 在 require-signed 下被拒（I6 / F-GATE-01）。",
    }
    material["refs"] = [
        value
        for value in (
            diff.get("path"),
            cases.get("path"),
            (material["report"].get("n3_digest")),
            (material["report"].get("n9_evidence")),
        )
        if value
    ]
    return material


#: Host 留痕里逐条变更的投影字段（SPEC-REV-01 R2：人必须能看出"改了什么"）。
HOST_TRACE_FIELDS: tuple[str, ...] = (
    "id", "kind", "old", "new", "line_before", "line_after",
    "encoding", "rationale", "evidence",
)


def n3_digest_view(run_dir: Path | None) -> dict[str, Any]:
    """N3 摘要入口（只给 `path` + `exists`；**不返回正文**）。

    规格依据：WEB_UI_SPEC §4.4/§5「材料区能打开 `n3_digest.md` 入口（存在性探测，缺失显示未生成）」。
    """
    path = Path(run_dir) / "n3_digest.md" if run_dir is not None else None
    return {
        "path": str(path) if path is not None else None,
        "exists": bool(path is not None and path.is_file()),
    }


def host_trace_view(run_dir: Path | None) -> dict[str, Any]:
    """Host 留痕（`staged/mock_change_applied.json`）的摘要投影。

    只投影逐条变更的九项事实（`id/kind/old/new/line_before/line_after/encoding/rationale/
    evidence`），不返回整份文件；文件不存在时 `exists=false`（**不编造**留痕）。
    """
    path = Path(run_dir) / "staged" / "mock_change_applied.json" if run_dir is not None else None
    out: dict[str, Any] = {
        "path": str(path) if path is not None else None,
        "exists": False,
        "count": 0,
        "changes": [],
        "applied_at": None,
        "baseline_from": None,
        "error": None,
    }
    if path is None:
        return out
    doc, error = _read_artifact(path)
    if not isinstance(doc, dict):
        out["error"] = error
        return out
    changes: list[dict[str, Any]] = []
    for item in doc.get("changes") or []:
        if not isinstance(item, dict):
            continue
        changes.append({key: item.get(key) for key in HOST_TRACE_FIELDS})
    out.update({
        "exists": True,
        "count": len(changes),
        "changes": changes,
        "applied_at": doc.get("applied_at"),
        "baseline_from": doc.get("baseline_from"),
        "error": None,
    })
    return out


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


#: 变更种类 → 面板展示名（原值仍保留在条目字段里）。
CHANGE_LABELS: dict[str, str] = {"modified": "修改", "added": "新增", "deleted": "删除"}

def _lines_text(lines: Any) -> str | None:
    """行号列表 →「第 171–172 行」；空列表 ⇒ None（不编行号）。"""
    values: list[int] = []
    for item in lines or []:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            values.append(int(item))
        elif isinstance(item, str) and item.strip().isdigit():
            values.append(int(item.strip()))
    if not values:
        return None
    if len(values) == 1:
        return f"第 {values[0]} 行"
    return f"第 {min(values)}–{max(values)} 行"


def _entry_title(item: dict[str, Any], has_hunk: bool) -> str:
    """一条差异条目的一句话说明（确定性投影，不读文件正文、不猜）。

    P-17 允许"拿不到一句话说明"：这里只用差异条目已有字段，拿不到就明说拿不到。
    """
    kind = str(item.get("kind") or "")
    change = CHANGE_LABELS.get(str(item.get("change")), item.get("change"))
    line_text = _lines_text(item.get("lines"))
    offset = item.get("offset")
    if has_hunk:
        parts = [part for part in (line_text, f"偏移 {offset}" if offset else None) if part]
        head = "内容有改动" + (f"（{change}）" if change else "")
        return head + ("：" + "，".join(parts) if parts else "：有行级差异（行号/偏移未抽取）")
    if kind == "doc_entry" and (item.get("before") is not None or item.get("after") is not None):
        return f"字段改动：{item.get('before')} → {item.get('after')}"
    if kind == "allfile":
        return "只比到整文件指纹：内容变了（没抓到文本 hunk，原因见原始记录）"
    return "内容有改动，但没抓到文本 hunk（原因见原始记录）"


def _group_diff_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 `entry_id` 归并多路证据（P-11 同一口径）：主条目 + 附证据，不重复计数。

    **口径唯一**（AGENTS 红线 8）：归并本身复用 `node_story.group_diff_entries`（面板 N2
    结果与 G1 清单是同一判据）；本函数只把分组的展示字段补成闸门清单的形状：
    `title` / `attached[].redundant_of` / 未决原因 / `offsets` / `encoding` 等。
    """
    out: list[dict[str, Any]] = []
    for group in node_story.group_diff_entries(entries):
        key = group["entry_id"]
        main = group["main"]
        has_hunk = bool(group["has_hunk"])
        attached: list[dict[str, Any]] = []
        for item in group["attached"]:
            md5_only = str(item.get("kind")) == "allfile" and not str(item.get("diff_hunk") or "").strip()
            attached.append({
                "kind": item.get("kind"),
                "change": item.get("change"),
                "before": item.get("before"),
                "after": item.get("after"),
                "evidence": item.get("evidence"),
                "unresolved": item.get("unresolved"),
                "redundant_of": key if md5_only else None,
                "note": ("整文件指纹，不计入修订点（同一文件已有行级证据）" if md5_only
                         else "同一文件的另一路证据"),
            })
        kinds: list[Any] = []
        for item in [main, *group["attached"]]:
            if item.get("kind") and item.get("kind") not in kinds:
                kinds.append(item.get("kind"))
        offsets = main.get("offsets") if isinstance(main.get("offsets"), list) else []
        out.append({
            "entry_id": key,
            "title": _entry_title(main, has_hunk),
            "kinds": kinds,
            "change": main.get("change"),
            "unresolved": bool(group["unresolved"]),
            "unresolved_reason": group.get("unresolved_reason"),
            "lines": list(main.get("lines") or []),
            "offset": main.get("offset") or (offsets[0] if offsets else None),
            "offsets": list(offsets),
            "encoding": main.get("encoding"),
            "has_hunk": has_hunk,
            "diff_hunk": main.get("diff_hunk"),
            "before": main.get("before"),
            "after": main.get("after"),
            "evidence": main.get("evidence"),
            "segment": main.get("segment"),
            "attached": attached,
            # 已决策态由 decisions/<gate>.json 回填；等待态为 None（草稿在界面侧）。
            "disposition": None,
        })
    return out


def _decision_ledger(run_dir: Path | None, gate: str) -> dict[str, Any] | None:
    """读 Host 闸门逐条处置落账（`decisions/<gate>.json`，只增不改）。

    缺失/损坏一律返回 None（**不编**逐条处置）；调用方据此显示"未留存"。
    """
    if run_dir is None:
        return None
    doc, _ = _read_artifact(Path(run_dir) / "decisions" / f"{gate}.json")
    return doc if isinstance(doc, dict) else None


def _gate_pending_items(
    *,
    gate: str,
    waiting: bool,
    payload: dict[str, Any] | None,
    blockers: list[dict[str, Any]] | None,
    conflicts: dict[str, Any],
    n12_open_items: list[Any] | None,
    selected_cases: list[Any] | None,
) -> list[dict[str, Any]]:
    """G2/G3 的只读待确认项（裁决 #2）：阻断项 / 报告未闭环项 / 未清冲突 / 回归选集用例。

    只读：**不带 disposition**，界面不得据此提交逐条处置（那套语义仍然只属于 G1/I1）。
    缺材料就少列、不编；G1 返回空列表（G1 用 `entries` 做逐条处置）。
    """
    if gate == "G1_diff_confirm":
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        key = str(item.get("id") or "")
        if not key or key in seen:
            return
        seen.add(key)
        out.append(item)

    # ① 阻断项：等待态取材料 hard_block + defects；已决策态取运行视图 blockers（只取 blocker/defect）。
    source_blockers: list[dict[str, Any]] = []
    if waiting and isinstance(payload, dict):
        for bucket in ("hard_block", "defects"):
            source_blockers.extend(
                b for b in (payload.get(bucket) or []) if isinstance(b, dict))
    elif blockers:
        source_blockers.extend(
            b for b in blockers
            if isinstance(b, dict) and b.get("severity") in ("blocker", "defect"))
    for bump in source_blockers:
        code = str(bump.get("code") or "")
        add({
            "id": f"blocker:{code or len(out)}",
            "kind": "blocker",
            "title": str(bump.get("title") or code or "（服务端未下发一句话）"),
            "detail": bump.get("message"),
            "severity": bump.get("severity"),
        })

    if gate == "G2_report_accept":
        # ② 报告未闭环项（N12 detail.open_items；旧 run 没有 ⇒ 不列，不猜）。
        for index, text in enumerate(n12_open_items or []):
            add({
                "id": f"open_item:{index}",
                "kind": "open_item",
                "title": str(text),
                "detail": None,
                "severity": "warning",
            })
    if gate == "G3_regression_decision":
        # ③ 未清冲突（I4）：只给摘要，逐条冲突清单仍在闸门材料/冲突快照里。
        open_count = conflicts.get("open")
        total = conflicts.get("total")
        if isinstance(open_count, int) and (open_count or 0) > 0:
            add({
                "id": "conflict_summary",
                "kind": "conflict",
                "title": f"冲突未清零：{open_count}/{total if total is not None else '未下发'} 条（发版前需逐条裁决）",
                "detail": "冲突清单原文在闸门材料/冲突快照里；本清单只读。",
                "severity": "blocker",
            })
        # ④ 回归选集用例（N15_select 在 G3 之后才跑；已决策且有选集时才列）。
        for index, case in enumerate(selected_cases or []):
            add({
                "id": f"case:{case}",
                "kind": "case",
                "title": str(case),
                "detail": "本轮回归集用例（只读；选集结果见 N15_select）",
                "severity": "info",
            })
    return out


def gate_entries_view(
    *,
    gate: str,
    run_dir: Path | None = None,
    diff: dict[str, Any] | None = None,
    pending_interrupt: dict[str, Any] | None = None,
    gate_options: dict[str, list[dict[str, Any]]] | None = None,
    authority: dict[str, Any] | None = None,
    node_events: list[dict[str, Any]] | None = None,
    mode: str | None = None,
    run_status: str | None = None,
    case_states: dict[str, Any] | None = None,
    conflicts: dict[str, Any] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    n12_open_items: list[Any] | None = None,
    selected_cases: list[Any] | None = None,
) -> dict[str, Any]:
    """闸门节点面板的二级差异清单（P-17/P-18/P-29；只读投影）。

    三态：

    - `waiting`：来源 = 运行视图 `pending_interrupt.payload`（材料已含逐条字段）；
    - `decided`：来源 = `n2_diff.json` 投影 + `decisions/<gate>.json`（逐条处置）；
      没有落账 ⇒ `note` 明说"逐条处置未留存"，**不从 gates.json 猜**（交接提示词 §0.5 ⑥）；
    - `no_material`：拿不到差异清单 ⇒ 明说缺什么，不编条目。

    裁决 #2（2026-10-23）：G2/G3 的"待确认项"只做**只读清单**（`items`），
    不新增逐条处置语义（勾选/提交仍只有 G1/I1）；清单来源全部是服务端既有材料：
    G2 = 阻断项 + 报告未闭环项；G3 = 阻断项 + 未清冲突 + 回归选集用例（有才列）。
    """
    payload: dict[str, Any] | None = None
    if isinstance(pending_interrupt, dict):
        candidate = pending_interrupt.get("payload")
        if isinstance(candidate, dict) and candidate.get("gate") == gate:
            payload = candidate
    # 等待态只在运行确实在等待时成立：`pending_interrupt` 可能是 run 文档里的旧载荷
    # （drill 夹具还自带历史 gates.json），不能凭它把"已经过去的闸门"显示成"正在等你处理"。
    waiting_run = run_status is None or str(run_status).startswith("waiting")
    waiting = payload is not None and waiting_run

    source_diff = diff or {}
    if waiting:
        waiting_diff = payload.get("difference_items")
        if isinstance(waiting_diff, dict):
            source_diff = waiting_diff
    raw_entries = source_diff.get("entries") if isinstance(source_diff, dict) else None
    # 只有 G1/I1 有「逐条差异清单 + 逐条处置」；G2/G3 的待确认项走只读 `items`（裁决 #2），
    # 不能把 G1 的差异条目挂到 G2/G3 面板上（那是另一套材料）。
    gate_has_entries = gate == "G1_diff_confirm"
    entries = _group_diff_entries(list(raw_entries or [])) if gate_has_entries else []

    ledger = _decision_ledger(run_dir, gate)
    latest: dict[str, Any] | None = None
    if isinstance(ledger, dict):
        records = ledger.get("records") or []
        if records and isinstance(records[-1], dict):
            latest = records[-1]
    dispositions = (latest or {}).get("entries") if isinstance(latest, dict) else None
    if isinstance(dispositions, dict):
        for entry in entries:
            raw = dispositions.get(entry["entry_id"])
            if isinstance(raw, dict):
                entry["disposition"] = {
                    "decision": raw.get("decision"),
                    "reason": raw.get("reason"),
                }
            elif isinstance(raw, str):
                entry["disposition"] = {"decision": raw, "reason": None}

    # 事件流里本节点的 gate_decided 是最贴近本节点的记录（reason/signed_at 原文）。
    decided_event: dict[str, Any] | None = None
    for event in node_events or []:
        if isinstance(event, dict) and event.get("kind") == "gate_decided":
            decided_event = event.get("detail") or {}

    authority = authority if isinstance(authority, dict) else {}
    signed = authority.get("status") == "signed" or bool(authority.get("decision"))
    decision: dict[str, Any] | None = None
    if decided_event or signed:
        detail = decided_event or {}
        decision = {
            "decision": detail.get("decision") or authority.get("decision"),
            "actor": detail.get("actor") or authority.get("actor"),
            "actor_kind": authority.get("actor_kind"),
            "human_signed": authority.get("human_signed"),
            "signed_at": detail.get("signed_at") or authority.get("signed_at"),
            "reason": detail.get("reason") if detail.get("reason") is not None
                      else authority.get("note"),
            "history_len": authority.get("history_len"),
        }

    if waiting:
        # 本 gate 正在等人处置：即便权威里有历史签署记录（drill 夹具会带），也以"等待"为准。
        decision = None
    state = "waiting" if waiting else ("decided" if decision is not None else "no_material")
    # R3-04：已决策态的"当时的硬阻断"只信 `decisions/<gate>.json` 最新 record 里的快照
    # （Host 签署时落账）。旧 run 没有该键 ⇒ 明说"未留存"，不拿现在的 blockers 冒充当时。
    hard_block_recorded: bool | None = (
        ("hard_block" in latest) if (state == "decided" and isinstance(latest, dict)) else None
    )
    note: str | None = None
    if gate == "G1_diff_confirm":
        if state == "decided" and latest is None:
            note = "逐条处置未留存（本轮早于处置落账；界面只显示整门决策，不从 gates.json 猜）"
        elif state == "no_material":
            note = (source_diff.get("error") or "差异清单未下发") + "（界面不编条目）"
    else:
        # 裁决 #2：G2/G3 没有「逐条差异清单」是正常形态（它们的待确认项走 `items`），
        # 不能因为 entries 为空就报"差异清单未下发"，更不能编逐条处置。
        if state == "no_material":
            note = "闸门材料未下发（服务端未给出待确认项；界面不编条目）"

    if state == "decided" and hard_block_recorded is False:
        legacy_note = "当时的阻断项未留存（该 run 早于落账）"
        note = f"{note}；{legacy_note}" if note else legacy_note

    options = (gate_options or {}).get(gate) or []
    entries_required: bool | None = None
    if waiting:
        entries_required = bool(payload.get("entry_decisions_required"))
    elif state == "decided":
        entries_required = bool(source_diff.get("unresolved_count")) and mode != "drill"

    cycle = payload.get("cycle") if waiting else None
    if cycle is None and isinstance(latest, dict):
        cycle = latest.get("cycle")
    unresolved_points = sum(1 for entry in entries if entry["unresolved"])
    disposed = sum(1 for entry in entries if entry.get("disposition"))
    if not gate_has_entries:
        unresolved = 0
    else:
        unresolved = int(source_diff.get("unresolved_count") or 0)
    # P-29：等待态首屏的关键数字（硬阻断/待验用例/未清冲突）也来自服务端材料，界面不自己数。
    cases_view = (payload.get("case_states") if waiting else case_states) or {}
    conflicts_view = (payload.get("conflicts") if waiting else conflicts) or {}
    pending_cases = cases_view.get("pending_own") if isinstance(cases_view, dict) else None
    hard_block_list = ([b for b in (payload.get("hard_block") or []) if isinstance(b, dict)]
                       if waiting else [])
    if state == "decided" and hard_block_recorded:
        # R3-04：只投影契约三字段（code/title/message），其余不外泄；顺序保持落账顺序。
        hard_block_list = [
            {"code": b.get("code"), "title": b.get("title"), "message": b.get("message")}
            for b in (latest.get("hard_block") or [])
            if isinstance(b, dict)
        ]
    items = _gate_pending_items(
        gate=gate,
        waiting=waiting,
        payload=payload,
        blockers=blockers,
        conflicts=conflicts_view if isinstance(conflicts_view, dict) else {},
        n12_open_items=n12_open_items,
        selected_cases=selected_cases,
    )
    if items and state == "no_material":
        # 有只读待确认项 ⇒ 不能再报"材料未下发"（那会自相矛盾）；
        # 也没有"等待/已决策"归属时给独立状态 `read_only`（界面只读渲染 items，不提供处置）。
        state = "read_only"
        note = None
    return {
        "gate": gate,
        "state": state,
        "cycle": cycle,
        "entries_required": entries_required,
        "decision_options": list(options),
        "counts": {
            "entries": len(entries),
            # P-18：md5-only 附证据不计入修订点 ⇒ 修订点 = 唯一 entry_id 数。
            "revision_points": len(entries),
            "disposed": disposed,
            "unresolved": unresolved,
            # 需要人工处置的"条"= 有未决证据的唯一 entry_id 数（与 entry_decisions 的键同一口径）。
            "unresolved_points": unresolved_points,
            # P-29：硬阻断条数 / 待验用例数 / 未清冲突（未下发就 None，不写 0）。
            # R3-04：已决策态只在落账里有 `hard_block` 时给条数（旧 run = 未下发，不是 0）。
            "hard_block": (len(hard_block_list) if (waiting or hard_block_recorded) else None),
            "pending_cases": (len(pending_cases) if isinstance(pending_cases, list) else None),
            "conflicts_open": (conflicts_view.get("open")
                               if isinstance(conflicts_view, dict) else None),
            "conflicts_total": (conflicts_view.get("total")
                                if isinstance(conflicts_view, dict) else None),
        },
        "entries": entries,
        # 裁决 #2：G2/G3 只读"待确认项"清单（无 disposition、不可勾选）；G1 不用本字段。
        "items": items,
        "decision": decision,
        "hard_block": hard_block_list,
        "source": ("pending_interrupt" if waiting
                   else "decisions_ledger" if latest is not None
                   else "n2_diff" if entries else "none"),
        "note": note,
    }


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
    mode = run_doc.get("mode")
    created = run_created_at(run_dir) or run_doc.get("created_at")
    diff = diff_entries_view(run_dir, mode=mode)
    cases = case_states_view(run_dir, created_at=created)
    rework = rework_counts(run_dir)
    extras = {"diff": diff, "case_states": cases, "rework": rework}
    blockers = compute_blockers(
        run_dir=run_dir, counts=counts, kb=kb, slot_status=slot_status, job=job, stage=stage,
        mode=mode, extras=extras,
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
        # agent 工作状态是**投影**（事件派生），不是权威；字段见 Web UI Spec §4.3。
        "project": run_doc.get("project"),
        # R5：环境来源徽标（空 = 未经 S0 派生；drill 不覆盖 S0）
        "s0_record_id": run_doc.get("s0_record_id"),
        "agents": build_agents(
            events,
            run_dir=run_dir,
            pending_interrupt=run_doc.get("pending_interrupt"),
            job=job,
        ),
        "stage_map": STAGES,
        "agents_authority": "projection",
        "gate_options": _gate_options(),
        "rework": rework,
        # I1/I2 的**放行前置**也必须在看板上可见（材料与判定同一口径）。
        "difference_items": diff,
        "case_states": cases,
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
