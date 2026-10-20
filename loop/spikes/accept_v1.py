"""v1 验收：对**真实运行中的服务**做带断言的全链路走查（闸门操作台 + 长任务看板）。

与 `api_walkthrough.py` 的区别（后者只 print，不能当验收）：
- 每条都是**断言**，任一失败 rc!=0；
- 分阶段，中间由人**真的重启服务进程**，用来证明"跨进程重启后重新附着到在跑作业"；
- 枚举与白名单**从权威导入**（`host.gate_authority` / `host.progress.ALLOWED_KINDS`），
  不手抄 —— 手抄枚举正是本项目已实证过的缺陷来源。

用法（服务需已在 `--base` 上运行）：
    cd loop
    LOOP_LLM_MODE=standin LOOP_PORT=8099 ./run.sh &        # 终端 A
    .venv/bin/python spikes/accept_v1.py --phase 1         # 建 run + 拒绝矩阵 + 签 G1 + 等 N9 停放
    # ---- 此处 kill 服务并重起（证明恢复）----
    .venv/bin/python spikes/accept_v1.py --phase 2         # 断言重附着 + G2 + G3
    .venv/bin/python spikes/accept_v1.py --phase 3         # 终态 + 闸门恰好一次 + N16 零副作用
    .venv/bin/python spikes/accept_v1.py --phase 4         # 取消作业（界面第二个写动作）
    .venv/bin/python spikes/accept_v1.py --phase 5         # 死任务必须判死且释放单槽
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from host import gate_authority as GA  # noqa: E402
from host.progress import ALLOWED_KINDS  # noqa: E402
from host import paths as P  # noqa: E402

STATE = Path(__file__).resolve().parent / ".accept_v1_state.json"

PASS = 0
FAIL = 0
FAILED_NAMES: list[str] = []


def ck(name: str, cond: bool, detail: Any = "") -> bool:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [ok  ] {name}")
    else:
        FAIL += 1
        FAILED_NAMES.append(name)
        print(f"  [FAIL] {name}  <<< {detail!r}")
    return bool(cond)


def show(label: str, value: Any) -> None:
    print(f"  [val ] {label} = {value}")


def digest_tree(root: Path) -> str:
    """目录内容摘要：排序 relpath + 内容 md5（不看 mtime —— 项目口径）。"""
    h = hashlib.sha256()
    if not root.exists():
        return "<absent>"
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        h.update(str(p.relative_to(root)).encode())
        h.update(b"\0")
        h.update(hashlib.md5(p.read_bytes()).hexdigest().encode())
        h.update(b"\n")
    return h.hexdigest()



def wait_clean_snapshot(path: Path, interrupt_id: str | None, *, seconds: float = 20.0) -> bool:
    """等快照落盘，且其中该中断是**可恢复**的（`resume_count < max_resumes`）。

    半截快照（已派发完）会被 `_is_clean_park` 拒绝落盘，所以这里等到的必然是干净停车。
    """
    if not interrupt_id:
        return False
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.2)
            continue
        found = None

        def walk(o):
            nonlocal found
            if isinstance(o, dict):
                for k, val in o.items():
                    if k == "interrupts" and isinstance(val, dict) and interrupt_id in val:
                        found = val[interrupt_id]
                    walk(val)
            elif isinstance(o, list):
                for x in o:
                    walk(x)

        walk(doc)
        if found is not None:
            mx, cnt = found.get("max_resumes"), found.get("resume_count") or 0
            if mx is None or cnt < mx:
                return True
        time.sleep(0.2)
    return False


def save_state(**kv: Any) -> None:
    cur = json.loads(STATE.read_text()) if STATE.is_file() else {}
    cur.update(kv)
    STATE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")


def load_state() -> dict[str, Any]:
    if not STATE.is_file():
        raise SystemExit("[FAIL] 找不到 .accept_v1_state.json —— 请先跑 --phase 1")
    return json.loads(STATE.read_text())


def wait_for(c: httpx.Client, run_id: str, pred, *, seconds: float = 90.0, what: str = "") -> dict:
    deadline = time.time() + seconds
    last: dict = {}
    while time.time() < deadline:
        last = c.get(f"/api/runs/{run_id}").json()
        if pred(last):
            return last
        if last.get("status") == "failed" and "failed" not in what:
            return last
        time.sleep(0.5)
    print(f"  [warn] 等待超时（{seconds}s）：{what}")
    return last


def interrupt_gate(view: dict) -> str | None:
    pi = view.get("pending_interrupt") or {}
    return (pi.get("payload") or {}).get("gate")


# --------------------------------------------------------------------- phase 1

def phase1(c: httpx.Client) -> None:
    print("== phase 1：投影 / 拒绝矩阵 / G1 签署 / N9 停放 ==")

    h = c.get("/api/health").json()
    show("health", {k: h.get(k) for k in ("ok", "agently", "python")})
    ck("A1 health.ok", h.get("ok") is True)
    ck("A2 agently 版本是钉住的 4.1.4.8", h.get("agently") == "4.1.4.8", h.get("agently"))
    ck("A3 llm 状态不含密钥字段值", "sk-" not in json.dumps(h.get("llm") or {}))
    ck("A4 启动即做恢复（有 restore_report）", isinstance(h.get("restore_report"), dict))
    show("llm", h.get("llm"))

    html = c.get("/").text
    # UI v1：页面拆成 index.html + 同源 app.js（零外链）。枚举消费方在 app.js，
    # 因此 A7 必须同时看两个同源静态件，而不是只扫 index.html 的内联脚本。
    app_js = c.get("/app.js").text if c.get("/app.js").status_code == 200 else ""
    ck("A5 前端可达", len(html) > 10000, len(html))
    ck("A6 前端零外链", "http://" not in html and "https://" not in html)
    ck("A7 前端渲染服务端下发的闸门枚举（不自造）",
       "gate_options" in html or "gateOptions" in html
       or "gate_options" in app_js or "gateOptions" in app_js,
       {"html": len(html), "app_js": len(app_js)})

    # 基准摘要：N16 全程不得有副作用 ⇒ 先取一次
    base_digest = digest_tree(P.KB_BASELINES)
    save_state(baselines_digest_before=base_digest)
    show("kb/baselines 内容摘要(前)", base_digest)

    r = c.post("/api/runs", json={"baseline": "v0", "mode": "drill", "scenario": "happy"})
    ck("A8 建 run 返回 200", r.status_code == 200, r.text[:200])
    run_id = r.json()["run_id"]
    save_state(run_id=run_id)
    show("run_id", run_id)

    v = c.get(f"/api/runs/{run_id}").json()
    pi = v.get("pending_interrupt") or {}
    show("status", v.get("status"))
    show("gate1 interrupt", {"id": pi.get("id"), "gate": interrupt_gate(v)})
    show("blockers", [(b["code"], b["severity"]) for b in v["blockers"]])
    show("gate_options", {g: [o["value"] for o in oo] for g, oo in v["gate_options"].items()})
    show("conflicts", v["conflicts"])
    show("rework", v["rework"])
    show("can", v["can"])

    ck("A9 首个中断是 G1_diff_confirm", interrupt_gate(v) == "G1_diff_confirm", pi.get("id"))
    ck("A10 状态是 waiting_gate（不是 running）", v.get("status") == "waiting_gate", v.get("status"))
    ck("A11 闸门历史此时为空", v["gate_history"] == [], v["gate_history"])

    authority = {g: [d for d in GA.actionable_decisions(g)] for g in GA.gate_ids()}
    served = {g: [o["value"] for o in oo] for g, oo in v["gate_options"].items()}
    ck("A12 服务端下发的枚举 == kb_lib 权威", served == authority, {"served": served, "authority": authority})
    ck("A13 pending 不作为可提交动作", all("pending" not in vals for vals in served.values()), served)

    codes = [b["code"] for b in v["blockers"]]
    # G1 阶段证据尚未产出（evidence 由 N9 之后才有）⇒ 此处是「证据缺失」。
    # 口径一的 1687 要到 G2 才可见（见 phase 2 的 B8/B11）。
    ck("A14 G1 阶段 I3 以「证据缺失」形态阻断", "I3_EVIDENCE_MISSING" in codes, codes)
    ck("A15 I4 冲突未清零被投影为 blocker", "I4_CONFLICTS_UNCLEARED" in codes, codes)
    ck("A16 I7 未达上限时不误报", "I7_REWORK_LIMIT" not in codes, codes)
    ck("A17 conflicts 总数与 expected_total 一致",
       v["conflicts"]["total"] == v["conflicts"]["expected_total"] == 72, v["conflicts"])
    ck("A18 judge_pass 此时为 false（blocker 存在）", v["can"]["judge_pass"] is False, v["can"])

    # ---- 闸门**权威**态（F-V1-02）：事件流里的 actor 是自报，回答不了"谁签的" ----
    au = v.get("gates_authority") or {}
    show("gates_authority(G1 未签)",
         {"present": au.get("present"), "anchor_ok": au.get("anchor_ok"),
          "anchor_detail": au.get("anchor_detail"), "human_signed_all": au.get("human_signed_all"),
          "divergences": au.get("divergences")})
    ck("A40 视图带权威闸门态（不是只有事件流）", au.get("present") is True, au.get("reason"))
    ck("A41 权威锚可复算且一致（gates.sha256）", au.get("anchor_ok") is True, au.get("anchor_detail"))
    ck("A42 权威态覆盖全部三道闸门",
       set((au.get("gates") or {}).keys()) == set(GA.gate_ids()), list((au.get("gates") or {}).keys()))
    ck("A43 未签的 G1 在权威里 human_signed=false",
       (au.get("gates") or {}).get("G1_diff_confirm", {}).get("human_signed") is False,
       (au.get("gates") or {}).get("G1_diff_confirm"))
    ck("A44 事件流投影确实缺 human_signed（这正是必须有权威态的原因）",
       all("human_signed" not in e for e in v["gate_history"]), v["gate_history"])

    # ---- 拒绝矩阵：四次都必须被拒，且**不消耗中断** ----
    print("-- 拒绝矩阵（I6 / 枚举 / I4 / 缺 actor），关键是都不能消耗中断 --")
    r1 = c.post(f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
                json={"decision": "confirmed", "actor": "model:gpt-x", "reason": "越权"})
    show("非人类 actor", {"status": r1.status_code, "err": (r1.json().get("detail") or {}).get("error", "")[:80]})
    ck("A19 非人类 actor 被拒 403（I6）", r1.status_code == 403, r1.status_code)

    r2 = c.post(f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
                json={"decision": "full_regression", "actor": "human:chenjunming", "reason": "自造枚举"})
    show("自造枚举", {"status": r2.status_code, "err": (r2.json().get("detail") or {}).get("error", "")[:80]})
    ck("A20 自造枚举被拒 400", r2.status_code == 400, r2.status_code)

    r3 = c.post(f"/api/runs/{run_id}/gates/G3_regression_decision/decision",
                json={"decision": "full_now", "actor": "human:chenjunming", "reason": "试越 I4"})
    show("I4 越权", {"status": r3.status_code, "err": (r3.json().get("detail") or {}).get("error", "")[:80]})
    ck("A21 冲突未清零时 full_now 被拒 403（I4）", r3.status_code == 403, r3.status_code)

    r4 = c.post(f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
                json={"decision": "confirmed"})       # 刻意不给 actor
    show("缺 actor", {"status": r4.status_code, "err": (r4.json().get("detail") or {}).get("error", "")[:80]})
    ck("A22 缺 actor 被拒 400", r4.status_code == 400, r4.status_code)

    v = c.get(f"/api/runs/{run_id}").json()
    ck("A23 四次拒绝后仍 waiting_gate", v.get("status") == "waiting_gate", v.get("status"))
    ck("A24 四次拒绝后中断仍是同一个（未被消耗）",
       (v.get("pending_interrupt") or {}).get("id") == pi.get("id"), (v.get("pending_interrupt") or {}).get("id"))
    ck("A25 四次拒绝后闸门历史仍为空（没有半签）", v["gate_history"] == [], v["gate_history"])
    ck("A45 四次拒绝后权威账本仍是一张白纸（human_signed_all=false）",
       (v.get("gates_authority") or {}).get("human_signed_all") is False,
       (v.get("gates_authority") or {}).get("human_signed_all"))

    # ---- 人类签署 G1 ----
    r = c.post(f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
               json={"decision": "confirmed", "actor": "human:chenjunming", "reason": "2 条差异已逐条核对"})
    show("human 签 G1", {"status": r.status_code, "body": r.json()})
    ck("A26 人类签 G1 成功", r.status_code == 200 and r.json().get("ok") is True, r.text[:200])
    gs = (r.json().get("gate_state") or {})
    ck("A27 响应里的 gate_state 是**权威闸门态**（human_signed=true，不再是子进程记录）",
       gs.get("human_signed") is True, gs)
    ck("A28 actor 记录了人名", str(gs.get("actor", "")).startswith("human:"), gs.get("actor"))
    ck("A28b 子进程调用记录另立 gate_tool（字段名与内容相符）",
       (r.json().get("gate_tool") or {}).get("rc") == 0, (r.json().get("gate_tool") or {}).keys())

    # 签署后权威账本必须立刻反映，且锚仍一致
    v = c.get(f"/api/runs/{run_id}").json()
    au2 = v.get("gates_authority") or {}
    g1a = (au2.get("gates") or {}).get("G1_diff_confirm", {})
    show("gates_authority(G1 已签)", g1a)
    ck("A46 权威里 G1 human_signed=true / actor_kind=human",
       g1a.get("human_signed") is True and g1a.get("actor_kind") == "human", g1a)
    ck("A47 权威 history 长度=1（append-only 起点）", g1a.get("history_len") == 1, g1a.get("history_len"))
    ck("A48 签署后锚仍一致", au2.get("anchor_ok") is True, au2.get("anchor_detail"))
    ck("A49 事件流与权威无分歧", (au2.get("divergences") or []) == [], au2.get("divergences"))

    # ---- 等 N9 进长任务 ----
    v = wait_for(c, run_id, lambda x: x.get("job") is not None, seconds=120, what="N9 作业出现")
    job = v.get("job") or {}
    show("job", {k: job.get(k) for k in ("job_id", "node", "phase", "rc", "tc", "seed", "log_path")})
    ck("A29 N9 已提交外部作业（看板有 job）", bool(job.get("job_id")), job)
    ck("A31 作业 ETA 外显（长任务不得静默）", bool(job.get("eta_human")), job.get("eta_human"))
    ck("A32 作业有日志路径（验收要能追到证据）", bool(job.get("log_path")), job.get("log_path"))
    save_state(job_id=job.get("job_id"), gate1_interrupt=pi.get("id"))

    ev_now = c.get(f"/api/runs/{run_id}/events", params={"since_seq": 0}).json()["events"]
    kinds = [e["kind"] for e in ev_now]
    ck("A33 事件流记了 job_submitted", "job_submitted" in kinds, kinds)

    # 停机前必须确认"当前停放已落盘、且是一张**可恢复的干净快照**"。
    # 否则第 2 代恢复的是上一张快照，测到的就不是"重附着到在跑作业"而是"回退到上一个停车点"
    # —— 那是另一个场景（F-V1-06b 有单测覆盖），不该在这里碰运气。
    parked_id = (v.get("pending_interrupt") or {}).get("id")
    snap_path = P.LOOP_DIR / "state" / "recovery" / f"{run_id}.json"
    ok = wait_clean_snapshot(snap_path, parked_id, seconds=10.0)
    current_id = parked_id
    if not ok:
        # happy 的 drill 作业瞬间完成并立即投递：`wait_for(job)` 返回时 JOB 中断可能已被
        # 消费，执行已推进到下一道闸门（G2）。此时「停机前干净停放」应对**当前**中断校验，
        # 而不是对已经消失的 JOB 中断（否则是观察窗口竞态，不是恢复能力缺陷）。
        cur = c.get(f"/api/runs/{run_id}").json()
        current_id = (cur.get("pending_interrupt") or {}).get("id")
        if current_id and current_id != parked_id:
            ok = wait_clean_snapshot(snap_path, current_id, seconds=15.0)
    ck("A51 当前停放已落盘且是可恢复的干净快照", ok,
       {"path": str(snap_path), "first_interrupt": parked_id, "current_interrupt": current_id})
    # 停放（执行在作业期间是 interrupt，而不是 running）由 phase 4 的 cancel 场景确定性断言：
    # 那个作业 `sleep 120`，一定能观察到；happy 的 drill 作业瞬间完成，观察窗口太窄。

    # ---- 证据存在性探测（E-2 的界面侧一半） ----
    # 冻结见证 `RUN-20261015-120626` 的 `evidence/archive/` 是**故意的空目录**
    # （归档腿修复后不回填历史轮）⇒ 界面必须按「证据缺失」显式呈现，而不是静默 404。
    ex = c.get(f"/api/runs/{run_id}/evidence/exists",
               params={"ref": "kb/runs/RUN-20261015-120626/evidence/archive"}).json()
    show("E-2 archive 探测（冻结见证，故意为空）", ex)
    ck("A50 空归档目录被判为「证据缺失」而非静默通过",
       ex.get("exists") is False and ex.get("is_dir") is True and ex.get("entries") == 0, ex)
    ex_missing = c.get(f"/api/runs/{run_id}/evidence/exists",
                       params={"ref": "kb/runs/__不存在__/evidence"}).json()
    ck("A35 缺失证据被显式标为缺失（不是 404）", ex_missing.get("exists") is False, ex_missing)
    ck("A36 缺失证据带解释（E-2）", bool(ex_missing.get("note")), ex_missing)

    # ---- 事件流白名单 ----
    ev = c.get(f"/api/runs/{run_id}/events", params={"since_seq": 0}).json()["events"]
    kinds = sorted({e["kind"] for e in ev})
    show("事件", {"n": len(ev), "kinds": kinds})
    ck("A37 事件 kind 全在白名单内", set(kinds) <= set(ALLOWED_KINDS), sorted(set(kinds) - set(ALLOWED_KINDS)))
    ck("A38 事件 refs 不含解析器内部路径",
       all("parser" not in json.dumps(e.get("refs", [])).lower() for e in ev))
    ck("A39 事件流有单调 seq", [e["seq"] for e in ev] == sorted(e["seq"] for e in ev), [e["seq"] for e in ev][:8])


# --------------------------------------------------------------------- phase 2

def phase2(c: httpx.Client) -> None:
    print("== phase 2：重启后重新附着 + G2 + G3 ==")
    st = load_state()
    run_id, job_id = st["run_id"], st["job_id"]

    h = c.get("/api/health").json()
    rr = h.get("restore_report") or {}
    show("restore_report", {"restored": rr.get("restored"), "failed": rr.get("failed"), "jobs": rr.get("jobs")})
    ck("B1 重启后从快照恢复了本 run", run_id in (rr.get("restored") or []), rr)
    ck("B2 恢复无失败项", not rr.get("failed"), rr.get("failed"))

    v = c.get(f"/api/runs/{run_id}").json()
    job = v.get("job") or {}
    show("重附着后的 job", {k: job.get(k) for k in ("job_id", "phase", "rc", "elapsed_s")})
    ck("B3 重新附着到**同一个**作业", job.get("job_id") == job_id, {"now": job.get("job_id"), "before": job_id})
    # 该 drill 作业在重启前就已跑完 ⇒ 正确行为是"锁已释放"。
    # 这里断言的是**自洽**：还在跑就必须占锁，已终态就必须不占。
    _running = (job.get("phase") in ("running", "cancelling"))
    ck("B4 单槽状态与作业相位自洽（运行中⇒占锁 / 终态⇒不占）",
       (v.get("slot") or {}).get("locked") is _running,
       {"phase": job.get("phase"), "slot": v.get("slot")})
    ck("B5 gate_history 仍恰好一次 G1（重启不重复记账）",
       len([g for g in v["gate_history"] if g.get("gate") == "G1_diff_confirm"]) == 1, v["gate_history"])

    # ---- 等 G2 ----
    v = wait_for(c, run_id, lambda x: interrupt_gate(x) == "G2_report_accept", seconds=180, what="G2 出现")
    show("G2 状态", v.get("status"))
    ck("B6 到达 G2_report_accept", interrupt_gate(v) == "G2_report_accept", interrupt_gate(v))

    counts = v.get("counts") or {}
    ev = v.get("evidence") or {}
    show("counts", counts)
    show("verdict", ev.get("verdict"))
    show("imprints", {k: {kk: vv.get(kk) for kk in ("verified_count", "failed_count", "consistent")}
                      for k, vv in (ev.get("imprints") or {}).items()})
    show("job(终)", {k: (v.get("job") or {}).get(k) for k in ("phase", "rc", "elapsed_s")})
    show("slot(终)", v.get("slot"))

    k1, k2 = counts.get("koutou1") or {}, counts.get("koutou2") or {}
    ck("B7 两套口径并列呈现（一个不能替代另一个）", bool(k1) and bool(k2), counts)
    ck("B8 口径一 = 1687（夹具实测值）", k1.get("value") == 1687, k1)
    # 口径二的值是**字典**（UVM Report Summary 四行），不是一个数字；判零看 `zero`。
    ck("B9 口径二 UVM_ERROR=0 且判零",
       isinstance(k2.get("value"), dict) and k2["value"].get("UVM_ERROR") == 0 and k2.get("zero") is True, k2)
    ck("B10 两口径分歧 ⇒ both_zero 必须为 false", counts.get("both_zero") is False, counts.get("both_zero"))
    ck("B11 分歧时不得判绿（verdict.passed=False）",
       (ev.get("verdict") or {}).get("passed") is False, ev.get("verdict"))
    ck("B12 verdict 明说「不得把跑通当结论」", bool((ev.get("verdict") or {}).get("must_not")), ev.get("verdict"))
    ck("B13 印记三向一致", all(i.get("consistent") for i in (ev.get("imprints") or {}).values()),
       ev.get("imprints"))
    ck("B14 作业终态 rc==0（该用例本身跑得完）", (v.get("job") or {}).get("rc") == 0, v.get("job"))
    ck("B15 作业结束后单槽已释放",
       (v.get("slot") or {}).get("locked") is False, v.get("slot"))

    # ---- G2 拒绝 ----
    r_bad = c.post(f"/api/runs/{run_id}/gates/G2_report_accept/decision",
                   json={"decision": "accept_all", "actor": "human:chenjunming"})
    ck("B16 G2 自造枚举被拒 400", r_bad.status_code == 400, r_bad.status_code)
    r_model = c.post(f"/api/runs/{run_id}/gates/G2_report_accept/decision",
                     json={"decision": "accept", "actor": "model:gpt-x"})
    ck("B17 G2 非人类 actor 被拒 403", r_model.status_code == 403, r_model.status_code)
    v = c.get(f"/api/runs/{run_id}").json()
    ck("B18 拒绝后仍停在 G2（中断未被消耗）", interrupt_gate(v) == "G2_report_accept", interrupt_gate(v))

    r = c.post(f"/api/runs/{run_id}/gates/G2_report_accept/decision",
               json={"decision": "accept", "actor": "human:chenjunming", "reason": "评估报告已复核"})
    show("human 签 G2", {"status": r.status_code, "decision": r.json().get("decision")})
    ck("B19 人类签 G2 成功", r.status_code == 200, r.text[:200])

    v = wait_for(c, run_id, lambda x: interrupt_gate(x) == "G3_regression_decision", seconds=120, what="G3 出现")
    ck("B20 到达 G3_regression_decision", interrupt_gate(v) == "G3_regression_decision", interrupt_gate(v))
    gh = {(g.get("gate")): 0 for g in v["gate_history"]}
    for g in v["gate_history"]:
        gh[g.get("gate")] = gh.get(g.get("gate"), 0) + 1
    show("gate_history 计数", gh)
    ck("B21 G1/G2 各恰好一次", gh.get("G1_diff_confirm") == 1 and gh.get("G2_report_accept") == 1, gh)
    show("G3 material", {"blockers": [(b["code"], b["severity"]) for b in v["blockers"]], "can": v["can"]})
    ck("B22 G3 材料里冲突未清零仍是 blocker", "I4_CONFLICTS_UNCLEARED" in [b["code"] for b in v["blockers"]], v["blockers"])

    # ---- G3 拒绝 + 签署 ----
    r_i4 = c.post(f"/api/runs/{run_id}/gates/G3_regression_decision/decision",
                  json={"decision": "full_now", "actor": "human:chenjunming"})
    ck("B23 冲突未清零时 full_now 被拒 403（I4 在提交前判）", r_i4.status_code == 403, r_i4.status_code)
    r_sub = c.post(f"/api/runs/{run_id}/gates/G3_regression_decision/decision",
                   json={"decision": "subset_only", "actor": "human:chenjunming"})
    ck("B24 subset_only 同样被 I4 拒 403", r_sub.status_code == 403, r_sub.status_code)
    r_model3 = c.post(f"/api/runs/{run_id}/gates/G3_regression_decision/decision",
                      json={"decision": "defer", "actor": "model:gpt-x"})
    ck("B25 G3 非人类 actor 被拒 403", r_model3.status_code == 403, r_model3.status_code)
    v = c.get(f"/api/runs/{run_id}").json()
    ck("B26 三次拒绝后仍停在 G3", interrupt_gate(v) == "G3_regression_decision", interrupt_gate(v))

    r = c.post(f"/api/runs/{run_id}/gates/G3_regression_decision/decision",
               json={"decision": "defer", "actor": "human:chenjunming", "reason": "冲突未清零，本轮不发版"})
    ck("B27 人类选 defer 成功（I4 允许的选项）", r.status_code == 200, r.text[:200])


# --------------------------------------------------------------------- phase 3

def phase3(c: httpx.Client) -> None:
    print("== phase 3：终态 / 闸门恰好一次 / N16 零副作用 ==")
    st = load_state()
    run_id = st["run_id"]

    v = wait_for(c, run_id, lambda x: x.get("status") in ("finished", "failed"), seconds=120, what="终态")
    show("终态", {"status": v.get("status"), "error": v.get("error"), "current_node": v.get("current_node")})
    ck("C1 跑到终态", v.get("status") in ("finished", "failed"), v.get("status"))
    ck("C2 终态是 finished（不是 failed）", v.get("status") == "finished", v.get("status"))
    ck("C3 无执行错误", not v.get("error"), v.get("error"))

    gh: dict[str, int] = {}
    for g in v["gate_history"]:
        gh[g.get("gate")] = gh.get(g.get("gate"), 0) + 1
    show("gate_history", gh)
    ck("C4 三道闸门各恰好一次（事件流）", gh == {"G1_diff_confirm": 1, "G2_report_accept": 1,
                                                  "G3_regression_decision": 1}, gh)
    # 事件流里的 actor 是自报字符串且**不带** human_signed ⇒ 必须看权威账本
    au = v.get("gates_authority") or {}
    show("gates_authority(终态)", {g: {k: (au.get("gates") or {}).get(g, {}).get(k)
                                       for k in ("decision", "status", "human_signed", "actor_kind", "history_len")}
                                   for g in GA.gate_ids()})
    ck("C5 权威账本：三道闸门均为人类签署", au.get("human_signed_all") is True, au.get("human_signed_all"))
    ck("C5b 权威账本 all_signed=true", au.get("all_signed") is True, au.get("all_signed"))
    ck("C5c 终态锚仍一致（全程未被外部改动）", au.get("anchor_ok") is True, au.get("anchor_detail"))
    ck("C5d 事件流与权威账本无分歧", (au.get("divergences") or []) == [], au.get("divergences"))

    nodes = [n.get("node") for n in v["node_history"]]
    show("node_history", nodes)
    ck("C6 节点历史覆盖 N0 起点", "N0" in nodes, nodes)
    # 本轮 G3 选 `defer`（冲突未清零时 I4 允许的"不发版"选项）⇒ 正确终点是 HALT。
    # 关键是**必须收敛**：F-V1-04 之前这里永远卡在 running。
    ck("C7 节点历史到达终止节点（HALT 或 N16）", ("HALT" in nodes) or ("N16" in nodes), nodes)
    ck("C7b defer ⇒ 终点是 HALT 且未走 N16（不发版）", "HALT" in nodes and "N16" not in nodes, nodes)
    ck("C8 节点历史无 failed", all(n.get("status") != "failed" for n in v["node_history"]),
       [n for n in v["node_history"] if n.get("status") == "failed"])
    ck("C8b HALT 是显式中止而非假装收敛（事件 status=halted）",
       any(n.get("node") == "HALT" and n.get("status") == "halted" for n in v["node_history"]),
       [n for n in v["node_history"] if n.get("node") == "HALT"])

    after = digest_tree(P.KB_BASELINES)
    before = st.get("baselines_digest_before")
    show("kb/baselines 内容摘要(前/后)", {"before": before, "after": after})
    ck("C9 N16 dry-run 对 kb/baselines 零副作用（内容 md5 逐行不变）", before == after, {"before": before, "after": after})
    ck("C10 promote 能力被 I4/I3 正确判否", v["can"]["promote"] is False, v["can"])

    ev = c.get(f"/api/runs/{run_id}/events", params={"since_seq": 0}).json()["events"]
    ck("C11 全流程事件 kind 仍在白名单", {e["kind"] for e in ev} <= set(ALLOWED_KINDS),
       sorted({e["kind"] for e in ev} - set(ALLOWED_KINDS)))
    seqs = [e["seq"] for e in ev]
    ck("C12 事件 seq 严格递增且连续", seqs == list(range(1, len(seqs) + 1)), seqs[:10])

    runs = c.get("/api/runs").json()["runs"]
    ck("C13 run 列表含本 run", run_id in [r["run_id"] for r in runs], [r["run_id"] for r in runs])
    show("run 列表", runs)


# ------------------------------------------------------------ phase 4 / 5

def _drive_to_job(c: httpx.Client, scenario: str) -> str:
    r = c.post("/api/runs", json={"baseline": "v0", "mode": "drill", "scenario": scenario})
    ck(f"建 run(scenario={scenario})", r.status_code == 200, r.text[:200])
    run_id = r.json()["run_id"]
    r = c.post(f"/api/runs/{run_id}/gates/G1_diff_confirm/decision",
               json={"decision": "confirmed", "actor": "human:chenjunming", "reason": "验收"})
    ck(f"签 G1(scenario={scenario})", r.status_code == 200, r.text[:120])
    v = wait_for(c, run_id, lambda x: x.get("job") is not None, seconds=120, what=f"{scenario} 作业出现")
    ck(f"作业已提交(scenario={scenario})", bool((v.get("job") or {}).get("job_id")), v.get("job"))
    return run_id


def _wait_parked(c: httpx.Client, run_id: str, job_id: str, *, seconds: float = 60.0) -> dict:
    """等「执行已停放 + 单槽被该作业持有 + 中断带 job_id」三件同时成立。

    这三条是长任务可跨重启恢复的前提：快照里若有 `running` 帧，`load` 就 fail-closed。
    happy 场景的 drill 作业瞬间完成、观察窗口太窄，所以用一个真正跑得久的场景来断言。
    """
    deadline = time.time() + seconds
    last: dict = {}
    while time.time() < deadline:
        last = c.get(f"/api/runs/{run_id}").json()
        pending_payload = (last.get("pending_interrupt") or {}).get("payload") or {}
        # I18：后端已把「等闸门 / 等作业 / 等单槽」区分成 waiting_gate / waiting_job /
        # waiting_slot。长任务停放必须是 waiting_job（旧断言只看 waiting_gate，是 I18 修复前口径）。
        if (last.get("status") in ("waiting_job", "waiting_gate")
                and (last.get("slot") or {}).get("locked") is True
                and pending_payload.get("job_id") == job_id):
            return last
        time.sleep(0.2)
    return last


def phase4(c: httpx.Client) -> None:
    """长任务停放（`sleep 120` 的场景，观察窗口足够宽）。**此处不取消** —— 留给 phase 4b
    在**真杀进程重起之后**断言"仍停在同一个作业上、单槽没丢"。"""
    print("== phase 4：长任务停放（作业仍在跑） ==")
    st0 = load_state()
    h = c.get("/api/health").json()
    rr = h.get("restore_report") or {}
    show("本次启动的恢复报告", {"restored": rr.get("restored"), "failed": rr.get("failed")})
    ck("D-1 已 finished 的 run 不会被重启反复恢复（僵尸 run 不再堆积）",
       st0["run_id"] not in (rr.get("restored") or []),
       {"restored": rr.get("restored"), "finished_run": st0["run_id"]})

    run_id = _drive_to_job(c, "cancel")
    v = c.get(f"/api/runs/{run_id}").json()
    job_id = (v.get("job") or {}).get("job_id")
    parked = _wait_parked(c, run_id, job_id)
    show("停放态", {"status": parked.get("status"), "slot": parked.get("slot"),
                    "pending_payload": (parked.get("pending_interrupt") or {}).get("payload")})
    ck("D0 作业运行期执行处于**停放**（waiting_job，不是 running 到不可快照）",
       parked.get("status") == "waiting_job", parked.get("status"))
    ck("D0b 单槽被该作业持有（uvs.setup 是全局单文件 ⇒ 单槽）",
       (parked.get("slot") or {}).get("locked") is True, parked.get("slot"))
    ck("D0c 停放的中断带 job_id（可被看护/补投递认领）",
       ((parked.get("pending_interrupt") or {}).get("payload") or {}).get("job_id") == job_id,
       (parked.get("pending_interrupt") or {}).get("payload"))
    ck("D0d 停放时执行快照已落盘（重启恢复的前提）",
       (P.LOOP_DIR / "state" / "recovery" / f"{run_id}.json").is_file(),
       str(P.LOOP_DIR / "state" / "recovery" / f"{run_id}.json"))
    save_state(cancel_run_id=run_id, cancel_job_id=job_id)


def phase4b(c: httpx.Client) -> None:
    """重启之后：仍停在**同一个**运行中的作业上，且单槽**没有丢**；然后走界面的取消动作。"""
    print("== phase 4b：重启后长任务仍在跑 + 取消（界面第二个写动作） ==")
    st = load_state()
    run_id, job_id = st["cancel_run_id"], st["cancel_job_id"]

    h = c.get("/api/health").json()
    rr = h.get("restore_report") or {}
    show("restore_report", {"restored": rr.get("restored"), "failed": rr.get("failed"), "jobs": rr.get("jobs")})
    ck("D1 重启后本长任务 run 被恢复", run_id in (rr.get("restored") or []), rr.get("restored"))
    # 「跨重启重附着」的**权威**证明：重启那一刻确有作业在跑（否则无从谈起）。
    ck("D1b 重启时确有作业在跑（re-attach 才有意义）",
       (rr.get("jobs") or {}).get("running", 0) >= 1, rr.get("jobs"))

    v = c.get(f"/api/runs/{run_id}").json()
    job = v.get("job") or {}
    show("重启后", {"status": v.get("status"), "job": job.get("job_id"), "phase": job.get("phase"),
                    "slot": v.get("slot")})
    ck("D2 仍重新附着到**同一个**在跑作业",
       job.get("job_id") == job_id and job.get("phase") in ("running", "cancelling"),
       {"job": job.get("job_id"), "phase": job.get("phase")})
    ck("D3 跨重启单槽**没有丢**（活动锁不得被重启误清）",
       (v.get("slot") or {}).get("locked") is True, v.get("slot"))
    ck("D4 重启后仍处于停放（waiting_job：可以再恢复，不会 fail-closed）",
       v.get("status") == "waiting_job", v.get("status"))

    r = c.post(f"/api/runs/{run_id}/jobs/{job_id}/cancel")
    show("cancel 响应", r.json())
    ck("D5 取消请求被接受", r.status_code == 200, r.status_code)
    v = wait_for(c, run_id, lambda x: x.get("status") in ("finished", "failed"), seconds=120, what="取消后终态")
    show("取消后", {"status": v.get("status"), "job": (v.get("job") or {}).get("phase"), "slot": v.get("slot")})
    ck("D6 取消后 run 不是成功态", v.get("status") == "failed", v.get("status"))
    ck("D7 取消后单槽已释放（终态必须释放，否则会把一次失败放大成全体挂起）",
       (v.get("slot") or {}).get("locked") is False, v.get("slot"))


def phase5(c: httpx.Client) -> None:
    print("== phase 5：死任务必须判死（无 rc 不得当成功） ==")
    run_id = _drive_to_job(c, "dead_job")
    v = wait_for(c, run_id, lambda x: x.get("status") in ("finished", "failed"), seconds=180, what="死任务终态")
    show("死任务后", {"status": v.get("status"), "job": v.get("job"), "error": v.get("error")})
    ck("E1 死任务判为 failed（不得静默当成功）", v.get("status") == "failed", v.get("status"))
    ck("E2 死任务后单槽已释放（否则失败会被放大成全体挂起）",
       (v.get("slot") or {}).get("locked") is False, v.get("slot"))
    ev = c.get(f"/api/runs/{run_id}/events", params={"since_seq": 0}).json()["events"]
    ck("E3 事件流记了 dead_job", any(e["kind"] == "dead_job" for e in ev), sorted({e["kind"] for e in ev}))


PHASES = {"1": phase1, "2": phase2, "3": phase3, "4": phase4, "4b": phase4b, "5": phase5}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8099")
    ap.add_argument("--phase", required=True, choices=sorted(PHASES))
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base, timeout=60.0, trust_env=False)
    try:
        PHASES[a.phase](c)
    finally:
        c.close()
    print(f"\n===== phase {a.phase}：PASS={PASS} FAIL={FAIL} =====")
    if FAILED_NAMES:
        print("失败项：")
        for n in FAILED_NAMES:
            print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
