# 计划 · 单一 RTL 文件夹一键派生（2026-10-30）

> 状态：**实施中**。规格先行已完成（本轮已改 4 份规格，见 §1）。
> 来源：人 2026-10-30 需求「入口处只传入一个完整的 RTL 代码文件夹，流程照样跑通」（grill-me 21 问已逐条拍板）。
> 归属：Host 派生 = `loop/host/**`；切换 = `loop/host/**` + `loop/services/api.py`；界面 = `loop/web/**`。
> 不触碰：环境仓 `RTL/TB/PKG/TESTLIB`（零写）、`kb/tools/**`（冻结）、冻结基线字节、run 拓扑与三道闸门语义。

## 1 规格（本轮已写，先于代码）

| 文件 | 变更 |
|---|---|
| `doc/spec/S0_ENVIRONMENT_SPEC.md` | 新增 §9（入口/根判定/选择性复制/RTL 替换语义/自动续跑/自动切换/失败语义/验收） |
| `doc/spec/WEB_UI_SPEC.md` | 新增 §13（表单、阶段回执、端口确认、切换后、副本清单、切回、不变量） |
| `doc/spec/LOOP_ORCHESTRATION_SPEC.md` | 新增 §13（run 文档 `env_root`/`env_origin_root`；零必改分流**登记为未决不实现**） |
| `doc/spec/ENV_PLUGIN_SPEC.md` | 新增 §8（派生副本作为 ENV_ROOT、零写、数据根、单槽、原始根记录） |

## 2 已拍板的 21 条决定（摘要，逐条见会话）

1. 输入 = 完整 RTL 文件夹（非单文件）；2. 它是新 RTL 全集，其余资产来自已注册环境派生副本；
3. 1:1 全量替换，按目录名判根（`RTL`/`SRC`，其它拒绝）；4. 摄入范围沿用 `RTL/SRC/imports` + `RTL/RTL_COMMON`；
5. 文档/regmap 默认沿用环境现态并落账；6. 基线沿用现有列表且必须 valid；
7. 在副本上真跑 N0–N16；8. 入口 = 改造现有 S0「派生并校验」表单；9. 选择性复制 + 跳过清单；
10. 端口差异停住等人逐条确认，其余自动续跑；11. 六项准出后自动切换；12. 新子进程接管 + 健康检查 + 失败回退；
13. 数据根 = 副本 `kb/`（自包含）；14. 活跃 run 拒绝派生/切换；15. 失败即停、保留副本与记录、服务活着；
16. 副本每次新建并保留，手动清理；17. 恒以原始根为基线源 + 可切回；
18. 零必改 = G1 分流（**本片未实现**，见 §6）；19. 错目录只告警不拦截；20. 副本不提供 drill；
21. 一轮做全并实测（软件层 + 真实副本，见 §7 环境限制）。

## 3 切片与写权（互不重叠）

| # | 切片 | 落点（唯一写者） | 验收 |
|---|---|---|---|
| T1 | 派生引擎 + `S0Store` 自动入口 | `loop/host/derive.py`（新）、`loop/host/s0.py`、`loop/tests/test_s0_derive.py`（新） | 单测全绿；根判定/复制/跳过/子树核验/告警/记录字段 |
| T2 | 切换状态机 + supervisor + API | `loop/host/env_switch.py`（新）、`loop/host/switch_supervisor.py`（新）、`loop/services/api.py`、`loop/tests/test_env_switch.py`（新）、`loop/tests/test_s0_from_rtl_api.py`（新） | 状态机 pending→active/rollback；活跃 run 拒绝；端点契约；切回 |
| T3 | 界面（S0 一键入口） | `loop/web/s0.js`、`loop/web/index.html`、`loop/web/app.js`（仅预填钩子）、`loop/tests/browser/test_s0_auto_entry.py`（新） | 浏览器门：表单/阶段/切换/预填/窄屏无溢出 |
| T4 | 集成、四道门、真实副本实测、STATUS | Lead（`doc/**`、`doc/STATUS.md`） | §4 门禁全绿或如实登记 |

## 4 冻结接口（T1/T2/T3 并行依据，改动需 Lead 同步）

### T1 `loop/host/derive.py`

```python
RTL_NAME_PREFIX = {"RTL": "RTL", "SRC": "RTL/SRC"}      # 目录名 → 仓库相对前缀
EXCLUDED_ROOTS = ("kb/runs", "loop", "SIMLIB_RUN", ".git", "COV", "WAVE", "LOG", "RUNS")
SKIP_DIR_NAMES = ("__pycache__", ".git", ".svn", ".hg")

def classify_rtl_source(path: Path) -> dict
    # -> {"kind": "RTL"|"SRC", "prefix": "RTL"|"RTL/SRC", "basename": str}；其它名 ValueError（列合法值）
def plan_copy(baseline: Path) -> dict
    # -> {"copied": [rel...], "excluded_roots": [rel...],
    #     "skipped": [{"rel","reason","target"}...]}   # reason ∈ {"symlink", ...}
def manifest_filtered(root: Path, plan: dict) -> dict          # 只走 copied，软链必须已在 skipped
def copy_selected(baseline: Path, work: Path, plan: dict) -> dict   # -> {"copied": int, "skipped": int}
def replace_rtl(work: Path, rtl_source: Path, prefix: str) -> dict  # -> {"prefix","replaced":[rel...]}
def folder_warning(baseline: Path, plan: dict, rtl_source: Path, prefix: str) -> dict
    # -> {"same","added","removed","ratio"}；只统计同前缀文件集，不拦截
```

### T1 `S0Store.prepare_from_rtl`

```python
def prepare_from_rtl(self, payload: dict, *, default_baseline: Path,
                     origin_env_root: Path, target_parent: Path) -> dict
    # payload: rtl_source(必填), baseline?, baseline_version?, work_env?, smoke_case?, now?
    # 记录只增字段：entry="rtl_folder", origin_env_root, rtl_prefix, copy_plan,
    #   folder_warning, smoke_case, auto={"phase": "awaiting_ports"|"ready"|"failed"}
def advance(self, record_id: str, *, smoke_case: str | None = None, now=None) -> dict
    # ports 未 passed ⇒ ValueError（不冒烟）；否则跑一次 smoke → 刷新 checks/ready
```

`get()`/`_refresh_checks()` 合并记录目录下 `env-switch.json`（T2 写，T1 只读投影，字段名 `env_switch`）。

### T2 `loop/host/env_switch.py`

```python
def state_dir() -> Path                                  # <STATE_DIR>/env-switch
def origin_env_root() -> Path | None                     # 持久化原始根（首次记录后不变）
def record_origin(env_root: Path) -> None
def active() -> dict | None                              # {"status":"active"|"rollback", ...}
def pending() -> dict | None
def build_request(*, target_env_root: Path, origin_env_root: Path, record_id: str | None,
                  project: Path, app_dir: Path, host: str, port: int, state_root: Path) -> dict
def spawn_supervisor(request: dict) -> int               # 独立 session，stdout/stderr → 日志文件
```

`switch_supervisor.py`：`python -m host.switch_supervisor --pending <json>`；
轮询 `GET /api/health` 校验 `env_root == target`；失败回退旧根并写 `rollback`。

### T2 API（形状冻结）

```text
POST   /api/s0/from-rtl        {rtl_source, baseline?, baseline_version?, work_env?, smoke_case?, now?}
POST   /api/s0/{id}/advance    {smoke_case?, now?}
POST   /api/s0/{id}/activate   {now?}                  → 202 {"switch": {...pending...}}
GET    /api/env/state          → {env_root, env_id, origin_env_root, switch, baseline_source}
POST   /api/env/switch-back    {}                      → 202 {"switch": {...}}
GET    /api/s0/copies          → {copies:[{id, work_env, exists, bytes, rtl_prefix, status, ready_for_execution}]}
DELETE /api/s0/{id}/copy?confirm=true                  → {deleted: bool, work_env}
```

### T3 界面

- 表单唯一必填 `#s0Rtl`；`#s0Baseline/#s0Version/#s0Work` 收进 `<details class="adv" id="s0Advanced">`，留空走默认；
- 新 DOM：`#s0PhaseFlow`（阶段回执）、`#s0Ports`（端口确认）、`#s0Switch`（切换状态/切回）、`#s0Copies`（副本清单）；
- 预填：切换成功后把 `{s0_record_id, baseline}` 存 `sessionStorage["loop.s0Prefill"]`，`showView("setup")` 时
  选中该基线并在 `POST /api/runs` 的 payload 带 `s0_record_id`（改动仅限 `s0.js` 与 `app.js` 的预填钩子）。

## 5 验收（先失败用例，再实现）

| 门 | 命令 | 期望 |
|---|---|---|
| 定向单测 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_s0_derive.py tests/test_env_switch.py tests/test_s0_from_rtl_api.py` | 全绿 |
| 单测门 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | 无回归（失败集与 STATUS 基线一致） |
| 浏览器门 | `cd loop && PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser` | 0 failed |
| 真实副本 | 真实环境派生（不写原 `ENV_ROOT`）+ 三库冒烟 + 切换 + 健康检查显示新根 + 切回 | 全步 rc=0、`baseline` 检查 passed |
| 文档门 | `python3 doc/audit/check_doc_links.py` | `missing=0` |

## 6 本轮明确不做（显式登记，不得冒充）

1. **零必改用例的 G1 分流**：需 `kb_lib.GATE_DECISIONS` 新枚举（冻结目录）+ N5 后条件分支，属独立变更；
   本轮保持现状（`N6_apply` 显式失败）。见 `doc/spec/LOOP_ORCHESTRATION_SPEC.md` §13-4。
2. 副本内 drill/演练：不复制夹具（733 M），副本环境只服务真实场景。
3. 副本自动清理：保留 + 界面手动删除（二次确认）。

## 7 环境限制（如实登记）

- 本机 `ENV_ROOT` 为只读挂载：派生只写 `<TOOL_ROOT>/workspaces/**`（可写），派生前后用 `baseline` 检查项自证原环境零写；
- 真实全跑 N9（≈19 min/用例）不在本片必达；本片实测到“派生 + 三库冒烟 + 切换 + 新建运行页”，
  N9 真机整跑按需另起；
- 浏览器门需 `PLAYWRIGHT_BROWSERS_PATH`/可写 `HOME`/`TMPDIR`（沿用既有命令）。
