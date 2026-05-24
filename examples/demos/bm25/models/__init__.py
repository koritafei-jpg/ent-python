"""BM25 demo 模型。"""

from examples.demos.bm25.models.document import Document
from examples.demos.bm25.models.section import Section

SEARCH_SCHEMAS = [Document, Section]

__all__ = ["Document", "Section", "SEARCH_SCHEMAS"]
