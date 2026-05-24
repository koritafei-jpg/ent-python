"""sqlgraph 操作规格。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

from entpy.schema.edge import RelType


@dataclass
class EdgeSpec:
    rel: RelType
    name: str
    peer_table: str
    ids: list[Any] = dc_field(default_factory=list)
    fk_columns: list[str] = dc_field(default_factory=list)
    join_table: str | None = None
    join_columns: list[str] = dc_field(default_factory=list)
    replace: bool = False


@dataclass
class CreateSpec:
    table: str
    fields: dict[str, Any]
    edges: list[EdgeSpec] = dc_field(default_factory=list)


@dataclass
class UpdateSpec:
    table: str
    id: Any
    fields: dict[str, Any]
    edges: list[EdgeSpec] = dc_field(default_factory=list)


@dataclass
class DeleteSpec:
    table: str
    ids: list[Any] = dc_field(default_factory=list)
    predicates: list[Any] = dc_field(default_factory=list)


@dataclass
class QuerySpec:
    table: str
    predicates: list[Any] = dc_field(default_factory=list)
    limit: int | None = None
    order_by: list[Any] = dc_field(default_factory=list)
    with_edges: list[str] = dc_field(default_factory=list)
