"""ent 入门示例模型 — https://entgo.io/docs/getting-started"""

from examples.start.models.car import Car
from examples.start.models.group import Group
from examples.start.models.user import User

SCHEMAS = [User, Car, Group]

__all__ = ["User", "Car", "Group", "SCHEMAS"]
