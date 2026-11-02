#!/usr/bin/env python3
"""3B-3 build the absorption table: colour literal -> design token.

Read-only over loop/web/**; writes only under .ui-audit/3b/:
  mapping.json  assignment + per-occurrence rows
  map.tsv       implementer's replace list

Rules baked in (documented in absorption.md / gaps.md):
  * the 24 existing tokens keep their current tokens.css value verbatim;
  * the 16 new tokens take the value that minimises max ΔRGB over the literals
    they absorb (per-channel median or best member colour);
  * canonical metric: ΔRGB = max(|Δr|,|Δg|,|Δb|) on 0-255 sRGB channels;
  * cross-semantic merging is forbidden: a warn literal never lands on an
    ok/primary/danger token and vice versa (COMPAT guardrail);
  * alpha-bearing literals are routed by role (overlay / white tint / shadow),
    because alpha, not RGB distance, decides their appearance.
"""
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
INV = os.path.join(HERE, "color-inventory.json")
CSS_FILES = ("loop/web/app.css", "loop/web/legacy.css")

EXISTING = {
    "--panel", "--surface", "--bg", "--line", "--line-strong", "--text", "--muted",
    "--faint", "--primary", "--primary-hover", "--primary-weak", "--primary-line",
    "--ok", "--ok-weak", "--warn", "--warn-weak", "--danger", "--danger-weak",
    "--purple", "--purple-weak", "--rail", "--rail-hover", "--rail-text", "--rail-muted",
}

# (token, family, role, value)   value = tokens.css current for EXISTING, §5.2 for new
TOKENS = [
    ("--panel", "surface", "fill", "#ffffff"),
    ("--surface", "surface", "fill", "#f8faf9"),
    ("--surface-2", "surface", "fill", "#fcfdfb"),
    ("--bg", "surface", "fill", "#f4f6f5"),
    ("--line", "line", "line", "#e1e8e4"),
    ("--line-strong", "line", "line", "#c7d4cc"),
    ("--line-soft", "line", "line", "#d9ecde"),
    ("--text", "text", "ink", "#213831"),
    ("--text-2", "text", "ink", "#2f4a37"),
    ("--text-3", "text", "ink", "#536e58"),
    ("--muted", "text", "ink", "#61746c"),
    ("--faint", "text", "ink", "#5f6f67"),
    ("--primary", "primary", "ink", "#15775e"),
    ("--primary-hover", "primary", "fill", "#0e604b"),
    ("--primary-weak", "primary", "fill", "#eaf5ef"),
    ("--primary-line", "primary", "line", "#b8daca"),
    ("--ok", "ok", "ink", "#24734d"),
    ("--ok-weak", "ok", "fill", "#edf7ef"),
    ("--ok-line", "ok", "line", "#cbe9d8"),
    ("--warn", "warn", "ink", "#9a5e16"),
    ("--warn-weak", "warn", "fill", "#fff6e8"),
    ("--warn-line", "warn", "line", "#f3d19e"),
    ("--warn-line-soft", "warn", "line", "#ecdcbe"),
    ("--warn-ink", "warn", "ink", "#7a6234"),
    ("--danger", "danger", "ink", "#b34140"),
    ("--danger-weak", "danger", "fill", "#fff0ef"),
    ("--danger-line", "danger", "line", "#eac8c3"),
    ("--purple", "purple", "ink", "#7357a0"),
    ("--purple-weak", "purple", "fill", "#f3eef9"),
    ("--rail", "rail", "fill", "#192e28"),
    ("--rail-hover", "rail", "fill", "#243d34"),
    ("--rail-border", "rail", "line", "#3a5a4a"),
    ("--rail-text", "rail", "ink", "#e1eae4"),
    ("--rail-muted", "rail", "ink", "#a5b9ae"),
    ("--rail-accent", "rail", "ink", "#bacdb3"),
    ("--rail-tint", "alpha", "alpha", "#ffffff08"),
    ("--rail-line", "alpha", "alpha", "#ffffff17"),
    ("--shadow-tint", "alpha", "alpha", "#20372b0a"),
    ("--shadow-pop", "alpha", "alpha", "#10291a38"),
    ("--overlay", "alpha", "alpha", "#12251ab3"),
]
TOK_FAMILY = {t[0]: t[1] for t in TOKENS}
TOK_ROLE = {t[0]: t[2] for t in TOKENS}
TOK_SUGGEST = {t[0]: t[3] for t in TOKENS}
TOK_EXIST = {t[0]: t[0] in EXISTING for t in TOKENS}

# which roles may a literal fall back to when its own role has no close token?
ROLE_FALLBACK = {"fill": {"fill", "line"}, "line": {"line", "fill"},
                 "ink": {"ink"}, "shadow": {"ink", "line"},
                 "any": {"fill", "line", "ink"}}

COMPAT = {
    "surface": {"surface", "line", "text", "rail", "primary", "ok", "purple"},
    "green": {"line", "text", "rail", "primary", "ok", "surface", "purple"},
    "ok": {"ok"},
    "warn": {"warn"},
    "danger": {"danger"},
    "purple": {"purple", "line"},
    "rail": {"rail", "text", "line"},
    "accent": {"primary", "purple", "text"},
    "alpha": {"alpha"},
}

HINTS = [
    (r"check-passed|status-pill\.done|chip\.ok|bg-ok|msg-ok|ref-ok", "ok"),
    (r"banner\.bad|alert\.bad|check-failed|\.conn\b|warn-banner|ccard-red|btn-danger|"
     r"ref-missing|sev-blocker|diff-pane\.before|bg-red|msg-err", "danger"),
    (r"banner\.warn|alert\.warn|snode\.wait|agent\.waiting|s0-blockers|readiness|"
     r"s0-rehearsal|\.missing\b|option\.on|warning|sev-defect|\.note\b|nd-mode-note|nohunk", "warn"),
    (r"a4|purple|bg-purple", "purple"),
]


def rgb_of(hexs):
    h = hexs.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def alpha_of(literal, alpha):
    if literal.startswith("#") and len(literal) == 9:
        return int(literal[7:9], 16)
    return alpha if alpha is not None else 255


def drgb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def role_of(prop):
    p = prop.lower()
    if "shadow" in p:
        return "shadow"
    if "border" in p or p.startswith("outline") or p == "scrollbar-color":
        return "line"
    if "background" in p:
        return "fill"
    if p == "color":
        return "ink"
    return "any"


def colour_family(rgb):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    chroma = mx - mn
    l = (mx + mn) / 2 / 255
    if chroma <= 10:
        return "surface" if l > 0.80 else ("line" if l > 0.55 else "text")
    if r > g >= b:                                  # warm family
        if (r - g) > 15 and (g - b) < 10:           # rose / pink -> danger
            return "danger"
        return "warn"
    if r > b > g:
        return "purple" if r - g > 8 else "danger"
    if b > r and b > g:                             # blue
        if l > 0.80:
            return "surface"                       # cool near-whites
        if chroma > 55:
            return "accent"                        # saturated blue: no token
        return "green"
    return "green"


def _assign(agg, centers, fam_of, role_of_tok, solid):
    tok_rgb = {n: rgb_of(v) for n, v in centers.items()}
    assign = {}
    for (hexs, a_l), a in agg.items():
        c = rgb_of(hexs)
        if a_l != 255:                              # alpha: role decides
            if a_l >= 140:
                assign[(hexs, a_l)] = "--overlay"
            elif c == (255, 255, 255):
                assign[(hexs, a_l)] = "--rail-tint" if a_l <= 14 else "--rail-line"
            else:
                assign[(hexs, a_l)] = "--shadow-tint" if a_l <= 20 else "--shadow-pop"
            continue
        votes = collections.Counter()
        for e in a["occ"]:
            for pat, fam in HINTS:
                if re.search(pat, e["selector"] + " " + e["property"]):
                    votes[fam] += 1
                    break
        fam = colour_family(c)
        if max(c) - min(c) > 10:                    # achromatic inks never inherit
            for hint, n in votes.most_common():     # the selector's state family
                if n * 2 >= sum(votes.values()):
                    fam = hint
                    break
        allowed = COMPAT.get(fam, COMPAT["green"])
        roles = collections.Counter(role_of(e["property"]) for e in a["occ"])
        role = roles.most_common(1)[0][0]
        cands = [n for n in solid if fam_of[n] in allowed and
                 (role in ("shadow", "any") or role_of_tok[n] == role)]
        if not cands:
            cands = [n for n in solid if fam_of[n] in allowed]
        best = min(cands, key=lambda n: (drgb(c, tok_rgb[n]), n))
        if drgb(c, tok_rgb[best]) > 8:               # same-role pool too far:
            wide = [n for n in solid if fam_of[n] in allowed]   # nearest in family wins
            best = min(wide, key=lambda n: (drgb(c, tok_rgb[n]), n))
        if fam == "accent":                          # no blue token exists
            best = min(solid, key=lambda n: (drgb(c, tok_rgb[n]), n))
        assign[(hexs, a_l)] = best
    return assign


def _refit(assign, centers, keys_by_token, frozen):
    """One k-medoids step for the NON-existing tokens: pick the value that keeps
    the most members inside ΔRGB<=12 (tie-break: smaller total distance)."""
    new_centers = dict(centers)
    for name, mem in keys_by_token.items():
        if name in frozen or len(mem) < 2:
            continue
        cands = [m[0] for m in mem]
        chans = [sorted(rgb_of(m[0])[i] for m in mem) for i in (0, 1, 2)]
        cands.append("#%02x%02x%02x" % tuple(c[len(c) // 2] for c in chans))
        cands.append(centers[name])

        def score(cd):
            cr = rgb_of(cd)
            ds = [drgb(cr, rgb_of(m[0])) for m in mem]
            return (-sum(1 for d in ds if d <= 12), sum(ds))
        new_centers[name] = min(cands, key=score)
    return new_centers


def run(tokens=TOKENS, verbose=True, refine_rounds=1):
    inv = json.load(open(INV, encoding="utf-8"))
    occ = [e for e in inv["entries"] if e["rgb"] and e["file"] in CSS_FILES]
    agg = collections.OrderedDict()
    for e in occ:
        a_l = alpha_of(e["literal"], e["alpha"])
        agg.setdefault((e["hex8"], a_l), {"hex": e["hex8"], "alpha": a_l, "occ": []})["occ"].append(e)

    fam_of = {t[0]: t[1] for t in tokens}
    role_of_tok = {t[0]: t[2] for t in tokens}
    solid = [t[0] for t in tokens if t[1] != "alpha"]
    frozen = {t[0] for t in tokens if t[0] in EXISTING} | {t[0] for t in tokens if t[1] == "alpha"}
    centers = {t[0]: t[3] for t in tokens}

    assign = _assign(agg, centers, fam_of, role_of_tok, solid)
    for _ in range(max(0, refine_rounds - 1)):
        keys_by_token = collections.defaultdict(list)
        for key, name in assign.items():
            keys_by_token[name].append(key)
        nxt = _refit(assign, centers, keys_by_token, frozen)
        if nxt == centers:
            break
        centers = nxt
        assign = _assign(agg, centers, fam_of, role_of_tok, solid)

    members = collections.defaultdict(list)
    for key, name in assign.items():
        members[name].append(key)
    fitted, report = {}, []
    for name, fam, role, val in tokens:
        mem = members.get(name, [])
        fitted[name] = centers[name]
        mx = max((drgb(rgb_of(centers[name]), rgb_of(m[0])) for m in mem), default=0)
        inside = sum(1 for m in mem if drgb(rgb_of(centers[name]), rgb_of(m[0])) <= 12)
        report.append((name, fam, role, val, centers[name], mx, len(mem),
                       sum(len(agg[m]["occ"]) for m in mem), inside))

    rows, deltas = [], []
    for e in occ:
        a_l = alpha_of(e["literal"], e["alpha"])
        name = assign[(e["hex8"], a_l)]
        d = drgb(rgb_of(e["hex8"]), rgb_of(fitted[name]))
        rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                     "selector": e["selector"], "current": e["literal"], "token": name,
                     "delta": d, "alpha": a_l,
                     "token_alpha": alpha_of(fitted[name], None)})
        deltas.append(d)
    over = [r for r in rows if r["delta"] > 12]

    payload = {"tokens": [{"name": n, "family": f, "role": r, "suggest": s,
                           "fitted": fitted[n], "existing": n in EXISTING,
                           "max_delta": mx, "distinct": nd, "occ": no,
                           "inside12": _in,
                           "members": sorted("%s/%d" % m for m in members.get(n, []))}
                          for n, f, r, s, _fit, mx, nd, no, _in in report],
               "rows": rows,
               "stats": {"occ": len(occ), "distinct": len(agg),
                         "over12_rows": len(over),
                         "over12_distinct": len({(r["current"], r["alpha"]) for r in over}),
                         "max_delta": max(deltas),
                         "tokens": len(tokens),
                         "tokens_absorbing_nothing": [n for n, f, r, s, _f, mx, nd, no, _i in report if nd == 0]}}
    json.dump(payload, open(os.path.join(HERE, "mapping.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "map.tsv"), "w", encoding="utf-8") as fh:
        fh.write("file\tline\tproperty\tcurrent\ttoken\tdelta\tselector\n")
        for r in rows:
            fh.write("%s\t%d\t%s\t%s\t%s\t%d\t%s\n" % (
                r["file"], r["line"], r["property"], r["current"], r["token"],
                r["delta"], r["selector"].replace("\t", " ")))

    # value-keyed map (survives 3C line shifts: it is literal -> token, no lines)
    with open(os.path.join(HERE, "map-values.tsv"), "w", encoding="utf-8") as fh:
        fh.write("literal\talpha\ttoken\tdelta\toccurrences\n")
        agg_rows = collections.OrderedDict()
        for r in rows:
            k = (r["current"], r["alpha"])
            e = agg_rows.setdefault(k, {"token": r["token"], "delta": r["delta"], "n": 0})
            e["n"] += 1
        for (lit, a), e in agg_rows.items():
            fh.write("%s\t%s\t%s\t%d\t%d\n" % (lit, a, e["token"], e["delta"], e["n"]))

    if verbose:
        print("occurrences:", len(occ), "distinct(rgb+alpha):", len(agg),
              "tokens:", len(tokens))
        print("%-18s %-7s %-5s %-9s %-9s %4s %3s %4s" %
              ("token", "family", "role", "suggest", "fitted", "mxΔ", "in", "occ"))
        for name, fam, role, sug, fit, mx, nd, no, inside in report:
            print("%-18s %-7s %-5s %-9s %-9s %4d %3d/%3d %4d%s" %
                  (name, fam, role, sug, fit, mx, inside, nd, no,
                   "  <-- >12" if mx > 12 else ""))
        print("over12 rows:", len(over), "distinct:", payload["stats"]["over12_distinct"],
              "max:", max(deltas))
        print("absorbing nothing:", payload["stats"]["tokens_absorbing_nothing"])
    return payload, over


if __name__ == "__main__":
    payload, over = run()
    print("\n=== rows with Δ>12 ===")
    g = collections.OrderedDict()
    for r in over:
        g.setdefault((r["current"], r["token"], r["delta"]), []).append(r)
    for (cur, tok, d), rs in g.items():
        print("%-24s -> %-18s Δ=%-3d n=%-2d  %s" % (cur, tok, d, len(rs), rs[0]["selector"][:56]))
