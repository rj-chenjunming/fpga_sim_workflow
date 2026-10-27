"""S0-b 的 Host 侧编排：派生 → 提议 → 人确认 → 落盘；三库冒烟执行与判据。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §8.2-1（ports）、§8.2-2（smoke）、§8.4 红线 6/7，
2026-10-27 修订（Q1 = Host 确定性派生、Q2 = 模型提议 + 人确认、Q3 = 基线相对增量）。

三段各归各的 owner（AGENTS §1：每个状态恰好一个 owner）：

| 段 | owner | 允许写什么 |
|---|---|---|
| 派生 | Host（`sv_ports.py`，只读） | 不写任何文件 |
| 提议 | 模型（`model:*`）或 Host | 只写 `s0b/proposals.json`，**不碰副本 TB** |
| 确认 | 人（`human:*`） | 只写 `s0b/confirmations.jsonl`（只增不改，带锚） |
| 落盘 | Host（本模块） | 只写副本 `TB/<tb_top>`，且**只按已确认 hunk 的精确原文替换** |
| 冒烟 | Host | 只在副本 `kb/runs/<run>/…` 与沙箱里写 |

不变式（不读源码也能判，见 `tests/test_s0b.py`）：

1. 未确认的 hunk ⇒ 副本 `TB/<tb_top>` **逐字节不变**；
2. 确认记录**只增不改**（同一 hunk 再确认 = 追加，旧记录保留），每条带 sha256 锚；
3. `old_text` 在文件里必须**恰好出现一次**，否则拒绝落盘（不猜位置）；
4. 冒烟读数只取 `uvs_logs`（唯一解析实现），`error(s)>0` ⇒ failed；warning 用基线相对增量；
5. 任一环节不成立 ⇒ 该 check 不得 `passed`（fail-closed），**不许降级成"无差异/无告警"**。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from host import sv_ports, uvs_logs

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPILE_DRIVER = REPO_ROOT / "kb" / "tools" / "run_guarded.sh"

#: 编译驱动里 `uvlan -work tb <路径>/<name>.sv` 的取值 = 真实 TB 顶层文件（单一来源）。
#: 实测驱动写的是 `./$TB_FILE/tbtop.sv`（`TB_FILE=TB`），所以取该 token 的 basename。
_DRIVER_TB_TOP = re.compile(r"uvlan\s+-work\s+tb\s+(\S+)")
#: 兜底候选：历史契约写法（演练夹具用它）。
FALLBACK_TB_TOP = "TB/top.sv"

#: 基线"运行入口"候选（按优先级；契约原写 `run` 文件，真实环境是 run_tc.py / run_uvs_new.sh /
#: doc/tools/run_local.sh —— 与 TB 顶层同属"契约写的名字环境里没有"的一类，交由本函数确定性解析）。
RUN_ENTRY_CANDIDATES = ("run", "run_tc.py", "run_uvs_new.sh", "doc/tools/run_local.sh")

PROPOSE_ACTORS = ("model:", "host:")
CONFIRM_ACTORS = ("human:",)
DECISIONS = ("confirmed", "rejected")

S0B_DIR = "s0b"
PROPOSALS = "proposals.json"
CONFIRMATIONS = "confirmations.jsonl"


# ---------------------------------------------------------------- 基础工具

def _parse_now(value) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise ValueError("now 必须为含时区的 ISO 时间")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("now 必须为含时区的 ISO 时间") from exc
    if stamp.tzinfo is None:
        raise ValueError("now 必须为含时区的 ISO 时间")
    return stamp


def _iso(stamp: datetime) -> str:
    return stamp.isoformat()


def _sha256_json(value) -> str:
    blob = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def unified_diff(old: str, new: str) -> str:
    """把 hunk 的"原片段 → 新片段"渲染成真实 unified diff（报告用；确定性）。"""
    import difflib
    old_text = old if old.endswith("\n") else old + "\n"
    new_text = new if new.endswith("\n") else new + "\n"
    return "".join(difflib.unified_diff(old_text.splitlines(keepends=True),
                                        new_text.splitlines(keepends=True),
                                        fromfile="baseline", tofile="confirmed", n=2))


def line_span(text: str, block: str) -> str:
    """`block` 在 `text` 里的行号范围（1 基，含首尾）；找不到返回空串。"""
    index = text.find(block)
    if index < 0:
        return ""
    start = text.count("\n", 0, index) + 1
    return "L%d-L%d" % (start, start + block.count("\n"))


def _md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _s0b(folder: Path) -> Path:
    target = Path(folder) / S0B_DIR
    if target.is_symlink():
        raise ValueError("s0b 目录不允许符号链接")
    target.mkdir(exist_ok=True)
    return target


def driver_tb_top() -> str | None:
    """从编译驱动里取 TB 顶层文件（驱动写 `./$TB_FILE/tbtop.sv` ⇒ `TB/tbtop.sv`）。

    取不到返回 None（调用方退回历史写法 `TB/top.sv`；两者都没有就显式失败）。
    """
    if not COMPILE_DRIVER.is_file():
        return None
    text = COMPILE_DRIVER.read_text(encoding="utf-8", errors="replace")
    for match in _DRIVER_TB_TOP.finditer(text):
        token = match.group(1)
        if token.endswith(".sv"):
            return "TB/" + Path(token).name
    return None


def resolve_run_entry(baseline: Path) -> str:
    """确定基线的运行入口文件（只复制、不执行）：按 `RUN_ENTRY_CANDIDATES` 优先级取第一个存在的。

    都不存在 ⇒ ValueError（显式失败，不猜）。
    """
    baseline = Path(baseline)
    for rel in RUN_ENTRY_CANDIDATES:
        if (baseline / rel).is_file():
            return rel
    raise ValueError("基线需含运行入口文件（%s 之一）" % "、".join(RUN_ENTRY_CANDIDATES))


def resolve_tb_top(baseline: Path) -> str:
    """确定基线里的 TB 顶层文件：**先按编译驱动**，再退回历史写法 `TB/top.sv`。

    两者都不存在 ⇒ ValueError（显式失败；不猜文件名）。返回相对路径（如 `TB/tbtop.sv`）。
    """
    baseline = Path(baseline)
    candidates = []
    from_driver = driver_tb_top()
    if from_driver:
        candidates.append(from_driver)
    if FALLBACK_TB_TOP not in candidates:
        candidates.append(FALLBACK_TB_TOP)
    for rel in candidates:
        if (baseline / rel).is_file():
            return rel
    raise ValueError(
        "基线需含 TB 顶层文件：编译驱动取到 %r，兜底 %r，但基线里都没有"
        % (from_driver, FALLBACK_TB_TOP))


# ---------------------------------------------------------------- 提议（模型 / Host）

def load_proposals(folder: Path) -> list[dict]:
    path = Path(folder) / S0B_DIR / PROPOSALS
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("hunks") or [])


def propose(folder: Path, hunks: list[dict], actor: str, now=None) -> dict:
    """记录模型（或 Host）的逐 hunk 提议。**只写 proposals.json，不碰副本 TB。**"""
    if not isinstance(actor, str) or not actor.startswith(PROPOSE_ACTORS):
        raise ValueError("提议者必须是 model:<name> 或 host:<name>（人只做确认，见 confirm）")
    stamp = _iso(_parse_now(now))
    folder = Path(folder)
    existing = load_proposals(folder)
    seen = {h["hunk_id"] for h in existing}
    added = []
    for raw in hunks:
        if not isinstance(raw, dict):
            raise ValueError("hunk 必须是对象")
        hunk = {
            "hunk_id": str(raw.get("hunk_id") or ""),
            "file": str(raw.get("file") or ""),
            "old_text": str(raw.get("old_text") or ""),
            "new_text": str(raw.get("new_text") or ""),
            "reason": str(raw.get("reason") or ""),
            "addresses": [str(a) for a in (raw.get("addresses") or [])],
            "scope": str(raw.get("scope") or ""),
            "proposed_by": actor,
            "proposed_at": stamp,
        }
        if not hunk["hunk_id"] or hunk["hunk_id"] in seen:
            raise ValueError("hunk_id 缺失或重复：%r" % hunk["hunk_id"])
        if not hunk["file"].startswith("TB/") or ".." in hunk["file"]:
            raise ValueError("hunk 的 file 必须是 TB/ 下的相对路径：%r" % hunk["file"])
        if not hunk["old_text"] or hunk["old_text"] == hunk["new_text"]:
            raise ValueError("hunk %s 的 old_text 必须非空且与 new_text 不同" % hunk["hunk_id"])
        if not hunk["reason"]:
            raise ValueError("hunk %s 缺少 reason" % hunk["hunk_id"])
        seen.add(hunk["hunk_id"])
        added.append(hunk)
    if not added:
        raise ValueError("至少要有 1 条 hunk（空列表不写文件）")
    target = _s0b(folder) / PROPOSALS
    payload = {"version": 1, "hunks": existing + added}
    # 追加语义：新 hunk 只增不改（重复 hunk_id 上面已拒绝）；先写临时文件再原子替换。
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    tmp.replace(target)
    return {"added": len(added), "total": len(payload["hunks"])}


# ---------------------------------------------------------------- 确认（人）

def load_confirmations(folder: Path) -> list[dict]:
    path = Path(folder) / S0B_DIR / CONFIRMATIONS
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        body = {k: v for k, v in row.items() if k != "sha256"}
        if row.get("sha256") != _sha256_json(body):
            raise ValueError("确认记录锚不符（文件被改动？）：%s" % row.get("hunk_id"))
        rows.append(row)
    return rows


def decisions_of(folder: Path) -> dict:
    """hunk_id → 最终决定（**最后一条**生效；历史记录保留）。"""
    latest = {}
    for row in load_confirmations(folder):
        latest[row["hunk_id"]] = row["decision"]
    return latest


def confirm(folder: Path, hunk_id: str, decision: str, actor: str, reason: str = "", now=None) -> dict:
    """人逐条确认/否决；**只追加**（同一 hunk 再确认 = 追加，旧记录保留）。"""
    if not isinstance(actor, str) or not actor.startswith(CONFIRM_ACTORS):
        raise ValueError("确认者必须是 human:<name>（模型/ Host 不得自封 confirmed）")
    if decision not in DECISIONS:
        raise ValueError("decision 必须是 %s" % (DECISIONS,))
    folder = Path(folder)
    known = {h["hunk_id"] for h in load_proposals(folder)}
    if hunk_id not in known:
        raise ValueError("未提议的 hunk 不能确认：%r" % hunk_id)
    _s0b(folder)
    row = {"hunk_id": hunk_id, "decision": decision, "actor": actor,
           "reason": reason, "at": _iso(_parse_now(now))}
    row["sha256"] = _sha256_json(row)
    with (Path(folder) / S0B_DIR / CONFIRMATIONS).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


# ---------------------------------------------------------------- warning 评估（人）

WARNING_DECISIONS = "warning_decisions.jsonl"


def load_warning_decisions(folder: Path) -> list[dict]:
    path = Path(folder) / S0B_DIR / WARNING_DECISIONS
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        body = {k: v for k, v in row.items() if k != "sha256"}
        if row.get("sha256") != _sha256_json(body):
            raise ValueError("warning 评估记录锚不符：%s" % row.get("code"))
        rows.append(row)
    return rows


def accepted_warnings(folder: Path) -> set[str]:
    return {row["code"] for row in load_warning_decisions(folder) if row.get("decision") == "accepted"}


def accept_warning(folder: Path, code: str, actor: str, reason: str = "", now=None) -> dict:
    """人对"新增/上升的 warning code"给出评估结论（accepted / must_fix）；只追加、带锚。"""
    if not isinstance(actor, str) or not actor.startswith(CONFIRM_ACTORS):
        raise ValueError("warning 评估者必须是 human:<name>")
    if not re.fullmatch(r"Warning-\d+", str(code or "")):
        raise ValueError("code 必须形如 Warning-<数字>：%r" % code)
    if not reason:
        raise ValueError("warning 评估必须给 reason（为什么可接受/必须修）")
    folder = Path(folder)
    _s0b(folder)
    row = {"code": code, "decision": "accepted", "actor": actor, "reason": reason,
           "at": _iso(_parse_now(now))}
    row["sha256"] = _sha256_json(row)
    with (folder / S0B_DIR / WARNING_DECISIONS).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return row


# ---------------------------------------------------------------- 落盘（Host，仅已确认）

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="surrogateescape")


def _write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".s0b-tmp")
    tmp.write_text(text, encoding="utf-8", errors="surrogateescape")
    tmp.replace(path)


def apply_confirmed(record: dict, folder: Path) -> dict:
    """把**已确认**的 hunk 按精确原文替换落进副本 TB 顶层。

    - 未确认/被否决 ⇒ 不动文件；
    - `old_text` 必须恰好出现一次，否则拒绝（不猜位置）；
    - 返回落盘前后 md5，供 `ports` 判据与报告使用。
    """
    folder = Path(folder)
    tb_top = record.get("tb_top")
    if not tb_top:
        raise ValueError("记录里没有 tb_top（先经 prepare 解析）")
    work = Path(record["work_env"])
    target = work / tb_top
    if not target.is_file():
        raise FileNotFoundError("副本里缺 TB 顶层文件：%s" % target)
    proposals = load_proposals(folder)
    decisions = decisions_of(folder)
    before = _md5(target)
    text = _read_text(target)
    # 幂等：内容已经等于"基线 + 已确认 hunk" ⇒ 视为已落盘，不报错（复核 FAIL-9）
    expected = _expected_tb_text(dict(record, _folder=str(folder)))
    if expected and text == expected:
        return {"applied": [], "already_applied": True, "skipped": [], "tb_top": tb_top,
                "md5_before": before, "md5_after": before}
    applied, skipped = [], []
    for hunk in sorted(proposals, key=lambda h: h["hunk_id"]):
        if hunk["file"] != tb_top:
            raise ValueError("hunk %s 的 file 与记录 tb_top 不一致" % hunk["hunk_id"])
        decision = decisions.get(hunk["hunk_id"])
        if decision != "confirmed":
            skipped.append({"hunk_id": hunk["hunk_id"], "decision": decision})
            continue
        occurrences = text.count(hunk["old_text"])
        if occurrences != 1:
            raise ValueError("hunk %s 的 old_text 在文件里出现 %d 次（要求恰好 1 次）"
                             % (hunk["hunk_id"], occurrences))
        text = text.replace(hunk["old_text"], hunk["new_text"], 1)
        applied.append(hunk["hunk_id"])
    if applied:
        _write_text(target, text)
    return {"applied": applied, "skipped": skipped, "already_applied": False,
            "tb_top": tb_top, "md5_before": before, "md5_after": _md5(target)}


# ---------------------------------------------------------------- ports 判据

def _expected_tb_text(record: dict) -> str:
    """按"基线的 TB 顶层 + 已确认 hunk 顺序替换"算出**应有**的内容（不写文件）。"""
    baseline_tb = Path(record["baseline"]) / record["tb_top"]
    text = _read_text(baseline_tb)
    decisions = decisions_of(Path(record["_folder"]))
    for hunk in sorted(load_proposals(Path(record["_folder"])), key=lambda h: h["hunk_id"]):
        if decisions.get(hunk["hunk_id"]) != "confirmed":
            continue
        if text.count(hunk["old_text"]) != 1:
            return ""                       # 期望内容算不出来 ⇒ 由调用方判 failed
        text = text.replace(hunk["old_text"], hunk["new_text"], 1)
    return text


def evaluate_ports(record: dict, folder: Path) -> dict:
    """`ports` check：派生 + 提议覆盖 + 确认终态 + TB 实际内容与期望一致。"""
    folder = Path(folder)
    record = dict(record, _folder=str(folder))
    tb_top = record["tb_top"]
    baseline = Path(record["baseline"])
    work = Path(record["work_env"])
    defines = sv_ports.load_defines(baseline / "all_define.txt")
    diff = sv_ports.derive_port_diff(baseline / "RTL", work / "RTL", defines=defines)

    table = []
    for row in diff["changed"]:
        table.append({"kind": "module", "module": row["module"],
                      "added": row["added"], "removed": row["removed"],
                      "changed": [c["name"] for c in row["changed"]]})
    for name in diff["added_modules"]:
        table.append({"kind": "module_added", "module": name})
    for name in diff["removed_modules"]:
        table.append({"kind": "module_removed", "module": name})

    proposals = load_proposals(folder)
    decisions = decisions_of(folder)
    addressed = set()
    for hunk in proposals:
        for key in hunk["addresses"]:
            addressed.add(key.split(":")[0])
    uncovered = sorted({row["module"] for row in table} - addressed)
    unconfirmed = sorted(h["hunk_id"] for h in proposals if h["hunk_id"] not in decisions)

    expected = _expected_tb_text(record)
    actual = _read_text(work / tb_top)
    baseline_text = _read_text(baseline / tb_top)
    tb_matches = bool(expected) and actual == expected
    # 已确认但**尚未落盘**：文件仍等于基线，而期望内容已被 hunk 改动 ⇒ 这是"待落盘"，
    # 与"未登记改动"（文件既不是基线也不是期望）必须区分，否则会误判 failed（复核 FAIL-7）。
    pending_apply = bool(expected) and expected != baseline_text and actual == baseline_text

    evidence = {
        "tb_top": tb_top,
        "baseline_rtl_md5": diff["baseline"]["md5"],
        "candidate_rtl_md5": diff["candidate"]["md5"],
        "baseline_modules": diff["baseline"]["parsed_modules"],
        "candidate_modules": diff["candidate"]["parsed_modules"],
        "baseline_unparsed": diff["baseline"]["unparsed"],
        "candidate_unparsed": diff["candidate"]["unparsed"],
        "derive_md5": diff["md5"],
        "defines": sorted(defines),
        "tb_md5_baseline": _md5(baseline / tb_top),
        "tb_md5_work": _md5(work / tb_top),
        "hunks": len(proposals),
        "confirmed": sorted(h for h, d in decisions.items() if d == "confirmed"),
        "rejected": sorted(h for h, d in decisions.items() if d == "rejected"),
    }

    if not diff["ok"]:
        status = "failed"
        reason = "端口派生不成立（输入缺失或有解析不了的模块），不得当作无差异"
    elif table and uncovered:
        status = "waiting"
        reason = "有端口差异未被任何 hunk 覆盖：%s" % ", ".join(uncovered[:8])
    elif unconfirmed:
        status = "waiting"
        reason = "有提议尚未确认：%s" % ", ".join(unconfirmed[:8])
    elif pending_apply:
        status = "waiting"
        reason = "已确认的 hunk 尚未落盘（副本 TB 仍等于基线）"
    elif not tb_matches:
        status = "failed"
        reason = "副本 TB 顶层内容与『基线 + 已确认 hunk』不一致（有未登记改动）"
    else:
        status = "passed"
        reason = "派生成立、差异均已处置、副本 TB 与已确认内容一致"
    return {"status": status, "reason": reason, "evidence": evidence, "table": table,
            "derive": {"changed": diff["changed"], "added_modules": diff["added_modules"],
                       "removed_modules": diff["removed_modules"]}}


# ---------------------------------------------------------------- smoke（副本内三库编译）

def _uvlan_available() -> bool:
    return shutil.which("uvlan") is not None


def run_smoke(record: dict, folder: Path, case: str, run_id: str, now=None) -> dict:
    """在**副本内**跑 `run_guarded.sh --mode compile-only`，再按基线相对增量判 warning。

    - 驱动复用既有实现（红线 8：不新增第二套编译）；
    - 基线编译在**独立沙箱**里做（`--sandbox-root` 指向基线树），保证基线零写入；
    - 读数一律经 `uvs_logs`（红线 7：不许裸 grep）。
    """
    folder = Path(folder)
    record = dict(record, _folder=str(folder))
    work = Path(record["work_env"])
    baseline = Path(record["baseline"])
    if not _uvlan_available():
        return {"status": "waiting", "reason": "PATH 里没有 uvlan（EDA 未装/未 source），未执行冒烟"}
    if not COMPILE_DRIVER.is_file():
        return {"status": "waiting", "reason": "缺少 %s，未执行冒烟" % COMPILE_DRIVER}
    for part in ("RTL", "TB", "PKG", "TESTLIB"):
        if not (work / part).is_dir():
            return {"status": "waiting", "reason": "副本缺 %s，未执行冒烟" % part}
    stamp = _iso(_parse_now(now))
    results = {}
    # 沙箱与证据必须放在**被见证的树之外**：`manifest()` 拒绝符号链接，而 run_guarded 的沙箱
    # 工作树全是软链 ⇒ 放进 work/baseline 里会让"漂移核验"把冒烟自己当成污染（实测踩过）。
    smoke_root = _s0b(folder) / "smoke"
    for label, root in (("candidate", work), ("baseline", baseline)):
        evidence = smoke_root / label / "evidence"
        sandbox = smoke_root / label / "sandbox"
        command = ["bash", str(COMPILE_DRIVER), "--mode", "compile-only", "-c", case,
                   "--sandbox-root", str(sandbox), "--run", "%s-s0smoke-%s" % (run_id, label),
                   "--evidence-dir", str(evidence)]
        # 驱动用 LOOP_ENV_ROOT 定位环境根（不是 cwd）⇒ 必须显式指向"要冒烟的那棵树"
        child_env = dict(os.environ, LOOP_ENV_ROOT=str(root))
        try:
            proc = subprocess.run(command, cwd=str(root), capture_output=True, text=True,
                                  timeout=1800, env=child_env)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"status": "failed", "reason": "冒烟命令无法执行（%s）：%s" % (label, exc),
                    "at": stamp}
        logs = sorted(evidence.glob("*_c_*.log")) or sorted(evidence.glob("archive/*_c_*.log"))
        if not logs:
            return {"status": "failed", "reason": "%s 段没有产出编译日志：%s" % (label, evidence),
                    "rc": proc.returncode, "at": stamp}
        reports = [uvs_logs.parse_log(path) for path in logs]
        results[label] = {"rc": proc.returncode, "command": command,
                          "evidence_dir": str(evidence),
                          "logs": [str(p) for p in logs],
                          "summary": uvs_logs.summarize(reports),
                          "tail": (proc.stdout or "")[-2000:]}
    delta = uvs_logs.warning_delta(results["baseline"]["summary"]["warning_codes"],
                                   results["candidate"]["summary"]["warning_codes"])
    candidate = results["candidate"]
    baseline_summary = results["baseline"]["summary"]
    accepted = accepted_warnings(folder)
    unaccepted = [code for code in delta["needs_evaluation"] if code not in accepted]
    payload = {"status": "passed", "reason": "", "at": stamp, "case": case,
               "candidate": candidate, "baseline": results["baseline"],
               "warning_delta": delta, "accepted_warnings": sorted(accepted),
               "unaccepted_warnings": unaccepted}
    # 判据顺序：读数可信（两侧）→ 两侧 rc → 两侧 error → warning 评估（复核 FAIL-3）
    if not candidate["summary"]["ok"]:
        payload.update(status="failed", reason="候选编译日志缺汇总行（读数不可信）")
    elif not baseline_summary["ok"]:
        payload.update(status="failed",
                       reason="基线编译日志缺汇总行（增量判据不可信，不得当作零告警）")
    elif candidate["rc"] != 0 or results["baseline"]["rc"] != 0:
        payload.update(status="failed",
                       reason="编译驱动 rc 非 0（candidate=%s / baseline=%s）"
                              % (candidate["rc"], results["baseline"]["rc"]))
    elif candidate["summary"]["errors"] > 0 or baseline_summary["errors"] > 0:
        payload.update(status="failed",
                       reason="编译 error(s)：candidate=%s / baseline=%s"
                              % (candidate["summary"]["errors"], baseline_summary["errors"]))
    elif unaccepted:
        payload.update(status="waiting",
                       reason="新增/上升的告警需人评估：%s" % ", ".join(unaccepted[:8]))
    return payload


def reevaluate_smoke(smoke: dict, folder: Path) -> dict:
    """人补齐 warning 评估后，**不必重跑编译**也能把 waiting 重算成 passed（复核 N6）。

    只改判据、不动读数：`needs_evaluation` 全部有 `accepted` 记录 ⇒ 判 passed，否则维持 waiting。
    """
    if (smoke or {}).get("status") != "waiting":
        return smoke
    needs = ((smoke.get("warning_delta") or {}).get("needs_evaluation") or [])
    if not needs:
        return smoke
    accepted = accepted_warnings(folder)
    unaccepted = [code for code in needs if code not in accepted]
    updated = dict(smoke, accepted_warnings=sorted(accepted), unaccepted_warnings=unaccepted)
    if not unaccepted:
        updated.update(status="passed", reason="新增/上升的告警已由人逐条评估")
    return updated


def ready_for_execution(record: dict, folder: Path) -> bool:
    """六项 check 全 passed **且**没有漂移/错误 ⇒ 才允许 `real`。

    fail-closed：任何一项不是 `passed`（含 `waiting`）都返回 False。
    """
    checks = {c["key"]: c["status"] for c in record.get("checks") or []}
    return (record.get("status") == "prepared" and not record.get("error")
            and all(checks.get(key) == "passed" for key in
                    ("copy", "rtl", "non_rtl", "ports", "smoke", "baseline")))
