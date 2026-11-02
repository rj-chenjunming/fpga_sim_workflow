"""图标 sprite 守卫（批次 4 · A 项，软件层，不启浏览器）。

契约来源：
- `doc/plans/2026-10-30-ui-batch4.md` §A（内联 sprite、`viewBox="0 0 16 16"`、无死 symbol、
  组件层不再出现被替换码位、零外链）；
- `doc/spec/WEB_UI_SPEC.md` §14「资产」（所有字体、装饰和图标本地化，无 CDN、外部字体或运行时依赖）
  与 §10 A13/A14（不得新增字号）；
- 设计分析 `.ui-audit/4/icons.md`（22 个 symbol 表 / 23 个码位 / 54 处、一符一义拆法）。

为什么是这几条（每条都对应一条既有测试或红线，属于「不读实现也能判定」的静态不变式）：

1. **无死 symbol、无悬空 use** —— sprite 是唯一图标来源；symbol 多于引用 ⇒ 没消费者的资产（YAGNI），
   小于引用 ⇒ 空框（浏览器对缺失 `<use>` 不报错，只是什么都不画，只能静态判）。
2. **`viewBox="0 0 16 16"`** —— 22 个符号同一坐标网格；缺了会按内容包围盒缩放，尺寸失控。
3. **被替换码位归零** —— 图标不再依赖系统字体回退（D-16）；`legacy.html` 是登记例外，**不在扫描面内**。
   不用 SVG 的标点（`→` 正文流程图、`…` 文案省略号、`!` JS 运算符、`●` `document.title` 前缀）
   单独走白名单，并在下面逐条写明理由 —— 白名单是**具名**的，不是整文件豁免。
4. **零外链** —— 内联 SVG 不写 `xmlns`（HTML5 不需要；写了会把 `http://` 带进 HTML/JS，
   直接红 `tests/test_web_smoke.py` 的 `http://` 断言）、JS 不 `createElementNS`（同一原因）、
   不新增 `url(`（`tests/browser/test_ui_visual_20261030.py` 的零 `url(` 断言）。
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"

#: 组件层（图标唯一消费者面）。`legacy.html` 是 §14/计划登记的**例外**：存档界面本轮不迁移。
COMPONENTS = ("index.html", "app.js", "s0.js", "node-detail.js")

#: sprite 里必须有、且**必须**被引用到的符号（一符一义；名字即语义）。
EXPECTED_SYMBOLS = {
    "icon-s0",       # ▧ 环境准备 / 派生工作副本
    "icon-setup",    # ⊞ 运行配置
    "icon-run",      # ◴ 运行监控
    "icon-gate",     # ◇ 人工闸门（导航）
    "icon-chevron",  # ⌄ / ▸ 展开收起（CSS 只 rotate，不换字）
    "icon-next",     # → 主操作「继续 / 前往」
    "icon-external", # ↗ 新窗口 / 下载
    "icon-panel",    # ↗ 打开页内浮层（Agent 窗口 / 前后对比）
    "icon-close",    # × 关闭浮层
    "icon-check",    # ✓ 完成 / 通过
    "icon-fail",     # ✕ 失败 / 拒绝
    "icon-wait",     # ! 等待（待人工）
    "icon-running",  # … 进行中（状态泡）
    "icon-up",       # ↑ 上级目录
    "icon-valid",    # ▣ 基线条目有效
    "icon-invalid",  # ▢ 基线条目无效 / 缺件
    "icon-agent",    # • agent 角色占位
    "icon-empty",    # ◇ 空态插图（结构与伪元素解耦）
}

#: 设计表里存在、但本轮**没有消费者**的符号：它们只被 `legacy.html` 用到，而 legacy 本轮不迁移。
#: 按 AGENTS §2 硬性纪律 4（没有消费者的字段/资产不得保留，YAGNI）不落进 sprite；
#: 若将来迁移 legacy，再把它们连同引用一起加进来（本表同时是 fail-closed 断言：先加资产后加消费者会红）。
DEFERRED_WITH_LEGACY = {
    "icon-back",    # ← legacy.html:171
    "icon-refresh", # ⟳ legacy.html:564
    "icon-warn",    # ⚠ legacy.html:766
    "icon-blocked", # ⛔ legacy.html:988/1303
}

#: 已被 sprite 取代、**必须归零**的码位（组件层）。
REPLACED_ZERO = "✓✕▸◇↑•⌄▧⊞◴▣▢×↗"

#: 不参与替换的码位 → 具名理由（不是整文件豁免，能用字面量卡的地方下面另加断言）。
WHITELIST = {
    "→": "正文里的流程箭头（copy → replace、派生 → 端口确认 …）是句子的一部分；"
         "换成 SVG 会伤选择/复制与读屏。可点击动作的 `→` 已换 icon-next，下面用字面量卡住",
    "…": "文案省略号（加载中…、截断路径）与状态泡无关；状态泡的「进行中」已换 icon-running",
    "!": "JS 逻辑非运算符，不可能也不应该归零；状态泡的「等待」已换 icon-wait",
    "●": "写入 document.title 的待办计数前缀：浏览器标签标题只接受文本，不可 SVG 化（唯一文本图标例外）",
}

_SYMBOL = re.compile(r'<symbol\s+id="([^"]+)"([^>]*)>')
_USE = re.compile(r'<use\s+href="#([^"]+)"')
#: `iconNode("x")` 与三元写法 `iconNode(cond ? "a" : "b")` 都算引用。
_JS_ICON_CALL = re.compile(r"iconNode\(([^)]*)\)")
_JS_ICON_NAME = re.compile(r'"([A-Za-z0-9_-]+)"')


def _text(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def _index() -> str:
    return _text("index.html")


def _js_texts() -> dict[str, str]:
    return {name: _text(name) for name in COMPONENTS if name.endswith(".js")}


# ---------------------------------------------------------------- sprite 骨架

def test_sprite_root_is_inline_and_hidden() -> None:
    """sprite 必须是 `index.html` 里的隐藏内联根：不新增静态资源文件、不新增一次 HTTP 请求。"""
    html = _index()
    assert 'id="iconSprite"' in html, "index.html 缺少内联图标 sprite（#iconSprite）"
    root = re.search(r'<svg\s+id="iconSprite"[^>]*>', html)
    assert root, "#iconSprite 必须是 <svg> 根"
    tag = root.group(0)
    assert "display:none" in tag.replace(" ", ""), f"#iconSprite 必须自带 display:none：{tag}"
    assert 'aria-hidden="true"' in tag, f"#iconSprite 必须 aria-hidden：{tag}"


def test_icon_template_for_dom_cloning_exists() -> None:
    """JS 端只克隆 `#iconTpl`，不拼 namespace 字符串（否则红 `test_web_smoke.py` 的 http:// 断言）。"""
    html = _index()
    assert 'id="iconTpl"' in html, "index.html 缺少 #iconTpl（JS 克隆模板）"
    template = re.search(r'<template\s+id="iconTpl">(.*?)</template>', html, re.S)
    assert template, "#iconTpl 必须是 <template>"
    body = template.group(1)
    assert '<use href="#icon-' in body, f"#iconTpl 内必须有 <use href=\"#icon-…\">：{body!r}"
    assert 'class="icon"' in body, "#iconTpl 的 svg 必须带 class=\"icon\""


def test_symbol_inventory_is_exactly_the_consumed_set() -> None:
    ids = [m.group(1) for m in _SYMBOL.finditer(_index())]
    assert len(ids) == len(set(ids)), f"symbol id 重复：{ids}"
    assert set(ids) == EXPECTED_SYMBOLS, (
        "symbol 表与设计不符：缺 " f"{sorted(EXPECTED_SYMBOLS - set(ids))}，多 {sorted(set(ids) - EXPECTED_SYMBOLS)}"
    )
    assert not (set(ids) & DEFERRED_WITH_LEGACY), f"以下符号没有消费者（legacy 未迁移）：{sorted(set(ids) & DEFERRED_WITH_LEGACY)}"


def test_every_symbol_uses_the_16px_grid() -> None:
    bad = [m.group(1) for m in _SYMBOL.finditer(_index()) if 'viewBox="0 0 16 16"' not in m.group(2)]
    assert not bad, f"这些 symbol 缺 viewBox=\"0 0 16 16\"：{bad}"


def test_every_symbol_has_a_consumer_and_every_use_resolves() -> None:
    html = _index()
    symbols = {m.group(1) for m in _SYMBOL.finditer(html)}
    refs = {m.group(1).lstrip("#") for m in _USE.finditer(html)}
    for name, text in _js_texts().items():
        for call in _JS_ICON_CALL.finditer(text):
            for m in _JS_ICON_NAME.finditer(call.group(1)):
                refs.add("icon-" + m.group(1))
        # `labelWithIcon(按钮, 文案, "图标名")` 的图标名是**末位参数**（前两个参数里也有字符串
        # 字面量，如 class 名与文案），所以按行取最后一个引号字面量，不能整行扫（会造出假引用）。
        for line in text.splitlines():
            if "labelWithIcon(" not in line or "function labelWithIcon" in line:
                continue
            names = _JS_ICON_NAME.findall(line)
            assert names, f"{name} 的 labelWithIcon 调用缺图标名：{line.strip()}"
            refs.add("icon-" + names[-1])
    assert not (refs - symbols), f"<use> 指向不存在的 symbol（会渲染成空框）：{sorted(refs - symbols)}"
    dead = symbols - refs
    assert not dead, f"没有消费者的死 symbol（YAGNI）：{sorted(dead)}"


# ---------------------------------------------------------------- 码位归零

def test_replaced_code_points_are_gone_from_components() -> None:
    offenders: dict[str, dict[str, int]] = {}
    for name in COMPONENTS:
        text = _text(name)
        hits = {cp: text.count(cp) for cp in REPLACED_ZERO if cp in text}
        if hits:
            offenders[name] = hits
    assert not offenders, (
        "组件层仍含被替换的图标码位（应改用 <use href=\"#icon-…\">）："
        f"{offenders}；码位集合={REPLACED_ZERO!r}"
    )


def test_legacy_only_symbols_are_not_shipped() -> None:
    """`legacy.html` 是登记例外（本轮不迁移）⇒ 它的 4 个专用符号不得进 sprite（见 DEFERRED_WITH_LEGACY）。

    同时卡住范围的另一侧：legacy 的存档字形必须**仍在原处**（本轮没顺手改存档页）。
    `⚠/⛔` 的 emoji 字体依赖因此仍未消除 —— 这是登记在案的未做项，不是本用例的失败。
    """
    legacy = _text("legacy.html")
    for glyph in ("←", "⟳", "⚠", "⛔"):
        assert glyph in legacy, f"legacy.html 的存档字形 {glyph!r} 不见了（本轮不应迁移 legacy）"


def test_prose_arrows_stay_text_but_action_suffixes_are_icons() -> None:
    """白名单里 `→` 的边界：**可点击动作后缀**必须换成图标，正文流程箭头保留字面。"""
    for name in COMPONENTS:
        text = _text(name)
        for literal in ("派生并校验 →", "继续冒烟 →", "去新建运行 →", "逐条处置 →", "同源）→"):
            assert literal not in text, f"{name} 仍有「动作 + →」文本后缀（应改 icon-next）：{literal!r}"
        assert "<span aria-hidden=\"true\">→</span>" not in text, f"{name} 仍有独立的 → 装饰 span"
        assert ">→<" not in text, f"{name} 仍有独立 → 字形"


def test_ellipsis_and_title_prefix_are_the_only_whitelisted_glyphs() -> None:
    """白名单必须仍然“名副其实”：`●` 只剩 `document.title` 一处，其它白名单码位不得变成图标。"""
    app_js = _text("app.js")
    for name, text in _js_texts().items():
        for literal in ('return "✓"', 'return "✕"', 'return "!"', 'return "…"'):
            assert literal not in text, f"{name} 的状态图标函数仍在返回字形：{literal}"
    # ● 只在 document.title 前缀里出现（唯一文本图标例外）：全组件层 1 处，且同语句里有 document.title
    tally = {name: text.count("●") for name, text in _js_texts().items() if "●" in text}
    assert tally == {"app.js": 1}, f"● 只允许出现在 app.js 的 document.title 前缀里：{tally}"
    lines = app_js.splitlines()
    idx = next(i for i, line in enumerate(lines) if "●" in line)
    context = "\n".join(lines[max(0, idx - 3): idx + 1])
    assert "document.title" in context, f"● 不在 document.title 语句里：{context!r}"


# ---------------------------------------------------------------- 零外链

def test_no_external_asset_or_namespace_references() -> None:
    for name in COMPONENTS:
        text = _text(name)
        assert "xmlns" not in text, f"{name} 不得写 xmlns（HTML5 内联 SVG 不需要；会带进 http://）"
        assert "http://" not in text and "https://" not in text, f"{name} 不得引用外部资源"
        assert "createElementNS" not in text, f"{name} 不得用 createElementNS（会拼 namespace URI）"
        assert "url(" not in text, f"{name} 不得出现 url(（CSS 伪元素图标方案被否决）"
