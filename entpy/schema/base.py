"""Schema 基类。"""

from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from entpy.schema.edge import Edge
    from entpy.schema.field import Field
    from entpy.schema.index import Index
    from entpy.schema.search import SearchConfig


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> UUID:
    return uuid4()


class Schema(ABC):
    """实体 Schema 定义（对应 ent.Schema）。"""

    @classmethod
    def type_name(cls) -> str:
        return cls.__name__

    @classmethod
    def fields(cls) -> list[Field]:
        return []

    @classmethod
    def edges(cls) -> list[Edge]:
        return []

    @classmethod
    def indexes(cls) -> list[Index]:
        return []

    @classmethod
    def mixins(cls) -> list[type[Mixin]]:
        return []

    @classmethod
    def hooks(cls) -> list[Any]:
        return []

    @classmethod
    def interceptors(cls) -> list[Any]:
        return []

    @classmethod
    def policy(cls) -> Any:
        return None

    @classmethod
    def annotations(cls) -> list[Any]:
        return []


class BaseSchema(Schema):
    """实体抽象基类：UUID 主键 + 创建/软删除时间戳。"""

    @classmethod
    def fields(cls) -> list[Field]:
        from entpy.schema import field

        return [
            field.uuid("id").default_func(_new_uuid).immutable().unique(),
            field.time("create_time").default_func(_utcnow).immutable(),
            field.time("delete_time").optional(),
        ]


class View(Schema):
    """只读 Schema — 无 create/update/delete 构建器。"""


class Mixin(ABC):
    """混入：扩展 Schema 的字段/边/hooks。"""

    @classmethod
    def fields(cls) -> list[Field]:
        return []

    @classmethod
    def edges(cls) -> list[Edge]:
        return []

    @classmethod
    def indexes(cls) -> list[Index]:
        return []

    @classmethod
    def hooks(cls) -> list[Any]:
        return []

    @classmethod
    def interceptors(cls) -> list[Any]:
        return []

    @classmethod
    def policy(cls) -> Any:
        return None

    @classmethod
    def annotations(cls) -> list[Any]:
        return []


class SearchMixin:
    """可检索实体混入（RAG / 混合检索）。"""

    @classmethod
    def search_config(cls) -> SearchConfig | None:
        return None
