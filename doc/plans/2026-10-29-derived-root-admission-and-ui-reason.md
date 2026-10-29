# 计划 · 派生数据根准入 + 「无可用基线」显式原因（B1/B2）

> 日期：2026-10-29。状态：**已实现并验证**（规格先行见 §1；实现 T1/T2 完成；门禁数字见
> [`doc/STATUS.md` §137](../STATUS.md)）。
> 入口：人反馈（截图：8199 看板「选择基线版本 0 个可用 / 1 个，v0（不可用）」）——现象与追问见 §0。
> 契约：[编排规格 §3.1 + §3.1.1](../spec/LOOP_ORCHESTRATION_SPEC.md)（准入第三条候选）、
> [WEB_UI_SPEC §3.1](../spec/WEB_UI_SPEC.md)（无可用项必须给原因）。
> 归属：B1 = Host 确定性判据（`loop/host/baseline.py`，唯一判据）；B2 = 纯展示层（`loop/web/**`）。
> 不触碰：环境仓 `RTL/TB/PKG/TESTLIB`、`kb/tools/**`（冻结）、任何冻结基线的字节。

## 0 现象与归因（2026-10-29 实测）

- 8199 实例（S8f 演示，`LOOP_WORKSPACE=<repo>/.demo-ws`）的 `GET /api/baselines`：
  `valid=false`，`missing` 恰为六件（`rtl_snapshot / allfiles_manifest / cases_freeze /
  conflicts_snapshot / doc_fingerprint / evidence_index`），但同批文件就在
  `.demo-ws/baselines/v0/` 下（`rtl_snapshot.tar` 2,570,240 字节）。
- 原因：manifest 按**环境仓根**书写成 `kb/baselines/v0/...`；数据根被复制到目录名不再是 `kb`
  的位置后，`<root>/<path>` 与 `<root>/../<path>` 双双落空（`baseline.py::_artifact_path`）。
- 同批文件在默认数据根（`ENV_ROOT/kb`）与 `workspaces/real-ws`（新布局 manifest）上
  `valid=true`；`provision_dev_workspace.sh` 产出的 `.dev-ws-*`、`seed-sandbox-workspace.sh`
  产出的 `workspaces/<env>-sandbox` 与 `.demo-ws` 一样是 `valid=false`。
- 人此前「真实走过」的那轮（2026-10-22 real，`workspaces/real-ws` + `workspaces/real-env-copy`）
  数据根是新布局，故不受影响；本次是**派生副本**这一形态暴露出的缺口。
- 页面侧缺口：无 `valid=true` 项时前端把选中值清空（`app.js` 的 `valid.length ? valid[0].id : ""`），
  meta 走「未选择基线」分支，`manifest 不可用 + missing` 的渲染分支**不可达** ⇒ 用户无法自查。

## 1 规格先行（本轮已完成，Lead 写）

| 文件 | 变更 |
|---|---|
| `doc/spec/LOOP_ORCHESTRATION_SPEC.md` | §3.1 第 4 条解析顺序补第三条；新增 §3.1.1（裁决理由、不采用做法、顺序/报错不变） |
| `doc/spec/WEB_UI_SPEC.md` | §3.1 新增「无可用项必须给原因」：渲染首个不可用条目的字段与 `missing`/`errors` |
| `doc/UI_RUNBOOK.md` | §1.2 旧 `kb -> .` 软链做法标为历史兼容（不再需要）；§4.1 增「meta 给原因」说明 |

**可观察行为**

1. 数据根是 `ENV_ROOT/kb` 的派生副本（目录名任意、manifest 写 `kb/baselines/...`）时，
   `GET /api/baselines` 对该副本内的基线返回 `valid=true`，`missing=[]`、`errors=[]`。
2. 前述情形下指纹、身份、边界判据**一条不少**：内容被篡改仍 `valid=false`。
3. 列表无 `valid=true` 项时，配置页 meta 区含「没有可用基线版本」与首个不可用条目的
   `missing`/`errors` 原文，且**不再**只显示「未选择基线」；`#btnStart` 仍不可用。

**不变量**

- 唯一判据：准入实现仍只在 `loop/host/baseline.py`（红线 8）；第三条候选走 R2 同一
  `resolve()` + 允许根判据；`missing` 报**声明路径**原文。
- 顺序不变：字面候选优先，第三条只兜底 ⇒ 既有数据根行为逐字不变（防回归）。
- 只读：准入仍零写入（不改写 manifest、不建软链/临时件）。
- 展示层不判定：界面只渲染服务端 `valid/missing/errors`，不猜路径、不合成原因。

## 2 为什么不是「复制时改 manifest」或「建软链」

- 改字节：派生副本与冻结件（`FIXTURE_IDENTITY.md` 的 md5、基线 444 语义）不再可比；且每多一个
  拷贝脚本就多一处「要记得改」的隐性契约。
- 建软链：仍是人工动作（旧根、新根各一次），目录树出现自环；且已存在的坏根不会自愈。
- 改判据：只有一处实现、一条规则、同一顺序；对已存在的 `.demo-ws`/`.dev-ws-*`/sandbox **立即自愈**。

## 3 切片（两个互不重叠的写域）

| # | 切片 | 落点（写权） | 验收 |
|---|---|---|---|
| T1 | 准入第三条候选 + 先失败用例 | `loop/host/baseline.py`、`loop/tests/test_baseline_admission.py`（owner：`baseline-admission`） | 新增：派生副本（manifest 带 `kb/` 前缀、目录名任意）⇒ `valid=true`；篡改仍 `false`；软链逃逸仍拒；字面优先（两条候选都有时按字面判）；missing 报声明原文；既有 19 条准入用例不改预期 |
| T2 | 「无可用基线」显式原因 + 浏览器用例 | `loop/web/app.js`、`loop/tests/browser/test_setup_baseline_reason.py`（owner：`setup-ui`；新增文件） | 新增浏览器判据 U1–U5（§4）；`test_web_layout` 既有断言（valid 双项、`#btnStart` 可用、无溢出）不回归 |
| T3 | 门禁与数字 | `doc/STATUS.md`（Lead） | 四道门 + 浏览器门 + e2e 实测数字由命令输出复制 |

**写权边界**：T1 只改上述两个 py 文件；T2 只改 `app.js` 与新增浏览器测试文件（**不改**
`index.html`/`app.css`，除非浏览器用例证明必须；不允许动其它 `web/*.js`）。Lead 负责
`doc/spec/**`、`doc/UI_RUNBOOK.md`、本计划、`doc/STATUS.md`。工作树当前干净（`git status` 空）。

## 4 浏览器判据（U1–U5，与 `tests/browser/test_setup_baseline_reason.py` 同名同号）

- **U1** 全部不可用（1 条 `valid=false`）：`#setupBaselineChip` = `0 个可用 / 1 个`；
  下拉项含 `v0（不可用）` 且该 option `disabled`。
- **U2** meta 区含「没有可用基线版本」、`created_at` 值、`rtl_snapshot`（missing 原文）；
  断言**不含**单独成句的「未选择基线」。
- **U3** `#btnStart` 仍 disabled，hint 含「请选择有效基线」。
- **U4** 1280×720 无水平溢出（复用 `test_web_layout.assert_fits` 的判据形态）。
- **U5** 混合列表（1 valid + 1 invalid）：选中 valid ⇒ meta 显示 `manifest 有效`，`#btnStart`
  在项目校验通过后可用（不因不可用条目存在而阻断）。

## 5 门禁计划（按 AGENTS §4）

1. 定向：`cd loop && LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_baseline_admission.py tests/browser/test_setup_baseline_reason.py`。
2. 单测门：`bash loop/spikes/run_software_checks.sh --ignore=tests/browser`（可写影子数据根）。
3. 浏览器门：`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser`（界面改动必须单独跑）。
4. kb/环境层：`bash loop/spikes/run_env_layer_checks.sh --with-kb-selftests`。
5. e2e：`bash loop/spikes/accept_v1_run.sh`（准入路径改动，必须跑）。
6. 文档门：`python3 doc/audit/check_doc_links.py`。

## 6 未决 / 边界

- `drill` 模式按 §3.1 **不读基线资产**（走夹具），本次准入改动对 drill 运行语义无影响；
  界面仍要求选中 `valid=true`，这是展示层既有的启动条件，本轮不动。
- `.demo-ws` 是 gitignored 演示数据：B1 落地后它**自动**变 `valid=true`，不写其字节；
  8199 实例需**重启**才加载新判据（本会话无法重启外部实例，验证用独立端口自起）。
- `clean-ws-20261023` 没有 drill 夹具（`runs/` 空）⇒ 不作为 drill 演示根；演示根仍是
  `ENV_ROOT/kb`（只读纪律下不当草稿本）与派生副本。
