#!/usr/bin/env python3
"""文档路径引用检查（只读，零写入）。

用途：扫 Markdown 里反引号包住的路径，判断它能否按「三个根」解析到真实文件，
把断链在整理后就地暴露出来，而不是等读者点开才发现。

三个根（与 `doc/spec/ENV_PLUGIN_SPEC.md` §1 同口径）：
  - TOOL_ROOT      本仓（自锚定：向上找 `kb/tools/kb_lib.py`）
  - ENV_ROOT       环境仓（`environments.json` 的 `path`，可被 `$LOOP_ENV_ROOT` 覆盖）
  - WORKSPACE_ROOT 数据根（`environments.json` 的 `workspace`，可被 `$LOOP_WORKSPACE` 覆盖）

判定规则：
  1. 以环境资产前缀开头的路径（RTL/、TB/、doc/AGENTS.md、kb/runs/ …）→ 到 ENV_ROOT/WORKSPACE_ROOT 下找；
  2. 其余仓库相对路径（loop/、kb/、doc/、workspaces/、README.md …）→ 先到 TOOL_ROOT 找，
     找不到再回落到 ENV_ROOT（环境仓自带文档如 `doc/skills/…`、`doc/reference/…` 属此类，记为 env-fallback）；
  3. 行号后缀（`:64-67`）、符号后缀（`::func`）先剥离再判存在；
  4. 运行时目录（loop/state、loop/.logs、loop/.venv）→ 跳过（可删/不入库）；
  5. `doc/evidence/demo/`、`doc/history/` 内的历史路径串 → 计入「历史」不判失败
     （迁移记录见 `doc/evidence/demo/MIGRATION.md`；历史快照见 `doc/history/`）；
  6. 含 `<` `>` `*` `$` `…` 的模板/变量、URL、锚点 → 跳过；
  7. `KNOWN_MISSING` 中登记的「文档故意引用、本仓确实不存在」的缺口 → 跳过但保留登记理由。

用法：`python3 doc/audit/check_doc_links.py [--verbose]`
退出码：0 = 无断链；1 = 存在断链。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
ENV_CANDIDATES = [
    "RTL/", "TB/", "PKG/", "TESTLIB/", "SIMLIB_RUN/", "uvs.setup", "uvs.setup.orig",
    "doc/AGENTS.md", "doc/_notes/", "doc/_run_artifacts/", "doc/reference/",
    "doc/skills/", "doc/tools/", "doc/templates/", "doc/spec/evidence/",
    "kb/runs/", "kb/baselines/", "kb/index/", "kb/conflicts/", "kb/adjudication/",
    "kb/FIXTURE_IDENTITY.md", "kb/schema/", "kb/tools/",
    "CHECKPOINT-20261015-1123.md",
]
TOOL_PREFIXES = ["loop/", "kb/", "doc/", "workspaces/", "README.md", "AGENTS.md",
                 "environments.json", ".gitignore"]
SKIP_PREFIXES = ["loop/state", "loop/.logs", "loop/.venv", "loop/.pytest_cache",
                 "loop/.agently", "/tmp/", "/home/soft/"]
HISTORICAL_FILES = ["doc/evidence/demo/", "doc/history/"]
SKIP_NAMES = {"DEPRECATED", "TBD"}
INLINE = re.compile(r"`([^`\n]{2,200})`")
#: 明确「本仓不存在、但文档故意引用其缺失」的路径（审计发现的缺口，不是断链）。
#: 新增条目前必须说明原因；不要用它掩盖真正的路径写错。
KNOWN_MISSING = {
    "kb/tools/compile_only.sh": "审计发现：real N7 引用的工具不存在（A-A5）",
    "workspaces/simenv-tcs9620-64ch/": "约定目标位置；当前数据仍在 ENV_ROOT/kb（ENV_PLUGIN_SPEC §7）",
    # S0 契约与运行手册引用的环境资产：本机未挂载内网 ENV_ROOT（TB/ 不存在），
    # 属环境缺件而非本仓断链；登记以止住「文档引用自身计数」的漂移（F16-b 复核 §③）。
    "TB/top.sv": "环境资产：内网 ENV_ROOT 的 TB/top.sv，本机未挂载（S0 契约引用）",
}
LINE_SUFFIX = re.compile(r":\d+(-\d+)?(,\d+(-\d+)?)*$")
SYMBOL_SUFFIX = re.compile(r"::.*$")


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


def _candidate(token: str) -> str | None:
    token = token.strip().strip('"\'(),.;:')
    if not token or " " in token:
        return None
    if any(ch in token for ch in "<>*$|{}[]"):
        return None
    if token.startswith(("http://", "https://", "#", "/", "-", "~")):
        return None
    if "…" in token or "..." in token:
        return None
    if not any(token == p or token.startswith(p) for p in TOOL_PREFIXES + ENV_CANDIDATES):
        return None
    if any(token.startswith(p) for p in SKIP_PREFIXES):
        return None
    return token


def _resolve(token: str, env_root: Path | None, workspace: Path | None) -> tuple[Path | None, str]:
    """返回 (路径或 None, 解析到的根标签)。"""
    clean = SYMBOL_SUFFIX.sub("", LINE_SUFFIX.sub("", token.rstrip(".")))
    is_env_asset = any(clean == p.rstrip("/") or clean.startswith(p) for p in ENV_CANDIDATES)
    if is_env_asset:
        for base, label in ((workspace, "workspace"), (env_root, "env")):
            if base is None:
                continue
            if clean.startswith("kb/") and label == "workspace":
                rel = clean[len("kb/"):]
                if (base / rel).exists():
                    return base / rel, label
                continue
            if (base / clean).exists():
                return base / clean, label
        return None, "env?"
    if (TOOL_ROOT / clean).exists():
        return TOOL_ROOT / clean, "tool"
    # 反向兼容：环境仓文档（doc/skills、doc/reference …）在本仓不存在，但在 ENV_ROOT 下存在。
    if env_root is not None and (env_root / clean).exists():
        return env_root / clean, "env-fallback"
    return None, "tool?"


def main() -> int:
    verbose = "--verbose" in sys.argv
    env_root, workspace = _env_roots()
    missing: list[tuple[str, int, str]] = []
    historical = skipped = checked = 0

    for md in sorted(TOOL_ROOT.rglob("*.md")):
        rel = md.relative_to(TOOL_ROOT).as_posix()
        if rel.startswith((".git/", "loop/.venv/", "workspaces/")):
            continue
        is_historical = any(rel.startswith(p) for p in HISTORICAL_FILES)
        try:
            lines = md.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, 1):
            for match in INLINE.finditer(line):
                token = _candidate(match.group(1))
                if not token:
                    skipped += 1
                    continue
                if is_historical:
                    historical += 1
                    continue
                checked += 1
                if any(token.startswith(k) or token == k for k in KNOWN_MISSING):
                    continue
                found, _where = _resolve(token, env_root, workspace)
                if found is None:
                    missing.append((rel, lineno, token))

    print(f"TOOL_ROOT = {TOOL_ROOT}")
    print(f"ENV_ROOT  = {env_root}")
    print(f"WORKSPACE = {workspace}")
    print(f"checked={checked} skipped={skipped} historical={historical} missing={len(missing)}")
    for rel, lineno, token in missing:
        print(f"[MISSING] {rel}:{lineno}  {token}")
        if verbose:
            print(f"          base tried: TOOL_ROOT / ENV_ROOT / WORKSPACE_ROOT")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
