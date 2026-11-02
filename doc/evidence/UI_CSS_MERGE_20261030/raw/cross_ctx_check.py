#!/usr/bin/env python3
"""复核用：把「同名选择器跨 @ 上下文的生效先后是否被改动」做成可复跑检查。

判据（与 CSS 级联语义一致，不依赖共命中证据）：
  同一简单选择器 S 在 @ 上下文 A / B 各有一条声明 longhand p（同重要性），
  且 A、B 的媒体条件可能在同一视口同时成立；则 S 命中的元素在两处生效者 = 文档位置更靠后的一条。
  若 before/after 的生效者互换，且两条声明**值不同** ⇒ 该元素的 p 计算值改变 ⇒ FAIL。

用法：
  python3 cross_ctx_check.py <before.css> <after.css>
退出码：0 = 无翻转；1 = 有翻转（逐条打印）；2 = 参数错。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indep_cascade as ic


def effective(rules):
    """(ctx, longhand) -> {simple: (important, pos, value)}，pos 为全局声明序号。"""
    from collections import defaultdict
    g = defaultdict(dict)
    pos = 0
    for r in rules:
        for s in r["sel_list"]:
            for prop, value, imp in r["decls"]:
                for lh, val in ic.longhand_map(prop, value).items():
                    cur = g[(r["ctx"], lh)].get(s)
                    if cur is None or imp >= cur[0]:
                        g[(r["ctx"], lh)][s] = (imp, pos, val)
                pos += 1
    return g


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    before, after = sys.argv[1], sys.argv[2]
    b = ic.parse_css(open(before, encoding="utf-8").read())
    a = ic.parse_css(open(after, encoding="utf-8").read())
    eb, ea = effective(b), effective(a)

    # 我只关心「同一简单选择器的不同 @ 上下文」：把 (ctx, lh) 键按 simple 归并
    per_key_b, per_key_a = {}, {}
    for (ctx, lh), m in eb.items():
        for s, v in m.items():
            per_key_b.setdefault((s, lh), {})[ctx] = v
    for (ctx, lh), m in ea.items():
        for s, v in m.items():
            per_key_a.setdefault((s, lh), {})[ctx] = v

    fails = []
    for key in sorted(set(per_key_b) & set(per_key_a)):
        s, lh = key
        mb, ma = per_key_b[key], per_key_a[key]
        cs = sorted(set(mb) & set(ma))
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                c1, c2 = cs[i], cs[j]
                if not ic.contexts_compatible(c1, c2):
                    continue
                (i1, p1, v1), (i2, p2, v2) = mb[c1], mb[c2]
                if i1 != i2:                     # 重要性不同 ⇒ 源码先后无关
                    continue
                if v1 == v2:                     # 值相同 ⇒ 谁赢都一样
                    continue
                win_b = c1 if p1 > p2 else c2
                win_a = c1 if ma[c1][1] > ma[c2][1] else c2
                if win_b != win_a:
                    fails.append((s, lh, c1, c2, mb[c1][2], mb[c2][2],
                                  " ".join(win_b) or "top", " ".join(win_a) or "top",
                                  (p1, p2), (ma[c1][1], ma[c2][1])))

    print(f"before={before}\nafter ={after}")
    print(f"跨 @ 上下文、同选择器、同属性、可能同时生效、值不同的对：{len(fails)} 处翻转")
    for s, lh, c1, c2, v1, v2, wb, wa, pb, pa in fails:
        print(f"  FAIL {s}  {lh}:  [{c1 or 'top'}]={v1} vs [{c2 or 'top'}]={v2}")
        print(f"        生效者 before={wb} (位置 {pb[0]}/{pb[1]})  →  after={wa} (位置 {pa[0]}/{pa[1]})")
    if fails:
        print("FAIL: 同名选择器跨 @ 上下文的生效先后被改动 ⇒ 断点区间内计算样式会变")
        return 1
    print("PASS: 未发现同名选择器跨 @ 上下文的发生效先后翻转")
    return 0


if __name__ == "__main__":
    sys.exit(main())
