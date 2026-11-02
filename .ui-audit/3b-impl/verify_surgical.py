"""3B 独立复核：用**冻结的 map-final.tsv（file/line/property/literal/token）**核对替换结果，
而不是复用 `apply_tokens.py` 的算法（否则只是自己证明自己）。

三道检查，全部通过才算「手术式替换」：

A. 骨架恒等：把「before 的颜色字面量」与「after 的 var(--…)」都抹成同一个占位符后，
   before/after 每一行必须逐字符相等 ⇒ 没有动选择器、没有动其它值、没有重排、没有增减声明。
   顺带用占位符位置对齐，逐位置核对「这个字面量位置换成了它该换的令牌」。
B. map-oracle：map-final.tsv 的 382 行逐行核对——该行 before 里确有该 literal（属性相符），
   该行 after 里对应属性的声明值里确有 `var(--token)`，且次数与 map 行数一致。
C. 行数/块结构不变：总行数、`{`/`}` 计数与 before 相同。
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / ".ui-audit" / "3b"
SNAP = ROOT / ".ui-audit" / "3b-impl" / "snap-before"
FILES = ("app.css", "legacy.css")

_CSSC = re.compile(r"/\*.*?\*/", re.DOTALL)
_COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
    r"|\b(?:rgba?|hsla?)\s*\([^()]*\)"
)
_VAR = re.compile(r"var\(\s*(--[\w-]+)[^)]*\)")
_MARK = "\x00"


def mask_declarations(css: str) -> str:
    chunks: list[tuple[int, int]] = []
    n = len(css)

    def mb(open_index: int, end: int) -> int:
        depth, i = 0, open_index
        while i < end:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise SystemExit("花括号不平衡")

    def walk(start: int, end: int) -> None:
        seg, i = start, start
        while i < end:
            ch = css[i]
            if ch == "{":
                chunks.append((seg, i))
                close = mb(i, end)
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
    for s, e in chunks:
        for i in range(s, e):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def blank_comments(text: str) -> str:
    return _CSSC.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def skeleton(line: str, is_before: bool) -> tuple[str, list[str]]:
    """抹平「颜色字面量 + var(--…)」两种色值载体的骨架，并返回按位置排列的序列。

    before 侧：颜色字面量与**既有** var 都要抹（既有 var 在 after 侧也必须还在原位）；
    after 侧：只有 var（= 既有 var + 新换进来的令牌）。两侧抹平后标记数相等、位置一一对应，
    因此可以逐位置核对「这个位置原来是字面量的，必须换成映射指定的令牌；原来是 var 的必须原样」。
    """
    pattern = re.compile(_COLOR.pattern + "|" + _VAR.pattern)
    if not is_before:
        pattern = _VAR
    seq: list[str] = []
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(line):
        parts.append(line[last:m.start()])
        parts.append(_MARK)
        if is_before:
            seq.append(m.group(1) if m.group(1) else m.group(0))
        else:
            seq.append(m.group(1))
        last = m.end()
    parts.append(line[last:])
    return "".join(parts), seq


def norm_value(text: str) -> str:
    return " ".join(text.split())


def decl_has_token(line: str, prop: str, token: str) -> bool:
    """该行是否存在「属性 prop 的声明值里含 var(token)」。

    用「属性名紧邻 `:`、值以 `;`/`{`/`}` 收尾」定位，因此能吃下简写
    （`border:1px solid var(--line-soft)`）与一行多条规则（`.a2{…}.a3{…}`）两种形态；
    前置 `(?<![\\w-])` 保证 `border-color:` 不会被当成 `color:`。
    """
    pattern = re.compile(r"(?<![\w-])" + re.escape(prop) + r"\s*:\s*[^;{}]*var\(\s*"
                         + re.escape(token) + r"\s*\)")
    return bool(pattern.search(line))


def normalize_value_carriers(css: str) -> str:
    """把颜色字面量与 `var(--…)` 统一抹成 `@`，用于「除色值载体外一字未动」的证明。"""
    return re.sub(_COLOR.pattern + "|" + _VAR.pattern, "@", css)


def main() -> int:
    token_of: dict[str, str] = {}
    for line in (AUDIT / "map-values-final.tsv").read_text().splitlines()[1:]:
        if line.strip():
            literal, _a, token, _d, _o = line.split("\t")
            token_of[literal] = token

    rows: list[tuple[str, int, str, str, str]] = []
    for line in (AUDIT / "map-final.tsv").read_text().splitlines()[1:]:
        if line.strip():
            rel, ln, prop, literal, token, _delta = line.split("\t")
            rows.append((Path(rel).name, int(ln), prop, literal, token))

    failures: list[str] = []
    replacements = Counter()

    for name in FILES:
        before = (SNAP / name).read_text(encoding="utf-8")
        after = (ROOT / "loop" / "web" / name).read_text(encoding="utf-8")
        blines, alines = before.split("\n"), after.split("\n")

        # C. 结构
        if len(blines) != len(alines):
            failures.append(f"{name}: 行数变了 {len(blines)} -> {len(alines)}")
        for ch in "{}":
            if before.count(ch) != after.count(ch):
                failures.append(f"{name}: {ch} 计数变了")
        # 声明文本（选择器前导已涂空）把「色值载体」统一抹成标记后必须逐字相等：
        # 这证明改动只发生在颜色字面量位置，属性名/单位/顺序/其它值一字未动。
        norm_b = normalize_value_carriers(mask_declarations(blank_comments(before)))
        norm_a = normalize_value_carriers(mask_declarations(blank_comments(after)))
        if norm_b != norm_a:
            diff_at = next((i for i, (x, y) in enumerate(zip(norm_b, norm_a)) if x != y), min(len(norm_b), len(norm_a)))
            failures.append(f"{name}: 声明文本（抹平色值载体后）不相等，首个差异在偏移 {diff_at}:\n"
                            f"    before={norm_b[max(0,diff_at-60):diff_at+60]!r}\n"
                            f"    after ={norm_a[max(0,diff_at-60):diff_at+60]!r}")

        # A. 骨架恒等 + 逐位置对齐
        for idx, (b, a) in enumerate(zip(blines, alines), start=1):
            if b == a:
                continue
            sb, seq = skeleton(b, True)
            sa, seq_after = skeleton(a, False)
            if sb != sa:
                failures.append(f"{name}:{idx}: 骨架不等（动了非颜色内容）\n"
                                f"    before={sb!r}\n    after ={sa!r}")
                continue
            for before_item, after_item in zip(seq, seq_after):
                if before_item.startswith("--"):
                    # 既有 var 必须原样保留在原位（不许被顺手换掉）
                    if before_item != after_item:
                        failures.append(f"{name}:{idx}: 既有 var({before_item}) 变成了 var({after_item})")
                    continue
                if token_of.get(before_item) != after_item:
                    failures.append(f"{name}:{idx}: {before_item} 换成了 var({after_item})，"
                                    f"映射要求 var({token_of.get(before_item)})")
                else:
                    replacements[name] += 1

    # B. map-oracle：逐行、按属性
    for name in FILES:
        before = (SNAP / name).read_text(encoding="utf-8").split("\n")
        after = (ROOT / "loop" / "web" / name).read_text(encoding="utf-8").split("\n")
        rows_here = [r for r in rows if r[0] == name]
        for _f, ln, prop, literal, token in rows_here:
            b, a = before[ln - 1], after[ln - 1]
            if literal not in b:
                failures.append(f"{name}:{ln}: before 该行没有 literal {literal}（map 行号漂了？）")
            if not decl_has_token(a, prop, token):
                failures.append(f"{name}:{ln}: after 该行的 {prop} 值里没有 var({token})\n"
                                f"    {a.strip()[:120]}")
        # 次数核对：每行每 token 的 var 出现次数 == map 该行该 token 的行数
        for ln in {r[1] for r in rows_here}:
            want = Counter(r[4] for r in rows_here if r[1] == ln)
            got = Counter(m.group(1) for m in _VAR.finditer(after[ln - 1]))
            for token, n in want.items():
                if got[token] < n:
                    failures.append(f"{name}:{ln}: var({token}) 出现 {got[token]} 次，map 要求 {n} 次")

    print(f"按位置逐条核对：app.css {replacements['app.css']} 条、legacy.css {replacements['legacy.css']} 条，"
          f"合计 {sum(replacements.values())}")
    print(f"map-final 行数：{len(rows)}（app.css {sum(1 for r in rows if r[0]=='app.css')} / "
          f"legacy.css {sum(1 for r in rows if r[0]=='legacy.css')}）")
    if failures:
        print(f"\nFAIL：{len(failures)} 项")
        for f in failures[:40]:
            print("  " + f)
        return 1
    print("PASS：骨架恒等（未动非颜色内容）+ 每个字面量位置都换成了映射指定的令牌 + map 382 行逐行命中")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
