#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n10_pending 自测（单一写者 / D1—D20 零改写 / expected_total 不变 / 幂等 / 原子写）。

背景：审计 A9 —— N10 分类 2/3 只留在 execution state，`conflicts/pending.json` 从未落盘；
Lead 裁决（2026-10-19）用**加法扩展** `n10_items`，D1—D20 的 items/expected_total 语义不变。

用法：`python3 kb/tools/_selftest_n10_pending.py`（退出码 0 = 全过；只写 tmp）
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.join(HERE, "n10_pending.py")
RESULTS = []
TMP = tempfile.mkdtemp(prefix="selftest-n10-")
PENDING = os.path.join(TMP, "pending.json")
RUN = "RUN-20261019-180000"


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


def run(args, stdin_text=None):
    p = subprocess.run([sys.executable, SELF] + args, input=stdin_text,
                       capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    return p


def write_base():
    doc = {
        "schema": "kb/conflicts/pending", "version": 1,
        "source_note": "doc/_notes/06_iface_doc_regmap.md", "expected_total": 2,
        "items": [
            {"id": "D1", "kind": "位定义缺失", "doc_line": "L724", "question": "q1",
             "status": "open", "owner": "doc-owner"},
            {"id": "D2", "kind": "位定义缺失", "doc_line": "L1413", "question": "q2",
             "status": "open", "owner": "doc-owner"},
        ],
    }
    with open(PENDING, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(PENDING, 0o644)
    return doc


def load():
    with open(PENDING, encoding="utf-8") as f:
        return json.load(f)


try:
    base = write_base()
    base_bytes = open(PENDING, "rb").read()
    items = [
        {"bucket_id": "PCIE_REG_RD@3DW|0x80xx", "case": "tc_pcie_rw_02",
         "classification": "本轮引入", "address_range": "0x8000-0x80ff", "count": 7,
         "basis": "N2 修订点命中", "evidence_path": "runs/%s/evidence/x_run.log" % RUN},
        {"bucket_id": "I2C_WR|0x01xx", "case": "tc_cpu_i2c_03",
         "classification": "待裁决", "count": 2, "basis": "需人裁决"},
    ]
    items_file = os.path.join(TMP, "items.json")
    with open(items_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)

    p = run(["--run", RUN, "--pending", PENDING, "--items", items_file,
             "--now", "2026-10-19T18:00:00+0800"])
    doc = load()
    check("1 追加两项 rc=0", p.returncode == 0, (p.stderr or "").strip()[-120:])
    check("2 n10_items==2", len(doc.get("n10_items") or []) == 2, str(len(doc.get("n10_items") or [])))
    check("3 D1—D20 items 零改写（逐字节等于原 items）",
          doc["items"] == base["items"], "items=%r" % doc["items"])
    check("4 expected_total 不变（仍=2，语义=文档条数）", doc.get("expected_total") == 2,
          str(doc.get("expected_total")))
    ids = [x["id"] for x in doc["n10_items"]]
    check("5 id 形状 N10-<run>-<bucket>", all(i.startswith("N10-%s-" % RUN) for i in ids), str(ids))
    backups = [n for n in os.listdir(TMP) if n.startswith("pending.json.bak-")]
    check("6 写前生成备份 pending.json.bak-<ts>", len(backups) == 1, str(backups))
    check("7 备份内容 == 写前内容（可回放）",
          open(os.path.join(TMP, backups[0]), "rb").read() == base_bytes, "")

    # 整文件过 conflicts schema（Lead 已加 n10_items 分支）
    sys.path.insert(0, HERE)
    sys.dont_write_bytecode = True
    import kb_lib as K  # noqa: E402
    try:
        K.check(doc, "conflicts", what="pending.json")
        ok_schema = True
        err = ""
    except Exception as exc:  # noqa: BLE001
        ok_schema = False
        err = str(exc)[:160]
    check("8 写后整文件过 conflicts schema", ok_schema, err)

    # ---- 幂等：重复提交 rc=0 且不写盘 ----
    stamp_before = os.path.getmtime(PENDING)
    p = run(["--run", RUN, "--pending", PENDING, "--items", items_file,
             "--now", "2026-10-19T18:05:00+0800"])
    doc2 = load()
    check("9 重复 append 幂等（rc=0，n10_items 仍 2）",
          p.returncode == 0 and len(doc2.get("n10_items") or []) == 2,
          "rc=%s n=%d" % (p.returncode, len(doc2.get("n10_items") or [])))
    backups2 = [n for n in os.listdir(TMP) if n.startswith("pending.json.bak-")]
    check("10 幂等路径不产生新备份（未写盘）", len(backups2) == len(backups),
          "%d -> %d" % (len(backups), len(backups2)))

    # ---- 非法输入拒绝且不写盘 ----
    bad = os.path.join(TMP, "bad.json")
    with open(bad, "w", encoding="utf-8") as f:
        json.dump([{"bucket_id": "b", "case": "tc_x", "classification": "乱写"}], f)
    before = open(PENDING, "rb").read()
    p = run(["--run", RUN, "--pending", PENDING, "--items", bad])
    check("11 非法 classification ⇒ rc=3", p.returncode == 3, "rc=%s" % p.returncode)
    check("12 被拒时 pending.json 一字节未动", open(PENDING, "rb").read() == before, "")

    # ---- 既有文件损坏 ⇒ rc=4 ----
    with open(PENDING, "w", encoding="utf-8") as f:
        f.write("{broken")
    p = run(["--run", RUN, "--pending", PENDING, "--items", items_file])
    check("13 既有 pending.json 损坏 ⇒ rc=4", p.returncode == 4, "rc=%s" % p.returncode)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
