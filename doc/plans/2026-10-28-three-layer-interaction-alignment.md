# 底层与 Agent 交互三层对齐体检（参考 cpld-pipeline 远程看板模式）

> 日期：2026-10-28。状态：**只体检、不改代码**；§7 五项裁决 + §9.5 四项冲突裁决已拍；P1–P8 探针已跑完（§6.3 + [证据档](../evidence/DSH_PROBE_20261028/README.md)）；下一步是 **S0 = 写 SPEC-REV-14（折进 REV-13，含 D1–D4 偏离）**。
> 参考文档：`/home/work/chenjunming/cpld-pipeline/doc/research/04-remote-ui-pattern.md`（方法论，**不是本仓契约**）。
> 本仓契约仍以 [`../spec/`](../spec/) 为准；流程纪律见 [`../../AGENTS.md`](../../AGENTS.md) §2/§3。
> 取证：代码 `file:line` + 一次定向 standin 测试（见 §8）。未跑四道门，不声称完成任何门。

## 1 三层定义与判定口径

| 层 | 边界 | 唯一 owner | 现行契约 |
|---|---|---|---|
| **A** | Host 引擎 ↔ 模型节点（N3/N6/N8/N10/N11/N12） | Host 管契约/预算/封存/控制；模型只出语义 | [SPEC-06](../spec/AGENT_CONTEXT_SPEC.md)、[SPEC-07](../spec/AGENT_WINDOW_SPEC.md)、[SPEC-08](../spec/DSH_AGENT_RUNTIME_SPEC.md) |
| **B** | Host ↔ DSH 执行器（实例/会话/工具/凭据/路径） | 桥接层只转协议，不复制业务判据 | SPEC-08（当前 `dsh` 后端显式不可用） |
| **C** | 看板投影 ↔ 前端（状态/会话/控制回执） | 看板只读投影 + 有限写操作 | [SPEC-04](../spec/WEB_UI_SPEC.md)、SPEC-07、[SPEC-09](../spec/AI_WORK_PANEL_SPEC.md) |

判定四态（比三态多一个"部分"，避免假绿）：**满足 / 部分 / 偏离 / 不适用**。
优先级：**P0**=不修则接 DSH 必踩死或证据失真；**P1**=影响体验/审计完整性；**P2**=登记差异即可。

## 2 本次访谈已定的目标态（12 条）

| # | 已裁决 | 影响层 |
|---|---|---|
| 1 | Python 仍是唯一编排者（派工/闸门/计数/回收），DSH 只当执行器 | A/B |
| 2 | 借 DSH 的多 agent 协作 + 上下文记忆；首版**全部模型节点**接入（默认后端仍 `agently`，S5 出对照后再定默认值，见 §7 Q4） | B |
| 3 | 一个节点一个 session，绑定 `(run, node)`；同会话跨 attempt 复用（**已验证**：`session/resume` 跨进程、跨 cwd 可用，见 §6.3 P1） | A/B |
| 4 | 不满意 → 回同一 session 追加意见 → 继续跑 → 再收口 = attempt N+1 | A/C |
| 5 | 完工信号＝会话内"提交成果"工具（**自写 TS 薄插件**），handler 把参数 POST 给 Python Host 校验后收口（**已验证**可行，见 §6.3 P2；插件加载失败只出 warning ⇒ 必须自检工具清单） | A/B |
| 6 | agent 可在**每 attempt 隔离副本**内读写/跑 bash；提交时 Host 按白名单+哈希导入（**实测限定**：写隔离成立、**读隔离不存在**；档位必须 `mode`+`defaultPreset` 双钉；attempt home 不得携带凭据） | B |
| 7 | 会话内可自由 spawn 子 agent，只限 `maxActiveSubagents` + 工具白名单 + 投影记账（**与 D0 旧建议冲突，见 §2.1**；裁决：全开放但配额先压到 2，见 §7 Q2） | B |
| 8 | 输入包覆盖归 Host，会话内压缩归 DSH，投影必须显示压缩次数（**与 D0 旧建议冲突，见 §2.1**；**实测**：压缩计数只在 session log，Host 必须自己落账，见 §6.3 P7） | A/B/C |
| 9 | 人可在**内嵌 DSH GUI 里直接说话**；Host 事后抓 `origin=human` 记账，不校验内容（**实测**：共用 home 时 Web 能列出/打开但**写句柄互斥** ⇒ 人只能在两次 attempt 之间说；内嵌走 **Q7 同源反代**，跨站 iframe 不可用，见 §6.3 P1/P8） | B/C |
| 10 | 指正**只在下一个请求边界生效**（业务结论仍只在收口+Host 校验时变） | A |
| 11 | **每 attempt 一个隔离 DSH 进程**（独立 cwd 副本；**home 共用**，P1 已验证并发写安全），另有一个常驻 Web 实例供人看/说 | B |
| 12 | 控制走**进程内直调 + 审计落盘**（不引入 `commands/*.cmd.json`）；terminate＝`TERM→超时→KILL 进程组`；卡死**只告警不自动收敛**（**实测**：退出码 0/空 final 不算成功，见 §6.3 P5） | A/C |

### 2.1 与 2026-10-24 D0 原生探针证据的冲突与处置

来源：`doc/STATUS.md` §57 + [`2026-10-24-dsh-native-interface.md`](2026-10-24-dsh-native-interface.md)（已实测：`dsh --profile sdk` 逐行 JSON-RPC；**无逐 prompt 取消 / 逐 session 关闭**，只有进程级 shutdown/EOF/信号；Web profile loopback **匿名 401**；base profile 含自动压缩；sdk 默认 `maxTokensAsSuccess`）。

| # | 旧证据/旧建议 | 本轮裁决 | 处置 |
|---|---|---|---|
| C1 | "每 attempt 一个隔离进程，不能共享活跃 Web 会话" | 先裁决"常驻单实例"，复查证据后**改回每 attempt 隔离进程**（目标态 #11） | 已消解；常驻的只剩 Web 实例（给人看/说），不承载执行 |
| C2 | SDK 无逐会话取消 | terminate＝杀该 attempt 进程 + 校验子孙进程清理 | 已消解（进程粒度天然匹配）；"杀进程是否留残留"进 §6.1 P5 探针 |
| C3 | Web 匿名 401（有鉴权门）；SDK 起的会话能否被 Web 列出**未验** | 人要在 GUI 里看/说（#9） | **未消解**：§6.1 P1/P8 探针；探不通则 #9 降级为"看板自建投影 + 导出会话副本" |
| C4 | "不启用子 Agent、最小允许工具" | 子 agent 全开放（#7）、可写副本（#6） | **已裁决**：全开放但 `maxActiveSubagents=2` + 工具白名单 + 投影记账；P6 验过越额拒绝后再放宽（§7 Q2） |
| C5 | "关闭自动压缩，否则上下文完整性无法核验" | 压缩归 DSH、投影显示次数（#8） | **按新裁决执行**：覆盖责任收缩到"Host 输入包"，业务结论不得依赖未提供材料；残余风险登记在 §8 |

## 3 对照表 A：参考文档 §3「十个关键决策」

| # | 文档决策 | A 层现状（证据） | B 层现状（证据） | C 层现状（证据） | 判定 | 建议动作（优先级） |
|---|---|---|---|---|---|---|
| 1 | 看板独立成网页，不做宿主 GUI 插件 | 不适用（无插件概念） | 不适用（无宿主插件依赖） | 独立 FastAPI + 静态页：`services/api.py:28` 导入 `RunManager`，服务同进程但独立部署；`~/.dsh` 实测只读（`touch` 失败） | 满足 | 不改 |
| 2 | 只绑 `127.0.0.1`，远程走 SSH 隧道 | — | — | `api.py:794` `host="127.0.0.1"`；`remote/serve.sh:4/41/47` 打印隧道命令且明示无鉴权 | 满足 | 不改 |
| 3 | 执行实例固定端口（被占回落随机） | — | 无执行实例：`host/agent_backends/__init__.py:43` 选 `dsh` 显式 `BackendUnavailable` | 界面无"实例/端口"概念 | 偏离（口径已变） | 每 attempt 进程**无常驻端口**；需要固定端口的是"给人看/说的 Web 实例"：固定优先 + 占用回落 + 页面显示实际端口（**P1**） |
| 4 | 看板内嵌实例 GUI（iframe） | — | — | `loop/web/**` 无 iframe（grep 0 命中）；目标态改为"总结投影 + 跳转/内嵌原生 GUI" | 偏离 | 内嵌前先 `curl -D -` 验 `X-Frame-Options`/CSP；不允许就退"新标签页 + 第二条隧道"需显式记录（**P1**） |
| 5 | 写操作只四类，全走命令文件，引擎唯一写状态者 | 控制动作恰 4 个（`agent_control.py:195` steer/pause/resume/terminate），进程内 + `agent_controls` 审计 + `expected_revision` 乐观并发（`:217`） | — | **12 个** POST 端点（`grep -c "@app.post" services/api.py` = 12），非命令文件；写后 `await poll()` 重读、无乐观更新（`web/app.js:3283`） | 偏离（**用户已裁决 12：保持进程内+审计**） | 不改实现；规格登记"四类写操作"不适用及理由（**P2**） |
| 6 | 批准绑 `stateHash`（pack md5 + 闸门摘要），改件后批准失败 | — | — | 锚只护 `gates.json` 自身：`kb_lib.py:667-701` 对去锚 JSON 求 sha256；`--artifact` 仅存清单、无回验（`gate.py:219-220`，`kb_lib.py:642-643`），**无“产物指纹变化 ⇒ 批准失效”判据** | 偏离 | 签入产物指纹（输入包 md5 + 闸门摘要）并纳入锚、`require-signed` 复算；**裁决改 `kb/tools/gate.py`**（唯一判据，冻结目录单独变更 + 留证，§7 Q1）（**P0**） |
| 7 | 批次任务正文写进配置，缺失拒绝派工 | 等价物已满足：`prompts/loop_nodes.yaml` + `node_schemas.py`；缺 schema 即 `KeyError` 显式失败（`model_request.py:38`） | 偏离：无"上下文包（路径 + md5）"清单概念 | — | 部分 | A 不改；B 新增上下文包清单（**P1**） |
| 8 | 阶段边界默认停，同阶段自动推进 | 满足：三道人工闸门 N4/N13/N14；drill 断言首个中断为 G1、状态 `waiting_gate` 而非 `running`（`accept_v1.py:187-188`） | — | 闸门视图独立入口 | 满足 | 不改 |
| 9 | 先 drill（确定性替身）再真跑 | 满足：`LOOP_LLM_MODE=standin` 全程 drill；`spikes/accept_v1_run.sh` 端到端 | — | 浏览器门可单独跑 | 满足 | 不改 |
| 10 | 会话视图只读解析落盘会话，不内嵌对话流 | — | 无 DSH 会话落盘可解析 | 偏离：会话视图来自 `agent_memory` 记录投影（`services/agent_view.py:238`），不是 DSH 会话 | 偏离（目标态已改为"投影 + 内嵌原生 GUI"） | 新增会话投影 + 跳转/内嵌；若做归档解析需按 zstd 多帧切（**P1**） |

## 4 对照表 B：参考文档 §5「我们踩过的坑」（10 条）

| # | 坑 | A 层现状 | B 层现状 | C 层现状 | 判定 | 建议（优先级） |
|---|---|---|---|---|---|---|
| 1 | 子进程继承宿主环境变量（`DSH_HOME` 指错） | — | 不适用：本仓无 DSH 子进程，仅 `job_runner.py`/`s0b.py` 起仿真与冒烟 | — | 不适用 | 接实例时隔离 home 显式配置 + resolve 后校验"在仓内且 ≠ `~/.dsh`"（**P0**） |
| 2 | 凭据是旧副本导致 403 | — | 满足：只读引用宿主凭据/settings，不拷贝（`model_provider.py:6-8`，`DSH_HOME` 见 `:85`） | — | 部分（接实例后需复验） | 实例 home 的凭据来源显式化；失败在界面可见（**P1**） |
| 3 | 执行者看得到工具表却缺 `read`/`bash`（preset 未组合） | — | 不适用 | — | 不适用 | 起会话后让它自检工具清单（含"提交成果"工具）作为接入手测（**P0**） |
| 4 | 会话 `cwd` 是相对路径 | — | 部分：`paths.py` 全自锚定绝对路径，但无"会话 cwd"概念 | — | 部分 | 传会话前一律解析为绝对路径并回读校验（**P0**） |
| 5 | 模型 403/超时后批次永远停在 open，伪装"在等人工" | 部分：HTTP `read` 超时 180 s（`model_provider.py:257-258` + `SETTINGS.yaml` `timeout_s: 180`）；失败 attempt 显式 `finish("error")`（`model_request.py:124`） | 不适用（无会话级） | 偏离：界面只有 elapsed（`app.js:1699-1736`）；`stale` 仅指"刷新失败"（`run-view-state.js:11`），**无"无进展"判据** | 部分 | 用户裁决 12：**只告警不自动收敛**。投影显示"无进展 N 分钟/最后事件/最后错误"并红字；状态文案禁止写成"在等人工"（**P0**） |
| 6 | 会话文件多帧 zstd 解压失败 | — | 不适用 | 不适用（不解析会话文件） | 不适用 | 若做归档解析：按魔数 `28 B5 2F FD` 切帧逐帧解（**P1**） |
| 7 | iframe 嵌不进（响应头禁止） | — | — | 不适用（无 iframe） | 不适用 | 内嵌前 P0 先验响应头（同 §3-#4） |
| 8 | 实例端口偶尔换导致隧道失效 | — | 不适用 | 不适用 | 不适用 | 随实例落地（**P1**） |
| 9 | 要开两条隧道/两个网页 | — | — | 满足：当前单服务单端口 8099（`api.py:794`） | 满足 | 接实例后改为一条 `ssh -L 8099 -L <实例端口>`（**P1**） |
| 10 | drill 里没有"确认"可点 | 满足：drill 显式提交人类决策并验拒绝矩阵（I6 非法 actor 403 / 自造枚举 400 / 缺 actor 400 / I4 前置），`accept_v1.py:224-271` | — | 闸门视图可点确认 | 满足 | 不改 |

> 统计：§3 满足 4 / 部分 1 / 偏离 5；§5 满足 2 / 部分 3 / 不适用 5（合并了原文"两条隧道"与"两网页"两种表述）。

## 5 对照表 C：接 DSH 才出现、文档未覆盖的新增契约缺口

| # | 缺口 | 现状 | 契约要点（目标态） | 依赖 | 优先级 |
|---|---|---|---|---|---|
| N1 | **Python ↔ DSH 桥** | 无；`dsh` 不在 PATH；`@deepseek-ai/dsh` 包在 `0.2.1-rc.2` 安装目录内；官方 stdio JSON-RPC 协议（7 方法 + 4 通知）有文档，**Python SDK 未安装**（`.venv` 无 dsh 包） | **自写 TS 薄插件**：定义 `submit_result` 工具（handler POST 给 Python Host）+ 把 `session.event/status`、`subagent.*` 转发回看板；Python 侧起进程、发 prompt、收事件、按事件终态收口。桥不复制业务判据 | §6.1 P1/P2 探针 | **P0** |
| N2 | **会话与节点绑定** | attempt＝一次请求（`agent_memory.Attempt`）；无 session 归属 | attempt＝**一次进程生命周期**；记录扩 `session_id`/轮次/pid/压缩次数；跨 attempt 复用同一 session 靠 `session/resume`（受 home 摆法约束）；旧 attempt 只增不改 | N1 + §6.1 P1 | **P0** |
| N3 | **提交工具收口** | 一次请求返回结构化 payload，Host `_validate` 校验 | 会话内工具 `submit_result`：schema 作参数，handler 在引擎侧校验后写 attempt；未提交即无收口 | N1 | **P0** |
| N4 | **可写隔离副本 + 导入** | 模型回传 edits，Host 命中/唯一性校验后应用（`model_steps`） | 每 attempt 一个副本目录；提交时 Host 按白名单 + 改动哈希导入候选件，越界即拒 | N1/N3 | **P1** |
| N5 | **子 agent 记账** | 无 | 配额（`maxActiveSubagents`）+ 工具白名单 + `subagent.started/finished` 进投影；越额拒绝而非静默 | N1 | **P1** |
| N6 | **人话抓取** | `human_interventions` 仅来自控制接口（`agent_control`），窗口只读 | 从 `session.event` 抓 `origin=human` 消息，记元数据（时间/长度/所属 attempt）进 `human_interventions`；不校验内容、不当作身份认证 | N1 | **P1** |
| N7 | **会话投影** | `agent_view.build_agents` 从记录投影；无会话摘要 | 总结投影（当前在做什么/最后工具/最后错误/压缩次数）+ 跳转或内嵌原生 GUI；投影只读，权威仍是 Host 记录 | N1 | **P1** |
| N8 | **上下文包与覆盖** | 输入按结构化 `input_data`；`input_digest` 只记长度 | 派工包＝路径 + md5 清单；覆盖声明由 Host 给，压缩次数由 DSH 报告并展示 | N1/N2 | **P1** |
| N9 | **预算/计量口径** | 唯一计量：`AM.check_budget` 紧凑序列化字节（≤120000），分项+开销==总量 | Host 输入包字节继续唯一准入；DSH 侧 usage（token/耗时）只作投影，**不进准入判据**（避免第二套口径，红线 8） | N1 | **P1** |

## 6 先探针、后写规格、再切代码

顺序沿用参考文档 §4「先状态真相，再引擎，最后界面」，但本仓多一道前置：**能力探针**（参考文档 §4-步 8 / §5-坑 3 的教训：把"框架可能提供"当成"已实现"是最大返工源）。

### 6.1 探针（一次性、可丢弃、不进主线）

| 探针 | 问题 | 判据（机器可判） | 不通则 |
|---|---|---|---|
| **P1** home 摆法 + 会话可见 | 每 attempt 进程用共用还是独立 `DSH_HOME`？另一进程起的会话，Web 实例能否列出/打开？多进程写同一 `sessions/` 库是否安全？ | 三种组合各跑一次：能列出 / 能打开 / 库索引无损坏；共用模式再跑并发写 2 进程 | 退回"每 attempt 独立 home + 看板自建投影"，并把目标态 #9 按 §7 Q5 降级为"投影 + 导出会话副本" |
| **P2** 工具 preset | 会话里能否看到 `submit_result` + 必需只读工具？自检工具清单与实际可用是否一致？ | 起会话让它逐个调用并回显结果；清单缺失即失败 | 改 profile 组合 / 显式 mount，不允许"看起来有、其实没有" |
| **P3** cwd 隔离 | `cwd` 是否绝对路径且被约束在 attempt 副本内？越界**写**是否被拒（读隔离实测不存在） | 副本内写 `rc=0`、副本外写 `rc=1`；`pwd` = 副本绝对路径；档位经 `mode`+`defaultPreset` 双钉后回显一致 | 不上写权（退回只读 + 提交 edits） |
| **P4** 事件与终态 | `session.event`/`status`/`wait` 顺序与终态是否可判？能否区分"模型 idle"与"任务完成" | 乱序/缺终态/重复终态都要能显式失败；`submit_result` 是唯一收口证据 | 收口只认提交工具，事件仅用于投影 |
| **P5** 杀进程 | terminate 杀 attempt 进程后，工具子孙进程是否清理干净？ | 杀后 `pgrep`/进程组检查为空；残留即失败 | 缩短会话寿命 + 起进程时用独立进程组 + 文档化残留风险 |
| **P6** 子 agent | `subagent.started/finished` 通知是否可用？越额 spawn 是否被拒？ | 配额 1..N 各跑一次；超限必须显式拒绝 | 子 agent 退回"按节点白名单"（目标态 #7 降级） |
| **P7** 压缩可见 | 压缩事件/计数能否被投影读到？ | 触发一次压缩并在投影里出现次数 | 关闭自动压缩（回到 D0 建议），超限显式失败 |
| **P8** Web 鉴权/内嵌 | Web profile 的 401 门怎么过？iframe 能否内嵌（`X-Frame-Options`/CSP）？ | `curl -D -` 记录响应头；无凭据请求必须 401 而不是 200 | 退"新标签页 + 用户已登录的浏览器会话"，并在 runbook 写明 |

### 6.2 切片（探针通过后）

| 切片 | 内容 | 验收（机器可判） | 门 |
|---|---|---|---|
| S0 | 规格修订：SPEC-08 改为"执行器契约"（每 attempt 进程 / 提交工具 / **最小 home** / cwd 副本 / 权限档双钉 / **terminate 三段式** / 事件终态与收口判据 / **桥走 sdk 协议**）；SPEC-06/07 改 attempt 粒度、压缩记账与人话记账 | 规格自洽；旧行为特征测试全绿；每条契约能在 §6.3 找到对应探针证据 | 单测（standin） |
| S0b | `stateHash` 判据落 `kb/tools/gate.py`（§7 Q1）：产物指纹入 `gates.json` + 纳入锚 + `require-signed` 复算；**冻结目录单独变更** | 改件后批准必须失败（真/假/缺件三态用例）；旧 run（无指纹）按 legacy 显式降级而非假通过 | kb 自测 + `run_env_layer_checks.sh --with-kb-selftests` |
| S1 | 桥（N1）：TS 薄插件（`submit_result` + 事件转发）+ Python 侧进程编排 + 隔离 cwd 副本 | 跑通一次"读文件→提交→Host 收口"；进程退出后无残留 | 探针复跑 + 单测 |
| S2 | 会话/attempt（N2/N3）：一节点一会话、跨 attempt `resume`、记录扩展 | 同会话两次收口 = attempt 1/2，旧记录可读；未提交不得收口 | 单测 + drill |
| S3 | 可写副本导入（N4）+ 子 agent 记账（N5） | 越界改动被拒；越额 spawn 被拒 | 单测 |
| S4 | 投影与界面（N7/N8/§4-#5）：总结投影、无进展告警、**同源反代 `/instance/*` + iframe（Q7）** | 刷新后与记录一致；无进展红字；状态不写"在等人工"；iframe 内能取到 cookie 且 `/api` 不 403 | 单测 + 浏览器门 |
| S5 | 全部模型节点切换 + 对照实测 | 六节点各一次真会话收口；与 Agently 路径对照数据 | 四道门 |
| S6 | 人话抓取（N6）+ 审计闭环 | 人在 GUI 说的话进 `human_interventions`；不受控来源不冒充干预 | 单测 |

### 6.3 探针结果（2026-10-28 实测，详见 [证据档](../evidence/DSH_PROBE_20261028/README.md)）

| 探针 | 三态 | 一句话结论 |
|---|---|---|
| P1 home/可见 | **过（有条件）** | 共用 home：Web 能列出+打开另一进程的会话；并发 3 进程×2 会话 ⇒ `sessions=10 ok=10 bad=0`；隔离 home ⇒ 不可见；**写句柄跨进程互斥**（`already owned by an active write handle`）；`resume` 跨进程/跨 cwd 可用 |
| P2 提交工具 | **过** | `--patch` 挂 ESM 插件 → 模型真调用 `submit_result`，handler 在 DSH 子进程执行；**插件加载失败只出 warning** |
| P3 cwd/写隔离 | **部分** | 写隔离成立（副本外 `rc=1`）；**读隔离不存在**（可读任意可读文件，含宿主 settings）；档位必须 `mode`+`defaultPreset` 双钉，否则继承宿主 `danger-full-access` |
| P4 事件/终态 | **过（headless 层）** | 终态是显式 `turn_end.reason.kind`（`completed`/`error`+`code`）；`--session-id` 续跑 turn 1→2；**headless 无 subagent/compaction 事件** |
| P5 杀进程 | **部分** | SIGTERM 无残留；SIGKILL+full-access 留孤儿；**退出码 0/空 final 不算成功（无 `turn_end`）** |
| P6 子 agent | **过（限定）** | sdk JSON-RPC 发 `subagent.started/finished`；配额键 `subagent.config.maxActiveSubagents`（默认 8，实测越额提示 `active child limit: 1`）；**headless 0 条** |
| P7 压缩可见 | **部分** | 可低成本触发；**计数/时点只在 session log**（`compaction/summary`+`time`），事件流与 projcache 都没有 |
| P8 Web 鉴权/内嵌 | **部分** | 匿名 401 且无 `WWW-Authenticate`、不支持 Bearer；只能 `?token=`→`SameSite=Strict` cookie；页面无 `X-Frame-Options`，但 `/api` 跨权威 `403` ⇒ 跨站 iframe 不可用 |

**由探针改写的契约点（写进 S0）**：桥的观测面改为 sdk stdio JSON-RPC（subagent/compaction 只在那里）；启动后必须自检"工具清单 + 实际权限档"；attempt home 最小化且不得携带凭据；terminate 三段式；收口只认 `turn_end`/提交工具；压缩与子 agent 由 Host 落账。

## 7 裁决记录（2026-10-28，全部已拍）

| # | 议题 | 裁决 | 落点/影响 |
|---|---|---|---|
| Q1 | `stateHash` 判据落点 | **改 `kb/tools/gate.py`**（唯一判据：CLI 签与 UI 签同一条） | 产物指纹（输入包 md5 + 闸门摘要）写入 `gates.json` 并纳入锚，`require-signed` 复算；`kb/` 冻结 ⇒ 单独变更 + 留证（`AGENTS.md` §3、红线 11） |
| Q2 | 子 agent 冲突（C4） | **全开放，配额先压到 2** | `maxActiveSubagents=2` + 工具白名单 + `subagent.*` 记账；P6 验过越额拒绝后再放宽 |
| Q3 | 预算口径 | **DSH usage 只投影、不进准入** | 准入仍只认 `AM.check_budget` 的紧凑序列化字节；token/耗时仅展示（避免第二套口径，红线 8） |
| Q4 | 回退路径 | **保留 `agently` 可切回，直到 S5 出对照数据** | `agent_runtime.default_backend` 首版仍为 `agently`；S5 交付"真会话 vs Agently"对照后再定默认值 |
| Q5 | 目标态 #9 降级线 | **接受降级** | P1/P8 探不通 ⇒ #9 变为"看板看总结投影 + 导出会话副本"，不再承诺在原生 GUI 里直接说话 |
| Q6 | 凭据投放（读隔离不存在） | **只走 env + 风险记档** | key 只在 attempt 进程环境变量里、不落 home 文件；**已知风险**：agent 的 bash 工具可 `echo $PUBLIC_API_KEY` 读到 ⇒ 写进规格的残余风险，不声称已解决 |
| Q7 | 内嵌 GUI 形态 | **同源反代** | 看板 `127.0.0.1:8099/instance/*` 反代到 DSH web（同源 ⇒ cookie 可投递、`/api` 不 403），iframe 内嵌；反代层要单独测（并入浏览器门） |

> 依据：Q1 的"唯一判据"来自红线 8（不许第二套同判据实现）；Q2/Q3/Q4/Q5 的取舍均为"先保证可交付 + 可回退"，与 `AGENTS.md` §2 的"规格声称、代码没有 ⇒ 登记缺口"一致。

## 8 取证与限制（照实登记）

- 本轮只体检：**未改任何代码**，未走 SpecDD 实施；表内"建议"不是已实施的契约。
- 定向实测：`cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_agent_control.py tests/test_agent_view.py tests/test_agent_context_memory.py`
  ⇒ `83 passed, 1 warning in 3.18s`（从命令输出复制；**不是**四道门）。
- 环境事实：`~/.dsh` 只读（`touch` 失败：`Read-only file system`）；`dsh` 不在 PATH；DSH 安装目录含 `@deepseek-ai/dsh`（`0.2.1-rc.2`）与 `dsh-sdk-*`；`loop/.venv` 无 DSH Python SDK。
- 沿用证据：STATUS §57（SDK 无逐会话取消、Web 匿名 401、base 含自动压缩、`maxTokensAsSuccess` 默认开）——本轮未复测，按"历史实测"引用，不当作当前实测。
- 未验证：P1–P8 全部探针、真实模型认证、工具写权强制、上下文完整性、异常停机清理。**不得**在规格里写成已实现。
- 残余风险（Q6）：凭据经 env 注入，agent 的 bash 工具可读到（读隔离不存在）——**已接受并记档**，不当作已缓解。
- 残余风险（C5）：DSH 自动压缩使"会话是否读完输入包"不可证；本表把覆盖责任收缩到"Host 输入包 + 提交回传"，业务结论不得依赖未提供材料——这条要写进 SPEC-06 修订。

## 9 与 SPEC-REV-13（2026-10-26，远端 `abdb16f`）的对齐

> 来源：[SPEC-REV-13](../spec/SPEC-REV-13-20261026.md) + [云端 DSH 与记忆设计](../plans/2026-10-26-cloud-dsh-memory-design.md)。
> 该规格成文于本次体检之前，**已把 D2/D3/D4 与 WM/IL/EXP 写成契约**；因此 S0 不再"新写一份 SPEC-08 修订"，
> 而是**折进 REV-13**（新增 REV-14 记录差异，不改历史正文）。下列三张表是折叠时的输入。

### 9.1 可直接借鉴（不必自造）

| # | REV-13 条款 | 借鉴点 | 落到本次哪项 |
|---|---|---|---|
| A1 | §5.3 状态机 | `prepared → starting → running → completed/failed/cancelled/execution_unknown → closed`；**`completed` 只表示后端候选完备**，业务接受另经 Host | N1/N2 的 adapter 状态与收口语义 |
| A2 | §5.2 请求与句柄 | `contract_version/identity{run_id,node,attempt_key,generation}/context_manifest_ref/instruction_revision/execution_grant_ref/runtime_fingerprint`；**handle 只存在接入层**，可恢复描述由 `agent_memory` 封存 | N1/N2 的字段与落点（别再自造第二套） |
| A3 | §4.1 + §4.3 | 资源布局（`input/` 只读、`scratch/`、`candidate/`、私有 `dsh-home/`、`agents/`）；七步交接：**先封存 intent → 起资源 → Host 封存 handle 才 prompt → 停止后才导入候选** | N1/N3/N4 的执行顺序与目录 |
| A4 | §6 WM 与 §6.3 冷热分离 | `working_memory` + `snapshot_sha256` + `source map` + `input_ref`（JSON Pointer，禁循环/外部）；**索引不等于材料已送达** | N8 上下文包（比"路径+md5 清单"更完整） |
| A5 | §7 IL 指令生命周期 | scope（attempt / node_rework / run）+ `create/revoke/supersede` + CAS + **接受门核 generation/指令版本** + `accepted≠applied≠effective` | **"人反馈"的正解通道**（见 §9.2-C3） |
| A6 | §10 必测不变量 | `CL/DS/WM/IL/EXP/OBS/REG` 系列，尤其 `DS-02`（仅 idle/messageId/rc=0 不放行）、`DS-03`（迟到结果只看代次）、`DS-05`（留后代不得报 paused）、`DS-06`（源漂移/换件拒绝） | S1–S3 的验收蓝本 |
| A7 | §4 分级 C0/C1/C2/E + `ready/unavailable/unknown` | 把"探针通过"与"业务可用"分层；**配置启用 ≠ 观察可用** | 我们把本机探针标为 C1/C2 证据，业务结论仍需 E |
| A8 | §5.4 | "**不以 cwd、提示词或工具名称白名单代替效果隔离**" | 修正我们 P3 的"写隔离即隔离"表述 |
| A9 | §5.1 | 版本锁定：0.1.x/0.2.x 不默认兼容，**本机安装版本不能代替目标版本** | S0 必须锁 package/锁文件/协议指纹；本轮探针只对 `0.2.1-rc.2` 成立 |
| A10 | 设计 §2 `P0–P7` | 已有切片编号与依赖（P0 探测 → P1/P2/P3 记忆/指令/经验 → P4/P5 D2/D3 → P6 C2 → P7 D4） | 我们的 S0–S6 应**映射**到 P0–P7，不并存两套编号（红线 8） |

### 9.2 与本次裁决的冲突（必须重裁，按严重度）

| # | 冲突点 | REV-13 条款（原文要点） | 本次裁决 | 后果 |
|---|---|---|---|---|
| **C1** | 凭据与工具准入 | §5.4 "无其他 run、宿主 home、**凭据文件**…挂载"；"原始凭据不得成为模型可读文件/工具输出"；"**若无法阻止工具读取原始秘密或宿主其他数据，则带工具准入失败**"；DS-04 必测 | **Q6 只走 env + 风险记档** | 直接冲突。按 REV-13，env 注入且读隔离不存在 ⇒ **带工具准入不成立**；要么真容器/bwrap 隔离，要么本阶段不带工具 |
| **C2** | 自动压缩 | §5.4 "受限 profile **关闭自动压缩**、静默工具裁剪和 token 达限当成功"；DS-07 必测 | **#8 压缩归 DSH + 投影显示次数** | 冲突。P7 实测压缩计数只在 session log、事件流与 projcache 都没有 ⇒ 我们那条"投影显示次数"没有稳定来源；REV-13 的"关闭"更可判 |
| **C3** | 会话续接与"人在会话里说话" | §5.3 "每 attempt 独立进程…**私有 DSH_HOME/DSH_AGENTS_HOME**；不连接用户正在使用的会话；**不使用 session/resume 续接不明上下文**"；§2 不实施"共享聊天历史"；§11 "默认不续会话" | **#3/#4 共用 home + 同会话 resume + #9 人进 GUI 说话** | 硬冲突。替代方案：REV-13 的 **IL（A5）** 正是"人在下一个尝试生效"的受控通道，与我们裁决 #10 完全一致，且不需要共用 home/resume |
| **C4** | 子 agent | §2 不实施项含"**并行子 Agent**"；§5.4 "默认关闭自动委派" | **#7 全开放（配额 2）** | 冲突。P6 证明能力存在且可拒，但"能"不等于"该开" |
| **C5** | home 共用与可见性 | §5.3/§4.1 每次 attempt **私有 home**，不与用户会话共享 | **#11 home 共用**（P1 验证并发安全）；**Q7 同源反代**依赖共用 home 才能列出 attempt 会话 | 级联冲突：采纳私有 home ⇒ Web 看不到 attempt 会话 ⇒ 反代没有对象，"人看对话"只能走 Q5 降级线（Host 导出投影/会话副本） |

### 9.3 探针结论反哺 REV-13（规格缺口，不是我们自造）

| # | 探针 | 应补进 REV-13 的位置 | 补什么 |
|---|---|---|---|
| B1 | P2 | §4.2 `result` 行 + DS-02 | `submit_result` 工具是"结构化结果 + turn 完成"的稳定通道；`result` 行至今没写"稳定结果获取接口"长什么样 |
| B2 | P2 | 新增 DS-08 | **插件/工具加载失败只出 warning、不阻断启动** ⇒ "启动成功 ≠ 可用"，必须自检工具清单 |
| B3 | P3 | §5.4 + 新增 DS-09 | 权限档会被用户层 `permission-presets.defaultPreset` 覆盖；**禁止把宿主 settings 复制进 attempt home**；必须回显实际 preset |
| B4 | P6/P7 | §5.1/§5.4 | headless `--json` 无 `subagent.*`/compaction 事件 ⇒ 观测面只能是 sdk 协议 + session log 落账 |
| B5 | P5 | DS-02 | **退出码 0、空 `final.text`、无 `turn_end` 都不算完成**；SIGKILL+full-access 会留工具后代 |
| B6 | P1 | §5.3 | `resume` 与写句柄互斥（`already owned by an active write handle`）；若保留 resume 必须写句柄仲裁；采纳私有 home 则作废 |
| B7 | P6 | §5.1 映射表 | 0.2.1-rc.2 实测配额键 `subagent.config.maxActiveSubagents`（默认 8）与越额原文 `active child limit: 1`；锁定版本映射时以实测为准 |

### 9.4 修订建议（S0 的新定义）

1. **不新写 SPEC-08 修订**：新增 `SPEC-REV-14`（日期本轮），只记录 §9.2 的冲突裁决与 §9.3 的缺口补丁，并给 SPEC-08/06/07 加指针；REV-13 正文不动（历史文档只增不改）。
2. **切片改挂 P0–P7**：本轮 S0–S6 与设计文档 P0–P7 做映射表（一处编号），S0=REV-14 契约、S1=P0+P4 探测与协议、S2=P5 接线、S3=P1/P2/P3 记忆与指令、S4=S4 投影界面、S5=P6 C2、S6=P7 D4。
3. **验收统一用 §10 的编号**（CL/DS/WM/IL/EXP/OBS/REG），本次追加 DS-08/DS-09；探针证据按 A7 分层标注（C1/C2）。
4. **S0b（kb stateHash）保持独立**，不折进 REV-13（它是 kb 冻结目录变更 + 证据）。

**S0 已交付（2026-10-28）**：[SPEC-REV-14](../spec/SPEC-REV-14-20261028.md)（D1–D4 偏离 + B1–B7 补丁 + A1–A10 采纳映射 + 切片映射 + `DS-08/DS-09`）；SPEC-06/07/08 各加一段指针。实现未开始。

### 9.5 冲突裁决（2026-10-28，全部已拍）

| 冲突 | 裁决 | 与 REV-13 的关系 | 落地要求 |
|---|---|---|---|
| **C1** 凭据/工具准入 | **保留本轮裁决**：凭据只走 attempt 进程 env、不落 home；记录"agent 可读 env/可读宿主文件"为**已知风险** | **偏离** §5.4（"无法阻止读取则带工具准入失败"） | REV-14 的偏离条款 D1 必须写明：本阶段带工具准入**不以强隔离为前提**，代价与暴露面显式记档；真容器隔离落地后重评 |
| **C2** 自动压缩 | **保留 DSH 压缩 + Host 落账**：Host 从 session log 读 `compaction/summary`（含 `time`/`compactionId`）落账并投影 | **偏离** §5.4（"关闭自动压缩"）/ DS-07 | D2 条款：压缩是确定性可读事实（P7），不是静默截断；`compaction/end.error` 必须显式失败 |
| **C3+C5** 会话/home/人反馈 | **保留共用 home + 同会话 `resume` + 人可在 GUI 说话**（写句柄互斥 ⇒ 只能在两次 attempt 之间）；**Q7 同源反代保留** | **偏离** §5.3（私有 home、不 resume、不连接在用会话）与 §2"不实施共享聊天历史" | D3 条款：会话是**旁路审计与沟通面**，不是业务状态；Host 只冷读、不接管活体；attempt 进程退出后 Web 才能写；`human_interventions` 从会话事件抓取 |
| **C4** 子 agent | **全开放，配额 `maxActiveSubagents=2`** | **偏离** §2"不实施并行子 Agent" / §5.4"默认关闭自动委派" | D4 条款：越额必须显式拒绝（P6 原文 `active child limit: 1`）；记账只走 sdk 协议通知 + 父会话日志，**不读 headless 输出**；默认 8 不得当作生效值（须运行时回显） |

### 9.6 偏离登记（REV-14 的骨架）

REV-14 不重写 REV-13，只记录：① 上述 D1–D4 四条偏离（含理由、证据、复评条件）；② §9.3 的 B1–B7 缺口补丁；③ §9.1 的 A1–A10 采纳映射；④ 切片编号映射（本轮 S0–S6 ↔ 设计 P0–P7）。

**偏离复评条件（写成条款，不是愿望）**：

- D1：出现等价强制沙箱（能挡读 + 清 env）并通过 DS-04 实测 ⇒ 重评"带工具准入"是否恢复为 REV-13 口径。
- D2：若 DSH 后续版本在事件流/投影里提供 compaction 事实 ⇒ 改为"事件流优先、session log 兜底"。
- D3：若 DSH 支持"只读挂载他人 home 会话"或写句柄仲裁原语 ⇒ 重新考虑是否需要共用 home。
- D4：若子 agent 成本/后代残留实测超阈值（P6 未测成本）⇒ 收紧为白名单或关闭。
