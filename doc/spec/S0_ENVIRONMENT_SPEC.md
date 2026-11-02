# SPEC-05 · S0 环境准备契约

> 编号：**SPEC-05**（文件名不变；编号与修订记录见 [SPEC-REV-01](SPEC-REV-01-20261022.md)）。

来源：用户修订稿 `simulation_flow_v2.md`，SHA256 `cf0c0fb4a50225449c203577949af947566ddcf7f92ebc8072ad471dcb330f3f`。仅采纳 §3、S0 双段时序及 §0.3 的 S0 授权边界；其余步骤不在本轮范围。附件命令示例不作为服务端命令执行。

## 1 时序与 owner

S0-a：完整复制基线 → 整体替换副本 RTL → 核对非 RTL，可与分析并行。

S0-b：消费外部接口差异 → 核对/适配副本 `TB/top.sv` 并逐 hunk 登记 → 副本内三库编译冒烟 → 收尾基线指纹。S0 两段及 GATE-1 均满足后才可执行用例。S0 不新增闸门，也不改变既有 N0–N16 的三个闸门。

Host `loop/host/s0.py` 是派生及核验的唯一写者；API 传输、UI 投影。模型不能设置就绪状态。S0 准备记录独立于既有 run，不把 N0 重命名成 S0，不偷偷切换进程 ENV_ROOT。

## 2 派生不变量

- 输入：完整基线工程、版本标识、新 RTL、新且不存在的副本路径。版本是操作者声明，不伪装已验证 Git commit。
- 基线含 `RTL/ TB/ TESTLIB/ PKG/`、`docs/` 或兼容旧插件的 `doc/`、以及**运行入口**；保持原目录名，脚本只复制不执行。
  - **TB 顶层文件**由编译驱动解析（`tb_top`，实测 `TB/tbtop.sv`），兼容历史写法 `TB/top.sv`，两者都没有即失败；
  - **运行入口**由 `s0b.resolve_run_entry()` 按 `run` → `run_tc.py` → `run_uvs_new.sh` → `doc/tools/run_local.sh` 顺序解析（`run_entry`），都没有即失败；
  - 基线**不得含符号链接**：`manifest()` 拒软链（防指回基线）。实测真实 `ENV_ROOT` 里有 30 个历史运行沙箱软链
    （`doc/`5、`kb/`21、`loop/`4），都在资产目录（RTL/TB/PKG/TESTLIB）之外 ⇒ 真实轮的基线必须是无软链的资产快照
    （或环境侧清理后再派生）。
- 输入/输出在服务端允许根内。拒绝符号链接、特殊文件、空 RTL、已有目标、输入输出树交叠；源工程不得包含本次记录目录。
- 完整复制后删除**新副本** RTL 再复制新版，删除的旧 RTL 不残留。清单记录相对路径、逐文件 MD5 和空目录；MD5 为内容见证，不是认证机制。
- 基线目录可为只读权限。仅对本次新副本根和待删除旧 RTL 的目录补 owner 读写执行权限，以完成替换；基线权限不改，其他继承资产内容不改。指纹以内容为准，不将此副本权限调整误报为资产污染。
- 非 RTL 初检完全一致；收尾再次核对基线和新 RTL 源。变化即失败。失败保留本次部分副本与失败记录，不删除用户目录或隐式覆盖重试；重新派生必须用新路径，操作者重试最多三次。
- 每次独立记录目录含 `reports/s0-env/env-check-report.md`、JSON 清单、`design-context.yaml` 的 `sim_verification.work_env`；不覆盖用户已有 context。

## 3 S0-b 完整目标与本轮能力边界

只授权副本 `TB/top.sv` 端口改名、位宽对齐、方向修正；新增端口须同时声明、初始化和连接；删除端口断连并注释、保留激励。其他 TB 文件、断言、激励时序、TESTLIB、PKG、文档、run 不得改。越界先停手登记，不能先改后申请。

登记表每项含 TB 编号、接口差异来源、位置/原片段、真实 unified diff、范围判定、影响用例和复核状态。GATE-1 负责复核；否决后逐 hunk 回滚并重跑冒烟。无登记差异不得准出；空表不能代表已核对接口。

三库冒烟须在副本真实执行，记录每库命令、退出码、error/warning 数、原始日志和 warning 评估。不得以现有 N7 两段编译、用户勾选、替身或单独 rc=0 替代三库证据。

**2026-10-23 时状态（历史）**：本轮实现 S0-a 派生与持续只读核验，S0-b 保持显式阻断。
**2026-10-27 更新**：S0-b 的 `ports`/`smoke` 已按 §8.2 接入（派生 + 模型提议 + 人确认 + 精确落盘 + 三库冒烟 + 基线相对增量），
`ready_for_execution` 由**六项检查全 `passed` 且无漂移**决定（§8.2-3，实测 STATUS §102）；仍不做的是**界面真实流转（D5）**
与**内网真机验收**。不实现未经验证的 SV 自动改写这条不变。

后续接入须补可验证驱动，并在执行入口消费完整 S0 判据。当前运行入口维持旧契约，明确标为“现有闭环”，不得称为附件新版 S3。S0-a 完成不能解锁新版执行。

> 后续开发项（D1–D5）、开放问题（Q1–Q3）与接入轮验收见 [§8](#8-未决登记s0-b-接入与执行入口消费2026-10-23)。

> **2026-10-27 修订（Q1/Q2 已裁、Q3 关闭）**：① `ports` 改为 Host 确定性派生、模型提议 + 人确认后落盘（§8.2-1）；
> ② `smoke` 的驱动确认复用既有 `kb/tools/run_guarded.sh --mode compile-only`，warning 判据改为基线相对增量（§8.2-2）；
> ③ 本契约原写的 `TB/top.sv` 在真实环境**不存在**（基线清单 TB 下为 `tbtop.sv` 等），改为由编译驱动解析 `tb_top`；
> ④ **S0-b 仍保持阻断**，直到 D1–D4 落地并过 §8.5 验收。上文“不猜编译命令”的前提已变化：命令来自仓库内既有驱动，
> 且在派生副本上实测 `rc=0`（STATUS §99.1）。

## 4 API 与报告

- `GET /api/s0`：默认基线、允许根、记录索引和能力边界。`capabilities.rehearsal=true` 只表示"可以点一次本机演练"，不表示环境就绪。2026-10-27 起 `tb_adapt`/`smoke` 为 `true`——
两者只描述**后端能力**（接口已实现），**不等于**任何记录已准出；准出仍由 §8.2-3 的六项判据决定。
- `POST /api/s0`：`baseline, baseline_version, rtl_source, work_env, now?`，派生。重复目标 409、越界 403、非法输入 400；操作失败持久化 failed/error 并返回失败，不伪装成功。
- `POST /api/s0/rehearsal`：**S0-rehearsal 一键演练**（软件能力验收，见 §6.2）。body **只允许可选 `now`**（含时区 ISO；非法 400）。
  Host 在**软件 state 目录**下自造一次性小基线（`${STATE_DIR}/s0-rehearsal/<UTC 戳>/baseline/`，含
  `RTL/ TB/top.sv PKG/ TESTLIB/ doc/`（兼容 `docs/`）与 `run`）与新 RTL（同戳 `rtl/`，含被替换的旧文件与新文件），
  派生到同戳的 `work/`；记录仍写 `${STATE_DIR}/s0/`（与真实 S0 记录同源，记录带 `rehearsal.kind=S0-rehearsal` 标记）。
  约束：
  - **不接受任何客户端路径参数**：多给任何键（`baseline`/`rtl_source`/`work_env` 等）⇒ 400（防任意写）；演练输入一律由 Host 自造；
  - 输入不能落在记录根内（§2 禁止输入/记录互相包含），所以演练目录是记录根 `${STATE_DIR}/s0/` 的**兄弟目录** `${STATE_DIR}/s0-rehearsal/`；
  - 每次调用都新建目录与**新记录**（同一个 `now` 也不复用），不覆盖上一次演练；
  - 失败沿用 `PreparationFailed` 语义：`status=failed` + `error` 原文 + 422，记录与已产生的部分副本保留；
  - **零写 `ENV_ROOT`**、不签闸门、不改变任何 run；返回记录的 `ready_for_execution` 仍恒 `false`，
    `ports/smoke` 仍 `waiting` ⇒ **S0-b 阻断不变**（§3、§6.2）。
- `GET /api/s0/{id}`：历史记录及当前只读核验；漂移即失败，不改历史清单。ID 限单层安全名称，不接受路径穿越。
- 报告下载只读。报告含路径、版本声明、时间、基线前后全量清单、RTL 清单、非 RTL 初检、阻断与失败原因；TB 空登记表明确未执行。
- 核验列出新增/删除/变化资产。准备期间全量非 RTL 保持一致；准备后只读核验对资产漂移报错，不把合法的未来运行输出与 S0-a 基础证据混同。时间只经 `now` 注入。

## 5 验收

先跑既有特征测试，再新增失败用例，再实现。临时工程验证完整派生、旧 RTL 删除、源不写、非 RTL 一致、路径/符号链接/已有目标拒绝、复制失败记录、内容/空目录漂移、记录恢复和 API。真实浏览器验证双段视图、表单、失败、重复提交、窄屏和既有闸门竞态。临时工程只验证软件，不能代替内网 UVS 验收。

## 6 S0 与 drill / N0–N16 的关系（2026-10-22 增补）

> 来源：[SPEC-REV-01](SPEC-REV-01-20261022.md) R5。本节回答"环境搭建在 drill 模式有没有体现、
> 『先 copy 再替换』能不能被验证到"。

**实测事实**：drill 模式的 N0–N16 **不复制环境、不替换 RTL**；`loop/workflows/main_flow.py` 与
`loop/workflows/chunks/host_steps.py` 中没有任何 S0 调用（`grep -n "s0\|S0"` 无命中），drill 的 N0
只是把冻结夹具的文件复制进 run 目录。因此 **drill 不能证明 S0，也不能证明"先 copy 再替换"**。

### 6.1 关系与禁止

- S0 是**运行前置准备**，不是 N0；S0 记录独立于 run，不得把 N0 改名为 S0，也不得静默切换进程 `ENV_ROOT`。
- run 文档必须带 `s0_record_id`（可空）。为空时运行视图显示"**未经 S0 派生**"（[SPEC-04](WEB_UI_SPEC.md) §4.5）。
- （**2026-10-27 已失效，见 §8.2-3**）S0 记录的 `ready_for_execution` 曾**恒为 false**（`S0Store.get()` 归一）：S0-b 接入前，
  任何"就绪/准出"说法都不成立。
- **运行入口的消费规则（2026-10-27 裁决 C12，传了才校验）**：`POST /api/runs` 的 `s0_record_id`
  仍然**可选、不强制**；但一旦传了：
  - `mode=real` ⇒ 记录必须存在（否则 400「S0 记录不存在」）且 `ready_for_execution=true`
    （否则 400「尚未准出 ⇒ real 运行被拒；可改用 drill 或先完成 S0-b」）。
    由于 `get()` 归一为 false，S0-b 接入前**real + 带 S0 记录一律拒**（有意的 fail-closed：
    没准出的副本不许真跑；准出不能被记录文件自称伪造）。
  - `mode≠real`（drill/rehearsal）⇒ **只做格式校验**，`s0_record_id` 只是来源徽标
    （drill 不覆盖 S0），不存在的 id 也不拦。
  该规则不改 N0–N16 拓扑、不改 `project == ENV_ROOT` 约束，也**不**表示 S0 已并入执行入口。
- **禁止**用 drill 结果声称 S0 通过；**禁止**以"run 跑完了"暗示环境已按 S0 派生。
- 若后续要把 S0 并入运行入口，必须是**显式选项**（如 drill 的 `s0_rehearsal`），且不得改变 N0–N16 拓扑、
  三道闸门与 `project == ENV_ROOT` 约束；未声明时默认不跑 S0。

### 6.2 两级验收（把"S0 是否成立"拆开）

| 级别 | 做法 | 能证明 | 不能证明 |
|---|---|---|---|
| **S0-rehearsal** | 在临时目录造一个小基线（含 `RTL/ TB/top.sv TESTLIB/ PKG/`、`docs/`（兼容 `doc/`）、`run`），用 `POST /api/s0` 完成一次 copy → 整体替换 RTL → 只读核验 | 复制完整性、旧 RTL 零残留、非 RTL 零污染、基线零写入、失败保留记录 | 真实环境的 TB 适配、三库冒烟、内网 UVS |
| **S0-real** | 内网真实环境副本 + 真实 RTL + 真实 UVS 三库冒烟 | S0-a 全部（+ S0-b，若接入） | —— |

> S0-rehearsal 可以在软件仓本机、无 UVS 的条件下完成；它是**软件能力验收**，
> 不是"环境已就绪"的证据。S0-b 的阻断状态不变（§3）。

### 6.3 「先 copy 再替换」的可验证判据

一次 S0 记录必须能回答下列问题（全部可从 `record.json` + 清单 + 报告复核，不依赖界面推断）：

1. `checks.copy=passed`：副本文件集合 = 基线，逐文件 md5 一致（含空目录）；
2. `checks.rtl=passed`：`work/RTL` 清单 == `rtl_source` 清单 ⇒ **旧 RTL 零残留**；
3. `checks.non_rtl=passed`：副本**非 RTL 部分**的清单与基线逐项一致 ⇒ 非 RTL 零污染；
4. `checks.baseline=passed`：基线前后清单逐项一致 ⇒ **基线零写入见证**；
5. 失败：`status=failed` + `error` 原文，保留本次部分副本与记录；**不删除、不隐式覆盖重试**（重试必须换新路径，≤3 次）。

### 6.4 工作台体现

- 环境准备视图展示记录 id、四项 checks 状态、指纹与阻断（S0-b 阻断如实显示）。
- drill / 现有闭环不经过 S0 ⇒ 运行视图徽标必须显示"未经 S0 派生（drill 不覆盖 S0）"。
- drill 里若要"看见" S0，只能通过：①运行视图来源徽标；②从该视图跳到环境准备视图；③显式勾选
  `s0_rehearsal` 时在 N0 之前跑一次小型夹具派生并把记录 id 写进 run 文档。**不得**在执行链路里
  插入隐含的 S0 节点，也不得因 rehearsal 通过而解锁任何准出。
- 若将来把 S0-rehearsal 做成"点一次"的动作，它仍**不并入** N0–N16 拓扑，也不改变三道闸门。

## 7 验收（增补：S0-rehearsal）

- 先跑既有 `loop/tests/test_s0.py`，不改期望；新增失败用例覆盖：copy 完整性、旧 RTL 删除、非 RTL 污染拒绝、基线零写入、失败保留记录；
- **工作台可一键完成 S0-rehearsal**：环境准备视图的「运行 S0 演练（临时小基线）」按钮 ⇒ `POST /api/s0/rehearsal`。
  成功后展示返回记录的 `id`/`status`/四项 checks（`copy`/`rtl`/`non_rtl`/`baseline`）与副本路径，并明确标注
  「演练：只证明 copy→replace→核验链路，**不是**环境就绪、不是 S0-b」；失败展示 `detail.error` 原文；
  按钮防双击，刷新准备记录不得清掉演练回执（表单与回执都不参与重建）；
- 工作台：环境准备视图能完成一次 S0-rehearsal 并显示四项 checks（浏览器验收证据）；
- **真实验收映射**（本次软件能力验收 = 下面三项，映射不到内网）：
  1. `loop/tests/test_s0.py` 的演练用例：200 + `status=prepared` + 四项 `passed` + `ports/smoke=waiting` +
     `ready_for_execution=false` + 副本 `work/RTL` 清单 == 演练新 RTL 清单（旧 RTL 零残留）+
     基线前后清单一致 + 重复调用不同记录 id + 非法 `now` 400 + 客户端路径参数 400 + `ENV_ROOT` 零写入；
  2. `spikes/run_software_checks.sh`（软件层全量，确认无回归）；
  3. 工作台一键动作的浏览器证据（成功回执 + 免责声明 + 失败原文）。
  这些证据**只**证明软件链路；**S0-real（内网真实环境 + 三库冒烟）仍未跑**，不得映射成"S0 通过/环境就绪"。
- 证据落 `doc/evidence/`（只增不改）。内网 S0-real 未跑时明确标"**未跑**"，不得记为通过，也不得用 drill 或 rehearsal 冒充。

## 8 未决登记：S0-b 接入与执行入口消费（2026-10-23）

> **状态**：**未实现**——登记后续开发，不阻塞现有闭环的真实运行。
> **写权**：Lead（`doc/spec/**` 唯一写者，见 [AGENTS.md](../../AGENTS.md) §3）。
> **触发（原话）**：真实 S0-a 派生走查后用户质疑「04 05未完成是需要补充修订的啊 怎么还有未完成这种东西呢」。
> **结论**：缺口成立，登记为本契约后续开发项；**不修改 §3 的当前边界**（本轮仍是 S0-a 已实现、S0-b 显式阻断）。

### 8.1 实测事实（登记依据，2026-10-23）

| 项 | 实测值 |
|---|---|
| 真实 S0-a 记录 | `S0-20261023T085921660208-0531c605aa`，`status=prepared` |
| checks | `copy/rtl/non_rtl/baseline = passed`；`ports/smoke = waiting` |
| `ready_for_execution` | `false`（§3 恒假） |
| 能力位 | `capabilities.tb_adapt=false, smoke=false` |
| 非 RTL 初检 | 副本 15579 条 == 基线 15579 条；基线派生前后全量清单逐条相同（零写入） |
| RTL 整体替换 | 副本 `RTL/` 1467 文件 vs 新 RTL 1467 文件，逐文件 MD5 全等、差异 0、旧 RTL 零残留 |
| 符号链接 | 副本内 0 个 |

结论：S0-a 已按 §2 完成；04/05 的“未完成”= §3 声明的功能缺口，不是操作缺失，也不是失败。**不得**在界面上把这两项手工置为通过。

### 8.2 目标行为（接入后应满足的契约）

1. `ports`：**Host 从基线 RTL 与新 RTL 确定性派生**端口差异，再由模型逐 hunk 提议、人逐条确认后才允许写副本 TB 顶层；分三段，判据独立：
   - **派生（Host，无模型、无副作用）**：输入 = `record.baseline/RTL/**` 与 `record.rtl_source/**`（`prepare()` 已各自落盘 manifest，可复算）；只读、只解析模块端口声明，并按**编译期宏**（`all_define.txt` 的 `-define`）求值条件编译；**同一输入必须得同一输出**（输出表 md5 可复算）。输入缺文件 ⇒ `ports=failed`。**解析不了的模块**（老式非 ANSI 等）按"是否真的变了"判：两侧都解析不了且源文件 md5 相同 ⇒ 语义未变、不阻断；**一侧解析成功另一侧解析不了、或两侧 md5 不同 ⇒ `ports=failed`**（不得降级为"无差异"）。
   - **提议（模型）**：对每条候选差异给出适配方案（改哪一行、改成什么、影响哪些用例），写入记录的 `proposals/`，**不写副本**。
   - **确认（人）**：逐条 `confirmed`/`rejected`；**只有 `confirmed` 的 hunk 允许落盘**，确认记录只增不改。
   - **TB 顶层文件**：本契约原写 `TB/top.sv`，但真实环境**没有**该文件（基线清单 `kb/baselines/v0/allfiles.md5` 里 TB 下只有 `tbtop.sv`/`top_env.sv`/`top_if.sv`/`top_cfg.sv`/`top_pkg.sv`/…），编译驱动用的是 `./TB/tbtop.sv`。因此改为：**顶层文件由编译驱动决定**（`kb/tools/run_guarded.sh` 的 `uvlan -work tb` 行，单一来源），作为记录字段 `tb_top` 显式落盘；`tb_top` 缺文件 ⇒ `ports=failed`。
   - **work 见证与授权落盘（2026-10-27 新增正文）**：`prepare()` 落 `work-after.json` 作为派生时刻的副本见证；
     **每次授权落盘后追加一份 `work-after.<n>.json`**，记录里以 `work_witness` 指向最新一份。追加新见证前，Host
     **必须**先确认"当前副本相对上一份见证只有 `TB/<tb_top>` 一个差异"，否则拒绝落盘（防"用落盘刷新见证洗白既有未登记改动"）；
     漂移核验一律取 `work_witness` 指向的那份，因此合法落盘不会被判成漂移，而未登记改动仍会被抓。
   - 登记表每项含：TB 编号、接口差异来源（基线/新 RTL 的 md5）、位置/原片段、真实 unified diff、范围判定、影响用例、复核状态（`proposed`/`confirmed`/`rejected`）。**空表不得准出；未确认的 hunk 不得写入。** 派生零差异时，登记表须带派生证据（两侧输入 md5、解析到的模块数与 TB 顶层文件 md5），并断言副本 TB 顶层**无未登记改动**。
2. `smoke`：在副本内真实执行三库编译，驱动**复用** `kb/tools/run_guarded.sh --mode compile-only`（N7 已在用：串行锁、沙箱工作树、`uvs.setup` 自愈、编译选项逐字自检），落每段命令、退出码、**工具自印** `Compilation: N error(s), M warning(s)`、`Error-<code>`/`Warning-<code>` 明细、原始日志路径。判据：`N>0` ⇒ `smoke=failed`；warning 用**基线相对增量**评（同用例在基线树与副本各编一次，`added = codes(副本) − codes(基线)`；`added` 或同 code 计数上升 ⇒ 每条必须评估，机制同 `ports` 的"人确认"：评估落账在记录目录 `s0b/warning_decisions.jsonl`，**只增不改、带 sha256 锚**，入口 `POST /api/s0/{id}/warnings`；零增量无需外部裁决）。基线编译须在独立沙箱工作树内跑，断言基线零写入。**禁止**用 `grep 'error'` 数行代替（会把 `0 error(s)` 汇总行本身算成错误）。
3. `ready_for_execution`：仅当 `copy/rtl/non_rtl/baseline/ports/smoke` 全 `passed` 且当前只读核验无漂移时为 `true`；其余一律 `false`。
4. 执行入口**消费**该判据：非 `true` 时拒绝 `real` 启动并给出结构化原因；`POST /api/runs` 的 `s0_record_id` 由界面写入 run 文档，运行视图来源徽标据此显示（不再恒为“未经 S0 派生”）。
5. 失败语义不变：越界先停手登记，保留部分副本，不删除用户目录、不隐式覆盖重试；否决后逐 hunk 回滚并重跑冒烟。

### 8.3 待开发项

| 编号 | 开发项 | 落点 | 依赖 / 开放问题 |
|---|---|---|---|
| **D1** | 接口差异来源（**已裁 2026-10-27：Host 确定性派生**；**已实现 2026-10-27**） | `loop/host/sv_ports.py`（端口解析 + 差异派生，唯一实现）；`loop/host/s0.py` | **Q1 关闭**：契约见 §8.2-1；**不再消费外部接口报告**；TB 顶层文件由编译驱动解析（`tb_top`） |
| **D2** | 副本 TB 顶层适配 + 逐 hunk 登记（含回滚）（**已裁 2026-10-27：模型提议 + 人确认**；**已实现 2026-10-27**） | `loop/host/s0.py`（提议/确认/落盘）、`loop/services/api.py`、环境准备视图 | **Q2 关闭**：模型只写 `proposals/`；人确认后 Host 才按已确认内容落盘；确认记录只增不改；禁止“先改后申请” |
| **D3** | 三库真实冒烟（**Q3 已于 2026-10-27 关闭：改为确定性判据**；**已实现 2026-10-27**） | `loop/host/s0.py`（smoke 段）+ 日志解析模块（唯一实现）；驱动复用 `kb/tools/run_guarded.sh --mode compile-only` | **Q3 关闭**：判据见 §8.2-2；不再需要外部白名单。依据：同用例两次编译 warning 集合恒等；注入重复定义后 4→5 且新增 `Warning-120162`（STATUS §100） |
| **D4** | 准出判据接进执行入口 + `s0_record_id` 透传（**已实现 2026-10-27**） | `loop/host/s0.py` 的 `ready_for_execution`（唯一判据口）+ C12 的 `_check_s0_record_for_run` | 六项全 `passed` 且无漂移/错误才为 `true`（实测：真实环境副本上 `ready_for_execution=True`，STATUS §102） |
| **D5** | 视图状态从“未接入”改为真实流转（**未做**） | `loop/web/index.html`、`loop/web/s0.js` | 后端已能返回真实 `ports/smoke` 与 `ready_for_execution`；界面灰态与确认交互仍待做（需界面门） |

### 8.4 红线（接入轮不得违反）

1. 不得以现有 N7 两段编译、用户勾选、替身或单独 `rc=0` 替代三库证据（§3）。
2. 不得实现未经验证的 SV 自动改写；无登记差异不得准出。
3. 不得把 `ports/smoke` 直接置 `passed`，也不得用演练/临时工程结果映射为 S0 准出（§6.2）。
4. 不得在 `real` 入口用默认值兜底 S0 缺失；拒绝必须发生在提交前（AGENTS.md §2 硬性纪律 5）。
5. 三库命令一律以环境侧协议为准；拿不到协议就保持阻断并登记。
6. **派生不改写**：Host 派生只产出候选差异表，**不得直接改写** TB 顶层或任何 SV；落盘必须有人对该 hunk 的 `confirmed` 记录（Q2）。
7. **冒烟不得裸 grep**：error/warning 一律取工具自印汇总行与 `<Error|Warning>-<code>` 明细行，并**分别**记录 `rc`；`rc=0` 不等于 `0 error`。

### 8.5 验收（接入轮）

- 先跑既有 `loop/tests/test_s0.py` 不改期望，再新增失败用例。**判定口径（2026-10-27 落实，与实现/用例一致）**：
  - 接口差异**为空**时，`ports` 可以 `passed`，但必须同时满足：派生证据齐全（两侧 `RTL` 输入 md5、解析到的模块数、TB 顶层 md5）
    且副本 TB 与基线**逐字节一致**；**"空表"本身不得作为准出依据**；
  - 三库 `error(s)>0` ⇒ `smoke=failed` 且报告含逐段命令、rc、计数与原始日志路径；任一侧日志缺汇总行、任一侧 rc≠0
    ⇒ 不得 `passed`（读数不可信不等于零告警）；
  - 同一副本二次核验漂移即失败（授权落盘会追加新的 work 见证，见 §8.2-1）。
- **本仓侧已完成（2026-10-27，S0-b 接入轮）**：派生/提议/确认/落盘/冒烟/准出六环已接线并通过用例
  （`tests/test_sv_ports.py`、`tests/test_s0b.py`）；真实环境副本上六项全 `passed`、`ready_for_execution=True`、
  基线零写入（STATUS §102）。**内网真机验收与 D5 界面仍未做**。
- **执行入口消费（C12 + S0-b 接入轮，已完成）**：「`ready_for_execution=false` 时 `real` 启动 400 且原因可读」由
  `services/api._check_s0_record_for_run()` + 4 条用例覆盖（不存在 / 未准出 / 文件自称 ready 仍拒 / drill 与不传不拦）；
  `get()` 能返回 true 的允许路径、三库 `smoke`、接口适配已在 S0-b 接入轮落地（STATUS §102）；
  **仍未做的是内网真机验收与 D5 界面**。
- **派生确定性**：同一 `baseline/RTL` + `rtl_source` 连续派生两次，输出表 md5 相同；`baseline/RTL` 或 `rtl_source` 缺文件 ⇒ `ports=failed`。**模块解析不了时按 §8.2-1 的 md5 规则判**：两侧都解析不了且源文件 md5 相同 ⇒ 不阻断（语义未变）；一侧解析成功另一侧解析不了、或两侧 md5 不同 ⇒ `ports=failed`（不得当作"无差异"）。
- **确认门槛**：对未 `confirmed` 的 hunk，副本 TB 顶层必须**逐字节不变**（md5 断言）；确认记录追加后再落盘，旧确认不得被覆盖（只增不改）。
- **冒烟判据**：每段必须落 `命令 / rc / error(s) / warning(s) / Error-<code> 明细 / 日志路径`；`error(s)>0` ⇒ `smoke=failed`；warning 必须落 `added/removed/count_increase`，`added ∪ count_increase` 非空时每条都要有评估记录才算 `smoke=passed`。
- `bash spikes/run_software_checks.sh` 无回归；文档门零断链；数字回写 `doc/STATUS.md`。
- **内网真机验收**：真实副本上跑一次 S0-a + S0-b，三库冒烟有原始日志与 error/warning 计数，`GET /api/s0/{id}` 与报告可复核；临时工程与演练不得替代。

### 8.6 优先级与影响面

- 优先级 **P1**：不阻塞当前真实 run（执行入口尚未消费 S0 判据）。
- D4 落地前，S0 记录只作为证据；落地后任何 `real` 启动都必须带合法 `s0_record_id` 且判据为真，否则拒绝。
- 本登记只增不改：接入轮完成后回填 D1–D5 的落点与验收数字，不删除本文。

## 9 单一 RTL 文件夹入口（一键派生与自动切换，2026-10-30）

> 来源：人 2026-10-30 需求原文「入口处只传入一个完整的 RTL 代码文件夹，不再像现在整个环境，流程也能正常跑通」。
> 本节**只增不改**；对 §2「完整复制」与 §6.1「不偷偷切换进程 `ENV_ROOT`」是**显式收窄/补充**，
> 不改变既有记录、闸门与 N0–N16 语义。

### 9.1 入口与默认值

`POST /api/s0/from-rtl`（界面：环境准备页「派生并校验 →」）只要求一个路径：

| 字段 | 必填 | 缺省 |
|---|---|---|
| `rtl_source` | 是 | ——（目录名必须为 `RTL` 或 `SRC`，见 9.2） |
| `baseline` | 否 | **原始环境根**（当前进程 `ENV_ROOT`；已切换过则取持久化的 `origin_env_root`） |
| `baseline_version` | 否 | `RTL@<folder-basename>+<UTC 时间戳>`（仍是操作者声明，不伪装已验证 commit） |
| `work_env` | 否 | `<TOOL_ROOT>/workspaces/<origin-env-name>-derived-<UTC 时间戳>/`（父目录已存在、目标必须不存在） |
| `smoke_case` | 否 | `sort(TESTLIB/*.sv)[0]` 的 basename；**记录里显式落账**，禁止从日志猜 |

> **2026-10-30 决定（见 §9.9）：入口改为单输入二选一** —— 只给 `rtl_source`（新版 RTL 文件夹，
> 环境资产取原始环境根）、或只给 `baseline`（**环境项目目录**，整套工程，RTL 用自带的不替换）；
> 两者都给仍兼容（= 环境项目 + 新版 RTL，行为同 §9.3/§9.4）；都为空的请求一律 400。
> 因此 `rtl_source` **不再是唯一必填**；「baseline」一词在本节的界面文案统一叫「环境项目目录」，
> **不要**与运行期的对比基线（`kb/baselines/<id>`，见 §3.1）混为一谈。

### 9.2 RTL 根判定（不猜）

按目录名判定：`RTL` ⇒ 映射到 `RTL/`（整棵替换）；`SRC` ⇒ 映射到 `RTL/SRC/`（只替换该子树）；
其它名字 ⇒ 400 并列出合法取值。**不接受**按内容/基线相似度猜测路径。

### 9.3 选择性复制（收窄 §2 的“完整复制”）

复制源 = `baseline`；跳过规则**显式落账**，不静默：

- 排除整目录：`kb/runs`、`loop`、`SIMLIB_RUN`、`.git`、`COV`、`WAVE`、`LOG`、`RUNS`、`__pycache__`；
- 符号链接：不复制、不跟随，记 `{rel, reason:"symlink", target}`（防指回基线）；
- 随副本复制的数据子集：**只** `kb/{baselines,index,conflicts,adjudication}`（副本自包含：
  派生环境的 `WORKSPACE_ROOT = <work>/kb`）；`kb/` 下其余条目（`kb/tools`、`kb/schema`、
  `kb/runs`、`kb/README.md`、`kb/FIXTURE_IDENTITY.md`…）不复制并落账——`kb/tools`/`kb/schema`
  的权威在软件根，副本里不得出现第二套冻结副本。

`copy` 检查判据：**副本实际复制集合**逐文件 md5 == 基线同一集合。被跳过项**不进判据**，
但必须出现在 `copy_plan.skipped` / `copy_plan.excluded_roots` 且理由可核（否则等于静默忽略）。

### 9.4 RTL 替换与检查语义

- `RTL` 根：删除副本 `RTL/` 后整棵放入；`rtl` 检查 = `manifest(work/RTL) == manifest_filtered(rtl_source)`。
  两者**同一口径**：RTL 源里的 VCS/缓存目录（`.git`/`.svn`/`.hg`/`__pycache__`）不复制并落账
  （记录 `rtl_plan.skipped`）；源里的符号链接仍按 §2 **拒绝**（不跳过）。
- `SRC` 根：只删除副本 `RTL/SRC` 后放入；`rtl` 检查 = `manifest(work/RTL/SRC) == manifest_filtered(rtl_source)`
  **且**副本 `RTL/` 其余部分与基线同名部分逐文件一致（防顺手改 vendor）。
- 错目录**只告警不拦截**：记录 `folder_warning = {same, added, removed, ratio}`；界面高亮，允许继续。
- 摄入范围**不变**：N1 仍只摄入 `RTL/SRC/imports` + `RTL/RTL_COMMON`（红线 8：旧基线口径可比）；
  两者缺一 ⇒ N1 显式失败，不在 S0 里伪造。

### 9.5 自动续跑与准出

1. `copy → rtl → non_rtl → ports` 由 `from-rtl` 一次完成；
2. `ports` 有差异 ⇒ 停在“待确认”：沿用 S0-b 的提议/逐 hunk 确认/否决与落盘语义（§8.2-1 不变）；
   处置后 `POST /api/s0/{id}/advance`；
3. `advance` 在 `ports=passed` 时**自动**跑一次三库冒烟（`smoke_case`），落 `smoke` 结论；
4. 六项全 `passed` 且无漂移 ⇒ `ready_for_execution=true`，界面自动进入 9.6。
   （§9.9-4 例外：**环境项目入口**下 `rtl` 记 `skipped`，其准出判据为“除 `rtl` 外五项全 `passed` 且无漂移”。）

### 9.6 自动切换（“服务必须活着”）

- 存在非终态 run（`running`/`waiting_gate`）⇒ **拒绝**切换，理由可读；
- 切换 = 写 `pending` → 起独立 `host/switch_supervisor.py` → 旧进程优雅退出；supervisor 负责：
  等端口释放 → 以 `LOOP_ENV_ROOT=<work>`、`LOOP_WORKSPACE=<work>/kb`、同一 `LOOP_STATE_ROOT`/端口起新服务 →
  轮询 `/api/health` 并校验 `env_root == target` → 成功落 `active`；失败则杀新进程并用**原环境根**
  重起旧服务，落 `rollback` + `reason`（不改记录为 passed、不冒充成功）；
- 切换记录 `env-switch.json` 落在 S0 记录目录（`/api/s0/{id}` 只读投影）；
- `origin_env_root` 一旦记录不再改变：后续派生始终以它为基线源（副本不再当基线，防套娃）；
- 「切回原环境」= 以当前根为目标反向执行同一流程，并保留副本（副本是数据根与证据）。

### 9.7 失败语义

任一步失败 ⇒ `status=failed` + `error` 原文；副本与记录保留；环境根不变；重试必须新副本路径（§2 不变）。
`uvlan` 不可用 ⇒ `smoke=waiting`（不冒充 passed），切换不发生。

### 9.8 验收

- 单测：根判定、选择复制与跳过清单、SRC 根只核子树、错目录告警、`pending→active/rollback` 状态机、
  活跃 run 拒绝、切回；
- real 链：真实副本上派生 + 冒烟 + 切换，`/api/health` 显示新根，原 `ENV_ROOT` 零写入（`baseline` 检查项）。

### 9.9 单输入二选一：环境项目入口（2026-10-30 决定）

> 来源：人 2026-10-30 两次确认——① 「这个不应该叫『基线工程目录』，而且『新版 RTL 文件夹』和它应该是 2 选 1
> 的关系，我选择一个就行了，不一定 RTL 就是必填的吧？」；② 三问拍板：只给环境项目时 **RTL 用该项目自带的、不替换**；
> 字段名用 **环境项目目录**；界面单选、API 仍兼容两者同时给。
> 本节只增不改 §9.1–§9.8 的既有语义；对 §9.1「`rtl_source` 必填」与 §9.5-4「六项全 passed」是**显式收窄**。

#### 9.9-1 输入与模式判定（不猜）

同一个端点 `POST /api/s0/from-rtl`，字段名不变，**判定只看字段是否为空**：

| 请求 | `entry` | 语义 |
|---|---|---|
| 只有 `rtl_source` | `rtl_folder` | 现行 §9.3/§9.4：环境资产 = 原始环境根，RTL 整体替换 |
| 只有 `baseline` | `env_folder` | **环境项目入口**：`baseline` 是整套工程目录；选择性复制成副本；**不替换 RTL** |
| 两者都给 | `rtl_folder` | 环境项目 + 新版 RTL（§9.3/§9.4 不变）；界面不展示此组合，供自动化/既有调用 |
| 两者都空 | —— | 400：必须提供「环境项目目录」或「新版 RTL 文件夹」之一 |

- `baseline` 校验与 §9.1 相同（须为独立实体目录、路径不含软链、在允许根内、含 RTL、TB、PKG、TESTLIB 四类目录与 `docs/`（兼容 `doc/`）、
  有运行入口与 TB 顶层）；`rtl_source` 校验与 §9.2 相同（目录名 `RTL`/`SRC`）。
- 界面文案：`baseline` 这一格叫「**环境项目目录**」（副标题：整套工程（RTL、TB、PKG、TESTLIB 四类目录 + 文档 + `kb/`））。

#### 9.9-2 `env_folder` 记录与检查语义

- 记录：`entry="env_folder"`、`rtl_source=null`、`rtl_prefix=null`、`rtl_plan=null`、`folder_warning=null`；
  `baseline` 的缺省版本 = `ENV@<basename>+<UTC 时间戳>`；其余字段（`copy_plan`、`smoke_case`、`origin_env_root`、`auto`）不变。
- 六项：`copy`（§9.3 判据，含 RTL 全部文件）、`non_rtl`、`ports`（§8.2 派生，本模式应为零差异）、
  `smoke`（§9.5-3）、`baseline`（零写入见证）语义不变；
  **`rtl` 记 `skipped`**，理由固定为：
  `环境项目入口：未提供新版 RTL，副本 RTL 与源环境逐文件一致（copy 判据已覆盖），不做替换`。
- 禁止用 `skipped` 掩盖任何失败：`rtl_folder` 入口下 `rtl` 出现 `skipped` 一律视为异常（不准出）。

#### 9.9-3 阶段回执

`rtl` 为 `skipped` 时，阶段回执与报告显示「未替换（环境项目入口）」；既不显示为通过，也不显示为阻断。

#### 9.9-4 准出判据（fail-closed）

`ready_for_execution` 唯一判据（`s0b.ready_for_execution`）：

```
status == "prepared" && not error
&& copy/non_rtl/ports/smoke/baseline 五项全 == "passed"
&& (rtl == "passed"  或  (entry == "env_folder" && rtl == "skipped"))
```

未知 `entry`、缺任一 check ⇒ `false`；除上述唯一例外外任何非 `passed` ⇒ `false`。

#### 9.9-5 报告与不变量

- 报告的「阻断项」与「无阻断」结论必须与 9.9-4 同一判据（`skipped` 不算阻断）；报告头措辞按模式区分。
- `_verify` 在 `rtl_source` 为 `null` 时**跳过**该项比对（不把 null 当漂移），`baseline`/`work_env` 见证照旧。
- 活跃 run 拒绝、缺失数据根拒绝、切换/切回/删除副本、prefill 运行配置、原 `ENV_ROOT` 零写入等不变量全部不变。

#### 9.9-6 验收

- 单测：模式判定（只 rtl / 只 baseline / 同时给 / 都空）、`env_folder` 的 `rtl=skipped` 与记录字段、
  `ready_for_execution` 的四种组合（env+skipped=true、rtl_folder+skipped=false、缺 check=false、五项非 passed=false）、
  `_verify` 在 `rtl_source=null` 时不报漂移、报告阻断项口径；
- API：只给 `baseline` ⇒ 200 且 `entry="env_folder"`；都空 ⇒ 400；两者都给 ⇒ 与 §9.3/§9.4 一致；
- 界面：单选切换、只填一格即可提交、`rtl` 阶段显示「未替换（环境项目入口）」；
- real 链：环境项目入口派生 → 六项（`rtl=skipped`）→ 准出 → 切换 → `/api/health` 新根；原 `ENV_ROOT` 零写入；切回。
