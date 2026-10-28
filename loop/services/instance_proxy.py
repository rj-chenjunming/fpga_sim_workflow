"""同源反代 `/instance/<run_id>/<node>/<attempt>/`（SPEC-REV-16 §5；REV-14 Q7 裁决）。

为什么是反代而不是 iframe 直连：跨站 iframe 不可用（P8 实测 —— 匿名 401、只能 `?token=`
换 `SameSite=Strict` cookie、`/api` 跨权威 403）。同源反代恢复"看起来同源"的语义；
朴素反代 = 开放代理 / SSRF / 凭据泄露面，因此本模块的**准入与拒绝判据是主要交付**：

- 目标**只能**来自受管元数据 `<run_dir>/agent_instance.json`（Host 落账，写入方属 S5）。
  客户端 query / body / 头里的任何 `url`/`port`/`token` 一律**丢弃**（不是"校验后使用"）。
- 目标只允许 loopback；非 loopback / 坏端口 ⇒ 显式不可用（`target_not_loopback`/`target_invalid`），
  不静默转发、不回落别的目标。
- 路径判据看**两层**：(a) 服务器已解码一次的 `path`；(b) `raw_path` 再解一次/两次。
  uvicorn 实测：`%2e%2e`→`..`、`%2f`→`/`、`%252e%252e` 只解到 `%2e%2e`（需再解）、`%00`→NUL。
- token 只在"元数据有 token 且本次请求无 cookie"时注入上游 query；**永不出现在**
  本服务日志 / 错误体 / JSON / 响应头 / 错误页 HTML。
- 不可用是**显式状态**（503 + `X-Instance-Proxy: unavailable` + `reason` 枚举）：
  JSON 或 HTML 两种表现都有明确语义，绝不 500 空白、绝不假装可内嵌。
- 不转发 hop-by-hop 与 `Forwarded`/`X-Forwarded-*`/`Via`/`Proxy-*`；不转发客户端 `Authorization`。
- 响应侧：删 `X-Frame-Options`（同源 iframe 需要）；CSP 只把 `frame-ancestors` 换成 `'self'`，
  其余指令逐字保留（多头实例逐个处理）；`Set-Cookie` 删 `Domain` 且 `Path` 收到实例前缀；
  `Location` 改写回同源前缀并剥离 token。
- 不缓存、不落盘、不写 run 目录。

**本片边界（REV-16 §9-10，2026-10-28 裁决）**：只保证"页面文档可加载 + 降级块可承接"。
**不做** HTML 重写、不注入 `<base href>`、不改上游内容 —— 上游若用绝对资源路径
（`/assets/…`、`/api/…`），iframe 内的资源请求会落到看板根，属 S5 真机实测后再定的问题
（上游 base path 配置 / 降级块承接）。因此 `availability()` 的 `embed` 语义是
"只要目标可开就给 iframe；资源断了用户走新标签页"，**不在 S4 声称已验证资源路径**。

实现纪律：本模块**不新增**第二套解码/重试/健康判据 —— HTTP 客户端只用 `httpx`
（`trust_env=False`：本机有 `HTTP_PROXY/ALL_PROXY`，否则会走环境代理），超时是显式常量。
"""

from __future__ import annotations

import json
import logging
import posixpath
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import httpx
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from urllib.parse import quote, unquote, unquote_plus, urlsplit

LOG = logging.getLogger(__name__)

#: P2-3（安全）：httpx 在 **INFO** 级会打印完整请求 URL，而受管 token 就注入在 query 里。
HTTP_CLIENT_LOGGERS = ("httpx", "httpcore")


def silence_http_client_logging() -> None:
    """把 httpx/httpcore 的日志压到 WARNING —— **显式声明**，不靠任何第三方库碰巧设过级别。"""
    for name in HTTP_CLIENT_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# 模块 import 即生效：服务只需要 `from services import instance_proxy` 就拿到这条安全边界，
# 不依赖部署时的 uvicorn 默认日志级别（uvicorn 不配置 httpx logger）。
silence_http_client_logging()

#: 反代前缀（与 SPEC-REV-16 §5.1 路由一致）
PREFIX = "/instance"
#: 受管元数据文件名（Host 落账；本片只读）
METADATA_NAME = "agent_instance.json"
#: 拒绝矩阵 R8 的长度上限
MAX_PATH_LEN = 2048
MAX_QUERY_LEN = 4096
#: R12：显式超时常量（连接 1.0 s / 读 15 s）；测试 monkeypatch 小值，不空转
CONNECT_TIMEOUT_S = 1.0
READ_TIMEOUT_S = 15.0
#: 会话副本内容上限（§6.2 "有大小上限"）
SESSION_COPY_MAX_BYTES = 64 * 1024

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
ALLOWED_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")

#: R14：客户端用来指定目标的 query 参数（值被丢弃，不是"校验后使用"）。
#: §5.2 写的是"含 url/port/token"（非穷举）⇒ `host` 同组丢弃，客户端任何目标信息都无效。
TARGET_PARAMS = frozenset({"token", "url", "port", "host"})

#: 请求侧不转发的头（hop-by-hop + R16 的代理链头 + 客户端凭据 + 表示层协商头）
_DROP_REQUEST_HEADERS = frozenset({
    "host", "connection", "keep-alive", "proxy-connection", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade", "expect",
    "authorization", "forwarded", "via",
    # 表示层协商归本层：若把浏览器的 `br` 原样转给上游，而我们又必须丢掉
    # `Content-Encoding`（httpx 解码后才转发），浏览器会收到"标称 identity 的压缩字节"。
    "accept-encoding",
})
_DROP_REQUEST_PREFIXES = ("x-forwarded-", "proxy-")
#: 响应侧不转发的头（hop-by-hop / 我们重算的表示层头）
_DROP_RESPONSE_HEADERS = frozenset({
    "content-length", "content-encoding", "transfer-encoding", "connection",
    "keep-alive", "proxy-connection", "te", "trailer", "upgrade",
})

_ENCODED_SLASH = re.compile(r"%2f|%2F")
_FRAME_ANCESTORS = re.compile(r"(?i)\bframe-ancestors\b[^;]*")

#: §5.5 不可用原因枚举（唯一来源；界面/测试据此判定）
REASONS = frozenset({
    "target_missing", "target_not_loopback", "target_invalid",
    "upstream_unreachable", "upstream_timeout", "upstream_auth",
    "upstream_error", "health_unknown",
})

_REASON_TEXT = {
    "target_missing": "实例未登记（Host 尚未落账 agent_instance.json）",
    "target_not_loopback": "实例目标不是 loopback（按 SSRF 面拒绝转发）",
    "target_invalid": "实例目标元数据非法（host/port）",
    "upstream_unreachable": "上游实例不可达",
    "upstream_timeout": "上游实例超时",
    "upstream_auth": "上游实例鉴权失败（401/403）",
    "upstream_error": "上游实例 5xx",
    "health_unknown": "上游健康状态未知",
}


# ================================================================ 异常


class Rejected(Exception):
    """§5.3 拒绝（R1–R8、R14）：400/404，**不转发**，不回显输入原文。"""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(detail)
        self.rule = rule
        self.detail = detail


class TargetUnavailable(Exception):
    """§5.5 不可用（R9–R13）：503 + reason，显式状态。"""

    def __init__(self, reason: str) -> None:
        if reason not in REASONS:
            raise ValueError(f"未知不可用原因：{reason!r}")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class InstanceTarget:
    """受管元数据解析出的上游目标（只可能来自 `agent_instance.json`）。"""

    host: str
    port: int
    node: str
    attempt: int
    token: str | None = None

    @property
    def authority(self) -> str:
        host = self.host
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{host}:{self.port}"

    @property
    def origin(self) -> str:
        return f"http://{self.authority}"


# ================================================================ 纯判据（§5.3）


def validate_host(host_header: str | None) -> str:
    """R7：`Host` 只认本服务 loopback 名（可带端口）；其余 400，不转发。"""
    raw = host_header if host_header is not None else ""
    if not raw or raw != raw.strip():
        raise Rejected("R7", "Host 头缺失或含首尾空白")
    if raw.startswith("["):
        matched = re.fullmatch(r"\[([0-9A-Fa-f:.]+)\](?::(\d{1,5}))?", raw)
        if matched is None:
            raise Rejected("R7", "Host 头 IPv6 形式非法")
        host, port = matched.group(1), matched.group(2)
    else:
        host, sep, port = raw.partition(":")
        if not sep:
            port = None
    if port is not None and not (port.isdigit() and 1 <= int(port) <= 65535):
        raise Rejected("R7", "Host 头的端口非法")
    if host.lower() not in LOOPBACK_HOSTS:
        raise Rejected("R7", "Host 头不是本服务的 loopback 名")
    return raw


def _decode_layers(path: str, raw_path: str) -> Iterable[tuple[str, str]]:
    """路径的所有解码层级：纯观测用（调用方决定每一层对应哪条规则）。"""
    yield "path", path
    yield "path~1", unquote(path)
    yield "path~2", unquote(unquote(path))
    if raw_path:
        yield "raw", raw_path
        yield "raw~1", unquote(raw_path)
        yield "raw~2", unquote(unquote(raw_path))


def validate_path(path: str, raw_path: str) -> str:
    """R1–R6、R8：路径准入（解码后校验；拒绝即不转发，也不把输入原文塞进错误体）。"""
    if not isinstance(path, str) or not isinstance(raw_path, str):
        raise Rejected("R1", "路径类型非法")
    if len(path) > MAX_PATH_LEN or len(raw_path) > MAX_PATH_LEN:
        raise Rejected("R8", f"路径超长（>{MAX_PATH_LEN}，含原始编码长度）")
    if _ENCODED_SLASH.search(raw_path):
        # 段边界在原始请求里被编码 ⇒ 不可信（R4）
        raise Rejected("R4", "路径含编码的 /（%2f），段边界不可信")
    lower_raw = raw_path.lower()
    if ".." in path:
        rule = "R2" if "%2e" in lower_raw else "R1"
        raise Rejected(rule, "路径含 .. 段")
    if ".." in unquote(path):
        # 服务器已解一次、这里再解才见 .. ⇒ 双编码（R3）；否则只是一次编码（R2）
        rule = "R3" if "%2e" in path.lower() else "R2"
        raise Rejected(rule, "路径解码后含 .. 段")
    for _, candidate in _decode_layers(path, raw_path):
        if ".." in candidate:
            raise Rejected("R3", "路径多次解码后含 .. 段")
    for _, candidate in _decode_layers(path, raw_path):
        if "\\" in candidate or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
            raise Rejected("R6", "路径含控制字符或反斜杠")
    if path.startswith("/") or "://" in path:
        raise Rejected("R5", "路径是绝对 URI 或协议相对形式")
    head = path.split("/", 1)[0]
    if "@" in head or ":" in head:
        raise Rejected("R5", "路径在 authority 位置含 @ 或 :")
    return path


def _filter_target_params(raw_query: str) -> str:
    """丢掉客户端用来指定目标的参数（R14），其余 query 逐字保留。"""
    kept: list[str] = []
    for part in (raw_query or "").split("&"):
        if not part:
            continue
        name = unquote_plus(part.split("=", 1)[0]).strip().lower()
        if name in TARGET_PARAMS:
            continue
        kept.append(part)
    return "&".join(kept)


def validate_query(raw_query: str) -> str:
    """R6/R8/R14：query 准入 + 丢弃客户端目标参数。"""
    raw_query = raw_query or ""
    if len(raw_query) > MAX_QUERY_LEN:
        raise Rejected("R8", f"query 超长（>{MAX_QUERY_LEN}）")
    for _, candidate in (("raw", raw_query), ("raw~1", unquote(raw_query))):
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
            raise Rejected("R6", "query 含控制字符")
    return _filter_target_params(raw_query)


def parse_attempt(value: Any) -> int:
    """`attempt` 只接受 >= 1 的整数（路由段是字符串）。"""
    try:
        attempt = int(str(value))
    except (TypeError, ValueError):
        raise Rejected("attempt", "attempt 不是整数") from None
    if attempt < 1:
        raise Rejected("attempt", "attempt 必须 >= 1")
    return attempt


# ================================================================ 受管目标（§5.2）


def load_target(run_dir: Path | str, node: str, attempt: int | None) -> InstanceTarget:
    """从 Host 落账的实例声明读目标；**绝不**接受客户端输入。

    `attempt=None` 表示"按元数据声明的 attempt"（可用性端点/会话副本允许显式带 attempt，
    也可省略后由受管元数据决定 —— 多 attempt 场景不能钉死 1，REV-16 §6.1 P1-1）。
    归属按 **(node, attempt)** 粒度：声明不是本 node、或与请求 attempt 不符 ⇒ `target_missing`。

    `target_missing` = 文件不存在 / 这条声明不是本 node 本 attempt 的；
    `target_invalid` = 文件坏 / 字段非法；`target_not_loopback` = 目标不在 loopback。
    """
    path = Path(run_dir) / METADATA_NAME
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise TargetUnavailable("target_missing") from None
    except json.JSONDecodeError:
        raise TargetUnavailable("target_invalid") from None
    except OSError:
        raise TargetUnavailable("target_invalid") from None
    if not isinstance(document, dict):
        raise TargetUnavailable("target_invalid")
    declared_attempt = document.get("attempt")
    if isinstance(declared_attempt, bool) or not isinstance(declared_attempt, int):
        raise TargetUnavailable("target_invalid")
    if str(document.get("node")) != node:
        raise TargetUnavailable("target_missing")
    if attempt is not None and declared_attempt != attempt:
        raise TargetUnavailable("target_missing")
    effective_attempt = declared_attempt if attempt is None else attempt
    host = document.get("host")
    if not isinstance(host, str) or not host:
        raise TargetUnavailable("target_invalid")
    if host.lower() not in LOOPBACK_HOSTS:
        raise TargetUnavailable("target_not_loopback")
    port = document.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise TargetUnavailable("target_invalid")
    token = document.get("token")
    if token is not None and not isinstance(token, str):
        raise TargetUnavailable("target_invalid")
    return InstanceTarget(host=host, port=port, node=node, attempt=effective_attempt,
                          token=(token or None))


def instance_prefix(run_id: str, node: str, attempt: int) -> str:
    """实例前缀（**以 / 结尾**，用于 cookie Path / Location / iframe src）。"""
    return f"{PREFIX}/{run_id}/{node}/{attempt}/"


def availability(run_dir: Path | str, *, run_id: str, node: str,
                 attempt: int | None) -> dict[str, Any]:
    """§6.1 可用性端点：只读判定，不探测上游（不新增第二套健康判据）。

    归属按 **(node, attempt)** 粒度：`attempt` 省略 ⇒ 用受管元数据声明的 attempt；
    显式给了则必须与元数据一致，否则 `target_missing`。响应 `attempt` 回显**实际判定**的
    attempt，`url` 用同一个值（多 attempt 场景不得钉死 1）。

    `available=true` 只表示"目标元数据可用且 loopback"；上游是否活着由反代请求本身暴露
    （iframe 加载失败 ⇒ 界面降级，§6.2）。`embed="iframe"` 只表示"值得尝试内嵌"，
    **不**表示已验证页面资源路径（§9-10：本片不做 HTML 重写；资源断走新标签页）。
    """
    try:
        target = load_target(run_dir, node, attempt)
    except TargetUnavailable as exc:
        return {"available": False, "state": "unavailable", "reason": exc.reason,
                "url": None, "embed": "new_tab_only", "authority": "projection",
                "attempt": attempt}
    return {"available": True, "state": "ready", "reason": None,
            "url": instance_prefix(run_id, node, target.attempt), "embed": "iframe",
            "authority": "projection", "attempt": target.attempt}


def _resolve_session_log(run_dir: Path | str, ref: str) -> Path:
    """`agent_instance.json.session_log` 只接受**相对 run_dir** 的普通文件（§5.2）。

    绝对路径 / 越界 / 符号链接一律拒绝：它们会让"导出会话副本"变成任意文件读取面。
    """
    if not ref or Path(ref).is_absolute():
        raise ValueError("session_log 必须是相对 run_dir 的路径")
    base = Path(run_dir).resolve()
    candidate = base / ref
    if candidate.is_symlink():
        raise ValueError("session_log 不能是符号链接")
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise ValueError(f"session_log 解析失败：{exc}") from None
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError("session_log 越出 run 目录") from None
    return resolved


def session_copy(run_dir: Path | str, *, node: str,
                 attempt: int | None) -> dict[str, Any]:
    """§6.2 会话副本：只返回 **session log 的解析事实**（`kind="session_log_facts"`）。

    口径（REV-16 §6.2 修正 / §9-11）：内容来自 `dsh_sdk.read_session_log` 的唯一解码实现
    —— 这是**压缩事实**（`CompactionFacts`），**不是**可读会话原文；原文导出列未决，不声称。

    归属按 **(node, attempt)** 粒度（P2-1）：`agent_instance.json` 声明的 node 不是本节点、
    或（显式给了 attempt 时）与声明 attempt 不符 ⇒ `session_owner_mismatch` ——
    任意节点窗口不能借这个端点导出别节点/别 attempt 的会话事实。
    `attempt` 省略 ⇒ 用元数据声明的 attempt 并在响应 `attempt` 里回显。

    来源 = `agent_instance.json.session_log`（相对 run_dir，越界/符号链接拒绝，写入方属 S5）；
    缺失即 `session_log_missing`。
    """
    from host.agent_backends import dsh_sdk

    document: Any
    try:
        document = json.loads((Path(run_dir) / METADATA_NAME).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _session_unavailable("session_metadata_missing", attempt=attempt)
    except (OSError, json.JSONDecodeError):
        return _session_unavailable("session_metadata_invalid", attempt=attempt)
    if not isinstance(document, dict):
        return _session_unavailable("session_metadata_invalid", attempt=attempt)
    declared_attempt = document.get("attempt")
    if isinstance(declared_attempt, bool) or not isinstance(declared_attempt, int):
        return _session_unavailable("session_metadata_invalid", attempt=attempt)
    if str(document.get("node")) != node:
        return _session_unavailable("session_owner_mismatch", attempt=attempt)
    if attempt is not None and attempt != declared_attempt:
        return _session_unavailable("session_owner_mismatch", attempt=attempt)
    effective_attempt = declared_attempt if attempt is None else attempt

    log_ref = document.get("session_log")
    if not isinstance(log_ref, str) or not log_ref:
        return _session_unavailable("session_log_missing", attempt=effective_attempt)

    try:
        log_path = _resolve_session_log(run_dir, log_ref)
    except ValueError:
        return _session_unavailable("session_log_invalid", attempt=effective_attempt)
    try:
        facts = dsh_sdk.read_session_log(log_path)
    except (dsh_sdk.SessionLogError, OSError):
        return _session_unavailable("session_log_unavailable", attempt=effective_attempt)
    if facts.availability != dsh_sdk.AVAILABILITY_OK:
        return _session_unavailable(facts.reason or "session_log_unavailable",
                                    attempt=effective_attempt)

    payload = asdict(facts)
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    truncated = len(encoded) > SESSION_COPY_MAX_BYTES
    if truncated:  # 有上限：先砍明细（计数仍是源事实，不重算、不猜测）
        payload["records"] = payload.get("records", [])[:10]
        payload["errors"] = payload.get("errors", [])[:10]
        encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return {"available": True, "reason": None, "kind": "session_log_facts",
            "facts": payload, "bytes": len(encoded), "truncated": truncated,
            "attempt": effective_attempt}


def _session_unavailable(reason: str, *, attempt: int | None) -> dict[str, Any]:
    return {"available": False, "reason": reason, "kind": None,
            "facts": None, "bytes": None, "truncated": False, "attempt": attempt}


# ================================================================ 转发与头改写（§5.4）


def build_upstream_url(target: InstanceTarget, path: str, query: str,
                       token: str | None) -> str:
    """上游 URL = `http://{host}:{port}/{path}` + 过滤后的 query（+ 受管 token）。"""
    encoded = quote(path, safe="/~!$&'()*+,;=:@-._")
    url = f"{target.origin}/{encoded}"
    if token:
        injection = f"token={quote(token, safe='')}"
        query = f"{query}&{injection}" if query else injection
    return f"{url}?{query}" if query else url


def _rewrite_referer(value: str, target: InstanceTarget, prefix_root: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return f"{target.origin}/"
    if parts.path.startswith(prefix_root):
        path = "/" + parts.path[len(prefix_root):]
    else:
        path = "/"
    query = _filter_target_params(parts.query)
    return f"{target.origin}{path}" + (f"?{query}" if query else "")


def upstream_headers(incoming: Mapping[str, str], target: InstanceTarget,
                     *, prefix_root: str) -> dict[str, str]:
    """请求头：丢 hop-by-hop/R16/客户端凭据，`Host` 改写目标 authority，恢复同源语义。"""
    out: dict[str, str] = {}
    for name, value in incoming.items():
        low = name.lower()
        if low in _DROP_REQUEST_HEADERS or low.startswith(_DROP_REQUEST_PREFIXES):
            continue
        out[low] = value
    out["host"] = target.authority
    if "origin" in out:
        out["origin"] = target.origin
    if "referer" in out:
        out["referer"] = _rewrite_referer(out["referer"], target, prefix_root)
    if "sec-fetch-site" in out:
        # 同源反代下的正确语义就是 same-origin；不改写则 DSH `/api` 按围栏回 403（P8 实测）
        out["sec-fetch-site"] = "same-origin"
    return out


def narrow_csp(value: str) -> str:
    """R18：只把 `frame-ancestors` 指令换成 `'self'`，其余指令逐字保留。"""
    return _FRAME_ANCESTORS.sub("frame-ancestors 'self'", value)


def rewrite_set_cookie(value: str, prefix_root: str) -> str:
    """R17：删 `Domain`、`Path` 收到实例前缀，其余属性逐字保留。"""
    parts = [part.strip() for part in value.split(";")]
    name_value = parts[0]
    attributes = [part for part in parts[1:]
                  if part and not part.lower().startswith(("domain=", "path="))]
    return "; ".join([name_value, f"Path={prefix_root}", *attributes])


def rewrite_location(location: str, *, target: InstanceTarget, prefix_root: str,
                     injected_token: str | None) -> str:
    """R15：上游 `Location` 收回同源前缀并剥离 token（绝对地址/相对地址两种都处理）。"""
    if injected_token and injected_token in location:
        # token 落在 path 里无法安全保留 ⇒ 一律收回前缀（宁可少跳一步，也不让 token 进地址栏）
        if injected_token not in urlsplit(location).query:
            return prefix_root
    try:
        parts = urlsplit(location)
    except ValueError:
        return prefix_root
    if parts.scheme or parts.netloc:
        if parts.netloc and parts.netloc.lower() != target.authority.lower():
            return prefix_root  # 指向上游之外 ⇒ 不跟随
        path = parts.path or "/"
    elif location.startswith("/"):
        path = parts.path
    else:
        path = posixpath.normpath(posixpath.join("/", parts.path))
    if ".." in path.split("/"):
        return prefix_root
    mapped = prefix_root + path.lstrip("/")
    if not mapped.startswith(prefix_root):
        return prefix_root
    query = _filter_target_params(parts.query)
    return mapped + (f"?{query}" if query else "")


def response_headers(items: Iterable[tuple[str, str]], *, target: InstanceTarget,
                     prefix_root: str, injected_token: str | None) -> list[tuple[str, str]]:
    """响应头改写：R15/R17/R18/R20 + 丢 hop-by-hop 与表示层头。"""
    out: list[tuple[str, str]] = []
    for name, value in items:
        low = name.lower()
        if low in _DROP_RESPONSE_HEADERS:
            continue
        if low == "x-frame-options":  # R20
            continue
        if low == "content-security-policy":  # R18（多头实例逐个处理）
            out.append((name, narrow_csp(value)))
            continue
        if low == "set-cookie":  # R17
            out.append((name, rewrite_set_cookie(value, prefix_root)))
            continue
        if low == "location":  # R15
            out.append((name, rewrite_location(value, target=target,
                                               prefix_root=prefix_root,
                                               injected_token=injected_token)))
            continue
        out.append((name, value))
    return out


# ================================================================ 显式不可用 / 拒绝响应（§5.5）


def _wants_html(accept: str | None) -> bool:
    return "text/html" in (accept or "").lower()


def _error_page(title: str, detail: str, *, link: str | None) -> str:
    action = (f'<p><a href="{link}" target="_blank" rel="noopener">在新标签页打开</a></p>'
              if link else "")
    return ("<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body><h1>{title}</h1>"
            f"<p>{detail}</p>{action}"
            "<p><strong>显式不可用态</strong>：不可内嵌，也不会伪装成已加载。</p>"
            "</body></html>")


def unavailable_response(reason: str, *, accept: str | None = "", prefix_root: str | None = None) -> Response:
    """503 + `X-Instance-Proxy: unavailable`；HTML/JSON 两种语义都不回显 token。"""
    if reason not in REASONS:
        raise ValueError(f"未知不可用原因：{reason!r}")
    headers = {"x-instance-proxy": "unavailable", "x-instance-proxy-reason": reason,
               "cache-control": "no-store"}
    if _wants_html(accept):
        return HTMLResponse(_error_page("实例不可用", _REASON_TEXT[reason], link=prefix_root),
                            status_code=503, headers=headers)
    return JSONResponse({"available": False, "state": "unavailable", "reason": reason,
                         "url": None, "embed": "new_tab_only", "authority": "projection"},
                        status_code=503, headers=headers)


def rejected_response(exc: Rejected, *, accept: str | None = "") -> Response:
    """400（未知 run/node 由调用方给 404）+ `X-Instance-Proxy: rejected`；不回显输入原文。"""
    headers = {"x-instance-proxy": "rejected", "x-instance-proxy-rule": exc.rule,
               "cache-control": "no-store"}
    if _wants_html(accept):
        return HTMLResponse(_error_page("请求被反代拒绝", f"规则 {exc.rule}：{exc.detail}",
                                        link=None),
                            status_code=400, headers=headers)
    return JSONResponse({"detail": {"error": exc.detail, "rule": exc.rule,
                                    "state": "rejected"}},
                        status_code=400, headers=headers)


def method_not_allowed_response(detail: str = "") -> Response:
    """405：CONNECT/TRACE/WebSocket 升级不转发（§5.1；升级支持属 §9-2 未决）。"""
    return JSONResponse(
        {"detail": {"error": detail or "反代只透传 HTTP 方法；CONNECT/TRACE/Upgrade 不支持",
                    "state": "rejected"}},
        status_code=405,
        headers={"allow": ", ".join(ALLOWED_METHODS), "x-instance-proxy": "rejected"},
    )


class _RawHeadersStreamingResponse(StreamingResponse):
    """允许**重复头**（多个 `Set-Cookie`/`Content-Security-Policy`）的流式响应。"""

    def __init__(self, content: Any, *, status_code: int,
                 raw: list[tuple[str, str]], media_type: str | None = None) -> None:
        super().__init__(content, status_code=status_code, media_type=media_type)
        self.raw_headers = [(name.lower().encode("latin-1"), str(value).encode("latin-1"))
                            for name, value in raw]


def _raw_path_of(request: Request) -> str:
    raw = request.scope.get("raw_path")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("latin-1")
    return ""


def _raw_query_of(request: Request) -> str:
    raw = request.scope.get("query_string")
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw).decode("latin-1")
    return ""


def _is_upgrade_request(headers: Mapping[str, str]) -> bool:
    for name, value in headers.items():
        low = name.lower()
        if low == "upgrade" and value.strip():
            return True
        if low == "connection" and "upgrade" in value.lower():
            return True
    return False


async def forward(request: Request, *, run_dir: Path | str, run_id: str, node: str,
                  attempt: Any, path: str) -> Response:
    """唯一反代入口：准入 → 受管目标 → 转发 → 头改写；失败一律显式。"""
    accept = request.headers.get("accept", "")
    if _is_upgrade_request(request.headers):
        return method_not_allowed_response("WebSocket/Upgrade 不支持（§9-2 未决）")

    prefix_root = ""
    try:
        validate_host(request.headers.get("host"))
        attempt_value = parse_attempt(attempt)
        prefix_root = instance_prefix(run_id, node, attempt_value)
        safe_path = validate_path(path, _raw_path_of(request))
        query = validate_query(_raw_query_of(request))
        target = load_target(run_dir, node, attempt_value)
    except Rejected as exc:
        LOG.warning("instance proxy rejected: rule=%s", exc.rule)
        return rejected_response(exc, accept=accept)
    except TargetUnavailable as exc:
        LOG.warning("instance proxy unavailable: reason=%s", exc.reason)
        return unavailable_response(exc.reason, accept=accept, prefix_root=prefix_root or None)

    has_cookie = any(name.lower() == "cookie" for name in request.headers)
    injected = target.token if (target.token and not has_cookie) else None
    url = build_upstream_url(target, safe_path, query, injected)
    headers = upstream_headers(request.headers, target, prefix_root=prefix_root)
    body: bytes | None = None
    if request.method not in ("GET", "HEAD"):
        body = await request.body()

    timeout = httpx.Timeout(connect=CONNECT_TIMEOUT_S, read=READ_TIMEOUT_S,
                            write=READ_TIMEOUT_S, pool=CONNECT_TIMEOUT_S)
    client = httpx.AsyncClient(trust_env=False, timeout=timeout)
    try:
        upstream_request = client.build_request(request.method, url, headers=headers,
                                                content=body)
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        await client.aclose()
        return unavailable_response("upstream_timeout", accept=accept, prefix_root=prefix_root)
    except (httpx.HTTPError, OSError):
        await client.aclose()
        return unavailable_response("upstream_unreachable", accept=accept,
                                    prefix_root=prefix_root)

    status = upstream_response.status_code
    if status in (401, 403):  # R13：不得把上游鉴权墙当页面转给浏览器
        await upstream_response.aclose()
        await client.aclose()
        return unavailable_response("upstream_auth", accept=accept, prefix_root=prefix_root)

    out_headers = response_headers(list(upstream_response.headers.multi_items()),
                                   target=target, prefix_root=prefix_root,
                                   injected_token=injected)
    if injected is not None and status in (301, 302, 303, 307, 308):
        status = 303  # §5.4：让浏览器落到"去掉 token 的同路径"、只保留 cookie
    if status >= 500:  # R19
        out_headers.append(("x-instance-proxy", "unavailable"))
        out_headers.append(("x-instance-proxy-reason", "upstream_error"))

    async def stream_body():
        try:
            async for chunk in upstream_response.aiter_bytes():
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    return _RawHeadersStreamingResponse(stream_body(), status_code=status, raw=out_headers)
