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
        m_top_cfg.m_pcie_cfg.m_if_mode = (`PCIE_TYPE == 1) ? pcie_pkg::PANGO128 : pcie_pkg::AMD2P64;
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
                                                                 `CRG_SQR_PERIOD(2, 8  /*125MHz*/  ),
                                                                 `CRG_SQR_PERIOD(3, 6.41/*156MHz*/ ),
                                                                 `CRG_SQR_PERIOD(4, 20 /*50MHz*/   )
                                                                 };
            crg_pkg::ClockUtil::get_inst().foreach_clock_gen(sqr_period_q);
            crg_pkg::ClockUtil::get_inst().foreach_wait_reset_deassert(sqr_period_q,3);
        end 
        #1us;
        `PR_STR($sformatf("%s%s", "Start TestCase...>>>", {32{"@"}}))
        //#########################################################################################
        `FORKJN_FOR_BLK(1, PCIE_REG_RW)
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
        begin : n6_obs_pcie_test_pcie_rw_smoke
          bit [31:0] n6_rdata;
          m_pcie_seq.PCIE_REG_RD('hd04, n6_rdata);
          `uvm_info("N6_pcie_test_tc_pcie_rw_smoke", $sformatf("OK 0x0d00+0x04 pcie_test = 0x%08h", n6_rdata), UVM_LOW)
        end
        set_read(m_pcie_seq,'h4200, rdata);
        //for (int addr = 'h0000_0000; addr <= 'h0001_FFFF; addr=addr+4)begin 
        //    this.regAA_55_chk(m_pcie_seq, addr);
        //end 
        set_write(m_pcie_seq,'h808, 32'h81);
        set_write(m_pcie_seq,'h808, 32'h81);
        set_read(m_pcie_seq, 'h808, rdata);
        set_read(m_pcie_seq, 'h80c, rdata);
        rdata[7] = 1;
        set_write(m_pcie_seq,'h80c, rdata);
        set_read(m_pcie_seq, 'h808, rdata);
        
        set_read(m_pcie_seq,'h8c, rdata);
        set_write(m_pcie_seq,'h8c, 32'h12345678);
        set_read(m_pcie_seq,'h8c, rdata);
        
        set_read(m_pcie_seq,'h600, rdata);
        
        //set_read(m_pcie_seq,'hf0, rdata);
        //#1ms;
        //set_read(m_pcie_seq,'hf0, rdata);
        //#1ms;
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

`DEF_TESTCASE_END

`endif
