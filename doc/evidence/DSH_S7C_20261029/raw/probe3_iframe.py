"""S7c 探针 #3（一次性，gitignored，不入库）：真机 iframe 取证（第 3 次 web 启动，不调模型）。

做什么：
1. 用本片模块起一个真 DSH Web 实例（隔离 home，env 无凭据）；原子落账 `agent_instance.json`；
2. 起看板（uvicorn 包装，仅替换 `_manager`）；
3. Playwright(Chromium) 先**顶层**打开经反代的 URL，再在**同源 iframe**里打开同一 URL
   （真实形态：看板自己的页面里嵌 `/instance/…`），采集：
   - `document.title`、`<base>`、`#root` 是否渲染、body 可见文本；
   - 网络：`assets/*.js` 与 `*.css` 的状态分布、`requestfailed` 全量；
   - console（**逐字**）与 pageerror，特别是 `remote.mux` 的报错原文；
   - WebSocket 事件（建立/失败）；
   - 按钮"能否点"：**不真的点**（点击可能触发模型调用）⇒ 用 `elementFromPoint` 命中测试 +
     未 disabled 按钮计数，判断有没有遮罩层盖住。
4. 截图 `iframe.png`（iframe 元素区域）与 `proxy_top.png`（顶层），报像素尺寸。
5. 收尾：停看板 + 停实例 + 删元数据 + 残留自证。
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/work/chenjunming/change-impact-loop")
LOOP = REPO / "loop"
OUT = LOOP / ".logs" / "s7c"
RUN_ID = "S7C-RUN-0001"
NODE = "N3"
ATTEMPT = 1
BOARD_PORT = 8098

sys.path.insert(0, str(LOOP))
from host.agent_backends import dsh_web_instance as WI  # noqa: E402

lines: list[str] = []


def say(text: str = "") -> None:
    lines.append(text)
    print(text, flush=True)


def redact(text: str) -> str:
    return re.sub(r"(token=)[A-Za-z0-9_\-]{8,}", r"\1<redacted>", text)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


MEASURE_JS = r"""
() => {
  const base = document.querySelector('base');
  const root = document.getElementById('root');
  const buttons = Array.from(document.querySelectorAll('button'));
  const enabled = buttons.filter(b => !b.disabled);
  const hit = enabled.map(b => {
    const r = b.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return {text: b.innerText.trim().slice(0, 24), hit: 'zero-size'};
    const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return {text: b.innerText.trim().slice(0, 24),
            hit: el === b || (el && b.contains(el)) ? 'button' : (el ? (el.tagName + '.' + (el.className || '')).slice(0, 60) : 'null')};
  });
  const alerts = Array.from(document.querySelectorAll(
      '[role="alert"], [class*="error"], [data-testid*="error"]'))
    .map(el => ({tag: el.tagName, cls: String(el.className).slice(0, 80),
                 text: (el.innerText || '').trim().slice(0, 200)}))
    .slice(0, 10);
  return {
    title: document.title,
    base: base ? base.getAttribute('href') : null,
    baseURI: document.baseURI,
    readyState: document.readyState,
    rootExists: !!root,
    rootChildren: root ? root.children.length : null,
    rootHtmlLen: root ? root.innerHTML.length : null,
    bodyText: (document.body.innerText || '').replace(/\s+\n/g, '\n').trim().slice(0, 1200),
    bodyHtmlLen: document.body.innerHTML.length,
    darkTheme: document.body.hasAttribute('data-ds-dark-theme'),
    buttonTotal: buttons.length,
    buttonEnabled: enabled.length,
    buttonHitSample: hit.slice(0, 8),
    alerts: alerts,
    scrollHeight: document.documentElement.scrollHeight,
  };
}
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    run_dir = OUT / "run" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    home = OUT / "home3"
    home.mkdir(parents=True, exist_ok=True)

    config = WI.WebInstanceConfig(
        enabled=True,
        node=Path("/home/soft/DSH/node/bin/node"),
        bin=Path("/home/soft/DSH/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js"),
        version="0.2.1-rc.2",
        home=home, host="127.0.0.1", preferred_port=18799,
        start_timeout_s=40.0, stop_grace_s=3.0)

    say("### 1) 第 3 次启动（模块起实例；不调模型）")
    instance = WI.WebInstance(config)
    try:
        instance.start()
    except WI.WebInstanceError as exc:
        say(f"!! 起实例失败：{exc}")
        return 2
    target = instance.target
    say(f"stdout 公告行（token 打码）= dsh web: {target.origin}/?token="
        f"<redacted {len(target.token or '')} chars>")
    say(f"实际端口 = {target.port} ；startup_s = {instance.startup_s} ；"
        f"describe() = {json.dumps(instance.describe(), ensure_ascii=False)}")
    meta_path = instance.write_metadata(run_dir, node=NODE, attempt=ATTEMPT)
    document = json.loads(meta_path.read_text(encoding="utf-8"))
    say(f"agent_instance.json: keys = {sorted(document)} ；mode = "
        f"{oct(meta_path.stat().st_mode & 0o777)} ；"
        f"token = <redacted {len(document.get('token') or '')} chars> ；"
        f"host:port = {document['host']}:{document['port']}")

    say("### 2) 起看板（uvicorn 包装）")
    wrapper = OUT / "probe2_app.py"
    board = subprocess.Popen([str(LOOP / ".venv" / "bin" / "python"), str(wrapper)],
                             cwd=str(LOOP), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True)
    import httpx
    base = f"http://127.0.0.1:{BOARD_PORT}"
    client = httpx.Client(trust_env=False, timeout=30.0, follow_redirects=False)
    prefix = f"/instance/{RUN_ID}/{NODE}/{ATTEMPT}/"
    for _ in range(120):
        try:
            client.get(f"{base}/api/health")
            break
        except (httpx.HTTPError, OSError):
            time.sleep(0.25)
    else:
        say("!! 看板没起来")
        board.terminate()
        instance.stop(remove_metadata=run_dir)
        return 3
    say(f"看板 = {base} ；可用性端点 = " + json.dumps(
        client.get(f"{base}/api/runs/{RUN_ID}/agents/{NODE}/instance",
                   params={"attempt": ATTEMPT}).json(), ensure_ascii=False))

    say("### 3) Playwright 真机采集")
    from playwright.sync_api import sync_playwright

    console: list[str] = []
    pageerrors: list[str] = []
    failed: list[str] = []
    responses: list[tuple[str, int]] = []
    sockets: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.on("console", lambda msg: console.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda exc: pageerrors.append(str(exc)))
            page.on("requestfailed",
                    lambda req: failed.append(f"{req.method} {req.url} :: {req.failure}"))
            page.on("response", lambda r: responses.append((r.url, r.status)))
            page.on("websocket", lambda ws: sockets.append(f"open {ws.url}"))

            # ---- Phase A：顶层直接打开反代 URL
            page.goto(base + prefix, wait_until="load", timeout=60000)
            page.wait_for_timeout(18000)  # generationReadyTimeoutMs = 15000
            top = page.evaluate(MEASURE_JS)
            page.screenshot(path=str(OUT / "proxy_top.png"))
            say("#### A. 顶层打开经反代的 URL")
            say(f"title = {top['title']!r} ；base = {top['base']!r} ；baseURI = {top['baseURI']}")
            say(f"readyState = {top['readyState']} ；#root 存在 = {top['rootExists']} ；"
                f"#root.children = {top['rootChildren']} ；#root.innerHTML = {top['rootHtmlLen']} 字符")
            say(f"body.innerText 长度 = {len(top['bodyText'])} ；darkTheme = {top['darkTheme']} ；"
                f"scrollHeight = {top['scrollHeight']}")
            say("body.innerText（前 700 字）：\n" + top["bodyText"][:700])
            say(f"按钮 total/enabled = {top['buttonTotal']}/{top['buttonEnabled']}")

            # ---- Phase B：真实形态 —— 看板页面里的同源 iframe
            page.goto(base + "/", wait_until="load", timeout=60000)
            page.evaluate(
                """(src) => {
                     const f = document.createElement('iframe');
                     f.id = 's7cFrame';
                     f.style.cssText = 'position:fixed;left:0;top:0;width:1280px;height:860px;border:0;z-index:99999';
                     f.src = src;
                     document.body.appendChild(f);
                   }""", prefix)
            page.wait_for_selector("#s7cFrame", timeout=30000)
            page.wait_for_timeout(18000)
            frame = next((fr for fr in page.frames if fr.url.endswith(prefix)), None)
            say("#### B. 同源 iframe（看板页面里嵌 /instance/…）")
            if frame is None:
                say("!! 没拿到 iframe 的 Frame 句柄")
                inner = None
            else:
                inner = frame.evaluate(MEASURE_JS)
                say(f"iframe URL = {frame.url}")
                say(f"title = {inner['title']!r} ；base = {inner['base']!r}")
                say(f"#root 存在 = {inner['rootExists']} ；#root.children = {inner['rootChildren']} ；"
                    f"#root.innerHTML = {inner['rootHtmlLen']} 字符 ；"
                    f"body.innerText 长度 = {len(inner['bodyText'])}")
                say("iframe body.innerText（前 700 字）：\n" + inner["bodyText"][:700])
                say(f"按钮 total/enabled = {inner['buttonTotal']}/{inner['buttonEnabled']}")
                say("按钮命中测试（elementFromPoint；'button' = 没被遮罩盖住）：")
                for item in inner["buttonHitSample"]:
                    say(f"  {item['text']!r:28} -> {item['hit']}")
                say("error/alert 元素 = " + json.dumps(inner["alerts"], ensure_ascii=False)[:800])
            shot = OUT / "iframe.png"
            page.locator("#s7cFrame").screenshot(path=str(shot))
            width, height = png_size(shot)
            say(f"截图 = {shot} ；像素 = {width}x{height} ；bytes = {shot.stat().st_size}")

            # ---- 网络
            asset = [r for r in responses if "/assets/" in r[0]]
            plugins = [r for r in responses if "/plugins/" in r[0]]
            bad = [r for r in asset if r[1] != 200]
            say("#### C. 网络")
            say(f"`assets/*` 响应 {len(asset)} 条，全部 200 = {not bad} ；非 200 = {bad}")
            say("assets 明细：" + json.dumps(sorted(set((u.rsplit('/', 1)[-1], s) for u, s in asset)),
                                            ensure_ascii=False))
            say(f"`plugins/??…` 批量响应 {len(plugins)} 条，状态分布 = "
                + json.dumps(sorted(set(s for _, s in plugins))))
            say(f"requestfailed {len(failed)} 条：")
            for item in failed:
                say("  " + redact(item))
            say(f"WebSocket 事件 {len(sockets)} 条：" + json.dumps(sockets, ensure_ascii=False))
            say(f"console {len(console)} 条（逐字）：")
            for item in console:
                say("  " + redact(item))
            say(f"pageerror {len(pageerrors)} 条（逐字）：")
            for item in pageerrors:
                say("  " + redact(item))
            context.close()
            browser.close()
    finally:
        client.close()
        board.terminate()
        try:
            board.wait(timeout=10)
        except subprocess.TimeoutExpired:
            board.kill()
        instance.stop(remove_metadata=run_dir)
        leftover = subprocess.run(["pgrep", "-af", "bin.js --profile web"],
                                  capture_output=True, text=True).stdout.strip() or "(none)"
        say("### 4) 收尾")
        say(f"实例 running = {instance.is_running()} ；元数据已删 = "
            f"{not (run_dir / 'agent_instance.json').exists()} ；残留 = {leftover}")

    (OUT / "probe3_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
