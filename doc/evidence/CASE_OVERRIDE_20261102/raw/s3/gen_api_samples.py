"""S3 四类响应样例生成器：真实 FastAPI 路由 + 真实 kb CLI（TestClient 进程内，不启常驻服务）。

用法：cd loop && LOOP_LLM_MODE=standin LOOP_STATE_ROOT=<tmp> .venv/bin/python \
        .logs/case_override/s3/gen_api_samples.py > .logs/case_override/s3/api-samples.log
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "loop"))

from fastapi.testclient import TestClient  # noqa: E402

from host import paths as P  # noqa: E402
from services import api as api_mod  # noqa: E402

HUMAN = "human:chenjunming"
REASON = "期望值来自旧文档条目；实测值与本变预期一致，属期望过期"


def kb(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", str(P.KB_TOOLS / "case_state.py"), *args],
                          cwd=str(REPO), capture_output=True, text=True)


def new_run(tmp: Path) -> SimpleNamespace:
    run_id = f"RUN-20261102-{uuid.uuid4().int % 1_000_000:06d}"
    run_dir = tmp / "runs" / run_id
    run_dir.mkdir(parents=True)
    ledger = run_dir / "case_states.json"
    assert kb("init", "--run", run_id, "--state-file", str(ledger)).returncode == 0
    for case in ("tc_rtc_05", "tc_rtc_10"):
        r = kb("set", "--run", run_id, "--state-file", str(ledger), "--case", case,
               "--state", "已修订待验", "--note", "N10 判据未通过 ⇒ 待验")
        assert r.returncode == 0, r.stderr
    (run_dir / "n10_cases.json").write_text(json.dumps({
        "schema": "loop/n10_cases", "run_id": run_id,
        "created_at": "2026-11-02T13:00:00+0800",
        "criterion": "聚合判据 = 各用例 I3 判据的合取（含印记三向一致）",
        "cases": {case: {
            "case": case, "passed": False,
            "criterion": "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致",
            "reasons": [f"印记 N6_pcie_test_{case} 三向不一致：['value_matches_expected']"],
            "counts": {"koutou1": {"value": 0},
                       "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
            "imprints": {f"N6_pcie_test_{case}": {"consistent": False}},
            "evidence": {"path": f"evidence/20261102-130000_{case}_1_run.log",
                         "md5": "a" * 32, "bytes": 123456},
        } for case in ("tc_rtc_05", "tc_rtc_10")},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return SimpleNamespace(run_id=run_id, run_dir=run_dir, ledger=ledger)


def client(run: SimpleNamespace, *, status: str = "waiting_gate") -> TestClient:
    doc = SimpleNamespace(run_dir=str(run.run_dir), status=status,
                          pending_interrupt={"id": "G2_report_accept:RUN"})

    class M:
        def __init__(self) -> None:
            self.docs = {run.run_id: doc}

    api_mod._manager = lambda: M()  # 样例脚本：复用真实路由与真实服务层
    return TestClient(api_mod.app)


def show(label: str, resp) -> None:
    print(f"\n===== {label} -> HTTP {resp.status_code} =====")
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="s3-sample-"))
    run = new_run(tmp)
    c = client(run)

    show("POST /api/runs/{id}/cases/override  (action=pass, 单例)", c.post(
        f"/api/runs/{run.run_id}/cases/override",
        json={"action": "pass", "cases": ["tc_rtc_05"], "actor": HUMAN, "reason": REASON}))

    # 只读投影（run_view.case_override / gate_material.case_override 同一形状）
    from services import contracts  # noqa: E402

    print("\n===== 投影样例：run_view.case_override（run_status=waiting_gate；"
          "tc_rtc_05 已豁免、tc_rtc_10 仍待验）=====")
    print(json.dumps(contracts.case_override_view(run.run_dir, run_status="waiting_gate"),
                     ensure_ascii=False, indent=2))

    show("400 请求体形状错（action 不在枚举）", c.post(
        f"/api/runs/{run.run_id}/cases/override",
        json={"action": "maybe", "cases": ["tc_rtc_05"], "actor": HUMAN, "reason": REASON}))

    show("403 §4-1 actor 非 human", c.post(
        f"/api/runs/{run.run_id}/cases/override",
        json={"action": "pass", "cases": ["tc_rtc_10"], "actor": "model:gpt", "reason": REASON}))

    c_running = client(run, status="running")
    show("403 §4-6 run 状态 running", c_running.post(
        f"/api/runs/{run.run_id}/cases/override",
        json={"action": "pass", "cases": ["tc_rtc_10"], "actor": HUMAN, "reason": REASON}))

    c = client(run)
    ledger = json.loads(run.ledger.read_text(encoding="utf-8"))
    entry = next(x for x in ledger["cases"] if x["case"] == "tc_rtc_05")
    entry["overrides"][0]["reason"] = "篡改后的理由（record_sha256 不再匹配）"
    run.ledger.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    show("409 锚复核失败（kb rc=4）", c.post(
        f"/api/runs/{run.run_id}/cases/override",
        json={"action": "revoke", "cases": ["tc_rtc_05"], "actor": HUMAN, "reason": REASON}))


main()
