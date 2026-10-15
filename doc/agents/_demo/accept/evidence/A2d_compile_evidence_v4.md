# A2d 编译证据 —— v4（卡点 B · 只编译 · 第 4 次重采）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **口径纪律**：本次**只编译、未仿真**。本文件不含任何"用例通过 / 功能正确"字样 ——
> 编译通过只证明"语法 / 宏展开 / 包依赖 / 端口连接无编译期错误"，**不等于**功能正确（功能判定属 A4/A5）。
>
> **为什么重采**：v1/v2/v3 的 A2/A2b/A2c 证据**不得复用**给 v4（`33cc907f…`）。
> 上游规格：`doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` §2 A2 + §3 + §4。

---

## 1 证据字段（task-21 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261014-A2d-01` |
| 时刻 | 段① `14:47:06` → 段② `14:47:07` → 结束 `2026-10-14 14:47:08`（日志内 `Compilation starts at` + job stdout 观测） |
| 用例名 | `tc_dom_polling_trig_chk_01` |
| 用例路径 | `doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **v4 md5** | `33cc907f7f03a930185ecfadaaadd7e0` |
| **v4 字节** | `47468` |
| **v4 行数** | `636` |
| 与 Lead 报值比对 | **一致** ✅（Lead 报 `33cc907f7f03a930185ecfadaaadd7e0` / 47468 B / 636 行） |
| v4 md5 跑后复查 | `33cc907f7f03a930185ecfadaaadd7e0`（与跑前相同 ⇒ 无移动靶）✅ |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_dom_polling_trig_chk_01 -f doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **段① rc** | **0** |
| **段② rc** | **0** |
| **段① 耗时** | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 1.30s, CPU time: 1.30s`） |
| **段② 耗时** | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 0.88s, CPU time: 0.86s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log` —— `86150` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log` —— `29201` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/a2d_compile_stdout_v4.log` —— `114485` 字节 / `2105` 行 |
| warning 计数 | 段① **13** 条；段② **4** 条（error 均为 0） |
| 首个 error 行 | **N/A（0 error）** |
| 编译库 | `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}` |
| 脚本 md5 | `4d7cf96c2e3acde11c46a5b15632bfa5` |

### 四代身份沿革（新证的理由）

| 轮次 | md5 | 字节 | 行数 |
|---|---|---|---|
| v1 | `bc9cd56d4b361f4a5be028d8d24cfc56` | 37468 | 539 |
| v2 | `e24aded26476aed9426576da361c0fa2` | 43922 | 605 |
| v3 | `235d20a5f2cc7b4911201c8939a14b81` | 44143 | 607 |
| **v4** | **`33cc907f7f03a930185ecfadaaadd7e0`** | **47468** | **636** |

### `[PASS]` 行原文（引述脚本自身输出）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv  (md5 33cc907f7f03a930185ecfadaaadd7e0)
库        : SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
```

### 判定依据（task-21 口径）

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

## 2 ★★ 内容指纹：证明日志是本轮 v4 重写（**不看字节数/mtime**）

**陷阱第 4 次出现**：v1 / v2 / v3 / **v4** 四轮的编译日志**字节数完全相同**（rtl 恒 `86150`、tb 恒 `29201`）——
**只比大小必然误判**（本轮再次实测确认：`86150` / `29201`）。故按 Lead 要求给出三重**内容指纹**：

| 指纹 | 本轮 **v4** | 归档 **v2**（`archive_a2b_v2/`） | 归档 **v1**（`archive_a2_v1/`） |
|---|---|---|---|
| ① `Compilation starts at`（rtl / tb） | **14:47:06 / 14:47:07** | 14:13:52 / 14:13:54 | 13:57:39 / 13:57:43 |
| ② 日志内引用用例的**行号** | **226 / 228 / 229 / 230 / 231** | 203 / 205 / 206 / 207 / 208 | 173 / 175 / 176 / 177 / 178 |
| ③ 与本轮日志 `diff` 行数 | — | c_tb **48 行**、c_rtl **8 行** | c_tb **48 行**、c_rtl **8 行** |
| 文件字节数（**仅供参考，非判据**） | 86150 / 29201 | 86150 / 29201 | 86150 / 29201 |

- ② 的行号**随用例行数变化**（539 → 605 → 607 → 636 行 ⇒ 173x → 203x → 205x → **226x**），是 v4 专属指纹 ✅
- ① 的时刻与本轮 `run_id` 起始时刻（`14:47:06`）吻合 ✅
- v3 的对照：v3 为 `14:23:00/01` + 行号 `205/207/208/209/210`（见 `A2c_compile_evidence_v3.md`）
- ⇒ 两段日志均为**本轮真实重写**，**不是复用任何旧日志**。

**v4 日志已另存副本**（因上一轮中止的全跑清掉了 v3 的编译日志原件，见 §5）：

```
SIMLIB_RUN/log/archive_a2d_v4/ tc_dom_polling_trig_chk_01_1_c_rtl.log  b1ccce3fb9b11dc2b6e7328c84d69939  86150 B
SIMLIB_RUN/log/archive_a2d_v4/ tc_dom_polling_trig_chk_01_1_c_tb.log   2c4c1102e0b06353227fd909590c9a0a  29201 B
SIMLIB_RUN/log/archive_a2d_v4/ a2d_compile_stdout_v4.log               53581eb7b81d3231deeabf8d5231a4b4 114485 B
```

## 3 `TESTLIB/` 口径 A 摘要（§3 硬纪律：本步绝对不动 `TESTLIB/`）

| 时刻 | `ls TESTLIB/*.sv \| wc -l` | `md5sum TESTLIB/*.sv \| LC_ALL=C sort \| md5sum` |
|---|---|---|
| 跑前 | **162** | `4c0942ac419f67c6fdb391dd2083f0b3` |
| 跑后 | **162** | `4c0942ac419f67c6fdb391dd2083f0b3` |
| 基线 | 162 | `4c0942ac419f67c6fdb391dd2083f0b3` ✅ **完全一致** |

其余 §8 冻结项跑前/跑后一致：

```
TESTLIB/tc_dom_polling_trig_chk_01.sv 是否存在 : 跑前无、跑后无 ✅
git status --porcelain TESTLIB | wc -l        : 跑前 34 → 跑后 34   ✅
LOG/ 文件数                                    : 跑前 78 → 跑后 78   ✅
git status --porcelain | wc -l                 : 跑前 49 → 跑后 49   ✅ ; ' M' 跑前 18 → 跑后 18 ✅
find RTL TB PKG -type f -newermt '2026-10-14 00:00' : 空 ✅（RTL/TB/PKG 零改动）
```

## 4 跑前残留检查（上一轮全跑被中止 —— Lead 特别要求）

**结论：环境干净，无残留** ✅

```
ps -ef | grep -E "uvlan|uvs|run_local|compile_only" → 无输出（rc=1）⇒ 无残留进程 ✅
ls -ld SIMLIB_RUN/.compile_only.lock               → 不存在 ⇒ 无遗留锁 ✅
diff uvs.setup doc/_run_artifacts/uvs.setup.orig   → rc=0（md5 a80f7b6ca48a7961a107bbe871af761d）⇒ 已还原 ✅
ls TESTLIB/*.sv | wc -l                            → 162；口径A摘要 == 基线 ⇒ 无残留临时用例 ✅
```

**Lead 的 A4 中止尝试产物我未改动**（仍在原位）：
`SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_run.log`（21005 B, 14:41）、
`archive_a4_attempt1_run.log`（21005 B, 14:41）、`a4_run_stdout.log`（153207 B, 14:41）、
`SIMLIB_RUN/wave/tc_dom_polling_trig_chk_01_1/`（已 elaborate 的可执行）。

跑后同样确认：`diff uvs.setup …` rc=0、无遗留锁、`ps -ef` 无输出 ⇒ 本次编译未污染后续全跑环境。

## 5 ⚠ 两条需 Lead 知晓的观察（非本步错误）

1. **串行重叠风险（建议处置）**：`task-11`（A4 全跑）状态仍为 `in_progress`、owner = `lead`，其
   `write_scopes` 含 `TESTLIB` 与 `SIMLIB_RUN`；本任务 `task-21` 的 `write_scopes` 亦含 `SIMLIB_RUN`，
   派发时已带 `writeScopeWarnings: ["write scopes overlap with task-11"]`。
   我在跑前/跑后两次 `ps -ef` 均为**空闲**，本次编译仅 ~2 秒且未与任何进程重叠，故**实际未并发**；
   但若 A4 随后启动，二者都写 `uvs.setup`（卡点 D 红线 7）⇒ **请确保同一时刻只有一方在跑**。
2. **v3 编译日志原件已被中止的全跑清掉**：`SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log`
   在本轮跑前**不存在**（v3 那两份 14:23 的日志原件已丢失）；v3 的日志指纹仍可从
   `A2c_compile_evidence_v3.md` 读到（`14:23:00/01`、行号 `205/207/208/209/210`）。
   v1/v2 的日志另有我在各轮运行前所留副本（`archive_a2_v1/`、`archive_a2b_v2/`），v4 也已留副本
   （`archive_a2d_v4/`）⇒ 建议以后每轮编译后立即归档，避免被后续全跑清理。

## 6 warning 明细（0 error / 17 warning，全为既有告警）

**段① rtl（13 条）**：`121687 Unknown Pragma Prefix` ×4、`121553 Use before declare` ×4、
`120002 Command option warning` ×3、`120428 Non standard gen block` ×2

**段② tb（4 条）**：`120002 Command option warning` ×3、`121147 Redefinition` ×1

> `Warning-121147: Redefinition` 位于既有 TB 文件 **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**
> （`set_rtc_rw` 定义于 `:799`）。该告警在 v1/v2/v3/v4 四轮编译中**逐字相同** ⇒ TB 既有告警，与本用例无关。
> RTL/TB 只读，runner 未做任何改动。

## 7 归档完整性（A6 会核）

| 文件 | 状态 |
|---|---|
| `evidence/A2_compile_evidence.md`（v1） | **未被覆盖** ✅ md5 仍 `a09a9a8c7f02d1241d231172f756a12c` |
| `evidence/A2b_compile_evidence_v2.md`（v2） | **未被覆盖** ✅ md5 仍 `c087031ae0b571b2c96e749152acadbe` |
| `evidence/A2c_compile_evidence_v3.md`（v3） | **未被覆盖** ✅ md5 仍 `4045540e4c3b79b7553f38d95ec7d9f5` |
| `doc/_run_artifacts/…_v1.sv` | **未被改动** ✅ `bc9cd56d4b361f4a5be028d8d24cfc56` |
| `doc/_run_artifacts/…_v2.sv` | **未被改动** ✅ `e24aded26476aed9426576da361c0fa2` |
| `doc/_run_artifacts/…_v3.sv` | **未被改动** ✅ `235d20a5f2cc7b4911201c8939a14b81` |
| `doc/tools/compile_only.sh` | **未被改动** ✅ `4d7cf96c2e3acde11c46a5b15632bfa5` |
| 本文件 | 新增（只增不改） |

## 8 写权与红线自查

- 本轮写出：`SIMLIB_RUN/log/*`（含 `archive_a2d_v4/` 副本、`a2d_compile_stdout_v4.log`）、
  `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/*`、本证据文件 —— 均在 `task-21` 的 `writeScopes` 内 ✅
- **未**写入 `TESTLIB/`；**未**修改用例、v1/v2/v3 归档件、既有证据文件、Lead 的 A4 中止产物、
  `RTL/`、`TB/`、`PKG/`、`compile_only.sh` ✅
- 串行：跑前跑后 `ps -ef` 均无并发；F4 锁已用并已释放 ✅
- 数字纪律：本文所有 md5 / 字节 / 行数 / 耗时 / 计数均由命令或工具输出直接复制，未手算 ✅

## 9 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv      # 33cc907f…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
grep -n '\[PASS\]' SIMLIB_RUN/log/a2d_compile_stdout_v4.log
# 内容指纹（不看字节数）
grep -h 'Compilation starts at' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log   # 14:47:06 / 14:47:07
grep -oE 'tc_dom_polling_trig_chk_01\.sv, [0-9]+' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log | sort -u  # 226/228-231
diff SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log SIMLIB_RUN/log/archive_a2b_v2/tc_dom_polling_trig_chk_01_1_c_tb.log | wc -l  # 48
ls TESTLIB/*.sv | wc -l                                        # 162
md5sum TESTLIB/*.sv | LC_ALL=C sort | md5sum                   # 4c0942ac419f67c6fdb391dd2083f0b3
diff uvs.setup doc/_run_artifacts/uvs.setup.orig               # rc=0
```
