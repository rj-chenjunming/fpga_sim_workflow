# K1：环境类检查统一入口（3 个 kb 自测 + 3 条 env_layer，一条命令）

> 状态：**已实施**（2026-10-27；实测数字见 [STATUS §94](../STATUS.md)）。
> 上游：`doc/plans/2026-10-27-kickoff-unresolved.md` §2 **K1**（本仓可自行推进、无外部依赖）。
> 口径引用：[AGENTS.md](../../AGENTS.md) §4（四道门 + 两道补充门）、§5 红线 8/10/11。

## 0 问题（可观察）

环境类检查现在分两处、各有各的跑法，且**都要人手拼环境变量**：

| 检查 | 现在怎么跑 | 手拼的部分 | 手拼错的后果 |
|---|---|---|---|
| 3 条 `@pytest.mark.env_layer` | `spikes/run_env_layer_checks.sh`（已自动建/复用派生副本） | 无 | 无（脚本已封装） |
| 3 个 kb 自测（10/9/28 条断言） | 手动 | `LOOP_ENV_ROOT=<repo>/.env-copy LOOP_WORKSPACE=<repo>/.env-copy/kb` | 忘了指 ⇒ 在**只读真实 ENV_ROOT** 上跑，`_selftest_gate_schema` 建临时 run 目录直接失败；或指错根 ⇒ 数字不可比 |

⇒ 同一批"需要可写环境/数据根才能跑"的检查有**两个入口、两套前置**，交接时容易只跑一半，
或者把「跑不动」当「通过」。这是**可用性缺陷**，不是判据缺陷：两类检查的判据本身没问题。

**验收判据（来自 K1 原文，不读源码也能判）**：一条命令输出 `PASS=10` / `PASS=9` / `PASS=28` 和 `3 passed`，
且原 `ENV_ROOT` 零写入（红线 11）。

## 1 方案选择：选 ②（给 `run_env_layer_checks.sh` 加 `--with-kb-selftests`）

K1 原文给了二选一，本切片选 ②，理由：

1. **派生副本的构造逻辑只有一份**（`run_env_layer_checks.sh` 里那段 `cp -a --reflink=auto` +
   `chmod -R u+w` + `kb_lib` 唯一解析器）。选项 ① 新增 `spikes/run_env_checks.sh` 必须复用这段逻辑，
   否则就是红线 8「不许出现第二套同判据实现」；而复用它的最省事形态恰好就是"改成同一脚本的一个开关"。
2. **一个入口名比两个好维护**：`run_env_checks.sh` 若只是薄包装，读者仍要记住两个名字。
3. 副作用最小：不改派生副本布局、不改 pytest 分层标记、不改默认门口径。

代价（显式登记）：`doc/plans/2026-10-27-kickoff-unresolved.md` §2 K1 与 §93 里提到的
`loop/spikes/run_env_checks.sh` **不会存在** ⇒ 文档门 `KNOWN_MISSING` 保留该条但改写原因
为"选项①未采用（K1 选②）"，不删除引用、不伪造文件。

## 2 切片与落点

| 切片 | 内容 | 落点 | 判据 |
|---|---|---|---|
| S1 | 参数面：`--with-kb-selftests`、`--dry-run`（只打印计划、不复制不执行） | `loop/spikes/run_env_layer_checks.sh` | `--dry-run` 退出 0；打印 3 个自测模块名 + env_layer 的 pytest 命令行；**不建副本**（`COPY` 仍不存在） |
| S2 | kb 自测执行：在同一个派生副本上跑 3 个自测，逐条打印 `PASS=n FAIL=m`，任一 `FAIL>0` 或 `rc!=0` ⇒ 整条命令红 | 同上 | 输出含 `PASS=10`/`PASS=9`/`PASS=28`；失败时退出码非 0 |
| S3 | 零写入见证覆盖 kb 自测：`find -newer` marker 在两类检查**之前**创建，跑完对原 `ENV_ROOT` 判零写入 | 同上 | 命中数 0；命中即退出码 3 |
| S4 | kb 自测不得往冻结的 `kb/tools/` 写 `.pyc`（红线 11 / R 类第 5 条） | 同上 | 命令行含 `-B` 且 `PYTHONDONTWRITEBYTECODE=1` |
| S5 | 流程与文案同步 | `AGENTS.md` §4、`doc/plans/2026-10-27-kickoff-unresolved.md` K1 行、`doc/plans/2026-10-27-c-group-handover.md` §2、`doc/audit/check_doc_links.py` | 文档门 `missing=0`；三处命令一致（不许出现第二套写法） |

## 3 测试（TDD：先红后绿）

新用例 `loop/tests/test_env_checks_script.py`（**不是** `env_layer` 标记 —— 它只跑 `--dry-run`，
不需要可写 ENV_ROOT，属于纯软件层）：

1. `--help` 列出四个开关（能力可发现，不靠读源码）；
2. `--dry-run --with-kb-selftests` 退出 0，输出含 3 个自测模块名与 `-m env_layer` 的 pytest 命令；
3. 同一次 `--dry-run` 必须**不创建** `COPY` 目录（用临时 `COPY` 断言）；
4. 打印出的 kb 自测命令必须带 `-B` + `PYTHONDONTWRITEBYTECODE=1`（红线 11：冻结目录零 `__pycache__`）；
5. 对照：不带 `--with-kb-selftests` 的 `--dry-run` **不出现**自测模块名（证明开关真的接上了覆盖范围）；
6. **打印与执行同源**：`--dry-run` 打印的每一行都要带副本的 `LOOP_ENV_ROOT`/`LOOP_WORKSPACE`
   （回归钉：`KB_ENV` 曾定义在 dry-run 分支之后 ⇒ 打印静默少了数据根，而断言只查"有没有 py 文件"就会漏）；
7. **`--dry-run --cleanup` 零副作用**：副本必须还在（独立复核 A 项回归钉：旧实现会真 `rm -rf`）；
8. **失败必须显式**：空派生副本 ⇒ 整条命令非 0 + `[FAIL]` + 每个失败自测名可见 + 指出验收数字
   （`PASS=10/9/28` 的 pin，独立复核 B 项）。

实测：先红 `5 failed`（实施前）→ 绿 `5 passed` → 补 3 条回归钉/同源钉后 `8 passed`（数字见 STATUS §94.2）。

## 4 验证门（本切片）

| 门 | 命令 | 期望 |
|---|---|---|
| 新用例（先红） | `loop/.venv/bin/python -m pytest -q tests/test_env_checks_script.py` | 实施前红，实施后绿 |
| 软件层 | `cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser` | 0 failed；通过数 = 基线 979 + 本切片新增用例数 |
| **本切片验收** | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests` | `PASS=10 / PASS=9 / PASS=28` + `3 passed` + 原 `ENV_ROOT` 零写入 |
| 文档 | `python3 doc/audit/check_doc_links.py` | `missing=0`，`exit=0` |

## 5 环境限制（不许绕过）

- 本机 `<ENV_ROOT>` 在 `/home` 的 `ro,nosuid,nodev` 挂载上 ⇒ 只能在**派生副本**上跑；脚本不得写原环境。
- 派生副本 2.6 GB；本轮先 `--reuse` 复用既有 `<repo>/.env-copy` 跑验收，另做过**两次全量重建**验证复制路径（都是 `RC=0`），
  跑完按 K3 清理（`--cleanup`），需要时再重建。
- `kb/tools/**` 是冻结目录：不得写 `.pyc`（`-B` + `PYTHONDONTWRITEBYTECODE=1`），也不得改其语义。
- 不得声称"独立验证"：实施者自跑只写「本轮实测」；独立复核另起 agent，且复核者只报告不改。

## 6 未做（显式登记）

- 不改 `run_software_checks.sh` 的默认排除口径（`-m "not env_layer"` 维持；R 类第 2 条已裁决）。
- 不把 env_layer 3 条并入全量单测门（R 类第 2 条、STATUS §81.4 裁决理由不变）。
- 不改 `KB_NOW`/时间注入口径；kb 自测的时间来源维持现状。
