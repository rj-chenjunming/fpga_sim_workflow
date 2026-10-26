# 侧栏可达性缺陷：实施计划（2026-10-26）

状态：**计划 + 已定位根因；实施按 SpecDD 顺序执行**。依据
[WEB_UI_SPEC §14 侧栏可达性](../spec/WEB_UI_SPEC.md)。
写权：`loop/web/app.css`、`loop/tests/browser/test_web_layout.py`（实现 owner，同一时刻一人）；
`doc/spec/WEB_UI_SPEC.md` 与 `doc/STATUS.md` 属 Lead 契约/数字写权。

## 0 缺陷（来自 STATUS §74.7 未关闭项）

`loop/tests/browser/test_web_layout.py` 4 failed / 5 passed。§74.4 记为「侧栏 `.run-item` 在
1280/1440/1920 视口内、滚动也无法进入」，**归因不准确**：宽度不是变量，**视口高度**才是。
本轮实测更正如下（命令输出见 §4）。

### 根因 1：sticky 视口高侧栏 + 内容溢出 + 无自身滚动

`loop/web/app.css:494` 把侧栏钉成固定视口高：

```css
aside{width:244px;flex:0 0 244px;…;position:sticky;top:72px;
      height:calc(100vh - 72px);align-self:flex-start}
```

但侧栏内容高度是自适应的：`.rail-top` + `#btnNew` + 4 个 `#viewSeg` 视图 tab +
「在等我」+ `.history-label` + `.run-list`（`min-height:80px`）+ `.rail-foot`。
窄高视口下这些固定部分本身就超过可用高度，`.run-list` 的 `min-height:80px` 又不能压缩
⇒ flex 容器溢出。而 `aside` 的 `overflow` 是默认 `visible`，溢出内容被**画在 sticky 盒之外**；
sticky 又让页面滚动无法把它带回视口 ⇒ 下级条目（最近运行、rail-foot）**永久不可点击**。

实测（1440×720，`scrollY=0`）：

| 量 | 修复前 | 修复后 |
|---|---|---|
| `aside` clientHeight / scrollHeight | 648 / **838** | 648 / 838 |
| `.run-item` A 包围盒 top–bottom | 734–801 | 653–720 |
| `scrollIntoView` 之后 top | **734（一分不动）** | 653 |
| 包围盒完整落在视口内 | **否** | 是 |
| `locator.click()` | 30 s 超时「outside of the viewport」 | 成功 |

> 视口高 1000 时侧栏内容（至 y≈900）装得下，因此**三个只设宽度、高度写死 1000 的用例一直是通过的**，
> 缺陷被默认视口 `1280×720`（Playwright `new_page()` 默认值）的用例暴露。§74.4 把它记成
> 「1280/1440/1920 视口外」是误判，`assert_fits` 只查横向，也查不到纵向可达性。

### 根因 2：`page.url` 拼接把文件名拼到 hash 后面（测试缺陷，非产品缺陷）

`test_web_layout.py:156` 写 `page.goto(page.url + 'legacy.html')`。前端把当前视图同步进 URL
（`session-url.js`），实测 `page.url == "http://127.0.0.1:37051/#view=s0"`
⇒ 拼成 `"…/#view=s0legacy.html"`，变成**同页 hash 跳转，根本没导航**，因此
`.back-workspace` 永远找不到（Aria 快照里仍是主工作台）。
产品侧无缺陷：`legacy.html` 的 `<a href="legacy.html">` 与 index 的 `#lnkLegacy` 都是相对链接，
点击会替换整个 path+hash。

## 1 切片

| # | 切片 | 落点 | 验证门 |
|---|---|---|---|
| 1 | 契约：侧栏可达性判据 A10 + §14 增补 | `doc/spec/WEB_UI_SPEC.md` | 文档门 |
| 2 | 先红：`assert_reachable` helper + 侧栏入口可达性用例；验收视口改为 (宽,高) 对 | `tests/browser/test_web_layout.py` | 浏览器门（先看红） |
| 3 | 修根因 1：`aside` 自身可滚动（`overflow:hidden auto`） | `web/app.css:494` | 浏览器门（转绿） |
| 4 | 修根因 2：用 `urljoin` 构造 legacy 目标 URL | `tests/browser/test_web_layout.py` | 浏览器门 |
| 5 | 实测与登记 | `doc/STATUS.md` 新节 | 四道门按 §4 记录 |

切片 2/3 是同一缺陷的红-绿对；切片 4 独立（纯测试缺陷，不改产品行为），分开提交。

## 2 不做什么

- 不重排侧栏信息层级、不改视觉（`.rail-foot` 仍由 `.run-list{flex:1}` 顶到底部）。
- 不引入 JS 测量/注入滚动条，纯 CSS。
- 不动 `.run-list` 的 `overflow:auto;flex:1` 语义（视觉设计基线，`mockup.html` 一致）。
- 不把浏览器用例并入全量单测门（单跑约 60 s，并入后受 30 s 超时叠加拖到 20 min+，见 STATUS §72）。

## 3 环境限制

浏览器用例需 Chromium：`PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers`（120 MiB
`chromium-1248`）+ 可写 `HOME`/`TMPDIR`。缺浏览器时整文件 setup error，属环境缺件，
**不得记为通过**。视口可达性是纯 DOM 判定，无内网依赖；但截图视觉核对需人工。

## 4 复现与红证据命令

```bash
cd loop
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers \
HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp \
.venv/bin/python -m pytest -q tests/browser/test_web_layout.py
```

## 5 回退

纯 CSS 单属性 + 单文件测试改动，回退即 `git revert` 对应提交；无可逆数据变更，
不影响任何服务端契约、闸门授权或台账。
