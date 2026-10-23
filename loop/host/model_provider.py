"""模型 provider 接入（本层唯一 provider 配置来源）。

三条硬约束：

1. **密钥不落仓库**。本文件与 `loop/SETTINGS.yaml` 都不写死任何凭据。
   密钥在运行时解析：`$LOOP_LLM_API_KEY` → 宿主 DSH 凭据库 `~/.dsh/.credentials.yaml`
   的 `refs.<apiKeyEnv>`。只注入进程内存与 Agently settings。
2. **端点不硬编码**。优先环境变量；否则**复用宿主 `~/.dsh/settings.yaml` 已声明的 provider**
   ——在仓库里再抄一份内部地址，早晚会和宿主配置漂移。
3. **fail closed**。拿不到 provider 就返回 `available=False` 并写明原因，
   由调用方决定降级（本层降级为**显式标注**的确定性替身），**绝不静默假装有模型**。

实测事实（写进代码的理由）：
- 本网关的模型是**推理模型**：`max_tokens` 给不足时 token 全被 `reasoning_content` 吃掉，
  `content` 为空且 `finish_reason=length`。默认 `max_tokens` 必须给足。
- 网关支持 `openai-responses`（宿主配置如此），也支持 `chat/completions`（已实测 200）。
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from host import paths as P

SETTINGS_FILE = P.LOOP_DIR / "SETTINGS.yaml"

#: 宿主声明的 API family → Agently 的 ModelRequester 插件名
_FAMILY_TO_PLUGIN = {
    "openai-responses": "OpenAIResponsesCompatible",
    "responses": "OpenAIResponsesCompatible",
    "chat": "OpenAICompatible",
    "chat/completions": "OpenAICompatible",
    "completions": "OpenAICompatible",
}

DEFAULTS = {
    "family": "openai-responses",
    "base_url": "",
    "model": "",
    "api_key_env": "PUBLIC_API_KEY",
    "max_tokens": 8000,
    "timeout_s": 180,
    # 留空 = 取 shell 的 HTTPS_PROXY/HTTP_PROXY。
    # **必须显式设**：插件 `request_builder.py:324` 写死
    # `client_options.setdefault("trust_env", False)` ⇒ 环境代理**不会**被 httpx 读取，
    # 不设就会直接 DNS 失败（实测 `[Errno -2] Name or service not known`）。
    "proxy": "",
}


class ProviderUnavailable(RuntimeError):
    """没有可用的 provider ⇒ 调用方必须降级或显式失败。"""


@dataclass
class ProviderConfig:
    available: bool
    plugin: str | None
    family: str | None
    base_url: str | None
    model: str | None
    api_key_env: str | None
    max_tokens: int
    timeout_s: int
    proxy: str | None = None
    key_source: str | None = None
    config_source: str | None = None
    reason: str | None = None
    _api_key: str | None = None

    def public(self) -> dict[str, Any]:
        """对外投影：**绝不含密钥**。"""
        out = asdict(self)
        out.pop("_api_key", None)
        out["has_api_key"] = bool(self._api_key)
        return out


def dsh_home() -> Path:
    return Path(os.environ.get("DSH_HOME") or (Path.home() / ".dsh"))


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _loop_settings() -> dict[str, Any]:
    doc = _read_yaml(SETTINGS_FILE)
    section = ((doc.get("loop") or {}).get("llm") or {}) if isinstance(doc, dict) else {}
    return {**DEFAULTS, **{k: v for k, v in section.items() if v not in (None, "")}}


def _dsh_declared_provider() -> dict[str, Any]:
    """复用宿主已声明的 provider（含 default model 与 apiKeyEnv）。"""
    settings = _read_yaml(dsh_home() / "settings.yaml")
    llm = settings.get("llm-pi-ai") or {}
    providers = llm.get("providers") or {}
    default = settings.get("agent-default-model") or {}
    name = default.get("provider")
    if not name or name not in providers:
        name = next(iter(providers), None)
    if name is None:
        return {}
    prov = providers.get(name) or {}
    return {
        "provider_name": name,
        "family": prov.get("api"),
        "base_url": prov.get("baseURL"),
        "model": default.get("model"),
        "api_key_env": prov.get("apiKeyEnv"),
    }


def _dsh_credential(env_name: str | None, provider_name: str | None = None) -> tuple[str | None, str | None]:
    """从宿主凭据库取密钥。返回 `(key, source)`；不打印、不落盘。"""
    if not env_name:
        return None, None
    doc = _read_yaml(dsh_home() / ".credentials.yaml")
    refs = doc.get("refs") or {}
    key = refs.get(env_name)
    if isinstance(key, str) and key.strip():
        return key.strip(), f"dsh_credentials:refs.{env_name}"
    records = doc.get("records") or {}
    for name, rec in records.items():
        payload = (rec or {}).get("payload") or {}
        if name == provider_name or name.endswith(f"/{provider_name}"):
            secret = payload.get("secret")
            if isinstance(secret, str) and secret.strip():
                return secret.strip(), f"dsh_credentials:records.{name}"
    return None, None


def resolve(*, family: str | None = None, model: str | None = None) -> ProviderConfig:
    """解析 provider。优先级：环境变量 → loop/SETTINGS.yaml → 宿主 DSH 声明。

    `LOOP_LLM_MODE=standin` 强制离线（测试与无网环境用），
    `live` 则要求必须真的拿到 provider（拿不到按不可用处理，仍然 fail closed）。
    """
    declared = _dsh_declared_provider()
    if (os.environ.get("LOOP_LLM_MODE") or "").strip().lower() == "standin":
        return ProviderConfig(
            available=False, plugin=None, family="forced-standin", base_url=None, model=None,
            api_key_env=None, max_tokens=int(_loop_settings()["max_tokens"]),
            timeout_s=int(_loop_settings()["timeout_s"]),
            reason="LOOP_LLM_MODE=standin：本进程被显式要求离线（用确定性替身）",
        )
    cfg = _loop_settings()

    chosen_family = (
        family
        or os.environ.get("LOOP_LLM_FAMILY")
        or cfg.get("family")
        or declared.get("family")
        or DEFAULTS["family"]
    )
    base_url = (
        os.environ.get("LOOP_LLM_BASE_URL")
        or cfg.get("base_url")
        or declared.get("base_url")
        or ""
    )
    chosen_model = model or os.environ.get("LOOP_LLM_MODEL") or cfg.get("model") or declared.get("model") or ""
    key_env = cfg.get("api_key_env") or declared.get("api_key_env") or DEFAULTS["api_key_env"]

    proxy = (
        os.environ.get("LOOP_LLM_PROXY")
        or cfg.get("proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    )
    # 目标若是 loopback，强制不走代理（宿主 .env 的 NO_PROXY 语义）
    if any(tok in (base_url or "") for tok in ("127.0.0.1", "localhost", "::1")):
        proxy = ""

    plugin = _FAMILY_TO_PLUGIN.get(str(chosen_family).lower())
    if plugin is None:
        return ProviderConfig(
            available=False, plugin=None, family=str(chosen_family), base_url=base_url or None,
            model=chosen_model or None, api_key_env=key_env,
            max_tokens=int(cfg["max_tokens"]), timeout_s=int(cfg["timeout_s"]), proxy=proxy or None,
            reason=f"不认识的 api family {chosen_family!r}；支持 {sorted(_FAMILY_TO_PLUGIN)}",
        )

    api_key = os.environ.get("LOOP_LLM_API_KEY")
    key_source = "env:LOOP_LLM_API_KEY" if api_key else None
    if not api_key:
        api_key_env = os.environ.get(key_env)
        if api_key_env:
            api_key, key_source = api_key_env, f"env:{key_env}"
    if not api_key:
        api_key, key_source = _dsh_credential(key_env, declared.get("provider_name"))

    missing = [name for name, value in (("base_url", base_url), ("model", chosen_model), ("api_key", api_key)) if not value]
    if missing:
        return ProviderConfig(
            available=False, plugin=plugin, family=str(chosen_family), base_url=base_url or None,
            model=chosen_model or None, api_key_env=key_env,
            max_tokens=int(cfg["max_tokens"]), timeout_s=int(cfg["timeout_s"]), proxy=proxy or None,
            key_source=key_source,
            config_source=f"dsh:{declared.get('provider_name')}" if declared else "loop/SETTINGS.yaml",
            reason=f"缺少 {missing}（密钥环境变量 {key_env} 未设且宿主凭据库无此 ref）",
        )

    return ProviderConfig(
        available=True, plugin=plugin, family=str(chosen_family), base_url=base_url,
        model=chosen_model, api_key_env=key_env,
        max_tokens=int(cfg["max_tokens"]), timeout_s=int(cfg["timeout_s"]), proxy=proxy or None,
        key_source=key_source,
        config_source=f"dsh:{declared.get('provider_name')}" if declared else "loop/SETTINGS.yaml",
        _api_key=api_key,
    )


def configure_agently(*, family: str | None = None, model: str | None = None,
                      config: ProviderConfig | None = None) -> ProviderConfig:
    """把解析结果写进 Agently settings。返回配置；不可用时抛 `ProviderUnavailable`。

    单次 attempt 可传入已解析的 config，确保审计与执行使用同一模型配置。
    不传 config 的诊断入口仍按原规则解析；config 不能与覆盖参数混用。

    只调用框架的 settings 接口，不手写 provider HTTP（技能 `agently-request` 的
    "Avoid" 第一条）。
    """
    from agently import Agently

    if config is not None and (family is not None or model is not None):
        raise ValueError('prepared provider config cannot be combined with overrides')
    cfg = config if config is not None else resolve(family=family, model=model)
    if not cfg.available:
        raise ProviderUnavailable(cfg.reason or "provider 不可用")

    assert cfg.plugin and cfg.base_url and cfg.model and cfg._api_key
    ns = f"plugins.ModelRequester.{cfg.plugin}"
    Agently.set_settings("plugins.ModelRequester.activate", cfg.plugin)
    Agently.set_settings(f"{ns}.base_url", cfg.base_url)
    Agently.set_settings(f"{ns}.api_key", cfg._api_key)
    Agently.set_settings(f"{ns}.model", cfg.model)
    Agently.set_settings(f"{ns}.request_retry", {"max_attempts": 2, "after_output": True})
    if cfg.proxy:
        Agently.set_settings(f"{ns}.proxy", cfg.proxy)
    Agently.set_settings(f"{ns}.client_options", {"trust_env": False})
    # 推理模型：给不足就会被 reasoning 吃光（实测 max_tokens=32 ⇒ content 为空）
    Agently.set_settings(f"{ns}.request_options", {"max_tokens": cfg.max_tokens})
    Agently.set_settings(
        f"{ns}.timeout",
        {"connect": 10.0, "read": float(cfg.timeout_s), "write": 30.0, "pool": 10.0},
    )
    return cfg


def status() -> dict[str, Any]:
    """对外投影（供 `/api/health` 与界面显示）。**不含密钥**。"""
    cfg = resolve()
    return cfg.public()


async def ping(*, model: str | None = None) -> dict[str, Any]:
    """真发一次最小请求，证明链路可用（不是读配置猜）。"""
    from agently import Agently

    try:
        cfg = configure_agently(model=model)
    except ProviderUnavailable as exc:
        return {"ok": False, "reason": str(exc)}

    agent = Agently.create_agent()
    try:
        result = await (
            agent.input("只回答两个字：收到")
            .output({"text": ("str", "模型回答原文")})
            .async_get_data()
        )
    except Exception as exc:  # noqa: BLE001 - 诊断端点用，原样回报
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}", "provider": cfg.public()}
    return {"ok": True, "provider": cfg.public(), "reply": result}
