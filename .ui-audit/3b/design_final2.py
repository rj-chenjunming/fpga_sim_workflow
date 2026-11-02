#!/usr/bin/env python3
"""3B-final design, take 2: semantic-family-aware cover.

Goal (lead's ruling A): every SOLID literal lands within ΔRGB<=12 of its token;
alpha literals land within <=12 after compositing over their real base; families
are never merged (success / warn / danger / purple / ok / av keep their own
tokens).  Existing 24 token values stay frozen.

Method: per semantic family, greedy cover of the remaining distinct values with
radius-12 balls whose centres are literal colours or pairwise midpoints, seeded
with the existing tokens of that family.  Token names are assigned afterwards
from the family + the cluster's own role.

Writes only .ui-audit/3b/final-design.json.
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
    "--panel": ("#ffffff", "surface"), "--surface": ("#f8faf9", "surface"),
    "--bg": ("#f4f6f5", "surface"), "--line": ("#e1e8e4", "line"),
    "--line-strong": ("#c7d4cc", "line"), "--text": ("#213831", "text"),
    "--muted": ("#61746c", "text"), "--faint": ("#5f6f67", "text"),
    "--primary": ("#15775e", "primary"), "--primary-hover": ("#0e604b", "primary"),
    "--primary-weak": ("#eaf5ef", "primary"), "--primary-line": ("#b8daca", "primary"),
    "--ok": ("#24734d", "ok"), "--ok-weak": ("#edf7ef", "ok"),
    "--warn": ("#9a5e16", "warn"), "--warn-weak": ("#fff6e8", "warn"),
    "--danger": ("#b34140", "danger"), "--danger-weak": ("#fff0ef", "danger"),
    "--purple": ("#7357a0", "purple"), "--purple-weak": ("#f3eef9", "purple"),
    "--rail": ("#192e28", "rail"), "--rail-hover": ("#243d34", "rail"),
    "--rail-text": ("#e1eae4", "rail"), "--rail-muted": ("#a5b9ae", "rail"),
}
ALPHA_TOKENS = [
    ("--overlay", "#12251aab"), ("--rail-tint", "#ffffff08"),
    ("--rail-line", "#ffffff17"), ("--rail-line-strong", "#ffffff30"),
    ("--shadow-tint", "#20372b0a"), ("--shadow-raise", "#173b2426"),
    ("--shadow-pop", "#10291a38"),
]
AV = {"--av-1": "#2457d6", "--av-2": "#3c7465", "--av-3": "#7a5a26",
      "--av-4": "#624d80", "--av-5": "#7b4f4f", "--av-6": "#55684f"}
# naming plan for new semantic tokens: (family, candidate name, role hint)
NAME_PLAN = {
    "neutral": ["--surface-2", "--surface-3", "--line-soft", "--line-warm",
                "--line-tint", "--text-2", "--text-3", "--text-4", "--text-5",
                "--rail-active", "--rail-border", "--rail-accent", "--rail-muted-2",
                "--rail-deep", "--neutral-15", "--neutral-16"],
    "warn": ["--warn-line", "--warn-line-soft", "--warn-ink", "--warn-accent", "--warn-tint"],
    "danger": ["--danger-line", "--danger-line-soft", "--danger-ink"],
    "ok": ["--ok-line", "--ok-ink"],
    "primary": ["--primary-ink"],
    "purple": ["--purple-line"],
    "blue": ["--meta-blue"],
    "av": [],
}
FAM_ORDER = ["neutral", "primary", "ok", "warn", "danger", "purple", "blue", "av"]


def rgb_of(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def drgb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def family_of(rgb, sel=""):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    chroma = mx - mn
    l = (mx + mn) / 2 / 255
    if re.search(r"\.a([1-6])\b", sel):
        return "av"
    if chroma <= 10:
        return "neutral"
    if r > g >= b:
        if (r - g) > 15 and (g - b) < 10:
            return "danger"
        return "warn"
    if r > b > g:
        return "purple" if r - g > 8 else "danger"
    if b > r and b > g:
        if l > 0.80:
            return "neutral"
        if (b - r) > 18:
            return "blue"
        return "neutral"
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
    # family per distinct value = majority vote over its occurrences
    fam = {}
    for hexs, es in solid.items():
        votes = collections.Counter(family_of(rgb_of(hexs), e["selector"]) for e in es)
        fam[hexs] = votes.most_common(1)[0][0]

    centers = {n: rgb_of(v) for n, (v, f) in EXISTING.items()}
    fam_of_tok = {n: ("neutral" if f in ("surface", "line", "text", "rail") else f)
                  for n, (v, f) in EXISTING.items()}
    covered = collections.defaultdict(dict)   # family -> value -> token
    for hexs, f in fam.items():
        best = min(((drgb(rgb_of(hexs), c), n) for n, c in centers.items()
                    if fam_of_tok[n] == f), default=None, key=lambda t: t[0])
        if best and best[0] <= 12:
            covered[f][hexs] = best[1]

    # ---- per family: greedily add radius-12 balls until everything is covered
    new = []
    for f in FAM_ORDER:
        vals = [v for v in fam if fam[v] == f and v not in covered[f]]
        if not vals:
            continue
        pool = set(vals)
        cands = set(vals)
        for a, b in itertools.combinations(vals, 2):
            if drgb(rgb_of(a), rgb_of(b)) <= 24:
                ra, rb = rgb_of(a), rgb_of(b)
                cands.add("#%02x%02x%02x" % tuple((ra[i] + rb[i]) // 2 for i in range(3)))
        names = list(NAME_PLAN.get(f, []))
        while pool:
            best = None
            for c in cands:
                grp = [v for v in pool if drgb(rgb_of(c), rgb_of(v)) <= 12]
                if not grp:
                    continue
                w = sum(len(solid[v]) for v in grp)
                if best is None or (w, len(grp)) > (best[0], best[1]):
                    best = (w, len(grp), c, grp)
            w, n, c, grp = best
            name = names.pop(0) if names else "--%s-%d" % (f, len(new))
            new.append((name, c, f, list(grp)))
            for v in grp:
                pool.discard(v)
            centers[name] = rgb_of(c)
            fam_of_tok[name] = f

    tokens = []
    for n, (v, f) in EXISTING.items():
        tokens.append({"name": n, "value": v, "family": f, "existing": True})
    for name, c, f, grp in new:
        tokens.append({"name": name, "value": c, "family": f, "existing": False,
                       "members": sorted(grp)})
    for n, v in ALPHA_TOKENS:
        tokens.append({"name": n, "value": v, "family": "alpha", "existing": False})
    for n, v in AV.items():
        if n != "--av-6" or True:
            pass
    # avatar identity colours: one token each (override the geometric family)
    av_vals = {}
    for hexs, es in solid.items():
        if any(re.search(r"\.a([1-6])\b", e["selector"]) for e in es):
            m = next(re.search(r"\.a([1-6])\b", e["selector"]).group(1) for e in es
                     if re.search(r"\.a([1-6])\b", e["selector"]))
            avn = "--av-%s" % m
            if avn not in av_vals:
                av_vals[avn] = hexs

    print("existing:", len(EXISTING), "new semantic:", len(new), "alpha:", len(ALPHA_TOKENS),
          "avatar:", len(av_vals), "=> total", len(EXISTING) + len(new) + len(ALPHA_TOKENS) + len(av_vals))

    # ---------------- assignment + verification -------------------------
    tok_rgb = {t["name"]: rgb_of(t["value"]) for t in tokens}
    for n, v in av_vals.items():
        tok_rgb[n] = rgb_of(v)
        tokens.append({"name": n, "value": v, "family": "av", "existing": False,
                       "members": [v]})
    tok_family = {t["name"]: t["family"] for t in tokens}
    rows = []
    worst = 0
    worst_row = None
    for e in occ:
        al = int(e["literal"][7:9], 16) if (e["literal"].startswith("#") and len(e["literal"]) == 9) \
            else (e["alpha"] if e["alpha"] is not None else 255)
        c = rgb_of(e["hex8"])
        if al != 255:
            name, base = route_alpha(c, al)
            ta = int(tok_rgb and next(t for t in tokens if t["name"] == name)["value"][7:9], 16)
            dcomp = max(abs(a - b) for a, b in zip(composite(c, al, base),
                                                   composite(tok_rgb[name], ta, base)))
            rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                         "selector": e["selector"], "current": e["literal"], "token": name,
                         "delta": dcomp, "alpha": al, "alpha_token": ta, "kind": "alpha"})
            continue
        f = fam[e["hex8"]]
        # avatar ink wins over geometry
        avn = None
        for cand in av_vals:
            if drgb(c, tok_rgb[cand]) == 0:
                avn = cand
        pool = [n for n in tok_rgb if n in {t["name"] for t in tokens}
                and tok_family[n] in (f, "av") and tok_family[n] != "alpha"]
        name = min(pool, key=lambda n: (drgb(c, tok_rgb[n]), n))
        d = drgb(c, tok_rgb[name])
        rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                     "selector": e["selector"], "current": e["literal"], "token": name,
                     "delta": d, "alpha": 255, "kind": "solid"})
        if d > worst:
            worst, worst_row = d, rows[-1]

    solid_rows = [r for r in rows if r["kind"] == "solid"]
    alpha_rows = [r for r in rows if r["kind"] == "alpha"]
    bad_solid = [r for r in solid_rows if r["delta"] > 12]
    worst_alpha = max(r["delta"] for r in alpha_rows)
    print("solid rows:", len(solid_rows), "max Δ:", max(r["delta"] for r in solid_rows),
          ">12:", len(bad_solid))
    print("alpha rows:", len(alpha_rows), "max composite Δ:", worst_alpha)
    for r in bad_solid[:12]:
        print("  BAD", r["current"], "->", r["token"], r["delta"], r["selector"][:40])

    out = {"tokens": tokens, "rows": rows,
           "stats": {"tokens": len(tokens), "solid": len(solid_rows),
                     "alpha": len(alpha_rows),
                     "max_solid_delta": max(r["delta"] for r in solid_rows),
                     "max_alpha_delta": worst_alpha,
                     "bad_solid": len(bad_solid),
                     "baseline": inv["baseline"]}}
    json.dump(out, open(os.path.join(HERE, "final-design.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote final-design.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
