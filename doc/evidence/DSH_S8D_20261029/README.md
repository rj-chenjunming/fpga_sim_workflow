# S8d 证据档（2026-10-29）：事件 `ts` 与注入时钟同源（**共享判据面，单独变更**）

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8D_20261029.md5`。
> 探针与命令的**原始输出**在 `raw/`（`raw/README.txt` 是索引）；正式结论/数字见 `doc/STATUS.md` §127。
> 本轮实现由 `s8d-impl` 完成；Lead 跑收口门与提交。**不声称独立复核**。

## 0 结论

**已收口**（REV-16 §9-8）。事件 `ts` 与投影 `now` 同源 ⇒ drill 下 `silence_s` **不再是夹出来的 0**；
不同源的历史事件**不再伪装成"没有进展"**，而是 `null` + `unavailable_reason="ts_source_mismatch"` +
`no_progress.state="unknown"`，**且不告警**。

## 1 变更（REV-16 §4「事件时间源（S8d 收口）」逐条）

| 文件 | 变更 | 条款 |
|---|---|---|
| `loop/host/progress.py` | `ProgressLog.append` 默认 `ts` → `host/paths.py::now_epoch()`（**唯一时间入口**）；删 `import time`；显式 `ts=` 不变 | ①② |
| `loop/services/agent_view.py` | 新增 `TS_SOURCE_MISMATCH` + 唯一判据 `_ts_ahead_of_now`（严格 `>`）；`age_s`/`silence_s` 不同源 ⇒ `null` + reason；`no_progress` ⇒ `unknown` + 可读 reason，**永不 warn**；`max(0,…)` 仅作防御 | ②③ |
| `loop/tests/test_progress_ts_source.py`（新 18 条） | 特征 3（2 条按新契约改写）+ 新契约 12 + 迁移 3 | §7 |
| `loop/tests/test_agent_view_projection.py`（改 4 条） | `..._silence_clamped_non_negative` → `..._silence_unknown_when_ts_source_differs`（钉旧行为 → 钉新契约）+ 3 条增量字段断言 | §2.1/§3.1 |

## 2 drill 对照（`LOOP_NOW=2026-10-28T12:00:00`，`raw/00-before-probe.txt` vs `raw/05-after-probe.txt`）

| 项 | 改前 | 改后 |
|---|---|---|
| 事件 `ts` | 墙钟 `1793254250.27279`（比注入 `now` 晚 **94250.27 s**） | `1793160000.0` = `now_epoch()`（**== now**） |
| `silence_s` / `age_s` | `0` / `0`（**夹出来的**） | `0` / `0`（**算出来的**）；注入 `now+700` ⇒ `silence_s=700`、`warn`「无进展 11 分钟」 |
| 冷读历史墙钟事件 | `silence_s=0`、`no_progress=ok`（伪装成没进展） | `silence_s=None`、`age_s=None`、`no_progress=unknown`、`unavailable_reason=ts_source_mismatch`、**不告警** |
| 事件文件 | — | **md5 前后一致**（不回填，有用例钉住） |

## 3 红线 grep（`raw/07-redline-grep-and-diffstat.txt`）

```
grep -n "time.time()" loop/host/progress.py   → 无输出（exit=1）
grep -c "time.time()" loop/host/progress.py   → 0
grep -n "^import time|^from time" …progress.py → 无输出（exit=1）
```

## 4 迁移影响面（逐项判定）

1. **事件流**：键/格式不变，只换默认时间源；显式 `ts=` 不变；注入时钟不可解析 ⇒ **显式 `ValueError`**（不回退墙钟，有用例）。
2. **无进展判据**：只新增 `null` + reason 分支与 warn 抑制；判据仍只在 `agent_view` 一处（红线 8），**前端未改**。
3. **drill 夹具 `RUN-2026…`**：实测夹具**不含 ProgressLog 事件流**（事件在 `STATE_DIR/events`、不随夹具分发）⇒ **夹具数据零改动**；变的只是 drill 期间**新写出**的事件 `ts`。
4. **固定 `LOOP_NOW` 的流程用例**逐个查（全绿）：此前它们的"假静默"达数十年量级（因墙钟 ts 远晚于注入 now），现在差值为 0 —— **这正是要修掉的假告警**。
5. **浏览器时间断言**：全部 `page.route` 桩数据（无真实后端/无 `LOOP_NOW`）⇒ 不受影响；OBS-03 子集实跑 **37 passed**。
6. **`_choose` 的同 `ts` tie-break（迁移修复）**：事件 `ts` 同源后 drill 里同 run 事件 `ts` 全相同，只按 `ts` 会退化成"按声明顺序取第一个"⇒ 卡片指旧节点。改为 `max((last_ts, last_seq))`；**`ts` 不同时行为逐字不变**，有用例。规格 REV-16 §4 已补一条迁移说明（不是新判据）。

## 5 未决（照实登记，见 REV-16 §9-18）

- **方向性限制**：只有"事件 `ts` 晚于注入 `now`"可**直接判别**；反方向（`ts` 远早于 `now`）与"真的长期静止"不可区分 ⇒ 一律 `unknown`，不猜、不告警。
- **`elapsed_s` 未纳入 null 面**：§4 只点名 `silence_s`/`last_event_age_s`；纳入须单独变更 + 留证。

## 6 不声称

- 不声称 `unavailable_reason` 已被前端渲染成中文（前端未改；本轮靠 `state=unknown` + `silence_s=null` 显示"未知"）。
- 不声称独立复核（实现者自测）。
