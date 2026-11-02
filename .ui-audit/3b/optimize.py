#!/usr/bin/env python3
"""3B-4 coordinate-ascent over the 16 NEW token values.

Objective: maximise the number of colour LITERAL OCCURRENCES whose ΔRGB to their
token is <= 12 (the accepted merge tolerance), subject to:
  * the 24 existing tokens are frozen (their tokens.css values do not move),
  * each literal only ever maps to a token of a compatible semantic family
    (success / warn / danger / purple never share a token),
  * a token keeps the role/name it has in §5.2.

Read-only; prints the tuned values, writes nothing.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_mapping as B  # noqa: E402


def prep():
    inv = json.load(open(os.path.join(HERE, "color-inventory.json"), encoding="utf-8"))
    occ = [e for e in inv["entries"] if e["rgb"] and e["file"] in B.CSS_FILES]
    agg = collections.OrderedDict()
    for e in occ:
        a_l = B.alpha_of(e["literal"], e["alpha"])
        agg.setdefault((e["hex8"], a_l), {"hex": e["hex8"], "alpha": a_l, "occ": []})["occ"].append(e)
    return occ, agg


def score(centers, agg, fam_of, role_of_tok, solid):
    assign = B._assign(agg, centers, fam_of, role_of_tok, solid)
    covered = tot = 0
    viol = 0
    for key, name in assign.items():
        d = B.drgb(B.rgb_of(key[0]), B.rgb_of(centers[name]))
        n = len(agg[key]["occ"])
        tot += n
        if d <= 12:
            covered += n
        else:
            viol += 1
    return covered, -viol, tot


def main():
    occ, agg = prep()
    tokens = [t for t in B.TOKENS]
    fam_of = {t[0]: t[1] for t in tokens}
    role_of_tok = {t[0]: t[2] for t in tokens}
    solid = [t[0] for t in tokens if t[1] != "alpha"]
    centers = {t[0]: t[3] for t in tokens}
    free = [t[0] for t in tokens if t[0] not in B.EXISTING and t[1] != "alpha"]
    palette = sorted({k[0] for k in agg})
    print("free tokens:", free)

    base = score(centers, agg, fam_of, role_of_tok, solid)
    print("baseline covered %d/%d occurrences (violations=%d)" % (base[0], base[2], -base[1]))
    for rnd in range(6):
        improved = False
        for name in free:
            fam = fam_of[name]
            allowed = B.COMPAT.get(fam, B.COMPAT["green"])
            cands = [c for c in palette if fam_of[name] in B.COMPAT.get(B.colour_family(B.rgb_of(c)), {"green"})]
            cands += [centers[name]]
            best = (score(centers, agg, fam_of, role_of_tok, solid), centers[name])
            for cd in cands:
                trial = dict(centers)
                trial[name] = cd
                sc = score(trial, agg, fam_of, role_of_tok, solid)
                if sc > best[0]:
                    best = (sc, cd)
            if best[1] != centers[name]:
                centers[name] = best[1]
                improved = True
        sc = score(centers, agg, fam_of, role_of_tok, solid)
        print("round %d: covered %d/%d violations=%d" % (rnd, sc[0], sc[2], -sc[1]))
        if not improved:
            break

    print("\n# tuned values (only NEW tokens changed)")
    for t in tokens:
        if t[0] in free and t[3] != centers[t[0]]:
            print("%-18s %s -> %s" % (t[0], t[3], centers[t[0]]))
    print("\n# full centre table")
    for t in tokens:
        print("%-18s %s" % (t[0], centers[t[0]]))


if __name__ == "__main__":
    main()
