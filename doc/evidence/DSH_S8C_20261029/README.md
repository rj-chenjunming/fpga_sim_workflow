# S8c 证据档（2026-10-29）：identity 冷读 + 9 条 `500` 定位 + SSE 截断定位

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8C_20261029.md5`。
> 探针脚本按纪律**不入库**（`loop/.logs/s8/`，gitignored）；本档只留**参数、命令与结果**，可照 §2/§3 重放。
> 本轮修复由 Lead（S8e，反代侧）与 S8c 实现者完成；**不声称独立复核**。

## 0 归属

| 项 | 结果 | 落点 |
|---|---|---|
| REV-16 §9-12 角色卡 `identity` 冷读 | **已收口**（S8c） | `loop/services/agent_view.py` + `loop/tests/test_agent_view_identity_cold_read.py`（13 条） |
| 9 条 `500` 根因 | **非产品缺陷**：S7c 探针夹具 `FakeManager` 缺 `list_runs` | 本档 §2；S7C 证据档加更正件 |
| SSE `ERR_INCOMPLETE_CHUNKED_ENCODING` | **产品 P2**：反代把 15 s 读超时套到事件流上 | 本档 §3；修复在 `6db2c93`（S8e） |

## 1 命令（原样可重放）

```bash
cd loop
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers \
HOME=<repo>/.chrome-home-s8c TMPDIR=<repo>/.chrome-tmp-s8c \
LOOP_WORKSPACE=<repo>/.dev-ws-s8c LOOP_LLM_MODE=standin \
.venv/bin/python .logs/s8/probe_500s.py --mode both      # §2 全量 (url,status) dump
.venv/bin/python .logs/s8/probe_sse.py                   # §3 SSE A/B
```

采集口径：Playwright `page.on("response")` 全量落 `(phase, frame, method, url, status, resource_type)`；
`frame` 由 `request.frame` 判定（`main` = 看板页、`iframe` = 看板里嵌入的 DSH 页面）；
`phase ∈ {A_top_proxied, B_board, B_iframe}`。两种模式用**同一个**真 DSH Web 实例，唯一差别是看板进程：
`fake` = S7c 的 `FakeManager`（同形夹具），`real` = `services.api:app` + 真 `RunManager`。

## 2 9 条 `500` 的定位（结论：探针夹具缺陷，不是产品缺陷）

`raw/probe_500s_report.txt` / `raw/probe_500s_summary.json` 原文：

| 模式 | 响应总数 | `500` 分桶（看板 / iframe / 其它） | 状态分布 |
|---|---|---|---|
| `fake` | 78 | **15 / 0 / 0** | `{303: 1, 200: 62, 500: 15}` |
| `real` | 78 | **0 / 0 / 0** | `{303: 1, 200: 77}` |

15 条 `500` 全部是**看板主帧**的 `GET /api/runs`，根因原文（`board_fake.log`）：
`services/api.py:266 list_runs → AttributeError: 'FakeManager' object has no attribute 'list_runs'`。
S7c 的 `probe2_app.py::FakeManager` 只给了 `docs`/`_progress`；看板每 1.5 s 轮询一次
⇒ 每次一条 `500`。**S7c 记 9 条只是轮询窗口更短**（本次 15 条，同根因）。
真看板（真 `RunManager`）下 `/api/runs` 逐条 `200`，**iframe 内上游端点 0 条 `500`**。

## 3 SSE 截断的 A/B（结论：反代读超时，不是上游关流）

同一 cookie、同一路径 `/plugins/events`、客户端读超时统一 35 s（`raw/probe_sse_report.txt`）：

| 项 | A 经反代 | B 直连上游 |
|---|---|---|
| status / content-type | 200 / `text/event-stream` | 200 / `text/event-stream` |
| 首块 | 0.01 s | 0.00 s |
| 字节 / 块 | 30121 B / 2 块 | 30121 B / 2 块（一致） |
| 结束时刻 | **15.02 s** | **35.04 s**（客户端读超时） |
| 结束方式 | `RemoteProtocolError: … incomplete chunked read` | `ReadTimeout`（上游流仍开着） |

根因：`READ_TIMEOUT_S = 15.0` 被装成整条 `httpx.Timeout`；SSE 空闲 ≥15 s ⇒ `aiter_bytes()` 抛
`ReadTimeout`；响应头已发出 ⇒ 无法改状态码 ⇒ 断连、缺终止 chunk ⇒ 浏览器 `ERR_INCOMPLETE_CHUNKED_ENCODING`。
修复（`6db2c93`）：`Accept: text/event-stream` 的请求 `read=None`（连接超时 1 s 仍生效），
响应头已发出后的读失败只允许干净结束 + 记日志。**修复后经反代 `/plugins/events` = 200 `text/event-stream`**
（S8B 证据档 §3 同轮实测）；`remote.mux` **WebSocket 仍 405**（REV-16 §9-2 未决，本轮不做）。

## 4 不声称

- 不声称 `500` 那 9 条在"产品里也存在"：真看板实测零 `500`；S7c 的登记因此更正。
- 不声称 SSE 修复让界面"实时流可用"：`remote.mux` WebSocket 仍 405。
- 不声称独立复核（实现者自测）。
