# DSH P0 探测（2026-10-28，S1 前置）：能力清单与"真隔离"可行性

> 归档件，**只增不改**；原始输出在 `raw/`。一次性探针现场：`workspaces/.probe-dsh/`（gitignored）。
> 目的：为 [REV-13 §4/§5](../../spec/SPEC-REV-13-20261026.md) 的 P0 探测与 [REV-14 D1](../../spec/SPEC-REV-14-20261028.md) 的**复评前提**取证据。
> 纪律：只在本机 `0.2.1-rc.2` 上验，不代替目标环境；`$HOME` 只读、`~/.dsh` 零写入；未接内网工程。

## 1 能力清单（`raw/p0-manifest.txt`，机器可复算）

| 项 | 值 |
|---|---|
| node | `v24.21.0` |
| dsh `lib/bin.js` sha256 | `80112efe368efb1a39720c7ada0af00442e5131fb2744edaaff8a3e8bb499e6f` |
| 包 `package.json` sha256 | `ab51c256bf5c927a91c3af4fb1a9cf0fc2513618cf84b1f249eadad7efea2a87` |
| `package-lock.json` sha256 | `e242cda6888c94186a18d8b10d629483d6344fc20141793139f8f9ff21cd0d01` |
| bwrap / kernel | `bubblewrap 0.4.0` / `4.18.0-553.el8_10.x86_64` |
| sdk profile 组合树 | `raw/p0-sdk-config.yml`（409 行），sha256 `6e19a614ad803f1d8f362c96e79ec6f549d4b3a2334554397fbbd671cdb49234` |
| 工具面（dump-config 实测） | `tool-bash`、`tool-fs`、`tool-fs-search`、`tool-jobs`、`tool-pwsh`、`tool-skill`、`tool-subagent(+control/fork)`、`tool-todo`、`tool-web`、`tool-workflow`、`tool-goal`、`tool-working-directory`、`tool-workspace-dependencies`、`tool-call-timeout-policy` |

> 与探针 P2/P3 的差异：`tool-web`/`tool-workflow`/`tool-goal`/`tool-workspace-dependencies` 也在默认面里 ⇒
> 带工具准入**必须显式禁用**，不能假设默认只有 read/bash/edit（REV-13 §5.4 "**不能只对模型说不要用**"）。

## 2 P0-1 未包裹时 agent 能看到什么（`raw/p0-env-leak.ndjson`、`raw/p0-env-clean.ndjson`）

| 观测 | 结果 |
|---|---|
| agent 的 bash 继承 env 数 | **145**（含 `ALL_PROXY`、`HTTPS_PROXY`、`DSH_*` 等） |
| 其中是否含 `PUBLIC_API_KEY` | **否**（dsh 对工具子进程剥离了该变量；`KEYLEN=0`） |
| `~/.dsh/settings.yaml` 可读 | **是**（`RC=0`） |
| `~/.dsh/.credentials.yaml` | **可读，237 B**（`ls -ld` + `wc -c` 均 rc=0） |

⇒ 未包裹时：**凭据文件对 agent 可读**（env 里的 key 反而不可见）。D1 的风险是"文件可读"，不是"env 泄漏"。

## 3 P0-2 bwrap 包裹可行性（`raw/p0-bwrap-dsh.ndjson`）

命令形态（`env -i` 替代 bwrap 0.4.0 不支持的 `--clearenv`）：

```bash
env -i HOME=… PATH=/usr/bin:/bin DSH_HOME=… PUBLIC_API_KEY=… HTTPS_PROXY=… \
bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --tmpfs "$HOME" \
      --bind <attempt-dir> <attempt-dir> \
      node …/dsh/lib/bin.js --profile headless --patch … --json "只回复 OK"
```

结果：**`FINAL: OK`、`turn_end.completed`** —— dsh（含其自带 sandbox 的嵌套 bwrap）在包裹内能正常跑、能调模型。

## 4 P0-3 包裹内的可见面（`raw/p0-bwrap-agent.ndjson`、`raw/p0-bwrap-home-mask.ndjson`）

| 观测 | 包裹内结果 |
|---|---|
| `~/.dsh` 内容 | **空**（tmpfs 遮蔽；目录里只有 `.`/`..`） |
| 凭据文件 | 不可读（所在路径被遮蔽） |
| `PUBLIC_API_KEY` 在工具 env | **无**（`KEYLEN=0`） |
| 宿主 home 其他内容 | **隐藏**：`ls /home/work/chenjunming` 只看到显式 bind 回的那个目录；`AGENTS.md` ⇒ `No such file` |
| `pwd` | attempt 工作副本绝对路径（未被替换） |

## 5 P0-4 决定性反例：`/proc/<dsh-pid>/environ` 可读（`raw/p0-proc-env.ndjson`）

包裹内 `ps` 显示 `1 bwrap / 2 bash / 5 bwrap / 6 MainThread`；agent 的 bash 在 `/proc/6/environ`
里**命中 `PUBLIC_API_KEY`**（`LEAK:/proc/6/environ`），而 `/proc/1/environ` 命中 0。
⇒ **同 uid 下，bwrap 的 pid/mount namespace 挡不住"读父进程 environ"**；只要 key 在 dsh 进程 env 里，
agent 就能拿到。这是 P0 最重要的否证。

## 6 结论（三态）

| 问题 | 结论 |
|---|---|
| 能否挡"读宿主其他数据" | **能**（`--ro-bind / /` + `tmpfs` 遮蔽 + 只 bind attempt 目录；实测 host home 隐藏、`AGENTS.md` 不可读） |
| 能否清"无关 env" | **能**（`env -i`；工具 env 仅剩显式传入项，且 dsh 自身还剥离 `PUBLIC_API_KEY`） |
| 能否挡"原始凭据对 agent 可读" | **不能**（`/proc/<dsh-pid>/environ`；同 uid） |
| 对 REV-13 §5.4 的意义 | "无法阻止读取原始秘密"这一条**仍成立** ⇒ D1 不能仅靠 bwrap 复评恢复；**要么** Host 代理上游 key（dsh 不持 key）**要么** 用不同 uid/容器**要么** 维持 D1 偏离并记档 |

## 7 建议（待裁决，按代价从低到高）

1. **维持 D1**，但把 bwrap 包裹作为**缓解**（挡宿主数据 + 清 env），并在规格里写明残余风险"key 可经 `/proc` 读出"；
2. **升级为 Host 代理**（REV-13 的第三条路）：dsh 只持"Host 签发的短期凭证/本地代理地址"，上游 key 留给 Host；代价是新增代理层与协议；
3. **不同 uid/容器**跑 dsh：本机无 root，需容器运行时（Podman/rootless 亦需额外条件），S1 不现实。

## 8 未验证 / 限制

- 未在目标环境（云端/内网）复测；本机版本 `0.2.1-rc.2` 结论不外推。
- `--ro-bind / /` 仍暴露只读系统面（`/usr`、`/etc` 等）；"允许清单"式最小挂载（只 bind node 树/必要 lib）**未验**，若采纳代理方案再补。
- 工具面清单来自 `--dump-config` 静态组合，未逐个调用验证（P2 只验了 `submit_result`）。
- 模型侧拒绝打印凭据内容（P0-3 第 3 条被模型自行改道），但"路径可读"已由 `ls`/`wc` 独立证明。
