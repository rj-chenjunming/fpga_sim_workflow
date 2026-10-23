"""闸门节点 ↔ 闸门 id 的**唯一**登记（R3-15：消灭同一事实的两份定义）。

`services.node_story.GATE_NODES` 与 `services.node_view.GATE_ID_BY_NODE` 曾经各写一份；
本模块是唯一来源，两个消费方都从这里引用（各自保留同名别名，避免外部 import 破裂）。

只读常量，不含逻辑：节点名与闸门 id 的权威枚举仍分别是
`node_view.NODE_CATALOG` 与 `host.gate_authority`（本模块只是把"哪些是闸门节点"这一层对齐）。
"""

from __future__ import annotations

#: 闸门节点 → 闸门 id（权威枚举止 `host.gate_authority.gate_ids()`；这里只做节点视角的映射）。
GATE_ID_BY_NODE: dict[str, str] = {
    "N4": "G1_diff_confirm",
    "N13": "G2_report_accept",
    "N14": "G3_regression_decision",
}

#: 闸门节点集合（由上面的映射派生，不再手抄第二份）。
GATE_NODES: frozenset[str] = frozenset(GATE_ID_BY_NODE)

__all__ = ["GATE_ID_BY_NODE", "GATE_NODES"]
