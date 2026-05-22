"""内置 Schema 混入。"""

from __future__ import annotations

from datetime import datetime, timezone

from entpy.schema import field
from entpy.schema.base import Mixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CreateTimeMixin(Mixin):
    @classmethod
    def fields(cls):
        return [
            field.time("create_time").default_func(_utcnow).immutable(),
        ]


class UpdateTimeMixin(Mixin):
    @classmethod
    def fields(cls):
        return [
            field.time("update_time").default_func(_utcnow),
        ]


class TimeMixin(Mixin):
    @classmethod
    def fields(cls):
        return CreateTimeMixin.fields() + UpdateTimeMixin.fields()
