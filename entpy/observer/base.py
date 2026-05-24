"""Observer 基类与 @observes 装饰器。"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from entpy.runtime.mutation import Mutation
    from entpy.schema.base import Schema


class Observer:
    """实体生命周期观察者（对应 Laravel Model Observer）。

    子类命名 ``UserObserver`` 时，默认绑定 Schema ``User``。
  也可使用 ``@observes(User)`` 显式绑定，或在子类上设置 ``schema = User``。
    """

    schema: ClassVar[type[Schema] | None] = None

    def __init__(self, schema_type: type[Schema]) -> None:
        self.schema_type = schema_type

    @classmethod
    def schema_name(cls) -> str | None:
        if cls.schema is not None:
            return cls.schema.__name__
        name = cls.__name__
        if name.endswith("Observer"):
            return name[: -len("Observer")]
        return None

    # --- 变更前（可修改 mutation.fields）---

    def creating(self, mutation: Mutation) -> None:
        pass

    def updating(self, mutation: Mutation) -> None:
        pass

    def deleting(self, mutation: Mutation) -> None:
        pass

    # --- 变更后（持久化已完成，mutation.id 已填充）---

    def created(self, mutation: Mutation) -> None:
        pass

    def updated(self, mutation: Mutation) -> None:
        pass

    def deleted(self, mutation: Mutation) -> None:
        pass

    # --- 统一回调（create / update 后、delete 后）---

    def on_save(self, mutation: Mutation) -> None:
        """持久化成功后（CREATE / UPDATE_ONE）。"""
        pass

    def on_delete(self, mutation: Mutation) -> None:
        """删除成功后（DELETE / DELETE_ONE）。"""
        pass


def observes(schema: type[Schema]):
    """装饰 Observer 类并登记到全局注册表（Observer 模块依赖 Schema，反向不依赖）。"""

    def decorator(observer_cls: type[Observer]) -> type[Observer]:
        from entpy.observer.registry import get_observer_registry

        get_observer_registry().register(schema, observer_cls)
        observer_cls.schema = schema
        return observer_cls

    return decorator
