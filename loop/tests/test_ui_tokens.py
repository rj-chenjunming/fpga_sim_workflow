"""批次 3B 配色令牌化守卫：`tokens.css` 是组件层唯一色源（软件层，不启浏览器）。

判据来源：`doc/plans/2026-10-30-ui-color-tokens-3b.md` §2（验收判据）+ 人裁
「接受 69 个颜色令牌、每条字面量到其令牌 ΔRGB ≤12（实色与 alpha 合成后都 ≤12）」。
色差本身不在这里判定——那是 `.ui-audit/3b/selfcheck-final.txt`（值级自检，实现前冻结）的职责：
本文件只守「组件层不再自己写颜色」这件事，可静态判定、不读实现细节。

扫描口径（三条，缺一条就会假绿或假红）：

1. **只扫声明位置**。`app.css`/`legacy.css` 里 `#banners{…}`、`aside #btnNew{…}` 这类 **ID 选择器**
   会被裸的 `#[0-9a-f]{3,8}` 正则误判成十六进制色值。所以先按花括号把「选择器前导」涂空
   （`_mask_declaration_positions`，等长替换、保留换行，故行号与原文一致），只剩声明文本再匹配。
   实测：涂空后 `app.css` 得 323 条、`legacy.css` 得 59 条，与 `.ui-audit/3b/map-final.tsv`
   的 323+59=382 逐条一致 —— 说明这个口径就是分析员用的口径。
2. **剥注释**（CSS `/*…*/`、HTML `<!--…-->`）：注释里的旧值不是声明。
3. **色值形态** = `#rgb`/`#rgba`/`#rrggbb`/`#rrggbbaa` + `rgb(`/`rgba(`/`hsl(`/`hsla(`。
   `transparent`/`none`/`inherit`/`auto` 不是色值字面量，按人裁保留原样。

`legacy.html` 的口径（死声明为什么不要求清零）：
该页 `<style>`（L8–L161）是重构前的暗色主题样式表，`tokens.css`/`legacy.css`/`app.css` 在其后加载。
按「选择器是否被后加载样式表重新声明」逐条比对（`.ui-audit/3b/_gen-inline.md`）：158 条色值 / 87 条带色规则里
**只有 3 条仍然生效**（`.chain-arrow` / `.toast-item.err` / `.toast-item.ok`），其余 **155 条是死声明**
（被后加载规则整体覆盖，运行时永不生效）。人裁：本批只令牌化**活的那 3 条**；死声明属「结构清理」，
删整块需要属性级级联证明，风险大于收益，单开一批处理。因此本文件：
- 断言 `<style>` 里的**活规则**与所有 `style="…"` 属性无颜色字面量；
- 另用一个**显式命名的**用例守住「死声明还在、按设计不动」（`test_dead_inline_declarations_…`），
  将来真的清退那 155 条时，只需在那一批里更新这一个用例，不会波及其它判据。

先按本文件判红、再实现，是本切片 SpecDD 的先失败用例（AGENTS §2.1 第 3 条）。
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
TOKENS_CSS = WEB / "tokens.css"
APP_CSS = WEB / "app.css"
LEGACY_CSS = WEB / "legacy.css"
LEGACY_HTML = WEB / "legacy.html"

#: 人裁：69 个颜色令牌，±0。实现时若发现必须变，先停手报告，不得自行改判据。
EXPECTED_COLOR_TOKENS = 69
#: 非颜色令牌（原样保留、不含色值）；与颜色令牌一起共 74 个变量。
EXPECTED_NON_COLOR_TOKENS = frozenset(
    {"--shadow", "--radius", "--ease-out", "--font-sans", "--font-mono"})
#: 反空扫：组件层的 `var(--…)` 用量（实现后约 949，退到 300 以下说明扫描器坏了）。
MIN_TOKEN_USES = 300
#: 反空扫：`legacy.html` `<style>` 解析出的选择器单元数（当前 137，退到 80 以下说明解析器坏了）。
MIN_INLINE_SELECTOR_UNITS = 80
#: 反空扫：`legacy.html` `<style>` 里应保留的死声明色值数（当前 155；见模块 docstring）。
MIN_DEAD_INLINE_COLOR_LITERALS = 100

#: 运行时由 JS 写入的自定义属性（不是设计令牌，不进 `tokens.css`）。
#: 每条必须能在 `app.js` 里找到 `setProperty("<name>"` 的写入点，否则本表失效（见下条用例）。
RUNTIME_SET_VARS: dict[str, str] = {
    "--p": "app.js 的 `fill.style.setProperty('--p', ratio)`：阶段进度比例，"
           "以 `var(--p,0)` 带 0 回退消费（§14 禁止动画 width，只动 transform）",
}

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

#: 色值字面量。长变体在前、后向不接十六进制位，避免 `#fff` 吃掉 `#fffdf8` 的前缀。
_COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
    r"|\b(?:rgba?|hsla?)\s*\([^()]*\)"
)
_VAR_USE = re.compile(r"var\(\s*(--[\w-]+)")
_VAR_DECL = re.compile(r"(--[\w-]+)\s*:\s*([^;{}]*)")
_INLINE_STYLE_ATTR = re.compile(r'\bstyle\s*=\s*"([^"]*)"')
_STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------- 基础工具


def _blank(text: str, chunks: list[tuple[int, int]]) -> str:
    """把 [start, end) 区间等长涂成空格（保留换行），偏移与行号不变。"""
    chars = list(text)
    for start, end in chunks:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _blank_css_comments(text: str) -> str:
    return _blank(text, [(m.start(), m.end()) for m in _CSS_COMMENT.finditer(text)])


def _blank_html_comments(text: str) -> str:
    return _blank(text, [(m.start(), m.end()) for m in _HTML_COMMENT.finditer(text)])


def _match_brace(text: str, open_index: int, end: int) -> int:
    depth, i = 0, open_index
    while i < end:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError("花括号不平衡（文件损坏或解析器坏了）")


def _mask_declaration_positions(css: str) -> str:
    """涂空所有「选择器前导 / @ 条件前导」，只留声明文本；等长替换，行号仍对得上原文。

    递归进 `@media`/`@supports`：块内先出现的 `…{` 之前的文本是嵌套规则的选择器，同样涂空。
    """
    chunks: list[tuple[int, int]] = []
    n = len(css)

    def walk(start: int, end: int) -> None:
        seg, i = start, start
        while i < end:
            ch = css[i]
            if ch == "{":
                chunks.append((seg, i))
                close = _match_brace(css, i, end)
                walk(i + 1, close)
                i = close + 1
                seg = i
                continue
            if ch == "}":
                i += 1
                seg = i
                continue
            i += 1

    walk(0, n)
    return _blank(css, chunks)


def _norm_selector(text: str) -> str:
    """归一空白：`a > b` 与 `a>b`、`a , b` 与 `a,b` 视为同一选择器。"""
    return re.sub(r"\s*([>+~])\s*", r"\1", " ".join(text.split()))


def _selector_units(selector_list: str) -> list[str]:
    """按顶层逗号拆简单选择器（`[type=a,b]`/`:not(a,b)` 里的逗号不拆）。"""
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
    units = [_norm_selector(p) for p in parts]
    return [u for u in units if u]


def _rules(css: str) -> list[tuple[tuple[str, ...], str, str]]:
    """`[(context, selector_list, declaration_text)]`；递归进 `@media`/`@supports`。

    入参须已剥注释。`@keyframes`/`@font-face` 等不是选择器规则，跳过其声明。
    """
    out: list[tuple[tuple[str, ...], str, str]] = []
    n = len(css)

    def walk(start: int, end: int, ctx: tuple[str, ...]) -> None:
        seg, i = start, start
        while i < end:
            ch = css[i]
            if ch == "{":
                close = _match_brace(css, i, end)
                prelude = _norm_selector(css[seg:i])
                if prelude.startswith("@"):
                    name = re.match(r"@[\w-]+", prelude)
                    if name and name.group(0).lower() in ("@media", "@supports", "@layer"):
                        walk(i + 1, close, ctx + (prelude,))
                    # @keyframes / @font-face 内的声明不是组件颜色，跳过
                else:
                    out.append((ctx, prelude, css[i + 1:close]))
                i = close + 1
                seg = i
                continue
            if ch == "}":
                i += 1
                seg = i
                continue
            i += 1

    walk(0, n, ())
    return out


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _literals_with_lines(text: str) -> list[tuple[int, str]]:
    return [(_line_of(text, m.start()), m.group(0)) for m in _COLOR.finditer(text)]


def _declaration_text(path: Path) -> str:
    """剥注释 + 涂空选择器前导后的「纯声明文本」。"""
    return _mask_declaration_positions(_blank_css_comments(path.read_text(encoding="utf-8")))


def _token_declarations() -> dict[str, str]:
    """`tokens.css` 的 `--name: value`（已是声明文本，`:` 不会来自选择器）。"""
    declared: dict[str, str] = {}
    for match in _VAR_DECL.finditer(_declaration_text(TOKENS_CSS)):
        declared[match.group(1)] = match.group(2).strip()
    return declared


def _later_stylesheet_units() -> set[str]:
    """后加载样式表（tokens → legacy → app）声明过的全部选择器单元。"""
    units: set[str] = set()
    for path in (TOKENS_CSS, LEGACY_CSS, APP_CSS):
        text = _blank_css_comments(path.read_text(encoding="utf-8"))
        for _ctx, selector_list, _decls in _rules(text):
            units.update(_selector_units(selector_list))
    return units


def _inline_style_block() -> str:
    match = _STYLE_BLOCK.search(LEGACY_HTML.read_text(encoding="utf-8"))
    assert match, "legacy.html 里找不到 <style> 块（结构变了就更新本守卫）"
    return match.group(1)


def _inline_rules() -> list[tuple[tuple[str, ...], str, str]]:
    return _rules(_blank_css_comments(_inline_style_block()))


def _live_inline_units() -> list[tuple[str, str]]:
    """`[(选择器单元, 声明文本)]`：没被 tokens/legacy/app 重新声明过的内联规则。

    这是 `.ui-audit/3b/_gen-inline.md` 的口径（158 条色值 / 88 个被覆盖选择器 / 3 个未覆盖）。
    单元级判定比「整条前导串」严格：`tokens.css` 里 `.badge,.chip{…}` 与内联 `.badge{…}`
    前导串不同，但选择器确实被重新声明，按单元比对才与冻结证据一致。
    """
    later = _later_stylesheet_units()
    live: list[tuple[str, str]] = []
    for _ctx, selector_list, decls in _inline_rules():
        for unit in _selector_units(selector_list):
            if unit not in later:
                live.append((unit, decls))
    return live


# ---------------------------------------------------------------- 组件层：零字面量


def test_component_css_has_no_color_literals() -> None:
    """`app.css` + `legacy.css` 的声明里不得再出现色值字面量（`tokens.css` 是唯一色源）。"""
    offenders: list[str] = []
    scanned = 0
    for path in (APP_CSS, LEGACY_CSS):
        text = _declaration_text(path)
        hits = _literals_with_lines(text)
        scanned += len(hits)
        offenders.extend(f"{path.name}:{line}  {literal}" for line, literal in hits[:20])
    assert not offenders, (
        "组件层仍有 %d 处颜色字面量（应全部换成 var(--token)；映射见 "
        ".ui-audit/3b/map-final.tsv）。前 20 条：\n  %s"
        % (scanned, "\n  ".join(offenders))
    )


def test_component_layer_actually_consumes_tokens() -> None:
    """反空扫：组件层必须真的在用令牌（实现后约 949 处），否则「零字面量」可能只是扫空了。"""
    uses = 0
    for path in (APP_CSS, LEGACY_CSS, LEGACY_HTML):
        text = path.read_text(encoding="utf-8")
        uses += len(_VAR_USE.findall(text))
    assert uses >= MIN_TOKEN_USES, (
        f"组件层只用到 {uses} 处 var(--…)，低于反空扫阈值 {MIN_TOKEN_USES}："
        "要么替换没做完，要么扫描器坏了")


def test_legacy_inline_live_rules_have_no_color_literals() -> None:
    """`legacy.html` `<style>` 里**仍然生效**的规则不得有色值字面量（死声明见下一条用例）。"""
    live = _live_inline_units()
    total_units = sum(len(_selector_units(selector_list))
                      for _ctx, selector_list, _decls in _inline_rules())
    assert total_units >= MIN_INLINE_SELECTOR_UNITS, (
        f"反空扫失败：<style> 只解析到 {total_units} 个选择器单元（阈值 "
        f"{MIN_INLINE_SELECTOR_UNITS}），解析器可能坏了")
    offenders = [(unit, literal) for unit, decls in live
                 for _line, literal in _literals_with_lines(decls)]
    assert not offenders, (
        "legacy.html 内联 <style> 的活规则仍有颜色字面量（应换成 var(...)，共 %d 处）：\n  %s"
        % (len(offenders), "\n  ".join(f"{unit}: {literal}" for unit, literal in offenders[:20]))
    )


def test_legacy_inline_style_attributes_have_no_color_literals() -> None:
    """`legacy.html` 的 `style="…"` 属性里不得有色值（当前 6 处全是布局，0 色值）。"""
    html = _blank_html_comments(LEGACY_HTML.read_text(encoding="utf-8"))
    offenders = [(value, m.group(0)) for m in _INLINE_STYLE_ATTR.finditer(html)
                 for value in [_COLOR.search(m.group(1))] if value]
    assert not offenders, (
        "legacy.html 的 style 属性里出现颜色字面量：\n  "
        + "\n  ".join(f'{attr[:80]}  →  {hit}' for attr, hit in offenders[:20])
    )


def test_dead_inline_declarations_stay_untouched_by_design() -> None:
    """按设计保留 `legacy.html` 那 155 条死声明（本批只令牌化活的 3 条）。

    理由：它们被后加载的 tokens/legacy/app 整体覆盖、运行时永不生效；清理属结构批次，
    需属性级级联证明。将来真清退这块样式时，**只需更新本用例**（其余判据不受影响）。
    """
    literals = _literals_with_lines(_mask_declaration_positions(
        _blank_css_comments(_inline_style_block())))
    assert len(literals) >= MIN_DEAD_INLINE_COLOR_LITERALS, (
        f"legacy.html <style> 只剩 {len(literals)} 条色值（预期 ≥"
        f"{MIN_DEAD_INLINE_COLOR_LITERALS} 条死声明）：如果这是有意的清退，"
        "请在同一批里更新本用例并在报告里写明")


# ---------------------------------------------------------------- 令牌层：唯一色源


def test_tokens_css_defines_every_used_variable() -> None:
    """组件层用到的每个 `var(--x)` 都必须可解析，且**颜色令牌只许来自 `tokens.css`**。

    可解析 = 三者之一：
    1. 在 `tokens.css` 定义（本批所有颜色令牌的唯一归属）；
    2. 在组件层**本地声明**（如 `app.css` 的 `--gate-pane-max-h:clamp(…)`，是组件局部的布局值，
       不是全站令牌，3B 不动它——`tests/browser/test_gate_panes.py` 直接读这个 token）；
    3. 运行时由 JS 写入（`RUNTIME_SET_VARS`，逐条有写入点校验）。
    颜色不许走第 2 条以外的方式：一旦组件层出现本地**颜色**变量，等于开了第二个色源，
    所以下面单独断言组件层本地声明的自定义属性里没有色值。
    """
    declared = _token_declarations()
    local: dict[str, tuple[str, str]] = {}
    for path in (APP_CSS, LEGACY_CSS):
        for match in _VAR_DECL.finditer(_declaration_text(path)):
            local.setdefault(match.group(1), (path.name, match.group(2).strip()))

    missing: dict[str, list[str]] = {}
    for path in (APP_CSS, LEGACY_CSS, LEGACY_HTML):
        for name in _VAR_USE.findall(path.read_text(encoding="utf-8")):
            if name in declared or name in local or name in RUNTIME_SET_VARS:
                continue
            missing.setdefault(name, []).append(path.name)
    assert not missing, "这些 var(--x) 既不在 tokens.css、也不是本地声明/运行时变量：\n  " + "\n  ".join(
        f"{name}: {sorted(set(files))}" for name, files in sorted(missing.items()))

    colour_local = {name: where for name, where in local.items()
                    if _COLOR.search(where[1])}
    assert not colour_local, (
        "组件层本地声明了颜色变量（等于第二个色源，颜色只能来自 tokens.css）：\n  "
        + "\n  ".join(f"{name}: {where[0]}  {where[1]}" for name, where in sorted(colour_local.items())))


def test_runtime_variable_allowlist_is_still_real() -> None:
    """`RUNTIME_SET_VARS` 是「这不是设计令牌」的声明，必须仍能在 JS 里找到写入点。"""
    js = (WEB / "app.js").read_text(encoding="utf-8")
    stale = [name for name in RUNTIME_SET_VARS if f'setProperty("{name}"' not in js]
    assert not stale, f"运行时变量白名单已失效（app.js 里没有 setProperty 写入点）：{stale}"


def test_color_token_count_is_the_adjudicated_69() -> None:
    """颜色令牌 = 69（人裁，±0）；非颜色令牌仍是那 5 个，合计 74 个变量。"""
    declared = _token_declarations()
    color = {name: value for name, value in declared.items()
             if _COLOR.fullmatch(value.strip())}
    assert len(color) == EXPECTED_COLOR_TOKENS, (
        f"颜色令牌 {len(color)} 个，人裁是 {EXPECTED_COLOR_TOKENS} 个（±0）。"
        "若确有必要改动，先停手报告，不要自行改判据")
    non_color = set(declared) - set(color)
    assert non_color == set(EXPECTED_NON_COLOR_TOKENS), (
        f"非颜色令牌集合变了：多了 {sorted(non_color - set(EXPECTED_NON_COLOR_TOKENS))}、"
        f"少了 {sorted(set(EXPECTED_NON_COLOR_TOKENS) - non_color)}")
    assert len(declared) == EXPECTED_COLOR_TOKENS + len(EXPECTED_NON_COLOR_TOKENS)


def test_tokens_css_stays_light_local_and_on_the_motion_contract() -> None:
    """既有浏览器用例 `test_tokens_and_motion_contract` 的口径不许被本批破坏。

    它断言：`tokens.css` + `app.css` 不含字体外链（`Inter`/`@font-face`/`url(`），
    `--ease-out` 仍是 `cubic-bezier(0.22,1,0.36,1)`，且 `color-scheme:light` 保留。
    """
    tokens = TOKENS_CSS.read_text(encoding="utf-8")
    assert "color-scheme:light" in tokens.replace(" ", "")
    assert "--ease-out" in tokens
    assert re.search(r"--ease-out\s*:\s*cubic-bezier\(\s*0\.22\s*,\s*1\s*,\s*0\.36\s*,\s*1\s*\)",
                     tokens), "--ease-out 的缓动曲线被改了（浏览器用例会红）"
    for forbidden in ("@font-face", "url(", "Inter", "http://", "https://", "//cdn"):
        assert forbidden not in tokens, f"tokens.css 出现 {forbidden!r}（必须零外部依赖）"
