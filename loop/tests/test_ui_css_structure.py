"""§10 A15 结构守卫：`loop/web/app.css` 同一简单选择器在同一 @ 上下文内只定义一次。

背景：F14（`doc/audit/AUDIT-20261021-post-ui-roadmap.md`）——`app.css` 是两段式，
早期组件样式被第 468 行起的「视觉系统段」重定义；批次 1+2/3A 之后仍有 146 个选择器
被 ≥2 条顶层规则定义。收敛计划见 `doc/plans/2026-10-30-ui-css-merge-f14c.md`（批次 3C）。

判据（软件层，不启浏览器）：
1. 用括号深度解析 `app.css`（剥注释、尊重字符串），得到每条规则的 (选择器列表, @ 上下文)。
2. 把选择器列表按逗号拆成**简单选择器**（本仓只关心「元素/类/id + 伪类」文本，不做语义解析），
   归一化空白后按 (上下文, 简单选择器) 计数；**每组计数必须 = 1**。
3. 反空扫：解析出的简单选择器实例数必须 ≥ 700（当前实现 ≈ 900，退到 700 以下说明解析器坏了）。

为什么按「同一 @ 上下文」而不是全文件：`@media`/`@supports` 内的同名规则是**按条件生效**的
独立层，与顶层规则不构成「重复定义」；这也是 `doc/spec/WEB_UI_SPEC.md` §14 与 F14 的原话。
白名单只用于「按级联语义判定必须保留两段」的例外，每条必须写理由（当前为空）。

允许修改本文件：仅在 `ALLOWED` 里加例外并注明理由；不得放宽计数阈值或跳过扫描。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_CSS = Path(__file__).resolve().parents[1] / "web" / "app.css"

# 例外：(上下文文本, 简单选择器) -> 理由。上下文文本 "" = 顶层，否则是完整 @media 条件文本。
#
# 批次 3C 逐条判级联语义后，只剩 4 组「两段之间夹着同特异性覆盖规则、且运行时确有线素同时命中两者」
# 的选择器：合并到前段会让后段的声明被中间规则压掉，合并到后段会让前段声明反压中间规则——两个方向
# 都改变生效值。证据：`.ui-audit/3c/cooccur-a.json`（36 个（视口,状态）组合的 DOM 共命中）
# + `.ui-audit/3c/merge-plan.json` 的受阻明细。放宽前必须重跑那两件证据并更新本表。
ALLOWED: dict[tuple[str, str], str] = {
    # ── 批次 3C 的 23 条「保留两段」例外（逐条判过级联语义，不是"懒得合"） ──────────────
    # 两类成因：
    #  (a) 两段之间夹着**同特异性覆盖规则**，且运行时 DOM 共命中证据（36 个（视口,状态）组合）显示
    #      确有元素同时命中两者 ⇒ 合并到前段会被中间规则压掉、合并到后段会反压中间规则，两个方向都改生效值；
    #  (b) 同名选择器在窗口内另有**别的 @ 上下文**规则：任何同时满足两边条件的环境里两条规则作用于同一批元素，
    #      源码先后就是生效关系（共命中证据对这条没有信息量）。
    # 依据文件：`.ui-audit/3c/merge-plan.json`（受阻明细）+ `.ui-audit/3c/cooccur-full.json`（2626 对共命中）。
    ('', '.btn'):
        '窗口内夹着同特异性覆盖规则 .btn-ghost、.rail-entry（background,border-color,color,gap,'
        'justify-content,padding）；DOM 共命中证据显示确有元素同时命中两者，合并任一方向都会改生效值',
    ('', '.run-item'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（width）',
    ('', '.card'):
        '窗口内夹着同特异性覆盖规则 .gate-card（background,border-color）；DOM 共命中证据显示确有元素同时命中两者，'
        '合并任一方向都会改生效值',
    ('', '.grid2'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值'
        '（grid-template-columns）',
    ('', '.input'):
        '窗口内夹着同特异性覆盖规则 .mono（font-family）；DOM 共命中证据显示确有元素同时命中两者，合并任一方向都会改生效值',
    ('', '.agents'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值'
        '（grid-template-columns）',
    ('', '.toast'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（max-width,right）',
    ('', '.s0-phases'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值'
        '（grid-template-columns）',
    ('', '.phase-card'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（align-items）',
    ('@media(max-width:760px)', 'header'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（gap）',
    ('@media(max-width:760px)', '.shell'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（min-height）',
    ('@media(max-width:760px)', '.rail-entry'):
        '窗口内夹着同特异性覆盖规则 .btn（font-size,height,margin-bottom）；DOM 共命中证据显示确有元素同时命中两者，'
        '合并任一方向都会改生效值',
    ('@media(max-width:760px)', 'aside #btnNew'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（height）',
    ('@media(max-width:760px)', '.run-item'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（padding）',
    ('@media(max-width:760px)', '.s0-phases'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值'
        '（gap,margin-bottom）',
    ('@media(max-width:760px)', '.phase-card'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（padding）',
    ('', '.agent-window'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（max-height）',
    ('', '.aw-head'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（gap）',
    ('', '.aw-terminal-mark'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值'
        '（font-size,height,width）',
    ('', '.aw-intervene'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（border-left）',
    ('', '.aw-timeline'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（max-height）',
    ('', '.aw-log-row'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（gap）',
    ('', '.aw-log-row>span'):
        '同名选择器在窗口内另有 @ 上下文规则：源码先后在那个上下文里就是生效关系，合并会改该断点内的生效值（flex-basis）',
}

MIN_SIMPLE_SELECTORS = 700


def _strip_comments(text: str) -> str:
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            out.append(" ")
            continue
        if text[i] in '"\'':
            quote = text[i]
            out.append(text[i])
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\":
                    i += 2
                    out.append(text[i - 1])
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _rules(text: str):
    """返回 [(context: tuple[str, ...], selector: str)]；括号深度解析，不猜。"""
    rules: list[tuple[tuple[str, ...], str]] = []
    n = len(text)

    def find_block_end(open_index: int) -> int:
        depth, i = 0, open_index
        while i < n:
            if text[i] in '"\'':
                quote = text[i]
                i += 1
                while i < n and text[i] != quote:
                    i += 2 if text[i] == "\\" else 1
                i += 1
                continue
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise AssertionError("app.css 花括号不平衡（解析器或文件损坏）")

    def walk(i: int, end: int, ctx: tuple[str, ...]) -> None:
        while i < end:
            while i < end and text[i] in " \t\r\n;":
                i += 1
            if i >= end:
                return
            if text[i] == "}":
                i += 1
                continue
            prelude_start = i
            paren = 0
            while i < end:
                ch = text[i]
                if ch in "([":
                    paren += 1
                elif ch in ")]":
                    paren -= 1
                elif ch == "{" and paren == 0:
                    break
                i += 1
            prelude = text[prelude_start:i].strip()
            block_end = find_block_end(i)
            if prelude.startswith("@"):
                # `@media(max-width:760px)`（括号前无空格）与 `@media (…)` 都是条件块，
                # 必须进上下文，否则会整块漏扫（3C 首轮红测就栽在这：少算了 @media 内的规则）。
                name = re.match(r"@[\w-]+", prelude).group(0).lower()
                if name in ("@media", "@supports", "@layer"):
                    walk(i + 1, block_end, ctx + (prelude,))
                # @keyframes / @font-face 等不是选择器规则，跳过
            else:
                rules.append((ctx, prelude))
            i = block_end + 1

    walk(0, n, ())
    return rules


def _simple_selectors(selector_list: str) -> list[str]:
    parts, buf, depth = [], [], 0
    for ch in selector_list:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    out = []
    for part in parts:
        norm = " ".join(part.split())
        if norm:
            out.append(norm)
    return out


def load_structure():
    text = _strip_comments(APP_CSS.read_text(encoding="utf-8"))
    seen: dict[tuple[tuple[str, ...], str], int] = {}
    duplicates: list[dict] = []
    total = 0
    for ctx, selector_list in _rules(text):
        for simple in _simple_selectors(selector_list):
            total += 1
            key = (ctx, simple)
            seen[key] = seen.get(key, 0) + 1
    for (ctx, simple), count in seen.items():
        if count > 1:
            duplicates.append({"context": " ".join(ctx),
                               "selector": simple, "count": count})
    return total, len(seen), duplicates


def test_whitelist_entries_still_duplicated():
    """白名单是「已知例外」，不是「永久豁免」：每条必须仍被 ≥2 条规则定义，否则要删掉这条。"""
    _total, _distinct, duplicates = load_structure()
    seen = {(d["context"], d["selector"]) for d in duplicates}
    stale = [key for key in ALLOWED if key not in seen]
    assert not stale, f"白名单已失效（这些选择器现在只定义一次，请从 ALLOWED 删除）：{stale}"


def test_simple_selectors_are_defined_once_per_context():
    """同一简单选择器在同一 @ 上下文内只允许一条规则定义（批次 3C 的收敛判据）。"""
    total, distinct, duplicates = load_structure()
    # 反空扫：先证明解析器真的读到了东西（否则「无重复」毫无意义）
    assert total >= MIN_SIMPLE_SELECTORS, (
        f"反空扫失败：只解析到 {total} 个简单选择器（阈值 {MIN_SIMPLE_SELECTORS}），"
        "解析器可能坏了，不是文件变干净了")
    assert distinct >= MIN_SIMPLE_SELECTORS, (
        f"反空扫失败：只有 {distinct} 个不同简单选择器（阈值 {MIN_SIMPLE_SELECTORS}）")
    unallowed = [d for d in duplicates
                 if (d["context"], d["selector"]) not in ALLOWED]
    if unallowed:
        lines = [f"{d['context'] or 'top-level'}  {d['selector']}  ×{d['count']}"
                 for d in unallowed[:40]]
        pytest.fail(
            "app.css 仍有 %d 个简单选择器在同一 @ 上下文内被多次定义"
            "（F14 两段式未收敛，见 doc/plans/2026-10-30-ui-css-merge-f14c.md）：\n  %s"
            % (len(unallowed), "\n  ".join(lines)))
