#!/usr/bin/env python3
"""UI 3C / F14 两段式 CSS 合并工具（默认只读，`apply` 才改写 loop/web/app.css）。

设计契约见 doc/plans/2026-10-30-ui-css-merge-f14c.md §2。

两件事，都可机械证明不改计算样式：
  1. `split`  —— 把 `a, b{...}` 拆成 `a{...}` + `b{...}`（同位置、同声明、同特异性；
     命中两个选择器的元素拿到完全相同的一串声明，值相同 ⇒ 无差别）。
  2. `merge`  —— 同一 (选择器文本, @ 上下文) 的多条规则合并成一条，放在**最后一条**的位置：
     每个属性取「胜者」（有 !important 时最后一条 !important 胜，否则最后一条普通声明胜），
     被支配的声明删除；被搬到后面的声明，必须证明 Ri..Rn 之间没有能"抢赢"的竞争者：
       · !important 不同 → 无关（重要性永远优先于源码顺序）
       · 特异性不同   → 无关（高特异性恒定胜出）
       · 特异性相等   → 比较**最右复合选择器**是否可能命中同一元素：
                        id 互斥 / 标签名互斥 / 伪元素互斥 ⇒ 不会同时命中（安全）；
                        其余 ⇒ 记一条 "blocked"（不自动合，交人判）。
     属性按**简写展开后的 longhand 集合**比较（font / background / border-* / gap / padding /
     margin / overflow / inset / flex / outline / transition / animation / place-items / ...），
     避免「font 简写搬到后面反而压掉中间 font-weight」这类假安全。

只读报告：
  loop/.venv/bin/python .ui-audit/3c/merge_plan.py stats
  loop/.venv/bin/python .ui-audit/3c/merge_plan.py plan            # 分组 + 安全/受阻清单
改写：
  loop/.venv/bin/python .ui-audit/3c/merge_plan.py split --apply
  loop/.venv/bin/python .ui-audit/3c/merge_plan.py merge --apply --max 15
  loop/.venv/bin/python .ui-audit/3c/merge_plan.py merge --apply --only --limit-file ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# 默认改 loop/web/app.css；`MERGE_CSS` 可指向暂存副本（3C 与批次 4 并行期间用 staging 隔离）
CSS = Path(os.environ.get("MERGE_CSS") or (REPO / "loop" / "web" / "app.css"))
OUT = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- #
# 解析（保留文本偏移，逐字改写）
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class Decl:
    prop: str
    value: str
    important: bool
    start: int
    end: int            # 含结尾 ';'（最后一条可能不含）
    text: str = ""
    rule: "Rule | None" = None


@dataclass(eq=False)
class Rule:
    selector: str
    start: int          # prelude 起始（含前导空白之后）
    end: int            # '}' 之后
    decls: list
    media: tuple = ()
    at: tuple = ()
    text: str = ""
    index: int = 0



def split_top_level(sel: str, sep: str = ",") -> list:
    """按顶层分隔符切分（尊重 ()、[] 与字符串）；`:where(a,b)` 里的逗号不算。"""
    parts, buf, depth = [], [], 0
    i = 0
    while i < len(sel):
        ch = sel[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch in "\"'" and depth >= 0:
            quote = ch
            buf.append(ch)
            i += 1
            while i < len(sel):
                buf.append(sel[i])
                if sel[i] == "\\":
                    i += 1
                    if i < len(sel):
                        buf.append(sel[i])
                elif sel[i] == quote:
                    break
                i += 1
            i += 1
            continue
        if ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts

def _skip_string(text, i):
    quote = text[i]
    i += 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return i


def _skip_comment(text, i):
    j = text.find("*/", i + 2)
    return len(text) if j < 0 else j + 2


def _skip_ws_comments(text, i, end):
    while i < end:
        ch = text[i]
        if ch in " \t\r\n\f":
            i += 1
        elif text.startswith("/*", i):
            i = _skip_comment(text, i)
        else:
            break
    return i


def _find_block_end(text, open_index):
    depth = 0
    i = open_index
    while i < len(text):
        ch = text[i]
        if ch in '"\'':
            i = _skip_string(text, i)
            continue
        if text.startswith("/*", i):
            i = _skip_comment(text, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced braces at %d" % open_index)


def _parse_decls(text, start, end):
    decls = []
    i = start
    while i < end:
        i = _skip_ws_comments(text, i, end)
        if i >= end:
            break
        if text[i] in ";":
            i += 1
            continue
        decl_start = i
        colon = None
        j = i
        while j < end:
            ch = text[j]
            if ch in '"\'':
                j = _skip_string(text, j)
                continue
            if text.startswith("/*", j):
                j = _skip_comment(text, j)
                continue
            if ch == ":" and colon is None:
                colon = j
            if ch == ";":
                break
            if ch == "}":
                break
            j += 1
        raw_end = j + 1 if j < end and text[j] == ";" else j
        if colon is None:
            i = raw_end
            continue
        prop = text[decl_start:colon].strip()
        value = text[colon + 1:min(j, end)].strip()
        important = False
        m = re.search(r"!\s*important\s*$", value, re.I)
        if m:
            important = True
            value = value[:m.start()].strip()
        decls.append(Decl(prop=prop.lower(), value=value, important=important,
                          start=decl_start, end=raw_end,
                          text=text[decl_start:raw_end]))
        i = raw_end
    return decls


def parse_css(text):
    rules = []

    def parse_block(i, end, media, at):
        while True:
            i = _skip_ws_comments(text, i, end)
            if i >= end:
                return
            if text[i] == "}":
                i += 1
                continue
            prelude_start = i
            j = i
            paren = 0
            while j < end:
                ch = text[j]
                if ch in '"\'':
                    j = _skip_string(text, j)
                    continue
                if text.startswith("/*", j):
                    j = _skip_comment(text, j)
                    continue
                if ch in "([":
                    paren += 1
                elif ch in ")]":
                    paren -= 1
                elif ch == "{" and paren == 0:
                    break
                j += 1
            if j >= end:
                return
            prelude = text[prelude_start:j].strip()
            block_end = _find_block_end(text, j)
            if prelude.startswith("@"):
                name = re.match(r"@[\w-]+", prelude).group(0).lower()
                if name in ("@media", "@supports"):
                    parse_block(j + 1, block_end, media + (prelude,), at)
                else:
                    parse_block(j + 1, block_end, media, at + (prelude,))
            else:
                decls = _parse_decls(text, j + 1, block_end)
                rule = Rule(selector=prelude, start=prelude_start, end=block_end + 1,
                            decls=decls, media=media, at=at,
                            text=text[prelude_start:block_end + 1])
                for d in decls:
                    d.rule = rule
                rules.append(rule)
            i = block_end + 1

    parse_block(0, len(text), (), ())
    for n, r in enumerate(rules):
        r.index = n
    return rules


# --------------------------------------------------------------------------- #
# 简写 → longhand 展开（只覆盖本文件实际出现的简写 + 常见族）
# --------------------------------------------------------------------------- #
_SIDES = ("top", "right", "bottom", "left")
_CORNERS = ("top-left", "top-right", "bottom-right", "bottom-left")
SHORT_EXPAND = {
    "margin": tuple("margin-" + s for s in _SIDES),
    "padding": tuple("padding-" + s for s in _SIDES),
    "inset": ("top", "right", "bottom", "left"),
    "gap": ("row-gap", "column-gap"),
    "overflow": ("overflow-x", "overflow-y"),
    "border-radius": tuple("border-%s-radius" % c for c in _CORNERS),
    "border": tuple("border-%s-%s" % (s, k) for s in _SIDES
                    for k in ("width", "style", "color")),
    "border-color": tuple("border-%s-color" % s for s in _SIDES),
    "border-width": tuple("border-%s-width" % s for s in _SIDES),
    "border-style": tuple("border-%s-style" % s for s in _SIDES),
    "background": ("background-color", "background-image", "background-position",
                   "background-size", "background-repeat", "background-clip",
                   "background-origin", "background-attachment", "background-blend-mode"),
    "font": ("font-family", "font-size", "font-weight", "font-style", "font-variant",
             "font-stretch", "line-height"),
    "flex": ("flex-grow", "flex-shrink", "flex-basis"),
    "outline": ("outline-width", "outline-style", "outline-color"),
    "text-decoration": ("text-decoration-line", "text-decoration-color",
                        "text-decoration-style", "text-decoration-thickness"),
    "place-items": ("align-items", "justify-items"),
    "list-style": ("list-style-type", "list-style-position", "list-style-image"),
    "transition": ("transition-property", "transition-duration",
                   "transition-timing-function", "transition-delay"),
    "animation": ("animation-name", "animation-duration", "animation-timing-function",
                  "animation-delay", "animation-iteration-count", "animation-direction",
                  "animation-fill-mode", "animation-play-state"),
    "grid-column": ("grid-column-start", "grid-column-end"),
    "grid-row": ("grid-row-start", "grid-row-end"),
    "grid-area": ("grid-row-start", "grid-column-start", "grid-row-end", "grid-column-end"),
    "grid": ("grid-template-rows", "grid-template-columns", "grid-template-areas",
             "grid-auto-rows", "grid-auto-columns", "grid-auto-flow"),
    "grid-template": ("grid-template-rows", "grid-template-columns", "grid-template-areas"),
    "scrollbar-color": ("scrollbar-color",),
}
for _s in _SIDES:
    SHORT_EXPAND["border-" + _s] = tuple("border-%s-%s" % (_s, k)
                                         for k in ("width", "style", "color"))
    SHORT_EXPAND["border-" + _s + "-color"] = ("border-%s-color" % _s,)
    SHORT_EXPAND["border-" + _s + "-width"] = ("border-%s-width" % _s,)
    SHORT_EXPAND["border-" + _s + "-style"] = ("border-%s-style" % _s,)


def longhands(prop: str) -> frozenset:
    if prop.startswith("--"):
        return frozenset([prop])
    return frozenset(SHORT_EXPAND.get(prop, (prop,)))


# --------------------------------------------------------------------------- #
# 特异性 + 最右复合选择器
# --------------------------------------------------------------------------- #
def _split_selector_parts(sel: str):
    """按组合符切分（尊重括号/方括号/字符串）。"""
    parts, buf, depth = [], [], 0
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if depth == 0 and ch in ">+~ \t\n":
            if buf:
                parts.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


_PSEUDO_ELEMENT = re.compile(r"::[a-zA-Z-]+")
_LEGACY_PSEUDO_EL = re.compile(r":(before|after|first-line|first-letter|selection|placeholder)\b")


def compound_info(compound: str):
    """返回 (ids, tags, pseudo_elements, pseudo_classes, has_attr) 供互斥判定。"""
    ids = set(re.findall(r"#([\w-]+)", compound))
    tags = set(re.findall(r"(?<![\w.#:\-])([a-zA-Z][\w-]*)", compound))
    tags = {t.lower() for t in tags if t.lower() not in ("not", "is", "where", "has")}
    pes = set(m.group(0) for m in _PSEUDO_ELEMENT.finditer(compound))
    pes |= {":" + m.group(1) for m in _LEGACY_PSEUDO_EL.finditer(compound)}
    pcs = set(re.findall(r"(?<![:a-zA-Z-]):([a-zA-Z-]+)", compound))
    pcs -= {"before", "after", "first-line", "first-letter", "selection", "placeholder"}
    return ids, tags, pes, pcs


def specificity(sel: str):
    """返回 (a,b,c)；遇到 :is/:not/:where/:has 返回 None（不自动判，交人）。"""
    if re.search(r":(is|not|where|has|matches)\(", sel):
        return None
    a = b = c = 0
    # 去掉属性选择器里的内容参与 b，伪元素/伪类参与 b/c
    for m in re.finditer(r"#([\w-]+)", sel):
        a += 1
    sel_no_ids = re.sub(r"#([\w-]+)", "", sel)
    b += len(re.findall(r"\.[\w-]+", sel_no_ids))
    b += len(re.findall(r"\[[^\]]*\]", sel_no_ids))
    # 伪元素
    c += len(re.findall(r"::[a-zA-Z-]+", sel_no_ids))
    c += len(re.findall(r":(before|after|first-line|first-letter|selection|placeholder)\b",
                        sel_no_ids))
    # 伪类（排除伪元素）
    pc = re.findall(r"(?<!:):([a-zA-Z-]+)", sel_no_ids)
    pc = [p for p in pc if p not in ("before", "after", "first-line", "first-letter",
                                     "selection", "placeholder")]
    b += len(pc)
    # 元素名：去掉伪类/伪元素/属性
    rest = re.sub(r"::[a-zA-Z-]+", " ", sel_no_ids)
    rest = re.sub(r":([a-zA-Z-]+)", " ", rest)
    rest = re.sub(r"\[[^\]]*\]", " ", rest)
    rest = re.sub(r"\.[\w-]+", " ", rest)
    for tok in rest.split():
        if tok in (">", "+", "~", "*", ""):
            continue
        if re.fullmatch(r"[a-zA-Z][\w-]*", tok):
            c += 1
    return (a, b, c)


def may_share_element(sel_a: str, sel_b: str) -> bool:
    """两个选择器的最右复合选择器是否**可能**命中同一元素（保守：宁可说"可能"）。"""
    a = _split_selector_parts(sel_a)[-1]
    b = _split_selector_parts(sel_b)[-1]
    ids_a, tags_a, pes_a, _ = compound_info(a)
    ids_b, tags_b, pes_b, _ = compound_info(b)
    if pes_a != pes_b:                      # 伪元素不同 ⇒ 不同盒子
        return False
    if ids_a and ids_b and not (ids_a & ids_b):
        return False                        # id 互斥
    if tags_a and tags_b and not (tags_a & tags_b):
        return False                        # 标签名互斥
    return True


# --------------------------------------------------------------------------- #
# 合并计划
# --------------------------------------------------------------------------- #
@dataclass
class Group:
    key: tuple                 # (media, at, selector)
    rules: list
    keep: list = field(default_factory=list)      # 保留下来的声明 [(decl, source_rule)]
    moves: list = field(default_factory=list)     # 从更早规则搬来的声明
    blocks: list = field(default_factory=list)    # [(rule, prop, blocking_rule)]
    dropped: list = field(default_factory=list)   # 被支配删除的声明


def build_groups(rules):
    groups = {}
    order = []
    for r in rules:
        key = (r.media, r.at, r.selector)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    out = []
    for key in order:
        rs = groups[key]
        if len(rs) < 2:
            continue
        g = Group(key=key, rules=rs)
        # 胜者判定
        winners = {}
        for ri, rule in enumerate(rs):
            for decl in rule.decls:
                prev = winners.get(decl.prop)
                # 级联：!important 胜过普通；同重要性时后置胜；前置 important 不被后置普通覆盖
                if prev is None or decl.important or not prev[1].important:
                    winners[decl.prop] = (ri, decl)
        for ri, rule in enumerate(rs):
            for decl in rule.decls:
                win_ri, win = winners[decl.prop]
                if decl is win:
                    entry = (decl, rule, ri)
                    g.keep.append(entry)
                    if ri != len(rs) - 1:
                        g.moves.append(entry)
                else:
                    g.dropped.append((decl, rule))
        out.append(g)
    return out


def classify(g: Group, rules, co=(), measured=None):
    """对每个"搬到后面"的声明做级联安全检查。返回 blocked 列表。"""
    last = g.rules[-1]
    blocked = []
    for decl, source_rule, ri in g.moves:
        lh = longhands(decl.prop)
        src_sel = source_rule.selector
        for cand in rules:
            if not (source_rule.index < cand.index < last.index):
                continue
            if cand is last:
                continue
            if cand.selector == src_sel and cand.media == source_rule.media and cand.at == source_rule.at:
                continue        # 同组内的自己
            hit = False
            for other in cand.decls:
                if not (lh & longhands(other.prop)):
                    continue
                if other.important != decl.important:
                    continue
                sp_src, sp_other = specificity(src_sel), specificity(cand.selector)
                if sp_src is None or sp_other is None:
                    blocked.append({"rule": cand.index, "selector": cand.selector,
                                    "prop": other.prop, "reason": "复杂选择器(:is/:not/:where)：不自动判"})
                    hit = True
                    break
                if sp_src != sp_other:
                    continue    # 特异性不同 ⇒ 源码顺序无关
                if may_share_element(src_sel, cand.selector):
                    if _same_value(decl, other):
                        continue
                    pair = frozenset((sanitize_selector(src_sel),
                                      sanitize_selector(cand.selector)))
                    if not pair:
                        blocked.append({"rule": cand.index, "selector": cand.selector,
                                        "prop": other.prop, "value": other.value,
                                        "reason": "选择器 sanitize 后为空：不自动判"})
                        hit = True
                        break
                    # 同一选择器、不同 @ 上下文：源码先后**就是**生效关系（两条规则在任何同时满足
                    # 两边条件的环境里都作用于同一批元素），共命中证据对这条没有信息量 ⇒ 直接受阻。
                    same_sel_cross_ctx = (sanitize_selector(src_sel)
                                          == sanitize_selector(cand.selector)
                                          and (cand.media, cand.at)
                                          != (source_rule.media, source_rule.at))
                    cleared = (not same_sel_cross_ctx
                               and co is not None and measured is not None
                               and pair <= measured and pair not in co)
                    if not cleared:
                        blocked.append({"rule": cand.index, "selector": cand.selector,
                                    "prop": other.prop, "value": other.value,
                                        "media": " ".join(cand.media),
                                        "reason": ("同一选择器在窗口内有别的 @media 上下文规则（源码先后即生效关系）"
                                                   if same_sel_cross_ctx else
                                                   ("共命中证据显示确实命中同一元素" if pair in co
                                                    else "该对选择器未被共命中证据覆盖 ⇒ 不能豁免"))})
                        hit = True
                        break
                    # 证据覆盖了该对且从未命中同一元素 ⇒ 这一条不算竞争者，
                    # 继续检查同一规则的下一条声明 / 下一条规则（不得短路）。
                    continue
            if hit:
                break
    return blocked



_INTERACTION_PSEUDO = (":hover", ":focus-visible", ":focus-within", ":focus", ":active")


def sanitize_selector(sel: str) -> str:
    """去掉交互态伪类与伪元素（用于共命中证据的键；与 .ui-audit/3c/cooccur.py 同口径）。"""
    out = re.sub(r"::[a-zA-Z-]+", "", sel)
    out = re.sub(r":(before|after|first-line|first-letter|selection|placeholder)\b", "", out)
    for pseudo in _INTERACTION_PSEUDO:
        out = out.replace(pseudo, "")
    return re.sub(r"\s+", " ", out).strip()

def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _same_value(a: Decl, b: Decl) -> bool:
    return _norm(a.value) == _norm(b.value)


def decl_text(d: Decl) -> str:
    """保留原文本（含前导空白/换行与结尾 ';'）；补齐尾分号。"""
    t = d.text
    if not t.rstrip().endswith(";"):
        t = t.rstrip() + ";"
    return t


def merged_text(g: Group) -> str:
    last = g.rules[-1]
    body = "".join(decl_text(d) for d, _r, _ri in g.keep)
    return last.selector + "{" + body + "}"


# --------------------------------------------------------------------------- #
# 文本编辑
# --------------------------------------------------------------------------- #
def _line_bounds(text, start, end):
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    le = len(text) if le < 0 else le
    return ls, le


def delete_span(text, start, end):
    """删除规则：若独占整行则连行删除；否则只删片段。"""
    ls, le = _line_bounds(text, start, end)
    if text[ls:start].strip() == "" and text[end:le].strip() == "":
        new = text[:ls] + text[le + 1:]
        # 合并由删除产生的连续空行
        new = re.sub(r"\n{3,}", "\n\n", new)
        return new
    return text[:start] + text[end:]


def apply_edits(text, edits):
    """edits: [(start, end, replacement)]，按 start 倒序应用。"""
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + repl + text[end:]
    return text


# --------------------------------------------------------------------------- #
# 命令
# --------------------------------------------------------------------------- #
def load():
    text = CSS.read_text(encoding="utf-8")
    return text, parse_css(text)


def stats(args):
    text, rules = load()
    top = [r for r in rules if not r.media and not r.at]
    groups = build_groups(rules)
    all_groups = {}
    for r in rules:
        all_groups.setdefault((r.media, r.at, r.selector), []).append(r)
    dup_all = {k: v for k, v in all_groups.items() if len(v) > 1}
    print("app.css: %d 行 / %d 条解析规则 / %d 条顶层规则" % (
        len(text.splitlines()), len(rules), len(top)))
    print("不同选择器文本: %d；不同简单选择器: %d" % (
        len({k[2] for k in all_groups}),
        len({p.strip() for k in all_groups for p in split_top_level(k[2])})))
    print("同 (选择器, @上下文) 被 ≥2 条规则定义: %d 组，涉及 %d 条规则" % (
        len(dup_all), len({id(r) for v in dup_all.values() for r in v})))
    ctx = {}
    for k in dup_all:
        ctx[k[0] + k[1]] = ctx.get(k[0] + k[1], 0) + 1
    print("按上下文:", {(" ".join(k) or "top-level"): v for k, v in ctx.items()})
    print("可合并组（拆分逗号后）: %d" % len(groups))
    for r in rules:
        if "," in r.selector:
            pass
    print("含顶层逗号选择器的规则: %d" % len(
        [r for r in rules if len(split_top_level(r.selector)) > 1]))


def load_co(path=None):
    """读共命中证据：只保留「确实命中同一元素」的对（frozenset of sanitized）。"""
    path = Path(path) if path else OUT / "cooccur.json"
    if not path.exists():
        # 没有证据 ⇒ 不能放宽：返回 None，classify 走严格判据（所有可能共命中都算受阻）
        return None, None, {}
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = set()
    for item in data.get("co_match", []):
        a, b = item.get("a"), item.get("b")
        if a and b:
            sa, sb = sanitize_selector(a), sanitize_selector(b)
            if sa and sb:
                pairs.add(frozenset((sa, sb)))
    measured = set()
    for orig, san in (data.get("selector_sanitized") or {}).items():
        if san:
            measured.add(san)
    if not measured:
        for sel in (data.get("selector_counts") or {}):
            measured.add(sanitize_selector(sel))
    return frozenset(pairs), frozenset(measured), data


def plan(args):
    text, rules = load()
    co, measured, data = load_co(args.evidence)
    groups = build_groups(rules)
    safe, blocked = [], []
    for g in groups:
        b = classify(g, rules, co, measured)
        if b:
            blocked.append({"selector": g.key[2], "media": g.key[0], "at": g.key[1],
                            "rules": [r.index for r in g.rules], "blocked": b,
                            "moves": [d.prop for d, _r, _ri in g.moves]})
        else:
            safe.append(g)
    report = {
        "evidence": args.evidence or str(OUT / "cooccur.json"),
        "evidence_used": co is not None,
        "evidence_pairs": len(co or ()),
        "evidence_measured_selectors": len(measured or ()),
        "evidence_states": (data or {}).get("states"),
        "groups": len(groups),
        "safe": len(safe),
        "blocked": len(blocked),
        "safe_selectors": [g.key[2] for g in safe],
        "blocked_detail": blocked,
        "moves_total": sum(len(g.moves) for g in groups),
        "dropped_total": sum(len(g.dropped) for g in groups),
    }
    (OUT / "merge-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print("可合并组: %d（安全 %d / 受阻 %d）" % (len(groups), len(safe), len(blocked)))
    print("搬动声明 %d 条；删除被支配声明 %d 条" % (report["moves_total"],
                                                report["dropped_total"]))
    for item in blocked:
        if args.verbose:
            print("\n受阻: %s  [%s]" % (item["selector"], " ".join(item["media"]) or "top"))
            for b in item["blocked"]:
                print("   ← rule#%d %s  %s:%s (%s) %s" % (
                    b["rule"], b["selector"], b["prop"], b.get("value", ""),
                    b.get("media", ""), b["reason"]))
    return 0


def split(args):
    text, rules = load()
    edits = []
    for r in rules:
        if "," not in r.selector:
            continue
        parts = [p.strip() for p in split_top_level(r.selector) if p.strip()]
        for part in parts:
            assert part.count("(") == part.count(")"), (
                "切分后括号不平衡（拒绝写盘）：%r ← %r" % (part, r.selector))
        if len(parts) < 2:
            continue
        open_brace = text.find("{", r.start + len(r.selector))
        block = text[open_brace:r.end]        # 含 {...}
        replacement = "".join(sel + block for sel in parts)
        edits.append((r.start, r.end, replacement))
    print("将要拆分 %d 条逗号规则" % len(edits))
    if not args.apply:
        for s, e, _ in edits[:10]:
            print("  @%d %s" % (s, text[s:e].split("{")[0].strip()[:90]))
        print("（干跑；加 --apply 才写）")
        return 0
    new_text = apply_edits(text, edits)
    CSS.write_text(new_text, encoding="utf-8")
    print("已写 %s（%d → %d 行）" % (CSS, len(text.splitlines()),
                                   len(new_text.splitlines())))
    return 0


def merge(args):
    """逐组应用（每组重新解析，避免偏移错乱）。"""
    text, rules = load()
    co, measured, _data = load_co(getattr(args, "evidence", ""))
    groups = build_groups(rules)
    candidates = []
    for g in groups:
        if not (g.moves or g.dropped):
            continue
        if classify(g, rules, co, measured):
            continue
        candidates.append(g)
    if args.only:
        only = {x.strip() for x in Path(args.only).read_text(encoding="utf-8").splitlines()
                if x.strip()}
        candidates = [g for g in candidates if g.key[2] in only]
    todo = [g.key for g in candidates][:args.max] if args.max else [g.key for g in candidates]
    if args.dry_run:
        for g in candidates[:len(todo)]:
            print("  %s [%s]: 删规则 %s；搬 %s；删声明 %s" % (
                g.key[2], " ".join(g.key[0]) or "top",
                [r.index for r in g.rules[:-1]],
                [d.prop for d, _r, _ri in g.moves],
                [d.prop for d, _r in g.dropped]))
        print("（干跑：%d 个选择器待合）" % len(todo))
        return 0
    log = []
    skipped = []
    for key in todo:
        text, rules = load()
        mapping = {g.key: g for g in build_groups(rules)}
        g = mapping.get(key)
        if g is None:
            skipped.append({"selector": key[2], "reason": "组已不存在"})
            continue
        b = classify(g, rules, co, measured)
        if b:
            skipped.append({"selector": key[2], "reason": "重算受阻", "blocked": b})
            continue
        last = g.rules[-1]
        body = "".join(decl_text(d) for d, _r, _ri in g.keep)
        new_text = text[:last.start] + last.selector + "{" + body + "}" + text[last.end:]
        # 删除更早的规则（文本偏移已变：从后往前删）
        for r in sorted(g.rules[:-1], key=lambda r: r.start, reverse=True):
            new_text = delete_span(new_text, r.start, r.end)
        CSS.write_text(new_text, encoding="utf-8")
        log.append({
            "selector": key[2], "media": list(key[0]),
            "removed_rules": [r.index for r in g.rules[:-1]],
            "kept_at_rule": last.index,
            "moved": [{"prop": d.prop, "from_rule": r.index, "value": d.value}
                      for d, r, _ri in g.moves],
            "dropped": [{"prop": d.prop, "rule": r.index, "value": d.value}
                        for d, r in g.dropped],
        })
        print("  merged %s [%s] rules %s → 第 %d 条位置" % (
            key[2], " ".join(key[0]) or "top",
            [r.index for r in g.rules[:-1]], last.index), flush=True)
    log_path = OUT / ("merge-log-%03d.json" % (args.batch or 0))
    log_path.write_text(json.dumps({"merged": log, "skipped": skipped},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    print("本批合并 %d 个选择器；批日志 %s" % (len(log), log_path))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stats")
    s.set_defaults(fn=stats)
    s = sub.add_parser("plan")
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--evidence", default="")
    s.set_defaults(fn=plan)
    s = sub.add_parser("split")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(fn=split)
    s = sub.add_parser("merge")
    s.add_argument("--apply", action="store_true")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--max", type=int, default=0)
    s.add_argument("--only", default="")
    s.add_argument("--all", action="store_true")
    s.add_argument("--batch", type=int, default=0)
    s.add_argument("--evidence", default="")
    s.set_defaults(fn=merge)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
