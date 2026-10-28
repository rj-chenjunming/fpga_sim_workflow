"""闸门签署绑产物指纹 `stateHash`（SPEC-REV-15）：先失败用例。

约束：不写权威数据根；每次用 tmp 造最小 ENV/WORKSPACE；时间经 `--now` 注入。
契约：签后材料变动 ⇒ `require-signed` 必须失败（`STATE_HASH_MISMATCH`）；
排除项（agent_calls/agent_controls/decisions/view.json/gates.*）不影响判定；
旧格式（无 state_hash）按 legacy 告警放行；材料不可读 ⇒ 显式失败。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KB_TOOLS = ROOT / "kb" / "tools"
NOW = "2026-10-28T15:00:00+0800"
RUN = "RUN-20261028-150000"
G1 = "G1_diff_confirm"
ACTOR = "human:lead"


def _env(tmp_path: Path) -> dict[str, str]:
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
    env = dict(os.environ)
    for key in ("KB_NOW", "LOOP_NOW", "LOOP_ENV_ROOT", "LOOP_WORKSPACE", "PYTHONPATH"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["LOOP_ENV_ROOT"] = str(env_dir)
    env["LOOP_WORKSPACE"] = str(ws)
    env["KB_NOW"] = NOW
    return env


def _run(env: dict, script: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KB_TOOLS / script), *map(str, args)],
                          capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=180)


def _material_files(ws: Path) -> None:
    rd = ws / "runs" / RUN
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "n1_manifest_new.json").write_text('{"files": []}\n', encoding="utf-8")
    (rd / "n2_diff.json").write_text('{"diffs": []}\n', encoding="utf-8")
    (rd / "n3_digest.md").write_text("# 摘要\n", encoding="utf-8")
    (rd / "evidence").mkdir()
    (rd / "evidence" / "a.log").write_text("log-a\n", encoding="utf-8")


def _signed_run(tmp_path: Path) -> tuple[dict, Path]:
    env = _env(tmp_path)
    ws = Path(env["LOOP_WORKSPACE"])
    _material_files(ws)
    r = _run(env, "gate.py", "init", "--run", RUN)
    assert r.returncode == 0, r.stderr
    r = _run(env, "gate.py", "sign", G1, "--run", RUN, "--decision", "confirmed",
             "--actor", ACTOR, "--actor-kind", "human", "--note", "范围认可")
    assert r.returncode == 0, r.stderr
    return env, ws / "runs" / RUN


def _require(env: dict) -> subprocess.CompletedProcess:
    return _run(env, "gate.py", "require-signed", "--run", RUN, "--gate", G1)


def _manifest(env: dict) -> list[dict]:
    """直接问 kb_lib 要材料集（不自己 walk：口径唯一，红线 8）。"""
    code = ("import json,sys;sys.path.insert(0,%r);import kb_lib as K;"
            "print(json.dumps(K.gate_material_manifest(%r), ensure_ascii=False))"
            % (str(KB_TOOLS), RUN))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(ROOT), env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ---------------------------------------------------------------- 绿灯基线

def test_t1_signed_and_unchanged_passes(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    st = json.loads((rd / "gates.json").read_text(encoding="utf-8"))
    assert st["gates"][G1]["state_hash"]["algo"] == "sha256-of-materials+gate-summary"
    assert len(st["gates"][G1]["state_hash"]["materials"]) >= 4
    r = _require(env)
    assert r.returncode == 0, r.stderr + r.stdout


# ---------------------------------------------------------------- 材料变动必须失败

def test_t2_changed_material_fails(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    (rd / "n2_diff.json").write_text('{"diffs": [{"id": "篡改"}]}\n', encoding="utf-8")
    r = _require(env)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "STATE_HASH_MISMATCH" in r.stderr
    assert "n2_diff.json" in r.stderr


def test_t3_added_material_fails(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    (rd / "n5_impact.json").write_text('{"impact": []}\n', encoding="utf-8")
    r = _require(env)
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert "STATE_HASH_MISMATCH" in r.stderr
    assert "added" in r.stderr and "n5_impact.json" in r.stderr


def test_t4_removed_material_fails(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    (rd / "evidence" / "a.log").unlink()
    r = _require(env)
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert "removed" in r.stderr and "evidence/a.log" in r.stderr


# ---------------------------------------------------------------- 排除项不影响判定

def test_t5_volatile_dirs_are_excluded(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    (rd / "agent_calls").mkdir(exist_ok=True)
    (rd / "agent_calls" / "N6_1.json").write_text("{}\n", encoding="utf-8")
    (rd / "agent_controls").mkdir(exist_ok=True)
    (rd / "agent_controls" / "c.jsonl").write_text("{}\n", encoding="utf-8")
    (rd / "decisions").mkdir(exist_ok=True)
    (rd / "decisions" / f"{G1}.json").write_text("{}\n", encoding="utf-8")
    (rd / "view.json").write_text("{}\n", encoding="utf-8")
    r = _require(env)
    assert r.returncode == 0, r.stderr + r.stdout


# ---------------------------------------------------------------- legacy 与不可读

def test_t6_legacy_without_state_hash_warns_but_passes(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    code = (
        "import json,sys;sys.path.insert(0,%r);import kb_lib as K;"
        "p=K.run_dir(%r)+'/gates.json';st=K.read_json(p);"
        "st['gates'][%r].pop('state_hash',None);K.write_json(p,st);K.gate_write_anchor(%r)"
    ) % (str(KB_TOOLS), RUN, G1, RUN)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       cwd=str(ROOT), env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    r = _require(env)
    assert r.returncode == 0, r.stderr
    assert "legacy" in (r.stdout + r.stderr)


def test_t7_unreadable_material_fails_explicitly(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    if os.geteuid() == 0:  # root 无视权限位，跳过
        pytest.skip("root 下无法构造不可读文件")
    target = rd / "n2_diff.json"
    target.chmod(0o000)
    try:
        r = _require(env)
    finally:
        target.chmod(0o644)
    assert r.returncode != 0, (r.returncode, r.stdout)
    assert "STATE_HASH" in (r.stderr + r.stdout) or "不可读" in r.stderr


# ---------------------------------------------------------------- 回归：锚仍生效

def test_t8_anchor_tamper_still_rejected(tmp_path: Path) -> None:
    env, rd = _signed_run(tmp_path)
    p = rd / "gates.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st["gates"][G1]["note"] = "外部偷偷改"
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    r = _require(env)
    assert r.returncode == 3, (r.returncode, r.stderr)
    assert "防篡改锚" in r.stderr or "被外部修改" in r.stderr

# ---------------------------------------------------------------- 执行期暂存 vs 业务材料（S5 C2a）

def test_t9_agent_workspaces_are_excluded_from_gate_materials(tmp_path: Path) -> None:
    """`agent_workspaces/**`（每 attempt 的隔离工作区）**不进**闸门材料集。

    为什么必须排除：工作区是执行期暂存（work 副本 / dsh-home / candidate / input 材料副本），
    签署之后会合法增长；不排除就会让签名后的正常读写把 `stateHash` 判成失配（假 red），
    也会让 C2 真机取证污染闸门材料集。判据两条（不读实现也应成立）：
    ① `gate_material_manifest()` 里不出现该路径（不是"恰好没变"）；
    ② 签署后往工作区写文件，`require-signed` 仍然通过。
    """
    env, rd = _signed_run(tmp_path)
    attempt = rd / "agent_workspaces" / "N3" / "attempt-000001"
    (attempt / "work").mkdir(parents=True)
    (attempt / "work" / "x.sv").write_text("module x; endmodule\n", encoding="utf-8")
    (attempt / "dsh-home").mkdir()
    (attempt / "dsh-home" / "session.jsonl").write_text("{}\n", encoding="utf-8")
    (attempt / "input").mkdir()
    (attempt / "input" / "n2_diff.json").write_text('{"diffs": []}\n', encoding="utf-8")
    paths = [item["path"] for item in _manifest(env)]
    assert not any(path.startswith("agent_workspaces/") for path in paths), paths
    signed = json.loads((rd / "gates.json").read_text(encoding="utf-8"))
    assert not any(item["path"].startswith("agent_workspaces/")
                   for item in signed["gates"][G1]["state_hash"]["materials"])
    r = _require(env)
    assert r.returncode == 0, r.stderr + r.stdout


def test_t10_business_materials_under_sandbox_stay_in_the_manifest(tmp_path: Path) -> None:
    """排除项只排除**执行期暂存**：导入后的业务材料（`sandbox/**`）仍必须在材料集里。

    反向抽检：如果实现把排除做大了（比如按名字前缀或整类目录排除），这条会红。
    """
    env, rd = _signed_run(tmp_path)
    target = rd / "sandbox" / "TESTLIB" / "x.sv"
    target.parent.mkdir(parents=True)
    target.write_text("module x; endmodule\n", encoding="utf-8")
    paths = [item["path"] for item in _manifest(env)]
    assert "sandbox/TESTLIB/x.sv" in paths, paths
    r = _require(env)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "STATE_HASH_MISMATCH" in r.stderr
    assert "sandbox/TESTLIB/x.sv" in r.stderr
