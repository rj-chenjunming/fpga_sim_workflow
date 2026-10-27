# 冲突清单 68 条批量裁决 · 待签草案（2026-10-27）

> **状态：已定值（2026-10-27 人裁决），待人工执行签字。** 本文件只准备**判据 + 命令**；裁决必须由**人**执行
> （`kb/tools/adjudicate_conflicts.py` 强制 `--actor human:<name>`，模型不得自签，schema 原文同理）。
> 草案中的 `human:<你的名字>`、`<可写数据根的 conflicts/>` 都是占位符，落地前替换。

## 0 身份（引用冻结文件必带 md5，红线 10）

| 对象 | 位置 | md5 |
|---|---|---|
| 冲突清单（真实 72 条，全 `open` / 全 `blocks_release=true`） | `<ENV_ROOT>/kb/conflicts/conflicts.json` | `1d0b95468e8be451955a0f2443c478be` |
| 分组与逐条摘要来源（764 行；G1–G9 / B1–B4 / Tier B 19 条） | `<ENV_ROOT>/kb/adjudication/C_conflicts_triage.md` | `bc862a6855cf48f5af4a6a70294f5c87` |
| 裁决写入器 | `kb/tools/adjudicate_conflicts.py` | `021820caad308921984de35db47cd5e6` |
| conflicts schema（**未改**） | `kb/schema/conflicts.schema.json` | `434387c12a972d2ca113c09cbc6cb6ac` |
| 抽取器（含裁决合并） | `kb/tools/n1_conflicts.py` | `6be49e83aad5b063f3677643bfeff66f` |

**分组去重口径**：本文件按 triage §4.1 的 `category contains <类型>` 判据分组，但**保证一条 id 只入一组**
（先命中先归属，顺序 G1→G9），避免同一条被两条不同结论重复裁决；triage §4.3 的并集自检仍成立
（本文件 68 条 = 72 − 4 条 core）。**裁决规则原文照抄 triage，不改判据。**

## 1 批量名单（68 条 = 72 − Tier B-core 4 条）

| 组 | 主题 | 条数 | 成员 |
|---|---|---|---|
| G1 | 地址 / offset / 区间笔误 | 12 | C19,C23,C28,C32,C33,C35,C36,C37,C41,C46,C48,C68 |
| G2 | Reset 值冲突（汇总 ↔ 位定义） | 4 | C1,C3,C15,C70 |
| G3 | R/W 属性冲突 | 7 | C4,C8,C16,C43,C44,C49,C69 |
| G4 | 位段重叠 / 跳空 / 位宽疑漏 | 6 | C7,C9,C18,C25,C27,C39 |
| G5 | 缺失 / 漏列 / 保留区间错标 / 位定义缺表 | 10 | C5,C6,C12,C14,C31,C40,C42,C52,C54,C64 |
| G6 | 命名 / 复制粘贴残留 | 10 | C10,C13,C17,C24,C26,C45,C51,C59,C60,C62 |
| G7 | 章节编号 / 行格式 / 数值书写 | 13 | C20,C21,C22,C29,C30,C47,C53,C61,C65,C66,C67,C71,C72 |
| G8 | 器件规模 / 接口数量 / 容量不一致 | 4 | C34,C50,C55,C63 |
| G9 | 模板 / 元信息残留 | 2 | C56,C57 |
| | **合计** | **68** | （另有 4 条 core 见 §3） |

## 2 执行命令（按组，一组一条）

先设两个变量（按你的环境改）：

```bash
REPO=/home/work/chenjunming/change-impact-loop
# 可写数据根的 conflicts 目录：本机 ENV_ROOT 只读，正式签请指向有写权的数据根；
# 想先演练可用派生副本：OUTDIR="$REPO/.env-copy/kb/conflicts"
OUTDIR="<可写数据根的 conflicts/>"
ACTOR="human:<你的名字>"
```

```bash
python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C19,C23,C28,C32,C33,C35,C36,C37,C41,C46,C48,C68 --status ruled \
  --resolution "地址以文档自洽一方为准（段头∨总表∨实际占用取一致者），登记文档勘误；G1 批量裁决（triage G1）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C1,C3,C15,C70 --status ruled \
  --resolution "Reset 以位定义表为准，汇总表值登记勘误；G2 批量裁决（triage G2）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C4,C8,C16,C43,C44,C49,C69 --status ruled \
  --resolution "R/W 以位定义表为准（状态类应只读，不做写回比对）；G3 批量裁决（triage G3）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C7,C9,C18,C25,C27,C39 --status ruled \
  --resolution "位段按同表规律修正（重叠与跳空按笔误处理）；G4 批量裁决（triage G4）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C5,C6,C12,C14,C31,C40,C42,C52,C54,C64 --status ruled \
  --resolution "以位定义表补全汇总与位定义；无定义者（C42）用例按已定义范围裁剪并显式标注未覆盖；G5 批量裁决（triage G5）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C10,C13,C17,C24,C26,C45,C51,C59,C60,C62 --status ruled \
  --resolution "命名以位定义表/字段名为准，汇总侧拼写登记勘误；用例按 entry_id 关联而非 name；G6 批量裁决（triage G6）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C20,C21,C22,C29,C30,C47,C53,C61,C65,C66,C67,C71,C72 --status ruled \
  --resolution "编号与格式勘误，不改变寄存器语义；用例引用一律带行号；G7 批量裁决（triage G7）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C34,C50,C55,C63 --status ruled \
  --resolution "以位定义表可枚举范围为准写入索引，文档口径差异登记，用例矩阵按已定义范围；G8 批量裁决（triage G8）"

python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --ids C56,C57 --status ruled \
  --resolution "模板/元信息残留，无寄存器语义；G9 批量裁决（triage G9）"
```

跑完立刻核对：

```bash
python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --list
python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --verify
# 预期：--list 显示仍阻断发版 = 4（只剩 C2/C11/C38/C58）；--verify 全部一致
```

## 2.5 定值记录（2026-10-27，人给定；命令见 `conflicts_sign_20261027.sh`）

| id | 定值 | 依据（人给的方向） |
|---|---|---|
| C2 | 以**位定义** `2023_0911` | 两表打架时以位定义表为准（逐位、可执行）；汇总 `0x2023_0804` 登记勘误 |
| C11 | 以**位定义** `0x0` | 同上；汇总 `0x5555aaaa`（自测图案）登记勘误 |
| C38 | 以**位定义逐位推导** `0xF0`（bit7:4=0xf、bit0=0） | 同上；汇总 `0x10` 登记勘误 |
| C58 | 以 **`DFX_VERSION=0x25092913`（≈2025-09-29）** 为版本/日期基准 | 版本基准取"可自证的最新受控版本"；`0x0004` 的 2023 值登记为历史遗留 |

68 条批量结论见 §2 各组命令内的 `--resolution`（原文即 triage §4.1 的批量规则）。

**一键签署**（执行人 = 人；脚本不含名字）：

```bash
ACTOR=human:<你的名字> OUTDIR=<可写数据根的 conflicts/> \
  bash doc/evidence/conflicts_sign_20261027.sh --dry-run   # 先空跑
ACTOR=human:<你的名字> OUTDIR=<可写数据根的 conflicts/> \
  bash doc/evidence/conflicts_sign_20261027.sh             # 真签 + 自动 --list/--verify
```

## 3 4 条 Tier B-core（定值已给，见 §2.5；下表保留两方取值备查）

triage §5.1 点名的 4 条：两个取值都合法，批量规则替不了。

| id | 段 / 类型 | 两方取值 | 影响 |
|---|---|---|---|
| C2 | 0x0000 / RT | `0x0004` 汇总 Reset `0x2023_0804` ↔ 位定义 `2023_0911` | 都是合法日期；影响"当前 BIN 发布日期"基准 |
| C11 | 0x0100 / RT | `0x0080 fpga_test` 汇总 `0x5555aaaa` ↔ 位定义 `0x0` | 语义完全不同（前者是自测图案）；**用例读回比对会直接判错** |
| C38 | 0x4000 / RT | `i2c_polling_cfg` 汇总 `0x10` ↔ 位定义推导 `0xF0`（bit0=0、bit7:4=0xf） | polling 通道使能初值判断错误 |
| C58 | ALL / RT | `DFX_VERSION` Reset `0x25092913`（≈2025-09-29）晚于修订记录最后日期 `2025/07/03`；`0x0004` 又写 2023 | 三者不可能同属一个受控版本 ⇒ 决定"当前 BIN 的版本/日期基准" |

每条三种合法处置（都要你签）：

```bash
# ① 以位定义表为准（与批量同规则）
python3 "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$OUTDIR" --actor "$ACTOR" \
  --id C2 --status ruled --resolution "以位定义表为准（2023_0911），汇总 0x2023_0804 登记勘误"
# ② 以汇总表为准
... --id C2 --status ruled --resolution "以汇总表为准（0x2023_0804），位定义登记勘误"
# ③ 暂不定值：确认"这是真冲突、等作者确认" ⇒ 仍阻断发版（confirmed 强制 blocks_release=true）
... --id C2 --status confirmed --resolution "待作者确认当前 BIN 发布日期；在确认前该冲突仍阻断发版"
```

## 4 边界与限制（如实）

1. **模型不签**：本文件的所有命令都由人执行；没有本文件被执行的记录 ⇒ `--list` 仍是 0 条裁决 / 72 条阻断。
2. **真实数据根只读**：本机 `<ENV_ROOT>/kb` 不可写。演练可在派生副本
   （`<repo>/.env-copy/kb/conflicts`，由 `loop/spikes/run_env_layer_checks.sh` 预置）上做；
   正式生效需要可写数据根（`LOOP_WORKSPACE`）。
3. **批量裁决的口径是"以位定义表为准/登记勘误"**，不等于"文档已改"：接口文档是冻结资产，
   勘误登记走 `pending.json` 的 `doc-owner` 流程，本文件不触碰文档。
4. 4 条 core 若标 `confirmed`，`blocks_release` 仍为 `true` ⇒ **I4 不会清零**（这是有意的：
   没定值前不能发版）。要清零必须先给出取值。
