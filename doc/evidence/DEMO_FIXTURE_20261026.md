# 演示夹具身份档案：`RUN-20261026-135835`（2026-10-26 冻结）

> **这份证据证明什么**：本机有一套**可完整演示**的闭环运行夹具，三道闸门都有决策、
> G1 的逐条处置**真的落账**，且已按「复制到独立数据根 → 起服务 → 查 N4 面板」的演示路径实测通过。
> **不证明**：判据通过（本轮报告是 `not_passed`）、环境就绪、S0-b 已接入。
> 数字一律由命令输出复制（`AGENTS.md` 红线 2）。

## 1 为什么需要这套夹具

另两套 run 都演示不了「已决策 run 的逐条处置重建」那一屏：

| run | 情况 | 能否演示逐条处置 |
|---|---|---|
| `RUN-20261024-002609`（2026-10-24 真实轮） | G1 已签署（`signed_at=2026-10-24T00:29:11+0800`），随后**恢复失败**（`view.json` 的 `error=恢复失败…fingerprint mismatch`），run 转 `failed`；落账在「恢复后闸门 chunk」里写，故**未落账**，G2/G3 也未走到 | ❌ 面板只能显示"未留存" |
| `RUN-20261015-120626`（归档演练轮夹具） | 早于落账功能（`append_decision_ledger` 于 `e7528fe`，2026-10-24 才进仓） | ❌ 同上 |
| **`RUN-20261026-135835`**（本夹具） | 当前代码跑出的 drill，`finished`；三门决策齐全；G1 落账 4 条 | ✅ |

## 2 身份

| 项 | 值 |
|---|---|
| 夹具目录 | `workspaces/s0-ws-20261023/fixtures/demo-20261026/`（**不入 git**，见 `workspaces/README.md`） |
| 内含 | `runs/RUN-20261026-135835/**` + `md5.txt`（103 行）+ `README.md`（用法） |
| 体量 | 14 MB |
| 来源 | 本机数据根 `workspaces/s0-ws-20261023/runs/RUN-20261026-135835`，即
[SPEC-REV-12 验证](SPEC_REV05_VERIFY_20261026.md) 用的那轮 drill（actor `human:lead-verify-20261026`） |
| 状态 | `finished`，`mode=drill`，`scenario=happy` |
| 闸门 | G1 `confirmed` / G2 `accept` / G3 `milestone_only` |
| G1 逐条处置 | 4 条（按唯一 `entry_id`），全部 `confirmed`，理由 `drill 夹具回放工程验证（非用户确认）` |
| 硬阻断快照 | G1 1 条（`I4_CONFLICTS_UNCLEARED`）/ G2 2 条 / G3 1 条 |

关键件 md5（全量见夹具内 `md5.txt`，可 `md5sum -c` 逐值校验）：

```
2e0ed2c98aa19f0cfe4ea6c109a280c5  runs/RUN-20261026-135835/decisions/G1_diff_confirm.json
752105e273481a49dc4285d5af119ed9  runs/RUN-20261026-135835/decisions/G2_report_accept.json
9c7c9a09fef7afe613ced8a4535be2e9  runs/RUN-20261026-135835/decisions/G3_regression_decision.json
e295baebf57fa9ca171521493f3783f6  runs/RUN-20261026-135835/gates.json
661eb086df03a49296130385972e6ed5  runs/RUN-20261026-135835/view.json
```

## 3 实测（按演示路径跑通）

复制夹具到独立可写数据根，起服务，查面板：

```bash
mkdir -p <WS>/runs
cp -a <repo>/workspaces/s0-ws-20261023/fixtures/demo-20261026/runs/RUN-20261026-135835 <WS>/runs/
cd <repo>/loop && LOOP_WORKSPACE=<WS> bash run.sh
```

实测输出（`GET /api/runs` 与 `GET /api/runs/RUN-20261026-135835/nodes/N4`）：

```
/api/runs   -> [('RUN-20261026-135835', 'finished', 'drill')]
run_status = finished | run_terminal = True
state      = decided | decision = confirmed | note = None          # note=None ⇒ 不再报"未留存"
counts     = {'entries': 4, 'revision_points': 4, 'disposed': 4, 'unresolved': 7,
              'unresolved_points': 4, 'hard_block': 1, 'pending_cases': 0,
              'conflicts_open': 0, 'conflicts_total': 0}
逐条处置   = [('TCS9620_MAC_TOP.v', 'confirmed'), ('dom_engine_top.v', 'confirmed'),
              ('pcie_register.v', 'confirmed'), ('uart_top.v', 'confirmed')]
hard_block = ['I4_CONFLICTS_UNCLEARED']
```

⇒ 「共 4 条修订点，已处置 4 条」这一屏的数据来源是 `decisions/G1_diff_confirm.json`，
不是 `gates.json`（口径见 [业务规格 §7](../spec/CHANGE_IMPACT_LOOP_SPEC.md) 与
[编排规格 §10.4.2](../spec/LOOP_ORCHESTRATION_SPEC.md)）。

## 4 万一夹具目录丢失，怎么重建

用当前代码跑一轮 drill（秒级，`LOOP_DRILL_FIXTURE=fixtures/drill-real-20261024` 回放），
然后通过闸门 API 提交三道门决策 —— G1 提交覆盖**全部** `entry_id` 的 `entry_decisions`、
G2 带 `reason` 的 `accept`（失败报告必须给理由）、G3 `milestone_only`；
actor 用固定的验证身份。做法与 [SPEC-REV-12 验证](SPEC_REV05_VERIFY_20261026.md) §1 相同。
重建后须重新生成 `md5.txt` 并更新本档案（证据只增不改：新增一节记新 md5，不回填旧值）。
