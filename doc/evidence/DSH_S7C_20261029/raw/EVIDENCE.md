# S7c 取证档（2026-10-29，一次性，gitignored，不入库）

> 本文件是 `s7c-proxy` 片的一次性探针证据汇总。**token / cookie 值一律脱敏**（保留长度与字符集事实）。
> 真实调用额度：S7c 授权 **≤2 次**，本文对应 **2 次**（均为本地起 `dsh --profile web` 取页面/头，**不调模型**）。
> 原始件：`run1.stdout`（公告行，token 已打码）、`index.html`（37512 B 原文）、`h_*.txt`（响应头）、
> `b_*.txt`（响应体）、`index_refs.txt`、`probe2_report.txt`（模块起实例 + 走反代的完整报告）。

## 0 决定性判据：上游是否用绝对路径？（B3 的 (b)(c)(a) 选择依据）

### 0.1 随包 `dist/index.html`（`dsh-web-frontend/dist/index.html`，825 B，逐字）

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="manifest" href="./manifest.webmanifest" />
    <link rel="icon" type="image/svg+xml" href="./favicon-dark.svg" media="(prefers-color-scheme: dark)" />
    <link rel="icon" type="image/svg+xml" href="./favicon.svg" media="(prefers-color-scheme: light)" />
    <title>DeepSeek Harness</title>
    <script type="module" crossorigin src="./assets/index-CN7NIWNw.js"></script>
    <link rel="modulepreload" crossorigin href="./assets/vendor-DcuzkuQH.js">
    <link rel="stylesheet" crossorigin href="./assets/vendor-DV2921Zo.css">
    <link rel="stylesheet" crossorigin href="./assets/index-BxpfOGf3.css">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
```

### 0.2 真机服务端实际吐出的 `index.html`（37512 B）关键片段（逐字）

```html
<head><base href="./"><style>:root{color-scheme:light}…</style><script>globalThis["__DSH_CONTACT_CONFIG__"] = …</script>
<script src="plugins/??@deepseek-ai/dsh-client-modules/client.js&amp;rev=089404108e2a"></script>
…
<link rel="manifest" href="./manifest.webmanifest" />
<link rel="icon" type="image/svg+xml" href="./favicon-dark.svg" media="(prefers-color-scheme: dark)" />
<link rel="icon" type="image/svg+xml" href="./favicon.svg" media="(prefers-color-scheme: light)" />
<title>DeepSeek Harness</title>
<script type="module" crossorigin src="./assets/index-CN7NIWNw.js"></script>
<link rel="modulepreload" crossorigin href="./assets/vendor-DcuzkuQH.js">
<link rel="stylesheet" crossorigin href="./assets/vendor-DV2921Zo.css">
<link rel="stylesheet" crossorigin href="./assets/index-BxpfOGf3.css">
```

### 0.3 资源引用清单（`index_refs.txt`，共 11 条；**以 `/` 开头 0 条**）

| 引用 | 以 `/` 开头 | query 长度 |
|---|---|---|
| `./`（`<base href="./">`） | 否 | 0 |
| `plugins/??@deepseek-ai/…（应用批 57 模块）&rev=57e1decf52e2` | 否 | **2813** |
| `plugins/??@deepseek-ai/…（第二批 11 模块）&rev=66bee40d69ad` | 否 | 546 |
| `plugins/??@deepseek-ai/dsh-client-modules/client.js&rev=089404108e2a` | 否 | 63 |
| `./manifest.webmanifest` | 否 | 0 |
| `./favicon-dark.svg` | 否 | 0 |
| `./favicon.svg` | 否 | 0 |
| `./assets/index-CN7NIWNw.js` | 否 | 0 |
| `./assets/vendor-DcuzkuQH.js` | 否 | 0 |
| `./assets/vendor-DV2921Zo.css` | 否 | 0 |
| `./assets/index-BxpfOGf3.css` | 否 | 0 |

- `<base>` 标签：**有**，`<base href="./">`（服务端注入）。
- CSP `<meta>` / `frame-ancestors` / `X-Frame-Options`：**均无**（`grep -oiE` 无匹配）。
- 客户端 API 走**相对** URL：`dsh-api-gateway/lib/client.browser.js` L761
  `const url = new URL(REMOTE_STREAM_MUX_PATH.slice(1), globals.__DSH_TRANSPORT__?.streamBaseUrl ?? document.baseURI)`
  ⇒ WS 地址相对 `document.baseURI`；unary RPC 见 `dsh-client-connection/lib/client.browser.js` L1218
  ``send(`${channel}/${endpoint}`.slice(1), …)`` ⇒ **相对**。

### 0.4 (b)(c)(a) 判断

| 方案 | 是否可行 | 结论依据 |
|---|---|---|
| **(b) 上游 base path 配置** | **不存在"路由/base path"配置**；`--public-url` 只是**广告**用途 | `dsh-web-app/README.md` L79 原文："`--public-url` advertises the HTTP(S) root browsers use — the printed and opened startup URL, `DSH_WEB_URL`, and the Web GUI URL in the agent's runtime context. **The flag configures no listener, routing, or cookie scope**, because the proxy owns the external leg"；`lib/public-url-D_dMK-yI.js` 只做校验+尾斜杠归一 |
| **(c) 第二个 loopback 反代端口** | **不必要** | 上游全程相对引用（§0.3），前缀剥离后浏览器自动把 `./assets/…` 解析到 `<前缀>/assets/…` |
| **(a) HTML 前缀化改写** | **不必要，且不应做** | 0 条绝对引用；改写只会引入"改上游内容"的风险（REV-16 §9-10 原本的顾虑在本版本不成立）。用例 `test_s7c_real_index_html_forwarded_byte_identical` 逐字节锁住"反代不改写 HTML" |

**唯一剩余的传输缺口不是路径，而是 WebSocket 升级**（`WS /api/remote.mux`，见 §3）。

## 1 起实例（探针 #1：`--port 0`，实测公告行形态与 401 门）

```bash
DSH_HOME=$OUT/home node /home/soft/DSH/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js \
  --profile web --host 127.0.0.1 --port 0 --no-open
```

stdout（唯一一行，token 已打码，**长度 43、字符集 [A-Za-z0-9_-]**）：

```text
dsh web: http://127.0.0.1:44239/?token=<redacted 43 chars>
```

`--port 0` **可用**（`--help` 原文 "listen port; pass 0 to let the OS pick a free one"），
端口由 OS 决定、**公告行里给的是实际端口**（本例 44239）。

## 2 `/api` 是否 403？（拿 cookie 前后各一次）

匿名：

```text
HTTP/1.1 401 Unauthorized
cache-control: no-store
content-type: text/plain; charset=utf-8
（体：`unauthorized`）
```

`?token=` 交换（`h_mint.txt`，逐字）：

```text
HTTP/1.1 303 See Other
cache-control: no-store
location: ./
referrer-policy: no-referrer
set-cookie: dsh-auth-uo7ZLgk0z9HuRlMCBeqBDQAC1VbqiPIRHxGt2tlui-k=v1.…;  Max-Age=2592000; Path=/; Expires=Sat, 28 Nov 2026 01:54:47 GMT; HttpOnly; SameSite=Strict
```

带 cookie 后 `POST /api/session/list`（`h_api_auth.txt` / `b_api_auth.txt`）：

```text
HTTP/1.1 200 OK
content-type: application/json
{"type":"server-response","rpcId":"p-2","result":{"ok":true,"value":{"items":[]}}}
```

⇒ **不是 403**。但注意：**跨权威**（`Origin` 不是本权威、`sec-fetch-site: cross-site`）或伪 `Host` 会 403（P8 §4.3 实测 14/15/17），
这正是不改 `Origin`/`Sec-Fetch-Site` 就走不通的原因（反代已按 §5.4 改写）。

`GET /api/remote.mux`（不带 `Upgrade`）：`404 not found` ⇒ 该路由是**升级专用**。

## 3 探针 #2：用本片新模块起实例 + 走同源反代（`probe2_report.txt`）

```
### 1) 用本片模块起实例
argv = /home/soft/DSH/node/bin/node …/dsh/lib/bin.js --profile web --host 127.0.0.1 --port 18799 --no-open
env keys = DSH_HOME, DSH_PROFILE, HOME, LANG, PATH, PYTHONDONTWRITEBYTECODE        # ← 无任何凭据
describe() = {"host":"127.0.0.1","port":18799,"pid":6,"running":true,
              "port_requested":18799,"port_fallback":false,"startup_s":3.179,"stderr_tail":[]}
实际监听 = 127.0.0.1:18799 ；token 长度 = 43 ；字符集 = [A-Za-z0-9_-]

### 2) 原子落账
mode = 0o600 ；keys = ['attempt','host','node','port','token','written_at']
document(token 脱敏) = {"attempt":1,"host":"127.0.0.1","node":"N3","port":18799,
                        "token":"<redacted 43 chars>","written_at":"2026-10-29T10:00:53.615398"}

### 4) 可用性端点（§6.1）
availability = {"available":true,"state":"ready","reason":null,
                "url":"/instance/S7C-RUN-0001/N3/1/","embed":"iframe",
                "authority":"projection","stream":"http_only","attempt":1}

### 5) 首跳：无 cookie ⇒ 反代注入受管 token（上游 303 + cookie）
status = 303
location: /instance/S7C-RUN-0001/N3/1/
set-cookie: dsh-auth-…=v1.…; Path=/instance/S7C-RUN-0001/N3/1/; Max-Age=2592000; …; HttpOnly; SameSite=Strict
token 出现在响应里？ = False

### 6) 第二跳：带 cookie 取 index.html
status = 200 ；content-type = text/html; charset=utf-8 ；bytes = 37512
含 <base href="./"> = True
引用总数 = 11 ；以 / 开头的绝对引用 = 0
XFO = None ；CSP = None

### 7) 相对资源经反代可取
  ./assets/index-CN7NIWNw.js  -> 200 text/javascript  939867 B
  ./assets/index-BxpfOGf3.css -> 200 text/css          77343 B
  ./manifest.webmanifest      -> 200 application/manifest+json  255 B
  ./favicon.svg               -> 200 image/svg+xml      3634 B

### 8) 批量插件 URL（plugins/??…&rev=…）
  query 长度 = 2809
  -> 200 text/javascript  9198843 B          # 9.2 MB 插件批全量经反代送达

### 9) /api 不 403：POST session/list 经反代
status = 200 ；body = {"type":"server-response","rpcId":"s7c-1","result":{"ok":true,"value":{"items":[]}}}
是 403 吗 = False

### 10) 匿名直连上游
直连上游匿名 GET / = 401（期望 401）        # token 门未因反代削弱

### 11) WebSocket 升级面
升级请求 -> 405 ；x-instance-proxy = rejected
同路径普通 GET -> 404（上游对非升级请求的真实回答）

### 12) 反代零写入
run_dir 文件 = ["agent_instance.json"]

### 13) 收尾
实例 running = False ；元数据已删 = True
残留 node 进程 = (none)
```

## 4 未验（额度已用尽，需人/Lead 授权第 3 次启动才能做）

**浏览器内 iframe 的真实渲染结果**（Playwright 打开 `/instance/…/`，看 DSH 前端在 WebSocket 405 下是否
落到"只能读快照"还是"报错覆盖层"）。已知事实 + 代码判据（非实测）：
`dsh-client-ui-*` 的 `__DSH_CONNECTION_RECOVERY__ = {generationReadyWarnMs:3000, generationReadyTimeoutMs:15000, …}`
⇒ 事件流不通时客户端会在 3 s 警告 / 15 s 超时；而会话快照（`session/list`、`session/page`）走 unary HTTP 可用。
因此**界面已按"内嵌成功但实时流未接通"如实披露**（`#awEmbedStream`，文案由服务端 `stream=http_only` 驱动），
但"页面在浏览器里到底长什么样"仍未实测，**不声称**。

## 5 探针 #3：真机 iframe 取证（第 3 次启动，Playwright/Chromium，不调模型）

原始件：`probe3_report.txt`（全量）、`iframe.png`（iframe 元素截图 1280x860 / 40349 B）、
`proxy_top.png`（顶层截图）、`probe3_iframe.py`（脚本）。

### 5.1 启动事实（模块起实例）

```text
stdout 公告行（token 打码）= dsh web: http://127.0.0.1:18799/?token=<redacted 43 chars>
实际端口 = 18799 ；startup_s = 3.08 ；port_requested = 18799 ；port_fallback = false
describe() = {"host":"127.0.0.1","port":18799,"pid":6,"running":true,"startup_s":3.08,"stderr_tail":[]}
agent_instance.json: keys = ['attempt','host','node','port','token','written_at'] ；mode = 0o600
                     token = <redacted 43 chars> ；host:port = 127.0.0.1:18799
可用性端点 = {"available":true,"state":"ready","reason":null,"url":"/instance/S7C-RUN-0001/N3/1/",
             "embed":"iframe","authority":"projection","stream":"http_only","attempt":1}
```

### 5.2 DOM 断言（顶层 与 同源 iframe **两次**都测，结果一致）

| 断言 | 顶层 | 同源 iframe |
|---|---|---|
| `document.title` | `'DeepSeek Harness'` | `'DeepSeek Harness'` |
| `<base href>` | `'./'` | `'./'` |
| `document.baseURI` | `http://127.0.0.1:8098/instance/S7C-RUN-0001/N3/1/` | 同 |
| `#root` 存在 / 子节点数 | `true` / `1` | `true` / `1` |
| `#root.innerHTML` 长度 | 39916 字符 | 39916 字符 |
| `body.innerText` 长度 | 168 | 168 |
| `readyState` | `complete` | — |
| 按钮 total / enabled | 14 / 12 | 14 / 12 |
| error/alert 元素 | `[]` | `[]` |

`body.innerText`（逐字，两处相同）：

```text
New Session
Plugins
Automation tasks
Workspaces
No sessions yet
More
Reconnecting...
Into the Unknown
Preview
Choose workspace
Standard mode
Choose a workspace to start
```

关键 DOM 选择器：`#root`（React 根）、`.sidebar` 侧栏（New Session / Plugins / Automation tasks /
Workspaces / No sessions yet / More）、主区 hero（Into the Unknown / Preview / Choose workspace /
Standard mode / Choose a workspace to start）、左下状态 chip 文本 **`Reconnecting...`**。

按钮"能否点"（**未真点**：点击可能触发模型调用）——`elementFromPoint` 命中测试 8 个采样按钮，
8/8 命中按钮本身（无遮罩层）：

```text
  ''                -> button        'New Session'     -> button
  'Plugins'         -> button        'Automation tasks'-> button
  （其余 4 个空文本按钮同样 -> button）
```

截图：`loop/.logs/s7c/iframe.png`，**1280x860 px**，40349 B（画面：完整侧栏 + 主区 + 左下
"Reconnecting..." 状态 chip；**非白屏、无错误覆盖层**）。

### 5.3 网络

```text
`assets/*` 响应 8 条，全部 200 = True ；非 200 = []
明细：[["index-BxpfOGf3.css",200],["index-CN7NIWNw.js",200],
       ["vendor-DV2921Zo.css",200],["vendor-DcuzkuQH.js",200]]
`plugins/??…` 批量响应 9 条，状态分布 = [200]
requestfailed 1 条：
  GET http://127.0.0.1:8098/instance/S7C-RUN-0001/N3/1/plugins/events :: net::ERR_INCOMPLETE_CHUNKED_ENCODING
pageerror 0 条
```

### 5.4 console（逐字，34 条；token 不打码处本来就没有 token）

`WS 405` × 13（每次重试一条，原文）：

```text
[error] WebSocket connection to 'ws://127.0.0.1:8098/instance/S7C-RUN-0001/N3/1/api/remote.mux'
        failed: Error during WebSocket handshake: Unexpected response code: 405
```

退避重试 × 10（`backoffBaseMs=500 / factor=2 / max=10000`）：

```text
[warning] [connection] connection lost, retry #1
… retry #2 / #3 / #4 / #5
[warning] [connection] generation is still not ready after 3000ms
```

其它 2 条：

```text
[error] Failed to load resource: net::ERR_INCOMPLETE_CHUNKED_ENCODING      # plugins/events（SSE）
[error] Failed to load resource: the server responded with a status of 500 (Internal Server Error)  × 9
```

### 5.5 **半死 vs 只缺实时流：结论 = 只缺实时流（页面活着）**

判据（全部可复现）：`#root` 渲染出 39916 字符 DOM、body.innerText 168 字符可读、12 个按钮 enabled
且 `elementFromPoint` 命中自身（无遮罩）、`pageerror` 0 条、截图非白屏；唯独实时事件流的 WS 握手 405，
DSH **自己在左下角显示 `Reconnecting...`** 并按退避重试（不是静默白屏）。会话快照类 unary RPC 走 HTTP
可用（probe #2：`POST /api/session/list` 200），因此"页面可开、可读快照、实时更新停"成立。

**未定位（照实记）**：9 条 `500 (Internal Server Error)` 的**具体 URL 未记录** —— 本次采集只 dump 了
`assets/*`、`plugins/*` 子集与 `requestfailed`，全量 `responses` 没落盘。两种候选原因：① 探针夹具
（`probe2_app.py` 的 `FakeManager`）导致**看板自身** `/api/…` 500（Phase B 导航到看板页时引入）；
② DSH 侧某端点真 500。**下次取证必须全量 dump `(url,status)` 并分离"看板页事件流"与"iframe 事件流"**。
同理 `plugins/events` 的 `ERR_INCOMPLETE_CHUNKED_ENCODING`（SSE）也待定位（可能是客户端 abort 或反代流式收尾）。

### 5.6 生命周期序列确认（Lead 裁决 #2：per-attempt 实例 + 结束后保留 + 下次替换）

- `resolve_port(preferred)`：**起进程之前**一次 bind 探测决定（空闲⇒用固定端口；占用⇒`0`），**不重试**、
  不二次起进程 —— 代码即如此，用例 `test_resolve_port_falls_back_when_preferred_is_busy`。
- `stop()` **可重入**：`self._proc = None` 后第二次调用不再发信号、join 空线程表；`remove_metadata`
  幂等（`clear_metadata` 缺失返回 `False`）。用例 `test_clear_metadata_makes_reader_report_target_missing`。
- **再次起同 home**：模块层无 home 级状态（`home.mkdir(parents=True, exist_ok=True)`）。实测 home 落盘
  只有 `storages/`、`profiles/web/`、`.anonymous-user-id`、`.credentials.yaml`，**home 根没有 pid/lock 文件**
  ⇒ 同 home 重启不会被模块或 home 布局挡住。**真机 start→stop→start 同 home 未实测**（冻结窗口内未做）。
- **⚠ 一条实测代价（裁决 #2 的副作用）**：`dsh web` 启动会在 home 里**自己生成 `.credentials.yaml`**
  （161 B，内容 = `client-connection/browser-session` 的 `kind: grant` + `secret`，即 cookie 签名密钥）。
  而 `dsh_assets.FORBIDDEN_HOME_ENTRIES = ("settings.yaml", ".credentials.yaml", ".credentials")`
  —— 若 Web 实例 home **就是**该 attempt 的 `dsh-home`，则 `home_problems()` 会把 DS-09 判成"attempt home
  含宿主件"，**下一次复用该 home 的 attempt 会在准入阶段失败**（或需把"dsh 自生成的会话签名 secret"
  与"Host 复制来的宿主凭据"在判据里显式区分 —— 那是判据变更，须单独登记）。
