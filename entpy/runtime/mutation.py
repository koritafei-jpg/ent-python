"""通用变更对象。"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any

from entpy.schema.base import Schema


class Op(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    UPDATE_ONE = "update_one"
    DELETE = "delete"
    DELETE_ONE = "delete_one"


@dataclass
class Mutation:
    schema: type[Schema]
    op: Op
    fields: dict[str, Any] = dc_field(default_factory=dict)
    edges: dict[str, list[Any]] = dc_field(default_factory=dict)
    id: Any | None = None

    def op_is(self, *ops: Op) -> bool:
        return self.op in ops

    def type_name(self) -> str:
        return self.schema.type_name()
