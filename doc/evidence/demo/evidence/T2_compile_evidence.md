# T2 编译证据（卡点 B · 只编译）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **本文件不含任何功能判定**：本次只编译，未跑仿真、未看断言、未判用例对错（那是 checker 的职责）。

---

## 1 证据字段（task-2 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261013-T2-01` |
| 用例 | `doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` |
| 用例 md5 | `da044d2ba922ded6081e3abe7d52aeaa` |
| 用例字节 / 行数 | `27459` 字节 / `393` 行 |
| md5 与 Lead 冻结值比对 | **一致** ✅（Lead 冻结 `da044d2ba922ded6081e3abe7d52aeaa` / 27459 / 393） |
| md5 跑后复查 | `da044d2ba922ded6081e3abe7d52aeaa`（与跑前相同 ⇒ 无移动靶）✅ |
| `compile_only.sh` md5（新） | `4d7cf96c2e3acde11c46a5b15632bfa5` |
| `run_local.sh` md5（F2 自检对照） | `162260235efa6f62023f97e11099b234` |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_rtc_blk_reset_chk_01 -f doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` |
| 段① rc | **0** |
| 段② rc | **0** |
| 段① 耗时 | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 1.36s, CPU time: 1.32s`） |
| 段② 耗时 | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 0.86s, CPU time: 0.86s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_rtl.log` —— `86144` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_tb.log` —— `29022` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/t2_compile_stdout.log` —— `114284` 字节 / `2105` 行 |
| 首个 error 行 | **N/A（0 error，无失败行）** |
| 编译库 | `SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl`（3.6M）、`.../tb`（1.2M） |

### 判定依据（task-2 口径，逐条命中）

- PASS ⟺ 两段 `uvlan` 均 rc=0 **且** `_c_rtl.log`/`_c_tb.log` 无 ERROR 级诊断
  - 段① rc=0 ✅；段② rc=0 ✅
  - `_c_rtl.log`：`Compilation: 0 error(s), 13 warning(s)`；`Error-\d+` 计数 **0**；`^ERROR|^Error` 计数 **0** ✅
  - `_c_tb.log`：`Compilation: 0 error(s), 4 warning(s)`；`Error-\d+` 计数 **0**；`^ERROR|^Error` 计数 **0** ✅
- ⇒ **编译通过（卡点 B）**

### 脚本自发结论行（原文引述，非功能判定）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv  (md5 da044d2ba922ded6081e3abe7d52aeaa)
库        : SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_{rtl,tb}.log
```

### 真编证据（排除"跳过编译"的路径）

```
SIMLIB_RUN/log/..._c_rtl.log:1293:Saving Verilog Library 'rtl' to Path './SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl' Done
SIMLIB_RUN/log/..._c_tb.log:793 :Saving Verilog Library 'tb'  to Path './SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/tb'  Done
rtl 段 Analyzing Verilog file 行数: 256
tb  段 Analyzing Verilog file 行数: 2（tbtop + 目标用例，其余为 include）
库内可见 treeir.db / macro_file.json / unified_option.txt（rtl/tb 两套）
```

## 2 跑前快照（串行 + 快照纪律）

```
diff uvs.setup doc/_run_artifacts/uvs.setup.orig   → rc=0（一致）
md5sum uvs.setup                                   → a80f7b6ca48a7961a107bbe871af761d
md5sum doc/_run_artifacts/uvs.setup.orig           → a80f7b6ca48a7961a107bbe871af761d
ps -ef | grep -E "uvlan|uvs |run_local|compile_only" | grep -v grep
                                                   → 无输出（rc=1）⇒ 空闲
ls -ld SIMLIB_RUN/.compile_only.lock               → 不存在（无遗留锁）
VENDOR 宏 all_define.txt:3                         → -define VENDOR_PANGO
```

## 3 跑后还原确认（E4 + F1）

```
diff uvs.setup doc/_run_artifacts/uvs.setup.orig   → rc=0（已还原）✅
md5sum uvs.setup                                   → a80f7b6ca48a7961a107bbe871af761d （== 跑前 == 夹具）
夹具权限/大小                                      → 444 / 1071 字节 / mtime 2026-10-10 10:58:47
ls -ld SIMLIB_RUN/.compile_only.lock               → 不存在 ⇒ F4 锁已释放 ✅
ps -ef | grep ...（跑后）                          → 无输出（rc=1）⇒ 空闲 ✅
```

## 4 本轮机制观测点（Lead 指定要看的四条）

| 机制 | 观测结果 |
|---|---|
| **F2 选项自检** | ✅ **通过**。stdout 第 7 行：`[info] 选项自检通过：tb_dir/all_opt 与 run_local.sh 逐字节一致`（未触发 exit 12） |
| **F1 夹具/还原断言** | 未出现 `[WARN] uvs.setup 还原到的是夹具值，与本轮开始前不同`；也未出现 `[info] 已创建 uvs.setup 夹具` ⇒ 夹具早已存在，且**本轮跑前值与夹具值本来就相等**（`a80f7b…`），还原后 md5 断言通过。**照实记录：无 WARN，无需解释的偏差** |
| **F4 并发锁** | ✅ 正常获取（`mkdir SIMLIB_RUN/.compile_only.lock` 成功，未 exit 3）、正常释放（跑后目录已消失）。无遗留锁，无需手工 `rmdir` |
| **F3 `-k` 修复** | 本轮**按 Lead 建议未加 `-k`**（干净全编，保证证据可复现）。故未行使复用路径；`-k` 代码路径本身本轮未被覆盖验证 —— **如需验证请视为独立待办** |

### 未加 `-k` 的取舍留痕（Lead 请我决定并留痕）

选择**不加 `-k`**，理由：
1. 目标路径 `SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl` 跑前不存在，`-k` 无收益；
2. 若为省时而手工把 `tc_dom_polling_new_01_1/rtl` 复制进来再 `-k`，属**偏离 task-2 命令原文**的动作，会给"证据可复现命令"打折扣；
3. 实测总耗时仅 **≈2 s**（远低于预期的 4 min），复用节省无意义 ⇒ 选择可复现性更高的干净全编。

## 5 成本观测（如实记录，供 Lead/guardian 复核）

- 实测：段① `耗时 1s`、段② `耗时 1s`，全程墙钟 **≈2 s**，**远快于**角色定义 §1 记载的"编译约 4 分钟（RTL 3 min + TB 1 min）"。
- 已在同目录核查过可能的缓存来源，均**不存在**：`./work`（`DEFAULT: ./work`）不存在；`~/.uvs*`、`/tmp/uvlan*` 无匹配。
- 两段均落盘了完整库（`Saving Verilog Library ... Done`，treeir.db 等均生成）⇒ **不是"跳过编译"的假快**。
- **本任务范围内不考证其成因**；仅标注"成本基线（4 min）与本机实测（≈2 s）严重不符，建议 Lead 更新基线数字或另立核查项"。数字均取自命令/工具输出，未手算。

## 6 警告清单（0 error / 17 warning，均为既有告警，非本任务判定范围）

**段① rtl（13 条）**

| 计数 | 告警 |
|---|---|
| 4 | `Warning-121687: Unknown Pragma Prefix`（`// synthesis translate_off`，提示可用 `-uvs_xlrm PragmaPrefix=synthesis`） |
| 4 | `Warning-121553: Use before declare`（`gtp_async/sync_fifo_*` 的 `PREFETCH_EN_SEL`） |
| 3 | `Warning-120002: Command option warning`（`-usdb -uvs_xlrm`、`-Xopts sva_fix_AIR_12100`、`-Xopts sva_fix_AIR_12098` 不被支持，已忽略） |
| 2 | `Warning-120428: Non standard gen block`（`user_sdpram_pango_bram.sv:1183` 等） |

**段② tb（4 条）**

| 计数 | 告警 |
|---|---|
| 3 | `Warning-120002: Command option warning`（同上三个选项被忽略；另有 `-Xair xb.always_opt_with_pda_signal is already default` 提示） |
| 1 | `Warning-121147: Redefinition` —— **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**，`task set_rtc_rw(... bit [31:0] base_addr='h2000, ...)`（定义于 **:799**）重定义了 `set_rtc_rw` 体内 :802 声明的 `bit [31:0] base_addr`，**该重定义被忽略**（`Previous definition here: :799`） |

> ⚠ **转交 checker 留意（runner 不判定用例对错）**：`Warning-121147` 位于 TB 既有文件 `pcie_sequence.sv`
> 的 `set_rtc_rw` task —— 与 RTC 用例很可能用到的 API 同名同域。它只是 warning（不阻塞卡点 B），
> 但"重定义被忽略"可能影响取值来源。**RTL/TB 只读，runner 未做任何改动**；是否影响用例语义请 checker 在卡点 C 判。

## 7 写权与红线自查

- 本轮写出的文件：`SIMLIB_RUN/log/*`、`SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/*`、本证据文件 —— 均在本任务 `writeScopes` 内 ✅
- **未修改**任何用例（`TESTLIB_sandbox/*.sv` 跑前跑后 md5 一致）、`RTL/`、`TB/`、`PKG/` ✅
- **未修改** `doc/tools/compile_only.sh`（我只有读权；其 md5 `4d7cf96c2e3acde11c46a5b15632bfa5` 跑前跑后一致）✅
- 串行：跑前跑后均 `ps -ef` 无并发，锁机制已生效 ✅
- 数字纪律：本文所有 md5/字节/行数/耗时/计数均**由命令或工具输出直接复制**，未手算 ✅

## 8 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv           # da044d2b…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_{rtl,tb}.log
diff uvs.setup doc/_run_artifacts/uvs.setup.orig                             # rc=0
```
