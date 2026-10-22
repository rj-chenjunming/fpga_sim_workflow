# F14-b 追加切片证据：C / D / E 与终态（2026-10-22）

> 本文件是**新增证据**，用于承载 F14-b 后三个组件切片（C S0、D 运行/闸门、E Agent+旧页）的结果。
> 背景：A/A2/B 的证据已冻结在 `AFTER-VERIFY.md`（MD5 `9a388b5cb5038d4510f1da7021513171`）；
> C/D 结果曾被就地追加到该文件（流程偏差，见 [CORRECTIONS-F14.md](CORRECTIONS-F14.md) §4），
> 已把该文件恢复为冻结内容，C/D/E 结果改记于此。执行者：Lead 整理，实现与验证由 `web-refactor` 完成；
> 同一执行者实施+验证，**不是独立视觉评审**。

## 1 切片与提交

| 切片 | commit | 内容 | 声明/规则 | 139 组合计算样式差异 | tests/browser | 冻结截图 |
|---|---|---|---|---|---|---|
| C S0 | `f2d39fe` | `.s0-*`/`.phase-*`/`.hero-*`/`.diagram-*`/`.eyebrow`/`.section-index`/`.form-*`/`#s0Report` | 88 声明 + 12 规则 | 0 | `41 passed in 54.07s` | 42/42 MD5 相同 |
| D 运行/闸门 | `b4df6e6` | `.run-head`/`.status-pill`/`.stage*`/`.snode*`/`.agents`/`.agent*`/`.avatar*`/`.count*`/`.blocker`/`.sev`/`.option`/`.kv`/`.diff-item`/`.gate-*`/`.ev*`/`.refs`/`.log-pre`/`.spinner`/`.pulse` | 81 声明 + 8 规则 | 0 | `41 passed in 62.71s` | 42/42 MD5 相同 |
| E Agent+旧页 | `7ecbb9c` | `.agent-window`/`.aw-*`；`legacy.css` 无可证冗余（未改） | 60 声明 + 4 规则 | 0 | `41 passed` | 42/42 MD5 相同 |

原始日志：`raw/f14b-sliceC-verify.log`、`raw/f14b-sliceC-pytest.log`、`raw/f14b-sliceC-screens.txt`、
`raw/f14b-sliceD-verify.log`、`raw/f14b-sliceD-pytest.log`、`raw/f14b-sliceD-screens.txt`、
`raw/f14b-sliceE-verify.log`、`raw/f14b-sliceE-pytest.log`、`raw/f14b-sliceE-screens.txt`。
**注意**：以上日志由 v1 校验工具产出（固定 149 项属性清单），终态判据以 v2 全属性工具复跑为准（§4）。

## 2 终态静态事实（Lead 实测，`loop/spikes/css_inventory.py` + `git show`）

| 项 | F14-a 基线（`9ebb986`） | 终态 | 命令 |
|---|---|---|---|
| `app.css` 字节 | `57834` | `50069` | `git show 9ebb986:loop/web/app.css \| wc -c`；`wc -c loop/web/app.css` |
| `app.css` 规则数 | 795 | **751** | `loop/spikes/css_inventory.py` |
| 媒体查询块 | 14 | **13**（仅删重复 reduce 块；两份 760 保留） | 同上 |
| `!important` 声明数 | app 6 / legacy 2 / tokens 0 | app **4** / legacy 2 / tokens 0（行数 app 3→2） | `grep -o "!important" loop/web/*.css \| wc -l` |
| 新增 `!important` | — | **0** | diff 检查 |
| `legacy.css` / `tokens.css` | — | 未改 | 同上 |
| JS / HTML / `tests/**` | — | 未改（F14 只动 CSS） | 复核者 `git archive` 比对 |

## 3 被否决/回退的改动（与冻结文件一致，不重复展开）

- 合并两份 `@media(max-width:760px)`：**否决**（9 个（宽度,状态）组合出现计算样式变化，元素数 52/52/111）。
- 颜色令牌化 3 条：**未采用**（理由见 [CORRECTIONS-F14.md](CORRECTIONS-F14.md) §1；原「非等价」结论已撤回）。
- 其余切片均满足「零计算样式差异 + 42/42 截图逐字节相同 + 41 条浏览器用例无 skip」。

## 4 终态复验（Lead 执行）与工具限制

- **Lead 复跑 `tests/browser`（终态 CSS）**：`41 passed in 55.92s`（0 skip / 0 error）。
- **CSS 静态终态**（`loop/spikes/css_inventory.py` + `git show`）：见 §2。
- **全属性指纹工具（v2）未采用**：对照实验（同一份 CSS 放两个目录做 before/after）下 v2 仍报
  逐元素差异（`1280/run` 1056/1056、`1280/s0` 665/665），属系统性误报 ⇒ 不能作等价判据，
  已恢复提交版 v1（md5 `346d81bb7614c64817fa9fc9d14b018a`）。详见
  [CORRECTIONS-F14.md](CORRECTIONS-F14.md) §2。
- 因此：**终态 139 组合计算样式等价没有由 Lead 独立重新建立**；现有 C/D/E「139 组合零差异」是
  v1 工具日志（`raw/f14b-slice{C,D,E}-verify.log`）。A/A2/B 的删除声明另有独立复核者的静态支配性
  证明；C/D/E 的静态支配性证明登记为**未完成项**（STATUS §41）。

## 5 未完成（下一轮直接接续）

- **F05-b/c 未开始**：运行/Agent/计数渲染提取、配置/目录浏览提取。前置（浏览器特征集、R5/`agent-window.js` 稳定）
  已具备；本轮时间盒内不启动，以免在无独立复核时扩大改动面。
- 人工视觉评审、Chrome UI 真实 125%/150% 缩放、`:hover`/`:focus` 动态伪类的计算样式对照、真实服务端数据：
  **未验证**，不得据本阶段声称视觉验收通过。
- `legacy.html` 内联深色主题（154 行）不在本轮可改范围，仅登记。
