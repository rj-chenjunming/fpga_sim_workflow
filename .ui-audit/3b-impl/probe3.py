"""Probe 3: unit-level (comma-split) live/dead; expect 91 units / 88 covered / 3 live."""
import re
from pathlib import Path
WEB = Path("loop/web")
COMMENT_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)
COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
                   r"|\b(?:rgba?|hsla?)\s*\([^()]*\)")
def strip(t): return COMMENT_CSS.sub(" ", t)
def norm(s):
    s = " ".join(s.split()); return re.sub(r"\s*([>+~])\s*", r"\1", s)
def units(sel):
    parts, buf, d = [], [], 0
    for ch in sel:
        if ch in "([": d += 1
        elif ch in ")]": d -= 1
        if ch == "," and d == 0: parts.append("".join(buf)); buf = []; continue
        buf.append(ch)
    parts.append("".join(buf))
    return [norm(p) for p in parts if norm(p)]
def blocks(css):
    out, n = [], len(css)
    def find_end(j):
        d, k = 0, j
        while k < n:
            if css[k] == "{": d += 1
            elif css[k] == "}":
                d -= 1
                if d == 0: return k
            k += 1
        return n - 1
    def walk(i, end, ctx):
        while i < end:
            j = css.find("{", i)
            if j < 0 or j >= end: return
            prelude = norm(css[i:j]); k = find_end(j)
            if prelude.startswith("@"): walk(j + 1, k, ctx + (prelude,))
            else: out.append((ctx, prelude, css[j + 1:k]))
            i = k + 1
    walk(0, n, ())
    return out
later_units = set()
for name in ("tokens.css", "legacy.css", "app.css"):
    for _c, p, _b in blocks(strip((WEB / name).read_text())):
        later_units.update(units(p))
inline = blocks(strip(re.search(r"<style>(.*?)</style>", (WEB / "legacy.html").read_text(), re.DOTALL).group(1)))
total = live = 0
live_colour = []
for _c, p, b in inline:
    for u in units(p):
        total += 1
        if u in later_units: continue
        live += 1
        lits = COLOR.findall(b)
        if lits: live_colour.append((u, lits))
print(f"selector units={total} live={live} covered={total-live}  (analyst: 91 / 3 / 88)")
print(f"live units carrying colour = {len(live_colour)}")
for u, l in live_colour: print(f"  {u}: {l}")
print("total colour literals in <style> block =", len(COLOR.findall(strip(re.sub(r'<[^>]+>', '', re.search(r'<style>(.*?)</style>', (WEB/'legacy.html').read_text(), re.DOTALL).group(1))))))

with_col = [(p, b) for _c, p, b in inline if COLOR.findall(b)]
print("inline rules carrying >=1 colour =", len(with_col), "of", len(inline), "parsed rules")
print("distinct preludes carrying colour =", len({p for p, b in with_col}))
