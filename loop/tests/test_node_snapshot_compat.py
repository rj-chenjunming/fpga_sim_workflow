"""Preserve f710079 handler locations; older topologies need separate migration."""

from workflows.chunks import gates, host_steps, long_jobs, model_steps


def test_upstream_graph_handler_locations_remain_stable():
    expected = {
        host_steps.n0_baseline: 149,
        host_steps.n1_manifest: 303,
        host_steps.n2_diff: 374,
        host_steps.n5_impact: 475,
        host_steps.n6_apply: 791,
        host_steps.n7_compile: 1052,
        host_steps.n16_promote: 1216,
        long_jobs.n9_submit: 507,
        long_jobs.n9_park: 655,
        long_jobs.n15_select: 839,
        long_jobs.n15_run: 870,
        model_steps.n3_digest: 637,
        model_steps.n6_author: 886,
        model_steps.n8_check: 1223,
        model_steps.n10_reconcile: 1388,
        model_steps.n11_review: 1652,
        model_steps.n12_report: 1885,
        gates.halt: 733,
    }
    assert {fn.__name__: fn.__code__.co_firstlineno for fn in expected} == {
        fn.__name__: line for fn, line in expected.items()
    }
    assert {g.__code__.co_firstlineno for g in (gates.gate1, gates.gate2, gates.gate3)} == {715}
