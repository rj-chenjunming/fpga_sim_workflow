"""E 复核：legacy.html skip-link + 焦点环是否真的可用（独立静态服务 + 通用 API 替身）。只读。"""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[2] / "loop" / "web"

class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Q, directory=str(WEB)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
try:
    with sync_playwright() as d:
        b = d.chromium.launch()
        p = b.new_page()
        errs = []
        p.on("pageerror", lambda e: errs.append(str(e)))
        # 通用替身：所有 /api/** 一律 200 + 空对象，让 legacy 页自身脚本不至于炸
        p.route("**/api/**", lambda r: r.fulfill(json={}))
        p.goto(base + "/legacy.html")
        p.wait_for_timeout(400)
        print("[legacy] pageerrors =", errs)
        print("[legacy] 首个 Tab 前 activeElement =",
              p.evaluate("() => document.activeElement && (document.activeElement.tagName + '.' + document.activeElement.className)"))
        p.keyboard.press("Tab")
        f1 = p.evaluate("""() => { const a = document.activeElement, cs = getComputedStyle(a);
          return {tag: a.tagName, cls: a.className, text: (a.textContent || '').trim().slice(0, 20),
                  outline: cs.outlineStyle + ' ' + cs.outlineWidth, top: Math.round(a.getBoundingClientRect().top)}; }""")
        print("[legacy] 首个 Tab 落点 =", f1)
        p.keyboard.press("Enter")
        p.wait_for_timeout(150)
        st = p.evaluate("""() => { const m = document.querySelector('#legacyMain'), a = document.activeElement,
            cs = getComputedStyle(m);
          return {activeIsMain: a === m, active: a && (a.id || a.tagName), tabindex: m.getAttribute('tabindex'),
                  outlineStyle: cs.outlineStyle, outlineWidth: cs.outlineWidth, outlineColor: cs.outlineColor,
                  outlineOffset: cs.outlineOffset, scrollY: Math.round(scrollY)}; }""")
        print("[legacy] Enter 后 =", st)
        # 第二个 Tab：确认既有键盘路径（header 返回链接 → 表单）
        p.keyboard.press("Tab")
        print("[legacy] Enter 后第 2 个 Tab =",
              p.evaluate("() => { const a = document.activeElement; return a.tagName + '#' + a.id + '.' + a.className; }"))
        b.close()
finally:
    srv.shutdown(); srv.server_close()
