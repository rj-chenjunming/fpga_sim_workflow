# T4 基线快照（guardian · 只读准备）

- 角色：`simenv-guardian`（证据与回归守护）
- 共享任务：`task-4`（rev=2，`blockedBy=["task-3"]`，`ready=false`）
- 状态：**只读准备阶段**（未 claim；不写任何生产件；唯一写权目录 `doc/agents/_demo/guard/`）
- 快照时刻：`2026-10-13 17:50 ~ 17:53 +0800`（会话内实测）
- 宿主 / 工作目录：`s24` / `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES`
- 数字纪律：本文所有数字**逐字复制自命令输出**，无一处手算。

> **为什么先建基线**：冻结纪律（`doc/AGENTS.md` §4）要求"防移动靶"。
> 若等到审计时才取数，**"改前"与"改后"就无从区分**——守护者必须先有锚点，再有结论。

---

## 1 冻结件：`uvs.setup` 与 `uvs.setup.orig`

```
$ md5sum uvs.setup doc/_run_artifacts/uvs.setup.orig
a80f7b6ca48a7961a107bbe871af761d  uvs.setup
a80f7b6ca48a7961a107bbe871af761d  doc/_run_artifacts/uvs.setup.orig

$ diff uvs.setup doc/_run_artifacts/uvs.setup.orig ; echo "diff_rc=$?"
diff_rc=0

$ stat -c'%s %y %n' doc/_run_artifacts/uvs.setup.orig uvs.setup
1071 2026-10-10 10:58:47.250001963 +0800 doc/_run_artifacts/uvs.setup.orig
1071 2026-10-10 10:58:47.250001963 +0800 uvs.setup
```

**基线结论（此刻成立）**：两者 **md5 相同**（`a80f7b6c…`）、**均 1071 字节**、**mtime 逐纳秒相同**（`10:58:47.250001963`）⇒ 就"当前值 == 当前备份"而言，一致性成立。

**⚠ 但该一致性证明力有限（本快照的第二个发现，与 task-2/3 无关，纯基线可查）**——见 §6。此处的 `a80f7b6c…`
可能被 `compile_only.sh:51` **覆写**，因此它只是"**本快照时刻的值**"，**不是不可变夹具**。

---

## 2 `LOG/` 历史文件基线

```
$ stat -c'%s %y %n' LOG/tc_dom_polling_new_01_1_run.log
220150 2026-10-10 10:58:46.208001995 +0800 LOG/tc_dom_polling_new_01_1_run.log
```
与角色/队长给的基线（**220150 字节 / 10-10 10:58**）**逐字一致** ✅

```
$ ls LOG/ | wc -l
78
$ find LOG -type f | wc -l
78
```
（`ls` 计数 == `find -type f` 计数 ⇒ `LOG/` 下无子目录，78 个条目全是普通文件）

**全量内容哈希清单（防"只按 mtime 判未改动"，§4 第 3 条）**：
`doc/agents/_demo/guard/T4_baseline_LOG_md5.txt`（82 行 = 4 行表头 + 78 行数据；每行 `md5 字节 mtime 路径`）

```
$ wc -l < doc/agents/_demo/guard/T4_baseline_LOG_md5.txt
82
$ sha256sum doc/agents/_demo/guard/T4_baseline_LOG_md5.txt
61feaf2ef1f80e9cd22d942d54df368ec67e98c0c465b77cccd05040cac41c50
$ md5sum LOG/tc_dom_polling_new_01_1_run.log
09a37ea22341d33ec62ba2672c6b5789  LOG/tc_dom_polling_new_01_1_run.log
```

---

## 3 `SIMLIB_RUN/` 相关基线（task-2 的写权范围，必须"改前"取证）

```
$ ls -la SIMLIB_RUN/
log/            （2 项）
tc_dom_polling_new_01_1/
wave/
$ find SIMLIB_RUN -mindepth 1 -maxdepth 1 -type d | wc -l
3

$ ls -la SIMLIB_RUN/log/
-rw-rw-r-- 1 chenjunming chenjunming 219341 Oct 10 14:33 tc_dom_polling_new_01_1_run.log
$ md5sum SIMLIB_RUN/log/tc_dom_polling_new_01_1_run.log
e67e485bbeff4c3facc1655883ad8bd1  SIMLIB_RUN/log/tc_dom_polling_new_01_1_run.log
$ stat -c'%s %y %n' SIMLIB_RUN/log/tc_dom_polling_new_01_1_run.log
219341 2026-10-10 14:33:54.480606281 +0800 SIMLIB_RUN/log/tc_dom_polling_new_01_1_run.log

$ ls -d SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1
ls: cannot access 'SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1': No such file or directory   ← task-2 目标库改前"不存在"
```

**task-2 跑完后我要核的三条（写进 T4_guard.md 的判据，现在先冻结）**：
1. §2 的 78 个 `LOG/` 文件 **md5 逐行比对 `T4_baseline_LOG_md5.txt`**（不是比 mtime）；
2. `SIMLIB_RUN/log/` 新增的只能是与 `tc_rtc_blk_reset_chk_01` 相关的文件，且
   `tc_dom_polling_new_01_1_run.log` 的 md5 仍须为 `e67e485b…`（219341 字节）；
3. `uvs.setup` 仍须为 `a80f7b6c…`（1071 字节）。

---

## 4 工作树与演示目录基线

```
$ git status --short | wc -l
49
$ git status --short | grep -c '^ M'
18
$ git status --short | grep '^??'          （30 条，逐字如下）
?? .uvs_lsp.sh
?? LOG/
?? RTL/
?? SIMLIB/
?? SIMLIB_RUN/
?? TESTLIB/tc_dom_polling_new_01_sts.sv
?? TESTLIB/tc_dom_polling_new_03_2_yuan.sv
?? TESTLIB/tc_dom_polling_new_03yuan.sv
?? TESTLIB/tc_dom_polling_new_04_1bf.sv
?? TESTLIB/tc_dom_polling_new_04yuan.sv
?? TESTLIB/tc_dom_polling_new_07_2.sv
?? TESTLIB/tc_dom_polling_new_10_yuan.sv
?? TESTLIB/tc_dom_rtc_01_tst.sv
?? TESTLIB/tc_dom_rtc_06_tst.sv
?? TESTLIB/tc_dom_rtc_08_yuan.sv
?? TESTLIB/tc_rtc_01_tst.sv
?? TESTLIB/tc_rtc_06_2_yuan.sv
?? TESTLIB/tc_rtc_08yuan.sv
?? TESTLIB/tc_rtc_09_yuan.sv
?? TESTLIB/tc_uart_01_test01.sv
?? TESTLIB/tc_uart_cts_test.sv
?? TESTLIB/tc_uart_cts_tst.sv
?? TESTLIB/tc_uart_rst_01_2.sv
?? TESTLIB_yuan/
?? check_runsim.log
?? cmem.txt
?? doc/
?? run_wave
?? tc_list1
?? tr_db.log
?? uvs.setup
```

**`git status --short | grep -c '^ M'` = 18**，逐字如下（`M` = 已跟踪文件被改；本演示**不得新增**第 19 条）：

```
 M TB/top_pkg.sv
 M TESTLIB/tc_bmc_i2c_01.sv
 M TESTLIB/tc_bmc_i2c_02.sv
 M TESTLIB/tc_bmc_i2c_03.sv
 M TESTLIB/tc_bmc_i2c_04_dfx.sv
 M TESTLIB/tc_bmc_spi_01.sv
 M TESTLIB/tc_bmc_spi_02.sv
 M TESTLIB/tc_bmc_spi_03.sv
 M TESTLIB/tc_bmc_spi_04_dfx.sv
 M TESTLIB/tc_cpu_i2c_01.sv
 M TESTLIB/tc_cpu_i2c_02.sv
 M TESTLIB/tc_cpu_i2c_03.sv
 M TESTLIB/tc_cpu_i2c_04_dfx.sv
 M TESTLIB/tc_pcie_rw_02.sv
 M TESTLIB/tc_pcie_rw_03_dfx.sv
 M TESTLIB/tc_pcie_rw_04_seu.sv
 M TESTLIB/tc_pcie_rw_06_bram_inject.sv
 M run_tc.py
```

> **注意（对本演示的约束）**：`?? doc/` 表示**整个 `doc/` 未被 git 跟踪**——本演示的全部产物
> （`doc/agents/_demo/**`、`doc/tools/compile_only.sh`）都**不在 git 版本控制下**，
> 因此 `git status` **无法**为它们提供任何"零改动"证据，**只能靠内容 md5**。这直接抬高了
> §1/§3 的 md5 要求：本演示没有 git 兜底。

```
$ ls -d doc/agents/_demo/*
doc/agents/_demo/evidence
doc/agents/_demo/guard
doc/agents/_demo/review
doc/agents/_demo/TESTLIB_sandbox

（快照时刻）find doc/agents/_demo -type f → 空；evidence/ review/ TESTLIB_sandbox/ 均为空目录
```

---

## 5 治理件 md5 基线（我的证据链锚点本身也要冻结）

```
$ md5sum doc/AGENTS.md doc/agents/sim-env-回归守护.md doc/agents/sim-env-用例作者.md \
         doc/agents/sim-env-用例执行.md doc/agents/sim-env-用例检查.md \
         doc/tools/compile_only.sh doc/tools/run_local.sh run_uvs_new.sh uvs.setup \
         doc/_run_artifacts/uvs.setup.orig
b3408fec714dd8f8d9de8c0d09b284cc  doc/AGENTS.md
adfecefacce0f143c0f790d6bdd3da8f  doc/agents/sim-env-回归守护.md
456e2ee419121d2ce77115c0763d338d  doc/agents/sim-env-用例作者.md
eecca1a09d6b2db5faeec33250648588  doc/agents/sim-env-用例执行.md
0c53611e8ede2bb9e42b7e39e3974fbc  doc/agents/sim-env-用例检查.md
564328902f8a1b15014e223efef5a150  doc/tools/compile_only.sh
6a79eed72b57749e7eff1f3bce1a8fd8  doc/tools/run_local.sh
4eddc2f84f855af4fbc8c76e6da246e1  run_uvs_new.sh
a80f7b6ca48a7961a107bbe871af761d  uvs.setup
a80f7b6ca48a7961a107bbe871af761d  doc/_run_artifacts/uvs.setup.orig

$ stat -c'%s %n' doc/tools/compile_only.sh doc/tools/run_local.sh uvs.setup doc/_run_artifacts/uvs.setup.orig
6979 doc/tools/compile_only.sh
15706 doc/tools/run_local.sh
1071 uvs.setup
1071 doc/_run_artifacts/uvs.setup.orig
```

> 若 T4 审计时 `compile_only.sh` / `run_local.sh` 的 md5 变了，**则本次使用的"工具"已不是被审计的工具** ⇒ 换锚点重审。

---

## 6 基线期已可判定的三条"形状/身份"发现（不需等 task-2/3，纯只读）

### 6.1 `uvs.setup.orig` 是"上一次原生运行留下的残值"，不是规范基线 —— 且 `compile_only.sh` 会**覆写**它

```
$ cat uvs.setup
DEFAULT: ./work
rtl:     ./SIMLIB/tc_bmc_spi_03_1/rtl
tb:      ./SIMLIB/tc_bmc_spi_03_1/tb
```

而 `compile_only.sh` **自己生成**的蓝图（`sed -n '67,86p' doc/tools/compile_only.sh`，
存为 `doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt`）写的是：

```
rtl:     ./SIMLIB_RUN/${tc}_${seed}/rtl
tb:      ./SIMLIB_RUN/${tc}_${seed}/tb
```

```
$ md5sum doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt uvs.setup doc/_run_artifacts/uvs.setup.orig
e229293e1e08ef25f8b6347f269cac3f  doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt
a80f7b6ca48a7961a107bbe871af761d  uvs.setup
a80f7b6ca48a7961a107bbe871af761d  doc/_run_artifacts/uvs.setup.orig

$ diff doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt uvs.setup ; echo "diff_rc=$?"
2,3c2,4
< rtl:     ./SIMLIB_RUN/${tc}_${seed}/rtl
< tb:      ./SIMLIB_RUN/${tc}_${seed}/tb
---
> rtl:     ./SIMLIB/tc_bmc_spi_03_1/rtl
> tb:      ./SIMLIB/tc_bmc_spi_03_1/tb
> 
diff_rc=1
```

> **逐行核（避免我自己的概括失真）**：`wc -l` → 蓝图 **20** 行 / 夹具 **21** 行（`41 total`）。
> `cat -n` 显示夹具在第 4 行**之外**第 5 行**还有一个空行**（`uvs.setup:4` 与 `:5` 皆空，蓝图只有 `:4` 空）。
> ⇒ 差异**共 3 行**：`rtl:` 值、`tb:` 值、多出的一个空行；其余 18 行逐字相同。

三个可查事实：

| # | 事实 | 命令/行号 |
|---|---|---|
| a | 夹具内容指向 **`SIMLIB/tc_bmc_spi_03_1`**（原生 `run_uvs_new.sh` 命名），而本轮工具链用的是 **`SIMLIB_RUN/`**（`run_local.sh:239-240` / `compile_only.sh:67-86`） | 上面 `cat` / `diff` |
| b | `SIMLIB/tc_bmc_spi_03_1/` **是空目录**（`total 8`，仅 `.`/`..`）；`SIMLIB/` 76 个子目录中 **75 个为空**，唯一有内容的是 `SIMLIB/tc_pcie_rw_smoke_1/`（26 个文件，全为编译中间件，无 `*.log`） | `ls -la SIMLIB/tc_bmc_spi_03_1/`；`find SIMLIB -mindepth 1 -maxdepth 1 -type d \| wc -l` → `76`；`… -empty \| wc -l` → `75` |
| c | `compile_only.sh:51` `if [ -f ./uvs.setup ]; then cp -p ./uvs.setup "${SETUP_BAK}"; fi` ⇒ **每次运行都会把"当前的 `uvs.setup`"覆写进夹具**，而 `:52` 的 `restore_setup` 又把它拷回来 | `doc/tools/compile_only.sh:45,51-53` |

⇒ **`diff uvs.setup doc/_run_artifacts/uvs.setup.orig` 返回 0 这件事，只证明"当前值 == 当前备份"，
不证明"uvs.setup 未被本轮改动"**——因为"备份"由被审计的脚本自己写、且写的是**改前那一刻的现值**。
这是"自证循环"（与 `AGENTS.md` §1 立守护角色的理由同源：**执行者的工具不能自证**）。
**此条不依赖 task-2/3，现在即可判定。**

### 6.2 `compile_only.sh` 的注释锚点失效（`run_local.sh:266-269` ≠ 实际行号）

`compile_only.sh:23` 声称"选项字符串**逐字复制**自 `doc/tools/run_local.sh:266-269`"。

```
$ sed -n '266,269p' doc/tools/run_local.sh | cat -n
     1	
     2	    if [ -z "${run_remote}" ] || [ "$(hostname)" != "m1" ]; then
     3	        wave_dir="${LOCAL_RUN_ROOT}/wave/${tc}_${seed}"
     4	        rm -rf ${wave_dir}
$ grep -n "tb_dir=\|all_opt=\|vlan_opt=" doc/tools/run_local.sh
279:        tb_dir="+incdir+./TESTLIB,…,./TB/MODEL,./TB"
280:        vlan_opt="-f all_define.txt "
282:        all_opt="-uvm1.2 -sv … -fly_Nopts cgresolve_partial_assign:0 "
$ wc -l doc/tools/run_local.sh
387 doc/tools/run_local.sh
```

**结论**：**引用的行号错了 13 行**（实际是 `:279` 与 `:282`，`vlan_opt` 在 `:280`），
`:266-269` 是 `wave_dir` / `rm -rf` 代码。但**字符串本身确实是逐字一致的**（去掉赋值包装后逐字节相同）：

```
$ md5sum（去包装：去首部空白 / 去 "tb_dir="/"all_opt=" / 去首尾双引号）
0115b1b3effa711632e9bbccf75ab015  <compile_only.sh:90 归一化>
0115b1b3effa711632e9bbccf75ab015  <run_local.sh:279 归一化>
656463ae3c6b8149d84bf42633e86d60  <compile_only.sh:92 归一化>
656463ae3c6b8149d84bf42633e86d60  <run_local.sh:282 归一化>
tb_dir identical? YES   （661 字节）
all_opt identical? YES  （366 字节）
```

⇒ **复制是真的，锚点是假的**。风险不在今天，而在**下次 `run_local.sh` 改动时**：
注释指向一个**恒为 `wave_dir` 代码的行号区间**，即使 `tb_dir` 变了，注释也"看起来还成立"（因为没人会去读 266-269）。
⇒ 机制性修法（见 §8-③）必须是**机器可查**的锚点，不是"写对行号"。

### 6.3 同名不同内容的两份运行日志，且**都没有 `SOURCE`**（本工程 §3-要点 3 的实例）

| 路径 | md5 | 字节 | mtime | 行数 | 脚本口径 `egrep -c '(\*E\|\*F\|\*e\|ERROR:)'` | 真实 `UVM_ERROR … @` 报告行 | UVM 汇总行 |
|---|---|---|---|---|---|---|---|
| `LOG/tc_dom_polling_new_01_1_run.log` | `09a37ea22341d33ec62ba2672c6b5789` | 220150 | 2026-10-10 10:58:46.208001995 | 4392 | 0 | 0 | `UVM_ERROR :    0` |
| `SIMLIB_RUN/log/tc_dom_polling_new_01_1_run.log` | `e67e485bbeff4c3facc1655883ad8bd1` | 219341 | 2026-10-10 14:33:54.480606281 | 4377 | 0 | 0 | `UVM_ERROR :    0` |

- 两份**同名、同 seed（`_1`）**，但**内容不同**（md5 不同）、**大小差 809 字节**、**时间差约 3h35m**；
  `LOG/` 的那份**更早却更大** ⇒ 二者**不是同一次运行的同一产物**。
- `grep -ci 'SOURCE'` 两份 **均为 0** ⇒ 按 `sim-env-回归守护.md` §1-3，**一律视为"移动靶归档"，不得作为改前证据**。
- `run_local.sh:338` `scp SIMLIB_RUN/log/<tc>_<seed>_run.log …:${current_dir}/LOG` + `:341` `rm SIMLIB_RUN/log/<tc>_<seed>_*.log`
  ⇒ 本地日志**跑完即删、远端 `LOG/` 留档**；两份并存本身说明**至少有一次运行没有走这条 scp 路径**（或走了不同的 `current_dir`）。
- 本行**不是**在指控谁改了什么，而是记录：**这两份"证据"当前无法回答"哪份对应哪个 run"** ⇒ 无锚点。

**口径仪器标定（证明我的两条计数命令是对的，不是自说自话）**——对 `sim-env-回归守护.md` §6 已实证的 3 个用例重取：

| 日志 | md5（本次重取） | 脚本口径 | 真实 `UVM_ERROR … @` 行 | UVM 汇总 | `check_runsim.log` 判定 |
|---|---|---|---|---|---|
| `LOG/tc_rtc_02_1_run.log` | `c37c872848ae20ff822f4be834820c06` | **0** | **32** | `UVM_ERROR :   32` | `[OK] … end_ok:1  err_cnt 0` |
| `LOG/tc_rtc_03_1_run.log` | `ddc032e02b3e34f21bdb2e7de66c2d2b` | **0** | **32** | `UVM_ERROR :   32` | `[OK] … end_ok:1  err_cnt 0` |
| `LOG/tc_rtc_08_1_run.log` | `42bbc9cf8dd20d00d92a41e822f30b86` | **0** | **64** | `UVM_ERROR :   64` | `[OK] … end_ok:1  err_cnt 0` |

⇒ 与我角色 §6 记载的 `32/32/64` **完全复现**，且**本次重取的 md5 是新锚点**。
⇒ 结论：**"脚本口径 = 0"绝不等于"无失败"**；任何只给一套口径的判定，我按 §1-1 判**退回**。

---

## 7 我对"只编译"这一限制的理解（预先想清楚，避免事后越界）

**"只编译"意味着：本演示的证据链在编译完成的那一刻就结束了。**

1. **没有运行日志 ⇒ 没有第二套口径可对。** 我的第 1 职责（判定口径守护）本轮**没有对象**：
   两套口径（脚本口径 / UVM Report Summary）都产自**仿真运行日志**；`compile_only.sh` 只产
   `SIMLIB_RUN/log/<tc>_<seed>_c_{rtl,tb}.log` 两份**编译**日志。⇒ 本轮**不存在 PASS/FAIL 判定**。
2. **因此任何"用例通过"的表述都是越界结论。** 编译 rc=0 只证明"语法/宏/包依赖/端口连接过关"，
   **不证明**：地址落在已登记段内、通道选择正确、复位值取自位定义表、失败路径会真的打 `*E`、
   写后读是否被打空——这些**只能由仿真 + 两套口径**回答（§6 已实证：真实 `UVM_ERROR` 32 条时脚本口径仍为 0）。
   ⇒ 本轮**允许**的措辞只有"**编译通过（卡点 B）**"；**禁止**"功能通过 / 用例通过 / 验证通过"。
3. **`compile_only.sh` 的 `[PASS]` 字样本身就是风险点**：`:125` 打印
   `=========== [PASS] 卡点 B 通过：两段编译均成功 ===========`。
   它写的是"卡点 B 通过"（正确），但字面上含 `[PASS]`，**极易被下游引用成"用例 PASS"**。
   ⇒ 我的动作：在 T4_guard.md 里把"该 `[PASS]` 的口径 = 仅编译 rc"写成显式限定，
   并要求下游任何引用**必须带"（编译）"限定词**。
4. **`SOURCE` 字段在本轮的唯一合法形态**：因为**没有 run**，T2 证据**不可能**给出真正的
   `run_id + 时刻 + 用例 + seed + 日志路径`。⇒ 本轮**不存在可归档的运行证据**；
   若 T2 写出了"`SOURCE: run_id=…`"，那反而是**造锚点**（比缺字段更严重）。
   合法做法是：T2 明确声明"**本轮无 run，故无 SOURCE；seed 仅用于库路径隔离**"。

---

## 8 三条机制的**预评估**（T4_guard.md 里按 T2/T3 实际产物复核后定稿）

### ① `compile_only.sh` 的 rc 门 —— **有效但不够；且它的"通过"比 task-2 的 PASS 定义窄**

- **有效**：`:102 rc_rtl=$?` → `:104 [ $rc_rtl -ne 0 ] && { …; exit 10; }`；`:111 rc_tb=$?` → `:114 if [ $rc_tb -ne 0 ]; then … exit 11; fi`。
  两段 rc 都真读了（`$?` 紧跟在 `uvlan` 命令后，捕获正确），失败分支**非 0 退出**，满足
  `AGENTS.md` §4-5"**空输入/部分跑的退出码必须非 0**"。
- **不够（缺口 1）**：脚本**只**看 rc，**不**看编译日志正文。而 task-2 的 PASS 定义是
  "两段 `uvlan` 均 rc=0，**且** `_c_rtl.log`/`_c_tb.log` **无 ERROR 级诊断**"——
  **后半个条件脚本根本不检查**。`:120` 的 `grep -nE "ERROR|Error|error"` **只在 rc≠0 的失败分支里执行**，
  永远不参与"通过"判定。⇒ 若 `uvlan` 以 0 退出但日志有 ERROR 级诊断，脚本打印 `[PASS]` 并 `exit 0`。
  **这一条只能靠人读日志 ⇒ 按验收口径判"未沉淀"。**
- **不够（缺口 2）**：`set -u` 是唯一的安全选项（`:26`），**没有 `set -e` / `set -o pipefail`**，
  且**没有任何锁**（`grep -rn "flock\|lockfile\|LOCK" doc/tools/` → **NO MATCH**）。
  `AGENTS.md` §5 红线 7"同一目录禁止并发跑用例"在本脚本里**零机制**——task-2 只能靠
  `ps -ef | grep` 人工确认（即"靠人更小心"）。`uvs.setup` 是全局单文件，并发 = 互踩。
- **不够（缺口 3）**：md5 只 `echo` 到**终端**（`:58`、`:126`），**不落盘** ⇒ 证据身份随滚动丢失；
  脚本也**不记录 `run_id` / 时刻 / 宿主**。这就是 §6.3/SOURCE 缺失的**结构性根因**（不是 T2 不用心）。

### ② `compile_only.sh` 的 `trap` 还原 —— **还原动作存在，但"还原正确性"零断言；且夹具可被覆写**

- **有效部分**：`:53 trap restore_setup EXIT INT TERM` 覆盖了正常/失败/`INT`/`TERM` 四条路径，
  `exit 10`/`exit 11` 也会触发；`:52` 的 `cp -p` 保留 mtime。
- **缺口 1（自证循环，基线期已证）**：`:51` **先把当前 `uvs.setup` 拷进夹具**再生成新的。
  ⇒ 夹具 = "本轮改前的现值"，**不是不可变基线**。§6.1 已证：其内容是上一次原生运行残留的
  `SIMLIB/tc_bmc_spi_03_1`（空目录）。⇒ `diff` 一致**不能**证明"未被本轮改动"。
- **缺口 2（还原无验证）**：`:52` `[ -f "${SETUP_BAK}" ] && cp -p …`——
  若备份不存在，**静默什么都不做**；且 trap 内的失败**不改退出码**（trap 在 `EXIT` 时运行，
  此时的 `cp` 失败只是丢弃一个非 0 状态）⇒ **还原失败仍会打印 `[PASS]` 且 rc=0**。
  全文 `grep -n md5sum` 只有 `:58`/`:126` 两处，**都是算用例 md5，没有一处校验还原结果**。
- **缺口 3（信号盲区）**：`SIGKILL` / `SIGQUIT` / 断电不在 trap 覆盖内；而 `:65 rm -f ./uvs.setup`
  之后再生成 ⇒ 被 `kill -9` 会留下生成态 `uvs.setup`（指向 `SIMLIB_RUN/<tc>_<seed>`）。
- **缺口 4（归属冲突）**：`SETUP_BAK` 落在 `doc/_run_artifacts/`，即**被审计的脚本在写"证据/夹具"目录**。
  按 `AGENTS.md` §3 的写权表，`doc/` 下的守护/证据产物归 guardian；此文件既无人署名也无写权声明。
- **缺口 5（没有锁）**：同 ① 缺口 2——还原一个"全局单文件"的同时，另一个进程可能正在改它。

### ③ 作者自检第 4 / 7 条 —— **两个"高危项"都只有"自证"，没有任何外部门**

对照 `doc/agents/sim-env-用例作者.md` §6：

| 条目 | 原文 | 性质 |
|---|---|---|
| 4 | "每个地址都写成 `<段基址>+<块内偏移>`，且**带注释说明是哪个块的哪个寄存器**？" | **自检（自己打勾）** |
| 7 | "**失败路径同时**打印含 `*E` 的文本 **和** `` `uvm_error ``？" | **自检（自己打勾）** |

- 这两条正是 `AGENTS.md` §5 红线 **4（121 个站点打空）** 与红线 **3（3 个用例被误判 OK）** 的对应项，
  却都**只存在于作者的清单里**，**无脚本、无 lint、无 CI**。
- 现状的"外部门"只有两个，且都是**人工**：
  - `task-3` 的 checker **逐条手看**（21 条静态清单 + 7 条重点）；
  - `compile_only.sh` 的编译 rc——**它对第 4/7 条完全无能为力**：
    地址写错是**语法合法**的，失败路径只打 `*E` 不写 `uvm_error` 也是**语法合法**的，都能编译通过。
- ⇒ **两条都可以机械化**（且都不是"看语义"）：
  - 第 7 条：同一用例文件内，若存在含 `*E` 的 `$display`/`uvm_info` 而**全文无** `` `uvm_error `` ⇒ 报错；
    更强的形式：要求每个"判定分支"内 `*E` 与 `` `uvm_error `` **同现**（可用块级文本 lint 近似）。
  - 第 4 条：对每个寄存器访问实参里的地址常量（如 `'h2000`、`32'hf00`）要求**同时出现**段基址符号 + 偏移符号
    （或要求地址实参**不是**单个裸常量），命中即报错。
  ⇒ 现判：**③ 判"未沉淀"**（写成"靠人更小心"即未沉淀——这里正是）。

---

## 9 基线期就绪状态 / 阻塞

```
$ ls doc/agents/_demo/TESTLIB_sandbox/          → 空（仅 . 与 ..）
$ ls -l doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv
ls: cannot access …: No such file or directory
```

- **task-1（作者）未产出** ⇒ `task-2`（runner）无输入 ⇒ `task-3`（checker）无对象 ⇒ **`task-4` 不可 claim**（`ready=false`，`blockedBy=["task-3"]`）。
- 基线期观察到的进程事实（只读，仅记录不改）：`doc/agents/_demo/evidence/T2_prerun_snapshot.md`
  于快照期间（17:51）出现，自述"**只读准备完成；未执行编译，等待 Lead 放行**"，
  且已独立复现 §6.1-c 的 `-k` 死代码（`compile_only.sh:63-64`）。
  ⇒ 两处**独立**观测收敛，**但"两个人各自看出来"不是机制**（见 §8-③ 判据）。
- **等 Lead「task-3 完成」后**：`team_task_get("task-4")` → `claim` → 按 §1~§6 实测
  → 落 `doc/agents/_demo/guard/T4_guard.md` → `complete` → 报 Lead。

## 10 本基线自身的可复现性

| 文件 | 说明 |
|---|---|
| `doc/agents/_demo/guard/T4_baseline.md` | 本文 |
| `doc/agents/_demo/guard/T4_baseline_LOG_md5.txt` | `LOG/` 78 个文件的 `md5 + 字节 + mtime + 路径`；`sha256=61feaf2ef1f80e9cd22d942d54df368ec67e98c0c465b77cccd05040cac41c50` |
| `doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt` | `sed -n '67,86p' doc/tools/compile_only.sh`（§6.1 比对用）；`md5=e229293e1e08ef25f8b6347f269cac3f` |

重取命令（任何人可复跑）：
```bash
md5sum uvs.setup doc/_run_artifacts/uvs.setup.orig
diff uvs.setup doc/_run_artifacts/uvs.setup.orig; echo "diff_rc=$?"
for f in LOG/*; do sz=$(stat -c'%s' "$f"); mt=$(stat -c'%y' "$f"); echo "$(md5sum "$f" | cut -d' ' -f1) $sz $mt $f"; done
```

本基线产物的 md5（就是"我的证据链"自身的身份）**不写死在正文里**——
一个文件无法记录自己的 md5（自指）。改由命令生成的旁挂清单记录：

```
doc/agents/_demo/guard/T4_artifacts_md5.txt      ← 由 md5sum 命令输出直接落盘
```

---

## 11 写入后漂移复查（证明基线在快照期间未被扰动）

写完本文件后**重新取数一次**，全部与 §1~§4 逐字一致：

```
$ md5sum uvs.setup doc/_run_artifacts/uvs.setup.orig
a80f7b6ca48a7961a107bbe871af761d  uvs.setup
a80f7b6ca48a7961a107bbe871af761d  doc/_run_artifacts/uvs.setup.orig
$ stat -c'%s %y %n' LOG/tc_dom_polling_new_01_1_run.log
220150 2026-10-10 10:58:46.208001995 +0800 LOG/tc_dom_polling_new_01_1_run.log
$ ls LOG/ | wc -l   → 78        $ find LOG -type f | wc -l → 78
$ git status --short | wc -l → 49    $ … | grep -c '^ M' → 18
```

**78 个 `LOG/` 文件按内容 md5 全量复核**（用 `T4_baseline_LOG_md5.txt` 反查，命令原文）：
```bash
awk 'NR>4{print $1"  "$6}' doc/agents/_demo/guard/T4_baseline_LOG_md5.txt > .verify_sum
md5sum -c .verify_sum; echo "rc=$?"
```
```
md5sum_check_rc          = 0
OK count                 = 78
non-OK lines             = 0
```
⇒ **`LOG/` 78/78 内容零改动**（这是内容断言，`AGENTS.md` §4-3；不是 mtime 断言）。

> 记录一处**我自己的**取证纠错：第一次用 `awk '{print $1"  "$4}'` 拼校验清单，
> `$4` 取到的是 mtime 的**时间片段**（如 `10:58:46.484001986`）而不是路径，
> 于是 `md5sum -c` 报出一片 `No such file or directory`。字段位置应为 `$6`（格式为 `md5 字节 日期 时刻 时区 路径`）。
> ⇒ **"命令输出必须被读，不能被假设"**——我把它留在案上，作为本工程"数字纪律"（§5 红线 10）的一条自证。
