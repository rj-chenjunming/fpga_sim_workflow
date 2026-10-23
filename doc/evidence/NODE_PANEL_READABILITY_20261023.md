# 节点详情面板"人话优先"实测（SPEC-REV-02 R1，2026-10-23）

> **这是什么**：把节点执行详情从"技术键值 + 事件流水 + 原始 detail"改成"一句话用途 → 一句话结果 →
> 关键数字 → 过程步骤 → 证据 → 原始记录（默认收起）"的过程与证据。
> **触发（用户原话）**：「每个环节的可读性太差 其实只要简单描述一下做了那几步 每一步做什么 结果怎么样
> 用大白话说明就行 具体那个 seq 我不知道干啥的 如果是类似的 log 可以缩起来 需要再展开即可
> 我们一个节点一个节点的过一遍吧」
> **不是什么**：不是"节点文案已定稿"——逐节点措辞仍待用户走查确认（见 §5）。

---

## 1 改了什么（契约 → 实现）

| 层 | 落点 | 内容 |
|---|---|---|
| 规格 | [`SPEC-REV-02`](../spec/SPEC-REV-02-20261023.md)、[SPEC-04](../spec/WEB_UI_SPEC.md) §4.2.1/§6.7、[SPEC-02](../spec/LOOP_ORCHESTRATION_SPEC.md) §10.4 | 面板七块结构；`story`（`purpose`/`steps`/`key_results`）由服务端确定性生成；`seq` 只留在收起的「原始记录」并注明"事件流水号，不是业务状态" |
| 投影 | `loop/services/node_story.py`（新增）、`loop/services/node_view.py` | 逐节点一句话用途（`NODE_CATALOG.purpose`）+ 步骤人话（按事件 `kind` 白名单）+ 关键数字（逐节点字段表）；缺失逐项"未下发"，不猜、不换算 |
| 前端 | `loop/web/node-detail.js`、`loop/web/index.html`、`loop/web/app.css` | 首屏：这一步做什么 / 结果 / 关键数字 / 过程；证据单独一段；失败时显示 error 原文；「原始记录（排查用）」`<details>` 默认收起，含 `seq`、完整 detail、`missing_fields`、身份技术字段 |
| 测试 | `loop/tests/test_node_story.py`（新增）、`test_node_detail_projection.py`、`tests/browser/test_node_detail.py` | 单元：purpose/steps/key_results/缺失/确定性；浏览器：首屏可读、seq 默认收起、失败不声称完成 |

**文案澄清（用户反馈"夹具好抽象"）**：`drill_fixture` 在面板显示为「drill 演示数据（不碰真实环境）」，
首屏加一行「节点结果来自预置数据（夹具），不碰真实环境，也不验证环境搭建（S0）」；N0 的
`fixture_files` 改标签「拷入预置文件」，real 模式显示「0（真实运行不复制预置文件）」，drill 显示实际份数。

**不变**：面板只读、不新增写动作；status 仍显示服务端原值；缺失仍显式"未下发"；
`refs` 仍只做存在性探测；判据仍只在 `blockers/can` 与 `gates.json`。

---

## 2 逐节点效果（真实 run `RUN-20261022-181700` 的投影输出，节选）

| 节点 | 一句话用途 | 首屏可读到的结果（summary / 关键数字） | 过程步骤 |
|---|---|---|---|
| N0 | 把这次运行要用的工作目录准备好，并把闸门/基线状态初始化。 | 真实运行目录初始化；baseline=v0、mode=real、夹具 0 | 开始 → 结束 |
| N1 | 给当前代码和文档拍一张快照：多少文件、什么指纹、哪些用例。 | allfiles 4491、cases 162、commit 可解析 | 开始 → 结束 |
| N2 | 把快照跟基线逐项比对：哪些文件改了、哪些还没对上。 | 差异 2 条、未决 1 条、offset 1 条 | 开始 → 结束 |
| N3 | 让分析模型把原始差异翻成一句人话。 | provider=origin-deepseek-v4-1-flash、校验问题 0 | 开始 → 结束 |
| N4 | 由人确认差异清单没问题。 | 闸门 G1、决策 confirmed、签署人 human:chenjunming | 开始 → 等待人工决策 → 人工已决策 → 闸门结论 |
| N5 | 根据改动算出哪些用例必须改。 | 必改 3 例（tc_pcie_rw_02 / tc_pcie_rw_smoke / tc_rtc_05）、索引缺口 5 | 开始 → 结束 |
| N6 | 让作者模型按影响清单改/补用例。 | 第 1 轮、目标 3 例、输出校验通过 | 开始 → 结束 |
| N6_apply | 把模型给的修改真正写进沙箱用例。 | 写入 3 例、施加 3 条 edits、applied | 开始 → 结束 |
| N7 | 先把改过的用例编译一遍。 | 编译 3 例、全部通过、失败 0 | 开始 → 拿到执行槽位 → 结束 |
| N8 | 让检查模型静态复核修订后的用例。 | 复核结论 pass、第 0 轮 | 开始 → 复核结论 |
| N9 | 把选中的用例全部跑一遍（长作业）。 | 作业号、3 例、口径一 1687、UVM_ERROR=0/UVM_FATAL=0 | 开始 → 拿到执行槽位 → 提交作业 → 作业结束 → 结束 |
| N9_submit | 把全跑作业交出去后先返回。 | 作业号、覆盖 3 例 | 结束（只有收尾事件） |
| N10 | 把全跑结果跟预期对账。 | 3 例、判定通过=否、待裁决 0 | 开始 → 结束 |
| N11 | 检查证据链完整、身份一致。 | 证据链 intact、身份一致=是 | 开始 → 证据链 |
| N12 | 让报告模型写本轮评估报告。 | 报告结论 not_passed、引用 18 条 | 开始 → 结束 |
| N4/N13/N14 | 闸门：人做决定。 | 未收尾时显示"该节点还没有收尾记录"，收尾后给出决策/签署人 | — |

完整清单与措辞见 [`SPEC-REV-02`](../spec/SPEC-REV-02-20261023.md) §R1；N15/N15_select/N15_submit/N16/HALT
在 drill 全链中同形（N16 实测：`dry-run`、退出码、操作者类型在一屏内可见）。

**`seq` 的处理**：正文不再出现；只在「原始记录（排查用）」顶部写
"seq 是同一 run 内的事件流水号，只用于排序和定位（第几条事件），不是业务状态"，
展开后仍是逐条原始事件（`#31 node_started …`）。

---

## 3 门禁实测（本轮工作树，2026-10-23）

| 门 | 命令 | 结果 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser --junitxml=…` | **546 tests, 0 failures, 0 errors, 0 skipped**（108.16s；3 项 `env_layer` 按脚本默认排除并在输出列出） |
| 浏览器 | `LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome pytest -q tests/browser`（可写 `HOME`） | **56 passed**（75.22s） |
| 端到端 | 隔离工具副本 + 副本环境：`LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS，117/117**（phase 1/2/3/4/4b/5 = 50/27/18/8/8/6，全部 rc=0） |
| 文档 | `python3 doc/audit/check_doc_links.py` | 见 `doc/STATUS.md` §44（`missing=0`） |

**端到端隔离方法的坑（实测记录）**：直接从仓库 `cp` 出工具副本会带上 `loop/.agently/records/identity/state.json`，
其中 `record_store_id` 绑定原工具根；新进程建 RecordStore 时报
`RecordStore identity state belongs to a different RecordStore.`，N0–N4 全部 fail（第一次跑 36/50）。
**处置**：副本里删掉 `loop/.agently` 与 `loop/state` 再跑，117/117 全过——这是复制陷阱，不是流程缺陷。

---

## 4 怎么手工验一遍

1. 重启服务（Python 投影在进程内，旧进程不会自己长出 `story`）：`cd loop && LOOP_ENV_ROOT=… ./run.sh`；
2. 浏览器打开工作台 → 选一个 run → 运行监控 → 点任意节点 chip；
3. 首屏应看到：一句话用途、summary、关键数字卡片、过程步骤编号列表；
4. 点开底部「原始记录（排查用）」才看到 `seq`、逐条事件、完整 detail、未下发字段；
5. 失败节点（例如 drill 的 dead_job）首屏过程里应出现红色"失败：…"，且全文不出现"完成"。

---

## 5 边界与未决（不声称已定稿）

- **文案待走查**：§R1 的逐节点措辞是首版；用户按节点逐个确认后可能改动（改动只动
  `node_story.py`/`NODE_CATALOG`，不改事件与 detail）。
- **模型子事件不并入父节点**：`N3_model` / `N3_request` 等事件仍属各自 `node`，父节点过程只按自身事件生成；
  是否合并另起修订。
- **历史 run**：`story` 在请求时生成，所以旧 run 也有；旧 detail 缺新字段时关键数字会显示"未下发"（不回填）。
- **服务重启**：已在跑的服务需重启才返回 `story`；不复用旧响应。浏览器测试与门禁数字均来自本工作树。
