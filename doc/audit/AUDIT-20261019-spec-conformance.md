# 规格一致性审计（2026-10-19）

> **一句话结论**：拓扑与 pause/resume 形状做得扎实；但 **real 链路未闭合**、**失败路径会产生僵尸 run / 孤儿签名 / 单槽泄漏**、**模型输出缺少消费者与阻断**。共登记 **约 170 条**（49 + 44 + 77），去重后**阻断级 22 条**、重要级 40+ 条。
>
> **本轮是否修复**：**否**。本轮只做「结构整理 + 偏差登记」；代码缺陷由对应 owner 另开一轮修复。任何「系统已合规」的表述都不成立。

---

## 1 范围与方法

| 维度 | 内容 |
|---|---|
| 审计对象 | 本仓 `loop/`（编排 886 + chunks 1147 + host 1513 + prompts 221 行）、`kb/`、三份 `doc/spec/*.md`、全部 README |
| 对照基准 | `doc/spec/CHANGE_IMPACT_LOOP_SPEC.md`（业务/I1–I8/N0–N16）、`doc/spec/LOOP_ORCHESTRATION_SPEC.md`（机制/生命周期/恢复/投影）、`doc/spec/ENV_PLUGIN_SPEC.md`（三根/插件契约） |
| 方法 | 三路独立只读审计并行：① spec↔实现逐条核对；② Agently 设计（加载 `agently` / `agently-design` / `agently-triggerflow`，对照 4.1.4.8 源码与 `to_mermaid()` 实测拓扑）；③ 文档/结构/路径/计数一致性 |
| 证据等级 | `[已确证]` = 直接读码/实测/命令输出；`[待核]` = 需并发、真机或跨仓验证 |
| 采样时 HEAD | `dc7c69e`（13 commits） |
| 未做的事 | 没跑端到端终验（需写 ENV_ROOT，本会话沙箱只读）；没跑真实全跑；没改任何代码 |

## 2 统计

| 来源 | 数量 | 阻断 | 重要 | 轻微 | 待核 |
|---|---|---|---|---|---|
| A. spec ↔ 实现 | 49 | 14 | 23 | 8 | 4 |
| B. Agently 运行时 | 44 | 5 | 23 | 14 | 2（部分重叠） |
| C. 文档结构 | 77 | — | ~30 | ~40 | 5 |
| **去重后阻断级** | **22** | 见 §3 | | | |

> 说明：C 组含**本轮已执行**的整理动作（迁移/导航/数字纠偏），未执行项在附录里单独标 `[未执行-需授权]`。

## 3 阻断级总表（去重）

> 「来源」列指向附录条目编号：`A-*` = `parts/spec-conformance.md`，`B-*` = `parts/agently-runtime.md`，`DOC-*` = `parts/docs-structure.md`。
> 同一缺陷被两路独立发现时在「来源」列并列 —— 这提高可信度，不重复计数。

| # | 缺陷 | 证据 | 后果 | 来源 |
|---|---|---|---|---|
| 1 | **N8 模型调用/校验失败默认 `pass`** | `chunks/model_steps.py:519-525` | 静态复核被跳过，带故障直接进 19min–22.8h 全跑 | A-C3 / B-B1 |
| 2 | **单槽队列只有排队、没有唤醒** | `chunks/long_jobs.py:41-47`、`host/admission.py:263-294` | 第二个 run 永久停放并占槽，后续全排队；`cancel_pending` 无调用者 | A-C2 / B-B2 |
| 3 | **N6 不产出沙箱用例，N9 静默回落未修订 TESTLIB** | `chunks/model_steps.py:409-443`、`chunks/long_jobs.py:88-93` | 全跑证据与「修订已生效」的结论不符 | A-A6/A-A7 / B-B3 |
| 4 | **闸门「先签后恢复」失败即楔死** | `main_flow.py:443-449`、`chunks/gates.py:137-163` | 中断已消费 + 账本孤儿签名 + 永远 running；G1=ignored/disputed、G2=rework 分支不可达 | A-C1 / B-B4 |
| 5 | **单槽 lease 按进程判活，重启可抢占在跑作业** | `host/admission.py:204-213,77-95` | 两仿真并发踩 `uvs.setup`；恢复不复核本 run 是否仍持锁 | A-C2 / B-B5 |
| 6 | **real 链路断裂（N1 缺 `--parent`）** | `chunks/host_steps.py:120` | `n1_snapshot.py stage` argparse rc=2，real 必挂 | A-A19 |
| 7 | **real 链路断裂（N7 不编译）** | `chunks/host_steps.py:245-247` | 找不存在的 `kb/tools/compile_only.sh`，只记 note `rc=None`，无卡点 B 证据 | A-A5 |
| 8 | **real 链路断裂（N9 固定用例）** | `chunks/long_jobs.py:20,33,63,91-109` | 固定 `tc_pcie_rw_02/seed1`，忽略 N5/N6 目标集 | A-A7 |
| 9 | **real 链路断裂（N15 不执行）** | `chunks/long_jobs.py:225-259` | 只 emit `job_progress(provisional=True)`，无回归证据 | A-A15 / B-I13 |
| 10 | **I1 未决条目未阻断 + 闸门材料不全** | `chunks/gates.py:98-176`、`host_steps.py:165-174` | 有未决也能确认并进 N5/N6；G1/G2/G3 材料远少于 spec | A-A1/A-A2/A-A23 / B-I9 |
| 11 | **I2 用例态无写入者** | `model_steps.py:661`、`services/contracts.py:67-80` | 全仓无 `case_states.json` 写入者；real N16 恒 rc=3 | A-A3 |
| 12 | **I3 印记三向一致未进 verdict** | `host/evidence.py:33-35,225-240` | 只判 UVM 汇总+两计数；期望地址/值硬编码 | A-A4 |
| 13 | **I4 在 N16 不校验** | `chunks/host_steps.py:266-272` | `G3=milestone/defer` 时 72 条 `blocks_release` 可绕过 | A-A18 |
| 14 | **I8 无真实晋升、无独立人触发** | `chunks/host_steps.py:274-290`、`main_flow.py:77-79` | N16 恒 `--dry-run`，由 G3 分支自动进入 | A-A12 |
| 15 | **N11 = 证据守护缺失** | `main_flow.py:69`、`model_steps.py:613-637` | 业务 N11 的「成链/不成链」被替换为评估，且不驱动回边 | A-A10 |
| 16 | **失败/中止的 run 从不 `async_close`** | `main_flow.py:304-313,811-832` | 框架置 FAILED 后 `is_waiting/is_closed` 皆假 ⇒ 永远 running、重启当 running 恢复 | B-I2/I3 |
| 17 | **恢复失败分支只写报告不改状态** | `main_flow.py:654-660,676-684` | 把崩溃/恢复失败伪装成「在等人工」 | B-I1 |
| 18 | **N3/N10/N12 输出无消费者、不落盘** | `model_steps.py:367-403,603,643-687`、`contracts.py:376-429` | 「分类 2/3 进待裁决清单」「报告引用可解析」均未实现 | B-I8 / A-A9/A-A20 |
| 19 | **conflicts 永久缓存 ⇒ I4 冻结在启动时刻** | `contracts.py:53-65`、`main_flow.py:175` | 人工清零后仍拒，新出现的 blocker 被忽略（放行方向不安全） | B-I7 |
| 20 | **单槽泄漏（submit/park 异常无 finally）** | `long_jobs.py:103-127,141-144` | 槽永久泄漏，后续全部卡在 `SLOT:` 中断 | B-I4 |
| 21 | **N16 身份语义矛盾** | `host_steps.py:274-283` | `--actor-kind human` 硬编码，与真实签署者脱钩 | B-I20 / A-C9 |
| 22 | **I7 计数三处边界不一致 + N6 自增** | `model_steps.py:526`、`contracts.py:229`、`n16_promote.py:165`、`model_steps.py:416,441` | `>=`/`>=`/`>` 混用；首次修订就自增，人工返工可能提前触发升级 | A-C5/C6 |

## 4 重要级主题（不逐条，详见附录）

| 主题 | 要点 | 附录 |
|---|---|---|
| 生命周期收敛 | 快照非原子/无 `RecordStore`；失败 run 不 close；`_status_of` 可能把失败显示成等待 | A-A16 / B-I2/I3/I6 |
| 单槽与准入 | N7 不走单槽；`holder_alive` 指进程；死锁回收两步非原子；同 job_id 直接 granted | A-A5 / B-I12/I14 |
| 模型契约 | prompt 引用不存在的 input 字段；N8 `offered={}` 无成员性校验；N12 子串判「跑通」；`mode` 失败也标 live | B-I14/I15/I16/I22 / A-A24 |
| 投影一致性 | 同一数字两条抽取路径；`waiting_gate` 泛化；白名单漂移；事件注入伪节点 | A-B1/B7/B8 / B-I18/I21/M1/M5 |
| 阻断与阻塞 | `subprocess.run` 在 async handler 内同步执行，阻塞事件循环 | B-I11 |
| 身份与证据 | 闸门 sign 未带证据指纹；human_signed 由自报 actor_kind 生成 | A-A17 / B-I7 |
| 文档结构 | 已执行：根 README/AGENTS/STATUS、导航、三处迁移、数字纠偏；未执行：跨仓去重、CLI 契约补齐、三根解析测试 | C 全部 |

## 5 交叉印证（两路独立发现同一缺陷）

这些条目可信度最高，建议优先修：

1. N8 失败默认 pass（A-C3 × B-B1）
2. 单槽队列无唤醒 + 无取消（A-C2 × B-B2）
3. N6 无沙箱 ⇒ N9 测未修订用例（A-A6/A7 × B-B3）
4. 闸门先签后恢复失败楔死 + 孤儿签名（A-C1 × B-B4）
5. 单槽按进程判活（A-C2 × B-B5）
6. I1 未决未阻断（A-A1 × B-I9）
7. N15 无证据（A-A15 × B-I13）
8. 恢复失败伪装等待（A-C13 × B-I1）

## 6 修复建议顺序（另开一轮）

1. **先让失败可见**：统一失败分支置 `failed` + `error` + `async_close`；恢复失败两分支改状态（#16/#17）。
2. **再补安全闸**：N8 失败不得分叉；闸门「先校验/先恢复、后签署」或事务化（#1/#4）。
3. **再修单槽**：lease 改为作业级 + 显式唤醒/取消 + `finally` 释放（#2/#5/#20）。
4. **再补 real 链路**：N1 `--parent`、N6 沙箱、N7 编译、N9 目标集、N15 `run_tc.py`（#6–#9）。
5. **最后补不变式与投影**：I1/I2/I3/I4/I8、N11 guardian、输出消费者与投影一致性（#10–#15/#18/#19/#21/#22）。

## 7 本次整理的验证基线

| 门 | 结果 |
|---|---|
| `pytest --collect-only` | 70 collected |
| `pytest`（可写 workspace 副本） | 67 passed / 3 failed（3 条均环境限制，见 `doc/STATUS.md` §3） |
| `_selftest_gate_schema.py` | 10/10（可写 workspace） |
| `_selftest_n5_reachability.py` | 9/9 |
| `accept_v1_run.sh` | 未复跑（需写 ENV_ROOT，本会话只读）；历史 117/117 |

## 8 附录

- `parts/spec-conformance.md` —— 49 条，A/B/C 三组，含逐条 `文件:行号` 与等级。
- `parts/agently-runtime.md` —— 44 条，B/I/M 三组，含 5 个阻断级的最小修复方向。
- `parts/docs-structure.md` —— 77 条，标注 `[已执行]` / `[未执行-需授权]`。
