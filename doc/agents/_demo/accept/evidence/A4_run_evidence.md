# A4 运行证据 · 卡点 D 真实全跑（`tc_dom_polling_trig_chk_01`）

> ## ★ 身份映射（先读这一条，避免把三次尝试混起来）
> 本文件**跨越三次尝试**；**唯一跑完并出结果的是 attempt 3**：
>
> | 尝试 | 被跑的用例 | 结果 | 记录位置 |
> |---|---|---|---|
> | attempt 1 | **v3** `235d20a5…` | 中止（预置段墙钟 >1 小时） | **§0~§6**（原始记录，保留不改以存真） |
> | attempt 2 | **v4** `33cc907f…` | 中止（观测窗 30ms ⇒ ≈2.4 小时） | **§7** |
> | **attempt 3** | **v6** `8ad474be7928496487517a8666691d78` | **✅ 通过**（49 分 52 秒；`UVM_ERROR/FATAL:0`、脚本 `*E`=0、`Pass!`、观测到 `0x4`×10→`0x2`） | **§8** |
>
> ⇒ **§0~§5 里出现的 `v3` 是 attempt 1 的身份，不是最终结论**；最终身份与结论一律以 **§8** 为准。
> （此说明由 Lead 于 A6 守护者登记后补入；A6 审计窗口内本文件的修订已按 M-H 记录。）

> **执行人：Lead**（`task-11` 由 runner 改派给 lead；原因：单次 45 分钟，长轮次交由 Lead 亲自执行更稳）。
> **上游规格**：`doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` §3 / §4 / §5 V4；三方输入见 `review/A3c_review_v3.md` §6。
> **入口条件**：A3'' 已判「通过」并**明确背书** v3（md5 `235d20a5f2cc7b4911201c8939a14b81`）可进入全跑。

---

## 0 身份（run identity）

| 项 | 值 |
|---|---|
| `run_id` | `A4-20261014T1428` |
| 用例名 | `tc_dom_polling_trig_chk_01` |
| seed | `1`（`-d 1`） |
| **被跑的那一份（v3）md5** | **`235d20a5f2cc7b4911201c8939a14b81`** / 44143 B / 607 行 |
| v3 归档（只复制不移动） | `doc/_run_artifacts/tc_dom_polling_trig_chk_01_v3.sv` = 同 md5 ✅ |
| 命令原文 | `./doc/tools/run_local.sh -c tc_dom_polling_trig_chk_01 -d 1` |
| 起跑时刻 | `2026-10-14 14:27:5x`（见 §3 落盘时刻） |
| 完整 stdout | `SIMLIB_RUN/log/a4_run_stdout.log`（`> … 2>&1`） |

## 1 跑前快照（Lead 取，2026-10-14 14:27:48）

| 项 | 值 | 判据 |
|---|---|---|
| 沙箱 v3 | md5 `235d20a5f2cc7b4911201c8939a14b81` / 44143 B / 607 行 | 与 A3'' 背书一致 ✅ |
| `uvs.setup` vs 夹具 | **一致（rc=0）** | 与 `doc/_run_artifacts/uvs.setup.orig` 比 |
| `TESTLIB/*.sv` 计数 | **162** | §8 基线 |
| `TESTLIB/` 口径A摘要 | **`4c0942ac419f67c6fdb391dd2083f0b3`** | `md5sum TESTLIB/*.sv \| LC_ALL=C sort \| md5sum` |
| `git status --porcelain TESTLIB` | **34** | 基线 |
| 并发现场 | **0 个进程**（`uvlan`/`uvs`/`run_local`/`compile_only` 全无） | §4 串行纪律 |

## 2 临时放置（§3 纪律）

| 步骤 | 结果 |
|---|---|
| 只新增 `TESTLIB/tc_dom_polling_trig_chk_01.sv` | 未改动/删除任何既有文件 |
| 放入后 `TESTLIB/*.sv` 计数 | **163**（162 + 1）✅ |
| 放入后口径A摘要 | `1d3e1390a858b8620eafa1cb281285bd` |
| 放入后新文件 md5 | `235d20a5f2cc7b4911201c8939a14b81`（= 沙箱 v3）✅ |

> **为什么必须归档 v3**：第 5 步会把它从 `TESTLIB/` 删除；不先复制归档，"跑的那一份"就跑完即灭、本次全跑不可复现。

## 3 执行时间线

| 时刻 | 事件 |
|---|---|
| 2026-10-14 14:27:48 | 跑前快照 + 归档 v3 + 放入 `TESTLIB/`（Lead，前台） |
| 2026-10-14 14:27:5x | **启动全跑**（后台 job `bash-45`，stdout 落 `SIMLIB_RUN/log/a4_run_stdout.log`） |
| （待补） | 全跑结束 |

## 4 结果（attempt 1 未产出 —— 见 §8 的最终结果）

- [ ] 三段日志路径 + 行数
- [ ] `UVM Report Summary` 原文片段（`UVM_ERROR` / `UVM_FATAL` / `UVM_WARNING`）
- [ ] **脚本口径** `*E` 计数：`egrep -c '(\*E|\*F|\*e|ERROR:)' <run.log>`
- [ ] **独立口径** `UVM_ERROR` 计数：`grep -c 'UVM_ERROR' <run.log>`
- [ ] 是否出现 `Pass!`
- [ ] 通过 / 不通过（三条判据：`UVM_ERROR:0` ∧ `UVM_FATAL:0` ∧ 脚本 `*E` 计数 0）

## 5 还原复验（attempt 1 已由 Lead 手工完成，见 §6.4；最终一次见 §8.5）

- [ ] `TESTLIB/*.sv` == **162**
- [ ] 口径A摘要 == **`4c0942ac419f67c6fdb391dd2083f0b3`**
- [ ] `git status --porcelain TESTLIB` == **34**
- [ ] `uvs.setup` vs 夹具 `diff` rc == 0
- [ ] 无遗留锁 `SIMLIB_RUN/.compile_only.lock`

---

## 6 第一次尝试（attempt 1）：**中止 —— 发现"墙钟成本模型"错误**

> **这一节是本次验收最有价值的产出之一**，它记录了一个**只有真实全跑才能发现**的问题。

### 6.1 事实（全部由命令输出复制）

| 项 | 值 |
|---|---|
| 起跑 | `2026-10-14 14:27:55`（job `bash-45`） |
| 中止 | `2026-10-14 14:41:0x`（Lead 主动 `job_kill`） |
| 已运行墙钟 | **≈13 分钟** |
| elaborate 实测 | **17.47s**（`a4_run_stdout.log:2529`，比报告里"≈4 分"更快）+ 215 targets 并行编译 |
| 推进到的仿真时刻 | `14:29:32 = 236.957us` → `14:40:54 = 2713.277us` |
| **实测仿真速率** | Δ`2476.320us` / Δ`682s` = **3.63 us-sim/s ≈ 0.218 ms-sim/分钟** |
| 中止时 run.log | 435 行 / 21005 B / md5 `def5410ff890c855…`（16 位截断，全值见 A6 §4）（已复制留档 `SIMLIB_RUN/log/archive_a4_attempt1_run.log`） |

### 6.2 根因：**被计的是"预测的仿真时间"，真正的成本是"密集总线读的笔数"**

实测 **≈3.3 秒墙钟 / 每笔 BMC SPI 读**（读间隔 12.32us 仿真时间）。

用例的仿真时间预算（v3）：`PRESET_BUDGET = 30ms`、`OBS_WINDOW = 30ms`、`DONE_TIMEOUT = 120ms`。

**但墙钟成本与"仿真时间"几乎无关，而与"是否密集读"强相关**：

| 段 | 仿真时间 | 事务特征 | **墙钟成本** |
|---|---|---|---|
| **预置段** `for i < 8×4 = 32` 轮，每轮 `polling_data_chk`（读 128 字）+ `set_data_ram` | ≈12.63ms（作者实测） | **密集读**（背靠背 ~12.32us/笔） | **≈1 小时以上** ← **瓶颈** |
| **观测窗** 30ms（`SAMPLE_GAP = 3ms`） | 30ms | 窗内只 **~10 笔**读，其余是**纯空转** | **≈34 秒**（几乎免费） |
| 兜底 120ms | 120ms | 纯空转 | 几乎免费 |

⇒ **反直觉但已实测**：**"30ms 观测窗"比"12.63ms 预置段"便宜约 100 倍**。
因为空转的仿真时间在事件驱动仿真器里**不花墙钟**，而密集读每笔都要 3.3 秒。

投影（不改用例）：预置还剩 ~10ms ≈ 45 分钟；随后 30ms 观测窗 ≈ 34 秒；**合计 ≈50 分钟**（若走到 120ms 兜底另加空转，仍便宜）。
—— 但若保持 32 轮预置，**仅预置段就要 1 小时以上**；这是不可接受的。

### 6.3 为什么这算"用例错"（分类 1），而不是环境问题

作者把 `PRESET_BUDGET` 的依据写成"实测 12.63ms × 2.4"，**只算了仿真时间、没算墙钟**，也没意识到
"预置段是本用例唯一的密集读扫"。而 `ACCEPTANCE_PLAN` §1 已经声明 **U1：不断言 polling 数据窗内容** ——
既然不拿它做判据，**就没有必要把 8 台控制器 × 4 通道全扫一遍**。
⇒ 这是**代价模型与判据需求脱节**，属用例侧可修项。

### 6.4 中止后的还原（已全部完成并复验）

| 项 | 结果 |
|---|---|
| 残留进程 | **0** |
| `TESTLIB/*.sv` | **162**；口径A摘要 = **`4c0942ac419f67c6fdb391dd2083f0b3`**（= 基线）✅ |
| `git status --porcelain TESTLIB` | **34**（= 基线）✅ |
| 临时文件 `TESTLIB/tc_dom_polling_trig_chk_01.sv` | 已删除 ✅ |
| `RTL/`、`TB/`、`PKG/` 今日改动 | **0 个文件** ✅ |
| `git status` 总项 / ` M` | 49 / 18（= 基线）✅ |
| `LOG/` 文件数 | 78 ✅ |

### 6.5 ★ 中止暴露的**机制缺口**（交 A6 守护者登记）

`job_kill`（SIGTERM 打到进程组）中止后，**`uvs.setup` 没有被还原**：
中止时实测 md5 `ec7f87c95e443c048a4d6d514cf83691` ≠ 夹具 `a80f7b6ca48a7961a107bbe871af761d`。
`run_local.sh` 的 `trap EXIT` **只在正常退出时生效**，进程组被信号打断时不执行。

**Lead 已手工还原**（`rm -f uvs.setup && cp 夹具 uvs.setup`，diff rc=0，md5 回到夹具值），
并把权限从 `444`（`cp` 会带过来）改回 `664`。
⇒ **这是一条真实的机制缺口：`trap` 不覆盖"被杀死"这一路径**；而全跑一次 45 分钟以上，被中止的概率不低。

---

## 7 第二次尝试（attempt 2）：**中止 —— 推翻了"空转仿真时间免费"这个结论**

| 项 | 值 |
|---|---|
| 起跑 | `2026-10-14 14:52:16`（job `bash-47`） |
| 中止 | `2026-10-14 15:14:5x`（Lead 主动 `job_kill`） |
| 已运行墙钟 | **≈22 分钟** |
| 推进到的仿真时刻 | `3594.793 us`（**样本 #2**，`i2c_sta=0x00000004`，busy=0 err=0） |
| **实测速率** | 14:52:16 → 15:09:25 共 1029s 推进 3.595ms ⇒ **3.49 us/s ≈ 0.209 ms/分钟** |
| run.log | 273 行 / 13821 B / md5 `7c46f7431afafa26…`（16 位截断，全值见 A6 §4）（已留档 `SIMLIB_RUN/log/archive_a4_attempt2_run.log`） |

### 7.1 ★ 被推翻的结论（attempt 1 §6.2 的那条）

attempt 1 我写下："**空转的仿真时间几乎不花墙钟**"、"30ms 观测窗 ≈34 秒"。
**attempt 2 实测证明这是错的**：样本间隔 `SAMPLE_GAP_NS = 3ms` 仿真，**每 3ms 要 ≈14 分钟墙钟**。

**修正后的成本模型**：

> **墙钟成本 ≈ 仿真时间 × 活动因子**。
> 在 `0x80` 使能、**DUT 轮询引擎持续工作时**，活动因子极高 ⇒ **≈0.21 ms 仿真 / 分钟**（1ms 仿真 ≈ 4.8 分钟墙钟）。
> **"笔数"不是主因**（attempt 1 的"3.3 秒/笔"只是在密集读场景下的**表象**）。

**证据（可直接复核）**：
- 样本 #1 在 `≈0.59ms`、样本 #2 在 `3594.793us`，两点各间隔 3ms 仿真 ⇒ 20 分钟只走了 2 个样本；
- 45 秒静止观测（15:13:10 → 15:13:55）期间 run.log 的仿真时刻**完全不动**（`3594.793us`），
  但 `SIMLIB_RUN/wave/…/*.usdb` **仍在持续写入**（mtime 15:14:22）⇒ 仿真**活着**，只是极慢。

### 7.2 后果（决定性）

| 段 | 仿真时间 | **实测/推算墙钟** |
|---|---|---|
| 预置（v4 已砍到 1 轮 = 32 笔） | ≈0.42ms | ≈2 分钟 ✅ |
| **观测窗 `OBS_WINDOW_NS = 30ms`** | 30ms | **≈2.4 小时** ❌ |
| `DONE_TIMEOUT_NS = 64ms` 兜底 | 64ms | ≈5 小时 ❌ |

⇒ 观测窗是**唯一**不可接受的项（预置已不再是瓶颈）。**v5 必须收敛观测窗**（见 `task-23`）。

### 7.3 中止后的还原（已全部完成并复验）

| 项 | 结果 |
|---|---|
| `TESTLIB/*.sv` | **162**；口径A摘要 = **`4c0942ac419f67c6fdb391dd2083f0b3`**（= 基线）✅ |
| `git status --porcelain TESTLIB` | **34**（= 基线）✅ |
| 临时文件 | 已删除 ✅ |
| `uvs.setup` | **再次未被 `trap` 还原**（`ec7f87c9…`）⇒ Lead 手工还原为 `a80f7b6c…`（diff rc=0）并把权限改回 `664` ✅ |
| 冻结件 | `RTL`/`TB`/`PKG` 今日改动 0；`git` 49/18 ✅ |

### 7.4 ★ 另一条机制缺口：**`ps` 检查在沙箱里不可靠**

attempt 2 期间，我（Lead）与 runner 都执行过 `ps -ef | grep -E "uvlan|uvs|run_local"`，**全部返回 0 个进程**，
而当时仿真**确实在跑**（波形文件持续增长）。原因：bash 工具在 `bwrap --unshare-pid` 命名空间内执行，
**看不到外部的仿真进程**。

⇒ **卡点 D 的"串行确认"不能只靠 `ps`**。可靠的替代信号（本轮实测可用）：
1. `uvs.setup` 的 md5 是否已回到夹具值（未回 = 脚本仍活着，因为 `trap` 只在退出时跑）；
2. `SIMLIB_RUN/wave/<tc>_<seed>/*.usdb` 的 **mtime 是否在持续更新**（更新 = 仿真活着）；
3. `SIMLIB_RUN/.compile_only.lock` 是否存在（仅覆盖编译门）。

**这是一条应写进 `compile_only.sh`/`run_local.sh` 与角色定义的机制修正**，交 A6 登记。



---

## 8 第三次尝试（attempt 3）：**✅ 通过 —— 完整跑出结果**

> **执行人：Lead**（`task-11`）。这一次**跑完了**，并产出了完整 `UVM Report Summary`。

### 8.1 身份

| 项 | 值 |
|---|---|
| `run_id` | `A4-20261014T1532` |
| 用例 | `tc_dom_polling_trig_chk_01`，seed = **1** |
| **被跑的那一份** | **v6：md5 `8ad474be7928496487517a8666691d78` / 51228 B / 673 行** |
| v6 归档 | `doc/_run_artifacts/tc_dom_polling_trig_chk_01_v6.sv` = 同 md5 ✅ |
| 命令 | `./doc/tools/run_local.sh -c tc_dom_polling_trig_chk_01 -d 1`（stdout → `SIMLIB_RUN/log/a4c_run_stdout.log`） |
| 起止 | `2026-10-14 15:31:55` → `16:21:47`，**墙钟 49 分 52 秒** |
| 脚本退出码 | **0** |
| run.log | **379 行 / 20398 B / md5 `396a3d2b13bcb0c60c403e33c6aa64d9`** |

### 8.2 ★ 两套口径（都必须记，谁也不替谁）

| 口径 | 值 |
|---|---|
| **脚本口径**（`run_uvs_new.sh:296` 的 `egrep -c '(\*E\|\*F\|\*e\|ERROR:)'`） | **0** |
| **独立口径**（`UVM Report Summary`） | `UVM_ERROR : 0`、`UVM_FATAL : 0`、`UVM_WARNING : 0`、`UVM_INFO : 57` |

**⇒ 两套口径一致，均为"无失败"。本次没有踩到 §7.1.1 那个"UVM 有 error 而脚本计数为 0"的陷阱。**

`Final_phase status: **Pass!**`（`test_lib.sv:286`）；`END pid=0: samples=11 seen_busy=1 err_seen=0 changed=1 hi_bad=0`。

### 8.3 ★ 观测到的"状态变化"（这正是用户要的"读寄存器状态变化"）

`0x403c i2c_sta` 的**完整采样序列**（1ms 栅格）：

```
sample#1  @  582.473us : i2c_sta=0x00000004   (bit2)
sample#2  @ 1594.793us : i2c_sta=0x00000004
sample#3  @ 2607.113us : i2c_sta=0x00000004
sample#4  @ 3619.433us : i2c_sta=0x00000004
sample#5  @ 4631.753us : i2c_sta=0x00000004
sample#6  @ 5644.073us : i2c_sta=0x00000004
sample#7  @ 6656.393us : i2c_sta=0x00000004
sample#8  @ 7668.713us : i2c_sta=0x00000004
sample#9  @ 8681.033us : i2c_sta=0x00000004
sample#10 @ 9693.353us : i2c_sta=0x00000004
sample#11 @10705.673us : i2c_sta=0x00000002   ← bit1 = BUSY
```

⇒ **闭环成立**：使能(`0x9c` BMC SPI) → 触发(`0x80` PCIE，读回 0x00000000→0x00000001) → **读到 `i2c_sta` 由 `0x4` 变为 `0x2`（BUSY 置位）**。
**EARLY_EXIT 按设计生效**：`EARLY_EXIT after 11 samples @10705.673us (O7 busy seen & O8 value changed)` —— 若无早退会走满 12ms 窗。

### 8.4 观测点清单（A3f 给出的 9 条通过印记，**全部命中**）

| 观测点 | 结果 |
|---|---|
`ENABLE_RDCHK` | 通过（`0x9c` 写 0x1ff 后读回一致）
`STA_IDLE_BEFORE` (O2b) | 通过 —— `pre-trigger i2c_sta=0x00000004 busy(bit1)=0 (idle, stale-1 excluded)`
`TRIG_BEFORE` / `TRIG_AFTER` | 通过 —— `RD=0x00000000` → `RD=0x00000001` == EXP
`STA_SAMPLES_SHORT` (O4) | 通过 —— `samples=11 >= MIN_SAMPLES=3 (read_timeout_seen=0)`
`STA_RESERVED` | 通过 —— `all samples bits[31:3] == 0`
`STA_ERR_CLEAR` | 通过 —— `err(bit0) never set in the window`
**`STA_BUSY_SEEN` (O7)** | **通过 —— `busy(bit1)==1 observed at least once`**
**`STA_CHANGED` (O8)** | **通过 —— `value changed across 11 samples`**

### 8.5 还原复验（全跑后）

| 项 | 结果 |
|---|---|
| `TESTLIB/*.sv` | **162**（临时用例已删）✅ |
| `TESTLIB/` 口径A摘要 | **`4c0942ac419f67c6fdb391dd2083f0b3`**（= 跑前基线，既有文件零改动）✅ |
| `git status --porcelain TESTLIB` | **34**（= 基线）✅ |
| `uvs.setup` | **`a80f7b6ca48a7961a107bbe871af761d`**（= 夹具，diff rc=0）—— **本次正常退出，`trap` 生效** ✅ |
| `RTL/`、`TB/`、`PKG/` 今日改动 | **0 个文件** ✅ |
| `git status` 总项 / ` M` | 49 / 18 ✅ |
| 遗留锁 | 无 ✅ |
