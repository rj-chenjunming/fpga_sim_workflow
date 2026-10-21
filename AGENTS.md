# 本仓流程与组织规范（`AGENTS.md`）

> **适用范围**：`change-impact-loop` 软件仓（`loop/` + `kb/` + `doc/`）。
> **不适用范围**：环境仓自带的 `doc/AGENTS.md` —— 它是环境侧的组织层权威，本仓**只读引用、绝不修改**。
> **本文件是流程权威**：定角色、定流转、定写权、定红线、定 DoD；业务/机制契约仍以 `doc/spec/*.md` 为准。

---

## 1 组织形态与 owner

一个 Lead 带三类 owner，**每个决策/状态/效果恰好一个 owner**：

| Owner | 承载 | 不负责 |
|---|---|---|
| **Host 确定性程序**（`kb/tools/*`、`loop/host/*`） | 快照、md5、diff、影响分析、执行、计数、闸门权威、N16 归档 | 不上模型、不猜、不吞异常换默认值 |
| **模型节点**（`loop/workflows/chunks/model_steps.py` + `loop/prompts/*`） | N3 差异语义、N6 用例修订、N8 静态复核、N10 FAIL 分类、N11 证据守护、N12 报告 | 不越过闸门、不做授权/算术/身份 join |
| **人** | 三道闸门（N4/N13/N14）+ N16 晋升触发 | —— |
| **TriggerFlow** | 稳定拓扑、durable interrupt、恢复 | 不承担业务持久化 |
| **独立验证者** | 复核与终验 | 不修被测文件、不改被测代码 |

> 历史角色细节见 [`doc/agents/`](doc/agents/README.md)；环境侧 4 个既有角色（用例作者/执行/检查/回归守护）仍是环境团队规范。

---

## 2 流转：本仓的 Spec-Driven Development（SDD）

```
需求/缺陷
  │
  ① 规格      doc/spec/*.md         ← 改契约先于改代码；契约缺口写进 §未决，不静默补实现
  ② 计划      任务拆分 + 写权划分    ← 跨 owner 的改动先列 owner/落点/验证门
  ③ 实现      TDD：先失败用例再实现   ← 每个不变式至少一条不读源码也能判定的断言
  ④ 验证      四道门全绿 + 证据落档   ← 见 §4；数字从命令输出复制
  ⑤ 归档      提交 + 证据只增不改    ← 归档件 chmod 444，md5 记到目录之外
```

**硬性纪律**

1. 改行为前先确认它属于哪个 owner；**两个 owner 都能写同一份状态 ⇒ 设计不成立**，先改设计。
2. 规格里声称、代码里没有的能力 ⇒ 登记为缺口（进审计/§未决），**不得用假实现或默认值糊过去**。
3. 失败必须显式：`failed` 状态 + `error` + 关闭执行；**不许把崩溃/恢复失败伪装成「在等人工」**。
4. 模型输出必须有**授权消费者**；没有消费者的字段/节点不得保留（YAGNI）。
5. 拒绝必须发生在提交前（闸门 actor/枚举/I4 校验先于签署与 resume）。

### 2.1 优化与重构必须执行的 SpecDD 顺序

1. 先读相关业务/机制/UI 规格，明确问题、可观察行为、不变量、唯一 owner 和验收条件；先更新规格，再改实现。
2. 计划写入 `doc/plans/`，列出切片、落点、验证门与环境限制。未经验证的能力和未决项必须显式登记。
3. 重构前先用**特征测试**固定既有可观察行为并运行通过；新行为/缺陷另加先失败用例。先做保持行为的局部提取，再实现行为变化，不把重构当作静默改契约的理由。
4. 每个切片执行受影响测试，再按 §4 验证。通过、失败、跳过、未运行分别记录；内网环境不可用时完成独立验证并保留内网验收条件，不能伪造环境或把跳过当通过。
5. 本轮实测写入 `doc/STATUS.md`；证据只新增，冻结后不得回填。同一执行者分阶段验证应如实说明，不能声称独立复核。

### 2.2 Agent 上下文与记忆纪律

- 具体契约见 [`AGENT_CONTEXT_SPEC.md`](doc/spec/AGENT_CONTEXT_SPEC.md)。Host 负责输入覆盖、预算、来源与版本校验；禁止静默截断后声称已完成全范围分析。
- 工作记忆由本轮结构化状态提供；每次模型请求使用新的 agent。重启记忆来自执行快照和权威文件，不依赖进程内聊天记录。
- 模型调用前保存输入、提示词/Schema 版本与校验上下文；结果、失败和替身状态分别留痕。调用记录按运行/节点/尝试只增不改，保存失败必须显式失败；不保存认证凭据。
- 跨运行经验由人明确确认并指定来源、适用环境/基线/事实和提示词版本；来源变化、版本不符或未确认则不使用并记录原因。模型不得自行把输出晋升为经验。
- 历史经验仅作有来源的建议；当前事实、文档和 Host 校验优先。经验不能签闸门、绕过 blockers 或改写业务权威。“human”字段是单机流程元数据，不等于身份认证。

---

## 3 写权（互只读）

| 产物 | 唯一写者 |
|---|---|
| `loop/workflows/**`、`loop/host/**`、`loop/services/**`、`loop/web/**` | Lead 指定的实现 owner（同一时刻一人） |
| `loop/prompts/**`、`loop/SETTINGS.yaml` | Lead / 编排 owner |
| `kb/tools/**`、`kb/schema/**`、`kb/README.md` | kb owner（**冻结目录，改语义需单独变更并留证**） |
| `doc/spec/**` | Lead（契约变更需显式评审） |
| `doc/agents/**` | Lead（角色定义） |
| `doc/evidence/**`、`doc/history/**` | **只增不改**（证据/历史快照冻结） |
| `doc/STATUS.md` | Lead（唯一数字源） |
| `doc/audit/**` | 审计 owner（一次审计一份，只新增） |
| 环境仓 `RTL/ TB/ PKG/ TESTLIB/` | **谁都不许改**（需环境侧显式授权，见环境 `doc/AGENTS.md` 红线） |
| `WORKSPACE_ROOT/{index,conflicts,baselines}` 与 run 内业务台账 | `kb/tools/*` 经唯一解析器写入；其余运行产物按节点契约分配写权 |
| run 内 `agent_calls/**` | Host `loop/host/agent_memory.py`（只增不改的模型调用记录） |
| run 内 `agent_controls/**` 与活跃模型请求控制 | Host `loop/host/agent_control.py`（只增不改审计；按 [工作窗口契约](doc/spec/AGENT_WINDOW_SPEC.md) 在请求边界取消/重发） |
| 工作区 `adjudication/agent_experiences.json` | 人工；Host 只读筛选，模型不得写回 |

---

## 4 DoD：四道门（缺一不算完成）

| 门 | 命令 | 期望 |
|---|---|---|
| 单测 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | 收集/通过/失败/跳过分别记录于 STATUS；无回归 |
| kb 自测 | `loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` / `_selftest_n5_reachability.py` | 全部断言通过；需要可写 `WORKSPACE_ROOT` 与历史夹具 |
| 端到端 | `cd loop && bash spikes/accept_v1_run.sh` | 退出成功且断言完整执行，实测见 STATUS；需要可写 `ENV_ROOT` |
| 文档 | 路径引用存在性 + 移动件有 MIGRATION/横幅 + 数字与 `doc/STATUS.md` 一致 | 零断链 |

> **不得声称「已合规」**：审计发现但未修复的阻断项，必须在 `doc/STATUS.md` 与审计报告中保持可见。

---

## 5 红线（继承并适用于本仓）

1. 本软件仓的新增与修改按 §3 写权和 §2 SpecDD 执行；环境的 `RTL/ TB/ PKG/ TESTLIB/` 与已定稿基线资产**绝不修改**。原“只新增 kb/doc”是拆仓前环境仓限制，不得与本软件仓 §3 的实现写权混用。
2. 数字一律由命令输出复制，禁止手算；唯一数字源 `doc/STATUS.md`。
3. 归档只增不改；已冻结运行目录绝不回填。
4. 闸门枚举权威 = `kb_lib.GATE_DECISIONS`，任何脚本/前端不许手抄；`pending` 是状态不是动作。
5. `human_signed` 只在 `actor_kind="human"` 时为真；权威凭据是 `gates.json` + `gates.sha256` 锚。
6. 单槽：`uvs.setup` 是环境根下全局单文件 ⇒ 同环境禁止并发；跨机走 `run_tc.py`。
7. 时间字段是唯一允许的非确定性，必须经 `--now`/`KB_NOW` 单一入口注入。
8. 口径唯一：不许出现第二套同判据实现。
9. 独立验证者发现缺陷**只报告不改**，不修被测文件；获得实现授权的 owner 按 §2 SpecDD 修复，不得同时声称独立验证。
10. 引用冻结文件必须带 md5；判「未改动」按内容 md5，不按 mtime。
11. **软件对环境的承诺**：除 `SIMLIB_RUN/` 与 `uvs.setup`（自愈还原）外，不写 `ENV_ROOT` 任何文件。
    S0 例外仅适用于**新建且与基线分离的派生副本**：Host 可完整复制并整体替换副本 RTL，基线原件零写入。副本 `TB/top.sv` 接口适配、逐 hunk 登记及三库冒烟按 [S0 契约](doc/spec/S0_ENVIRONMENT_SPEC.md)；未接入能力不得宣称通过，不扩大原环境写权。
12. **文档纪律**：移动文件必须留迁移记录（旧→新 + 内容 md5 未变声明）；历史快照必须加「已过期」横幅。

---

## 6 目录与文档纪律

- 根入口：`README.md`（项目导航）→ 本文（流程）→ `doc/README.md`（文档索引）。
- 新增文档先问「它属于 spec / agents / evidence / history / audit 哪一类」，**不允许在根目录堆日期文件**。
- 一次审计一份报告：`doc/audit/AUDIT-<YYYYMMDD>-<topic>.md` + `parts/` 附录；报告头必须说明「本轮是否修复」。
- 状态数字只在 `doc/STATUS.md` 维护；其它文档引用它，不各自抄一份。
