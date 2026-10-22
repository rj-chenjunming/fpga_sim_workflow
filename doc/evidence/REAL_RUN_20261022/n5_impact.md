# N5 影响分析（两级；Host 确定性，spec §2 N5 / §10.3）

- run_id：`RUN-20261022-181700`｜generated_at：`2026-10-22T19:30:39+0800`
- N2 差异清单：`runs/RUN-20261022-181700/n2_diff.json`（sha256 `015132bd54b8303cd22eaf5a82bf743faf2f58f2500317d231001eab8ae3d7f6`）
- 门禁：G1 signed=True decision=confirmed actor_kind=human human_signed=True enforced=True
- 结论：【必改】3 条、【待查】6 条；index_complete=True
- 索引来源（index_provenance）：case_access=`index/case_access.json` sha256=`f49524edfefd4e28`；segment_rtl=`index/segment_rtl.json` sha256=`81b15c3f3b915634`；buckets={'B1': 1915, 'B1_in_doc': 1739, 'B1_unique_addrs': 150, 'B2': 64, 'B3': 2580, 'total': 4559}；权威口径：kb/index/case_access.json 的重新推导值为权威；doc/_notes/09_iface_doc_vs_case.md 的数字（1928/66/2561/4555）仅为参照（kb/README.md §3.3 已按 T3 重推值改）
- B3 补偿（lead hard rule）：命中站点总数=0（明细列出 0 条）；差异清单参照=/home/work/chenjunming/change-impact-loop/workspaces/real-ws/runs/dev-case-kb/divergence_sites.csv（存在=False）

## 8 段覆盖（自检 ≥8，缺段即索引缺口）

| 段 | 候选 | 触及 RTL 文件 | 触及 offset | 必改 | 待查 |
|---|---|---|---|---|---|
| `0x0000` | 否 | - | - | 0 | 0 |
| `0x0100` | 否 | - | - | 0 | 0 |
| `0x0600` | 否 | - | - | 0 | 0 |
| `0x0800` | 否 | - | - | 0 | 0 |
| `0x0a00` | 否 | - | - | 0 | 0 |
| `0x0d00` | 是 | RTL/SRC/imports/SRC/pcie_controller/pcie_register.v | 0x1a04,0xd04 | 5 | 6 |
| `0x2000` | 否 | - | - | 0 | 0 |
| `0x4000` | 否 | - | - | 0 | 0 |

只打标记不建映射：`0x8000`, `0x10000`（命中只记 index_gaps，不产出必改/待查）

## task-13 标注汇总（可达性 / 墙钟成本 / 可行性）

- 阈值 `--max-wall` = 1800 s；速率样本 n=5，中位数 3.7831448679424327 µs/s（**样本逐条 sha256 见 cost_model.sources；n=1 时不外推**）
- 分组计数：**must_change**=3；**must_change_over_budget**=2；**must_change_unreachable**=0；**to_check**=6

## 【必改】（offset 直接命中且位域可判定） —— 3 条

| 用例 | 段 | offset | entry_id | 可达性 | 预计墙钟 | 可行 | 依据链（段→RTL文件→用例） | why |
|---|---|---|---|---|---|---|---|---|
| `tc_pcie_rw_02` | `0x0d00` | 0xd04 | 0x0d00#0x0d04 | live | 17.6 min | yes | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_pcie_rw_02.sv:238（base_addr+'h04） | offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改 |
| `tc_pcie_rw_smoke` | `0x0d00` | 0xd04 | 0x0d00#0x0d04 | live | 0.0 min | yes | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_pcie_rw_smoke.sv:113（'hd04） | offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改 |
| `tc_rtc_05` | `0x0d00` | 0xd04 | 0x0d00#0x0d04 | live | 3.2 min | yes | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_rtc_05.sv:115（'hd04） | offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改 |

访问站点（B1/B2 原样）：
- `tc_pcie_rw_02` TESTLIB/tc_pcie_rw_02.sv:238 [B1] addr=0xd04 callee=reg_field_test
- `tc_pcie_rw_smoke` TESTLIB/tc_pcie_rw_smoke.sv:113 [B1] addr=0xd04 callee=set_write
- `tc_pcie_rw_smoke` TESTLIB/tc_pcie_rw_smoke.sv:114 [B1] addr=0xd04 callee=PCIE_REG_RDCHK
- `tc_rtc_05` TESTLIB/tc_rtc_05.sv:115 [B1] addr=0xd04 callee=set_write
- `tc_rtc_05` TESTLIB/tc_rtc_05.sv:116 [B1] addr=0xd04 callee=PCIE_REG_RDCHK

## 【必改·超预算】（仍要改，但预计本轮跑不完；**不假装会跑**） —— 2 条

| 用例 | 段 | offset | entry_id | 可达性 | 预计墙钟 | 可行 | 依据链（段→RTL文件→用例） | why |
|---|---|---|---|---|---|---|---|---|
| `tc_cpu_i2c_03` | `0x0d00` | 0xd04 | 0x0d00#0x0d04 | live | 13.84 h | no | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_cpu_i2c_03.sv:329（base_addr+'h04） | offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改；【超预算】预计墙钟 13.84 h > 阈值 1800 s（sim_end=188.463 ms × 速率 3.7831 µs/s，样本 n=5，来源见 sim_cost） |
| `tc_rtc_10` | `0x0d00` | 0xd04 | 0x0d00#0x0d04 | live | 7.45 h | no | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_rtc_10.sv:121（'hd04） | offset 直接命中且文档有位定义表（bitdef_present=true）⇒ 必改；【超预算】预计墙钟 7.45 h > 阈值 1800 s（sim_end=101.463 ms × 速率 3.7831 µs/s，样本 n=5，来源见 sim_cost） |

访问站点（B1/B2 原样）：
- `tc_cpu_i2c_03` TESTLIB/tc_cpu_i2c_03.sv:329 [B1] addr=0xd04 callee=reg_field_test
- `tc_rtc_10` TESTLIB/tc_rtc_10.sv:121 [B1] addr=0xd04 callee=set_write
- `tc_rtc_10` TESTLIB/tc_rtc_10.sv:122 [B1] addr=0xd04 callee=set_rdchk

## 【必改·不可达】（静态站点存在但活链不可达 ⇒ 修订无法被验证） —— 0 条

_无_

## 【待查】（只段级命中或位域不确定） —— 6 条

| 用例 | 段 | offset | entry_id | 可达性 | 预计墙钟 | 可行 | 依据链（段→RTL文件→用例） | why |
|---|---|---|---|---|---|---|---|---|
| `tc_cpu_i2c_03` | `0x0d00` | - | - | live | 13.84 h | no | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_cpu_i2c_03.sv:328（base_addr+'h00） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |
| `tc_pcie_rw_02` | `0x0d00` | - | - | live | 17.6 min | yes | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_pcie_rw_02.sv:237（base_addr+'h00） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |
| `tc_qsfp_03` | `0x0d00` | - | - | live | unknown | unknown | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_qsfp_03.sv:119（32'h1400+'h3e0） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |
| `tc_qsfp_03_test` | `0x0d00` | - | - | live | unknown | unknown | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_qsfp_03_test.sv:119（32'h1400+'h3bc） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |
| `tc_qsfp_04` | `0x0d00` | - | - | live | unknown | unknown | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_qsfp_04.sv:114（32'h1400+'h3bc） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |
| `tc_uart_08_cov` | `0x0d00` | - | - | live | unknown | unknown | 段 0x0d00 → RTL RTL/SRC/imports/SRC/pcie_controller/pcie_register.v → 用例 TESTLIB/tc_uart_08_cov.sv:162（32'h1000） | 只段级命中（diff 触及的 offset 与该站点的 addr 不相交）⇒ 待查（宁多勿漏） |

访问站点（B1/B2 原样）：
- `tc_cpu_i2c_03` TESTLIB/tc_cpu_i2c_03.sv:328 [B1] addr=0xd00 callee=reg_field_test
- `tc_cpu_i2c_03` TESTLIB/tc_cpu_i2c_03.sv:330 [B1] addr=0xd08 callee=reg_field_test
- `tc_pcie_rw_02` TESTLIB/tc_pcie_rw_02.sv:237 [B1] addr=0xd00 callee=reg_field_test
- `tc_pcie_rw_02` TESTLIB/tc_pcie_rw_02.sv:239 [B1] addr=0xd08 callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:119 [B1] addr=0x17e0 callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:120 [B1] addr=0x15c0 callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:121 [B1] addr=0x15cc callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:122 [B1] addr=0x15d8 callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:123 [B1] addr=0x1580 callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:127 [B1] addr=0x17fc callee=reg_field_test
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:131 [B1] addr=0x15c0 callee=set_write
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:132 [B1] addr=0x15c0 callee=PCIE_REG_RDCHK
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:139 [B1] addr=0x15cc callee=PCIE_REG_RDCHK
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:145 [B1] addr=0x1580 callee=PCIE_REG_RDCHK
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:150 [B1] addr=0x17fc callee=set_write
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:151 [B1] addr=0x17fc callee=PCIE_REG_RDCHK
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:153 [B1] addr=0x15d8 callee=set_write
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:154 [B1] addr=0x15d8 callee=PCIE_REG_RDCHK
- `tc_qsfp_03` TESTLIB/tc_qsfp_03.sv:157 [B1] addr=0x15cc callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:119 [B1] addr=0x17bc callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:120 [B1] addr=0x15c0 callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:121 [B1] addr=0x15cc callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:122 [B1] addr=0x15d8 callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:123 [B1] addr=0x1580 callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:127 [B1] addr=0x17d8 callee=reg_field_test
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:131 [B1] addr=0x15c0 callee=set_write
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:132 [B1] addr=0x15c0 callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:139 [B1] addr=0x15cc callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:145 [B1] addr=0x1580 callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:150 [B1] addr=0x17d8 callee=set_write
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:151 [B1] addr=0x17d8 callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:153 [B1] addr=0x15d8 callee=set_write
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:154 [B1] addr=0x15d8 callee=PCIE_REG_RDCHK
- `tc_qsfp_03_test` TESTLIB/tc_qsfp_03_test.sv:157 [B1] addr=0x15cc callee=PCIE_REG_RDCHK
- `tc_qsfp_04` TESTLIB/tc_qsfp_04.sv:114 [B1] addr=0x17bc callee=PCIE_REG_RDCHK
- `tc_qsfp_04` TESTLIB/tc_qsfp_04.sv:115 [B1] addr=0x17bc callee=set_write
- `tc_qsfp_04` TESTLIB/tc_qsfp_04.sv:116 [B1] addr=0x17bc callee=PCIE_REG_RDCHK
- `tc_uart_08_cov` TESTLIB/tc_uart_08_cov.sv:162 [B1] addr=0x1000 callee=set_read
- `tc_uart_08_cov` TESTLIB/tc_uart_08_cov.sv:188 [B1] addr=0x1ef8 callee=set_read
- `tc_uart_08_cov` TESTLIB/tc_uart_08_cov.sv:189 [B1] addr=0x1efc callee=set_read

## 索引缺口（index_complete=True）

- `rtl_file`：RTL/SRC/imports/SRC/pcie_controller/pcie_register.v 的段映射未经 grep 复验（verified!=true）：0x0d00 → **转人工：请 case-kb 复验 RTL/SRC/imports/SRC/pcie_controller/pcie_register.v:161 原文**
- `rtl_file`：RTL/SRC/imports/SRC/pcie_controller/pcie_register.v 的段映射未经 grep 复验（verified!=true）：0x0d00 → **转人工：请 case-kb 复验 RTL/SRC/imports/SRC/pcie_controller/pcie_register.v:161 原文**
- `offset`：存在 2580 个 B3 未能归类访问站点（含未知符号，不猜测） → **转人工：如需精确判定，请作者补绑定形参/展开变量后重扫 case_access.json**
- `marked-only-segment`：0x8000 只打标记不建映射（docs/RTL 依据不足；本轮 diff 未触及该段） → **转人工：如需覆盖该段，先补文档登记或 RTL 译码依据，再决定是否建映射**
- `marked-only-segment`：0x10000 只打标记不建映射（docs/RTL 依据不足；本轮 diff 未触及该段） → **转人工：如需覆盖该段，先补文档登记或 RTL 译码依据，再决定是否建映射**

## 口径说明

- 一级段级粗筛**宁多勿漏**：diff 触及的 RTL 文件经 `segment_rtl.json` 映射到候选段；文件未映射时 8 段全部进候选，绝不用『没映射就当无影响』。
- 二级 offset 交集：①路 hunk 抽取的字面量按**块内偏移**换算 `<段基址>+<块内偏移>`（同时保留“字面量已是全局地址”的候选）；③路 entry_id 的 `offset_global` 直接作为 offset。
- **位域不确定口径**：`regEntry.bitdef_present=false` ⇒ 位域不可判定 ⇒ 进【待查】；只有 offset 直接命中且 `bitdef_present=true` 才是【必改】（README §6 红线 2：预期值只认文档位定义表）。
- B2 大范围扫描站点：只知区间不含逐点 ⇒ 命中区间也只是【待查】。B3 未能归类 ⇒ 一律【待查】，不予猜测（09 §B.0）。
- **B3 补偿规则（不许把『未归类』当漏检借口）**：B3 站点的 `addr_expr` 文本**显式含**本次变更触及的 offset 字面量（`32'h04` / `+32'h4` / `0x04`）时，该站点必须登记`index_gaps[kind=offset]`（转人工确认实际地址）且所属用例**至少**进【待查】；命中站点总数完整写在 `index_provenance.b3_compensation.total` 与 notes 里，明细超过 200 条只列前 200 条但**总数不截断**。
- **B3 补偿计数语义（防误读为矛盾）**：`b3_compensation.total=0` 是**站点数**，`listed=0` 是列出明细的站点数；而 `to_check` 里带 `b3_compensated=true` 的是**用例级条目数=0**（同一用例多个站点会合并成一条，且若该 (用例,段,offset) 已被 B1/B2 命中则合并到那条上）。站点数 ≥ 用例条目数，两者不是同一种计数。
- **可达性判据（task-13）**：对用例源（`TESTLIB/<tc>.sv`）做**静态调用图** —— 以入口 task `m_run_phase`（缺则 `run_phase`/`m_run`）为根，沿 `task <name>(` 定义 + `name(` 调用点传播；站点所在 task 可达 ⇒ `live`；定义存在但无调用点 ⇒ `unreachable`；站点不在任何 task 内 ⇒ `static-only`；源不可读/无 task/无入口 ⇒ `static-only`（**不猜 live**）。**`unreachable` 的条目不得留在【必改】** ⇒ 单独成组 `must_change_unreachable[]`。
- **墙钟成本判据（task-13）**：从历史运行日志（`LOG/`、`SIMLIB_RUN/log/`、`SIMLIB/` 下 `<tc>_*_run.log`；固定根顺序 + 排序取字典序最大者）解析 `from call to $finish` 的仿真时刻；速率**必须**来自已归档真实运行（`kb/runs/**/evidence/*_run.log` 的 `Elapsed` 与仿真时刻），多样本取中位数，来源 path+sha256 全部记进 `cost_model`。`wall_est = sim_end / rate`；`> --max-wall` ⇒ `feasible=no` 并移入 `must_change_over_budget[]`（**仍在清单里**，附量化原因）。缺历史日志 ⇒ `sim_cost=unknown`/`feasible=unknown`（**不许猜 yes**）。
- **索引权威口径**：`kb/index/case_access.json`（T3 重推）为权威；09 笔记的数字仅为参照，N5 **不**用 09 的数字去校准（README §3.3 已改）。
- `0x8000`/`0x10000` 只打标记不建映射 ⇒ 命中写 `marked-only-segment` 缺口并 rc!=0，转人工，不产出必改/待查（spec §10.3）。
- 归一化指纹复算口径（task-18 / F-DET-01）：`normalized_sha256 = sha256(canon_json(本对象 **剔除 `normalized_sha256` 与 `time_fields`**（以及下划线开头的内部键）后，把 `generated_at` 替换为 `"<TIMESTAMP>"`))` —— 按 README §3.1.1 的字面公式**必须先剔除自指簿记键**才能复算。被剔除键清单：`["normalized_sha256","time_fields","_*"]`；被归一化的时间字段：`['generated_at']`。本件自报值见 `normalized_sha256` 字段。
- `generated_at` 是唯一被允许的非确定性字段（README §3.1.1，本脚本声明时间字段 `("generated_at",)`），一律经 `kb_lib.now_iso()` 与 `--now`/`KB_NOW` 注入；强判据：同一输入 + 同一 `--now` 两次逐字节相同；弱判据：不同 `--now` 两次，`K.sha256_obj_normalized(obj, ("generated_at",))` 相同。

## 其他说明

- 位域可判定性来源：kb/index/regmap.json（126 条），用于把 ① 路抽出的 offset 接到位定义表
- RTL/SRC/imports/SRC/pcie_controller/pcie_register.v（allfile）未抽出 offset：② 路只比逐文件 md5 清单，无文本 hunk（旧版正文不在 KB）⇒ offset 由 ①/③ 路提供；本条已按『modified』计入差异（② 路设计如此，offset 由 ①/③ 路提供）
- 用例访问站点：B1=1915 B2=64 B3=2580（B3 不猜，只在段级命中时进【待查】）
- 墙钟速率样本 n=5（中位数 3.7831 µs/s；**不外推**：样本来自真实归档运行，逐条 sha256 记在产物里）
- task-13 标注（必改）：reachability live=5/static-only=0/unreachable=0，feasible yes=3/no=2/unknown=0；阈值 1800 s；不可达 0 组、超预算 2 组（分组后仍在清单里，但不假装本轮会跑）

