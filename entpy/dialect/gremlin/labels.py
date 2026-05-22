"""Gremlin 顶点/边标签辅助函数。"""

from __future__ import annotations

from entpy.ir.descriptor import NodeDescriptor
from entpy.ir.graph import ResolvedEdge


def vertex_label(node: NodeDescriptor) -> str:
    return node.resolved_table()


def edge_label(edge: ResolvedEdge) -> str:
    return f"{edge.owner.name.lower()}_{edge.name}"
