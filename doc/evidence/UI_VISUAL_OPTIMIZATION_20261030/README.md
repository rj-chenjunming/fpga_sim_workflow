# UI 视觉优化（批次 1+2）证据（2026-10-30）

> **只增不改**。本目录是 `doc/STATUS.md` §140 与
> [`doc/plans/2026-10-30-ui-visual-optimization.md`](../../plans/2026-10-30-ui-visual-optimization.md) 的证据附录。
> 上游审计：[`doc/audit/AUDIT-20261030-ui-design.md`](../../audit/AUDIT-20261030-ui-design.md)。
> **数据来源**：Chromium 156 + **受控 API 夹具**（非真实运行）；截图与读数只证明样式事实，不证明业务结果。

## 1 前后对比（同一受控夹具、同一视口）

| 视口 / 视图 | 优化前 | 优化后 | 判据 |
|---|---|---|---|
| 1280×720 环境准备 | `#s0Rtl` y=793、`#s0Prepare` y=1098（均在首屏外） | 两者 `visibleRatio = 1` | §10 A12 |
| 1440×900 环境准备 | `#s0Rtl` y=794.8、`#s0Prepare` y=1078.3 | 两者 `visibleRatio = 1` | §10 A12 |
| 1920×1080 环境准备 | `#s0Prepare` 仅 32% 可见 | 两者 `visibleRatio = 1` | §10 A12 |
| 1440×900 人工闸门 | `#gateMaterial` y=913.6（首屏外） | `#gateMaterial` 进入首屏（`visibleRatio 0.12`，顶边可见） | §10 A12（只压上方留白） |
| 信息文本对比度 | S0 28/209 个文本节点 <4.5 | S0 3/194，且**全部为装饰符或禁用控件** | §10 A13 |
| 焦点环 | `#s0Rtl` 1.39、侧栏 2.62 | `#s0Rtl` **5.48**、侧栏 **9.0** | §10 A13 |
| 点击靶 <24px | 5 个（`.agent-open` 19.5px） | **0** | — |
| 背景渐变 | 1 处（单选点 `radial-gradient`） | **0** | §14 增补 |
| 动效曲线 | 0 处显式曲线（全 `ease`/150ms） | 全部 `cubic-bezier(0.22, 1, 0.36, 1)`；无 `transition: width` | §14 增补 |

截图（受控夹具，非真实运行）：

| 文件 | 说明 |
|---|---|
| [`screens/before-1280x720-s0.png`](screens/before-1280x720-s0.png) | 优化前：1280×720 首屏只有页头与 hero/阶段卡 |
| [`screens/after-1280x720-s0.png`](screens/after-1280x720-s0.png) | 优化后：必填项与「派生并校验」同屏 |
| [`screens/before-1440-gate.png`](screens/before-1440-gate.png) | 优化前：1440×900 闸门材料在首屏外 |
| [`screens/after-1440-gate.png`](screens/after-1440-gate.png) | 优化后：材料/操作两栏顶边进入首屏 |
| [`screens/after-1440-environment.png`](screens/after-1440-environment.png) | 优化后整页（hero 已删、阶段卡收紧） |

## 2 运行时读数（`measure-after.json`，2026-10-30 复跑）

```
M6_fold            #s0Rtl / #s0Prepare visibleRatio = 1.0 / 1.0 / 1.0（1280/1440/1920）
M6b_gate_fold      #gateMaterial visibleRatio = 0 / 0.12 / 0.37（1280/1440/1920）
M4_contrast_s0     failCount=3 / textNodes=194，min=1.53（装饰分隔符）
M4_contrast_gate   failCount=4 / 173（装饰 1.53、1.89 + 禁用 2.17/2.56）
M4_contrast_monitor failCount=4 / 238（装饰 + 禁用 2.85）
M5_focus_s0        #s0Rtl ringContrast=5.48；#btnS0/#segS0=9.0；skip→main 2px solid --primary
M7_targets_*       lt24 = 0（s0/monitor）
M8_*               gradients = []（S0 与 gate 视图均无背景渐变）
M9_motion          全部 cubic-bezier(0.22, 1, 0.36, 1)
```

**豁免说明**：剩余低对比度项只有两类，均不属信息文本 —— ① 装饰分隔符 `/`（页头与面包屑，`aria` 无关的排版符）；
② `disabled` 控件（通知开关、闸门提交、运行刷新；WCAG 1.4.3 不适用于禁用态）。
**monitor 视图的头像首字母**已单独压暗（`.a3/.a4/.a5/.a6`），读数由 4.06–4.42 提到 5.71–6.23。

## 3 md5

```
a163b05acc960d2dce7f57fad76f2db8  screens/after-1280x720-s0.png
5ad1552118f200e98f5a5339d6d01a59  screens/after-1440-environment.png
3822d4eaf10fe8eb3bd9a97bedd729cd  screens/after-1440-gate.png
5c1c6207847736a425fa9c29f20a6987  screens/before-1280x720-s0.png
4255a774ff636cb319a0894b1e9af9d7  screens/before-1440-gate.png
3f389f76e8e8ec87f9f4c6142f46b84b  measure-after.json
```

## 4 复跑

```bash
cd <repo>
PLAYWRIGHT_BROWSERS_PATH=$PWD/.pw-browsers HOME=$PWD/.chrome-home TMPDIR=$PWD/.chrome-tmp \
  loop/.venv/bin/python doc/evidence/UI_DESIGN_AUDIT_20261030/measure.py   # 运行时读数（会写同目录）
```

验收用例（本轮新增，先红后绿）：
`loop/tests/browser/test_ui_visual_20261030.py`（11 passed）。
