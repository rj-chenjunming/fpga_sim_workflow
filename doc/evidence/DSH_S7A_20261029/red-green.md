# S7a RED → GREEN（数字从命令输出复制）

> 片：S7a（N6 材料面瘦身 + 提交格式前置）。用例文件 `loop/tests/test_n6_material_face.py`（12 例）。
> 纪律：先写失败用例再实现；判据只加严、不放宽（`apply_edits` 的"old 唯一且落在声明行"、
> `n6_apply` 的导入判据、DS-06 拒绝矩阵均未改动）。

## 1 RED

```
cd loop && .venv/bin/python -m pytest -q tests/test_n6_material_face.py
11 failed in 0.71s
```

11 条失败覆盖：N6 input 仍含 `n5_impact.json`、无派生摘要、派生记录缺 `derived_from`、
非 N6 节点未保持白名单面、缺源件未 `present=False`、符号链接未被拒、坏 JSON 未显式失败、
任务文本未禁止字符串 payload、`submit_result` 工具描述未禁止字符串 payload、
`apply_edits` 错误信息未点名"字段/实际行号/期望"、`BadSubmission` 未写期望类型。

> 说明（照实登记）：其中"`line` 必须逐字取自 `excerpts` 片段行首"一条，初版断言放在
> `_compose_task`（通用 Host 文本）上；该要求属 **N6 节点语义**，改判据面应落在
> `loop/prompts/loop_nodes.yaml`。于是把断言挪到 `request_contract("n6_author")` 上，
> 并**加强**为"逐字复制片段行首十进制行号，不得自己数行/从 1 重排"——这是收窄而非放宽。

## 2 GREEN

```
cd loop && .venv/bin/python -m pytest -q tests/test_n6_material_face.py
12 passed in 0.67s
```

## 3 受影响回归（定向）

| 组 | 命令 | 结果 |
|---|---|---|
| dsh 八件 + N6 三件 | `pytest -q tests/test_dsh_{assets,backend,admission,candidate,selfcheck,process,sdk}.py tests/test_agent_candidate_import.py tests/test_n6_imprint.py tests/test_n6_material_face.py` | **286 passed in 15.14s** |
| 旧断言更新（错误信息文本） | `pytest -q tests/test_fix_real_chain.py::test_n6_apply_rejects_line_mismatch_and_missing_revision` | **1 passed in 0.72s**（原 regex 钉的是旧错误文案 `与声明的 line`，改成钉"字段+声明值+实际行号"，判据不变） |
| flow/story/real-chain/context | `LOOP_WORKSPACE=<repo>/.dev-ws pytest -q tests/test_flow.py tests/test_node_story.py tests/test_fix_real_chain.py tests/test_agent_context_memory.py` | 首跑 `1 failed, 224 passed in 65.35s`；失败项 `test_g3_defer_halts_and_run_converges_to_finished` **单独复跑 `1 passed in 8.77s`** ⇒ 并发 flake（另一进程同一固定 `LOOP_NOW`；§8 已知坑），非本片回归 |

## 4 离线先行（不烧 token）

| 步 | 命令 | 结果 |
|---|---|---|
| dry-run（材料面 + prompt 渲染） | `probe_s7a.py --dry-run` | 材料面 **16757 B**；`input/` 只有 `TESTLIB/tc_bmc_i2c_03.sv`(15470) + `n6_impact_summary.json`(1287)；任务文本 `chars=17562` |
| 纯 Host 链路（S6 真实候选字节回放） | `probe_s7a.py --offline-chain` | `status=applied`、`source=candidate_import`、`md5_after=53f06f1b…` = S6 第 4 次真实候选 md5；`sandbox == real candidate bytes: True` |

## 5 真机（1 次调用）

| 阶段 | 结果 |
|---|---|
| `n6_author` | exit `completed`、wall **127.234 s**（`assert config.timeout_s == 300` 通过）、`validation.ok=True`、`execution_state=stopped` |
| `n6_apply`（同一 run，探针喂错 target） | `failed`：`revision 含非目标用例`（Host **正确** fail-closed） |
| `n6_apply`（同一次 attempt 的候选 + 封存输出重放） | `applied`、`candidate_import.ok=True`、5/5 `source=candidate_import` |
