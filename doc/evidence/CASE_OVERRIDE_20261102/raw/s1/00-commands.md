# S1（kb 层 case override）验证命令与原始输出留档

> 执行者：kb-owner（本片唯一写者）。工作目录 `/home/work/chenjunming/change-impact-loop`。
> 改动文件（仅 3 个）：`kb/tools/case_state.py`、`kb/schema/case_states.schema.json`、
> `kb/tools/_selftest_case_state.py`。测试/临时输出全部落在本目录（`loop/.logs/case_override/s1/`）。
> **本机 ENV_ROOT 只读**：kb 自测只写 `tempfile.mkdtemp()`；kb 门在派生副本上跑（AGENTS §4）。
> 注意：k=`cd loop` 后跑 kb 自测的路径是 `../kb/tools/...`；本目录记录的是**实际执行**的命令。

## 0 TDD：先红后绿

| # | 命令（真实执行） | rc | 结果 | 日志 |
|---|---|---|---|---|
| 0 | `PYTHONDONTWRITEBYTECODE=1 python3 -B kb/tools/_selftest_case_state.py`（改 selftest 前，基线） | 0 | `汇总：PASS=16 FAIL=0` | （终端） |
| 1 | 同上（**只加断言、未实现** ⇒ 红） | 1 | `FAIL` 30 条 + 在篡改锚处 `KeyError: 'overrides'`（功能不存在）；`PASS` 不完整 | `01-selftest-red.log` |
| 2 | 同上（实现 + schema 后第一轮） | 1 | `汇总：PASS=51 FAIL=2`（夹具里仍留「已修订待验」的负例影响 check 断言，已在 3 修正断言取向） | `02-selftest-green-1.log` |
| 3 | 同上 | 0 | `汇总：PASS=53 FAIL=0` | `03-selftest-green.log` |
| 4 | 同上（补 `--actor ""` = 矩阵 1 断言；`--actor` 缺省仍是 rc=2 用法错） | 0 | `汇总：PASS=54 FAIL=0` | `08-selftest-green-final.log` |

> 日志里的 `[FAIL] …` 行是**被拒路径的 stderr 诊断**（断言本身没有括号 `(rc=…)`），
> 判定以最后 `汇总：PASS=… FAIL=…` 为准。

## 1 kb 自测门（AGENTS §4 第 2 门，统一入口 + 派生副本）

```
cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests --reuse
```
- rc=0；`_selftest_gate_schema.py: PASS=10 FAIL=0` / `_selftest_n5_reachability.py: PASS=9 FAIL=0`
  / `_selftest_adjudicate_conflicts.py: PASS=28 FAIL=0`（与 `KB_EXPECT_PASS=(10 9 28)` 逐项相符）
- env_layer 用例：`3 passed, 24 deselected`
- `[info] 原 ENV_ROOT 零写入（find -newer 命中 0）`
- 日志：`05-env-layer-kb.log`
- 说明：`_selftest_case_state.py` **不在**该入口的 `KB_SELFTESTS` 清单里（数字不受本片影响），
  它以 `08-selftest-green-final.log` 单独为证。

## 2 单测层（受本片影响的消费方 + 全量）

| # | 命令 | rc | 结果 | 日志 |
|---|---|---|---|---|
| 5 | `cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh tests/test_fix_kbtools.py tests/test_fix_real_chain.py tests/test_agent_view_projection.py tests/test_node_story.py tests/test_node_detail_projection.py tests/test_agent_working_memory.py tests/test_agent_review.py tests/test_fix_lifecycle.py -q`（grep 出所有引用 `case_states` 的用例） | 0 | `423 passed, 1 warning in 129.79s` | `04-pytest-targeted.log` |
| 6 | `cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh`（全量软件层） | 见文件尾 | 见 `06-pytest-full.log` 末行 | `06-pytest-full.log` |

## 3 CLI 冒烟（默认 run dir 解析，不依赖 `--state-file`）

脚本 `/tmp/s1_smoke.sh`（一次性，写 `$TMPDIR` 工作区）：`init → set ×2 → override --verify → override 批量 2 例 →
check --json → override --verify → show --json → 重复签（rc=3）→ revoke → actor=model:（rc=3）→ check --json → --help`。
全部 rc 与预期一致；`check --json` 出现 `"waived":["tc_a","tc_b"]`；撤销后 `waived:["tc_b"]`。
日志：`07-cli-smoke.log`。

## 4 冻结目录纪律自证

- 本次只写 3 个文件：`find kb -newermt '-3 hours' -type f | grep -v __pycache__` ⇒ 恰为这 3 个。
- 未写 `doc/**`、`loop/services|web|workflows/**`（本片无写权）。
- `kb/tools/**` 未新增 `__pycache__`：所有 Python 调用均带 `-B` + `PYTHONDONTWRITEBYTECODE=1`。

## 5 全量单测（2026-11-02T11:0x 实测，数字从日志末尾复制）

命令：`cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh`（默认 `-m "not env_layer"`）
末行：`1 failed, 2067 passed, 3 deselected, 1 warning, 180 errors in 413.61s (0:06:53)`（日志 `06-pytest-full.log`）

两类非本片失败，逐条定性（**都不是 kb 改动引起**）：
1. `180 errors`：全部落在 `tests/browser/**`，根因是
   `playwright BrowserType.launch: Executable doesn't exist at …/chromium_headless_shell-1248/…`
   ⇒ 浏览器门需要 `PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=… TMPDIR=…`（AGENTS §4 补充门），
   本次全量入口没带该环境 ⇒ **环境缺件**，不当作通过、也不当作代码缺陷。
2. `1 failed`：`tests/test_flow.py::test_dead_job_never_counts_as_success`
   （断言 `'死任务' in doc.error`，实际得到 `loop/workflows/main_flow.py:619` 的
   `执行被框架置为 failed：见事件流/日志`）⇒ 该断言判据在 `loop/workflows/**`（**不是本片写域**），
   孤立重跑 `bash spikes/run_software_checks.sh tests/test_flow.py::test_dead_job_never_counts_as_success -q`
   ⇒ `1 passed in 2.67s`（日志 `09-pytest-deadjob-retry.log`）⇒ 全量下的**时序抖动**，与本片无关。

## 6 给 S2/S3 的 CLI 契约（实物行为，供联调对齐）

- `python3 kb/tools/case_state.py override --run <id> --case <c> [--case <c> …] --actor human:<n> --reason <r> [--revoke]`
  - 可选 `--state-file <path>`（与既有子命令同形；给了就取其**父目录**为 run_dir）；
  - 可选 `--verify`：带动作参数 ⇒ 先复核既有链再追加；不带动作参数 ⇒ 只复核（不需要 actor/reason/case）。
  - `--now ISO` / `KB_NOW`：`decided_at` 与 `updated_at` 的单一注入入口。
- 读 `<run_dir>/n10_cases.json`（**唯一**机器原因来源），要求：`schema="loop/n10_cases"`、
  `run_id` 与 `--run` 相等、`cases.<c>.passed` **恰好 false**、`reasons` 非空数组；
  该件缺失/旧轮未留存 ⇒ rc=3 拒绝（不解析 `n10_reconcile.md`）。
- 退出码：`0` 成功 / `2` 用法或请求形状错（重复 `--case`、缺 `--actor/--reason/--case`）/
  `3` 拒绝矩阵 1/2/3/4/5/7（**台账一字节未动**）/ `4` 台账损坏或矩阵 8 锚复核失败（**台账未改动**）。
- stdout：逐例一行 `[kb] override <action>：<case> <prev> -> <new>（machine.passed=False，机器原因 N 条）`
  + 一行台账摘要；**没有 JSON 输出**（S3 若要结构化结果，请读台账/`check --json`，不要复制判据）。
- `check --json` 的 `info` 新增 `waived`（最近一条记录是 `action="pass"` 的用例名，**展示用**；
  I2/I7 判据仍是 `state`/`rework_cycles`，未新增任何判定）。

## 7 Lead 追加项（2026-11-02，规格 §3.1/§4 行 4 已由 Lead 更新）

### 7.1 revoke 语义收紧
契约：`revoke` 必须要求「最近一条 `overrides[]` 记录 `action="pass"`」；机器途径/正常流程写入的
`已验证通过` 不得被 revoke 降级成待验 ⇒ 拒绝 rc=3、台账不动。

| # | 命令 | rc | 结果 | 日志 |
|---|---|---|---|---|
| 7 | `PYTHONDONTWRITEBYTECODE=1 python3 -B kb/tools/_selftest_case_state.py`（**只加断言 22b、未实现** ⇒ 红） | 1 | `汇总：PASS=54 FAIL=1`；失败行 `22b … (rc=0 same=False)` ⇒ 旧实现真的把机器通过降级了 | `11-selftest-red-revoke.log` |
| 8 | 同上（实现「最近一条记录不是 pass ⇒ 拒」后） | 0 | `汇总：PASS=55 FAIL=0` | `12-selftest-green-revoke.log` |
| 9 | 同上（最终复核，连跑一致） | 0 | `汇总：PASS=55 FAIL=0` | `13-selftest-final-revoke.log` |
| 10 | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests --reuse` | 0 | `PASS=10` / `PASS=9` / `PASS=28`、FAIL=0、`3 passed, 24 deselected`、原 ENV_ROOT 零写入 | `15-env-layer-kb-revoke.log` |
| 11 | `cd loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh <同样的 8 个文件> -q` | 0 | `423 passed, 1 warning in 111.21s` | `14-pytest-targeted-revoke.log` |
| 12 | CLI 冒烟 `/tmp/s1_smoke_revoke.sh`（默认 run dir）：机器通过的 `tc_machine` 上 revoke ⇒ `rc=3` 且 `LEDGER_UNCHANGED=1`（md5 前后同为 `755c92b2eda19d1779e62f2a1c5af9e4`）；`pass` 后 revoke ⇒ `rc=0`；`--verify` ⇒ `rc=0`；`check --json` ⇒ `tc_machine` 仍是 `已验证通过`、`waived:[]` | — | 全部符合 | `16-cli-smoke-revoke.log` |

### 7.2 冻结变更的文档面
本次冻结变更文件清单**增加第 4 个**：`kb/README.md`（Lead 授权；行 42 子命令清单
`init/set/show/check` → `init/set/show/check/override`，仅此一行、无其它段落改动）。
因此本片改动文件 = `kb/tools/case_state.py`、`kb/schema/case_states.schema.json`、
`kb/tools/_selftest_case_state.py`、`kb/README.md`（前 3 个为 S1 原始写域，第 4 个为本次授权追加）。

`kb/schema/gate_state.schema.json` / `kb/tools/gate.py` / `kb/tools/kb_lib.py` 的未提交改动
**不是本片**（会话开始前即存在，Lead 已按 mtime 10-30 核实）。
