"""E 复核：把新用例里**文件级**断言，逐个在 .ui-audit/tmp 的**副本**上做判别性实验。不改原文件。"""
from __future__ import annotations
import re, shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "loop" / "web"
TMP = Path(__file__).resolve().parent / "copy"
TMP.mkdir(exist_ok=True)
for name in ("tokens.css", "app.css", "app.js", "index.html", "legacy.html"):
    shutil.copy(WEB / name, TMP / name)


def offenders(css):
    return re.findall(r"transition\s*:\s*[^;{}]*\b(?:width|height)\b", css)


def motion_ok(tokens, css):
    checks = {}
    checks["no-Inter"] = "Inter" not in tokens
    checks["bezier"] = bool(re.search(r"cubic-bezier\(\s*0\.22\s*,\s*1\s*,\s*0\.36\s*,\s*1\s*\)", tokens + css))
    checks["--ease-out"] = "--ease-out" in tokens
    checks["no-transition-wh"] = not offenders(css)
    checks["has-:active"] = ":active" in css
    checks["has-text-wrap"] = "text-wrap" in css
    checks["no-@font-face"] = "@font-face" not in tokens + css
    checks["no-url("] = "url(" not in tokens + css
    return checks


base_tok = (WEB / "tokens.css").read_text()
base_css = (WEB / "app.css").read_text()
base_js = (WEB / "app.js").read_text()
print("[S0] 当前文件全部通过:", motion_ok(base_tok, base_css))

# 1) 回退 Inter
print("[S1] tokens 加回 Inter ⇒", motion_ok(base_tok.replace("--font-sans:-apple-system", "--font-sans:Inter,-apple-system"), base_css)["no-Inter"])
# 2) 回退 transition:width（原 .stage-bar i 的写法）
print("[S2] app.css 恢复 transition:width ⇒", motion_ok(base_tok, base_css + "\n.x{transition:width .3s}")["no-transition-wh"], offenders(".x{transition:width .3s}"))
# 3) 长写法绕过：transition-property:width（判据抓不到）
print("[S3] transition-property:width 长写法 ⇒ 判据仍通过？", "transition-property:width" not in base_css,
      "| offenders=", offenders(".x{transition-property:width}"))
# 4) 有 :active 但无实际样式（存在性断言抓不到）
print("[S4] ':active' 只在注释里出现 ⇒ has-:active =", ":active" in base_css.replace(".btn:active", ".btn"))

# 5) app.js 断言
print("[S5] app.js: 无 fill.style.width =", "fill.style.width" not in base_js,
      "| 有 --p =", "--p" in base_js,
      '| 无 label: "进行中" =', 'label: "进行中"' not in base_js,
      '| 无 working: "工作中" =', 'working: "工作中"' not in base_js)
print("[S5] 若把 label 改回「进行中」⇒",
      'label: "进行中"' not in base_js.replace('label: "执行中"', 'label: "进行中"'))

# 6) 结构断言
idx = (WEB / "index.html").read_text()
leg = (WEB / "legacy.html").read_text()
print("[S6] index: 无 .s0-hero =", ".s0-hero" not in idx,
      "| 有 nav =", "<nav" in idx,
      '| 有 link[rel=icon] =', 'rel="icon"' in idx,
      '| 有 sk-line =', "sk-line" in idx)
print("[S6] legacy: skip-link =", 'class="skip-link"' in leg, "| legacyMain =", "legacyMain" in leg)
print("[S6] sk-line 出现次数 index.html =", idx.count("sk-line"),
      "| 骨架容器数 =", len(re.findall(r'<div class="sk-line', idx)))
print("[S6] 三页 HTML =", sorted(p.name for p in WEB.glob("*.html")),
      "| 带 favicon 的页 =", sorted(p.name for p in WEB.glob("*.html") if 'rel="icon"' in p.read_text()))
