"""S0 契约：只用受控工程验证软件，不冒充 UVS 验收。"""
from pathlib import Path
import json
import shutil
import stat

import pytest
from fastapi.testclient import TestClient

from host.s0 import S0Store, PreparationFailed, manifest


@pytest.fixture
def setup_s0(tmp_path):
    baseline = tmp_path / 'baseline'
    for name in ('RTL', 'TB', 'PKG', 'TESTLIB', 'docs'):
        (baseline / name).mkdir(parents=True)
        (baseline / name / 'kept.txt').write_text(name)
    (baseline / 'TB/top.sv').write_text('module top; endmodule\n')
    (baseline / 'run').write_text('#!/bin/sh\nexit 99\n')
    (baseline / '.hidden').write_text('also inherited')
    (baseline / 'empty').mkdir()
    rtl = tmp_path / 'src/rtl'
    rtl.mkdir(parents=True)
    (rtl / 'new.sv').write_text('module dut; endmodule\n')
    payload = dict(baseline=str(baseline), baseline_version='operator:v1',
                   rtl_source=str(rtl), work_env=str(tmp_path / 'baseline_wk_v2'),
                   now='2026-10-21T12:00:00+00:00')
    return S0Store(tmp_path / 'records', [tmp_path]), payload


def test_full_copy_replaces_entire_rtl_and_records_witness(setup_s0):
    store, payload = setup_s0
    before = manifest(Path(payload['baseline']))
    result = store.prepare(payload)
    work = Path(payload['work_env'])
    assert manifest(Path(payload['baseline'])) == before
    assert manifest(work / 'RTL') == manifest(Path(payload['rtl_source']))
    assert not (work / 'RTL/kept.txt').exists()
    assert (work / '.hidden').read_text() == 'also inherited'
    assert (work / 'empty').is_dir()
    assert result['status'] == 'prepared'
    assert result['ready_for_execution'] is False
    assert {r['key']: r['status'] for r in result['checks']} == dict(
        copy='passed', rtl='passed', non_rtl='passed', ports='waiting', smoke='waiting', baseline='passed')
    folder = store.root / result['id']
    assert 'sim_verification:' in (folder / 'design-context.yaml').read_text()
    report = (folder / 'reports/s0-env/env-check-report.md').read_text()
    assert 'operator:v1' in report and '未执行' in report
    assert (folder / 'baseline-before.json').read_bytes() == (folder / 'baseline-after.json').read_bytes()


@pytest.mark.parametrize('part', ['RTL', 'TB/top.sv', 'PKG', 'TESTLIB', 'docs', 'run'])
def test_missing_input_rejected_before_creating_destination(setup_s0, part):
    store, payload = setup_s0
    p = Path(payload['baseline']) / part
    shutil.rmtree(p) if p.is_dir() else p.unlink()
    with pytest.raises(ValueError):
        store.prepare(payload)
    assert not Path(payload['work_env']).exists()


def test_doc_legacy_layout_compatible_without_renaming(setup_s0):
    store, payload = setup_s0
    (Path(payload['baseline']) / 'docs').rename(Path(payload['baseline']) / 'doc')
    result = store.prepare(payload)
    assert result['docs_dir'] == 'doc'
    assert (Path(payload['work_env']) / 'doc').is_dir()


def test_readonly_baseline_can_derive_writable_work_root_without_changing_source(setup_s0):
    store, payload = setup_s0
    baseline = Path(payload['baseline'])
    original = manifest(baseline)
    for directory in (baseline, baseline / 'RTL'):
        directory.chmod(0o555)
    try:
        store.prepare(payload)
        assert Path(payload['work_env']).stat().st_mode & stat.S_IWUSR
        assert not baseline.stat().st_mode & stat.S_IWUSR
        assert manifest(baseline) == original
    finally:
        baseline.chmod(0o755)
        (baseline / 'RTL').chmod(0o755)


@pytest.mark.parametrize('field', ['baseline', 'rtl_source', 'work_env'])
def test_outside_roots_rejected(setup_s0, tmp_path, field):
    store, payload = setup_s0
    payload[field] = str(tmp_path.parent / 'outside')
    with pytest.raises(PermissionError):
        store.prepare(payload)


@pytest.mark.parametrize('kind', ['existing', 'nested_work', 'source_in_baseline', 'records_in_baseline', 'symlink', 'empty_rtl'])
def test_unsafe_or_ambiguous_inputs_rejected(setup_s0, kind):
    store, payload = setup_s0
    baseline = Path(payload['baseline'])
    if kind == 'existing':
        Path(payload['work_env']).mkdir()
    elif kind == 'nested_work':
        payload['work_env'] = str(baseline / 'new')
    elif kind == 'source_in_baseline':
        payload['rtl_source'] = str(baseline / 'RTL')
    elif kind == 'records_in_baseline':
        store.root = baseline / 'records'
    elif kind == 'symlink':
        (baseline / 'TB/link').symlink_to(baseline / 'TB/top.sv')
    else:
        (Path(payload['rtl_source']) / 'new.sv').unlink()
    with pytest.raises((ValueError, FileExistsError)):
        store.prepare(payload)


@pytest.mark.parametrize('target', ['baseline', 'rtl_source', 'work_env'])
def test_later_drift_is_visible_without_rewriting_original_evidence(setup_s0, target):
    store, payload = setup_s0
    result = store.prepare(payload)
    record = store.root / result['id'] / 'record.json'
    original = record.read_bytes()
    path = Path(payload[target])
    if target == 'work_env':
        path = path / 'TB'
    (path / 'unexpected').write_text('drift')
    fresh = S0Store(store.root, store.allowed_roots).get(result['id'])
    assert fresh['status'] == 'failed'
    assert fresh['verification']['drift']
    assert fresh['ready_for_execution'] is False
    assert record.read_bytes() == original


def test_empty_directory_drift_detected(setup_s0):
    store, payload = setup_s0
    result = store.prepare(payload)
    (Path(payload['work_env']) / 'PKG/newempty').mkdir()
    assert store.get(result['id'])['status'] == 'failed'


def test_copy_error_preserves_explicit_failed_record(setup_s0, monkeypatch):
    store, payload = setup_s0
    def broken(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(shutil, 'copytree', broken)
    with pytest.raises(PreparationFailed) as error:
        store.prepare(payload)
    result = error.value.record
    assert result['status'] == 'failed' and 'disk full' in result['error']
    assert json.loads((store.root / result['id'] / 'record.json').read_text())['status'] == 'failed'


def test_duplicate_never_overwrites_and_bad_id_rejected(setup_s0):
    store, payload = setup_s0
    store.prepare(payload)
    with pytest.raises(FileExistsError):
        store.prepare(payload)
    with pytest.raises(ValueError):
        store.get('../outside')


def test_report_write_failure_never_leaves_prepared_status(setup_s0, monkeypatch):
    store, payload = setup_s0
    def unavailable(*args):
        raise OSError('report volume unavailable')
    monkeypatch.setattr(store, '_write_report', unavailable)
    with pytest.raises(PreparationFailed) as error:
        store.prepare(payload)
    saved = json.loads((store.root / error.value.record['id'] / 'record.json').read_text())
    assert saved['status'] == 'failed'
    assert 'report volume unavailable' in saved['error']


def test_missing_report_detected_on_recheck(setup_s0):
    store, payload = setup_s0
    record = store.prepare(payload)
    store.report_path(record['id']).unlink()
    assert store.get(record['id'])['status'] == 'failed'


def test_api_prepare_list_get_report_and_errors(setup_s0, monkeypatch):
    from services import api
    store, payload = setup_s0
    monkeypatch.setattr(api, '_s0_store', lambda: store)
    client = TestClient(api.app)
    response = client.post('/api/s0', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert client.get('/api/s0').json()['records'][0]['id'] == result['id']
    assert client.get('/api/s0/' + result['id']).json()['ready_for_execution'] is False
    assert 'operator:v1' in client.get(result['report_url']).text
    assert client.post('/api/s0', json=payload).status_code == 409
    assert client.post('/api/s0', json={}).status_code == 400
    assert client.get('/api/s0/S0-missing').status_code == 404
