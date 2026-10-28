"""S2-b 启动自检（SPEC-REV-14 B2/B3、DS-08/DS-09/DS-10；计划 §3.2）。

判据（不读实现也应成立）：
- **B2**：`toolNames` 里没有 `submit_result` ⇒ 自检失败（插件加载失败只出 warning，进程照起）；
- **B3**：`sandboxDefaultMode` 与钉死值一致 **且** preset 回显与钉死值一致；回显拿不到（unknown）⇒ 失败；
- **DS-09**：`attempt home` 不得含宿主 `settings.yaml`/凭据；回显的 home 必须是本次 attempt 的 home；
- **DS-10**：包裹内宿主 home 不可读 + 白名单外的 env 不继承（**不**检查 `/proc/<pid>/environ`——D1 残余风险）；
- 缺报告/坏 JSON/超时一律显式失败：**不许把"进程起来了"当准入**。

真 bwrap / 真 dsh 用例缺件即 `skip`（缺件是环境事实，不是通过）。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_process as DP
from host.agent_backends import dsh_selfcheck as SC

DSH_BIN = Path("/home/soft/DSH/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js")
NODE_BIN = Path("/home/soft/DSH/node/bin/node")


# ------------------------------------------------------------------ 夹具

@pytest.fixture()
def layout(tmp_path: Path) -> A.AttemptLayout:
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    return layout


def _preset_echo(**over) -> dict:
    echo = {
        "availability": "composition",
        "scope": "composition",
        "sessionScoped": False,
        "preset": A.DEFAULT_PRESET,
        "api": ["catalog()", "defaultPreset", "resolve(%s)" % A.DEFAULT_PRESET],
        "defaultPreset": A.DEFAULT_PRESET,
        "catalog": {"options": [A.DEFAULT_PRESET], "defaultOptions": [A.DEFAULT_PRESET],
                    "defaultPreset": A.DEFAULT_PRESET},
        "resolved": {"preset": A.DEFAULT_PRESET, "sandbox": A.DEFAULT_SANDBOX_MODE,
                     "approval": "ask"},
        "reason": None,
        "resolveError": None,
    }
    echo.update(over)
    return echo


def _report(layout: A.AttemptLayout, **over) -> dict:
    payload = {
        "plugin": "s2-selfcheck",
        "applied": True,
        "phase": "deferred",
        "pid": 4242,
        "toolNames": ["read", "bash", "submit_result"],
        "toolError": None,
        "sandboxDefaultMode": A.DEFAULT_SANDBOX_MODE,
        "sandboxModeError": None,
        "presetEcho": _preset_echo(),
        "home": str(layout.home),
        "patches": [str(layout.patch_dir / "00-pins.yml")],
    }
    payload.update(over)
    return payload


def _write(layout: A.AttemptLayout, payload: dict | str | None = None) -> Path:
    path = layout.selfcheck_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if payload is None:
        payload = _report(layout)
    text = payload if isinstance(payload, str) else json.dumps(payload)
    path.write_text(text, encoding="utf-8")
    return path


def _verify(layout: A.AttemptLayout, **over):
    kwargs = {"expected_mode": A.DEFAULT_SANDBOX_MODE,
              "expected_preset": A.DEFAULT_PRESET, "timeout_s": 0.0}
    kwargs.update(over)
    return SC.verify_session(layout, **kwargs)


# ------------------------------------------------------------------ B2/B3/DS-09：verify_session

def test_clean_report_passes(layout: A.AttemptLayout) -> None:
    _write(layout)
    result = _verify(layout)
    assert result.ok, result.problems
    assert result.facts["plugin"] == "s2-selfcheck" and result.facts["applied"] is True
    result.require_ok()          # 宿主可直接用：不通过就抛


def test_verify_session_polls_until_report_appears(layout: A.AttemptLayout) -> None:
    """插件是异步激活的：钩子读到文件前允许等一小段（超时仍缺 ⇒ 失败）。"""
    import threading

    def _later() -> None:
        time.sleep(0.15)
        _write(layout)

    threading.Thread(target=_later, daemon=True).start()
    assert _verify(layout, timeout_s=3.0).ok


async def test_averify_session_waits_without_blocking(layout: A.AttemptLayout) -> None:
    """生产钩子在事件循环里跑：用 async 版等落盘，不阻塞 dsh 的 stdout 收帧。"""
    async def _later() -> None:
        await asyncio.sleep(0.15)
        _write(layout)

    task = asyncio.create_task(_later())
    result = await SC.averify_session(layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
                                      expected_preset=A.DEFAULT_PRESET, timeout_s=3.0)
    await task
    assert result.ok, result.problems


async def test_averify_session_missing_report_fails(layout: A.AttemptLayout) -> None:
    result = await SC.averify_session(layout, timeout_s=0.0)
    assert not result.ok
    assert any("selfcheck.json" in problem for problem in result.problems)


def test_missing_report_fails(layout: A.AttemptLayout) -> None:
    result = _verify(layout)
    assert not result.ok
    assert any("selfcheck.json" in problem for problem in result.problems)


def test_bad_json_fails(layout: A.AttemptLayout) -> None:
    _write(layout, '{"plugin": "s2-selfcheck", ')
    result = _verify(layout)
    assert not result.ok
    assert any("坏 JSON" in problem for problem in result.problems)


def test_report_not_object_fails(layout: A.AttemptLayout) -> None:
    _write(layout, "[1, 2, 3]")
    with pytest.raises(SC.SelfCheckFailed):
        _verify(layout).require_ok()


def test_applied_false_fails(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, applied=False, error="boom"))
    result = _verify(layout)
    assert not result.ok
    assert any("applied" in problem or "未完成" in problem for problem in result.problems)


def test_missing_submit_result_fails(layout: A.AttemptLayout) -> None:
    """B2：插件没挂上时 dsh 只出 warning，工具清单里就没有 submit_result。"""
    _write(layout, _report(layout, toolNames=["read", "bash"]))
    result = _verify(layout)
    assert not result.ok
    joined = "；".join(result.problems)
    assert "submit_result" in joined and "B2" in joined


def test_apply_phase_snapshot_is_not_ready(layout: A.AttemptLayout) -> None:
    """apply 期快照是**诊断**用（实测那时 toolNames=[]、sandboxPolicy 取不到）⇒ 不得当准入。"""
    _write(layout, _report(layout, phase="apply", toolNames=[], sandboxDefaultMode=None,
                           presetEcho={"availability": "unknown",
                                       "reason": 'ctx.get("sandboxPolicy") 返回空'}))
    result = _verify(layout)
    assert not result.ok
    joined = "；".join(result.problems)
    assert "apply" in joined and "deferred" in joined


def test_tool_names_unavailable_fails(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, toolNames=None, toolError="ctx.tools.schemas() 抛错：boom"))
    result = _verify(layout)
    assert not result.ok
    assert any("工具清单" in problem for problem in result.problems)


def test_sandbox_mode_mismatch_fails(layout: A.AttemptLayout) -> None:
    """B3：只钉 defaultPreset 不钉 mode（或反过来）会被覆盖。"""
    _write(layout, _report(layout, sandboxDefaultMode="danger-full-access"))
    result = _verify(layout)
    assert not result.ok
    assert any("B3" in problem and "sandbox" in problem for problem in result.problems)


def test_preset_echo_unknown_fails(layout: A.AttemptLayout) -> None:
    """拿不到 preset 回显 ⇒ 不得以"进程起来了"当准入（计划 §6-1）。"""
    _write(layout, _report(layout, presetEcho={"availability": "unknown",
                                              "reason": "ctx.get('permissionPresets') 返回空"}))
    result = _verify(layout)
    assert not result.ok
    assert any("回显" in problem and "unknown" in problem for problem in result.problems)


def test_preset_mismatch_fails(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, presetEcho=_preset_echo(preset="workspace-write")))
    result = _verify(layout)
    assert not result.ok
    assert any("B3" in problem and "preset" in problem for problem in result.problems)


def test_preset_resolve_error_fails(layout: A.AttemptLayout) -> None:
    """回显名对但档位包解析不了（preset 不在配置表里）⇒ 双钉不成立，显式失败。"""
    _write(layout, _report(layout, presetEcho=_preset_echo(
        resolved=None, resolveError='unknown preset "read-only" (known: workspace-write)')))
    result = _verify(layout)
    assert not result.ok
    assert any("档位包" in problem for problem in result.problems)


def test_preset_resolved_sandbox_mismatch_fails(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, presetEcho=_preset_echo(
        resolved={"preset": A.DEFAULT_PRESET, "sandbox": "danger-full-access",
                  "approval": "never"})))
    result = _verify(layout)
    assert not result.ok
    assert any("档位包" in problem and "沙箱" in problem for problem in result.problems)


def test_home_with_host_settings_fails(layout: A.AttemptLayout) -> None:
    """DS-09：宿主 settings 被复制进 attempt home ⇒ 权限档可被宿主值覆盖。"""
    (layout.home / "settings.yaml").write_text(
        "permission-presets:\n  defaultPreset: danger-full-access\n", encoding="utf-8")
    _write(layout)
    result = _verify(layout)
    assert not result.ok
    assert any("DS-09" in problem and "settings.yaml" in problem for problem in result.problems)


def test_home_mismatch_fails(layout: A.AttemptLayout) -> None:
    """自检回显的 home 不是本次 attempt 的 home ⇒ 隔离证据不成立。"""
    _write(layout, _report(layout, home="/host/home/somewhere"))
    result = _verify(layout)
    assert not result.ok
    assert any("home" in problem for problem in result.problems)


def test_verify_home_clean_and_dirty(tmp_path: Path) -> None:
    home = tmp_path / "dsh-home"
    home.mkdir()
    assert SC.verify_home(home) == []
    (home / ".credentials.yaml").write_text("x: y\n", encoding="utf-8")
    assert SC.verify_home(home)


def test_verify_home_reuses_assets_home_problems(tmp_path: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """红线 8：DS-09 判据只有一套实现（复用 dsh_assets.home_problems）。"""
    home = tmp_path / "dsh-home"
    home.mkdir()
    monkeypatch.setattr(A, "home_problems", lambda path: ["sentinel-from-assets"])
    assert SC.verify_home(home) == ["sentinel-from-assets"]


# ------------------------------------------------------------------ DS-10：build_wrap_argv 组成（不执行）

def _spec(tmp_path: Path, **over) -> DP.AttemptSpec:
    cwd = tmp_path / "attempt" / "work"
    home = tmp_path / "attempt" / "dsh-home"
    for path in (cwd, home):
        path.mkdir(parents=True, exist_ok=True)
    base = dict(attempt_key="RUN-TEST/N6/1", cwd=cwd, home=home, task="只回复 OK",
                dsh_bin=tmp_path / "dsh-bin.js", node=Path(sys.executable),
                timeout_s=5.0, wrap=True)
    base.update(over)
    return DP.AttemptSpec(**base)


def test_build_wrap_argv_composition(tmp_path: Path) -> None:
    """dsh 与自检探针必须用**同一套**隔离参数（红线 8：不出现第二套口径）。"""
    layout_dirs = tmp_path / "attempt"
    assets_dir = layout_dirs / "plugin"
    state_dir = layout_dirs / "selfcheck"
    for path in (assets_dir, state_dir):
        path.mkdir(parents=True, exist_ok=True)
    spec = _spec(tmp_path, asset_dirs=(assets_dir,), state_dirs=(state_dir,))
    inner = ["/usr/bin/env"]
    argv = DP.build_wrap_argv(spec, inner)

    assert argv[0] == "bwrap"
    assert argv[-1] == inner[-1] and argv[-len(inner):] == inner   # inner 原样在最内层
    text = " ".join(argv)
    assert "--ro-bind / /" in text                       # 全盘只读
    assert f"--tmpfs {Path.home()}" in text              # 宿主 home 整体遮蔽
    assert f"--bind {spec.cwd} {spec.cwd}" in text       # attempt cwd 可写
    assert f"--bind {spec.home} {spec.home}" in text     # DSH_HOME 可写
    assert f"--ro-bind {assets_dir} {assets_dir}" in text
    assert f"--bind {state_dir} {state_dir}" in text
    assert "--unshare-pid" in argv and "--die-with-parent" in argv and "--new-session" in argv
    # 宿主 home 不得被写成可写挂载
    assert f"--bind {Path.home()} {Path.home()}" not in text
    # 不得出现 `--clearenv`（bwrap 0.4.0 不支持；等价物是 env 白名单）
    assert "--clearenv" not in argv


def test_build_wrap_argv_without_wrap_returns_inner(tmp_path: Path) -> None:
    spec = _spec(tmp_path, wrap=False)
    inner = ["echo", "hi"]
    assert DP.build_wrap_argv(spec, inner) == inner


def test_build_argv_uses_build_wrap_argv(tmp_path: Path) -> None:
    """拆函数后 `build_argv` 语义不变：dsh argv = 同一个包裹函数 + dsh inner。"""
    spec = _spec(tmp_path, patches=(tmp_path / "00-pins.yml",))
    inner = [str(spec.node), str(spec.dsh_bin), "--profile", spec.profile,
             "--patch", str(spec.patches[0]), "--json", spec.task]
    assert DP.build_argv(spec) == DP.build_wrap_argv(spec, inner)


# ------------------------------------------------------------------ run_attempt(on_start=...)

STUB_QUIET = '''#!/usr/bin/env python3
import json, os, sys, time, subprocess
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(os.environ["STUB_CHILD_PIDFILE"], "w").write(str(child.pid))
time.sleep(120)
'''


def _stub(tmp_path: Path, body: str, name: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


async def test_on_start_runs_after_spawn(tmp_path: Path) -> None:
    stub = _stub(tmp_path, '''#!/usr/bin/env python3
import json, os, sys
def emit(o):
    sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
emit({"type": "session", "sessionId": "s", "cwd": os.getcwd()})
emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
emit({"type": "final", "text": "OK"})
''', "dsh_ok.py")
    spec = _spec(tmp_path, dsh_bin=stub, wrap=False)
    seen: list[str] = []

    async def on_start() -> None:
        seen.append("called")

    outcome = await DP.run_attempt(spec, on_start=on_start)
    assert seen == ["called"] and outcome.status == "completed"


async def test_on_start_failure_stops_group_and_raises(tmp_path: Path) -> None:
    """自检钩子抛错 ⇒ TERM→KILL 进程组后显式失败（不留孤儿，不降级为告警）。"""
    pidfile = tmp_path / "child.pid"
    stub = _stub(tmp_path, STUB_QUIET, "dsh_hang.py")
    spec = _spec(tmp_path, dsh_bin=stub, stop_grace_s=2.0, timeout_s=60, wrap=False,
                 env_extra={"STUB_CHILD_PIDFILE": str(pidfile)})

    async def on_start() -> None:
        # 等 stub 起好子孙进程再抛（自检钩子本身就是"轮询到事实再判"）
        deadline = time.monotonic() + 5.0
        while not pidfile.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        raise SC.SelfCheckFailed("B2：工具清单缺 submit_result")

    with pytest.raises(SC.SelfCheckFailed):
        await DP.run_attempt(spec, on_start=on_start)
    assert pidfile.exists(), "stub 未起子孙进程，用例无效"
    child = int(pidfile.read_text().strip())
    assert not Path(f"/proc/{child}").exists(), f"子孙进程 {child} 未被清理"


# ------------------------------------------------------------------ DS-10：attest_wrap

def test_attest_wrap_without_wrap_fails_explicitly(tmp_path: Path) -> None:
    spec = _spec(tmp_path, wrap=False)
    result = SC.attest_wrap(spec)
    assert not result.ok
    assert any("wrap" in problem for problem in result.problems)


def test_attest_wrap_probe_outside_host_home_is_rejected(tmp_path: Path) -> None:
    """探针不在宿主 home 之下 ⇒ 这条断言没有意义（防止自证变空转）。"""
    probe = tmp_path / "probe.txt"
    probe.write_text("x", encoding="utf-8")
    result = SC.attest_wrap(_spec(tmp_path), probe_file=probe)
    assert not result.ok
    assert any("宿主 home" in problem for problem in result.problems)


def _host_home_probe_file() -> Path:
    """在**宿主 home 之内**造探针（本仓在宿主 home 下，且可写）。"""
    root = Path(__file__).resolve().parents[2]
    path = root / (".dsh-selfcheck-probe-%s" % uuid.uuid4().hex[:12])
    path.write_text("sentinel\n", encoding="utf-8")
    return path


@pytest.mark.skipif(not __import__("shutil").which("bwrap"), reason="本机无 bwrap（环境缺件，不是通过）")
def test_attest_wrap_real_bwrap_masks_host_home_and_env(tmp_path: Path) -> None:
    probe = _host_home_probe_file()
    sentinel_key = "DSH_SELFCHECK_SENTINEL_%s" % uuid.uuid4().hex[:8]
    layout_dirs = tmp_path / "attempt"
    state_dir = layout_dirs / "selfcheck"
    state_dir.mkdir(parents=True, exist_ok=True)
    spec = _spec(tmp_path, state_dirs=(state_dir,))
    os.environ[sentinel_key] = "must-not-leak"
    try:
        result = SC.attest_wrap(spec, probe_file=probe)
    finally:
        os.environ.pop(sentinel_key, None)
        probe.unlink(missing_ok=True)

    assert result.ok, result.problems
    assert result.probe_visible is False, "宿主 home 里的探针在包裹内可见 ⇒ DS-10 不成立"
    assert sentinel_key not in result.env_keys, "父进程哨兵环境变量被继承了"
    assert "PUBLIC_API_KEY" not in result.env_keys
    # 包裹内 env 必须是白名单：不多（不继承）也不少（dsh 还能起）。
    # PWD 是 bwrap 自己按子进程 cwd 设的（实测），不算"继承"。
    assert set(result.env_keys) <= set(DP.build_env(spec)) | {"PWD"}
    assert {"PATH", "HOME", "DSH_HOME"} <= set(result.env_keys)


# ------------------------------------------------------------------ 真 dsh（无 key；缺件 skip）

def _dsh_spec(layout: A.AttemptLayout, patches=(), **over) -> DP.AttemptSpec:
    base = dict(attempt_key="RUN-TEST/N6/real", cwd=layout.work, home=layout.home,
                task="只回复 OK", dsh_bin=DSH_BIN, node=NODE_BIN,
                patches=tuple(patches), profile="headless", timeout_s=180.0,
                wrap=True, env_extra={"DSH_SELFCHECK_DIR": str(layout.selfcheck_dir)},
                asset_dirs=(layout.plugin_dir, layout.patch_dir),
                state_dirs=(layout.selfcheck_dir,))
    base.update(over)
    return DP.AttemptSpec(**base)


def _skip_reason() -> str | None:
    if not DSH_BIN.is_file():
        return "本机无该 DSH 安装（%s）" % DSH_BIN
    if not __import__("shutil").which("bwrap"):
        return "本机无 bwrap"
    return None


async def test_real_dsh_report_lands_and_b2_rejects(tmp_path: Path) -> None:
    """真 dsh + 只挂自检插件：报告落盘、工具清单非空，且 verify_session 因缺
    submit_result **失败** —— 这正是 B2 判据有效的证据（缺提交工具不阻断启动）。"""
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    assets = A.materialize(layout, pins=A.Pins(),
                           plugins=(A.Plugin("s2-selfcheck", "selfcheck.mjs"),))
    spec = _dsh_spec(layout, patches=assets.patch_files)
    seen: dict = {}

    async def on_start() -> None:
        # 钩子只记录（本用例要看到"无 key ⇒ 非零退出"），不在这里拦
        seen["result"] = await SC.averify_session(
            layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
            expected_preset=A.DEFAULT_PRESET, timeout_s=90.0)

    with pytest.raises(DP.ProcessFailed):     # 无 key ⇒ MISSING_CREDENTIAL，非零退出
        await DP.run_attempt(spec, on_start=on_start)

    payload = json.loads(layout.selfcheck_file().read_text(encoding="utf-8"))
    assert payload["applied"] is True and payload["plugin"] == "s2-selfcheck"
    assert payload["phase"] == "deferred", "只拿到 apply 期快照：工具/服务可能还没就绪"
    assert payload["toolNames"], "工具清单为空：插件/工具加载失败不能当准入"
    assert "submit_result" not in payload["toolNames"]   # 本片没挂提交插件
    result = seen["result"]
    assert not result.ok
    joined = "；".join(result.problems)
    assert "B2" in joined and "submit_result" in joined


async def test_real_dsh_preset_echo_with_full_pins_patch(tmp_path: Path) -> None:
    """B3 回显链路（真 dsh）：permission 的 patch config 是**整块替换**，
    正确的钉死 patch 必须带完整 presets 表；此时 preset 回显 = 钉死值。

    注：本用例自建 patch 只为验证回显通路，不改 `dsh_assets`（那是 Lead 写权）。
    """
    reason = _skip_reason()
    if reason:
        pytest.skip(reason)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    assets = A.materialize(layout, plugins=(A.Plugin("s2-selfcheck", "selfcheck.mjs"),))
    pins = layout.patch_dir / "00-pins-full.yml"
    pins.write_text(
        "- id: sandbox-policy\n"
        "  config:\n"
        "    mode: %s\n"
        "- id: permission\n"
        "  config:\n"
        "    presets:\n"
        "      %s:\n"
        "        sandbox: %s\n"
        "        approval: ask\n"
        "      workspace-write:\n"
        "        sandbox: workspace-write\n"
        "        approval: ask\n"
        "      danger-full-access:\n"
        "        sandbox: danger-full-access\n"
        "        approval: never\n"
        "    defaultPreset: %s\n"
        % (A.DEFAULT_SANDBOX_MODE, A.DEFAULT_PRESET, A.DEFAULT_SANDBOX_MODE, A.DEFAULT_PRESET),
        encoding="utf-8")
    spec = _dsh_spec(layout, patches=(pins, assets.patch_files[-1]))

    async def on_start() -> None:
        result = await SC.averify_session(layout, expected_mode=A.DEFAULT_SANDBOX_MODE,
                                          expected_preset=A.DEFAULT_PRESET, timeout_s=90.0)
        # B3/DS-09 必须通过；只剩 B2（本片没挂 submit_result 插件）才允许继续看"无 key"失败
        blocking = [problem for problem in result.problems if not problem.startswith("B2")]
        if blocking:
            raise SC.SelfCheckFailed("；".join(blocking))

    with pytest.raises(DP.ProcessFailed):
        await DP.run_attempt(spec, on_start=on_start)

    payload = json.loads(layout.selfcheck_file().read_text(encoding="utf-8"))
    echo = payload["presetEcho"]
    assert echo["availability"] == "composition"
    assert echo["preset"] == A.DEFAULT_PRESET
    assert echo["resolved"] == {"preset": A.DEFAULT_PRESET,
                               "sandbox": A.DEFAULT_SANDBOX_MODE, "approval": "ask"}
    assert echo["sessionScoped"] is False      # 计划 §6-1：session 级 preset 未回显
    assert payload["sandboxDefaultMode"] == A.DEFAULT_SANDBOX_MODE


# ------------------------------------------------------------------ 身份 join（独立复核 P1-1）

def test_expected_nonce_mismatch_fails(layout: A.AttemptLayout) -> None:
    """自检报告必须回显**本次** attempt 的 nonce：旧快照不得当准入。"""
    _write(layout, _report(layout, nonce="old-nonce", attemptKey="RUN-TEST/N6/1"))
    result = _verify(layout, expected_nonce="new-nonce",
                     expected_attempt_key="RUN-TEST/N6/1")
    assert not result.ok
    assert any("nonce" in problem for problem in result.problems), result.problems


def test_expected_attempt_key_mismatch_fails(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, nonce="n1", attemptKey="RUN-OTHER/N6/1"))
    result = _verify(layout, expected_nonce="n1", expected_attempt_key="RUN-TEST/N6/1")
    assert not result.ok
    assert any("attemptKey" in problem for problem in result.problems), result.problems


def test_matching_nonce_and_attempt_key_passes(layout: A.AttemptLayout) -> None:
    _write(layout, _report(layout, nonce="n1", attemptKey="RUN-TEST/N6/1"))
    result = _verify(layout, expected_nonce="n1", expected_attempt_key="RUN-TEST/N6/1")
    assert result.ok, result.problems


async def test_async_gate_requires_nonce(layout: A.AttemptLayout) -> None:
    """`averify_session`（on_start 用的入口）也必须做身份 join。"""
    _write(layout, _report(layout, nonce="stale", attemptKey="RUN-TEST/N6/1"))
    result = await SC.averify_session(layout, timeout_s=0.0,
                                      expected_nonce="fresh",
                                      expected_attempt_key="RUN-TEST/N6/1")
    assert not result.ok
    assert any("nonce" in problem for problem in result.problems), result.problems
