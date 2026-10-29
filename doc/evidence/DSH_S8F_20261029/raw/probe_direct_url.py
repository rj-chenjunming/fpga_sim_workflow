"""S8f 真机验收（0 token）：availability 下发的 direct_url 打开后，真的能看到该 attempt 的会话。

复用 S8b 的 attempt 夹具（其会话 cwd 就是该 attempt 的 work）。不调模型：
不进入 execute、不注入 api_key；仅起 dsh --profile web + Playwright 打开页面。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/home/work/chenjunming/change-impact-loop")
sys.path.insert(0, str(REPO / "loop"))

from host import web_instance_ctl as WC          # noqa: E402
from services import instance_proxy as IP        # noqa: E402

RUN_ID = "RUN-20261029-S8B"
NODE = "N6"
ATTEMPT = 1
RUN_DIR = REPO / "loop/.logs/s8b/run" / RUN_ID
OUT = REPO / "loop/.logs/s8f"
CHROME_HOME = REPO / ".chrome-home-s8f"
CHROME_TMP = REPO / ".chrome-tmp-s8f"


def main() -> int:
    facts: dict = {"run_id": RUN_ID, "node": NODE, "attempt": ATTEMPT}
    # 1) 起实例（与生产同一路径：home/cwd 都取自 AttemptLayout）
    started = WC.ensure(RUN_DIR, NODE, ATTEMPT, enable=True)
    facts["instance"] = {k: started.get(k) for k in ("host", "port")}
    try:
        # 2) 走 availability（端点用的同一函数）拿 direct_url
        availability = IP.availability(RUN_DIR, run_id=RUN_ID, node=NODE, attempt=ATTEMPT)
        facts["availability"] = {k: v for k, v in availability.items() if k != "direct_url"}
        direct = availability.get("direct_url")
        facts["has_direct_url"] = bool(direct)
        facts["direct_url_has_token"] = bool(direct and "token=" in direct)
        facts["proxy_url_has_token"] = "token=" in str(availability.get("url"))
        if not direct:
            facts["verdict"] = "no_direct_url"
            (OUT / "probe_facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1

        # 3) Playwright 直接打开 direct_url（不经反代、不经看板）
        from playwright.sync_api import sync_playwright

        CHROME_HOME.mkdir(parents=True, exist_ok=True)
        CHROME_TMP.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(direct, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(6_000)
            html = page.evaluate("() => document.documentElement.innerHTML")
            text = page.evaluate("() => document.body ? document.body.innerText : ''")
            rows = page.evaluate(
                "() => Array.from(document.querySelectorAll('[class*=\"sessionRow\"]')).length")
            url_after = page.url
            page.screenshot(path=str(OUT / "direct_url_page.png"), full_page=False)
            browser.close()

        facts["final_url_has_token"] = "token=" in url_after
        facts["session_rows"] = rows
        facts["session_title_visible"] = "只回复 OK" in text
        facts["session_block_absent"] = "No sessions yet" not in text
        facts["verdict"] = "achieved" if (rows > 0 and "No sessions yet" not in text) else "list_empty"
        (OUT / "probe_facts.json").write_text(
            json.dumps({**facts, "body_text_head": text[:400]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return 0 if facts["verdict"] == "achieved" else 2
    finally:
        try:
            WC.stop(RUN_DIR, NODE)
        except Exception as exc:                       # noqa: BLE001 - 收尾尽力
            print("stop failed:", type(exc).__name__)


if __name__ == "__main__":
    raise SystemExit(main())
