# 独立验证报告 · CASE-OVERRIDE（SPEC-REV-20）终验

> 执行者：verifier（独立验证者，AGENTS §1/§9：**只报告不修改**）。
> 时间：2026-11-02 12:10–12:35（Asia/Shanghai）。工作目录 `<repo>=/home/work/chenjunming/change-impact-loop`。
> 本目录只放验证输出；未修改 `kb/**`、`loop/**`、`doc/**` 任何文件（见 §7 自证）。
> 判定原则：不信任自报数字，关键项自己复跑；命令与输出见同目录 `*.log`。

## 0 结论表

| # | 项 | 判定 | 一句话 |
|---|---|---|---|
| 1 | 冻结目录自测 `_selftest_case_state.py` | **PASS** | rc=0，`汇总：PASS=55 FAIL=0`（与期望逐字一致） |
| 2 | 本轮新增/受影响单测（4 文件） | **PASS** | 字面命令 2 failed（只读 ENV_ROOT 环境缺件）；按 AGENTS §4 用影子数据根 **59 passed, 0 failed** |
| 3 | 红线实验 a/b/c/d（自造数据） | **PASS** | O-2/O-3/revoke 边界全 rc=3 且台账 md5 不变；合法覆写留机器原判；n12/gates md5 不变；I2 生效 |
| 4 | 红线 8「唯一判据」 | **PASS** | 前端零自判、缺投影明说禁用；服务层零写台账、零第二套 I2 判据；唯一判定函数三处复用 |
| 5 | 证据与数字一致性 | **FAIL** | md5 账本 38/38 OK；四道门数字 4/5 逐字相符；**文档门 `skipped` 差 2**、证据索引 3 处与原件不符（详见 §5 缺陷清单） |
| 6 | 文档门 | **PASS** | `check_doc_links.py` rc=0 `missing=0`；`test_doc_links.py` rc=0 **65 passed** |

**总计：5 PASS / 1 FAIL（FAIL 全部是文档/证据层，无行为缺陷；门禁判定不变）。**

---

## 1 冻结目录自测（PASS）

任务书给的字面命令 `cd loop && python3 kb/tools/_selftest_case_state.py` 在本仓不成立
（`kb/` 在仓根、不在 `loop/` 下），实际命令（两种等价）：

```bash
cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -B kb/tools/_selftest_case_state.py
# 或：cd <repo>/loop && python3 -B ../kb/tools/_selftest_case_state.py
```

输出（`01-kb-selftest.log`）：

```
rc=0
汇总：PASS=55 FAIL=0
```

- `[PASS]` 行 55 条；另有 27 条 `[FAIL] …` 行是**被拒路径的 stderr 诊断**（rb 自测把 stderr 也打进来，
  断言本身另有 `[PASS]` 行），与 `raw/s1/00-commands.md` 的说明一致，非断言失败。
- 本机只读 ENV_ROOT 无影响：该自测只写 `tempfile.mkdtemp()`，**不需要**派生副本。
- 另跑四个门的 kb 自测统一入口（`--reuse`，复用派生副本，原 ENV_ROOT 零写入）：
  `01b-env-layer-kb.log` ⇒ `PASS=10 / PASS=9 / PASS=28`、`FAIL=0`、`3 passed, 24 deselected in 6.99s`、
  `[info] 原 ENV_ROOT 零写入（find -newer 命中 0）`，rc=0。

## 2 本轮新增/受影响单测（PASS）

**(a) 任务书字面命令**（`02-target-tests.log`）：

```
cd <repo>/loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q \
  tests/test_n10_cases.py tests/test_case_override_api.py tests/test_case_states_waivers.py tests/test_api_ui_contract.py
=> 2 failed, 57 passed, 1 warning in 8.31s   rc=1
FAILED tests/test_api_ui_contract.py::test_create_run_echoes_project
FAILED tests/test_api_ui_contract.py::test_gate_material_projection_has_diff_entries
E  OSError: [Errno 30] Read-only file system: '…/SimEnv_…/kb/runs/RUN-20261102-120848'
```

两条都是 `POST /api/runs` 要写真实只读数据根（AGENTS §4 明确：缺可写数据根属**环境缺件，不是代码缺陷**；
`raw/s4/00-commands.md` 记录了修复前后同样失败）。与本轮改动无关。

**(b) 按 AGENTS §4 的统一入口（可写影子数据根）**（`02b-target-tests-shadowroot.log`）：

```
cd <repo>/loop && LOOP_LLM_MODE=standin bash spikes/run_software_checks.sh -q \
  tests/test_n10_cases.py tests/test_case_override_api.py tests/test_case_states_waivers.py tests/test_api_ui_contract.py
=> 59 passed, 1 warning in 8.31s   rc=0
```

**判 PASS**（0 failed；字面命令的 2 failed 已定性为环境缺件）。另独立复跑
`tests/browser/test_case_override.py` ⇒ **16 passed in 15.17s, rc=0**（`07b-browser-case-override.log`），
与 S4 自报的 16 一致。

## 3 红线实验（自造数据；PASS）—— 原始输出 `exp/`、`exp2/`、`exp3/`

夹具：自造 `case_states.json` + 同目录 `n10_cases.json`（顺带自造 `n12_report.md`/`gates.json` 做 md5 探针），
**不碰** `kb/runs`、不碰 ENV_ROOT。用例：`tc_pending`（待验+机器判失败）、`tc_machine`（走 I3 合取门槛的
「机器途径通过」）、`tc_ok`（机器 passed=true）、`tc_noreason`（reasons 空）、`tc_nomachine`（台账有、n10 无）。

### 3a O-2/O-3 拒绝 ⇒ 必须 rc=3 且台账 md5 不变

| # | 场景 | rc | md5 前后 | 结果 |
|---|---|---|---|---|
| a1 | `--actor model:x` | 3 | `00777a72…c8515` 不变 | ✅ |
| a1b | `--actor host:x` | 3 | 不变 | ✅ |
| a1c | `--actor chenjunming`（裸名） | 3 | 不变 | ✅ |
| a2 | `--reason "   "`（全空白） | 3 | 不变 | ✅ |
| a3 | 用例不在台账（`tc_absent`） | 3 | 不变 | ✅ |
| a3′ | **用例在台账、但 n10_cases.json 缺该例**（`tc_nomachine`，exp2） | 3 | `8c6539a8…3fd14` 不变 | ✅ |
| a4 | 机器判 `passed=true`（`tc_ok`） | 3 | 不变 | ✅ |
| a5 | 机器 `reasons=[]`（`tc_noreason`） | 3 | 不变 | ✅ |
| a6 | 批量（合规+不合规混合）⇒ 全有或全无 | 3 | 不变 | ✅ |

### 3b revoke 边界（机器途径通过的用例）⇒ rc=3 且台账不变

```
$ case_state.py override --run RUN-20261102-120000 --case tc_machine --actor human:verifier --reason … --revoke
[FAIL] §4-4 用例 'tc_machine' 当前态虽是「已验证通过」，但最近一条覆写记录不是 action="pass"（该通过不是覆写来的）⇒ revoke 拒绝
rc=3  md5_before=00777a72f1a7463d1af1ee36e4fc8515  md5_after=00777a72f1a7463d1af1ee36e4fc8515  MD5-UNCHANGED
```

### 3c 合法覆写（O-1/O-5）与 3d I2 生效（exp3，干净夹具）

```
override rc=0
overrides_len=1  keys=[action, actor, actor_kind, decided_at, machine, prev_state, reason, record_sha256, schema]
action=pass  actor=human:chenjunming  actor_kind=human  prev_state=已修订待验
machine.passed=False  machine.source_path=n10_cases.json  machine.source_md5=49638b3a…b5ba479
machine.criterion="PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致"
machine.reasons=["印记 N6_tc_pending 三向不一致：['value_matches_expected']"]
machine.evidence={'path':'evidence/x_tc_pending_run.log','md5':'d41d8cd9…f8427e','bytes':12}
-- --verify（逐条 record_sha256 + source_md5 复算）rc=0

覆写后 check --json（rc=0）：
ok=True  pending=[]  waived=['tc_pending']  problems=[]
counts={'已修订待验':0,'已退回':0,'已验证通过':2,'未改':0}
ASSERT-OK: waived 含 tc_pending、pending=[]、无「待验」问题、ok=true、state 真变

n12_report.md / gates.json 覆写前后 md5：
e4c1a73afe2e5eb81c3db1f7a10fe158  n12_report.md   （前=后）
6a75606c3bce079358d53d99a696c19a  gates.json      （前=后）
=> N12/GATES-MD5-UNCHANGED
```

**加强项（我自己加的）**：把 `n10_cases.json` 追加一个空格后 `--verify` ⇒ `rc=4`（source_md5 复核真生效），
还原后 `rc=0`。撤销刚签的覆写 ⇒ rc=0、`overrides` 追加成 2 条 `[pass, revoke]`、`waived` 变空（只增不改）。

## 4 红线 8「唯一判据」（PASS）

**服务层 `loop/services/case_override.py`（352 行，逐行读过）**：
- 写盘：`grep -n "open(\|write_text\|write_bytes\|shutil\|os.replace\|json.dump"` ⇒ **0 命中**；
  唯一 `--state-file` 作为参数传给 `kb/tools/case_state.py override`（P.KB_TOOLS）⇒ 台账唯一写者成立。
- 第二套判据：`grep "待验|pending|CASE_PENDING|I2"` ⇒ 只 1 处**文案**（206 行「用例态回到「已修订待验」」），
  无判据代码；前置复用 `contracts.case_override_view`（248–269 行，注释与实现一致）。
- run 状态前置（§4-6）在服务层：`OVERRIDE_WAITING_GATE="waiting_gate"` 来自 `contracts`，未手抄。

**唯一判定函数复用（三处同一实现）**：
`contracts.py::case_override_view` 由 `services/case_override.py:250`（写端点前置）、
`contracts.py:1109`（闸门材料）、`contracts.py:1815`（`run_view`）共用；函数内按 `action` 参数化
（`_override_action_blocked` + `OVERRIDE_ACTIONS`），**没有**第二个 revoke 判据实现。

**前端 `loop/web/app.js`**：
- 四态字面量只出现 **1 次**：`var CASE_PASS_STATE = "已验证通过"`（仅用于选按钮标签「认定通过 / 撤销」）。
- 可签性只消费服务端投影：`overrideBlockedReason()` 先看 `projection.enabled===true`，
  再要求 `ctx.actions[action].available===true`，否则返回原因并 `btn.disabled = true`；
  `projection` 缺失 ⇒ **「服务端未下发可覆写判定 ⇒ 不可提交」**（2895 行区域 + 2904/2907 行两处明说）。
- 前端**不读不解析** `n10_cases.json`（只显示服务端下发的 `reasons` 原文 / `evidence.path`+`md5`）。
- 事件 kind 白名单：`host/progress.py::ALLOWED_KINDS` 含 `case_override`（progress.py:41），
  `tests/test_api_ui_contract.py::test_frontend_event_whitelist_matches_server_authority` 逐项相等（已随 §2 通过）。

## 5 证据与数字一致性（FAIL）—— 缺陷清单见 §5.2

### 5.1 逐项复核结果

| 复核对象 | 期望（文档） | 实测 | 结论 |
|---|---|---|---|
| `doc/evidence/CASE_OVERRIDE_20261102.md5` 逐条 | 38 条可复核 | `md5sum -c` **38/38 OK，rc=0** | ✅ |
| 冻结目录 4 文件 md5（README §1） | 6a43334…/35f9fe9…/da0c47b…/81154bb… | 逐条 `md5sum` **全等** | ✅ |
| 单测门 | `2104 passed, 3 deselected, 1 warning in 273.16s` rc=0 | `raw/s5/01b` **逐字相同** | ✅ |
| kb 自测门 | `PASS=10/9/28`、`FAIL=0`、`3 passed, 24 deselected`、原 ENV_ROOT 零写入 | `raw/s5/01b` 逐字相同；我复跑 `01b-env-layer-kb.log` 同（本次 6.99s） | ✅ |
| 端到端门 | phase 1/2/3/4/4b/5 全 rc=0 ⇒ `=> ALL PASS` | `raw/s5/04b` + `raw/e2e/driver.log` 逐字相同；phase PASS 数 50/27/18/8/8/6 均 FAIL=0 | ✅ |
| 浏览器门 | `199 passed in 200.18s` rc=0 | `raw/s5/05-browser-gate.log` 逐字相同 | ✅ |
| **文档门** | `checked=3380 skipped=47802 historical=857 known_missing=16 env_missing=35 missing=0` rc=0 | 重跑：**`skipped=47804`**，其余逐字相同，rc=0 | ❌ **差 2** |
| §148.2「S4 16 passed」 | 16 passed | `raw/s4/*` 无逐字 `16 passed`；从 `02-required-command.log`（`2 failed, 23 passed`=16+7）可推出；我独立复跑 **16 passed** | △ 数字真、未落盘原件 |
| README §2「kb/** 4 件」在 `raw/s5-our-hunks.diff` | 4 个 kb 文件 hunk | 该 diff 仅 3 个（缺 `kb/README.md`，它在 `raw/s1-kb-frozen-change.diff`） | ❌ |
| README §4 S1「红/绿、17 条 CLI 冒烟」 | raw/s1 内含这些原件 | raw/s1 只有 01/13/14/15/16；绿日志 02/03/08/10 与 CLI 冒烟 07 未归档；07 有 **13** 步、16 有 **8** 步，**全仓无 17 步版本** | ❌ |
| raw/s1/00-commands.md 的日志列 | 索引能点到原件 | 引用 02/03/04/05/06/07/08/09/11/12-*.log（**10 个**）不在 `raw/s1/`（只在 `loop/.logs/case_override/s1/`，gitignored） | ❌ |

### 5.2 缺陷清单（位置 / 判据 / 最小复现 / 期望 vs 实际）

> 全部为**证据-文档层**不一致，不改任何门禁判定；代码行为不受影响。按 AGENTS §9 只报告，请 Lead 决定谁修。

**D1｜`doc/STATUS.md:7174` 文档门 `skipped` 数字与命令输出不符**
- 判据：红线 2「数字一律由命令输出复制」+ 本题「逐字比对」。
- 复现：`cd <repo> && python3 doc/audit/check_doc_links.py | sed -n '4p'`
- 期望：`skipped=47802`；实际：`skipped=47804`（`checked=3380 historical=857 known_missing=16 env_missing=35 missing=0` 全等，rc=0）。
- 备注：该字段是工具自述的**诊断值**（`check_doc_links.py` docstring 第 5 条：「判定只看退出码 + missing」），
  差值可由 `doc/evidence/CASE_OVERRIDE_20261102/README.md`（67 个 skip token）等文档在数字采集后的编辑解释；
  **门禁判定（missing=0）未变**，只需订正数字或注明采集时点。

**D2｜`doc/evidence/CASE_OVERRIDE_20261102/README.md:32-33` 本轮 hunk 覆盖范围不实**
- 判据：证据索引必须能点到宣称的原件（AGENTS §2④/§5.3）。
- 复现：`grep '^diff --git' doc/evidence/CASE_OVERRIDE_20261102/raw/s5-our-hunks.diff | grep kb/`
- 期望：4 个 kb 文件（README §1 表：`case_state.py`、`case_states.schema.json`、`_selftest_case_state.py`、`kb/README.md`）；
  实际：3 个（`kb/README.md` 无 hunk —— 其新增行 `init/set/show/check/override` 不含抽取关键字，
  只出现在 `raw/s1-kb-frozen-change.diff`）。
- 建议改法（供 Lead 决定）：README §2 把那句改成「kb/** 4 件：3 件见 s5-our-hunks.diff、`kb/README.md` 见 s1-kb-frozen-change.diff」。

**D3｜`doc/evidence/CASE_OVERRIDE_20261102/README.md:58` 对 `raw/s1/` 内容的描述不实**
- 判据：同上（证据目录内容必须与描述一致）。
- 复现：`ls doc/evidence/CASE_OVERRIDE_20261102/raw/s1/`（6 个文件）＋
  `grep -c '^###' loop/.logs/case_override/s1/07-cli-smoke.log loop/.logs/case_override/s1/16-cli-smoke-revoke.log`
- 期望：「红/绿、**17 条** CLI 冒烟」；实际：红只有 01，绿只有 13（final），02/03/08/10 未归档；
  CLI 冒烟归档件 `16-…` 只有 **8** 步、工作目录 `07-…` 只有 **13** 步，**没有 17 步的任何版本**。

**D4｜`doc/evidence/CASE_OVERRIDE_20261102/raw/s1/00-commands.md` 索引指向未归档文件（10 处）**
- 判据：归档件必须自洽（`raw/` 是「原样保存的命令输出」）。
- 复现：`grep -o '[0-9][0-9]-[a-z0-9-]*\.log' …/raw/s1/00-commands.md | sort -u` 与 `ls …/raw/s1/` 对差
- 期望：索引里 15 个日志名都能在 `raw/s1/` 找到；实际：缺 02/03/04/05/06/07/08/09/11/12（**10 个**），
  它们只存在于 `loop/.logs/case_override/s1/`（gitignored 运行目录，**不是归档**）。

**△ 备注（未判缺陷，但请 Lead 知悉）**：§148.2「S4 16 passed」在 `raw/s4/` 无逐字原件
（`02-required-command.log` 是 `2 failed, 23 passed` = 16 浏览器 + 7 契约，可推出）；我独立复跑
`tests/browser/test_case_override.py` = **16 passed**，数字为真，只是缺一条逐字落盘件。

## 6 文档门（PASS）—— 原始输出 `06-doc-links.log`、`06b-test-doc-links.log`

```bash
cd <repo> && python3 doc/audit/check_doc_links.py         # rc=0
=> checked=3380 skipped=47804 historical=857 known_missing=16 env_missing=35 missing=0
   （KNOWN-MISSING 16 条与 ENV-MISSING 35 条均为既有登记项，无新增本仓断链；missing=0）

cd <repo>/loop && .venv/bin/python -m pytest -q tests/test_doc_links.py   # rc=0
=> 65 passed in 2.67s
```

## 7 我不声称的东西

1. **没有跑 21 h 真实全跑轮**；本轮只经单测 + 我的自造夹具 + 既有真实轮只读快照级验证，不折算、不宣称 real 通过。
2. **没有重跑全量软件层（2104）与端到端 e2e**：只逐字比对 `raw/s5` 原件；我的独立复跑限于
   §2 的 4 个目标文件（59 passed）、浏览器 `test_case_override.py`（16 passed）、kb 自测门（10/9/28）、
   冻结目录自测（55/0）、文档门两条。
3. **没有验证浏览器门全量 199**（只跑了本轮新增的 16 条）。
4. e2e 的 8098/8099 端口环境事实（8099 被跨沙箱残留监听占用）我未独立复核，按 Lead 登记接受。
5. **未改任何被测文件**（`kb/**`、`loop/**`、`doc/**` 一律未动，包括错别字）；本目录（`loop/.logs/case_override/verify/`）
   之外的写入：仅 `.env-copy` 派生副本（`run_env_layer_checks.sh --reuse` 的既定行为，脚本自证原 ENV_ROOT 零写入）。
