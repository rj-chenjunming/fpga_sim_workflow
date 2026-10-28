# S5+S6 计划 · dsh 受控准入（六节点）+ C2 取证 + 候选导入（同窗口、分两次收口）

> 日期：2026-10-28。状态：**进行中（C1）**。SpecDD ②产物：本条 + 人工裁决记录（§2）。
> 入口：[开工提示词 S4–S6](../agents/开工提示词_S4-投影取证与候选导入.md) §4.2/§4.3/§4.4；契约沿用
> [REV-13](../spec/SPEC-REV-13-20261026.md) §5/§10、[REV-14](../spec/SPEC-REV-14-20261028.md) §3/§6/§7、
> [SPEC-08](../spec/DSH_AGENT_RUNTIME_SPEC.md) §10/§12——**不新写替代契约**，缺口登记 §未决/STATUS。

## 1 切片

| 片 | 内容 | 退出条件 |
|---|---|---|
| **S5** | 受控准入分支（六节点）+ A2 请求字段 + `context_manifest_ref` + 双钉写档 + §7.3 停止执行 + C2 真机取证 | C2 证据齐全（DS-04/05/07 + DS-08/09/10 复验）+ 无 P0/P1 未决；四道门重跑；**单独提交** |
| **S6** | N6 候选导入（白名单+哈希+拒绝矩阵，DS-06）+ 真机候选写/导入取证 + 对照结论分级 | DS-06 拒绝用例 + 真机候选导入证据；对照无对照组 ⇒ 结论"证据不足"；四道门重跑；**单独提交** |

**串行纪律（§4.4）**：S5 退出门**未过** ⇒ 不开 S6 真机候选写；S6 的 C1 导入实现可并行。两次收口 = 两份证据目录 + 两段 STATUS + 两个提交，不合成"大提交"。

## 2 人工裁决记录（2026-10-28，本窗口；与 REV-14/体检表旧裁决的差异照实登记）

原话（人）：**「所有节点都要走 dsh 呀 且赋予读写权限 暂时不考虑额度时间限制」「统一都走 dsh」「只在对应的隔离工作区写」**
（并选定："全员 dsh，保留可回退"）。

| # | 裁决 | 与旧裁决的关系 | 落地要求 |
|---|---|---|---|
| **A1 节点范围** | **六个模型节点 N3/N6/N8/N10/N11/N12 全部显式用 dsh** | **扩**开工提示词 §4.2 的"首版只 N3 只读"；与体检表 **Q4**（默认后端仍 agently）**一致**：`default_backend` 不动，靠 `node_backends` 六条显式选择 | `SETTINGS.node_backends` 六条（Lead 改）；`select()` 受控准入分支；每节点 real 运行一次收口 |
| **A2 写权** | **写权只在每 attempt 隔离工作区内**；仓库/ENV_ROOT/`kb`/闸门/审计一律写不到 | 与红线 11、AGENTS §3 一致（不扩大对环境的写承诺）；把体检表 #6「副本内可读写」落到本阶段 | `sandbox-policy.mode` + `permission-presets.defaultPreset` **双钉 workspace-write**；越界读写**实测被挡**（DS-04/D11） |
| **A3 额度** | **暂时不设调用次数/时长硬上限** | **改**本计划原拟的"12 次/1 h"上限 | 不设硬上限 ≠ 不记账：真实调用数/token/耗时逐次如实记账（SPEC-08 §12.2 口径），不可得标 unknown |
| **A4 对照组** | **不再跑 Agently 对照组**（统一走 dsh） | **改**开工提示词 §4.3 的公平对照 | 无对照组 ⇒ 按 SPEC-08 §12.2「模型不可比/样本不足」行：**结论只能写"探索/证据不足"**，不得宣布采纳/节省成本；数据表字段仍登记（§4） |

**未放宽**：`default_backend` 仍 `agently`（可一键回退）；不推送；不声称 E（内网业务）；**准入 ≠ 默认**；未通过自检/端口/指纹任一条件仍 `BackendUnavailable`，不静默回退 Agently。
**残余风险（照旧记档）**：D1 —— 同 uid 可经 `/proc/<dsh-pid>/environ` 读 key，不称已解决；bwrap 只挡宿主数据与 env 清洗。

## 3 S5 落点与验收

| 项 | 落点（唯一 writer：`s5-admit`） | 验收 |
|---|---|---|
| 受控准入分支 | `loop/host/agent_backends/__init__.py` | enabled + `DshConfig.verify(wrap_required=True)` + DS-08/09 自检 + 版本/指纹 ⇒ 返回 `DshBackend`；任一不满足 ⇒ `BackendUnavailable` 且可判；**不回退 Agently** |
| 六节点 | `node_backends` + `SETTINGS.yaml`（Lead 改） | 六节点各自 `select()` 返回 dsh；未列节点仍 default |
| mode 分层 | `select()` 与调用方 | **drill/standin 一律 agently 替身；real 才允许 dsh**；两种都是显式规则，不是静默回退（用例覆盖两态；全量 standin 门不得因准入而红） |
| A2 字段 | `BackendRequest` / 封存记录 | `contract_version/identity{run_id,node,attempt_key,generation}/execution_grant_ref/runtime_fingerprint/context_manifest_ref`；旧记录只读兼容 |
| 写档双钉 | `dsh_assets`/`dsh_selfcheck` | 档位缺失/不符即拒（DS-09）；宿主 settings/凭据不进 attempt home |
| §7.3 停止 | `agent_control` + dsh 进程管理 | 先撤销资格 → 停执行 → 确认后 `applied`；停止未知 ⇒ `execution_unknown`，不重发（DS-05） |
| C2 取证 | `doc/evidence/DSH_C2_<date>/`（Lead 冻结） | DS-04 越界读写实测被挡；DS-05 无后代残留；DS-07 压缩经 session log 落账；DS-08/09/10 真机复验；六节点各一次收口（真实调用数/时间/token 记账） |

## 4 S6 落点与验收

| 项 | 落点 | 验收 |
|---|---|---|
| 候选布局 | `dsh_assets` 的 `candidate/`（attempt 内可写；已预留） | 只在 `candidate/` 写；写入不越过 attempt 根 |
| Host 导入 | **确认执行停止后**按白名单 + 哈希导入；仍交原 `n6_apply` | 额外文件/符号链接/绝对路径/源漂移/校验后换件 ⇒ 拒绝（DS-06）；不新建第二套应用判据 |
| 真机候选取证 | 一次 N6 real 运行 | 候选由 Host 导入；拒绝矩阵中至少"额外文件/换件/漂移"各一次决定性证据 |
| 对照结论 | 本计划 §2-A4 | **无对照组 ⇒ "探索/证据不足"**；数据表字段登记但标 unknown/unavailable，不宣布收益 |

## 5 验证门（每片收口各自跑）

四道门（AGENTS §4；命令见开工提示词 §6）+ 浏览器门仅当 `loop/web/**` 或界面字段有改动才跑（S5/S6 预计不动界面 ⇒ 不跑，照实记）。证据目录冻结 444 + md5 记在目录外；STATUS 新节只增（见 §6）。

## 6 STATUS 节号（本窗口实际使用）

§113 是交接节，§114 起递增：**§114 = S4、§115 = S5、§116 = S6**。
（开工提示词 §4.4 写的是"§114 = S5、§115 = S6"，那是假定 S4 另开窗口；本窗口三片都做，故整体顺延，差异在此登记，不静默改口径。）

## 7 未决（照实登记）

0. **工具白名单未实现（P1 gap，2026-10-29 C2 实测暴露）**：真机 `toolNames` 为全量 harness（26 项，含 `web_search/web_fetch/subagent/workflow/send_message/job_*/present`），REV-14 D4 的"工具白名单"**尚未落地**。C2 证据一律**不声称**工具白名单；收紧另立小片（S6 前评估），暴露面按实测记录。
1. 真实 DSH Web 实例的端口/令牌落账（`agent_instance.json` 写入方）——S5 真机接入后补齐；S4 反代缺失即 `target_missing`。
2. WebSocket/SSE 反代未支持（405）；S5 实测 DSH Web 是否需要后再定。
3. 子 agent 配额实际生效值需运行时回显（REV-14 D4）；本轮不放开成本测量。
4. 压缩后覆盖责任收缩为"Host 输入包 + 提交回传"（REV-14 D2），不声称"读完材料已证"。
5. 对照试验（SPEC-08 §12）本轮**不做**（无对照组）；若后续要归因，需另行登记阈值与 Agently 控制臂。
6. **attempt `input/` 不含目标用例源件（S6 真机两次失败的根因，2026-10-29 实测）**：`INPUT_MATERIALS` 只含 run 产物（n1/n2/n5/doc_entries），而候选通道要求模型写"整份 `candidate/TESTLIB/<case>.sv`" ⇒ 模型拿不到基线全文，只能猜或扫宿主 FS（两次 300 s 超时、0 候选）。修法：对 N6 把 `n6_targets` 指向的用例源件**只读**纳入 `input/`（白名单、md5 入记录、不放宽任何导入判据）。
7. **工具白名单仍未实现**（S5 C2 实测 `toolNames` 为全量 harness 26 项）；收紧需另立 tool-allowlist 插件小片（`toolAllowlist` 无廉价配置键）。
