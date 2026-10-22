# SPEC-REV-01 实现验收证据（2026-10-22）

> **这是什么**：用户验收 [`SPEC-REV-01`](../spec/SPEC-REV-01-20261022.md) 后，按其 R2–R6 实施并实测的**冻结证据**。
> **不是什么**：不是独立终验，不是四道门全绿声明，不是内网/真机验收。
> **被测对象**：本仓工作树（`doc/spec/**` 的 SPEC-REV-01 与实现同批；提交见同日 `feat(spec-rev-01)` 提交）。
> **执行者**：Lead（同一会话内集成并复核；**没有独立验证者**）。

---

## 1 范围

| 编号 | 规格要求 | 落点 |
|---|---|---|
| R2 | G1 逐条材料可判（before/after、diff_hunk、encoding、N3/Host 留痕入口） | `loop/services/contracts.py`、`loop/workflows/chunks/gates.py`、`loop/workflows/context.py`（drill 复制 Host 留痕） |
| R3 | 非 UTF-8 差异可读 + 解码口径唯一 | `kb/tools/kb_lib.py`、`kb/tools/n2_diff.py`、`kb/tools/n5_impact.py`、`kb/tools/_selftest_n2_encoding.py` |
| R4 | **全部节点**可点详情（22 节点：N0–N16 + `N6_apply`/`N9_submit`/`N15_select`/`N15_submit`/`HALT`） | `loop/services/node_view.py`、`loop/services/api.py`、4 个 `chunks/*.py`、`loop/web/node-detail.js`、`loop/web/app.js` |
| R5 | S0 来源徽标（`s0_record_id` 可空；drill 标"未经 S0 派生"） | `loop/workflows/main_flow.py`、`loop/services/api.py`、`loop/services/contracts.py`、`loop/web/app.js` |
| §6.7 | `refs` 只给 run 目录内路径；目录外只计数 | `loop/services/node_view.py`（`refs_omitted`） |

不变量：不新增业务写动作；闸门权威仍只 `gates.json`；不判绿、不替人签署；历史 run 不回填。

---

## 2 命令与原始结果

### 2.1 软件层单测（官方入口，可写影子数据根）

```bash
cd /home/work/chenjunming/change-impact-loop
bash loop/spikes/run_software_checks.sh --ignore=tests/browser
```

```
523 passed, 3 deselected, 1 warning in 95.80s (0:01:35)
```

### 2.2 浏览器用例（系统 Chrome；playwright 自带 chromium 未安装）

```bash
cd /home/work/chenjunming/change-impact-loop/loop
HOME=/tmp/chromehome XDG_CONFIG_HOME=/tmp/chromehome/.config \
XDG_DATA_HOME=/tmp/chromehome/.local/share \
LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome LOOP_LLM_MODE=standin \
.venv/bin/python -m pytest -q tests/browser
```

```
55 passed in 72.79s (0:01:12)
```

（改动前基线 41 passed；本次新增 14 条节点面板/G1 材料用例。）

复跑（节点面板补 `refs_omitted` 显示后）：浏览器 `55 passed in 75.25s`；软件层 `523 passed, 3 deselected in 97.69s`。

### 2.3 新增投影测试（sandbox 数据根）

```
34 passed, 1 warning
```

### 2.4 注册表默认命令的环境限制（如实登记，非代码失败）

```bash
cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
```

```
54 failed, 471 passed, 1 warning, 55 errors in 67.13s
```

分类（逐条核对过）：
- 52 × `OSError: [Errno 30] Read-only file system`：本会话 `WORKSPACE_ROOT` 默认 = `<ENV_ROOT>/kb`，drill 建不了 run 目录；
- 2 × `env_layer` 归档用例（`test_archive_e2.py`）：需可写 `ENV_ROOT/SIMLIB_RUN`；
- 55 × 浏览器 setup error：`Executable doesn't exist … chrome-headless-shell`（未安装 playwright 自带浏览器）。

⇒ 该结果**不能**当作代码回归；可写数据根 + 系统 Chrome 下的真实结果见 2.1/2.2。

### 2.5 kb 自测

```bash
loop/.venv/bin/python kb/tools/_selftest_n2_encoding.py      # PASS 37/37
loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py  # 汇总：PASS=9 FAIL=0
loop/.venv/bin/python kb/tools/_selftest_gate_schema.py      # 汇总：PASS=10 FAIL=0
```

R3 语义：条目带**实际命中 codec** 的 `encoding`（GB18030 优先，实测 `gb18030`；GBK 在其后作为回退）；
N2/N5 的候选集同源 `kb_lib.DECODE_ENCODINGS`，`_selftest_n2_encoding.py` 第 35–37 条断言三者同源同序。

### 2.6 文档门

```bash
python3 doc/audit/check_doc_links.py
```

```
checked=1587 skipped=19615 historical=857 known_missing=10 env_missing=12 missing=0
退出码 0
```

### 2.7 端到端

**未运行**：`loop/spikes/accept_v1_run.sh` 需可写 `ENV_ROOT/SIMLIB_RUN`，本会话 `ENV_ROOT` 只读。
⇒ 四道门中的端到端门**仍未验证**，不得记为通过。

---

## 3 隔离实服务复核（不碰 8099）

```bash
LOOP_STATE_ROOT=$PWD/workspaces/verify-state-18099 \
LOOP_WORKSPACE=$PWD/workspaces/simenv-tcs9620-64ch-sandbox \
LOOP_LLM_MODE=standin LOOP_PORT=18099 \
bash loop/remote/serve.sh --sandbox
```

`/openapi.json` = **17** 条路由（含 `/api/runs/{run_id}/nodes/{node}`；8099 上的旧构建只有 11 条）。

新建 drill run `RUN-20261022-160528`（`mode=drill`、`scenario=happy`、`s0_record_id=null`），停在 G1 后实测：

| 项 | 实测 |
|---|---|
| G1 entries（2 条） | 均带 `before`/`after`；`diff_hunk=null`、`encoding=null`（drill 夹具历史产物，**未回填**） |
| `0x0000#0x0004` | `reset` `2023_0911` → `2026_0708` |
| `sys_reg.v` | md5 `f9d14795…` → `094692d0…` |
| `host_trace` | `exists=true`、`count=3`；M1 `32'h04→32'h0000_0004`（行 539→540，`encoding=gbk`）、M2a/M2b 文档值（行 414/447，`encoding=utf-8`） |
| `n3_digest` | `exists=true` |
| N0/N1/N2/N3 详情 | 均有 `source`+`summary`；N1 摘要含 allfiles 3374 条 / cases 162 / doc 指纹 / commit 可解析 |
| N4（等待签署） | `missing_fields=[summary,source,human_signed]`（未下发即诚实列出） |
| 内部节点/未知节点 | `N9_submit`/`HALT` 可点（未执行）；`N_FUTURE` → `known=false`（200，不是 404） |
| `refs` | 均来自事件顶层；`refs_omitted=0`（本轮引用都在 run 目录内） |

> **未做**：没有替人签任何闸门（I6）。因此下游 N5–N16 的 live 验证只由 `tests/test_node_detail_projection.py`
> 的 drill 全链用例覆盖（断言每个节点 `summary`/`source` 非空），不是人工实签。

---

## 4 边界与未完成项

1. **端到端未跑**（见 2.7）；内网 `real` 链路、S0-real 未涉及。
2. **E1 未修**：N2 把 `rc=3`（`RC_GAP`，明确不产出 `n2_diff.json`）当成功放行 ⇒ 有输入缺口的 N2 可能显示"完成、0 差异"；需单独切片（`node_failed` 或显式 `incomplete`）。
3. **E2 未修**：事件 kind 白名单规格 8 / 服务端 15 / 前端 16，三处不一致；本轮未夹带。
4. **历史 run 不回填**：`RUN-20261022-143532` 等旧 run 缺新字段，面板显示"未下发"；验收不得当缺陷。
5. 8099 仍是旧构建；用新界面需重启服务（或使用隔离实例 18099 的启动方式）。
   **实测到的运行纪律问题**：两个服务进程共享同一 `WORKSPACE_ROOT` 会互相覆盖
   `runs/<id>/view.json`（18099 恢复时把 `RUN-20261022-143532` 标 `failed`，8099 轮询又写回
   `waiting_gate`）。复核实例已停止；重启后请新建运行，旧 run 不建议复用。
6. 浏览器用例依赖系统 Chrome + 可写 HOME（见 2.2 的命令）；不满足时 setup 直接失败，不冒充通过。
7. 本轮由 Lead 一人集成与复核，**无独立验证者**；不声称四道门全绿。

---

## 5 第二轮收口：端到端复跑 / E1 / E2 / S0-rehearsal（同日）

> 覆盖第 4 节中的「端到端未跑」与 E1/E2；S0-rehearsal 为同一规格 R5 的补齐。仍无独立终验。

### 5.1 端到端终验（隔离副本）

```bash
# 工作树一次性副本（清运行时状态），复用一次性 workspace 副本；端口 18097
rsync -a --exclude '.git' --exclude 'loop/.venv' --exclude 'loop/state' \
  --exclude 'loop/.logs' --exclude 'loop/.pytest_cache' --exclude 'workspaces' \
  --exclude '__pycache__' ./ workspaces/verify-e2e2/
rm -rf workspaces/verify-e2e2/loop/.agently
cd workspaces/verify-e2e2/loop
LOOP_WORKSPACE=<verify-e2e-ws> LOOP_LLM_MODE=standin LOOP_PORT=18097 bash spikes/accept_v1_run.sh
```

```
phase 1 rc=0 / phase 2 rc=0 / phase 3 rc=0 / phase 4 rc=0 / phase 4b rc=0 / phase 5 rc=0
=> ALL PASS
断言：117/117（50/27/18/8/8/6）
```

**踩点**：副本若带旧 `.agently/`，首跑 `RecordStoreError: identity state belongs to a different RecordStore`；
清运行时状态后通过。属复制方法，不是产品缺陷。

### 5.2 E1（N2 rc=3）

- 修复：`host_steps.n2_diff` 对 `rc=3`（`RC_GAP`，不产出 `n2_diff.json`）→ `node_failed` + 抛错；`rc=4` 仍失败。
- 回归：`tests/test_fix_real_chain.py::test_n2_rc3_gap_fails_explicitly_and_writes_no_diff`（断言无 `n2_diff.json`、事件为 `node_failed`）。
- 同步：`tests/test_baseline_admission.py::test_n2_uses_selected_baseline` 的 fake rc 3→0（旧口径）。

### 5.3 E2（事件 kind 白名单）

- 唯一权威 `host.progress.ALLOWED_KINDS`（15）；`/api/health.event_kinds` 下发；前端运行时消费、删 `run_failed`；SPEC-02 §9 同步。
- 测试：`test_api.py::test_health_and_static_ui`（`event_kinds == sorted(ALLOWED_KINDS)`）+
  `test_api_ui_contract.py::test_frontend_event_whitelist_matches_server_authority`（解析 app.js 静态兜底表，防漂移）。

### 5.4 S0-rehearsal（SPEC-05 §6.2/§4/§7）

- `POST /api/s0/rehearsal`：只接受可选 `now`；Host 在 `${STATE_DIR}/s0-rehearsal/<UTC 戳>/` 自造小基线，
  派生到同戳 `work/`；记录写 `${STATE_DIR}/s0/`（带 `rehearsal.kind=S0-rehearsal`）。
- 安全：客户端路径参数一律 400；每次新记录/新目录；失败 422 + 记录保留；`ENV_ROOT` 零写入；`ready_for_execution` 恒 false。
- 工作台：S0 视图「运行 S0 演练（临时小基线）」按钮 + 回执（id/status/四项 checks/副本路径）+ 固定免责声明。
- 测试：`tests/test_s0.py` 33 passed；浏览器
  `test_run_sessions.py::test_s0_rehearsal_runs_once_and_shows_four_checks_with_scope_notice`。

### 5.5 最终门禁（本轮工作树）

| 门 | 命令 | 结果 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | `531 passed, 3 deselected, 1 warning in 105.38s` |
| 浏览器 | `pytest -q tests/browser`（系统 Chrome + 可写 HOME） | `56 passed in 76.76s` |
| 端到端 | 见 5.1 | `117/117，ALL PASS` |
| 文档 | `python3 doc/audit/check_doc_links.py` | `checked=1614 … missing=0`，rc=0 |

**仍未关闭**：S0-real（内网真实环境 + 三库冒烟）未跑；`real` 真机链路未跑；8099 仍是旧构建；历史 run 不回填。
**不声称四道门全绿或已合规。**
