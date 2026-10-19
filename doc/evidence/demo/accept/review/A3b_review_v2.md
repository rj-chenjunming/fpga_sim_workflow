# A3' 聚焦复验（v2）— D-1/D-2 是否真消除 + 有无夹带改动

> **复核者**：`simenv-checker`（非作者）｜**任务**：`task-16`（rev 2，owner=simenv-checker）
> **复核时刻**：2026-10-14 14:15–14:18 +0800｜**引用 md5 于 2026-10-14 14:17:26 +0800 重取**
> **上游**：`ACCEPTANCE_PLAN.md`（`5d1b230241c9667a8296c7fe23bd2199`）§2 A3 / §5；上一轮 `review/A3_review.md`（`999445d1a6fe7cbbd19ff5c1a4388707`，结论=退回）
> **唯一写权**：`doc/agents/_demo/accept/review/`（本件为**新文件**，未覆盖 `A3_review.md`）｜未修改用例 / `RTL/` / `TB/` / `PKG/` / `TESTLIB/` / v1 归档件
> **口径纪律**：只到**编译 + 静态**。本文件**不含任何功能级/时序级结论**；所有"实测"均为**历史日志**的只读引用。
>
> # 结论（先行）
> # 退回（逐条依据）
> **本轮主问全部答对**：**D-1 真消除**（`samples < MIN_SAMPLES` 可达、可失败）；**D-2 真消除**（O5~O8 全部嵌套在 `samples >= MIN_SAMPLES` 分支内，"采样不足"只由 O4 独立报出）；**D-3/D-4/D-5/D-6/D-8 全部改到位**；**未发现超范围夹带改动**。
> **但 D-1 的修法引入了一条新的失败面收窄 → 主因 1 条：**
> **D-10（新）**：v1 的 `STA_RD_TIMEOUT` 双写失败点**被整条删除**，超时改为 `rd_to_seen=1'b1; break;`（v2 `:513-518`，**无任何 `*E`/输出**）。于是当超时发生在**第 4 次采样及以后**（`samples ≥ MIN_SAMPLES=3`）时，`O4`（`:543`）**通过**、`O5~O8` 照常裁决 ⇒ **一次真实的"总线读超时"可以零 `*E`、零 `UVM_ERROR` 地过去**（v1 会判 FAIL）。这属 Lead 点名的"**断言被放宽/弱化**" ⇒ 判退回。
> **修法 1 行**：`if (samples < MIN_SAMPLES) begin` → `if ((samples < MIN_SAMPLES) || rd_to_seen) begin`（消息里已打印 `read_timeout_seen`，改文案即可）；或恢复超时分支的 `fail_both`。
> 另有 **D-11（我自己上轮的行号错，须随改）**：D-6 引用的 `pcie_sequence.sv:869/:875` 应为 **`:870/:876`**（`869/875` 是紧邻的 `t0 = $time;` 行）—— 该行号**源自我上一轮 A3 复核件**，作者照抄，故由我更正并负责。

---

## 0 身份与引用（md5 重取 = 2026-10-14 14:17:26 +0800）

| 文件 | md5 | 字节/行 |
|---|---|---|
| **v2 用例**（被复核）`accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` | `e24aded26476aed9426576da361c0fa2` | 43922 / 605 |
| **v1 归档**（只读）`doc/_run_artifacts/tc_dom_polling_trig_chk_01_v1.sv` | `bc9cd56d4b361f4a5be028d8d24cfc56` | 37468 / 539 |
| v2 证据 `accept/evidence/A2b_compile_evidence_v2.md` | `c087031ae0b571b2c96e749152acadbe` | 9842 / 174 |
| v1 证据 `accept/evidence/A2_compile_evidence.md`（应未被覆盖） | `a09a9a8c7f02d1241d231172f756a12c` | 8898 / 154 |
| 上一轮 `accept/review/A3_review.md`（应未被覆盖） | `999445d1a6fe7cbbd19ff5c1a4388707` | 36660 |
| `accept/ACCEPTANCE_PLAN.md` | `5d1b230241c9667a8296c7fe23bd2199` | — |
| `doc/skills/simenv-test/_FORMAT.md`（§7 已含**复现命令**块） | `8bbc8e57ba663ea11843c35d52b743e8` | — |
| `doc/skills/simenv-test/tc_dom_polling_template.md` | `e2a675913f23bbc48c9a0d3323c00dd7` | 417 |
| 接口文档 | `8e82c835015d3bd728447c113be81cc5` | 2006 |
| `RTL/SRC/imports/SRC/dom_src/dom_i2c_data_ram.sv` | `8b29530dbe56ced329dc4c6cb4dbe5f3` | — |
| `TB/AGENTS/PCIE-Agent/pcie_sequence.sv` | `72b3b9808469bdc4603488f88b65b771` | — |
| `TB/tbtop.sv` | `39e95ecd73604ef672f9644dc61fc06d` | — |
| **v2** rtl/tb 日志 `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log` | `04098ba8b3dfceb0f8d38987cbbcf283` / `bf92a8500f898586ffd89ba119c60fd8` | 86150 / 29201 |
| **v1 归档**日志 `SIMLIB_RUN/log/archive_a2_v1/..._c_{rtl,tb}.log` | `2f8ad76b58e9178f88db49e665bc74b0` / `73f9c6683c1f30744882109998e2eccf` | 同上（字节数巧合相同） |
| v2 stdout `SIMLIB_RUN/log/a2b_compile_stdout_v2.log` | `0a00c163652cb6b321d934cc6cd0df7a` | 114485 / 2105 |
| v1 stdout 归档 `.../archive_a2_v1/a2_compile_stdout_v1.log` | `2c1611766c203b5ba5abee2629aff7ac` | 114485 |
| `uvs.setup` / `doc/_run_artifacts/uvs.setup.orig` | `a80f7b6ca48a7961a107bbe871af761d`（相同） | — |
| `doc/tools/compile_only.sh` | `4d7cf96c2e3acde11c46a5b15632bfa5` | — |
| `accept/TESTLIB_baseline_md5.txt` | `4e5ac033f8c7ac671f1be82bd37ca702` | — |

**diff 规模核对**：`diff` 得 **24 个 hunk**、`<` **57** 行 / `>` **123** 行（合计 **180** 行改动）—— 与 Lead 转述的作者自报**完全一致** ✓（我独立跑出，非采信）。

---

## 1 `diff` 原文（`diff v1归档 v2沙箱`，逐字复制，未编辑）

```diff
64a65,66
> //   O2b STA_IDLE_BEFORE: 触发前 SPI 读 0x403c 的 busy(bit1) 必须 == 0（D-8 采纳的"先 0"）
> //                      失败条件：== 1（触发前引擎就忙 ⇒ 上一轮命令的 stale-1 残留 / 状态机未复位）
67,69c69,75
< //   O4 STA_READ_EMPTY: 30ms 观测窗内成功采样数必须 > 0
< //                      失败条件：== 0（SPI 读通道打空，观测值为空 → 后续断言无意义）
< //   O5 STA_RESERVED  : 每个采样的 bits[31:3] 必须 == 0（文档 :1547 Reserve 位 Reset 0）
---
> //   O4 STA_SAMPLES_SHORT: 30ms 观测窗内有效采样数必须 >= MIN_SAMPLES(=3)
> //                      失败条件：任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回 ⇒ 提前结束采样，
> //                              有效样本数 < 3（总线/agent 卡住）。★ v2 对 A3 D-1 的整改：
> //                              v1 的 `samples==0` 在控制流上不可达（恒真式断言），已删除；
> //                              本判据**可达**（真实触发路径：读超时 ⇒ 提前结束采样）。
> //   O5 STA_RESERVED  : ★仅当 samples >= MIN_SAMPLES 时裁决：每个采样的 bits[31:3] 必须 == 0
> //                      （文档 :1547 Reserve 位 Reset 0）
71c77,78
< //   O6 STA_ERR_CLEAR : 每个采样的 bit0（err，文档 :1545 "1:I2C通信异常"）必须 == 0
---
> //   O6 STA_ERR_CLEAR : ★仅当 samples >= MIN_SAMPLES 时裁决：每个采样的 bit0
> //                      （err，文档 :1545 "1:I2C通信异常"）必须 == 0
74,75c81,83
< //   O7 STA_BUSY_SEEN : 30ms 观测窗内 bit1（busy，文档 :1546 "1:正在通信"）至少一次 == 1
< //                      失败条件：全程 bit1 为 0（polling 未启动 / 1Hz 节拍未跑 / 触发未生效）
---
> //   O7 STA_BUSY_SEEN : ★仅当 samples >= MIN_SAMPLES 时裁决：30ms 观测窗内 bit1（busy，
> //                      文档 :1546 "1:正在通信"）至少一次 == 1
> //                      失败条件：全程 bit1 为 0（polling 未启动 / 节拍未跑 / 触发未生效）
77c85
< //   O8 STA_CHANGED   : 采样值序列必须至少变化一次
---
> //   O8 STA_CHANGED   : ★仅当 samples >= MIN_SAMPLES 时裁决：采样值序列必须至少变化一次
78a87,89
> //                      ★ v2 对 A3 D-2 的整改：样本不足时**不再**落到本判据（v1 会把"采样不足"
> //                        误报成"状态没动"= 假失败），改由 O4 的独立分支唯一报出，一条根因一条 *E
> //   （★ 说明：O4 的"样本不足"一旦成立，O5~O8 一律不裁决 —— 避免一条根因刷出多条失败）
99a111,123
> //   ★ D-8（BUSY 手型）二选一：**① 已采纳"先 0"，并说明为何不必做"后 1 → 再等落 0"**：
> //     - 已做"先 0"：触发**之前**读一次 0x403c，断言 busy(bit1)==0（判据 O2b）。这比模板
> //       `tc_dom_polling_template.md:128-129` 建议的"先等它落 0"更强 —— 它证明的是
> //       "本次 poll 开始前 FSM 确实空闲"，而不是"在观测点等到它落 0"。
> //     - 未做"后 1 → 再等落 0"第二段：模板那段手型是为了在**连续轮询**场景里避免把
> //       "上一轮还没消的 1"当成本次命中（stale-1 假命中）。本用例是**单次新鲜 poll**：
> //       触发前 0x80 已读回 0x0（判据 O2，仅 CPU 可写、且本用例是唯一写者），而 poll 的启动
> //       条件第一步就是 `polling_en_sys`（RTL dom_i2c_data_ram.sv:488-490）⇒ 触发前**不可能**
> //       存在任何已发起的 poll，也就没有可残留的 stale-1；O2b 又把这个结论变成了**读数证据**。
> //     - O8 如何兜住 stale-1：退一步说，若真有上一轮残留的 1，则本次窗口内不会发生新的
> //       poll ⇒ 采样值会**恒定**（0x2 恒 busy 或 0x4 恒 arm）⇒ 恒定 0x2 被 O8（值未变化）抓住，
> //       恒定 0x4 被 O7（从未见到 bit1=1）抓住。两条合起来覆盖 stale-1 的两种表现。
> //       （实测的正常序列是 0x4 ↔ 0x2 交替，见下）
112,114c136,138
< //   · 单笔访问基数 T_acc = 0.32us（背靠背 PCIE/SPI 寄存器访问实测，mode = median = 0.320us、
< //     min 0.224us；来源 LOG/tc_pcie_rw_02_1_run.log 的 10513 条 PCIE_REG_RD 与
< //     LOG/tc_dom_polling_new_01_1_run.log 的 SPI 读节奏）
---
> //   · 单笔访问基数 T_acc = 0.32us（**只给 mode/median/min，不给"条数"**：计数必须附可复现命令，
> //     口径与复现命令见 doc/skills/simenv-test/_FORMAT.md §7；实测 mode = median = 0.320us、
> //     min 0.224us；来源 LOG/tc_pcie_rw_02_1_run.log 与 LOG/tc_dom_polling_new_01_1_run.log 的 SPI 读节奏）
119a144,146
> //   · 采样数下界 MIN_SAMPLES = 3：窗 30ms / 节拍 3ms ⇒ **期望 ≈11 个样本**（首样本 t=0 即采），
> //     取 3 作为"有效证据"的下界（约为期望值的 1/4，容忍数次采样缺失）；实际单笔读 ≤1ms，
> //     正常情形样本数 ≥8，故 3 这个下界**不会**因轻微变慢而误报
121c148,149
< //     （日志 `:213` → `:1274`，含 32 次 polling_data_chk + 32 次 set_data_ram 的库内不定长访问）
---
> //     （日志 `:213` → `:1274`，含 32 轮 × 2 次库调用 = **64 次**库调用：polling_data_chk ×32
> //      + set_data_ram ×32；轮数 = 本文件 for 循环上界 `DOME_PCA9548_NUM × `DOME_CHN_NUM = 8 × 4 = 32）
124,125c152,155
< //        否则会抢在子任务逐条判定之前误报（假失败）；同时覆盖预置段 32 次库调用
< //        （库内**无**超时，靠本兜底封顶）与采样循环约 10 次的调度开销。
---
> //        否则会抢在子任务逐条判定之前误报（假失败）；同时覆盖预置段 64 次库调用
> //        （库内**无报错式**超时：`set_data_ram` 无界；`polling_data_chk` 只有**静默** 50ms
> //         软界 —— pcie_sequence.sv:869/:875，到了也不报错，故障只能靠本兜底封顶）
> //        与采样循环约 11 次的调度开销。
217c247
<     localparam bit [31:0] EXP_POLLING_EN_PRE  = 32'h0000_0000; // 文档 :419 Reset 0x0000（触发前必须还是复位值）
---
>     localparam bit [31:0] EXP_POLLING_EN_PRE  = 32'h0000_0000; // 文档 **位定义表 :503**（Reset 0x0）+ 汇总 :419（Reset 0x0000）两处一致（触发前必须还是复位值）
233a264
>     localparam int MIN_SAMPLES        = 3;           // 有效采样下界（窗 30ms / 节拍 3ms ⇒ 期望 ≈11；取 3 容忍缺失）
357a389
>         bit        rd_to_seen;
406c438,442
<         //    注：库内无超时，整段由 DONE_TIMEOUT_NS(120ms) 封顶（预置实测 12.63ms）
---
>         //    轮数 32 = for 循环上界 `DOME_PCA9548_NUM × `DOME_CHN_NUM = 8 × 4；
>         //    每轮 2 次库调用 ⇒ 共 **64 次**（polling_data_chk ×32 + set_data_ram ×32）
>         //    注：库内**无报错式**超时（`set_data_ram` 无界；`polling_data_chk` 只有静默 50ms
>         //        软界 —— pcie_sequence.sv:869/:875，到了也不报错）⇒ 整段由 DONE_TIMEOUT_NS
>         //        (120ms) 封顶（预置段实测 12.63ms）
413a450,470
>         // 2b) D-8 采纳的"先 0"：触发**之前**读一次 i2c_sta，断言 busy(bit1)==0
>         //     怎样失败：== 1（触发前引擎就忙 ⇒ 上一轮命令残留 stale-1 / 状态机未复位）
>         //     这正是模板 §3.3（tc_dom_polling_template.md:128-129）要求的手型前半段，
>         //     作用是排除 stale-1 假命中；详见文件头 (b) 段对"为何省去后半段"的说明。
>         //---------------------------------------------------------------------
>         bmc_spi_rd_to(DOM0_I2C_STA_ADDR, rdata, to);
>         if (to) begin
>             fail_both("STA_IDLE_RD_TIMEOUT", DOM0_I2C_STA_ADDR,
>                       $sformatf("BMC SPI pre-trigger read of i2c_sta did not return within %0dms", RD_TIMEOUT_NS/1_000_000));
>             test_done[pid] = 1'b1;
>             return;
>         end
>         if ((rdata & STA_BUSY_MASK) !== 32'h0) begin
>             fail_both("STA_IDLE_BEFORE", DOM0_I2C_STA_ADDR,
>                       $sformatf("pre-trigger i2c_sta=0x%08h has busy(bit1)=1 (stale-1 / FSM not idle before we start a fresh poll)", rdata));
>         end else begin
>             pass_note("STA_IDLE_BEFORE", DOM0_I2C_STA_ADDR,
>                       $sformatf("pre-trigger i2c_sta=0x%08h busy(bit1)=0 (idle, stale-1 excluded)", rdata));
>         end
> 
>         //---------------------------------------------------------------------
447a505
>         rd_to_seen   = 1'b0;
456,460c514,517
<                 fail_both("STA_RD_TIMEOUT", DOM0_I2C_STA_ADDR,
<                           $sformatf("BMC SPI read of i2c_sta did not return within %0dms (sample#%0d)",
<                                     RD_TIMEOUT_NS/1_000_000, samples));
<                 test_done[pid] = 1'b1;
<                 return;
---
>                 // 本笔读超时：不再继续发起访问（避免与被中止的访问抢总线），提前结束采样。
>                 // 失败由下方 O4 的"样本数不足"分支**唯一**报出（一条根因一条 *E，不重复刷屏）
>                 rd_to_seen = 1'b1;
>                 break;
478,483c535,546
<         // 5) 判定（5 条独立断言，逐条给"怎样才能失败"）
<         //---------------------------------------------------------------------
<         // O4：== 0 次采样 ⇒ 读通道打空，观测值为空
<         if (samples == 0) begin
<             fail_both("STA_READ_EMPTY", DOM0_I2C_STA_ADDR,
<                       $sformatf("no successful sample in %0dms observation window", OBS_WINDOW_NS/1_000_000));
---
>         // 5) 判定（逐条给"怎样才能失败"）
>         //    O4 是"观测证据是否充分"的**前置门**：样本不足时由它唯一报出，O5~O8 一律不裁决
>         //    （v1 的假失败路径是"采样不足被 O8 误报成状态没动"，A3 D-2；这里从结构上消除）
>         //---------------------------------------------------------------------
>         // O4：有效采样数 < MIN_SAMPLES ⇒ 观测证据不足
>         //     怎样失败：任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回 ⇒ 提前结束采样，样本数 < 3
>         //     ★ v1 的 `if (samples == 0)` 在控制流上不可达（恒真式断言，A3 D-1），已删除；
>         //       本判据**可达**：唯一触发路径 = 采样循环里那一笔读超时（`rd_to_seen`）。
>         if (samples < MIN_SAMPLES) begin
>             fail_both("STA_SAMPLES_SHORT", DOM0_I2C_STA_ADDR,
>                       $sformatf("samples=%0d < MIN_SAMPLES=%0d in %0dms window (read_timeout_seen=%0b): insufficient observation evidence",
>                                 samples, MIN_SAMPLES, OBS_WINDOW_NS/1_000_000, rd_to_seen));
485,486c548,549
<             pass_note("STA_READ_EMPTY", DOM0_I2C_STA_ADDR, $sformatf("samples=%0d in %0dms", samples, OBS_WINDOW_NS/1_000_000));
<         end
---
>             pass_note("STA_SAMPLES_SHORT", DOM0_I2C_STA_ADDR,
>                       $sformatf("samples=%0d >= MIN_SAMPLES=%0d (read_timeout_seen=%0b)", samples, MIN_SAMPLES, rd_to_seen));
488,494c551,557
<         // O5：任一采样 bits[31:3] != 0 ⇒ 与文档 Reserve(Reset 0) 不符
<         if (hi_bad) begin
<             fail_both("STA_RESERVED", DOM0_I2C_STA_ADDR,
<                       "some sample has bits[31:3] != 0, but doc :1547 marks them Reserve(Reset 0)");
<         end else begin
<             pass_note("STA_RESERVED", DOM0_I2C_STA_ADDR, "all samples bits[31:3] == 0");
<         end
---
>             // O5：任一采样 bits[31:3] != 0 ⇒ 与文档 Reserve(Reset 0) 不符
>             if (hi_bad) begin
>                 fail_both("STA_RESERVED", DOM0_I2C_STA_ADDR,
>                           "some sample has bits[31:3] != 0, but doc :1547 marks them Reserve(Reset 0)");
>             end else begin
>                 pass_note("STA_RESERVED", DOM0_I2C_STA_ADDR, "all samples bits[31:3] == 0");
>             end
496,502c559,565
<         // O6：任一采样 bit0 == 1 ⇒ I2C 通信异常（本用例已起 I2C 从模型应答）
<         if (err_seen) begin
<             fail_both("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR,
<                       "i2c_sta.bit0(err)=1 observed -> I2C device did not respond or the path is broken");
<         end else begin
<             pass_note("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR, "err(bit0) never set in the window");
<         end
---
>             // O6：任一采样 bit0 == 1 ⇒ I2C 通信异常（本用例已起 I2C 从模型应答）
>             if (err_seen) begin
>                 fail_both("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR,
>                           "i2c_sta.bit0(err)=1 observed -> I2C device did not respond or the path is broken");
>             end else begin
>                 pass_note("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR, "err(bit0) never set in the window");
>             end
504,512c567,575
<         // O7：整个窗口 bit1 从未为 1 ⇒ polling 未启动 / 节拍未跑 / 触发未生效
<         //     （★ 与参照用例的差别：它的 50ms 软超时是静默通过的；这里超时即失败）
<         if (!seen_busy) begin
<             fail_both("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR,
<                       $sformatf("busy(bit1) never seen as 1 within %0dms (polling not started / tick not running)",
<                                 OBS_WINDOW_NS/1_000_000));
<         end else begin
<             pass_note("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR, "busy(bit1)==1 observed at least once");
<         end
---
>             // O7：整个窗口 bit1 从未为 1 ⇒ polling 未启动 / 节拍未跑 / 触发未生效
>             //     （★ 与参照用例的差别：它的 50ms 软超时是静默通过的；这里超时即失败）
>             if (!seen_busy) begin
>                 fail_both("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR,
>                           $sformatf("busy(bit1) never seen as 1 within %0dms (polling not started / tick not running)",
>                                     OBS_WINDOW_NS/1_000_000));
>             end else begin
>                 pass_note("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR, "busy(bit1)==1 observed at least once");
>             end
514,519c577,585
<         // O8：全部采样完全相同 ⇒ 状态机没动（"读到了但没变化"）
<         if (!changed) begin
<             fail_both("STA_CHANGED", DOM0_I2C_STA_ADDR,
<                       $sformatf("i2c_sta value never changed across %0d samples", samples));
<         end else begin
<             pass_note("STA_CHANGED", DOM0_I2C_STA_ADDR, $sformatf("value changed across %0d samples", samples));
---
>             // O8：全部采样完全相同 ⇒ 状态机没动（"读到了但没变化"）
>             //     ★ 仅在 samples >= MIN_SAMPLES 时裁决（A3 D-2）：样本不足已由 O4 报出，
>             //       不会再把"采样不足"误报成"状态没动"
>             if (!changed) begin
>                 fail_both("STA_CHANGED", DOM0_I2C_STA_ADDR,
>                           $sformatf("i2c_sta value never changed across %0d samples", samples));
>             end else begin
>                 pass_note("STA_CHANGED", DOM0_I2C_STA_ADDR, $sformatf("value changed across %0d samples", samples));
>             end
```

---

## 2 事项 1 · D-1 是否真消除（逐行控制流论证）

**结论：真消除 ✓** —— `samples < MIN_SAMPLES` **可达**，且新判据**可失败**。

v2 采样循环（`:509-532`）与判定（`:543`）逐行：

```
507/509:  v = 32'h0;  t0 = $time;                 ← t0 在循环前一行赋值
511:      while (($time - t0) < (OBS_WINDOW_NS * 1ns)) begin    // 首判 = 0 < 30ms ⇒ 恒真
512:          bmc_spi_rd_to(DOM0_I2C_STA_ADDR, v, to);           // ≤RD_TIMEOUT_NS(1ms) 必返回
513:          if (to) begin
516:              rd_to_seen = 1'b1;
517:              break;                                          // ← 超时：跳出，**samples 未自增**
518:          end
520:          samples++;                                          // ← 成功才自增
531:          #(SAMPLE_GAP_NS * 1ns);
532:      end
543:      if (samples < MIN_SAMPLES) begin                        // MIN_SAMPLES=3（:264）
544:          fail_both("STA_SAMPLES_SHORT", ...)                 // ← 双写失败
```

| 步骤 | 断言 | 论证 |
|---|---|---|
| ① 循环体至少执行一次 | 必然 | `t0 = $time`（`:509`）紧随 `:511` 的条件 ⇒ 首次求值 `0 < 30ms` 恒真 |
| ② `samples` 可为 0 | **可达** | 第 1 笔读超时（`:513` 真）⇒ `:517 break`，`:520 samples++` **未执行** ⇒ `samples = 0` |
| ③ `samples < 3` 可达 | **可达** | 由 ② 得 `0 < 3` 真；甚至 1 或 2 笔后超时也成立 |
| ④ 该分支可失败 | **可失败** | `:544 fail_both("STA_SAMPLES_SHORT", …)` → `:338` `$display("chk_f *E …")` **且** `:339` `` `uvm_error `` ⇒ 双写 ✓ |
| ⑤ 触发路径是否就是"读超时"这一真实事件 | **是** | 无超时时：单笔读 ≈12.3us（参照日志 `:1278→:1286` 节拍 3.012ms）+ 节拍 3ms ⇒ 30ms 窗内 ≈**10–11** 个样本（`:511` 在 t=0/3/…/27ms 各采一次），**不可能** `< 3`；故 `samples < 3` 只能由 `:513 to=1` 造成 ⇒ **唯一真实事件** |
| ⑥ 正常情形 `samples ≥ 8` 是否成立 | **成立** | 期望 ≈11（`:144-146` 写"期望 ≈11、正常 ≥8"）；实际每笔 ≤1ms + 固定 3ms 节拍 ⇒ 30/3.012 ≈ **9.96** ⇒ ≈10 笔，≥8 有 1 个节拍的抖动余量 ✓（该数是**静态推算**，非本次运行观测） |

**"怎样才能失败"（新判据）**：任一采样读未在 1ms 内返回（总线/agent 卡住）⇒ 提前结束采样 ⇒ 有效样本 `< 3` ⇒ `*E STA_SAMPLES_SHORT` + `` `uvm_error ``。**答得出来 ⇒ 不再是恒真式** ✓。
**逐行确认 v1 的不可达式已删除**：v1 `:481 if (samples == 0)` 已不存在（`grep 'samples == 0'` 为 0），替换为 `:543 if (samples < MIN_SAMPLES)` ✓。

---

## 3 事项 2 · D-2 是否真消除

**结论：真消除 ✓** —— 分支结构（我逐行核过缩进与 `end` 归属）：

```
543:      if (samples < MIN_SAMPLES) begin
544:          fail_both("STA_SAMPLES_SHORT", ...)          // ← 样本不足的**唯一**报出口（双写）
547:      end else begin                                    // ← 只有 samples >= 3 才进入
548:          pass_note("STA_SAMPLES_SHORT", ...)           //    （含 read_timeout_seen=%0b）
552-557:      O5 STA_RESERVED      （fail_both / pass_note）
560-565:      O6 STA_ERR_CLEAR     （fail_both / pass_note）
569-575:      O7 STA_BUSY_SEEN     （fail_both / pass_note）
580-585:      O8 STA_CHANGED       （fail_both / pass_note）  ← ★ 注释 :577-579 明写"仅在 samples >= MIN_SAMPLES 时裁决"
586:      end                                               // ← 关闭 else ⇒ O5~O8 全在其内
```

| 检查项 | 结论 | 依据 |
|---|---|---|
| O5/O6/O7/O8 是否**全部嵌套**在 `samples >= MIN_SAMPLES` 分支内 | **是（4/4）** | 四个 `if` 的物理缩进均 +4（`:552/:560/:569/:580`），且唯一的收尾 `end` 在 `:586`，紧接 `:588` 的 `uvm_info`；无任何一个逃到外层 ✓ |
| "采样不足"是否**只由 O4 独立分支**报出、**不再**落到 O8 的"状态未变化" | **是** | `samples < 3` ⇒ 走 `:543-546` 分支后**直接跳到 `:586`**，O8（`:580`）在 `else` 内**不会执行** ⇒ v1 的"采样不足被误报成状态没动"（A3 D-2）从结构上消失 ✓ |
| `MIN_SAMPLES` 取值依据是否写清 | **是** | `:144-146`："窗 30ms / 节拍 3ms ⇒ 期望 ≈11（首样本 t=0 即采），取 3 作为有效证据下界（约期望值的 1/4，容忍数次采样缺失）；单笔读 ≤1ms、正常 ≥8，故 3 不会因轻微变慢而误报" ✓；`:264` 值 `3` 与注释同源 ✓ |
| 附带代价（须记录，非缺陷） | 记录 | `samples < 3` 时 O5~O8 一律不裁决 ⇒ 此时"err/busy/值变化"的诊断信息不输出；但用例**仍判 FAIL**（O4 双写）⇒ 不会造成假通过，属作者声明的"一条根因一条 `*E`"取舍 ✓ |

### 新增判据 O2b `STA_IDLE_BEFORE` 复核（Lead 点名）

| 检查项 | 结论 | 依据 |
|---|---|---|
| 是不是**真探针**（怎样才能失败） | **是** | `:462` `if ((rdata & STA_BUSY_MASK) !== 32'h0)` → `:463` `fail_both("STA_IDLE_BEFORE", …)`。失败 = 触发前 `i2c_sta.bit1`=1（stale-1 残留 / FSM 未复位）。反例具体存在 ⇒ 真探针 ✓。用 `!==`（含 X）而非 `==`：若 `rdata` 低位为 X，`x & 0` = 0 / `x & 1` = x ⇒ 结果 `!== 0` 为真 ⇒ **偏向判失败**，不会静默放过 ✓ |
| 是否被写进"检查点清单" | **是** | 文件头 O2b 条目 `:65-66`（含"失败条件：== 1"）✓ 与代码同名 `STA_IDLE_BEFORE` ✓ |
| 失败是否也走 `fail_both` 双写 | **是** | `:463` 经 `fail_both`（`:338`/`:339` 双写）✓；其读超时另走 `:457 fail_both("STA_IDLE_RD_TIMEOUT")` + `:458-459 test_done/return` ✓ |
| 位置是否为"触发之前" | **是** | 插在 v1 `:413` 之后、`3) 触发` 段之前（v2 `:450-470`），即**预置完成后、写 0x80 之前** ✓ 语义正确 |

---

## 4 事项 3 · D-3~D-8 是否都改到位

| # | 要求 | 结论 | 依据（v2 行号） |
|---|---|---|---|
| **D-3** | 笔数 64 | **改到位 ✓** | `:148-149` "32 轮 × 2 次库调用 = **64 次**库调用：polling_data_chk ×32 + set_data_ram ×32；轮数 = `DOME_PCA9548_NUM × `DOME_CHN_NUM = 8 × 4 = 32"；`:152` "同时覆盖预置段 **64 次**库调用"；`:438-440` 在预置段就地再述 "共 **64 次**"。**与 `:408-411` 的 `for` 循环上界及 `TB/tbtop.sv:41-42`（8×4）一致** ✓ |
| **D-4** | `10513` 清零并指向 §7 复现命令 | **改到位 ✓（采用了更稳的做法：不给数）** | `:136-138` 改为"**只给 mode/median/min，不给'条数'**：计数必须附可复现命令，口径与复现命令见 `_FORMAT.md §7`；实测 mode = median = 0.320us、min 0.224us"。用例内 `grep '10513'` = **0 处** ✓；`_FORMAT.md §7`（`8bbc8e57…`）现确实含**可执行复现命令块**（`python3 - <<'PY' …`，该节 "复现命令（本表所有数字均由它产生，禁手算）"）✓ ⇒ 指向有效 ✓ |
| **D-5** | 补位定义表 `:503` | **改到位 ✓** | `:247` `EXP_POLLING_EN_PRE` 注释："文档 **位定义表 :503**（Reset 0x0）+ 汇总 :419（Reset 0x0000）两处一致" ✓；我复核文档 `:503` 确为 `Polling_en_sys` 行、Reset `0x0`、备注"只能由CPU接口访问" ✓ |
| **D-6** | 改为"无**报错式**超时（`set_data_ram` 无界；`polling_data_chk` 静默 50ms 软界）" | **内容改到位 ✓，引用的行号错 1 行（见 D-11）** | `:152-155` 与 `:440-442`："库内**无报错式**超时：`set_data_ram` 无界；`polling_data_chk` 只有**静默** 50ms 软界 —— pcie_sequence.sv:**869/:875**，到了也不报错" ✓ 表述准确；但两条 `$time-t0<50ms` 实际在 **`:870` 与 `:876`**（`:869`/`:875` 是紧邻的 `t0 = $time;` 行）⇒ **行号须改**（D-11，**该行号源自我上一轮 A3 复核件，作者照抄**） |
| **D-8** | 二选一已落实（①+写明偏离） | **改到位 ✓** | `:111-123`（13 行）显式："**① 已采纳"先 0"**，并说明为何不必做"后 1 → 再等落 0"第二段"：① 单次新鲜 poll，触发前 `0x80` 读回 `0x0`（O2），而 poll 启动条件第一步即 `polling_en_sys`（引 `dom_i2c_data_ram.sv:488-490`，我复核 `:490` 即该 assign ✓）⇒ 触发前不可能有已发起的 poll、无 stale-1 可残留；② 已把该结论变成**读数证据**（O2b）；③ 兜底说明 O8/O7 如何覆盖 stale-1 的两种表现（恒 0x2 被 O8 抓、恒 0x4 被 O7 抓）。**三问都答了** ✓；模板引用 `tc_dom_polling_template.md:128-129` 我复核准确 ✓ |
| 附带 | `MIN_SAMPLES` 有注释依据 | **✓** | `:144-146`（推导）+ `:264`（取值）✓ |

---

## 5 事项 4 · 有没有夹带改动（以 diff 为准，逐 hunk 判定）

### 5.1 24 个 hunk 的归属判定

| hunk | 位置（v1→v2） | 内容 | 归属 | 判定 |
|---|---|---|---|---|
| 1 | `64a65,66` | 头注释新增 O2b 条目 | D-8/O2b | 在范围内 |
| 2-6 | `67,69c69,75` / `71c77,78` / `74,75c81,83` / `77c85` / `78a87,89` | O4 改名+失败条件；O5~O8 标"仅当 samples>=MIN_SAMPLES"；D-2 说明 | D-1/D-2 | 在范围内 |
| 7 | `99a111,123` | 头注释 D-8 偏离理由 13 行 | D-8 | 在范围内 |
| 8 | `112,114c136,138` | D-4：删"10513"，改指 §7 | D-4 | 在范围内 |
| 9 | `119a144,146` | MIN_SAMPLES 依据 | D-2 | 在范围内 |
| 10-11 | `121c148,149` / `124,125c152,155` | D-3 笔数 64；D-6 无报错式超时 | D-3/D-6 | 在范围内 |
| 12 | `217c247` | D-5 补位定义 :503 | D-5 | 在范围内 |
| 13 | `233a264` | 新增 `localparam MIN_SAMPLES=3` | D-2 | 在范围内 |
| 14 | `357a389` | 新增 `bit rd_to_seen;` | D-1 | 在范围内 |
| 15 | `406c438,442` | 预置段：笔数 64 + 库超时表述 | D-3/D-6 | 在范围内 |
| 16 | `413a450,470` | **新增 O2b 代码块（21 行）** | D-8 | 在范围内（新增**判据**，非放宽） |
| 17 | `447a505` | `rd_to_seen = 1'b0;` 初始化 | D-1 | 在范围内 |
| 18 | `456,460c514,517` | **超时分支：`fail_both`+`return` → `rd_to_seen=1'b1; break;`** | D-1 | ⚠ **在 D-1 范围内，但引入 D-10（失败面收窄）** |
| 19-20 | `478,483c535,546` / `485,486c548,549` | O4 → `samples < MIN_SAMPLES`；改名 `STA_SAMPLES_SHORT` | D-1 | 在范围内（判据增强） |
| 21-24 | `488,494c551,557` / `496,502c559,565` / `504,512c567,575` / `514,519c577,585` | O5~O8 缩进入 `else` + 收尾 `end` | D-2 | 在范围内 |

⇒ **24/24 hunk 均属 D-1~D-8 范围，无任何"无关顺手改"**。

### 5.2 关键不变量（逐项复核，均**未被改动**）

| 不变量 | 结论 | 依据（v2 行号） |
|---|---|---|
| 闭环选型（`0x9c` 使能 / `0x80` 触发 / `0x403c` 观测） | **未动 ✓** | `:234-236` 偏移仍 `32'h9c` / `32'h80` / `32'h3c`；`grep '0x6000'` 仅注释 |
| 段基址/步长 | **未动 ✓** | `:228-230` `0x0000` / `0x4000` / `0x0400`；`:201` 仍 `DOM_SEG_BASE + DOM_BLK_STRIDE*0` |
| 通道（`SPI_MST(2)` / `PCIE_SQR`） | **未动 ✓** | `:216` `PCIE_SQR` 宏、`:358/:370` `SPI_MST(2).set_read/set_write`、`:404-407` `setTiming(160,240,240,400)`/`setMode(3)`/`setConfig(1,9)` —— 与 v1 逐字相同（不在任何 hunk 内） |
| 三层超时结构（单笔 1ms / 窗 30ms / 兜底 120ms） | **未动 ✓** | `:260-263`、`:265` 四个值逐字未变；`MIN_SAMPLES` 是**新增**（`:264`），不改变任何既有阈值 |
| `*E` ↔ `` `uvm_error `` 结构性配对 | **配对成立 ✓（但失败点集合变了，见 D-10）** | 字面双写点仍 2 处：`:322`+`:324`（DONE_TIMEOUT 就地）、`:338`+`:339`（`fail_both` 体内）；v2 `fail_both` 调用 **12 处**：`:415 / :422 / :429 / :457 / :463 / :478 / :488 / :544 / :553 / :561 / :570 / :581` ⇒ 12 + 1 = **13 个失败点全部双写** ✓。⚠ v1 的 `:456 STA_RD_TIMEOUT`（第 12 个）**已被删除** |
| `PCIE_REG_RDCHK` / `set_rdchk` / `uvm_hdl_force` 代码处数 | **0 / 0 / 0 ✓** | `grep` 仅命中**注释**（`:45` 引日志原文、`:190` 说明不用 RDCHK 的理由）；`set_rdchk`、`uvm_hdl_force` 各 0 ✓；`uvm_warning` 0、`uvm_fatal` 0 ✓ |
| 无裸 `wait` / 无固定延时收尾 | **未动 ✓** | 唯一 `wait(` 仍在 `fork : DONE_WAIT_FORK`（`:286-297`）内带超时；`:267 #10us` 相位序；`:531` 节拍被 `:511` 硬界包围 |
| 零写入范围 | **未扩大 ✓** | 写调用仍仅 2 处：`:339`（SPI，唯一调用点 `0x9c`）与 `:484`（PCIE，`0x80`）；对 RO 的 `0x403c` 仍只读（`:455`/`:512`） |
| v1 归档件未被改动 | **✓** | `doc/_run_artifacts/tc_dom_polling_trig_chk_01_v1.sv` md5 仍 `bc9cd56d…`、37468 B、539 行 |
| 上一轮复核件未被覆盖 | **✓** | `A3_review.md` md5 仍 `999445d1a6fe7cbbd19ff5c1a4388707` |

### 5.3 ⚠ 新发现 **D-10**（本轮的退回主因，点名行号）

**事实**：v1 `:456-460` 的
```
fail_both("STA_RD_TIMEOUT", DOM0_I2C_STA_ADDR, $sformatf("BMC SPI read of i2c_sta did not return within %0dms (sample#%0d)", …));
test_done[pid] = 1'b1;  return;
```
被 v2 `:513-518` 替换为 **`rd_to_seen = 1'b1; break;`**（**该分支内无任何 `$display`/`fail_both`/`pass_note`**）。

**后果（分相讨论，逐项）**：

| 超时发生时机 | v1 行为 | v2 行为 | 差异 |
|---|---|---|---|
| 第 1–3 笔（`samples` 停在 0/1/2） | `fail_both("STA_RD_TIMEOUT")` ⇒ FAIL | `samples < 3` ⇒ `:544 fail_both("STA_SAMPLES_SHORT")` ⇒ FAIL | 仍 FAIL（改了名字，**失败面等价**） |
| **第 4 笔及以后**（`samples ≥ 3` 已成立） | `fail_both("STA_RD_TIMEOUT")` ⇒ **FAIL** | `:543` 判 `samples ≥ 3` ⇒ 走 `:547 else` ⇒ `:548 pass_note(...read_timeout_seen=1)`；O5~O8 照常裁决 | **v2 不再失败** ⇒ 一次真实的"总线读超时"可以**零 `*E`、零 `UVM_ERROR`** 通过 |

**危害（可判定的假通过路径）**：设采到 3 笔好样本（`busy=1` 出现过、`err=0`、值有变化，与参照日志的 `0x4↔0x2` 交替一致），第 4 笔读超时 ⇒ v2 全绿 **PASS**；v1 会因 `STA_RD_TIMEOUT` **FAIL**。回归判定只认 `*E` 文本（`run_uvs_new.sh:296`），而 v2 该分支连 `chk_f` 都不打印 ⇒ **脚本口径与 UVM 口径同时为 0** ⇒ 该假通过**不会被任何一套口径拦住**。
**作者注释与实现不符**：`:514-515` 称"失败由下方 O4 的'样本数不足'分支**唯一**报出"—— 该说法仅在 `samples < 3` 时成立；`samples ≥ 3` 时**没有任何分支报出**。故这是疏漏，而非有序取舍（`rd_to_seen` 变量与消息里的 `read_timeout_seen=%0b` 说明作者本意是让它可见）。
**定级**：属 Lead 点名的"**断言被放宽/弱化**"⇒ **退回**。
**改法（1 行，二选一）**：
- ① `:543` → `if ((samples < MIN_SAMPLES) || rd_to_seen) begin`（消息里已打印 `read_timeout_seen`，文案微调即可）；**此改法同时保持"一条根因一条 `*E`"**，推荐。
- ② 或把超时分支恢复为 `fail_both("STA_RD_TIMEOUT", …);` 后再 `break`（会与 O4 各自报一次，两条 `*E` 同一根因）。

### 5.4 ⚠ **D-11**（我的上轮错误，须随改）

D-6 写进用例的 `pcie_sequence.sv:869/:875`：实测两条 `$time-t0<50ms` 软界在 **`:870` 与 `:876`**，`:869`/`:875` 是紧邻的 `t0 = $time;` 行。**该行号源自我上一轮 `A3_review.md` 的 D-6 条目**（我在那件里写的就是 `:869/:875`），作者照抄 ⇒ 由我担责更正，并建议改为 `:870/:876`。**不影响 D-6 的结论（内容表述准确）**。

---

## 6 事项 4 续 · A2b 对账

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 6.1 | v2 md5 与证据记录一致（防移动靶） | **通过** | 我现取 `e24aded26476aed9426576da361c0fa2` / 43922 / 605 = A2b 证据 `:21-23` = Lead 报值 ✓ |
| 6.2 | 两段 rc | **通过（脚本自报）** | `a2b_compile_stdout_v2.log:1303` `rc=0 耗时 1s`、`:2099` `rc=0 耗时 1s`、`:2101` `[PASS]`；stdout 头部 `:4-5` 内嵌 `md5 e24aded2…` / `43922 字节 / 605 行` ✓ |
| 6.3 | 0 error 独立复核 | **通过** | 我复算：rtl `0`、tb `0`；`Compilation: 0 error(s), 13 warning(s)`（rtl）/ `0 error(s), 4 warning(s)`（tb）✓ |
| 6.4 | **本轮日志确为 v2 的**（字节数巧合相同，须逐条证） | **通过（三重证据 + 我独立复现）** | ① md5 不同：v2 `04098ba8…`(rtl)/`bf92a850…`(tb) ≠ 归档 v1 `2f8ad76b…`/`73f9c668…`；② `Compilation starts at`：v2 `14:13:52`/`14:13:54` vs v1 `13:57:39`/`13:57:43`；③ **用例行号位移**：v2 tb 日志引用 `203/205/206/207/208`，v1 引用 `173/175/176/177/178`，**恰好 +30**；我核 v1 `:173-178` 与 v2 `:203-208` 内容**逐字同构**（`uvm_macros.svh` + 注释行 + `top_pkg/crg_pkg/macros_pkg/packet.sv`）⇒ 编译器确实读到变长后的 v2 ✓（A2b 证据 §2 该结论**我独立复现一致**） |
| 6.5 | v1 日志是否被保全（防原位覆盖） | **通过** | `SIMLIB_RUN/log/archive_a2_v1/` 三件 md5 = `2f8ad76b…`/`73f9c668…`/`2c161176…`，**与我上一轮 A3 复核时读到的 v1 日志 md5 完全一致** ✓ |
| 6.6 | `uvs.setup` 是否还原 | **通过** | 现取 `uvs.setup` = 夹具 = `a80f7b6ca48a7961a107bbe871af761d`；`diff` rc=0；`.compile_only.lock` 不存在 ✓ |
| 6.7 | `TESTLIB/` 未被动 | **通过** | 我现测 `ls TESTLIB/*.sv \| wc -l` = **162**；`md5sum TESTLIB/*.sv \| LC_ALL=C sort \| md5sum` = **`4c0942ac419f67c6fdb391dd2083f0b3`**（与 §8 基线一致，我复现 ✓）；`TESTLIB/tc_dom_polling_trig_chk_01.sv` 不存在 ✓ |
| 6.8 | 归档只增不改 | **通过** | v1 证据 md5 仍 `a09a9a8c…`（含 v1 内容）✓；v1 用例归档 `bc9cd56d…` ✓；`compile_only.sh` `4d7cf96c…` ✓；上一轮 `A3_review.md` 未被覆盖 ✓ |

---

## 7 若整改后通过 · A5 对账注意点（两套口径分流判据）

> 依据 **D-7**：库 `polling_data_chk` 的失败**只打 `*E` 文本、不发 `` `uvm_error ``**（`pcie_sequence.sv:924` 与 `:928` 两处 `$display("*E pcie_rtc[…])`），而本用例所有失败点**双写**。故 A5 必须按**文本前缀**分流，不能只看 `*E` 计数。

**分流判据（可机械执行）**：

| 观测组合 | 判定 | 依据 |
|---|---|---|
| `*E` 计数 > 0 **且** `UVM_ERROR` > 0 | **用例断言失败**（O1/O2/O2b/O3/O4~O8/DONE_TIMEOUT 之一） | 用例失败点全部双写：`fail_both` 体内 `:338`/`:339`，DONE_TIMEOUT 就地 `:322`/`:324` |
| `*E` 计数 > 0 **且** `UVM_ERROR` == 0 | **库数据检查抱怨**（`polling_data_chk` 对 polling 数据窗/golden 的比对），**不是**用例断言失败 | `pcie_sequence.sv:924/:928` 只有 `$display`；文本前缀 `*E pcie_rtc[` |
| `*E` == 0 **且** `UVM_ERROR` > 0 | 需查 UVM 报告来源（本用例不应出现：所有失败点双写） | 与报告 §7.1.1 的**正向**陷阱（UVM 有错而脚本 0）相反，须单独登记 |

**操作建议**：A5 抽样时以**文本前缀**区分 —— 用例侧为 `chk_f *E DOM_TRIG_CHK …`（`:322` 与 `:338`），库侧为 `*E pcie_rtc[`（`pcie_sequence.sv:924/:928`，**该前缀不含 `chk_f` 也不含 `DOM_TRIG_CHK`**）。若出现 `*E pcie_rtc[` ⇒ 按**分类 3（环境/数据）**处理并注明"非 O1~O8 断言"，**不得**记成用例断言失败，也不得据此改用例断言。
**另附**：`PCIE_REG_RDCHK`/`set_rdchk`/`set_rtc_rw` 的 `*E`（`pcie_sequence.sv:598/:660`，也是 `uvm_info` 内的 `*E`）**本用例不会触达**（代码 0 处调用，仅注释提及）⇒ 若 A5 日志里出现该类前缀，应作为"环境/其他用例污染"线索单列。

---

## 8 未在本机复算的量（诚实清单）

| 量 | 为什么未复算 | 核到什么程度 |
|---|---|---|
| 两段 `uvlan` 的 **rc=0 本身** | 重跑会写 `SIMLIB_RUN/`（runner 写权） | 脚本自报（`:1303/:2099`）+ 两段日志 0 error + stdout 头部内嵌本用例 md5/字节/行数 + tb 日志 `Analyzing` 本用例 + 行号位移 +30 ⇒ **多方一致**；**不称"已复核 rc"** |
| v2 在仿真中的**行为/时序/实际样本数** | 本轮只编译 | **完全未核**；§2 的"期望 ≈11 / 正常 ≥8"是**静态推算**（30ms ÷ 3.012ms），非本次观测 |
| O2b 在实跑中**是否真的读到 0** | 需全跑 | 只做静态判据审查（探针有效、双写、位置正确）；其"正常应为 0"的依据是 v1 参照日志中触发前 `0x4038/0x403c` 的行为与 RTL `:490` 的启动条件 |
| 30ms/120ms 在本用例下的充分性 | 需全跑 | 沿用 A3 的静态论证（上界和 ≈79ms < 120ms；BUSY 首现 9.047ms < 30ms，取自参照日志） |

---

## 9 判定

| 事项 | 结论 |
|---|---|
| **D-1** 是否真消除 | **是** —— `samples` 可为 0（`:513 to=1` ⇒ `:517 break`，跳过 `:520 samples++`）⇒ `:543 if (samples < MIN_SAMPLES)` **可达**；新判据**可失败**（双写于 `:544`）⇒ 不再是恒真式 |
| **D-2** 是否真消除 | **是** —— O5/O6/O7/O8 全部嵌套于 `:547 end else begin … :586 end` 内（4/4）；`samples < 3` 时由 O4 独立分支报出，**不再**落到 O8 |
| 新增 **O2b** | **真探针**（`:462` 反例明确）、**已入检查点清单**（`:65-66`）、**走 `fail_both` 双写**（`:463`）、位置正确（触发前） |
| **D-3/D-4/D-5/D-6/D-8** | **全部改到位**（逐条见 §4）；仅 D-6 引用的行号 **`869/:875` 应改 `:870/:876`**（**D-11，我上轮写错、作者照抄**） |
| 夹带改动 | **未发现超范围改动**：24/24 hunk 全属 D-1~D-8；地址/通道/三层超时/零写入范围/v1 归档均未动；`PCIE_REG_RDCHK`/`set_rdchk`/`uvm_hdl_force` 代码 **0 处** |
| **但** | **D-10**：v1 的 `STA_RD_TIMEOUT` 双写失败点被整条删除（v2 `:513-518`），使 `samples ≥ 3` 时的读超时**零 `*E` 零 `UVM_ERROR`** 通过 ⇒ **失败面收窄 / 可致假通过** ⇒ 属"断言被弱化" |
| A2b 对账 | **全绿**（md5 一致、两段 rc=0、0 error 独立复核、**日志确为 v2（三重证据 + 我复现 +30 位移）**、`uvs.setup` 已还原、TESTLIB 162 与 `4c0942ac…` 均复现、归档未覆盖） |

---

# 结论：**退回（逐条依据）**

**唯一阻塞项 D-10**（1 行可改）：本次 D-1 的整改把 v1 的 `fail_both("STA_RD_TIMEOUT")` 删成了 `rd_to_seen=1'b1; break;`（v2 `:513-518`），导致 **`samples ≥ MIN_SAMPLES` 时的读超时不再产生任何失败信号**（v1 会 FAIL）。这与 Lead 明令的"**发现任何超范围改动（尤其断言被放宽/弱化）⇒ 直接判退回并点名行号**"相符，且构成一条**不会被两套口径拦住的假通过路径**。
**建议改法（推荐 ①，同时保留作者"一条根因一条 `*E`"的意图）**：
① `:543` `if (samples < MIN_SAMPLES) begin` → `if ((samples < MIN_SAMPLES) || rd_to_seen) begin`；并把 `:545` 文案从"insufficient observation evidence"改为"read timeout seen / insufficient samples"之类，使 `read_timeout_seen=%0b` 成为判据的一部分；
② 或在 `:516` 前恢复 `fail_both("STA_RD_TIMEOUT", …)` 后再 `break`。
**同时随改（1 处，来自我上轮的错）**：D-11 —— `:155` 与 `:442` 的 `pcie_sequence.sv:869/:875` → **`:870/:876`**。

**除 D-10 外，本轮其余目标全部达成**：D-1/D-2 真消除、O2b 是真探针且双写、D-3/D-4/D-5/D-6/D-8 全部到位、**无夹带改动**、A2b 对账全绿。⇒ 改完这 1–2 处（**约 2 行 + 2 秒重编**）即可再送卡点 C；**不建议触碰闭环选型、地址、通道与三层超时结构**。
**口径边界（重申）**：本轮只到 **编译 + 静态**。本"退回"是**静态判据**结论（失败面收窄），**不是**功能/时序结论；即使整改后通过，也只代表"编译期 + 判据可信"，功能结论必须由 A4 全跑 + A5 两套口径对账给出。

---
*本文件由 `simenv-checker`（非作者）产出，落在唯一写权 `doc/agents/_demo/accept/review/`。未修改用例 / `RTL/` / `TB/` / `PKG/` / `TESTLIB/` / v1 归档件 / 上一轮复核件。所有 md5、行数、计数与日志原文均由命令输出复制，未手算。*
