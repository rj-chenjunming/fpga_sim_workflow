# S0-b 规格变更提案（Q1 = Host 派生 / Q2 = 模型提议 + 人确认）——待评审，未实施

> **状态**：**提案**（2026-10-27）。**本文件不改 `doc/spec/**`，也不改任何代码**；请先评这份 diff。
> 评审通过后我按 §5 的顺序落地：先改 `S0_ENVIRONMENT_SPEC`，再实现 D1/D2/D3，最后按 §8.5 验收。
> **裁决依据**：`doc/plans/2026-10-27-e2-e3-feasibility.md` §3 的 Q1/Q2，人已选 **Q1=A（Host 确定性派生）**、
> **Q2=A（模型提议 + 人确认）**；Q3（warning 阈值）**仍缺环境侧一句话**，因此 D3 只做到"能跑并记录"，不给"可准出"。
> 流程：AGENTS §2.1（改契约先于改代码）、§3（`doc/spec/**` 唯一写者 = Lead，契约变更需显式评审）。

## 0 变更摘要

| 条目 | 现在 | 提案 |
|---|---|---|
| `ports` 的接口差异来源 | `S0_ENVIRONMENT_SPEC §8.2-1`「消费**可校验的接口差异来源**」；§8.3 D1 待定（外部报告 vs Host 派生） | **Host 从 `baseline/RTL` 与 `rtl_source` 确定性派生**，不消费外部人工报告；派生结果只是**候选表** |
| `TB/top.sv` 谁改 | §8.3 D2 待定（人填 vs 模型提议+人确认） | **模型逐 hunk 提议 → 人逐条确认 → Host 才落盘**；未确认的 hunk 一个字都不写 |
| 三库冒烟驱动 | §8.3 D3「复用 `kb/tools/run_guarded.sh` 的真实执行路径」，Q3 需协议、不得猜 | **驱动仍是 `kb/tools/run_guarded.sh --mode compile-only`**（Q3 的"哪三条命令"已就位，N7 在用）；本仓只新增"汇总行解析 + 计数 + 明细"（拟名 `uvs_logs.py`，放在 `loop/host/` 下）；判据 = 工具自印汇总行，**禁止裸 grep** |
| S0-b 阻断状态 | §3「S0-b 保持显式阻断」 | **仍然阻断**，直到 D1–D4 落地并过 §8.5；只是把"为什么阻断/接什么"写具体 |

## 1 diff：§8.2 第 1 条（ports）

**原文**：

> 1. `ports`：消费**可校验的接口差异来源**，产出副本 `TB/top.sv` 的逐 hunk 登记表（TB 编号、差异来源、位置/原片段、真实 unified diff、范围判定、影响用例、复核状态）；空表不得准出。

**建议改为**：

> 1. `ports`：**Host 从基线 RTL 快照与新 RTL 确定性派生**端口差异，再由**模型逐 hunk 提议**适配、**人逐条确认**后
>    才允许写副本 `TB/top.sv`。分三段，每段判据独立：
>    - **派生（Host，无模型）**：输入 = `record.baseline/RTL/**`（基线）与 `record.rtl_source/**`（新 RTL），
>      只读、只解析模块端口声明；**同一输入必须得同一输出**（输出可复算 md5）。派生失败（输入缺文件/解析不了）
>      ⇒ `ports` 直接 `failed`，**不得降级为"无差异"**。
>    - **提议（模型）**：对每条候选差异给出适配方案（改哪一行、改成什么、影响哪些用例），写入
>      `proposals/`，**不写副本**。
>    - **确认（人）**：逐条 `confirmed` / `rejected`；**只有 `confirmed` 的 hunk 允许落盘**。确认记录只增不改。
>    登记表每项含：TB 编号、接口差异来源（基线/新 RTL 的 md5）、位置/原片段、真实 unified diff、范围判定、
>    影响用例、复核状态（`proposed` / `confirmed` / `rejected`）。**空表不得准出；未确认的 hunk 不得写入。**

## 2 diff：§8.2 第 2 条（smoke）

**原文**：

> 2. `smoke`：在副本内真实执行三库编译，落每库命令、退出码、error/warning 计数、原始日志与 warning 评估。

**建议改为**：

> 2. `smoke`：在**副本内**真实执行三库编译，落每库的命令、退出码、**工具自印**
>    `Compilation: N error(s), M warning(s)`、`Error-<code>`/`Warning-<code>` 明细、原始日志路径。
>    **驱动复用既有实现** `kb/tools/run_guarded.sh --mode compile-only`（N7 已在用：串行锁、沙箱工作树、
>    `uvs.setup` 自愈、编译选项逐字自检、逐用例 rc + 日志），**本仓只新增"汇总行解析 + 计数 + 明细"**，
>    不新增第二套编译驱动。判据：任意一段 `N > 0` ⇒ `smoke=failed`；`M` 的**阈值待环境侧给（Q3）**，
>    未给出前 `smoke` 最多到 `passed_with_warnings_unconfirmed`，**不得准出**。
>    **禁止**用 `grep 'error'` 数行代替（会把 `0 error(s)` 汇总行本身算成错误，见 STATUS §99.2 实测）。

## 3 diff：§8.3 D1 / D2 / D3 三行

**原文（D1/D2/D3）**：

> | **D1** | 接口差异来源 | 待定：外部接口报告文件，或 Host 从基线 RTL 快照 vs 新 RTL 确定性派生端口差异 | **Q1**：§3 原文为"消费外部接口差异"；若改为 Host 派生，须先修订本契约 |
> | **D2** | `TB/top.sv` 适配 + 逐 hunk 登记（含回滚） | `loop/host/s0.py`、`loop/services/api.py`、环境准备视图 | **Q2**：hunk 由人填写，还是模型提议 + 人确认；两者都禁止"先改后申请" |
> | **D3** | 三库真实冒烟 | 复用 `kb/tools/run_guarded.sh` 的真实执行路径；每库命令/日志/计数落报告 | **Q3**：需环境侧三库驱动协议（哪三条命令、如何判 error/warning）；**不得猜** |

**建议改为**：

> | **D1** | 接口差异来源（**已裁 2026-10-27：Host 确定性派生**） | `loop/host/s0.py`（新增纯读派生函数）；报告模板新增候选表 | **Q1 关闭**：契约见 §8.2-1；**不再消费外部接口报告**。派生输入在 `record.baseline/RTL` 与 `record.rtl_source`，两者都在 `prepare()` 落盘过、可复算 |
> | **D2** | 副本 `TB/top.sv` 适配 + 逐 hunk 登记（含回滚）（**已裁 2026-10-27：模型提议 + 人确认**） | `loop/host/s0.py`（确认门槛 + 落盘）、`loop/services/api.py`（提议/确认端点）、环境准备视图 | **Q2 关闭**：模型只写 `proposals/`；人确认后 Host 才写副本；确认记录只增不改；禁止"先改后申请" |
> | **D3** | 三库真实冒烟（**Q3 部分就位**） | `loop/host/s0.py`（smoke 段）+ `loop/host/` 下新增日志解析模块（拟名 `uvs_logs.py`，汇总行解析的唯一实现）+ 新增用例；**驱动复用 `kb/tools/run_guarded.sh --mode compile-only`** | **Q3 剩一半**：驱动已在仓库里且 N7 在用（`run_guarded.sh --mode compile-only`，≈2 s/例；`test_fix_real_chain.py` 覆盖）；判据已实测（`Compilation: N error(s), M warning(s)`；STATUS §99）；**仍需环境侧给 `M` 的可接受阈值**。**不引入**环境侧 `doc/tools/compile_only.sh` 作为产品驱动（避免第二套实现，红线 8）——它只在本轮体检里用来证明 EDA 可用 |

## 4 diff：§8.4 红线（新增第 6、7 条）

> 6. **派生不改写**：Host 派生只产出候选差异表，**不得直接改写** `TB/top.sv` 或任何 SV；写盘必须有人对
>    该 hunk 的 `confirmed` 记录（Q2=A）。
> 7. **冒烟不得裸 grep**：error/warning 一律取工具自印汇总行与 `<Error|Warning>-<code>` 明细行，并**分别**
>    记录 `rc`；`rc=0` 不等于 `0 error`（实测反例见 STATUS §99.2）。

## 5 diff：§8.5 验收（新增三条可判定断言）

> - **派生确定性**：同一 `baseline/RTL` + `rtl_source` 连续派生两次，输出表 md5 相同；若 `baseline/RTL`
>   或 `rtl_source` 缺文件，`ports=failed`（**不得**当作"无差异"通过）。
> - **确认门槛**：对未 `confirmed` 的 hunk，副本 `TB/top.sv` 必须**逐字节不变**（用 md5 断言）；
>   确认记录追加后再落盘，旧确认不得被覆盖（只增不改）。
> - **冒烟判据**：每段必须落 `命令 / rc / error(s) / warning(s) / Error-<code> 明细 / 日志路径`；
>   `error(s) > 0` ⇒ `smoke=failed`；`warning(s)` 在 Q3 阈值给前不得判 `passed`。

## 6 实现切片（评审通过后按此顺序，一片一提交）

| 切片 | 内容 | 落点 | 验收（先失败用例） |
|---|---|---|---|
| **S1** | 派生函数（纯读、确定性）：解析两棵树里模块端口，输出候选差异 + 输入 md5 | `loop/host/s0.py` | 两次派生 md5 相同；缺文件 ⇒ fail-closed；不改任何 SV |
| **S2** | 提议与确认门槛：`proposals/` + 确认记录（只增不改）+ 落盘前的 md5 断言 | `loop/host/s0.py`、`loop/services/api.py` | 未确认 ⇒ 副本 SV md5 不变；确认后落盘恰含该 hunk；重复确认追加不覆盖 |
| **S3** | `ports` check 接上 S1/S2 的通过条件（空表/未确认不得 passed） | `loop/host/s0.py` | 现有 `test_s0.py` 不改期望先跑通，再加失败用例 |
| **S4** | `smoke` 复用既有驱动：在 S0 副本里跑 `run_guarded.sh --mode compile-only`，落命令/rc/计数/明细/日志 | `loop/host/s0.py` + 日志解析模块（拟名 `uvs_logs.py`）+ 用例 | 汇总行解析用受控日志夹具测（含"`0 error(s)` 不得被当成 1 条错误"）；真实跑 1 例 ≈2 s |
| **S5** | `ready_for_execution` 放开**一处**（`loop/host/s0.py:334` 的归一逻辑）+ D4 的 `s0_record_id` 透传复核 | `loop/host/s0.py`、`loop/services/api.py` | `GET /api/s0/{id}` 在六项全 passed 时才 `true`；漂移即回 `false` |

**明确不做**：不改 `loop/web/**`（D5 另起，需界面门）；不实现 SV 自动改写；不在 Q3 阈值缺失时判 `smoke=passed`。

## 7 评审要点（请重点看这三处）

1. **D1 的派生输入**：我打算用 `record.baseline/RTL` + `record.rtl_source`（`prepare()` 已分别落盘 manifest，
   目录真实存在）。若你认为"基线 RTL 文本"另有权威来源，请指出，我改。
2. **"人确认"的载体**：我准备复用既有闸门/账本习惯（**只增不改**的确认记录），不新造一套枚举；
   如果你要有独立的确认界面，那 D5 会提前，界面门也要跑。
3. **Q3 的阈值**：这条不定，`smoke` 就永远只能到 `passed_with_warnings_unconfirmed` ⇒ `ready_for_execution` 仍 false。
   这是唯一还会挡 E2 的外部输入。
