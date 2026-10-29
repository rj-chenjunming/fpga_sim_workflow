S7b 工具白名单 · 真机取证原件（2026-10-29）
============================================

本目录是**纯文本/JSON 原件**，供 Lead 冻结进 doc/evidence/DSH_S7_20261029/。
本目录本身在 gitignored 的 loop/.logs/ 下，**不入库**。

一句话结论
----------
同一份 dsh 0.2.1-rc.2 真机 boot，只改 `tool_allowlist.enforce_visibility`：

  boot2（enforce_visibility=true）  ⇒ 引擎实际发给模型的工具清单 = **7 项**（= 允清单）
  boot3（enforce_visibility=false） ⇒ 引擎实际发给模型的工具清单 = **26 项**（全量 harness）

两份都是 `request/header.data.header.tools`（session log 里引擎发给模型的那份），
不是"注册表可见面"的推断值。清单外调用另有**一次真派发取证**（`probe`，见下表）。

文件
----
| 文件 | 内容 | 源 |
|---|---|---|
| `boot2_echo.json` | `phase` + `toolNames`（26 项逐项）+ `allowlist` 段**逐字**（含 `effective`/`denied`/`unknownAllowed`/`agentScope`/`probe`/`allowedProbe`/`enforceVisibility`） | `.logs/s7b/boot2/attempt/selfcheck/selfcheck.json`（md5 见文件内 `md5` 字段） |
| `boot3_echo.json` | 同上（`enforce_visibility=false`，`agentScope=null`、`enforceVisibility=false`） | `.logs/s7b/boot3/...` |
| `boot2_request_tools.json` | **模型请求体**里的工具清单（7 项）+ session log 路径与 md5 + 解压命令 | `.logs/s7b/boot2/attempt/dsh-home/sessions/**/session.v4.jsonl.zstd` |
| `boot3_request_tools.json` | 同上（26 项） | `.logs/s7b/boot3/...` |
| `submit_result_dispatch.json` | 旁路真派发 `submit_result` 的返回（`{"accepted":true,"problems":[]}`，`isError=false`）+ 该 boot 的 session 事件类型普查（**无** `tool/result`） | `.logs/s7b/exp/...` |

（同目录的 `dsh.py.base` / `dsh.py.wired` / `dsh_py_wiring.diff` 是给 Lead 审的接线草稿，
 不是证据；见 §B。）

生成命令（工作目录 = 仓库 `loop/`）
-----------------------------------
    # 1) 两个真机 boot（各一次）：enforce_visibility=true / false
    .venv/bin/python .logs/s7b/boot_probe2.py     # → .logs/s7b/boot2/
    .venv/bin/python .logs/s7b/boot_probe3.py     # → .logs/s7b/boot3/
    # 2) submit_result 旁路派发实验
    .venv/bin/python .logs/s7b/exp_run.py         # → .logs/s7b/exp/boot/
    # 3) 导出本目录
    .venv/bin/python .logs/s7b/make_evidence.py

三个脚本都只用 `host.agent_backends.dsh_process.run_attempt` 起一次**真 dsh 进程**，
参数与生产 attempt 同源（`ATTEMPT_PINS` 双钉、bwrap 包裹、`profile=headless`、
插件经 `--patch insert` 挂载），唯一差别是**没有 API key**。

为什么这条不消耗模型预算 / 不计入 B1 的真实调用额度
--------------------------------------------------
1. 环境里没有任何 `DEEPSEEK_API_KEY`/`PUBLIC_API_KEY`（`dsh.py::_api_key()` 取不到就不注入）。
2. 进程跑到"模型请求"阶段被引擎自己挡下并退出，stderr 原文：
   `dsh: MISSING_CREDENTIAL: llm-deepseek: no API key for provider route "deepseek-official"; …`
3. 到这一步时 **boot → 插件 apply → agent 创建 → 请求组装（含本证据要的 tool 清单）全部已完成**，
   自检的 `phase=deferred` 快照也已落盘；**没有任何 HTTP 请求发往模型端点** ⇒ token = 0。
4. `run_attempt` 因此抛 `ProcessFailed`（预期）：脚本捕获后只读产物。
   ⇒ 本片**真实模型调用 0 次**，不需要动用裁决 B1 的 S7b ≤2 次额度。

DSH_HOME（try 内 home = bwrap 里 `$HOME`）
-----------------------------------------
    boot2: <repo>/loop/.logs/s7b/boot2/attempt/dsh-home
    boot3: <repo>/loop/.logs/s7b/boot3/attempt/dsh-home
    exp  : <repo>/loop/.logs/s7b/exp/boot/attempt/dsh-home

实际 env 键（`dsh_process.build_env(spec)` 的产出；没有 API key）
--------------------------------------------------------------
基础白名单（`dsh_process._BASE_ENV_KEYS`）：
    PATH, HOME(=attempt dsh-home), DSH_HOME(=同上), DSH_PROFILE(=headless), PYTHONDONTWRITEBYTECODE
本片/自检追加（`env_extra`）：
    DSH_SELFCHECK_DIR   = <attempt>/selfcheck          （自检报告落点）
    DSH_SELFCHECK_NONCE = <per-attempt 随机 nonce>      （身份 join，防旧快照当准入）
    DSH_ATTEMPT_KEY     = EXP/N6/1 | RUN-PROBE/N6/2/3   （attempt 标识，自检逐字回显）
    DSH_TOOL_ALLOWLIST  = compact JSON（**本片新增，唯一配置通道**）
        boot2（enforce on）: {"allowed":["read","write","edit","glob","grep","bash","submit_result"],
                              "enabled":true,"enforce_visibility":true}
        boot3（enforce off）: 同上但 "enforce_visibility":false
    （exp 另有 EXP_OUT = <attempt>/selfcheck/exp_out.json，仅实验插件用）
说明：`build_env` 是**白名单**（`env -i` 等价物），宿主 env 一律不继承；白名单策略由
`dsh_allowlist.render_env` 渲染（唯一编码实现），插件只读这个 env、不解析 SETTINGS。

boot2 关键事实（enforce_visibility=true，默认档）
-----------------------------------------------
    phase=deferred
    toolNames（全局注册面）           = 26 项
    allowlist.allowed                = 7 项
    allowlist.effective              = [bash, edit, glob, grep, read, submit_result, write]
    allowlist.denied                 = 19 项（含 web_search/web_fetch/subagent/subagent_fork/
                                       workflow/send_message/job_output/job_list/job_kill/
                                       working_directory/skill/todo_write/…）
    allowlist.unknownAllowed         = []
    allowlist.agentScope.names       = 7 项（= 清单∩全局面，**本 agent 的作用域可见面**）
    **request/header.tools           = 7 项（引擎实际发给模型的清单）**
    allowlist.probe                  = {name: job_list, denied: true,
                                        code: TOOL_NOT_ALLOWLISTED, reason: 中文可读原因}
    allowlist.allowedProbe           = {name: read, code: INVALID_ARGS}
                                       （放行到参数校验；工具体未执行 ⇒ 排除"全拒"假通过）
    Host 判据 `dsh_allowlist.verify_echo(...)` = ()（零问题）

boot3 关键事实（enforce_visibility=false，回退档）
------------------------------------------------
    phase=deferred；toolNames=26；effective=7；denied=19
    allowlist.enforceVisibility = false；allowlist.agentScope = null
    **request/header.tools = 26 项**（模型仍看到全量面）
    probe / allowedProbe 与 boot2 相同（deny 层与收窄层独立）
    verify_echo = ()

旁路派发 `submit_result`（不经模型）
----------------------------------
    派发：tools.execute({name:'submit_result', arguments:{task_id,summary,payload}})
    返回：isError=false，value/content = `{"accepted":true,"problems":[]}`（插件 handler 真执行）
    会话：该 boot 的 session log 事件类型里**没有** `tool/result`
          ⇒ 旁路派发不写会话日志、不进提交记账，不会被 `dpr.require_submission` 当成提交。
          （durable 写入只有 agent loop：`dsh-agent-loop/lib/index.js:697`
            `session.append("tool/result", …)`。）

代码状态（生成证据时的实现；被打包进 Lead 的 stash，见下）
--------------------------------------------------------
本目录的产物生成于下列实现的树内（Lead 为跑 S7a 门把这些改动 stash 了：
`stash@{0}` = "s7b+s7c-wip-during-s7a-gates"，**不是**丢件；恢复 = `git stash pop`）：

    loop/host/agent_backends/dsh_allowlist.py                  md5 b3be64669cd575e9dab86a908d311aa9
    loop/host/agent_backends/dsh_plugin/tool_allowlist.mjs     md5 f6586087985ed577f26df7e7de20e48a
    loop/host/agent_backends/dsh_plugin/selfcheck.mjs          md5 ac9c1a539312dd7801c97f0ac45df6c1
    loop/host/agent_backends/dsh_selfcheck.py                  md5 5179dc4f95f663b0d4c74e8723bc4909
    loop/tests/test_dsh_tool_allowlist.py                      （唯一测试入口，61 例）

注意：`boot2_echo.json`/`boot3_echo.json` 生成于最后一处**非行为性**改动之前
（`surfaceNames()` 在"schemas 有条目缺 name"时改为 fail-closed；本次 26 项全部有 name，
该分支未被触发）。`submit_result_dispatch.json` 生成于最终实现之后。
pop 之后重跑 `make_evidence.py` 可复核（见下）。

复现（Lead pop 之后）
--------------------
    cd loop
    bash -c 'git stash pop'                      # 恢复 S7b+S7c WIP（Lead 自己的节奏，别由别人代跑）
    .venv/bin/python .logs/s7b/boot_probe2.py
    .venv/bin/python .logs/s7b/boot_probe3.py
    .venv/bin/python .logs/s7b/exp_run.py
    .venv/bin/python .logs/s7b/make_evidence.py
    # 期望：boot2_request_tools 7 项 / boot3_request_tools 26 项；
    #      两份 echo 的 verify_echo 均为 ()
    # 复核模型请求体清单（本目录提取逻辑的原始命令）：
    zstd -dc <session>.zstd | python3 -c \
      'import sys,json;[print(len(e["data"]["header"]["tools"])) for l in sys.stdin
        if (e:=json.loads(l)).get("type")=="request/header"]'
