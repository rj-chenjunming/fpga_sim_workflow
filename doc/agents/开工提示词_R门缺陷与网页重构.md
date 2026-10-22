# 开工提示词：R 门缺陷收口与网页重构（2026-10-22）

> **用法**：新窗口把本文件**全文**作为第一条消息粘贴。
> 目标：按 [下一轮 SpecDD 计划](../plans/2026-10-22-next-iteration-specdd.md) 的 A→B→C 顺序，**连续执行完软件可验证的待办**；不要每个切片停下来请示，遇到硬阻塞先登记再继续下一项。
> 本文件自包含：仓库状态、已完成、待办、强制流程、验证命令、环境坑、红线。

---

## 0 你的角色

你是本仓 **Lead**：负责规格、计划、实现、验证与归档，遵守 [`AGENTS.md`](../../AGENTS.md)。
按 §3 写权分配实现 owner；可以自己实现，但**每个切片必须有独立验证者**（见 §5）。
「发现缺陷只报告不改」只约束验证者，不约束你。

## 1 开工前必读（只读，按顺序）

1. [`AGENTS.md`](../../AGENTS.md)：流程权威（§2 SpecDD、§3 写权、§4 四道门、§5 红线）。
2. [`doc/STATUS.md`](../STATUS.md) **§33–§38**：§33 阻塞清单、§34 上批复核汇总、§35 内网复核 R1–R5、§36 离线浏览器交付、§37 下一轮规划、§38 本次 bundle 合入与实测。
3. [`doc/audit/AUDIT-20261022-intranet-batch-review.md`](../audit/AUDIT-20261022-intranet-batch-review.md)：**R1–R5 缺陷原始描述与修法建议**（本轮主要输入）。
4. [`doc/plans/2026-10-22-next-iteration-specdd.md`](../plans/2026-10-22-next-iteration-specdd.md)：阶段、切片、owner、验收 ID、退出门。
5. [`doc/plans/2026-10-22-intranet-validation.md`](../plans/2026-10-22-intranet-validation.md)：V0–V9 验证步骤。
6. [`loop/offline/README.md`](../../loop/offline/README.md)：离线浏览器安装/启动。
7. 相关 `doc/spec/*.md`（先规格后实现，不许凭记忆写契约）。

## 2 仓库与环境事实（已核实，不要重复踩坑）

| 事实 | 值 / 做法 |
|---|---|
| 仓库 | `/home/work/chenjunming/change-impact-loop`，分支 `main` |
| 起始状态 | HEAD **`f2946ec`**（§38 文档）；`8816dbc` 是最后同步的内容基线；本地比 `origin/main` **领先 1 个文档提交** |
| 远端 | **不可达**：代理 `192.168.1.27:3128` 对 `github.com:443` CONNECT 返回 503；本机无 nameserver、无 VPN 路由。**不要 push，也不要指望 `git fetch`**；需要新内容时走 bundle 交付（流程见 §38） |
| 解释器 | `loop/.venv/bin/python`（3.11.7）；模型节点默认 `LOOP_LLM_MODE=standin` |
| 软件层门禁 | `cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh --tb=no` ⇒ 合入后实测 **`464 passed, 3 skipped, 3 deselected, 0 failed`**（约 86s）。这是本轮起步基线 |
| 默认根 pytest | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q --tb=no` ⇒ **`46 failed, 414 passed, 3 skipped`**：44 项 `Errno 30`（`ENV_ROOT` 只读）+ 2 项 `test_archive_e2`。**是同集环境失败，不是代码回归**；不许 skip 换绿 |
| `ENV_ROOT` | 内网环境仓，本机**只读**；`kb/tools/**`、`kb/schema/**`、`doc/evidence/**`、`doc/history/**` 冻结，kb 子进程必须带 `-B` |
| 浏览器 | 系统有 `/usr/bin/google-chrome`；**`playwright` Python 包当前未安装** ⇒ `tests/browser` 目前**无法收集/整组 skip**。本轮已交付离线包，按 §3 Stage A 安装后应能真实运行 |
| 离线包 | `loop/offline/browser-linux-x86_64/`（约 186 MiB，普通 Git 交付，非 LFS、非子模块） |
| 文档门 | `python3 doc/audit/check_doc_links.py`：**只看退出码与 `missing`**（当前 rc=0 / missing=0）；`known_missing=10`、`env_missing=12` 是已知环境缺件诊断值，**不是失败，也不许回填** |
| 软件 state | conftest 注入一次性 `$LOOP_STATE_ROOT`；沙箱外可能有常驻服务改写 `loop/state`，不要用 mtime/md5 反证 |
| `/tmp` | 每次 bash 调用是**独立 tmpfs**，不要指望跨调用保留文件；跨调用产物放工作区临时目录并清理 |

## 3 已完成（不要重做；发现缺陷按新切片修）

- **F01/F02/F03-a/F03-b/F03-c**：基线准入唯一判据、能力事实四维、`$LOOP_STATE_ROOT`、测试分层 `env_layer` + 入口脚本、文档根路由。
- **F05 第一步**：闸门会话判定提取为纯函数（`loop/web/gate-session.js`）。**余下步骤未做**。
- **F06**：模型请求机制与节点语义分离（`model_request.py` / `n6_facts.py` / `n10_semantics.py` / `n11_guard.py`，纯重构保持行为）。
- **F07**：Agent 历史读取先测量后决策（未达阈值 ⇒ 不引入缓存/分页）。
- **F08**：封存四态 + 符号链接显式失败（**但 R1 暴露发布空窗未关**）。
- **F10/F11 前半**：只读可解释性、token 恒 unknown（**但 R5 暴露预算口径不一致**）。
- **F13**：首次失败/刷新失败五态判据。
- **F15-a / F16 / F16-b / F16-c / F02-b / F02-c**：文档对齐、N8 预算分片与闭锁、基线结构化错误、窗口能力消费。
- **§36 离线浏览器交付**：包 + 校验/安装/运行 CLI。

## 4 待办（按顺序执行；细则以计划 §3–§5 为准）

### Stage A · 验证基线（先做，否则后面全是盲修）

1. 跑 V0：确认三根、版本、`git rev-parse HEAD`，把起始 HEAD 写进 STATUS 的采样行。
2. 跑 V1：离线浏览器
   ```bash
   cd loop
   .venv/bin/python spikes/browser_offline.py verify     # 只校验，不改环境
   .venv/bin/python spikes/browser_offline.py install    # 装 wheel（--no-index --require-hashes）
   .venv/bin/python spikes/browser_offline.py check      # 真实启动冒烟
   ```
   若缺系统库（`libnspr4.so`/`libnss3.so` 等），**登记为环境缺件，不得写成浏览器验收通过**。
3. 跑 V2：软件层特征基线，记录通过/跳过/排除/未运行四类数字。
4. 跑 V3：浏览器回归 + 改动前截图（F14/F05 要用）。

**退出门**：根与版本可追踪；浏览器真实启动；基线失败逐项登记并归因（环境层 vs 代码）。

### Stage B · 关闭可复现缺陷（本轮核心，严格按序）

每个缺陷都必须：**先补确定性红灯 → 确认红灯因目标缺陷失败 → 修复 → 定向绿 → 软件层绿 → 归档**。
现成复现入口（只观察，不是修好）：
```bash
loop/.venv/bin/python doc/audit/parts/intranet-batch-probe.py
```

| 序 | 缺陷 | 级别 | 落点 | 期望证据 |
|---|---|---|---|---|
| 1 | **R1 发布空窗**：校验文件创建后进程被杀 → 整个节点历史不可读（旧 committed 尝试也读不到） | P1 | `loop/host/agent_memory.py`（seal/record_state/read_view） | 固定故障点终止子进程后：旧 committed 仍可读、半件不可消费、完成件可核验；竞争写同编号只有一个成功 |
| 2 | **R2 相对路径绕过允许根**：绝对路径被拒但相对 `../` 放行 | P2 | `loop/host/baseline.py` `_artifact_path` | 绝对/`..`/相对符号链接全部拒绝且零副作用；合法根内成对通过 |
| 3 | **R3 manifest 坏编码**：非 UTF-8 使 `/api/baselines` 整体 500 | P2 | `loop/host/baseline.py` | 坏项 `valid=false + errors`，其它基线仍可列；real 选择坏项按协议拒绝 |
| 4 | **R4 N8 预算误拒**：全文可行（59341<60000）却报碎片更大（61835） | P2 | `loop/workflows/chunks/model_steps.py` | 按真实编码成本选择表示；全文可容时可选全文；并列成本稳定；全超限才拒绝（不丢文件、不虚报 complete） |
| 5 | **R5 预算口径不一**：界面 1055B vs Host 72B | P2 | Host 出计量、`loop/web/context-explain.js` 只消费 | Host 准入字节 == API == UI 总量；分项+显式开销==总量；上限未知不显示假比例；token 仍 unknown |
| 6 | **R6 候选（§38.4，需先确认再立项）**：N6 沙箱残留件被当本轮复核对象 | 待定 | `loop/workflows/chunks/host_steps.py:597`、`model_steps.py:660/673`、`main_flow.py:90` | 先写红灯证明"返工轮 target 缩水时残留 `.sv` 被计入且可标 `coverage.complete=true`"，再决定修法（清理沙箱 / 白名单 + 多余件显式失败） |

**R1 未关之前不要启动 F09**（持久暂停依赖封存语义）。

### Stage C · 网页重构（B 稳定后）

1. **F14** 样式收敛：`loop/web/tokens.css` / `app.css` / `legacy.css`；先存改前截图与计算样式，再按布局→通用控件→S0→运行/闸门→Agent 逐组件收敛；**不新增 `!important` 掩盖层叠冲突**。
2. **F05 余下**：运行/Agent/计数渲染、配置/目录浏览提取；纯渲染以参数接收事实，状态与订阅仍由唯一装配方持有；DOM id、草稿身份/焦点、重复提交互斥、409 后输入保留不得变。

**退出门**：前后行为等价、视觉差异逐条解释、浏览器测试**无 skip**。

### Stage D/E/F · 有前置才启动（否则登记阻塞，不做空实现）

- **F01-d**（真实非默认基线整链）、**F04 S0-b**（驱动/三库/准出，`ready_for_execution` 恒 false）：缺内网环境与授权 ⇒ **阻塞**。
- **F09**：依赖 R1 关闭 + TriggerFlow 恢复契约评审。
- **F07/F11/F10 token/F15-b/F12**：按测量或真实用例触发，未达条件不立项。

## 5 强制流程（每切片照抄）

1. **规格/计划**：写可观察行为、不变量、唯一 owner、允许改的文件、验收 ID、未决决策。契约先改 `doc/spec/*` 再改实现；计划的建议**不自动成为契约**。
2. **红灯/特征**：纯重构先固定旧行为并跑绿；缺陷先写确定性失败用例，并**确认它因目标缺陷失败**（测试写错/缺环境不算红灯）。
3. **实现**：先保持行为的局部提取，再单独改行为；保护历史数据与兼容读取。**改测试期望必须退回规格评审并单独记录**。
4. **验证**：受影响集合 → 软件层/浏览器 → 适用四道门；通过/失败/跳过/排除/未运行分列记录。环境阻塞可交付软件切片，**不能标完整完成**。
5. **归档**：原始命令、提交、环境、退出码、日志、来源指纹写入**新增**证据，记 MD5 到 `doc/STATUS.md`（你的唯一数字源）；证据只增不改。

**独立验证者**：每个切片派只读子代理复核，**只写自己报告、不改被测文件、不做 git 写命令**；没有独立验证者时，如实登记为同一执行者复验，不得声称"复核通过"。

## 6 命令清单（可直接复制）

```bash
# 定位
cd /home/work/chenjunming/change-impact-loop && git log --oneline -5 && git status -sb

# 软件层门禁（起步基线 464 passed / 0 failed）
cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh --tb=no

# 默认根（46 failed 为环境层，如实记录）
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q --tb=no

# 定向
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_f08_sealed.py tests/test_baseline_admission.py --tb=short

# 缺陷复现（R1–R5 现状观察）
loop/.venv/bin/python doc/audit/parts/intranet-batch-probe.py

# 离线浏览器
cd loop && .venv/bin/python spikes/browser_offline.py verify && .venv/bin/python spikes/browser_offline.py install
cd loop && .venv/bin/python -m pytest tests/browser -q

# 文档门（只看退出码与 missing）
python3 doc/audit/check_doc_links.py; echo "rc=$?"

# 提交前自检
git diff --check && git status --short
```

## 7 红线（违反即回退重做）

1. 不改 `RTL/ TB/ PKG/ TESTLIB/` 原件与任何冻结基线资产；软件对环境的写入只有 `SIMLIB_RUN/` 与 `uvs.setup` 自愈还原（S0 派生副本另按 S0 规格）。
2. 数字一律从命令输出复制，禁止手算；只写进 `doc/STATUS.md`。
3. 归档只增不改；不回填已冻结运行目录、不改写旧审计/证据。
4. 闸门枚举权威是 `kb_lib.GATE_DECISIONS`，前端/脚本不许手抄；`pending` 是状态不是动作。
5. 失败必须显式：`failed` + `error` + 关闭执行；**不许把崩溃/恢复失败伪装成"在等人工"**。
6. 同一判据只能有一个实现（发现第二套就登记并消除，例如预算、状态机、路径校验）。
7. 不静默截断、不用默认值兜底掩盖缺失、不吞异常换绿灯。
8. 时间字段是唯一允许的非确定性，只能经 `--now`/`KB_NOW` 注入。
9. **不声称四道门全绿、不声称合规**：端到端、kb 自测、真实 provider 在内网具备前一律记"未运行"。

## 8 交付标准（本窗口完成时应有）

- Stage A 的 V0–V3 结果已记入 `doc/STATUS.md`（含浏览器真实启动证据或明确缺件）。
- R1–R5 各自：红灯提交 → 修复提交 → 定向绿 → 软件层绿 → 独立复核报告 → STATUS 条目（含 MD5）；**未关闭项保持可见**。
- R6 候选至少给出"是否成立"的确定性结论（成立则立项，不成立则记录否决依据）。
- 文档门 `missing=0`；软件层 0 failed；默认根失败集与 §34.1 同集（否则说明原因）。
- 每个切片有一行"回退方式"；旧格式/旧记录保持可读或被显式版本化。
- 最终答复里写清：跑了什么、没跑什么、哪些是环境缺件、哪些仍是阻塞。
