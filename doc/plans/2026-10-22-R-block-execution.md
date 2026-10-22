# R 门缺陷收口与网页重构执行计划（2026-10-22）

> 依据：[开工提示词](../agents/开工提示词_R门缺陷与网页重构.md)、[下一轮 SpecDD 计划](2026-10-22-next-iteration-specdd.md)、
> [内网批次复核](../audit/AUDIT-20261022-intranet-batch-review.md)（R1–R5）、[STATUS §33–§38](../STATUS.md)。
> 本计划是本轮**执行计划**，只写切片/owner/落点/验收/回退；实测数字只进 `doc/STATUS.md` 与本轮证据文件。
> 采样：`HEAD=5e2f8cb`（开工）→ 契约先行提交 `8669cd7`（R1/R2/R3/R4/R5 规格条款）。

## 1 阶段 A 采样（Lead 执行）

| 步骤 | 事实 | 结果 |
|---|---|---|
| V0 三根/版本 | `git rev-parse HEAD`、`uname`、`git branch` | `HEAD=5e2f8cb0149a95823d3f8ebd4cd0c729398fccf6`，`main`，Linux x86_64；`ENV_ROOT` 存在但 `/home` 只读；`CPython 3.11.7` |
| V1 离线浏览器 | `verify` / `install` / `check` | verify `PASS`；install 装 `playwright-1.64.0`、`greenlet-3.2.5`、`pyee-13.0.1`；`check` 首次 `FAIL`（系统 Chrome 因 `$HOME` 只读崩溃），设可写 `HOME`/`XDG_*` 后 `PASS`，`version=152.0.7977.75` |
| V2 软件层特征基线 | `spikes/run_software_checks.sh` + 浏览器环境变量 | 见 §4 与 STATUS §39 |
| V3 浏览器回归 | `spikes/browser_offline.py run` | `41 passed`（0 skip），HOME 可写 + `LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome` |

**环境事实（新增，必须写进命令）**：安装 playwright 后 `tests/browser` 不再模块级 skip；它们需要
（a）`LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome`（或随包 Chrome）与（b）**可写 `HOME`/`XDG_CONFIG_HOME`/`XDG_CACHE_HOME`**
（系统 Chrome 在 `$HOME` 只读时以 SIGTRAP 退出）。缺任一条件时浏览器用例是 **error**，不是 skip，不得当通过。
本机封存数据根只读 ⇒ 默认根 pytest 的 46 项环境层失败维持不变，不修、不 skip。

## 2 owner 与写权（同一时刻一人）

| 切片 | 实现 owner | 写 scope | 规格条款 | 验收 |
|---|---|---|---|---|
| R1 原子发布 | `r1r5-host-memory` | `loop/host/agent_memory.py`（必要时只读 `agent_control.py`） | `AGENT_CONTEXT_SPEC` 封存与恢复「原子发布（R1）」 | R1-A/R1-B |
| R5 预算口径 | `r1r5-host-memory`（R1 后） | `loop/host/agent_memory.py`、`loop/services/api.py`、`loop/web/context-explain.js`、`agent-window.js` | `AGENT_CONTEXT_SPEC` C1「预算计量唯一 owner 是 Host」；`AGENT_WINDOW_SPEC` 可解释性 1 | R5-A |
| R2 路径边界 | `r2r3-baseline` | `loop/host/baseline.py` | `LOOP_ORCHESTRATION_SPEC` §3.1 条款 4「统一边界判据」 | R2-A |
| R3 坏编码 | `r2r3-baseline`（R2 后） | `loop/host/baseline.py` | `LOOP_ORCHESTRATION_SPEC` §3.1 条款 4「解码失败隔离」 | R3-A |
| R4 N8 真实成本 | `r4r6-n8-sandbox` | `loop/workflows/chunks/model_steps.py` | `AGENT_CONTEXT_SPEC` C1「按真实序列化成本选择表示」 | R4-A |
| R6 沙箱残留（候选） | `r4r6-n8-sandbox` | 先只确认；授权后 `host_steps.py`/`model_steps.py`/`main_flow.py` | 待 Lead 依红灯结论补条款 | 是否成立 + 修后回归 |
| F14 样式收敛 | 待派（B 稳定后） | `loop/web/tokens.css`、`app.css`、`legacy.css`、`tests/browser/**` | `WEB_UI_SPEC` + F14 前置清单 | 前后截图逐条解释、无 `!important` 掩盖 |
| F05 余下 | 待派（F14 后） | `loop/web/app.js` + 新渲染模块 | `WEB_UI_SPEC`、F05 首步计划 | GET/POST 次数、DOM id、草稿身份/焦点、409 保留不变 |

**唯一 git 写者纪律**：提交统一经 `flock .git/agent-commit.lock` 串行 + 显式路径 `git add`；
禁止 `git add -A`、`commit -a`、push、amend 他人提交。每切片固定两笔：红灯（只加测试）→ 实现。
Lead 负责全量门、STATUS、证据、最终整合。

## 3 每切片交接（SpecDD）

1. **规格**：已在 `8669cd7` 前置登记；R6 条款在红灯确认后补登，未经确认不改行为。
2. **红灯**：确定性失败用例，必须确认失败原因是目标缺陷（环境/测试笔误不算）；红灯先提交。
3. **实现**：先保持行为提取再改行为；历史记录与旧格式保持可读或被显式版本化。
4. **验证**：定向 → 受影响集合 → 软件层（Lead 串行）→ 适用四道门；通过/失败/跳过/排除/未运行分列。
5. **归档**：新增证据文件 + STATUS 条目 + MD5；证据只增不改。

## 4 阶段门与顺序

| 门 | 条件 |
|---|---|
| G-B1 | R1 定向绿 + 受影响集合绿；R5 才有资格启动（同文件） |
| G-B2 | R2、R3 各定向绿；R3 独立提交 |
| G-B3 | R4 定向绿；R6 结论成立才立项，不成立记录否决依据 |
| G-C1 | R5 已合入（`context-explain.js`/`agent-window.js` 不再被改）后才启动 F14/F05 |
| G-final | 软件层 0 failed；文档门 `missing=0`；R1–R5 各自证据与独立复核；未关闭项保持可见 |

**独立验证**：每切片完成后由只读子代理复核（只写自己报告、不改被测文件、不做 git 写命令）；
没有独立验证者时如实登记为「同一执行者复验」，不得声称复核通过。

## 5 退出门与回退

- 回退 R1/R5：`git revert` 对应实现提交（旧格式记录保持可读）；回退 R5 先回 UI 消费再回 API 字段。
- 回退 R2/R3：分别 revert 软件提交，基线原件零写入；回退后缺陷重新标未关闭。
- 回退 R4：仅回退算法提交；保留超预算显式失败，不增大默认预算。
- 回退 F14/F05：按组件提交 revert；截图基线不得在差异未解释时批量覆盖。

## 6 已知阻塞（不因本轮改进而消失）

F01-d 真实非默认基线整链、F04 S0-b、F09 持久暂停仍缺内网环境/授权/恢复契约评审；
kb 自测与端到端 `accept_v1_run.sh` 需可写 `ENV_ROOT` 与内网夹具 ⇒ 本轮记「未运行」，不以软件层替代。
