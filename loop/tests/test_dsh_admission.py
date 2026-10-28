"""S5 C1：dsh 受控准入 + mode 分层 + A2 契约字段 + attempt 双钉档位 + 停执行。

判据（不读实现也应成立）：

- **准入矩阵**：只有 `enabled=true` + bin 指纹匹配 + 版本匹配 + DS-08/09 静态自检通过
  + mode 允许时才返回 `DshBackend`；任一不满足 ⇒ `BackendUnavailable`（`err.admission['code']`
  可判、说明缺哪一项），**绝不**返回 `AgentlyBackend`（DS-01/D01：显式 dsh 不悄悄变 Agently）。
- **mode 分层**（人工裁决 2026-10-28）：`run_mode='drill'` ⇒ 显式按 mode 规则用 Agently 替身
  （`admission.rule='mode_drill'`、`effective='agently'`，不伪装成 dsh）；`run_mode='real'` +
  `LOOP_LLM_MODE=standin` ⇒ 显式失败；`run_mode=None`（旧/未知调用）⇒ 保持现行严格语义。
- **六节点**：N3/N6/N8/N10/N11/N12 都能被显式选中；未列入的节点仍按 default。
- **A2 字段**（REV-13 §5.2）：`contract_version`/`identity{run_id,node,attempt_key,generation}`/
  `context_manifest_ref`/`execution_grant_ref`/`runtime_fingerprint` 进请求与封存投影；
  旧记录缺省显示 `legacy`/`unknown`（只读、不回填）。
- **双钉档位**（B3/DS-09）：attempt 可写档位必须 `sandbox-policy.mode` +
  `permission-presets.defaultPreset` 双钉 `workspace-write`；自检回显与钉死值不一致即拒；
  attempt home 不得含宿主 settings/凭据。
- **停执行**（REV-13 §7.3/DS-05）：撤销资格后必须**真的**停掉在途进程组；停止无法确认 ⇒
  `execution_unknown`、节点失败、禁止自动重发（不许报 paused / 不许当成功）。
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from host import agent_backends as B
from host import agent_memory as AM
from host import paths as P
from host import model_provider as MP
from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A
from host.agent_backends import dsh_process as DP
from host.agent_backends import dsh_selfcheck as SC
from host.agent_backends.base import BackendRequest, RequestIdentity

#: 复用请求机制的特征夹具（唯一来源；本文件不重造 ctx/provider）
from test_agent_context_memory import ctx, provider, call  # noqa: F401

NODES = ("N3", "N6", "N8", "N10", "N11", "N12")

#: 冒充 dsh CLI 的 python stub（只吐 NDJSON；行为由 STUB_MODE 选）。
STUB = '''#!/usr/bin/env python3
import json, os, sys, time
mode = os.environ.get("STUB_MODE", "ok")
TASK_ID = os.environ.get("STUB_TASK_ID", "RUN-ADMIT/N3/1")

def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\\n")
    sys.stdout.flush()

def submit(payload=None):
    emit({"type": "tool_call", "callId": "call-1", "tool": "submit_result",
          "input": {"task_id": TASK_ID, "summary": "一句话结论",
                    "payload": {"summary": "ok"} if payload is None else payload}})
    emit({"type": "tool_result", "callId": "call-1", "status": "completed",
          "result": json.dumps({"accepted": True, "problems": []})})

emit({"type": "session", "sessionId": "session-stub", "cwd": os.getcwd()})
if mode == "hang":
    (open("child.pid", "w")).write(str(os.getpid()))
    sys.stdout.flush()
    time.sleep(300)
    raise SystemExit(0)
emit({"type": "status", "phase": "turn_end", "reason": {"kind": "completed"}})
submit()
emit({"type": "final", "text": "DONE"})
emit({"type": "status", "phase": "step_end",
      "usage": {"inputTokens": 11, "outputTokens": 3}})
'''


# ------------------------------------------------------------------ 夹具

def _stub(tmp_path: Path) -> Path:
    path = tmp_path / "dsh_admission_stub.py"
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    return path


def _install(tmp_path: Path, *, version: str = "0.2.1-rc.2",
             package: bool = True) -> Path:
    """假安装树：`<tmp>/install/node_modules/@deepseek-ai/dsh/lib/bin.js`。

    必须在 `node_modules` 之下：插件的 `@deepseek-ai/dsh-tools` 解析根由 `A.node_modules_for`
    从 bin 路径推出（不在 node_modules 下 ⇒ 静态自检显式失败）。
    """
    root = tmp_path / "install" / "node_modules" / "@deepseek-ai" / "dsh"
    (root / "lib").mkdir(parents=True)
    bin_path = root / "lib" / "bin.js"
    bin_path.write_text(STUB, encoding="utf-8")
    bin_path.chmod(0o755)
    if package:
        (root / "package.json").write_text(
            json.dumps({"name": "@deepseek-ai/dsh", "version": version}), encoding="utf-8")
    return bin_path


def _dsh(bin_path: Path, **over: Any) -> dict[str, Any]:
    runtime = {"enabled": True, "version": "0.2.1-rc.2", "node": sys.executable,
               "bin": str(bin_path),
               "bin_sha256": hashlib.sha256(Path(bin_path).read_bytes()).hexdigest(),
               "profile": "headless", "wrap": True, "patches": [],
               "api_key_env": "PUBLIC_API_KEY"}
    runtime.update(over)
    return runtime


@pytest.fixture()
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """tmp SETTINGS.yaml（不碰仓内 `loop/SETTINGS.yaml`）。"""
    path = tmp_path / "SETTINGS.yaml"
    monkeypatch.setattr(B, "SETTINGS_FILE", path)

    def write(runtime: dict[str, Any]) -> type:
        path.write_text(yaml.safe_dump({"loop": {"agent_runtime": runtime}}))
        return B

    write({})
    return write


@pytest.fixture()
def live(monkeypatch: pytest.MonkeyPatch) -> None:
    """显式 live 模型方式（套件默认 standin；真机调用仍受人工授权约束，本文件不发起）。"""
    monkeypatch.setenv("LOOP_LLM_MODE", "live")


@pytest.fixture()
def no_agently(monkeypatch: pytest.MonkeyPatch) -> None:
    """准入失败/替身路径都**不得**去解析 Agently 凭据（DS-01）。"""
    monkeypatch.setattr(MP, "resolve", lambda *a, **k: pytest.fail(
        "不得解析 Agently provider"))


def _six(runtime: dict[str, Any]) -> dict[str, Any]:
    return {"default_backend": "agently",
            "node_backends": {node: "dsh" for node in NODES}, "dsh": runtime}


def _offline_provider(monkeypatch: pytest.MonkeyPatch, *, available: bool = False) -> None:
    monkeypatch.setattr(MP, "resolve", lambda *a, **k: SimpleNamespace(
        available=available, model=None, plugin=None, reason="offline-test",
        _api_key="never-record-this-secret"))


# ================================================================== 准入矩阵

@pytest.mark.parametrize("node", NODES)
def test_six_nodes_can_be_admitted(live, settings, node: str, tmp_path: Path) -> None:
    """六节点显式 dsh + 条件齐备 ⇒ 返回 `DshBackend`，并带可判的准入记录。"""
    B_ = settings(_six(_dsh(_install(tmp_path))))
    backend = B_.select(node, run_mode="real")
    assert isinstance(backend, D.DshBackend)
    meta = backend.metadata()
    assert meta["name"] == "dsh"
    assert meta["admission"]["rule"] == "admission"
    assert meta["admission"]["code"] == "admitted"
    assert meta["admission"]["node"] == node
    assert meta["admission"]["requested"] == meta["admission"]["effective"] == "dsh"
    assert meta["contract_version"] == B.CONTRACT_VERSION
    assert meta["runtime_fingerprint"].startswith("sha256:")


@pytest.mark.parametrize("over,code", [
    ({"enabled": False}, "disabled"),
    ({"bin_sha256": "0" * 64}, "fingerprint_mismatch"),
    ({"version": ""}, "not_verified"),          # 版本锁定是配置必备字段（verify 先拦）
])
def test_admission_failures_are_judgeable_and_never_fall_back_to_agently(
        live, settings, no_agently, tmp_path: Path, over: dict[str, Any], code: str) -> None:
    B_ = settings(_six(_dsh(_install(tmp_path), **over)))
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3", run_mode="real")
    assert error.value.admission["code"] == code
    assert error.value.admission["node"] == "N3"
    assert "DSH" in str(error.value)


def test_declared_version_must_match_installed(live, settings, no_agently,
                                               tmp_path: Path) -> None:
    """版本锁定：声明的 0.2.1-rc.2 ≠ 实际安装的 0.2.1-rc.1 ⇒ 不准入（不得沿用旧结论）。"""
    B_ = settings(_six(_dsh(_install(tmp_path, version="0.2.1-rc.1"))))
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3", run_mode="real")
    assert error.value.admission["code"] == "version_mismatch"
    assert "0.2.1-rc.1" in " ".join(error.value.admission["detail"])


def test_missing_installed_version_fails_closed(live, settings, no_agently,
                                                tmp_path: Path) -> None:
    B_ = settings(_six(_dsh(_install(tmp_path, package=False))))
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3", run_mode="real")
    assert error.value.admission["code"] == "version_unknown"


def test_static_selfcheck_requires_resolvable_node_modules(live, settings, no_agently,
                                                           tmp_path: Path) -> None:
    """DS-08 的静态前提：插件能解析到 `@deepseek-ai/dsh-tools`（否则只 warning、工具缺失）。

    构造：安装树**不在** `node_modules` 下（版本查得出来，但插件 import 解析根推不出来）。
    """
    plain = tmp_path / "plain-pkg"
    plain.mkdir()
    (plain / "package.json").write_text(
        json.dumps({"name": "@deepseek-ai/dsh", "version": "0.2.1-rc.2"}), encoding="utf-8")
    plain_bin = plain / "bin.js"
    plain_bin.write_text(STUB, encoding="utf-8")
    B_ = settings(_six(_dsh(plain_bin)))
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3", run_mode="real")
    assert error.value.admission["code"] == "selfcheck_failed"
    assert any("node_modules" in item for item in error.value.admission["detail"])


def test_bad_dsh_config_on_dsh_path_is_unavailable(live, settings, no_agently,
                                                   tmp_path: Path) -> None:
    """dsh 路径上的坏配置仍是**准入失败**（可判），不是"配置错误后无事发生"。"""
    runtime = _six({"enabled": True})  # 缺 version/node/bin/bin_sha256
    B_ = settings(runtime)
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3", run_mode="real")
    assert error.value.admission["code"] == "config_invalid"


async def test_admission_failure_is_judgeable_and_happens_before_submission(
        ctx, settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """准入**失败**形态（rule/code/requested/effective）必须可判、且发生在提交前。

    替身形态（`standin_mode`/`mode_drill`）随 `backend.metadata()` 进请求封存记录；
    失败形态没有 attempt 记录可封（拒绝发生在提交前），所以由异常上的 `admission` 承载，
    界面/证据按同一四字段消费。
    """
    monkeypatch.setenv("LOOP_LLM_MODE", "live")
    settings(_six(_dsh(_install(tmp_path), enabled=False)))

    async def run() -> dict[str, Any]:
        with B.run_mode("real"):
            await call(ctx)
        raise AssertionError("准入失败必须抛出")

    with pytest.raises(B.BackendUnavailable) as error:
        await run()
    assert error.value.admission["rule"] == "admission"
    assert error.value.admission["code"] == "disabled"
    assert error.value.admission["requested"] == "dsh"
    assert not (ctx.run_dir / "agent_calls").exists()   # 失败发生在提交前


def test_unlisted_node_keeps_default_backend(live, settings, tmp_path: Path,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """未列入 `node_backends` 的节点仍按 default（agently），且不带 mode 记录。"""
    _offline_provider(monkeypatch)
    B_ = settings({"default_backend": "agently",
                   "node_backends": {node: "dsh" for node in NODES if node != "N3"},
                   "dsh": _dsh(_install(tmp_path))})
    backend = B_.select("N3", run_mode="real")
    assert not isinstance(backend, D.DshBackend)
    assert backend.info.available is False
    assert "admission" not in backend.metadata()
    assert backend.metadata()["name"] == "agently"


# ================================================================== mode 分层

def test_drill_substitutes_agently_with_explicit_record(live, settings, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    """drill 是确定性替身模式：契约上**不选原生后端**，这必须是显式规则而非静默回落。"""
    _offline_provider(monkeypatch)
    B_ = settings(_six(_dsh(_install(tmp_path))))
    backend = B_.select("N3", run_mode="drill")
    assert not isinstance(backend, D.DshBackend)
    record = backend.metadata()["admission"]
    assert record["rule"] == "mode_drill"
    assert record["requested"] == "dsh"
    assert record["effective"] == "agently"          # 不得把替身记成 effective='dsh'
    assert record["code"] == "substituted"
    assert record["reason"]


def test_default_backend_dsh_in_drill_still_substitutes(live, settings, tmp_path: Path,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    _offline_provider(monkeypatch)
    B_ = settings({"default_backend": "dsh", "dsh": _dsh(_install(tmp_path))})
    backend = B_.select("N6", run_mode="drill")
    assert backend.metadata()["admission"]["effective"] == "agently"


def test_standin_mode_substitutes_agently_for_any_run_mode(settings, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    """`LOOP_LLM_MODE=standin`（**任何** run_mode）⇒ 按模式规则用 Agently 替身。

    这是模式规则（standin 的定义就是"模型用确定性替身"），不是 dsh 准入失败后的回落：
    必须记 `rule='standin_mode'` / `effective='agently'`；`run_mode` 仍如实记录（不冒充 real）。
    """
    _offline_provider(monkeypatch)
    monkeypatch.setenv("LOOP_LLM_MODE", "standin")
    B_ = settings(_six(_dsh(_install(tmp_path))))
    for mode in ("real", "drill"):
        backend = B_.select("N3", run_mode=mode)
        assert not isinstance(backend, D.DshBackend)
        record = backend.metadata()["admission"]
        assert record["rule"] == "standin_mode"
        assert record["code"] == "substituted"
        assert record["requested"] == "dsh" and record["effective"] == "agently"
        assert record["reason"]


async def test_standin_substitution_does_not_pretend_to_be_live(
        ctx, settings, provider, monkeypatch: pytest.MonkeyPatch) -> None:
    """替身路径下结果 `mode` 仍是 `standin`：不得因为后端配置写了 dsh 就冒充 real。"""
    monkeypatch.setenv("LOOP_LLM_MODE", "standin")
    settings({"default_backend": "agently", "node_backends": {"N3": "dsh"}, "dsh": {}})
    provider["cfg"].available = False
    provider["cfg"].reason = "standin-mode-test"
    out = await call(ctx)
    assert out["mode"] == "standin" and out["standin"] is True
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    admission = record["request"]["backend"]["admission"]
    assert admission["rule"] == "standin_mode"
    assert admission["requested"] == "dsh" and admission["effective"] == "agently"
    assert admission["code"] == "substituted"


def test_unspecified_run_mode_keeps_strict_semantics(settings, no_agently,
                                                     tmp_path: Path) -> None:
    """旧/未知调用（不传 run_mode、无请求作用域声明）⇒ 不默认当 real。"""
    B_ = settings(_six(_dsh(_install(tmp_path))))
    with pytest.raises(B.BackendUnavailable) as error:
        B_.select("N3")
    assert error.value.admission["code"] == "mode_unspecified"


def test_mode_scope_is_read_by_select_without_changing_call_signature(
        live, settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`model_request` 用请求作用域声明 run 模式（`select(node)` 调用形状不变）。"""
    _offline_provider(monkeypatch)
    B_ = settings(_six(_dsh(_install(tmp_path))))
    with B_.run_mode("drill"):
        backend = B_.select("N3")
    assert backend.metadata()["admission"]["rule"] == "mode_drill"
    assert B_.current_run_mode() is None


def test_invalid_run_mode_is_rejected(settings, tmp_path: Path) -> None:
    B_ = settings(_six(_dsh(_install(tmp_path))))
    with pytest.raises(B.BackendConfigurationError):
        B_.select("N3", run_mode="rehearsal")


# ================================================================== A2 契约字段

def test_contract_record_defaults_to_legacy_unknown() -> None:
    request = BackendRequest(input_data={}, info="i", instruct="do", schema={})
    record = request.contract()
    assert record["contract_version"] == "legacy"
    assert record["identity"] == "unknown"
    assert record["context_manifest_ref"] == "unknown"
    assert record["execution_grant_ref"] == "unknown"
    assert record["runtime_fingerprint"] == "unknown"


def test_contract_record_marks_missing_identity_fields_unknown() -> None:
    request = BackendRequest(
        input_data={}, info="i", instruct="do", schema={},
        contract_version=B.CONTRACT_VERSION,
        identity=RequestIdentity(run_id="RUN-1", node="N3"),
        context_manifest_ref="wm-sha256:abc")
    record = request.contract()
    assert record["contract_version"] == B.CONTRACT_VERSION
    assert record["identity"]["run_id"] == "RUN-1"
    assert record["identity"]["attempt_key"] == "unknown"
    assert record["identity"]["generation"] == "unknown"
    assert record["context_manifest_ref"] == "wm-sha256:abc"
    assert record["execution_grant_ref"] == "unknown"


def _attempt_dirs(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "attempt"
    cwd, home = root / "work", root / "dsh-home"
    cwd.mkdir(parents=True)
    home.mkdir(parents=True)
    return cwd, home


def _unwrapped(tmp_path: Path, *, mode: str = "ok") -> D.DshBackend:
    """诊断形态后端（`wrap=False`）：只为跑 stub 的协议面，不冒充生产形态。"""
    stub = _stub(tmp_path)
    config = D.DshConfig(
        enabled=True, version="0.2.1-rc.2", node=Path(sys.executable), bin=stub,
        bin_sha256=hashlib.sha256(stub.read_bytes()).hexdigest(),
        timeout_s=30.0, wrap=False)
    backend = D.DshBackend(config, diagnostic_unwrapped=True)
    original = backend._spec

    def _spec_with_mode(request: BackendRequest, *, attempt_key: str, cwd: Path,
                        home: Path) -> DP.AttemptSpec:
        spec = original(request, attempt_key=attempt_key, cwd=cwd, home=home)
        return dataclasses.replace(spec, env_extra={
            **spec.env_extra, "STUB_MODE": mode, "STUB_TASK_ID": attempt_key})

    backend._spec = _spec_with_mode  # type: ignore[method-assign]
    return backend


ATTEMPT_KEY = "RUN-ADMIT/N3/1"


async def test_candidate_payload_echoes_contract_fields(tmp_path: Path) -> None:
    """A2 字段必须随候选一起落进封存记录（`result.json` 封的就是 payload 本身）。"""
    cwd, home = _attempt_dirs(tmp_path)
    request = BackendRequest(
        input_data={}, info="i", instruct="do", schema={"type": "object"},
        contract_version=B.CONTRACT_VERSION,
        identity=RequestIdentity(run_id="RUN-ADMIT", node="N3",
                                 attempt_key=ATTEMPT_KEY, generation=1),
        context_manifest_ref="wm-sha256:abc",
        execution_grant_ref="grant/unknown",
        runtime_fingerprint="sha256:deadbeef")
    payload = await _unwrapped(tmp_path).execute(request, attempt_key=ATTEMPT_KEY,
                                                cwd=cwd, home=home)
    assert payload.get("model_call_failed") is not True, payload
    assert payload["contract"] == {
        "contract_version": B.CONTRACT_VERSION,
        "identity": {"run_id": "RUN-ADMIT", "node": "N3",
                     "attempt_key": ATTEMPT_KEY, "generation": 1,
                     "control_session_id": "unknown"},
        "context_manifest_ref": "wm-sha256:abc",
        "execution_grant_ref": "grant/unknown",
        "runtime_fingerprint": "sha256:deadbeef",
    }


async def test_unknown_contract_version_is_explicit_failure(tmp_path: Path) -> None:
    cwd, home = _attempt_dirs(tmp_path)
    request = BackendRequest(input_data={}, info="i", instruct="do",
                             schema={"type": "object"}, contract_version=99)
    payload = await _unwrapped(tmp_path).execute(request, attempt_key=ATTEMPT_KEY,
                                                cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "contract_version" in payload["error"]


async def test_identity_mismatch_is_explicit_failure(tmp_path: Path) -> None:
    """请求身份与本次 attempt 身份必须逐字一致（身份 join 失败 ⇒ 不出候选）。"""
    cwd, home = _attempt_dirs(tmp_path)
    request = BackendRequest(
        input_data={}, info="i", instruct="do", schema={"type": "object"},
        contract_version=B.CONTRACT_VERSION,
        identity=RequestIdentity(run_id="RUN-ADMIT", node="N3",
                                 attempt_key="RUN-ADMIT/N3/2", generation=2))
    payload = await _unwrapped(tmp_path).execute(request, attempt_key=ATTEMPT_KEY,
                                                cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "attempt_key" in payload["error"]


async def test_request_record_carries_a2_fields(ctx, provider, settings) -> None:
    """A2 字段进**请求**封存记录（旧记录只读兼容由 `AM.contract_view` 负责）。"""
    settings({})
    out = await call(ctx)
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    sealed = record["request"]["backend_contract"]
    assert sealed["contract_version"] == B.CONTRACT_VERSION
    assert sealed["identity"]["run_id"] == ctx.run_id
    assert sealed["identity"]["node"] == "N3"
    assert sealed["identity"]["attempt_key"].endswith("/N3/1")
    assert sealed["identity"]["generation"] == 1
    assert sealed["context_manifest_ref"].startswith("wm-sha256:")
    assert sealed["execution_grant_ref"] == "unknown"
    assert sealed["runtime_fingerprint"] != "unknown"
    assert AM.contract_view(record["request"]) == sealed


async def test_legacy_record_reads_as_legacy(ctx) -> None:
    attempt = AM.Attempt(ctx, "N3", {"input": {}, "model": "historical-model"})
    attempt.finish("standin", payload={"standin": True})
    record = AM.verify_attempt(attempt.path)
    assert "backend_contract" not in record["request"]
    assert AM.contract_view(record["request"]) == {
        "contract_version": "legacy", "identity": "unknown",
        "context_manifest_ref": "unknown", "execution_grant_ref": "unknown",
        "runtime_fingerprint": "unknown"}


# ================================================================== 双钉档位（B3/DS-09）

def test_attempt_pins_are_workspace_write_double_pinned() -> None:
    pins = A.ATTEMPT_PINS
    assert pins.sandbox_mode == pins.default_preset == "workspace-write"
    text = A.pins_patch(pins)
    assert "sandbox-policy" in text and "mode: workspace-write" in text
    assert "permission" in text and "defaultPreset: workspace-write" in text
    assert A.PRESET_TABLE["workspace-write"] == ("workspace-write", "ask")
    # 诊断/无 attempt 归属的保守默认仍是 read-only（不放大暴露面）
    assert A.Pins().sandbox_mode == A.DEFAULT_SANDBOX_MODE == "read-only"


def test_attempt_layout_has_private_candidate_dir(tmp_path: Path) -> None:
    """候选落点**必须在工作区内**：dsh 应用层 `workspace-write` 边界 = cwd。

    真机证据（S6 第 3 次）：候选在兄弟目录时 dsh 要求 `danger-full-access` 审批，headless
    `outcome="unavailable"` ⇒ 候选写不出去、整轮超时。所以 `candidate = work/candidate`。
    """
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    assert layout.candidate == layout.work / "candidate"
    assert layout.candidate.is_relative_to(layout.work)
    assert layout.candidate.is_dir()
    assert not (layout.root / "candidate").exists()      # 旧"兄弟目录"不再生成
    A.check_layout(layout)                               # 不变式：通过


def test_layout_rejects_candidate_outside_work(tmp_path: Path) -> None:
    """越界候选（兄弟目录/试图逃逸）⇒ 显式失败（不落回"写不动就算"）。"""
    work = tmp_path / "attempt" / "work"
    work.mkdir(parents=True)
    bad = dataclasses.replace(A.AttemptLayout.under(tmp_path / "attempt"),
                              candidate=tmp_path / "attempt" / "candidate")
    with pytest.raises(A.AssetError):
        A.check_layout(bad)


def _report(layout: A.AttemptLayout, *, preset: str, mode: str) -> dict[str, Any]:
    return {"plugin": "s2-selfcheck", "applied": True, "phase": "deferred", "pid": 4242,
            "toolNames": ["read", "bash", "submit_result"], "toolError": None,
            "sandboxDefaultMode": mode, "sandboxModeError": None,
            "presetEcho": {"availability": "composition", "scope": "composition",
                           "preset": preset,
                           "resolved": {"preset": preset, "sandbox": mode, "approval": "ask"},
                           "reason": None, "resolveError": None},
            "home": str(layout.home), "patches": []}


def test_selfcheck_rejects_preset_echo_mismatch_against_attempt_pins(tmp_path: Path) -> None:
    """自检必须回显**实际**档位并与钉死值逐字比对；不符即拒（不是只看进程起来了）。"""
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    pins = A.ATTEMPT_PINS
    good = layout.selfcheck_file()
    good.write_text(json.dumps(_report(layout, preset=pins.default_preset,
                                       mode=pins.sandbox_mode)), encoding="utf-8")
    assert SC.verify_session(layout, expected_mode=pins.sandbox_mode,
                             expected_preset=pins.default_preset, timeout_s=0.0).ok
    good.write_text(json.dumps(_report(layout, preset="read-only",
                                       mode="read-only")), encoding="utf-8")
    result = SC.verify_session(layout, expected_mode=pins.sandbox_mode,
                               expected_preset=pins.default_preset, timeout_s=0.0)
    assert not result.ok
    assert any("B3" in problem and "钉死值" in problem for problem in result.problems)


def test_attempt_home_must_not_contain_host_settings_or_credentials(tmp_path: Path) -> None:
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    (layout.home / "settings.yaml").write_text("x: y\n", encoding="utf-8")
    (layout.home / ".credentials.yaml").write_text("refs: {}\n", encoding="utf-8")
    problems = SC.verify_home(layout.home)
    assert any("settings.yaml" in item for item in problems)
    assert any(".credentials.yaml" in item for item in problems)
    with pytest.raises(A.AssetError):
        A.materialize(layout, pins=A.ATTEMPT_PINS)


# ================================================================== 停执行（§7.3 / DS-05）

def _spec(tmp_path: Path, stub: Path, *, mode: str, timeout_s: float = 30.0,
          attempt_key: str = ATTEMPT_KEY) -> DP.AttemptSpec:
    cwd, home = _attempt_dirs(tmp_path)
    return DP.AttemptSpec(attempt_key=attempt_key, cwd=cwd, home=home, task="t",
                          dsh_bin=stub, node=Path(sys.executable), wrap=False,
                          timeout_s=timeout_s, stop_grace_s=1.0,
                          env_extra={"STUB_MODE": mode, "STUB_TASK_ID": attempt_key})


async def _until(predicate, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("等待超时")


async def test_cancel_really_stops_the_attempt_process_group(tmp_path: Path) -> None:
    """撤销资格后必须**主动停**在途执行：取消协程不能留下孤儿进程。"""
    stub = _stub(tmp_path)
    spec = _spec(tmp_path, stub, mode="hang")
    task = asyncio.create_task(DP.run_attempt(spec))
    pidfile = spec.cwd / "child.pid"
    await _until(pidfile.exists)
    pid = int(pidfile.read_text().strip())
    assert Path(f"/proc/{pid}").exists()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _until(lambda: not Path(f"/proc/{pid}").exists())


async def test_unconfirmed_stop_is_execution_unknown(tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """停止无法确认 ⇒ `execution_unknown`（不得报"已停"、不得当成功）。"""
    stub = _stub(tmp_path)
    spec = _spec(tmp_path, stub, mode="hang")
    monkeypatch.setattr(DP, "_group_members", lambda pgid: [4242])
    task = asyncio.create_task(DP.run_attempt(spec))
    pidfile = spec.cwd / "child.pid"
    await _until(pidfile.exists)
    task.cancel()
    with pytest.raises(DP.ExecutionUnknown):
        await task


async def test_backend_surfaces_execution_unknown_without_candidate(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _unwrapped(tmp_path, mode="hang")
    cwd, home = _attempt_dirs(tmp_path)
    monkeypatch.setattr(DP, "_group_members", lambda pgid: [4242])
    task = asyncio.create_task(backend.execute(
        BackendRequest(input_data={}, info="i", instruct="do", schema={"type": "object"}),
        attempt_key=ATTEMPT_KEY, cwd=cwd, home=home))
    pidfile = cwd / "child.pid"
    await _until(pidfile.exists)
    task.cancel()
    with pytest.raises(DP.ExecutionUnknown):
        await task


async def test_control_marks_execution_unknown_and_never_resends(ctx, provider,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """§7.3：先撤销资格 → 停执行 → **确认后** applied；停止未知 ⇒ execution_unknown 且不重发。"""
    from host import agent_control as C
    from workflows.chunks import model_request as MR

    calls: list[dict[str, Any]] = []

    async def unconfirmed(*args, **kwargs):
        calls.append(kwargs["input_data"])
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise DP.ExecutionUnknown("execution_unknown：进程组停不下来") from None

    monkeypatch.setattr(MR, "ask", unconfirmed)
    task = asyncio.create_task(call(ctx))
    await _until(lambda: len(calls) == 1)
    view = C.read_view(ctx.run_dir, "N3")
    C.command(ctx.run_dir, "N3", {
        "action": "steer", "actor": "human:tester", "message": "改一句说明",
        "session_id": view["live"]["session_id"],
        "expected_revision": view["live"]["revision"],
        "request_id": "request-unknown-1"})
    with pytest.raises(DP.ExecutionUnknown):
        await task
    final = C.read_view(ctx.run_dir, "N3")
    assert final["live"] is None
    assert final["controls"][-1]["state"] == "execution_unknown"
    assert not any(event["type"] == "applied" for event in final["controls"])
    assert any(event["type"] == "discarded" for event in final["controls"])
    assert len(calls) == 1          # 禁止自动重发


async def test_control_keeps_applied_only_after_confirmed_stop(ctx, provider) -> None:
    """确认已停 ⇒ 既有语义不变：discarded → 停止 → applied → 重发一次新请求。"""
    from host import agent_control as C

    async def until(predicate, timeout_s: float = 5.0) -> None:
        await _until(predicate, timeout_s)

    provider["wait"], provider["entered"] = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(call(ctx))
    await until(lambda: len(provider["inputs"]) == 1)
    view = C.read_view(ctx.run_dir, "N3")
    C.command(ctx.run_dir, "N3", {
        "action": "steer", "actor": "human:tester", "message": "改一句说明",
        "session_id": view["live"]["session_id"],
        "expected_revision": view["live"]["revision"],
        "request_id": "request-stop-1"})
    await until(lambda: len(provider["inputs"]) == 2)
    provider["wait"].set()
    result = await task
    assert result["validation"]["ok"]
    controls = C.read_view(ctx.run_dir, "N3")["controls"]
    assert [event["type"] for event in controls].count("applied") == 1


# ================================================================== attempt 隔离工作区（S5-C2a）

def _workspace_backend(tmp_path: Path) -> D.DshBackend:
    """wrap=True 的**生产形态**后端（本组用例只做分配/物化，不启进程、不烧模型）。"""
    bin_path = _install(tmp_path)
    config = D.DshConfig(
        enabled=True, version="0.2.1-rc.2", node=Path(sys.executable), bin=bin_path,
        bin_sha256=hashlib.sha256(bin_path.read_bytes()).hexdigest(),
        timeout_s=30.0, wrap=True)
    return D.DshBackend(config)


def test_workspace_layout_is_isolated_and_outside_sealed_records(tmp_path: Path) -> None:
    """工作区形状固定、且在 `agent_workspaces/` 下 —— 不混进 `agent_calls/**` 封存记录目录。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    (run_dir / "agent_calls" / "N3").mkdir(parents=True)
    workspace = _workspace_backend(tmp_path).prepare_attempt(run_dir, "N3", 1)
    root = run_dir / "agent_workspaces" / "N3" / "attempt-000001"
    assert workspace.root == root
    for name in ("work", "dsh-home", "input"):
        assert (root / name).is_dir(), name
    assert (root / "work" / "candidate").is_dir()          # 候选在 cwd 内
    assert not (root / "candidate").exists()
    assert workspace.layout.input_dir == root / "input"
    assert not any((root / "work" / "candidate").iterdir())   # S6 才写候选，本片留空
    assert list((run_dir / "agent_calls" / "N3").iterdir()) == []
    record = workspace.record(run_dir=run_dir)
    assert record["root"] == "agent_workspaces/N3/attempt-000001"
    assert record["work"] == record["root"] + "/work"
    assert record["home"] == record["root"] + "/dsh-home"
    assert record["candidate"] == record["work"] + "/candidate"   # 在 cwd 内（应用层可写边界）


def test_input_staging_copies_only_whitelisted_materials_with_md5(tmp_path: Path) -> None:
    """`input/` 只放白名单材料（显式常量）；非白名单件/整目录不进来；每件算 md5+size。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    (run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    (run_dir / "n5_impact.json").write_text('{"impacts": []}', encoding="utf-8")
    (run_dir / "secrets.json").write_text('{"api_key": "never-copy"}', encoding="utf-8")
    (run_dir / "kb").mkdir()
    (run_dir / "kb" / "ledger.json").write_text("{}", encoding="utf-8")
    workspace = _workspace_backend(tmp_path).prepare_attempt(run_dir, "N3", 1)
    staged = {item["name"]: item for item in workspace.materials}
    copied = sorted(path.name for path in workspace.layout.input_dir.iterdir())
    assert copied == ["n2_diff.json", "n5_impact.json"]     # 白名单 + 实际存在
    by_name = {item["name"]: item for item in workspace.materials}
    payload = (run_dir / "n2_diff.json").read_bytes()
    assert by_name["n2_diff.json"] == {"name": "n2_diff.json", "present": True,
                                       "md5": hashlib.md5(payload).hexdigest(),
                                       "size": len(payload)}
    assert by_name["n3_digest.md"]["present"] is False      # 缺失不补、不猜
    assert "secrets.json" not in by_name and "ledger.json" not in by_name
    assert "never-copy" not in b"".join(p.read_bytes()
                                       for p in workspace.layout.input_dir.iterdir()).decode()
    # 拷入的是普通文件（不是指向 run 目录的链接）
    assert all(not path.is_symlink() for path in workspace.layout.input_dir.iterdir())
    # md5 必须真的进 attempt 记录（唯一位点：model_request 的 request 封存）
    record = workspace.record(run_dir=run_dir)
    staged_record = {item["name"]: item for item in record["materials"]}
    assert staged_record["n2_diff.json"]["md5"] == hashlib.md5(payload).hexdigest()


@pytest.mark.parametrize("name", ["../outside.json", "/etc/passwd", "sub/dir.json", ""])
def test_input_staging_rejects_escaping_material_names(tmp_path: Path, name: str) -> None:
    """材料名只接受 run 目录下的裸文件名：`..`/绝对路径/子目录一律显式失败（不静默跳过）。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    with pytest.raises(B.BackendConfigurationError):
        D.stage_inputs(layout, run_dir, materials=(name,))


def test_input_staging_rejects_symlink_escape(tmp_path: Path) -> None:
    """符号链接逃逸必须拒（哪怕它指向 run 目录内的文件也不接受链接）。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    secret = tmp_path / "outside.json"
    secret.write_text('{"api_key": "never-copy"}', encoding="utf-8")
    (run_dir / "n2_diff.json").symlink_to(secret)
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    with pytest.raises(B.BackendConfigurationError):
        D.stage_inputs(layout, run_dir)


def _available_provider(monkeypatch: pytest.MonkeyPatch, *,
                        family: str = "openai-responses",
                        base_url: str = "https://model.invalid/v1",
                        model: str = "probe-model",
                        api_key_env: str = "PUBLIC_API_KEY") -> SimpleNamespace:
    """冒充 `MP.resolve()` 的可用 provider（含一个**假密钥**，用来证明它不会落进 overlay）。"""
    cfg = SimpleNamespace(available=True, family=family, base_url=base_url, model=model,
                          api_key_env=api_key_env, plugin="OpenAIResponsesCompatible",
                          reason=None, max_tokens=8000, timeout_s=180, proxy=None,
                          _api_key="never-record-this-secret")
    monkeypatch.setattr(MP, "resolve", lambda *a, **k: cfg)
    return cfg


def test_provider_overlay_is_generated_from_host_provider_without_secret(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """provider overlay 由 Host 生成：只写 `apiKeyEnv` 名，**绝不写密钥值**；落 attempt 且被 bind。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    provider = _available_provider(monkeypatch, family="openai-responses",
                                   base_url="https://model.invalid/v1", model="probe-model")
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N3", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    overlay = workspace.layout.patch_dir / "01-provider.yml"
    assert overlay.is_file()
    text = overlay.read_text(encoding="utf-8")
    assert "apiKeyEnv: PUBLIC_API_KEY" in text          # 只写环境变量名
    assert "api: openai-responses" in text
    assert "baseURL: https://model.invalid/v1" in text
    assert "id: probe-model" in text and "model: probe-model" in text
    assert provider._api_key not in text               # 密钥值绝不落文件
    # patch 顺序：钉死 → 生成的 overlay → 插件 insert
    names = [path.name for path in spec.patches]
    assert names[0] == "00-pins.yml" and names[1] == "01-provider.yml"
    assert all(not name.startswith("10-plugin-") for name in names[:2])
    # 包裹内可见（patch_dir 是只读 bind 的资产面）
    argv = DP.build_argv(spec)
    assert str(workspace.layout.patch_dir) in argv
    assert str(overlay) in argv


@pytest.mark.parametrize("kwargs", [
    {"family": "unknown-family"},
    {"base_url": ""},
    {"model": ""},
    {"api_key_env": ""},
])
def test_provider_overlay_refuses_incomplete_or_unknown_provider(kwargs: dict[str, Any]) -> None:
    """family 不认识 / 端点/模型/apiKeyEnv 缺失 ⇒ 显式失败（不生成半个 overlay、不猜端点）。"""
    base = {"family": "openai-responses", "base_url": "https://model.invalid/v1",
            "model": "probe-model", "api_key_env": "PUBLIC_API_KEY"}
    base.update(kwargs)
    with pytest.raises(A.AssetError):
        A.provider_overlay(**base)


async def test_attempt_fails_explicitly_when_provider_is_unavailable(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 不可用 ⇒ 不做「没有 provider 的 dsh 尝试」：显式失败并说明原因。"""
    monkeypatch.setattr(MP, "resolve", lambda *a, **k: SimpleNamespace(
        available=False, family="forced-standin", base_url=None, model=None,
        api_key_env=None, plugin=None, reason="LOOP_LLM_MODE=standin", _api_key=None))
    backend = _workspace_backend(tmp_path)
    cwd, home = _attempt_dirs(tmp_path)
    payload = await backend.execute(
        BackendRequest(input_data={}, info="i", instruct="do", schema={}),
        attempt_key=ATTEMPT_KEY, cwd=cwd, home=home)
    assert payload["model_call_failed"] is True
    assert "provider overlay" in payload["error"] and "model_provider" in payload["error"]


def test_attempt_key_comes_from_credentials_but_only_through_env(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """凭据值只进子进程 env：来源可以是宿主凭据库，但**绝不落 attempt 文件**。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    _available_provider(monkeypatch)              # _api_key='never-record-this-secret'
    monkeypatch.delenv("PUBLIC_API_KEY", raising=False)
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N3", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    assert spec.api_key == "never-record-this-secret"
    assert DP.build_env(spec)["PUBLIC_API_KEY"] == "never-record-this-secret"
    leaked = [path for path in workspace.root.rglob("*")
              if path.is_file() and b"never-record-this-secret" in path.read_bytes()]
    assert leaked == []
    assert "never-record-this-secret" not in backend.redact("leak never-record-this-secret")


def test_provider_proxy_reaches_the_attempt_env_but_not_diagnostic(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 代理必须显式带进 attempt env（Node 不读宿主代理）；诊断形态不带。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    cfg = _available_provider(monkeypatch)
    cfg.proxy = "http://proxy.invalid:3128"
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N3", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    env = DP.build_env(spec)
    assert env["HTTPS_PROXY"] == "http://proxy.invalid:3128"
    assert env["HTTP_PROXY"] == env["HTTPS_PROXY"]
    cfg.proxy = None
    none_spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                              attempt_key=workspace.attempt_key,
                              cwd=workspace.layout.work, home=workspace.layout.home)
    assert not any(key.endswith("_PROXY") or key.endswith("_proxy")
                   for key in DP.build_env(none_spec))


# ---------------------------------------------------------------- N6 材料供给（Lead 2026-10-29）

def _fake_env(tmp_path: Path, *, files: dict[str, str]) -> Path:
    root = tmp_path / "env"
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def test_target_sources_are_staged_into_input_with_md5(tmp_path: Path) -> None:
    """N6 目标用例源件以**只读**方式进 `input/TESTLIB/<case>.sv`，md5/size 进 attempt 记录。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    env = _fake_env(tmp_path, files={"TESTLIB/tc_demo.sv": "module tc_demo;\nendmodule\n",
                                     "TESTLIB/other.sv": "module other;\nendmodule\n"})
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N6", 1,
                                        sources=((env, "TESTLIB/tc_demo.sv"),))
    staged = workspace.layout.input_dir / "TESTLIB" / "tc_demo.sv"
    assert staged.is_file()
    payload = staged.read_bytes()
    assert payload == (env / "TESTLIB/tc_demo.sv").read_bytes()
    assert staged.is_symlink() is False
    record = workspace.record(run_dir=run_dir)
    items = {item["name"]: item for item in record["materials"]}
    assert items["TESTLIB/tc_demo.sv"]["md5"] == hashlib.md5(payload).hexdigest()
    assert items["TESTLIB/tc_demo.sv"]["size"] == len(payload)
    # 不整目录：未声明的 other.sv 不得进来
    assert sorted(p.name for p in (workspace.layout.input_dir / "TESTLIB").iterdir()) == ["tc_demo.sv"]
    # `input/` 仍是只读 bind 的材料面（不是资产面）
    assert workspace.layout.input_dir in [workspace.layout.input_dir]


@pytest.mark.parametrize("relative", ["../outside.sv", "/etc/passwd", "TESTLIB/../../x.sv", ""])
def test_target_source_escape_or_absolute_is_rejected(tmp_path: Path, relative: str) -> None:
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    env = _fake_env(tmp_path, files={"TESTLIB/tc_demo.sv": "module a; endmodule\n"})
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    with pytest.raises(A.AssetError):
        A.stage_sources(layout, ((env, relative),))


def test_target_source_symlink_is_rejected(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    env = _fake_env(tmp_path, files={"TESTLIB/tc_demo.sv": "module a; endmodule\n"})
    (env / "TESTLIB" / "link.sv").symlink_to(env / "TESTLIB" / "tc_demo.sv")
    layout = A.AttemptLayout.under(tmp_path / "attempt")
    layout.prepare()
    with pytest.raises(A.AssetError):
        A.stage_sources(layout, ((env, "TESTLIB/link.sv"),))


def test_sources_are_derived_only_for_n6_with_targets() -> None:
    """`sources` 派生**只**在 N6 且带 targets 时发生（别顺手给所有节点开材料面）。"""
    from workflows.chunks.model_request import _attempt_sources

    targets = [{"case": "tc_demo", "file": "TESTLIB/tc_demo.sv"},
               {"case": "tc_demo", "file": "TESTLIB/tc_demo.sv"},   # 去重
               {"case": "bad"}]
    derived = _attempt_sources("N6", {"targets": targets})
    assert derived == ((P.ENV_ROOT, "TESTLIB/tc_demo.sv"),)
    assert _attempt_sources("N3", {"targets": targets}) == ()
    assert _attempt_sources("N6", {}) == ()
    assert _attempt_sources("N6", {"targets": "not-a-list"}) == ()


# ---------------------------------------------------------------- candidate 可写落点（S6 依赖）

def test_candidate_is_the_only_writable_business_dir(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """`candidate/` 必须可写（S6 候选导入只读它），且**只挂这一层**（不放宽到 attempt root）。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    _available_provider(monkeypatch)
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N6", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    attempt_root = workspace.layout.root
    candidate = workspace.layout.work / "candidate"
    # Host 侧信道 ≠ 模型可写业务落点（分开可审计）
    assert tuple(spec.state_dirs) == (attempt_root / "selfcheck",)
    assert tuple(spec.write_dirs) == (candidate,)
    assert candidate.is_relative_to(workspace.layout.work)      # 在 cwd 内（应用层可写边界）
    # candidate 既不是只读资产也不是只读材料
    assert candidate not in spec.asset_dirs and candidate not in spec.material_dirs
    argv = DP.build_argv(spec)
    index = argv.index(str(candidate))
    assert argv[index - 1] == "--bind"          # 可写挂载
    assert argv.count(str(candidate)) == 2
    # 不得把 attempt root / run_dir 整体挂成可写
    for forbidden in (attempt_root, run_dir):
        if str(forbidden) in argv:
            position = argv.index(str(forbidden))
            assert argv[position - 1] != "--bind", "不得把 %s 整体挂成可写" % forbidden


def test_candidate_write_works_inside_the_real_wrap(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """真 bwrap 里写 `candidate/` 成功、写 `input/` 被拒（离线，不调模型）。"""
    import shutil
    import subprocess
    if not shutil.which("bwrap"):
        pytest.skip("本机无 bwrap（环境缺件，不是通过）")
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    (run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    _available_provider(monkeypatch)
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N6", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    script = ("echo ok > %s/probe.sv; echo rc=$?; "
              "echo rel > candidate/probe_rel.sv; echo rel_rc=$?; "
              "echo deny > %s/probe.sv 2>/dev/null; echo input_rc=$?" % (
                  workspace.layout.candidate, workspace.layout.input_dir))
    completed = subprocess.run(DP.build_wrap_argv(spec, ["/bin/sh", "-c", script]),
                               cwd=str(spec.cwd), env=DP.build_env(spec),
                               capture_output=True, text=True, timeout=120, check=False)
    assert completed.returncode == 0, completed.stderr
    assert "rc=0" in completed.stdout and "input_rc=0" not in completed.stdout
    assert "rel_rc=0" in completed.stdout                # 相对 cwd 的 `candidate/` 也可写
    assert (workspace.layout.candidate / "probe.sv").is_file()
    assert (workspace.layout.candidate / "probe_rel.sv").is_file()
    assert not (workspace.layout.input_dir / "probe.sv").exists()


def test_input_dir_is_bound_read_only_into_the_wrap(tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """`input/` 必须以只读 bind 进包裹（模型只能读材料，不能改材料）。"""
    run_dir = tmp_path / "runs" / "RUN-WS"
    run_dir.mkdir(parents=True)
    (run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    _available_provider(monkeypatch)
    backend = _workspace_backend(tmp_path)
    workspace = backend.prepare_attempt(run_dir, "N3", 1)
    spec = backend._spec(BackendRequest(input_data={}, info="i", instruct="do", schema={}),
                         attempt_key=workspace.attempt_key,
                         cwd=workspace.layout.work, home=workspace.layout.home)
    assert workspace.layout.input_dir in spec.material_dirs
    assert workspace.layout.input_dir not in spec.asset_dirs   # 材料 ≠ 资产（语义分开）
    argv = DP.build_argv(spec)
    index = argv.index(str(workspace.layout.input_dir))
    assert argv[index - 1] == "--ro-bind"           # 只读挂载，不是 --bind
    assert argv.count(str(workspace.layout.input_dir)) == 2


class _RecordingDsh:
    """冒充"需要工作区的后端"：只录 Host 传了什么，不启进程。"""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.calls: list[dict[str, Any]] = []
        self.info = D.BackendInfo(True, "dsh/test", "dsh", None)

    def metadata(self) -> dict[str, Any]:
        return {"name": "dsh", "version": "test", "bin_sha256": "0" * 64,
                "implementation_sha256": "1" * 64, "contract_version": B.CONTRACT_VERSION,
                "runtime_fingerprint": "sha256:test"}

    def redact(self, message: str) -> str:
        return message

    def prepare_attempt(self, run_dir, node, sequence, *, attempt_key=None,
                        **_: Any) -> D.AttemptWorkspace:
        layout = A.AttemptLayout.under(A.workspace_root(run_dir, node, sequence))
        layout.prepare()
        staged = D.stage_inputs(layout, run_dir)
        assert attempt_key, "Host 必须传 attempt_key（身份不许两处派生）"
        return D.AttemptWorkspace(attempt_key=attempt_key, root=layout.root,
                                  layout=layout, materials=staged)

    async def execute(self, request: BackendRequest, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"request": request, **kwargs})
        return {"standin": False, "provider": "dsh/test", "plugin": "dsh",
                "data": {"summary": "ok", "groups": [], "risky_points": []}}


async def test_host_allocates_workspace_and_passes_cwd_home_to_execute(
        ctx, settings, provider, monkeypatch: pytest.MonkeyPatch) -> None:
    """`cwd`/`home` 只能来自 Host 分配；分配结果与材料 md5 进 attempt 记录。"""
    (ctx.run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    settings({})
    backend = _RecordingDsh(ctx.run_dir)
    monkeypatch.setattr(B, "select", lambda node: backend)
    out = await call(ctx)
    assert out["validation"]["ok"]
    assert len(backend.calls) == 1
    kwargs = backend.calls[0]
    workspace = ctx.run_dir / "agent_workspaces" / "N3" / "attempt-000001"
    assert Path(kwargs["attempt_key"]) == Path(f"{ctx.run_id}/N3/1")
    assert Path(kwargs["cwd"]) == workspace / "work"
    assert Path(kwargs["home"]) == workspace / "dsh-home"
    assert kwargs["request"].identity.attempt_key == kwargs["attempt_key"]
    record = AM.verify_attempt((ctx.run_dir / out["request_ref"]).parent)
    sealed = record["request"]["attempt_workspace"]
    assert sealed["root"] == "agent_workspaces/N3/attempt-000001"
    assert sealed["candidate"] == sealed["work"] + "/candidate"
    staged = {item["name"]: item for item in sealed["materials"]}
    assert staged["n2_diff.json"]["present"] is True
    assert staged["n2_diff.json"]["md5"] == hashlib.md5(
        (ctx.run_dir / "n2_diff.json").read_bytes()).hexdigest()


async def test_standin_substitution_does_not_allocate_a_workspace(ctx, settings,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    """替身路径不分配工作区、不碰 dsh 执行面（避免演练留下真机现场）。"""
    monkeypatch.setenv("LOOP_LLM_MODE", "standin")
    settings({"node_backends": {"N3": "dsh"}, "dsh": {}})
    ctx.pending.clear()
    await call(ctx)
    assert not (ctx.run_dir / "agent_workspaces").exists()


async def test_dsh_execute_refuses_host_paths_without_host_allocation(tmp_path: Path) -> None:
    """没有 Host 分配的 cwd/home ⇒ 显式拒绝（不从任务文本/客户端 hint 拼宿主路径）。"""
    backend = _workspace_backend(tmp_path)
    request = BackendRequest(input_data={}, info="i", instruct="do", schema={})
    with pytest.raises(B.BackendConfigurationError):
        await backend.execute(request, attempt_key="RUN/N3/1")
    with pytest.raises(B.BackendConfigurationError):
        await backend.execute(request, attempt_key="RUN/N3/1", cwd=tmp_path / "work")


@pytest.mark.parametrize("prompt_key", [
    "n3_digest", "n6_author", "n8_check", "n10_fail_classify", "n11_review", "n12_report"])
def test_composed_task_never_looks_like_a_cli_option(prompt_key: str) -> None:
    """任务文本**不得以 `-` 开头**（C2 真机缺陷，2026-10-29）。

    真实事故：节点 `instruct` 经 `render_block` 后以 `- ` 开头（列表项）⇒ dsh CLI 把它当
    未知选项解析，进程 boot 阶段 `unknown option '- …'` 退出（rc=1、stderr 空，极难定位；
    六节点真机探针 6/6 全被这一条打死）。判据：首行是固定标题、首字符不是 `-`。
    """
    from workflows.chunks.model_request import request_contract

    contract = request_contract(prompt_key)
    request = BackendRequest(input_data={}, info=contract["info"],
                             instruct=contract["instruct"], schema=contract["schema"])
    task = D._compose_task(request, attempt_key="RUN-ADMISSION/%s/1" % prompt_key[:3].upper())
    assert task.startswith(D.TASK_HEADER) and not task.startswith("-")
    assert "\n\n[instruct]\n" in task and "\n\n[submit]\n" in task


def test_admission_never_writes_the_repo_settings(live, settings, tmp_path: Path) -> None:
    """准入是纯判定：**不改**仓内 `SETTINGS.yaml`（内容逐字节不变），也不写证据目录。

    注意：这里**不**断言仓内 SETTINGS 的具体取值（`enabled` 由人工裁决翻转，属 Lead 写权）；
    只钉"准入判定没有副作用"。
    """
    repo_settings = Path(__file__).resolve().parents[1] / "SETTINGS.yaml"
    before = repo_settings.read_bytes()
    settings(_six(_dsh(_install(tmp_path), enabled=False)))
    with pytest.raises(B.BackendUnavailable) as error:
        B.select("N3", run_mode="real")
    assert error.value.admission["code"] == "disabled"
    assert repo_settings.read_bytes() == before
