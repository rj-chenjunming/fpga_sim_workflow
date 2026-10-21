# F03-c 文档解析器根解析与表驱动用例 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F03（P1 验证基础）第 5 条、
> [STATUS §16/§17](../STATUS.md)「未解决：F03-c 文档解析器根解析」、F03-b 后仍未闭合项。
> 按 [STATUS §19](../STATUS.md) 整改顺序：**计划+规格先提交 → 红灯用例 → 实现 → 独立复核报告落盘**。

| 项 | 内容 |
|---|---|
| 类型 | 验证工具缺陷修复（不改业务行为） |
| 基线提交 | `9afc7e5` |
| 唯一 owner | 验证工具 owner（本切片同一 owner 实现） |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [环境插件规格 §4.2](../spec/ENV_PLUGIN_SPEC.md)、§1 三根 |
| 允许修改 | `doc/audit/`（文档检查器）、`loop/tests/`（新增表驱动用例）、`doc/spec/ENV_PLUGIN_SPEC.md`、本计划、`doc/STATUS.md`、`doc/audit/`（验证报告） |
| 不修改 | 业务实现、`kb/**`、冻结证据/历史；不改扫描口径之外的历史内容 |

## 1 问题（可复现）

`check_doc_links.py` 用一张 `ENV_CANDIDATES` 前缀表同时决定「去哪找」和「算不算环境资产」：

1. `kb/tools/`、`kb/schema/` 被当成**数据根/环境**资产：在只有本仓工具树的受控根里会解析失败，
   真实仓库里则命中 `ENV_ROOT/kb/tools`（旧副本），等于**用错根也能通过**——工具/Schema 的修改无法由文档门发现。
2. `loop/` 路径存在环境回落：已迁走的 `loop/ACCEPTANCE_V1.md` 会命中 `ENV_ROOT/loop/...`，
   被误判为「已解析」而不是断链（误判缺失的反面：**误判存在**）。
3. 环境缺件与真断链混在一个 `missing` 里：`TB/top.sv` 这类内网资产只能写进 `KNOWN_MISSING` 静默跳过，
   既不可见也不分类；判定无法区分「本仓断链」与「环境未挂载」。
4. 没有表驱动用例：根路由、后缀剥离、历史件、分类只靠全库扫描间接验证。

## 2 目标可观察行为

见 [规格 §4.2](../spec/ENV_PLUGIN_SPEC.md)：

1. 本仓/数据根路径（`kb/tools/*`、`kb/schema/*`、`loop/*`、`doc/*`、`workspaces/*`）只在 `TOOL_ROOT` / `WORKSPACE_ROOT`
   解析；`loop/` 无环境回落。
2. 环境资产（`RTL/`、`TB/`、`uvs.setup`、`doc/AGENTS.md`、`doc/skills/`…）只在 `ENV_ROOT` 解析；
   解析不到 ⇒ `env_missing`，**逐条打印**但不改变退出码。
3. 真断链 ⇒ `missing` + 退出码 1；`KNOWN_MISSING` ⇒ 打印原因、不计失败。
4. 历史件（`doc/history/`、`doc/evidence/demo/`）按既有契约只计数不判失败。
5. 行号/符号后缀、URL/锚点/模板/变量按既有契约处理。

## 3 不变量与唯一判据

1. 唯一实现 `doc/audit/check_doc_links.py`；任何其它脚本不得再写一套根解析。
2. 路由由**路径所有权**决定（表驱动），不由「先试这个根再试那个根」决定。
3. 退出码只由 `missing`（本仓/数据根断链）决定；`env_missing`/`known_missing` 必须**可见**但不等同失败。
4. 扫描范围、历史件规则、后缀剥离与现状一致，不得借重构放宽。
5. 检查器只读：不写仓库任何文件。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F03-c1 | 规格 §4.2 + 本计划 | 文档门 |
| F03-c2 | 红灯：`tests/test_doc_links.py` 表驱动（根路由/分类/退出码/后缀/历史） | 先红（贴原始输出） |
| F03-c3 | 实现：检查器重写为 `Roots` + `classify/resolve/scan`；CLI 输出分类 | 定向 + 全库扫描（退出码 0、missing=0）+ 默认根 |
| F03-c4 | 独立复核报告（`doc/audit/`，只读子代理） | 报告含命令、原始输出、结论、残余；md5 记入 STATUS |
| F03-c5 | STATUS §24 | 命令与输出逐字复制；未运行项单列 |

**验证边界**：本机未挂载内网 `ENV_ROOT` 的部分资产 ⇒ `env_missing` 可见但不失败；
kb 自测与端到端仍不可运行（沿用既有环境限制）。

## 5 回退

还原 `doc/audit/check_doc_links.py` 旧实现与测试即可；不改任何被测文档内容。
