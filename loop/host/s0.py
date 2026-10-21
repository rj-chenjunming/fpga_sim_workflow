"""S0-a 的确定性派生与只读核验；不执行基线脚本，不宣称 S0-b 通过。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path


class PreparationFailed(RuntimeError):
    def __init__(self, record):
        super().__init__(record['error'])
        self.record = record


def _read_regular(path: Path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, 'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError(f'拒绝特殊文件：{path}')
    return stream


def manifest(root: Path) -> dict:
    """目录也入清单；拒绝软链，不跟随可能指回基线的链接。"""
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f'不是独立实体目录：{root}')
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'拒绝符号链接：{path}')
        key = path.relative_to(root).as_posix()
        if path.is_dir():
            result[key] = {'kind': 'directory'}
        else:
            with _read_regular(path) as stream:
                result[key] = {'kind': 'file', 'md5': hashlib.file_digest(stream, 'md5').hexdigest()}
    return result


def _copy_regular(src, dst):
    with _read_regular(Path(src)) as source, open(dst, 'xb') as target:
        shutil.copyfileobj(source, target)
    shutil.copystat(src, dst, follow_symlinks=False)
    return dst


def _json(path: Path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write('\n')


def _overlap(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def _changes(before, after):
    return [key for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)]


def _without_rtl(snapshot):
    return {k: v for k, v in snapshot.items() if k != 'RTL' and not k.startswith('RTL/')}


S0B_BLOCKERS = [
    {'key': 'ports', 'message': 'S0-b：外部接口差异核对、TB/top.sv 适配与逐 hunk 登记尚未接入。'},
    {'key': 'smoke', 'message': 'S0-b：副本内真实三库冒烟尚未执行，缺少每库日志、error/warning 计数与评估。'},
    {'key': 'execution', 'message': '新版执行入口尚未接入 S0 准出判据；现有闭环不代表新版 S3。'},
]


class S0Store:
    def __init__(self, root: Path, allowed_roots):
        self.root = Path(root).resolve()
        self.allowed_roots = [Path(p).resolve() for p in allowed_roots]

    def _path(self, value) -> Path:
        if not isinstance(value, str) or not value.strip() or not Path(value).is_absolute():
            raise ValueError('请提供非空绝对路径')
        raw = Path(value)
        if any(p.is_symlink() for p in (raw, *raw.parents)):
            raise ValueError(f'路径中不允许符号链接：{raw}')
        path = raw.resolve()
        if not any(path == root or root in path.parents for root in self.allowed_roots):
            raise PermissionError(f'路径不在服务端允许根内：{value}')
        return path

    def _folder(self, record_id):
        if not re.fullmatch(r'S0-[A-Za-z0-9_-]+', record_id):
            raise ValueError('非法 S0 记录 ID')
        folder = self.root / record_id
        if folder.is_symlink():
            raise ValueError('记录目录不允许符号链接')
        return folder

    def list(self):
        records = []
        for path in sorted(self.root.glob('S0-*/record.json'), reverse=True):
            if path.parent.is_symlink() or path.is_symlink():
                continue
            row = json.loads(path.read_text(encoding='utf-8'))
            records.append({k: row.get(k) for k in ('id', 'status', 'work_env', 'created_at', 'baseline_version')})
        return records

    def prepare(self, payload: dict):
        baseline = self._path(payload.get('baseline'))
        rtl = self._path(payload.get('rtl_source'))
        work = self._path(payload.get('work_env'))
        version = payload.get('baseline_version')
        if not isinstance(version, str) or not version.strip() or '\n' in version:
            raise ValueError('必须填写单行基线版本标识（操作者声明）')
        if any(_overlap(a, b) for a, b in ((baseline, rtl), (baseline, work), (rtl, work),
                                          (self.root, baseline), (self.root, rtl), (self.root, work))):
            raise ValueError('基线、新 RTL、副本和准备记录必须是互不包含的独立目录')
        if work.exists():
            raise FileExistsError(f'目标已存在，不会覆盖：{work}')
        if not work.parent.is_dir():
            raise ValueError('副本父目录必须预先存在')
        for part in ('RTL', 'TB', 'PKG', 'TESTLIB'):
            if not (baseline / part).is_dir():
                raise ValueError(f'基线缺少目录：{part}')
        docs = 'docs' if (baseline / 'docs').is_dir() else 'doc'
        if not (baseline / docs).is_dir() or not (baseline / 'run').is_file() or not (baseline / 'TB/top.sv').is_file():
            raise ValueError('基线需含 docs/（兼容 doc/）、run 和 TB/top.sv')
        before, source = manifest(baseline), manifest(rtl)
        if not any(v['kind'] == 'file' for v in source.values()):
            raise ValueError('新 RTL 目录为空')
        now = payload.get('now')
        if now is not None:
            try:
                stamp = datetime.fromisoformat(now.replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    raise ValueError('缺少时区')
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError('now 必须为含时区的 ISO 时间') from exc
        else:
            stamp = datetime.now(timezone.utc)
        record_id = 'S0-' + stamp.strftime('%Y%m%dT%H%M%S%f') + '-' + hashlib.sha256(str(work).encode()).hexdigest()[:10]
        folder = self._folder(record_id)
        folder.mkdir(parents=True, exist_ok=False)
        checks = [dict(key=k, label=label, status='waiting') for k, label in (
            ('copy', '完整派生工作副本'), ('rtl', '新版 RTL 整体替换'), ('non_rtl', '非 RTL 初检一致'),
            ('ports', '接口核对与 TB 变更登记'), ('smoke', '副本三库编译冒烟'), ('baseline', '基线零写入见证'))]
        record = dict(id=record_id, baseline=str(baseline), baseline_version=version.strip(),
                      rtl_source=str(rtl), work_env=str(work), created_at=stamp.isoformat(), docs_dir=docs,
                      status='preparing', ready_for_execution=False, checks=checks,
                      blockers=S0B_BLOCKERS, error=None, report_url=f'/api/s0/{record_id}/report')
        _json(folder / 'baseline-before.json', before)
        _json(folder / 'rtl-source.json', source)
        owned_work = False
        try:
            # mkdir 是独占目标的原子步骤；copytree 只能写本次刚取得的目录。
            work.mkdir(exist_ok=False)
            owned_work = True
            shutil.copytree(baseline, work, dirs_exist_ok=True, copy_function=_copy_regular)
            checks[0]['status'] = 'passed'
            # copytree 继承基线的只读目录权限；只在本次新副本上取得删除旧 RTL 的权限。
            for directory in [work, work / 'RTL', *(p for p in (work / 'RTL').rglob('*') if p.is_dir())]:
                if directory.is_symlink():
                    raise ValueError(f'副本目录出现符号链接：{directory}')
                directory.chmod(stat.S_IMODE(directory.stat().st_mode) | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            shutil.rmtree(work / 'RTL')
            shutil.copytree(rtl, work / 'RTL', copy_function=_copy_regular)
            copied = manifest(work)
            if manifest(work / 'RTL') != source or manifest(rtl) != source:
                raise ValueError('RTL 内容不一致或复制期间源发生变化')
            checks[1]['status'] = 'passed'
            if _without_rtl(copied) != _without_rtl(before):
                raise ValueError('非 RTL 目录发生污染，必须重新派生')
            checks[2]['status'] = 'passed'
            _json(folder / 'work-after.json', copied)
            (folder / 'design-context.yaml').write_text(
                'sim_verification:\n  work_env: ' + json.dumps(str(work), ensure_ascii=False) + '\n', encoding='utf-8')
            record['status'] = 'prepared'
        except (OSError, ValueError, shutil.Error) as exc:
            record['status'], record['error'] = 'failed', str(exc)
            # 与输入校验后外部抢占目标的情况区分，不宣称已取得别人目录。
            record['partial_work_owned'] = owned_work
        finally:
            try:
                after = manifest(baseline)
                _json(folder / 'baseline-after.json', after)
                if after != before:
                    raise ValueError('基线指纹变化：停止并排查，不能准出')
                checks[5]['status'] = 'passed'
            except (OSError, ValueError) as exc:
                checks[5]['status'] = 'failed'
                record['status'], record['error'] = 'failed', str(exc)
            try:
                self._write_report(folder, record)
            except OSError as exc:
                record['status'], record['error'] = 'failed', f'准备报告写入失败：{exc}'
            _json(folder / 'record.json', record)
        if record['status'] == 'failed':
            raise PreparationFailed(record)
        return record

    def _write_report(self, folder, record):
        report = folder / 'reports/s0-env'
        report.mkdir(parents=True)
        rows = ['# S0 环境准备记录', '', 'S0-a 完成不代表 S0 准出；S0-b 未执行。', '']
        for key in ('id', 'baseline', 'baseline_version', 'rtl_source', 'work_env', 'created_at', 'status', 'error'):
            rows.append(f'- {key}: {record[key]}')
        rows += ['', '版本标识为操作者声明，未校验为 Git ref。', '', '## 检查', '']
        rows += [f'- {c["label"]}: {c["status"]}' for c in record['checks']]
        rows += ['', '## 指纹文件', '', '完整清单位于本记录目录：baseline-before.json、baseline-after.json、rtl-source.json、work-after.json（成功时）。',
                 '', '## 阻断项', '']
        rows += ['- ' + b['message'] for b in record['blockers']]
        rows += ['', '## TB 变更登记表', '', '未执行接口核对，未改写 TB；空表不代表无接口变化。', '',
                 '| 编号 | 接口差异来源 | 位置/原片段 | 真实 diff | 授权范围 | 影响用例 | 复核状态 |',
                 '|---|---|---|---|---|---|---|', '']
        (report / 'env-check-report.md').write_text('\n'.join(rows), encoding='utf-8')

    def get(self, record_id):
        folder = self._folder(record_id)
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        drift, errors = {}, []
        if record['status'] == 'prepared':
            for name in ('reports/s0-env/env-check-report.md', 'design-context.yaml'):
                if not (folder / name).is_file():
                    errors.append(f'准备产物缺失：{name}')
            def compare(label, path, filename, assets=False):
                try:
                    current = manifest(self._path(path))
                    old = json.loads((folder / filename).read_text(encoding='utf-8'))
                    if assets:
                        roots = {'RTL', 'TB', 'PKG', 'TESTLIB', record['docs_dir'], 'run'}
                        current = {k: v for k, v in current.items() if k.split('/')[0] in roots}
                        old = {k: v for k, v in old.items() if k.split('/')[0] in roots}
                    changed = _changes(old, current)
                    if changed:
                        drift[label] = changed
                except (OSError, ValueError) as exc:
                    errors.append(f'{label}: {exc}')
            compare('baseline', record['baseline'], 'baseline-before.json')
            compare('rtl_source', record['rtl_source'], 'rtl-source.json')
            compare('work_env', record['work_env'], 'work-after.json', assets=True)
        record['verification'] = {'drift': drift, 'errors': errors}
        if drift or errors:
            record['status'] = 'failed'
            record['error'] = '当前内容偏离派生时见证；原始准备记录保持不变'
        record['ready_for_execution'] = False
        return record

    def report_path(self, record_id):
        return self._folder(record_id) / 'reports/s0-env/env-check-report.md'
