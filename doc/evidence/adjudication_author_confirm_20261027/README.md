# 4 条 Tier B-core 的作者确认快照（D1，2026-10-27）

> **性质**：`doc/plans/2026-10-27-d-group-rulings.md` **D1 = A（确认 4 条现口径）** 的落账快照。
> **只增不改**：本目录冻结（`chmod 444`），md5 记在 `md5.txt`；后续若改判，另建目录，不回填本目录。
> **与本仓其它快照的关系**：72 条裁决的原始快照是 `doc/evidence/adjudication_20261027/`（md5 `d6ec877…`/`47300360…`），
> 本目录是它**追加 4 条作者确认之后**的状态，不替代它。

## 1 这次追加了什么

| id | 冲突 | 原口径（2026-10-27 人批示） | 追加记录（本次） | blocks_release |
|---|---|---|---|---|
| C2 | `0x0004 fpga_date`：汇总 L414 `0x2023_0804` ↔ 位定义 L447 `2023_0911` | 位定义 `2023_0911` | 原口径 + "作者确认 2026-10-27（Host 工具代录；追加记录，不改前条）" | False |
| C11 | `0x0080 fpga_test`：汇总 L635 `0x5555aaaa` ↔ 位定义 L735 `0x0` | 位定义 `0x0` | 同上 | False |
| C38 | `i2c_polling_cfg`：汇总 L1409 `0x10` ↔ 位定义 L1630/L1632 推导 `0xF0` | 逐位推导 `0xF0` | 同上，并写明**依赖假设**：`REV` bits[3:1] 复位值按 0 处理（原文 L1631 未给值） | False |
| C58 | 版本自洽性：`DFX_VERSION` L620 `0x25092913`、修订履历 L276–L278、`fpga_date` L447 `2023_0911` | 以 `DFX_VERSION` 为基准，`0x0004` 的 2023 值记历史遗留 | 同上 | False |

## 2 落账动作（可复算）

```bash
# 1) 可写数据根（真实 <ENV_ROOT>/kb 是 ro 挂载，写不进）
bash loop/spikes/provision_dev_workspace.sh --force --quiet
# 2) 先落 72 条原始快照（快照指纹校验通过；输出见下方读数）
bash loop/spikes/apply_conflict_adjudication.sh --workspace <repo>/.dev-ws
# 3) 追加 4 条作者确认（human-only；只增不改；每条约 1 s）
loop/.venv/bin/python -B kb/tools/adjudicate_conflicts.py \
  --outdir <repo>/.dev-ws/conflicts --actor human:chenjunming --id <C2|C11|C38|C58> \
  --status ruled --resolution "<原口径>。作者确认 2026-10-27（Host 工具代录；追加记录，不改前条）"
# 4) 校验
loop/.venv/bin/python -B kb/tools/adjudicate_conflicts.py --outdir <repo>/.dev-ws/conflicts --verify
```

## 3 实测读数（命令输出复制）

- 落 72 条快照后：`[after] I4 读数：conflicts=72，blocks_release=0，open=0`；
  `[g3] full_now 提交前检查：通过`、`[g3] subset_only 提交前检查：通过`；
  `[n16] after blockers=[I1_UNRESOLVED_ENTRIES, I2_CASES_PENDING, I3_EVIDENCE_MISSING, E2_EVIDENCE_ARCHIVE_EMPTY, F_N16_04_STAGING_RESIDUE]`，
  `I4 在列=False`（apply 脚本自印；与 STATUS §87.3 的 before/after 同口径）。
- 追加 4 条后：`[verify] 裁决记录=76（去重后 72）；conflicts=72，仍阻断=0`；
  `[verify] 锚与合并一致性：全部通过`。
- 每条被确认的 id 都有 **2 条**历史记录（原裁决 + 本次确认），`blocks_release=True` 的记录数 = **0**。
- 4 条新记录的 `adjudicated_at` = `2026-10-27T13:52:49～50+0800`，`sha256` 前缀分别为
  `79ed535a86ea`（C2）、`e73529d889de`（C11）、`311ce343434b`（C38）、`22d29e9f466a`（C58）。

## 4 本文件与两份 json 的指纹（红线 10）

| 文件 | md5 |
|---|---|
| `adjudication.json`（76 条记录 / 72 去重） | `a2e399a7c22fa0c04dc13fe8187c3396` |
| `conflicts.json`（72 条，仍阻断 0） | `21cc93005f9a6a151ec4f76bffab2e7f` |

## 5 边界（没做的事）

- **没有写真实数据根**：本机 `<ENV_ROOT>/kb` 是 `ro,nosuid,nodev` 挂载 ⇒ 上面所有写入都落在派生数据根
  `<repo>/.dev-ws`（跑完已 `--cleanup` 删除）。真实根生效仍属 **E1**（拿到可写数据根后跑
  `apply_conflict_adjudication.sh --workspace <真实数据根>`）。
- **没有改任何判据**：4 条仍是 `status=ruled`、`blocks_release=false`，只是把"作者确认"这一事实写进记录。
- **没有覆盖历史**：同一 id 的第二次裁决是**追加**记录（工具强制），原记录与其 `sha256` 锚全部保留。
