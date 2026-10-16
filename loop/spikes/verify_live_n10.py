"""真模型验证 N10：Host 抽数字+分桶，模型做三分类，Host 交叉核对。"""
import asyncio, json, os, sys
sys.path.insert(0, ".")
os.environ["LOOP_LLM_MODE"] = "live"
from host import paths as P
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.context import RunCtx, RESOURCE_KEY
from workflows.chunks import model_steps as MS

class FakeData:
    def __init__(self, ctx): self._s={}; self._c=ctx; self.is_resume=False; self.resume=None; self.input={}; self.emitted=[]
    def require_resource(self,k): assert k==RESOURCE_KEY; return self._c
    def get_state(self,k=None,d=None,**kw): return dict(self._s) if k is None else self._s.get(k,d)
    async def async_set_state(self,k,v,**kw): self._s[k]=v
    async def async_emit(self,e,v=None,**kw): self.emitted.append(e)

async def main():
    # 直接用归档夹具当输入（它同时有 n2_diff.json 与全跑证据）
    run_dir = P.KB_RUNS / "RUN-20261015-120626"
    ctx = RunCtx(run_id="RUN-20261015-120626", run_dir=run_dir, mode="drill", scenario="happy",
                 kb=KbSources.from_workspace(P.WORKSPACE_ROOT),
                 progress=ProgressLog(P.EVENTS_DIR, "N10-live-probe"))
    d = FakeData(ctx)
    out = await MS.n10_reconcile(d)
    fb = out["fail_buckets"]; fc = out["fail_classification"]
    print("Host 分桶:", fb["bucket_count"], "桶 | coverage:", json.dumps(fb["coverage"], ensure_ascii=False))
    print("合并报告:", fb["merged_note"])
    print("修订点:", json.dumps(fb["revision_points"], ensure_ascii=False))
    print("任一桶落在修订点上:", fb["any_bucket_overlaps_revision_point"])
    print("分类 mode:", fc.get("mode"), "provider:", fc.get("provider"))
    print("校验问题:", (fc.get("validation") or {}).get("problems"))
    acc = (fc.get("validation") or {}).get("accepted") or {}
    print("已分类桶数:", acc.get("buckets_classified"), "/", acc.get("buckets_expected"))
    print("按分类的条目数:", json.dumps(acc.get("entries_by_classification"), ensure_ascii=False))
    print("Host 冲突:", json.dumps(acc.get("conflicts"), ensure_ascii=False)[:400])
    print("summary:", str(acc.get("summary"))[:220])
    for it in (acc.get("items") or [])[:3]:
        print("  样本:", json.dumps(it, ensure_ascii=False)[:230])
    await MS.n10_reconcile(d)  # 幂等性：再跑一次不应崩
    assert fc.get("mode") == "live", fc
    assert (fc.get("validation") or {}).get("problems") == [], fc
    print("\nN10 live 通过，零校验问题")

asyncio.run(main())
