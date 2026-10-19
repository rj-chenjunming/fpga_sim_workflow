#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F-01 自测：`n1_snapshot.py` 的 argparse 默认值不得再引用裸名 `kb_lib`。

缺陷原文（外部场景 SCN_RTL_0D04 的 scripts/kbwrap.py 头注释 + 本仓审计 F-01）：
    `n1_snapshot.py:330` 的 argparse 默认值 `default=kb_lib.kb_path("conflicts")`
    而该文件只写了 `import kb_lib as K` ⇒ 任何 `build` / `stage` 都在**解析参数阶段**
    `NameError: name 'kb_lib' is not defined`（连 `--help` 都过不去）。

本自测在**最小 fake env**（`$LOOP_ENV_ROOT` + `$LOOP_WORKSPACE`，WORKSPACE 在 ENV_ROOT 之外）
上真实跑 build/stage，不触碰权威环境、不写本仓数据根。

用法：`python3 kb/tools/_selftest_n1_snapshot.py`（退出码 0 = 全过）
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.join(HERE, "n1_snapshot.py")
RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


def make_fake_env(root):
    env = os.path.join(root, "env")
    ws = os.path.join(root, "ws")
    for d in ("RTL/SRC/imports", "RTL/RTL_COMMON", "TB", "TESTLIB", "PKG",
              "doc/reference"):
        os.makedirs(os.path.join(env, d), exist_ok=True)
    os.makedirs(os.path.join(ws, "index"), exist_ok=True)
    os.makedirs(os.path.join(ws, "conflicts"), exist_ok=True)
    open(os.path.join(env, "RTL/SRC/imports/a.v"), "w").write("module a; endmodule\n")
    open(os.path.join(env, "RTL/RTL_COMMON/b.v"), "w").write("module b; endmodule\n")
    open(os.path.join(env, "TB/t.sv"), "w").write("module t; endmodule\n")
    open(os.path.join(env, "TESTLIB/tc_x.sv"), "w").write("module tc_x; endmodule\n")
    open(os.path.join(env, "PKG/p.txt"), "w").write("pkg\n")
    open(os.path.join(env, "doc/reference/doc.md"), "w").write(
        "| 0x0004 | date | R | 0x2026_0708 | 4 | x |\n")
    regmap = {"schema": "kb/index/regmap", "version": 1, "source_doc": "doc/reference/doc.md",
              "entries": [{
                  "entry_id": "0x0000#0x0004", "segment": "0x0000",
                  "offset_global": "0x0004", "name": "fpga_date", "rw": "R",
                  "reset": "2026_0708", "bytes": 4, "bitdef_present": True,
                  "sources": [{"kind": "summary", "line": 1}], "conflict_ids": [],
                  "raw_line": "| 0x0004 | date | R | 0x2026_0708 | 4 | x |"}]}
    json.dump(regmap, open(os.path.join(ws, "index", "regmap.json"), "w"))
    json.dump({"schema": "kb/conflicts/conflicts", "version": 1, "source_note": "x",
               "expected_total": 0, "conflicts": []},
              open(os.path.join(ws, "conflicts", "conflicts.json"), "w"))
    return env, ws


def run(args, env, ws):
    e = dict(os.environ)
    e.update({"LOOP_ENV_ROOT": env, "LOOP_WORKSPACE": ws,
              "PYTHONDONTWRITEBYTECODE": "1"})
    p = subprocess.run([sys.executable, SELF] + args, capture_output=True, text=True,
                       env=e, cwd=os.path.dirname(os.path.dirname(HERE)))
    return p


root = tempfile.mkdtemp(prefix="selftest-f01-")
env, ws = make_fake_env(root)
try:
    # ---- 1 参数解析阶段不再 NameError（旧缺陷连 --help 都过不去）----
    p = run(["build", "--help"], env, ws)
    check("1 build --help 不抛 NameError（rc=0，F-01 根因面）",
          p.returncode == 0, (p.stderr or p.stdout).strip().splitlines()[-1][:80] if (p.stderr or p.stdout) else "")

    # ---- 2 源码里不再有裸名 kb_lib.（静态回归，防止再漏）----
    src = open(SELF, encoding="utf-8").read()
    bad = re.findall(r"(?<![\w.])kb_lib\.", src)
    check("2 源码无裸名 kb_lib.（只剩 import kb_lib as K）", not bad, str(bad[:3]))

    # ---- 3 最小 fake env 上真实 build ----
    p = run(["build", "--out-baseline", "v0", "--now", "2026-10-19T17:00:00+0800"], env, ws)
    manifest = os.path.join(ws, "baselines", "v0", "manifest.json")
    check("3 build rc=0 且产出 v0/manifest.json", p.returncode == 0 and os.path.isfile(manifest),
          (p.stderr or "").strip()[-120:])
    m = json.load(open(manifest)) if os.path.isfile(manifest) else {}
    check("4 v0 的 parent=null、baseline=v0", m.get("parent") is None and m.get("baseline") == "v0",
          "parent=%r baseline=%r" % (m.get("parent"), m.get("baseline")))

    # ---- 4 最小 fake env 上真实 stage（N1 摄取）----
    run_id = "RUN-20261019-170001"
    p = run(["stage", "--parent", "v0", "--run", run_id,
             "--now", "2026-10-19T17:01:00+0800"], env, ws)
    draft = os.path.join(ws, "runs", run_id, "n1_manifest_new.json")
    check("5 stage rc=0 且产出 n1_manifest_new.json", p.returncode == 0 and os.path.isfile(draft),
          (p.stderr or "").strip()[-120:])
    d = json.load(open(draft)) if os.path.isfile(draft) else {}
    check("6 stage 草案 parent=v0（--parent 必需项生效）", d.get("parent") == "v0",
          "parent=%r" % d.get("parent"))
    bundle = os.path.join(ws, "runs", run_id, "bundle")
    required = ("rtl_snapshot.tar", "rtl_files.md5", "allfiles.md5", "doc_entries.txt",
                "doc_entries.jsonl", "cases.md5", "conflicts/conflicts.json", "manifest.json")
    missing = [r for r in required if not os.path.isfile(os.path.join(bundle, r))]
    check("7 stage 七件套可复算件齐全", not missing, "缺=%r" % missing)
finally:
    shutil.rmtree(root, ignore_errors=True)

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
