"""GATE-1 文案中性化守卫（批次 4 · B 项，软件层，不启浏览器）。

事实与授权（见 `doc/plans/2026-10-30-ui-batch4.md` §B 与 `.ui-audit/4/gate-identity.md`）：

- `kb/tools/kb_lib.py` 的 `GATE_DECISIONS` 只有 `G1_diff_confirm` / `G2_report_accept` /
  `G3_regression_decision` 三个键，**没有** `GATE-1`；`doc/spec/S0_ENVIRONMENT_SPEC.md:11`
  又明说「S0 不新增闸门」。所以界面自己造的 `GATE-1` 是在下达一个权威里不存在的身份
  （`AGENTS.md` §5 红线 4 的邻域）。
- 本批次只做**文案中性化**：界面不再出现任何闸门 id，改用 S0 规格既有词汇
  （「S0 两段」「S0-b」「接口复核」「准出」）。**`GATE-1` ↔ `G1` 的身份映射仍待裁**，
  本用例既不断言映射成立，也不允许界面提前暗示它。
- 不改 `kb/**`（冻结）、不改闸门判据、不改后端、不改任何既有测试判据。

本用例是三条**不读源码也能判定**的不变式（AGENTS §2.1 第 3 条）：

1. `loop/web/**`（`.html` / `.js`）里 `GATE-1` 出现 **0** 次；
2. 中性文案确实出现在三处，且「首屏兜底文本」（`index.html` 的 `#s0SubmitHint`）与
   「busy 态恢复文本」（`s0.js` 的 `else` 分支字符串）**逐字相同**（防双写漂移）；
3. `kb/tools/kb_lib.py` 的 `GATE_IDS` / `GATE_DECISIONS` 仍是原值（**只读解析**：
   用 `ast` 读字面量，不 `import kb_lib`，避免在冻结目录生成 `__pycache__`）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
REPO = Path(__file__).resolve().parents[2]
KB_LIB = REPO / "kb" / "tools" / "kb_lib.py"

#: §2.1 落点 1 + §2.3 落点 3 的同一段文案（必须逐字一致）。
HINT = "准出与切换由服务端判定；准备完成后仍需 S0-b 接口复核"
#: §2.2 落点 2（`#s0Blockers` 第二段兜底）。
BLOCKER = "完成 S0 两段（含 S0-b 接口复核与准出判定）后才能进入新版执行。"
#: 交付前必须为 0 的过时身份名（形状守卫：`GATE-<数字>` 一并禁止，防止换个号又自建）。
FORBIDDEN = re.compile(r"GATE-\d")


def _web_texts() -> dict[str, str]:
    """`loop/web/**` 的组件层文本（`.html` / `.js`），按文件名索引。"""
    texts: dict[str, str] = {}
    for path in sorted(WEB.rglob("*")):
        if path.suffix not in {".html", ".js"}:
            continue
        texts[str(path.relative_to(WEB))] = path.read_text(encoding="utf-8")
    return texts


def _kb_gate_ids() -> tuple[str, ...]:
    """解析 `GATE_IDS`：既支持纯字面量，也支持「GATE_IDS_V1 + (...)」的追加形态。

    2026-10-30 授权变更把 `GATE_IDS` 写成 `GATE_IDS_V1 + ("G1_no_impact",)`，
    这里只按 AST 还原成元组，不 import 冻结目录（仍不生成 __pycache__）。
    """
    tree = ast.parse(KB_LIB.read_text(encoding="utf-8"))
    values: dict[str, tuple[str, ...]] = {}
    expr: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            try:
                literal = ast.literal_eval(node.value)
            except ValueError:
                literal = None
            if name == "GATE_IDS":
                expr = node.value
            if isinstance(literal, tuple) and all(isinstance(v, str) for v in literal):
                values[name] = literal

    def resolve(node: ast.AST) -> tuple[str, ...]:
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return resolve(node.left) + resolve(node.right)
        literal = ast.literal_eval(node)
        return tuple(literal)

    assert expr is not None, "kb_lib.py 里找不到模块级赋值 GATE_IDS"
    return resolve(expr)


def _kb_dict(name: str) -> object:
    """从 `kb_lib.py` 源码里取模块级字面量赋值（只读，不 import 冻结目录）。"""
    tree = ast.parse(KB_LIB.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise AssertionError(f"kb_lib.py 里找不到模块级赋值 {name}")


# ---------------------------------------------------------------- ① GATE-1 归零

def test_no_gate_1_identity_literal_in_web_layer() -> None:
    """界面不得再下达权威里不存在的 `GATE-1` 身份（三处文案改中性化）。"""
    offenders = {
        name: text.count("GATE-1")
        for name, text in _web_texts().items()
        if "GATE-1" in text
    }
    assert not offenders, f"loop/web 仍有 GATE-1：{offenders}"


def test_no_new_gate_identity_is_invented_by_ui() -> None:
    """反向护栏：不许换个号自建闸门名（`GATE-2` / `GATE-3` … 同样禁止）。

    `G1_diff_confirm` / `G2_report_accept` / `G3_regression_decision` 是服务端下发的身份，
    界面只消费、不手抄，所以这里只卡「`GATE-<数字>`」这种自造代号。
    """
    offenders = {
        name: FORBIDDEN.findall(text)
        for name, text in _web_texts().items()
        if FORBIDDEN.search(text)
    }
    assert not offenders, f"界面自建了闸门代号：{offenders}"


# ---------------------------------------------------------------- ② 中性文案三处

def test_neutral_copy_replaces_the_three_spots() -> None:
    index_html = _web_texts()["index.html"]
    s0_js = _web_texts()["s0.js"]
    # 落点 1：首屏兜底（主操作行左提示）
    assert HINT in index_html, "index.html 的 #s0SubmitHint 缺少中性文案"
    # 落点 2：执行前 blocked 兜底段落
    assert BLOCKER in index_html, "index.html 的 #s0Blockers 缺少中性文案"
    # 落点 3：busy 态恢复时覆盖同一段提示
    assert HINT in s0_js, "s0.js 的 setBusy() 缺少中性文案"


def test_hint_copy_is_identical_in_html_and_js() -> None:
    """两处双写必须逐字相同：否则 busy 恢复后提示与首屏兜底不一致。"""
    index_html = _web_texts()["index.html"]
    s0_js = _web_texts()["s0.js"]
    hint_ids = index_html.count('id="s0SubmitHint"')
    assert hint_ids == 1, f"#s0SubmitHint 应唯一，实际 {hint_ids} 处"
    # 取 index.html 里 #s0SubmitHint 元素的文本（到下一个 '<' 为止）
    match = re.search(r'id="s0SubmitHint"[^>]*>([^<]*)<', index_html)
    assert match, "index.html 找不到 #s0SubmitHint 的文本节点"
    html_text = match.group(1).strip()
    assert html_text == HINT, f"#s0SubmitHint 文本漂移：{html_text!r}"
    # s0.js 的 else 分支字符串
    branch = re.search(r':\s*"([^"]*S0-b 接口复核[^"]*)"\s*;', s0_js)
    assert branch, "s0.js 找不到含中性文案的 else 分支字符串"
    assert branch.group(1) == HINT, f"s0.js 提示与 index.html 不一致：{branch.group(1)!r}"


# ---------------------------------------------------------------- ③ kb 未动

def test_gate_decisions_in_frozen_kb_are_untouched() -> None:
    """三道**主线**闸门的枚举仍是原值——证明本 UI 批次没动它们。

    2026-10-30 授权变更（LOG §14，见 `doc/plans/2026-10-30-zero-must-change-gate.md`）：
    `GATE_IDS` 末尾**追加**了 `G1_no_impact`（N5 必改=0 的 G1 分流支线），
    因此本用例改为「前三项与前三个枚举逐值不变 + 第四项只允许是这条已授权的分流门」。
    """
    ids = _kb_gate_ids()
    decisions = _kb_dict("GATE_DECISIONS")
    assert ids[:3] == ("G1_diff_confirm", "G2_report_accept", "G3_regression_decision"), ids
    assert ids[3:] == ("G1_no_impact",), ids      # 只允许追加这一条（已授权变更）
    assert set(decisions) == {"G1_diff_confirm", "G2_report_accept", "G3_regression_decision",
                              "G1_no_impact"}, decisions
    assert decisions["G1_no_impact"] == ["no_impact_end", "full_regression", "pending"], decisions
    assert decisions["G1_diff_confirm"] == ["confirmed", "ignored", "disputed", "pending"], decisions
    assert decisions["G2_report_accept"] == ["accept", "rework", "pending"], decisions
    assert decisions["G3_regression_decision"] == [
        "full_now",
        "subset_only",
        "milestone_only",
        "defer",
        "pending",
    ], decisions


def test_frozen_kb_lib_has_no_gate_1_name() -> None:
    """`GATE-1` 不是权威枚举的一部分：冻结目录里也不许出现（只读断言）。"""
    assert "GATE-1" not in KB_LIB.read_text(encoding="utf-8")
