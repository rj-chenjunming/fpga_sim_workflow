# UI 字号阶梯落地证据（2026-10-30，批次 3A）

> **只增不改**。本目录是 `doc/STATUS.md` §141 与
> [`doc/plans/2026-10-30-ui-typography-scale.md`](../../plans/2026-10-30-ui-typography-scale.md) 的证据附录。
> 判据：[`WEB_UI_SPEC.md`](../../spec/WEB_UI_SPEC.md) §14「字号阶梯（2026-10-30 增补）」/ §10 A14。
> 截图来自受控 API 夹具（非真实运行）；只证明字号层级与几何，不证明业务结果。

## 1 结果

| 项 | 优化前 | 优化后 |
|---|---|---|
| `app.css` 不同字号 | **25 个**（7/8/9/9.5/10/10.5/11/11.5/12/12.5/13/13.5/14/15/15.5/16/17/18/19/20/21/22/24/29/31） | **10 个**（10/11/12/13/14/16/18/20/24/30），全部属于 §14 阶梯 |
| `legacy.css` 不同字号 | 4 个（12/13/15/17） | 3 个（12/13/16） |
| `legacy.html` 内联字号 | 8 个（11/11.5/12/12.5/13/13.5/14/15） | 5 个（11/12/13/14/16） |
| 被吸附的声明 | — | **脚本吸附 124 处**（其中 3 处落在此前 T3 未提交声明上；按 `git diff` 可归属本轮的可见变化为 **121 处**。明细：11.5→12 ×50、12.5→12 ×28、10.5→11 ×10、9→10 ×8、15→16 ×8、17→16 ×4、21→20 ×3、13.5→14 ×3、22→20 ×2、8→10 ×2、7/9.5→10 ×2、19→18、29/31→30、15.5→16 各 1） |
| 阶梯档位 | 未定义（§14 只写「稳定阶梯」） | 11 档：10/11/12/13/14/16/18/20/24/30/36（36 暂未使用） |
| 主区状态类文字 | 11px（`.status-pill`/`.s0-checks b`/`.s0-flow .flow-status`） | **12px**（复核 P2-5：状态/结论类文字不得停在 11px；10/11 只留给标签、图注与密集侧栏元信息） |

**映射口径**（与计划 §3 逐条一致，脚本唯一实现）：
`7,8,9,9.5→10`；`10.5→11`；`11.5→12`；`12.5→12`；`13.5→14`；`15,15.5,15?→16`；`17→16`；`19→18`；`21,22→20`；`29,31→30`。
13–14px 正文/表单口径按 §14:825 保持不变。

## 2 截图

| 文件 | 说明 |
|---|---|
| [`screens/before-1440-environment.png`](screens/before-1440-environment.png) | 吸附前（批次 1+2 之后） |
| [`screens/after-1440-environment.png`](screens/after-1440-environment.png) | 吸附后：标签 9→10px、说明 11.5→12px，层级更稳 |
| [`screens/after-1440-monitor.png`](screens/after-1440-monitor.png) | 运行监控（阶段/Agent 卡） |
| [`screens/after-1440-agent.png`](screens/after-1440-agent.png) | Agent 窗口（弹层字号同步） |

## 3 门（原始输出）

```
tests/test_ui_typography.py                 先红：首轮 2 failed, 1 passed（含 1 项用例自身解析缺陷，已修正）
                                            修正后 1 failed（16 个阶外 / 25 个不同字号）
                                            后绿：3 passed in 0.68s（扫描 355 处声明）
tests/browser（全量）                        178 passed in 208.71s
run_software_checks.sh --ignore=tests/browser  2002 passed, 3 deselected in 274.98s（exit 0）
check_doc_links.py                           missing=0，exit 0
```

**先红日志未落档**（本轮未保存原始输出）；判别性由独立复核以副本注入证明：
`font-size:11.5px`、`font:11.5px …`、HTML 内联 `font-size:11.5px` 三种写法均判红；
加固后另验：大写 `11.5PX` 判红、`font:1.1em` 与 `font-size:90%` 判红、注释内旧值不计入。

## 4 md5

```
5ad1552118f200e98f5a5339d6d01a59  screens/before-1440-environment.png
4db7ed984313007be9e733db3e9ed9fc  screens/after-1440-environment.png
f61285621f35d7943e93254762475dab  screens/after-1440-monitor.png
bb25b4165b0155753c501dc6d78c23a8  screens/after-1440-agent.png
```

## 5 复跑

```bash
cd loop
.venv/bin/python -m pytest -q tests/test_ui_typography.py
R=$PWD/..; PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser
```
