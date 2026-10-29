# `doc/agents/` —— 角色定义索引

> 本目录 = 本仓的 **6 个角色定义** + **多份开工提示词**（用例生成 / 后续批次一次性执行 / R 门缺陷与网页重构 / S2 / S3 / S4–S6 / **S7**）。
> **当前现行开工指令**：[`开工提示词_S7-暴露面收敛与真机收口.md`](开工提示词_S7-暴露面收敛与真机收口.md)（2026-10-29 起）。
> 团队演练产物（32 件）已于 2026-10-19 迁至 [`../evidence/demo/`](../evidence/demo/)，
> 迁移记录见 [`../evidence/demo/MIGRATION.md`](../evidence/demo/MIGRATION.md)。
> 组织层流程 / 写权 / 红线见本仓 [`../../AGENTS.md`](../../AGENTS.md) 与环境仓 `doc/AGENTS.md`（只读引用）。

---

## 1 六个角色

| 角色 | 文件 | 节点 | 一句话职责 | 下游 |
|---|---|---|---|---|
| 差异语义分析师 | [`sim-env-分析师.md`](sim-env-分析师.md) | N3 | 把 Host 产出的确定性 diff 翻译成人可核对的语义摘要；**每条带证据行号**，不编造「影响」 | 人 · Gate1 |
| 评估报告员 | [`sim-env-报告员.md`](sim-env-报告员.md) | N12 | 把 N2–N11 产物组织成 Gate2 可判的评估报告；编译口径与功能口径分栏，引用不可解析即拒发 | 人 · Gate2 |
| 用例作者 | [`sim-env-用例作者.md`](sim-env-用例作者.md) | N6 | 在 `TESTLIB/` 下生成/修订 UVM 用例；**唯一有权写 `TESTLIB/*.sv` 的角色** | 用例执行（卡点 B） |
| 用例执行 | [`sim-env-用例执行.md`](sim-env-用例执行.md) | N7 / N9 | 只编译 / 运行，**不改用例**；rc、日志与 md5 进证据 | 用例检查（卡点 C） |
| 用例检查 | [`sim-env-用例检查.md`](sim-env-用例检查.md) | N8 / N10 | 静态复核与结果对账；发现问题是**退回 + 逐条依据**，不顺手改 | 回归守护（卡点 E） |
| 回归守护 | [`sim-env-回归守护.md`](sim-env-回归守护.md) | N11 | 证据链 / 冻结件完整性守护；证据不成链不算完成 | 人 · Gate2 / Gate3 |

> **来源与归属**：用例作者 / 用例执行 / 用例检查 / 回归守护是**环境仓既有的 4 个团队角色**；
> 分析师 / 报告员是本仓按 [`doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`](../spec/CHANGE_IMPACT_LOOP_SPEC.md) §10
> 第一阶段第 4 条**新增**的 N3/N12 角色。本仓 `doc/agents/` 是**单一权威副本**。

## 2 开工提示词（不是角色定义）

- [`开工提示词_用例生成.md`](开工提示词_用例生成.md) —— 「新增/修改 `TESTLIB/` 用例」这一工作的**唯一开工指令**，
  自包含（工作对象权威表、实测成本、三步检索、卡点 A~E、两个硬停点、回报协议）。
- **为什么保留在本目录**：环境仓 `doc/AGENTS.md` §7 按 `doc/agents/开工提示词_用例生成.md` 引用它，
  而 `doc/AGENTS.md` 是**冻结文件**；移动会造成冻结文档断链。单次任务可用 `AGENTS.md` §7 的浓缩版。
- [`开工提示词_R门缺陷与网页重构.md`](开工提示词_R门缺陷与网页重构.md) —— **现行开工指令**（2026-10-22）：
  以 R1–R5 缺陷收口为主线，含 Stage A 验证基线、Stage B 五项缺陷（+ R6 候选）、Stage C F14/F05 重构、
  命令清单与红线；自包含，新窗口可全文粘贴。
- [`开工提示词_后续批次一次性执行.md`](开工提示词_后续批次一次性执行.md) —— **已过期（历史参考）**：
  其范围内的切片已在 [`../STATUS.md`](../STATUS.md) §14–§34 完成，现行指令以上一条为准。
- [`开工提示词_S2-DSH执行器与后续切片.md`](开工提示词_S2-DSH执行器与后续切片.md) —— **已过期（历史参考）**：S2 已交付（STATUS §111）。
- [`开工提示词_S3-记忆与指令.md`](开工提示词_S3-记忆与指令.md) —— **已过期（历史参考）**：S3 已交付（STATUS §112）。
- [`开工提示词_S4-投影取证与候选导入.md`](开工提示词_S4-投影取证与候选导入.md) —— **已过期（历史参考）**：S4/S5/S6 已交付（STATUS §114/§115/§116）。
- [`开工提示词_S7-暴露面收敛与真机收口.md`](开工提示词_S7-暴露面收敛与真机收口.md) —— **现行开工指令**（2026-10-29）：
  S7a N6 收口 + DS-06 真机、S7b tool-allowlist、S7c DSH Web 实例与同源反代真机、S7d 低成本清理；
  自包含（必读清单、缺口派活表、三片验收、人工前置门、门命令、纪律、已知坑表、完成定义），新窗口可全文粘贴。

## 3 演练产物（已迁出本目录）

- 32 件演练证据（`accept/`、`evidence/`、`review/`、`guard/`、`TESTLIB_sandbox/` + `README.md`）现在在
  [`../evidence/demo/`](../evidence/demo/)，**内容冻结**。
- 其中 28 个文件正文仍含 doc/agents/_demo/... 的**历史路径字符串**（冻结证据，**不要批量重写**，
  否则会改内容 md5 并破坏 `T4_artifacts_md5.txt` 等记录）。old→new 映射与「内容 md5 未变」声明见
  [`../evidence/demo/MIGRATION.md`](../evidence/demo/MIGRATION.md)。

## 4 路径口径（拆仓后）

- 角色文档中的 `kb/runs`、`kb/conflicts`、`kb/index`、`kb/baselines` 一律指 **`WORKSPACE_ROOT`**
  （本机当前 = `ENV_ROOT/kb`，由 [`environments.json`](../../environments.json) 的 `workspace` 决定），
  **不是本仓 `kb/`**（本仓 `kb/` 只有 `tools/`、`schema/`、`README.md`）。
- `RTL/ TB/ PKG/ TESTLIB/`、`doc/AGENTS.md`、`doc/skills/`、`doc/_notes/`、`doc/tools/` 均相对 **`ENV_ROOT`**
  （环境仓），不是本仓 `doc/`。
- 解析规则见 [`doc/spec/ENV_PLUGIN_SPEC.md`](../spec/ENV_PLUGIN_SPEC.md) §1。
