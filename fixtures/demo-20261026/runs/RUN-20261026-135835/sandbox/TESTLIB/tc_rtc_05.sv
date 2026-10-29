/*=============================================================================
// Ruijie IS PROVIDING THIS DESIGN, CODE, OR INFORMATION "AS IS"
// SOLELY FOR USE IN DEVELOPING PROGRAMS AND SOLUTIONS FOR
// Ruijie DEVICES.  BY PROVIDING THIS DESIGN, CODE, OR INFORMATION
// AS ONE POSSIBLE IMPLEMENTATION OF THIS FEATURE, APPLICATION
// OR STANDARD, Ruijie IS MAKING NO REPRESENTATION THAT THIS
// IMPLEMENTATION IS FREE FROM ANY CLAIMS OF INFRINGEMENT,
// AND YOU ARE RESPONSIBLE FOR OBTAINING ANY RIGHTS YOU MAY REQUIRE
// FOR YOUR IMPLEMENTATION.  Ruijie EXPRESSLY DISCLAIMS ANY
// WARRANTY WHATSOEVER WITH RESPECT TO THE ADEQUACY OF THE
// IMPLEMENTATION, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OR
// REPRESENTATIONS THAT THIS IMPLEMENTATION IS FREE FROM CLAIMS OF
// INFRINGEMENT, IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
// FOR A PARTICULAR PURPOSE.
// (c) Copyright 2025 Ruijie, Inc.
// All rights reserved.

//============================================================================
//     FileName: tc_pcie_rw.sv
//         Desc: 
//       Author: lixu
//        Email: lixu@ruijie.com.cn
//     HomePage: http://www.ruijie.com.cn/
//      Version: 1.0.0
//   LastChange: 2025-01-10 09:23:55
//      History:
//============================================================================*/
`ifndef TC_PCIE_RW__SV
`define TC_PCIE_RW__SV

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
`define CRG_SQR_PERIOD(PID, PERIOD) '{top_env0.m_top_vsqr.m_crg_sqrs[PID], PERIOD}
`define PCIE_SQR top_env0.m_top_vsqr.m_pcie_sqr
`define SPI_MST(PID) top_env0.spi_msts[PID]
`define SPI_SLV(PID) top_env0.spi_slvs[PID]
`define I2C_MST(PID) top_env0.i2c_msts[PID]
//########################################
//TEST BEGIN 
//########################################
`DEF_TESTCASE_BEGIN(`TEST_NAME,base_test)

    bit test_done;
    function void m_build_phase(uvm_phase phase);
        top_cfg m_top_cfg = `CREATE_OBJ(top_cfg, "m_top_cfg")
        m_top_cfg.m_pcie_cfg.m_if_mode = pcie_pkg::AMD2P64;
        uvm_config_db#(top_cfg)::set(this,"top_env0", "m_top_cfg", m_top_cfg);
    endfunction:m_build_phase
    
    task m_run_phase(uvm_phase phase);
        `PHASE_RAISE_OBJECTION
        begin:CLK_PROC 
            //#########################################################################################
            //CRG clock&rst
            //#########################################################################################
            crg_pkg::ClockUtil::sqr_period_t sqr_period_q[$] = '{
                                                                 `CRG_SQR_PERIOD(0, 40 /*25MHz*/   ), 
                                                                 `CRG_SQR_PERIOD(1, 16 /*62.5MHz*/ ), 
                                                                 `CRG_SQR_PERIOD(2, 8  /*125MHz*/  )
                                                                 };
            crg_pkg::ClockUtil::get_inst().foreach_clock_gen(sqr_period_q);
            crg_pkg::ClockUtil::get_inst().foreach_wait_reset_deassert(sqr_period_q);
        end 
        #10us;
        `PR_STR($sformatf("%s%s", "Start TestCase...>>>", {32{"@"}}))
        
        I2C_MST_RW(1);
        SPI_MST_RW(2);
        //#########################################################################################
        //`FORKJN_FOR_BLK(1, PCIE_REG_RW)
        PCIE_REG_RW(2);
        //#########################################################################################
        wait(test_done);
        `PHASE_DROP_OBJECTION
    endtask:m_run_phase

    //################################################################################
    //PCIE REG RW 
    //################################################################################
    task regAA_55_chk(pcie_pkg::pcie_seq m_pcie_seq, bit [31:0] addr);
        bit [31:0] rdata;
        m_pcie_seq.PCIE_REG_WR(addr, 32'hAAAA_AAAA);
        m_pcie_seq.PCIE_REG_RD(addr, rdata);
        if(rdata != 32'hAAAA_AAAA) begin
            `uvm_warning("WR_AA", $sformatf("ADDR:0x%0h Rdata:0x%0h != 32'hAAAA_AAAA", addr, rdata))
        end 
        m_pcie_seq.PCIE_REG_WR(addr, 32'h5555_5555);
        m_pcie_seq.PCIE_REG_RD(addr, rdata);
        if(rdata != 32'h5555_5555) begin 
            `uvm_warning("WR_55", $sformatf("ADDR:0x%0h Rdata:0x%0h != 32'h5555_5555", addr, rdata))
        end 
    endtask 

    task PCIE_REG_RW(int pid);
        bit [31:0] rdata;
        bit [31:0] addr;
        string ID = $sformatf("PCIE_REG_RW");
        pcie_pkg::pcie_seq m_pcie_seq = `CREATE_OBJ(pcie_pkg::pcie_seq, "m_pcie_seq")
        m_pcie_seq.set_sequencer(`PCIE_SQR);
        `uvm_info("SYSTEM_REG_TEST", "----------------", UVM_LOW)
        set_write(m_pcie_seq,'h8, 32'h12345678);
        m_pcie_seq.PCIE_REG_RDCHK('h8, 32'h12345678,1);
        set_write(m_pcie_seq,'h8, 32'hAAAA_AAAA);
        m_pcie_seq.PCIE_REG_RDCHK('h8, 32'hAAAA_AAAA);
        set_write(m_pcie_seq,'hd04, 32'h12345678);
        m_pcie_seq.PCIE_REG_RDCHK('hd04, 32'h0000_5678,1);
        begin : n6_obs_pcie_test_rtc_05
          bit [31:0] n6_rdata;
          m_pcie_seq.PCIE_REG_RD('hd04, n6_rdata);
          `uvm_info("N6_pcie_test_tc_rtc_05", $sformatf("OK 0x0d00+0x04 pcie_test = 0x%08h", n6_rdata), UVM_LOW)
        end
        
        for(int i = 0; i < `FPGA_RTC_NUM; i++) begin
          m_pcie_seq.PCIE_REG_RDCHK(`FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 32'h1,1);
          set_write(m_pcie_seq, `FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 0);//复位
          #10us;
          set_write(m_pcie_seq, `FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 1);///解复位
        end
        #20us;
        for(int i = 0; i < `FPGA_RTC_NUM; i++) begin
          `SPI_MST(pid).set_rdchk(`FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 32'h1);
          `SPI_MST(pid).set_write(`FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 0);//复位
          #10us;
          `SPI_MST(pid).set_write(`FPGA_OT9548_ADDR + i*32'h200 + 32'h78, 1);//解复位
        end
        test_done = 1;
    endtask
    task set_write(pcie_pkg::pcie_seq m_pcie_seq, bit [31:0] addr, bit [31:0] wdata);
      bit [31:0] wdata_tmp;
      
      wdata_tmp = {wdata[7:0],wdata[15:8],wdata[23:16],wdata[31:24]};
      m_pcie_seq.PCIE_REG_WR(addr, wdata_tmp);
    endtask
    task set_read(pcie_pkg::pcie_seq m_pcie_seq, bit [31:0] addr, output bit [31:0] rdata);
      bit [31:0] rdata_tmp;

      m_pcie_seq.PCIE_REG_RD(addr, rdata_tmp);
      rdata = {rdata_tmp[7:0],rdata_tmp[15:8],rdata_tmp[23:16],rdata_tmp[31:24]};
    endtask

    task SPI_MST_RW(int pid);
        string ID = $sformatf("%0s_SPI_MST_RW", (pid == 0) ? "CPLDA": 
                                                (pid == 1) ? "CPLDB": "BMC");
        int burstSize;
        int msb;
        bit[31:0] base_addr;
        packet dataIn, expData, dataOut;
        `SPI_MST(2).setTiming(160, 240, 240, 400);
        fork
          `SPI_MST(pid).startEnv();
        join_none
        `SPI_MST(pid).setMode(3);//SPI-MODE:3
        burstSize = 9;//burst bytes size
        msb = 1;//shift out bit first
        `SPI_MST(pid).setConfig(msb, burstSize);
        `SPI_MST(pid).set_write(32'h9c, {`FPGA_RTC_NUM{1'b1}});
        `SPI_MST(pid).set_rdchk(32'h9c, {`FPGA_RTC_NUM{1'b1}});
        pcie_pkg::spi_mt = `SPI_MST(pid);

    endtask

    task I2C_MST_RW(int pid);
        bit[31:0] base_addr,rdata;
        `I2C_MST(pid).setSpeedMode("FastPlus");
        `I2C_MST(pid).startEnv();
        `I2C_MST(pid).setRndDelay(0, 0);

        //`I2C_MST(pid).set_read(32'h14, rdata);
        //`I2C_MST(pid).set_rdchk(32'h14, 32'h1);
        //`I2C_MST(pid).set_write(32'h14, 32'h0);
        `I2C_MST(pid).set_rdchk(32'h14, 32'h0);
    endtask

`DEF_TESTCASE_END

`endif
