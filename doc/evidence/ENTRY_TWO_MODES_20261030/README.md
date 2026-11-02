# 证据：S0 入口「单输入二选一」（环境项目 / 新版 RTL）· 2026-10-30

> 冻结件：本目录只增不改；引用请带 md5（账本在目录外：`doc/evidence/ENTRY_TWO_MODES_20261030.md5`）。
> 本轮为**同一执行者**分阶段实施与验证，不声称独立复核。

## 1 范围与决定

人 2026-10-30 对上一轮「单一 RTL 文件夹入口」提出两点修正，并逐条拍板：

1. 「基线工程目录」这个名字与运行期的**对比基线**（`kb/baselines/<id>`）混淆 ⇒ 改名 **环境项目目录**；
2. 「新版 RTL 文件夹」与「环境项目目录」应是**二选一**、RTL 不应是唯一必填；
3. 三问拍板：① 只给环境项目时 **RTL 用该项目自带的、不替换**；② 字段名用 **环境项目目录**；
   ③ 界面**单选二选一**，API 仍兼容两者同时给。

契约：[S0 §9.9](../../spec/S0_ENVIRONMENT_SPEC.md)、[WEB_UI §15](../../spec/WEB_UI_SPEC.md)；
计划：[2026-10-30-entry-two-modes.md](../../plans/2026-10-30-entry-two-modes.md)。

关键语义（fail-closed）：只给 `baseline` ⇒ `entry="env_folder"`，选择性复制成副本、**不替换 RTL**，
`rtl` 检查记 `skipped` + 固定理由（`ENV_NO_REPLACE`），其余五项照常；准出唯一例外 =
「`entry=env_folder` 且 `rtl=skipped`」，其它任何非 `passed` 一律不准出；两者都空 ⇒ 400。

## 2 验证（数字全部从命令输出复制）

| 门 | 命令 | 结果 |
|---|---|---|
| 单测（软件层） | `cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser` | **`2039 passed, 3 deselected, 1 warning in 254.85s`**，`rc=0` |
| 浏览器（补充门） | `cd loop && PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… .venv/bin/python -m pytest -q tests/browser` | **`180 passed in 186.42s`**，`rc=0` |
| 端到端 | `cd loop && LOOP_PORT=8197 LOOP_WORKSPACE=… bash spikes/accept_v1_run.sh` | 六相全 `rc=0` + **`=> ALL PASS`**，`rc=0` |
| 环境层 + kb 自测 | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests` | **`PASS=10 / PASS=9 / PASS=28`, `FAIL=0`**；`3 passed, 24 deselected in 9.24s`；原 `ENV_ROOT` 零写入（`find -newer` 命中 0），`rc=0` |
| 文档 | `python3 doc/audit/check_doc_links.py` + `pytest -q tests/test_doc_links.py` | `checked=3263 skipped=46498 historical=857 known_missing=16 env_missing=35 missing=0`，`rc=0`；`65 passed in 2.55s` |
| 真实链（环境项目入口） | `cd loop && .venv/bin/python spikes/verify_rtl_folder_entry.py --entry env --port 8198` | **`PASS=33 FAIL=0`**，`rc=0` |

### 2.1 真实链实测覆盖（`chain-env.log`）

真实 `ENV_ROOT`（只读挂载）作为**环境项目入口**的唯一输入，端到端 33 条断言全过：

- 派生：`entry="env_folder"`、`rtl_source`/`rtl_prefix`/`rtl_plan`/`folder_warning` 全为 `null`；
  `copy/non_rtl/baseline` `passed`，`rtl` `skipped` 且理由原文含「未提供新版 RTL / 不做替换」，
  `ports` 零差异（RTL 未替换），派生时 `smoke=waiting` 且未准出；`copy_plan` 落账（copied 非空 + 排除根非空）；
  副本数据根自包含（`<副本>/kb`）；
- 冒烟与准出：`advance` 后 `smoke=passed`，五项 `passed` + `rtl=skipped` ⇒ `ready_for_execution=true`；
- 切换：`activate` 202、202 的 `switch.target_env_root` == 副本、`/api/health.env_root` == 副本、
  `/api/env/state` 当前根=副本且 `origin_env_root` 仍为原始根、`switch.status=active`；
- 运行：副本数据根基线准入至少一个 `valid`；`POST /api/runs`（real、带 `s0_record_id`）跑到 **G1**
  （`status=waiting_gate`，`pending_interrupt` 以 `G1` 开头），run 文档 `env_root`=副本、`origin`=原始根；
  G1 逐条 `ignored`（human + 逐条理由）后运行收敛到终态（不阻塞切回）；
- 零写入：原始 `ENV_ROOT` `find -newer` **命中 0**；
- 切回与清理：`switch-back` 202、`/api/health.env_root` == 原始根、副本仍保留、`DELETE …/copy?confirm=true` 200。

`chain-env-attempt1.log` 是**同一脚本的第一次运行**：产品链本身 32 条 ok，唯一 FAIL 是验证脚本断言写了
`"未替换" in reason`，而产品理由是「未提供新版 RTL……不做替换」——**验证脚本断言文本错误**（已改为
`未提供新版 RTL` + `不做替换`），产品代码未因此改动；第二次运行即 `PASS=33 FAIL=0`（`chain-env.log`）。

## 3 边界与未做的（不宣称）

1. **`rtl_folder` 真实链本轮未重跑**：该入口的请求/记录语义未变（只多了分支），由软件层与浏览器层覆盖；
   其真实链证据仍见上一轮 [`RTL_FOLDER_ENTRY_20261030/`](../RTL_FOLDER_ENTRY_20261030/README.md)。
2. **N9 真机全跑**仍未跑（真实链只到 G1）；`kb/runs` 历史不随副本复制（§9.3 决定）。
3. **零必改用例的 G1 分流**仍未接入（[编排 §13-4](../../spec/LOOP_ORCHESTRATION_SPEC.md)）。
4. 软件层与浏览器门**分开跑**：`pytest -q`（含 `tests/browser`）需要浏览器与可写 `HOME`/`TMPDIR`，
   而 `tests/test_dsh_selfcheck.py` 断言"探针必须位于宿主真实 home 之下"，二者共用同一 `HOME` 覆盖会冲突
   （实测：覆盖 `HOME` 跑全量 ⇒ 该 1 条失败，属执行方式冲突而非产品回归）。因此软件层用
   `spikes/run_software_checks.sh`（影子可写数据根 + `-m "not env_layer"`），浏览器门单独跑。
5. 端到端使用 `LOOP_PORT=8197`：8099 被同工作区另一路会话的服务占用（未干预他人进程）。

## 4 本目录文件

| 文件 | 说明 |
|---|---|
| `chain-env.log` | 真实链（环境项目入口）最终运行日志：`PASS=33 FAIL=0` |
| `chain-env-attempt1.log` | 同一脚本首跑日志：唯一 FAIL 为验证脚本断言文本错误（见 §2.1） |
| `record.json` / `smoke.json` / `reports/env-check-report.md` | 该次真实链的 S0 记录、冒烟结论与准备报告 |
| `env-switch-active.json` / `env-switch-origin.json` | 切换状态与原始根记录（真实链结束时） |
| `software-gate.log` | 软件层门输出（`2039 passed, 3 deselected`） |
| `browser-gate.log` | 浏览器门输出（`180 passed`） |
| `e2e-accept.log` | 端到端六相输出（`=> ALL PASS`） |
| `env-kb-gate.log` | 环境层 + kb 自测输出（`PASS=10/9/28`、`3 passed`、原根零写入） |
| `doc-gate.log` | 文档路径门输出（`missing=0`） |
