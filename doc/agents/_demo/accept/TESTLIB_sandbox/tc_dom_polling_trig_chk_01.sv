/*=============================================================================
//     FileName: tc_dom_polling_trig_chk_01.sv
//         Desc: DOM 段控制器 0 —— 「使能/配置 → 触发 → 读寄存器状态变化」功能验证
//       备注: 验收沙箱件（doc/agents/_demo/accept/TESTLIB_sandbox/），未进 TESTLIB/
//=============================================================================
// 【目标】
//   对 DOM 段（段基址 0x4000，块步长 0x400）**控制器 0** 做一次端到端功能验证：
//     ① 使能：BMC SPI 通道写全局 0x9c（bmc_rtc_en[9:0] = 0x1ff）并读回证明写入生效；
//     ② 触发：PCIE 通道写全局 0x80（Polling_en_sys.bit0 = 1）开启全局 polling，并读回 0x80==1；
//     ③ 观测：BMC SPI 通道**轮询读**控制器 0 的 0x403c（i2c_sta，RO），采集状态值序列，
//        断言「BUSY(bit1) 至少出现一次」「err(bit0) 全程为 0」「值序列发生过变化」
//        「bits[31:3] 全程为 0（文档 Reserve=0）」。
//
// 【来龙去脉（卡点 A 三步检索，全部给行号）】
//   ① 模板库：doc/skills/simenv-test/tc_dom_polling_template.md
//       —— SKILL.md §6 模板库索引表 **第 158 行（第 7 行）**：功能族「DOM 引擎 Polling」，
//          索引行给的陷阱即本用例的两个关键点（`i2c_sta(0x3c)` 是 RO、`0x6000` 无应答者）。
//          实际读用：该模板 §3.3（轮询状态位/BUSY 手型、超时当失败）第 105-148 行；
//                    §5.1 真实取值表 第 281-295 行；§5.2/§5.4 第 297-336 行；
//                    §6 陷阱备忘第 338-417 行（坑一 RO/坑二 8 台/坑三 dom_done 死信号/
//                    坑七"轮询软超时静默通过"/坑九 1Hz 节拍与未被驱动的时钟）。
//   ② 参照用例（同族语料，锁风格不锁地址）：
//       - TESTLIB/tc_dom_polling_new_01.sv（★ 实机通过对象；本用例的操作序即取自它的
//         §114-158 PCIE_REG_RW 与 §228-235 I2C_SLV_RW：先起 I2C 从模型 → 32×预置
//         → PCIE 写 0x80 触发 → 轮询 0x3c）
//       - TESTLIB/tc_dom_polling_03.sv（反例：用 `DOME_PLREG_ADDR(0x8000)+n*0x100`，
//         文档/RTL 双侧都不存在的段（模板 §5.3 第 315-326 行）→ 本用例**不学**）
//   ③ 项目专属基准：
//       - 接口文档 DOM 段（doc/reference/TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md）
//         段头 `:1376`、「DOM CPU RTC控制器0~7(CPU接口访问)」`:1385`、基址表 `:1386`（0x4000 起/0x400 步长）
//         · 全局 `0x9c bmc_rtc_en`：汇总 `:422`、位定义 `:535-546`（"只能由BMC接口访问"）
//         · 全局 `0x80 Polling_en_sys`：汇总 `:419`、位定义 `:500-503`（"只能由CPU接口访问"，Reset 0x0000）
//         · DOM `+0x3c i2c_sta`：汇总 `:1402`、位定义 `:1538-1547`
//         · DOM `+0x38 i2c_ctl`：位定义 `:1527-1536`（备选触发，见 (a)）
//       - RTL：DOM 寄存器偏移 `RTL/SRC/imports/SRC/dom_src/dom_i2c_data_ram.sv:86`（I2C_STA=8'h3c）、
//         `:539-542`（`s_bmc_i2c_sta[1]` 由 start 置 1、com 清 0）、`:488-490`（polling 启动条件含 en_1hz）
//       - TB：段基址/台数 `TB/tbtop.sv:67-68`（`DOME_RTC_ADDR=0x4000`/`DOME_RTC_OFFSET=0x400`）、
//         `:41-42`（`DOME_PCA9548_NUM=8`/`DOME_CHN_NUM=4`）、`:47`（`I2C_SLV_NUM`）、
//         `:298/:332`（DOM 侧 I2C 从模型接口）
//       - 实测日志（本用例的操作序与所有常数由此取证）：
//         LOG/tc_dom_polling_new_01_1_run.log（md5 09a37ea22341d33ec62ba2672c6b5789 / 220150 B / 4392 行；
//         末尾 `:4367 UVM_ERROR: 0`、`:4368 UVM_FATAL: 0`、`:4354 Final_phase status: Pass!`）
//         · 使能：`:213 [SPI_WR] reg@0x0000009c = 0x000001ff, 22.905 us`；`:214 [SPI_RD] ... = 0x000001ff`
//         · 触发：`:1272 [PCIE_REG_RD@0x80] -> 0x0` → `:1274 [PCIE_REG_WR@0x80] -> 0x1000000`
//                 → `:1276 [PCIE_REG_RD@0x80] -> 0x1000000` → `:1277 [set_rdchk] @ADDR[0x80] -> 0x1`
//         · 观测：0x403c 共 32 次读，**32/32 全走 `[SPI_RD]`（BMC SPI），没有一次走 PCIE**；
//                 值分布 `0x2`×22、`0x4`×10；首读 `:1278 @15673.785us = 0x4`；
//                 首个 BUSY=1（0x2）`:1310 @21698.425us`（触发后 9.05ms）；相邻采样间隔 3.012ms
//         · 全日志未出现 `i2c_sta` bit0（err）=1，也未出现 `0x60/0x4060` 的访问
//
// 【覆盖寄存器清单】（地址一律写 <段基址> + <块内偏移>）
//   #  归属块（段）                     寄存器            全局地址 = 段基址 + 块内偏移   属性  文档位定义表
//   1  全局寄存器段（0x0000）           bmc_rtc_en        0x0000 + 0x9c = 0x9c            R/W   :535-546（仅 BMC 接口）
//   2  全局寄存器段（0x0000）           Polling_en_sys    0x0000 + 0x80 = 0x80            R/W   :500-503（仅 CPU 接口，Reset 0x0）
//   3  DOM 控制器 0 块（0x4000+0x400*0） i2c_sta(RO)      0x4000 + 0x00 + 0x3c = 0x403c  RO    :1538-1547
//   （辅助：DOM 控制器 0 的 0x00~0x17c 配置区与 0x200~0x3fc 数据窗由库函数
//     polling_data_chk/set_data_ram 访问，用于把 I2C 从模型灌成 golden 并核对上电初值，
//     不是本用例的断言对象；见下方 (c)。）
//
// 【观测点】（每条都写明"怎样才能失败"）
//   O1 ENABLE_RDCHK  : 写 0x9c=0x1ff 后 SPI 读回必须 == 0x1ff
//                      失败条件：读回 != 0x1ff（写不进 / 通道错 / 权限错）
//   O2 TRIG_BEFORE   : 触发前 PCIE 读 0x80 必须 == 0x0
//                      失败条件：!= 0（复位值被破坏 / 地址打空读到别处）
//   O2b STA_IDLE_BEFORE: 触发前 SPI 读 0x403c 的 busy(bit1) 必须 == 0（D-8 采纳的"先 0"）
//                      失败条件：== 1（触发前引擎就忙 ⇒ 上一轮命令的 stale-1 残留 / 状态机未复位）
//   O3 TRIG_AFTER    : 触发后 PCIE 读 0x80 必须 == 0x1
//                      失败条件：!= 1（写不进 / 通道错 —— 触发没发生，后面 BUSY 也不会起）
//   O4 STA_SAMPLES_SHORT: 判据 = (有效采样数 >= MIN_SAMPLES(=3)) **且** (从未出现读超时)
//                      失败条件（两选一即失败，v3 按 A3b D-10 恢复失败面）：
//                        (i) 任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回（`rd_to_seen=1`）——
//                            总线/agent 卡住；无论样本数多少都判失败；
//                        (ii) 有效样本数 < 3。★ v2 对 A3 D-1 的整改：v1 的 `samples==0`
//                            在控制流上不可达（恒真式断言），已删除；本判据**可达**
//                            （真实触发路径 (i)：读超时 ⇒ 提前结束采样）。
//   O5 STA_RESERVED  : ★仅当 samples >= MIN_SAMPLES 时裁决：每个采样的 bits[31:3] 必须 == 0
//                      （文档 :1547 Reserve 位 Reset 0）
//                      失败条件：任一采样 bits[31:3] != 0（总线数据错 / 位定义与实现不符）
//   O6 STA_ERR_CLEAR : ★仅当 samples >= MIN_SAMPLES 时裁决：每个采样的 bit0
//                      （err，文档 :1545 "1:I2C通信异常"）必须 == 0
//                      失败条件：任一采样 bit0 == 1（I2C 器件未应答或通路异常；本用例已起
//                      I2C 从模型应答，故 err 置位即为真实缺陷/环境问题）
//   O7 STA_BUSY_SEEN : ★仅当 samples >= MIN_SAMPLES 时裁决：12ms 观测窗内 bit1（busy，
//                      文档 :1546 "1:正在通信"）至少一次 == 1
//                      失败条件：全程 bit1 为 0（polling 未启动 / 节拍未跑 / 触发未生效）
//                      —— 实测支撑：触发后 **9.047ms** 首现 0x2；12ms 窗只留 **1.33× 薄余量**
//                         （被墙钟逼出的取舍，见【超时预算推导】；更保守的 30ms ≈2.4 小时）
//   O8 STA_CHANGED   : ★仅当 samples >= MIN_SAMPLES 时裁决：采样值序列必须至少变化一次
//                      失败条件：全部采样完全相同（状态机没动；"读到了但没变化"正是要抓的）
//                      ★ v2 对 A3 D-2 的整改：样本不足时**不再**落到本判据（v1 会把"采样不足"
//                        误报成"状态没动"= 假失败），改由 O4 的独立分支唯一报出，一条根因一条 *E
//   （★ 说明：O4 的"样本不足"一旦成立，O5~O8 一律不裁决 —— 避免一条根因刷出多条失败）
//
// 【(a) 定案：触发/使能到底是哪个寄存器哪一位】
//   · 使能 = 全局 `0x9c bmc_rtc_en[9:0]` 写 0x1ff。依据：文档 `:422`/`:535-546`（bit0~bit9 =
//     bmc_rtc_en0..9，"只能由BMC接口访问，关闭则BMC无法RTC"）+ 实测日志 `:213`（SPI_WR 0x1ff 生效，
//     `:214` 读回 0x1ff）。**不是** `+0x60 i2c_polling_cfg`：全日志对它 0 次访问（见待确认 T3）。
//   · 触发 = 全局 `0x80 Polling_en_sys.bit0` 写 1。依据：文档 `:419`/`:500-503`
//     （bit0："1：开启polling"，"只能由CPU接口访问"，Reset 0x0）+ 实测日志 `:1272-1277`
//     （读 0x0 → 写 1 → 读回 1）。**不是** DOM `+0x38 i2c_ctl.bit1 start`：该位是"写清0"
//     自清零（文档 `:1535`），且全工程无任何实测先例证明 CPU 侧写它能起 I2C（见 U3）。
//   · 访问通道：全局 0x9c 只能 BMC 访问、全局 0x80 只能 CPU 访问（文档 `:535-546`/`:500-503`）⇒
//     本用例分别用 BMC SPI 与 PCIE，**两条通道都与文档标注一致**。
//
// 【(b) 定案：BUSY(i2c_sta.bit1) 的可见性】
//   `i2c_sta` 是 RO，且"新的命令开始时自动清 0"（文档 `:1402`）⇒ **绝不能写后读**，只能轮询。
//   "读到 BUSY=1 需要什么条件"的答案是**实证的**：全局 polling 打开（0x80=1）后，polling 引擎
//   按内部节拍发起 I2C 访问，期间 `s_bmc_i2c_sta[1]` 被 start 置 1、通信完成清 0
//   （RTL dom_i2c_data_ram.sv:539-542）。实测：触发后 3.02ms 首读到 0x4（`:1278 @15673.785us`，
//   距触发 12651.145us 为 3.023ms）、9.05ms 首读到 0x2，32 次采样中 22 次为 0x2 ⇒ **BUSY=1 稳定可观测**，因此本用例敢写"至少出现一次为 1"的真探针
//   （O7）。若 45 分钟那次一次都没读到 1 ⇒ 判失败，而不是静默通过。
//   ★ 与参照用例的差别：参照用例的 50ms 软超时是**静默通过**的（模板 §6 坑七，依据
//     TB/AGENTS/PCIE-Agent/pcie_sequence.sv:866-881），本用例把"窗口内没等到 BUSY"直接判为失败。
//   ★ D-8（BUSY 手型）二选一：**① 已采纳"先 0"，并说明为何不必做"后 1 → 再等落 0"**：
//     - 已做"先 0"：触发**之前**读一次 0x403c，断言 busy(bit1)==0（判据 O2b）。这比模板
//       `tc_dom_polling_template.md:128-129` 建议的"先等它落 0"更强 —— 它证明的是
//       "本次 poll 开始前 FSM 确实空闲"，而不是"在观测点等到它落 0"。
//     - 未做"后 1 → 再等落 0"第二段：模板那段手型是为了在**连续轮询**场景里避免把
//       "上一轮还没消的 1"当成本次命中（stale-1 假命中）。本用例是**单次新鲜 poll**：
//       触发前 0x80 已读回 0x0（判据 O2，仅 CPU 可写、且本用例是唯一写者），而 poll 的启动
//       条件第一步就是 `polling_en_sys`（RTL dom_i2c_data_ram.sv:488-490）⇒ 触发前**不可能**
//       存在任何已发起的 poll，也就没有可残留的 stale-1；O2b 又把这个结论变成了**读数证据**。
//     - O8 如何兜住 stale-1：退一步说，若真有上一轮残留的 1，则本次窗口内不会发生新的
//       poll ⇒ 采样值会**恒定**（0x2 恒 busy 或 0x4 恒 arm）⇒ 恒定 0x2 被 O8（值未变化）抓住，
//       恒定 0x4 被 O7（从未见到 bit1=1）抓住。两条合起来覆盖 stale-1 的两种表现。
//       （实测的正常序列是 0x4 ↔ 0x2 交替，见下）
//
// 【(c) 定案：外部器件/应答】
//   DOM 控制器是 I2C **主**，要对光模块（DOM 器件）发起访问；若器件不应答，bit0 err 会置位。
//   TB 侧有 I2C 从模型可应答：`FORKJN_FOR_BLK(`I2C_SLV_NUM, I2C_SLV_RW)`（参照用例 `:82` 与 `:228-235`），
//   每个从模型 `I2C_SLV(pid).startEnv()` 后由模型自己应答；再用库函数
//   `m_pcie_seq.set_data_ram(n,0,256)` 把 golden 数据灌进从模型（`pcie_sequence.sv:889-897`
//   内的 `i2c_slv[n].putbpWord(addr+i, data_rand)`）⇒ 闭环不需要真实光模块。
//   收缩声明：本用例**不**断言 polling 数据窗的内容（那是参照用例的覆盖点），只断言 `i2c_sta`
//   的状态序列，因此"数据是否与 golden 逐字节相同"不在本用例范围内（见 U1）。
//
// 【超时预算推导】（口径按 doc/skills/simenv-test/_FORMAT.md §7：基数取**背靠背**访问间隔；
//   笔数回本用例里数实际访问点；禁止拿"日志里相邻两次访问的间隔"当基数）
//   · 单笔访问基数 T_acc = 0.32us（**只给 mode/median/min，不给"条数"**：计数必须附可复现命令，
//     口径与复现命令见 doc/skills/simenv-test/_FORMAT.md §7；实测 mode = median = 0.320us、
//     min 0.224us；来源 LOG/tc_pcie_rw_02_1_run.log 与 LOG/tc_dom_polling_new_01_1_run.log 的 SPI 读节奏）
//   · 单笔读超时 RD_TIMEOUT_NS = 1ms ≈ 3125 × T_acc（BMC SPI/PCIE 读各自带超时兜底，铁律 5）
//   · 采样节拍 SAMPLE_GAP_NS = **1ms**（v6 由 3ms 改小，D-12）：
//     **目的不是省时间，而是保证覆盖 9.047ms 的 BUSY onset**。3ms 栅格（参照实测相邻采样
//     3.012ms）在 12ms 窗内只落 4 个样本（t0+0.01/3.02/6.04/9.05ms），onset 之后**只剩 1 次
//     采样机会**，其后 2.95ms 是永无样本的死尾 ⇒ onset 稍晚就漏采；1ms 栅格 ⇒ 窗内 **12 个样本**、
//     onset 之后有 3 次机会（t0+9.12/10.14/11.15ms），首个 ≥onset 的采样只需等 ≈1 个间隔。
//     成本几乎为零：观测窗仍 12ms（仿真时间口径不变），只多 ≈8 笔读 × 12.31us ≈ **0.1ms 仿真**
//     （按 0.216 口径 ≈28 秒墙钟）。
//     （参照实测 3.012ms 见 LOG 上述日志 `:1278 @15673.785us` → `:1286 @18686.105us`）
//   · 观测窗 OBS_WINDOW_NS = 12ms：BUSY=1 **首现于触发后 9.047ms**（参照实跑
//     LOG/tc_dom_polling_new_01_1_run.log `:1274 @12651.145us` → `:1310 @21698.425us`）
//     ⇒ 12ms 只留 **1.33× 余量，很薄**（9.047 × 1.33 = 12.03ms）。这是**被墙钟逼出来的取舍**：
//     按下面的修正口径，12ms 已需 ≈56 分钟，而更保守的 ≥30ms 要 ≈2.4 小时
//     （A4 attempt2 正是因此中止）⇒ 只能取 12ms。
//   · 采样数下界 MIN_SAMPLES = 3（**值不动**）：1ms 栅格 ⇒ 12ms 窗内最多 **12 个样本**
//     （12×1.012=12.15ms 越界），3 是宽松下界、余量充足；"读超时提前结束采样"
//     这条真实路径仍可使样本数 < 3 ⇒ O4 判据的可达性不变（A3b D-10 仍成立）。
//   ★ 墙钟口径（**v5 按 A4 attempt2 修正**，证据 doc/agents/_demo/accept/evidence/A4_run_evidence.md §7.1）
//     —— **撤回 v4 的"按笔数计费"投影**：v4 写的"48 笔 × 3.3s ≈ 3.0 分钟"是 attempt1 密集读
//     场景下的**表象**，attempt2 实测推翻。**真正的口径是：墙钟成本 ≈ 仿真时间 × 活动因子**。
//     使能 0x80、DUT polling 引擎持续工作后活动因子极高：实测 **≈0.21~0.216 ms 仿真 / 分钟墙钟**
//     （§7：1029s 墙钟推进 3.595ms ⇒ 3.49us/s ≈ 0.209ms/min；本文件按 0.216 计）
//     ⇒ **1ms 仿真 ≈ 4.6~4.8 分钟墙钟**；"笔数"不是主因。
//   · 预置段（v4 = **1 轮**）：1 轮 = `polling_data_chk` ×1 = **32 笔**读
//     （函数内 `for (i < 128/4)`；实测参照日志触发前 SPI_RD 共 1025 笔 = 32 次调用 × 32 笔
//      + 0x9c 读回 1 笔 ⇒ 每轮 32 笔，不是 128 笔）
//     · 仿真时间 ≈ 32 × 12.31us ≈ **0.39ms**（另加 0x9c 写/读回 2 笔 ≈ 0.03ms ⇒ ≈0.42ms）
//     · 墙钟 ≈ 0.42ms / 0.216 ≈ **1.9 分钟**（按修正口径；v4 之前的 32 轮 = 1024 笔/12.6ms
//       仿真 ≈ 58 分钟，v4 已砍到 1 轮）
//     ⇒ 取 PRESET_BUDGET_NS = 2ms（≈ 上述投影 0.42ms 的 4.8 倍）
//   · 观测窗（v5 = **12ms**）：走满整窗 ⇒ 墙钟 ≈ 12 / 0.216 ≈ **55.6 分钟**（上界，正常不会走满）
//   · ★ 成功即早退（v5 新增，**不放宽任何判据**）：仅当 **O7(BUSY 已见) ∧ O8(值已变化) 都已满足**
//     才 `break` 采样循环。**早退不可能早于 BUSY 首现 9.047ms**（条件含 `seen_busy`）⇒
//     1ms 栅格下最早早退 = **第 10 个样本 `t0+9.12ms`**（3ms 栅格下为第 4 个样本 `t0+9.05ms`；
//     v5 曾误写为"样本#3 ≈6.0ms" —— 那是把参照的**采样序号**当成了**时刻**，D-13 已订正）。
//   · 整用例收敛兜底 DONE_TIMEOUT_NS = 2 × (PRESET_BUDGET + OBS_WINDOW) = 2 × (2 + 12)ms = 28ms
//     —— 自洽性：DONE(28ms) ≥ 预置投影(0.42ms) + 观测窗(12ms) = 12.42ms，余量 15.6ms
//        最后再留一倍余量：外层兜底必须**严格晚于**子任务自己的所有硬上界之和，
//        否则会抢在子任务逐条判定之前误报（假失败）；同时覆盖预置段 2 次库调用
//        （库内**无报错式**超时：`set_data_ram` 无界；`polling_data_chk` 只有**静默** 50ms
//         软界 —— pcie_sequence.sv:870/:876，到了也不报错，故障只能靠本兜底封顶）
//        与采样循环最多 4 次的调度开销。
//   · 总墙钟投影（v6，按 0.209~0.216 ms 仿真/分钟）：预置 0.42ms + 观测早退 ≈9.12ms
//     ⇒ (9.54ms) ÷ (0.209~0.216) ≈ **正常路径 ≈45 分钟**（44.2~45.7）；
//     若早退不成立、走满 12ms（含预置 ≈12.8ms）⇒ ≈ **59~61 分钟**（59.4~61.3，落在 A3e 给的 58~61 包络内）
//
// 【已知未覆盖项（含原因）】
//  U1 未断言 polling 数据窗（DOM 控制器 0 的 0x200~0x3fc）内容与 golden 的逐字节一致性。
//     原因：那是参照用例 tc_dom_polling_new_01 的既有覆盖点；本用例定位是"状态序列"，
//     一个用例一个功能组。数据窗内容本轮只作为 I2C 从模型的 golden 灌入手段。
//  U2 只覆盖 8 台 DOM 控制器中的**控制器 0**（0x4000）。原因：实证链路（32/32 SPI 读）只在
//     0x403c 上成立，其余 7 台（0x443c…0x5c3c）在工程日志里**零次**访问，无先例；按"先求
//     能真跑出结果"的原则不扩面（扩面应另开用例并逐台给出实证）。
//  U3 DOM `+0x38 i2c_ctl.bit1 start` 这条 CPU 侧"直接发起一次 I2C"的通路未覆盖。原因：该位
//     文档写明"写清0"（`:1535`），且全工程未找到"CPU 写 start 位 → 真的起 I2C"的实测先例；
//     无实证先例就写它=可能写出"配置了但什么都没发生"的假通过（模板 §6 坑十一）。登记待裁决。
//  U4 未覆盖 9CLK 解锁通路（`+0x40 i2c_scl_unlock` WC / `+0x44 i2c_sta_lock`）。原因：属另一
//     功能组（总线死锁恢复），且会引入写操作与额外观测点。
//  U5 未覆盖 polling 的关闭方向（写 0x80=0 后状态是否停止变化）。原因："状态不变化"是**缺席**
//     类断言，窗口选择稍短就会漏判/误判；本轮不做弱断言。
//  U6（v4 新增 · **真实的覆盖率削减**）预置段与 polling 数据窗**只覆盖控制器 0**：
//     `polling_data_chk(0,1)` 只扫控制器 0 通道 0 的 128 字节窗口（32 笔读），
//     `set_data_ram(ch=0..3)` 只把 golden 灌进控制器 0 的 4 个通道；
//     **控制器 1~7（0x4400~0x5c00）的预置/数据窗完全未扫**。
//     原因 = **墙钟成本**（按修正口径：墙钟 ≈ 仿真时间 × 活动因子，A4_run_evidence.md §7.1）：
//     另 28 轮 ⇒ 仿真时间 +28 × 0.394ms ≈ **11.0ms** ⇒ 墙钟 ≈ 11.0 / 0.216 ≈ **51 分钟**，
//     即当前预置（0.42ms ≈ 1.9 分钟）的 **×26**、整用例正常路径（≈45 分钟）的 ≈**×1.1**。
//     由于本用例按 U1 不断言数据窗内容 ⇒ 该扩展**不改变任何断言结论**，只买墙钟；
//     若要覆盖控制器 1~7 的**状态序列**（i2c_sta），应另开用例并复用本用例的
//     1 轮预置 + 每台 `+0x3c` 观测骨架。
//
// 【待确认项】
//  T1 ★ `i2c_sta` 的 **bit2 在文档位定义表里没有登记**：文档 `:1544-1547` 只定义 bit0=err、
//     bit1=busy、bits[31:2]=Reserve（Reset 0）；而实测读到 **0x4（bit2=1）**（日志 10/32 次）。
//     `doc/_notes/02_cases_i2c_uart_dom.md` 把它记作 "poll-arm"，RTL 侧对应 `s_bmc_i2c_sta[2]`
//     （`dom_i2c_data_ram.sv:539-542` 注释/用法）。⇒ **bits[31:3] 可断言为 0，bit2 不可断言**，
//     请文档方补登记 bit2 语义（本用例按实测不改判据、也不迁就 RTL）。
//  T2 文档 `i2c_sta` 的 bits[31:2] 标的是 Reserve 且 **R/W**（`:1547`），但实测 bit2 会被硬件置 1
//     ⇒ "Reserve + R/W + 硬件会写"三者自相矛盾；已按 T1 记入待确认，未据此写断言。
//  T3 `+0x60 i2c_polling_cfg` 在实跑日志里 **0 次访问**，且其 Reset 文档自相矛盾
//     （汇总 `:1409` 写 0x10、位定义 `:1627-1632` 写 bit0=0x0 / bit7:4=0xf ⇒ 已知条目 C38）。
//     本用例因此**不用它做使能**（改用有实测支撑的全局 0x9c），该寄存器本轮不覆盖。
//  T4 全局 `0x80` 的语义跨文档略有不一致（`:419` 汇总注"cpu rtc跟bmc rtc优先级控制"、
//     `:500-503` 位定义写 "1：开启polling"）。本用例按**位定义表**（铁律 3）取"bit0=开启 polling"，
//     并以实测（写 1 后 0x80 读回 1 且后续 BUSY 起）为准；请文档方统一表述。
//  T5 `i2c_sta` 的可见性只在 **BMC SPI 通道**上有实证（日志 32/32 走 `[SPI_RD]`，0 次 PCIE）。
//     文档 `:1385` 只写"CPU接口访问"，未说明 BMC 侧为何可见 ⇒ 通道标注与实际不符，请接口方确认。
//
// 【红线遵守】
//   - 零异常写法：不使用 PCIE_REG_RDCHK（它失败只 `uvm_info` 打 *E、不发 `uvm_error`，
//     会让回归判 OK —— 见 SKILL.md §3 铁律 1）；所有失败路径**双写** `*E` + `` `uvm_error ``。
//   - 不自造判据：每条断言都在上方写清"怎样才能失败"；不写恒真式。
//   - 不动 TESTLIB/、RTL/、TB/、PKG/；本文件写在验收沙箱。
//   - 写后读只用于 R/W 寄存器（0x9c/0x80）；RO 的 0x403c **只读轮询**，绝不写。
//============================================================================*/
`ifndef TC_DOM_POLLING_TRIG_CHK_01__SV
`define TC_DOM_POLLING_TRIG_CHK_01__SV

//###########################################################
// 固定包含顺序（照抄，顺序错了会报 package 未定义）
//###########################################################
import uvm_pkg::*;
`include "uvm_macros.svh"
//###########################################################
`include "top_pkg.sv"
`include "crg_pkg.sv"
`include "macros_pkg.sv"
`include "packet.sv"
import macros_pkg::*;
import top_pkg::*;
import PACKET::*;
//###########################################################
// 句柄短宏：本用例用 BMC SPI（写使能 / 读状态）+ PCIE（写触发 / 读回）
//###########################################################
`define CRG_SQR_PERIOD(PID, PERIOD) '{top_env0.m_top_vsqr.m_crg_sqrs[PID], PERIOD}
`define PCIE_SQR       top_env0.m_top_vsqr.m_pcie_sqr
`define SPI_MST(PID)   top_env0.spi_msts[PID]
`define I2C_SLV(PID)   top_env0.i2c_slvs[PID]
//###########################################################
// TEST BEGIN
//###########################################################
`DEF_TESTCASE_BEGIN(`TEST_NAME,base_test)

    //-------------------------------------------------------------------------
    // 地址表：全局地址 = <段基址> + <块内偏移>。任何地方都不允许只写块内偏移。
    //-------------------------------------------------------------------------
    // 段基址
    localparam bit [31:0] GLOBAL_SEG_BASE = 32'h0000;   // 全局寄存器段（文档 :386 的 0x0000 段）
    localparam bit [31:0] DOM_SEG_BASE    = 32'h4000;   // DOM 段基址（文档 :1386；TB/tbtop.sv:67 DOME_RTC_ADDR）
    localparam bit [31:0] DOM_BLK_STRIDE  = 32'h0400;   // DOM 块步长（文档 :1386；TB/tbtop.sv:68 DOME_RTC_OFFSET）
    localparam bit [31:0] DOM0_BLK_BASE   = DOM_SEG_BASE + DOM_BLK_STRIDE * 32'd0; // = 0x4000，控制器 0 块基址

    // 块内偏移
    localparam bit [31:0] GLOBAL_BMC_RTC_EN_OFF      = 32'h9c; // 全局段 + 0x9c = bmc_rtc_en[9:0]（仅 BMC 接口）
    localparam bit [31:0] GLOBAL_POLLING_EN_SYS_OFF  = 32'h80; // 全局段 + 0x80 = Polling_en_sys（仅 CPU 接口）
    localparam bit [31:0] DOM0_I2C_STA_OFF           = 32'h3c; // DOM 控制器0块内 + 0x3c = i2c_sta（RO）

    // 全局地址 = 段基址 + 块内偏移
    localparam bit [31:0] BMC_RTC_EN_ADDR    = GLOBAL_SEG_BASE + GLOBAL_BMC_RTC_EN_OFF;     // = 0x009c
    localparam bit [31:0] POLLING_EN_SYS_ADDR= GLOBAL_SEG_BASE + GLOBAL_POLLING_EN_SYS_OFF; // = 0x0080
    localparam bit [31:0] DOM0_I2C_STA_ADDR  = DOM0_BLK_BASE  + DOM0_I2C_STA_OFF;           // = 0x403c（DOM 控制器0 的 i2c_sta）

    //-------------------------------------------------------------------------
    // 期望值（唯一基准 = 接口文档「位定义表」/「汇总表」中与位定义一致的那一处）
    //-------------------------------------------------------------------------
    localparam bit [31:0] EXP_BMC_RTC_EN      = 32'h0000_01ff; // 文档 :535-546：bit8..bit0 = bmc_rtc_en8..0（写 0x1ff 与参照实证一致；bit9 保持 0）
    localparam bit [31:0] EXP_POLLING_EN_PRE  = 32'h0000_0000; // 文档 **位定义表 :503**（Reset 0x0）+ 汇总 :419（Reset 0x0000）两处一致（触发前必须还是复位值）
    localparam bit [31:0] EXP_POLLING_EN_POST = 32'h0000_0001; // 文档 :500-503：bit0=1 开启 polling
    localparam bit [31:0] STA_BUSY_MASK       = 32'h0000_0002; // 文档 :1546：bit1 = busy（1:正在通信）
    localparam bit [31:0] STA_ERR_MASK        = 32'h0000_0001; // 文档 :1545：bit0 = err（1:I2C 通信异常）
    localparam bit [31:0] STA_RESERVED_MASK   = 32'hffff_fff8; // 文档 :1547：bits[31:3] Reserve（Reset 0）→ 必须为 0
    //   注：bit2 属文档未登记位（实测会出现 0x4），故按 T1 不纳入任何断言。

    //-------------------------------------------------------------------------
    // 并发/超时参数（推导见文件头【超时预算推导】；单位显式乘 1ns，避免依赖 timescale）
    //   NUM_TEST_TASKS = 参与 test_done 的并发子任务数 = 1（I2C 从模型线程是"服务线程"，
    //   无限应答、不参与 test_done —— 与参照用例一致）
    //-------------------------------------------------------------------------
    localparam int NUM_TEST_TASKS     = 1;
    localparam int RD_TIMEOUT_NS      = 1_000_000;   // 1ms  单笔总线读超时（≈3125 × 0.32us）
    localparam int SAMPLE_GAP_NS      = 1_000_000;   // 1ms  采样节拍（为保证覆盖 9.047ms onset；3ms 栅格只余 1 次机会，D-12）
    localparam int OBS_WINDOW_NS      = 12_000_000;  // 12ms 状态观测窗（BUSY 首现 9.047ms × 1.33，薄余量；12ms≈56min 墙钟）
    localparam int PRESET_BUDGET_NS   = 2_000_000;   // 2ms 预置段预算（v4：1 轮 = 32 笔读 ≈0.42ms 仿真 ⇒ ×4.8）
    localparam int MIN_SAMPLES        = 3;           // 有效采样下界（值不动；1ms 节拍 ⇒ 12ms 窗最多 12 个样本，下界宽松）
    localparam int DONE_TIMEOUT_NS    = 28_000_000;  // 28ms = 2 × (2ms 预置 + 12ms 观测)；墙钟投影见文件头

    bit [NUM_TEST_TASKS-1:0] test_done;

    //=========================================================================
    // m_build_phase：只做配置（与同族用例一致：Pango/AMD2P64）
    //=========================================================================
    function void m_build_phase(uvm_phase phase);
        top_cfg m_top_cfg = `CREATE_OBJ(top_cfg, "m_top_cfg")
        m_top_cfg.m_pcie_cfg.m_if_mode = pcie_pkg::AMD2P64;
        uvm_config_db#(top_cfg)::set(this, "top_env0", "m_top_cfg", m_top_cfg);
    endfunction : m_build_phase

    //=========================================================================
    // m_run_phase
    //=========================================================================
    task m_run_phase(uvm_phase phase);
        `PHASE_RAISE_OBJECTION            // 惯例：与末尾 DROP 配对（宏内 run_phase 还会 raise/drop 一次）
        //#####################################################################
        // 1. 时钟与复位（照抄同族惯例：先起 CRG，再 #10us 稳环境）
        //    PID0=25MHz / PID1=62.5MHz / PID2=125MHz —— 与参照用例的三个通道一致；
        //    polling 依赖的内部节拍在参照实测里由这三个通道即可跑起来（模板 §6 坑九的提醒已核）
        //#####################################################################
        begin : CLK_PROC
            crg_pkg::ClockUtil::sqr_period_t sqr_period_q[$] = '{
                `CRG_SQR_PERIOD(0, 40 /*25MHz*/   ),
                `CRG_SQR_PERIOD(1, 16 /*62.5MHz*/ ),
                `CRG_SQR_PERIOD(2, 8  /*125MHz*/  )
            };
            crg_pkg::ClockUtil::get_inst().foreach_clock_gen(sqr_period_q);
            crg_pkg::ClockUtil::get_inst().foreach_wait_reset_deassert(sqr_period_q);
        end
        // 等环境稳定（DUT 内部复位/初始化状态机跑完；模板/SKILL 规定的相位序固定项）
        #10us;
        `PR_STR($sformatf("%s%s", "Start TestCase...>>>", {32{"@"}}))

        //#####################################################################
        // 2. I2C 从模型服务线程（(c) 的答案：DOM 主控要有器件应答，err 才会保持 0）
        //    它们无限应答、不参与 test_done；必须在预置灌数据之前起动
        //#####################################################################
        `FORKJN_FOR_BLK(`I2C_SLV_NUM, I2C_SLV_RW)

        //#####################################################################
        // 3. 测试子任务：使能 → 触发 → 观测状态序列
        //#####################################################################
        `FORKJN_FOR_BLK(NUM_TEST_TASKS, DOM_TRIG_CHK)

        //#####################################################################
        // 4. 结束条件：wait(test_done) + 超时兜底（铁律 5/6）
        //    - 命名 fork + disable <label>：只杀本 wait 的两支，不影响其它 join_none 子任务
        //    - 超时后仍置位 test_done：避免 phase 挂死，同时保证日志有 *E
        //#####################################################################
        fork : DONE_WAIT_FORK
            // 等价于工程惯例的 wait(test_done)；这里显式比到位宽
            wait (test_done == {NUM_TEST_TASKS{1'b1}});
            begin
                #(DONE_TIMEOUT_NS * 1ns);
                $display("chk_f *E DOM_TRIG_CHK DONE_TIMEOUT seg 0x%08h: test_done=0x%0h, not converged within %0dms",
                         DOM_SEG_BASE, test_done, DONE_TIMEOUT_NS/1_000_000);
                `uvm_error("DOM_TRIG_CHK", $sformatf("DONE_TIMEOUT: seg=0x%08h test_done=0x%0h not converged within %0dms",
                           DOM_SEG_BASE, test_done, DONE_TIMEOUT_NS/1_000_000))
                test_done = {NUM_TEST_TASKS{1'b1}};
            end
        join_any
        disable DONE_WAIT_FORK;
        `PHASE_DROP_OBJECTION             // 与开头 RAISE 配对
    endtask : m_run_phase

    //=========================================================================
    // 失败报告（**双写**：① 含 *E 的文本；② `uvm_error）—— 铁律 1
    //   name : 检查点名（配合地址，构成全局唯一 desc）
    //=========================================================================
    task fail_both(string name, bit [31:0] addr, string detail);
        $display("chk_f *E DOM_TRIG_CHK %s @0x%08h: %s", name, addr, detail);
        `uvm_error("DOM_TRIG_CHK", $sformatf("%s @0x%08h: %s", name, addr, detail))
    endtask : fail_both

    task pass_note(string name, bit [31:0] addr, string detail);
        $display("chk_s DOM_TRIG_CHK %s @0x%08h: %s", name, addr, detail);
        `uvm_info("DOM_TRIG_CHK", $sformatf("%s @0x%08h: %s", name, addr, detail), UVM_LOW)
    endtask : pass_note

    //=========================================================================
    // 带超时的 BMC SPI 读/写（铁律 5）
    //   用宏 `SPI_MST(2) 直取句柄，避免书写 agent class 名；
    //   命名 fork + disable <label>：只中止本笔，不会波及 m_run_phase 里别的 fork。
    //   ★ 超时后调用方必须立即结束子任务（不再发后续访问）：被中止的访问可能留下未释放的
    //     总线/互斥状态，继续访问会互相干扰。
    //=========================================================================
    task bmc_spi_rd_to(bit [31:0] addr, output bit [31:0] data, output bit to);
        data = 32'h0;
        to   = 1'b0;
        fork : BSPI_RD_FORK
            `SPI_MST(2).set_read(addr, data);
            begin
                #(RD_TIMEOUT_NS * 1ns);
                to = 1'b1;
            end
        join_any
        disable BSPI_RD_FORK;
    endtask : bmc_spi_rd_to

    task bmc_spi_wr_to(bit [31:0] addr, bit [31:0] data, output bit to);
        to = 1'b0;
        fork : BSPI_WR_FORK
            `SPI_MST(2).set_write(addr, data);
            begin
                #(RD_TIMEOUT_NS * 1ns);
                to = 1'b1;
            end
        join_any
        disable BSPI_WR_FORK;
    endtask : bmc_spi_wr_to

    //=========================================================================
    // 子任务：DOM 控制器 0 「使能 → 触发 → 观测状态序列」
    //   通道：使能/读状态走 BMC SPI（`SPI_MST(2)`，与文档"仅 BMC"标注一致）；
    //         触发/读回走 PCIE（CPU 侧，与文档"仅 CPU"标注一致）。
    //=========================================================================
    task DOM_TRIG_CHK(int pid);
        bit [31:0] rdata;
        bit [31:0] v, v_prev;
        bit        to;
        bit        seen_busy, err_seen, changed, hi_bad;
        bit        rd_to_seen;
        bit        first_sample;
        int        samples;
        time       t0;
        string     ID = $sformatf("DOM_TRIG_CHK_CTRL_%0d", pid);

        pcie_pkg::pcie_seq m_pcie_seq = `CREATE_OBJ(pcie_pkg::pcie_seq, "m_pcie_seq")
        m_pcie_seq.set_sequencer(`PCIE_SQR);

        `uvm_info(ID, $sformatf("BEGIN: DOM ctrl%0d seg 0x%08h block 0x%08h; enable@0x%08h, trigger@0x%08h, sta@0x%08h",
                  pid, DOM_SEG_BASE, DOM0_BLK_BASE, BMC_RTC_EN_ADDR, POLLING_EN_SYS_ADDR, DOM0_I2C_STA_ADDR), UVM_LOW)

        //---------------------------------------------------------------------
        // 0) BMC SPI 通道就绪（时序 160/240/240/400 取自参照用例 m_run_phase）
        //---------------------------------------------------------------------
        `SPI_MST(2).setTiming(160, 240, 240, 400);
        `SPI_MST(2).startEnv();
        `SPI_MST(2).setMode(3);                 // SPI-MODE:3
        `SPI_MST(2).setConfig(1, 9);            // msb=1, burstSize=9
        pcie_pkg::spi_mt = `SPI_MST(2);         // 库函数 polling_data_chk(bmc_flg=1) 依赖该静态句柄

        //---------------------------------------------------------------------
        // 1) 使能：全局 0x9c bmc_rtc_en[9:0] = 0x1ff（仅 BMC 接口，文档 :535-546）
        //---------------------------------------------------------------------
        bmc_spi_wr_to(BMC_RTC_EN_ADDR, EXP_BMC_RTC_EN, to);
        if (to) begin
            fail_both("ENABLE_WR_TIMEOUT", BMC_RTC_EN_ADDR,
                      "BMC SPI write of bmc_rtc_en did not return within 1ms");
            test_done[pid] = 1'b1;
            return;
        end
        bmc_spi_rd_to(BMC_RTC_EN_ADDR, rdata, to);
        if (to) begin
            fail_both("ENABLE_RD_TIMEOUT", BMC_RTC_EN_ADDR,
                      "BMC SPI read-back of bmc_rtc_en did not return within 1ms");
            test_done[pid] = 1'b1;
            return;
        end
        // O1：怎样才能失败 —— 读回 != 0x1ff（写不进 / 通道错 / 权限错）
        if (rdata !== EXP_BMC_RTC_EN) begin
            fail_both("ENABLE_RDCHK", BMC_RTC_EN_ADDR,
                      $sformatf("RD=0x%08h != EXP=0x%08h (bmc_rtc_en write did not land)", rdata, EXP_BMC_RTC_EN));
        end else begin
            pass_note("ENABLE_RDCHK", BMC_RTC_EN_ADDR, $sformatf("RD=0x%08h == EXP=0x%08h", rdata, EXP_BMC_RTC_EN));
        end

        //---------------------------------------------------------------------
        // 2) 预置（实证配方，参照用例 :125-129）：核对 polling 数据窗上电初值 0xff，
        //    并把 golden 数据灌进 I2C 从模型（(c)：让 DOM 主控的访问被应答，err 保持 0）
        //    ★ v4 墙钟整改（A4 attempt1 实测根因）：密集读扫 **32 轮 → 1 轮**（只扫控制器 0 通道 0）。
        //      依据：ACCEPTANCE_PLAN §1 的 U1 已声明"本用例不断言 polling 数据窗内容" ⇒
        //            不拿它做判据，就不必把 8 台控制器 × 4 通道全扫一遍；预置段的唯一目的是
        //            "证明使能 + 预置通路可用"，1 轮足够。
        //      笔数：`polling_data_chk` 内是 `for (i < 128/4)` ⇒ **32 笔** BMC SPI 读/轮
        //            （实测参照日志 LOG/tc_dom_polling_new_01_1_run.log：触发前 SPI_RD 共 1025 笔
        //             = 32 次调用 × 32 笔 + 0x9c 读回 1 笔 ⇒ 每轮 32 笔，不是 128 笔）
        //      墙钟（修正口径：墙钟 ≈ 仿真时间 × 活动因子，A4_run_evidence.md §7.1）：
        //      0.42ms 仿真 / 0.216ms·分钟⁻¹ ≈ **1.9 分钟**
        //    注：库内**无报错式**超时（`set_data_ram` 无界；`polling_data_chk` 只有静默 50ms
        //        软界 —— pcie_sequence.sv:870/:876，到了也不报错）⇒ 整段由 DONE_TIMEOUT_NS 封顶
        //---------------------------------------------------------------------
        m_pcie_seq.polling_data_chk(0, 1);          // 控制器0 通道0：上电初值应为 0xff（库内以 *E 文本报告，非本用例断言对象）
        //    为控制器 0 的 4 个通道都灌 golden：`set_data_ram` 内的 `putbpWord` 是 `function void`
        //    （TB/AGENTS/I2C-Agent/i2c_s.sv:419）⇒ **零总线读、零墙钟**，故不构成代价；保留它是
        //    为了不依赖"未编程的从模型也会应答"这一无实证假设（n = 控制器×4 + 通道 ⇒ 控制器 0 = 0..3）
        for (int ch = 0; ch < `DOME_CHN_NUM; ch++) begin
            m_pcie_seq.set_data_ram(ch, 0, 256);    // 灌 golden 到 i2c_slv[控制器0 的通道 ch]
        end

        //---------------------------------------------------------------------
        // 2b) D-8 采纳的"先 0"：触发**之前**读一次 i2c_sta，断言 busy(bit1)==0
        //     怎样失败：== 1（触发前引擎就忙 ⇒ 上一轮命令残留 stale-1 / 状态机未复位）
        //     这正是模板 §3.3（tc_dom_polling_template.md:128-129）要求的手型前半段，
        //     作用是排除 stale-1 假命中；详见文件头 (b) 段对"为何省去后半段"的说明。
        //---------------------------------------------------------------------
        bmc_spi_rd_to(DOM0_I2C_STA_ADDR, rdata, to);
        if (to) begin
            fail_both("STA_IDLE_RD_TIMEOUT", DOM0_I2C_STA_ADDR,
                      $sformatf("BMC SPI pre-trigger read of i2c_sta did not return within %0dms", RD_TIMEOUT_NS/1_000_000));
            test_done[pid] = 1'b1;
            return;
        end
        if ((rdata & STA_BUSY_MASK) !== 32'h0) begin
            fail_both("STA_IDLE_BEFORE", DOM0_I2C_STA_ADDR,
                      $sformatf("pre-trigger i2c_sta=0x%08h has busy(bit1)=1 (stale-1 / FSM not idle before we start a fresh poll)", rdata));
        end else begin
            pass_note("STA_IDLE_BEFORE", DOM0_I2C_STA_ADDR,
                      $sformatf("pre-trigger i2c_sta=0x%08h busy(bit1)=0 (idle, stale-1 excluded)", rdata));
        end

        //---------------------------------------------------------------------
        // 3) 触发：全局 0x80 Polling_en_sys.bit0 0 → 1（仅 CPU 接口，文档 :500-503）
        //    ★ 字节序：set_read/set_write 内部做 {b0,b1,b2,b3} 翻转（pcie_sequence.sv:641-652），
        //      故这里比较的是"CPU 可见值"；日志里显示为 0x1000000 是翻转前的原始镜像值。
        //---------------------------------------------------------------------
        m_pcie_seq.set_read(POLLING_EN_SYS_ADDR, rdata);
        // O2：怎样才能失败 —— 触发前读回 != 0（复位值被破坏 / 地址打空读到别处）
        if (rdata !== EXP_POLLING_EN_PRE) begin
            fail_both("TRIG_BEFORE", POLLING_EN_SYS_ADDR,
                      $sformatf("pre-trigger RD=0x%08h != EXP=0x%08h (not at reset value)", rdata, EXP_POLLING_EN_PRE));
        end else begin
            pass_note("TRIG_BEFORE", POLLING_EN_SYS_ADDR, $sformatf("pre-trigger RD=0x%08h == EXP", rdata));
        end

        m_pcie_seq.set_write(POLLING_EN_SYS_ADDR, EXP_POLLING_EN_POST);
        m_pcie_seq.set_read(POLLING_EN_SYS_ADDR, rdata);
        // O3：怎样才能失败 —— 写 1 后读回 != 1（写不进 / 通道错 ⇒ 触发没发生）
        if (rdata !== EXP_POLLING_EN_POST) begin
            fail_both("TRIG_AFTER", POLLING_EN_SYS_ADDR,
                      $sformatf("post-trigger RD=0x%08h != EXP=0x%08h (trigger did not land)", rdata, EXP_POLLING_EN_POST));
            test_done[pid] = 1'b1;                  // 触发无效时后续观测没有意义，直接收敛
            return;
        end else begin
            pass_note("TRIG_AFTER", POLLING_EN_SYS_ADDR, $sformatf("post-trigger RD=0x%08h == EXP", rdata));
        end

        //---------------------------------------------------------------------
        // 4) 观测：每 **1ms** 采一次 DOM 控制器0 的 i2c_sta（RO，只能读；文档 :1402/:1538-1547）
        //    窗口 12ms：BUSY 实测首现于触发后 9.047ms ⇒ **窗口界**余量 12/9.047 = 1.33×（薄）；
        //    按**采样机会**口径：3ms 栅格只剩 1 次机会（第 4 个样本 t0+9.05ms，其后 2.95ms 死尾），
        //    故用 1ms 栅格 ⇒ 窗内 12 个样本、onset 后 3 次机会（D-12）。窗口本身是硬上界，不会挂死
        //    ★ 成功即早退：仅当 O7(busy 已见) ∧ O8(值已变化) 都已满足时 break（见循环末）。
        //      带 `samples >= MIN_SAMPLES` 前提的理由：O8 本来就在 samples >= MIN_SAMPLES 时才裁决
        //      （A3b/A3 D-2 的结构），而参照实测序列 0x4→0x2 只需 **2** 个样本就能同时满足 O7/O8 ——
        //      若不带上该前提，早退会让 samples=2 < MIN_SAMPLES 去触发 O4 的"样本不足"，
        //      凭空造出一条**新的假失败**。
        //      早退**不产生通过结论**：通过仍由 O4~O8 各自裁决；不满足则走满 12ms 窗。
        //      取舍：早退后 O6 的"未观察到 err"覆盖的是早退前的样本（12ms 窗下的必然取舍）。
        //---------------------------------------------------------------------
        samples      = 0;
        seen_busy    = 1'b0;
        err_seen     = 1'b0;
        changed      = 1'b0;
        hi_bad       = 1'b0;
        rd_to_seen   = 1'b0;
        first_sample = 1'b1;
        v_prev       = 32'h0;
        v            = 32'h0;
        t0           = $time;

        while (($time - t0) < (OBS_WINDOW_NS * 1ns)) begin
            bmc_spi_rd_to(DOM0_I2C_STA_ADDR, v, to);
            if (to) begin
                // 本笔读超时：不再继续发起访问（避免与被中止的访问抢总线），提前结束采样。
                // 失败由下方 O4 的"样本数不足"分支**唯一**报出（一条根因一条 *E，不重复刷屏）
                rd_to_seen = 1'b1;
                break;
            end

            samples++;
            if (v[1] === 1'b1) seen_busy = 1'b1;                      // bit1 = busy
            if (v[0] === 1'b1) err_seen  = 1'b1;                      // bit0 = err
            if ((v & STA_RESERVED_MASK) !== 32'h0) hi_bad = 1'b1;     // bits[31:3] 必须为 0
            if (!first_sample && (v !== v_prev)) changed = 1'b1;      // 值序列发生过变化

            `uvm_info(ID, $sformatf("sample#%0d @%0t: i2c_sta=0x%08h (busy=%0b err=%0b)", samples, $time, v, v[1], v[0]), UVM_LOW)
            $display("chk_i DOM_TRIG_CHK sample#%0d @%0t: i2c_sta=0x%08h", samples, $time, v);

            v_prev       = v;
            first_sample = 1'b0;

            // ★ v5 成功即早退（**不放宽任何判据**）：O7(seen_busy) ∧ O8(changed) 都已满足、
            //    且 samples >= MIN_SAMPLES（O8 的裁决前提）时才允许 break；早退**不产生通过结论**
            //    （通过仍由 O4~O8 各自裁决，见下方判定段）。不满足则走满 12ms 窗，由既有失败分支报出。
            if (seen_busy && changed && (samples >= MIN_SAMPLES)) begin
                `uvm_info(ID, $sformatf("EARLY_EXIT after %0d samples @%0t (O7 busy seen & O8 value changed)", samples, $time), UVM_LOW)
                $display("chk_i DOM_TRIG_CHK early-exit after %0d samples @%0t", samples, $time);
                break;
            end
            #(SAMPLE_GAP_NS * 1ns);
        end

        //---------------------------------------------------------------------
        // 5) 判定（逐条给"怎样才能失败"）
        //    O4 是"观测证据是否充分"的**前置门**：样本不足时由它唯一报出，O5~O8 一律不裁决
        //    （v1 的假失败路径是"采样不足被 O8 误报成状态没动"，A3 D-2；这里从结构上消除）
        //---------------------------------------------------------------------
        // O4：出现读超时 **或** 有效采样数 < MIN_SAMPLES ⇒ 观测证据不足
        //     怎样失败：(i) 任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回（`rd_to_seen=1`，无论样本数
        //     多少都判失败 —— A3b D-10：超时这条根因自己必须能触发双写）；(ii) 样本数 < 3。
        //     ★ v1 的 `if (samples == 0)` 在控制流上不可达（恒真式断言，A3 D-1），已删除。
        if ((samples < MIN_SAMPLES) || rd_to_seen) begin
            fail_both("STA_SAMPLES_SHORT", DOM0_I2C_STA_ADDR,
                      $sformatf("read timeout seen=%0b / samples=%0d < MIN_SAMPLES=%0d in %0dms window: insufficient observation evidence",
                                rd_to_seen, samples, MIN_SAMPLES, OBS_WINDOW_NS/1_000_000));
        end else begin
            pass_note("STA_SAMPLES_SHORT", DOM0_I2C_STA_ADDR,
                      $sformatf("samples=%0d >= MIN_SAMPLES=%0d (read_timeout_seen=%0b)", samples, MIN_SAMPLES, rd_to_seen));

            // O5：任一采样 bits[31:3] != 0 ⇒ 与文档 Reserve(Reset 0) 不符
            if (hi_bad) begin
                fail_both("STA_RESERVED", DOM0_I2C_STA_ADDR,
                          "some sample has bits[31:3] != 0, but doc :1547 marks them Reserve(Reset 0)");
            end else begin
                pass_note("STA_RESERVED", DOM0_I2C_STA_ADDR, "all samples bits[31:3] == 0");
            end

            // O6：任一采样 bit0 == 1 ⇒ I2C 通信异常（本用例已起 I2C 从模型应答）
            if (err_seen) begin
                fail_both("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR,
                          "i2c_sta.bit0(err)=1 observed -> I2C device did not respond or the path is broken");
            end else begin
                pass_note("STA_ERR_CLEAR", DOM0_I2C_STA_ADDR, "err(bit0) never set in the window");
            end

            // O7：整个窗口 bit1 从未为 1 ⇒ polling 未启动 / 节拍未跑 / 触发未生效
            //     （★ 与参照用例的差别：它的 50ms 软超时是静默通过的；这里超时即失败）
            if (!seen_busy) begin
                fail_both("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR,
                          $sformatf("busy(bit1) never seen as 1 within %0dms (polling not started / tick not running)",
                                    OBS_WINDOW_NS/1_000_000));
            end else begin
                pass_note("STA_BUSY_SEEN", DOM0_I2C_STA_ADDR, "busy(bit1)==1 observed at least once");
            end

            // O8：全部采样完全相同 ⇒ 状态机没动（"读到了但没变化"）
            //     ★ 仅在 samples >= MIN_SAMPLES 时裁决（A3 D-2）：样本不足已由 O4 报出，
            //       不会再把"采样不足"误报成"状态没动"
            if (!changed) begin
                fail_both("STA_CHANGED", DOM0_I2C_STA_ADDR,
                          $sformatf("i2c_sta value never changed across %0d samples", samples));
            end else begin
                pass_note("STA_CHANGED", DOM0_I2C_STA_ADDR, $sformatf("value changed across %0d samples", samples));
            end
        end

        `uvm_info(ID, $sformatf("END pid=%0d: samples=%0d seen_busy=%0b err_seen=%0b changed=%0b hi_bad=%0b",
                  pid, samples, seen_busy, err_seen, changed, hi_bad), UVM_LOW)
        test_done[pid] = 1'b1;                    // 本子任务唯一收敛点（位宽与并发数一致）
    endtask : DOM_TRIG_CHK

    //=========================================================================
    // I2C 从模型服务线程（照抄参照用例 tc_dom_polling_new_01.sv:228-235）
    //   作用：给 DOM I2C 主控一个会应答的器件（(c)）；无限应答，不参与 test_done
    //=========================================================================
    task I2C_SLV_RW(int pid);
        string ID = $sformatf("I2C_SLV_RW_%0d", pid);
        pcie_pkg::i2c_slv[pid] = `I2C_SLV(pid);
        `I2C_SLV(pid).startEnv();
    endtask : I2C_SLV_RW

`DEF_TESTCASE_END

`endif
