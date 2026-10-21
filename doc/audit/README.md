# 审计目录（`doc/audit/`）

本目录存放**一次性审计报告**与**只读独立验证报告**。一次审计/验证一份，只新增不改写；
验证报告只报告不改被测实现（`AGENTS.md` §9）。

## 2026-10-19 · 规格一致性审计

| 文件 | 内容 |
|---|---|
| [`AUDIT-20261019-spec-conformance.md`](AUDIT-20261019-spec-conformance.md) | 主报告：范围、方法、阻断级总表（去重）、结论、修复建议顺序 |
| [`parts/spec-conformance.md`](parts/spec-conformance.md) | 附录 A：`loop/` 实现 ↔ 业务/编排 spec 的偏差（49 条） |
| [`parts/agently-runtime.md`](parts/agently-runtime.md) | 附录 B：Agently 设计与运行时用法（44 条） |
| [`parts/docs-structure.md`](parts/docs-structure.md) | 附录 C：文档与目录结构一致性（约 50 条，含本轮已执行项） |

## 2026-10-21 起的逐切片独立验证

| 文件 | 内容 |
|---|---|
| [`check_doc_links.py`](check_doc_links.py) | 文档路径检查器（按所有权路由；退出码 0/1/2） |
| [`F02b-verify-20261021.md`](F02b-verify-20261021.md) | F02-b 独立复核 |
| [`F16b-verify-20261021.md`](F16b-verify-20261021.md) | F16-b 独立复核 |
| [`F13-verify-20261021.md`](F13-verify-20261021.md) | F13 独立复核 + 回归复核 |
| [`F03b-verify-20261022.md`](F03b-verify-20261022.md) | F03-b 独立复核 |
| [`F03c-verify-20261022.md`](F03c-verify-20261022.md) | F03-c 独立复核 + 回归复核 |
| [`F16c-F02c-verify-20261022.md`](F16c-F02c-verify-20261022.md) | F16-c/F02-c 独立复核 |
| [`F15a-verify-20261022.md`](F15a-verify-20261022.md) | F15-a 独立复核 |

## 纪律

1. 审计**只读**被测代码：发现问题只登记，不修；修复由对应 owner 另开一轮。
2. 每条发现必须可定位（`文件:行号`）并区分 `[已确证]` / `[待核]`。
3. 报告头必须写明「本轮是否修复」；未修复项在 `doc/STATUS.md` 保持可见。
4. 修复完成后，在**新**报告里记录「已修 + 复验证据」，不回写旧报告。
