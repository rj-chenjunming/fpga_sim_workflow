"""S7c 接线：Host 侧"起/停常驻 DSH Web 实例 + 落账 `agent_instance.json`"的唯一入口。

**为什么单独一层**：`dsh_web_instance` 只负责"起进程 / 解析公告行 / 健康检查 / 原子写元数据"
（纯机制）；本模块负责**编排决策**——给哪个 `(run, node, attempt)` 起、`home` 落在哪、
已有实例怎么替换、什么时候清落账。决策只此一处，读者（`services/instance_proxy`）不参与。

**三条硬纪律**：
1. **不自启动**：没有任何代码在 attempt 生命周期里偷偷起 Web 实例。`SETTINGS.dsh.web.enabled`
   只是"允许被启动"；真的要起必须**显式**调用本模块（CLI 或未来编排钩子）。
   ⇒ `enabled: false`（仓内默认）时连显式调用也拒（`web_disabled`），要用必须同时 `--enable`。
2. **home 不与 attempt 共用**：实例 home = `<attempt>/dsh-web-home`，**不是** `<attempt>/dsh-home`。
   理由（实测，2026-10-29）：`dsh --profile web` 会在 home 里自生成 `.credentials.yaml`
   （cookie 签名 secret），而 `dsh_assets.FORBIDDEN_HOME_ENTRIES` 把它判成"attempt home 含宿主件"
   ⇒ 若共用 dsh-home，**下一次复用该 home 的 attempt 会在 DS-09 准入阶段失败**。
   改成并列目录即可，**不改 DS-09 判据**（判据变更要单独变更 + 留证）。
   代价：Web 与 attempt **不共用 home** ⇒ REV-14 D3「人在 GUI 看到 attempt 会话」**未落地**，
   登记未决（计划 §8-9 / STATUS §120.6）；`agent_instance.json.session_log` 仍指向该 attempt 的
   session log，所以「导出会话副本」这条路可用。
3. **token 永不回显**：本模块的任何返回值/日志都不含 token；token 只进受管元数据文件。

**不声称**：WebSocket 可透传（反代 405，REV-16 §9-2，界面已如实披露）；不声称 Web 是执行通道。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path
from typing import Any

from host import paths as P
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_web_instance as WI

LOG = logging.getLogger("loop.web_instance_ctl")

#: 实例 home 的目录名（与 `dsh_assets.AttemptLayout.home` 并列，**刻意不同名**，见模块 docstring 纪律 2）
WEB_HOME_DIRNAME = "dsh-web-home"

#: 进程内登记：`(run_dir.resolve(), node) -> WebInstance`。
#: 为什么按 (run, node) 而不是 (run, node, attempt)：元数据是**每 run 一个文件**，
#: 只能指向"当前 (node, attempt)"；同一 (run, node) 换 attempt 时必须替换旧实例。
_REGISTRY: dict[tuple[str, str], WI.WebInstance] = {}


class WebCtlError(RuntimeError):
    """接线层失败（配置不允许 / 起不来 / 落账失败）。调用方必须显式失败，不降级成"不可用但假装"。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__("%s: %s" % (reason, detail) if detail else reason)


def home_for_attempt(run_dir: Path | str, node: str, attempt: int) -> Path:
    """实例 home = `<attempt>/dsh-web-home`（**布局唯一来源**是 `dsh_assets.workspace_root`）。"""
    root = A.workspace_root(run_dir, node, int(attempt))
    return Path(root) / WEB_HOME_DIRNAME


def web_config(*, enable: bool = False, document: dict[str, Any] | None = None) -> WI.WebInstanceConfig:
    """装配 Web 实例配置：**只读** `SETTINGS.dsh.web`，不接受任务文本/客户端输入。

    `enable=True` 是**显式算子意图**（CLI `--enable`）：只有它能把 `enabled:false` 翻成允许启动；
    否则 `enabled:false` ⇒ `web_disabled`（默认关，不因内嵌成功就改默认行为）。
    """
    base = D.config_from_settings(document)
    try:
        config = WI.config_from_settings(document, base=base)
    except WI.WebConfigError as exc:
        raise WebCtlError(exc.reason, exc.detail) from None
    if enable and not config.enabled:
        config = dataclasses.replace(config, enabled=True)
    return config


def _key(run_dir: Path | str, node: str) -> tuple[str, str]:
    return (Path(run_dir).resolve().as_posix(), str(node))


def current(run_dir: Path | str, node: str) -> WI.WebInstance | None:
    """当前登记的实例（不启动、不探测）。"""
    instance = _REGISTRY.get(_key(run_dir, node))
    if instance is None or not instance.is_running:
        _REGISTRY.pop(_key(run_dir, node), None)
        return None
    return instance


def ensure(run_dir: Path | str, node: str, attempt: int, *, session_log: str | None = None,
           enable: bool = False, document: dict[str, Any] | None = None) -> dict[str, Any]:
    """确保该 `(run, node, attempt)` 有一个在跑的 Web 实例并落账；返回**不含 token** 的事实。

    判据（显式失败，不降级）：
    - `enabled=false` 且未显式 `enable` ⇒ `WebCtlError("web_disabled")`（不起"半个"）；
    - 同 `(run, node)` 已有实例但 attempt 不同 ⇒ **停掉旧的再起新的**（元数据只能指一个目标）；
    - 起不来 / 健康检查失败 / 落账失败 ⇒ 收干净进程再抛（不留半死实例、不留指向死端口的元数据）。
    """
    config = web_config(enable=enable, document=document)
    if not config.enabled:
        raise WebCtlError("web_disabled", "dsh.web.enabled=false；显式启动需 --enable")
    key = _key(run_dir, node)
    existing = current(run_dir, node)
    if existing is not None:
        previous = read_declared_attempt(run_dir)
        if previous == int(attempt):
            return describe(existing, run_dir=run_dir, node=node, attempt=int(attempt),
                            reused=True)
        LOG.info("dsh web instance replace: node=%s attempt %s -> %s", node, previous, attempt)
        stop(run_dir, node)
    config = dataclasses.replace(config, home=home_for_attempt(run_dir, node, int(attempt)))
    try:
        instance = WI.start(config)
    except WI.WebInstanceError as exc:
        raise WebCtlError(exc.reason, exc.detail) from None
    _REGISTRY[key] = instance
    try:
        instance.write_metadata(run_dir, node=node, attempt=int(attempt), session_log=session_log)
    except (WI.WebInstanceError, OSError) as exc:
        stop(run_dir, node)
        raise WebCtlError("metadata_write_failed", type(exc).__name__) from None
    return describe(instance, run_dir=run_dir, node=node, attempt=int(attempt), reused=False)


def describe(instance: WI.WebInstance, *, run_dir: Path | str, node: str,
             attempt: int, reused: bool) -> dict[str, Any]:
    """给调用方/证据看的事实：**不含 token**（token 只在 `describe()` 之外，即元数据文件里）。"""
    target = instance.target
    return {"node": node, "attempt": int(attempt), "host": target.host,
            "port": target.port, "reused": bool(reused),
            "port_requested": instance.port_requested,
            "port_fallback": bool(instance.port_fallback),
            "startup_s": instance.startup_s, "pid": instance.pid,
            "home": str(instance.config.home),
            "metadata": str(WI.metadata_path(run_dir))}


def stop(run_dir: Path | str, node: str) -> bool:
    """停掉该 `(run, node)` 的实例并清落账；**可重入**（没有实例 ⇒ 只清落账，返回 False）。"""
    instance = _REGISTRY.pop(_key(run_dir, node), None)
    stopped = False
    if instance is not None:
        instance.stop(remove_metadata=Path(run_dir))
        stopped = True
    else:
        try:
            WI.clear_metadata(run_dir)
        except WI.WebInstanceError:
            pass
    return stopped


def stop_all() -> int:
    """停掉本进程登记的全部实例（进程退出前收干净）。返回停掉的个数。"""
    count = 0
    for key in list(_REGISTRY):
        instance = _REGISTRY.pop(key)
        try:
            instance.stop(remove_metadata=Path(key[0]))
            count += 1
        except Exception:  # noqa: BLE001 - 收尾尽力而为，不因一个失败漏掉其余
            LOG.warning("dsh web instance stop failed: %s", key[0])
    return count


def read_declared_attempt(run_dir: Path | str) -> int | None:
    """读元数据里声明的 attempt（**只读**，不校验 loopback —— 那是读者的判据）。"""
    try:
        document = json.loads(WI.metadata_path(run_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = document.get("attempt")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ---------------------------------------------------------------- CLI（算子的显式入口）

def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m host.web_instance_ctl",
        description="Host 侧起/停常驻 DSH Web 实例并落账 agent_instance.json（**不自启动**）")
    parser.add_argument("action", choices=("start", "stop", "status"))
    parser.add_argument("--run-dir", required=False, help="run 目录（含 agent_instance.json）")
    parser.add_argument("--node", default="N6")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--session-log", default=None,
                        help="相对 run_dir 的 session log 路径（可选；供『导出会话副本』）")
    parser.add_argument("--enable", action="store_true",
                        help="显式允许启动（SETTINGS 里 web.enabled=false 时需要）")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.action == "status":
        print(json.dumps({"declared_attempt": read_declared_attempt(args.run_dir)
                          if args.run_dir else None}, ensure_ascii=False))
        return 0
    if not args.run_dir:
        parser.error("--run-dir 必填")
    if args.action == "stop":
        print(json.dumps({"stopped": stop(args.run_dir, args.node)}, ensure_ascii=False))
        return 0
    try:
        facts = ensure(args.run_dir, args.node, args.attempt,
                       session_log=args.session_log, enable=args.enable)
    except WebCtlError as exc:
        print(json.dumps({"ok": False, "reason": exc.reason, "detail": exc.detail},
                         ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **facts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
