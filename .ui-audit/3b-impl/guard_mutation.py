"""守卫变异性自检：证明 test_ui_tokens.py 的扫描器真的会抓到回退，且不会把 #id 选择器当色值。"""
import importlib.util, sys, tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("gut", Path("tests/test_ui_tokens.py"))
gut = importlib.util.module_from_spec(spec)
sys.modules["gut"] = gut
spec.loader.exec_module(gut)

def scan(css: str):
    with tempfile.NamedTemporaryFile("w", suffix=".css", delete=False, dir="/tmp") as fh:
        fh.write(css)
        p = Path(fh.name)
    try:
        return gut._literals_with_lines(gut._declaration_text(p))
    finally:
        p.unlink()

cases = [
    ("正常：全 var", ".a{background:var(--bg);color:var(--text)}", 0),
    ("回退：回填 hex", ".a{background:var(--bg);color:#fff}", 1),
    ("回退：回填 rgba", ".a{box-shadow:0 1px 2px rgba(16,24,40,.08)}", 1),
    ("回退：回填 hsl", ".a{color:hsl(200 10% 20%)}", 1),
    ("误报检查：ID 选择器不是色值", "#banners{display:flex}#awSelection{min-width:0}", 0),
    ("误报检查：注释里的旧值", "/* 旧值 #f2f4f7 已删 */ .a{color:var(--text)}", 0),
    ("误报检查：transparent/关键字保留", ".a{background:transparent;color:inherit}", 0),
    ("多色一行逐个抓", ".a{box-shadow:0 2px 4px #20372b03,0 8px 24px #20372b03}", 2),
]
bad = 0
for name, css, want in cases:
    got = scan(css)
    ok = len(got) == want
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name}: 抓到 {len(got)} 条（期望 {want}）{got if got else ''}")

# 归一化与活规则集合
print("PASS" if gut._norm_selector(".panel > h2") == gut._norm_selector(".panel>h2") else "FAIL",
      "选择器归一：`.panel > h2` == `.panel>h2`")
live = gut._live_inline_units()
print(f"PASS" if len(live) > 0 else "FAIL", f"legacy.html 仍识别出 {len(live)} 个活选择器单元")
for unit, decls in live:
    if gut._COLOR.search(decls):
        print("FAIL 活规则仍有色值:", unit, decls[:60]); bad += 1
need = {".chain-arrow", ".toast-item.err", ".toast-item.ok"}
missing = need - {u for u, _d in live}
print("PASS" if not missing else "FAIL", f"3 条内联活规则仍在活集合里（缺: {sorted(missing)}）")
print(f"\n结果: {'全部通过' if bad == 0 else f'{bad} 项失败'}")
sys.exit(1 if bad else 0)
