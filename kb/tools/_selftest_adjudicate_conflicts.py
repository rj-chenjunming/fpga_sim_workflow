#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate_conflicts.py 的自测（C10-a）：**human-only 写入 + 只增不改 + 锚 + 合并**。

为什么必须有它（`doc/STATUS.md` §83.3）：冲突裁决此前**没有任何写入路径**，而 `I4` 只读
`blocks_release` ⇒ 72 条冲突永远清零不了。写入器一旦写错方向（例如允许模型自签、
允许用 `confirmed` 清零、允许覆盖旧裁决、重跑抽取丢裁决），`I4` 会变成"随便就能过"，
所以每条不变式都要有**不读源码也能判定**的断言。

用法：`python3 kb/tools/_selftest_adjudicate_conflicts.py`（退出码 0 = 全过）
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

sys.dont_write_bytecode = True

import kb_lib  # noqa: E402
import n1_conflicts  # noqa: E402

TOOL = os.path.join(_HERE, "adjudicate_conflicts.py")
PASS = 0
FAIL = 0


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("[PASS] %s" % name)
    else:
        FAIL += 1
        print("[FAIL] %s %s" % (name, detail))


def run(workdir, *args):
    env = dict(os.environ)
    env.pop("KB_NOW", None)
    env["KB_NOW"] = "2026-10-27T10:00:00+0800"
    p = subprocess.run([sys.executable, "-B", TOOL, "--outdir", workdir] + list(args),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout + p.stderr


def fixture(workdir):
    """最小 schema-valid `conflicts.json`（3 条：C1/C2/C3，全 open + 全阻断）。"""
    items = [{"id": "C%d" % i, "segment": "0x0000", "category": "NUM",
              "doc_line": "L1 vs L2", "summary": "夹具冲突 C%d" % i,
              "evidence": "夹具（自测用，不是真实文档）", "status": "open",
              "resolution": None, "resolution_actor": None, "resolution_kind": None,
              "linked_entries": [], "blocks_release": True} for i in (1, 2, 3)]
    doc = {"schema": "kb/conflicts/conflicts", "version": 1, "source_note": "fixture",
           "expected_total": 3, "conflicts": items}
    kb_lib.check(doc, "conflicts", "fixture")
    kb_lib.write_json(os.path.join(workdir, "conflicts.json"), doc)


def load_conflicts(workdir):
    return kb_lib.read_json(os.path.join(workdir, "conflicts.json"))


def main():
    work = tempfile.mkdtemp(prefix="adj-selftest-")
    try:
        fixture(work)
        human = "--actor"
        name = "human:selftest"

        # 1) human 裁决 cleared + 落 adjudication.json（带锚）
        rc, out = run(work, human, name, "--id", "C1", "--status", "ruled",
                      "--resolution", "以位定义表为准")
        ok("1 human 裁决写入 rc=0", rc == 0, out[-400:])
        adj_path = os.path.join(work, "adjudication.json")
        ok("1 adjudication.json 已生成", os.path.exists(adj_path))
        adj = kb_lib.read_json(adj_path)
        rec = adj["records"][-1]
        body = {k: v for k, v in rec.items() if k != "sha256"}
        ok("1 记录锚可复算", kb_lib.sha256_text(kb_lib.canon_json(body)) == rec["sha256"])
        ok("1 记录含裁决时刻（KB_NOW 注入）", rec["adjudicated_at"] == "2026-10-27T10:00:00+0800",
           rec["adjudicated_at"])
        c1 = {c["id"]: c for c in load_conflicts(work)["conflicts"]}["C1"]
        ok("1 C1 合并为 ruled/false/human",
           (c1["status"], c1["blocks_release"], c1["resolution_kind"]) == ("ruled", False, "human"),
           c1)

        # 2) 拒绝非 human actor（model / host / 裸名），且不写任何文件
        before = open(adj_path, encoding="utf-8").read()
        for bad_actor in ("model:gpt", "host:loop", "chenjm"):
            rc, out = run(work, human, bad_actor, "--id", "C2", "--status", "ruled",
                          "--resolution", "x")
            ok("2 拒绝 actor=%s（rc=%d）" % (bad_actor, rc), rc == 4, out[-200:])
        ok("2 被拒时不改动 adjudication.json", open(adj_path, encoding="utf-8").read() == before)

        # 3) ruled/fixed/ignored 必须给 resolution
        rc, out = run(work, human, name, "--id", "C2", "--status", "ruled")
        ok("3 缺 resolution 被拒（rc=5）", rc == 5, out[-200:])

        # 4) confirmed 不得清零（冲突确认存在 ⇒ 仍阻断）
        rc, out = run(work, human, name, "--id", "C2", "--status", "confirmed",
                      "--resolution", "确认冲突真实存在")
        c2 = {c["id"]: c for c in load_conflicts(work)["conflicts"]}["C2"]
        ok("4 confirmed 写入 rc=0", rc == 0, out[-300:])
        ok("4 confirmed 仍 blocks_release=true", c2["blocks_release"] is True, c2)

        # 5) 只增不改：同 id 改判 ⇒ 追加一条，历史保留，合并取最后一条
        rc, out = run(work, human, name, "--id", "C1", "--status", "ignored",
                      "--resolution", "改判：该冲突可忽略（自测）")
        adj = kb_lib.read_json(adj_path)
        ok("5 改判是追加（C1 两条记录）", len(adj["records"]) == 3, len(adj["records"]))
        first = adj["records"][0]
        ok("5 旧记录未被覆盖", first["status"] == "ruled" and first["resolution"] == "以位定义表为准")
        c1 = {c["id"]: c for c in load_conflicts(work)["conflicts"]}["C1"]
        ok("5 合并取最后一条（ignored）", c1["status"] == "ignored", c1["status"])
        ok("5 仍阻断数 = 2（C2 仍阻断）",
           sum(1 for c in load_conflicts(work)["conflicts"] if c["blocks_release"]) == 2)

        # 6) --list / --verify 正常
        rc, out = run(work, "--list")
        ok("6 --list rc=0 且显示仍阻断数", rc == 0 and "仍阻断发版=2" in out, out[-300:])
        rc, out = run(work, "--verify")
        ok("6 --verify rc=0", rc == 0, out[-300:])

        # 7) 锚不符 ⇒ 拒绝（verify 非 0；后续写入也被拒）
        tampered_path = os.path.join(work, "adjudication.json")
        doc = kb_lib.read_json(tampered_path)
        doc["records"][0]["resolution"] = "被人手改了但没更新锚"
        kb_lib.write_json(tampered_path, doc)
        rc, out = run(work, "--verify")
        ok("7 篡改记录 ⇒ --verify 非 0", rc != 0, out[-300:])
        rc, out = run(work, human, name, "--id", "C3", "--status", "ruled",
                      "--resolution", "x")
        ok("7 篡改记录 ⇒ 写入被拒（rc=3）", rc == 3, out[-300:])

        # 8) 未知 id ⇒ 写前拒绝（不留脏记录），文件不变
        shutil.copy(tampered_path, tampered_path + ".bak")
        os.remove(tampered_path)
        before_files = sorted(os.listdir(work))
        rc, out = run(work, human, name, "--id", "C99", "--status", "ruled",
                      "--resolution", "x")
        ok("8 未知 id 被拒（rc=6）", rc == 6, out[-300:])
        ok("8 被拒后未产生 adjudication.json", "adjudication.json" not in os.listdir(work),
           sorted(os.listdir(work)))
        ok("8 目录无新增文件", sorted(os.listdir(work)) == before_files)

        # 9) n1_conflicts 的合并函数：正常合并 + 未知 id 报错
        decisions = {"C1": {"id": "C1", "status": "ruled", "resolution": "r",
                            "resolution_actor": "human:selftest", "resolution_kind": "human",
                            "blocks_release": False}}
        merged_list, n = n1_conflicts.merge_adjudication(load_conflicts(work)["conflicts"],
                                                         decisions)
        ok("9 merge_adjudication 合并 1 条", n == 1)
        ok("9 合并后 C1 清零",
           {c["id"]: c for c in merged_list}["C1"]["blocks_release"] is False)
        try:
            n1_conflicts.merge_adjudication(merged_list, {"C99": decisions["C1"]})
            ok("9 未知 id 应报错", False)
        except ValueError as exc:
            ok("9 未知 id 报错", "C99" in str(exc), str(exc))

        # 10) 缺 conflicts.json 且未 --no-apply ⇒ 拒绝（不写到一半）
        empty = tempfile.mkdtemp(prefix="adj-selftest-empty-")
        try:
            rc, out = run(empty, human, name, "--id", "C1", "--status", "ruled",
                          "--resolution", "x")
            ok("10 缺 conflicts.json 被拒（rc=2）", rc == 2, out[-200:])
            rc, out = run(empty, human, name, "--id", "C1", "--status", "ruled",
                          "--resolution", "x", "--no-apply")
            ok("10 --no-apply 时允许（rc=0）", rc == 0, out[-200:])
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n汇总：PASS=%d FAIL=%d" % (PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
