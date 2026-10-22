# F14-a · 改前样式基线（style inventory）

日期：2026-10-22 11:24:26 +0800（Asia/Shanghai）。采集时仓库 `HEAD=746ec8d13ea857e4dcb30190d1fcc8c27b0458b7`，分支 `main`，工作树脏文件：`doc/spec/AGENT_CONTEXT_SPEC.md、doc/audit/R1-verify-20261022.md、doc/audit/R2-verify-20261022.md、doc/audit/R3-verify-20261022.md、doc/audit/R4-verify-20261022.md、doc/audit/R5-verify-20261022.md、doc/evidence/R_BLOCK_B_20261022.md、doc/evidence/R_BLOCK_B_20261022_after_probe.py、doc/evidence/R_BLOCK_C_20261022/`。

本文件是 **F14-b 样式收敛的改前对照基线**，由只读采集脚本 [collect_f14a.py](collect_f14a.py) 与现有 `loop/tests/browser` 生成。全部页面数据来自 Playwright 受控 API 替身，不是真实模型/内网仿真结果。同一执行者分阶段采集，不是独立视觉评审；**不声称视觉验收通过**。

## 0 采集环境

| 项 | 值 |
|---|---|
| 浏览器 | Chrome `152.0.7977.75`（`/usr/bin/google-chrome`） |
| Playwright | `1.64.0` |
| Python | `3.11.7 (/home/work/chenjunming/change-impact-loop/loop/.venv/bin/python)`（`loop/.venv`） |
| 操作系统 | `Linux-4.18.0-553.el8_10.x86_64-x86_64-with-glibc2.28` |
| 视口（主验收） | 1280×1000 / 1440×1000 / 1920×1000，`devicePixelRatio=1`、`visualViewport.scale=1`（**100% 缩放**） |
| 窄屏（仅溢出检查） | 390×844 / 768×844 |
| 页面语言 / 时区 | `en-US` / `Asia/Shanghai` |
| prefers-reduced-motion 对照 | no-preference 与 reduce 各跑一次（见 §7） |
| 采集命令 | 见 [commands.md](commands.md) |

正文/等宽字体计算值（1280 视口，三视口一致）：

```text
body font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", "Microsoft YaHei", sans-serif
body font-size  : 14px
mono font-family: SFMono-Regular, Consolas, "Liberation Mono", monospace
document.fonts.check('14px Inter')         = True
document.fonts.check('14px "Noto Sans SC"') = True
document.fonts.check('12px ui-monospace')  = True
```

> 字体族声明同一份 `--font-sans`/`--font-mono` 令牌，但 `app.css` 多处直接写死系统字体栈（body、`.mono`、`.stage-range` 等），令牌与硬编码并存，属 F14-b 的收敛对象；本文件只记录事实。

## 1 截图索引（screens-before/）

| 文件 | 像素 | 状态 | 来源 | MD5 |
|---|---|---|---|---|
| [1280-agent.png](screens-before/1280-agent.png) | 1280×1000 | Agent 工作窗口（loop/tests/browser 落图，视口内） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `7589ce94adad53ffb628d3bd5a9cc936` |
| [1280-configuration.png](screens-before/1280-configuration.png) | 1280×1768 | 运行配置 + 基线目录浏览器（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `cda246a2cc29d5a4d9c8dab2bc19b407` |
| [1280-dirpicker-baseline.png](screens-before/1280-dirpicker-baseline.png) | 1280×1821 | 基线目录浏览器 | collect_f14a.py | `880eb11a3b7108f40550ba53733ca339` |
| [1280-dirpicker-project.png](screens-before/1280-dirpicker-project.png) | 1280×1863 | 项目目录浏览器 | collect_f14a.py | `df8bcb470ee54f77c21eb55d0d085850` |
| [1280-empty.png](screens-before/1280-empty.png) | 1280×1000 | 运行视图空态 | collect_f14a.py | `70549e6d0730086a2ff6a28b4745bd92` |
| [1280-environment.png](screens-before/1280-environment.png) | 1280×1655 | S0 环境准备（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `1c59d6c16575e901a1931e1187f775f8` |
| [1280-error.png](screens-before/1280-error.png) | 1280×1524 | 首次读取失败态 | collect_f14a.py | `becfc6e5237847dbb6777b4f7530cf1c` |
| [1280-gate-rejected.png](screens-before/1280-gate-rejected.png) | 1280×1780 | 闸门被拒（403 blockers） | collect_f14a.py | `ecbabab95de15024da9321132f033342` |
| [1280-gate.png](screens-before/1280-gate.png) | 1280×1780 | 人工闸门（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `ab1422b81c02be52d4e92e7ed4066f33` |
| [1280-legacy.png](screens-before/1280-legacy.png) | 1280×2597 | 旧界面（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `258ad9827d3d2c804248c3e598aab3dd` |
| [1280-loading.png](screens-before/1280-loading.png) | 1280×1415 | 首次读取加载态 | collect_f14a.py | `a9ab4d6ae1a5f87267768553ddd8f8fa` |
| [1280-monitor.png](screens-before/1280-monitor.png) | 1280×2309 | 运行监控（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `a65a7d00f9d34773c3967d8e7d6f719a` |
| [1280-run-failed.png](screens-before/1280-run-failed.png) | 1280×2395 | 运行失败（error + notes） | collect_f14a.py | `ed2818de052287d0e1827b299a94241b` |
| [1280-s0-script.png](screens-before/1280-s0-script.png) | 1280×1655 | S0 环境准备（采集脚本落图，用于状态对照） | collect_f14a.py | `fbdc4299439e04fb28ca2d02e6fbffae` |
| [1280-stale.png](screens-before/1280-stale.png) | 1280×2483 | 已有数据但刷新失败（陈旧） | collect_f14a.py | `92902614e179595605846126aebc997c` |
| [1440-agent.png](screens-before/1440-agent.png) | 1440×1000 | Agent 工作窗口（loop/tests/browser 落图，视口内） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `5f7b78bc5d9d8ade6556524d84bedd27` |
| [1440-configuration.png](screens-before/1440-configuration.png) | 1440×1768 | 运行配置 + 基线目录浏览器（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `35f9859478b898083644705ee8261419` |
| [1440-dirpicker-baseline.png](screens-before/1440-dirpicker-baseline.png) | 1440×1821 | 基线目录浏览器 | collect_f14a.py | `a77ad17f719170dd172f688efc1ddfba` |
| [1440-dirpicker-project.png](screens-before/1440-dirpicker-project.png) | 1440×1863 | 项目目录浏览器 | collect_f14a.py | `91de798cbf9381c4c2db399a5458e54e` |
| [1440-empty.png](screens-before/1440-empty.png) | 1440×1000 | 运行视图空态 | collect_f14a.py | `4e24bda6a775f520cf4a924245db6316` |
| [1440-environment.png](screens-before/1440-environment.png) | 1440×1672 | S0 环境准备（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `8944353bee7a28798eef8f4c671e4777` |
| [1440-error.png](screens-before/1440-error.png) | 1440×1524 | 首次读取失败态 | collect_f14a.py | `b2ce394ac9dec83b4f6083133cf74587` |
| [1440-gate-rejected.png](screens-before/1440-gate-rejected.png) | 1440×1780 | 闸门被拒（403 blockers） | collect_f14a.py | `9f171b36488e9e006de7bf5f13d59347` |
| [1440-gate.png](screens-before/1440-gate.png) | 1440×1780 | 人工闸门（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `5e2f92ae768fd4546c61eb5768608308` |
| [1440-legacy.png](screens-before/1440-legacy.png) | 1440×2597 | 旧界面（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `b52f89767e2206be8015eb7b0f7f6f5a` |
| [1440-loading.png](screens-before/1440-loading.png) | 1440×1415 | 首次读取加载态 | collect_f14a.py | `51cb608d0dfc3caf6a3ecc6516ac929a` |
| [1440-monitor.png](screens-before/1440-monitor.png) | 1440×2309 | 运行监控（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `4c795c55f984f6704ab78ccc299f7b83` |
| [1440-run-failed.png](screens-before/1440-run-failed.png) | 1440×2395 | 运行失败（error + notes） | collect_f14a.py | `55a14bde3d84ddaea3e1597aee6e1d66` |
| [1440-s0-script.png](screens-before/1440-s0-script.png) | 1440×1672 | S0 环境准备（采集脚本落图，用于状态对照） | collect_f14a.py | `1cb9facb90caf035a84673898970ac6b` |
| [1440-stale.png](screens-before/1440-stale.png) | 1440×2333 | 已有数据但刷新失败（陈旧） | collect_f14a.py | `6d75db80b16ba1f0c12c9fca9cc79b34` |
| [1920-agent.png](screens-before/1920-agent.png) | 1920×1000 | Agent 工作窗口（loop/tests/browser 落图，视口内） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `be7880ca1713d05c9f1079e588d96de2` |
| [1920-configuration.png](screens-before/1920-configuration.png) | 1920×1782 | 运行配置 + 基线目录浏览器（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `f0d2947fb62538e288a715dc5ed6e9f8` |
| [1920-dirpicker-baseline.png](screens-before/1920-dirpicker-baseline.png) | 1920×1835 | 基线目录浏览器 | collect_f14a.py | `3721bbcb9b782e48c66f1129db0db0f1` |
| [1920-dirpicker-project.png](screens-before/1920-dirpicker-project.png) | 1920×1877 | 项目目录浏览器 | collect_f14a.py | `4470ee6416067fbfe69a63ca6eddb6c5` |
| [1920-empty.png](screens-before/1920-empty.png) | 1920×1000 | 运行视图空态 | collect_f14a.py | `14b2abf4683a1e6be47877a00b9b6bee` |
| [1920-environment.png](screens-before/1920-environment.png) | 1920×1696 | S0 环境准备（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `ffcc395f34b388797734f27bb3fb632a` |
| [1920-error.png](screens-before/1920-error.png) | 1920×1516 | 首次读取失败态 | collect_f14a.py | `34f242ec967900c3b1b55e6c872240af` |
| [1920-gate-rejected.png](screens-before/1920-gate-rejected.png) | 1920×1756 | 闸门被拒（403 blockers） | collect_f14a.py | `8e899fa10410e06fdf3857b7e3fcb719` |
| [1920-gate.png](screens-before/1920-gate.png) | 1920×1756 | 人工闸门（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `1d7874998cb6de8a14e8cfcecbd5bc2f` |
| [1920-legacy.png](screens-before/1920-legacy.png) | 1920×2544 | 旧界面（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `5fbc82b781028fa38272093f7958cfc1` |
| [1920-loading.png](screens-before/1920-loading.png) | 1920×1429 | 首次读取加载态 | collect_f14a.py | `a6a936648e6fa4a3f4944ff23c543842` |
| [1920-monitor.png](screens-before/1920-monitor.png) | 1920×2323 | 运行监控（loop/tests/browser 落图） | loop/tests/browser（LOOP_VISUAL_ARTIFACTS） | `e83556c4197fff489042224dd17e1db9` |
| [1920-run-failed.png](screens-before/1920-run-failed.png) | 1920×2409 | 运行失败（error + notes） | collect_f14a.py | `63228d8ece157065501eea72256709f9` |
| [1920-s0-script.png](screens-before/1920-s0-script.png) | 1920×1696 | S0 环境准备（采集脚本落图，用于状态对照） | collect_f14a.py | `789c710d769ebe18e3d760139ddf500e` |
| [1920-stale.png](screens-before/1920-stale.png) | 1920×2327 | 已有数据但刷新失败（陈旧） | collect_f14a.py | `f3e5cca92f5ed40ee8604436217b27dd` |

> `loop/tests/browser` 的 `capture()` 在 `LOOP_VISUAL_ARTIFACTS` 下自动落图；空/加载/失败、目录浏览器、闸门拒绝、失败运行等补充状态由采集脚本落图。两者都是 `page.screenshot(full_page=True)`（`*-agent` 为视口内截图），未裁切。

## 2 媒体查询与断点生效矩阵

| # | 源文件:行 | 条件 | 内部规则数 | 1280 | 1440 | 1920 |
|---|---|---|---|---|---|---|
| 1 | `app.css:97` | `(max-width: 1180px)` | 1 | — | — | — |
| 2 | `app.css:197` | `(max-width: 1100px)` | 1 | — | — | — |
| 3 | `app.css:397` | `(min-width: 1550px)` | 3 | — | — | ✅ 命中 |
| 4 | `app.css:398` | `(max-width: 1200px)` | 14 | — | — | — |
| 5 | `app.css:399` | `(max-width: 1000px)` | 12 | — | — | — |
| 6 | `app.css:400` | `(max-width: 760px)` | 43 | — | — | — |
| 7 | `app.css:401` | `(prefers-reduced-motion: reduce)` | 1 | — | — | — |
| 8 | `app.css:453` | `(max-width: 850px)` | 17 | — | — | — |
| 9 | `app.css:622` | `(min-width: 1101px)` | 2 | ✅ 命中 | ✅ 命中 | ✅ 命中 |
| 10 | `app.css:725` | `(min-width: 1600px)` | 9 | — | — | ✅ 命中 |
| 11 | `app.css:726` | `(min-width: 1101px) and (max-width: 1390px)` | 19 | ✅ 命中 | — | — |
| 12 | `app.css:727` | `(min-width: 761px) and (max-width: 1100px)` | 13 | — | — | — |
| 13 | `app.css:729` | `(max-width: 760px)` | 36 | — | — | — |
| 14 | `app.css:730` | `(prefers-reduced-motion: reduce)` | 1 | — | — | — |
| 15 | `(inline style):?` | `(max-width: 1080px)` | 1 | — | — | — |
| 16 | `(inline style):?` | `(max-width: 760px)` | 1 | — | — | — |
| 17 | `legacy.css:74` | `(max-width: 1080px)` | 1 | — | — | — |
| 18 | `legacy.css:75` | `(prefers-reduced-motion: reduce)` | 1 | — | — | — |

源码 `@media` 出现次数（只读解析 `loop/web/*.css`）：`tokens.css=0`、`app.css=14`、`legacy.css=2`，合计 16 次；另有 `legacy.html` 内联 `<style>` 2 条（`max-width:1080px`、`max-width:760px`）。CSSOM 采集到 18 次出现、16 个不同条件；差额即同条件重复（`app.css` 的 `max-width:760px` 与 `prefers-reduced-motion:reduce` 各出现两次）。行号只对链式样式表有效，内联样式记为 `(inline style)`。

> 观察（事实，不是结论）：`760/761`、`1100/1101`、`1180/1200/1390/1550/1600` 构成重叠与交界；两份 `max-width:760px` 与两份 `prefers-reduced-motion:reduce` 内容不同但条件相同。F14-b 合并/收敛时必须逐条核对交界宽度 ±1px。

## 3 版面几何（三视口）

| 状态 | 视口 | 文档 scrollWidth | header | 侧栏宽 | 主区宽 | main padding | shell 方向 | .grid2 | .run-grid | #agents |
|---|---|---|---|---|---|---|---|---|---|---|
| run-empty | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | repeat(2, minmax(0px, 1fr)) | 1fr |
| s0 | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | repeat(2, minmax(0px, 1fr)) | 1fr |
| setup | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | 489px 489px | repeat(2, minmax(0px, 1fr)) | 1fr |
| dirpicker-baseline | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | 489px 489px | repeat(2, minmax(0px, 1fr)) | 1fr |
| dirpicker-project | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | 489px 489px | repeat(2, minmax(0px, 1fr)) | 1fr |
| run | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| run-failed | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| gate | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | repeat(2, minmax(0px, 1fr)) | 1fr |
| gate-rejected | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | repeat(2, minmax(0px, 1fr)) | 1fr |
| agent | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| legacy | 1280×1000 | 1280 | 1280×116.8 | — | — | `—` | — / — | — | — | — |
| run-empty | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| s0 | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| setup | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 551px 551px | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| dirpicker-baseline | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 551px 551px | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| dirpicker-project | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 551px 551px | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| run | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| run-failed | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| gate | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| gate-rejected | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | 1fr 1fr |
| agent | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| legacy | 1440×1000 | 1440 | 1440×116.8 | — | — | `—` | — / — | — | — | — |
| run-empty | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| s0 | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| setup | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 779px 779px | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| dirpicker-baseline | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 779px 779px | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| dirpicker-project | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 779px 779px | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| run | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |
| run-failed | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |
| gate | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| gate-rejected | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | minmax(0px, 1.45fr) minmax(320px, 1fr) | repeat(2, minmax(0px, 1fr)) |
| agent | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |
| legacy | 1920×1000 | 1920 | 1920×116.8 | — | — | `—` | — / — | — | — | — |
| loading | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| first-error | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| stale-error | 1280×1000 | 1280 | 1280×72 | 224 | 1056 | `28px 28px 28px 28px` | flex / row | repeat(2, minmax(0px, 1fr)) | 490px 490px | 444px |
| loading | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| first-error | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| stale-error | 1440×1000 | 1440 | 1440×72 | 244 | 1196 | `32px 36px 24px 36px` | flex / row | 1fr 1fr | 651.016px 448.984px | 295.5px 295.516px |
| loading | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |
| first-error | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |
| stale-error | 1920×1000 | 1920 | 1920×72 | 244 | 1676 | `38px 48px 28px 48px` | flex / row | 1fr 1fr | 920.891px 635.109px | 430.438px 430.453px |

## 4 关键元素计算样式（每视口）

属性缩写：字号/行高/字重 · 前景/背景 · 边框（上宽 上色）· 圆角 · padding · margin · 盒尺寸。完整属性集（含 `border-*`、`outline-*`、`transition-*`、`overflow`、`gap`、`letter-spacing`、`box-shadow`）在 [raw/summary.json](raw/summary.json) 的 `pages[].inventory[].style`；除下表的 7 个状态外，空/加载/首次失败/陈旧失败/运行失败/闸门被拒/基线目录浏览器也都在 raw 数据里，未逐行复制到本文件。

### 1280×1000

#### 全局框架（所有页面共用，样本取 S0 页）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| body | `body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(244, 246, 245)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1280×1000 |
| 顶栏 header | `header` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 0px/28px | 0px/0px | 1280×72 |
| 顶栏品牌 .brand | `.brand` | 21px / 34.65px / 750 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 185×34.64 |
| 顶栏环境胶囊 #hdrEnv | `#hdrEnv` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 75.55×28 |
| 顶栏地址胶囊 #hdrAddr | `#hdrAddr` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 0×0 |
| 顶栏健康胶囊 #hdrHealth | `#hdrHealth` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 149.28×28 |
| 旧版入口 #lnkLegacy | `#lnkLegacy` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/8px | 0px/0px | 92.7×30 |
| 跳过导航 .skip-link | `.skip-link` | 14px / 23.1px / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 0px `rgb(255, 255, 255)` · 8px | 10px/18px | 0px/0px | 106×43.09 |
| 左栏 aside#sidebar | `aside#sidebar` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgb(25, 46, 40)` | 0px `rgb(225, 234, 228)` · 0px | 0px/0px | 0px/0px | 224×928 |
| 左栏入口 #btnS0 | `#btnS0` | 13px / 21.45px / 550 | `rgb(225, 234, 228)` / `rgba(255, 255, 255, 0.024)` | 1px `rgba(255, 255, 255, 0.09)` · 7px | 10px/10px | 0px/0px | 188×64 |
| 新建运行 #btnNew | `#btnNew` | 13px / 21.45px / 650 | `rgb(35, 75, 52)` / `rgb(217, 236, 222)` | 1px `rgb(217, 236, 222)` · 7px | 0px/17px | 0px/0px | 188×40 |
| 导航 tab 选中 #segS0.on | `#segS0` | 13px / 21.45px / 450 | `rgb(243, 250, 245)` / `rgb(48, 75, 61)` | 0px `rgb(243, 250, 245)` · 7px | 0px/14px | 0px/0px | 196×44 |
| 导航 tab 未选 #segSetup | `#segSetup` | 13px / 21.45px / 450 | `rgb(178, 197, 185)` / `rgba(0, 0, 0, 0)` | 0px `rgb(178, 197, 185)` · 7px | 0px/14px | 0px/0px | 196×44 |
| 左栏分组标签 .rail-label | `.rail-label` | 11px / 18.15px / 400 | `rgb(165, 185, 174)` / `rgba(0, 0, 0, 0)` | 0px `rgb(165, 185, 174)` · 0px | 20px/28px | 0px/0px | 224×47.14 |
| 运行记录项 .run-item | `.run-item` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 12px/10px | 4px/0px | 196×66.94 |
| 运行记录项选中 .run-item.active | `.run-item.active` | — | — | — | — | — | **选择器未命中**（s0） |
| 页标题 #pageTitle | `#pageTitle` | 27px / 37.8px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 299.02×37.8 |
| 面包屑 .page-breadcrumb | `.page-breadcrumb` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×18.14 |
| 页副标题 #pageSub | `#pageSub` | 13px / 21.45px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×21.44 |
| 页编号 .page-edition | `.page-edition` | 8px / 13.2px / 400 | `rgb(123, 139, 129)` / `rgba(0, 0, 0, 0)` | 0px `rgb(123, 139, 129)` · 0px | 0px/0px | 8px/0px | 193×28 |
| 卡片 .card | `.card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 524.17×787.64 |
| 卡片头 .card-head | `.card-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 18px/22px | 0px/0px | 522.17×62 |
| 卡片标题 .card-head h2 | `.card-head h2` | 15px / 24.75px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 88.81×24.75 |
| 卡片副标题 .card-head .sub | `.card-head .sub` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/315.594px | 24.77×19.8 |
| 卡片体 .card-body | `.card-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 522.17×723.64 |
| 页脚 .workspace-footer | `.workspace-footer` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 20px/0px | 24px/0px | 1000×43.14 |
| 等宽文本 .mono | `.mono` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 0×0 |

#### s0（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| S0 hero .s0-hero | `#viewS0 .s0-hero` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(234, 241, 231)` | 1px `rgb(220, 230, 215)` · 12px | 26px/26px | 0px/0px | 1000×252.03 |
| S0 hero 标题 h2 | `#viewS0 .s0-hero h2` | 27px / 40.5px / 550 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 12px/0px | 335.86×81 |
| S0 hero 正文 p | `#viewS0 .s0-hero p` | 12px / 21.6px / 400 | `rgb(89, 112, 91)` / `rgba(0, 0, 0, 0)` | 0px `rgb(89, 112, 91)` · 0px | 0px/0px | 0px/0px | 335.86×21.59 |
| S0 hero 标签 .hero-tags span | `#viewS0 .hero-tags span` | 11px / 18.15px / 400 | `rgb(82, 110, 83)` / `rgba(0, 0, 0, 0)` | 0px `rgb(82, 110, 83)` · 4px | 0px/0px | 0px/0px | 57.52×18.14 |
| S0 示意 .hero-diagram | `#viewS0 .hero-diagram` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 10px/8px | 0px/0px | 378.39×198.03 |
| S0 阶段卡 .phase-card | `#viewS0 .phase-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/16px | 0px/0px | 490×102.78 |
| S0 阶段序号 .phase-index | `#viewS0 .phase-index` | 16px / normal / 400 | `rgb(106, 133, 94)` / `rgb(240, 244, 237)` | 0px `rgb(106, 133, 94)` · 8px | 0px/0px | 0px/0px | 36×39 |
| S0 阶段 chip 警告 | `#s0PhaseB .chip` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| S0 卡片序号 .section-index | `#viewS0 .section-index` | 12px / normal / 400 | `rgb(105, 133, 99)` / `rgb(248, 250, 246)` | 1px `rgb(220, 231, 218)` · 6px | 0px/0px | 0px/0px | 25×25 |
| S0 表单标签 .s0-label | `#s0Form .s0-label` | 13px / 21.45px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 17px/0px | 478.17×21.44 |
| S0 输入框 #s0Baseline | `#s0Baseline` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 478.17×43 |
| S0 边界说明 .s0-boundary | `#viewS0 .s0-boundary` | 12px / 21.6px / 400 | `rgb(93, 119, 86)` / `rgb(242, 247, 239)` | 1px `rgb(225, 234, 219)` · 6px | 13px/14px | 17px/0px | 478.17×71.19 |
| S0 主按钮 #s0Prepare | `#s0Prepare` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/19px | 0px/0px | 478.17×42 |
| S0 检查项 .s0-checks li | `#s0Checks li` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 15px/0px | 0px/0px | 409.81×75.23 |
| S0 准出状态 #s0Readiness | `#s0Readiness` | 12px / 19.8px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(237, 223, 197)` · 6px | 11px/13px | 0px/0px | 409.81×43.8 |
| S0 阻断区 .s0-blockers | `#viewS0 .s0-blockers` | 14px / 23.1px / 400 | `rgb(140, 114, 76)` / `rgb(255, 250, 240)` | 1px `rgb(235, 223, 198)` · 10px | 22px/22px | 0px/0px | 455.81×165.53 |
| S0 范围说明 .s0-scope | `#viewS0 .s0-scope` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 6px/0px | 0px/0px | 1000×41.59 |
| S0 历史卡 .s0-history | `#viewS0 .s0-history` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 524.17×59.44 |

#### setup（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 配置步骤卡 .step-card | `#viewSetup .step-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(225, 232, 228)` · 9px | 22px/22px | 0px/0px | 954×170.94 |
| 步骤序号 .step-no | `#viewSetup .step-no` | 14px / normal / 400 | `rgb(98, 131, 76)` / `rgb(237, 243, 232)` | 1px `rgb(218, 229, 210)` · 7px | 0px/0px | 0px/0px | 30×32 |
| 步骤标题 .step-title | `#viewSetup .step-title` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 860×26.14 |
| 基线 select #setupBaseline | `#setupBaseline` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 460×42 |
| 基线 chip #setupBaselineChip | `#setupBaselineChip` | 11px / 18.15px / 640 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 89.22×26.14 |
| 浏览按钮 #btnBaselineBrowse | `#btnBaselineBrowse` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 69.02×38 |
| 项目输入 #setupProject | `#setupProject` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 718.97×42 |
| 校验按钮 #setupCheck | `#setupCheck` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 56.02×38 |
| 字段说明 .field-meta | `#setupProjectMeta` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 12px/0px | 860×27.8 |
| chips 容器 .chips | `#viewSetup .chips` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 8px/0px | 860×26.14 |
| chip 普通 | `#viewSetup .chips .chip` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 186.72×26.14 |
| chip 警告 | `#viewSetup .chips .chip.warn` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 128×26.14 |
| 模式 select #setupMode | `#setupMode` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 385.98×42 |
| 选项字段标签 .field-label | `#viewSetup .field-label` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 26.02×19.8 |
| 真实运行告警 #realWarn | `#realWarn` | 13px / 21.45px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(234, 215, 183)` · 8px | 12px/15px | 10px/0px | 0×0 |
| 高级折叠 summary | `#viewSetup details.adv summary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 4px/0px | 0px/0px | 860×28.63 |
| 确认条 .confirm-bar | `#viewSetup .confirm-bar` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(247, 250, 245)` | 1px `rgb(225, 232, 228)` · 0px 0px 12px 12px | 20px/22px | 0px/0px | 998×83 |
| 确认启动 #btnStart | `#btnStart` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/24px | 0px/0px | 115.02×42 |
| 确认条提示 #btnStartHint | `#btnStartHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 120.02×19.8 |
| health 卡 #healthBody | `#healthBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 487×333.48 |
| 操作边界 kv .kv | `#viewSetup .kv` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 9px/0px | 0px/0px | 443×40.44 |
| 脚注 .foot-note | `#viewSetup .foot-note` | 12px / 21.6px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 0px `rgb(113, 130, 123)` · 0px | 0px/0px | 10px/0px | 860×21.59 |

#### run（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 运行头 .run-head | `#runHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1000×64 |
| 运行状态胶囊 .status-pill | `#runHead .status-pill` | 11px / 18.15px / 600 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 6px | 0px/10px | 0px/0px | 110.72×26 |
| 运行元信息 .run-meta | `#runHead .run-meta` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 106.77×19.8 |
| 刷新按钮 #runHead .btn | `#runHead .btn` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 四段容器 .stages | `#stages` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 998×418.13 |
| 阶段卡 .stage | `#stages .stage` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(243, 209, 158)` · 8px | 0px/0px | 0px/0px | 954×150.42 |
| 阶段头 .stage-head | `#stages .stage-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 952×67.23 |
| 阶段序号 .stage-idx | `#stages .stage-idx` | 12px / normal / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 7px | 0px/0px | 0px/0px | 27×27 |
| 阶段名 .stage-name | `#stages .stage-name` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 33.13×23.09 |
| 阶段进度 .stage-bar | `#stages .stage-bar` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(234, 240, 233)` | 0px `rgb(97, 116, 108)` · 999px | 0px/0px | 0px/0px | 90×5 |
| 阶段汇总 .stage-sum | `#stages .stage-sum` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/668.328px | 167.55×19.8 |
| 阶段展开体 .stage-body | `#stages .stage.open .stage-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 247)` | 1px `rgb(225, 232, 228)` · 0px | 16px/16px | 0px/0px | 952×81.19 |
| 节点 chip .snode | `#stages .snode` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 7px | 9px/10px | 0px/0px | 112×48.19 |
| 节点标记 .snode .sb | `#stages .snode .sb` | 10.5px / 17.325px / 700 | `rgb(113, 130, 123)` / `rgb(238, 241, 245)` | 1px `rgb(199, 212, 204)` · 50% | 0px/0px | 0px/0px | 20×20 |
| Agent 容器 #agents | `#agents` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 444×1049.52 |
| Agent 卡 .agent | `#agents .agent` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 17px/17px | 0px/0px | 444×198.7 |
| Agent 名称 .agent-name | `#agents .agent-name` | 13px / 19.5px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 113.7×19.5 |
| Agent 角色 .agent-role | `#agents .agent-role` | 11px / 17.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 277.25×17.59 |
| Agent 正文 .agent-body | `#agents .agent-body` | 13px / 22.1px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 408×68.88 |
| Agent 动作 .agent-action | `#agents .agent-action` | 12px / 20.4px / 400 | `rgb(21, 119, 94)` / `rgba(0, 0, 0, 0)` | 0px `rgb(21, 119, 94)` · 0px | 0px/0px | 0px/0px | 408×20.39 |
| Agent 卡脚 .agent-foot | `#agents .agent-foot` | 11px / 18.15px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 10px/0px | 0px/0px | 408×29.14 |
| Host 行 .host-row | `#hostRow` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(246, 249, 244)` | 1px `rgb(224, 233, 219)` · 9px | 14px/14px | 14px/0px | 444×89.39 |
| 闸门卡 #gateCard | `#gateCard` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 253, 247)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 490×711.52 |
| 计数容器 .counts | `#countsBody .counts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 444×99.48 |
| 计数框 .count-box | `#countsBody .count-box` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(250, 252, 248)` | 1px `rgb(224, 232, 219)` · 9px | 17px/17px | 0px/0px | 217×99.48 |
| 计数数字 .count-box .n | `#countsBody .count-box .n` | 29px / 37.7px / 600 | `rgb(179, 65, 64)` / `rgba(0, 0, 0, 0)` | 0px `rgb(179, 65, 64)` · 0px | 0px/0px | 0px/0px | 181×37.69 |
| 阻断项 .blocker | `#blockersBody .blocker` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 12px/0px | 0px/0px | 444×66.88 |
| 严重度标记 .sev | `#blockersBody .sev` | 10px / 16.5px / 700 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 0px `rgb(179, 65, 64)` · 4px | 3px/6px | 0px/0px | 49.06×22.5 |
| 长任务区 #jobBody | `#jobBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 488×63.8 |
| 事件折叠 summary | `#eventsSummary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 12px/18px | 0px/0px | 488×45.63 |
| 事件列表 .ev-list | `#eventList` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/18px | 0px/0px | 488×41.8 |
| 空态卡 #runEmpty | `#runEmpty` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 65px/25px | 0px/0px | 0×0 |

#### gate（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 闸门运行头 #gateHead | `#gateHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1000×102.14 |
| 闸门告警区 #gateAlerts | `#gateAlerts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1000×0 |
| 闸门四段 .stages | `#stagesGate` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 998×418.13 |
| 闸门材料区 #gateMaterial | `#gateMaterial` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 488×754.69 |
| 差异清单项 .diff-item | `#gateMaterial .diff-item` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 444×127.58 |
| 差异未决项 .diff-item.unresolved | `#gateMaterial .diff-item.unresolved` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 444×127.58 |
| 闸门操作区 #gatePanel | `#gatePanel` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 488×454.14 |
| 决策选项 .option | `#gatePanel .option` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 8px | 14px/14px | 0px/0px | 444×74.53 |
| 决策选项单选 .radio | `#gatePanel .option .radio` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 2px `rgb(199, 212, 204)` · 50% | 0px/0px | 2px/0px | 15×15 |
| actor 输入 | `#gatePanel [aria-label=actor]` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 220×42 |
| 理由输入 | `#gatePanel [aria-label='裁决理由']` | 14px / 23.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 8px/0px | 444×95.39 |
| 提交按钮 [data-gate-submit] | `#gatePanel [data-gate-submit]` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 10px/0px | 444×38 |
| 闸门错误区 .gate-error | `#gatePanel .gate-error` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 10px/0px | 444×0 |

#### dirpicker-project（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 目录选择器 #dirPicker | `#dirPicker` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 9px | 0px/0px | 10px/0px | 860×316.38 |
| 目录头 .dp-head | `#dirPicker .dp-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 0px `rgb(33, 56, 49)` · 0px | 13px/15px | 0px/0px | 858×57 |
| 上级按钮 #btnDirUp | `#btnDirUp` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 面包屑 .dp-crumb | `#dirCrumb` | 11.5px / 18.975px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 705.28×18.97 |
| 收起按钮 #btnDirClose | `#btnDirClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 根列表 .dp-roots | `#dirRoots` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(251, 252, 254)` | 0px `rgb(33, 56, 49)` · 0px | 7px/10px | 0px/0px | 858×45 |
| 目录列表 .dp-list | `#dirList` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 858×155.38 |
| 目录项 .dp-item | `#dirList .dp-item` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 858×53.14 |
| 目录项名 .dp-item b | `#dirList .dp-item b` | 12.5px / 20.625px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 301.91×20.63 |
| 目录脚 .dp-foot | `#dirPicker .dp-foot` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 1px `rgb(225, 232, 228)` · 0px | 13px/15px | 0px/0px | 858×57 |
| 选择此目录 #btnDirChoose | `#btnDirChoose` | 12.5px / 20.625px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/12px | 0px/0px | 88.52×30 |
| 目录提示 #dirHint | `#dirHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 289.36×19.8 |

#### agent（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| Agent 窗口 dialog | `#agentWindow` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 200)` · 14px | 0px/0px | 33.9062px/32px | 1216×932.17 |
| 窗口头 .aw-head | `#agentWindow .aw-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(245, 248, 241)` | 0px `rgb(33, 56, 49)` · 0px | 22px/28px | 0px/0px | 1214×99.14 |
| 窗口标题 h2 | `#awTitle` | 21px / 34.65px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 962.3×34.64 |
| 窗口状态 chip #awStatus | `#awStatus` | 11px / 18.15px / 400 | `rgb(21, 119, 94)` / `rgb(234, 245, 239)` | 1px `rgb(184, 218, 202)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| 关闭按钮 #awClose | `#awClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 工具条 .aw-toolbar | `#agentWindow .aw-toolbar` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 13px/28px | 0px/0px | 1214×61 |
| 身份 #awIdentity | `#awIdentity` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 171.64×18.14 |
| 节点 select #awNode | `#awNode` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 52×34 |
| 尝试 select #awAttempt | `#awAttempt` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 130×34 |
| 刷新 #awRefresh | `#awRefresh` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 观察区 .aw-observe | `#agentWindow .aw-observe` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 25px/28px | 0px/0px | 747.06×770.03 |
| 干预区 .aw-intervene | `#agentWindow .aw-intervene` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(248, 250, 245)` | 0px `rgb(33, 56, 49)` · 0px | 25px/25px | 0px/0px | 466.94×770.03 |
| 区块标题 .aw-section-head h3 | `#agentWindow .aw-section-head h3` | 15px / 24.75px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 60.02×24.75 |
| 能力事实 #awCapabilities | `#awCapabilities` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 691.06×22.8 |
| 详情折叠 summary | `#agentWindow .aw-detail summary` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 246)` | 0px `rgb(33, 56, 49)` · 0px | 15px/15px | 0px/0px | 689.06×51.44 |
| 时间线 .aw-timeline | `#awTimeline` | 14px / 23.1px / 400 | `rgb(217, 232, 212)` / `rgb(32, 54, 42)` | 1px `rgb(52, 83, 60)` · 9px | 17px/17px | 0px/0px | 691.06×170 |
| 输入补全 #awMessage | `#awMessage` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 0px/0px | 415.94×164.34 |
| 操作者 #awActor | `#awActor` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 415.94×42 |
| 补充指令按钮 #awSteer | `#awSteer` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 0px/0px | 415.94×40 |
| 暂停/恢复按钮 #awPause | `#awPause` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 203.47×40 |
| 终止按钮 #awTerminate | `#awTerminate` | 13px / 21.45px / 550 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 1px `rgb(231, 196, 191)` · 7px | 0px/14px | 0px/0px | 415.94×40 |
| 只读说明 .aw-note | `#agentWindow .aw-note` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 691.06×22.8 |
| 动作行 .aw-action-row | `#agentWindow .aw-action-row` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 9px/0px | 415.94×40 |

#### legacy（1280×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 旧页返回入口 .back-workspace | `.back-workspace` | 12px / 20.4px / 400 | `rgb(193, 220, 189)` / `rgba(0, 0, 0, 0)` | 1px `rgb(107, 131, 106)` · 6px | 5px/10px | 0px/0px | 161.36×32.39 |
| 旧页权威说明 .authority | `.authority` | 13px / 22.1px / 400 | `rgb(226, 235, 225)` / `rgb(237, 243, 232)` | 1px `rgb(212, 224, 204)` · 0px | 12px/28px | 0px/0px | 1280×45.39 |
| 旧页面板 .panel | `.panel` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 20px/20px | 4px/0px | 1224×62.39 |
| 旧页面板标题 h2 | `.panel>h2` | 15px / 25.5px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(225, 232, 228)` · 0px | 0px/0px | 0px/0px | 298×39.5 |
| 旧页状态条 .status-strip | `.status-strip` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 15px/19px | 0px/0px | 1224×141.73 |
| 旧页按钮 .btn | `.btn` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页主按钮 .btn-primary | `.btn-primary` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页输入框 input[type=text] | `input[type=text]` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 285×40.8 |
| 旧页 textarea | `textarea` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 820×82.39 |
| 旧页 select | `select` | 13px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 285×41 |
| 旧页折叠 summary | `details>summary` | 12px / 20.4px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 1182×20.39 |
| 旧页日志 .logtail | `pre.logtail` | 12px / 21.6px / 400 | `rgb(220, 232, 215)` / `rgb(32, 56, 43)` | 1px `rgb(52, 83, 60)` · 7px | 12px/12px | 5px/0px | 0×0 |
| 旧页 JSON pre | `pre.json` | 12px / 20.4px / 400 | `rgb(80, 105, 75)` / `rgb(247, 250, 243)` | 1px `rgb(225, 232, 228)` · 7px | 12px/12px | 5px/0px | 820×220 |
| 旧页徽章 .badge | `.badge` | 11.5px / 19.55px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(231, 213, 180)` · 5px | 3px/7px | 0px/0px | 47.23×27.55 |
| 旧页 chip | `.chip` | — | — | — | — | — | **选择器未命中**（legacy） |

### 1440×1000

#### 全局框架（所有页面共用，样本取 S0 页）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| body | `body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(244, 246, 245)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1440×1000 |
| 顶栏 header | `header` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 0px/28px | 0px/0px | 1440×72 |
| 顶栏品牌 .brand | `.brand` | 21px / 34.65px / 750 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 205×34.64 |
| 顶栏环境胶囊 #hdrEnv | `#hdrEnv` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 75.55×28 |
| 顶栏地址胶囊 #hdrAddr | `#hdrAddr` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 128.03×28 |
| 顶栏健康胶囊 #hdrHealth | `#hdrHealth` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 149.28×28 |
| 旧版入口 #lnkLegacy | `#lnkLegacy` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/8px | 0px/0px | 92.7×30 |
| 跳过导航 .skip-link | `.skip-link` | 14px / 23.1px / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 0px `rgb(255, 255, 255)` · 8px | 10px/18px | 0px/0px | 106×43.09 |
| 左栏 aside#sidebar | `aside#sidebar` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgb(25, 46, 40)` | 0px `rgb(225, 234, 228)` · 0px | 0px/0px | 0px/0px | 244×928 |
| 左栏入口 #btnS0 | `#btnS0` | 13px / 21.45px / 550 | `rgb(225, 234, 228)` / `rgba(255, 255, 255, 0.024)` | 1px `rgba(255, 255, 255, 0.09)` · 7px | 10px/10px | 0px/0px | 208×64 |
| 新建运行 #btnNew | `#btnNew` | 13px / 21.45px / 650 | `rgb(35, 75, 52)` / `rgb(217, 236, 222)` | 1px `rgb(217, 236, 222)` · 7px | 0px/17px | 0px/0px | 208×40 |
| 导航 tab 选中 #segS0.on | `#segS0` | 13px / 21.45px / 450 | `rgb(243, 250, 245)` / `rgb(48, 75, 61)` | 0px `rgb(243, 250, 245)` · 7px | 0px/14px | 0px/0px | 216×44 |
| 导航 tab 未选 #segSetup | `#segSetup` | 13px / 21.45px / 450 | `rgb(178, 197, 185)` / `rgba(0, 0, 0, 0)` | 0px `rgb(178, 197, 185)` · 7px | 0px/14px | 0px/0px | 216×44 |
| 左栏分组标签 .rail-label | `.rail-label` | 11px / 18.15px / 400 | `rgb(165, 185, 174)` / `rgba(0, 0, 0, 0)` | 0px `rgb(165, 185, 174)` · 0px | 20px/28px | 0px/0px | 244×47.14 |
| 运行记录项 .run-item | `.run-item` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 12px/10px | 4px/0px | 216×66.94 |
| 运行记录项选中 .run-item.active | `.run-item.active` | — | — | — | — | — | **选择器未命中**（s0） |
| 页标题 #pageTitle | `#pageTitle` | 27px / 37.8px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 299.02×37.8 |
| 面包屑 .page-breadcrumb | `.page-breadcrumb` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×18.14 |
| 页副标题 #pageSub | `#pageSub` | 13px / 21.45px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×21.44 |
| 页编号 .page-edition | `.page-edition` | 9px / 14.85px / 400 | `rgb(123, 139, 129)` / `rgba(0, 0, 0, 0)` | 0px `rgb(123, 139, 129)` · 0px | 0px/0px | 8px/0px | 213.33×28 |
| 卡片 .card | `.card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 588.36×787.64 |
| 卡片头 .card-head | `.card-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 18px/22px | 0px/0px | 586.36×62 |
| 卡片标题 .card-head h2 | `.card-head h2` | 15px / 24.75px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 88.81×24.75 |
| 卡片副标题 .card-head .sub | `.card-head .sub` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/379.781px | 24.77×19.8 |
| 卡片体 .card-body | `.card-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 586.36×723.64 |
| 页脚 .workspace-footer | `.workspace-footer` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 20px/0px | 24px/0px | 1124×43.14 |
| 等宽文本 .mono | `.mono` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 128.03×28 |

#### s0（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| S0 hero .s0-hero | `#viewS0 .s0-hero` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(234, 241, 231)` | 1px `rgb(220, 230, 215)` · 12px | 29px/32px | 0px/0px | 1124×265.03 |
| S0 hero 标题 h2 | `#viewS0 .s0-hero h2` | 29px / 43.5px / 550 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 12px/0px | 335.86×87 |
| S0 hero 正文 p | `#viewS0 .s0-hero p` | 12px / 21.6px / 400 | `rgb(89, 112, 91)` / `rgba(0, 0, 0, 0)` | 0px `rgb(89, 112, 91)` · 0px | 0px/0px | 0px/0px | 335.86×21.59 |
| S0 hero 标签 .hero-tags span | `#viewS0 .hero-tags span` | 11px / 18.15px / 400 | `rgb(82, 110, 83)` / `rgba(0, 0, 0, 0)` | 0px `rgb(82, 110, 83)` · 4px | 0px/0px | 0px/0px | 57.52×18.14 |
| S0 示意 .hero-diagram | `#viewS0 .hero-diagram` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 10px/20px | 0px/0px | 400×205.03 |
| S0 阶段卡 .phase-card | `#viewS0 .phase-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 18px/20px | 0px/0px | 552×106.78 |
| S0 阶段序号 .phase-index | `#viewS0 .phase-index` | 16px / normal / 400 | `rgb(106, 133, 94)` / `rgb(240, 244, 237)` | 0px `rgb(106, 133, 94)` · 8px | 0px/0px | 0px/0px | 36×39 |
| S0 阶段 chip 警告 | `#s0PhaseB .chip` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| S0 卡片序号 .section-index | `#viewS0 .section-index` | 12px / normal / 400 | `rgb(105, 133, 99)` / `rgb(248, 250, 246)` | 1px `rgb(220, 231, 218)` · 6px | 0px/0px | 0px/0px | 25×25 |
| S0 表单标签 .s0-label | `#s0Form .s0-label` | 13px / 21.45px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 17px/0px | 542.36×21.44 |
| S0 输入框 #s0Baseline | `#s0Baseline` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 542.36×43 |
| S0 边界说明 .s0-boundary | `#viewS0 .s0-boundary` | 12px / 21.6px / 400 | `rgb(93, 119, 86)` / `rgb(242, 247, 239)` | 1px `rgb(225, 234, 219)` · 6px | 13px/14px | 17px/0px | 542.36×71.19 |
| S0 主按钮 #s0Prepare | `#s0Prepare` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/19px | 0px/0px | 542.36×42 |
| S0 检查项 .s0-checks li | `#s0Checks li` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 15px/0px | 0px/0px | 465.63×75.23 |
| S0 准出状态 #s0Readiness | `#s0Readiness` | 12px / 19.8px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(237, 223, 197)` · 6px | 11px/13px | 0px/0px | 465.63×43.8 |
| S0 阻断区 .s0-blockers | `#viewS0 .s0-blockers` | 14px / 23.1px / 400 | `rgb(140, 114, 76)` / `rgb(255, 250, 240)` | 1px `rgb(235, 223, 198)` · 10px | 22px/22px | 0px/0px | 511.63×165.53 |
| S0 范围说明 .s0-scope | `#viewS0 .s0-scope` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 6px/0px | 0px/0px | 1124×41.59 |
| S0 历史卡 .s0-history | `#viewS0 .s0-history` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 588.36×59.44 |

#### setup（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 配置步骤卡 .step-card | `#viewSetup .step-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(225, 232, 228)` · 9px | 22px/22px | 0px/0px | 1078×170.94 |
| 步骤序号 .step-no | `#viewSetup .step-no` | 14px / normal / 400 | `rgb(98, 131, 76)` / `rgb(237, 243, 232)` | 1px `rgb(218, 229, 210)` · 7px | 0px/0px | 0px/0px | 30×32 |
| 步骤标题 .step-title | `#viewSetup .step-title` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 984×26.14 |
| 基线 select #setupBaseline | `#setupBaseline` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 460×42 |
| 基线 chip #setupBaselineChip | `#setupBaselineChip` | 11px / 18.15px / 640 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 89.22×26.14 |
| 浏览按钮 #btnBaselineBrowse | `#btnBaselineBrowse` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 69.02×38 |
| 项目输入 #setupProject | `#setupProject` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 842.97×42 |
| 校验按钮 #setupCheck | `#setupCheck` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 56.02×38 |
| 字段说明 .field-meta | `#setupProjectMeta` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 12px/0px | 984×27.8 |
| chips 容器 .chips | `#viewSetup .chips` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 8px/0px | 984×26.14 |
| chip 普通 | `#viewSetup .chips .chip` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 186.72×26.14 |
| chip 警告 | `#viewSetup .chips .chip.warn` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 128×26.14 |
| 模式 select #setupMode | `#setupMode` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 447.98×42 |
| 选项字段标签 .field-label | `#viewSetup .field-label` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 26.02×19.8 |
| 真实运行告警 #realWarn | `#realWarn` | 13px / 21.45px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(234, 215, 183)` · 8px | 12px/15px | 10px/0px | 0×0 |
| 高级折叠 summary | `#viewSetup details.adv summary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 4px/0px | 0px/0px | 984×28.63 |
| 确认条 .confirm-bar | `#viewSetup .confirm-bar` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(247, 250, 245)` | 1px `rgb(225, 232, 228)` · 0px 0px 12px 12px | 20px/22px | 0px/0px | 1122×83 |
| 确认启动 #btnStart | `#btnStart` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/24px | 0px/0px | 115.02×42 |
| 确认条提示 #btnStartHint | `#btnStartHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 120.02×19.8 |
| health 卡 #healthBody | `#healthBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 549×333.48 |
| 操作边界 kv .kv | `#viewSetup .kv` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 9px/0px | 0px/0px | 505×40.44 |
| 脚注 .foot-note | `#viewSetup .foot-note` | 12px / 21.6px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 0px `rgb(113, 130, 123)` · 0px | 0px/0px | 10px/0px | 984×21.59 |

#### run（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 运行头 .run-head | `#runHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1124×64 |
| 运行状态胶囊 .status-pill | `#runHead .status-pill` | 11px / 18.15px / 600 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 6px | 0px/10px | 0px/0px | 110.72×26 |
| 运行元信息 .run-meta | `#runHead .run-meta` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 106.77×19.8 |
| 刷新按钮 #runHead .btn | `#runHead .btn` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 四段容器 .stages | `#stages` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 1122×418.13 |
| 阶段卡 .stage | `#stages .stage` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(243, 209, 158)` · 8px | 0px/0px | 0px/0px | 1078×150.42 |
| 阶段头 .stage-head | `#stages .stage-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 1076×67.23 |
| 阶段序号 .stage-idx | `#stages .stage-idx` | 12px / normal / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 7px | 0px/0px | 0px/0px | 27×27 |
| 阶段名 .stage-name | `#stages .stage-name` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 33.13×23.09 |
| 阶段进度 .stage-bar | `#stages .stage-bar` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(234, 240, 233)` | 0px `rgb(97, 116, 108)` · 999px | 0px/0px | 0px/0px | 90×5 |
| 阶段汇总 .stage-sum | `#stages .stage-sum` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/792.328px | 167.55×19.8 |
| 阶段展开体 .stage-body | `#stages .stage.open .stage-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 247)` | 1px `rgb(225, 232, 228)` · 0px | 16px/16px | 0px/0px | 1076×81.19 |
| 节点 chip .snode | `#stages .snode` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 7px | 9px/10px | 0px/0px | 112×48.19 |
| 节点标记 .snode .sb | `#stages .snode .sb` | 10.5px / 17.325px / 700 | `rgb(113, 130, 123)` / `rgb(238, 241, 245)` | 1px `rgb(199, 212, 204)` · 50% | 0px/0px | 0px/0px | 20×20 |
| Agent 容器 #agents | `#agents` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 605.02×707.38 |
| Agent 卡 .agent | `#agents .agent` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 17px/17px | 0px/0px | 295.5×241.19 |
| Agent 名称 .agent-name | `#agents .agent-name` | 13px / 19.5px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 113.7×19.5 |
| Agent 角色 .agent-role | `#agents .agent-role` | 11px / 17.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 128.75×17.59 |
| Agent 正文 .agent-body | `#agents .agent-body` | 13px / 22.1px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 259.5×111.36 |
| Agent 动作 .agent-action | `#agents .agent-action` | 12px / 20.4px / 400 | `rgb(21, 119, 94)` / `rgba(0, 0, 0, 0)` | 0px `rgb(21, 119, 94)` · 0px | 0px/0px | 0px/0px | 259.5×20.39 |
| Agent 卡脚 .agent-foot | `#agents .agent-foot` | 11px / 18.15px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 10px/0px | 0px/0px | 259.5×29.14 |
| Host 行 .host-row | `#hostRow` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(246, 249, 244)` | 1px `rgb(224, 233, 219)` · 9px | 14px/14px | 14px/0px | 605.02×69.59 |
| 闸门卡 #gateCard | `#gateCard` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 253, 247)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 448.98×711.52 |
| 计数容器 .counts | `#countsBody .counts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 402.98×99.48 |
| 计数框 .count-box | `#countsBody .count-box` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(250, 252, 248)` | 1px `rgb(224, 232, 219)` · 9px | 17px/17px | 0px/0px | 196.48×99.48 |
| 计数数字 .count-box .n | `#countsBody .count-box .n` | 29px / 37.7px / 600 | `rgb(179, 65, 64)` / `rgba(0, 0, 0, 0)` | 0px `rgb(179, 65, 64)` · 0px | 0px/0px | 0px/0px | 160.48×37.69 |
| 阻断项 .blocker | `#blockersBody .blocker` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 12px/0px | 0px/0px | 402.98×66.88 |
| 严重度标记 .sev | `#blockersBody .sev` | 10px / 16.5px / 700 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 0px `rgb(179, 65, 64)` · 4px | 3px/6px | 0px/0px | 49.06×22.5 |
| 长任务区 #jobBody | `#jobBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 446.98×63.8 |
| 事件折叠 summary | `#eventsSummary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 12px/18px | 0px/0px | 446.98×45.63 |
| 事件列表 .ev-list | `#eventList` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/18px | 0px/0px | 446.98×41.8 |
| 空态卡 #runEmpty | `#runEmpty` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 65px/25px | 0px/0px | 0×0 |

#### gate（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 闸门运行头 #gateHead | `#gateHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1124×102.14 |
| 闸门告警区 #gateAlerts | `#gateAlerts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1124×0 |
| 闸门四段 .stages | `#stagesGate` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 1122×418.13 |
| 闸门材料区 #gateMaterial | `#gateMaterial` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 649.02×754.69 |
| 差异清单项 .diff-item | `#gateMaterial .diff-item` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 605.02×127.58 |
| 差异未决项 .diff-item.unresolved | `#gateMaterial .diff-item.unresolved` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 605.02×127.58 |
| 闸门操作区 #gatePanel | `#gatePanel` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 446.98×454.14 |
| 决策选项 .option | `#gatePanel .option` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 8px | 14px/14px | 0px/0px | 402.98×74.53 |
| 决策选项单选 .radio | `#gatePanel .option .radio` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 2px `rgb(199, 212, 204)` · 50% | 0px/0px | 2px/0px | 15×15 |
| actor 输入 | `#gatePanel [aria-label=actor]` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 220×42 |
| 理由输入 | `#gatePanel [aria-label='裁决理由']` | 14px / 23.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 8px/0px | 402.98×95.39 |
| 提交按钮 [data-gate-submit] | `#gatePanel [data-gate-submit]` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 10px/0px | 402.98×38 |
| 闸门错误区 .gate-error | `#gatePanel .gate-error` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 10px/0px | 402.98×0 |

#### dirpicker-project（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 目录选择器 #dirPicker | `#dirPicker` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 9px | 0px/0px | 10px/0px | 984×316.38 |
| 目录头 .dp-head | `#dirPicker .dp-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 0px `rgb(33, 56, 49)` · 0px | 13px/15px | 0px/0px | 982×57 |
| 上级按钮 #btnDirUp | `#btnDirUp` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 面包屑 .dp-crumb | `#dirCrumb` | 11.5px / 18.975px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 829.28×18.97 |
| 收起按钮 #btnDirClose | `#btnDirClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 根列表 .dp-roots | `#dirRoots` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(251, 252, 254)` | 0px `rgb(33, 56, 49)` · 0px | 7px/10px | 0px/0px | 982×45 |
| 目录列表 .dp-list | `#dirList` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 982×155.38 |
| 目录项 .dp-item | `#dirList .dp-item` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 982×53.14 |
| 目录项名 .dp-item b | `#dirList .dp-item b` | 12.5px / 20.625px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 301.91×20.63 |
| 目录脚 .dp-foot | `#dirPicker .dp-foot` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 1px `rgb(225, 232, 228)` · 0px | 13px/15px | 0px/0px | 982×57 |
| 选择此目录 #btnDirChoose | `#btnDirChoose` | 12.5px / 20.625px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/12px | 0px/0px | 88.52×30 |
| 目录提示 #dirHint | `#dirHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 289.36×19.8 |

#### agent（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| Agent 窗口 dialog | `#agentWindow` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 200)` · 14px | 0px/0px | 33.9062px/110px | 1220×932.17 |
| 窗口头 .aw-head | `#agentWindow .aw-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(245, 248, 241)` | 0px `rgb(33, 56, 49)` · 0px | 22px/28px | 0px/0px | 1218×99.14 |
| 窗口标题 h2 | `#awTitle` | 21px / 34.65px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 966.3×34.64 |
| 窗口状态 chip #awStatus | `#awStatus` | 11px / 18.15px / 400 | `rgb(21, 119, 94)` / `rgb(234, 245, 239)` | 1px `rgb(184, 218, 202)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| 关闭按钮 #awClose | `#awClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 工具条 .aw-toolbar | `#agentWindow .aw-toolbar` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 13px/28px | 0px/0px | 1218×61 |
| 身份 #awIdentity | `#awIdentity` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 171.64×18.14 |
| 节点 select #awNode | `#awNode` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 52×34 |
| 尝试 select #awAttempt | `#awAttempt` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 130×34 |
| 刷新 #awRefresh | `#awRefresh` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 观察区 .aw-observe | `#agentWindow .aw-observe` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 25px/28px | 0px/0px | 749.53×770.03 |
| 干预区 .aw-intervene | `#agentWindow .aw-intervene` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(248, 250, 245)` | 0px `rgb(33, 56, 49)` · 0px | 25px/25px | 0px/0px | 468.47×770.03 |
| 区块标题 .aw-section-head h3 | `#agentWindow .aw-section-head h3` | 15px / 24.75px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 60.02×24.75 |
| 能力事实 #awCapabilities | `#awCapabilities` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 693.53×22.8 |
| 详情折叠 summary | `#agentWindow .aw-detail summary` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 246)` | 0px `rgb(33, 56, 49)` · 0px | 15px/15px | 0px/0px | 691.53×51.44 |
| 时间线 .aw-timeline | `#awTimeline` | 14px / 23.1px / 400 | `rgb(217, 232, 212)` / `rgb(32, 54, 42)` | 1px `rgb(52, 83, 60)` · 9px | 17px/17px | 0px/0px | 693.53×170 |
| 输入补全 #awMessage | `#awMessage` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 0px/0px | 417.47×164.34 |
| 操作者 #awActor | `#awActor` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 417.47×42 |
| 补充指令按钮 #awSteer | `#awSteer` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 0px/0px | 417.47×40 |
| 暂停/恢复按钮 #awPause | `#awPause` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 204.23×40 |
| 终止按钮 #awTerminate | `#awTerminate` | 13px / 21.45px / 550 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 1px `rgb(231, 196, 191)` · 7px | 0px/14px | 0px/0px | 417.47×40 |
| 只读说明 .aw-note | `#agentWindow .aw-note` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 693.53×22.8 |
| 动作行 .aw-action-row | `#agentWindow .aw-action-row` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 9px/0px | 417.47×40 |

#### legacy（1440×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 旧页返回入口 .back-workspace | `.back-workspace` | 12px / 20.4px / 400 | `rgb(193, 220, 189)` / `rgba(0, 0, 0, 0)` | 1px `rgb(107, 131, 106)` · 6px | 5px/10px | 0px/0px | 161.36×32.39 |
| 旧页权威说明 .authority | `.authority` | 13px / 22.1px / 400 | `rgb(226, 235, 225)` / `rgb(237, 243, 232)` | 1px `rgb(212, 224, 204)` · 0px | 12px/28px | 0px/0px | 1440×45.39 |
| 旧页面板 .panel | `.panel` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 20px/20px | 4px/0px | 1384×62.39 |
| 旧页面板标题 h2 | `.panel>h2` | 15px / 25.5px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(225, 232, 228)` · 0px | 0px/0px | 0px/0px | 298×39.5 |
| 旧页状态条 .status-strip | `.status-strip` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 15px/19px | 0px/0px | 1384×114.19 |
| 旧页按钮 .btn | `.btn` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页主按钮 .btn-primary | `.btn-primary` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页输入框 input[type=text] | `input[type=text]` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 325×40.8 |
| 旧页 textarea | `textarea` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 980×82.39 |
| 旧页 select | `select` | 13px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 325×41 |
| 旧页折叠 summary | `details>summary` | 12px / 20.4px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 1342×20.39 |
| 旧页日志 .logtail | `pre.logtail` | 12px / 21.6px / 400 | `rgb(220, 232, 215)` / `rgb(32, 56, 43)` | 1px `rgb(52, 83, 60)` · 7px | 12px/12px | 5px/0px | 0×0 |
| 旧页 JSON pre | `pre.json` | 12px / 20.4px / 400 | `rgb(80, 105, 75)` / `rgb(247, 250, 243)` | 1px `rgb(225, 232, 228)` · 7px | 12px/12px | 5px/0px | 980×220 |
| 旧页徽章 .badge | `.badge` | 11.5px / 19.55px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(231, 213, 180)` · 5px | 3px/7px | 0px/0px | 47.23×27.55 |
| 旧页 chip | `.chip` | — | — | — | — | — | **选择器未命中**（legacy） |

### 1920×1000

#### 全局框架（所有页面共用，样本取 S0 页）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| body | `body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(244, 246, 245)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1920×1000 |
| 顶栏 header | `header` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 0px/28px | 0px/0px | 1920×72 |
| 顶栏品牌 .brand | `.brand` | 21px / 34.65px / 750 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 205×34.64 |
| 顶栏环境胶囊 #hdrEnv | `#hdrEnv` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 75.55×28 |
| 顶栏地址胶囊 #hdrAddr | `#hdrAddr` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 128.03×28 |
| 顶栏健康胶囊 #hdrHealth | `#hdrHealth` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(248, 250, 249)` | 1px `rgb(225, 232, 228)` · 999px | 0px/10px | 0px/0px | 149.28×28 |
| 旧版入口 #lnkLegacy | `#lnkLegacy` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/8px | 0px/0px | 92.7×30 |
| 跳过导航 .skip-link | `.skip-link` | 14px / 23.1px / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 0px `rgb(255, 255, 255)` · 8px | 10px/18px | 0px/0px | 106×43.09 |
| 左栏 aside#sidebar | `aside#sidebar` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgb(25, 46, 40)` | 0px `rgb(225, 234, 228)` · 0px | 0px/0px | 0px/0px | 244×928 |
| 左栏入口 #btnS0 | `#btnS0` | 13px / 21.45px / 550 | `rgb(225, 234, 228)` / `rgba(255, 255, 255, 0.024)` | 1px `rgba(255, 255, 255, 0.09)` · 7px | 10px/10px | 0px/0px | 208×64 |
| 新建运行 #btnNew | `#btnNew` | 13px / 21.45px / 650 | `rgb(35, 75, 52)` / `rgb(217, 236, 222)` | 1px `rgb(217, 236, 222)` · 7px | 0px/17px | 0px/0px | 208×40 |
| 导航 tab 选中 #segS0.on | `#segS0` | 13px / 21.45px / 450 | `rgb(243, 250, 245)` / `rgb(48, 75, 61)` | 0px `rgb(243, 250, 245)` · 7px | 0px/14px | 0px/0px | 216×44 |
| 导航 tab 未选 #segSetup | `#segSetup` | 13px / 21.45px / 450 | `rgb(178, 197, 185)` / `rgba(0, 0, 0, 0)` | 0px `rgb(178, 197, 185)` · 7px | 0px/14px | 0px/0px | 216×44 |
| 左栏分组标签 .rail-label | `.rail-label` | 11px / 18.15px / 400 | `rgb(165, 185, 174)` / `rgba(0, 0, 0, 0)` | 0px `rgb(165, 185, 174)` · 0px | 20px/28px | 0px/0px | 244×47.14 |
| 运行记录项 .run-item | `.run-item` | 14px / 23.1px / 400 | `rgb(225, 234, 228)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 12px/10px | 4px/0px | 216×66.94 |
| 运行记录项选中 .run-item.active | `.run-item.active` | — | — | — | — | — | **选择器未命中**（s0） |
| 页标题 #pageTitle | `#pageTitle` | 27px / 37.8px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 299.02×37.8 |
| 面包屑 .page-breadcrumb | `.page-breadcrumb` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×18.14 |
| 页副标题 #pageSub | `#pageSub` | 13px / 21.45px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 299.02×21.44 |
| 页编号 .page-edition | `.page-edition` | 9px / 14.85px / 400 | `rgb(123, 139, 129)` / `rgba(0, 0, 0, 0)` | 0px `rgb(123, 139, 129)` · 0px | 0px/0px | 8px/0px | 213.33×28 |
| 卡片 .card | `.card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 862.22×755.84 |
| 卡片头 .card-head | `.card-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 18px/22px | 0px/0px | 860.22×62 |
| 卡片标题 .card-head h2 | `.card-head h2` | 15px / 24.75px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 88.81×24.75 |
| 卡片副标题 .card-head .sub | `.card-head .sub` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/653.641px | 24.77×19.8 |
| 卡片体 .card-body | `.card-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 860.22×691.84 |
| 页脚 .workspace-footer | `.workspace-footer` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 20px/0px | 24px/0px | 1580×43.14 |
| 等宽文本 .mono | `.mono` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 999px | 0px/10px | 0px/0px | 128.03×28 |

#### s0（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| S0 hero .s0-hero | `#viewS0 .s0-hero` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(234, 241, 231)` | 1px `rgb(220, 230, 215)` · 12px | 34px/40px | 0px/0px | 1580×275.03 |
| S0 hero 标题 h2 | `#viewS0 .s0-hero h2` | 34px / 51px / 550 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 12px/0px | 391.83×102 |
| S0 hero 正文 p | `#viewS0 .s0-hero p` | 14px / 25.2px / 400 | `rgb(89, 112, 91)` / `rgba(0, 0, 0, 0)` | 0px `rgb(89, 112, 91)` · 0px | 0px/0px | 0px/0px | 391.83×25.19 |
| S0 hero 标签 .hero-tags span | `#viewS0 .hero-tags span` | 11px / 18.15px / 400 | `rgb(82, 110, 83)` / `rgba(0, 0, 0, 0)` | 0px `rgb(82, 110, 83)` · 4px | 0px/0px | 0px/0px | 57.52×18.14 |
| S0 示意 .hero-diagram | `#viewS0 .hero-diagram` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 10px/20px | 0px/0px | 400×205.03 |
| S0 阶段卡 .phase-card | `#viewS0 .phase-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 18px/20px | 0px/0px | 780×106.78 |
| S0 阶段序号 .phase-index | `#viewS0 .phase-index` | 16px / normal / 400 | `rgb(106, 133, 94)` / `rgb(240, 244, 237)` | 0px `rgb(106, 133, 94)` · 8px | 0px/0px | 0px/0px | 36×39 |
| S0 阶段 chip 警告 | `#s0PhaseB .chip` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| S0 卡片序号 .section-index | `#viewS0 .section-index` | 12px / normal / 400 | `rgb(105, 133, 99)` / `rgb(248, 250, 246)` | 1px `rgb(220, 231, 218)` · 6px | 0px/0px | 0px/0px | 25×25 |
| S0 表单标签 .s0-label | `#s0Form .s0-label` | 13px / 21.45px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 17px/0px | 816.22×21.44 |
| S0 输入框 #s0Baseline | `#s0Baseline` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 816.22×43 |
| S0 边界说明 .s0-boundary | `#viewS0 .s0-boundary` | 12px / 21.6px / 400 | `rgb(93, 119, 86)` / `rgb(242, 247, 239)` | 1px `rgb(225, 234, 219)` · 6px | 13px/14px | 17px/0px | 816.22×71.19 |
| S0 主按钮 #s0Prepare | `#s0Prepare` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/19px | 0px/0px | 125.03×42 |
| S0 检查项 .s0-checks li | `#s0Checks li` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 15px/0px | 0px/0px | 643.78×75.23 |
| S0 准出状态 #s0Readiness | `#s0Readiness` | 12px / 19.8px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(237, 223, 197)` · 6px | 11px/13px | 0px/0px | 643.78×43.8 |
| S0 阻断区 .s0-blockers | `#viewS0 .s0-blockers` | 14px / 23.1px / 400 | `rgb(140, 114, 76)` / `rgb(255, 250, 240)` | 1px `rgb(235, 223, 198)` · 10px | 22px/22px | 0px/0px | 689.78×165.53 |
| S0 范围说明 .s0-scope | `#viewS0 .s0-scope` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 6px/0px | 0px/0px | 1580×41.59 |
| S0 历史卡 .s0-history | `#viewS0 .s0-history` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 862.22×59.44 |

#### setup（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 配置步骤卡 .step-card | `#viewSetup .step-card` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(225, 232, 228)` · 9px | 22px/22px | 0px/0px | 1534×170.94 |
| 步骤序号 .step-no | `#viewSetup .step-no` | 14px / normal / 400 | `rgb(98, 131, 76)` / `rgb(237, 243, 232)` | 1px `rgb(218, 229, 210)` · 7px | 0px/0px | 0px/0px | 30×32 |
| 步骤标题 .step-title | `#viewSetup .step-title` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 1440×26.14 |
| 基线 select #setupBaseline | `#setupBaseline` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 460×42 |
| 基线 chip #setupBaselineChip | `#setupBaselineChip` | 11px / 18.15px / 640 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 89.22×26.14 |
| 浏览按钮 #btnBaselineBrowse | `#btnBaselineBrowse` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 69.02×38 |
| 项目输入 #setupProject | `#setupProject` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 1298.97×42 |
| 校验按钮 #setupCheck | `#setupCheck` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 56.02×38 |
| 字段说明 .field-meta | `#setupProjectMeta` | 12px / 21.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 12px/0px | 1440×27.8 |
| chips 容器 .chips | `#viewSetup .chips` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 8px/0px | 1440×26.14 |
| chip 普通 | `#viewSetup .chips .chip` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgb(243, 246, 243)` | 1px `rgb(225, 232, 228)` · 5px | 3px/8px | 0px/0px | 186.72×26.14 |
| chip 警告 | `#viewSetup .chips .chip.warn` | 11px / 18.15px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 5px | 3px/8px | 0px/0px | 128×26.14 |
| 模式 select #setupMode | `#setupMode` | 14px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 675.98×42 |
| 选项字段标签 .field-label | `#viewSetup .field-label` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 26.02×19.8 |
| 真实运行告警 #realWarn | `#realWarn` | 13px / 21.45px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(234, 215, 183)` · 8px | 12px/15px | 10px/0px | 0×0 |
| 高级折叠 summary | `#viewSetup details.adv summary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 4px/0px | 0px/0px | 1440×28.63 |
| 确认条 .confirm-bar | `#viewSetup .confirm-bar` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(247, 250, 245)` | 1px `rgb(225, 232, 228)` · 0px 0px 12px 12px | 20px/22px | 0px/0px | 1578×83 |
| 确认启动 #btnStart | `#btnStart` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/24px | 0px/0px | 115.02×42 |
| 确认条提示 #btnStartHint | `#btnStartHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 120.02×19.8 |
| health 卡 #healthBody | `#healthBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 777×333.48 |
| 操作边界 kv .kv | `#viewSetup .kv` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 9px/0px | 0px/0px | 733×40.44 |
| 脚注 .foot-note | `#viewSetup .foot-note` | 12px / 21.6px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 0px `rgb(113, 130, 123)` · 0px | 0px/0px | 10px/0px | 1440×21.59 |

#### run（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 运行头 .run-head | `#runHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1580×64 |
| 运行状态胶囊 .status-pill | `#runHead .status-pill` | 11px / 18.15px / 600 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 6px | 0px/10px | 0px/0px | 110.72×26 |
| 运行元信息 .run-meta | `#runHead .run-meta` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 106.77×19.8 |
| 刷新按钮 #runHead .btn | `#runHead .btn` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 四段容器 .stages | `#stages` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 1578×418.13 |
| 阶段卡 .stage | `#stages .stage` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(243, 209, 158)` · 8px | 0px/0px | 0px/0px | 1534×150.42 |
| 阶段头 .stage-head | `#stages .stage-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 1532×67.23 |
| 阶段序号 .stage-idx | `#stages .stage-idx` | 12px / normal / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(243, 209, 158)` · 7px | 0px/0px | 0px/0px | 27×27 |
| 阶段名 .stage-name | `#stages .stage-name` | 14px / 23.1px / 640 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 33.13×23.09 |
| 阶段进度 .stage-bar | `#stages .stage-bar` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(234, 240, 233)` | 0px `rgb(97, 116, 108)` · 999px | 0px/0px | 0px/0px | 90×5 |
| 阶段汇总 .stage-sum | `#stages .stage-sum` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/1248.33px | 167.55×19.8 |
| 阶段展开体 .stage-body | `#stages .stage.open .stage-body` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 247)` | 1px `rgb(225, 232, 228)` · 0px | 16px/16px | 0px/0px | 1532×81.19 |
| 节点 chip .snode | `#stages .snode` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 7px | 9px/10px | 0px/0px | 112×48.19 |
| 节点标记 .snode .sb | `#stages .snode .sb` | 10.5px / 17.325px / 700 | `rgb(113, 130, 123)` / `rgb(238, 241, 245)` | 1px `rgb(199, 212, 204)` · 50% | 0px/0px | 0px/0px | 20×20 |
| Agent 容器 #agents | `#agents` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 874.89×624.11 |
| Agent 卡 .agent | `#agents .agent` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 17px/17px | 0px/0px | 430.44×198.7 |
| Agent 名称 .agent-name | `#agents .agent-name` | 13px / 19.5px / 650 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 113.7×19.5 |
| Agent 角色 .agent-role | `#agents .agent-role` | 11px / 17.6px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 263.69×17.59 |
| Agent 正文 .agent-body | `#agents .agent-body` | 13px / 22.1px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 394.44×68.88 |
| Agent 动作 .agent-action | `#agents .agent-action` | 12px / 20.4px / 400 | `rgb(21, 119, 94)` / `rgba(0, 0, 0, 0)` | 0px `rgb(21, 119, 94)` · 0px | 0px/0px | 0px/0px | 394.44×20.39 |
| Agent 卡脚 .agent-foot | `#agents .agent-foot` | 11px / 18.15px / 400 | `rgb(113, 130, 123)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 10px/0px | 0px/0px | 394.44×29.14 |
| Host 行 .host-row | `#hostRow` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgb(246, 249, 244)` | 1px `rgb(224, 233, 219)` · 9px | 14px/14px | 14px/0px | 874.89×69.59 |
| 闸门卡 #gateCard | `#gateCard` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 253, 247)` | 1px `rgb(225, 232, 228)` · 12px | 0px/0px | 0px/0px | 635.11×711.52 |
| 计数容器 .counts | `#countsBody .counts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 589.11×99.48 |
| 计数框 .count-box | `#countsBody .count-box` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(250, 252, 248)` | 1px `rgb(224, 232, 219)` · 9px | 17px/17px | 0px/0px | 289.55×99.48 |
| 计数数字 .count-box .n | `#countsBody .count-box .n` | 29px / 37.7px / 600 | `rgb(179, 65, 64)` / `rgba(0, 0, 0, 0)` | 0px `rgb(179, 65, 64)` · 0px | 0px/0px | 0px/0px | 253.55×37.69 |
| 阻断项 .blocker | `#blockersBody .blocker` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 12px/0px | 0px/0px | 589.11×66.88 |
| 严重度标记 .sev | `#blockersBody .sev` | 10px / 16.5px / 700 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 0px `rgb(179, 65, 64)` · 4px | 3px/6px | 0px/0px | 49.06×22.5 |
| 长任务区 #jobBody | `#jobBody` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 633.11×63.8 |
| 事件折叠 summary | `#eventsSummary` | 12.5px / 20.625px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgb(225, 232, 228)` · 0px | 12px/18px | 0px/0px | 633.11×45.63 |
| 事件列表 .ev-list | `#eventList` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/18px | 0px/0px | 633.11×41.8 |
| 空态卡 #runEmpty | `#runEmpty` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 65px/25px | 0px/0px | 0×0 |

#### gate（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 闸门运行头 #gateHead | `#gateHead` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 10px | 16px/20px | 0px/0px | 1580×64 |
| 闸门告警区 #gateAlerts | `#gateAlerts` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1580×0 |
| 闸门四段 .stages | `#stagesGate` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 8px/22px | 0px/0px | 1578×418.13 |
| 闸门材料区 #gateMaterial | `#gateMaterial` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 918.89×754.69 |
| 差异清单项 .diff-item | `#gateMaterial .diff-item` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 874.89×127.58 |
| 差异未决项 .diff-item.unresolved | `#gateMaterial .diff-item.unresolved` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(255, 250, 241)` | 1px `rgb(232, 216, 183)` · 8px | 15px/15px | 0px/0px | 874.89×127.58 |
| 闸门操作区 #gatePanel | `#gatePanel` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 22px/22px | 0px/0px | 633.11×454.14 |
| 决策选项 .option | `#gatePanel .option` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 8px | 14px/14px | 0px/0px | 589.11×74.53 |
| 决策选项单选 .radio | `#gatePanel .option .radio` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 2px `rgb(199, 212, 204)` · 50% | 0px/0px | 2px/0px | 15×15 |
| actor 输入 | `#gatePanel [aria-label=actor]` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 220×42 |
| 理由输入 | `#gatePanel [aria-label='裁决理由']` | 14px / 23.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 8px/0px | 589.11×95.39 |
| 提交按钮 [data-gate-submit] | `#gatePanel [data-gate-submit]` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 10px/0px | 589.11×38 |
| 闸门错误区 .gate-error | `#gatePanel .gate-error` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 10px/0px | 589.11×0 |

#### dirpicker-project（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 目录选择器 #dirPicker | `#dirPicker` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 9px | 0px/0px | 10px/0px | 1440×316.38 |
| 目录头 .dp-head | `#dirPicker .dp-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 0px `rgb(33, 56, 49)` · 0px | 13px/15px | 0px/0px | 1438×57 |
| 上级按钮 #btnDirUp | `#btnDirUp` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 面包屑 .dp-crumb | `#dirCrumb` | 11.5px / 18.975px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 1285.28×18.97 |
| 收起按钮 #btnDirClose | `#btnDirClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 根列表 .dp-roots | `#dirRoots` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(251, 252, 254)` | 0px `rgb(33, 56, 49)` · 0px | 7px/10px | 0px/0px | 1438×45 |
| 目录列表 .dp-list | `#dirList` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 1438×155.38 |
| 目录项 .dp-item | `#dirList .dp-item` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 13px/16px | 0px/0px | 1438×53.14 |
| 目录项名 .dp-item b | `#dirList .dp-item b` | 12.5px / 20.625px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 301.91×20.63 |
| 目录脚 .dp-foot | `#dirPicker .dp-foot` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(246, 249, 243)` | 1px `rgb(225, 232, 228)` · 0px | 13px/15px | 0px/0px | 1438×57 |
| 选择此目录 #btnDirChoose | `#btnDirChoose` | 12.5px / 20.625px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/12px | 0px/0px | 88.52×30 |
| 目录提示 #dirHint | `#dirHint` | 12px / 19.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 289.36×19.8 |

#### agent（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| Agent 窗口 dialog | `#agentWindow` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 200)` · 14px | 0px/0px | 33.9062px/350px | 1220×932.17 |
| 窗口头 .aw-head | `#agentWindow .aw-head` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(245, 248, 241)` | 0px `rgb(33, 56, 49)` · 0px | 22px/28px | 0px/0px | 1218×99.14 |
| 窗口标题 h2 | `#awTitle` | 21px / 34.65px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 3px/0px | 966.3×34.64 |
| 窗口状态 chip #awStatus | `#awStatus` | 11px / 18.15px / 400 | `rgb(21, 119, 94)` / `rgb(234, 245, 239)` | 1px `rgb(184, 218, 202)` · 5px | 3px/8px | 0px/0px | 51×26.14 |
| 关闭按钮 #awClose | `#awClose` | 12px / 19.8px / 550 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 1px `rgba(0, 0, 0, 0)` · 7px | 0px/10px | 0px/0px | 60.7×30 |
| 工具条 .aw-toolbar | `#agentWindow .aw-toolbar` | 12px / 19.8px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 0px `rgb(33, 56, 49)` · 0px | 13px/28px | 0px/0px | 1218×61 |
| 身份 #awIdentity | `#awIdentity` | 11px / 18.15px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 171.64×18.14 |
| 节点 select #awNode | `#awNode` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 52×34 |
| 尝试 select #awAttempt | `#awAttempt` | 12px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/7px | 0px/0px | 130×34 |
| 刷新 #awRefresh | `#awRefresh` | 12px / 19.8px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/10px | 0px/0px | 46.02×30 |
| 观察区 .aw-observe | `#agentWindow .aw-observe` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 25px/28px | 0px/0px | 749.53×770.03 |
| 干预区 .aw-intervene | `#agentWindow .aw-intervene` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgb(248, 250, 245)` | 0px `rgb(33, 56, 49)` · 0px | 25px/25px | 0px/0px | 468.47×770.03 |
| 区块标题 .aw-section-head h3 | `#agentWindow .aw-section-head h3` | 15px / 24.75px / 700 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 0px/0px | 60.02×24.75 |
| 能力事实 #awCapabilities | `#awCapabilities` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 693.53×22.8 |
| 详情折叠 summary | `#agentWindow .aw-detail summary` | 13px / 21.45px / 400 | `rgb(33, 56, 49)` / `rgb(249, 251, 246)` | 0px `rgb(33, 56, 49)` · 0px | 15px/15px | 0px/0px | 691.53×51.44 |
| 时间线 .aw-timeline | `#awTimeline` | 14px / 23.1px / 400 | `rgb(217, 232, 212)` / `rgb(32, 54, 42)` | 1px `rgb(52, 83, 60)` · 9px | 17px/17px | 0px/0px | 693.53×170 |
| 输入补全 #awMessage | `#awMessage` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 11px/13px | 0px/0px | 417.47×164.34 |
| 操作者 #awActor | `#awActor` | 13px / 23.4px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 252)` | 1px `rgb(199, 212, 204)` · 7px | 0px/13px | 0px/0px | 417.47×42 |
| 补充指令按钮 #awSteer | `#awSteer` | 13px / 21.45px / 550 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 0px/14px | 0px/0px | 417.47×40 |
| 暂停/恢复按钮 #awPause | `#awPause` | 13px / 21.45px / 550 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(199, 212, 204)` · 7px | 0px/14px | 0px/0px | 204.23×40 |
| 终止按钮 #awTerminate | `#awTerminate` | 13px / 21.45px / 550 | `rgb(179, 65, 64)` / `rgb(255, 240, 239)` | 1px `rgb(231, 196, 191)` · 7px | 0px/14px | 0px/0px | 417.47×40 |
| 只读说明 .aw-note | `#agentWindow .aw-note` | 12px / 22.8px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 10px/0px | 693.53×22.8 |
| 动作行 .aw-action-row | `#agentWindow .aw-action-row` | 14px / 23.1px / 400 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(33, 56, 49)` · 0px | 0px/0px | 9px/0px | 417.47×40 |

#### legacy（1920×1000）

| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |
|---|---|---|---|---|---|---|---|
| 旧页返回入口 .back-workspace | `.back-workspace` | 12px / 20.4px / 400 | `rgb(193, 220, 189)` / `rgba(0, 0, 0, 0)` | 1px `rgb(107, 131, 106)` · 6px | 5px/10px | 0px/0px | 161.36×32.39 |
| 旧页权威说明 .authority | `.authority` | 13px / 22.1px / 400 | `rgb(226, 235, 225)` / `rgb(237, 243, 232)` | 1px `rgb(212, 224, 204)` · 0px | 12px/28px | 0px/0px | 1920×45.39 |
| 旧页面板 .panel | `.panel` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 12px | 20px/20px | 4px/0px | 1844×62.39 |
| 旧页面板标题 h2 | `.panel>h2` | 15px / 25.5px / 600 | `rgb(33, 56, 49)` / `rgba(0, 0, 0, 0)` | 0px `rgb(225, 232, 228)` · 0px | 0px/0px | 0px/0px | 298×39.5 |
| 旧页状态条 .status-strip | `.status-strip` | 13px / 22.1px / 400 | `rgb(33, 56, 49)` / `rgb(255, 255, 255)` | 1px `rgb(225, 232, 228)` · 9px | 15px/19px | 0px/0px | 1844×88.64 |
| 旧页按钮 .btn | `.btn` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页主按钮 .btn-primary | `.btn-primary` | 13px / normal / 400 | `rgb(255, 255, 255)` / `rgb(21, 119, 94)` | 1px `rgb(21, 119, 94)` · 7px | 8px/13px | 0px/0px | 182.98×37 |
| 旧页输入框 input[type=text] | `input[type=text]` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 440×40.8 |
| 旧页 textarea | `textarea` | 13px / 20.8px / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 1440×82.39 |
| 旧页 select | `select` | 13px / normal / 400 | `rgb(33, 56, 49)` / `rgb(252, 253, 251)` | 1px `rgb(199, 212, 204)` · 7px | 9px/12px | 0px/0px | 440×41 |
| 旧页折叠 summary | `details>summary` | 12px / 20.4px / 400 | `rgb(97, 116, 108)` / `rgba(0, 0, 0, 0)` | 0px `rgb(97, 116, 108)` · 0px | 0px/0px | 0px/0px | 1802×20.39 |
| 旧页日志 .logtail | `pre.logtail` | 12px / 21.6px / 400 | `rgb(220, 232, 215)` / `rgb(32, 56, 43)` | 1px `rgb(52, 83, 60)` · 7px | 12px/12px | 5px/0px | 0×0 |
| 旧页 JSON pre | `pre.json` | 12px / 20.4px / 400 | `rgb(80, 105, 75)` / `rgb(247, 250, 243)` | 1px `rgb(225, 232, 228)` · 7px | 12px/12px | 5px/0px | 1440×220 |
| 旧页徽章 .badge | `.badge` | 11.5px / 19.55px / 400 | `rgb(154, 94, 22)` / `rgb(255, 246, 232)` | 1px `rgb(231, 213, 180)` · 5px | 3px/7px | 0px/0px | 47.23×27.55 |
| 旧页 chip | `.chip` | — | — | — | — | — | **选择器未命中**（legacy） |

## 6 键盘焦点顺序

从 `document.body`（`tabindex=-1` 程序聚焦）按 `Tab` 逐次记录，遇到重复签名即停止；记录 `:focus-visible` 是否成立与 outline 值。1280 全量列出；1440/1920 与 1280 的差异见每节末尾（完整三视口数据在 [raw/focus-order.json](raw/focus-order.json)）。

### s0（1280×1000，16 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `skip-link` | 跳到工作区 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `lnkLegacy` | 旧版操作台 ↗ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `btnS0` | F 仿真与验证 Simulation workspace ⌄ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `btnNew` | ＋ 新建运行 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `segS0` | ▧ 环境准备 S0 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `run-item` | A drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `run-item` | B drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `s0Baseline` |  | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 9 | `s0Version` |  | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 10 | `s0Rtl` |  | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 11 | `s0Work` |  | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 12 | `summary` | 可访问的目录范围 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `s0Prepare` | 派生并校验 → | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `summary` | 准备记录 查看历史派生与重新核验 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 15 | `s0Refresh` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 16 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（16 站）；1920 与 1280 完全一致（16 站）

### setup（1280×1000，17 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `skip-link` | 跳到工作区 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `lnkLegacy` | 旧版操作台 ↗ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `btnS0` | F 仿真与验证 Simulation workspace ⌄ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `btnNew` | ＋ 新建运行 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `segSetup` | ⊞ 运行配置 01 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `run-item` | A drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `run-item` | B drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `setupBaseline` | 基线版本 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 9 | `btnBaselineBrowse` | 浏览… | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 10 | `btnRefreshBaselines` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 11 | `setupProject` | 项目目录 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 12 | `btnProjectBrowse` | 浏览… | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `setupCheck` | 校验 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `setupMode` | drill · 用冻结夹具（推荐先跑） real · 真机编译/全跑 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 15 | `setupScenario` | happy dead_job（死任务夹具） cancel（取消夹具） | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 16 | `summary` | 高级（时间注入） | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 17 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（17 站）；1920 与 1280 完全一致（17 站）

### run（1280×1000，23 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `skip-link` | 跳到工作区 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `lnkLegacy` | 旧版操作台 ↗ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `btnS0` | F 仿真与验证 Simulation workspace ⌄ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `btnNew` | ＋ 新建运行 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `segRun` | ◴ 运行监控 02 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `run-item active` | A drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `run-item` | B drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `btn btn-sm` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 9 | `stage-head` | 1 摄取 N0–N4 等待人工 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 10 | `stage-head` | 2 修订 N5–N8 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 11 | `stage-head` | 3 验证 N9–N12 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 12 | `stage-head` | 4 决策 N13–N16 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `agent-name agent-open` | 打开 simenv-analyst 工作窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `agent-name agent-open` | 打开 simenv-author 工作窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 15 | `agent-name agent-open` | 打开 simenv-checker 工作窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 16 | `agent-name agent-open` | 打开 simenv-guardian 工作窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 17 | `agent-name agent-open` | 打开 simenv-reporter 工作窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 18 | `summary` | N2 差异清单 · 2 条 · 无未决 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 19 | `input` | confirmed | ✅ | 1px auto rgb(16, 16, 16) offset 2px |
| 20 | `input mono` | actor | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 21 | `input` | 裁决理由 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 22 | `eventsSummary` | 事件流 · 0 条白名单事件（seq 递增 · 只读 · 折叠） | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 23 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（23 站）；1920 与 1280 完全一致（23 站）

### gate（1280×1000，17 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `skip-link` | 跳到工作区 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `lnkLegacy` | 旧版操作台 ↗ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `btnS0` | F 仿真与验证 Simulation workspace ⌄ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `btnNew` | ＋ 新建运行 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `segGate` | ◇ 人工闸门 03 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `run-item active` | A drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `run-item` | B drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `btn btn-sm` | 查看执行详情 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 9 | `btn btn-sm` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 10 | `stage-head` | 1 摄取 N0–N4 等待人工 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 11 | `stage-head` | 2 修订 N5–N8 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 12 | `stage-head` | 3 验证 N9–N12 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `stage-head` | 4 决策 N13–N16 待开始 ▸ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `input` | confirmed | ✅ | 1px auto rgb(16, 16, 16) offset 2px |
| 15 | `input mono` | actor | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 16 | `input` | 裁决理由 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 17 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（17 站）；1920 与 1280 完全一致（17 站）

### dirpicker-project（1280×1000，26 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `skip-link` | 跳到工作区 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `lnkLegacy` | 旧版操作台 ↗ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `btnS0` | F 仿真与验证 Simulation workspace ⌄ | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `btnNew` | ＋ 新建运行 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `segSetup` | ⊞ 运行配置 01 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `run-item` | A drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `run-item` | B drill · 等待人工 · — | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `setupBaseline` | 基线版本 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 9 | `btnBaselineBrowse` | 浏览… | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 10 | `btnRefreshBaselines` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 11 | `setupProject` | 项目目录 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 12 | `btnProjectBrowse` | 浏览… | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `setupCheck` | 校验 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `btnDirUp` | ↑ 上级 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 15 | `crumb-seg` | simulation | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 16 | `btnDirClose` | 收起 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 17 | `btn btn-ghost btn-sm` | 根：simulation | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 18 | `btn btn-ghost btn-sm` | 根：projects | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 19 | `dp-item` | ▸ TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES 环境仓 uvs | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 20 | `dp-item` | ▸ baseline-v1.2 manifest.json | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 21 | `dp-item` | ▸ work-v1.3 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 22 | `btnDirChoose` | 选择此目录 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 23 | `setupMode` | drill · 用冻结夹具（推荐先跑） real · 真机编译/全跑 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 24 | `setupScenario` | happy dead_job（死任务夹具） cancel（取消夹具） | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 25 | `summary` | 高级（时间注入） | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 26 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（26 站）；1920 与 1280 完全一致（26 站）

### agent（1280×1000，16 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `awNode` | Agent 节点 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 2 | `awAttempt` | 调用尝试 | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 3 | `awRefresh` | 刷新 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `summary` | 上下文预算 未知（未测量） | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `summary` | 尝试摘要与输入差异 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 6 | `summary` | 任务输入 完整调用输入，只读 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 7 | `summary` | 提示词与约束 调用时快照 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `summary` | 输出与 Host 校验 尚无结果 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 9 | `awActor` | human: | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 10 | `awMessage` |  | ✅ | 2px solid rgb(196, 226, 207) offset 1px |
| 11 | `awSteer` | 补充指令并重跑 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 12 | `awPause` | 暂停请求 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 13 | `awTerminate` | 终止当前节点 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 14 | `summary` | 取消与恢复的边界 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 15 | `body` | 跳到工作区 FPGA Flow / 仿真工作台 /fixture 插件面齐全 · agently | — | 3px none rgb(33, 56, 49) offset 0px |
| 16 | `awClose` | 关闭 Agent 窗口 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |

**三视口对照**：1440 与 1280 完全一致（16 站）；1920 与 1280 完全一致（16 站）

### legacy（1280×1000，12 站）

| # | 元素 | 名称/文本 | :focus-visible | outline |
|---|---|---|---|---|
| 1 | `back-workspace` | ← 返回 FPGA Flow 工作台 | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 2 | `summary` | 启动运行 / 打开既有运行（写操作：POST api/runs） | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 3 | `summary` | pending_interrupt 原始 JSON | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 4 | `summary` | gate_material 原始 JSON | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 5 | `fActor` | human: | ✅ | 2px solid rgb(200, 223, 188) offset 1px |
| 6 | `fReason` |  | ✅ | 2px solid rgb(200, 223, 188) offset 1px |
| 7 | `btn dec-btn` | 服务端确认 confirmed | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 8 | `btn dec-btn` | 服务端忽略 ignored | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 9 | `summary` | counts 原始 JSON | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 10 | `summary` | can 原始 JSON | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 11 | `summary` | blockers 原始 JSON | ✅ | 3px solid rgb(21, 119, 94) offset 3px |
| 12 | `body` | 闭环变更影响 · 闸门操作台 ← 返回 FPGA Flow 工作台 agently （字段缺失） | — | 3px none rgb(33, 56, 49) offset 0px |

**三视口对照**：1440 与 1280 完全一致（12 站）；1920 与 1280 完全一致（12 站）

## 7 溢出、缩放与 reduced-motion

### 7.1 主验收视口的页面水平溢出

| 状态 | 1280 | 1440 | 1920 |
|---|---|---|---|
| run-empty | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| s0 | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| setup | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| dirpicker-baseline | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| dirpicker-project | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| run | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| run-failed | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| gate | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| gate-rejected | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| agent | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| legacy | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| loading | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| first-error | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |
| stale-error | 无溢出（scrollWidth 1280 / 1280） | 无溢出（scrollWidth 1440 / 1440） | 无溢出（scrollWidth 1920 / 1920） |

### 7.2 窄屏 390/768（只做溢出检查，不新增移动目标）

| 宽度 | 状态 | 页面水平溢出 | 越界/局部溢出元素数 | 前若干项 |
|---|---|---|---|---|
| 390 | s0 | 否 | 0 | — |
| 390 | setup | 否 | 1 | local-overflow#setupProject |
| 390 | run | 否 | 3 | local-overflow；local-overflow；local-overflow |
| 390 | gate | 否 | 2 | local-overflow；local-overflow |
| 390 | agent | 否 | 3 | local-overflow；local-overflow；local-overflow |
| 768 | s0 | 否 | 3 | local-overflow#btnS0；local-overflow；local-overflow |
| 768 | setup | 否 | 3 | local-overflow#btnS0；local-overflow；local-overflow |
| 768 | run | 否 | 4 | local-overflow#btnS0；local-overflow；local-overflow；local-overflow |
| 768 | gate | 否 | 4 | local-overflow#btnS0；local-overflow；local-overflow；local-overflow |
| 768 | agent | 否 | 4 | local-overflow#btnS0；local-overflow；local-overflow；local-overflow |

### 7.3 prefers-reduced-motion 对照（1440）

| 设置 | matchMedia | 按钮 transition-duration | spinner 动画 | html/body scroll-behavior |
|---|---|---|---|---|
| no-preference | False | `0.15s, 0.15s, 0.15s` | `spin 1s` | `auto` / `auto` |
| reduce | True | `0s` | `none 0s` | `auto` / `auto` |

## 8 采集期安全性与失败项

- 采集全程只读：切页、聚焦、hover、打开/关闭目录浏览器与 Agent 窗口；闸门「提交」仅用于触发被拒态，POST 被 route 拦截并回 403，未发往真实服务。
- 采集脚本记录的 POST 目的地：1280 视口 `/api/runs/A/gates/G1_diff_confirm/decision`；1440 视口 `/api/runs/A/gates/G1_diff_confirm/decision`；1920 视口 `/api/runs/A/gates/G1_diff_confirm/decision`
- 页面 JS 异常（`pageerror`）：无
- 脚本采集失败项：无

## 9 未覆盖项与限制

1. **不是视觉验收**：本文件只固定改前可观察事实；是否「视觉等价」需要独立评审按 screens-after 对比逐条判读，同一执行者不得自证通过。
2. **API 是受控替身**：基线列表、运行 A/B、Agent 记录、目录列表均为固定响应；真实服务端数据形状与真实模型/仿真链路未覆盖。
3. **未测宿主缩放 125%/150%**：本轮记录 100%（`devicePixelRatio=1`、`visualViewport.scale=1`）。主验收的缩放与键盘可达性复核留到 F14-b 改后阶段。
4. **窄屏 390/768 只做溢出检查**，不提供截图，也不作为产品目标。
5. **旧页（legacy.html）只覆盖桌面三视口**；其窄屏兼容沿用既有实现，未新增目标。
6. **未覆盖**：真实浏览器地址栏/系统字体差异（不同主机字体可能影响换行与高度）、深色系统主题（页面固定 `color-scheme:light`）、打印样式、150% 以上缩放。

