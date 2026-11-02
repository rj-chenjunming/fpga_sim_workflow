# 计划：S0 入口「单输入二选一」（环境项目 / 新版 RTL）

- 日期：2026-10-30（承接 `2026-10-30-rtl-folder-one-click.md`）
- 契约：[S0 §9.9](../spec/S0_ENVIRONMENT_SPEC.md)、[WEB_UI §15](../spec/WEB_UI_SPEC.md)
- 人已拍板（2026-10-30，三问）：① 只给环境项目时 **RTL 用该项目自带的、不替换**；② 字段名 **环境项目目录**；
  ③ 界面**单选二选一**，API 仍兼容两者同时给。
- 同一执行者分阶段实施与验证，不声称独立复核。

## 1 问题

上一轮的入口把 `rtl_source` 定为**唯一必填**（S0 §9.1），但真实场景有三种输入：
只有新版 RTL；只有整套环境项目（交付包/别人给的工程）；两者都有。现状逼着"有环境项目"的人也必须再指一个 RTL，
且「基线工程目录」这个词与运行期的对比基线（`kb/baselines/<id>`）混淆。

## 2 决定（冻结）与不加的东西

| 项 | 决定 |
|---|---|
| 输入 | 同一个端点 `POST /api/s0/from-rtl`，字段名不变；**判定只看空不空** |
| 只 `rtl_source` | `entry="rtl_folder"`（现行 §9.3/§9.4，环境资产取原始环境根） |
| 只 `baseline` | `entry="env_folder"`：选择性复制环境项目成副本，**不替换 RTL**；`rtl` 检查 `skipped` + 固定理由 |
| 两者都给 | 兼容保留，等同现行「环境项目 + 新版 RTL」（`entry="rtl_folder"`）；界面不展示 |
| 都为空 | 400，理由可读 |
| 界面 | 单选 `#s0Mode`（默认 rtl）→ `#s0Rtl` 或 `#s0EnvDir`；只有一个可见必填 |
| 准出 | 除 `rtl` 外五项全 `passed` 且无漂移；`rtl` 允许 `skipped` **仅当** `entry="env_folder"`；其余 fail-closed |
| 报告 | 阻断项与「无阻断」结论同判据；`rtl` skipped 显示「未替换（环境项目入口）」 |
| 不加 | 不加新端点、不改字段名、不引入对比基线选择、不改切换/切回/删除/活跃 run 语义、不做"环境项目 + 后续补 RTL"两步流 |

## 3 切片与写权

| 切片 | 范围 | 写权 | 验证 |
|---|---|---|---|
| T1 Host | `loop/host/s0.py`（模式判定、`env_folder` 记录、`_verify` 跳过 null `rtl_source`、报告分支）、`loop/host/s0b.py`（`ready_for_execution` 模式感知） | Lead | 新增 `loop/tests/test_s0_env_entry.py`；`tests/test_s0b.py`、`test_s0.py` 回归 |
| T2 API | `loop/services/api.py`（二选一校验、docstring/错误映射）、`loop/tests/test_s0_from_rtl_api.py` | Lead | 只给 `baseline` 200/都空 400/两者都给不变 |
| T3 Web | `loop/web/index.html`、`loop/web/s0.js`、`loop/tests/browser/test_s0_auto_entry.py` | frontend（Lead 复核） | 浏览器门（`pytest tests/browser`，0 failed） |
| T4 验收 | 真实链脚本 `loop/spikes/verify_rtl_folder_entry.py`（env 模式场景）、证据与 STATUS | Lead | 四道门 + 浏览器门 + real 链 |

## 4 关键实现点（供复核）

1. `prepare_from_rtl`：`rtl_value, baseline_value = payload.get('rtl_source'), payload.get('baseline')`；
   都空 ⇒ `ValueError`；`rtl_value` 空 ⇒ `env_folder`；`baseline` 空 ⇒ 用 `default_baseline`（现行）。
2. `env_folder`：`plan = plan_copy(baseline)`；`rtl_plan = None`；`folder_warning = None`；不调 `plan_rtl_source`/`replace_rtl`；
   `checks[1]`（`rtl`）置 `skipped` + 固定理由；其余 `copy → non_rtl → ports` 不变；`baseline_version` 缺省 `ENV@<basename>+<UTC>`。
3. `ready_for_execution`：唯一例外分支写死 `entry == "env_folder" and rtl == "skipped"`，其它非 `passed` 一律 false。
4. `_verify`：`record.get('rtl_source')` 为 `None` ⇒ 跳过 `rtl_source` 见证比对（不能把 null 当漂移）。
5. 报告：阻断项集合 = 与准出同判据（`skipped` 不算阻断）；头措辞按 `entry`。
6. 证据：`doc/evidence/ENTRY_TWO_MODES_20261030/`（记录/报告/real 链日志/browser 门日志），只增不改，chmod 444 + md5 账本。

## 5 验证门

- 单测：`cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q`（记录 passed/failed/skipped）
- 浏览器门：`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser`
- 端到端：`bash spikes/accept_v1_run.sh`
- 环境+kb：`bash spikes/run_env_layer_checks.sh --with-kb-selftests`
- 真实链：`DEST=… bash spikes/provision_dev_workspace.sh --link-fixture --force --quiet` + `spikes/verify_rtl_folder_entry.py`
  （新增 `--entry env` 场景：只给环境项目，断言 `rtl=skipped`、五项 passed、准出、切换、原根零写入、切回）
- 文档门：`doc/audit/check_doc_links.py`
