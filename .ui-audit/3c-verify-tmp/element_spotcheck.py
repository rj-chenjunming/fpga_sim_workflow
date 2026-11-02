#!/usr/bin/env python3
"""复核员自写：抽查「逐元素计算样式指纹哈希」是否 before/after 一致（不只看汇总）。

复用被测工具里**冻结的采集函数**（capture_side / serve_dir，保证与 Lead 的 196 组合同口径），
但比较逻辑与报告由我自己写：按元素逐个打印 label + 双哈希，统计不一致元素数。
"""
import importlib.util, sys, os, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vse", REPO / ".ui-audit/3c/verify_style_equivalence.py")
vse = importlib.util.module_from_spec(spec); sys.modules["vse"] = vse
spec.loader.exec_module(vse)
from playwright.sync_api import sync_playwright

BEFORE = REPO / ".ui-audit/3c/snap-before"
AFTER = REPO / ".ui-audit/3c/web-stage"
# 主视口 + 窄断点（760 是旧 P0 会现形的区间）+ 中宽（851/1000）
PAIRS = [(1280, 720, "s0"), (1280, 720, "gate"), (760, 1000, "run"),
         (1000, 1000, "s0"), (851, 1000, "agent"), (1920, 1080, "node-detail")]

print("开跑时间:", time.strftime("%H:%M:%S"), "before=", BEFORE, "after=", AFTER, flush=True)
bs, bt, burl = vse.serve_dir(BEFORE)
as_, at, aurl = vse.serve_dir(AFTER)
try:
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        try:
            cb = vse.capture_side(br, burl, PAIRS)
            ca = vse.capture_side(br, aurl, PAIRS)
        finally:
            br.close()
finally:
    for s, t in ((bs, bt), (as_, at)):
        s.shutdown(); s.server_close(); t.join()

bad = 0
for pair in PAIRS:
    b, a = cb[pair], ca[pair]
    bfp, afp = b["fp"], a["fp"]
    same = [x[1] for x in bfp] == [x[1] for x in afp]
    diffn = sum(1 for i in range(min(len(bfp), len(afp))) if bfp[i][1] != afp[i][1])
    bad += 0 if same else 1
    print(f"\n=== {pair[2]} @ {pair[0]}x{pair[1]} ===")
    print(f"  元素数 before={len(bfp)} after={len(afp)}；哈希序列相同={same}；不一致元素={diffn}")
    for i in range(min(6, len(bfp))):
        print(f"  [{i:>3}] {bfp[i][0]:<46} before={bfp[i][1][:16]}… after={afp[i][1][:16]}… "
              f"{'一致' if bfp[i][1]==afp[i][1] else '★不一致'}")
    # 规则序列：只报条数，作为「结构收敛」的旁证
    print(f"  规则序列条数 before={len(b['rules'])} after={len(a['rules'])}")
print(f"\n结论：{len(PAIRS)} 个组合中，逐元素哈希不一致的组合数 = {bad}")
sys.exit(0 if bad == 0 else 1)
