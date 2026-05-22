"""将 Schema 类加载为 NodeDescriptor。"""

from __future__ import annotations

import inspect

from entpy.schema.base import Mixin, Schema, View
from entpy.schema.edge import Edge
from entpy.schema.field import Field
from entpy.schema.index import Index
from entpy.ir.descriptor import NodeDescriptor


def load_schemas(schemas: list[type[Schema]]) -> list[NodeDescriptor]:
    """从 Schema 类构建节点描述符。"""
    nodes: list[NodeDescriptor] = []
    for cls in schemas:
        if not inspect.isclass(cls) or not issubclass(cls, Schema):
            raise TypeError(f"{cls!r} is not a Schema subclass")
        nodes.append(_load_one(cls))
    return nodes


def _load_one(cls: type[Schema]) -> NodeDescriptor:
    fields: list = []
    edges: list = []
    indexes: list = []

    for mixin in cls.mixins():
        if not issubclass(mixin, Mixin):
            continue
        fields.extend(f.descriptor() for f in mixin.fields() if isinstance(f, Field))
        edges.extend(e.descriptor() for e in mixin.edges() if isinstance(e, Edge))
        indexes.extend(i.descriptor() for i in mixin.indexes() if isinstance(i, Index))

    fields.extend(f.descriptor() for f in cls.fields() if isinstance(f, Field))
    edges.extend(e.descriptor() for e in cls.edges() if isinstance(e, Edge))
    indexes.extend(i.descriptor() for i in cls.indexes() if isinstance(i, Index))

    seen: dict[str, int] = {}
    merged_fields = []
    for f in fields:
        if f.name in seen:
            merged_fields[seen[f.name]] = f
        else:
            seen[f.name] = len(merged_fields)
            merged_fields.append(f)

    return NodeDescriptor(
        name=cls.type_name(),
        schema_type=cls,
        view=issubclass(cls, View),
        fields=merged_fields,
        edges=edges,
        indexes=indexes,
    )
