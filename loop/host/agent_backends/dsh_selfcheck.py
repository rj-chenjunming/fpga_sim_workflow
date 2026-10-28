"""S2 启动自检（SPEC-REV-14 B2/B3、DS-08/DS-09/DS-10；计划 §3.2）。

为什么需要它：dsh 的插件/工具加载失败**只出** `dsh: warning: 1 entry did not activate`，
不阻断启动（P2 实测）⇒ "进程起来了"不能当准入。本模块把三类事实变成**可判定**的准入条件：

- **B2（DS-08）**：`selfcheck.json` 的 `toolNames` 里必须有 `submit_result`；
- **B3（DS-09）**：`sandboxPolicy.defaultMode` 与 `permission-presets` 回显都要等于钉死值
  （单钉会被覆盖：P3 实测只钉 `mode` 时 `defaultPreset: danger-full-access` 仍然越界写 `rc=0`）；
- **DS-09**：attempt home 不得含宿主 `settings.yaml`/凭据（判据复用 `dsh_assets.home_problems`）；
- **DS-10**：用**同一套**隔离参数（`dsh_process.build_wrap_argv`）跑一个不调模型的探针，
  证明宿主 home 不可读、白名单外的 env 不继承。

边界（不声称）：
- **不检查** `/proc/<pid>/environ`：同 uid 下它仍可读出 key（P0 实测 `LEAK:/proc/6/environ`），
  这是 D1 的残余风险，不在本模块的判据里；
- 不判业务、不注工具、不改策略：只读运行时事实并显式失败。
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import dsh_assets as A
from . import dsh_process as DP

#: 自检报告文件名（必须与 `dsh_plugin/selfcheck.mjs` 一致）
REPORT_FILE = "selfcheck.json"
#: 插件 id（与 patch insert 的 entry id 一致）
PLUGIN_NAME = "s2-selfcheck"
#: B2：缺了它就没有结构化候选通道
REQUIRED_TOOL = "submit_result"
#: 可接受的回显作用域；其它值（含 `unknown`）一律判失败
PRESET_ECHO_AVAILABILITY = ("composition", "session")

_VISIBILITY_SCRIPT = """i=1
for p in "$@"; do
  if [ -e "$p" ]; then echo "PATH_$i=yes"; else echo "PATH_$i=no"; fi
  i=$((i+1))
done
"""
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
#: 准入快照的阶段标记（`apply` 快照是诊断用：那时工具/服务可能还没就绪，实测 toolNames=[]）
READY_PHASE = "deferred"
_REQUIRED_ENV = ("PATH", "HOME", "DSH_HOME", "DSH_PROFILE")
#: 探针里只回显这几个非敏感值（凭据值绝不落库）
_ECHO_VALUES = ("HOME", "DSH_HOME", "DSH_PROFILE", "PWD")


class SelfCheckFailed(RuntimeError):
    """自检不通过（调用方必须显式失败，**不得**以"进程起来了"当准入）。"""


# ------------------------------------------------------------------ DS-09

def verify_home(home: Path | str) -> list[str]:
    """DS-09：attempt home 不得含宿主 settings/凭据。

    判据**复用** `dsh_assets.home_problems`（红线 8：口径唯一，不写第二套）。
    """
    return A.home_problems(Path(home))


# ------------------------------------------------------------------ B2/B3/DS-09：会话事实

@dataclass(frozen=True)
class SelfCheckResult:
    """一次会话自检的结论：`ok` 只由 `problems` 决定（没有 problems 才算通过）。"""

    path: Path
    facts: dict[str, Any]
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems

    def require_ok(self) -> "SelfCheckResult":
        """不通过就抛 `SelfCheckFailed`（宿主准入用）。"""
        if self.problems:
            raise SelfCheckFailed("启动自检未通过（%s）：%s" % (self.path, "；".join(self.problems)))
        return self


def _read_report(path: Path, timeout_s: float) -> tuple[dict[str, Any] | None, str | None]:
    """在 `timeout_s` 预算内读**准入快照**（`phase == 'deferred'`）。

    插件先写一份 `apply` 期快照（那时服务/工具可能还没就绪：实测 `toolNames=[]`），
    再写 deferred 快照。只认后者；只有前者的情形在超时后**显式失败**，不拿诊断快照当准入。
    """
    deadline = time.monotonic() + max(0.0, timeout_s)
    detail: str | None = None
    while True:
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as exc:
                detail = "自检报告读取失败（%s）：%s" % (path, exc)
            except json.JSONDecodeError as exc:
                detail = "自检报告是坏 JSON（%s）：%s" % (path, exc)
            else:
                if isinstance(payload, dict) and payload.get("phase") == READY_PHASE:
                    return payload, None
                if isinstance(payload, dict):
                    detail = ("自检报告还是 %r 阶段快照（apply 期工具/服务可能尚未就绪）："
                              "未等到 %r 快照" % (payload.get("phase"), READY_PHASE))
                else:
                    detail = "自检报告不是 JSON 对象（%s）：%r" % (
                        type(payload).__name__, str(payload)[:120])
        else:
            detail = "缺自检报告（%s 不存在；插件未激活或未落盘）" % path
        if time.monotonic() >= deadline:
            return None, detail
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _preset_problems(echo: Any, expected_preset: str, expected_mode: str) -> list[str]:
    """B3 的另一半：preset 回显必须等于钉死值，且档位包解析得出来、与沙箱默认档一致。"""
    if not isinstance(echo, dict):
        return ["B3：拿不到 preset 回显（presetEcho=%r）：拿不到回显 ⇒ 不得以"
                "'进程起来了'当准入（计划 §6-1）" % (echo,)]
    availability = echo.get("availability")
    if availability not in PRESET_ECHO_AVAILABILITY:
        return ["B3：preset 回显 unavailable（availability=%r，reason=%r）："
                "拿不到回显 ⇒ 不得以'进程起来了'当准入（计划 §6-1；session 级 preset 需在"
                "拿到 session 后重测）" % (availability, echo.get("reason"))]

    problems: list[str] = []
    preset = echo.get("preset")
    if preset != expected_preset:
        problems.append(
            "B3：preset 回显 %r ≠ 钉死值 %r（`sandbox-policy.mode` 与 "
            "`permission-presets.defaultPreset` 必须双钉并回显）" % (preset, expected_preset))
    resolved = echo.get("resolved")
    if not isinstance(resolved, dict):
        problems.append(
            "B3：preset 档位包未回显（resolve(%r) 失败：%s）——preset 名不在配置表里，"
            "双钉不成立（patch 的 config 是整块替换，必须带完整 presets 表）"
            % (preset, echo.get("resolveError")))
    elif resolved.get("sandbox") != expected_mode:
        problems.append(
            "B3：preset %r 的档位包沙箱=%r，与沙箱默认档 %r 不一致（双钉自相矛盾）"
            % (preset, resolved.get("sandbox"), expected_mode))
    return problems


async def _read_report_async(path: Path,
                            timeout_s: float) -> tuple[dict[str, Any] | None, str | None]:
    """`_read_report` 的 async 版（`asyncio.sleep` 轮询）：钩子在事件循环里跑时**不阻塞收帧**。"""
    deadline = time.monotonic() + max(0.0, timeout_s)
    detail: str | None = None
    while True:
        payload, error = _read_report(path, 0.0)
        if error is None:
            return payload, None
        detail = error
        if time.monotonic() >= deadline:
            return None, detail
        await asyncio.sleep(min(0.05, max(0.0, deadline - time.monotonic())))


def _evaluate(layout: Any, path: Path, facts: dict[str, Any], *,
              expected_mode: str, expected_preset: str,
              expected_nonce: str | None = None,
              expected_attempt_key: str | None = None) -> SelfCheckResult:
    """把准入快照判成结论（B2/B3/DS-09 的唯一判据实现；sync/async 入口共用）。

    `expected_nonce`/`expected_attempt_key` 给定时必须与报告逐字一致：没有这层身份 join，
    复用同一 attempt root 时会把**上一次**的 deferred 快照当成本次准入（独立复核 P1-1 复现）。
    """
    problems: list[str] = []
    if expected_nonce is not None and facts.get("nonce") != expected_nonce:
        problems.append("DS-08：自检报告 nonce=%r ≠ 本次 attempt 的 nonce（旧快照/跨 attempt "
                        "复用，不得当准入）" % (facts.get("nonce"),))
    if (expected_attempt_key is not None
            and facts.get("attemptKey") != expected_attempt_key):
        problems.append("DS-08：自检报告 attemptKey=%r ≠ 本次 %r（身份 join 失败）"
                        % (facts.get("attemptKey"), expected_attempt_key))
    if facts.get("plugin") != PLUGIN_NAME:
        problems.append("自检报告 plugin=%r ≠ %r（不是本片的自检插件）"
                        % (facts.get("plugin"), PLUGIN_NAME))
    if facts.get("applied") is not True:
        problems.append("自检插件未完成 apply（applied=%r，error=%r）：激活失败不阻断 dsh 启动，"
                        "但绝不能当准入" % (facts.get("applied"), facts.get("error")))

    # B2：工具清单（插件加载失败只出 warning ⇒ 必须看注册表可见面）
    tool_names = facts.get("toolNames")
    if not isinstance(tool_names, list) or not tool_names:
        problems.append("B2：拿不到工具清单（toolNames=%r，toolError=%r）——"
                        "不能以'进程起来了'当准入" % (tool_names, facts.get("toolError")))
    elif REQUIRED_TOOL not in tool_names:
        problems.append("B2：工具清单缺 %s（插件/工具没激活；dsh 只出 `warning: … did not "
                        "activate` 不阻断启动）；可见 %d 个：%s"
                        % (REQUIRED_TOOL, len(tool_names), sorted(map(str, tool_names))[:12]))

    # B3：沙箱默认档（双钉的一半）
    mode = facts.get("sandboxDefaultMode")
    if mode != expected_mode:
        problems.append("B3：sandboxPolicy.defaultMode=%r ≠ 钉死值 %r（只钉 preset 或只钉 mode "
                        "都会被覆盖；error=%r）" % (mode, expected_mode,
                                                    facts.get("sandboxModeError")))

    # B3：permission preset 回显（双钉的另一半）
    problems += _preset_problems(facts.get("presetEcho"), expected_preset, expected_mode)

    # DS-09：home 证据 + 最小 home
    home = facts.get("home")
    expected_home = Path(layout.home)
    if not isinstance(home, str) or not home:
        problems.append("DS-09：自检没回显 home（无法证明 attempt 用的是最小 home）")
    elif Path(home).resolve() != expected_home.resolve():
        problems.append("DS-09：自检回显 home=%r ≠ 本次 attempt home=%r（隔离证据不成立）"
                        % (home, str(expected_home)))
    problems += ["DS-09：%s" % problem for problem in verify_home(expected_home)]

    return SelfCheckResult(path=path, facts=facts, problems=tuple(problems))


def verify_session(layout: Any, *, expected_mode: str = A.DEFAULT_SANDBOX_MODE,
                   expected_preset: str = A.DEFAULT_PRESET,
                   timeout_s: float = 5.0,
                   expected_nonce: str | None = None,
                   expected_attempt_key: str | None = None) -> SelfCheckResult:
    """B2/B3/DS-09：把 `selfcheck.json` 的运行时事实判成准入结论。

    参数期望值默认取 `dsh_assets` 的钉死值（不抄字面量）。缺报告/坏 JSON/超时/任一不一致
    都进 `problems`（**显式失败**）；`timeout_s` 是等待插件落盘的预算（0 = 只读一次）。

    **async 调用方请用 `averify_session`**：本函数用同步 sleep 轮询，直接在事件循环里调用会
    卡住收帧任务（dsh 的 stdout 读不动）。
    """
    path = Path(layout.selfcheck_file())
    facts, error = _read_report(path, timeout_s)
    if error is not None:
        return SelfCheckResult(path=path, facts={}, problems=(error,))
    return _evaluate(layout, path, facts, expected_mode=expected_mode,
                     expected_preset=expected_preset,
                     expected_nonce=expected_nonce,
                     expected_attempt_key=expected_attempt_key)


async def averify_session(layout: Any, *, expected_mode: str = A.DEFAULT_SANDBOX_MODE,
                          expected_preset: str = A.DEFAULT_PRESET,
                          timeout_s: float = 5.0,
                          expected_nonce: str | None = None,
                          expected_attempt_key: str | None = None) -> SelfCheckResult:
    """`verify_session` 的 async 版：给 `dsh_process.run_attempt(on_start=...)` 用（不阻塞收帧）。"""
    path = Path(layout.selfcheck_file())
    facts, error = await _read_report_async(path, timeout_s)
    if error is not None:
        return SelfCheckResult(path=path, facts={}, problems=(error,))
    return _evaluate(layout, path, facts, expected_mode=expected_mode,
                     expected_preset=expected_preset,
                     expected_nonce=expected_nonce,
                     expected_attempt_key=expected_attempt_key)


# ------------------------------------------------------------------ DS-10：包裹自证

@dataclass(frozen=True)
class WrapAttestation:
    """DS-10 的实测结论 + 可复核的 argv（`ok` 只由 `problems` 决定）。

    `argv` 是**可见性**探针（`/bin/sh -c` 逐路径 `test -e`），`env_argv` 是**环境**探针
    （直接 `/usr/bin/env`，不经 shell —— 否则 shell 自己会加 `PWD`/`SHLVL`/`_`，
    就分不清"继承"和"shell 自带"）。两次调用用**同一套**包裹参数。
    """

    argv: tuple[str, ...]
    env_argv: tuple[str, ...]
    host_home: str
    probe_file: str
    probe_visible: bool | None
    env_keys: tuple[str, ...]
    home_echo: str | None
    dsh_home_echo: str | None
    asset_paths: tuple[str, ...]
    returncode: int | None
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems

    def require_ok(self) -> "WrapAttestation":
        if self.problems:
            raise SelfCheckFailed("bwrap 包裹自证未通过（DS-10）：%s" % "；".join(self.problems))
        return self


def _parse_visibility(stdout: str) -> dict[str, str]:
    """`PATH_<n>=yes|no` 标记行。"""
    markers: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.startswith("PATH_"):
            markers[key] = value
    return markers


def _parse_env(stdout: str) -> dict[str, str]:
    """包裹内 env 的键 + 少量非敏感值；凭据类值一律不保留。"""
    facts: dict[str, str] = {}
    for line in stdout.splitlines():
        if not _ENV_KEY.match(line):
            continue
        key, _, value = line.partition("=")
        facts[key] = value if key in _ECHO_VALUES else ""
    return facts


def attest_wrap(spec: DP.AttemptSpec, *, probe_file: Path | str | None = None,
                host_home: Path | str | None = None,
                timeout_s: float = 60.0) -> WrapAttestation:
    """DS-10：用**同一隔离参数**跑一个不调模型的探针，实测包裹生效。

    断言（判据，不是描述）：
    1. 宿主 home 下的探针文件在包裹内**不存在**（`--tmpfs <宿主 home>` 生效）；
    2. 包裹内 env 键 ⊆ `dsh_process.build_env` 的白名单（父进程 env 不被继承）；
    3. 包裹内 `HOME`/`DSH_HOME` 指向本次 attempt home（dsh 在包裹里用的是最小 home）；
    4. 传进来的 patch/资产目录在包裹内**可见**（否则 dsh 只会 `failed to read overlay` / 插件
       `did not activate` —— 实测过这个坑）。

    **不检查** `/proc/<pid>/environ`：同 uid 下它仍可读出 dsh 进程 env 里的 key
    （P0 实测 `LEAK:/proc/6/environ`）。这是 D1 的**残余风险**，本函数不声称挡住它。

    `probe_file` 必须位于宿主 home 之下（否则遮蔽断言没有意义）；不传则自己在宿主 home
    下造一个并在结束时删除（宿主 home 只读时**显式失败**，不静默跳过）。
    """
    argv = tuple(DP.build_argv(spec))
    host_home_path = Path(host_home) if host_home is not None else Path.home()
    host_home_resolved = host_home_path.resolve()

    if not spec.wrap:
        return WrapAttestation(
            argv=argv, env_argv=(), host_home=str(host_home_resolved), probe_file="",
            probe_visible=None, env_keys=(), home_echo=None, dsh_home_echo=None,
            asset_paths=(), returncode=None,
            problems=("spec.wrap=False：没有包裹就没有隔离可自证（DS-10 不成立）",))
    if not Path(spec.cwd).is_dir():
        return WrapAttestation(
            argv=argv, env_argv=(), host_home=str(host_home_resolved), probe_file="",
            probe_visible=None, env_keys=(), home_echo=None, dsh_home_echo=None,
            asset_paths=(), returncode=None,
            problems=("attempt cwd 不存在：%s（探针无处起）" % spec.cwd,))

    probe = Path(probe_file) if probe_file is not None else None
    created = False
    if probe is None:
        probe = host_home_path / (".dsh-selfcheck-probe-%s" % uuid.uuid4().hex[:12])
        try:
            probe.write_text("sentinel\n", encoding="utf-8")
        except OSError as exc:
            return WrapAttestation(
                argv=argv, env_argv=(), host_home=str(host_home_resolved), probe_file=str(probe),
                probe_visible=None, env_keys=(), home_echo=None, dsh_home_echo=None,
                asset_paths=(), returncode=None,
                problems=("无法在宿主 home 放置探针（%s）：DS-10 无法自证（宿主 home 只读 ⇒ "
                          "显式失败，不跳过）" % exc,))
        created = True
    elif not probe.is_file():
        return WrapAttestation(
            argv=argv, env_argv=(), host_home=str(host_home_resolved), probe_file=str(probe),
            probe_visible=None, env_keys=(), home_echo=None, dsh_home_echo=None,
            asset_paths=(), returncode=None,
            problems=("探针文件不存在：%s（用例必须先造出来）" % probe,))

    asset_paths = tuple(str(p) for p in spec.patches) + tuple(str(d) for d in spec.asset_dirs)
    env = DP.build_env(spec)
    # 两次探针、同一套包裹参数：① 路径可见性（需要 shell 的 test）② env 白名单（不经 shell，
    # 否则 shell 自己会加 PWD/SHLVL/_，就分不清"父进程继承"和"shell 自带"）
    argv = tuple(DP.build_wrap_argv(
        spec, ["/bin/sh", "-c", _VISIBILITY_SCRIPT, "dsh-selfcheck-probe",
               str(probe), *asset_paths]))
    env_argv = tuple(DP.build_wrap_argv(spec, ["/usr/bin/env"]))
    try:
        if host_home_resolved not in probe.resolve().parents:
            return WrapAttestation(
                argv=argv, env_argv=env_argv, host_home=str(host_home_resolved),
                probe_file=str(probe), probe_visible=None, env_keys=(), home_echo=None,
                dsh_home_echo=None, asset_paths=asset_paths, returncode=None,
                problems=("探针 %s 不在宿主 home %s 之下：遮蔽断言没有意义（防止自证空转）"
                          % (probe, host_home_resolved),))
        try:
            visible_run = subprocess.run(argv, cwd=str(spec.cwd), env=env,
                                         capture_output=True, text=True,
                                         timeout=timeout_s, check=False)
            env_run = subprocess.run(env_argv, cwd=str(spec.cwd), env=env,
                                     capture_output=True, text=True,
                                     timeout=timeout_s, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return WrapAttestation(
                argv=argv, env_argv=env_argv, host_home=str(host_home_resolved),
                probe_file=str(probe), probe_visible=None, env_keys=(), home_echo=None,
                dsh_home_echo=None, asset_paths=asset_paths, returncode=None,
                problems=("包裹探针无法执行（%s）：bwrap 不可用或参数不成立" % exc,))

        markers = _parse_visibility(visible_run.stdout)
        env_facts = _parse_env(env_run.stdout)
        env_keys = tuple(env_facts)
        problems: list[str] = []
        for label, run in (("可见性", visible_run), ("env", env_run)):
            if run.returncode != 0:
                tail = (run.stderr or "").strip().splitlines()[-3:]
                problems.append("包裹探针（%s）退出码 %s：%s"
                                % (label, run.returncode, " | ".join(tail)))

        probe_visible = markers.get("PATH_1") == "yes"
        if probe_visible:
            problems.append("宿主 home 探针 %s 在包裹内**可见**：`--tmpfs <宿主 home>` 没生效"
                            "（DS-10 不成立）" % probe)
        for index, path in enumerate(asset_paths, start=2):
            if markers.get("PATH_%d" % index) != "yes":
                problems.append("包裹内看不到 attempt 资产 %s：dsh 读不到自己的 patch/插件"
                                "（实测表现是 `failed to read overlay` 或插件 `did not activate`）"
                                % path)

        home_echo = env_facts.get("HOME") or None
        dsh_home_echo = env_facts.get("DSH_HOME") or None
        if home_echo != str(spec.home):
            problems.append("包裹内 HOME=%r ≠ attempt home %r（最小 home 没生效）"
                            % (home_echo, str(spec.home)))
        if dsh_home_echo != str(spec.home):
            problems.append("包裹内 DSH_HOME=%r ≠ attempt home %r（dsh 会落到别的 home）"
                            % (dsh_home_echo, str(spec.home)))

        # `PWD` 由 bwrap 自己设成子进程 cwd（实测：`--new-session` 下 env 里多出 PWD=/cwd），
        # 不是父进程继承；单独核对它指向本次 attempt cwd。
        unexpected = sorted(set(env_keys) - set(env) - {"PWD"})
        if unexpected:
            problems.append("包裹内出现白名单外的环境变量：%s（父进程 env 被继承 ⇒ DS-10 不成立）"
                            % unexpected[:10])
        pwd_echo = env_facts.get("PWD")
        if pwd_echo and Path(pwd_echo).resolve() != Path(spec.cwd).resolve():
            problems.append("包裹内 PWD=%r ≠ attempt cwd %r（工作副本没对上）"
                            % (pwd_echo, str(spec.cwd)))
        missing = sorted(set(_REQUIRED_ENV) - set(env_keys))
        if missing:
            problems.append("包裹内缺必需环境变量：%s（dsh 起不来）" % missing)

        return WrapAttestation(
            argv=argv, env_argv=env_argv, host_home=str(host_home_resolved),
            probe_file=str(probe), probe_visible=probe_visible, env_keys=env_keys,
            home_echo=home_echo, dsh_home_echo=dsh_home_echo, asset_paths=asset_paths,
            returncode=env_run.returncode, problems=tuple(problems))
    finally:
        if created:
            try:
                probe.unlink()
            except OSError:
                pass


__all__ = [
    "PLUGIN_NAME", "PRESET_ECHO_AVAILABILITY", "REPORT_FILE", "REQUIRED_TOOL",
    "SelfCheckFailed", "SelfCheckResult", "WrapAttestation",
    "attest_wrap", "averify_session", "verify_home", "verify_session",
]
