"""字号阶梯守卫（WEB_UI_SPEC §14「字号阶梯（2026-10-30 增补）」/ §10 A14）。

组件层字号只允许 11 个档位。本用例是**软件层静态扫描**：不启动浏览器，直接读
`loop/web/{app.css,legacy.css,index.html,legacy.html}`，把每个 `font-size` 与 `font`
简写的 px 值抽出来对照阶梯。`mockup.html` 是 §14 明示的静态历史样张，不参与。

复核加固（2026-10-30，依据 `.ui-audit/F-typography-verify.md` P2-2/2-3/2-4）：
- 扫描前剥离 CSS 注释与 HTML 注释，避免注释里的旧值被当声明；
- px 匹配大小写不敏感（`11.5PX` 也抓）；`font:` 简写与 `font-size` 都查相对单位（em/rem/%/vw/vh）；
- 规格解析只取 §14 那一条 bullet，允许 1–3 位数字，并交叉校验 §10 A14 的列表。

先按本文件判红、再实现，是本切片 SpecDD 的先失败用例（AGENTS §2.1 第 3 条）。
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
SPEC = Path(__file__).resolve().parents[2] / "doc" / "spec" / "WEB_UI_SPEC.md"

#: 唯一口径（与 §14 表格逐字对应；改这里必须同时改规格）。
SCALE = {10, 11, 12, 13, 14, 16, 18, 20, 24, 30, 36}

FILES = ("app.css", "legacy.css", "index.html", "legacy.html")

_FONT_SIZE = re.compile(r"font-size\s*:\s*([^;{}\"']+)", re.IGNORECASE)
_FONT_SHORT = re.compile(r"(?<![-\w])font\s*:\s*([^;{}\"']+)", re.IGNORECASE)
_PX = re.compile(r"(\d+(?:\.\d+)?)\s*px", re.IGNORECASE)
_RELATIVE = re.compile(r"\d\s*(?:em|rem|%|vw|vh)\b", re.IGNORECASE)
_COMMENT_CSS = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_HTML = re.compile(r"<!--.*?-->", re.DOTALL)


def _clean(text: str) -> str:
    return _COMMENT_HTML.sub("", _COMMENT_CSS.sub("", text))


def _sizes(decl: str, shorthand: bool) -> list[float]:
    """`font-size` 取全部 px；`font` 简写只取第一个 px（字号），避免把行高/边框误判。"""
    values = _PX.findall(decl)
    if shorthand and values:
        values = values[:1]
    return [float(v) for v in values]


def scan() -> list[tuple[str, int, str, float]]:
    """返回 (文件, 行号, 原文声明, 字号)。"""
    found: list[tuple[str, int, str, float]] = []
    for name in FILES:
        text = _clean((WEB / name).read_text())
        for pattern, shorthand in ((_FONT_SIZE, False), (_FONT_SHORT, True)):
            for match in pattern.finditer(text):
                decl = match.group(1).strip()
                for value in _sizes(decl, shorthand):
                    line = text[: match.start()].count("\n") + 1
                    found.append((name, line, decl, value))
    return found


def test_every_font_size_is_on_the_declared_scale() -> None:
    found = scan()
    assert len(found) >= 300, f"扫描数过少（{len(found)}），守卫失效"
    offenders = [(name, line, decl, size) for name, line, decl, size in found if size not in SCALE]
    assert not offenders, "字号不在 §14 阶梯上：\n" + "\n".join(
        f"  {name}:{line}  {size:g}px  （{decl[:80]}）" for name, line, decl, size in offenders[:20]
    )


def test_no_relative_or_unitless_font_sizes() -> None:
    """阶梯是绝对 px；`rem`/`em`/`%` 会让判定失效（§10 A14），`font:` 简写同样适用。"""
    for name in FILES:
        text = _clean((WEB / name).read_text())
        for pattern in (_FONT_SIZE, _FONT_SHORT):
            for match in pattern.finditer(text):
                decl = match.group(1)
                assert not _RELATIVE.search(decl), f"{name}: 疑似相对字号 {match.group(0)[:70]}"
                if pattern is _FONT_SHORT:
                    # 简写允许 inherit 等无字号写法；一旦出现数字就必须有 px 字号
                    if re.search(r"\d", decl):
                        assert _PX.search(decl), f"{name}: font 简写缺少 px 字号 {decl[:70]}"
                elif not re.fullmatch(r"(?:inherit|initial|unset|revert(?:-layer)?)\s*", decl, re.IGNORECASE):
                    assert _PX.search(decl), f"{name}: font-size 缺少 px 值 {decl[:70]}"


def _bullet(spec: str, marker: str) -> str:
    start = spec.index(marker)
    end = spec.find("\n- **", start + 1)
    if end == -1:
        end = spec.find("\n\n", start)
    assert end != -1, f"规格里找不到 bullet 边界：{marker}"
    return spec[start:end]


def _quoted_sizes(block: str) -> set[int]:
    values: set[int] = set()
    for chunk in re.findall(r"`([\d/]+?)`", block):
        for part in chunk.split("/"):
            if part.isdigit():
                values.add(int(part))
    return values


def test_scale_matches_spec_table_and_a14() -> None:
    """双写防漂移：§14 表、§10 A14、本文件 SCALE 三处必须一致。"""
    spec = SPEC.read_text()
    table = _quoted_sizes(_bullet(spec, "**字号阶梯（2026-10-30 增补"))
    assert table == SCALE, f"§14 表 {sorted(table)} != 用例 {sorted(SCALE)}"

    a14_line = next(line for line in spec.splitlines() if line.startswith("| A14 |"))
    row = _quoted_sizes(a14_line.split("|")[2])
    assert row == SCALE, f"§10 A14 {sorted(row)} != 用例 {sorted(SCALE)}"
