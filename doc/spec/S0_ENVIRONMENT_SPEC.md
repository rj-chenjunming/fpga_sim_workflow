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

**本轮实现 S0-a 派生与持续只读核验，S0-b 保持显式阻断。** 内网 UVS 不可访问，附件没有可校验的三库驱动协议；不猜编译命令、不实现未经验证的 SV 自动改写。UI 列出接口核对、变更登记和三库冒烟未接入，`ready_for_execution` 恒为 false。此为功能缺口，不是“待授权通过”。

后续接入须补可验证驱动，并在执行入口消费完整 S0 判据。当前运行入口维持旧契约，明确标为“现有闭环”，不得称为附件新版 S3。S0-a 完成不能解锁新版执行。

> 后续开发项（D1–D5）、开放问题（Q1–Q3）与接入轮验收见 [§8](#8-未决登记s0-b-接入与执行入口消费2026-10-23)。

> **2026-10-27 修订（Q1/Q2 已裁、Q3 关闭）**：① `ports` 改为 Host 确定性派生、模型提议 + 人确认后落盘（§8.2-1）；
> ② `smoke` 的驱动确认复用既有 `kb/tools/run_guarded.sh --mode compile-only`，warning 判据改为基线相对增量（§8.2-2）；
> ③ 本契约原写的 `TB/top.sv` 在真实环境**不存在**（基线清单 TB 下为 `tbtop.sv` 等），改为由编译驱动解析 `tb_top`；
> ④ **S0-b 仍保持阻断**，直到 D1–D4 落地并过 §8.5 验收。上文“不猜编译命令”的前提已变化：命令来自仓库内既有驱动，
> 且在派生副本上实测 `rc=0`（STATUS §99.1）。

## 4 API 与报告

- `GET /api/s0`：默认基线、允许根、记录索引和能力边界。`capabilities.rehearsal=true` 只表示"可以点一次本机演练"，不表示环境就绪，也不表示 S0-b 已接入（`tb_adapt`/`smoke` 仍为 `false`）。
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
- S0 记录的 `ready_for_execution` 当前**恒为 false**（`S0Store.get()` 归一，§3）：S0-b 接入前，
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
- **部分已完成（2026-10-27，C12）**：「`ready_for_execution=false` 时 `real` 启动 400 且原因可读」已落地为 `services/api._check_s0_record_for_run()` + 4 条用例（不存在 / 未准出 / 文件自称 ready 仍拒 / drill 与不传不拦）；S0-b 其余验收（`get()` 能返回 true 的允许路径、三库 `smoke`、接口适配）仍未做。
- **派生确定性**：同一 `baseline/RTL` + `rtl_source` 连续派生两次，输出表 md5 相同；`baseline/RTL` 或 `rtl_source` 缺文件、或模块解析不了 ⇒ `ports=failed`（不得当作“无差异”）。
- **确认门槛**：对未 `confirmed` 的 hunk，副本 TB 顶层必须**逐字节不变**（md5 断言）；确认记录追加后再落盘，旧确认不得被覆盖（只增不改）。
- **冒烟判据**：每段必须落 `命令 / rc / error(s) / warning(s) / Error-<code> 明细 / 日志路径`；`error(s)>0` ⇒ `smoke=failed`；warning 必须落 `added/removed/count_increase`，`added ∪ count_increase` 非空时每条都要有评估记录才算 `smoke=passed`。
- `bash spikes/run_software_checks.sh` 无回归；文档门零断链；数字回写 `doc/STATUS.md`。
- **内网真机验收**：真实副本上跑一次 S0-a + S0-b，三库冒烟有原始日志与 error/warning 计数，`GET /api/s0/{id}` 与报告可复核；临时工程与演练不得替代。

### 8.6 优先级与影响面

- 优先级 **P1**：不阻塞当前真实 run（执行入口尚未消费 S0 判据）。
- D4 落地前，S0 记录只作为证据；落地后任何 `real` 启动都必须带合法 `s0_record_id` 且判据为真，否则拒绝。
- 本登记只增不改：接入轮完成后回填 D1–D5 的落点与验收数字，不删除本文。
