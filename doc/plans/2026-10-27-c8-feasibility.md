# C8 评估：能不能产出「通过形态（passed）」夹具（2026-10-27）

> **结论先行**：在本机**不能诚实产出** passed 夹具。三条可能的路都过不去：
> ① drill 回放（证据来自冻结的真实日志，counts≠0，改日志＝伪造证据）；
> ② real 真跑（本机 `/home` 是 **ro 挂载**，连红线允许写的 `SIMLIB_RUN/`/`uvs.setup` 都写不了，
> 且需一次 ≈**21.56 h** 的 N9 真跑）；
> ③ 合成夹具（能造，但违反"夹具＝真实运行"的口径，需你显式要求且三处标死）。
> ⇒ 建议把 C8 登记为**环境阻塞**，并保留本文的产出 runbook，等有写权 + EDA 工具时按单执行。

## 1 什么才算「通过形态」

一条 run 要被判 `passed`，证据链必须自下而上全对（缺一环就不是 passed）：

| 层 | 判据 | 现状 |
|---|---|---|
| N9 执行证据 | 每个用例的 `run.log` 有 `rc=0`、错误标记行 = 0、**预期观测点印记三向一致** | 现有一点（`21.56 h` 的 5 例真实跑）是 `rc` 全 0 但**印记不足** ⇒ 仍是 `not_passed` |
| N10 对账 | 口径一/口径二计数 + 三分类；`verdict` 聚合 | 依赖 N9 证据 |
| N12 报告 | 报告里 `claimed_verdict` 行 = `passed` | 现有夹具是 `not_passed`（`n12_report.md:4`） |
| 闸门/终态 | I2（无待验）∧ I3（计数=0）∧ I4（冲突清零）∧ G3 选 `full_now/subset_only` | I4 已可清零（`§87`），其余仍受 N9 证据制约 |

## 2 三条路的判定

### P1 drill 回放 —— **不可行（且不该做）**

drill 的 N9 是把**冻结的真实证据日志**回放成证据（`long_jobs` 里 `_drill_replay_done`），
日志不改 ⇒ counts 不变 ⇒ 报告必然 `not_passed`。要让回放出 `passed`，只能改那份冻结日志的计数
——那是**伪造环境证据**（红线：失败必须显式、证据只增不改），比"没有 passed 夹具"严重得多。

### P2 real 真跑 —— **本机不可行，需环境侧**

环境里工具是齐的：

```
<ENV_ROOT>/uvs.setup      <ENV_ROOT>/run_tc.py      <ENV_ROOT>/run_uvs_new.sh
```

但：

1. `/home` 是 `ro,nosuid,nodev` 挂载 ⇒ 连红线 11 **允许**写的 `SIMLIB_RUN/` 与 `uvs.setup`
   也写不了（实测 `touch` 报 `Read-only file system`，`§87.1`）；
2. N9 一次真跑按 `§54.2` 实测 **21.56 h**（吞吐 ≈3.8 µs 仿真/秒，5 例），且要 EDA 工具/许可可用；
3. 跑完还要把"通过"冻结成夹具（md5 + README + 演示步骤），否则只是又一条 run。

**产出 runbook（等环境可写时照做）**：

```bash
# 0) 前置：可写数据根（LOOP_WORKSPACE）与可写 SIMLIB_RUN 所在的 ENV_ROOT
# 1) 起服务并新建 real 轮（mode=real；不带 s0_record_id，C12 会拒未准出的 S0）
#    或用 run.sh + POST /api/runs {"baseline":"v0","mode":"real","scenario":"happy"}
# 2) 走到 N4 逐条处置（G1）、N9 真跑（约 21.56 h）、N9 后看 N10/N12 判据
# 3) 判据自检（通过形态的三条硬条件）：
#    - N9 每例 rc=0 且错误标记行=0
#    - 印记三向一致（预期观测点）
#    - N12 报告 claimed_verdict=passed；I2=0 待验、I3 计数=0
# 4) 冻结：复制 run 目录到 workspaces/<env>/fixtures/passed-YYYYMMDD/，
#    生成 md5.txt（md5sum -c 通过）+ README（身份/演示步骤/重建步骤），
#    参考 doc/evidence/DEMO_FIXTURE_20261026.md 的格式
```

### P3 合成夹具 —— **可造，但不建议**

可以在副本上手改 evidence/report 造一个 `passed` 形态的 run 目录。**但它不是真实运行结果**，
而界面没有"合成"徽标 ⇒ 下一个人很可能当成真实通过证据。若要，必须：
目录名 `SYNTHETIC-PASSED-*` + README 首行加粗声明 + STATUS 登记 + 演示话术明确"这是合成形态，
只用于 UI 演示，不代表环境通过"。**默认不做**，除非你明确要"UI 演示用的假夹具"。

## 3 现有夹具矩阵（诚实版）

| 夹具 | 形态 | 能演什么 | 不能演什么 |
|---|---|---|---|
| `workspaces/s0-ws-20261023/runs/RUN-20261024-002609` | **real / failed**（恢复失败） | 失败收口、N4 逐条处置、账本缺失的真实形态 | passed 链路 |
| `workspaces/s0-ws-20261023/fixtures/demo-20261026/runs/RUN-20261026-135835` | **drill / finished**（报告 `not_passed`，G1 4 条落账、G2 accept、G3 milestone_only） | 四屏演示、闸门、逐条处置落账、N13/N14 | "passed 报告 → accept 无需理由 → N16 晋升" |

⇒ 演示话术应说："演示用的是 drill 回放夹具（报告如实是 not_passed，可演示闸门与落账）；
passed 链路的夹具需一次真实通过轮，属环境依赖（C8）。"

## 4 建议

1. **C8 登记为环境阻塞**（blocked-by-env）：阻塞条件 = ① 可写数据根/可写 `SIMLIB_RUN`
   ② EDA 工具与许可 ③ N9 ≈21.56 h 真跑 ④ 一次真实"通过"结果。
2. 优先级取决于你是否需要演示 passed 链路；若只是演示面板/闸门/落账，现有两套夹具够用。
3. 若只是想要"UI 上看到 accept 不需要理由"的效果，**不需要**新夹具：可以在测试/浏览器用例里
   用受控替身（已有 `test_run_sessions.py` 覆盖 `requires_reason` 两种形态），不必造假 run。
