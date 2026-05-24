"""User 实体 Observer — 演示 creating / created 生命周期。"""

from __future__ import annotations

from entpy.observer import Observer
from entpy.runtime.mutation import Mutation


class UserObserver(Observer):
    def creating(self, mutation: Mutation) -> None:
        if "name" in mutation.fields and isinstance(mutation.fields["name"], str):
            mutation.fields["name"] = mutation.fields["name"].strip()

    def created(self, mutation: Mutation) -> None:
        # 持久化后回调；可写审计日志、发消息等
        _ = mutation.id
