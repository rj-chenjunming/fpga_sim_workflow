#!/usr/bin/env python3
"""文档路径引用检查（只读，零写入）。

用途：扫 Markdown 里反引号包住的路径，判断它能否按「路径所有权」解析到真实文件，
把断链暴露出来，而不是等读者点开才发现。

路由（与 `doc/spec/ENV_PLUGIN_SPEC.md` §1/§4.2 同口径，**唯一实现**）：
  - TOOL_ROOT       本仓（自锚定：向上找 `kb/tools/kb_lib.py`）：工具/Schema/代码/现行文档
  - WORKSPACE_ROOT  数据根（`environments.json` 的 `workspace`，可被 `$LOOP_WORKSPACE` 覆盖）：kb 数据
  - ENV_ROOT        环境仓（`environments.json` 的 `path`，可被 `$LOOP_ENV_ROOT` 覆盖）：RTL/TB/… 与环境文档

判定分类：
  - `missing`        本仓/数据根路径解析不到 ⇒ 真断链，**退出码 1**；
  - `env_missing`    环境资产解析不到 ⇒ 单独打印（`[ENV-MISSING]`），可见但不计失败
                     （本机未挂载内网 ENV_ROOT 资产属环境缺件）；
  - `known_missing`  `KNOWN_MISSING` 登记的「文档故意引用、本仓确实不存在」缺口 ⇒ 打印原因，不计失败；
  - `historical`     `doc/history/`、`doc/evidence/demo/` 内的历史路径 ⇒ 只计数，不判失败。

其它规则：
  1. `loop/` 前缀**不做**环境回落：旧路径必须暴露为 missing，不能被环境仓同名文件掩盖；
  2. `doc/` 先查 TOOL_ROOT；本仓没有时允许回落到 ENV_ROOT（环境仓自带文档）；
  3. 行号后缀（`:64-67`）、符号后缀（`::func`）、URL/锚点/模板/变量先剥离或跳过；
  4. 运行时目录（loop/state、loop/.logs、loop/.venv）与 `/tmp`、`/home/soft` 跳过；
  5. 判定只看**退出码 + missing**；`checked/skipped` 是诊断值，不写回文档（见 STATUS §19）。

用法：`python3 doc/audit/check_doc_links.py [--verbose]`
退出码：0 = 无本仓/数据根断链；1 = 存在断链；2 = 三根不可确定（不得伪造通过）。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]

#: 环境资产/环境文档：只在 ENV_ROOT 下解析。
ENV_PREFIXES = [
    "RTL/", "TB/", "PKG/", "TESTLIB/", "SIMLIB_RUN/", "uvs.setup", "uvs.setup.orig",
    "doc/AGENTS.md", "doc/_notes/", "doc/_run_artifacts/", "doc/reference/",
    "doc/skills/", "doc/tools/", "doc/templates/", "doc/spec/evidence/",
    "CHECKPOINT-20261015-1123.md",
]
#: 本仓所有物：只在 TOOL_ROOT 下解析（顺序无关，但 `loop/` 明确无环境回落）。
TOOL_PREFIXES = [
    "loop/", "workspaces/", "kb/tools/", "kb/schema/", "kb/README.md",
    "README.md", "AGENTS.md", "environments.json", ".gitignore",
]
#: 数据根所有物：只在 WORKSPACE_ROOT 下解析。
WORKSPACE_PREFIXES = [
    "kb/runs/", "kb/baselines/", "kb/index/", "kb/conflicts/",
    "kb/adjudication/", "kb/FIXTURE_IDENTITY.md",
]
#: 仓内派生数据根/副本（由 `loop/spikes/*.sh` 预置，内含环境文档副本）⇒ 不算本仓文档
SKIP_PREFIXES = ["loop/state", "loop/.logs", "loop/.venv", "loop/.pytest_cache",
                 "loop/.agently", ".env-copy", ".dev-ws", ".wsp", ".tmp-",
                 # S0 真实环境验证的一次性派生副本（`host/s0.py` 的 work_env / rtl_source / 记录根）
                 ".s0-",
                 "/tmp/", "/home/soft/"]
HISTORICAL_FILES = ["doc/evidence/demo/", "doc/history/"]
INLINE = re.compile(r"`([^`\n]{2,200})`")
#: 明确「本仓不存在、但文档故意引用其缺失」的路径 ⇒ 原因（必须是环境/计划/迁移说明，不是遮羞布）。
KNOWN_MISSING: dict[str, str] = {
    "kb/tools/compile_only.sh": "审计发现：real N7 引用的工具不存在（A-A5）",
    "loop/spikes/run_env_checks.sh": "K1 的选项①**未采用**（2026-10-27 选②：`run_env_layer_checks.sh --with-kb-selftests`）；此路径只出现在计划文本里，本仓不会创建 —— 见 doc/plans/2026-10-27-k1-env-checks-entry.md §1、STATUS §94",
    "workspaces/simenv-tcs9620-64ch/": "约定目标位置；当前数据仍在 ENV_ROOT/kb（ENV_PLUGIN_SPEC §7）",
    "loop/ACCEPTANCE_V1.md": "迁移记录中的旧路径；现行文件为 doc/evidence/ACCEPTANCE_V1.md",
}
LINE_SUFFIX = re.compile(r":\d+(-\d+)?(,\d+(-\d+)?)*$")
SYMBOL_SUFFIX = re.compile(r"::.*$")


@dataclass(frozen=True)
class Roots:
    """三个解析根；测试可用临时目录构造。"""

    tool: Path
    env: Path | None = None
    workspace: Path | None = None


@dataclass(frozen=True)
class Finding:
    doc: str
    lineno: int
    token: str
    reason: str = ""


@dataclass
class Report:
    checked: int = 0
    skipped: int = 0
    historical: int = 0
    missing: list[Finding] = field(default_factory=list)
    env_missing: list[Finding] = field(default_factory=list)
    known_missing: list[Finding] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.missing else 0


class RootError(RuntimeError):
    """三根不可确定（注册表坏、缺配置等）：必须显式失败，不得降级成 env_missing。"""


def _load_kb_lib(tool_root: Path):
    """加载三根解析器的**唯一实现** `kb/tools/kb_lib.py`；不写冻结目录字节码。

    口径只有一份（ENV_PLUGIN_SPEC §1）：本检查器**不自己**解析 `environments.json` 或
    环境变量名，避免与 kb_lib 漂移（第二套解析必然漂移：旧布局回落、LOOP_ENV、坏注册表）。
    """
    tools = Path(tool_root) / "kb" / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        import importlib

        module = importlib.import_module("kb_lib")
        loaded = Path(getattr(module, "__file__", "")).resolve()
        if tools.resolve() not in loaded.parents:
            # 防 sys.modules 缓存里他处同名模块冒充本仓解析器（第二套口径）。
            raise RuntimeError(f"kb_lib 归属校验失败：{loaded} 不在 {tools} 下")
        return module
    finally:
        sys.dont_write_bytecode = previous


def default_roots() -> Roots:
    try:
        kb = _load_kb_lib(TOOL_ROOT)
        return Roots(tool=Path(kb.TOOL_ROOT), env=Path(kb.ENV_ROOT),
                     workspace=Path(kb.WORKSPACE_ROOT))
    except Exception as exc:  # noqa: BLE001 - 根不可确定必须整体失败
        raise RootError(f"三根不可确定（复用 kb_lib 失败）：{type(exc).__name__}: {exc}") from exc


def normalize(token: str) -> str | None:
    """把反引号内容归一成路径候选；非路径/模板/URL 返回 None。"""
    token = token.strip().strip('"\'(),.;:')
    if not token or " " in token:
        return None
    if any(ch in token for ch in "<>*$|{}[]"):
        return None
    if token.startswith(("http://", "https://", "#", "/", "-", "~")):
        return None
    if "…" in token or "..." in token:
        return None
    return SYMBOL_SUFFIX.sub("", LINE_SUFFIX.sub("", token.rstrip(".")))


def _matches(clean: str, prefixes: list[str]) -> bool:
    """前缀匹配：目录引用可带/不带尾斜杠（`kb/tools` 与 `kb/tools/` 同等对待）。"""
    for prefix in prefixes:
        if clean == prefix.rstrip("/") or clean.startswith(prefix):
            return True
    return False


def classify(token: str) -> str | None:
    """按路径所有权分类：tool / workspace / env / doc / None（非路径或不判定）。

    顺序即优先级：数据根前缀 → 本仓前缀 → 环境资产/环境文档 → doc 回落 → 其它 kb 数据。
    """
    clean = normalize(token)
    if not clean:
        return None
    if clean.startswith(tuple(SKIP_PREFIXES)):
        return None
    if _matches(clean, WORKSPACE_PREFIXES):
        return "workspace"
    if _matches(clean, TOOL_PREFIXES):
        return "tool"
    if _matches(clean, ENV_PREFIXES):
        return "env"
    if clean.startswith("doc/"):
        # 本仓文档优先；本仓没有时允许回落到 ENV_ROOT（环境仓自带文档）。
        return "doc"
    if clean.startswith("kb/"):
        # 其余 kb 子路径视为数据根所有物（数据根只放 kb 数据）。
        return "workspace"
    return None


def resolve(token: str, roots: Roots) -> tuple[Path | None, str]:
    """返回 (路径或 None, 解析根标签)。"""
    clean = normalize(token)
    if not clean:
        return None, "skip"
    kind = classify(clean)
    if kind == "tool":
        path = roots.tool / clean
        return (path, "tool") if path.exists() else (None, "tool?")
    if kind == "workspace":
        if roots.workspace is None:
            return None, "workspace?"
        # 数据根本身就是 kb 目录（ENV_PLUGIN_SPEC §1：WORKSPACE_ROOT = <ENV_ROOT>/kb），
        # 所以 `kb/xxx` 映射为 `<WORKSPACE_ROOT>/xxx`。
        rel = clean[len("kb/"):] if clean.startswith("kb/") else clean
        path = roots.workspace / rel
        if path.exists():
            return path, "workspace"
        # 兼容旧布局：TOOL_ROOT 自身就是数据根时的回落在 §1 已声明；这里只查 WORKSPACE_ROOT。
        return None, "workspace?"
    if kind == "env":
        if roots.env is None:
            return None, "env?"
        path = roots.env / clean
        return (path, "env") if path.exists() else (None, "env?")
    if kind == "doc":
        local = roots.tool / clean
        if local.exists():
            return local, "tool"
        if roots.env is not None and (roots.env / clean).exists():
            return roots.env / clean, "env-fallback"
        return None, "tool?"
    return None, "skip"


def scan(roots: Roots, docs_root: Path | None = None) -> Report:
    """扫 `docs_root`（默认 TOOL_ROOT）下的 Markdown，返回分类结果。"""
    base = Path(docs_root) if docs_root else roots.tool
    report = Report()
    for md in sorted(base.rglob("*.md")):
        rel = md.relative_to(base).as_posix()
        # 派生数据根/环境副本（`loop/spikes/*.sh` 预置）内含环境文档副本，不是本仓文档。
        if rel.startswith((".git/", "loop/.venv/", "workspaces/",
                           ".env-copy/", ".dev-ws", ".wsp", ".tmp-", ".s0-")):
            continue
        is_historical = any(rel.startswith(p) for p in HISTORICAL_FILES)
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for match in INLINE.finditer(line):
                raw = match.group(1)
                token = normalize(raw)
                if not token or classify(token) is None:
                    report.skipped += 1
                    continue
                if is_historical:
                    report.historical += 1
                    continue
                report.checked += 1
                reason = next((why for key, why in KNOWN_MISSING.items()
                               if token == key or token.startswith(key)), None)
                if reason is not None:
                    report.known_missing.append(Finding(rel, lineno, token, reason))
                    continue
                found, where = resolve(token, roots)
                if found is not None:
                    continue
                if where.startswith("env"):
                    report.env_missing.append(Finding(rel, lineno, token))
                else:
                    report.missing.append(Finding(rel, lineno, token))
    return report


def main() -> int:
    verbose = "--verbose" in sys.argv
    try:
        roots = default_roots()
    except RootError as exc:
        print(f"[ROOT-ERROR] {exc}", file=sys.stderr)
        return 2
    report = scan(roots)

    print(f"TOOL_ROOT = {roots.tool}")
    print(f"ENV_ROOT  = {roots.env}")
    print(f"WORKSPACE = {roots.workspace}")
    print(f"checked={report.checked} skipped={report.skipped} historical={report.historical} "
          f"known_missing={len(report.known_missing)} env_missing={len(report.env_missing)} "
          f"missing={len(report.missing)}")
    for finding in report.known_missing:
        print(f"[KNOWN-MISSING] {finding.doc}:{finding.lineno}  {finding.token}  ({finding.reason})")
    for finding in report.env_missing:
        print(f"[ENV-MISSING] {finding.doc}:{finding.lineno}  {finding.token}")
        if verbose:
            print("          base tried: ENV_ROOT（环境资产，本机可能未挂载）")
    for finding in report.missing:
        print(f"[MISSING] {finding.doc}:{finding.lineno}  {finding.token}")
        if verbose:
            print("          base tried: TOOL_ROOT / WORKSPACE_ROOT")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
