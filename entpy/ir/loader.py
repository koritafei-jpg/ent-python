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


def _collect_fields(cls: type[Schema]) -> list:
    """沿 MRO 合并各层 Schema 子类的 fields（子类覆盖同名基类字段）。"""
    fields: list = []
    seen: dict[str, int] = {}
    for base in reversed(cls.__mro__):
        if base is object or not issubclass(base, Schema) or base is Schema:
            continue
        for f in base.fields():
            if not isinstance(f, Field):
                continue
            d = f.descriptor()
            if d.name in seen:
                fields[seen[d.name]] = d
            else:
                seen[d.name] = len(fields)
                fields.append(d)
    return fields


def _load_one(cls: type[Schema]) -> NodeDescriptor:
    edges: list = []
    indexes: list = []

    for mixin in cls.mixins():
        if not issubclass(mixin, Mixin):
            continue
        edges.extend(e.descriptor() for e in mixin.edges() if isinstance(e, Edge))
        indexes.extend(i.descriptor() for i in mixin.indexes() if isinstance(i, Index))

    merged_fields = _collect_fields(cls)
    edges.extend(e.descriptor() for e in cls.edges() if isinstance(e, Edge))
    indexes.extend(i.descriptor() for i in cls.indexes() if isinstance(i, Index))

    return NodeDescriptor(
        name=cls.type_name(),
        schema_type=cls,
        view=issubclass(cls, View),
        fields=merged_fields,
        edges=edges,
        indexes=indexes,
    )
