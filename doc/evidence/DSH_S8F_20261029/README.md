# S8f 证据档（2026-10-29）：`direct_url` 直连实例 —— D3 产品路径达成（0 token）

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8F_20261029.md5`。
> 探针脚本 `raw/probe_direct_url.py`（可复放；本次同时保留在 gitignored `loop/.logs/s8f/`）。
> **本轮真机 0 token**：不进入 execute、不注入 api_key（只起 `dsh --profile web` + Playwright）。
> Lead 实现与验证同一人 ⇒ **不声称独立复核**。

## 0 裁决来源

S8b 真机结论是「D3 机制达成、产品内嵌路径被 `remote.mux` WebSocket 405 挡住」（REV-16 §9-2 本轮不做）。
2026-10-29 人裁决选项 **B**：`availability()` 直接下发 `direct_url`（含受管 token），
「在新标签页打开」指向**直连实例**。契约：[REV-16 §6.1](../../spec/SPEC-REV-16-20261028.md) 的 `direct_url` 条（只增）。

## 1 结论（真机，`raw/probe_facts.json`）

| 判据 | 实测 |
|---|---|
| availability 下发 `direct_url` | `has_direct_url=true`；`direct_url_has_token=true` |
| 反代 URL 不带 token（§5.4 不变） | `proxy_url_has_token=false` |
| 打开后浏览器最终地址栏不含 token（dsh 303 剥掉） | `final_url_has_token=false` |
| **会话列表出现** | `session_rows=2`、`session_title_visible=true`（「只回复 OK」） |
| **不再空白** | `session_block_absent=true`（`No sessions yet` 消失） |
| **判定** | **`achieved`** |

`raw/direct_url_page.png`：1280×900 截图，侧栏 `Workspaces → work → 「只回复 OK」`。

## 2 复放

```bash
cd loop
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home-s8f TMPDIR=<repo>/.chrome-tmp-s8f \
  .venv/bin/python .logs/s8f/probe_direct_url.py     # 退出码 0 = achieved
```

夹具：复用 S8b 的 attempt（`loop/.logs/s8b/run/RUN-20261029-S8B`，其会话 **cwd 就是该 attempt 的 `work`**，
由 0-token boot 产生）。探针走**生产同一路径** `web_instance_ctl.ensure` 起实例，
再用**端点同一函数** `instance_proxy.availability` 取 `direct_url`。

## 3 不声称

- **不声称** iframe 内嵌可用：内嵌仍是反代 URL，`remote.mux` 仍 **405**（§9-2 未决）。
- **不声称**远程访问形态可用：`direct_url` 是 `127.0.0.1:<port>`，**只在浏览器与服务同机**时可达。
- **不声称** token 无痕：首次导航的 URL 里会带 token（随后 303 剥掉），且可能进浏览器历史 / dsh 自身访问日志；
  反代的 `TokenRedactFilter` 覆盖不到 dsh 进程自身日志 —— 这是人已裁决接受的风险（REV-16 §6.1 第 6 条）。
- 不声称独立复核。
