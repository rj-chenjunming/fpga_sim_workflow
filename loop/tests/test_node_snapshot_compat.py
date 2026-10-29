"""Pinned TriggerFlow 4.1.4.8 derives chunk identity from handler locations."""

from workflows.chunks import gates, host_steps, long_jobs, model_steps


def test_existing_graph_handler_locations_remain_stable():
    expected = {
        host_steps.n0_baseline: 146,
        host_steps.n1_manifest: 300,
        host_steps.n2_diff: 371,
        host_steps.n5_impact: 472,
        host_steps.n6_apply: 627,
        host_steps.n7_compile: 847,
        host_steps.n16_promote: 1011,
        long_jobs.n9_submit: 463,
        long_jobs.n9_park: 599,
        long_jobs.n15_select: 783,
        long_jobs.n15_run: 814,
        model_steps.n3_digest: 633,
        model_steps.n6_author: 749,
        model_steps.n8_check: 1073,
        model_steps.n10_reconcile: 1238,
        model_steps.n11_review: 1498,
        model_steps.n12_report: 1731,
        gates.halt: 685,
    }
    assert {fn.__name__: fn.__code__.co_firstlineno for fn in expected} == {
        fn.__name__: line for fn, line in expected.items()
    }
    assert {g.__code__.co_firstlineno for g in (gates.gate1, gates.gate2, gates.gate3)} == {669}
