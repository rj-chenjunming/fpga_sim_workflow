"""DSH sdk stdio 观测面（JSON-RPC 通知落账）+ D2 压缩事实落账（SPEC-REV-14 B4·B7、§3-D2）。

为什么必须有它（P6/P7 实测，REV-14 B4）：`subagent.*` 生命周期与压缩事实**只**出现在
`--profile sdk` 的 stdio NDJSON JSON-RPC 通知与 session log 里；headless `--json` 事件流
（24 行 / 19 行两次统计）**0 条** `subagent.*`、**0 条** compaction，projcache 也没有 compaction 行。
所以「桥的观测面」只能是 sdk 协议 + session log，**不得**用 headless 输出冒充。

边界（本模块只做观测，不越权）：
- 不判 attempt 完成：`turn_end` 归 `dsh_protocol`；`submit_result` 归 `dsh.py`；
- 不写业务状态、不签闸门、不改 `agent_backends.select()` 的准入；
- 不复制进程层：env 白名单复用 `dsh_process.build_env`（唯一口径，红线 8），
  停机只做最小 `TERM → KILL` 进程组回收。

=====================================================================================
版本锁定表（B7：**换版本必须整表重录**，不得沿用旧表，也不许"看起来差不多"）
=====================================================================================
    SDK_PROTOCOL_VERSION = "0.2.1-rc.2"      ← npm 包版本（`@deepseek-ai/dsh*`）
    SERVER_NAME          = "deepseek-harness-sdk-runtime"   ← wire-stable
    SERVERINFO_VERSION   = "0.0.1"           ← **wire** `serverInfo.version`（≠ 包版本！）
    REQUEST_METHODS      = 7 个，逐字
    NOTIFICATION_METHODS = 4 个，逐字

映射表来源（本机安装，只读；行号为本机 0.2.1-rc.2 实测）：
- `@deepseek-ai/dsh-sdk-protocol/lib/types/types.d.ts`
  · 14-33 行 `InitializeParams`（14）/ `InitializeResult`（27）（`serverInfo.name` 是 wire 稳定的
    `'deepseek-harness-sdk-runtime'`，`serverInfo.version` 由服务端给，**类型里不是包版本**）
  · 35-80 行 `session/prompt`（35）/`resume`（57）/`wait`（62）与
    `session/working-directory/get|set`（67/77）的参/结果
  · 82-120 行 `SdkRunStatus`（82）、`session.event`（84）、`session.status`（91）、
    `subagent.started`（98）、`subagent.finished`（105）的字段（`parentSessionId`/`childSessionId`/`status`/`stopReason`/`provider`）
  · 122-127 行 `HarnessSdkNotificationMap` = 4 个通知
  · 129-158 行 `HarnessSdkRequestMap` = 7 个请求（`shutdown` 的 `params` 为 `undefined`）
- 同目录 `transport.d.ts`
  · 1-5 行：NDJSON JSON-RPC 2.0；**服务端忽略坏行**（原文 "Malformed lines are ignored"）
    ⇒ 本仓客户端**不许**忽略，坏行必须显式失败（fail-closed）
  · 4-5 行：`id` + `method` = 请求，只有 `id` = 响应，只有 `method` = 通知
- `@deepseek-ai/dsh-session/lib/types/known-event-types.js` 31-34 行：compaction 词表
  （`compaction/end`、`compaction/prune`、`compaction/start`、`compaction/summary`）
- `@deepseek-ai/dsh-compaction/lib/types/types.d.ts` 14-99 行：compaction 事件 `data` 字段
  （`compaction/summary` 的 `compactionId`/`shadowedTokenCount`；
  `compaction/end` 的 `error?: string` —— 失败形态**显式落盘**）
- `@deepseek-ai/dsh-session/lib/types/types.d.ts` 490-519 行：`SessionEvent` 信封
  `{type, seq, time, data}`
- 本机 session log 首个物理行是**头行** `{"type":"session","version":4,"id":…,"cwd":…}`
  （无 `seq`/`data`），解析必须容忍它，否则真实日志一行都读不了。

本机实测（2026-10-28，Lead 已跑；本模块的 `initialize` 断言即由此校准）：
    initialize → {"jsonrpc":"2.0","id":1,"result":{"serverInfo":{
                    "name":"deepseek-harness-sdk-runtime","version":"0.0.1"}}}
    shutdown   → {"jsonrpc":"2.0","id":2,"result":{}}
    响应**可以乱序**（先 id=2 后 id=1）⇒ 必须按 `id` 匹配，不许按到达顺序配对；
    未注册 provider 的 initialize → error frame `code=-32603`（显式失败，非静默）。
    测试环境无模型授权 ⇒ 本片**不发** `session/prompt`（真实 turn 未验，见报告降级线）。

D2 压缩事实口径（唯一判据，别在别处再写一套）：
- **压缩次数 = `compaction/summary` 条数**（一次成功压缩一条；`compaction/start` 只是加锁标记，
  `compaction/prune` 是"不调模型的剪枝"，单列不混算）；
- 时点/身份 = 信封 `time` + `data.compactionId`；释放量 = `data.shadowedTokenCount`；
- **失败必须显式**：`compaction/end.data.error` 非空 ⇒ 计入 `errors`（`error_count`），
  不得把"压缩没触发"当"压缩成功"，也不得吞掉失败形态；
- 源不可用（缺 `zstd` / 解压失败）⇒ `availability="unavailable"` + `reason`，**不编数**。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from . import dsh_process as DP

# ==================================================================== 版本锁定（B7）

#: 上游 npm 包版本（换版本必须重录本文件整张表）
SDK_PROTOCOL_VERSION = "0.2.1-rc.2"

#: wire 稳定的服务端身份（`types.d.ts:6` 原文 "stays the wire-stable ..."）
SERVER_NAME = "deepseek-harness-sdk-runtime"

#: 服务端在 `initialize` 回执里自报的 `serverInfo.version`（实测 0.0.1）
#: ⚠ 它**不是** npm 包版本：`0.2.1-rc.2` 的包回的是 `0.0.1`。两者分别锁定、都不得猜。
SERVERINFO_VERSION = "0.0.1"

#: 本次观测面使用的 profile（`dsh --profile sdk`；headless 不算观测面，见 B4）
SDK_PROFILE = "sdk"

#: NDJSON JSON-RPC 2.0（`transport.d.ts` 头注释）
WIRE_JSONRPC_VERSION = "2.0"

#: 客户端→服务端 7 个请求方法，逐字来自 `types.d.ts:128-158`（HarnessSdkRequestMap）
REQUEST_METHODS = frozenset({
    "initialize",
    "session/prompt",
    "session/resume",
    "session/wait",
    "session/working-directory/get",
    "session/working-directory/set",
    "shutdown",
})

#: 服务端→客户端 4 个通知，逐字来自 `types.d.ts:121-127`（HarnessSdkNotificationMap）
NOTIFICATION_METHODS = frozenset({
    "session.event",
    "session.status",
    "subagent.started",
    "subagent.finished",
})

#: `SdkRunStatus`（`types.d.ts:82`）：封闭二值，超出即坏帧
SDK_RUN_STATUSES = frozenset({"ok", "error"})

#: `SessionStatusNotification.status`（`types.d.ts:95`）：封闭二值
SESSION_STATUSES = frozenset({"idle", "running"})

# ==================================================================== D2 压缩词表

COMPACTION_START = "compaction/start"
COMPACTION_SUMMARY = "compaction/summary"
COMPACTION_END = "compaction/end"
COMPACTION_PRUNE = "compaction/prune"

#: `known-event-types.js:31-34` 的 compaction 四件套
COMPACTION_KINDS = frozenset({COMPACTION_START, COMPACTION_SUMMARY,
                              COMPACTION_END, COMPACTION_PRUNE})

AVAILABILITY_OK = "ok"
AVAILABILITY_UNAVAILABLE = "unavailable"

# ==================================================================== S8k 人参与词表（SPEC-REV-18 §2）

#: 承载「人类消息」的两类事件：落盘消息 与 D3 旁路插入（同一条会两边各出现一次 ⇒ 按 id 去重）
HUMAN_MESSAGE_KIND = "user/message"
HUMAN_SPLICED_KIND = "agent/inbox/spliced"
HUMAN_KINDS = frozenset({HUMAN_MESSAGE_KIND, HUMAN_SPLICED_KIND})

#: 只认这一个来源：`source.kind == "user"`（实测带 `rpcId`/`clientTimeZone` = 浏览器人输入）。
#: 其余来源（`time-context`/`system-reminder`/`runtime-context`…）是注入上下文，不是人说的 ⇒ 不计数。
HUMAN_SOURCE_KIND = "user"

#: 计数依据前缀（写进 `human_messages_basis`，让界面/审计能解释这个数怎么来的）
HUMAN_BASIS = "source.kind=user,dedupe=id|rpcId"

#: zstd 解压单次上限（多帧一次解全；超时按 unavailable 处理，不编数）
SESSION_LOG_TIMEOUT_S = 120.0


# ==================================================================== 异常

class SdkProtocolError(RuntimeError):
    """sdk 观测面失败基类：所有失败都发生在收口之前，调用方必须显式失败。"""


class SdkBadFrame(SdkProtocolError):
    """坏帧：非 JSON / 非对象 / `jsonrpc != "2.0"` / 既无 id 也无 method / 未知 id 的响应。"""


class SdkVersionMismatch(SdkProtocolError):
    """`serverInfo.name`/`version` 与锁定表不符（换版本必须重录，B7）。"""


class SdkResponseError(SdkProtocolError):
    """JSON-RPC error frame：保留 wire `code`/`message`/`data`（不吞、不改写）。"""

    def __init__(self, code: int | None, message: str, data: Any = None) -> None:
        super().__init__("sdk error %r: %s" % (code, message))
        self.code = code
        self.message = message
        self.data = data


class SdkTimeout(SdkProtocolError):
    """deadline 内没有回执（不重试、不伪造结果）。"""


class SdkUnknownMethod(SdkProtocolError):
    """请求方法不在锁定映射表（含服务端反向请求）。"""


class SdkUnknownNotification(SdkProtocolError):
    """通知方法不在锁定映射表（未知通知必须显式失败，不许丢弃）。"""


class SdkServerClosed(SdkProtocolError):
    """服务端已退出/已关闭，无法再收发帧。"""


class SessionLogError(RuntimeError):
    """session log 行不可解释（坏 JSON、缺字段）：显式失败，**不静默少计数**。"""


# ==================================================================== 观测事实

@dataclass(frozen=True)
class SubagentStarted:
    """`subagent.started`（`types.d.ts:97-103`）：只有父子会话身份。"""

    parent_session_id: str
    child_session_id: str


@dataclass(frozen=True)
class SubagentFinished:
    """`subagent.finished`（`types.d.ts:104-120`）：provider/agentId/status/stopReason。

    `stop_reason` 按 wire 原文记录、**不做 enum 白名单**：`SubagentStopReason` 是
    declaration-merged 联合（`completed|aborted|error|max-tokens|refusal`），
    新 backend 会并入新取值，硬白名单会把正常回执判成坏帧。
    """

    provider: str
    agent_id: str
    parent_session_id: str
    child_session_id: str
    status: str
    stop_reason: str
    last_assistant_message: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class SdkHandshake:
    """一次成功 `initialize` 的握手事实（自证"我握的是哪一份协议"）。"""

    name: str
    version: str
    expected_name: str
    expected_version: str
    profile: str


@dataclass(frozen=True)
class SdkObservation:
    """sdk 通知面的**只读快照**：`SdkClient.observations()` 每次返回新快照。"""

    subagents_started: tuple[SubagentStarted, ...] = ()
    subagents_finished: tuple[SubagentFinished, ...] = ()
    session_status: tuple[tuple[str, str], ...] = ()
    session_event_count: int = 0
    session_event_kinds: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({}))
    handshake: SdkHandshake | None = None

    @property
    def subagents_started_count(self) -> int:
        return len(self.subagents_started)

    @property
    def subagents_finished_count(self) -> int:
        return len(self.subagents_finished)


@dataclass(frozen=True)
class CompactionRecord:
    """一次成功压缩（一条 `compaction/summary`）。"""

    compaction_id: str
    time: int
    seq: int | None = None
    shadowed_token_count: int | None = None


@dataclass(frozen=True)
class CompactionError:
    """一次失败压缩（`compaction/end.data.error`）：显式登记，不吞。"""

    compaction_id: str
    error: str
    time: int | None = None


@dataclass(frozen=True)
class CompactionFacts:
    """D2 压缩事实 + S8k 人参与反馈次数（同一份会话日志、同一遍解析，唯一实现）。

    口径：`count` = `compaction/summary` 条数 = 成功压缩次数；
    `prune_count` = 不调模型的剪枝次数（单列，不混算成功次数）；
    `failed` = 存在显式失败形态；`availability="unavailable"` 时全零且必须给 `reason`（不编数）。

    `human_messages`（SPEC-REV-18 §2）= **人发出的消息条数**：只认 `source.kind == "user"`，
    按 `id` → `rpcId` 去重；`human_messages_basis` 是计数依据（可核）。源不可用时为 0 且不给依据。
    """

    availability: str
    count: int = 0
    records: tuple[CompactionRecord, ...] = ()
    errors: tuple[CompactionError, ...] = ()
    start_count: int = 0
    end_count: int = 0
    prune_count: int = 0
    reason: str | None = None
    path: str | None = None
    human_messages: int = 0
    human_messages_basis: str | None = None

    def __post_init__(self) -> None:
        if self.availability not in (AVAILABILITY_OK, AVAILABILITY_UNAVAILABLE):
            raise ValueError("availability 只能是 %r/%r：%r"
                             % (AVAILABILITY_OK, AVAILABILITY_UNAVAILABLE, self.availability))
        if isinstance(self.human_messages, bool) or not isinstance(self.human_messages, int):
            raise ValueError("human_messages 必须是整数：%r" % (self.human_messages,))
        if self.human_messages < 0:
            raise ValueError("human_messages 不得为负：%r" % (self.human_messages,))
        if self.availability == AVAILABILITY_UNAVAILABLE:
            if any((self.count, self.records, self.errors, self.start_count,
                    self.end_count, self.prune_count, self.human_messages)):
                raise ValueError("source 不可用时不得给出任何计数（不编数）")
            if self.human_messages_basis is not None:
                raise ValueError("source 不可用时不得给出计数依据")
            if not self.reason:
                raise ValueError("source 不可用必须给 reason")
        elif self.reason is not None:
            raise ValueError("source 可用时不得携带降级 reason")
        if self.count != len(self.records):
            raise ValueError("count（%d）必须等于 records 条数（%d）"
                             % (self.count, len(self.records)))
        if len(self.errors) > self.end_count:
            raise ValueError("errors 条数（%d）不可能多于 compaction/end 条数（%d）"
                             % (len(self.errors), self.end_count))

    @classmethod
    def unavailable(cls, reason: str, *, path: str | None = None) -> "CompactionFacts":
        return cls(availability=AVAILABILITY_UNAVAILABLE, reason=reason, path=path)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def failed(self) -> bool:
        return bool(self.errors)

    @property
    def times(self) -> tuple[int, ...]:
        return tuple(record.time for record in self.records)

    @property
    def compaction_ids(self) -> tuple[str, ...]:
        return tuple(record.compaction_id for record in self.records)

    @property
    def freed_tokens(self) -> int:
        return sum(record.shadowed_token_count or 0 for record in self.records)


# ==================================================================== 严格帧校验（纯函数）

def _require_str(payload: Mapping[str, Any], key: str, *, where: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SdkBadFrame("%s 缺非空字符串字段 %r：%r" % (where, key, payload))
    return value


def _response_error(error: Any) -> SdkResponseError:
    """把 wire error 对象折成异常；结构不符 ⇒ 坏帧（不得猜 code/message）。"""
    if not isinstance(error, dict):
        raise SdkBadFrame("error frame 的 error 不是对象：%r" % (error,))
    message = _require_str(error, "message", where="error frame")
    code = error.get("code")
    if code is not None and (not isinstance(code, int) or isinstance(code, bool)):
        raise SdkBadFrame("error frame 的 code 不是整数：%r" % (code,))
    return SdkResponseError(code, message, error.get("data"))


# ==================================================================== sdk 客户端

_STDERR_TAIL_BYTES = 4096


class SdkClient:
    """最小 sdk 客户端（观测面够用为止）。

    用法：

        client = SdkClient(node=…, bin=…, cwd=…, home=…)
        await client.start()
        try:
            await client.initialize(cwd=…, provider=…, model=…)
            message_id = await client.session_prompt("s1", "…")   # 只表示入队
            await client.session_wait("s1")                       # 完成等待
            facts = client.observations()
        finally:
            await client.close()                                  # shutdown 失败也回收进程
    """

    def __init__(self, *, node: Path | str, bin: Path | str, cwd: Path | str,
                 home: Path | str | None = None, timeout_s: float = 120.0,
                 api_key: str | None = None, api_key_env: str = "PUBLIC_API_KEY",
                 proxy_env: Mapping[str, str] | None = None,
                 env_extra: Mapping[str, str] | None = None) -> None:
        self._node = Path(node)
        self._bin = Path(bin)
        self._cwd = Path(cwd)
        # home 不另给时用 cwd：DSH_HOME/HOME 必须落在 attempt 自己目录里（DS-09）
        self._home = Path(home) if home is not None else self._cwd
        self._timeout_s = float(timeout_s)
        self._api_key = api_key
        self._api_key_env = api_key_env
        self._proxy_env = dict(proxy_env or {})
        self._env_extra = dict(env_extra or {})

        self._proc: asyncio.subprocess.Process | None = None
        self._pump_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._lock: asyncio.Lock | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._abandoned: set[int] = set()
        self._next_id = 1
        self._fatal: BaseException | None = None
        self._closing = False
        self._shutdown_sent = False
        self._closed = False
        self._stderr_tail = bytearray()

        # 通知落账的**内部可变**状态；只经 observations() 的冻结快照外泄
        self._started: list[SubagentStarted] = []
        self._finished: list[SubagentFinished] = []
        self._status: list[tuple[str, str]] = []
        self._event_count = 0
        self._kind_counts: dict[str, int] = {}
        self._handshake: SdkHandshake | None = None

    # -------------------------------------------------------- 生命周期

    @classmethod
    async def spawn(cls, **kwargs: Any) -> "SdkClient":
        """构造 + `start()` 的合体（调用方不想写两步时用）。"""
        client = cls(**kwargs)
        return await client.start()

    async def start(self) -> "SdkClient":
        """起 `node <bin> --profile sdk`；cwd/env 由调用方给，env 走 build_env 白名单。"""
        if self._proc is not None:
            raise SdkProtocolError("sdk 客户端只能 start 一次（请新建实例）")
        if not self._cwd.is_dir():
            raise SdkProtocolError("sdk 工作目录不存在：%s" % self._cwd)
        if not self._home.is_dir():
            raise SdkProtocolError("sdk DSH_HOME 不存在：%s（attempt home 必须由调用方准备好）"
                                   % self._home)
        for label, path in (("node", self._node), ("dsh bin", self._bin)):
            if not path.is_file():
                raise SdkProtocolError("sdk 缺 %s：%s" % (label, path))
        env = DP.build_env(self._attempt_spec())          # 唯一 env 口径（不写第二套）
        self._lock = asyncio.Lock()
        self._proc = await asyncio.create_subprocess_exec(
            str(self._node), str(self._bin), "--profile", SDK_PROFILE,
            cwd=str(self._cwd), env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, start_new_session=True)
        self._pump_task = asyncio.create_task(self._pump())
        self._stderr_task = asyncio.create_task(self._pump_stderr())
        return self

    def _attempt_spec(self) -> DP.AttemptSpec:
        """把 sdk 观测面映射成进程层 spec —— env 白名单的唯一入口（复用，不复制）。"""
        return DP.AttemptSpec(
            attempt_key="sdk-observation", cwd=self._cwd, home=self._home, task="",
            dsh_bin=self._bin, node=self._node, profile=SDK_PROFILE,
            timeout_s=self._timeout_s, wrap=False, api_key=self._api_key,
            api_key_env=self._api_key_env, proxy_env=self._proxy_env,
            env_extra=self._env_extra)

    @property
    def returncode(self) -> int | None:
        return None if self._proc is None else self._proc.returncode

    @property
    def closed(self) -> bool:
        return self._closed

    def stderr_tail(self) -> str:
        return self._stderr_tail.decode("utf-8", "replace").strip()

    # -------------------------------------------------------- 请求/响应

    async def request(self, method: str, params: Any = None, *,
                      timeout: float | None = None) -> Any:
        """发一个请求并等**自己 id** 的回执；error frame ⇒ `SdkResponseError`。"""
        if method not in REQUEST_METHODS:
            raise SdkUnknownMethod(
                "未知请求方法 %r：锁定版本 %s 的映射表里没有它（换版本必须重录）"
                % (method, SDK_PROTOCOL_VERSION))
        if self._proc is None:
            raise SdkServerClosed("sdk 客户端尚未 start")
        if self._closed or self._proc.returncode is not None:
            raise SdkServerClosed("sdk 服务端已退出（rc=%r），无法再发 %r"
                                  % (self._proc.returncode, method))
        if self._fatal is not None:
            raise self._fatal

        request_id = self._next_id
        self._next_id += 1
        frame: dict[str, Any] = {"jsonrpc": WIRE_JSONRPC_VERSION, "id": request_id,
                                 "method": method}
        if params is not None:
            frame["params"] = params
        try:
            payload = (json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SdkProtocolError("请求 %r 的 params 不能序列化成 JSON：%s"
                                   % (method, exc)) from None

        lock = self._lock
        if lock is None or self._proc.stdin is None:
            raise SdkServerClosed("sdk 客户端尚未 start（没有可写的 stdin）")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future
        try:
            async with lock:
                self._proc.stdin.write(payload)
                await self._proc.stdin.drain()
        except (OSError, RuntimeError) as exc:
            self._pending.pop(request_id, None)
            raise SdkServerClosed("写帧失败（服务端已关闭）：%r" % (exc,)) from None

        limit = self._timeout_s if timeout is None else float(timeout)
        try:
            return await asyncio.wait_for(future, limit)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            self._abandoned.add(request_id)   # 迟到的回执不再改变结论
            raise SdkTimeout("请求 %r 在 %.1fs 内无回执（id=%d）%s"
                             % (method, limit, request_id,
                                ("；stderr: " + self.stderr_tail()) if self.stderr_tail() else "")
                             ) from None
        except asyncio.CancelledError:
            self._pending.pop(request_id, None)
            self._abandoned.add(request_id)
            raise

    async def initialize(self, cwd: Path | str, provider: str, model: str, *,
                         reasoning_effort: str | None = None,
                         max_tokens: int | None = None) -> dict[str, Any]:
        """握手并**校验**服务端身份/版本（不符 ⇒ `SdkVersionMismatch`，B7）。"""
        params: dict[str, Any] = {"cwd": str(cwd), "provider": provider, "model": model}
        if reasoning_effort is not None:
            params["reasoningEffort"] = reasoning_effort
        if max_tokens is not None:
            params["maxTokens"] = int(max_tokens)
        result = await self.request("initialize", params)
        if not isinstance(result, dict):
            raise SdkVersionMismatch("initialize 回执不是对象：%r" % (str(result)[:120],))
        info = result.get("serverInfo")
        if not isinstance(info, dict):
            raise SdkVersionMismatch("initialize 回执缺 serverInfo：%r" % (str(result)[:120],))
        name, version = info.get("name"), info.get("version")
        if name != SERVER_NAME:
            raise SdkVersionMismatch(
                "serverInfo.name 不符：期望 %r 实际 %r（换版本必须重录映射表）"
                % (SERVER_NAME, name))
        if version != SERVERINFO_VERSION:
            raise SdkVersionMismatch(
                "serverInfo.version 不符：期望 %r 实际 %r（包版本 %s；wire 版本单独锁定，"
                "换版本必须重录）" % (SERVERINFO_VERSION, version, SDK_PROTOCOL_VERSION))
        self._handshake = SdkHandshake(name=str(name), version=str(version),
                                       expected_name=SERVER_NAME,
                                       expected_version=SERVERINFO_VERSION,
                                       profile=SDK_PROFILE)
        return result

    async def session_prompt(self, session_id: str, text: str) -> str:
        """入队一轮 prompt，返回 `messageId`。

        **`messageId` 只是入队身份，不是完成**：完成只由 `session_wait`（或对侧
        `turn_end`）判，B5 明确"仅 `messageId` 不放行"。
        """
        if not isinstance(text, str) or not text:
            raise SdkProtocolError("prompt 文本必须是非空字符串")
        result = await self.request("session/prompt", {
            "sessionId": session_id,
            "contentBlocks": [{"type": "text", "text": text}],
        })
        if not isinstance(result, dict):
            raise SdkProtocolError("session/prompt 回执不是对象：%r" % (str(result)[:120],))
        message_id = _require_str(result, "messageId", where="session/prompt 回执")
        return message_id

    async def session_wait(self, session_id: str) -> dict[str, Any]:
        """等待会话及其受管子孙结束（**完成判据**的协议面入口）。"""
        result = await self.request("session/wait", {"sessionId": session_id})
        if not isinstance(result, dict):
            raise SdkProtocolError("session/wait 回执不是对象：%r" % (str(result)[:120],))
        return result

    async def shutdown(self, *, timeout: float | None = None) -> dict[str, Any]:
        """发 `shutdown`（类型里 `params` 是 `undefined`，因此不带 params 成员）。"""
        if self._proc is None:
            raise SdkServerClosed("sdk 客户端尚未 start")
        self._closing = True                  # 之后的 EOF 是正常收尾，不算 fatal
        self._shutdown_sent = True
        try:
            result = await self.request("shutdown", None, timeout=timeout)
        finally:
            await self._terminate()
        if not isinstance(result, dict):
            raise SdkProtocolError("shutdown 回执不是对象：%r" % (str(result)[:120],))
        return result

    async def close(self, *, shutdown_timeout_s: float = 5.0) -> None:
        """幂等收尾：shutdown 失败也**必须**把进程回收掉（TERM → KILL 进程组）。"""
        if self._proc is None:
            self._closed = True
            return
        if not self._shutdown_sent and not self._closed and self._proc.returncode is None:
            try:
                await self.shutdown(timeout=shutdown_timeout_s)
            except SdkProtocolError:
                pass                          # 停机失败不影响回收；下面 TERM→KILL 兜底
        await self._terminate()

    async def __aenter__(self) -> "SdkClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    # -------------------------------------------------------- 进程回收

    async def _terminate(self, *, grace_s: float = 3.0) -> None:
        proc = self._proc
        if proc is not None and proc.returncode is None:
            for sig, wait_s in ((signal.SIGTERM, grace_s), (signal.SIGKILL, 5.0)):
                try:
                    os.killpg(os.getpgid(proc.pid), sig)
                except (ProcessLookupError, PermissionError, OSError):
                    break
                try:
                    await asyncio.wait_for(proc.wait(), wait_s)
                    break
                except asyncio.TimeoutError:
                    continue
        await self._cleanup()

    async def _cleanup(self) -> None:
        self._closed = True
        self._closing = True
        for task in (self._pump_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._pump_task = None
        self._stderr_task = None
        if self._proc is not None and self._proc.stdin is not None:
            with contextlib.suppress(Exception):
                self._proc.stdin.close()
        self._fail_pending(SdkServerClosed("sdk 客户端已关闭"), record_fatal=False)

    # -------------------------------------------------------- 读帧循环

    async def _pump_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    return
                self._stderr_tail.extend(chunk)
                if len(self._stderr_tail) > _STDERR_TAIL_BYTES:
                    del self._stderr_tail[:-_STDERR_TAIL_BYTES]
        except asyncio.CancelledError:
            raise
        except Exception:
            return

    async def _pump(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            self._fail_pending(SdkServerClosed("sdk 进程/管道缺失，无法读帧"))
            return
        try:
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    tail = self.stderr_tail()
                    self._fail_pending(
                        SdkServerClosed("sdk 服务端在回执前关闭了 stdout（rc=%r）%s"
                                        % (proc.returncode,
                                           ("；stderr: " + tail) if tail else "")),
                        record_fatal=not self._closing)
                    return
                try:
                    self._handle_line(raw)
                except SdkProtocolError as exc:
                    self._fail_pending(exc)     # 坏帧一律 fail-closed（不忽略、不修补）
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:                 # 读循环自身崩溃也必须显式化
            self._fail_pending(SdkProtocolError("读帧循环崩溃：%r" % (exc,)))
            return

    def _fail_pending(self, exc: BaseException, *, record_fatal: bool = True) -> None:
        if record_fatal and self._fatal is None:
            self._fatal = exc
        pending = list(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(exc)

    def _handle_line(self, raw: bytes) -> None:
        """一帧一行：严格校验后派发（纯同步，异常即 fail-closed）。"""
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise SdkBadFrame("帧不是合法 UTF-8：%r（%s）" % (raw[:60], exc)) from None
        if not text:
            raise SdkBadFrame("收到空行：NDJSON 里空行不是合法帧")
        try:
            frame = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SdkBadFrame("坏 JSON 帧：%r（%s）" % (text[:120], exc)) from None
        if not isinstance(frame, dict):
            raise SdkBadFrame("帧不是 JSON 对象：%r" % (text[:120],))
        if frame.get("jsonrpc") != WIRE_JSONRPC_VERSION:
            raise SdkBadFrame("帧的 jsonrpc 不是 %r：%r"
                              % (WIRE_JSONRPC_VERSION, text[:120]))

        has_method = "method" in frame
        has_id = "id" in frame
        if has_method:
            method = frame.get("method")
            if not isinstance(method, str) or not method:
                raise SdkBadFrame("帧的 method 不是非空字符串：%r" % (text[:120],))
            if has_id:
                # 服务端→客户端请求：锁定映射表里没有这一类，显式拒绝而不是静默丢弃
                raise SdkUnknownMethod("服务端反向请求 %r 不在锁定映射表（本客户端只收通知/响应）"
                                       % (method,))
            self._handle_notification(method, frame.get("params"))
            return

        if not has_id:
            raise SdkBadFrame("帧既无 id 也无 method：%r" % (text[:120],))
        request_id = frame.get("id")
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            raise SdkBadFrame("响应 id 不是整数：%r" % (request_id,))
        has_result, has_error = "result" in frame, "error" in frame
        if has_result == has_error:
            raise SdkBadFrame("响应必须恰有 result 或 error 之一：%r" % (text[:120],))

        if request_id in self._abandoned:        # 超时后迟到的回执：不改变结论
            self._abandoned.discard(request_id)
            return
        future = self._pending.pop(request_id, None)
        if future is None:
            raise SdkBadFrame("收到未知 id=%d 的响应（乱序允许，但 id 必须是自己发过的）"
                              % request_id)
        if future.done():
            return
        if has_error:
            future.set_exception(_response_error(frame.get("error")))
        else:
            future.set_result(frame.get("result"))

    def _handle_notification(self, method: str, params: Any) -> None:
        if method not in NOTIFICATION_METHODS:
            raise SdkUnknownNotification(
                "未知通知 %r：锁定版本 %s 的映射表里没有它（换版本必须重录）"
                % (method, SDK_PROTOCOL_VERSION))
        payload = {} if params is None else params
        if not isinstance(payload, dict):
            raise SdkBadFrame("通知 %r 的 params 不是对象：%r" % (method, params))

        if method == "subagent.started":
            self._started.append(SubagentStarted(
                parent_session_id=_require_str(payload, "parentSessionId",
                                              where="subagent.started"),
                child_session_id=_require_str(payload, "childSessionId",
                                             where="subagent.started")))
        elif method == "subagent.finished":
            status = _require_str(payload, "status", where="subagent.finished")
            if status not in SDK_RUN_STATUSES:
                raise SdkBadFrame("subagent.finished.status 不在 %r：%r"
                                  % (sorted(SDK_RUN_STATUSES), status))
            raw_message = payload.get("lastAssistantMessage")
            if raw_message is None:
                message: tuple[dict[str, Any], ...] = ()
            elif isinstance(raw_message, list) and all(isinstance(b, dict) for b in raw_message):
                message = tuple(raw_message)
            else:
                raise SdkBadFrame("subagent.finished.lastAssistantMessage 不是对象数组：%r"
                                  % (raw_message,))
            self._finished.append(SubagentFinished(
                provider=_require_str(payload, "provider", where="subagent.finished"),
                agent_id=_require_str(payload, "agentId", where="subagent.finished"),
                parent_session_id=_require_str(payload, "parentSessionId",
                                              where="subagent.finished"),
                child_session_id=_require_str(payload, "childSessionId",
                                             where="subagent.finished"),
                status=status,
                stop_reason=_require_str(payload, "stopReason",
                                         where="subagent.finished"),
                last_assistant_message=message))
        elif method == "session.status":
            status = _require_str(payload, "status", where="session.status")
            if status not in SESSION_STATUSES:
                raise SdkBadFrame("session.status.status 不在 %r：%r"
                                  % (sorted(SESSION_STATUSES), status))
            self._status.append((_require_str(payload, "sessionId", where="session.status"),
                                 status))
        else:  # session.event
            # 身份只校验不落账（计数按 kind 合并；会话维度已由 session.status/明细覆盖）
            _require_str(payload, "sessionId", where="session.event")
            event = payload.get("event")
            if not isinstance(event, dict):
                raise SdkBadFrame("session.event.event 不是对象：%r" % (event,))
            kind = _require_str(event, "type", where="session.event.event")
            self._event_count += 1
            self._kind_counts[kind] = self._kind_counts.get(kind, 0) + 1

    # -------------------------------------------------------- 只读快照

    def observations(self) -> SdkObservation:
        """返回不可变快照：之后到达的通知不会改已交出的视图。"""
        return SdkObservation(
            subagents_started=tuple(self._started),
            subagents_finished=tuple(self._finished),
            session_status=tuple(self._status),
            session_event_count=self._event_count,
            session_event_kinds=MappingProxyType(dict(self._kind_counts)),
            handshake=self._handshake)


# ==================================================================== D2 压缩事实

def _log_str(payload: Mapping[str, Any], key: str, *, where: str) -> str:
    """session log 字段校验：坏字段 ⇒ `SessionLogError`（与 wire 层 `SdkBadFrame` 区分）。"""
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise SessionLogError("%s 缺非空字符串字段 %r：%r" % (where, key, str(payload)[:120]))
    return value


def _compaction_event_data(event: Mapping[str, Any], *, where: str) -> Mapping[str, Any]:
    data = event.get("data")
    if not isinstance(data, dict):
        raise SessionLogError("%s 缺 data 对象：%r" % (where, str(event)[:120]))
    return data


# ---------------------------------------------------------------- S8k：人参与反馈计数

def _human_items(kind: str, data: Any) -> tuple[Mapping[str, Any], ...]:
    """从一条事件里取「可能是人发的」消息条目。

    `user/message` ⇒ `data` 本身；`agent/inbox/spliced` ⇒ `data.inserted[]`。
    结构不认识 ⇒ 返回空元组（不猜、不抛：这些事件不参与压缩计数，坏件不该让整份事实失败）。
    """
    if not isinstance(data, dict):
        return ()
    if kind == HUMAN_MESSAGE_KIND:
        return (data,)
    inserted = data.get("inserted")
    if not isinstance(inserted, list):
        return ()
    return tuple(item for item in inserted if isinstance(item, dict))


def _is_human_message(item: Mapping[str, Any]) -> bool:
    """`source.kind == "user"` 才算人发的；其余来源是注入上下文，不计数。"""
    source = item.get("source")
    return isinstance(source, dict) and source.get("kind") == HUMAN_SOURCE_KIND


def _human_key(item: Mapping[str, Any]) -> str | None:
    """去重键：`id` → 缺则 `rpcId`（条目顶层或 `source.rpcId`，实测在 source 里）。

    D3 插入与落盘是同一条消息 ⇒ 只计一次；两个键都没有 ⇒ None（调用方不计数，只记 `skipped`）。
    """
    for value in (item.get("id"), item.get("rpcId")):
        if isinstance(value, str) and value.strip():
            return value
    source = item.get("source")
    if isinstance(source, dict):
        value = source.get("rpcId")
        if isinstance(value, str) and value.strip():
            return value
    return None


def parse_session_log_lines(lines: Iterable[str], *,
                            path: str | None = None) -> CompactionFacts:
    """纯函数：把 session log 的 JSONL 行折成压缩事实 + 人参与反馈次数（不改文件、不猜数）。

    口径见模块 docstring：成功次数 = `compaction/summary` 条数；
    `compaction/end.data.error` 非空 ⇒ 显式失败登记；
    `compaction/prune`（不调模型的剪枝）与 `compaction/start` 单列计数，不混算成功次数。
    人参与（SPEC-REV-18 §2）：`user/message` / `agent/inbox/spliced.inserted[]` 里 `source.kind=="user"`
    的条目按 `id`→`rpcId` 去重计数；其它来源不计；缺两个键的条目不计数但记 `skipped`。

    行纪律：整行空白 ⇒ 跳过（帧边界，无事实可计）；**非 JSON / 非对象 / 缺 type**
    ⇒ `SessionLogError`（宁可显式失败，也不静默少计数）。头行
    `{"type":"session",…}` 不是 `SessionEvent`（无 seq/data），按非 compaction 事件跳过。
    """
    records: list[CompactionRecord] = []
    errors: list[CompactionError] = []
    start_count = end_count = prune_count = 0
    human_keys: set[str] = set()
    human_skipped = 0

    for lineno, raw in enumerate(lines, 1):
        text = raw.strip()
        if not text:
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SessionLogError("第 %d 行不是 JSON：%r（%s）"
                                  % (lineno, text[:120], exc)) from None
        if not isinstance(event, dict):
            raise SessionLogError("第 %d 行不是 JSON 对象：%r" % (lineno, text[:120]))
        kind = event.get("type")
        if not isinstance(kind, str) or not kind:
            raise SessionLogError("第 %d 行缺 type：%r" % (lineno, text[:120]))
        if kind in HUMAN_KINDS:
            for item in _human_items(kind, event.get("data")):
                if not _is_human_message(item):
                    continue                      # 注入上下文/未知来源：不是人说的
                key = _human_key(item)
                if key is None:
                    human_skipped += 1            # 无 id/rpcId ⇒ 不计数，但记进 basis
                    continue
                human_keys.add(key)
            continue
        if kind not in COMPACTION_KINDS:
            continue                              # 其它事件不参与压缩计数

        where = "第 %d 行 %s" % (lineno, kind)
        data = _compaction_event_data(event, where=where)
        time_value = event.get("time")
        if not isinstance(time_value, int) or isinstance(time_value, bool):
            raise SessionLogError("%s 的信封缺整数 time：%r" % (where, str(event)[:120]))
        seq_value = event.get("seq")
        if seq_value is not None and (not isinstance(seq_value, int)
                                      or isinstance(seq_value, bool)):
            raise SessionLogError("%s 的 seq 不是整数：%r" % (where, seq_value))

        compaction_id = None
        if kind != COMPACTION_PRUNE:
            # `compaction/prune` 的 data 只有 shadowedRange/shadowedSeqs/shadowedTokenCount
            # （types.d.ts:88-98），没有 compactionId —— 不拿 summary 的形状套 prune
            compaction_id = _log_str(data, "compactionId", where=where)

        if kind == COMPACTION_SUMMARY:
            tokens = data.get("shadowedTokenCount")
            if tokens is not None and (not isinstance(tokens, int)
                                       or isinstance(tokens, bool) or tokens < 0):
                raise SessionLogError("%s 的 shadowedTokenCount 不是非负整数：%r"
                                      % (where, tokens))
            records.append(CompactionRecord(compaction_id=str(compaction_id),
                                            time=time_value, seq=seq_value,
                                            shadowed_token_count=tokens))
        elif kind == COMPACTION_END:
            end_count += 1
            error = data.get("error")
            if error is not None:
                if not isinstance(error, str) or not error.strip():
                    raise SessionLogError("%s 的 error 不是非空字符串：%r" % (where, error))
                errors.append(CompactionError(compaction_id=str(compaction_id),
                                              error=error, time=time_value))
        elif kind == COMPACTION_START:
            start_count += 1
        else:                                     # COMPACTION_PRUNE
            prune_count += 1

    return CompactionFacts(availability=AVAILABILITY_OK, count=len(records),
                           records=tuple(records), errors=tuple(errors),
                           start_count=start_count, end_count=end_count,
                           prune_count=prune_count, path=path,
                           human_messages=len(human_keys),
                           human_messages_basis="%s,skipped=%d" % (HUMAN_BASIS, human_skipped))


def _resolve_zstd(zstd: str | None) -> str | None:
    """解析 zstd 可执行文件；找不到 ⇒ None（调用方降级为 unavailable，不编数）。"""
    if zstd is None:
        return shutil.which("zstd")
    if os.sep in zstd:
        candidate = Path(zstd)
        return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None
    return shutil.which(zstd)


def read_session_log(path: Path | str, *, zstd: str | None = None,
                     timeout_s: float = SESSION_LOG_TIMEOUT_S) -> CompactionFacts:
    """读一个 session log（多帧 zstd）并折成压缩事实。

    - 多帧追加写：`zstd -dc` 一次解全（P7 实测：无需自己切帧）；
    - 缺 `zstd` / 解压失败 / 解出非 UTF-8 ⇒ `availability="unavailable"` + `reason`；
    - 文件不存在 ⇒ `SessionLogError`（调用方给错路径是代码缺陷，不是"源不可用"）。
    """
    log_path = Path(path)
    if not log_path.is_file():
        raise SessionLogError("session log 不存在：%s" % log_path)
    executable = _resolve_zstd(zstd)
    if executable is None:
        return CompactionFacts.unavailable(
            "zstd 不可用（PATH 里找不到 zstd；可用 zstd= 显式给可执行文件）",
            path=str(log_path))
    try:
        completed = subprocess.run([executable, "-dc", str(log_path)],
                                   capture_output=True, check=False, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return CompactionFacts.unavailable(
            "zstd -dc 超时（%.1fs）：%s" % (timeout_s, log_path), path=str(log_path))
    except OSError as exc:
        return CompactionFacts.unavailable(
            "zstd 启动失败：%r（%s）" % (exc, log_path), path=str(log_path))
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", "replace").strip().splitlines()[-3:]
        return CompactionFacts.unavailable(
            "zstd -dc 失败 rc=%s：%s（%s）"
            % (completed.returncode, " | ".join(tail), log_path), path=str(log_path))
    try:
        text = completed.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        return CompactionFacts.unavailable(
            "session log 解出非 UTF-8 内容：%s（%s）" % (exc, log_path), path=str(log_path))
    return parse_session_log_lines(text.splitlines(), path=str(log_path))


# ==================================================================== 会话日志发现（SPEC-REV-19 §2）

#: 会话日志文件名（dsh v4 会话存储：`<home>/sessions/<cwd 编码>/session-<id>/session.v4.jsonl.zstd`）
SESSION_LOG_NAME = "session.v4.jsonl.zstd"

#: 会话存储的根目录名（在 `DSH_HOME` 下）
SESSION_DIR_ROOT = "sessions"


def session_dir_name(cwd: Path | str) -> str:
    """dsh 会话存储的 **cwd 编码目录名**：`/<a>/<b>` → `--a-b--`（去前导 `/`、`/`→`-`、前后各 `--`）。

    **唯一实现**（SPEC-REV-19 §2-2）：attempt 的 `work` 路径 → 会话目录名只在这里算，
    `services/instance_proxy.py` 不另写一份（红线 8）。编码不可逆（与路径里真实的 `-` 混淆）。
    """
    return "--" + str(cwd).lstrip("/").replace("/", "-") + "--"


def find_latest_session_log(home: Path | str, *, work: Path | str) -> Path | None:
    """在 `<home>/sessions/<cwd 编码>/session-*/session.v4.jsonl.zstd` 里找**该 attempt 的**会话日志。

    只认目录名逐字等于 `session_dir_name(work)` 的会话（别的 cwd = 别的 workspace/attempt，
    借用会把别人说的话算成这里的"人参与"）；同一 cwd 下多条会话 ⇒ 取 **mtime 最新**
    （并列取会话目录名最大，保证确定性）；符号链接 / 非普通文件一律跳过（不扩大读取面）。
    找不到 ⇒ `None`（调用方给既有 `session_log_missing`，不编造空会话）。
    """
    root = Path(home) / SESSION_DIR_ROOT
    try:
        if root.is_symlink() or not root.is_dir():
            return None
        wanted = session_dir_name(work)
        found: list[tuple[float, str, Path]] = []
        for directory in sorted(root.iterdir()):
            try:
                if directory.is_symlink() or not directory.is_dir():
                    continue
                if directory.name != wanted:
                    continue
            except OSError:
                continue
            for path in sorted(directory.glob("session-*/" + SESSION_LOG_NAME)):
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    found.append((path.stat().st_mtime, path.parent.name, path))
                except OSError:
                    continue
    except OSError:
        return None
    if not found:
        return None
    found.sort(key=lambda item: (item[0], item[1]))
    return found[-1][2]
