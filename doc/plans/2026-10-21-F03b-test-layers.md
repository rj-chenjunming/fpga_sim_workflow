# F03-b 完整形态：测试分层标记与软件层入口 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](../../doc/plans/OPTIMIZATION_PLAYBOOK.md) F03（P1 验证基础）、
> [STATUS §17](../STATUS.md)「未完成：F03-b 的测试分层标记（纯软件/受控插件/真实内网）与剩余失败分类」。
> 按 [STATUS §19](../STATUS.md) 整改顺序：**计划+规格先提交 → 红灯用例 → 实现 → 独立复核报告落盘**。

| 项 | 内容 |
|---|---|
| 类型 | 验证基础设施（不改业务行为） |
| 基线提交 | `219fb70`（F13 整改后） |
| 唯一 owner | 验证工具 owner（本切片同一 owner 实现） |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [环境插件规格 §4 / §4.1](../spec/ENV_PLUGIN_SPEC.md) |
| 允许修改 | `loop/pytest.ini`、`loop/tests/conftest.py`（如需要）、`loop/tests/test_archive_e2.py`、`loop/tests/test_projection_and_frozen.py`、`loop/tests/`（新增分层断言）、`loop/spikes/`（入口脚本）、`doc/spec/ENV_PLUGIN_SPEC.md`、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | `kb/**`、业务实现、默认根的失败集；不把环境层失败改成 skip |

## 1 问题

- 环境层与环境无关的软件层混在一起：默认根 `46 failed` 全部是环境只读/布局原因，但没有机器可读的标记；
  软件层入口靠「人事先知道只排除哪几个」运行，`3 failed` 时无法自动区分「环境层」与「新回归」。
- `pytest.ini` 未注册自定义标记、未开 `--strict-markers`：将来拼错标记不会失败。
- 软件层入口没有显式打印「排除了哪些环境层用例」。

## 2 目标可观察行为

1. 3 项环境层用例带 `@pytest.mark.env_layer` 且在用例内写明原因（可写 `ENV_ROOT` / 冻结见证 / 布局要求）。
2. `pytest.ini` 注册 `env_layer` 并启用 `--strict-markers`；使用未注册标记时 pytest 直接报错。
3. `run_software_checks.sh` 默认 `-m "not env_layer"`，打印被排除的用例数与清单；`INCLUDE_ENV_LAYER=1` 时包含。
4. 软件层入口：**0 failed**（3 项环境层被显式排除，不是 skip 换绿）。
5. 默认根：仍如实执行并失败这 3 项（失败集与 §17/§21 基线相同，不隐藏）。

## 3 不变量与唯一判据

1. 标记只影响**选择**，不影响用例成败：默认根结果不得因标记改变。
2. 环境层判定由「失败原因是否属于可写 ENV_ROOT / 冻结见证 / 布局」决定，写进测试原因说明，不只写标记。
3. 软件层入口不得新增 `--ignore`/`-k` 之类的隐式过滤；过滤表达式唯一为 `not env_layer`。
4. 数字从命令输出复制；默认根与软件层分别记录。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F03-b1 | 规格 §4/§4.1 + 本计划 | 文档门 |
| F03-b2 | 红灯：分层元数据断言（`-m env_layer --collect-only` 精确 3 项；`--strict-markers` 生效） | 先红（贴原始输出） |
| F03-b3 | 实现：pytest.ini 标记 + 3 处标记与原因 + 入口脚本默认排除/打印/开关 | 定向 + 默认根 + 软件层（0 failed） |
| F03-b4 | 独立复核报告（`doc/audit/`，只读子代理） | 报告含命令、原始输出、结论、残余；md5 记入 STATUS |
| F03-b5 | STATUS §23 | 命令与输出逐字复制；未运行项单列 |

**验证边界**：本机 `ENV_ROOT` 只读，环境层 3 项**未运行通过**（如实失败）；
kb 自测与端到端仍不可运行。软件层 `0 failed` 只覆盖纯软件层。

## 5 回退

移除标记与入口过滤即回退到原行为；不删除任何用例、不改默认根的失败集。
