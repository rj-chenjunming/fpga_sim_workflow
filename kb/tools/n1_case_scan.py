#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""n1_case_scan.py —— TESTLIB 用例静态访问扫描 → 用例侧索引（N1）

口径**逐字**对齐 `doc/_notes/09_iface_doc_vs_case.md` §B.0：
  1. 剔除 `//` 行注释/行尾注释（字符串内的 `//` 不剔）、剔除 `/* */` 块注释；
  2. 剔除本文件 `` `define `` 行（只当宏表用，不作为访问）；
  3. 剔除 task/function **声明**行；
  4. 剔除实参里的数据类型名（`int pid` / `bit [31:0] addr` 这类声明残留）。
  被统计的 callee 共 12 个；地址取**去掉前导 sequencer 实参后的第一个实参**；
  `base_addr` 靠顺序扫描 + 宏表展开（`TB/tbtop.sv` / `TB/top_pkg.sv` / `TB/LIBS/**` /
  本文件 `` `define ``）+ 常量折叠；变量表在 `task`/`function` 与 `endtask`/`endfunction`
  边界清空；若表达式只剩 `for` 循环变量则按该文件 `for(...)` 头推断的取值范围枚举
  （上限 4096）；任务形参只在**所有调用点**都能解析时回填；`set_write/set_read/...`
  这些与类方法同名的名字**不参与形参回填**；解析不出一律 B3，**不猜**。

产物（全部由本脚本写；幂等确定性：同一输入两次运行逐字节相同）：
  kb/index/case_access.json / kb/index/case_access.csv / kb/index/cases.json
  kb/index/segments.json / kb/index/segment_rtl.json

用法：
  python3 kb/tools/n1_case_scan.py              # 写索引
  python3 kb/tools/n1_case_scan.py --check      # 只打印统计，不写盘
  python3 kb/tools/n1_case_scan.py --diag DIR   # 额外把诊断落 DIR
"""

import argparse
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kb_lib  # noqa: E402  （契约：指纹/写盘/校验一律复用）

ROOT = kb_lib.ROOT
TESTLIB_DIR = os.path.join(ROOT, "TESTLIB")

# ------------------------------------------------------------------ 口径常量

CALLEES = [
    "PCIE_REG_WR", "PCIE_REG_RD", "PCIE_REG_RDCHK", "PCIE_REG_RW",
    "set_write", "set_read", "set_rdchk",
    "set_reg_wr", "set_reg_rdchk", "set_reg_rd", "set_reg_rw",
    "reg_field_test",
]
CALLEE_RE = re.compile(r"\b(" + "|".join(CALLEES) + r")\s*\(")

# 与 callee 同名的本地 task 不参与形参回填（09 §B.0）
NO_BACKFILL = set(CALLEES)

ENUM_LIMIT = 4096  # 09 §B.0：for 循环变量按范围枚举，上限 4096 个取值

# 变量表 / 形参回填口径（逐条对照 09 §B.0，见 resolve_sites 与 collect_file_loops 注释）
KEEP_UNRESOLVED = False   # 赋值 RHS 解析不出 → 置未知（不猜）
KEEP_PARTIAL = False      # 位选/域选赋值 → 置未知（不猜）
LOOP_TYPE_ANY = True      # for 头变量无论 `int` 还是 `bit[31:0]` 都推断取值域
LOOPVAR_PREPASS = True    # 「按该文件内 for(...) 头推断取值范围」= 文件级预扫 for 表
BACKFILL_CHAIN = False    # 形参回填不跨任务链式传递（调用点实参须自身可解析）

# 前导 sequencer 实参判据（`*_seq` / `m_pcie_seq` / `vseqr` 等）
SEQ_ARG_RE = re.compile(r"^(?:[A-Za-z_]\w*::)?(?:m_)?\w*_seq$|^vseqr$")

# 实参里的数据类型名（声明残留）：`int pid` / `bit [31:0] addr`
TYPE_PREFIX_RE = re.compile(
    r"^(?:(?:input|output|inout|ref|const|var|automatic|static|virtual|local|protected)\s+)*"
    r"(?:bit|logic|reg|int|integer|byte|shortint|longint|time|shortreal|real|string|"
    r"[A-Za-z_]\w*(?:::\w+)*)\s*"
    r"(?:\[[^\]]*\]\s*)*"
    r"([A-Za-z_]\w*)$"
)

# ------------------------------------------------------------------ 注释剥离


def strip_comments(text):
    """剔除 `/* */` 与 `//` 注释；字符串内的 `//` 不剔。注释内容换成空白（保换行）。"""
    out = []
    i = 0
    n = len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j < 0:
                j = n - 2
            seg = text[i:j + 2]
            out.append("".join("\n" if ch == "\n" else " " for ch in seg))
            i = j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _paren_balance(line):
    depth = 0
    in_str = False
    i = 0
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return depth


def logical_lines(lines):
    """跨行（圆括号未闭合）拼成一条逻辑行；返回 [(start, end, text)]。"""
    out = []
    buf = None
    start = 1
    depth = 0
    for idx, ln in enumerate(lines, 1):
        if buf is None:
            buf = ln
            start = idx
        else:
            buf = buf + "\n" + ln
        depth += _paren_balance(ln)
        if depth <= 0:
            out.append((start, idx, buf))
            buf = None
            depth = 0
    if buf is not None:
        out.append((start, len(lines), buf))
    return out


def split_top(text, sep=";"):
    parts = []
    depth = 0
    cur = ""
    in_str = False
    i = 0
    while i < len(text):
        c = text[i]
        if in_str:
            cur += c
            if c == "\\" and i + 1 < len(text):
                cur += text[i + 1]
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            cur += c
        elif c in "([{":
            depth += 1
            cur += c
        elif c in ")]}":
            depth -= 1
            cur += c
        elif c == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    parts.append(cur)
    return parts


def split_args(argstr):
    parts = []
    depth = 0
    cur = ""
    in_str = False
    i = 0
    while i < len(argstr):
        c = argstr[i]
        if in_str:
            cur += c
            if c == "\\" and i + 1 < len(argstr):
                cur += argstr[i + 1]
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            cur += c
        elif c in "([{":
            depth += 1
            cur += c
        elif c in ")]}":
            depth -= 1
            cur += c
        elif c == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
        i += 1
    if cur.strip():
        parts.append(cur)
    return parts


# ------------------------------------------------------------------ 宏表


def parse_defines(text):
    """text 需已剥注释。返回 {name: (params_or_None, body)}。支持 `\\` 续行。"""
    text = re.sub(r"\\\r?\n", " ", text)
    macros = {}
    for m in re.finditer(r"`define[ \t]+([A-Za-z_]\w*)(\(([^)]*)\))?[ \t]*(.*)", text):
        name = m.group(1)
        params = m.group(3)
        body = m.group(4).strip()
        if params is None:
            macros[name] = (None, body)
        else:
            macros[name] = ([p.strip() for p in params.split(",") if p.strip()], body)
    return macros


def load_macro_table():
    """宏表：TB/tbtop.sv + TB/top_pkg.sv + TB/LIBS/** 下的 sv/v/svh。"""
    paths = [os.path.join(ROOT, "TB", "tbtop.sv"),
             os.path.join(ROOT, "TB", "top_pkg.sv")]
    libs = os.path.join(ROOT, "TB", "LIBS")
    for ext in ("*.sv", "*.svh", "*.v", "*.vh"):
        paths += sorted(glob.glob(os.path.join(libs, "**", ext), recursive=True))
    macros = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            macros.update(parse_defines(strip_comments(f.read())))
    return macros


def expand_macros(expr, macros):
    """把 `NAME 与 `NAME(args) 展开成文本（递归，带环保护）。"""
    if "`" not in expr:
        return expr
    pat = re.compile(r"`([A-Za-z_]\w*)(\([^()]*\))?")

    def repl(m):
        name = m.group(1)
        args = m.group(2)
        if name not in macros:
            return m.group(0)
        params, body = macros[name]
        if params:
            if args is None:
                return m.group(0)
            parts = split_args(args[1:-1])
            body2 = body
            for prm, val in zip(params, parts):
                body2 = re.sub(r"\b%s\b" % re.escape(prm), val, body2)
            return body2
        if args is not None:
            return m.group(0)
        return body

    prev = None
    cur = expr
    for _ in range(64):
        if cur == prev:
            break
        prev = cur
        cur = pat.sub(repl, cur)
    return cur


# ------------------------------------------------------------------ 表达式求值
# value = ('c', int) | ('s', frozenset) | ('r', lo, hi, step) | ('u', reason)

UNK = ("u", None)


class Unresolved(Exception):
    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


TOKEN_RE = re.compile(
    r"(?:\d+)?'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?_]+"
    r"|0[xX][0-9a-fA-F_]+"
    r"|\d[\d_]*"
    r"|[A-Za-z_]\w*"
    r"|<<|>>|<=|>=|==|!=|&&|\|\||\*\*"
    r"|[-+*/%&|^~!?:()<>]"
)


def sv_int(tok):
    t = tok.replace("_", "")
    if t.startswith("0x") or t.startswith("0X"):
        return int(t, 16)
    if "'" in t:
        body = t.split("'", 1)[1]
        base_ch = body[0].lower() if body else ""
        digits = body[1:]
        if digits == "" and base_ch in "01":
            return int(base_ch)
        if re.search(r"[xXzZ?]", digits):
            raise Unresolved("含 x/z 的字面量 %s" % tok)
        base = {"b": 2, "o": 8, "d": 10, "h": 16}.get(base_ch)
        if base is None:
            raise Unresolved("未知进制 %s" % tok)
        return int(digits, base)
    return int(t, 10)


def vc(x):
    return ("c", x & 0xFFFFFFFF)


def vset(vals):
    vals = sorted(set(v & 0xFFFFFFFF for v in vals))
    if not vals:
        return ("u", "空值集")
    if len(vals) == 1:
        return ("c", vals[0])
    if len(vals) > ENUM_LIMIT:
        return ("r", vals[0], vals[-1], 1)
    return ("s", frozenset(vals))


def vrange(lo, hi, step):
    if step <= 0:
        return ("u", "非正步长")
    if hi < lo:
        return ("u", "空范围")
    cnt = (hi - lo) // step + 1
    if cnt > ENUM_LIMIT:
        return ("r", lo, hi, step)
    return vset(range(lo, hi + 1, step))


def as_set(v):
    if v[0] == "c":
        return frozenset([v[1]])
    if v[0] == "s":
        return v[1]
    if v[0] == "r" and (v[2] - v[1]) // v[3] + 1 <= ENUM_LIMIT:
        return frozenset(range(v[1], v[2] + 1, v[3]))
    return None


def as_range(v):
    if v[0] == "c":
        return (v[1], v[1], 1)
    if v[0] == "s":
        vals = sorted(v[1])
        return (vals[0], vals[-1], 1)
    if v[0] == "r":
        return (v[1], v[2], v[3])
    return None


def _apply(op, x, y):
    try:
        if op == "+":
            return vc(x + y)
        if op == "-":
            return vc(x - y)
        if op == "*":
            return vc(x * y)
        if op == "/":
            return ("u", "除零") if y == 0 else vc(x // y)
        if op == "%":
            return ("u", "除零") if y == 0 else vc(x % y)
        if op == "<<":
            return vc((x << y) & 0xFFFFFFFF) if 0 <= y < 64 else ("u", "移位越界")
        if op == ">>":
            return vc((x >> y) & 0xFFFFFFFF) if 0 <= y < 64 else ("u", "移位越界")
        if op == "&":
            return vc(x & y)
        if op == "|":
            return vc(x | y)
        if op == "^":
            return vc(x ^ y)
        if op == "**":
            return vc(pow(x, y) & 0xFFFFFFFF) if y < 64 else ("u", "幂越界")
    except (OverflowError, ValueError):
        return ("u", "算术溢出")
    return ("u", "未知运算符 %s" % op)


CMP_FUNCS = {
    "<": lambda x, y: x < y, "<=": lambda x, y: x <= y,
    ">": lambda x, y: x > y, ">=": lambda x, y: x >= y,
    "==": lambda x, y: x == y, "!=": lambda x, y: x != y,
}

BITOPS = ("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^", "**")


def binop(op, a, b):
    if a[0] == "u" or b[0] == "u":
        return UNK
    if a[0] == "c" and b[0] == "c":
        return _apply(op, a[1], b[1])
    if op in BITOPS:
        # 仿射捷径只对**量程**（'r'）成立；有限枚举（'s'）走逐元素展开，
        # 否则 {0,0x400,…} + 0x48 会被错当成步长 1 的大范围。
        if a[0] == "c" and b[0] == "r":
            a, b = b, a
            swap = True
        else:
            swap = False
        if a[0] == "r" and b[0] == "c":
            rng = as_range(a)
            if rng is None:
                return UNK
            lo, hi, st = rng
            k = b[1]
            try:
                if op == "+" and not swap:
                    return vrange(lo + k, hi + k, st)
                if op == "+" and swap:
                    return vrange(lo + k, hi + k, st)
                if op == "-" and not swap:
                    return vrange(lo - k, hi - k, st)
                if op == "*":
                    if k == 0:
                        return vc(0)
                    if k > 0:
                        return vrange(lo * k, hi * k, st * k)
                if op == "<<" and not swap and 0 <= k < 32:
                    return vrange((lo << k) & 0xFFFFFFFF, (hi << k) & 0xFFFFFFFF,
                                  max(1, st << k))
                if op == ">>" and not swap and 0 <= k < 32:
                    return vrange(lo >> k, hi >> k, max(1, st >> k))
                if op == "/" and not swap and k > 0 and st == 1:
                    return vrange(lo // k, hi // k, 1)
                if op == "%" and not swap and k > 0 and (hi - lo) < k * 16:
                    return vset(x % k for x in range(lo, hi + 1))
            except (Unresolved, ValueError):
                return UNK
    sa = as_set(a)
    sb = as_set(b)
    if sa is not None and sb is not None and len(sa) * len(sb) <= ENUM_LIMIT:
        out = set()
        for x in sa:
            for y in sb:
                r = _apply(op, x, y)
                if r[0] == "u":
                    return UNK
                out.add(r[1])
        return vset(out)
    return UNK


class Evaluator(object):
    def __init__(self, env):
        self.env = env
        self.toks = []
        self.pos = 0

    def ev(self, expr):
        expr = expr.strip()
        if not expr:
            raise Unresolved("空表达式")
        self.toks = TOKEN_RE.findall(expr)
        self.pos = 0
        # 覆盖性检查：token 去掉空白后应拼接出原文
        if "".join(self.toks).replace(" ", "") != re.sub(r"\s+", "", expr):
            raise Unresolved("含未识别字符")
        v = self._ternary()
        if self.pos != len(self.toks):
            raise Unresolved("表达式尾部多余 token")
        return v

    def _peek(self):
        return self.toks[self.pos] if self.pos < len(self.toks) else None

    def _next(self):
        t = self._peek()
        if t is None:
            raise Unresolved("表达式意外结束")
        self.pos += 1
        return t

    def _ternary(self):
        cond = self._lor()
        if self._peek() == "?":
            self._next()
            a = self._ternary()
            if self._peek() != ":":
                raise Unresolved("三元缺 :")
            self._next()
            b = self._ternary()
            cs = as_set(cond)
            if cs is None:
                raise Unresolved("三元条件未定")
            if cs == frozenset([1]):
                return a
            if cs == frozenset([0]):
                return b
            sa, sb = as_set(a), as_set(b)
            if sa is None or sb is None:
                raise Unresolved("三元分支不可枚举")
            return vset(sorted(sa | sb))
        return cond

    def _logic(self, a, b, op):
        sa, sb = as_set(a), as_set(b)
        if sa is None or sb is None:
            raise Unresolved("逻辑运算不可枚举")
        out = set()
        for x in sa:
            for y in sb:
                out.add(1 if ((x != 0) if op == "||" else (x != 0 and y != 0)) else 0)
        return vset(sorted(out))

    def _lor(self):
        a = self._land()
        while self._peek() == "||":
            self._next()
            a = self._logic(a, self._land(), "||")
        return a

    def _land(self):
        a = self._bor()
        while self._peek() == "&&":
            self._next()
            a = self._logic(a, self._bor(), "&&")
        return a

    def _bor(self):
        a = self._bxor()
        while self._peek() == "|":
            self._next()
            a = binop("|", a, self._bxor())
        return a

    def _bxor(self):
        a = self._band()
        while self._peek() == "^":
            self._next()
            a = binop("^", a, self._band())
        return a

    def _band(self):
        a = self._eq()
        while self._peek() == "&":
            self._next()
            a = binop("&", a, self._eq())
        return a

    def _eq(self):
        a = self._rel()
        while self._peek() in ("==", "!="):
            op = self._next()
            a = self._cmp(a, self._rel(), op)
        return a

    def _rel(self):
        a = self._shift()
        while self._peek() in ("<", "<=", ">", ">="):
            op = self._next()
            a = self._cmp(a, self._shift(), op)
        return a

    def _cmp(self, a, b, op):
        sa, sb = as_set(a), as_set(b)
        if sa is None or sb is None:
            raise Unresolved("比较运算不可枚举")
        f = CMP_FUNCS[op]
        out = set()
        for x in sa:
            for y in sb:
                out.add(1 if f(x, y) else 0)
        return vset(sorted(out))

    def _shift(self):
        a = self._add()
        while self._peek() in ("<<", ">>"):
            op = self._next()
            a = binop(op, a, self._add())
        return a

    def _add(self):
        a = self._mul()
        while self._peek() in ("+", "-"):
            op = self._next()
            a = binop(op, a, self._mul())
        return a

    def _mul(self):
        a = self._unary()
        while self._peek() in ("*", "/", "%", "**"):
            op = self._next()
            a = binop(op, a, self._unary())
        return a

    def _unary(self):
        t = self._peek()
        if t in ("-", "+", "~", "!"):
            self._next()
            v = self._unary()
            s = as_set(v)
            if s is None:
                raise Unresolved("一元运算不可枚举")
            if t == "-":
                return vset([(-x) & 0xFFFFFFFF for x in s])
            if t == "+":
                return v
            if t == "~":
                return vset([(~x) & 0xFFFFFFFF for x in s])
            return vset([0 if x != 0 else 1 for x in s])
        return self._primary()

    def _primary(self):
        t = self._next()
        if t == "(":
            v = self._ternary()
            if self._next() != ")":
                raise Unresolved("括号不匹配")
            return v
        if re.match(r"^(?:\d+)?'[sS]?[bBoOdDhH]", t) or re.match(r"^\d", t) \
                or t.lower().startswith("0x"):
            return vc(sv_int(t))
        if re.match(r"^[A-Za-z_]\w*$", t):
            if t in self.env:
                return self.env[t]
            raise Unresolved("未绑定符号:%s" % t)
        raise Unresolved("未识别 token:%s" % t)


def eval_expr(expr, env, macros):
    """求值：先展开宏，再解析。未绑定/不可解析抛 Unresolved。"""
    e = expand_macros(expr, macros).strip()
    if not e:
        raise Unresolved("空表达式")
    return Evaluator(env).ev(e)


# ------------------------------------------------------------------ 段表

# 首版 8 段（06 §0.3 / 09 §A.1）。ends = 该段最高可命中地址（含）。
SEGMENTS = [
    dict(seg_id="0x0000", name="全局寄存器", base=0x0000, ends=0x00FC,
         stride=None, controllers=None, coverage="partial", doc_registered=True,
         tb_macro=None,
         note="BAR0 总表 0x0000~0x00FC（文档 L389）；RTL 在 sys_reg.v 模块级译码"),
    dict(seg_id="0x0100", name="DFX", base=0x0100, ends=0x01FC,
         stride=None, controllers=None, coverage="full", doc_registered=True,
         tb_macro=None,
         note="BAR0 总表 0x0100~0x01FC（文档 L390）；DFX 版本复位值文档与 RTL 双向印证"),
    dict(seg_id="0x0600", name="QSFP LED", base=0x0600, ends=0x06FC,
         stride=None, controllers=None, coverage="partial", doc_registered=True,
         tb_macro=None,
         note="BAR0 总表 0x0600~0x06FC（文档 L391）；位定义只覆盖 0x600，且文档只写 32 端口"),
    dict(seg_id="0x0800", name="UART", base=0x0800, ends=0x09FC,
         stride="0x20", controllers=4, coverage="partial", doc_registered=True,
         tb_macro="UART_BASE_ADDR/UART_OFFSET",
         note="BAR0 总表 0x0800~0x09FC（文档 L392）；段头 Offset 0x0F00 是笔误（C23）"),
    dict(seg_id="0x0A00", name="在线升级", base=0x0A00, ends=0x0BFC,
         stride=None, controllers=None, coverage="full", doc_registered=True,
         tb_macro="UPT_SPI_ADDR",
         note="BAR0 总表 0x0A00~0x0BFC（文档 L393）；RTL 把 0x0A00/0x0B00 两个 0x100 段合并给 upt"),
    dict(seg_id="0x0D00", name="PCIE debug", base=0x0D00, ends=0x0DFC,
         stride=None, controllers=None, coverage="full", doc_registered=True,
         tb_macro="PCIE_BASE_ADDR",
         note="BAR0 总表 0x0D00~0x0DFC（文档 L395）；RTL 模块级 pcie_register BLOCK_ADDR=8'h0d"),
    dict(seg_id="0x2000", name="RTC I2C Master", base=0x2000, ends=0x33FC,
         stride="0x200", controllers=10, coverage="partial", doc_registered=True,
         tb_macro="FPGA_OT9548_ADDR/RTC_OFFSET（FPGA_IN9548_ADDR 宏错写 0x3800）",
         note="每控制器 stride 0x200，+0x00~+0x1FC；10 台 = 0x2000..0x3200（文档 L747）"),
    dict(seg_id="0x4000", name="DOM RTC/Polling", base=0x4000, ends=0x7FFC,
         stride="0x400", controllers=8, coverage="full", doc_registered=True,
         tb_macro="DOME_RTC_ADDR/DOME_RTC_OFFSET",
         note="RTL 只实现 8 台引擎 0x4000~0x5FFF（文档段头 0x4000—0x7ffc 见 C41）"),
    dict(seg_id="0x8000", name="DOME_PLREG_ADDR", base=0x8000, ends=None,
         stride=None, controllers=None, coverage="marked-only", doc_registered=False,
         tb_macro="DOME_PLREG_ADDR",
         note="三方皆缺：文档无登记、RTL 无有效译码（仅已停用注释），仅 TB 自造宏 → 只打标记不建映射"),
    dict(seg_id="0x10000", name="DOME_PLRAM_ADDR", base=0x10000, ends=0x1FFFF,
         stride="0x400", controllers=None, coverage="missing", doc_registered=False,
         tb_macro="DOME_PLRAM_ADDR",
         note="仅 RTL 有：DOM_RAM_ADD_START/STOP='h10000/'h1ffff（文档未登记）→ 只打标记不建映射"),
]

DOC_SEGS = [s for s in SEGMENTS if s["doc_registered"]]
MARKED_SEGS = [s for s in SEGMENTS if not s["doc_registered"]]


def seg_out(seg_id):
    """schema 要求 seg_id/base 小写（^0x[0-9a-f]{4,5}$）；站点 segment 与之一致以便 join。"""
    return seg_id.lower() if seg_id else None


def addr_segment(addr):
    """返回命中段的 seg_id；不在任何已登记段内返回 None。"""
    for s in DOC_SEGS:
        if s["base"] <= addr <= s["ends"]:
            return s["seg_id"]
    return None


def addr_marked(addr):
    for s in MARKED_SEGS:
        if s["ends"] is None:
            if addr == s["base"]:
                return s["seg_id"]
        elif s["base"] <= addr <= s["ends"]:
            return s["seg_id"]
    return None


# ------------------------------------------------------------------ 扫描

TASK_DECL_RE = re.compile(
    r"\b(?:task|function)\b\s+(.*?)\s*\(", re.S)
ENDFUNC_RE = re.compile(r"^\s*end(?:task|function)\b")
KEYWORDS = set(
    "task function endtask endfunction begin end if else for while repeat forever "
    "case endcase fork join join_any join_none return assign initial always wait "
    "module endmodule class endclass program package localparam parameter "
    "assign always_comb always_ff posedge negedge".split())


class Site(object):
    __slots__ = ("case", "file", "line", "callee", "expr", "env", "scope",
                 "bucket", "addr", "range", "segment", "in_doc", "align_ok",
                 "unresolved_reason", "addrs")

    def __init__(self, case, file, line, callee, expr, env, scope):
        self.case = case
        self.file = file
        self.line = line
        self.callee = callee
        self.expr = expr
        self.env = env
        self.scope = scope
        self.bucket = None
        self.addr = None
        self.range = None
        self.segment = None
        self.in_doc = None
        self.align_ok = None
        self.unresolved_reason = None
        self.addrs = None


class Scope(object):
    __slots__ = ("name", "formals", "env")

    def __init__(self, name, formals):
        self.name = name
        self.formals = list(formals)
        self.env = {}
        for f in formals:
            self.env[f] = UNK


def parse_decl(line):
    """从 task/function 声明行取 (name, formals)。"""
    m = TASK_DECL_RE.search(line)
    if not m:
        return None, []
    head = m.group(1)
    nm = re.search(r"([A-Za-z_]\w*)\s*$", head)
    if not nm:
        return None, []
    name = nm.group(1)
    # 取参数括号内容
    start = m.end()
    depth = 1
    i = start
    while i < len(line) and depth > 0:
        if line[i] == "(":
            depth += 1
        elif line[i] == ")":
            depth -= 1
        i += 1
    inner = line[start:i - 1]
    formals = []
    for part in split_args(inner):
        p = part.split("=")[0].strip()
        p = p.split("::")[-1].strip()
        nm2 = re.findall(r"([A-Za-z_]\w*)", p)
        if nm2:
            formals.append(nm2[-1])
    return name, formals


def formal_name(text):
    s = text.split("=")[0].strip()
    m = TYPE_PREFIX_RE.match(s)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Za-z_]\w*)$", s)
    return m.group(1) if m else None


FOR_RE = re.compile(r"\bfor\s*\(")


def collect_file_loops(lines, macros):
    """09 §B.0：`for` 循环变量按**该文件内** `for(...)` 头推断的取值范围展开枚举。

    预扫全部 `for` 头，同名变量取 min(lo)/max(hi) 合并（跨任务共享），
    得到文件级取值域表；站点求值时先看顺序扫描得到的变量表，未绑定则回落到本表。
    """
    ranges = {}
    for (_a, _b, line) in logical_lines(lines):
        for m in FOR_RE.finditer(line):
            start = m.end() - 1
            depth = 0
            i = start
            while i < len(line):
                if line[i] == "(":
                    depth += 1
                elif line[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if depth != 0:
                continue
            header = line[start + 1:i]
            r = parse_for_range(header, {}, macros)
            if r is None:
                continue
            var, lo, hi, st = r
            if var in ranges:
                plo, phi, pst = ranges[var]
                lo = min(lo, plo)
                hi = max(hi, phi)
                if st != pst:
                    st = 1
            ranges[var] = (lo, hi, st)
    return dict((v, vrange(lo, hi, st)) for v, (lo, hi, st) in ranges.items())


def parse_for_range(header, env, macros):
    """解析 for(...) 头 → (var, lo, hi, step) 或 None。"""
    parts = split_top(header, sep=";")
    if len(parts) != 3:
        return None
    init, cond, step = parts
    mi = re.search(r"([A-Za-z_]\w*)\s*=\s*(.+)$", init.strip(), re.S)
    if not mi:
        return None
    # 09 §B.0 只对 `for(int VAR = ...)` 这类头做范围推断；
    # `for(bit[31:0] i = ...)` 不推断取值域（其站点按「无法还原」计 B3，不猜）。
    head_init = init.strip()
    mt = re.match(r"^\s*([A-Za-z_]\w*(?:::\w+)*)?\s*(?:\[[^\]]*\]\s*)*"
                  r"([A-Za-z_]\w*)\s*=", head_init)
    if (not LOOP_TYPE_ANY) and mt and mt.group(1) is not None \
            and mt.group(1) not in ("int", "integer"):
        return None
    var = mi.group(1)
    cond_e = expand_macros(cond.strip(), macros)
    mc = re.match(r"^\s*%s\s*(<=|<)\s*(.+)$" % re.escape(var), cond_e, re.S)
    if not mc:
        return None
    lo_v = mi.group(2)
    try:
        v_lo = eval_expr(lo_v, env, macros)
        v_hi = eval_expr(mc.group(2), env, macros)
    except Unresolved:
        return None
    if v_lo[0] != "c" or v_hi[0] != "c":
        return None
    step_e = step.strip()
    ms = re.match(r"^(?:%s\s*(\+\+|--)|(\+\+|--)\s*%s)$"
                  % (re.escape(var), re.escape(var)), step_e)
    if ms:
        st = 1 if (ms.group(1) or ms.group(2)) == "++" else -1
    else:
        ms = re.match(r"^%s\s*=\s*%s\s*([+\-])\s*(.+)$" % (re.escape(var), re.escape(var)),
                      step_e, re.S)
        if not ms:
            return None
        try:
            v_st = eval_expr(ms.group(2), env, macros)
        except Unresolved:
            return None
        if v_st[0] != "c":
            return None
        st = v_st[1] if ms.group(1) == "+" else -v_st[1]
    if st <= 0:
        return None
    lo, hi = v_lo[1], v_hi[1]
    if mc.group(1) == "<":
        if hi <= lo:
            return None
        hi = lo + ((hi - lo - 1) // st) * st
    else:
        if hi < lo:
            return None
        hi = lo + ((hi - lo) // st) * st
    cnt = (hi - lo) // st + 1
    if cnt > 1 << 24:
        return None
    return var, lo, hi, st


ASSIGN_RE = re.compile(
    r"(?<![=!<>+\-*/%&|^])\b([A-Za-z_]\w*)\s*(\[[^\[\]]*\])?\s*=(?!=)")


def merge_env(env, loops, formals=()):
    """顺序扫描变量表 + 文件级 for 取值域表：变量表里的**已知值**优先，未知则回落 for 表。

    形参（task/function 的 formal）**不**走 for 表回落 —— 形参只能靠调用点回填，
    否则 `set_write(..., addr, ...)` 这种与 callee 同名的任务体会被别的任务的
    `for(int addr...)` 误绑（09 §B.0 明确要求排除）。
    """
    e = {}
    for k, v in env.items():
        if v[0] != "u":
            e[k] = v
    for k, v in (loops or {}).items():
        if k in formals:
            continue
        e[k] = v
    return e


def scan_file(path, case, macros):
    """扫描一个用例文件 → (sites, diag)"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    text = strip_comments(raw)
    lines = text.split("\n")
    local_macros = dict(macros)
    local_macros.update(parse_defines(text))
    file_loops = collect_file_loops(lines, local_macros) if LOOPVAR_PREPASS else {}

    file_sites = []
    all_calls = []
    scopes = []          # 本文件所有 task/function scope
    task_formals = {}    # name -> formals（首次声明）
    file_env = {}        # 文件级变量表
    stack = []           # scope 栈
    env = file_env

    for (lno, lno_end, raw_line) in logical_lines(lines):
        line = raw_line
        if not line.strip():
            continue
        if ENDFUNC_RE.match(line):
            if stack:
                stack.pop()
            env = stack[-1].env if stack else file_env
            continue
        mdecl = re.match(r"^\s*(?:(?:virtual|automatic|local|protected|static|extern)\s+)*"
                         r"(?:task|function)\b", line)
        if mdecl:
            name, formals = parse_decl(line)
            sc = Scope(name, formals)
            scopes.append(sc)
            if name and name not in task_formals:
                task_formals[name] = formals
            stack.append(sc)
            env = sc.env
            continue

        work = line
        # ---- for 循环头：先解析取值域（并把该段从后续处理中挖空）
        for m in list(FOR_RE.finditer(work)):
            start = m.end() - 1
            depth = 0
            i = start
            while i < len(work):
                if work[i] == "(":
                    depth += 1
                elif work[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if depth != 0:
                continue
            header = work[start + 1:i]
            r = parse_for_range(header, env, local_macros)
            if r is not None:
                var, lo, hi, st = r
                env[var] = vrange(lo, hi, st)
            work = work[:start + 1] + " " * (i - start - 1) + work[i:]

        # ---- 逐语句：赋值 + 调用
        for stmt in split_top(work, sep=";"):
            s = stmt.strip()
            if not s:
                continue
            # 赋值
            for ma in list(ASSIGN_RE.finditer(s)):
                var = ma.group(1)
                if var in KEYWORDS:
                    continue
                rhs_start = ma.end()
                rhs = s[rhs_start:]
                rhs = rhs.split(";")[0]
                if ma.group(2):      # 位选/域选赋值 → 不可判
                    if not KEEP_PARTIAL:
                        env[var] = UNK
                    continue
                if not rhs.strip():
                    continue
                try:
                    env[var] = eval_expr(rhs, env, local_macros)
                except Unresolved as e:
                    if not KEEP_UNRESOLVED:
                        env[var] = ("u", e.reason)
            # 调用
            for mc in CALLEE_RE.finditer(s):
                callee = mc.group(1)
                j = mc.end() - 1
                depth = 0
                k = j
                while k < len(s):
                    if s[k] == "(":
                        depth += 1
                    elif s[k] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                args = split_args(s[j + 1:k])
                if not args:
                    continue
                idx = 0
                if SEQ_ARG_RE.match(args[0].strip()):
                    idx = 1
                if idx >= len(args):
                    continue
                aexpr = args[idx].strip()
                # 剔除实参里的数据类型名
                fn = formal_name(aexpr)
                if fn and re.search(r"\b(bit|logic|int|integer|output|input|ref)\b", aexpr):
                    aexpr = fn
                sc_now = stack[-1] if stack else None
                site = Site(case, kb_lib.relpath(path), lno, callee, aexpr,
                            merge_env(env, file_loops,
                                      sc_now.formals if sc_now else ()),
                            sc_now)
                file_sites.append(site)
            # 记录对本文件内 task 的调用（供形参回填）
            for mc in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", s):
                nm = mc.group(1)
                if nm in KEYWORDS or nm in CALLEES:
                    continue
                j = mc.end() - 1
                depth = 0
                k = j
                while k < len(s):
                    if s[k] == "(":
                        depth += 1
                    elif s[k] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                    k += 1
                sc_now = stack[-1] if stack else None
                all_calls.append(dict(name=nm, args=split_args(s[j + 1:k]),
                                      env=merge_env(env, file_loops,
                                                    sc_now.formals if sc_now else ()),
                                      line=lno, scope=sc_now))
    return file_sites, all_calls, scopes, task_formals


def merge_values(vals):
    if not vals:
        return UNK
    first = vals[0]
    if all(v == first for v in vals):
        return first
    if all(v[0] == "c" for v in vals):
        return vset(sorted(set(v[1] for v in vals)))
    sets = [as_set(v) for v in vals]
    if all(s is not None for s in sets):
        total = set()
        for s in sets:
            total |= s
        if len(total) <= ENUM_LIMIT:
            return vset(sorted(total))
        return vrange(min(total), max(total), 1)
    rs = [as_range(v) for v in vals]
    if all(r is not None for r in rs):
        lo = min(r[0] for r in rs)
        hi = max(r[1] for r in rs)
        step = rs[0][2]
        if all(r[2] == step for r in rs):
            return vrange(lo, hi, step)
    return UNK


def resolve_sites(file_sites, all_calls, scopes, task_formals, macros):
    """任务形参回填（所有调用点都可解析时），迭代到不动点。"""
    by_name = collections.defaultdict(list)
    for c in all_calls:
        by_name[c["name"]].append(c)
    scope_of = {}
    for sc in scopes:
        scope_of.setdefault(sc.name, []).append(sc)

    def env_of(snap, scope):
        # 调用点实参在调用者的顺序扫描变量表里求值；BACKFILL_CHAIN=True 时把调用者
        # 已被回填的形参也带进来（跨任务形参链式传递）。
        if not BACKFILL_CHAIN:
            return dict(snap)
        e = dict(snap)
        if scope is not None:
            for f in scope.formals:
                if f in scope.env and scope.env[f][0] != "u":
                    e[f] = scope.env[f]
        return e

    # 09 §B.0：任务形参只在**所有调用点都能解析**时才回填。
    # 只判「出现在本任务站点地址表达式里」的形参；站点地址表达式里看不到任何形参时，
    # 退化为按该任务全部形参尝试回填。
    needed = collections.defaultdict(set)
    for site in file_sites:
        if site.scope is None:
            continue
        for f in site.scope.formals:
            if re.search(r"\b%s\b" % re.escape(f), site.expr):
                needed[site.scope.name].add(f)

    for _ in range(6):
        changed = False
        for tname, formals in task_formals.items():
            if not formals or tname in NO_BACKFILL or tname not in by_name:
                continue
            want = sorted(needed.get(tname) or set(formals))
            if not want:
                continue
            calls = by_name[tname]
            per_formal = collections.OrderedDict((f, []) for f in formals)
            ok = True
            for c in calls:
                e = env_of(c["env"], c["scope"])
                for i, f in enumerate(formals):
                    if f not in want:
                        continue
                    if i >= len(c["args"]):
                        ok = False
                        break
                    try:
                        v = eval_expr(c["args"][i], e, macros)
                    except Unresolved:
                        ok = False
                        break
                    if v[0] == "u":
                        ok = False
                        break
                    per_formal[f].append(v)
                if not ok:
                    break
            if not ok:
                continue
            for sc in scope_of.get(tname, []):
                for f in want:
                    mv = merge_values(per_formal[f])
                    if mv[0] == "u":
                        continue
                    if sc.env.get(f) != mv:
                        sc.env[f] = mv
                        changed = True
        if not changed:
            break

    for site in file_sites:
        e = dict(site.env)
        sc = site.scope
        if sc is not None:
            for f in sc.formals:
                if f in sc.env and sc.env[f][0] != "u":
                    e[f] = sc.env[f]
        site.env = e


def classify_sites(file_sites, macros):
    for site in file_sites:
        try:
            v = eval_expr(site.expr, site.env, macros)
        except Unresolved as e:
            v = ("u", e.reason)
        if v[0] == "c":
            site.bucket = "B1"
            site.addrs = [v[1]]
            site.addr = "0x%x" % v[1]
        elif v[0] == "s":
            site.bucket = "B1"
            site.addrs = sorted(v[1])
            site.addr = "0x%x" % site.addrs[0] if len(site.addrs) == 1 else None
        elif v[0] == "r":
            site.bucket = "B2"
            site.range = ["0x%x" % v[1], "0x%x" % v[2]]
        else:
            site.bucket = "B3"
            site.unresolved_reason = v[1] or "unknown"
        if site.addrs:
            # 站点归段：按最小（首个）地址判段；有限枚举跨越段边界时以首地址为准。
            site.segment = addr_segment(site.addrs[0])
            site.in_doc = site.segment is not None
            site.align_ok = all(a % 4 == 0 for a in site.addrs)
    return file_sites


# ------------------------------------------------------------------ 段 ↔ RTL
# 09 §A.0/§A.1 的 RTL 证据；每条 expect 是本轮 grep 复验要命中的基址常量。
RTL_TOP = "RTL/SRC/imports/SRC/TCS9620_MAC_TOP.v"
RTL_SYS = "RTL/SRC/imports/SRC/reg/sys_reg.v"
RTL_DFX = "RTL/SRC/imports/SRC/reg/dfx_debug_reg.sv"
RTL_CLK = "RTL/SRC/imports/SRC/reg/common_aligned_time_static.sv"
RTL_PCIE = "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v"

SEG_RTL = {
    "0x0000": [
        dict(path=RTL_TOP, lines="701,752", level="top-level-decode",
             expect=None, active=False,
             why="一级译码只按 bit[31:8] 兜底：<=24'ha 或 >24'hb 且 !=24'h08 走 sys 路，"
                 "本条不含 0x00 显式判决（09 §A.0）"),
        dict(path=RTL_SYS, lines="538", level="module-level", expect="32'h00", active=True,
             why="sys_reg 模块级译码 0x00~0x0C 等全局寄存器读回"),
        dict(path=RTL_SYS, lines="555", level="module-level", expect="32'h00", active=True,
             why="sys_reg 有效区间 0x00~0x23 / 0x4C~0x73"),
    ],
    "0x0100": [
        dict(path=RTL_TOP, lines="701,752", level="top-level-decode",
             expect=None, active=False,
             why="落 sys 兜底，无 0x01 独立判决（09 §A.0）"),
        dict(path=RTL_CLK, lines="101", level="module-level", expect="24'h1", active=True,
             why="common_aligned_time_static：sc_dcb_addr[31:8]==24'h1 命中 0x100~0x1FC"),
        dict(path=RTL_DFX, lines="554", level="module-level", expect="32'h25092913",
             active=True,
             why="DFX 版本复位值 25092913 与文档 L620 完全一致"),
    ],
    "0x0600": [
        dict(path=RTL_TOP, lines="691,696", level="top-level-decode", expect="24'h06",
             active=False,
             why="dcb 侧 0x06 判决已被整段注释停用（09 §A.0），故 dcb 走 sys 兜底"),
        dict(path=RTL_TOP, lines="780", level="module-level", expect="'h6", active=True,
             why="CPU 侧独立命中：cpld_dcb_req = cpu_addr[31:8]=='h6 送 qsfp_top"),
    ],
    "0x0800": [
        dict(path=RTL_TOP, lines="684", level="top-level-decode", expect="24'h08",
             active=True, why="一级译码 uart_sel：dcb_addr[31:8]==24'h08"),
        dict(path=RTL_TOP, lines="687", level="top-level-decode", expect="24'h08",
             active=True, why="一级译码 uart_dcb_req：dcb_addr[31:8]==24'h08"),
        dict(path=RTL_TOP, lines="689", level="module-level", expect="uart_dcb_addr",
             active=False, why="地址直通 uart_dcb_addr = dcb_addr（本条不含基址常量）"),
    ],
    "0x0A00": [
        dict(path=RTL_TOP, lines="663", level="top-level-decode", expect="24'ha",
             active=True, why="一级译码 s_upt_sel：dcb_addr[31:8]==24'ha||24'hb"),
        dict(path=RTL_TOP, lines="680", level="top-level-decode", expect="24'ha",
             active=True, why="一级译码 upt_dcb_req：dcb_addr[31:8]==24'ha||24'hb"),
        dict(path=RTL_TOP, lines="682", level="module-level", expect="upt_dcb_addr",
             active=False, why="地址变换 upt_dcb_addr = {7'd0,dcb_addr[8:2]}"),
    ],
    "0x0D00": [
        dict(path=RTL_TOP, lines="701,752", level="top-level-decode",
             expect=None, active=False,
             why="落 sys 兜底，无 0x0D 独立判决（09 §A.0）"),
        dict(path=RTL_PCIE, lines="104", level="module-level", expect="8'h0d", active=True,
             why="pcie_register：parameter BLOCK_ADDR = 8'h0d"),
        dict(path=RTL_PCIE, lines="161", level="module-level", expect="BLOCK_ADDR",
             active=False, why="段命中判据 s_hit_me = (dcb_addr[15:8] == BLOCK_ADDR)"),
    ],
    "0x2000": [
        dict(path=RTL_TOP, lines="701,752", level="top-level-decode",
             expect=None, active=False,
             why="落 sys 兜底，无 0x20 独立判决（09 §A.0）"),
        dict(path=RTL_TOP, lines="201", level="module-level", expect="'h2000", active=True,
             why="localparam OUT_9548_I2C_ADDR = 'h2000"),
        dict(path=RTL_TOP, lines="202", level="module-level", expect="'h200", active=True,
             why="localparam OUT_9548_I2C_OFFSET = 'h200（stride）"),
        dict(path=RTL_TOP, lines="1307", level="module-level", expect="IN_9548_I2C_OFFSET",
             active=False, why="第 10 台控制器基址 CPU_REG_BASE_ADDR = OUT+OFFSET*k（k=9）→0x3200"),
    ],
    "0x4000": [
        dict(path=RTL_TOP, lines="701,752", level="top-level-decode",
             expect=None, active=False,
             why="落 sys 兜底，无 0x40 独立判决（09 §A.0）"),
        dict(path=RTL_TOP, lines="206", level="module-level", expect="'h4000", active=True,
             why="localparam DOM_I2C_ADDR = 'h4000"),
        dict(path=RTL_TOP, lines="207", level="module-level", expect="'h400", active=True,
             why="localparam DOM_I2C_OFFSET = 'h400（stride）"),
        dict(path=RTL_TOP, lines="1370", level="module-level", expect="DOM_I2C_ADDR",
             active=False, why="CPU_REG_BASE_ADDR = DOM_I2C_ADDR + DOM_I2C_OFFSET*m（m<8）"),
    ],
}


def verify_rtl_entry(entry):
    """本轮 grep 复验：读 file:line 原文，确认含该基址常量。"""
    path = os.path.join(ROOT, entry["path"])
    out = dict(entry)
    out.pop("expect", None)
    out.pop("active", None)
    out.pop("why", None)
    evid = []
    ok = False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        src = f.read().split("\n")
    for tok in str(entry["lines"]).split(","):
        tok = tok.strip()
        if not tok.isdigit():
            continue
        n = int(tok)
        line = src[n - 1].strip() if 0 < n <= len(src) else ""
        evid.append("%s:%d: %s" % (entry["path"], n, line))
        if entry["expect"] and entry["expect"] in line:
            ok = True
    out["verified"] = bool(ok and entry["active"])
    # evidence_text 只放**复验命中的原文**（schema 只允许 path/lines/level/verified/evidence_text）
    out["evidence_text"] = " | ".join(evid)
    return out


# ------------------------------------------------------------------ 主体

def collect(macros, diag_dir=None):
    files = sorted(glob.glob(os.path.join(TESTLIB_DIR, "*.sv")))
    all_sites = []
    cases = []
    for path in files:
        case = os.path.splitext(os.path.basename(path))[0]
        fsites, calls, scopes, formals = scan_file(path, case, macros)
        resolve_sites(fsites, calls, scopes, formals, macros)
        classify_sites(fsites, macros)
        all_sites += fsites
        raw = open(path, "rb").read()
        cases.append(dict(
            case=case, file=kb_lib.relpath(path),
            md5=kb_lib.md5_file(path), bytes=len(raw),
            lines=raw.count(b"\n")))
    all_sites.sort(key=lambda s: (s.file, s.line, s.callee, s.expr))
    return files, all_sites, cases


def bucket_stats(sites):
    b = collections.Counter(s.bucket for s in sites)
    b1 = [s for s in sites if s.bucket == "B1"]
    uniq = set()
    for s in b1:
        if s.addrs:
            # 「B1 去重地址数」：每个站点取代表地址（有限枚举取最小地址）再去重
            uniq.add(s.addrs[0])
    in_doc = sum(1 for s in b1 if s.in_doc)
    return dict(B1=b["B1"], B2=b["B2"], B3=b["B3"], total=len(sites),
                B1_unique_addrs=len(uniq), B1_in_doc=in_doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只打印统计不写盘")
    ap.add_argument("--diag", default=None, help="诊断输出目录")
    args = ap.parse_args()

    macros = load_macro_table()
    files, sites, cases = collect(macros)

    stats = bucket_stats(sites)
    print("== 三桶（09 §B.0/§B.1）==")
    print("B1=%d B2=%d B3=%d total=%d" % (stats["B1"], stats["B2"], stats["B3"],
                                          stats["total"]))
    print("B1_unique_addrs=%d B1_in_doc=%d" % (stats["B1_unique_addrs"],
                                               stats["B1_in_doc"]))
    if stats["total"]:
        print("可静态解析 %d/%d = %.1f%%" % (stats["B1"] + stats["B2"], stats["total"],
                                            100.0 * (stats["B1"] + stats["B2"]) / stats["total"]))
    if stats["B1"]:
        print("B1 in_doc %d/%d = %.1f%%" % (stats["B1_in_doc"], stats["B1"],
                                            100.0 * stats["B1_in_doc"] / stats["B1"]))
    dist = collections.Counter()
    for s in sites:
        if s.bucket == "B1":
            dist[s.segment if s.segment else "段外"] += 1
    print("== B1 段分布 ==")
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
        print("  %-8s %d" % (k, v))
    print("== B2 范围分布 ==")
    rd = collections.Counter()
    for s in sites:
        if s.bucket == "B2":
            rd["~".join(s.range)] += 1
    for k, v in sorted(rd.items(), key=lambda kv: -kv[1]):
        print("  %-24s %d" % (k, v))
    print("== B3 Top 表达式 ==")
    h = collections.Counter(s.expr for s in sites if s.bucket == "B3")
    for k, v in h.most_common(10):
        print("  %5d  %s" % (v, k))

    if args.diag:
        os.makedirs(args.diag, exist_ok=True)
        kb_lib.write_json(os.path.join(args.diag, "diag_stats.json"), dict(
            buckets=stats,
            b1_seg_dist=dict(dist),
            b2_ranges=dict(rd),
            b3_top=[{"expr": k, "n": v} for k, v in h.most_common(40)],
            b1_top_addr=collections.Counter(
                "%s" % s.addr for s in sites if s.bucket == "B1").most_common(40),
        ))
        kb_lib.write_csv(os.path.join(args.diag, "diag_sites.csv"),
                         ["file", "line", "callee", "expr", "bucket", "addr",
                          "range", "segment", "in_doc", "reason"],
                         [[s.file, s.line, s.callee, s.expr, s.bucket,
                           s.addr or "", ",".join(s.range) if s.range else "",
                           s.segment or "", s.in_doc, s.unresolved_reason or ""]
                          for s in sites])
    if args.check:
        return

    # ---------------- 写索引 ----------------
    access_obj = dict(
        schema="kb/index/case_access", version=1, buckets=stats,
        sites=[dict(case=s.case, file=s.file, line=s.line, callee=s.callee,
                    addr_expr=s.expr, addr=s.addr, range=s.range, bucket=s.bucket,
                    segment=seg_out(s.segment), in_doc=s.in_doc, align_ok=s.align_ok,
                    unresolved_reason=s.unresolved_reason) for s in sites])
    kb_lib.check(access_obj, "index")
    kb_lib.write_json(kb_lib.kb_path("index", "case_access.json"), access_obj)
    kb_lib.write_csv(
        kb_lib.kb_path("index", "case_access.csv"),
        ["case", "file", "line", "callee", "addr_expr", "addr", "range_lo", "range_hi",
         "bucket", "segment", "in_doc", "align_ok", "unresolved_reason"],
        [[s.case, s.file, s.line, s.callee, s.expr, s.addr or "",
          (s.range[0] if s.range else ""), (s.range[1] if s.range else ""),
          s.bucket, seg_out(s.segment) or "",
          "" if s.in_doc is None else ("true" if s.in_doc else "false"),
          "" if s.align_ok is None else ("true" if s.align_ok else "false"),
          s.unresolved_reason or ""] for s in sites])

    by_case = collections.defaultdict(list)
    for s in sites:
        by_case[s.case].append(s)
    out_cases = []
    for c in cases:
        ss = by_case.get(c["case"], [])
        segs = sorted(set(seg_out(s.segment) for s in ss
                          if s.bucket == "B1" and s.segment))
        out_cases.append(dict(c, access_sites=len(ss),
                              B1_sites=sum(1 for s in ss if s.bucket == "B1"),
                              segments_hit=segs))
    out_cases.sort(key=lambda c: c["file"])
    cases_obj = dict(schema="kb/index/cases", version=1,
                     frozen_dir="TESTLIB", cases=out_cases)
    kb_lib.check(cases_obj, "index")
    kb_lib.write_json(kb_lib.kb_path("index", "cases.json"), cases_obj)

    seg_b1 = collections.Counter()
    for s in sites:
        if s.bucket == "B1" and s.segment:
            seg_b1[s.segment] += 1
    segs_obj = dict(
        schema="kb/index/segments", version=1,
        note="首版 8 段 coverage=full/partial（doc_registered=true）；"
             "0x8000（文档与 RTL 双侧无依据）标 marked-only、0x10000（仅 RTL 有译码）标 "
             "missing，二者 doc_registered=false 且**只打标记不建映射**（spec §10.3）。"
             "cases_static = 本段 B1 定向访问站点数，由 n1_case_scan.py 扫描填入（禁手算）；"
             "B1 站点按代表地址（有限枚举取最小地址）归段，未落进 8 个已登记段的记 段外。"
             "段范围取文档 BAR0 总表/段头（06 §0.3、09 §A.1）：0x0000~0x00FC、0x0100~0x01FC、"
             "0x0600~0x06FC、0x0800~0x09FC、0x0A00~0x0BFC、0x0D00~0x0DFC、"
             "0x2000+0x200*k(k=0..9)+0x1FC=0x33FC、0x4000~0x7FFC（文档段头，RTL 实际 8 台）。",
        segments=[dict(
            seg_id=seg_out(s["seg_id"]), name=s["name"], base=seg_out(s["seg_id"]),
            ends=("0x%x" % s["ends"]) if s["ends"] is not None else s["seg_id"],
            stride=s["stride"], controllers=s["controllers"],
            doc_registered=s["doc_registered"], coverage=s["coverage"],
            rtl_evidence=[
                "%s:%s" % (e["path"], e["lines"])
                for e in SEG_RTL.get(s["seg_id"], []) if e["active"]],
            tb_macro=s["tb_macro"], cases_static=seg_b1.get(s["seg_id"], 0),
            note=s["note"]) for s in SEGMENTS])
    kb_lib.check(segs_obj, "index")
    kb_lib.write_json(kb_lib.kb_path("index", "segments.json"), segs_obj)

    mappings = []
    for s in SEGMENTS:
        if not s["doc_registered"]:
            continue
        entries = [verify_rtl_entry(e) for e in SEG_RTL.get(s["seg_id"], [])]
        whys = "; ".join("%s:%s %s -> %s" % (
            e["path"], e["lines"], e["level"],
            "verified" if ent["verified"] else "未标 verified（原文不含有效基址常量判决）")
            for e, ent in zip(SEG_RTL.get(s["seg_id"], []), entries))
        mappings.append(dict(segment=seg_out(s["seg_id"]), rtl_files=entries,
                             tb_macro=s["tb_macro"],
                             note=s["note"] + " || " + whys))
    rtl_obj = dict(schema="kb/index/segment_rtl", version=1, mappings=mappings)
    kb_lib.check(rtl_obj, "index")
    kb_lib.write_json(kb_lib.kb_path("index", "segment_rtl.json"), rtl_obj)

    nver = sum(1 for m in mappings for e in m["rtl_files"] if e["verified"])
    print("== 写盘完成 ==")
    print("cases=%d segment_rtl mappings=%d verified=%d"
          % (len(out_cases), len(mappings), nver))
    for m in mappings:
        print("  %s: %d entries, verified=%d"
              % (m["segment"], len(m["rtl_files"]),
                 sum(1 for e in m["rtl_files"] if e["verified"])))


if __name__ == "__main__":
    main()
