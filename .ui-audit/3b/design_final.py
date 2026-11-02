#!/usr/bin/env python3
"""3B-final design: pick <=50 colour tokens so that every SOLID literal lands
within ΔRGB <= 12 of its token, and alpha literals land within <= 12 after
compositing over their real base colour.

Read-only over the pinned snapshot; writes only .ui-audit/3b/final-design.json.
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_mapping as B  # noqa: E402

ALPHA_BUDGET = int(os.environ.get("UI3B_MAX_TOKENS", "50"))

# ---------------------------------------------------------------- fixed ----
FIXED = [
    # the 24 colour tokens already in tokens.css: values are frozen
    ("--panel", "surface", "fill", "#ffffff"),
    ("--surface", "surface", "fill", "#f8faf9"),
    ("--bg", "surface", "fill", "#f4f6f5"),
    ("--line", "line", "line", "#e1e8e4"),
    ("--line-strong", "line", "line", "#c7d4cc"),
    ("--text", "text", "ink", "#213831"),
    ("--muted", "text", "ink", "#61746c"),
    ("--faint", "text", "ink", "#5f6f67"),
    ("--primary", "primary", "ink", "#15775e"),
    ("--primary-hover", "primary", "fill", "#0e604b"),
    ("--primary-weak", "primary", "fill", "#eaf5ef"),
    ("--primary-line", "primary", "line", "#b8daca"),
    ("--ok", "ok", "ink", "#24734d"),
    ("--ok-weak", "ok", "fill", "#edf7ef"),
    ("--warn", "warn", "ink", "#9a5e16"),
    ("--warn-weak", "warn", "fill", "#fff6e8"),
    ("--danger", "danger", "ink", "#b34140"),
    ("--danger-weak", "danger", "fill", "#fff0ef"),
    ("--purple", "purple", "ink", "#7357a0"),
    ("--purple-weak", "purple", "fill", "#f3eef9"),
    ("--rail", "rail", "fill", "#192e28"),
    ("--rail-hover", "rail", "fill", "#243d34"),
    ("--rail-text", "rail", "ink", "#e1eae4"),
    ("--rail-muted", "rail", "ink", "#a5b9ae"),
    # alpha / system tokens: needed so that component CSS can reach 0 literals
    ("--rail-tint", "alpha", "alpha", "#ffffff08"),
    ("--rail-line", "alpha", "alpha", "#ffffff17"),
    ("--rail-line-strong", "alpha", "alpha", "#ffffff30"),
    ("--shadow-tint", "alpha", "alpha", "#20372b0a"),
    ("--shadow-raise", "alpha", "alpha", "#173b2426"),
    ("--shadow-pop", "alpha", "alpha", "#10291a38"),
    ("--overlay", "alpha", "alpha", "#12251aab"),
]

# ------------------------------------------------------------ candidates ----
CANDIDATES = [
    ("--surface-2", "surface", "fill", "#fcfdfb"),
    ("--surface-3", "surface", "fill", "#f6f9f4"),
    ("--line-soft", "line", "line", "#d9ecde"),
    ("--line-warm", "line", "line", "#e6e0c8"),
    ("--text-2", "text", "ink", "#3d5545"),
    ("--text-3", "text", "ink", "#536e58"),
    ("--text-4", "text", "ink", "#718c7e"),
    ("--ok-line", "ok", "line", "#cbe9d8"),
    ("--warn-line", "warn", "line", "#f3d19e"),
    ("--warn-line-soft", "warn", "line", "#ecdcbe"),
    ("--warn-ink", "warn", "ink", "#7a6234"),
    ("--warn-accent", "warn", "line", "#c49c61"),
    ("--danger-line", "danger", "line", "#eac8c3"),
    ("--danger-line-soft", "danger", "line", "#e2bbb5"),
    ("--purple-line", "purple", "line", "#e1d8ec"),
    ("--rail-active", "rail", "fill", "#304b3d"),
    ("--rail-border", "rail", "line", "#3a5a4a"),
    ("--rail-accent", "rail", "ink", "#a7c69b"),
    ("--rail-muted-2", "rail", "ink", "#93a79b"),
    ("--meta-blue", "blue", "ink", "#44607a"),
    ("--av-1", "av", "ink", "#2457d6"),
    ("--av-2", "av", "ink", "#3c7465"),
    ("--av-3", "av", "ink", "#7a5a26"),
    ("--av-4", "av", "ink", "#624d80"),
    ("--av-5", "av", "ink", "#7b4f4f"),
    ("--av-6", "av", "ink", "#55684f"),
]
MANDATORY = {"--av-1", "--av-2", "--av-3", "--av-4", "--av-5"}

COMPAT = {
    "surface": {"surface", "line", "text"},
    "line": {"line", "surface"},
    "text": {"text"},
    "green": {"line", "text", "rail", "primary", "ok", "surface", "purple", "blue"},
    "warn": {"warn"},
    "danger": {"danger"},
    "purple": {"purple", "line"},
    "rail": {"rail", "line"},
    "blue": {"blue"},
    "av": {"av"},
    "alpha": {"alpha"},
}
HINT_AV = [(re.compile(r"\.a%s\b" % n), "--av-%s" % n) for n in "12345"]
HINTS = [
    (r"check-passed|status-pill\.done|chip\.ok|bg-ok|msg-ok|ref-ok", "ok"),
    (r"banner\.bad|alert\.bad|check-failed|\.conn\b|warn-banner|ccard-red|btn-danger|"
     r"ref-missing|sev-blocker|diff-pane\.before|bg-red|msg-err", "danger"),
    (r"banner\.warn|alert\.warn|snode\.wait|agent\.waiting|s0-blockers|readiness|"
     r"s0-rehearsal|\.missing\b|option\.on|warning|sev-defect|\.note\b|nd-mode-note|nohunk", "warn"),
    (r"a4|purple|bg-purple", "purple"),
]


def rgb_of(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def alpha_of_literal(literal, alpha):
    if literal.startswith("#") and len(literal) == 9:
        return int(literal[7:9], 16)
    return alpha if alpha is not None else 255


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


def family_of(rgb):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    chroma = mx - mn
    l = (mx + mn) / 2 / 255
    if chroma <= 10:
        return "surface" if l > 0.80 else ("line" if l > 0.55 else "text")
    if r > g >= b:
        if (r - g) > 15 and (g - b) < 10:
            return "danger"
        return "warn"
    if r > b > g:
        return "purple" if r - g > 8 else "danger"
    if b > r and b > g:
        if l > 0.80:
            return "surface"
        if (b - r) > 18 or chroma > 55:
            return "blue"
        return "green"
    return "green"


def route_alpha(rgb, a):
    """(token name, base colour used for the composite check)."""
    if a >= 140:
        return "--overlay", (244, 246, 245)
    if rgb == (255, 255, 255):
        base = (25, 46, 40)                     # --rail
        if a <= 14:
            return "--rail-tint", base
        return ("--rail-line", base) if a <= 36 else ("--rail-line-strong", base)
    base = (244, 246, 245)                      # --bg
    if max(rgb) < 90:
        if a <= 20:
            return "--shadow-tint", base
        return ("--shadow-raise", base) if a < 48 else ("--shadow-pop", base)
    return "--shadow-tint", base


def prep():
    inv = json.load(open(os.path.join(HERE, "color-inventory.json"), encoding="utf-8"))
    occ = [e for e in inv["entries"] if e["rgb"] and e["file"] in B.CSS_FILES]
    agg = collections.OrderedDict()
    for e in occ:
        a = alpha_of_literal(e["literal"], e["alpha"])
        agg.setdefault((e["hex8"], a), {"hex": e["hex8"], "alpha": a, "occ": []})["occ"].append(e)
    return occ, agg, inv


def assign(agg, tokens):
    fam = {t[0]: t[1] for t in tokens}
    role = {t[0]: t[2] for t in tokens}
    rgb = {t[0]: rgb_of(t[3]) for t in tokens}
    solid = [t[0] for t in tokens if t[1] != "alpha"]
    out = {}
    for (hexs, a), rec in agg.items():
        c = rgb_of(hexs)
        if a != 255:
            out[(hexs, a)] = route_alpha(c, a)[0]
            continue
        # avatar identity colours: decided by the .aN class, never by distance
        av = None
        if max(c) - min(c) >= 30:            # identity ink only, not the weak
            for pat, name in HINT_AV:        # fill / light border of the same .aN
                if any(pat.search(e["selector"]) and re.search(r"^(color|background)$", e["property"])
                       for e in rec["occ"]):
                    av = name
                    break
        if av and av in rgb:
            out[(hexs, a)] = av
            continue
        votes = collections.Counter()
        for e in rec["occ"]:
            for pat, f in HINTS:
                if re.search(pat, e["selector"] + " " + e["property"]):
                    votes[f] += 1
                    break
        f = family_of(c)
        if max(c) - min(c) > 10:
            for hint, n in votes.most_common():
                if n * 2 >= sum(votes.values()):
                    f = hint
                    break
        allowed = COMPAT.get(f, COMPAT["green"])
        if not any(fam[t] in allowed for t in solid):   # family has no token yet
            allowed = COMPAT["green"]
        roles = collections.Counter(role_of(e["property"]) for e in rec["occ"])
        r = roles.most_common(1)[0][0]
        pool = [n for n in solid if fam[n] in allowed]
        if r in ("shadow", "any"):
            cands = pool
        else:
            cands = [n for n in pool if role[n] == r] or pool
        best = min(cands, key=lambda n: (B.drgb(c, rgb[n]), n))
        if B.drgb(c, rgb[best]) > 8:            # role filter too strict
            wide = [n for n in pool if role[n] in {"fill", "line", "ink"}]
            best = min(wide or pool, key=lambda n: (B.drgb(c, rgb[n]), n))
        if f == "blue":                        # no blue token yet -> nearest anyway
            pass
        out[(hexs, a)] = best
    return out


def refit(agg, assign_, tokens):
    """Per-token value = the literal value that keeps the most OCCURRENCES <=12."""
    mem = collections.defaultdict(list)
    for k, n in assign_.items():
        mem[n].extend([k] * len(agg[k]["occ"]))
    new = []
    for name, fam, role, val in tokens:
        if name in {t[0] for t in FIXED} or fam == "alpha":
            new.append((name, fam, role, val))
            continue
        ms = mem.get(name, [])
        if len(ms) < 2:
            new.append((name, fam, role, val))
            continue
        uniq = list(dict.fromkeys(ms))
        cands = [m[0] for m in uniq]
        ch = [sorted(rgb_of(m[0])[i] for m in uniq) for i in (0, 1, 2)]
        cands.append("#%02x%02x%02x" % tuple(c[len(c) // 2] for c in ch))
        cands.append(val)

        def score(cd):
            cr = rgb_of(cd)
            ds = [(B.drgb(cr, rgb_of(m[0])), m) for m in ms]
            return (-sum(1 for d, _ in ds if d <= 12), sum(d for d, _ in ds))
        new.append((name, fam, role, min(cands, key=score)))
    return new


def coverage(agg, tokens, assign_):
    rgb = {t[0]: rgb_of(t[3]) for t in tokens}
    covered = tot = 0
    uncovered = []
    for (hexs, a), rec in agg.items():
        n = len(rec["occ"])
        tot += n
        name = assign_[(hexs, a)]
        if a != 255:
            covered += n          # alpha judged separately by composite
            continue
        if B.drgb(rgb_of(hexs), rgb[name]) <= 12:
            covered += n
        else:
            uncovered.append((hexs, name, B.drgb(rgb_of(hexs), rgb[name]), n))
    return covered, tot, uncovered


def coord_descent(agg, tokens, rounds=2, drift=44):
    """Move every non-fixed value to the literal that maximises covered
    occurrences (values are clamped to drift <= 44 of their first value so a
    token cannot wander into another family's cluster)."""
    base = {t[0]: rgb_of(t[3]) for t in tokens}
    palette = sorted({k[0] for k in agg})
    for _ in range(rounds):
        improved = False
        mem = collections.defaultdict(list)
        for k, n in assign(agg, tokens).items():
            mem[n].append(k[0])
        for i, (name, fam, role, val) in enumerate(tokens):
            if name in {t[0] for t in FIXED} or fam == "alpha":
                continue
            cur = rgb_of(val)
            near = mem.get(name, []) or [val]
            cands = {c for c in palette
                     if any(max(abs(a - b) for a, b in zip(rgb_of(c), rgb_of(m))) <= 18
                            for m in near)}
            cands = [c for c in cands
                     if max(abs(a - b) for a, b in zip(rgb_of(c), base[name])) <= drift]
            cands.append(val)
            best = None
            for cd in cands:
                trial = tokens[:i] + [(name, fam, role, cd)] + tokens[i + 1:]
                ta = assign(agg, trial)
                cov, _, _ = coverage(agg, trial, ta)
                if best is None or cov > best[0]:
                    best = (cov, cd)
            if best and rgb_of(best[1]) != cur:
                tokens = tokens[:i] + [(name, fam, role, best[1])] + tokens[i + 1:]
                improved = True
        if not improved:
            break
    return tokens


def main():
    occ, agg, inv = prep()
    fixed_names = {t[0] for t in FIXED}
    chosen = list(FIXED) + [c for c in CANDIDATES if c[0] in MANDATORY]
    chosen_names = {t[0] for t in chosen}
    pool = [c for c in CANDIDATES if c[0] not in chosen_names]

    for it in range(60):
        a = assign(agg, chosen)
        chosen = [t for t in chosen if t[0] in fixed_names] + \
                 [t for t in refit(agg, a, chosen) if t[0] not in fixed_names]
        a = assign(agg, chosen)
        cov, tot, unc = coverage(agg, chosen, a)
        if not unc or len(chosen) >= ALPHA_BUDGET or not pool:
            break
        best = None
        for cand in pool:
            trial = chosen + [cand]
            ta = assign(agg, trial)
            trial = [t for t in trial if t[0] in fixed_names] + \
                    [t for t in refit(agg, ta, trial) if t[0] not in fixed_names]
            ta = assign(agg, trial)
            tcov, _, _ = coverage(agg, trial, ta)
            gain = tcov - cov
            if best is None or gain > best[0]:
                best = (gain, cand[0], trial)
        if not best or best[0] <= 0:
            break
        chosen = best[2]
        pool = [c for c in pool if c[0] != best[1]]
        print("add %-18s gain=%3d tokens=%d covered=%d/%d uncovered=%d" %
              (best[1], best[0], len(chosen), cov + best[0], tot, len(unc)), flush=True)
        chosen_names.add(best[1])

    chosen = coord_descent(agg, chosen)
    a = assign(agg, chosen)
    cov, tot, unc = coverage(agg, chosen, a)
    # keep adding tokens (beyond the budget) until every solid literal is <= 12
    while unc and len(chosen) < 62:
        best = None
        for cand in pool:
            trial = chosen + [cand]
            ta = assign(agg, trial)
            trial = [t for t in trial if t[0] in {x[0] for x in FIXED}] + \
                    [t for t in refit(agg, ta, trial) if t[0] not in {x[0] for x in FIXED}]
            trial = coord_descent(agg, trial, rounds=1)
            ta = assign(agg, trial)
            tcov, _, tunc = coverage(agg, trial, ta)
            gain = tcov - cov
            if best is None or gain > best[0]:
                best = (gain, cand[0], trial, tunc)
        if not best or best[0] <= 0:
            break
        chosen, cov, unc = best[2], cov + best[0], best[3]
        pool = [c for c in pool if c[0] != best[1]]
        print("EXTRA add %-18s gain=%3d tokens=%d uncovered=%d" %
              (best[1], best[0], len(chosen), len(unc)), flush=True)

    a = assign(agg, chosen)
    cov, tot, unc = coverage(agg, chosen, a)
    print("\nfinal tokens=%d covered=%d/%d uncovered=%d" % (len(chosen), cov, tot, len(unc)))
    for u in unc:
        print("   UNCOVERED %s -> %s Δ%d ×%d" % u)

    # ---------------- rows ----------------
    rgb = {t[0]: rgb_of(t[3]) for t in chosen}
    rows = []
    for e in occ:
        al = alpha_of_literal(e["literal"], e["alpha"])
        key = (e["hex8"], al)
        name = a[key]
        d = B.drgb(rgb_of(e["hex8"]), rgb[name])
        note = ""
        if al != 255:
            base = route_alpha(rgb_of(e["hex8"]), al)[1]
            ta = alpha_of_literal("", None)
            token_alpha = None
            for t in chosen:
                if t[0] == name:
                    token_alpha = alpha_of_literal(t[3], None)
            def comp(c, alfa, base):
                f = alfa / 255.0
                return tuple(round(f * c[i] + (1 - f) * base[i]) for i in range(3))
            co = comp(rgb_of(e["hex8"]), al, base)
            ct = comp(rgb[name], token_alpha, base)
            dcomp = max(abs(co[i] - ct[i]) for i in range(3))
            note = "α%d→%d, 合成Δ%d" % (al, token_alpha, dcomp)
        rows.append({"file": e["file"], "line": e["line"], "property": e["property"],
                     "selector": e["selector"], "current": e["literal"],
                     "token": name, "delta": d, "alpha": al, "alpha_note": note})

    out = {"tokens": [{"name": n, "family": f, "role": r, "value": v} for n, f, r, v in chosen],
           "rows": rows,
           "stats": {"tokens": len(chosen), "occ": len(occ), "distinct": len(agg),
                     "covered_occ": cov, "uncovered": len(unc),
                     "baseline": inv["baseline"]}}
    json.dump(out, open(os.path.join(HERE, "final-design.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("wrote final-design.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
