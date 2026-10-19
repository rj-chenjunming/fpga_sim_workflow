"""WS-K 修复回归（F-01/F-02、I3 印记、I4/I8/I20、I7 边界、case_state、证据聚合）。

约束
    * 不写权威 ENV_ROOT、不跑真实仿真：所有 kb 工具调用都用 **tmp_path 造的最小 fake env**
      （`LOOP_ENV_ROOT` / `LOOP_WORKSPACE` 都是 tmp 目录，WORKSPACE 在 ENV_ROOT 之外）。
    * 证据聚合/判定用 tmp 目录里的合成日志，不依赖归档夹具（fixture 缺失也不假过）。
    * 每个测试用唯一 run_id / 独立目录。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB_TOOLS = ROOT / "kb" / "tools"
LOOP_DIR = ROOT / "loop"

#: 固定注入时刻（README §3.1.1：时间是唯一允许的非确定性，必须经 --now/KB_NOW）
NOW = "2026-10-19T18:00:00+0800"
RUN = "RUN-20261019-180000"
G1_ACTOR = "human:lead"


# ---------------------------------------------------------------- 帮助函数


def _clean_env() -> dict:
    env = dict(os.environ)
    for key in ("KB_NOW", "LOOP_NOW", "LOOP_ENV_ROOT", "LOOP_WORKSPACE", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(script, *args, env_extra=None, timeout=180):
    env = _clean_env()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(KB_TOOLS / script)] + [str(a) for a in args],
        capture_output=True, text=True, env=env, cwd=str(ROOT), timeout=timeout,
    )


def _make_fake_env(tmp_path: Path):
    """最小 fake env + workspace：RTL/TB/PKG/TESTLIB/doc + regmap + 空冲突清单。"""
    env_dir = tmp_path / "env"
    ws = tmp_path / "ws"
    for d in ("RTL/SRC/imports", "RTL/RTL_COMMON", "TB", "TESTLIB", "PKG", "doc/reference"):
        (env_dir / d).mkdir(parents=True, exist_ok=True)
    (ws / "index").mkdir(parents=True, exist_ok=True)
    (ws / "conflicts").mkdir(parents=True, exist_ok=True)
    (env_dir / "RTL/SRC/imports/a.v").write_text("module a; endmodule\n", encoding="utf-8")
    (env_dir / "RTL/RTL_COMMON/b.v").write_text("module b; endmodule\n", encoding="utf-8")
    (env_dir / "TB/t.sv").write_text("module t; endmodule\n", encoding="utf-8")
    (env_dir / "TESTLIB/tc_x.sv").write_text("module tc_x; endmodule\n", encoding="utf-8")
    (env_dir / "PKG/p.txt").write_text("pkg\n", encoding="utf-8")
    (env_dir / "doc/reference/doc.md").write_text(
        "| 0x0004 | date | R | 0x2026_0708 | 4 | x |\n", encoding="utf-8")
    regmap = {
        "schema": "kb/index/regmap", "version": 1,
        "source_doc": "doc/reference/doc.md",
        "entries": [{
            "entry_id": "0x0000#0x0004", "segment": "0x0000",
            "offset_global": "0x0004", "name": "fpga_date", "rw": "R",
            "reset": "2026_0708", "bytes": 4, "bitdef_present": True,
            "sources": [{"kind": "summary", "line": 1}], "conflict_ids": [],
            "raw_line": "| 0x0004 | date | R | 0x2026_0708 | 4 | x |",
        }],
    }
    (ws / "index/regmap.json").write_text(json.dumps(regmap, ensure_ascii=False),
                                         encoding="utf-8")
    _write_conflicts(ws, [])
    return env_dir, ws


def _write_conflicts(ws: Path, conflicts: list[dict]):
    doc = {"schema": "kb/conflicts/conflicts", "version": 1,
           "source_note": "tmp", "expected_total": len(conflicts),
           "conflicts": conflicts}
    (ws / "conflicts/conflicts.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _fenv(env_dir: Path, ws: Path) -> dict:
    return {"LOOP_ENV_ROOT": str(env_dir), "LOOP_WORKSPACE": str(ws)}


def _build_v0(env_dir: Path, ws: Path):
    p = _run("n1_snapshot.py", "build", "--out-baseline", "v0", "--now", NOW,
             env_extra=_fenv(env_dir, ws))
    assert p.returncode == 0, p.stderr
    manifest = ws / "baselines/v0/manifest.json"
    assert manifest.is_file()
    return manifest


def _stage(env_dir: Path, ws: Path, run=RUN):
    p = _run("n1_snapshot.py", "stage", "--parent", "v0", "--run", run, "--now", NOW,
             env_extra=_fenv(env_dir, ws))
    assert p.returncode == 0, p.stderr
    return ws / "runs" / run / "n1_manifest_new.json"


def _sign_gates(env_dir: Path, ws: Path, run=RUN, g3="milestone_only",
                actor=G1_ACTOR, actor_kind="human"):
    env_extra = _fenv(env_dir, ws)
    p = _run("gate.py", "init", "--run", run,
             "--from-manifest", str(ws / "baselines/v0/manifest.json"),
             "--to-manifest", str(ws / "runs" / run / "n1_manifest_new.json"),
             "--now", NOW, env_extra=env_extra)
    assert p.returncode == 0, p.stderr
    for gid, decision in (("G1_diff_confirm", "confirmed"),
                          ("G2_report_accept", "accept"),
                          ("G3_regression_decision", g3)):
        p = _run("gate.py", "sign", gid, "--run", run, "--decision", decision,
                 "--actor", actor, "--actor-kind", actor_kind, "--allow-nonhuman",
                 "--now", NOW, env_extra=env_extra)
        assert p.returncode == 0, p.stderr


def _case_states_init(env_dir: Path, ws: Path, run=RUN):
    env_extra = _fenv(env_dir, ws)
    p = _run("case_state.py", "init", "--run", run, "--now", NOW, env_extra=env_extra)
    assert p.returncode == 0, p.stderr


def _case_state_set(env_dir: Path, ws: Path, *args, run=RUN):
    return _run("case_state.py", "set", "--run", run, *args, "--now", NOW,
                env_extra=_fenv(env_dir, ws))


def _finish_run(env_dir: Path, ws: Path, run=RUN):
    rd = ws / "runs" / run
    (rd / "n2_diff.json").write_text('{"conflicts": []}', encoding="utf-8")
    (rd / "n5_impact.json").write_text('{"must_change": []}', encoding="utf-8")
    (rd / "evidence").mkdir(exist_ok=True)
    return rd


def _prepare_promotable(tmp_path: Path):
    env_dir, ws = _make_fake_env(tmp_path)
    _build_v0(env_dir, ws)
    _stage(env_dir, ws)
    rd = _finish_run(env_dir, ws)
    _sign_gates(env_dir, ws)
    _case_states_init(env_dir, ws)
    assert _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "未改").returncode == 0
    return env_dir, ws, rd


def _n16(env_dir: Path, ws: Path, *args, run=RUN):
    return _run("n16_promote.py", "--run", run, *args,
                env_extra=_fenv(env_dir, ws))


# ---------------------------------------------------------------- F-01


def test_f01_n1_snapshot_selftest_passes() -> None:
    """F-01：最小 fake env 上 build/stage 不再 NameError（selftest 7/7）。"""
    p = subprocess.run([sys.executable, str(KB_TOOLS / "_selftest_n1_snapshot.py")],
                       capture_output=True, text=True, env=_clean_env(), cwd=str(ROOT),
                       timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "FAIL=0" in p.stdout


# ---------------------------------------------------------------- F-02


def test_f02_entry_candidates_resolves_workspace_relative_path(tmp_path: Path) -> None:
    """F-02：manifest 的工作区相对路径必须经 K.data_path 解析（WORKSPACE 在 ENV_ROOT 外）。"""
    env_dir, ws = _make_fake_env(tmp_path)
    _build_v0(env_dir, ws)
    draft = _stage(env_dir, ws)
    manifest = json.loads(draft.read_text(encoding="utf-8"))
    dfp = manifest["doc_fingerprint"]["path"]
    # 前提：这是**工作区相对路径**，在 ENV_ROOT 下不存在（旧代码用 root_path 必然错位）
    assert not (env_dir / dfp).exists()
    assert (ws / dfp).exists()

    code = (
        "import json, sys\n"
        "sys.path.insert(0, %r)\n"
        "import n2_diff as N\n"
        "m = json.load(open(%r))\n"
        "c = N.entry_candidates(m, %r, 'from', None)\n"
        "print(json.dumps([(str(p), l) for p, l in c], ensure_ascii=False))\n"
        % (str(KB_TOOLS), str(draft), str(draft))
    )
    env = _clean_env()
    env.update(_fenv(env_dir, ws))
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=env, cwd=str(ROOT), timeout=120)
    assert p.returncode == 0, p.stderr
    cands = json.loads(p.stdout)
    main_path, main_label = cands[0]
    assert "主口径" in main_label
    assert main_path == str(ws / Path(dfp).parent / "doc_entries.jsonl")
    assert Path(main_path).is_file(), "主口径没命中工作区数据根的 doc_entries.jsonl（F-02 未修）"


# ---------------------------------------------------------------- I3 印记 / verdict


def _write_run_with_log(tmp_path: Path, log_text: str, *, name="tc_x",
                        reset="2026_0708", run=RUN) -> Path:
    rd = tmp_path / "run"
    (rd / "evidence").mkdir(parents=True, exist_ok=True)
    (rd / "case_states.json").write_text("{}", encoding="utf-8")   # 让 _find_run_dir 认 run
    bundle = rd / "bundle"
    bundle.mkdir(exist_ok=True)
    entry = {"entry_id": "0x0000#0x0004", "segment": "0x0000",
             "offset_global": "0x0004", "name": "fpga_date", "rw": "R",
             "reset": reset, "bytes": 4, "bitdef_present": True,
             "sources": [{"kind": "summary", "line": 1}], "conflict_ids": []}
    (bundle / "doc_entries.jsonl").write_text(
        json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    log = rd / "evidence" / ("20261019-180000_%s_1_run.log" % name)
    log.write_text(log_text, encoding="utf-8")
    return rd


GOOD_LOG = """\
UVM_INFO tc_x.sv(186) @ 141.913 us [N6_FPGA_DATE_PCIE] OK 0x0000+0x04 fpga_date = 0x20260708
UVM Report Summary
UVM_INFO :    7
UVM_WARNING : 0
UVM_ERROR :    0
UVM_FATAL :    0
Report counts by id
[N6_FPGA_DATE_PCIE]     1
---
"""


def test_i3_verdict_includes_imprint_three_way(tmp_path: Path) -> None:
    """I3：两套口径皆 0 + UVM 汇总 + 印记三向一致 ⇒ 才判跑通。"""
    import host.evidence as E

    rd = _write_run_with_log(tmp_path, GOOD_LOG)
    view = E.evidence_view(rd / "evidence" / "20261019-180000_tc_x_1_run.log")
    assert view["present"] is True
    imp = view["imprints"]["N6_FPGA_DATE_PCIE"]
    # 期望来自 run 的文档条目快照（不是 host 代码里硬编码）
    assert imp["expected"]["source"].endswith("doc_entries.jsonl")
    assert imp["expected"]["address"] == "0x0000+0x04"
    assert imp["expected"]["value"] == "0x20260708"
    assert imp["checks"]["address_matches_expected"] is True
    assert imp["checks"]["value_matches_expected"] is True
    assert view["verdict"]["passed"] is True, view["verdict"]


def test_i3_verdict_rejects_wrong_imprint_value(tmp_path: Path) -> None:
    """I3 反例：印记地址/值与文档条目期望不符 ⇒ 不得判跑通。"""
    import host.evidence as E

    bad = GOOD_LOG.replace("0x20260708", "0xdeadbeef")
    rd = _write_run_with_log(tmp_path, bad)
    view = E.evidence_view(rd / "evidence" / "20261019-180000_tc_x_1_run.log")
    assert view["verdict"]["passed"] is False
    assert any("印记" in r for r in view["verdict"]["reasons"]), view["verdict"]


def test_i3_verdict_rejects_missing_imprint(tmp_path: Path) -> None:
    """I3 反例：没有预期观测点印记 ⇒ 不得判跑通（哪怕两套口径都是 0）。"""
    import host.evidence as E

    rd = _write_run_with_log(tmp_path, GOOD_LOG.split("UVM_INFO tc_x")[0])
    view = E.evidence_view(rd / "evidence" / "20261019-180000_tc_x_1_run.log")
    assert view["verdict"]["passed"] is False
    assert any("观测点印记" in r for r in view["verdict"]["reasons"]), view["verdict"]


# ---------------------------------------------------------------- 多用例证据聚合


def _guard_text(case: str, md5: str, seed="1", run_id=RUN) -> str:
    return (
        "==================== run_guarded.sh 运行日志头 ====================\n"
        "case_name        : %s\n"
        "case_file        : /tmp/%s.sv\n"
        "case md5         : %s\n"
        "seed             : %s\n"
        "run_id           : %s\n"
        "mode             : full\n"
        "==================================================================\n"
        % (case, case, md5, seed, run_id)
    )


def test_evidence_aggregate_multi_case(tmp_path: Path) -> None:
    """N9/N15：多用例聚合（逐例判据的合取 + 身份四方同值 + 印记一致性）。"""
    import host.evidence as E

    rd = _write_run_with_log(tmp_path, GOOD_LOG.replace("tc_x", "tc_a"), name="tc_a")
    ev = rd / "evidence"
    (ev / "20261019-180000_tc_a_1_guard.log").write_text(
        _guard_text("tc_a", "a" * 32), encoding="utf-8")
    (ev / "20261019-180000_tc_b_1_run.log").write_text(GOOD_LOG, encoding="utf-8")
    (ev / "20261019-180000_tc_b_1_guard.log").write_text(
        _guard_text("tc_b", "b" * 32), encoding="utf-8")

    out = E.extract_run(rd, expected_md5={"tc_a": "a" * 32, "tc_b": "b" * 32})
    assert set(out["per_case"]) == {"tc_a", "tc_b"}
    assert out["totals"] == {"cases": 2, "present": 2, "passed": 2, "failed": 0}
    assert out["verdict"]["passed"] is True, out["verdict"]
    assert out["identity"]["consistent"] is True, out["identity"]
    assert out["imprint_consistent"] is True
    for case in ("tc_a", "tc_b"):
        item = out["per_case"][case]
        assert item["present"] is True
        assert item["identity"]["case"] == case
        assert item["identity"]["case_md5"] in ("a" * 32, "b" * 32)
        assert item["counts"]["single_source"] is True
        assert item["verdict"]["passed"] is True
        assert item["has_report_summary"] is True
        assert item["chosen"]["path"] == item["path"]

    # 身份四方同值断裂：审的 md5 ≠ 跑的 md5 ⇒ 总 verdict=false 且 mismatches 点名 case
    broken = E.extract_run(rd, expected_md5={"tc_a": "c" * 32})
    assert broken["verdict"]["passed"] is False
    assert broken["identity"]["consistent"] is False
    assert any("tc_a" in m and "md5" in m for m in broken["identity"]["mismatches"]), \
        broken["identity"]

    # 缺日志 ⇒ present=false + defect，不得默认 true
    missing = E.aggregate_evidence({"tc_z": tmp_path / "nope.log"})
    assert missing["per_case"]["tc_z"]["present"] is False
    assert "E-2" in missing["per_case"]["tc_z"]["defect"]
    assert missing["verdict"]["passed"] is False


# ---------------------------------------------------------------- N16：I4 / I8 / I20 / I7 / I2


def test_n16_default_dry_run_has_no_side_effect(tmp_path: Path) -> None:
    env_dir, ws, _rd = _prepare_promotable(tmp_path)
    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human")
    assert p.returncode == 0, p.stderr
    assert not (ws / "baselines/v1").exists(), "默认必须是 dry-run：不得写盘"
    assert not (ws / "baselines/INDEX.json").exists()


def test_n16_real_promote_atomic_parent_chain_and_v0_untouched(tmp_path: Path) -> None:
    env_dir, ws, _rd = _prepare_promotable(tmp_path)
    v0_manifest = ws / "baselines/v0/manifest.json"
    v0_before = v0_manifest.read_bytes()

    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human", "--promote")
    assert p.returncode == 0, p.stdout + p.stderr
    v1 = json.loads((ws / "baselines/v1/manifest.json").read_text(encoding="utf-8"))
    assert v1["baseline"] == "v1" and v1["parent"] == "v0"
    assert v1["trigger"]["by"] == G1_ACTOR
    assert v1["trigger"]["actor_kind"] == "human"
    assert v1["trigger"]["human_signed"] is True
    assert v0_manifest.read_bytes() == v0_before, "旧基线 v0 被改动（违反只增不改）"
    index = json.loads((ws / "baselines/INDEX.json").read_text(encoding="utf-8"))
    assert "v1" in index["baselines"] and index["baselines"]["v1"]["parent"] == "v0"
    for rel in ("rtl_snapshot.tar", "doc_entries.txt", "cases.md5",
                "conflicts/conflicts.json", "frozen_change/frozen_change.json",
                "evidence/index.md"):
        assert (ws / "baselines/v1" / rel).is_file(), "七件套缺件：%s" % rel
    assert not (ws / "baselines/.staging-v1").exists(), "staging 未清理"


def test_n16_i4_unconditional_even_milestone(tmp_path: Path) -> None:
    """A18：G3=milestone_only 也必须在 N16 无条件校验 I4（旧实现只在 full/subset 查）。"""
    env_dir, ws = _make_fake_env(tmp_path)
    _write_conflicts(ws, [{"id": "C1", "segment": "ALL", "category": "OFFSET",
                           "doc_line": "L1", "summary": "s", "evidence": "e",
                           "status": "open", "blocks_release": True}])
    _build_v0(env_dir, ws)
    _stage(env_dir, ws)
    _finish_run(env_dir, ws)
    _sign_gates(env_dir, ws, g3="milestone_only")
    _case_states_init(env_dir, ws)
    assert _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "未改").returncode == 0

    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human", "--promote")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "I4" in p.stderr and "blocks_release" in p.stderr
    assert not (ws / "baselines/v1").exists()


def test_n16_identity_must_come_from_g3_and_match(tmp_path: Path) -> None:
    """I20/C9：--trigger-by/--actor-kind 与 G3 签署记录不一致 ⇒ fail closed、不写盘。"""
    env_dir, ws, _rd = _prepare_promotable(tmp_path)
    p = _n16(env_dir, ws, "--trigger-by", "human:someone-else", "--actor-kind", "human")
    assert p.returncode == 3 and "G3" in p.stderr, p.stderr
    assert not (ws / "baselines/v1").exists()

    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "rehearsal")
    assert p.returncode == 3 and "actor_kind" in p.stderr, p.stderr


def test_n16_real_promote_requires_human(tmp_path: Path) -> None:
    """I8：真实晋升只允许人触发；G3 由 rehearsal 签署时 --promote 必须拒绝。"""
    env_dir, ws = _make_fake_env(tmp_path)
    _build_v0(env_dir, ws)
    _stage(env_dir, ws)
    _finish_run(env_dir, ws)
    _sign_gates(env_dir, ws, actor="host:drill", actor_kind="rehearsal")
    _case_states_init(env_dir, ws)
    assert _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "未改").returncode == 0

    p = _n16(env_dir, ws, "--trigger-by", "host:drill", "--actor-kind", "rehearsal",
             "--promote")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "human" in p.stderr
    assert not (ws / "baselines/v1").exists()
    # 同一状态 dry-run 可以预演（不写盘）
    p = _n16(env_dir, ws, "--trigger-by", "host:drill", "--actor-kind", "rehearsal")
    assert p.returncode == 0, p.stderr


def test_n16_i7_boundary_ge_limit_blocks_promotion(tmp_path: Path) -> None:
    """C5：cycles == limit 就必须拒绝晋升（旧实现用 `>` 漏掉相等）。"""
    env_dir, ws, _rd = _prepare_promotable(tmp_path)
    p = _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "未改",
                        "--rework-cycles", "3")
    assert p.returncode == 0, p.stderr
    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human", "--promote")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "I7" in p.stderr or "返工" in p.stderr
    assert not (ws / "baselines/v1").exists()


def test_n16_pending_case_blocks_promotion(tmp_path: Path) -> None:
    """I2：存在「已修订待验」⇒ 不得晋升。"""
    env_dir, ws, _rd = _prepare_promotable(tmp_path)
    p = _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "已修订待验")
    assert p.returncode == 0, p.stderr
    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "已修订待验" in p.stderr
    assert not (ws / "baselines/v1").exists()


# ---------------------------------------------------------------- N5 消费口径


def test_n5_must_change_excludes_over_budget_and_unreachable() -> None:
    """#22 相关：`must_change` 只含可执行项；over_budget/unreachable 单独成组。

    loop 侧 `must_change_cases` 由 `must_change[]` 派生 ⇒ 分组口径必须与之一致，
    否则超预算/不可达用例会被当成"必改且可跑"混进 N9 目标集。
    """
    sys.path.insert(0, str(KB_TOOLS))
    import n5_impact as N5

    must = [
        {"case": "tc_live", "reachability": "live", "feasible": "yes"},
        {"case": "tc_over", "reachability": "live", "feasible": "no",
         "infeasible_reason": "wall_est > max_wall"},
        {"case": "tc_unreach", "reachability": "unreachable",
         "reachability_basis": "no call path"},
    ]
    keep, over, unreach = N5.split_by_budget(must, 1800)
    assert [e["case"] for e in keep] == ["tc_live"]
    assert [e["case"] for e in over] == ["tc_over"]
    assert [e["case"] for e in unreach] == ["tc_unreach"]
    assert [e["case"] for e in keep + over + unreach] == ["tc_live", "tc_over", "tc_unreach"]


def test_n16_g3_defer_cannot_promote(tmp_path: Path) -> None:
    """G3=defer = 本轮不发版 ⇒ 即使 I4/I2 都过关也不得晋升（LOOP §10 表 ④同口径）。"""
    env_dir, ws = _make_fake_env(tmp_path)
    _build_v0(env_dir, ws)
    _stage(env_dir, ws)
    _finish_run(env_dir, ws)
    _sign_gates(env_dir, ws, g3="defer")
    _case_states_init(env_dir, ws)
    assert _case_state_set(env_dir, ws, "--case", "tc_x", "--state", "未改").returncode == 0

    p = _n16(env_dir, ws, "--trigger-by", G1_ACTOR, "--actor-kind", "human", "--promote")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "defer" in p.stderr or "可晋升" in p.stderr
    assert not (ws / "baselines/v1").exists()


def test_extract_run_picks_latest_round_log(tmp_path: Path) -> None:
    """N9 返工回边会在同一 run 目录留多轮日志 ⇒ 必须选**最新**一轮，不得取最旧。

    Lead 指定场景：旧日志口径一 1687、新日志 0 ⇒ 必须选新（且 expected_md5 优先级更高）。
    """
    import host.evidence as E

    rd = _write_run_with_log(tmp_path, GOOD_LOG, name="tc_a")   # 提供 run/bundle 文档快照
    ev = rd / "evidence"
    old_bad = ev / "20261019-180000_tc_a_1_run.log"
    old_bad.write_text(
        ("UVM_INFO tc_a.sv(1) @ 1 us [PCIE_REG_RD@3DW] *E @ADDR[0x84] filler\n" * 1687)
        + "UVM Report Summary\nUVM_ERROR :    0\nUVM_FATAL :    0\n",
        encoding="utf-8")
    new_good = ev / "20261019-190000_tc_a_1_run.log"
    new_good.write_text(GOOD_LOG, encoding="utf-8")
    (ev / "20261019-180000_tc_a_1_guard.log").write_text(
        _guard_text("tc_a", "a" * 32), encoding="utf-8")
    (ev / "20261019-190000_tc_a_1_guard.log").write_text(
        _guard_text("tc_a", "b" * 32), encoding="utf-8")

    out = E.extract_run(rd)
    item = out["per_case"]["tc_a"]
    assert item["chosen"]["stamp"] == "20261019-190000", item["chosen"]
    assert "最新" in item["chosen"]["reason"], item["chosen"]
    assert len(item["chosen"]["candidates"]) == 2
    assert item["counts"]["koutou1"]["value"] == 0, "取了最旧 1687 日志 ⇒ I3 判据错位"
    assert item["verdict"]["passed"] is True, item["verdict"]
    assert item["has_report_summary"] is True
    assert out["chosen"]["tc_a"]["path"] == str(new_good)

    # 身份优先于时间：审的 md5 = 旧轮 md5 ⇒ 选中旧轮（此时口径一 1687 ⇒ 明确判 false）
    out2 = E.extract_run(rd, expected_md5={"tc_a": "a" * 32})
    item2 = out2["per_case"]["tc_a"]
    assert item2["chosen"]["stamp"] == "20261019-180000", item2["chosen"]
    assert "expected_md5" in item2["chosen"]["reason"]
    assert item2["counts"]["koutou1"]["value"] == 1687
    assert item2["verdict"]["passed"] is False


# ---------------------------------------------------------------- case_state CLI / N10 pending


def test_case_state_selftest_passes() -> None:
    p = subprocess.run([sys.executable, str(KB_TOOLS / "_selftest_case_state.py")],
                       capture_output=True, text=True, env=_clean_env(), cwd=str(ROOT),
                       timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "FAIL=0" in p.stdout


def test_n10_pending_selftest_passes() -> None:
    p = subprocess.run([sys.executable, str(KB_TOOLS / "_selftest_n10_pending.py")],
                       capture_output=True, text=True, env=_clean_env(), cwd=str(ROOT),
                       timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "FAIL=0" in p.stdout
