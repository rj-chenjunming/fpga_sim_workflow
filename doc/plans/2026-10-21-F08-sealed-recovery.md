# F08 封存发布与崩溃边界 · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F08（P2 先注入故障）、
> 开工提示词 §4 第 10 项。目标：对 `_sealed` 发布边界注入进程终止，建立恢复观察矩阵，
> 定义 incomplete/corrupt/committed，修复「不消费半写记录」，并提取公开封存接口。

| 项 | 内容 |
|---|---|
| 类型 | 可靠性与诊断（失败必须显式，不冒充完成） |
| 基线提交 | `6c4ee6e` |
| 唯一 owner | 记录存储 owner（`host/agent_memory.py`）；业务写权不变 |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [AGENT_CONTEXT_SPEC M1](../spec/AGENT_CONTEXT_SPEC.md) + 新增「封存与恢复」 |
| 允许修改 | `loop/host/agent_memory.py`、`loop/host/agent_control.py`（仅改用公开封存 API）、`loop/tests/`（新增故障注入用例）、`doc/spec/AGENT_CONTEXT_SPEC.md`、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | 记录格式（`request.json`/`result.json`/`.sha256` 名字与内容不变）、业务写权、`kb/**`、冻结证据 |

## 1 问题

`_sealed` 先写数据、再写校验和（两次 `O_EXCL`）。在两步之间被 `SIGKILL`：数据在、校验和缺。
当前 `read_view` 对任意缺失/坏校验的记录整体抛 `ValueError`，窗口/API 变成 422，
无法区分「这次尝试不完整」与「整个 run 记录坏了」；也没有公开 API，`agent_control` 直接引用私有 `_sealed`。

## 2 观测矩阵（进程在发布边界被终止）

| 终止点 | 磁盘状态 | 诊断 | 消费者行为 |
|---|---|---|---|
| 建目录前 | 无 attempt 目录 | `absent` | 新尝试按序号继续，不复用 |
| 建目录后、数据前 | 空 attempt 目录 | `incomplete` | 该尝试标 incomplete，不消费 |
| 数据写完、校验前 | `request.json` 有、`.sha256` 无 | `incomplete` | 该尝试标 incomplete，不消费；其余尝试可读 |
| 校验写完、result 前 | request 完整、result 缺 | `incomplete` | 既有语义：尝试未完成，不消费 |
| 校验不匹配/JSON 坏 | 两文件在、内容不一致 | `corrupt` | 显式 corrupt，不消费、不自动重发 |
| 两步都完成 | 内容与校验一致 | `committed` | 可读；身份校验通过后才消费 |

## 3 目标可观察行为

1. `AM.record_state(path)` 返回 `absent / incomplete / corrupt / committed`（只读，不修改文件）。
2. `read_view` 对 individual 尝试的 incomplete/corrupt **不再整体抛错**：该尝试摘要标状态，
   记录不进入 `records`（不消费）；其它 committed 尝试照常可读。越界/符号链接/身份不匹配仍显式失败。
3. 公开封存接口 `AM.seal_record(path, value)`；`agent_control` 不再引用私有 `_sealed`（保留别名兼容）。
4. 新尝试序号只增，不复用已存在目录；不覆盖已发布记录。
5. 恢复诊断不自动重发模型请求。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F08-1 | 规格「封存与恢复」+ 本计划 | 文档门 |
| F08-2 | 红灯：故障注入用例（子进程在数据/校验之间 `os._exit(9)`；`SIGKILL` 写入循环） | 先红（`record_state` 与容错读取尚不存在） |
| F08-3 | 实现：`record_state`/`seal_record` + `read_view` 容错 + `agent_control` 改用公开 API | 定向 + 默认根 + 软件层 |
| F08-4 | 独立复核报告（`doc/audit/`，只读子代理） | 报告含观察矩阵与原始输出；md5 记入 STATUS |
| F08-5 | STATUS §31 | 命令/输出逐字复制；未运行项单列 |

**验证边界**：故障注入用真实子进程终止（`os._exit`/`SIGKILL`），不只用内存模拟；
持久暂停/续跑（F09）不在本切片。

## 5 回退

保留 `record_state` 只读诊断，回退 `read_view` 容错分支即恢复「整体显式失败」；记录格式不变，旧数据可读。
