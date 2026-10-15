"""逐个驱动 5 个模型节点（真请求），验证各自 request 契约可用。
不经过闸门/回边，因此不受 N8 裁决影响。"""
import asyncio, json, os, sys, pathlib
sys.path.insert(0, ".")
os.environ["LOOP_LLM_MODE"] = "live"
from host import paths as P
from host.progress import ProgressLog
from services.contracts import KbSources
from workflows.context import RunCtx, RESOURCE_KEY
from workflows.chunks import model_steps as MS

class FakeData:
    def __init__(self, ctx, initial=None):
        self._state = dict(initial or {}); self._ctx = ctx
        self.is_resume = False; self.resume = None
        self.input = {}; self.emitted = []
    def require_resource(self, key):
        assert key == RESOURCE_KEY; return self._ctx
    def get_state(self, key=None, default=None, **kw):
        if key is None: return dict(self._state)
        return self._state.get(key, default)
    async def async_set_state(self, key, value, **kw): self._state[key] = value
    async def async_emit(self, event, value=None, **kw): self.emitted.append(event)

async def main():
    run_dir = sorted([p for p in (P.KB_RUNS).glob("RUN-*") if (p/"evidence").is_dir()],
                     key=lambda p: p.stat().st_mtime)[-1]
    print("复用运行目录:", run_dir.name, "（含 drill 拷入的全跑日志）")
    ctx = RunCtx(run_id=run_dir.name, run_dir=run_dir, mode="drill", scenario="happy",
                 kb=KbSources.from_repo(P.REPO_ROOT), progress=ProgressLog(P.EVENTS_DIR, run_dir.name+"-nodes"))
    n2 = json.loads((run_dir/"n2_diff.json").read_text()) if (run_dir/"n2_diff.json").is_file() else {"diffs":[]}
    n5 = json.loads((run_dir/"n5_impact.json").read_text()) if (run_dir/"n5_impact.json").is_file() else {}
    d = FakeData(ctx, {"n2_diff": {"diff_count": len(n2.get("diffs", []))},
                       "n5_impact": {"must_change_cases": n5.get("must_change_cases", []) or ["tc_pcie_rw_02"],
                                     "must_change_count": len(n5.get("must_change", []))},
                       "rework_limit": 3, "n6_n8_cycles": 0})

    results = {}
    for name, fn in (("N3", MS.n3_digest), ("N6", MS.n6_author), ("N8", MS.n8_check),
                     ("N10", MS.n10_reconcile), ("N11", MS.n11_review), ("N12", MS.n12_report)):
        out = await fn(d)
        results[name] = {"mode": out.get("mode"), "standin": out.get("standin"),
                         "provider": out.get("provider"),
                         "problems": (out.get("validation") or {}).get("problems", []),
                         "data_keys": sorted((out.get("data") or {}).keys())[:10]}
        print("  %-4s mode=%-8s problems=%s" % (name, out.get("mode"), results[name]["problems"]))

    n12 = d.get_state("n12_report") or {}
    acc = (n12.get("validation") or {}).get("accepted", {})
    print("\nN11 assessment:", (d.get_state("n11_review") or {}).get("data", {}).get("assessment"))
    print("N12 counts_match_authority:", acc.get("counts_match_authority"))
    print("N12 权威口径:", json.dumps(acc.get("authoritative_counts"), ensure_ascii=False)[:160])
    print("N12 引用口径:", json.dumps(acc.get("counts_quoted"), ensure_ascii=False)[:200])
    print("N12 章节数:", len(acc.get("sections") or []))
    print("N12 open_items:", len(acc.get("open_items") or []))
    model_nodes = ["N3","N6","N8","N11","N12"]
    live = [n for n in model_nodes if results[n]["mode"] == "live"]
    print(f"\n模型节点 live {len(live)}/5: {live}")
    assert len(live) == 5, results
    assert all(not results[n]["problems"] for n in model_nodes), results

asyncio.run(main())
