# 下一轮 SpecDD 计划与内网验证手册：交付检查

日期：2026-10-22；基线 `343584c4ddbeb942f503aa04734368ed4062de37`。用户授权规划优化/重构、补充可在内网照做的验证计划并推送。本轮只改计划/导航/状态并新增本证据，未实施 R1–R5、F14/F05 或其它新能力。同一执行者编制和校核，不声称独立终验。

交付：[实施计划](../plans/2026-10-22-next-iteration-specdd.md)、[内网验证手册](../plans/2026-10-22-intranet-validation.md)。实测汇总唯一入口为 [STATUS](../STATUS.md) §37；本文件保留校核范围与原始输出。

## 1 同步与来源

```text
$ git fetch origin refs/heads/main
From https://github.com/rj-chenjunming/fpga_sim_workflow
 * branch            main       -> FETCH_HEAD
$ git merge --ff-only FETCH_HEAD
Already up to date.
```

核对 AGENTS 的顺序/写权/四道门，现行上下文/窗口/编排/环境/网页/S0 规格，以及 STATUS §33–§36。复核报告内容 MD5 为 `ace25b5d483802efbf061cf82e42a385`；已有证据指纹继续由各原 STATUS 节维护。

## 2 计划与命令校核

对新增计划和手册逐一解析相对 Markdown 链接并检查目标存在；提取全部 Bash 代码块送入 bash -n，嵌入 Python here-doc 送入 ast.parse；逐一核对现有 tests 路径。新模块和未实现能力未编造执行命令。校核输出：

```text
PASS: new plan/runbook Markdown targets, Bash syntax, embedded Python syntax and existing test paths.
```

源码核对的入口：browser_offline 四种 action/浏览器选取与 smoke 输出、软件层影子根/排除规则、pytest 的显式浏览器环境变量、CSS/测量工具、kb 自测临时运行名、端到端清理与 phase 汇总、文档路径分类。由此在手册明确普通 pytest 必须选择已通过 smoke 的浏览器，以及端到端只在专用副本执行。

此为语法与入口校核，未在当前云端执行手册的内网安装、全量测试、端到端、真实 provider 或仿真命令；不能推导这些能力已通过。

## 3 资源完整性与保护边界

```text
$ loop/.venv/bin/python loop/spikes/browser_offline.py verify
PASS: offline bundle platform and SHA-256 verification
```

逐个读取 HEAD 中既有 evidence/history/audit、kb 与 loop 文件，与工作树内容按字节比较：

```text
PASS: existing evidence/history/audit, frozen kb and application files match HEAD byte-for-byte.
```

git diff --check 退出成功，无输出。没有移动旧文件或修改旧证据；新增证据冻结后 MD5 记录在 STATUS。

## 4 全库文档门及既有缺口

执行 python3 doc/audit/check_doc_links.py，退出码为 1。按检查器 Report 原值输出：

```text
known_missing=10 env_missing=304 missing=116
doc_links_exit=1
```

为区分本次与既有问题，将 git ls-tree -rz --name-only HEAD 列出的 Markdown 原字节写到临时目录，使用相同 Roots 调用现有 scan；比较两侧 (doc, token, reason) 集合，不以因新增内容移动的行号作差异依据：

```text
PASS: whole-repository missing/env_missing finding sets match HEAD; new plan and runbook add no findings.
```

第一次临时对照脚本未使用 -z，Git 对中文路径的转义导致原始文档副本漏项，集合断言失败。改为 NUL 分隔重建后通过；这是校核脚本的问题，不计产品缺陷或 SpecDD 红灯。当前缺少内网根/数据与既有路径缺口继续可见，不声称全库文档门通过，不将全部 missing 归为环境缺件。

## 5 未运行与交接

本轮没有业务实现变更，未重复执行业务全套、浏览器回归、kb、完整端到端或真实 provider；各功能本轮状态仍为待实施/待验证。内网按 V0–V9 留证，R 项先新增目标缺陷红灯，再实现；纯重构先采集通过的行为/视觉基线。完整四道门未通过，不能标合规。
