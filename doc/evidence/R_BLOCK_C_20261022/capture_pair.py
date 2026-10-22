#!/usr/bin/env python3
"""F14-b 改前/改后截图对（只读样式、可复现）：同一脚本、同一受控数据、同一视口，
**关闭动画与过渡**后截图，使改前/改后逐张可比、可做 MD5 相等判定。

为什么需要它：常规截图里 `.pulse`/`.spinner` 是无限动画、`.toast`/按钮有 150ms 过渡，
同一份 CSS 两次运行也会拍到不同动画相位，MD5 必然不同——那不能证明视觉等价。
本脚本在每次导航后注入 `animation:none!important;transition:none!important`（只作用于
用于比对的页面，不写仓库），再截图；于是 MD5 相同 ⇔ 像素相同 ⇔ 视觉等价。

用法（可写 HOME + 浏览器路径）：
    cd loop
    HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
      LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
      .venv/bin/python ../doc/evidence/R_BLOCK_C_20261022/capture_pair.py \
        --web <web 目录> --screens-dir <输出目录>

只写 `--screens-dir`；`--web` 只读（可以是 `git archive` 出来的改前快照目录）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from collect_f14a import MockApi, agent_view, populated_view  # noqa: E402
from verify_style_equivalence import HEIGHT, MAIN_VIEWPORTS, serve_dir  # noqa: E402

FREEZE_CSS = "*,*::before,*::after{animation:none!important;transition:none!important}"


def wait_js(page, expr, desc, timeout=8000):
    import time
    deadline = time.time() + timeout / 1000.0
    while time.time() < deadline:
        try:
            if page.evaluate(expr):
                return
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(50)
    raise RuntimeError("等待超时：%s" % desc)


def fresh(page, static_url, api):
    api.hold = None
    api.pending.clear()
    page.goto(static_url)
    page.wait_for_selector(".run-item", timeout=10000)
    page.add_style_tag(content=FREEZE_CSS)
    page.wait_for_timeout(60)


def shot(page, screens_dir, name):
    page.evaluate("() => scrollTo(0, 0)")
    screens_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screens_dir / name), full_page=True)


def capture(browser, static_url, screens_dir):
    width_states = [
        # (状态名, 驱动函数)
        ("s0", None),
        ("setup", "setup"),
        ("dirpicker-baseline", "dirpicker-baseline"),
        ("dirpicker-project", "dirpicker-project"),
        ("run", "run"),
        ("gate", "gate"),
        ("gate-rejected", "gate-rejected"),
        ("agent", "agent"),
        ("empty", "empty"),
        ("loading", "loading"),
        ("first-error", "first-error"),
        ("stale-error", "stale-error"),
        ("run-failed", "run-failed"),
        ("legacy", "legacy"),
    ]
    for width in MAIN_VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        for name, driver in width_states:
            if driver == "legacy":
                page.goto(static_url + "/legacy.html")
                page.add_style_tag(content=FREEZE_CSS)
                page.wait_for_timeout(150)
                shot(page, screens_dir, "%d-%s.png" % (width, name))
                continue
            fresh(page, static_url, api)
            if driver in (None,):
                pass
            elif driver == "empty":
                page.locator("#segRun").click()
                page.wait_for_timeout(120)
            elif driver == "setup":
                page.locator("#segSetup").click()
                page.locator("#btnRefreshBaselines").click()
                wait_js(page, "() => document.querySelectorAll('#setupBaseline option').length > 1",
                        "基线下拉")
            elif driver == "dirpicker-baseline":
                page.locator("#segSetup").click()
                page.wait_for_timeout(100)
                page.locator("#btnBaselineBrowse").click()
                page.wait_for_timeout(150)
            elif driver == "dirpicker-project":
                page.locator("#segSetup").click()
                page.wait_for_timeout(100)
                page.locator("#btnProjectBrowse").click()
                wait_js(page, "() => document.querySelectorAll('#dirList .dp-item').length > 0",
                        "项目目录浏览器")
            elif driver == "run":
                populated_view(api.views["A"])
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#runHead').innerText.includes('v1.2-stable')",
                        "运行头")
                page.locator("#segRun").click()
                page.wait_for_timeout(120)
            elif driver == "gate":
                populated_view(api.views["A"])
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#gatePanel [aria-label=\"actor\"]')",
                        "闸门表单")
                page.locator("#segGate").click()
                page.wait_for_timeout(120)
            elif driver == "gate-rejected":
                populated_view(api.views["A"])
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#gatePanel [aria-label=\"actor\"]')",
                        "闸门表单")
                page.locator('#gatePanel input[value="confirmed"]').check()
                page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
                page.locator('#gatePanel [aria-label="裁决理由"]').fill("已逐条核对差异与证据")
                page.locator("#gatePanel [data-gate-submit]").evaluate(
                    "el => { el.click(); el.click(); }")
                page.wait_for_timeout(150)
                api.pending.pop(0).fulfill(
                    status=403,
                    json={"detail": {"error": "refused",
                                     "blockers": [{"code": "I4", "message": "闸门材料未确认"}],
                                     "note": "gate unchanged；中断未被消耗"}})
                wait_js(page, "() => document.querySelector('#gatePanel .gate-error') && "
                              "document.querySelector('#gatePanel .gate-error').innerText.length > 0",
                        "闸门拒绝提示")
            elif driver == "agent":
                populated_view(api.views["A"])
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#agents [data-agent-node=\"N3\"]')",
                        "Agent 卡片")
                page.locator("#segRun").click()
                page.route("**/api/runs/*/agents/**",
                           lambda route: route.fulfill(json=agent_view()))
                page.locator("#agents [data-agent-node=\"N3\"]").click()
                wait_js(page, "() => document.querySelector('#agentWindow') && "
                              "document.querySelector('#agentWindow').open", "Agent 窗口")
                page.wait_for_timeout(150)
                # 模态窗口：截视口而非整页
                page.evaluate("() => scrollTo(0, 0)")
                screens_dir.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screens_dir / ("%d-%s.png" % (width, name))),
                                full_page=False)
                continue
            elif driver == "loading":
                page.locator("#segRun").click()
                api.hold = lambda path: path == "/api/runs/A"
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#runHead') && "
                              "document.querySelector('#runHead').innerText.includes('加载中')",
                        "加载态")
            elif driver == "first-error":
                page.locator("#segRun").click()
                api.hold = lambda path: path == "/api/runs/A"
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#runHead') && "
                              "document.querySelector('#runHead').innerText.includes('加载中')",
                        "加载态")
                api.pending.pop(0).fulfill(
                    status=503,
                    json={"detail": {"error": "证据读取失败：" + "/simulation/long-project/" * 12}})
                wait_js(page, "() => document.querySelector('#runHead') && "
                              "document.querySelector('#runHead').innerText.includes('读取失败')",
                        "首次失败")
            elif driver == "stale-error":
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#runHead') && "
                              "document.querySelector('#runHead').innerText.includes('A-baseline')",
                        "首次成功")
                page.locator("#segRun").click()
                api.hold = lambda path: path == "/api/runs/A"
                page.clock.run_for(1600)
                page.wait_for_timeout(90)
                api.pending.pop(0).fulfill(status=503, json={"detail": {"error": "轮询超时"}})
                wait_js(page, "() => document.querySelector('#runAlerts') && "
                              "document.querySelector('#runAlerts').innerText.includes('数据已过期')",
                        "陈旧失败")
            elif driver == "run-failed":
                failed = populated_view(api.views["A"])
                failed.update(status="failed", error="N7 编译失败：uvs 退出码 1",
                              notes=["需要人工确认 RTL 接口改动"])
                page.locator(".run-item").filter(has_text="A").click()
                wait_js(page, "() => document.querySelector('#runHead') && "
                              "document.querySelector('#runHead').innerText.includes('v1.2-stable')",
                        "运行头")
                page.locator("#segRun").click()
                page.clock.run_for(1600)
                page.wait_for_timeout(90)
                wait_js(page, "() => document.querySelector('#runAlerts') && "
                              "document.querySelector('#runAlerts').innerText.includes('运行失败')",
                        "运行失败")
            else:
                raise ValueError(driver)
            shot(page, screens_dir, "%d-%s.png" % (width, name))
        page.close()
        context.close()
        print("captured width=%d" % width)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", required=True, help="要渲染的 web 目录（只读）")
    parser.add_argument("--screens-dir", required=True, help="截图输出目录")
    args = parser.parse_args(argv)
    web = Path(args.web).resolve()
    if not (web / "index.html").exists():
        print("缺少 index.html：%s" % web, file=sys.stderr)
        return 2
    screens_dir = Path(args.screens_dir).resolve()
    from playwright.sync_api import sync_playwright

    server, thread, static_url = serve_dir(web)
    try:
        with sync_playwright() as pw:
            executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
            browser = pw.chromium.launch(
                **({"executable_path": executable} if executable else {}))
            try:
                capture(browser, static_url, screens_dir)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    files = sorted(screens_dir.glob("*.png"))
    print("截图完成：%d 张（%s）" % (len(files), screens_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
