# S7 计划 · 暴露面收敛与真机收口（四片，各自收口）

> 日期：2026-10-29。状态：**进行中**。SpecDD ②产物：本文件 + §2 人工裁决记录。
> 入口：[开工提示词 S7](../agents/开工提示词_S7-暴露面收敛与真机收口.md) §4/§5/§6/§9。
> 契约沿用 [REV-13](../spec/SPEC-REV-13-20261026.md) §5/§7.3/§10、[REV-14](../spec/SPEC-REV-14-20261028.md) §3/§4/§6/§7、
> [SPEC-08](../spec/DSH_AGENT_RUNTIME_SPEC.md) §10/§12、[REV-16](../spec/SPEC-REV-16-20261028.md) §5/§6/§9——
> **不新写替代契约**（新行为先改既有 spec 的未决登记，再实现）；缺口登记 §未决与 STATUS。

## 1 开工基线（2026-10-29 实测，命令输出复制）

`HEAD=492d4e0`（= 交接 `3d2a1a6` + S7 提示词提交 + gitignore 提交），`git status --short` 空。

| 门 | 结果 |
|---|---|
| 单测（可写数据根 `<repo>/.dev-ws`） | `3 failed, 1643 passed, 1 warning, 137 errors in 402.75s`；3 failed 全是既有 `@pytest.mark.env_layer`，137 errors 是 `tests/browser/**` 缺 Chromium |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；`3 passed, 24 deselected in 15.09s`；原 ENV_ROOT 零写入 |
| 端到端（drill） | phase 1–5 + 4b 全 `rc=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.79s` |
| 浏览器门（三组 env） | `138 passed in 144.17s` |

与 STATUS §116.4 基线**逐项相符**，零新增失败。

## 2 人工裁决记录（2026-10-29 本窗口，人已拍）

| # | 裁决 | 落地 |
|---|---|---|
| **B1 真实调用授权** | **全部授权**：S7a ≤4 次、S7b ≤2 次、S7c ≤2 次（其中 S7c 不烧 token，纯本地 HTTP） | 逐次记账；单次 >300 s 或 >60k tokens ⇒ 立即停手报人；不重试超额度 |
| **B2 工具白名单** | 允许 `read/list/grep/glob/write/edit/apply_patch` + `submit_result` + selfcheck 通道；**`bash` 保留并单独登记为已接受暴露面**（N6 实测用它做 `ls`/`md5sum`，禁掉显著降成功率）；拒绝 `web_search/web_fetch/subagent*/workflow/send_message/present/job_*` | S7b 插件；越权调用**显式拒绝**（deny + 原因），不静默丢弃；有显式开关可回退 |
| **B3 S7c 上游绝对路径** | 优先 (b) 上游 base path 配置 → (c) 第二 loopback 反代端口；**若 (b)(c) 都不可行，授权 (a) HTML 前缀化改写**作为备选（只在反代层做、逐条白名单、不顺手改脚本逻辑） | 必须**先取证再选**；证据记代价与白名单条目 |
| **B4 其余三项** | ① **不推送**（需另行授权 + 凭据）；② **不做公平对照**（沿用 A4「不跑 Agently 对照组」，结论只写"探索/证据不足"）；③ **E（内网业务验收）记"未验证"**，不伪造环境 | 与 §7 纪律、SPEC-08 §12.2 一致 |

**未放宽**：`default_backend` 仍 `agently`；`select()` 之外不放开任何入口；不 bind `0.0.0.0`；`kb/**` 零改动（除单独变更 + 留证）。

## 3 切片与写权

> 写权纪律：`dsh.py` 与 `SETTINGS.yaml` **只由 Lead 改**（S7b/S7c 都要接线，避免两个 writer）；
> S7b/S7c 各自新增模块与测试文件互不重叠。

| 片 | 内容 | 写权（唯一 writer） | 退出条件 |
|---|---|---|---|
| **S7a** | N6 材料面瘦身 + 提交格式前置 + DS-06 真机 | Lead：`workflows/chunks/model_steps.py`、`workflows/chunks/host_steps.py`、`host/agent_backends/dsh_assets.py`、`loop/prompts/loop_nodes.yaml` | N6 真机 `submit accepted + validation ok`；DS-06 `candidate_import.ok=True` + `status=applied` + `source=candidate_import`；六节点 6/6；证据档 + STATUS + 单独提交 |
| **S7b** | tool-allowlist 薄插件（dispatch 钩子）+ 自检回显 + 显式开关 | `s7b-allowlist`：`host/agent_backends/dsh_plugin/tool_allowlist.mjs`（新）+ `tests/test_dsh_tool_allowlist.py`（新）；**Lead 接线** `dsh.py`/`SETTINGS.yaml` | 真机 selfcheck 回显 `toolNames` = 允清单；被拒工具实际调用一次拿到 deny 原因；`submit_result` 仍可用；证据含前后对比 |
| **S7c** | Host 起常驻 DSH Web 实例 + `agent_instance.json` 落账 + 同源反代真机 | `s7c-proxy`：`services/instance_proxy.py`、`services/api.py`、`host/agent_backends/dsh_web_instance.py`（新）、`loop/web/**`、`tests/` 新增；**Lead 接线** `dsh.py`/`SETTINGS.yaml` | 可用性端点 `ready` 且 `url` 指向正确 attempt；iframe 加载真实页面；`/api` 不 403；cookie 同源投递；token 零回显；缺失/上游挂 ⇒ 显式降级；否则"不可用 + 原因" |
| **S7d** | 低成本清理（各 ≤1 h） | Lead | 事件 `ts` 同源（**共享判据面，单独变更 + 留证**）、角色卡 `identity`、反代 `(node,attempt)` 归属抽函数、前端 `session_*` reason 映射、用例 docstring |

**串行纪律**：片间提交顺序 S7a → S7b → S7c（各自门用 `git stash push -u -- <另一片文件>` 取干净数字，跑完 `pop`）；
共享文件（`dsh.py`/`SETTINGS.yaml`/`services/instance_proxy.py`/`loop/web/**`/`workflows/chunks/**`）同一时刻只有一个 writer。

## 4 S7a 落点与验收（对象：`host_steps.n6_apply` / `model_steps.n6_author` / `dsh_assets` 材料面）

| 项 | 落点 | 验收 |
|---|---|---|
| 材料面瘦身 | `dsh_assets` 的 N6 input 构造 | attempt `input/` 只给 targets 摘要（`excerpts`/`rtl_change`/`api_semantics`/`doc_bitdef`）+ 目标用例源件（既有 `stage_sources`）；**不塞 345 KB `n5_impact.json` 全文**。若需影响面 ⇒ Host 派生摘要件进 input，证据记"派生自哪个源件 + md5" |
| 提交格式前置 | `prompts/loop_nodes.yaml`（模型输入文本）+ `dsh_protocol` 错误信息可读性 | ① prompt 强调 `submit_result.payload` **必须是 JSON 对象**；② Host 侧 `BadSubmission`/`apply_edits` 漂移的错误信息指出**具体字段与期望**；③ **不放宽** `apply_edits` 的"old 在声明行唯一命中"判据 |
| 离线先行 | 真夹具 `tc_bmc_i2c_03` 单目标 | 纯 Host 链路：`n6_author` 输入构造 → 假 out 四键 → `n6_apply` 导入生效；1 次 `--dry-run` 确认 prompt 渲染与材料面 |
| 真机 | 探针（gitignored `loop/.logs/s7a/`） | ≤4 次；1 target；单次 ≤300 s（`assert config.timeout_s == 300` 真的生效）；第 1 次目标 = N6 `submit accepted + validation ok`；成功后 1 次 DS-06 |

**不做**：不改 N6 schema、不跳过 `n6_apply` 校验、不把 Host 结构校验通过当业务正确、不放宽 DS-06 拒绝矩阵、不为凑"六节点全绿"降标准。

## 5 S7b 落点与验收（对象：新 `dsh_plugin/tool_allowlist.mjs` + `dsh.py` 挂载 + 自检回显）

| 项 | 落点 | 验收 |
|---|---|---|
| 插件 | `dsh_plugin/tool_allowlist.mjs`（薄插件，dsh dispatch 钩子） | 允清单放行；清单外**显式 deny + 原因**；`disabled:true` 只作粗粒度兜底不作主方案 |
| 开关 | `SETTINGS.yaml` `dsh.tool_allowlist`（与 `node_backends` 同级） | 关闭 ⇒ 行为回到 S6 现状；开关进运行时指纹（A2）；旧记录只读 |
| 自检 | `dsh_plugin/selfcheck.mjs` / `dsh_selfcheck.py` | 回显 `toolNames` 实际值 + allowlist 生效状态（插件加载失败只 warning ⇒ 必须回显，不得以"进程起来了"当准入） |
| 真机 | 探针（`loop/.logs/s7b/`） | ≤2 次；1 次 selfcheck 回显；被拒工具实际调用一次拿 deny 原因；`submit_result` 仍可用 |

**不做**：不用白名单代替效果隔离（REV-13 §5.4 / A8）；不放宽 bwrap/双钉；不给 `danger-full-access`。

## 6 S7c 落点与验收（对象：`dsh_web_instance.py` 新建 + `services/instance_proxy.py`/`api.py` + `loop/web/**`）

| 项 | 落点 | 验收 |
|---|---|---|
| Host 起实例 | `DSH_HOME=<实例 home> node <dsh bin> --profile web --host 127.0.0.1 --port <preferred\|0> --no-open` | 端口优先固定、占用回落随机；页面/证据显示**实际端口**；stdout 形态见 [p1p8](../evidence/DSH_PROBE_20261028/p1p8.md) |
| 落账 | `<run_dir>/agent_instance.json`（唯一目标源，S4 已实现读取） | `{node, attempt, host, port, token, session_log?, written_at}`；token 只从受管元数据读、**永不回显**；**不**写成"客户端可传目标" |
| 真机清单 | 探针（`loop/.logs/s7c/`） | ① `ready` + `url` 指向正确 attempt；② iframe 加载真实页面；③ `/api` 不 403；④ cookie 同源投递（`?token=` 交换后浏览器携带）；⑤ token 不出现在日志/响应/错误页；⑥ 目标缺失/上游挂 ⇒ 显式降级块 |
| 上游绝对路径 | 先抓 `index.html` 与资源引用 | 三选一并写清代价：(b) 上游 base path 配置（优先）→ (c) 第二 loopback 反代端口 → (a) HTML 前缀化改写（B3 已授权，仅 (b)(c) 均不可行时） |
| WebSocket | 实测 | 需要则登记；不支持就显式 405 + 界面降级（§9-2），不静默半死 |

**不做**：反代不接受客户端目标（仍只读受管元数据）；不 bind `0.0.0.0`；不把 Web 实例当执行通道；不因内嵌成功就改默认后端。

## 7 验证门（每片收口各自跑；AGENTS §4 是权威）

命令照抄开工提示词 §6：单测（可写数据根 `.dev-ws`）→ kb 自测 + env layer → 端到端 drill → 文档门；
**改 `loop/web/**` 或 `services/contracts.py` 界面字段的片（S7c、S7d 若动界面）必须另跑浏览器门**并记 STATUS。

**独占跑门**：跑门时不同时跑其它 pytest；片间取干净数字用 `git stash push -u -- <另一片文件>` → 跑 → `pop`。
每片收口数字从命令输出复制，写 STATUS 新节（§118 起递增）。

## 8 未决（照实登记，不静默补实现）

1. **S7b 前工具面仍全量**：S7a 真机期间 `toolNames` 仍是 26 项全量 harness（含 `web_search`/`web_fetch`/`subagent`）⇒
   S7a 证据**不声称**工具面已收敛；这是"先 S7a 后 S7b"的固有代价，已由裁决 B1 显式接受。
2. **`dsh.py` 单 writer**：S7b/S7c 的接线都由 Lead 做；两片各自新增模块，避免同一文件两个 writer。
3. **`SETTINGS.dsh.web` 常驻实例键**（REV-16 §9-6）：本片若走常驻实例须同时改 `CONFIG_KEYS`；若只走 per-attempt
   实例则登记"常驻源未实现"。
4. **S7d 事件 `ts` 同源**属共享判据面变更（REV-16 §9-8）：必须单独变更 + 留证，不并入 S7a–S7c 的提交。
5. **E（内网业务验收）未验证**（裁决 B4）；**未推送**（裁决 B4）。

## 9 STATUS 节号

§117 是交接节，本窗口起递增：**S7a = §118、S7b = §119、S7c = §120、S7d = §121**（实际使用节号以 STATUS 为准，
若某片合并则顺延并在 STATUS 登记差异，不静默改口径）。
