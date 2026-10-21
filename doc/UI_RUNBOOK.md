# 人工跑通手册：用 Web UI 走一遍 N0–N16

> **这是什么**：给**人**用的操作手册 —— 从启动服务、配置一次运行，到三道人工闸门怎么点、
> 点了会发生什么、怎么判断结果、失败了怎么查。
> **这不是契约**：节点语义/闸门枚举/红线以 [`spec/CHANGE_IMPACT_LOOP_SPEC.md`](spec/CHANGE_IMPACT_LOOP_SPEC.md)、
> [`spec/LOOP_ORCHESTRATION_SPEC.md`](spec/LOOP_ORCHESTRATION_SPEC.md)、
> [`spec/ENV_PLUGIN_SPEC.md`](spec/ENV_PLUGIN_SPEC.md) 为准；界面投影契约见
> [`spec/WEB_UI_SPEC.md`](spec/WEB_UI_SPEC.md)。本手册与契约冲突时，**以契约为准并回来修本手册**
> （下一条列出的、已确认落后的 spec 段落除外）。
>
> **对应实现**：`loop/web/`（运营台 v1）、`loop/services/api.py`、`loop/workflows/main_flow.py`、
> `kb/tools/gate.py`。本机数据状态见 [`STATUS.md`](STATUS.md)（数字唯一来源）。
>
> **一处已知的 spec 落后**：`spec/WEB_UI_SPEC.md` §4.1/§13 仍写 v1 把 `waiting_job/waiting_slot`
> 归并为 `waiting_gate`，§6.2 的示例数字也还是旧值；实现已按 I18 分成六态（`run.sh` 起的服务
> 与本文 §4.1 一致）。以**实现 + 本手册**为准，spec 待 owner 更新；不要据此认为实现错了。
>
> **本手册的验证方式**（2026-10-20）：在 `workspaces/simenv-tcs9620-64ch-sandbox`（可写副本、
> `LOOP_LLM_MODE=standin`）上实际起了服务，并按界面发出的**同一组 HTTP 请求**走了三次闸门，
> 实际做了「拒绝→改选」、「N9 作业取消」、「服务重启后恢复」、「N16 拒绝」与「晋升 API 拒绝」；
> 复核记录见 §14。**本次验证自己建的 5 条 run 已删除**；沙箱里仍保留历史 e2e/demo run
> （其中 `RUN-20261019-164836` 等带脚本占位 `human:accept` 的 `human_signed=true` 账本），
> 那些**不是人工签署证据**，也不属于本次验证，见 §14 末尾说明。

---

## 0 先搞清楚三件事（不然一定会误会界面）

### 0.1 什么算「跑通一遍」

完整闭环是 **N0→N16 + 三道人工闸门**。在当前数据状态下，一轮的正常终点是：

```
N16 = refused（rc=3，零副作用），run.status = finished
can.judge_pass = false，can.promote = false   # 当前数据状态下的值
```

这**不是失败**，而是设计的诚实收敛：I3（口径一 1687≠0）与 I4（72 条冲突 blocks_release）
都需要人先拍板（材料在 `<WORKSPACE_ROOT>/adjudication/`）。**把 N16 说成"晋升成功"才是错的。**
`real` 模式同理：N9 真实全跑尚未验收，详见 [`STATUS.md`](STATUS.md) §2。

### 0.2 界面能写什么、不能写什么

| 动作 | 界面入口 | 权威落点 |
|---|---|---|
| 新建运行 | 配置视图「确认并启动」 | `POST /api/runs`；run 目录 + 执行 |
| 闸门决策 | 执行视图右列闸门卡 / 闸门视图 | `kb/tools/gate.py` → `gates.json` + `gates.sha256` |
| 取消作业 | 执行视图顶部「取消作业」（仅作业 running 时可用） | Host 作业看护 → 显式 failed |

**界面不做**：判绿/判红、编辑用例、改基线/冲突清单、手抄枚举。
**晋升不在 v1 界面上**：只能调 `POST /api/runs/{run_id}/promote`（见 §7.4，当前预期被拒）。

### 0.3 你是「human actor」，名字要自己写

闸门表单里的 actor 默认是 `human:`，**请补成 `human:你的名字`**（例如 `human:chenjunming`）。
服务端只校验「以 `human` 开头」，`: ` 后为空也签得下去 —— 但那是匿名签署，审计上等于说不清谁批的。
**不要填别人名字，也不要让模型/脚本代签**（I6）。

### 0.4 单机、单用户、单槽

- 服务只绑 `127.0.0.1`，**无鉴权**。远程访问一律 SSH 隧道，不要把 8099 暴露到网络。
- `uvs.setup` 是环境根下全局单文件 ⇒ **同一环境禁止并发**。开两个 run 不会并行，
  第二个会显示「排队等单槽」；开两个服务进程共享 `loop/state` 更会互相污染。
- 时间字段是唯一允许的非确定性。要在同一秒重复建 run，用「高级 → 时间注入」换一个 `now`。

### 0.5 最短路径（先跑通，再看细节）

```bash
# ① 起服务（沙箱 + 离线替身；本机 ENV_ROOT 只读时用这个）
cd /home/work/chenjunming/change-impact-loop
LOOP_WORKSPACE="$PWD/workspaces/simenv-tcs9620-64ch-sandbox" \
LOOP_LLM_MODE=standin LOOP_PORT=8099 bash loop/remote/serve.sh

# ② 浏览器打开 http://127.0.0.1:8099/
```

1. **① 配置**：基线选 `v0` → 「浏览…」选环境仓根 → 「校验」通过 → 模式 `drill`、场景 `happy` →
   「确认并启动」。
2. **G1**（通常已自动进 ③ 闸门）：选「差异确认」，actor 写 `human:你的名字`，
   理由写「已逐条核对 N2 未决条目」→ 提交。
3. **G2**：选「接受报告」→ 提交。
4. **G3**：选「仅里程碑」→ 提交（选「立即全量回归」会被 I4 拒，这是练习拒绝的机会）。
5. 看到 `已结束` + N16 `refused` = 这一轮走完；账本在
   `workspaces/simenv-tcs9620-64ch-sandbox/runs/<RUN_ID>/gates.json`。

每一步的预期现象、坑与排障见 §6 与 §10；**第一次不要用 real**。

---

## 1 开跑前的准备

### 1.1 三个根（先确认，再启动）

| 根 | 含义 | 本机取值（默认） |
|---|---|---|
| `TOOL_ROOT` | 本软件仓（自锚定） | `/home/work/chenjunming/change-impact-loop` |
| `ENV_ROOT` | 被守卫的环境仓（插件） | `/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES` |
| `WORKSPACE_ROOT` | 该环境的**数据根**（index/conflicts/baselines/runs） | 默认 = `ENV_ROOT/kb`；可用 `$LOOP_WORKSPACE` 覆盖 |

解析优先级与 fail-closed 规则见 [`spec/ENV_PLUGIN_SPEC.md`](spec/ENV_PLUGIN_SPEC.md) §1。
**界面里看根**：顶栏健康胶囊 + 配置视图「本环境插件面」卡片 + 左栏底部（`TOOL_ROOT / 数据根 / 模型`）。

### 1.2 选一种运行档位

| 档位 | 适用 | 命令（在软件仓根执行） | 数据写在哪 |
|---|---|---|---|
| **A. 沙箱（第一次强烈推荐）** | `ENV_ROOT` 只读、或只想练手 | `LOOP_LLM_MODE=standin bash loop/remote/serve.sh --sandbox` | `workspaces/simenv-tcs9620-64ch-sandbox/` |
| **B. 正式** | `ENV_ROOT` 可写、要跑 `real` | `bash loop/remote/serve.sh` | `ENV_ROOT/kb/` |
| **C. 强制离线模型** | 断网/不想等模型 | `LOOP_LLM_MODE=standin LOOP_WORKSPACE=… bash loop/remote/serve.sh` | 同上 |

> **本机（DSH 会话）现状**：`ENV_ROOT` 被挂为**只读**（`touch` 会报 Read-only file system），
> 所以档位 B 在本会话里**能看不能写**：服务能起、基线能列，但一启动 run 就会因为
> 建不了 `runs/<RUN_ID>/` 而 500。请用 **A**。
>
> 沙箱数据已经存在（`workspaces/simenv-tcs9620-64ch-sandbox/`，含 `baselines/v0` 与 drill 夹具）。
> 若目录被清掉，先跑一次 `bash loop/remote/seed-sandbox-workspace.sh`（复制、不动权威数据）。

**档位 A 的完整启动命令**（手工版，便于看清环境变量）：

```bash
cd /home/work/chenjunming/change-impact-loop
LOOP_WORKSPACE="$PWD/workspaces/simenv-tcs9620-64ch-sandbox" \
LOOP_LLM_MODE=standin \
LOOP_PORT=8099 \
bash loop/remote/serve.sh
```

`serve.sh` 会打印监听地址、工作区、环境根和 Windows 侧隧道命令；前台运行，`Ctrl+C` 停止。

### 1.3 预检（30 秒，能挡掉一半的"为什么按钮是灰的"）

```bash
cd /home/work/chenjunming/change-impact-loop
# 若无 loop/.venv：先按 loop/README.md §2 建环境（Python 3.11 + requirements.txt）

# 1) 三个根与插件/数据面（不受 LOOP_WORKSPACE 覆盖时是默认数据根）
loop/.venv/bin/python - <<'PY'
import sys, os
sys.path.insert(0, "loop")
from host import paths as P
print("TOOL_ROOT     =", P.TOOL_ROOT)
print("ENV_ROOT      =", P.ENV_ROOT)
print("WORKSPACE_ROOT=", P.WORKSPACE_ROOT)
print("plugin_missing   =", P.missing_plugin_parts())
print("workspace_missing=", P.missing_workspace_parts())
for name in ("RTL", "TB", "PKG", "TESTLIB"):
    print(f"  {name:8s} readable={os.access(P.ENV_ROOT/name, os.R_OK)}")
print("SIMLIB_RUN writable =", os.access(P.ENV_ROOT/"SIMLIB_RUN", os.W_OK))
PY

# 2) 端口是否被占（有输出就说明 8099 已被别人用）
ss -ltn 2>/dev/null | grep 8099 || echo "8099 free"

# 3) 服务起来后：健康 + 基线
curl -s http://127.0.0.1:8099/api/health | head -c 400; echo
curl -s http://127.0.0.1:8099/api/baselines
```

`/api/health` 里要重点看：`plugin_missing=[]`、`workspace_missing=[]`、`llm.available`。
`llm.available=false` 时 `llm.reason` 会说明原因（常见：显式 `standin`、无凭据）。

### 1.4 打开页面

- 本机：<http://127.0.0.1:8099/>
- Windows 远程：服务器跑 `bash loop/remote/serve.sh`，Windows 跑
  `loop\remote\connect-loop.bat`（或 `connect-loop.ps1`），浏览器打开 `http://127.0.0.1:8099/`。
  详见 [`../loop/remote/README.md`](../loop/remote/README.md)。
- 旧界面入口：右上角「旧界面」→ `legacy.html`（保留一个迭代，功能可能落后于 v1）。
- **别和 DSH 自己的 Web GUI 搞混**：DSH Web（例如 `127.0.0.1:3083`）是会话界面；
  本手册说的是 `loop/` 起的**变更影响闭环运营台**（默认 `8099`）。

**进程寿命提醒**：在 DSH 会话里用 `nohup … &` 起的服务会随会话/父进程被回收（实测约 1 小时后
SIGTERM）。要常驻请在**服务器自己的登录 shell**里起，或用 `loop/remote/README.md` 里的
systemd 用户服务。

### 1.5 启动前最后三问

1. **数据根对不对？** 沙箱还是正式？左栏「数据根」必须和你打算写入的位置一致。
2. **上一个服务停了吗？** 同一端口只能一个；同一 `loop/state` 也只能一个服务。
3. **要不要模型 live？** 默认按 `loop/SETTINGS.yaml` + 宿主凭据解析；`standin` 更快、可复现，
   但**不代表模型判断**（尤其 N11 不会做真实成链判断）。

---

## 2 界面地图（先认路，再动手）

```
顶栏：品牌 · 环境胶囊 · 服务地址 · 健康检查 · 版本标记 · 「旧界面」
左栏：＋新建运行 ｜ 运行记录列表（run_id / mode / 状态·当前节点 / 更新时间）｜ 底部三根与模型
右区：① 配置   ② 执行   ③ 闸门      （右上角视图切换）
```

| 区域 | 你要看什么 | 权威性 |
|---|---|---|
| 顶栏环境胶囊 | `env_id`、`插件面齐全/缺 N 项`、`数据缺 N 项` | 来自 `/api/health`，只读 |
| 左栏运行列表 | 每条 run 的状态、模式、当前节点、最近更新 | 来自各 run 目录的 `view.json` 投影（不是现场重新执行） |
| ① 配置 | 基线 / 项目目录 / 模式 / 校验 / 启动 | 校验是只读探测，启动是写动作 |
| ② 执行 | 四段流程、agent 卡、双口径、阻断项、长任务、事件流 | 全部是投影；判据在服务端 |
| ③ 闸门 | 闸门材料 + 决策选项 + actor/理由 + 提交 | 提交会写 `gates.json`，是唯一业务写动作 |

**轮询**：执行/闸门视图约 1.5 s 刷一次；页面在后台时降为 10 s，切回立即刷新。
断连时顶部出现红色横幅并保留最后成功时间；恢复后自动消失。

> 左栏「运行记录」读的是**每个 run 目录里的 `view.json`**（以及 `loop/state/runs/*/view.json`）。
> 手工从别处拷进来、没有 `view.json` 的历史 run **不会**出现在列表里；反过来说，
> 列表里的状态是"最后一次投影"，不是重新执行的结果。

---

## 3 配置视图：建这次运行（① 配置）

### 3.1 步骤 1：选择基线版本

- 下拉框自动列出 `GET /api/baselines` 的版本；默认选中第一个 `valid=true` 的版本。
- 每个版本下方显示：`created_at`、`parent`、用例数、RTL 快照大小、`manifest 有效/缺失`。
- 「浏览…」打开目录浏览器（只列基线版本，`valid=false` 的置灰）；「刷新」重新拉列表。
- **通过条件**：必须选一个 `valid=true` 的版本。
- 本机沙箱预期：`v0`，162 用例，`rtl_snapshot_bytes=2570240`，`manifest 有效`。

若列表为空：看 `/api/baselines` 是否报错；沙箱是否缺 `baselines/v0`；数据根是否指错（§10）。
下拉只列有效版本，所以正常操作不会选到坏基线；**绕过界面**直接调 API 传不存在的版本时，
HTTP 层不会拦（契约缺口）：drill 会把不存在的名字当 `parent` 标签照跑（N0/N1 不校验），
real 才由 N1 显式失败 —— 不要这么做。

### 3.2 步骤 2：选择要修订的项目目录（= `ENV_ROOT`）

- 输入框只读，只能「浏览…」选择或由当前进程环境预填；选完会自动触发一次「校验」。
- 目录浏览器的根：注册环境的 path / 父 / 祖父目录、`<WORKSPACE_ROOT>/baselines`、
  `loop/SETTINGS.yaml` 的 `loop.ui.browse_roots`、`$LOOP_BROWSE_ROOTS`。越界由服务端 403。
- **操作**：点「浏览…」→ 进到环境仓根（也就是同时能看到 `RTL`、`TB`、`PKG`、`TESTLIB`
  与 `uvs.setup` 的那一层）→ 点底部「选择此目录」。

校验通过要同时满足（界面逐项显示）：

| 检查项 | 期望 | 不满足时 |
|---|---|---|
| `ok` | `true` | 看 `plugin_missing` |
| `plugin_missing` | `[]` | 缺 `RTL`、`TB`、`PKG`、`TESTLIB` 或 `uvs.setup` |
| `matches_current_process` | `true` | 选到了别的环境 ⇒ 必须重启服务（`400` 的成因） |
| 路径是否仍是刚校验的路径 | 是 | 改了目录要重新校验（否则按钮保持禁用） |

另有两个**提示性**字段（不拦启动，但要看）：

- `writable.frozen` / `writable.sim_workdir`：显示为「冻结面 可写/只读 · SIMLIB_RUN 可写/不可写」。
- `warnings[]`：如缺 `run_local.sh`（real 不可用）、缺 `doc/_run_artifacts/uvs.setup.orig`（中止自愈不可用）。

> **本机沙箱预期**：`ok=true`、`registered=true`、`RTL 1467 文件`、`TESTLIB 162 用例`、
> 「与当前进程环境一致」；但 `SIMLIB_RUN 不可写`。
> ⇒ **drill 可以跑**（drill 不写真机仿真目录）；**real 会在 N7/N9 失败**。别拿这个档位跑 real。

### 3.3 步骤 3：运行选项

| 控件 | 取值 | 说明 |
|---|---|---|
| 模式 | `drill`（默认）/ `real` | drill 用冻结夹具；real 走真机编译/全跑 |
| 场景 | `happy` / `dead_job` / `cancel` | 只对 drill 有意义；`dead_job` 无 rc 必须判死，`cancel` 用来练取消；选 `real` 时下拉被禁用（沿用上次值，实际不生效） |
| 高级 → 时间注入 | 留空 = 服务器时间；或 ISO 时间 | 注入后整轮用该时间，**run_id 也由它决定**（`RUN-YYYYMMDD-HHMMSS`） |

选 `real` 会显示警告条：**「real 链路尚未闭合（N1/N6/N7/N9/N15）；允许启动，但结果不得当作真机结论。」**
这句话是旧结论：real 的 N0→N8 已在真实环境副本上跑通（见
[`evidence/REAL_RUN_SCN_RTL_0D04_20261020.md`](evidence/REAL_RUN_SCN_RTL_0D04_20261020.md)），
但 **N9 真实全跑仍未验收**。因此：real 可以起，但**不要把结果当"真机已验收"**。

### 3.4 确认条：启动

- 左侧汇总：`基线 / 环境 / 模式`；右侧提示随状态变化：
  依次为：`请选择有效基线`、`请选择项目目录`、`请先点「校验」`、`校验通过，可启动`、
  `real 模式：结果不得当作真机结论`。
- 点「确认并启动」→ `POST /api/runs`。按钮变「启动中…」并防双击。
  ⚠ **前端所有请求 15 s 超时**（`app.js` 的 AbortController）。drill/standin 很快不会触发；
  但 **live 模型下建 run 常常 >15 s**：页面会显示「启动失败：请求超时（15 s）」，而服务端
  可能已经建好 run 并继续跑。**超时 ≠ 没建成** —— 先刷新左栏/`GET /api/runs` 确认，
  不要连点第二次（会多建一条 run）。
- 成功后 toast「已创建运行：RUN-…」，界面自动进入：
  - 若服务端已停在闸门（drill 很快）⇒ 直接进 **③ 闸门**；
  - 否则进 **② 执行**。
- 失败时按服务端错误展示（不吞）。常见：

| HTTP | 原文要点 | 处置 |
|---|---|---|
| 400 | `project 必须等于当前进程 ENV_ROOT；跨环境需以该环境重启服务。` | 用 `LOOP_ENV_ROOT` 重启服务后再选 |
| 400 | `now 不是可解析的 ISO 时间` | 改成合法的 ISO 时间（如 `2026-10-20T13:00:00`） |
| 409 | `运行目录 RUN-… 已存在；run_id 必须唯一` | 换一个注入时间；**权威 run 绝不删**，只有沙箱演示 run 可按 §11 清 |
| 500 | 无结构化错误（多为数据根不可写） | 换沙箱/可写 `WORKSPACE_ROOT` |

---

## 4 执行视图：这一轮在干什么（② 执行）

### 4.1 顶部状态条

`run_id` · 状态胶囊 · mode · baseline · project · 已用时长 · 更新时间 · 「刷新」·「取消作业」。

| 状态 | 含义 | 你应该做什么 |
|---|---|---|
| `执行中`（running） | 节点正在跑 | 等；看四段进度与事件流 |
| `等待人工`（waiting_gate） | 执行已停放，等闸门决策 | 去 ③ 闸门（或右列闸门卡） |
| `等待作业`（waiting_job） | N9/N15 长任务在跑，图已停放 | 等；可点「取消作业」；可安全重启 |
| `排队等单槽`（waiting_slot） | 别的作业占着单槽 | 等队首释放；不要重复启动 |
| `已结束`（finished） | 走到 HALT / N16，执行已关闭 | 判读终点（§7） |
| `失败`（failed） | 显式失败（顶部红框给出 `error`） | 按 error 排查；**不能续跑**，重开一轮 |

`v1` 的细分状态已修（I18），但**不要**根据状态胶囊猜业务结论：判据只认 `gates.json` +
服务端 `blockers/can`。

### 4.2 四段流程

| 段 | 节点 | 何时自动展开 |
|---|---|---|
| 摄取 | N0 基线 · N1 摄取 · N2 diff · N3 总结 · N4 闸门1 | 闸门 1 等待时 |
| 修订 | N5 影响 · N6 修订 · N7 编译 · N8 复核 | N5–N8 进行时 |
| 验证 | N9 全跑 · N10 对账 · N11 守护 · N12 报告 | N9–N12 进行时 |
| 决策 | N13 闸门2 · N14 闸门3 · N15 回归 · N16 晋升 | 闸门 2/3 等待时 |

- 段头显示状态：`完成 / 进行中 / 等待人工 / 失败 / 待开始 / n/m`；同一时刻只展开一段，点段头切换。
- 节点 chip 显示 `节点号 + 名称 + owner`（Host / analyst / author / checker / guardian / reporter / 人 / TriggerFlow）。
- 闸门节点用菱形标记；等待中为琥珀色。
- `node_history` 里不在四段映射中的内部节点（如 `N3_request`、`N6_model`、`N9_submit`、`HALT`）
  会列在四段下方的「未纳入四段展示的节点」区 —— **这是如实展示，不是异常**。
- **注意**：节点 chip 的 ✓ 只表示该节点执行结束（`node_finished`），**不表示业务通过**。
  例如 N9 的 `status=fail`（口径一 ≠ 0）、N16 的 `refused` 在流程条上都可能显示为已完成；
  结论看顶部状态、右列 blocker、`gates.json`。

### 4.3 Agent 工作状态（5 张角色卡 + Host 一行）

| 卡片 | 节点 | 本手册里你会看到 |
|---|---|---|
| `simenv-analyst` | N3 | 差异语义摘要（standin 时 `mode=standin`） |
| `simenv-author` | N6 | 用例修订/补充 |
| `simenv-checker` | N8、N10 | 静态复核 / 结果对账 |
| `simenv-guardian` | N11 | 证据守护（成链判断） |
| `simenv-reporter` | N12 | 评估报告 |
| Host（固定一行） | N0/N1/N2/N5/N7/N9/N15/N16 | 确定性步骤 / 长任务看护 |

卡片字段：状态、最近动作、耗时、摘要、`mode`（live/standin）、证据入口。
**证据入口只做存在性探测**（`GET …/evidence/exists`）：存在弹路径/字节数，缺失显示「证据缺失（E-2）」，
不会在页面里打开文件内容。要看正文，去 run 目录（§7.3）。
卡片底部固定标注「投影，非权威；判据以服务端 blockers / gates.json 为准」。

### 4.4 右列

1. **闸门卡**（仅 pending 时出现）：闸门名/轮次、精简材料、决策单选、actor、理由、提交。
   它和 ③ 闸门视图**共用同一份草稿**，在哪边填都一样。
2. **双口径计数**：口径一 / 口径二**并列同权、不换算**；两者都归零才可判绿。
   还没有 N9 证据时显示「无全跑证据：两套口径均无法取数（I3 / E-2）」。
3. **阻断项**：按 `blocker → defect → info` 排序，显示 `code + title + message` 和最多 3 条 refs；
   前端不过滤。**没有阻断项 ≠ 判绿**（以服务端 `can` 与 `gates.json` 为准）。
4. **长任务**：`job_id / 节点·用例 / phase / rc / 已用 / ETA`，日志尾部折叠（最多 12 行，只读）。
5. **事件流**：折叠；只显示白名单 `kind`；`seq` 递增；最近 60 条倒序。

---

## 5 过三道闸门（本手册的核心）

### 5.0 通用操作（三道门都一样）

1. 等到状态 `等待人工`，进 **③ 闸门**（或直接看执行视图右列闸门卡）。
2. 看「闸门材料」：闸门/节点/轮次、冲突快照、返工轮次、硬阻断、缺陷、权威枚举、
   **服务端决策选项**（几个）、双口径、`invariant_note`。
3. 选一个决策（单选；选项与 `requires_reason` 全部由服务端下发，界面不手抄）。
4. actor 补上你的名字（`human:xxx`）。**每道闸门的草稿是独立的**，换门后 actor 会重置成
   `human:`，每次都要重新补名字。
5. 理由：标了「必须填写理由」的**一定**要写；没标的也建议写（会作为 `note` 进 `gates.json`）。
6. 点「提交闸门决策」。按钮提交中禁用；**重复点击不会发第二次请求**。
7. 成功：toast「闸门决策已提交：`<GATE>` · `<decision>`」→ 自动回执行视图。
   服务端是**同步**把执行推进到下一个停放点才返回的，所以：
   - standin/drill 通常 < 1 s；
   - live 模型节点可能 >15 s。**注意前端每个请求 15 s 超时**（`app.js`）：
     页面会报「闸门提交被拒：请求超时（15 s）」，但**签名可能已经落账、执行可能已在推进**。
     **超时 ≠ 未提交**：先刷新 `GET /api/runs/{run_id}` 看 `status`/`pending_interrupt` 和
     `gates.json`；若已消费，再次提交只会得到 400「当前没有待处理中断」。
8. 被拒：表单里出现红色错误 + 「服务端 blockers（原样）」。**闸门保持待决策、中断没有被消耗**，
   改选或补齐后再提交即可。

**提交前的服务端拒绝顺序**（理解它就不会瞎试）：
① 闸门/枚举/actor 静态校验 → ② 业务前置（I1/I2/I4/A2）→ ③ 确认本门确有中断 → ④ 才写账本 → ⑤ 恢复执行。
所以被拒**不会**留下孤儿签名，也不会把执行打成 failed。

> 一个真实例外：如果恢复阶段本身失败（模型异常、死任务在 continue 同一次调用里被判死等），
> HTTP 可能返回 **200**，但随后 `GET /api/runs/{id}` 的 `status` 变成 `failed`、`error` 有值
> （内部 `execution_failed=true` 字段当前未透传到 HTTP 响应）。
> 这时**不要再点提交**：先看顶部 error 与事件流，按 §8 处理。

### 5.1 闸门 1（N4）：差异确认

**材料看什么**

- **闸门材料里直接显示「N2 差异清单」**（2026-10-20 起）：标题行给出「共 N 条 · 未决 M 条」，
  未决条目单独标琥珀色并在顶部列 chip；每条显示 `entry_id`、`kind`、`change`、`segment/offset/lines`、
  `unresolved`（若有）与 `evidence` 全文。**先逐条看完再决定**，不要空口点「差异确认」。
  运行视图右列的闸门卡里有同名折叠块（`N2 差异清单 · N 条 · 未决 M 条`），点开即可看全。
- 交叉核对（可选，终端）：投影与 run 目录里的 `n2_diff.json` 是同一份数据，命令如下：

  ```bash
  RUN=RUN-20261020-xxxxxx
  # 方式 1：读投影（pending 存在时）
  curl -s "http://127.0.0.1:8099/api/runs/$RUN" | python3 -c '
  import json,sys
  p=json.load(sys.stdin)["pending_interrupt"]["payload"]
  d=p.get("difference_items") or {}
  print(json.dumps({"entries": d.get("entries"), "unresolved": p.get("unresolved_entries")},
                   ensure_ascii=False, indent=2))'
  # 方式 2：直接读 run 目录（更完整）
  cat "<WORKSPACE_ROOT>/runs/$RUN/n2_diff.json"
  ```
- 差异条目字段：`entry_id`、`kind`、`change`、`unresolved`、`evidence`、行号/offset；
  可读摘要见 N3 的 `n3_digest.md`（agent 卡「simenv-analyst」→ 证据，或直接看文件）。
- 未决条目：`unresolved` 非空的条目（drill 夹具里 `RTL/SRC/imports/SRC/reg/sys_reg.v` 是非 UTF-8，
  会被标成历史夹具未决；drill 夹具的这个条目 `entry_id` 可能为 null，见 §5.1 脚本说明）。
- 阻断项：此时通常还有 `I3_EVIDENCE_MISSING`、`I4_CONFLICTS_UNCLEARED`（它们不拦 G1）。

**决策**

| 决策 | 后果 | 适用 |
|---|---|---|
| `confirmed` 差异确认 | 进入 N5→N8 修订 | 你逐条看过了，同意进入修订 |
| `ignored` 忽略（须给理由） | 去 HALT，本轮终止 | 认为这轮变更不值得修 |
| `disputed` 有疑义（须理由） | 去 HALT，转人工裁决 | 差异本身有争议 |

**坑 1（drill）**：存在未决条目时，`confirmed` 虽然**选项上没标"必须理由"**，但服务端强制要求
非空 reason（作为「已逐条核对」的证明）——所以**先按上面的命令看过条目**，再写「已逐条核对」，
否则就是空口 attestation。不写会得到 403：

> `I1：N2 有未决差异条目。drill 模式须给出非空 reason（作为「已逐条核对」的证明），或提交覆盖全部条目的 entry_decisions。`

**坑 2（real）**：当 G1 材料的 `entry_decisions_required=true`（存在未决条目）时，
`confirmed` 必须提交覆盖**全部**条目的 `entry_decisions`；而 **v1 界面没有逐条处置的输入控件**。
这时 UI 提交会被 403 拒绝，只能走 API（下面是可复制脚本）：

```bash
cd /home/work/chenjunming/change-impact-loop
RUN=RUN-20261020-xxxxxx            # 换成你的 run_id
ACTOR='human:你的名字'
loop/.venv/bin/python - "$RUN" "$ACTOR" <<'PY'
import json, sys, urllib.request, urllib.error
run, actor = sys.argv[1], sys.argv[2]
base = "http://127.0.0.1:8099"
view = json.load(urllib.request.urlopen(f"{base}/api/runs/{run}"))
pending = view.get("pending_interrupt") or {}
mat = pending.get("payload") or {}
raw = (mat.get("difference_items") or {}).get("entries", [])
entries = [e.get("entry_id") for e in raw if e.get("entry_id")]
if not entries:
    raise SystemExit("difference_items.entries 为空：改从 <RUN_DIR>/n2_diff.json 的 "
                     "diffs[].entry_id 取全部条目后再提交。")
body = {
    "decision": "confirmed",
    "actor": actor,
    "reason": "已逐条核对 N2 全部差异条目",
    "entry_decisions": {eid: {"decision": "confirmed"} for eid in entries},
}
req = urllib.request.Request(
    f"{base}/api/runs/{run}/gates/G1_diff_confirm/decision",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    print(json.dumps(json.load(urllib.request.urlopen(req)), ensure_ascii=False, indent=2))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8"))
PY
```

要点：`entry_decisions` 的 key 必须覆盖 `difference_items.entries` 的**全部** `entry_id`；
`ignored/disputed` 条目的 value 要带 `reason`；只要有条目判 `disputed`，整门决策必须是 `disputed`。
提交后界面会在下一次轮询看到结果，**不需要重启**。

> **不要为了过闸门把有疑义的条目一律写 `confirmed`** —— 逐条处置正是闸门要你做的判断；
> 上面的脚本只是把你无法在 v1 界面里表达的逐条结果送进去。有疑义就改成 `disputed` 并给理由，
> 后果是本轮转人工裁决（HALT），这是正确行为。
>
> 脚本已过滤 `entry_id` 为空的条目（drill 夹具的未决 `rtl_file` 条目就是 null）：这类条目
> 无法用 `entry_decisions` 逐条表达，real 模式遇到它应先在 N2 产物里补 identity，或整门
> `disputed` 转人工 —— **不要**把 null 当 key 送进去（服务端会报「含未知条目」）。

> **v1 限制登记**：界面缺 `entry_decisions` 编辑是已知缺口（见 §12），不是服务端拒绝你。

### 5.2 闸门 2（N13）：报告验收

**材料看什么**

- `n12_report.md`（报告本体）、`reconcile.md` / `n10_reconcile.md`（N10 对账，随轮次/夹具而异）、
  `check_C.md`；N9 的聚合结果在 execution state（`n9_result`）里，**不是 run 目录的落盘文件**，
  证据看 `evidence/` 下的全跑日志。
  UI 材料里有 `counts`、`conflicts`、`rework`、`case_states`、`defects`、`hard_block`。
- 双口径：本机 drill 夹具固定为 **口径一 = 1687**（`*E` 文本行数）、
  **口径二 = {UVM_ERROR:0, UVM_FATAL:0, UVM_WARNING:0, UVM_INFO:34933}**。
  `1687 ≠ 0` ⇒ 即便口径二为 0 **也不得判绿**（I3；根因是 TB 侧走 `uvm_info` 而非 `uvm_error`，
  属既有缺陷，不是本轮引入）。
- 用例态：`accept` 前检查**本轮**是否有「已修订待验」。
- 返工计数：`n6_n8_cycles` 与 `g2_rework_cycles` **分账**（各有上限 3）；界面「返工轮次」
  只渲染 `n6_n8_cycles`，`g2_rework_cycles` 要看 `GET /api/runs/{id}.rework` 或 `rework_cycles.json`。

**决策**

| 决策 | 前置 | 后果 |
|---|---|---|
| `accept` 接受报告 | 本轮无「已修订待验」 | 进 N14（闸门 3） |
| `rework` 返工（须理由） | —— | 回到 N6，`g2_rework_cycles + 1` |

**坑**：`accept` 被拒时原文类似：

> `I2：本轮仍有 N 个用例「已修订待验」（[....]）⇒ 不得接受报告（I2：待验不得称跑通）。`

处置：要么选 `rework` 且写清返工要求，要么先让本轮用例态归零（正常流程里由 N8/N10 写入）。
drill 下 `case_states.json` 可能不存在（N10 明确跳过台账，事件 `drill_ledger_skipped`），
这不算 `pending_own`，`accept` 可以通过 —— 但报告里会如实保留 I3/I4 阻断。

**接受报告 ≠ 判绿**：G2 只表示"报告本身可接受"，不解除 I3/I4；`gates.json` 里也只是
`G2_report_accept: accept`。

### 5.3 闸门 3（N14）：回归决策

**材料看什么**

- 冲突快照：`total / open / blocks_release`，本机 = **72 / 72 / 72**（`conflicts.json` 自检一致）。
- 硬阻断：`I4_CONFLICTS_UNCLEARED`（若选 full/subset 会被拒）。
- 报告与用例态、返工轮次（`gates.json` 只记决策，不记 `can`；`can` 在 `GET /api/runs/{id}`）。

**决策与后果**

| 决策 | 前置 | 后果 |
|---|---|---|
| `full_now` 立即全量回归 | **冲突必须清零** | N15 全量 → N16 |
| `subset_only` 仅受影响子集回归 | **冲突必须清零** | N15 子集 → N16 |
| `milestone_only` 仅里程碑 | 无 I4 前置 | N15（按 G3 选择取集合）→ N16 |
| `defer` 暂缓 | 无 | 去 **HALT**：本轮显式终止，不跑 N15/N16 |

**本机一定会遇到的拒绝**（实测原文）：

```json
{"detail": {"error": "I4：冲突未清零（72 项 blocks_release）⇒ 不得选 full_now；闸门保持待决策，可改选 milestone_only / defer。",
            "blockers": [ ...I3_KOUTOU1_NONZERO, I4_CONFLICTS_UNCLEARED... ],
            "note": "被拒 = 权威（kb/tools/gate.py 或 I4 前置）拒绝，不是界面错误。"}}
```

HTTP 403，**闸门仍是 pending**（`gates.json` 中 G3 仍 `pending`、`history_len=0`）。
改选 `milestone_only`（先让流程走完）或 `defer`（显式停）即可。

**推荐第一次演练选 `milestone_only`**：能走到 N15→N16，看到完整终点形态；
`defer` 看不到 N15/N16，但同样是合法终点。选哪个都请写理由（审计要能回答"为什么这么定"）。

### 5.4 提交之后

| 决策 | 你接下来会看到 |
|---|---|
| G1 confirmed | 修订段亮起，N5→N6→N7→N8，然后 N9 作业（drill 约 0.2 s）、N10、N11、N12，最后停在 G2 |
| G1 ignored/disputed | 决策段 → HALT，run `finished` |
| G2 accept | N14 闸门 3 |
| G2 rework | 回 N6（可能重复 N6–N12）；看 `rework` 卡与事件流 |
| G3 milestone_only/subset/full | N15_select → N15 → N16；run `finished` |
| G3 defer | HALT；run `finished` |

drill 下 N15 是**显式 no-op**：节点 detail 里 `simulated=true`，不是真跑仿真。real 下 N15 才是
真实回归（单槽串行，耗时长）。

---

## 6 一次完整演练（按这个顺序点）

> 前置：档位 A（沙箱）+ `LOOP_LLM_MODE=standin`；「高级 → 时间注入」建议留空，
> 或填一个唯一时间（例如 `2026-10-20T13:00:00`）。下面括号里是**预期值**，用于自查。

| # | 操作 | 预期现象 / 判据 |
|---|---|---|
| 1 | 打开 `http://127.0.0.1:8099/` | 顶栏环境胶囊显示 `simenv-tcs9620-64ch`，健康「插件面齐全」；左栏底部数据根 = 沙箱路径 |
| 2 | ① 配置 → 基线 | 默认 `v0`，meta 显示 162 用例、约 2.45 MB、`manifest 有效` |
| 3 | 点「浏览…」选项目目录 → 选环境仓根 → 「选择此目录」 | 自动校验；出现「校验通过」「与当前进程环境一致」「插件面齐全」；`SIMLIB_RUN 不可写`（drill 无妨） |
| 4 | 模式 `drill`、场景 `happy` → 「确认并启动」 | toast「已创建运行：RUN-…」；通常**直接进 ③ 闸门**（drill 很快） |
| 5 | 看 ③ 闸门材料里的「N2 差异清单」 | 标题 `N2 差异清单 · 2 条 · 未决 1 条`；未决 chip 指向 `RTL/SRC/imports/SRC/reg/sys_reg.v`；两条各自展开 `entry_id/kind/change/evidence`；未决那条标琥珀色并给出未决原因 |
| 6 | 选「差异确认」，actor `human:你的名字`，理由写「已逐条核对 N2 未决条目」（确认你真的看过了）→ 提交 | toast 成功；回执行视图；修订/验证段走完；停在 `G2_report_accept`（轮次 `0-0`） |
| 7 | 看双口径 / 阻断项 | 口径一 `1687`、口径二 `UVM_ERROR=0 …`；阻断项含 `I3_KOUTOU1_NONZERO`、`I4_CONFLICTS_UNCLEARED`、`I1_UNRESOLVED_ENTRIES`（warning） |
| 8 | 点右上角 **③ 闸门**（或右列闸门卡），G2 选「接受报告」，理由写「接受报告本身；I3/I4 阻断保留」→ 提交 | toast 成功；决策段亮起；停在 `G3_regression_decision` |
| 9 | （练习拒绝）G3 选「立即全量回归」→ 提交 | 表单红框：`I4：冲突未清零（72 项 blocks_release）…`；**闸门仍是等待人工**，可改选 |
| 10 | G3 改选「仅里程碑」，写理由 → 提交 | toast 成功；N15_select（count=5）→ N15（simulated）→ N16（`refused`）；run 变 `已结束` |
| 11 | 看终点 | 无 pending；`node_history` 末项 N16 `refused`；notes 可能有 `snapshot 失败…tasks are active`（见 §10）与 `执行已关闭…` |
| 12 | 旁证（可选，终端） | `curl -s .../api/runs/RUN-... \| python3 -m json.tool \| head -80`，确认 `status=finished`、`can.judge_pass=false`、`can.promote=false` |

**时间预期**：standin drill 全链路约 **5–15 s**（模型节点是确定性替身）。
默认 live 模型会慢很多（N3 实测约 16 s，已经**超过前端 15 s 超时**；N6/N8/N10/N11/N12
各自数十秒到分钟级），而且 **N11 可能判证据不成链并触发 N6 返工**（最多 3 轮后升级到 G2）
——这是设计行为，不是界面故障。**第一次走流程请用 standin**；用 live 时遇到「请求超时」
按 §5.0 第 7 步先查状态再决定，不要连点。

### 6.1 real 与 drill 的差别（UI 操作一样，预期不同）

| 项 | drill | real |
|---|---|---|
| 前提 | 可读环境 + 可写 `WORKSPACE_ROOT` | **`ENV_ROOT` 可写**（`SIMLIB_RUN`、`uvs.setup` 自愈）+ 可写数据根 + 空单槽 |
| 模型 | 可用 standin | **必须 live**：N3/N8/N10/N11/N12 缺 live 即 fail-closed；N6 的 standin 只产出显式空，不会冒充真实修订 |
| G1 | 未决条目可用 reason attestation | 可能要求 `entry_decisions` ⇒ 用 §5.1 API 脚本 |
| N7 | drill 不真编译 | 真编译（代码注释写 ≈2 s，real 未实测；仍走单槽） |
| N9 | 夹具作业瞬间完成（约 0.2 s） | 真实全跑，**单用例约 19 min 起**；修订后可能更长 |
| N15 | 显式 no-op（`simulated=true`） | 真实串行回归（耗时长） |
| 终点 | N16 `refused`（缺 case_states 等） | N16 `refused`（I3/I4/台账等原因不同） |
| 结论口径 | 只验证机制 | 结果**仍不得当作已验收**（N9 全跑未验收） |

real 模式下**不要**因为 N9 跑得久就反复刷新/重启：执行已停放，重启会重新附着；
真要停就点「取消作业」，它会显式 `failed` 并释放单槽（见 §8）。

> **N9 是"提交即停放"，不会卡住闸门/建 run 的请求**：真正让 `POST /api/runs` 或闸门提交
> 超过前端 15 s 的是 **live 模型节点**（N3/N6/N8/N10/N11/N12），不是 N9 作业本身。

---

## 7 终点判读：什么算正常结束

### 7.1 四种终点

| 终点 | 触发 | run.status | 关键证据 |
|---|---|---|---|
| **N16 refused** | G3 = full/subset/milestone，走到 N16 | `finished` | N16 detail `rc=3` + `stderr_tail`；不要再把 `can.promote` 当 N16 的同义词（它只看 I4/I7/I3_EVIDENCE_MISSING） |
| **HALT** | G1 = ignored/disputed，或 G3 = defer | `finished` | 事件 `warning/halted`；节点 HALT `halted` |
| **failed** | 死任务、取消、闸门恢复失败、节点异常 | `failed` + `error` | 顶部红框原文；事件 `node_failed` / `dead_job` |
| **仍在等待** | 闸门/作业/单槽 | `waiting_*` | 服务重启后可恢复（§9） |

### 7.2 权威在哪

| 事实 | 权威文件 | 说明 |
|---|---|---|
| 三道闸门签没签、谁签的 | `<RUN_DIR>/gates.json` + `<RUN_DIR>/gates.sha256` | `human_signed` 只在 `actor_kind=human` 时为真；sha256 是锚 |
| 本轮做了什么 | `<RUN_DIR>/view.json`、`loop/state/events/<RUN>.jsonl` | 投影/事件流，**不是**权威 |
| 业务判据 | 服务端 `blockers` / `can` | 界面不持有「已通过」 |
| 产物 | `<RUN_DIR>/` 下的 `n*.json/md`、`evidence/` | 见 §7.3；界面不直接显示 run 目录 |

复核闸门账本（只读）：

```bash
RUN=RUN-20261020-xxxxxx
cd /home/work/chenjunming/change-impact-loop

# 沙箱档位（kb 工具按 LOOP_WORKSPACE 解析数据根）
WS="$PWD/workspaces/simenv-tcs9620-64ch-sandbox"
LOOP_WORKSPACE="$WS" loop/.venv/bin/python kb/tools/gate.py show --run "$RUN"
cat "$WS/runs/$RUN/gates.sha256"
ls -la "$WS/runs/$RUN"

# 正式档位：去掉 LOOP_WORKSPACE 覆盖，WS 换成 ENV_ROOT/kb
```

### 7.3 run 目录里有什么（按闸门看）

> **run 目录怎么找**：界面只显示 `RUN_ID`，不显示绝对路径。路径 = `<WORKSPACE_ROOT>/runs/<RUN_ID>`；
> 也可以在终端用 `curl -s http://127.0.0.1:8099/api/runs/<RUN_ID> | python3 -c 'import sys,json;print(json.load(sys.stdin)["run_dir"])'` 取。

```
<WORKSPACE_ROOT>/runs/<RUN_ID>/
├── gates.json / gates.sha256     # 权威：三闸门决策 + 锚
├── view.json                     # 最后一次投影（左栏状态来源）
├── n1_manifest_new.json          # N1 摄取
├── n2_diff.json / n2_diff.md     # N2 差异（G1 材料）
├── n3_digest.md                  # N3 摘要（G1 材料）
├── n5_impact.json / .md          # N5 影响
├── sandbox/TESTLIB/*.sv          # N6 修订的沙箱副本（不碰真 TESTLIB）
├── check_C.md / N6_author_note.md# N8 / N6 产物
├── reconcile.md / n10_reconcile.md # N10 对账（N9 结果只在 execution state）
├── n12_report.md                 # N12 报告（G2 材料）
├── rework_cycles.json            # 返工计数快照
├── case_states.json              # 用例态台账（如有）
├── evidence/                     # 编译/运行证据（drill 带 DRILL FIXTURE 标记）
└── baseline_drill/               # N16 dry-run 的 staging（拒绝后可能残留，见 §12）
```

> 上面是**可能存在**的产物清单；drill 夹具与 real 的落盘不完全相同
> （例如 drill 的 N10 写 `n10_reconcile.md`，历史夹具里则是 `reconcile.md`；
> drill 下 `case_states.json` 可能不存在）。以 run 目录实际内容为准。

**证据缺失（E-2）**：agent 卡点「证据」若提示缺失，先看对应文件是否真的存在；
drill 的 N9 证据是 **DRILL FIXTURE**，不能当真实运行证据。

### 7.4 晋升（不在 UI 上）

```bash
RUN=RUN-20261020-xxxxxx
curl -s -X POST "http://127.0.0.1:8099/api/runs/$RUN/promote" \
  -H 'Content-Type: application/json' \
  -d '{"actor":"human:你的名字","reason":"G3 已签署，申请晋升"}'
```

- `actor` 必须 `human` 开头，且与 **G3 签署者逐字一致**。
- G3 只能是 `full_now` / `subset_only` / `milestone_only`（`defer` 不允许晋升）。
- 只允许在 G3 已签、I3/I4/用例态/I7 前置都满足时成功；否则 **403**，且拒绝发生在任何写盘之前。
  只有真正调用到 `n16_promote.py`（rc=0/3）才会在 run 目录落 `promote_result.json`（只增不改）；
  actor 前缀不对、G3 签署者不一致、本轮已成功过等**前置拒绝不落文件**。
- 本机现状（drill 且 case_states 缺失）预期原文：
  `晋升被权威拒绝（rc=3）：[FAIL] 用例态台账不存在 …（I2：缺台账不得晋升）`
- 真实晋升由 `kb/tools/n16_promote.py --promote` 原子完成（API 不写 `baselines/`、不伪造闸门）。

---

## 8 长任务、取消、失败

### 8.1 N9（全跑）在界面上的形态

- N9 拆成「提交 → 停放」：提交后 run 变 `等待作业`，执行处于 interrupt（**可安全重启**）。
- 右列「长任务」显示 `job_id`、phase、rc、已用、ETA（可能显示"未知"；API 里有
  basis/confidence，但**界面只渲染 eta_human 与 note**）、日志尾部。完整日志在
  `loop/state/jobs/<JOB_ID>.log`。
- 作业还在 running 时，顶部「取消作业」可用；完成后自动禁用。
- 恢复后**以日志为权威重新取数**，不信任 resume 载荷里的数字。

### 8.2 练习取消（用 `cancel` 场景）

1. 新建运行：`drill` + 场景 `cancel` + 唯一 `now`。
2. G1 选 confirmed 并写理由 → 提交。
3. run 变「等待作业」，长任务 phase=`running`（夹具睡眠作业）。
4. 点「取消作业」→ 浏览器确认框 → 服务端返回 `{"ok":true,...}`。
5. 预期：run 变 `failed`，顶部红框：

   > `投递失败：RuntimeError: 作业 JOB-… 被取消 ⇒ 本轮无法满足 I3，按失败处理，不得继续。`

   作业 phase=`cancelled`，单槽释放；**流程条上 N9 可能仍显示进行中**（事件流没有 `node_failed`），
   以顶部 `failed` + error 为准。

### 8.3 失败后的纪律

- `failed` 是显式收敛：**不要**手工改 `gates.json`/`view.json` 让它"看起来通过"。
- 失败轮不能续跑；要重试请**新开一轮**（换 `now`，避免 409）。
- 死任务（`dead_job` 场景）与取消一样按失败处理并释放单槽；不会把槽永久占住。
- 如果失败发生在"闸门已签署但恢复失败"，账本里那次签名视为未生效；先看 `error`、
  再决定是否重开。必要时把经过写进 evidence/记录，不要静默重签。

---

## 9 重启与恢复（可以放心重启）

### 9.1 重启会发生什么

- 服务启动时 `async_restore_all()`：重新判定作业命运 + 从 `loop/state/recovery/<RUN>.json`
  快照恢复执行。
- 停在闸门的 run：恢复后仍停在**同一个闸门**，`pending_interrupt` 不变，你可以继续决策。
- 停在作业的 run：会重新附着到仍在跑的作业；未投递的中断会补投递（换新的 request id，
  幂等，不是重复执行）；死作业按失败收敛。
- 恢复报告在 `/api/health` 的 `restore_report`：`restored` / `failed` / `jobs` 分桶。
- 前提：快照是**干净停车**的（约 0.2 s 节拍落盘）。若重启落在两次落盘之间，
  可能 `failed` 并说明原因（如 `snapshot_behind_ledger`）——这是**刻意**的：
  宁可红，也不自动重放一个已经签过的决定。此时按 §8.3 重开一轮。

### 9.2 操作步骤

```bash
# 停（前台 Ctrl+C；后台）
pkill -f "uvicorn services.api:app"

# 起（与上次相同的数据根/模式！）
cd /home/work/chenjunming/change-impact-loop
LOOP_WORKSPACE="$PWD/workspaces/simenv-tcs9620-64ch-sandbox" \
LOOP_LLM_MODE=standin LOOP_PORT=8099 bash loop/remote/serve.sh

# 验
curl -s http://127.0.0.1:8099/api/health | python3 -c \
  'import sys,json;d=json.load(sys.stdin);print(d["restore_report"])'
```

重启后左栏会重新列出 `view.json` 可读的 run；点进去看状态是否还是你离开时的闸门。

### 9.3 不要做的事

- **不要**删 `loop/state/recovery/<RUN>.json` 来"清掉卡住的 run"——那会让它下次恢复失败。
- **不要**手改 `gates.json`（权威 + 锚；手改既不生效也毁证据）。
- **不要**把 `loop/state` 从一个工作区/环境挪到另一个（会恢复出错误的作业语义）。
- `loop/state` 是**可删**的运行时状态；删之前确认没有在跑的 run，并接受"投影与恢复能力丢失"。

---

## 10 排障表（症状 → 原因 → 处置）

| 症状 | 最可能原因 | 处置 |
|---|---|---|
| 浏览器打不开 / 连接被拒 | 服务没起；端口不是 8099；远程隧道没建 | `ss -ltn \| grep 8099`；看启动终端（nohup/systemd 时看 `loop/.logs/serve.log`）；重连隧道 |
| 顶栏「环境未就绪」/ 健康失败 | `ENV_ROOT` 解析错误、健康端点异常 | `curl /api/health`；按 `plugin_missing` 修 |
| 顶栏「插件缺 N 项」 | 选的目录不是完整环境仓 | 用注册表里的环境根；缺 `uvs.setup`/`RTL` 等 |
| 顶栏「数据缺 N 项」 | `WORKSPACE_ROOT` 指错 | 检查 `LOOP_WORKSPACE` 或 `environments.json` |
| 基线列表为空 | 数据根没有 `baselines/*/manifest.json`；`/api/baselines` 报错 | 看沙箱是否完整；重跑 `seed-sandbox-workspace.sh` |
| 基线 `valid=false` | manifest 缺失/损坏 | 不要选；先修数据或换版本 |
| hint 显示 `请先点「校验」` / 按钮灰 | 没校验、校验失败、或目录变过 | 重新点「校验」；看 hint 原文 |
| 「需以该环境重启服务」 | 选的项目目录 ≠ 进程 `ENV_ROOT` | 用 `LOOP_ENV_ROOT` 重启后再选；不要静默换根 |
| `SIMLIB_RUN 不可写` | 环境仓只读 | drill 可继续；real 必须换可写环境 |
| 启动 400 `project 必须等于…` | 同上 | 同上 |
| 启动 409 `运行目录…已存在` | 固定 `now` 重复建 run | 换注入时间；或按 §11 清理同一 run |
| 启动 500 | 数据根不可写（建 run 目录失败） | 用沙箱/可写 `WORKSPACE_ROOT` |
| 闸门提交 403 含 `I1…entry_decisions` | real 有未决条目、UI 没逐条输入 | 用 §5.1 的 API 脚本 |
| 闸门提交 403 `I2…已修订待验` | G2 accept 前置不满足 | 选 rework（写理由）或先归零用例态 |
| 闸门提交 403 `I4…blocks_release` | G3 选了 full/subset 且冲突未清零 | 改选 milestone_only / defer |
| 闸门提交 403 `I6…human` | actor 没以 human 开头 | 改成 `human:你的名字` |
| 提交后 run 变 failed（HTTP 200） | 闸门已签、恢复阶段失败 | 看 error；按 §8.3 重开，不要重复提交 |
| N16 `refused` | 前置不满足（drill：缺 case_states；real：I3/I4/台账等） | 这是正常终点；看 N16 detail `rc/stderr_tail` |
| 状态一直 `等待作业` | 作业确实在跑 | 看长任务 phase/日志；必要时取消 |
| 状态一直 `running` 不动 | 可能在 live 模型长调用；或恢复/投递异常 | 看事件流最后一条与 `loop/state/jobs/*.log`；刷新；重启可恢复 |
| notes 出现 `snapshot 失败…tasks are active` | 某次快照恰逢执行非空闲，未落盘 | 本轮不受影响；若紧接着重启，恢复可能退回更早快照或显式失败 —— 重开一轮即可 |
| 页面无数据但服务正常 | 左栏列表来自 `view.json`，不是目录扫描 | 确认 run 目录里有 `view.json`；或新建一条 |
| 模型不可用 / 全是 standin | `LOOP_LLM_MODE=standin` 或无凭据 | 看 `/api/health.llm.reason`；real 必须有 live provider |
| real 在 N7/N9 失败 | `SIMLIB_RUN` 不可写/缺 `uvs.setup`/单槽/作业错误 | 看 job 日志与 error；换可写环境重试 |

---

## 11 清理与复跑

### 11.1 清掉自己刚建的演示 run（仅沙箱）

```bash
WS=/home/work/chenjunming/change-impact-loop/workspaces/simenv-tcs9620-64ch-sandbox
RUN=RUN-20261020-xxxxxx

# 1) 先确认它是什么（服务在线时）
curl -s "http://127.0.0.1:8099/api/runs/$RUN" | head -c 300; echo

# 2) ⚠ 停服务：waiting_* 的 run 会被 0.2 s 快照节拍重建 view.json / recovery，服务运行时删不掉
pkill -f "uvicorn services.api:app" || true

# 3) 确认绝对路径无误后再删（只动沙箱）
test -d "$WS/runs/$RUN" && echo "将删除 $WS/runs/$RUN"
rm -rf "$WS/runs/$RUN"
rm -f /home/work/chenjunming/change-impact-loop/loop/state/recovery/"$RUN".json \
      /home/work/chenjunming/change-impact-loop/loop/state/events/"$RUN".jsonl

# 4) 再起服务
```

删除 run 目录会**连 `gates.json` 一起删掉** —— 对这个 run 而言它就是权威账本，删了就没有了。
所以只删**你自己在沙箱里刚建的演示 run**；`ENV_ROOT/kb/runs/` 下的任何 run（尤其是冻结见证）
与冻结基线**绝对不要删**。

> 为什么必须先停服务：快照 ticker 每约 0.2 s 对**非 finished/failed** 的 run 调一次
> `async_sync`，会写快照并 `_persist` 重建 `view.json`。服务运行时删 waiting_gate/job/slot
> 的 run，目录会在 0.2 s 内复活成"只有投影、没有 `gates.json`"的残骸，下次重启按失败处理。

### 11.2 清运行时状态（可选）

`loop/state/` 是"可删"的槽/队列/事件/快照目录。只有在**没有在跑 run**、且接受
"丢失投影与恢复能力"时才清：

```bash
cd /home/work/chenjunming/change-impact-loop
pkill -f "uvicorn services.api:app" || true
mv loop/state loop/state.bak-$(date +%Y%m%d-%H%M%S)   # 先改名保留，确认无事再删
```

### 11.3 复跑

- 直接再点「＋ 新建运行」；run_id 取当前时间，一般不会撞。
- 若用固定 `now` 演练，记得每次换值；否则 409（**权威 run 只换时间，不删**）。
- 重新跑之前确认上一轮已 `finished`/`failed`，单槽未被占（`loop/state/queue.json` 为空）。

---

## 12 v1 已知限制（不得当成已具备）

| # | 限制 | 影响 | 现状/出处 |
|---|---|---|---|
| 1 | **UI 没有 `entry_decisions` 编辑** | real 模式下 G1 有未决条目时无法在 UI 完成 | 用 §5.1 API 脚本；缺口登记 |
| 1b | ~~UI 不展示逐条差异/未决计数~~ **已修（2026-10-20）** | 闸门材料已逐条渲染 `difference_items`：未决高亮 + evidence 全文，运行视图闸门卡可折叠查看 | 见 §5.1；回归 `test_web_smoke.py::test_gate_material_script_renders_n2_diff_entries` |
| 2 | **UI 没有晋升按钮** | N16/I8 只能走 `POST …/promote` | §7.4；当前被 I3/I4/台账阻断 |
| 3 | N11 在 standin 下固定判 `intact` | standin 不会暴露证据链问题；live 才做真实成链判断 | 卡片 `mode` 可见；要真实守护结论请用 live |
| 4 | 模型可为 standin | standin 结论**不代表模型判断** | 卡片 `mode` 字段可见；real 模式下关键节点 fail-closed |
| 5 | real 全跑未验收；N15 drill 为 no-op | 不要把 drill 的 N15 当真实回归 | [`STATUS.md`](STATUS.md) §2/§3 |
| 6 | I3 双口径、I4 冲突清零需人拍板 | N16/晋升必然被拒，直到裁决 | 材料在 `<WORKSPACE_ROOT>/adjudication/` |
| 7 | actor 只校验 `human` 前缀 | `human:` 空名字也能签（审计上等于匿名） | 请规范填写 |
| 8 | 快照竞态窗口未完全消除 | 极端情况下重启会显式失败 | §9.1；重开一轮 |
| 9 | 单槽 `holder_alive` 语义待改 | 极少数情况下锁判活看进程而非作业 | 见 [`../loop/README.md`](../loop/README.md) §5 |
| 10 | 无鉴权、单机单用户 | 绝不能暴露到网络 | 只绑 `127.0.0.1` + SSH 隧道 |
| 11 | `baseline_drill/` 拒绝后可能残留 | **界面当前没有专门告警**（残留告警只覆盖 `staged`/`.staging-v1`）；需自己看 run 目录 | 已知 F-N16-04；不要手改成晋升产物 |

---

## 13 快速检查清单（打印/贴屏用）

**启动**
- [ ] 数据根 = 我打算写入的目录（沙箱 or `ENV_ROOT/kb`）
- [ ] `/api/health`：`plugin_missing=[]`、`workspace_missing=[]`
- [ ] `/api/baselines` 有 `valid=true` 的版本
- [ ] 端口 8099 只有一个服务；没有第二个 run 在跑

**每道闸门**
- [ ] 状态 = 等待人工；材料/选项来自服务端
- [ ] actor = `human:我的名字`；理由写清"为什么"
- [ ] 被拒时：读原文 → 改选/补理由 → 再提交（不重复乱点）
- [ ] 提交成功后：确认 `gates.json` 里 `human_signed=true`、`decision` 正确

**终点**
- [ ] `status` 是 `finished` 或 `failed`（不是永远 running）
- [ ] 正常 happy 路径三道门各恰好一次（`gate_history` 长度 3；G2 rework 会更多，HALT 路径更少）
- [ ] 走完整链时 N16 是 `refused` 并能说出原因；同时看 `can.judge_pass/promote`（两者口径不同，
      不能互相代替；当前数据状态下两者都是 false）
- [ ] 证据在 `runs/<RUN>/evidence/`；drill 证据带 DRILL FIXTURE 标记

---

## 14 本手册的验证记录（2026-10-20）

在沙箱 + `LOOP_LLM_MODE=standin` 上实际执行，命令块与输出摘要：

| 验证项 | 做法 | 结果 |
|---|---|---|
| 服务/健康 | `serve.sh`（sandbox）→ `GET /api/health` | `ok=true`、`plugin_missing=[]`、`workspace_missing=[]`、`llm.available=false`（standin 原因可见） |
| 基线/环境校验 | `GET /api/baselines`、`GET /api/env/check` | `v0` valid、162 用例、2,570,240 B；`ok=true`、`matches_current_process=true`、`writable.sim_workdir=false` |
| 全链路 | 建 drill run（`now=2026-10-20T12:30:00`）→ G1 confirmed + reason → G2 accept → G3 milestone_only | 停在 G1/G2/G3 各一次；最终 `finished`，N15 `simulated=true`，N16 `refused`（rc=3，case_states 缺失）；`can={judge_pass:false,promote:false}` |
| 拒绝不消耗中断 | G3 提交 `full_now` | HTTP 403 + I4 blockers；G3 仍 `pending`、`history_len=0`；改选后成功 |
| 差异清单渲染 | 无头 Chrome 打开闸门视图（CDP 读 DOM） | `#gateMaterial .diff-item=2`、`.diff-item.unresolved=1`；文本含两条 `entry_id`、未决原因与 evidence；运行视图闸门卡折叠块 `#gateCardBody .diff-item=2` |
| 拒绝原文核对 | G1 不写 reason / actor 非 human | 分别得到 403「I1：N2 有未决差异条目…drill 模式须给出非空 reason…」与 403「I6：闸门决策只接受 human actor…」；G1 仍 pending、账本未变 |
| 重启恢复 | 停在 G1 时 kill 服务 → 同参数重启 | `restore_report.restored=[RUN-…]`；run 仍 `waiting_gate`，pending 仍是该 G1 |
| 取消作业 | `cancel` 场景 → G1 confirmed → 取消 running 作业 | run `failed`，error 含「作业被取消 ⇒ 本轮无法满足 I3」；job `cancelled` |
| 晋升拒绝 | `POST …/promote` | HTTP 403，`n16_promote rc=3`，`baselines/` 仍只有 `v0`（零副作用） |
| 清理 | 停服务后删除**本次验证的 5 条** run 目录/事件/快照 | 这 5 条已消失；左栏仍显示沙箱里原有的历史 e2e/demo run（预期）；未触碰权威 run 与冻结基线 |

> 说明一：本次验证建的 run 已删除，actor 用的是操作者名字占位；不构成任何"已人工签署"的证据。
> 真实签署必须由本人操作。
>
> 说明二（不要把历史脚本签名当人工签署）：沙箱 `runs/` 里仍有早先 e2e/演示留下的 run。
> 例如 `RUN-20261019-164836` 的 `actor=human:accept`、`RUN-20261019-160206` 的 `actor=human:demo`，
> 都是**脚本占位**；`RUN-20261016-1114xx` 也带 `human_signed=true`（自动化测试用操作者名字提交）。
> `human_signed=true` 只代表"当时填了 human 前缀"，**不是真人签署**。要看本轮是否可发布，
> 以本轮 `gates.json` + 冲突/I3 状态为准，不能拿这些历史件当依据。
>
> 说明三：`loop/state/{events,recovery}` 里可能还有更早的孤儿投影（run 目录已不在，如
> `RUN-20261020-1120xx`）。它们不是本手册产生的；重启时看到这些 run 走 failed 属预期，
> 不要为了"消除报错"去手改状态。

---

## 附录 A：API 速查（排障/旁证用）

| 端点 | 用途 |
|---|---|
| `GET /api/health` | 三根、插件/数据缺件、模型状态、恢复报告 |
| `GET /api/baselines` | 基线列表（版本/父链/用例数/有效性） |
| `GET /api/env/check?path=` | 只读环境校验（ok/plugin_missing/counts/writable/matches_current_process） |
| `GET /api/fs/dirs?path=` | 目录浏览（allowlist，越界 403） |
| `GET /api/runs` | 运行列表（来自 `view.json` 投影） |
| `POST /api/runs` | 建运行（唯一建运行入口） |
| `GET /api/runs/{run_id}` | 完整投影：四段/节点历史/agents/blockers/counts/gate_options/pending |
| `GET /api/runs/{run_id}/events?since_seq=` | 事件流（白名单外仍可读，但界面只显示白名单） |
| `POST /api/runs/{run_id}/gates/{gate_id}/decision` | 闸门决策（唯一业务写动作） |
| `POST /api/runs/{run_id}/jobs/{job_id}/cancel` | 取消作业 |
| `GET /api/runs/{run_id}/evidence/exists?ref=` | 证据存在性探测（界面按钮用） |
| `POST /api/runs/{run_id}/promote` | 人触发 N16 真实晋升（v1 无界面入口） |

投影字段要点（`GET /api/runs/{id}`）：`status`、`error`、`notes`、`stage_map`、`node_history`、
`pending_interrupt.payload`（含 `difference_items`、`conflicts`、`rework`、`decision_options`、
`entry_decisions_required`、`unresolved_entries`）、`gate_options`、`blockers`、`counts`、
`agents`、`can`、`evidence`、`job`、`gates_authority`。

## 附录 B：相关契约与代码索引

| 想知道 | 看 |
|---|---|
| N0–N16 / I1–I8 / 三闸门语义 | [`spec/CHANGE_IMPACT_LOOP_SPEC.md`](spec/CHANGE_IMPACT_LOOP_SPEC.md) |
| 生命周期/长任务/准入/恢复/投影 | [`spec/LOOP_ORCHESTRATION_SPEC.md`](spec/LOOP_ORCHESTRATION_SPEC.md) |
| 三根解析、插件契约 | [`spec/ENV_PLUGIN_SPEC.md`](spec/ENV_PLUGIN_SPEC.md) |
| 界面契约与验收判据 A1–A8 | [`spec/WEB_UI_SPEC.md`](spec/WEB_UI_SPEC.md) |
| 界面实现 | [`../loop/web/index.html`](../loop/web/index.html)、[`../loop/web/app.js`](../loop/web/app.js) |
| HTTP 边界 | [`../loop/services/api.py`](../loop/services/api.py) |
| 拓扑与恢复 | [`../loop/workflows/main_flow.py`](../loop/workflows/main_flow.py) |
| 闸门前置判定（I1/I2/I4/A2） | [`../loop/workflows/chunks/gates.py`](../loop/workflows/chunks/gates.py) |
| 闸门权威（签名/锚/枚举） | [`../kb/tools/gate.py`](../kb/tools/gate.py)、[`../kb/tools/kb_lib.py`](../kb/tools/kb_lib.py) |
| 远程访问/隧道 | [`../loop/remote/README.md`](../loop/remote/README.md) |
| 现状数字 | [`STATUS.md`](STATUS.md) |
