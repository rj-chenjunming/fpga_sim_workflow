"""端到端演练：drill 模式走完 N0→N16，三道闸门全过。"""
import asyncio, json, os, sys
sys.path.insert(0, "loop")
os.environ["LOOP_NOW"] = "2026-10-15T14:30:00"
from workflows.main_flow import RunManager

async def show(m, rid, label):
    v = m.run_view(rid)
    pi = (v.get("pending_interrupt") or {})
    print(f"--- {label}: status={v['status']} node={(v['node_history'] or [{}])[-1].get('node')} "
          f"interrupt={pi.get('id')} gates={[(g['gate'],g['decision']) for g in v['gate_history']]}")
    if v.get("counts"):
        print("    口径一=", v["counts"]["koutou1"]["value"], "口径二=", v["counts"]["koutou2"]["value"])
    hard = [b["code"] for b in v["blockers"] if b["severity"]=="blocker"]
    if hard: print("    blockers:", hard)
    return v

async def main():
    m = RunManager()
    rid = await m.start(baseline="v0", mode="drill", scenario="happy")
    print("run_id:", rid)
    await show(m, rid, "起点")

    await m.decide(run_id=rid, gate="G1_diff_confirm", decision="confirmed",
                   actor="human:chenjunming", reason="2 条差异已核对")
    await asyncio.sleep(0.8)
    v = await show(m, rid, "过闸门1 后")

    for _ in range(40):
        await m.async_sync(rid)
        v = m.run_view(rid)
        pi = ((v.get("pending_interrupt") or {}).get("payload") or {})
        if (v.get("pending_interrupt") or {}).get("id","").startswith("G2"): break
        if v.get("status") == "failed": break
        await asyncio.sleep(0.5)
    v = await show(m, rid, "等作业完成后")
    print("    job:", json.dumps({k: v["job"][k] for k in ("job_id","phase","rc","tc","elapsed_s")} if v.get("job") else None, ensure_ascii=False))
    print("    evidence present:", bool(v.get("evidence")))

    if ((v.get("pending_interrupt") or {}).get("id","").startswith("G2")):
        await m.decide(run_id=rid, gate="G2_report_accept", decision="accept",
                       actor="human:chenjunming", reason="接受报告本身，不解除冲突")
        await asyncio.sleep(0.8)
        v = await show(m, rid, "过闸门2 后")
        await m.decide(run_id=rid, gate="G3_regression_decision", decision="milestone_only",
                       actor="human:chenjunming", reason="I4 冲突未清零，只做里程碑")
        await asyncio.sleep(1.5)
        v = await show(m, rid, "过闸门3 后（应到 N16）")
        print("    N16 结果:", json.dumps([n for n in v["node_history"] if n["node"]=="N16"], ensure_ascii=False)[:300])
    await m.stop_watching()

asyncio.run(main())
