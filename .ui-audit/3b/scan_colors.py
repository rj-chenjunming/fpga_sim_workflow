#!/usr/bin/env python3
"""3B-1 color inventory: scan CSS for colour literals with selector/property context.

Read-only. Outputs .ui-audit/3b/color-inventory.json.
Usage: python3 .ui-audit/3b/scan_colors.py
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "color-inventory.json")

SNAP = os.environ.get("UI3B_SNAP") == "1"   # analyse the pinned snapshot, not the live tree
SNAPDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snap")

TARGETS = [
    ("loop/web/app.css", None, None),
    ("loop/web/legacy.css", None, None),
    # inline <style> of legacy.html: lines 8..161 (inclusive), line numbers are
    # kept as the real file lines so implementers can jump to them.
    ("loop/web/legacy.html", 8, 161),
]

NAMED = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "blue": (0, 0, 255),
    "green": (0, 128, 0),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "silver": (192, 192, 192),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "purple": (128, 0, 128),
    "lime": (0, 255, 0),
    "teal": (0, 128, 128),
    "navy": (0, 0, 128),
    "maroon": (128, 0, 0),
    "olive": (128, 128, 0),
    "aqua": (0, 255, 255),
    "cyan": (0, 255, 255),
    "fuchsia": (255, 0, 255),
    "magenta": (255, 0, 255),
}
KEYWORDS = {"transparent", "currentcolor", "inherit", "initial", "unset", "none", "auto", "revert"}

HEX_RE = re.compile(r"#([0-9a-fA-F]+)")
FUNC_RE = re.compile(r"\b(rgba?|hsla?)\(\s*([^()]*)\)")
NAMED_RE = re.compile(r"\b(" + "|".join(sorted(NAMED, key=len, reverse=True)) + r")\b")
KEYWORD_RE = re.compile(r"\b(" + "|".join(sorted(KEYWORDS, key=len, reverse=True)) + r")\b")


def parse_hex(digits):
    n = len(digits)
    if n == 3:
        return tuple(int(c * 2, 16) for c in digits), 255, "hex3"
    if n == 4:
        return tuple(int(c * 2, 16) for c in digits[:3]), int(digits[3] * 2, 16), "hex4"
    if n == 6:
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4)), 255, "hex6"
    if n == 8:
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4)), int(digits[6:8], 16), "hex8"
    return None, None, None


def parse_func(name, args):
    parts = [p.strip() for p in re.split(r"[,\s/]+", args.strip()) if p.strip()]
    try:
        if name.startswith("rgb"):
            vals = []
            for p in parts[:3]:
                if p.endswith("%"):
                    vals.append(round(float(p[:-1]) * 2.55))
                else:
                    vals.append(round(float(p)))
            alpha = 255
            if len(parts) >= 4:
                a = parts[3]
                alpha = round(float(a[:-1]) / 100 * 255) if a.endswith("%") else round(float(a) * 255)
            return tuple(vals), alpha, "rgb" if name == "rgb" else "rgba"
        # hsl
        import colorsys
        h = float(parts[0].rstrip("deg")) % 360
        s = float(parts[1].rstrip("%")) / 100
        l = float(parts[2].rstrip("%")) / 100
        r, g, b = colorsys.hls_to_rgb(h / 360.0, l, s)
        alpha = 255
        if len(parts) >= 4:
            a = parts[3]
            alpha = round(float(a[:-1]) / 100 * 255) if a.endswith("%") else round(float(a) * 255)
        return (round(r * 255), round(g * 255), round(b * 255)), alpha, "hsl"
    except Exception:
        return None, None, None


def iter_declarations(text, line_offset):
    """Yield (line, selector, at_context, prop, value) for each declaration."""
    i, n = 0, len(text)
    line = 1 + (line_offset or 0)
    stack = []          # list of preludes ("@media(...)", ".foo", "@keyframes x")
    buf = []            # current prelude/declaration chars
    prop = None
    in_comment = False
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            buf.append(ch)
            i += 1
            continue
        if in_comment:
            if text.startswith("*/", i):
                in_comment = False
                i += 2
            else:
                i += 1
            continue
        if text.startswith("/*", i):
            in_comment = True
            i += 2
            continue
        if ch == "{":
            prelude = "".join(buf).strip()
            buf = []
            stack.append(prelude)
            prop = None
            i += 1
            continue
        if ch == "}":
            if prop is not None and buf:
                selector = stack[-1] if stack else ""
                ats = [s for s in stack[:-1] if s.startswith("@")]
                yield line, selector, " ".join(ats), prop, "".join(buf)
            buf = []
            if stack:
                stack.pop()
            prop = None
            i += 1
            continue
        if ch == ";":
            decl = "".join(buf)
            buf = []
            if prop is not None:
                selector = stack[-1] if stack else ""
                ats = [s for s in stack[:-1] if s.startswith("@")]
                yield line, selector, " ".join(ats), prop, decl
            prop = None
            i += 1
            continue
        if ch == ":" and prop is None and stack and not all(s.startswith("@") for s in stack):
            # property of a declaration (only inside a rule block)
            prop = "".join(buf).strip().lower()
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    # last declaration without trailing ';'
    if prop is not None and buf:
        selector = stack[-1] if stack else ""
        ats = [s for s in stack[:-1] if s.startswith("@")]
        yield line, selector, " ".join(ats), prop, "".join(buf)


def scan_file(rel, start, end):
    path = os.path.join(SNAPDIR, os.path.basename(rel)) if SNAP else os.path.join(ROOT, rel)
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    if start is not None:
        text = "".join(lines[start - 1:end])
        offset = start - 1
    else:
        text = "".join(lines)
        offset = 0
    entries = []
    for decl_line, selector, ats, prop, value in iter_declarations(text, offset):
        found = []
        for m in HEX_RE.finditer(value):
            rgb, alpha, kind = parse_hex(m.group(1))
            if rgb is None:
                continue  # not a valid 3/4/6/8 hex -> not a colour
            found.append((m.start(), m.group(0), kind, rgb, alpha))
        for m in FUNC_RE.finditer(value):
            rgb, alpha, kind = parse_func(m.group(1), m.group(2))
            if rgb is None:
                continue
            found.append((m.start(), m.group(0), kind, rgb, alpha))
        for m in NAMED_RE.finditer(value):
            word = m.group(1)
            # guard: skip when it is part of an identifier such as --font-sans
            if m.start() > 0 and (value[m.start() - 1].isalnum() or value[m.start() - 1] in "-_"):
                continue
            found.append((m.start(), word, "named", NAMED[word], 255))
        for m in KEYWORD_RE.finditer(value):
            found.append((m.start(), m.group(1), "keyword", None, None))
        found.sort(key=lambda t: t[0])
        for _, literal, kind, rgb, alpha in found:
            entries.append({
                "file": rel,
                "line": decl_line,
                "selector": selector,
                "at_context": ats,
                "property": prop,
                "literal": literal,
                "kind": kind,
                "rgb": list(rgb) if rgb else None,
                "hex8": ("#%02x%02x%02x" % rgb) if rgb else None,
                "alpha": alpha,
            })
    return entries


def main():
    all_entries = []
    per_file = {}
    for rel, start, end in TARGETS:
        ents = scan_file(rel, start, end)
        all_entries.extend(ents)
        per_file[rel] = {
            "occurrences": len(ents),
            "color_occurrences": sum(1 for e in ents if e["rgb"] is not None),
            "keyword_occurrences": sum(1 for e in ents if e["rgb"] is None),
        }

    colors = [e for e in all_entries if e["rgb"] is not None]
    distinct = {}
    for e in colors:
        key = "#%02x%02x%02x" % tuple(e["rgb"])
        alpha = e["alpha"] if e["alpha"] is not None else 255
        k2 = (key, alpha)
        if k2 not in distinct:
            distinct[k2] = {"hex": key, "alpha": alpha, "count": 0, "sample": []}
        distinct[k2]["count"] += 1
        if len(distinct[k2]["sample"]) < 3:
            distinct[k2]["sample"].append("%s:%s %s %s" % (e["file"].split("/")[-1], e["line"], e["selector"], e["property"]))

    distinct_by_hex = {}
    for k2, v in distinct.items():
        distinct_by_hex.setdefault(v["hex"], 0)
        distinct_by_hex[v["hex"]] += v["count"]

    import hashlib
    baseline = {}
    for rel in ("loop/web/app.css", "loop/web/legacy.css", "loop/web/tokens.css"):
        p = os.path.join(SNAPDIR, os.path.basename(rel)) if SNAP else os.path.join(ROOT, rel)
        with open(p, "rb") as fh:
            raw = fh.read()
        baseline[rel] = {"md5": hashlib.md5(raw).hexdigest(),
                         "lines": raw.count(b"\n"),
                         "source": "snapshot" if SNAP else "live"}
    doc = {
        "generated_by": ".ui-audit/3b/scan_colors.py",
        "baseline": baseline,
        "scope": ["loop/web/app.css", "loop/web/legacy.css", "loop/web/legacy.html (inline <style> L8-L161)"],
        "excluded": ["loop/web/mockup.html (§14: 静态历史样张不参与)", "favicon.svg"],
        "stats": {
            "occurrences_total_incl_keywords": len(all_entries),
            "color_occurrences": len(colors),
            "distinct_values_by_rgb": len(distinct_by_hex),
            "distinct_values_by_rgb_and_alpha": len(distinct),
            "per_file": per_file,
            "by_kind": {},
        },
        "distinct_values": [
            {"hex": h, "count": c} for h, c in sorted(distinct_by_hex.items(), key=lambda kv: -kv[1])
        ],
        "distinct_values_with_alpha": [
            {"hex": v["hex"], "alpha": v["alpha"], "count": v["count"], "sample": v["sample"]}
            for v in sorted(distinct.values(), key=lambda v: -v["count"])
            if v["alpha"] != 255
        ],
        "entries": all_entries,
    }
    for e in colors:
        doc["stats"]["by_kind"][e["kind"]] = doc["stats"]["by_kind"].get(e["kind"], 0) + 1

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    s = doc["stats"]
    print("wrote", OUT)
    print("occurrences (color only) =", s["color_occurrences"])
    print("occurrences (incl. keywords) =", s["occurrences_total_incl_keywords"])
    print("distinct rgb =", s["distinct_values_by_rgb"])
    print("distinct rgb+alpha =", s["distinct_values_by_rgb_and_alpha"])
    print("by kind =", s["by_kind"])
    for f, v in s["per_file"].items():
        print("  %-24s color=%-4d keyword=%-3d" % (f, v["color_occurrences"], v["keyword_occurrences"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
