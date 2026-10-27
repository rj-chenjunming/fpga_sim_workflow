# E2 / E3 可行性体检：能力已就位，剩下的是**裁决**与**算力**（2026-10-27）

> **结论先行**
> - **E2（S0-b 接入）**：不再是"环境能力不够"——本轮实测 EDA 工具与许可可用、**派生副本上三库编译 rc=0（2.7 s）**、
>   原 `ENV_ROOT` 零写入。剩下的是 **3 个口径裁决**（ports 差异来源 Q1、hunk 谁填 Q2、smoke 判据/阈值 Q3）
>   + 一个**中小切片**（落点已列在 §3）。
> - **E3（`passed` 形态夹具）**：能力也够了（编译 2.7 s、许可可用），剩下的是一次**真实通过轮**
>   （N9 全跑 ≈**21.56 h**/5 例，`doc/STATUS.md` §54.2）+ **印记口径**必须先定。不是"做不了"，是"要算力 + 排队"。
> - **本轮没有改任何 S0 代码或规格**：`D4 = 等 E2`（STATUS §96），且 Q1–Q3 未定；按 `S0_ENVIRONMENT_SPEC §8.4`
>   红线 5「拿不到协议就保持阻断并登记，不得猜」，这里只登记 + 给可执行提案。

## 1 本轮实测（数字全部从命令输出复制）

做法：把 `<ENV_ROOT>` 整体复制成派生副本 `<repo>/.env-copy`（红线 11 允许在派生副本上验证），
在副本里跑环境侧自带的 `doc/tools/compile_only.sh -c tc_pcie_rw_02`（= 卡点 B「只编译」入口）。

| 事实 | 实得 |
|---|---|
| EDA 工具 | `/home/soft/UNIVISTA/20260917/UVS/bin/{uvlan,uvs}` 在 PATH；`UVS_HOME`、`UV_LICENSE=8273@s24:…` 已配置 |
| 副本 | `cp -a --reflink=auto` → `<repo>/.env-copy`，`chmod -R u+w` 后可用 |
| 编译结果 | `=========== [PASS] 卡点 B 通过：两段编译均成功 ===========`，`COMPILE_RC=0`，`real 0m2.737s` |
| 库与日志 | `SIMLIB_RUN/tc_pcie_rw_02_1/{rtl,tb}`；日志 `SIMLIB_RUN/log/tc_pcie_rw_02_1_c_{rtl,tb}.log` |
| rtl 段 | 日志 1295 行 / 86 124 B，工具自印 `Compilation: 0 error(s), 13 warning(s)` |
| tb 段 | 日志 795 行 / 28 421 B，工具自印 `Compilation: 0 error(s), 4 warning(s)` |
| 原 `ENV_ROOT` | `find <ENV_ROOT> -newer <marker> \| wc -l` = **0**（零写入） |

> 注：`compile_only.sh` 自带并发锁 `.compile_only.lock`（红线 7）、`uvs.setup` 备份/还原**带 md5 断言**、
> 选项字符串与 `doc/tools/run_local.sh` 做机器自检 —— 也就是说"冒烟"要用的**驱动协议在环境侧已有现成实现**。

## 2 Q3（smoke 判据）这次钉清了——附一个必须写下来的陷阱

**三库是什么**（据 `<ENV_ROOT>/doc/_notes/05_env_layer.md` §库 表与 `compile_only.sh`）：
> **更正（同日，定稿前发现）**：产品侧**不**用环境那个 `compile_only.sh`——本仓已有
> `kb/tools/run_guarded.sh --mode compile-only`（N7 在用：串行锁、沙箱工作树、`uvs.setup` 自愈、
> 编译选项逐字自检、逐用例 rc + 日志），S0 的 `smoke` 应当**复用它**（红线 8：一套实现）。
> 下面用环境 `compile_only.sh` 只是为了**独立证明 EDA/许可可用**（它自带 `.compile_only.lock` 与 md5 断言），
> 不改变"产品驱动 = `run_guarded.sh`"这一结论。


| 库 | 命令 | 产物 |
|---|---|---|
| `rtl` | `uvlan -work rtl -filelist ./RTL/rtl_dir_pango.txt <vlan_opt> <all_opt> -logfile LOG/…` | DUT/RTL 编译库 |
| `tb` | `uvlan -work tb ./TB/tbtop.sv ./TESTLIB/<tc>.sv <vlan_opt> <all_opt> -logfile LOG/…` | TB 编译库 |
| `xli_lib` | 仅当 `VENDOR_XILINX` 宏打开时额外一段（本工程默认 Pango ⇒ 不出现） | Xilinx 库 |

**判据（本轮实测校准）**：

1. **权威读数是工具自印的汇总行** `Compilation: <N> error(s), <M> warning(s)`；
2. 明细看 `Error-<code>` / `Warning-<code>` 行（实测样例：`Warning-120002: Command option warning`、
   `Warning-121147: Redefinition`）；
3. `rc` 只反映"能否产出库"，**不等于 0 error**（本轮 rc=0 且 0 error；但两者要分别记录）；
4. ⚠️ **陷阱**：用 `grep -c -iE '\berror\b' <log>` 数"错误行"会**把汇总行自己算进去**
   —— 实测命中 1 行，那行正是 `Compilation: 0 error(s), 13 warning(s)`。所以判据必须是"解析汇总行 + `Error-`
   前缀行"，**不是裸 grep**（这条要写进 D3 的实现与用例，否则冒烟会把 0 error 判成有错）。

**还缺环境侧一句话**：`<M> warning(s)` 的**可接受阈值**（哪些 warning 属已知可接受、哪些必须为 0）。
不许猜（`S0_ENVIRONMENT_SPEC §8.4` 红线 5）。

## 3 E2 的剩余阻塞：3 个裁决 + 1 个切片（落点已定）

| # | 待定 | 需要谁 | 若给定，我改哪里 |
|---|---|---|---|
| **Q1** | `ports` 的**接口差异来源**：消费外部接口报告，还是 Host 从"基线 RTL 快照 vs 新 RTL"确定性派生端口差异 | 人（要先改 `S0_ENVIRONMENT_SPEC §8.3` D1 行的契约） | `loop/host/s0.py`（派生/登记）、报告模板 |
| **Q2** | `TB/top.sv` 的逐 hunk **由人填写还是模型提议+人确认**（两者都禁止"先改后申请"） | 人 | `loop/host/s0.py`、`loop/services/api.py`、环境准备视图 |
| **Q3** | 三库冒烟的**warning 阈值**（§2） | 环境侧 | `loop/host/s0.py`（smoke 段）+ 新增用例 |
| **D4** | 准出判据接进执行入口 | 已有基础（C12「传了才校验」） | 只改一处：`loop/host/s0.py:334` 的 `ready_for_execution = False` 归一逻辑（放开到真实核验结果） |
| **D5** | 视图状态从"未接入"改为真实流转 | 依赖 D1–D3 | `loop/web/index.html`、`loop/web/s0.js` |

规模判断：Q1/Q2/Q3 一旦定了，这是**一个中小切片**（`s0.py` + `api.py` + 报告模板 + 4–8 条用例），
不是大重构；卡点从来不是"能不能编译"（今天证明 2.7 s 就行）。

## 4 E3 的剩余阻塞：一次真实通过轮 + 印记口径

`I3`（"跑通"）的判据（`CHANGE_IMPACT_LOOP_SPEC` §I3 行原文）：

> 编译卡点 B rc=0 ∧ 静态卡点 C 通过 ∧ 全跑卡点 D 产完整 UVM 汇总 ∧ **两套口径均为 0** ∧
> **预期观测点留下通过印记且计数三向一致**

| 需要 | 现状 |
|---|---|
| 卡点 B（编译） | ✅ 本轮实测可跑（2.7 s/例，rc=0） |
| 卡点 C（静态复核） | 有实现（N8）；需要一次真实轮去跑 |
| 卡点 D（全跑） | ⏳ 需 ≈**21.56 h**/5 例（§54.2 实测吞吐 ≈3.8 µs/s）；本机 `/home` ro ⇒ **必须先有可写 ENV_ROOT** |
| 两套口径 = 0 | 依赖卡点 D 的完整日志 |
| 观测量印记三向一致 | 需用例侧能打印 `N6_` 前缀的预期观测点（`model_steps.py:52`、`host/evidence.py`）；2026-10-24 那次真实轮 `rc=0` 但**印记不足** ⇒ 仍是 `not_passed`（§91） |

⇒ E3 要的是：**可写环境 + 21.56 h 排期 + 印记口径确认**。前两项是环境侧/算力，第三项是口径。

## 5 建议的推进顺序（按代价从低到高）

1. **你给 Q1/Q2 各一句话**（ports 来源、hunk 谁填）→ 我出 `S0_ENVIRONMENT_SPEC §8.3` 的规格 diff 给你评审
   （不改代码）；评审过 → 实现 D1/D2 + 用例，D4 的"一处判据"同时打开。
2. **环境侧给 Q3 阈值**（warning 哪些可接受）→ 我把 D3（三库冒烟）接上：编译 2.7 s/例，
   接完就能在 S0 派生副本里跑出"每库命令 + rc + error/warning 计数 + 原始日志"。
3. **E3**：等可写环境 + 排期。我可以先把 runbook 脚本化（一条命令：起 real 轮 → 落日志 → 按 I3 五项自检
   → 通过则冻结夹具 + md5 + README），到时有写权就能直接跑。

## 6 本轮没做的事（照实登记）

- 没改 `loop/host/s0.py`、`loop/services/api.py`、`loop/web/**` 任何代码（Q1–Q3 未定，猜=违反 S0 §8.4 红线 5）。
- 没改 `S0_ENVIRONMENT_SPEC`（契约变更要显式评审）。
- 没跑真实通过轮（需 21.56 h + 可写 ENV_ROOT）。
- 派生副本 `<repo>/.env-copy` 用完已删（`du -sh` 2.6 G；重建约 10 s）。
