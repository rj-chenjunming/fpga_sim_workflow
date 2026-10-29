# 更正件 · S7C「9 条 500 未定位」与「WS 405」的后续（2026-10-29，**只增不改**）

> **性质**：本文件是 [`DSH_S7C_20261029/`](README.md) 冻结证据的**只增更正件**。
> 原 `README.md` §7（未做 / 未定位）与 `red-green.md` **未被修改、不回填**。
> 触发：S8 的 [S8c 交付](../../STATUS.md) 与独立复核 [`AUDIT-20261029-s7`](../../audit/AUDIT-20261029-s7.md)。
> 纪律：`AGENTS.md` §5 红线 3（归档只增不改）。

## 1 §7-1「9 条 `500` 的 URL 未定位」⇒ **已定位：探针夹具缺陷，不是产品缺陷**

- **原登记**：`README.md` §7-1 写"9 条 `500` 的 URL 未定位；候选：探针夹具导致看板自身 `/api/…` 500，或 DSH 某端点真 500；**未排除**"。
- **定位方式**：一次 Playwright 全量落 `(phase, frame, method, url, status, resource_type)`，fake/real 两模式各 78 条响应。
- **计数原文**（[`DSH_S8C_20261029/raw/probe_500s_report.txt`](../DSH_S8C_20261029/raw/probe_500s_report.txt)）：
  - `mode=fake`：`{303: 1, 200: 62, 500: 15}`，500 全在**看板主帧** `GET /api/runs`；
    根因原文 `services/api.py:266 list_runs → AttributeError: 'FakeManager' object has no attribute 'list_runs'`。
  - `mode=real`（真 `RunManager`）：`{303: 1, 200: 77}` ⇒ **零 `500`**；iframe 内上游端点 **0 条 `500`**。
- **结论**：15 条（S7c 当时窗口更短 ⇒ 9 条）全部来自 S7c 自己的探针夹具 `probe2_app.py::FakeManager`
  缺 `list_runs`。**产品面无 500**。S7C 的这一条**不应再作为"未排除的产品风险"引用**。

## 2 §7-5「Web 实例未套 bwrap」⇒ 不变（仍登记为加固项）

## 3 关于 `remote.mux`（WebSocket 405）的补充事实

S7c 已实测 `WS /api/remote.mux` 需升级、反代回 **405**（REV-16 §9-2 登记为未决）。S8b 进一步实测到它的
**产品后果**：同源反代 iframe 里 DSH Web 的 **live channel 起不来** ⇒ 会话列表取不到数据
（`No sessions yet` / `Reconnecting…`）；而**直连实例**（不经反代）会话列表正常。
⇒ 「人在 GUI 里看到该 attempt 的会话」这条产品目标，**机制已达成、内嵌路径被 §9-2 挡住**
（见 [`DSH_S8B_20261029`](../DSH_S8B_20261029/README.md) 的 D3 判定）。
本条只补事实，**不改变** §9-2 的"本轮不做"裁决定位。
