# S4 计划 · 投影与界面（总结投影 / 无进展告警 / 同源反代 / S3 接面）

> 日期：2026-10-28。状态：**进行中**。SpecDD ② 产物：本条 + 契约 [SPEC-REV-16](../spec/SPEC-REV-16-20261028.md)。
> 入口：[开工提示词 S4–S6](../agents/开工提示词_S4-投影取证与候选导入.md) §4.1；基线 `9bd0b78`。
> 本计划不含 S5/S6（另见 `2026-10-28-s5-s6-admission-and-candidate.md`）。

## 1 开工基线（命令输出复制，详见 STATUS 新节）

| 门 | 结果 |
|---|---|
| 单测（可写数据根 `<repo>/.dev-ws`） | `3 failed, 1394 passed, 1 warning, 113 errors in 358.47s`；3 failed 全是 `@pytest.mark.env_layer`（本机 ENV_ROOT 只读）、113 errors 是 `tests/browser/**` 缺 Chromium（不并入四门） |
| kb 自测 + env layer | `PASS=10` / `PASS=9` / `PASS=28`，`FAIL=0`；env_layer `3 passed, 24 deselected in 10.55s`；**原 ENV_ROOT 零写入**（`find -newer` 命中 0） |
| 端到端（drill） | `phase 1–5`（含 4b）全 `rc=0`，`=> ALL PASS` |
| 文档门 | `65 passed in 2.17s` |
| 浏览器门（§6 三组 env） | `114 passed in 124.61s` |

（全部为本窗口实测，命令输出复制；`loop/.logs/gate-*.log` 留原始输出。）

## 2 切片与落点

| 片 | 内容 | 落点（唯一写者） | 验收 |
|---|---|---|---|
| **S4-A** | 总结投影 + 无进展判据 + 压缩次数 + S3 解释面（纯函数） | `loop/services/agent_view.py`、`loop/services/contracts.py`、`loop/tests/test_agent_view_projection.py`（+ 特征测试 `test_agent_view_baseline.py`） | `OBS-02`～`OBS-04`、`OBS-08`（服务端半边） |
| **S4-B** | 同源反代与安全拒绝矩阵、不可用态、可用性端点 | `loop/services/instance_proxy.py`（新）、`loop/services/api.py`（只加路由/错误映射）、`loop/tests/test_instance_proxy.py` | `OBS-05`、`OBS-06` |
| **S4-C** | 运行摘要区 / 无进展红字 / S3 三列 / iframe 两态与降级 | `loop/web/**`、`loop/tests/browser/**`（新文件优先） | `OBS-03`(界面)、`OBS-04`(界面)、`OBS-07`、`OBS-08`(界面)、`OBS-01`/`U01–U11` 不回归 |
| **S4-D** | 独立复核（只报告不改） | 只读 | 反向抽检 |

**串行点**：S4-B 在 `api.py` 里接线 S4-A 的纯函数（2 行），必须等 S4-A 函数签名落定；除此之外三片文件互不重叠，可并行。
**写权冲突纪律**：`api.py` 只有 S4-B 一个 writer；`agent_view.py`/`contracts.py` 只有 S4-A；`web/**` 只有 S4-C。Lead 只写 `doc/**`（spec/计划/STATUS/证据）。

## 3 契约要点索引（细节在 SPEC-REV-16，这里只记账号，不复制正文）

- 投影字段/未知保持未知 → REV-16 §2；压缩次数只认 session log → §2.2。
- 无进展判据（`NO_PROGRESS_THRESHOLD_S=600`、只告警）与文案禁令 → §3。
- 时间唯一入口 `LOOP_NOW`/`KB_NOW` → §4。
- 反代：目标来自受管元数据、loopback、R1–R14 拒绝矩阵、token 不回显、不可用态 → §5。
- iframe 三态与降级（新标签页 + 导出会话副本）→ §6.2；S3 接面三态分列 + `scope_expiry=未判定` → §6.3。

## 4 验证门

1. **每片 TDD**：特征测试（固定既有行为）→ 失败用例（RED，数字留档）→ 实现（GREEN）→ 受影响回归；新增用例做**反向抽检**（把实现改坏，用例必须变红）。
2. **S4 收口四道门**（AGENTS §4，命令见开工提示词 §6）：单测（可写数据根）、kb 自测 + env layer、e2e、文档门。
3. **浏览器门**（本片必跑，`loop/web/**` 与界面字段都改了）：
   `PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp pytest -q tests/browser`；基线 `114 passed in 120.78s`。
4. 证据：新目录 `doc/evidence/DSH_S4_20261028/`（raw 脱敏 + README 三态结论 + 冻结 444 + md5 记在目录外）。
5. STATUS 新节（只增），数字从命令输出复制。

## 5 不做（边界）

- 不在前端实现第二套预算/闸门/校验/无进展判据（红线 8）；不把投影当权威。
- 不引入前端构建链/新依赖；不改 `kb/**`；不改 `SETTINGS.yaml` 的 dsh 块（属 S5，需裁决）。
- 不做"自动收敛/自动终止"；无进展只告警。
- 不声称 C2/E；不声称内嵌已对真实 DSH Web 验过。

## 6 未决（照实登记）

1. `agent_instance.json` 的**写入方**属 S5 真机接入；本片只读，缺失即 `target_missing`（REV-16 §9-1）。
2. WebSocket/SSE 升级未支持（405），S5 实测后再定（§9-2）。
3. `node_rework`/`run` 终态到期归约未实现 ⇒ `scope_expiry` 恒 `determined=false`，界面写"未判定"（§9-3、S3 计划 §6.4-39）。
4. 会话副本解码只到 `read_session_log` 现有能力（§9-4）。
5. 旧 session 事件 `attempt` 投影在目录缺口时可能偏 1（S3 计划 §6.4-45，低优先，不影响封存身份与 IL 判定）。
6. **反代读 SETTINGS 的常驻实例源本片不做**（与 `dsh.config_from_settings` 的 `CONFIG_KEYS` 冲突、且不在 S4 写权）⇒ 本片唯一目标源是 `<run_dir>/agent_instance.json`，缺失即 `target_missing`。S5 与写入方一并落地（REV-16 §9-6）。
7. **反代方法面修正（2026-10-28 实现期）**：为满足"iframe 内 `/api` 不 403"的验收，HTTP 方法原样透传（`GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS`），目标仍只来自受管元数据；`CONNECT`/`TRACE`/WebSocket 升级 405。写方法透传的是**上游实例自己的会话状态**（旁路审计面），不是本仓业务写权（REV-16 §5.1 注、§9-7）。
8. **压缩事实的指路字段 `session_log_ref` 无生产者**（S5 前）：S4 按"记录里有 `session_log_ref`（相对 run_dir，越界/符号链接拒绝）才读，否则 `source=unknown,count=null`"实现；S5 落账时必须按此字段名写入（REV-16 §2.2 来源纪律不变）。
9. **`last_tool` / `last_result.ts` 无生产者**：`last_tool` 恒 `null`（不从事件 detail 猜），`last_result.ts` 只在记录有 `ts`/`finished_at` 时使用、**不用文件 mtime**；两者均登记为 S5 工具/结果事件落账后补齐。
10. **事件 `ts` 与注入时钟不同源**：`host/progress.py::ProgressLog.append` 用系统时钟 ⇒ drill 固定 `LOOP_NOW` 时 `silence_s` 夹 0（不产生假告警，但可能掩盖停滞）。本片不做共享判据面改造（单独变更 + 留证）；真实运行不注入时钟时同源（REV-16 §4 补充、§9-8）。
11. **角色卡 `identity.attempt/session_id` 为 null**（复核 P2-2）：卡片投影不接 request/result，补需跨层接线（另开小片）；界面显示"尝试未知"（REV-16 §9-12）。
12. **`explain.entries[].availability` 转发口径**（复核 P2-7）：沿用既有服务端结论，不是新判据（REV-16 §9-13）。
