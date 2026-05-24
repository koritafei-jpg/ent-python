"""CRM 关系 demo 模型。"""

from examples.demos.relational.models.article import Article
from examples.demos.relational.models.author import Author
from examples.demos.relational.models.comment import Comment

SCHEMAS = [Author, Article, Comment]

__all__ = ["Author", "Article", "Comment", "SCHEMAS"]
