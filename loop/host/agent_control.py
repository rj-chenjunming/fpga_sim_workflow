"""模型请求边界的人工控制；不重放业务效果，不拥有闸门状态。"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
from pathlib import Path

from host import agent_memory as AM, paths as P

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
        request_state = AM.record_state(request_file)
        if request_state == 'corrupt':
            # 校验不匹配/JSON 坏 ⇒ 显式失败（不可当成有效记录）；不是「写了一半」。
            raise ValueError(f'agent record checksum mismatch: {request_file.name}')
        if request_state != 'committed':
            # F08：半写请求只报告状态，不进入可消费记录；其它尝试照常可读。
            summaries.append({'attempt': sequence, 'status': request_state,
                              'model': None, 'cycle': None})
            continue
        result_file = folder / 'result.json'
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
    return {'run_id': Path(root).name, 'node': node, 'live': live_view(root, node),
            'attempts': summaries, 'selected_attempt': selected, 'request': request, 'result': result,
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
