# DSH 探针实测（2026-10-28）：P1–P8

> 归档件，**只增不改**。原始产物：本目录 `raw/`；一次性探针工作区（不入库）：`workspaces/.probe-dsh/`。
> 目的：为 [`../../plans/2026-10-28-three-layer-interaction-alignment.md`](../../plans/2026-10-28-three-layer-interaction-alignment.md) §6.1 的 P1–P8 提供实测结论。
> 纪律：本目录冻结；下方数字全部从命令输出复制；未跑四道门、未改 `loop/`/`kb/` 业务代码。

## 0 环境与配方（可复现）

| 项 | 值 |
|---|---|
| Node / DSH | `/home/soft/DSH/node/bin/node`（v24.21.0）+ `…/versions/0.2.1-rc.2/node_modules/@deepseek-ai/dsh/lib/bin.js`（`--version` ⇒ `0.2.1-rc.2`） |
| 宿主 home | `~/.dsh` **只读**（`touch` ⇒ `Read-only file system`）；探针全程零写入 |
| 正在跑的 GUI | `http://127.0.0.1:3083`（**未碰**） |
| 探针 home | `<repo>/workspaces/.probe-dsh/…`（`/tmp` 跨 bash 调用不共享，故不用） |
| provider 切换 | `--patch patch-public.yml`（`llm-pi-ai` + `agent-default-model`），凭据用 `PUBLIC_API_KEY` 环境变量注入（不落档、不回显） |

## 1 结论总表

| 探针 | 三态 | 一句话 |
|---|---|---|
| **P1** home 摆法 + 会话可见 | **过（有条件）** | 共用 home：另一进程建的会话 Web 能列出（`session/list n=1`）+ 能打开（`session/page records=3`）；隔离 home ⇒ `items:[]`/`session/not-found`；并发 3 进程 × 2 会话 + Web 在跑 ⇒ `sessions=10 ok=10 bad=0`、`storages 11 json bad=0`；同会话并发写者被拒 `already owned by an active write handle`；`session/resume` 跨进程、跨 cwd 均可用 |
| **P2** 提交工具 | **过** | `--patch` 的 `insert` 挂 ESM 插件（`defineTool`）可行；模型真调用：`tool_call{tool:"submit_result", input:{…}}` → `tool_result{"accepted":true,"problems":[]}`；handler 在 DSH 子进程执行（`pid=7`）。**坑**：加载失败只出 `dsh: warning: 1 entry did not activate`（不阻断启动） |
| **P3** cwd/写隔离 | **部分** | 只 `--patch sandbox-policy.mode` **不生效**（被 `permission-presets.defaultPreset` 覆盖；宿主 settings 写的是 `danger-full-access`）。钉死后：read-only 两处写 `Read-only file system`/`rc=1`；workspace-write 副本内 `rc=0`、副本外 `rc=1`；`working_directory` 切到副本外**不放宽**写权。**读隔离不存在**：`AGENTS.md`、`~/.dsh/settings.yaml` 均 `rc=0` |
| **P4** 事件/终态 | **过（headless 层）** | 终态显式：`turn_end.reason.kind=completed` / `error`（带 `code`，如 `MISSING_CREDENTIAL`）；事件含 `session`/`turn/step`/`usage`/`tool_call`/`tool_result`；`--session-id` 续跑：同 `sessionId`、`turn` 1→2、`cacheReadTokens 9216`。**限定**：headless 事件流不含 subagent/compaction（见 P6/P7） |
| **P5** 杀进程/子孙清理 | **部分** | SIGTERM：两档均无残留（bwrap `--die-with-parent`）；SIGKILL + `danger-full-access`（无 bwrap）残留 `sleep 45` 孤儿（+3 s/+8 s 仍在）。**坑**：SIGTERM 后 `headless_exit=0`、`final.text=""` 但**无 `turn_end`** ⇒ 退出码/空 final 不能当成功 |
| **P6** 子 agent | **过（限定）** | `--profile sdk` JSON-RPC 实发 `subagent.started`/`subagent.finished`（含 `parentSessionId`/`childSessionId`/`status`/`stopReason`/`lastAssistantMessage`）；配额键实查 `@deepseek-ai/dsh-subagent`(id `subagent`).`config.maxActiveSubagents`（默认 8；`maxDepth` 默认 1）；越额显式拒绝 `subagent limit reached (active child limit: 1); …`（不排队不挂住）。**限定**：headless `--json` 0 条 `subagent.*` |
| **P7** 压缩可见 | **部分** | 可低成本触发（`contextWindow 20000` + `thresholdRatio 0.55` + `headroomTokens 0` + `retainTokens 300` ⇒ `compaction/prune→start→summary(4845 字符)→end`，释放 3356 tokens）；**计数/时点只在 session log**（`compaction/summary` 条数 + `time` + `compactionId`；多帧 zstd 用 `zstd -dc` 一次解全，37229 B / 20 处魔数 `28 B5 2F FD`）；headless 事件 0 条、projcache 无 compaction 行；失败以 `compaction/end.error` 显式落盘 |
| **P8** Web 鉴权/内嵌 | **部分** | 匿名一律 `401`（index/connect//api），**无 `WWW-Authenticate`**、不支持 `Authorization`；唯一入口是启动 stdout 的 `?token=` → `HttpOnly; SameSite=Strict` 签名 cookie（API 走 `/connect?token=` 换 v2 cookie）；页面**无 `X-Frame-Options`/CSP**，但 `/api` 对跨权威 `Origin`、`sec-fetch-site: cross-site`、伪 `Host` 均 `403`；静态资源公开（无 cookie 也 200） |

## 2 会改契约的七条事实（本节是规格输入）

1. **桥的观测面必须是 sdk stdio JSON-RPC，不能是 headless 输出**：subagent/compaction 事件只出现在 SDK 通知与 session log；headless `--json` 里 0 条（P6/P7）。`submit_result` 仍靠 `--patch` 挂薄插件（P2）。
2. **"启动成功 ≠ 可用"**：插件加载失败只出 warning（P2），权限档可能被用户层覆盖（P3）。⇒ Host 必须做启动后自检：工具清单在场 + 实际 preset 回显，缺失即显式失败。
3. **attempt home 必须是最小 home，且不得携带凭据**：读隔离不存在，模型可读任意可读文件（P3）；宿主 settings 里的 `permission.defaultPreset: danger-full-access` 会被继承（P3）。⇒ 复制宿主 home 的做法**禁止**；凭据投放方式仍待裁决（见 §4）。
4. **terminate 契约**：`TERM → 超时 → KILL 进程组`；无 bwrap 档位的 SIGKILL 会留孤儿（P5）。收口只认 `turn_end`/提交工具；退出码 0 与空 `final.text` 都不算成功（P5）。
5. **可见性＝冷读持久化日志**；写句柄跨进程互斥（P1）。⇒ "人对着**正在跑的**会话说话"需要写句柄仲裁；"在**两次 attempt 之间**说话"天然可行，且与"指正只在下一个请求边界生效"（已裁决 #10）一致。
6. **内嵌 GUI 的可行形态受同源约束**：跨站 iframe 因 `SameSite=Strict` 取不到 cookie，`/api` 跨权威 `403`（P8）。⇒ 同源反代最稳；退路是新标签页（已裁决 Q5 接受降级）。
7. **压缩计数与子 agent 记账必须由 Host 落账**（读 session log / 收 SDK 通知），不能依赖现成事件流或 projcache（P6/P7）。

## 3 未验证 / 限制（照实登记）

- 未用真浏览器验 iframe 的 cookie 投递（P8 只到 HTTP/头层）；建议并入浏览器门补测。
- sdk stdio JSON-RPC 的 `session/prompt`/`session/wait` 全链路未由 Python 侧复测（P6 的探针是自写 Node 客户端，只验通知面）。
- 凭据投放方式（env / credentials 服务 / 一次性 token）未定；env 注入对 agent 的 bash 工具可见，是否构成泄漏面需单独验。
- `subagents` 实测越额提示写的是 `active child limit: 1`，与默认 `maxActiveSubagents: 8` 不一致——真实有效限额需运行时读取，不能按默认值写死（P6）。
- P7 用了 4 次 headless 运行（软预算 3，超 1 次，原因：v1/v2 命中压缩失败形态后换配置）；P3/P5 各 4 次（同）。探针 bash 在 bwrap `--unshare-pid` 内，`pgrep` 只覆盖本命名空间 ⇒ 不能声称"全机无残留"。
- 本目录不是四道门的证据：单测/kb/端到端/文档门未在本轮运行。

## 4 需要裁决的两条新问题

| # | 问题 | 选项 |
|---|---|---|
| **Q6** | 凭据怎么投放给 attempt 进程？（读隔离不存在） | ① 只走 env + 接受"agent 能 echo 到"的风险并记档；② 用一次性短期 token（需 DSH 支持 / 自建代理）；③ 凭据留在 Host，模型调用经 Host 代理（DSH 不直接持有上游 key，改动最大） |
| **Q7** | 内嵌 DSH GUI 的形态 | ① 同源反代（看板 `/instance/*` 反代到 DSH web，最稳）；② 新标签页 + 用户顶层 mint cookie（已裁决 Q5 可接受）；③ 看板自建投影，不内嵌 |

## 5 逐探针原始报告

- [`p1p8.md`](p1p8.md)：home 摆法/会话可见性 + Web 鉴权/内嵌（0 次模型调用）
- [`p2p4.md`](p2p4.md)：提交工具 + 事件/终态 + 跨进程 resume（Lead 实测）
- [`p3p5.md`](p3p5.md)：cwd/写隔离 + 杀进程/子孙清理
- [`p6p7.md`](p6p7.md)：子 agent 配额 + 压缩可见性

`raw/` 内为本轮直接引用的一手输出：`p2-submit.ndjson`、`p4-resume.ndjson`、`submit-calls.log`、`p2-cjs-boot.err`、`p6-run.ndjson`、`p6-sdk.stdout`。
