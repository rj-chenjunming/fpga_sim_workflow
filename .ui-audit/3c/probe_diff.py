#!/usr/bin/env python3
"""定位用：对比两个 web 目录里指定元素的计算样式逐属性差异（单宽度单状态）。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from collect_f14a import MockApi, populated_view, serve_web  # noqa: E402

from playwright.sync_api import sync_playwright

JS = r"""
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  const out = {};
  for (let i = 0; i < cs.length; i++) out[cs[i]] = cs.getPropertyValue(cs[i]);
  for (const pseudo of ['::before', '::after']) {
    const pcs = getComputedStyle(el, pseudo);
    for (let i = 0; i < pcs.length; i++) out[pseudo + ' ' + pcs[i]] = pcs.getPropertyValue(pcs[i]);
  }
  return out;
}
"""


def serve_dir(path: Path):
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = partial(Handler, directory=str(path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, "http://127.0.0.1:%d" % server.server_address[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--before-web", required=True)
    ap.add_argument("--after-web", required=True)
    ap.add_argument("--selector", required=True)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1000)
    ap.add_argument("--state", default="s0")
    args = ap.parse_args()

    results = {}
    servers = []
    try:
        with sync_playwright() as pw:
            exe = os.environ.get("LOOP_BROWSER_EXECUTABLE")
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
            for label, web in (("before", args.before_web), ("after", args.after_web)):
                server, thread, url = serve_dir(Path(web))
                servers.append((server, thread))
                ctx = browser.new_context(viewport={"width": args.width, "height": args.height})
                page = ctx.new_page()
                page.clock.install()
                api = MockApi(page)
                page.goto(url)
                page.wait_for_selector(".run-item", timeout=10000)
                if args.state == "run":
                    populated_view(api.views["A"])
                    page.locator(".run-item").filter(has_text="A").click()
                    page.wait_for_timeout(300)
                    page.locator("#segRun").click()
                page.wait_for_timeout(400)
                results[label] = page.evaluate(JS, args.selector)
                ctx.close()
            browser.close()
    finally:
        for server, thread in servers:
            server.shutdown()
            server.server_close()
    b, a = results["before"], results["after"]
    if b is None or a is None:
        print("元素不存在:", args.selector, bool(b), bool(a))
        return 2
    diffs = {k: (b.get(k), a.get(k)) for k in set(b) | set(a) if b.get(k) != a.get(k)}
    print("属性差异 %d 条（%s @ %dx%d %s）" % (len(diffs), args.selector, args.width,
                                          args.height, args.state))
    for k in sorted(diffs):
        print("  %-42s %r -> %r" % (k, diffs[k][0], diffs[k][1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
