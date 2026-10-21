# 全站网页视觉重设计 · 实测与预览

日期：2026-10-21（Asia/Shanghai）。基线：提交 `17650b6`。本轮同一执行者先固定交互特征，再实施与验证；没有独立验证者。

用户选择“专业清爽”，最终明确仅现有网页；本轮不开发桌面客户端，也不做手机端专项设计。契约：[Web UI §14](../spec/WEB_UI_SPEC.md#14-全站网页视觉系统2026-10-21)；[计划](../plans/2026-10-21-desktop-redesign.md)。本轮实测数字以 [STATUS §12](../STATUS.md#12-全站网页视觉重设计2026-10-21) 为准，下方保留命令原始摘要。

## 变更与边界

主工作台和旧界面共享本地视觉令牌，统一深墨导航、雾白工作区、青绿操作色及语义状态色。四视图集中到左侧导航；重排页标题、准备流程示意、S0 检查回执、配置步骤、执行阶段、Agent 卡、闸门材料/操作、目录浏览与 Agent 工作窗口。导航支持方向键、Home/End 与跳到主内容，切换后同步选中页和可访问状态。

请求协议、轮询、草稿与后端业务判据没有迁移到视觉层。页面保留 S0 未准出、未接入、投影来源及失败信息。未修改环境资产、kb 工具或先前冻结证据。旧静态样张保留为历史参考，没有把受控数据写入产品实现。

## 浏览器预览（受控 API 数据）

以下为真实 Chromium 加载仓库网页的截图；基线、计数、运行 A/B、模型状态均是测试路由提供的受控数据，不能作为真实模型调用或内网仿真结果。图中 `/fixture` 为测试目录标识。

| 页面 | 预览 | MD5 |
|---|---|---|
| 环境准备 | [查看](WEB_REDESIGN_20261021/1440-environment.png) | `ea074be9f75f76ec34a68675ce9e45a9` |
| 运行配置与目录浏览 | [查看](WEB_REDESIGN_20261021/1440-configuration.png) | `0b82750c4af97eb5735dee8ac3af11ca` |
| 运行监控 | [查看](WEB_REDESIGN_20261021/1440-monitor.png) | `c139bf61025ceea6b2f253e95f5910bd` |
| 人工闸门 | [查看](WEB_REDESIGN_20261021/1440-gate.png) | `e49eabe2710ec58432b3bcf88b3c51cc` |
| Agent 工作窗口 | [查看](WEB_REDESIGN_20261021/1440-agent.png) | `a40e2b6b04d00db90f8ddaa757eaa278` |
| 旧界面 | [查看](WEB_REDESIGN_20261021/1440-legacy.png) | `6c224ba7f9f1ce6e2dd7308441868e75` |
| 空态 | [查看](WEB_REDESIGN_20261021/1440-empty.png) | `183604c20e5d62a1a3f40ea142c4b340` |
| 加载态 | [查看](WEB_REDESIGN_20261021/1440-loading.png) | `23ab9522eae0560102be64d0f6f0961e` |
| 长错误提示 | [查看](WEB_REDESIGN_20261021/1440-error.png) | `9e148df64cfa397e6bd544edd43b1278` |

保存了浏览器截图原文件，未裁切或修饰；主工作台、旧界面及模态窗口均做过视觉检查。其余浏览器窗口尺寸的截图为临时验证产物，不作为仓库冻结件。

## 命令与原始输出摘要

在 `loop` 目录运行，浏览器使用 `/usr/bin/chromium`，API 响应由 Playwright route 控制。

实现前特征基线：

```text
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest tests/browser -q
28 passed in 41.26s
```

全套已有交互、新布局与静态页面冒烟（配置行布局最后细调前）：

```text
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium LOOP_VISUAL_ARTIFACTS=/tmp/fpga-web-redesign .venv/bin/python -m pytest tests/browser tests/test_web_smoke.py -q
39 passed, 1 warning in 56.31s
```

警告为 Starlette TestClient/httpx 的既有弃用提示。之后细调配置选项排版，补充真实基线列表与空/加载/失败截图装置，最终重跑受影响浏览器集合：

```text
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium LOOP_VISUAL_ARTIFACTS=/tmp/fpga-web-redesign .venv/bin/python -m pytest tests/browser/test_web_layout.py -q
8 passed in 15.59s
```

集合覆盖浏览器宽度 1280/1440/1920 的四页、目录选择器、长路径输入、闸门差异、Agent 控件、旧界面返回入口，以及方向键导航和空/加载/长错误提示。无写请求作为切页和预览的验收条件；原 S0/闸门/Agent 干预、焦点与响应隔离仍由前面的完整回归覆盖。

验证装置修正记录：首次新增旧界面预览装置没有拦截旧页面的 events 请求，出现 `3 failed, 4 passed in 13.14s`（KeyError: events）；加上该只读响应后综合回归通过。后补异常截图时错把隐藏的 runEmpty 当作加载容器，出现 `1 failed, 7 passed in 19.98s`；对照实际可观察界面改为 runHead/runAlerts 后上述最终集合通过。这两处是测试装置缺陷，没有据此宣称产品缺陷先红后绿。

实际 FastAPI TestClient 静态资源读取：

```text
HTTP 200 /
HTTP 200 /tokens.css
HTTP 200 /app.css
HTTP 200 /app.js
HTTP 200 /legacy.html
HTTP 200 /legacy.css
PASS: shared styles and compatibility console are served by the actual API.
```

另执行 `node --check` 检查 app.js、s0.js、agent-window.js（全部退出成功），以及 `git diff --check`；变更 Markdown 链接、截图 MD5 与既有冻结件另做只读检查，结果登记于 STATUS。

只读链接与冻结件核验的原始输出：

```text
PASS: changed Markdown links and screenshot targets resolve.
PASS: no additional unresolved inline paths versus HEAD.
PASS: previously frozen evidence contents are unchanged.
PASS: archived screenshot MD5 values match the evidence report.
```

链接检查覆盖本轮所有变更/新增 Markdown 的相对链接和截图目标；inline 引用按仓库现有扫描器对每份变更文件计算相对 HEAD 的新增未解析集合。冻结件逐一对照 HEAD 内容 MD5；没有重复运行已知受环境缺件影响的全库扫描，也不声称全库零断链。

## 限制

只验证网页展示及既有浏览器交互，不声称真实模型、UVS 工具链或完整闭环通过。本轮没有运行后端业务全套、kb 历史夹具自测或完整端到端；未对冻结环境执行写入。环境缺件、S0-b 尚未接入及其他审计缺口沿用既有 STATUS，四道门未全绿。浏览器截图中既有加载/错误文案按原行为显示，没有用视觉改动推导新的业务状态。

本报告与预览图冻结为只读；报告自身 MD5 记录在 STATUS，截图 MD5 记录在本目录外的此报告。
