"""对真实运行中的服务做一次完整 HTTP 走查（闸门操作台 + 看板所需的全部端点）。"""
import json, sys, time
import httpx

B = "http://127.0.0.1:8099"
c = httpx.Client(base_url=B, timeout=30.0, trust_env=False)

h = c.get("/api/health").json()
print(f"[health] ok={h['ok']} agently={h['agently']} python={h['python']} restored={h['restore_report']['restored']}")

rid = c.post("/api/runs", json={"baseline": "v0", "mode": "drill"}).json()["run_id"]
print(f"[create] run_id={rid}")

v = c.get(f"/api/runs/{rid}").json()
pi = v["pending_interrupt"] or {}
print(f"[gate1 ] status={v['status']} interrupt={pi.get('id')} gate={(pi.get('payload') or {}).get('gate')}")
print(f"[gate1 ] invariant=\"{ (pi.get('payload') or {}).get('invariant_note') }\"")
print(f"[gate1 ] blockers={[b['code'] for b in v['blockers']]}  can={v['can']}")
print(f"[gate1 ] conflicts={v['conflicts']['total']} blocks_release={v['conflicts']['blocks_release']}  rework={v['rework']}")

r = c.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
           json={"decision": "confirmed", "actor": "model:gpt-x", "reason": "越权"})
print(f"[gate1 ] 非人类 actor -> {r.status_code} detail.error={r.json()['detail']['error'][:60]}")

r = c.post(f"/api/runs/{rid}/gates/G1_diff_confirm/decision",
           json={"decision": "confirmed", "actor": "human:chenjunming", "reason": "2 条差异已逐条核对"})
print(f"[gate1 ] human -> {r.status_code} ok={r.json().get('ok')} decision={r.json().get('decision')}")

for i in range(60):
    v = c.get(f"/api/runs/{rid}").json()
    if ((v.get("pending_interrupt") or {}).get("id") or "").startswith("G2"): break
    if v["status"] == "failed": break
    time.sleep(0.5)

c1, c2 = v["counts"]["koutou1"], v["counts"]["koutou2"]
print(f"[gate2 ] status={v['status']} interrupt={(v.get('pending_interrupt') or {}).get('id')}")
print(f"[看板  ] 口径一={c1['value']} zero={c1['zero']} | 口径二={c2['value']} zero={c2['zero']} | both_zero={v['counts']['both_zero']}")
print(f"[看板  ] verdict.passed={v['evidence']['verdict']['passed']} reasons={v['evidence']['verdict']['reasons']}")
print(f"[看板  ] must_not=\"{v['evidence']['verdict']['must_not']}\"")
for m, im in v["evidence"]["imprints"].items():
    print(f"[看板  ] 印记 {m}: verified={im['verified_count']} failed={im['failed_count']} consistent={im['consistent']} refs={im['refs']}")
j = v["job"]
print(f"[看板  ] job={j['job_id']} phase={j['phase']} rc={j['rc']} tc={j['tc']} elapsed={j['elapsed_s']}s eta={j['eta_human']} conf={j['confidence']}")
print(f"[看板  ] slot locked={v['slot']['locked']} alive_known={v['slot']['holder_alive_known']} queue={v['slot']['queue_depth']}")
print(f"[看板  ] blockers={[(b['code'],b['severity']) for b in v['blockers']]}")

ev = c.get(f"/api/runs/{rid}/events", params={"since_seq": 0}).json()["events"]
print(f"[事件流] n={len(ev)} kinds={sorted({e['kind'] for e in ev})}")

ex = c.get(f"/api/runs/{rid}/evidence/exists", params={"ref": "kb/runs/RUN-20261015-120626/evidence/archive"}).json()
print(f"[E-2   ] evidence/archive -> exists={ex['exists']} note={ex.get('note')}")
ex2 = c.get(f"/api/runs/{rid}/evidence/exists", params={"ref": v["job"]["log_path"]}).json()
print(f"[证据  ] job log -> exists={ex2['exists']} bytes={ex2.get('bytes')}")

r = c.post(f"/api/runs/{rid}/gates/G3_regression_decision/decision",
           json={"decision": "full_now", "actor": "human:chenjunming", "reason": "试越 I4（权威枚举是 full_now）"})
print(f"[I4    ] G3 full_regression 提前提交 -> {r.status_code} {json.dumps(r.json(), ensure_ascii=False)[:120]}")

html = c.get("/").text
print(f"[前端  ] index.html bytes={len(html.encode())} 含双计数警示={'口径二为 0' in html or '不足以判绿' in html} 无外链={'http://' not in html and 'https://' not in html}")
