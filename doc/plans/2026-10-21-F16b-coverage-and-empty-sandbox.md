# F16-b 残余项：coverage 语义与空沙盒闭锁 · 切片计划

> 承接 [F16 计划](2026-10-21-F16-n8-context-budget.md) §5 复核残余、[STATUS §18](../STATUS.md) 的 P3 项。
> 本计划按 [STATUS §19 流程整改](../STATUS.md) 执行：**计划先提交（本节不含实测）→ 失败用例提交 → 实现提交**。

| 项 | 内容 |
|---|---|
| 类型 | 契约补齐 + fail-closed |
| 基线提交 | `b7d4269` |
| 唯一 owner | Host 上下文构造器（N8 沙箱输入） |
| 规格位置 | [上下文规格 C1](../spec/AGENT_CONTEXT_SPEC.md) |
| 允许修改 | `loop/workflows/chunks/model_steps.py`、`loop/tests/test_n8_context_budget.py`、`doc/spec/AGENT_CONTEXT_SPEC.md`、本计划、`doc/STATUS.md` |
| 不修改 | `kb/**`、闸门、拓扑、冻结证据；不改 120000 总预算与 60000 分片预算 |

## 1 问题

1. `coverage.complete` 恒为 `true` 但**语义未定义**：消费者可能把它读成「已做全文复核」，而片段模式只提供变更区域。
2. 沙箱目录缺失或为空时，`build_sandbox_cases` 返回空列表且 `used_bytes=0`，N8 会以「复核 0 件」继续 ——
   与 fail-closed 纪律不符（N6 施加后不应凭空没有用例）。
3. 字节级确定性缺少断言：现有用例比较文件顺序与汇总，未比较 `AM.encoded` 的逐字节一致。

## 2 目标可观察行为

- 规格定义 `coverage.complete`：`true` = 该件**全部变更区域**已提供（不是全文复核证明）；出现未提供的变更组不得置 true。
- 沙箱无 `*.sv`，或 `applied_cases` 非空却找不到文件 ⇒ `RuntimeError`，错误信息可定位（缺什么/期望什么）。
- 两次构造的 `AM.encoded(sandbox_cases)` 逐字节相同。

## 3 不变量

1. 不改变既有成功路径的输入形状（`excerpt/coverage/changed_regions` 字段不变）。
2. 闭锁只针对「无可复核对象」，不影响已定位的正常输入。
3. 错误必须出现在模型请求之前（`check_budget` / provider 不触发）。

## 4 切片与验证

| 切片 | 内容 | 验证 |
|---|---|---|
| F16-b1 | 规格：complete 语义 + 空沙盒闭锁 | 文档链接可达 |
| F16-b2 | 失败用例：空沙盒 / applied 非空但无文件 / 字节确定性 / complete 与 regions 自洽 | 先红（原始输出入提交信息） |
| F16-b3 | 实现：空/缺件闭锁；确定性与 complete 断言转绿 | 定向用例 + 全套 + 软件层 |
| F16-b4 | 独立复核报告落 `doc/audit/F16b-verify-20261021.md` | 报告含命令与 md5 |

## 5 回退

删除闭锁判断与规格新增条款即回到原行为；已生成的历史请求不复用、不回填。

## 6 实测（数字从命令输出复制）

| 验证 | 原始输出 | 说明 |
|---|---|---|
| 失败用例先红（提交 `ef8b7b1`） | `3 failed, 9 passed in 0.78s`（`DID NOT RAISE RuntimeError` ×3） | 空目录/缺目录/applied 非空无文件 |
| 实现后定向 | `65 passed, 32 deselected in 1.93s` | N8/上下文相关（含新增 5 项） |
| 默认根全套 | `46 failed, 287 passed, 3 skipped, 1 warning in 13.09s` | 46 项同因（44 `Errno 30` + 2 归档）；通过数 282→287 |
| 软件层全套 | 见 STATUS §20 | 5 个夹具用例仍正常（闭锁不误伤） |

## 7 独立复核

报告：[doc/audit/F16b-verify-20261021.md](../audit/F16b-verify-20261021.md)（仅由验证者写入，Lead 不改）。
