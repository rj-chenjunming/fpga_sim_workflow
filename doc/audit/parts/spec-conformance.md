# 规格一致性审计 · 附录：`loop` 实现 vs 两份 spec

> **审计任务**：task-1 / task-4。**审计日期**：2026-10-19。**代码基线**：HEAD `dc7c69e`（13 commits）。
> **范围**：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（v0.2，节点 N0–N16、不变式 I1–I8、三闸门）
> 与 `doc/spec/LOOP_ORCHESTRATION_SPEC.md`（v0.1，owner 账本、生命周期、长任务停等、单槽准入、恢复、投影）
> 对照 `loop/workflows/main_flow.py`、`loop/workflows/chunks/*.py`、`loop/host/*.py`、`loop/services/*.py`。
> **不在本附录**：Agently/框架层的实现偏差由同目录其它 `parts/*.md` 负责，本文件不重复。

---

## 1 方法与证据等级

- **只读审计**：未修改代码、未运行会写 `loop/state` 的终验；只执行了
  `cd loop && .venv/bin/python -m pytest --collect-only -q`（**70 collected**）与 read/grep。
- **证据等级 [已确证]**：由代码路径、函数/常量定义、`grep` 无调用者、既有测试名可直接判定。
- **证据等级 [待核]**：行为依赖运行条件（例如某个分支当前不可达、需框架语义或真机），
  已给出触发条件，不能作为“已修复”或“必现缺陷”使用。
- **等级**：`阻断` = 会让 real 闭环/不变式失效或产生错误结论；`重要` = 关键契约缺失/边界错误；
  `轻微` = 一致性/可维护性/投影噪声。
- **本轮（task-4）只做文档纠偏**：下列条目均为**实现缺口/偏差登记**，没有代码修复。
- **路径约定**：表中 `chunks/…`、`host/…`、`services/…`、`main_flow.py` 等“文件:行号”一律**相对 `loop/`**；
  `kb/tools/…` 相对 `TOOL_ROOT`；数据/证据路径相对三根（当前 `WORKSPACE_ROOT = ENV_ROOT/kb`）。

**统计**：49 条 —— 阻断 14 / 重要 23 / 轻微 8 / 待核 4（待核项不计入前三类）。

---

## 2 A 组：spec 有、代码没有或缺

| ID | 等级 | 文件:行号 | spec 条款 | 实际行为 | 影响 | 建议 |
|---|---|---|---|---|---|---|
| A1 | 阻断 [已确证] | `chunks/gates.py:98-176`、`chunks/host_steps.py:165-174`、`services/contracts.py:287-318` | CI-I1、CI-§4-N4、LOOP§2-I1 | `gate1` 只校验“已签 + human”，不读未决条目；N2 的 `pending_entries` 计算后无人消费；闸门材料无差异清单、无逐条决策 → I1 未强制、N4 无法逐条确认/忽略/转人工 | 未决条目可进入修订阶段，违反完成不变式 I1 | `gates.py` 放行前读 `n2_diff` 未决数并 fail closed；材料加入条目级决策；补回归测试 |
| A2 | 重要 [已确证] | `main_flow.py:432-446`、`chunks/gates.py:137-144` | CI-§4-N4、LOOP§5.7 | 服务端不强制 `ignored`/`disputed`/`rework` 的 `reason`；`requires_reason` 仅是 UI 提示；`disputed` 无“转人工裁决清单”，只有整门单选 | 忽略/有疑义可无理由落账，裁决清单不成立 | `decide()` 与 `_resumed()` 对这三类决策强制非空 reason；`disputed` 写入待裁决清单 |
| A3 | 阻断 [已确证] | `chunks/model_steps.py:661`、`services/contracts.py:67-80`、`kb/tools/n16_promote.py:145-149` | CI-I2、LOOP§2-I2 | `loop` 全仓无 `case_states.json` 写入者（N16 工具侧有前置检查）；I2 状态机、待验阻断、gate2 前 I2 检查均缺 → real run 的 N16 恒因缺台账 rc=3 | 用例态不可收敛；I2 只在拒绝侧存在 | N6/N8/N10 通过 `kb/tools/case_state.py` 维护台账；gate2 材料投影待验用例 |
| A4 | 阻断 [已确证] | `host/evidence.py:33-35,225-240` | CI-I3、CI-§7.2、LOOP§2-I3 | `_verdict` 只判 UVM 汇总 + 两计数，不判 imprint 三向一致；期望地址/值硬编码在 host 代码，不取文档位定义表 | 印记缺失/期望值不符仍可能判“跑通” | `_verdict` 纳入 imprint consistency；期望值从文档条目/索引读取；补反例测试 |
| A5 | 阻断 [已确证] | `chunks/host_steps.py:245-247` | LOOP§3-N7（§6 又允许短任务内联，spec 自相矛盾） | real N7 检查不存在的 `kb/tools/compile_only.sh` 后只置 `note rc=None`：不编译、无卡点B证据、无 rc/日志 | 修订后的用例未经过廉价编译门就直接提交 N9 | 调 `run_guarded.sh --mode compile-only`（短任务可内联，但必须有 rc/证据），或删除 §6 内联例外 |
| A6 | 阻断 [已确证] | `chunks/model_steps.py:409-443,462-488` | LOOP§3-N6、CI-§4-N6 | N6 只产 plan，不写 `run_dir/sandbox/TESTLIB`、不冻结用例 md5；N8 因此只能 `plan_only` 复核 | N6 的输出契约（用例 v + md5）不成立，N7 无编译对象 | 落 Host 的沙箱写入步骤（作者产 diff/文件 + md5 冻结），N8 回到代码级复核 |
| A7 | 阻断 [已确证] | `chunks/long_jobs.py:20,33,63,91-109` | LOOP§3-N9、CI-§4-N9 | N9 固定 `tc_pcie_rw_02`/seed1，忽略 N5/N6 目标集；real 下沙箱不存在时回退未修订的 `TESTLIB` 原件 | 验证的不是本轮修订点 | 目标用例/seed 从 N5/N6 状态取；沙箱缺失应失败而非回退原件 |
| A8 | 重要 [已确证] | `chunks/long_jobs.py:175-188` | CI-§4-N9、CI-§8 全跑成本门 | dead/cancelled/相位不明一律 `RuntimeError` 终止，未“采证并三分类”，无失败证据包 | 跑挂后无法按 N10 口径归因 | 失败路径落证据 + 进入 N10 三分类，而不是直接终止 |
| A9 | 重要 [已确证] | `chunks/model_steps.py:250-278`、`services/contracts.py:49` | LOOP§3-N10/§4 | FAIL 分类 2/3 只留在 execution state；无 `conflicts/pending.json` 落盘（`KbSources.pending` 从未使用）；无“断言实效性”分析 | 待裁决清单缺失，I4 的一等公民不完整 | 分类结果写 `<WORKSPACE_ROOT>/conflicts/pending.json`；补断言实效性判定 |
| A10 | 阻断 [已确证] | `main_flow.py:69`、`chunks/model_steps.py:613-637` | CI-§4-N11、LOOP§3-N11 | 业务 N11=guardian 证据守护（成链/不成链）完全缺失；现 N11 改成评估节点，且 `assessment=needs_rework` 不驱动回边（N11→N12 无条件） | I5/身份四方 join 在编排层无消费者；评估返工不生效 | 增加 guardian 节点或把证据链判定并入 N10/N11；N11 需要返工时显式回边 N6 |
| A11 | 重要 [已确证] | `main_flow.py:71,432-437` | CI-N13、CI-§8 返工回指、LOOP§3-N13 | 只有 `G2_REWORK→N6`；从不向 `gate.py` 传 `--rework-target N4`，故“范围判错回 N4”不可用 | 返工只能修用例，不能修范围 | `decide()` 透传 `--rework-target`，图上增加 G2_REWORK→N4 分支 |
| A12 | 阻断 [已确证] | `chunks/host_steps.py:274-290`、`main_flow.py:77-79`、`services/api.py:116-178` | CI-I8/N16、LOOP§3-N16/§10.1#5 | N16 恒 `--dry-run`、无七件套真实晋升；且由 G3 分支自动进入，无独立“人点晋升”API/按钮（LOOP§11-A8 只要求拒绝，但 I8 能力未落地） | I8 不可达；晋升时机语义与 spec 不符 | 增加人触发入口与真实晋升开关；`dry-run` 只用于 drill |
| A13 | 重要 [已确证] | `main_flow.py:53-59`、`chunks/host_steps.py:153-157` | CI-§4-N2、CI-§5 N16→下一轮 | `has_change` 无人消费，无“无差异直接结束”；`--from-baseline` 写死 `v0`，N0 的 `baseline` 与新基线链不生效 | 无差异仍走全链；晋升后仍与 v0 比 | 使用 N0/N16 的基线号；has_change=false 时结束并报告 |
| A14 | 重要 [已确证] | `chunks/host_steps.py:216-227` | CI-§4-N5、LOOP§4 | `n5_impact` 的 `index_complete`/`index_gaps` 只记录不分支；`must_change` 为空也继续 N6（§4 要求受影响子集非空校验） | 索引缺口/空子集被静默放过 | 非空校验 + 索引缺口转人工；gate1 材料展示 index_gaps |
| A15 | 阻断 [已确证] | `chunks/long_jobs.py:225-259`、`main_flow.py:77-79` | LOOP§3-N15/§7 | N15 从不调用 `run_tc.py`；real 下 `n15_case` 不执行任何回归，只 emit `job_progress(provisional=True)` | 全量/分层回归能力不存在 | 接入 `run_tc.py` 或把 N15 标为未实现并从 G3 分支移除 |
| A16 | 重要 [已确证] | `main_flow.py:359,677` | LOOP§8.1-8.3 | 未用 `async_save(RecordStore)`；无 `snapshot_retention` / projection policy，恢复靠手写 JSON 快照 | 恢复机制与机制契约不一致；保留/投影策略缺失 | 改用 RecordStore + retention/projection 配置，或修订 §8 承认自定义快照 |
| A17 | 重要 [已确证] | `main_flow.py:434-441` | CI-I5、LOOP§4 闸门2 | `gate.py sign` 未带证据指纹（`--artifact`/counts 快照）；闸门决策不绑定证据与版本化冻结变更结果 | 闸门签署不可回指本轮证据，I5 身份链断 | 签署时带 artifacts（N2/N5/N10/证据包 md5）并写入 gate history |
| A18 | 阻断 [已确证] | `chunks/host_steps.py:266-272`、`kb/tools/n16_promote.py`（全文无 conflicts 校验） | CI-I4、LOOP§2-I4/§4-N16 | 仅当 `G3=full_now/subset_only` 才查 `blocks_release`；kb n16 工具完全未查 → `G3=milestone/defer` 时 I4 在晋升路径失效（当前 72 条全 blocks_release） | 未清零冲突可通过里程碑路径晋升 | N16 工具无条件校验 `blocks_release`；chunk 不再按 G3 分流 |
| A19 | 阻断 [已确证] | `chunks/host_steps.py:120` vs `kb/tools/n1_snapshot.py:349` | LOOP§3-N1、CI-N1 | 调 `stage` 缺必填 `--parent` ⇒ argparse rc=2，real 必挂；且 loop 无新 RTL 包/文档的 staged 摄入入口 | real 链在 N1 即断 | 补 `--parent`；增加 staged 输入入口（API/约定目录）并校验完整性 |
| A20 | 重要 [已确证] | `chunks/model_steps.py:643-687` | CI-§4-N12 | N12 报告不落盘（仅 execution state），无“引用不可解析→拒发”（schema 有 refs，`_validate` 不检查） | 报告不可回放；引用错误可放行 | 报告写入 `<WORKSPACE_ROOT>/runs/<id>/n12_report.md`；Host 校验 refs 可解析性 |
| A21 | 重要 [已确证] | `chunks/model_steps.py:367-403` | LOOP§3-N3 | 模型调用/解析失败仍 `node_finished` 继续（只记 problems），未按“解析失败结束执行、不伪造” | 空摘要可进入 Gate1 | N3 校验失败显式终止本轮 |
| A22 | 重要 [已确证] | `chunks/model_steps.py:526-529`、`main_flow.py:68` | CI-I7、LOOP§2-I7 | N8 超限 emit `N8_ESCALATE→halt`，未“升级 N13 人工裁决” | 超限后无法由人接手，流程直接终止 | `N8_ESCALATE→gate2`（带升级原因）或专用人工裁决闸门 |
| A23 | 重要 [已确证] | `chunks/gates.py:100-118`、`services/contracts.py:287-318` | LOOP§3-N4/N13/N14 | 三闸门材料只有 counts/blockers/冲突摘要/返工/基线：G1 无差异清单与冲突快照，G2 无报告+用例态+计数，G3 无评估结论 | 人工无法按 spec 输入做决策 | gate material 补齐 N4/N13/N14 输入（含 refs） |
| A24 | 重要 [已确证] | `chunks/model_steps.py:220-224` | CI-§6/§9 铁律3 | N8 只校验 fail 条目 `basis` 非空；Host 不校验预期值/地址是否取自文档位定义表，模型可自造预期值 | 预期值可脱离文档权威 | Host 用文档位定义表/索引交叉校验 N6/N8 的地址与预期值 |

## 3 B 组：代码有、spec 未登记或描述不符

| ID | 等级 | 文件:行号 | spec 条款 | 实际行为 | 影响 | 建议 |
|---|---|---|---|---|---|---|
| B1 | 重要 [已确证] | `host/progress.py:23-41`、`chunks/long_jobs.py:258` | LOOP§9、§11-A9 | 白名单比 §9 多 `run_started`/`node_failed`/`job_finished`/`admission_*`/`run_finished`；`job_progress` 只 `provisional=true`，无终值 `provisional=false` 对账；测试按本层常量断言，A9 实际空转 | 前端可能收到 spec 未定义的 kind；临时计数无终值覆盖 | 收紧白名单到 §9 或正式修订 §9；补终值冻结逻辑 |
| B2 | 重要 [已确证] | `services/api.py:81-97`、`web/index.html:181,197` | LOOP§10 | spec 称写动作恰好两个，实现有第三个 `POST /api/runs`（建 run + `gate.py init`） | UI 写面与契约不符 | 修订 §10 登记建 run，或从 UI 移除该入口（保留脚本入口） |
| B3 | 轻微 [已确证] | `host/admission.py:62-75` | LOOP§7 | 锁字段是 `acquired_at`（另 `owner_start`/`note`），spec 要求 `start_ts` | 文档与锁结构不一致，界面/审计字段对不上 | 统一字段名或修订 §7 |
| B4 | 轻微 [已确证] | `host/job_runner.py:183-271` | LOOP§6.7 | 无 `lookup(job_id)`，恢复用 `reattach()`/`poll()` 全量扫描（行为等价、接口不符） | 契约接口不可直接对应 | 补 `lookup()` 或修订 §6.7 写 `reattach` |
| B5 | 重要 [已确证] | `chunks/gates.py:111` | LOOP§10.1、README§5.1 | `material.standin_model_nodes` 恒 `True`；live 模型时向操作员谎报“替身” | 闸门材料误导人判断模型结论可信度 | 由 `model_steps` 实际 mode 汇总后投影，删除硬编码 |
| B6 | 重要 [已确证] | `chunks/model_steps.py:458-507` | LOOP§3-N8 | 新增 `plan_only` 复核范围（spec N8 输入是沙箱用例+卡点C），是 N6 无产物的绕行口径 | 复核标准被降级，代码级问题漏检 | 随 A6 落地删除 `plan_only` 分支 |
| B7 | 轻微 [已确证] | `web/index.html:355-377` | LOOP§5.7 | 前端保留写死的 `GATE_DECISIONS_FALLBACK`，与“前端不得写死枚举”冲突（兜底路径） | 服务端字段缺失时可能渲染过期枚举 | 删除兜底表，改为禁用按钮并提示 |
| B8 | 轻微 [已确证] | `services/contracts.py:423`、`main_flow.py:838-852` | LOOP§1 owner 账本 | `run_view` 原样外放 events/pending payload，“不泄露 raw event、内部 metadata”未做到 | 投影层职责边界被打破 | 投影裁剪为稳定字段，raw 仅按需/鉴权暴露 |
| B9 | 轻微 [已确证] | `services/contracts.py:118-128`、`chunks/gates.py:100-107` | LOOP§5/§10.1 | G1 材料把 `I3_EVIDENCE_MISSING` 列为 hard_block（N9 尚未发生） | 闸门1 材料出现误导性阻断 | 按闸门阶段裁剪 blockers（G1 不评 I3） |
| B10 | 轻微 [已确证] | `main_flow.py:240-288`、`chunks/long_jobs.py:66-87` | 无 spec 条目 | `scenario` 任意字符串均接受，未知值在 drill 下静默按 happy 跑 | 拼写错误会被当成功情景 | 校验 scenario ∈ {happy, dead_job, cancel} |

## 4 C 组：代码内自相矛盾/明显缺陷

| ID | 等级 | 文件:行号 | spec 条款 | 实际行为 | 影响 | 建议 |
|---|---|---|---|---|---|---|
| C1 | 阻断 [已确证] | `chunks/gates.py:147-154`、`kb/tools/gate.py:56-60`、`kb/tools/gate.py:241` | LOOP§5.4/5.8、CI-I6 | 恢复时 `require-signed` 不带 `--expect` ⇒ 默认 G1=confirmed/G2=accept；故 G1 `ignored`/`disputed`、G2 `rework` 在 sign 之后必抛 `GatePreconditionFailed`：分支不可达、run failed、`gates.json` 留孤儿签名 | spec 枚举中的 3 个决策不可用；账本被污染（F-V1-01 同类） | `require-signed` 传该门实际决策，或改用“已签且非 pending”判据；拒绝必须在 sign 前 |
| C2 | 阻断 [已确证] | `chunks/long_jobs.py:38-47`、`host/admission.py:254-294`（全仓无 SLOT `continue_with`） | LOOP§7 queue | 排队者无人唤醒（`release` 只交接锁）；`cancel_pending` 无调用者，排队 run 无法取消；锁交排队者后由当前进程持有，后续 run 可能永判 busy | 第二个 N9 永久挂起 + 单槽被“假活”占用 | 增加队列唤醒器（release 后 resume 队首 SLOT 中断）与排队取消路径 |
| C3 | 阻断 [已确证] | `chunks/model_steps.py:519,340-361,161-169` | LOOP§3-N8 | 模型调用/校验失败时 `verdict = data.get(...) or "pass"` ⇒ N8 默认放行 N9（校验失败=通过） | 安全闸失灵，未复核的修订进入全跑 | 模型失败/校验失败必须显式失败或退回 N6，禁止默认 pass |
| C4 | 重要 [已确证] | `chunks/long_jobs.py:33-127 vs 213-219` | LOOP§5.9/§6.8 | 拿到单槽后 `runner.submit` 等异常无 `finally`，release 只在 `n9_park`，异常路径泄漏单槽 | 一次提交失败会把槽永久占住 | 把 acquire→submit 纳入 try/finally，或在 submit 失败时立即 release |
| C5 | 重要 [已确证] | `chunks/model_steps.py:526`、`services/contracts.py:229`、`kb/tools/n16_promote.py:165` | CI-I7 | 同一 limit 三处边界不一致：`>=` / `>=` / `>`（cycles=limit 时 N8 升级但 N16 仍可晋升） | I7 边界可被绕过 | 统一为 `>= limit` 或统一在 case_state 一处判定 |
| C6 | 重要 [已确证] | `chunks/model_steps.py:416,441`、`main_flow.py:71` | CI-I7、LOOP§3-N13 | N6 每次进入即自增 `n6_n8_cycles`（首次修订也算）；G2 rework 经 N6 自增同一计数，人工返工可能提前触发 N8 升级 | 返工预算被误耗，可能提前 HALT | 分开 N6↔N8 与 N13 返工计数；首次修订不计返工 |
| C7 | 重要 [待核：可达性] | `chunks/long_jobs.py:57-59`、`main_flow.py:69` | LOOP§6 | 排队分支返回 `slot_retry` 后图上无分支仍流入 `n9_park`（无 job_id ⇒ RuntimeError）；当前因 SLOT 无人恢复而几乎不可达 | 若队列恢复实现，会引入崩溃路径 | 为 `slot_retry` 加显式回边/自环；与 C2 一并修 |
| C8 | 待核 | `chunks/host_steps.py:287-290`、`main_flow.py:105-118,811-832` | LOOP§3-N16 | N16 `rc∉{0,3}` 时 `node_finished=failed` 后 raise；`decide()` 不记 `doc.error`，终态判定只看节点名 ⇒ 失败可能投影 finished/waiting（当前 dry-run 下不可达） | 归档失败可能被当成结束/等待 | 把异常写入 `doc.error` 并让 `_status_of` 以 execution 状态兜底 |
| C9 | 待核 | `chunks/host_steps.py:275-278` | CI-I8/N16 人触发 | N16 恒传 `--actor-kind human`；`gate_actor` 缺失时 `trigger-by="host"` 却按人签 | I6 语义矛盾（正常路径不触发） | `actor_kind` 由 `gate_actor`/触发来源推导；缺失时 fail closed |
| C10 | 重要 [已确证] | `chunks/model_steps.py:593-607` | LOOP§3-N10、CI-I3 | N10 模型分类 validation 失败不阻断/不失败，N11/N12 继续消费空 data | FAIL 三分类可静默缺失 | 分类失败显式失败或降级为“待裁决”并阻断 gate2 |
| C11 | 重要 [已确证] | `chunks/model_steps.py:47-62,396-398,509-518,548,633-634,671-676`、`workflows/context.py:63` | LOOP§3 N3/N6/N8/N10/N11/N12 | `standin` 恒从 drill 夹具 `FIXTURE_RUN` 读产物；real 模式 provider 不可用时把夹具结论当本轮输出（只标 standin，无夹具来源路径） | real 结论可被 drill 证据污染 | standin 在 real 模式只输出空/待补，不读夹具；投影 source 路径 |
| C12 | 待核（轻微） | `chunks/long_jobs.py:183-188,213-219` | LOOP§6.8 | 相位非 done 时 raise 后 `finally` 仍 release 单槽；若作业其实在跑会破坏单槽互斥（当前投递路径只送终态） | 单槽互斥可能失效 | 仅在权威相位为终态时 release；未知相位保留锁并升级 |
| C13 | 待核 | `main_flow.py:811-832` | LOOP§5/§9 | `_status_of` 先返回 `doc.status`（waiting_gate）再看 execution，恢复/决策异常后可能短时把失败显示成“在等人工” | 失败被误显示为等待 | 先查 `doc.error`/execution 状态，再回退 doc.status |
| C14 | 轻微 [已确证] | `chunks/host_steps.py:172` | LOOP§4 n2 edge | `self_check_ok` 读入但不校验（False 也不阻断） | N2 自检失败可继续 | 自检 false 时 fail closed |
| C15 | 轻微 [已确证] | `chunks/gates.py:72-76` vs `services/contracts.py:376-429` | LOOP§5.6 | G2 材料 counts 取 n10 state 旧值，而 `run_view.counts` 取 evidence 当前值，两处可能分歧 | 闸门材料与看板计数可不同 | 统一由 evidence/run_dir 现读，或把 n10 证据指针写入材料 |

---

## 5 残留待核与边界

1. **[待核] C7/C8/C9/C12/C13**：均给出触发条件；其中 C8/C9 在当前 dry-run 路径不可达，
   C12 在当前仅终态投递下不触发。**不得**把它们当作“已复现缺陷”写进 STATUS 之外的结论文档。
2. **A 组中的 P0 合同缺口**（A3/A5/A6/A7/A10/A12/A15/A18/A19）与 LOOP§11 的未勾选项对应；
   本次 task-4 只在其文档中标注状态，**未修代码**。
3. **环境限制（不是代码缺陷）**：本会话沙箱把 `ENV_ROOT` 挂为只读，
   `accept_v1_run.sh` / `test_archive_e2.py` 无法在本会话复跑；终验数字引用
   `doc/evidence/ACCEPTANCE_V1.md` 与 `loop/.logs/accept/FINAL_r1.txt`（六相 50/27/18/8/8/6 = 117）。
4. **与 Agently parts 的边界**：本附录只覆盖 `loop/*` + `kb/tools/*` 与两份 spec 的契约一致性；
   TriggerFlow/Agently 框架层的 API 选择与恢复语义不在此重复。
