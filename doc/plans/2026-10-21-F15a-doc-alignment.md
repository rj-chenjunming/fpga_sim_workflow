# F15-a 规格与文档对齐 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F15-a、[开工提示词](../agents/开工提示词_后续批次一次性执行.md) §4 第 5 项
> 「旧数字（“70 项”“94 项”“单文件前端”）与旧能力描述按现状更新；历史章节加“适用版本”指向现行章节；
> 不动冻结证据」。本切片**只改现行导航/说明性文字**，不改任何契约判据。

| 项 | 内容 |
|---|---|
| 类型 | 文档整理（不含行为变化，不适用红灯用例） |
| 基线提交 | `96cf86b` |
| 唯一 owner | Lead / 规格 owner |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 允许修改 | `README.md`、`doc/README.md`、`loop/README.md`、`doc/spec/ENV_PLUGIN_SPEC.md`（仅 §5 历史数字口径）、`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（仅历史完成度行）、`doc/plans/2026-10-19-web-ui-v1.md`（仅顶部适用版本横幅）、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | `doc/evidence/**`、`doc/history/**`（冻结）、`kb/**`、业务实现、任何验收判据 |

## 1 问题

现行入口文档仍把历史采样当作现状：

1. `loop/README.md` 写「70 项」「94 项」「静态页 index.html+app.js+app.css（单文件前端）」——前端早已拆成
   `app.js` / `s0.js` / `agent-window.js` / `run-view-state.js` / `capabilities.js` + 共享 CSS；用例数量已变。
2. 根 `README.md` §5 红线 1 仍写「只新增 `kb/` 与 `doc/` 下文件」——这是拆仓前环境仓的限制，
   与 [AGENTS.md](../../AGENTS.md) §3（软件仓有实现写权）矛盾。
3. 根 `README.md` 快速开始把 `10/10`、`9/9`、`117 断言` 当成当前期望；`doc/README.md` 说
   「1 份开工提示词」「audit 只登记不修复」「尚未实施待办」；`doc/agents/` 实有 2 份提示词、audit 已含验证报告、
   手册任务已开始逐切片实施。
4. `doc/spec/ENV_PLUGIN_SPEC.md` §5 与 `CHANGE_IMPACT_LOOP_SPEC.md` 完成度行仍以旧数字作「当前基线」，
   未标明是历史采样；`doc/plans/2026-10-19-web-ui-v1.md` 的「N11 未实现」结论已过期且无适用版本横幅。

## 2 目标可观察行为

1. 现行入口（根 README / `doc/README.md` / `loop/README.md`）不再出现「单文件前端」与硬编码用例/断言数；
   数字统一指向 [STATUS](../../doc/STATUS.md)。
2. 根 README 写权摘要与 AGENTS.md §3 一致（软件仓实现可写；环境资产与冻结件只读）。
3. 目录/文档索引反映现状：2 份开工提示词、audit 含验证报告、手册任务已开始实施。
4. 历史章节（`ENV_PLUGIN_SPEC` §5、`CHANGE_IMPACT_LOOP_SPEC` 完成度行、2026-10-19 UI 计划）
   加「适用版本 / 历史采样」标注并指向现行章节；冻结证据不回填。
5. 文档门退出码 0、`missing=0`；`env_missing` 只含未挂载的内网资产。

## 3 不变量

1. 不改任何契约判据、API 字段、测试期望；只改说明性文字与导航。
2. 不删除历史事实：历史数字保留在原处但显式标注为历史采样，不替换成新数字（避免制造第二数字源）。
3. 冻结件（`doc/evidence/**`、`doc/history/**`）零改动。
4. 每处改动都能在仓库现状中找到依据（文件存在、命令可跑、STATUS 记录）。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F15-a1 | 本计划 | 文档门 |
| F15-a2 | README/索引/loop README/历史横幅对齐 | 文档门 + 引用存在性 + 人工逐条核对 |
| F15-a3 | 独立复核报告（`doc/audit/`，只读子代理） | 报告含命令/原始输出/结论/残余；md5 记入 STATUS |
| F15-a4 | STATUS §26 | 命令与输出逐字复制；未运行项单列 |

**验证边界**：文档切片不跑业务代码；单测/kb 自测/端到端不在本切片重复执行（沿用 STATUS 记录）。
「现状」以仓库文件与 STATUS 为准，不声称四道门全绿。

## 5 回退

还原被修改的说明性文字即可；不涉及代码、契约或冻结件。
