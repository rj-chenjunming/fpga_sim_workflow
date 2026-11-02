# 计划：N5 必改=0 的 G1 分流闸门 `G1_no_impact`

- 日期：2026-10-30（承接 [LOOP §13-4](../spec/LOOP_ORCHESTRATION_SPEC.md) 的未决登记）
- 业务契约：[CHANGE_IMPACT_LOOP_SPEC §12](../spec/CHANGE_IMPACT_LOOP_SPEC.md)
- 机制契约：[LOOP_ORCHESTRATION_SPEC §14](../spec/LOOP_ORCHESTRATION_SPEC.md)
- 人 2026-10-30 五项裁决：① 新增闸门 id `G1_no_impact`；② 触发用**宽口径**（只看 `must_change_count == 0`）；
  ③ `full_regression` 跳过 N6–N8 直接 N9 全量跑；④ `no_impact_end` = HALT + finished + 不晋升；
  ⑤ 只有 `no_impact_end` 强制理由。
- 同一执行者实施与验证，不声称独立复核。

## 1 变更性质

`kb/tools/kb_lib.py` 与 `kb/schema/gate_state.schema.json` 属**冻结目录**（AGENTS §3）：
按「改语义需单独变更并留证」执行——本计划 + 证据 `doc/evidence/KB_GATE_NO_IMPACT_20261030/`
（枚举/模式 diff、kb 自测输出、`gate.py` 对新闻门的签/查实测）。

## 2 冻结接口（实现前定死）

| 项 | 值 |
|---|---|
| `GATE_IDS` | `(…原三项…, "G1_no_impact")`（末尾追加） |
| `GATE_IDS_V1` | 原三项（供 `gate.py` 读 v1 旧 `gates.json`） |
| `GATE_KIND["G1_no_impact"]` | `"diff_confirm"` |
| `GATE_DECISIONS["G1_no_impact"]` | `["no_impact_end", "full_regression", "pending"]` |
| gate-state `version` | 新文件 `2`（含第 4 门）；旧文件 `1` 仍合法可读（`gate.py` 按 version 决定必需门集合） |
| `kb/schema/gate_state.schema.json` | `version` 允许 `1/2`；`gates.required` 恒含三项主门；`version==2` 时要求 `G1_no_impact`；`gate_id` 枚举加新门 |
| 节点 | `N5b`；`GATE_STAGE["G1_no_impact"] = "n5_gate1b"` |
| 事件 | N5 出口：`N5_HAS_MUST_CHANGE` / `N5_ZERO_MUST_CHANGE`；门出口：`G1_NO_IMPACT_END` / `G1_NO_IMPACT_FULL_REGRESSION` |
| 目标集来源标识 | `n9_job.target_set = "baseline_frozen_full"`（全量分支）/ `"n6_applied"`（原路径） |

## 3 切片与写权

| 切片 | 范围 | 写权 | 验证 |
|---|---|---|---|
| S1 冻结枚举+schema | `kb/tools/kb_lib.py`、`kb/schema/gate_state.schema.json`、`kb/tools/gate.py`（version-aware 必需门 + 文档） | Lead（单独变更+留证） | kb 自测 + 新单测（v1 旧文件可读 / v2 新文件校验 / 新门可签可查） |
| S2 权威与投影 | `loop/host/gate_authority.py`（DEFAULT_EXPECT / 中文标签 / 适用性）、`loop/services/contracts.py`（GATE_STAGE、理由集、`_gates_authority` 过滤） | Lead | 投影单测 |
| S3 拓扑与分支 | `loop/workflows/chunks/gates.py`、`host_steps.n5_impact`、`long_jobs.n9_submit`、`main_flow.py`、`model_steps.n12_report`（缺 N6/N8 容错） | Lead | 分支单测（必改>0 不进分流；必改=0 进门；两决策行为；N9 全量目标集/身份） |
| S4 界面 | `loop/web/app.js`（第 4 门标签/节点名）、必要时 `loop/web/index.html` 文案；浏览器测试 | frontend（Lead 复核） | 浏览器门 |
| S5 文档/证据/STATUS | 规格（已改）、本计划、证据目录 + md5、STATUS 追加 | Lead | 文档门 |

## 4 不做与边界

- **不跑 real 全量回归**（≈19 min/用例 × 全量，成本超本轮）：分支只经 drill + 单测证明，
  STATUS/证据里如实写「real 全量回归未跑」，不得宣称跑通。
- 不新增第四道「主线闸门」：`G1_no_impact` 是 G1 的分流支线，上游业务契约措辞已同步（§12）。
- 不改 N6 路径语义；有任一必改用例 ⇒ 不得进入该门。
- 旧 run 的 `gates.json`（version=1，3 门）保持可读；不改写历史文件。
