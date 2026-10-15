# `loop/` — 变更影响闭环的编排层与操作界面

> **状态**：P0 可运行（drill 夹具全链路已验证；real 模式未在真机全跑）
> **上游契约**：`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（业务与不变量 I1–I8）
> **本层契约**：`doc/spec/LOOP_ORCHESTRATION_SPEC.md`（owner / 生命周期 / 长任务 / 准入 / 恢复 / 投影）

---

## 1 这层是什么

把上游 16 个节点（N0–N16）与三道人工闸门落成**可交互、可重启、可拒绝**的系统：

- **编排**：`agently` TriggerFlow 的稳定拓扑（源码内定义），3 道闸门 = durable graph interrupt；
- **界面**：FastAPI + 单文件静态页 —— **闸门操作台 + 长任务看板**（v1 范围）；
- **准入**：单槽（`uvs.setup` 是仓库根下全局单文件）+ 队列 + 取消；
- **恢复**：执行快照 + 记录库，跨进程重启后能重新附着到在跑的作业。

### 它不是

- 不是第二个状态机。**状态权威 = TriggerFlow 执行 + `kb/tools/gate.py`**；界面只是只读投影 + 传输。
- 不重新实现业务判定。N2/N5/N16 一律调用既有 `kb/tools/*.py`。
- 不写冻结资产。`RTL/ TB/ PKG/ TESTLIB/ doc/ kb/baselines kb/index kb/conflicts kb/tools` 全部只读
  （`host/paths.FROZEN_FOR_WRITE`）。

---

## 2 快速开始

```bash
cd loop
./run.sh                      # 默认 http://127.0.0.1:8099
LOOP_PORT=9000 ./run.sh       # 换端口
```

环境已建好（Python 3.11.7 + agently 4.1.4.8）：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
```

**`agently` 钉 4.1.4.8**：技能文档与参考工程都对齐这一代 API
（`flow.to/when/for_each`、`execution.pause_for/continue_with`）。
镜像上有更新版本（4.1.4.10），但其 `TriggerFlow` 表面已重构，不为未文档化的 API 猜签名。

跑测试：

```bash
cd loop && .venv/bin/python -m pytest -q      # 38 项，约 22 s
```

---

## 3 目录

```
loop/
  run.sh                    启动（uvicorn）
  app.py 相关入口见 services/api.py:main
  host/                     host 侧 owner（不碰业务判定）
    paths.py                仓库根锚定（找 kb/tools/kb_lib.py）+ 冻结守卫
    admission.py            单槽准入 / 队列 / 审计（N9-3 修复：锁带 format_version）
    job_runner.py           长任务提交 / 看护 / 重附着 / 取消
    progress.py             稳定应用事件投影（白名单 kind）
    evidence.py             两套口径与观测印记的**抽取器**（数字全由文件数出）
    gate_authority.py       闸门枚举的唯一来源（取自 kb_lib，本层不手抄）
  workflows/
    context.py              一次运行的 host 依赖（经 runtime_resources 注入）
    main_flow.py            稳定拓扑 N0–N16 + RunManager（生命周期/恢复/投影）
    chunks/host_steps.py    N0 N1 N2 N5 N7 N16（调 kb 工具）
    chunks/model_steps.py   N3 N6 N8 N10 N11 N12（**当前为确定性替身**，见 §5）
    chunks/long_jobs.py     N9 提交+停放 / N15 回归
    chunks/gates.py         三道闸门（pause/resume + 显式分叉）
  services/
    contracts.py            对外投影 + 六项信任缺口的服务端判定
    api.py                  FastAPI（唯一入口）
  web/index.html            单文件前端（零外链）
  tests/                    38 项
  state/                    槽/队列/事件/快照（可删）
```

---

## 4 四条会让人踩坑的设计决定

### 4.1 长任务必须"停放"而不是"阻塞"

`agently-triggerflow/references/recovery.md:75-77`：快照里若有 `running` 帧，**`load` fail-closed**。

所以 N9 拆成两段：

```
n9_submit: 申请单槽 → 提交外部作业 → 记 job_id 进 state → 返回
n9_park:   pause_for(type="job_done", resume_to="self")
           ← 此刻执行是 interrupt，不是 running ⇒ 快照可落可载
           外部完成 → job_runner 看护回调 → execution.continue_with(...)
```

**必须用 `resume_to="self"`**：用 `"next"` 时 `pause_for` 的返回值是**中断描述符**而非恢复载荷，
本 chunk 永远看不到作业结局，死任务会被静默当成继续（这是实测到的真 bug）。

恢复后**以日志为权威重新取数**，不信任 resume 载荷里的数字。

### 4.2 单槽是 host 持有的，不是 TriggerFlow 并发

`uvs.setup` 是本仓库根下的全局单文件 ⇒ 同工作目录最多一个仿真/编译。
`concurrency=N` 在这里是错的。真正的并行只跨机（`run_tc.py`，5 机 × 2 LIC）。

**锁带 `format_version`**：陈旧判定按格式版本决定解析哪些字段；
遇到不认识的格式**拒绝自动清理并升级人工**（N9-3：误删活动锁曾导致约 10 分钟无互斥）。

**终态必须释放**：成功/失败/取消都要释放且幂等。修复前死任务会把槽永久占住，
把一个 run 的失败放大成后续全体挂起。

### 4.3 闸门枚举不许手抄

`kb_lib.GATE_DECISIONS` 是唯一来源：

| 闸门 | 权威枚举 |
|---|---|
| `G1_diff_confirm` | `confirmed` / `ignored` / `disputed` / `pending` |
| `G2_report_accept` | `accept` / `rework` / `pending` |
| `G3_regression_decision` | `full_now` / `subset_only` / `milestone_only` / `defer` / `pending` |

本层曾自造 `full_regression` / `escalate_to_human` / `ignored_with_reason`，
结果用户点到一个权威不认的值，收到的是 argparse 用法错误而不是业务拒绝。
现在：`host/gate_authority.py` 从 `kb_lib` 导入，`chunks/gates.validate_branches()` 做漂移自检，
`run_view.gate_options` 把枚举下发给界面 —— **前端只渲染，无从漂移**。

**`pending` 是状态，不是可提交动作。**

### 4.4 拒绝必须发生在提交前

I6（非 human actor）与 I4（冲突未清零时选全量/子集回归）都在
`RunManager.decide()` 里**先判**，再签、再恢复。

原因：`pause_for(resume_to="self")` 的 `max_resumes=1`。若阻断发生在恢复之后，
用户的一次误选就会消耗掉中断并把执行打成 `failed`（实测 `self_resume_limit_reached`），
**闸门从此不可用**。现在误选得到 403/400，闸门保持待决策。

---

## 5 当前限制（不得当成已具备）

| 项 | 现状 |
|---|---|
| 模型节点 | **已接真 ModelRequest**：N3/N6/N8/N11/N12 走宿主已声明的 provider（`openai-responses`，`origin-deepseek-v4-1-flash`），5/5 实测 live 且 Host 校验零问题。凭据不可用时自动退回**显式标注**的确定性替身（`standin=True`），离线测试即走此路径。 |
| N10 对账 | **数字与分桶归 Host**（`host/evidence.py`，确定性、零丢失：夹具上 1622/1622 地址、1687/1687 条目），**三分类归模型**（24 个桶逐桶判定）。Host 校验覆盖性/枚举/依据，并交叉核对「本轮引入」是否真落在修订点上（不重叠的断言记为冲突且不采信）。夹具实测：模型把 24/24 桶判为既有缺陷 ⇒ 1687 条目，Host 冲突 0。 |
| real 模式 | N9 已改为经 `kb/tools/run_guarded.sh --mode full`（身份头 + 归档 + 自愈 + 串行锁），但**未在真机跑过一次完整全跑**（单用例 ≈19 min，修订后可达 22.8 h）；归档腿本身已用 `uvlan` 桩在真实代码路径上验证。 |
| N15 回归 | drill 下不真跑；`for_each(concurrency=1)` 已就位，跨机 `run_tc.py` 未接。 |
| N16 晋升 | 本层**恒为 `--dry-run`**，绝不写 `kb/baselines/`。 |
| F-N16-04 | 拒绝后残留 `staged/` 仍在（界面作为告警呈现，未清理）。 |
| E-2 | **已修**：`run_guarded.sh` 归档腿原只 glob `$ROOT/SIMLIB_RUN/log`，与 `compile-only`/`full` 实际落点 `$EVIDENCE_DIR` 不符 ⇒ 必空；且这两个模式没启动轮询。现候选路径覆盖两处、两分支都轮询、归档件 444 只读、加稳定性判定防半截件堆积、`_guard.log` 不自我归档；N9 真实路径也改为走 `run_guarded.sh --mode full`。归档的演练轮**不回填**（它是冻结见证）。 |
| 单机单用户 | 无鉴权、无多用户；`actor` 只是自报字符串。 |

---

## 5.1 模型接入（provider）

配置在 `SETTINGS.yaml`（非机密）+ `host/model_provider.py`（解析与注入）：

1. **密钥不落仓库**：优先 `$LOOP_LLM_API_KEY`，其次宿主 DSH 凭据库
   `~/.dsh/.credentials.yaml` 的 `refs.<apiKeyEnv>`。对外投影（`/api/health`）**不含密钥**。
2. **端点不硬编码**：留空即复用宿主 `~/.dsh/settings.yaml` 已声明的 provider，
   避免在仓库里再抄一份内部地址而漂移。
3. **proxy 必须显式设**：插件 `request_builder.py:324` 写死
   `client_options.setdefault("trust_env", False)` ⇒ 环境代理**不会**被 httpx 读取。
   不设直接 DNS 失败（实测 `[Errno -2] Name or service not known`）。
   留空则取 shell 的 `HTTPS_PROXY/HTTP_PROXY`。
4. **`max_tokens` 要给足**：本网关模型是推理模型，32 tokens 会被 `reasoning_content` 吃光、
   `content` 为空且 `finish_reason=length`（实测）。
5. **`LOOP_LLM_MODE=standin`** 强制离线（测试套件默认如此）；`live` 要求必须真拿到 provider。

契约分三处、各归其主：

| 关注点 | 归属 |
|---|---|
| 字段形状（类型/必填/枚举）| `prompts/node_schemas.py`（Pydantic）|
| 行为规则（info / instruct 散文）| `prompts/loop_nodes.yaml` |
| 确定性验收（数字一致性、offered-key 成员性、否决规则）| `workflows/chunks/model_steps.py::_validate` |

**为什么形状用 Pydantic 而不是 YAML**：YAML 没有元组，`["str", "说明"]` 会被解析成列表，
于是模型把标量返回成单元素列表（实测 `verdict=['rework']`、`assessment=[...]`），
`counts_quoted` 变成空字典。

验证装置（可复跑）：

```bash
cd loop
.venv/bin/python spikes/probe_provider.py        # 端点连通 + 最小请求
LOOP_LLM_MODE=live .venv/bin/python spikes/verify_live_nodes.py   # 5 个语义节点逐个 live
LOOP_LLM_MODE=live .venv/bin/python spikes/verify_live_n10.py     # N10 分桶分类 live（Host 抽数+模型分类）
.venv/bin/python -m pytest -q                    # 55 项，离线（替身）
```

## 6 drill 夹具

`kb/runs/RUN-20261015-120626/**`（**只读**）。选它是因为一个目录同时覆盖：
双计数分歧（口径一 1687 / 口径二 `UVM_ERROR=0`）、死任务、印记三向一致、
闸门拒绝、篡改检测、staging 残留 —— 而真实全跑不能作为交互开发循环。

drill 与 real 的差别**只在节点数据来源**，运行目录两者都是 `kb/runs/<run_id>`
（硬约束：`kb/tools/gate.py` 经 `kb_lib.run_dir` 唯一口径解析路径，无环境变量可覆盖）。

drill 运行目录带 `.loop_drill` 标记，测试据此清理**自己创建的**目录，绝不触碰归档。

**drill 情景**：`happy`（拷夹具全跑日志）/ `dead_job`（`kill -9 $$`，无 rc ⇒ 必须判死）/
`cancel`（`sleep 120`，从界面取消）。

---

## 7 已验证什么

`tests/` 38 项 + 一次真实 HTTP 走查。关键断言：

- 口径一与 `grep -c '\*E'` **独立对账一致**；两套口径并列、`both_zero=false` 时**不得判绿**；
- 观测印记三向一致（印记行 / by-id 计数 / 地址与值）逐项通过；
- 全链路 N0→N16 三道闸门，`gate_history` 每道**恰好一次**；
- 作业运行期间执行处于 **interrupt**（`is_waiting()`），换 `RunManager` 从快照恢复后
  **重新附着到同一作业**；
- 死任务与取消**都走失败**，且都**释放单槽**；
- 非 human actor、非法枚举、I4 阻断三类拒绝**不消耗中断**，闸门仍可用；
- N16 在真实 `kb/baselines/` 上 **rc=3 且零副作用**（v0 与目录清单不变）；
- 冻结见证：完整 drill 运行前后 `TESTLIB/`、`kb/baselines/v0/`、`doc/AGENTS.md`、
  `kb/tools/gate.py` 的**内容 md5 清单逐行不变**（不按 mtime 判）。

## 8 界面不做的事

- 不判绿/判红（一切 `passed` / `can` / `blockers` 由服务端算）。
- 不编辑 `TESTLIB/`（v1 写权仍在作者角色 + 沙箱）。
- 不改基线、不改冲突清单。
- 只有两个写动作：**提交闸门决策**、**取消作业**。
