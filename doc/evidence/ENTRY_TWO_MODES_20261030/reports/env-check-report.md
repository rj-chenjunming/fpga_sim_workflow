# S0 环境准备记录

S0-a 完成不代表 S0 准出；S0-b 已全部完成（环境项目入口：rtl 项为「未替换」，其余五项 passed 且无漂移，可准出）。

- id: S0-20261030T084029183436-9a21225eae
- baseline: /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
- baseline_version: ENV@SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES+20261030T084029Z
- rtl_source: None
- work_env: /home/work/chenjunming/change-impact-loop/workspaces/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES-derived-20261030T084029183436Z
- created_at: 2026-10-30T08:40:29.183436+00:00
- status: prepared
- error: None

版本标识为操作者声明，未校验为 Git ref。

## 检查

- 选择性复制工作副本: passed
- RTL 未替换（环境项目入口）: skipped
- 非 RTL 初检一致: passed
- 接口核对与 TB 变更登记: passed
- 副本三库编译冒烟: passed
- 基线零写入见证: passed

## 环境项目入口派生（SPEC-05 §9）

- 入口：env_folder（RTL 根判定 = 未替换）
- 原始环境根（origin_env_root）：/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
- 默认冒烟用例：tc_bmc_i2c_01（记录落账，不从日志猜）
- 基线指纹是**过滤后**清单（baseline-before/after.json = copy_plan.copied），排除目录与软链不进判据但必须登记
- kb 随副本复制的**只有**数据子集：kb/baselines、kb/index、kb/conflicts、kb/adjudication（其余 kb 条目不复制，见下方跳过清单）
- 错目录告警（只告警不拦截）：{}
- 排除整目录：.git、COV、LOG、RUNS、SIMLIB_RUN、WAVE、kb/runs、loop
- 跳过条目（14，软链不复制不跟随）：
  - RTL/.git（skip_dir_name）
  - RTL/RTL_COMMON/.git（skip_dir_name）
  - doc/spec/evidence/loop_rehearsal/mock/__pycache__（skip_dir_name）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/PKG（symlink → /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/PKG）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/RTL（symlink → /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/RTL）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/TB（symlink → /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/TB）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/TESTLIB（symlink → /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/TESTLIB）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/doc（symlink → /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/doc）
  - doc/spec/evidence/loop_rehearsal/verify/sandbox/kb/tools/__pycache__（skip_dir_name）
  - kb/.gitignore（kb_non_data）
  - kb/FIXTURE_IDENTITY.md（kb_non_data）
  - kb/README.md（kb_non_data）
  - kb/schema（kb_non_data）
  - kb/tools（kb_non_data）
- RTL：**未替换**（环境项目入口）——环境项目入口：未提供新版 RTL，副本 RTL 与源环境逐文件一致（copy 判据已覆盖），不做替换

## 指纹文件

完整清单位于本记录目录：baseline-before.json、baseline-after.json、rtl-source.json、work-after*.json（成功后，每次授权落盘追加一份）。

## 阻断项（按当前状态计算）

- 无（环境项目入口：rtl 为「未替换」，其余五项全部 passed，且无漂移/核验错误）

## TB 变更登记表

接口差异表为空；**空表不代表无接口变化**，须以本次派生的输入 md5 为准。

- 派生证据：{"baseline_modules": 205, "baseline_rtl_md5": "37b3d5b3fcb3a445dbe102034fd54901c67a0ac9e34a4c20eebfef98639816d0", "baseline_unparsed": ["FD", "cold_warm_reset_cnt", "dcb_mag", "distribute", "fifo_pre", "gtp_async_fifo_18k", "gtp_async_fifo_36k", "gtp_async_fifo_distributed", "gtp_sdpram_18k", "gtp_sdpram_36k", "gtp_sdpram_distributed", "gtp_sync_fifo_18k", "gtp_sync_fifo_36k", "gtp_sync_fifo_distributed", "i2c_slave", "ipal_cram_frame_fifo_32_101", "ips2l_seu_crc32x37_v1_0", "ips2l_seu_crc_v1_0", "ips2l_seu_init_crc_ram", "pcie_arbit", "pcie_controller", "pcie_register", "pds_asyn_block_fwft_fifo", "pds_asyn_distributed_fwft_fifo", "pds_asyn_distributed_std_fifo", "pds_distributed_simple_dual_ram", "pds_distributed_single_ram", "pds_drm_dual_ram", "pds_drm_simple_dual_ram", "pds_drm_single_ram", "pds_syn_block_fwft_fifo", "pds_syn_block_std_fifo", "pds_syn_distributed_fwft_fifo", "pds_syn_distributed_std_fifo", "qsfp_reg_dcb", "ramd_16384d_9w", "ramd_256d_8w", "ramd_8192d_8w", "ramt1_512d_32w", "ramt_1024d_32w", "rcv_data_ram", "rcv_header_ram", "retry_data_ram", "s_axi_1024x129_ram", "s_axi_128x129_ram", "s_axi_512x129_ram", "spi_ctrl", "up_cpl_mag", "upt_bram_64d64w", "upt_ctrl", "upt_top", "user_sdpram_pango_dram"], "candidate_modules": 205, "candidate_rtl_md5": "37b3d5b3fcb3a445dbe102034fd54901c67a0ac9e34a4c20eebfef98639816d0", "candidate_unparsed": ["FD", "cold_warm_reset_cnt", "dcb_mag", "distribute", "fifo_pre", "gtp_async_fifo_18k", "gtp_async_fifo_36k", "gtp_async_fifo_distributed", "gtp_sdpram_18k", "gtp_sdpram_36k", "gtp_sdpram_distributed", "gtp_sync_fifo_18k", "gtp_sync_fifo_36k", "gtp_sync_fifo_distributed", "i2c_slave", "ipal_cram_frame_fifo_32_101", "ips2l_seu_crc32x37_v1_0", "ips2l_seu_crc_v1_0", "ips2l_seu_init_crc_ram", "pcie_arbit", "pcie_controller", "pcie_register", "pds_asyn_block_fwft_fifo", "pds_asyn_distributed_fwft_fifo", "pds_asyn_distributed_std_fifo", "pds_distributed_simple_dual_ram", "pds_distributed_single_ram", "pds_drm_dual_ram", "pds_drm_simple_dual_ram", "pds_drm_single_ram", "pds_syn_block_fwft_fifo", "pds_syn_block_std_fifo", "pds_syn_distributed_fwft_fifo", "pds_syn_distributed_std_fifo", "qsfp_reg_dcb", "ramd_16384d_9w", "ramd_256d_8w", "ramd_8192d_8w", "ramt1_512d_32w", "ramt_1024d_32w", "rcv_data_ram", "rcv_header_ram", "retry_data_ram", "s_axi_1024x129_ram", "s_axi_128x129_ram", "s_axi_512x129_ram", "spi_ctrl", "up_cpl_mag", "upt_bram_64d64w", "upt_ctrl", "upt_top", "user_sdpram_pango_dram"], "confirmed": [], "defines": ["SIM", "SIMULATION", "VENDOR_PANGO"], "derive_md5": "c2592ef40077eef28b65db18c70fff1a83878f5c1098bf2b718e04800c31c012", "hunks": 0, "rejected": [], "tb_md5_baseline": "39e95ecd73604ef672f9644dc61fc06d", "tb_md5_work": "39e95ecd73604ef672f9644dc61fc06d", "tb_top": "TB/tbtop.sv"}
- 派生结论：passed（派生成立、差异均已处置、副本 TB 与已确认内容一致）

## 三库冒烟

- 状态：passed（已执行且无新增告警）
- candidate：rc=0 errors=0 warnings=17
  - 命令：bash /home/work/chenjunming/change-impact-loop/kb/tools/run_guarded.sh --mode compile-only -c tc_bmc_i2c_01 --sandbox-root /home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/candidate/sandbox --run S0-20261030T084029183436-9a21225eae-s0smoke-candidate --evidence-dir /home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/candidate/evidence
  - 日志：/home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/candidate/evidence/20261030-164041_tc_bmc_i2c_01_1_c_rtl.log、/home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/candidate/evidence/20261030-164041_tc_bmc_i2c_01_1_c_tb.log
- baseline：rc=0 errors=0 warnings=17
  - 命令：bash /home/work/chenjunming/change-impact-loop/kb/tools/run_guarded.sh --mode compile-only -c tc_bmc_i2c_01 --sandbox-root /home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/baseline/sandbox --run S0-20261030T084029183436-9a21225eae-s0smoke-baseline --evidence-dir /home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/baseline/evidence
  - 日志：/home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/baseline/evidence/20261030-164044_tc_bmc_i2c_01_1_c_rtl.log、/home/work/chenjunming/change-impact-loop/.lead-e2e-state/s0/S0-20261030T084029183436-9a21225eae/s0b/smoke/baseline/evidence/20261030-164044_tc_bmc_i2c_01_1_c_tb.log
- warning 增量：{"added": [], "count_increase": [], "needs_evaluation": [], "removed": []}