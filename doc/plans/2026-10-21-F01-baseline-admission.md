# F01 基线准入与全链身份 · 切片计划

> 承接 [优化与重构执行手册](OPTIMIZATION_PLAYBOOK.md) 批次 A 首包（F01-a/b/c）。**本文件只登记本切片的规格、落点、验收与实测**；整体路线仍以手册为准，数字只回填 [STATUS](../STATUS.md)。

| 项 | 内容 |
|---|---|
| 类型 | 缺陷修复（含一处保持行为的判据收敛） |
| 基线提交 | `fb83ed0` |
| 唯一 owner | Host 准入与编排 owner（本切片由 Lead 实现，未指派独立验证者） |
| 规格位置 | [编排规格 §3.1](../spec/LOOP_ORCHESTRATION_SPEC.md#31-基线准入与身份f01)、[Web UI §6.1 / §9](../spec/WEB_UI_SPEC.md) |
| 允许修改 | `loop/host/baseline.py`（新增）、`loop/host/paths.py`（公开只读入口 `kb_module()`）、`loop/services/config_api.py`、`loop/workflows/main_flow.py`、`loop/workflows/chunks/host_steps.py`、`loop/tests/test_baseline_admission.py`（新增）、上述两份规格、本计划 |
| 不修改 | 冻结目录 `kb/**`、`doc/evidence/**`、`doc/history/**`、执行拓扑、闸门签署、S0、仿真资产 |

## 1 问题与触发示例

已复现（[复核 §F01](../audit/AUDIT-20261021-post-ui-roadmap.md)）：

1. `<WORKSPACE_ROOT>/baselines/vX/manifest.json` 为 `{}` 时，`GET /api/baselines` 仍返回 `valid=true`。
2. manifest 为数组时，`list_baselines` 里 `doc.get(...)` 抛 `AttributeError` ⇒ 端点 500。
3. 受控探针截获 real N2：请求 `v-next`，实际 `--from-baseline v0`（[host_steps.py](../../loop/workflows/chunks/host_steps.py) 硬编码）。
4. `RunManager.start` 在创建运行目录、隔离残留投影、写事件流、申请单槽**之前**不校验基线。

## 2 目标可观察行为

- `GET /api/baselines`：坏件一律 `valid=false`，`missing` 列缺失件、`errors` 列 schema/身份/指纹/parent 链违规；不抛 500。
- `POST /api/runs`（`mode=real`）：非法/未知/不完整基线 ⇒ `400`，且**零副作用**（不建 run 目录、不隔离投影、不写事件、不占槽）。
- `mode=real` 下 N2 使用选中基线：`--from-baseline <选中>`，不再出现硬编码 `v0`。
- `mode=drill` 行为不变（不读基线资产，不因缺基线失败）。

## 3 不变量

1. **唯一判据**：列表与准入调用同一个 `loop/host/baseline.py`；API 层与编排层不得各写近似规则。
2. **只读**：准入不写任何文件（含不写字节码）；`list_baselines` 仍不创建目录。
3. **身份单一来源**：入口解析一次，N0→N1→N2→投影消费同一值。
4. **失败显式**：`missing`/`errors` 为空才 `valid`，不得用空数组冒充成功。

## 4 切片与验证

| 切片 | 内容 | 验证 |
|---|---|---|
| F01-a | 规格 §3.1 + 本计划 | 文档链接/锚点可达 |
| F01-b | 失败用例：空对象、数组、缺件、身份不符、指纹不符、parent 断链、准入零副作用、N2 身份 | 先红（记录输出） |
| F01-c | `host/baseline.py` + 三处接线 | 目标集合转绿；既有 drill 用例不回归 |
| F01-d | 内网一次真实**非默认**基线整链（工具实际消费） | **阻塞**：缺内网环境与有效非默认基线，不在本轮声称完成 |

## 5 实测（数字从命令输出复制）

| 验证 | 原始输出 | 结论 |
|---|---|---|
| 修改前红灯（回退三处接线） | `10 failed, 2 passed in 0.74s` | 三个缺陷先复现 |
| 修改后新用例（含独立复核补充 5 项） | `17 passed`；定向 `24 passed in 0.64s` | 转绿 |
| N1 身份相关既有用例 | `16 passed, 23 deselected in 1.16s` | 节点层去兜底后仍通过 |
| 真实基线 v0 | `v0 valid= True missing= [] errors= [] cases= 162 rtl_bytes= 2570240` | 不误伤既有基线 |
| 全套单测 | `46 failed, 269 passed, 3 skipped, 1 warning in 11.26s` | 46 项与拉取后基线同因（`ENV_ROOT` 只读），无新增回归；通过数 252→269 = 新增 17 项 |
| 独立复核 | `f01-verifier`：首轮「不建议合并」→ 必改 3 项修复 → 二轮「可合并」，见 [STATUS §14](../STATUS.md#14-f01-基线准入与全链身份2026-10-21) | 自测与复核分离记录 |

未运行：kb 自测、端到端、F01-d 内网真实非默认基线整链。实测全文见 [STATUS §14](../STATUS.md#14-f01-基线准入与全链身份2026-10-21)。

## 6 未决（本轮不做，已登记）

1. `services/contracts.py::baseline_chain()` 是第二套 manifest 扫描（无 schema/指纹），应改为复用 `host/baseline.py`。
2. `kb/tools/` 子进程调用未加 `-B`：既有行为，会向冻结目录写 `__pycache__`（与本切片无关，属验证工具治理 F03/F15-b）。
3. `/api/baselines` 失败时的 detail 未附 `missing/errors`（前端已展示 `missing`，`errors` 待接入）。
4. 超大文件哈希上限未设（本地基线制，风险低）。
5. `_selected_baseline` 对 drill 的 N1 也生效（生产由 `RunManager.start` 注入，属收紧，已在规格语义内）。

## 7 回退

按切片还原 `host/baseline.py` 与三处接线，保留「拒绝非法基线」的阻断行为，不回退或改写任何历史基线与账本。
