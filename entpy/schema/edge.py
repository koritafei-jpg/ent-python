"""边构建器。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from entpy.schema.base import Schema


class RelType(str, Enum):
    O2O = "O2O"
    O2M = "O2M"
    M2O = "M2O"
    M2M = "M2M"


@dataclass
class EdgeDescriptor:
    name: str
    typ: type[Schema] | Any
    inverse: bool = False  # edge.From 时为 True
    ref: str | None = None
    unique: bool = False
    required: bool = False
    storage_key: str | None = None
    through: type[Schema] | None = None
    rel: RelType | None = None
    fk_columns: list[str] | None = None
    join_table: str | None = None


class Edge:
    def __init__(self, descriptor: EdgeDescriptor) -> None:
        self._d = descriptor

    def descriptor(self) -> EdgeDescriptor:
        return self._d

    def ref(self, name: str) -> Edge:
        self._d.ref = name
        return self

    def unique(self) -> Edge:
        self._d.unique = True
        return self

    def required(self) -> Edge:
        self._d.required = True
        return self

    def storage_key(self, key: str) -> Edge:
        self._d.storage_key = key
        return self

    def through(self, schema: type[Schema]) -> Edge:
        self._d.through = schema
        return self


def to(name: str, typ: type[Schema], /, **kwargs: Any) -> Edge:
    d = EdgeDescriptor(name=name, typ=typ, inverse=False, **kwargs)
    return Edge(d)


def from_(name: str, typ: type[Schema], /, **kwargs: Any) -> Edge:
    d = EdgeDescriptor(name=name, typ=typ, inverse=True, **kwargs)
    return Edge(d)
