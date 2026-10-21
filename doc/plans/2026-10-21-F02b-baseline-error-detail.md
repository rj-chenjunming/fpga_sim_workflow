# F02-b 基线错误结构化 detail 与前端展示 · 切片计划

> 承接 [F02 计划](2026-10-21-F02-capability-facts.md) 收尾项、[STATUS §14](../STATUS.md) 后续第 ③ 条
> （`/api/baselines` 失败 detail 未带 `missing/errors`）。按 [STATUS §19](../STATUS.md) 执行：
> **计划+规格先提交 → 红灯用例提交 → 实现提交 → 独立复核报告落盘**。

| 项 | 内容 |
|---|---|
| 类型 | 缺陷修复（错误可诊断性）＋前端展示 |
| 基线提交 | `f4f0979` |
| 唯一 owner | API 投影 owner（detail）+ UI owner（展示）；本切片同一 owner |
| 规格位置 | [Web UI §9 POST /api/runs](../spec/WEB_UI_SPEC.md)、§6.1 |
| 允许修改 | `loop/services/api.py`、`loop/web/app.js`、`loop/tests/test_api_baseline_detail.py`（新增）、`doc/spec/WEB_UI_SPEC.md`、本计划、`doc/STATUS.md` |
| 不修改 | `kb/**`、闸门、拓扑、冻结证据；不改准入判据本身 |

## 1 问题

`POST /api/runs`（`mode=real`）在基线无效时返回 `400 {"error": "..."}`：`error` 是拼接后的长字符串，
调用方与 UI 拿不到结构化的 `missing`/`errors`，只能整段文本展示；`GET /api/baselines` 列表项已有这两个字段，
但配置视图的“manifest 不可用”提示只展示 `missing`，不展示 `errors`（schema/身份/指纹/链违规）。

## 2 目标可观察行为

- 基线无效 ⇒ `400`，`detail` 含 `{error, baseline, missing[], errors[]}`；两者为空也必须是数组。
- `drill` 与其它 `ValueError` 的 400 形态不变（只有基线准入失败才带结构化字段）。
- UI：启动失败提示追加 `缺件…`/`违规…`；配置视图基线提示与目录选择器中的不可用基线展示 `errors`。

## 3 不变量

1. 只在**拒绝路径**增强字段，不改准入判据、不改变成功响应。
2. `missing`/`errors` 直接取 `BaselineInvalid.details`（判据唯一来源），API/UI 不重复推导。
3. 不泄漏敏感路径之外的信息：字段来自基线判据本身（本就对列表端点可见）。

## 4 切片与验证

| 切片 | 内容 | 验证 |
|---|---|---|
| F02-b1 | 规格：结构化 detail + UI 展示要求 | 文档链接可达 |
| F02-b2 | 红灯用例：未知基线 / 坏 manifest 的 400 detail 字段 | 先红（原始输出入提交信息） |
| F02-b3 | 实现：`api.py` 构造 detail；`app.js` 展示 missing/errors | 定向 + 全套；`node --check` |
| F02-b4 | 独立复核报告 `doc/audit/F02b-verify-20261021.md` | 报告含命令与 md5 |

**验证边界**：本机无 Chromium，UI 行为不跑浏览器断言（如实登记未运行）；API detail 有单测覆盖。

## 5 回退

只回退 detail 字段与前端展示分支；准入判据与列表端点行为不变，历史请求记录不回填。

## 6 实测

（实现与验证后回填；见 [STATUS §21](../STATUS.md)。）
