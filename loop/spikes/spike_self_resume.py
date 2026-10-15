import asyncio, json
from agently import TriggerFlow
flow = TriggerFlow(name="spike-self")
hits = []
async def gate(data):
    hits.append({"call": len(hits)+1, "is_resume": data.is_resume,
                 "input": data.input,
                 "resume": getattr(data.resume, "__dict__", str(data.resume))})
    if data.is_resume:
        print("  [gate] RESUME 分支 input=", data.input)
        print("  [gate] resume __dict__=", json.dumps(getattr(data.resume,'__dict__',{}), default=str, ensure_ascii=False)[:400])
        await data.async_emit("GATE_OK", {"from": "gate"})
        return {"done": True}
    print("  [gate] 首次进入，停放")
    await data.async_pause_for(type="gate_decision", interrupt_id="G1", payload={"m": 1}, resume_to="self")
    return {"status": "waiting"}
async def after(data):
    print("  [after] input=", data.input)
    return data.input
flow.to(gate)
flow.when("GATE_OK").to(after)
async def main():
    ex = flow.create_execution(auto_close=False)
    await ex.async_start({"x": 1})
    await asyncio.sleep(0.2)
    print("waiting:", ex.is_waiting(), "pending:", list(ex.get_pending_interrupts()))
    await ex.async_continue_with("G1", {"decision": "confirmed", "actor": "human:cj"})
    await asyncio.sleep(0.4)
    print("hits:", json.dumps(hits, default=str, ensure_ascii=False)[:600])
    await ex.async_close(pending_interrupts="cancel")
asyncio.run(main())
