# 演示夹具：`RUN-20261026-135835`（2026-10-26 冻结）

> **这是什么**：一套**能完整演示**的闭环运行，冻结自本机数据根
> `workspaces/s0-ws-20261023/runs/RUN-20261026-135835`（2026-10-26 由当前代码跑出的 drill，
> 状态 `finished`）。它的用途是**给人演示工作台**：三道闸门都有决策，G1 的**逐条处置记录真的落账了**。
>
> **为什么需要它**：另两套 run 都演示不了逐条处置那一屏 ——
> `RUN-20261024-002609`（2026-10-24 真实轮）G1 签完名后进程恢复失败（`view.json` 里
> `error=恢复失败…fingerprint mismatch`），落账在恢复后的闸门 chunk 里写，因此**一条都没记下**，
> G2/G3 也没走到；`RUN-20261015-120626`（归档演练轮）则早于落账功能。

## 1 内容与身份

| 项 | 值 |
|---|---|
| run_id | `RUN-20261026-135835` |
| 模式 / 场景 | `drill` / `happy` |
| 状态 | `finished`（完整跑完） |
| 闸门 | G1 `confirmed` · G2 `accept` · G3 `milestone_only` |
| G1 逐条处置 | **4 条**（按唯一 `entry_id`；每条带理由），来自 `decisions/G1_diff_confirm.json` |
| 硬阻断快照 | G1 1 条 · G2 2 条 · G3 1 条（各自 `decisions/<gate>.json` 的 `hard_block`） |
| 文件数 | 103（含 `md5.txt` 清单 1 个，故清单 103 行对应 103 个被校验文件） |
| 体量 | 14 MB |

关键件 md5（其余见 `md5.txt`，全目录可逐值校验）：

```
2e0ed2c98aa19f0cfe4ea6c109a280c5  runs/RUN-20261026-135835/decisions/G1_diff_confirm.json
752105e273481a49dc4285d5af119ed9  runs/RUN-20261026-135835/decisions/G2_report_accept.json
9c7c9a09fef7afe613ced8a4535be2e9  runs/RUN-20261026-135835/decisions/G3_regression_decision.json
e295baebf57fa9ca171521493f3783f6  runs/RUN-20261026-135835/gates.json
661eb086df03a49296130385972e6ed5  runs/RUN-20261026-135835/view.json
```

## 2 怎么用它演示

夹具目录本身就是一段数据根的 `runs/` 片段，把它放进一个**可写**数据根即可（不要就地改夹具）：

```bash
FI=<repo>/workspaces/s0-ws-20261023/fixtures/demo-20261026
WS=<repo>/.demo-ws            # 任意可写目录
mkdir -p "$WS/runs"
cp -a "$FI/runs/RUN-20261026-135835" "$WS/runs/"

cd <repo>/loop
LOOP_WORKSPACE="$WS" bash run.sh      # 默认 127.0.0.1:8099
```

浏览器打开后选 `RUN-20261026-135835`，能看到的四屏：

1. **运行监控** —— 四段流程都走过、状态 `finished`；
2. **人工闸门** —— G1 已决策 `confirmed`，材料区 4 条修订点；
3. **N4 节点面板** —— 顶部「共 4 条修订点，**已处置 4 条**」，每条后面是处置结论 + 理由
   （即 P-18「已决策 run 逐条处置重建」，数据来源是 `decisions/G1_diff_confirm.json` 而不是 `gates.json`）；
4. **N13 / N14** —— G2 `accept`、G3 `milestone_only`，各自带签署当时的硬阻断快照。

> 如果只演示 N4/N13/N14 三屏，数据根里没有 `baselines/`、`index/`、`conflicts/` 也能看（这些面板只读 run 目录）；
> 若要跑新 run 才需要完整数据根（见 `loop/README.md` 的预置脚本）。

## 3 校验

```bash
cd <repo>/workspaces/s0-ws-20261023/fixtures/demo-20261026
md5sum -c md5.txt --quiet && echo OK        # 103 个文件逐值校验
```

## 4 约束

- **只增不改**：要改动请复制到别处改，不要就地编辑本夹具；一旦校验不过，说明内容已漂移。
- 本夹具**不入 git**（`workspaces/**` 的数据默认不入库，见 `workspaces/README.md`）；
  它的身份与来源另记在 `doc/evidence/DEMO_FIXTURE_20261026.md`，
  万一目录丢失，可按那里的说明用当前代码重跑一轮 drill 复现。
