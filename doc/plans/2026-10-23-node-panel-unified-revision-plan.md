# 节点面板统一修订 · 实施计划与接口契约（2026-10-23）

> **已过期（2026-10-26，由 [`doc/STATUS.md` §81.1](../STATUS.md) 取代）**：本文中"逐条处置未留存
> （该 run 早于处置落账）"、"当时的阻断项未留存（该 run 早于落账）"这类表述已**作废**——
> 投影现按 `missing`（文件不存在）/ `corrupt`（不可解析或形状不符）/ `records` 为空三种事实分开
> 陈述，且**不再猜原因**。本文其余部分按历史记录保留、不回填。


> **上游**：[开工交接提示词](2026-10-23-node-panel-revision-kickoff.md)（用户用法与硬约束）、
> [SPEC-REV-04 §C](../spec/SPEC-REV-04-20261023.md)（P-01～P-35 唯一权威清单）、
> [SPEC-REV-04 §R2](../spec/SPEC-REV-04-20261023.md)（闸门复核 UI 设计已定）。
> **本文件不是新契约**：只把 SPEC-REV-04 已定的行为**落成实现接口**（字段名/形状/文案），
> 让多个 owner 能互不重叠地并行实现。行为冲突以 SPEC-REV-04 为准。
> **状态**：**已实施（2026-10-23）**。四道门实测与未关闭项写 [`doc/STATUS.md` §49](../STATUS.md)，
> 证据见 [`doc/evidence/NODE_PANEL_REVISION_20261023.md`](../evidence/NODE_PANEL_REVISION_20261023.md)。

---

## 0 写权与切片（互不重叠）

| 切片 | 内容 | owner | 写文件 |
|---|---|---|---|
| S1 故事投影 | `story.headline` / `note` / `not_reached` / `not_executed` / `evidence_note` / `status_note` / `status_glossary` / 逐节点 headline 与关键数字 | **story-owner** | `loop/services/node_story.py`、`loop/tests/test_node_story.py` |
| S2 宿主数据面 | 新 detail 字段（N3/N5/N6/N6_apply/N8/N9/N10/N11/N12/N15*/N16/HALT）、闸门逐条处置落账、`node_started` 补齐、N16 结果件、P-14 提示词 | **host-owner** | `loop/workflows/chunks/*.py`、`loop/prompts/node_schemas.py`、`loop/prompts/loop_nodes.yaml`、`loop/tests/test_flow.py` 等受影响单测 |
| S3 服务端闸门/报告投影 | `node_view` 扩展、`contracts.gate_entries_view`、`GET /api/runs/{id}/report` | **Lead** | `loop/services/node_view.py`、`loop/services/contracts.py`、`loop/services/api.py`、`loop/tests/test_node_detail_projection.py` |
| S4 前端 | 结果区 headline/note、状态 chip 释义、未到达/未执行文案、证据入口、闸门二级清单 + 浮窗 + 共享草稿、N12 报告全文视图 | **web-owner** | `loop/web/node-detail.js`、`loop/web/index.html`、`loop/web/app.css`、`loop/web/app.js`（只加桥）、`loop/tests/browser/test_node_detail.py` |
| S5 文档 | WEB_UI_SPEC / LOOP_ORCHESTRATION_SPEC / SPEC-REV-04 §C.2 / STATUS §49 / evidence | **Lead** | `doc/**` |

**并发红线**（交接提示词 §0.5 ④，比原文更严）：

1. 不重启 `:18098`、不 `pkill uvicorn`（其下有真实 N9 作业 `JOB-63f79d482690`）；
2. 不修改 `kb/tools/run_guarded.sh`；不写 `workspaces/s0-ws-20261023/**`、
   `workspaces/s0-work-20261023/{SIMLIB_RUN,uvs.setup}`；不动 `doc/UI_RUNBOOK.md` 与
   `doc/evidence/UI_RUNBOOK_20261023/`；
3. `git` 工作树里已有**另一条线**的未提交改动（`app.js` / `gate-session.js` / `agent_view.py` 等）：
   一律先 `git diff <文件>` 看清，只叠加不回退；`FS_STALE_VERSION` ⇒ re-read 后重做；
4. 本轮不改 `kb/tools/**`、不改环境仓 `RTL/TB/PKG/TESTLIB`、不给面板加任何写动作；
5. 每个 P 项至少一条**可判定断言**；断言只认服务端字段/前端 DOM，不靠"看着顺眼"。

---

## 1 接口契约 A：`story`（S1 产出，S4 消费）

`services.node_story.build_story(node, *, events, detail, purpose, run_status=None, mode=None, gate=None)`

返回（在原 `purpose/steps/key_results` 上**只增不改**）：

```jsonc
{
  "purpose": "…",                      // 不变
  "headline": "结果一句话（必为字符串）",
  "headline_source": "template|summary|missing",
  "note": {"text": "…", "level": "warn|info"} | null,   // 首屏黄条（P-10/P-12/P-29）
  "not_reached": false,                // P-30：运行已终态且该节点无事件
  "not_executed": false,               // P-32/P-33：drill/演示下确实没执行
  "evidence_note": {"text": "…", "kind": "agent_calls|not_executed|in_events|artifact"} | null,
  "status_note": "通过|未通过|真实模型|替身|完整|已确认|…" | null,   // 仅释义，原值仍在 status
  "status_glossary": {"ok": "通过", "fail": "未通过", "live": "真实模型调用", "standin": "替身（非模型结论）",
                       "intact": "完整", "broken": "不完整", "confirmed": "已确认", "ignored": "忽略",
                       "disputed": "有疑义", "accept": "接受", "rework": "返工", "refused": "晋升被拒",
                       "halted": "已终止", "applied": "已写入", "pass": "通过", "waiting": "等待中"},
  "steps": [{"seq","at","kind","status","text"}],       // 形状不变；文案按 P 项改
  "key_results": [{"field","label","value","text","missing"}],  // 逐节点精简（见 §1.2）
  "gate": {...} | null                 // 原样透传 S3 的 gate 块（前端用）
}
```

**留白规则（硬）**：缺字段一律"未下发"；`detail` 为空且运行未终态 ⇒ 不逐项堆"未下发"（沿用现状）；
`not_reached` 时正文不得出现"等它跑完"；失败节点全文不得出现"完成"；正文不出现 `seq`。

### 1.1 逐节点 headline / note / evidence_note（模板必须确定性）

| 节点 | headline（有数据时） | note（黄条） | evidence_note.kind |
|---|---|---|---|
| N0 | `工作目录已准备好：基线 {baseline}，运行模式 {mode}。` | — | — |
| N1 | `快照完成：{manifest.allfiles_entries} 个文件，冻结 {manifest.cases_frozen} 个用例。` | — | — |
| N2 | 内容维度（见 §1.3） | `{unresolved_count} 条需要你确认，到 G1 逐条处置`（warn；0 条不给黄条） | — |
| N3 | `模型说：{digest_summary}`＋`（另有 {n} 条需要你确认）`；无 `digest_summary` ⇒ `模型摘要未下发（旧 run 的 detail 没有摘要；正文在证据 n3_digest.md，面板不打开正文）。` | — | agent_calls |
| N4/N13/N14 | 等待/已决策/未到达三态，见 §1.4 | 等待态把硬阻断逐条写成白话（P-29） | in_events（已决策：`签署记录在 gates.json`） |
| N5 | `必改 {must_change_count} 个用例：{must_change_cases}；另有 {to_check_count} 个待查（可能受影响，需人工确认）。`（`to_check_count` 未下发 ⇒ `另有待查（数量未下发）`） | — | — |
| N6 | `改了 {targets} 个用例：{case}（{n} 处）…；输出校验{通过/未通过}。` | — | agent_calls |
| N6_apply | `{cases} 个用例共 {edits} 处修改已写入沙箱；每条都在原文里唯一命中，改完的文件指纹已记录。` | — | — |
| N7 | `{case_count} 个用例都编译通过（失败 0）。` / `{failed_cases} 个用例编译失败。` | — | — |
| N8 | `复核通过：检查了 {check_count} 项，没有必须修改的地方（第 {cycle+1} 次复核，返工上限 {limit}）。` / `复核不通过：{must_fix_count} 项必须修改（…）。` | — | agent_calls |
| N9 | `全跑{通过/失败}：口径一（日志错误标记行数）{koutou1}，口径二（UVM 报告）UVM_ERROR {UVM_ERROR} / UVM_FATAL {UVM_FATAL}；两套口径都要为 0 才算通过 ⇒ {结论}。` | — | — |
| N9_submit | `已提交全跑作业 {job_id}，覆盖 {cases} 个用例；流程转入等待作业完成。` | — | — |
| N10 | `整轮{通过/未通过}：{逐用例结论摘要}；待裁决 {pending}。`（`cases_table` 缺失 ⇒ `判定未通过（verdict_passed=false）；逐用例原因未下发（旧 run 的 detail 没有这张表）。`） | — | agent_calls |
| N11 | `证据链{完整/不完整}：{cases} 个用例身份四处一致（run_id / 用例名 / 审的 md5 / 跑的 md5），返工请求 {rework_requests_count} 条。` | — | agent_calls |
| N12 | `报告结论：{claimed_verdict 中文}；引用 {ref_count} 条证据（不可解析 {n} 条）；未闭环 {m} 项。` | — | agent_calls |
| N15_select | `本轮 G3={g3 中文}：按受影响子集选出 {count} 个回归用例（{cases}）；{real: 会真跑这 N 个 / drill: 演示模式不真跑}。` | — | — |
| N15 | drill/no-op：`演示模式：不真跑回归。本轮回归集 = {count} 个受影响用例（{cases}）。`；real：`回归跑完：{count} 个用例，通过 {passed}，失败 {failed}。` | — | not_executed（drill） |
| N15_submit | `已提交回归作业 {job_id}，覆盖 {cases} 个用例；流程转入等待。` | — | — |
| N16 | `晋升被拒：{reason 白话}。本次是试运行（dry-run），没有真正落盘。` / `晋升成功（试运行）：…` | — | artifact |
| HALT | `本轮已终止：{detail.reason}。这是合法终点，不是失败。` | — | in_events |

### 1.2 逐节点 key_results（P-09/P-12/P-19/P-24 等；`(field, label)`）

- N1（P-09 只留 2 项）：`manifest.allfiles_entries` 快照文件数 · `manifest.cases_frozen` 冻结用例数。
- N2（P-12 内容维度）：`n2.content.files` 改了几个文件 · `n2.content.hunks` 有几处行级改动 ·
  `n2.content.confirm` 需要人工确认 · `self_check_ok` 自检通过（md5/路由计数/偏移列表**不进关键数字**）。
- N3：`provider` 模型提供方 · `digest_confirmations` 需人工确认条数 · `groups_count` 分组数
  （`offered_segments_empty=true` ⇒ 文案 `0（没有段信息，无法分组——不是没分析）`）。
- N5（P-19）：`must_change_count` 必改 · **`to_check_case_count` 待查（去重用例数；缺失回退 `to_check_count` 条目数）**（索引缺口/索引完整/gate1_rc 移原始记录）。
- N7（P-22）：`case_count` 编译用例（列出名字）· `failed_cases` 失败用例（删掉重复的"全部通过"）。
- N8（P-23）：`check_count` 检查项 · `must_fix_count` 必须修改 · `cycle` 返工轮次（`{n}（上限 {limit}）`）。
- N9（P-24）：`cases` 用例数 · `koutou1` 日志错误标记行数 · `koutou2.UVM_ERROR` UVM 报告 UVM_ERROR ·
  `koutou2.UVM_FATAL` UVM 报告 UVM_FATAL · `identity.consistent` 证据身份一致。
- N10（P-26）：`verdict_passed` 整轮判定（通过/未通过）· `pending` 待裁决项 · `classification.buckets` 失败点位.
- N11（P-27）：`chain` 证据链 · `identity.consistent` 身份一致 · `cases` 用例数 ·
  `rework_requests_count` 返工请求 · `unclosed` 未闭环项（`{n} 条`）。
- N12（P-28）：`claimed_verdict` 报告结论 · `ref_count` 引用证据数 · `refs_parseable_count` 可解析引用.
- N15_select（P-31）：`count` 选中用例 · `g3` G3 决策（中文）· `will_really_run` 本次是否真跑.
- N15（P-32）：`cases` 回归用例（名字）· `will_really_run` 本次是否真跑 · `passed` 通过数（未执行 ⇒ `—（未执行）`）.
- N16（P-34）：`status` 晋升结果（拒绝/成功）· `dry_run` 本次是否真写 · `actor` 触发人.
- HALT（P-35）：`reason` 终止原因.
- 其余节点保持 §R1 表（缺失逐项"未下发"）。

> 行内文案（如 `—（未执行）`）由服务端在 `text` 里给；`value` 保留原值。标签改动不改 detail。

### 1.3 N2 内容维度（P-10/P-11/P-12）

`detail.diffs` 存在时按 `entry_id`（=`id`）分组：主条目 = 有 `diff_hunk` 的条目（否则第一条），
其余同 id 条目为**附证据**。计数口径（服务端确定性，与 P-11 同一口径）：

- `files` = 唯一 `entry_id` 个数（删/增/改分开说，若有 `change` 字段）；
- `hunks` = 主条目里 `diff_hunk` 非空的条数（"处"）；
- `confirm` = **有未决证据的唯一 `entry_id` 数**（与 G1 逐条处置的键同一口径；
  不用 `detail.unresolved_count` 的逐路计数——那个是按比对路数的，会重复计同一文件）。
  N2 黄条里的"N 条需要你确认"用这个数（P-10 的样例：1 个文件 1 条）。
- headline：单文件 + 有行号 + 有偏移 ⇒ `内容有变化：1 个文件改了（{basename}），第 {lines}，偏移 {offset}。`；
  多文件 ⇒ `内容有变化：{files} 个文件改了（{basenames ≤3}…）；其中 {hunks} 处有行级证据，{confirm} 条需要你确认。`；
  `has_change=false` ⇒ `文件内容没有变化。`；
  无 `diffs` ⇒ `差异清单未下发（旧 run 的 detail 没有逐条清单）。`

### 1.4 闸门节点三态（P-15/P-16/P-29/P-30）

输入里 `gate`（§2.4）与 `run_status`：

1. **等待态**（`gate.state="waiting"`）：`headline` = `等待你处理：本轮停在闸门 {1|2|3}（{门中文}）。`；
   N13 追加 `现在不能接受`（当 `hard_block` 非空）；`note.text` = 硬阻断逐条白话，形如
   `I2：有 {n} 个用例改完没验证通过；I3：日志错误标记 {k1} 行 ≠ 0；I4：{n} 条文档/RTL 冲突未清零`
   （代号只作小字附注，正文不得只写代号）。
2. **已决策态**：`headline` = `人已{确认差异清单|接受报告|决定回归策略}（{decision} {中文}），签署人 {actor}，理由：{reason}。`
   （理由缺失 ⇒ `未填写（原记录无理由）`；`decision` 原值必须保留）。G3 的 `milestone_only` 追加
   `（按受影响子集跑回归后晋升，不要求冲突清零）`；`defer` 追加 `（本轮显式终止）`。
   内部词（`human_signed`/`G1_CONFIRMED`/`branch`）不进 headline，只在原始记录。
3. **未到达态**：`not_reached=true`，`headline` = `本轮没有走到这个节点（运行停在 {run_status}）。`

---

## 2 接口契约 B：node detail 新增字段（S3 产出，S4 消费）

`GET /api/runs/{run_id}/nodes/{node}` 返回体在原字段上只增：

```jsonc
{
  "run_status": "waiting_gate|waiting_job|waiting_slot|running|finished|failed",
  "run_terminal": true,                 // run_status ∈ {finished, failed}
  "node_started_present": true,         // 是否有 node_started（P-33 诚实标注）
  "story": { ... §1 ... },
  "gate": { ... §2.4 ... } | null,      // 仅 N4/N13/N14
  "report": {"file":"n12_report.md","available":true,"bytes":12345} | null   // 仅 N12
}
```

### 2.4 `gate` 块（P-17/P-18/P-29；服务端只读投影）

```jsonc
{
  "gate": "G1_diff_confirm",
  "state": "waiting|decided|no_material",
  "cycle": 0,
  "entries_required": true,
  "decision_options": [{"value":"confirmed","label":"差异确认","requires_reason":false}],
  "counts": {"entries": 4, "revision_points": 4, "disposed": 0, "unresolved": 7,
             "unresolved_points": 4,
             "hard_block": 3, "pending_cases": 3,
             "conflicts_open": 72, "conflicts_total": 72},
  "entries": [
    {"entry_id": "RTL/…/pcie_register.v",
     "title": "内容有改动：第 171–172 行，偏移 0x0d04",     // 确定性一句话，不编
     "kinds": ["rtl_file"], "change": "modified",
     "unresolved": false, "unresolved_reason": null,
     "lines": [171,172], "offset": "0xd04", "encoding": "utf-8",
     "has_hunk": true, "diff_hunk": "@@ -168,7 +168,8 @@…",
     "before": null, "after": null, "evidence": "…",
     "attached": [{"kind":"allfile","redundant_of":"RTL/…/pcie_register.v",
                   "before":"5fcc…","after":"18fc…","evidence":"…","note":"整文件指纹，不计入修订点"}],
     "disposition": null}
  ],
  "decision": {"decision":"confirmed","actor":"human:…","actor_kind":"human","human_signed":true,
               "signed_at":"…","reason":"…","history_len":1} | null,
  "hard_block": [{"code":"I2_CASES_PENDING","title":"…","message":"…"}],
  "source": "pending_interrupt|decisions_ledger|none",
  "note": "逐条处置未留存（本轮早于处置落账）"
}
```

- `revision_points` = 唯一 `entry_id` 数（md5-only 附证据**不计**；P-18）；
- `entries` 按 `entry_id` 归并（P-11 同一口径）；`attached[].redundant_of` = 主条目 `entry_id`；
- `disposition` 只在已决策态给（来自 §2.5 落账），等待态为 `null`（由前端草稿计数）；
- 无材料（`n2_diff.json` 缺失 / 非本门阶段）⇒ `state="no_material"` + `note` 说明，不编条目。

### 2.5 逐条处置落账（S2 写、S3 读）

路径 `run_dir/decisions/<gate>.json`（Host 只读产物，只增不改）：

```jsonc
{"schema":"loop/gate_entries","gate":"G1_diff_confirm","run_id":"RUN-…",
 "records":[{"cycle":0,"decided_at":"…","decision":"confirmed","actor":"human:…",
             "reason":"…","entries":{"<entry_id>":{"decision":"confirmed","reason":null}}}]}
```

写入点：`chunks/gates.py::_resumed` 在 `record` 组装后、`node_finished` 前（append `records`）。

### 2.6 报告只读视图（P-28，S3）

`GET /api/runs/{run_id}/report` → JSON：

```jsonc
{"run_id":"…","file":"n12_report.md","path":"…","bytes":12345,"truncated":false,"content":"…"}
```

- 白名单写死 `n12_report.md`（**不接受任意路径**；给 `?path=` 且不等于白名单 ⇒ 403）；
- 大小上限 512 KiB，超出 ⇒ `truncated=true` 并截断（不报 500）；
- 缺失 ⇒ 404；未知 run ⇒ 404；只读、不落盘、不缓存；不越 run 目录。

---

## 3 接口契约 C：host detail 新增字段（S2 产出，S1 消费；只对新 run 生效）

| 节点 | 新增 detail 字段 | 依据 |
|---|---|---|
| N3 | `digest_summary`(str)、`digest_confirmations`(list[str])、`groups_count`(int)、`offered_segments_empty`(bool)；节点 `summary` 改用模型 `summary`（组数降为关键数字） | P-13/P-14 |
| N5 | `to_check_count`(int)、`to_check_cases`(list[str]) | P-19 |
| N6 | `case_edits`([{case, edit_count, edits:[{line, old, new}]}])、`case_edits_source`(="n6_output") | P-20 |
| N6_apply | `case_edits`（与 N6 同源）、`applied_cases`(list[str]) | P-21 |
| N8 | `check_count`(int)、`must_fix_count`(int)、`cycle`(int)、`limit`(int) | P-23 |
| N9 | `koutou1_by_case`({case:int})、`example_line`(str\|null)、`identity`({consistent, mismatches})、`cases_detail`([{case,koutou1,uvm_error,uvm_fatal,passed}]) | P-24 |
| N10 | `cases_table`([{case,koutou1,uvm_error,uvm_fatal,imprints_ok,imprints_missing,passed,reasons}])、`classification`({buckets,既有缺陷,本轮引入,待裁决}) | P-26 |
| N11 | `identity_table`([{case,run_id,case_md5,audit_md5,run_md5,consistent}])、`unclosed`(list[str])、`rework_requests_count`(int) | P-27 |
| N12 | `refs_parseable_count`(int)、`open_items`(list[str])、`cases_summary`(list[str]) | P-28 |
| N15_select | `cases`(list[str] 名字)、`will_really_run`(bool) | P-31 |
| N15 | `cases`(list[str] 名字)、`executed`(bool)、`failed_cases`(list[str])、`will_really_run`(bool) | P-32 |
| N9_submit / N15_submit | 补 `node_started`；`node_finished.refs` 带作业日志（`job_submitted.refs` 同源） | P-33 |
| N16 | `reason_line`(stderr 首行原文)、`result_artifact`(str)、`status` 语义不变；每次尝试落 `run_dir/n16_result.json`（已存在 ⇒ `n16_result.<n>.json`） | P-34 |
| HALT | `reason`(str，白话说终止原因)、`decisions`({gate: decision}) | P-35 |
| 全部闸门 | `gate_decided.detail.entries` = 逐条处置（新 run） | P-15/P-18 |

约束：**不改事件 kind/status**；不删既有字段；旧 run 不回填；`refs` 只加真实存在件。
N16 结果件用 `n16_result.json`（区别于人触发真实晋升的 `promote_result.json`，避免 dry-run
与真实晋升互相覆盖）；S3 投影把两者都列入 `refs`（存在即列）。

P-14（提示词/schema）：`loop_nodes.yaml::n3_digest` ①分组改为有条件（`offered_segments` 空 ⇒ 不分组，
按文件/改动逐条说清楚，并把"缺段信息"写成一条待确认）②`summary` 先写改了什么再写影响 ③`risky_points`
每条"一句风险 + 依据"；`model_steps.n3_digest` 的 input 增 `id`/`offsets`。**只影响新 run**。

---

## 4 前端渲染约定（S4）

- 「结果」区显示 `story.headline`；`story.note` 非空 ⇒ 在其下渲染一行黄条（`.nd-note-warn`）；
  `detail.summary` 原文移入「原始记录」（`.nd-raw`）顶部，并注明"服务端 summary 原文"。
- 状态 chip：`{status} {status_note}`（如 `ok 通过`）；原值必须逐字保留。���骤 chip 同样加释义。
- `not_reached=true` ⇒ 结果区/过程/证据区不显示"等它跑完"，统一显示未到达文案（服务端已给 headline）。
- `evidence_note` 非空 ⇒ 证据区顶部显示它；`kind="agent_calls"` 时**不得**再显示"证据缺失"。
- 闸门区（N4/N13/N14，`gate.state != "no_material"`）：
  1. 首行 `共 {revision_points} 条修订点，已处置 {M} 条`（等待态 M 由共享草稿算）；
  2. 每条一行：勾选框 + `title` + 元信息（文件名 · 行号/偏移 · 变更种类 · 未决徽标）+「查看前后对比 ↗」；
  3. 浮窗（dialog 栈/页内 overlay，宽 ≥ 80% 视口，代码自动换行）：左右两栏 before/after，
     `diff_hunk` 按 `@@ -a,b +c,d @@` 解析成两栏并标行号（纯展示，不判定）；无 hunk 时显示原因
     （旧版正文缺失/非 UTF-8/二进制）与替代证据（行号、md5）；元信息含 offset/encoding/附证据；
  4. 逐条处置单选（已确认/忽略/有疑义）+ 理由输入（忽略/有疑义必填）；
  5. 底部「去闸门视图确认并提交 →」；**不得**在节点面板发 POST；草稿经桥读写 app.js 的
     `state.gateDraft.entryDecisions`（同一 `GateSession` 身份），提交入口仍只有闸门视图表单；
  6. 已决策态：控件只读，显示 `disposition` 与 `decision`（含理由/签署时间）；
  7. `hard_block` 等待态逐条白话展示（P-29），代号作小字附注。
- 报告视图（N12）：`report.available` ⇒ 「查看报告全文」按钮 → `GET …/report` → 只读 `<pre>` 浮窗；
  缺失显示"本轮没有报告文件"。
- 桥（app.js，只加不删）：`window.GateDraftBridge = {required(), options(), rows(), get(id),
  set(id, decision, reason), counts(), openGateView()}`；NodeDetail.open 增可选 `gateBridge` 参数。

---

## 5 验收断言（每个 P 项至少一条）

| 范围 | 断言落点 |
|---|---|
| S1 | `loop/tests/test_node_story.py`：逐节点 headline/note/key_results/status_note/not_reached/not_executed/evidence_note（含 drill 与 real、单文件与多文件 N2、闸门三态） |
| S2 | `loop/tests/test_flow.py` 等：新 detail 字段存在且值来自既有产物；`decisions/<gate>.json` 落账形状；N16 结果件；HALT `reason`；submit 节点有 `node_started`；P-14 提示词含条件分组要求 |
| S3 | `loop/tests/test_node_detail_projection.py`：`run_status`/`gate.entries` 归并与 `redundant_of`/已决策 disposition/报告端点白名单与上限 |
| S4 | `loop/tests/browser/test_node_detail.py`：headline 首屏可见、summary 移入原始记录、chip 释义、闸门清单与浮窗两栏、未处置禁用跳转提示、已决策只读、Esc 只关上层的焦点、报告浮窗 |

## 6 收尾（Lead）

1. 四道门（软件层 standin / 浏览器 / 端到端隔离副本 / 文档门）实测数字**从命令输出复制**；
   18098 真实作业在跑时先做代码+单测，浏览器与 e2e 留到作业结束（交接提示词 §0.5 ④.4）。
2. `SPEC-REV-04 §C.2` 状态改「已修（2026-10-23）」或保留「未定」并写明原因；
   `WEB_UI_SPEC` §4.2.1/§4.4/§6.7、`LOOP_ORCHESTRATION_SPEC` §10.4 同步新字段与只读报告契约。
3. `doc/STATUS.md` 追加 **§49**（§54 已被 Lead 预订）：改了什么/四道门数字/未关闭项；只追加不回填。
4. `doc/evidence/NODE_PANEL_REVISION_20261023.md`（只新增）记录实测证据。
5. **不声称"已合规"**：未拍板项（P-25 系统侧印记、N13/N14 待确认项数据源、P-02/P-05 等）在
   STATUS 与 §C.2 保持可见。

## 7 实施期定稿的接口决策（2026-10-23，只增不改）

1. **N15 detail 的 `cases` 改为用例名列表**（旧 run 仍是计数；story 两种兼容），另加 `case_count` 保留数字。
2. **N5** 新增 `to_check_case_count`（去重用例数，P-19 首屏用）而 `to_check_count` 保留条目数
   （真实数据可能 178 条 / 162 个用例——用户要看的是用例数）。
3. **P-11 归并口径只有一份实现**：`node_story.group_diff_entries` 是唯一实现，
   `contracts._group_diff_entries` **委托**它（AGENTS 红线 8：不许第二套同判据）。
4. **`gate.counts` 增加 P-29 数字**：`hard_block` / `pending_cases` / `conflicts_open` / `conflicts_total`
   （等待态取材料 `hard_block`、`case_states.pending_own`、`conflicts`；已决策态取运行视图同名字段；
   缺材料一律 `null`，不写 0 冒充"没有")。
5. **N16 结果件 = `run_dir/n16_result.json`**（已存在则 `n16_result.<n>.json`），与人触发真实晋升的
   `promote_result.json` 分开；两者都在 run 目录内，refs 都会展示。
6. **G2 报告入口**：闸门材料区只加"查看报告全文（在本轮 N12 面板只读打开）"按钮，打开 N12 面板的只读
   报告视图；不在闸门视图复制第二套取正文逻辑、不新增写动作。
7. **`status_glossary` 覆盖失败与常见状态**（含 `failed`/`halted`/`refused`/`applied` 等），原值逐字保留。

## 8 用户裁决记录（2026-10-23 20:05，逐项确认）

> 9 项一轮问完、逐项拍板。本节的裁决优先级高于本文件其它"未定/暂定"表述。

| # | 议题 | 裁决 | 落地方式 |
|---|---|---|---|
| 1 | **P-25 观测点印记由谁产生** | **A. 作者模型产出观测点** | N6 提示词/schema 增 `observation_points`（`{case, marker, address, offset, expected_value}`，marker `^N6_[A-Za-z0-9_]+$`）；要求每个改动用例打印 `[N6_<检查点>] OK <addr>+<off> <name> = <value>`；Host 校验（每用例至少一条、marker 唯一、marker 必须出现在同用例 edits 里）fail-closed；N6 detail 投影 `observation_points`。只对新 run 生效；N10/`host.evidence` 的期望解析不变 |
| 2 | **N13/N14 待确认项** | **A. 只读清单，不新增逐条处置** | `gate.items = [{id, kind, title, detail, severity}]`；G2 = 阻断项 + 报告未闭环项（N12 `open_items`），G3 = 阻断项 + 未清冲突摘要 + 回归选集用例（`N15_select.cases`，有才列）。无 `disposition`、无勾选、无提交；`gate.state` 增第四态 `read_only`（非 G1 且只有只读清单） |
| 3 | **P-02 偏移条目** | **A. 保持条数** | 关键数字仍"偏移条目 N 条"；具体偏移已在 headline 与原始记录/闸门材料里 |
| 4 | **P-05 模型子事件** | **A. 保持不并入** | `N3_model`/`N3_request` 仍是各自 node；细节看 Agent 工作窗口 |
| 5 | **P-09 关键数字是否只留 2 项** | **A. 保持逐节点精选** | N1 2 项不变；N9/N11 等按节点语义保留；其余进原始记录 |
| 6 | **P-01 三项措辞** | **A. 双写 + real 隐藏 + 后端改称** | drill 说明保留"预置数据（夹具）"；real 不显示 S0 说明行；N0 新 run 的 summary 改"预置数据（夹具）初始化"（旧 run 不回填） |
| 7 | **`:18098` 重启时机** | **A. 作业结束后重启** | 先盯真实作业（`JOB-63f79d482690`）到终态并留证，再重启；重启前不动 18098 |
| 8 | **G2 报告入口** | **A. 一次点击直接弹报告浮窗** | 报告浮窗抽成公共模块 `window.ReportViewer`（N12 面板与 G2 材料共用），G2 材料按钮一次点击直接打开 |
| 9 | **git 提交** | **A. 暂不提交** | 工作树含另一条线未提交改动；等另一条线先落，再由人统一定夺提交 |
