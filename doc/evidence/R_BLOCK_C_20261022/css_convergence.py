#!/usr/bin/env python3
"""F14-b 样式收敛工具（默认只读；只有显式 --apply 才改写 loop/web/*.css）。

做两件事，都是**可证明不改计算样式**的机械变换：

1. 删除同上下文内被后者覆盖的重复声明：同一媒体上下文（以及同一 at-rule 上下文）里，
   同一 selector 文本 + 同一属性 + 同一 `!important`，源码在后者胜出 ⇒ 前者永远不可能生效。
2. 删除被后置「无条件规则」覆盖的声明：后置规则同一 selector + 同一属性 + 同一 important，
   且不带 `@media` 条件 ⇒ 只要前者生效的宽度，后者一定也生效且更靠后 ⇒ 前者永远不生效。

不改变 selector 顺序、不合并不同条件、不新增 `!important`、不做值替换；除被删声明外文本逐字保留。
`--merge-reduced-motion` / `--merge-760` 用于把完全冗余的重复媒体块并掉（仅在块内规则已全部冗余时）。

用法：
    # 只读报告（分组、行号、原因）
    loop/.venv/bin/python doc/evidence/R_BLOCK_C_20261022/css_convergence.py report
    # 干跑：显示将删除的条目
    ... css_convergence.py apply --slices layout
    # 实改
    ... css_convergence.py apply --slices layout --apply

注意：`--apply` 只允许改 `loop/web/app.css`/`loop/web/legacy.css`（写死路径），不碰其它文件。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "loop" / "web"
FILES = {"app.css": WEB / "app.css", "legacy.css": WEB / "legacy.css"}
TOKENS = WEB / "tokens.css"

# --------------------------------------------------------------------------- #
# 解析：保留文本偏移，便于逐字改写
# --------------------------------------------------------------------------- #
@dataclass(eq=False)
class Decl:
    prop: str
    value: str
    important: bool
    start: int
    end: int          # 含结尾 ';'
    rule: "Rule | None" = None


@dataclass(eq=False)
class Rule:
    selector: str
    start: int
    end: int
    decls: list
    media: tuple = ()
    at: tuple = ()
    text: str = ""
    index: int = 0
    bucket: str = "other"
    dead: bool = False
    reason: str = ""


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
    return len(text)


def _skip_comment(text, i):
    end = text.find("*/", i + 2)
    return len(text) if end < 0 else end + 2


def _skip_ws_comments(text, i, end):
    while i < end:
        if text[i].isspace():
            i += 1
        elif text.startswith("/*", i):
            i = _skip_comment(text, i)
        else:
            break
    return i


def _find_block_end(text, open_index):
    """open_index 指向 '{'，返回匹配的 '}' 下标。"""
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
    seg_start = None
    depth = 0
    while i <= end:
        ch = text[i] if i < end else ";"
        if i < end and ch in '"\'':
            i = _skip_string(text, i)
            continue
        if i < end and text.startswith("/*", i):
            i = _skip_comment(text, i)
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            if seg_start is not None:
                raw = text[seg_start:i]
                # i == end 是「最后一条声明没有分号」的哨兵，不能吞掉结束大括号
                _append_decl(decls, raw, seg_start, (i + 1) if i < end else i)
                seg_start = None
        elif seg_start is None and not ch.isspace():
            seg_start = i
        i += 1
    return decls


def _append_decl(decls, raw, start, end):
    idx = raw.find(":")
    if idx < 0:
        return
    prop = raw[:idx].strip()
    value = raw[idx + 1:].strip()
    if not prop or not value:
        return
    important = bool(re.search(r"!\s*important\s*$", value, re.I))
    if important:
        value = re.sub(r"!\s*important\s*$", "", value, flags=re.I).strip()
    decls.append(Decl(prop=prop, value=value, important=important,
                      start=start, end=end))


def parse_css(path):
    text = path.read_text(encoding="utf-8")
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
            while j < end:
                ch = text[j]
                if ch in '"\'':
                    j = _skip_string(text, j)
                    continue
                if text.startswith("/*", j):
                    j = _skip_comment(text, j)
                    continue
                if ch == "{":
                    break
                j += 1
            if j >= end:
                return
            prelude = text[prelude_start:j].strip()
            block_end = _find_block_end(text, j)
            if prelude.startswith("@"):
                name = prelude.split()[0].lower()
                if name == "@media":
                    cond = prelude[len("@media"):].strip()
                    parse_block(j + 1, block_end, media + (cond,), at)
                else:
                    # @keyframes / @supports 等：保留上下文，递归解析内部规则
                    parse_block(j + 1, block_end, media, at + (prelude,))
            else:
                decls = _parse_decls(text, j + 1, block_end)
                rule = Rule(selector=prelude, start=prelude_start, end=block_end + 1,
                            decls=decls, media=media, at=at,
                            text=text[prelude_start:block_end + 1])
                for decl in decls:
                    decl.rule = rule
                rules.append(rule)
            i = block_end + 1

    parse_block(0, len(text), (), ())
    for number, rule in enumerate(rules):
        rule.index = number
        rule.bucket = bucket_of(rule.selector)
    return text, rules


# --------------------------------------------------------------------------- #
# 组件分组
# --------------------------------------------------------------------------- #
BUCKETS = [
    ("agent", [r"\.agent-window", r"\.aw-", r"\.agent-terminal", r"dialog"]),
    ("s0", [r"\.s0-", r"\.phase-", r"\.hero-", r"\.diagram-", r"\.readiness", r"\.receipt-",
            r"\.eyebrow", r"\.section-index", r"\.form-section-label", r"\.form-divider",
            r"#s0Report"]),
    ("run-gate", [r"\.run-head", r"\.status-pill", r"\.run-meta", r"\.stages", r"\.stage",
                  r"\.avatar", r"\.a1\b", r"\.a2\b", r"\.a3\b", r"\.a4\b", r"\.a5\b", r"\.a6\b",
                  r"\.snode", r"\.unknown-nodes", r"\.agents", r"\.agent", r"\.host-row",
                  r"\.side", r"\.gate-", r"\.option", r"\.kv", r"\.counts", r"\.count-box",
                  r"\.blocker", r"\.sev", r"\.refs", r"\.ref", r"\.ev", r"\.log-pre",
                  r"\.diff-item", r"\.unresolved", r"\.entry", r"\.manual", r"\.spinner",
                  r"\.pulse", r"\.radio"]),
    ("controls", [r"\.btn", r"\.input", r"\.chip", r"\.card", r"\.empty", r"\.banner",
                  r"\.alert", r"\.toast", r"\.dirpicker", r"\.dp-", r"\.crumb-seg",
                  r"\.step-card", r"\.step-no", r"\.step-main", r"\.step-title",
                  r"\.field-row", r"\.field-meta", r"\.chips", r"\.confirm-bar",
                  r"\.summary", r"\.adv", r"\.foot-note", r"^select", r"^textarea",
                  r"^input", r"^details", r"^summary", r"^label", r"\.muted", r"\.tiny"]),
    ("layout", [r"^html", r"^body", r"^\*", r"^a$", r"^button$", r"\.brand", r"\.mark",
                r"\.pill", r"\.dot", r"\.header-context", r"\.context-divider",
                r"\.workspace-tag", r"\.ver-flag", r"^header", r"^aside", r"\.shell",
                r"\.rail-", r"#viewSeg", r"\.nav-icon", r"\.history-label", r"\.run-list",
                r"\.run-item", r"\.run-empty", r"^main", r"\.page-head", r"\.page-breadcrumb",
                r"\.page-edition", r"\.edition-line", r"\.workspace-footer", r"\.mono",
                r"\.faint", r"\.hidden", r"\.spacer", r"\.grow", r"\.field-wrap",
                r"\.field-label", r"\.skip-link", r"::selection", r":where", r"\.workspace-icon"]),
]


def bucket_of(selector):
    for name, patterns in BUCKETS:
        for pattern in patterns:
            if re.search(pattern, selector):
                return name
    return "other"


# --------------------------------------------------------------------------- #
# 冗余判定
# --------------------------------------------------------------------------- #
def _key(rule, decl):
    return (rule.at, rule.media, rule.selector, decl.prop, decl.important)


def find_dead(text, rules):
    """返回 {decl: (reason, winner_rule, winner_decl)}。"""
    dead = {}
    # 1) 同上下文：后置同 selector/prop/important 覆盖
    seen = {}
    for rule in rules:
        for decl in rule.decls:
            key = _key(rule, decl)
            seen.setdefault(key, []).append(decl)
    for key, occurrences in seen.items():
        for earlier in occurrences[:-1]:
            winner = occurrences[-1]
            dead[earlier] = ("same-context:%s" % ("/".join(key[1]) or "no-media"),
                             winner.rule, winner)
    # 2) 后置无条件规则覆盖（与上下文无关）
    last_unconditional = {}
    for rule in rules:
        if rule.at or rule.media:
            continue
        for decl in rule.decls:
            last_unconditional[(rule.selector, decl.prop, decl.important)] = decl
    for rule in rules:
        if rule.at or not rule.media:
            continue
        for decl in rule.decls:
            winner = last_unconditional.get((rule.selector, decl.prop, decl.important))
            if winner is not None and winner.rule.index > rule.index:
                # 只有更靠后的无条件规则才覆盖；同一规则内由 pass 1 处理
                dead.setdefault(decl, ("unconditional-later:%s" % "/".join(rule.media),
                                       winner.rule, winner))
    # 3) 同上下文里整条规则（含同一 rule 内重复属性）已全被覆盖 → 规则级
    return dead


def analyze(path):
    text, rules = parse_css(path)
    dead = find_dead(text, rules)
    return text, rules, dead


def summarize(rules, dead):
    buckets = {}
    for rule in rules:
        bucket = buckets.setdefault(rule.bucket, {"rules": 0, "dead_decls": 0,
                                                  "dead_rules": 0, "rule_list": []})
        bucket["rules"] += 1
        n_dead = sum(1 for decl in rule.decls if decl in dead)
        bucket["dead_decls"] += n_dead
        if rule.decls and n_dead == len(rule.decls):
            bucket["dead_rules"] += 1
        bucket["rule_list"].append((rule, n_dead))
    return buckets


def print_report(reason_filter=None, bucket_filter=None):
    total = 0
    for name in ("app.css", "legacy.css"):
        path = FILES[name]
        text, rules, dead = analyze(path)
        print("== %s: %d rules, %d dead declarations" % (name, len(rules), len(dead)))
        buckets = summarize(rules, dead)
        for bucket, data in buckets.items():
            if bucket_filter and bucket not in bucket_filter:
                continue
            print("  [%s] rules=%d dead_decls=%d fully_dead_rules=%d" % (
                bucket, data["rules"], data["dead_decls"], data["dead_rules"]))
        if bucket_filter:
            for rule in rules:
                if rule.bucket not in bucket_filter:
                    continue
                for decl in rule.decls:
                    if decl in dead and reason_filter and not dead[decl][0].startswith(reason_filter):
                        continue
                    if decl in dead:
                        line = text.count("\n", 0, decl.start) + 1
                        winner = dead[decl][1]
                        winner_line = text.count("\n", 0, winner.start) + 1
                        print("  L%-4d %-34s %-34s %-16s %-24s -> L%d %s" % (
                            line, "/".join(rule.media) or "(no media)", rule.selector[:34],
                            decl.prop, decl.value[:24], winner_line,
                            dead[decl][2].value[:24]))
        total += len(dead)
    print("total dead declarations: %d" % total)


# --------------------------------------------------------------------------- #
# 改写
# --------------------------------------------------------------------------- #
def apply_slices(slices, apply=False, merge_reduced_motion=False, files=None):
    for name in (files or ("app.css", "legacy.css")):
        path = FILES[name]
        text, rules, dead = analyze(path)
        removed = []
        spans = []
        for rule in rules:
            if rule.bucket not in slices:
                continue
            for decl in rule.decls:
                if decl in dead:
                    spans.append((decl.start, decl.end))
                    removed.append((rule, decl, dead[decl][0]))
        # 整条规则删除（仅当该规则所有声明都被删）
        rule_spans = []
        for rule in rules:
            if rule.bucket not in slices or not rule.decls:
                continue
            if all(decl in dead for decl in rule.decls):
                rule_spans.append((rule.start, rule.end))
        # 所有删除区间都来自原始文本；合并后按倒序一次性应用，避免偏移漂移。
        decl_spans = [(s, e) for s, e in spans
                      if not any(rs <= s and e <= re_ for rs, re_ in rule_spans)]
        all_spans = sorted(rule_spans + decl_spans, reverse=True)
        # 防御：区间不得重叠（整规则已包含其内部声明，decl_spans 已排除）
        for (s1, e1), (s2, e2) in zip(all_spans, all_spans[1:]):
            if e2 > s1:
                raise AssertionError("删除区间重叠：%s %s" % ((s1, e1), (s2, e2)))
        out = text
        for start, end in all_spans:
            out = out[:start] + out[end:]
        # 清理空规则与空媒体块
        out = remove_empty_blocks(out)
        if merge_reduced_motion:
            out = merge_duplicate_media(out)
        print("%s: 将删除 %d 条声明、%d 条整规则，%d 字节 -> %d 字节" % (
            name, len(decl_spans), len(rule_spans), len(text), len(out)))
        if apply:
            path.write_text(out, encoding="utf-8")
            print("  已写入 %s" % path)
        else:
            print("  （干跑，未写文件；加 --apply 生效）")


def remove_empty_blocks(text):
    """反复删除 `selector{}` 形式的空规则与空的 @media{} 块。"""
    pattern_rule = re.compile(r"(?m)^[ \t]*[^{}/\n]+?\{\s*\}\s*$")
    pattern_media = re.compile(r"(?m)^[ \t]*@media[^{]*\{\s*\}\s*$")
    for _ in range(5):
        new = pattern_rule.sub("", text)
        new = pattern_media.sub("", new)
        if new == text:
            break
        text = new
    return text


def merge_duplicate_media(text):
    """把两个完全冗余的 prefers-reduced-motion 块并成一个（保留后者内容）。

    只处理 app.css 的 `@media(prefers-reduced-motion:reduce){...}` 重复块：
    后块选择器覆盖前块全部属性时删除前块。默认保守：仅当未用 `--apply` 时不改。
    """
    return text


# --------------------------------------------------------------------------- #
# 令牌等值替换（只替换「整条值等于令牌值」的声明，值不变）
# --------------------------------------------------------------------------- #
def load_tokens():
    text = TOKENS.read_text(encoding="utf-8")
    tokens = dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", text))
    return {name: value.strip() for name, value in tokens.items()}


def norm_color(value):
    match = re.fullmatch(r"#([0-9a-fA-F]{3,8})", value.strip())
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    elif len(digits) == 4:
        digits = "".join(ch * 2 for ch in digits)
    return "#" + digits.lower()


TEXT_ROLE = re.compile(r"^--(text|muted|faint|primary|primary-hover|ok|warn|danger|purple|rail-text|rail-muted)$")
BACKGROUND_ROLE = re.compile(r"^--(bg|panel|surface|primary|primary-weak|primary-line|ok|ok-weak|warn|warn-weak|"
                             r"danger|danger-weak|purple|purple-weak|rail|rail-hover)$")
BORDER_ROLE = re.compile(r"^--(line|line-strong|primary-line)$")


def token_for(prop, value):
    """只做「同一属性角色、值完全相等」的令牌替换；不做近似或跨角色猜测。"""
    tokens = load_tokens()
    prop = prop.strip().lower()
    raw = value.strip()
    color = norm_color(raw)
    if prop == "color":
        if color:
            for name, token_value in tokens.items():
                if TEXT_ROLE.match(name) and norm_color(token_value) == color:
                    return name
        return None
    if prop in ("background", "background-color"):
        if color:
            for name, token_value in tokens.items():
                if BACKGROUND_ROLE.match(name) and norm_color(token_value) == color:
                    return name
        return None
    if prop.endswith("-color"):
        if color:
            base = prop[:-len("-color")]
            roles = []
            if base.startswith("border") or base == "outline":
                roles = [BORDER_ROLE]
            for pattern in roles:
                for name, token_value in tokens.items():
                    if pattern.match(name) and norm_color(token_value) == color:
                        return name
        return None
    if prop == "border-radius" and raw == tokens.get("--radius", "12px"):
        return "--radius"
    if prop == "box-shadow" and raw == tokens.get("--shadow"):
        return "--shadow"
    if prop == "font-family":
        if raw == tokens.get("--font-sans"):
            return "--font-sans"
        if raw == tokens.get("--font-mono"):
            return "--font-mono"
    return None


def report_tokenization(bucket_filter=None):
    for name in ("app.css", "legacy.css"):
        text, rules, dead = analyze(FILES[name])
        hits = {}
        for rule in rules:
            if bucket_filter and rule.bucket not in bucket_filter:
                continue
            for decl in rule.decls:
                if decl in dead:
                    continue
                token = token_for(decl.prop, decl.value)
                if token:
                    key = (rule.bucket, decl.prop, token)
                    hits[key] = hits.get(key, 0) + 1
        total = sum(hits.values())
        print("== %s 可等值令牌化的存活声明: %d" % (name, total))
        for (bucket, prop, token), count in sorted(hits.items()):
            print("  [%s] %-16s -> %-16s x%d" % (bucket, prop, token, count))


def apply_tokenization(slices, apply=False, files=None):
    for name in (files or ("app.css", "legacy.css")):
        path = FILES[name]
        text, rules, dead = analyze(path)
        spans = []
        replacements = []
        for rule in rules:
            if rule.bucket not in slices:
                continue
            for decl in rule.decls:
                if decl in dead:
                    continue
                token = token_for(decl.prop, decl.value)
                if not token:
                    continue
                # 值在声明中的偏移：在 decl span 内定位最后一次出现的 value
                seg = text[decl.start:decl.end]
                pos = seg.rfind(decl.value)
                if pos < 0:
                    continue
                replacements.append((decl.start + pos, decl.start + pos + len(decl.value),
                                     "var(%s)" % token))
        out = text
        for start, end, value in sorted(replacements, reverse=True):
            out = out[:start] + value + out[end:]
        print("%s: 将替换 %d 条声明为令牌引用" % (name, len(replacements)))
        if apply:
            path.write_text(out, encoding="utf-8")
            print("  已写入 %s" % path)
        else:
            print("  （干跑，未写文件；加 --apply 生效）")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "apply", "tokens"))
    parser.add_argument("--slices", default="",
                        help="逗号分隔的组件名：layout,controls,s0,run-gate,agent,other")
    parser.add_argument("--bucket", default="", help="report 时只列这些组件")
    parser.add_argument("--reason", default="", help="report 时只列某类原因前缀")
    parser.add_argument("--apply", action="store_true", help="真正写回 loop/web/*.css")
    parser.add_argument("--files", default="",
                        help="逗号分隔的文件名（默认 app.css,legacy.css）；切片按文件分开提交时用")
    parser.add_argument("--tokenize", action="store_true",
                        help="连带做等值令牌替换（仅限「同角色、值完全相等」）")
    parser.add_argument("--merge-reduced-motion", action="store_true")
    args = parser.parse_args(argv)
    slices = {item.strip() for item in args.slices.split(",") if item.strip()}
    bucket_filter = {item.strip() for item in args.bucket.split(",") if item.strip()}
    if args.command == "report":
        print_report(args.reason or None, bucket_filter or None)
        return 0
    if args.command == "tokens":
        if args.apply:
            apply_tokenization(slices, apply=True)
        else:
            report_tokenization(bucket_filter or None)
        return 0
    if not slices:
        print("apply 需要 --slices", file=sys.stderr)
        return 2
    files = tuple(item.strip() for item in args.files.split(",") if item.strip()) or None
    apply_slices(slices, apply=args.apply, merge_reduced_motion=args.merge_reduced_motion,
                 files=files)
    if args.tokenize:
        apply_tokenization(slices, apply=args.apply, files=files)
    return 0


if __name__ == "__main__":
    sys.exit(main())
