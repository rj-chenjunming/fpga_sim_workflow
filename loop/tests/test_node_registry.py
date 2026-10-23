"""R3-15：`GATE_NODES` 与 `GATE_ID_BY_NODE` 是同一事实，只能有一份定义。

`services/node_registry.py` 是唯一来源；`node_story` 与 `node_view` 只是引用/别名。
断言用 `is`（同一对象）而不是 `==`：两份内容相同的字面量会相等但**不是**同一对象，
`is` 才能证明"第二份定义被删掉了"（而不是被复制成一样的内容）。
"""
from __future__ import annotations

import inspect

from services import node_registry, node_story, node_view


def test_gate_nodes_have_exactly_one_declaration() -> None:
    assert node_registry.GATE_NODES is node_registry.GATE_NODES  # noqa: PLR0124 — 见上
    assert node_registry.GATE_NODES == frozenset({"N4", "N13", "N14"})
    assert node_registry.GATE_NODES == frozenset(node_registry.GATE_ID_BY_NODE)
    assert node_registry.GATE_ID_BY_NODE == {
        "N4": "G1_diff_confirm",
        "N13": "G2_report_accept",
        "N14": "G3_regression_decision",
    }


def test_consumers_share_the_single_source() -> None:
    assert node_view.GATE_ID_BY_NODE is node_registry.GATE_ID_BY_NODE
    assert node_story.GATE_NODES is node_registry.GATE_NODES


def test_no_second_literal_definition_in_consumers() -> None:
    """结构断言：两个消费模块里不得再出现"节点→闸门 id"的字面量表定义。"""
    for module in (node_story, node_view):
        source = inspect.getsource(module)
        assert '"N4": "G1_diff_confirm"' not in source, module.__name__
        assert '{"N4", "N13", "N14"}' not in source, module.__name__
