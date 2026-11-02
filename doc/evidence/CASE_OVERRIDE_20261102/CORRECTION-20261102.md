# 更正件（只增不改）· CASE-OVERRIDE 证据档 · 2026-11-02

> **性质**：本文件是**追加**，不修改本目录任何既有文件（归档只增不改，红线 3）。
> **触发**：独立验证者终验（报告见 [`raw/verify/REPORT.md`](raw/verify/REPORT.md)）发现本档
> `README.md` 与 `doc/STATUS.md` 有 3 处索引/计数与原件不符（判定 §5：证据-数字一致性 **FAIL**，
> 其余 5 项 PASS，**无行为缺陷**）。另 1 处（D1）在活文档 `STATUS.md` 中，已直接更正。

## 更正项

| # | 位置 | 原文（不准确） | 实际（以原件为准） | 处置 |
|---|---|---|---|---|
| D1 | `doc/STATUS.md` §148.2 文档门行 | 引 `skipped=47802` | 文档门计数 `skipped` 是**诊断值**，随文档正文变化；更正件写入后再测为 **47804** | 已在 STATUS 中改为只引 `checked=3380 … missing=0` 与 rc=0，不再引用易变的 `skipped` |
| D2 | 本档 `README.md` §2 末句 | 称 `kb/**` **4 件**的本轮 hunk 全在 `raw/s5-our-hunks.diff` | 实际 **3 件**（`case_state.py`、`case_states.schema.json`、`_selftest_case_state.py`）；`kb/README.md` 的 1 行在 [`raw/s1-kb-frozen-change.diff`](raw/s1-kb-frozen-change.diff) | 以本表为准；原因：hunk 抽取关键字未含裸词 `override`，故未收入 s5 汇总 diff |
| D3 | 本档 `README.md` §4 S1 行 | 称 `raw/s1/` 含「17 条 CLI 冒烟」 | 实际两版冒烟：`raw/s1/07-cli-smoke.log` = **13 步**、`raw/s1/16-cli-smoke-revoke.log` = **8 步**；**没有 17 步版本**。S1 口头报告里的"17"是"CLI 冒烟 + 断言"的合计说法，不是步数 | 以日志为准；两版均已归档 |
| D4 | 本档 `raw/s1/00-commands.md` 索引 | 索引了 10 个当时未归档的日志 | 本次已**全部补归档**：`02/03/04/05/06/07/08/09/10/11/12`（补后 `raw/s1/` 共 17 个文件，与索引 1:1） | 追加文件，索引与归档现已对齐 |

## 追加的文件（均为只增）

- `raw/s1/02-selftest-green-1.log`、`03-selftest-green.log`、`04-pytest-targeted.log`、
  `05-env-layer-kb.log`、`06-pytest-full.log`、`07-cli-smoke.log`、`08-selftest-green-final.log`、
  `09-pytest-deadjob-retry.log`、`10-selftest-final-rerun.log`、`11-selftest-red-revoke.log`、
  `12-selftest-green-revoke.log`
- `raw/verify/*`：独立验证者的报告与原始输出（`REPORT.md` 等）

## 账本

目录外 md5 账本 `doc/evidence/CASE_OVERRIDE_20261102.md5` 已在上述追加后**重新生成**
（旧账本只覆盖 38 个文件；新账本覆盖当前全部文件）。本目录仍为只读（`chmod -R a-w`）。

## 复核口径

- 验证者未重跑 21 h 真实轮，也未重跑全量 `2104` 单测 / e2e / 浏览器 `199`（如实登记，不代称通过）；
  四道门正式数字仍以 `raw/s5/` 原始输出与 `doc/STATUS.md` §148.2 为准。
- 本更正件不改变任何门禁判定：5 PASS / 1 FAIL（证据-数字项）中的行为、红线与文档门结论不变。
