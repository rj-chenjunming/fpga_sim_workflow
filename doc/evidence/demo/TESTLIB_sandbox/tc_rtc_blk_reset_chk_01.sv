/*=============================================================================
//     FileName: tc_rtc_blk_reset_chk_01.sv
//         Desc: 0x2000 段 RTC I2C Master 控制器 0 —— 复位值（只读初值）检查
//       备注: 演示沙箱件（doc/agents/_demo/TESTLIB_sandbox/），未进 TESTLIB/
//=============================================================================
// 【目标】
//   对 0x2000 段「RTC I2C Master 控制器 0」的三个 I2C 配置寄存器做复位值断言：
//   在**写任何寄存器之前**（本用例全程不做任何写）读一次，与接口文档「位定义表」
//   的 Reset 列比对。R/W 寄存器也必须"复位后立即读"，不得做"写后读"。
//
// 【检索留痕】（SKILL.md §2 三步检索）
//   ① 模板库：
//      - doc/skills/simenv-test/test_case_template.md   （通用骨架：三类模式 + 陷阱清单）
//      - doc/templates/tc_template_reg.sv              （寄存器类 .sv 骨架）
//        ※ doc/skills/simenv-test/tc_reg_rw_template.md 本工程**尚未生成**，
//          按任务约定改用 doc/templates/tc_template_reg.sv 兜底
//   ② 语料库（锁风格，不锁地址）：
//      - TESTLIB/tc_pcie_rw_02.sv  L107-130（PCIE_REG_RW 子任务骨架）
//                                  L177-184（rtc_reg_test：PCIE 通道读 0x2000+0x00/0x04/0x08
//                                            复位值 0x4e/0x7c/0x7c）★ 最贴近的同族参照
//                                  L367-387（reg_field_test：先读复位值再写）
//      - TESTLIB/tc_bmc_i2c_03.sv  L262-269（rtc_reg_test，BMC 通道同一组复位值 0x4e/0x7c/0x7c）
//      - TESTLIB/tc_rtc_01.sv      L43-100（RTC 族头注释 / 句柄短宏 / CRG 起时钟复位风格）
//   ③ 项目专属基准（接口文档 doc/reference/TCS9620-64CH-F-RJ-MAC_FPGA_软硬件接口文档.md）：
//      - 段：3.1.2.3「I2C Master控制器RTC寄存器地址分配和说明」（L737）
//      - 段基址表 L745/L747：0x2000 为该段第 1 个基址（stride 0x200）
//      - 位定义表（**唯一基准**，铁律 3）：
//          i2c_scale   L777-785  Offset:+0x00  bits[7:0] scale   R/W Reset=0x4e；bits[31:8] Reserve R/W Reset=0
//          i2c_filter  L787-795  Offset:+0x04  bits[7:0] filter  R/W Reset=0x7c；bits[31:8] Reserve R/W Reset=0
//          i2c_timeout L797-805  Offset:+0x08  bits[7:0] timeout R/W Reset=0x7c；bits[31:8] Reserve R/W Reset=0
//        ⚠ 「寄存器汇总」表 L748-750 的 Reset 列把这三个都写成 0x00，是**成片错误**
//          （SKILL.md §3 铁律 3 / _FORMAT.md §4），本用例不采用。
//      - 交叉验证（不是基准，只用于确认取值方向）：
//          RTL  RTL/SRC/imports/SRC/i2c_master_scheduler_top/i2c_data_ram.sv:690-692
//               s_init_data: sr_init_addr[6:0]==0 -> 32'h4e / ==1 -> 32'h7c / ==2 -> 32'h7c（字地址 0/1/2 = 0x00/0x04/0x08）
//          TB   TB/tbtop.sv:64-65  `FPGA_OT9548_ADDR = 32'h2000 / `RTC_OFFSET = 32'h200（与文档 L747 前 9 个基址一致）
//       - 实测证据（同一通道、同一段，已被前人跑过）：
//          LOG/tc_pcie_rw_02_1_run.log: @ADDR[0x2000] -> 0x4e / @ADDR[0x2004] -> 0x7c / @ADDR[0x2008] -> 0x7c
//
// 【覆盖寄存器清单】（3 条，地址一律写 <段基址 0x2000> + <块内偏移>）
//   #  归属块（控制器）          寄存器        全局地址                块内偏移  属性  复位值   文档位定义表行号
//   1  RTC I2C Master 控制器0    i2c_scale     0x2000 + 0x00 = 0x2000  0x00      R/W   0x4e     L784
//   2  RTC I2C Master 控制器0    i2c_filter    0x2000 + 0x04 = 0x2004  0x04      R/W   0x7c     L794
//   3  RTC I2C Master 控制器0    i2c_timeout   0x2000 + 0x08 = 0x2008  0x08      R/W   0x7c     L804
//
// 【观测点】（本用例只读，无副作用可验）
//   O1 复位后（CRG 释放复位 + #10us）首读 = 位定义表 Reset（相位 1，3 条断言）
//   O2 不写任何寄存器的情况下复读，值必须与首读逐位一致（相位 2，3 条"通道/镜像可重复"断言）
//   O3 通道本身在 10us 级别可用：LOG/tc_upt_spi_01..06_1_run.log 的首次 PCIE 读在 10.505us 成功，
//      本用例首读时刻与之同档（#10us + 若干拍）
//
// 【读数据的字节序处理（务必先看，否则必然假失败）】
//   PCIE 通道的 `PCIE_REG_RD(addr,rdata)` 返回的是 **FPGA_RAM_MIRROR 的原始字**（pcie_sequence.sv:570），
//   而该镜像相对"CPU 可见的小端寄存器字"是**字节反序**的（项目惯例用 `PCIE_REG_RDCHK(...,big_d=1)`
//   翻转回来，见 pcie_sequence.sv:589-594）。实测：LOG/tc_rtc_07_1_run.log 的 `PCIE_REG_RD @ADDR[0x2000]
//   -> DATA[0x4e000000]`，而 LOG/tc_pcie_rw_02_1_run.log 的 RDCHK 打印 `@ADDR[0x2000] -> DATA[0x4e]`。
//   ⇒ 本用例用 raw2cpu() 做与 big_d 完全相同的字节翻转后再与位定义表 Reset 比对。
//     不用 PCIE_REG_RDCHK 的原因：它失败时只 `uvm_info` 打印含 `*E` 的文本、**不发 `` `uvm_error ``**，
//     不满足"失败路径双写"（铁律 1）。故本用例自建检查函数做双写。
//
// 【已知未覆盖项（含原因）】
//  U1 复位值**重载**未覆盖：只验"上电/初始复位后"的静态值，未验"块内软复位（0x2000+0x7c i2c_m_rst、
//     全局 0x50~0x70 复位类）后这三个寄存器是否重新载入 0x4e/0x7c/0x7c"。
//     原因：该验证必须先写复位寄存器，与本用例"写任何寄存器之前读"的只读口径直接冲突，须另开用例。
//  U2 只覆盖 10 个 RTC 控制器中的第 1 个（0x2000），未覆盖 0x2200/0x2400/.../0x3200 其余 9 个。
//     原因：一个用例只覆盖一个功能组；多实例须用差异化激励 + one-hot + 独立断言另开用例。
//  U3 写后读/位域掩码/保留位写 1 行为未覆盖（这三个是 R/W）。原因：本用例定位为"复位值检查"，
//     全程零写入；RW 属性与掩码属另一功能组。
//  U4 复位值之外的文档宣称未验（如 bits[31:8] Reserve 的写行为）。原因：同 U3（零写入）。
//  U5 未做动态访问路径反证（例如从 BMC 侧复读同址做交叉比对）。原因：0x2000 段文档无任何访问路径
//     限制标注（见待确认项 T1），在无依据的情况下不引入第二条通道。
//  U6（块身份限定）本用例三条复位值断言**无块身份敏感性**：0x2000 段与 0x4000 DOM 段在
//     +0x00/+0x04/+0x08 处**同名、同偏移、同 Reset 0x4e/0x7c/0x7c**（文档 DOM 汇总 L1387-1389、
//     DOM 位定义 L1424/L1434/L1444；RTL dom_i2c_data_ram.sv:733-739 的 s_init_data 同样给
//     word0/1/2 → 'h4e/'h7c/'h7c）⇒ 即使打到 DOM 段，这 3 条断言也会通过。块身份**完全由字面
//     地址 0x2000 保证**（已与文档 L745/L747、RTL TCS9620_MAC_TOP.v:201/:202 核对一致）。
//     若日后地址宏/基址被改动，这组断言**不会**自动发现"串块" → 需另加一条块身份锚点断言；
//     本轮按任务范围未加（不加"写后读"或额外寄存器读，以保持零写入与单功能组）。
//
// 【待确认项】
//  T1 ★ 0x2000 段在接口文档里**没有任何**"只能由 CPU/BMC 接口访问"标注（核对范围：文档 L737-L1067
//     整段，`grep -n "只能由\|CPU接口\|BMC接口"` 命中 0 行）。按铁律 4："没写限制 ≠ 没有限制"。
//     本用例选 **PCIE（CPU/PCIe）通道**，依据：
//       (a) 文档 BAR0 总表 L397 把 0x2000 段列入 BAR0（CPU/PCIe 侧）地址空间；
//       (b) RTL 模块级同时挂了两个寄存器口：TCS9620_MAC_TOP.v:1270 `CPU_REG_BASE_ADDR =
//           OUT_9548_I2C_ADDR + OUT_9548_I2C_OFFSET*j`（= 0x2000+0x200*j），:1272 的
//           `BMC_REG_BASE_ADDR` 是同一表达式 → 该段 CPU/BMC 双侧可达，文档两侧都没写限制；
//       (c) BMC 侧受全局门控：文档 L422 的 0x009c `bmc_rtc_en0` 复位 0x0，L542 注明
//           "只能由BMC接口访问，关闭则BMC无法RTC" → 复位态下 BMC 通道本就进不去；
//           CPU/PCIE 侧没有这层门控，所以"复位值检查"用 PCIE 更干净；
//       (d) 同族用例 tc_pcie_rw_02 已用 PCIE 通道读到同一组复位值（见上"实测证据"）。
//     **仍需接口/设计方确认 0x2000 段对 CPU 侧是否完全开放（有无隐藏门控）。**
//  T2 「控制器个数」文档自相矛盾：BAR0 总表 L397 写"控制器寄存器 1~6"，段内 L747 列 **10** 个基址
//     （含 0x3200），RTL 是 9 OUT + 1 IN = 10。本用例只碰 0x2000（两种说法都含它），不受影响。
//     本用例按文档 L745/L747 把 0x2000 记为"控制器 0"（第 1 个基址）；若项目命名以 1 起算，
//     则同一地址会被叫成"控制器 1"——地址唯一、命名待统一（见 doc/_notes/09_iface_doc_vs_case.md A 节）。
//  T3 若实测在 CRG 释放复位后 #10us（工程惯例）即读到**非**复位值，需先与"块初始化时序不足"区分：
//     本用例按接口文档断言（绝不迁就 RTL），此类 FAIL 应走 FAIL 三分类（分类 1 作者错 vs 分类 2 文档 vs RTL）。
//
// 【红线遵守】
//   - 零写入：不写 TESTLIB/RTL/TB/PKG，不在用例里写任何寄存器；不为通过而放松断言
//   - 所有"等"都有超时兜底（铁律 5：run_uvs_new.sh 从不传 +UVM_TIMEOUT=）；无固定延时收尾
//   - 无 uvm_hdl_force（本用例是总线级检查，不需要白盒）
//============================================================================*/
`ifndef TC_RTC_BLK_RESET_CHK_01__SV
`define TC_RTC_BLK_RESET_CHK_01__SV

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
// 句柄短宏（本用例只用 PCIE 通道；不改动其它通道的宏定义惯例）
//###########################################################
`define CRG_SQR_PERIOD(PID, PERIOD) '{top_env0.m_top_vsqr.m_crg_sqrs[PID], PERIOD}
`define PCIE_SQR       top_env0.m_top_vsqr.m_pcie_sqr
//###########################################################
// TEST BEGIN
//###########################################################
`DEF_TESTCASE_BEGIN(`TEST_NAME,base_test)

    //-------------------------------------------------------------------------
    // 地址表：全局地址 = <段基址 0x2000> + <块内偏移>。任何地方都不允许只写块内偏移。
    //   - 0x2000 段 = RTC I2C Master 控制器（接口文档 L737 段头 / L747 第 1 个基址）
    //     本用例只取第 1 个基址 0x2000，即"控制器 0"（命名歧义见头注释 T2）
    //   - TB 侧同址宏：TB/tbtop.sv:64 `FPGA_OT9548_ADDR(32'h2000)、:65 `RTC_OFFSET(32'h200)
    //     ★ 不照抄同族用例的 base_addr（本工程已有 121 个站点因 base_addr 写错而打空）
    //-------------------------------------------------------------------------
    // 段基址
    localparam bit [31:0] RTC_SEG_BASE        = 32'h2000;
    // 块内偏移（块内 0x00/0x04/0x08）
    localparam bit [31:0] RTC0_I2C_SCALE_OFF  = 32'h00;
    localparam bit [31:0] RTC0_I2C_FILTER_OFF = 32'h04;
    localparam bit [31:0] RTC0_I2C_TIMEOUT_OFF= 32'h08;
    // 全局地址 = 段基址 + 块内偏移
    localparam bit [31:0] RTC0_I2C_SCALE_ADDR   = RTC_SEG_BASE + RTC0_I2C_SCALE_OFF  ; // 0x2000 段控制器0 + 块内0x00 = i2c_scale
    localparam bit [31:0] RTC0_I2C_FILTER_ADDR  = RTC_SEG_BASE + RTC0_I2C_FILTER_OFF ; // 0x2000 段控制器0 + 块内0x04 = i2c_filter
    localparam bit [31:0] RTC0_I2C_TIMEOUT_ADDR = RTC_SEG_BASE + RTC0_I2C_TIMEOUT_OFF; // 0x2000 段控制器0 + 块内0x08 = i2c_timeout

    //-------------------------------------------------------------------------
    // 期望复位值：**唯一基准 = 接口文档「位定义表」**（不是「汇总表」，汇总表 L748-750 写 0x00 是错的）
    //   位定义表 bits[31:8] Reserve 的 Reset 也是 0 → 整字复位值 = 低 8 位复位值
    //-------------------------------------------------------------------------
    localparam bit [31:0] EXP_RST_I2C_SCALE   = 32'h0000_004e; // 文档 L784：bits[7:0]=0x4e，bits[31:8]=0
    localparam bit [31:0] EXP_RST_I2C_FILTER  = 32'h0000_007c; // 文档 L794：bits[7:0]=0x7c，bits[31:8]=0
    localparam bit [31:0] EXP_RST_I2C_TIMEOUT = 32'h0000_007c; // 文档 L804：bits[7:0]=0x7c，bits[31:8]=0

    //-------------------------------------------------------------------------
    // 并发/超时参数
    //   NUM_BLK_TASKS = 本用例并发子任务数 = 1（位宽必须等于并发数，见作者 §4.4）
    //   超时推导（口径按 doc/skills/simenv-test/_FORMAT.md §7：基数只用**背靠背**访问间隔）：
    //     ① 基数 T_rd = 0.32us：LOG/tc_pcie_rw_02_1_run.log 中 0x2000 的背靠背两次读
    //        @173.721us（L539）→ @174.041us（L542）；该日志 10513 条 PCIE_REG_RD 的相邻读间隔
    //        mode = median = 0.320us（min 0.224us）→ 单笔访问往返 ≈ 0.32us
    //        （禁止拿"相邻读间隔"的 max 当基数：它被用例层活动撑开，同工程实测 max 达 17.2ms）
    //     ② 单笔读自兜底 RD_TIMEOUT_NS = 1ms ≈ 3125 × T_rd（按 min 0.224us 也有 ≈4464×）
    //     ③ 收敛兜底 T_done = 6 × RD_TIMEOUT_NS + 2 × RD_TIMEOUT_NS = 8ms
    //        - 6 笔读 = 相位1 三笔（i2c_scale / i2c_filter / i2c_timeout）
    //                          + 相位2 三笔（同三处复读）
    //        - 余量 2 × RD_TIMEOUT_NS = 2ms 的理由：外层收敛兜底必须**严格晚于**子任务自己的
    //          最后一笔预算，否则会抢在子任务逐笔判定之前误报（即 Δ1 的病根）；同时覆盖 6 笔读
    //          之间 6 次断言调用（chk_reset_value ×3 + chk_repeat ×3，各内含 $display/$sformatf）
    //          与 6 个读超时分支判定的（零延时但非零）调度开销
    //     ④ 对照实测：6 笔理想耗时 ≈ 6 × 0.32us ≈ 1.92us，8ms ≈ 4170 × 理想值 → 兜底不会误触发
    //   （单位显式乘 1ns，避免依赖 timescale）
    //-------------------------------------------------------------------------
    localparam int NUM_BLK_TASKS    = 1;
    localparam int RD_TIMEOUT_NS    = 1_000_000; // 1ms：单笔读超时
    localparam int DONE_TIMEOUT_NS  = 8_000_000; // 8ms = 6 笔读 × 1ms + 2ms 余量：整用例收敛超时（兜底）

    bit [NUM_BLK_TASKS-1:0] test_done;

    //=========================================================================
    // m_build_phase：只做配置（与同族用例 tc_pcie_rw_02.sv:55-63 一致）
    //=========================================================================
    function void m_build_phase(uvm_phase phase);
        top_cfg m_top_cfg = `CREATE_OBJ(top_cfg, "m_top_cfg")
        // 与 tc_pcie_rw_02 / tc_rtc_01 相同的 PCIe 形态（实测日志里 PCIE_REG_*@3DW）
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
        // 等环境稳定（DUT 内部复位/初始化状态机跑完）
        #10us;
        `PR_STR($sformatf("%s%s", "Start TestCase...>>>", {32{"@"}}))

        //#####################################################################
        // 2. 并发子任务：只有 1 个（复位值检查）
        //    本用例**全程零写入**，所以"写任何寄存器之前读"这一条自动成立且更强
        //#####################################################################
        `FORKJN_FOR_BLK(NUM_BLK_TASKS, RTC_BLK_RESET_CHK)

        //#####################################################################
        // 3. 结束条件：wait(test_done)，并带超时兜底（铁律 5）
        //    - 命名 fork + disable <label>：只杀本 wait 的两支，不影响其它 join_none 子任务
        //    - 超时后仍置位 test_done：避免整个 phase 挂死，同时保证日志有 *E
        //#####################################################################
        fork : DONE_WAIT_FORK
            // 等价于工程惯例的 wait(test_done)；这里显式比到位宽（位宽 == 并发数 == 1）
            wait (test_done == {NUM_BLK_TASKS{1'b1}});
            begin
                #(DONE_TIMEOUT_NS * 1ns);
                $display("chk_f *E RTC0_RST TEST_TIMEOUT seg 0x%08h: test_done=0x%0h, not converged within %0dms",
                         RTC_SEG_BASE, test_done, DONE_TIMEOUT_NS/1_000_000);
                `uvm_error("RTC0_RST", $sformatf("TEST_TIMEOUT: seg=0x%08h test_done=0x%0h, RTC reset-value check not converged within %0dms",
                           RTC_SEG_BASE, test_done, DONE_TIMEOUT_NS/1_000_000))
                test_done = {NUM_BLK_TASKS{1'b1}};
            end
        join_any
        disable DONE_WAIT_FORK;
        `PHASE_DROP_OBJECTION             // 与开头 RAISE 配对
    endtask : m_run_phase

    //=========================================================================
    // 字节序转换：FPGA_RAM_MIRROR 原始字 -> CPU 可见小端寄存器字
    //   与 pcie_sequence.sv:589-594 的 big_d 分支**逐位等价**
    //=========================================================================
    function bit [31:0] raw2cpu(bit [31:0] raw);
        return {raw[7:0], raw[15:8], raw[23:16], raw[31:24]};
    endfunction : raw2cpu

    //=========================================================================
    // 带超时的单笔读（铁律 5）
    //   seq_h      : pcie_seq 句柄
    //   addr       : 全局地址（<段基址>+<块内偏移>）
    //   cpu_data   : 归一化到 CPU 小端视野的读值（timed_out=1 时无意义）
    //   timed_out  : 1 = 本笔读在 RD_TIMEOUT_NS 内未返回
    //   命名 fork + disable <label>：只中止本笔，不会波及 m_run_phase 里别的 fork
    //=========================================================================
    task rd_le_with_timeout(pcie_pkg::pcie_seq seq_h, bit [31:0] addr,
                            output bit [31:0] cpu_data, output bit timed_out);
        bit [31:0] raw;
        timed_out = 1'b0;
        raw       = 32'h0;
        fork : RD_FORK
            seq_h.PCIE_REG_RD(addr, raw);
            begin
                #(RD_TIMEOUT_NS * 1ns);
                timed_out = 1'b1;
            end
        join_any
        disable RD_FORK;
        cpu_data = raw2cpu(raw);
    endtask : rd_le_with_timeout

    //=========================================================================
    // 复位值断言（失败路径**双写**：① 含 *E 的文本；② `uvm_error）
    //   desc 用 $sformatf 带寄存器名 + 全局地址，保证全局唯一
    //=========================================================================
    task chk_reset_value(string reg_name, bit [31:0] addr, bit [31:0] cpu_data, bit [31:0] exp_rst);
        if (cpu_data !== exp_rst) begin
            // ① 打印含 *E 的文本（回归判定是 egrep '(\*E|\*F|\*e|ERROR:)'，`uvm_error 会被漏判）
            $display("chk_f *E RTC0_RST %s @0x%08h(seg 0x%08h + off 0x%02h): RD=0x%08h != RST=0x%08h | bits[7:0] RD=0x%02h EXP=0x%02h, bits[31:8] RD=0x%06h EXP=0x000000",
                     reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE,
                     cpu_data, exp_rst, cpu_data[7:0], exp_rst[7:0], cpu_data[31:8]);
            // ② 同时发 `uvm_error（UVM 汇总口径也能抓到）
            `uvm_error("RTC0_RST", $sformatf("%s @0x%08h(seg 0x%08h + off 0x%02h): RD=0x%08h != RST=0x%08h (bits[7:0] RD=0x%02h EXP=0x%02h)",
                       reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE, cpu_data, exp_rst, cpu_data[7:0], exp_rst[7:0]))
        end
        else begin
            $display("chk_s RTC0_RST %s @0x%08h(seg 0x%08h + off 0x%02h): RD=0x%08h == RST=0x%08h",
                     reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE, cpu_data, exp_rst);
            `uvm_info("RTC0_RST", $sformatf("%s @0x%08h(seg 0x%08h + off 0x%02h): RD=0x%08h == RST=0x%08h",
                      reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE, cpu_data, exp_rst), UVM_LOW)
        end
    endtask : chk_reset_value

    //=========================================================================
    // 复读一致性断言（相位 2）：全程未写任何寄存器，同一地址两次读必须逐位一致。
    //   作用：证明"通道/镜像返回的是稳定的寄存器内容"，而不是一次性的偶然值。
    //   失败路径同样双写。
    //=========================================================================
    task chk_repeat(string reg_name, bit [31:0] addr, bit [31:0] rd_first, bit [31:0] rd_again);
        if (rd_again !== rd_first) begin
            $display("chk_f *E RTC0_RST %s[re-read] @0x%08h(seg 0x%08h + off 0x%02h): 2nd=0x%08h != 1st=0x%08h (2nd read != 1st read, no write in between)",
                     reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE, rd_again, rd_first);
            `uvm_error("RTC0_RST", $sformatf("%s[re-read] @0x%08h(seg 0x%08h + off 0x%02h): 2nd=0x%08h != 1st=0x%08h",
                       reg_name, addr, RTC_SEG_BASE, addr - RTC_SEG_BASE, rd_again, rd_first))
        end
        else begin
            $display("chk_s RTC0_RST %s[re-read] @0x%08h: 2nd=0x%08h == 1st=0x%08h",
                     reg_name, addr, rd_again, rd_first);
        end
    endtask : chk_repeat

    //=========================================================================
    // 子任务：0x2000 段 RTC 控制器0 复位值检查（唯一并发子任务，pid 恒为 0）
    //   通道：PCIE（`PCIE_SQR + PCIE_REG_RD）。
    //   ⚠ 该段文档**没有**访问路径限制标注 → "没写限制 ≠ 没有限制"，选 PCIE 的依据与待确认项见头注释 T1。
    //   全程零写入：不调用 PCIE_REG_WR，也不需要 send_write/set_write 之类会写寄存器的封装。
    //=========================================================================
    task RTC_BLK_RESET_CHK(int pid);
        bit [31:0] rd_scale,  rd_filter,  rd_timeout;   // 相位 1：复位值首读
        bit [31:0] rd2_scale, rd2_filter, rd2_timeout;  // 相位 2：复读
        bit        to;
        pcie_pkg::pcie_seq m_pcie_seq = `CREATE_OBJ(pcie_pkg::pcie_seq, "m_pcie_seq")
        m_pcie_seq.set_sequencer(`PCIE_SQR);

        `uvm_info("RTC0_RST", $sformatf("BEGIN pid=%0d: seg 0x%08h ctrl0 i2c_scale/filter/timeout @ +0x00/+0x04/+0x08, EXP 0x%08h/0x%08h/0x%08h (doc L784/L794/L804)",
                  pid, RTC_SEG_BASE, EXP_RST_I2C_SCALE, EXP_RST_I2C_FILTER, EXP_RST_I2C_TIMEOUT), UVM_LOW)

        //---------------------------------------------------------------------
        // 相位 1：写任何寄存器之前，各读一次，与位定义表 Reset 比对
        //---------------------------------------------------------------------
        // 1) 0x2000 段 RTC I2C Master 控制器0 + 块内 0x00 = i2c_scale
        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_SCALE_ADDR, rd_scale, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_scale @0x%08h(seg 0x%08h + off 0x00): no response within %0dms",
                     RTC0_I2C_SCALE_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_scale @0x%08h(seg 0x%08h + off 0x00) no response within %0dms",
                       RTC0_I2C_SCALE_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;   // 逃生：不再发后续读，避免与超时中被中止的读抢 PCIe 原子锁
            return;
        end
        chk_reset_value("i2c_scale",   RTC0_I2C_SCALE_ADDR,   rd_scale,   EXP_RST_I2C_SCALE);

        // 2) 0x2000 段 RTC I2C Master 控制器0 + 块内 0x04 = i2c_filter
        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_FILTER_ADDR, rd_filter, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_filter @0x%08h(seg 0x%08h + off 0x04): no response within %0dms",
                     RTC0_I2C_FILTER_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_filter @0x%08h(seg 0x%08h + off 0x04) no response within %0dms",
                       RTC0_I2C_FILTER_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;
            return;
        end
        chk_reset_value("i2c_filter",  RTC0_I2C_FILTER_ADDR,  rd_filter,  EXP_RST_I2C_FILTER);

        // 3) 0x2000 段 RTC I2C Master 控制器0 + 块内 0x08 = i2c_timeout
        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_TIMEOUT_ADDR, rd_timeout, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_timeout @0x%08h(seg 0x%08h + off 0x08): no response within %0dms",
                     RTC0_I2C_TIMEOUT_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_timeout @0x%08h(seg 0x%08h + off 0x08) no response within %0dms",
                       RTC0_I2C_TIMEOUT_ADDR, RTC_SEG_BASE, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;
            return;
        end
        chk_reset_value("i2c_timeout", RTC0_I2C_TIMEOUT_ADDR, rd_timeout, EXP_RST_I2C_TIMEOUT);

        //---------------------------------------------------------------------
        // 相位 2：全程未写任何寄存器，复读三处，值必须与首读逐位一致（观测点 O2）
        //---------------------------------------------------------------------
        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_SCALE_ADDR, rd2_scale, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_scale[re-read] @0x%08h: no response within %0dms",
                     RTC0_I2C_SCALE_ADDR, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_scale[re-read] @0x%08h no response within %0dms",
                       RTC0_I2C_SCALE_ADDR, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;
            return;
        end
        chk_repeat("i2c_scale",   RTC0_I2C_SCALE_ADDR,   rd_scale,   rd2_scale);

        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_FILTER_ADDR, rd2_filter, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_filter[re-read] @0x%08h: no response within %0dms",
                     RTC0_I2C_FILTER_ADDR, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_filter[re-read] @0x%08h no response within %0dms",
                       RTC0_I2C_FILTER_ADDR, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;
            return;
        end
        chk_repeat("i2c_filter",  RTC0_I2C_FILTER_ADDR,  rd_filter,  rd2_filter);

        rd_le_with_timeout(m_pcie_seq, RTC0_I2C_TIMEOUT_ADDR, rd2_timeout, to);
        if (to) begin
            $display("chk_f *E RTC0_RST READ_TIMEOUT i2c_timeout[re-read] @0x%08h: no response within %0dms",
                     RTC0_I2C_TIMEOUT_ADDR, RD_TIMEOUT_NS/1_000_000);
            `uvm_error("RTC0_RST", $sformatf("READ_TIMEOUT: i2c_timeout[re-read] @0x%08h no response within %0dms",
                       RTC0_I2C_TIMEOUT_ADDR, RD_TIMEOUT_NS/1_000_000))
            test_done[pid] = 1'b1;
            return;
        end
        chk_repeat("i2c_timeout", RTC0_I2C_TIMEOUT_ADDR, rd_timeout, rd2_timeout);

        `uvm_info("RTC0_RST", $sformatf("END pid=%0d: 3 reset-value checks + 3 re-read consistency checks done", pid), UVM_LOW)
        test_done[pid] = 1'b1;   // 本子任务唯一收敛点（位宽与并发数一致）
    endtask : RTC_BLK_RESET_CHK

`DEF_TESTCASE_END

`endif
