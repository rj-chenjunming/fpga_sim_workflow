"""R 门收口后的**跨切片复核探针**（2026-10-22，Lead 新增证据，只读、临时目录）。

与 `doc/audit/parts/intranet-batch-probe.py` 的区别：旧探针按**旧协议**注入故障/调用旧 JS 签名
（例如直接 monkeypatch `_write_once` 建最终名、用 `X.budget(request, limit)`），R1/R5 修复后
它不再测量真实代码路径。本探针按**现行契约**注入与取数，输出 R1–R5 的收口证据。

用法（仓库根）：`loop/.venv/bin/python doc/evidence/R_BLOCK_B_20261022_after_probe.py`
成功退出 = 全部断言通过；观察成功不等于四道门通过。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "loop"), str(REPO / "loop/tests")]
os.environ.setdefault("LOOP_LLM_MODE", "standin")

from host import agent_control as C, agent_memory as AM, baseline as B  # noqa: E402
from test_baseline_admission import make_baseline  # noqa: E402

FAILS = []


def check(name, ok, **fields):
    print(json.dumps({"check": name, "ok": bool(ok), **fields}, ensure_ascii=False))
    if not ok:
        FAILS.append(name)


def r1_new_protocol_kill():
    """在**新协议**的校验发布点（os.link 到 .sha256 之前）终止子进程。"""
    with tempfile.TemporaryDirectory(prefix="after-r1-") as folder:
        run = Path(folder) / "RUN-AFTER"
        run.mkdir()
        ctx = SimpleNamespace(run_dir=run, run_id=run.name)
        prior = AM.Attempt(ctx, "N3", {"input": {"x": 1}})
        prior.finish("validated", payload={})
        attempt = run / "agent_calls/N3/attempt-000002"
        attempt.mkdir()
        target = attempt / "request.json"
        code = f"""
import os, sys
from pathlib import Path
sys.path.insert(0, {str(REPO / 'loop')!r})
from host import agent_memory as AM
real_link = os.link
def link_then_die(src, dst):
    if Path(dst).suffix == '.sha256':
        os._exit(9)          # 校验和发布前终止：最终名下不应出现半件
    return real_link(src, dst)
os.link = link_then_die
AM.seal_record(Path({str(target)!r}),
               {{'run_id': 'RUN-AFTER', 'node': 'N3', 'attempt': 2}})
"""
        proc = subprocess.run([sys.executable, "-c", code], check=False,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        data_published = target.is_file()
        checksum_published = target.with_suffix(".sha256").is_file()
        state = AM.record_state(target)
        view = C.read_view(run, "N3")
        statuses = {item["attempt"]: item["status"] for item in view["attempts"]}
        completed = attempt / "result.json"
        _ = completed
        check("R1_kill_before_checksum_publish",
              proc.returncode == 9 and data_published and not checksum_published
              and state == "incomplete" and statuses.get(1) is not None
              and statuses.get(2) == "incomplete",
              child_exit=proc.returncode, data_published=data_published,
              checksum_published=checksum_published, state=state, attempt_statuses=statuses)
        # 完成件可核验（同协议的顺序封存不能被误判）
        good = run / "agent_calls/N3/attempt-000003"
        good.mkdir()
        AM.seal_record(good / "request.json", {"run_id": run.name, "node": "N3", "attempt": 3})
        AM.seal_record(good / "result.json", {"run_id": run.name, "node": "N3",
                                              "attempt": 3, "status": "validated"})
        verified = AM.verify_attempt(good)
        check("R1_completed_record_verifiable", verified["request"]["attempt"] == 3)


def r2_relative_escape():
    with tempfile.TemporaryDirectory(prefix="after-r2-") as folder, \
            tempfile.TemporaryDirectory(prefix="after-ext-") as external:
        root = Path(folder) / "workspace"
        base = make_baseline(root, "v1")
        outside = Path(external) / "outside.md5"
        outside.write_bytes(b"outside-data")
        doc = json.loads((base / "manifest.json").read_text())
        doc["allfiles_manifest"]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        results = {}
        for kind, raw in (("relative", os.path.relpath(outside, root)), ("absolute", str(outside))):
            doc["allfiles_manifest"]["path"] = raw
            (base / "manifest.json").write_text(json.dumps(doc))
            record = B.inspect(root, "v1")
            results[kind] = {"valid": record["valid"], "missing": record["missing"],
                             "errors": record["errors"]}
        check("R2_relative_and_absolute_escape_rejected",
              all(not item["valid"] for item in results.values()), results=results)


def r3_non_utf8_manifest():
    from fastapi.testclient import TestClient
    from services import api

    with tempfile.TemporaryDirectory(prefix="after-r3-") as folder:
        root = Path(folder) / "workspace"
        make_baseline(root, "v1")
        bad = root / "baselines" / "v2"
        bad.mkdir()
        (bad / "manifest.json").write_bytes(b"\xff\xfe")
        from unittest.mock import patch
        with patch.object(api.P, "WORKSPACE_ROOT", root):
            client = TestClient(api.app, raise_server_exceptions=False)
            try:
                response = client.get("/api/baselines")
            finally:
                client.close()
        body = response.json()
        items = {item["id"]: item for item in body["baselines"]}
        check("R3_bad_encoding_isolated",
              response.status_code == 200 and items["v1"]["valid"] is True
              and items["v2"]["valid"] is False
              and any("UnicodeDecodeError" in error for error in items["v2"]["errors"]),
              http_status=response.status_code, v1_valid=items["v1"]["valid"],
              v2_valid=items["v2"]["valid"], v2_errors=items["v2"]["errors"])


def r4_feasible_full_plan():
    from workflows.chunks import model_steps as MS

    with tempfile.TemporaryDirectory(prefix="after-r4-") as folder:
        root = Path(folder)
        sandbox = root / "sandbox"
        source = root / "source/TESTLIB"
        sandbox.mkdir()
        source.mkdir(parents=True)
        for index in range(86):
            name = f"tc{index:02}.sv"
            (sandbox / name).write_text("new code\n" * 20)
            (source / name).write_text("old code\n" * 20)
        try:
            cases, names, summary = MS.build_sandbox_cases(sandbox, root / "source", [])
            check("R4_default_budget_uses_full_file",
                  summary["full_files"] == 86 and summary["region_files"] == 0
                  and summary["used_bytes"] <= MS.N8_SANDBOX_BUDGET_BYTES,
                  full_bytes=len(AM.encoded(cases)), summary=summary)
        except RuntimeError as exc:
            check("R4_default_budget_uses_full_file", False, error=str(exc))


def r5_host_is_single_measure():
    with tempfile.TemporaryDirectory(prefix="after-r5-") as folder:
        run = Path(folder) / "RUN-R5"
        run.mkdir()
        ctx = SimpleNamespace(run_dir=run, run_id=run.name)
        request = {"input": {"x": "中文", "n": 1}, "info": "i", "instruct": "z\tz",
                   "schema": {"type": "object"},
                   "offered": {"cases": ["x" * 100]}, "scope": {"a": "b"}}
        attempt = AM.Attempt(ctx, "N3", request)
        sealed = (attempt.path / "request.json")
        record = json.loads(sealed.read_text())
        host = AM.check_budget(record["input"],
                              {k: record[k] for k in ("info", "instruct", "schema")})
        measure = AM.context_budget(record, attempt=1)
        module = str(REPO / "loop/web/context-explain.js")
        script = ("const X=require(" + json.dumps(module) + ");" +
                  "console.log(JSON.stringify(X.budget(" + json.dumps(measure) + ")))")
        window = json.loads(subprocess.check_output(["node", "-e", script], text=True))
        total = sum(measure["breakdown"].values()) + measure["overhead_bytes"]
        check("R5_host_api_window_same_bytes",
              host == measure["used_bytes"] == window["totalBytes"] and total == host
              and window["tokenEstimate"] == "unknown"
              and measure["storage"]["offered_bytes"] > 0,
              host_bytes=host, api_bytes=measure["used_bytes"],
              window_bytes=window["totalBytes"], breakdown=measure["breakdown"],
              overhead_bytes=measure["overhead_bytes"], storage=measure["storage"],
              token=window["tokenEstimate"])


if __name__ == "__main__":
    r1_new_protocol_kill()
    r2_relative_escape()
    r3_non_utf8_manifest()
    r4_feasible_full_plan()
    r5_host_is_single_measure()
    print(json.dumps({"fails": FAILS}, ensure_ascii=False))
    raise SystemExit(1 if FAILS else 0)
