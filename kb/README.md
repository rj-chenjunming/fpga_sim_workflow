# `kb/` —— FPGA 变更影响闭环知识库（Host 确定性侧）

> **权威设计契约**：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md` v0.2（16 节点 N0~N16、三道人工闸门）。
> **交接说明**：`CHECKPOINT-20261015-1123.md` §9 第 3 条（建 `kb/`）——该文件是 **ENV_ROOT 历史件**
> （`<ENV_ROOT>/CHECKPOINT-20261015-1123.md`），不在本仓；这里只作历史引用。
> **三根**：`TOOL_ROOT`=本仓；`ENV_ROOT`=被守卫的环境仓；`WORKSPACE_ROOT`=该环境的数据根
> （当前 = `<ENV_ROOT>/kb`；目标 = `workspaces/<env-id>/`）。定义见 `doc/spec/ENV_PLUGIN_SPEC.md` §1。
> **写权**：本仓 `kb/` 只放契约与 Host 程序；运行数据由 Host 工具写到 `<WORKSPACE_ROOT>`。
> 环境的 `RTL/ TB/ PKG/ TESTLIB/` 与 `doc/` 只读（见 §6 红线）。
>
> 本文件是 `kb/` 内部所有脚本与角色共用的**接口契约**。任何脚本不得私自定义指纹口径、
> 序列化方式或字段名 —— 口径一旦分裂，"身份可 join"就不成立。

---

## 1 目录布局（本仓软件目录 vs 数据根）

拆仓后 `kb/` 分成两半：**本仓 `kb/` 只放契约与 Host 程序（git 跟踪）**；
**运行数据在 `WORKSPACE_ROOT`**（不入 git；当前 = `ENV_ROOT/kb`，目标 = `workspaces/<env-id>/`）。

```
<TOOL_ROOT>/kb/                     # 本仓（软件；git 跟踪）
├── README.md                      # 本文件（契约；Lead 维护）
├── schema/                        # 【契约】JSON Schema draft-07，可执行校验（共 8 个）
│   ├── manifest.schema.json       #   manifest（含 parent 链）
│   ├── index.schema.json          #   段索引 / 寄存器条目 / 用例访问站点 / 段↔RTL / 用例元信息
│   ├── conflicts.schema.json      #   C1—C72 矛盾 / 访问路径限制 / D1—D20 待确认
│   ├── gate_state.schema.json     #   闸门状态 + anchor（I6 的权威形状）
│   ├── case_states.schema.json    #   用例态台账（I2）
│   ├── n2_diff.schema.json        #   N2 原始差异清单
│   ├── n5_impact.schema.json      #   N5 必改/待查清单
│   └── baselines_index.schema.json#   基线索引（parent 链）
└── tools/                         # 【Host 确定性程序，不上模型】
    ├── kb_lib.py                  #   公共库：三根解析/指纹/原子写/Schema 子集校验/闸门
    ├── n1_doc_entries.py          #   文档条目抽取 → regmap（N2/N5 的文档侧锚）
    ├── n1_conflicts.py            #   06 号笔记 → conflicts / restrictions / pending
    ├── n1_case_scan.py            #   TESTLIB 静态访问扫描 → case_access / cases
    ├── n1_snapshot.py             #   N0/N1：自研代码 tar + 全量清单 md5 + manifest
    ├── n2_diff.py                 #   N2：纯确定性差异对比（三路）
    ├── n5_impact.py               #   N5：段粗筛 → offset/位域交集 → 必改/待查
    ├── case_state.py              #   用例态台账（I2；N6~N10 责任方写入）
    ├── gate.py                    #   三道人工闸门的持久化状态机（I6）
    ├── n16_promote.py             #   N16：人触发 + Host 原子晋升（七件套）
    └── run_guarded.sh             #   卡点B/D 的安全包装（不改冻结的 run_local.sh）

<WORKSPACE_ROOT>/                   # 数据根（由 environments.json / $LOOP_WORKSPACE 解析）
├── index/                         # 【生成物】机器可读索引（第一键=段，第二键=RTL 文件）
│   ├── segments.json              #   10 条：8 段全覆盖 + 0x8000/0x10000 只打标记
│   ├── regmap.json / regmap.csv   #   文档寄存器条目（段+offset 去重，双来源标注）
│   ├── segment_rtl.json           #   段 ↔ RTL 文件（含 file:line 复验证据）
│   ├── case_access.json / .csv    #   用例访问站点（B1 定向 / B2 大范围 / B3 未归类）
│   └── cases.json                 #   162 用例元信息（md5/字节/行数/命中段）
├── conflicts/                     # 【生成物】一等公民清单（I4）
│   ├── conflicts.json             #   C1—C72（expected_total=72 自检）
│   ├── access_restrictions.json   #   20 条通道限制
│   └── pending.json               #   D1—D20（每条必须带去向 owner）
├── baselines/                     # 【不可变】基线归档，只增不改
│   ├── v0/                        #   七件套 + manifest.json + evidence/
│   └── v1/ …                      #   N16 晋升产物，parent 指向上一个
├── adjudication/                  # 【人裁决材料】不是数据、不是判定，是"等人拍板"的决策包（只新增）
│   ├── I3_dual_count_dispute.md   #   口径一 1687 vs 口径二 UVM_ERROR=0 的裁决请求
│   └── C_conflicts_triage.md      #   C1—C72 批量裁决分组（解 I4 死锁）
└── runs/                          # 【每轮一目录】一个变更一个 run_id
    └── RUN-YYYYMMDD-HHMMSS/
        ├── gates.json             #   三道闸门状态（人签名才 human_signed=true）
        ├── n1_manifest_new.json   #   N1 摄取出的新版 manifest 草案
        ├── n2_diff.json / .md     #   N2 原始差异清单
        ├── n3_digest.md           #   N3 分析师差异语义摘要（模型产物）
        ├── n5_impact.json / .md   #   N5 必改/待查清单
        ├── n12_report.md          #   N12 报告员评估报告（模型产物）
        └── evidence/              #   编译/运行/复核证据（按 run_id 归档，只增不改）
```

> **当前实际（2026-10-19，`environments.json`）**：`WORKSPACE_ROOT = <ENV_ROOT>/kb`，
> 因此上面 `<WORKSPACE_ROOT>/…` 实际落在 `ENV_ROOT/kb/…`；本仓 `kb/` 只有 README + schema + tools。
> 数据不搬的决定见 `doc/spec/ENV_PLUGIN_SPEC.md` §7。

**写权**（与 `doc/AGENTS.md` §3 一致，外加 Host 工具）：

| 产物 | 唯一写者 |
|---|---|
| `kb/schema/`、`kb/README.md` | Lead |
| `kb/tools/kb_lib.py` | Lead（契约代码，改动必须过评审） |
| `kb/tools/n1_*.py`、`<WORKSPACE_ROOT>/index/`、`<WORKSPACE_ROOT>/conflicts/` | 对应生成脚本（Host） |
| `kb/tools/n2_diff.py` / `n5_impact.py` / `gate.py` / `n16_promote.py` / `case_state.py` | Host 工具 owner |
| `<WORKSPACE_ROOT>/baselines/**` | `n16_promote.py`（原子晋升）或 Lead 的 v0 建档 |
| `<WORKSPACE_ROOT>/runs/<run_id>/**` | 该轮 run_id 的 owner（同一 run 内按文件切分，不并发写同一文件） |
| `<WORKSPACE_ROOT>/adjudication/**` | 分析角色（一次一个文件）；**只写"请求人裁决的材料"，不写裁决结论** |

**`adjudication/` 的定位**：数据根里唯一一类**给人看的非数据产物**。它存在的理由是
spec 的闸门语义 —— 系统的职责是**备料**，不是替人拍板。所以这两个文件里
**不得出现**任何形式的"已裁决 / 已确认"措辞，只有「选项 + 后果 + 推荐 + 我需要你回什么」。
真正改变判定的事实必须落回 `<WORKSPACE_ROOT>/conflicts/*.json`（经人授权）或 `gates.json`（人签名）。

---

## 2 节点 ↔ 脚本映射

| 节点 | 类型 | 实现 | 产物 |
|---|---|---|---|
| N0 建基线 | Host | `n1_snapshot.py build --out-baseline v0` | `<WORKSPACE_ROOT>/baselines/v0/manifest.json` |
| N1 输入摄取 | Host | `n1_snapshot.py stage --parent vN --run <run_id>` | `<WORKSPACE_ROOT>/runs/<id>/n1_manifest_new.json` |
| N2 差异对比 | Host | `n2_diff.py` | `<WORKSPACE_ROOT>/runs/<id>/n2_diff.json` + `.md` |
| N3 差异总结 | Model:analyst | `doc/agents/sim-env-分析师.md`（编排层 `model_steps.py` 调用） | `<WORKSPACE_ROOT>/runs/<id>/n3_digest.md` |
| N4 差异确认 | **人·Gate1** | `gate.py sign G1_diff_confirm --actor <人>` | `<WORKSPACE_ROOT>/runs/<id>/gates.json` |
| N5 影响分析 | Host | `n5_impact.py` | `<WORKSPACE_ROOT>/runs/<id>/n5_impact.json` + `.md` |
| N6~N11 | 四角色 team | `doc/agents/sim-env-*.md` + `run_guarded.sh` | `<WORKSPACE_ROOT>/runs/<id>/evidence/` |
| N12 评估报告 | Model:reporter | `doc/agents/sim-env-报告员.md` | `<WORKSPACE_ROOT>/runs/<id>/n12_report.md` |
| N13 评估 | **人·Gate2** | `gate.py sign G2_report_accept` | `<WORKSPACE_ROOT>/runs/<id>/gates.json` |
| N14 回归决策 | **人·Gate3** | `gate.py sign G3_regression_decision` | `<WORKSPACE_ROOT>/runs/<id>/gates.json` |
| N16 晋升新基线 | **人触发 + Host** | `n16_promote.py --trigger-by <人>` | `<WORKSPACE_ROOT>/baselines/vN+1/` |

---

## 3 口径（**唯一**，禁止各脚本自定义）

### 3.1 指纹

| 对象 | 口径 | 实现 |
|---|---|---|
| 单文件 | `md5sum`（逐文件清单）/ `sha256sum`（归档件本体） | `kb_lib.md5_file` / `sha256_file` |
| 逐文件 md5 清单 | 清单**文本**的 sha256（`manifest_sha256`） | `kb_lib.md5_manifest_sha256` |
| 规范化 JSON | 键排序 + `separators=(",",":")` + `ensure_ascii=False` + 结尾 `\n` | `kb_lib.canon_json` |
| 对象指纹 | 上式的 sha256 | `kb_lib.sha256_obj` |
| 条目集（文档） | 逐行规范化 `norm(line) = ' '.join(line.strip().split())`，顺序拼接（每行补 `\n`）后 sha256 | `kb_lib.canon_lines_sha256` |

> **`norm` 只归空白，不归大小写**：寄存器名的大小写是语义的一部分
> （例：`Golden_fpga_version` vs `golden_fpga_version` 在文档里就混用，属 C 类矛盾，必须暴露而不是抹平）。

### 3.1.1 确定性口径（**时间字段是唯一被允许的非确定性**）

证据要带时刻（I5），所以产物里有 `generated_at` / `updated_at` / `created_at`；
但"确定性程序"又要求同一输入可复算。两者这样调和（**这是本 KB 的正式口径**）：

1. **所有时间字段必须可注入**：每个写盘脚本都支持 `--now <ISO8601>`（等价环境变量 `KB_NOW`）。
   未给时用 `kb_lib.now_iso()`（墙钟）。**时间只由这一个入口决定**，不许在别处再取时钟。
2. **强判据（必须成立）**：同一输入 + **同一 `--now`** 连跑两次 ⇒ 输出文件 sha256 **逐字节相同**。
3. **弱判据（必须成立）**：同一输入 + **不同 `--now`** 连跑两次 ⇒ 把**声明过的时间字段**值
   替换成固定占位串后再算 sha256（`kb_lib.sha256_obj`，见下），两次仍相同
   —— 即"时间字段是**唯一**的差异"。
   **复算者另须剔除产物里的"自指簿记键"**：`normalized_sha256` 与 `time_fields` 是*由对象自身*
   算出来的（它们记录的就是这次归一化的结果），把它们算进去会得到一个永远对不上的值。
   实测（verifier F-DET-01）：按 §3.1.1 字面直接复算得 `265ad363…`，而脚本自报
   `ef5318bb…`；差异**全部**来自这两个键。**口径即：归一化指纹 = 剔除声明的时间字段
   + 剔除 `normalized_sha256`/`time_fields` 后的对象 sha256。**
4. **禁止**靠"跑得快、秒级时间戳碰巧相同"来通过判据 —— 那属于 D-2/D-10 类**假通过**。
   确定性验证必须显式用同值/异值 `--now` 各跑一次；**不足 1 秒的两次运行不能作为通过证据**。
5. 每个脚本必须在其产物或 `.md` 伴生文件里**声明**自己的时间字段名清单（供第 3 条归一化）。

`kb_lib` 提供配套工具（脚本必须用它，不许自己实现）：

```python
# 归一化：把声明的时间字段替成固定占位串后取对象指纹
K.sha256_obj_normalized(obj, time_fields=("generated_at",))   # 用于弱判据
```

> **例**：`n2_diff.py` 声明时间字段 `("generated_at",)`；裁判给出
> `same_now: <sha256>`（强判据）与 `diff_now_normalized: <sha256>`（弱判据）。

### 3.2 地址与段

- 段基址表（首版 8 段）：`0x0000 / 0x0100 / 0x0600 / 0x0800 / 0x0A00 / 0x0D00 / 0x2000 / 0x4000`。
- **只打标记不建映射**（spec §10.3）：`0x8000`（文档与 RTL 双侧无依据）、`0x10000`（RTL 有译码、文档未登记）。
- `0x2000` 段含 10 台控制器（`0x2000 + 0x200*k`, `k=0..9`，第 10 台 = **`0x3200`**）；
  `0x4000` 段含 **8** 台（`0x4000 + 0x400*m`, `m=0..7`，**`0x6000` 无 RTL 应答者**）。
- 地址一律写 `<段基址>+<块内偏移>` 并注释标块名（红线 4）。

### 3.3 用例访问站点三桶（**算法口径**与 `doc/_notes/09_iface_doc_vs_case.md` §B.0 逐字一致）

| 桶 | 定义 |
|---|---|
| **B1 定向访问** | 解析成单一常量，或 ≤4096 的有限枚举集合 |
| **B2 大范围扫描** | 只剩一个量程已知的扫描表达式（超枚举上限），范围可确定但未逐点展开 |
| **B3 未能归类** | 含未知符号（未绑定形参、跨用例实参、变量依赖），**不予猜测** |

**权威数字 = `<WORKSPACE_ROOT>/index/case_access.json` 的 `buckets`（重新推导、可复跑）；09 笔记的数字是参照，不是验收门。**

| 指标 | 09 笔记（参照） | 本轮重新推导（权威） | 差 |
|---|---|---|---|
| B1 定向 | 1928 | **1915** | −13 |
| B2 大范围 | 66 | **64** | −2 |
| B3 未能归类 | 2561 | **2580** | +19 |
| 合计 | 4555 | **4559** | +4 |
| B1 去重地址数 | 155 | **150** | −5 |
| B1 文档内 | 1740/1928 = 90.3% | **1739/1915 = 90.8%** | −1 |
| B1 段分布 | 937/300/200/188/134/75/54/24/16 | **935/300/200/176/134/76/54/24/16** | 6 项精确，0x0000 −2、段外 −12、0x0800 +1 |

**为什么允许不一致（Lead 裁定，2026-10-15）**：09 号笔记是**报告**不是可执行规范，且它**自身不自洽**：
① §B.4 段外分族相加 = **208**，与同节声明的 **188** 对不上；
② §B.2 说上界/非法字面量「在 RAW 抽取里**偶发出现**…**仅登记不展开**」，未说明是否计入 4555 总数（差 4 条即源于此）；
③ §B.0 的「按**该文件内** for 头推断取值范围」对 `0x040000 / 0x11000` 一族存在「逐循环覆盖」与「文件级合并」两种读解（分别给 60/64，均非 66）；
④ §B.2 #18/#20 把 9 处 `DOME_PLRAM_ADDR + n*32'h400` / `32'h10000 + n*32'h400` 站点记到 `tc_bmc_i2c_02`/`tc_bmc_spi_02`/`tc_dom_reg_01`，但其中两个文件根本不含该站点。
⇒ 强行"复现"必须**猜** 09 的未写明行为，比"有归因的重新推导"更糟。因此：
**B1/B2 的差集站点必须逐条列出并可查**（`<WORKSPACE_ROOT>/runs/dev-case-kb/divergence_sites.csv`），
差异站点所属桶在 CSV 里标明"09 判 X / 本轮判 Y / 原因"。**N5 影响分析必须用重推数字，并在产物里标注 index provenance。**

> **N5 的「宁多勿漏」补偿规则（针对 B3 差集）**：`B3` 站点虽不可用于"未覆盖"类硬结论，
> 但当其 `addr_expr` 文本**显式含**本次变更触及的 offset 字面量时，N5 必须把它登记进
> `index_gaps`（kind=`offset`）并让对应用例至少落到【待查】——否则"未归类"就成了漏检的借口。

### 3.4 文档条目抽取（验收基准 = `doc/_notes/06_iface_doc_regmap.md` §C）

| 指标 | 06 笔记实测值 |
|---|---|
| 汇总具名行（各段合计） | **126** |
| 汇总去重 offset | **121** |
| 位定义表数 | **125** |
| 文档内部矛盾 | **72**（`C1—C72` 连续无缺号） |
| 访问路径受限 | **20**（主表 18 + 隐含 2） |
| 待确认 | **20**（`D1—D20`） |

> **口径注 1（条目范围）**：`regmap.entries` 只覆盖**首版 8 个 BAR0 段**。
> SPI Slave（独立 16bit 空间、软件不可见）与 IO 接口（`Offset：NA`）**不建条目**，
> 只计入上述抽取口径统计 —— 所以 `126` 是"8 段 offset 并集"，不是"文档所有表行数"。
> **口径注 2（冲突关联方向）**：`regEntry.conflict_ids` 由 `n1_doc_entries.py` 留空
> （它先于冲突抽取运行，不应反向依赖）；冲突 ↔ 条目的关联写在
> `<WORKSPACE_ROOT>/conflicts/conflicts.json` 的 `linked_entries`（40 条）。
> ⇒ **`conflict_ids` 为空 ≠ 该寄存器无冲突**，判定一律以 `conflicts.json.linked_entries` 为准。
> **口径注 3（已知笔记自洽性问题，保留实测不迁就）**：06 笔记 §C 的「汇总表总数据行」列
> 列内之和 = **161**，而该表合计行写 **138**；另 0x2000/0x0800/0x0600 三段该列口径差 1。
> 这是笔记在**非验收列**上的不自洽，四个硬指标不受影响。证据：
> `<WORKSPACE_ROOT>/runs/dev-doc-kb/06_vs_doc_diff.md`。

---

## 4 有据偏离（决策记录）

| # | 偏离 | 理由 | 影响 |
|---|---|---|---|
| **K1** | 机器可读索引用 **JSON**（+CSV），而不是 spec §3 决策 7 字面的 YAML | 本机 Python 3.8.5 **无 `pyyaml`**（实测 `MISS yaml No module named 'yaml'`），装包不可控；**JSON 是 YAML 1.2 的严格子集**，任何标准 YAML 解析器都能直接读 | 无损；`kb/schema/*.json` 仍用 JSON Schema |
| **K2** | 不修改 `doc/tools/run_local.sh`，改为**新增** `kb/tools/run_guarded.sh` 包装它 | spec §9 说"需补 run_local.sh 自愈 + 日志头写 case md5"，但 `CHECKPOINT-…md` §2 把 `doc/tools/*` 列为**已定稿禁止改动**。冻结纪律优先，用新增包装实现同一意图 | 原文件 md5 不变（可复核）；自愈/md5 头落在包装层 |
| **K3** | 三道人工闸门在**演练**中写 `actor_kind="rehearsal"`、`human_signed=false` | spec I6：模型不得替人盖章。演练只能验证机制，**不得**产出"已人工签署"的假证据 | `gate_summary().human_signed_all == False` 是可预期结果，不是缺陷 |

---

## 5 用法

```bash
# 0) 环境自检（不写任何东西；三根由 $LOOP_ENV_ROOT/$LOOP_WORKSPACE 或 environments.json 决定）
python3 kb/tools/kb_lib.py

# 1) 建 v0 基线（N0）：快照 + 三锚 + manifest → <WORKSPACE_ROOT>/baselines/v0/
python3 kb/tools/n1_snapshot.py build --out-baseline v0

# 2) 抽取索引（可重复执行，幂等）→ <WORKSPACE_ROOT>/index|conflicts/
python3 kb/tools/n1_doc_entries.py
python3 kb/tools/n1_conflicts.py
python3 kb/tools/n1_case_scan.py
python3 kb/tools/n1_snapshot.py build --out-baseline v0          # 索引建好后重取锚

# 3) 一轮变更：摄取 → diff → 人确认 → 影响分析
#    先由交付方把新 RTL/文档放到 <WORKSPACE_ROOT>/runs/<run_id>/staged/（见 n1_snapshot.py 头注释）
python3 kb/tools/n1_snapshot.py stage --parent v0 --run <run_id>
python3 kb/tools/n2_diff.py --from-baseline v0 --to-manifest <WORKSPACE_ROOT>/runs/<run_id>/n1_manifest_new.json
python3 kb/tools/gate.py sign G1_diff_confirm --run <run_id> --decision confirmed --actor "<人名>" --actor-kind human
python3 kb/tools/n5_impact.py --run <run_id>

# 4) 闸门状态 / 晋升
python3 kb/tools/gate.py show --run <run_id>
python3 kb/tools/n16_promote.py --run <run_id> --trigger-by "<人名>" --actor-kind human
```

> 以上命令的**数据落点**都是 `<WORKSPACE_ROOT>/…`（当前 = `ENV_ROOT/kb/…`）；
> 本仓 `kb/` 只放程序/schema，不落运行数据。`n1_snapshot.py stage` 需要 `--parent` 与 `--run`，且要求
> `<WORKSPACE_ROOT>/runs/<run_id>/staged/` 下已有新输入（这是 N1 的输入契约）。

---

## 6 红线（继承 `doc/AGENTS.md` §5，本目录额外加粗）

1. `ENV_ROOT/RTL/`、`ENV_ROOT/PKG/` 严格只读；`ENV_ROOT/TB/`、`ENV_ROOT/TESTLIB/` 只读（162 条冻结）。
   **`<WORKSPACE_ROOT>/baselines/**` 不改历史基线**，只新增。
2. 预期值只认文档**位定义表**（铁律 3），绝不迁就 RTL 或"寄存器汇总"表。
3. 数字一律由命令输出复制，**禁手算**；本文件里出现的数字都是引 `06`/`09` 笔记的实测值。
4. 归档只增不改：`<WORKSPACE_ROOT>/baselines/**` 一旦写入即置只读（`chmod 444`），md5 记到目录之外。
5. **N2/N5 必须是确定性脚本**，不许引入模型或随机性；确定性按 **§3.1.1 的两条判据**验证
   （同 `--now` ⇒ 逐字节相同；异 `--now` ⇒ 归一化后相同）。**时间字段是唯一被允许的非确定性**，
   且必须由 `--now` / `KB_NOW` 单一入口注入 —— 不许靠"跑得快、秒级时间戳碰巧相同"蒙过判据（D-2/D-10 类假通过）。
6. 闸门只能由 `gate.py` 写，且 `human_signed` 只在 `actor_kind="human"` 时为真。

---

## 7 变更记录

| 日期 | 版本 | 改了什么 | 为什么改 | 证据 |
|---|---|---|---|---|
| 2026-10-15 | 1 | 建档：目录布局 + 三类 schema + 口径（指纹/段/三桶/条目）+ 偏离 K1~K3 | `CHECKPOINT-20261015-1123.md` §9 第 3 条（ENV_ROOT 历史件） | `kb/schema/*.json`、`kb/tools/kb_lib.py` 自检输出 |
| 2026-10-19 | 2 | 按三根重写 §1（本仓 `kb/`=README+schema+tools；数据在 `<WORKSPACE_ROOT>`）、写权表、节点↔脚本表、用法与红线 1/4；补 `case_state.py`；CHECKPOINT 引用标注为 ENV_ROOT 历史件 | 拆仓后 `kb/` 已分两半，旧表述会让人误以为本仓 `kb/` 有数据 | `doc/spec/ENV_PLUGIN_SPEC.md` §1/§2、`environments.json`、`git ls-files kb` |

> **历史登记里的路径**：下文各「变更登记」中的 `kb/runs/...` 等**运行数据路径**是拆仓前记录；
> 在当前三根下等价于 `<WORKSPACE_ROOT>/...`（当前 = `ENV_ROOT/kb/...`）。内容/指纹未变，
> 只是路径口径迁移，不构成证据篡改。

---

## 变更登记 · N5 可达性接入宏展开（N5-M1 / N5-M4 修复）

**登记日期**：2026-10-15
**改动文件**：`kb/tools/n5_impact.py`（新增 `macro_called_names()` 与宏调用点接入调用图）
**回归自测**：`kb/tools/_selftest_n5_reachability.py`（9/9 PASS，可独立复跑）

### 缺陷
`REHEARSAL_REPORT.md:136` / `:147`：
> N5 静态可达性判据**假阴性**：`tc_pcie_rw_02` 被判 `unreachable`，但 **N9 实测印记真的出现**
> ⇒ 根因是判据**没展开 `FORKJN_FOR_BLK` 宏**。

**决定性证据**：N9 真机全跑产出了印记 `[N6_FPGA_DATE_PCIE] OK 0x0000+0x04 fpga_date = 0x20260708`
（`kb/runs/RUN-20261015-120626/evidence/20261015-125305_tc_pcie_rw_02_1_run.log:252`，sim 141.913 µs）
⇒ 该用例**物理上可达**。判据说它不可达 ⇒ **判据错**，不是用例不可达。

### 根因
`PCIE_REG_RW` / `I2C_SLV_RW` 这类 task 在用例里是以宏**第 2 实参**的形式被调用的：
`` `FORKJN_FOR_BLK(<FOR_END_NUM>, <TF_NAME>, …) ``（宏定义：`TB/LIBS/CBB-LIB/macros_pkg.sv:2447`，
变体 `FORKJN_FOR_BLK_PHASE` 在 `:2462`）。原调用图只用 `name(` 正则 ⇒ 看不见这类调用点 ⇒ 调用图不完整。

### 修法
1. `macro_called_names()`：识别 `` `FORKJN\w*\s*\(\s*[^,()]*,\s*([A-Za-z_]\w*) `` 的第 2 实参为调用点；
   **先剔除 `` `define `` 定义行**（那是宏定义不是调用）；`[^,()]*` 允许跨行与缩进。
2. 宏调用点与普通 `name(` 调用点在 BFS 中**同等对待**。
3. 新增 `called_via_macro`：按**链**判定（可达路径上是否用到过宏调用点）。
   只查 site 所在 task 自身会漏掉"宏那一跳在上一层"——本工程实例：
   `m_run_phase --(宏)--> PCIE_REG_RW --(普通)--> sys_reg_test`。

### 口径结论的变化（`--now 2026-10-15T15:00:00`，阈值 1800 s）
| | 改前 | 改后 |
|---|---|---|
| `must_change`（必改） | 0 | **1** |
| `must_change_unreachable` | 2 | **1** |
| `must_change_over_budget` | 3 | 3 |
| `tc_pcie_rw_02` | `unreachable` | **`live` / `via_macro=True` / feasible=yes（17.6 min）** |
| `tc_bmc_i2c_04_dfx` | `unreachable` | **仍 `unreachable`**（`called_somewhere=False`，文件内确实无调用点） |

**没有放宽口径**：判据仍是"以 `m_run_phase` 为根的调用链可达性"，只是把宏形式的调用点补齐了。
`task-13` 当时上交的裁定 (i)/(ii) 两个选项**都不采纳** —— 物理证据表明这是判据缺陷，不是定义选择。

**确定性**：同一 `--now`（`2026-10-15T15:00:00`）两次运行，`n5_impact.json` sha256 均为 `9ad2458a606fc1e4d46203351f9995fae8ac46d18e379f57e6ec29539cb4e028`（×2）。

---

## 变更登记 · 闸门 schema 进闭环 + N5 删重复实现 + 新增 `adjudication/`

**登记日期**：2026-10-15
**改动文件**：`kb/schema/gate_state.schema.json`、`kb/tools/kb_lib.py`、
`kb/tools/n5_impact.py`、`kb/tools/_selftest_gate_schema.py`（新增）、`kb/README.md`（本登记）
**回归自测**：`kb/tools/_selftest_gate_schema.py`（10/10 PASS）、`kb/tools/_selftest_n5_reachability.py`（9/9 PASS）

### ① F-SCHEMA-01（blocker，verifier 独立复现）：schema 与产物**一词之差**
`gate_state.schema.json` 要求 `anchor.algo = 'sha256-of-canonical-record-without-anchor'`，
而 `kb_lib._anchor_value` 实写 `'…state-without-anchor'` ⇒ `check(obj,"gate_state")` 对**当前脚本写的
每一个** `gates.json` 都失败。归档的 `RUN-20261015-120626/gates.json` 能过，只是因为它恰好是
**legacy 无 anchor** 版本 —— "能过"来自缺陷未覆盖的路径，不代表兼容。

**修法**：锚算法字面量收敛到 `kb_lib._ANCHOR_ALGO` + `_anchor_record()` **单一定义**，
schema 的 `const` 与代码同源（`_selftest_gate_schema.py` 第 4 条断言两者相等，漂移即失败）。

### ② F-SCHEMA-02（major）：schema 名字对不上 + **是死文件**
`check(obj, "gate-state")` 抛 `FileNotFoundError`（落盘是 `gate_state.schema.json`，下划线），
且全仓**没有任何脚本调用**该 schema ⇒ `anchor`/`history` 的结构约束实际未强制。

**修法**：
1. `load_schema()` 做**命名归一**：`gate-state` 与 `gate_state` 解析到同一个文件；
2. **写前校验**：`gate_init()` / `gate_set()` 在 `write_json()` **之前**调用
   `check(st, "gate_state")` ⇒ 状态坏在盘上之前就被拦下（自测第 7/8 条：把 algo 改错一个词，
   `gate_set` 抛 `SchemaError` 且**账本一个字节未动**）。
   *为什么不加在读取侧*：schema 收紧不得让历史归档变得不可读；读侧的完整性由锚复算负责。

### ③ 口径唯一：删掉 N5 的**第二套**宏展开实现
协作期间 `kb/tools/n5_impact.py` 里同时存在两套同判据实现：已登记的 `macro_called_names()`
（`` `FORKJN* `` 的**第 2 实参**）+ 另一套把宏实参注入成行内注释 `// TB_MACRO_EXPANDED: …`
再重跑调用图。两套实现同一条判据即**口径分裂**；且注入的注释会出现在引用的原文行里
（**证据文本与真实文件不一致**）。

**核实**：`TB/LIBS/CBB-LIB/macros_pkg.sv` 只有 `FORKJN_FOR_BLK(:2447)` 与
`FORKJN_FOR_BLK_PHASE(:2462)`，两者的 `TF_NAME` **都是第 2 实参**（不存在 `FORKJN(` 宏）。
删除注入实现后重算，`n5_impact.json` sha256 **逐字节还原**为 `9ad2458a…`、归一化指纹
`ef5318bbd23c5b67bfbd58d55c02c357f5d5ecf8595226a127d17456fff6765a`（与删前 M1 一致）
⇒ 那套注入实现是**纯冗余**。

### ④ 新增 `kb/adjudication/`
本目录唯一一类**给人看的非数据产物**：把"必须由人拍的事"写成可拍板的材料。
首批两份：`I3_dual_count_dispute.md`（口径一 1687 vs 口径二 0）、`C_conflicts_triage.md`（C1—C72）。
写权与纪律见 §1 写权表下方的说明：**只写请求，不写裁决结论**。
