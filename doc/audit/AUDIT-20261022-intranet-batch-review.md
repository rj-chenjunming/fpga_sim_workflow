# 内网批次拉取后的代码复核

> **本轮是否修复：否。** 拉取远端 main，从 `fb83ed0` 快进至 `a19107c`；本轮只审查实现、运行受控验证并新增复核文档，不修改业务代码。
> 日期：2026-10-22（Asia/Shanghai）。同一执行者进行源码复核与测试，不冒充独立终验。实际结果以 [STATUS §35](../STATUS.md#35-内网批次拉取后复核2026-10-22) 为准。

结论：本批有实质进展，原基线有效性/参数传递、guardian 旧说明和首次错误展示均有实现与覆盖，模型请求与节点辅助也已建立模块边界。但 F08 的发布中断窗口仍可使整个节点历史不可读，另有基线路径、坏编码、N8 可行预算和预算展示问题，不建议将这些相关切片直接标记为最终收口。

## 复核范围与已确认进展

- F01：列表与创建复用 `host.baseline`，real 创建先准入，N1/N2 消费选中身份；空对象/数组 manifest 的旧问题已有测试。
- F02/F13：能力投影由服务端提供，角色卡与窗口复用格式化；加载、首次失败与已有数据刷新失败通过单一模块推导，旧回包仍按身份隔离。本轮已有浏览器用例全部通过；具体输出见 STATUS。
- F03/F06/F05：软件 state 可注入，提供影子数据根检查入口、环境层标记和文档根路由；模型机制与节点事实分离；闸门会话判定先作纯函数提取。
- F07/F10/F11：先测量再决定分页/缓存、只读解释和尝试差异均有落点。保留 token 未知、不自动扩大权限的方向合理。
- F14 尚未进行样式收敛，F05 后续拆分、F04、F09 等继续保持未完成；这与 STATUS §33 的登记一致，不把静态清单当作视觉重构完成。

以下只登记已受控复现的问题。优先级 P1 表示应先处理的可靠性缺口，P2 表示需要修正的边界或展示错误；不声称真实内网运行已受影响。

## R1 · P1 · 校验和直接发布仍暴露半写文件，杀进程可阻断全部历史读取

定位：[seal_record](../../loop/host/agent_memory.py#L113)、[record_state](../../loop/host/agent_memory.py#L124)、[read_view](../../loop/host/agent_control.py#L86)。

校验和仍通过 `_write_once` 在最终文件名上 `O_CREAT|O_EXCL` 创建，然后缓冲写入、flush、fsync。在 open 成功而 flush 尚未完成时被终止，会留下空或不完整的 `.sha256`。新诊断将其判成 `corrupt`，`read_view` 随即抛错；即使之前有完整尝试，也不能读取其视图。这是正常进程终止能留下的状态，与外部篡改无关。

现有 `test_sigkill_during_publish_loop_never_yields_consumable_partial` 在本轮综合检查中失败，单独复跑又通过。固定故障点探针先封存一个完整尝试，再在下一次 `seal_record` 创建校验文件后令真实子进程退出，稳定观察到 `prior_state=committed`、`checksum_bytes=0`、`partial_state=corrupt` 和整体 checksum mismatch。

建议先定义可原子识别的发布点：完整写入并同步私有临时件，再以不覆盖已有编号的操作原子发布校验/提交标记；保留真正 checksum mismatch 的显式失败，不能通过吞掉所有 corrupt 来变绿。新增“校验文件创建后、写入前”及“部分写入后”的确定性故障断言，证明旧完整尝试仍可读，并保留现有 SIGKILL 压力检查。

## R2 · P2 · 相对 artifact 路径绕过允许根校验

定位：[_artifact_path 的相对路径分支](../../loop/host/baseline.py#L97)。

绝对路径分支会 resolve 后检查工作区、其父和环境根；相对分支仅判断 `(base / candidate).exists()`，没有相同的范围检查。临时合法 manifest 的 allfiles 路径改成 `../../<另一个临时目录>/outside.md5` 并填写真实摘要后，基线仍 `valid=true`，目标位于所有允许根之外；同一文件改为绝对路径则被拒绝。相对符号链接也存在同样的检查缺口。

这会让基线准入接受范围外的材料并读取/哈希它，破坏新增准入所承诺的路径边界；本轮不推断远程可利用性。建议所有候选统一 resolve 和允许根判断后再读文件，并补 `..`、外部符号链接、绝对/相对等价路径的成对用例。

## R3 · P2 · 非 UTF-8 manifest 仍使整个基线列表返回 500

定位：[manifest 读取异常处理](../../loop/host/baseline.py#L153)。

`read_text(encoding="utf-8")` 可抛 `UnicodeDecodeError`，当前 except 只捕获 OSError/JSONDecodeError。临时目录的一个 manifest 写为非 UTF-8 字节后，真实 `GET /api/baselines` 返回 HTTP 500，而不是该项 `valid=false + errors`；同目录其它合法基线也无法正常列出。real 创建同样无法按结构化基线错误收敛。

建议把解码失败归入该条目的 errors，继续列出其它条目；在列表 API 与 real 创建入口各补一条可观察断言，不使用 `errors="ignore"` 静默改写清单内容。

## R4 · P2 · N8 把片段成本当作最小成本，存在可行全文却被拒绝

定位：[min_cost 与打包选择](../../loop/workflows/chunks/model_steps.py#L790)，另见提前使用近似值拒绝的 [total_min](../../loop/workflows/chunks/model_steps.py#L746)。

小文件全部行都变更时，片段含额外定位头、coverage 值，可能比全文更大。当前只要存在 region，就把 region_cost 当作最小成本，预留给后续文件，再在预算不足时把全文“降级”为更大的片段。实测默认预算下，全部全文可装入，算法却选择更大的片段集合并抛错；精确字节见 STATUS 与原始证据。

建议先构造实际条目，非强制片段的最小成本取 `min(full_cost, region_cost)`；数组标点按真实组合计费，只在成本确实下降时降级。删除或修正提前基于近似成本的拒绝。增加“所有行都变、片段更大”“刚好能装入全文”“默认预算可行”断言，保留确定性顺序和全部文件覆盖。

## R5 · P2 · 工作窗口预算使用率与 Host 实际计费口径不同

定位：[ContextExplain 的字段清单与求和](../../loop/web/context-explain.js#L14)、[Host check_budget](../../loop/host/agent_memory.py#L97)。

Host 计费为紧凑编码后的完整 `{input, info, instruct, schema}`。前端把各字段值分别 JSON 编码相加，额外计入未发送给模型的 `offered` 和 `scope`，却漏掉对象字段名/标点。相同请求探针得到 Host 与界面不同的数值。额外的校验材料较大时，会显示高使用率甚至超限，即使 Host 判定实际输入远低于上限；缺少这些材料时又会低估。

建议由 Host 公开并复用一份预算统计，在 API 下发实际计费总数/构成；offered/scope 若要展示，单列为记录存储大小。补充用同一已封存请求对照 `AM.check_budget` 和窗口显示的跨层断言，不能只断言前端总数等于自身行求和。

## 验证边界与复现入口

[受控探针](parts/intranet-batch-probe.py) 使用临时目录、受控 HTTP、实际子进程终止和 Node 纯函数；不连接 provider/仿真器，不修改现有基线/运行。探针退出成功只表示观察完成，不能作为缺陷修复验收。原始命令、输出、套件失败栈及文档门限制见 [本轮证据](../evidence/INTRANET_REVIEW_20261022.md)（MD5 `976c315044d5c65ff4e8b3279c3c5bb9`），汇总记于 STATUS §35。

本轮环境没有注册表指向的内网 ENV_ROOT/WORKSPACE_ROOT 和历史夹具；不能复现旧 STATUS 的软件层全套数字。文档门的本机缺件与真实断链仍按原始输出记录，不把内网缺件冒充代码回归。未执行 kb 自测、会清理共享状态的完整端到端或真实 provider；本轮通过的浏览器用例证明已有受控路径，未证明新增预算解释的计费正确性或真实模型效果。

建议顺序：先修 R1 的发布点，再修 R2/R3 基线边界和 R4 可行预算，最后修 R5 展示口径。随后补齐每项对应失败用例并复验；F01-d、S0-b 和 F09 仍按已有外部前置条件推进。
