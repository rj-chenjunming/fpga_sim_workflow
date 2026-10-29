# S7c 证据档 · DSH Web 实例落账 + 同源反代真机（2026-10-29）

> 状态：**通过（真机）**。Host 能起常驻 DSH Web 实例并把 `(node, attempt, host, port, token)`
> 落账到 `<run_dir>/agent_instance.json`；S4 建好的同源反代对着**真实** DSH Web 跑通：
> 可用性端点 `ready`、页面经反代取回、`/api` RPC **不 403**、cookie 同源投递、token 零回显、
> 实例停后**显式降级**。`iframe` 在真实 Chromium 里**渲染成功**（有截图 + DOM 断言）。
> 执行者：`s7c-proxy`（模块 + 反代/界面 + 真机 HTTP/Playwright 取证）+ Lead（`dsh.py`/`SETTINGS.yaml`
> 接线、编排入口 `host/web_instance_ctl.py`、接线后整链真机复核、门/证据/STATUS/提交）。
> **本片没有独立复核者**（照实说明，不声称独立验证）。
> 入口：[开工提示词 S7](../../agents/开工提示词_S7-暴露面收敛与真机收口.md) §4.3；计划
> [`2026-10-29-s7-exposure-convergence.md`](../../plans/2026-10-29-s7-exposure-convergence.md) §2-B3/§6/§8；
> 契约沿用 [REV-16](../../spec/SPEC-REV-16-20261028.md) §5（R1–R20）/§6/§9-1/§9-2/§9-10、[REV-14](../../spec/SPEC-REV-14-20261028.md) §3-D3/§4-B6。
> 目录只增不改；冻结（444）与 `doc/evidence/DSH_S7C_20261029.md5` 由 Lead 在提交前一次完成。

## 1 结论（逐条对 §4.3-3 验收清单）

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| ① | 可用性端点 `ready` 且 `url` 指向正确 attempt | **通过** | `raw/wired_report.json` `availability`：`state=ready`、`url=/instance/RUN-20261029-103000/N6/1/`、`attempt=1`、`stream=http_only` |
| ② | iframe 加载真实页面 | **通过** | 反代取回 `index.html` **200 / 37512 B**、`<base href="./">` 在、**11 条资源引用 0 条绝对**；真实 Chromium 内 `title='DeepSeek Harness'`、`#root` 39916 字符 DOM、body 可读 168 字符、按钮 14/12 enabled、`elementFromPoint` 8/8 命中自身（无遮罩）、`pageerror 0`；截图 `raw/iframe.png`（1280×860） |
| ③ | `/api` 不 403 | **通过** | 经反代 `POST …/api/session/list` ⇒ **200**（`raw/wired_report.json` `api_post`）；上游侧的合法 envelope 另取到 `200 {"ok":true,"value":{"items":[]}}`（`raw/probe3_report.txt`）。详见 §4 的**照实说明** |
| ④ | cookie 由同源投递 | **通过** | 首跳 `GET …/?token=` ⇒ **303**、`location` 已剥离 token、`Set-Cookie` 的 `Path` 收到实例前缀（`raw/wired_report.json` `first_hop`） |
| ⑤ | token 不出现在日志/响应/错误页 | **通过（含一条真机修掉的 P2）** | `tokens_echoed=[]`、`token_in_dashboard_log=0`；**修复前** uvicorn access log 会记录首跳完整 URL ⇒ 新增日志层脱敏过滤器（§5） |
| ⑥ | 目标缺失/上游挂 ⇒ 显式降级 | **通过** | 实例停后端点 ⇒ `state=unavailable`、`reason=target_missing`、`embed=new_tab_only`、元数据已清（`raw/wired_report.json` `after_stop`） |
| 附 | 会话副本（`session_log` 接线） | **通过** | `/session-copy?attempt=1` ⇒ `available=true`、`kind=session_log_facts`（只给解析事实，不声称原文全文，REV-16 §9-11） |

## 2 上游绝对路径（B3 三方案取证 → 结论）

**决定性事实（真机 `index.html` 原文）**：`<base href="./">` 由**服务端自己注入**，11 条资源引用
**全部相对**（`./assets/…`、`plugins/??…&rev=`、`./manifest.webmanifest`、`./favicon-*.svg`），
**以 `/` 开头的 0 条**；客户端 API/WS 也按 `document.baseURI` 相对解析
（`dsh-api-gateway`：`new URL("/api/remote.mux".slice(1), … document.baseURI)`）。

| 方案 | 结论 |
|---|---|
| (b) 上游 base path 配置 | **不存在**：`--public-url` 只作广告（`dsh-web-app/README.md` 原文："advertises the HTTP(S) root … configures no listener, routing, or cookie scope"） |
| (c) 第二 loopback 反代端口 | **不必要**：前缀剥离后浏览器自己把 `./assets/…` 解析到 `<前缀>/assets/…` |
| (a) HTML 前缀化改写（B3 已授权） | **不需要也不应做**：0 条绝对引用，改写只引入"改上游内容"的风险。**未启用该授权** |

逐字节锁住"反代不改写 HTML"：`test_s7c_real_index_html_forwarded_byte_identical`。
⇒ REV-16 §9-10 **可收口为"已实测：前缀剥离即可"**（STATUS §120 登记，spec 正文本轮不改）。

## 3 交付物

| 文件 | 变更 | 契约 |
|---|---|---|
| `loop/host/agent_backends/dsh_web_instance.py`（新，533 行） | 起/停 `dsh --profile web`；从 stdout 解析**实际** host/port 与 launch token；健康检查（**匿名 `GET /` 必须 401**，不是"进程起来了当就绪"）；原子写元数据（tmp+fsync+`os.replace`，0600）；`stop` 可重入、进程组一起收；token 永不进日志/repr | REV-16 §5.2 #1（§9-1 的写入方）、§5.5 |
| `loop/host/web_instance_ctl.py`（新，Lead） | **编排入口**：给哪个 `(run,node,attempt)` 起、home 落在哪、已有实例怎么替换、何时清落账；CLI `start/stop/status`；**不自启动** | REV-16 §5.2；计划 §6 |
| `loop/services/instance_proxy.py` | 只增：`availability()` 两个分支都下发 `stream="http_only"`；**新增 uvicorn/root 日志的 token 脱敏过滤器**（真机 P2，§5） | REV-16 §6.1；§5.4 token 零回显 |
| `loop/web/{s4-view.js,agent-window.js,index.html}` | 内嵌成功时也如实披露"实时流未接通"（`#awEmbedStream`，文案由服务端字段驱动，前端不判） | REV-16 §9-2；红线 8 |
| `loop/host/agent_backends/dsh.py`（Lead 接线） | `CONFIG_KEYS` 加 `web`；新增 `web_config_from_settings()` 适配（复用 `DshConfig` 的 node/bin/version，不另立第二份解析） | REV-16 §9-6 |
| `loop/SETTINGS.yaml`（Lead 接线） | `dsh.web: {enabled: false, home: "", host: 127.0.0.1, preferred_port: 0, start_timeout_s: 30, stop_grace_s: 5}` | 裁决 B3 |
| 测试 | `test_dsh_web_instance.py`（新 30 例）、`test_instance_proxy.py`（+8 S7c 例 +3 token 脱敏例，S4 原 45 例**零回归**）、`test_web_instance_ctl.py`（新 9 例）、`tests/browser/test_s4_projection_ui.py`（+3） | 各条 TDD |

## 4 接线后的整链真机复核（Lead，`raw/wired_report.json`）

`RUN-20261029-103000 / N6 / 1`（该 attempt 的 session log 真实存在，`session_log` 接线因此可验）：

| 项 | 值 |
|---|---|
| 实例 | `127.0.0.1:<port>`、`port_fallback=false`、`startup_s` 见 json、home = `<attempt>/dsh-web-home` |
| token | 长 43 字符；`tokens_echoed=[]`；`token_in_dashboard_log=0` |
| 首跳 | `303`、`location=/instance/RUN-20261029-103000/N6/1/`（无 token）、`Set-Cookie` Path 含实例前缀 |
| 页面 | `200`、37512 B、`<base href="./">`、绝对引用 `[]`、引用 11 条 |
| `/api` | `POST …/api/session/list` ⇒ **200** |
| 会话副本 | `200`、`available=true`、`kind=session_log_facts` |
| 停后 | `unavailable` / `target_missing` / 元数据已清 |

**照实说明（不美化）**：本次 `POST /api/session/list` 的响应体是 **RPC 层 `gateway/bad-request`**
（我发的 envelope 不完整），状态码 200 说明请求**已穿过 Origin/`sec-fetch-site` 围栏到达上游 RPC 网关**
（这正是"不 403"的判据）。`s7c-proxy` 另用**合法 envelope** 在同一链上取到
`200 {"ok":true,"value":{"items":[]}}`（`raw/probe3_report.txt`）。两者合起来才完整。

## 5 真机修掉的 P2：uvicorn access log 会记下首跳 `?token=`

**发现**：接线后整链复核时，`token_in_dashboard_log` 断言首次为**红**——uvicorn 的 access log
把 `GET /instance/<run>/<node>/<n>/?token=<43 chars>` 的完整 request line 打进日志。
REV-16 §5.4 要求 token **永不出现在本服务日志** ⇒ 属真机缺陷（P2），不是"浏览器自己也会看到所以算了"。

**修复**（`services/instance_proxy.py`，import 即生效，与既有 httpx 压级同一纪律）：
`TokenRedactFilter` 挂在 `uvicorn.access`/`uvicorn.error`/`uvicorn`/root 上，把
`token=<值>` 渲染成 `token=<redacted>`（保留参数名便于排障）。**只改日志文本**，不改请求/响应/元数据
（token 仍只进受管元数据）。幂等（重复安装不叠加）。用例：`test_s7c_token_*` 三条。
修复后整链复核 `token_in_dashboard_log=0`。

## 6 界面与降级（改了界面 ⇒ 浏览器门）

- `availability` 响应新增 `"stream": "http_only"`（可用/不可用两分支形状一致）：这是"反代只透传 HTTP"
  的**能力事实**，不是健康判据；前端只渲染服务端字段（不自己判）。
- 内嵌成功时 `#awEmbedStream` 如实写"实时流未接通"；`WebSocket` 实测需要
  （`WS /api/remote.mux`，非升级 GET 上游 404）⇒ 反代保持 **405**，界面**不静默半死**。
- 真机截图（`raw/iframe.png`）里 DSH 自己在左下角显示 `Reconnecting...`；console 原文
  `WebSocket connection to 'ws://…/api/remote.mux' failed: … Unexpected response code: 405`（×13）
  + `connection lost, retry #1..#5` + `generation is still not ready after 3000ms`。
  ⇒ **判定：不是白屏半死，是"只缺实时流"**（页面可见可点，`elementFromPoint` 8/8 无遮罩）。

## 7 未定位项与未做项（照实登记）

1. **9 条 `500` 的 URL 未定位**（`s7c-proxy` 的 Playwright 采集只 dump 了 assets/plugins 子集与
   `requestfailed`，未落全量 `(url,status)`）。候选：探针夹具导致**看板自身** `/api/…` 500
   （导航到看板页时引入），或 DSH 某端点真 500。**未排除**，登记为下次补测项。
2. **不自启动**：`SETTINGS.dsh.web.enabled=false`（仓内默认）。要起实例必须显式调用
   `python -m host.web_instance_ctl start --run-dir <run> --node N6 --attempt 1 --enable`
   （或未来编排钩子）。⇒ "改动默认运行行为"**未发生**。
3. **D3「人在 GUI 里看到并在说话」未落地**：Web 实例 home = `<attempt>/dsh-web-home`，
   **不与该 attempt 的 `dsh-home` 共用**。原因（实测）：`dsh --profile web` 会在自己的 home 里自生成
   `.credentials.yaml`（cookie 签名 secret），而 `dsh_assets.FORBIDDEN_HOME_ENTRIES` 把它判成
   "attempt home 含宿主件" ⇒ 若共用，**下一次复用该 home 的 attempt 会在 DS-09 准入阶段失败**。
   改成并列目录即可，**不改 DS-09 判据**（判据变更要单独变更 + 留证）。⇒ 会话共享登记未决（计划 §8-9）。
4. **WebSocket/SSE 升级仍未支持**（405，REV-16 §9-2 不变）。
5. **Web 实例未套 bwrap**：它要读安装树与自己的 home，env 无凭据、不调模型、不 bind 通配地址；
   登记为未做项（若要与 attempt 一致需额外 bind 清单）。
6. **未声称**：不声称"人在 GUI 对正在跑的会话说话"；不把 Web 实例当执行通道；不因内嵌成功改默认后端。

## 8 复现与索引

- 接线后整链复核（Lead）：`raw/probe_s7c_wired.py` → `raw/wired_report.json`
  （命令：`LOOP_WORKSPACE=<repo>/loop/.logs/s7a/ws .venv/bin/python .logs/s7c/probe_s7c_wired.py`）。
- 上游取证 + Playwright（`s7c-proxy`）：`raw/probe3_report.txt`、`raw/probe3_iframe.py`、
  `raw/iframe.png`、`raw/proxy_top.png`、`raw/probe2_report.txt`、`raw/EVIDENCE.md`。
- 响应头原文（`curl -D -`）：`raw/h_*.txt`；body 片段：`raw/b_*.txt`。
- 门日志：`raw/s7c-gate{1..5}-*.log`；RED→GREEN：[`red-green.md`](red-green.md)。
- 一次性脚本与实例 home（gitignored）：`loop/.logs/s7c/`。
