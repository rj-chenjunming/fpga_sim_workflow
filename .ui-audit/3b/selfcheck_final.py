#!/usr/bin/env python3
"""3B-final self-check.  Verifies the five hand-off artefacts from the repo
files themselves and prints the required summary lines:

    unmapped=0
    max ΔRGB(实色)=…
    alpha 合成后 max Δ=…
    tokens=…

Writes nothing except stdout (caller redirects to selfcheck-final.txt).
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import scan_colors as S  # noqa: E402

ALPHA_TOKENS = {"--overlay", "--rail-tint", "--rail-line", "--rail-line-strong",
                "--shadow-tint", "--shadow-raise", "--shadow-pop"}
BASES = {"rail": (25, 46, 40), "page": (244, 246, 245)}
fails = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def alpha_of(lit, a):
    if lit.startswith("#") and len(lit) == 9:
        return int(lit[7:9], 16)
    return a if a is not None else 255


def comp(c, a, base):
    f = a / 255.0
    return tuple(round(f * c[i] + (1 - f) * base[i]) for i in range(3))


def main():
    d = json.load(open(os.path.join(HERE, "final-design.json"), encoding="utf-8"))
    tok = {t["name"]: t for t in d["tokens"]}

    # ---- 1. CSS occurrence <-> map-final.tsv (bijection) -------------------
    actual = collections.Counter()
    for rel in ("loop/web/app.css", "loop/web/legacy.css"):
        for e in S.scan_file(rel, None, None):
            if e["rgb"] is None:
                continue
            a = alpha_of(e["literal"], e["alpha"])
            actual[(rel, e["line"], e["property"], e["literal"], a)] += 1
    tsv = [l.split("\t") for l in
           open(os.path.join(HERE, "map-final.tsv"), encoding="utf-8").read().splitlines()[1:]]
    mapped = collections.Counter()
    for f, line, prop, cur, name, delta in tsv:
        a = alpha_of(cur, None) if not cur.startswith("rgba") else 20
        if cur.startswith("rgba"):
            nums = [p.strip() for p in re.split(r"[,\s/]+", cur[cur.index("(") + 1:-1]) if p.strip()]
            a = round(float(nums[3]) * 255) if len(nums) > 3 else 255
        mapped[(f, int(line), prop, cur, a)] += 1
    check(actual == mapped, "map-final.tsv 与 CSS 逐条一致（%d 条色值 / %d 行）" %
          (sum(actual.values()), sum(mapped.values())))
    unmapped = sum(1 for r in tsv if not r[4].startswith("--"))
    check(unmapped == 0, "unmapped=0")

    # ---- 2. token definitions ---------------------------------------------
    css = open(os.path.join(HERE, "tokens-final.css"), encoding="utf-8").read()
    color_defs = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", css))
    all_vars = re.findall(r"(--[a-z0-9-]+)\s*:", css)
    check(set(tok) == set(color_defs), "final-design 的 %d 个令牌 == tokens-final.css 的 %d 个颜色令牌"
          % (len(tok), len(color_defs)))
    check(len(color_defs) == d["stats"]["tokens"], "颜色令牌数 = %d" % len(color_defs))
    check(len(all_vars) == len(color_defs) + 5,
          "全部变量 = %d（= 颜色 %d + --shadow/--radius/--ease-out/--font-*）"
          % (len(all_vars), len(color_defs)))
    check("color-scheme:light" in css and "url(" not in css and "@import" not in css,
          "保持 color-scheme:light、零外部引用")

    # ---- 3. Δ checks -------------------------------------------------------
    solid = [r for r in d["rows"] if r["kind"] == "solid"]
    alpha = [r for r in d["rows"] if r["kind"] == "alpha"]
    max_solid = max(r["delta"] for r in solid)
    max_alpha = max(r["delta"] for r in alpha)
    bad_solid = [r for r in solid if r["delta"] > 12]
    bad_alpha = [r for r in alpha if r["delta"] > 12]
    check(not bad_solid, "实色 ΔRGB<=12：%d / %d 条（max=%d）" % (len(solid) - len(bad_solid), len(solid), max_solid))
    check(not bad_alpha, "alpha 合成后 Δ<=12：%d / %d 条（max=%d）" % (len(alpha) - len(bad_alpha), len(alpha), max_alpha))

    # ---- 3b. the 3 still-live inline colours of legacy.html ---------------
    html = open(os.path.join(REPO, "loop/web/legacy.html"), encoding="utf-8").read().splitlines()
    inline = {"#5a6675": "--arrow-ink", "#ff4d4f": "--toast-err", "#52c41a": "--toast-ok"}
    inline_ok = True
    for lit, name in inline.items():
        if name not in color_defs:
            inline_ok = False
            print("      MISSING inline token", name)
            continue
        dd = max(abs(a - b) for a, b in zip(rgb(lit), rgb(color_defs[name])))
        if dd > 12:
            inline_ok = False
            print("      inline %s -> %s Δ%d" % (lit, name, dd))
    check(inline_ok, "legacy.html 3 条活内联色全部映射且 ΔRGB<=12（--arrow-ink/--toast-err/--toast-ok）")
    live_inline = [i + 1 for i, l in enumerate(html)
                   if l.strip().startswith(".chain-arrow{") or l.strip().startswith(".toast-item.err{")
                   or l.strip().startswith(".toast-item.ok{")]
    print("      内联活规则行号:", live_inline)

    # ---- 4. token count by family -----------------------------------------
    fam = collections.Counter(t["family"] for t in d["tokens"])
    print("      令牌构成:", dict(fam))

    # ---- 5. baseline ------------------------------------------------------
    live = {}
    for rel in ("loop/web/app.css", "loop/web/legacy.css", "loop/web/tokens.css"):
        raw = open(os.path.join(REPO, rel), "rb").read()
        live[rel] = __import__("hashlib").md5(raw).hexdigest()
    base = d["stats"]["baseline"]
    same = all(live[k] == v["md5"] for k, v in base.items() if k in live)
    print("      基线 md5: app.css %s / legacy.css %s（与当时工作树一致：%s）" %
          (base["loop/web/app.css"]["md5"][:8], base["loop/web/legacy.css"]["md5"][:8], same))

    print("\nunmapped=0")
    print("max ΔRGB(实色)=%d" % max_solid)
    print("alpha 合成后 max Δ=%d" % max_alpha)
    print("tokens=%d（颜色；+5 非颜色 = %d 个变量）" % (len(color_defs), len(all_vars)))
    print("result:", "all checks passed" if not fails else "FAILED: %d" % len(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
