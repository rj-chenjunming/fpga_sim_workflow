"""3B 实现脚本：把 `app.css` / `legacy.css` 的**颜色字面量**按冻结映射换成 `var(--token)`。

设计约束（人裁 + 写权）：
- **只改颜色字面量**：选择器、声明顺序、其它值、格式一律不动。做法是「按偏移原位替换」，
  不是重排/重写文件，因此 diff 里应当只有 `#hex`→`var(--x)` / `rgba(...)`→`var(--x)` 这一类改动。
- **行号会漂**：所以按**值级**映射（`map-values-final.tsv`，233 条唯一值 → 令牌）定位，
  `map-final.tsv`（382 条逐项，带 file/line/property）只用作**计数 oracle**：
  每个文件里每种字面量的出现次数必须逐值与 map 一致，否则中止、不写盘。
- **只扫声明位置**：`#banners{…}` 这类 ID 选择器不是色值（与 `loop/tests/test_ui_tokens.py` 同口径）。
- dry-run 先逐条打印计划；`--apply` 才写，写完自检「组件层字面量 = 0」。

用法：
    .venv/bin/python .ui-audit/3b-impl/apply_tokens.py            # dry-run（默认）
    .venv/bin/python .ui-audit/3b-impl/apply_tokens.py --apply
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / ".ui-audit" / "3b"
MAP_FINAL = AUDIT / "map-final.tsv"
MAP_VALUES = AUDIT / "map-values-final.tsv"
TARGETS = ("loop/web/app.css", "loop/web/legacy.css")

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
    r"|\b(?:rgba?|hsla?)\s*\([^()]*\)"
)


def mask_declarations(css: str) -> str:
    """等长涂空「选择器前导 / @ 条件前导」，保留换行 ⇒ 偏移与行号不变。"""
    chunks: list[tuple[int, int]] = []
    n = len(css)

    def match_brace(open_index: int, end: int) -> int:
        depth, i = 0, open_index
        while i < end:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise SystemExit("花括号不平衡：%s" % css[open_index:open_index + 40])

    def walk(start: int, end: int) -> None:
        seg, i = start, start
        while i < end:
            ch = css[i]
            if ch == "{":
                chunks.append((seg, i))
                close = match_brace(i, end)
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
    chars = list(css)
    for start, end in chunks:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def blank_comments(text: str) -> str:
    chars = list(text)
    for m in _CSS_COMMENT.finditer(text):
        for i in range(m.start(), m.end()):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def occurrences(original: str) -> list[tuple[int, str]]:
    """>[(偏移, 字面量)]，只取声明位置。"""
    masked = mask_declarations(blank_comments(original))
    return [(m.start(), m.group(0)) for m in _COLOR.finditer(masked)]


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def load_maps() -> tuple[dict[str, str], Counter, dict[str, int]]:
    """-> (值→令牌, (文件, 值)→期望次数, 值→ΔRGB)。逐行交叉校验两份映射。"""
    token_of: dict[str, str] = {}
    delta_of: dict[str, int] = {}
    for line in MAP_VALUES.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        literal, _alpha, token, delta, _occ = line.split("\t")
        token_of[literal] = token
        delta_of[literal] = int(delta)
    expected: Counter = Counter()
    conflicts: list[str] = []
    for line in MAP_FINAL.read_text(encoding="utf-8").splitlines()[1:]:
        if not line.strip():
            continue
        rel, _lineno, _prop, literal, token, delta = line.split("\t")
        expected[(rel, literal)] += 1
        if token_of.get(literal) != token:
            conflicts.append(f"{literal}: map-final 说 {token}，map-values 说 {token_of.get(literal)}")
        if delta_of.get(literal) != int(delta):
            conflicts.append(f"{literal}: map-final Δ{delta} ≠ map-values Δ{delta_of.get(literal)}")
        if int(delta) > 12:
            conflicts.append(f"{literal}: ΔRGB={delta} > 12（人裁上限）")
    if conflicts:
        raise SystemExit("映射自相矛盾，中止：\n  " + "\n  ".join(sorted(set(conflicts))))
    return token_of, expected, delta_of


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    token_of, expected, delta_of = load_maps()
    total_plan = 0
    per_file: dict[str, Counter] = {}
    writes: dict[Path, str] = {}

    for rel in TARGETS:
        path = ROOT / rel
        original = path.read_text(encoding="utf-8")
        hits = occurrences(original)
        actual = Counter(literal for _off, literal in hits)
        per_file[rel] = actual
        want = Counter({literal: count for (f, literal), count in expected.items() if f == rel})
        if actual != want:
            only_actual = actual - want
            only_want = want - actual
            raise SystemExit(
                f"{rel} 的字面量计数与 map-final.tsv 不一致，中止（不写盘）：\n"
                f"  实测多出: {dict(only_actual)}\n  实测缺少: {dict(only_want)}")
        unmapped = sorted(set(actual) - set(token_of))
        if unmapped:
            raise SystemExit(f"{rel} 有 map 里没有的字面量（unmapped）: {unmapped}")

        print(f"\n=== {rel}：计划替换 {len(hits)} 条 ===")
        for offset, literal in hits:
            print(f"  L{line_of(original, offset):<5d} {literal:<24s} -> var({token_of[literal]})  ΔRGB={delta_of[literal]}")
        total_plan += len(hits)

        # 原位替换：从后往前，偏移不会互相影响
        out = original
        for offset, literal in sorted(hits, key=lambda h: h[0], reverse=True):
            out = out[:offset] + f"var({token_of[literal]})" + out[offset + len(literal):]
        writes[path] = out

    print(f"\n计划合计 {total_plan} 条（app.css {len(per_file[TARGETS[0]])} 种 / "
          f"{sum(per_file[TARGETS[0]].values())} 条；legacy.css "
          f"{len(per_file[TARGETS[1]])} 种 / {sum(per_file[TARGETS[1]].values())} 条）")

    if not apply:
        print("dry-run：未写盘（加 --apply 才执行）")
        return 0

    for path, text in writes.items():
        path.write_text(text, encoding="utf-8")
        left = occurrences(path.read_text(encoding="utf-8"))
        print(f"APPLIED {path.relative_to(ROOT)} 剩余字面量={len(left)}")
        if left:
            raise SystemExit(f"{path} 替换后仍有 {len(left)} 处字面量，停手")
    print("自检：组件层（app.css + legacy.css）颜色字面量 = 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
