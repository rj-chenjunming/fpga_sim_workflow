# SPEC-10 · 开发侧工作流自我迭代（RSI）契约

> 编号：**SPEC-10**（文件名不变；新增契约，非修订既有 SPEC，故不占用 `SPEC-REV` 编号）。
> 状态：**规格阶段（未实现、未验收）**。本文件是可判定的实施契约；任何"已生效/已提升"表述必须有台账记录支撑。
> 来源：外部设计文档《工作流自我迭代闭环（RSI-Reflect）设计方案 v1.0》（2026-10-29，用户提供，未入库）。
> **本规格是唯一契约；外部文档只作来源，冲突时以本文为准。** 相对外部文档的有意偏离见 [§4](#4-rsi-01-触发与-cli-契约人工按键p0-只做-cli)（不做钩子，改人工触发）、[§6](#6-rsi-03-输入切片覆盖率与预算)（否决 20k 固定预算）、[§8](#8-rsi-05-落地分层与写权白名单)（经验自动生效 ⇒ draft + 人批）；已核实项见 [§15](#15-rsi-12-内核适配层已核实不臆造)；未决见 [§19](#19-未决与验证边界)。
> 上游契约：[SPEC-02](LOOP_ORCHESTRATION_SPEC.md)（编排 owner）、[SPEC-06](AGENT_CONTEXT_SPEC.md)（调用留痕与人工确认经验 M1/M2）、[SPEC-07](AGENT_WINDOW_SPEC.md)（人工指令）、[SPEC-08](DSH_AGENT_RUNTIME_SPEC.md)（DSH 执行后端）。
> 执行纪律：[`AGENTS.md`](../../AGENTS.md) §2 SpecDD / §3 写权 / §5 红线。

---

## 0 一句话与判断

每次开发会话（人或 Lead + teammate/subagent 协作）结束后，由**人手动触发**一次异步复盘，把会话轨迹、人的反馈原文与验证事实转成「经验（draft）、skill 提案、代码问题单」；经验经人批准后才进入下一轮上下文，skill 改动**必须人批准**才由确定性代码应用到仓内副本，下一轮复核上轮改动是否真的生效，无效则自动撤回。

> **本方案的价值不在"让它改自己"，而在"证明它改对了"。** 因此本文所有机制服务于三件事：可验证、可回滚、可审计；**不服务于**"越用越强"的叙事。

**一句话边界**：RSI 是**开发侧旁路工具**，不是产品运行期的一部分；它不推进 N0–N16、不签任何业务闸门、不改验收器/评分器、不写环境仓。

---

## 1 范围与非目标（RSI-00）

### 1.1 范围

- **服务对象**：本仓（`change-impact-loop`）的**开发工作流**——Lead、teammate/subagent 的协作与所用 skill/subagent 提示词。
- **迭代对象**：仓内副本形式的 skill（`doc/agents/skills/**`）、subagent 提示词（`doc/agents/subagents/**`）、经验库（`.rsi/memory/lessons.md`）、代码问题单（`.rsi/issues/**`）。
- **数据来源**：dsh 会话日志（只读）、仓内 git 事实、人给的反馈原文。

### 1.2 非目标（硬性）

| 不做 | 理由 |
|---|---|
| 不改模型权重、不微调 | 成本与风险不成比例 |
| 不改验收器 / 评分器 / 仿真判定脚本 | 评估器必须在可编辑面之外，否则会进化出"改判分逻辑"的假增益 |
| 不自动合并任何工具代码补丁 | 错脚本会污染后续所有 run |
| 不默认开启 skill 自动生效（`auto_apply_skill` 恒 `false`） | 静默劣化是此类系统的头号死因 |
| 不承诺"越用越强"的长期收益 | 只有留出集对照才能证明；本文 P0/P1 不声称收益（§19 未决 3） |
| 不做跨项目记忆共享 | `.rsi/` 按仓隔离；`~/.dsh/skills` 全局共享，RSI **永不写** |
| 不改产品链路 | 不写 `gates.json`、不写产品 run 目录、不改 `kb/**`、不进四道门 |
| 不替代 AGENTS §9 的独立验证 | 复盘者与开发者常为同一模型家族；RSI 结论不构成独立验证 |

---

## 2 唯一 owner（每个对象恰好一个写者）

| 对象 | 唯一 owner | 边界 |
|---|---|---|
| dsh 会话日志 | dsh（只读） | RSI 采集器只读，不改不删 |
| RunRecord / 输入切片 / 覆盖率 | **RSI 采集器**（确定性代码，无模型） | 不做语义判断、不猜 |
| ProposalSet（复盘输出） | **Reflector**（模型） | **无任何被控文件写权**；输出非法即失败 |
| 落地（写 `.rsi/**`、应用 diff） | **Gatekeeper**（确定性代码） | 只按台账允许的状态迁移落盘 |
| 台账 `.rsi/ledger.jsonl` | Gatekeeper（**只追加**） | 其它任何模块不得写 |
| 提案/经验批准、复核签署 | **人**（`actor=human:<非空>`） | 单机流程元数据，不是强鉴权 |
| `~/.dsh/skills/**` 生效位置 | **人**（手工同步） | RSI 进程**永不写** |
| 产品状态 / 闸门 / 用例态 / 基线 | 原 owner（SPEC-01/02/06/07） | RSI 不读不写不改判 |

> **红线**：两个 owner 都能写同一份状态 ⇒ 设计不成立。Reflector 与 Gatekeeper 分离必须由**代码/权限**保证，不能只靠 prompt。

---

## 3 术语

| 术语 | 定义 |
|---|---|
| **一轮** | 默认 = 一次 dsh 会话（`session-<uuid>`，`cwd` = 本仓根）；人可显式结轮并附加 `--label` 切片名。跨切片的会话不自动切分 |
| **RunRecord** | 一轮的只增不改快照 JSON，落 `.rsi/runs/<run_id>.json` |
| **ProposalSet** | 复盘器输出的结构化提议（经验草案 / skill 提案 / 问题单），**提议 ≠ 落地** |
| **提案** | `.rsi/proposals/P-<nnnn>.md`，含 unified diff 与证据原文 |
| **经验** | `.rsi/memory/lessons.md` 中的条目，`draft` / `approved` / `revoked` |
| **问题单** | `.rsi/issues/C-<nnnn>.md`，只描述现象与方向，**不含补丁** |
| **台账** | `.rsi/ledger.jsonl`，唯一状态真相源，页面/INDEX 必须能由它重放 |

---

## 4 RSI-01 触发与 CLI 契约（人工按键，P0 只做 CLI）

- **触发必须是人**：不存在守护进程、cron、会话钩子（dsh 未暴露可依赖的结束钩子，本规格不臆造）。
- 入口统一为 `cd loop && .venv/bin/python -m rsi <子命令>`（复用 `loop/.venv`；不得新增独立部署）。

| 子命令 | 作用 | 写什么 |
|---|---|---|
| `reflect --session <uuid\|latest> [--label <切片名>] [--dry-run]` | 采集 + 两段复盘 + 落地 draft/提案/问题单 + 台账 | `.rsi/**` |
| `review --run <run_id>` | 对上一轮 active 提案产出复核**证据**（不签） | `.rsi/proposals/*` 复核记录 |
| `review-sign --proposal <id> --outcome effective\|ineffective\|untouched --actor human:<name>` | 人签复核结论 | 台账（`actor_kind=human`） |
| `decide --kind proposal --id <id> --decision accepted\|rejected --actor human:<name> [--note]` | 人批准/驳回**提案** | 台账 |
| `decide --kind memory --id <id> --decision approved\|rejected --actor human:<name> [--note]` | 人批准/驳回**经验** | 台账 |
| `decide --kind issue --id <id> --decision confirmed\|rejected --actor human:<name> [--note]` | 人确认/驳回**问题单** | 台账 |
| `apply --proposal <id>` | 只对已 `accepted` 且 `base_sha256` 匹配的提案应用 diff 到仓内副本 | `doc/agents/skills/**`、`doc/agents/subagents/**` + 台账 |
| `sync-record --proposal <id> --global-sha256 <sha256>` | 记录人已完成全局同步 | 台账 |
| `status` | 由台账重放 INDEX 状态 + pending 摘要 | 无（只读） |
| `selftest` | 夹具测试入口（与 pytest 同判据，不另做一套） | 临时目录 |

**退出码**：`0` 成功；`1` 一般失败（含模型/IO）；`2` 前置不满足（会话格式不支持、预算超限、越权路径、`stale`、非法状态迁移、`auto_apply_skill=true`）。**拒绝必须发生在写盘之前。**

**幂等**：同一 `--session` 重复 `reflect` ⇒ 返回既有 run 并报 `already_reflected`（`--dry-run` 除外），不覆盖、不追加第二份 RunRecord。

---

## 5 RSI-02 采集：RunRecord（原文 + 确定性事实）

落 `.rsi/runs/<run_id>.json`，只写一次（已存在则拒绝，`--dry-run` 除外）。

```json
{
  "schema": "rsi/run-record",
  "version": 1,
  "run_id": "run-<YYYYMMDD-HHMMSS>-<session 前 8 位>",
  "session_id": "<uuid>",
  "cwd": "<本仓绝对路径>",
  "dsh": {"version": "...", "bin_sha256": "...", "session_format": 4},
  "session_log": {"path": "...", "bytes": 0, "sha256": "..."},
  "closed_by": "human | last_turn",
  "session_end_observed": true,
  "task_spec": "本轮任务描述原文（首条用户消息，含附件引用，禁止改写）",
  "started_at": "ISO8601", "ended_at": "ISO8601",
  "trajectory": [
    {"step": "...", "agent": "lead|teammate:<name>|subagent", "action": "<工具或动作>",
     "result": "ok|error", "error": "报错摘要，无则省略", "compressed": false}
  ],
  "human_feedback": [
    {"turn": 3, "after_step": "...", "text": "用户原话（逐字）",
     "kind": "correction|evaluation|preference|question", "masked": false}
  ],
  "verification": [{"cmd": "...", "rc": 0, "summary": "输出尾部摘要（不重跑）"}],
  "artifacts": ["改动文件相对路径"],
  "metrics": {"tokens": "unknown", "duration_sec": 0, "llm_calls": "unknown"},
  "prior_active_changes": [{"id": "P-0001", "target_sha256": "..."}],
  "coverage": {"included": ["..."], "omitted": ["..."], "reason": "..."}
}
```

硬性要求：

1. **`human_feedback[].text` 必须原文**：禁止改写、禁止总结。复盘质量的上限由这条决定。
2. **`trajectory` 允许压缩，但失败步骤与被人纠正的步骤不得压缩**（`compressed=false`）。
3. **`metrics.tokens` / `llm_calls` 未知就写 `"unknown"`**，不得伪造数字。
4. **`artifacts` 与 `verification` 由 Host 确定性提取**（git 事实 + 会话里的命令与返回码），不重跑命令、不采信模型转述。
5. **凭据掩码（RSI-02.5）**：对可识别的凭据形态（`api_key`/`token`/`password`/`Authorization`/私钥块等）做**确定性掩码**，`masked=true`，并把掩码事件（位置 + 规则名，**不含被掩值**）记入台账 `note`。掩码只作用于凭据形态，**不得掩掉业务事实**。掩码规则是单点实现（`rsi/redact.py`），可单测；规则不可能穷举，漏网属于已登记风险（§19）。
6. 会话日志读取失败、格式不支持、`zstd` 缺失 ⇒ **显式失败**（退出码 2），**不得产出空轨迹的 RunRecord**。

---

## 6 RSI-03 输入切片、覆盖率与预算

- **最低必含切片**（不可省略）：全部 `human_feedback` 原文、全部失败/返工步骤、全部 `verification`、全部 `prior_active_changes` 及其提案与目标文件快照。
- **可压缩切片**：成功路径轨迹（可压成 step 摘要）。
- **覆盖率显式**：每个请求带 `coverage{included, omitted, reason}`；**禁止静默截断**（SPEC-06 C1 的同一纪律）。
- **预算口径唯一**：按**序列化字节数**计（与 SPEC-06 C1 同一实现 `AM.encoded` 的度量口径），不比 token 猜。
  - 单次请求上限 `reflect_token_budget_bytes`（默认 **200000 bytes**）；
  - 单轮总上限 `reflect_total_budget_bytes`（默认 **800000 bytes**）；
  - 超单次上限 ⇒ **分多次调用**再汇总；超总上限 ⇒ **显式失败**（退出码 2，`budget_exceeded`），不截断、不抽样。
- **量级依据**：本规格实测采样（2026-10-29，命令输出复制，非手算）——本机最近三次会话解压后为 `945402` / `2977125` / `15431643` bytes。按 4 bytes/token **粗估**约 0.25M–4M tokens（估算，仅作量级参考）。
  > 采样值**不是门禁数字**，权威记录见 [`doc/STATUS.md`](../STATUS.md) §138.2；实现后以 STATUS 新增章节更新。
  > 因此**否决**外部文档的 `reflect_token_budget: 20000`：它比真实数据小两个数量级，照做只能靠静默截断。

---

## 7 RSI-04 复盘两段（提议者无写权）

### 段一：无工具单次调用（Host 组输入）

- Host 组装 `RunRecord` + `coverage` + 输出 Schema 与状态枚举，发给模型；模型**只输出结构化 ProposalSet**。
- 输出 Schema 校验失败、字段缺失、枚举非法 ⇒ 整轮失败（不落半件、不"尽量解析"）。
- 每次调用落 `.rsi/runs/<run_id>/calls/reflect-1/{request.json,result.json}`，各自附 sha256，**只写一次**，镜像 SPEC-06 M1 的封存纪律；**不保存认证凭据**。

### 段二：局部只读核验（可选，仅当段一声明 `needs_verification`）

- 用 dsh headless 起一个**只读实例**：`cwd` = 本仓，**不 bind cwd**（其余全盘 `ro-bind`），工具白名单仅 `read`/`glob`/`grep`（**禁** `bash`/`write`/`edit`/`submit_result`）。
- **复用既有唯一实现**：`loop/host/agent_backends/dsh_process.py`（`build_wrap_argv`）与 `dsh_allowlist.py`；**不得出现第二套隔离/白名单实现**（红线 8）。
- 段二只回答"待核验问题清单"，输出核验结论 + 证据位置；不产出提案。
- 记录与段一同构（`calls/reflect-2/`）。

### 模型通路

- 复用 `loop/host/model_provider.py` 的 `resolve()`（唯一 provider 解析实现）；记录 `provider/model`、prompt/schema sha256、实现文件指纹。
- 模型调用失败/超时 ⇒ 按 `on_timeout` 降级为 `memory_only`（只写经验草案），**不得阻塞或影响主开发工作**（这是旁路工具，本就异步）。

---

## 8 RSI-05 落地分层与写权白名单

| 层 | 写什么 | 生效时机 |
|---|---|---|
| **MEMORY** | `.rsi/memory/lessons.md` 追加 `draft` 条目 | **不生效**；人批准后才可被读取 |
| **SKILL** | `.rsi/proposals/P-<nnnn>.md`（unified diff + 证据原文） | 人 `accepted` 后由 `rsi apply` 写到**仓内副本**；人手工同步到 `~/.dsh/skills` 才真正生效 |
| **CODE** | `.rsi/issues/C-<nnnn>.md`（只描述现象与方向，不给补丁） | 永不自动；人确认后才进产品文档 |

**写白名单（代码级，非 prompt）**：

- 允许写：`.rsi/**`（其中 `ledger.jsonl` **只追加**）、`doc/agents/skills/**`、`doc/agents/subagents/**`。
- 禁止写：`~/.dsh/**`、`kb/**`、`doc/spec/**`、`doc/STATUS.md`、`doc/evidence/**`、`doc/history/**`、`ENV_ROOT`、产品 run 目录、`loop/**`。
- 所有写操作经**单一白名单函数**（`rsi/writes.py`）判定；拒绝发生在写盘前；单测必须断言上述禁止面全部被拒。
- **`~/.dsh/skills` 的实际写入只能是人**：RSI 只提供 diff 与同步记录（`sync-record`）。

**提案文件格式**：

```markdown
---
id: P-0001
status: pending
created_from: run-20261029-231500-7d1dcfb5
target: {repo_path: doc/agents/skills/tdd/SKILL.md, base_sha256: "<sha256>", source: "~/.dsh/skills/test-driven-development/SKILL.md @ <sha256>"}
category: 缺少知识 | 规则错误 | 流程顺序
evidence: "用户反馈原文引用，必填，不得为空"
---

## 反事实说明
如果本轮开始前就存在这条规则，哪一步的哪个问题就不会发生。

## Diff
（unified diff，禁止全文重写）

## 复核记录
- run-<id>: 生效 / 无效 / 未触达（人签：<actor>，<ts>）
```

**状态枚举**（单点定义在 `rsi/status.py`，任何脚本/文档不得手抄第二套）：
`pending | accepted | rejected | active | validated | ineffective | reverted | archived | stale`。
（`retained` 等未使用值**不入枚举**：没有消费者的状态不得保留，见 AGENTS §2 硬性纪律 4。）

**副本建立规则**：提案只在需要时才建立仓内副本（从全局 skill 复制 + 记录来源与 sha256，或新建 subagent 模板）；**不批量 vendor** 全局 skill。

---

## 9 RSI-06 审批与台账（不是业务闸门）

- `.rsi/ledger.jsonl` **只追加**，每行一个状态变更：

```json
{"seq": 1, "ts": "ISO8601", "id": "P-0001", "kind": "proposal|memory|issue",
 "from_status": null, "to_status": "pending",
 "actor": "human:<name>|system", "actor_kind": "human|system",
 "run_id": "run-...", "note": "", "prev_sha256": "<前一行 line_sha256 或 64×0>",
 "line_sha256": "<本行规范化 JSON 的 sha256>"}
```

- **重放**：`.rsi/proposals/INDEX.md` 与 `rsi status` 输出必须能由台账重放得到；INDEX 不是第二真相源。重放遇断链/坏行/非法迁移 ⇒ 显式失败。
- **批准必须是人**：`actor` 形如 `human:<非空名称>` 且 `actor_kind=human`；`human` 字段是单机流程元数据，**不是身份认证**（与 SPEC-06 M2 同一口径）。
- **拒绝先于提交**：非法状态迁移、未知 id、非 human actor、越权路径一律拒绝且**不落行**。
- **它不是业务闸门**：不得签 G1/G2/G3/N16，不得写 `gates.json`，枚举**不复用** `kb_lib.GATE_DECISIONS`（红线 4 的反面：业务闸门枚举权威仍唯一）。

---

## 10 RSI-07 复核三态、撤回与漂移

| 判定 | 含义 | 处理 |
|---|---|---|
| **生效** | 本轮触达该场景且同类问题消失 | **人签**；连续 2 次 ⇒ `validated` |
| **无效** | 触达该场景但问题依旧 | **人签**；连续 2 次 ⇒ 自动撤回（`reverted`） |
| **未触达** | 本轮没走到该场景 | 不计数；连续 3 次 ⇒ `archived`（保留文件，不进上下文） |

- **分工**：模型只出**证据**（触达位置、是否复现、指向 `RunRecord` 的具体轮次/步骤）；**生效/无效由人签署**。模型无法指认证据 ⇒ 一律 `untouched`，禁止猜。
- **"未触达"必须单列**：不得计入生效，这是虚假完成状态的主要来源。
- **自动撤回**由 Gatekeeper 执行：按提案 diff 反向应用 → 台账记 `actor=system` 的 `reverted`；经验中对应条目标记失效但**不删除**（保留审计痕迹）。
- **已撤回/已归档的提案不得再次自动应用**；重新提案必须新 id。
- **`stale`（RSI-08）**：目标文件 sha256 与提案记录不符 ⇒ 标 `stale`，不应用、不计生效/无效，等待人重评。

---

## 11 RSI-08 同步与漂移（能证明"真的生效了"）

- 提案记录 `target.base_sha256`（仓内副本）与 `target.source`（全局 skill 路径 + 建副本时 sha256）。
- `rsi apply` 前校验 `base_sha256`；不符 ⇒ `stale`（退出码 2），不写文件。
- 人完成 `~/.dsh/skills` 同步后，用 `rsi sync-record` 把全局 sha256 落台账；**同步是人的动作，机器只记录**。
- 下一轮 `review` 先比 sha256 链（仓内副本 / 全局副本 / dsh 版本与二进制指纹）；任一与记录不符 ⇒ `stale`，**停止判效果**。
- 与红线 10「引用冻结文件必须带 md5、判未改动按内容指纹」同一纪律，本规格用 sha256。

---

## 12 RSI-09 经验消费（必须有消费者）

- **消费者 = Lead**（唯一）：下一次开工时读 `.rsi/memory/lessons.md` 的 `[approved]` 条目 + `.rsi/proposals/INDEX.md` 的 pending 摘要。
- **机制**：P0 实施时在 `AGENTS.md` 增一节「开工前置」，契约文字如下（**本节文字即契约**，实现时逐字加入，由人评审）：

```
### 开工前置（RSI 经验消费）
每次开工（新会话首轮）必须：
1. 读 `.rsi/memory/lessons.md` 中 `[approved]` 条目与 `.rsi/proposals/INDEX.md` 的 pending 摘要；
2. 在开工回报中列出实际读取的条目 id；文件不存在可说明"未配置"，但不许假装读过；
3. 未批准（draft）条目只能作为「待确认候选」提出，不得当作依据；
4. 把某条经验交给子代理时必须引用条目 id。
```

- **不自动注入**：RSI 不修改 AGENTS.md、不往 spawn 提示词里塞经验；注入是 Lead 的动作且必须可追溯（引用 id）。
- **不读未配置文件**：`.rsi/` 不存在时按普通开工执行，不影响任何既有流程。

---

## 13 RSI-10 存储布局与版本化

```
.rsi/
├── runs/            # RunRecord 与调用记录（含会话派生原文）—— 不入 git
├── memory/lessons.md        # 经验库（draft/approved），有上限       —— 入 git
├── proposals/INDEX.md       # 提案索引（由台账重放生成）             —— 入 git
├── proposals/P-<nnnn>.md    # 单提案（含 diff）                      —— 入 git
├── issues/C-<nnnn>.md       # 代码问题单（不含补丁）                 —— 入 git
├── ledger.jsonl             # 台账，只追加                           —— 入 git
├── config.yaml              # 预算、上限、开关                       —— 入 git
├── holdout/tasks.md         # 留出任务清单（P2；禁止用于生成规则）    —— 不入 git
└── README.md                # 布局、入/不入 git 边界、命令速查        —— 入 git
```

- `.gitignore` 增两条：`.rsi/runs/`、`.rsi/holdout/`。
- **`lessons.md` 的"提炼压缩"会合并/删除条目**：这不是"只增不改"的违规——只增不改约束的是 `doc/evidence/**`、`doc/history/**` 与台账；经验库的可压缩性由 git 历史兜底（旧版可回查）。
- **落点**：Python 包 `loop/rsi/`（复用 `loop/.venv` 与 `host.agent_backends` 的隔离实现）。**单向依赖**：`rsi → loop/host` 允许，产品运行期 **禁止 import `rsi`**；以 grep 测试断言。
- 本目录**不得**被产品 `loop/web`、`loop/services`、`kb/` 读取。

---

## 14 RSI-11 可观测性与措辞纪律

- 每次 `reflect` 结束输出一行固定格式（写 `.rsi/runs/<run_id>/reflect.log`，并进 INDEX 顶部）：

```
[RSI] run-20261029-231500-7d1dcfb5 | 归因 2 | draft 经验 +2 | 提案 +1 | 复核: 生效1 无效0 未触达1 | stale 0 | 耗时 41s
```

- **措辞纪律（写进实现要求）**：
  1. 生成提案 ≠ 已改进，只能说"已生成提案"；
  2. 部署成功、测试通过 ≠ 长期收益，不得宣称能力已提升；
  3. 任何"已生效"表述必须有台账中的**人签**复核记录支撑；
  4. **未触达不得计入生效**；
  5. **P0/P1 阶段不得声称收益**（留出集对照是 P2，且未实现）。

---

## 15 RSI-12 内核适配层（已核实，不臆造）

外部文档 §3.3 的四个"待实现方核实"条目，本机已核实如下（实测 2026-10-29）：

| 问题 | 核实结论 |
|---|---|
| 如何在 run 终态注册回调 | **不存在可依赖的钩子**。改为**人工按键触发**（§4）；不臆造事件 API |
| 如何取到用户消息（含轮次/步骤对应） | 会话日志 `~/.dsh/sessions/<cwd 编码>/session-<uuid>/session.v4.jsonl.zstd`。格式：zstd 压缩 JSONL；首行 `{"type":"session","version":4,"cwd":"..."}`。**用首行 `cwd` 匹配本仓，不反推目录编码** |
| 如何以受限权限再启动一次 LLM 调用 | 段一：`model_provider.resolve()` 无工具单次调用；段二：dsh headless + `dsh_process.build_wrap_argv`（不 bind cwd）+ `dsh_allowlist`（`read/glob/grep`） |
| skill 的实际存放位置与加载机制 | 全局 `~/.dsh/skills/<name>/SKILL.md`（**工作区外、跨项目共享、RSI 永不写**）；仓内副本 `doc/agents/skills/<name>/SKILL.md` 为 diff 对象；subagent 模板 `doc/agents/subagents/<name>.md` |

**版本与失败语义**：

- `session_format != 4` ⇒ 显式失败 `unsupported_session_format`（退出码 2）；**不得**降级成空轨迹或"尽力解析"。
- 解压依赖系统 `zstd` 可执行（本机实测无 Python `zstandard` 模块）；缺失 ⇒ 显式失败 `zstd_missing`（退出码 2）。
- 会话结束标记缺失 ⇒ `session_end_observed=false`，允许复盘但必须在 RunRecord 与摘要行标注。
- 记录 `dsh.version` 与 `dsh.bin_sha256`；任一变化使适配层指纹变化，纳入 `stale` 判据（不自动重跑）。

---

## 16 RSI-13 防污染与预算默认值

`.rsi/config.yaml`（全部给默认值；文件缺失按默认值，不因缺配置失败）：

```yaml
max_skill_proposals_per_run: 3
lessons_max_lines: 200            # 超限触发提炼压缩（合并同类、删除被取代条目），不是无限追加
duplicate_suppression_runs: 3     # 同一根因 3 轮内不重复提案
reflect_token_budget_bytes: 200000   # 单次请求（序列化字节，非 token 估算）
reflect_total_budget_bytes: 800000   # 单轮总量；超限显式失败
reflect_timeout_sec: 300
on_timeout: memory_only           # 超时降级为只写经验草案
auto_apply_skill: false           # 恒 false；配置为 true ⇒ 显式拒绝启动（exit 2）
reviewer_enabled: true
holdout_eval_every_n_runs: 5      # P2 生效；P0/P1 不读该键
```

- **经验库必须有上限**：无限追加会让信噪比逐轮下降。
- 去重按**根因指纹**（归因类别 + 涉及步骤/文件类别）在最近 N 轮内抑制，而非按文本相似度。

---

## 17 分期与完成判据

| 阶段 | 内容 | 完成判据（全部满足才算闭合） |
|---|---|---|
| **P0 最小闭环** | CLI 触发 + RunRecord 采集 + 两段复盘 + draft 经验 + 提案落盘 + 问题单 + 台账 + 人批准/驳回 | ① `pytest tests/test_rsi_*.py` 全绿；② **3 次真实会话** `reflect` 均产出 RunRecord/draft/（若有）提案/台账行；③ **未批准时被控文件字节不变**（sha256 前后一致）；④ 批准后 `apply` 能应用且 `git checkout` 可回滚；⑤ `status` 能由台账重放出 INDEX；⑥ 夹具注入假凭据 ⇒ 落盘与请求中无该值、台账有掩码事件 |
| **P1 复核回滚** | 三态（人签）+ 自动撤回 + 经验上限提炼 + 摘要日志 | 构造一条故意无效提案 ⇒ 人签 2 次无效 ⇒ 自动撤回且台账完整；超 200 行触发提炼且 git 历史保留旧版 |
| **P2 验证增强** | 留出集对照 + 问题单流转 + 沙箱验证后才允许代码提案 | 留出集上有前后对照数据；**在此之前不得声称收益**（§19 未决 3） |

> **建议先只做 P0 跑一周。** 没有真实反馈数据之前，P1/P2 的复杂度都是猜测。

---

## 18 可判定验收

| 条款 | 判据（不读源码也能判定） |
|---|---|
| RSI-01 | 无 cron/守护进程；`reflect` 重复同一 session 返回 `already_reflected`；越权路径退出码 2 且文件未变 |
| RSI-02 | `human_feedback.text` 与用户原话逐字一致；失败步骤 `compressed=false`；`metrics` 未知为 `"unknown"`；掩码夹具下无明文凭据 |
| RSI-03 | 每请求带 `coverage`；人为构造超预算 ⇒ 分多次或显式失败，**不出现**"输入被裁而 coverage 说完整" |
| RSI-04 | Reflector 进程无写权（段一无工具、段二只读实例）；Schema 非法 ⇒ 无任何 `.rsi` 落地 |
| RSI-05 | 禁止写面单测全被拒；`~/.dsh/skills` 全程 sha256 不变 |
| RSI-06 | 台账只追加；删/改历史行 ⇒ 重放失败；非法迁移不落行；`actor_kind` 非 human 的批准被拒 |
| RSI-07 | 三态枚举唯一；未触达不计生效；2 次人签无效 ⇒ 自动撤回；撤回后条目不删除 |
| RSI-08 | `base_sha256` 不符 ⇒ `stale` 且不写文件；`sync-record` 后复核用全局 sha256 |
| RSI-09 | AGENTS.md 含"开工前置"三条；`.rsi/` 不存在时开工不受影响 |
| RSI-10 | `.gitignore` 两行生效；`grep` 断言产品运行期不 import `rsi` |
| RSI-11 | 摘要行格式固定；措辞纪律进入实现要求；P0/P1 无收益声明 |
| RSI-12 | `session_format=5` 夹具 ⇒ 退出码 2；无 `zstd` ⇒ 退出码 2；无结束标记 ⇒ 标注 `session_end_observed=false` |
| RSI-13 | `auto_apply_skill: true` ⇒ 拒绝启动；提案超 3 条 ⇒ 按证据强度保留前 3 条并在记录中写明取舍（不得静默丢弃） |

---

## 19 未决与验证边界

1. **会话格式演进**：`session.v4` → v5 的兼容策略未定；本规格只保证**fail-closed**（显式失败，不静默降级）。适配层指纹变化后必须重评。
2. **模型自审独立性**：Reflector 与开发者可能同模型家族，RSI 结论**不构成** `AGENTS.md` §9 的独立验证；不得用 RSI 记录替代独立验证者意见。
3. **留出集（holdout）**：登记为 P2，**未实现、未验证**；P0/P1 只能声称"已生成提案/已入库"，不得声称能力提升。开发侧任务异质，"盲对照"本身存疑，届时需单独契约。
4. **会话结束标记**：部分会话日志可能不含结束标记；本规格允许在标注后复盘，但这类 RunRecord 的归因证据强度较低，复核时应优先 `untouched`。
5. **掩码不可能穷举**：凭据形态规则有限，漏网属已登记风险；**不得声称已完全脱敏**。
6. **落点裁定**：`loop/rsi/` 为规格作者裁定（复用 venv 与隔离实现、单向依赖），**待评审**；若实现时发现循环依赖，迁移须留 MIGRATION 记录并改本节。
7. **单机单用户**：批准元数据不是强鉴权；多人协作/跨机审批不在本期。

---

## 20 实施期决策记录

（由实现方追加：日期 / 决策 / 理由 / 可回滚方式）

| 日期 | 决策 | 理由 | 回滚方式 |
|---|---|---|---|
| — | — | — | — |

---

## 附：决策追溯（本轮访谈 20 条 → 条款）

| # | 决策 | 落点 |
|---|---|---|
| 1 | 迭代对象 = 开发侧 Agent 工作流（Lead+subagent+skill） | §1 |
| 2 | SKILL 仓内副本为 diff 对象，人批准后同步全局 | §8、§11 |
| 3 | 一轮 = 一次会话，人可显式结轮 | §3、§4 |
| 4 | 人工按键触发 | §4 |
| 5 | P0 只做 CLI，按钮后置 | §4 |
| 6 | 经验自动写 `draft`，批准后才进上下文 | §8、§12 |
| 7 | RSI 自建台账，明确不是业务闸门 | §9 |
| 8 | 经验/提案/台账入 git；runs/holdout 不入 | §13 |
| 9 | 模型出证据、人签生效/无效；2 次无效自动撤回 | §10 |
| 10 | Reflector 无工具 + 局部只读核验 | §7 |
| 11 | 段二用 dsh 只读实例，复用 bwrap + 白名单 | §7、§15 |
| 12 | 本轮只出规格（计划后置） | 本文件；P0 计划待确认后另立 `doc/plans/` |
| 13 | 并行支线；首批真实 run = 修缺陷批次 | §17 |
| 14 | 原文保留 + 确定性凭据掩码 | §5 |
| 15 | 确定性切片 + 覆盖率 + 超限分次，禁止静默截断 | §6 |
| 16 | P0 验收 = 夹具全绿 + 3 次真实会话 + 未批不变/批后可回滚 | §17 |
| 17 | 问题单只落 `.rsi/issues/`，人确认后才进产品文档 | §8 |
| 18 | holdout 登记 P2，P0/P1 不声称收益 | §19 |
| 19 | base_sha256 + 同步落账 + 变则 stale | §11 |
| 20 | 经验消费者 = Lead，AGENTS.md 开工前置 | §12 |
