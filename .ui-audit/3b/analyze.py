#!/usr/bin/env python3
"""3B-2 exploration: nearest-token assignment against the §5.2 proposal.

Read-only helper; prints diagnostics only (no files written).
"""
import json
import os
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
INV = os.path.join(HERE, "color-inventory.json")

# §5.2 proposal (accepted palette), family-tagged. value = suggested colour.
TOKENS = [
    # group, token, value, role
    ("底", "--panel", "#ffffff", "surface"),
    ("底", "--surface", "#f8faf9", "surface"),
    ("底", "--surface-2", "#fcfdfb", "surface"),
    ("底", "--surface-3", "#f6f9f4", "surface"),
    ("底", "--bg", "#f4f6f5", "surface"),
    ("线", "--line", "#e1e8e4", "line"),
    ("线", "--line-strong", "#c7d4cc", "line"),
    ("线", "--line-soft", "#eef1f5", "line"),
    ("字", "--text", "#213831", "text"),
    ("字", "--text-2", "#3d5545", "text"),
    ("字", "--muted", "#61746c", "text"),
    ("字", "--faint", "#5f6f67", "text"),
    ("主色", "--primary", "#15775e", "solid"),
    ("主色", "--primary-hover", "#0e604b", "solid"),
    ("主色", "--primary-weak", "#eaf5ef", "weak"),
    ("主色", "--primary-line", "#b8daca", "line"),
    ("成功", "--ok", "#24734d", "solid"),
    ("成功", "--ok-weak", "#edf7ef", "weak"),
    ("成功", "--ok-line", "#bfe8d8", "line"),
    ("警告", "--warn", "#9a5e16", "solid"),
    ("警告", "--warn-weak", "#fff6e8", "weak"),
    ("警告", "--warn-line", "#f3d19e", "line"),
    ("警告", "--warn-line-soft", "#ead7b7", "line"),
    ("警告", "--warn-ink", "#7a6234", "text"),
    ("危险", "--danger", "#b34140", "solid"),
    ("危险", "--danger-weak", "#fff0ef", "weak"),
    ("危险", "--danger-line", "#f5c6c6", "line"),
    ("危险", "--danger-line-soft", "#ebc4bf", "line"),
    ("紫", "--purple", "#7357a0", "solid"),
    ("紫", "--purple-weak", "#f3eef9", "weak"),
    ("紫", "--purple-line", "#e1d8ec", "line"),
    ("侧栏", "--rail", "#192e28", "rail"),
    ("侧栏", "--rail-hover", "#243d34", "rail"),
    ("侧栏", "--rail-active", "#304b3d", "rail"),
    ("侧栏", "--rail-border", "#3a5a4a", "rail"),
    ("侧栏", "--rail-text", "#e1eae4", "rail"),
    ("侧栏", "--rail-muted", "#a5b9ae", "rail"),
    ("侧栏", "--rail-accent", "#b9d5aa", "rail"),
    ("浮层/日志", "--overlay", "#12251ab3", "overlay"),
    ("浮层/日志", "--mono-bg", "#20382b", "mono"),
    ("浮层/日志", "--mono-text", "#dde8dc", "mono"),
]


def rgb(hexs):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def drgb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def main():
    inv = json.load(open(INV, encoding="utf-8"))
    ents = [e for e in inv["entries"]
            if e["rgb"] and e["file"] in ("loop/web/app.css", "loop/web/legacy.css")]
    agg = collections.defaultdict(lambda: {"n": 0, "ctx": [], "alpha": set()})
    for e in ents:
        key = e["hex8"]
        a = agg[key]
        a["n"] += 1
        a["alpha"].add(e["alpha"])
        if len(a["ctx"]) < 3:
            a["ctx"].append("%s:%s:%s" % (e["file"].split("/")[-1], e["property"], e["selector"][:34]))
    print("distinct in app+legacy.css:", len(agg), " occurrences:", len(ents))

    tok_rgb = [(g, n, rgb(v), v, r) for g, n, v, r in TOKENS]
    assign = collections.defaultdict(list)
    over = []
    for hexs, a in agg.items():
        c = rgb(hexs)
        best = min(tok_rgb, key=lambda t: drgb(c, t[2]))
        d = drgb(c, best[2])
        assign[best[1]].append((hexs, d, a["n"]))
        if d > 12:
            over.append((hexs, c, best[1], best[3], d, a["n"], a["ctx"]))

    print("\n=== per-token absorption (distinct / occurrences) ===")
    for g, n, v, val, r in tok_rgb:
        mem = assign[n]
        occ = sum(m[2] for m in mem)
        print("%-6s %-20s %-9s distinct=%-3d occ=%-4d maxΔ=%-3s %s" % (
            g, n, val, len(mem), occ,
            max((m[1] for m in mem), default="-"),
            ",".join("%s(%d)" % (m[0], m[1]) for m in sorted(mem, key=lambda x: -x[1])[:4])))

    print("\n=== ΔRGB > 12 (%d distinct) ===" % len(over))
    for hexs, c, n, val, d, cnt, ctx in sorted(over, key=lambda x: -x[4]):
        print("%s -> %-18s %-9s Δ=%-3d n=%-2d  %s" % (hexs, n, val, d, cnt, " | ".join(ctx[:2])))

    print("\nunmapped check: every distinct colour got exactly one token?",
          sum(len(v) for v in assign.values()) == len(agg))


if __name__ == "__main__":
    main()
