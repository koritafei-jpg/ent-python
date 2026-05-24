from __future__ import annotations

from entpy.observer import Observer
from entpy.runtime.mutation import Mutation
from examples.demos.common.observer_log import record


class CommentObserver(Observer):
    def on_save(self, mutation: Mutation) -> None:
        record("Comment", "on_save", mutation)

    def on_delete(self, mutation: Mutation) -> None:
        record("Comment", "on_delete", mutation)
