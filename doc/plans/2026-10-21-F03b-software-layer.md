# F03-b 软件层检查入口 + 缺陷发现（F16）· 切片计划

> 承接 [优化与重构执行手册](OPTIMIZATION_PLAYBOOK.md) 批次 A 的 F03（P1/验证基础）。本文件覆盖 F03-b 的
> **入口与首次实测**；测试夹具按环境/数据根分层（F03-b 完整形态）与文档解析（F03-c）仍未完成。

| 项 | 内容 |
|---|---|
| 类型 | 验证工具（新增入口）+ 新发现缺陷登记 |
| 基线提交 | `7307d94` |
| 唯一 owner | 验证工具 owner（入口）；缺陷 F16 属模型节点 owner / 上下文 owner |
| 允许修改 | `loop/spikes/run_software_checks.sh`（新增）、本计划、`doc/STATUS.md`、`doc/plans/OPTIMIZATION_PLAYBOOK.md`（登记 F16） |
| 不修改 | 业务实现、`kb/**`、冻结证据 |

## 1 问题

`WORKSPACE_ROOT` 默认 = `<ENV_ROOT>/kb`。本机环境根只读 ⇒ `kb/runs` 不可写，
默认 `pytest -q` 有 **46 项**在 `mkdir` 处 `OSError: [Errno 30] Read-only file system` 失败，
无法区分「环境缺件」与「软件缺陷」。

## 2 入口（已交付）

`bash loop/spikes/run_software_checks.sh [pytest 参数...]`：

1. 从 `host.paths` 解析真实数据根；
2. 建一次性影子根：`runs/`（可写）、`index/`、`conflicts/`、`adjudication/` 浅拷贝、`baselines/` 符号链接到真实只读基线、
   drill 夹具轮 `RUN-20261015-120626`（733 MB）符号链接（不复制）；
3. `LOOP_WORKSPACE=<影子>` + conftest 注入的 `$LOOP_STATE_ROOT` 跑 pytest；`KEEP_SHADOW=1` 可保留现场。

它证明：软件层用例在可写数据根 + 隔离 state 下**能真正执行**；
它不证明：需要可写 `ENV_ROOT` 的环境侧用例（归档/守卫脚本）通过。

## 3 实测（数字从命令输出复制）

| 验证 | 原始输出 | 说明 |
|---|---|---|
| 默认根（未隔离） | `46 failed, 275 passed, 3 skipped in 11.23s` | 46 项全为只读 `OSError` |
| 影子根首跑（未链接夹具轮） | `44 failed, 271 passed, 9 skipped in 650.84s` | 失败转为 `AssertionError`：N0/N1 缺 drill 夹具 |
| 链接夹具轮后 `test_flow.py` | `11 failed`（18 项中） | drill 全链开始执行，随即暴露 F16 |

**软件层运行成本**：受 `wait_until(timeout=25s)` 与真实作业停等的驱动，整套约 10–11 分钟（默认只读根下 11 秒是因为
用例早在 `mkdir` 处失败）。这不是入口缺陷，但属于「软件层不能当快速门」的事实，记录在案。

## 4 新发现：F16 · N6 上下文预算超限（阻断 drill 全链）

**现象（受控复现）**：

```
bash spikes/run_software_checks.sh tests/test_flow.py::test_gates_are_recorded_once_each
RuntimeError: 闸门 G1_diff_confirm 已签署但恢复失败（run 已置 failed）：
  agent context budget exceeded（上下文预算）: 130546 > 120000 bytes
```

**性质**：不是测试装置缺陷。G1 之后 N5→N6 构造请求时输入 130546 bytes，超过
[AGENT_CONTEXT_SPEC](../spec/AGENT_CONTEXT_SPEC.md) 的 120000 bytes 硬预算，`check_budget` 显式失败，
整个 drill 链在 G1 后收敛为 failed。默认只读根下该路径从未被走到（更早的 `mkdir` 已失败），因此此前被掩盖。

**与本次拉取的关系**：`5f6cdb2→fb83ed0` 的 N6 改动删除了「20 行/6000 字/3 个定义」上限，改为
`api_semantics` 全文 + `excerpts` 全量；输入规模上升后与既有 120000 预算冲突。属**行为变化未同步预算契约**。

**未修**：需要先定契约方向（建议三选一，均须显式覆盖、不许静默截断）：
1. 全局 API 定义去重（`targets[].api_semantics` → 顶层 `api_index` + 引用），通常可降一个量级；
2. 预算上限按 provider 上下文窗口重定，并在规格写明依据；
3. 超预算时分块请求并定义汇合与唯一消费者（成本最高）。

阻塞影响：`test_flow` 11 项、以及所有走到 G1 之后的软件层用例；**四道门端到端在本机不可判为通过**。

## 5 回退

删除 `spikes/run_software_checks.sh` 即回到原入口；缺陷 F16 的登记不修改任何业务行为。
