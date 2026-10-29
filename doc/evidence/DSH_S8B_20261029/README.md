# S8b 证据档（2026-10-29）：D3 会话共享 + 随 attempt 自动起实例（0 token）

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8B_20261029.md5`。
> 探针脚本按纪律**不入库**（`loop/.logs/s8b/`，gitignored）；本档留**参数、命令与结果**，可照 §1 重放。
> 本轮修复由 `s8b-impl` 完成；Lead 复核 DS-09 判据（`doc/STATUS.md` §125.2）与最终 diff。**不声称独立复核**。

## 0 结论（一句话）

**D3 的机制达成、产品（内嵌）路径被 WebSocket 405 挡住** —— 这是两个不同的事实，分别对应下面两行。

| 路径 | 判定 | 证据 |
|---|---|---|
| **直连实例**（不经反代） | **`achieved`** | `raw/dom_session_list.txt`：侧栏自动出现 `Workspaces → work → 「只回复 OK」`、`Choose workspace` = False；DOM 断言**可见会话行自身含 `session_id`**（`{"found": true, "hops": 1, "cls": "YDXeBa_sessionRow"}`）；`raw/direct_instance.png`、`raw/direct_session_row.png` |
| **同源反代 iframe**（产品路径） | **`blocked_by_missing_live_channel`** | `remote.mux` **WebSocket 握手 405**（`raw/probe_d3_sessions_report.txt` §3 console 原文两条）⇒ 前端 live channel 起不来 ⇒ `No sessions yet` / `Reconnecting…`；`/instance/**` 的 ≥400 响应 **0 条**；`raw/iframe.png`、`raw/proxy_top.png` |

三条机制判据（`raw/probe_d3_facts.json` / `probe_d3_sessions_report.txt` §4）：

1. **素材正确性**：会话 projcache `identity.cwd` == 本 attempt 的 `layout.work`（**cwd 只认 projcache，不能从会话目录名反解** ——
   目录名把 `/` 映射成 `-` 不可逆，实现者就此做过一次自我更正）；
2. **归属**：实例 `home == <attempt>/dsh-home`、实例进程 `cwd == <attempt>/work`（`raw` 报告判据 2 全 True）；
3. **DS-09**：`problems = []`，`.credentials.yaml` 判 `source=dsh_generated`（键集合符合实测登记）；自生成件 161 B、**不含**宿主凭据值。

**降级路径（真机）**：真 spawn + 把 `start_timeout_s` 压到 0.5 s ⇒ 真 `start_timeout`；`prepare_attempt`（`mode=real`）**5.60 s 正常返回**、
记录 `web={"state":"unavailable","reason":"start_timeout","embed":"new_tab_only"}`、**未写** `agent_instance.json`、无残留 `--profile web` 进程。

## 1 命令（原样可重放）

```bash
cd loop
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home-s8b TMPDIR=<repo>/.chrome-tmp-s8b \
  .venv/bin/python .logs/s8b/probe_d3_sessions.py
```

探针**全程不进入 execute、不注入 api_key**；0 token 佐证 = attempt 内 boot 失败原文
`dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"; …`
（请求组装期即失败 ⇒ 模型从未被调用）。

## 2 raw 清单

| 文件 | 内容 |
|---|---|
| `raw/probe_d3_sessions_report.txt` | 主报告：判据 1/2/3、两路径 DOM 断言、console/网络摘录、D3 三选一判定 |
| `raw/probe_d3_facts.json` | 结构化事实（session_id、cwd、home/cwd/DS-09、DOM 命中、耗时） |
| `raw/dom_session_list.txt` | 顶层反代 / iframe / 直连实例三份 `body.innerText` 原文 |
| `raw/iframe.png` / `raw/proxy_top.png` | 经反代的 iframe 与顶层画面（`No sessions yet`） |
| `raw/direct_instance.png` / `raw/direct_session_row.png` | 直连实例：侧栏出现该 attempt 的 workspace 与会话行 |

## 3 不声称

- **不声称 D3 产品目标已交付**（内嵌路径被 `remote.mux` WS 405 挡住，REV-16 §9-2 本轮不做）。
- 不声称挡得住"home 内伪造自生成形态"（`bwrap` 与凭据只经 env 注入仍是隔离主体）。
- 不声称多节点实例不累积（`_REGISTRY` 按 `(run,node)` 建键；`stop_all()` 可收，已写进 docstring）。
- 不声称独立复核（实现者自测）。
