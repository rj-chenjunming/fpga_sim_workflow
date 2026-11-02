#!/usr/bin/env python3
"""独立复核器（复核员自写，不复用 loop/tests/test_ui_css_structure.py 的 load_structure，
也不 import .ui-audit/3c/merge_plan.py）。

做四件事：
 A. 独立解析 before/after 两份 app.css（括号深度 + 字符串/注释感知）。
 B. 「值未变」判据：对每个 (上下文, 简单选择器)，把该选择器在所有规则里的声明**按文档顺序串起来**，
    after 的串必须 == before 的串删掉「被同属性同重要性后置声明支配」的那些。字符串逐字比较。
 C. 「跨选择器顺序翻转」判据：按 longhand 展开，同一上下文同一 longhand 属性下，同特异性、同重要性
    的两个选择器，其生效声明的**文档先后**若在 before/after 之间翻转 ⇒ 可能改生效值；
    再用 cooccur-full.json 做 fail-closed 裁决（未覆盖 ⇒ 不算豁免）。
 D. 结构数字：重复组 / 简单选择器重复 / !important / @ 条件 / hex 多重集。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict

# ---------------------------------------------------------------- 解析
def strip_comments(s: str) -> str:
    out = list(s)
    i, n = 0, len(s)
    while i < n:
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def skip_string(t, i):
    q = t[i]
    i += 1
    while i < len(t):
        if t[i] == "\\":
            i += 2
            continue
        if t[i] == q:
            return i + 1
        i += 1
    return i


def block_end(t, open_i, end):
    d = 0
    i = open_i
    while i < end:
        c = t[i]
        if c in "\"'":
            i = skip_string(t, i)
            continue
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d == 0:
                return i
        i += 1
    raise SystemExit("花括号不平衡")


def parse_decls(t, i, end):
    out = []
    buf = []
    paren = 0
    while i < end:
        c = t[i]
        if c in "\"'":
            j = skip_string(t, i)
            buf.append(t[i:j])
            i = j
            continue
        if c in "([":
            paren += 1
        elif c in ")]":
            paren -= 1
        if c == ";" and paren == 0:
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    out.append("".join(buf))
    decls = []
    for chunk in out:
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        prop = prop.strip().lower()
        value = value.strip()
        imp = False
        m = re.search(r"!\s*important\s*$", value, re.I)
        if m:
            imp = True
            value = value[:m.start()].strip()
        decls.append((prop, value, imp))
    return decls


def split_top_commas(sel: str):
    parts, buf, depth = [], [], 0
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return [norm_sel(p) for p in parts if norm_sel(p)]


def norm_sel(s: str) -> str:
    return " ".join(s.split())


def parse_css(text: str):
    """→ rules: [{ctx, sel_list, decls, at}]，文档顺序。"""
    text = strip_comments(text)
    rules = []
    n = len(text)

    def walk(i, end, ctx):
        while i < end:
            while i < end and text[i] in " \t\r\n;":
                i += 1
            if i >= end:
                return
            if text[i] == "}":
                i += 1
                continue
            start = i
            paren = 0
            while i < end:
                c = text[i]
                if c in "\"'":
                    i = skip_string(text, i)
                    continue
                if c in "([":
                    paren += 1
                elif c in ")]":
                    paren -= 1
                elif c == "{" and paren == 0:
                    break
                i += 1
            prelude = text[start:i].strip()
            be = block_end(text, i, end)
            if prelude.startswith("@"):
                name = re.match(r"@[\w-]+", prelude).group(0).lower()
                if name in ("@media", "@supports", "@layer", "@container"):
                    walk(i + 1, be, ctx + (" ".join(prelude.split()),))
                # @keyframes / @font-face 等跳过
            else:
                rules.append({"ctx": ctx, "sel_list": split_top_commas(prelude),
                              "decls": parse_decls(text, i + 1, be)})
            i = be + 1

    walk(0, n, ())
    return rules


# ---------------------------------------------------- 是否「被支配」(同上下文同属性)
def shadowed_flags(decls):
    """decls: [(prop,value,imp)] 文档顺序 → 每条的 winner 判定（同属性、同上下文内）。"""
    last_imp = {}
    last_norm = {}
    for idx, (prop, _v, imp) in enumerate(decls):
        if imp:
            last_imp[prop] = idx
        else:
            last_norm[prop] = idx
    flags = []
    for idx, (prop, _v, imp) in enumerate(decls):
        win = last_imp.get(prop) if prop in last_imp else last_norm.get(prop)
        flags.append(idx == win)
    return flags


# ---------------------------------------------------------------- 简写展开
SIDES = ("top", "right", "bottom", "left")
CORNERS = ("top-left", "top-right", "bottom-right", "bottom-left")
EXPAND = {
    "margin": tuple("margin-" + s for s in SIDES),
    "padding": tuple("padding-" + s for s in SIDES),
    "inset": ("top", "right", "bottom", "left"),
    "gap": ("row-gap", "column-gap"),
    "overflow": ("overflow-x", "overflow-y"),
    "border-radius": tuple("border-%s-radius" % c for c in CORNERS),
    "border": tuple("border-%s-%s" % (s, k) for s in SIDES for k in ("width", "style", "color")),
    "border-color": tuple("border-%s-color" % s for s in SIDES),
    "border-width": tuple("border-%s-width" % s for s in SIDES),
    "border-style": tuple("border-%s-style" % s for s in SIDES),
    "background": ("background-color", "background-image", "background-position",
                   "background-size", "background-repeat", "background-clip",
                   "background-origin", "background-attachment", "background-blend-mode"),
    "font": ("font-family", "font-size", "font-weight", "font-style", "font-variant",
             "font-stretch", "line-height"),
    "flex": ("flex-grow", "flex-shrink", "flex-basis"),
    "outline": ("outline-width", "outline-style", "outline-color"),
    "place-items": ("align-items", "justify-items"),
    "text-decoration": ("text-decoration-line", "text-decoration-color",
                        "text-decoration-style", "text-decoration-thickness"),
    "transition": ("transition-property", "transition-duration",
                   "transition-timing-function", "transition-delay"),
    "animation": ("animation-name", "animation-duration", "animation-timing-function",
                  "animation-delay", "animation-iteration-count", "animation-direction",
                  "animation-fill-mode", "animation-play-state"),
    "grid-template": ("grid-template-rows", "grid-template-columns", "grid-template-areas"),
    "grid-column": ("grid-column-start", "grid-column-end"),
    "grid-row": ("grid-row-start", "grid-row-end"),
    "grid-area": ("grid-row-start", "grid-column-start", "grid-row-end", "grid-column-end"),
    "grid": ("grid-template-rows", "grid-template-columns", "grid-template-areas",
             "grid-auto-rows", "grid-auto-columns", "grid-auto-flow"),
    "flex-flow": ("flex-direction", "flex-wrap"),
    "scroll-margin": tuple("scroll-margin-" + s for s in SIDES),
    "scroll-padding": tuple("scroll-padding-" + s for s in SIDES),
}
for _s in SIDES:
    EXPAND["border-" + _s] = tuple("border-%s-%s" % (_s, k) for k in ("width", "style", "color"))
    EXPAND["border-" + _s + "-color"] = ("border-%s-color" % _s,)
    EXPAND["border-" + _s + "-width"] = ("border-%s-width" % _s,)
    EXPAND["border-" + _s + "-style"] = ("border-%s-style" % _s,)

COLORISH = re.compile(r"^(#[0-9a-fA-F]{3,8}|var\(|rgba?\(|hsla?\(|transparent$|current[Cc]olor$|"
                      r"inherit$|initial$|unset$|revert$|white$|black$|red$|none$)")


def longhand_map(prop: str, value: str):
    """返回 {longhand: value}；只为**比较对称性**服务（同文本 ⇒ 同展开）。"""
    if prop not in EXPAND:
        return {prop: f"{prop}={value}"}
    lh = EXPAND[prop]
    v = value.strip()
    if re.search(r"\b(inherit|initial|unset|revert|revert-layer)\b", v):
        return {p: f"{p}={v}" for p in lh}
    if prop in ("margin", "padding", "scroll-margin", "scroll-padding", "inset"):
        toks = split_ws(v)
        if 1 <= len(toks) <= 4:
            vals = expand_box(toks)
            names = ("top", "right", "bottom", "left") if prop == "inset" else \
                    ("-" + s for s in ("top", "right", "bottom", "left"))
            keys = SIDES if prop == "inset" else tuple(prop + "-" + s for s in SIDES)
            return {k: f"{k}={val}" for k, val in zip(keys, vals)}
        return {p: f"{p}={v}" for p in lh}
    if prop == "border-radius":
        toks = split_ws(v)
        if 1 <= len(toks) <= 4:
            vals = expand_box(toks)
            return {k: f"{k}={val}" for k, val in zip(
                tuple("border-%s-radius" % c for c in CORNERS), vals)}
        return {p: f"{p}={v}" for p in lh}
    if prop in ("gap", "overflow"):
        toks = split_ws(v)
        if len(toks) == 1:
            return {p: f"{p}={toks[0]}" for p in lh}
        if len(toks) == 2:
            return {lh[0]: f"{lh[0]}={toks[0]}", lh[1]: f"{lh[1]}={toks[1]}"}
        return {p: f"{p}={v}" for p in lh}
    if prop in ("flex", "flex-flow"):
        toks = split_ws(v)
        if len(toks) == 1 and toks[0] == "none":
            return {"flex-grow": "flex-grow=0", "flex-shrink": "flex-shrink=0",
                    "flex-basis": "flex-basis=auto"} if prop == "flex" else {p: f"{p}={v}" for p in lh}
        if prop == "flex" and 1 <= len(toks) <= 3:
            g = toks[0]
            s = toks[1] if len(toks) > 1 else "1"
            b = toks[2] if len(toks) > 2 else "0%"
            return {"flex-grow": f"flex-grow={g}", "flex-shrink": f"flex-shrink={s}",
                    "flex-basis": f"flex-basis={b}"}
        return {p: f"{p}={v}" for p in lh}
    if prop == "font":
        return expand_font(v)
    if prop == "background":
        if COLORISH.match(v) or re.fullmatch(r"var\([^)]*\)", v):
            return {"background-color": f"background-color={v}",
                    **{p: f"{p}=initial" for p in lh if p != "background-color"}}
        return {p: f"{p}={v}" for p in lh}
    if prop.startswith("border") and prop in EXPAND and len(lh) == 12:
        toks = split_ws(v)
        if 1 <= len(toks) <= 3:
            width = style = color = "initial"
            for t in toks:
                if re.fullmatch(r"[\d.]+[a-z]+|0|thin|medium|thick", t):
                    width = t
                elif t in ("none", "hidden", "dotted", "dashed", "solid", "double",
                           "groove", "ridge", "inset", "outset"):
                    style = t
                else:
                    color = t
            out = {}
            for s in SIDES:
                out[f"border-{s}-width"] = f"border-{s}-width={width}"
                out[f"border-{s}-style"] = f"border-{s}-style={style}"
                out[f"border-{s}-color"] = f"border-{s}-color={color}"
            return out
        return {p: f"{p}={v}" for p in lh}
    return {p: f"{p}={v}" for p in lh}


def split_ws(v):
    return [x for x in re.split(r"\s+", v) if x]


def expand_box(toks):
    if len(toks) == 1:
        return [toks[0]] * 4
    if len(toks) == 2:
        return [toks[0], toks[1], toks[0], toks[1]]
    if len(toks) == 3:
        return [toks[0], toks[1], toks[2], toks[1]]
    return toks[:4]


def expand_font(v):
    base = {p: f"{p}=normal" for p in ("font-weight", "font-style", "font-variant",
                                       "font-stretch")}
    m = re.match(r"^(?:(?P<pre>(?:italic|oblique|small-caps|bold|bolder|lighter|\d{3})\s+)*)"
                 r"(?P<size>[\d.]+(?:px|em|rem|%|pt|vw|vh)?)(?:/(?P<lh>[\d.]+(?:px|em|rem|%)?))?"
                 r"\s+(?P<fam>.+)$", v)
    if not m:
        return {p: f"{p}={v}" for p in EXPAND["font"]}
    out = dict(base)
    pre = (m.group("pre") or "").split()
    for tok in pre:
        if tok in ("italic", "oblique"):
            out["font-style"] = f"font-style={tok}"
        elif tok in ("bold", "bolder", "lighter") or re.fullmatch(r"\d{3}", tok):
            out["font-weight"] = f"font-weight={tok}"
        elif tok == "small-caps":
            out["font-variant"] = "font-variant=small-caps"
    out["font-size"] = f"font-size={m.group('size')}"
    out["line-height"] = f"line-height={m.group('lh') if m.group('lh') else 'normal'}"
    out["font-family"] = f"font-family={m.group('fam')}"
    return out


# ---------------------------------------------------------------- 特异性
def specificity(sel: str):
    sel = norm_sel(sel)
    # :where(...) 归零；:is/:not/:has 取参数最大 —— 简化实现：递归求最大
    a = b = c = 0

    def strip_where(s):
        out, i = [], 0
        while True:
            k = s.find(":where(", i)
            if k < 0:
                out.append(s[i:])
                return "".join(out)
            out.append(s[i:k])
            # 找配对右括号
            d, j = 0, k + 6
            while j < len(s):
                if s[j] == "(":
                    d += 1
                elif s[j] == ")":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            i = j + 1

    def max_of_func(s, fname):
        best = (0, 0, 0)
        i = 0
        while True:
            k = s.find(fname + "(", i)
            if k < 0:
                return best
            d, j = 0, k + len(fname)
            while j < len(s):
                if s[j] == "(":
                    d += 1
                elif s[j] == ")":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            inner = s[k + len(fname) + 1:j]
            for part in split_top_commas(inner):
                sp = specificity(part)
                if sp > best:
                    best = sp
            i = j + 1

    s = strip_where(sel)
    extra = (0, 0, 0)
    for fn in (":is", ":not", ":has", ":matches"):
        mx = max_of_func(s, fn)
        extra = tuple(x + y for x, y in zip(extra, mx))
        # 去掉这些函数体，避免重复计数
        while True:
            k = s.find(fn + "(")
            if k < 0:
                break
            d, j = 0, k + len(fn)
            while j < len(s):
                if s[j] == "(":
                    d += 1
                elif s[j] == ")":
                    d -= 1
                    if d == 0:
                        break
                j += 1
            s = s[:k] + " " + s[j + 1:]
    a += len(re.findall(r"#[\w-]+", s))
    a += extra[0]
    b += len(re.findall(r"\.[\w-]+", s))
    b += len(re.findall(r"\[[^\]]*\]", s))
    b += extra[1]
    c += len(re.findall(r"::[a-zA-Z-]+", s))
    c += len(re.findall(r":(before|after|first-line|first-letter|selection|placeholder)\b", s))
    b += len([p for p in re.findall(r"(?<!:):([a-zA-Z-]+)", s)
              if p not in ("before", "after", "first-line", "first-letter",
                           "selection", "placeholder")])
    rest = s
    rest = re.sub(r"::[a-zA-Z-]+", " ", rest)
    rest = re.sub(r":[a-zA-Z-]+", " ", rest)
    rest = re.sub(r"\[[^\]]*\]", " ", rest)
    rest = re.sub(r"\.[\w-]+", " ", rest)
    rest = re.sub(r"#[\w-]+", " ", rest)
    for tok in rest.split():
        if tok in (">", "+", "~", "*"):
            continue
        if re.fullmatch(r"[a-zA-Z][\w-]*", tok):
            c += 1
    c += extra[2]
    return (a, b, c)


INTERACTION = (":hover", ":focus-visible", ":focus-within", ":focus", ":active")


def sanitize(sel: str) -> str:
    out = re.sub(r"::[a-zA-Z-]+", "", norm_sel(sel))
    out = re.sub(r":(before|after|first-line|first-letter|selection|placeholder)\b", "", out)
    for p in INTERACTION:
        out = out.replace(p, "")
    return norm_sel(out)


def rightmost_compound(sel: str) -> str:
    parts, buf, depth = [], [], 0
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if depth == 0 and ch in ">+~ \t":
            if buf:
                parts.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts[-1] if parts else sel


def may_share(a: str, b: str) -> bool:
    ca, cb = rightmost_compound(a), rightmost_compound(b)
    ids_a = set(re.findall(r"#([\w-]+)", ca))
    ids_b = set(re.findall(r"#([\w-]+)", cb))
    if ids_a and ids_b and not (ids_a & ids_b):
        return False
    tags_a = {t.lower() for t in re.findall(r"(?<![\w.#:\-])([a-zA-Z][\w-]*)", ca)} - {
        "not", "is", "where", "has"}
    tags_b = {t.lower() for t in re.findall(r"(?<![\w.#:\-])([a-zA-Z][\w-]*)", cb)} - {
        "not", "is", "where", "has"}
    if tags_a and tags_b and not (tags_a & tags_b):
        return False
    pe_a = set(re.findall(r"::[a-zA-Z-]+", ca)) | {
        ":" + m for m in re.findall(r":(before|after|first-line|first-letter|selection|placeholder)\b", ca)}
    pe_b = set(re.findall(r"::[a-zA-Z-]+", cb)) | {
        ":" + m for m in re.findall(r":(before|after|first-line|first-letter|selection|placeholder)\b", cb)}
    if pe_a != pe_b:
        return False
    return True


# ---------------------------------------------------------------- 媒体条件
def media_bounds(ctx):
    """把 @media 条件文本解析成 (min_w, max_w, others)；未出现 = None。"""
    txt = " ".join(ctx)
    mn = mx = None
    for m in re.finditer(r"min-width\s*:\s*(\d+)px", txt):
        v = int(m.group(1))
        mn = v if mn is None else max(mn, v)
    for m in re.finditer(r"max-width\s*:\s*(\d+)px", txt):
        v = int(m.group(1))
        mx = v if mx is None else min(mx, v)
    others = re.sub(r"\(\s*(?:min|max)-width\s*:\s*\d+px\s*\)", "", txt).strip()
    return mn, mx, others


def contexts_compatible(c1, c2):
    """两个 @ 上下文是否可能在同一视口同时生效（保守：说不清就 True）。"""
    if c1 == c2:
        return True
    mn1, mx1, o1 = media_bounds(c1)
    mn2, mx2, o2 = media_bounds(c2)
    mn = max([x for x in (mn1, mn2) if x is not None], default=None)
    mx = min([x for x in (mx1, mx2) if x is not None], default=None)
    if mn is not None and mx is not None and mn > mx:
        return False
    # 非宽度条件不同（例如 prefers-reduced-motion vs 无）⇒ 仍可能同时生效
    return True


def cross_context_flips(eb, ea, co, measured):
    """跨 @ 上下文的先后翻转（顶层规则可能搬到 @media 块之后，或反之）。"""
    out = []
    ctxs = sorted({k[0] for k in eb} & {k[0] for k in ea})
    lh_all = sorted({k[1] for k in eb} & {k[1] for k in ea})
    for lh in lh_all:
        per = {c: eb[(c, lh)] for c in ctxs if (c, lh) in eb}
        perA = {c: ea[(c, lh)] for c in ctxs if (c, lh) in ea}
        cs = [c for c in per if c in perA]
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                c1, c2 = cs[i], cs[j]
                if not contexts_compatible(c1, c2):
                    continue
                for x, xb in per[c1].items():
                    if x not in perA[c1]:
                        continue
                    xa = perA[c1][x]
                    for y, yb in per[c2].items():
                        if y not in perA[c2]:
                            continue
                        ya = perA[c2][y]
                        if xb[0] != yb[0] or xb[2] == yb[2]:
                            continue
                        if specificity(x) != specificity(y) or not may_share(x, y):
                            continue
                        if (xb[1] < yb[1]) != (xa[1] < ya[1]):
                            pair = frozenset((sanitize(x), sanitize(y)))
                            verdict = ("evidence-hit" if pair in co else
                                       "uncovered" if (len(pair) == 1 or not pair <= measured)
                                       else "evidence-cleared")
                            out.append((lh, c1, c2, x, y, xb, yb, xa, ya, verdict))
    return out

# ---------------------------------------------------------------- 主分析
def group_decls(rules):
    """(ctx, simple) → [(prop, value, imp)] 文档顺序串起来。"""
    g = defaultdict(list)
    for r in rules:
        for s in r["sel_list"]:
            for d in r["decls"]:
                g[(r["ctx"], s)].append(d)
    return g


def main():
    before_path, after_path = sys.argv[1], sys.argv[2]
    ev_path = sys.argv[3] if len(sys.argv) > 3 else None
    b = parse_css(open(before_path, encoding="utf-8").read())
    a = parse_css(open(after_path, encoding="utf-8").read())
    gb, ga = group_decls(b), group_decls(a)

    print("== 解析规模 ==")
    print(f"before: {len(b)} 条规则 / {len(gb)} 个(上下文,简单选择器)键 / "
          f"{sum(len(x) for x in gb.values())} 条声明实例")
    print(f"after : {len(a)} 条规则 / {len(ga)} 个键 / {sum(len(x) for x in ga.values())} 条声明实例")

    def rules_per_key(rules):
        c = Counter()
        for r in rules:
            for sm in r["sel_list"]:
                c[(r["ctx"], sm)] += 1
        return c
    rpb, rpa = rules_per_key(b), rules_per_key(a)

    # ---- B: 值未变（逐字）
    print("\n== B. 值未变判据（after 串 == before 串去掉被支配者，逐字比较）==")
    bad = []
    still_dup = []
    keys_added = sorted(set(ga) - set(gb))
    keys_removed = sorted(set(gb) - set(ga))
    for key in sorted(set(gb) & set(ga)):
        bd = gb[key]
        flags = shadowed_flags(bd)
        expected = [d for d, keep in zip(bd, flags) if keep]
        actual = ga[key]
        if rpa[key] > 1:            # 该选择器在 after 里仍是 ≥2 条规则 ⇒ 尚未合并
            if actual != bd:
                still_dup.append((key, bd, actual))
            continue
        if expected != actual:
            bad.append((key, expected, actual))
    print(f"键新增 {len(keys_added)}；键消失 {len(keys_removed)}；未合并键 {sum(1 for k in rpa if rpa[k] > 1)}"
          f"（其中串与 before 不等 {len(still_dup)}，属正常未合并）；已合并键声明串不等 {len(bad)}")
    for k in keys_added[:20]:
        print("  +", k)
    for k in keys_removed[:20]:
        print("  -", k)
    for key, exp, act in bad[:12]:
        print("  !", key)
        print("     expected:", exp)
        print("     actual  :", act)

    # 统计被删声明的数量（= before 里同属性被后置支配的实例数）
    dropped = 0
    for key in sorted(set(gb) & set(ga)):
        bd = gb[key]
        flags = shadowed_flags(bd)
        dropped += sum(1 for f in flags if not f)
    print(f"被判定支配并删除的声明实例：{dropped}")

    # ---- C: 跨选择器顺序翻转
    print("\n== C. 跨选择器「生效声明先后翻转」判据 ==")
    co = None
    measured = set()
    if ev_path:
        ev = json.load(open(ev_path, encoding="utf-8"))
        co = {frozenset((p["a_sanitized"], p["b_sanitized"])) for p in ev["co_match"]}
        measured = set(ev["selector_sanitized"].keys())
        print(f"证据：states={len(ev['states'])} 选择器={len(ev['selector_sanitized'])} "
              f"co_match={ev['co_match_pair_count']} pairs_checked={ev['pairs_checked']}")

    def eff_map(rules):
        """(ctx, longhand) → {simple: (imp, pos, value)}；pos = 全局声明序号。"""
        g = defaultdict(dict)
        pos = 0
        ctx_prop_spec = defaultdict(dict)   # (ctx, lh) → {simple: (imp, pos)} 取最先生效位
        for r in rules:
            for s in r["sel_list"]:
                for prop, value, imp in r["decls"]:
                    for lh, val in longhand_map(prop, value).items():
                        cur = g[(r["ctx"], lh)].get(s)
                        if cur is None or imp or not cur[0]:
                            # important 胜普通；同重要性时后置胜
                            if cur is None or imp > cur[0] or (imp == cur[0]):
                                g[(r["ctx"], lh)][s] = (imp, pos, val)
                    pos += 1
        return g

    eb, ea = eff_map(b), eff_map(a)
    flips = []
    for key in sorted(set(eb) & set(ea)):
        ctx, lh = key
        m_b, m_a = eb[key], ea[key]
        common = sorted(set(m_b) & set(m_a))
        for i in range(len(common)):
            for j in range(i + 1, len(common)):
                x, y = common[i], common[j]
                ib, pb, vb = m_b[x][0], m_b[x][1], m_b[x][2]
                jb, qb, wb = m_b[y][0], m_b[y][1], m_b[y][2]
                if ib != jb:
                    continue
                if specificity(x) != specificity(y):
                    continue
                if not may_share(x, y):
                    continue
                if vb == wb:
                    continue                # 两条声明值相同 ⇒ 谁赢都一样，翻转无影响
                if (pb < qb) != (m_a[x][1] < m_a[y][1]):
                    flips.append((ctx, lh, x, y, m_b[x], m_b[y], m_a[x], m_a[y]))
    print(f"长手属性×上下文键：before {len(eb)} / after {len(ea)}")
    print(f"同特异性同重要性、可能共命中、先后关系翻转的对：{len(flips)}")
    real, uncovered, cleared = [], [], []
    for f in flips:
        ctx, lh, x, y, db, wb, da, wa = f
        pair = frozenset((sanitize(x), sanitize(y)))
        reason = ""
        if pair in co:
            real.append((f, "证据中确实共命中"))
        elif len(pair) == 1:
            uncovered.append((f, "同 sanitize 键（交互态/伪元素对），证据无法覆盖自反 pair"))
        elif not pair <= measured:
            uncovered.append((f, "证据未覆盖该对（fail-closed：不算豁免）"))
        else:
            cleared.append((f, "证据覆盖且从未共命中"))
    print(f"  → 真风险(证据共命中) {len(real)}；未覆盖 {len(uncovered)}；证据已豁免 {len(cleared)}")
    zh2 = set()
    if ev_path:
        ev3 = json.load(open(ev_path, encoding="utf-8"))
        zh2 = {k for k, v in ev3["selector_counts"].items() if v == 0}
        n_zh = sum(1 for f, _w in cleared if sanitize(f[2]) in zh2 or sanitize(f[3]) in zh2)
        print(f"  其中「一侧选择器零命中 ⇒ 由其vacuous清掉」的翻转对：{n_zh}")
        print(f"  未覆盖明细：")
        for f, why in uncovered[:20]:
            print(f"    x {f[2]} (san={sanitize(f[2])!r}) vs {f[3]} (san={sanitize(f[3])!r}) :: {why}")
    for f, why in (real + uncovered)[:40]:
        ctx, lh, x, y, db, wb, da, wa = f
        print(f"  ! {ctx or 'top'} {lh}: {x} (spec={specificity(x)}) vs {y} "
              f"(spec={specificity(y)}) → {why}")
        print(f"      before pos x={db[1]} y={wb[1]}  after pos x={da[1]} y={wa[1]} 值 {db[2]} | {wb[2]}")

    # ---- C2: 跨 @ 上下文翻转
    cc = cross_context_flips(eb, ea, co or set(), measured)
    print(f"\n== C2. 跨 @ 上下文（顶层 vs @media 等）先后翻转：{len(cc)} ==")
    by_verdict = Counter(t[9] for t in cc)
    print("  裁决分布:", dict(by_verdict))
    zh = set()
    if ev_path:
        ev2 = json.load(open(ev_path, encoding="utf-8"))
        zh = {k for k, v in ev2["selector_counts"].items() if v == 0}
        print(f"  零命中选择器（36 组合里一次都没命中元素）：{len(zh)} 个 / 共 {len(ev2['selector_counts'])}")
        uninvolved = [t for t in cc if t[9] == "uncovered"]
        print(f"  covered 但其中一侧是零命中选择器的跨上下文翻转："
              f"{sum(1 for t in cc if t[9] != 'uncovered' and (sanitize(t[3]) in zh or sanitize(t[4]) in zh))}")
    for t in cc[:30]:
        lh, c1, c2, x, y, xb, yb, xa, ya, v = t
        print(f"  ! {lh}: [{c1 or 'top'}] {x} pos {xb[1]}→{xa[1]}  vs  [{c2 or 'top'}] {y} "
              f"pos {yb[1]}→{ya[1]}  值 {xb[2]} | {yb[2]}  → {v}")

    # ---- D: 结构 / 全局不变量
    print("\n== D. 结构数字与全局不变量 ==")
    for name, rules in (("before", b), ("after", a)):
        groups = defaultdict(int)
        simple_dup = defaultdict(int)
        for r in rules:
            groups[(r["ctx"], "|".join(r["sel_list"]))] += 1
            for s in r["sel_list"]:
                simple_dup[(r["ctx"], s)] += 1
        g2 = sum(1 for k, v in groups.items() if v >= 2)
        g2r = sum(v for k, v in groups.items() if v >= 2)
        d2 = sum(1 for k, v in simple_dup.items() if v >= 2)
        d2r = sum(v for k, v in simple_dup.items() if v >= 2)
        imp = sum(1 for r in rules for d in r["decls"] if d[2])
        print(f"{name}: 规则 {len(rules)}；(选择器文本,上下文) 重复组 {g2} 涉及 {g2r} 条；"
              f"简单选择器重复 {d2} 个 涉及 {d2r} 条；!important 声明 {imp}")
        if name == "before":
            print(f"  before: 不同选择器文本 {len({s for r in rules for s in r['sel_list']})}"
                  f" / 不同简单选择器 {len({s for r in rules for s in r['sel_list']})}")
    for name, rules in (("before", b), ("after", a)):
        ctxs = Counter(r["ctx"] for r in rules)
        print(f"{name} 的 @ 上下文：{ {(' '.join(k) or 'top'): v for k, v in ctxs.items()} }")
    for name, rules in (("before", b), ("after", a)):
        db = {(d[0], d[1], d[2]) for r in rules for d in r["decls"]}
        print(f"{name}: 不同 (prop,value,important) 组合 {len(db)}；"
              f"其中 important=True {len([x for x in db if x[2]])}")
    hb = Counter(re.findall(r"#[0-9a-fA-F]{3,8}\b", open(before_path).read()))
    ha = Counter(re.findall(r"#[0-9a-fA-F]{3,8}\b", open(after_path).read()))
    print(f"hex 字面量多重集 before={sum(hb.values())} after={sum(ha.values())} 不等={hb != ha}")


if __name__ == "__main__":
    main()
