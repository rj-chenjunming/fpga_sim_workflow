# 实施计划 · 用例判据人签覆写（CASE-OVERRIDE）（2026-11-02）

> 契约：[SPEC-REV-20](../spec/SPEC-REV-20-20261102.md)（**本计划的唯一契约来源**；冲突以规格为准）。
> 流程：[AGENTS.md](../../AGENTS.md) §2.1（先规格 → 计划 → TDD → 四道门 → 证据落档）。
> 写权：按 AGENTS §3 切片，**同一文件同一时刻只有一个 owner**。
> 环境约束：本机 `ENV_ROOT` 只读；N9/N15 真实执行不跑（覆写只经单测/drill/只读回放验证）。

## 切片与写权

| 片 | 内容 | owner | 写作用域 | 依赖 |
|---|---|---|---|---|
| **S1** | `case_state.py` 新增 `override` 子命令 + `--verify`；schema 增 `overrides`；`check_ledger` info 增 `waived`；kb 自测 | kb-owner | `kb/tools/case_state.py`、`kb/schema/case_states.schema.json`、`kb/tools/_selftest_case_state.py` | — |
| **S2** | N10 Host 落盘 `<run_dir>/n10_cases.json`（搬运既有判据）+ `ARTIFACTS` 登记 + 单测 | svc-owner | `loop/workflows/chunks/n10_semantics.py`、`loop/workflows/chunks/host_steps.py`（仅 ARTIFACTS 行）、`loop/workflows/chunks/model_steps.py`（仅 2 处最小调用，Lead 2026-11-02 裁定授权）、`loop/tests/test_n10_cases.py`（新） | — |
| **S3** | `services/case_override.py`（新）+ API 端点 + `contracts` 投影（`case_waivers` / `case_failures` / 报告横幅数据）+ 事件 + 单测 | svc-owner | `loop/services/case_override.py`（新）、`loop/services/api.py`、`loop/services/contracts.py`、`loop/host/progress.py`（仅 `ALLOWED_KINDS` 加 1 行，Lead 2026-11-02 裁定授权）、`loop/tests/test_case_override_api.py`（新）、`loop/tests/test_case_states_waivers.py`（新） | S1 的 CLI 契约、S2 的产物契约（**契约在规格 §3/§5/§7 已冻结，可并行开工**） |
| **S4** | G2/N13 面板逐例「机器原因 + 认定通过/撤销 + 二次确认」、徽标（用例列表/报告/N16）；浏览器门用例 | web-owner | `loop/web/app.js`、`loop/web/index.html`（如需）、`loop/tests/browser/test_case_override.py`（新） | S3 的 API/投影契约（规格 §7/§8） |
| **S5** | 集成复核、四道门 + 浏览器门实跑、冻结目录证据、`doc/STATUS.md`、文档索引；独立验证者复核 | Lead（+ verifier） | `doc/**`（Lead）、`loop/tests/**` 只读复核 | S1–S4 完成 |

**互不重叠**：`kb/**` 只有 kb-owner；`loop/workflows/**` 与 `loop/services/**` 只有 svc-owner；
`loop/web/**` 只有 web-owner；`doc/**` 只有 Lead。测试文件按片新建、不改他人文件。

## TDD 顺序（每片：先失败用例，再实现）

1. S1：`_selftest_case_state.py` 先加断言（拒绝矩阵 + 追加 + 锚 + 撤销 + 批量）→ 跑红 → 实现 → 跑绿。
2. S2：先写 `test_n10_cases.py`（缺件/字段值等于 n9_result/不重算）→ 红 → 实现 → 绿。
3. S3：`test_case_override_api.py` 先覆盖 §4 矩阵 1–7 与 200 路径；`test_case_states_waivers.py` 覆盖投影与 N16 `check_ledger`。→ 红 → 实现 → 绿。
4. S4：浏览器用例先写（机器原因原文可见、必须填理由、徽标、撤销）→ 红 → 实现 → 绿。
5. S5：四道门 + 浏览器门全绿；数字从命令输出复制。

## 验证门（DoD + 本片附加）

| 门 | 命令 | 期望 |
|---|---|---|
| 单测 | `cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q` | 无回归；收集/通过/失败/跳过记入 STATUS |
| kb 自测 | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests` | `PASS=10 / 9 / 28`、`FAIL=0`（**含 S1 新增断言**） |
| 端到端 | `cd loop && bash spikes/accept_v1_run.sh` | 退出成功、断言完整执行 |
| 文档 | 路径引用存在 + 数字与 STATUS 一致 | 零断链 |
| 浏览器（附加） | `cd loop && PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… .venv/bin/python -m pytest -q tests/browser` | 0 failed（S4 有界面改动 ⇒ 必须单独跑并记 STATUS） |
| **冻结目录专项** | `cd loop && python3 kb/tools/_selftest_case_state.py`（派生 ENV_ROOT 副本上） | 新断言全绿；证据落 `doc/evidence/CASE_OVERRIDE_20261102/` |

## 风险与对策

| 风险 | 对策 |
|---|---|
| 冻结目录改动被视为"改契约不修规格" | 规格已先写（本片）；证据目录含 diff + 自测原始输出 |
| 服务层与 kb CLI 形状不一致 | 规格 §3/§5 冻结命令行与字段名；S1 完成后 svc-owner 按实物复核一次 |
| 覆写真把失败说成通过 | O-5：所有读侧强制徽标；O-1：机器结论原样留档；测试断言"报告仍为 not_passed" |
| 旧 run 被盲签 | O-3/§3.2：`n10_cases.json` 缺失即 403，文案写明"机器原因未留存" |
| 并发写台账 | O-7：仅等待闸门可签；`running` 拒绝 |

## 未决（与规格 §12 同步）

- 独立锚文件、报告正文是否写豁免清单 —— 本轮不做，登记于规格 §12。
