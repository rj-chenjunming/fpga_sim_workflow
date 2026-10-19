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
| `WORKSPACE_ROOT/{index,conflicts,baselines,runs}` | `kb/tools/*` 经唯一解析器写入；人工只手写 `adjudication/` 请求 |

---

## 4 DoD：四道门（缺一不算完成）

| 门 | 命令 | 期望 |
|---|---|---|
| 单测 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | 70 收集；无回归 |
| kb 自测 | `loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` / `_selftest_n5_reachability.py` | 10/10、9/9（需要可写 `WORKSPACE_ROOT`） |
| 端到端 | `cd loop && bash spikes/accept_v1_run.sh` | rc=0、117 断言（需要可写 `ENV_ROOT`） |
| 文档 | 路径引用存在性 + 移动件有 MIGRATION/横幅 + 数字与 `doc/STATUS.md` 一致 | 零断链 |

> **不得声称「已合规」**：审计发现但未修复的阻断项，必须在 `doc/STATUS.md` 与审计报告中保持可见。

---

## 5 红线（继承并适用于本仓）

1. 只新增 `kb/` 与 `doc/` 下文件；环境的 `RTL/ TB/ PKG/ TESTLIB/` 与已定稿基线资产**绝不修改**。
2. 数字一律由命令输出复制，禁止手算；唯一数字源 `doc/STATUS.md`。
3. 归档只增不改；已冻结运行目录绝不回填。
4. 闸门枚举权威 = `kb_lib.GATE_DECISIONS`，任何脚本/前端不许手抄；`pending` 是状态不是动作。
5. `human_signed` 只在 `actor_kind="human"` 时为真；权威凭据是 `gates.json` + `gates.sha256` 锚。
6. 单槽：`uvs.setup` 是环境根下全局单文件 ⇒ 同环境禁止并发；跨机走 `run_tc.py`。
7. 时间字段是唯一允许的非确定性，必须经 `--now`/`KB_NOW` 单一入口注入。
8. 口径唯一：不许出现第二套同判据实现。
9. 发现缺陷**只报告不改**；独立验证者不修被测文件。
10. 引用冻结文件必须带 md5；判「未改动」按内容 md5，不按 mtime。
11. **软件对环境的承诺**：除 `SIMLIB_RUN/` 与 `uvs.setup`（自愈还原）外，不写 `ENV_ROOT` 任何文件。
12. **文档纪律**：移动文件必须留迁移记录（旧→新 + 内容 md5 未变声明）；历史快照必须加「已过期」横幅。

---

## 6 目录与文档纪律

- 根入口：`README.md`（项目导航）→ 本文（流程）→ `doc/README.md`（文档索引）。
- 新增文档先问「它属于 spec / agents / evidence / history / audit 哪一类」，**不允许在根目录堆日期文件**。
- 一次审计一份报告：`doc/audit/AUDIT-<YYYYMMDD>-<topic>.md` + `parts/` 附录；报告头必须说明「本轮是否修复」。
- 状态数字只在 `doc/STATUS.md` 维护；其它文档引用它，不各自抄一份。
