# 批次 4 交接（≤50 行）· 三项设计已完成，待人裁/Lead 改规格后实现

## 改动文件清单
- **A 图标 sprite**（`.ui-audit/4/icons.md`，22 个 symbol/23 码位/54 处）：`index.html`（sprite+15 处）、`app.js`（14 处）、`s0.js`（7）、`node-detail.js`（3）、`app.css`（.icon 等 6 条规则；`.aw-detail` 的 ▸▾ 为死规则→删）。**legacy.html 12 处不迁移**（登记例外）。
- **B GATE-1 中性化**（`gate-identity.md`）：仅 `index.html:87`、`index.html:136`、`s0.js:77` 三行文案 + 新增 `tests/test_ui_gate_copy.py`。不改 kb/枚举/判据/后端。
- **C 常数放宽**（`gate-pane-height.md`）：`WEB_UI_SPEC.md` §14 一行公式、`app.css` `.gate-pane` 的 token、`test_gate_panes.py:17-19` 三常量、STATUS。

## 建议实现顺序
1. **B（最小、纯文案）** → 2. **C（Lead 先改 §14 → 改测试常量先红 → 改 CSS → 绿）** → 3. **A（最大，最后做；避开 3C 正在改的 app.css）**。
   理由：B 无依赖；C 动测试常量必须先有规格授权；A 与 3C 同文件冲突面最大。

## 会碰到的测试
- B：**0 处**（`GATE-1` 在 `tests/` 里 0 命中）；`#s0Blockers` 的两条断言走服务端 blockers 路径，不受影响。
- C：`test_gate_panes.py:16-19` 必须改；`:125-132` 自动跟随；`test_pane_scroll.py` 不受影响（它只看 `gate-pane` class 计数=2）。
- A：**图标字符在 tests 里 0 断言**；真正的边是四条：`test_web_smoke.py:31/38`+`test_api.py:59`（`http://` 零出现 ⇒ **禁止 xmlns / 禁止 createElementNS**）、`test_ui_visual_20261030.py:261`（`url(` 零出现 ⇒ 伪元素图标只能删或改结构）、`test_ui_typography.py`（≥300 声明、不得新增字号）、A10 侧栏几何（`.seg button` 实测 44×216、`.rail-entry` 64）。
   建议新增 `test_ui_icons.py`（symbol↔use 对应、viewBox、码位归零、无死符号）。

## 必须由人裁 / Lead 做的
1. **C**：改 §14 公式 = 改契约承诺，**Lead 改规格后**才能动 CSS 与测试常量。
2. **C 的口径确认**：推荐 `clamp(300px, calc(100dvh - 300px), 860px)`（720/900/1080 → 420/600/780）；**它不能解决 1280×720 首屏进入**（`#gateMaterial.y` 与常数无关，缺口 108.3px，需结构折叠=人裁已列"非当前阶段"）。请人裁确认"放宽只为窗格余量与修 1080 的 20px 截断"。
3. **B 的措辞**：「S0-b 接口复核」vs「执行前检查（S0-b）」二选一；**GATE-1↔G1 映射仍待裁**，本批次只中性化。
4. **A 的 legacy 范围**：本设计建议不动 `legacy.html`（则 `⚠/⛔` 的 emoji 字体依赖仍在，须进 STATUS 未做清单）；若要求覆盖需复制 sprite 并逐字节一致。
5. **STATUS 新区段**（§142 起）：Lead 唯一写者；需写明"1280 首屏未解决""GATE-1 映射未决""legacy 未迁移"。

## 结论的可信度分层
- **有运行时读数支撑**（`.ui-audit/measure.json`，Chromium 156，受控夹具）：三视口 `#gateMaterial/#gatePanel` 的 y/h/bottom、token 解析值=实测窗格高（380/560/720）、页面 `scrollHeight`、`.seg button`/`.rail-entry` 盒。
- **由读数+CSS 边距推导**（±几 px）：四段流程卡高 493.7、上方链分解、压掉 108.3px、A1/A2 的 `scrollHeight` 预测值（+40/+40/+60）、A3 的 `y=386.6`。
- **静态推断（无运行时验证）**：所有 SVG path 草图、`.icon` CSS 效果、图标替换后布局不变、`<use>` 在 Chromium 156 的渲染——**均未跑浏览器**，实现后必须目检+跑门。
- **测量缺口（诚实登记）**：`measure_gate_fold` 未采集两栏 `scrollHeight` ⇒ "放宽多少才不滚"无法精确算，需扩 `measure.py` 重测。
- **并发风险**：`app.css` 正被 3C（F14 合并）反复改写（10:03→13:48→13:53，-1171 行，md5 `ef5b3893…`→`7d9e3ace…`），本文行号是快照；A/C 落地前先确认 3C 已收口，行号一律按选择器 grep。
