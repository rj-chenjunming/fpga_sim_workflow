# A3'' 最终静态复验（v3）— D-10/D-11 + 夹带改动 + A4/A5 交接件

> **复核者**：`simenv-checker`（非作者）｜**任务**：`task-19`（rev 2，owner=simenv-checker）
> **复核时刻**：2026-10-14 14:24–14:27 +0800｜**引用 md5 于 2026-10-14 14:24:07 +0800 重取**
> **上游**：`ACCEPTANCE_PLAN.md` §2 A3/§5；上一轮 `review/A3b_review_v2.md`（`1978742b0fde97b1c3f6830a1b3c8335`，结论=退回）；`review/A3_review.md`（`999445d1a6fe7cbbd19ff5c1a4388707`，结论=退回）
> **唯一写权**：`doc/agents/_demo/accept/review/`（新文件，未覆盖前两件）｜未修改用例 / `RTL/` / `TB/` / `PKG/` / `TESTLIB/` / v1·v2 归档件
> **口径纪律**：只到**编译 + 静态**。本文件**不含任何功能级/时序级结论**；§6 的"预期观测点"是**全跑前的期望**，不是观测结果。
>
> # 结论（先行）
> # 通过
> **D-10 真消除**（"任何一次读超时，无论第几笔、`samples` 多少，都必然 `*E` + `` `uvm_error ``"成立，且**无重复报错**）；**D-11 改对**（`869/:875` → `870/:876`，残留 0 处）；**无夹带改动**（5 hunk / 14 行全部属 D-10/D-11，**代码逻辑仅 1 行**）；A2c 对账全绿。
> **★ 可以进入 A4 全跑** —— 背书与判据清单、A5 分流判据定稿、**预期观测点清单**见 **§6**（三者齐备，缺任一 A5 无法区分"断言真通过"与"断言根本没执行"）。

---

## 0 身份与引用（md5 重取 = 2026-10-14 14:24:07 +0800）

| 文件 | md5 | 字节/行 |
|---|---|---|
| **v3 用例**（被复核）`accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` | `235d20a5f2cc7b4911201c8939a14b81` | 44143 / 607 |
| **v2 归档**（只读）`doc/_run_artifacts/tc_dom_polling_trig_chk_01_v2.sv` | `e24aded26476aed9426576da361c0fa2` | 43922 / 605 |
| **v1 归档**（只读）`doc/_run_artifacts/tc_dom_polling_trig_chk_01_v1.sv` | `bc9cd56d4b361f4a5be028d8d24cfc56` | 37468 / 539 |
| v3 证据 `accept/evidence/A2c_compile_evidence_v3.md` | `4045540e4c3b79b7553f38d95ec7d9f5` | 10690 / 180 |
| v2 证据（应未覆盖）`accept/evidence/A2b_compile_evidence_v2.md` | `c087031ae0b571b2c96e749152acadbe` | — |
| v1 证据（应未覆盖）`accept/evidence/A2_compile_evidence.md` | `a09a9a8c7f02d1241d231172f756a12c` | — |
| **v3** rtl/tb 日志 `SIMLIB_RUN/log/tc_dom_polling_trig_chk_01_1_c_{rtl,tb}.log` | `9557d917e9bb6fb89fb2f868c9b94fdd` / `fc51a732e89b354eaffe26d01429ec93` | 86150 / 29201 |
| **v2 归档**日志 `SIMLIB_RUN/log/archive_a2b_v2/..._c_{rtl,tb}.log` | `04098ba8b3dfceb0f8d38987cbbcf283` / `bf92a8500f898586ffd89ba119c60fd8` | 86150 / 29201 |
| **v1 归档**日志 `SIMLIB_RUN/log/archive_a2_v1/..._c_{rtl,tb}.log` | `2f8ad76b58e9178f88db49e665bc74b0` / `73f9c6683c1f30744882109998e2eccf` | 86150 / 29201 |
| `SIMLIB_RUN/log/a2c_compile_stdout_v3.log` | （见 §5） | 114485 / 2105 |
| `TB/AGENTS/PCIE-Agent/pcie_sequence.sv` | `72b3b9808469bdc4603488f88b65b771` | — |
| `RTL/SRC/imports/SRC/dom_src/dom_i2c_data_ram.sv` | `8b29530dbe56ced329dc4c6cb4dbe5f3` | — |
| `doc/tools/compile_only.sh` | `4d7cf96c2e3acde11c46a5b15632bfa5` | — |
| `uvs.setup` / `doc/_run_artifacts/uvs.setup.orig` | `a80f7b6ca48a7961a107bbe871af761d`（相同） | — |
| `accept/ACCEPTANCE_PLAN.md` | `5d1b230241c9667a8296c7fe23bd2199` | — |

**diff 规模（我独立跑出）**：**5 个 hunk**、`<` **14** 行 / `>` **14** 行、**净 +2 行**（605 → 607）⇒ 与 Lead 转述的"5 hunk / 4 处 / 代码逻辑行只有 1 行"**一致** ✓

---

## 1 `diff` 原文（`diff v2归档 v3沙箱`，逐字复制，未编辑）

```diff
69,73c69,75
< //   O4 STA_SAMPLES_SHORT: 30ms 观测窗内有效采样数必须 >= MIN_SAMPLES(=3)
< //                      失败条件：任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回 ⇒ 提前结束采样，
< //                              有效样本数 < 3（总线/agent 卡住）。★ v2 对 A3 D-1 的整改：
< //                              v1 的 `samples==0` 在控制流上不可达（恒真式断言），已删除；
< //                              本判据**可达**（真实触发路径：读超时 ⇒ 提前结束采样）。
---
> //   O4 STA_SAMPLES_SHORT: 判据 = (有效采样数 >= MIN_SAMPLES(=3)) **且** (从未出现读超时)
> //                      失败条件（两选一即失败，v3 按 A3b D-10 恢复失败面）：
> //                        (i) 任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回（`rd_to_seen=1`）——
> //                            总线/agent 卡住；无论样本数多少都判失败；
> //                        (ii) 有效样本数 < 3。★ v2 对 A3 D-1 的整改：v1 的 `samples==0`
> //                            在控制流上不可达（恒真式断言），已删除；本判据**可达**
> //                            （真实触发路径 (i)：读超时 ⇒ 提前结束采样）。
154c156
< //         软界 —— pcie_sequence.sv:869/:875，到了也不报错，故障只能靠本兜底封顶）
---
> //         软界 —— pcie_sequence.sv:870/:876，到了也不报错，故障只能靠本兜底封顶）
441c443
<         //        软界 —— pcie_sequence.sv:869/:875，到了也不报错）⇒ 整段由 DONE_TIMEOUT_NS
---
>         //        软界 —— pcie_sequence.sv:870/:876，到了也不报错）⇒ 整段由 DONE_TIMEOUT_NS
539,543c541,545
<         // O4：有效采样数 < MIN_SAMPLES ⇒ 观测证据不足
<         //     怎样失败：任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回 ⇒ 提前结束采样，样本数 < 3
<         //     ★ v1 的 `if (samples == 0)` 在控制流上不可达（恒真式断言，A3 D-1），已删除；
<         //       本判据**可达**：唯一触发路径 = 采样循环里那一笔读超时（`rd_to_seen`）。
<         if (samples < MIN_SAMPLES) begin
---
>         // O4：出现读超时 **或** 有效采样数 < MIN_SAMPLES ⇒ 观测证据不足
>         //     怎样失败：(i) 任一采样读在 RD_TIMEOUT_NS(1ms) 内未返回（`rd_to_seen=1`，无论样本数
>         //     多少都判失败 —— A3b D-10：超时这条根因自己必须能触发双写）；(ii) 样本数 < 3。
>         //     ★ v1 的 `if (samples == 0)` 在控制流上不可达（恒真式断言，A3 D-1），已删除。
>         if ((samples < MIN_SAMPLES) || rd_to_seen) begin
545,546c547,548
<                       $sformatf("samples=%0d < MIN_SAMPLES=%0d in %0dms window (read_timeout_seen=%0b): insufficient observation evidence",
<                                 samples, MIN_SAMPLES, OBS_WINDOW_NS/1_000_000, rd_to_seen));
---
>                       $sformatf("read timeout seen=%0b / samples=%0d < MIN_SAMPLES=%0d in %0dms window: insufficient observation evidence",
>                                 rd_to_seen, samples, MIN_SAMPLES, OBS_WINDOW_NS/1_000_000));
```

**逐 hunk 归属**：hunk1 = **D-10**（头注释 O4 条目重写）；hunk2/3 = **D-11**（两处行号）；hunk4 = **D-10**（判据表达式 `|| rd_to_seen` + 注释）；hunk5 = **D-10**（失败文案把 `rd_to_seen` 提到首位）⇒ **5/5 hunk 全属 D-10/D-11，唯一代码逻辑改动是 `:545` 一行** ✓

---

## 2 事项 1 · D-10 是否真消除（逐行论证）

**作者采用【① `|| rd_to_seen`】方案**（非 ② 恢复 `fail_both`），故**不存在双重报错**：`grep 'STA_RD_TIMEOUT'` = **0 处** ✓（v2 里那条已被 v3 之前的版本删除，v3 未把它加回来）。

### 2.1 `rd_to_seen` 的赋值点与初始化（逐点）

| 行 | 内容 | 性质 |
|---|---|---|
| `:391` | `bit rd_to_seen;` | 声明（**task 内局部变量** = class 方法的自动变量，不跨调用残留） |
| `:507` | `rd_to_seen = 1'b0;` | **初始化**，位于观测块首（与 `samples=0` 等同一初始化组 `:502-510`），**在循环 `:513` 之前** ✓ |
| `:518` | `rd_to_seen = 1'b1;` | **唯一的置位点**，位于采样循环的超时分支内 ✓ |
| `:545` / `:548` / `:551` | 只读（判据 + 文案） | 无写入 ✓ |

⇒ **写入点恰 2 处**（1 处初始化 `:507` + 1 处置位 `:518`），**置位点唯一**（与作者所述 `:518` 一致）；**初始化在读取之前、在循环之前** ⇒ **不存在"上一轮遗留值导致误报"** ✓。

### 2.2 "任何一次读超时都必然 `*E` + `` `uvm_error ``"逐行论证

采样循环与判定（v3 `:502-552`）：

```
507:  rd_to_seen = 1'b0;                       // ① 先清零
511:  t0 = $time;
513:  while (($time - t0) < (OBS_WINDOW_NS * 1ns)) begin
514:      bmc_spi_rd_to(DOM0_I2C_STA_ADDR, v, to);      // 唯一采样读，1ms 超时兜底
515:      if (to) begin
518:          rd_to_seen = 1'b1;                          // ② 任一笔超时 ⇒ 置 1（不依赖 samples）
519:          break;                                       // ③ 结束采样
520:      end
522:      samples++;                                       // 成功才自增
534:  end
545:  if ((samples < MIN_SAMPLES) || rd_to_seen) begin     // ④ 超时 OR 样本不足
546:      fail_both("STA_SAMPLES_SHORT", DOM0_I2C_STA_ADDR, …)   // ⑤ 双写
549:  end else begin                                       // ⑥ 两支互斥 ⇒ 不重复报错
```

| # | 断言 | 论证 |
|---|---|---|
| ① | 超时发生在**第 1~3 笔**（`samples` 停在 0/1/2） | `:518` 置 1 ⇒ `:545` 左项已真 ⇒ `:546 fail_both` ⇒ **`*E` + `` `uvm_error ``** ✓ |
| ② | 超时发生在**第 4 笔及以后**（`samples ≥ 3`） | 由 `:545` 的**右项 `|| rd_to_seen`**（v3 新增）⇒ 仍进 `:546 fail_both` ⇒ **`*E` + `` `uvm_error ``** ✓ ← **这正是 D-10 的修复点** |
| ③ | 是否可能"超时但 `rd_to_seen` 未被置位" | 不可能：循环内**只有** `:514` 一笔读，其返回值只经 `:515 if (to)` 一条支路；`to=1` ⇒ `:518` 必执行 ⇒ `break` 前已置位 ✓ |
| ④ | 是否可能"未超时而 `rd_to_seen` 误为 1" | 不可能：`:507` 已清零，`:518` 是唯一置位点且仅在 `to=1` 内 ⇒ 无误报 ✓ |
| ⑤ | 双写是否真发生 | `fail_both`（`:339-342`）：`:340` `$display("chk_f *E DOM_TRIG_CHK %s @0x%08h: %s", …)` **且** `:341` `` `uvm_error("DOM_TRIG_CHK", …) `` ✓ |
| ⑥ | 是否变成双重报错（同一根因 2 条） | **否**：`:545` 是 `if/else` 二选一，`fail_both` 只在 `if` 支；且 `STA_RD_TIMEOUT` 已 0 处 ⇒ 一次超时**恰 1 条** `*E` + **恰 1 条** `` `uvm_error `` ✓ |

### 2.3 全用例"读/写超时"清单穷举（确认**无静默超时路径**）

| 通道/位置 | 超时兜底 | 超时后的报出 | 双写？ |
|---|---|---|---|
| 使能写 `:413`（BMC SPI） | `bmc_spi_wr_to` `#RD_TIMEOUT_NS` | `:417 fail_both("ENABLE_WR_TIMEOUT")` + return | ✓ |
| 使能读回 `:420`（BMC SPI） | `bmc_spi_rd_to` 同 | `:424 fail_both("ENABLE_RD_TIMEOUT")` + return | ✓ |
| **O2b 触发前读** `:455`（BMC SPI） | 同 | `:459 fail_both("STA_IDLE_RD_TIMEOUT")` + return | ✓ |
| **采样读** `:514`（BMC SPI） | 同 | `:518 rd_to_seen=1` → `:546 fail_both("STA_SAMPLES_SHORT")` | ✓（**v3 修复**） |
| PCIE `set_read/set_write`（`:475/:484/:485`） | **无内部超时** → 若卡住则子任务挂住 | 第三层 `fork : DONE_WAIT_FORK`（`:319-331`，超时支 `:322-329`）120ms 超时 ⇒ `:324 $display("chk_f *E … DONE_TIMEOUT …")` + `:326 uvm_error` | ✓ |
| 库调用 64 次（预置段 `:410-413`） | 库内只有**静默** 50ms 软界 | 同上第三层封顶 | ✓（`*E` 由 DONE 给出） |

⇒ **"任何一次读超时都会产生 `*E` + `` `uvm_error ``"成立**，D-10 彻底消除。

### 2.4 O5~O8 是否仍只嵌套在 `else` 内（"一条根因一条 `*E`"未被破坏）

```
545:      if ((samples < MIN_SAMPLES) || rd_to_seen) begin
546-548:      fail_both("STA_SAMPLES_SHORT", …)
549:      end else begin                     ← 只有"未超时 且 samples>=3"才进入
554-559:      O5 STA_RESERVED      (if hi_bad … else pass_note)
562-567:      O6 STA_ERR_CLEAR     (if err_seen … else pass_note)
571-577:      O7 STA_BUSY_SEEN     (if !seen_busy … else pass_note)
582-587:      O8 STA_CHANGED       (if !changed … else pass_note)
588:      end                                ← 关闭 else
```

**结论：结构零变化 ✓** —— 四个 `if` 缩进仍 +4，唯一收尾 `end` 在 `:588`（其后 `:590` 是 `uvm_info`/END 与 `:592 test_done`）。⇒ ①"超时/样本不足时 O5~O8 不裁决"保持不变；② 因 `:545` 是 if/else 互斥，**既未变成双重报错，也未放宽**（v2 的 `if` 支只有 `samples<3`，v3 的 `if` 支是 `samples<3 || 超时` ⇒ **失败面只增不减**）✓

---

## 3 事项 2 · D-11 是否改对

| 检查项 | 结论 | 依据 |
|---|---|---|
| 用例内 `869`/`875` 残留 | **0 处 ✓** | `grep -n '869\|875'` 于 v3 用例 → **无输出** |
| 改为 `870/:876` | **✓** | v3 `:156`（头注释超时推导）与 `:443`（预置段注释）均写 `pcie_sequence.sv:870/:876` |
| 该行号**确实指向** 50ms 静默软界 | **✓** | 我本机复核 `TB/AGENTS/PCIE-Agent/pcie_sequence.sv`：**`:870` = `while(pol_busy==0 && $time-t0<50ms) begin`**、**`:876` = `while(pol_busy==1 && $time-t0<50ms) begin`** —— 正是 `polling_data_chk` 的两条静默软界（`:869`/`:875` 是紧邻的 `t0 = $time;` 行，v2 引错） |
| 措辞澄清（供 A5） | 记录 | Lead 转述"确认该行号确实指向 `$display` 那两行"——**精确说**：它们指向两条 **`while(… && $time-t0<50ms)` 软界行**（软界的载体是 while 条件），而不是 `$display` 行（其体内 `:872`/`:878` 才是 `spi_mt.set_read`）。用例注释写的是"**静默** 50ms 软界 —— `:870/:876`"，与该行内容**语义一致** ✓ |

---

## 4 事项 3 · 有没有夹带改动

### 4.1 关键不变量（逐项复核，**全部零变化**）

| 不变量 | 结论 | 依据（v3 行号） |
|---|---|---|
| 闭环选型：`0x9c` / `0x80` / `0x403c` | **未动 ✓** | `:236-238` 偏移仍 `32'h9c` / `32'h80` / `32'h3c`；段基址 `:230-232` 仍 `0x0000` / `0x4000` / `0x0400` |
| 通道：`SPI_MST(2)` + `PCIE_SQR` + SPI 时序 | **未动 ✓** | `:218` `` `PCIE_SQR ``；`:406` `setTiming(160,240,240,400)`、`:408` `setMode(3)`、`:409` `setConfig(1,9)` —— 与 v2 逐字相同（均不在任何 hunk 内） |
| 三层超时结构 | **未动 ✓** | `:262` `RD_TIMEOUT_NS=1_000_000`、`:263` `SAMPLE_GAP_NS=3_000_000`、`:264` `OBS_WINDOW_NS=30_000_000`、`:265` `PRESET_BUDGET_NS=30_000_000`、`:266` `MIN_SAMPLES=3`、`:267` `DONE_TIMEOUT_NS=120_000_000` —— **六个值逐字未变**（v3 只改判据表达式与文案） |
| O2b 块 | **未动 ✓** | `:455-470` 区域不在任何 hunk 内；`grep 'STA_IDLE_BEFORE'` 仍出现（`:65`/`:465`/`:468`） |
| O4/O5~O8 结构 | **仅在 D-10 范围内变化 ✓** | O4 条件 `:545`（D-10）+ 文案 `:547`（D-10）；O5~O8（`:554-587`）与 else 收尾 `:588` **逐字未动** |
| 失败双写汇聚 | **仍成立 ✓** | 字面双写点 2 处：`:324`+`:326`（DONE 就地）、`:340`+`:341`（`fail_both` 体内）；`fail_both` 调用 **12 处**：`:417 / :424 / :431 / :459 / :465 / :480 / :490 / :546 / :555 / :563 / :572 / :583` ⇒ 12 + 1 = **13 个失败点全部双写** ✓；`uvm_warning` **0** 处 ✓ |
| 零写入范围 | **未扩大 ✓** | 写调用仍 2 处（SPI `0x9c`、PCIE `0x80`）；RO 的 `0x403c` 仍只读（`:455`/`:514`） |
| `PCIE_REG_RDCHK` / `set_rdchk` / `uvm_hdl_force` **代码**处数 | **0 / 0 / 0 ✓** | `grep` 仅命中**注释** `:45`（引日志原文）与 `:192`（说明不用 RDCHK 的理由）；`set_rdchk`、`uvm_hdl_force` 各 0 ✓ |
| 无裸 `wait` / 无固定延时收尾 | **未动 ✓** | 唯一 `wait(`（`:321`）在 `fork : DONE_WAIT_FORK`（`:319-331`）内带超时；`:300 #10us` 相位序；`:533` 节拍被 `:513` 硬界包围 |
| v1/v2 归档件、前两轮复核件、既有证据 | **未被改动 ✓** | v1 `bc9cd56d…`、v2 `e24aded2…`、`A3_review.md` `999445d1…`、`A3b_review_v2.md` `1978742b…`、`A2_compile_evidence.md` `a09a9a8c…`、`A2b_…_v2.md` `c087031a…`（A2c 证据 §6 亦自述一致，我抽查 v1/v2 归档 md5 无误） |

⇒ **24 个不变量零变化；5 个 hunk 全属 D-10/D-11；唯一代码逻辑行是 `:545` 的 `|| rd_to_seen`（失败面只增不减，未放宽）** ⇒ **无夹带改动，无断言弱化** ✓

---

## 5 A2c 对账

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 5.1 | v3 md5 与证据/Lead 一致 | **通过** | 我现取 `235d20a5f2cc7b4911201c8939a14b81` / 44143 / 607 = A2c 证据 `:20-22` = Lead 报值 ✓ |
| 5.2 | 两段 rc | **通过（脚本自报）** | `a2c_compile_stdout_v3.log:1303` `rc=0 耗时 1s`、`:2099` `rc=0 耗时 1s`、`:2101` `[PASS]` ✓ |
| 5.3 | 0 error 独立复核 | **通过** | `grep -cE 'Error-[0-9]+\|^ERROR'` → rtl **0**、tb **0**；`Compilation: 0 error(s), 13 warning(s)`（rtl）/ `0 error(s), 4 warning(s)`（tb）✓ |
| 5.4 | **本轮日志确为 v3 的**（字节数与 v1/v2 恒同，须内容指纹） | **通过（我独立复现三重指纹）** | ① md5：v3 `9557d917…`(rtl)/`fc51a732…`(tb) ≠ v2 归档 `04098ba8…`/`bf92a850…`；② `Compilation starts at`：v3 `14:23:00`/`14:23:01`（= A2c 的 run_id 起始时刻）vs v2 `14:13:52/54`、v1 `13:57:39/43`；③ 用例行号引用：v3 **205/207/208/209/210** ← v2 203/205-208 ← v1 173/175-178（**+2 / +30 步进**，与用例 605→607 行、539→605 行的净增一致）✓ |
| 5.5 | v1/v2 日志均被保全（未被原位覆盖） | **通过** | `archive_a2_v1/` 三件 md5 = `2f8ad76b…`/`73f9c668…`/`2c161176…`；`archive_a2b_v2/` 三件 = `04098ba8…`/`bf92a850…`/`0a00c163…` —— **与我前两轮复核时记录的 v1/v2 日志 md5 逐一相同** ✓ |
| 5.6 | `uvs.setup` 已还原 | **通过** | 现取 `uvs.setup` = 夹具 = `a80f7b6ca48a7961a107bbe871af761d`；`diff` rc=0；`.compile_only.lock` 不存在 ✓ |
| 5.7 | `TESTLIB/` 未被动 | **通过** | 我现测 `ls TESTLIB/*.sv \| wc -l` = **162**；`md5sum TESTLIB/*.sv \| LC_ALL=C sort \| md5sum` = **`4c0942ac419f67c6fdb391dd2083f0b3`**（= §8 基线，复现 ✓）；`TESTLIB/tc_dom_polling_trig_chk_01.sv` 不存在 ✓ |
| 5.8 | 归档只增不改 | **通过** | `compile_only.sh` `4d7cf96c…` ✓；v1/v2 证据与归档件未覆盖 ✓；`A3_review.md`/`A3b_review_v2.md` 未被覆盖 ✓ |

---

## 6 ★ 若通过 → A4/A5 交接件（三项，缺一不可）

### 6.1 明确背书：**可以进入 A4 全跑**

**背书的判据清单（逐项均已在本件复算）**：
1. **卡点 B（编译）**：A2c 两段 `rc=0`、两段日志 `0 error`（我独立复算）；两段日志经**内容指纹**证明是本轮 v3 重写（md5 不同 + `Compilation starts at` 14:23:0x + 用例行号 205/207-210 与 607 行一致）。
2. **卡点 C（静态）— 缺陷项全部关闭**：
   - D-1（恒真式 `samples==0`）→ A3' 已判真消除（本件 §2.3 的 `:545` 保留 `samples < MIN_SAMPLES` 支）；
   - D-2（采样不足误报为"状态未动"）→ A3' 已判真消除（O5~O8 嵌套于 `else`，本件 §2.4 复核结构零变化）；
   - **D-10（超时被静默吞掉）→ 本件判真消除**：`:545` 新增 `|| rd_to_seen`，**任何一次采样读超时（无论第几笔、`samples` 多少）都必然触发 `:546 fail_both` 的双写**（§2.2 逐行）；且 `STA_RD_TIMEOUT` 0 处 ⇒ **恰 1 条 `*E` + 1 条 `uvm_error`**，无重复报错；
   - D-3/D-4/D-5/D-6/D-8 → A3' 已判改到位；**D-11（行号）→ 本件判改对**（`:156`/`:443` = `:870/:876`，残留 0 处，且两行确为两条 `50ms` 静默软界）。
3. **红线与纪律**：地址全部 `<段基址>+<块内偏移>`；属性/复位值取自**位定义表**（`L537-546`/`L503`/`L1542-1547`），`i2c_sta.bit2` 未登记矛盾已按 `T1/T2` 登记并排除断言；`0x2000` 类通道矛盾已按 `T5` 登记；**13 个失败点全部 `*E` + `` `uvm_error `` 双写**；无裸 `wait`、无固定延时收尾、无 `uvm_warning` 代失败；三层超时结构完整。
4. **无夹带改动**：5/5 hunk 属 D-10/D-11，唯一代码逻辑行 `:545`（失败面只增不减）；24 项不变量零变化。

**边界（必须与结论分开写）**：本背书仅覆盖**编译期 + 静态判据可信**。v3 在仿真中的行为、样本数、`i2c_sta` 序列**完全未核**；功能结论必须由 **A4 全跑 + A5 两套口径对账**给出。

### 6.2 A5 对账分流判据（**最终版**，确认并定稿）

| 观测组合 | 判定 | 处置 |
|---|---|---|
| `*E` 计数 **> 0** 且 `UVM_ERROR` **> 0** | **用例断言失败**（`fail_both` 的 12 个点名判据之一，或 DONE_TIMEOUT） | 按 §6.3 定位到具体观测点名；再做 FAIL 三分类（1 用例错 / 2 文档错 / 3 RTL·环境） |
| `*E` 计数 **> 0** 且 `UVM_ERROR` **== 0** | **库数据检查抱怨**（`polling_data_chk` 对 polling 数据窗/golden 的比对失败，**只 `$display`**） | 按**分类 3（环境/数据）**登记并注明"**非** O1~O8 断言"；**不得**记成用例断言失败，**不得**据此改断言 |
| `*E` **== 0** 且 `UVM_ERROR` **> 0** | 须单独登记（本用例**不应出现**：13 个失败点全部双写） | 与报告 §7.1.1 的**正向**陷阱（UVM 有错而脚本计数 0）相反；须查 UVM 报告来源（如 UVM 自身/环境/其他 agent） |
| `*E` **== 0** 且 `UVM_ERROR` **== 0** | **不得直接判"通过"** —— 必须先用 §6.3 的**观测点清单**确认各断言**确实执行过** | 见 §6.3 的"执行性核对" |

**文本前缀判据（机械可执行）**：
- **用例侧**（双写）：`chk_f *E DOM_TRIG_CHK <NAME> @0x<ADDR>: <detail>`（`fail_both` 体的 `$display`，`pcie_sequence.sv` **不是**来源；本用例 `:340`）或 `chk_f *E DOM_TRIG_CHK DONE_TIMEOUT …`（`:324` 就地）；配套 `` `uvm_error("DOM_TRIG_CHK", …) ``（`:341`/`:326`）。
- **库侧**（仅 `*E` 文本）：`*E pcie_rtc[n] addr[..] num[..] rdata[..] != exp[..]`（`TB/AGENTS/PCIE-Agent/pcie_sequence.sv:924` 与 `:928`，均为 `$display`、**无 `uvm_error`**）。
- **本用例不会触达**但需认得：`pcie_sequence.sv:598`（`PCIE_REG_RDCHK` 内）、`:660`（`set_rdchk` 内）的 `*E` 出现在 **`UVM_INFO` 行内**（前缀含 `[PCIE_REG_RD@3DW]` / `[set_rdchk]`）；本用例代码 0 处调用这两者（§4.1）⇒ 若出现，应作为"环境/其他用例污染"线索单列。
- **注意反向陷阱（D-7）**：库侧 `*E` 会让**脚本口径 > 0** 而 **UVM 口径 = 0**，若只看 `*E` 计数就会把"库数据抱怨"误记成"用例断言失败"；反之若只看 UVM 就会漏掉库侧抱怨。**两套口径必须都记，并按上表分流。**

### 6.3 ★ 本用例「预期观测点清单」（供 A5 判"真通过 vs 没执行"）

**印记格式约定**：每条检查点有 3 种可能的日志形态——
- **通过印记**：`chk_s DOM_TRIG_CHK <NAME> @0x<ADDR>: <detail>`（`$display`，无 UVM 前缀）**且** `UVM_INFO … [DOM_TRIG_CHK] <NAME> @0x<ADDR>: <detail>`（`` `uvm_info `` 同内容）；
- **失败印记**：`chk_f *E DOM_TRIG_CHK <NAME> @0x<ADDR>: <detail>` + `UVM_ERROR … [DOM_TRIG_CHK] <NAME> @0x<ADDR>: <detail>`；
- **地址按 `%08h` 展开**：使能 `@0x0000009c`、触发 `@0x00000080`、观测 `@0x0000403c`。

**(A) 有通过印记的 9 个观测点（正常全跑应全部出现，各 1 条 `chk_s`）**

| # | 观测点（`<NAME>`） | 行 | 期望的通过印记文本（`chk_s` 形态） |
|---|---|---|---|
| O1 | `ENABLE_RDCHK` | `:434` | `chk_s DOM_TRIG_CHK ENABLE_RDCHK @0x0000009c: RD=0x000001ff == EXP=0x000001ff` |
| O2b | `STA_IDLE_BEFORE` | `:468` | `chk_s DOM_TRIG_CHK STA_IDLE_BEFORE @0x0000403c: pre-trigger i2c_sta=0x0000000? busy(bit1)=0 (idle, stale-1 excluded)` |
| O2 | `TRIG_BEFORE` | `:483` | `chk_s DOM_TRIG_CHK TRIG_BEFORE @0x00000080: pre-trigger RD=0x00000000 == EXP` |
| O3 | `TRIG_AFTER` | `:495` | `chk_s DOM_TRIG_CHK TRIG_AFTER @0x00000080: post-trigger RD=0x00000001 == EXP` |
| O4 | `STA_SAMPLES_SHORT` | `:550` | `chk_s DOM_TRIG_CHK STA_SAMPLES_SHORT @0x0000403c: samples=N >= MIN_SAMPLES=3 (read_timeout_seen=0)` |
| O5 | `STA_RESERVED` | `:558` | `chk_s DOM_TRIG_CHK STA_RESERVED @0x0000403c: all samples bits[31:3] == 0` |
| O6 | `STA_ERR_CLEAR` | `:566` | `chk_s DOM_TRIG_CHK STA_ERR_CLEAR @0x0000403c: err(bit0) never set in the window` |
| O7 | `STA_BUSY_SEEN` | `:576` | `chk_s DOM_TRIG_CHK STA_BUSY_SEEN @0x0000403c: busy(bit1)==1 observed at least once` |
| O8 | `STA_CHANGED` | `:586` | `chk_s DOM_TRIG_CHK STA_CHANGED @0x0000403c: value changed across N samples` |

**(B) 默认静默的 4 个失败点（通过时**不**打印任何行；只在失败时出现 `chk_f *E`）**

| # | 观测点 | 行 | 触发条件 |
|---|---|---|---|
| — | `ENABLE_WR_TIMEOUT` | `:417` | 使能写 BMCS SPI 1ms 未返回 |
| — | `ENABLE_RD_TIMEOUT` | `:424` | 使能读回 1ms 未返回 |
| — | `STA_IDLE_RD_TIMEOUT` | `:459` | O2b 的前置读 1ms 未返回 |
| — | `DONE_TIMEOUT` | `:324`（就地） | 120ms 内 `test_done` 未置位 |

**(C) 过程性印记（不属判定，但用于交叉核对）**

| 印记 | 位置 | 形态 | 用途 |
|---|---|---|---|
| BEGIN | `:400` | `UVM_INFO … [DOM_TRIG_CHK_CTRL_0] BEGIN: DOM ctrl0 seg 0x00004000 block 0x00004000; enable@0x0000009c, trigger@0x00000080, sta@0x0000403c` | 证明子任务**已启动**、地址与用例一致 |
| 采样逐笔 | `:529`（`$display`）/`:528`（`uvm_info`） | `chk_i DOM_TRIG_CHK sample#N @<time>: i2c_sta=0x0000000?` / `[DOM_TRIG_CHK_CTRL_0] sample#N @<time>: i2c_sta=0x0000000? (busy=b err=b)` | **采样确实发生**；行数应与 O4 的 `N` 相等（期望 ≈10，参照日志节拍 3.012ms） |
| END | `:590` | `UVM_INFO … [DOM_TRIG_CHK_CTRL_0] END pid=0: samples=N seen_busy=b err_seen=b changed=b hi_bad=b` | **子任务走完至 `test_done` 收敛点**（`:592`）；其五个变量可与 O4~O8 的结论交叉核对 |

**(D) "断言真通过 vs 根本没执行"的判别规则（A5 必须执行）**

1. **O4 走 `chk_f`（失败）时**：`:545` 的 `if` 支成立 ⇒ **O5~O8 的 4 条 `chk_s` 必然缺席**（结构决定，§2.4）。此时**不得**把"未见 O5~O8 报错"读成"它们通过了"——它们**根本没执行**。此时 `END` 行仍应出现（`:590` 在分支之外）。
2. **O4 走 `chk_s`（`read_timeout_seen=0` 且 `samples≥3`）时**：**O5~O8 的 4 条 `chk_s` 必须全部出现**；缺任一条 ⇒ 视为"该断言未执行 / 日志被截断"，**单独登记，不得算通过**。
3. **三向交叉核对**：`grep -c 'chk_i DOM_TRIG_CHK sample#'` 应等于 O4 的 `samples=N` 与 `END` 行的 `samples=N`；`END` 行的 `seen_busy/err_seen/changed/hi_bad` 应与 O7/O6/O8/O5 的结论一致（如 `err_seen=0` 对应 O6 通过）。
4. **O2b 的存在性检查**：`STA_IDLE_BEFORE` 的 `chk_s`/`chk_f` 必须存在（它是 v2 新增判据）；**只出现 `STA_IDLE_RD_TIMEOUT` 而无 `STA_IDLE_BEFORE`** ⇒ 说明前置读超时提前 `return`（`:459-461`），此时 O2/O3/O4~O8 **全部未执行**，须按"前置失败"上报而非"其余通过"。

---

## 7 未在本机复算的量（诚实清单）

| 量 | 为什么未复算 | 核到什么程度 |
|---|---|---|
| 两段 `uvlan` 的 **rc=0 本身** | 重跑会写 `SIMLIB_RUN/`（runner 写权） | 脚本自报（`:1303/:2099`）+ 两段日志 0 error + `[PASS]` 行含 v3 md5 + 三重内容指纹 ⇒ **多方一致**；**不称"已复核 rc"** |
| v3 在仿真中的**行为/时序/样本数/`i2c_sta` 序列** | 本轮只编译 | **完全未核**；§6.3 的"期望 ≈10 个样本"是**静态推算**（30ms ÷ 3.012ms），不是本次观测 |
| 30ms / 120ms 阈值在本用例下的充分性 | 需全跑 | 沿用 A3/A3' 的静态论证（上界和 ≈79ms < 120ms；BUSY 首现 9.047ms < 30ms，取自参照日志 `LOG/tc_dom_polling_new_01_1_run.log`） |

---

## 8 判定

| 事项 | 结论 |
|---|---|
| **D-10** 是否真消除 | **是** —— `rd_to_seen` 写入恰 2 处（初始化 `:507` + 唯一置位 `:518`，均在循环前/循环内，无滞留值）；`:545 if ((samples < MIN_SAMPLES) \|\| rd_to_seen)` ⇒ **任何一次采样读超时（无论第几笔、`samples` 多少）都必然 `fail_both` 双写**；`STA_RD_TIMEOUT` 0 处 ⇒ **无双重报错**；O5~O8 仍只嵌套在 `else`（`:549-588`）内，"一条根因一条 `*E`"未破坏 |
| **D-11** 是否改对 | **是** —— `:156`/`:443` = `:870/:876`（我核该两行确为 `while(pol_busy==… && $time-t0<50ms)` 两条静默软界），残留 `869`/`875` = **0 处** |
| 夹带改动 | **无** —— 5/5 hunk 属 D-10/D-11；唯一代码逻辑行 `:545`（失败面只增不减）；24 项不变量（地址/通道/三层超时/O2b/O5~O8 结构/双写汇聚/零写入/RDCHK·rdchk·force 代码 0 处）**全部零变化** |
| A2c 对账 | **全绿**（md5 一致、两段 rc=0、0 error 独立复核、**三重内容指纹证明日志为本轮 v3**、v1/v2 日志均保全、`uvs.setup` 已还原、TESTLIB 162 与 `4c0942ac…` 均复现、归档只增不改） |
| §6 交接件 | **已齐备** —— ① A4 背书 + 判据清单；② A5 分流判据定稿；③ 预期观测点清单（9 条通过印记 + 4 条默认静默 + 3 类过程印记 + 4 条执行性判别规则） |

---

# 结论：**通过**

**理由**：v3 对 v2 只做了 **5 个 hunk**（D-10 的判据/注释 + D-11 的两处行号），其中**唯一代码逻辑改动**是把 `:545` 的判据补成 `if ((samples < MIN_SAMPLES) || rd_to_seen)` —— 经**逐行控制流论证**，该改动使**任何一次采样读超时，不论发生在第几笔、已累计多少个样本，都必然经 `fail_both` 产生 `*E` 文本 + `` `uvm_error ``**（A3b 的 D-10 彻底消除），同时因 if/else 互斥且 `STA_RD_TIMEOUT` 已 0 处而**不产生双重报错**；O5~O8 仍严格只嵌套在 `else` 内，未破坏"一条根因一条 `*E`"，也**未放宽任何断言**。D-11 的两处行号已改为 `:870/:876` 且残留为 0。逐 hunk 核查确认**无任何超范围夹带改动**，地址 / 通道 / 三层超时 / O2b / O5~O8 结构 / 13 个失败点的双写汇聚**全部零变化**。A2c 对账全绿，且本轮编译日志经**三重内容指纹**（md5、`Compilation starts at`、随用例行数变化的行号引用）证明确为 v3 重写。

**据此，我给出明确背书：`tc_dom_polling_trig_chk_01` v3（md5 `235d20a5f2cc7b4911201c8939a14b81`）可以进入 A4 全跑。** 依据见 §6.1 的判据清单。
**同时交付 A5 两项输入**：**分流判据定稿**（§6.2，两套口径必须都记并按前缀分流）与**预期观测点清单**（§6.3，含 9 条通过印记、4 条默认静默、3 类过程印记、以及"断言真通过 vs 根本没执行"的 4 条判别规则）。

**口径边界（重申，不得混写）**：本"通过"仅覆盖**编译期 + 静态判据可信**。它**不是**功能/时序结论；v3 是否真能跑出结果、`i2c_sta` 序列是否如预期，必须由 **A4 全跑**产出完整日志（含 `UVM Report Summary`）后，由 **A5** 按两套口径与 §6.3 的观测点清单对账给出。若 A4/A5 出现 FAIL，按 `ACCEPTANCE_PLAN.md` §6 三分类处理并附证据行号。

---
*本文件由 `simenv-checker`（非作者）产出，落在唯一写权 `doc/agents/_demo/accept/review/`。未修改用例 / `RTL/` / `TB/` / `PKG/` / `TESTLIB/` / v1·v2 归档件 / 前两轮复核件。所有 md5、行数、计数与日志原文均由命令输出复制，未手算。*
