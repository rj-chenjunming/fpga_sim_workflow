"""S7a 探针：N6 材料面/提交格式收口 + DS-06 真机（**一次一个模式，不重试**）。

三种模式：
  --dry-run      纯 Host：建 run 目录 → build_n6_targets → **真的**物化 attempt 工作区
                 （`DshBackend.prepare_attempt`，不启进程、不烧 token）→ 打印材料面 +
                 渲染出的任务文本长度与前 400 字。证明"材料面瘦身 + prompt 渲染"生效。
  --offline-chain 纯 Host：用 S6 第 4 次**真实候选字节**（15647 B / md5 53f06f1b…）+
                 该次真实 payload（line 218 → 文件实际 217 的**已知错误已按文件更正**）回放
                 `n6_apply` 的导入链路：候选由 Host 导入并施加，落 `sandbox/TESTLIB/`。
                 **不是** DS-06 真机通过（没有模型参与，没有真机 attempt）。
  --live          真机：一次 N6 调用（`LOOP_LLM_MODE=live`），上限 = SETTINGS 的 300 s（断言），
                 然后 `n6_apply`。usage/session 拿不到就写 unknown（**不填 0**）。

纪律：探针不入库（gitignored `loop/.logs/s7a/`）；不写 ENV_ROOT；密钥只在子进程 env，
输出统一脱敏；`attempts.jsonl` 只增不改。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

LOOP_DIR = Path(os.environ.get("S7_LOOP_DIR") or os.getcwd()).resolve()
sys.path.insert(0, str(LOOP_DIR))
STATE = LOOP_DIR / ".logs" / "s7a" / "state"
os.environ.setdefault("LOOP_STATE_ROOT", str(STATE))

from host import agent_backends as AB  # noqa: E402
from host import paths as P  # noqa: E402
from host.agent_backends import dsh as D  # noqa: E402
from host.agent_backends import dsh_assets as A  # noqa: E402
from host.progress import ProgressLog  # noqa: E402
from services.contracts import KbSources  # noqa: E402
from workflows.chunks import host_steps, model_steps as M  # noqa: E402
from workflows.chunks import n6_facts  # noqa: E402
from workflows.chunks import model_request as MR  # noqa: E402
from workflows.context import RunCtx  # noqa: E402

#: 夹具固定取**真实 ENV_ROOT**（只读）：不随 `LOOP_WORKSPACE` 变（可写数据根里没有历史夹具）
FIXTURE = P.ENV_ROOT / "kb" / "runs" / "RUN-20261015-120626"
#: S6 第 4 次真实调用的候选（保留在 gitignored 工作区里；md5 与 S6 证据档一致）
S6_RUN4_CANDIDATE = (LOOP_DIR / ".logs" / "s6" / "ws-real4" / "runs" / "RUN-20261029-S6-04"
                     / "agent_workspaces" / "N6" / "attempt-000001" / "work" / "candidate"
                     / "TESTLIB" / "tc_bmc_i2c_03.sv")
#: 该次真实 payload 的 revisions（S6 证据 `raw/n6_run4_model_payload_summary.json` 的 first_edit）
S6_RUN4_EDITS = [
    {"line": 217,   # 真实提交写 218；文件实际 217（S6 证据 §3 第 4 次第 2 条）
     "old": "    task sys_reg_test(int pid);\n        bit[31:0] base_addr;",
     "new": "    task sys_reg_test(int pid);\n        bit[31:0] base_addr;\n        bit[31:0] fpga_date_exp;",
     "basis": "为观测点新增 task 局部变量（excerpts 217 行起，sys_reg_test 唯一）"},
    {"line": 222,
     "old": "        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_0000, `REG_FPGA_DATE, 1);",
     "new": ("        fpga_date_exp = 32'h2026_0708;\n"
             "        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_0000, fpga_date_exp, 1);\n"
             "        `uvm_info(\"N6_fpga_date\", $sformatf(\"OK 0x0000+0x04 fpga_date = 0x%08h\", fpga_date_exp), UVM_LOW)"),
     "basis": "doc_bitdef fpga_date.reset 2023_0911→2026_0708"},
]


class Data:
    def __init__(self, ctx: RunCtx, repo_root: Path, state: dict[str, Any] | None = None):
        self.resources = {"repo_root": repo_root, "loop_ctx": ctx}
        self.state = dict(state or {})
        self.emitted: list[Any] = []

    def get_state(self, key: str) -> Any:
        return self.state.get(key)

    def require_resource(self, key: str) -> Any:
        return self.resources[key]

    async def async_set_state(self, key: str, value: Any) -> None:
        self.state[key] = value

    async def async_emit(self, key: str, value: Any) -> None:
        self.emitted.append(key)


def redact(text: str) -> str:
    for value in (os.environ.get("PUBLIC_API_KEY"), os.environ.get("LOOP_LLM_API_KEY")):
        if value and len(value) > 8:
            text = text.replace(value, "[redacted]")
    try:
        from host import model_provider as MP
        secret = getattr(MP.resolve(), "_api_key", None)
        if secret and len(secret) > 8:
            text = text.replace(secret, "[redacted]")
    except Exception:  # noqa: BLE001 - 脱敏尽力而为，不因解析失败中断
        pass
    return text


def build_run(ws: Path, run_id: str) -> tuple[RunCtx, Path]:
    """建一个**真夹具形态**的 run 目录：run 产物是原件（含 345 KB n5_impact），
    材料面瘦身由生产代码（`dsh_assets.materials_for`）负责 —— 探针不替生产瘦身。"""
    run_dir = ws / "runs" / run_id
    if run_dir.exists():
        raise SystemExit("run_dir 已存在（拒绝复用 run 身份）：%s" % run_dir)
    run_dir.mkdir(parents=True)
    # **不拷 case_states.json**：那是上一轮的台账（run_id 不同），拷进来会被
    # `_ensure_case_state` 判成身份错位（正确行为）。
    for name in ("n1_manifest_new.json", "n2_diff.json", "n2_diff.md", "n3_digest.md",
                 "n5_impact.json", "n5_impact.md"):
        source = FIXTURE / name
        if source.is_file():
            shutil.copy2(source, run_dir / name)
    marker_lines = [line for line in (FIXTURE / "bundle" / "doc_entries.jsonl")
                    .read_text(encoding="utf-8").splitlines() if "fpga_date" in line]
    (run_dir / "doc_entries.jsonl").write_text(
        (marker_lines[0] if marker_lines else "{}") + "\n", encoding="utf-8")
    kb_root = ws / "kb"
    (kb_root / "conflicts").mkdir(parents=True, exist_ok=True)
    (kb_root / "conflicts" / "conflicts.json").write_text(
        '{"schema": "kb/conflicts", "version": 1, "conflicts": [], "items": []}', encoding="utf-8")
    ctx = RunCtx(run_id=run_id, run_dir=run_dir, mode="real", scenario="happy",
                 kb=KbSources.from_workspace(kb_root),
                 progress=ProgressLog(ws / "events", run_id))
    return ctx, P.ENV_ROOT


def backend() -> D.DshBackend:
    """生产形态后端（配置来自仓内 SETTINGS；不启进程时不需要凭据）。"""
    cfg = D.config_from_settings()
    cfg.verify(wrap_required=True)
    return D.DshBackend(cfg)


def one_target(ctx: RunCtx, repo_root: Path) -> dict[str, Any]:
    """单目标：真夹具 5 个 must_change 里取第一个（tc_bmc_i2c_03，与 S6 真机同一个）。"""
    targets = n6_facts.build_n6_targets(ctx, Data(ctx, repo_root))
    keep = [item for item in targets if item.get("case") == "tc_bmc_i2c_03"]
    if not keep:
        raise SystemExit("夹具里没有 tc_bmc_i2c_03 目标（夹具变了？）：%s"
                         % [t.get("case") for t in targets])
    return keep[0]


def material_face(workspace: D.AttemptWorkspace) -> dict[str, Any]:
    input_dir = workspace.layout.input_dir
    staged = []
    for path in sorted(input_dir.rglob("*")):
        if path.is_file():
            staged.append({"name": path.relative_to(input_dir).as_posix(),
                           "size": path.stat().st_size,
                           "md5": hashlib.md5(path.read_bytes()).hexdigest()})
    return {"attempt_root": str(workspace.root), "staged": staged,
            "total_bytes": sum(item["size"] for item in staged),
            "materials": list(workspace.materials)}


def dry_run(args: argparse.Namespace) -> int:
    ws = Path(args.ws).resolve()
    ctx, repo_root = build_run(ws, args.run_id)
    target = one_target(ctx, repo_root)
    # 生产形态：`model_request._attempt_sources` 会把 N6 目标用例源件只读摆进 input/TESTLIB/
    sources = ((repo_root, str(target.get("file") or "TESTLIB/%s.sv" % target.get("case"))),)
    workspace = backend().prepare_attempt(ctx.run_dir, "N6", 1, sources=sources)
    face = material_face(workspace)
    contract = MR.request_contract("n6_author")
    request = D.BackendRequest(input_data={"targets": [target], "run_id": ctx.run_id},
                               info=contract["info"], instruct=contract["instruct"],
                               schema=contract["schema"])
    task = D._compose_task(request, attempt_key="%s/N6/1" % ctx.run_id)
    print("== 材料面（N6） ==")
    print(json.dumps(face, ensure_ascii=False, indent=1))
    print("== 任务文本 ==")
    print("chars=%d（含 [schema]）" % len(task))
    print(task[:400].replace("\n", "\\n"))
    payload = {"mode": "dry-run", "run_id": ctx.run_id, "target": target.get("case"),
               "target_line": (target.get("excerpts") or [{}])[0].get("line")
               if target.get("excerpts") else target.get("excerpt", {}).get("line"),
               "material_face": face, "task_chars": len(task),
               "task_head": task[:400], "config_timeout_s": D.config_from_settings().timeout_s}
    out = Path(args.raw) / "s7a_dry_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("dry-run OK（未调用模型）；raw =", out)
    return 0


def offline_chain(args: argparse.Namespace) -> int:
    """用 S6 第 4 次**真实候选字节**回放导入链路（不调模型）。"""
    ws = Path(args.ws).resolve()
    ctx, repo_root = build_run(ws, args.run_id)
    target = one_target(ctx, repo_root)
    workspace = backend().prepare_attempt(ctx.run_dir, "N6", 1)
    if not S6_RUN4_CANDIDATE.is_file():
        raise SystemExit("缺 S6 第 4 次真实候选：%s" % S6_RUN4_CANDIDATE)
    payload_bytes = S6_RUN4_CANDIDATE.read_bytes()
    candidate_file = workspace.layout.candidate / "TESTLIB" / "tc_bmc_i2c_03.sv"
    candidate_file.parent.mkdir(parents=True, exist_ok=True)
    candidate_file.write_bytes(payload_bytes)
    from host import agent_candidate_import as CI

    expected = [M._candidate_contract_path("tc_bmc_i2c_03")]
    manifest = CI.snapshot_candidate_manifest(workspace.layout.candidate, expected)
    baseline = {rel: hashlib.md5((repo_root / "TESTLIB" / "tc_bmc_i2c_03.sv").read_bytes()).hexdigest()
                for rel in manifest}
    author_out = {
        "mode": "live",
        "data": {"revisions": [{"case": "tc_bmc_i2c_03", "edits": S6_RUN4_EDITS}],
                 "observation_points": [{"case": "tc_bmc_i2c_03", "marker": "N6_fpga_date"}],
                 "notes": "offline replay of S6 run4 real payload with line 218→217 corrected"},
        "validation": {"ok": True, "problems": [], "accepted": {}},
        host_steps.CANDIDATE_ROOT_KEY: str(workspace.layout.candidate),
        host_steps.CANDIDATE_MANIFEST_KEY: manifest,
        host_steps.CANDIDATE_BASELINE_KEY: baseline,
        host_steps.CANDIDATE_EXECUTION_KEY: "stopped",
    }
    data = Data(ctx, repo_root, state={"n6_targets": {"targets": [target]},
                                       "n6_author": author_out})
    applied = asyncio.run(host_steps.n6_apply(data))
    result = {
        "mode": "offline-chain", "run_id": ctx.run_id,
        "candidate": {"path": "work/candidate/TESTLIB/tc_bmc_i2c_03.sv",
                      "size": len(payload_bytes),
                      "md5": hashlib.md5(payload_bytes).hexdigest(),
                      "origin": "S6 run4 real candidate"},
        "edits_line_correction": {"submitted_by_model": 218, "actual_file_line": 217},
        "status": applied.get("status"),
        "cases": [{k: c.get(k) for k in ("case", "source", "md5_before", "md5_after", "edits")}
                  for c in (applied.get("cases") or [])],
        "candidate_import": applied.get("candidate_import"),
    }
    out = Path(args.raw) / "s7a_offline_chain.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT:", json.dumps({k: result[k] for k in ("status", "cases", "candidate_import")},
                                ensure_ascii=False))
    # 候选自洽性：沙箱产出必须与真实候选字节逐字一致（EDITS_MISMATCH 的反向核对）
    sandbox_case = ctx.run_dir / "sandbox" / "TESTLIB" / "tc_bmc_i2c_03.sv"
    same = sandbox_case.is_file() and sandbox_case.read_bytes() == payload_bytes
    print("sandbox == real candidate bytes:", same)
    return 0 if result["status"] == "applied" and same else 1


async def live(args: argparse.Namespace) -> int:
    if os.environ.get("LOOP_LLM_MODE", "").strip().lower() != "live":
        raise SystemExit("必须显式 LOOP_LLM_MODE=live 才允许真实调用")
    cfg = D.config_from_settings()
    assert cfg.timeout_s == 300, "授权上限必须真的生效：SETTINGS timeout_s=%r" % (cfg.timeout_s,)
    ws = Path(args.ws).resolve()
    ctx, repo_root = build_run(ws, args.run_id)
    target = one_target(ctx, repo_root)
    data = Data(ctx, repo_root)
    print("target:", target.get("case"), "| file:", target.get("file"))

    started = time.time()
    exit_kind, error = "completed", None
    try:
        out = await asyncio.wait_for(M.n6_author(data), float(cfg.timeout_s))
    except asyncio.TimeoutError:
        exit_kind, error = "failed", "timeout>%ss（已停止，不重发）" % cfg.timeout_s
        out = {}
    except Exception as exc:  # noqa: BLE001 - 失败如实记录
        exit_kind, error = "failed", "%s: %s" % (type(exc).__name__, exc)
        out = {}
    wall_s = round(time.time() - started, 3)

    usage: dict[str, Any] = {"inputTokens": "unknown", "outputTokens": "unknown",
                             "totalTokens": "unknown", "cacheReadTokens": "unknown"}
    session_id, attempt_rel = "unknown", "unknown"
    calls = sorted((ctx.run_dir / "agent_calls" / "N6").glob("attempt-*"))
    if calls:
        attempt_rel = calls[0].relative_to(ctx.run_dir).as_posix()
        from host import agent_memory as AM
        try:
            rec = AM.verify_attempt(calls[0])
            payload = rec["result"].get("payload") or {}
            got = payload.get("usage") or {}
            if isinstance(got, dict) and got:
                usage = {k: got.get(k, "unknown") for k in usage}
            session_id = payload.get("session_id") or "unknown"
        except (OSError, ValueError):
            pass

    keys = (host_steps.CANDIDATE_ROOT_KEY, host_steps.CANDIDATE_MANIFEST_KEY,
            host_steps.CANDIDATE_BASELINE_KEY, host_steps.CANDIDATE_EXECUTION_KEY)
    channel = {k: out.get(k) for k in keys} if out else {}
    applied: dict[str, Any] = {}
    if out and (out.get("validation") or {}).get("ok") is True:
        try:
            # 探针 bug 更正（RUN-20261029-100500 暴露）：`n6_author` 自己按夹具构建**全部**
            # 目标并产出全部候选，`n6_apply` 必须喂同一组目标，否则 Host 正确判"revision 含
            # 非目标用例"。这里改成按 run 现算（不手抄 [target]）。
            all_targets = n6_facts.build_n6_targets(ctx, data)
            await data.async_set_state("n6_targets", {"targets": all_targets})
            applied = await host_steps.n6_apply(data)
        except Exception as exc:  # noqa: BLE001 - 导入失败也是证据
            applied = {"status": "failed", "error": redact("%s: %s" % (type(exc).__name__, exc))}
    result = {
        "mode": "live", "run_id": ctx.run_id, "exit": exit_kind,
        "error": redact(str(error)) if error else None,
        "wall_s": wall_s, "timeout_s": cfg.timeout_s, "usage": usage, "session_id": session_id,
        "validation": (out.get("validation") or {}) if out else None,
        "channel": channel,
        "apply_status": applied.get("status"),
        "candidate_import": applied.get("candidate_import"),
        "apply_error": redact(str(applied.get("error") or "")) if applied.get("error") else None,
        "apply_cases": [{k: c.get(k) for k in ("case", "source", "md5_after")}
                        for c in (applied.get("cases") or [])],
    }
    out_path = Path(args.raw) / ("s7a_live_%s.json" % args.run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    line = {"attempt_key": "%s/N6/1" % ctx.run_id, "exit": exit_kind, "wall_s": wall_s,
            "usage": usage, "session_id": session_id, "attempt_record": attempt_rel,
            "stop_confirmed": channel.get(host_steps.CANDIDATE_EXECUTION_KEY) if channel else None,
            "validation_ok": (out.get("validation") or {}).get("ok") if out else None,
            "apply_status": applied.get("status"),
            "error": redact(str(error)) if error else None}
    with (Path(args.raw) / "attempts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    print("RESULT:", json.dumps(line, ensure_ascii=False))
    ok = (exit_kind == "completed"
          and (out.get("validation") or {}).get("ok") is True
          and channel.get(host_steps.CANDIDATE_EXECUTION_KEY) == "stopped")
    if args.apply and ok:
        print("N6 收口条件满足（submit accepted + validation ok + 停止确认）；n6_apply =",
              applied.get("status"))
    return 0 if ok else 1


def replay_apply(args: argparse.Namespace) -> int:
    """对一次**已完成的真实 attempt** 重放 Host 导入步骤（不调模型、不新起 attempt）。

    为什么允许：模型输出与候选字节都是那次真实 attempt 的产物（`completed` +
    `validation.ok=true` + `execution_state=stopped`）；探针只把 `n6_targets` 喂错了
    （只给 1 个目标），Host 因此正确 fail-closed。这里按同一次 attempt 的真实产出重跑
    `n6_apply`，不伪造任何模型事实（四键取自该次 attempt 的封存输出，候选取自该次工作区）。
    """
    result_path = Path(args.result_file).resolve()
    recorded = json.loads(result_path.read_text(encoding="utf-8"))
    run_id = recorded["run_id"]
    run_dir = Path(args.ws).resolve() / "runs" / run_id
    if not run_dir.is_dir():
        raise SystemExit("run_dir 不存在：%s" % run_dir)
    kb_root = Path(args.ws).resolve() / "kb"
    ctx = RunCtx(run_id=run_id, run_dir=run_dir, mode="real", scenario="happy",
                 kb=KbSources.from_workspace(kb_root),
                 progress=ProgressLog(Path(args.ws).resolve() / "events", run_id))
    data = Data(ctx, P.ENV_ROOT)
    targets = n6_facts.build_n6_targets(ctx, data)
    accepted = ((recorded.get("validation") or {}).get("accepted") or {})
    channel = recorded.get("channel") or {}
    author_out = {
        "mode": "live",
        "data": {key: accepted.get(key) for key in
                 ("revisions", "observation_points", "notes", "issue_responses",
                  "rework_resolution")},
        "validation": recorded.get("validation"),
        host_steps.CANDIDATE_ROOT_KEY: channel.get(host_steps.CANDIDATE_ROOT_KEY),
        host_steps.CANDIDATE_MANIFEST_KEY: channel.get(host_steps.CANDIDATE_MANIFEST_KEY),
        host_steps.CANDIDATE_BASELINE_KEY: channel.get(host_steps.CANDIDATE_BASELINE_KEY),
        host_steps.CANDIDATE_EXECUTION_KEY: channel.get(host_steps.CANDIDATE_EXECUTION_KEY),
    }
    data.state = {"n6_targets": {"targets": targets}, "n6_author": author_out}
    applied = asyncio.run(host_steps.n6_apply(data))
    payload = {"mode": "replay-apply", "run_id": run_id,
               "source_result": str(result_path),
               "targets": [item.get("case") for item in targets],
               "manifest": channel.get(host_steps.CANDIDATE_MANIFEST_KEY),
               "status": applied.get("status"),
               "candidate_import": applied.get("candidate_import"),
               "cases": [{k: c.get(k) for k in ("case", "source", "md5_before", "md5_after", "edits")}
                         for c in (applied.get("cases") or [])],
               "error": redact(str(applied.get("error") or "")) if applied.get("error") else None}
    out_path = Path(args.raw) / ("s7a_replay_apply_%s.json" % run_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT:", json.dumps({k: payload[k] for k in ("status", "cases", "error")},
                                ensure_ascii=False))
    print("candidate_import.ok =", (payload["candidate_import"] or {}).get("ok"))
    return 0 if payload["status"] == "applied" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=str(LOOP_DIR / ".logs" / "s7a" / "ws"))
    ap.add_argument("--raw", default=str(LOOP_DIR / ".logs" / "s7a" / "raw"))
    ap.add_argument("--run-id", default="RUN-20261029-S7A-01")
    ap.add_argument("--apply", action="store_true", help="live 成功后立刻跑 n6_apply（DS-06）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline-chain", action="store_true")
    ap.add_argument("--replay-apply", action="store_true")
    ap.add_argument("--result-file", default="")
    args = ap.parse_args()
    if args.dry_run:
        return dry_run(args)
    if args.offline_chain:
        return offline_chain(args)
    if args.replay_apply:
        return replay_apply(args)
    return asyncio.run(live(args))


if __name__ == "__main__":
    raise SystemExit(main())
