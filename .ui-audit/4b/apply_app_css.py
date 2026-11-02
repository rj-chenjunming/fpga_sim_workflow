#!/usr/bin/env python3
"""批次 4 · A 项的 app.css 改动（Lead 执行；按选择器定位，不信行号）。

依据 `.ui-audit/4b/app-css-requests.md`：
  1. 新增 `.icon`（硬依赖：没有它 41 处 <use> 图标渲染成黑色实心块）
  2. 新增 `.icon-30` / `.empty .icon-30`（替代被删的 `.empty:before` 插图）
  3. 删 `.empty:before`（结构已挂内联 svg，不删=双图标）
  4. 删 `.aw-detail summary:before` / `.aw-detail[open] summary:before`（死规则，最后两个 ▸/▾）
  5. 删 3 条失效 font-size（`.nav-icon` 20px、760 断点 `.nav-icon` 16px、`.stage-chev` 11px）
每一步都断言「目标恰好出现一次」，找不到就报错退出（不猜、不静默跳过）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(sys.argv[1] if len(sys.argv) > 1 else
           "/home/work/chenjunming/change-impact-loop/loop/web/app.css")
text = CSS.read_text(encoding="utf-8")
orig = text


def remove_rule(sel: str) -> None:
    """删除整条规则（选择器文本精确匹配，允许前面有空白/在 @media 内）。"""
    global text
    pattern = re.compile(r"(?m)^[ \t]*" + re.escape(sel) + r"\{")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        sys.exit(f"[FAIL] {sel}: 期望 1 条，实际 {len(matches)} 条")
    start = matches[0].start()
    brace = text.index("{", matches[0].end() - 1)
    depth, i = 0, brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    # 连行删（含行尾换行），并压掉多出来的空行
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end < 0 else line_end
    if text[line_start:start].strip() == "" and text[end:line_end].strip() == "":
        text = text[:line_start] + text[line_end + 1:]
    else:
        text = text[:start] + text[end:]
    text = re.sub(r"\n{3,}", "\n\n", text)
    print(f"[ok] 删除规则 {sel}")


def drop_decl(sel: str, prop: str) -> None:
    """在指定规则里删掉某条声明（其余声明与格式逐字保留）。"""
    global text
    pattern = re.compile(r"(?m)^[ \t]*" + re.escape(sel) + r"\{")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        sys.exit(f"[FAIL] {sel}: 期望 1 条，实际 {len(matches)} 条")
    brace = text.index("{", matches[0].end() - 1)
    depth, i = 0, brace
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body_start, body_end = brace + 1, i
    body = text[body_start:body_end]
    decl = re.compile(r"(?m)(^|;)\s*" + re.escape(prop) + r"\s*:[^;{}]*")
    found = list(decl.finditer(body))
    if len(found) != 1:
        sys.exit(f"[FAIL] {sel} 内 {prop}: 期望 1 条声明，实际 {len(found)} 条")
    m = found[0]
    replacement = m.group(1) if m.group(1) == "" else ""
    body_new = body[:m.start()] + replacement + body[m.end():]
    # 清理可能出现的 `;;`
    body_new = re.sub(r";\s*;", ";", body_new)
    text = text[:body_start] + body_new + text[body_end:]
    print(f"[ok] 删除声明 {sel} {{ {prop} }}")


# ---- 3/4：删整条规则 -------------------------------------------------------
for sel in (".empty:before", ".aw-detail summary:before", ".aw-detail[open] summary:before"):
    remove_rule(sel)

# ---- 5：删失效 font-size ---------------------------------------------------
drop_decl(".nav-icon", "font-size")
drop_decl(".nav-icon", "line-height")
drop_decl(".stage-chev", "font-size")
# 760 断点里 `.nav-icon{font-size:16px;width:16px}` 是 @media 内的一条规则，单独处理
m = re.search(r"\.nav-icon\{font-size:16px;width:16px\}", text)
if not m:
    sys.exit("[FAIL] 760 断点 .nav-icon{font-size:16px;width:16px} 未找到")
text = text[:m.start()] + ".nav-icon{width:16px}" + text[m.end():]
print("[ok] 760 断点 .nav-icon 去掉 font-size:16px")

# ---- 1/2：新增图标规则（放在文件末尾，带分节注释） -------------------------
icon_block = """
/* ---------- 图标（WEB_UI_SPEC §14「资产」：本地内联 sprite，零外链、零字体依赖；批次 4 A） ----------
   16×16 = symbol viewBox 的 1:1 尺寸；fill:none + stroke:currentColor 是全部 symbol 的共同描边口径，
   符号内不重复声明；currentColor 让图标继承父元素颜色。不设 font-size（字号受 §14 阶梯/A14 约束）。 */
.icon{width:16px;height:16px;flex:0 0 auto;display:inline-block;vertical-align:-3px;
  fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
/* 空态插图：替代已删的 .empty:before（原 58×58 圆角框逐像素保留；58 − 2 边框 − 26 padding = 30 内容盒） */
.icon-30{width:30px;height:30px;vertical-align:baseline}
.empty .icon-30{display:block;width:58px;height:58px;padding:13px;box-sizing:border-box;
  margin:0 auto 20px;border:1px solid #d6e3d8;border-radius:16px;background:#f0f6f1;color:#60846a}
"""
if ".icon{width:16px;height:16px" in text:
    sys.exit("[FAIL] .icon 规则已存在（重复执行？）")
text = text.rstrip("\n") + "\n" + icon_block
print("[ok] 新增 .icon / .icon-30 / .empty .icon-30")

CSS.write_text(text, encoding="utf-8")
print(f"\n改写完成：{len(orig.splitlines())} → {len(text.splitlines())} 行；{CSS}")
