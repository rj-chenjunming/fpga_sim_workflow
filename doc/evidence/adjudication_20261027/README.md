# 冲突裁决落账快照（2026-10-27，72 条）

> **这是什么**：`kb/tools/adjudicate_conflicts.py` 在**派生数据根副本**上产出的两份落账文件快照，
> 由 `doc/evidence/conflicts_sign_20261027.sh` 一次跑完（68 条批量 G1–G9 + 4 条 Tier B-core）。
> **生效状态：未生效**。本机 `<ENV_ROOT>/kb` 只读，写不到真实数据根；本目录是"判据 + 落账内容"的
> 可复核快照，不是运行时权威（运行时权威仍是数据根里的 `conflicts/conflicts.json`）。

## 1 身份与来源

| 项 | 值 |
|---|---|
| 生成时间 | 2026-10-27（Asia/Shanghai） |
| 执行 actor | `human:chenjunming` |
| 代录声明 | 人于 2026-10-27 明示授权代录；每条 `resolution` 末尾**逐条**带「（人工批示，Host 工具代录 2026-10-27）」，不冒充亲笔 |
| 写入工具 | `kb/tools/adjudicate_conflicts.py` md5 `021820caad308921984de35db47cd5e6` |
| 抽取合并 | `kb/tools/n1_conflicts.py` md5 `6be49e83aad5b063f3677643bfeff66f` |
| 分组判据 | `<ENV_ROOT>/kb/adjudication/C_conflicts_triage.md` md5 `bc862a6855cf48f5af4a6a70294f5c87`（G1–G9 + Tier B） |
| 原始清单 | `<ENV_ROOT>/kb/conflicts/conflicts.json` md5 `1d0b95468e8be451955a0f2443c478be`（72 条全 open / 全阻断） |
| 快照生成时的数据根 | 派生副本 `<repo>/.env-copy/kb`（由 `loop/spikes/run_env_layer_checks.sh` 预置；不在 git 内） |

## 2 文件与指纹

| 文件 | md5 | 内容 |
|---|---|---|
| `adjudication.json` | `d6ec87796f72f40dcfd124cbfc7af991` | 72 条 human 裁决记录（append-only，每条带 `sha256` 锚） |
| `conflicts.json` | `47300360ba208012d262bc673a1d07d9` | 合并后清单：72 条 `status=ruled`、`blocks_release=false` |

裁决结果：`[stat] conflicts=72，仍阻断发版=0`；`[verify] 裁决记录=72（去重后 72）；锚与合并一致性：全部通过`。

> **注**：上表快照取自签署当时的文件。随后为验证「重跑抽取不丢裁决」，对副本又跑了一次
> `n1_conflicts.py`（输出 `[merge] adjudication.json：72 条裁决已合并` + 仍阻断 0），
> 该次重跑会给 `conflicts.json` 增加 `generated_at` ⇒ 副本当前文件与本快照 md5 不同，属预期。

## 3 如何让它"生效"（在有写权的数据根上）

本机 `ENV_ROOT` 只读（实测：`/home` 是 `ro,nosuid,nodev` 挂载，`touch` 报 `Read-only file system`）
⇒ 本轮**没有**写真实数据根（真实仍为 72 条阻断）。生效需要可写数据根：

**方式 C（推荐，一条命令）**：`bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根>`
（先 `--dry-run` 体检；脚本会校验本目录快照指纹、落账、重跑抽取合并、`--verify`，
并打印 I4 读数 / G3 `full_now|subset_only` 提交前检查 / N16 blockers 是否仍含 `I4_CONFLICTS_UNCLEARED`）。

另两种等价方式（手工）：

```bash
# 方式 A（推荐）：把快照里的裁决文件放进目标数据根，再让抽取器合并
WS=<可写数据根>            # 该数据根的 conflicts/ 目录
cp doc/evidence/adjudication_20261027/adjudication.json "$WS/conflicts/"
python3 -B kb/tools/n1_conflicts.py --outdir "$WS/conflicts"     # 抽取 + 合并裁决
python3 -B kb/tools/adjudicate_conflicts.py --outdir "$WS/conflicts" --verify

# 方式 B：在目标数据根上重新跑一次签署脚本（等价，且会重新签发时刻）
ACTOR=human:chenjunming NOTE_SUFFIX="（人工批示，Host 工具代录 2026-10-27）" \
  OUTDIR="$WS/conflicts" bash doc/evidence/conflicts_sign_20261027.sh
```

生效后 I4 的消费口径（`KbSources.from_workspace` + `contracts._conflict_summary`）应为
`blocks_release=0, open=0`；G3 的 `full_now/subset_only` 才不再被 I4 在提交前拒绝。

## 4 边界（如实）

1. 本快照**不是**亲笔签署：actor 是 `human:chenjunming`，但写入由 Host 工具执行，代录事实写在每条
   `resolution` 与本节；若要亲笔，请在有写权环境用方式 B 重签（重签为追加记录，不改历史）。
2. 真实 `ENV_ROOT` 全程只读未写入；这批裁决**尚未**影响任何真实轮次的 I4 判定。
3. 4 条 Tier B-core 的取值依据见 `doc/evidence/CONFLICTS_SIGNING_20261027.md` §2.5
   （C2/C11/C38 以位定义为准、C58 以 `DFX_VERSION` 为基准）；它们仍是"人给的方向"，
   作者若后续给出不同口径，按追加改判处理，不回填本快照。
