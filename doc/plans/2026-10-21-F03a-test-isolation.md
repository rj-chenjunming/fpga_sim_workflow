# F03-a 验证隔离最小切片：软件 state 根注入 · 切片计划

> 承接 [优化与重构执行手册](OPTIMIZATION_PLAYBOOK.md) 批次 A 的 F03（P1/验证基础），
> 本文件只覆盖其中**最小可验切片 F03-a**；测试夹具按环境/数据根分层（F03-b）与文档解析（F03-c）另行立项。

| 项 | 内容 |
|---|---|
| 类型 | 验证工具/基础设施（缺陷类：测试写共享 state、子进程写冻结目录） |
| 基线提交 | `c3257f7` |
| 唯一 owner | 验证工具 owner；本切片由 Lead 实现并自测，未指派独立验证者 |
| 规格位置 | [环境插件规格 三根表 + 已知风险](../spec/ENV_PLUGIN_SPEC.md) |
| 允许修改 | `loop/host/paths.py`、`loop/tests/conftest.py`、`loop/workflows/chunks/host_steps.py`、`loop/tests/test_paths_isolation.py`（新增）、`doc/spec/ENV_PLUGIN_SPEC.md`、本计划、`doc/STATUS.md` |
| 不修改 | 冻结目录 `kb/**`（含 `kb/tools/**`）、执行拓扑、闸门、`loop/state` 下既有历史快照 |

## 1 问题

1. `STATE_DIR` 写死 `<TOOL_ROOT>/loop/state`：pytest 运行会把 jobs/recovery/events/单槽锁写进**共享软件 state**，
   与正在使用的服务副本互相污染；多副本/CI 无法隔离（[环境规格已知风险](../spec/ENV_PLUGIN_SPEC.md)）。
2. `run_kb_tool()` 以 `python <kb/tools/xx.py>` 调子进程，未带 `-B` ⇒ 子进程导入 `kb_lib` 会在
   **冻结目录** `kb/tools/__pycache__/` 写字节码（红线：冻结目录只读）。
3. 实证：本轮早前测试曾留下 loop/None/view.json 与 `loop/state/events/*.stale-*`（已清理）。

## 2 目标可观察行为

- `$LOOP_STATE_ROOT` 可覆盖软件 state 根；缺省仍为 `<TOOL_ROOT>/loop/state`（生产路径不变）。
- pytest 进程的 `STATE_DIR/JOBS_DIR/RECOVERY_DIR/EVENTS_DIR/SLOT_LOCK/SLOT_QUEUE` 全部落在一次性临时目录。
- kb 工具子进程命令行包含 `-B`；测试后 `kb/tools` 无新增 `*.pyc`。

## 3 不变量

1. **生产缺省不变**：不设环境变量时路径与历史布局逐字相同。
2. **只隔离不清理共享**：测试只写自己的 state 根，绝不清理共享 `loop/state` 下的资产。
3. **冻结目录零写入**：`kb/tools/**` 源文件与字节码都不新增。

## 4 实测（数字从命令输出复制）

| 验证 | 原始输出 | 说明 |
|---|---|---|
| 修改前红灯（临时 stash 三处改动） | `3 failed, 1 passed in 0.69s` | 注入/隔离/`-B` 三项先红；缺省路径用例本就绿 |
| 修改后 | `4 passed in 0.62s` | 四项全绿 |
| 全套单测 | `46 failed, 275 passed, 3 skipped, 1 warning in 11.23s` | 46 项仍为 `ENV_ROOT` 只读同因；通过数 271→275 = 新增 4 项（F03-a 用例） |
| 冻结目录检查 | `find kb/tools -name '*.pyc' -newermt <start>` 无输出 | 子进程未写字节码 |

**验证边界**：检查共享 `loop/state/recovery` 是否被改写时发现该目录由**沙箱 PID 命名空间外的常驻服务**持续写入
（空闲 3 秒内容也会变，`ps` 在沙箱内不可见），因此「共享 state 未被测试写」**不能**用 mtime/md5 反证；
以「进程内 `STATE_DIR` 指向一次性目录」的断言与 `kb/tools` 无新字节码为证据。

## 5 未完成（不在本切片）

- F03-b：纯软件 / 受控插件 / 真实内网三类测试入口分层；46 项 `ENV_ROOT` 只读失败仍未解（需要按测试类别注入
  可写数据根，并给缺依赖的显式未运行原因）。
- F03-c：文档解析器根解析误判（`doc/audit/check_doc_links.py`）。
- 多环境共享一个软件实例时按 `ENV_ID` 分区 state/槽键（审计待办，见环境规格）。

## 6 回退

删除 `$LOOP_STATE_ROOT` 覆盖与 conftest 注入即回到原布局；`-B` 与测试可独立回退，不影响业务判据。
