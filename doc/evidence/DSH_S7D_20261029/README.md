# S7d 证据档 · 低成本清理（2026-10-29）

> 状态：**三件已收口（REV-16 §9-15 / §9-16 / §9-17），两件按纪律登记为下一轮（§9-8 / §9-12）**。
> 执行者：Lead（实现 + 门 + 收口）。**本片没有独立复核者**（不声称独立验证）。
> 入口：[开工提示词 S7](../../agents/开工提示词_S7-暴露面收敛与真机收口.md) §4/§5-9；计划
> [`2026-10-29-s7-exposure-convergence.md`](../../plans/2026-10-29-s7-exposure-convergence.md) §3/§8；
> 契约收口记录：[REV-16](../../spec/SPEC-REV-16-20261028.md) **§10（只增，不改写 §9 原文）**。
> 目录只增不改；冻结（444）与 `doc/evidence/DSH_S7D_20261029.md5` 由 Lead 在提交前一次完成。

## 1 逐条处置

| §9 条目 | 处置 | 判据可观察 |
|---|---|---|
| **§9-15** 归属判据两处实现 | **已收口**：抽出唯一实现 `services/instance_proxy.py::owned_document()`（三档 `missing/invalid/mismatch`），`load_target` 与 `session_copy` 只消费它；reason 词表各由调用方映射 | 反向抽检：把 `owned_document` 换成"永远 mismatch" ⇒ **两个端点同时**改变行为（`test_s7d_ownership_judgement_is_shared_by_proxy_and_session_copy`）；三档 kind 在两套词表里映射一致（`test_s7d_ownership_kind_maps_to_each_reason_vocabulary`） |
| **§9-16** 前端未映射 `session_*` reason | **已收口**：`web/s4-view.js::sessionReason()` 六个 reason 中文映射 + 未知值**原样显示**；`web/agent-window.js` 经它渲染 | 浏览器：中文说明可见 + 枚举仍可核（`test_unavailable_session_copy_explains_reason`）；未知值不折成"原因未知"（`test_unknown_session_reason_is_shown_verbatim_not_folded`） |
| **§9-17** `test_p2_httpx_*` docstring/顺序耦合 | **已收口**：拆三条（泄漏用例 / import 期契约 / 级别翻转幂等），并补**子进程对照**证明"不装压级时 token 确实进日志" | 4 条用例：`test_p2_httpx_info_logging_never_prints_managed_token`、`test_p2_silencing_is_idempotent_and_recoverable`、`test_p2_import_time_silencing_is_explicit`、`test_p2_control_without_silencing_token_reaches_info_log` |
| **§9-8** 事件 `ts` 与注入时钟不同源 | **仍开（本轮不做）** | 属**共享判据面**变更（§4 要求"单独变更 + 留证"）：改 `host/progress.py::ProgressLog.append` 的时间源会同时改变事件流、无进展判据与**所有 drill 夹具**的时间语义。必须走"改规格 → 特征测试 → 迁移 → 留证"的单独变更。现行为仍是"差值夹 0，不产生假告警" |
| **§9-12** 角色卡 `identity.attempt/session_id` 恒 null | **仍开（本轮不做）** | 需把**已封存记录**冷读进 `build_agents` 再喂给已有的 `progress_view(request=…, result=…)`（窗口端点已这么做）；这是跨层接线的独立小片。界面继续显示"尝试未知"（诚实值） |

**为什么后两条不做**（照实说明，不写成"已实现"）：它们不是"廉价清理"——
§9-8 属共享判据面（改一处、三处语义一起动），§9-12 属跨层冷读接线（`agent_view` → `agent_memory`）。
为它们各开一片并单独留证，比在窗口尾部塞进 S7d 更符合 SpecDD 的"单独变更 + 留证"。

## 2 交付物

| 文件 | 变更 |
|---|---|
| `loop/services/instance_proxy.py` | 新增 `OWNERSHIP_MISSING/INVALID/MISMATCH`、`OwnershipError`、`owned_document()`；`load_target`/`session_copy` 改为消费它（**判据语义逐条不变**：坏件→`target_invalid`/`session_metadata_invalid`；缺失/归属不符→`target_missing`/`session_metadata_missing`/`session_owner_mismatch`） |
| `loop/web/s4-view.js` | 新增 `SESSION_REASON` 表与 `sessionReason()`（导出）；未知值原样返回 |
| `loop/web/agent-window.js` | 会话副本不可用文案改经 `window.S4View.sessionReason()`（不再直出英文枚举） |
| `loop/tests/test_instance_proxy.py` | 新增 2 条归属唯一性用例；拆 3 条 P2 用例 + 新增子进程对照（+4 例，S4 原 45 例零回归） |
| `loop/tests/browser/test_s4_projection_ui.py` | 强化 1 条 + 新增 1 条（session reason 映射与不折叠） |
| `doc/spec/SPEC-REV-16-20261028.md` | **§10 未决收口记录（只增）**：逐条标"已收口/仍开"与依据，**不改写 §9 原文** |

## 3 收口门（数字从输出复制）

| 门 | 结果 |
|---|---|
| 单测（可写数据根） | `3 failed, 1770 passed, 1 warning, 141 errors in 431.96s`；3 failed 全部是既有 `env_layer`；141 errors = 浏览器缺 Chromium（140 既有 + 1 条新增浏览器用例） |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；**原 ENV_ROOT 零写入** |
| 端到端（drill） | `phase 1–5 + 4b` 全 `rc=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.48s` |
| **浏览器门（改了界面，必跑）** | **`142 passed in 150.19s`**（S7c 141 + 1） |

差量对账：S7c 树 `1766 passed`/`140 errors` → S7d 树 **`1770 passed`/`141 errors`**
（+4 单测用例；+1 浏览器用例在无 Chromium 的机器上计入 errors）；`failed 3=3`、`warnings 1=1`，
**零新增失败**。

## 4 纪律核对

- **写权**：`doc/spec/**` 只由 Lead 改（且**只增 §10**，不改 §9 原文）；`kb/**` 零改动；`doc/evidence/**` 只增。
- **唯一判据（红线 8）**：§9-15 是**消除**第二份判据（不是新增）；reason 映射只在 `s4-view.js` 一处，
  `agent-window.js` 只调用。前端仍不重算任何判据。
- **可观察行为未变**：`load_target`/`session_copy` 的 reason 取值逐条保持（用例覆盖 missing/invalid/mismatch 三档）。
- **不声称**：不声称 §9-8/§9-12 已解决；不声称独立复核。

## 5 复现

- 定向：`cd loop && LOOP_WORKSPACE=<repo>/.dev-ws .venv/bin/python -m pytest -q tests/test_instance_proxy.py`
  ⇒ `60 passed`；`-k s7d` ⇒ 2 条归属用例；`-k p2` ⇒ 4 条。
- 浏览器：`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp
  .venv/bin/python -m pytest -q tests/browser/test_s4_projection_ui.py` ⇒ `28 passed`。
- 门日志：`raw/s7d-gate{1..5}-*.log`。
