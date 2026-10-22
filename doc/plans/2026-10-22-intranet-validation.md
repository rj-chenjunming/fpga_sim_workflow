# 内网验证手册：拉取后按阶段执行

对应 [下一轮 SpecDD 计划](2026-10-22-next-iteration-specdd.md)，基线 `343584c`。目标 Rocky Linux 8.10 / x86_64 / glibc 2.28，项目 CPython 3.11；浏览器工具也支持 CPython 3.12。下文为**待执行步骤**，结果填写到 [STATUS](../STATUS.md) 新章节，历史结果不充当本轮通过。

## V0 拉取、留存身份与配置

在软件仓根目录、Bash 中执行。先查看工作树；若有内网未提交修订，先单独提交/保留后再同步，不用 reset/clean 覆盖。远端有分叉时停止快进，记录并正常合并。

```bash
git status --short --branch
git pull --ff-only origin main
export VERIFY_REPO="$(git rev-parse --show-toplevel)"
export VERIFY_OUT="$(mktemp -d /tmp/loop-verification-XXXXXXXX)"
export PYTHONDONTWRITEBYTECODE=1
cd "$VERIFY_REPO"
git rev-parse HEAD > "$VERIFY_OUT/commit.txt"
git status --porcelain > "$VERIFY_OUT/worktree.txt"
cat /etc/os-release > "$VERIFY_OUT/os.txt"
uname -m >> "$VERIFY_OUT/os.txt"
ldd --version >> "$VERIFY_OUT/os.txt"
loop/.venv/bin/python -V > "$VERIFY_OUT/python.txt" 2>&1
node --version > "$VERIFY_OUT/node.txt" 2>&1
printf '证据目录：%s\n' "$VERIFY_OUT"
```

Node 是现有前端纯函数测试的执行依赖，不在浏览器 wheel 包里。缺 Python/Node/项目基础依赖先补匹配的内网包；不要把环境缺件记为代码通过。不要导出整份环境变量或 provider 配置（可能包含密钥）。

在**同一 Bash 会话**定义记录函数；命令失败仍记录真实退出码，执行完一项先判读，再手动进入下一项：

```bash
record() {
  local label="$1"
  shift
  local code
  if "$@" > "$VERIFY_OUT/$label.log" 2>&1; then
    code=0
  else
    code=$?
  fi
  printf '%s\t%s\n' "$label" "$code" >> "$VERIFY_OUT/exits.tsv"
  cat "$VERIFY_OUT/$label.log"
  printf '\n[%s] exit=%s\n' "$label" "$code"
  return "$code"
}
```

该函数不用 tee 管道，避免日志命令的成功掩盖测试失败。勿将全部步骤合并成「失败继续、最后 echo 成功」的脚本。

## V1 浏览器离线安装与真实启动

前置：项目 .venv 已有基础依赖。UI 包是增量，未包含应用全部 requirements、Node、Rocky 共享库/字体；具体来源、SHA-256、边界见 [离线说明](../../loop/offline/README.md)。

```bash
cd "$VERIFY_REPO"
record bundle-verify loop/.venv/bin/python loop/spikes/browser_offline.py verify
record browser-install loop/.venv/bin/python loop/spikes/browser_offline.py install
record python-deps loop/.venv/bin/python -m pip check
record browser-check loop/.venv/bin/python loop/spikes/browser_offline.py check
```

预期：全部资源哈希通过；pip 只从本地 wheels 安装；依赖一致；真实浏览器启动后输出版本与 smoke PASS。默认优先已有系统 Chrome，缺失时解包随包 Chrome。若显式配置 LOOP_BROWSER_EXECUTABLE 无效，修正它再运行；工具不会偷偷换浏览器。

需要验证随包版本时另跑以下命令；env 仅取消浏览器路径选择变量，不改变代理/认证配置：

```bash
record browser-bundled env -u LOOP_BROWSER_EXECUTABLE \
  loop/.venv/bin/python loop/spikes/browser_offline.py check --bundled
```

缺 NSS/X11/GBM/字体时，记录工具列出的缺件，通过匹配 Rocky 8 的内网 RPM 源补齐后重跑；最小 Rocky 镜像离线装 wheel 成功**不等于浏览器启动通过**。资源哈希失败先核对 Git 文件，不能关闭校验。安装完成后分别保留「所用浏览器」和「备用浏览器」结果，二者不混写。

普通 pytest 不会调用离线工具的自动选浏览器逻辑。将 browser-check 成功日志中 executable= 后的**真实绝对路径**填入下列变量，供 V2/V4/V5/V7 使用；仅安装工具成功还不足以配置普通 pytest：

```bash
export LOOP_BROWSER_EXECUTABLE="/请替换/browser-check输出的浏览器绝对路径"
if ! test -x "$LOOP_BROWSER_EXECUTABLE"; then
  printf 'STOP: 先填写已通过 smoke 的浏览器路径。\n' >&2
  exit 1
fi
```

## V2 三根确认与软件层特征基线

```bash
cd "$VERIFY_REPO/loop"
record roots .venv/bin/python - <<'PY'
from host import paths as P
for key in ("TOOL_ROOT", "ENV_ROOT", "WORKSPACE_ROOT", "STATE_DIR"):
    value = getattr(P, key)
    print(f"{key}={value} exists={value.exists()}")
print("plugin_missing=", P.missing_plugin_parts())
print("workspace_missing=", P.missing_workspace_parts())
fixture = P.KB_RUNS / "RUN-20261015-120626"
print("historical_fixture=", fixture, "exists=", fixture.is_dir())
PY
record collection env LOOP_LLM_MODE=standin .venv/bin/python -m pytest --collect-only -q
record software bash spikes/run_software_checks.sh -ra
```

roots 命令只读、只打印配置事实，退出 0 不代表缺件已解决，必须查看 missing 列表。软件入口创建影子数据根与临时 state，但仍只读真实 baselines/历史夹具；缺夹具不能靠创建空目录伪造可用。它默认排除 env_layer，输出的 deselected 不是通过；pytest 自身 exit 0 也可能含 skip，必须逐条解释。浏览器独立验收走 V3，完整环境门走 V7。

**基线有失败时**：记录 node ID、堆栈、首次退出码及复跑结果，与 STATUS §35 的已知问题比较。R1 随机 SIGKILL 用例偶发通过不解除 R1；新失败先定位再重构。不要用 -k 排除失败换取全绿。

## V3 浏览器回归与改动前截图

```bash
cd "$VERIFY_REPO/loop"
record browser-regression env LOOP_VISUAL_ARTIFACTS="$VERIFY_OUT/screenshots-before" \
  .venv/bin/python spikes/browser_offline.py run
```

预期：CLI 先真实启动浏览器，再执行整个 tests/browser；有收集/运行跳过或未收集到测试均应非零。按当次实际收集数和输出记录，不硬编码历史用例总数。截图目录来自已有布局用例，只覆盖部分状态，不等于 V6 全矩阵。

现有用例使用受控 API 响应，验证网页交互、会话隔离和布局；它不能证明真实 provider、仿真或 S0 驱动。改后用相同浏览器版本、字体、数据、视口运行，把输出目录改为 screenshots-after，不覆盖 before。

## V4 R1–R5 的基线复现与定向回归

现有复核探针只是**观察工具**，退出 0 不表示缺陷修好了。它使用内部注入点，修复重构后可能失效；不要修改冻结审计脚本迎合新实现，改用新增回归用例。

```bash
cd "$VERIFY_REPO"
record review-probes env LOOP_LLM_MODE=standin \
  loop/.venv/bin/python doc/audit/parts/intranet-batch-probe.py
cd "$VERIFY_REPO/loop"
record r1 bash spikes/run_software_checks.sh \
  tests/test_f08_sealed.py tests/test_agent_context_memory.py tests/test_agent_control.py -ra
record r2-r3 bash spikes/run_software_checks.sh \
  tests/test_baseline_admission.py tests/test_api_baseline_detail.py tests/test_admission_and_jobs.py -ra
record r4 bash spikes/run_software_checks.sh tests/test_n8_context_budget.py -ra
record r5 bash spikes/run_software_checks.sh \
  tests/test_context_explain.py tests/test_agent_view.py tests/test_agent_control.py -ra
```

这些路径已经存在；**当前套件未完整覆盖新发现的边界**。实施者必须先把下表断言加入对应测试文件并记录精确 node ID，验证者再运行同一命令；不能以旧测试通过关闭新缺陷。

| 验收 ID | 修复前要稳定看到的失败 | 修复后必须看到的外部结果 |
|---|---|---|
| R1-A/B | 固定校验发布中断导致整个历史不可读 | 每个故障点旧完整尝试可读、半件不可消费；真正篡改仍失败；竞争写不覆盖；压力失败不能靠重跑抹掉 |
| R2-A | 同一外部文件相对路径可通过、绝对路径被拒 | 相对/绝对/符号链接越界全部结构化拒绝；有效路径照常通过；拒绝前无 run/作业副作用 |
| R3-A | 非 UTF-8 manifest 导致列表 500 | HTTP 列表成功，坏项 invalid 且原因明确，好项保留；real 创建拒绝且无副作用 |
| R4-A | 合法全文能装下却因更大片段被拒 | 合法候选中存在可行表示就不误拒；编码预算、完整覆盖、确定性与大文件强制规则一致 |
| R5-A | UI 总量与 Host 计费字节不同 | Host/API/UI 同一总量；分项与开销对账；未知不伪装为 0/token 估值 |

R4/R5 变更涉及现行规格细节，先完成任务卡中的契约评审。新增断言不能只读取源码查字符串，必须构造输入并检查 API、文件产物或 DOM 可观察结果。按「红灯提交→实现提交→绿灯输出」留证。

## V5 F14 / F05 定向检查

```bash
cd "$VERIFY_REPO/loop"
record css-before .venv/bin/python spikes/css_inventory.py
record frontend-feature bash spikes/run_software_checks.sh \
  tests/test_gate_session.py tests/test_run_view_state.py tests/test_capability_format.py \
  tests/test_context_explain.py tests/test_web_smoke.py -ra
record read-measurement .venv/bin/python spikes/measure_agent_read.py --repeat 30
```

CSS 清单与读取测量不是功能通过证明。记录整理前后清单并解释删改，不能把重复声明数减少当成视觉等价。读取测量只覆盖受控历史读取，不包含真实 provider 回执延迟；未触发窗口规格门限不先做缓存/分页。

每个 CSS 组件或 JS 模块提交后跑受影响特征与 V3；阶段末复跑 V2 软件层。新增模块按实际文件运行 node --check，并补加载顺序/唯一事件绑定断言；尚未创建的模块不在本手册伪造命令路径。

## V6 网页人工验收矩阵

在专用测试服务上按 [UI 操作手册](../UI_RUNBOOK.md) 的业务步骤操作；配置、判据和身份以现行 spec 为准，操作手册历史示例不替代规格。主视口 1280/1440/1920，缩放 100%/125%/150%；同屏前后截图记录提交、浏览器和字体。每条填通过/失败/阻塞及证据文件。

| 页面/状态 | 操作与预期 |
|---|---|
| S0 | 基线、RTL、派生工作目录长路径不遮挡按钮；无驱动/校验失败明确不准出；加载/空/错态可区分 |
| 配置/目录 | 无基线、坏基线、刷新失败可见；选择/取消目录不串草稿；Tab/Enter/Escape 和焦点返回正常 |
| 运行监控 | 长项目名、节点、Agent、blockers 和两套计数可读；计数来源/unknown 不被样式掩盖 |
| 闸门 | 连续点击仅一次 POST；身份变化清草稿；拒绝/409 保留同身份输入；旧运行回包不改当前页 |
| Agent | 节点切换、关闭再打开、历史/空记录、暂停/取消请求态清晰；输入不丢；预算与 Host 同源；重启后不暗示旧会话可恢复 |
| 全局/旧页 | 旧入口可用；hover/focus/disabled/告警对比可辨；模态与页面滚动层正确；无控制台异常/重复监听 |
| 断点 | 按 CSS 清单逐个断点及 ±1px 检查；缩放后操作可达，无关键内容裁切；保留已有溢出回归 |

截图不同必须解释是预期调整还是回归，由验收者逐项确认；自动断言通过不能替代视觉判读。发现差异先保持原截图，修复后另存新批次。

## V7 完整四道门：仅在独立可写副本执行

**专门的写入边界**：accept_v1_run.sh 会删除当前软件副本的 state、接收脚本状态，以及所选数据根中带 .loop_drill 的运行目录；kb 自测使用固定临时 run 名；部分环境测试调用守卫和仿真。不得指向生产服务 state、共享数据根或冻结环境原件。

由内网执行者先准备：独立软件 checkout（不与线上共用 .venv/state；独立 venv 中按 V1 安装基础与 UI 依赖）、完整可写测试环境副本、完整测试数据副本（保留历史夹具、基线/指纹/目录结构）、可用 UVS 与独占环境时段。数据/环境副本不要用指回原件的软链接或硬链接；基线中的绝对引用若仍指原件，先做迁移/兼容核对，不能静默改冻结 manifest。若不能满足，V7 记阻塞，V1–V6 可继续。

将下面占位路径换成真实**专用测试副本**；前置断言故意不允许缺路径时继续：

```bash
export VERIFY_CHECKOUT="/请替换/独立软件副本"
export VERIFY_ENV_COPY="/请替换/独立环境副本"
export VERIFY_DATA_COPY="/请替换/独立数据副本"
if ! test -e "$VERIFY_CHECKOUT/.git" ||
   ! test -x "$VERIFY_CHECKOUT/loop/.venv/bin/python" ||
   ! test -d "$VERIFY_ENV_COPY/RTL" ||
   ! test -d "$VERIFY_DATA_COPY/baselines" ||
   ! test -d "$VERIFY_DATA_COPY/runs/RUN-20261015-120626"; then
  printf 'STOP: 专用副本或历史夹具不完整，先修正路径。\n' >&2
  exit 1
fi
export LOOP_ENV_ROOT="$VERIFY_ENV_COPY"
export LOOP_WORKSPACE="$VERIFY_DATA_COPY"
export LOOP_STATE_ROOT="$VERIFY_CHECKOUT/loop/state"
export LOOP_LLM_MODE=standin
export LOOP_PORT=18099
cd "$VERIFY_CHECKOUT"
record isolated-commit git rev-parse HEAD
cd loop
record isolated-browser .venv/bin/python spikes/browser_offline.py check --executable "$LOOP_BROWSER_EXECUTABLE"
record isolated-roots .venv/bin/python - <<'PY'
import os
from pathlib import Path
from host import paths as P
for key, variable in (("TOOL_ROOT", "VERIFY_CHECKOUT"), ("ENV_ROOT", "VERIFY_ENV_COPY"),
                      ("WORKSPACE_ROOT", "VERIFY_DATA_COPY"), ("STATE_DIR", "LOOP_STATE_ROOT")):
    actual = getattr(P, key).resolve()
    expected = Path(os.environ[variable]).resolve()
    print(key, actual)
    assert actual == expected, (key, actual, expected)
assert not P.missing_plugin_parts(), P.missing_plugin_parts()
assert not P.missing_workspace_parts(), P.missing_workspace_parts()
PY
```

上述根检查非零就停止，切勿继续复制后面的执行命令；人工再确认这些路径确实是副本、与共享原件无可写链接、目标提交一致、端口空闲且无并发仿真。不要为通过检查伪造目录。

先对测试环境 RTL/TB/PKG/TESTLIB、数据副本基线及 uvs.setup 建相对路径+内容 MD5 清单，保存在 VERIFY_OUT；运行结束再生成一次并比较。只允许现行规格定义的 SIMLIB_RUN 与可恢复 uvs.setup 运行写入；其它差异一律停下调查。清单必须包含新增/删除，不只比较既有文件。下面函数只读指纹，不改变资产权限：

```bash
fingerprint_assets() {
  "$VERIFY_CHECKOUT/loop/.venv/bin/python" - <<'PY'
import hashlib, json, os
from pathlib import Path
env = Path(os.environ["VERIFY_ENV_COPY"])
data = Path(os.environ["VERIFY_DATA_COPY"])
roots = [("env/" + name, env / name) for name in ("RTL", "TB", "PKG", "TESTLIB", "uvs.setup")]
roots.append(("workspace/baselines", data / "baselines"))
rows = {}
for label, root in roots:
    if not root.exists():
        raise RuntimeError(f"缺资产：{root}")
    paths = [root, *sorted(root.rglob("*"))] if root.is_dir() else [root]
    for path in paths:
        key = label if path == root else label + "/" + path.relative_to(root).as_posix()
        if path.is_symlink():
            raise RuntimeError(f"存在需人工核对的链接：{path}")
        if path.is_dir():
            rows[key] = {"type": "directory"}
        elif path.is_file():
            digest = hashlib.md5()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            rows[key] = {"type": "file", "md5": digest.hexdigest()}
        else:
            raise RuntimeError(f"非普通资产：{path}")
print(json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2))
PY
}
record assets-before fingerprint_assets
```

若合法环境确需软链接，先由环境 owner 核对解析目标及只读边界，再另写覆盖链接与目标的指纹方案，不能跳过它后声称零改动；原环境/原基线在副本制作前后也须同口径只读核对。

```bash
# 当前目录：独立软件副本的 loop
record full-unit env LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q -ra
cd "$VERIFY_CHECKOUT"
record kb-gate loop/.venv/bin/python kb/tools/_selftest_gate_schema.py
record kb-reachability loop/.venv/bin/python kb/tools/_selftest_n5_reachability.py
cd loop
record acceptance bash spikes/accept_v1_run.sh
cp -a .logs/accept "$VERIFY_OUT/accept-driver-logs"
cd "$VERIFY_CHECKOUT"
record docs loop/.venv/bin/python doc/audit/check_doc_links.py
record assets-after fingerprint_assets
record assets-diff diff -u "$VERIFY_OUT/assets-before.log" "$VERIFY_OUT/assets-after.log"
```

逐项串行，前一门失败先留证与处理，不能把完整命令块当作自动准出器。

| 门 | 通过标准 | 未通过处理 |
|---|---|---|
| 全量单测 | exit 0；实际收集与通过可对账；每个 skip 都有处置，目标能力不得跳过 | 区分代码失败/缺件，保留首次失败；软件层排除结果不能代替全量 |
| kb | 两脚本 exit 0 且全部断言执行通过 | 缺历史夹具/权限为阻塞，不伪造样本；其它受影响 kb 自测按切片补跑 |
| 端到端 | exit 0，全部预定 phase 均有输出且通过；检查重启与存活任务断言，副本写入边界无变化 | 保留 driver/server/phase 日志；不要在共享根重试清理；该脚本为 standin 演练，不等于 real 链路 |
| 文档 | exit 0、missing=0；新增 Markdown 链接/锚点另核；迁移/冻结指纹与 STATUS 一致 | env_missing/known_missing 逐条保留；不能把数据根断链全部归为环境资产缺失 |

四门结果分别登记。只要必需门未通过/未运行，就不声称完整 DoD；允许注明已完成的软件切片及待内网关闭项。

## V8 真实 provider、非默认基线、S0 与恢复（条件式验收）

这部分不得由 V7 standin 结果替代。前置是内网 provider 配置、仿真许可/工具、专用数据与环境；通过现有配置入口配置凭据，不写入 Git、截图或日志。

```bash
cd "$VERIFY_CHECKOUT/loop"
record provider-probe .venv/bin/python spikes/probe_provider.py
```

该命令会发真实最小请求，检查 public 配置、成功响应与错误；返回的真实内容按内网留存规则处理。它只证明接通，不能证明各节点质量或整链通过。探针异常/超时停止相关验收。

| 任务 | 手动/产物核验步骤 | 退出证据 |
|---|---|---|
| F01-d | 使用合法非默认基线发起 real，按现行 UI/API 流程过人工闸门；对照选中 ID、N0、N1 parent、N2 输入和实际来源摘要；坏基线另跑拒绝用例 | run_id、模式/provider、基线指纹、各节点/闸门/双计数与 N16 真实结果；拒绝不得写副作用 |
| F04 | 实现并接入驱动后，在新派生副本依次校验基线/RTL 替换、授权 TB 适配、三库编译冒烟与准出；分别注入缺库/驱动失败 | 逐 hunk 台账、三库真实日志、准出字段、原件前后 MD5；未实现前保持阻塞 |
| F09 | 实现后按新规格依次测暂停→重启→显式恢复、重复恢复、旧响应晚到、完成竞态、写入失败 | 新进程 PID/快照版本、尝试编号、控制回执与账本副作用计数；恢复失败显式 failed；当前版本不具备该能力 |

F04/F09 的新执行接口尚未确定，本手册不编造命令。实现 owner 交付时必须把真实 CLI/API、请求样例和预期产物补到新切片验证文档，方可交给内网执行者验收。三道业务闸门始终由人阅读材料后决定；验证脚本内的演练 actor 不是真实人工批准。

## V9 留证、冻结与交接

在 VERIFY_OUT 新建结果表，每项记录：任务/验收 ID、被测 commit、命令、退出码、原始 pytest 总结、skip/deselect 原因、实际浏览器/provider、预期与实际、缺件、日志/截图、验证者。执行过程中改了代码或依赖就新建批次目录，不覆盖失败日志。

归档时新增证据文件与必要日志/截图（内网源码/敏感日志按访问范围留存，Git 只提交可共享件与可追踪摘要），先审核内容，再 chmod 444、计算 MD5，填入 STATUS 新节；不要修改旧 evidence/history/audit。保留首次失败和修复后输出两份，独立复核报告另新增，独立验证者不改代码。

完成判定：每项都有规格→任务→用例→命令→证据→提交的链条；既有未修 R 项、环境阻塞及未执行门继续可见。计划中的目标值与历史实测均不得填到「本轮实际」栏。
