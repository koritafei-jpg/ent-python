"""Car 实体。"""

from __future__ import annotations

from datetime import datetime, timezone

from entpy.active import ActiveSchema
from entpy.schema import BaseSchema, edge, field
from entpy.schema import from_


class Car(ActiveSchema, BaseSchema):
    @classmethod
    def fields(cls):
        return [
            field.string("model"),
            field.time("registered_at").default(
                lambda: datetime.now(timezone.utc)
            ),
        ]

    @classmethod
    def edges(cls):
        from examples.start.models.user import User

        return [
            from_("owner", User).ref("cars").unique(),
        ]
