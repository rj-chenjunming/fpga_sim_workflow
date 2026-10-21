"""Read-only roadmap observations; temporary fixtures, intercepted tools, optional browser.

Run from the repository root with its venv. This records current behavior and is
not a test claiming that the observed defects pass acceptance.
"""
import argparse
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'loop'))


def emit(probe, **values):
    print(json.dumps({'probe': probe, **values}, ensure_ascii=False))


async def backend_observations():
    from services.config_api import list_baselines
    from services.agent_view import build_agents
    from workflows.chunks import host_steps

    class Captured(Exception):
        pass

    with tempfile.TemporaryDirectory(prefix='roadmap-review-') as folder:
        root = Path(folder)
        baseline = root / 'baselines' / 'v-next'
        baseline.mkdir(parents=True)
        manifest = baseline / 'manifest.json'
        manifest.write_text('{}')
        emit('manifest_only', valid=list_baselines(root)['baselines'][0]['valid'])
        manifest.write_text('[]')
        try:
            list_baselines(root)
        except Exception as exc:
            emit('manifest_array', exception=type(exc).__name__)
        else:
            emit('manifest_array', exception=None)
        guardian = next(a for a in build_agents([], run_dir=root) if a['role'] == 'guardian')
        emit('guardian_idle', summary=guardian['summary'])
        ctx = SimpleNamespace(mode='real', run_dir=root / 'run', run_id='REVIEW',
                              node_started=lambda *args: None)

        def capture(tool, args):
            emit('n2_baseline', requested='v-next',
                 actual=args[args.index('--from-baseline') + 1])
            raise Captured

        data = SimpleNamespace(input={'baseline': 'v-next'},
                               get_state=lambda key: {'baseline': 'v-next'})
        with patch.object(host_steps, 'ctx_of', return_value=ctx), patch.object(host_steps, 'run_kb_tool', capture):
            try:
                await host_steps.n2_diff(data)
            except Captured:
                pass
    spec = importlib.util.spec_from_file_location('doc_links', REPO / 'doc/audit/check_doc_links.py')
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    ref = 'kb/tools/kb_lib.py'
    found, label = scanner._resolve(ref, None, None)
    emit('tool_reference', local_exists=(REPO / ref).is_file(), resolved=str(found), root=label)


def browser_observation():
    sys.path.insert(0, str(REPO / 'loop/tests/browser'))
    from test_run_sessions import static_url, ui, select, release, pw
    server = static_url.__wrapped__()
    url = next(server)
    fixture = ui.__wrapped__(url)
    page, api = next(fixture)
    try:
        api['hold'] = lambda path: path == '/api/runs/A'
        select(page, 'A')
        pw.expect(page.locator('#runHead')).to_contain_text('加载')
        page.wait_for_timeout(80)
        release(page, api, {'detail': {'error': 'controlled first-load failure'}}, 503)
        pw.expect(page.locator('#runAlerts')).to_contain_text('controlled first-load failure')
        emit('first_load_error', head=page.locator('#runHead').inner_text(),
             claims_previous_success='最近一次成功' in page.locator('#runAlerts').inner_text(),
             write_requests=len(api['posts']), page_errors=api['errors'])
    finally:
        api['hold'] = None
        while api['pending']:
            api['pending'].pop().fulfill(json=api['views']['A'])
        fixture.close()
        server.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true')
    options = parser.parse_args()
    os.environ.setdefault('LOOP_LLM_MODE', 'standin')
    asyncio.run(backend_observations())
    if options.browser:
        browser_observation()
