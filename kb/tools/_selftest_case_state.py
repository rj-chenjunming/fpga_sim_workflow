#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""case_state 台账自测（I2 四态 / I3 跑通门槛 / I7 边界 / check 机器出口 / 人签覆写）。

固定下来的契约
    * 四态字面量 = schema enum（漂移即失败）；
    * `set --state 已验证通过` 是**合取门槛**：卡点B/C/D + 两套口径 + 观测点三向一致，
      缺一条就 rc=3 **且不写盘**（模型/脚本不能自封跑通）；
    * `check` 是唯一判定出口：待验 ⇒ rc=3；`n6_n8_cycles >= limit` ⇒ rc=3（边界统一 `>=`）；
    * `set --rework-cycles` 允许记录 `==limit`（那是升级 N13 的状态），但拒绝 `>limit`（不写盘）；
    * `override`（SPEC-REV-20 §4/§5）拒绝矩阵 1/2/3/4/5/7/8 全在写盘前判 ⇒ rc≠0 且台账 md5 不变；
      合法动作**只追加** `overrides[]` 记录（含可复算 `record_sha256`），批量全有或全无；
      `--verify` 逐条复算 `record_sha256` 与 `source_md5`，不符/无法复核 ⇒ rc=4 且不写盘。

用法：`python3 kb/tools/_selftest_case_state.py`（退出码 0 = 全过；只写 tmp 文件）
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib as K  # noqa: E402
import case_state as CS  # noqa: E402

RESULTS = []
TMP = tempfile.mkdtemp(prefix="selftest-case-state-")
STATE = os.path.join(TMP, "case_states.json")
RUN = "RUN-19990101-000000"


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("[%s] %s %s" % ("PASS" if cond else "FAIL", name, ("(%s)" % detail) if detail else ""))


def call(*argv):
    try:
        return CS.main(list(argv))
    except SystemExit as exc:      # argparse 用法错误也要转成 rc，而不是终止自测
        return int(exc.code or 0)


def read_state():
    return K.read_json(STATE) if os.path.isfile(STATE) else None


try:
    # ---- 1 四态字面量与 schema 同源 ----
    schema = K.load_schema("case_states")
    enum = schema["properties"]["cases"]["items"]["properties"]["state"]["enum"]
    check("1 STATES 与 case_states.schema.json 的 enum 逐值一致",
          list(CS.STATES) == list(enum), str(enum))

    rc = call("--now", "2026-10-19T18:00:00+0800", "init", "--run", RUN,
              "--state-file", STATE)
    check("2 init rc=0 且台账落盘", rc == 0 and os.path.isfile(STATE), "rc=%s" % rc)
    st = read_state()
    check("3 初始 rework_cycles={n6_n8_cycles:0,limit:3}",
          (st or {}).get("rework_cycles") == {"n6_n8_cycles": 0, "limit": 3},
          str((st or {}).get("rework_cycles")))
    rc = call("init", "--run", RUN, "--state-file", STATE)
    check("4 重复 init 无 --force ⇒ rc=3（台账只增不改）", rc == 3, "rc=%s" % rc)

    # ---- 2 I3 合取门槛 ----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过")
    check("5 缺全部卡点证据 ⇒ 已验证通过被拒 rc=3", rc == 3, "rc=%s" % rc)
    st = read_state()
    check("6 被拒后台账未写盘（找不到 tc_a）",
          st is not None and not any(c.get("case") == "tc_a" for c in st.get("cases", [])), "")
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--compile-rc", "0", "--static-check", "pass",
              "--run-md5", "a" * 32, "--md5-after", "a" * 32,
              "--script-egrep", "0", "--uvm-error", "0", "--uvm-summary-present",
              "--obs-expected", "1", "--obs-observed", "1")
    check("7 卡点B/C/D+两口径+观测点齐全 ⇒ 已验证通过 rc=0", rc == 0, "rc=%s" % rc)

    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("8 check 无待验、返工未到上限 ⇒ rc=0", rc == 0, "rc=%s" % rc)

    # ---- 3 待验阻断（I2）----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_b",
              "--state", "已修订待验")
    check("9 写入已修订待验 rc=0", rc == 0, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--for-promotion", "--json")
    info = {}
    check("10 有待验 ⇒ N16 前置 check rc=3", rc == 3, "rc=%s" % rc)
    # 机器出口：JSON 里必须点名待验用例
    print("     check --json（待验态）：", json.dumps(
        {"ok": False, "note": "rc=%s" % rc}, ensure_ascii=False))

    # ---- 4 I7 边界统一 >= ----
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_b",
              "--state", "已验证通过", "--compile-rc", "0", "--static-check", "pass",
              "--run-md5", "b" * 32, "--md5-after", "b" * 32,
              "--script-egrep", "0", "--uvm-error", "0", "--uvm-summary-present",
              "--obs-expected", "2", "--obs-observed", "2")
    check("11 tc_b 补齐证据后 已验证通过 rc=0（无待验）", rc == 0, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("12 无待验 ⇒ check rc=0", rc == 0, "rc=%s" % rc)

    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--rework-cycles", "3")
    st = read_state()
    check("13 记录 n6_n8_cycles==limit(3) 允许（升级 N13 的状态要可记录）",
          rc == 0 and st["rework_cycles"]["n6_n8_cycles"] == 3, "rc=%s" % rc)
    rc = call("check", "--run", RUN, "--state-file", STATE, "--for-promotion", "--json")
    check("14 cycles>=limit ⇒ check rc=3（边界统一 >=，审计 C5）", rc == 3, "rc=%s" % rc)
    rc = call("set", "--run", RUN, "--state-file", STATE, "--case", "tc_a",
              "--state", "已验证通过", "--rework-cycles", "4")
    st = read_state()
    check("15 cycles>limit ⇒ set rc=3 且台账保持 3（不偷偷放宽预算）",
          rc == 3 and st["rework_cycles"]["n6_n8_cycles"] == 3, "rc=%s" % rc)

    # ================= 6 人签覆写 override / --verify（SPEC-REV-20 §3.1/§4/§5） =========
    # 冻结目录变更：`kb/schema/case_states.schema.json` 条目属性新增 `overrides`；
    # `case_state.py` 新增 `override` 子命令（只读同目录 `n10_cases.json`，不解析 n10_reconcile.md）。
    item_props = schema["properties"]["cases"]["items"]["properties"]
    ov_schema = item_props.get("overrides") or {}
    ov_props = ((ov_schema.get("items") or {}).get("properties") or {})
    check("17 schema 条目属性新增 overrides（array；action=[pass,revoke]；actor_kind=[human]）",
          ov_schema.get("type") == "array"
          and ov_props.get("action", {}).get("enum") == ["pass", "revoke"]
          and ov_props.get("actor_kind", {}).get("enum") == ["human"],
          str(sorted(ov_props)))

    OVR_DIR = os.path.join(TMP, "ovr")
    OVR = os.path.join(OVR_DIR, "case_states.json")
    N10 = os.path.join(OVR_DIR, "n10_cases.json")
    NOW = "2026-11-02T11:00:00+0800"
    ACTOR = "human:chenjunming"
    PASS_ST, PEND_ST = "已验证通过", "已修订待验"

    # 机器原因唯一来源：台账同目录的 n10_cases.json（S2 由 Host 落盘；这里是夹具）
    N10_DOC = {
        "schema": "loop/n10_cases",
        "run_id": RUN,
        "created_at": "2026-11-02T10:00:00+0800",
        "criterion": "聚合判据 = 各用例 I3 判据的合取（含印记三向一致）",
        "cases": {
            "tc_r1": {"case": "tc_r1", "passed": False,
                      "criterion": "PASS ⟺ 两套口径皆 0 ∧ 印记三向一致",
                      "reasons": ["印记 N6_tc_r1 三向不一致：['value_matches_expected']"],
                      "counts": {"koutou1": {"value": 0}},
                      "imprints": {"N6_tc_r1": {"consistent": False}},
                      "evidence": {"path": "evidence/x_tc_r1_run.log", "md5": "a" * 32,
                                   "bytes": 123}},
            "tc_r2": {"case": "tc_r2", "passed": False, "reasons": ["口径一 egrep=2"],
                      "counts": {}, "imprints": {}},
            "tc_r3": {"case": "tc_r3", "passed": False, "reasons": ["UVM Report Summary 缺失"]},
            "tc_pass": {"case": "tc_pass", "passed": False, "reasons": ["印记三向不一致"]},
            "tc_ok": {"case": "tc_ok", "passed": True, "reasons": []},
            "tc_noreason": {"case": "tc_noreason", "passed": False, "reasons": []},
        },
    }

    def read_p(p):
        return K.read_json(p) if os.path.isfile(p) else None

    def md5_p(p):
        return K.md5_file(p) if os.path.isfile(p) else None

    def entries(p=None):
        doc = read_p(p or OVR) or {}
        return {c.get("case"): c for c in (doc.get("cases") or [])}

    def entry_of(doc, case):
        for c in (doc.get("cases") or []):
            if c.get("case") == case:
                return c
        return None

    def overr(*argv):
        return call("override", "--run", RUN, "--state-file", OVR, "--now", NOW, *argv)

    def check_json(*argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc_ = call(*argv)
        txt = buf.getvalue().strip()
        return rc_, (json.loads(txt) if txt else {})

    def reject(*argv):
        """一次应被拒绝的调用：返回 (rc, 台账 md5 是否一字节不动)。"""
        before = md5_p(OVR)
        rc_ = overr(*argv)
        return rc_, md5_p(OVR) == before

    call("init", "--run", RUN, "--state-file", OVR)
    for c in ("tc_r1", "tc_r2", "tc_r3", "tc_non10", "tc_ok", "tc_noreason"):
        call("set", "--run", RUN, "--state-file", OVR, "--case", c, "--state", PEND_ST)
    call("set", "--run", RUN, "--state-file", OVR, "--case", "tc_weird", "--state", "未改")
    call("set", "--run", RUN, "--state-file", OVR, "--case", "tc_pass", "--state", PASS_ST,
         "--compile-rc", "0", "--static-check", "pass", "--run-md5", "c" * 32,
         "--md5-after", "c" * 32, "--script-egrep", "0", "--uvm-error", "0",
         "--uvm-summary-present", "--obs-expected", "5", "--obs-observed", "5")
    K.write_json(N10, N10_DOC)
    N10_MD5 = K.md5_file(N10)

    # ---- §4 拒绝矩阵 1/2/3/4/5/7：全部在写盘前 ⇒ rc=3 且台账一字节不动 ----
    for bad in ("model:gpt-5", "host:kb", "rehearsal:drill", "chenjunming", "",
                "human:", "human:   "):
        rc, same = reject("--case", "tc_r1", "--actor", bad, "--reason", "想签")
        check("18 §4-1 --actor %r 被拒 rc=3 且台账一字节不动" % bad,
              rc == 3 and same, "rc=%s same=%s" % (rc, same))
    for bad in ("", "   ", "\t\n"):
        rc, same = reject("--case", "tc_r1", "--actor", ACTOR, "--reason", bad)
        check("19 §4-2 reason=%r 被拒 rc=3 且台账一字节不动" % bad,
              rc == 3 and same, "rc=%s same=%s" % (rc, same))
    rc, same = reject("--case", "tc_absent", "--actor", ACTOR, "--reason", "理由")
    check("20 §4-3 用例不在台账 ⇒ rc=3 且台账一字节不动", rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_weird", "--actor", ACTOR, "--reason", "理由")
    check("21 §4-4 当前态不是「%s」（pass）⇒ rc=3 且台账不动" % PEND_ST,
          rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_r1", "--actor", ACTOR, "--reason", "理由", "--revoke")
    check("22 §4-4 当前态不是「%s」（revoke）⇒ rc=3 且台账不动" % PASS_ST,
          rc == 3 and same, "rc=%s" % rc)
    # §4-4 撤销边界（2026-11-02 裁定）：revoke 只撤回「我自己刚签的覆写」；
    # 机器途径/正常流程写入的 `已验证通过` 不得被 revoke 降级成待验（O-1/O-3 精神）。
    rc, same = reject("--case", "tc_pass", "--actor", ACTOR, "--reason", "撤销机器通过",
                      "--revoke")
    check("22b §4-4 当前态是「%s」但最近一条覆写记录不是 pass（机器途径）⇒ revoke rc=3"
          " 且台账不动" % PASS_ST, rc == 3 and same, "rc=%s same=%s" % (rc, same))
    os.rename(N10, N10 + ".bak")
    rc, same = reject("--case", "tc_r1", "--actor", ACTOR, "--reason", "理由")
    os.rename(N10 + ".bak", N10)
    check("23 §4-5 n10_cases.json 缺失 ⇒ rc=3 且台账不动（不许盲签）",
          rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_non10", "--actor", ACTOR, "--reason", "理由")
    check("24 §4-5 用例不在 n10_cases.json ⇒ rc=3 且台账不动", rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_ok", "--actor", ACTOR, "--reason", "理由")
    check("25 §4-5 机器判 passed=true ⇒ rc=3 且台账不动（机器已放过，不许盲签）",
          rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_noreason", "--actor", ACTOR, "--reason", "理由")
    check("26 §4-5 机器 reasons 为空 ⇒ rc=3 且台账不动（原因必须可读）",
          rc == 3 and same, "rc=%s" % rc)
    rc, same = reject("--case", "tc_r1", "--case", "tc_r2", "--case", "tc_ok",
                      "--actor", ACTOR, "--reason", "批量签")
    e = entries()
    check("27 §4-7 批量任一不满足 ⇒ 整批拒绝 rc=3、台账不动、两例都没写",
          rc == 3 and same
          and not (e["tc_r1"].get("overrides") or [])
          and not (e["tc_r2"].get("overrides") or []), "rc=%s" % rc)
    m0 = md5_p(OVR)
    rc = overr("--case", "tc_r1", "--case", "tc_r1", "--actor", ACTOR, "--reason", "重复")
    check("28 同批重复 --case ⇒ rc=2（请求形状错）且台账不动",
          rc == 2 and md5_p(OVR) == m0, "rc=%s" % rc)

    # ---- 合法单签（pass）：只追加、锚可复算、机器快照原样搬运 ----
    rc = overr("--case", "tc_r1", "--actor", ACTOR,
               "--reason", "期望值来自旧文档条目；实测与本变预期一致，属期望过期")
    st_o = read_p(OVR) or {}
    e = {c.get("case"): c for c in (st_o.get("cases") or [])}
    ovs = e["tc_r1"].get("overrides") or []
    rec = ovs[-1] if ovs else {}
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    check("29 合法覆写 ⇒ rc=0、state 变「%s」、overrides 长度 1" % PASS_ST,
          rc == 0 and e["tc_r1"].get("state") == PASS_ST and len(ovs) == 1,
          "rc=%s state=%s len=%d" % (rc, e["tc_r1"].get("state"), len(ovs)))
    check("30 record_sha256 = sha256(canonical(record 去掉 record_sha256)) 可复算",
          rec.get("record_sha256") == K.sha256_obj(body),
          str(rec.get("record_sha256"))[:16])
    mach = rec.get("machine") or {}
    check("31 machine 快照来源唯一 = n10_cases.json（source_path/source_md5/passed/reasons 原样搬运）",
          rec.get("machine", {}).get("schema") == "loop/n10_cases"
          and mach.get("source_path") == "n10_cases.json"
          and mach.get("source_md5") == N10_MD5
          and mach.get("passed") is False
          and mach.get("reasons") == N10_DOC["cases"]["tc_r1"]["reasons"]
          and mach.get("evidence") == N10_DOC["cases"]["tc_r1"]["evidence"],
          "src_md5=%s" % str(mach.get("source_md5"))[:16])
    check("32 记录字段：action/actor/actor_kind/prev_state/decided_at（时间走 --now 单一入口）",
          rec.get("schema") == "kb/case_override" and rec.get("action") == "pass"
          and rec.get("actor") == ACTOR and rec.get("actor_kind") == "human"
          and rec.get("prev_state") == PEND_ST and rec.get("decided_at") == NOW,
          "action=%s prev=%s" % (rec.get("action"), rec.get("prev_state")))
    check("33 台账 writer / 条目 updated_by 同步 human:<name>；updated_at 走 now_iso()",
          st_o.get("writer") == ACTOR and e["tc_r1"].get("updated_by") == ACTOR
          and st_o.get("updated_at") == NOW, "writer=%s" % st_o.get("writer"))
    check("34 含 overrides 的台账仍通过 case_states.schema.json 校验",
          K.validate(st_o, schema) == [], " | ".join(K.validate(st_o, schema)[:3]))

    # ---- 批量一次签（每例一条记录、全有或全无）----
    rc = overr("--case", "tc_r2", "--case", "tc_r3", "--actor", ACTOR, "--reason", "同批两例")
    e = entries()
    check("35 批量合法 ⇒ rc=0、两例各一条记录、状态皆「%s」（一次落盘）" % PASS_ST,
          rc == 0 and len(e["tc_r2"].get("overrides") or []) == 1
          and len(e["tc_r3"].get("overrides") or []) == 1
          and e["tc_r2"].get("state") == PASS_ST and e["tc_r3"].get("state") == PASS_ST,
          "rc=%s" % rc)
    rc, info = check_json("check", "--run", RUN, "--state-file", OVR, "--json")
    # 夹具里 tc_non10/tc_noreason/tc_ok 仍是「已修订待验」（它们专门用于 §4-5 拒绝用例），
    # 所以这里 check 仍 rc=3；要看的是**被签的三例已不阻断 I2** + info.waived 列出它们。
    check("36 签后被签用例不再阻断 I2：pending 不含 tc_r1/r2/r3；info.waived 列出三例"
          "（展示用，不加新判据）",
          rc == 3 and not {"tc_r1", "tc_r2", "tc_r3"} & set(info.get("pending") or [])
          and info.get("waived") == ["tc_r1", "tc_r2", "tc_r3"],
          "pending=%r waived=%r" % (info.get("pending"), info.get("waived")))

    # ---- 撤销 = 追加 revoke 记录（不删不改前面的记录）----
    before = entries()
    rc = overr("--case", "tc_r1", "--actor", ACTOR, "--reason", "撤销：按修正后的期望值复核",
               "--revoke")
    e = entries()
    ovs = e["tc_r1"].get("overrides") or []
    check("37 撤销 ⇒ rc=0、追加第 2 条 action=revoke、state 回「%s」、旧记录一字未改" % PEND_ST,
          rc == 0 and len(ovs) == 2 and ovs[-1].get("action") == "revoke"
          and ovs[-1].get("prev_state") == PASS_ST
          and e["tc_r1"].get("state") == PEND_ST
          and ovs[0] == (before["tc_r1"].get("overrides") or [None])[0],
          "len=%d state=%s" % (len(ovs), e["tc_r1"].get("state")))
    rc, info = check_json("check", "--run", RUN, "--state-file", OVR, "--json")
    check("38 撤销后 I2 恢复：tc_r1 重新出现在 pending；waived 只剩 tc_r2/tc_r3",
          rc == 3 and "tc_r1" in (info.get("pending") or [])
          and info.get("waived") == ["tc_r2", "tc_r3"],
          "pending=%r waived=%r" % (info.get("pending"), info.get("waived")))

    # ---- --verify：逐条复算 record_sha256 与 source_md5 ----
    m0 = md5_p(OVR)
    rc = overr("--verify")
    check("39 --verify 链完整 ⇒ rc=0 且不写盘（离线复核，不需要 actor/reason/case）",
          rc == 0 and md5_p(OVR) == m0, "rc=%s" % rc)
    orig = json.loads(json.dumps(read_p(OVR)))
    bad = json.loads(json.dumps(orig))
    entry_of(bad, "tc_r2")["overrides"][0]["record_sha256"] = "0" * 64
    K.write_json(OVR, bad)
    m_tampered = md5_p(OVR)
    rc = overr("--verify")
    check("40 §4-8 record_sha256 复核失败 ⇒ --verify rc=4 且不复写台账",
          rc == 4 and md5_p(OVR) == m_tampered, "rc=%s" % rc)
    rc = overr("--case", "tc_r2", "--actor", ACTOR, "--reason", "想继续", "--revoke")
    check("41 §4-8 锚复核失败时动作也在写盘前被拒 rc=4、台账不动",
          rc == 4 and md5_p(OVR) == m_tampered, "rc=%s" % rc)
    K.write_json(OVR, orig)
    check("42 还原后台账字节复原（md5 与篡改前一致）", md5_p(OVR) == m0, "")
    bad_n10 = json.loads(json.dumps(N10_DOC))
    bad_n10["cases"]["tc_r1"]["reasons"] = ["篡改后的原因"]
    K.write_json(N10, bad_n10)
    rc = overr("--verify")
    check("43 §4-8 source_md5 复核失败 ⇒ --verify rc=4", rc == 4, "rc=%s" % rc)
    os.remove(N10)
    rc = overr("--verify")
    check("44 source_md5 无法复核（件缺失）⇒ --verify rc=4（缺件不当作通过）",
          rc == 4, "rc=%s" % rc)
    K.write_json(N10, N10_DOC)
    check("45 恢复 n10_cases.json 后其 md5 与签名时一致", K.md5_file(N10) == N10_MD5, "")
    rc = overr("--verify")
    check("46 恢复后 --verify rc=0（整条链可离线复核）", rc == 0, "rc=%s" % rc)

    # ---- 5 台账损坏 ----
    with open(STATE, "w", encoding="utf-8") as f:
        f.write("{not json")
    rc = call("check", "--run", RUN, "--state-file", STATE, "--json")
    check("16 台账不是合法 JSON ⇒ check rc=4", rc == 4, "rc=%s" % rc)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

fails = [n for n, ok, _ in RESULTS if not ok]
print("\n汇总：PASS=%d FAIL=%d" % (len(RESULTS) - len(fails), len(fails)))
sys.exit(1 if fails else 0)
