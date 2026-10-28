# S6 证据档 · N6 候选导入（DS-06）· 2026-10-29

> 状态：**证据不足 / 探索（C1 软件层通过；真机候选导入 4 次均未达成，方案 B 定稿，无第 5 次）**。
> 执行者：S6 实现 owner（C1）；Lead 授权 4 次真实 N6 调用（第 4 次为最终次）。目录只增不改；
> 冻结（444）与 `doc/evidence/DSH_S6_20261029.md5` 由 Lead 在提交前一次完成（本文件最后更新后不再改）。
> 关联：S5/S6 计划 §4、SPEC-REV-13 §5.4/§10 DS-06、SPEC-REV-14 B1/B3·D04、SPEC-08 §4/§10 D04/§12.2。

## 1 结论（三态，按 SPEC-08 §12.2「无对照组」口径）

| 项 | 结论 |
|---|---|
| C1 候选导入判据（白名单/路径/链接/额外文件/哈希/大小/停止确认/源漂移/覆盖 + 施加阶段 `EDITS_MISMATCH`） | **通过**（软件层：`tests/test_agent_candidate_import.py` 52 passed） |
| 真机 N6：模型写 `candidate/` → Host 导入 → `n6_apply` 落沙箱 | **未达成**（4 次真实调用均失败；第 4 次已产出真实候选但提交格式不合规） |
| 真机侧拒绝矩阵（在成功 attempt 的真候选上篡改） | **未执行**（无"成功 attempt"的候选）；**补充证据**见 §4（真实候选字节来自 `validation_failed` attempt，3/3 拒绝） |
| 效果/成本对照 | **不作结论**（无对照组；usage 全程不可得，标 unknown） |

**不声称**：不声称 DS-06 真机通过、不声称候选导入在真实模型上可用、不声称任何成本/质量收益。

## 2 四次真实调用事实（未重试；`raw/attempts.jsonl` **只增不改**，4 行逐字记账）

| # | run/attempt | 上限 | wall_s | exit / 结果 | 候选 |
|---|---|---|---|---|---|
| 1 | `RUN-20261029-S6-01/N6/1` | 120 s | 120.192 | failed（`interrupted`/`CancelledError`） | 0 件 |
| 2 | `RUN-20261029-S6-02/N6/1` | 300 s | 300.367 | failed（`interrupted`/`CancelledError`） | 0 件 |
| 3 | `RUN-20261029-S6-03/N6/1` | 300 s | 300.185 | failed（`interrupted`/`CancelledError`） | attempt/candidate 0 件；`work/candidate` 有 15701 B 草稿 |
| 4 | `RUN-20261029-S6-04/N6/1` | 300 s | 127.76 | failed（`validation_failed`） | **`work/candidate/TESTLIB/tc_bmc_i2c_03.sv` 15647 B** |

- 记账：4 次 `usage` 全 `unknown`（无终态 usage 帧或提交被拒）；`session_id` 全 `unknown`。
  `raw/attempts.jsonl` 是**只增不改**的原始记账；**run4 的 `candidate_files=[]` 是探针旧路径 bug**
  （探针按旧布局 `attempt/candidate` 列目录）。更正见 **`raw/attempts_corrections.jsonl`**
  （一行：`attempt_key=…S6-04/N6/1`、`field=candidate_files`、`observed=1`、
  `path=work/candidate/TESTLIB/tc_bmc_i2c_03.sv`、`bytes=15647`、`reason="探针旧路径 bug，非无候选"`）；
  **原行不回填/不改写**。
- 超时口径：1–3 次上限由探针外层 `asyncio.wait_for` 施加（wall 120.192/300.367/300.185 证明闸门生效）；
  `SETTINGS.dsh.timeout_s` 仍为 600（被取消时 dsh 自身超时未到）。第 4 次未到上限（127.76 s 自然结束）。
- 真机形态 4 次都成立：`agent_workspaces/N6/attempt-000001/{work,dsh-home,candidate,input,plugin,patches,selfcheck}`；
  自检 `workspace-write` 双钉 + `attemptKey` 与请求一致（`raw/n6_selfcheck_summary_run*.json`）。
- 提示词/输入生效（封存 request，`raw/n6_attempt_record_run*.json`）：候选规则、禁扫宿主 FS、
  `instruct` 先写候选、`write_scope_rule`、`input.workspace`（含 `source_files`）均在。

## 3 根因链（有帧/文件证据；不是"模型瞎逛"）

**① 第 1–2 次：candidate 不在 OS 绑定内 ⇒ 包裹内不可见。**
探针工作区在 `--tmpfs $HOME` 遮蔽范围内；当时 `_spec` 只绑 `work`/`dsh-home`（rw）、`input`/`plugin`/`patch`（ro）、
`selfcheck`（rw），**candidate 未绑定** ⇒ 包裹内不存在该路径。离线 bwrap A/B（复刻当时绑定）：
写 `<attempt>/candidate/probe.sv` ⇒ `No such file or directory`、0 件；追加 `--bind candidate` ⇒ rc=0、文件落盘。
会话侧：run1 166 帧/16 step/27 次 bash（含 `find / … -name TESTLIB`）；run2 已给 `input.workspace` 路径
（275 帧/30 step/42 bash+1 job_output，首条命令即 `ls ../candidate` 但看不到），仍去宿主机找 —— 与"候选不可见"一致。
**修复**：s5-admit 增 `write_dirs=(layout.candidate,)`（只挂 candidate 一层，`input/` 仍只读）；
`raw/n6_offline_verify_run4.txt` 记录修复后 OS 层 A/B 通过（相对+绝对可写、`input/` 只读）。

**② 第 3 次：修好 OS 绑定后暴露"应用层"边界 `workspace-write` 只覆盖 cwd。**
run3（`raw/n6_session_summary_run3.json`）：250 帧/34 step/37 工具调用；模型**读到源件**（`read input/TESTLIB/…`）、
算出候选并写出 **`work/candidate/TESTLIB/tc_bmc_i2c_03.sv` 15701 B**；但写 attempt 根 `candidate/`（当时布局）时：
- `approval/asked`（bash，+131 s）理由："escalate sandbox to danger-full-access: 候选文件必须写到 attempt 根下 candidate/TESTLIB/，
  默认 workspace-write 只覆盖 work 目录" ⇒ `approval/decided outcome="unavailable"`（headless 无审批人）；
- `approval/asked`（write，+144 s）同理由 ⇒ 同样 `unavailable`；
- 模型退回相对路径写 `work/candidate/`（成功），反复复核至 300 s 被停止，**始终没写进 attempt/candidate、没调 `submit_result`**。
⇒ **应用层沙箱边界 ≠ OS `--bind`**；只有真实 attempt 才能观察到（离线 A/B 只证 OS 层，本档如实标注该边界）。
**修复**：Lead 裁决布局改为 `candidate = work/candidate`（s5-admit 落地 `AttemptLayout`/`check_layout`/`write_dirs`）。

**③ 第 4 次（最终）：三座山已翻（OS 绑定、应用层边界、时间预算），剩余是模型输出合规。**
run4（`raw/n6_session_summary_run4.json`）：81 帧/8 step；工具 bash 9 + read 1 + **submit_result 1**；**无 approval**；
`work/candidate/TESTLIB/tc_bmc_i2c_03.sv` **15647 B** 写在正确位置（新布局生效）、`work/payload.json` 3407 B 为**合法 dict**
（`revisions` 1 条 2 edits + `observation_points` + `notes`）；**127.76 s 自然结束**（远低于 300 s）。
失败点两处，均为 Host **正确 fail-closed**：
1. 模型把 `submit_result.payload` 传成 **JSON 字符串** ⇒ `dsh_protocol` 提交门 `BadSubmission`：
   "payload 必须是 JSON 对象（实际 'str'）" ⇒ `validation_failed`（不得把字符串当结构化结果，DS-02/DS-07）；
2. 即使按对象提交，其 `edits[0].line=218` 与实际 **217** 不符 ⇒ `apply_edits` 的行号漂移判据会拒（同样 fail-closed）。
⇒ 真机 DS-06 **未达成**，原因落在模型输出合规，而非接线/判据；**无第 5 次调用**（Lead 裁决方案 B 定稿）。

## 4 补充证据：真实候选字节上的导入判据（**不是** DS-06 真机通过）

来源：第 4 次 attempt 的真实候选 `work/candidate/TESTLIB/tc_bmc_i2c_03.sv`（15647 B）**复制**到 tmp 真机形态副本，
用生产导入判据离线核验（不调模型），原始输出 `raw/n6_real_candidate_tamper_run4.txt`：
- ① 加一个清单外文件 ⇒ `extra_file`（拒绝）
- ② 快照后改一字节 ⇒ `hash_mismatch`（拒绝）
- ③ baseline 声明与现算不符 ⇒ `source_drift`（拒绝）
- 对照（未篡改）⇒ `ok=True`
另：`raw/n6_offline_verify_run4.txt` 记录第 4 次前的三项离线复验全绿（布局字段/反推、OS 相对+绝对可写且 `input/` 只读、
四键→`n6_apply` 端到端 `source=candidate_import`）。
**标注**：上述证据来自一次 `validation_failed` 的 attempt 的真实产物，只能证明"导入判据在真实字节上有效"，
**不能**写成"DS-06 真机通过"；整链 `n6_apply` 在 run4 上被模型 edits 行号漂移挡住（Host 正确 fail-closed）。

## 5 边界（必须与上文一起读）

1. **模型声明候选清单未实现**：N6 schema 没有 `candidate_manifest` 字段；生产的 `candidate_manifest` 由 Host 在
   **停止后快照**生成、键来自合同（`TESTLIB/<case>.sv`），不是模型声明。
2. 因此 DS-06 的"校验后换件"在真机上的决定性形态只能是：**停止快照（manifest 值） vs 导入时复算**之间的窗口。
   四次尝试都没有发生"成功 attempt 的导入"，**没有 DS-06 真机换件证据**；§4 的 `hash_mismatch` 是
   在真实候选字节上人为制造该窗口得到的**补充证据**，不得冒充真机通过。
3. `execution_state='stopped'` 判据（进程退出 + payload 无 `execution_unknown`）与源漂移判据只有 C1 单测覆盖；
   四次均无 live out ⇒ 未观测到该字段在真实候选导入路径上的取值。
4. 「真机侧拒绝矩阵在成功 attempt 上执行」**未做**；C1 的 52 个用例与 §4 补充证据可独立引用，但不替代 DS-06 真机证据。

## 6 未做 / 收口

1. **没有第 5 次真实调用**（Lead 裁决：第 4 次仍失败 ⇒ 方案 B 定稿）。
2. 未为凑通放宽预算/判据/白名单，未改 prompt 措辞或删断言；失败一律如实记录、usage 不可得标 unknown。
3. `raw/attempts.jsonl` **只增不改**；run4 的更正以 `raw/attempts_corrections.jsonl` 为准（见 §2）。
4. 证据目录冻结（444）与 md5：由 Lead 在提交前一次完成；本 README 与 `raw/` 在该时点后不再变动。

## 7 复现与索引

- 探针：`raw/probe_s6_n6.py`（无凭据；`--dry-run` 不调模型；`--run-id`/`--timeout` 参数化；`--timeout ≤300` 断言）。
  工作区（gitignore）：`loop/.logs/s6/ws-real{,2,3,4}/`（含 session log）。
- 记账：`raw/attempts.jsonl`（4 行，只增不改）、`raw/attempts_corrections.jsonl`（run4 探针 bug 更正）。
- 每轮：`raw/n6_params_run{1..4}.json`、`raw/n6_result_run{1..4}.json`、`raw/n6_attempt_record_run{1..4}.json`、
  `raw/n6_selfcheck_summary_run{1..4}.json`、`raw/n6_control_events_run{1..4}.json`、
  `raw/n6_session_summary_run{1..4}.json`、`raw/n6_candidate_listing_run{1..4}.txt`。
- 第 4 次专项：`raw/n6_run4_model_payload_summary.json`、`raw/n6_run4_workspace_files.txt`、
  `raw/n6_offline_verify_run4.txt`、`raw/n6_real_candidate_tamper_run4.txt`。
