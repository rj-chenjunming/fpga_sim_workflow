"""Read-only review probes for a19107c; uses temporary fixtures and no providers.

Run from any directory with loop/.venv/bin/python. Observations describe current
defects; successful exit is not acceptance of the implementation.
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
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "loop"), str(REPO / "loop/tests")]
os.environ.setdefault("LOOP_LLM_MODE", "standin")

from host import agent_control as C, agent_memory as AM, baseline as B
from test_baseline_admission import make_baseline
from workflows.chunks import model_steps as MS


def emit(probe, **fields):
    print(json.dumps({"probe": probe, **fields}, ensure_ascii=False))


def baseline_probes():
    from fastapi.testclient import TestClient
    from services import api

    with tempfile.TemporaryDirectory(prefix="review-baseline-") as folder, \
            tempfile.TemporaryDirectory(prefix="review-external-") as external:
        root = Path(folder) / "workspace"
        base = make_baseline(root, "v1")
        outside = Path(external) / "outside.md5"
        outside.write_bytes(b"outside-data")
        doc = json.loads((base / "manifest.json").read_text())
        doc["allfiles_manifest"]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
        allowed = (root, root.parent, B.P.ENV_ROOT)
        for kind, raw in (("relative", os.path.relpath(outside, root)),
                          ("absolute", str(outside))):
            doc["allfiles_manifest"]["path"] = raw
            (base / "manifest.json").write_text(json.dumps(doc))
            result = B.inspect(root, "v1")
            emit("artifact_boundary", kind=kind, valid=result["valid"],
                 outside_all_allowed_roots=all(
                     not outside.resolve().is_relative_to(p.resolve()) for p in allowed))
        (base / "manifest.json").write_bytes(b"\xff\xfe")
        with patch.object(api.P, "WORKSPACE_ROOT", root):
            # No context manager: do not start application lifespan/recovery.
            client = TestClient(api.app, raise_server_exceptions=False)
            try:
                emit("manifest_encoding", http_status=client.get("/api/baselines").status_code)
            finally:
                client.close()


def publish_probe():
    with tempfile.TemporaryDirectory(prefix="review-seal-") as folder:
        run = Path(folder) / "RUN-REVIEW"
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
write = AM._write_once
def die_after_checksum_open(path, content):
    if path.suffix == '.sha256':
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os._exit(9)
    write(path, content)
AM._write_once = die_after_checksum_open
AM.seal_record(Path({str(target)!r}),
               {{'run_id': 'RUN-REVIEW', 'node': 'N3', 'attempt': 2}})
"""
        proc = subprocess.run([sys.executable, "-c", code], check=False,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            C.read_view(run, "N3")
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        emit("checksum_publication_crash", child_exit=proc.returncode,
             prior_state=AM.record_state(prior.path / "request.json"),
             checksum_bytes=target.with_suffix(".sha256").stat().st_size,
             partial_state=AM.record_state(target), read_error=error)


def n8_probe():
    with tempfile.TemporaryDirectory(prefix="review-n8-") as folder:
        root = Path(folder)
        sandbox = root / "sandbox"
        source = root / "source/TESTLIB"
        sandbox.mkdir()
        source.mkdir(parents=True)
        for index in range(86):
            name = f"tc{index:02}.sv"
            (sandbox / name).write_text("new code\n" * 20)
            (source / name).write_text("old code\n" * 20)
        full, _, _ = MS.build_sandbox_cases(sandbox, root / "source", [], budget_bytes=10**7)
        try:
            result = MS.build_sandbox_cases(sandbox, root / "source", [])[2]
        except RuntimeError as exc:
            result = str(exc).split("（")[0]
        emit("n8_feasible_full_plan", full_bytes=len(AM.encoded(full)),
             budget=MS.N8_SANDBOX_BUDGET_BYTES, actual=result)


def budget_probe():
    request = {"input": {"x": "y"}, "info": "i", "instruct": "z",
               "schema": {"type": "object"}, "offered": {"cases": ["x" * 1000]},
               "scope": {"a": "b"}}
    host = AM.check_budget(request["input"], {k: request[k] for k in ("info", "instruct", "schema")})
    module = str(REPO / "loop/web/context-explain.js")
    script = ("const X=require(" + json.dumps(module) + ");" +
              "console.log(JSON.stringify(X.budget(" + json.dumps(request) + ",120000)))")
    view = json.loads(subprocess.check_output(["node", "-e", script], text=True))
    emit("context_budget", host_bytes=host, displayed_bytes=view["totalBytes"])


if __name__ == "__main__":
    baseline_probes()
    publish_probe()
    n8_probe()
    budget_probe()
