import asyncio, json, os, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, '/home/fpga/work/compat-check/loop')
from agently import TriggerFlow
from workflows.chunks import long_jobs
record=[]
ctx=SimpleNamespace(run_id='RUN-1',pending={},runner=SimpleNamespace(poll=lambda job: SimpleNamespace(phase='cancelled')),
 admission=SimpleNamespace(release=lambda **kw:record.append(('release',kw))),
 event=lambda kind,**kw:record.append((kind,kw)),node_failed=lambda *a,**k:None)
long_jobs.ctx_of=lambda data:ctx
async def seed(data):
 await data.async_set_state('n9_job',{'job_id':'job-1','cases':['case1'],'tc':'case1','log_path':'/tmp/mock'})
 return {}
flow=TriggerFlow(name='compat-job-test')
flow.to(seed).to(long_jobs.n9_park)
e=flow.create_execution(auto_close=False)
p=Path('/home/fpga/work/compat-job-snapshot.json')
async def main():
 if os.environ['STAGE']=='save':
  await e.async_start({})
  for _ in range(200):
   if e.is_waiting(): break
   await asyncio.sleep(.01)
  assert e.is_waiting(), 'job did not pause'
  p.write_text(json.dumps(e.save(require_idle=True)))
  print('baseline job paused and snapshot saved')
 else:
  await e.async_load(json.loads(p.read_text()))
  assert e.is_waiting() and 'JOB:job-1' in e.get_pending_interrupts()
  try:
   await e.async_continue_with('JOB:job-1', {'job_id':'job-1','phase':'cancelled'}, resume_request_id='job-test-1')
  except RuntimeError as exc:
   assert '被取消' in str(exc), str(exc)
  for _ in range(200):
   if record: break
   await asyncio.sleep(.01)
  assert any(x[0]=='warning' and x[1].get('status')=='cancelled' for x in record),record
  for _ in range(200):
   if any(x[0]=='release' for x in record): break
   await asyncio.sleep(.01)
  assert any(x[0]=='release' for x in record),record
  print('baseline waiting job loaded, cancellation observed, slot released')
 await e.async_close(pending_interrupts='cancel')
asyncio.run(main())

