# UI 设计审视证据（2026-10-30）

> **只增不改**。本目录是 [`doc/audit/AUDIT-20261030-ui-design.md`](../../audit/AUDIT-20261030-ui-design.md) 的证据附录。
> **本轮不修任何被测文件**：`loop/web/**`、`doc/spec/**`、`doc/STATUS.md` 均未改动。

## 1 这些证据是什么、不是什么

| 项 | 说明 |
|---|---|
| 数据来源 | Chromium 156（`loop/.venv` 的 Playwright）+ **受控 API 夹具**（与 `loop/tests/browser/test_web_layout.py::populate` 同源） |
| 是不是真实运行 | **不是**。夹具只用于渲染稳定页面结构以测量样式事实；页面里的「未记录/ignored/—」等文案来自夹具，**不作产品缺陷结论** |
| 视口 | 验收视口 1280×720 / 1440×900 / 1920×1080（`doc/spec/WEB_UI_SPEC.md` §14） |
| 测量内容 | 计算样式（字体真实回退、字号直方图、行高、对比度、焦点环对比、点击靶、折叠线包围盒、过渡曲线、渐变、横向溢出） |
| 不可测量 | hover/active 的视觉截图、真机非 headless 的滚动条渲染、真实长路径/超长错误串下的对比度 |

## 2 文件清单与 md5

```
5c1c6207847736a425fa9c29f20a6987  screens/01-s0-1280x720-first-screen.png
389d503fb3c6b6a2f23e8d8f32a21259  screens/02-s0-1440x900-first-screen.png
4255a774ff636cb319a0894b1e9af9d7  screens/03-gate-1440x900-first-screen.png
6910597b07169eeae4b7863ab2e015ba  screens/04-monitor-1440-fullpage.png
274087f6bc55bc8c5a2eca63c8c10ec7  screens/05-agent-window-1440.png
3fb28fde16864aefbf396d1d44f52fbd  screens/06-loading-1440-fullpage.png
a2b221ac6a7057624761d06b5b7971e6  screens/07-empty-1440.png
09979b74dcd6735a3b53e29e1f5e2898  measure.json
b2ebd148c4338915a2eea597752e5bea  measure.py（归档副本，见 §3）
```

截图来源：`01`–`03` 由 `measure.py` 本轮生成；`04`–`07` 由 `loop/tests/browser/test_web_layout.py` 的
`LOOP_VISUAL_ARTIFACTS` 机制生成（同一受控夹具）。

## 3 `measure.py` 归档副本与原始脚本的差异

原始脚本在工作区临时目录 `.ui-audit/measure.py`（**未入库**，md5 `bbd6dba4c205d9611f01e62c20524267`）。
归档副本 md5 为 `b2ebd148c4338915a2eea597752e5bea`，**唯一差异**是第 31 行：

```diff
-REPO = Path(__file__).resolve().parents[1]
+# 归档副本的唯一差异：REPO 由所在目录推导改为向上查找 loop/web 的仓库根（
+# 原脚本在 .ui-audit/measure.py，测量逻辑未改；差异与 md5 见同目录 README.md）。
+REPO = next(p for p in Path(__file__).resolve().parents if (p / 'loop' / 'web').is_dir())
```

原因：原脚本假定自己位于 `.ui-audit/`（`parents[1]` = 仓库根）；归档后目录层级变深，该行会指向
`doc/`。测量逻辑、夹具、输出结构均未改。

## 4 复跑

```bash
cd <repo>
PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
  loop/.venv/bin/python doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py
```

输出：同目录 `measure.json` 与 `shots-b/*.png`（会覆盖本目录 `measure.json`；要保留归档件请先复制）。

**复跑一致性实测（2026-10-30）**：把归档副本复制到 `.ui-audit/repro/` 运行，exit=0；与归档
`measure.json` 逐值对比，**仅 6 处差异且全部是 ephemeral 本地端口**（`127.0.0.1:44629` vs
`127.0.0.1:34849`），其余数字逐位相同。差异原文见 [`repro-diff.txt`](repro-diff.txt)。

## 5 分报告归档（`doc/audit/parts/ui-design-20261030/`）

四份独立分报告原在审计工作区 `.ui-audit/`（未入库临时件），审计收口时归档并更名；归档副本只加了来源横幅，
C 报告另改了 1 处「计划新建、尚不存在」的路径表述（避免被文档门当成断链）。原始 md5 一并记录：

| 归档文件 | md5（归档件） | 原文件名 / md5 |
|---|---|---|
| [`A-visual-tokens.md`](../../audit/parts/ui-design-20261030/A-visual-tokens.md) | `319fc0e418e838609a24ac19aace8248` | `.ui-audit/A-visual.md` / `6b0e74e37337803e6ac51196aecc4f36` |
| [`B-runtime-measured.md`](../../audit/parts/ui-design-20261030/B-runtime-measured.md) | `b20efdb69916addd8e4ba1d2d2b751bc` | `.ui-audit/B-runtime.md` / `97eb69b3770286b3f5bde6e2e0b3a947` |
| [`C-content-semantics.md`](../../audit/parts/ui-design-20261030/C-content-semantics.md) | `a2ee45322d412e8345e8407d06d68c70` | `.ui-audit/C-content.md` / `1a400788d6a1e6c690712ca5eb753f07` |
| [`D-independent-verify.md`](../../audit/parts/ui-design-20261030/D-independent-verify.md) | `ce4b9e5ebe747a37e383eccc0c5d2df9` | `.ui-audit/D-verify.md` / `0a36b232e37e16c51c1ed4bae239335d` |

## 6 已知局限（未实测项）

- 未在真实运行数据上复测对比度（夹具下的长路径、超长错误串未覆盖）。
- 未在非 Chromium 浏览器复测字体回退与焦点环渲染；`scrollbar-gutter` 的实际留白依赖浏览器。
- 未截图验证 hover / active / loading 的视觉（仅读计算样式与 CSS 声明）。
- 移动端/窄屏按 `WEB_UI_SPEC.md` §14 是明确非目标，未验、不建议验。
