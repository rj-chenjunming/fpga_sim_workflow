"""S7c/S8b 接线：Host 侧"起/停常驻 DSH Web 实例 + 落账 `agent_instance.json`"的唯一入口。

**为什么单独一层**：`dsh_web_instance` 只负责"起进程 / 解析公告行 / 健康检查 / 原子写元数据"
（纯机制）；本模块负责**编排决策**——给哪个 `(run, node, attempt)` 起、`home` 落在哪、
已有实例怎么替换、什么时候清落账。决策只此一处，读者（`services/instance_proxy`）不参与。

**三条硬纪律**：

1. **是否启动由 attempt 装配点决定**（S8b 收口，裁决 B3）：`SETTINGS.dsh.web.enabled` 是准入门，
   真正的启动发生在 `dsh.DshBackend.prepare_attempt`（**仅** `mode=real` 且 `enabled=true`）。
   起不来**不阻断** attempt（Web 只是观测面，降级为"不可内嵌 + 原因"）；
   attempt 结束**不 stop**（人还要看）。本模块自身不自启任何东西；`enabled:false` 时连显式调用也拒
   （`web_disabled`）⇒ 一键回退到 S7 行为。
2. **`home` 与 `workdir` 都取自该 attempt 的 `AttemptLayout`**（D3 收口，REV-14 §3-D3 / §9.3）：
   `home` = `<attempt>/dsh-home`（与模型 attempt 共用 ⇒ 会话可见），
   `workdir` = `<attempt>/work`（实例进程 cwd ⇒ dsh 按 cwd 编码的目录分组会话，cwd 错了列表恒空）。
   **真机实测（2026-10-29，0 token，`loop/.logs/s8b/`）**：修 `workdir` 后，直连实例的侧栏
   自动出现 workspace `work` 与本次 0-token boot 的会话（标题「只回复 OK」），**无需人工选 workspace**；
   同一会话的 `session-<uuid>` 出现在该列表行的 DOM 里。经同源反代（iframe）仍受
   `remote.mux` WebSocket 握手 **405**（REV-16 §9-2 未决）⇒ 前端 live channel 起不来、列表取不到数据；
   那条路的判定是 `blocked_by_missing_live_channel`，**不是** home/cwd 的问题。
   下面是 S7c 的并列目录历史（已退场），保留说明以免读者再走一遍：
   实例 home = `<attempt>/dsh-home`，由 `home_for_attempt` 给出，**路径唯一来源**是
   `dsh_assets.workspace_root`（不另写拼接，红线 8）。
   S7c 曾把它放在**并列目录** `dsh-web-home`，理由是"`dsh --profile web` 会在 home 里自生成
   `.credentials.yaml`（cookie 签名 secret），而 `FORBIDDEN_HOME_ENTRIES` 把它判成 attempt home
   含宿主件"——代价是**人在 GUI 里看不到该 attempt 的会话**，D3 未落地。
   S8b 按 REV-14 §9 的**来源判定**取消了这个并列目录：`dsh_generated` 的凭据件**放行**并记录，
   `host_settings_copy`/`host_credential_value`/`unknown` 仍**拒绝**（B3 的禁令语义不变）。
   旧 run 目录里的 `dsh-web-home` **不迁移、不删除**：`stop` 按 `(run, node)` 认实例，
   与 home 布局无关（只读兼容）。
3. **token 永不回显**：本模块的任何返回值/日志都不含 token；token 只进受管元数据文件。

**不声称**：WebSocket 可透传（反代 405，REV-16 §9-2，界面已如实披露）；不声称 Web 是执行通道。
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from host import paths as P
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_web_instance as WI

LOG = logging.getLogger("loop.web_instance_ctl")

#: S7c 的**并列**实例 home 目录名。**已退场**（S8b 收口，REV-14 §9.3）：实例 home 与 attempt
#: `dsh-home` 共用。常量保留只作**只读兼容**：老 run 目录里可能还有这个目录，
#: 我们既不迁移也不删除它（`stop` 按 `(run, node)` 认实例，与 home 布局无关）。
LEGACY_WEB_HOME_DIRNAME = "dsh-web-home"

#: 进程内登记：`(run_dir.resolve(), node) -> WebInstance`。
#: 为什么按 (run, node) 而不是 (run, node, attempt)：元数据是**每 run 一个文件**，
#: 只能指向"当前 (node, attempt)"；同一 (run, node) 换 attempt 时必须替换旧实例。
#: 也正因为只按 (run, node) 认实例，**旧布局**（`dsh-web-home`）起出来的实例照样能被 `stop` 收掉。
_REGISTRY: dict[tuple[str, str], WI.WebInstance] = {}


class WebCtlError(RuntimeError):
    """接线层失败（配置不允许 / 起不来 / 落账失败）。调用方必须显式失败，不降级成"不可用但假装"。"""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__("%s: %s" % (reason, detail) if detail else reason)


def layout_for_attempt(run_dir: Path | str, node: str, attempt: int) -> A.AttemptLayout:
    """该 `(run, node, attempt)` 的 attempt 布局（**路径唯一来源**，本模块不另写拼接）。

    `home` 与 `work` 都从这里取：`home` = 实例的 `DSH_HOME`（与 attempt 共用），
    `work` = 实例进程的 **cwd**（dsh 按 cwd 编码的目录分组会话 ⇒ cwd 错了就看不到该 attempt 的会话）。
    """
    return A.AttemptLayout.under(A.workspace_root(run_dir, node, int(attempt)))


#: Web 实例专用 patch 落点（与 attempt 的 `patches/` 分开：Web 只挂 provider overlay，
#: 不挂 attempt 的提交/自检插件 —— 那会把"执行面"的工具塞进人看的 GUI）。
WEB_PATCH_DIRNAME = "patches-web"


def provider_launch(layout: A.AttemptLayout) -> tuple[tuple[Path, ...], dict[str, str], dict[str, Any]]:
    """Web 实例要继承的 provider 运行时（REV-14 §9.4 / S8h）。

    返回 `(patches, env_extra, state)`：
    - `patches`：生成的 provider overlay 文件（`--patch` 传入；**唯一生成实现**是
      `dsh_assets.provider_overlay`，本函数只落盘）；
    - `env_extra`：模型凭据 + 代理（仍只走 env，不落文件）；
    - `state`：`{"state": "ready"|"unavailable", "reason", "detail"}` —— **provider 不可用不阻断
      起实例**（观测面不该因配置问题消失），但必须如实记录，界面显示"模型未配置"。
    """
    try:
        overlay, env = A.provider_runtime()
    except A.AssetError as exc:
        return (), {}, {"state": "unavailable", "reason": "provider_unavailable",
                        "detail": str(exc)[:300]}
    directory = Path(layout.root) / WEB_PATCH_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / overlay.filename
    path.write_text(overlay.text, encoding="utf-8")
    return (path,), env, {"state": "ready", "reason": None, "detail": None}


def seed_provider_credential(layout: A.AttemptLayout) -> dict[str, Any]:
    """把宿主自己的 provider key 写进 dsh 凭据库（裁决 A，REV-14 §9.1a / S8h）。

    为什么需要：DSH Web 的**模型选择器**只认 `dsh-credentials-local` 的存储
    （`<home>/.credentials.yaml` 的 `llm-pi-ai/<provider>` 记录），不认 env；只给 env 会得到
    `No models available.`。写进去等价于人在 GUI 里点一次 "Add API Key"。

    **安全边界（人已裁决 A，2026-10-29）**：这是**故意**把宿主凭据落到共用 home 的磁盘文件，
    因此 DS-09 新增 `host_authorized_store` 档只放行"值全是宿主已有凭据"的凭据库；
    陌生秘密仍拒。文件 0600、原子替换、**零回显**（本函数返回值里不含 key）。
    """
    credential = A.provider_credential()
    if credential is None:
        return {"state": "skipped", "reason": "provider_credential_unavailable", "record": None}
    _env_name, key = credential
    path = Path(layout.home) / A.CREDENTIAL_STORE_NAME
    record_key = "llm-pi-ai/%s" % A.PROVIDER_NAME
    import yaml

    document: dict[str, Any] = {"version": 1, "records": {}}
    if path.is_file():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            loaded = None
        if not isinstance(loaded, dict) or not isinstance(loaded.get("records"), dict):
            # 不认识的凭据库 ⇒ 不擅自覆盖（那会毁掉已有的登录态）；如实报，交给 DS-09 判。
            return {"state": "skipped", "reason": "credential_store_unreadable",
                    "record": None}
        document = {"version": loaded.get("version", 1), "records": dict(loaded["records"])}
    document["records"][record_key] = {"kind": "api-key", "key": key}
    payload = yaml.safe_dump(document, sort_keys=False, allow_unicode=True).encode("utf-8")
    tmp = path.with_name(".%s.tmp-%d" % (path.name, os.getpid()))
    tmp.write_bytes(payload)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return {"state": "seeded", "reason": None, "record": record_key}


def home_for_attempt(run_dir: Path | str, node: str, attempt: int) -> Path:
    """实例 home = **该 attempt 的** `dsh-home`（D3：人与模型共用同一实例 home）。

    路径**唯一来源**是 `dsh_assets.workspace_root` + `AttemptLayout`（"dsh-home"这个名字只在
    `dsh_assets.AttemptLayout` 里拼），本模块不另写一份拼接 —— 反向抽检见
    `tests/test_web_instance_ctl.py::test_home_for_attempt_has_no_second_path_implementation`。
    """
    return layout_for_attempt(run_dir, node, attempt).home


def workdir_for_attempt(run_dir: Path | str, node: str, attempt: int) -> Path:
    """实例进程 cwd = **该 attempt 的** `work`（唯一来源同上）。

    为什么必须是它（真机实测 2026-10-29）：dsh 的会话存储按**cwd 编码的目录**分组
    （目录名形如 `--home-…-attempt-work--`）。实例 cwd 若停在仓根，Web 列的是"仓根这个
    workspace"的会话 ⇒ 画面恒为 `No sessions yet`，D3 落不了地。
    **实测结论（同日志 `loop/.logs/s8b/`）**：cwd 修成 `<attempt>/work` 后，直连实例侧栏
    自动列出该 attempt 的会话（workspace `work` + 会话标题），`session-<uuid>` 在该列表行的 DOM 内。
    """
    return layout_for_attempt(run_dir, node, attempt).work


def web_config(*, enable: bool = False, document: dict[str, Any] | None = None) -> WI.WebInstanceConfig:
    """装配 Web 实例配置：**只读** `SETTINGS.dsh.web`，不接受任务文本/客户端输入。

    `enable=True` 是**显式算子意图**（CLI `--enable`）：只有它能把 `enabled:false` 翻成允许启动；
    否则 `enabled:false` ⇒ `web_disabled`（回退档：一改配置就回到 S7 的"不起实例"行为）。
    仓内默认是 `enabled:true`（裁决 B3：随 real attempt 自动起，见模块 docstring 纪律 1）。
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

    **已知边界（如实登记，不是缺陷）**：登记表按 `(run, node)` 建键，所以**换 node 不会**释放
    先前节点的实例 —— 一次 real run 走 N 个节点就会同时留 N 个 loopback 实例（进程数随节点数增长）。
    这是裁决 B3「attempt 结束后保留实例（人还要看）」的直接后果：每个节点的最新 attempt 会话
    都要能被人打开。收干净靠 `stop_all()`（进程退出前/`stop(run_dir, node)` 逐个来）。
    若将来要"只保留当前节点"，得先裁决"看旧节点会话"的需求怎么承接（本模块不擅自回收）。
    """
    config = web_config(enable=enable, document=document)
    if not config.enabled:
        raise WebCtlError("web_disabled", "dsh.web.enabled=false；显式启动需 --enable")
    key = _key(run_dir, node)
    existing = current(run_dir, node)
    if existing is not None:
        previous = read_declared_attempt(run_dir)
        if previous == int(attempt):
            facts = describe(existing, run_dir=run_dir, node=node, attempt=int(attempt),
                             reused=True)
            # 复用已起实例：它的 provider 配置是**起那一刻**的决定，这里不重算、不假装知道。
            facts["provider"] = {"state": "unchanged", "reason": None, "detail": None}
            return facts
        LOG.info("dsh web instance replace: node=%s attempt %s -> %s", node, previous, attempt)
        stop(run_dir, node)
    layout = layout_for_attempt(run_dir, node, int(attempt))
    if not layout.home.is_dir() or not layout.work.is_dir():
        # attempt 目录布局的物化归 `dsh_assets.AttemptLayout`（幂等；本模块只调它，不自己拼路径）。
        # 生产路径由 `DshBackend.prepare_attempt` 先物化；CLI/诊断入口靠这一步补齐。
        layout.prepare()
    # DS-09（防御纵深）：起进程前先消费**唯一判据**的结论，home 有该拒的宿主件就不起
    # （本模块不重算判据）。`dsh_generated` 的自生成件在这条判据里是放行的（REV-14 §9）。
    problems = A.home_problems(layout.home)
    if problems:
        raise WebCtlError("home_not_compliant", "；".join(problems))
    # S8h（REV-14 §9.4）：把 attempt 的 provider 运行时带给 Web 实例（人才能在 GUI 里说话）。
    # provider 不可用**不阻断**起实例：观测面不该因配置问题消失，但状态照实记录。
    patches, env_extra, provider_state = provider_launch(layout)
    # 裁决 A：把宿主自己的 key 写进 dsh 凭据库（GUI 的模型选择器只认它）。写在 DS-09 检查**之后**：
    # 本 attempt 的准入按"起进程那一刻"的 home 判定，写进去的记录从下一次 attempt 起由
    # `host_authorized_store` 档放行（有用例钉住）。
    provider_state = {**provider_state,
                      "credential": seed_provider_credential(layout)}
    config = dataclasses.replace(config, home=layout.home, workdir=layout.work,
                                 patches=patches, env_extra=env_extra)
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
    facts = describe(instance, run_dir=run_dir, node=node, attempt=int(attempt), reused=False)
    facts["provider"] = provider_state
    return facts


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
            "workdir": (None if instance.config.workdir is None
                        else str(instance.config.workdir)),
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
        description="Host 侧起/停常驻 DSH Web 实例并落账 agent_instance.json"
                    "（正常路径由 attempt 装配点自动调用；本 CLI 是算子/诊断入口）")
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
