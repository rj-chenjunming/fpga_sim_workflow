import asyncio, json, os, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, '/home/fpga/work/compat-check/loop')
from agently import TriggerFlow
from workflows.chunks import gates, host_steps

run_dir=Path('/home/fpga/work/compat-gate-run')
run_dir.mkdir(exist_ok=True)
ctx=SimpleNamespace(run_dir=run_dir,run_id='RUN-1',mode='drill',kb=None,
 event=lambda *a,**k:None,node_started=lambda *a,**k:None,node_finished=lambda *a,**k:None,node_failed=lambda *a,**k:None)
gates.ctx_of=lambda data:ctx
gates._cycles_view=lambda *a:{'g2_rework_cycles':0,'n6_n8_cycles':0}
gates._persist_cycles=lambda *a:None
gates._state_facts=lambda data:{}
gates._ledger_notes=lambda ctx:[]
gates._counts_for=lambda data:{}
gates._cycle=lambda *a:0
gates.contracts.gate_material=lambda **kw:{'hard_block':[],'difference_items':{}}
gates.contracts.report_claimed_verdict=lambda *a:None
gates.decision_options=lambda *a,**kw:[]
gates.precheck_decision=lambda **kw:{'entries':{}}
gates.authority_record=lambda *a:{'signed_at':'t'}
gates.human_signed_flag=lambda *a:True
gates.append_decision_ledger=lambda *a:None
host_steps.run_kb_tool=lambda *a,**kw:{'rc':0}
flow=TriggerFlow(name='compat-gate-test')
flow.to(gates.gate1)
e=flow.create_execution(auto_close=False)
p=Path('/home/fpga/work/compat-gate-snapshot.json')
async def main():
 if os.environ['STAGE']=='save':
  await e.async_start({})
  for _ in range(200):
   if e.is_waiting(): break
   await asyncio.sleep(.01)
  assert e.is_waiting(), 'gate did not pause'
  snap=e.save(require_idle=True)
  p.write_text(json.dumps(snap))
  print('baseline gate paused and snapshot saved')
 else:
  await e.async_load(json.loads(p.read_text()))
  assert e.is_waiting(), 'loaded gate is not waiting'
  pending=e.get_pending_interrupts()
  assert 'G1_diff_confirm:0' in pending, pending
  await e.async_continue_with('G1_diff_confirm:0', {'decision':'confirmed','actor':'human:test','reason':'checked'}, resume_request_id='test-1', actor='human:test')
  for _ in range(200):
   await asyncio.sleep(.01)
   if not e.is_waiting(): break
  assert not e.is_waiting(), 'gate remains paused'
  print('baseline waiting gate loaded and resumed')
 await e.async_close(pending_interrupts='cancel')
asyncio.run(main())

