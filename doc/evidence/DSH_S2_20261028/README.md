# DSH S2 实测与证据（2026-10-28）：结构化候选 / 启动自检 / sdk 观测面

> 归档件，**只增不改**；原始产物在本目录 `raw/`，冻结方式见 §7。
> 目的：为 [S2 计划](../../plans/2026-10-28-s2-candidate-selfcheck-observation.md) 与
> [REV-14](../../spec/SPEC-REV-14-20261028.md) 的 B1/B2/B3/B4/B5/B8、DS-08/DS-09/DS-10 提供实测。
> **本目录不是四道门的证据**：四道门命令与数字只在 [STATUS §111](../../STATUS.md) 维护。
> 分层：C1（机制/替身）≠ C2（真实内核+模型）≠ E（内网业务）。本目录有**一次**真实模型调用（C2 部分），
> 其余为 C1。

## 1 结论（三态，照实）

| 项 | 结论 | 决定性证据 |
|---|---|---|
| **B1/B5 结构化候选** | **过（C2 部分）**：真 dsh + 真模型 + bwrap，模型真调用 `submit_result`，Host 拿到 `data={"verdict":"pass","reason":"integration"}`、`task_id` 逐字等于 attempt_key；S1 的 `text`/`note` 占位已删 | `raw/integration-positive.json`（候选原文）+ `loop/tests/test_dsh_candidate.py`（帧形态：
`tool_call{tool:submit_result}`/`tool_result{accepted...}` 的判据由 stub 用例覆盖；真机原始帧未单独归档） |
| **B2 启动自检（工具清单）** | **过（真机正+负例）**：插件不可解析时工具清单 25 项无 `submit_result`，自检**显式拦截**、不出候选；报告须回显本次 attempt 的 `nonce`/`attemptKey`（否则旧快照会被当准入，见 §3-6） | `raw/integration-negative-b2.json`、`raw/negative-dsh-stderr.txt`、`raw/selfcheck-negative-b2.json` |
| **B3 权限档双钉 + 回显** | **过（composition 级）**：`sandboxDefaultMode="read-only"`、`presetEcho` 回显 `defaultPreset="read-only"`、`resolve(read-only)={sandbox:'read-only',approval:'ask'}`；**session 级 preset 未回显**（`apply` 期无 session），不称 DS-09 全满足 | `raw/selfcheck-positive.json`、`raw/patches/00-pins.yml` |
| **DS-09 attempt home 最小化** | **过**：home 顶层只有 `.anonymous-user-id/profiles/sessions/storages`（dsh 自动生成），无 `settings.yaml`/`.credentials.yaml`；带宿主件时用例判失败 | `raw/selfcheck-positive.json`、`tests/test_dsh_selfcheck.py` |
| **DS-10 bwrap 包裹自证** | **过（本机）**：`attest_wrap` 真跑 bwrap 探针——宿主 home 探针不可见、内层 env ⊆ Host 白名单（`build_env`）且关键项指向 attempt home、资产只读/侧信道可写可见；**不声称**挡 `/proc/<pid>/environ`（D1 残余风险）。注："不继承父进程 env"由**显式传 env 给 subprocess** 的结构保证，探针只证明内层 env 集合（§3-7） | `tests/test_dsh_selfcheck.py`、`raw/selfcheck-positive.json` |
| **模型缺凭据的失败语义** | **过**：自检通过后模型调用缺 key ⇒ `model_call_failed=True` + `MISSING_CREDENTIAL` 原文（显式，不伪装"在等人工"） | `raw/integration-nokey-explicit.json` |
| **B4 sdk 观测面** | **部分（C1 + 真握手）**：7 请求方法/4 通知逐字锁定 `0.2.1-rc.2` 类型文件；严格帧（坏行/未知通知/未知方法/版本不符/超时都显式失败）；真 `--profile sdk` 只验 `initialize`+`shutdown`。**真实模型 turn（`session/prompt`→`session/wait`）未验**（无 key 不发） | `raw/sdk-handshake.json` |
| **D2 压缩计数** | **C1**：`compaction/summary` 条数 = 成功次数；用例夹具按 [P7 记录的日志片段](../DSH_PROBE_20261028/p6p7.md)（`count=1 / freed_tokens=3356 / start=2 / end=2 / prune=1 / 1 条显式 error`）**手工构造**（不是原样回放，合成夹具是另一个 count=2 场景）；zstd 缺失 ⇒ `unavailable` 不编数 | `tests/test_dsh_sdk.py` |
| **准入未放开** | **过**：`SETTINGS.yaml` 的 `dsh.enabled=false`；`select()` 对 dsh 仍 `BackendUnavailable`（实现存在 ≠ 准入） | `tests/test_dsh_backend.py` |

## 2 配方（可复现）

| 项 | 值 |
|---|---|
| Node / DSH | node `v24.21.0`；`@deepseek-ai/dsh` `0.2.1-rc.2`（`lib/bin.js` sha256 与 `SETTINGS.yaml` 的钉一致） |
| 包裹 | `bwrap 0.4.0`：`--ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --tmpfs $HOME` + 只 bind attempt 的 cwd/home/资产（只读）/侧信道（可写）+ `--unshare-pid --die-with-parent --new-session`；env 白名单（`env -i` 等价物） |
| 凭据 | 只经进程 env `PUBLIC_API_KEY`（从宿主 `~/.dsh/.credentials.yaml` 的 `refs` 读入，**不入档、不回显**）；`apiKeyEnv` 由 provider overlay 解析 |
| 模型 | `public/origin-deepseek-v4-1-flash`（内网 uniapi overlay；本目录里 baseURL 已脱敏）——**只调用 1 次** |
| attempt 目录 | `<root>/{work,dsh-home,plugin,patches,selfcheck}`；patch 顺序见 `raw/patches/`（`00-pins` → `01-extra-provider` → `10-plugin-submit` → `10-plugin-selfcheck`） |
| 复现 | 单测：`cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_dsh_*.py`（不烧模型）；真机脚本是**一次性**的（不入库，避免把"跑真模型"变成常规动作） |

## 3 会改契约/实现的实测事实（S2 新增）

1. **`--patch` 的 `config` 是整块替换**（不是深合并）：只写 `permission.config.defaultPreset` 会清空 `presets`
   ⇒ `permission: unknown preset "read-only" (known: workspace-write, danger-full-access)`、条目不激活。
   钉死 patch 必须带**完整**档位表（`dsh_assets.PRESET_TABLE`，用例钉住）。
2. **插件复制进 attempt 目录后必须能解析 `@deepseek-ai/dsh-tools`**：否则 `ERR_MODULE_NOT_FOUND` ⇒ 插件
   `did not activate`（**只 warning**）⇒ 工具清单少一项。处置：插件目录放软链到**锁定安装树**的 `node_modules`。
   这一条同时证明 **B2 判据有效**（负例 `raw/integration-negative-b2.json`）。
3. **wire `serverInfo.version` ≠ 包版本**：`initialize` 回 `0.0.1`，包是 `0.2.1-rc.2` ⇒ 双常量分锁（B7 重录纪律）。
4. **`apply` 期拿不到运行时事实**：`toolNames=[]`、`sandboxPolicy`/`permissionPresets` 空 ⇒ 自检只认
   `phase="deferred"` 快照（`setTimeout(0).unref()` 后写），只拿到 `apply` 快照 ⇒ 显式失败。
5. **preset 回显只能到 composition 级**（`catalog()`/`defaultPreset`/`resolve(name)`）；`current(session)` 需 session 对象。
6. **自检报告必须绑定 attempt 身份**（独立复核 P1-1）：`deferred` 快照本身不带身份 ⇒ 复用 attempt root 时
   Host 会用**上一次**的快照放行。处置：每次 attempt 生成随机 `nonce`（`DSH_SELFCHECK_NONCE`）+ `DSH_ATTEMPT_KEY`
   注入 env、报告回显、Host 逐字比对，并在物化时清空 `selfcheck/` 旧文件。`nonce` 只证明"报告来自本次 attempt"，
   不证明内容不可伪造（同 uid 可写自己看到的 env）——威胁模型与 `/proc` 残余风险同层，不额外声称。
7. **`wrap=false` 不是准入**（独立复核 P1-2）：配置里 `wrap:false` 现在启用不了后端（`verify` 拒绝）；
   无包裹只允许代码里显式 `diagnostic_unwrapped=True` 的诊断路径，候选标 `isolation="unwrapped-diagnostic"`。
8. **`attest_wrap` 的 env 判据边界**（独立复核 P2-2）：探针用 `env=build_env(spec)` 起进程，
   "不继承父进程 env"是结构保证而非实测；能实测的是"内层 env ⊆ 白名单"。本目录与计划都按此措辞。

## 4 不声称

- 不声称 B4 的**真实模型 turn** 已验证（本片未发真实 `session/prompt`）；不用 headless 事件冒充 sdk 观测面。
- 不声称挡 `/proc/<dsh-pid>/environ`（D1 残余风险，Q8 已记档）；`attest_wrap` 的 docstring 与用例都不断言它。
- 不声称 DS-09 全满足（session 级 preset 未回显）；不声称 C2/E 业务可用（本次只 1 次真实调用、无内网工程）。
- 不声称自检报告不可伪造（nonce 只是身份 join）；不声称 `attest_wrap` 实测了"父进程 env 不被继承"。
- 不声称大 payload 不截断（截断时 fail-closed，未实测）；不声称子 agent 真实通知/长会话压缩已验。
- 本目录不是四道门证据；四门见 [STATUS §111](../../STATUS.md)。

## 5 raw 清单

| 文件 | 内容 |
|---|---|
| `raw/integration-positive.json` | 真机正例：`data`/`task_id`/`session_id`/`isolation=bwrap`/`selfcheck`/usage |
| `raw/integration-negative-b2.json` | 负例：插件不可解析 ⇒ B2 显式拦截（工具清单 25 项无 `submit_result`） |
| `raw/integration-nokey-explicit.json` | 负例：自检通过但缺凭据 ⇒ `model_call_failed` + `MISSING_CREDENTIAL` |
| `raw/selfcheck-positive.json` | 真机 deferred 自检快照（toolNames 含 `submit_result`、双钉回显） |
| `raw/selfcheck-nokey.json` | 无 key 真机自检快照（自检通过、模型失败） |
| `raw/selfcheck-negative-b2.json` | 负例的诊断快照（`phase=deferred`、25 项、无 `submit_result`） |
| `raw/negative-dsh-stderr.txt` | 负例的 dsh stderr 原文（`ERR_MODULE_NOT_FOUND … did not activate`）与 rc |
| `raw/integration-input.json` | 正例的输入侧身份（`attempt_key`、请求摘要；脚本一次性不入库） |
| `raw/sdk-handshake.json` | 真 `--profile sdk` 的 `initialize` 回执（`serverInfo` 名/版本）+ `shutdown {}` + rc=0 |
| `raw/patches/*.yml` | 本次 attempt 的 patch 应用顺序（钉死 → provider → 提交插件 → 自检插件；baseURL 已脱敏） |

## 6 冻结

- 本目录与 `raw/` 全部 `chmod 444`；md5 记在**目录之外**：`doc/evidence/DSH_S2_20261028.md5`，
  校验方式 `cd doc/evidence/DSH_S2_20261028 && md5sum -c ../DSH_S2_20261028.md5`。
- 后续变更**不得回填**；新证据另开目录并同样冻结。
