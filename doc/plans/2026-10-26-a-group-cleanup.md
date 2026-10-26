# A 组收尾：账本归因、旧界面选项来源、数据根脚本去重（2026-10-26）

> 状态：**已实施**（2026-10-26，切片 A1–A4 全部落地；实测数字见 [STATUS §81](../STATUS.md)）。
> 上游：`doc/STATUS.md` §75–§80 之后仍留的 A 组待办（本会话盘点清单），由人指定「先把 A 组做了」。

## 0 范围与判据

本组只处理**软件仓内可自主关闭**的遗留项，不触碰移动端（已裁决不在功能开发范围）、
不改环境仓、不为通过而放宽任何闸门判据。

| 切片 | 问题（可观察） | 唯一 owner | 落点 |
|---|---|---|---|
| A1 | 「有签名无落账」被归因成"本轮早于落账"；账本"损坏"与"不存在"不可区分 | Host 投影（`services/contracts.py`） | `contracts.gate_entries_view` |
| A2 | 两个可写数据根脚本各写一遍构造逻辑（复制哪些目录、夹具在不在） | Lead（开发入口脚本） | `spikes/provision_dev_workspace.sh`、`spikes/run_software_checks.sh` |
| A3 | `legacy.html` 仍"优先中断载荷快照选项"，还有一张手抄枚举兜底表 | 前端（`web/legacy.html`） | `gateDecisionOptions` |
| A4 | 浏览器门是否并入全量单测门（流程口径未登记） | Lead（流程） | `AGENTS.md` §4、STATUS §81 |

## A1 账本缺失/损坏可分、归因只说事实

**问题**：`_decision_ledger()` 对「文件不存在」与「文件损坏」都返回 `None`，投影于是只能说
"逐条处置未留存"，并把原因写死成「本轮早于处置落账」。周末那轮 `RUN-20261024-002609`
是**签名成功、恢复失败**（`async_load` 指纹不匹配）⇒ 账本没写成，被这句话错误归因。

**判据**（不读源码也能判）：

1. 账本不存在 ⇒ note 含"未落账" + 具体文件路径 + "不存在"，**不含**"早于"、**不含**"不可解析"；
2. 账本不可解析或形状不符 ⇒ note 含"不可解析" + "损坏"，**不含**"不存在"；
3. 账本存在但 `records` 为空 ⇒ note 说"没有记录"，**不含**"不存在"；
4. 以上三种 `entries[].disposition` 全部为 `null`（**不编**逐条处置）。

**实现**：`_decision_ledger()` 改返回 `(doc, status)`，`status ∈ {ok, missing, corrupt, no_run_dir}`；
文案唯一出口 `_ledger_absent_note(gate, status)`。`hard_block` 缺失的旧记录改写为
"当时的阻断项未留存（`decisions/<gate>.json` 的该条记录没有该字段）"，不再声称 run 早于落账。

**回归钉子**：`loop/tests/test_node_detail_projection.py` 的
`test_gate_entries_decided_without_ledger_says_not_retained`（改写）、
`test_gate_entries_corrupt_ledger_is_not_reported_as_missing`（新）、
`test_gate_entries_ledger_without_records_is_explicit`（新）。

## A2 数据根构造只剩一份实现

**问题**：`provision_dev_workspace.sh`（持久副本，含 733 MB 夹具复制）与
`run_software_checks.sh`（一次性影子，夹具符号链接）各自维护一份"带哪些目录、夹具在不在"，
两份口径迟早漂；判据函数重复也违反红线 8 的精神。

**做法**：`provision_dev_workspace.sh` 成为唯一实现，新增三个开关
`--link-fixture`（夹具/baselines 用符号链接）、`--quiet`、`--tolerate-missing-fixture`
（缺夹具降级为 warn，保持旧入口"继续跑、失败如实记录"的行为）；
`run_software_checks.sh` 删掉自己的 `mkdir/cp/ln` 段与 `host.paths` 解析，改为
`DEST=$SHADOW provision_dev_workspace.sh --force --link-fixture --quiet --tolerate-missing-fixture`。

**验证**：`bash spikes/run_software_checks.sh tests/test_software_checks_script.py` → 2 passed；
两种模式各实跑一次（持久副本自检通过后 `--cleanup`，影子根由软件层全套跑通）。

## A3 旧界面不再消费中断快照选项

**问题**：`legacy.html` 的 `gateDecisionOptions()` 顺序是「`material.decision_options`（中断快照）
→ `run_view.gate_options` → 手抄枚举兜底表」。快照恢复后旧选项会盖掉服务端重算值
（第二套判据，红线 8）；兜底表是前端手抄 `kb_lib.GATE_DECISIONS`（红线 4）。

**做法**：只读 `run_view.gate_options`；没有就返回 `[]` ⇒ 面板明说
「服务端未下发决策选项（`run_view.gate_options` 缺失）：本界面不写死枚举 ⇒ 不可提交」，
提交按钮保持禁用。删除 `GATE_DECISIONS_FALLBACK`。

**回归钉子**：`loop/tests/browser/test_legacy_gate_options.py`（受控替身：快照里有选项、
`gate_options` 缺失 ⇒ 零按钮 + 不可提交；下发重算值后才出现按钮）。

## A4 浏览器门：**不并入**全量单测门（登记裁决）

**裁决**：保持单独执行，不进 `run_software_checks.sh` 默认路径。理由：

1. 浏览器门依赖 Chromium（`PLAYWRIGHT_BROWSERS_PATH` + 可写 `HOME`/`TMPDIR`），
   并入会把"软件层可跑"绑到"本机能起浏览器"上；缺件时是**环境缺件**，不能算通过（§2.1-4）；
2. 并入需串行起静态服务器 + 每用例起浏览器，实测把全量门从 ~5.5 min 拖到 20 min+；
3. 两者判据不同（浏览器门验界面行为，单测门验软件行为），混在一个退出码里失败定位变差。

**口径**：四道必备门定义不变；浏览器门是**必备门之外的补充门**。跑法与"何时必须跑"写在
[AGENTS.md §4](../../AGENTS.md)，视口判据见 [WEB_UI_SPEC §10 A10](../spec/WEB_UI_SPEC.md)
（A10 只有视口判据，不含门级命令），实测数字见 [STATUS §81.8](../STATUS.md)。

## 未决 / 遗留

- 决策项文案（失败轮次的 `accept` 是否改名）属产品文案，仍需人裁决（本组不动）。
- 残留 2（drill + API 直给 `entry_decisions` 时选项声明"不需要理由"而 precheck 收下）
  方向是**更严**，维持登记不改。
- 演示夹具"通过形态"仍缺（需一次真实通过轮或 `ENV_ROOT` 写授权，红线 11）。
