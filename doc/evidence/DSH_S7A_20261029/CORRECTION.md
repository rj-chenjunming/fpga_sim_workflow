# 更正件 · S7A 材料面数字口径（2026-10-29，**只增不改**）

> **性质**：本文件是 [`DSH_S7A_20261029/`](README.md) 冻结证据的**只增更正件**。
> 冻结件（`README.md` / `red-green.md` / `raw/**`）**未被修改、不回填**；原文口径的问题在此更正。
> 触发：独立复核 [`AUDIT-20261029-s7`](../../audit/AUDIT-20261029-s7.md) **P1-1**（已确证）。
> 纪律依据：`AGENTS.md` §5 红线 2（数字一律由命令输出复制）、红线 3（归档只增不改）。

## 1 原口径（错在哪）

| 出处 | 原文 |
|---|---|
| `README.md` §3 / `raw/material_face_before_after.md` | 「总量：S6 全量面 = 528122 B → S7a 的 N6 材料面 = **16757 B**（15470 + 1287），缩小 **96.8%**」 |
| `doc/STATUS.md` §118.2 | 「N6 的 `input/` **528122 B → 16757 B（−96.8%）**」 |

**两个缺陷**：

1. **`16757` 是单目标 dry-run 的数，不是真机数**。`raw/s7a_dry_run.json` 的 `material_face` 明确：
   `target="tc_bmc_i2c_03"`、`staged` 只有 2 件（`TESTLIB/tc_bmc_i2c_03.sv` 15470 + `n6_impact_summary.json` 1287）、
   `total_bytes=16757`。而**真机同一次 attempt** 的记录（`raw/n6_attempt_record_summary.json`）列出 **6 件**材料。
2. **口径不对称**：before 侧 528122 B = **8 个 run 产物**合计（不含任何 TESTLIB）；after 侧却含 TESTLIB 源件
   ⇒ 两侧不是同一个集合，百分比不可比。

## 2 更正后（双口径，数字由命令输出复制）

### 2.1 真机 `input/` 实测（`raw/n6_attempt_record_summary.json` 的 `attempt_workspace.materials`）

| 材料 | 字节 |
|---|---|
| `n6_impact_summary.json`（Host 派生自 `n5_impact.json` 345638 B / md5 `dd1306a4…`） | 1287 |
| `TESTLIB/tc_bmc_i2c_03.sv` | 15470 |
| `TESTLIB/tc_bmc_i2c_04_dfx.sv` | 24985 |
| `TESTLIB/tc_bmc_spi_03.sv` | 17214 |
| `TESTLIB/tc_cpu_i2c_03.sv` | 21282 |
| `TESTLIB/tc_pcie_rw_02.sv` | 20130 |
| **合计** | **100368** |

### 2.2 两个口径的复算（命令见 §3）

| 口径 | before | after | 变化 |
|---|---|---|---|
| **run 产物白名单面**（8 件 → 只留派生的 1 件） | 528122 B | 1287 B | **−99.76%** |
| **同口径 input/ 全量**（before 侧补同样 5 个 TESTLIB = 99081 B ⇒ 627203 B） | 627203 B | 100368 B | **−84.00%** |

> 原「−96.8%」的分母是 `528122 + 15470 = 543592`、分子是「1 个 TESTLIB + 摘要」= 16757（= −96.92%），
> 即拿**单目标**的 after 对**全量 run 产物**的 before —— 既非单目标对单目标，也非全量对全量。

## 3 复算命令（可重放，只读冻结件）

```bash
cd doc/evidence/DSH_S7A_20261029
python3 -c "import json;d=json.load(open('raw/n6_attempt_record_summary.json'));\
ms=d['attempt_workspace']['materials'];print(sum(m['size'] for m in ms), [m['name'] for m in ms])"
# => 100368（6 件：n6_impact_summary.json + 5 个 TESTLIB/*.sv）

python3 -c "import json;d=json.load(open('raw/s7a_dry_run.json'))['material_face'];\
print(d['total_bytes'],[x['name'] for x in d['staged']])"
# => 16757（2 件，单目标 dry-run）
```

## 4 **机制结论不受影响**（与数字更正是两件事）

- `materials_for(node)` 仍是 N6 材料面的**唯一来源**（反向抽检 M1–M3 判红，见审计 §5）；
- 345638 B 的 `n5_impact.json` **确实不再进** N6 `input/`（改由 1287 B 派生摘要承载）；
- 真机 127.234 s 完成、`submit accepted + validation.ok=True` 的事实不变；
- 变的只是**对外报的数字与口径**。

## 5 沿用旧数字的位置（冻结件不改，登记以免误读）

| 位置 | 处置 |
|---|---|
| 本目录 `README.md` §3 | **冻结，不回填**；以本更正件 §2 为准 |
| 本目录 `raw/material_face_before_after.md` | **冻结，不回填**；以本更正件 §2 为准 |
| 本目录 `red-green.md` | **冻结，不回填** |
| `doc/STATUS.md` §118.2 | 由后续 STATUS 节追加**订正**（STATUS 只增，不改写 §118） |
| `doc/agents/开工提示词_S8-复核与D3收口.md` §2 | 后续在该文件加订正注（非冻结件） |

## 6 覆盖缺口（为什么用例没抓住）

`loop/tests/test_n6_material_face.py` 的 `test_n6_input_excludes_full_impact_documents` 用**无 sources** 的
假夹具断言 `total < 16384` ⇒ 对真机「5 目标 = 100368 B」的场景**不敏感**。该缺口登记于
[AUDIT-20261029-s7](../../audit/AUDIT-20261029-s7.md) §4-P1-1 附 G5，处置见 `doc/STATUS.md` 新节。
