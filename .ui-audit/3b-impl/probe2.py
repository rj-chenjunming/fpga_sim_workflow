"""Probe 2: pin the analyst's live/dead criterion for legacy.html inline <style>."""
import re
from pathlib import Path

WEB = Path("loop/web")
COMMENT_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)
COLOR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
                   r"|\b(?:rgba?|hsla?)\s*\([^()]*\)")

def strip(t): return COMMENT_CSS.sub(" ", t)
def norm(s):
    s = " ".join(s.split())
    s = re.sub(r"\s*([>+~])\s*", r"\1", s)
    return s

def blocks(css):
    """[(ctx, prelude, body)] recursing into @media/@supports."""
    out, i, n = [], 0, len(css)
    def find_end(j):
        d, k = 0, j
        while k < n:
            if css[k] == "{": d += 1
            elif css[k] == "}":
                d -= 1
                if d == 0: return k
            k += 1
        return n - 1
    stack = [("", 0, n, ())]
    # simple recursive walker
    def walk(i, end, ctx):
        while i < end:
            j = css.find("{", i)
            if j < 0 or j >= end: return
            prelude = norm(css[i:j])
            k = find_end(j)
            if prelude.startswith("@"):
                walk(j + 1, k, ctx + (prelude,))
            else:
                out.append((ctx, prelude, css[j + 1:k]))
            i = k + 1
    walk(0, n, ())
    return out

later = " ".join(strip((WEB / n).read_text()) for n in ("tokens.css", "legacy.css", "app.css"))
later_preludes = {p for _c, p, _b in blocks(later)}
html = (WEB / "legacy.html").read_text()
block = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
inline = blocks(strip(block))
print("inline rules =", len(inline), " (analyst: 91 selectors)")
live = [(c, p, b) for c, p, b in inline if (c + (p,)) not in later_preludes and p not in later_preludes]
print("prelude-level live =", len(live), "| with colours:", sum(1 for *_x, b in live if COLOR.findall(b)))
for c, p, b in live:
    lits = COLOR.findall(b)
    if lits: print(f"  LIVE-WITH-COLOUR {p}: {lits}")
print("covered rules =", len(inline) - len(live))
