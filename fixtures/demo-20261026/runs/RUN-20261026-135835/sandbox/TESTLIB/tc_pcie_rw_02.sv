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
`define I2C_SLV(PID) top_env0.i2c_slvs[PID]
//########################################
//TEST BEGIN 
//########################################
`DEF_TESTCASE_BEGIN(`TEST_NAME,base_test)

    bit test_done;
    function void m_build_phase(uvm_phase phase);
        top_cfg m_top_cfg = `CREATE_OBJ(top_cfg, "m_top_cfg")
        m_top_cfg.m_pcie_cfg.m_if_mode = pcie_pkg::AMD2P64;
        //m_top_cfg.m_pcie_cfg.m_if_mode = pcie_pkg::PANGO128;
        //m_top_cfg.m_pcie_cfg.m_disp_pcie_drv = 0;
        //m_top_cfg.m_pcie_cfg.m_disp_pcie_mon = 0;
        //m_top_cfg.m_pcie_cfg.pango128_cfg.s_tready_cfg = 1;
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
        `FORKJN_FOR_BLK(`I2C_SLV_NUM, I2C_SLV_RW)
        #10us;
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
        
        sys_reg_test(m_pcie_seq);
        for (int i=0;i<`FPGA_RTC_NUM;i++) begin
          rtc_reg_test(m_pcie_seq, i);
        end
        spi_reg_test(m_pcie_seq);
        
        for (int i=0;i<`DOME_PCA9548_NUM;i++) begin
          dom_reg_test(m_pcie_seq,i);
          dom_wr_chk(m_pcie_seq, i);
          
        end
        uart_reg_test(m_pcie_seq);
        pcie_reg_test(m_pcie_seq);
        
        test_done = 1;
    endtask

    task sys_reg_test(pcie_pkg::pcie_seq m_pcie_seq);
        bit[31:0] base_addr;
        
        base_addr = 32'h0;
        reg_field_test(m_pcie_seq, base_addr+'h00  ,32'h0000_0000, `REG_FPGA_VERSION, 1);
        reg_field_test(m_pcie_seq, base_addr+'h04  ,32'h0000_0000, `REG_FPGA_DATE, 1);
        reg_field_test(m_pcie_seq, base_addr+'h08  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h0c  ,32'h0000_0000, `REG_GOLDEN_FPGA_VERSION, 1);
        reg_field_test(m_pcie_seq, base_addr+'h10  ,32'h0000_0000, `REG_FPGA_MODULE, 1);
        reg_field_test(m_pcie_seq, base_addr+'h14  ,32'h0000_0000, 32'h0000_0000, 1);//bmc i2c only
        //reg_field_test(m_pcie_seq, base_addr+'h18  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only
        //reg_field_test(m_pcie_seq, base_addr+'h1c  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only h0000_1fff
        reg_field_test(m_pcie_seq, base_addr+'h20  ,32'h0000_0000, 32'h0000_0000, 1);//cpu i2c only
        //reg_field_test(m_pcie_seq, base_addr+'h24  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h28  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h2c  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h30  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h34  ,32'h0000_1fff, 32'h0000_0000, 0);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h38  ,32'h0000_ffff, 32'h0000_ffff, 1);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h3c  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h40  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h44  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //reg_field_test(m_pcie_seq, base_addr+'h48  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'h80  ,32'h0000_0001, 32'h0000_0000, 0);//cpu only?
        reg_field_test(m_pcie_seq, base_addr+'h84  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'h88  ,32'h0000_0003, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h90  ,32'h0000_0000, 32'h0000_0001, 1);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'h9c  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only
        reg_field_test(m_pcie_seq, base_addr+'hb8  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'hbc  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'hc0  ,32'h0000_0000, 32'h0000_0000, 1);//cpu only
        reg_field_test(m_pcie_seq, base_addr+'hc4  ,32'h0000_0000, 32'h0000_0001, 1);
        reg_field_test(m_pcie_seq, base_addr+'hc8  ,32'h0000_ffff, 32'h0000_ffff, 0);
        reg_field_test(m_pcie_seq, base_addr+'hf0  ,32'h0000_0000, 32'h000f_1110, 1);
        //reg_field_test(m_pcie_seq, base_addr+'hf4  ,32'h0000_0000, `REG_FPGA_GET, 1);
        //reg_field_test(m_pcie_seq, base_addr+'hf8  ,32'h0000_0000, `REG_FPGA_SEED, 1);
        //reg_field_test(m_pcie_seq, base_addr+'hfc  ,32'h0000_0000, `REG_FPGA_DATE1, 1);
        //for(int j=0;j<3;j++) begin
        //  reg_field_test(m_pcie_seq, base_addr+32'h68+j*4,32'h0000_0001,32'h0000_0001,0);//0x20~0x78
        //end
        //for(int j=0;j<5;j++) begin
        //  reg_field_test(m_pcie_seq, base_addr+32'ha0+j*4,32'h0000_0001,32'h0000_0001,0);//0x20~0x78
        //end
    endtask

    task rtc_reg_test(pcie_pkg::pcie_seq m_pcie_seq, int n=0);
        bit[31:0] base_addr;
        
        base_addr = `FPGA_OT9548_ADDR + n*`RTC_OFFSET;
        reg_field_test(m_pcie_seq, base_addr+32'h50,32'h0000_0003,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h00,32'hffff_ffff,32'h4e,0);
        reg_field_test(m_pcie_seq, base_addr+32'h04,32'hffff_ffff,32'h7c,0);
        reg_field_test(m_pcie_seq, base_addr+32'h08,32'hffff_ffff,32'h7c,0);//
        reg_field_test(m_pcie_seq, base_addr+32'h0c,32'h0000_0003,32'h00,0);//h0000_0003
        reg_field_test(m_pcie_seq, base_addr+32'h10,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h14,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h18,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h1c,32'hffff_ffff,32'h00,0);
        for(int j=0;j<4;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h20+j*4,32'hffff_ffff,32'h00,0);//0x20~0x78
        end
        reg_field_test(m_pcie_seq, base_addr+32'h30,32'hffff_ffff,32'h01,0);
        reg_field_test(m_pcie_seq, base_addr+32'h34,32'hffff_ffff,32'h00,0);
        
        reg_field_test(m_pcie_seq, base_addr+32'h3c,32'h0000_0000,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h44,32'h0000_0000,32'h03,1);
        reg_field_test(m_pcie_seq, base_addr+32'h48,32'h0000_0000,32'h00,1);
        reg_field_test(m_pcie_seq, base_addr+32'h4c,32'h0000_0000,32'h01,1);
        
        
        for(int j=0;j<64;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h100+j*4,32'hffff_ffff,32'h00,0);//0x68~0x78
        end
        reg_field_test(m_pcie_seq, base_addr+32'h78,32'h0000_0001,32'h01,0);
        reg_field_test(m_pcie_seq, base_addr+32'h7c,32'h0000_0001,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h38,32'h0000_0001,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h40,32'h0000_0000,32'h00,0);
    endtask

    task spi_reg_test(pcie_pkg::pcie_seq m_pcie_seq);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `UPT_SPI_ADDR;
        for(int j=0;j<64;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h00+j*4,32'hffff_ffff,32'h00,0);//0xa00~0xafc
        end
        reg_field_test(m_pcie_seq, base_addr+'h180  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h184  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h188  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h18c  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h190  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h194  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h198  ,32'hffff_ffff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h19c  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h1a0  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h1a4  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h1a8  ,32'h0000_0000, 32'h0000_0000, 1);
        reg_field_test(m_pcie_seq, base_addr+'h1ac  ,32'h0000_0000, 32'h0000_0000, 1);
    endtask

    task pcie_reg_test(pcie_pkg::pcie_seq m_pcie_seq);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `PCIE_BASE_ADDR;
        
        reg_field_test(m_pcie_seq, base_addr+'h00  ,32'h0000_0000, 32'h20121017, 1);
        reg_field_test(m_pcie_seq, base_addr+'h04  ,32'h0000_ffff, 32'h0000_0000, 0);
        begin : n6_obs_pcie_test_pcie_rw_02
          bit [31:0] n6_rdata;
          set_write(m_pcie_seq, base_addr+'h04, 32'h1234_5678);
          m_pcie_seq.PCIE_REG_RD(base_addr+'h04, n6_rdata);
          `uvm_info("N6_pcie_test_tc_pcie_rw_02", $sformatf("OK 0x0d00+0x04 pcie_test = 0x%08h", n6_rdata), UVM_LOW)
        end
        reg_field_test(m_pcie_seq, base_addr+'h08  ,32'hffff_ffff, 32'h0000_0000, 0);
        for(int j=0;j<4;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h10+j*4,32'h0000_0000,32'h00,1);//0xa00~0xafc
        end
        for(int j=0;j<8;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h70+j*4,32'h0000_0000,32'h00,1);//0xa00~0xafc
        end
    endtask

    task dom_reg_test(pcie_pkg::pcie_seq m_pcie_seq, int n=0);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `DOME_RTC_ADDR + n*`DOME_RTC_OFFSET;
        reg_field_test(m_pcie_seq, base_addr+32'h50,32'h0000_0003,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h00,32'hffff_ffff,32'h4e,0);
        reg_field_test(m_pcie_seq, base_addr+32'h04,32'hffff_ffff,32'h7c,0);
        reg_field_test(m_pcie_seq, base_addr+32'h08,32'hffff_ffff,32'h7c,0);//
        reg_field_test(m_pcie_seq, base_addr+32'h0c,32'h0000_0003,32'h00,0);//h0000_0003
        reg_field_test(m_pcie_seq, base_addr+32'h10,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h14,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h18,32'hffff_ffff,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h1c,32'hffff_ffff,32'h50,0);
        reg_field_test(m_pcie_seq, base_addr+32'h20,32'hffff_ffff,32'h00,0);
        for(int j=1;j<4;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h20+j*4,32'hffff_ffff,32'h00,0);//0x24~0x2c
        end
        reg_field_test(m_pcie_seq, base_addr+32'h30,32'hffff_ffff,32'h01,0);
        reg_field_test(m_pcie_seq, base_addr+32'h34,32'hffff_ffff,32'h80,0);
        
        reg_field_test(m_pcie_seq, base_addr+32'h3c,32'h0000_0000,32'h00,0);
        
        reg_field_test(m_pcie_seq, base_addr+32'h44,32'h0000_0000,32'h03,1);
        reg_field_test(m_pcie_seq, base_addr+32'h48,32'h0000_0000,32'h00,1);
        reg_field_test(m_pcie_seq, base_addr+32'h4c,32'h0000_0000,32'h01,1);
        
        for(int j=0;j<64;j++) begin
          reg_field_test(m_pcie_seq, base_addr+32'h100+j*4,32'hffff_ffff,32'h00,0);//0x100~0x1fc
        end
        reg_field_test(m_pcie_seq, base_addr+32'h78,32'h0000_0001,32'h01,0);
        reg_field_test(m_pcie_seq, base_addr+32'h7c,32'h0000_0001,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h38,32'h0000_0001,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h40,32'h0000_0000,32'h00,0);
        reg_field_test(m_pcie_seq, base_addr+32'h60,32'h0000_00f1,32'hf1,0);

        //base_addr = 32'h8000 + n*32'h100;
        //for(int j=0;j<8;j++) begin
        //  reg_field_test(m_pcie_seq, base_addr+32'h00+j*4,32'hffff_ffff,32'h00,0);//0x00~0x1c
        //end
        //
        //reg_field_test(m_pcie_seq, base_addr+32'h24,32'h0000_0000,32'h00,1);
        //
        //reg_field_test(m_pcie_seq, base_addr+32'h28,32'hffff_ffff,32'h00,0);
        //reg_field_test(m_pcie_seq, base_addr+32'h2c,32'hffff_ffff,{16'd50,13'd0,3'd7},0);
        //for(int j=0;j<6;j++) begin
        //  reg_field_test(m_pcie_seq, base_addr+32'h30+j*4,32'hffff_ffff,32'h00,0);//0x30~0x34
        //end
        //reg_field_test(m_pcie_seq, base_addr+32'h48,32'h0000_0001,32'h00,0);
        //reg_field_test(m_pcie_seq, base_addr+32'h4c,32'h0000_0001,32'h00,0);
        //reg_field_test(m_pcie_seq, base_addr+32'h20,32'hffff_ffff,32'h00,0);
    endtask

    task uart_reg_test(pcie_pkg::pcie_seq m_pcie_seq);//cpu pcie only
        bit[31:0] base_addr;
        
        base_addr = `UART_BASE_ADDR;
        
        reg_field_test(m_pcie_seq, base_addr+'h00  ,32'h0000_0000, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h04  ,32'h0000_000f, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h0c  ,32'h0000_00ff, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h10  ,32'h0000_001f, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h14  ,32'h0000_001f, 32'h0000_0000, 0);
        reg_field_test(m_pcie_seq, base_addr+'h1c  ,32'h0000_00ff, 32'h0000_0000, 0);
        set_write(m_pcie_seq, base_addr+'h0c, 32'h80);
        reg_field_test(m_pcie_seq, base_addr+'h00  ,32'h0000_00ff, 32'h0000_002d, 0);
        reg_field_test(m_pcie_seq, base_addr+'h04  ,32'h0000_00ff, 32'h0000_0003, 0);
        reg_field_test(m_pcie_seq, base_addr+'h08  ,32'h0000_00ff, 32'h0000_0000, 0);
        set_write(m_pcie_seq, base_addr+'h0c, 32'h00);
    endtask
    
    task dom_wr_chk(pcie_pkg::pcie_seq m_pcie_seq, int n);
      bit[31:0] base_addr, wdata, rdata;
      bit[31:0] exp_data[64*4];
      base_addr = `DOME_RTC_ADDR + `DOME_RTC_OFFSET * n;
      for (int i=0;i<64;i++) begin
        if (i != 3 && i<14) begin
          wdata = $urandom();
          set_write(m_pcie_seq,base_addr + i*4, wdata);
          exp_data[i] = wdata;
        end else if (i!=14 && i!=20 && i!=31) begin
          set_write(m_pcie_seq,base_addr + i*4, $urandom());
        end
      end

      for (int i=64;i<64*4;i++) begin
        wdata = $urandom();
        set_write(m_pcie_seq,base_addr + i*4, wdata);
        exp_data[i] = i < 64*2 ? wdata : 0;
      end
      
      for (int i=0;i<32;i++) begin
        if (i != 3 && i<14) begin
          m_pcie_seq.PCIE_REG_RDCHK(base_addr + i*4, exp_data[i],1);
        end else begin
          set_read(m_pcie_seq,base_addr + i*4, rdata);
        end
      end
      for (int i=32;i<64;i++) begin
        m_pcie_seq.PCIE_REG_RDCHK(base_addr + i*4, 0,1);
      end
      for (int i=64;i<64*4;i++) begin
        m_pcie_seq.PCIE_REG_RDCHK(base_addr + i*4, exp_data[i],1);
      end
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

    task reg_field_test( pcie_pkg::pcie_seq m_pcie_seq,
                           bit[31:0]  addr  ,
                           bit[31:0]  data_expmask,
                           bit[31:0]  initial_dat = '0, bit only_r=0); //rev bit is masked
      bit[31:0]  test_data ;                   
      bit[31:0]  data_rdexp;
   
      m_pcie_seq.PCIE_REG_RDCHK(addr,initial_dat,1);
      for (int i = 0; i < 5; i++) begin
        case (i)
          0: begin test_data  = 32'hffff_ffff;  end
          1: begin test_data  = 32'h5555_5555;  end
          2: begin test_data  = 32'haaaa_aaaa;  end
          3: begin test_data  = 32'h1234_5678;  end
          4: begin test_data  = 32'h0000_0000;  end
        endcase
        data_rdexp = only_r ? initial_dat : test_data & data_expmask; 
        set_write(m_pcie_seq, addr, test_data );//write interal rigister
        m_pcie_seq.PCIE_REG_RDCHK(addr, data_rdexp,1); //read interal rigister 
      end 
    endtask
    
    task I2C_SLV_RW(int pid);
        string ID = $sformatf("%0s_I2C_MST_RW", (pid == 0) ? "CPU": "BMC");
        `I2C_SLV(pid).startEnv();
    endtask

`DEF_TESTCASE_END

`endif
