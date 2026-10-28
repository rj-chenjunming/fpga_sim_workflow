# S1 实施切片：DSH 执行器进程与协议（2026-10-28）

> 依据：[REV-14](../spec/SPEC-REV-14-20261028.md)（D1/B4/B5/B8、DS-08/09/10）、[REV-13](../spec/SPEC-REV-13-20261026.md) §5、[设计 P4](../plans/2026-10-26-cloud-dsh-memory-design.md)、[P0 证据](../evidence/DSH_P0_20261028/README.md)。
> 状态：**机制层已实施（S1，2026-10-28）**，真机包裹集成已验；不切换业务节点，`dsh` 仍是显式不可用后端（`BackendUnavailable` 不变）。实测与门见 [STATUS §109](../STATUS.md)。

## 1 范围

| 做 | 不做 |
|---|---|
| `dsh_process`：每 attempt 一个受管进程（bwrap 包裹、env 白名单、超时、`TERM→KILL` 进程组、attempt 标签） | 不接真实模型做业务（C2 不在本片） |
| `dsh_protocol`：headless NDJSON 帧解析、身份/终态判定、失败分类（坏帧/无终态/重复终态/拒绝/超时） | 不实现 sdk stdio JSON-RPC 全链路（B4 的观测面在 S2 接） |
| `dsh` 后端骨架：实现 `AgentBackend` 协议，`execute` = 起进程→收事件→按终态出 payload；**不进入 `select()` 的可用路径** | 不改节点语义、不改 `model_steps` 校验 |
| 配置锁定：dsh 版本/指纹未匹配 ⇒ 显式拒绝 | 不改 `kb/`、不改闸门 |

## 2 失败语义（固定诊断，不猜成功）

| 情形 | 结果 |
|---|---|
| 坏 JSON 帧 / 未知事件类型 | `BadFrame`，显式失败（不忽略坏行） |
| 无 `turn_end`（含被 SIGTERM 打断） | `NO_TERMINAL`，失败；**退出码 0 / 空 final 都不算成功** |
| 重复且冲突的 `turn_end` | `CONFLICTING_TERMINAL`，失败 |
| `turn_end.reason.kind=error`（模型拒绝/缺凭据） | 保留 `code` 与脱敏 message，失败 |
| 超时（`timeout_s`） | `TERM` → 宽限 → `KILL` 进程组；`STOPPED_ON_TIMEOUT`，失败 |
| 停机后仍有子孙 | `LEFTOVER_CHILDREN`，失败（`execution_unknown` 语义） |

## 3 bwrap 包裹（B8，只对 `wrap=true`）

```text
env -i HOME=<attempt-home> PATH=<minimal> DSH_HOME=<attempt-home> PUBLIC_API_KEY=<env-only> <proxy…>
bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp
      --tmpfs <原 HOME> --bind <attempt-dir> <attempt-dir>
      --unshare-pid  (实现时按需；P0 已证明 pid ns 挡不住 /proc environ，残余风险记档)
      node <dsh-bin> --profile headless --patch <public.yml> [--patch <submit.yml>] --json "<task>"
```

- 只 bind **attempt 工作副本** 与 `DSH_HOME`（P0：宿主 home 遮蔽后 `AGENTS.md` 不可读）；
- `PUBLIC_API_KEY` 只进 env、不落文件；工具 env 由 dsh 剥离该变量（P0 实测 `KEYLEN=0`）；
- **不声称**挡 `/proc/<dsh-pid>/environ`（残余风险，REV-14 D1/B8）。

## 4 测试策略（不烧模型、不依赖真 dsh）

用 **python stub** 冒充 `dsh` CLI，按 `STUB_MODE` 产出 NDJSON：`ok` / `badframe` / `no_terminal` / `dup_terminal` / `refuse` / `hang`。
`dsh_process` 的 `wrap` 可关闭（单测跑 stub），另有用例只断言"bwrap argv 组成"（不执行）。

| 用例 | 断言 |
|---|---|
| ok | 终态 `completed`，文本与 usage 取到 |
| badframe | `BadFrame`，失败且不返回候选 |
| no_terminal（含被 TERM） | `NO_TERMINAL`，退出码 0 也不算成功 |
| dup_terminal | `CONFLICTING_TERMINAL` |
| refuse（`reason.kind=error`） | 失败，`code`/message 保留、secret 被 redact |
| hang | 超时后 `STOPPED_ON_TIMEOUT`，进程组无残留（stub 起一个 sleep 子孙验证 `KILL`） |
| wrap argv | 含 `env -i`/`bwrap`/`--tmpfs $HOME`/`--bind attempt` 且不含宿主 home 的写挂载 |

## 5 退出条件（本片）

- 上表全绿；既有后端与模型节点行为不变（`REG-01` 回归）；
- 未匹配锁定的版本/指纹时 `select()` 继续 `BackendUnavailable`（不因实现存在而放行）；
- 证据写 STATUS；不声称 C2/业务可用。
