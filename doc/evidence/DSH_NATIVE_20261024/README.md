# npm DSH 原生启动与 SDK 探针证据

日期：2026-10-24。来源：用户补充要求通过 npm 安装 dshweb。
本轮实际安装、无模型启动验证及接口阅读；同一执行者，无独立终验。
版本/结果数字与限制见 [STATUS §57](../../STATUS.md#57-dsh-npm-安装与原生协议探针2026-10-24)，
设计影响见 [原生接口计划](../../plans/2026-10-24-dsh-native-interface.md)。

发行版：[npm 固定版本](https://www.npmjs.com/package/@deepseek-ai/dsh/v/0.2.1-rc.2)。
安装在项目外独立目录，命令为：

```bash
npm --prefix /workspace/dsh-runtime --cache /tmp/dsh-npm-cache install \
  --ignore-scripts --no-audit --no-fund --save-exact @deepseek-ai/dsh@0.2.1-rc.2
```

[归档包](probe.tar.gz) 仅含公开依赖锁/包清单、探针脚本与其白名单摘要、包文档/协议实现指纹。
不含 DSH_HOME、配置、凭据、原始诊断或 Web 启动 URL。
目录外 [MD5 清单](../DSH_NATIVE_20261024.md5) 校验冻结件。

复核：在同名独立目录按依赖锁执行 npm ci --ignore-scripts --no-audit --no-fund，
将 probe_runtime.py 放在安装根，预建 home/agents/workspace/probe-evidence 子目录后执行。
脚本使用明确的 DSH_HOME/DSH_AGENTS_HOME、关闭 telemetry；SDK 不发送 prompt，
Web 仅监听 loopback，并在探针结束后停止自建进程。
输出仅保留协议固定身份匹配、错误码/固定错误类别、HTTP 状态和受管进程组退出事实。

认证拦截不能当网页功能验收；空闲 SDK 停机不能当工具后代全部停止；握手不能当模型认证通过。
安装时禁用了 lifecycle scripts，未执行原生工具，因此它们的构建和宿主可用性仍待核验。
