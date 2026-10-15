#!/usr/bin/env python3
"""闸门 schema 自测：F-SCHEMA-01（一词之差）与 F-SCHEMA-02（死文件 / 名字对不上）。

缺陷原文（`doc/spec/evidence/loop_rehearsal/verify/V9_fixes_reverify.md`，verifier 独立复现）：
> `gate_state.schema.json` 要求 `anchor.algo = 'sha256-of-canonical-record-without-anchor'`，
> 而 `gate.py` 实写 `'...state-without-anchor'` —— **一词之差**，导致 `check(obj,"gate_state")`
> 对当前脚本写的**任何** gates.json 都失败。
> 且 `check(obj,"gate-state")`（任务书的写法）抛 `FileNotFoundError`；
> 全仓**没有任何脚本调用**该 schema ⇒ 它是**死文件**。

本测试把这些固定下来：
1. `-`/`_` 两种拼法都能解析到同一个 schema（名字不该决定能不能校验）；
2. schema 里的 `anchor.algo` const 与 `kb_lib._ANCHOR_ALGO` **同源**（漂移即失败）；
3. `gate_init` / `gate_set` 产出的状态过校验；
4. **写路径真的会拒**：把 algo 常量改错一个词，`gate_set` 必须抛 SchemaError 且**不落盘**
   —— 这一条是"schema 不是死文件"的可执行证据；
5. 归档的 legacy `RUN-20261015-120626/gates.json` 仍可校验（只读兼容不得被收紧破坏）。

用法：`python3 kb/tools/_selftest_gate_schema.py`（退出码 0 = 全过）
"""
import hashlib
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True          # kb/tools 是冻结目录：不许写 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ARCHIVE = os.path.join(ROOT, "kb", "runs", "RUN-20261015-120626", "gates.json")
TMP_RUN = "RUN-19990101-000000"
TMP_DIR = os.path.join(ROOT, "kb", "runs", TMP_RUN)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


# ---- 1 名字归一（F-SCHEMA-02）----
ok_dash = ok_us = False
try:
    a = K.load_schema("gate-state")
    ok_dash = True
except Exception as exc:
    a = {"err": "%s: %s" % (type(exc).__name__, exc)}
try:
    b = K.load_schema("gate_state")
    ok_us = True
except Exception as exc:
    b = {"err": "%s: %s" % (type(exc).__name__, exc)}
check("1 check 名 'gate-state' 可解析", ok_dash, str(a.get("err", ""))[:60])
check("2 check 名 'gate_state' 可解析", ok_us, str(b.get("err", ""))[:60])
check("3 两种拼法解析到同一个 schema", ok_dash and ok_us and a == b, "")

# ---- 2 const 与代码同源（F-SCHEMA-01 的根因面）----
schema_algo = ((a.get("properties") or {}).get("anchor") or {}).get("properties", {}).get("algo", {}).get("const")
check("4 schema 的 anchor.algo const 与 kb_lib._ANCHOR_ALGO 同源",
      schema_algo == K._ANCHOR_ALGO, "schema=%r code=%r" % (schema_algo, K._ANCHOR_ALGO))

# ---- 3 写路径产出的状态过校验 ----
shutil.rmtree(TMP_DIR, ignore_errors=True)
K.set_now("1999-01-01T00:00:00")
try:
    K.gate_init(TMP_RUN, "v0", "kb/runs/%s/n1_manifest_new.json" % TMP_RUN)
    st = K.gate_set(TMP_RUN, "G1_diff_confirm", "confirmed", "human:selftest", "human")
    K.check(st, "gate_state")
    check("5 gate_init + gate_set 的产出过 gate_state.schema.json", True, "")
    check("6 锚算法字段 == _ANCHOR_ALGO",
          st.get("anchor", {}).get("algo") == K._ANCHOR_ALGO, str(st.get("anchor")))
except Exception as exc:
    check("5 gate_init + gate_set 的产出过 gate_state.schema.json", False, "%s: %s" % (type(exc).__name__, exc))

# ---- 4 写路径**真的会拒**（证明 schema 不是死文件）----
ledger = os.path.join(TMP_DIR, "gates.json")
before = hashlib.md5(open(ledger, "rb").read()).hexdigest()
real_algo = K._ANCHOR_ALGO
K._ANCHOR_ALGO = "sha256-of-canonical-record-without-anchor"      # 就是当初那个错词
try:
    K.gate_set(TMP_RUN, "G2_report_accept", "accept", "human:selftest", "human")
    rejected = False
    how = "没有抛异常"
except K.SchemaError as exc:
    rejected = True
    how = str(exc)[:80]
except Exception as exc:
    rejected = False
    how = "%s: %s" % (type(exc).__name__, exc)
finally:
    K._ANCHOR_ALGO = real_algo

check("7 algo 常量写错一词 ⇒ 写路径抛 SchemaError", rejected, how)
after = hashlib.md5(open(ledger, "rb").read()).hexdigest()
check("8 被拒时账本一个字节都没动（check 在 write_json 之前）", before == after,
      "before=%s after=%s" % (before[:12], after[:12]))
st2 = K.read_json(ledger)
check("9 被拒后 G2 仍是 pending（无半签）",
      st2["gates"]["G2_report_accept"]["human_signed"] is False
      and st2["gates"]["G2_report_accept"]["decision"] == "pending", "")

shutil.rmtree(TMP_DIR, ignore_errors=True)

# ---- 5 归档 legacy 状态仍可校验（只读兼容）----
if not os.path.isfile(ARCHIVE):
    check("10 归档 gates.json 仍过校验", False, "跳过：%s 不存在" % ARCHIVE)
else:
    arc = json.load(open(ARCHIVE, encoding="utf-8"))
    try:
        K.check(arc, "gate-state")
        check("10 归档 gates.json 仍过校验（只用读，不得收紧破坏）", True,
              "anchor=%s" % ("有" if arc.get("anchor") else "无(legacy)"))
    except Exception as exc:
        check("10 归档 gates.json 仍过校验（只用读，不得收紧破坏）", False, str(exc)[:120])

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
