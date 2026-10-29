"""S7c：Host 起/停常驻 DSH Web 实例 + `agent_instance.json` 落账（`host/web_instance_ctl.py`）。

判据（不读实现也应成立）：
- **不自启动**：`SETTINGS.dsh.web.enabled=false` 时 `ensure()` 显式拒绝（`web_disabled`）；
  只有显式 `enable=True`（CLI `--enable`）才允许启动。
- **home 不与 attempt 共用**：实例 home = `<attempt>/dsh-web-home`，**不是** `<attempt>/dsh-home`；
  起完之后 `.credentials.yaml` 只落在 web home 里，attempt 的 `dsh-home` 保持干净
  （否则下一次 attempt 会被 DS-09 的 `FORBIDDEN_HOME_ENTRIES` 判成"含宿主件"而准入失败）。
- **落账可被读者消费**：元数据文档经 `services.instance_proxy.load_target` 读回，`(node, attempt)` 归属正确。
- **token 永不回显**：`ensure()` 的返回值和日志都不含 token。
- **收干净**：`stop()` 可重入；停后元数据被清 ⇒ 读者按 `target_missing` 显式降级（不是连死端口）。
- 配置坏值（非 loopback / 未知键）在**解析期**就炸，不拖到起实例那一刻。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from host import paths as P
from host import web_instance_ctl as C
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from services import instance_proxy as IP

#: 仓内默认：`SETTINGS.dsh.web.enabled = false`（"不自启动"的落地形态）
DOC_DISABLED = {"loop": {"agent_runtime": {"dsh": {
    "enabled": True, "version": "0.2.1-rc.2", "node": str(P.LOOP_DIR / ".venv/bin/python"),
    "bin": str(P.LOOP_DIR / "SETTINGS.yaml"), "bin_sha256": "0" * 64,
    "timeout_s": 300, "wrap": True,
    "web": {"enabled": False, "host": "127.0.0.1", "preferred_port": 0}}}}}


def _doc(**web: object) -> dict:
    """真机形态的配置文档：`node`/`bin`/指纹取**仓内 SETTINGS 的真实值**（起进程要用真的）。

    非真机用例只用它的解析结果，不会真的起进程；真机用例则依赖这台机器上确有该安装。
    """
    real = D.config_from_settings()
    base = {"loop": {"agent_runtime": {"dsh": {
        "enabled": True, "version": real.version, "node": str(real.node),
        "bin": str(real.bin), "bin_sha256": real.bin_sha256,
        "timeout_s": 300, "wrap": True, "web": {"enabled": True, "host": "127.0.0.1"}}}}}
    base["loop"]["agent_runtime"]["dsh"]["web"].update(web)
    return base


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "RUN-20261029-S7C"
    run_dir.mkdir(parents=True)
    return run_dir


# ---------------------------------------------------------------- 不自启动

def test_disabled_settings_refuse_explicit_start_without_enable_flag(tmp_path: Path) -> None:
    """`web.enabled=false` ⇒ 显式调用也拒：不产生"半个实例"、不写元数据。"""
    run_dir = _run_dir(tmp_path)
    with pytest.raises(C.WebCtlError) as info:
        C.ensure(run_dir, "N6", 1, document=DOC_DISABLED)
    assert info.value.reason == "web_disabled"
    assert not (run_dir / IP.METADATA_NAME).exists()


def test_enable_flag_is_the_only_way_to_start_a_disabled_config() -> None:
    """`--enable` 是算子显式意图：它把 enabled 翻成允许；不带则保持关。"""
    assert C.web_config(document=DOC_DISABLED).enabled is False
    assert C.web_config(enable=True, document=DOC_DISABLED).enabled is True


def test_shipped_settings_do_not_self_start_web() -> None:
    """仓内 SETTINGS 的 web 默认**关**（"不因内嵌成功就改默认运行行为"）；且 dsh 配置能解析。"""
    config = D.web_config_from_settings()
    assert config.enabled is False, "SETTINGS 里 web.enabled 必须默认 false（不自启动）"
    assert config.host == "127.0.0.1"


# ---------------------------------------------------------------- home 归属

def test_instance_home_is_parallel_to_attempt_home(tmp_path: Path) -> None:
    """实例 home 在 attempt 根下、与 `dsh-home` **并列且不同名**（DS-09 冲突的治法）。"""
    run_dir = _run_dir(tmp_path)
    home = C.home_for_attempt(run_dir, "N6", 1)
    layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
    assert layout.root in home.parents
    assert home == layout.root / C.WEB_HOME_DIRNAME
    assert home != layout.home
    assert C.WEB_HOME_DIRNAME not in A.FORBIDDEN_HOME_ENTRIES


# ---------------------------------------------------------------- 配置坏值在解析期炸

def test_non_loopback_host_is_rejected_at_parse_time() -> None:
    """`0.0.0.0` 必须在解析期被拒（不 bind 通配地址）。"""
    with pytest.raises(C.WebCtlError) as info:
        C.web_config(enable=True, document=_doc(host="0.0.0.0"))
    assert info.value.reason == "host_not_loopback"


def test_unknown_web_keys_are_rejected() -> None:
    """未知键 ⇒ 显式失败（避免"悄悄接受未实现开关"）。"""
    with pytest.raises(C.WebCtlError) as info:
        C.web_config(enable=True, document=_doc(public_url="http://evil"))
    assert info.value.reason == "unknown_keys"


# ---------------------------------------------------------------- 停 / 清落账 可重入

def test_stop_is_reentrant_and_clears_metadata(tmp_path: Path) -> None:
    """没有实例时 stop 只清落账、返回 False；重复 stop 不抛。"""
    run_dir = _run_dir(tmp_path)
    (run_dir / IP.METADATA_NAME).write_text('{"node":"N6","attempt":1,"host":"127.0.0.1",'
                                            '"port":1,"token":null}', encoding="utf-8")
    assert C.stop(run_dir, "N6") is False
    assert not (run_dir / IP.METADATA_NAME).exists()
    assert C.stop(run_dir, "N6") is False


# ---------------------------------------------------------------- 真机（本机有该安装才跑）

requires_dsh = pytest.mark.skipif(
    not D.config_from_settings().bin.is_file(), reason="本机没有该 DSH 安装（CI/异机）")


@requires_dsh
def test_real_instance_start_lands_metadata_and_keeps_attempt_home_clean(tmp_path: Path) -> None:
    """真机：起实例 → 落账 → 读者能读回 → attempt 的 `dsh-home` 保持干净 → 停后读者显式降级。"""
    run_dir = _run_dir(tmp_path)
    try:
        facts = C.ensure(run_dir, "N6", 1, enable=True,
                         document=_doc(preferred_port=0, start_timeout_s=45))
        assert facts["port"] > 0 and facts["host"] == "127.0.0.1"
        assert facts["reused"] is False
        # token 永不回显
        assert "token" not in facts and all(not isinstance(v, str) or len(v) < 200
                                            for v in facts.values())
        # 读者（唯一归属判据）能读回
        target = IP.load_target(run_dir, "N6", 1)
        assert (target.host, target.port, target.attempt) == (facts["host"], facts["port"], 1)
        assert target.token, "受管元数据必须带 token（读者用它做首跳交换）"
        # DS-09：dsh web 自生成的 cookie 签名 secret 落在 **web home**，attempt 的 dsh-home 保持干净
        layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
        home = Path(facts["home"])
        assert (home / ".credentials.yaml").is_file(), "dsh web 应在自己的 home 里生成会话签名件"
        assert not (layout.home / ".credentials.yaml").exists(), "attempt dsh-home 必须保持干净"
        assert A.home_problems(layout.home) == () or all(
            "credentials" not in item for item in A.home_problems(layout.home))
    finally:
        C.stop(run_dir, "N6")
    with pytest.raises(IP.TargetUnavailable) as info:
        IP.load_target(run_dir, "N6", 1)
    assert info.value.reason == "target_missing"


@requires_dsh
def test_real_replace_on_attempt_switch(tmp_path: Path) -> None:
    """同一 (run, node) 换 attempt ⇒ 停旧起新，元数据指向新 attempt（不跨 attempt 借用实例）。"""
    run_dir = _run_dir(tmp_path)
    try:
        first = C.ensure(run_dir, "N6", 1, enable=True,
                         document=_doc(preferred_port=0, start_timeout_s=45))
        second = C.ensure(run_dir, "N6", 2, enable=True,
                          document=_doc(preferred_port=0, start_timeout_s=45))
        assert first["port"] != second["port"] or first["pid"] != second["pid"]
        target = IP.load_target(run_dir, "N6", 2)
        assert target.attempt == 2
        with pytest.raises(IP.TargetUnavailable) as info:
            IP.load_target(run_dir, "N6", 1)
        assert info.value.reason == "target_missing", "不跨 attempt 借用实例"
        # 复用同一 attempt 不重启
        again = C.ensure(run_dir, "N6", 2, enable=True,
                         document=_doc(preferred_port=0, start_timeout_s=45))
        assert again["reused"] is True and again["port"] == second["port"]
    finally:
        C.stop_all()
