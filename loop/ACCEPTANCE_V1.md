# v1 真实 HTTP 终验（闸门操作台 + 长任务看板）

> **结论**：`116/116` 断言通过，**4 代服务进程、3 次真重启**。
> 复跑方式只有一条命令（见 §1）。原始输出全部留档在 `loop/.logs/accept/`。
>
> 本轮验收**同时担任发现手段**：它抓出并修掉了 7 个真实缺陷（其中 2 个会影响"能不能发版"级别的判断，
> 3 个影响"崩溃重启后还能不能继续"）。缺陷清单与修法在 §3；它们是这份报告比"全绿"更重要的部分。

---

## 1 怎么复跑（唯一命令）

```bash
cd loop
bash spikes/accept_v1_run.sh        # 约 3 分钟；rc=0 即全过
```

脚本会：清运行时状态 → 起第 1 代服务跑 `--phase 1` → 停 → 起第 2 代跑 `2/3` → 停 → 起第 3 代跑 `4`
→ 停 → 起第 4 代跑 `4b/5` → 停。原始输出落 `loop/.logs/accept/{driver.log,server.out,phase*.txt}`。

**为什么必须是"单次调用内"起停服务**：本工程的每次 `bash` 调用都跑在独立沙箱里
（`--unshare-pid --die-with-parent`）——换一次调用就**既看不见也杀不掉**上一代留下的 uvicorn
（实测：phase 1 因此打到了旧代码的服务上，端口被占却静默继续）；而用 DSH 的 `job_kill` 会连沙箱
把长任务子进程一起收掉，于是"运行中的长任务跨重启仍然活着"这条**根本测不出来**（会被误判成死任务）。
驱动脚本因此自己 `kill -TERM` **只杀 uvicorn 那一个 PID**，并**等端口真的不再响应**才起下一代。

| 相 | 断言 | 覆盖 |
|---|---|---|
| 1 | **49/49** | 健康/前端零外链 · 权威闸门态与锚 · 拒绝矩阵四次（I6/枚举/I4/缺 actor）都不消耗中断 · 签 G1 · N9 提交 · E-2 探测 · 事件白名单 |
| 2 | **27/27** | 重启后重附着同一作业 · 两套口径并列（1687 / `UVM_ERROR=0`）· 分歧不判绿 · G2/G3 拒绝矩阵 · 写 G2/写 G3 |
| 3 | **18/18** | 收敛为 `finished` · 三闸门各恰好一次 · 权威账本三门皆人类签署 · 终态锚一致 · 事件 seq 连续 · N16 dry-run 对 `kb/baselines/` 零副作用 |
| 4 | **8/8** | 长任务停放（执行在中断、单槽持有、快照已落、终态不误占锁） |
| 4b | **8/8** | **重启时确有作业在跑**（`jobs.running=1`）· 重附着到**同一在跑作业** · 跨重启**锁没丢** · 取消后失败并释放锁 |
| 5 | **6/6** | 死任务判死（不当成功）· 释放单槽 · 事件流记 `dead_job` |

## 2 关键原始输出（命令输出复制，非手算）

```text
# 3 次真重启：四代 uvicorn 的 PID 各不相同
[driver] 服务已起 pid=17（第 1 代）      [driver] 已停 uvicorn pid=17（未触碰长任务）
[driver] 服务已起 pid=101（第 2 代）     [driver] 已停 uvicorn pid=101（未触碰长任务）
[driver] 服务已起 pid=143（第 3 代）     [driver] 已停 uvicorn pid=143（未触碰长任务）
[driver] 服务已起 pid=223（第 4 代）     [driver] 已停 uvicorn pid=223（未触碰长任务）

# 第 4 代启动时的恢复报告：**确有作业在跑**，本 run 被恢复
restore_report = {'restored': ['RUN-20261015-171829'], 'failed': [],
                  'jobs': {'running': 1, 'done': 1, 'dead': 0, 'undelivered': 0}}
重启后 = {'status': 'waiting_gate', 'job': 'JOB-df43dbbaf5de', 'phase': 'running',
          'slot': {'locked': True, 'holder': {'format_version': 1, 'owner_pid': 143,
                    'job_id': 'N9-RUN-20261015-171829', ...}, 'holder_alive': False}}

# 双计数并列、分歧不判绿
counts.koutou1.value = 1687        counts.koutou2.value = {UVM_ERROR: 0, UVM_FATAL: 0, ...}
both_zero = False                  verdict.passed = False
verdict.must_not = 口径二为 0 不足以判绿：口径一非 0 时**不得**判跑通。

# 闸门权威（gates.json + gates.sha256）：三门皆人类签署、锚一致、与事件流无分歧
{'G1_diff_confirm': {'decision':'confirmed','human_signed':True,'actor_kind':'human','history_len':1},
 'G2_report_accept': {'decision':'accept',   'human_signed':True,'actor_kind':'human','history_len':1},
 'G3_regression_decision': {'decision':'defer','human_signed':True,'actor_kind':'human','history_len':1}}
anchor_ok = True   divergences = []

# 收敛（F-V1-04 修复后；此前永远卡在 running）
node_history = [... 'N12','N13','N14','HALT']    status = finished
kb/baselines 内容摘要(前/后) = 34aa3b60…  ==  34aa3b60…（逐行不变 ⇒ N16 零副作用）

# 死任务：判死 + 释放锁 + 失败原因可见（F-V1-07 修复后）
{'status': 'failed', 'job': {'phase': 'dead', 'rc': None}, 'error': '投递失败：RuntimeError: 死任务 …⇒ 不得当成功'}
```

## 3 本轮抓出并修掉的缺陷（**这部分才是重点**）

### F-V1-01（major）拒绝路径会往权威账本写「孤儿签名」
`RunManager.decide()` 原顺序是"先 `gate.py sign` 落权威、后查有无待处理中断"。闸门已被决策过时
（典型触发：**双击按钮 / 两个标签页各点一次**），`gates.json` 的 `history` 会多一条记录、账本被改，
而执行侧毫无动作，用户只看到一个 400 —— 权威与被控对象悄悄分叉。
**修法**：先确认本闸门确有待处理中断，再写账本（与本层 §4.4「拒绝必须发生在提交前」同一纪律）。
**回归**：`test_double_decide_leaves_no_orphan_signature` 断言拒绝后 `gates.json` **md5 不变**。

### F-V1-02（major）操作台的「闸门历史」不是权威，且前端在渲染一个服务端从不发送的字段
`gate_history` 由**事件流**派生：`actor` 是 HTTP 请求体里的**自报字符串**，既无 `human_signed`
也无 `actor_kind`；而前端 `renderGateHistory` 恰恰在渲染 `json.actor_kind` ⇒ **徽章永远是空的**。
"这道闸门到底是不是人类签的、账本改过没有"——操作台最该回答的问题，界面上答不了。
**修法**：新增 `host/gate_authority.authority_view()`（`kb_lib.gate_get` + `gate_verify_anchor`）
→ `run_view.gates_authority`（含 `human_signed`/`actor_kind`/`history[]`/`anchor_ok`），
并把**事件流 vs 权威账本**的逐门对账结果作为 `divergences` 外显（分歧不得静默取其一）；
前端改渲染权威态 + 锚 + 分歧，事件流降级为明确标注的"自报"列表。
**回归**：`test_view_projects_authority_not_just_events`、`test_gate_divergence_is_reported_not_hidden`、
`test_authority_projection_fails_closed_without_ledger`。

### F-V1-03（minor）`POST /api/runs` 的 `now` 被静默丢弃
`RunManager.start(now=…)` 声明了却从未使用，run_id 与时间戳实际都来自 `LOOP_NOW`/`KB_NOW` 或墙钟
⇒ 调用方以为定住了 run 身份，实际拿到另一个 run。
**修法**：`now` 生效（显式优先于环境变量），非法值 400。
**回归**：`test_start_honors_now`、`test_invalid_now_is_rejected`。

### F-V1-04（major）走到终止节点后执行**永不关闭** ⇒ run 永远显示"进行中"
`create_execution(auto_close=False)` 关掉了框架里**唯一**会把生命周期置为 CLOSED 的机制
（`Execution._auto_close_monitor`，而它对 `is_waiting()` 是安全的、不会关掉停放中的闸门）⇒
`is_closed()` 恒假、`async_sync` 里 `doc.status="finished"` 那个分支**是死代码**。
实测：`G3=defer` 走到 HALT 后 `status=running` 永不收敛；且 `async_restore_all()` 按
`status in (waiting_gate, running)` 筛选 ⇒ **每次重启都把这些僵尸 run 再恢复一遍**。
**修法**：声明 `TERMINAL_NODES = {HALT, N16}` + `reached_terminal(events)`；`async_sync` 在终止节点
**显式** `execution.async_close()`；投影侧 `_status_of()` 再用事件流兜底判一次（不盲信落盘状态）。
**回归**：`test_full_drill_loop_to_n16_refusal`（补 finished 断言）、
`test_g3_defer_halts_and_run_converges_to_finished`、`test_terminal_detection_helper`。

### F-V1-05（blocker，崩溃恢复路径）死任务被当「正常完成」投递
`JobRunner._persist_finish()` 把更新后的**副本**写盘、却把**原记录**留在 `JobStatus.record` 里 ⇒
`reattach()` 放进 `undelivered` 的记录 `phase` 还是陈旧的 `"running"` ⇒ 补投递据此恢复 `n9_park`，
`payload["phase"]` 不是 dead/cancelled ⇒ **走成功分支**、读到空证据、`status="fail"`，
run 带着 `koutou1=null` 一路走到 **G2 人工闸门**（而不是失败）。这条正是崩溃恢复路径，也是最难被测到的路径。
**修法**：① `poll()` 返回的 `record` 改为磁盘上的**权威记录**；② `n9_park` 恢复时**不再相信
resume 载荷的相位**，一律回读 `JobRunner.poll()`（rc 文件 + 进程存活），相位不一致时另发
`phase_disagreement` 事件；`phase` 既非 done 也非 dead/cancelled 时**宁可失败**；
③ 补投递失败必须把 run 标成 `failed`（原先只记进报告的 `failed[]`，run 仍停在 `waiting_gate`
—— 正是 §4.3 要防的"把崩溃伪装成在等人工"）。
**回归**：`test_crash_recovery_delivers_dead_job_as_dead_not_done`；另在 `test_flow`
既有的死任务/取消用例上验证不退化。

### F-V1-06（major）快照靠"碰运气"落盘 ⇒ 重启会回退到**已签**闸门
落快照只在 `async_sync()` 恰好观察到 `waiting_gate` 时发生，而 `async_sync` 只在
`start`/`decide`/`_deliver` 结尾被调用，这三处都可能是"执行正在跑"。
实测：happy drill 从 G1 跑到 G2 只用约 1.3 s，两次 `async_sync` 都看到 `running` ⇒
盘上只剩停在 **G1** 的那份快照（`view.json` 卡在 `running`、`notes` 空），
而账本里 G1 已是 `confirmed` ⇒ 恢复后 run 停在**一个已经签过的闸门**上
（`pending=['G1_diff_confirm:0']`），phase 2 直接失败。
**修法**：① 新增 `_snapshot_ticker()`（0.5 s 节拍）保证"停在中断上"的执行必然落盘；
② 恢复时与权威账本对账 —— 若停在**账本已签**的闸门上，判定快照落后，
**显式失败**并说明原因（`snapshot_behind_ledger` 事件 + `error`）。
**刻意不自动重放该决定**：重放等于在没人要求的情况下自动重跑一整轮修订 + 仿真（可能是几十分钟的
外部作业）。按本层一贯口径，宁可显式失败也不静默替人推进。
**回归**：`test_park_snapshot_is_written_without_opportunistic_sync`、
`test_restore_refuses_when_snapshot_lags_the_ledger`。

### F-V1-07（major）投影不携带 `error` ⇒ 失败的 run 看不到原因
`contracts.run_view()` 的返回里**根本没有 `error`**，前端也不渲染它 ⇒ `status=failed` 的 run
在操作台上只剩一个 "failed" —— N9 死任务 / 补投递失败 / 快照落后于账本 三条失败路径的原因**全被吞掉**。
**修法**：投影补 `error` + `notes`；前端在状态条下方渲染醒目的"运行失败"块与 note 列表。
**回归**：`test_decision_response_gate_state_is_authority_not_process_record`（同名一类的字段名与
内容不符问题）以及 phase 5 的实机输出（现在能看到 `error=投递失败：RuntimeError: 死任务 …`）。

### F-V1-06c（major）快照停在**已终结作业**中断上 ⇒ run 永久卡在 JOB
F-V1-06 的竞态换了位置后暴露：补投递发生在快照落盘**之后**，于是盘上快照仍停在 `JOB:` 中断，
而作业记录已是 `delivered=True` ⇒ **没有任何补投递会再来**，run 永远停在 JOB、永不收敛。
（实测：在独立工作区复跑本终验时第 2 代就是这样。）
**修法**：恢复时 `_stale_job_interrupts()` 按 `JobRunner.poll()` 的**权威相位**识别"停在已终结作业上"，
强制重投递该结局 —— **只读取已跑完作业的结局，不重跑外部作业**。投递路径仍只有一条：
不另起分支，因为两条路径各带一套错误处理必然分裂（实测把死任务路径弄坏过一次）。
**反证（真跑）**：把 `_stale_job_interrupts` 换成返回 `[]` ⇒ 回归测试立刻失败并报
「仍卡在 JOB 中断：status=waiting_gate」。

### F-V1-08（blocker，只在恢复路径触发）重投递复用旧 `resume_request_id` 被**静默拒绝**
`resume_request_id` 是 TriggerFlow 的**去重键**。第 1 代已用 `JOB-x:done:0` 投递过一次；
恢复时沿用同一 id，框架判为重复投递且**只打日志、不抛错**：
```
ERROR [triggerflow.resume_dispatch_failed] resume request 'JOB-…:done:0' for interrupt 'JOB:JOB-…' changed phase.
```
而 `async_continue_with` 正常返回 ⇒ 我们照常 `mark_delivered` ⇒ run 永久卡住。
**修法**：① 强制重投递一律换**新的** id（`…:restore:<本次进程实例>:<n>`）；
② **核验执行体** —— 投递后若该中断仍在等待，抛错且**不标记已投递**，把静默空操作变成显式失败。
这是"不信返回值、查执行体"纪律的又一次直接命中。

### 顺带修掉的字段名与内容不符（`gate_state` 装的是子进程记录）
`POST …/gates/{gate}/decision` 的响应字段 `gate_state` 实际装的是 `gate.py` 的子进程调用记录
（`cmd`/`rc`/`stdout_tail`）⇒ 读 `gate_state.human_signed` 只会得到 `undefined`，界面在签署后
看不出是否人签。**修法**：拆成 `gate_state`（**权威**闸门态那一条）+ `gate_tool`（原始调用记录）+ `gates_authority`。

## 4 本轮**没有**消解的事（不得当成已具备）

| 项 | 现状 |
|---|---|
| `mode="real"` 全跑 | 仍未在真机跑过完整一轮（单用例 ≈19 min，修订后可达 22.8 h）。drill 全链路已全绿。|
| 拆仓后的数据位置 | 本轮只在**软件迁出、数据暂留旧位置**的模式下复验（`LOOP_WORKSPACE=<旧环境仓>/kb`）；把数据搬进 `workspaces/` 属第 4 步，未做。|
| I3 口径分歧 | 口径一 = 1687 ≠ 0 是**既有缺陷**，判绿路径未通。三选项与推荐见 `kb/adjudication/I3_dual_count_dispute.md`（**需人拍板**）。|
| C1—C72 | 72 条全 `blocks_release=true` ⇒ 晋升永久阻断。分组与清零路径见 `kb/adjudication/C_conflicts_triage.md`（**需人拍板** + 缺 human-only 裁决工具）。|
| 快照落后于账本 | 现在会**显式失败**并说明原因，但不会自动恢复；修复路径（更频繁落盘）只降低了发生率，未消除竞态窗口。|
| 单槽 `holder_alive` 语义 | 重启后 `slot.holder.owner_pid` 指向**已死的 uvicorn**，`holder_alive=False`，而作业其实还活着（`phase=running`）。本轮实测未发现别的 run 能借此抢占，但该字段的语义需要复核（建议改判"作业是否存活"而非"进程是否存活"）。|
| N6 不真改沙箱 `.sv` | 只产出修订方案，v1 边界。|
| 单机单用户 | 无鉴权；`actor` 是自报字符串（权威账本里的 `human_signed` 才是真凭据）。|
