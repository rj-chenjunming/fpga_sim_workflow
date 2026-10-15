# A2f 编译证据 —— v6（卡点 B · 只编译 · 第 6 次重采）

> **结论：编译通过（卡点 B）** —— 两段 `uvlan` 均 rc=0，两段日志 0 error。
> **口径纪律**：本次**只编译、未仿真**。本文件不含任何"用例通过 / 功能正确"字样 ——
> 编译通过只证明"语法 / 宏展开 / 包依赖 / 端口连接无编译期错误"，**不等于**功能正确（功能判定属 A4/A5）。
>
> **为什么重采**：v1~v5 的 A2/A2b/A2c/A2d/A2e 证据**不得复用**给 v6（`8ad474be…`）。
> 上游规格：`doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` §2 A2 + §3 + §4。

---

## 1 证据字段（task-27 要求逐项）

| 字段 | 值 |
|---|---|
| `run_id` | `20261014-A2f-01` |
| 时刻 | 段① `15:27:53` → 段② `15:27:55` → 结束 `2026-10-14 15:27:56`（日志内 `Compilation starts at` + job stdout 观测） |
| 用例名 | `tc_dom_polling_trig_chk_01` |
| 用例路径 | `doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **v6 md5** | `8ad474be7928496487517a8666691d78` |
| **v6 字节** | `51228` |
| **v6 行数** | `673` |
| 与 Lead 报值比对 | **一致** ✅（Lead 消息给 `8ad474be7928496487517a8666691d78` / 51228 B / 673 行） |
| ⚠ 中间态说明 | task-27 正文仍写作者的中间态 `bcb431f7ec5775126c23bdf652a29ba9` / 51192 B / 673 行；**磁盘现值与 Lead 消息的 `8ad474be…` 一致**，本轮按 Lead 消息口径复核通过（见 §5 观察 1） |
| v6 md5 跑后复查 | `8ad474be7928496487517a8666691d78`（与跑前相同 ⇒ 无移动靶）✅ |
| 命令原文 | `./doc/tools/compile_only.sh -c tc_dom_polling_trig_chk_01 -f doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` |
| **段① rc** | **0** |
| **段② rc** | **0** |
| **段① 耗时** | 脚本自报 `耗时 2s`（工具自报 `Elapsed time: 1.31s, CPU time: 1.30s`） |
| **段② 耗时** | 脚本自报 `耗时 1s`（工具自报 `Elapsed time: 0.80s, CPU time: 0.80s`） |
| 脚本退出码 | **0** |
| 日志① rtl | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log` —— `86150` 字节 / `1295` 行 |
| 日志② tb | `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log` —— `29201` 字节 / `795` 行 |
| 脚本全程 stdout | `SIMLIB_RUN/log/a2f_compile_stdout_v6.log` —— `114485` 字节 / `2105` 行 |
| warning 计数 | 段① **13** 条；段② **4** 条（error 均为 0） |
| 首个 error 行 | **N/A（0 error）** |
| 编译库 | `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}` |
| 脚本 md5 | `4d7cf96c2e3acde11c46a5b15632bfa5` |

### 六代身份沿革（新证的理由）

| 轮次 | md5 | 字节 | 行数 |
|---|---|---|---|
| v1 | `bc9cd56d4b361f4a5be028d8d24cfc56` | 37468 | 539 |
| v2 | `e24aded26476aed9426576da361c0fa2` | 43922 | 605 |
| v3 | `235d20a5f2cc7b4911201c8939a14b81` | 44143 | 607 |
| v4 | `33cc907f7f03a930185ecfadaaadd7e0` | 47468 | 636 |
| v5 | `14ed595ad25601a1efc277aa6fe7bb89` | 50067 | 664 |
| **v6** | **`8ad474be7928496487517a8666691d78`** | **51228** | **673** |

### `[PASS]` 行原文（引述脚本自身输出）

```
=========== [PASS] 卡点 B 通过：两段编译均成功 ===========
用例      : doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv  (md5 8ad474be7928496487517a8666691d78)
库        : SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/{rtl,tb}
日志      : SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
```

### 判定依据（task-27 口径）

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

## 2 ★★ 串行确认（三信号，**不用 `ps`**）—— 跑前跑后各一次

| 信号 | 跑前 | 跑后 | 判读 |
|---|---|---|---|
| ① `md5sum uvs.setup` 是否 == 夹具 `a80f7b6ca48a7961a107bbe871af761d` | **== 夹具** | **== 夹具**（`diff` rc=0） | ✅ 无脚本存活（`trap` 只在退出时还原） |
| ② `SIMLIB_RUN/wave/<tc>_1/*.usdb` mtime 是否滚动 | t0 `1791962080` / t0+6s `1791962080` ⇒ **未滚动** | t0 `1791962080` / t0+5s `1791962080` ⇒ **未滚动** | ✅ 无仿真在跑 |
| ③ `SIMLIB_RUN/.compile_only.lock` 是否存在 | **不存在** | **不存在** | ✅ 无并发 compile_only |

> `ps` 结果**未作为判据**（沙箱 PID 命名空间下不可靠，Lead 已修正口径）。

## 3 ★★ 内容指纹：证明日志是本轮 v6 重写（**不看字节数/mtime**）

**陷阱第 6 次出现**：v1~**v6** 六轮编译日志**字节数完全相同**（rtl 恒 `86150`、tb 恒 `29201`）——
**只比大小必然误判**。故给出三重**内容指纹**：

| 指纹 | 本轮 **v6** | 归档 **v5**（`archive_a2e_v5/`） | 归档 **v4**（`archive_a2d_v4/`） | 归档 **v2**（`archive_a2b_v2/`） |
|---|---|---|---|---|
| ① `Compilation starts at`（rtl / tb） | **15:27:53 / 15:27:55** | 15:19:23 / 15:19:24 | 14:47:06 / 14:47:07 | 14:13:52 / 14:13:54 |
| ② 日志内引用用例的**行号** | **244 / 246 / 247 / 248 / 249** | 236 / 238 / 239 / 240 / 241 | 226 / 228 / 229 / 230 / 231 | 203 / 205 / 206 / 207 / 208 |
| ③ 与本轮日志 `diff` 行数 | — | c_tb **48 行**、c_rtl **8 行** | c_tb **48 行**、c_rtl **8 行** | c_tb **48 行**、c_rtl **8 行** |
| 文件字节数（**仅供参考，非判据**） | 86150 / 29201 | 86150 / 29201 | 86150 / 29201 | 86150 / 29201 |

（v3 指纹见 `A2c_compile_evidence_v3.md`：`14:23:00/01` + 行号 `205/207/208/209/210`；v3 日志原件已被 A4 全跑清理。）

- ② 的行号**随用例行数变化**（539 → 605 → 607 → 636 → 664 → **673** 行 ⇒ 173x → 203x → 205x → 226x → 236x → **244x**），是 v6 专属指纹 ✅
- ① 的时刻与本轮 `run_id` 起始时刻（`15:27:53`）吻合 ✅
- ⇒ 两段日志均为**本轮真实重写**，**不是复用任何旧日志**。

**v6 日志已另存副本**（Lead 指定动作；延续"每轮编译后立即归档"惯例）：

```
SIMLIB_RUN/log/archive_a2f_v6/ tc_dom_polling_trig_chk_01_1_c_rtl.log  d311a072198ff946ca3023800dcb9577  86150 B
SIMLIB_RUN/log/archive_a2f_v6/ tc_dom_polling_trig_chk_01_1_c_tb.log   1e1bce78bb07847d83400b7e07101b26  29201 B
SIMLIB_RUN/log/archive_a2f_v6/ a2f_compile_stdout_v6.log               a3112b1e3bddc06ac6fad5f1fa7fb548 114485 B
```

## 4 `TESTLIB/` 口径 A 摘要（§3 硬纪律：本步绝对不动 `TESTLIB/`）

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

## 5 ⚠ 一条需 Lead 知晓的观察（非本步错误）

**用例身份在派发过程中出现过两套数字**：task-27 正文写作者中间态 `bcb431f7…` / 51192 B；
Lead 的消息更正为 `8ad474be…` / 51228 B / 673 行。**磁盘现值 = `8ad474be…` / 51228 B / 673 行**，
与 Lead 消息一致 ⇒ 本轮判定以 `8ad474be…` 为准，复核通过。
建议：把任务正文的 md5 也同步更正，避免后续轮次再按正文口径误判为"移动靶"。

## 6 warning 明细（0 error / 17 warning，全为既有告警）

**段① rtl（13 条）**：`121687 Unknown Pragma Prefix` ×4、`121553 Use before declare` ×4、
`120002 Command option warning` ×3、`120428 Non standard gen block` ×2

**段② tb（4 条）**：`120002 Command option warning` ×3、`121147 Redefinition` ×1

> `Warning-121147: Redefinition` 位于既有 TB 文件 **`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:802`**
> （`set_rtc_rw` 定义于 `:799`）。该告警在 v1~v6 六轮编译中**逐字相同** ⇒ TB 既有告警，与本用例无关。
> RTL/TB 只读，runner 未做任何改动。

## 7 归档完整性（A6 会核）

| 文件 | 状态 |
|---|---|
| `evidence/A2_compile_evidence.md`（v1） | **未被覆盖** ✅ md5 仍 `a09a9a8c7f02d1241d231172f756a12c` |
| `evidence/A2b_compile_evidence_v2.md`（v2） | **未被覆盖** ✅ md5 仍 `c087031ae0b571b2c96e749152acadbe` |
| `evidence/A2c_compile_evidence_v3.md`（v3） | **未被覆盖** ✅ md5 仍 `4045540e4c3b79b7553f38d95ec7d9f5` |
| `evidence/A2d_compile_evidence_v4.md`（v4） | **未被覆盖** ✅ md5 仍 `cda582b9ca2c6f883733ba6c7bb72889` |
| `evidence/A2e_compile_evidence_v5.md`（v5） | **未被覆盖** ✅ md5 仍 `5d3d497733ae7a091e2b3b913ca8f9c1` |
| `doc/_run_artifacts/…_v1..v5.sv` | **未被改动** ✅ md5 依次 `bc9cd56d…` / `e24aded2…` / `235d20a5…` / `33cc907f…` / `14ed595a…` |
| `doc/tools/compile_only.sh` | **未被改动** ✅ `4d7cf96c2e3acde11c46a5b15632bfa5` |
| 本文件 | 新增（只增不改） |

## 8 写权与红线自查

- 本轮写出：`SIMLIB_RUN/log/*`（含 `archive_a2f_v6/` 副本、`a2f_compile_stdout_v6.log`）、
  `SIMLIB_RUN/tc_dom_polling_trig_chk_01_1/*`、本证据文件 —— 均在 `task-27` 的 `writeScopes` 内 ✅
- **未**写入 `TESTLIB/`；**未**修改用例、v1~v5 归档件、既有五份证据文件、Lead 的 A4 产物、
  `RTL/`、`TB/`、`PKG/`、`compile_only.sh` ✅
- 串行：跑前跑后**三信号**均判空闲；F4 锁已用并已释放 ✅
- 数字纪律：本文所有 md5 / 字节 / 行数 / 耗时 / 计数均由命令或工具输出直接复制，未手算 ✅

## 9 复核用命令（可原样重放）

```bash
cd /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
md5sum doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv      # 8ad474be…
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_rtl.log   # 0
grep -cE 'Error-[0-9]+|^ERROR' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log    # 0
grep -E 'Compilation:' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log
grep -n '\[PASS\]' SIMLIB_RUN/log/a2f_compile_stdout_v6.log
# 三信号串行确认（替代 ps）
md5sum uvs.setup doc/_run_artifacts/uvs.setup.orig   # 两者应相同
ls -d SIMLIB_RUN/.compile_only.lock                  # 应不存在
stat -c%Y SIMLIB_RUN/wave/tc_dom_polling_trig_chk_01_1/tc_dom_polling_trig_chk_01_1.usdb; sleep 5; stat -c%Y ...   # 两次应相同
# 内容指纹（不看字节数）
grep -h 'Compilation starts at' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log   # 15:27:53 / 15:27:55
grep -oE 'tc_dom_polling_trig_chk_01\.sv, [0-9]+' SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log | sort -u  # 244/246-249
diff SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_tb.log SIMLIB_RUN/log/archive_a2e_v5/tc_dom_polling_trig_chk_01_1_c_tb.log | wc -l  # 48
ls TESTLIB/*.sv | wc -l                                        # 162
md5sum TESTLIB/*.sv | LC_ALL=C sort | md5sum                   # 4c0942ac419f67c6fdb391dd2083f0b3
```
