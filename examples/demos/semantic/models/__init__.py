"""语义检索 demo 模型。"""

from examples.demos.semantic.models.document import Document
from examples.demos.semantic.models.section import Section

SEARCH_SCHEMAS = [Document, Section]

__all__ = ["Document", "Section", "SEARCH_SCHEMAS"]
