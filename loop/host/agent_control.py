"""模型请求边界的人工控制；不重放业务效果，不拥有闸门状态。

本模块有**两套互不干扰**的指令语义：

1. 旧 `/control`（`Session`/`command`/`execute`）：会话内 steer/pause/resume/terminate，
   事件写 `agent_controls/<node>/session-*/`，语义与指纹保持（IL-04，不许改）；
2. run 作用域指令生命周期（REV-13 §7，`submit`/`instructions_view`/`effective`/`next_attempt`）：
   事件写 `agent_controls/run/instruction-<seq>.json`（只增不改、复用 `AM.seal_record`），
   支持 create/revoke/supersede、目录 revision CAS、request_id 幂等与单写者锁。
   指令合法性的判据只在**本模块**一处实现；`model_request` 只消费 `effective()` 的结论。
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import os
import re
from pathlib import Path

from host import agent_memory as AM, paths as P

try:  # POSIX 单写者锁；没有 flock 的平台显式拒绝指令写入（不猜、不静默降级）。
    import fcntl
except ImportError:  # pragma: no cover - 非 POSIX 平台
    fcntl = None

NODES = frozenset({'N3', 'N6', 'N8', 'N10', 'N11', 'N12'})
ACTIONS = {'working': ['steer', 'pause', 'terminate'], 'paused': ['steer', 'resume', 'terminate']}
CANCEL_TIMEOUT = 5
_ACTIVE = {}
_seal = AM.seal_record


class ControlConflict(ValueError):
    pass


class AgentTerminated(RuntimeError):
    pass


def _key(root, node):
    if node not in NODES:
        raise KeyError(f'不是可观察的模型节点：{node}')
    return str(Path(root).resolve()), node


def _safe(root, path):
    if not path.resolve().is_relative_to(Path(root).resolve()) or path.is_symlink():
        raise ValueError('Agent 记录路径越界或使用符号链接')
    return path


def _read(root, path):
    _safe(root, path)
    data = path.read_bytes()
    checksum = _safe(root, path.with_suffix('.sha256')).read_text().strip()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError(f'agent record checksum mismatch: {path.name}')
    return json.loads(data)


def _attempts(root, node):
    directory = _safe(root, Path(root) / 'agent_calls' / node)
    return [p for p in sorted(directory.glob('attempt-*')) if re.fullmatch(r'attempt-\d{6,}', p.name)]


def _control_events(root, node):
    directory = _safe(root, Path(root) / 'agent_controls' / node)
    out = []
    for folder in sorted(directory.glob('session-*')):
        if not re.fullmatch(r'session-\d{6,}', folder.name):
            continue
        _safe(root, folder)
        identity = {'run_id': Path(root).name, 'node': node, 'session_id': f'{node}:{folder.name}'}
        metadata = _read(root, folder / 'session.json')
        if any(metadata.get(k) != v for k, v in identity.items()):
            raise ValueError('agent control identity mismatch')
        for path in sorted(folder.glob('event-*.json')):
            event = _read(root, path)
            if any(event.get(k) != v for k, v in identity.items()):
                raise ValueError('agent control identity mismatch')
            out.append(event)
    return out


def live_view(root, node):
    session = _ACTIVE.get(_key(root, node))
    return session.view() if session else None


def read_view(root, node, attempt=None):
    _key(root, node)
    summaries, records = [], {}
    for folder in _attempts(root, node):
        _safe(root, folder)
        sequence = int(folder.name.split('-')[1])
        request_file = folder / 'request.json'
        _safe(root, request_file)  # 符号链接/越界在读取状态前显式失败（F08 复核 M1）
        request_state = AM.record_state(request_file)
        if request_state == 'corrupt':
            # 校验不匹配/JSON 坏 ⇒ 显式失败（不可当成有效记录）；不是「写了一半」。
            raise ValueError(f'agent record checksum mismatch: {request_file.name}')
        if request_state != 'committed':
            # F08：半写请求只报告状态，不进入可消费记录；其它尝试照常可读。
            # 观测矩阵：尝试目录已建但数据未写 ⇒ incomplete（不是 absent）。
            status = 'incomplete' if request_state == 'absent' else request_state
            summaries.append({'attempt': sequence, 'status': status,
                              'model': None, 'cycle': None})
            continue
        result_file = folder / 'result.json'
        _safe(root, result_file)
        result_state = AM.record_state(result_file)
        if result_state == 'committed':
            request = _read(root, request_file)
            result = _read(root, result_file)
        elif result_state == 'absent':
            request = _read(root, request_file)
            result = None
        elif result_state == 'corrupt':
            raise ValueError(f'agent record checksum mismatch: {result_file.name}')
        else:
            summaries.append({'attempt': sequence, 'status': result_state,
                              'model': None, 'cycle': None})
            continue
        expected = {'run_id': Path(root).name, 'node': node, 'attempt': sequence}
        if any(request.get(k) != v for k, v in expected.items()) or (
                result and any(result.get(k) != v for k, v in expected.items())):
            raise ValueError('agent record identity mismatch')
        summaries.append({'attempt': sequence, 'status': result['status'] if result else 'incomplete',
                          'model': request.get('model'), 'cycle': request.get('cycle')})
        records[sequence] = (request, result)
    selected = attempt if attempt is not None else next(
        (item['attempt'] for item in reversed(summaries) if item['attempt'] in records), None)
    if selected is not None and selected not in records:
        raise KeyError('调用尝试不存在')
    request, result = records.get(selected, (None, None))
    previous_input = None
    if selected is not None:
        earlier = [sequence for sequence in sorted(records) if sequence < selected]
        if earlier:
            previous_input = records[earlier[-1]][0].get('input')
    return {'run_id': Path(root).name, 'node': node, 'live': live_view(root, node),
            'attempts': summaries, 'selected_attempt': selected, 'request': request, 'result': result,
            'previous_input': previous_input,
            'controls': _control_events(root, node),
            'observation': '实际输入、节点事件和返回结果；不提供模型隐藏推理或 token 流。'}


class Session:
    def __init__(self, ctx, node):
        self.ctx, self.node = ctx, node
        self.root = Path(ctx.run_dir)
        parent = _safe(self.root, self.root / 'agent_controls' / node)
        parent.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while True:
            self.folder = parent / f'session-{sequence:06d}'
            try:
                self.folder.mkdir()
                break
            except FileExistsError:
                sequence += 1
        self.session_id = f'{node}:{self.folder.name}'
        self.state, self.revision, self.attempt = 'starting', 0, None
        self.pending, self.task = None, None
        self.signal = asyncio.Event()
        self.instructions = []
        self.receipts = {}
        _seal(self.folder / 'session.json', {'run_id': ctx.run_id, 'node': node,
                                            'session_id': self.session_id, 'created_at': P.now_iso()})

    def record(self, kind, **fields):
        sequence = self.revision + 1
        event = {'type': kind, 'run_id': self.ctx.run_id, 'node': self.node,
                 'session_id': self.session_id, 'revision': sequence, 'at': P.now_iso(), **fields}
        _seal(self.folder / f'event-{sequence:06d}.json', event)
        self.revision = sequence
        return event

    def transition(self, state, **fields):
        self.record('state', state=state, attempt=self.attempt, **fields)
        self.state = state

    def view(self):
        return {'session_id': self.session_id, 'revision': self.revision, 'state': self.state,
                'attempt': self.attempt,
                'available_actions': [] if self.pending else ACTIONS.get(self.state, [])}

    async def cancel_child(self):
        task = self.task
        if task is None:
            return
        if not task.done():
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=CANCEL_TIMEOUT)
            if not done:
                # 旧调用即使返回也只会写请求记录；调用消费者已被本边界切断。
                task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
                raise RuntimeError('模型请求取消超时；禁止重叠重发，节点失败')
        with contextlib.suppress(asyncio.CancelledError, Exception):
            task.result()
        self.task = None


def command(root, node, data):
    key = _key(root, node)
    action = data.get('action')
    if not isinstance(action, str) or action not in {'steer', 'pause', 'resume', 'terminate'}:
        raise ValueError('非法 Agent 控制动作')
    actor = data.get('actor')
    if not isinstance(actor, str) or not actor.startswith('human:') or not actor[6:].strip():
        raise PermissionError('必须提供 human:<name> 操作者')
    message = data.get('message', '')
    if not isinstance(message, str) or len(message) > 4000 or (action == 'steer' and not message.strip()):
        raise ValueError('补充指令需非空，且不超过 4000 字符')
    request_id = data.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
        raise ValueError('非法 request_id')
    signature = {k: data.get(k) for k in ('action', 'actor', 'message', 'session_id', 'expected_revision', 'request_id')}
    fingerprint = AM.fingerprint(signature)
    # 完成后仍允许查询同一已接收命令的回执，不会重放动作。
    for event in _control_events(root, node):
        if event['type'] == 'accepted' and event.get('request_id') == request_id:
            if event['signature'] != fingerprint:
                raise ControlConflict('request_id 已用于另一命令')
            return event
    session = _ACTIVE.get(key)
    if session is None or data.get('session_id') != session.session_id:
        raise ControlConflict('没有匹配的活跃 Agent 会话；历史记录只读')
    if data.get('expected_revision') != session.revision:
        raise ControlConflict('窗口状态已变化，请刷新后再提交')
    if session.pending or action not in ACTIONS.get(session.state, []):
        raise ControlConflict('当前状态不允许该动作，或已有命令正在处理')
    if session.task and session.task.done():
        raise ControlConflict('当前请求已经返回，不能再干预；请刷新')
    receipt = session.record('accepted', status='accepted', action=action, actor=actor,
                             message=message.strip(), request_id=request_id, signature=fingerprint)
    session.pending = receipt
    session.state = 'interrupting'
    session.signal.set()
    return receipt


async def execute(ctx, node, invoke):
    key = _key(ctx.run_dir, node)
    if key in _ACTIVE:
        raise RuntimeError('同一节点已有活跃模型请求')
    session = Session(ctx, node)
    _ACTIVE[key] = session
    terminal = 'failed'
    try:
        while True:
            previous = _attempts(ctx.run_dir, node)
            session.attempt = int(previous[-1].name.split('-')[1]) + 1 if previous else 1
            session.transition('working', instruction_ids=[i['request_id'] for i in session.instructions])
            session.task = asyncio.create_task(invoke(list(session.instructions)))
            while True:
                notification = asyncio.create_task(session.signal.wait())
                try:
                    await asyncio.wait({session.task, notification}, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    notification.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await notification
                if session.pending:
                    session.record('discarded', attempt=session.attempt)
                    await session.cancel_child()
                    break
                if session.task.done():
                    result = session.task.result()
                    terminal = 'completed'
                    return result
            while True:
                receipt = session.pending
                session.pending = None
                session.signal.clear()
                action = receipt['action']
                session.record('applied', action=action, request_id=receipt['request_id'],
                               attempt=session.attempt)
                if action == 'terminate':
                    terminal = 'stopped'
                    raise AgentTerminated('人工终止当前 Agent 请求，节点停止执行')
                if action == 'steer':
                    session.instructions.append({k: receipt[k] for k in ('actor', 'message', 'request_id')})
                    break
                if action == 'resume':
                    break
                session.transition('paused')
                await session.signal.wait()
    finally:
        try:
            await session.cancel_child()
        finally:
            _ACTIVE.pop(key, None)
            session.transition(terminal)


# ---------------------------------------------------------------- run 作用域指令生命周期（IL，REV-13 §7）
#
# 与旧会话内 `/control` 完全分开：不同的目录（`agent_controls/run/`）、不同的事件格式
# （`format_version=2`）、不同的读取器。旧节点 session 事件零改动，也不被本读取器扩展。
# 这里只做「指令事件的唯一判据」：合法性/作用域归约/到期/幂等/CAS/单写者；业务判据
# （`model_steps._validate`）与预算（`AM.check_budget`）都不在这里复制。

IL_FORMAT_VERSION = 2
IL_SCOPES = frozenset({'attempt', 'node_rework', 'run'})
IL_OPERATIONS = frozenset({'create', 'revoke', 'supersede'})
IL_MESSAGE_LIMIT = 4000
IL_DIR = ('agent_controls', 'run')
_IL_LOCK_NAME = '.lock'
_IL_FILE = re.compile(r'instruction-(\d{6,})\.json')
_IL_ATTEMPT_DIR = re.compile(r'attempt-(\d{6,})')
#: 命令载荷允许的字段（未知字段在写前拒绝）。
_IL_PAYLOAD_FIELDS = frozenset({'operation', 'actor', 'request_id',
                                'expected_instruction_revision', 'target_instruction_id',
                                'message', 'scope', 'target_nodes', 'dependencies'})
#: 事件允许的字段（读取器显式支持该格式；未知字段即审计损坏，显式失败）。
_IL_EVENT_FIELDS = frozenset({'format_version', 'run_id', 'revision', 'operation', 'request_id',
                              'actor', 'at', 'replaces_instruction_id', 'instruction',
                              'request_fingerprint'})
_IL_INSTRUCTION_FIELDS = frozenset({'id', 'version', 'message', 'scope', 'target_nodes',
                                    'dependencies', 'dependency_versions', 'bound_attempt'})


def _il_dir(root) -> Path:
    return _safe(root, Path(root) / IL_DIR[0] / IL_DIR[1])


def _il_path(root, sequence: int) -> Path:
    return _il_dir(root) / f'instruction-{sequence:06d}.json'


def _il_rel(sequence: int) -> str:
    return f'{IL_DIR[0]}/{IL_DIR[1]}/instruction-{sequence:06d}.json'


def next_attempt(root, node) -> int:
    """Host 预留的下一次明确尝试序号（与 `AM.Attempt` 取首个空位、`Session.execute` 的
    `max+1` 同一算法；同 run 同节点的尝试创建由控制边界串行化）。"""
    _key(root, node)
    previous = _attempts(root, node)
    return int(previous[-1].name.split('-')[1]) + 1 if previous else 1


@contextlib.contextmanager
def write_lock(root):
    """run 指令事件面的**单写者**协调（非阻塞 `flock`）。

    拿不到 ⇒ `ControlConflict`（API 409），并留下持有者诊断（锁文件内文本）；
    没有可用 `flock` 的平台同样显式拒绝写入 —— 契约允许「没有经验证的单写者协调时拒绝」。
    """
    if fcntl is None:  # pragma: no cover - 非 POSIX 平台
        raise ControlConflict('本平台没有可用的单写者文件锁；拒绝指令写入')
    directory = _il_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = _safe(root, directory / _IL_LOCK_NAME)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            holder = ''
            with contextlib.suppress(OSError, ValueError):
                holder = (directory / _IL_LOCK_NAME).read_text(encoding='utf-8').strip()
            raise ControlConflict(
                f'指令写入锁被占用（{IL_DIR[0]}/{IL_DIR[1]}/{_IL_LOCK_NAME}），拒绝并发写入：'
                f'{exc.strerror or exc}{("；持有者：" + holder) if holder else ""}') from exc
        with contextlib.suppress(OSError):
            os.ftruncate(fd, 0)
            os.write(fd, json.dumps({'pid': os.getpid(), 'at': P.now_iso()},
                                    ensure_ascii=False).encode('utf-8'))
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _il_actor(value):
    if not isinstance(value, str) or not value.startswith('human:') or not value[6:].strip():
        raise PermissionError('必须提供 human:<name> 操作者')
    return value


def _il_request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('非法 request_id')
    return value


def _il_dependency_digest(root, token):
    """显式依赖的当前指纹：`resource:<run 内相对路径>`（越界/符号链接/缺件显式失败）。

    这条依赖词表是**唯一实现**（不猜业务语义）；不支持的依赖类型写前拒绝，
    避免出现「声明了依赖但没人核验」的死字段。
    """
    if not isinstance(token, str) or not token.startswith('resource:'):
        raise ValueError(f'未知指令依赖类型：{token!r}（仅支持 resource:<run 内相对路径>）')
    relative = token.split(':', 1)[1]
    if not relative or Path(relative).is_absolute():
        raise ValueError(f'指令依赖路径非法：{token!r}')
    path = Path(root) / relative
    _safe(root, path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f'指令依赖缺失或不可读：{token}') from exc


def _il_dependency_changed(root, item) -> bool:
    versions = item.get('dependency_versions') or {}
    for token in item.get('dependencies') or []:
        if token not in versions:
            return True
        try:
            if _il_dependency_digest(root, token) != versions[token]:
                return True
        except ValueError:
            return True
    return False


def _il_attempt_terminal(root, node, attempt) -> bool:
    """绑定尝试是否已终态（`result.json` 出现即到期；半写/坏件也算「已结束但读不到」）。"""
    folder = Path(root) / 'agent_calls' / node / f'attempt-{attempt:06d}'
    _safe(root, folder)
    return AM.record_state(folder / 'result.json') != 'absent'


def _il_body(root, operation, data) -> dict:
    """按 operation 校验指令内容（写前拒绝）；返回要写进事件的规范化内容。"""
    content = ('message', 'scope', 'target_nodes', 'dependencies')
    if operation == 'revoke':
        extras = [key for key in content if key in data]
        if extras:
            raise ValueError(f'revoke 不接受字段：{extras}')
        if 'target_instruction_id' not in data:
            raise ValueError('revoke 必须带 target_instruction_id')
        return {}
    if operation == 'create' and 'target_instruction_id' in data:
        raise ValueError('create 不接受 target_instruction_id')
    if operation == 'supersede' and 'target_instruction_id' not in data:
        raise ValueError('supersede 必须带 target_instruction_id')
    message = data.get('message')
    if not isinstance(message, str) or not message.strip() or len(message) > IL_MESSAGE_LIMIT:
        raise ValueError('指令 message 需非空，且不超过 4000 字符')
    scope = data.get('scope')
    if scope not in IL_SCOPES:
        raise ValueError(f'非法指令作用域：{scope!r}（attempt/node_rework/run）')
    target_nodes = data.get('target_nodes')
    if not isinstance(target_nodes, list) or not target_nodes:
        raise ValueError('target_nodes 需为非空列表')
    if any(not isinstance(node, str) or node not in NODES for node in target_nodes):
        raise ValueError('target_nodes 含非法节点')
    if len(set(target_nodes)) != len(target_nodes):
        raise ValueError('target_nodes 不得重复')
    if scope != 'run' and len(target_nodes) != 1:
        raise ValueError(f'{scope} 作用域只能绑定一个目标节点')
    dependencies = data.get('dependencies', [])
    if not isinstance(dependencies, list) or any(
            not isinstance(item, str) or not item for item in dependencies):
        raise ValueError('dependencies 需为字符串列表')
    if len(set(dependencies)) != len(dependencies):
        raise ValueError('dependencies 不得重复')
    versions = {token: _il_dependency_digest(root, token) for token in dependencies}
    return {'instruction': {'message': message.strip(), 'scope': scope,
                            'target_nodes': list(target_nodes),
                            'dependencies': list(dependencies),
                            'dependency_versions': versions}}


def _il_instruction_event(root, event, sequence) -> dict:
    """校验一个已封存事件的形状/身份/枚举；返回归约用的条目（不改文件）。"""
    if not isinstance(event, dict):
        raise ValueError('指令事件不是对象')
    unknown = set(event) - _IL_EVENT_FIELDS
    if unknown:
        raise ValueError(f'指令事件含未知字段（审计损坏）：{sorted(unknown)}')
    if event.get('format_version') != IL_FORMAT_VERSION:
        raise ValueError(f'指令事件 format_version 非法：{event.get("format_version")!r}')
    if event.get('run_id') != Path(root).name:
        raise ValueError(f'指令事件身份不匹配（run_id）：{event.get("run_id")!r}')
    if event.get('revision') != sequence:
        raise ValueError(f'指令事件 revision 不匹配：{event.get("revision")!r} != {sequence}')
    operation = event.get('operation')
    if operation not in IL_OPERATIONS:
        raise ValueError(f'指令事件 operation 非法：{operation!r}')
    if not isinstance(event.get('actor'), str) or not event['actor'].startswith('human:'):
        raise ValueError('指令事件 actor 非法')
    if not isinstance(event.get('request_id'), str) or not event['request_id']:
        raise ValueError('指令事件 request_id 缺失')
    if not isinstance(event.get('at'), str) or not event['at']:
        raise ValueError('指令事件 at 缺失')
    target = event.get('replaces_instruction_id')
    if operation == 'create':
        if target is not None:
            raise ValueError('create 事件不得带 replaces_instruction_id')
    elif not isinstance(target, str) or not target:
        raise ValueError(f'{operation} 事件缺少 replaces_instruction_id')
    item = None
    if operation == 'revoke':
        if event.get('instruction') is not None:
            raise ValueError('revoke 事件不得带 instruction')
    else:
        instruction = event.get('instruction')
        if not isinstance(instruction, dict):
            raise ValueError(f'{operation} 事件缺少 instruction')
        unknown = set(instruction) - _IL_INSTRUCTION_FIELDS
        if unknown:
            raise ValueError(f'指令条目含未知字段（审计损坏）：{sorted(unknown)}')
        if not isinstance(instruction.get('id'), str) or not instruction['id']:
            raise ValueError('指令条目缺少 id')
        version = instruction.get('version')
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError('指令条目 version 非法')
        message = instruction.get('message')
        if not isinstance(message, str) or not message.strip() or len(message) > IL_MESSAGE_LIMIT:
            raise ValueError('指令条目 message 非法')
        scope = instruction.get('scope')
        if scope not in IL_SCOPES:
            raise ValueError(f'指令条目 scope 非法：{scope!r}')
        nodes = instruction.get('target_nodes')
        if not isinstance(nodes, list) or not nodes or any(
                not isinstance(node, str) or node not in NODES for node in nodes):
            raise ValueError('指令条目 target_nodes 非法')
        dependencies = instruction.get('dependencies', [])
        versions = instruction.get('dependency_versions', {})
        if not isinstance(dependencies, list) or not isinstance(versions, dict):
            raise ValueError('指令条目依赖声明非法')
        bound = instruction.get('bound_attempt')
        if scope == 'attempt':
            if (not isinstance(bound, dict) or bound.get('node') not in NODES
                    or isinstance(bound.get('attempt'), bool)
                    or not isinstance(bound.get('attempt'), int) or bound['attempt'] < 1):
                raise ValueError('attempt 作用域指令缺少 Host 绑定的尝试身份')
        elif bound is not None:
            raise ValueError('非 attempt 作用域不得带 bound_attempt')
        item = {'instruction_id': instruction['id'], 'version': version, 'message': message,
                'scope': scope, 'target_nodes': list(nodes), 'dependencies': list(dependencies),
                'dependency_versions': dict(versions), 'bound_attempt': copy.deepcopy(bound),
                'event_revision': sequence, 'actor': event['actor'], 'created_at': event['at'],
                'request_id': event['request_id'],
                'replaces_instruction_id': target}
    return {'event': event, 'operation': operation, 'target': target, 'instruction': item}


def _il_events(root) -> list[dict]:
    """读取并核验 run 指令事件流（按 seq 排序；不连续/坏件/身份不符 ⇒ 显式失败）。"""
    directory = Path(root) / IL_DIR[0] / IL_DIR[1]
    if not directory.exists():
        return []
    _safe(root, directory)
    if directory.is_symlink():
        raise ValueError('指令事件目录使用符号链接')
    found = []
    for path in directory.glob('instruction-*.json'):
        match = _IL_FILE.fullmatch(path.name)
        if not match:
            raise ValueError(f'指令事件文件名非法（审计损坏）：{path.name}')
        found.append((int(match.group(1)), path))
    found.sort()
    checked = []
    for expected, (sequence, path) in enumerate(found, 1):
        if sequence != expected:
            raise ValueError(f'指令事件不连续（缺失或重复）：期望 {expected:06d}，实际 {sequence:06d}')
        try:
            event = _read(root, path)
        except FileNotFoundError as exc:
            raise ValueError(f'指令事件不完整（incomplete）：{path.name}') from exc
        except ValueError as exc:
            raise ValueError(f'指令事件不可读或校验和不匹配（checksum mismatch）：{path.name}: {exc}') from exc
        checked.append(_il_instruction_event(root, event, sequence))
    return checked


def _il_reduce(entries):
    """归约有效集：supersede 单事件同时完成「旧失效 + 新条目」，绝不产生双生效/双失效。"""
    valid, invalidated = {}, {}
    for entry in entries:
        operation, target = entry['operation'], entry['target']
        if operation == 'create':
            item = entry['instruction']
            if item['instruction_id'] in valid or item['instruction_id'] in invalidated:
                raise ValueError(f'指令事件 ID 重复：{item["instruction_id"]}')
            valid[item['instruction_id']] = {**item, 'invalidated_by': None}
            continue
        if target not in valid:
            raise ValueError(f'{operation} 事件目标当前无效（审计不自洽）：{target}')
        old = valid.pop(target)
        invalidated[target] = {**old,
                               'state': 'revoked' if operation == 'revoke' else 'superseded',
                               'reason': 'revoked' if operation == 'revoke' else 'superseded',
                               'invalidated_by': {'event_revision': entry['event']['revision'],
                                                  'operation': operation,
                                                  'instruction_id': (entry['instruction'] or {}).get(
                                                      'instruction_id')}}
        if operation == 'supersede':
            item = entry['instruction']
            if item['instruction_id'] in valid or item['instruction_id'] in invalidated:
                raise ValueError(f'指令事件 ID 重复：{item["instruction_id"]}')
            valid[item['instruction_id']] = {**item, 'invalidated_by': None}
    return valid, invalidated


def _il_applicable(root, node, attempt, item):
    """`None` = 适用于该节点该尝试；否则返回**明确未采用原因**（优先级固定）。"""
    if node not in item['target_nodes']:
        return 'bound_to_other_node' if item['scope'] == 'attempt' else 'node_not_in_target_nodes'
    if item['scope'] == 'attempt':
        if attempt is None:
            return 'awaiting_bound_attempt'
        if item['bound_attempt']['attempt'] != attempt:
            return 'bound_to_other_attempt'
        if _il_attempt_terminal(root, node, attempt):
            return 'bound_attempt_finished'
    if _il_dependency_changed(root, item):
        return 'dependency_changed'
    return None


def _il_effective(root, entries, node, attempt, reduced=None) -> dict:
    valid, _ = reduced if reduced is not None else _il_reduce(entries)
    adopted, not_adopted = [], []
    for item in sorted(valid.values(), key=lambda value: (value['event_revision'],
                                                          value['instruction_id'])):
        reason = _il_applicable(root, node, attempt, item)
        if reason is not None:
            not_adopted.append({'instruction_id': item['instruction_id'],
                                'version': item['version'], 'reason': reason})
            continue
        adopted.append({'instruction_id': item['instruction_id'], 'version': item['version'],
                        'scope': item['scope'], 'message': item['message'],
                        'event_revision': item['event_revision'],
                        'sealed_ref': _il_rel(item['event_revision'])})
    # 本节点有效指令指纹：**只覆盖适用条目**（改别的节点的指令不会取消本节点的结果接受资格）。
    digest = AM.fingerprint({
        'version': 1, 'run_id': Path(root).name, 'node': node,
        'instructions': [{'instruction_id': item['instruction_id'], 'version': item['version'],
                          'message_sha256': AM.fingerprint(item['message']),
                          'scope': item['scope'], 'event_revision': item['event_revision']}
                         for item in adopted]})
    return {'run_id': Path(root).name, 'node': node, 'attempt': attempt,
            'revision': len(entries), 'effective_sha256': digest,
            'adopted': adopted, 'not_adopted': not_adopted}


def effective(root, node, attempt=None) -> dict:
    """某节点在某次尝试上的有效指令集（含目录 revision、指纹、采用/未采用原因）。

    这是「指令 → 请求」的唯一归约入口：`model_request` 与 API 都消费它，
    不另写第二套作用域/到期判据（红线 8）。
    """
    _key(root, node)
    entries = _il_events(root)
    return _il_effective(root, entries, node, attempt)


def _il_applied(root) -> dict:
    """从**已封存请求**重建「实际采用」事实：`{instruction_id: [{node, attempt}]}`。

    applied 是历史事实（请求真的带着它发出去了），与 accepted（已接收）和
    effective（当前有效集成员）分开投影；不读实现外的推断。
    """
    applied = {}
    for node in sorted(NODES):
        directory = Path(root) / 'agent_calls' / node
        if not directory.is_dir():
            continue
        _safe(root, directory)
        for folder in sorted(directory.glob('attempt-*')):
            match = _IL_ATTEMPT_DIR.fullmatch(folder.name)
            if not match:
                continue
            path = folder / 'request.json'
            state = AM.record_state(path)
            if state in ('absent', 'incomplete'):
                continue
            if state != 'committed':
                raise ValueError(f'agent record checksum mismatch: {path.name}')
            request = _read(root, path)
            for item in (request.get('instruction_projection') or {}).get('adopted') or []:
                instruction_id = item.get('instruction_id') if isinstance(item, dict) else None
                if isinstance(instruction_id, str):
                    applied.setdefault(instruction_id, []).append(
                        {'node': node, 'attempt': int(match.group(1))})
    return applied


def _il_entry_view(root, entries, reduced, applied, item) -> dict:
    state, reason = 'valid', None
    if item['scope'] == 'attempt':
        bound = item['bound_attempt']
        if _il_attempt_terminal(root, bound['node'], bound['attempt']):
            state, reason = 'expired', 'bound_attempt_finished'
    if state == 'valid' and _il_dependency_changed(root, item):
        state, reason = 'expired', 'dependency_changed'
    effective_now = False
    if state == 'valid':
        for node in item['target_nodes']:
            projection = _il_effective(root, entries, node, next_attempt(root, node),
                                       reduced=reduced)
            if any(entry['instruction_id'] == item['instruction_id']
                   for entry in projection['adopted']):
                effective_now = True
                break
    return {'instruction_id': item['instruction_id'], 'version': item['version'],
            'message': item['message'], 'scope': item['scope'],
            'target_nodes': list(item['target_nodes']),
            'dependencies': list(item['dependencies']),
            'bound_attempt': copy.deepcopy(item['bound_attempt']),
            'state': state, 'reason': reason,
            'accepted': True,
            'applied_attempts': applied.get(item['instruction_id'], []),
            'effective': effective_now,
            'actor': item['actor'], 'created_at': item['created_at'],
            'event_revision': item['event_revision'],
            'event_ref': _il_rel(item['event_revision']),
            'replaces_instruction_id': item['replaces_instruction_id'],
            'invalidated_by': None}


def instructions_view(root) -> dict:
    """GET /api/runs/{run_id}/instructions 的唯一装配：有效条目/版本/来源/失效原因。

    `accepted` / `applied` / `effective` 分别投影，**不合并**：
    回执只代表 accepted；applied 来自封存请求；effective 是当前有效集成员。
    空集合与读取失败不是同一状态（读取失败在 API 层映射 422）。
    """
    root = Path(root)
    entries = _il_events(root)
    valid, invalidated = _il_reduce(entries)
    applied = _il_applied(root)
    rows = [_il_entry_view(root, entries, (valid, invalidated), applied, item)
            for item in sorted(valid.values(), key=lambda value: (value['event_revision'],
                                                                  value['instruction_id']))]
    for instruction_id, item in sorted(invalidated.items(),
                                       key=lambda pair: pair[1]['event_revision']):
        row = _il_entry_view(root, entries, (valid, invalidated), applied, item)
        row.update({'state': item['state'], 'reason': item['reason'],
                    'effective': False, 'invalidated_by': copy.deepcopy(item['invalidated_by'])})
        rows.append(row)
    overview = {}
    for node in sorted(NODES):
        projection = _il_effective(root, entries, node, next_attempt(root, node),
                                   reduced=(valid, invalidated))
        if projection['adopted']:
            overview[node] = {'sha256': projection['effective_sha256'],
                              'instruction_ids': [item['instruction_id']
                                                  for item in projection['adopted']]}
    return {'run_id': root.name, 'revision': len(entries), 'instructions': rows,
            'effective': overview}


def _il_receipt(root, event) -> dict:
    """accepted 回执：只说明「已持久化接收」，不声称 applied/effective。"""
    return {'status': 'accepted', 'run_id': event['run_id'], 'operation': event['operation'],
            'revision': event['revision'], 'instruction_revision': event['revision'],
            'request_id': event['request_id'], 'actor': event['actor'], 'at': event['at'],
            'replaces_instruction_id': event.get('replaces_instruction_id'),
            'instruction': copy.deepcopy(event['instruction']),
            'event_ref': _il_rel(event['revision'])}


def submit(root, data) -> dict:
    """提交一条 run 作用域指令命令（create/revoke/supersede），返回 accepted 回执。

    写前拒绝：未知字段/枚举、空 message、非法节点、actor、CAS、目标不存在/已失效、
    未知依赖类型/缺件。幂等：同 `request_id` 同载荷返回原回执，不同载荷 ⇒ 冲突。
    单个 supersede 事件原子包含「旧失效 + 新条目」。
    """
    root = Path(root)
    if not isinstance(data, dict):
        raise ValueError('指令命令必须是对象')
    unknown = set(data) - _IL_PAYLOAD_FIELDS
    if unknown:
        raise ValueError(f'指令命令含未知字段：{sorted(unknown)}')
    operation = data.get('operation')
    if operation not in IL_OPERATIONS:
        raise ValueError(f'非法指令操作：{operation!r}（create/revoke/supersede）')
    actor = _il_actor(data.get('actor'))
    request_id = _il_request_id(data.get('request_id'))
    expected = data.get('expected_instruction_revision')
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError('expected_instruction_revision 必须是非负整数')
    body = _il_body(root, operation, data)
    # 幂等指纹只覆盖**声明的载荷**（不含 Host 解析出的依赖版本）：同 request_id 同声明的重放
    # 即使期间资源内容变化也返回原回执；依赖版本是 Host 记录的事实，不是客户端命令的一部分。
    declared = {'instruction': {key: value for key, value in body['instruction'].items()
                                if key != 'dependency_versions'}} if body else {}
    fingerprint = AM.fingerprint({'operation': operation, 'actor': actor,
                                  'request_id': request_id,
                                  'expected_instruction_revision': expected, **declared})
    with write_lock(root):
        try:
            entries = _il_events(root)
        except ValueError as exc:
            # 审计损坏/不自洽 ⇒ 无法确定当前 revision，拒绝写入（不覆盖未知状态、不悄悄清空指令）。
            raise ControlConflict(f'指令审计不可用，拒绝写入（不覆盖未知状态）：{exc}') from exc
        for entry in entries:  # 幂等先于 CAS：成功提交后的同命令重试仍返回原回执
            event = entry['event']
            if event.get('request_id') != request_id:
                continue
            if event.get('request_fingerprint') != fingerprint:
                raise ControlConflict('request_id 已用于另一指令命令')
            return _il_receipt(root, event)
        if expected != len(entries):
            raise ControlConflict(
                f'指令目录 revision 已变化（期望 {expected}，当前 {len(entries)}），请刷新后重试')
        valid, _ = _il_reduce(entries)
        target = data.get('target_instruction_id')
        if operation != 'create' and target not in valid:
            raise ControlConflict(f'指令目标不存在或已失效：{target}')
        revision = len(entries) + 1
        event = {'format_version': IL_FORMAT_VERSION, 'run_id': root.name,
                 'revision': revision, 'operation': operation, 'request_id': request_id,
                 'actor': actor, 'at': P.now_iso(),
                 'replaces_instruction_id': target if operation != 'create' else None,
                 'instruction': None, 'request_fingerprint': fingerprint}
        if operation != 'revoke':
            instruction = {'id': f'ins-{revision:06d}',
                           'version': (valid[target]['version'] + 1
                                       if operation == 'supersede' else 1),
                           **body['instruction']}
            if instruction['scope'] == 'attempt':
                instruction['bound_attempt'] = {
                    'node': instruction['target_nodes'][0],
                    'attempt': next_attempt(root, instruction['target_nodes'][0])}
            event['instruction'] = instruction
        _seal(_il_path(root, revision), event)
        return _il_receipt(root, event)
