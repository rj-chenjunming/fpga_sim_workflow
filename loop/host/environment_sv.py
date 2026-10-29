"""现有环境的 SystemVerilog 事实提取。"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any


#: 从调用行里抽候选 callee 时忽略的语言关键字（其余候选再去源码里找定义）
_API_KEYWORDS = frozenset({
    "if", "else", "for", "foreach", "while", "do", "case", "begin", "end", "task",
    "function", "return", "new", "void", "int", "bit", "logic", "input", "output",
    "reg", "wire", "assign", "always", "initial", "repeat", "fork", "join", "wait",
    "posedge", "negedge", "this", "super",
})
_API_SEARCH_DIRS = ("TB", "TESTLIB")
_API_SEARCH_MAX_BYTES = 4 * 1024 * 1024  # 单文件上限，避免把超大生成件读进内存


def _call_candidates(window_text: str) -> list[str]:
    """从调用窗口抽 callee 名（`obj.method(` 与 `method(`），过滤关键字。"""
    names: list[str] = []
    for match in re.finditer(r"(?:\.|\b)([A-Za-z_]\w*)\s*\(", window_text):
        name = match.group(1)
        if name in _API_KEYWORDS:
            continue
        if name not in names:
            names.append(name)
    return names


def _extract_api_definition(text: str, callee: str) -> dict[str, Any] | None:
    """只读提取完整签名/函数体；不闭合的定义显式标记不完整。"""
    pattern = re.compile(r"\b(task|function)\b[^\n;]*?\b%s\s*\(" % re.escape(callee))
    match = pattern.search(text)
    if match is None:
        return None
    start = text.rfind("\n", 0, match.start()) + 1
    lines = text[start:].splitlines()
    sig_lines: list[str] = []
    depth = 0
    seen_paren = False
    sig_end = 0
    for idx, line in enumerate(lines):
        sig_lines.append(line)
        depth += line.count("(") - line.count(")")
        if "(" in line:
            seen_paren = True
        if seen_paren and depth <= 0 and ");" in line.replace(" ", ""):
            sig_end = idx
            break
        if seen_paren and depth <= 0 and line.strip().endswith(");"):
            sig_end = idx
            break
    signature = " ".join(x.strip() for x in sig_lines)
    body_lines: list[str] = []
    complete = False
    for line in lines[sig_end + 1:]:
        body_lines.append(line)
        if re.search(r"\bend(task|function)\b", line):
            complete = True
            break
    body = "\n".join(body_lines).strip()
    return {"signature": signature, "body": body, "complete": complete,
            "line": start_lines(text, match.start())}


def start_lines(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _find_api_definition(env_root: Path, case_text: str, callee: str,
                         cache: dict | None = None) -> dict[str, Any] | None:
    """先查本用例文件（本地 task/function），再查 ENV_ROOT/TB、TESTLIB 的定义。

    只做**只读文本扫描**，不执行任何环境脚本；找不到定义返回 None（由调用方标 not_found，
    不得让模型去猜参数语义）。
    """
    local = _extract_api_definition(case_text, callee)
    if local is not None:
        return {"callee": callee, "defined_in": "<case_file>", "source": "case_file",
                "signature": local["signature"], "body": local["body"], "complete": local["complete"]}
    if cache is None:
        cache = {}
    key = (str(env_root), callee)
    if key in cache:
        return cache[key]
    for dirname in _API_SEARCH_DIRS:
        root = env_root / dirname
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.sv")):
            try:
                if path.stat().st_size > _API_SEARCH_MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = _extract_api_definition(text, callee)
            if found is None:
                continue
            result = {
                "callee": callee,
                "defined_in": str(path.relative_to(env_root)),
                "source": f"scan:{dirname}",
                "signature": found["signature"],
                "body": found["body"],
                "complete": found["complete"],
            }
            cache[key] = result
            return result
    cache[key] = None
    return None


def _api_semantics_for(env_root: Path, source_text: str, line: int,
                       cache: dict | None = None) -> list[dict[str, Any]]:
    """取修订点附近调用的**测试台 API 语义**（signature + body），供 N6 判断实参角色。

    实测教训（2026-10-20 real 首跑）：`reg_field_test(addr, data_expmask, initial_dat, only_r)`
    的第 2 个数据参数是**期望掩码**、第 3 个是初始值；模型只看到调用行，把两者弄反，
    期望值改错（N7 只抓语法，抓不到）。把定义源码作为事实输入，模型才能按**参数名**定位。
    """
    if not source_text or line < 1:
        return []
    lines = source_text.splitlines()
    window = "\n".join(lines[max(0, line - 3):min(len(lines), line + 2)])
    semantics: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for callee in _call_candidates(window):
        found = _find_api_definition(env_root, source_text, callee, cache)
        if found is None:
            continue
        key = (found["callee"], found["signature"])
        if key in seen:
            continue
        seen.add(key)
        semantics.append(found)
    return semantics


#: RTL 截断/清零的常见写法：`{16'h0, wdata[15:0]}`（高半清零、低半保留）
_RTL_CONCAT_RE = re.compile(
    r"\{\s*(\d+)'([hb])([0-9a-fA-F_]+)\s*,\s*([A-Za-z_]\w*)\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*\}"
)


def _rtl_effect_hint(rtl_change: list[dict[str, Any]]) -> dict[str, Any] | None:
    """从 RTL 新增行里抽**确定性的位截断事实**（readback mask / 保留位）。

    为什么由 Host 算而不是让模型推：实测 2026-10-20 real 第二轮，模型知道要改
    `data_expmask`，但把掩码应用到相反的一半（写 `0xffff_0000` / `0x1234_0000`）。
    `{16'h0, w[15:0]}` 的语义是确定的：保留 `[15:0]`、清 `[31:16]` ⇒ 期望值 = 写入值 &
    `0x0000ffff`。Host 把这条算术作为事实给模型，模型只负责选对实参与填值。
    """
    for change in rtl_change:
        hunk = str(change.get("hunk") or "")
        for line in hunk.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for match in _RTL_CONCAT_RE.finditer(line):
                const_bits = match.group(3).replace("_", "").strip()
                if const_bits.strip("0"):
                    continue  # 只处理"常量全 0"的截断（其余形态不当成确定事实）
                hi, lo = int(match.group(5)), int(match.group(6))
                if lo < 0 or hi < lo or hi > 31:
                    continue
                width = int(match.group(1))
                total = 32
                retained_mask = ((1 << (hi - lo + 1)) - 1) << lo
                cleared_mask = ((1 << total) - 1) ^ retained_mask
                cleared_hi = total - 1
                cleared_lo = hi + 1
                return {
                    "pattern": match.group(0).strip(),
                    "retained_bits": f"[{hi}:{lo}]",
                    "retained_mask": f"0x{retained_mask:08x}",
                    "cleared_bits": f"[{cleared_hi}:{cleared_lo}]" if cleared_lo <= cleared_hi else None,
                    "cleared_mask": f"0x{cleared_mask:08x}",
                    "rule": "期望读回值 = 写入值 & retained_mask；不得把掩码应用到相反的一半",
                    "zero_prefix_bits": width,
                    "source": change.get("file"),
                }
    return None
