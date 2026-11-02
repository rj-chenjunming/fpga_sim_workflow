"""Report numbers: literal counts before/after, token usage, dead declarations."""
import re
from collections import Counter
from pathlib import Path

WEB = Path("loop/web")
SNAP = Path(".ui-audit/3b-impl/snap-before")
COLR = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
                  r"|\b(?:rgba?|hsla?)\s*\([^()]*\)")
VAR = re.compile(r"var\(\s*(--[\w-]+)")
CSSC = re.compile(r"/\*.*?\*/", re.DOTALL)

def mask(css):
    chunks = []
    n = len(css)
    def mb(o, e):
        d, i = 0, o
        while i < e:
            if css[i] == "{": d += 1
            elif css[i] == "}":
                d -= 1
                if d == 0: return i
            i += 1
        raise SystemExit("unbalanced")
    def walk(s, e):
        seg, i = s, s
        while i < e:
            if css[i] == "{":
                chunks.append((seg, i)); c = mb(i, e); walk(i+1, c); i = c+1; seg = i; continue
            if css[i] == "}": i += 1; seg = i; continue
            i += 1
    walk(0, n)
    ch = list(css)
    for s, e in chunks:
        for i in range(s, e):
            if ch[i] != "\n": ch[i] = " "
    return "".join(ch)

def decls(path):
    return mask(CSSC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), path.read_text()))

print("== 组件层颜色字面量（声明位置）==")
for name in ("app.css", "legacy.css"):
    b = len(COLR.findall(decls(SNAP / name)))
    a = len(COLR.findall(decls(WEB / name)))
    print(f"  {name:11s} before={b:4d}  after={a}  var()用量 before={len(VAR.findall((SNAP/name).read_text())):4d} after={len(VAR.findall((WEB/name).read_text()))}")
html_b = (SNAP / "legacy.html").read_text(); html_a = (WEB / "legacy.html").read_text()
print(f"  legacy.html style块字面量 before={len(COLR.findall(html_b))} after={len(COLR.findall(html_a))}"
      f"（其中活规则 3 条已换 var；死声明应余 155）")
print(f"  legacy.html var()用量 before={len(VAR.findall(html_b))} after={len(VAR.findall(html_a))}")

tok = decls(WEB / "tokens.css")
decl = dict(re.findall(r"(--[\w-]+)\s*:\s*([^;{}]*)", tok))
colour = {k: v.strip() for k, v in decl.items() if COLR.fullmatch(v.strip())}
print(f"\n== 令牌 ==\n  变量总数={len(decl)}  颜色令牌={len(colour)}  非颜色={sorted(set(decl)-set(colour))}")

uses = Counter()
for name in ("app.css", "legacy.css", "legacy.html"):
    uses.update(VAR.findall((WEB / name).read_text()))
print(f"  var() 引用总数={sum(uses.values())}  被引用的不同变量={len(uses)}")
unused = sorted(set(decl) - set(uses))
print(f"  定义了但没被组件层引用的变量={unused}")
print(f"  引用了但未定义的变量={sorted(set(uses) - set(decl))}")
print("\n  每令牌引用次数（组件层）:")
for name in sorted(decl):
    print(f"    {name:20s} {uses.get(name, 0):3d}  {decl[name].strip()[:40]}")
