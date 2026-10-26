# AUDIT-20261026-A 组收尾（A1/A2/A3/A4）独立复核

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-26（Asia/Shanghai） |
| 复核者 | 独立 agent（复核者角色，**不是**实现者） |
| 复核对象 | `fc8f61d`（`feat(contracts,web,spikes): A 组收尾 …`）；母本 `a813881` |
| 复核范围 | `loop/services/contracts.py`（A1）、`loop/web/legacy.html` + `loop/tests/browser/test_legacy_gate_options.py`（A3）、`loop/spikes/{provision_dev_workspace,run_software_checks}.sh`（A2）、`AGENTS.md` §4 + `doc/plans/2026-10-26-a-group-cleanup.md`（A4）、`doc/spec/{WEB_UI_SPEC,LOOP_ORCHESTRATION_SPEC}.md`、`doc/STATUS.md` §81 |
| 本轮是否修复 | **否。只登记，不修任何被测文件**（`loop/**`、`doc/spec/**`、`AGENTS.md`、`doc/STATUS.md`、`doc/plans/**` 全部未改；未执行 `git add`/`git commit`） |
| 工作树 | 复核开始前 `git status --short` 为空；结束后仅本报告一个未跟踪文件（`?? doc/audit/AUDIT-20261026-a-group.md`），`git diff --stat` 为空（无任何已跟踪文件改动） |
| 本次唯一写入 | 本文件 `doc/audit/AUDIT-20261026-a-group.md` |

---

## 1 结论

**可接受（阻断项 0 个），但有 3 组「应修」（均为环境门显式性 + 文档数字/小节号）与若干建议。**

- A1 的三种读不到形态**确实分得开**：我用四个 tmp run_dir 直调 `services.contracts.gate_entries_view`，
  note 与实现者声明的判据逐条吻合（含「`ok` 但 `records` 空」不被误判成 missing）。
  三条钉子对真实回归**有判别性**（运行时 monkeypatch 三条回归，分别 1 红 / 3 红 / 1 红；基线 3 绿）。
  产品代码与规格里已无「本轮早于处置落账」这一**断言**（仅剩注释与"不得这样写"的禁止性表述）。
- A3 旧界面**确实断了**两条来源：`legacy.html` 全文件已无 `payload.decision_options` 消费、
  无 `GATE_DECISIONS_FALLBACK`；**旧实现 + 新用例判红**（渲染出「快照里的确认 confirmed」），
  新实现 + 新用例判绿；浏览器全量 **111 passed**。
- A2 委托后**目录集合等价**（持久副本实测 rc=0、737 MB、内容齐），但**丢失了「数据根不存在 ⇒ exit 2」
  的显式失败**，且 `--quiet` 把缺夹具 warn 吞掉 ⇒ 环境缺件可能静默（应修 1）。
- A4 的「四道门定义不变」成立（AGENTS §4 表格未改），但新段落里的成本数字
  「~5.5 min → 20 min+」与实测/同提交 STATUS 自述不符（应修 2）；另有多处小节号错引（应修 3）。
- 四道门里我**实测复现**了：软件层 **967 passed / 3 deselected**、浏览器 **111 passed**、
  端到端 **ALL PASS / 117 断言 / 0 FAIL**、文档 **missing=0**。`kb` 自测**未复现**（本轮未改 `kb/**`）。

---

## 2 环境与限制（先说清楚，避免把环境缺件当缺陷）

- 数据根 `ENV_ROOT/kb` 只读：软件层一律走 `loop/spikes/run_software_checks.sh`（自造一次性影子根），
  不直接全量 `pytest`。
- 沙箱的 `/tmp` 在**每条 bash 调用结束后即不可见**（跨调用不持久）。因此所有破坏性反证都写成
  「单条命令内建临时件 → 跑 → 删」；仓库内不留 `.dev-ws` / `.tmp-*`。
- 破坏性反证**没有改仓库**：A1 用 `/tmp` 里的 pytest 插件运行时 monkeypatch
  `contracts._decision_ledger` / `contracts._ledger_absent_note`；A3 用 `/tmp` 临时树放
  `a813881` 的 `legacy.html` + `fc8f61d` 的新用例。
- 端到端用**仓外数据根**（`/tmp/dev-ws-audit-e2e`，由 `provision --force` 造）+ `LOOP_PORT=18099`，
  跑完服务已停（实测 18099 无响应），不占仓内目录。
- 限制：`kb` 自测未跑；内网/真实模型/真实仿真仍不在本机能力内（与本轮改动无关）。

---

## 3 逐条结论

### 3.1 A1 判据是否真的分得开 —— **通过**（边缘形态 3 条归入建议 S1）

探针（`tmp_path` + `gate_entries_view(gate="G1_diff_confirm", authority={"status":"signed",…})`，
即 `state=decided` 且 `latest is None` 的路径）实测 note 原文：

| 构造 | 实测 note | 判据核对 |
|---|---|---|
| 无 `decisions/` 目录 | `逐条处置未落账（decisions/G1_diff_confirm.json 不存在）：界面只显示整门决策，不从 gates.json 猜` | 含「未落账」+文件路径+「不存在」；不含「早于」「不可解析」✅ |
| 坏 JSON `{not json` | `逐条处置落账不可解析（decisions/G1_diff_confirm.json 损坏或形状不符）：界面不猜，请以现场文件为准` | 含「不可解析」「损坏」；不含「不存在」✅ |
| 形状 `[]` | 同上（corrupt） | 同上 ✅ |
| `{"records": []}` | `逐条处置落账没有记录（decisions/G1_diff_confirm.json 的 records 为空）：界面不猜` | 含「没有记录」「records」；不含「不存在」✅ |
| `run_dir=None` | `逐条处置未落账（定位不到运行目录）：…` | 对应 `no_run_dir`，未冒充 missing ✅ |

四种形态 `entries[].disposition` 全为 `null`（实测 `[None]`），没有编造逐条处置 ✅。

重点核对项「`ok` 但 `records` 空是否可能被错误实现成 missing」：**不会**。`_decision_ledger`
（`loop/services/contracts.py:1171`）在 `isinstance(doc, dict)` 时先返回 `"ok"`，`gate_entries_view`
（同文件 `:1393`）把 `ledger_status` 原样传给 `_ledger_absent_note`（`:1194`）；`"ok"` 分支只有在
「文件能解析成对象、但 `records` 无有效 dict 尾记录」时可达。我另做了 R3 反证（见 3.2），
把这条错误实现灌进去会让新用例判红，说明该分支**有独立钉子**。

`hard_block` 旧记录文案改为「`decisions/<gate>.json` 的该条记录没有该字段」（`:1405`），
实测 note 为 `当时的阻断项未留存（decisions/G1_diff_confirm.json 的该条记录没有该字段）`，
不再声称 run 早于落账 ✅。

**边缘形态（不是本轮阻断，但判据文字没覆盖）**：见建议 S1（`null` 文件、`records` 非列表、非 UTF-8/路径是目录）。

### 3.2 A1 钉子是否有判别性 —— **通过**

用 `/tmp` 插件在 `pytest_configure` 里运行时 monkeypatch（**未改仓库文件**），只跑三条相关用例
（`-k "without_ledger or corrupt_ledger or without_records"`）：

| 回归注入 | 结果 |
|---|---|
| R1：`_decision_ledger` 折回旧形态（missing/corrupt 不分，损坏也返回 `None`） | **1 failed**（`test_gate_entries_corrupt_ledger_is_not_reported_as_missing`），2 passed |
| R2：`_ledger_absent_note` 折回旧文案「逐条处置未留存（本轮早于处置落账…）」 | **3 failed**（三条全红） |
| R3：`ok` 但 `records` 空被错误折成 `missing` | **1 failed**（`test_gate_entries_ledger_without_records_is_explicit`），2 passed |
| 基线（不注入） | **3 passed** |

即：三条钉子分别钉住「状态不可折叠」「文案不可回到猜测性归因」「有文件无记录 ≠ 不存在」。
限制：这是**运行时 monkeypatch**，不等于真实改坏生产代码，但三条回归都直接落在被测函数边界上。

### 3.3 A1 是否引入新矛盾 —— **通过**（历史文档的过期登记点见 §6）

- 全仓 grep `早于处置落账|早于落账`：
  - 产品代码 `loop/services/contracts.py` 只剩注释/docstring（`:1179`、`:1312`、`:1404`），
    且都是"不得这样写"的说明；**没有**任何分支再把这句话当输出。
  - 规格 `doc/spec/LOOP_ORCHESTRATION_SPEC.md:492-494` 是**禁止性**表述（"不得猜原因（例如断言…）"），
    与本轮实现一致。
  - `legacy.html` / `app.js` / 其它前端无此文案。
- 历史文档按「只增不改」保留原文：`doc/STATUS.md:1658` 与
  `doc/plans/2026-10-23-node-panel-*`（4 处）仍写着旧 note 文案/「未留存」。
  它们不构成**现行规格冲突**（现行规格在 `LOOP_ORCHESTRATION_SPEC §10.4.2`），但 `STATUS:1658`
  读起来像仍然有效的验收记录。建议 Lead 在这些旧节加「已被 §81 取代」指针，**不由复核者改**（§6）。

### 3.4 A3 是否真的把「快照优先」与「手抄枚举」都断了 —— **通过**

- 全文件读 `loop/web/legacy.html`：
  - `gateDecisionOptions(gid, view)`（`:364`）只读 `view.gate_options[gid]`；不是数组或为空 ⇒ `[]`。
  - `renderGateButtons`（`:1078`）在 `defs` 空时**不渲染任何 `.dec-btn`**，明说
    「服务端未下发决策选项（`run_view.gate_options` 缺失）：本界面不写死枚举 ⇒ 不可提交。」（`:1080`）。
  - `updateSubmitState`（`:1125`）同样只按 `gateDecisionOptions(gid, state.view).length` 决定
    `#btnSubmit.disabled`。
  - grep `decision_options|GATE_DECISIONS|GATE_DECISIONS_FALLBACK|full_regression|escalate_to_human|milestone_only`：
    **仅剩两处注释**（`:360`、`:361`），无任何读取；`GATE_DECISIONS_FALLBACK` 已不存在。
- 新用例判别性（临时树：`a813881` 的 `legacy.html` + `fc8f61d` 的新用例）：

  ```
  OLD legacy.html + NEW test → 1 failed
    Actual value: 快照里的确认 confirmed
    Aria snapshot: - button "快照里的确认 confirmed"
  NEW legacy.html + NEW test → 1 passed
  ```
  即旧实现确实会渲染**快照**里的选项（不是只渲染 `gate_options`），新用例会判红 ✅。
- 浏览器全量：**111 passed in 114.79s**（我实测，见 §4），说明 A3 未破坏其它界面行为。
- 建议 S2/S3：同屏文案与 app.js 的一处措辞仍与新规格口径不一致；新用例只覆盖 G1。

### 3.5 A2 委托后行为是否等价 —— **部分通过**（1 条应修，1 条建议）

对比 `a813881:loop/spikes/run_software_checks.sh`（下称"旧入口"）与 `fc8f61d` 的两个脚本：

| 行为 | 旧入口（`a813881`） | 现（`fc8f61d`） | 判定 |
|---|---|---|---|
| 数据根不存在 | `REAL_ROOT` 取不到目录 ⇒ `[FAIL] 数据根不存在：…`、**exit 2**（旧 `:36-39`） | 只检查解析结果非空；SRC_ROOT 不存在也继续 | **回归**：见应修 1 |
| 缺 drill 夹具 | `[warn] 缺 drill 夹具轮 …`（总是打印，旧 `:65`） | 由 provision 打印，但 `run_software_checks` 传 `--quiet` ⇒ **warn 被吞** | **回归**（同一应修） |
| 夹具完整性自检（5 个关键件） | 无 | 有；影子模式下降级为 warn | 增强（无害） |
| `runs/` | `mkdir -p` | provision `mkdir -p` | 等价 |
| drill 夹具 | 符号链接 `runs/RUN-20261015-120626` | 同（`--link-fixture`） | 等价 ✅ |
| `baselines` | 符号链接真实只读基线 | 影子=符号链接；持久=完整复制 | 等价 ✅ |
| `index/conflicts/adjudication` | `cp -a` | `cp -a` | 等价 ✅ |
| `FIXTURE_IDENTITY.md` | **不拷贝** | 拷贝 | 差异（无害；只是影子根多一个文件） |
| 失败退出码 | cp 失败经 `set -e` ⇒ 1；前置不满足 ⇒ 2 | provision 失败 ⇒ `run_software_checks` 统一 `exit 2` | 差异（失败细节略降） |
| `--cleanup` / `--force` / `--help` | 各自实现 | 同（新增 `--link-fixture/--quiet/--tolerate-missing-fixture`） | 等价 ✅ |
| 影子根清理 | `rm -rf` | 先 `chmod -R u+w` 再删 | 增强（实测 `chmod -R` 不跟随符号链接，只读源权限未被改：`dr-xr-xr-x` 保持不变） |

实跑证据：
- 一次性影子：软件层全套 967 passed（影子根由 provision `--link-fixture` 造，见 §4）✅
- 持久副本：`DEST=/tmp/dev-ws-audit provision --force --quiet` → **rc=0**，737 MB，
  `runs/RUN-20261015-120626` + `baselines/`（实目录）+ `index/conflicts/adjudication` +
  `FIXTURE_IDENTITY.md` 齐；与 STATUS §81.3 自述一致 ✅
- 缺夹具：`--link-fixture` 无 tolerate ⇒ rc=1；有 tolerate ⇒ rc=0 + `[warn]`（`--quiet` 时不可见）；
  未知参数 ⇒ rc=2；`--cleanup` 对不存在的 DEST ⇒ rc=0（`DEST` 必须用环境变量传，不能当位置参数）。

**e2e 用持久副本的回归风险**：我按 STATUS §81.5 的口径实跑了一次
（`provision --force` 到仓外目录 → `LOOP_WORKSPACE=<该目录> LOOP_PORT=18099 bash spikes/accept_v1_run.sh`），
**ALL PASS，117 断言 / 0 FAIL**，6 个 phase 全 `rc=0`（PASS=50/27/18/8/8/6），
说明"持久副本 + e2e"这条路径未被 A2 破坏。

### 3.6 A4 与四道门口径 —— **有问题（数字），口径本身成立**

- 「四道门定义不变」成立：`AGENTS.md` §4 表格未改；新段落（`:92-96`）明确说"默认不并入上表"、
  "不是第六道必备门"，并要求"改 `loop/web/**` 或界面投影字段时必须单独跑并记入 STATUS"——
  这与 `doc/spec/WEB_UI_SPEC.md`（`loop/web/**` 改动必须跑浏览器用例）不冲突。
- **数字问题（应修 2）**：`AGENTS.md:96` 写"并入后全量门从 ~5.5 min 拖到 20 min+"。
  本轮实测软件层 **168.26 s**、浏览器 **114.79 s**（实现者记录 162.46 s / 115.39 s），
  串行相加 ≈ **4.7 min**；同提交的 `STATUS.md` §81.4 自己写的是"**单门 5 min+**"。
  「20 min+」没有命令输出支撑，触红线 2。
- **措辞歧义（建议 S5）**：标题是「四道门（缺一不算完成）」，正文第一句叫「第五道补充门」，
  下一句又叫「不是第六道必备门」。建议统一成「四道门不变；浏览器门是**补充门**（不是必备门）」，
  避免"第五道 vs 不是第六道"的第一眼矛盾。
- 另：计划 `doc/plans/2026-10-26-a-group-cleanup.md:77-78` 声称"命令与视口要求写在
  `WEB_UI_SPEC §10 A10`"——A10（`WEB_UI_SPEC:735`）只有视口判据，**没有**浏览器门命令，
  也没有"第五道补充门"的登记；口径实际落在 `AGENTS.md §4`。属错引（应修 3）。

### 3.7 文档一致性 —— **部分通过**

抽查（我的命令输出）：

| STATUS §81 声明 | 我的实测 | 判定 |
|---|---|---|
| 软件层 967 passed / 3 deselected / 0 failed（162.46 s） | `bash spikes/run_software_checks.sh --ignore=tests/browser` → **967 passed, 3 deselected, 1 warning in 168.26s**；被排除的 3 条名字与 §81.5 完全一致（`test_archive_e2` ×2、`test_projection_and_frozen` ×1） | ✅ 复现 |
| 浏览器 111 passed（115.39 s） | **111 passed in 114.79s** | ✅ 复现 |
| 端到端 ALL PASS 117 / 0 FAIL（50/27/18/8/8/6） | **117 ok / 0 FAIL**，phase 1/2/3/4/4b/5 全 rc=0，计数 50/27/18/8/8/6 | ✅ 复现 |
| 文档 missing=0（checked=1944 skipped=24560 historical=857 known_missing=10 env_missing=19） | `missing=0 checked=1944 skipped=24570 historical=857 known_missing=10 env_missing=19` | missing/checked 等一致；**skipped 差 10**（诊断值，不判失败） |
| 「较 §78.7 的 965 多 2 条」 | §78.7（`STATUS:3115`）= 965 ✅ | ✅ |
| 「浏览器…较 §75 的 110 多 1 条」 | §75.6 记的是 **108**（`STATUS:2797-2812`）；**110** 出自 §77.6（`STATUS:3006`） | **错引**（并入应修 3） |
| 「规格 `WEB_UI_SPEC §4.4`『中断载荷里的选项只是快照』」 | 该条在 **§5 闸门视图**（`WEB_UI_SPEC:366`）；§4.4 是"右列" | **错引**（并入应修 3） |

`doc/plans/2026-10-26-a-group-cleanup.md` 的 A1–A4 声明都对应到了实现/登记：
A1（`contracts.py` + 3 条钉子）、A3（`legacy.html` + 新浏览器用例）、A2（两个 shell + 实测）、
A4（AGENTS §4 + STATUS §81.4）；§"未决/遗留"三条与 §81.6 一致。
未落地的只是 A4 里那句 `WEB_UI_SPEC §10 A10` 的错引（见上）。

---

## 4 我实际跑过的门（数字来自我的命令输出）

```console
# 1) 软件层（唯一文档化入口；自带一次性影子根）
$ cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser
967 passed, 3 deselected, 1 warning in 168.26s (0:02:48)          # 退出码 0
# 被排除（不是 skip）：
#   tests/test_archive_e2.py::test_guard_compile_only_archives_evidence_readonly
#   tests/test_archive_e2.py::test_guard_archive_is_bounded_and_excludes_guard_log
#   tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run

# 2) 浏览器门
$ cd loop && PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home \
    TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser
111 passed in 114.79s (0:01:54)                                    # 退出码 0

# 3) 端到端（仓外可写数据根，端口 18099）
$ DEST=/tmp/dev-ws-audit-e2e bash spikes/provision_dev_workspace.sh --force --quiet   # rc=0
$ LOOP_WORKSPACE=/tmp/dev-ws-audit-e2e LOOP_PORT=18099 bash spikes/accept_v1_run.sh
=> ALL PASS（phase 1/2/3/4/4b/5 全 rc=0；[ok]=50/27/18/8/8/6，合计 117，[FAIL]=0）  # 退出码 0

# 4) 文档门（仓内无 .dev-ws / 无临时残留时）
$ python3 doc/audit/check_doc_links.py
missing=0 checked=1944 skipped=24570 historical=857 known_missing=10 env_missing=19   # 退出码 0
```

- `kb` 自测：**未复现**（本轮未改 `kb/**`；引用 STATUS §81.5 的"未重跑"登记，不当作通过）。
- 端到端断言总数 117 与 `STATUS §73` 同值，本轮改动未改 e2e 可观察行为。

---

## 5 问题清单（按严重度）

### 阻断（必须修才能算通过）

**无。**

### 应修

**R1 — A2 把「数据根不存在」的显式失败降级成静默（`loop/spikes/run_software_checks.sh:46-48` + `provision_dev_workspace.sh:97-104`）**
- 旧入口（`a813881:loop/spikes/run_software_checks.sh:36-39`）在起 pytest **之前**
  `[FAIL] 数据根不存在：…` + `exit 2`；现在委托时固定传 `--quiet --tolerate-missing-fixture`，
  数据根/夹具缺失只剩一条被 `--quiet` 吞掉的 `[warn]`。
- 实测（[已确证]）：
  ```console
  $ cd loop && LOOP_WORKSPACE=/tmp/definitely-not-a-data-root-xyz \
      bash spikes/run_software_checks.sh tests/test_software_checks_script.py
  [info] 软件层数据根：/tmp/loop-software-XXXX（drill 夹具与 baselines → 真实只读源）
  ...
  2 passed in 5.82s        # rc=0，全程无任何告警
  ```
  旧脚本同条件会在 0 个用例运行前 exit 2。
- 风险：选错/漂移的 `LOOP_WORKSPACE` 下跑**子集**门会拿到绿色退出码；
  与 `AGENTS.md` §4「缺件属环境缺件，不能算通过」的口径相反。建议：保留"数据根必须是目录"的前置检查，
  并让缺夹具的 `[warn]` 不受 `--quiet` 抑制（或 `--quiet` 只压进度、不压 warn）。

**R2 — A4 的成本数字没有命令输出支撑（`AGENTS.md:96`）**
- 「并入后全量门从 ~5.5 min 拖到 20 min+」：本轮实测 168.26 s + 114.79 s ≈ 4.7 min；
  实现者记录 162.46 s + 115.39 s；同提交 `doc/STATUS.md` §81.4 写的是"单门 5 min+"。
  20 min+ 与三者都不符（红线 2：数字一律由命令输出复制）。建议改成实测值或删掉倍数说法。

**R3 — 文档小节号/出处错引（3 处，均可在不改变语义的前提下改对）**
- `loop/web/legacy.html:362`、`loop/tests/browser/test_legacy_gate_options.py:3`、
  `doc/STATUS.md:3275`：把「中断载荷里的选项只是快照」记成 `WEB_UI_SPEC §4.4`；
  实际在 **§5 闸门视图**（`doc/spec/WEB_UI_SPEC.md:366`，章节头 `:352`）。`app.js:2883` 引的是 §5，是对的。
- `doc/STATUS.md:3299`：「较 §75 的 110 多 1 条」——§75.6 记的是 **108**（`:2812`）；
  110 出自 **§77.6**（`:3006`）。
- `doc/plans/2026-10-26-a-group-cleanup.md:77-78`：「命令与视口要求写在 `WEB_UI_SPEC §10 A10`」——
  A10（`WEB_UI_SPEC:735`）只有视口判据，没有浏览器门命令/门级登记；实际落在 `AGENTS.md §4`。
- `doc/spec/LOOP_ORCHESTRATION_SPEC.md:488`：句中说"面板文案据它在**两种**事实之间分开"，
  紧接的三条 bullet 是三种（missing / corrupt / ok 但空），且枚举里还有 `no_run_dir`。
  建议改为"三种情形（另有 `no_run_dir`）"。

### 建议

**S1 — A1 的边缘形态仍会把事实说错（不是本轮引入的崩溃，但判据文字没兜住）**
- [已确证] 文件内容是字面 `null`（合法 JSON、非对象）⇒ 报 **"不存在"**（文件其实在）。
  与新判据"形状不是对象 ⇒ 不可解析/损坏"冲突。
- [已确证] `{"records": "oops"}` / `{"records": ["x"]}` ⇒ 报 **"records 为空"**（不为空，是形状错）。
- [已确证，非本轮引入] 账本路径是目录 ⇒ `IsADirectoryError`；非 UTF-8 字节 ⇒ `UnicodeDecodeError`
  （`_read_artifact` 只捕 `FileNotFoundError`/`JSONDecodeError`），面板拿不到 note 而是 500/异常。
- 建议：`doc is None and error is None` ⇒ corrupt；`records` 非 list ⇒ corrupt；
  把 `OSError`/`UnicodeDecodeError` 收敛到 corrupt。属小切片，不阻塞本轮。

**S2 — A3 同屏文案自相矛盾 + app.js 措辞过期**
- `legacy.html:1059`（`payload` 不是对象时）仍说"材料不可得，**仍可提交决策**（以后端为准）"，
  而同一面板 `:1080` 说"**不可提交**"。该状态可达（`pending_interrupt.payload` 缺失且 gate_options 未下发）。
  行为上按钮是禁用的（`:1125`），但文案会让操作员困惑。
- `app.js:3014` 仍写"服务端未下发决策选项（**gate_options / decision_options** 缺失）"，
  而新规格说两个前端都只认 `gate_options`；建议删掉 `/ decision_options` 以免读者以为快照仍是合法来源。

**S3 — A3 钉子只覆盖 G1**
- 新浏览器用例只构造 `G1_diff_confirm`；旧兜底表同时含 G1/G2/G3。若将来只为 G2/G3 回退
  （或只为某一道门重加快照优先），本用例不会红。建议参数化三道门各跑一遍。

**S4 — A2 委托让软件层门每次执行一次「未禁字节码」的 `kb_lib` import**
- `provision_dev_workspace.sh:78-85` 的解析片段直接 `sys.path.insert` 后 `import kb_lib`，
  没有 `sys.dont_write_bytecode = True`；`loop/host/paths.py:42-43` 明确写"普通 import 会在
  `kb/tools/`（冻结目录）写出 `__pycache__`（实测发生过）"并专门禁了字节码。
- [已确证] 同样的 import 片段在**临时副本**上会重写 `__pycache__/kb_lib.cpython-311.pyc`
  （带 `dont_write_bytecode` 时不留目录）；仓库 `kb/tools/__pycache__/` 下确实存在历史遗留的
  字节码（如 `kb/tools/__pycache__/kb_lib.cpython-38.pyc`，另有两份 311 版旧 .pyc），但**311 版的
  `kb_lib` .pyc 只出现在临时副本里，仓库中并无该文件**。不是本轮新增的代码，但委托把它放到了
  每次软件门的热路径上。
- 建议：解析片段加 `sys.dont_write_bytecode = True`（或 `python -B`）。

**S5 — A4「第五道 / 不是第六道」措辞**
- 建议统一为「四道门不变；浏览器门是补充门（不是必备门），改界面必须单独跑并记 STATUS」，
  避免"第五道 vs 不是第六道"看起来互相否定的第一印象。

**S6 — STATUS §81.5 记录了 `checked/skipped`**
- `doc/audit/check_doc_links.py:24` 明说「判定只看退出码 + missing；checked/skipped 是诊断值，
  不写回文档（见 STATUS §19）」，§19 也把"记录动作本身会改变被扫跨度"列为已发生偏差。
  我实测 `skipped=24570`、记录 `24560`（差 10，missing 与 checked 一致）。
  写完本报告后**同一棵树**再测：`checked=1990 / skipped=24822 / missing=0`（复测 skipped=24823）——只多了一份报告就
  +46 / +252，正是 §19 说的"记录动作本身会改变被扫跨度"。建议只留
  `missing=0`（与 exit=0），不写诊断值；或注明"诊断值、随树漂移"。

---

## 6 已发现但不得由复核者修（交 Lead 处置）

1. 上述 R1/R2/R3、S1–S6 的修复：按 §3 写权归对应 owner（`contracts.py`/`legacy.html` 实现 owner、
   `spikes/**` 开发入口 owner、`doc/STATUS.md`/`doc/spec/**`/`AGENTS.md` 归 Lead）。
2. **历史文档过期登记点**（按「只增不改」保留原文，仅建议加指针，复核者不改）：
   - `doc/STATUS.md:1658`（旧验收记录仍引用"逐条处置未留存（该 run 早于处置落账）"）；
   - `doc/plans/2026-10-23-node-panel-unified-revision-plan.md:189`、
     `doc/plans/2026-10-23-node-panel-revision-kickoff.md:76,197`、
     `doc/plans/2026-10-23-node-panel-revision-round3-impl.md:109-110`、
     `doc/plans/2026-10-23-node-panel-revision-round3-kickoff.md:167`。
   建议在 STATUS 新节或这些旧节加一句"**已被 §81 取代**"，而不是回填旧文。
3. `loop/tests/test_node_detail_projection.py:647` 的 docstring 仍写"早于落账的旧 run"，
   而该用例覆盖的是 `hard_block` **字段缺失**（不是"早于"）；属措辞，实现 owner 可顺手改。
4. 观察（非问题）：`workspaces/real-env-copy/loop/web/index.html` 仍是含
   `GATE_DECISIONS_FALLBACK` 的旧副本（untracked/ignored 的派生副本，不在产品路径）。
   若有人拿它当"新版前端"验收会看到旧行为；是否清理由环境副本 owner 决定。

---

## 7 复核过程的副作用（如实登记）

- 端到端跑过一次，覆盖了 **本地、未入库** 的 `loop/.logs/accept/`（脚本每次启动会截断该日志），
  以及 `loop/state/`、`loop/spikes/.accept_v1_state.json`（均在 `loop/.gitignore`，`git status` 仍为空）。
  这些不是证据文件，未进入任何冻结目录。
- 所有破坏性反证在 `/tmp` 内完成并已删除；仓库无 `.dev-ws` / `.tmp-*` 残留。
- 未执行 `git add`/`git commit`；被测文件一个字节未改。

---

## 8 更正记录

- 2026-10-26 路径引用更正：311 版 `kb_lib` 的 .pyc → 仓库实际存在的 38 版（`kb_lib.cpython-38.pyc`）；结论不变（S4 仍然成立：解析片段未禁字节码会往冻结的 `kb/tools/` 写 `__pycache__`，建议加 `python -B`/`dont_write_bytecode`）。本次仅改本报告正文的路径引用与本节，未改任何被测文件、未 `git add`/`git commit`。
