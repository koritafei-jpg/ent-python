"""IR 描述符（从 Schema 类加载）。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from entpy.schema.edge import EdgeDescriptor, RelType
from entpy.schema.field import FieldDescriptor
from entpy.schema.index import IndexDescriptor


@dataclass
class NodeDescriptor:
    name: str
    schema_type: type
    view: bool = False
    fields: list[FieldDescriptor] = dc_field(default_factory=list)
    edges: list[EdgeDescriptor] = dc_field(default_factory=list)
    indexes: list[IndexDescriptor] = dc_field(default_factory=list)
    table: str | None = None

    @property
    def table_name(self) -> str:
        if self.table:
            return self.table
        return self.name.lower() + "s" if not self.name.lower().endswith("s") else self.name.lower()

    # 简单复数：User -> users, Group -> groups
    def resolved_table(self) -> str:
        n = self.name.lower()
        mapping = {"user": "users", "car": "cars", "group": "groups", "chunk": "chunks"}
        return self.table or mapping.get(n, n + "s")
