# S8j 证据档（2026-10-29）：窗口实例区 = 执行结果/状态 + 打开真实用例（移除 iframe）

> 冻结：本目录 `444`（文件）/ `555`（目录），md5 记在**目录之外** `doc/evidence/DSH_S8J_20261029.md5`。
> Lead 实现与验证同一人 ⇒ **不声称独立复核**。
> 契约：[SPEC-REV-17 §2](../../spec/SPEC-REV-17-20261029.md)（= REV-16 新增 **§6.4**）+ [AGENT_WINDOW_SPEC](../../spec/AGENT_WINDOW_SPEC.md) 指针。

## 0 裁决来源

S8b/S8g 真机实测：反代只透传 HTTP，DSH 的 `WS /api/remote.mux` 仍 405（[REV-16 §9-2](../../spec/SPEC-REV-16-20261028.md) 仍开）
⇒ iframe 内画面恒为空会话列表，人看不到、点不动。2026-10-29 人裁决：

> 「内嵌显示其实没那么必要，只要有一个结果展示就行，具体信息可以通过跳转到实例窗口查看；
> 内嵌那块换成一段执行结果/状态，再加一个跳转真实用例的按键即可。」

## 1 交付内容

| 项 | 落点 | 判据 |
|---|---|---|
| 取消内嵌面 | `web/index.html` 删 `#awEmbedFrame`/`#awEmbedFallback`/`#awEmbedNewTab`；`web/agent-window.js` 删内嵌探测（`probeInstance`）、8 s 加载超时、降级块 | `raw/no-embed-surface.txt`：`iframe/object/embed` 与探测函数源码 **0 命中** |
| 执行结果块 | `#awEmbedFacts`：`session-copy.facts` 的 `count`/`len(records)`/`len(errors)`/`start→end`/`prune` + `bytes`/`truncated` | 数字逐字来自服务端；缺字段「未知」；`0` 显示 0；不可用给 `session_*` 中文映射且不出 0 假数 |
| 打开真实用例 | `#awEmbedDirect`「打开真实用例（实例窗口）↗」：`href=direct_url`，缺则回退反代 `url`，皆无 ⇒ 隐藏 | `title` 披露"token 短暂进地址栏、仅本机可用"；回退时披露实时流未接通 |
| 自动读取 | 打开/切节点/切 attempt/刷新各读一次 `instance` + `session-copy`；「刷新执行结果」重读并展开原始事实块 | 两端点**最新一次**请求都带 `?attempt=` |
| 契约 | `doc/spec/SPEC-REV-17-20261029.md`、`doc/plans/2026-10-29-s8-review-and-d3.md` §8.1、`doc/STATUS.md` §133 | 规格先于实现；REV-16/`OBS-01`–`OBS-08` 原文不改写 |

## 2 验证（`raw/gates.txt` 是命令输出原文）

| 门 | 结果 | 归因 |
|---|---|---|
| 隔离复核（worktree，仅本片） | 红 `10 failed, 1 passed` → 绿 `24 passed`；前端契约 `19 passed` | **可归因**：HEAD 树 + 只回放本片改动 |
| 浏览器门（主树） | `146 passed in 162.08s` | 主树另含并发切片的 6 条用例 |
| 单测门（主树） | `5 failed, 1867 passed, 1 warning, 145 errors` | 3 = 既有数据根/归档失败；2 = **并发切片**的 `index.html` 注释命中 `html.index("app.js")`（同一用例在隔离树上 19 passed） |
| 文档门 | `65 passed` | —— |
| 端到端（drill） | phase `1/2/3/4/4b/5` 全 `rc=0`，`=> ALL PASS` | —— |

## 3 复放

```bash
cd loop
# 本片界面契约（24 条；含 11 条 S8j）
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp \
  .venv/bin/python -m pytest -q tests/browser/test_s4_projection_ui.py
```

隔离复现（红/绿可归因）：

```bash
git worktree add -f .s8j-verify HEAD
cp loop/tests/browser/test_s4_projection_ui.py .s8j-verify/loop/tests/browser/     # 先红
cd .s8j-verify/loop && ../../loop/.venv/bin/python -m pytest -q tests/browser/test_s4_projection_ui.py -k s8j
# 再把本片 web 四项改动回放进去 → 24 passed
```

## 4 不声称

- **不声称内嵌可用**：本片是**取消**内嵌路径，不是修好它；`WS /api/remote.mux` 仍 405（§9-2 仍开）。
- **不声称远程浏览器可用**：`direct_url` 仍是 `127.0.0.1:<port>`（REV-16 §6.1 第 5 条硬限制）。
- **不声称会话原文可导出**：结果块渲染的是 `session_log_facts`（解析事实），§9-11 仍开。
- **不声称独立复核**；未推送（`origin/main` 之外本地提交）。
- 反代转发面（R1–R20、token 脱敏、SSE 读超时口径）**未删**，只是当前无界面消费者（REV-17 §5 已登记）。
