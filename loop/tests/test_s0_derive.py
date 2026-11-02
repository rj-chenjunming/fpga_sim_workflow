"""T1：单一 RTL 文件夹派生引擎（SPEC-05 §9；计划 2026-10-30 §4 冻结接口 T1）。

全部用例用 `tmp_path` 自造小工程：不读真实 `ENV_ROOT`、不写真实环境、不执行基线脚本。
断言都可由命令/清单输出判定，不需要读实现源码：

1. 根判定：目录名 `RTL`/`SRC` 才收，其它显式拒绝并列出合法值；
2. 选择性复制：排除 `kb/runs`/`loop`/`SIMLIB_RUN` 等整目录，软链不复制不跟随且进 `skipped`；
   `kb/` 下**只有** `kb/{baselines,index,conflicts,adjudication}` 四个数据子目录随副本复制，
   其余 kb 条目（`kb/tools`、`kb/schema`、`kb/README.md`…）不复制但落账（`reason="kb_non_data"`）；
3. `copy_selected` + `manifest_filtered` 逐文件相等（copy 检查判据）；
4. RTL 根整棵替换（旧文件零残留）；SRC 根只换 `RTL/SRC` 子树（其余 RTL 与基线一致，动了就 failed）；
5. RTL 源的 VCS/缓存目录（`.git`/`.svn`/`.hg`/`__pycache__`）跳过并落账 `rtl_plan`，
   `rtl` 检查与 `folder_warning` 用**同一份**过滤后源清单；源里出现软链仍按 §2 直接拒绝；
6. 错目录只告警不拦截（`folder_warning` 数字）；
7. `prepare_from_rtl` 记录字段、失败保留副本与记录、基线零写入；
8. `advance`：ports 未 passed 拒绝冒烟；passed 时冒烟一次并落账/刷新 checks/ready；
9. legacy `prepare()` 不回归（记录不多出字段）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from host import derive, s0b
from host.s0 import AUTO_PHASES, PreparationFailed, S0Store, manifest

NOW = '2026-10-30T12:00:00+00:00'
LATER = '2026-10-30T12:00:01+00:00'

DUT_V1 = ('module dut(\n'
          '    input  clk,\n'
          '    input  [7:0] din,\n'
          '    output [7:0] dout\n'
          ');\nendmodule\n')
# 端口不变、只改注释：ports 判据必须仍为 passed（注解不是接口差异）
DUT_V2 = ('module dut(\n'
          '    // 新版 RTL：端口不变，仅注释差异\n'
          '    input  clk,\n'
          '    input  [7:0] din,\n'
          '    output [7:0] dout\n'
          ');\nendmodule\n')
# 多一个端口：ports 判据必须 waiting（差异未被任何 hunk 覆盖）
DUT_EN = ('module dut(\n'
          '    input  clk,\n'
          '    input  [7:0] din,\n'
          '    input  en,\n'
          '    output [7:0] dout\n'
          ');\nendmodule\n')
IMP_V1 = 'module a_imp(\n    input clk\n);\nendmodule\n'
COMMON_V = 'module common(\n    input clk\n);\nendmodule\n'
VENDOR_V = 'module vendor(\n    input clk\n);\nendmodule\n'
EXTRA_V = 'module extra(\n    input clk\n);\nendmodule\n'
TB_TOP = 'module top;\n  dut u_dut(.clk(clk), .din(din), .dout(dout));\nendmodule\n'
PKG_V = 'package p;\nendpackage\n'

RTL_FILES = {
    'SRC/dut.v': DUT_V1,
    'SRC/imports/a.v': IMP_V1,
    'RTL_COMMON/common.v': COMMON_V,
    'vendor.v': VENDOR_V,
}
# 真实 ENV_ROOT/RTL 里有内嵌 git 仓库（实测 RTL/.git、RTL/RTL_COMMON/.git）⇒ 基线口径也必须跳过
BASELINE_FILES = {f'RTL/{rel}': text for rel, text in RTL_FILES.items()}
BASELINE_FILES.update({
    'RTL/.git/HEAD': 'ref: refs/heads/main\n',
    'TB/top.sv': TB_TOP,
    'PKG/pkg.sv': PKG_V,
    'TESTLIB/tc_a.sv': 'module tc_a;\nendmodule\n',
    'TESTLIB/tc_b.sv': 'module tc_b;\nendmodule\n',
    'doc/index.md': '# 文档\n',
    'run': '#!/bin/sh\nexit 99\n',
    'all_define.txt': '-define SIM\n',
    'kb/baselines/v0/allfiles.md5': 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  RTL/SRC/dut.v\n',
    'kb/index/index.json': '{}\n',
    'kb/conflicts/conflicts.csv': 'id,kind\n',
    'kb/adjudication/adjudication.json': '[]\n',
    # kb 非数据子集：权威在软件根，副本里不放（§9.3 收窄口径），但必须落账
    'kb/tools/kb_lib.py': '# 软件根的冻结工具，不进副本\n',
    'kb/schema/run.schema.json': '{}\n',
    'kb/README.md': '# kb 说明\n',
    'kb/FIXTURE_IDENTITY.md': '# 夹具身份\n',
    'loop/loop_entry.py': '# 软件目录，必须整目录排除\n',
    'SIMLIB_RUN/work/a.log': 'sim log\n',
    '.git/HEAD': 'ref: refs/heads/main\n',
    'COV/cov.dat': 'cov\n',
    'WAVE/w.vcd': 'wave\n',
    'LOG/l.log': 'log\n',
    'RUNS/r.json': '{}\n',
    'PKG/__pycache__/pkg.cpython-311.pyc': 'bytecode\n',
})

EXCLUDED = ('kb/runs', 'loop', 'SIMLIB_RUN', '.git', 'COV', 'WAVE', 'LOG', 'RUNS')
KB_DATA = derive.KB_DATA_DIRS


def _write_tree(root: Path, files: dict) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


@pytest.fixture()
def project(tmp_path):
    """一份"环境根"形状的小基线 + 四个候选 RTL 文件夹 + 可写副本父目录 + S0 记录根。"""
    baseline = tmp_path / 'env'
    _write_tree(baseline, BASELINE_FILES)
    (baseline / 'PKG/empty').mkdir()
    for index in range(40):                       # kb/runs 是重目录：必须整目录排除、不进入 walk
        run = baseline / 'kb/runs' / f'RUN-{index:02d}' / 'view.json'
        run.parent.mkdir(parents=True, exist_ok=True)
        run.write_text('{}\n', encoding='utf-8')
    sandbox_target = baseline / 'kb/runs/RUN-00'
    (baseline / 'doc/sandbox').symlink_to(sandbox_target)
    (baseline / 'TB/top_link.sv').symlink_to('top.sv')        # 相对软链

    incoming = tmp_path / 'incoming'
    _write_tree(incoming / 'identical/RTL', RTL_FILES)
    changed = dict(RTL_FILES)
    changed['SRC/dut.v'] = DUT_V2
    changed['SRC/imports/a.v'] = IMP_V1
    changed['extra.v'] = EXTRA_V
    changed.pop('vendor.v')
    _write_tree(incoming / 'changed/RTL', changed)
    newport = dict(RTL_FILES, **{'SRC/dut.v': DUT_EN})
    _write_tree(incoming / 'newport/RTL', newport)
    # 用户 RTL 文件夹大概率是 git 仓库 + 编辑器缓存：与 copy 同一口径跳过并落账
    git_source = dict(RTL_FILES)
    git_source.update({
        '.git/HEAD': 'ref: refs/heads/main\n',
        '.git/objects/ab/cdef': 'blob\n',
        '__pycache__/dut.cpython-311.pyc': 'bytecode\n',
        'SRC/.svn/entries': 'svn\n',
    })
    _write_tree(incoming / 'git/RTL', git_source)
    # RTL 源里的软链仍按 §2 拒绝（不跳过）
    _write_tree(incoming / 'symlink/RTL', RTL_FILES)
    (incoming / 'symlink/RTL/SRC/link.v').symlink_to('dut.v')
    _write_tree(incoming / 'src/SRC', {
        'dut.v': DUT_V2,
        'imports/a.v': IMP_V1,
        'extra_imp.v': 'module extra_imp(\n    input clk\n);\nendmodule\n',
    })
    _write_tree(incoming / 'design', {'x.v': 'module x;\nendmodule\n'})

    workspaces = tmp_path / 'workspaces'
    workspaces.mkdir()
    store = S0Store(tmp_path / 'state' / 's0', [tmp_path])
    return {
        'baseline': baseline,
        'incoming': incoming,
        'workspaces': workspaces,
        'store': store,
        'tmp': tmp_path,
    }


def _derive(project, source: Path, *, now: str = NOW, payload: dict | None = None):
    data = {'rtl_source': str(source), 'now': now}
    data.update(payload or {})
    return project['store'].prepare_from_rtl(
        data, default_baseline=project['baseline'],
        origin_env_root=project['baseline'], target_parent=project['workspaces'])


# ---------------------------------------------------------------- 根判定（§9.2）

@pytest.mark.parametrize('name,pair', [('RTL', ('RTL', 'RTL')), ('SRC', ('SRC', 'RTL/SRC'))])
def test_classify_rtl_source_accepts_only_rtl_and_src(tmp_path, name, pair):
    (tmp_path / name).mkdir()
    result = derive.classify_rtl_source(tmp_path / name)
    assert result == {'kind': pair[0], 'prefix': pair[1], 'basename': name}


@pytest.mark.parametrize('name', ['rtl', 'src', 'design', 'RTL2', 'SRC_OLD'])
def test_classify_rtl_source_rejects_other_names_and_lists_valid_values(tmp_path, name):
    (tmp_path / name).mkdir()
    with pytest.raises(ValueError) as error:
        derive.classify_rtl_source(tmp_path / name)
    message = str(error.value)
    assert 'RTL' in message and 'SRC' in message       # 文案必须列出合法值（不猜）
    assert derive.RTL_NAME_PREFIX == {'RTL': 'RTL', 'SRC': 'RTL/SRC'}


def test_classify_rtl_source_rejects_non_directory(tmp_path):
    (tmp_path / 'RTL').write_text('not a dir\n', encoding='utf-8')
    with pytest.raises(ValueError):
        derive.classify_rtl_source(tmp_path / 'RTL')


# ---------------------------------------------------------------- 选择性复制（§9.3）

def test_plan_copy_excludes_roots_skips_symlinks_and_keeps_data_subset(project):
    baseline = project['baseline']
    plan = derive.plan_copy(baseline)

    excluded = set(plan['excluded_roots'])
    assert set(EXCLUDED) <= excluded, sorted(excluded)
    assert plan['excluded_roots'] == sorted(plan['excluded_roots'])
    for rel in plan['copied']:
        assert not rel.startswith('kb/runs/'), rel
        assert not rel.startswith('loop/'), rel
        assert not rel.startswith('SIMLIB_RUN/'), rel
        assert not rel.startswith('__pycache__'), rel

    # 数据子集随副本复制（副本自包含：WORKSPACE_ROOT = <work>/kb）
    for rel in ('kb', 'kb/baselines/v0/allfiles.md5', 'kb/index/index.json',
                'kb/conflicts/conflicts.csv', 'kb/adjudication/adjudication.json'):
        assert rel in plan['copied'], rel
    assert 'PKG/empty' in plan['copied'] and 'run' in plan['copied']
    # 裁决 1：kb 下**只有**四个数据子目录随副本复制
    kb_copied = [rel for rel in plan['copied'] if rel == 'kb' or rel.startswith('kb/')]
    assert 'kb' in kb_copied
    for rel in kb_copied:
        assert rel == 'kb' or any(rel == item or rel.startswith(item + '/')
                                  for item in KB_DATA), rel
    declared = {row['rel'] for row in plan['skipped'] if row['reason'] == 'kb_non_data'}
    for rel in ('kb/tools', 'kb/schema', 'kb/README.md', 'kb/FIXTURE_IDENTITY.md'):
        assert rel not in plan['copied'], rel
        assert rel in declared, (rel, declared)          # 不复制但必须落账

    skipped = {row['rel']: row for row in plan['skipped']}
    sandbox = skipped['doc/sandbox']
    assert sandbox['reason'] == 'symlink'
    assert sandbox['target'] == str(baseline / 'kb/runs/RUN-00')     # 只记目标，不跟随
    assert skipped['TB/top_link.sv'] == {'rel': 'TB/top_link.sv', 'reason': 'symlink',
                                         'target': 'top.sv'}
    assert skipped['PKG/__pycache__']['reason'] != 'symlink'
    assert skipped['RTL/.git']['reason'] == 'skip_dir_name'          # 内嵌 git 仓库不复制
    # 软链目标的内容没有被当成本基线条目（不跟随）
    assert not any(rel.startswith('doc/sandbox/') for rel in plan['copied'])
    assert 'kb/runs/RUN-00/view.json' not in plan['copied']


def test_copy_selected_and_manifest_filtered_are_byte_equal(project):
    baseline, work = project['baseline'], project['tmp'] / 'work'
    plan = derive.plan_copy(baseline)
    before = derive.manifest_filtered(baseline, plan)
    work.mkdir()
    counts = derive.copy_selected(baseline, work, plan)

    assert counts == {'copied': len(plan['copied']), 'skipped': len(plan['skipped'])}
    assert derive.manifest_filtered(work, plan) == before        # copy 检查：逐文件 md5 相等
    assert manifest(work) == before                             # 副本里没有额外条目
    assert not (work / 'kb/runs').exists() and not (work / 'loop').exists()
    assert not (work / 'doc/sandbox').exists() and not (work / 'TB/top_link.sv').exists()
    assert (work / 'PKG/empty').is_dir()                        # 空目录也复制
    # 裁决 1：kb 非数据子集不进副本（否则副本里会多一套冻结 tools/schema）
    for rel in ('kb/tools', 'kb/schema', 'kb/README.md', 'kb/FIXTURE_IDENTITY.md'):
        assert not (work / rel).exists(), rel
    assert (work / 'kb/baselines/v0/allfiles.md5').is_file()    # 四个数据子目录在
    assert not (work / 'RTL/.git').exists()                     # 基线内嵌 git 仓库也不复制


def test_manifest_filtered_rejects_unregistered_symlink(project):
    baseline, work = project['baseline'], project['tmp'] / 'work'
    plan = derive.plan_copy(baseline)
    work.mkdir()
    derive.copy_selected(baseline, work, plan)
    (work / 'TB/rogue.sv').symlink_to(baseline / 'TB/top.sv')
    with pytest.raises(ValueError):
        derive.manifest_filtered(work, plan)
    # 基线侧同理：plan 之后凭空多出的软链也必须报错（不能被 filter 静默忽略）
    (baseline / 'TB/rogue2.sv').symlink_to(baseline / 'TB/top.sv')
    with pytest.raises(ValueError):
        derive.manifest_filtered(baseline, plan)


# ---------------------------------------------------------------- RTL 替换（§9.4）

def test_replace_rtl_replaces_rtl_root_entirely(project):
    baseline, work = project['baseline'], project['tmp'] / 'work'
    plan = derive.plan_copy(baseline)
    work.mkdir()
    derive.copy_selected(baseline, work, plan)

    source = project['incoming'] / 'changed/RTL'
    result = derive.replace_rtl(work, source, 'RTL')
    assert result['prefix'] == 'RTL'
    assert 'RTL/vendor.v' in result['replaced']                  # 旧文件被删（零残留）
    assert manifest(work / 'RTL') == manifest(source)
    assert not (work / 'RTL/vendor.v').exists()
    assert (work / 'RTL/extra.v').read_text(encoding='utf-8') == EXTRA_V
    # 非 RTL 部分一字未动
    assert (work / 'TB/top.sv').read_text(encoding='utf-8') == TB_TOP


def test_replace_rtl_src_root_replaces_only_subtree(project):
    baseline, work = project['baseline'], project['tmp'] / 'work'
    plan = derive.plan_copy(baseline)
    work.mkdir()
    derive.copy_selected(baseline, work, plan)

    source = project['incoming'] / 'src/SRC'
    result = derive.replace_rtl(work, source, 'RTL/SRC')
    assert result['prefix'] == 'RTL/SRC'
    assert manifest(work / 'RTL/SRC') == manifest(source)
    assert (work / 'RTL/RTL_COMMON/common.v').read_text(encoding='utf-8') == COMMON_V
    assert (work / 'RTL/vendor.v').read_text(encoding='utf-8') == VENDOR_V
    assert not (work / 'RTL/SRC/extra.v').exists()


def test_replace_rtl_rejects_unknown_prefix(project):
    work = project['tmp'] / 'work'
    work.mkdir()
    with pytest.raises(ValueError):
        derive.replace_rtl(work, project['incoming'] / 'identical/RTL', 'RTL/SRC/imports')


def test_plan_rtl_source_skips_vcs_dirs_and_rejects_symlinks(project):
    """裁决 2：RTL 源的 VCS/缓存目录跳过并落账；软链仍按 §2 拒绝（不跳过）。"""
    source = project['incoming'] / 'git/RTL'
    plan = derive.plan_rtl_source(source)
    assert set(plan) == {'copied', 'skipped'}
    assert {row['rel'] for row in plan['skipped']} == {'.git', '__pycache__', 'SRC/.svn'}
    assert all(row['reason'] == 'skip_dir_name' for row in plan['skipped'])
    for rel in ('.git/HEAD', '.git/objects/ab/cdef',
                '__pycache__/dut.cpython-311.pyc', 'SRC/.svn/entries'):
        assert rel not in plan['copied'], rel
    for rel in ('SRC/dut.v', 'SRC/imports/a.v', 'RTL_COMMON/common.v', 'vendor.v',
                'SRC', 'SRC/imports'):
        assert rel in plan['copied'], rel

    with pytest.raises(ValueError):
        derive.plan_rtl_source(project['incoming'] / 'symlink/RTL')


def test_plan_rtl_source_rejects_special_file(tmp_path):
    source = tmp_path / 'RTL'
    source.mkdir()
    os.mkfifo(source / 'pipe')
    with pytest.raises(ValueError):
        derive.plan_rtl_source(source)


def test_replace_rtl_skips_vcs_dirs_from_source(project):
    baseline, work = project['baseline'], project['tmp'] / 'work'
    plan = derive.plan_copy(baseline)
    work.mkdir()
    derive.copy_selected(baseline, work, plan)

    source = project['incoming'] / 'git/RTL'
    rtl_plan = derive.plan_rtl_source(source)
    derive.replace_rtl(work, source, 'RTL')
    assert derive.manifest_filtered(work / 'RTL', rtl_plan) == \
        derive.manifest_filtered(source, rtl_plan)
    for rel in ('.git', '__pycache__', 'SRC/.svn'):
        assert not (work / 'RTL' / rel).exists(), rel
    assert (work / 'RTL/SRC/dut.v').is_file()


# ---------------------------------------------------------------- 错目录只告警（§9.4）

def test_folder_warning_counts_same_added_removed(project):
    baseline = project['baseline']
    plan = derive.plan_copy(baseline)
    changed = derive.folder_warning(baseline, plan, project['incoming'] / 'changed/RTL', 'RTL')
    # 基线 4 个文件；新目录：a.v/common.v 逐字节相同，dut.v 改了内容，extra.v 新增，vendor.v 消失
    # 并集 = {SRC/dut.v, SRC/imports/a.v, RTL_COMMON/common.v, vendor.v, extra.v}
    assert changed == {'same': 2, 'added': 1, 'removed': 1, 'ratio': 0.4}
    identical = derive.folder_warning(baseline, plan,
                                     project['incoming'] / 'identical/RTL', 'RTL')
    assert identical == {'same': 4, 'added': 0, 'removed': 0, 'ratio': 1.0}
    # 裁决 2：RTL 源的 .git/__pycache__ 不参与统计（口径唯一）⇒ 仍与 identical 一样是 1.0
    git_source = derive.folder_warning(baseline, plan, project['incoming'] / 'git/RTL', 'RTL')
    assert git_source == {'same': 4, 'added': 0, 'removed': 0, 'ratio': 1.0}
    src = derive.folder_warning(baseline, plan, project['incoming'] / 'src/SRC', 'RTL/SRC')
    # 子树文件：基线 {dut.v, imports/a.v}；新目录 {dut.v(改), imports/a.v, extra_imp.v} ⇒ 并集 3
    assert src == {'same': 1, 'added': 1, 'removed': 0, 'ratio': 0.3333}


# ---------------------------------------------------------------- prepare_from_rtl（§9.1/§9.5）

def test_prepare_from_rtl_records_derivation_fields(project):
    record = _derive(project, project['incoming'] / 'identical/RTL')
    baseline, workspaces = project['baseline'], Path(project['workspaces'])
    work = Path(record['work_env'])

    assert record['status'] == 'prepared'
    assert record['entry'] == 'rtl_folder'
    assert record['origin_env_root'] == str(baseline)
    assert record['rtl_prefix'] == 'RTL'
    assert record['baseline_version'] == 'RTL@RTL+20261030T120000Z'   # 操作者声明，不伪装 commit
    assert work.parent == workspaces and work.name.startswith('env-derived-')
    assert record['smoke_case'] == 'tc_a'                              # sorted(TESTLIB/*.sv)[0] 的 stem
    assert record['auto'] == {'phase': 'ready'}
    assert record['auto']['phase'] in AUTO_PHASES               # 冻结枚举只有一份定义
    assert record['ready_for_execution'] is False                       # smoke 还没跑
    assert set(record['folder_warning']) == {'same', 'added', 'removed', 'ratio'}
    assert record['folder_warning']['same'] == 4
    assert 'kb/runs' in record['copy_plan']['excluded_roots']
    assert any(row['rel'] == 'doc/sandbox' for row in record['copy_plan']['skipped'])
    # 裁决 1：kb 只复制四个数据子目录，其余落在 copy_plan.skipped（kb_non_data）
    assert [row['rel'] for row in record['copy_plan']['skipped']
            if row['reason'] == 'kb_non_data']
    assert record['rtl_plan']['skipped'] == []                 # 裁决 2 新字段：无 VCS 目录时为空
    assert {check['key']: check['status'] for check in record['checks']} == dict(
        copy='passed', rtl='passed', non_rtl='passed',
        ports='passed', smoke='waiting', baseline='passed')

    # 副本：RTL 整棵换成新 RTL；数据子集在；重目录/软链/kb 非数据子集不在
    assert manifest(work / 'RTL') == manifest(project['incoming'] / 'identical/RTL')
    assert (work / 'kb/baselines/v0/allfiles.md5').is_file()
    assert (work / 'kb/adjudication/adjudication.json').is_file()
    assert not (work / 'kb/runs').exists()
    assert not (work / 'kb/tools').exists() and not (work / 'kb/schema').exists()
    assert not (work / 'doc/sandbox').exists()
    folder = project['store'].root / record['id']
    assert (folder / 'baseline-before.json').read_bytes() == \
        (folder / 'baseline-after.json').read_bytes()                   # 基线零写入见证
    report = (folder / 'reports/s0-env/env-check-report.md').read_text(encoding='utf-8')
    assert 'rtl_folder' in report or '单一 RTL 文件夹' in report
    assert 'doc/sandbox' in report


def test_prepare_from_rtl_skips_vcs_dirs_in_rtl_source(project):
    """裁决 2：RTL 源里的 `.git`/`__pycache__`/`.svn` 不复制、落 `rtl_plan`，且 rtl 检查用同一口径。"""
    record = _derive(project, project['incoming'] / 'git/RTL')
    work = Path(record['work_env'])

    assert record['rtl_plan']['skipped'] and all(
        row['reason'] == 'skip_dir_name' for row in record['rtl_plan']['skipped'])
    assert {row['rel'] for row in record['rtl_plan']['skipped']} == {'.git', '__pycache__',
                                                                    'SRC/.svn'}
    assert record['folder_warning'] == {'same': 4, 'added': 0, 'removed': 0, 'ratio': 1.0}
    checks = {check['key']: check['status'] for check in record['checks']}
    assert checks['rtl'] == 'passed' and checks['non_rtl'] == 'passed'
    for rel in ('.git', '__pycache__', 'SRC/.svn'):
        assert not (work / 'RTL' / rel).exists(), rel
    assert (work / 'RTL/SRC/dut.v').is_file()
    folder = project['store'].root / record['id']
    assert json.loads((folder / 'rtl-source.json').read_text(encoding='utf-8')) == \
        derive.manifest_filtered(project['incoming'] / 'git/RTL', record['rtl_plan'])
    report = (folder / 'reports/s0-env/env-check-report.md').read_text(encoding='utf-8')
    assert 'RTL 源跳过条目' in report and '.git' in report
    # 漂移核验也用过滤后源清单：get() 不得把被跳过的 .git 当成漂移
    fresh = project['store'].get(record['id'])
    assert fresh['status'] == 'prepared' and fresh['verification']['drift'] == {}
    assert fresh['rtl_plan'] == record['rtl_plan']


def test_prepare_from_rtl_rejects_symlink_in_rtl_source(project):
    """§2：RTL 源里的软链不跳过、直接拒绝；拒绝发生在写盘之前。"""
    with pytest.raises(ValueError) as error:
        _derive(project, project['incoming'] / 'symlink/RTL')
    assert '符号链接' in str(error.value)
    root = project['store'].root
    assert not root.exists() or not list(root.glob('S0-*'))
    assert not list(project['workspaces'].iterdir())


def test_prepare_from_rtl_src_root_keeps_other_rtl(project):
    record = _derive(project, project['incoming'] / 'src/SRC')
    work = Path(record['work_env'])
    source = project['incoming'] / 'src/SRC'
    assert record['rtl_prefix'] == 'RTL/SRC'
    assert record['folder_warning']['same'] == 1
    assert manifest(work / 'RTL/SRC') == manifest(source)
    assert (work / 'RTL/RTL_COMMON/common.v').read_text(encoding='utf-8') == COMMON_V
    assert (work / 'RTL/vendor.v').read_text(encoding='utf-8') == VENDOR_V
    checks = {check['key']: check['status'] for check in record['checks']}
    assert checks['rtl'] == 'passed' and checks['non_rtl'] == 'passed'


def test_prepare_from_rtl_src_root_detects_tampered_other_rtl(project, monkeypatch):
    """SRC 根只允许换子树；顺手改 `RTL/` 其它部分 ⇒ rtl 检查 failed（不静默放过）。"""
    real_replace = derive.replace_rtl

    def tampered(work, rtl_source, prefix):
        result = real_replace(work, rtl_source, prefix)
        (Path(work) / 'RTL/RTL_COMMON/common.v').write_text('// 顺手改了 vendor\n', encoding='utf-8')
        return result

    monkeypatch.setattr(derive, 'replace_rtl', tampered)
    with pytest.raises(PreparationFailed) as error:
        _derive(project, project['incoming'] / 'src/SRC')
    record = error.value.record
    assert record['status'] == 'failed'
    assert record['auto'] == {'phase': 'failed'}            # 阶段回执：失败即 failed
    assert record['auto']['phase'] in AUTO_PHASES
    assert 'SRC' in record['error'] or '其余' in record['error']
    saved = json.loads((project['store'].root / record['id'] / 'record.json').read_text(
        encoding='utf-8'))
    assert saved['status'] == 'failed' and saved['error'] == record['error']


def test_prepare_from_rtl_failure_keeps_copy_and_failed_record(project, monkeypatch):
    def broken(work, rtl_source, prefix):
        raise OSError('磁盘已满：替换失败')

    monkeypatch.setattr(derive, 'replace_rtl', broken)
    with pytest.raises(PreparationFailed) as error:
        _derive(project, project['incoming'] / 'identical/RTL')
    record = error.value.record
    assert record['status'] == 'failed'
    assert record['error'] == '磁盘已满：替换失败'          # error 原文，不吞异常换默认值
    assert record['partial_work_owned'] is True
    work = Path(record['work_env'])
    assert (work / 'RTL/SRC/dut.v').is_file()                # 部分副本保留，不删除
    assert (work / 'kb/baselines/v0/allfiles.md5').is_file()
    folder = project['store'].root / record['id']
    saved = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    assert saved['status'] == 'failed' and saved['error'] == record['error']
    assert (folder / 'baseline-before.json').read_bytes() == \
        (folder / 'baseline-after.json').read_bytes()


def test_prepare_from_rtl_requires_smoke_case_when_testlib_has_no_sv(project):
    for path in (project['baseline'] / 'TESTLIB').glob('*.sv'):
        path.unlink()
    with pytest.raises(ValueError) as error:
        _derive(project, project['incoming'] / 'identical/RTL')
    assert 'smoke_case' in str(error.value)
    root = project['store'].root
    assert not root.exists() or not list(root.glob('S0-*'))     # 拒绝发生在写盘之前


def test_prepare_from_rtl_rejects_unknown_source_folder_name(project):
    with pytest.raises(ValueError) as error:
        _derive(project, project['incoming'] / 'design')
    message = str(error.value)
    assert 'RTL' in message and 'SRC' in message
    root = project['store'].root
    assert not root.exists() or not list(root.glob('S0-*'))
    assert not list(project['workspaces'].iterdir())


def test_prepare_from_rtl_accepts_explicit_work_env(project):
    work = project['tmp'] / 'hand-picked-work'
    record = _derive(project, project['incoming'] / 'identical/RTL',
                     payload={'work_env': str(work), 'baseline_version': 'operator:v9',
                              'smoke_case': 'tc_b'})
    assert record['work_env'] == str(work)
    assert record['baseline_version'] == 'operator:v9'
    assert record['smoke_case'] == 'tc_b'
    assert work.is_dir()


def test_prepare_from_rtl_refuses_existing_target(project):
    """副本每次新建并保留：同名（同一 now ⇒ 同一缺省路径）再来一次必须拒绝，不覆盖上一次。"""
    first = _derive(project, project['incoming'] / 'identical/RTL')
    before = (project['store'].root / first['id'] / 'record.json').read_bytes()
    with pytest.raises(FileExistsError):
        _derive(project, project['incoming'] / 'identical/RTL')
    assert (project['store'].root / first['id'] / 'record.json').read_bytes() == before
    # 换一个 now ⇒ 新副本路径，可正常派生
    second = _derive(project, project['incoming'] / 'identical/RTL', now=LATER)
    assert second['id'] != first['id'] and second['work_env'] != first['work_env']


# ---------------------------------------------------------------- advance（§9.5）

def test_advance_refuses_smoke_before_ports_pass(project, monkeypatch):
    record = _derive(project, project['incoming'] / 'newport/RTL')
    checks = {check['key']: check['status'] for check in record['checks']}
    assert checks['ports'] == 'waiting' and checks['copy'] == 'passed'
    assert record['auto'] == {'phase': 'awaiting_ports'}     # 停在"待确认端口"
    assert record['auto']['phase'] in AUTO_PHASES

    def explode(*args, **kwargs):
        raise AssertionError('ports 未 passed 时不得冒烟')

    monkeypatch.setattr(s0b, 'run_smoke', explode)
    with pytest.raises(ValueError):
        project['store'].advance(record['id'])
    folder = project['store'].root / record['id']
    assert not (folder / 'smoke.json').exists()
    saved = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    assert saved['smoke'] is None


def test_advance_smokes_once_and_flips_ready(project, monkeypatch):
    record = _derive(project, project['incoming'] / 'identical/RTL')
    assert {check['key']: check['status'] for check in record['checks']}['ports'] == 'passed'
    calls = []

    def fake_smoke(record, folder, case, run_id=None, now=None):
        calls.append({'case': case, 'run_id': run_id, 'now': now, 'work_env': record['work_env']})
        return {'status': 'passed', 'reason': '', 'at': '2026-10-30T12:00:02+00:00', 'case': case,
                'warning_delta': {'added': [], 'removed': [], 'count_increase': [],
                                  'needs_evaluation': []}}

    monkeypatch.setattr(s0b, 'run_smoke', fake_smoke)
    fresh = project['store'].advance(record['id'], now='2026-10-30T12:00:02+00:00')

    assert len(calls) == 1
    assert calls[0]['case'] == 'tc_a' and calls[0]['run_id'] == record['id']
    assert calls[0]['now'] == '2026-10-30T12:00:02+00:00'
    assert fresh['smoke']['status'] == 'passed'
    assert {check['key']: check['status'] for check in fresh['checks']}['smoke'] == 'passed'
    assert fresh['ready_for_execution'] is True                  # 六项全 passed 且无漂移
    assert fresh['auto'] == {'phase': 'ready'}
    folder = project['store'].root / record['id']
    assert json.loads((folder / 'smoke.json').read_text(encoding='utf-8'))['status'] == 'passed'
    saved = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    assert saved['smoke']['status'] == 'passed' and saved['smoke_case'] == 'tc_a'
    assert project['store'].get(record['id'])['ready_for_execution'] is True


def test_advance_uses_explicit_smoke_case(project, monkeypatch):
    record = _derive(project, project['incoming'] / 'identical/RTL')
    seen = {}

    def fake_smoke(record, folder, case, run_id=None, now=None):
        seen['case'] = case
        return {'status': 'waiting', 'reason': 'PATH 里没有 uvlan（EDA 未装/未 source），未执行冒烟'}

    monkeypatch.setattr(s0b, 'run_smoke', fake_smoke)
    fresh = project['store'].advance(record['id'], smoke_case='tc_b')
    assert seen['case'] == 'tc_b'
    assert fresh['smoke_case'] == 'tc_b'
    # uvlan 不可用 ⇒ smoke=waiting（§9.7：不冒充 passed，不切换）
    assert {check['key']: check['status'] for check in fresh['checks']}['smoke'] == 'waiting'
    assert fresh['ready_for_execution'] is False


# ---------------------------------------------------------------- 只读投影 / legacy 不回归

def test_get_projects_env_switch_json_read_only(project):
    record = _derive(project, project['incoming'] / 'identical/RTL')
    assert 'env_switch' not in record
    folder = project['store'].root / record['id']
    switch = {'status': 'active', 'target_env_root': record['work_env'],
              'origin_env_root': record['origin_env_root']}
    (folder / 'env-switch.json').write_text(json.dumps(switch), encoding='utf-8')
    fresh = project['store'].get(record['id'])
    assert fresh['env_switch'] == switch
    # 只读投影：本切片不写、不改这个文件
    assert json.loads((folder / 'env-switch.json').read_text(encoding='utf-8')) == switch


def test_legacy_prepare_record_has_no_rtl_folder_fields(tmp_path):
    baseline = tmp_path / 'legacy'
    for name in ('RTL', 'TB', 'PKG', 'TESTLIB', 'docs'):
        (baseline / name).mkdir(parents=True)
        (baseline / name / 'kept.txt').write_text(name, encoding='utf-8')
    (baseline / 'TB/top.sv').write_text('module top; endmodule\n', encoding='utf-8')
    (baseline / 'run').write_text('#!/bin/sh\nexit 99\n', encoding='utf-8')
    rtl = tmp_path / 'src/rtl'
    rtl.mkdir(parents=True)
    (rtl / 'new.sv').write_text('module dut; endmodule\n', encoding='utf-8')
    store = S0Store(tmp_path / 'records', [tmp_path])
    record = store.prepare(dict(baseline=str(baseline), baseline_version='v1',
                                rtl_source=str(rtl), work_env=str(tmp_path / 'work'), now=NOW))

    for key in ('entry', 'origin_env_root', 'rtl_prefix', 'copy_plan',
                'folder_warning', 'smoke_case', 'auto'):
        assert key not in record, key                                 # 新字段只增给 from-rtl 记录
    assert {check['key']: check['status'] for check in record['checks']} == dict(
        copy='passed', rtl='passed', non_rtl='passed',
        ports='waiting', smoke='waiting', baseline='passed')
    folder = store.root / record['id']
    assert manifest(baseline) == json.loads((folder / 'baseline-before.json').read_text(
        encoding='utf-8'))                                            # 仍是**全量**清单
    assert (folder / 'baseline-before.json').read_bytes() == (folder / 'baseline-after.json').read_bytes()
    fresh = store.get(record['id'])
    assert 'env_switch' not in fresh
