# SPEC-02 · 变更影响闭环 · 编排层规格书（ORCHESTRATION SPEC）

> 编号：**SPEC-02**（文件名不变；编号与修订记录见 [SPEC-REV-01](SPEC-REV-01-20261022.md)）。

> Agent 请求边界控制见 [AGENT_WINDOW_SPEC.md](AGENT_WINDOW_SPEC.md)。控制器只包围模型请求，不重放下游副作用、不改 TriggerFlow 拓扑或闸门；暂停限当前进程，重启后历史只读。

> **状态**：v0.1 · 已实现（P0）；实现审计见 `doc/audit/AUDIT-20261019-spec-conformance.md`。
> **上游**：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md` v0.2（业务与不变量 I1–I8、16 节点 N0–N16、三道人工闸门）。
> **本件定位**：上游是**业务契约**，本件是它的**机制契约**——把 N0–N16 落到具体 owner
> （Host 确定性程序 / ModelRequest / TriggerFlow / 人工闸门 / 外部容量），并定死
> **一次运行的生命周期、长任务停等、单槽准入、重启恢复、进度投影、UI 投影**六件事。
> **本件仍不是实现**：实现落到 `loop/` 下对应 owner 的代码。
> **本文语言**：中文正文；代码、路径、标识符、md5、命令原文、日志原文保留原文。

---

## 0. 为什么需要这一层

上游 §12 明确写着「**本件是跨 owner 的设计契约，不是调度器/TriggerFlow 定义/重试引擎实现**」。
反过来读：上游**故意留下了**「谁来调度、谁来持闸门中断、谁来容错重启」这个空洞。

没有这一层会发生的具体后果（本轮演练已实证，见
`doc/spec/evidence/loop_rehearsal/REHEARSAL_REPORT.md` 与
`doc/spec/evidence/loop_rehearsal/verify/V0_verdict.md`）：

| 缺失能力 | 本轮实证到的后果 |
|---|---|
| 闸门中断的**权威持有者** | 闸门态写成 JSON 文件 + `anchor`，但无人持中断 ⇒ 「谁在等、等到谁、能否重启」无法回答 |
| **长任务与执行生命周期**解耦 | 一次全跑实测 `Elapsed 1140.79s`（≈19 min），修订后规模可达 22.8 h；阻塞式 handler 会让执行快照在 `running` 帧上**拒绝 load** |
| **单槽准入的外部 owner** | 缺陷 N9-3：锁格式变更后陈旧判定读错字段 ⇒ 活动锁被误删 ⇒ 约 10 分钟无互斥 |
| **进度投影** | 进度只能靠人读日志；`*E` 文本计数 1687 与 UVM 汇总 `UVM_ERROR=0` **两套口径分歧**无法在界面上并列呈现 |
| **重启语义** | 「挂起的 Python 帧不是恢复契约」（`agently-triggerflow/references/recovery.md`）——进程一断，闭环态归零 |

---

## 1. 机制 owner 账本

> 规则：**每个能力恰好一个 owner**。两个 owner 都能写同一份状态 ⇒ 立即判设计不成立。

| Owner | 承载 | 明确**不**负责 |
|---|---|---|
| `loop/workflows/main_flow.py` | 稳定拓扑（N0–N16 的边、扇出、汇合、回边）、一次运行的生命周期、`create_execution(auto_close=False)` | 不写业务判定；不写 Prompt；不做准入 |
| `loop/workflows/chunks/*.py` | 每个可观测阶段（Host 确定性 or ModelRequest） | 不实现重试循环；不吞异常换默认值 |
| `loop/prompts/*.yaml` | 模型节点的 `input`/`info`/`instruct`/`output` 契约 | 不持有状态 |
| **`kb/tools/*.py`（既有，只读）** | **业务权威**：闸门态 + `anchor`、N2 diff、N5 影响、N16 晋升、用例态 | 不知道 TriggerFlow 存在 |
| `loop/host/admission.py` | **单槽准入 / 队列 / 取消**（外部容量 owner） | 不决定业务是否继续 |
| `loop/host/job_runner.py` | 长任务提交、看护、重附着、取消送达 | 不写执行状态（只返回 ref，由 chunk 写） |
| `loop/host/agent_memory.py` | 上下文预算、模型调用记录、人工确认经验筛选（见 [上下文与记忆契约](AGENT_CONTEXT_SPEC.md)） | 不签署、不晋升、不作为执行恢复或业务通过权威 |
| `loop/host/progress.py` | 稳定应用事件投影 | 不作为权威（只投影，不回写） |
| `loop/services/contracts.py` | 对外投影（闸门材料 / 看板项 / 运行摘要） | 不泄露 raw event、内部 metadata |
| `loop/services/api.py` | FastAPI 准入与 HTTP 投影（ExecutionExchange 适配器） | **不实现自己状态机** |
| `loop/web/` | v1 闸门操作台 + 长任务看板（只读投影 + 4 个写动作，见 §10.0） | 不编辑 `TESTLIB/` |
| `RecordStore`（框架） | 执行快照的**物理留存** | 不承担业务持久化 |
| `TaskWorkspace`（框架） | 运行目录/文件 | 不承担快照语义 |

**反模式（明令禁止）**：

1. **在 UI 旁边再建一个状态机**。「不要在有 TriggerFlow 的项目里加一套并行执行拓扑」——UI 必须挂在
   TriggerFlow 的 interrupt/resume 账本上。
2. **把 TriggerFlow 并发当成仿真并发**。`uvs.setup` 是仓库根下全局单文件（`doc/AGENTS.md` §2 卡点 D），
   所以同工作目录内**最多一个仿真/编译**——这必须是 **host 持有的单槽**，不是 `concurrency=N`。
3. **闸门态双写**。闸门权威在 `kb/tools/gate.py` 的 gate_state + `anchor` + `history[]`；
   TriggerFlow 只持**中断**，UI 只做**传输**。三者不得各存一份「已通过」。
4. **把 raw parser 路径当日志协议暴露给前端**（`agently-triggerflow/references/stream-bridge` 要求
   翻译为稳定应用事件，且临时项必须与最终校验值对账）。

---

## 2. 不变量 → owner 落点（上游 I1–I8）

| # | 不变式（上游原文摘要） | 机制 owner | 落点 |
|---|---|---|---|
| I1 | 差异条目无未决项才可进入修订 | 闸门1 pause chunk + `kb/tools/gate.py` | `gates.py::gate1` 放行前读 gate_state，未决>0 则拒绝 resume |
| I2 | 受影响用例态 ∈ {未改/已修订待验/已验证通过/已退回}；有「待验」不得称跑通 | N16 前置 + `kb/tools/case_state.py` | N16 读 `case_states.json`，存在「已修订待验」⇒ rc=3 |
| I3 | 跑通 = 编译 rc=0 ∧ 静态卡点C ∧ 全跑有完整 UVM 汇总 ∧ **两套口径均为 0** ∧ 观测点印记计数三向一致 | 结果对账 chunk | **双计数并列**：口径一（`*E` 文本计数）与口径二（UVM 汇总）分别取、分别存、**永不互相替代** |
| I4 | 冲突清单未清零不发版 | 闸门2/3 + N16 | N16 读 `<WORKSPACE_ROOT>/conflicts/conflicts.json`，任一 `blocks_release=true` ⇒ 拒绝 |
| I5 | 每步证据带身份，归档只增不改 | `kb/tools/n1_snapshot.py` + RecordStore | manifest/anchor 冻结，快照留存 |
| I6 | 三道闸门都必须显式通过，模型不得越过 | 闸门 pause chunk | `actor_kind` 必须为 `human`；模型/演练 actor 在 `require-signed` 下被拒（F-GATE-01 已实现） |
| I7 | 返工有界 | `main_flow` 显式回边 | N6↔N8 回边计数 `n6_n8_cycles`，超限升级 N13；N16 二次校验（F-I7-01 已实现） |
| I8 | 收敛后可原子晋升新基线 | `kb/tools/n16_promote.py` | 目标已存在 `manifest.json` ⇒ rc=3 且零副作用（F-N16-01/02 已实现） |

**验收含义**：上表中每一行都必须在测试里有**一条对应断言**，且该断言必须能在**不读源码**的情况下
从运行产物判定（对齐上游 DoD 的「靠人更小心 ⇒ 判未沉淀」口径）。

---

## 3. 节点账本

| 节点 | owner | 输入契约 | 输出契约 | 生命周期 / 失败 |
|---|---|---|---|---|
| N0 选基线 | Host | `--baseline`、`--now`/`KB_NOW` | `run_id`、`run_dir` | 目录非法即拒（F-GATE-04 已实现 `RUN-YYYYMMDD-HHMMSS` 校验） |
| N1 快照/manifest | Host | 基线目录、`--now` | `manifest.json`（含 `parent` 链） | 失败清理半成品（已实现） |
| N2 diff | Host | 新旧 manifest | `n2_diff.json` | rc=3 为「有差异」业务码，非错误 |
| N3 差异摘要 | ModelRequest | `n2_diff.json` | 分组摘要 | 解析失败结束执行，不伪造 |
| **N4 闸门1** | 人工 | 差异清单 + 冲突快照 | 决策（确认/忽略+理由/转人工） | `pause_for`；未决>0 拒绝放行 |
| N5 影响分析 | Host | 已确认差异 + 索引 | `n5_impact.json` | rc=3 业务码 |
| N6 修订/补充 | ModelRequest + Host | 受影响子集 + 逐条目标（case/file/md5/excerpt 带行号 + `revision_points` + `doc_bitdef` + **`rtl_change`**（N2 的 RTL 新增/删除行与 offset）+ **`api_semantics`**（TB/TESTLIB 中 callee 的 signature+body）+ **`rtl_effect`**（Host 从 RTL 截断解析的 retained_mask/cleared_mask）） | 修订 `edits[{line,old,new,basis}]` + 作者说明；Host `n6_apply` 写入 `<run>/sandbox/TESTLIB/` 并冻结 `md5_after` | 期望值以 `rtl_change` 的新行为为准，并按 `rtl_effect` 计算（`期望 = 写入值 & retained_mask`）；用 `api_semantics` 的**参数名**定位期望/掩码实参；`doc_bitdef` 未同步时在 basis 标 `doc_out_of_sync`（冲突交 N12/G2 暴露）；**地址实参/写入值/初始值不动**，十六进制用 `'h…`；缺依据/非唯一 old 行/行号不符 ⇒ fail closed；写权不落 `TESTLIB/` |
| N7 编译（约 2 s） | Host | 沙箱用例 | rc + 编译日志 | `run_guarded.sh --mode compile-only`（身份头/先归档再删/串行锁）经单槽准入；short lease，异常也 release |
| N8 检查 | ModelRequest | 沙箱用例 + 卡点C + `applied_edits`（本轮改动行） | 通过 / 退回 + 逐条依据；`static_check` 写台账 | 复核必须读代码/日志（`plan_only` 已删）；**checklist 只判本轮 edits 触及的行**（既有代码问题记 notes/defect，不作退回依据）；按 `api_semantics` 校验实参角色（期望掩码 vs 初始值）、按 `rtl_effect` 复算期望值；`doc_out_of_sync` 记 finding 不单独退回；`sandbox_cases` 按 `N8_SANDBOX_BUDGET_BYTES` 确定性分片，每件带 `coverage`（F16，见上下文规格 C1）；证据不足/校验失败 ⇒ node_failed；退回 ⇒ 显式回边到 N6 |
| N9 全跑（实测 ≈19 min/用例） | Host | `n6_applied` 目标集（不是硬编码单例） | 单作业覆盖全部目标用例的 run 证据（日志/耗时/双计数/印记/identity 四方同值） | **不阻塞**：提交**一个**串行作业（`run_guarded.sh --mode full`）→ `pause_for` 停等 → 完成事件 resume；目标/沙箱/md5 缺失或证据目录缺失 ⇒ fail closed |
| N10 结果对账 | ModelRequest + Host | N9 证据（`aggregate_evidence`） | FAIL 三分类；`reconcile.md` 落盘；分类 2/3 经 `n10_pending.py` 进 `pending.json` 的 `n10_items` | drill/real 都落 run_dir；待裁决只经单一写者追加，D1—D20 与 `expected_total` 不变 |
| N11 评估 | ModelRequest + Host | 对账 + 用例态 + 证据身份（run_id/case/md5/seed 四方同值） | `chain=intact|broken` + 返工需求 | **Host 事实优先**：身份不一致或模型声称 intact 与 Host 证据矛盾 ⇒ 强制 `broken`；`>= limit` ⇒ `N11_ESCALATE` 升级闸门2；返工 ⇒ 显式回边到 N6 |
| N12 报告 | ModelRequest | 全轮证据 | 报告草稿 | 数字一律引用产物，禁手算 |
| **N13 闸门2** | 人工 | 报告 + 用例态 + 返工计数 | accept / rework | `pause_for`；rework ⇒ 回 N6 且计数+1 |
| **N14 闸门3** | 人工 | 评估结论 + 冲突态 + I7 计数 | 权威枚举 `full_now / subset_only / milestone_only / defer` | `pause_for`；I4：冲突未清零时 `full_now`/`subset_only` 在**提交前**被拒；`defer` ⇒ 显式 HALT（不晋升） |
| N15 分层回归 | Host | G3 决策 + 用例集 | 每用例证据（最终态，非 provisional） | 先 `n15_select` 选目标集，再 `n15_run` 提交**一个**串行作业经单槽；drill 为显式 no-op；不再 `for_each`/`n15_case` 假进度 |
| N16 晋升基线 | **人触发 + Host** | 轮结果 + 冲突态 + 用例态 + G3 签署记录 | `v(n+1)(parent=v(n))`；`promote_result.json` | 图内节点默认 dry-run；真实晋升必须 `--promote` 且 `--trigger-by/--actor-kind` 与 G3 逐字一致（human），I4 无条件、I2 待验阻断、I7 `>=limit` 拒绝；前置不过 ⇒ rc=3 零副作用 |

### 3.1 基线准入与身份（F01）

**唯一判据**：`<WORKSPACE_ROOT>/baselines/<id>` 同时满足下列 6 条才算 `valid`。判据只有一处实现
（`loop/host/baseline.py`）：只读列表与运行创建**共用同一函数**，不得各写一份近似规则（红线 8）。

1. `id` 匹配 `^v[0-9]+$`；目录存在且不是符号链接。
2. `manifest.json` 存在、是 JSON 对象，并通过 `kb/schema/manifest.schema.json`（`kb_lib.validate`，权威不手抄）。
3. 身份一致：`manifest.baseline == <id>`。
4. **七件套齐全**：manifest 声明路径可解析且落盘存在，声明指纹与实际内容一致——
   `rtl_snapshot`（含 `rtl_files.md5` 的 `manifest_sha256`）、`allfiles_manifest`、`doc_fingerprint`、
   `cases_freeze`、`conflicts_snapshot`、`evidence_index`。清单内路径按环境仓根书写，
   解析顺序 `<WORKSPACE_ROOT>/<path>` → `<WORKSPACE_ROOT>/../<path>`。
   **统一边界判据（R2，2026-10-22）**：无论清单写绝对路径还是相对路径，候选都先 `resolve()`
   （跟随符号链接）再判定必须落在允许根集合内（`<WORKSPACE_ROOT>`、其父、环境根），**然后**才读取/哈希；
   `..` 越界、相对符号链接逃逸、断链/循环链接与绝对越界使用**同一条**判据，不得出现第二套近似规则。
   越界 ⇒ 该件按 `missing`/`errors` 计入并拒绝，且准入零副作用（不写 run、作业、事件）。
   **解码失败隔离（R3，2026-10-22）**：manifest 非 UTF-8 的解码失败归入**该条** `errors`，
   同目录其它基线仍可列出；不得用 `errors="ignore"` 改写清单内容来掩盖。
5. parent 链可回放：`parent` 为 `null`（v0）或指向另一个 `valid` 基线；成环、超深、指向未知版本即拒。
6. **只读**：准入过程不写任何文件（不落临时件、不写字节码）。

**准入时点**：`real` 模式在**创建运行目录、隔离残留投影、写事件流、申请单槽之前**完成准入；
不通过 ⇒ `ValueError`（HTTP 400），零副作用。`drill` 不读基线资产（走夹具），不做准入，
但 `baseline` 仍按原样记录，不能据此声称基线已验证。

**身份贯穿**：选中身份只在入口解析一次（`RunDoc.baseline`）→ N0 写入 `run_meta.baseline`
→ N1 `--parent` → N2 `--from-baseline` → 运行投影与闸门材料。任何节点不得再出现硬编码 `v0`。
缺省（`baseline=None`）语义固定为 `v0`；`v0` 不存在或不完整 ⇒ 拒绝，**不猜其他版本**。

**失败语义**：`missing` 列缺失件、`errors` 列结构性违规（schema / 身份 / 指纹 / parent 链），
二者都不得用空数组冒充成功；列表端点对坏件返回 `valid=false` + 原因，**不抛 500**。

---

## 4. 边账本

| 来源 | 变换 / 校验 | 消费方 |
|---|---|---|
| `n2_diff.json` 条目 | 条目 id 唯一性 + 未决判定 | 闸门1 材料、N3、N5 |
| 闸门1 决策 | `actor_kind` 校验 + `history[]` 追加 + `anchor` 更新 | N5 输入 |
| `n5_impact.json` 受影响子集 | 非空校验 | N6 派发 |
| N6 产出 | 沙箱路径（禁越界写） | N7 → N8 |
| N8 退回依据 | 逐条依据非空 + 代码级复核（`plan_only` 已删） | 回边计数 `n6_n8_cycles` |
| `n6_n8_cycles` | **`>= limit`** ⇒ 拒绝 N16 并升级 N13 人工裁决（I7） | N13 升级人工 |
| N9 证据 | 双计数分别取 + 印记三向一致校验 + identity 四方同值（run_id/case/md5/seed） | N10 对账 / N11 守护 |
| 闸门2 决策 | `actor_kind` + 计数快照 | N11 / 回边 |
| 闸门3 决策 | 冲突清零校验（选 `full_now`/`subset_only` 时，提交前） | N15 / N16 |
| N16 前置 | `case_states.json` 无「已修订待验」（本轮）∧ 冲突无 `blocks_release` ∧ 两类回边均 `>= limit` 拒绝 ∧ 身份与 G3 逐字一致 ∧ 无残留 `manifest.json` | 晋升或 rc=3 |

---

## 5. 三闸门契约（TriggerFlow 中断 + 业务权威分离）

```python
# 形状（不是最终代码）：显式 pause chunk + 前置校验，人工审批用 when(...) 预定路由
async def gate1(data):
    state = read_gate_state("gate1")          # 权威：kb/tools/gate.py
    if state.pending > 0:
        raise GatePreconditionFailed(...)      # I1：未决不得进入修订
    return await data.pause_for(               # durable interrupt
        kind="gate_decision",
        payload=build_gate_material("gate1"),  # 只放材料，不放权限
        resume_to="next",
    )

main_flow.when(...).to(gate1).to(n5_impact)
```

契约条款：

1. **中断归属** TriggerFlow（`pause_for` 为 durable graph interrupt）；**决策权威**归
   `kb/tools/gate.py`（gate_state + `history[]` + `gates.sha256` + `anchor`）。
2. **恢复只对根执行**：子流程的中断投影到根；调用方持 `root_execution_id` 与
   `root_interrupt_id`，用 `continue_with(...)` 恢复（`recovery.md`）。
3. **幂等**：`resume_request_id` 必须稳定；重复提交同一 id 不得产生第二次副作用。
4. **不可越权**：`actor_kind != human` 在 `require-signed` 下被拒（F-GATE-01，已实现并有对抗测试）；
   非 human 不得覆盖 human 签名（F-GATE-02）。
5. **篡改可检出**：`gates.sha256` 与落盘不符 ⇒ rc=3（F-GATE-03）；legacy（无 anchor）只告警。
6. **闸门材料必须并列双计数**，且**界面上不存在"只凭 UVM 汇总就放行"的交互路径**。
7. **决策枚举不手抄**，唯一来源是 `kb_lib.GATE_DECISIONS`：

   | 闸门 | 权威枚举 | `pending` |
   |---|---|---|
   | `G1_diff_confirm` | `confirmed` / `ignored` / `disputed` / **`pending`** | 状态，非可提交动作 |
   | `G2_report_accept` | `accept` / `rework` / **`pending`** | 同上 |
   | `G3_regression_decision` | `full_now` / `subset_only` / `milestone_only` / `defer` / **`pending`** | 同上 |

   实现须从 `kb_lib` 导入并经启动自检比对（`chunks/gates.validate_branches()`）；
   界面按钮由服务端下发（`run_view.gate_options`），前端不得写死枚举。

8. **拒绝必须发生在提交前**。`pause_for(resume_to="self")` 的 `max_resumes=1`：
   若 I6/I4 阻断发生在恢复之后，用户的一次误选会消耗中断并把执行打成 `failed`
   （实测 `self_resume_limit_reached`），**闸门从此不可用**。
   因此 `RunManager.decide()` 必须先判 actor 与 I4，再签署、再恢复。

9. **终态必须释放单槽**（成功 / 失败 / 取消），且幂等。缺此一步会把「一个 run 失败」
   放大成「后续全部卡在 `SLOT:` 中断」。

---

## 6. 长任务停等契约（本层最关键的一条）

**约束来源**：`agently-triggerflow/references/recovery.md:75-77`——快照中若存在
`running` / `cancel_requested` 帧，**load 会 fail-closed**。
所以：**长 Host 阶段绝不可写成阻塞 handler**，否则重启恢复不成立、单槽锁不可见、进度无流。

**规定形状**（N7 短任务可直接内联；N9/N15 必须走此形状）：

```
n9_sim chunk                       park chunk                      job_runner 看护
──────────────                     ──────────                      ─────────────
1. admission.acquire()  ← 单槽
2. job = job_runner.submit()
3. set_state("n9_job", {job_id,   4. pause_for(kind="job_done",    5. 作业结束 →
   log_path, tc, seed})               payload={job_id}, resume_to=      continue_with(
4. return {"status":"submitted"}      "next")                          interrupt_id,
                                                                       {job_id, rc})
   此时执行处于 interrupt（非 running）⇒ save/load 合法
```

6. **resume 载荷只作提示，权威在日志**：恢复后的下游 chunk 必须**回读日志**重新取
   口径一/口径二/印记，**不得信任 resume payload 里的数字**（否则外部可伪造跑通）。
7. **崩溃重附着**：恢复后 `job_runner.lookup(job_id)` 重新附着到仍在跑的作业；
   作业已死 ⇒ 记 dead job，走 N9 失败分支（本轮演练已有死任务夹具，须覆盖）。
8. **释放单槽**：无论成功/失败/取消，释放动作必须在**终态**执行且幂等。

---

## 7. 单槽准入契约

| 项 | 规定 |
|---|---|
| 单槽 owner | `loop/host/admission.py`（**不是** TriggerFlow 并发） |
| 锁文件 | `loop/state/slot.lock`，字段含 `format_version` / `owner_pid` / `job_id` / `tc` / `seed` / `start_ts` |
| **N9-3 修复** | 陈旧判定**按 `format_version` 决定解析哪些字段**；禁止用新格式去读旧锁（本轮实证：误删活动锁约 10 分钟无互斥） |
| 队列 | FIFO，落盘 `loop/state/queue.json`；看板显示位次 |
| ETA | 依据实测吞吐 **≈3.78–3.80 µs sim / 1 s wall（n=2）**；n=2 必须显式标注为低置信 |
| 取消 | `cancel_requested` 标记 + 送达进程组；取消后必须释放单槽 |
| 并行例外 | 只有 N15（经 `run_tc.py`，5 机 × 2 LIC）是跨机并行，不受本槽约束 |

**禁用估算**：「笔数 × 单笔墙钟」的估法在本工程**错约 40 倍**（已实证），不得用于 ETA。

---

## 8. 恢复与重启契约

1. `create_execution(auto_close=False)`；`async_save(record_store)` 落 `loop/state/recovery/`。
2. `RecordStore("./recovery", mode="read_write", snapshot_retention={"keep_last": N})`；
   执行级覆盖用 `set_snapshot_retention_policy(keep_last=…)`（执行级优先且跨 save/load 存活）。
3. 终态历史过大时用 `set_snapshot_projection_policy(terminal_value_mode="digest", min_value_bytes=4096)`
   ——**投影而非删字段**，且它会保留 pending interrupt 与未完成 resume 记录。
4. **保存前必须 `require_idle=True`**；执行活跃时保存会被推迟。
5. `load` 前校验：pending/不健康的必需资源**不算 ready**；外部系统（单槽锁、作业）自带
   ref/lease/fence，恢复时必须**重新验证**后再续跑（`recovery.md`）。
6. **能力声明边界**：本地 RecordStore 只证明**本机重启**；不得宣称分布式恢复
   （无真实共享 provider 与运行证据）。
7. **恢复后行为必须落在**下游 chunk / 显式 resume 事件 / `data.is_resume` 分支里，
   **不得依赖挂起的 Python 帧**。
8. **`resume_to` 选错会静默丢结局**：长任务停放必须用 `resume_to="self"`。
   用 `"next"` 时 `pause_for` 的返回值是**中断描述符**而非恢复载荷，
   停放 chunk 永远看不到作业结局 ⇒ 死任务被当成继续（实测真 bug）。

---

## 9. 进度流投影契约

- 载体：稳定应用事件 `{seq, ts, run_id, node, kind, status, refs}`。
- `kind` 白名单：`node_started` / `node_finished` / `job_submitted` / `job_progress` /
  `gate_pending` / `gate_decided` / `warning` / `dead_job`。
- **禁止**把 raw parser 路径作为前端协议；日志原文只以 `refs`（路径 + 行号）出现。
- **临时项对账**：`job_progress` 的计数是临时值，终态必须用最终校验值覆盖并标注
  `provisional=false`（stream bridge 要求）。
- 事件流**不是权威**：任何判绿/判红都必须能追到 `kb/` 或 run 目录里的产物。

---

## 10. UI 投影契约（v1 = 闸门操作台 + 长任务看板）

**v1 范围**：单机单用户。**允许的写动作恰好四个**（全部经服务端校验，前端只传输）：

| # | 动作 | 端点 | 权威校验（拒绝发生在任何写盘之前） |
|---|---|---|---|
| ① | 提交闸门决策 | `POST /api/runs/{run_id}/gates/{gate_id}/decision` | actor 必须以 `human` 开头（I6）；枚举 ∈ `kb_lib.GATE_DECISIONS`；I4/I1/I2 前置；拒绝不消耗中断、不写账本 |
| ② | 取消作业 | `POST /api/runs/{run_id}/jobs/{job_id}/cancel` | 作业存在且未终态；送达后由 `JobRunner` 记权威相位 |
| ③ | 新建运行 | `POST /api/runs` | `project` 必须等于进程 `ENV_ROOT`（跨环境须重启）；`mode ∈ {drill, real}`；`scenario` 见 `SCENARIOS`；run_id 必须唯一 |
| ④ | 人触发晋升（N16/I8） | `POST /api/runs/{run_id}/promote` | actor 必须以 `human` 开头且**与 G3 签署者逐字一致**；G3 已签、`human_signed=true`、决策 ∈ {full_now, subset_only, milestone_only}；再交 `kb/tools/n16_promote.py --promote`（I4/I7/七件套/parent 链由工具复核）；每次尝试落 `<run_dir>/promote_result.json`，已成功过拒绝重复晋升 |

**明确不做**：UI 编辑 `TESTLIB/`（写权在 v1–v3 归作者角色 + 沙箱）、UI 直接改基线/冲突清单。
晋升的**真实写盘**只由 `n16_promote.py` 原子完成；API 层不写 `baselines/`、不伪造闸门。

### 10.1 十项信任缺口在界面上的强制呈现

| # | 缺口（实证） | 界面强制行为 |
|---|---|---|
| 1 | I3 第 4 条不成立：口径一 = **1687**，口径二 `UVM_ERROR=0`（`REHEARSAL_REPORT.md`） | 两计数**并列同权**显示 + 来源 refs；**无"仅凭 UVM 汇总放行"的路径**；根因指向 `TB/AGENTS/PCIE-Agent/pcie_sequence.sv:598` 走 `uvm_info` 而非 `` `uvm_error `` |
| 2 | E-2：`evidence/archive/` 为空 → **已修**（见 §10.3） | 「查看原始证据」链接**先探测存在性**；缺失显示为显式缺陷项而非 404。归档腿修好后该阻断项对新 run 自动消失，对归档的演练轮仍如实显示 |
| 3 | N9-3 锁误清 + F-N16-04（拒绝后残留 `.staging-v1/`，20 项 ≈2.9 MB） | 看板显示锁 owner/`format_version`；残留 staging 作为**待清理告警**呈现 |
| 4 | 必改用例跨度 17.6 min → 22.8 h（78×） | 显示 ETA（低置信标注）+ 队列位次 + 取消按钮 |
| 5 | 冲突未清零（C2 `blocks_release=true`，共 72 项 C1–C72） | 闸门3 选 `full_regression` 时**前置阻断**；晋升按钮显示被阻断原因 |
| 6 | `case_state --rework-cycles` 未做范围校验；I7 仅在 N16 强制 | 看板常驻显示 `rework_count` / limit=3；超限显示升级路径 |

### 10.3 E-2 修复登记（归档腿）

**原始登记**（`REHEARSAL_REPORT.md:146`，major/N11）：
`evidence/archive/` 为空 ⇒ `run_guarded` 的「先归档再删」腿没有留下只读归档件，
违反 spec §7.7「归档只增不改；归档件置只读」。

**机制原因（实测定位，两个都在 `kb/tools/run_guarded.sh`）**：

1. `archive_sweep` 只 glob `$ROOT/SIMLIB_RUN/log/<case>_<seed>_*.log`，
   而 `compile-only`/`full` 模式的全部日志写在 `$EVIDENCE_DIR/<stamp>_<case>_<seed>_*.log`
   —— **目录与命名都不匹配** ⇒ 这两种模式下 `archive/` 永远为空。
   实证：`kb/runs/dev-host-tools/GUARD/ev5`（compile-only 轮）证据目录内有
   `_c_rtl.log`(86236 B)/`_c_tb.log`(28545 B)，而 `archive/` 里只有一个
   时间戳更早（12:12 vs 证据 12:14）的 16 字节陈旧 `_run.log`。
2. `compile-only`/`full` 分支**根本没有启动轮询** —— 而它恰恰是最需要归档的两个模式。

**修复**：候选路径补 `$EVIDENCE_DIR` 与 `--sandbox-root` 落点；两个分支都启动
「跑前 sweep + 运行中 0.5s 轮询」；终态 sweep 连跑两次（稳定判定需要连续两次观测，
而 `*.guarded`/`*.invalidated` 是收尾才出现的）；归档件 `chmod 444`（spec §7.7）；
加**稳定性判定**（同一 `(size, mtime)` 连续两次相同才归档），避免把仍在增长的日志
每 0.5s 复制一份半截件；`_guard.log` **不自我归档**（它是主证据原件，且收尾仍在追加）。

**另一半（闭环侧）**：N9 真实路径原先直接调 `run_uvs_new.sh`，绕过身份头 / 先归档再删 /
中止自愈 / 串行锁四项 ⇒ 归档必然为空。现改为
`bash kb/tools/run_guarded.sh --mode full --sandbox-root … --evidence-dir …`。

**验证**（可复跑）：`loop/tests/test_archive_e2.py`
——用 `uvlan` 桩走真实 `run_guarded.sh --mode compile-only`，断言
`archive/` 非空且含 `_c_rtl/_c_tb`、全部 444、数量 ≤12、无 `_guard.log`、
名字无重复 STAMP、scratch 已清理、`uvs.setup` md5 不变、仓库根无残留锁；
另有闭环侧断言：drill 运行后 `E2_EVIDENCE_ARCHIVE_EMPTY` 消失而
`I3_KOUTOU1_NONZERO` **仍在**（归档修好不得让判据变绿）。

**刻意不做**：不回填归档演练轮 `kb/runs/RUN-20261015-120626/evidence/archive/`。
那一轮是 verifier 的**冻结见证**（`frozen_before.md5` 4642 / `frozen_after.md5` 4644），
补文件会使见证失效。E-2 在该轮作为**历史缺陷**保留，新 run 才展示修复后行为。

### 10.2 界面不得成为权威

- 闸门"通过"以 `kb/tools/gate.py` 的 gate_state + `anchor` 为准；UI 只提交、只显示。
- 判绿条件由 `contracts.py` 在**服务端**计算；前端不参与判定（防前端伪造）。

---

### 10.4 节点执行详情投影（**全部节点**，供界面点击）

> 来源：[SPEC-REV-01](SPEC-REV-01-20261022.md) R4。执行视图的**每一个**节点 chip 都必须可点击，
> 点开能看到**该节点执行了什么、结果是什么、证据在哪**；不许只有一句"完成"。

**范围 = 全部节点，不按白名单裁剪**：`node_history` 里出现的任何 node 都必须能打开详情，
包括 N0–N16、四段之外/内部的节点（`N6_apply` / `N9_submit` / `N15_select` / `N15_submit`）、
`HALT`，以及将来新增的节点。未知节点也要能打开（显示原始事件与 detail，`known=false`），
不得因为没有中文名/owner 就不可点、或 404。

**数据来源唯一**：事件流（§9，**每条事件顶层的 `refs`**）+ `node_finished.detail` / `node_failed.detail`。
`node_history` 投影**只含** `{node,status,kind,at,detail}`——`refs` 只在事件里，构造 `node_history` 时已丢弃；
界面**不得**自行拼装事件或推断结论。

**每个节点（Host / 模型 / 闸门 / 框架）的 `node_finished.detail` 必含**：

| 字段 | 含义 |
|---|---|
| `source` | 执行路径：`drill_fixture` / `kb_tool` / `model_live` / `model_standin` / `human_gate` / `framework`；drill 夹具必须能看出是夹具 |
| `summary` | 一行可读结论（人话，含关键数字与去向，如"N1：allfiles 3374 条 + 162 用例冻结，parent=v0"） |

- **证据引用**：`refs` 属于事件顶层字段（`node_finished` 的 `refs`），detail 内不重复；
  详情投影把两者合并展示，但不改写任何一类数据。**只展示 run 目录内路径**（[SPEC-04](WEB_UI_SPEC.md) §6.7）；
  目录外引用（如 `loop/state/jobs/*.log`）只以 `refs_omitted` 计数呈现，不给路径。
- **status 语义**：节点 status **不只** `ok/failed`——闸门节点 status = 决策值（`confirmed`/`accept`/…）、
  `N8 ∈ {pass, rework, escalated}`、`N11 ∈ {intact, broken, escalated}`、`N16 ∈ {ok, refused, failed}`、
  `HALT = halted`。服务端原值下发，界面**原样显示**，不得自行把非 `ok` 当失败（反之亦然）。

**逐节点下限（现状 → 必须补到）**：

| 节点 | 现状 detail（实测） | 必须补到 |
|---|---|---|
| N0 | `mode` / `fixture_files` / `gate_init_rc`；refs=run_dir | `summary`；`baseline` |
| N1 | `artifact` / `parent` / `source` | `summary`；manifest 摘要（allfiles 条目数与 sha256、cases 冻结数、doc 指纹、commit 可解析性） |
| N2 | `artifact` / `rc` / `source` / `has_change` / `diff_count` / `diff_ids` / `pending_entries` / `diffs` / `self_check_ok` | `summary`；`routes`；`unresolved_count`；`offsets` |
| N3 | `mode` / `provider` / `problems` | `summary`（差异语义一句话）；`source` |
| N4 / N13 / N14（闸门） | `gate` / `decision` / `branch` / `actor` | `summary`（含是否给了理由）；`human_signed`；refs（`gates.json`） |
| N5 | `must_change_count` / `must_change_cases` / `index_complete` / `index_gaps` / `gate1_rc` / `source` | `summary`；`index_gap_count` |
| N6 | `mode` / `cycle` / `targets` / `validation_ok` | `summary`；`source` |
| N6_apply | `status` / `cases` / `edits` | `summary`；`source` |
| N7 | `cases` / `all_ok` | `summary`；`source`；失败用例名单 |
| N8 | `verdict` / `cycle`（+`limit` / `escalated`） | `summary`；`source` |
| N9 | `cases` / `koutou1` / `koutou2` | `summary`；`source`（drill 为模拟）；`job_id` |
| N9_submit | `job_id` / `cases` 或 `scenario` | `summary` |
| N10 | `cases` / `verdict_passed` / `pending` | `summary`；`source` |
| N11 | `chain` / `host_consistent` | `summary`；`source` |
| N12 | `mode` / `claimed_verdict` / `refs`（**与事件 refs 同名冲突**） | `summary`；`source`；detail 内改名为 `ref_count` |
| N15_select | `count` / `g3` | `summary` |
| N15 | `simulated`/`count` 或 `cases`/`passed` | `summary`；`source`；`job_id` |
| N15_submit | `job_id` / `cases` | `summary` |
| N16 | `cmd` / `rc` / `mode` / `dry_run` / `actor` / `actor_kind` / stdout/stderr 尾 | `summary`；refs（`n16_promote.json` / `promote_result.json`） |
| HALT | `reason` | `summary`（终止原因原文） |

> **现状差距**：上表右列字段当前**全部缺失**（`summary`/`source` 系统性缺失，N1/N2 另缺摘要与统计）。
> 因此"只加一个节点详情端点"不足以满足本节——`host_steps.py` / `model_steps.py` / `long_jobs.py` / `gates.py`
> 的 `node_finished` 调用都必须补 detail（各自 owner 的写权）。

**失败态**：`node_failed` + `message` 原文 + 最后一条事件；界面不得显示"完成"。
**禁止**把"有输入缺口/子步失败"记成 `node_finished ok`（现存反例见 [SPEC-REV-01](SPEC-REV-01-20261022.md) §D1：N2 的 `rc=3` 被当成功）。

**缺失与历史**：缺失字段一律显式 `null` / 列进 `missing_fields`，显示"未下发"，不猜、不补默认值。
事件与 detail 只增不改；新增字段只对生效后的新 run 出现，**旧 run 不回填**。

**只读契约**：详情投影不写盘、不改变业务权威；界面不得用详情里的数字判绿（判据仍在服务端 `blockers/can` 与 `gates.json`）。

**端点**：`GET /api/runs/{run_id}/nodes/{node}`（契约见 [SPEC-04](WEB_UI_SPEC.md) §6.7）；覆盖全部节点；
未实现的节点返回显式空投影（`known=false`），不返回 404 冒充"节点不存在"。

## 11. P0 验收判据（可判定）

夹具：归档运行目录 `<WORKSPACE_ROOT>/runs/RUN-20261015-120626/**`（含双计数分歧、死任务、印记 1/1/1、
闸门拒绝、篡改检测、staging 残留）。当前 `WORKSPACE_ROOT = <ENV_ROOT>/kb`（`environments.json`）。
**原因**：真实全跑单用例 ≈19 min，修订后可达 22.8 h，不能作为交互开发的循环。夹具必须标注 `DRILL FIXTURE`。

- [x] A1 图可跑：`N0→N4` 停在闸门1，pending interrupt 可被程序读到（非轮询日志推断）
      —— `tests/test_flow.py::test_reaches_gate1_with_readable_interrupt`；验收相 1。
- [x] A2 闸门材料并列双计数，且两者值与夹具产物**逐字一致**（命令复制，禁手算）
      —— `tests/test_evidence.py::test_dual_counts_diverge_and_both_are_recorded`；验收相 2。
- [ ] A3 未决条目 >0 时 resume 被拒（I1），拒绝原因可在界面读到
      —— **P0 未实现**：`gate1` 不读未决条目（审计 A1）；仅校验“已签 + human”。
- [x] A4 `N9` 形状正确：执行在作业期间处于 interrupt 而非 `running`，`save()` 成功且 `load()` 不 fail-closed
      —— `tests/test_flow.py::test_execution_parks_while_long_job_runs_and_survives_restart`；验收相 2/4。
- [x] A5 崩溃重附着：杀掉进程后 load，重新附着到在跑作业；作业已死则记 dead job
      —— `tests/test_flow.py::test_restore_redelivers_terminal_job_when_snapshot_is_stale` /
      `test_crash_recovery_delivers_dead_job_as_dead_not_done`；验收相 4b/5。
- [x] A6 单槽：并发两次 N9 申请，第二个排队而非并行；锁 owner 与 `format_version` 可见
      —— `tests/test_admission_and_jobs.py::test_slot_is_single_and_second_waits`；
      验收相 4b（跨重启锁不丢）。**注**：整链的排队唤醒缺口见审计 C2（准入层已排队，执行层无唤醒）。
- [x] A7 闸门2/3 的 `actor_kind` 门禁：`rehearsal`/模型 actor 在 `require-signed` 下被拒（对抗用例）
      —— `tests/test_flow.py::test_gate_rejects_non_human_actor`；验收相 1。
- [x] A8 N16 在**真实** `<WORKSPACE_ROOT>/baselines/` 上拒绝（rc=3）且**零副作用**；v0 五锚点与 12 文件不变
      —— `tests/test_flow.py::test_n16_on_real_baselines_refuses_with_zero_side_effects`；验收相 3。
- [x] A9 进度流只出现白名单 `kind`，无 raw parser 路径
      —— `tests/test_projection_and_frozen.py::test_run_view_events_are_whitelisted_only`；
      白名单实际比 §9 宽（多 `run_started` / `job_finished` / `admission_*` 等），见审计 B1。
- [x] A10 全程不修改 `RTL/`、`TB/`、`PKG/`、`TESTLIB/`、`<WORKSPACE_ROOT>/baselines/`（冻结见证：`MODIFIED=0 / DELETED=0`）
      —— `tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run`；验收相 2/3/5。
      **注**：该测试假设 `WORKSPACE_ROOT` 位于 `ENV_ROOT` 之内（`path.relative_to(P.REPO_ROOT)`）；
      工作区指向外部目录时该断言不成立（审计 I7；本会话 `ENV_ROOT` 只读且工作区在外部 ⇒ 未复跑）。

### 11.1 实现审计（2026-10-19）

P0 实现与本文契约的逐条对照见 **`doc/audit/AUDIT-20261019-spec-conformance.md`** 及附录
`doc/audit/parts/spec-conformance.md`（49 条：阻断 14 / 重要 23 / 轻微 8 / 待核 4）。
本节勾选状态以该审计为准；`[ ]` 表示 P0 未实现，或与 §9 白名单等条款存在明确偏差。
数字以 `doc/STATUS.md`（唯一数字源）为准：单测收集 70；
终验历史记录 117 断言（`loop/.logs/accept/FINAL_r1.txt` 六相 50/27/18/8/8/6）。
本会话 `ENV_ROOT` 只读 ⇒ `accept_v1_run.sh` 未复跑（环境限制，非代码缺陷）。

---

## 12. 边界（本层明确不做）

1. 不改 `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（上游业务契约）、`doc/AGENTS.md`（组织层权威）。
2. 不改 `kb/tools/*.py` 的**语义**；编排层只调用。（如需修 bug，走 `kb/` 自己的变更流程并留证。）
3. 不改 `RTL/`、`TB/`、`PKG/`、`TESTLIB/`、`doc/skills/`、`doc/tools/`、`doc/_notes/`、`doc/reference/`。
4. 不引入 `TaskDAG`/动态生成图：稳定拓扑写在源码里；未验证的运行时计划数据**不得**编译成临时 TriggerFlow 定义。
5. 不宣称分布式恢复、不宣称多用户并发。
6. v1 不做前端编辑用例、不做自动发版决策。
