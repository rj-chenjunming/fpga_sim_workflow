# 第三轮补充修订 · 实现契约与写权（2026-10-23 晚，接 round3-kickoff）

> **上游**：[`2026-10-23-node-panel-revision-round3-kickoff.md`](2026-10-23-node-panel-revision-round3-kickoff.md)
> （R3-01～R3-18 唯一清单）、[`2026-10-23-node-panel-unified-revision-plan.md`](2026-10-23-node-panel-unified-revision-plan.md)
> （§1–§8 既有接口契约，**不改**）、[`SPEC-REV-04` §C.2](../spec/SPEC-REV-04-20261023.md)、
> [`SPEC-02` §10.4](../spec/LOOP_ORCHESTRATION_SPEC.md)、[`SPEC-04` §4.2.1/§4.2.2/§6.7](../spec/WEB_UI_SPEC.md)。
> **本文件只做一件事**：把 R3 项落成**字段名/形状/文案/断言落点**，让多个 owner 互不重叠地并行。
> 与 SPEC 冲突以 SPEC 为准；本文件不新增业务写动作、不改判据、不改事件。
> **状态**：**已实施（2026-10-23 晚）**。四道门实测与未关闭项见 [`doc/STATUS.md` §52](../STATUS.md)，
> 证据见 [`doc/evidence/NODE_PANEL_ROUND3_20261023.md`](../evidence/NODE_PANEL_ROUND3_20261023.md)；
> 规格状态见 [`SPEC-REV-04` §E](../spec/SPEC-REV-04-20261023.md)。

---

## 0 切片与写权（互不重叠）

| 片 | 内容 | owner | 写文件（同一时刻只有一人） |
|---|---|---|---|
| W1 宿主数据面 | R3-01（提示词 + 校验）、R3-04 写侧（闸门落账 `hard_block`）、R3-09（N9_submit drill `cases` / N7 drill `case_count`） | **host-owner** | `loop/prompts/loop_nodes.yaml`、`loop/workflows/chunks/{model_steps,long_jobs,host_steps,gates}.py`、`loop/tests/test_flow.py`、`loop/tests/test_agent_context_memory.py`、新 `loop/tests/test_n6_imprint.py` |
| W2 story 投影 | R3-03 服务端、R3-06 服务端分组、R3-08、R3-10、R3-15 引用 | **story-owner** | `loop/services/node_story.py`、`loop/tests/test_node_story.py` |
| W3 前端 | R3-03 渲染、R3-06 分组渲染、R3-07、R3-08/R3-10 前端兜底、R3-12 消费、R3-13 死路径 | **web-owner** | `loop/web/{node-detail.js,index.html,app.css,app.js}`、`loop/tests/browser/test_node_detail.py` |
| W4 服务端投影/清理/文档 | R3-04 读侧、R3-11、R3-14、R3-15 单一来源、R3-17 收尾 | **Lead** | `loop/services/{node_registry,node_view,contracts}.py`、`loop/tests/{test_node_detail_projection,test_node_registry,test_software_checks_script}.py`、`loop/spikes/run_software_checks.sh`、`doc/**` |
| — 未执行 | R3-02/R3-05（服务未重启）、R3-16（`UI_RUNBOOK.md` 仍被另一条线占用）、R3-18（无新 real run） | Lead 登记 | 不改 |

**并发红线**（继承 round3-kickoff §0④）：不重启 `:18098`、不 `pkill`；不改 `kb/tools/**`、`host/evidence.py`、
环境仓 `RTL/TB/PKG/TESTLIB`；不写 `workspaces/s0-*`；不动 `doc/evidence/UI_RUNBOOK_20261023/**`；
不 `git commit`；只叠加不回退另一条线未提交改动。每个 R3 项至少一条**可判定断言**。

---

## 1 契约 A：`story` 新字段（W2 产出 / W3 消费；只增不改；旧 run 不回填）

### 1.1 `story.observation_points`（R3-03，仅 N6）

```jsonc
"observation_points": [{"case":"tc_pcie_rw_02","marker":"N6_fpga_date",
                        "addr":"0x0000","offset":"0x04","expected_value":"0x20260708"}] | null
```

- 来源 = N6 `detail.observation_points`（同一字段，**服务端确定性透传**；不新增 Host 字段）。
- `null` ⇒ 未下发（旧 run / drill / standin：模型未产出观测点）；空列表 = 下发了但 0 条（不冒充 null）。
- `key_results` 增一行（仅 N6）：`field="observation_points"`，`label="观测点"`，
  `value`=条数或 `"未下发"`，`text`= `"N 条（逐条见下）"` / `"未下发（旧 run 或替身，模型未产出观测点）"`，
  `missing`=是否未下发。

### 1.2 `story.evidence_groups` / `story.evidence_groups_note`（R3-06，N9/N7）

```jsonc
"evidence_groups": [{"case":"tc_pcie_rw_02", "refs":["logs/…_tc_pcie_rw_02_1_run.log"], "note":null}] | null,
"evidence_groups_note": "本轮没有证据文件（服务端未列出用例，也没有可展示的证据件）" | null
```

- 仅当**用例名可知**才分组：N9 取 `detail.cases_detail[].case`（旧 run 无 ⇒ 不分）；
  N7 取 `detail.cases`（名字列表；drill 的 `cases` 是对象列表 ⇒ 取其中的 `case`）。
- 每个用例一组；`refs` = `node.refs` 中 basename 含该用例名的件（保持服务端原顺序，不推断）。
- 该组 `refs` 为空 ⇒ `note="本轮未执行/无证据"`（N9 未执行）或 `"本轮没有这个用例的证据文件"`（N7）；
  不得留空白，也不得说"缺失"。
- 用例名不可知 **或** 一条 ref 都归不到任何用例 ⇒ `evidence_groups=[]`，
  `evidence_groups_note` 说明原因（不编组）。
- 无法分组（`null`）⇒ 前端维持现状平铺 `refs`（不得报错）。

### 1.3 `not_reached` headline 加中文 gloss（R3-08）

`本轮没有走到这个节点（运行停在 {run_status}，{gloss}）。`
其中 `gloss` = `STATUS_GLOSSARY[run_status]`（`failed→失败`、`finished→已完成`），
值缺失 ⇒ 不加 gloss、写成 `本轮没有走到这个节点（运行停在 {run_status}）。`。
**原值必须保留**；正文不得出现"等它跑完"。

### 1.4 `run_halted` 输入（R3-10）

`build_story(..., run_halted: bool = False)` 新增关键字参数；W4 的 `node_view.build_node_detail`
从全量事件算出 `run_halted = any(e.node == "HALT" and e.kind in ("node_finished","node_failed") for e in events)`
后传入。语义只影响 `DRILL_SKIPPED_NODES`（当前 = `N15_submit`）的"未执行"归因：

| 条件 | headline / evidence_note（示例） |
|---|---|
| drill 且 `run_halted=True` 且该节点无事件 | `本轮未执行这个节点（没有提交记录）。` / `本轮未执行这个节点：没有提交记录，因此没有证据文件。` |
| drill 且未 halted（演示模式正常走到终点） | 保持 P-33 原文（`演示模式下不提交作业…`） |
| 非 drill | 不变 |

`not_executed` 仍为 `true`（确实没执行），只改归因文案；`run_halted` 不写进投影字段。

### 1.5 `headline_source` 的授权消费者（R3-12）

前端消费：`headline_source != "template"` 且 headline 非空时，在结果标题后加一个小字附注
`.nd-headline-src`：`summary → "（原文摘要）"`、`missing → "（未下发）"`；`template` 不显示。
（字段保留在契约里；断言见 §6。）

---

## 2 契约 B：闸门"当时的硬阻断"落账与投影（R3-04）

### 2.1 写侧（W1 `gates.py::_resumed`）

`run_dir/decisions/<gate>.json` 的每条 `records[]` 增：

```jsonc
"hard_block": [{"code":"I2_CASES_PENDING","title":"…","message":"…"}]
```

- 来源 = 本门开启时落进 state 的 `gate_material::<gate>` 的 `hard_block`（提交前材料）；
  材料缺失/不可读 ⇒ `[]`（不猜、不以 0 条冒充"没有阻断"以外的含义：空列表就是材料里没有）。
- `append_decision_ledger` 只写契约字段（`code/title/message`），不改既有字段、不删 `entries`。

### 2.2 读侧（W4 `contracts.gate_entries_view`）

- 已决策态（`state="decided"`）：`hard_block` 取最新 ledger record 的 `hard_block`（白名单三字段）；
  `counts.hard_block` = 该列表长度（ledger 有该键才算下发，旧 run 无 ledger ⇒ `null`）。
- ledger 缺 `hard_block` 键（旧 run / 早于落账）⇒ `hard_block=[]` **且** `note` 追加一句
  `当时的阻断项未留存（该 run 早于落账）`（与 G1"逐条处置未留存"同一句式的并列句，不覆盖原 note）。
- 等待态不变（材料 `hard_block`）。

---

## 3 契约 C：detail 补齐（R3-09，W1）

| 节点 | 变更 | 断言 |
|---|---|---|
| `N9_submit`（drill 路径） | `node_finished.detail` 增 `"cases": 1`（= 本轮 drill 目标用例数，`payload.cases` 长度），既有字段不动 | drill 全链表单节点 headline 含 `覆盖 1 个用例`（不再"覆盖用例数未下发"） |
| `N7`（drill 路径） | `node_finished.detail` 增 `"case_count": 1`（与 real 路径同字段名；`cases` 形态不动） | drill N7 headline 含 `1 个用例都编译通过` |

`story` 两处都按"字段存在即用、缺失走既有回退"消费（W2 只补断言，不新逻辑外的猜）。

---

## 4 `GATE_NODES` 单一来源（R3-15）

新增叶子模块 `loop/services/node_registry.py`：

```python
GATE_ID_BY_NODE: dict[str, str] = {"N4": "G1_diff_confirm", "N13": "G2_report_accept",
                                   "N14": "G3_regression_decision"}
GATE_NODES: frozenset[str] = frozenset(GATE_ID_BY_NODE)
```

- `node_view` 与 `node_story` 都**只**从这里引用（保留各自模块级同名别名，避免外部 import 破裂）；
  删除两份本地定义。
- 断言：`node_story.GATE_NODES is node_registry.GATE_NODES`、`node_view.GATE_ID_BY_NODE is node_registry.GATE_ID_BY_NODE`。

---

## 5 `REQUIRED_FIELDS` 与可选下限（R3-11，W4）

- `REQUIRED_FIELDS` **不加**新 run 才有的字段（否则旧 run 全报 `missing_fields`）。
- `SPEC-02 §10.4.5` 增"可选下限（新 run 才下发；缺失不算 missing）"表，覆盖
  `digest_summary/digest_confirmations/groups_count/offered_segments_empty/to_check_case_count/to_check_cases/
  case_edits/observation_points/applied_cases/check_count/must_fix_count/cycle/limit/koutou1_by_case/
  example_line/identity/cases_detail/cases_table/classification/identity_table/unclosed/
  rework_requests_count/refs_parseable_count/open_items/cases_summary/will_really_run/executed/
  failed_cases/reason_line/result_artifact`。
- 断言：新 drill 全链这些字段**存在**（`null` 也算下发）；旧 run 不因缺它们进 `missing_fields`。

---

## 6 断言落点（每个 R3 项至少一条；只加不放宽）

| R3 | 断言文件 | 可判定内容 |
|---|---|---|
| R3-01 a/b/c | `loop/tests/test_n6_imprint.py`（新） | 提示词含 `uvm_info("<marker>"` 且不含 `uvm_info("N6",`；合法 marker+edits 通过；`N6_CHECK_1` 不可解析 ⇒ fail-closed 且原因点名 marker |
| R3-01 d | 同上 | 真格式日志 + by-id 段 + run 级 `doc_entries.jsonl` ⇒ `evidence_view()` 该印记 `consistent=True`、`verdict.passed=True` |
| R3-02/R3-05 | `doc/STATUS.md` §52 | 未执行 + 原因（服务进程仍是旧代码：`GET …/nodes/N1` 无 `story`） |
| R3-03 | `test_node_story.py` + `tests/browser/test_node_detail.py` | story 两态（有/无 observation_points + key_results 行）；前端有列表/无文案 |
| R3-04 | `tests/test_flow.py`（写侧）+ `test_node_detail_projection.py`（读侧） | 新 drill run 的 G1 ledger 含 `hard_block`；已决策 gate 块含 `hard_block`；无 ledger 旧 run 显示"当时的阻断项未留存" |
| R3-06 | `test_node_story.py` + 浏览器 | N9 3 用例 ⇒ 3 组（空 refs 组带 note）；N7 无名 ⇒ `[]` + note |
| R3-07 | 浏览器 | 展开后含 `example_line` 原文；`null` ⇒ 不渲染该块 |
| R3-08 | `test_node_story.py` + 浏览器 | `failed→失败` / `finished→已完成`；不含"等它跑完" |
| R3-09 | `test_flow.py` + `test_node_story.py` | drill N9_submit headline 含"覆盖 1 个用例"；drill N7 含"1 个用例都编译通过" |
| R3-10 | `test_node_story.py` | `run_halted=True` 的 drill N15_submit 文案不含"演示模式"；`run_halted=False` 仍是 P-33 文案 |
| R3-11 | `test_node_detail_projection.py` | 新 run 可选字段全存在且不进 `missing_fields`；旧 run 无这些字段也不进 `missing_fields` |
| R3-12 | 浏览器 | `headline_source="summary"` ⇒ `.nd-headline-src` 可见；`template` ⇒ 不可见；`attached[].note` 在展开区可见 |
| R3-13 | `test_web_smoke.py`/`test_gate_session.py`（跑通）+ 浏览器 | 删除 `renderEntryDecisionHint` 后既有行为不变（无死函数引用） |
| R3-14 | `loop/tests/test_software_checks_script.py`（新） | 带 `-q` 调用脚本时输出仍含 `passed`（不再 `-qq` 吞掉汇总） |
| R3-15 | `loop/tests/test_node_registry.py`（新） | 两份定义合并为一份（`is` 同一对象） |
| R3-16 | `doc/STATUS.md` §52 | 未执行 + 原因（`UI_RUNBOOK.md` 仍是另一条线未提交改动） |
| R3-17 | `doc/**` | SPEC-REV-04 §C.2 / SPEC-02 §10.4.5 / STATUS §52 / evidence 只增 |
| R3-18 | `doc/STATUS.md` §52 | 只登记，不阻塞 |

---

## 7 四道门（收尾由 Lead 统一跑，数字复制输出）

```bash
bash loop/spikes/run_software_checks.sh --ignore=tests/browser          # 基线 656 passed / 3 deselected
cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
  .venv/bin/python -m pytest -q tests/browser                            # 基线 75 passed
LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py      # PASS=10
LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py  # PASS=9
# 端到端：隔离工具副本 + 副本环境 + LOOP_PORT=18199（基线 ALL PASS 117/117）
python3 doc/audit/check_doc_links.py                                      # missing=0
```
