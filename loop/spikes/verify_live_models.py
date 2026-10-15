"""真模型验证：drill 闭环跑完，断言 5 个语义节点确实走了 ModelRequest。"""
import asyncio, json, os, sys
sys.path.insert(0, ".")
os.environ["LOOP_LLM_MODE"] = "live"
from host import model_provider as MP
from workflows.main_flow import RunManager

NODES = ["n3_digest", "n6_author", "n8_check", "n11_review", "n12_report"]

async def main():
    st = MP.resolve()
    print("provider:", json.dumps({k: st.public()[k] for k in
          ("available","plugin","family","model","has_api_key","proxy","max_tokens")}, ensure_ascii=False))
    assert st.available, st.reason

    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill")
    print("run_id:", rid)
    ex = m.executions[rid]
    for _ in range(120):
        if ex.is_waiting(): break
        await asyncio.sleep(0.2)
    await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                   actor="human:live-verify", reason="真模型验证")
    for i in range(400):
        v = m.run_view(rid)
        pid = ((v.get("pending_interrupt") or {}).get("id") or "")
        if pid.startswith("G2") or v["status"] == "failed":
            break
        await asyncio.sleep(0.5)
    v = m.run_view(rid)
    print(f"status={v['status']} interrupt={((v.get('pending_interrupt') or {}).get('id'))}")

    # 从事件流读出各节点的 mode
    ev = v["events"]
    seen = {}
    for e in ev:
        if e.get("kind") == "node_finished" and e.get("node") in ("N3","N6","N8","N11","N12"):
            seen[e["node"]] = e.get("status")
    print("节点终态:", json.dumps(seen, ensure_ascii=False))

    print("=== 各节点 state（mode / 校验问题）===")
    ex_state = {}
    for key in NODES:
        s = ex.get_state(key) or {}
        ex_state[key] = {
            "mode": s.get("mode"), "provider": s.get("provider"),
            "standin": s.get("standin"),
            "problems": (s.get("validation") or {}).get("problems", [])[:4],
            "model_call_failed": s.get("model_call_failed"),
        }
    print(json.dumps(ex_state, ensure_ascii=False, indent=1))

    n12 = ex.get_state("n12_report") or {}
    acc = (n12.get("validation") or {}).get("accepted", {})
    print("N12 counts_match_authority =", acc.get("counts_match_authority"))
    print("N12 引用口径:", json.dumps(acc.get("counts_quoted"), ensure_ascii=False)[:200])
    print("N12 权威口径:", json.dumps(acc.get("authoritative_counts"), ensure_ascii=False))
    print("N12 verdict_statement:", str(acc.get("verdict_statement"))[:200])
    print("N12 章节数:", len(acc.get("sections") or []))
    live = [k for k, s in ex_state.items() if s["mode"] == "live"]
    print(f"\n走真模型的节点 {len(live)}/5: {live}")
    await m.stop_watching()
    assert len(live) == 5, f"不是 5 个节点都走了真模型：{ex_state}"
    assert acc.get("counts_match_authority") is True, "N12 引用数字与权威不一致"

asyncio.run(main())
