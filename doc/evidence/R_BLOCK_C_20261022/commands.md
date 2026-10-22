# F14-a · 采集命令与原始输出

日期：2026-10-22（Asia/Shanghai）。采集时 `HEAD=746ec8d13ea857e4dcb30190d1fcc8c27b0458b7`（`main`），
其中 R5 已合入（`746ec8d`，`agent-window.js`/`context-explain.js` 定稿），所以改前截图与样式事实都取自
含 R5 的同一棵树。工作树脏文件（他人的在途产物）见 `raw/env-facts.log` 的 `git status --porcelain`。

本文件记录**实际执行的命令与原始输出**；`style-inventory.md` 记录采集结果，两者都由脚本生成/校核。
同一执行者采集，**不是独立视觉评审**；本阶段只做改前基线，**不声称视觉验收通过**。

## 0 环境前置（缺任一条件是错误，不是 skip）

浏览器用例与采集脚本都要求：**可写 `HOME`/`XDG_*`** 与显式的 `LOOP_BROWSER_EXECUTABLE`。
`$HOME` 只读时 Chrome 启动会失败（§39 已登记 `FAIL: TargetClosedError`；本轮首次以只读 HOME 便捷
验证时也复现了 `touch: cannot touch '.../.local/share/applications/mimeapps.list': Read-only file system`），
因此下列命令统一写成：

```text
cd /home/work/chenjunming/change-impact-loop/loop
mkdir -p /tmp/h
HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
  LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome ...
```

`/tmp/h` 是每次调用可重建的临时目录；仓库内不留临时产物。

## 1 版本与文件事实（原始输出：`raw/env-facts.log`）

```text
$ git rev-parse HEAD
746ec8d13ea857e4dcb30190d1fcc8c27b0458b7
$ git rev-parse --abbrev-ref HEAD
main
$ cd loop && .venv/bin/python -V
Python 3.11.7
$ cd loop && .venv/bin/python -c "from importlib.metadata import version; print(version('playwright'))"
1.64.0
$ HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache /usr/bin/google-chrome --version
Google Chrome 152.0.7977.75
```

采集脚本记录的运行环境（`raw/env.json`）：`devicePixelRatio=1`、`visualViewport.scale=1`（**100% 缩放**）、
`screen 1280×1000`、UA 见文件原文；Playwright context 视口为 1280/1440/1920 × **1000**（高 1000），
窄屏 390×844 / 768×844。字体计算值：`body` 为 `--font-sans` 栈、`.mono` 为 `--font-mono` 栈（原文见
`style-inventory.md` §0）。

## 2 现有浏览器特征集 + 改前截图（21 张）

`loop/tests/browser` 的 `capture()` 支持 `LOOP_VISUAL_ARTIFACTS`，截图落在该目录（`full_page=True`，
`*-agent` 为视口内截图）。

```text
$ cd /home/work/chenjunming/change-impact-loop/loop
$ HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
    LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
    LOOP_VISUAL_ARTIFACTS=/home/work/chenjunming/change-impact-loop/doc/evidence/R_BLOCK_C_20261022/screens-before \
    .venv/bin/python -m pytest -q tests/browser --tb=short
```

原始输出（`raw/pytest-browser.log` 末尾）：`.........................................  [100%]` / `41 passed in 60.17s (0:01:00)`。
无 skip、无 error。落图状态：1280/1440/1920 × 环境准备、运行配置（含基线目录浏览器）、运行监控、
人工闸门、Agent 工作窗口、旧界面；另有 1440 的空态、加载态、首次失败态（`1440-empty/loading/error.png`）。

## 3 独立只读采集脚本（补充场景 + 计算样式 + 焦点顺序）

`collect_f14a.py` 只启动 `127.0.0.1` 临时静态服务指向 `loop/web/`，`/api/**` 全部由 Playwright route
返回受控替身；**不连接真实服务、不写 `loop/web/**`、不写 `ENV_ROOT`/`kb/**`**。POST 只记录不转发
（闸门被拒态用本地 403 回包渲染）。

```text
$ cd /home/work/chenjunming/change-impact-loop/loop
$ HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
    LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
    .venv/bin/python ../doc/evidence/R_BLOCK_C_20261022/collect_f14a.py \
      --out ../doc/evidence/R_BLOCK_C_20261022
```

原始输出（`raw/collect_f14a.log`，逐行复制）：

```text
F14-a 采集完成
  输出目录：/home/work/chenjunming/change-impact-loop/doc/evidence/R_BLOCK_C_20261022
  截图：45 张（screens-before）
  页面状态：42 个（含三视口记录）
  焦点顺序：21 份
  交互态：59 项
  媒体查询：18 次出现 / 16 个不同条件
  浏览器：152.0.7977.75
```

补充场景截图（24 张，三视口各 8 张）：空态、加载态、首次失败、陈旧失败、运行失败、基线目录浏览器、
项目目录浏览器、闸门被拒。采集的确定性手段：`page.clock.install()` 冻结定时器，轮询用
`clock.run_for(1600)` + 80 ms 真实等待推进（与 `tests/browser` 同口径）；hover 态另用未装假时钟的
页面，`hover` 后等 400 ms 让 150 ms 过渡结束再读计算样式。

## 4 静态清单（既有只读工具，复跑）

```text
$ cd /home/work/chenjunming/change-impact-loop/loop
$ .venv/bin/python spikes/css_inventory.py
```

原始输出摘要（全文 `raw/env-facts.log`）：

```text
== tokens.css: lines=17 rules=1 media=0 important=0 duplicate_decls=0
== app.css: lines=730 rules=795 media=14 important=6 duplicate_decls=98
== legacy.css: lines=75 rules=74 media=2 important=2 duplicate_decls=0
```

> 与 `doc/STATUS.md` §29 的静态表对照：`legacy.css` 的 `!important` 本工具实测为 **2 处**
> （`animation:none!important`、`transition:none!important`），§29 记的是「1 处」。
> 本轮按工具输出记录差异，不改 `doc/STATUS.md`（Lead 唯一写者），供 Lead 更正数字。

媒体查询方面，浏览器 CSSOM 采集到 **18 次出现 / 16 个不同条件**：`app.css` 14 次（其中
`max-width:760px` 与 `prefers-reduced-motion:reduce` 各出现两次）、`legacy.css` 2 次、
`legacy.html` 内联 `<style>` 2 次（`max-width:1080px`、`max-width:760px`）。`legacy.html` 的内联样式
是独立深色主题（不是 `legacy.css`），本轮只记录，不修改 HTML。

## 5 采集期的只读/安全事实

- 采集全程没有向真实服务发出请求：`/api/**` 全部被 route 拦截；脚本记录的 POST 仅有闸门被拒态
  一次 `POST /api/runs/A/gates/G1_diff_confirm/decision`（本地 403，未转发），且每视口各一次。
- `pageerror`：无（采集脚本与浏览器特征集均无 JS 异常；`raw/summary.json` 的 `page_errors=[]`）。
- 未修改 `loop/web/**`：本阶段只新增 `doc/evidence/R_BLOCK_C_20261022/**`。

## 6 未运行项与限制

1. **改后截图与视觉等价判读**：属于 F14-b，本文件不含。
2. **125% / 150% 缩放**：本轮只记录 100%（`devicePixelRatio=1`、`visualViewport.scale=1`）。
3. **窄屏 390/768**：只做页面水平溢出检查，无截图（F14 计划：不新增移动端产品目标）。
4. **真实服务端/真实模型/内网夹具**：未运行；所有数据是受控替身。
5. **视觉验收结论**：本阶段只固定改前可观察事实，不能据此声称视觉已验收（同一执行者不得自证）。

## 7 产物清单

| 产物 | 说明 |
|---|---|
| [screens-before/](screens-before/) | 45 张改前截图（21 张来自 `tests/browser`、24 张来自采集脚本），像素与 MD5 见 `style-inventory.md` §1 |
| [style-inventory.md](style-inventory.md) | 改前样式清单：环境、截图索引、断点矩阵、版面几何、关键元素计算样式、交互态、焦点顺序、溢出/缩放/reduced-motion、限制 |
| [collect_f14a.py](collect_f14a.py) | 只读采集脚本（可复跑；支持 `--screens-dir`/`--no-markdown` 供 F14-b 改后采集） |
| [raw/](raw/) | 原始输出与机器可读快照：`env-facts.log`、`pytest-browser.log`、`collect_f14a.log`、`env.json`、`media-queries.json`、`focus-order.json`、`interactive-states.json`、`summary.json` |
| [MD5SUMS.txt](MD5SUMS.txt) | 本目录稳定件的 MD5（只增不改锚点） |
