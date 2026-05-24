from __future__ import annotations

from entpy.observer import Observer
from entpy.runtime.mutation import Mutation
from examples.demos.common.observer_log import record


class PersonObserver(Observer):
    def on_save(self, mutation: Mutation) -> None:
        record("Person", "on_save", mutation)

    def on_delete(self, mutation: Mutation) -> None:
        record("Person", "on_delete", mutation)
