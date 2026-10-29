"""S8b：Host 起/停常驻 DSH Web 实例 + `agent_instance.json` 落账（`host/web_instance_ctl.py`）。

D3 收口（REV-14 §3-D3 / §9.3，裁决 B1/B3）后本文件固定住的判据：

- **home 与 attempt 共用**：实例 home = `<attempt>/dsh-home`（**唯一** attempt home），
  S7c 的并列目录 `dsh-web-home` **退场**；路径唯一来源是 `dsh_assets.workspace_root`
  （不另写拼接 —— 反向抽检：改 `workspace_root`，`home_for_attempt` 必须跟着变）。
- **DS-09 与共用 home 不冲突**：`dsh --profile web` 在该 home 里自生成的 `.credentials.yaml`
  被判 `dsh_generated` **放行**（判据见 `tests/test_ds09_home_provenance.py`），
  因此**下一次** attempt 的 DS-09 准入不会因共用而失败（D3 的落地前提）。
- **默认开**（裁决 B3）：仓内 `SETTINGS.dsh.web.enabled=true`；`enabled:false` ⇒ `ensure()` 显式拒绝
  （`web_disabled`）⇒ 一键回退到 S7 行为。
- **旧落账只读兼容**：指向旧布局的 `agent_instance.json` 仍能被 `stop` 识别并清掉，
  **不动**任何 home 目录（不迁移、不删除）。
- **落账可被读者消费**：元数据文档经 `services.instance_proxy.load_target` 读回，`(node, attempt)` 归属正确。
- **token 永不回显**：`ensure()` 的返回值和日志都不含 token。
- **收干净**：`stop()` 可重入；停后元数据被清 ⇒ 读者按 `target_missing` 显式降级（不是连死端口）。
- 配置坏值（非 loopback / 未知键）在**解析期**就炸，不拖到起实例那一刻。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from host import paths as P
from host import web_instance_ctl as C
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_web_instance as WI
from services import instance_proxy as IP

#: 真机实测形态（dsh 0.2.1-rc.2 自生成 `.credentials.yaml` 的**键形态**；secret 用假值）。
#: 单一来源的钉住在 `tests/test_ds09_home_provenance.py`（常量漂移用例）。
DSH_GENERATED_SAMPLE = """\
version: 1
records:
  client-connection/browser-session:
    kind: grant
    payload:
      version: 1
      secret: fake-dsh-generated-secret-0123456789
"""

#: 关掉的配置（回退档：`web.enabled: false` ⇒ 显式调用也拒）
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
    run_dir = tmp_path / "runs" / "RUN-20261029-S8B"
    run_dir.mkdir(parents=True)
    return run_dir


class _FakeInstance:
    """冒充 `dsh_web_instance.WebInstance`：起的时候在 home 里写一份 dsh 自生成件（真机行为）。"""

    def __init__(self, config: WI.WebInstanceConfig) -> None:
        self.config = config
        self.port_requested = 0
        self.port_fallback = False
        self.startup_s = 0.01
        self.pid = 4242
        self.stopped = False
        self._target = WI.LaunchTarget(host="127.0.0.1", port=18999, token="T" * 43)

    @property
    def target(self) -> WI.LaunchTarget:
        return self._target

    def is_running(self) -> bool:
        return not self.stopped

    def stop(self, *, remove_metadata: Path | None = None) -> None:
        self.stopped = True
        if remove_metadata is not None:
            WI.clear_metadata(remove_metadata)

    def write_metadata(self, run_dir: Path | str, *, node: str, attempt: int,
                       session_log: str | None = None) -> Path:
        document = {"node": node, "attempt": attempt, "host": self._target.host,
                    "port": self._target.port, "token": self._target.token,
                    "written_at": P.now_iso()}
        return WI.write_metadata_document(run_dir, document)


def _fake_start(config: WI.WebInstanceConfig) -> _FakeInstance:
    """`dsh --profile web` 的行为：在自己的 home 里生成会话签名件（DS-09 的来源判定对象）。"""
    config.home.mkdir(parents=True, exist_ok=True)
    (config.home / ".credentials.yaml").write_text(DSH_GENERATED_SAMPLE, encoding="utf-8")
    return _FakeInstance(config)


# ---------------------------------------------------------------- 默认开 / 回退档

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


def test_shipped_settings_enable_web_by_default_with_rollback() -> None:
    """裁决 B3：仓内 SETTINGS 默认**开**（随 real attempt 自动起实例）；`enabled:false` 可一键回退。"""
    config = D.web_config_from_settings()
    assert config.enabled is True, "裁决 B3：dsh.web.enabled 默认 true（随 real attempt 自动起）"
    assert config.host == "127.0.0.1"
    # 回退档：同一套判据在 enabled=false 时回到 S7 行为（显式调用也拒）
    assert C.web_config(document=DOC_DISABLED).enabled is False


# ---------------------------------------------------------------- home 归属（D3 收口）

def test_instance_home_is_the_attempt_home(tmp_path: Path) -> None:
    """实例 home **就是** attempt 的 `dsh-home`（共用同一 home ⇒ 人能在 GUI 看到该 attempt 会话）。"""
    run_dir = _run_dir(tmp_path)
    assert C.home_for_attempt(run_dir, "N6", 1) == A.AttemptLayout.under(
        A.workspace_root(run_dir, "N6", 1)).home


def test_home_for_attempt_has_no_second_path_implementation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """反向抽检（红线 8）：路径**唯一来源**是 `dsh_assets.workspace_root`，本模块不另写拼接。"""
    sentinel = tmp_path / "sentinel-root"
    monkeypatch.setattr(A, "workspace_root",
                        lambda run_dir, node, sequence: sentinel)
    assert C.home_for_attempt(tmp_path, "N6", 1) == A.AttemptLayout.under(sentinel).home


def test_ensure_uses_shared_home_and_ds09_allows_the_generated_secret(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """共用 home 后 DS-09 不误伤：实例自生成的凭据件被判 `dsh_generated`，准入仍通过。"""
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(C.WI, "start", _fake_start)
    try:
        facts = C.ensure(run_dir, "N6", 1, enable=True, document=_doc(preferred_port=0))
        layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
        assert Path(facts["home"]) == layout.home == C.home_for_attempt(run_dir, "N6", 1)
        assert (layout.home / ".credentials.yaml").is_file()
        provenance = A.home_provenance(layout.home)
        assert provenance.problems == (), provenance.problems
        assert [item["source"] for item in provenance.record()] == ["dsh_generated"]
        # 零回显：准入记录里不出现 secret 值
        assert "fake-dsh-generated-secret" not in str(provenance.record())
    finally:
        C.stop(run_dir, "N6")


# ---------------------------------------------------------------- 旧落账只读兼容

def test_stop_clears_legacy_metadata_and_keeps_homes(tmp_path: Path) -> None:
    """旧布局（并列 `dsh-web-home` + attempt `dsh-home`）的落账仍能被 `stop` 识别：只清落账。"""
    run_dir = _run_dir(tmp_path)
    layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
    layout.prepare()
    legacy = layout.root / C.LEGACY_WEB_HOME_DIRNAME
    legacy.mkdir()
    (legacy / ".credentials.yaml").write_text(DSH_GENERATED_SAMPLE, encoding="utf-8")
    (run_dir / IP.METADATA_NAME).write_text(
        '{"node":"N6","attempt":1,"host":"127.0.0.1","port":18799,"token":null}',
        encoding="utf-8")
    assert C.read_declared_attempt(run_dir) == 1          # 旧落账仍可读
    assert C.stop(run_dir, "N6") is False                 # 没有本进程实例 ⇒ 只清落账
    assert not (run_dir / IP.METADATA_NAME).exists()
    assert legacy.is_dir() and (legacy / ".credentials.yaml").is_file()   # 不迁移、不删除
    assert layout.home.is_dir()


def test_stop_recognises_in_process_instance_regardless_of_home_layout(tmp_path: Path) -> None:
    """实例登记按 `(run, node)` 而不是 home 布局 ⇒ 旧布局起出来的实例照样能停（只读兼容）。"""
    run_dir = _run_dir(tmp_path)
    legacy_home = run_dir / "agent_workspaces" / "N6" / "attempt-000001" / C.LEGACY_WEB_HOME_DIRNAME
    legacy_home.mkdir(parents=True)
    instance = _FakeInstance(WI.WebInstanceConfig(
        enabled=True, node=Path("/n"), bin=Path("/b"), version="0.2.1-rc.2", home=legacy_home))
    C._REGISTRY[C._key(run_dir, "N6")] = instance
    assert C.current(run_dir, "N6") is instance
    assert C.stop(run_dir, "N6") is True
    assert instance.stopped is True
    assert C.current(run_dir, "N6") is None


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
def test_real_instance_shares_attempt_home_and_ds09_allows_generated_secret(
        tmp_path: Path) -> None:
    """真机：起实例 → 落到**共用** home → DS-09 判 dsh_generated 放行 → 读者能读回 → 停后显式降级。"""
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
        # D3 + DS-09：实例与 attempt 共用同一 home；自生成的签名件被判 dsh_generated（放行）
        layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
        assert Path(facts["home"]) == layout.home
        assert (layout.home / ".credentials.yaml").is_file(), "dsh web 应在共用 home 里生成会话签名件"
        provenance = A.home_provenance(layout.home)
        assert provenance.problems == (), provenance.problems
        assert [item["source"] for item in provenance.record()] == ["dsh_generated"]
        # 零回显：真机自生成件的 secret 值不得出现在准入记录里
        import yaml
        generated = yaml.safe_load((layout.home / ".credentials.yaml").read_text(encoding="utf-8"))
        secret = generated["records"]["client-connection/browser-session"]["payload"]["secret"]
        assert secret not in json.dumps(provenance.record(), ensure_ascii=False)
        assert secret[:12] not in json.dumps(provenance.record(), ensure_ascii=False)
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



def test_instance_cwd_is_the_attempt_work_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D3 的第二个半边：实例进程 cwd = 该 attempt 的 `work`（dsh 按 cwd 分组会话）。

    路径同样**唯一来源**是 `AttemptLayout`；反向抽检：改 `workspace_root`，cwd 也跟着变。
    """
    run_dir = _run_dir(tmp_path)
    seen: list[WI.WebInstanceConfig] = []

    def fake_start(config: WI.WebInstanceConfig) -> _FakeInstance:
        seen.append(config)
        return _fake_start(config)

    monkeypatch.setattr(C.WI, "start", fake_start)
    try:
        facts = C.ensure(run_dir, "N6", 1, enable=True, document=_doc(preferred_port=0))
        layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
        assert C.workdir_for_attempt(run_dir, "N6", 1) == layout.work
        assert seen[0].workdir == layout.work, "Popen 的 cwd 必须是 attempt 的 work 目录"
        assert Path(facts["workdir"]) == layout.work
        assert Path(facts["home"]) == layout.home
    finally:
        C.stop(run_dir, "N6")


def test_workdir_for_attempt_has_no_second_path_implementation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """红线 8：`workdir` 也只从 `dsh_assets.workspace_root` 派生。"""
    sentinel = tmp_path / "sentinel-root"
    monkeypatch.setattr(A, "workspace_root", lambda run_dir, node, sequence: sentinel)
    assert C.workdir_for_attempt(tmp_path, "N6", 1) == A.AttemptLayout.under(sentinel).work


def test_ensure_refuses_to_start_on_a_non_compliant_home(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """防御纵深：CLI/诊断入口也先消费 DS-09 判据（不重算），home 有宿主件就不起进程。"""
    run_dir = _run_dir(tmp_path)
    layout = A.AttemptLayout.under(A.workspace_root(run_dir, "N6", 1))
    layout.prepare()
    (layout.home / "settings.yaml").write_text("x: 1\n", encoding="utf-8")
    started: list[object] = []
    monkeypatch.setattr(C.WI, "start", lambda config: started.append(config))
    with pytest.raises(C.WebCtlError) as info:
        C.ensure(run_dir, "N6", 1, enable=True, document=_doc(preferred_port=0))
    assert info.value.reason == "home_not_compliant"
    assert started == [], "home 不合规时不许起进程"
    assert not (run_dir / IP.METADATA_NAME).exists()
