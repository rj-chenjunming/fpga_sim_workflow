#!/usr/bin/env python3
"""F14 静态清单：样式规模、媒体查询断点、`!important` 与重复声明（只读）。

为什么不自动改：没有浏览器就无法看默认/hover/focus/disabled/告警/模态与断点交界处的
实际效果；按 AGENTS §2 与 F14 计划，必须**先人工看图**才能删除/合并规则。
本脚本只提供可复核的事实，不做修改。

用法：`.venv/bin/python spikes/css_inventory.py`
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
FILES = ["tokens.css", "app.css", "legacy.css"]
RULE = re.compile(r"([^{}@]+)\{([^{}]*)\}")


def declarations(body: str) -> list[tuple[str, str]]:
    out = []
    for chunk in body.split(";"):
        if ":" not in chunk:
            continue
        prop, value = chunk.split(":", 1)
        out.append((prop.strip(), value.strip()))
    return out


def main() -> int:
    print(f"web = {WEB}")
    for name in FILES:
        path = WEB / name
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + (0 if text.endswith("\n") else 1)
        media = re.findall(r"@media[^{]+", text)
        important = [m for m in re.finditer(r"[^;{}]*!important[^;{}]*", text)]
        selector_decls: Counter[tuple[str, str, str]] = Counter()
        for match in RULE.finditer(text):
            selectors = [s.strip() for s in match.group(1).split(",") if s.strip()]
            for selector in selectors:
                for prop, value in declarations(match.group(2)):
                    selector_decls[(selector, prop, value)] += 1
        duplicates = sum(1 for count in selector_decls.values() if count > 1)
        print(f"\n== {name}: lines={lines} rules={len(RULE.findall(text))} "
              f"media={len(media)} important={len(important)} duplicate_decls={duplicates}")
        for query in media:
            print(f"   @media {query.strip()}")
        for hit in important:
            snippet = " ".join(hit.group(0).split())
            print(f"   !important: {snippet[:120]}")
        for (selector, prop, value), count in sorted(selector_decls.items()):
            if count > 1:
                print(f"   dup x{count}: {selector} {{ {prop}: {value} }}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
