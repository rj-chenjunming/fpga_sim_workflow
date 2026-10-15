# A2 编译证据（卡点 B · 只编译）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **口径纪律**：本次**只编译、未仿真**。本文件不含任何"用例通过 / 功能正确"字样 ——
> 编译通过只证明"语法 / 宏展开 / 包依赖 / 端口连接无编译期错误"，**不等于**功能正确（功能判定属 A4/A5）。
> 上游规格：`doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` §2 A2 + §3 第 1 条 + §4 串行纪律。

---

## 1 证据字段（task-9 / A2 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261014-A2-01` |
| 时刻 | 结束 `2026-10-14 13:57:44`（job stdout 观测）；START 行未落 tee（`echo`/`date` 在管道外），不提供手算数字 |
| 用例名 | `tc_dom_polling_trig_chk_01` |
| 用例路径 | `doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| 用例 md5 | `bc9cd56d4b361f4a5be028d8d24cfc56` |
| 字节 | `37468` |
| 行数 | `539` |
| 与 Lead 报值比对 | **一致** ✅（Lead 报 `bc9cd56d4b361f4a5be028d8d24cfc56` / 37468 B / 539 行） |
| md5 跑后复查 | `bc9cd56d4b361f4a5be028d8d24cfc56`（与跑前相同 ⇒ 无移动靶）✅ |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_dom_polling_trig_chk_01 -f doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **段① rc** | **0** |
| **段② rc** | **0** |
| **段① 耗时** | 脚本自报 `耗时 3s`（工具自报 `Elapsed time: 3.06s, CPU time: 1.28s`） |
| **段② 耗时** | 脚本自报 `耗时 2s`（工具自报 `Elapsed time: 1.12s, CPU time: 0.77s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log` —— `86150` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log` —— `29201` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/a2_compile_stdout.log` —— `114485` 字节 / `2105` 行 |
| warning 计数 | 段① **13** 条；段② **4** 条（error 均为 0） |
| 首个 error 行 | **N/A（0 error）** |
| 编译库 | `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}` |
| 脚本 md5 | `4d7cf96c2e3acde11c46a5b15632bfa5` |

### `[PASS]` 行原文（引述脚本自身输出）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv  (md5 bc9cd56d4b361f4a5be028d8d24cfc56)
库        : SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
```

### 判定依据（task-9 口径）

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

## 2 `TESTLIB/` 计数（§3 硬纪律：本步绝对不动 `TESTLIB/`）

| 时刻 | `ls TESTLIB/*.sv \| wc -l` | 说明 |
|---|---|---|
| 跑前 | **162** | == Lead 基线 162 ✅ |
| 跑后 | **162** | ✅ 未变 |

补充冻结项跑前/跑后一致：

```
TESTLIB/tc_dom_polling_trig_chk_01.sv 是否存在 : 跑前无、跑后无（本步不放入 TESTLIB/）✅
git status --porcelain TESTLIB | wc -l        : 跑前 34 → 跑后 34   ✅
LOG/ 文件数                                    : 跑前 78 → 跑后 78   ✅（历史日志只读）
git status --porcelain | wc -l                 : 跑前 49 → 跑后 49   ✅
  其中 ' M'                                    : 跑前 18 → 跑后 18   ✅
find RTL TB PKG -type f -newermt '2026-10-14 00:00' : 空 ✅（RTL/TB/PKG 零改动）
```

## 3 跑前快照 / 跑后还原 / 串行（全绿）

```
跑前: diff uvs.setup doc/_run_artifacts/uvs.setup.orig → rc=0
      两者 md5 均 a80f7b6ca48a7961a107bbe871af761d（== ACCEPTANCE_PLAN §8 基线）
      ps -ef | grep -E "uvlan|uvs|run_local|compile_only" → 无输出（rc=1）⇒ 空闲
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在（无遗留锁）
跑后: diff uvs.setup doc/_run_artifacts/uvs.setup.orig → rc=0 ✅ 已还原
      md5 a80f7b6ca48a7961a107bbe871af761d
      ls -ld SIMLIB_RUN/.compile_only.lock → 不存在 ✅ 无遗留锁
      ps -ef | grep ... → 无输出（rc=1）⇒ 空闲 ✅
脚本 exit 0
```

本轮 F2 选项自检**通过**（`[info] 选项自检通过：tb_dir/all_opt 与 run_local.sh 逐字节一致`，未 exit 12）；
F4 锁正常获取并释放；F1 未出现任何 `[WARN] uvs.setup 还原到的是夹具值…`。

## 4 warning 明细（0 error / 17 warning，全为既有告警）

**段① rtl（13 条）**：`121687 Unknown Pragma Prefix` ×4、`121553 Use before declare` ×4、
`120002 Command option warning` ×3、`120428 Non standard gen block` ×2

**段② tb（4 条）**：`120002 Command option warning` ×3、`121147 Redefinition` ×1

> `Warning-121147: Redefinition` 位于既有 TB 文件 **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**
> （`set_rtc_rw` 定义于 `:799`，其形参 `bit [31:0] base_addr='h2000` 被 :802 的局部声明重定义、
> **该重定义被忽略**）。此告警在上一轮（v1/v2 沙箱用例）编译时**逐字相同** ⇒ 属 TB 既有告警，与本用例无关。
> RTL/TB 严格只读，runner 未做任何改动；是否影响语义由 checker 在 A3 判。

## 5 ⚠ 需 Lead 确认的一处基线口径差异：`TESTLIB` 内容 md5 不可复现

Lead 给的 `TESTLIB/` 内容 md5 基线为 `50b7669715d3e49d5b82db517939f935`。
我**用 15 种常见口径都无法复现**该值（**计数 162 则完全一致**）。实测值：

| 口径 | 实测 md5 |
|---|---|
| `md5sum TESTLIB/*.sv \| md5sum`（同为 `find -type f \| sort \| xargs md5sum`） | `5c479ec6f317f3308d18f5494e8c61d2` |
| `md5sum TESTLIB/*.sv \| sort \| md5sum` | `ce5c210c7495b0fbf1bd4a61b71335b4` |
| `cat TESTLIB/*.sv \| md5sum` | `c32455123d3468026837c4257a08872f` |
| `find TESTLIB -type f \| sort \| xargs md5sum \| md5sum` | `228e2d17369b6abd72766179463a428f` |
| `md5sum TESTLIB/*.sv \| md5sum`（`md5sum TESTLIB/*.sv \| md5sum`） | 同上 `5c479ec6…` |
| `ls -1 TESTLIB/*.sv \| sort \| md5sum`（仅路径） | `6626c3b65c9e36ef0c3f5d047bd59a40` |
| `find -printf '%s %p\n' \| sort \| md5sum` | `2441b99fcb7a34c43bbcf4656fb7031e` |
| `md5sum ... \| awk '{print $1}' \| md5sum` | `c43a7c3c767750819566144001c3c8b1` |
| `md5sum ... \| sort \| md5sum` | `ce5c210c7495b0fbf1bd4a61b71335b4` |

- **计数 `162` 完全一致** ⇒ 无文件增删；`git status --porcelain TESTLIB | wc -l` 跑前跑后同为 34；
  `find RTL TB PKG -newermt` 为空。故**本步未触碰 `TESTLIB/`** 这一结论有独立证据支撑，不受该 md5 口径影响。
- 差异原因**不确知**（可能是 Lead 取值时的口径/工作目录/文件名排序不同）。
- **给 Lead 的建议**：把 §8 的"内容 md5"基线**连口径一起写死**（例如统一为
  `find TESTLIB -maxdepth 1 -name '*.sv' | LC_ALL=C sort | xargs md5sum | md5sum`），
  否则该行不可独立复验（属"机制缺锚点"，不是本轮错误）。

## 6 写权与红线自查

- 本轮写出：`SIMLIB_RUN/log/*`、`SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/*`、本证据文件
  —— 均在 `task-9` 的 `writeScopes` 内（`doc/agents/_demo/accept/evidence`、`SIMLIB_RUN/log`、
  `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1`）✅
- **未**写入 `TESTLIB/`（无新增、无修改、无删除）；**未**修改用例、`RTL/`、`TB/`、`PKG/`、
  `compile_only.sh` ✅
- 串行：跑前跑后 `ps -ef` 均无并发；F4 锁已用并已释放 ✅
- 数字纪律：本文所有 md5 / 字节 / 行数 / 耗时 / 计数均由命令或工具输出直接复制，未手算 ✅

## 7 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv   # bc9cd56d…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
grep -n '\[PASS\]' SIMLIB_RUN/log/a2_compile_stdout.log
ls TESTLIB/*.sv | wc -l                     # 162
diff uvs.setup doc/_run_artifacts/uvs.setup.orig                        # rc=0
```
