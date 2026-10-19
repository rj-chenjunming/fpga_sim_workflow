# T2b 编译证据 —— v2（卡点 B · 只编译 · 重采）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **口径声明**：本次**只编译、未仿真**。本文件不含任何"用例通过 / 功能正确"之类判定 ——
> 只编译能证明的仅仅是"语法 / 宏展开 / 包依赖 / 端口连接在编译期无错误"，**不能**证明用例行为正确。
>
> **为什么重采**：v1（md5 `da044d2b…` / 27459 B / 393 行）已归档；作者为修 Δ1 改为 v2
> （`21fd7e49…` / 29341 B / 409 行）。用例已变 ⇒ v1 的编译证据**不得复用**，本文件为 v2 专属新证。

---

## 1 证据字段（task-6 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261013-T2b-01` |
| 时刻 | 结束 `2026-10-13 18:13:11`（job stdout 观测）；START 行未落 tee（`echo`/`date` 在管道外），故不提供手算数字 |
| 用例名 | `tc_rtc_blk_reset_chk_01` |
| 用例路径 | `doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` |
| **v2 md5** | `21fd7e49a4c9916d76dada84fc276ca7` |
| **v2 字节** | `29341` |
| **v2 行数** | `409` |
| 与 Lead 冻结值比对 | **一致** ✅（Lead 报 `21fd7e49a4c9916d76dada84fc276ca7` / 29341 B / 409 行） |
| v2 md5 跑后复查 | `21fd7e49a4c9916d76dada84fc276ca7`（与跑前相同 ⇒ 无移动靶）✅ |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_rtc_blk_reset_chk_01 -f doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` |
| 段① rc | **0** |
| 段② rc | **0** |
| 段① 耗时 | 脚本自报 `耗时 2s`（工具自报 `Elapsed time: 1.36s, CPU time: 1.36s`） |
| 段② 耗时 | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 0.84s, CPU time: 0.85s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_rtl.log` —— `86144` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_tb.log` —— `29022` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/t2b_compile_stdout_v2.log` —— `114284` 字节 / `2105` 行 |
| warning 计数 | 段① **13** 条；段② **4** 条（error 均为 0） |
| 首个 error 行 | **N/A（0 error）** |
| 编译库 | `SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl`、`.../tb` |

### v2 与 v1 的身份差异（新证的理由）

```
v1 : da044d2ba922ded6081e3abe7d52aeaa   27459 字节   393 行   （原件归档 doc/_run_artifacts/tc_rtc_blk_reset_chk_01_v1.sv）
v2 : 21fd7e49a4c9916d76dada84fc276ca7   29341 字节   409 行   （本次编译对象）
差异: 字节 +1882，行数 +16
```

## 2 判定依据（task-6 口径，逐条命中）

- PASS ⟺ 两段 `uvlan` 均 rc=0 **且** 两段日志无 ERROR 级诊断
  - 段① rc=0 ✅；段② rc=0 ✅
  - `_c_rtl.log`：`Compilation: 0 error(s), 13 warning(s)`；`Error-\d+`/`^ERROR` 计数 **0** ✅
  - `_c_tb.log`：`Compilation: 0 error(s), 4 warning(s)`；`Error-\d+`/`^ERROR` 计数 **0** ✅
- ⇒ **编译通过（卡点 B）**

### `[PASS]` 行原文（引述脚本自身输出）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv  (md5 21fd7e49a4c9916d76dada84fc276ca7)
库        : SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_{rtl,tb}.log
```

### 脚本头部（原样，含 v2 身份）

```
============================================================
 compile_only  tc=tc_rtc_blk_reset_chk_01  seed=1
 src           doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv
 md5           21fd7e49a4c9916d76dada84fc276ca7
 大小/行数     29341 字节 / 409 行
============================================================
[info] 选项自检通过：tb_dir/all_opt 与 run_local.sh 逐字节一致
```

### 真编证据（排除"跳过编译"）

```
SIMLIB_RUN/log/..._c_rtl.log:1293:Saving Verilog Library 'rtl' to Path './SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl' Done
SIMLIB_RUN/log/..._c_tb.log:793 :Saving Verilog Library 'tb'  to Path './SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/tb'  Done
rtl 段 Analyzing Verilog file 行数: 256
```

## 3 warning 明细（0 error / 17 warning，全为既有告警）

**段① rtl（13 条）**：`121687 Unknown Pragma Prefix` ×4、`121553 Use before declare` ×4、
`120002 Command option warning` ×3、`120428 Non standard gen block` ×2

**段② tb（4 条）**：`120002 Command option warning` ×3、`121147 Redefinition` ×1

> `Warning-121147: Redefinition` 位于既有 TB 文件 **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**
> （`set_rtc_rw` 定义于 `:799`，其形参 `bit [31:0] base_addr='h2000` 被 :802 的局部声明重定义、
> **该重定义被忽略**）。与 v1 编译时**完全相同**（同一文件:行号、同一措辞）⇒ 与 v2 的三处整改无关，
> 属 TB 既有告警。RTL/TB 严格只读，runner 未做任何改动；**是否影响用例语义由 checker 在卡点 C 判**。

## 4 跑前快照 / 跑后还原 / 串行（全绿）

```
跑前: diff uvs.setup doc/_run_artifacts/uvs.setup.orig  → rc=0
      两者 md5 均为 a80f7b6ca48a7961a107bbe871af761d
      ps -ef | grep -E "uvlan|uvs|compile_only|run_local" → 无输出（rc=1）⇒ 空闲
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在（无遗留锁）
      夹具 doc/_run_artifacts/uvs.setup.orig 权限 444

跑后: diff uvs.setup doc/_run_artifacts/uvs.setup.orig  → rc=0 ✅ 已还原
      md5 a80f7b6ca48a7961a107bbe871af761d（== 跑前 == 夹具）
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在 ✅ 无遗留锁
      ps -ef | grep ... → 无输出（rc=1）⇒ 空闲 ✅
脚本 exit 0
```

本轮 F2 选项自检**再次通过**（未 exit 12）；F4 锁正常获取并释放；F1 未出现任何 `[WARN] uvs.setup 还原到的是夹具值…`。

## 5 归档完整性（T4 会核）

| 文件 | 状态 |
|---|---|
| `doc/agents/_demo/evidence/T2_compile_evidence.md`（v1 证据） | **未被覆盖** ✅ md5 仍为 `b276686a2c97f00ee76138329d47f31f` |
| `doc/_run_artifacts/tc_rtc_blk_reset_chk_01_v1.sv`（v1 原件归档） | **未被改动** ✅ md5 `da044d2ba922ded6081e3abe7d52aeaa`、权限 600 |
| `doc/tools/compile_only.sh` | **未被改动** ✅ md5 `4d7cf96c2e3acde11c46a5b15632bfa5` |
| 本文件 | 新增（只增不改） |

**v1 编译日志的保全**：脚本把编译日志固定写在 `SIMLIB_RUN/log/<tc>_<seed>_c_{rtl,tb}.log`，
本次运行会**原位覆盖** v1 的日志。为不破坏 v1 证据链，我在运行**之前**把 v1 日志
**复制（未移动）**到 `SIMLIB_RUN/log/archive_v1/`：

```
SIMLIB_RUN/log/archive_v1/tc_rtc_blk_reset_chk_01_1_c_rtl.log   1f0bc0f631631da14162fc286a51a03d  86144 B
SIMLIB_RUN/log/archive_v1/tc_rtc_blk_reset_chk_01_1_c_tb.log    1bea7c60feca2185fa9d502db7808342  29022 B
SIMLIB_RUN/log/archive_v1/t2_compile_stdout_v1.log              899b14080fc5c675e1b8c21bf3924647 114284 B
```

> 提示 guardian：`SIMLIB_RUN/log/` 下新增了子目录 `archive_v1/`（additive，未动其它任何文件）。

## 6 写权与红线自查

- 本轮写出：`SIMLIB_RUN/log/*`（含 `archive_v1/` 副本、`t2b_compile_stdout_v2.log`）、
  `SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/*`、本证据文件 —— 均在 `task-6` 的 `writeScopes` 内 ✅
- **未修改**用例（v2 跑前跑后 md5 一致）、v1 归档件、v1 证据文件、`RTL/`、`TB/`、`PKG/`、`compile_only.sh` ✅
- 串行：跑前跑后 `ps -ef` 均无并发；F4 锁已用并已释放 ✅
- 数字纪律：本文所有 md5 / 字节 / 行数 / 耗时 / 计数均由命令或工具输出直接复制，未手算 ✅

## 7 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv      # 21fd7e49…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_rtc_blk_reset_chk_01_1_c_{rtl,tb}.log
grep -n '\[PASS\]' SIMLIB_RUN/log/t2b_compile_stdout_v2.log
diff uvs.setup doc/_run_artifacts/uvs.setup.orig                        # rc=0
```
