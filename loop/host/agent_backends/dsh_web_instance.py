"""S7c：Host 起常驻 DSH Web 实例 + `agent_instance.json` 落账（SPEC-REV-16 §5.2 #1 的写入方 / §9-1）。

**为什么需要本模块**：REV-16 §5.2 的目标来源只有 `<run_dir>/agent_instance.json` 一条，
而它的写入方在 S4 被显式登记为「属 S5」（§9-1）。本片把这个写入方做出来：

1. 起一个**只读观测面**的 DSH Web 实例（`dsh --profile web`）：不调模型、不传凭据 env、
   不 bind 通配地址、不把 Web 实例当执行通道；
2. 从 stdout 解析**实际** host/port 与 launch token（token 只进受管元数据，不进日志/证据）；
3. 健康检查（匿名 `GET /` 必须 401 —— 证明"服务在跑且 token 门在"，**不是**"进程起来了当就绪"）；
4. 原子写 `<run_dir>/agent_instance.json`（0200→0600，tmp + fsync + `os.replace`）；
5. 停实例（SIGTERM → grace → SIGKILL；进程组一起收，不留孤儿）。

**判据来源（口径唯一，不新增第二套）**：
- 元数据文件名取 `services/instance_proxy.METADATA_NAME`（读者是它，写入方不另抄一份）；
- 元数据字段集 = `REV-16 §5.2`：`{node, attempt, host, port, token, session_log?, written_at}`；
- 时间走 `host/paths.now_iso`（§4 唯一入口）；
- 目标准入（loopback/端口）由读者 `instance_proxy.load_target` 判，本模块**不重复实现**，
  只保证自己写出的东西能通过读者的判据（用例 `test_metadata_roundtrip_through_proxy_reader`）。

**真机取证（2026-10-29，`loop/.logs/s7c/`）**：`--port 0` ⇒ stdout
`dsh web: http://127.0.0.1:<实际端口>/?token=<43 chars>`；匿名 `GET /` ⇒ 401；
`?token=` ⇒ 303 + `dsh-auth-…` cookie；带 cookie `GET /` ⇒ 200 且**无** XFO/CSP。

**home / cwd 归属（S8b 收口）**：实例 home 必须等于该 attempt 的 `dsh-home`（REV-14 §3-D3 / §9.3），
**进程 cwd 必须等于该 attempt 的 `work`**（`workdir`）——dsh 按 **cwd 编码的目录**分组会话，
cwd 停在仓根就只列"仓根这个 workspace"的会话（真机实测 2026-10-29：画面恒 `No sessions yet`）。
两者都由接线层 `web_instance_ctl`（`home_for_attempt` / `workdir_for_attempt`）从
`dsh_assets.AttemptLayout` 显式传入；本模块**只接显式配置**，不自己拼路径、不擅自改布局。
SETTINGS 里 `home`/`workdir` 留空时的回落（`dsh-web-instance` / 仓根）只是"未归属"兜底
（单独装配/诊断用），生产路径**总会被**接线层改写成 `<attempt>/dsh-home` 与 `<attempt>/work`。
**实测结论（2026-10-29，0 token）**：cwd 修好后，直连实例侧栏自动出现 workspace `work` 与
本次 0-token boot 的会话，`session-<uuid>` 在该列表行 DOM 内；无需人工选 workspace。

**不声称**：不声称 WebSocket/Upgrade 可透传（反代侧 405，REV-16 §9-2）；不声称 Web 是执行通道。
`dsh --profile web` 会在 home 里自生成 `.credentials.yaml`（会话签名 secret）；它在共用 home 里
被判 `dsh_generated` 放行（判据 `dsh_assets.home_provenance`，REV-14 §9），本模块不参与那个判定。
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

import httpx

from host import paths as P

LOG = logging.getLogger(__name__)

#: `loop.agent_runtime.dsh.web` 允许字段（多一个就拒绝：不悄悄接受未实现开关）
WEB_CONFIG_KEYS = frozenset({"enabled", "home", "workdir", "host", "preferred_port",
                             "start_timeout_s", "stop_grace_s"})
SETTINGS_FILE = P.LOOP_DIR / "SETTINGS.yaml"

#: 启动时 stdout 的**唯一**公告行形态（P1/P8 实测：`dsh web: <url>`，只打印一次）
LAUNCH_LINE_RE = re.compile(r"^dsh web: (?P<url>\S+)\s*$")
#: launch token 的 query 名（DSH 只认 `?token=`；不支持 `Authorization`，P8 §4.1）
TOKEN_QUERY = "token"
#: P8 实测：匿名请求必须是 401，不是 200（200 说明 token 门没上 ⇒ 显式失败）
HEALTH_EXPECTED_STATUS = 401
HEALTH_TIMEOUT_S = 2.0
#: 读到启动行后仍可能有一两行 warning（stderr）；排水线程必须一直跑，否则管道写满会卡住 dsh
LOG_TAIL_LINES = 200
#: 元数据文件权限：含 launch token ⇒ 只给本 uid 读
METADATA_MODE = 0o600
#: 读者（`services/instance_proxy`）接受的目标 host 集合。本模块**只用它做写入前自检**，
#: 判据本身仍由读者的 `load_target` 说了算（这里 import 一次，避免两处各抄一份字面量）。
def _loopback_hosts() -> frozenset[str]:
    from services import instance_proxy

    return instance_proxy.LOOPBACK_HOSTS


def _metadata_name() -> str:
    from services import instance_proxy

    return instance_proxy.METADATA_NAME


class WebInstanceError(RuntimeError):
    """起/停 Web 实例的显式失败（`reason` 可机判；消息里**永不含** token）。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class WebConfigError(WebInstanceError):
    """配置错误（未知字段 / 坏类型 / 未启用）。"""


@dataclass(frozen=True)
class WebInstanceConfig:
    """`dsh --profile web` 的启动配置（**只由 Host 装配**，不接受任务文本/客户端输入）。

    `node`/`bin`/`version` 来自既有 `dsh` 后端配置（版本锁定 + 指纹校验都在那边），
    本模块不重复解析、也不自己判断版本；这里只做启动与记账。
    """

    enabled: bool
    node: Path
    bin: Path
    version: str
    home: Path
    #: 实例进程的 cwd（S8b）；**必须是该 attempt 的 `work` 目录**（由接线层从 `AttemptLayout` 取）。
    #: 为什么：dsh 的会话存储按 **cwd 编码的目录** 分组（真机实测目录名形如
    #: `--home-…-attempt-work--`）⇒ 进程 cwd 若不是该 attempt 的 `work`，
    #: Web 列的就是"另一个 workspace"的会话，人在 GUI 里看不到本 attempt 的会话（D3 落不了地）。
    workdir: Path | None = None
    host: str = "127.0.0.1"
    preferred_port: int = 0
    start_timeout_s: float = 30.0
    stop_grace_s: float = 5.0
    #: S8h（REV-14 §9.4）：Web 实例要继承的 provider overlay（`--patch`，唯一生成实现仍是
    #: `dsh_assets.provider_overlay`）。空 ⇒ 不带任何 overlay（GUI 会提示"模型未配置"，如实）。
    patches: tuple[Path, ...] = ()
    #: S8h：要注入 Web 进程的额外 env（模型凭据 + 代理）。**仍走白名单**：只加这里显式给的键。
    env_extra: Mapping[str, str] = field(default_factory=dict)

    def verify(self) -> None:
        """准入：启用 + node/bin 在 + home 是目录（缺目录就建——它只装 DSH 自己的状态）。"""
        if not self.enabled:
            raise WebConfigError("web_disabled", "dsh.web.enabled=false（不启动常驻实例）")
        for label, path in (("node", self.node), ("bin", self.bin)):
            if not Path(path).is_file():
                raise WebConfigError("missing_binary", f"{label} 不存在：{path}")
        self.validate_values()
        # cwd 必须真的存在：目录布局的创建属 `dsh_assets.AttemptLayout`（本模块不擅自造 attempt 目录）
        if self.workdir is not None and not Path(self.workdir).is_dir():
            raise WebConfigError("missing_workdir",
                                 f"workdir 不是已存在目录：{self.workdir}（应由 AttemptLayout 物化）")
        for patch in self.patches:
            if not Path(patch).is_file():
                raise WebConfigError("missing_patch",
                                     f"provider overlay 不存在：{patch}（应由接线层生成后传入）")

    def validate_values(self) -> None:
        """**值的形状**（与 enabled / 文件是否存在无关）：host 必须 loopback、端口/超时合法。

        解析期就调用 —— 坏值必须在接线/加载时炸，而不是拖到"要起实例的那一刻"
        （那时失败会被误读成"上游不可用"）。
        """
        if self.host not in _loopback_hosts():
            raise WebConfigError("host_not_loopback",
                                 f"dsh.web.host 必须是 loopback（{sorted(_loopback_hosts())}），得到 {self.host!r}")
        if not isinstance(self.preferred_port, int) or isinstance(self.preferred_port, bool) \
                or not 0 <= self.preferred_port <= 65535:
            raise WebConfigError("bad_port", f"preferred_port 必须是 0..65535 的整数，得到 {self.preferred_port!r}")
        if self.start_timeout_s <= 0 or self.stop_grace_s < 0:
            raise WebConfigError("bad_timeout", "start_timeout_s 必须 > 0，stop_grace_s 必须 >= 0")


def config_from_settings(document: dict[str, Any] | None = None, *,
                         base: Any) -> WebInstanceConfig:
    """从 `SETTINGS.yaml` 的 `loop.agent_runtime.dsh.web` 读 Web 实例配置。

    `base` 是既有 `dsh` 后端配置（duck-typed：需要 `.node`/`.bin`/`.version`）——
    **有意不 import `dsh.py`**：那是接线方（Lead 单点 writer），本模块只被它调用，
    双向 import 会让"谁是谁的依赖"变模糊。

    **接线契约**：`dsh.CONFIG_KEYS` 必须加 `"web"`，否则 `config_from_settings` 的未知字段
    判据会先拒（REV-16 §9-6 已登记同一坑）。
    """
    if document is None:
        import yaml

        try:
            document = yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            raise WebConfigError("settings_unreadable", "无法读取有效 SETTINGS YAML") from None
    runtime = ((document or {}).get("loop") or {}).get("agent_runtime") or {}
    dsh_raw = runtime.get("dsh") or {}
    if not isinstance(dsh_raw, dict):
        raise WebConfigError("settings_invalid", "agent_runtime.dsh 必须是 mapping")
    raw = dsh_raw.get("web") or {}
    if not isinstance(raw, dict):
        raise WebConfigError("settings_invalid", "agent_runtime.dsh.web 必须是 mapping")
    unknown = set(raw) - WEB_CONFIG_KEYS
    if unknown:
        raise WebConfigError("unknown_keys", f"agent_runtime.dsh.web 含未知字段：{sorted(unknown)}")
    home_raw = raw.get("home")
    # 空 ⇒ "未归属"兜底目录：生产路径由 `web_instance_ctl.ensure` 改写成 `<attempt>/dsh-home`
    # （S8b 收口后**没有**并列的 `dsh-web-home` 了，这里也不再沿用那个名字）。
    home = Path(str(home_raw)) if home_raw else (P.WORKSPACE_ROOT / "dsh-web-instance")
    # 空 ⇒ "未归属"兜底 cwd（单独装配/诊断用）；生产路径由 `web_instance_ctl.ensure`
    # 改写成 `<attempt>/work`（会话按 cwd 分组，见 `WebInstanceConfig.workdir`）
    workdir_raw = raw.get("workdir")
    workdir = Path(str(workdir_raw)) if workdir_raw else Path(P.TOOL_ROOT)
    config = WebInstanceConfig(
        enabled=bool(raw.get("enabled", False)),
        node=Path(str(base.node)), bin=Path(str(base.bin)), version=str(base.version),
        home=home, workdir=workdir,
        host=str(raw.get("host") or "127.0.0.1"),
        preferred_port=int(raw.get("preferred_port") or 0),
        start_timeout_s=float(raw.get("start_timeout_s") or 30.0),
        stop_grace_s=float(raw.get("stop_grace_s") or 5.0),
    )
    config.validate_values()
    return config


def build_argv(config: WebInstanceConfig, port: int) -> list[str]:
    """argv 用数组（绝不拼 shell 字符串）：只起 Web 面，`--no-open` 不开宿主浏览器。"""
    argv = [str(config.node), str(config.bin), "--profile", "web"]
    # **启动器级**选项 `--patch` 必须排在 app 参数**之前**（实测放在 `--no-open` 之后会被
    # 当成 app 选项：`error: unknown option '--patch'`，进程 rc=1 在公告行之前退出）。
    # 顺序即 patch 顺序；Web 只需要 provider overlay（不挂 attempt 的提交/自检插件）。
    for patch in config.patches:
        argv += ["--patch", str(patch)]
    argv += ["--host", config.host, "--port", str(port), "--no-open"]
    return argv


def build_env(config: WebInstanceConfig) -> dict[str, str]:
    """白名单环境：**不继承宿主**；只加 `config.env_extra` 里**显式**给的键。

    S8h 更正（REV-14 §9.4）：旧实现刻意不给凭据（理由"Web 面不调模型"），但 D3 要求
    "人可在 GUI 说话" ⇒ 人一进 GUI 就卡在 `Could not sign in / Add API Key`。
    现在由接线层经 `env_extra` 显式注入**同一份** provider 凭据与代理（仍只走 env、不落文件）。
    **代价**：凭据进入第二个进程的 env（D1 残余风险扩大）；白名单语义不变 —— 宿主 env
    仍不整体继承，只多出调用方显式列出的键。
    """
    env = {"PATH": "/usr/bin:/bin", "HOME": str(config.home), "DSH_HOME": str(config.home),
           "DSH_PROFILE": "web", "PYTHONDONTWRITEBYTECODE": "1"}
    for key in ("LANG", "LC_ALL", "TZ"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    for key, value in (config.env_extra or {}).items():
        if value is not None and str(value) != "":
            env[str(key)] = str(value)
    return env


@dataclass(frozen=True)
class LaunchTarget:
    """从 stdout 公告行解析出的**实际**监听目标（host/port）与 launch token。"""

    host: str
    port: int
    token: str | None

    @property
    def authority(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{host}:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://{self.authority}"

    def __repr__(self) -> str:  # 不把 token 带进 repr（异常/日志里会顺手打印对象）
        redacted = "None" if self.token is None else f"<redacted {len(self.token)} chars>"
        return f"LaunchTarget(host={self.host!r}, port={self.port}, token={redacted})"


def parse_launch_line(line: str) -> LaunchTarget | None:
    """解析 `dsh web: <url>`；不是公告行 ⇒ `None`（调用方继续等其他行）。

    硬判据（缺一即显式失败，不猜）：
    - 只认 `http(s)://` 绝对 URL；
    - host 必须是 loopback（写出非 loopback 目标的元数据会被读者拒，等于白起）；
    - **端口必须显式出现**（不带端口时不做 scheme 默认端口的推断：那是猜测）。
    """
    matched = LAUNCH_LINE_RE.match(line.strip())
    if matched is None:
        return None
    parts = urlsplit(matched.group("url"))
    if parts.scheme not in ("http", "https"):
        raise WebInstanceError("launch_url_invalid", "公告 URL 不是 http(s)")
    host = parts.hostname or ""
    if not host:
        raise WebInstanceError("launch_url_invalid", "公告 URL 没有 host")
    if host not in _loopback_hosts():
        raise WebInstanceError("launch_url_not_loopback", f"公告 URL 的 host 不是 loopback：{host!r}")
    try:
        port = parts.port
    except ValueError:
        raise WebInstanceError("launch_url_invalid", "公告 URL 的端口非法") from None
    if port is None:
        raise WebInstanceError("launch_url_invalid", "公告 URL 未显式给出端口（不做 scheme 默认端口的推断）")
    if not 1 <= port <= 65535:
        raise WebInstanceError("launch_url_invalid", f"公告 URL 的端口越界：{port}")
    tokens = parse_qs(parts.query).get(TOKEN_QUERY) or []
    token = tokens[0] if len(tokens) == 1 and tokens[0] else None
    return LaunchTarget(host=host, port=port, token=token)


def resolve_port(preferred_port: int) -> tuple[int, bool]:
    """端口策略：**优先固定**（先试 bind 一次确认空闲），占用/不可用 ⇒ 回落 `0`（OS 随机）。

    为什么不是"先起固定端口、失败再起一次随机"：那会多起一次实例（真实调用额度）。
    这里把回落决断放在**起进程之前**，一次起完；竞赛窗口由"起不来就显式失败"兜底，
    不静默重试（重试会把"端口被占"藏成"随机端口正常"，审计看不到）。

    返回 `(要传给 --port 的值, 是否发生了回落)`。
    """
    if preferred_port <= 0:
        return 0, False
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", preferred_port))
    except OSError:
        return 0, True
    finally:
        probe.close()
    return preferred_port, False


def health_check(target: LaunchTarget, *, timeout_s: float = HEALTH_TIMEOUT_S) -> None:
    """就绪判据：匿名 `GET /` 必须 **401**（服务在跑 + token 门在），否则显式失败。

    `trust_env=False`：本机有 `HTTP_PROXY/ALL_PROXY`，否则健康检查会走环境代理。
    **不**用 token 做健康检查 —— token 只该出现在受管元数据里。
    """
    client = httpx.Client(trust_env=False, timeout=timeout_s, follow_redirects=False)
    try:
        response = client.get(f"{target.origin}/")
    except (httpx.HTTPError, OSError) as exc:
        raise WebInstanceError("health_unreachable", type(exc).__name__) from None
    finally:
        client.close()
    if response.status_code != HEALTH_EXPECTED_STATUS:
        raise WebInstanceError(
            "health_unexpected_status",
            f"匿名 GET / 期望 {HEALTH_EXPECTED_STATUS}，实际 {response.status_code}"
            "（200 ⇒ token 门没上，不能当就绪）")


class WebInstance:
    """一个在跑的 DSH Web 实例（起/停/记账；token 只在内存与受管元数据里）。"""

    def __init__(self, config: WebInstanceConfig) -> None:
        self.config = config
        self._proc: subprocess.Popen[str] | None = None
        self._target: LaunchTarget | None = None
        self._stdout: deque[str] = deque(maxlen=LOG_TAIL_LINES)
        self._stderr: deque[str] = deque(maxlen=LOG_TAIL_LINES)
        self._threads: list[threading.Thread] = []
        self._launched = threading.Event()
        self._lock = threading.Lock()
        self.port_requested: int = 0
        self.port_fallback: bool = False
        self.started_at: float | None = None
        self.startup_s: float | None = None

    # ------------------------------------------------------------ 生命周期

    def start(self) -> "WebInstance":
        """起进程 → 等公告行 → 健康检查。任一步失败都**收干净**再抛（不留半死进程）。"""
        self.config.verify()
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.port_requested, self.port_fallback = resolve_port(self.config.preferred_port)
        argv = build_argv(self.config, self.port_requested)
        LOG.info("dsh web instance start: host=%s port_requested=%s fallback=%s home=%s cwd=%s",
                 self.config.host, self.port_requested, self.port_fallback, self.config.home,
                 self.config.workdir)
        begun = time.monotonic()
        try:
            self._proc = subprocess.Popen(  # noqa: S603 - argv 数组，无 shell
                argv, cwd=str(self.config.workdir or P.TOOL_ROOT), env=build_env(self.config),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, start_new_session=True)
        except OSError as exc:
            raise WebInstanceError("spawn_failed", type(exc).__name__) from None
        self.started_at = time.time()
        self._threads = [
            threading.Thread(target=self._pump, args=(self._proc.stdout, self._stdout, True),
                             name="dsh-web-stdout", daemon=True),
            threading.Thread(target=self._pump, args=(self._proc.stderr, self._stderr, False),
                             name="dsh-web-stderr", daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        try:
            self._await_launch_line()
            assert self._target is not None
            health_check(self._target)
        except WebInstanceError:
            self.stop()
            raise
        self.startup_s = round(time.monotonic() - begun, 3)
        LOG.info("dsh web instance ready: authority=%s startup_s=%s",
                 self._target.authority, self.startup_s)
        return self

    def _pump(self, stream: Any, sink: deque[str], is_stdout: bool) -> None:
        """持续排水（**必须一直读**：不读则管道写满 ⇒ dsh 卡在 write 上，表现为"假死"）。"""
        if stream is None:
            return
        for raw in stream:
            line = raw.rstrip("\n")
            with self._lock:
                sink.append(line)
            if is_stdout and LAUNCH_LINE_RE.match(line.strip()) and not self._launched.is_set():
                self._launched.set()

    def _await_launch_line(self) -> None:
        deadline = time.monotonic() + self.config.start_timeout_s
        while time.monotonic() < deadline:
            if self._launched.wait(timeout=0.05):
                break
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                # 公告行可能刚写进管道：再给排水线程一次机会
                self._launched.wait(timeout=0.2)
                if self._launched.is_set():
                    break
                raise WebInstanceError(
                    "exited_before_launch", f"进程在公告行之前退出（rc={proc.returncode}）")
        else:
            raise WebInstanceError("start_timeout",
                                   f"{self.config.start_timeout_s}s 内没等到 `dsh web:` 公告行")
        with self._lock:
            candidates = list(self._stdout)
        target = None
        for line in candidates:
            target = parse_launch_line(line)
            if target is not None:
                break
        if target is None:
            raise WebInstanceError("launch_line_invalid", "有公告行但解析不出目标")
        self._target = target

    def stop(self, *, remove_metadata: Path | None = None) -> None:
        """SIGTERM → grace → SIGKILL；整组收（`start_new_session` 起的进程组）后清句柄。"""
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            self._signal_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=self.config.stop_grace_s)
            except subprocess.TimeoutExpired:
                LOG.warning("dsh web instance: SIGTERM 未在 %ss 内退出，升级 SIGKILL",
                            self.config.stop_grace_s)
                self._signal_group(proc, signal.SIGKILL)
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    LOG.error("dsh web instance: SIGKILL 后仍未退出（pid=%s）", proc.pid)
        for thread in self._threads:
            thread.join(timeout=2.0)
        self._threads = []
        if remove_metadata is not None:
            clear_metadata(remove_metadata)
        self._target = None
        LOG.info("dsh web instance stopped")

    @staticmethod
    def _signal_group(proc: subprocess.Popen[str], signum: int) -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signum)
        except (ProcessLookupError, PermissionError):
            try:
                proc.send_signal(signum)
            except ProcessLookupError:
                pass

    def __enter__(self) -> "WebInstance":
        return self.start()

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()

    # ------------------------------------------------------------ 观测

    @property
    def target(self) -> LaunchTarget:
        if self._target is None:
            raise WebInstanceError("not_started", "实例未就绪（没有解析到监听目标）")
        return self._target

    @property
    def pid(self) -> int | None:
        return None if self._proc is None else self._proc.pid

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def describe(self) -> dict[str, Any]:
        """诊断摘要（**不含 token**）：端口/pid/启动耗时/回落事实/尾部日志。"""
        target = self._target
        with self._lock:
            stderr_tail = list(self._stderr)[-5:]
        return {"host": None if target is None else target.host,
                "port": None if target is None else target.port,
                "pid": self.pid, "running": self.is_running(),
                "port_requested": self.port_requested, "port_fallback": self.port_fallback,
                "startup_s": self.startup_s, "stderr_tail": stderr_tail}

    def __repr__(self) -> str:
        return f"WebInstance(host={self.config.host!r}, target={self._target!r})"

    # ------------------------------------------------------------ 落账

    def metadata(self, *, node: str, attempt: int,
                 session_log: str | None = None) -> dict[str, Any]:
        """`REV-16 §5.2` 的元数据文档（字段集固定，不夹带宿主细节）。"""
        target = self.target
        document: dict[str, Any] = {"node": node, "attempt": attempt,
                                    "host": target.host, "port": target.port,
                                    "token": target.token, "written_at": P.now_iso()}
        if session_log is not None:
            document["session_log"] = _relative_ref(session_log)
        return document

    def write_metadata(self, run_dir: Path | str, *, node: str, attempt: int,
                       session_log: str | None = None) -> Path:
        """原子写 `<run_dir>/agent_instance.json`（tmp + fsync + `os.replace`，权限 0600）。"""
        document = self.metadata(node=node, attempt=attempt, session_log=session_log)
        return write_metadata_document(run_dir, document)


def _relative_ref(session_log: str) -> str:
    """`session_log` 必须是**相对**路径且不含 `..`（读者的 `_resolve_session_log` 只收这种）。"""
    if not session_log or Path(session_log).is_absolute():
        raise WebInstanceError("session_log_invalid", "session_log 必须是相对 run_dir 的路径")
    parts = Path(session_log).parts
    if ".." in parts:
        raise WebInstanceError("session_log_invalid", "session_log 不得含 .. 段")
    return session_log


def metadata_path(run_dir: Path | str) -> Path:
    return Path(run_dir) / _metadata_name()


def write_metadata_document(run_dir: Path | str, document: dict[str, Any]) -> Path:
    """原子写：同目录临时文件（0600）→ fsync → `os.replace`；失败则删临时文件。"""
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    final = metadata_path(directory)
    tmp = directory / f".{final.name}.tmp-{os.getpid()}-{threading.get_ident()}"
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, METADATA_MODE)
        try:
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, final)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise WebInstanceError("metadata_write_failed", type(exc).__name__) from None
    return final


def clear_metadata(run_dir: Path | str) -> bool:
    """删掉本实例的落账（实例停了 ⇒ 读者按 `target_missing` 显式降级，而不是连一个死端口）。"""
    try:
        metadata_path(run_dir).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise WebInstanceError("metadata_clear_failed", type(exc).__name__) from None


def start(config: WebInstanceConfig) -> WebInstance:
    """便捷入口：装配 → 起 → 就绪检查（失败时不留进程）。"""
    return WebInstance(config).start()
