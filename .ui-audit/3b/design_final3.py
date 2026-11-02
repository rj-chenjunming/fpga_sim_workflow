#!/usr/bin/env python3
"""3B-final design, take 3 (deterministic, family-guarded).

Families: neutral (surface/line/text/rail may share a token) | primary | ok |
warn | danger | purple | blue | av.  Cross-family merging is forbidden; the six
avatar identity colours always get their own --av-N token.

Every SOLID literal must land within ΔRGB<=12 of its token; every alpha literal
within <=12 after compositing over its real base colour (shadow/mask alphas are
checked the same way, not exempted).  Existing 24 token values stay frozen.

Construction: per family, greedy covering of the still-uncovered distinct values
with radius-12 balls (centres = literal colour or pairwise midpoint), seeded with
that family's existing tokens; token names come from a fixed name plan so the
result is reviewable.  Writes .ui-audit/3b/final-design.json only.
"""
import collections
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_mapping as B  # noqa: E402

EXISTING = {
    "--panel": ("#ffffff", "neutral"), "--surface": ("#f8faf9", "neutral"),
    "--bg": ("#f4f6f5", "neutral"), "--line": ("#e1e8e4", "neutral"),
    "--line-strong": ("#c7d4cc", "neutral"), "--text": ("#213831", "neutral"),
    "--muted": ("#61746c", "neutral"), "--faint": ("#5f6f67", "neutral"),
    "--primary": ("#15775e", "primary"), "--primary-hover": ("#0e604b", "primary"),
    "--primary-weak": ("#eaf5ef", "primary"), "--primary-line": ("#b8daca", "primary"),
    "--ok": ("#24734d", "ok"), "--ok-weak": ("#edf7ef", "ok"),
    "--warn": ("#9a5e16", "warn"), "--warn-weak": ("#fff6e8", "warn"),
    "--danger": ("#b34140", "danger"), "--danger-weak": ("#fff0ef", "danger"),
    "--purple": ("#7357a0", "purple"), "--purple-weak": ("#f3eef9", "purple"),
    "--rail": ("#192e28", "neutral"), "--rail-hover": ("#243d34", "neutral"),
    "--rail-text": ("#e1eae4", "neutral"), "--rail-muted": ("#a5b9ae", "neutral"),
}
INLINE_TOKENS = [           # for the 3 still-live inline styles of legacy.html
    ("--toast-err", "#ff4d4f", "danger"),
    ("--toast-ok", "#52c41a", "ok"),
    ("--arrow-ink", "#5a6675", "neutral"),
]
ALPHA_TOKENS = [
    ("--overlay", "#12251aab"), ("--rail-tint", "#ffffff08"),
    ("--rail-line", "#ffffff17"), ("--rail-line-strong", "#ffffff30"),
    ("--shadow-tint", "#20372b0a"), ("--shadow-raise", "#173b2426"),
    ("--shadow-pop", "#10291a38"),
]
AV_VALUES = {"--av-1": "#2457d6", "--av-2": "#3c7465", "--av-3": "#7a5a26",
             "--av-4": "#624d80", "--av-5": "#7b4f4f", "--av-6": "#55684f"}
# names are assigned AFTER covering, ordered by lightness (light -> dark)
# name bands: (family) -> [(lightness_floor, [names...])] ; light -> dark
NAME_BANDS = {
    "neutral": [(0.92, ["--surface-2", "--surface-3"]),
                (0.80, ["--line-soft", "--line-warm", "--line-tint"]),
                (0.62, ["--rail-accent", "--rail-muted-2", "--neutral-4"]),
                (0.42, ["--text-4", "--text-5", "--neutral-5"]),
                (0.28, ["--text-2", "--text-3"]),
                (0.16, ["--rail-border", "--rail-active"]),
                (0.0, ["--rail-deep"])],
    "warn": [(0.86, ["--warn-tint", "--warn-line-soft"]),
             (0.72, ["--warn-line", "--warn-line-3"]),
             (0.52, ["--warn-accent", "--warn-line-4"]),
             (0.0, ["--warn-ink"])],
    "danger": [(0.84, ["--danger-line", "--danger-line-soft", "--danger-line-3"]),
               (0.60, ["--danger-ink-soft"])],
    "ok": [(0.80, ["--ok-line", "--ok-line-2"]), (0.0, ["--ok-ink"])],
    "primary": [(0.85, ["--primary-weak-2"]), (0.0, ["--primary-ink"])],
    "purple": [(0.85, ["--purple-line"]), (0.0, ["--purple-ink-soft"])],
    "blue": [(0.80, ["--meta-blue-line"]), (0.0, ["--meta-blue"])],
}
FAM_ORDER = ["neutral", "primary", "ok", "warn", "danger", "purple", "blue"]


def rgb_of(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def drgb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


HINTS = [
    (r"check-passed|status-pill\.done|chip\.ok|bg-ok|msg-ok|ref-ok", "ok"),
    (r"banner\.bad|alert\.bad|check-failed|\.conn\b|warn-banner|ccard-red|btn-danger|ref-missing|"
     r"sev-blocker|diff-pane\.before|bg-red|msg-err|s0-switch-msg-bad", "danger"),
    (r"banner\.warn|alert\.warn|snode\.wait|agent\.waiting|s0-blockers|readiness|s0-rehearsal|"
     r"\.missing\b|option\.on|warning|sev-defect|\.note\b|nd-mode-note|nohunk|s0-switch-msg-warn", "warn"),
    (r"purple|bg-purple", "purple"),
]


def family_of(rgb, selector="", prop="", use_av=True):
    if use_av and re.search(r"\.a([1-6])\b", selector):
        return "av"
    for pat, fam in HINTS:
        if re.search(pat, selector + " " + prop):
            return fam
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    chroma = mx - mn
    l = (mx + mn) / 2 / 255
    if chroma <= 12:
        return "neutral"
    if l > 0.78:                      # light tints: hue decides the family
        if b - r >= 10 and b - g >= 6:
            return "purple"
        if r - b >= 10:
            return "danger" if (r - g) > 15 and (g - b) < 26 else "warn"
        return "neutral"
    if r > g >= b:
        return "danger" if (r - g) > 15 and (g - b) < 10 else "warn"
    if r > b > g:
        return "purple" if r - g > 8 else "danger"
    if b > r and b > g:
        if l > 0.78:
            return "neutral"
        return "blue" if (b - r) > 40 else "neutral"
    return "neutral"


def route_alpha(rgb, a):
    if a >= 140:
        return "--overlay", (244, 246, 245)
    if rgb == (255, 255, 255):
        base = (25, 46, 40)
        if a <= 14:
            return "--rail-tint", base
        return ("--rail-line", base) if a <= 36 else ("--rail-line-strong", base)
    base = (244, 246, 245)
    if max(rgb) < 90:
        if a <= 20:
            return "--shadow-tint", base
        return ("--shadow-raise", base) if a < 48 else ("--shadow-pop", base)
    return "--shadow-tint", base


def composite(c, a, base):
    f = a / 255.0
    return tuple(round(f * c[i] + (1 - f) * base[i]) for i in range(3))


def main():
    inv = json.load(open(os.path.join(HERE, "color-inventory.json"), encoding="utf-8"))
    occ = [e for e in inv["entries"] if e["rgb"] and e["file"] in B.CSS_FILES]
    solid = collections.defaultdict(list)
    for e in occ:
        if e["alpha"] in (None, 255):
            solid[e["hex8"]].append(e)

    fam = {}
    pinned = {v for v in AV_VALUES.values()}
    for hexs, es in solid.items():
        if hexs in pinned:
            fam[hexs] = "av"
            continue
        votes = collections.Counter(
            family_of(rgb_of(hexs), e["selector"], e["property"], use_av=False) for e in es)
        fam[hexs] = votes.most_common(1)[0][0]

    # avatar identity colours are pinned one-to-one, never geometrically merged
    av_pin = {}
    for name, val in AV_VALUES.items():
        av_pin[val] = name
        fam[val] = "av"

    centers = {n: rgb_of(v) for n, (v, f) in EXISTING.items()}
    fam_tok = {n: f for n, (v, f) in EXISTING.items()}
    covered = {}
    for hexs, f in fam.items():
        if f == "av":
            continue
        cand = [(drgb(rgb_of(hexs), c), n) for n, c in centers.items() if fam_tok[n] == f]
        if cand:
            d, n = min(cand)
            if d <= 12:
                covered[hexs] = n

    new = []
    for f in FAM_ORDER:
        pool = {v for v in fam if fam[v] == f and v not in covered}
        if not pool:
            continue
        vals = sorted(pool)
        cands = set(vals)
        for a, b in itertools.combinations(vals, 2):
            if drgb(rgb_of(a), rgb_of(b)) <= 24:
                ra, rb = rgb_of(a), rgb_of(b)
                cands.add("#%02x%02x%02x" % tuple((ra[i] + rb[i]) // 2 for i in range(3)))
        while pool:
            best = None
            for c in cands:
                grp = [v for v in pool if drgb(rgb_of(c), rgb_of(v)) <= 12]
                if not grp:
                    continue
                w = sum(len(solid[v]) for v in grp)
                if best is None or (w, len(grp)) > (best[0], best[1]):
                    best = (w, len(grp), c, grp)
            w, ncnt, c, grp = best
            new.append({"value": c, "family": f, "members": sorted(grp)})
            for v in grp:
                pool.discard(v)

    def light(h):
        r, g, b = rgb_of(h)[:3]
        return (max(r, g, b) + min(r, g, b)) / 510.0

    used_names = set()
    for f in FAM_ORDER:
        cl = sorted([c for c in new if c["family"] == f], key=lambda c: -light(c["value"]))
        bands = NAME_BANDS.get(f, [])
        queues = []
        for _, names in bands:
            queues.extend(names)
        for i, c in enumerate(cl):
            L = light(c["value"])
            nm = None
            for floor, names in bands:
                if L >= floor and names:
                    nm = names.pop(0)
                    break
            if nm is None or nm in used_names:
                k = i + 1
                while "--%s-%d" % (f, k) in used_names:
                    k += 1
                nm = "--%s-%d" % (f, k)
            used_names.add(nm)
            c["name"] = nm
    for c in new:
        centers[c["name"]] = rgb_of(c["value"])
        fam_tok[c["name"]] = c["family"]
        for v in c["members"]:
            covered[v] = c["name"]

    tokens = [{"name": n, "value": v, "family": f, "existing": True}
              for n, (v, f) in EXISTING.items()]
    tokens += [{"name": d["name"], "value": d["value"], "family": d["family"],
                "members": d["members"]} for d in new]
    tokens += [{"name": n, "value": v, "family": "alpha"} for n, v in ALPHA_TOKENS]
    tokens += [{"name": n, "value": v, "family": f, "inline_only": True}
               for n, v, f in INLINE_TOKENS]
    tokens += [{"name": n, "value": v, "family": "av", "members": [v]} for n, v in AV_VALUES.items()]
    tok_rgb = {t["name"]: rgb_of(t["value"]) for t in tokens}
    tok_fam = {t["name"]: t["family"] for t in tokens}
    # the 3 inline-only tokens serve legacy.html ONLY: never absorb CSS literals
    inline_only = {t["name"] for t in tokens if t.get("inline_only")}

    rows = []
    for e in occ:
        lit = e["literal"]
        al = int(lit[7:9], 16) if (lit.startswith("#") and len(lit) == 9) else \
            (e["alpha"] if e["alpha"] is not None else 255)
        c = rgb_of(e["hex8"])
        if al != 255:
            name, base = route_alpha(c, al)
            ta = int(tok_rgb[name] and tokens[[t["name"] for t in tokens].index(name)]["value"][7:9], 16)
            d = max(abs(x - y) for x, y in zip(composite(c, al, base),
                                               composite(tok_rgb[name], ta, base)))
            rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                         "selector": e["selector"], "current": lit, "token": name,
                         "delta": d, "alpha": al, "token_alpha": ta, "kind": "alpha"})
            continue
        f = fam[e["hex8"]]
        if f == "av":
            name = av_pin[e["hex8"]]
        else:
            pool = [n for n in tok_rgb if tok_fam[n] == f and n not in inline_only]
            name = min(pool, key=lambda n: (drgb(c, tok_rgb[n]), n))
        rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                     "selector": e["selector"], "current": lit, "token": name,
                     "delta": drgb(c, tok_rgb[name]), "alpha": 255, "kind": "solid"})

    sr = [r for r in rows if r["kind"] == "solid"]
    ar = [r for r in rows if r["kind"] == "alpha"]
    bad = [r for r in sr if r["delta"] > 12]
    bad_a = [r for r in ar if r["delta"] > 12]
    counts = collections.Counter(t["family"] for t in tokens)
    print("tokens total=%d  (existing 24 + new %d + alpha %d + av %d + inline %d)  by family=%s" % (
        len(tokens), len(new), len(ALPHA_TOKENS), len(AV_VALUES), len(INLINE_TOKENS), dict(counts)))
    print("solid rows=%d maxΔ=%d  >12: %d" % (len(sr), max(r["delta"] for r in sr), len(bad)))
    print("alpha rows=%d max composite Δ=%d  >12: %d" % (len(ar), max(r["delta"] for r in ar), len(bad_a)))
    for r in bad[:10]:
        print("  BAD", r["current"], "->", r["token"], r["delta"], r["selector"][:40])
    for r in bad_a[:10]:
        print("  BAD-α", r["current"], "->", r["token"], r["delta"], r["selector"][:40])

    json.dump({"tokens": tokens, "rows": rows,
               "stats": {"tokens": len(tokens), "solid_rows": len(sr), "alpha_rows": len(ar),
                         "max_solid_delta": max(r["delta"] for r in sr),
                         "max_alpha_delta": max(r["delta"] for r in ar),
                         "bad_solid": len(bad), "bad_alpha": len(bad_a),
                         "by_family": dict(counts), "baseline": inv["baseline"]}},
              open(os.path.join(HERE, "final-design.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote final-design.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
