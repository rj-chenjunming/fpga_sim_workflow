# S8k 证据档（2026-10-29）：执行结果补「人参与反馈次数」

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8K_20261029.md5`。
> Lead 实现与验证同一人 ⇒ **不声称独立复核**。
> 契约：[SPEC-REV-18](../spec/SPEC-REV-18-20261029.md)（新增 `OBS-10`）+ [AGENT_WINDOW_SPEC](../spec/AGENT_WINDOW_SPEC.md) 指针 + [REV-17 §2](../spec/SPEC-REV-17-20261029.md)。

## 0 裁决来源

人 2026-10-29 看过 S8j 的执行结果块后提出：「执行结果能不能补充人参与的反馈次数呢」。
含义 = **该 attempt 的 DSH 会话里人说了几次话**（D3 旁路：人在实例 GUI 里输入）。

## 1 交付内容

| 项 | 落点 | 判据 |
|---|---|---|
| 唯一判据 | `host/agent_backends/dsh_sdk.py`：`parse_session_log_lines` 同一遍解析里统计 `user/message` 与 `agent/inbox/spliced.inserted[]` 中 `source.kind=="user"` 的条目，按 `id`→`rpcId` 去重 | 15 条单测（`tests/test_session_human_messages.py`） |
| 契约只增 | `session-copy.facts` 增 `human_messages`(int) 与 `human_messages_basis`(str\|null)；源不可用 ⇒ `0` 且不给依据 | `tests/test_instance_proxy.py::test_session_copy_returns_session_log_facts`（断言 `1` + `source.kind=user,dedupe=id|rpcId,skipped=0`） |
| 界面 | `#awEmbedFacts` 在「剪枝 …」后追加「人参与 N 次」；缺字段 ⇒ 「未知」；`0` 显示 0 | 浏览器 3 条（`人参与 1 次` / `人参与 0 次` / 缺字段 `未知` 且不出现 0） |

**为什么不合并 loop 侧 steer/pause**：那是 `agent_controls` 的人工指令，已由窗口「指令回执与生效」三列表呈现；
两个口径混成一个数会让"人参与"失去可解释性（REV-18 §5 已登记）。

## 2 验证（`raw/gates.txt` 为命令输出原文）

| 门 | 结果 |
|---|---|
| 本片单测 | `tests/test_session_human_messages.py` **15 passed**；`tests/test_instance_proxy.py -k session_copy` **7 passed** |
| 本片浏览器 | `tests/browser/test_s4_projection_ui.py` **27 passed**（24 + 3 条 S8k） |
| 单测门（主树） | `3 failed, 1884 passed, 1 warning, 148 errors`（3 failed = 既有数据根/归档类；148 errors = 本机无 Chromium） |
| 浏览器门（主树） | `1 failed, 148 passed`（失败项 = **并发切片** `test_gate_panes.py::test_identity_change_resets_scroll_to_top`；该文件单独跑 `8 passed`） |
| 文档门 | `65 passed` |
| 端到端（drill） | 见 `raw/gates.txt` |

> 归因纪律：本机同一工作区另有并发切片在写（闸门双栏独立滚动）。本片改动只碰
> `dsh_sdk.py` / `agent-window.js` / 测试与本片文档；单测门与浏览器门的失败项均已用"单独跑该文件"证明与本片无关。

## 3 真机（0 token，只读；演示看板 `127.0.0.1:8199` → `RUN-DEMO-S8F` / `N6`）

`raw/live-probe.txt`（探针 `loop/.logs/s8j/probe_ui.py`，截图 `loop/.logs/s8j/agent-window-s8j.png`）：

| 判据 | 实测 |
|---|---|
| `session-copy.facts` | `human_messages=1`、`basis=source.kind=user,dedupe=id|rpcId,skipped=0` |
| 界面执行结果行 | `执行结果（session_log_facts）：压缩成功 0 次 · 记录 0 条 · 错误 0 条 · 起止 0→0 · 剪枝 0 次 · 人参与 1 次` |
| 入口 | `http://127.0.0.1:42810/?token=<redacted>`（固定端口 42810 已收回） |
| 内嵌面 | `iframe_count=0`、`object_count=0`；页面错误 `0` |

**演示夹具说明（不入库）**：该 attempt 的 DSH 会话日志（多帧 zstd，人在 GUI 说的那句在 `agent/inbox/spliced` +
`user/message` 各出现一次、同 `id`）被复制进 attempt 目录并在 `agent_instance.json` 写 `session_log`（相对 run_dir）。
`人参与 1 次` 是**真实解析结果**，不是造数。

## 4 不声称

- 不声称这是"人审次数/业务反馈质量"的判据；只数"人说过几次话"。
- 不声称覆盖 loop 侧 steer/pause（另口径，未合并）。
- 不声称 `source.kind` 的取值集合永远只有这些：上游新增来源需单独确认后再纳入（REV-18 §5）。
- 不声称独立复核；未推送。
