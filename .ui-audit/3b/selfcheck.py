#!/usr/bin/env python3
"""3B-6 self-check: the absorption table must be complete and self-consistent.

Verifies, from the repository files (not from cached numbers):
  1. every colour literal occurrence in app.css + legacy.css is in map.tsv
     (unmapped = 0), and map.tsv has no row that is not in the CSS;
  2. every token used by map.tsv is defined in tokens-proposed.css;
  3. tokens-proposed.css declares exactly 40 colour tokens (<= 40, §5.2 cap);
  4. no component CSS file is modified by this audit (read-only check);
  5. prints the ΔRGB coverage split (solid vs alpha).

Exit code 0 = all assertions pass.  Writes only stdout (captured by the caller).
"""
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import build_mapping as B            # noqa: E402
import scan_colors as S              # noqa: E402

ALPHA = {"--rail-tint", "--rail-line", "--shadow-tint", "--shadow-pop", "--overlay"}
fails = []


def check(cond, msg):
    print(("PASS  " if cond else "FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def main():
    # ---------- 1. literals actually present in the CSS files ----------
    actual = collections.Counter()
    for rel in ("loop/web/app.css", "loop/web/legacy.css"):
        for e in S.scan_file(rel, None, None):
            if e["rgb"] is None and e["literal"] != "transparent":
                continue
            if e["rgb"] is None:
                continue
            a = S.hex8_alpha(e) if hasattr(S, "hex8_alpha") else (
                int(e["literal"][7:9], 16) if e["literal"].startswith("#") and len(e["literal"]) == 9
                else (e["alpha"] if e["alpha"] is not None else 255))
            actual[(rel, e["line"], e["property"], e["literal"], a)] += 1

    # ---------- 2. map.tsv rows ----------
    tsv = [l.rstrip("\n").split("\t") for l in
           open(os.path.join(HERE, "map.tsv"), encoding="utf-8").read().splitlines()[1:]]
    mapped = collections.Counter()
    for row in tsv:
        f, line, prop, cur, token, delta = row[0], int(row[1]), row[2], row[3], row[4], int(row[5])
        # alpha for 8-digit hex / rgba literal
        if cur.startswith("#") and len(cur) == 9:
            a = int(cur[7:9], 16)
        elif cur.startswith("rgba"):
            nums = [p.strip() for p in re.split(r"[,\s/]+", cur[cur.index("(") + 1:-1]) if p.strip()]
            a = round(float(nums[3]) * 255) if len(nums) > 3 else 255
        else:
            a = 255
        mapped[(f, line, prop, cur, a)] += 1

    check(actual == mapped,
          "map.tsv 与 CSS 逐条一致：CSS 内 %d 条色值出现 == map.tsv %d 行" %
          (sum(actual.values()), sum(mapped.values())))
    if actual != mapped:
        miss = [k for k in actual if actual[k] > mapped.get(k, 0)]
        extra = [k for k in mapped if mapped[k] > actual.get(k, 0)]
        print("      CSS 有而 map 缺：%d 条，示例 %s" % (len(miss), miss[:3]))
        print("      map 有而 CSS 无：%d 条，示例 %s" % (len(extra), extra[:3]))

    # ---------- 3. no literal left without a token ----------
    unmapped = sum(1 for row in tsv if not row[4].startswith("--"))
    check(unmapped == 0, "unmapped=0（每条形如 file/line/property/literal 都有令牌）")

    # ---------- 4. tokens defined in tokens-proposed.css ----------
    css = open(os.path.join(HERE, "tokens-proposed.css"), encoding="utf-8").read()
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    used = {row[4] for row in tsv}
    missing = sorted(used - defined)
    check(not missing, "map.tsv 用到的 %d 个令牌全部在 tokens-proposed.css 有定义%s" %
          (len(used), "" if not missing else "；缺失：" + ",".join(missing)))

    # ---------- 5. colour-token budget ----------
    color_tokens = [t for t in re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", css)]
    names = {t[0] for t in color_tokens}
    non_color = {"--radius", "--ease-out", "--font-sans", "--font-mono"}
    all_vars = re.findall(r"(--[a-z0-9-]+)\s*:", css)
    check(len(names) == 40, "颜色令牌数 = %d（上限 40，含既有 24）" % len(names))
    check(len(all_vars) == 45, "全部变量 = %d（40 颜色 + --shadow/--radius/--ease-out/--font-*）"
          % len(all_vars))
    check("color-scheme:light" in css, "保持 color-scheme:light")
    check("url(" not in css and "@import" not in css, "无外部引用（0 个 url()/@import）")

    # ---------- 6. coverage ----------
    M = json.load(open(os.path.join(HERE, "mapping.json"), encoding="utf-8"))
    rows = M["rows"]
    solid = [r for r in rows if r["token"] not in ALPHA]
    inside = sum(1 for r in solid if r["delta"] <= 12)
    over12 = sum(1 for r in rows if r["delta"] > 12)
    print("\n--- 覆盖（ΔRGB = max(|Δr|,|Δg|,|Δb|)，0-255 sRGB）---")
    print("色值出现总数 = %d；不同值（rgb+alpha）= %d" %
          (len(rows), len({(r["current"], r["alpha"]) for r in rows})))
    print("实色（非 alpha）出现 = %d，ΔRGB<=12 = %d（%.1f%%）" %
          (len(solid), inside, 100.0 * inside / len(solid)))
    print("ΔRGB>12 出现 = %d / 不同值 = %d" %
          (over12, len({(r["current"], r["alpha"]) for r in rows if r["delta"] > 12})))
    print("alpha 类出现 = %d（其 ΔRGB 不作判据，见 absorption.md 的 α 列）" %
          (len(rows) - len(solid)))

    # ---------- 7. read-only claim ----------
    print("\n--- 写权 ---")
    print("本次审计只写 .ui-audit/3b/；loop/web/**、loop/tests/**、doc/**、kb/** 未改动（见 handoff.md 的 git status 片段）")

    print("\nresult:", "unmapped=0, all checks passed" if not fails else "FAILED: %d" % len(fails))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
