# S8l 证据档（2026-10-29）：会话日志发现 —— 元数据未声明 `session_log` 时按 attempt 的 dsh-home 解析

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8L_20261029.md5`。
> Lead 实现与验证同一人 ⇒ **不声称独立复核**。
> 契约：[SPEC-REV-19](../spec/SPEC-REV-19-20261029.md)（新增 `OBS-11`）+ [AGENT_WINDOW_SPEC](../spec/AGENT_WINDOW_SPEC.md) 指针。

## 0 反馈与根因

人 2026-10-29 在 S8k 上线后说：「刷新了，咋没涨？」

真机排查结论：**不是刷新逻辑的问题**，而是 `agent_instance.json` **从来没有** `session_log` 字段
（写入方 S5 未落账）⇒ `session-copy` 恒 `session_log_missing` ⇒ 真实 attempt 的执行结果恒「不可用」；
S8k 的演示为了出数，挂的是**一份快照副本**，人在实例里新说的话不会进那份副本（所以数字不动）。

实测对照（`raw/live-api.txt` 之前的排查）：

```
$ 各会话活文件直读（dsh_sdk.read_session_log）
session-1b43037d… human=3      ← 人真实说了 3 次
session-a2d2faac… human=1
$ agent_instance.json["session_log"] → agent_workspaces/N6/attempt-000001/session-log.zstd（快照副本，恒 1）
```

## 1 交付内容

| 项 | 落点 | 判据 |
|---|---|---|
| cwd 编码唯一实现 | `dsh_sdk.session_dir_name`（`/<a>/<b>` → `--a-b--`） | 单测字面断言 + 演示真目录名逐字相等 |
| 会话日志发现 | `dsh_sdk.find_latest_session_log(home, work=…)`：只认该 attempt 的 cwd 目录；同目录取 mtime 最新、并列取会话名最大；符号链接/非普通文件跳过 | 8 条单测（`tests/test_session_log_discovery.py`） |
| 兜底来源 | `instance_proxy._discover_session_log`（路径取 `dsh_assets.AttemptLayout`，不另拼）+ `session_copy` 元数据缺失时用它；结果仍须在 run_dir 内 | proxy 用例：元数据缺 + 活会话日志在盘 ⇒ `available=True`、`session_log_source="newest_mtime"`、`human_messages=1` |
| 字段只增 | 可用响应增 `session_log_source`（`"metadata"` / `"newest_mtime"`）；**不可用响应保持六键不变** | 元数据用例断言 `"metadata"`；不可用用例既有断言未改 |

## 2 验证（`raw/gates.txt` 为命令输出原文）

| 门 | 结果 |
|---|---|
| 本片单测 | `tests/test_session_log_discovery.py` **8 passed**；`tests/test_instance_proxy.py -k session` **8 passed** |
| 单测门（主树） | `3 failed, 1894 passed, 1 warning, 148 errors in 459.01s` |
| 浏览器门（主树） | `1 failed, 148 passed in 163.14s` |
| 文档门 | `65 passed` |
| 端到端（drill） | phase `1/2/3/4/4b/5` 全 `rc=0` → `=> ALL PASS` |

**归因**：单测 `3 failed` = 环境/数据根（`guard rc=3` 旧格式互斥量 + 归档夹具缺件），与本片无关（输出原文见 `raw/gates.txt`）；
浏览器那 1 failed = `tests/browser/test_run_sessions.py::test_refresh_failure_does_not_rebuild_gate_form_or_lose_draft`，
**该用例单独跑 `1 passed`、整文件 `26 passed`**（全量运行时的抖动，且属并发切片改过的闸门表单区域）。

## 3 真机（0 token，只读；看板 `127.0.0.1:8199` → `RUN-DEMO-S8F` / `N6`）

`raw/live-api.txt`（端点原文，token 无关）+ `raw/live-ui.txt`（探针 DOM + 截图 `loop/.logs/s8j/agent-window-s8j.png`）：

| 判据 | 实测 |
|---|---|
| 来源 | `session_log_source = "newest_mtime"`（元数据无 `session_log`） |
| 人参与 | `facts.human_messages = 3`、`basis=source.kind=user,dedupe=id|rpcId,skipped=0` |
| 界面 | `执行结果（session_log_facts）：压缩成功 0 次 · 记录 0 条 · 错误 0 条 · 起止 0→0 · 剪枝 0 次 · 人参与 3 次` |
| 端口 | 直连实例 `127.0.0.1:42810`（固定端口） |
| 页面错误 | `0` |

⇒ 刷新/再次读取会重新解码**活**会话日志：人在实例里再说一句，`人参与` 就会 +1（不再依赖快照副本）。

## 4 不声称

- 不声称"最新会话"就是 agent 主会话：同一 cwd 多会话时取 mtime 最新（REV-19 §5 已登记未决）。
- 不声称 S5 的 `session_log` 落账已完成：落账后仍优先元数据，本解析器只作兜底。
- 不声称独立复核；不声称浏览器门"零失败"（唯一失败项已用单跑证明与本片无关）；未推送。
