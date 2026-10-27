"""UVS 编译日志的**唯一**解析实现（S0-b `smoke` 用；N7 将来也应复用）。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §8.2-2 / §8.4 红线 7（2026-10-27 修订）。

为什么必须有它、且必须有测试：**裸 grep 会把汇总行本身算成错误**——
`Compilation: 0 error(s), 13 warning(s)` 里就含 "error"，用 `grep -c error` 会得到 1。
所以判据只能是"解析工具自印的汇总行 + `Error-<code>` / `Warning-<code>` 明细行"。

`uvlan` 每段编译的日志末尾自印一行：

    Compilation: 0 error(s), 13 warning(s)

warning 明细是 `Warning-<code>: <text>` 形式（实测样例 `Warning-120002: Command option warning`、
`Warning-121147: Redefinition`）。本模块只做**纯解析**，不跑编译、不写文件。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SUMMARY = re.compile(r"Compilation:\s*(\d+)\s*error\(s\),\s*(\d+)\s*warning\(s\)")
_WARNING = re.compile(r"^\s*(Warning-\d+)\s*:\s*(.*)$")
_ERROR = re.compile(r"^\s*(Error-\d+)\s*:\s*(.*)$")


@dataclass(frozen=True)
class LogReport:
    """一段编译日志的读数。`summary` 缺失 ⇒ `ok=False`（不猜成 0 error）。"""

    path: str
    ok: bool
    errors: int | None
    warnings: int | None
    error_codes: dict
    warning_codes: dict
    line_count: int

    def as_dict(self) -> dict:
        return {
            "path": self.path, "ok": self.ok, "errors": self.errors,
            "warnings": self.warnings, "error_codes": dict(sorted(self.error_codes.items())),
            "warning_codes": dict(sorted(self.warning_codes.items())),
            "line_count": self.line_count,
        }


def parse_log(path: Path | str) -> LogReport:
    """解析一段 uvlan 编译日志。

    - 汇总行取**最后一条**（重编时日志可能追加）；
    - 明细按 `<code>: <text>` 的 code 计数（同一 code 出现多次就计多次）；
    - 没有汇总行 ⇒ `ok=False`、`errors/warnings=None`（**不**当成 0）。
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    lines = text.splitlines()
    summary = None
    for line in lines:
        match = _SUMMARY.search(line)
        if match is not None:
            summary = match
    error_codes: dict[str, int] = {}
    warning_codes: dict[str, int] = {}
    for line in lines:
        err = _ERROR.match(line)
        if err is not None:
            error_codes[err.group(1)] = error_codes.get(err.group(1), 0) + 1
            continue
        warn = _WARNING.match(line)
        if warn is not None:
            warning_codes[warn.group(1)] = warning_codes.get(warn.group(1), 0) + 1
    if summary is None:
        return LogReport(str(path), False, None, None, error_codes, warning_codes, len(lines))
    return LogReport(str(path), True, int(summary.group(1)), int(summary.group(2)),
                     error_codes, warning_codes, len(lines))


def warning_delta(baseline: dict, candidate: dict) -> dict:
    """warning 的**基线相对增量**（判"本次改动是否引入新告警"）。

    输入是 `{code: 次数}`。输出三个集合：`added`（基线没有的 code）、
    `count_increase`（同 code 次数上升）、`removed`（基线有、候选没有的 code）。
    **只有 added 与 count_increase 需要逐条评估**（契约 §8.2-2）。
    """
    added = sorted(code for code in candidate if code not in baseline)
    removed = sorted(code for code in baseline if code not in candidate)
    count_increase = [
        {"code": code, "baseline": baseline[code], "candidate": candidate[code]}
        for code in sorted(set(baseline) & set(candidate))
        if candidate[code] > baseline[code]
    ]
    return {"added": added, "removed": removed, "count_increase": count_increase,
            "needs_evaluation": sorted(added + [row["code"] for row in count_increase])}


def summarize(reports: list[LogReport]) -> dict:
    """把一段或多段日志汇总成 smoke 判据需要的最小结构（不含"通过/不通过"决策）。"""
    errors = sum(r.errors or 0 for r in reports)
    warnings = sum(r.warnings or 0 for r in reports)
    codes: dict[str, int] = {}
    for report in reports:
        for code, count in report.warning_codes.items():
            codes[code] = codes.get(code, 0) + count
    return {
        "ok": all(r.ok for r in reports) and bool(reports),
        "errors": errors,
        "warnings": warnings,
        "warning_codes": dict(sorted(codes.items())),
        "logs": [r.as_dict() for r in reports],
    }
