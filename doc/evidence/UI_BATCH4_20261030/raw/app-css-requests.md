# 批次 4 · A 项：`app.css` 需要 Lead 落地的改动（逐条）· **已全部落地（2026-10-30 15:0x）**

> **落地状态：DONE。** Lead 在 3C 合并后的 `app.css`（md5 `d75422b5ecdc15fd26d9114d34369b5c`）里一次性落齐 5 条：
> `.icon`（含分节注释「图标…批次 4 A」）、`.icon-30` + `.empty .icon-30`、删 `.empty:before`、
> 删 `.aw-detail summary:before`/`[open] summary:before`、删 `.nav-icon{font-size,line-height}` 与
> 760 断点 `.nav-icon{font-size}` 与 `.stage-chev{font-size}`。落地文本与本文清单**逐字一致**（已 `sed` 比对）。
> 另：同一批 Lead 落了 C 项 `--gate-pane-max-h:clamp(300px, calc(100dvh - 300px), 860px)`（规格 §14 先改），
> 所以闸门视图窗格变高是**预期**，与本项无关。
>
> 下面是**当初的请求清单**（保留原文作为契约留痕；§7 的复核项对 browser 面仍有效）。
>
> **实测复核**：落地后 `test_ui_typography.py` 扫描数 = **352**（门槛 ≥300；比我预估的 369 更低，
> 因为 3C 的 F14 合并同时删掉了大量重复 `font-size` 声明——不是本项多删）。落地后
> `test_ui_typography` / `test_ui_icons` / `test_ui_gate_copy` / `test_ui_css_structure` 合计 **21 passed**。

---


> 写权：`loop/web/app.css` 是 Lead 的；实现 owner 只改 `index.html/app.js/s0.js/node-detail.js`。
> 下面每条都写「选择器 / 规则内容 / 理由 / 不做的后果」。行号是 2026-10-30 14:1x 的 `app.css`（md5 见 §4），
> **落地时按选择器 grep 定位，不要信行号**（3C 合并期间行号漂移过）。
> 实测前提：`.icon` 未落地时，39 处 `<use>` 图标会按浏览器默认 `fill:black; stroke:none` 渲染成
> **黑色实心块、且无 16px 尺寸约束**（`<svg>` 无 width/height 时按容器宽度撑开）。**`#1` 是硬依赖。**

---

## 1 必须新增：`.icon`（1 条，硬依赖）

```css
/* ---------- 图标（WEB_UI_SPEC §14「资产」：本地内联 sprite，零外链、零字体依赖） ---------- */
.icon{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:-3px;
  fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
```

- **理由**：16×16 是 `viewBox="0 0 16 16"` 的 1:1 尺寸；`fill:none + stroke:currentColor` 是所有 22 个
  symbol 的共同描边口径（符号内不重复声明，只此一处）；`currentColor` 让图标自动继承父元素颜色
  （`.nav-icon{color:#91ad9b}` / `.snode .sb` / `.btn-primary` 全部免改）。
- **不加 `font-size`**：字号必须留在 §14 的 11 档内（A14 判定），图标尺寸只走 `width/height`。
- **不写 `url(`/`@font-face`/`mask`**：`tests/browser/test_ui_visual_20261030.py:261` 卡零 `url(`。
- **不做**：`.icon{position:relative;top:...}` 之类定位微调——`vertical-align:-3px` 对 `.btn`(flex) 无效但无害，
  对行内文本（如 `#btnDirUp` 的「上级」、`.s0-boundary`）负责基线对齐。

## 2 必须新增：空态插图 `.icon-30`（替代被删的 `.empty:before`）

```css
.icon-30{width:30px;height:30px;vertical-align:baseline}
.empty .icon-30{display:block;width:58px;height:58px;padding:13px;box-sizing:border-box;
  margin:0 auto 20px;border:1px solid #d6e3d8;border-radius:16px;background:#f0f6f1;color:#60846a}
```

- **理由**：`.empty:before` 的 `◇` 是**伪元素**，`<use>` 放不进去（CSS 图标方案被 `url(` 断言否决）。
  结构侧已改：`index.html` 的静态 `#runEmpty .empty` 与 `app.js` 的 `h("div","empty")` 现在都插一个
  `<svg class="icon icon-30"><use href="#icon-empty"/></svg>` 作首子节点。
- **58×58 的圆角框逐像素保留**：全局有 `*{box-sizing:border-box}`，故 `58 − 2（边框）− 26（上下 padding 各 13）
  = 30px` 内容盒正好放 30px 图标，外框仍是 58×58（与原 `:before` 的 `width/height:58px` 完全一致，**实测
  Chromium 里 `getBoundingClientRect()` = 58×58**）。
- 颜色沿用原伪元素的 4 个值（`#d6e3d8` 边框 / `#f0f6f1` 底 / `#60846a` 前景），未新增新色值。

## 3 必须删除：`.empty:before`（不删会双图标）

```css
/* 现状（app.css:516 一带，按选择器 grep） */
.empty:before{content:"◇";display:grid;place-items:center;margin:0 auto 20px;width:58px;height:58px;
  border:1px solid #d6e3d8;border-radius:16px;background:#f0f6f1;color:#60846a;font-size:30px}
```

- **理由**：内容已由 §2 的结构节点承担；保留就是「◇ + 内联图标」两个插图叠着出现，
  且 `◇` 是 `◇` 一符多义（导航「人工闸门」vs 空态插图）要拆掉的那一半。
- **副作用（预期）**：typography 扫描数 −1（`font-size:30px` 消失）。

## 4 必须删除：`.aw-detail` 的 `▸/▾` 伪元素（死规则）

```css
.aw-detail summary:before{content:'▸';color:#799a8c}      /* app.css:382 */
.aw-detail[open] summary:before{content:'▾'}              /* app.css:383 */
```

- **理由**：`grep -rn aw-detail loop/web/` 只命中 `app.css`（无 HTML/JS 消费者），本来就是死规则；
  同时它们是 `▸/▾` 两个码位在组件层的最后残留，删掉后 `▸/▾` 彻底退出界面。
  （若 3C 已按死声明删过，本条跳过。）

## 5 建议删除：3 条已失效的 `font-size`（图标不再靠字号撑尺寸）

| 选择器（grep 定位） | 现在 | 建议 | 理由 |
|---|---|---|---|
| `.nav-icon{width:19px;font-size:20px;line-height:1;text-align:center;color:#91ad9b}` | 4 个 nav 图标已是 `<svg class="icon">`（套在原 `.nav-icon` span 里） | 删 `font-size:20px;line-height:1`，其余**保留**（`width:19px` 是 `.seg button` 44px 高的输入；`text-align:center` 仍居中 svg） | 字号不再参与图标尺寸；保留 19px 槽宽 ⇒ 侧栏几何不变（A10） |
| `@media(max-width:760px){… .nav-icon{font-size:16px;width:16px} …}` | 同上 | 删 `font-size:16px`，保留 `width:16px` | 同上 |
| `.stage-chev{…;font-size:11px;…;display:inline-block}` | 展开指示已是 `<svg class="icon">`（套在 `.stage-chev` span 里） | 删 `font-size:11px`；`display:inline-block` 与 `.stage.open .stage-chev{transform:rotate(90deg)}` **保留** | 旋转动效不变（只动 transform，符合 §14「动效」）；字号只为撑 `▸` 字形 |

- **合计影响（实测口径）**：改前 `app.css` 当前基线 **373**（`tests/test_ui_typography.py` 的 `scan()` 实测），
  上面 4 条合计 −4 ⇒ 落地后约 **369**，门槛 ≥300，安全。
- **可以不改**（保留也无害，只是空声明）：`.snode .sb{font-size:11px;font-weight:700}`（状态泡已是 svg）、
  `.s0-boundary>span{font-size:18px}`（span 包裹仍在，字号不再影响其中 svg）、`.dp-icon{text-align:center}`
  （`.dp-item` 是 flex，居中由 `align-items` 负责）。

## 6 明确**不要**改的（防止顺手改动把几何/判据弄坏）

1. `.stage.open .stage-chev{transform:rotate(90deg)}` —— 图标是「右向 chevron」，旋转 90° 表示展开，语义未变。
2. `.snode.gate .sb span{transform:rotate(-45deg);display:block}` —— 图标仍套在 `span` 里，
   正是为了保留闸门菱形泡的反向旋转（`app.js` 的 `nodeEl()` 仍用 `h("span")` 包裹）。
3. `.stage-idx{width:27px;height:27px;display:flex;place-items:center}`、`.s0-checks li>span{display:grid;place-items:center}`、
   `.avatar{display:flex;align-items:center;justify-content:center}` —— 三者已是居中容器，svg 直接放进去即居中，不要加新规则。
4. `.rail-entry>span:last-child{margin-left:auto}` —— `#btnS0` 的折叠指示仍在外层 `<span>` 里（内联 `style="transform:rotate(90deg)"`），
   该选择器必须继续匹配；不要把这处结构改成裸 `<svg>`。
5. **不要**新增任何 `font-size`（A14）；**不要**引入 `url(`/`mask`/`@font-face`（A13/A14 与零外链）。
6. **不要**改 `.card-body gate-pane` 的两个 class 顺序（`tests/test_pane_scroll.py:110` 计数 `== 2`）。

---

## 7 落地后我需要复核的 3 件事（Lead 落完请 ping 我）

1. 三视口截图目检：图标是否 16px、是否空心描边、颜色是否跟随父元素、有无空框/错位；
2. `.empty` 是否只剩 1 个插图（58×58 圆角框）；
3. `cd loop && .venv/bin/python -m pytest -q tests/test_ui_typography.py` 实际扫描数（预期 ≈369：373 − 4；门槛 ≥300）。
