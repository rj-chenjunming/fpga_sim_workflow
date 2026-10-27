"""S0-b D1：RTL 端口的**确定性**抽取与差异派生（Host 侧；无模型、无副作用）。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §8.2-1（2026-10-27 裁决 Q1 = Host 确定性派生）。
为什么单独成模块：`ports` 的判据必须是"输入相同 ⇒ 输出相同"，所以"派生"与"模型提议/人确认"必须分开；
本模块只做前者，且**只读**。

不变式（不读源码也能判）：

1. **确定性**：同一输入两次派生，输出表的 md5 相同（输出里就带 `md5`）；
2. **无副作用**：派生前后输入树逐文件 md5 不变（调用方用 `tree_md5()` 断言）；
3. **不猜**：端口表解析不了（非 ANSI 端口、端口项缺方向、`ifdef` 割裂端口表、同名模块重复……）⇒
   该模块进 `unparsed` 且 `ok=False`；**不得**当作"无差异"；
4. **只报差异**：`changed` 只列有变化的模块，按模块名、端口名排序 ⇒ 可复算；
5. **按编译期宏求值**：端口表里允许出现 `` `ifdef/`ifndef/`elsif/`else/`endif ``（真实 DUT 顶层就有
   `` `ifndef SIMULATION `` 分段）。必须用**编译时实际定义的宏**（环境 `all_define.txt` 的 `-define`）求值，
   未定义的宏按 Verilog 语义取假 —— 否则会把"仿真配置下不存在的端口"算进去，得出错误的差异表。

术语：`width` 是归一化后的位宽文本（如 `[7:0]`；空串 = 1 bit 或未写位宽）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

#: 参与扫描的源码后缀（RTL 里既有 .v 也有 .sv）。
SV_SUFFIXES = (".v", ".sv")

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_MODULE = re.compile(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)")
_DIRECTION = re.compile(r"^(input|output|inout)\b\s*")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_RANGE = re.compile(r"\[\s*([^\[\]]*?)\s*\]")
_DIRECTIVE = re.compile(r"^\s*`(ifdef|ifndef|elsif|else|endif|define|undef|include|timescale|"
                        r"undefineall|resetall|celldefine|endcelldefine|default_nettype|line|"
                        r"begin_keywords|end_keywords|pragma)\b(.*)$")
_DEFINE_DECL = re.compile(r"^\s*`define\s+([A-Za-z_][A-Za-z0-9_$]*)")


@dataclass(frozen=True)
class Port:
    """一个端口：名字 + 方向 + 归一化位宽。"""

    name: str
    direction: str
    width: str

    def as_dict(self) -> dict:
        return {"name": self.name, "direction": self.direction, "width": self.width}


def _strip_comments(text: str) -> str:
    return _COMMENT.sub(" ", text)


def apply_preprocessor(text: str, defines: frozenset[str] | set[str] = frozenset()) -> str:
    """按 `defines` 求值条件编译，返回"像是编译时看到的那份文本"（保持行数）。

    - 支持 `` `ifdef / `ifndef / `elsif / `else / `endif ``（可嵌套）；
    - 未定义的宏按 Verilog 语义取假（**这就是编译器看到的行为**，不是猜）；
    - 处理 `` `define / `undef ``（文件内的定义对后续条件可见）；
    - 其它指令行（`include`/`timescale`/…）原样保留但不参与条件判断。
    """
    known = set(defines)
    out: list[str] = []
    # 栈元素：(本层当前是否活跃, 本层是否已有分支被选中)
    stack: list[tuple[bool, bool]] = []

    def active() -> bool:
        return all(layer[0] for layer in stack)

    for line in text.splitlines():
        match = _DIRECTIVE.match(line)
        if match is None:
            out.append(line if active() else "")
            continue
        directive, rest = match.group(1), match.group(2).strip()
        if directive in ("ifdef", "ifndef"):
            name = (rest.split() or [""])[0]
            taken = (name in known) if directive == "ifdef" else (name not in known)
            stack.append((taken, taken))
        elif directive == "elsif":
            name = (rest.split() or [""])[0]
            if not stack:
                out.append("")               # 不平衡 ⇒ 当空行；下面 ok 判定会暴露
                continue
            _, any_taken = stack[-1]
            taken = (not any_taken) and (name in known)
            stack[-1] = (taken, any_taken or taken)
        elif directive == "else":
            if not stack:
                out.append("")
                continue
            _, any_taken = stack[-1]
            stack[-1] = (not any_taken, True)
        elif directive == "endif":
            if stack:
                stack.pop()
        elif directive == "define":
            decl = _DEFINE_DECL.match(line)
            if decl is not None and active():
                known.add(decl.group(1))
        elif directive == "undef":
            name = (rest.split() or [""])[0]
            if active():
                known.discard(name)
        # 指令行本身不进入"可见文本"（引脚表里它不产生端口）
        out.append("")
    return "\n".join(out)


def load_defines(all_define_path: Path) -> frozenset[str]:
    """读环境侧 `all_define.txt`，取 `-define NAME`（`//` 注释行与行内注释都忽略）。"""
    path = Path(all_define_path)
    if not path.is_file():
        return frozenset()
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line.startswith("-define"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            names.add(parts[1])
    return frozenset(names)


def read_filelist(filelist: Path) -> list[str]:
    """读 `RTL/rtl_dir_pango.txt` 一类文件清单：忽略 `+incdir+`/`-define`/注释，返回相对路径。"""
    path = Path(filelist)
    if not path.is_file():
        return []
    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.split("//", 1)[0].strip()
        if not line or line.startswith("+") or line.startswith("-"):
            continue
        entries.append(line[2:] if line.startswith("./") else line)
    return entries


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    """按顶层逗号切分（忽略括号/方括号/字符串内部的逗号）。"""
    parts: list[str] = []
    depth = 0
    quote = ""
    current: list[str] = []
    for ch in text:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch == '"':                    # 只用双引号当字符串定界符：
            quote = ch                       # Verilog 的 `'d32` / `1'b0` 里的单引号不是字符串
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    tail = "".join(current)
    if tail.strip():
        parts.append(tail)
    return [p.strip() for p in parts if p.strip()]


def _header_after(text: str, start: int) -> str:
    """取 `module <name>` 之后到顶层 `;` 之前的头部（含 `#(...)` 参数块与端口表）。"""
    depth = 0
    quote = ""
    index = start
    while index < len(text):
        ch = text[index]
        if quote:
            if ch == quote:
                quote = ""
        elif ch == '"':                  # 只用双引号当字符串定界符；`'d32` / `1'b0` 里的单引号不是
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            return text[start:index]
        index += 1
    return text[start:]


def _drop_param_block(header: str) -> str:
    """去掉 `#( ... )` 参数块，只留端口表（无参模块原样返回）。"""
    text = header.lstrip()
    if not text.startswith("#"):
        return text
    depth = 0
    for index, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[index + 1:].lstrip()
    return text  # 括号不平衡 ⇒ 调用方判 unparsed


def parse_module_ports(source: str, defines: frozenset[str] | set[str] = frozenset()
                       ) -> tuple[dict[str, list[Port]], list[str]]:
    """解析一段源码里的模块端口：返回 `(模块名 → 端口列表, 解析不了的模块名列表)`。

    `defines` = 编译期宏集合（见 `load_defines`）；条件编译按它求值。
    """
    text = _strip_comments(apply_preprocessor(_strip_comments(source), defines))
    modules: dict[str, list[Port]] = {}
    unparsed: list[str] = []
    for match in _MODULE.finditer(text):
        name = match.group(1)
        header = _drop_param_block(_header_after(text, match.end())).strip()
        if not header:
            modules[name] = []
            continue
        if not (header.startswith("(") and header.endswith(")")):
            unparsed.append(name)
            continue
        ports: list[Port] = []
        for item in _split_top_level(header[1:-1]):
            direction_match = _DIRECTION.match(item)
            if direction_match is None:
                ports = []                       # 缺方向（non-ANSI / 续行 / 宏）⇒ 整模块不猜
                break
            rest = item[direction_match.end():]
            range_match = _RANGE.search(rest)
            width = ""
            if range_match is not None:
                width = "[%s]" % re.sub(r"\s+", "", range_match.group(1))
            names = _IDENT.findall(_RANGE.sub(" ", rest))
            if not names:
                ports = []
                break
            ports.append(Port(name=names[-1], direction=direction_match.group(1), width=width))
        if ports or header[1:-1].strip() == "":
            modules[name] = ports
        else:
            unparsed.append(name)
    return modules, unparsed


def _listed_sources(rtl_dir: Path) -> tuple[list[Path], bool]:
    """优先按 `RTL/rtl_dir_pango.txt` 的文件清单取源文件（= 编译实际编的那批）。

    返回 `(文件列表, 是否来自清单)`；清单缺失或一条都对不上时退回全树遍历。
    """
    filelist = rtl_dir / "rtl_dir_pango.txt"
    if not filelist.is_file():
        return [], False
    marker = rtl_dir.name + "/"
    resolved: list[Path] = []
    for rel in read_filelist(filelist):
        candidate = rtl_dir / (rel.split(marker, 1)[1] if marker in rel else rel)
        if candidate.is_file():
            resolved.append(candidate)
    return resolved, bool(resolved)


def scan_tree(root: Path, defines: frozenset[str] | set[str] = frozenset(),
              prefer_filelist: bool = True) -> dict:
    """扫一棵 **RTL 目录** → 模块端口表、覆盖率与树指纹。确定性（排序遍历，无写入）。

    - `defines`：编译期宏（`all_define.txt`），条件编译按它求值；
    - `prefer_filelist`：有 `rtl_dir_pango.txt` 时只扫清单里那批文件（与编译一致，减少无关噪声）。
    """
    root = Path(root)
    if not root.is_dir():
        return {"root": str(root), "exists": False, "files": 0, "modules": {},
                "unparsed": [], "duplicates": 0, "from_filelist": False, "md5": ""}
    modules: dict[str, list[Port]] = {}
    unparsed: list[str] = []
    duplicates = 0
    listed, from_filelist = (_listed_sources(root) if prefer_filelist else ([], False))
    paths = listed if from_filelist else [p for p in sorted(root.rglob("*"))
                                          if p.is_file() and p.suffix in SV_SUFFIXES]
    files = 0
    for path in paths:
        if not path.is_file() or path.suffix not in SV_SUFFIXES:
            continue
        files += 1
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            unparsed.append(path.relative_to(root).as_posix())
            continue
        found, bad = parse_module_ports(source, defines)
        unparsed.extend(bad)
        for name, ports in found.items():
            if name in modules:
                if [p.as_dict() for p in sorted(modules[name], key=lambda p: p.name)] == \
                        [p.as_dict() for p in sorted(ports, key=lambda p: p.name)]:
                    duplicates += 1             # 同名且端口完全一致（厂商库常见）⇒ 不是歧义
                else:
                    unparsed.append(f"{name}@{path.relative_to(root).as_posix()}")
                continue
            modules[name] = ports
    canonical = {name: [p.as_dict() for p in sorted(ports, key=lambda p: p.name)]
                 for name, ports in sorted(modules.items())}
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"root": str(root), "exists": True, "files": files, "modules": canonical,
            "unparsed": sorted(unparsed), "duplicates": duplicates,
            "from_filelist": from_filelist, "md5": hashlib.sha256(blob).hexdigest()}


def tree_md5(root: Path) -> str:
    """输入树的内容指纹（判"派生无副作用"用：只看内容，不看 mtime）。"""
    root = Path(root)
    if not root.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.md5(path.read_bytes()).hexdigest().encode("ascii"))
    return digest.hexdigest()


def _diff_ports(before: list[Port], after: list[Port]) -> dict:
    old = {p.name: p for p in before}
    new = {p.name: p for p in after}
    return {
        "added": sorted(n for n in new if n not in old),
        "removed": sorted(n for n in old if n not in new),
        "changed": [
            {"name": name, "before": old[name].as_dict(), "after": new[name].as_dict()}
            for name in sorted(set(old) & set(new))
            if old[name].as_dict() != new[name].as_dict()
        ],
    }


def derive_port_diff(baseline_root: Path, candidate_root: Path,
                     modules: list[str] | None = None,
                     defines: frozenset[str] | set[str] = frozenset()) -> dict:
    """派生端口差异表（确定性、只读）。

    `modules` 给定时只比较这些模块（例如 TB 顶层实例化到的 DUT 模块）；给定模块在某一侧缺失
    ⇒ 计入 `added_modules` / `removed_modules`，仍算差异。
    """
    base = scan_tree(baseline_root, defines)
    cand = scan_tree(candidate_root, defines)
    wanted = sorted(set(modules)) if modules is not None else None
    base_modules = base["modules"]
    cand_modules = cand["modules"]
    if wanted is not None:
        base_modules = {k: v for k, v in base_modules.items() if k in wanted}
        cand_modules = {k: v for k, v in cand_modules.items() if k in wanted}

    def _unparsed(scan: dict) -> list[str]:
        rows = scan["unparsed"]
        if wanted is None:
            return rows
        return [u for u in rows if u.split("@")[0] in wanted]

    changed = []
    for name in sorted(set(base_modules) & set(cand_modules)):
        before = [Port(**row) for row in base_modules[name]]
        after = [Port(**row) for row in cand_modules[name]]
        delta = _diff_ports(before, after)
        if delta["added"] or delta["removed"] or delta["changed"]:
            changed.append({"module": name, **delta})

    result = {
        "modules_filter": wanted,
        "baseline": {"exists": base["exists"], "md5": base["md5"], "files": base["files"],
                     "modules": len(base_modules), "parsed_modules": len(base["modules"]),
                     "unparsed": _unparsed(base)},
        "candidate": {"exists": cand["exists"], "md5": cand["md5"], "files": cand["files"],
                      "modules": len(cand_modules), "parsed_modules": len(cand["modules"]),
                      "unparsed": _unparsed(cand)},
        "changed": changed,
        "added_modules": sorted(set(cand_modules) - set(base_modules)),
        "removed_modules": sorted(set(base_modules) - set(cand_modules)),
    }
    # 不猜：任一输入不存在 / 有解析不了的模块 ⇒ ok=False（调用方必须 fail-closed）
    ok = bool(result["baseline"]["exists"] and result["candidate"]["exists"]
              and not result["baseline"]["unparsed"] and not result["candidate"]["unparsed"])
    blob = json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")
    result["md5"] = hashlib.sha256(blob).hexdigest()
    result["ok"] = ok
    return result
