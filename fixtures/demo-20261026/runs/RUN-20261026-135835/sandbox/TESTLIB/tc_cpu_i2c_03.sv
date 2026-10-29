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
// (c) Copyright 2024 Ruijie, Inc.
// All rights reserved.

//============================================================================
//     FileName: tc_regs_test.sv
//         Desc: 
//       Author: lixu
//        Email: lixu@ruijie.com.cn
//     HomePage: http://www.ruijie.com.cn/
//      Version: 1.0.0
//   LastChange: 2024-10-15 10:06:54
//      History:
//============================================================================*/
`ifndef TC_REGS_TEST__SV
`define TC_REGS_TEST__SV

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
        #1us;
        `PR_STR($sformatf("%s%s", "Start TestCase...>>>", {32{"@"}}))
        //#########################################################################################
        //`FORKJN_FOR_BLK(1, PCIE_REG_RW)
        //`FORKJN_FOR_BLK(`SPI_MST_NUM, SPI_MST_RW)
        //`FORKJN_FOR_BLK(`SPI_SLV_NUM, SPI_SLV_RW)
        //`FORKJN_FOR_BLK(`I2C_MST_NUM, I2C_MST_RW)
        //`SPI_MST(2).setTiming(24, 36, 36, 60);
        //PCIE_REG_RW(0);
        #10us;
        I2C_MST_RW(0);
        //SPI_MST_RW(2);
        test_done=1;
        #10us;
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
        //m_pcie_seq.PCIE_REG_WR(32'h14, 32'h0000_0001);
        //m_pcie_seq.PCIE_REG_RD(32'h14, rdata);
        //for (int addr = 'h0000_0000; addr <= 'h0001_FFFF; addr=addr+4)begin 
        //    regAA_55_chk(m_pcie_seq, addr);
        //end 
        //test_done = 1;
    endtask
    //################################################################################
    //SPI MST RW 
    //################################################################################
    typedef bit [7:0] bit8;
    typedef bit8 packet[$];
    task SPI_MST_RW(int pid);
        string ID = $sformatf("%0s_SPI_MST_RW", (pid == 0) ? "CPLDA": 
                                                (pid == 1) ? "CPLDB": "BMC");
        int burstSize;
        int msb;
        packet dataIn, expData, dataOut;
        `SPI_MST(pid).startEnv();
        `SPI_MST(pid).setMode(3);//SPI-MODE:3
        burstSize = 9;//burst bytes size
        msb = 1;//shift out bit first
        `SPI_MST(pid).setConfig(msb, burstSize);
        for(int i = 0; i < 1; ++i) begin
            bit [31:0] addr = 32'h4;
            bit [31:0] data = 32'hA;
            bit [31:0] chk_data;
            // Master writes to the slave.
            dataIn.push_back(8'h2);//WRITE
            dataIn = {dataIn, bit8_que_t'(addr)};
            dataIn = {dataIn, bit8_que_t'(data)};
            `SPI_MST(pid).readWriteData(0, dataIn, dataOut);
            // Master reads from the slave.
            dataIn.delete();
            dataIn.push_back(8'h3);//READ
            dataIn = {dataIn, bit8_que_t'(addr)};
            dataIn = {dataIn, 8'hFF, 8'hFF, 8'hFF, 8'hFF};
            `SPI_MST(pid).readWriteData(0, dataIn, dataOut, dataIn.size());
            chk_data = {dataOut[5], dataOut[6], dataOut[7], dataOut[8]};
            if(data != chk_data) begin
                `uvm_error(ID, $sformatf("*E, WR_DATA:0x%0h != RD_DATA:0x%0h.", data, chk_data))
            end
            else begin
                `uvm_info(ID, $sformatf("WR_DATA:0x%0h == RD_DATA:0x%0h.", data, chk_data), UVM_LOW)
            end 
        end 
    endtask
    //################################################################################
    //SPI SLV RW 
    //################################################################################
    event spi_slv_done_e[`SPI_SLV_NUM];
    task SPI_SLV_RW(int pid);
        string ID = $sformatf("%0s_SPI_SLV_RW", (pid == 0) ? "SPI-FLASH": 
                                                (pid == 1) ? "CLOCK-BUFFER": "???");
        bit [15:0] spi_mem[bit[15:0]];
        int burstSize;
        int msb;
        packet dataIn, expData, dataOut;
        `SPI_SLV(pid).startEnv();
        `SPI_SLV(pid).setMode(3);//SPI-MODE:3
        burstSize = 1+2+2;//burst byte size
        msb = 1;
        `SPI_SLV(pid).setConfig(msb, burstSize);
        forever begin 
            @(spi_slv_done_e[pid]);
            `SPI_SLV(pid).getData(dataOut, burstSize);
            `uvm_info(ID, $sformatf("RD_DATA:%p.", dataOut), UVM_LOW)
            case(dataOut[0])
                'h2:begin:WR 
                    spi_mem[{dataOut[1], dataOut[2]}] = {dataOut[3], dataOut[4]};
                end 
                'h3:begin:RD
                    dataIn.push_back(spi_mem[{dataOut[1], dataOut[2]}][15:8]);
                    dataIn.push_back(spi_mem[{dataOut[1], dataOut[2]}][ 7:0]);
                    `SPI_SLV(pid).putData(dataIn);
                end
                default:begin
                end 
            endcase
        end 
    endtask
    //################################################################################
    //I2C MST RW 
    //################################################################################
    task I2C_MST_RW(int pid);
        string ID = $sformatf("%0s_I2C_MST_RW", (pid == 0) ? "CPU": "BMC");
        bit [31:0] rdata,wdata;
        Packet pkt;
        packet dataIn, expData, dataOut;
        pkt = new();
        `I2C_MST(pid).setSpeedMode("FastPlus");
        `I2C_MST(pid).startEnv();
        `I2C_MST(pid).setRndDelay(0, 0);

        `I2C_MST(pid).reg_field_test(32'h20  ,32'h0000_0001, 32'h0000_0000, 0);
        `I2C_MST(pid).set_write(32'h20, 32'h1);
        
        sys_reg_test(pid);
        rtc_reg_test(pid);
        //spi_reg_test(pid);
        //pcie_reg_test(pid);
        dom_reg_test(pid);
        //uart_reg_test(pid);

    endtask
    
    task sys_reg_test(int pid);
        bit[31:0] base_addr;
        
        base_addr = 32'h0;
        `I2C_MST(pid).reg_field_test(base_addr+'h00  ,32'h0000_0000, `REG_FPGA_VERSION, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_0000, `REG_FPGA_DATE, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h08  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h0c  ,32'h0000_0000, `REG_GOLDEN_FPGA_VERSION, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h10  ,32'h0000_0000, `REG_FPGA_MODULE, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h14  ,32'h0000_0000, 32'h0000_0000, 1);//bmc i2c only
        //`I2C_MST(pid).reg_field_test(base_addr+'h18  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only
        `I2C_MST(pid).reg_field_test(base_addr+'h1c  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only h0000_1fff
        
        //`I2C_MST(pid).reg_field_test(base_addr+'h24  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h28  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h2c  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h30  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h34  ,32'h0000_1fff, 32'h0000_0000, 0);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h38  ,32'h0000_ffff, 32'h0000_ffff, 1);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h3c  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h40  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h44  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        //`I2C_MST(pid).reg_field_test(base_addr+'h48  ,32'hffff_ffff, 32'hffff_ffff, 1);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'h80  ,32'h0000_0001, 32'h0000_0000, 0);//cpu only?
        `I2C_MST(pid).reg_field_test(base_addr+'h84  ,32'h0000_0001, 32'h0000_0000, 0);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'h88  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h90  ,32'h0000_0000, 32'h0000_0001, 1);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'h9c  ,32'h0000_0000, 32'h0000_0000, 1);//bmc only
        `I2C_MST(pid).reg_field_test(base_addr+'hb8  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'hbc  ,32'hffff_ffff, 32'h0000_0000, 0);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'hc0  ,32'h0000_0000, 32'h0000_0000, 1);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'hc4  ,32'h0000_0000, 32'h0000_0001, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'hc8  ,32'h0000_ffff, 32'h0000_ffff, 0);//cpu only
        `I2C_MST(pid).reg_field_test(base_addr+'hf0  ,32'h0000_0000, 32'h000f_2221, 1);
        //`I2C_MST(pid).reg_field_test(base_addr+'hf4  ,32'h0000_0000, `REG_FPGA_GET, 1);
        //`I2C_MST(pid).reg_field_test(base_addr+'hf8  ,32'h0000_0000, `REG_FPGA_SEED, 1);
        //`I2C_MST(pid).reg_field_test(base_addr+'hfc  ,32'h0000_0000, `REG_FPGA_DATE1, 1);
        //for(int j=0;j<3;j++) begin
        //  `I2C_MST(pid).reg_field_test(base_addr+32'h68+j*4,32'h0000_0001,32'h0000_0001,0);//0x68~0x70
        //end
        //for(int j=0;j<5;j++) begin
        //  `I2C_MST(pid).reg_field_test(base_addr+32'ha0+j*4,32'h0000_0001,32'h0000_0001,0);//0x20~0x78
        //end
    endtask
    
    task rtc_reg_test(int pid, int n=0);
        bit[31:0] base_addr;
        
        base_addr = `FPGA_OT9548_ADDR + n*`RTC_OFFSET;
        `I2C_MST(pid).reg_field_test(base_addr+32'h50,32'h0000_0003,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h00,32'hffff_ffff,32'h4e,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h04,32'hffff_ffff,32'h7c,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h08,32'hffff_ffff,32'h7c,0);//
        `I2C_MST(pid).reg_field_test(base_addr+32'h0c,32'h0000_0003,32'h00,0);//h0000_0003
        `I2C_MST(pid).reg_field_test(base_addr+32'h10,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h14,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h18,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h1c,32'hffff_ffff,32'h00,0);
        for(int j=0;j<4;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h20+j*4,32'hffff_ffff,32'h00,0);//0x20~0x78
        end
        `I2C_MST(pid).reg_field_test(base_addr+32'h30,32'hffff_ffff,32'h01,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h34,32'hffff_ffff,32'h00,0);
        
        `I2C_MST(pid).reg_field_test(base_addr+32'h3c,32'h0000_0000,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h44,32'h0000_0000,32'h03,1);
        `I2C_MST(pid).reg_field_test(base_addr+32'h48,32'h0000_0000,32'h00,1);
        `I2C_MST(pid).reg_field_test(base_addr+32'h4c,32'h0000_0000,32'h01,1);
        
        
        for(int j=0;j<64;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h100+j*4,32'hffff_ffff,32'h00,0);//0x68~0x78
        end
        `I2C_MST(pid).reg_field_test(base_addr+32'h78,32'h0000_0001,32'h01,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h7c,32'h0000_0001,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h38,32'h0000_0001,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h40,32'h0000_0000,32'h00,0);
    endtask

    task spi_reg_test(int pid);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `UPT_SPI_ADDR;
        for(int j=0;j<64;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h00+j*4,32'hffff_ffff,32'h00,0);//0xa00~0xafc
        end
        `I2C_MST(pid).reg_field_test(base_addr+'h180  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h184  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h188  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h18c  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h190  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h194  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h198  ,32'hffff_ffff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h19c  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h1a0  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h1a4  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h1a8  ,32'h0000_0000, 32'h0000_0000, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h1ac  ,32'h0000_0000, 32'h0000_0000, 1);
    endtask

    task pcie_reg_test(int pid);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `PCIE_BASE_ADDR;
        
        `I2C_MST(pid).reg_field_test(base_addr+'h00  ,32'h0000_0000, 32'h20121017, 1);
        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_ffff, 32'h0000_0000, 0);
        begin : n6_obs_pcie_test_cpu_i2c_03
          bit [31:0] n6_rdata;
          `I2C_MST(pid).set_write(base_addr+'h04, 32'h1234_5678);
          `I2C_MST(pid).set_read(base_addr+'h04, n6_rdata);
          `uvm_info("N6_pcie_test_tc_cpu_i2c_03", $sformatf("OK 0x0d00+0x04 pcie_test = 0x%08h", n6_rdata), UVM_LOW)
        end
        `I2C_MST(pid).reg_field_test(base_addr+'h08  ,32'hffff_ffff, 32'h0000_0000, 0);
        for(int j=0;j<4;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h10+j*4,32'h0000_0000,32'h00,1);//0xa00~0xafc
        end
        for(int j=0;j<8;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h70+j*4,32'h0000_0000,32'h00,1);//0xa00~0xafc
        end
    endtask
    
    task dom_reg_test(int pid, int n=0);//cpu only
        bit[31:0] base_addr;
        
        base_addr = `DOME_RTC_ADDR + n*`DOME_RTC_OFFSET;
        `I2C_MST(pid).reg_field_test(base_addr+32'h50,32'h0000_0003,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h00,32'hffff_ffff,32'h4e,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h04,32'hffff_ffff,32'h7c,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h08,32'hffff_ffff,32'h7c,0);//
        `I2C_MST(pid).reg_field_test(base_addr+32'h0c,32'h0000_0003,32'h00,0);//h0000_0003
        `I2C_MST(pid).reg_field_test(base_addr+32'h10,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h14,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h18,32'hffff_ffff,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h1c,32'hffff_ffff,32'h50,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h20,32'hffff_ffff,32'h00,0);
        for(int j=1;j<4;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h20+j*4,32'hffff_ffff,32'h00,0);//0x24~0x2c
        end
        `I2C_MST(pid).reg_field_test(base_addr+32'h30,32'hffff_ffff,32'h01,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h34,32'hffff_ffff,32'h80,0);
        
        `I2C_MST(pid).reg_field_test(base_addr+32'h3c,32'h0000_0000,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h44,32'h0000_0000,32'h03,1);
        `I2C_MST(pid).reg_field_test(base_addr+32'h48,32'h0000_0000,32'h00,1);
        `I2C_MST(pid).reg_field_test(base_addr+32'h4c,32'h0000_0000,32'h01,1);
        
        for(int j=0;j<64;j++) begin
          `I2C_MST(pid).reg_field_test(base_addr+32'h100+j*4,32'hffff_ffff,32'h00,0);//0x100~0x1fc
        end
        `I2C_MST(pid).reg_field_test(base_addr+32'h78,32'h0000_0001,32'h01,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h7c,32'h0000_0001,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h38,32'h0000_0001,32'h00,0);
        `I2C_MST(pid).reg_field_test(base_addr+32'h40,32'h0000_0000,32'h00,0);
        //base_addr = 32'h8000 + n*32'h100;
        //for(int j=0;j<8;j++) begin
        //  `I2C_MST(pid).reg_field_test(base_addr+32'h00+j*4,32'hffff_ffff,32'h00,0);//0x00~0x1c
        //end
        //
        //`I2C_MST(pid).reg_field_test(base_addr+32'h24,32'h0000_0000,32'h00,1);
        //`I2C_MST(pid).reg_field_test(base_addr+32'h20,32'hffff_ffff,32'h00,0);
        //`I2C_MST(pid).reg_field_test(base_addr+32'h28,32'hffff_ffff,32'h00,0);
        //`I2C_MST(pid).reg_field_test(base_addr+32'h2c,32'hffff_ffff,{16'd50,13'd0,3'd7},0);
        //for(int j=0;j<6;j++) begin
        //  `I2C_MST(pid).reg_field_test(base_addr+32'h30+j*4,32'h0000_0000,32'h00,0);//0x00~0x1c
        //end
        //`I2C_MST(pid).reg_field_test(base_addr+32'h48,32'h0000_0001,32'h00,0);
        //`I2C_MST(pid).reg_field_test(base_addr+32'h4c,32'h0000_0003,32'h00,0);
    endtask
    
    task uart_reg_test(int pid);//cpu pcie only
        bit[31:0] base_addr;
        
        base_addr = `UART_BASE_ADDR;
        
        `I2C_MST(pid).reg_field_test(base_addr+'h00  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h0c  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h10  ,32'h0000_0010, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h14  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h18  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h1c  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).set_write(base_addr+'h0c, 32'h80);
        `I2C_MST(pid).reg_field_test(base_addr+'h00  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h04  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).reg_field_test(base_addr+'h08  ,32'h0000_00ff, 32'h0000_0000, 0);
        `I2C_MST(pid).set_write(base_addr+'h0c, 32'h00);
    endtask

`DEF_TESTCASE_END

`endif
