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


# ---------------------------------------------------------------- S0-rehearsal（SPEC-05 §6.2/§7）
#
# 演练只在**软件 state 目录**下造一次性小基线，走一次真实的 copy → 整体替换 RTL → 核验；
# 它证明"链路能走通"，**不**证明环境就绪、不证明 S0-b。以下断言都不读源码即可判定。


def rehearsal_client(tmp_path, monkeypatch):
    """把 S0 记录根指到临时 state，并保证演练输入也落在同一 state 下。"""
    from services import api
    state = tmp_path / 'state'
    store = S0Store(state / 's0', [state])
    monkeypatch.setattr(api, '_s0_store', lambda: store)
    return TestClient(api.app), store


def test_rehearsal_api_derives_small_baseline_and_replaces_entire_rtl(tmp_path, monkeypatch):
    client, store = rehearsal_client(tmp_path, monkeypatch)
    response = client.post('/api/s0/rehearsal', json={})
    assert response.status_code == 200, response.text
    record = response.json()

    assert record['status'] == 'prepared'
    assert record['ready_for_execution'] is False
    assert record['baseline_version'].startswith('S0-rehearsal:')
    assert {c['key']: c['status'] for c in record['checks']} == dict(
        copy='passed', rtl='passed', non_rtl='passed',
        ports='waiting', smoke='waiting', baseline='passed')

    baseline = Path(record['baseline'])
    source = Path(record['rtl_source'])
    work = Path(record['work_env'])
    state = tmp_path / 'state'
    # 演练输入与副本必须全在软件 state 下（不是 ENV_ROOT，也不是客户端给的路径）。
    for path in (baseline, source, work):
        assert state in path.parents, path
        assert str(path).startswith(str(state))

    # 小基线的最小结构：RTL / TB/top.sv / PKG / TESTLIB / doc（兼容分支之一）/ run。
    assert (baseline / 'RTL/old.v').is_file()
    assert (baseline / 'TB/top.sv').is_file()
    assert (baseline / 'PKG/x.v').is_file()
    assert (baseline / 'TESTLIB/tc_demo.sv').is_file()
    assert (baseline / 'doc').is_dir() and any((baseline / 'doc').glob('*.md'))
    assert (baseline / 'run').is_file()

    # 整体替换：副本 RTL 清单 == 演练新 RTL 清单，基线独有的旧 RTL 零残留。
    assert (source / 'old.v').read_text() != (baseline / 'RTL/old.v').read_text()
    assert manifest(work / 'RTL') == manifest(source)
    assert not (work / 'RTL/legacy.v').exists()

    # 基线前后清单一字不差，且与当前实际内容一致（演练期间零写入）。
    folder = store.root / record['id']
    assert (folder / 'baseline-before.json').read_bytes() == (folder / 'baseline-after.json').read_bytes()
    assert manifest(baseline) == json.loads((folder / 'baseline-before.json').read_text())
    assert manifest(work) != manifest(baseline)

    # 记录与真实 S0 记录同源，且带演练标记（证据里能区分 rehearsal 与 real）。
    saved = json.loads((folder / 'record.json').read_text())
    assert saved['status'] == 'prepared'
    marker = saved['rehearsal']
    assert marker['kind'] == 'S0-rehearsal'
    assert '不是环境就绪' in marker['note'] and 'S0-b' in marker['note']
    assert record['rehearsal']['kind'] == 'S0-rehearsal'
    assert '演练记录（S0-rehearsal）' in (folder / 'reports/s0-env/env-check-report.md').read_text()

    # 只读投影：GET 单条记录仍恒 false，并带演练标记与四项 passed。
    fresh = client.get('/api/s0/' + record['id']).json()
    assert fresh['ready_for_execution'] is False
    assert fresh['status'] == 'prepared'
    assert fresh['rehearsal']['kind'] == 'S0-rehearsal'
    assert {c['key']: c['status'] for c in fresh['checks']}['copy'] == 'passed'


def test_rehearsal_repeat_creates_new_record_and_never_overwrites(tmp_path, monkeypatch):
    client, store = rehearsal_client(tmp_path, monkeypatch)
    now = '2026-10-22T12:00:00+08:00'
    first = client.post('/api/s0/rehearsal', json={'now': now})
    second = client.post('/api/s0/rehearsal', json={'now': now})
    assert first.status_code == 200 and second.status_code == 200
    a, b = first.json(), second.json()
    assert a['id'] != b['id']
    assert a['work_env'] != b['work_env']
    json_first = store.root / a['id'] / 'record.json'
    before = json_first.read_bytes()
    third = client.post('/api/s0/rehearsal', json={'now': now})
    assert third.status_code == 200
    assert third.json()['id'] not in (a['id'], b['id'])
    # 前两次的记录与副本都还在，没有任何覆盖。
    assert json_first.read_bytes() == before
    for record in (a, b, third.json()):
        saved = json.loads((store.root / record['id'] / 'record.json').read_text())
        assert saved['rehearsal']['kind'] == 'S0-rehearsal'
        assert Path(record['work_env']).is_dir()


def test_rehearsal_rejects_client_paths_and_bad_now_without_side_effects(tmp_path, monkeypatch):
    client, store = rehearsal_client(tmp_path, monkeypatch)
    state = tmp_path / 'state'
    for key in ('baseline', 'rtl_source', 'work_env', 'baseline_version', 'work'):
        response = client.post('/api/s0/rehearsal', json={key: str(tmp_path / 'evil')})
        assert response.status_code == 400, (key, response.text)
        assert response.json()['detail']['error']
    for value in ('not-a-time', '2026-10-22T12:00:00', 123):
        response = client.post('/api/s0/rehearsal', json={'now': value})
        assert response.status_code == 400, (value, response.text)
        assert response.json()['detail']['error']
    # 拒绝发生在写盘之前：没有记录、也没有演练目录。
    assert not (state / 's0').exists()
    assert not (state / 's0-rehearsal').exists()


def test_rehearsal_never_writes_env_root(tmp_path, monkeypatch):
    from host import paths as P
    client, store = rehearsal_client(tmp_path, monkeypatch)
    env = P.ENV_ROOT
    assert env.is_dir(), f'本用例要求真实 ENV_ROOT 可读：{env}'
    names_before = sorted(p.name for p in env.iterdir())
    mtime_before = env.stat().st_mtime_ns
    response = client.post('/api/s0/rehearsal', json={})
    assert response.status_code == 200, response.text
    record = response.json()
    assert sorted(p.name for p in env.iterdir()) == names_before
    assert env.stat().st_mtime_ns == mtime_before
    for key in ('baseline', 'rtl_source', 'work_env'):
        assert env not in Path(record[key]).parents
        assert not str(record[key]).startswith(str(env))


def test_rehearsal_failure_keeps_failed_record_and_returns_422(tmp_path, monkeypatch):
    client, store = rehearsal_client(tmp_path, monkeypatch)

    def broken(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(shutil, 'copytree', broken)
    response = client.post('/api/s0/rehearsal', json={})
    assert response.status_code == 422, response.text
    detail = response.json()['detail']
    assert 'disk full' in detail['error']
    failed = detail['record']
    assert failed['status'] == 'failed'
    assert failed['ready_for_execution'] is False
    folder = store.root / failed['id']
    saved = json.loads((folder / 'record.json').read_text())
    assert saved['status'] == 'failed'
    assert saved['rehearsal']['kind'] == 'S0-rehearsal'
    assert (folder / 'baseline-before.json').is_file() and (folder / 'baseline-after.json').is_file()


def test_s0_index_advertises_rehearsal_capability(tmp_path, monkeypatch):
    client, store = rehearsal_client(tmp_path, monkeypatch)
    body = client.get('/api/s0').json()
    assert body['capabilities']['rehearsal'] is True
    assert body['capabilities']['prepare'] is True
    # 2026-10-27 S0-b 接入后，这两项**后端**能力位为 True（界面 D5 仍是灰态，属另一切片）。
    # 判据仍然是六项全 passed 才 ready；能力位只表示"后端有实现"，不表示"本记录已准出"。
    assert body['capabilities']['tb_adapt'] is True
    assert body['capabilities']['smoke'] is True
    assert body['records'] == []


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


# ---------------------------------------------------------------- C12（2026-10-27）：运行入口传了才校验

def _write_s0_record(record_id: str, *, ready: bool) -> None:
    """在测试 state 的 S0 记录根下写一条最小记录（不跑 prepare，避免依赖路径权限）。"""
    from host import paths as P

    folder = P.STATE_DIR / "s0" / record_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "record.json").write_text(json.dumps({
        "id": record_id, "status": "failed", "ready_for_execution": ready,
        "work_env": "/fixture/work", "created_at": "2026-10-27T00:00:00+0800",
        "baseline_version": "fixture",
    }), encoding="utf-8")


def test_run_entry_rejects_missing_s0_record_for_real():
    """C12：real + 传了不存在的记录 ⇒ 400，且原因可读（不得放行后再说）。"""
    from fastapi import HTTPException

    from services.api import _check_s0_record_for_run

    with pytest.raises(HTTPException) as excinfo:
        _check_s0_record_for_run("S0-NOT-EXIST-01", "real")
    assert excinfo.value.status_code == 400
    assert "不存在" in excinfo.value.detail["error"]


def test_run_entry_rejects_unready_s0_record_for_real():
    """C12：real + 记录未准出（ready_for_execution=false）⇒ 400，提示改 drill 或先做 S0-b。"""
    from fastapi import HTTPException

    from services.api import _check_s0_record_for_run

    rid = "S0-FIXTURE-UNREADY"
    _write_s0_record(rid, ready=False)
    with pytest.raises(HTTPException) as excinfo:
        _check_s0_record_for_run(rid, "real")
    error = excinfo.value.detail["error"]
    assert "未准出" in error and "ready_for_execution=false" in error
    assert "drill" in error and "S0-b" in error


def test_run_entry_rejects_even_file_claimed_ready_record_for_real():
    """C12 + S0 §3：`S0Store.get()` 把 `ready_for_execution` **归一为 false**（S0-b 未接入时恒假）
    ⇒ 即便记录文件里写 `true`，real 仍被拒：准出只能由真实核验产生，不能被文件声明伪造。
    （S0-b 接入后 `get()` 才可能返回 true，那时本用例应改成"允许"，属接入轮的验收项。）
    """
    from fastapi import HTTPException

    from services.api import _check_s0_record_for_run

    rid = "S0-FIXTURE-CLAIMS-READY"
    _write_s0_record(rid, ready=True)
    with pytest.raises(HTTPException) as excinfo:
        _check_s0_record_for_run(rid, "real")
    assert "未准出" in excinfo.value.detail["error"]


def test_run_entry_drill_and_empty_record_id_are_not_checked():
    """C12：drill 不覆盖 S0（徽标语义）⇒ 不存在的 id 也不拦；不传 ⇒ 不强制。"""
    from services.api import _check_s0_record_for_run

    _check_s0_record_for_run("S0-NOT-EXIST-01", "drill")   # 不抛
    _check_s0_record_for_run(None, "real")                  # 不抛（不强制 S0）
