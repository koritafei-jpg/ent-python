"""Gremlin 社交图 demo 模型。"""

from examples.demos.gremlin.models.comment import Comment
from examples.demos.gremlin.models.person import Person
from examples.demos.gremlin.models.post import Post

GREMLIN_SCHEMAS = [Person, Post, Comment]

__all__ = ["Person", "Post", "Comment", "GREMLIN_SCHEMAS"]
