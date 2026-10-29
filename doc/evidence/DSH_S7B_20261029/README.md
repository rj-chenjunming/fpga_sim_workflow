# S7b 证据档 · tool-allowlist 暴露面收敛（2026-10-29）

> 状态：**通过**。真机把发给模型的工具面从 **26 项全量 harness** 收到 **7 项显式允清单**；
> 清单外调用**显式 deny**（带可判 code + 可读原因），`submit_result` 在收窄后**仍可用**
> （该 attempt 的提交被接受、`n6_apply=applied`）。
> 执行者：`s7b-allowlist`（实现 + 离线/真机 boot 取证）+ Lead（`dsh.py`/`SETTINGS.yaml` 接线、真机带模型复核、收口）。
> **本片没有独立复核者**（照实说明，不声称独立验证）。
> 入口：[开工提示词 S7](../../agents/开工提示词_S7-暴露面收敛与真机收口.md) §4.2；计划
> [`2026-10-29-s7-exposure-convergence.md`](../../plans/2026-10-29-s7-exposure-convergence.md) §2-B2/§5/§8；
> 契约沿用 [REV-14](../../spec/SPEC-REV-14-20261028.md) §3 D4/§4 B2、[SPEC-08](../../spec/DSH_AGENT_RUNTIME_SPEC.md) §5/§10 D04/§12。
> 目录只增不改；冻结（444）与 `doc/evidence/DSH_S7B_20261029.md5` 由 Lead 在提交前一次完成。

## 1 结论

| 项 | 结论 |
|---|---|
| 工具面收敛 | **通过（真机）**：引擎发给模型的 `request/header.data.header.tools` = **7 项** |
| 越权调用 | **通过（真机）**：`job_list` 实测被 `tools/pre-execute` deny，`code=TOOL_NOT_ALLOWLISTED` + 可读原因，工具体**未执行** |
| `submit_result` 仍可用 | **通过（真机 + 旁路）**：真机 attempt 内提交被接受（23 次 `tool/result` 全 `ok`、0 `isError`）；旁路 `tools.execute('submit_result')` 返回 `{"accepted":true,"problems":[]}` 且**不写会话日志**（不进提交记账） |
| 显式开关 / 可回退 | **通过**：`tool_allowlist.enabled=false` ⇒ 插件不挂、不渲染 env、**不进运行时指纹** = 与 S6 逐字相同 |

**不声称**：不声称隔离（白名单是"准入 + 显式拒绝"，不代替效果隔离，REV-13 §5.4 / REV-14 A8）；不声称
`bash` 的效果被约束（`bash` 是**已接受暴露面**，见 §5）；不声称全局注册表收敛（引擎明确拒绝对全局
`tools.restrict`，只能按 agent 作用域收窄）。

## 2 交付物

| 文件 | 变更 | 契约 |
|---|---|---|
| `loop/host/agent_backends/dsh_allowlist.py`（新，399 行） | **Host 唯一判据，纯函数零 I/O**：`DEFAULT_ALLOWED`/`ACCEPTED_EXPOSURE`/`DECISION_REJECTED`、`policy_from_settings`、`render_env`、`policy_fingerprint`、`verify_echo`；常量 `PLUGIN_ID`/`PLUGIN_FILE`/`REPORT_KEY`/`DENY_CODE`/`CONFIG_ENV`/`STATE_SERVICE` | 裁决 B2；REV-14 D4；红线 8 |
| `loop/host/agent_backends/dsh_plugin/tool_allowlist.mjs`（新，275 行） | 判据执行方：`tools/pre-execute` 返回 `{kind:'deny',reason,info{name,code,reason}}`；`agent/created` → `agent.ctx.tools.restrict({allow})` 收窄可见面；`ctx.provide('s7ToolAllowlist', …)` 发布生效状态 | REV-14 D4 / SPEC-08 §5 |
| `.../dsh_plugin/selfcheck.mjs` | 回显 `allowlist`（插件名/开关/清单/有效面/被拒面/unknownAllowed/configError/enforceVisibility/agentScope）+ 驱动**两份取证**（`probe` 必被拒 / `allowedProbe` 必不被白名单拒）；回显纳入"就绪" | DS-08 同一纪律（插件加载失败只 warning ⇒ 必须回显） |
| `loop/host/agent_backends/dsh_selfcheck.py` | 新增 `allowlist_policy=None` 参数：非空时 `problems += AL.verify_echo(...)`；**不传时行为与 S6 逐字相同** | DS-08 |
| `loop/host/agent_backends/dsh.py`（Lead 接线） | `CONFIG_KEYS` 加 `tool_allowlist`；`DshConfig.tool_allowlist` 默认 `DISABLED_POLICY`；`_plugins()` 顺序 `SUBMIT → ALLOWLIST(启用时) → SELFCHECK`；`env_extra` 展开 `**AL.render_env(...)`（关掉返回 `{}`）；`static_selfcheck` 并入 allowlist 插件（源码缺失 = 不起进程就失败）；`runtime_fingerprint` **只在 enabled 时**加键（A2）；`on_start` 传策略 + `allowlist_record()` 投影进 attempt 记录 | 裁决 B2；A2；DS-08 |
| `loop/SETTINGS.yaml`（Lead 接线） | `dsh.tool_allowlist: {enabled: true, accept_bash: true, enforce_visibility: true}` | 裁决 B2 |
| `loop/tests/test_dsh_tool_allowlist.py`（新，61 例） | Host 判据 37 + 真内核离线派发 12 + 真 dsh 3 + 自检接线 3 + 契约常量漂移 1 + 配置矩阵 | 各条 TDD |

## 3 真机证据（本片关键：**请求体层面**，不是推断）

### 3.1 带模型的真实 attempt（`RUN-20261029-103000`，production wiring）

| 项 | 值 |
|---|---|
| exit / wall / usage | `completed` / **164.266 s** / input 168 · output 550 · cacheRead 83968 · **total 84686** |
| 提交门 | `validation.ok=True`、`submit accepted`、`execution_state=stopped` |
| **发给模型的工具清单** | **7 项**：`bash, edit, glob, grep, read, submit_result, write`（`raw/n6_request_tools.json`，来源 = session log `request/header`，附 session log md5） |
| 模型实际调用 | `bash`×13、`read`×9、`submit_result`×1；`tool/result` 共 23 条，**`isError` 0 条**（`raw/n6_tool_calls.json`） |
| 自检回显 | `allowlist.allowed` = 7；`effective` = 7；`agentScope.names` = 7；`denied` **19 项**；`unknownAllowed` = `[]`；`toolNames`（**全局**注册表）= 26（`raw/n6_selfcheck_allowlist.json`） |
| `n6_apply` | **`applied`**、`candidate_import.ok=True` ⇒ `submit_result` 在收窄后**真的可用**（不是"理论上"） |

### 3.2 无模型预算的 boot 取证（`s7b-allowlist` 产出，0 token）

| 文件 | 事实 |
|---|---|
| `raw/boot2_echo.json` | `enforce_visibility=true`：`toolNames` 26 项逐项 + `allowlist` 段逐字（effective 7 / denied 19 / probe `TOOL_NOT_ALLOWLISTED` / allowedProbe `INVALID_ARGS`） |
| `raw/boot3_echo.json` | `enforce_visibility=false`（回退档）：`agentScope=null`、deny 取证照旧成立 |
| `raw/boot2_request_tools.json` / `raw/boot3_request_tools.json` | **请求体工具清单 7 项 vs 26 项**——回退档的真实代价证据 |
| `raw/submit_result_dispatch.json` | 旁路 `tools.execute('submit_result')` ⇒ `{"accepted":true,"problems":[]}`；该 boot 的 session log 事件类型普查**无 `tool/result`** ⇒ 旁路派发不写会话日志、不进提交记账 |
| `raw/README.txt` | 生成命令、`DSH_HOME`、实际 env 键（含 `DSH_TOOL_ALLOWLIST` 两种取值）、**为什么不吃模型预算**（`dsh: MISSING_CREDENTIAL` 发生在 boot/插件/agent 创建/请求组装**之后**）、代码 md5、复现步骤 |

> 说明：`boot2/boot3` 两份快照由 `s7b-allowlist` 在其实现上取得；**生产接线后的权威证据是 §3.1**
> （`n6_*` 三件）。两份快照对应实现的 md5 与最终代码一致（`dsh_allowlist.py b3be6466…`、
> `tool_allowlist.mjs f6586087…`、`selfcheck.mjs ac9c1a53…`、`dsh_selfcheck.py 5179dc4f…`）。

### 3.3 接线取证

`raw/dsh_py_wiring.diff`（175 行）`git apply --check` exit 0；应用后 `dsh.py` md5 =
`6530df1e49f481da4b813b0c39872542`，与 `s7b-allowlist` 的 `dsh.py.wired` **逐字节相同**
（接线不是照抄，Lead 逐处复核了判据面/顺序/指纹条件）。

## 4 离线证据（真内核，无 dsh 进程）

`@deepseek-ai/dsh-tools` 真 `ToolRuntime` + 真 `SystemPrompt`：deny 带 code/原因、被拒工具体**零执行**、
允许面照常执行（含同形态 `defineTool` 的 `submit_result`）、坏配置 fail-closed 全拒、
未注册名**保留 `UNKNOWN_TOOL` 语义**（不误报成越权）。

## 5 已接受暴露面与残留风险（照实登记）

1. **`bash` 保留 = 已接受暴露面**（人工裁决 B2）：`bash` 能读 `/proc/self/environ`、能在
   `workspace-write` 内任意读写、宿主有网就能联网。白名单**不收窄** `bash` 的效果；bwrap/双钉未放宽。
2. **两层不是隔离证明**：白名单 = 准入 + 显式拒绝，不代替效果隔离（REV-13 §5.4 / REV-14 A8）。
3. **全局注册表仍是 26 项**：引擎明确拒绝全局 `tools.restrict`（原文见 `dsh-tools/lib/index.js`
   "a context-global restriction would mask every agent"）⇒ 可收敛的是 **agent 作用域面**（实测 = 7 项）。
4. **提示词可能仍提到被收窄的工具**（工具插件无条件注册 prompt section）⇒ 模型可能调用不可见工具拿到 deny
   （丢一个回合，不执行）。`enforce_visibility=true` 已把大部分诱惑消掉。
5. **`enforce_visibility` 的 fail-closed 代价**：收窄失败（拿不到作用域 / `restrict` 抛错 / 清单与全局面无交集）
   ⇒ 回显 `agentScope.error` ⇒ 准入**显式失败**，attempt 被挡（宁可挡也不静默退化）。

## 6 收口门（干净 S7b 树：S7c 改动 `git stash` 后跑；数字从输出复制）

| 门 | 结果 |
|---|---|
| 单测（可写数据根） | 见 STATUS §119.4（同一棵树） |
| kb 自测 + env layer | 同上 |
| 端到端（drill） | 同上 |
| 文档门 | 同上 |
| 浏览器门 | **未跑**：S7b 未改 `loop/web/**` 与界面字段 |

定向：`tests/test_dsh_tool_allowlist.py` **61 passed in 8.76s**；三文件回归 **118 passed in 5.98s**；
八个 dsh 测试文件 **276 passed in 21.68s**。

## 7 纪律核对

- **写权**：`dsh.py`/`SETTINGS.yaml` 只由 Lead 改；`s7b-allowlist` 只碰 5 个文件；`kb/**` 零改动。
- **唯一判据（红线 8）**：允/拒清单、指纹、回显校验只有 `dsh_allowlist` 一处；插件只执行判据；
  界面/记录只消费回显，不重算。
- **A2**：开关 ON/OFF 指纹必然不同（enabled 才加键）；旧记录只读兼容。
- **可回退**：`enabled: false` ⇒ 不挂插件、不渲染 env、不进指纹（与 S6 逐字相同）。
- **真实调用**：本片真机 = 1 次带模型 attempt（额度 2 内；usage 已记账）+ 3 次 boot（0 token）。
- **独立复核**：**无**。

## 8 复现与索引

- 接线：`raw/dsh_py_wiring.diff`（对 `dsh.py` 的 7 处 + 2 helper）。
- 真机（带模型）：`raw/s7a_live_RUN-20261029-103000.json`、`raw/attempts.jsonl`、
  `raw/n6_request_tools.json`、`raw/n6_tool_calls.json`、`raw/n6_selfcheck_allowlist.json`。
- boot 取证（0 token）：`raw/boot{2,3}_echo.json`、`raw/boot{2,3}_request_tools.json`、
  `raw/submit_result_dispatch.json`、`raw/README.txt`。
- 一次性脚本（gitignored）：`loop/.logs/s7b/{boot_probe2,boot_probe3,exp_run}.py`、`loop/.logs/s7b/evidence/`。
