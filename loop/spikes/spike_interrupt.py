"""spike：验证 pause → save(require_idle) → 新进程 load → continue_with 恢复。"""
import asyncio, json, sys
from agently import TriggerFlow

flow = TriggerFlow(name="spike-interrupt")

async def n0(data):
    print("  [n0] input =", data.input)
    return {"val": 1}

async def gate(data):
    print("  [gate] value =", data.input)
    resumed = await data.async_pause_for(
        type="gate_decision",
        payload={"material": "diff pending=3"},
        resume_to="next",
        interrupt_id="GATE1",
        max_resumes=1,
    )
    print("  [gate] resumes ->", resumed)
    return {"decision": resumed}

async def n5(data):
    print("  [n5] value =", data.input)
    return {"impact": "ok", "saw": data.input}

(flow.to(n0).to(gate).to(n5))

async def phase_a():
    ex = flow.create_execution(auto_close=False)
    await ex.async_start({"run": "r1"}, wait_for_result=False)
    await asyncio.sleep(0.3)
    print("phase_a waiting?", ex.is_waiting())
    print("phase_a pending:", json.dumps(ex.get_pending_interrupts(), ensure_ascii=False, default=str))
    snap = ex.save(require_idle=True)
    open("loop/spikes/snap.json", "w").write(json.dumps(snap, default=str))
    print("phase_a snapshot keys:", sorted(snap.keys()))
    print("phase_a state:", ex.get_state())
    return ex

async def phase_b():
    ex = flow.create_execution(auto_close=False)
    snap = json.load(open("loop/spikes/snap.json"))
    await ex.async_load(snap)
    print("phase_b restored waiting?", ex.is_waiting(), "state:", ex.get_state())
    pending = ex.get_pending_interrupts()
    print("phase_b pending:", json.dumps(pending, ensure_ascii=False, default=str))
    # 找到闸门中断 id
    pid = None
    if isinstance(pending, dict):
        pid = next(iter(pending), None)
    print("phase_b interrupt id =", pid)
    await ex.async_continue_with(pid, {"actor": "human", "decision": "confirmed"})
    await asyncio.sleep(0.5)
    print("phase_b state after resume:", ex.get_state())
    try:
        r = await ex.async_close()
        print("phase_b close ->", r)
    except Exception as e:
        print("phase_b close raised:", type(e).__name__, e)

async def main():
    print("=== phase A（跑到闸门并落盘）===")
    ex = await phase_a()
    try: await ex.async_close(pending_interrupts="cancel")
    except Exception as e: print("phase_a close:", type(e).__name__, e)
    print("\n=== phase B（新执行，从盘恢复并放行）===")
    await phase_b()

asyncio.run(main())
