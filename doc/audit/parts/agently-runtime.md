# 附录：Agently 运行时与编排用法审计（只读，仅登记不修复）

> 本附录对应审计日期 **2026-10-19**，HEAD=**dc7c69e**。
> 分工：本文件只登记"Agently 设计与运行时用法"这一审计面；不修改任何代码，不与其它附录重复登记。

## 0. 审计范围、方法与证据等级（10 行）

1. 审计对象：`loop/workflows/main_flow.py`（886 行，拓扑/RunManager/恢复/快照/投影）、`loop/workflows/chunks/{gates,long_jobs,model_steps,host_steps}.py`（1147 行）。
2. 运行时对象：`loop/host/{model_provider,job_runner,admission,gate_authority,evidence,progress,paths}.py`（1513 行）；契约对象：`loop/prompts/loop_nodes.yaml`、`loop/prompts/node_schemas.py`（221 行）。
3. 方法：依次加载技能 `agently`、`agently-design`、`agently-triggerflow`，按其核心工作流（owner 分离、请求/值/事件拓扑、生命周期、证据）逐条对照。
4. 框架侧对读：Agently **4.1.4.8** 源码（`TriggerFlow/Execution*.py`、`Definition`/`Process`、`types/trigger_flow`），确认 `pause_for`、`continue_with`、`save/load`、`for_each`、`self_resume` 的真实语义，不按文档猜。
5. 契约侧对读：`doc/spec/LOOP_ORCHESTRATION_SPEC.md`（§1–§10）、`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`、`loop/README.md`（§4/§5）。
6. 拓扑取证：只读构建 `LOOP_FLOW` 并取 `to_mermaid()`，以运行时定义（而非源码阅读）确认算子与边，结论见 §2。
7. 证据等级 **[已确证]**：直接读码可判定，或已用只读方式实测（如 to_mermaid、全仓 grep 调用点）。
8. 证据等级 **[待核]**：需要并发压测、跨进程/跨仓复现，或需真实 provider 才能定论；本轮不做会写 `loop/state` 的终验。
9. 路径约定：表中"文件:行号"一律相对 `loop/`；框架源码行号属 `.venv/lib/python3.11/site-packages/agently/`，仅在正文引用。
10. 一句话结论：拓扑与 pause/resume 形状扎实；风险集中在"失败即僵尸 run"的生命周期收敛、单槽的作业级 lease、模型输出无消费者/校验不阻断三类。

## 1. 做得扎实的部分

### 1.1 显式回边（已实测核验，非阅读推断）

`to_mermaid()` 显示 `n6_author`、`halt`、N15 的 `for_each` 各自只有**一个** operator：

- `signal_in_event_N8_REWORK --> n6_author`、`signal_in_event_G2_REWORK --> n6_author`、`op_chunk_ec9a...n5_impact --> n6_author` 汇入同一节点，并继承 `n6_author --> n7_compile --> n8_check` 后继 ⇒ 返工回边是**显式且连通**的，不是断头边。
- `for_each(concurrency=1)` 只生成一个 split/collect 组，四条 G3 分支共享同一 N15 组，没有隐式扇出。

### 1.2 pause_for / continue_with 形状

- 三闸门（`chunks/gates.py:120-125`）与 N9 停放（`chunks/long_jobs.py:146-155`）都用 `resume_to="self"`，并用 `data.is_resume` + `data.resume.value` 在下游显式分叉，**没有**把 `pause_for` 返回值当载荷（这正是 spec §8.8 记的实测真 bug）。
- `main_flow.py:501-515` 在 `continue_with` 之后**复核** `get_pending_interrupts()` 仍含该中断才 `mark_delivered`，正确规避了"框架被拒只打日志不抛错"的坑；恢复重投递换新 `resume_request_id`（`_boot_id` 段）也正确。
- `_is_clean_park`（`main_flow.py:571-588`）+ `save(require_idle=True)` 的组合，确实避免了"已派发但接管未开始"的半截快照。

### 1.3 owner 分离

- **N10 是全仓最好的分工样本**：计数/逐地址分解/分桶/修订点交集全部在 `host/evidence.py`（确定性），模型只对**有界桶**判 {既有缺陷/本轮引入/待裁决}，Host 再做覆盖性、枚举、依据与"是否落在修订点"的交叉核对，并按桶回填条目数（模型从不逐地址说话）。符合 agently-design「给模型一个 Host 签发的选择键 + 相关事实，Host 校验并重建身份」。
- N12 的数字以 Host 权威值覆盖并要求逐值一致；N11 的 `satisfied` 与"口径一非 0"做 Host 侧冲突判定；G3 的 I4 前置在 `decide()`、闸门恢复、N16 三处纵深防御。

## 2. 5 个阻断级问题（B1–B5）

### B1 模型调用失败默认判 pass

- 位置：`chunks/model_steps.py:519-525`（配合 `:353`、`:161-164`）
- 后果：模型调用失败时 `validation.accepted = {}` ⇒ `out["data"] = None` ⇒ `verdict = ... or "pass"` ⇒ 发 `N8_PASS`。**静态复核被整段跳过**，run 带着故障直接进入 19 min–22.8 h 的全跑；非法 verdict 同样被当 pass。
- 最小修复方向：`validation.ok is False` 时不得分叉，走 `node_failed` + 显式事件并终止本轮；verdict 缺失视为失败，而非 pass。

### B2 SLOT 中断没有任何恢复者

- 位置：`chunks/long_jobs.py:41-47` + `host/admission.py:263-294`
- 后果：全仓 grep 只有 `pause_for("SLOT:...")`，**没有任何 `continue_with` 指向 SLOT 中断**；`release()` 把槽"交接"给队首，但队首的执行永远不会被唤醒 ⇒ 第二个并发 run 永久停放**且持有单槽**，后续全部排队，无 API 可救（`decide` 只匹配闸门，`_deliver` 只匹配作业）。spec §7 FIFO / A6 因此不成立。
- 最小修复方向：给 SLOT 中断配显式 resumer（`release` 时按 queued owner 找到执行并 `continue_with`），或改成 host 事件 + 下游 chunk 判定；run 失败/取消时调用 `cancel_pending`。

### B3 N6 不产出沙箱，N9 real 测的是未修订用例

- 位置：`chunks/model_steps.py:409-443` + `chunks/long_jobs.py:88-93`
- 后果：N6 只产出修订**方案**，loop 内**没有任何步骤**把方案写进 `run_dir/sandbox/TESTLIB/*.sv`（已 grep 全仓，只有读没有写）；N9 real 找不到沙箱文件就**静默回落**到仓库 `TESTLIB/tc_pcie_rw_02.sv`（未修订）⇒ 全跑证据与"修订已生效"的结论不符，I3 的被测对象错了。
- 最小修复方向：新增显式 Host 写沙箱步骤并校验基线 md5 前后差异；回落必须 fail closed 或至少落一条显式 defect。

### B4 decide() 签署后恢复失败会楔死 run

- 位置：`workflows/main_flow.py:443-449` + `chunks/gates.py:137-163`
- 后果：先 `gate.py sign` 再 `async_continue_with`；恢复后的 chunk 抛异常（篡改为 require-signed rc=3、枚举漂移 KeyError、非法决策）时，框架把执行置 FAILED，中断已被消费（`resume_count=1`），而 `decide` 无 try/except ⇒ doc 停在 waiting_gate→running、无 pending 中断、不可重签不可续跑，账本留下**孤儿签名**（正是 F-V1-01 同类，只是触发源不同）。
- 最小修复方向：`decide` 包 try/except 并写 `doc.error/status=failed` + 显式关闭执行；或调整顺序为"先 resume 成功再签"（失败可回滚）。

### B5 单槽归属是进程而非作业

- 位置：`host/admission.py:204-213,77-95` + `workflows/main_flow.py:642-754`
- 后果：锁里 `owner_pid` 是 uvicorn 进程 ⇒ (a) 作业已死但 `holder_alive=true`，界面显示错误；(b) 进程重启后旧 pid 判死，**仍在跑的作业的锁可被下一个 run 抢占** ⇒ 两个仿真并发踩 `uvs.setup`（spec §7 单槽失效）；`async_restore_all` 从不复核本 run 是否仍持锁，违反 spec §8.5「外部系统 lease/fence 必须恢复时重新验证」。
- 最小修复方向：锁里写**作业** pid/job_id 并按 `JobRunner.poll()` 的相位判活；恢复时按作业记录重建租约，校验通过后才算 ready。

## 3. 完整清单（44 条）

> 列说明：等级列同时承载证据标记（`[已确证]` / `[待核]`）；路径相对 `loop/`。

| ID | 等级 | 文件:行号 | 违反条款/反模式 | 实际后果 | 建议 |
|---|---|---|---|---|---|
| B1 | 阻断 [已确证] | chunks/model_steps.py:519-525（+353、161-164） | agently fail-closed / 文件自述"校验失败不静默接受" | 模型调用失败时 data=None ⇒ `verdict or "pass"` ⇒ 发 N8_PASS，静态复核被跳过、带故障进 19min–22.8h 全跑；非法 verdict 同样当 pass | validation.ok=False 必须不得分叉，走 node_failed+终止；verdict 缺失视为失败 |
| B2 | 阻断 [已确证] | chunks/long_jobs.py:41-47 + host/admission.py:263-294 | triggerflow「required external wait 必须有信号 owner」+ spec §7/A6 | 全仓只有 pause 无任何 `SLOT:*` 的 continue_with（已 grep 全仓）；release 把锁交给队首但队首永不被唤醒 ⇒ 第二个 run 永久停放且持有单槽，后续全排队，无 API 可救 | 给 SLOT 加显式 resumer（release 时按 queued owner 找执行 continue_with），或改 host 事件+下游判定；失败时 cancel_pending |
| B3 | 阻断 [已确证] | chunks/model_steps.py:409-443 + chunks/long_jobs.py:88-93 | spec §3（N6 输出=沙箱用例）/"被测对象必须是本轮修订" | loop 内没有任何步骤写 `run_dir/sandbox/TESTLIB/*.sv`（已 grep）；N9 real 找不到沙箱文件就静默回落到未修订的仓库 TESTLIB ⇒ 全跑证据与"修订已生效"的结论不符 | 加显式 Host 写沙箱步骤并校验基线 md5；回落必须 fail-closed 或记显式 defect |
| B4 | 阻断 [已确证] | workflows/main_flow.py:443-449 + chunks/gates.py:137-163 | "拒绝必须发生在提交前"只覆盖顺序路径；回调异常必须落状态 | 先 gate.py sign 再 continue_with；恢复后 chunk 抛异常（篡改致 require-signed rc=3、枚举漂移 KeyError）时框架置 FAILED、中断已被消费(resume_count=1)，而 decide 无 try/except ⇒ doc 停在 waiting_gate→running、无 pending、不可重签不可续跑，账本留孤儿签名（F-V1-01 同类） | 包 try/except 置 failed+error+关闭执行；或先 resume 后签 |
| B5 | 阻断 [已确证] | host/admission.py:204-213,77-95 + workflows/main_flow.py:642-754 | spec §8.5「load 前校验外部 lease/fence」；单槽 owner 应是作业 | owner_pid 是 uvicorn 进程：作业死 holder_alive=true；进程重启后旧 pid 判死 ⇒ 仍在跑的作业的锁可被下一 run 抢占 ⇒ 两仿真并发踩 uvs.setup；restore 从不复核本 run 是否仍持锁 | 锁写作业 pid/记录句柄并按作业相位判活；恢复时重建租约后才 ready |
| I1 | 重要 [已确证] | workflows/main_flow.py:654-660,676-684 | 恢复失败必须显式失败（README §4.3） | "无快照"与 async_load 异常只 append 进报告，doc.status 不变 ⇒ 长期显示"在等你决策"/running | 两分支都置 failed+error+清 pending_interrupt |
| I2 | 重要 [已确证] | workflows/main_flow.py:323-351,811-832 | 生命周期收敛需兜底 owner（框架已暴露 execution.get_status()） | 只判 is_waiting/is_closed/reached_terminal；框架置 FAILED 时三者皆假 ⇒ 永远 running、ticker 永久巡检、重启还会当 running 恢复 | 加 get_status()/is_idle 分支，failed 即显式失败并 close |
| I3 | 重要 [已确证] | workflows/main_flow.py:304-313,545-555 + host_steps 各 raise 点 | 执行必须关闭并报告未解决 owner | auto_close=False 后只有 reached_terminal 会 close；start 异常与所有 failed run 永不 close，managed task/执行资源挂到进程结束 | 统一失败分支 async_close 并记录 close_result |
| I4 | 重要 [已确证] | chunks/long_jobs.py:103-127,141-144 | "终态必须释放单槽且幂等" | acquire 成功后 submit 抛异常、或 park 前缺 job_id 直接 raise 都不在 try/finally 内 ⇒ 槽永久泄漏 | acquire→submit→park 纳入同一持有生命周期，finally 释放 |
| I5 | 重要 [已确证] | host/admission.py:254-261 | 队列是状态，必须有终止清理 | cancel_pending 无调用点；排队 run 失败/取消后条目永存，后续 release 把锁交给死条目 | 失败/取消路径调用 cancel_pending；handoff 前校验队首执行仍活 |
| I6 | 重要 [已确证] | workflows/main_flow.py:359 + 框架 ExecutionPersistence.py:185 | spec §8.1/8.2 + recovery.md「snapshot-store CAS/retention」 | execution.save(path) 直接 Path.write_text：非原子、无 RecordStore、无保留代数/CAS；tear 写毁掉唯一恢复点 | 改 async_save(RecordStore keep_last)，临时文件+os.replace |
| I7 | 重要 [已确证] | services/contracts.py:53-65 + main_flow.py:175 | 跨边界权威必须校验新鲜度 | load_conflicts 在进程级 KbSources 上永久缓存 ⇒ I4 权威冻结在启动时刻：人工清零后仍拒，新出现的 blocks_release 被忽略（放行方向不安全） | 去掉缓存或按 mtime/version 校验后重读 |
| I8 | 重要 [已确证] | chunks/model_steps.py:367-403,603,643-687 + services/contracts.py:376-429 | agently-design「每个输出字段必须有授权消费者」 | N3 摘要/分组/风险点、N10 三分类、N12 报告正文只写执行状态，无节点/投影读取；spec §3「分类 2/3 进待裁决清单」无实现 | N10 接入 G2 材料与 case_state，N12 报告投影；N3 无人消费则删 |
| I9 | 重要 [已确证] | chunks/host_steps.py:171 + chunks/gates.py:98-126 | spec §2 I1「未决>0 不得进入修订」 | pending_entries 被算出但从未消费，gate1 只做材料+pause，n5 只校验"已签 confirmed" ⇒ 有未决条目也能确认并进 N5/N6 | 闸门1 放行前读未决数拒绝，判定下沉到 gate.py 前置 |
| I10 | 重要 [已确证] | chunks/model_steps.py:441 + services/contracts.py:67-80 | 同一计数两 owner | 图上 I7 用执行状态 n6_n8_cycles，看板/材料用 case_states.json.rework_cycles（real 下 loop 从不写）⇒ 图已 HALT 而 UI 的 I7 blocker 不出现，反之亦然 | 把 cycles 落进 run 产物作为唯一账本，图只读它 |
| I11 | 重要 [已确证] | chunks/host_steps.py:28-43 + chunks/gates.py:149 | triggerflow「blocking worker pool 是独立压力 owner」 | subprocess.run 在 async handler 内同步执行（n1/n2/n5/n7/n16 + require-signed）⇒ 事件循环被阻塞，其它 run 的投递、快照节拍、UI 全停顿 | asyncio.to_thread 或 host 有界执行器 |
| I12 | 重要 [已确证] | chunks/host_steps.py:234-251 | spec §3/§7「N7 经单槽准入」+ fail-closed | N7 不申请单槽（跨 run 可能与 N9 的 uvs.setup 并发）；real 下 compile_only.sh 无参调用、缺失时静默 rc=None 仍判 ok | N7 走短租约 admission；工具缺失/无 rc 视为失败 |
| I13 | 重要 [已确证] | chunks/long_jobs.py:242-259 | spec §3 N15「每用例证据」/ stream-bridge 临时项对账 | n15_case 只写 job_progress provisional=True，不跑任何东西、不申请单槽、无终态值覆盖；N16 照常晋升 | real 走 run_tc.py 并落证据；provisional 必须被 provisional=false 覆盖 |
| I14 | 重要 [已确证] | prompts/loop_nodes.yaml:29,55 vs chunks/model_steps.py:422-431,620-630 | agently-request「input 契约必须与代码一致」 | n6 要求偏移取自 input.targets[].values（未提供，只给 case+write_scope）⇒ 偏移只能编；n11 要求依据 input.case_states（代码给的是 rework）；Host 也不校验 basis_offsets 是否落在修订点 | Host 签发偏移或改 instruct；basis_offsets 做成员性校验 |
| I15 | 重要 [已确证] | chunks/model_steps.py:312-313,511-513 | agently 反模式「keyword/substring 当语义 owner」「test-only 生产分支」 | n12 用"跑通"/"不得"/"未"子串判是否宣称跑通；n8 替身用"退回"子串 + `scenario=="rework_once" and cycles<=1` 强制 rework ⇒ API 的 scenario 参数能左右 verdict | 改结构化枚举字段（claimed_verdict: passed/not_passed/undetermined）由 Host 比对权威；删除 scenario 对判定的影响 |
| I16 | 重要 [已确证] | chunks/model_steps.py:346 | 投影必须诚实 | `mode = "live" if not payload.get("standin")` ⇒ 模型调用失败也标 live，N8 还会走"有数据"路径 | 显式三态 live/standin/failed |
| I17 | 重要 [已确证] | chunks/gates.py:69 + main_flow.py:33 | spec §5.7「实现须经启动自检比对」 | BRANCH_DRIFT 只被 import 从不判定；权威枚举漂移时 BRANCH_EVENTS[gate][decision] KeyError → 落入 B4 楔死路径 | 启动即 `if BRANCH_DRIFT: raise`，或在 _resumed 对未知分支显式失败 |
| I18 | 重要 [已确证] | workflows/main_flow.py:333-336 | 状态投影语义 | 任何 pause_for 都投影为 waiting_gate：停在 JOB/SLOT 上也显示"等你决策" | 按 pending_interrupt.type 区分 waiting_gate/waiting_job/waiting_slot |
| I19 | 重要 [已确证] | workflows/main_flow.py:519-530 + host/job_runner.py:284-306 | 外部事件桥必须是有界投影 | watch 每 0.5s 全量扫 JOB-*.json；非内存 run 的记录永不 mark_delivered ⇒ 永久轮询，历史越多越慢 | 只扫未终结/未投递索引，对无句柄记录标 orphan |
| I20 | 重要 [已确证] | chunks/host_steps.py:274-283 | 身份 join 必须用真实身份 | `--actor-kind human` 硬编码、`--trigger-by` 取 state（可能 "host"）⇒ 晋升清单写死人类身份，与真实签署者脱钩 | 从 gates.json 的 G3 签署记录取 actor/actor_kind，缺失即拒绝 |
| I21 | 重要 [待核] | workflows/main_flow.py:419-448 | check-then-act 非原子 | 双击/双标签并发提交可双双通过 pending 检查并各自 sign ⇒ 双签名/账本 history 增长（F-V1-01 只在顺序场景成立） | decide 加按 run 互斥，或让 gate.py 做 compare-and-sign |
| I22 | 重要 [已确证] | prompts/loop_nodes.yaml:7 + prompts/node_schemas.py:122-130 vs chunks/model_steps.py:149-324 | 单一形状 owner | YAML 声称持有 output 契约但无 output 段；同一形状由 pydantic 与手写 _validate 两处拥有（历史上已因 kind 键失配而静默失效） | YAML 只留 info/instruct，形状只留 pydantic，_validate 只做成员性/交叉核对 |
| I23 | 重要 [待核] | workflows/context.py:104-141 + services/contracts.py:388 | 同一数字两条抽取路径 | run_view 用 evidence_log() 重抽（sorted 后取第一个带 summary 的日志），real 返工后有多份时间戳日志 ⇒ 看板可能展示上一轮证据，与 N10 state/闸门材料不一致 | 投影统一读 N10 结果或按最新 stamp 选日志并留 chosen-path 事件 |
| M1 | 轻微 [已确证] | chunks/model_steps.py:126-129,356-360 | 不得把内部阶段当拓扑节点 | 向事件流注入 N3_model/N3_request/N9_submit/N15_select 等伪节点 node_finished ⇒ node_history/current_node 出现图中不存在的节点 | 用独立 kind（model_call）或 detail 承载 |
| M2 | 轻微 [已确证] | chunks/gates.py:111 | 未消费字段 | standin_model_nodes=True 硬编码且前端不读 ⇒ 闸门材料永远宣称"模型节点为替身" | 由 provider status 动态生成或删除 |
| M3 | 轻微 [已确证] | workflows/main_flow.py:356-363,545-555 | 快照不得无变化反复落盘 | 每 0.2s 同步全量序列化+重写 view.json；require_idle 失败时 note 每 tick 追加（无界增长） | 按状态版本变化落盘、限制 notes、改 async_save |
| M4 | 轻微 [已确证] | workflows/main_flow.py:541,554 + README:196 | 文档与实现一致 | 注释/README 称 0.5s 节拍，实际 0.2s | 统一口径 |
| M5 | 轻微 [已确证] | workflows/main_flow.py:863-876 | 单一投影口径 | list_runs 用 doc.status，run_view 用 _status_of 重判 ⇒ 列表与详情可能一 running 一 finished | list 复用 _status_of |
| M6 | 轻微 [已确证] | workflows/main_flow.py:534,546 | owner 单一 | ticker 循环条件读 runner._stopping（另一 owner 的私有字段） | ticker 用 RunManager 自己的 Event |
| M7 | 轻微 [已确证] | chunks/long_jobs.py:123 + main_flow.py:365-370 | 状态单一 owner | job_id 同时写 execution state 与 ctx.pending（不序列化、恢复即丢）且从不清理 ⇒ 每 tick 轮询旧作业 | 只留 execution state |
| M8 | 轻微 [已确证] | chunks/model_steps.py:377 | 信息损失必须披露 | N3 静默只取前 40 条 diff，输出未标注截断 | 把 total/truncated 写给模型与消费者 |
| M9 | 轻微 [已确证] | host/progress.py:23-41 | spec §9 kind 白名单 | 白名单比 spec 多 run_started/job_finished/admission_*；run_finished 在白名单却无写入方（终态事件从不产） | 以 spec 为唯一清单并加自检 |
| M10 | 轻微 [已确证] | chunks/model_steps.py:508 | 输出字段必须有授权校验 | N8 offered={}，_validate("n8") 无成员性/依据落地校验，findings 可凭空 | findings.item 限定到 checklist 项集合 |
| M11 | 轻微 [已确证] | host/gate_authority.py:95 | 死代码 | DEFAULT_EXPECT 无人使用 | 删除或用于 _resumed 的 --expect |
| M12 | 轻微 [已确证] | workflows/main_flow.py:484-493 | 失败必须留痕 | _deliver 找不到匹配中断时静默 return（无事件、无 error） | 写 warning 事件并按陈旧快照规则处置 |
| M13 | 轻微 [待核] | workflows/main_flow.py:614-640 | 对账方向单一 | 只查"快照落后于账本"，不查"快照超前"（快照已签、账本未签）⇒ 会重放未签闸门随后被 require-signed 拒绝并楔死 | 做双向对账 |
| M14 | 轻微 [待核] | host/admission.py:222-224 | 陈锁判定一致性 | 同 job_id 直接 granted，绕过 format_version/存活判定；SLOT job_id 每 run 固定 ⇒ 旧锁可能被当"自己持有" | 命中同 job_id 也校验 owner_start |
| M15 | 轻微 [待核] | host/admission.py:241-252 | 文件级 CAS | 死锁回收是 unlink+O_EXCL 两步，跨进程并发可能双双成功（单机单用户概率低） | 改 rename/lockf 原子回收 |
| M16 | 轻微 [已确证] | host/model_provider.py:226-254 | 全局可变配置 owner | 每次节点调用都改写 Agently 全局 settings（多 run 共享），无 per-run 绑定 | settings 启动一次幂等设置 |

统计：阻断 5 条、重要 23 条、轻微 16 条，合计 **44** 条；其中 [已确证] 39 条、[待核] 5 条（I21、I23、M13、M14、M15）。

## 4. 本轮不修复声明与建议修复顺序

**本轮不修复**：本附录只登记审计发现，**不改任何代码、不改 spec、不改 kb 工具**。用户已批准"只登记不修复"，修复须另立任务并各自留证。

建议修复顺序（按"后果不可逆性 / 修复成本"排序）：

1. **先修生命周期收敛与单槽 lease**：B4、I1、I2、I3（失败一律显式 failed + close，杜绝僵尸 run）、B2、B5、I4、I5（SLOT 有 resumer、锁以作业为 owner、释放幂等）。
2. **再修模型输出消费者与校验阻断**：B1、I8、I13、I15、I16、I14（fail-closed + 每个字段有消费者 + 去掉子串判据）。
3. **再修证据链与被测对象**：B3、I12、I9、I10（沙箱产出、N7 准入、I1/I7 单一账本）。
4. **最后修投影与一致性**：I6、I7、I11、I18、I19、I22、I23 与 M 系列（快照改 RecordStore、权威新鲜度、事件/节点投影口径）。

> 本附录对应审计日期 **2026-10-19**，HEAD=**dc7c69e**。所有行号以该提交为准。
