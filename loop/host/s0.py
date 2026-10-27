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

from host import s0b


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

# ---------------------------------------------------------------- S0-rehearsal（SPEC-05 §6.2/§7）
#
# 演练 = 本机自造一份**一次性小基线**，走一次真实的 copy → 整体替换 RTL → 核验。
# 它只证明"链路能走通"，不证明环境就绪、不证明 S0-b、不签任何闸门。

REHEARSAL_NOTE = '演练：只证明 copy→replace→核验链路，不是环境就绪、不是 S0-b。'

#: 演练输入（相对演练根）。`RTL/legacy.v` 只存在于基线，用来证明"整体替换"而非"覆盖合并"。
REHEARSAL_FILES = {
    'baseline/RTL/old.v': 'module old;\n  // 基线旧 RTL\nendmodule\n',
    'baseline/RTL/legacy.v': 'module legacy;\n  // 只在基线里存在；整体替换后必须消失\nendmodule\n',
    'baseline/TB/top.sv': 'module top;\n  old u_old();\nendmodule\n',
    'baseline/PKG/x.v': 'package x;\nendpackage\n',
    'baseline/TESTLIB/tc_demo.sv': 'module tc_demo;\nendmodule\n',
    'baseline/doc/S0_REHEARSAL.md': '# 演练基线（临时）\n\n只用于 S0-rehearsal，不是真实工程。\n',
    'baseline/run': '#!/bin/sh\n# 演练基线里的 run 文件；只复制不执行\nexit 99\n',
    'rtl/old.v': 'module old;\n  // 演练：整体替换后的新版 RTL\nendmodule\n',
    'rtl/new.v': 'module new;\nendmodule\n',
}


def _parse_now(value):
    """`now` 是唯一的时间注入入口；缺省取当前 UTC。非法/无时区一律 ValueError。"""
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, str):
        raise ValueError('now 必须为含时区的 ISO 时间')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('now 必须为含时区的 ISO 时间') from exc
    if stamp.tzinfo is None:
        raise ValueError('now 必须为含时区的 ISO 时间')
    return stamp


def _unique_dir(parent: Path, name: str) -> Path:
    """独占创建一层新目录；同名已存在则加序号，绝不覆盖上一次演练。"""
    if parent.is_symlink():
        raise ValueError(f'演练目录不允许符号链接：{parent}')
    parent.mkdir(parents=True, exist_ok=True)
    candidate, index = parent / name, 0
    while candidate.exists() or candidate.is_symlink():
        index += 1
        candidate = parent / f'{name}-{index}'
    candidate.mkdir(exist_ok=False)
    return candidate


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

    def prepare(self, payload: dict, extra: dict | None = None):
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
        if not (baseline / docs).is_dir():
            raise ValueError('基线需含 docs/（兼容 doc/）')
        # 运行入口：契约原写 `run` 文件，真实环境是 run_tc.py / run_uvs_new.sh / doc/tools/run_local.sh
        # ⇒ 由 resolve_run_entry 确定性解析（只复制、不执行）。
        run_entry = s0b.resolve_run_entry(baseline)
        # TB 顶层文件：契约原写 TB/top.sv，真实环境里只有 TB/tbtop.sv ⇒ 由编译驱动决定（STATUS §101）。
        tb_top = s0b.resolve_tb_top(baseline)
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
                      tb_top=tb_top, run_entry=run_entry, status='preparing', ready_for_execution=False, checks=checks,
                      ports=None, smoke=None, blockers=S0B_BLOCKERS, error=None,
                      report_url=f'/api/s0/{record_id}/report')
        if extra:
            # 附加标记只允许新增字段（如演练标记）；覆盖既有字段会让记录自相矛盾。
            clash = sorted(set(extra) & set(record))
            if clash:
                raise ValueError(f'附加标记不得覆盖记录字段：{"、".join(clash)}')
            record.update(extra)
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
            # S0-b：派生 + 提议/确认终态核验（fail-closed：算不出来就 waiting，不冒充 passed）
            try:
                ports = s0b.evaluate_ports(record, folder)
            except (OSError, ValueError) as exc:
                ports = {'status': 'failed', 'reason': f'接口派生失败：{exc}', 'evidence': {}, 'table': [], 'derive': {}}
            record['ports'] = ports
            checks[3]['status'] = ports['status']
            checks[3]['reason'] = ports.get('reason', '')
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

    def rehearse(self, now=None):
        """S0-rehearsal：自造一次性小基线 → 完整派生 → 四项 checks；不接受任何客户端路径。

        - 输入/副本都落在**软件 state 目录**下：`<state>/s0-rehearsal/<UTC 戳>/`；
          记录仍写 `<state>/s0/`（与真实 S0 记录同源）。输入不能放进记录根内
          （§2 禁止输入/记录互相包含），所以是记录根的**兄弟目录**。
        - 每次都新建目录、新记录；同名戳自动加序号，绝不覆盖上一次演练。
        - `ENV_ROOT` 零写入：本方法不解析、不引用环境根。
        - `ready_for_execution` 仍恒 false：演练不签闸门、不改变 S0-b 阻断（§3）。
        """
        stamp = _parse_now(now)
        utc = stamp.astimezone(timezone.utc)
        stage = _unique_dir(self.root.parent / 's0-rehearsal', utc.strftime('%Y%m%dT%H%M%S%fZ'))
        baseline, source, work = stage / 'baseline', stage / 'rtl', stage / 'work'
        extra = {'rehearsal': {'kind': 'S0-rehearsal', 'note': REHEARSAL_NOTE,
                               'fixture_root': str(stage), 'baseline': str(baseline),
                               'rtl_source': str(source), 'work_env': str(work),
                               'created_at': stamp.isoformat()}}
        for relative, text in REHEARSAL_FILES.items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')
        payload = dict(baseline=str(baseline),
                       baseline_version='S0-rehearsal:' + utc.isoformat(timespec='seconds'),
                       rtl_source=str(source), work_env=str(work), now=stamp.isoformat())
        # 失败按既有语义抛 PreparationFailed（记录 status=failed + error，API 422）；
        # 演练标记随 record.json 一次写入，失败记录同样带标记。
        return self.prepare(payload, extra=extra)

    def _write_report(self, folder, record):
        report = folder / 'reports/s0-env'
        report.mkdir(parents=True, exist_ok=True)   # apply/smoke 后会重写报告；不可因目录已存在而失败
        s0b_all = bool(record.get('checks')) and all(
            c['status'] == 'passed' for c in (record.get('checks') or []))
        header = ('S0-a 完成不代表 S0 准出；S0-b 已全部完成（六项 passed，可准出）。'
                  if s0b_all else 'S0-a 完成不代表 S0 准出；S0-b 未执行或未完成（见下表）。')
        rows = ['# S0 环境准备记录', '', header, '']
        if record.get('rehearsal'):
            rows += ['> **演练记录（S0-rehearsal）**：只证明 copy→replace→核验链路，不是环境就绪、不是 S0-b。',
                     '> 基线是软件 state 下的一次性小基线；真实环境（S0-real）未跑。', '']
        for key in ('id', 'baseline', 'baseline_version', 'rtl_source', 'work_env', 'created_at', 'status', 'error'):
            rows.append(f'- {key}: {record.get(key)}')   # 记录可能不完整（伪造/早期失败）⇒ 不抛 KeyError
        rows += ['', '版本标识为操作者声明，未校验为 Git ref。', '', '## 检查', '']
        rows += [f'- {c["label"]}: {c["status"]}' for c in (record.get('checks') or [])]
        rows += ['', '## 指纹文件', '', '完整清单位于本记录目录：baseline-before.json、baseline-after.json、'
                 'rtl-source.json、work-after*.json（成功后，每次授权落盘追加一份）。',
                 '', '## 阻断项（按当前状态计算）', '']
        blocked = [(c['key'], c.get('label', c['key']), c['status'], c.get('reason') or '')
                   for c in (record.get('checks') or []) if c.get('status') != 'passed']
        if blocked:
            rows += [f'- {key}（{label}）：{status}' + (f' — {reason}' if reason else '')
                     for key, label, status, reason in blocked]
        else:
            rows += ['- 无（六项检查全部 passed）']
        if not record.get('ready_for_execution'):
            rows += ['- execution：新版执行入口尚未放行（六项未全 passed，或存在漂移/错误）']
        rows += ['', '## TB 变更登记表', '']
        ports = record.get('ports') or {}
        if ports.get('table'):
            rows += ['| 编号 | 模块 | 差异 | 复核状态 |', '|---|---|---|---|']
            decisions = {}
            try:
                decisions = s0b.decisions_of(folder)
            except (OSError, ValueError):
                decisions = {}
            for index, row in enumerate(ports['table'], 1):
                detail = []
                if row.get('added'):
                    detail.append('新增 ' + '、'.join(row['added']))
                if row.get('removed'):
                    detail.append('删除 ' + '、'.join(row['removed']))
                if row.get('changed'):
                    detail.append('变更 ' + '、'.join(row['changed']))
                if row['kind'] != 'module':
                    detail.append(row['kind'])
                state = '已处置' if decisions else '未确认'
                rows.append(f'| H{index} | {row["module"]} | {"；".join(detail)} | {state} |')
        else:
            rows += ['接口差异表为空；**空表不代表无接口变化**，须以本次派生的输入 md5 为准。']
        rows += ['', f'- 派生证据：{json.dumps(ports.get("evidence") or {}, ensure_ascii=False, sort_keys=True)}',
                 f'- 派生结论：{ports.get("status")}（{ports.get("reason", "")}）']
        # 逐 hunk 登记（契约 §8.2-1 要求的字段：位置 / 真实 unified diff / 影响用例 / 复核状态）
        try:
            proposals = s0b.load_proposals(folder)
            decisions = s0b.decisions_of(folder)
        except (OSError, ValueError):
            proposals, decisions = [], {}
        if proposals:
            baseline_text = ''
            try:
                baseline_text = (Path(record['baseline']) / record['tb_top']).read_text(
                    encoding='utf-8', errors='surrogateescape')
            except (KeyError, OSError, TypeError):
                baseline_text = ''
            rows += ['', '## 逐 hunk 登记（提议 + 真实 diff + 复核状态）', '']
            for hunk in proposals:
                state = decisions.get(hunk['hunk_id'], '未确认')
                rows.append(f'### {hunk["hunk_id"]}（{state}）')
                rows.append(f'- 位置：{s0b.line_span(baseline_text, hunk["old_text"]) or "（基线里找不到原片段）"}')
                rows.append(f'- 影响用例/接口：{"、".join(hunk["addresses"]) or "-"}')
                rows.append(f'- 理由：{hunk["reason"]}')
                rows.append('')
                rows.append('```diff')
                rows.extend(s0b.unified_diff(hunk['old_text'], hunk['new_text']).rstrip().splitlines())
                rows.append('```')
                rows.append('')
        rows += ['', '## 三库冒烟', '']
        smoke = record.get('smoke') or {}
        rows += [f'- 状态：{smoke.get("status", "waiting")}（{smoke.get("reason", "尚未执行")}）']
        for label in ('candidate', 'baseline'):
            segment = smoke.get(label) or {}
            if not segment:
                continue
            summary = segment.get('summary') or {}
            rows.append(f'- {label}：rc={segment.get("rc")} errors={summary.get("errors")} '
                        f'warnings={summary.get("warnings")}')
            rows.append(f'  - 命令：{" ".join(segment.get("command") or []) or "-"}')
            rows.append(f'  - 日志：{"、".join(segment.get("logs") or []) or "-"}')
        if smoke.get('warning_delta'):
            rows += [f'- warning 增量：{json.dumps(smoke["warning_delta"], ensure_ascii=False, sort_keys=True)}']
        if smoke.get('unaccepted_warnings'):
            rows += [f'- 待评估告警：{"、".join(smoke["unaccepted_warnings"])}']
        (report / 'env-check-report.md').write_text('\n'.join(rows), encoding='utf-8')

    def _verify(self, record, folder):
        """漂移核验（唯一实现）：baseline / rtl_source / work_env 三处见证比对。

        work 的见证取 `record['work_witness']`（授权落盘后会追加新的见证文件），
        否则"合法落盘"会被自己判成漂移（复核 FAIL-1）。
        """
        drift, errors = {}, []
        if not record.get('baseline') or not record.get('work_env'):
            return drift, errors            # 记录不完整（伪造/早期失败）⇒ 无从核验，交给 ports 判 waiting
        if record.get('status') not in ('prepared', 'failed'):
            return drift, errors
        for name in ('reports/s0-env/env-check-report.md', 'design-context.yaml'):
            if not (folder / name).is_file():
                errors.append(f'准备产物缺失：{name}')

        def compare(label, path, filename, assets=False):
            try:
                current = manifest(self._path(path))
                old = json.loads((folder / filename).read_text(encoding='utf-8'))
                if assets:
                    roots = {'RTL', 'TB', 'PKG', 'TESTLIB', record['docs_dir'], 'run',
                             record.get('run_entry') or 'run'}
                    current = {k: v for k, v in current.items() if k.split('/')[0] in roots}
                    old = {k: v for k, v in old.items() if k.split('/')[0] in roots}
                changed = _changes(old, current)
                if changed:
                    drift[label] = changed
            except (OSError, ValueError) as exc:
                errors.append(f'{label}: {exc}')

        compare('baseline', record['baseline'], 'baseline-before.json')
        compare('rtl_source', record['rtl_source'], 'rtl-source.json')
        compare('work_env', record['work_env'],
                record.get('work_witness') or 'work-after.json', assets=True)
        return drift, errors

    def get(self, record_id):
        folder = self._folder(record_id)
        record = self._load_record(folder)
        return self._refresh_checks(record, folder)

    def propose(self, record_id, hunks, actor, now=None):
        """模型/Host 记录逐 hunk 提议（不碰副本 TB）。"""
        folder = self._folder(record_id)
        self._load_record(folder)
        return s0b.propose(folder, hunks, actor, now=now)

    def confirm(self, record_id, hunk_id, decision, actor, reason="", now=None):
        """人逐条确认/否决（只增不改，带锚）。"""
        return s0b.confirm(self._folder(record_id), hunk_id, decision, actor, reason=reason, now=now)

    def apply(self, record_id):  # noqa: A003 - 方法名沿用既有 API 词汇
        """把已确认 hunk 落进副本 TB 顶层，返回前后 md5。

        - **幂等**：已落盘的 hunk 再次 apply ⇒ `already_applied=True`，不报错；
        - 落盘成功后**追加一份 work 见证**（`work-after.<n>.json`），把"合法授权落盘"与
          "未登记改动"区分开；否则 `get()` 会把自己的落盘判成漂移（复核 FAIL-1）。
        """
        folder = self._folder(record_id)
        record = self._load_record(folder)
        result = s0b.apply_confirmed(record, folder)
        if result.get('applied'):
            index = len(list(folder.glob('work-after*.json')))
            witness = f'work-after.{index + 1}.json'
            _json(folder / witness, manifest(Path(record['work_env'])))
            record['work_witness'] = witness
            result['witness'] = witness
        record = self._refresh_checks(record, folder)
        self._save_record(folder, record)
        return result

    def smoke(self, record_id, case, now=None):
        """在副本内跑三库编译冒烟（驱动 = kb/tools/run_guarded.sh --mode compile-only）。"""
        folder = self._folder(record_id)
        record = self._load_record(folder)
        result = s0b.run_smoke(record, folder, case, run_id=record['id'], now=now)
        self._save_smoke(folder, result)
        record['smoke'] = result
        record = self._refresh_checks(record, folder)
        self._save_record(folder, record)
        return result

    def accept_warning(self, record_id, code, actor, reason="", now=None):
        """人对"新增/上升的 warning code"给出评估结论（只追加、带锚）。"""
        return s0b.accept_warning(self._folder(record_id), code, actor, reason=reason, now=now)

    def _load_record(self, folder):
        return json.loads((folder / 'record.json').read_text(encoding='utf-8'))

    def _save_record(self, folder, record):
        (folder / 'record.json').write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def _save_smoke(self, folder, result):
        (folder / 'smoke.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    def _refresh_checks(self, record, folder):
        """唯一判据链：漂移核验 → ports/smoke 结论 → checks → ready_for_execution → 刷新报告。

        `get()` / `apply()` / `smoke()` 全走这一条，避免"record.json 说 true、get() 说 false"两套判据（复核 FAIL-1/4）。
        """
        drift, errors = self._verify(record, folder)
        record['verification'] = {'drift': drift, 'errors': errors}
        if drift or errors:
            record['status'] = 'failed'
            record['error'] = '当前内容偏离派生时见证；原始准备记录保持不变'
        if record.get('baseline') and record.get('work_env'):
            try:
                record['tb_top'] = record.get('tb_top') or s0b.resolve_tb_top(Path(record['baseline']))
                record['ports'] = s0b.evaluate_ports(record, folder)
            except (OSError, ValueError) as exc:
                record['ports'] = {'status': 'failed', 'reason': f'接口派生失败：{exc}',
                                   'evidence': {}, 'table': [], 'derive': {}}
        else:
            record['ports'] = {'status': 'waiting',
                               'reason': '记录缺少 baseline/work_env，无法派生接口差异',
                               'evidence': {}, 'table': [], 'derive': {}}
        smoke = record.get('smoke') or {'status': 'waiting', 'reason': '尚未执行三库冒烟'}
        record['smoke'] = smoke
        for check in record.get('checks') or []:
            if check['key'] == 'ports':
                check['status'] = record['ports']['status']
                check['reason'] = record['ports'].get('reason', '')
            elif check['key'] == 'smoke':
                check['status'] = smoke['status']
                check['reason'] = smoke.get('reason', '')
        record['ready_for_execution'] = s0b.ready_for_execution(record, folder)
        try:
            record['report_url'] = record.get('report_url') or f"/api/s0/{record['id']}/report"
            self._write_report(folder, record)
        except OSError as exc:
            record['status'] = 'failed'
            record['error'] = f'准备报告写入失败：{exc}'
        return record

    def report_path(self, record_id):
        return self._folder(record_id) / 'reports/s0-env/env-check-report.md'
