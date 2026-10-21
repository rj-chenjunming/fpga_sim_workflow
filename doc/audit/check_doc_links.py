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
退出码：0 = 无本仓/数据根断链；1 = 存在断链。
"""
from __future__ import annotations

import json
import os
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
SKIP_PREFIXES = ["loop/state", "loop/.logs", "loop/.venv", "loop/.pytest_cache",
                 "loop/.agently", "/tmp/", "/home/soft/"]
HISTORICAL_FILES = ["doc/evidence/demo/", "doc/history/"]
INLINE = re.compile(r"`([^`\n]{2,200})`")
#: 明确「本仓不存在、但文档故意引用其缺失」的路径 ⇒ 原因（必须是环境/计划/迁移说明，不是遮羞布）。
KNOWN_MISSING: dict[str, str] = {
    "kb/tools/compile_only.sh": "审计发现：real N7 引用的工具不存在（A-A5）",
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


def _env_roots() -> tuple[Path | None, Path | None]:
    env_root = os.environ.get("LOOP_ENV_ROOT")
    workspace = os.environ.get("LOOP_WORKSPACE")
    try:
        reg = json.loads((TOOL_ROOT / "environments.json").read_text(encoding="utf-8"))
        env_id = reg.get("default")
        entry = (reg.get("environments") or {}).get(env_id or "", {})
        env_root = env_root or entry.get("path")
        workspace = workspace or entry.get("workspace")
    except Exception:
        pass
    return (Path(env_root) if env_root else None), (Path(workspace) if workspace else None)


def default_roots() -> Roots:
    env_root, workspace = _env_roots()
    return Roots(tool=TOOL_ROOT, env=env_root, workspace=workspace)


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


def classify(token: str) -> str | None:
    """按路径所有权分类：tool / workspace / env / doc / None（非路径或不判定）。

    顺序即优先级：数据根前缀 → 本仓前缀 → 环境资产/环境文档 → doc 回落 → 其它 kb 数据。
    """
    clean = normalize(token)
    if not clean:
        return None
    if clean.startswith(tuple(SKIP_PREFIXES)):
        return None
    if clean.startswith(tuple(WORKSPACE_PREFIXES)):
        return "workspace"
    if clean.startswith(tuple(TOOL_PREFIXES)):
        return "tool"
    if clean.startswith(tuple(ENV_PREFIXES)):
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
        if rel.startswith((".git/", "loop/.venv/", "workspaces/")):
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
    roots = default_roots()
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
