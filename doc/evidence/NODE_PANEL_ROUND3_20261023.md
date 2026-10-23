# 节点面板第三轮补充修订 · 实测证据（2026-10-23 晚）

> **范围**：遗漏审计开工包 [`plans/2026-10-23-node-panel-revision-round3-kickoff.md`](../plans/2026-10-23-node-panel-revision-round3-kickoff.md)
> 的 R3-01～R3-18；实现契约 [`plans/2026-10-23-node-panel-revision-round3-impl.md`](../plans/2026-10-23-node-panel-revision-round3-impl.md)。
> **规格**：[`SPEC-REV-02` §E](../spec/SPEC-REV-02-20261023.md)、[`SPEC-02` §10.4.5](../spec/LOOP_ORCHESTRATION_SPEC.md)、
> [`SPEC-04` §4.2.1/§4.2.2/§6.7](../spec/WEB_UI_SPEC.md)。门禁数字同步在 [`doc/STATUS.md` §50](../STATUS.md)。
> **只增不改**：本文件记录本轮实测；旧证据 [`NODE_PANEL_REVISION_20261023.md`](NODE_PANEL_REVISION_20261023.md) 保持原样。
> **不声称合规**：§8 的未执行项与边界必须与本文件一起读。

---

## 0 本轮红线遵守（实测可核）

- 未重启 `:18098`、未 `pkill uvicorn`；未改 `kb/tools/**`、环境仓 `RTL/TB/PKG/TESTLIB`、`doc/evidence/UI_RUNBOOK_20261023/**`；
- 未 `git commit / checkout / stash`；只叠加另一条线的未提交改动（`git diff` 逐文件看过）；
- 端到端在**隔离工具副本** + 副本环境 + `:18199` 上跑，跑完删除副本与 3 个 `.loop_drill` 测试 run；
- 每个 R3 项至少一条可判定断言；未放宽/删除既有断言（唯一改写是 R3-08 收紧 not_reached 期望串）。

---

## 1 R3-01（P0）：N6 观测点印记必须能被 host/evidence 解析

### 1.1 根因（改前）

提示词示例是 `uvm_info("N6", $sformatf("[%s] OK …", "N6_FPGA_DATE", …))` ⇒ 日志里 UVM report
**ID 是 `N6`**，而 `host.evidence.find_imprints()` / `_auto_markers()` 只认 **ID 含 `N6_`** 的印记
⇒ `无预期观测点印记(I3)`，真实轮 I3 永远过不了。即使 ID 对了，marker 解析不到文档条目时
`_verdict` 仍判"期望不可解析"⇒ 不得判跑通。

### 1.2 改动

| 落点 | 改动 |
|---|---|
| `loop/prompts/loop_nodes.yaml::n6_author` | 示例改 `uvm_info("<marker>", $sformatf("OK <addr>+<off> <name> = 0x%08h", actual), UVM_LOW)`；规则明写「marker 必须是 UVM_INFO 的 **ID** 参数，不是消息前缀」「marker 必须含 doc_bitdef.name，解析不到 ⇒ fail-closed」；保留"必须写进同用例 `edits[].new`""打印实读值" |
| `loop/workflows/chunks/model_steps.py` | `_validate(..., run_dir=None)`；n6 分支**恒执行** `host.evidence.resolve_expected_imprint(marker, run_dir=run_dir)`，address/value 任一空 ⇒ problem（点名 marker + `resolved_by`）；`run_model_node`/`_run_model_attempt` 用 `partial(_validate, run_dir=ctx.run_dir)` 绑定；无"没绑就跳过"的旁路（有反向用例锁死） |
| `loop/tests/test_n6_imprint.py`（新，7 条） | a 提示词形态；b 合法 marker+edits 通过；c 不可解析 marker fail-closed；d 端到端印记单测；另有 run_dir 绑定/未绑定区分、无 run_dir 反例 |

**不改** `host/evidence.py`（期望解析是权威，本轮只让输出可被它解析）。

### 1.3 断言实测（命令输出复制；`bash loop/spikes/run_software_checks.sh tests/test_n6_imprint.py`）

```
7 passed in 0.62s
a) contains uvm_info("<marker>": True   /   contains uvm_info("N6", : False
b) ok: True problems: []
   point {'case': 'tc_demo', 'marker': 'N6_fpga_date', 'addr': '0x0000', 'offset': '0x04',
          'expected_value': '0x20260708'}
c) ok: False
   problem: observation_points[0].marker 'N6_CHECK_1' 的期望地址/值不可解析：
            文档条目快照里没有匹配条目（resolved_by=未解析）…
d) imprint.checks: {"imprint_present": true, "id_count_present": true,
                    "count_matches_id_count": true,
                    "address_matches_expected": true, "value_matches_expected": true}
   expected: {"entry_name": "fpga_date", "address": "0x0000+0x04",
              "value": "0x20260708", "resolved_by": "run-snapshot"}
   imprint.consistent: True    verdict.passed: True    reasons: []
```

> **d 直接证明"新 run 能过 I3"**：日志行
> `UVM_INFO top_env.sv(154) @ 0.000 us [N6_fpga_date] OK 0x0000+0x04 fpga_date = 0x20260708`
> + `UVM Report Summary`（四项 severity=0）+ `Report counts by id` 段 `[N6_fpga_date] 1`
> + run 级 `doc_entries.jsonl`（`fpga_date` / `0x0000` / `0x0004` / `0x2026_0708`）
> ⇒ `evidence_view()` 的 `consistent=True`、`verdict.passed=True`。
> 只影响新 run：旧 run/夹具不回填；drill/standin 下 `observation_points=null`。

---

## 2 R3-02 / R3-05 真机复核：**未执行**（依赖人工重启，原因如下）

2026-10-23T22:08:50 实测 `:18098`（命令与输出见 `.tmp/r3_02_service_probe.log`，本文件抄录）：

```
GET /api/runs -> 200
routes=18
report_route= ['/api/s0/{record_id}/report']        # 没有 /api/runs/{id}/report
story_keys= ['key_results', 'purpose', 'steps']      # 没有 headline/note/gate 等第二轮字段
run_status= failed  mode= real
```

⇒ 服务进程仍是**第一版"人话面板"（§45）时的旧代码**，第二轮与第三轮的服务端改动都没加载。
按并发红线（进程在独立 PID 命名空间、Agent 无法按 PID 停止；重启必须由人执行）**未重启**，
因此 N1–N9 的新 `story`/N4 逐条处置/N12 报告全文/N13 只读待确认项等**真机复核未执行**。
重启命令见 [`doc/STATUS.md` §50.4](../STATUS.md)；重启后可复核清单见 §8。

---

## 3 R3-03 / R3-06 / R3-07 / R3-08 / R3-10（story + 前端）

| 项 | 服务端 | 前端 | 断言 |
|---|---|---|---|
| R3-03 观测点 | `story.observation_points` **仅 N6 下发 key**（`null`=未下发 / `[]`=0 条 / 数组=透传）；N6 关键数字增「观测点」行 | `#ndKey .nd-obs-details`（默认收起；三态互不冒充） | `test_node_story.py`（N6 三态 + 非 N6 无 key）；浏览器 `nd-obs-*` |
| R3-06 证据分组 | `story.evidence_groups=[{case,refs,note}]`（N7/N9 按用例名；组内无证据给 note；不能分组 `[]`+原因；只取面板展示的 run 目录内 refs） | `#ndRefs .nd-ref-group`（空组显示 note，不留空白） | `test_node_story.py`（分组/空组/不可分组/refs 过滤 4 类）+ 浏览器 |
| R3-07 示例行 | （字段既有）`detail.example_line` | `details.nd-example` 默认收起，展开见原文；`null` 不渲染 | 浏览器 |
| R3-08 未到达 | headline =「本轮没有走到这个节点（运行停在 {原值}，{失败/已完成}）」 | 原样透传，不再拼"等它跑完" | `test_node_story.py`（failed/finished 两种）+ 浏览器 |
| R3-10 早停归因 | `build_story(run_halted=…)`；drill 且运行已 HALT ⇒ N15_submit「本轮未执行这个节点（没有提交记录）。」 | 原样透传，不再自拼"演示模式" | `test_node_story.py`（halted / 未 halted 两态） |

实测：`bash loop/spikes/run_software_checks.sh tests/test_node_story.py` ⇒ **105 passed in 0.67s**
（第二轮基线 82；本轮 +23 条断言）。浏览器 `tests/browser/test_node_detail.py` ⇒ **43 passed in 61.04s**（基线 33）。

> 说明：**"未收尾节点"**（运行未终态、该节点 detail 为空）的「还没有收尾记录，关键数字等它跑完再看」
> 是 SPEC-REV-02 §R1 规定的**另一种状态**（节点确实还没跑完），不属于 R3-08 的 `not_reached`；
> 本轮未改它，浏览器断言只覆盖 `not_reached`/`not_executed` 两种终态。

---

## 4 R3-04：闸门"当时的硬阻断"落账与只读投影

- 写侧（`chunks/gates.py::_resumed`）：`run_dir/decisions/<gate>.json` 的 `records[]` 增
  `hard_block:[{code,title,message}]`（取自本门开启时 `gate_material::<gate>`；缺失 ⇒ `[]`）；
  不改 `gate_decisions` / `gate_decided` 事件既有形状。
- 读侧（`services/contracts.py::gate_entries_view`）：已决策态只从 ledger 最新 record 读；
  ledger 无该键（旧 run）⇒ `hard_block=[]` + note「当时的阻断项未留存（该 run 早于落账）」，
  `counts.hard_block=null`（不写 0 冒充"没有硬阻断"）。
- 断言：`test_flow.py`（drill 全链三闸门 records[-1] 含 `hard_block`，且等于本门 gate_pending 材料快照的 code 列表、
  每条键集恰为 `{code,title,message}`）；`test_node_detail_projection.py`（读侧 + 旧 run 未留存两态）。

drill 全链实测快照：G1 `[I4_CONFLICTS_UNCLEARED]`；G2 `[I3_KOUTOU1_NONZERO, I4_CONFLICTS_UNCLEARED]`；
G3 `[I4_CONFLICTS_UNCLEARED]`。

---

## 5 R3-09：drill 下 submit / 编译节点字段补齐

- `long_jobs.py`：drill `N9_submit.node_finished.detail.cases = 1`；`host_steps.py`：drill `N7.detail.case_count = 1`
  （与 real 路径同字段名）。
- 效果：drill 全链 N9_submit headline「已提交全跑作业 JOB-…，覆盖 1 个用例；流程转入等待作业完成。」；
  N7「1 个用例都编译通过（失败 0）。」（改前是"覆盖用例数未下发"）。
- 断言：`test_flow.py` drill 全链字段存在 + `test_node_story.py` 文案。

---

## 6 R3-11 / R3-12 / R3-13 / R3-14 / R3-15（一致性与清理）

| 项 | 结果 | 断言 |
|---|---|---|
| R3-11 可选下限 | 新 run 才下发的字段登记为 SPEC-02 §10.4.5 **可选下限**（不进 `REQUIRED_FIELDS`）；新 drill 全链全部存在（`null` 也算下发）、旧 run 缺它们不进 `missing_fields` | `test_node_detail_projection.py` 三条 |
| R3-12 字段消费者 | `story.headline_source` 前端消费（结果标题后小字：summary→（原文摘要）/ missing→（未下发））；`gate.entries[].attached[].note` 在浮窗附证据区可见 | 浏览器 2 条 |
| R3-13 死路径 | 删除 `app.js::renderEntryDecisionHint` + 唯一调用 + 死 CSS；另一条线的逐条处置控件保留 | 浏览器反向断言（全仓无残留引用）；`test_web_smoke/test_gate_session` 绿 |
| R3-14 门禁脚本 | `run_software_checks.sh` 仅当调用方未给 `-q/--quiet` 时才加 `-q`（不再 `-qq` 吞汇总行） | `tests/test_software_checks_script.py` 2 条（带 `-q`/不带 `-q` 都出现 "N passed"） |
| R3-15 单一来源 | 新增 `services/node_registry.py`；`node_story.GATE_NODES is node_registry.GATE_NODES`、`node_view.GATE_ID_BY_NODE is node_registry.GATE_ID_BY_NODE` | `tests/test_node_registry.py` 3 条 |

---

## 7 四道门实测（数字为命令输出复制；同一最终工作树）

| 门 | 命令 | 实测 |
|---|---|---|
| 软件层 | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser` | **695 passed, 3 deselected, 1 warning in 154.35s**（`EXIT=0`；收集 698；3 项 `env_layer` 按脚本默认排除并在输出列出；基线 656） |
| 浏览器 | `cd loop && HOME=$(mktemp -d) LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome .venv/bin/python -m pytest -q tests/browser` | **85 passed in 111.88s**（`EXIT=0`；基线 75，+10） |
| kb 自测（schema） | `LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` | **PASS=10 FAIL=0**（`EXIT=0`） |
| kb 自测（N5 可达性） | `LOOP_WORKSPACE=<可写影子> loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py` | **PASS=9 FAIL=0**（`EXIT=0`） |
| 端到端（隔离副本） | 工具副本（rsync 排除 workspaces、`.git`、虚拟环境、日志、state、`.agently`、`.tmp`）+ `LOOP_ENV_ROOT=workspaces/real-env-copy LOOP_WORKSPACE=workspaces/real-env-copy/kb LOOP_PORT=18199 bash spikes/accept_v1_run.sh` | **ALL PASS**：phase 1/2/3/4/4b/5 = **50/27/18/8/8/6 = 117 PASS / 0 FAIL**，六相 `rc=0`，`EXIT=0` |
| 文档 | `python3 doc/audit/check_doc_links.py` | 见 §7.1（同一命令） |

- 端到端收尾：删除隔离工具副本目录与副本环境里 3 个 `.loop_drill` 测试 run
  （`RUN-20261023-221327/221337/221342`）；`RUN-20261015-120626` 夹具保留。
- 软件层必须走 `spikes/run_software_checks.sh`（自建可写影子数据根）：直接 `pytest` 会写只读数据根
  （`OSError: Errno 30`）。kb 自测需 `LOOP_WORKSPACE` 指向可写影子（index/conflicts 拷贝 + baselines 软链）。

### 7.1 文档门

`python3 doc/audit/check_doc_links.py` ⇒ `checked=1788 skipped=22543 historical=857 known_missing=10 env_missing=19 missing=0`，`EXIT=0`。
（`env_missing` 多出的是另一条线本轮改动里的环境侧引用，不在本仓可验证范围；`known_missing=10` 是历史登记项。）

---

## 8 未执行 / 未关闭（必须与结论一起读）

1. **R3-02/R3-05 真机复核未执行**：`:18098` 仍是旧构建（§2）。重启后应复核：
   N1–N9 的 `story.headline`/关键数字；N9 未收尾；N10–N16「本轮没有走到这个节点（运行停在 failed，失败）」；
   N4「逐条处置未留存」；N2 黄条与 offset；`GET /api/runs/{id}/report` 只读报告；N13 只读待确认项。
2. **R3-16 UI_RUNBOOK 未改**：`doc/UI_RUNBOOK.md` 仍是另一条线未提交改动（`git status` 未落），
   按写权互斥不动；其过期段落（如"v1 未提供逐条处置输入控件"）待该线落定后由对应 owner 更新。
3. **R3-18 真实轮验收**：上一轮 real `RUN-20261023-171744` 在 N9 被**外部取消**（21:24:53 failed），
   未到 N16 ⇒ P-13/P-14/P-20/P-21/P-24/P-26…的真机表现本期无法观测；本轮只登记，不伪造。
4. **P-25 live 首次真机验证缺口**：可解析性已由 Host fail-closed 与 d 单测证明，但"live 模型是否稳定
   按新格式产出观测点"要等下一次 real 轮；若长期不满足，需回到裁决 #1 讨论方案 B/C。
5. **旧 run 不回填**：新 story 字段/新 detail 字段/闸门 `hard_block` 只对新 run 生效；历史 run 显示"未下发/未留存"。
6. **`app.js` 删除区与另一条线改动同 hunk**：删的是死函数（`renderEntryDecisionHint`），
   另一条线的逐条处置控件完整保留；review 时按实体区分。
7. **不声称"已合规"**：以上与 [`doc/STATUS.md` §50](../STATUS.md)、[`SPEC-REV-02` §E](../spec/SPEC-REV-02-20261023.md) 同一份。
