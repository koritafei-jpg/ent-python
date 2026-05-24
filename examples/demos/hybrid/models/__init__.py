"""混合检索 demo 模型。"""

from examples.demos.hybrid.models.document import Document
from examples.demos.hybrid.models.section import Section

SEARCH_SCHEMAS = [Document, Section]

__all__ = ["Document", "Section", "SEARCH_SCHEMAS"]
