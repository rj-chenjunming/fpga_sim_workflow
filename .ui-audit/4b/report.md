# 批次 4 · B/A 实现报告（`.ui-audit/4b/report.md`）

> owner `batch4-owner`｜写权：`loop/web/{index.html,app.js,s0.js,node-detail.js}` + 2 个新测试 + `.ui-audit/4b/**`；C 项与 `app.css` 由 Lead 落。
> 计划：[`doc/plans/2026-10-30-ui-batch4.md`](../../doc/plans/2026-10-30-ui-batch4.md)。**状态：B 完成 / A 完成（代码+测试+浏览器面）；C 项不在本报告。**

## 1 B · GATE-1 文案中性化（完成）

- 只改 3 处文案，不加枚举、不映射 G1、不动 `kb/**` 与后端：
  ① `index.html:112` `#s0SubmitHint` →「准出与切换由服务端判定；准备完成后仍需 S0-b 接口复核」
  ② `index.html:161` `#s0Blockers` →「完成 S0 两段（含 S0-b 接口复核与准出判定）后才能进入新版执行。」
  ③ `s0.js:109` busy 恢复串 → 与 ① **逐字相同**（用例断言二者相等，防双写漂移）
- `grep -rn GATE-1 loop/web/` = **0**。`GATE-1 ↔ G1` 映射**未决**，界面只是不再宣称。
- 新用例 `loop/tests/test_ui_gate_copy.py`（6 条）：归零 / 不许自造 `GATE-\d` / 中性文案三处 / 双写相等 /
  `kb_lib.GATE_IDS·GATE_DECISIONS` 只读 `ast` 断言原值 / `kb_lib.py` 无 `GATE-1`。
- 红→绿：[`red-gate-copy.txt`](red-gate-copy.txt)`4 failed,2 passed` → [`green-gate-copy.txt`](green-gate-copy.txt)`6 passed`。

## 2 A · 图标 sprite（完成）

- `index.html` `<body>` 首插隐藏内联 `#iconSprite`（**18** 个 `<symbol viewBox="0 0 16 16">`，**无 `xmlns`**）+ `#iconTpl`；样式只在 `app.css` 的 `.icon` 写一次。
- `app.js`/`s0.js`/`node-detail.js` 各加 5 行 `iconNode()`：克隆 `#iconTpl` + 改 `<use href>`；无 `createElementNS`、无命名空间 URI。
- **替换 41 处**：index 15 · app 14 · s0 7 · node-detail 5；`legacy.html` 12 处**不迁移**（登记例外）。
- 一符一义：`◇`→`icon-gate`/`icon-empty`；`▸`→`icon-chevron`；`↗`→`icon-external`/`icon-panel`；`×`/`✕`→`icon-close`/`icon-fail`；`→` 只给**可点击动作**换 `icon-next`（正文流程箭头保留）。
- 几何不回退（A10）：nav / `.stage-chev` / `.dp-icon` / `.snode .sb` / `.s0-boundary` **保留原 `<span>` 包裹**，原 19px 槽宽、`.stage.open`/`.snode.gate .sb span` 的旋转、`.rail-entry>span:last-child{margin-left:auto}` 全不动。
- 与 icons.md 的 3 处有意偏离（少改 Lead 文件、不降可访问性）：① 不引入 `.icon-fill`/`.sr-only` —— `icon-running` 用符号内 `fill="currentColor" stroke="none"`（`<use>` 影子树里文档选择器不匹配），状态语义由**已有文本/`aria-label`** 承担；② 不改 `.nav-icon` 的 `text-align`；③ `.s0-boundary` 箭头仍套 `<span>`，原 `>span{font-size:18px}` 不必删。
- 新用例 `loop/tests/test_ui_icons.py`（10 条）：sprite 根/模板、symbol 表==消费者集合、`viewBox`、无死 symbol、无悬空 `use`（含 `iconNode("x")` 与 `labelWithIcon(…,"x")`）、码位归零（`✓✕▸◇↑•⌄▧⊞◴▣▢×↗`）、白名单具名（`→ … ! ●`）、零外链（`xmlns`/`http(s)://`/`createElementNS`/`url(`）。
- 红→绿：[`red-icons.txt`](red-icons.txt)`6 failed,4 passed` → [`green-icons.txt`](green-icons.txt)`10 passed`。
- 落盘 md5（3B 之后复核，证明 3B 没碰这 4 个文件）：`index.html 0eccb188…`/`app.js 9d403aba…`/`s0.js 66b0136e…`/`node-detail.js 5ea59e2c…`；`git diff --stat` = `143/138/590/34`（与我收工时刻逐字一致）。

## 3 三处偏差（Lead 已认可）

1. **node-detail 5 处而非 3**：另 2 处（680「去闸门视图确认并提交 →」、1564「查看闸门材料（同源）→」）与 `app.js:3158` 完全同型，icons.md 漏记；不补则同弹窗两按钮一个 SVG 一个字形。
2. **18 symbol 而非 22**：`icon-back/refresh/warn/blocked` 只有 `legacy.html` 有消费者，legacy 本轮不迁移 ⇒ 按 AGENTS §2 纪律 4（无消费者资产不得保留）不入 sprite；用例 `DEFERRED_WITH_LEGACY` fail-closed 登记，迁移 legacy 时成对添加。
3. `app.css` 的图标/死规则不在我写权内 ⇒ 只出清单，由 Lead 落（已落，见 §4）。

## 4 `app.css` 清单：**已落地**（Lead，`md5 d75422b5…`（mtime 15:17:42，**早于**我 15:19 的截图 ⇒ 截图即最终态），已 `sed` 与清单逐字比对）

```css
.icon{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:-3px;
  fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.icon-30{width:30px;height:30px;vertical-align:baseline}
.empty .icon-30{display:block;width:58px;height:58px;padding:13px;box-sizing:border-box;
  margin:0 auto 20px;border:1px solid var(--line-soft);border-radius:16px;background:var(--bg);color:var(--text-5)}
```
+ 删 `.empty:before`、`.aw-detail summary:before`/`[open]:before`、`.nav-icon{font-size:20px;line-height:1}`、760 断点 `.nav-icon{font-size:16px}`、`.stage-chev{font-size:11px}`。
**3B 令牌化对本项的影响**：图标描边用 `currentColor`，**不受令牌化影响**；空态框 3 个字面量已映射到 `--line-soft/--bg/--text-5`（Δ≤9）。

## 5 验证数字（原样复制）

- 软件层相关面（可写数据根）**146 passed, 2 failed** —— 2 条均为 `tests/test_ui_css_structure.py`（当时 `app.css` F14 未收敛；Lead 收口后转绿）。原始输出 [`software-tests.txt`](software-tests.txt)。
- 浏览器面（Lead 交还 Chromium 后本轮亲自跑）：`test_web_layout.py` + `test_ui_visual_20261030.py` = **24 passed in 23.55s**（[`browser-tests.txt`](browser-tests.txt)）。
- typography 扫描数 = **352**（门槛 ≥300；低于我预估 369，因为 3C 的 F14 合并同时删了大量重复 `font-size`，非本项多删）。
- 运行时读数（[`measure-4b.json`](measure-4b.json)）：`.icon` = 16×16 / `fill:none` / `stroke-width:1.5px`；空态插图 = 1 个 58×58；三视口 `.seg button` 44、`.rail-entry` 64、`.nav-icon` 内层 svg 16×16、无水平溢出；`#gateMaterial` y = **828.3 / 832.3 / 811.9**、闸门窗格 **420 / 600 / 780**（C 项，仅记录）。
- 裸跑 `test_api` 的 `OSError [Errno 30]` = ENV_ROOT 只读缺件（Lead 已确认），非缺陷。
- 自查并修掉**自己引入的回归**：`index.html` 注释里裸写 `app.js`，令 `html.index("app.js")` 提前命中，红了 `test_gate_session.py:125` / `test_capability_format.py:80`；改措辞后绿 ⇒ `index.html` 不得出现裸 `app.js`/`agent-window.js`。

## 6 交付物 / 未做

- 截图 12 张（`shots/`，最终态无注入样式）：`s0|run|gate-{1280x720,1440x900,1920x1080}.png`、`agent-window-1440x900.png`、`final-node-detail-1440x900.png`、`final-empty-1440x900.png`；目检与逐项结论见 [`visual-check.md`](visual-check.md)。历史 `prelim-*` 是「样式未落地时注入自证」的留档，不作交付。
- **未做/不声称**：① `legacy.html` 12 处图标未迁移，`⚠/⛔` 仍依赖 emoji 字体；② `●`（`app.js:806`）不 sprite 化（写 `document.title`，唯一文本图标例外）；③ `GATE-1 ↔ G1` 映射未决；④ 4 个 legacy-only symbol 未落；⑤ 窄屏（≤760px）与 Firefox/Safari **未测**；⑥ 全量浏览器门/软件层门由 Lead 跑，我没有跑、也不代跑数字。
