# A2c 编译证据 —— v3（卡点 B · 只编译 · 第 3 次重采）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **口径纪律**：本次**只编译、未仿真**。本文件不含任何"用例通过 / 功能正确"字样 ——
> 编译通过只证明"语法 / 宏展开 / 包依赖 / 端口连接无编译期错误"，**不等于**功能正确（功能判定属 A4/A5）。
>
> **为什么重采**：v1（`bc9cd56d…`）、v2（`e24aded2…`）的 A2/A2b 证据**不得复用**给 v3
> （`235d20a5…`）。上游规格：`doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` §2 A2 + §3 + §4。

---

## 1 证据字段（task-18 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261014-A2c-01` |
| 时刻 | 段① `14:23:00` → 段② `14:23:01` → 结束 `2026-10-14 14:23:02`（日志内 `Compilation starts at` + job stdout 观测） |
| 用例名 | `tc_dom_polling_trig_chk_01` |
| 用例路径 | `doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **v3 md5** | `235d20a5f2cc7b4911201c8939a14b81` |
| **v3 字节** | `44143` |
| **v3 行数** | `607` |
| 与 Lead 报值比对 | **一致** ✅（Lead 报 `235d20a5f2cc7b4911201c8939a14b81` / 44143 B / 607 行） |
| v3 md5 跑后复查 | `235d20a5f2cc7b4911201c8939a14b81`（与跑前相同 ⇒ 无移动靶）✅ |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_dom_polling_trig_chk_01 -f doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **段① rc** | **0** |
| **段② rc** | **0** |
| **段① 耗时** | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 1.32s, CPU time: 1.30s`） |
| **段② 耗时** | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 0.78s, CPU time: 0.79s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log` —— `86150` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log` —— `29201` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/a2c_compile_stdout_v3.log` —— `114485` 字节 / `2105` 行 |
| warning 计数 | 段① **13** 条；段② **4** 条（error 均为 0） |
| 首个 error 行 | **N/A（0 error）** |
| 编译库 | `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}` |
| 脚本 md5 | `4d7cf96c2e3acde11c46a5b15632bfa5` |

### 三代身份沿革（新证的理由）

| 轮次 | md5 | 字节 | 行数 |
|---|---|---|---|
| v1 | `bc9cd56d4b361f4a5be028d8d24cfc56` | 37468 | 539 |
| v2 | `e24aded26476aed9426576da361c0fa2` | 43922 | 605 |
| **v3** | **`235d20a5f2cc7b4911201c8939a14b81`** | **44143** | **607** |

### `[PASS]` 行原文（引述脚本自身输出）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv  (md5 235d20a5f2cc7b4911201c8939a14b81)
库        : SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
```

### 判定依据（task-18 口径）

- PASS ⟺ 两段 `uvlan` 均 rc=0 **且** 两段日志无 ERROR 级诊断
  - 段① rc=0 ✅；段② rc=0 ✅
  - `_c_rtl.log`：`Compilation: 0 error(s), 13 warning(s)`；`Error-\d+`/`^ERROR` 计数 **0** ✅
  - `_c_tb.log`：`Compilation: 0 error(s), 4 warning(s)`；`Error-\d+`/`^ERROR` 计数 **0** ✅
- ⇒ **编译通过（卡点 B）**

### 真编证据（排除"跳过编译"）

```
SIMLIB_RUN/log/..._c_rtl.log:1293:Saving Verilog Library 'rtl' to Path './SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/rtl' Done
SIMLIB_RUN/log/..._c_tb.log:793 :Saving Verilog Library 'tb'  to Path './SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/tb'  Done
rtl 段 Analyzing Verilog file 行数: 256
```

## 2 ★★ 内容指纹：证明日志是本轮 v3 重写（**不看字节数/mtime**）

**先说陷阱为何仍在**：v1 / v2 / v3 三轮的编译日志**字节数完全相同**（rtl 恒 `86150`、tb 恒 `29201`）——
**只比大小必然误判**。故本轮按 Lead 要求给出三重**内容指纹**：

| 指纹 | 本轮 **v3** | 归档 **v2**（`archive_a2b_v2/`） | 归档 **v1**（`archive_a2_v1/`） |
|---|---|---|---|
| ① `Compilation starts at`（rtl / tb） | **14:23:00 / 14:23:01** | 14:13:52 / 14:13:54 | 13:57:39 / 13:57:43 |
| ② 日志内引用用例的**行号** | **205 / 207 / 208 / 209 / 210** | 203 / 205 / 206 / 207 / 208 | 173 / 175 / 176 / 177 / 178 |
| ③ 与本轮日志 `diff` 行数 | — | c_tb **48 行**、c_rtl **8 行** | c_tb **48 行**、c_rtl **8 行** |
| 文件字节数（**仅供参考，非判据**） | 86150 / 29201 | 86150 / 29201 | 86150 / 29201 |

- ② 的行号**随用例行数变化**（539 → 605 → 607 行 ⇒ 173x → 203x → 205x），是 v3 专属指纹 ✅
- ① 的时刻与本轮 `run_id` 起始时刻（`14:23:00`）吻合 ✅
- ⇒ 两段日志均为**本轮真实重写**，**不是复用任何旧日志**。

**v1/v2 日志的保全**（各自运行前**复制、未移动**）：

```
SIMLIB_RUN/log/archive_a2_v1/  tc_dom_polling_trig_chk_01_1_c_rtl.log  2f8ad76b58e9178f88db49e665bc74b0  86150 B
SIMLIB_RUN/log/archive_a2_v1/  tc_dom_polling_trig_chk_01_1_c_tb.log   73f9c6683c1f30744882109998e2eccf  29201 B
SIMLIB_RUN/log/archive_a2_v1/  a2_compile_stdout_v1.log                2c1611766c203b5ba5abee2629aff7ac 114485 B
SIMLIB_RUN/log/archive_a2b_v2/ tc_dom_polling_trig_chk_01_1_c_rtl.log  04098ba8b3dfceb0f8d38987cbbcf283  86150 B
SIMLIB_RUN/log/archive_a2b_v2/ tc_dom_polling_trig_chk_01_1_c_tb.log   bf92a8500f898586ffd89ba119c60fd8  29201 B
SIMLIB_RUN/log/archive_a2b_v2/ a2b_compile_stdout_v2.log               0a00c163652cb6b321d934cc6cd0df7a 114485 B
```

> 提示 guardian：`SIMLIB_RUN/log/` 下现有 `archive_a2_v1/`、`archive_a2b_v2/` 两个子目录（additive，未动其它文件）。

## 3 `TESTLIB/` 口径 A 摘要（§3 硬纪律：本步绝对不动 `TESTLIB/`）

| 时刻 | `ls TESTLIB/*.sv \| wc -l` | `md5sum TESTLIB/*.sv \| LC_ALL=C sort \| md5sum` |
|---|---|---|
| 跑前 | **162** | `4c0942ac419f67c6fdb391dd2083f0b3` |
| 跑后 | **162** | `4c0942ac419f67c6fdb391dd2083f0b3` |
| 基线 | 162 | `4c0942ac419f67c6fdb391dd2083f0b3` ✅ **完全一致** |

其余 §8 冻结项跑前/跑后一致：

```
TESTLIB/tc_dom_polling_trig_chk_01.sv 是否存在 : 跑前无、跑后无（本步不放入 TESTLIB/）✅
git status --porcelain TESTLIB | wc -l        : 跑前 34 → 跑后 34   ✅
LOG/ 文件数                                    : 跑前 78 → 跑后 78   ✅
git status --porcelain | wc -l                 : 跑前 49 → 跑后 49   ✅ ; ' M' 跑前 18 → 跑后 18 ✅
find RTL TB PKG -type f -newermt '2026-10-14 00:00' : 空 ✅（RTL/TB/PKG 零改动）
```

## 4 跑前快照 / 跑后还原 / 串行（全绿）

```
跑前: diff uvs.setup doc/_run_artifacts/uvs.setup.orig → rc=0（两者 md5 均 a80f7b6ca48a7961a107bbe871af761d）
      ps -ef | grep -E "uvlan|uvs|run_local|compile_only" → 无输出（rc=1）⇒ 空闲
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在（无遗留锁）
跑后: diff uvs.setup doc/_run_artifacts/uvs.setup.orig → rc=0 ✅ 已还原
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在 ✅ 无遗留锁
      ps -ef | grep ... → 无输出（rc=1）⇒ 空闲 ✅
脚本 exit 0
```

F2 选项自检**通过**（`[info] 选项自检通过：tb_dir/all_opt 与 run_local.sh 逐字节一致`，未 exit 12）；
F4 锁正常获取并释放；F1 未出现任何 `[WARN] uvs.setup 还原到的是夹具值…`。

## 5 warning 明细（0 error / 17 warning，全为既有告警）

**段① rtl（13 条）**：`121687 Unknown Pragma Prefix` ×4、`121553 Use before declare` ×4、
`120002 Command option warning` ×3、`120428 Non standard gen block` ×2

**段② tb（4 条）**：`120002 Command option warning` ×3、`121147 Redefinition` ×1

> `Warning-121147: Redefinition` 位于既有 TB 文件 **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**
> （`set_rtc_rw` 定义于 `:799`）。该告警在 v1/v2/v3 三轮编译中**逐字相同** ⇒ TB 既有告警，与本用例无关。
> RTL/TB 只读，runner 未做任何改动。

## 6 归档完整性（A6 会核）

| 文件 | 状态 |
|---|---|
| `evidence/A2_compile_evidence.md`（v1 证据） | **未被覆盖** ✅ md5 仍 `a09a9a8c7f02d1241d231172f756a12c` |
| `evidence/A2b_compile_evidence_v2.md`（v2 证据） | **未被覆盖** ✅ md5 仍 `c087031ae0b571b2c96e749152acadbe` |
| `doc/_run_artifacts/tc_dom_polling_trig_chk_01_v1.sv` | **未被改动** ✅ md5 `bc9cd56d4b361f4a5be028d8d24cfc56` |
| `doc/_run_artifacts/tc_dom_polling_trig_chk_01_v2.sv` | **未被改动** ✅ md5 `e24aded26476aed9426576da361c0fa2` |
| `doc/tools/compile_only.sh` | **未被改动** ✅ md5 `4d7cf96c2e3acde11c46a5b15632bfa5` |
| 本文件 | 新增（只增不改） |

## 7 写权与红线自查

- 本轮写出：`SIMLIB_RUN/log/*`（含 `archive_a2b_v2/` 副本、`a2c_compile_stdout_v3.log`）、
  `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/*`、本证据文件 —— 均在 `task-18` 的 `writeScopes` 内 ✅
- **未**写入 `TESTLIB/`；**未**修改用例、v1/v2 归档件、既有证据文件、`RTL/`、`TB/`、`PKG/`、`compile_only.sh` ✅
- 串行：跑前跑后 `ps -ef` 均无并发；F4 锁已用并已释放 ✅
- 数字纪律：本文所有 md5 / 字节 / 行数 / 耗时 / 计数均由命令或工具输出直接复制，未手算 ✅

## 8 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv      # 235d20a5…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
grep -n '\[PASS\]' SIMLIB_RUN/log/a2c_compile_stdout_v3.log
# 内容指纹（不看字节数）
grep -h 'Compilation starts at' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log   # 14:23:0x
grep -oE 'tc_dom_polling_trig_chk_01\.sv, [0-9]+' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log | sort -u   # 205/207-210
diff SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log SIMLIB_RUN/log/archive_a2b_v2/tc_dom_polling_trig_chk_01_1_c_tb.log | wc -l  # 48
ls TESTLIB/*.sv | wc -l                                        # 162
md5sum TESTLIB/*.sv | LC_ALL=C sort | md5sum                   # 4c0942ac419f67c6fdb391dd2083f0b3
diff uvs.setup doc/_run_artifacts/uvs.setup.orig               # rc=0
```
