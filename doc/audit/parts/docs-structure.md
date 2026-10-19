# 文档与目录结构审计（task-2 附录 · `docs-structure`）

> **审计员**：auditor-docs（team task-2）　**审计时间**：2026-10-19
> **审计对象**：`/home/work/chenjunming/change-impact-loop`（软件仓）
> **审计性质**：**只读审计**（审计期间未改任何文件；本轮整理仅执行下文标 `[已执行]` 的文档动作）
> **审计时点基线**：本仓 HEAD=`dc7c69e`（13 commits）；`cd loop && .venv/bin/python -m pytest --collect-only -q -p no:cacheprovider` ⇒ **70 tests collected**；
> 终验原始日志 `loop/.logs/accept/FINAL_r1.txt` / `FINAL_r2.txt` 六相 `rc=0`，`[ok]` 计数 50+27+18+8+8+6 = **117**。
> **数据/证据位置**：`ENV_ROOT`=`/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES`（本会话只读）；
> `WORKSPACE_ROOT` = `ENV_ROOT/kb`（`environments.json` 的 `workspace`，第 4 步「数据不搬」已决）。

## 0 方法

1. **导航/一致性**：`find` + `grep` 找入口文档与相互引用；对每个 README/spec 的路径声明做存在性检查（按 `HEAD` 时布局）。
2. **数字**：`git log/rev-list`、`pytest --collect-only`、accept 原始日志逐相计数；不手算。
3. **移动/重复**：与 `ENV_ROOT` 做 `diff -rq`（`loop/`、`kb/tools/`、`kb/schema/`、`doc/agents/`、`kb/README.md`、根 `CHECKPOINT`）。
4. **证据完整性**：迁移件用 `git show HEAD:<old> | md5sum` 与迁移后文件 `md5sum` 逐件比对（32/32 一致，0 不一致）。
5. **行号口径**：下文行号为**审计时点（HEAD `dc7c69e`）**的行号；`doc/spec/**`、`kb/README.md`、`workspaces/README.md`、
   `loop/README.md` 正在由 task-4 改写，行号可能位移；冻结证据（`doc/evidence/demo/**`）内容不再变动。

### 状态图例

- `[已执行]`：本轮（2026-10-19 文档整理）已落地（含 Lead 的 `git mv` 与根 README/AGENTS）。
- `[执行中-他任务]`：已由其它写入任务承接（主要是 task-4：spec / kb / workspaces / loop 四个 README）。
- `[未执行-需授权]`：需跨仓操作、改代码或改冻结证据，本轮明确不做。
- `[保留-设计决定]`：经确认**不应改**（冻结证据语义、旧路径字符串等），由迁移记录或横幅解释。
- `[待核]`：需用户/Lead 判断。

### 本轮执行摘要

| 类别 | 本轮动作 | 结果 |
|---|---|---|
| 根入口 | Lead 新建 `README.md` + `AGENTS.md` | `[已执行]` |
| doc 导航 | 新增 `doc/README.md`、`doc/agents/README.md`、`doc/evidence/README.md`、`doc/history/README.md` | `[已执行]` |
| 结构归位 | `_demo`→`doc/evidence/demo/`；loop/ACCEPTANCE_V1.md→`doc/evidence/`；根 `CHECKPOINT`→`doc/history/`（均 `git mv`） | `[已执行]`（Lead） |
| 迁移记录 | 新增 `doc/evidence/demo/MIGRATION.md`（old→new + md5 未变声明 + 历史路径字符串说明） | `[已执行]` |
| 历史横幅 | `CHECKPOINT` 头部加「已过期」横幅；仅修正 2 处被移动文件路径；正文数字保留为历史值 | `[已执行]` |
| 角色路径口径 | 分析师 / 报告员文首各加 3 行声明（数据根=`WORKSPACE_ROOT`，不是本仓 `kb/`） | `[已执行]` |
| spec / kb / workspaces / loop README | 状态、数字、路径、CLI 契约等偏差 | `[执行中-他任务 task-4]` |
| 跨仓去重、`.gitignore`、代码级缺口 | 见下表 `[未执行-需授权]` | 未做 |

---

## 1 清单（ID 前缀 `DOC-`，按 A–I 分组）

> 表中“行号”为审计时点行号。等级：**高**=会把读者引到错误结论/路径；**中**=契约或数字失真；**低**=清洁度/可读性。

| ID | 等级 | 文件:行号 | 现状 | 应为 / 建议动作 | 风险 |
|---|---|---|---|---|---|
| DOC-A1 | 高 | `(根目录)` | 无 README；唯一根级 md 曾是过期 CHECKPOINT | `[已执行]` 根 `README.md` 已建：定位/三根/快速开始/文档读法/红线；`AGENTS.md` 已建 | 中 |
| DOC-A2 | 中 | `doc/` | 无索引，spec 三件仅靠 loop/kb README 零散链到 | `[已执行]` 新增 `doc/README.md`：spec/agents/evidence/history/audit/STATUS 索引 + 阅读顺序 + 纪律 | 中 |
| DOC-A3 | 中 | `kb/README.md`:1-10 | 不链 loop/README、workspaces/README、ENV_PLUGIN_SPEC，未提三根 | `[执行中-他任务]` 加 §0「三根与数据位置」并链 `doc/spec/ENV_PLUGIN_SPEC.md`、`workspaces/README.md` | 中 |
| DOC-A4 | 低 | `loop/README.md`:1-8 | 不链 kb/README、workspaces/README | `[执行中-他任务]` §1/§2 补导航链接 | 低 |
| DOC-A5 | 低 | `workspaces/README.md`:1-23 | 无出链，不链 environments.json / ENV_PLUGIN_SPEC | `[执行中-他任务]` 加双向链接 | 低 |
| DOC-A6 | 中 | doc/agents/_demo/（32 文件） | 全仓 grep 仅自身命中，无入口文档引用；与角色定义混放 | `[已执行]` 已迁 `doc/evidence/demo/`；`doc/agents/README.md`、`doc/evidence/README.md` 建索引 | 中 |
| DOC-A7 | 低 | `doc/spec/*.md` | 互链不全（CHANGE 不链 ENV/LOOP；ENV 不链另两件） | `[已执行]` 由 `doc/README.md` §2 统一索引；各文件头「相关规范」由 task-4 决定 | 低 |
| DOC-B1 | 高 | `doc/spec/ENV_PLUGIN_SPEC.md`:6-8 | 头部仍写「根解析拆分尚未实现…本仓还不能独立运行」 | `[执行中-他任务]` 改为「第 3 步已完成（三根 + 零配置）；数据未搬（§7）」 | 高 |
| DOC-B2 | 中 | `doc/spec/ENV_PLUGIN_SPEC.md`:40-45 | §2「目标布局」把 `workspaces/<env-id>` 画成本仓数据目录 | `[执行中-他任务]` 标注「目标布局；当前 workspace 指向 ENV_ROOT/kb」 | 中 |
| DOC-B3 | 中 | `doc/spec/ENV_PLUGIN_SPEC.md`:93 vs `:140` | §5「仍未做第 4 步」vs §7「第 4 步暂不执行」 | `[执行中-他任务]` §5 第 4 步标「不执行（决定见 §7）」，第 5 步标「待做」 | 中 |
| DOC-B4 | 高 | `doc/spec/ENV_PLUGIN_SPEC.md`:20,27 | 声称最高优先级 `--env-root/--workspace`，代码中无此参数（`kb_lib` 只认 env var + 注册表） | `[执行中-他任务]` 删除该优先级，或补 CLI 并加测试；不得留假契约 | 高 |
| DOC-B5 | 低 | `doc/spec/ENV_PLUGIN_SPEC.md`:157 | `[待核]` kb/README 待按新布局重写 | `[执行中-他任务]` 随 DOC-C1…C7 完成后关闭 | 低 |
| DOC-B6 | 中 | `doc/spec/LOOP_ORCHESTRATION_SPEC.md`:3 | 「P0 设计契约 v0.1（草案，实现前评审）」但 P0 已实现并验收 | `[执行中-他任务]` 改为「v0.1 · 已实现（P0）」+ 验收链接 | 中 |
| DOC-B7 | 中 | `doc/spec/LOOP_ORCHESTRATION_SPEC.md`:314-323 | §11 A1–A10 全部 `[ ]`，与已验收状态相反 | `[执行中-他任务]` 逐条勾选并注对应测试/ACCEPTANCE 相 | 中 |
| DOC-B8 | 中 | `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`:3 | 「新设计 v0.2（草案，待评审）」但 N0–N16 已落地 | `[执行中-他任务]` 改为「v0.2 · 已实现（业务契约）」 | 中 |
| DOC-B9 | 中 | `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`:7 | 「当前仓库即第一基线」——拆仓后本仓是软件仓 | `[执行中-他任务]` 「第一基线 = ENV_ROOT；本仓为软件仓」 | 中 |
| DOC-B10 | 低 | `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`:265-277 | §10 第一阶段 6 项无完成标记；第 6 项只做到一半（自愈在包装层 K2；`run_tc.py` 未接） | `[执行中-他任务]` 标 ✅/⚠️ 并注偏差 | 低 |
| DOC-B11 | 低 | `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`:284 | §11 未决 #2「doc/ 与 kb/ 纳入 git 授权」已解决 | `[执行中-他任务]` 标「已解决」 | 低 |
| DOC-C1 | 高 | `kb/README.md`:15-58 | §1 目录树把 index/conflicts/baselines/adjudication/runs 画成 `kb/` 子目录（本仓 kb/ 只有 README/schema/tools） | `[执行中-他任务]` 拆两棵树：本仓 `kb/`（软件）+ `WORKSPACE_ROOT`（数据） | 高 |
| DOC-C2 | 中 | `kb/README.md`:60-70,79-93 | 写权表 / 节点↔脚本表的产物路径仍是 `kb/index`、`kb/baselines`、`kb/runs` | `[执行中-他任务]` 统一 `<WORKSPACE>/…` 并注明由 environments.json 决定 | 中 |
| DOC-C3 | 中 | `kb/README.md`:218-242,251 | §5 用法不提三根/注册表；示例 `kb/runs/<run_id>`；红线 4 写 `kb/baselines/**` | `[执行中-他任务]` 加「路径解析」说明 + WORKSPACE 前缀 | 中 |
| DOC-C4 | 低 | `kb/README.md`:4 | 引用 `CHECKPOINT-20261015-1123.md`（仅存在于 ENV_ROOT） | `[执行中-他任务]` 写 `$ENV_ROOT/…` 或链 `doc/history/` | 低 |
| DOC-C5 | 中 | `kb/README.md`:5-6 | 「本目录只新增、不改已定稿基线资产（RTL/…doc/spec/…）」——这些资产已不在本仓 kb/ | `[执行中-他任务]` 按三根重写（本仓只读软件资产，被守卫资产在 ENV_ROOT） | 中 |
| DOC-C6 | 中 | `workspaces/README.md`:3 | `environments.yaml`（文件不存在；提交 994ce54 已改名） | `[执行中-他任务]` → `environments.json` | 中 |
| DOC-C7 | 高 | `workspaces/README.md`:7-13 | 树声称数据落在 `workspaces/<env-id>/{index,…}`；实际 workspaces/ 只有 README+.gitkeep，数据在 ENV_ROOT/kb | `[执行中-他任务]` 改「目录约定 + 当前数据暂存 ENV_ROOT/kb（§7 决定）」 | 高 |
| DOC-C8 | 低 | `workspaces/README.md`:12,19-23 | `runs/ # … kb/runs/<run_id>/**` 两层路径混写；「数据默认不入 git」与空目录现状不符 | `[执行中-他任务]` 改 `<WORKSPACE>/runs/…` + 条件化表述 | 低 |
| DOC-C9 | 中 | `loop/README.md`:74 | 「`app.py` 相关入口见 services/api.py:main」——loop/app.py 不存在 | `[执行中-他任务]` 改为「`run.sh` → `uvicorn services.api:app`；手工入口 `main()`」 | 中 |
| DOC-C10 | 中 | `loop/README.md`:22-23 | 冻结清单未区分三根，漏 `kb/schema`、`SIMLIB`、`LOG` | `[执行中-他任务]` 按 `host/paths.py:93-106/160-162` 重写 | 中 |
| DOC-C11 | 低 | `loop/README.md`:192,198-199 | `kb/baselines/`、`kb/adjudication/*.md` 数据路径 | `[执行中-他任务]` → `<WORKSPACE>/...` | 低 |
| DOC-C12 | 中 | `loop/README.md`:243,269-270 | drill 夹具 kb/runs/RUN-…、真实 `kb/baselines/`、`kb/baselines/v0/` | `[执行中-他任务]` → `<WORKSPACE>/runs\|baselines/...` | 中 |
| DOC-C13 | 中 | `loop/README.md`:247-248 | 「运行目录都是 `kb/runs/<run_id>`…**无环境变量可覆盖**」——`run_dir` 已走 `kb_path`→WORKSPACE_ROOT，可被覆盖 | `[执行中-他任务]` 改为「WORKSPACE_ROOT/runs/…；根由 $LOOP_WORKSPACE/注册表决定」 | 中 |
| DOC-C14 | 中 | `doc/spec/LOOP_ORCHESTRATION_SPEC.md`:19-20,257,310 | 引用 doc/spec/evidence/…（旧布局）、`REHEARSAL_REPORT.md`、kb/runs/RUN-…（均只在 ENV_ROOT） | `[执行中-他任务]` 加「以下路径相对 ENV_ROOT/WORKSPACE」注 | 中 |
| DOC-C15 | 高 | `doc/agents/sim-env-分析师.md`:49,60-65,72,152,177；`sim-env-报告员.md:50,60-70,76,92,94,112,161,184` | 写权/输入路径写作 `kb/runs\|conflicts\|index`，照做会找不到（本仓无这些目录） | `[已执行]` 两文件文首各加 3 行「路径口径」声明（数据根=WORKSPACE_ROOT）；正文职责未动 | 高 |
| DOC-C16 | 低 | `doc/evidence/demo/README.md`（原 doc/agents/_demo/README.md）`:1,35` | 正文仍写 doc/agents/_demo/… 历史路径 | `[保留-设计决定]` 冻结证据不改写；由 `doc/evidence/demo/MIGRATION.md` §4 统一解释 | 低 |
| DOC-C17 | 高 | doc/history/CHECKPOINT-20261016-1001.md（原根 `CHECKPOINT-20261016-1001.md`）全篇 | 引用 `kb/index\|conflicts\|baselines\|runs`、`doc/spec/evidence` 等旧仓路径，且放在根目录会被当现状 | `[已执行]` 已迁 `doc/history/` + 顶部「已过期」横幅（相对 ENV_ROOT 声明）；2 处 loop/ACCEPTANCE_V1.md 改为 `doc/evidence/ACCEPTANCE_V1.md`；其余正文不动 | 高 |
| DOC-C18 | 低 | `doc/evidence/ACCEPTANCE_V1.md`（原 loop/ACCEPTANCE_V1.md）`:31,175,176` | `kb/baselines/`、`kb/adjudication/` 数据路径 | `[保留-设计决定]` 证据冻结（路径经 WORKSPACE 解析仍正确）；在 `doc/evidence/README.md` 统一说明 | 低 |
| DOC-D1 | 中 | `doc/history/CHECKPOINT-20261016-1001.md`:54-55,79,130,237-238（行号迁移前） | 68 单测 / 116 断言 | `[已执行]` 横幅声明为历史值（当时实测）；不改成 70/117，避免篡改历史件 | 中 |
| DOC-D2 | 中 | `doc/spec/ENV_PLUGIN_SPEC.md`:74-75,84-85,142 | 68/68、69/69、116 断言 | `[执行中-他任务 task-4]` §4 基线改 **70 collected / 117 断言**（当前执行结果以 `doc/STATUS.md` §2 为准：本会话受 ENV_ROOT 只读限制为 67 passed / 3 failed，非业务回归） | 中 |
| DOC-D3 | 中 | `loop/README.md`:95,238,259 | 116/116、55 项、同句「117 断言」+「116/116」 | `[执行中-他任务]` 统一 70 项 / 117 断言 | 中 |
| DOC-D4 | 中 | `loop/README.md`:158,162-170；`doc/evidence/ACCEPTANCE_V1.md`:6-7 | 声称「7 个缺陷」，ACCEPTANCE §3 实有 9 条（01…07 + 06c + 08） | `[执行中-他任务]` loop/README 表补 2 行；ACCEPTANCE 属冻结证据 `[未执行-需授权]`，建议以勘误/复验件补 | 中 |
| DOC-D5 | 中 | `doc/history/CHECKPOINT-20261016-1001.md`:75 | HEAD=`9f56193`（ENV_ROOT 当时的 HEAD） | `[已执行]` 横幅写明「ENV_ROOT 9f56193 / 本仓 dc7c69e」 | 中 |
| DOC-D6 | 中 | `doc/history/CHECKPOINT-20261016-1001.md`:62-64,217-219 | 「环境自带 3 个既有角色」；实为 4 个（作者/执行/检查/回归守护）+ 新增 2 = 6 角色（7 个 md 中另 1 个是开工提示词） | `[已执行]` 横幅只声明历史；`doc/agents/README.md` 已给出正确分类（4+2+1 提示词） | 中 |
| DOC-D7 | 低 | `doc/history/CHECKPOINT-20261016-1001.md`:76-77 | 「工作树 52 项」是 ENV_ROOT 当时状态；现 ENV_ROOT 为 53 项 | `[已执行]` 横幅声明为历史值；不再维护 | 低 |
| DOC-D8 | 无 | `doc/spec/ENV_PLUGIN_SPEC.md`:3 | 「历史按 5 个提交重放」 | `[保留-核对无误]` 本仓首 5 提交 = `f3097cb…41bd213`，与实际一致 | 无 |
| DOC-E1 | 中 | `.gitignore`:12-14,16-18（审计时） | 注释指 `kb/FIXTURE_IDENTITY.md`、规则 `kb/runs/` 与 doc/spec/evidence/…/sandbox/（旧布局）——本仓均不存在（在 ENV_ROOT）；注释体积 157MB 实测 225MB | `[已执行-他任务]` 已删除两条残留规则与旧注释；`workspaces/*/` 规则保留并更新注释 | 中 |
| DOC-E2 | 低 | `.gitignore`:20-23（审计时） | `workspaces/*/` 规则可用，但注释「拆仓后新增」与「数据不搬」现状不符 | `[已执行-他任务]` 注释已改为「当前数据仍在 ENV_ROOT/kb；若将来迁入 workspaces/ 则忽略」 | 低 |
| DOC-E3 | 低 | `.gitignore`:2-6 vs `loop/.gitignore`:1-8 | 两套忽略规则重复 | `[未执行-需授权]` 保留一套或加主从注释（根规则已覆盖 loop/.gitignore 的大部分项） | 低 |
| DOC-E4 | 低 | `loop/spikes/snap.json`（被跟踪） | 运行时快照，由 `loop/spikes/spike_interrupt.py`:36,43 写读，却入库 | `[已执行-他任务]` 已从索引删除（`git rm --cached` 效果）并加入 `.gitignore` | 低 |
| DOC-E5 | 低 | `kb/tools/__pycache__/*.pyc`（工作树） | 冻结目录内出现字节码，与 `loop/host/paths.py`:37「不许写 .pyc」纪律冲突 | `[未执行-低优先]` 清理；CLI 跑 kb 自测时设 `PYTHONDONTWRITEBYTECODE=1` | 低 |
| DOC-F1 | 高 | doc/history/CHECKPOINT-20261016-1001.md（原 `CHECKPOINT-20261016-1001.md`） | 拆仓前状态快照放在根目录，会被当现状 | `[已执行]` `git mv` → `doc/history/`；加「已过期」横幅（ENV HEAD 9f56193 / 本仓 dc7c69e；路径相对 ENV_ROOT；数字为历史值；现状看 doc/STATUS.md） | 高 |
| DOC-F2 | 中 | `ENV_ROOT/CHECKPOINT-20261016-1001.md` | 与迁移前根副本逐字相同（`cmp` 通过），两仓各一份 | `[未执行-需授权]` 单一权威（本仓 `doc/history/`），ENV_ROOT 留指针或反之 | 中 |
| DOC-F3 | 低 | `doc/history/CHECKPOINT-20261016-1001.md`:190-245 §10 | 迁移分析已被 ENV_PLUGIN_SPEC §7「不搬」决定取代 | `[已执行]` 横幅指向 §7；正文保留（历史决策价值） | 低 |
| DOC-G1 | 中 | `doc/evidence/demo/`（原 doc/agents/_demo/，32 文件） | 演练产物与角色定义混放 | `[已执行]` 整目录 `git mv` → `doc/evidence/demo/`（内容 32/32 逐字节未变） | 中 |
| DOC-G2 | 低 | `doc/evidence/demo/README.md`:1,35 | 自述路径仍是旧 doc/agents/_demo/… | `[保留-设计决定]` 冻结证据不重写；`MIGRATION.md` §4 给出换算规则 | 低 |
| DOC-G3 | 中 | `doc/evidence/demo/guard/T4_artifacts_md5.txt`:4 等 28 个文件 | 证据内记录旧路径字符串（含 md5 记账语义） | `[已执行]` 新增 `doc/evidence/demo/MIGRATION.md`：目录级 + 关键件映射、md5 未变声明、历史字符串说明、校验命令 | 中 |
| DOC-G4 | 低 | `doc/agents/开工提示词_用例生成.md` | 非角色定义，与角色混放 | `[已执行]` **保留原位**（ENV_ROOT/doc/AGENTS.md §7 冻结引用，移动会断链）；由 `doc/agents/README.md` §2 标注分类 | 低 |
| DOC-G5 | 中 | `doc/agents/` | 无 README 说明三类内容（6 角色 / 1 提示词 / 演练产物） | `[已执行]` 新增 `doc/agents/README.md`：角色表 + 提示词说明 + 演练已迁出 + 路径口径 | 中 |
| DOC-G6 | 中 | `ENV_ROOT/doc/agents/` | 与本仓 `doc/agents/` 逐字相同（含 `_demo` 32 件） | `[未执行-需授权]` 单归属（软件仓），ENV_ROOT 留指针 README | 中 |
| DOC-H1 | 中 | `doc/evidence/ACCEPTANCE_V1.md`（原 loop/ACCEPTANCE_V1.md） | 一次性验收报告混在代码层目录 | `[已执行]` `git mv` → `doc/evidence/`；`doc/evidence/README.md` 建索引；**残留引用由 task-4 更新**：`doc/spec/ENV_PLUGIN_SPEC.md`:91、`loop/README.md`:95,158,259（doc/history/CHECKPOINT 两处已改） | 中 |
| DOC-H2 | 中 | `doc/evidence/ACCEPTANCE_V1.md`:6-7 | 「7 个真实缺陷」vs §3 九条 | `[未执行-需授权]` 证据冻结：不改原件；建议新增勘误/复验件或在 `doc/evidence/README.md` 索引中注明「正文旧称 7 条，实为 9 条」 | 中 |
| DOC-I1 | 高 | `ENV_ROOT/loop/`（13 文件与本仓不同）、`ENV_ROOT/kb/tools/`（8 文件不同）+ py3.8 pycache | 拆仓后 ENV_ROOT 仍留旧软件副本且已分叉（旧 README 仍描述旧布局） | `[未执行-需授权]` 旧副本降级为指针（README 指向本仓），避免第二套可执行代码 | 高 |
| DOC-I2 | 低 | `kb/tools/kb_lib.py`:164 | `WORKSPACE_PARTS` 不含 `adjudication`（两份 README 都把它列为数据目录） | `[未执行-需授权]` 若必需则加入；否则在 README 注明可缺省 | 低 |
| DOC-I3 | 低 | `kb/tools/run_guarded.sh`:49 | 注释「必须由 LOOP_ENV_ROOT 给出」，实际 56-62 行会回落 kb_lib/注册表 | `[未执行-需授权]` 注释改为「$LOOP_ENV_ROOT → kb_lib（注册表）→ 旧布局回落」 | 低 |
| DOC-I4 | 中 | `loop/README.md`:72-97 | 目录树缺 `host/model_provider.py`、`prompts/`、`SETTINGS.yaml`、`requirements.txt`、`pytest.ini` | `[执行中-他任务]` 补全树或标注「节选」 | 中 |
| DOC-I5 | 低 | `kb/README.md`:259-263 vs `:267,311` | §7 变更记录只有 1 行，后面两段「变更登记」未入表 | `[执行中-他任务]` 并入 §7 或把 §7 改为索引 | 低 |
| DOC-I6 | 低 | `loop/spikes/` | 可复跑验收装置（accept_v1*、verify_live_*）与一次性 spike 混放 | `[未执行-低优先]` 验收装置移 loop/acceptance/（需同步 README/ACCEPTANCE 命令） | 低 |
| DOC-I7 | 中 | `loop/host/paths.py`、`loop/services/api.py`:48-64 | `check_env()`/`check_workspace()` 与 `/api/health.plugin_missing\|workspace_missing` 在单测与 accept_v1 中均无断言；ENV_PLUGIN_SPEC §4「向后兼容」门无自动化入口 | `[未执行-需授权]` 加单测：指错 workspace ⇒ `workspace_missing` 非空；旧布局回落用 tmp 目录验证 | 中 |
| DOC-I8 | 中 | 全仓文档 | HEAD/单测/断言/门状态分散在 6 个文件，已出现 4 种读数 | `[已执行-Lead]` 已建 `doc/STATUS.md` 作唯一数字源（本会话：HEAD `dc7c69e`、70 collected；执行环境限制见其 §3）；本目录各 README 与审计附录均链它 | 中 |
| DOC-I9 | 低 | `workspaces/.gitkeep` | README 已跟踪即可保留目录，`.gitkeep` 冗余 | `[未执行-低优先]` 可删 | 低 |

---

## 2 未执行项（需授权/他任务，汇总）

1. **跨仓去重**（DOC-F2 / DOC-G6 / DOC-I1）：ENV_ROOT 仍留旧软件与文档副本，且已与本仓分叉；
   需环境仓写入授权，把旧副本降级为指针。
2. **`.gitignore` 纠偏**（DOC-E1…E3）：本仓 `.gitignore` 不在本轮写范围，需对应 owner 处理。
3. **代码级/测试级缺口**（DOC-I2 / DOC-I3 / DOC-I7）：属 kb/loop 代码写权，审计只登记。
4. **冻结证据的两处旧称**（DOC-D4 / DOC-H2）：`ACCEPTANCE` 的「7 个缺陷」应为 9；按「证据只增不改」
   只能用勘误/复验件处理，需 Lead 决定是否立项。
5. **spec / kb / workspaces / loop README**（DOC-A3…A5、DOC-B1…B11、DOC-C1…C14、DOC-D2…D3、DOC-I4…I5）：
   由 task-4 承接，本附录保留原始行号供其核对。

> **审计结论**：文档导航与结构归位已在 2026-10-19 一轮完成；剩余高风险项均属**跨仓重复**与
> **代码/契约缺口**，不在本次只读审计的修复范围。**审计发现 ≠ 已修复**，未执行项不得从
> `doc/STATUS.md` 与总审计报告中消失。
