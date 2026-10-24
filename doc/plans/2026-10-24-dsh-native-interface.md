# DSH 原生接口核验与下一切片

日期：2026-10-24。用户在 D1 交付后补充授权通过 npm 安装 dshweb。
本页是 D0 发现与 D2 前置计划，不声明 DSH 后端已可用于业务节点。
安装和无模型探针结果归 [STATUS §57](../STATUS.md#57-dsh-npm-安装与原生协议探针2026-10-24)。

## 发行包与当前实例

npm 的 dshweb 名称查询返回不存在；搜索和包内文档确认 CLI 为
[@deepseek-ai/dsh](https://www.npmjs.com/package/@deepseek-ai/dsh/v/0.2.1-rc.2)，
其 repository 字段指向 [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)。
已按确切版本独立安装在 /workspace/dsh-runtime，未加入本软件仓依赖；安装禁用 lifecycle scripts。
DSH_HOME、DSH_AGENTS_HOME、cwd 各自位于该独立目录，未导入旧宿主凭据、设置或会话。
运行方式与复核脚本见本次证据，安装版本、依赖锁指纹与包内文档指纹见 STATUS 引用的归档。

安装新的 npm 版本只补足此实例的公开运行时，不证明与原内网 DSH 安装版本/插件/模型配置等价。
Web 只是同一核的一种 profile；自动化接入应使用包内已确认的 SDK profile。

## 与原拟议设计的实际映射

| 需求 | 当前发行版实际接口/行为 | D2 实施决定与前置条件 |
|---|---|---|
| 结构化传输 | dsh --profile sdk，逐行 JSON-RPC；stdout 只承载协议 | 锁定安装版本及依赖树；未知或非 JSON 帧失败，不能照搬原生 transport 的忽略坏行行为 |
| 运行时就绪 | initialize 接收 cwd/provider/model，返回 serverInfo | 校验协议固定名称；serverInfo.version 不是 npm 版本，二者分别记录；握手不等于凭据可用 |
| 输入入队 | session/prompt 返回 messageId | messageId 仅为入队身份，不是结果身份；每 attempt 独立进程、独立 session、单次 prompt |
| 完成观测 | session.event、session.status、session/wait | idle 或 wait 回执不能代替有效 turn/end 与结构化业务候选；先核验事件顺序、目标身份和终态，再走原 Host 校验 |
| 取消/关闭 | 无逐 prompt 取消或逐 session 关闭，只有进程级 shutdown/EOF/信号 | 暂停/补充指令必须关闭旧进程，确认子进程受管范围停稳后重发；未知停止仍阻断，禁止共享进程承载多个 attempt |
| 历史/恢复 | session/resume 可加载并修复历史 | 首版不使用；目录/会话隔离、隐式历史及空上下文证据仍须实测 |
| 模型与工具 | 完整 sdk 继承 base 配置、托管凭据和工具 | 固定模型路由与最小允许工具；不导入 Web 用户配置，不启用子 Agent、持久 shell、工作流工具或任意插件 |
| 上下文完整 | base 含 compaction；sdk-minimal 明确自动压缩并允许高权限 shell | 不直接选 sdk-minimal 当安全最小配置；建立受限 profile，关闭自动压缩/结果裁剪，并验证实际模型上下文可核验 |
| token 达限 | sdk 默认允许 maxTokensAsSuccess | 显式关闭这一默认，截断/预算耗尽必须失败，不能当结构化结果完成 |
| 子进程控制 | 官方 subprocess 文档区分 Linux systemd scope 与较弱 fallback | 本轮没有工具子进程，空闲进程退出不构成后代终止证明；须验证宿主强制边界及异常退出清理 |

协议事实来自安装包的 README.zh.md、SDK 协议类型与服务端实现；版本/哈希在证据中定位。
本次 SDK 只发 initialize、未知会话 wait、shutdown；没有 prompt、真实模型、工具或业务目录写入。
Web 只在 loopback 启动；匿名请求被鉴权拦截后关闭，没有输出启动凭据、打开浏览器或暴露外部端口。

## 下一片按 SpecDD 推进

实现 owner 仍为 Host 接入层；先按 SPEC-08 修订受限 profile、进程/会话身份、事件与结果选择契约。
先失败用例覆盖坏帧、身份不符、无终态/重复终态、模型拒绝/超时、预算耗尽、停机超时及子进程存活。
在受控协议端通过后，再以原生运行时验证相同边界；真实模型认证、工具权限强制与上下文完整性单独验收。
只有 D0 的能力门完整满足，才接入 N3 只读探针；N6 候选应用和价值对照继续后置。

当前仍保留显式 DSH 不可用的准入拒绝。不能仅因 npm 安装、Web 可启动或 SDK 握手成功就切换业务后端。
