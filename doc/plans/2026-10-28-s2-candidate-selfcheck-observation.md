# S2 实施切片：结构化候选 / 启动自检 / sdk 观测面（2026-10-28）

> 依据：[REV-14](../spec/SPEC-REV-14-20261028.md) §3-D1/D2、§4（B1/B2/B3/B4/B8、DS-08/DS-09/DS-10）、
> [REV-13](../spec/SPEC-REV-13-20261026.md) §5.1/§5.2/§10、[S1 计划](2026-10-28-s1-dsh-process.md)、
> [P0 证据](../evidence/DSH_P0_20261028/README.md)、[P1–P8 证据](../evidence/DSH_PROBE_20261028/README.md)、
> [开工提示词 §3](../agents/开工提示词_S2-DSH执行器与后续切片.md)。
> 状态：**已实施（S2，2026-10-28）**：T1/T2/T3 三片已落地（用例先红后绿），真机集成与证据见
> [`doc/evidence/DSH_S2_20261028/`](../evidence/DSH_S2_20261028/README.md)，四道门数字只在 [STATUS §111](../STATUS.md)。
> 不改 `kb/`、不改闸门、不改节点判据；`dsh` 仍是显式不可用后端
> （`agent_backends.select()` 对 dsh 继续抛 `BackendUnavailable`，"实现存在 ≠ 准入"）。
> 规格缺口不在本文件改契约：遇到缺口登记到本文件 §6“未决”，由 Lead 决定是否另开规格修订。

## 1 范围

| 做 | 不做 |
|---|---|
| T1 结构化候选：`submit_result` 插件进仓 + 收口只认 `turn_end(completed)` **且**提交被接受；去掉 `text` 占位 | 不做业务判据（唯一判据仍是 `workflows/chunks/model_steps._validate`） |
| T3 启动自检：工具清单含 `submit_result`、权限档双钉并回显、`attempt home` 无宿主 settings/凭据、bwrap 包裹自证 | 不声称挡 `/proc/<pid>/environ`（D1 残余风险，Q8 已记档） |
| T2 sdk stdio 观测面：锁定 `0.2.1-rc.2` 的 JSON-RPC 方法与通知类型，收 `subagent.*`；压缩计数从 session log 落账 | 不用 headless `--json` 冒充观测面；S2 内不稳则显式降级并标“未实现” |
| 每片先失败用例（`loop/tests/test_dsh_*.py`），再实现 | 不接真实内网工程、不做 N6 候选导入（S6）、不切换默认后端 |

## 2 唯一 owner 与写权（本片）

| 产物 | 写者（同一时刻一人） |
|---|---|
| `loop/host/agent_backends/dsh_assets.py`（新，attempt 布局与资产物化） | Lead |
| `loop/host/agent_backends/dsh.py`、`dsh_protocol.py`、`dsh_plugin/submit_result.mjs` | 实现 owner A（T1） |
| `loop/host/agent_backends/dsh_selfcheck.py`、`dsh_plugin/selfcheck.mjs`、`dsh_process.py` | 实现 owner B（T3） |
| `loop/host/agent_backends/dsh_sdk.py`（新）+ sdk 观测测试 | 实现 owner C（T2） |
| `loop/SETTINGS.yaml`、`doc/spec/**`、`doc/STATUS.md`、本计划 | Lead |
| 验收复核 | 独立验证者（**不改被测文件**） |

> `dsh_assets.py` 是 `dsh.py` / `dsh_selfcheck.py` 的共同依赖，先由 Lead 落地接口与实现（含用例），
> 之后 A/B 只**读用**它；需要改它时向 Lead 提，不各自改。

## 3 切片、接口与验收

### 3.1 S2-a（T1）结构化候选（B1 + DS-02）

- 插件 `dsh_plugin/submit_result.mjs`（ESM，`inject=['tools']`，`defineTool`）：
  - 参数 `task_id` / `summary` / `payload`；**handler 不校验业务**，只落“已收到”的侧信道记录并回
    `{"accepted": true, "problems": []}`（`accepted` 的含义是"引擎已接收"，不是业务通过）。
  - 业务通过与否只由 Host 的 `_validate` 决定（`model_steps.py` 唯一实现，本片不复制）。
- `dsh_protocol.fold`：从帧流收集 `tool_call{tool:"submit_result"}` 与其 `callId` 对应的 `tool_result`；
  终态、提交、冲突的判定规则写死在协议层（纯函数、可单测）：
  - 恰一条被接受（`status=completed` 且 result 解析出的 `accepted is True`）⇒ 候选；
  - 0 条 ⇒ `NoSubmission`（不得出候选）；
  - 多条不同提交 / `callId` 对不上 / `tool_result` 非 completed / result 非 JSON ⇒ 显式失败。
  - `task_id` 必须等于本次 attempt 的 `attempt_key`（由 `_compose_task` 明确告知模型），不等 ⇒ 身份失败。
- `dsh.py`：`completed` **且**有被接受提交才返回 `{plugin:"dsh", data:<payload>, task_id, summary,
  session_id, usage}`；**删掉 `text` 占位与 `note`**；缺提交 ⇒ `model_call_failed=True` + 明确 error。
- 先失败用例 `tests/test_dsh_candidate.py`（stub CLI 产 NDJSON，不烧模型）：
  ok / 无提交 / 提交被拒 / 两条冲突提交 / task_id 错 / `tool_result` 缺失 / 坏 result JSON / 终态 error 但已提交。

### 3.2 S2-b（T3）启动自检（B2/B3、DS-08/DS-09/DS-10）

- 插件 `dsh_plugin/selfcheck.mjs`：`apply` 时把**运行时事实**写到 `$DSH_SELFCHECK_DIR/selfcheck.json`：
  `{plugin, applied, pid, toolNames:[...], sandboxDefaultMode, permissionPresetEcho, home, patches}`。
  `toolNames` 用 `ctx.tools.schemas()`（注册表可见面）；`sandboxDefaultMode` 用
  `ctx.get('sandboxPolicy').defaultMode`；preset 用 `ctx.get('permissionPresets')` 的公开 API
  （**取不到就写 `{availability:"unknown", reason}`，不得编造**）。
- `dsh_selfcheck.py`：
  - `verify_home(home)`（DS-09）：`attempt home` 不得含**宿主**件 `settings.yaml`/`.credentials.yaml`/`.credentials`；
    违反 ⇒ 显式失败。注意 `profiles/`/`sessions/`/`storages/` 是 **dsh 自己在 attempt home 里生成**的（空 home 也会建），
    不是宿主件 ⇒ 不能按"存在即失败"判（见 §6-9）。
  - `verify_session_facts(layout, expected_mode, expected_preset)`（B2/B3）：读 `selfcheck.json`，
    要求 `submit_result ∈ toolNames`（B2）、`sandboxDefaultMode == expected_mode`、preset 回显与钉死值一致
    （B3）；缺件/超时/不一致 ⇒ 显式失败（不把"进程起来了"当准入）。
  - `attest_wrap(spec)`（DS-10）：用**同一隔离参数**跑一个不调模型的探针（`/usr/bin/env` + 逐路径 `test -e`），
    断言：宿主 home 里的探针文件在包裹内不可读、内层 env ⊆ `dsh_process.build_env` 的白名单
    （"不继承父进程 env"由**传显式 env 给 subprocess** 的结构保证，探针只能证明内层 env 集合；
    不能把这条写成"实测父进程 env 没被继承"——独立复核 P2-2）、关键 env 指向 attempt home；
    **不检查** `/proc` environ（D1 残余风险）。
- `dsh_process.py`：
  - 拆出 `build_wrap_argv(spec, inner)`（探针与 dsh 共用同一隔离参数，避免第二套口径）；
  - `run_attempt(..., on_start=...)`：spawn 后、收帧前等待 `on_start`（自检钩子），钩子抛错 ⇒ `TERM→KILL` 进程组后显式失败；
    **不放宽**现有 `TERM→KILL`、残留检查、坏帧/无终态的失败语义。
- 钉死值（B3）：`sandbox-policy.mode=read-only` + `permission.defaultPreset=read-only` 由 `dsh_assets` 生成的
  `pins.yml` 写进 attempt 目录内（**不复制宿主 settings**），并在自检里回显比对。
- 先失败用例 `tests/test_dsh_selfcheck.py`：工具清单缺 `submit_result` ⇒ 失败；preset 不一致 ⇒ 失败；
  home 带宿主 settings ⇒ 失败；`selfcheck.json` 缺失/超时 ⇒ 失败；`attest_wrap` argv 组成（不执行）；
  真 bwrap 探针（有 `bwrap` 才跑，缺件 `skip` 并标注）。

### 3.3 S2-c（T2）sdk stdio 观测面（B4 + D2）

- 先锁版本与类型映射（**不许编方法名**）：`0.2.1-rc.2` 的
  `@deepseek-ai/dsh-sdk-protocol` 明写 7 个请求方法（`initialize`/`session/prompt`/`session/resume`/
  `session/wait`/`session/working-directory/get|set`/`shutdown`）与 4 个通知
  （`session.event`/`session.status`/`subagent.started`/`subagent.finished`）；本机实测
  `dsh --profile sdk` 走 stdio NDJSON JSON-RPC、`shutdown` 有回执、**响应可乱序**（按 `id` 匹配）。
  映射表以常量写在 `dsh_sdk.py`，换版本必须重录（B7）。
- `dsh_sdk.py`：最小客户端（只做观测面需要的）：
  - 严格帧处理：坏行/未知方法/未知通知/版本不符 ⇒ 显式失败（不忽略坏行）；
  - `initialize` 校验 `serverInfo.name == "deepseek-harness-sdk-runtime"` 且版本等于钉死版本；
  - `session/prompt`（`messageId` 只是入队身份，不是完成）、`session.wait`（完成等待）、`shutdown`；
  - 通知落账：`subagent.started/finished` 计数与明细、`session.status`、`session.event`；
  - 压缩计数（D2）：从 session log 读 `compaction/summary`（`zstd -dc` 多帧）计数与 `time`/`compactionId`；
    zstd 缺失 ⇒ `availability="unavailable"` 显式降级，不编数。
- `tests/test_dsh_sdk.py`：纯解析/帧测试；python stub JSON-RPC 服务端（initialize/prompt/wait/shutdown +
  通知流 + 故意乱序 + 坏帧 + 错误码）作为 C1 证据；真 `--profile sdk` 只做 `initialize`+`shutdown` 握手
  （**不烧模型**，无 key 即不 prompt），缺安装则 `skip`。
- **显式降级线**：若 `session/prompt`→`session.wait` 全链路在本片无法稳定验证（缺模型授权），
  文档与 STATUS 必须写“B4 观测面：C1 已实现（stub + 真握手），真实模型 turn 未验”，**不得**用 headless 事件冒充。

## 4 验证（本片收口）

1. 每片先失败用例 → 实现 → 受影响回归（`test_dsh_process.py`、`test_dsh_backend.py`、`test_agent_backends*`、`test_f06_structure`）。
2. 四道门在 S2 收口时**全部重跑**并把数字写进 `doc/STATUS.md` 新节（从命令输出复制，不手算）：
   单测（可写数据根）/ kb 自测 + env_layer（派生 ENV_ROOT 副本）/ 端到端 drill / 文档门。
3. 浏览器门：本片无 `loop/web/**` 与界面字段改动 ⇒ **不跑**，并在 STATUS 写明理由（AGENTS §4）。
4. 证据：新目录 `doc/evidence/DSH_S2_20261028/`（冻结 444 + 目录外 md5），只增不改。

## 5 完成定义（S2）

- T1/T3/T2 的先失败用例转绿；受影响回归无红（passed/failed/skipped 分别记录）；
- `select()` 准入仍显式（`enabled` + 指纹 + 自检通过），未通过保持 `BackendUnavailable`；
- 证据新增并冻结；STATUS 新节；提交信息可追溯到契约条款（B1/B2/B3/B4、DS-08/09/10）与证据。

## 6 未决（本片遇到的缺口，不静默补实现）

1. `permission-presets.defaultPreset` 的**运行时回显 API**：实测 `apply` 期无 session，`current(session)` 不可用
   ⇒ 只能回显 **composition 级**（`catalog()` / `defaultPreset` / `resolve('read-only')` = `{sandbox:'read-only',approval:'ask'}`）。
   自检把 `scope:"composition", sessionScoped:false` 写进事实并**不声称 DS-09 全满足**；拿到 session 对象后需重测并补 session 级回显。
2. **`--patch` 的 `config` 是整块替换，不是深合并**（实测）：只写 `permission.config.defaultPreset` 会清空 `presets`
   ⇒ `permission` 条目激活失败（原文 `permission: unknown preset "read-only" (known: workspace-write, danger-full-access)`），
   `permissionPresets` 恒为空。钉死 patch 必须带完整档位表（`dsh_assets.PRESET_TABLE`，由用例钉住）。
3. **插件必须能解析 `@deepseek-ai/dsh-tools`**（实测）：插件源码复制进 attempt 目录后，
   Node 向上找不到 `node_modules` ⇒ `ERR_MODULE_NOT_FOUND … Cannot find package '@deepseek-ai/dsh-tools'`
   ⇒ 插件 `did not activate`（只 warning），工具清单 25 项里没有 `submit_result`。
   处置：`dsh_assets.materialize(node_modules=A.node_modules_for(config.bin))` 在插件目录放软链到**锁定安装树的**
   `node_modules`（不复制安装树；包裹内由 `--ro-bind / /` 可见）。换 DSH 安装路径必须重录（B7 同一纪律）。
4. **wire `serverInfo.version` ≠ npm 包版本**（实测）：`initialize` 回 `serverInfo.version = "0.0.1"`，
   而包/协议版本是 `0.2.1-rc.2`（P6 证据一致）。`dsh_sdk.py` 用**双常量**分别锁定
   （`SDK_PROTOCOL_VERSION="0.2.1-rc.2"` + `SERVERINFO_VERSION="0.0.1"`），两者都严格比较；换版本必须整表重录。
5. `submit_result` 的 `payload` 经 headless NDJSON 回传的**完整性**（大 payload 是否截断）未验：
   截断时按坏 JSON/坏提交显式失败（fail-closed），真机大 payload 实测留到 S5（C2）再补。
6. sdk `initialize` 的 `provider` 路由需要适配器注册（本机探针 `initialize` 对未注册 provider 返回 `-32603`）：
   真实 provider 路由的 initialize 通过属 S5（C2）；本片锁协议、真机只验 initialize+shutdown 握手。
7. 压缩事实的来源优先级（D2 复评条件①）：若 sdk `session.event` 能稳定给出 compaction 事件，
   改为"事件流优先、session log 兜底"；本片先实现 session log 落账（真实 P7 日志回放校验过）。
8. **自检报告的身份 join**（独立复核 P1-1）：`apply` 期与 deferred 快照都不带 attempt 身份时，
   复用同一 attempt root 会把**上一次**的快照当本次准入。处置：每次 attempt 生成随机 nonce
   （`DSH_SELFCHECK_NONCE`）与 `DSH_ATTEMPT_KEY` 注入 env，报告必须回显、Host 逐字比对；
   物化时清空 `selfcheck/` 旧文件。`nonce` 只证明"报告来自本次 attempt"，不证明"报告内容不可伪造"
   （同 uid 下进程可写自己看到的 env）——威胁模型与 `/proc` 残余风险同层，不额外声称。
9. **`profiles/` 口径**：计划初稿把 `profiles/` 列为"不得出现在 attempt home"的宿主件，实测 dsh 在**空 home**
   里自动生成 `profiles/`（headless/sdk 模板）与 `storages/`、`sessions/` ⇒ 按原文实现会恒失败。
   现行判据只禁宿主 settings/凭据（`dsh_assets.FORBIDDEN_HOME_ENTRIES`）；`profiles/` 的内容来源
   （是不是 dsh 自带模板 vs 宿主复制）**未逐个比对**，登记为未决。
10. **`wrap=false` 不构成准入**（独立复核 P1-2）：配置里 `wrap:false` 现在**不能**启用后端
    （`DshConfig.verify(wrap_required=True)` 显式拒绝）；无包裹只允许代码里显式
    `DshBackend(config, diagnostic_unwrapped=True)` 的诊断路径，候选标 `isolation="unwrapped-diagnostic"`。
11. **`attest_wrap` 对部署布局的隐含依赖**：遮蔽探针优先用宿主 home 下**已存在**的仓内文件
    （本机 `$HOME` 只读，不能临时造）；仓库不在 `$HOME` 下且 `$HOME` 不可写 ⇒ 无法自证 ⇒ 显式失败
    （fail-closed，但会让 dsh 在该布局下永远不可准入）。需在 S5 的内网布局上复验。

12. 真机集成（本机一次模型调用，见证据档 `DSH_S2_20261028`）已证明"bwrap + 自检 + 提交 + 候选"闭环；
   但**未验**：真实大 payload、长会话压缩、子 agent 真实通知、`session/prompt` 全链路。
   这些是 S5（C2）的取证对象，本片不声称。
