"""Scratch probe: validate the scan semantics before freezing the guard.

Counts, with declaration-only extraction (selector preludes excluded so `#toast`
ID selectors are NOT mistaken for hex colours):
  - colour literals in app.css / legacy.css
  - token count in tokens-final.css (exact-colour values only)
  - legacy.html <style>: rule count, selector-unit count, live units (not present
    in tokens.css/legacy.css/app.css), colour literals per unit
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WEB = Path("loop/web")
AUDIT = Path(".ui-audit/3b")

COMMENT_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)
COMMENT_HTML = re.compile(r"<!--.*?-->", re.DOTALL)

COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
    r"|\b(?:rgba?|hsla?)\s*\([^()]*\)"
)


def strip_comments(text: str) -> str:
    return COMMENT_HTML.sub(" ", COMMENT_CSS.sub(" ", text))


def declarations(css: str) -> str:
    """Return only declaration text: everything between braces, minus nested preludes."""
    out, buf, depth, i, n = [], [], 0, 0, len(css)
    while i < n:
        ch = css[i]
        if ch == "{":
            depth += 1
            buf = []
            i += 1
            continue
        if ch == "}":
            out.append("".join(buf))
            buf = []
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth >= 1:
            buf.append(ch)
        i += 1
    out.append("".join(buf))
    return "\n".join(out)


def rules(css: str):
    """[(selector_list, declaration_text)] with brace matching."""
    found, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        prelude = css[i:j].strip()
        depth, k = 0, j
        while k < n:
            if css[k] == "{":
                depth += 1
            elif css[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        found.append((prelude, css[j + 1:k]))
        i = k + 1
    return found


def selector_units(sel: str) -> list[str]:
    parts, buf, depth = [], [], 0
    for ch in sel:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return [norm(p) for p in parts if norm(p)]


def norm(text: str) -> str:
    return " ".join(text.split())


def main() -> int:
    for name in ("app.css", "legacy.css", "tokens.css"):
        text = strip_comments((WEB / name).read_text())
        dec = declarations(text)
        hits = COLOR.findall(dec)
        print(f"{name:12s} declarations-colour-literals={len(hits)} distinct={len(set(hits))}")

    tok = strip_comments((AUDIT / "tokens-final.css").read_text())
    pairs = re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", tok)
    decls = dict(pairs)
    print(f"tokens-final.css declarations={len(pairs)} variables={len(decls)}")
    colour = {k: v.strip() for k, v in decls.items() if COLOR.fullmatch(v.strip())}
    print(f"  exact-colour tokens={len(colour)}; non-colour={sorted(set(decls) - set(colour))}")

    # legacy.html inline <style>
    html = (WEB / "legacy.html").read_text()
    m = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
    block = m.group(1)
    style_attrs = re.findall(r'style="([^"]*)"', html)
    print(f"legacy.html style attrs={len(style_attrs)} colour-in-attrs={sum(len(COLOR.findall(a)) for a in style_attrs)}")

    later = " ".join(strip_comments((WEB / n).read_text()) for n in ("tokens.css", "legacy.css", "app.css"))
    later_units: set[str] = set()
    for prelude, _body in rules(later):
        later_units.update(selector_units(prelude))

    units_total, live = 0, []
    for prelude, body in rules(strip_comments(block)):
        for unit in selector_units(prelude):
            units_total += 1
            if unit not in later_units:
                live.append((unit, norm(body)))
    total_lit = len(COLOR.findall(declarations(strip_comments(block))))
    print(f"inline <style>: selector units={units_total} live units={len(live)} colours-in-block={total_lit}")
    for unit, body in live:
        print(f"  LIVE {unit}: {body[:90]} colours={COLOR.findall(body)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
